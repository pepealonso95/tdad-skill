"""Go language plugin using tree-sitter."""

import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Set

from .base import FileInfo, FunctionInfo, ClassInfo
from . import _treesitter_base as tsb


# Test file patterns
_TEST_FILE_PATTERNS = ["*_test.go"]


class GoPlugin:
    """Language plugin for Go."""

    @property
    def name(self) -> str:
        return "go"

    @property
    def file_extensions(self) -> Set[str]:
        return {".go"}

    def parse_file(self, path: Path, repo_root: Path) -> FileInfo:
        source = path.read_text(encoding="utf-8", errors="replace")
        hash_val = tsb.content_hash(source)

        try:
            relative_path = str(path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            relative_path = path.name

        try:
            tree = tsb.parse_source("go", source)
        except Exception:
            return FileInfo(
                path=str(path),
                relative_path=relative_path,
                name=path.name,
                content_hash=hash_val,
                language="go",
                is_test_file=self.is_test_file(path.name),
            )

        source_bytes = source.encode("utf-8")
        root = tree.root_node

        functions: List[FunctionInfo] = []
        classes: List[ClassInfo] = []
        imports = self._collect_imports(root, source_bytes)

        is_test = self.is_test_file(path.name)

        # Track structs by name so we can attach methods later
        struct_map: Dict[str, ClassInfo] = {}

        for child in root.children:
            self._extract_node(child, source_bytes, relative_path, functions,
                               classes, struct_map, is_test)

        return FileInfo(
            path=str(path),
            relative_path=relative_path,
            name=path.name,
            content_hash=hash_val,
            language="go",
            imports=imports,
            functions=functions,
            classes=classes,
            is_test_file=is_test,
        )

    def _extract_node(self, node, source_bytes: bytes, file_path: str,
                      functions: List[FunctionInfo], classes: List[ClassInfo],
                      struct_map: Dict[str, ClassInfo], is_test_file: bool):
        """Extract functions, methods, and structs from a tree-sitter node."""
        ntype = node.type

        if ntype == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = tsb.node_text(name_node, source_bytes)
                calls = tsb.collect_calls(node, source_bytes)
                func = FunctionInfo(
                    name=name,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    signature=self._extract_signature(node, source_bytes),
                    docstring=self._extract_comment(node, source_bytes),
                    calls=calls,
                    is_test=is_test_file and self.is_test_function(name),
                )
                functions.append(func)

        elif ntype == "method_declaration":
            name_node = node.child_by_field_name("name")
            receiver_node = node.child_by_field_name("receiver")
            if name_node:
                name = tsb.node_text(name_node, source_bytes)
                calls = tsb.collect_calls(node, source_bytes)
                receiver_type = self._extract_receiver_type(
                    receiver_node, source_bytes) if receiver_node else None

                func = FunctionInfo(
                    name=name,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    signature=self._extract_signature(node, source_bytes),
                    docstring=self._extract_comment(node, source_bytes),
                    calls=calls,
                    is_test=is_test_file and self.is_test_function(name),
                )

                # Attach to struct if we already parsed it
                if receiver_type and receiver_type in struct_map:
                    struct_map[receiver_type].methods.append(func)
                else:
                    # Standalone method (struct may not have been parsed yet
                    # or receiver is a pointer to an unknown type).
                    # Still record it as a top-level function.
                    functions.append(func)

        elif ntype == "type_declaration":
            # type Foo struct { ... }
            for child in node.children:
                if child.type == "type_spec":
                    type_name_node = child.child_by_field_name("name")
                    type_body = child.child_by_field_name("type")
                    if type_name_node and type_body and type_body.type == "struct_type":
                        struct_name = tsb.node_text(type_name_node, source_bytes)
                        cls = ClassInfo(
                            name=struct_name,
                            file_path=file_path,
                            start_line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            docstring=self._extract_comment(node, source_bytes),
                            methods=[],
                            bases=[],
                        )
                        classes.append(cls)
                        struct_map[struct_name] = cls

    def _extract_receiver_type(self, receiver_node, source_bytes: bytes) -> Optional[str]:
        """Extract the receiver type name from a method receiver.

        Handles both value receivers ``(c Calculator)`` and pointer
        receivers ``(c *Calculator)``.
        """
        # The receiver is a parameter_list containing a parameter_declaration.
        for child in receiver_node.children:
            if child.type == "parameter_declaration":
                type_node = child.child_by_field_name("type")
                if type_node:
                    if type_node.type == "pointer_type":
                        # *Calculator -> get the inner type identifier
                        for inner in type_node.children:
                            if inner.type == "type_identifier":
                                return tsb.node_text(inner, source_bytes)
                    elif type_node.type == "type_identifier":
                        return tsb.node_text(type_node, source_bytes)
        return None

    def _extract_signature(self, node, source_bytes: bytes) -> str:
        """Extract function/method signature."""
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        name = tsb.node_text(name_node, source_bytes) if name_node else "anonymous"
        params = tsb.node_text(params_node, source_bytes) if params_node else "()"
        return f"{name}{params}"

    def _extract_comment(self, node, source_bytes: bytes) -> Optional[str]:
        """Extract the comment block preceding a node."""
        prev = node.prev_sibling
        if prev and prev.type == "comment":
            return tsb.node_text(prev, source_bytes)
        return None

    def _collect_imports(self, root_node, source_bytes: bytes) -> List[str]:
        """Collect import paths from Go import declarations."""
        imports: List[str] = []
        for child in root_node.children:
            if child.type == "import_declaration":
                for inner in child.children:
                    if inner.type == "import_spec_list":
                        for spec in inner.children:
                            if spec.type == "import_spec":
                                path_node = spec.child_by_field_name("path")
                                if path_node:
                                    raw = tsb.node_text(path_node, source_bytes)
                                    imports.append(raw.strip('"'))
                    elif inner.type == "import_spec":
                        path_node = inner.child_by_field_name("path")
                        if path_node:
                            raw = tsb.node_text(path_node, source_bytes)
                            imports.append(raw.strip('"'))
                    elif inner.type == "interpreted_string_literal":
                        raw = tsb.node_text(inner, source_bytes)
                        imports.append(raw.strip('"'))
        return imports

    def module_name(self, relative_path: str) -> str:
        normalized = relative_path.replace("\\", "/")
        # Strip .go extension
        if normalized.endswith(".go"):
            normalized = normalized[:-3]
        return normalized

    def is_test_file(self, filename: str) -> bool:
        return any(fnmatch(filename, p) for p in _TEST_FILE_PATTERNS)

    def is_test_function(self, name: str) -> bool:
        return name.startswith("Test") or name.startswith("Bench")

    def is_test_class(self, name: str) -> bool:
        # Go doesn't have test classes, but support the pattern
        return name.startswith("Test") or name.endswith("Suite")

    def resolve_self_calls(self, class_name: str, call: str) -> str:
        # Go doesn't have self/cls; return the call unchanged
        return call

    def test_runner_command(self, repo_path: Path, test_ids: List[str]) -> List[str]:
        """Return the command to run specific Go tests.

        Uses ``go test -run TestName -v ./pkg/...`` form.
        """
        # Build a regex pattern matching any of the given test names
        run_pattern = "|".join(test_ids)
        return ["go", "test", "-run", run_pattern, "-v", "./..."]

    def parse_test_output(self, output: str) -> Dict[str, int]:
        """Parse ``go test`` output for pass/fail/error counts.

        Recognises individual test result lines like::

            --- PASS: TestFoo (0.00s)
            --- FAIL: TestBar (0.01s)

        and package summary lines like::

            ok      example.com/pkg  0.123s
            FAIL    example.com/pkg  0.456s
        """
        passed = 0
        failed = 0
        errors = 0

        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("--- PASS:"):
                passed += 1
            elif stripped.startswith("--- FAIL:"):
                failed += 1

        return {"passed": passed, "failed": failed, "errors": errors}

    def heuristic_test_stem(self, test_stem: str) -> Optional[str]:
        # foo_test -> foo
        if test_stem.endswith("_test"):
            return test_stem[:-5]
        return None
