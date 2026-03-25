"""Dart language plugin using tree-sitter."""

import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Set

from .base import FileInfo, FunctionInfo, ClassInfo
from . import _treesitter_base as tsb


# Test file patterns
_TEST_FILE_PATTERNS = ["*_test.dart", "test_*.dart"]

# Test function names used inside test files
_TEST_CALL_NAMES = {"test", "testWidgets", "group", "setUp", "tearDown",
                    "setUpAll", "tearDownAll"}


class DartPlugin:
    """Language plugin for Dart."""

    @property
    def name(self) -> str:
        return "dart"

    @property
    def file_extensions(self) -> Set[str]:
        return {".dart"}

    def parse_file(self, path: Path, repo_root: Path) -> FileInfo:
        source = path.read_text(encoding="utf-8", errors="replace")
        hash_val = tsb.content_hash(source)

        try:
            relative_path = str(path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            relative_path = path.name

        try:
            tree = tsb.parse_source("dart", source)
        except Exception:
            return FileInfo(
                path=str(path),
                relative_path=relative_path,
                name=path.name,
                content_hash=hash_val,
                language="dart",
                is_test_file=self.is_test_file(path.name),
            )

        source_bytes = source.encode("utf-8")
        root = tree.root_node

        functions: List[FunctionInfo] = []
        classes: List[ClassInfo] = []
        imports = self._collect_imports(root, source_bytes)

        is_test = self.is_test_file(path.name)

        # Walk top-level nodes
        i = 0
        children = root.children
        while i < len(children):
            node = children[i]

            if node.type == "function_signature":
                # Top-level function: function_signature followed by function_body
                body_node = children[i + 1] if i + 1 < len(children) and children[i + 1].type == "function_body" else None
                doc = self._extract_doc_comment(children, i, source_bytes)
                func = self._extract_function(node, body_node, source_bytes, relative_path, is_test, doc)
                if func:
                    functions.append(func)
                if body_node:
                    # Extract test blocks from inside main() in test files
                    if is_test and func and func.name == "main" and body_node:
                        self._extract_test_blocks(body_node, source_bytes, relative_path, functions)
                    i += 1  # skip the body node

            elif node.type == "class_definition":
                cls = self._extract_class(node, source_bytes, relative_path, is_test)
                if cls:
                    classes.append(cls)

            i += 1

        return FileInfo(
            path=str(path),
            relative_path=relative_path,
            name=path.name,
            content_hash=hash_val,
            language="dart",
            imports=imports,
            functions=functions,
            classes=classes,
            is_test_file=is_test,
        )

    def _extract_function(
        self,
        sig_node,
        body_node,
        source_bytes: bytes,
        file_path: str,
        is_test_file: bool,
        docstring: Optional[str] = None,
    ) -> Optional[FunctionInfo]:
        """Extract a function from function_signature + function_body pair."""
        name_node = sig_node.child_by_field_name("name")
        if not name_node:
            # Try direct child lookup
            for child in sig_node.children:
                if child.type == "identifier":
                    name_node = child
                    break
        if not name_node:
            return None

        name = tsb.node_text(name_node, source_bytes)
        calls = self._collect_calls(body_node, source_bytes) if body_node else []
        signature = self._build_signature(sig_node, source_bytes)

        return FunctionInfo(
            name=name,
            file_path=file_path,
            start_line=sig_node.start_point[0] + 1,
            end_line=(body_node.end_point[0] + 1) if body_node else (sig_node.end_point[0] + 1),
            signature=signature,
            docstring=docstring,
            calls=calls,
            is_test=is_test_file and self.is_test_function(name),
        )

    def _extract_class(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        is_test_file: bool,
    ) -> Optional[ClassInfo]:
        """Extract a class_definition."""
        name_node = None
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break
        if not name_node:
            return None

        class_name = tsb.node_text(name_node, source_bytes)
        bases = self._extract_bases(node, source_bytes)
        docstring = self._get_preceding_doc(node, source_bytes)

        methods: List[FunctionInfo] = []
        body = None
        for child in node.children:
            if child.type == "class_body":
                body = child
                break

        if body:
            body_children = body.children
            j = 0
            while j < len(body_children):
                child = body_children[j]

                if child.type == "method_signature":
                    # method_signature followed by function_body
                    method_body = body_children[j + 1] if j + 1 < len(body_children) and body_children[j + 1].type == "function_body" else None
                    doc = self._extract_doc_comment(body_children, j, source_bytes)

                    # Find the inner function_signature
                    inner_sig = None
                    for sub in child.children:
                        if sub.type == "function_signature":
                            inner_sig = sub
                            break
                    if inner_sig:
                        func = self._extract_function(inner_sig, method_body, source_bytes, file_path, is_test_file, doc)
                        if func:
                            methods.append(func)
                    if method_body:
                        j += 1

                elif child.type == "declaration":
                    # Could be a constructor or field
                    for sub in child.children:
                        if sub.type == "constructor_signature":
                            ctor = self._extract_constructor(sub, source_bytes, file_path)
                            if ctor:
                                methods.append(ctor)

                j += 1

        return ClassInfo(
            name=class_name,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=docstring,
            methods=methods,
            bases=bases,
        )

    def _extract_constructor(
        self,
        sig_node,
        source_bytes: bytes,
        file_path: str,
    ) -> Optional[FunctionInfo]:
        """Extract a constructor from constructor_signature."""
        parts = []
        for child in sig_node.children:
            if child.type == "identifier":
                parts.append(tsb.node_text(child, source_bytes))
            elif child.type == ".":
                continue
        name = ".".join(parts) if parts else "constructor"

        params_node = None
        for child in sig_node.children:
            if child.type == "formal_parameter_list":
                params_node = child
                break

        params = tsb.node_text(params_node, source_bytes) if params_node else "()"
        return FunctionInfo(
            name=name,
            file_path=file_path,
            start_line=sig_node.start_point[0] + 1,
            end_line=sig_node.end_point[0] + 1,
            signature=f"{name}{params}",
            docstring=None,
            calls=[],
            is_test=False,
        )

    def _extract_test_blocks(
        self,
        body_node,
        source_bytes: bytes,
        file_path: str,
        functions: List[FunctionInfo],
    ):
        """Recursively extract test/group/testWidgets calls from a function body."""
        self._walk_for_test_calls(body_node, source_bytes, file_path, functions)

    def _walk_for_test_calls(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        functions: List[FunctionInfo],
    ):
        """Walk tree looking for test()/testWidgets()/group() calls."""
        children = node.children
        i = 0
        while i < len(children):
            child = children[i]

            if child.type == "expression_statement":
                # Pattern: identifier selector(args)
                self._try_extract_test_call(child, source_bytes, file_path, functions)

            # Recurse into blocks, arguments, etc.
            if child.type in ("block", "argument", "arguments", "argument_part",
                              "function_expression_body", "function_body"):
                self._walk_for_test_calls(child, source_bytes, file_path, functions)

            i += 1

    def _try_extract_test_call(
        self,
        expr_stmt,
        source_bytes: bytes,
        file_path: str,
        functions: List[FunctionInfo],
    ):
        """Try to extract a test/group/testWidgets call from an expression_statement."""
        children = expr_stmt.children
        if not children:
            return

        # First child should be identifier
        ident = children[0]
        if ident.type != "identifier":
            return

        call_name = tsb.node_text(ident, source_bytes)
        if call_name not in ("test", "testWidgets", "group"):
            return

        # Find the argument_part in selectors
        test_desc = None
        callback_node = None
        for child in children:
            if child.type == "selector":
                arg_part = None
                for sub in child.children:
                    if sub.type == "argument_part":
                        arg_part = sub
                        break
                if arg_part:
                    args_node = None
                    for sub in arg_part.children:
                        if sub.type == "arguments":
                            args_node = sub
                            break
                    if args_node:
                        for arg in args_node.children:
                            if arg.type == "argument":
                                arg_children = arg.children
                                if arg_children:
                                    inner = arg_children[0]
                                    if inner.type == "string_literal" and test_desc is None:
                                        raw = tsb.node_text(inner, source_bytes)
                                        test_desc = raw.strip("'\"")
                                    elif inner.type == "function_expression":
                                        callback_node = inner

        if call_name in ("test", "testWidgets") and test_desc:
            calls = self._collect_calls(callback_node, source_bytes) if callback_node else []
            functions.append(FunctionInfo(
                name=f"{call_name}:{test_desc}",
                file_path=file_path,
                start_line=expr_stmt.start_point[0] + 1,
                end_line=expr_stmt.end_point[0] + 1,
                signature=f"{call_name}('{test_desc}')",
                docstring=None,
                calls=calls,
                is_test=True,
            ))
        elif call_name == "group" and callback_node:
            # Recurse into group callback body
            self._walk_for_test_calls(callback_node, source_bytes, file_path, functions)

    def _collect_calls(self, node, source_bytes: bytes) -> List[str]:
        """Collect function/method call names from a subtree.

        Dart calls are: identifier + selector chain.
        A selector with argument_part means it's a call.
        A selector with .identifier means member access.
        """
        if node is None:
            return []
        calls: List[str] = []
        self._collect_calls_recursive(node, source_bytes, calls)
        return calls

    def _collect_calls_recursive(self, node, source_bytes: bytes, calls: List[str]):
        """Walk the tree collecting Dart call expressions."""
        children = node.children
        i = 0
        while i < len(children):
            child = children[i]

            if child.type == "identifier":
                # Check if this identifier is followed by selectors that include argument_part
                parts = [tsb.node_text(child, source_bytes)]
                j = i + 1
                has_args = False
                while j < len(children) and children[j].type == "selector":
                    sel = children[j]
                    # Check for .member
                    for sub in sel.children:
                        if sub.type == "unconditional_assignable_selector":
                            for inner in sub.children:
                                if inner.type == "identifier":
                                    parts.append(tsb.node_text(inner, source_bytes))
                        elif sub.type == "argument_part":
                            has_args = True
                    j += 1
                if has_args:
                    calls.append(".".join(parts))
                    i = j
                    continue

            # Recurse into child nodes
            self._collect_calls_recursive(child, source_bytes, calls)
            i += 1

    def _collect_imports(self, root_node, source_bytes: bytes) -> List[str]:
        """Collect import URIs from Dart import statements."""
        imports = []
        for child in root_node.children:
            if child.type == "import_or_export":
                for sub in child.children:
                    if sub.type == "library_import":
                        for inner in sub.children:
                            if inner.type == "import_specification":
                                for spec_child in inner.children:
                                    if spec_child.type == "configurable_uri":
                                        raw = tsb.node_text(spec_child, source_bytes)
                                        imports.append(raw.strip("'\""))
        return imports

    def _extract_bases(self, class_node, source_bytes: bytes) -> List[str]:
        """Extract superclass, mixins, and interfaces."""
        bases = []
        for child in class_node.children:
            if child.type == "superclass":
                for sub in child.children:
                    if sub.type == "type_identifier":
                        bases.append(tsb.node_text(sub, source_bytes))
                # Also check mixins within superclass
                for sub in child.children:
                    if sub.type == "mixins":
                        for inner in sub.children:
                            if inner.type == "type_identifier":
                                bases.append(tsb.node_text(inner, source_bytes))
            elif child.type == "interfaces":
                for sub in child.children:
                    if sub.type == "type_identifier":
                        bases.append(tsb.node_text(sub, source_bytes))
        return bases

    def _build_signature(self, sig_node, source_bytes: bytes) -> str:
        """Build human-readable signature from a function_signature node."""
        name = None
        params = "()"
        ret_type = None
        for child in sig_node.children:
            if child.type == "identifier":
                name = tsb.node_text(child, source_bytes)
            elif child.type == "formal_parameter_list":
                params = tsb.node_text(child, source_bytes)
            elif child.type in ("type_identifier", "void_type"):
                ret_type = tsb.node_text(child, source_bytes)
        if ret_type and name:
            return f"{ret_type} {name}{params}"
        elif name:
            return f"{name}{params}"
        return tsb.node_text(sig_node, source_bytes)

    def _extract_doc_comment(self, siblings: list, index: int, source_bytes: bytes) -> Optional[str]:
        """Check if the node at index is preceded by a documentation_comment."""
        if index > 0:
            prev = siblings[index - 1]
            if prev.type == "documentation_comment":
                return tsb.node_text(prev, source_bytes)
        return None

    def _get_preceding_doc(self, node, source_bytes: bytes) -> Optional[str]:
        """Get doc comment preceding a node via prev_sibling."""
        prev = node.prev_sibling
        if prev and prev.type == "documentation_comment":
            return tsb.node_text(prev, source_bytes)
        return None

    def module_name(self, relative_path: str) -> str:
        normalized = relative_path.replace("\\", "/")
        # Strip lib/ prefix (Dart convention)
        if normalized.startswith("lib/"):
            normalized = normalized[4:]
        if normalized.endswith(".dart"):
            normalized = normalized[:-5]
        return normalized.replace("/", ".").strip(".")

    def is_test_file(self, filename: str) -> bool:
        return any(fnmatch(filename, p) for p in _TEST_FILE_PATTERNS)

    def is_test_function(self, name: str) -> bool:
        if name in _TEST_CALL_NAMES:
            return True
        if name.startswith("test:") or name.startswith("testWidgets:"):
            return True
        return False

    def is_test_class(self, name: str) -> bool:
        return name.endswith("Test") or name.startswith("Test")

    def resolve_self_calls(self, class_name: str, call: str) -> str:
        if call.startswith("this."):
            return f"{class_name}.{call[5:]}"
        return call

    def test_runner_command(self, repo_path: Path, test_ids: List[str]) -> List[str]:
        # Detect Flutter vs plain Dart
        if (repo_path / "pubspec.yaml").exists():
            pubspec = (repo_path / "pubspec.yaml").read_text(errors="replace")
            if "flutter:" in pubspec or "flutter_test:" in pubspec:
                return ["flutter", "test", "--reporter=expanded"] + list(test_ids)
        return ["dart", "test", "--reporter=expanded"] + list(test_ids)

    def parse_test_output(self, output: str) -> Dict[str, int]:
        """Parse dart test / flutter test output."""
        passed = failed = errors = 0

        # Pattern: "+N: All tests passed!" or "+N -M: Some tests failed."
        # Also: "00:05 +10 -2: Some tests failed."
        summary = re.search(r'\+(\d+)(?:\s+-(\d+))?:', output)
        if summary:
            passed = int(summary.group(1))
            failed = int(summary.group(2) or 0)
            return {"passed": passed, "failed": failed, "errors": errors}

        # Fallback: count individual lines
        for line in output.splitlines():
            if re.match(r'\s*\+\d+:', line) and 'passed' in line.lower():
                m = re.search(r'\+(\d+)', line)
                if m:
                    passed = int(m.group(1))
            if re.match(r'\s*-\d+:', line) or 'failed' in line.lower():
                m = re.search(r'-(\d+)', line)
                if m:
                    failed = int(m.group(1))

        return {"passed": passed, "failed": failed, "errors": errors}

    def heuristic_test_stem(self, test_stem: str) -> Optional[str]:
        # calculator_test -> calculator
        if test_stem.endswith("_test"):
            return test_stem[:-5]
        # test_calculator -> calculator
        if test_stem.startswith("test_"):
            return test_stem[5:]
        return None
