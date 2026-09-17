import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from models import ToolResult


def run_tests(cwd: str, workspace_root: str) -> ToolResult:
    root = Path(workspace_root).resolve()
    directory = Path(cwd)
    if not directory.is_absolute():
        directory = root / directory
    directory = directory.resolve()

    if not directory.is_relative_to(root):
        return ToolResult("工作目录超出允许范围", is_error=True)

    try:
        # 每次运行使用新缓存目录，避免快速编辑后读到旧的 .pyc。
        with TemporaryDirectory(prefix="agent-pycache-") as cache_dir:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"],
                cwd=directory,
                timeout=30,
                capture_output=True,
                text=True,
                shell=False,
                env={**os.environ, "PYTHONPYCACHEPREFIX": cache_dir},
            )
    except subprocess.TimeoutExpired:
        return ToolResult("命令执行超时", is_error=True)
    except FileNotFoundError:
        return ToolResult("命令启动失败", is_error=True)

    stdout = result.stdout[:1000]
    stderr = result.stderr[:1000]
    content = f"退出码: {result.returncode}\n{stdout}"
    if stderr:
        content += f"\n标准错误:\n{stderr}"
    if len(result.stdout) > 1000 or len(result.stderr) > 1000:
        content += "\n[输出已截断]"

    return ToolResult(content, is_error=result.returncode != 0)
