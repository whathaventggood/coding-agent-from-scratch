from r4_practice import run_allowed_command, is_allowed_cwd, truncate_text


def test_success_command(tmp_path):
    result = run_allowed_command(
        "success_check",
        tmp_path,
        tmp_path,
    )

    assert result == {
        "returncode": 0,
        "stdout": "R4 ready\n",
        "stderr": "",
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def test_failure_command(tmp_path):
    result = run_allowed_command(
        "failure_check",
        tmp_path,
        tmp_path,
    )

    assert result == {
        "returncode": 7,
        "stdout": "",
        "stderr": "validation failed\n",
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def test_timeout_command(tmp_path):
    result = run_allowed_command(
        "timeout_check",
        tmp_path,
        tmp_path,
        timeout=0.1,
    )

    assert result == {
        "returncode": None,
        "stdout": "",
        "stderr": "命令执行超时",
        "timed_out": True,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def test_unknown_command(tmp_path):
    result = run_allowed_command(
        "unknown_check",
        tmp_path,
        tmp_path,
    )

    assert result == {
        "returncode": None,
        "stdout": "",
        "stderr": "命令不在允许列表",
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def test_greeting_command(tmp_path):
    result = run_allowed_command(
        "greeting_check",
        tmp_path,
        tmp_path,
    )

    assert result == {
        "returncode": 0,
        "stdout": "hello R4\n",
        "stderr": "",
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def test_missing_cwd(tmp_path):
    missing_dir = tmp_path / "missing"

    result = run_allowed_command(
        "success_check",
        missing_dir,
        tmp_path,
    )

    assert result == {
        "returncode": None,
        "stdout": "",
        "stderr": "命令启动失败",
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def test_allowed_cwd_inside_workspace(tmp_path):
    workspace_root = tmp_path / "workspace"
    inside_dir = workspace_root / "src"
    inside_dir.mkdir(parents=True)

    assert is_allowed_cwd(inside_dir, workspace_root) is True


def test_rejects_cwd_outside_workspace(tmp_path):
    workspace_root = tmp_path / "workspace"
    outside_dir = tmp_path / "outside"
    workspace_root.mkdir()
    outside_dir.mkdir()

    assert is_allowed_cwd(outside_dir, workspace_root) is False


def test_rejects_command_outside_workspace(tmp_path):
    workspace_root = tmp_path / "workspace"
    outside_dir = tmp_path / "outside"
    workspace_root.mkdir()
    outside_dir.mkdir()

    result = run_allowed_command(
        "greeting_check",
        outside_dir,
        workspace_root,
    )

    assert result == {
        "returncode": None,
        "stdout": "",
        "stderr": "工作目录超出允许范围",
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def test_shell_metacharacters_are_literal_arguments(tmp_path):
    result = run_allowed_command(
        "literal_argument_check",
        tmp_path,
        tmp_path,
    )

    assert result == {
        "returncode":0,
        "stdout":"hello; touch injected.txt\n",
        "stderr":"",
        "timed_out":False,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }

    assert (tmp_path / "injected.txt").exists() is False


def test_truncate_text_shorter_than_limit():
    assert truncate_text("abc", 5) == {
        "text": "abc",
        "truncated": False,
    }


def test_truncate_text_equal_to_limit():
    assert truncate_text("abcde", 5) == {
        "text": "abcde",
        "truncated": False,
    }


def test_truncate_text_longer_than_limit():
    assert truncate_text("abcdefgh", 5) == {
        "text": "abcde",
        "truncated": True,
    }


def test_large_stdout_is_truncated(tmp_path):
    result = run_allowed_command("large_stdout_check", tmp_path, tmp_path)

    assert result == {
        "returncode": 0,
        "stdout": "A" * 1000,
        "stderr": "",
        "timed_out": False,
        "stdout_truncated": True,
        "stderr_truncated": False,
    }


def test_large_stderr_is_truncated(tmp_path):
    result = run_allowed_command("large_stderr_check", tmp_path, tmp_path)

    assert result == {
        "returncode": 0,
        "stdout": "",
        "stderr": "E" * 1000,
        "timed_out": False,
        "stdout_truncated": False,
        "stderr_truncated": True,
    }