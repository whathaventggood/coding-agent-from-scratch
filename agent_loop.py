import json

from main import handle_request
from models import ToolResult, ToolTraceEntry
from dataclasses import dataclass

MAX_TOOL_RESULT_CHARS = 4000
MAX_TOTAL_TOOL_RESULT_CHARS = 12000


@dataclass
class ToolMessageState:
    message: dict
    compressed_content: str
    included_chars: int
    is_compressed: bool = False


def execute_tool_call(
        tool_call: dict,
        workspace_root: str | None = None,
) -> ToolResult:
    raw = json.dumps({
        "name": tool_call["name"],
        "arguments": tool_call["arguments"],
    })

    return handle_request(raw, workspace_root=workspace_root)


def limit_tool_result_for_model(
        result: ToolResult,
        limit: int = MAX_TOOL_RESULT_CHARS,
) -> ToolResult:
    if len(result.content) <= limit:
        return result

    omitted_count = len(result.content) - limit
    limited_content = (
            result.content[:limit]
            + "\n"
            + f"[工具结果已截断，省略 {omitted_count} 个字符]"
    )

    return ToolResult(
        content=limited_content,
        is_error=result.is_error,
    )


def limit_tool_result_with_budget(
        result: ToolResult,
        remaining_chars: int,
) -> tuple[ToolResult, int]:
    if remaining_chars <= 0:
        raise RuntimeError(
            "工具结果累计超过上下文预算，请缩小读取或搜索范围"
        )

    result_limit = min(
        MAX_TOOL_RESULT_CHARS,
        remaining_chars,
    )

    model_result = limit_tool_result_for_model(
        result,
        limit=result_limit,
    )
    included_chars = min(
        len(result.content),
        result_limit,
    )

    return model_result, included_chars


def shorten_text(text: str, limit: int = 160) -> str:
    compact = " ".join(text.split())

    if not compact:
        return "无输出"

    if len(compact) <= limit:
        return compact

    return compact[:limit] + "…"


def summarize_tool_result(
        tool_name: str,
        result: ToolResult,
) -> str:
    if result.is_error:
        return shorten_text(result.content)

    if tool_name == "read_file":
        return f"读取成功，返回 {len(result.content)} 个字符"

    if tool_name == "list_files":
        item_count = len(result.content.splitlines())
        return f"列出 {item_count} 项"

    if tool_name in {"search_file", "search_workspace"}:
        line_count = len(result.content.splitlines())
        return f"搜索完成，返回 {line_count} 行结果"

    if tool_name == "edit_file":
        return "文件编辑完成"

    if tool_name == "create_file":
        return "文件创建完成"

    if tool_name == "create_directory":
        return "目录创建完成"

    if tool_name == "rename_file":
        return "文件重命名完成"

    if tool_name == "inspect_git_changes":
        return "Git 变化检查完成"

    if tool_name == "delete_file":
        return "文件删除完成"

    return shorten_text(result.content)


def build_compressed_tool_content(
        tool_name: str,
        result: ToolResult,
        structured: bool,
) -> str:
    summary = summarize_tool_result(
        tool_name,
        result,
    )
    compressed_content = (
        f"[旧工具结果已压缩] {tool_name}：{summary}"
    )

    if not structured:
        return compressed_content

    return json.dumps(
        {
            "content": compressed_content,
            "is_error": result.is_error,
        },
        ensure_ascii=False,
    )


def compress_tool_messages_seen_by_model(
        states: list[ToolMessageState],
) -> int:
    released_chars = 0

    for state in states:
        if state.is_compressed:
            continue

        state.message["content"] = state.compressed_content
        state.is_compressed = True
        released_chars += state.included_chars

    return released_chars


def append_tool_trace(
        tool_trace: list[ToolTraceEntry] | None,
        model_step: int,
        tool_name: str,
        result: ToolResult,
) -> None:
    if tool_trace is None:
        return

    tool_trace.append(
        ToolTraceEntry(
            model_step=model_step,
            tool_name=tool_name,
            is_error=result.is_error,
            summary=summarize_tool_result(tool_name, result),
        )
    )


