import importlib.util
import json
from pathlib import Path
import subprocess


SCRIPT = Path(__file__).parent / "docs" / "verify_real_repo_demo.py"
spec = importlib.util.spec_from_file_location("verify_real_repo_demo", SCRIPT)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_demo_verifier_checks_report_and_actual_workspace(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    (workspace / "file_tools.py").write_text("value = 1\n", encoding="utf-8")
    (workspace / "test_smoke.py").write_text(
        "from file_tools import value\n\ndef test_value():\n    assert value == 2\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=workspace, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Demo", "-c", "user.email=demo@example.invalid",
         "commit", "-q", "-m", "baseline"],
        cwd=workspace, check=True,
    )
    (workspace / "file_tools.py").write_text("value = 2\n", encoding="utf-8")
    report = tmp_path / "repair.json"
    report.write_text(json.dumps({
        "status": "success",
        "verification": {"is_error": False},
        "workspace": str(workspace),
        "workspace_changes": {
            "created": [], "modified": ["file_tools.py"], "deleted": [],
        },
        "rollback": None,
    }), encoding="utf-8")

    assert demo.verify_demo(report, workspace) == []
    (workspace / "unexpected.txt").write_text("extra\n", encoding="utf-8")
    assert any(
        "非目标文件变化" in error
        for error in demo.verify_demo(report, workspace)
    )
