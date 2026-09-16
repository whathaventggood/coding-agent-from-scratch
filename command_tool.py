from models import ToolResult
from r4_practice import run_allowed_command
from pathlib import Path

def run_tests(cwd: str, workspace_root: str) -> ToolResult:
    cwd_path = Path(cwd)          #将路径字符串转成路径对象

    if not cwd_path.is_absolute():
        cwd_path = Path(workspace_root) / cwd_path

    result = run_allowed_command(
        "project_tests",
        cwd_path,
        workspace_root,
        timeout=30,
    )

    if result["returncode"] is None:
        return ToolResult(
            content=result["stderr"],
            is_error=True,
        )

    content = f"退出码: {result['returncode']}\n{result['stdout']}"

    if result["stderr"]:
        content += f"\n标准错误:\n{result['stderr']}"

    if result["stdout_truncated"] or result["stderr_truncated"]:
        content += "\n[输出已截断]"

    return ToolResult(
        content=content,
        is_error=result["returncode"] != 0,
    )