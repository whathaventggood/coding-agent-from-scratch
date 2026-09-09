import json
from pathlib import Path


#读工具
def read_file(path):
    if not path:
        return {"error":"路径不能为空"}
    file_path=Path(path)
    if file_path.is_dir():
        return {"error":"路径是目录"}
    try:
        content=file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"error":"文件不存在"}
    return {"content":content}


#列出目录下文件名
def list_files(path):
    if not path:
        return {"error":"路径不能为空"}
    folders = Path(path)
    if not folders.is_dir():
        return {"error":"不是目录"}
    items=folders.iterdir()
    files=[]
    for item in items:
        if item.is_file():
           files.append(str(item))
    return {"files":files}



#选择工具执行
def dispatch(tool_name,path):
    if tool_name=="read_file":
        return read_file(path)
    elif tool_name=="list_files":
        return list_files(path)
    else:
        return {"error":"未知工具"}



#解析json内容
def parse_request(raw):
    try:
        request=json.loads(raw)
    except json.JSONDecodeError:
        return {"error":"json格式错误"}

    if not isinstance(request,dict):
        return {"error":"请求必须是JSON对象"}

    name=request.get("name")
    if name is None:
        return {"error":"缺少name"}

    arguments = request.get("arguments")

    if arguments is None:
        return {"error": "缺少arguments"}

    if not isinstance(arguments, dict):
        return {"error": "arguments必须是JSON对象"}


    path=arguments.get("path")
    if path is None:
        return {"error":"缺少path"}

    return {"name":name,"path":path}



#处理请求
def handle_request(raw):
    result=parse_request(raw)
    if "error" in result:
        return result
    return dispatch(result["name"],result["path"])
