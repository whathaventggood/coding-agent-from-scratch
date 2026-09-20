import argparse
import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from command_tool import run_tests
from deepseek_model import read_file_and_answer
from models import ToolTraceEntry

MISSING_FILE = "<missing>"


@dataclass
class WorkspaceSnapshot:
    is_git_repository: bool
    files: dict[str, str]
    message: str | None = None


def fingerprint_file(path: Path) -> str:
    try:
        if path.is_symlink():
            return f"symlink:{os.readlink(path)}"

        if not path.exists():
            return MISSING_FILE

        if not path.is_file():
            return "other"

        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(64 * 1024):
                digest.update(chunk)

        return digest.hexdigest()
    except OSError as error:
        return f"unreadable:{error.errno}"


def capture_workspace_snapshot(workspace: Path) -> WorkspaceSnapshot:
    try:
        repository_check = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return WorkspaceSnapshot(
            is_git_repository=False,
            files={},
            message="未找到 Git，无法记录 Git 基线",
        )

    if (
            repository_check.returncode != 0
            or repository_check.stdout.strip() != "true"
    ):
        return WorkspaceSnapshot(
            is_git_repository=False,
            files={},
            message="工作区不是 Git 仓库，无法记录 Git 基线",
        )

    file_list = subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            ".",
        ],
        capture_output=True,
        text=True,
    )

    if file_list.returncode != 0:
        return WorkspaceSnapshot(
            is_git_repository=False,
            files={},
            message="无法读取 Git 文件清单",
        )

    files = {}
    for relative_path in file_list.stdout.split("\0"):
        if not relative_path:
            continue

        files[relative_path] = fingerprint_file(workspace / relative_path)

    return WorkspaceSnapshot(
        is_git_repository=True,
        files=files,
    )


def find_workspace_changes(
        before: WorkspaceSnapshot,
        after: WorkspaceSnapshot,
) -> dict[str, list[str]] | None:
    if not before.is_git_repository or not after.is_git_repository:
        return None

    changes = {
        "created": [],
        "modified": [],
        "deleted": [],
    }

    all_paths = sorted(before.files.keys() | after.files.keys())

    for path in all_paths:
        before_exists = (
                path in before.files
                and before.files[path] != MISSING_FILE
        )
        after_exists = (
                path in after.files
                and after.files[path] != MISSING_FILE
        )

        if not before_exists and after_exists:
            changes["created"].append(path)
        elif before_exists and not after_exists:
            changes["deleted"].append(path)
        elif (
                before_exists
                and after_exists
                and before.files[path] != after.files[path]
        ):
            changes["modified"].append(path)

    return changes


def print_run_report(
        answer: str | None,
        tool_trace: list[ToolTraceEntry],
        check,
        before: WorkspaceSnapshot | None,
        after: WorkspaceSnapshot | None,
        failure_reason: str | None = None,
) -> None:
    print("\n=== Coding Agent 运行报告 ===")

    print("\n模型最终回答：")
    if answer is None:
        print("模型未返回最终回答")
    else:
        print(answer)

    print("\n工具调用轨迹：")
    if not tool_trace:
        print("未调用工具")
    else:
        for entry in tool_trace:
            status = "失败" if entry.is_error else "成功"
            print(
                f"- 第 {entry.model_step} 次模型请求"
                f" | {entry.tool_name}"
                f" | {status}"
                f" | {entry.summary}"
            )

    print("\n本地独立复验：")
    if check is None:
        print("未执行（未开启编辑模式或模型执行失败）")
    else:
        print(check.content)

    print("\n本次运行文件变化：")
    if before is None or after is None:
        print("未跟踪（未开启编辑模式）")
    else:
        changes = find_workspace_changes(before, after)

        if changes is None:
            print(f"无法归因：{before.message or after.message}")
        elif not any(changes.values()):
            print("无文件变化")
        else:
            labels = {
                "created": "新增或恢复",
                "modified": "修改",
                "deleted": "删除",
            }
            for change_type, label in labels.items():
                for path in changes[change_type]:
                    print(f"- {label}：{path}")

    print("\n运行结果：")
    if failure_reason is None:
        print("成功")
    else:
        print(f"失败：{failure_reason}")


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

    before = None
    if args.allow_edit:
        before = capture_workspace_snapshot(workspace)

    tool_trace: list[ToolTraceEntry] = []

    try:
        answer = read_file_and_answer(
            args.task,
            workspace_root=str(workspace),
            allow_edit=args.allow_edit,
            max_steps=args.max_steps,
            tool_trace=tool_trace,
        )
    except RuntimeError as error:
        after = None
        if args.allow_edit:
            after = capture_workspace_snapshot(workspace)

        print_run_report(
            answer=None,
            tool_trace=tool_trace,
            check=None,
            before=before,
            after=after,
            failure_reason=f"模型执行失败：{error}",
        )
        raise SystemExit(1)

    check = None
    after = None
    failure_reason = None

    if args.allow_edit:
        check = run_tests(".", str(workspace))
        after = capture_workspace_snapshot(workspace)

        if check.is_error:
            failure_reason = "本地独立复验未通过"

    print_run_report(
        answer=answer,
        tool_trace=tool_trace,
        check=check,
        before=before,
        after=after,
        failure_reason=failure_reason,
    )

    if failure_reason is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
