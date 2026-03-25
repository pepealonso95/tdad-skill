"""Language plugin protocol for multi-language support.

Each supported language implements this protocol to provide language-specific
parsing, test detection, and test execution behavior.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Set, runtime_checkable


@dataclass
class FunctionInfo:
    name: str
    file_path: str
    start_line: int
    end_line: int
    signature: str
    docstring: Optional[str]
    calls: List[str] = field(default_factory=list)
    is_test: bool = False


@dataclass
class ClassInfo:
    name: str
    file_path: str
    start_line: int
    end_line: int
    docstring: Optional[str]
    methods: List[FunctionInfo] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)


@dataclass
class FileInfo:
    path: str
    relative_path: str
    name: str
    content_hash: str
    language: str = "python"
    imports: List[str] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    is_test_file: bool = False


@runtime_checkable
class LanguagePlugin(Protocol):
    """Protocol that all language plugins must implement."""

    @property
    def name(self) -> str:
        """Language identifier (e.g., 'python', 'javascript')."""
        ...

    @property
    def file_extensions(self) -> Set[str]:
        """Set of file extensions including dot (e.g., {'.py'})."""
        ...

    def parse_file(self, path: Path, repo_root: Path) -> FileInfo:
        """Parse a source file and return extracted information."""
        ...

    def module_name(self, relative_path: str) -> str:
        """Convert a repo-relative file path to a module/package name."""
        ...

    def is_test_file(self, filename: str) -> bool:
        """Check if a filename matches test file patterns."""
        ...

    def is_test_function(self, name: str) -> bool:
        """Check if a function name matches test function patterns."""
        ...

    def is_test_class(self, name: str) -> bool:
        """Check if a class name matches test class patterns."""
        ...

    def resolve_self_calls(self, class_name: str, call: str) -> str:
        """Resolve instance/class method calls to qualified form.

        E.g., for Python: 'self.method' -> 'ClassName.method'
        """
        ...

    def test_runner_command(self, repo_path: Path, test_ids: List[str]) -> List[str]:
        """Return the command to run specific tests."""
        ...

    def parse_test_output(self, output: str) -> Dict[str, int]:
        """Parse test runner output and return {passed, failed, errors}."""
        ...

    def heuristic_test_stem(self, test_stem: str) -> Optional[str]:
        """Map a test file stem to the likely source file stem.

        E.g., 'test_foo' -> 'foo', 'foo.test' -> 'foo'
        Returns None if the stem doesn't match any pattern.
        """
        ...
