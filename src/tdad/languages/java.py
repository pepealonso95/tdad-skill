"""Java language plugin using tree-sitter."""

import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Set

from .base import FileInfo, FunctionInfo, ClassInfo
from . import _treesitter_base as tsb


# Test file patterns
_TEST_FILE_PATTERNS = [
    "*Test.java",
    "Test*.java",
    "*Tests.java",
    "*TestCase.java",
]

# JUnit / TestNG annotation names that mark test methods
_TEST_ANNOTATIONS = {"Test", "ParameterizedTest", "RepeatedTest"}

# Setup/teardown annotations
_LIFECYCLE_ANNOTATIONS = {
    "BeforeEach", "AfterEach", "BeforeAll", "AfterAll",
    "Before", "After", "BeforeClass", "AfterClass",
}


def _collect_calls_java(node, source_bytes: bytes) -> List[str]:
    """Recursively collect function/method call names from a Java subtree.

    Java uses ``method_invocation`` nodes instead of ``call_expression``.
    For ``validateNumber(value)`` the node has a single ``name`` child
    (identifier).  For ``Math.min(...)`` the node has an ``object`` child
    (identifier ``Math``), a ``.``, and a ``name`` child (identifier ``min``),
    yielding ``Math.min``.
    """
    calls: List[str] = []
    _collect_java_recursive(node, source_bytes, calls)
    return calls


def _collect_java_recursive(node, source_bytes: bytes, calls: List[str]):
    if node.type == "method_invocation":
        name_node = node.child_by_field_name("name")
        obj_node = node.child_by_field_name("object")
        if name_node:
            name = tsb.node_text(name_node, source_bytes)
            if obj_node:
                obj_text = tsb.node_text(obj_node, source_bytes)
                calls.append(f"{obj_text}.{name}")
            else:
                calls.append(name)
    elif node.type == "object_creation_expression":
        type_node = node.child_by_field_name("type")
        if type_node:
            calls.append(f"new {tsb.node_text(type_node, source_bytes)}")
    for child in node.children:
        _collect_java_recursive(child, source_bytes, calls)


