from main import handle_request,parse_request
from models import ToolResult,ToolRequest
from file_tools import read_file,list_files


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
    file_path=tmp_path/"hello.txt"
    file_path.write_text("你好 agent",encoding="utf-8")
    result = read_file(str(file_path))
    assert result==ToolResult(
        content = "你好 agent"
    )

def test_read_file_missing():
    result=read_file("not_exist.txt")
    assert result== ToolResult(
        content="文件不存在",
        is_error=True,
    )

def test_read_file_rejects_directory(tmp_path):
    result=read_file(str(tmp_path))
    assert result == ToolResult(
        content="路径是目录",
        is_error=True,
    )

def test_read_file_rejects_empty_path():
    result=read_file("")
    assert result==ToolResult(
        content="路径不能为空",
        is_error=True,
    )


def test_list_files_success(tmp_path):
    file_a=tmp_path/"a.txt"
    file_b=tmp_path/"b.py"
    folder=tmp_path/"nested"
    file_a.write_text("A",encoding="utf-8")
    file_b.write_text("B", encoding="utf-8")
    folder.mkdir()

    result=list_files(str(tmp_path))

    expected_content='\n'.join(
        sorted([str(file_a),str(file_b)])
    )

    assert result==ToolResult(
        content=expected_content
    )

def test_list_files_rejects_empty_path():
    result=list_files("")
    assert result==ToolResult(
        content="路径不能为空",
        is_error=True,
    )

def test_list_files_rejects_file_path(tmp_path):
    file_path=tmp_path/"hello.txt"
    file_path.write_text("hello",encoding="utf-8")
    result=list_files(str(file_path))
    assert result==ToolResult(
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
    result=handle_request(
        '{"name": 123, "arguments": {"path": "demo.txt"}}'
    )
    assert result==ToolResult(
        content="name必须是字符串",
        is_error=True,
    )

def test_path_must_be_string():
    result=handle_request(
        '{"name": "read_file" , "arguments": {"path": 123}}'
    )
    assert result==ToolResult(
        content="path必须是字符串",
        is_error=True,
    )

def test_tool_request_fielsd():
    request=ToolRequest(
        name="read_file",
        path="demo.txt",
    )

    assert request.name == "read_file"
    assert request.path == "demo.txt"

def test_parse_request_success():
    result = parse_request(
        '{"name": "read_file", "arguments": {"path": "demo.txt"}}'
    )

    assert result == ToolRequest(
        name="read_file",
        path="demo.txt",
    )