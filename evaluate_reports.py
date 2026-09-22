import argparse
import json
from pathlib import Path

REQUIRED_FIELDS = {
    "status",
    "tool_trace",
    "verification",
    "workspace_changes",
}


def load_run_report(path: Path) -> dict:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(
            f"无法读取报告 {path}：{error}"
        ) from error

    try:
        report = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"报告不是有效 JSON：{path}"
        ) from error

    if not isinstance(report, dict):
        raise ValueError(
            f"报告顶层必须是 JSON 对象：{path}"
        )

    missing_fields = REQUIRED_FIELDS - report.keys()

    if missing_fields:
        names = ", ".join(sorted(missing_fields))
        raise ValueError(
            f"报告缺少字段 {names}：{path}"
        )

    if report["status"] not in {"success", "failure"}:
        raise ValueError(
            f"报告 status 无效：{path}"
        )

    if not isinstance(report["tool_trace"], list):
        raise ValueError(
            f"报告 tool_trace 必须是列表：{path}"
        )

    return report


def count_file_changes(changes) -> int:
    if not isinstance(changes, dict):
        return 0

    return sum(
        len(changes.get(change_type, []))
        for change_type in (
            "created",
            "modified",
            "deleted",
        )
    )


def summarize_reports(report_paths: list[Path]) -> dict:
    runs = []
    successful_runs = 0
    verification_passed_runs = 0
    verification_failed_runs = 0
    verification_skipped_runs = 0
    total_tool_calls = 0
    failed_tool_calls = 0
    total_file_changes = 0

    for input_path in report_paths:
        path = input_path.expanduser().resolve()
        report = load_run_report(path)

        if report["status"] == "success":
            successful_runs += 1

        verification = report["verification"]

        if verification is None:
            verification_status = "skipped"
            verification_skipped_runs += 1
        elif verification["is_error"]:
            verification_status = "failed"
            verification_failed_runs += 1
        else:
            verification_status = "passed"
            verification_passed_runs += 1

        tool_calls = len(report["tool_trace"])
        tool_errors = sum(
            1
            for entry in report["tool_trace"]
            if entry.get("is_error") is True
        )
        file_changes = count_file_changes(
            report["workspace_changes"]
        )

        total_tool_calls += tool_calls
        failed_tool_calls += tool_errors
        total_file_changes += file_changes

        runs.append({
            "path": str(path),
            "task": report.get("task", ""),
            "status": report["status"],
            "verification": verification_status,
            "tool_calls": tool_calls,
            "failed_tool_calls": tool_errors,
            "file_changes": file_changes,
        })

    total_runs = len(runs)

    return {
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": total_runs - successful_runs,
        "verification_passed_runs": verification_passed_runs,
        "verification_failed_runs": verification_failed_runs,
        "verification_skipped_runs": verification_skipped_runs,
        "total_tool_calls": total_tool_calls,
        "failed_tool_calls": failed_tool_calls,
        "total_file_changes": total_file_changes,
        "runs": runs,
    }


def print_evaluation_summary(summary: dict) -> None:
    total_runs = summary["total_runs"]
    successful_runs = summary["successful_runs"]
    success_rate = (
        successful_runs / total_runs * 100
        if total_runs
        else 0
    )

    print("=== Coding Agent 固定任务评测 ===")
    print(f"运行数量：{total_runs}")
    print(
        f"成功：{successful_runs}"
        f" | 失败：{summary['failed_runs']}"
        f" | 成功率：{success_rate:.1f}%"
    )
    print(
        "独立复验："
        f"通过 {summary['verification_passed_runs']}"
        f" | 失败 {summary['verification_failed_runs']}"
        f" | 未执行 {summary['verification_skipped_runs']}"
    )
    print(
        f"工具调用：{summary['total_tool_calls']}"
        f" | 工具错误：{summary['failed_tool_calls']}"
    )
    print(f"文件变化总数：{summary['total_file_changes']}")

    print("\n逐次运行：")

    for run in summary["runs"]:
        print(
            f"- {run['path']}"
            f" | {run['status']}"
            f" | verification={run['verification']}"
            f" | tools={run['tool_calls']}"
            f" | tool_errors={run['failed_tool_calls']}"
            f" | changes={run['file_changes']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="汇总 Coding Agent JSON 运行记录"
    )
    parser.add_argument(
        "reports",
        nargs="+",
        type=Path,
        help="一个或多个 --report-json 生成的文件",
    )
    args = parser.parse_args()

    try:
        summary = summarize_reports(args.reports)
    except ValueError as error:
        parser.error(str(error))

    print_evaluation_summary(summary)


if __name__ == "__main__":
    main()
