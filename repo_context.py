"""Read-only, best-effort Python import relations inside a trusted workspace."""

import ast
import os
from collections import defaultdict
from pathlib import Path

from file_tools import IGNORED_SYMBOL_DIRECTORIES, MAX_PYTHON_SOURCE_BYTES
from models import ToolResult


MAX_IMPORT_RELATIONS = 50
MAX_IMPORT_RELATION_CHARS = 3000


def module_names(relative_path: Path) -> list[str]:
    parts = list(relative_path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    if not parts:
        return []

    names = [".".join(parts)]
    if parts[0] == "src" and len(parts) > 1:
        names.append(".".join(parts[1:]))
    return names


def scan_python_modules(root: Path) -> tuple[dict, dict]:
    trees = {}
    modules = defaultdict(set)

    for current_root, directory_names, file_names in os.walk(
            root, followlinks=False,
    ):
        current_directory = Path(current_root)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if (
                name not in IGNORED_SYMBOL_DIRECTORIES
                and not name.endswith(".egg-info")
                and not (current_directory / name).is_symlink()
            )
        )

        for file_name in sorted(file_names):
            path = current_directory / file_name
            if path.suffix != ".py" or path.is_symlink():
                continue
            try:
                if path.stat().st_size > MAX_PYTHON_SOURCE_BYTES:
                    continue
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError,
                    ValueError, RecursionError):
                continue

            relative_path = path.relative_to(root)
            trees[relative_path] = tree
            for name in module_names(relative_path):
                modules[name].add(relative_path)

    return trees, modules


def resolve_local_module(name: str, modules: dict) -> Path | None:
    parts = name.split(".")
    for end in range(len(parts), 0, -1):
        candidates = modules.get(".".join(parts[:end]), set())
        if len(candidates) == 1:
            return next(iter(candidates))
        if len(candidates) > 1:
            return None
    return None


def import_targets(
        node: ast.Import | ast.ImportFrom,
        importer: Path,
        modules: dict,
) -> set[Path]:
    targets = set()
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    else:
        base = node.module or ""
        if node.level:
            importer_names = module_names(importer)
            if not importer_names:
                return targets
            parts = importer_names[0].split(".")
            if importer.name != "__init__.py":
                parts.pop()
            up = node.level - 1
            if up >= len(parts):
                return targets
            parts = parts[:len(parts) - up]
            base = ".".join(parts + ([base] if base else []))

        names = [
            f"{base}.{alias.name}" if base else alias.name
            for alias in node.names
            if alias.name != "*"
        ]
        if not names:
            names = [base]

    for name in names:
        if not name:
            continue
        target = resolve_local_module(name, modules)
        if target is not None and target != importer:
            targets.add(target)
    return targets


def find_python_imports(
        path: str,
        workspace_root: str,
        direction: str = "imports",
        offset: int = 0,
) -> ToolResult:
    if not isinstance(direction, str) or direction not in {
            "imports", "imported_by"
    }:
        return ToolResult("direction必须是imports或imported_by", is_error=True)
    if type(offset) is not int or offset < 0:
        return ToolResult("offset必须是非负整数", is_error=True)

    root = Path(workspace_root).resolve()
    requested = Path(path)
    if not requested.is_absolute():
        requested = root / requested
    requested = requested.resolve()
    if not requested.is_relative_to(root):
        return ToolResult("路径超出工作区", is_error=True)
    if requested.suffix != ".py" or not requested.is_file():
        return ToolResult("路径不是Python文件", is_error=True)

    trees, modules = scan_python_modules(root)
    selected = requested.relative_to(root)
    if selected not in trees:
        return ToolResult(
            "文件未被索引（可能位于跳过目录、过大或无法解析）",
            is_error=True,
        )

    relations = set()
    for importer, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for target in import_targets(node, importer, modules):
                if (
                    direction == "imports" and importer == selected
                    or direction == "imported_by" and target == selected
                ):
                    relations.add((importer, node.lineno, target))

    ordered = sorted(
        relations,
        key=lambda item: (str(item[0]), item[1], str(item[2])),
    )
    page = []
    chars = 0
    for importer, line_number, target in ordered[offset:]:
        entry = f"{importer}:{line_number}: imports {target}"
        if page and (
                len(page) >= MAX_IMPORT_RELATIONS
                or chars + len(entry) + 1 > MAX_IMPORT_RELATION_CHARS
        ):
            page.append(
                "[还有更多导入关系：保持 path 和 direction 不变，"
                f"下次传 offset={offset + len(page)}]"
            )
            return ToolResult("\n".join(page))
        page.append(entry)
        chars += len(entry) + 1

    return ToolResult("\n".join(page) if page else "未找到本地导入关系")
