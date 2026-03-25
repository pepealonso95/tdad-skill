"""Tests for the JavaScript/TypeScript language plugin."""

import pytest
from pathlib import Path

# Skip all tests if tree-sitter is not installed
ts = pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
pytest.importorskip("tree_sitter_javascript", reason="tree-sitter-javascript not installed")

from tdad.languages.javascript import JavaScriptPlugin
from tdad.languages.base import FileInfo


@pytest.fixture
def js_plugin():
    return JavaScriptPlugin("javascript")


@pytest.fixture
def ts_plugin():
    return JavaScriptPlugin("typescript")


@pytest.fixture
def sample_js_repo():
    return Path(__file__).parent / "fixtures" / "sample_js_repo"


@pytest.fixture
def sample_calculator_js(sample_js_repo):
    return sample_js_repo / "src" / "calculator.js"


@pytest.fixture
def sample_utils_js(sample_js_repo):
    return sample_js_repo / "src" / "utils.js"


@pytest.fixture
def sample_test_calculator_js(sample_js_repo):
    return sample_js_repo / "tests" / "calculator.test.js"


@pytest.fixture
def sample_test_utils_js(sample_js_repo):
    return sample_js_repo / "tests" / "utils.test.js"


# -- Test file detection --

def test_is_test_file(js_plugin):
    assert js_plugin.is_test_file("calculator.test.js")
    assert js_plugin.is_test_file("utils.spec.ts")
    assert js_plugin.is_test_file("foo.test.tsx")
    assert not js_plugin.is_test_file("calculator.js")
    assert not js_plugin.is_test_file("utils.ts")


def test_is_test_function(js_plugin):
    assert js_plugin.is_test_function("test:should add numbers")
    assert js_plugin.is_test_function("it:does something")
    assert js_plugin.is_test_function("describe")
    assert not js_plugin.is_test_function("add")
    assert not js_plugin.is_test_function("myHelper")


# -- File parsing --

def test_parse_calculator(js_plugin, sample_js_repo, sample_calculator_js):
    info = js_plugin.parse_file(sample_calculator_js, sample_js_repo)

    assert isinstance(info, FileInfo)
    assert info.name == "calculator.js"
    assert info.language == "javascript"
    assert not info.is_test_file
    assert info.content_hash

    # Should find top-level functions
    func_names = [f.name for f in info.functions]
    assert "add" in func_names
    assert "subtract" in func_names
    assert "multiply" in func_names
    assert "divide" in func_names

    # Should find Calculator class
    class_names = [c.name for c in info.classes]
    assert "Calculator" in class_names

    # Calculator class should have methods
    calc_class = next(c for c in info.classes if c.name == "Calculator")
    method_names = [m.name for m in calc_class.methods]
    assert "constructor" in method_names
    assert "compute" in method_names

    # Should detect imports
    assert any("utils" in imp for imp in info.imports)


def test_parse_utils(js_plugin, sample_js_repo, sample_utils_js):
    info = js_plugin.parse_file(sample_utils_js, sample_js_repo)

    assert not info.is_test_file
    func_names = [f.name for f in info.functions]
    assert "validateNumber" in func_names
    assert "clamp" in func_names

    # clamp should call validateNumber
    clamp_func = next(f for f in info.functions if f.name == "clamp")
    assert "validateNumber" in clamp_func.calls


def test_parse_test_file(js_plugin, sample_js_repo, sample_test_calculator_js):
    info = js_plugin.parse_file(sample_test_calculator_js, sample_js_repo)

    assert info.is_test_file
    assert info.name == "calculator.test.js"

    # Should find test functions (it/test blocks)
    func_names = [f.name for f in info.functions]
    test_funcs = [f for f in info.functions if f.is_test]
    assert len(test_funcs) > 0

    # Should have imports
    assert any("calculator" in imp for imp in info.imports)


def test_parse_test_utils(js_plugin, sample_js_repo, sample_test_utils_js):
    info = js_plugin.parse_file(sample_test_utils_js, sample_js_repo)

    assert info.is_test_file
    test_funcs = [f for f in info.functions if f.is_test]
    assert len(test_funcs) > 0


# -- Module name --

def test_module_name(js_plugin):
    assert js_plugin.module_name("src/calculator.js") == "src.calculator"
    assert js_plugin.module_name("tests/calculator.test.js") == "tests.calculator.test"
    assert js_plugin.module_name("index.ts") == "index"


# -- Heuristic stem --

def test_heuristic_test_stem(js_plugin):
    assert js_plugin.heuristic_test_stem("calculator.test") == "calculator"
    assert js_plugin.heuristic_test_stem("utils.spec") == "utils"
    assert js_plugin.heuristic_test_stem("calculator") is None


# -- Self-call resolution --

def test_resolve_self_calls(js_plugin):
    assert js_plugin.resolve_self_calls("Foo", "this.bar") == "Foo.bar"
    assert js_plugin.resolve_self_calls("Foo", "otherObj.bar") == "otherObj.bar"


# -- Test output parsing --

def test_parse_jest_output(js_plugin):
    output = """PASS tests/calculator.test.js
  Calculator functions
    ✓ should add two numbers (2 ms)
    ✓ should subtract two numbers (1 ms)

Tests: 2 passed, 2 total
"""
    result = js_plugin.parse_test_output(output)
    assert result["passed"] == 2
    assert result["failed"] == 0


def test_parse_jest_output_with_failures(js_plugin):
    output = """FAIL tests/calculator.test.js
Tests: 1 failed, 3 passed, 4 total
"""
    result = js_plugin.parse_test_output(output)
    assert result["passed"] == 3
    assert result["failed"] == 1


def test_parse_vitest_output(js_plugin):
    output = """Tests  1 failed | 5 passed (6)
"""
    result = js_plugin.parse_test_output(output)
    assert result["passed"] == 5
    assert result["failed"] == 1


def test_parse_mocha_output(js_plugin):
    output = """
  3 passing (10ms)
  1 failing
"""
    result = js_plugin.parse_test_output(output)
    assert result["passed"] == 3
    assert result["failed"] == 1


# -- Test runner detection --

def test_detect_test_runner(js_plugin, sample_js_repo):
    runner = js_plugin._detect_test_runner(sample_js_repo)
    assert runner == "jest"


def test_test_runner_command(js_plugin, sample_js_repo):
    cmd = js_plugin.test_runner_command(sample_js_repo, ["tests/calculator.test.js"])
    assert "jest" in " ".join(cmd)
    assert "tests/calculator.test.js" in cmd
