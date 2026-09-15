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

ALLOWED_COMMANDS = {
    "success_check": success_command,
    "failure_check": failure_command,
    "timeout_check": timeout_command,
    "show_cwd": show_cwd_command,
    "greeting_check": greeting_command,
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

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "命令执行超时",
            "timed_out": True,
        }
    except FileNotFoundError:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "命令启动失败",
            "timed_out": False,
        }


def run_allowed_command(name, cwd, timeout=2):
    command = ALLOWED_COMMANDS.get(name)

    if command is None:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "命令不在允许列表",
            "timed_out": False,
        }

    return run_command(command, cwd, timeout)


if __name__ == "__main__":
    project_dir = Path.cwd()
    parent_dir = project_dir.parent

    print("父进程当前目录: ", project_dir)
    print(run_allowed_command("show_cwd", parent_dir, 2))
    print("父进程运行后目录: ", Path.cwd())
