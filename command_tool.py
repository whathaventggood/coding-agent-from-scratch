from models import ToolResult
from r4_practice import run_allowed_command


def run_tests(cwd: str, workspace_root: str) -> ToolResult:
    result = run_allowed_command(
        "project_tests",
        cwd,
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