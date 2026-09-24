import json
import subprocess
import sys
from pathlib import Path

import pytest

from command_tool import build_verification_command
from evaluate_reports import summarize_reports
from run_benchmark import (
    build_cli_command,
    load_benchmark_tasks,
    prepare_task_workspace,
    verify_benchmark_guard,
    run_benchmark_task,
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


def test_portfolio_tasks_start_with_failing_verification(tmp_path):
    manifest = Path(__file__).with_name(
        "benchmark_tasks_portfolio.json"
    )
    tasks = load_benchmark_tasks(manifest)

    assert len(tasks) == 8
    assert all(task["allow_edit"] for task in tasks)
    assert all(task["protected_files"] for task in tasks)
    assert all(task["holdout_files"] for task in tasks)

    for task in tasks:
        workspace = tmp_path / task["name"]
        prepare_task_workspace(task, workspace)
        result = subprocess.run(
            build_verification_command(
                task["verification_profile"]
            ),
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0, task["name"]


def test_benchmark_guard_checks_hidden_tests_after_agent(tmp_path):
    task = {
        "name": "guard-example",
        "files": {
            "maths.py": "def double(value):\n    return value\n",
            "test_maths.py": (
                "from maths import double\n\n"
                "def test_two():\n    assert double(2) == 4\n"
            ),
        },
        "protected_files": ["test_maths.py"],
        "holdout_files": {
            "test_holdout_maths.py": (
                "from maths import double\n\n"
                "def test_three():\n    assert double(3) == 6\n"
            ),
        },
        "verification_profile": "pytest",
    }
    workspace = tmp_path / "workspace"
    prepare_task_workspace(task, workspace)
    assert not (workspace / "test_holdout_maths.py").exists()
    skipped = verify_benchmark_guard(task, workspace, 1)
    assert skipped["status"] == "skipped"
    assert skipped["protected_files_unchanged"] is True
    assert not (workspace / "test_holdout_maths.py").exists()

    # 可见测试能过，但只硬编码一个输入会被结束后加入的测试识别。
    (workspace / "maths.py").write_text(
        "def double(value):\n    return 4\n",
        encoding="utf-8",
    )
    guard = verify_benchmark_guard(task, workspace, 0)
    assert guard["status"] == "failed"
    assert guard["holdout_status"] == "failed"

    (workspace / "maths.py").write_text(
        "def double(value):\n    return value * 2\n",
        encoding="utf-8",
    )
    (workspace / "test_holdout_maths.py").unlink()
    guard = verify_benchmark_guard(task, workspace, 0)
    assert guard["status"] == "passed"
    assert guard["protected_files_unchanged"] is True


def test_benchmark_guard_rejects_modified_visible_test(tmp_path):
    task = {
        "name": "test-edit",
        "files": {
            "test_math.py": "def test_real():\n    assert False\n",
        },
        "protected_files": ["test_math.py"],
        "holdout_files": {
            "test_holdout.py": "def test_other():\n    assert True\n",
        },
        "verification_profile": "pytest",
    }
    workspace = tmp_path / "workspace"
    prepare_task_workspace(task, workspace)
    (workspace / "test_math.py").write_text(
        "def test_real():\n    assert True\n",
        encoding="utf-8",
    )

    guard = verify_benchmark_guard(task, workspace, 0)
    assert guard["status"] == "failed"
    assert guard["protected_files_unchanged"] is False
    assert not (workspace / "test_holdout.py").exists()

    (workspace / "test_math.py").unlink()
    (workspace / "replacement.py").write_text(
        task["files"]["test_math.py"],
        encoding="utf-8",
    )
    (workspace / "test_math.py").symlink_to("replacement.py")
    guard = verify_benchmark_guard(task, workspace, 0)
    assert guard["status"] == "failed"
    assert guard["protected_files_unchanged"] is False


@pytest.mark.parametrize(
    "holdout_path",
    [
        "../outside.py",
        "/tmp/outside.py",
        "test_visible.py",
        "./test_visible.py",
        "tests/test_holdout.py",
        "holdout.py",
    ],
)
def test_benchmark_manifest_rejects_unsafe_holdout_path(
        tmp_path,
        holdout_path,
):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps({
        "tasks": [{
            "name": "unsafe-holdout",
            "prompt": "fix",
            "files": {"test_visible.py": "def test_a(): pass\n"},
            "protected_files": ["test_visible.py"],
            "holdout_files": {holdout_path: "def test_b(): pass\n"},
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError):
        load_benchmark_tasks(manifest)


def test_benchmark_summary_counts_guard_failure_as_failure(tmp_path):
    report_path = tmp_path / "report.json"
    write_report(report_path, {
        "status": "success",
        "benchmark_status": "failure",
        "benchmark_guard": {
            "status": "failed",
            "protected_files_unchanged": False,
            "holdout_status": "skipped",
            "holdout_output": "test changed",
        },
        "tool_trace": [],
        "verification": {"is_error": False},
        "workspace_changes": None,
    })

    summary = summarize_reports([report_path])
    assert summary["successful_runs"] == 0
    assert summary["guard_failed_runs"] == 1
    assert summary["verification_passed_runs"] == 1
    assert summary["runs"][0]["agent_status"] == "success"
    assert summary["runs"][0]["status"] == "failure"


def test_benchmark_runner_records_guard_result_without_model(
        tmp_path,
        monkeypatch,
):
    task = {
        "name": "runner-example",
        "files": {
            "maths.py": "def double(value):\n    return value\n",
            "test_maths.py": (
                "from maths import double\n\n"
                "def test_two():\n    assert double(2) == 4\n"
            ),
        },
        "protected_files": ["test_maths.py"],
        "holdout_files": {
            "test_holdout.py": (
                "from maths import double\n\n"
                "def test_three():\n    assert double(3) == 6\n"
            ),
        },
        "verification_profile": "pytest",
    }
    report_path = tmp_path / "report.json"
    agent_report = json.dumps({
        "status": "success",
        "tool_trace": [],
        "verification": {"is_error": False},
        "workspace_changes": None,
    })
    script = (
        "from pathlib import Path; import sys; "
        "Path(sys.argv[1]).write_text(sys.argv[3], encoding='utf-8'); "
        "Path(sys.argv[2]).write_text("
        "'def double(value):\\n    return value * 2\\n', "
        "encoding='utf-8')"
    )

    def fake_command(_task, workspace, output):
        return [
            sys.executable, "-c", script,
            str(output), str(workspace / "maths.py"),
            agent_report,
        ]

    monkeypatch.setattr(
        "run_benchmark.build_cli_command",
        fake_command,
    )

    assert run_benchmark_task(task, report_path) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "success"
    assert report["benchmark_status"] == "success"
    assert report["benchmark_guard"]["holdout_status"] == "passed"


def test_benchmark_runner_fails_when_agent_edits_test(
        tmp_path,
        monkeypatch,
):
    task = {
        "name": "tampered-test",
        "files": {
            "test_maths.py": "def test_real():\n    assert False\n",
        },
        "protected_files": ["test_maths.py"],
        "holdout_files": {},
        "verification_profile": "pytest",
    }
    report_path = tmp_path / "report.json"
    agent_report = json.dumps({
        "status": "success",
        "tool_trace": [],
        "verification": {"is_error": False},
        "workspace_changes": None,
    })
    script = (
        "from pathlib import Path; import sys; "
        "Path(sys.argv[1]).write_text(sys.argv[3], encoding='utf-8'); "
        "Path(sys.argv[2]).write_text("
        "'def test_real():\\n    assert True\\n', "
        "encoding='utf-8')"
    )

    monkeypatch.setattr(
        "run_benchmark.build_cli_command",
        lambda _task, workspace, output: [
            sys.executable, "-c", script,
            str(output), str(workspace / "test_maths.py"),
            agent_report,
        ],
    )

    assert run_benchmark_task(task, report_path) == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "success"
    assert report["benchmark_status"] == "failure"
    assert report["benchmark_guard"][
        "protected_files_unchanged"
    ] is False


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
