import json

from main import handle_request
from models import ContextUsageStats, ToolResult, ToolTraceEntry
from dataclasses import dataclass, field

MAX_TOOL_RESULT_CHARS = 4000
MAX_TOTAL_TOOL_RESULT_CHARS = 12000
MAX_HISTORY_SUMMARY_CHARS = 2000
MAX_TOTAL_MESSAGE_CHARS = 24000


@dataclass
class ToolMessageState:
    message: dict
    compressed_content: str
    included_chars: int
    is_compressed: bool = False


@dataclass
class HistoryTrimState:
    summary_lines: list[str] = field(default_factory=list)


def json_fallback(value):
    model_dump = getattr(type(value), "model_dump", None)

    if callable(model_dump):
        return model_dump(
            value,
            mode="json",
            exclude_none=True,
        )

    return str(value)


def estimate_messages_chars(messages: list) -> int:
    serialized = json.dumps(
        messages,
        ensure_ascii=False,
        separators=(",", ":"),
        default=json_fallback,
    )
    return len(serialized)


def get_message_role(message) -> str | None:
    if isinstance(message, dict):
        return message.get("role")

    return getattr(message, "role", None)


def limit_history_summary_lines(
        lines: list[str],
        limit: int = MAX_HISTORY_SUMMARY_CHARS,
) -> list[str]:
    prefix = "[较早工具结果摘要]"
    selected_reversed = []
    used_chars = len(prefix)

    for line in reversed(lines):
        required_chars = 1 + len(line)

        if used_chars + required_chars > limit:
            break

        selected_reversed.append(line)
        used_chars += required_chars

    return list(reversed(selected_reversed))


def build_history_summary_message(
        lines: list[str],
) -> dict:
    content = "[较早工具结果摘要]"

    if lines:
        content += "\n" + "\n".join(lines)

    return {
        "role": "assistant",
        "content": content,
    }


def trim_message_history(
        messages: list,
        tool_message_states: list[ToolMessageState],
        trim_state: HistoryTrimState,
        max_chars: int,
) -> tuple[int, int]:
    before_chars = estimate_messages_chars(messages)

    if before_chars <= max_chars:
        return 0, 0

    pending_indices = []

    for state in tool_message_states:
        if state.is_compressed:
            continue

        for index, message in enumerate(messages):
            if message is state.message:
                pending_indices.append(index)
                break

    if not pending_indices:
        raise RuntimeError(
            "完整消息历史超过近似字符上限，"
            "且没有可安全裁剪的旧工具交互"
        )

    keep_start = min(pending_indices)

    if (
            keep_start > 1
            and get_message_role(messages[keep_start - 1])
            == "assistant"
    ):
        keep_start -= 1

    removable_messages = messages[1:keep_start]
    removable_ids = {
        id(message)
        for message in removable_messages
    }

    removed_states = [
        state
        for state in tool_message_states
        if (
                id(state.message) in removable_ids
                and state.is_compressed
        )
    ]

    if not removed_states:
        raise RuntimeError(
            "完整消息历史超过近似字符上限，"
            "但旧消息尚未形成可安全裁剪的完整交互"
        )

    trim_state.summary_lines.extend(
        state.compressed_content
        for state in removed_states
    )
    trim_state.summary_lines = limit_history_summary_lines(
        trim_state.summary_lines
    )

    summary_message = build_history_summary_message(
        trim_state.summary_lines
    )

    messages[1:keep_start] = [summary_message]

    tool_message_states[:] = [
        state
        for state in tool_message_states
        if id(state.message) not in removable_ids
    ]

    after_chars = estimate_messages_chars(messages)

    while (
            after_chars > max_chars
            and trim_state.summary_lines
    ):
        trim_state.summary_lines.pop(0)

        if trim_state.summary_lines:
            messages[1] = build_history_summary_message(
                trim_state.summary_lines
            )
        else:
            messages.pop(1)

        after_chars = estimate_messages_chars(messages)

    if after_chars > max_chars:
        raise RuntimeError(
            "初始任务和最新工具交互已经超过"
            "完整消息历史近似字符上限"
        )

    removed_message_count = len(removable_messages)
    released_chars = before_chars - after_chars

    return removed_message_count, released_chars


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
) -> tuple[int, int]:
    compressed_count = 0
    released_chars = 0

    for state in states:
        if state.is_compressed:
            continue

        state.message["content"] = state.compressed_content
        state.is_compressed = True
        compressed_count += 1
        released_chars += state.included_chars

    return compressed_count, released_chars


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
        context_usage: ContextUsageStats | None = None,
        max_total_message_chars: int = MAX_TOTAL_MESSAGE_CHARS,
) -> str:
    messages = [
        {
            "role": "user",
            "content": user_message,
        }
    ]
    tool_result_chars_sent = 0
    tool_message_states: list[ToolMessageState] = []
    history_trim_state = HistoryTrimState()

    for model_step in range(1, max_steps + 1):
        trimmed_count, released_history_chars = trim_message_history(
            messages,
            tool_message_states,
            history_trim_state,
            max_chars=max_total_message_chars,
        )

        if context_usage is not None and trimmed_count:
            context_usage.history_trim_count += 1
            context_usage.trimmed_message_count += trimmed_count
            context_usage.released_history_chars += (
                released_history_chars
            )
        message_chars = estimate_messages_chars(messages)

        if context_usage is not None:
            context_usage.request_message_chars.append(message_chars)
            context_usage.peak_message_chars = max(
                context_usage.peak_message_chars,
                message_chars,
            )

        response = model(messages)

        compressed_count, released_chars = (
            compress_tool_messages_seen_by_model(
                tool_message_states,
            )
        )

        if context_usage is not None:
            context_usage.compressed_tool_message_count += compressed_count
            context_usage.released_tool_result_chars += released_chars
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
