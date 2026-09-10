import json
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ToolResult:
    content: str
    is_error: bool=False

@dataclass
class ToolRequest:
    name:str
    path:str


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



#选择工具执行
def dispatch(tool_name:str,path:str)->ToolResult:
    if tool_name=="read_file":
        return read_file(path)
    elif tool_name=="list_files":
        return list_files(path)
    else:
        return ToolResult(
            content="未知工具",
            is_error=True,
        )



#解析json内容
def parse_request(raw:str)->dict[str,str]|ToolRequest:
    try:
        request=json.loads(raw)
    except json.JSONDecodeError:
        return {"error":"json格式错误"}

    if not isinstance(request,dict):
        return {"error":"请求必须是JSON对象"}

    name=request.get("name")

    if name is None:
        return {"error":"缺少name"}

    if not isinstance(name,str):
        return {"error":"name必须是字符串"}

    arguments = request.get("arguments")

    if arguments is None:
        return {"error": "缺少arguments"}

    if not isinstance(arguments, dict):
        return {"error": "arguments必须是JSON对象"}


    path=arguments.get("path")
    if path is None:
        return {"error":"缺少path"}

    if not isinstance(path,str):
        return {"error":"path必须是字符串"}

    return ToolRequest(
        name=name,
        path=path,
    )



#处理请求
def handle_request(raw: str) ->  ToolResult:
    result=parse_request(raw)
    if isinstance(result,dict):
        return ToolResult(
            content=result["error"],
            is_error=True,
        )
    return dispatch(
        result.name,
        result.path,
    )
