"""Test execution wrapper with multi-language support."""

import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


def run_tests(
    repo_path: Path,
    test_ids: List[str],
    timeout: int = 300,
    language: Optional[str] = None,
) -> Dict:
    """Run specific tests and return results summary.

    Args:
        repo_path: Root of the repository.
        test_ids: List of test IDs (format depends on language).
        timeout: Maximum seconds for the test process.
        language: Language name. If None, auto-detects from test file extensions.

    Returns:
        Dict with keys: passed, failed, errors, output, returncode.
    """
    if not test_ids:
        return {"passed": 0, "failed": 0, "errors": 0, "output": "No tests specified.", "returncode": 0}

    # Detect language from the first test ID's file extension
    if language is None:
        language = _detect_language(test_ids)

    # Get the appropriate plugin
    from ..languages import get_plugin
    try:
        plugin = get_plugin(language)
    except (ValueError, ImportError):
        # Fall back to Python/pytest
        plugin = None

    if plugin:
        cmd = plugin.test_runner_command(repo_path, test_ids)
    else:
        cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q"] + list(test_ids)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "output": f"Test runner timed out after {timeout}s",
            "returncode": -1,
        }

    output = result.stdout + result.stderr

    if plugin:
        counts = plugin.parse_test_output(output)
        passed = counts.get("passed", 0)
        failed = counts.get("failed", 0)
        errors = counts.get("errors", 0)
    else:
        passed, failed, errors = _parse_summary(output)

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "output": output,
        "returncode": result.returncode,
    }


def _detect_language(test_ids: List[str]) -> str:
    """Guess language from test ID file extensions."""
    from ..languages import EXTENSION_MAP
    for tid in test_ids:
        # Test IDs often contain :: separators (pytest) — extract the file part
        file_part = tid.split("::")[0] if "::" in tid else tid
        suffix = Path(file_part).suffix.lower()
        if suffix in EXTENSION_MAP:
            return EXTENSION_MAP[suffix]
    return "python"


def _parse_summary(output: str) -> tuple:
    """Extract pass/fail/error counts from pytest output."""
    passed = failed = errors = 0
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line:
            continue
        # Pytest summary line: "3 passed, 1 failed, 1 error in 0.5s"
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
    return passed, failed, errors
