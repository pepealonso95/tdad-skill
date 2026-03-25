"""Graph builder: walks a repo, parses source files, persists to graph DB."""

import hashlib
import logging
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .ast_parser import FileInfo as AstFileInfo, parse_file as ast_parse_file
from ..languages import get_active_plugins, all_extensions, SKIP_DIRS
from ..languages.base import LanguagePlugin, FileInfo

logger = logging.getLogger(__name__)


def _collect_source_files(repo_path: Path, extensions: Set[str]) -> List[Path]:
    """Walk repo for source files matching the given extensions."""
    files = []
    for p in repo_path.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and p.suffix in extensions:
            files.append(p)
    return sorted(files)


# Keep for backward compatibility
def _collect_python_files(repo_path: Path) -> List[Path]:
    """Walk repo for .py files, skipping common non-source directories."""
    return _collect_source_files(repo_path, {".py"})


def _parse_file_worker(file_path_str: str, repo_root_str: str) -> AstFileInfo:
    """Standalone worker function for ProcessPoolExecutor (Python only)."""
    return ast_parse_file(Path(file_path_str), Path(repo_root_str))


def _module_name(relative_path: str) -> str:
    """Convert repo-relative path to dotted module name (Python convention)."""
    normalized = relative_path.replace("\\", "/")
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    return normalized.replace("/", ".").strip(".")


