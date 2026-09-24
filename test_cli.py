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


def test_rollback_restores_task_start_file_state(tmp_path):
    initialize_git_repository(tmp_path)

    modified_file = tmp_path / "modified.py"
    deleted_file = tmp_path / "deleted.py"
    created_file = tmp_path / "created.py"

    modified_file.write_text("committed value\n", encoding="utf-8")
    deleted_file.write_text("keep this file\n", encoding="utf-8")

    subprocess.run(
        ["git", "add", "modified.py", "deleted.py"],
        cwd=tmp_path,
        check=True,
    )

    # 模拟任务开始前用户已有的未提交修改。
    modified_file.write_text(
        "user change before task\n",
        encoding="utf-8",
    )

    before = cli.capture_workspace_snapshot(tmp_path)

    # 模拟本次 Agent 产生的部分修改。
    modified_file.write_text(
        "agent partial change\n",
        encoding="utf-8",
    )
    deleted_file.unlink()
    created_file.write_text(
        "agent created file\n",
        encoding="utf-8",
    )

    after = cli.capture_workspace_snapshot(tmp_path)

    result = cli.rollback_workspace_changes(
        tmp_path,
        before,
        after,
    )

    assert result.error is None
    assert result.restored_paths == [
        "deleted.py",
        "modified.py",
    ]
    assert result.removed_paths == ["created.py"]

    assert (
            modified_file.read_text(encoding="utf-8")
            == "user change before task\n"
    )
    assert (
            deleted_file.read_text(encoding="utf-8")
            == "keep this file\n"
    )
    assert not created_file.exists()

    restored_snapshot = cli.capture_workspace_snapshot(tmp_path)

    assert cli.find_workspace_changes(
        before,
        restored_snapshot,
    ) == {
        "created": [],
        "modified": [],
        "deleted": [],
    }


def test_rollback_rejects_changed_symlink(tmp_path):
    initialize_git_repository(tmp_path)

    first_target = tmp_path / "first.txt"
    second_target = tmp_path / "second.txt"
    link = tmp_path / "current.txt"

    first_target.write_text("first\n", encoding="utf-8")
    second_target.write_text("second\n", encoding="utf-8")
    link.symlink_to(first_target.name)

    subprocess.run(
        ["git", "add", "first.txt", "second.txt", "current.txt"],
        cwd=tmp_path,
        check=True,
    )

    before = cli.capture_workspace_snapshot(tmp_path)

    link.unlink()
    link.symlink_to(second_target.name)

    after = cli.capture_workspace_snapshot(tmp_path)
    result = cli.rollback_workspace_changes(
        tmp_path,
        before,
        after,
    )

    assert result.restored_paths == []
    assert result.removed_paths == []
    assert result.error == "无法安全回滚以下路径：current.txt"
    assert link.readlink() == second_target.relative_to(tmp_path)


def test_cli_failure_keeps_partial_workspace_changes(
        tmp_path,
        monkeypatch,
        capsys,
):
    initialize_git_repository(tmp_path)

    modified_file = tmp_path / "modified.py"
    deleted_file = tmp_path / "deleted.py"
    created_file = tmp_path / "created.py"

    modified_file.write_text("value = 1\n", encoding="utf-8")
    deleted_file.write_text("value = 1\n", encoding="utf-8")

    subprocess.run(
        ["git", "add", "modified.py", "deleted.py"],
        cwd=tmp_path,
        check=True,
    )

    def fake_agent(*args, **kwargs):
        modified_file.write_text("value = 2\n", encoding="utf-8")
        created_file.write_text("value = 1\n", encoding="utf-8")
        deleted_file.unlink()
        raise RuntimeError("planned agent failure")

    def fail_if_verification_runs(*args, **kwargs):
        raise AssertionError("模型执行失败后不应运行独立复验")

    monkeypatch.setattr(
        cli,
        "read_file_and_answer",
        fake_agent,
    )
    monkeypatch.setattr(
        cli,
        "run_tests",
        fail_if_verification_runs,
    )

    report_path = (
        tmp_path.parent
        / f"{tmp_path.name}-failure-report.json"
    )

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
            "触发确定性失败",
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    output = capsys.readouterr().out

    assert error.value.code == 1
    assert modified_file.read_text(encoding="utf-8") == "value = 2\n"
    assert created_file.read_text(encoding="utf-8") == "value = 1\n"
    assert not deleted_file.exists()

    assert "- 新增或恢复：created.py" in output
    assert "- 修改：modified.py" in output
    assert "- 删除：deleted.py" in output
    assert "未执行（未开启编辑模式或模型执行失败）" in output
    assert "失败：模型执行失败：planned agent failure" in output

    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert report["status"] == "failure"
    assert (
            report["failure_reason"]
            == "模型执行失败：planned agent failure"
    )
    assert report["verification"] is None
    assert report["workspace_changes"] == {
        "created": ["created.py"],
        "modified": ["modified.py"],
        "deleted": ["deleted.py"],
    }
    assert report["rollback_on_failure"] is False
    assert report["rollback"] is None


