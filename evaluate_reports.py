import argparse
import json
from pathlib import Path

REQUIRED_FIELDS = {
    "status",
    "tool_trace",
    "verification",
    "workspace_changes",
}

CONTEXT_USAGE_FIELDS = (
    "model_request_count",
    "peak_message_chars",
    "history_trim_count",
    "trimmed_message_count",
    "released_history_chars",
)


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


def read_context_usage(
        report: dict,
        path: Path,
) -> dict | None:
    context_usage = report.get("context_usage")

    if context_usage is None:
        return None

    if not isinstance(context_usage, dict):
        raise ValueError(
            f"报告 context_usage 必须是对象：{path}"
        )

    values = {}

    for field_name in CONTEXT_USAGE_FIELDS:
        value = context_usage.get(field_name, 0)

        if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
        ):
            raise ValueError(
                f"报告 context_usage.{field_name} "
                f"必须是非负整数：{path}"
            )

        values[field_name] = value

    return values


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

    context_observed_runs = 0
    total_model_requests = 0
    max_peak_message_chars = 0
    total_history_trims = 0
    total_trimmed_messages = 0
    total_released_history_chars = 0

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

        context_usage = read_context_usage(
            report,
            path,
        )
        context_usage_available = context_usage is not None

        if context_usage is None:
            model_requests = 0
            peak_message_chars = 0
            history_trim_count = 0
            trimmed_message_count = 0
            released_history_chars = 0
        else:
            context_observed_runs += 1

            model_requests = context_usage[
                "model_request_count"
            ]
            peak_message_chars = context_usage[
                "peak_message_chars"
            ]
            history_trim_count = context_usage[
                "history_trim_count"
            ]
            trimmed_message_count = context_usage[
                "trimmed_message_count"
            ]
            released_history_chars = context_usage[
                "released_history_chars"
            ]

            total_model_requests += model_requests
            max_peak_message_chars = max(
                max_peak_message_chars,
                peak_message_chars,
            )
            total_history_trims += history_trim_count
            total_trimmed_messages += trimmed_message_count
            total_released_history_chars += (
                released_history_chars
            )

        runs.append({
            "path": str(path),
            "task": report.get("task", ""),
            "status": report["status"],
            "verification": verification_status,
            "tool_calls": tool_calls,
            "failed_tool_calls": tool_errors,
            "file_changes": file_changes,
            "context_usage_available": (
                context_usage_available
            ),
            "model_requests": model_requests,
            "peak_message_chars": peak_message_chars,
            "history_trim_count": history_trim_count,
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
        "context_observed_runs": context_observed_runs,
        "total_model_requests": total_model_requests,
        "max_peak_message_chars": max_peak_message_chars,
        "total_history_trims": total_history_trims,
        "total_trimmed_messages": total_trimmed_messages,
        "total_released_history_chars": (
            total_released_history_chars
        ),
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
    print(
        "上下文观测覆盖："
        f"{summary['context_observed_runs']}/{total_runs}"
    )

    if summary["context_observed_runs"]:
        print(
            f"模型请求总数：{summary['total_model_requests']}"
            f" | 最大消息峰值："
            f"{summary['max_peak_message_chars']}"
        )
        print(
            f"历史裁剪：{summary['total_history_trims']}"
            f" | 删除旧消息："
            f"{summary['total_trimmed_messages']}"
            f" | 释放历史字符："
            f"{summary['total_released_history_chars']}"
        )
    else:
        print("上下文指标：旧报告未提供")

    print("\n逐次运行：")

    for run in summary["runs"]:
        if run["context_usage_available"]:
            context_part = (
                f" | model_requests={run['model_requests']}"
                f" | peak_chars={run['peak_message_chars']}"
                f" | trims={run['history_trim_count']}"
            )
        else:
            context_part = " | context=unavailable"

        print(
            f"- {run['path']}"
            f" | {run['status']}"
            f" | verification={run['verification']}"
            f" | tools={run['tool_calls']}"
            f" | tool_errors={run['failed_tool_calls']}"
            f" | changes={run['file_changes']}"
            f"{context_part}"
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
