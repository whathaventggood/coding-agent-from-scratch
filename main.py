import json
from models import ToolRequest, ToolResult
from file_tools import read_file, list_files, search_file, edit_file


# 选择工具执行
def dispatch(
        tool_name: str,
        path: str,
        keyword: str | None = None,
        old_text: str | None = None,
        new_text: str | None = None,
) -> ToolResult:
    if tool_name == "read_file":
        return read_file(path)

    elif tool_name == "list_files":
        return list_files(path)

    elif tool_name == "search_file":
        if keyword is None:
            return ToolResult(
                content="缺少keyword",
                is_error=True,
            )
        return search_file(path, keyword)

    elif tool_name == "edit_file":
        if old_text is None:
            return ToolResult(
                content="缺少old_text",
                is_error=True,
            )
        if new_text is None:
            return ToolResult(
                content="缺少new_text",
                is_error=True,
            )
        return edit_file(path, old_text, new_text)
    else:
        return ToolResult(
            content="未知工具",
            is_error=True,
        )


# 解析json内容
def parse_request(raw: str) -> dict[str, str] | ToolRequest:
    try:
        request = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "json格式错误"}

    if not isinstance(request, dict):
        return {"error": "请求必须是JSON对象"}

    name = request.get("name")

    if name is None:
        return {"error": "缺少name"}

    if not isinstance(name, str):
        return {"error": "name必须是字符串"}

    arguments = request.get("arguments")

    if arguments is None:
        return {"error": "缺少arguments"}

    if not isinstance(arguments, dict):
        return {"error": "arguments必须是JSON对象"}

    path = arguments.get("path")
    if path is None:
        return {"error": "缺少path"}

    if not isinstance(path, str):
        return {"error": "path必须是字符串"}

    keyword = None
    if name == "search_file":
        keyword = arguments.get("keyword")

        if keyword is None:
            return {"error": "缺少keyword"}

        if not isinstance(keyword, str):
            return {"error": "keyword必须是字符串"}

        if keyword == "":
            return {"error": "keyword不能为空"}

    old_text = None
    new_text = None

    if name == "edit_file":
        old_text = arguments.get("old_text")
        new_text = arguments.get("new_text")

        if old_text is None:
            return {"error": "缺少old_text"}

        if not isinstance(old_text, str):
            return {"error": "old_text必须是字符串"}

        if old_text == "":
            return {"error": "old_text不能为空"}

        if new_text is None:
            return {"error": "缺少new_text"}

        if not isinstance(new_text, str):
            return {"error": "new_text必须是字符串"}

    return ToolRequest(
        name=name,
        path=path,
        keyword=keyword,
        old_text=old_text,
        new_text=new_text,
    )


# 处理请求
def handle_request(raw: str) -> ToolResult:
    result = parse_request(raw)
    if isinstance(result, dict):
        return ToolResult(
            content=result["error"],
            is_error=True,
        )
    return dispatch(
        result.name,
        result.path,
        result.keyword,
        result.old_text,
        result.new_text,
    )
