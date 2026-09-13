from main import handle_request, parse_request
from models import ToolResult, ToolRequest
from file_tools import (
    read_file, list_files, search_file, replace_text_once, edit_file
)
import json


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

    expected_content = '\n'.join(
        sorted([str(file_a), str(file_b)])
    )

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

    expected_content = '\n'.join(
        sorted([str(file_a), str(file_b)])
    )

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
