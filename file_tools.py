from pathlib import Path
from models import ToolResult
import os
import json


MAX_LIST_PAGE_ENTRIES = 50
MAX_LIST_PAGE_CHARS = 3000


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
def list_files(
        path: str,
        start_after: str | None = None,
) -> ToolResult:
    if not path:
        return ToolResult(
            content="路径不能为空",
            is_error=True,
        )

    if start_after is not None:
        if not isinstance(start_after, str):
            return ToolResult("start_after必须是字符串", is_error=True)
        if not start_after:
            return ToolResult("start_after不能为空", is_error=True)

    folder = Path(path)

    if not folder.is_dir():
        return ToolResult(
            content="不是目录",
            is_error=True,
        )

    try:
        items = sorted(
            folder.iterdir(),
            key=lambda item: item.name,
        )
    except OSError as error:
        return ToolResult(
            content=f"无法列出目录：{error}",
            is_error=True,
        )

    entries = []
    page_chars = 0
    last_name = None
    has_more = False

    for item in items:
        if start_after is not None and item.name <= start_after:
            continue

        if item.is_dir():
            line = f"[目录] {item}/"
        elif item.is_file():
            line = f"[文件] {item}"
        else:
            continue

        if entries and (
                len(entries) >= MAX_LIST_PAGE_ENTRIES
                or page_chars + len(line) + 1 > MAX_LIST_PAGE_CHARS
        ):
            has_more = True
            break

        entries.append(line)
        page_chars += len(line) + 1
        last_name = item.name

    if has_more:
        cursor = json.dumps(last_name, ensure_ascii=False)
        entries.append(
            "[还有更多条目：再次调用 list_files，"
            f"path 不变，start_after={cursor}]"
        )

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


IGNORED_SEARCH_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
}

MAX_WORKSPACE_SEARCH_RESULTS = 100
MAX_WORKSPACE_SEARCH_CHARS = 3000
MAX_SEARCH_MATCH_LINE_CHARS = 300


def search_workspace(
        path: str,
        keyword: str,
        offset: int = 0,
) -> ToolResult:
    if not path:
        return ToolResult(
            content="路径不能为空",
            is_error=True,
        )

    if not keyword:
        return ToolResult(
            content="关键词不能为空",
            is_error=True,
        )

    if type(offset) is not int or offset < 0:
        return ToolResult(
            content="offset必须是非负整数",
            is_error=True,
        )

    root = Path(path)

    if not root.is_dir():
        return ToolResult(
            content="不是目录",
            is_error=True,
        )

    matches = []
    page_chars = 0
    seen_matches = 0

    # 递归遍历 root 目录树，每轮获取当前目录、子目录列表和文件列表
    for current_root, directory_names, file_names in os.walk(
            root,
            # 不递归进入符号链接指向的目录
            followlinks=False,
    ):
        current_directory = Path(current_root)

        directory_names[:] = sorted(
            name
            for name in directory_names
            if (
                    name not in IGNORED_SEARCH_DIRECTORIES
                    and not (current_directory / name).is_symlink()
            )
        )

        for file_name in sorted(file_names):
            file_path = current_directory / file_name

            if file_path.is_symlink():
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            relative_path = file_path.relative_to(root)

            for line_number, line in enumerate(
                    content.splitlines(),
                    start=1,
            ):
                if keyword not in line:
                    continue

                if seen_matches < offset:
                    seen_matches += 1
                    continue

                if len(line) > MAX_SEARCH_MATCH_LINE_CHARS:
                    match_index = line.find(keyword)
                    excerpt_start = max(0, match_index - 80)
                    excerpt_end = (
                        excerpt_start + MAX_SEARCH_MATCH_LINE_CHARS
                    )
                    line = (
                        ("…" if excerpt_start else "")
                        + line[excerpt_start:excerpt_end]
                        + ("…" if excerpt_end < len(line) else "")
                    )

                entry = f"{relative_path}:{line_number}: {line}"

                if matches and (
                        len(matches) >= MAX_WORKSPACE_SEARCH_RESULTS
                        or page_chars + len(entry) + 1
                        > MAX_WORKSPACE_SEARCH_CHARS
                ):
                    matches.append(
                        "[还有更多搜索结果：保持 path 和 keyword 不变，"
                        f"下次传 offset={offset + len(matches)}]"
                    )
                    return ToolResult(
                        content="\n".join(matches),
                    )

                matches.append(entry)
                page_chars += len(entry) + 1
                seen_matches += 1

    return ToolResult(
        content="\n".join(matches),
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

#文件移动 + 改名
def rename_file(
        path: str,
        destination: str,
) -> ToolResult:
    if not path:
        return ToolResult(
            content="源路径不能为空",
            is_error=True,
        )

    if not destination:
        return ToolResult(
            content="目标路径不能为空",
            is_error=True,
        )

    source = Path(path)
    target = Path(destination)

    if source.is_symlink():
        return ToolResult(
            content="源路径不能是符号链接",
            is_error=True,
        )

    if not source.is_file():
        return ToolResult(
            content="源路径不是已存在的文件",
            is_error=True,
        )

    if target.exists() or target.is_symlink():
        return ToolResult(
            content="目标路径已存在，拒绝覆盖",
            is_error=True,
        )

    if not target.parent.is_dir():
        return ToolResult(
            content="目标父目录不存在",
            is_error=True,
        )

    try:
        source.rename(target)
    except OSError as error:
        return ToolResult(
            content=f"重命名文件失败：{error}",
            is_error=True,
        )

    return ToolResult(
        content="文件重命名成功",
        is_error=False,
    )


def delete_file(path: str) -> ToolResult:
    if not path:
        return ToolResult(
            content="路径不能为空",
            is_error=True,
        )

    file_path = Path(path)

    if file_path.is_symlink():
        return ToolResult(
            content="不能删除符号链接",
            is_error=True,
        )

    if not file_path.exists():
        return ToolResult(
            content="文件不存在",
            is_error=True,
        )

    if not file_path.is_file():
        return ToolResult(
            content="路径不是普通文件",
            is_error=True,
        )

    try:
        file_path.unlink()
    except OSError as error:
        return ToolResult(
            content=f"删除文件失败：{error}",
            is_error=True,
        )

    return ToolResult(
        content="文件删除成功",
        is_error=False,
    )
