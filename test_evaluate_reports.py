import json

from evaluate_reports import summarize_reports


def write_report(path, report):
    path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_summarize_success_and_failure_reports(tmp_path):
    success_path = tmp_path / "success.json"
    failure_path = tmp_path / "failure.json"

    write_report(
        success_path,
        {
            "task": "修复加法函数",
            "status": "success",
            "tool_trace": [
                {
                    "tool_name": "edit_file",
                    "is_error": False,
                },
            ],
            "verification": {
                "content": "1 passed",
                "is_error": False,
            },
            "workspace_changes": {
                "created": [],
                "modified": ["calculator.py"],
                "deleted": [],
            },
        },
    )

    write_report(
        failure_path,
        {
            "task": "读取不存在的文件",
            "status": "failure",
            "tool_trace": [
                {
                    "tool_name": "read_file",
                    "is_error": True,
                },
                {
                    "tool_name": "list_files",
                    "is_error": False,
                },
            ],
            "verification": None,
            "workspace_changes": None,
        },
    )

    summary = summarize_reports([
        success_path,
        failure_path,
    ])

    assert summary["total_runs"] == 2
    assert summary["successful_runs"] == 1
    assert summary["failed_runs"] == 1
    assert summary["verification_passed_runs"] == 1
    assert summary["verification_failed_runs"] == 0
    assert summary["verification_skipped_runs"] == 1
    assert summary["total_tool_calls"] == 3
    assert summary["failed_tool_calls"] == 1
    assert summary["total_file_changes"] == 1

    assert summary["runs"][0]["status"] == "success"
    assert summary["runs"][0]["verification"] == "passed"
    assert summary["runs"][1]["status"] == "failure"
    assert summary["runs"][1]["verification"] == "skipped"
