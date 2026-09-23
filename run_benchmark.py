import json
import re
import subprocess
from pathlib import Path
import sys
import tempfile
import argparse
from evaluate_reports import (
    print_evaluation_summary,
    summarize_reports,
)
from command_tool import VERIFICATION_PROFILES

TASK_NAME_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
ALLOWED_TASK_FIELDS = {
    "name",
    "prompt",
    "files",
    "allow_edit",
    "max_steps",
    "verification_profile",
}


def load_benchmark_tasks(path: Path) -> list[dict]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(
            f"无法读取任务清单 {path}：{error}"
        ) from error

    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"任务清单不是有效 JSON：{path}"
        ) from error

    if not isinstance(document, dict):
        raise ValueError("任务清单顶层必须是 JSON 对象")

    tasks = document.get("tasks")

    if not isinstance(tasks, list) or not tasks:
        raise ValueError("任务清单 tasks 必须是非空列表")

    normalized_tasks = []
    seen_names = set()

    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise ValueError(
                f"第 {index} 个任务必须是 JSON 对象"
            )

        unsupported_fields = task.keys() - ALLOWED_TASK_FIELDS

        if unsupported_fields:
            names = ", ".join(sorted(unsupported_fields))
            raise ValueError(
                f"任务 {index} 包含不支持字段：{names}"
            )

        name = task.get("name")
        prompt = task.get("prompt")
        files = task.get("files")
        allow_edit = task.get("allow_edit", True)
        max_steps = task.get("max_steps", 8)
        verification_profile = task.get(
            "verification_profile",
            "pytest",
        )

        if (
                not isinstance(name, str)
                or not TASK_NAME_PATTERN.fullmatch(name)
        ):
            raise ValueError(
                f"任务 {index} 的 name "
                "只能包含字母、数字、下划线和连字符"
            )

        if name in seen_names:
            raise ValueError(f"任务名称重复：{name}")

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(
                f"任务 {name} 的 prompt 必须是非空字符串"
            )

        if not isinstance(files, dict) or not files:
            raise ValueError(
                f"任务 {name} 的 files 必须是非空对象"
            )

        normalized_files = {}

        for relative_path, file_content in files.items():
            if (
                    not isinstance(relative_path, str)
                    or not relative_path
            ):
                raise ValueError(
                    f"任务 {name} 包含无效文件路径"
                )

            if not isinstance(file_content, str):
                raise ValueError(
                    f"任务 {name} 的文件内容必须是字符串"
                )

            normalized_files[relative_path] = file_content

        if not isinstance(allow_edit, bool):
            raise ValueError(
                f"任务 {name} 的 allow_edit 必须是布尔值"
            )

        if (
                isinstance(max_steps, bool)
                or not isinstance(max_steps, int)
                or not 1 <= max_steps <= 20
        ):
            raise ValueError(
                f"任务 {name} 的 max_steps 必须在 1 到 20 之间"
            )

        if (
                not isinstance(verification_profile, str)
                or verification_profile
                not in VERIFICATION_PROFILES
        ):
            choices = ", ".join(VERIFICATION_PROFILES)
            raise ValueError(
                f"任务 {name} 的 verification_profile "
                f"必须是以下值之一：{choices}"
            )

        seen_names.add(name)
        normalized_tasks.append({
            "name": name,
            "prompt": prompt.strip(),
            "files": normalized_files,
            "allow_edit": allow_edit,
            "max_steps": max_steps,
            "verification_profile": verification_profile,
        })

    return normalized_tasks


def resolve_task_file(
        workspace: Path,
        relative_path: str,
) -> Path:
    path = Path(relative_path)

    if path.is_absolute():
        raise ValueError(
            f"任务文件路径不能是绝对路径：{relative_path}"
        )

    trusted_root = workspace.resolve()
    target = (trusted_root / path).resolve()

    if not target.is_relative_to(trusted_root):
        raise ValueError(
            f"任务文件路径超出临时工作区：{relative_path}"
        )

    return target


