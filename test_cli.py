import subprocess
import sys
import json
import pytest

import cli
from models import ToolResult


def initialize_git_repository(path):
    subprocess.run(
        ["git", "init", "-q"],
        cwd=path,
        check=True,
    )


def test_snapshot_reports_created_modified_and_deleted_files(tmp_path):
    initialize_git_repository(tmp_path)

    modified_file = tmp_path / "modified.py"
    deleted_file = tmp_path / "deleted.py"

    modified_file.write_text("value = 1\n", encoding="utf-8")
    deleted_file.write_text("value = 1\n", encoding="utf-8")

    subprocess.run(
        ["git", "add", "modified.py", "deleted.py"],
        cwd=tmp_path,
        check=True,
    )

    before = cli.capture_workspace_snapshot(tmp_path)

    modified_file.write_text("value = 2\n", encoding="utf-8")
    deleted_file.unlink()
    (tmp_path / "created.py").write_text(
        "value = 1\n",
        encoding="utf-8",
    )

    after = cli.capture_workspace_snapshot(tmp_path)

    assert cli.find_workspace_changes(before, after) == {
        "created": ["created.py"],
        "modified": ["modified.py"],
        "deleted": ["deleted.py"],
    }


def test_snapshot_ignores_unchanged_old_edit_but_detects_new_edit(tmp_path):
    initialize_git_repository(tmp_path)

    unchanged_old_edit = tmp_path / "old_edit.py"
    changed_again = tmp_path / "changed_again.py"

    unchanged_old_edit.write_text("value = 1\n", encoding="utf-8")
    changed_again.write_text("value = 1\n", encoding="utf-8")

    subprocess.run(
        ["git", "add", "old_edit.py", "changed_again.py"],
        cwd=tmp_path,
        check=True,
    )

    unchanged_old_edit.write_text("value = 2\n", encoding="utf-8")
    changed_again.write_text("value = 2\n", encoding="utf-8")

    before = cli.capture_workspace_snapshot(tmp_path)

    changed_again.write_text("value = 3\n", encoding="utf-8")

    after = cli.capture_workspace_snapshot(tmp_path)
    changes = cli.find_workspace_changes(before, after)

    assert changes == {
        "created": [],
        "modified": ["changed_again.py"],
        "deleted": [],
    }


def test_cli_exits_nonzero_when_independent_verification_fails(
        tmp_path,
        monkeypatch,
        capsys,
):
    monkeypatch.setattr(
        cli,
        "read_file_and_answer",
        lambda *args, **kwargs: "已尝试修复",
    )
    monkeypatch.setattr(
        cli,
        "run_tests",
        lambda *args: ToolResult(
            "退出码: 1\n1 failed",
            is_error=True,
        ),
    )
    report_path = tmp_path / "run-report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cli.py",
            "--workspace",
            str(tmp_path),
            "--allow-edit",
            "--report-json",
            str(report_path),
            "修复失败的测试",
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    output = capsys.readouterr().out

    assert error.value.code == 1
    assert "已尝试修复" in output
    assert "退出码: 1" in output
    assert "无法归因：工作区不是 Git 仓库" in output
    assert "失败：本地独立复验未通过" in output

    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert report["task"] == "修复失败的测试"
    assert report["workspace"] == str(tmp_path.resolve())
    assert report["allow_edit"] is True
    assert report["max_steps"] == 8
    assert report["status"] == "failure"
    assert report["failure_reason"] == "本地独立复验未通过"
    assert report["answer"] == "已尝试修复"
    assert report["tool_trace"] == []
    assert report["context_usage"] == {
        "model_request_count": 0,
        "request_message_chars": [],
        "peak_message_chars": 0,
        "compressed_tool_message_count": 0,
        "released_tool_result_chars": 0,
    }
    assert report["verification"] == {
        "content": "退出码: 1\n1 failed",
        "is_error": True,
    }
    assert report["workspace_changes"] is None
    assert (
            report["workspace_change_message"]
            == "无法归因：工作区不是 Git 仓库，无法记录 Git 基线"
    )