def _hash_file(path: Path) -> str:
    """Compute MD5 content hash without reading entire file into memory."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------
# Incremental diff
# ------------------------------------------------------------------

def _get_indexed_hashes(db) -> Dict[str, str]:
    """Query graph for all File nodes and their content_hash."""
    if hasattr(db, "get_all_file_hashes"):
        return db.get_all_file_hashes()
    # Neo4j fallback
    with db.session() as session:
        result = db.run_query(session, """
            MATCH (f:File)
            RETURN f.path AS path, f.content_hash AS hash
        """)
        return {r["path"]: r["hash"] for r in result}


def _compute_diff(
    python_files: List[Path],
    repo_path: Path,
    indexed: Dict[str, str],
) -> Tuple[List[Path], List[Path], List[str]]:
    """Compare on-disk files against indexed hashes.

    Returns:
        (new_or_changed, unchanged, deleted_paths)
    """
    new_or_changed: List[Path] = []
    unchanged: List[Path] = []
    current_rel_paths: Set[str] = set()

    for p in python_files:
        try:
            rel = str(p.resolve().relative_to(repo_path.resolve()))
        except ValueError:
            rel = p.name
        current_rel_paths.add(rel)

        old_hash = indexed.get(rel)
        if old_hash is None:
            new_or_changed.append(p)
        else:
            current_hash = _hash_file(p)
            if current_hash != old_hash:
                new_or_changed.append(p)
            else:
                unchanged.append(p)

    deleted = [path for path in indexed if path not in current_rel_paths]
    return new_or_changed, unchanged, deleted


def _delete_file_subgraph(db, deleted_paths: List[str]) -> int:
    """Remove nodes and edges for deleted files."""
    if not deleted_paths:
        return 0
    if hasattr(db, "delete_file_subgraph"):
        db.delete_file_subgraph(deleted_paths)
    else:
        with db.session() as session:
            db.run_query(session, """
                UNWIND $paths AS p
                MATCH (f:File {path: p})-[:CONTAINS]->(n)
                DETACH DELETE n
                WITH count(*) AS child_count
                UNWIND $paths AS p
                MATCH (f:File {path: p})
                DETACH DELETE f
                RETURN child_count
            """, paths=deleted_paths)
    logger.info("Deleted subgraphs for %d removed files", len(deleted_paths))
    return len(deleted_paths)


def _delete_stale_nodes(db, changed_rel_paths: List[str]) -> None:
    """Remove old child nodes for files that will be re-indexed."""
    if not changed_rel_paths:
        return
    if hasattr(db, "delete_file_subgraph"):
        # NetworkX: delete children but keep File node (subgraph deletes file too,
        # but it will be re-merged during persist)
        db.delete_file_subgraph(changed_rel_paths)
    else:
        with db.session() as session:
            db.run_query(session, """
                UNWIND $paths AS p
                MATCH (f:File {path: p})-[:CONTAINS]->(n)
                DETACH DELETE n
            """, paths=changed_rel_paths)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def build_graph(
    repo_path: Path,
    db,
    force: bool = False,
    languages: Optional[str] = None,
) -> Dict[str, Any]:
    """Index a repository into the graph.

    Incremental by default: only re-parses new/changed files and removes
    deleted ones. Use force=True for a full rebuild.

    Args:
        languages: Comma-separated language names (e.g., "python,javascript").
                   If None, auto-detects from file extensions.

    Returns statistics dict with node/edge counts.
    """
    repo_path = repo_path.resolve()
    if not repo_path.is_dir():
        raise ValueError(f"Not a directory: {repo_path}")

    if force:
        db.clear_database()

    db.ensure_schema()

    # Resolve active language plugins
    plugins = get_active_plugins(repo_path, explicit_languages=languages)
    extensions = all_extensions(plugins)

    python_files = _collect_source_files(repo_path, extensions)
    if not python_files:
        return {"files": 0, "functions": 0, "classes": 0, "tests": 0, "edges": 0,
                "incremental": False, "changed": 0, "unchanged": 0, "deleted": 0}

    # Incremental diff (skip when force or empty graph)
    if not force:
        indexed = _get_indexed_hashes(db)
    else:
        indexed = {}

    if indexed:
        to_parse, unchanged, deleted = _compute_diff(python_files, repo_path, indexed)
        _delete_file_subgraph(db, deleted)

        if not to_parse and not deleted:
            logger.info("Graph is up-to-date, nothing to index")
            return {"files": len(unchanged), "functions": 0, "classes": 0, "tests": 0,
                    "edges": 0, "incremental": True, "changed": 0,
                    "unchanged": len(unchanged), "deleted": 0}

        # Remove stale child nodes for changed files before re-inserting
        changed_rel = []
        for p in to_parse:
            try:
                changed_rel.append(str(p.resolve().relative_to(repo_path.resolve())))
            except ValueError:
                pass
        _delete_stale_nodes(db, changed_rel)

        logger.info(
            "Incremental index: %d changed/new, %d unchanged, %d deleted",
            len(to_parse), len(unchanged), len(deleted),
        )
    else:
        to_parse = python_files
        unchanged = []
        deleted = []

    # Parse files (parallel when > 1 worker)
    workers = min(db.settings.index_workers, len(to_parse))
    file_infos = _parse_files(to_parse, repo_path, workers, plugins)

    # Persist nodes and edges
    stats = _persist_to_graph(file_infos, repo_path, db, plugins)
    stats["incremental"] = bool(indexed)
    stats["changed"] = len(to_parse)
    stats["unchanged"] = len(unchanged)
    stats["deleted"] = len(deleted)

    logger.info(
        "Indexed %d files (%d changed, %d unchanged, %d deleted): "
        "%d functions, %d classes, %d tests, %d edges",
        stats["files"], stats["changed"], stats["unchanged"], stats["deleted"],
        stats["functions"], stats["classes"], stats["tests"], stats["edges"],
    )
    return stats


def _get_plugin_for_file(path: Path, plugins: List[LanguagePlugin]) -> Optional[LanguagePlugin]:
    """Find the plugin that handles the given file's extension."""
    suffix = path.suffix.lower()
    for plugin in plugins:
        if suffix in plugin.file_extensions:
            return plugin
    return None