def prepare_task_workspace(
        task: dict,
        workspace: Path,
) -> None:
    workspace.mkdir()

    for relative_path, content in task["files"].items():
        target = resolve_task_file(
            workspace,
            relative_path,
        )
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        target.write_text(
            content,
            encoding="utf-8",
        )

    subprocess.run(
        ["git", "init", "-q"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Coding Agent Benchmark",
            "-c",
            "user.email=benchmark@example.invalid",
            "commit",
            "-q",
            "--no-verify",
            "-m",
            "benchmark baseline",
        ],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )


def build_cli_command(
        task: dict,
        workspace: Path,
        report_path: Path,
) -> list[str]:
    cli_path = Path(__file__).with_name("cli.py").resolve()

    command = [
        sys.executable,
        str(cli_path),
        "--workspace",
        str(workspace),
        "--max-steps",
        str(task["max_steps"]),
        "--verification-profile",
        task["verification_profile"],
        "--report-json",
        str(report_path),
    ]

    if task["allow_edit"]:
        command.append("--allow-edit")

    command.append(task["prompt"])
    return command


def run_benchmark_task(
        task: dict,
        report_path: Path,
) -> int:
    if report_path.exists() or report_path.is_symlink():
        raise ValueError(
            f"评测报告目标已存在：{report_path}"
        )

    with tempfile.TemporaryDirectory(
            prefix=f"coding-agent-{task['name']}-"
    ) as temporary_directory:
        workspace = (
                Path(temporary_directory)
                / "workspace"
        )
        prepare_task_workspace(
            task,
            workspace,
        )

        command = build_cli_command(
            task,
            workspace,
            report_path,
        )

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        print(f"\n=== 任务 {task['name']} ===")

        if result.stdout:
            print(result.stdout, end="")

        if result.stderr:
            print(result.stderr, end="")

        print(
            f"任务退出码：{result.returncode}"
        )

        return result.returncode


def run_benchmark_suite(
        tasks: list[dict],
        output_directory: Path,
) -> tuple[list[Path], list[str]]:
    if (
            output_directory.exists()
            or output_directory.is_symlink()
    ):
        raise ValueError(
            f"输出目录必须不存在：{output_directory}"
        )

    if not output_directory.parent.is_dir():
        raise ValueError("输出目录的父目录不存在")

    output_directory.mkdir()

    report_paths = []
    failed_task_names = []

    for task in tasks:
        report_path = (
                output_directory
                / f"{task['name']}.json"
        )

        return_code = run_benchmark_task(
            task,
            report_path,
        )

        if report_path.is_file():
            report_paths.append(report_path)
        else:
            failed_task_names.append(
                f"{task['name']}（没有生成报告）"
            )

        if return_code != 0:
            failed_task_names.append(task["name"])

    if not report_paths:
        raise RuntimeError("评测没有生成任何 JSON 报告")

    summary = summarize_reports(report_paths)
    print()
    print_evaluation_summary(summary)

    summary_path = output_directory / "summary.json"
    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\n评测汇总 JSON：{summary_path}")

    return report_paths, failed_task_names


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 Coding Agent 固定任务集"
    )
    parser.add_argument(
        "manifest",
        type=Path,
        help="固定任务集 JSON 清单",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="保存逐次报告和汇总的新目录",
    )
    args = parser.parse_args()

    manifest_path = args.manifest.expanduser().resolve()
    output_directory = (
        args.output_dir.expanduser().resolve()
    )

    try:
        tasks = load_benchmark_tasks(manifest_path)
        _, failed_task_names = run_benchmark_suite(
            tasks,
            output_directory,
        )
    except (
            ValueError,
            RuntimeError,
            OSError,
            subprocess.CalledProcessError,
    ) as error:
        parser.error(str(error))

    if failed_task_names:
        print(
            "\n评测失败任务："
            + ", ".join(failed_task_names)
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
