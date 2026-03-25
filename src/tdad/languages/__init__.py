"""Language plugin registry.

Auto-detects languages by scanning file extensions and returns
the appropriate plugin instances.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from .base import LanguagePlugin, FileInfo, FunctionInfo, ClassInfo

logger = logging.getLogger(__name__)

# Extension -> language name mapping
EXTENSION_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".dart": "dart",
}

# Directories to skip when scanning
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
             ".tox", ".eggs", "dist", "build", ".mypy_cache", ".pytest_cache"}

# Plugin cache
_plugin_cache: Dict[str, LanguagePlugin] = {}


def get_plugin(language_name: str) -> LanguagePlugin:
    """Return the plugin instance for the given language.

    Raises ValueError if the language is not supported or its
    dependencies are not installed.
    """
    if language_name in _plugin_cache:
        return _plugin_cache[language_name]

    plugin: LanguagePlugin

    if language_name == "python":
        from .python import PythonPlugin
        plugin = PythonPlugin()
    elif language_name in ("javascript", "typescript"):
        from .javascript import JavaScriptPlugin
        plugin = JavaScriptPlugin(language_name)
    elif language_name == "go":
        from .go import GoPlugin
        plugin = GoPlugin()
    elif language_name == "java":
        from .java import JavaPlugin
        plugin = JavaPlugin()
    elif language_name == "rust":
        from .rust import RustPlugin
        plugin = RustPlugin()
    elif language_name == "dart":
        from .dart import DartPlugin
        plugin = DartPlugin()
    else:
        raise ValueError(f"Unsupported language: {language_name!r}")

    _plugin_cache[language_name] = plugin
    return plugin


def detect_languages(repo_path: Path) -> Set[str]:
    """Auto-detect languages in a repository by scanning file extensions."""
    languages: Set[str] = set()
    try:
        for p in repo_path.rglob("*"):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.is_file():
                lang = EXTENSION_MAP.get(p.suffix.lower())
                if lang:
                    languages.add(lang)
    except OSError as exc:
        logger.warning("Error scanning repo for languages: %s", exc)
    return languages


def get_active_plugins(
    repo_path: Path,
    explicit_languages: Optional[str] = None,
) -> List[LanguagePlugin]:
    """Return plugin instances for the active languages.

    If explicit_languages is provided (comma-separated string), use those.
    Otherwise auto-detect from the repository.
    Falls back to Python-only if detection finds nothing.
    """
    if explicit_languages:
        names = [lang.strip() for lang in explicit_languages.split(",") if lang.strip()]
    else:
        names = sorted(detect_languages(repo_path))

    if not names:
        names = ["python"]

    plugins = []
    for name in names:
        # Treat typescript as javascript (same plugin)
        if name == "typescript":
            name = "javascript"
        try:
            plugin = get_plugin(name)
            if plugin not in plugins:
                plugins.append(plugin)
        except (ValueError, ImportError) as exc:
            logger.warning("Skipping language %s: %s", name, exc)

    if not plugins:
        plugins.append(get_plugin("python"))

    return plugins


def all_extensions(plugins: List[LanguagePlugin]) -> Set[str]:
    """Collect all file extensions from the given plugins."""
    exts: Set[str] = set()
    for plugin in plugins:
        exts.update(plugin.file_extensions)
    return exts
