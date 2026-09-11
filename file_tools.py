from pathlib import Path
from models import ToolResult

#读工具
def read_file(path:str)->ToolResult:
    if not path:
        return ToolResult(
            content="路径不能为空",
            is_error=True,
        )
    file_path=Path(path)
    if file_path.is_dir():
        return ToolResult(
            content="路径是目录",
            is_error=True,
        )

    try:
        content=file_path.read_text(encoding="utf-8")
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

    return ToolResult(
        content=content,
    )


#列出目录下文件名
def list_files(path:str)->ToolResult:
    if not path:
        return ToolResult(
            content="路径不能为空",
            is_error=True,
        )
    folders = Path(path)
    if not folders.is_dir():
        return  ToolResult(
            content="不是目录",
            is_error=True,
        )
    items=folders.iterdir()
    files=[]

    for item in items:
        if item.is_file():
           files.append(str(item))

    files.sort()

    return ToolResult(
        content='\n'.join(files),
    )


#关键词搜索
def search_file(path:str,keyword:str)->ToolResult:
    read_result=read_file(path)

    if read_result.is_error:
        return read_result

    matches=[]

    for line_number,line in enumerate(read_result.content.splitlines(),start=1):
        if keyword in line:
            matches.append(f"{line_number}: {line}")

    return ToolResult(
        content='\n'.join(matches),
    )
