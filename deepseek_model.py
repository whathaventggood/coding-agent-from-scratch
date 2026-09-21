import os

from openai import (
    APIConnectionError,  ##网络或代理连接失败
    APIStatusError,  # 服务器返回其他 HTTP 错误
    APITimeoutError,  # 请求超过等待时间
    AuthenticationError,  # Key 无效或没有权限
    OpenAI,
    OpenAIError,  # SDK 的其他错误
    RateLimitError,  # 请求频率或额度受到限制
)

from agent_loop import run_agent
from models import ToolTraceEntry

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
                },
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "可选，从第几行开始读取，行号从1开始",
                },
                "max_lines": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "description": "可选，本次最多读取多少行",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}

RUN_TESTS_TOOL = {
    "type": "function",
    "function": {
        "name": "run_tests",
        "description": "在受信工作区内运行固定的 pytest 测试命令",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "工作区内要运行测试的目录",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}

SEARCH_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "search_file",
        "description": "在工作区内的指定文件中查找关键词",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", },
                "keyword": {"type": "string"},
            },
            "required": ["path", "keyword"],
            "additionalProperties": False,
        },
    },
}

EDIT_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": "将文件中唯一一处 old_text 替换为 new_text",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        }
    }
}

LIST_FILES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "列出工作区指定目录下一层的文件和子目录，并标明类型",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}

CREATE_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "create_file",
        "description": "在受信工作区内创建一个不存在的UTF-8文本文件，不允许覆盖已有文件",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要创建的文件路径",
                },
                "content": {
                    "type": "string",
                    "description": "要写入文件的完整文本内容",
                },
            },
            "required": ["path", "content"],
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
        timeout=30.0,
        max_retries=1,  # 遇到可重试错误时，SDK最多自动重试一次
    )


def request_chat_completion(client: OpenAI, **request_options):
    try:
        return client.chat.completions.create(**request_options)
    except AuthenticationError as error:
        raise RuntimeError(
            "DeepSeek 鉴权失败，请检查 DEEPSEEK_API_KEY"
        ) from error
    except RateLimitError as error:
        raise RuntimeError(
            "DeepSeek 请求受到限流，请稍后重试或检查账户额度"
        ) from error
    except APITimeoutError as error:
        raise RuntimeError(
            "DeepSeek 请求超时，请稍后重试"
        ) from error
    except APIConnectionError as error:
        raise RuntimeError(
            "无法连接 DeepSeek，请检查网络或代理"
        ) from error
    except APIStatusError as error:
        raise RuntimeError(
            f"DeepSeek 服务返回错误（HTTP {error.status_code}）"
        ) from error
    except OpenAIError as error:
        raise RuntimeError(
            "DeepSeek 模型请求失败"
        ) from error


def ask_deepseek(prompt: str) -> str:
    client = create_deepseek_client()

    response = request_chat_completion(
        client,
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

    response = request_chat_completion(
        client,
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


def read_file_and_answer(
        prompt: str,
        max_steps: int = 5,
        workspace_root: str | None = None,
        allow_edit: bool = False,
        tool_trace: list[ToolTraceEntry] | None = None,
) -> str:
    if allow_edit and workspace_root is None:
        raise ValueError("编辑工具需要受信工作区")

    client = create_deepseek_client()
    available_tools = [READ_FILE_TOOL]
    allowed_tool_names = {"read_file"}

    if workspace_root is not None:
        available_tools.extend([
            LIST_FILES_TOOL,
            SEARCH_FILE_TOOL,
            RUN_TESTS_TOOL,
        ])
        allowed_tool_names.update({
            "list_files",
            "search_file",
            "run_tests",
        })

        if allow_edit:
            available_tools.extend([
                EDIT_FILE_TOOL,
                CREATE_FILE_TOOL,
            ])
            allowed_tool_names.update({
                "edit_file",
                "create_file",
            })

    def model(messages):
        response = request_chat_completion(
            client,
            model="deepseek-flash",
            messages=messages,
            tools=available_tools,
            tool_choice="auto",
            max_tokens=300,
            stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )

        choice = response.choices[0]
        message = choice.message

        if not message.tool_calls:
            if choice.finish_reason != "stop":
                return {"type": "incomplete"}
            return {
                "type": "final",
                "content": message.content or "",
            }

        calls = []
        for call in message.tool_calls:
            calls.append({
                "id": call.id,
                "name": call.function.name,
                "arguments": call.function.arguments,
            })

        return {
            "type": "tool_calls",
            "assistant_message": message,
            "calls": calls,
        }

    return run_agent(
        model,
        prompt,
        max_steps=max_steps,
        workspace_root=workspace_root,
        allowed_tool_names=allowed_tool_names,
        tool_trace=tool_trace,
    )


if __name__ == "__main__":
    answer = read_file_and_answer(
        "请使用 read_file 读取 demo.txt，并告诉我文件的完整内容"
    )
    print("模型回答：", answer)
