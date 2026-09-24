"""Independently check the synthetic full-repository repair demo."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def verify_demo(report_path: Path, workspace: Path) -> list[str]:
    errors = []
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"无法读取 JSON 报告：{error}"]

    if not isinstance(report, dict):
        return ["JSON 报告顶层必须是对象"]
    if report.get("status") != "success":
        errors.append("Agent/CLI 最终状态不是 success")
    verification = report.get("verification")
    if not isinstance(verification, dict) or verification.get("is_error") is not False:
        errors.append("CLI 独立复验未通过")
    if report.get("workspace") != str(workspace):
        errors.append("报告中的工作区与指定演示副本不一致")
    if report.get("workspace_changes") != {
        "created": [], "modified": ["file_tools.py"], "deleted": [],
    }:
        errors.append("任务前后变化不是仅修改 file_tools.py")
    rollback = report.get("rollback")
    if rollback is not None:
        errors.append("演示发生过失败回滚")

    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=workspace,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if Path(root).resolve() != workspace:
            errors.append("指定目录不是 Git 仓库根目录")
        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"], cwd=workspace,
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=workspace, capture_output=True, text=True, check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as error:
        return errors + [f"无法检查演示副本的 Git 状态：{error}"]

    unexpected = sorted((set(changed) | set(untracked)) - {"file_tools.py"})
    if unexpected:
        errors.append("演示副本存在非目标文件变化：" + ", ".join(unexpected))

    try:
        with tempfile.TemporaryDirectory(prefix="agent-demo-pycache-") as cache:
            check = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"], cwd=workspace,
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "PYTHONPYCACHEPREFIX": cache},
            )
        if check.returncode != 0:
            errors.append(
                "验收器重新运行完整 pytest 未通过：\n"
                + (check.stdout + check.stderr)[-2000:]
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append(f"验收器无法完成完整 pytest：{error}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="独立验收完整仓库合成回归修复演示")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    errors = verify_demo(args.report.expanduser().resolve(), workspace)
    if errors:
        for error in errors:
            print(f"未通过：{error}")
        raise SystemExit(1)
    print("演示验收通过：任务前后仅修改 file_tools.py，CLI 复验与再次完整复验均通过。")


if __name__ == "__main__":
    main()
