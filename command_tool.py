import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from models import ToolResult

VERIFICATION_PROFILES = (
    "pytest",
    "unittest",
)


def build_verification_command(
        verification_profile: str,
) -> list[str]:
    commands = {
        "pytest": [
            sys.executable,
            "-m",
            "pytest",
            "-q",
        ],
        "unittest": [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-v",
        ],
    }

    command = commands.get(verification_profile)

    if command is None:
        raise ValueError(
            f"不支持的验证方案：{verification_profile}"
        )

    return command


def run_tests(
        cwd: str,
        workspace_root: str,
        verification_profile: str = "pytest",
) -> ToolResult:
    root = Path(workspace_root).resolve()
    directory = Path(cwd)
    if not directory.is_absolute():
        directory = root / directory
    directory = directory.resolve()

    if not directory.is_relative_to(root):
        return ToolResult(
            "工作目录超出允许范围",
            is_error=True,
        )

    try:
        command = build_verification_command(
            verification_profile
        )
    except ValueError as error:
        return ToolResult(
            str(error),
            is_error=True,
        )

    try:
        # 每次运行使用新缓存目录，避免快速编辑后读到旧的 .pyc。
        with TemporaryDirectory(prefix="agent-pycache-") as cache_dir:
            result = subprocess.run(
                command,
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


def inspect_git_changes(
        cwd: str,
        workspace_root: str,
) -> ToolResult:
    root = Path(workspace_root).resolve()
    directory = Path(cwd)

    if not directory.is_absolute():
        directory = root / directory

    directory = directory.resolve()

    if not directory.is_relative_to(root):
        return ToolResult(
            content="工作目录超出允许范围",
            is_error=True,
        )

    commands = {
        "Git状态": [
            "git",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            ".",
        ],
        "未暂存差异": [
            "git",
            "diff",
            "--",
            ".",
        ],
        "已暂存差异": [
            "git",
            "diff",
            "--cached",
            "--",
            ".",
        ],
    }

    sections = []

    try:
        for label, command in commands.items():
            result = subprocess.run(
                command,
                cwd=directory,
                timeout=10,
                capture_output=True,
                text=True,
                shell=False,
            )

            if result.returncode != 0:
                message = result.stderr.strip() or result.stdout.strip()
                return ToolResult(
                    content=f"无法读取{label}：{message}",
                    is_error=True,
                )

            output = result.stdout.strip() or "无"
            sections.append(f"{label}：\n{output}")
    except subprocess.TimeoutExpired:
        return ToolResult(
            content="Git 检查超时",
            is_error=True,
        )
    except FileNotFoundError:
        return ToolResult(
            content="未找到 Git",
            is_error=True,
        )

    content = "\n\n".join(sections)

    if len(content) > 12000:
        omitted_count = len(content) - 12000
        content = (
                content[:12000]
                + "\n"
                + f"[Git 检查结果已截断，省略 {omitted_count} 个字符]"
        )

    return ToolResult(
        content=content,
        is_error=False,
    )


def run_test_file(
        path: str,
        workspace_root: str,
) -> ToolResult:
    root = Path(workspace_root).resolve()
    test_file = Path(path)

    if not test_file.is_absolute():
        test_file = root / test_file

    test_file = test_file.resolve()

    if not test_file.is_relative_to(root):
        return ToolResult(
            content="测试文件超出允许范围",
            is_error=True,
        )

    if not test_file.is_file():
        return ToolResult(
            content="测试路径不是已存在的文件",
            is_error=True,
        )

    relative_path = test_file.relative_to(root)

    try:
        with TemporaryDirectory(prefix="agent-pycache-") as cache_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    str(relative_path),
                ],
                cwd=root,
                timeout=30,
                capture_output=True,
                text=True,
                shell=False,
                env={
                    **os.environ,
                    "PYTHONPYCACHEPREFIX": cache_dir,
                },
            )
    except subprocess.TimeoutExpired:
        return ToolResult(
            content="命令执行超时",
            is_error=True,
        )
    except FileNotFoundError:
        return ToolResult(
            content="命令启动失败",
            is_error=True,
        )

    stdout = result.stdout[:1000]
    stderr = result.stderr[:1000]
    content = f"退出码: {result.returncode}\n{stdout}"

    if stderr:
        content += f"\n标准错误:\n{stderr}"

    if len(result.stdout) > 1000 or len(result.stderr) > 1000:
        content += "\n[输出已截断]"

    return ToolResult(
        content=content,
        is_error=result.returncode != 0,
    )
