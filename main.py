import json
from models import ToolRequest, ToolResult
from pathlib import Path
from command_tool import (
    run_tests,
    run_test_file,
    inspect_git_changes,
)
from file_tools import (
    read_file,
    list_files,
    search_file,
    edit_file,
    create_file,
    create_directory,
    search_workspace,
    list_python_symbols,
    rename_file,
    delete_file,
)


def resolve_workspace_path(path: str, workspace_root: str) -> str | None:
    root = Path(workspace_root).resolve()
    target = Path(path)

    if not target.is_absolute():
        target = root / path

    target = target.resolve()

    if not target.is_relative_to(root):
        return None

    return str(target)


# 选择工具执行
def dispatch(
        tool_name: str,
        path: str,
        keyword: str | None = None,
        old_text: str | None = None,
        new_text: str | None = None,
        workspace_root: str | None = None,
        start_line: int | None = None,
        max_lines: int | None = None,
        start_after: str | None = None,
        offset: int = 0,
        content: str | None = None,
        destination: str | None = None,
        verification_profile: str = "pytest",
) -> ToolResult:
    file_tools = {
        "read_file",
        "list_files",
        "search_file",
        "edit_file",
        "create_file",
        "create_directory",
        "search_workspace",
        "list_python_symbols",
        "rename_file",
        "delete_file",
    }

    if workspace_root is not None and tool_name == "rename_file":
        root = Path(workspace_root).resolve()
        source_input = Path(path)

        if not source_input.is_absolute():
            source_input = root / source_input

        if source_input.is_symlink():
            return ToolResult(
                content="源路径不能是符号链接",
                is_error=True,
            )

        if destination is not None:
            destination_input = Path(destination)

            if not destination_input.is_absolute():
                destination_input = root / destination_input

            if destination_input.is_symlink():
                return ToolResult(
                    content="目标路径已存在，拒绝覆盖",
                    is_error=True,
                )

    if workspace_root is not None and tool_name == "delete_file":
        root = Path(workspace_root).resolve()
        delete_input = Path(path)

        if not delete_input.is_absolute():
            delete_input = root / delete_input

        if delete_input.is_symlink():
            return ToolResult(
                content="不能删除符号链接",
                is_error=True,
            )

    if workspace_root is not None and tool_name in file_tools and path:
        resolve_path = resolve_workspace_path(path, workspace_root)

        if resolve_path is None:
            return ToolResult(
                content="路径超出工作区",
                is_error=True,
            )

        path = resolve_path

    if (
            workspace_root is not None
            and tool_name == "rename_file"
            and destination is not None
    ):
        resolved_destination = resolve_workspace_path(
            destination,
            workspace_root,
        )

        if resolved_destination is None:
            return ToolResult(
                content="目标路径超出工作区",
                is_error=True,
            )

        destination = resolved_destination

    if tool_name == "read_file":
        return read_file(
            path,
            start_line=start_line,
            max_lines=max_lines,
        )

    elif tool_name == "list_files":
        return list_files(path, start_after=start_after)

    elif tool_name == "search_file":
        if keyword is None:
            return ToolResult(
                content="缺少keyword",
                is_error=True,
            )
        return search_file(path, keyword)

    elif tool_name == "search_workspace":
        if keyword is None:
            return ToolResult(
                content="缺少keyword",
                is_error=True,
            )

        return search_workspace(path, keyword, offset=offset)

    elif tool_name == "list_python_symbols":
        return list_python_symbols(path, keyword=keyword, offset=offset)

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

    elif tool_name == "create_directory":
        return create_directory(path)

    elif tool_name == "create_file":
        if content is None:
            return ToolResult(
                content="缺少content",
                is_error=True,
            )

        return create_file(path, content)

    elif tool_name == "run_tests":
        if workspace_root is None:
            return ToolResult(
                content="缺少受信工作区",
                is_error=True,
            )
        return run_tests(
            path,
            workspace_root,
            verification_profile=verification_profile,
        )

    elif tool_name == "run_test_file":
        if workspace_root is None:
            return ToolResult(
                content="缺少受信工作区",
                is_error=True,
            )

        return run_test_file(
            path,
            workspace_root,
        )

    elif tool_name == "inspect_git_changes":
        if workspace_root is None:
            return ToolResult(
                content="缺少受信工作区",
                is_error=True,
            )

        return inspect_git_changes(
            path,
            workspace_root,
        )

    elif tool_name == "rename_file":
        if destination is None:
            return ToolResult(
                content="缺少destination",
                is_error=True,
            )

        return rename_file(path, destination)

    elif tool_name == "delete_file":
        return delete_file(path)

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

    content = None

    if name == "create_file":
        content = arguments.get("content")

        if content is None:
            return {"error": "缺少content"}

        if not isinstance(content, str):
            return {"error": "content必须是字符串"}

    path = arguments.get("path")
    if path is None:
        return {"error": "缺少path"}

    if not isinstance(path, str):
        return {"error": "path必须是字符串"}

    destination = None

    if name == "rename_file":
        destination = arguments.get("destination")

        if destination is None:
            return {"error": "缺少destination"}

        if not isinstance(destination, str):
            return {"error": "destination必须是字符串"}

        if destination == "":
            return {"error": "destination不能为空"}

    start_line = None
    max_lines = None
    start_after = None
    offset = 0

    if name == "list_files":
        start_after = arguments.get("start_after")

        if start_after is not None:
            if not isinstance(start_after, str):
                return {"error": "start_after必须是字符串"}
            if not start_after:
                return {"error": "start_after不能为空"}

    if name in {"search_workspace", "list_python_symbols"}:
        offset = arguments.get("offset", 0)

        if type(offset) is not int or offset < 0:
            return {"error": "offset必须是非负整数"}

    if name == "read_file":
        start_line = arguments.get("start_line")
        max_lines = arguments.get("max_lines")

        if start_line is not None:
            if type(start_line) is not int:
                return {"error": "start_line必须是整数"}

            if start_line < 1:
                return {"error": "start_line必须大于0"}

        if max_lines is not None:
            if type(max_lines) is not int:
                return {"error": "max_lines必须是整数"}

            if max_lines < 1:
                return {"error": "max_lines必须大于0"}

            if max_lines > 200:
                return {"error": "max_lines不能超过200"}

    keyword = None
    if name in {"search_file", "search_workspace"}:
        keyword = arguments.get("keyword")

        if keyword is None:
            return {"error": "缺少keyword"}

        if not isinstance(keyword, str):
            return {"error": "keyword必须是字符串"}

        if keyword == "":
            return {"error": "keyword不能为空"}

    if name == "list_python_symbols":
        keyword = arguments.get("keyword")
        if keyword is not None and (
                not isinstance(keyword, str) or not keyword
        ):
            return {"error": "keyword必须是非空字符串"}

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
        start_line=start_line,
        max_lines=max_lines,
        start_after=start_after,
        offset=offset,
        content=content,
        destination=destination,
    )


# 处理请求
def handle_request(
        raw: str,
        workspace_root: str | None = None,
        verification_profile: str = "pytest",
) -> ToolResult:
    result = parse_request(raw)

    if isinstance(result, dict):
        return ToolResult(
            content=result["error"],
            is_error=True,
        )

    return dispatch(
        tool_name=result.name,
        path=result.path,
        keyword=result.keyword,
        old_text=result.old_text,
        new_text=result.new_text,
        workspace_root=workspace_root,
        start_line=result.start_line,
        max_lines=result.max_lines,
        start_after=result.start_after,
        offset=result.offset,
        content=result.content,
        destination=result.destination,
        verification_profile=verification_profile,
    )
