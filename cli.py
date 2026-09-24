import argparse
import hashlib
import os
import subprocess
import json
import stat
from dataclasses import dataclass
from pathlib import Path
from deepseek_model import read_file_and_answer
from models import ContextUsageStats, ToolResult, ToolTraceEntry
from command_tool import (
    VERIFICATION_PROFILES,
    run_tests,
)

MISSING_FILE = "<missing>"


@dataclass
class WorkspaceSnapshot:
    is_git_repository: bool
    files: dict[str, str]
    file_contents: dict[str, bytes]
    file_modes: dict[str, int]
    message: str | None = None


@dataclass
class RollbackResult:
    restored_paths: list[str]
    removed_paths: list[str]
    error: str | None = None


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
            capture_output=True,  # 表示别直接把输出打印终端，而是存进返回对象里
            text=True,  # 输出按字符串处理而非bytes
        )  # 在 workspace 目录里执行一条 Git 命令，判断它是不是 Git 仓库内部
    except FileNotFoundError:
        return WorkspaceSnapshot(
            is_git_repository=False,
            files={},
            file_contents={},
            file_modes={},
            message="未找到 Git，无法记录 Git 基线",
        )

    if (
            repository_check.returncode != 0
            or repository_check.stdout.strip() != "true"
    ):
        return WorkspaceSnapshot(
            is_git_repository=False,
            files={},
            file_contents={},
            file_modes={},
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
            file_contents={},
            file_modes={},
            message="无法读取 Git 文件清单",
        )

    files = {}
    file_contents = {}
    file_modes = {}

    for relative_path in file_list.stdout.split("\0"):
        if not relative_path:
            continue

        file_path = workspace / relative_path
        files[relative_path] = fingerprint_file(file_path)

        if file_path.is_symlink():
            continue

        try:
            if file_path.is_file():
                file_contents[relative_path] = file_path.read_bytes()
                file_modes[relative_path] = stat.S_IMODE(
                    file_path.stat().st_mode
                )
        except OSError:
            continue

    return WorkspaceSnapshot(
        is_git_repository=True,
        files=files,
        file_contents=file_contents,
        file_modes=file_modes,
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


def rollback_workspace_changes(
        workspace: Path,
        before: WorkspaceSnapshot,
        after: WorkspaceSnapshot,
) -> RollbackResult:
    changes = find_workspace_changes(before, after)

    if changes is None:
        return RollbackResult(
            restored_paths=[],
            removed_paths=[],
            error=(
                "无法安全回滚："
                f"{before.message or after.message}"
            ),
        )

    paths_to_restore = sorted(
        changes["modified"] + changes["deleted"]
    )
    paths_to_remove = sorted(changes["created"])
    unsupported_paths = []

    for relative_path in paths_to_restore:
        target = workspace / relative_path

        if (
                relative_path not in before.file_contents
                or relative_path not in before.file_modes
                or not target.parent.is_dir()
                or target.is_symlink()
                or (
                target.exists()
                and not target.is_file()
        )
        ):
            unsupported_paths.append(relative_path)

    for relative_path in paths_to_remove:
        target = workspace / relative_path

        if target.is_symlink() or not target.is_file():
            unsupported_paths.append(relative_path)

    if unsupported_paths:
        return RollbackResult(
            restored_paths=[],
            removed_paths=[],
            error=(
                    "无法安全回滚以下路径："
                    + ", ".join(sorted(set(unsupported_paths)))
            ),
        )

    restored_paths = []
    removed_paths = []

    try:
        for relative_path in paths_to_restore:
            target = workspace / relative_path
            target.write_bytes(
                before.file_contents[relative_path]
            )
            target.chmod(
                before.file_modes[relative_path]
            )
            restored_paths.append(relative_path)

        for relative_path in paths_to_remove:
            target = workspace / relative_path
            target.unlink()
            removed_paths.append(relative_path)
    except OSError as error:
        return RollbackResult(
            restored_paths=restored_paths,
            removed_paths=removed_paths,
            error=f"回滚文件失败：{error}",
        )

    return RollbackResult(
        restored_paths=restored_paths,
        removed_paths=removed_paths,
    )


def perform_failure_rollback(
        enabled: bool,
        workspace: Path,
        before: WorkspaceSnapshot | None,
        after: WorkspaceSnapshot | None,
) -> RollbackResult | None:
    if not enabled:
        return None

    if before is None or after is None:
        return RollbackResult(
            restored_paths=[],
            removed_paths=[],
            error="缺少任务前后快照，无法安全回滚",
        )

    result = rollback_workspace_changes(
        workspace,
        before,
        after,
    )

    if result.error is not None:
        return result

    final_snapshot = capture_workspace_snapshot(workspace)
    remaining_changes = find_workspace_changes(
        before,
        final_snapshot,
    )

    if (
            remaining_changes is None
            or any(remaining_changes.values())
    ):
        return RollbackResult(
            restored_paths=result.restored_paths,
            removed_paths=result.removed_paths,
            error="回滚后工作区仍存在本次任务产生的文件变化",
        )

    return result


def print_rollback_result(
        enabled: bool,
        result: RollbackResult | None,
) -> None:
    print("\n失败恢复：")

    if not enabled:
        print("未启用")
        return

    if result is None:
        print("本次运行未触发回滚")
        return

    if result.error is not None:
        print(f"失败：{result.error}")
        return

    print("成功：Git 可见普通文件已恢复到任务开始时状态")

    for path in result.restored_paths:
        print(f"- 恢复：{path}")

    for path in result.removed_paths:
        print(f"- 移除本次新建：{path}")


def build_json_run_report(
        task: str,
        workspace: Path,
        allow_edit: bool,
        max_steps: int,
        verification_profile: str,
        answer: str | None,
        tool_trace: list[ToolTraceEntry],
        context_usage: ContextUsageStats,
        check: ToolResult | None,
        before: WorkspaceSnapshot | None,
        after: WorkspaceSnapshot | None,
        failure_reason: str | None,
        rollback_on_failure: bool,
        rollback_result: RollbackResult | None,
) -> dict:
    changes = None
    change_message = None

    if before is None or after is None:
        change_message = "未跟踪（未开启编辑模式）"
    else:
        changes = find_workspace_changes(before, after)

        if changes is None:
            change_message = (
                f"无法归因：{before.message or after.message}"
            )

    return {
        "task": task,
        "workspace": str(workspace),
        "allow_edit": allow_edit,
        "max_steps": max_steps,
        "verification_profile": verification_profile,
        "status": (
            "success"
            if failure_reason is None
            else "failure"
        ),
        "failure_reason": failure_reason,
        "rollback_on_failure": rollback_on_failure,
        "rollback": (
            None
            if rollback_result is None
            else {
                "status": (
                    "failure"
                    if rollback_result.error is not None
                    else "success"
                ),
                "restored_paths": rollback_result.restored_paths,
                "removed_paths": rollback_result.removed_paths,
                "error": rollback_result.error,
            }
        ),
        "answer": answer,
        "tool_trace": [
            {
                "model_step": entry.model_step,
                "tool_name": entry.tool_name,
                "is_error": entry.is_error,
                "summary": entry.summary,
            }
            for entry in tool_trace
        ],
        "context_usage": {
            "model_request_count": context_usage.model_request_count,
            "request_message_chars": context_usage.request_message_chars,
            "peak_message_chars": context_usage.peak_message_chars,
            "compressed_tool_message_count": (
                context_usage.compressed_tool_message_count
            ),
            "released_tool_result_chars": (
                context_usage.released_tool_result_chars
            ),
            "history_trim_count": (
                context_usage.history_trim_count
            ),
            "trimmed_message_count": (
                context_usage.trimmed_message_count
            ),
            "released_history_chars": (
                context_usage.released_history_chars
            ),
        },
        "verification": (
            None
            if check is None
            else {
                "content": check.content,
                "is_error": check.is_error,
            }
        ),
        "workspace_changes": changes,
        "workspace_change_message": change_message,
    }


def save_json_run_report(
        report_path: Path | None,
        task: str,
        workspace: Path,
        allow_edit: bool,
        max_steps: int,
        verification_profile: str,
        answer: str | None,
        tool_trace: list[ToolTraceEntry],
        context_usage: ContextUsageStats,
        check: ToolResult | None,
        before: WorkspaceSnapshot | None,
        after: WorkspaceSnapshot | None,
        failure_reason: str | None,
        rollback_on_failure: bool,
        rollback_result: RollbackResult | None,
) -> None:
    if report_path is None:
        return

    report = build_json_run_report(
        task=task,
        workspace=workspace,
        allow_edit=allow_edit,
        max_steps=max_steps,
        verification_profile=verification_profile,
        answer=answer,
        tool_trace=tool_trace,
        context_usage=context_usage,
        check=check,
        before=before,
        after=after,
        failure_reason=failure_reason,
        rollback_on_failure=rollback_on_failure,
        rollback_result=rollback_result,
    )

    try:
        with report_path.open("x", encoding="utf-8") as file:
            json.dump(
                report,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")
    except FileExistsError:
        print("\nJSON 运行记录保存失败：目标文件已存在")
        raise SystemExit(1)
    except OSError as error:
        print(f"\nJSON 运行记录保存失败：{error}")
        raise SystemExit(1)

    print(f"\nJSON 运行记录：{report_path}")


def print_run_report(
        answer: str | None,
        tool_trace: list[ToolTraceEntry],
        context_usage: ContextUsageStats,
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

    print("\n模型上下文用量（近似字符）：")
    print(f"- 模型请求次数：{context_usage.model_request_count}")

    if context_usage.request_message_chars:
        request_sizes = ", ".join(
            str(value)
            for value in context_usage.request_message_chars
        )
        print(f"- 各次完整消息：{request_sizes}")
    else:
        print("- 各次完整消息：无")

    print(f"- 完整消息峰值：{context_usage.peak_message_chars}")
    print(
        "- 已压缩旧工具消息："
        f"{context_usage.compressed_tool_message_count}"
    )
    print(
        "- 已释放工具结果原文字符："
        f"{context_usage.released_tool_result_chars}"
    )
    print(
        "- 完整历史裁剪次数："
        f"{context_usage.history_trim_count}"
    )
    print(
        "- 裁剪掉的旧消息数："
        f"{context_usage.trimmed_message_count}"
    )
    print(
        "- 完整历史释放字符："
        f"{context_usage.released_history_chars}"
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
    parser.add_argument(
        "--rollback-on-failure",
        action="store_true",
        help="任务失败时恢复本次产生的 Git 可见普通文件变化",
    )
    parser.add_argument("--max-steps", type=int, default=8, help="最多请求模型的次数")
    parser.add_argument(
        "--verification-profile",
        choices=VERIFICATION_PROFILES,
        default="pytest",
        help="本地预选的完整验证方案",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        help="将本次运行记录保存为新的 JSON 文件",
    )
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()  # 展开路径对象中的~并且转成绝对路径

    if not workspace.is_dir():
        parser.error("工作区不是已存在的目录")  # 打印 argparse 的标准错误信息,退出程序，退出码通常是 2
    if args.max_steps < 1:
        parser.error("--max-steps 必须大于 0")

    if args.rollback_on_failure and not args.allow_edit:
        parser.error(
            "--rollback-on-failure 必须与 --allow-edit 一起使用"
        )

    report_path = None

    if args.report_json is not None:
        report_path = args.report_json.expanduser().resolve()

        if report_path.exists() or report_path.is_symlink():
            parser.error("--report-json 目标必须不存在")

        if not report_path.parent.is_dir():
            parser.error("--report-json 的父目录不存在")

    before = None
    if args.allow_edit:
        before = capture_workspace_snapshot(workspace)  # Agent 动手前先给整个有效工作区的文件内容留个案底（hash）

    if (
            args.rollback_on_failure
            and before is not None
            and not before.is_git_repository
    ):
        parser.error(
            "--rollback-on-failure 需要有效的 Git 工作区"
        )

    tool_trace: list[ToolTraceEntry] = []
    context_usage = ContextUsageStats()

    try:
        answer = read_file_and_answer(
            args.task,
            workspace_root=str(workspace),
            allow_edit=args.allow_edit,
            max_steps=args.max_steps,
            tool_trace=tool_trace,
            context_usage=context_usage,
            verification_profile=args.verification_profile,
        )
    except RuntimeError as error:
        after = None
        if args.allow_edit:
            after = capture_workspace_snapshot(workspace)

        rollback_result = perform_failure_rollback(
            enabled=args.rollback_on_failure,
            workspace=workspace,
            before=before,
            after=after,
        )

        print_run_report(
            answer=None,
            tool_trace=tool_trace,
            check=None,
            before=before,
            after=after,
            failure_reason=f"模型执行失败：{error}",
            context_usage=context_usage,
        )

        print_rollback_result(
            enabled=args.rollback_on_failure,
            result=rollback_result,
        )

        save_json_run_report(
            report_path=report_path,
            task=args.task,
            workspace=workspace,
            allow_edit=args.allow_edit,
            max_steps=args.max_steps,
            verification_profile=args.verification_profile,
            answer=None,
            tool_trace=tool_trace,
            check=None,
            before=before,
            after=after,
            failure_reason=f"模型执行失败：{error}",
            context_usage=context_usage,
            rollback_on_failure=args.rollback_on_failure,
            rollback_result=rollback_result,
        )

        raise SystemExit(1)

    check = None
    after = None
    failure_reason = None
    rollback_result = None

    if args.allow_edit:
        check = run_tests(
            ".",
            str(workspace),
            verification_profile=args.verification_profile,
        )
        after = capture_workspace_snapshot(workspace)

        if check.is_error:
            failure_reason = "本地独立复验未通过"

    if failure_reason is not None:
        rollback_result = perform_failure_rollback(
            enabled=args.rollback_on_failure,
            workspace=workspace,
            before=before,
            after=after,
        )

    print_run_report(
        answer=answer,
        tool_trace=tool_trace,
        check=check,
        before=before,
        after=after,
        failure_reason=failure_reason,
        context_usage=context_usage,
    )

    print_rollback_result(
        enabled=args.rollback_on_failure,
        result=rollback_result,
    )

    save_json_run_report(
        report_path=report_path,
        task=args.task,
        workspace=workspace,
        allow_edit=args.allow_edit,
        max_steps=args.max_steps,
        verification_profile=args.verification_profile,
        answer=answer,
        tool_trace=tool_trace,
        check=check,
        before=before,
        after=after,
        failure_reason=failure_reason,
        context_usage=context_usage,
        rollback_on_failure=args.rollback_on_failure,
        rollback_result=rollback_result,
    )

    if failure_reason is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
