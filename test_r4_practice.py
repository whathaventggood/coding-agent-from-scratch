from r4_practice import run_allowed_command


def test_success_command(tmp_path):
    result = run_allowed_command(
        "success_check",
        tmp_path,
    )

    assert result == {
        "returncode": 0,
        "stdout": "R4 ready\n",
        "stderr": "",
        "timed_out": False,
    }


def test_failure_command(tmp_path):
    result = run_allowed_command(
        "failure_check",
        tmp_path,
    )

    assert result == {
        "returncode": 7,
        "stdout": "",
        "stderr": "validation failed\n",
        "timed_out": False,
    }


def test_timeout_command(tmp_path):
    result = run_allowed_command(
        "timeout_check",
        tmp_path,
        timeout=0.1,
    )

    assert result == {
        "returncode": None,
        "stdout": "",
        "stderr": "命令执行超时",
        "timed_out": True,
    }


def test_unknown_command(tmp_path):
    result = run_allowed_command(
        "unknown_check",
        tmp_path,
    )

    assert result == {
        "returncode": None,
        "stdout": "",
        "stderr": "命令不在允许列表",
        "timed_out": False,
    }


def test_greeting_command(tmp_path):
    result = run_allowed_command(
        "greeting_check",
        tmp_path,
    )

    assert result == {
        "returncode": 0,
        "stdout": "hello R4\n",
        "stderr": "",
        "timed_out": False,
    }


def test_missing_cwd(tmp_path):
    missing_dir = tmp_path / "missing"

    result = run_allowed_command(
        "success_check",
        missing_dir,
    )

    assert result == {
        "returncode": None,
        "stdout": "",
        "stderr": "命令启动失败",
        "timed_out": False,
    }