class JavaPlugin:
    """Language plugin for Java."""

    @property
    def name(self) -> str:
        return "java"

    @property
    def file_extensions(self) -> Set[str]:
        return {".java"}

    def parse_file(self, path: Path, repo_root: Path) -> FileInfo:
        source = path.read_text(encoding="utf-8", errors="replace")
        hash_val = tsb.content_hash(source)

        try:
            relative_path = str(path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            relative_path = path.name

        try:
            tree = tsb.parse_source("java", source)
        except Exception:
            return FileInfo(
                path=str(path),
                relative_path=relative_path,
                name=path.name,
                content_hash=hash_val,
                language="java",
                is_test_file=self.is_test_file(path.name),
            )

        source_bytes = source.encode("utf-8")
        root = tree.root_node

        functions: List[FunctionInfo] = []
        classes: List[ClassInfo] = []
        imports: List[str] = []
        package_name: Optional[str] = None

        is_test = self.is_test_file(path.name)

        # Walk top-level nodes
        for child in root.children:
            if child.type == "package_declaration":
                package_name = self._extract_package(child, source_bytes)
            elif child.type == "import_declaration":
                imp = self._extract_import(child, source_bytes)
                if imp:
                    imports.append(imp)
            elif child.type == "class_declaration":
                self._extract_class(
                    child, source_bytes, relative_path,
                    functions, classes, is_test,
                )
            elif child.type == "interface_declaration":
                self._extract_class(
                    child, source_bytes, relative_path,
                    functions, classes, is_test,
                )

        return FileInfo(
            path=str(path),
            relative_path=relative_path,
            name=path.name,
            content_hash=hash_val,
            language="java",
            imports=imports,
            functions=functions,
            classes=classes,
            is_test_file=is_test,
        )

    # ------------------------------------------------------------------ #
    # Extraction helpers
    # ------------------------------------------------------------------ #

    def _extract_package(self, node, source_bytes: bytes) -> Optional[str]:
        """Extract the package name from a package_declaration node."""
        for child in node.children:
            if child.type == "scoped_identifier" or child.type == "identifier":
                return tsb.node_text(child, source_bytes)
        return None

    def _extract_import(self, node, source_bytes: bytes) -> Optional[str]:
        """Extract the import path from an import_declaration node."""
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier"):
                return tsb.node_text(child, source_bytes)
        return None

    def _extract_class(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        functions: List[FunctionInfo],
        classes: List[ClassInfo],
        is_test_file: bool,
    ):
        """Extract a class/interface and its methods."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        class_name = tsb.node_text(name_node, source_bytes)
        bases = self._extract_bases(node, source_bytes)
        methods: List[FunctionInfo] = []

        body = node.child_by_field_name("body")
        if body:
            for member in body.children:
                if member.type == "method_declaration":
                    self._extract_method(
                        member, source_bytes, file_path,
                        methods, is_test_file,
                    )
                elif member.type == "constructor_declaration":
                    self._extract_constructor(
                        member, source_bytes, file_path, methods,
                    )
                elif member.type == "class_declaration":
                    # Inner class — recurse
                    self._extract_class(
                        member, source_bytes, file_path,
                        functions, classes, is_test_file,
                    )

        classes.append(ClassInfo(
            name=class_name,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=self._extract_javadoc(node, source_bytes),
            methods=methods,
            bases=bases,
        ))

    def _extract_method(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        methods: List[FunctionInfo],
        is_test_file: bool,
    ):
        """Extract a method_declaration into a FunctionInfo."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        method_name = tsb.node_text(name_node, source_bytes)
        calls = _collect_calls_java(node, source_bytes)

        has_test_annotation = self._has_annotation(node, source_bytes, _TEST_ANNOTATIONS)
        is_test_method = has_test_annotation or (
            is_test_file and self.is_test_function(method_name)
        )

        methods.append(FunctionInfo(
            name=method_name,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._extract_signature(node, source_bytes),
            docstring=self._extract_javadoc(node, source_bytes),
            calls=calls,
            is_test=is_test_method,
        ))

    def _extract_constructor(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        methods: List[FunctionInfo],
    ):
        """Extract a constructor_declaration into a FunctionInfo."""
        name_node = node.child_by_field_name("name")
        name = tsb.node_text(name_node, source_bytes) if name_node else "constructor"
        calls = _collect_calls_java(node, source_bytes)

        methods.append(FunctionInfo(
            name=name,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._extract_signature(node, source_bytes),
            docstring=self._extract_javadoc(node, source_bytes),
            calls=calls,
            is_test=False,
        ))

    def _extract_signature(self, node, source_bytes: bytes) -> str:
        """Build a human-readable signature from a method/constructor node."""
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        name = tsb.node_text(name_node, source_bytes) if name_node else "unknown"
        params = tsb.node_text(params_node, source_bytes) if params_node else "()"

        # Include return type for methods
        type_node = node.child_by_field_name("type")
        if type_node:
            ret_type = tsb.node_text(type_node, source_bytes)
            return f"{ret_type} {name}{params}"
        return f"{name}{params}"

    def _extract_javadoc(self, node, source_bytes: bytes) -> Optional[str]:
        """Extract Javadoc comment preceding a node."""
        prev = node.prev_sibling
        if prev and prev.type == "block_comment":
            text = tsb.node_text(prev, source_bytes)
            if text.startswith("/**"):
                return text
        return None

    def _extract_bases(self, class_node, source_bytes: bytes) -> List[str]:
        """Extract superclass and interface names."""
        bases: List[str] = []
        superclass = class_node.child_by_field_name("superclass")
        if superclass:
            # superclass is a `superclass` node containing a type_identifier
            for child in superclass.children:
                if child.type == "type_identifier":
                    bases.append(tsb.node_text(child, source_bytes))
        interfaces = class_node.child_by_field_name("interfaces")
        if interfaces:
            # interfaces is a `super_interfaces` node containing type_list
            for child in interfaces.children:
                if child.type == "type_list":
                    for type_child in child.children:
                        if type_child.type == "type_identifier":
                            bases.append(tsb.node_text(type_child, source_bytes))
                elif child.type == "type_identifier":
                    bases.append(tsb.node_text(child, source_bytes))
        return bases

    def _has_annotation(
        self, node, source_bytes: bytes, annotation_names: Set[str],
    ) -> bool:
        """Check if a node has any of the given annotations in its modifiers."""
        modifiers = node.child_by_field_name("modifiers")
        if not modifiers:
            # Some tree-sitter-java versions put modifiers as regular children
            for child in node.children:
                if child.type == "modifiers":
                    modifiers = child
                    break
        if not modifiers:
            return False

        for child in modifiers.children:
            if child.type == "marker_annotation":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    # Fallback: walk children for identifier
                    for sub in child.children:
                        if sub.type == "identifier":
                            name_node = sub
                            break
                if name_node:
                    ann_name = tsb.node_text(name_node, source_bytes)
                    if ann_name in annotation_names:
                        return True
            elif child.type == "annotation":
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    for sub in child.children:
                        if sub.type == "identifier":
                            name_node = sub
                            break
                if name_node:
                    ann_name = tsb.node_text(name_node, source_bytes)
                    if ann_name in annotation_names:
                        return True
        return False

    # ------------------------------------------------------------------ #
    # Protocol methods
    # ------------------------------------------------------------------ #

    def module_name(self, relative_path: str, source: Optional[str] = None) -> str:
        """Derive module name from source package declaration or path.

        If *source* is provided, the ``package`` statement is parsed from it.
        Otherwise falls back to converting the directory path to a dotted name.
        """
        if source:
            m = re.search(r"^\s*package\s+([\w.]+)\s*;", source, re.MULTILINE)
            if m:
                return m.group(1)

        # Fallback: derive from relative path
        normalized = relative_path.replace("\\", "/")
        # Strip .java extension
        if normalized.endswith(".java"):
            normalized = normalized[:-5]
        # Strip common source roots
        for prefix in ("src/main/java/", "src/test/java/"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break
        return normalized.replace("/", ".").strip(".")

    def is_test_file(self, filename: str) -> bool:
        return any(fnmatch(filename, p) for p in _TEST_FILE_PATTERNS)

    def is_test_function(self, name: str) -> bool:
        # Common JUnit naming conventions
        if name.startswith("test"):
            return True
        return False

    def is_test_class(self, name: str) -> bool:
        return (
            name.endswith("Test")
            or name.endswith("Tests")
            or name.endswith("TestCase")
            or name.startswith("Test")
        )

    def resolve_self_calls(self, class_name: str, call: str) -> str:
        if call.startswith("this."):
            return f"{class_name}.{call[5:]}"
        return call

    def test_runner_command(self, repo_path: Path, test_ids: List[str]) -> List[str]:
        runner = self._detect_build_tool(repo_path)
        if runner == "gradle":
            cmd = ["gradle", "test"]
            for tid in test_ids:
                cmd.extend(["--tests", tid])
            return cmd
        # Default to Maven
        test_arg = ",".join(test_ids)
        return ["mvn", "test", f"-Dtest={test_arg}"]

    def _detect_build_tool(self, repo_path: Path) -> str:
        """Detect Maven vs Gradle by checking build files."""
        if (repo_path / "build.gradle").exists():
            return "gradle"
        if (repo_path / "build.gradle.kts").exists():
            return "gradle"
        # Default to Maven (pom.xml or fallback)
        return "maven"

    def parse_test_output(self, output: str) -> Dict[str, int]:
        """Parse Maven Surefire or Gradle test output for pass/fail/error counts."""
        passed = failed = errors = 0

        # Maven Surefire pattern:
        #   Tests run: 5, Failures: 1, Errors: 0, Skipped: 0
        maven_match = re.search(
            r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)",
            output,
        )
        if maven_match:
            total = int(maven_match.group(1))
            failed = int(maven_match.group(2))
            errors = int(maven_match.group(3))
            passed = total - failed - errors
            return {"passed": passed, "failed": failed, "errors": errors}

        # Gradle pattern:
        #   3 tests completed, 1 failed
        gradle_match = re.search(
            r"(\d+)\s+tests?\s+completed,\s+(\d+)\s+failed",
            output,
        )
        if gradle_match:
            total = int(gradle_match.group(1))
            failed = int(gradle_match.group(2))
            passed = total - failed
            return {"passed": passed, "failed": failed, "errors": errors}

        # Gradle success (no failures line):
        #   3 tests completed
        gradle_success = re.search(r"(\d+)\s+tests?\s+completed", output)
        if gradle_success:
            passed = int(gradle_success.group(1))
            return {"passed": passed, "failed": 0, "errors": 0}

        return {"passed": passed, "failed": failed, "errors": errors}

    def heuristic_test_stem(self, test_stem: str) -> Optional[str]:
        """Map test file stem to likely source file stem.

        FooTest -> Foo, TestFoo -> Foo, FooTests -> Foo, FooTestCase -> Foo.
        """
        if test_stem.endswith("TestCase"):
            return test_stem[:-8] or None
        if test_stem.endswith("Tests"):
            return test_stem[:-5] or None
        if test_stem.endswith("Test"):
            return test_stem[:-4] or None
        if test_stem.startswith("Test"):
            return test_stem[4:] or None
        return None
