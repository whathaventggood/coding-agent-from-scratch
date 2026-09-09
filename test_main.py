from main import handle_request


def test_missing_arguments():
    result = handle_request('{"name": "read_file"}')

    assert result == {
        "error": "缺少arguments"
    }


def test_arguments_must_be_object():
    result = handle_request(
        '{"name": "read_file", "arguments": []}'
    )

    assert result == {
        "error": "arguments必须是JSON对象"
    }


def test_request_must_be_object():
    result = handle_request("[]")

    assert result == {
        "error": "请求必须是JSON对象"
    }