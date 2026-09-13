import json

from main import handle_request
from models import ToolResult


def execute_tool_call(tool_call: dict) -> ToolResult:
    raw = json.dumps({
        "name": tool_call["name"],
        "arguments": tool_call["arguments"],
    })

    return handle_request(raw)


def run_agent(
        model,
        user_message: str,
        max_steps: int = 5,
) -> str:
    messages = [
        {
            "role": "user",
            "content": user_message,
        }
    ]

    for _ in range(max_steps):
        response = model(messages)

        if response["type"] == "final":
            return response["content"]

        if response["type"] == "tool_call":
            tool_result = execute_tool_call(response)
            messages.append(
                {
                    "role": "tool",
                    "content": tool_result.content,
                    "is_error": tool_result.is_error,
                }
            )

        else:
            return "未知模型响应类型"

    return "达到最大步骤数"
