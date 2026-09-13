from dataclasses import dataclass


@dataclass
class ToolResult:
    content: str
    is_error: bool=False


@dataclass
class ToolRequest:
    name:str
    path:str
    keyword:str|None=None
    old_text:str|None=None
    new_text:str|None=None
