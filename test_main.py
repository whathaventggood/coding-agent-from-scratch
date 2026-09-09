from main import handle_request


assert handle_request('{"name": "read_file"}') == {
    "error": "缺少arguments"
}

assert handle_request(
    '{"name": "read_file", "arguments": []}'
) == {
    "error": "arguments必须是JSON对象"
}

assert handle_request("[]") == {
    "error": "请求必须是JSON对象"
}

print("全部测试通过")