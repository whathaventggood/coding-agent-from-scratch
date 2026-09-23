import json
import subprocess
import sys

import pytest

from evaluate_reports import summarize_reports
from run_benchmark import (
    build_cli_command,
    load_benchmark_tasks,
    prepare_task_workspace,
    run_benchmark_suite,
)


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
            "context_usage": {
                "model_request_count": 3,
                "peak_message_chars": 12000,
                "history_trim_count": 1,
                "trimmed_message_count": 2,
                "released_history_chars": 800,
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

    assert summary["context_observed_runs"] == 1
    assert summary["total_model_requests"] == 3
    assert summary["max_peak_message_chars"] == 12000
    assert summary["total_history_trims"] == 1
    assert summary["total_trimmed_messages"] == 2
    assert summary["total_released_history_chars"] == 800

    assert (
            summary["runs"][0]["context_usage_available"]
            is True
    )
    assert summary["runs"][0]["model_requests"] == 3
    assert summary["runs"][0]["peak_message_chars"] == 12000
    assert summary["runs"][0]["history_trim_count"] == 1

    assert (
            summary["runs"][1]["context_usage_available"]
            is False
    )


def test_benchmark_manifest_prepares_clean_git_workspace(
        tmp_path,
):
    manifest_path = tmp_path / "tasks.json"
    manifest_path.write_text(
        json.dumps(
            {
                "tasks": [{
                    "name": "fix-addition",
                    "prompt": "修复加法函数并运行测试",
                    "files": {
                        "calculator.py": (
                            "def add(a, b):\n"
                            "    return a - b\n"
                        ),
                        "tests/test_calculator.py": (
                            "from calculator import add\n\n"
                            "def test_add():\n"
                            "    assert add(2, 3) == 5\n"
                        ),
                    },
                    "allow_edit": True,
                    "max_steps": 8,
                    "verification_profile": "unittest",
                }],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tasks = load_benchmark_tasks(manifest_path)

    assert len(tasks) == 1
    assert tasks[0]["name"] == "fix-addition"
    assert tasks[0]["verification_profile"] == "unittest"

    command = build_cli_command(
        tasks[0],
        tmp_path / "command-workspace",
        tmp_path / "report.json",
    )

    assert command[0] == sys.executable
    assert command[1].endswith("cli.py")
    assert "--allow-edit" in command
    profile_index = command.index(
        "--verification-profile"
    )
    assert command[profile_index + 1] == "unittest"
    assert command[-1] == "修复加法函数并运行测试"

    workspace = tmp_path / "workspace"
    prepare_task_workspace(
        tasks[0],
        workspace,
    )

    assert (
                   workspace / "calculator.py"
           ).read_text(encoding="utf-8") == (
               "def add(a, b):\n"
               "    return a - b\n"
           )
    assert (
            workspace / "tests/test_calculator.py"
    ).is_file()

    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )

    assert status.stdout == ""

    invalid_task = {
        **tasks[0],
        "files": {
            "../outside.py": "unsafe\n",
        },
    }

    with pytest.raises(
            ValueError,
            match="超出临时工作区",
    ):
        prepare_task_workspace(
            invalid_task,
            tmp_path / "invalid-workspace",
        )


def test_run_benchmark_suite_writes_summary_without_real_model(
        tmp_path,
        monkeypatch,
):
    tasks = [
        {"name": "success-task"},
        {"name": "failure-task"},
    ]
    output_directory = tmp_path / "reports"

    def fake_run_benchmark_task(task, report_path):
        succeeded = task["name"] == "success-task"

        write_report(
            report_path,
            {
                "task": task["name"],
                "status": (
                    "success"
                    if succeeded
                    else "failure"
                ),
                "tool_trace": [],
                "verification": None,
                "workspace_changes": None,
            },
        )

        return 0 if succeeded else 1

    monkeypatch.setattr(
        "run_benchmark.run_benchmark_task",
        fake_run_benchmark_task,
    )

    report_paths, failed_task_names = run_benchmark_suite(
        tasks,
        output_directory,
    )

    assert report_paths == [
        output_directory / "success-task.json",
        output_directory / "failure-task.json",
    ]
    assert failed_task_names == ["failure-task"]

    summary = json.loads(
        (
                output_directory / "summary.json"
        ).read_text(encoding="utf-8")
    )

    assert summary["total_runs"] == 2
    assert summary["successful_runs"] == 1
    assert summary["failed_runs"] == 1
