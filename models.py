from dataclasses import dataclass, field


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
    start_after: str | None = None
    content: str | None = None
    destination: str | None = None


# 记录 Agent 每一次工具调用的信息
@dataclass
class ToolTraceEntry:
    model_step: int
    tool_name: str
    is_error: bool
    summary: str


@dataclass
class ContextUsageStats:
    request_message_chars: list[int] = field(default_factory=list)
    peak_message_chars: int = 0
    compressed_tool_message_count: int = 0
    released_tool_result_chars: int = 0
    history_trim_count: int = 0
    trimmed_message_count: int = 0
    released_history_chars: int = 0

    @property
    def model_request_count(self) -> int:
        return len(self.request_message_chars)
