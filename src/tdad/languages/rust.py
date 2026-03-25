"""Rust language plugin using tree-sitter."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from .base import FileInfo, FunctionInfo, ClassInfo
from . import _treesitter_base as tsb


class RustPlugin:
    """Language plugin for Rust."""

    @property
    def name(self) -> str:
        return "rust"

    @property
    def file_extensions(self) -> Set[str]:
        return {".rs"}

    def parse_file(self, path: Path, repo_root: Path) -> FileInfo:
        source = path.read_text(encoding="utf-8", errors="replace")
        hash_val = tsb.content_hash(source)

        try:
            relative_path = str(path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            relative_path = path.name

        try:
            tree = tsb.parse_source("rust", source)
        except Exception:
            return FileInfo(
                path=str(path),
                relative_path=relative_path,
                name=path.name,
                content_hash=hash_val,
                language="rust",
                is_test_file=self.is_test_file(path.name),
            )

        source_bytes = source.encode("utf-8")
        root = tree.root_node

        functions: List[FunctionInfo] = []
        classes: List[ClassInfo] = []
        imports = self._collect_imports(root, source_bytes)

        is_test = self.is_test_file(path.name)

        # Walk top-level nodes
        for child in root.children:
            self._extract_node(
                child, source_bytes, relative_path, functions,
                classes, is_test, pending_attrs=[],
            )

        return FileInfo(
            path=str(path),
            relative_path=relative_path,
            name=path.name,
            content_hash=hash_val,
            language="rust",
            imports=imports,
            functions=functions,
            classes=classes,
            is_test_file=is_test,
        )

    # ------------------------------------------------------------------
    # Tree-sitter extraction helpers
    # ------------------------------------------------------------------

    def _extract_node(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        functions: List[FunctionInfo],
        classes: List[ClassInfo],
        is_test_file: bool,
        pending_attrs: List[str],
    ):
        """Recursively extract functions, structs, enums, and impl blocks."""
        ntype = node.type

        if ntype == "attribute_item":
            # Accumulate attribute text for the *next* sibling
            pending_attrs.append(tsb.node_text(node, source_bytes))
            return

        attr_text = " ".join(pending_attrs)
        # Clear pending after consumption
        pending_attrs.clear()

        if ntype == "function_item":
            self._extract_function(
                node, source_bytes, file_path, functions,
                is_test_file, attr_text,
            )

        elif ntype in ("struct_item", "enum_item"):
            self._extract_struct_or_enum(
                node, source_bytes, file_path, classes, attr_text,
            )

        elif ntype == "impl_item":
            self._extract_impl(
                node, source_bytes, file_path, functions, classes,
                is_test_file, attr_text,
            )

        elif ntype == "mod_item":
            self._extract_mod(
                node, source_bytes, file_path, functions, classes,
                is_test_file, attr_text,
            )

    def _extract_function(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        functions: List[FunctionInfo],
        is_test_file: bool,
        attr_text: str,
    ):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = tsb.node_text(name_node, source_bytes)
        calls = tsb.collect_calls(node, source_bytes)
        is_test_fn = _has_test_attr(attr_text)
        func = FunctionInfo(
            name=name,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._extract_signature(node, source_bytes),
            docstring=self._extract_doc_comment(node, source_bytes),
            calls=calls,
            is_test=is_test_fn,
        )
        functions.append(func)

    def _extract_struct_or_enum(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        classes: List[ClassInfo],
        attr_text: str,
    ):
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = tsb.node_text(name_node, source_bytes)
        classes.append(ClassInfo(
            name=name,
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=self._extract_doc_comment(node, source_bytes),
            methods=[],
            bases=[],
        ))

    def _extract_impl(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        functions: List[FunctionInfo],
        classes: List[ClassInfo],
        is_test_file: bool,
        attr_text: str,
    ):
        # Get the type being implemented
        type_node = node.child_by_field_name("type")
        if not type_node:
            return
        impl_type = tsb.node_text(type_node, source_bytes)

        # Check if there is a trait being implemented
        trait_node = node.child_by_field_name("trait")
        bases = []
        if trait_node:
            bases.append(tsb.node_text(trait_node, source_bytes))

        body = node.child_by_field_name("body")
        if not body:
            return

        methods: List[FunctionInfo] = []
        pending_attrs: List[str] = []
        for child in body.children:
            if child.type == "attribute_item":
                pending_attrs.append(tsb.node_text(child, source_bytes))
                continue

            if child.type == "function_item":
                child_attr_text = " ".join(pending_attrs)
                pending_attrs.clear()
                method_name_node = child.child_by_field_name("name")
                if method_name_node:
                    method_name = tsb.node_text(method_name_node, source_bytes)
                    calls = tsb.collect_calls(child, source_bytes)
                    is_test_fn = _has_test_attr(child_attr_text)
                    methods.append(FunctionInfo(
                        name=method_name,
                        file_path=file_path,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        signature=self._extract_signature(child, source_bytes),
                        docstring=self._extract_doc_comment(child, source_bytes),
                        calls=calls,
                        is_test=is_test_fn,
                    ))
            else:
                pending_attrs.clear()

        # Find or create the ClassInfo for this impl type
        existing = next((c for c in classes if c.name == impl_type), None)
        if existing:
            existing.methods.extend(methods)
            for b in bases:
                if b not in existing.bases:
                    existing.bases.append(b)
        else:
            classes.append(ClassInfo(
                name=impl_type,
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                docstring=None,
                methods=methods,
                bases=bases,
            ))

    def _extract_mod(
        self,
        node,
        source_bytes: bytes,
        file_path: str,
        functions: List[FunctionInfo],
        classes: List[ClassInfo],
        is_test_file: bool,
        attr_text: str,
    ):
        """Extract items from an inline module (e.g., #[cfg(test)] mod tests)."""
        is_test_mod = _has_cfg_test_attr(attr_text)
        body = node.child_by_field_name("body")
        if not body:
            return  # Extern mod declaration (e.g. mod foo;), no body

        pending_attrs: List[str] = []
        for child in body.children:
            # Inside a test module, mark functions as test-context
            self._extract_node(
                child, source_bytes, file_path, functions,
                classes, is_test_file or is_test_mod,
                pending_attrs=pending_attrs,
            )

    # ------------------------------------------------------------------
    # Signature / doc extraction
    # ------------------------------------------------------------------

    def _extract_signature(self, node, source_bytes: bytes) -> str:
        """Extract function signature (name + parameters)."""
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        name = tsb.node_text(name_node, source_bytes) if name_node else "anonymous"
        params = tsb.node_text(params_node, source_bytes) if params_node else "()"
        # Include return type if present
        ret_node = node.child_by_field_name("return_type")
        ret = ""
        if ret_node:
            raw = tsb.node_text(ret_node, source_bytes)
            # tree-sitter may or may not include the "->"; ensure it's present
            if not raw.startswith("->"):
                raw = "-> " + raw
            ret = " " + raw
        return f"{name}{params}{ret}"

    def _extract_doc_comment(self, node, source_bytes: bytes) -> Optional[str]:
        """Extract /// doc comments preceding a node."""
        comments: List[str] = []
        prev = node.prev_sibling
        while prev and prev.type == "line_comment":
            text = tsb.node_text(prev, source_bytes)
            if text.startswith("///"):
                comments.insert(0, text)
                prev = prev.prev_sibling
            else:
                break
        return "\n".join(comments) if comments else None

    # ------------------------------------------------------------------
    # Import collection
    # ------------------------------------------------------------------

    def _collect_imports(self, root_node, source_bytes: bytes) -> List[str]:
        """Collect use-declaration paths from Rust source."""
        imports: List[str] = []
        for child in root_node.children:
            if child.type == "use_declaration":
                # The argument field holds the use-path tree
                arg = child.child_by_field_name("argument")
                if arg:
                    imports.append(tsb.node_text(arg, source_bytes))
        return imports

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def module_name(self, relative_path: str) -> str:
        """Convert a repo-relative file path to a Rust module path.

        E.g., ``src/foo/bar.rs`` -> ``crate::foo::bar``
        """
        normalized = relative_path.replace("\\", "/")
        # Strip .rs extension
        if normalized.endswith(".rs"):
            normalized = normalized[:-3]
        # Remove leading src/ prefix, replace with crate::
        parts = normalized.split("/")
        if parts and parts[0] == "src":
            parts[0] = "crate"
        else:
            parts.insert(0, "crate")
        # Remove lib or main as leaf (they represent the crate root)
        if parts[-1] in ("lib", "main"):
            parts = parts[:-1]
        # Remove mod if it's the leaf (mod.rs represents its parent)
        if parts[-1] == "mod":
            parts = parts[:-1]
        return "::".join(parts)

    def is_test_file(self, filename: str) -> bool:
        # Rust tests are typically in the same file.  Separate test files
        # live under tests/ but are still named *.rs, so we treat any file
        # whose stem starts with "test_" or ends with "_test" as a test file.
        stem = Path(filename).stem
        return stem.startswith("test_") or stem.endswith("_test")

    def is_test_function(self, name: str) -> bool:
        return name.startswith("test_") or name.startswith("test")

    def is_test_class(self, name: str) -> bool:
        # Rust doesn't really have "test classes", but test modules qualify
        return name == "tests" or name.startswith("test_")

    def resolve_self_calls(self, class_name: str, call: str) -> str:
        if call.startswith("self."):
            return f"{class_name}.{call[5:]}"
        return call

    def test_runner_command(self, repo_path: Path, test_ids: List[str]) -> List[str]:
        cmd = ["cargo", "test"]
        cmd.extend(test_ids)
        cmd.append("--")
        cmd.append("--nocapture")
        return cmd

    def parse_test_output(self, output: str) -> Dict[str, int]:
        """Parse ``cargo test`` output for pass/fail/error counts.

        Looks for the summary line::

            test result: ok. N passed; M failed; I ignored; ...

        and also individual lines like::

            test foo ... ok
            test bar ... FAILED
        """
        passed = failed = errors = 0

        # Summary line: "test result: ok. 5 passed; 0 failed; 0 ignored; ..."
        summary = re.search(
            r"test result:.*?(\d+)\s+passed;\s*(\d+)\s+failed",
            output,
        )
        if summary:
            passed = int(summary.group(1))
            failed = int(summary.group(2))
            return {"passed": passed, "failed": failed, "errors": errors}

        # Fallback: count individual lines
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("test ") and " ... " in stripped:
                if stripped.endswith("ok"):
                    passed += 1
                elif stripped.endswith("FAILED"):
                    failed += 1

        return {"passed": passed, "failed": failed, "errors": errors}

    def heuristic_test_stem(self, test_stem: str) -> Optional[str]:
        """Map a test file stem to the likely source file stem.

        Rust tests are typically in the same file, so this usually returns
        None.  For separate test files: ``test_foo`` -> ``foo``.
        """
        if test_stem.startswith("test_"):
            return test_stem[5:]
        if test_stem.endswith("_test"):
            return test_stem[:-5]
        return None


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _has_test_attr(attr_text: str) -> bool:
    """Return True if the accumulated attributes contain ``#[test]``."""
    return "#[test]" in attr_text


def _has_cfg_test_attr(attr_text: str) -> bool:
    """Return True if the accumulated attributes contain ``#[cfg(test)]``."""
    return "#[cfg(test)]" in attr_text
