import json
import pytest

from unittest.mock import Mock

import deepseek_model


def test_read_loop_returns_matching_tool_result(tmp_path, monkeypatch):
    file_path = tmp_path / "example.txt"
    file_path.write_text("练习编号：927", encoding="utf-8")

    tool_call = Mock()  # 创建一个假的工具调用对象
    tool_call.id = "call_read_1"
    tool_call.function.name = "read_file"
    tool_call.function.arguments = json.dumps({"path": str(file_path)})

    request_message = Mock(tool_calls=[tool_call], content=None)
    final_message = Mock(tool_calls=None, content="练习编号：927")
    first_response = Mock(
        choices=[Mock(message=request_message, finish_reason="tool_calls")]
    )

    def fake_create(**kwargs):
        if client.chat.completions.create.call_count == 1:
            return first_response

        assert kwargs["messages"][-2] is request_message
        tool_message = kwargs["messages"][-1]
        assert tool_message["role"] == "tool"
        assert tool_message["tool_call_id"] == "call_read_1"
        assert json.loads(tool_message["content"]) == {
            "content": "练习编号：927",
            "is_error": False,
        }
        return Mock(
            choices=[Mock(message=final_message, finish_reason="stop")]
        )

    client = Mock()
    client.chat.completions.create.side_effect = fake_create
    monkeypatch.setattr(deepseek_model, "create_deepseek_client", lambda: client)

    answer = deepseek_model.read_file_and_answer("读取练习文件")

    assert answer == "练习编号：927"
    assert client.chat.completions.create.call_count == 2


def test_read_loop_returns_missing_file_error(tmp_path, monkeypatch):
    file_path = tmp_path / "missing.txt"

    tool_call = Mock()
    tool_call.id = "call_missing_1"
    tool_call.function.name = "read_file"
    tool_call.function.arguments = json.dumps({"path": str(file_path)})

    request_message = Mock(tool_calls=[tool_call], content=None)
    final_message = Mock(tool_calls=None, content="文件不存在")
    first_response = Mock(
        choices=[Mock(message=request_message, finish_reason="tool_calls")]
    )

    def fake_create(**kwargs):
        if client.chat.completions.create.call_count == 1:
            return first_response

        assert kwargs["messages"][-2] is request_message
        tool_message = kwargs["messages"][-1]
        assert tool_message["role"] == "tool"
        assert tool_message["tool_call_id"] == "call_missing_1"
        assert json.loads(tool_message["content"]) == {
            "content": "文件不存在",
            "is_error": True,
        }
        return Mock(
            choices=[Mock(message=final_message, finish_reason="stop")]
        )

    client = Mock()
    client.chat.completions.create.side_effect = fake_create
    monkeypatch.setattr(deepseek_model, "create_deepseek_client", lambda: client)

    answer = deepseek_model.read_file_and_answer("读取练习文件")

    assert answer == "文件不存在"
    assert client.chat.completions.create.call_count == 2


def test_read_loop_returns_invalid_json_error(monkeypatch):
    tool_call = Mock()
    tool_call.id = "call_invalid_json_1"
    tool_call.function.name = "read_file"
    tool_call.function.arguments = '{"path":'

    request_message = Mock(tool_calls=[tool_call], content=None)
    final_message = Mock(tool_calls=None, content="工具参数不是有效JSON")
    first_response = Mock(
        choices=[Mock(message=request_message, finish_reason="tool_calls")]
    )

    def fake_create(**kwargs):
        if client.chat.completions.create.call_count == 1:
            return first_response

        assert kwargs["messages"][-2] is request_message
        tool_message = kwargs["messages"][-1]
        assert tool_message["role"] == "tool"
        assert tool_message["tool_call_id"] == "call_invalid_json_1"
        assert json.loads(tool_message["content"]) == {
            "content": "工具参数不是有效JSON",
            "is_error": True,
        }
        return Mock(
            choices=[Mock(message=final_message, finish_reason="stop")]
        )

    client = Mock()
    client.chat.completions.create.side_effect = fake_create
    monkeypatch.setattr(deepseek_model, "create_deepseek_client", lambda: client)

    answer = deepseek_model.read_file_and_answer("读取练习文件")

    assert answer == "工具参数不是有效JSON"
    assert client.chat.completions.create.call_count == 2


