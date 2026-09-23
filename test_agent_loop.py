import json
import pytest

from agent_loop import (
    ToolMessageState,
    compress_tool_messages_seen_by_model,
    estimate_messages_chars,
    execute_tool_call,
    run_agent,
)
from models import ContextUsageStats, ToolResult


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

    with pytest.raises(
            RuntimeError,
            match="达到最大步骤数",
    ):
        run_agent(
            fake_model,
            "请一直读取文件",
            max_steps=3,
        )
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


def test_run_agent_recomputes_budget_between_parallel_tool_calls(
        tmp_path,
):
    file_path = tmp_path / "large.txt"
    file_path.write_text(
        "abcdefghij",
        encoding="utf-8",
    )

    tool_trace = []
    captured_messages = None

    def fake_model(messages):
        nonlocal captured_messages
        captured_messages = messages
        return {
            "type": "tool_calls",
            "assistant_message": {
                "role": "assistant",
                "content": None,
            },
            "calls": [
                {
                    "id": "call_1",
                    "name": "read_file",
                    "arguments": json.dumps({
                        "path": str(file_path),
                    }),
                },
                {
                    "id": "call_2",
                    "name": "read_file",
                    "arguments": json.dumps({
                        "path": str(file_path),
                    }),
                },
                {
                    "id": "call_3",
                    "name": "read_file",
                    "arguments": json.dumps({
                        "path": str(file_path),
                    }),
                },
            ],
        }

    with pytest.raises(
            RuntimeError,
            match="工具结果累计超过上下文预算",
    ):
        run_agent(
            fake_model,
            "同一轮读取三次文件",
            max_steps=2,
            tool_trace=tool_trace,
            max_total_tool_result_chars=12,
        )

    assert len(tool_trace) == 2

    assert captured_messages is not None

    tool_messages = [
        message
        for message in captured_messages
        if (
                isinstance(message, dict)
                and message.get("role") == "tool"
        )
    ]

    assert len(tool_messages) == 2
    assert [
               message["tool_call_id"]
               for message in tool_messages
           ] == [
               "call_1",
               "call_2",
           ]


def test_run_agent_compresses_seen_results_and_reuses_budget(
        tmp_path,
):
    file_path = tmp_path / "large.txt"
    file_path.write_text(
        "abcdefghij",
        encoding="utf-8",
    )

    model_call_count = 0

    def fake_model(messages):
        nonlocal model_call_count
        model_call_count += 1

        if model_call_count == 1:
            return {
                "type": "tool_calls",
                "assistant_message": {
                    "role": "assistant",
                    "content": None,
                },
                "calls": [{
                    "id": "call_1",
                    "name": "read_file",
                    "arguments": json.dumps({
                        "path": str(file_path),
                    }),
                }],
            }

        if model_call_count == 2:
            first_result = json.loads(
                messages[-1]["content"]
            )

            assert first_result == {
                "content": "abcdefghij",
                "is_error": False,
            }

            return {
                "type": "tool_calls",
                "assistant_message": {
                    "role": "assistant",
                    "content": None,
                },
                "calls": [{
                    "id": "call_2",
                    "name": "read_file",
                    "arguments": json.dumps({
                        "path": str(file_path),
                    }),
                }],
            }

        first_result = json.loads(
            messages[-3]["content"]
        )
        second_result = json.loads(
            messages[-1]["content"]
        )

        assert messages[-3]["tool_call_id"] == "call_1"
        assert first_result == {
            "content": (
                "[旧工具结果已压缩] "
                "read_file：读取成功，返回 10 个字符"
            ),
            "is_error": False,
        }

        assert messages[-1]["tool_call_id"] == "call_2"
        assert second_result == {
            "content": "abcdefghij",
            "is_error": False,
        }

        return {
            "type": "final",
            "content": "读取完成",
        }

    context_usage = ContextUsageStats()
    answer = run_agent(
        fake_model,
        "连续读取文件",
        max_steps=3,
        max_total_tool_result_chars=12,
        context_usage=context_usage,
    )

    assert answer == "读取完成"
    assert model_call_count == 3
    assert context_usage.model_request_count == 3
    assert len(context_usage.request_message_chars) == 3
    assert context_usage.peak_message_chars == max(
        context_usage.request_message_chars
    )
    assert context_usage.compressed_tool_message_count == 2
    assert context_usage.released_tool_result_chars == 20


def test_compressing_tool_message_reduces_full_message_chars():
    tool_message = {
        "role": "tool",
        "content": "x" * 1000,
        "is_error": False,
    }
    messages = [
        {
            "role": "user",
            "content": "读取文件",
        },
        tool_message,
    ]
    states = [
        ToolMessageState(
            message=tool_message,
            compressed_content=(
                "[旧工具结果已压缩] "
                "read_file：读取成功，返回 1000 个字符"
            ),
            included_chars=1000,
        )
    ]

    before_chars = estimate_messages_chars(messages)

    compressed_count, released_chars = (
        compress_tool_messages_seen_by_model(states)
    )

    after_chars = estimate_messages_chars(messages)

    assert after_chars < before_chars
    assert compressed_count == 1
    assert released_chars == 1000
