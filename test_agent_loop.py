from agent_loop import execute_tool_call, run_agent
from models import ToolResult


def test_execute_tool_call_reads_file(tmp_path):
    file_path = tmp_path / 'hello.txt'
    file_path.write_text(
        "hello agent",
        encoding='utf-8',
    )

    tool_call = {
        "type": "tool_call",
        "name": "read_file",
        "arguments": {
            "path": str(file_path),
        },
    }

    result = execute_tool_call(tool_call)

    assert result == ToolResult(
        content="hello agent",
        is_error=False,
    )


def test_run_agent_reads_file_then_returns_final_answer(tmp_path):
    file_path = tmp_path / "hello.txt"
    file_path.write_text(
        "hello agent",
        encoding="utf-8",
    )

    def fake_model(messages):
        if len(messages) == 1:
            return {
                "type": "tool_call",
                "name": "read_file",
                "arguments": {
                    "path": str(file_path),
                },
            }

        assert messages[-1] == {
            "role": "tool",
            "content": "hello agent",
            "is_error": False,
        }

        return {
            "type": "final",
            "content": "文件内容是hello agent",
        }

    answer = run_agent(
        fake_model,
        "请读取文件",
    )

    assert answer == "文件内容是hello agent"


def test_run_agent_searches_file_then_returns_final_answer(tmp_path):
    file_path = tmp_path / "hello.txt"
    file_path.write_text(
        "hello agent\nhello Python\nagent tools",
        encoding="utf-8",
    )

    def fake_model(messages):
        if len(messages) == 1:
            return {
                "type": "tool_call",
                "name": "search_file",
                "arguments": {
                    "path": str(file_path),
                    "keyword": "agent"
                },
            }

        assert messages[-1] == {
            "role": "tool",
            "content": "1: hello agent\n3: agent tools",
            "is_error": False,
        }

        return {
            "type": "final",
            "content": "找到了两行",
        }

    answer = run_agent(
        fake_model,
        "请搜索 agent",
    )

    assert answer == "找到了两行"


def test_run_agent_stops_at_max_steps(tmp_path):
    file_path = tmp_path / "hello.txt"
    file_path.write_text(
        "hello agent",
        encoding="utf-8",
    )
    seen_message_counts = []

    def fake_model(messages):
        seen_message_counts.append(len(messages))
        return {
            "type": "tool_call",
            "name": "read_file",
            "arguments": {
                "path": str(file_path),
            },
        }

    answer = run_agent(
        fake_model,
        "请一直读取文件",
        max_steps=3,
    )

    assert answer == "达到最大步骤数"
    assert seen_message_counts == [1, 2, 3]
