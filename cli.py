import argparse
import subprocess
from pathlib import Path

from command_tool import run_tests
from deepseek_model import read_file_and_answer


def show_workspace_changes(workspace: Path) -> None:
    try:
        status = subprocess.run(
            ["git", "-C", str(workspace), "status", "--short", "--", "."],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("\n未找到 Git，无法展示工作区差异")
        return

    if status.returncode != 0:
        print("\n工作区不是 Git 仓库，无法展示 Git 差异")
        return

    print("\n当前工作区 Git 状态（可能包含任务开始前的改动）：")
    print(status.stdout or "无改动")

    diff = subprocess.run(
        ["git", "-C", str(workspace), "diff", "--no-ext-diff", "--", "."],
        capture_output=True,
        text=True,
    )
    if diff.returncode == 0 and diff.stdout:
        print("已跟踪文件的差异：")
        print(diff.stdout[:12000])
        if len(diff.stdout) > 12000:
            print("[差异已截断]")


def main():
    parser = argparse.ArgumentParser(description="在受信工作区运行 Coding Agent")
    parser.add_argument("task", help="交给 Agent 的任务")
    parser.add_argument("--workspace", required=True, type=Path, help="受信工作区")
    parser.add_argument("--allow-edit", action="store_true", help="允许修改文件")
    parser.add_argument("--max-steps", type=int, default=8, help="最多请求模型的次数")
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        parser.error("工作区不是已存在的目录")
    if args.max_steps < 1:
        parser.error("--max-steps 必须大于 0")

    try:
        answer = read_file_and_answer(
            args.task,
            workspace_root=str(workspace),
            allow_edit=args.allow_edit,
            max_steps=args.max_steps,
        )
    except RuntimeError as error:
        parser.exit(1, f"{error}\n")

    print(answer)
    if args.allow_edit:
        check = run_tests(".", str(workspace))
        print("\n本地独立复验：", check)
        show_workspace_changes(workspace)
        if check.is_error:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
