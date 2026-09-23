from main import handle_request, parse_request
from models import ToolResult, ToolRequest
from file_tools import (
    read_file, list_files, search_file, replace_text_once, edit_file
)
import subprocess
import json
from command_tool import run_tests


def test_missing_arguments():
    result = handle_request('{"name": "read_file"}')

    assert result == ToolResult(
        content="缺少arguments",
        is_error=True,
    )


def test_arguments_must_be_object():
    result = handle_request(
        '{"name": "read_file", "arguments": []}'
    )

    assert result == ToolResult(
        content="arguments必须是JSON对象",
        is_error=True,
    )


def test_request_must_be_object():
    result = handle_request("[]")

    assert result == ToolResult(
        content="请求必须是JSON对象",
        is_error=True,
    )


def test_read_file_success(tmp_path):
    file_path = tmp_path / "hello.txt"
    file_path.write_text("你好 agent", encoding="utf-8")
    result = read_file(str(file_path))
    assert result == ToolResult(
        content="你好 agent"
    )


def test_read_file_missing():
    result = read_file("not_exist.txt")
    assert result == ToolResult(
        content="文件不存在",
        is_error=True,
    )


def test_read_file_rejects_directory(tmp_path):
    result = read_file(str(tmp_path))
    assert result == ToolResult(
        content="路径是目录",
        is_error=True,
    )


def test_read_file_rejects_empty_path():
    result = read_file("")
    assert result == ToolResult(
        content="路径不能为空",
        is_error=True,
    )


