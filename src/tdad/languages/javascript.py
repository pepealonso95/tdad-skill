"""JavaScript/TypeScript language plugin using tree-sitter."""

import json
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Set

from .base import FileInfo, FunctionInfo, ClassInfo
from . import _treesitter_base as tsb


# Test file patterns
_TEST_FILE_PATTERNS = [
    "*.test.js", "*.spec.js", "*.test.ts", "*.spec.ts",
    "*.test.jsx", "*.spec.jsx", "*.test.tsx", "*.spec.tsx",
    "*.test.mjs", "*.spec.mjs", "*.test.cjs", "*.spec.cjs",
]

# Test function names (inside describe/it/test blocks)
_TEST_FUNCTION_NAMES = {"it", "test", "describe", "beforeEach", "afterEach",
                        "beforeAll", "afterAll", "before", "after"}


class JavaScriptPlugin:
    """Language plugin for JavaScript and TypeScript."""

    def __init__(self, variant: str = "javascript"):
        self._variant = variant  # "javascript" or "typescript"

    @property
    def name(self) -> str:
        return self._variant

    @property
    def file_extensions(self) -> Set[str]:
        if self._variant == "typescript":
            return {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
        return {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}

    def parse_file(self, path: Path, repo_root: Path) -> FileInfo:
        source = path.read_text(encoding="utf-8", errors="replace")
        hash_val = tsb.content_hash(source)

        try:
            relative_path = str(path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            relative_path = path.name

        suffix = path.suffix.lower()
        if suffix in (".ts", ".tsx"):
            ts_lang = "tsx" if suffix == ".tsx" else "typescript"
        else:
            ts_lang = "javascript"

        try:
            tree = tsb.parse_source(ts_lang, source)
        except Exception:
            return FileInfo(
                path=str(path),
                relative_path=relative_path,
                name=path.name,
                content_hash=hash_val,
                language=self._variant,
                is_test_file=self.is_test_file(path.name),
            )

        source_bytes = source.encode("utf-8")
        root = tree.root_node

        functions = []
        classes = []
        imports = tsb.collect_imports_js(root, source_bytes)

        is_test = self.is_test_file(path.name)

        # Walk top-level nodes
        for child in root.children:
            self._extract_node(child, source_bytes, relative_path, functions,
                               classes, is_test, parent_class=None)

        return FileInfo(
            path=str(path),
            relative_path=relative_path,
            name=path.name,
            content_hash=hash_val,
            language=self._variant,
            imports=imports,
            functions=functions,
            classes=classes,
            is_test_file=is_test,
        )

    def _extract_node(self, node, source_bytes: bytes, file_path: str,
                       functions: List[FunctionInfo], classes: List[ClassInfo],
                       is_test_file: bool, parent_class: Optional[str]):
        """Recursively extract functions, classes from a tree-sitter node."""
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
                    docstring=self._extract_jsdoc(node, source_bytes),
                    calls=calls,
                    is_test=is_test_file and self.is_test_function(name),
                )
                functions.append(func)

        elif ntype == "lexical_declaration" or ntype == "variable_declaration":
            # const foo = () => {} or const foo = function() {}
            for decl in node.children:
                if decl.type == "variable_declarator":
                    name_node = decl.child_by_field_name("name")
                    value_node = decl.child_by_field_name("value")
                    if name_node and value_node and value_node.type in (
                        "arrow_function", "function_expression", "function"
                    ):
                        name = tsb.node_text(name_node, source_bytes)
                        calls = tsb.collect_calls(value_node, source_bytes)
                        func = FunctionInfo(
                            name=name,
                            file_path=file_path,
                            start_line=decl.start_point[0] + 1,
                            end_line=decl.end_point[0] + 1,
                            signature=f"{name}()",
                            docstring=self._extract_jsdoc(node, source_bytes),
                            calls=calls,
                            is_test=is_test_file and self.is_test_function(name),
                        )
                        functions.append(func)

        elif ntype == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_name = tsb.node_text(name_node, source_bytes)
                bases = self._extract_bases(node, source_bytes)
                methods = []
                body = node.child_by_field_name("body")
                if body:
                    for member in body.children:
                        if member.type == "method_definition":
                            method_name_node = member.child_by_field_name("name")
                            if method_name_node:
                                method_name = tsb.node_text(method_name_node, source_bytes)
                                calls = tsb.collect_calls(member, source_bytes)
                                methods.append(FunctionInfo(
                                    name=method_name,
                                    file_path=file_path,
                                    start_line=member.start_point[0] + 1,
                                    end_line=member.end_point[0] + 1,
                                    signature=self._extract_signature(member, source_bytes),
                                    docstring=self._extract_jsdoc(member, source_bytes),
                                    calls=calls,
                                    is_test=is_test_file and self.is_test_function(method_name),
                                ))
                classes.append(ClassInfo(
                    name=class_name,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    docstring=self._extract_jsdoc(node, source_bytes),
                    methods=methods,
                    bases=bases,
                ))

        elif ntype == "expression_statement":
            # Handle describe/it/test blocks in test files
            if is_test_file and node.children:
                expr = node.children[0]
                if expr.type == "call_expression":
                    func_node = expr.child_by_field_name("function")
                    if func_node:
                        call_name = tsb.node_text(func_node, source_bytes)
                        if call_name in ("describe", "it", "test"):
                            self._extract_test_block(expr, source_bytes, file_path,
                                                     functions, is_test_file)

        # Recurse into export statements
        elif ntype in ("export_statement", "export_default_declaration"):
            for child in node.children:
                self._extract_node(child, source_bytes, file_path, functions,
                                   classes, is_test_file, parent_class)

    def _extract_test_block(self, call_node, source_bytes: bytes, file_path: str,
                            functions: List[FunctionInfo], is_test_file: bool):
        """Extract test functions from describe/it/test call expressions."""
        func_node = call_node.child_by_field_name("function")
        if not func_node:
            return
        call_name = tsb.node_text(func_node, source_bytes)
        args_node = call_node.child_by_field_name("arguments")
        if not args_node:
            return

        # Extract the test description (first string argument)
        test_desc = None
        callback = None
        for arg in args_node.children:
            if arg.type in ("string", "template_string") and test_desc is None:
                test_desc = tsb.node_text(arg, source_bytes).strip("'\"`")
            elif arg.type in ("arrow_function", "function_expression", "function"):
                callback = arg

        if call_name in ("it", "test") and test_desc:
            name = f"{call_name}:{test_desc}"
            calls = tsb.collect_calls(callback, source_bytes) if callback else []
            functions.append(FunctionInfo(
                name=name,
                file_path=file_path,
                start_line=call_node.start_point[0] + 1,
                end_line=call_node.end_point[0] + 1,
                signature=f"{call_name}('{test_desc}')",
                docstring=None,
                calls=calls,
                is_test=True,
            ))
        elif call_name == "describe" and callback:
            # Recurse into describe body to find nested it/test calls
            for child in callback.children:
                if child.type == "statement_block":
                    for stmt in child.children:
                        if stmt.type == "expression_statement" and stmt.children:
                            expr = stmt.children[0]
                            if expr.type == "call_expression":
                                self._extract_test_block(expr, source_bytes,
                                                          file_path, functions,
                                                          is_test_file)

    def _extract_signature(self, node, source_bytes: bytes) -> str:
        """Extract function signature from declaration."""
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        name = tsb.node_text(name_node, source_bytes) if name_node else "anonymous"
        params = tsb.node_text(params_node, source_bytes) if params_node else "()"
        return f"{name}{params}"

    def _extract_jsdoc(self, node, source_bytes: bytes) -> Optional[str]:
        """Extract JSDoc comment preceding a node."""
        # Look at the previous sibling for a comment
        prev = node.prev_sibling
        if prev and prev.type == "comment":
            text = tsb.node_text(prev, source_bytes)
            if text.startswith("/**"):
                return text
        return None

    def _extract_bases(self, class_node, source_bytes: bytes) -> List[str]:
        """Extract base class names from class heritage."""
        bases = []
        heritage = class_node.child_by_field_name("heritage")
        if heritage is None:
            # Look for class_heritage node in children
            for child in class_node.children:
                if child.type == "class_heritage":
                    heritage = child
                    break
        if heritage:
            for child in heritage.children:
                if child.type == "identifier" or child.type == "type_identifier":
                    bases.append(tsb.node_text(child, source_bytes))
                elif child.type == "member_expression":
                    bases.append(tsb.node_text(child, source_bytes))
        return bases

    def module_name(self, relative_path: str) -> str:
        normalized = relative_path.replace("\\", "/")
        # Strip extension
        for ext in sorted(self.file_extensions, key=len, reverse=True):
            if normalized.endswith(ext):
                normalized = normalized[:-len(ext)]
                break
        return normalized.replace("/", ".").strip(".")

    def is_test_file(self, filename: str) -> bool:
        # Check patterns
        if any(fnmatch(filename, p) for p in _TEST_FILE_PATTERNS):
            return True
        # Check __tests__ directory (handled via path, not just filename)
        return False

    def is_test_function(self, name: str) -> bool:
        # Direct test runner function names
        if name in _TEST_FUNCTION_NAMES:
            return True
        # Test descriptions from it/test blocks
        if name.startswith("it:") or name.startswith("test:"):
            return True
        return False

    def is_test_class(self, name: str) -> bool:
        # JS doesn't commonly use test classes, but support the pattern
        return name.startswith("Test") or name.endswith("Test")

    def resolve_self_calls(self, class_name: str, call: str) -> str:
        if call.startswith("this."):
            return f"{class_name}.{call[5:]}"
        return call

    def test_runner_command(self, repo_path: Path, test_ids: List[str]) -> List[str]:
        runner = self._detect_test_runner(repo_path)
        if runner == "vitest":
            return ["npx", "vitest", "run", "--reporter=verbose"] + list(test_ids)
        elif runner == "mocha":
            return ["npx", "mocha", "--reporter", "spec"] + list(test_ids)
        # Default to Jest
        return ["npx", "jest", "--verbose", "--no-coverage"] + list(test_ids)

    def _detect_test_runner(self, repo_path: Path) -> str:
        """Detect the test runner from package.json."""
        pkg_json = repo_path / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                deps = {**pkg.get("devDependencies", {}), **pkg.get("dependencies", {})}
                if "vitest" in deps:
                    return "vitest"
                if "mocha" in deps:
                    return "mocha"
                if "jest" in deps:
                    return "jest"
                # Check scripts for runner hints
                scripts = pkg.get("scripts", {})
                test_script = scripts.get("test", "")
                if "vitest" in test_script:
                    return "vitest"
                if "mocha" in test_script:
                    return "mocha"
            except (json.JSONDecodeError, OSError):
                pass
        return "jest"

    def parse_test_output(self, output: str) -> Dict[str, int]:
        """Parse Jest/Vitest/Mocha output for pass/fail/error counts."""
        passed = failed = errors = 0

        # Jest pattern: "Tests: 2 failed, 5 passed, 7 total"
        jest_match = re.search(
            r"Tests:\s*(?:(\d+)\s+failed,?\s*)?(?:(\d+)\s+passed,?\s*)?(\d+)\s+total",
            output,
        )
        if jest_match:
            failed = int(jest_match.group(1) or 0)
            passed = int(jest_match.group(2) or 0)
            return {"passed": passed, "failed": failed, "errors": errors}

        # Vitest pattern: "Tests  2 failed | 5 passed (7)"
        vitest_match = re.search(
            r"Tests\s+(?:(\d+)\s+failed\s+\|\s+)?(\d+)\s+passed",
            output,
        )
        if vitest_match:
            failed = int(vitest_match.group(1) or 0)
            passed = int(vitest_match.group(2) or 0)
            return {"passed": passed, "failed": failed, "errors": errors}

        # Mocha pattern: "N passing" / "N failing"
        passing = re.search(r"(\d+)\s+passing", output)
        failing = re.search(r"(\d+)\s+failing", output)
        if passing:
            passed = int(passing.group(1))
        if failing:
            failed = int(failing.group(1))
        return {"passed": passed, "failed": failed, "errors": errors}

    def heuristic_test_stem(self, test_stem: str) -> Optional[str]:
        # foo.test -> foo, foo.spec -> foo
        if test_stem.endswith(".test") or test_stem.endswith(".spec"):
            return test_stem.rsplit(".", 1)[0]
        # test_foo -> foo (Python-like convention sometimes used in JS)
        if test_stem.startswith("test_"):
            return test_stem[5:]
        return None
