"""Python language plugin.

Wraps the existing ast_parser module to implement the LanguagePlugin protocol.
Uses Python's built-in ast module — no tree-sitter needed.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..indexer import ast_parser
from .base import FileInfo, FunctionInfo, ClassInfo


class PythonPlugin:
    """Language plugin for Python using the built-in ast module."""

    @property
    def name(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> Set[str]:
        return {".py"}

    def parse_file(self, path: Path, repo_root: Path) -> FileInfo:
        info = ast_parser.parse_file(path, repo_root)
        # Convert ast_parser dataclasses to languages.base dataclasses
        functions = [
            FunctionInfo(
                name=f.name,
                file_path=f.file_path,
                start_line=f.start_line,
                end_line=f.end_line,
                signature=f.signature,
                docstring=f.docstring,
                calls=f.calls,
                is_test=f.is_test,
            )
            for f in info.functions
        ]
        classes = [
            ClassInfo(
                name=c.name,
                file_path=c.file_path,
                start_line=c.start_line,
                end_line=c.end_line,
                docstring=c.docstring,
                methods=[
                    FunctionInfo(
                        name=m.name,
                        file_path=m.file_path,
                        start_line=m.start_line,
                        end_line=m.end_line,
                        signature=m.signature,
                        docstring=m.docstring,
                        calls=m.calls,
                        is_test=m.is_test,
                    )
                    for m in c.methods
                ],
                bases=c.bases,
            )
            for c in info.classes
        ]
        return FileInfo(
            path=info.path,
            relative_path=info.relative_path,
            name=info.name,
            content_hash=info.content_hash,
            language="python",
            imports=info.imports,
            functions=functions,
            classes=classes,
            is_test_file=info.is_test_file,
        )

    def module_name(self, relative_path: str) -> str:
        normalized = relative_path.replace("\\", "/")
        if normalized.endswith(".py"):
            normalized = normalized[:-3]
        return normalized.replace("/", ".").strip(".")

    def is_test_file(self, filename: str) -> bool:
        return ast_parser.is_test_file(filename)

    def is_test_function(self, name: str) -> bool:
        return ast_parser.is_test_function(name)

    def is_test_class(self, name: str) -> bool:
        return ast_parser.is_test_class(name)

    def resolve_self_calls(self, class_name: str, call: str) -> str:
        if call.startswith("self.") or call.startswith("cls."):
            return f"{class_name}.{call.split('.', 1)[1]}"
        return call

    def test_runner_command(self, repo_path: Path, test_ids: List[str]) -> List[str]:
        return [sys.executable, "-m", "pytest", "--tb=short", "-q"] + list(test_ids)

    def parse_test_output(self, output: str) -> Dict[str, int]:
        passed = failed = errors = 0
        for line in reversed(output.splitlines()):
            line = line.strip()
            if not line:
                continue
            parts = line.replace(",", " ").split()
            for i, word in enumerate(parts):
                if word == "passed" and i > 0:
                    try:
                        passed = int(parts[i - 1])
                    except ValueError:
                        pass
                elif word == "failed" and i > 0:
                    try:
                        failed = int(parts[i - 1])
                    except ValueError:
                        pass
                elif word in ("error", "errors") and i > 0:
                    try:
                        errors = int(parts[i - 1])
                    except ValueError:
                        pass
            if "passed" in line or "failed" in line or "error" in line:
                break
        return {"passed": passed, "failed": failed, "errors": errors}

    def heuristic_test_stem(self, test_stem: str) -> Optional[str]:
        if test_stem.startswith("test_"):
            return test_stem[5:]
        if test_stem.endswith("_test"):
            return test_stem[:-5]
        return None