def test_read_loop_stops_at_max_steps(tmp_path, monkeypatch):
    file_path = tmp_path / "example.txt"
    file_path.write_text("练习编号：927", encoding="utf-8")

    tool_call = Mock()
    tool_call.id = "call_read_1"
    tool_call.function.name = "read_file"
    tool_call.function.arguments = json.dumps({
        "path": str(file_path),
    })

    request_message = Mock(
        tool_calls=[tool_call],
        content=None,
    )
    repeated_response = Mock(
        choices=[
            Mock(
                message=request_message,
                finish_reason="tool_calls",
            )
        ]
    )

    client = Mock()
    client.chat.completions.create.return_value = repeated_response

    monkeypatch.setattr(
        deepseek_model,
        "create_deepseek_client",
        lambda: client,
    )

    with pytest.raises(
            RuntimeError,
            match="达到最大步骤数",
    ):
        deepseek_model.read_file_and_answer(
            "不断读取文件",
            max_steps=3,
        )
    assert client.chat.completions.create.call_count == 3


def test_read_loop_runs_tests_with_trusted_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test_smoke.py").write_text(
        "def test_smoke():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )

    tool_call = Mock()
    tool_call.id = "call_tests_1"
    tool_call.function.name = "run_tests"
    tool_call.function.arguments = json.dumps({"path": str(workspace)})

    request_message = Mock(tool_calls=[tool_call], content=None)
    final_message = Mock(tool_calls=None, content="测试通过")
    first_response = Mock(
        choices=[Mock(message=request_message, finish_reason="tool_calls")]
    )
    final_response = Mock(
        choices=[Mock(message=final_message, finish_reason="stop")]
    )

    client = Mock()

    def fake_create(**kwargs):
        if client.chat.completions.create.call_count == 1:
            names = {
                tool["function"]["name"]
                for tool in kwargs["tools"]
            }
            assert names == {
                "list_files",
                "read_file",
                "search_file",
                "search_workspace",
                "run_tests",
                "run_test_file",
                "inspect_git_changes",
            }
            return first_response

        tool_message = kwargs["messages"][-1]
        assert tool_message["role"] == "tool"
        assert tool_message["tool_call_id"] == "call_tests_1"

        payload = json.loads(tool_message["content"])
        assert payload["is_error"] is False
        assert "1 passed" in payload["content"]
        return final_response

    client.chat.completions.create.side_effect = fake_create
    monkeypatch.setattr(
        deepseek_model,
        "create_deepseek_client",
        lambda: client,
    )

    answer = deepseek_model.read_file_and_answer(
        "运行工作区测试",
        workspace_root=str(workspace),
    )

    assert answer == "测试通过"
    assert client.chat.completions.create.call_count == 2


def test_edit_tool_with_local_permission(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    note = workspace / "note.txt"
    note.write_text("旧内容\n", encoding="utf-8")

    tool_call = Mock()
    tool_call.id = "call_edit_1"
    tool_call.function.name = "edit_file"
    tool_call.function.arguments = json.dumps({
        "path": "note.txt",
        "old_text": "旧内容",
        "new_text": "新内容",
    })

    request_message = Mock(tool_calls=[tool_call], content=None)
    final_message = Mock(tool_calls=None, content="已修改")
    client = Mock()

    def fake_create(**kwargs):
        if client.chat.completions.create.call_count == 1:
            names = {tool["function"]["name"] for tool in kwargs["tools"]}
            assert names == {
                "list_files",
                "read_file",
                "search_file",
                "search_workspace",
                "run_tests",
                "run_test_file",
                "edit_file",
                "create_file",
                "create_directory",
                "inspect_git_changes",
            }
            return Mock(choices=[
                Mock(message=request_message, finish_reason="tool_calls")
            ])

        tool_message = kwargs["messages"][-1]
        assert tool_message["tool_call_id"] == "call_edit_1"
        assert json.loads(tool_message["content"]) == {
            "content": "新内容\n",
            "is_error": False,
        }
        return Mock(choices=[
            Mock(message=final_message, finish_reason="stop")
        ])

    client.chat.completions.create.side_effect = fake_create
    monkeypatch.setattr(deepseek_model, "create_deepseek_client", lambda: client)

    answer = deepseek_model.read_file_and_answer(
        "修改 note.txt",
        workspace_root=str(workspace),
        allow_edit=True,
    )

    assert answer == "已修改"
    assert note.read_text(encoding="utf-8") == "新内容\n"
