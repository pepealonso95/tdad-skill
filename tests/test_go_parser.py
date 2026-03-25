"""Tests for the Go language plugin."""

import pytest
from pathlib import Path

# Skip all tests if tree-sitter or the Go grammar is not installed
ts = pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
pytest.importorskip("tree_sitter_go", reason="tree-sitter-go not installed")

from tdad.languages.go import GoPlugin
from tdad.languages.base import FileInfo


@pytest.fixture
def go_plugin():
    return GoPlugin()


@pytest.fixture
def sample_go_repo():
    return Path(__file__).parent / "fixtures" / "sample_go_repo"


@pytest.fixture
def sample_calculator_go(sample_go_repo):
    return sample_go_repo / "calculator" / "calculator.go"


@pytest.fixture
def sample_utils_go(sample_go_repo):
    return sample_go_repo / "utils" / "utils.go"


@pytest.fixture
def sample_test_calculator_go(sample_go_repo):
    return sample_go_repo / "calculator" / "calculator_test.go"


@pytest.fixture
def sample_test_utils_go(sample_go_repo):
    return sample_go_repo / "utils" / "utils_test.go"


# -- Test file detection --

def test_is_test_file(go_plugin):
    assert go_plugin.is_test_file("calculator_test.go")
    assert go_plugin.is_test_file("utils_test.go")
    assert not go_plugin.is_test_file("calculator.go")
    assert not go_plugin.is_test_file("main.go")


def test_is_test_function(go_plugin):
    assert go_plugin.is_test_function("TestAdd")
    assert go_plugin.is_test_function("TestSubtract")
    assert go_plugin.is_test_function("BenchmarkAdd")
    assert not go_plugin.is_test_function("Add")
    assert not go_plugin.is_test_function("helper")


# -- File parsing --

def test_parse_calculator(go_plugin, sample_go_repo, sample_calculator_go):
    info = go_plugin.parse_file(sample_calculator_go, sample_go_repo)

    assert isinstance(info, FileInfo)
    assert info.name == "calculator.go"
    assert info.language == "go"
    assert not info.is_test_file
    assert info.content_hash

    # Should find top-level functions
    func_names = [f.name for f in info.functions]
    assert "Add" in func_names
    assert "Subtract" in func_names

    # Should find Calculator struct
    class_names = [c.name for c in info.classes]
    assert "Calculator" in class_names

    # Calculator struct should have the Compute method attached
    calc_class = next(c for c in info.classes if c.name == "Calculator")
    method_names = [m.name for m in calc_class.methods]
    assert "Compute" in method_names

    # Compute method should call Add and Subtract
    compute_method = next(m for m in calc_class.methods if m.name == "Compute")
    assert "Add" in compute_method.calls
    assert "Subtract" in compute_method.calls

    # Should detect imports
    assert "fmt" in info.imports


def test_parse_utils(go_plugin, sample_go_repo, sample_utils_go):
    info = go_plugin.parse_file(sample_utils_go, sample_go_repo)

    assert not info.is_test_file
    func_names = [f.name for f in info.functions]
    assert "ValidateNumber" in func_names
    assert "Clamp" in func_names

    # Clamp should call ValidateNumber
    clamp_func = next(f for f in info.functions if f.name == "Clamp")
    assert "ValidateNumber" in clamp_func.calls

    # Should detect grouped imports
    assert "fmt" in info.imports
    assert "math" in info.imports


def test_parse_test_file(go_plugin, sample_go_repo, sample_test_calculator_go):
    info = go_plugin.parse_file(sample_test_calculator_go, sample_go_repo)

    assert info.is_test_file
    assert info.name == "calculator_test.go"

    # Should find test functions
    func_names = [f.name for f in info.functions]
    assert "TestAdd" in func_names
    assert "TestSubtract" in func_names

    # Test functions should be marked as tests
    test_funcs = [f for f in info.functions if f.is_test]
    assert len(test_funcs) == 2

    # Should have testing import
    assert "testing" in info.imports


def test_parse_test_utils(go_plugin, sample_go_repo, sample_test_utils_go):
    info = go_plugin.parse_file(sample_test_utils_go, sample_go_repo)

    assert info.is_test_file
    test_funcs = [f for f in info.functions if f.is_test]
    assert len(test_funcs) == 2

    test_names = [f.name for f in test_funcs]
    assert "TestValidateNumber" in test_names
    assert "TestClamp" in test_names


# -- Module name --

def test_module_name(go_plugin):
    assert go_plugin.module_name("calculator/calculator.go") == "calculator/calculator"
    assert go_plugin.module_name("utils/utils_test.go") == "utils/utils_test"
    assert go_plugin.module_name("main.go") == "main"


# -- Heuristic stem --

def test_heuristic_test_stem(go_plugin):
    assert go_plugin.heuristic_test_stem("calculator_test") == "calculator"
    assert go_plugin.heuristic_test_stem("utils_test") == "utils"
    assert go_plugin.heuristic_test_stem("calculator") is None


# -- Self-call resolution --

def test_resolve_self_calls(go_plugin):
    # Go doesn't have self/cls, so the call should be returned as-is
    assert go_plugin.resolve_self_calls("Calculator", "Add") == "Add"
    assert go_plugin.resolve_self_calls("Calculator", "c.Compute") == "c.Compute"


# -- Test output parsing --

def test_parse_go_test_output_pass(go_plugin):
    output = """=== RUN   TestAdd
--- PASS: TestAdd (0.00s)
=== RUN   TestSubtract
--- PASS: TestSubtract (0.00s)
PASS
ok      example.com/calculator  0.003s
"""
    result = go_plugin.parse_test_output(output)
    assert result["passed"] == 2
    assert result["failed"] == 0
    assert result["errors"] == 0


def test_parse_go_test_output_with_failures(go_plugin):
    output = """=== RUN   TestAdd
--- PASS: TestAdd (0.00s)
=== RUN   TestSubtract
--- FAIL: TestSubtract (0.00s)
    calculator_test.go:14: Subtract(5, 3) = 3.000000; want 2
FAIL
FAIL    example.com/calculator  0.004s
"""
    result = go_plugin.parse_test_output(output)
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["errors"] == 0


def test_parse_go_test_output_all_fail(go_plugin):
    output = """=== RUN   TestAdd
--- FAIL: TestAdd (0.00s)
=== RUN   TestSubtract
--- FAIL: TestSubtract (0.00s)
FAIL
FAIL    example.com/calculator  0.002s
"""
    result = go_plugin.parse_test_output(output)
    assert result["passed"] == 0
    assert result["failed"] == 2


# -- Test runner command --

def test_test_runner_command(go_plugin, sample_go_repo):
    cmd = go_plugin.test_runner_command(sample_go_repo, ["TestAdd", "TestSubtract"])
    assert cmd[0] == "go"
    assert cmd[1] == "test"
    assert "-run" in cmd
    run_idx = cmd.index("-run")
    assert "TestAdd" in cmd[run_idx + 1]
    assert "TestSubtract" in cmd[run_idx + 1]
    assert "-v" in cmd
    assert "./..." in cmd


# -- File extensions --

def test_file_extensions(go_plugin):
    assert go_plugin.file_extensions == {".go"}


# -- Plugin name --

def test_plugin_name(go_plugin):
    assert go_plugin.name == "go"


# -- Test class detection --

def test_is_test_class(go_plugin):
    assert go_plugin.is_test_class("TestSuite")
    assert go_plugin.is_test_class("CalculatorSuite")
    assert not go_plugin.is_test_class("Calculator")