def _parse_files(
    source_files: List[Path],
    repo_path: Path,
    workers: int,
    plugins: Optional[List[LanguagePlugin]] = None,
) -> List[FileInfo]:
    if plugins is None:
        plugins = get_active_plugins(repo_path)

    # Separate Python files (can use ProcessPoolExecutor) from others
    python_files = [f for f in source_files if f.suffix == ".py"]
    other_files = [f for f in source_files if f.suffix != ".py"]

    results: List[FileInfo] = []

    # Parse Python files (parallel-capable via ProcessPoolExecutor)
    if python_files:
        python_plugin = None
        for p in plugins:
            if p.name == "python":
                python_plugin = p
                break

        if python_plugin and workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_parse_file_worker, str(f), str(repo_path)): f
                    for f in python_files
                }
                for future in as_completed(futures):
                    try:
                        ast_info = future.result()
                        # Convert ast_parser FileInfo to languages.base FileInfo
                        results.append(_convert_ast_fileinfo(ast_info))
                    except Exception as exc:
                        logger.error("Error parsing %s: %s", futures[future], exc)
        else:
            for f in python_files:
                try:
                    if python_plugin:
                        results.append(python_plugin.parse_file(f, repo_path))
                    else:
                        results.append(_convert_ast_fileinfo(ast_parse_file(f, repo_path)))
                except Exception as exc:
                    logger.error("Error parsing %s: %s", f, exc)

    # Parse non-Python files via their language plugins (single-threaded)
    for f in other_files:
        plugin = _get_plugin_for_file(f, plugins)
        if plugin is None:
            continue
        try:
            results.append(plugin.parse_file(f, repo_path))
        except Exception as exc:
            logger.error("Error parsing %s: %s", f, exc)

    return results