def run_agent(
        model,
        user_message: str,
        max_steps: int = 5,
        workspace_root: str | None = None,
        allowed_tool_names: set[str] | None = None,
        tool_trace: list[ToolTraceEntry] | None = None,
        max_total_tool_result_chars: int = MAX_TOTAL_TOOL_RESULT_CHARS,
) -> str:
    messages = [
        {
            "role": "user",
            "content": user_message,
        }
    ]
    tool_result_chars_sent = 0
    tool_message_states: list[ToolMessageState] = []

    for model_step in range(1, max_steps + 1):
        response = model(messages)

        released_chars = compress_tool_messages_seen_by_model(
            tool_message_states,
        )
        tool_result_chars_sent = max(
            0,
            tool_result_chars_sent - released_chars,
        )

        response_type = response["type"]

        if response_type == "final":
            return response["content"]

        if response_type == "incomplete":
            raise RuntimeError("模型响应未正常完成")

        if response_type == "tool_call":
            remaining_chars = (
                    max_total_tool_result_chars
                    - tool_result_chars_sent
            )

            if remaining_chars <= 0:
                raise RuntimeError(
                    "工具结果累计超过上下文预算，请缩小读取或搜索范围"
                )
            name = response["name"]

            if allowed_tool_names is not None and name not in allowed_tool_names:
                result = ToolResult(
                    content="模型请求了未开放的工具",
                    is_error=True,
                )
                append_tool_trace(
                    tool_trace,
                    model_step,
                    name,
                    result,
                )
                raise RuntimeError(result.content)

            result = execute_tool_call(response, workspace_root)
            append_tool_trace(
                tool_trace,
                model_step,
                name,
                result,
            )

            model_result, included_chars = limit_tool_result_with_budget(
                result,
                remaining_chars,
            )
            tool_result_chars_sent += included_chars

            tool_message = {
                "role": "tool",
                "content": model_result.content,
                "is_error": result.is_error,
            }
            messages.append(tool_message)

            tool_message_states.append(
                ToolMessageState(
                    message=tool_message,
                    compressed_content=build_compressed_tool_content(
                        name,
                        result,
                        structured=False,
                    ),
                    included_chars=included_chars,
                )
            )
            continue

        if response_type == "tool_calls":
            messages.append(response["assistant_message"])

            for call in response["calls"]:
                remaining_chars = (
                        max_total_tool_result_chars
                        - tool_result_chars_sent
                )

                if remaining_chars <= 0:
                    raise RuntimeError(
                        "工具结果累计超过上下文预算，请缩小读取或搜索范围"
                    )
                name = call["name"]

                if allowed_tool_names is not None and name not in allowed_tool_names:
                    result = ToolResult(
                        content="模型请求了未开放的工具",
                        is_error=True,
                    )
                    append_tool_trace(
                        tool_trace,
                        model_step,
                        name,
                        result,
                    )
                    raise RuntimeError(result.content)

                try:
                    arguments = json.loads(call["arguments"])
                except json.JSONDecodeError:
                    result = ToolResult(
                        content="工具参数不是有效JSON",
                        is_error=True,
                    )
                else:
                    result = execute_tool_call(
                        {
                            "name": name,
                            "arguments": arguments,
                        },
                        workspace_root,
                    )

                append_tool_trace(
                    tool_trace,
                    model_step,
                    name,
                    result,
                )

                model_result, included_chars = (
                    limit_tool_result_with_budget(
                        result,
                        remaining_chars,
                    )
                )
                tool_result_chars_sent += included_chars

                tool_message = {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(
                        {
                            "content": model_result.content,
                            "is_error": result.is_error,
                        },
                        ensure_ascii=False,
                    ),
                }
                messages.append(tool_message)

                tool_message_states.append(
                    ToolMessageState(
                        message=tool_message,
                        compressed_content=build_compressed_tool_content(
                            name,
                            result,
                            structured=True,
                        ),
                        included_chars=included_chars,
                    )
                )
            continue

        raise RuntimeError("未知模型响应类型")

    raise RuntimeError("达到最大步骤数")
