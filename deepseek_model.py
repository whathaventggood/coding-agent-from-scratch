import os
import json
from main import handle_request
from openai import OpenAI
from models import ToolResult

# 工具清单
READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "读取指定路径的 UTF-8 文本文件",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "需要读取的文件路径",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}


def create_deepseek_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError("缺少DEEPSEEK_API_KEY")

    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )


def ask_deepseek(prompt: str) -> str:
    client = create_deepseek_client()

    response = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        max_tokens=50,
        stream=False,
        extra_body={
            "thinking": {
                "type": "disabled",
            }
        },
    )

    return response.choices[0].message.content  # 仅需返回文本内容


def request_file_read(prompt: str):
    client = create_deepseek_client()

    response = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {"role": "user", "content": prompt},
        ],
        tools=[READ_FILE_TOOL],  # 表示tools可用的工具列表
        tool_choice={
            "type": "function",
            "function": {"name": "read_file"},
        },  # 明确指定使用read_file工具
        max_tokens=300,
        stream=False,
        extra_body={"thinking": {"type": "disabled"}},  # 不开启thinking模式
    )

    return response.choices[0].message  # 还需调用message.tool_calls


def read_file_and_answer(prompt: str, max_steps: int = 5) -> str:
    client = create_deepseek_client()
    messages = [{"role": "user", "content": prompt}]

    for _ in range(max_steps):
        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=messages,
            tools=[READ_FILE_TOOL],
            tool_choice="auto",
            max_tokens=300,
            stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )

        choice = response.choices[0]  # response.choices被设计成列表，通常需要获取的消息是第一条
        message = choice.message
        messages.append(message)

        if not message.tool_calls:
            if choice.finish_reason != "stop":
                return "模型响应未正常完成"
            return message.content or ""

        for tool_call in message.tool_calls:
            if tool_call.function.name != "read_file":
                return "模型请求了未开放的工具"
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                result = ToolResult(
                    content="工具参数不是有效JSON",
                    is_error=True,
                )
            else:
                raw = json.dumps({
                    "name": tool_call.function.name,
                    "arguments": arguments,
                })
                result = handle_request(raw)

            print("本地工具结果：", result)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps({
                    "content": result.content,
                    "is_error": result.is_error,
                }, ensure_ascii=False),
            })

    return "达到最大步骤数"


if __name__ == "__main__":
    answer = read_file_and_answer(
        "请使用 read_file 读取 demo.txt，并告诉我文件的完整内容"
    )
    print("模型回答：", answer)
