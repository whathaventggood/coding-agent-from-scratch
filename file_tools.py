from pathlib import Path
from models import ToolResult


# 读工具
def read_file(
        path: str,
        start_line: int | None = None,
        max_lines: int | None = None,
) -> ToolResult:
    if not path:
        return ToolResult(
            content="路径不能为空",
            is_error=True,
        )

    file_path = Path(path)

    if file_path.is_dir():
        return ToolResult(
            content="路径是目录",
            is_error=True,
        )

    try:
        content = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ToolResult(
            content="文件不存在",
            is_error=True,
        )
    except UnicodeDecodeError:
        return ToolResult(
            content="文件不是有效UTF-8文本",
            is_error=True,
        )

    # 没有提供分段参数时，保持原来的整文件读取行为。
    if start_line is None and max_lines is None:
        return ToolResult(content=content)

    actual_start = start_line if start_line is not None else 1
    lines = content.splitlines(keepends=True)  # 把完整文本拆成一个“每行一个元素(字符串)”的列表，并保留每行末尾的换行符。

    if actual_start > len(lines):
        return ToolResult(
            content=f"起始行超出文件范围，文件共 {len(lines)} 行",
            is_error=True,
        )

    if max_lines is None:
        actual_end = len(lines)
    else:
        actual_end = min(
            actual_start + max_lines - 1,
            len(lines),
        )

    selected_content = "".join(lines[actual_start - 1:actual_end])

    return ToolResult(
        content=(
            f"[读取第 {actual_start}-{actual_end} 行，"
            f"共 {len(lines)} 行]\n"
            f"{selected_content}"
        ),
    )


# 列出目录下文件名
def list_files(path: str) -> ToolResult:
    if not path:
        return ToolResult(
            content="路径不能为空",
            is_error=True,
        )

    folder = Path(path)

    if not folder.is_dir():
        return ToolResult(
            content="不是目录",
            is_error=True,
        )

    entries = []
    items = sorted(
        folder.iterdir(),
        key=lambda item: item.name,
    )

    for item in items:
        if item.is_dir():
            entries.append(f"[目录] {item}/")
        elif item.is_file():
            entries.append(f"[文件] {item}")

    return ToolResult(
        content="\n".join(entries),
    )


# 关键词搜索
def search_file(path: str, keyword: str) -> ToolResult:
    read_result = read_file(path)

    if read_result.is_error:
        return read_result

    matches = []

    for line_number, line in enumerate(read_result.content.splitlines(), start=1):
        if keyword in line:
            matches.append(f"{line_number}: {line}")

    return ToolResult(
        content='\n'.join(matches),
    )


def replace_text_once(
        text: str,
        old_text: str,
        new_text: str,
) -> ToolResult:
    match_count = text.count(old_text)

    if match_count == 0:
        return ToolResult(
            content="未找到待替换文本",
            is_error=True,
        )

    if match_count > 1:
        return ToolResult(
            content="待替换文本出现多次",
            is_error=True,
        )

    updated_text = text.replace(
        old_text,
        new_text,
        1,
    )

    return ToolResult(
        content=updated_text,
        is_error=False,
    )


def edit_file(
        path: str,
        old_text: str,
        new_text: str,
) -> ToolResult:
    read_result = read_file(path)

    if read_result.is_error:
        return read_result

    replace_result = replace_text_once(
        read_result.content,
        old_text,
        new_text,
    )

    if replace_result.is_error:
        return replace_result

    file_path = Path(path)
    file_path.write_text(
        replace_result.content,
        encoding="utf-8",
    )

    return replace_result


def create_file(path: str, content: str) -> ToolResult:
    if not path:
        return ToolResult(
            content="路径不能为空",
            is_error=True,
        )

    file_path = Path(path)

    if not file_path.parent.is_dir():
        return ToolResult(
            content="父目录不存在",
            is_error=True,
        )

    try:
        # 使用 x 模式：只有文件不存在时才能创建，避免覆盖已有内容。
        with file_path.open("x", encoding="utf-8") as file:
            file.write(content)
    except FileExistsError:
        return ToolResult(
            content="文件已存在，拒绝覆盖",
            is_error=True,
        )
    except OSError as error:
        return ToolResult(
            content=f"创建文件失败：{error}",
            is_error=True,
        )

    return ToolResult(
        content="文件创建成功",
        is_error=False,
    )


def create_directory(path: str) -> ToolResult:
    if not path:
        return ToolResult(
            content="路径不能为空",
            is_error=True,
        )

    directory = Path(path)

    if not directory.parent.is_dir():
        return ToolResult(
            content="父目录不存在",
            is_error=True,
        )

    try:
        # 不使用 parents=True，不自动创建模型没有明确请求的上级目录。
        directory.mkdir()
    except FileExistsError:
        return ToolResult(
            content="路径已存在，拒绝重复创建",
            is_error=True,
        )
    except OSError as error:
        return ToolResult(
            content=f"创建目录失败：{error}",
            is_error=True,
        )

    return ToolResult(
        content="目录创建成功",
        is_error=False,
    )
