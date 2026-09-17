import json

from main import handle_request
from models import ToolResult


def execute_tool_call(
    tool_call: dict,
    workspace_root: str | None = None,
) -> ToolResult:
    raw = json.dumps({
        "name": tool_call["name"],
        "arguments": tool_call["arguments"],
    })

    return handle_request(raw, workspace_root = workspace_root)


def run_agent(
        model,     #函数
        user_message: str,
        max_steps: int = 5,
        workspace_root: str | None = None,
        allowed_tool_names: set[str] | None = None,
) -> str:
    messages = [
        {
            "role": "user",
            "content": user_message,
        }
    ]

    for _ in range(max_steps):
        response = model(messages)
        response_type = response["type"]

        if response_type == "final":
            return response["content"]

        if response_type == "incomplete":
            return "模型响应未正常完成"

        if response_type == "tool_call":
            name = response["name"]
            if allowed_tool_names is not None and name not in allowed_tool_names:
                return "模型请求了未开放的工具"

            result = execute_tool_call(response, workspace_root)
            messages.append({
                "role": "tool",
                "content": result.content,
                "is_error": result.is_error,
            })
            continue

        if response_type == "tool_calls":
            messages.append(response["assistant_message"])

            for call in response["calls"]:
                name = call["name"]
                if allowed_tool_names is not None and name not in allowed_tool_names:
                    return "模型请求了未开放的工具"

                try:
                    arguments = json.loads(call["arguments"])
                except json.JSONDecodeError:
                    result = ToolResult(
                        content="工具参数不是有效JSON",
                        is_error=True,
                    )
                else:
                    result = execute_tool_call(
                        {"name": name, "arguments": arguments},
                        workspace_root,
                    )

                print("本地工具结果：", result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps({
                        "content": result.content,
                        "is_error": result.is_error,
                    }, ensure_ascii=False),
                })
            continue

        return "未知模型响应类型"

    return "达到最大步骤数"
