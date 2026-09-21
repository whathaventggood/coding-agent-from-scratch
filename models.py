from dataclasses import dataclass


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


@dataclass
class ToolRequest:
    name: str
    path: str
    keyword: str | None = None
    old_text: str | None = None
    new_text: str | None = None
    start_line: int | None = None
    max_lines: int | None = None


 # 记录 Agent 每一次工具调用的信息
@dataclass
class ToolTraceEntry:
    model_step: int
    tool_name: str
    is_error: bool
    summary: str