def _convert_ast_fileinfo(info: AstFileInfo) -> FileInfo:
    """Convert an ast_parser.FileInfo to a languages.base.FileInfo."""
    from ..languages.base import FunctionInfo as BaseFunctionInfo, ClassInfo as BaseClassInfo
    functions = [
        BaseFunctionInfo(
            name=f.name, file_path=f.file_path,
            start_line=f.start_line, end_line=f.end_line,
            signature=f.signature, docstring=f.docstring,
            calls=f.calls, is_test=f.is_test,
        )
        for f in info.functions
    ]
    classes = [
        BaseClassInfo(
            name=c.name, file_path=c.file_path,
            start_line=c.start_line, end_line=c.end_line,
            docstring=c.docstring,
            methods=[
                BaseFunctionInfo(
                    name=m.name, file_path=m.file_path,
                    start_line=m.start_line, end_line=m.end_line,
                    signature=m.signature, docstring=m.docstring,
                    calls=m.calls, is_test=m.is_test,
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
        language=getattr(info, "language", "python"),
        imports=info.imports,
        functions=functions,
        classes=classes,
        is_test_file=info.is_test_file,
    )


def _persist_to_graph(
    file_infos: List[FileInfo],
    repo_path: Path,
    db,
    plugins: Optional[List[LanguagePlugin]] = None,
) -> Dict[str, int]:
    """Persist parsed file info to graph DB."""
    if plugins is None:
        plugins = get_active_plugins(repo_path)

    # Build extension -> plugin map for quick lookup
    ext_to_plugin: Dict[str, LanguagePlugin] = {}
    for plugin in plugins:
        for ext in plugin.file_extensions:
            ext_to_plugin[ext] = plugin

    files_data = []
    functions_data = []
    classes_data = []
    tests_data = []
    contains_data = []
    calls_data = []
    imports_data = []
    inherits_data = []

    for fi in file_infos:
        # Find the plugin for this file's language
        suffix = Path(fi.name).suffix.lower()
        plugin = ext_to_plugin.get(suffix)
        if plugin:
            mod = plugin.module_name(fi.relative_path)
        else:
            mod = _module_name(fi.relative_path)

        files_data.append({
            "path": fi.relative_path,
            "name": fi.name,
            "content_hash": fi.content_hash,
            "repo_path": str(repo_path),
            "language": fi.language,
        })

        for func in fi.functions:
            func_id = f"{fi.relative_path}::{func.name}:{func.start_line}"
            functions_data.append({
                "id": func_id,
                "name": func.name,
                "file_path": fi.relative_path,
                "start_line": func.start_line,
                "end_line": func.end_line,
                "signature": func.signature,
                "docstring": func.docstring,
                "qualified_name": f"{mod}.{func.name}",
                "calls": func.calls or [],
            })
            contains_data.append({"file_path": fi.relative_path, "node_id": func_id, "node_type": "Function"})

            if func.is_test:
                test_id = f"test::{func_id}"
                tests_data.append({
                    "id": test_id,
                    "name": func.name,
                    "file_path": fi.relative_path,
                })
                contains_data.append({"file_path": fi.relative_path, "node_id": test_id, "node_type": "Test"})

            for call in func.calls:
                calls_data.append({"caller_id": func_id, "callee_name": call})

        for cls in fi.classes:
            class_id = f"{fi.relative_path}::{cls.name}:{cls.start_line}"
            classes_data.append({
                "id": class_id,
                "name": cls.name,
                "file_path": fi.relative_path,
                "start_line": cls.start_line,
                "end_line": cls.end_line,
                "docstring": cls.docstring,
                "qualified_name": f"{mod}.{cls.name}",
            })
            contains_data.append({"file_path": fi.relative_path, "node_id": class_id, "node_type": "Class"})

            for base in cls.bases:
                inherits_data.append({"class_id": class_id, "base_name": base})

            for method in cls.methods:
                method_id = f"{fi.relative_path}::{cls.name}.{method.name}:{method.start_line}"

                # Resolve self/cls/this references via the language plugin
                resolved_calls = []
                for call in method.calls:
                    if plugin:
                        resolved_calls.append(plugin.resolve_self_calls(cls.name, call))
                    elif call.startswith("self.") or call.startswith("cls."):
                        resolved_calls.append(f"{cls.name}.{call.split('.', 1)[1]}")
                    else:
                        resolved_calls.append(call)

                functions_data.append({
                    "id": method_id,
                    "name": f"{cls.name}.{method.name}",
                    "file_path": fi.relative_path,
                    "start_line": method.start_line,
                    "end_line": method.end_line,
                    "signature": method.signature,
                    "docstring": method.docstring,
                    "qualified_name": f"{mod}.{cls.name}.{method.name}",
                    "calls": resolved_calls,
                })
                contains_data.append({"file_path": fi.relative_path, "node_id": method_id, "node_type": "Function"})

                if method.is_test:
                    test_id = f"test::{method_id}"
                    tests_data.append({
                        "id": test_id,
                        "name": f"{cls.name}.{method.name}",
                        "file_path": fi.relative_path,
                    })
                    contains_data.append({"file_path": fi.relative_path, "node_id": test_id, "node_type": "Test"})

                for call in resolved_calls:
                    calls_data.append({"caller_id": method_id, "callee_name": call})

        # File-level import edges
        for imp in fi.imports:
            imports_data.append({"importer": fi.relative_path, "imported_module": imp})

    # Resolve CALLS, IMPORTS, and INHERITS edges in Python using dict lookups.
    # This replaces O(rows × nodes) Cypher cross-product scans with O(1) per lookup.
    resolved_calls = _resolve_calls(calls_data, functions_data)
    resolved_imports = _resolve_imports(imports_data, files_data)
    resolved_inherits = _resolve_inherits(inherits_data, classes_data)

    logger.info(
        "Edge resolution: %d/%d calls, %d/%d imports, %d/%d inherits resolved",
        len(resolved_calls), len(calls_data),
        len(resolved_imports), len(imports_data),
        len(resolved_inherits), len(inherits_data),
    )

    # -- Write to graph DB --
    if hasattr(db, "merge_nodes"):
        # NetworkX backend
        db.merge_nodes("File", files_data, "path")
        db.merge_nodes("Function", functions_data, "id")
        db.merge_nodes("Class", classes_data, "id")
        db.merge_nodes("Test", tests_data, "id")

        # CONTAINS edges
        for row in contains_data:
            src = f"File::{row['file_path']}"
            dst = f"{row['node_type']}::{row['node_id']}"
            db.merge_edge(src, dst, "CONTAINS")

        # CALLS edges (pre-resolved)
        for row in resolved_calls:
            db.merge_edge(f"Function::{row['caller_id']}", f"Function::{row['callee_id']}", "CALLS")

        # IMPORTS edges (pre-resolved)
        for row in resolved_imports:
            db.merge_edge(f"File::{row['importer']}", f"File::{row['imported']}", "IMPORTS")

        # INHERITS edges (pre-resolved)
        for row in resolved_inherits:
            db.merge_edge(f"Class::{row['class_id']}", f"Class::{row['parent_id']}", "INHERITS")

        db.save()
    else:
        # Neo4j backend
        with db.session() as session:
            if files_data:
                db.run_query(session, """
                    UNWIND $rows AS r
                    MERGE (f:File {path: r.path})
                    SET f.name = r.name, f.content_hash = r.content_hash,
                        f.repo_path = r.repo_path, f.updated_at = datetime()
                """, rows=files_data)

            if functions_data:
                db.run_query(session, """
                    UNWIND $rows AS r
                    MERGE (fn:Function {id: r.id})
                    SET fn.name = r.name, fn.file_path = r.file_path,
                        fn.start_line = r.start_line, fn.end_line = r.end_line,
                        fn.signature = r.signature, fn.docstring = r.docstring,
                        fn.qualified_name = r.qualified_name, fn.calls = r.calls,
                        fn.updated_at = datetime()
                """, rows=functions_data)

            if classes_data:
                db.run_query(session, """
                    UNWIND $rows AS r
                    MERGE (c:Class {id: r.id})
                    SET c.name = r.name, c.file_path = r.file_path,
                        c.start_line = r.start_line, c.end_line = r.end_line,
                        c.docstring = r.docstring, c.qualified_name = r.qualified_name,
                        c.updated_at = datetime()
                """, rows=classes_data)

            if tests_data:
                db.run_query(session, """
                    UNWIND $rows AS r
                    MERGE (t:Test {id: r.id})
                    SET t.name = r.name, t.file_path = r.file_path, t.updated_at = datetime()
                """, rows=tests_data)

            if contains_data:
                db.run_query(session, """
                    UNWIND $rows AS r
                    MATCH (f:File {path: r.file_path})
                    MATCH (n {id: r.node_id})
                    MERGE (f)-[:CONTAINS]->(n)
                """, rows=contains_data)

            if resolved_calls:
                db.run_query(session, """
                    UNWIND $rows AS r
                    MATCH (caller:Function {id: r.caller_id})
                    MATCH (callee:Function {id: r.callee_id})
                    MERGE (caller)-[:CALLS]->(callee)
                """, rows=resolved_calls)

            if resolved_imports:
                db.run_query(session, """
                    UNWIND $rows AS r
                    MATCH (importer:File {path: r.importer})
                    MATCH (imported:File {path: r.imported})
                    MERGE (importer)-[:IMPORTS]->(imported)
                """, rows=resolved_imports)

            if resolved_inherits:
                db.run_query(session, """
                    UNWIND $rows AS r
                    MATCH (child:Class {id: r.class_id})
                    MATCH (parent:Class {id: r.parent_id})
                    MERGE (child)-[:INHERITS]->(parent)
                """, rows=resolved_inherits)

    edges = len(contains_data) + len(resolved_calls) + len(resolved_imports) + len(resolved_inherits)
    return {
        "files": len(files_data),
        "functions": len(functions_data),
        "classes": len(classes_data),
        "tests": len(tests_data),
        "edges": edges,
    }


# ------------------------------------------------------------------
# Python-side edge resolution (replaces O(n²) Cypher cross-products)
# ------------------------------------------------------------------

def _resolve_calls(
    calls_data: List[Dict],
    functions_data: List[Dict],
) -> List[Dict]:
    """Resolve callee names to callee IDs using Python dict lookups.

    Replaces the O(calls × functions) Cypher cross-product with
    O(calls + functions) dict construction + O(1) lookups.
    """
    # Build lookup: bare name → set of function IDs
    by_name: Dict[str, Set[str]] = defaultdict(set)
    # Build lookup: qualified name suffix → set of function IDs
    by_qsuffix: Dict[str, Set[str]] = defaultdict(set)

    for fn in functions_data:
        fn_id = fn["id"]
        by_name[fn["name"]].add(fn_id)
        qname = fn.get("qualified_name", "")
        if qname:
            parts = qname.split(".")
            # Index all proper suffixes (after a dot boundary)
            for i in range(1, len(parts)):
                suffix = ".".join(parts[i:])
                by_qsuffix[suffix].add(fn_id)

    resolved = []
    seen: Set[Tuple[str, str]] = set()

    for call in calls_data:
        caller_id = call["caller_id"]
        callee_name = call["callee_name"]

        # Match: callee.name = callee_name
        callee_ids = set(by_name.get(callee_name, set()))
        # Match: callee.qualified_name ENDS WITH ('.' + callee_name)
        callee_ids.update(by_qsuffix.get(callee_name, set()))

        for callee_id in callee_ids:
            key = (caller_id, callee_id)
            if key not in seen:
                seen.add(key)
                resolved.append({"caller_id": caller_id, "callee_id": callee_id})

    return resolved


def _resolve_imports(
    imports_data: List[Dict],
    files_data: List[Dict],
) -> List[Dict]:
    """Resolve import module names to file paths using Python dict lookups.

    Replaces the O(imports × files) Cypher scan with string manipulation
    with O(imports + files) dict construction + O(1) lookups.
    """
    # Build lookup: module suffix → set of file paths
    # "foo/bar/baz.py" → module "foo.bar.baz" → suffixes: "baz", "bar.baz", "foo.bar.baz"
    suffix_to_paths: Dict[str, Set[str]] = defaultdict(set)

    for f in files_data:
        path = f["path"]
        module = path.replace("/", ".").replace("\\", ".")
        if module.endswith(".py"):
            module = module[:-3]
        parts = module.split(".")
        for i in range(len(parts)):
            suffix = ".".join(parts[i:])
            suffix_to_paths[suffix].add(path)

    resolved = []
    seen: Set[Tuple[str, str]] = set()

    for imp in imports_data:
        importer = imp["importer"]
        imported_module = imp["imported_module"]

        for target_path in suffix_to_paths.get(imported_module, set()):
            if target_path == importer:
                continue  # Skip self-imports
            key = (importer, target_path)
            if key not in seen:
                seen.add(key)
                resolved.append({"importer": importer, "imported": target_path})

    return resolved


def _resolve_inherits(
    inherits_data: List[Dict],
    classes_data: List[Dict],
) -> List[Dict]:
    """Resolve base class names to class IDs using Python dict lookups."""
    by_name: Dict[str, List[str]] = defaultdict(list)
    for cls in classes_data:
        by_name[cls["name"]].append(cls["id"])

    resolved = []
    seen: Set[Tuple[str, str]] = set()

    for inh in inherits_data:
        class_id = inh["class_id"]
        for parent_id in by_name.get(inh["base_name"], []):
            if parent_id == class_id:
                continue  # Skip self-inheritance
            key = (class_id, parent_id)
            if key not in seen:
                seen.add(key)
                resolved.append({"class_id": class_id, "parent_id": parent_id})

    return resolved