def test_list_files_success(tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.py"
    folder = tmp_path / "nested"
    file_a.write_text("A", encoding="utf-8")
    file_b.write_text("B", encoding="utf-8")
    folder.mkdir()

    result = list_files(str(tmp_path))

    expected_content = "\n".join([
        f"[文件] {file_a}",
        f"[文件] {file_b}",
        f"[目录] {folder}/",
    ])

    assert result == ToolResult(
        content=expected_content
    )


def test_list_files_rejects_empty_path():
    result = list_files("")
    assert result == ToolResult(
        content="路径不能为空",
        is_error=True,
    )


def test_list_files_rejects_file_path(tmp_path):
    file_path = tmp_path / "hello.txt"
    file_path.write_text("hello", encoding="utf-8")
    result = list_files(str(file_path))
    assert result == ToolResult(
        content="不是目录",
        is_error=True,
    )


def test_missing_path():
    result = handle_request(
        '{"name": "read_file", "arguments": {}}'
    )

    assert result == ToolResult(
        content="缺少path",
        is_error=True,
    )


def test_invalid_json():
    result = handle_request(
        '{"name": "read_file"'
    )

    assert result == ToolResult(
        content="json格式错误",
        is_error=True,
    )


def test_unknown_tool():
    result = handle_request(
        '{"name": "attack", "arguments": {"path": "demo.txt"}}'
    )

    assert result == ToolResult(
        content="未知工具",
        is_error=True,
    )


def test_name_must_be_string():
    result = handle_request(
        '{"name": 123, "arguments": {"path": "demo.txt"}}'
    )
    assert result == ToolResult(
        content="name必须是字符串",
        is_error=True,
    )


def test_path_must_be_string():
    result = handle_request(
        '{"name": "read_file" , "arguments": {"path": 123}}'
    )
    assert result == ToolResult(
        content="path必须是字符串",
        is_error=True,
    )


def test_tool_request_fielsd():
    request = ToolRequest(
        name="read_file",
        path="demo.txt",
    )

    assert request.name == "read_file"
    assert request.path == "demo.txt"
    assert request.keyword is None
    assert request.old_text is None
    assert request.new_text is None


def test_parse_request_success():
    result = parse_request(
        '{"name": "read_file", "arguments": {"path": "demo.txt"}}'
    )

    assert result == ToolRequest(
        name="read_file",
        path="demo.txt",
    )


def test_handle_request_read_file_success(tmp_path):
    file_path = tmp_path / "hello.txt"
    file_path.write_text("你好 agent", encoding="utf-8")
    raw = json.dumps({
        "name": "read_file",
        "arguments": {"path": str(file_path)},
    })
    result = handle_request(raw)
    assert result == ToolResult(
        content="你好 agent"
    )


def test_handle_request_list_files_success(tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.py"
    folder = tmp_path / "nested"
    file_a.write_text("A", encoding="utf-8")
    file_b.write_text("B", encoding="utf-8")
    folder.mkdir()

    raw = json.dumps({
        "name": "list_files",
        "arguments": {"path": str(tmp_path)},
    })

    expected_content = "\n".join([
        f"[文件] {file_a}",
        f"[文件] {file_b}",
        f"[目录] {folder}/",
    ])

    result = handle_request(raw)

    assert result == ToolResult(
        content=expected_content,
        is_error=False,
    )


def test_search_file_success(tmp_path):
    file_path = tmp_path / "hello.txt"

    file_path.write_text(
        "hello agent\nhello Python\nagent tools",
        encoding="utf-8",
    )

    result = search_file(str(file_path), "agent")

    assert result == ToolResult(
        content="1: hello agent\n3: agent tools",
    )


def test_tool_request_search_fields():
    request = ToolRequest(
        name="search_file",
        path="demo.txt",
        keyword="agent",
    )

    assert request.name == "search_file"
    assert request.path == "demo.txt"
    assert request.keyword == "agent"


def test_parse_search_request_success():
    result = parse_request(
        '{"name":"search_file",'
        '"arguments":{"path":"demo.txt","keyword":"agent"}}'
    )

    assert result == ToolRequest(
        name="search_file",
        path="demo.txt",
        keyword="agent",
    )


def test_parse_search_request_missing_keyword():
    raw = json.dumps({
        "name": "search_file",
        "arguments": {
            "path": "demo.txt",
        },
    })

    result = parse_request(raw)

    expected = {"error": "缺少keyword"}
    assert result == expected


def test_parse_search_request_keyword_must_be_string():
    raw = json.dumps({
        "name": "search_file",
        "arguments": {
            "path": "demo.txt",
            "keyword": 123,
        },
    })

    result = parse_request(raw)

    expected = {"error": "keyword必须是字符串"}
    assert result == expected


def test_parse_search_request_rejects_empty_keyword():
    raw = json.dumps({
        "name": "search_file",
        "arguments": {
            "path": "demo.txt",
            "keyword": ""
        },
    })

    result = parse_request(raw)

    expected = {"error": "keyword不能为空"}
    assert result == expected


def test_handle_request_search_file_success(tmp_path):
    file_path = tmp_path / "example.txt"

    file_path.write_text(
        "hello agent\nhello Python\nagent tools",
        encoding="utf-8",
    )

    raw = json.dumps({
        "name": "search_file",
        "arguments": {
            "path": str(file_path),
            "keyword": "agent",
        },
    })

    result = handle_request(raw)

    expected = ToolResult(
        content="1: hello agent\n3: agent tools",
        is_error=False,
    )

    assert result == expected


def test_handle_request_search_file_no_matches(tmp_path):
    file_path = tmp_path / "example.txt"

    file_path.write_text(
        "hello agent\nhello Python\nagent tools",
        encoding="utf-8",
    )

    raw = json.dumps({
        "name": "search_file",
        "arguments": {
            "path": str(file_path),
            "keyword": "java",
        },
    })

    result = handle_request(raw)

    expected = ToolResult(
        content="",
        is_error=False,
    )

    assert result == expected


def test_search_file_rejects_invalid_utf8(tmp_path):
    file_path = tmp_path / "invalid.txt"
    file_path.write_bytes(b"\xff")

    result = search_file(str(file_path), "agent")

    assert result == ToolResult(
        content="文件不是有效UTF-8文本",
        is_error=True,
    )


def test_handle_request_search_file_missing_file(tmp_path):
    file_path = tmp_path / "missing.txt"

    raw = json.dumps({
        "name": "search_file",
        "arguments": {
            "path": str(file_path),
            "keyword": "agent",
        },
    })

    result = handle_request(raw)

    expected = ToolResult(
        content="文件不存在",
        is_error=True,
    )

    assert result == expected


def test_replace_text_once_success():
    text = "mode = debug\nport = 8000"

    result = replace_text_once(
        text,
        "mode = debug",
        "mode = release",
    )

    assert result == ToolResult(
        content="mode = release\nport = 8000",
        is_error=False,
    )


def test_replace_text_once_rejects_no_match():
    text = "mode = debug\nport = 8000"

    result = replace_text_once(
        text,
        "host = localhost",
        "host = 127.0.0.1",
    )

    assert result == ToolResult(
        content="未找到待替换文本",
        is_error=True,
    )


def test_replace_text_once_rejects_multiple_matches():
    text = "mode = debug\nmode = debug"

    result = replace_text_once(
        text,
        "mode = debug",
        "mode = release",
    )

    assert result == ToolResult(
        content="待替换文本出现多次",
        is_error=True,
    )


def test_edit_file_success(tmp_path):
    file_path = tmp_path / "config.txt"
    file_path.write_text(
        "mode = debug\nport = 8000",
        encoding="utf-8",
    )

    result = edit_file(
        str(file_path),
        "mode = debug",
        "mode = release",
    )

    assert result == ToolResult(
        content="mode = release\nport = 8000",
        is_error=False,
    )

    actual_content = file_path.read_text(encoding="utf-8")

    assert actual_content == "mode = release\nport = 8000"


def test_edit_file_rejects_multiple_matches_without_changing_file(
        tmp_path,
):
    file_path = tmp_path / "config.txt"
    original_content = "mode = debug\nmode = debug"

    file_path.write_text(
        original_content,
        encoding="utf-8",
    )

    result = edit_file(
        str(file_path),
        "mode = debug",
        "mode = release",
    )

    assert result == ToolResult(
        content="待替换文本出现多次",
        is_error=True,
    )

    actual_content = file_path.read_text(encoding="utf-8")

    assert actual_content == original_content


def test_parse_edit_request_success():
    raw = json.dumps({
        "name": "edit_file",
        "arguments": {
            "path": "config.txt",
            "old_text": "mode=debug",
            "new_text": "mode=release",
        },
    })
    result = parse_request(raw)

    assert result == ToolRequest(
        name="edit_file",
        path="config.txt",
        old_text="mode=debug",
        new_text="mode=release",
    )


def test_parse_edit_request_allows_empty_new_text():
    raw = json.dumps({
        "name": "edit_file",
        "arguments": {
            "path": "config.txt",
            "old_text": "mode=debug",
            "new_text": "",
        }
    })
    result = parse_request(raw)

    assert result == ToolRequest(
        name="edit_file",
        path="config.txt",
        old_text="mode=debug",
        new_text="",
    )


def test_handle_request_edit_file_success(tmp_path):
    file_path = tmp_path / "config.txt"
    file_path.write_text(
        "mode=debug\nport=8000",
        encoding="utf-8",
    )
    raw = json.dumps({
        "name": "edit_file",
        "arguments": {
            "path": str(file_path),
            "old_text": "mode=debug",
            "new_text": "mode=release",
        },
    })

    result = handle_request(raw)
    expected_content = "mode=release\nport=8000"
    assert result == ToolResult(
        content=expected_content,
        is_error=False,
    )

    actual_content = file_path.read_text(encoding="utf-8")
    assert expected_content == actual_content


def test_handle_request_edit_file_deletes_text(tmp_path):
    file_path = tmp_path / "config.txt"
    file_path.write_text(
        "mode=debug\nport=8000",
        encoding="utf-8",
    )
    raw = json.dumps({
        "name": "edit_file",
        "arguments": {
            "path": str(file_path),
            "old_text": "mode=debug\n",
            "new_text": "",
        },
    })

    result = handle_request(raw)
    expected_content = "port=8000"
    assert result == ToolResult(
        content=expected_content,
        is_error=False,
    )

    actual_content = file_path.read_text(encoding="utf-8")
    assert expected_content == actual_content


def test_handle_request_edit_file_rejects_multiple_matches_without_changing_file(
        tmp_path,
):
    file_path = tmp_path / "config.txt"

    original_content = "mode=debug\nmode=debug"

    file_path.write_text(
        original_content,
        encoding="utf-8",
    )

    raw = json.dumps({
        "name": "edit_file",
        "arguments": {
            "path": str(file_path),
            "old_text": "mode=debug",
            "new_text": "release",
        },
    })

    result = handle_request(raw)

    assert result == ToolResult(
        content="待替换文本出现多次",
        is_error=True,
    )

    actual_content = file_path.read_text(encoding="utf-8")
    assert original_content == actual_content


def test_parse_edit_request_rejects_invalid_text_arguments():
    cases = [
        (
            {"path": "config.txt", "new_text": "release"},
            {"error": "缺少old_text"},
        ),
        (
            {"path": "config.txx", "old_text": 123, "new_text": "mode=release"},
            {"error": "old_text必须是字符串"},
        ),
        (
            {"path": "config.txt", "old_text": "", "new_text": "mode=release"},
            {"error": "old_text不能为空"},
        ),
        (
            {"path": "config.txt", "old_text": "mode=debug"},
            {"error": "缺少new_text"},
        ),
        (
            {"path": "config.txt", "old_text": "mode=debug", "new_text": 123},
            {"error": "new_text必须是字符串"},
        ),
    ]

    for arguments, expected in cases:
        raw = json.dumps({
            "name": "edit_file",
            "arguments": arguments,
        })
        result = parse_request(raw)
        assert result == expected


def test_run_tests_in_trusted_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test_smoke.py").write_text(
        "def test_smoke():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )

    raw = json.dumps({
        "name": "run_tests",
        "arguments": {"path": "."},
    })

    result = handle_request(raw, workspace_root=str(workspace))

    assert result.is_error is False
    assert "1 passed" in result.content


def test_run_tests_uses_allowlisted_unittest_profile(
        tmp_path,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "test_unittest_smoke.py").write_text(
        "import unittest\n\n"
        "class SmokeTests(unittest.TestCase):\n"
        "    def test_addition(self):\n"
        "        self.assertEqual(1 + 1, 2)\n",
        encoding="utf-8",
    )

    result = run_tests(
        ".",
        str(workspace),
        verification_profile="unittest",
    )

    assert result.is_error is False
    assert "Ran 1 test" in result.content
    assert "OK" in result.content

    rejected = run_tests(
        ".",
        str(workspace),
        verification_profile="custom-command",
    )

    assert rejected == ToolResult(
        content="不支持的验证方案：custom-command",
        is_error=True,
    )


def test_run_tests_rejects_outside_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()

    raw = json.dumps({
        "name": "run_tests",
        "arguments": {"path": str(outside)},
    })

    result = handle_request(raw, workspace_root=str(workspace))

    assert result == ToolResult(
        content="工作目录超出允许范围",
        is_error=True,
    )


def test_file_tools_stay_in_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "inside.txt").write_text("inside", encoding="utf-8")

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    read_inside = json.dumps({
        "name": "read_file",
        "arguments": {"path": "inside.txt"},
    })
    assert handle_request(
        read_inside,
        workspace_root=str(workspace),
    ) == ToolResult(content="inside", is_error=False)

    read_outside = json.dumps({
        "name": "read_file",
        "arguments": {"path": str(outside)},
    })
    assert handle_request(
        read_outside,
        workspace_root=str(workspace),
    ) == ToolResult(content="路径超出工作区", is_error=True)

    list_outside = json.dumps({
        "name": "list_files",
        "arguments": {"path": str(tmp_path)},
    })
    assert handle_request(
        list_outside,
        workspace_root=str(workspace),
    ) == ToolResult(content="路径超出工作区", is_error=True)

    edit_outside = json.dumps({
        "name": "edit_file",
        "arguments": {
            "path": str(outside),
            "old_text": "secret",
            "new_text": "changed",
        },
    })
    assert handle_request(
        edit_outside,
        workspace_root=str(workspace),
    ) == ToolResult(content="路径超出工作区", is_error=True)
    assert outside.read_text(encoding="utf-8") == "secret"


def test_handle_request_read_file_range(tmp_path):
    file_path = tmp_path / "large.txt"
    file_path.write_text(
        "第一行\n第二行\n第三行\n第四行\n",
        encoding="utf-8",
    )

    raw = json.dumps({
        "name": "read_file",
        "arguments": {
            "path": str(file_path),
            "start_line": 2,
            "max_lines": 2,
        },
    })

    result = handle_request(raw)

    assert result == ToolResult(
        content=(
            "[读取第 2-3 行，共 4 行]\n"
            "第二行\n第三行\n"
        ),
        is_error=False,
    )


def test_handle_request_create_file_and_reject_overwrite(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    raw = json.dumps({
        "name": "create_file",
        "arguments": {
            "path": "new_module.py",
            "content": "VALUE = 92741\n",
        },
    })

    first_result = handle_request(
        raw,
        workspace_root=str(workspace),
    )

    created_file = workspace / "new_module.py"

    assert first_result == ToolResult(
        content="文件创建成功",
        is_error=False,
    )
    assert created_file.read_text(encoding="utf-8") == "VALUE = 92741\n"

    second_result = handle_request(
        raw,
        workspace_root=str(workspace),
    )

    assert second_result == ToolResult(
        content="文件已存在，拒绝覆盖",
        is_error=True,
    )
    assert created_file.read_text(encoding="utf-8") == "VALUE = 92741\n"


def test_handle_request_create_directory_and_reject_existing(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    raw = json.dumps({
        "name": "create_directory",
        "arguments": {
            "path": "package",
        },
    })

    first_result = handle_request(
        raw,
        workspace_root=str(workspace),
    )

    directory = workspace / "package"

    assert first_result == ToolResult(
        content="目录创建成功",
        is_error=False,
    )
    assert directory.is_dir()

    second_result = handle_request(
        raw,
        workspace_root=str(workspace),
    )

    assert second_result == ToolResult(
        content="路径已存在，拒绝重复创建",
        is_error=True,
    )
    assert directory.is_dir()


def test_handle_request_search_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    source = workspace / "src"
    nested = source / "nested"
    ignored = workspace / ".git"

    nested.mkdir(parents=True)
    ignored.mkdir()

    (source / "a.py").write_text(
        "first line\nTARGET_WORKSPACE_SEARCH\n",
        encoding="utf-8",
    )
    (nested / "b.py").write_text(
        "value = 'TARGET_WORKSPACE_SEARCH'\n",
        encoding="utf-8",
    )
    (ignored / "hidden.txt").write_text(
        "TARGET_WORKSPACE_SEARCH\n",
        encoding="utf-8",
    )
    (source / "binary.bin").write_bytes(b"\xff")

    raw = json.dumps({
        "name": "search_workspace",
        "arguments": {
            "path": ".",
            "keyword": "TARGET_WORKSPACE_SEARCH",
        },
    })

    result = handle_request(
        raw,
        workspace_root=str(workspace),
    )

    assert result == ToolResult(
        content=(
            "src/a.py:2: TARGET_WORKSPACE_SEARCH\n"
            "src/nested/b.py:1: value = 'TARGET_WORKSPACE_SEARCH'"
        ),
        is_error=False,
    )


def test_handle_request_inspects_git_changes(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    subprocess.run(
        ["git", "init", "-q"],
        cwd=workspace,
        check=True,
    )

    tracked = workspace / "tracked.txt"
    tracked.write_text("old\n", encoding="utf-8")

    subprocess.run(
        ["git", "add", "tracked.txt"],
        cwd=workspace,
        check=True,
    )

    tracked.write_text("new\n", encoding="utf-8")
    (workspace / "new.txt").write_text(
        "untracked\n",
        encoding="utf-8",
    )

    raw = json.dumps({
        "name": "inspect_git_changes",
        "arguments": {
            "path": ".",
        },
    })

    result = handle_request(
        raw,
        workspace_root=str(workspace),
    )

    assert result.is_error is False
    assert "AM tracked.txt" in result.content
    assert "?? new.txt" in result.content
    assert "未暂存差异" in result.content
    assert "-old" in result.content
    assert "+new" in result.content
    assert "已暂存差异" in result.content
    assert "+old" in result.content


def test_handle_request_runs_single_test_file(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "test_pass.py").write_text(
        "def test_pass():\n"
        "    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    (workspace / "test_fail.py").write_text(
        "def test_fail():\n"
        "    assert 1 + 1 == 3\n",
        encoding="utf-8",
    )

    raw = json.dumps({
        "name": "run_test_file",
        "arguments": {
            "path": "test_pass.py",
        },
    })

    result = handle_request(
        raw,
        workspace_root=str(workspace),
    )

    assert result.is_error is False
    assert "1 passed" in result.content
    assert "failed" not in result.content


def test_handle_request_renames_file_and_rejects_overwrite(tmp_path):
    source = tmp_path / "old_name.py"
    source.write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    rename_request = json.dumps({
        "name": "rename_file",
        "arguments": {
            "path": "old_name.py",
            "destination": "new_name.py",
        },
    })

    result = handle_request(
        rename_request,
        workspace_root=str(tmp_path),
    )

    assert result == ToolResult(
        content="文件重命名成功",
        is_error=False,
    )
    assert not source.exists()
    assert (tmp_path / "new_name.py").read_text(
        encoding="utf-8",
    ) == "VALUE = 1\n"

    blocked_source = tmp_path / "another.py"
    blocked_source.write_text(
        "VALUE = 2\n",
        encoding="utf-8",
    )
    existing_target = tmp_path / "existing.py"
    existing_target.write_text(
        "KEEP\n",
        encoding="utf-8",
    )

    overwrite_request = json.dumps({
        "name": "rename_file",
        "arguments": {
            "path": "another.py",
            "destination": "existing.py",
        },
    })

    blocked_result = handle_request(
        overwrite_request,
        workspace_root=str(tmp_path),
    )

    assert blocked_result == ToolResult(
        content="目标路径已存在，拒绝覆盖",
        is_error=True,
    )
    assert blocked_source.exists()
    assert existing_target.read_text(
        encoding="utf-8",
    ) == "KEEP\n"


def test_handle_request_deletes_regular_file_and_rejects_unsafe_paths(
        tmp_path,
):
    target = tmp_path / "obsolete.py"
    target.write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    link = tmp_path / "shortcut.py"
    link.symlink_to(target)

    link_request = json.dumps({
        "name": "delete_file",
        "arguments": {
            "path": "shortcut.py",
        },
    })

    link_result = handle_request(
        link_request,
        workspace_root=str(tmp_path),
    )

    assert link_result == ToolResult(
        content="不能删除符号链接",
        is_error=True,
    )
    assert link.is_symlink()
    assert target.exists()

    directory = tmp_path / "package"
    directory.mkdir()

    directory_request = json.dumps({
        "name": "delete_file",
        "arguments": {
            "path": "package",
        },
    })

    directory_result = handle_request(
        directory_request,
        workspace_root=str(tmp_path),
    )

    assert directory_result == ToolResult(
        content="路径不是普通文件",
        is_error=True,
    )
    assert directory.is_dir()

    delete_request = json.dumps({
        "name": "delete_file",
        "arguments": {
            "path": "obsolete.py",
        },
    })

    delete_result = handle_request(
        delete_request,
        workspace_root=str(tmp_path),
    )

    assert delete_result == ToolResult(
        content="文件删除成功",
        is_error=False,
    )
    assert not target.exists()
