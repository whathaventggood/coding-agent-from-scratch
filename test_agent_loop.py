import json

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


def test_run_agent_repairs_after_failed_test(tmp_path):
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    (tmp_path / "test_calculator.py").write_text(
        "from calculator import add\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    requests = [
        ("run_tests", {"path": "."}),
        ("read_file", {"path": "calculator.py"}),
        ("edit_file", {
            "path": "calculator.py",
            "old_text": "return a - b",
            "new_text": "return a + b",
        }),
        ("run_tests", {"path": "."}),
    ]

    def fake_model(messages):
        step = (len(messages) - 1) // 2
        if step:
            tool_message = messages[-1]
            assert tool_message["tool_call_id"] == f"call_{step}"
            result = json.loads(tool_message["content"])
            assert result["is_error"] is (step == 1)

        if step == len(requests):
            return {"type": "final", "content": "修复完成"}

        name, arguments = requests[step]
        return {
            "type": "tool_calls",
            "assistant_message": {"role": "assistant", "content": None},
            "calls": [{
                "id": f"call_{step + 1}",
                "name": name,
                "arguments": json.dumps(arguments),
            }],
        }

    answer = run_agent(
        fake_model,
        "修复失败的测试",
        max_steps=5,
        workspace_root=str(tmp_path),
        allowed_tool_names={"run_tests", "read_file", "edit_file"},
    )

    assert answer == "修复完成"
    assert "return a + b" in (tmp_path / "calculator.py").read_text(
        encoding="utf-8"
    )
