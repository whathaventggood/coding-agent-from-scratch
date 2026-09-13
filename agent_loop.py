import json

from main import handle_request
from models import ToolResult


def execute_tool_call(tool_call: dict) -> ToolResult:
    raw = json.dumps({
        "name": tool_call["name"],
        "arguments": tool_call["arguments"],
    })

    return handle_request(raw)


def run_agent(model, user_message: str) -> str:
    messages = [
        {
            "role": "user",
            "content": user_message,
        }
    ]

    while True:
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
