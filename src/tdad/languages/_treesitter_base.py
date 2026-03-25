"""Shared tree-sitter utilities for non-Python language plugins.

Provides grammar loading, query execution, and mapping of tree-sitter
captures to TDAD dataclasses (FunctionInfo, ClassInfo, FileInfo).
"""

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .base import FileInfo, FunctionInfo, ClassInfo

logger = logging.getLogger(__name__)

# Cache loaded languages to avoid repeated initialization
_language_cache: Dict[str, Any] = {}


def _get_language(language_name: str):
    """Load and cache a tree-sitter Language object.

    Raises ImportError if the required tree-sitter grammar package
    is not installed.
    """
    if language_name in _language_cache:
        return _language_cache[language_name]

    try:
        import tree_sitter
    except ImportError:
        raise ImportError(
            "tree-sitter is required for non-Python language support. "
            "Install it with: pip install tdad[treesitter]"
        )

    if language_name == "javascript":
        try:
            import tree_sitter_javascript as ts_js
            lang = tree_sitter.Language(ts_js.language())
        except ImportError:
            raise ImportError(
                "tree-sitter-javascript is required for JS/TS support. "
                "Install it with: pip install tree-sitter-javascript"
            )
    elif language_name == "typescript":
        try:
            import tree_sitter_typescript as ts_ts
            lang = tree_sitter.Language(ts_ts.language_typescript())
        except ImportError:
            raise ImportError(
                "tree-sitter-typescript is required for TypeScript support. "
                "Install it with: pip install tree-sitter-typescript"
            )
    elif language_name == "tsx":
        try:
            import tree_sitter_typescript as ts_ts
            lang = tree_sitter.Language(ts_ts.language_tsx())
        except ImportError:
            raise ImportError(
                "tree-sitter-typescript is required for TSX support. "
                "Install it with: pip install tree-sitter-typescript"
            )
    elif language_name == "go":
        try:
            import tree_sitter_go as ts_go
            lang = tree_sitter.Language(ts_go.language())
        except ImportError:
            raise ImportError(
                "tree-sitter-go is required for Go support. "
                "Install it with: pip install tree-sitter-go"
            )
    elif language_name == "java":
        try:
            import tree_sitter_java as ts_java
            lang = tree_sitter.Language(ts_java.language())
        except ImportError:
            raise ImportError(
                "tree-sitter-java is required for Java support. "
                "Install it with: pip install tree-sitter-java"
            )
    elif language_name == "rust":
        try:
            import tree_sitter_rust as ts_rust
            lang = tree_sitter.Language(ts_rust.language())
        except ImportError:
            raise ImportError(
                "tree-sitter-rust is required for Rust support. "
                "Install it with: pip install tree-sitter-rust"
            )
    elif language_name == "dart":
        try:
            import tree_sitter_dart_orchard as ts_dart
            lang = tree_sitter.Language(ts_dart.language())
        except ImportError:
            raise ImportError(
                "tree-sitter-dart-orchard is required for Dart support. "
                "Install it with: pip install tree-sitter-dart-orchard"
            )
    else:
        raise ValueError(f"No tree-sitter grammar available for: {language_name}")

    _language_cache[language_name] = lang
    return lang


def get_parser(language_name: str):
    """Create a tree-sitter Parser for the given language."""
    import tree_sitter
    lang = _get_language(language_name)
    parser = tree_sitter.Parser(lang)
    return parser


def load_query(language_name: str, query_text: str):
    """Create a tree-sitter Query from a string."""
    import tree_sitter
    lang = _get_language(language_name)
    return lang.query(query_text)


def load_query_file(language_name: str, query_filename: str):
    """Load a .scm query file from the queries/ directory."""
    query_dir = Path(__file__).parent / "queries"
    query_path = query_dir / query_filename
    if not query_path.exists():
        raise FileNotFoundError(f"Query file not found: {query_path}")
    query_text = query_path.read_text(encoding="utf-8")
    return load_query(language_name, query_text)


def content_hash(source: str) -> str:
    """Compute MD5 hash of file content."""
    return hashlib.md5(source.encode("utf-8")).hexdigest()


def parse_source(language_name: str, source: str):
    """Parse source code and return the tree-sitter tree."""
    parser = get_parser(language_name)
    return parser.parse(source.encode("utf-8"))


def node_text(node, source_bytes: bytes) -> str:
    """Extract the text of a tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def find_children_by_type(node, type_name: str) -> list:
    """Find all direct children of a node with the given type."""
    return [child for child in node.children if child.type == type_name]


def find_descendant_by_type(node, type_name: str):
    """Find the first descendant of a node with the given type (DFS)."""
    for child in node.children:
        if child.type == type_name:
            return child
        result = find_descendant_by_type(child, type_name)
        if result is not None:
            return result
    return None


def collect_calls(node, source_bytes: bytes) -> List[str]:
    """Recursively collect all function call names from a subtree."""
    calls = []
    _collect_calls_recursive(node, source_bytes, calls)
    return calls


def _collect_calls_recursive(node, source_bytes: bytes, calls: List[str]):
    """Recursively walk a tree-sitter node collecting call expressions."""
    if node.type == "call_expression":
        func_node = node.child_by_field_name("function")
        if func_node:
            name = node_text(func_node, source_bytes)
            if name and not name.startswith("("):
                calls.append(name)
    elif node.type == "method_invocation":
        # Java-specific: method_invocation nodes
        # Extract the full method call name (e.g., "Math.min" or "validateNumber")
        parts = []
        for child in node.children:
            if child.type == "identifier":
                parts.append(node_text(child, source_bytes))
            elif child.type == ".":
                continue
            elif child.type in ("argument_list", "(", ")"):
                break
            elif child.type == "method_invocation":
                # Nested call: the object is itself a method call
                parts.append(node_text(child, source_bytes).split("(")[0])
                break
            elif child.type == "field_access":
                parts.append(node_text(child, source_bytes))
        if parts:
            calls.append(".".join(parts))
    for child in node.children:
        _collect_calls_recursive(child, source_bytes, calls)


def collect_imports_js(root_node, source_bytes: bytes) -> List[str]:
    """Collect import sources from JavaScript/TypeScript import statements."""
    imports = []
    for child in root_node.children:
        if child.type == "import_statement":
            source_node = child.child_by_field_name("source")
            if source_node:
                raw = node_text(source_node, source_bytes)
                imports.append(raw.strip("'\""))
        elif child.type == "expression_statement":
            # CommonJS: const x = require("module")
            expr = child.children[0] if child.children else None
            if expr and expr.type == "assignment_expression":
                right = expr.child_by_field_name("right")
                if right and right.type == "call_expression":
                    func = right.child_by_field_name("function")
                    if func and node_text(func, source_bytes) == "require":
                        args = right.child_by_field_name("arguments")
                        if args and args.children:
                            for arg in args.children:
                                if arg.type == "string":
                                    imports.append(node_text(arg, source_bytes).strip("'\""))
        elif child.type == "lexical_declaration":
            # const x = require("module")
            for decl in child.children:
                if decl.type == "variable_declarator":
                    value = decl.child_by_field_name("value")
                    if value and value.type == "call_expression":
                        func = value.child_by_field_name("function")
                        if func and node_text(func, source_bytes) == "require":
                            args = value.child_by_field_name("arguments")
                            if args:
                                for arg in args.children:
                                    if arg.type == "string":
                                        imports.append(node_text(arg, source_bytes).strip("'\""))
    return imports
