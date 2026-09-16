import subprocess
import sys
from pathlib import Path

failure_command = [
    sys.executable,
    "-c",
    "import sys;print('validation failed',file=sys.stderr);sys.exit(7)"
]

success_command = [
    sys.executable,
    "-c",
    "print('R4 ready')"
]

timeout_command = [
    sys.executable,
    "-c",
    "import time;time.sleep(5)"
]

show_cwd_command = [
    sys.executable,
    "-c",
    "from pathlib import Path;print(Path.cwd())"
]

greeting_command = [
    sys.executable,
    "-c",
    "print('hello R4')"
]

literal_argument_command = [
    sys.executable,
    "-c",
    "import sys; print(sys.argv[1])",
    "hello; touch injected.txt",
]

large_stdout_command = [
    sys.executable,
    "-c",
    "import sys; sys.stdout.write('A' * 1001)",
]

large_stderr_command = [
    sys.executable,
    "-c",
    "import sys; sys.stderr.write('E' * 1001)",
]

project_tests_command = [
    sys.executable,
    "-m",
    "pytest",
    "-q",
]

ALLOWED_COMMANDS = {
    "success_check": success_command,
    "failure_check": failure_command,
    "timeout_check": timeout_command,
    "show_cwd": show_cwd_command,
    "greeting_check": greeting_command,
    "literal_argument_check": literal_argument_command,
    "large_stdout_check": large_stdout_command,
    "large_stderr_check": large_stderr_command,
    "project_tests": project_tests_command,
}


def run_command(command, cwd, timeout=2):
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=False,
        )

        stdout_result = truncate_text(result.stdout, 1000)
        stderr_result = truncate_text(result.stderr, 1000)

        return {
            "returncode": result.returncode,
            "stdout": stdout_result["text"],
            "stderr": stderr_result["text"],
            "timed_out": False,
            "stdout_truncated": stdout_result["truncated"],
            "stderr_truncated": stderr_result["truncated"],
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "命令执行超时",
            "timed_out": True,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
    except FileNotFoundError:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "命令启动失败",
            "timed_out": False,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }


def is_allowed_cwd(cwd, workspace_root):
    resolved_cwd = Path(cwd).resolve()
    resolved_root = Path(workspace_root).resolve()

    return resolved_cwd.is_relative_to(resolved_root)


def run_allowed_command(name, cwd, workspace_root, timeout=2):
    command = ALLOWED_COMMANDS.get(name)

    if command is None:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "命令不在允许列表",
            "timed_out": False,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }

    if not is_allowed_cwd(cwd, workspace_root):
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "工作目录超出允许范围",
            "timed_out": False,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }

    return run_command(command, cwd, timeout)


def truncate_text(text, limit):
    return {
        "text": text[:limit],
        "truncated": len(text) > limit,
    }


if __name__ == "__main__":
    project_dir = Path.cwd()
    parent_dir = project_dir.parent

    print("父进程当前目录: ", project_dir)
    print(
        run_allowed_command(
            "show_cwd",
            parent_dir,
            project_dir,
            timeout=2,
        )
    )
    print("父进程运行后目录: ", Path.cwd())