def test_cli_rolls_back_partial_changes_after_agent_failure(
        tmp_path,
        monkeypatch,
        capsys,
):
    initialize_git_repository(tmp_path)

    modified_file = tmp_path / "modified.py"
    deleted_file = tmp_path / "deleted.py"
    created_file = tmp_path / "created.py"

    modified_file.write_text(
        "user state before task\n",
        encoding="utf-8",
    )
    deleted_file.write_text(
        "keep this file\n",
        encoding="utf-8",
    )

    subprocess.run(
        ["git", "add", "modified.py", "deleted.py"],
        cwd=tmp_path,
        check=True,
    )

    def fake_agent(*args, **kwargs):
        modified_file.write_text(
            "agent partial change\n",
            encoding="utf-8",
        )
        created_file.write_text(
            "agent created file\n",
            encoding="utf-8",
        )
        deleted_file.unlink()
        raise RuntimeError("planned agent failure")

    monkeypatch.setattr(
        cli,
        "read_file_and_answer",
        fake_agent,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cli.py",
            "--workspace",
            str(tmp_path),
            "--allow-edit",
            "--rollback-on-failure",
            "触发失败并恢复",
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    output = capsys.readouterr().out

    assert error.value.code == 1

    assert (
            modified_file.read_text(encoding="utf-8")
            == "user state before task\n"
    )
    assert (
            deleted_file.read_text(encoding="utf-8")
            == "keep this file\n"
    )
    assert not created_file.exists()

    # 运行报告保留 Agent 原本产生的三类变化。
    assert "- 新增或恢复：created.py" in output
    assert "- 修改：modified.py" in output
    assert "- 删除：deleted.py" in output

    # 最终磁盘状态已经恢复。
    assert "失败恢复：" in output
    assert "成功：Git 可见普通文件已恢复到任务开始时状态" in output
    assert "- 恢复：deleted.py" in output
    assert "- 恢复：modified.py" in output
    assert "- 移除本次新建：created.py" in output


def test_cli_rolls_back_when_independent_verification_fails(
        tmp_path,
        monkeypatch,
        capsys,
):
    initialize_git_repository(tmp_path)

    source_file = tmp_path / "calculator.py"
    source_file.write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )

    subprocess.run(
        ["git", "add", "calculator.py"],
        cwd=tmp_path,
        check=True,
    )

    def fake_agent(*args, **kwargs):
        source_file.write_text(
            "def add(a, b):\n    return a + b\n",
            encoding="utf-8",
        )
        return "已完成修复"

    def fake_verification(*args, **kwargs):
        return ToolResult(
            "退出码: 1\n1 failed",
            is_error=True,
        )

    monkeypatch.setattr(
        cli,
        "read_file_and_answer",
        fake_agent,
    )
    monkeypatch.setattr(
        cli,
        "run_tests",
        fake_verification,
    )

    report_path = (
        tmp_path.parent
        / f"{tmp_path.name}-verification-report.json"
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cli.py",
            "--workspace",
            str(tmp_path),
            "--allow-edit",
            "--rollback-on-failure",
            "--report-json",
            str(report_path),
            "修复计算错误",
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    output = capsys.readouterr().out

    assert error.value.code == 1
    assert (
            source_file.read_text(encoding="utf-8")
            == "def add(a, b):\n    return a - b\n"
    )

    assert "失败：本地独立复验未通过" in output
    assert "成功：Git 可见普通文件已恢复到任务开始时状态" in output
    assert "- 恢复：calculator.py" in output

    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert report["status"] == "failure"
    assert report["failure_reason"] == "本地独立复验未通过"
    assert report["workspace_changes"] == {
        "created": [],
        "modified": ["calculator.py"],
        "deleted": [],
    }
    assert report["rollback_on_failure"] is True
    assert report["rollback"] == {
        "status": "success",
        "restored_paths": ["calculator.py"],
        "removed_paths": [],
        "error": None,
    }


def test_cli_exits_nonzero_when_independent_verification_fails(
        tmp_path,
        monkeypatch,
        capsys,
):
    received_profiles = []

    def fake_agent(*args, **kwargs):
        received_profiles.append(
            ("agent", kwargs["verification_profile"])
        )
        return "已尝试修复"

    def fake_verification(*args, **kwargs):
        received_profiles.append(
            ("verification", kwargs["verification_profile"])
        )
        return ToolResult(
            "退出码: 1\n1 failed",
            is_error=True,
        )

    monkeypatch.setattr(
        cli,
        "read_file_and_answer",
        fake_agent,
    )
    monkeypatch.setattr(
        cli,
        "run_tests",
        fake_verification,
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
            "--verification-profile",
            "unittest",
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
    assert report["verification_profile"] == "unittest"
    assert received_profiles == [
        ("agent", "unittest"),
        ("verification", "unittest"),
    ]
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
        "history_trim_count": 0,
        "trimmed_message_count": 0,
        "released_history_chars": 0,
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
