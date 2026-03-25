"""Tests for the Rust language plugin."""

import pytest
from pathlib import Path

# Skip all tests if tree-sitter or the Rust grammar is not installed
ts = pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
pytest.importorskip("tree_sitter_rust", reason="tree-sitter-rust not installed")

from tdad.languages.rust import RustPlugin
from tdad.languages.base import FileInfo


@pytest.fixture
def rust_plugin():
    return RustPlugin()


@pytest.fixture
def sample_rust_repo():
    return Path(__file__).parent / "fixtures" / "sample_rust_repo"


@pytest.fixture
def sample_calculator_rs(sample_rust_repo):
    return sample_rust_repo / "src" / "calculator.rs"


@pytest.fixture
def sample_utils_rs(sample_rust_repo):
    return sample_rust_repo / "src" / "utils.rs"


@pytest.fixture
def sample_lib_rs(sample_rust_repo):
    return sample_rust_repo / "src" / "lib.rs"


# -- Test file detection --

def test_is_test_file(rust_plugin):
    assert rust_plugin.is_test_file("test_calculator.rs")
    assert rust_plugin.is_test_file("calculator_test.rs")
    assert not rust_plugin.is_test_file("calculator.rs")
    assert not rust_plugin.is_test_file("lib.rs")
    assert not rust_plugin.is_test_file("utils.rs")


def test_is_test_function(rust_plugin):
    assert rust_plugin.is_test_function("test_add")
    assert rust_plugin.is_test_function("test_subtract")
    assert not rust_plugin.is_test_function("add")
    assert not rust_plugin.is_test_function("compute")


# -- File extensions --

def test_file_extensions(rust_plugin):
    assert rust_plugin.file_extensions == {".rs"}


def test_name(rust_plugin):
    assert rust_plugin.name == "rust"


# -- File parsing: calculator.rs --

def test_parse_calculator(rust_plugin, sample_rust_repo, sample_calculator_rs):
    info = rust_plugin.parse_file(sample_calculator_rs, sample_rust_repo)

    assert isinstance(info, FileInfo)
    assert info.name == "calculator.rs"
    assert info.language == "rust"
    assert not info.is_test_file
    assert info.content_hash

    # Should find top-level functions
    func_names = [f.name for f in info.functions]
    assert "add" in func_names
    assert "subtract" in func_names
    assert "multiply" in func_names
    assert "divide" in func_names

    # Should find Calculator struct as a class
    class_names = [c.name for c in info.classes]
    assert "Calculator" in class_names

    # Calculator class should have methods from impl block
    calc_class = next(c for c in info.classes if c.name == "Calculator")
    method_names = [m.name for m in calc_class.methods]
    assert "new" in method_names
    assert "compute" in method_names
    assert "get_last_result" in method_names

    # Should detect imports (use declarations)
    assert any("validate_number" in imp for imp in info.imports)


def test_parse_calculator_calls(rust_plugin, sample_rust_repo, sample_calculator_rs):
    info = rust_plugin.parse_file(sample_calculator_rs, sample_rust_repo)

    # The add function should call validate_number
    add_func = next(f for f in info.functions if f.name == "add")
    assert "validate_number" in add_func.calls


def test_parse_calculator_test_functions(rust_plugin, sample_rust_repo, sample_calculator_rs):
    info = rust_plugin.parse_file(sample_calculator_rs, sample_rust_repo)

    # Should find test functions inside #[cfg(test)] mod tests
    test_funcs = [f for f in info.functions if f.is_test]
    test_func_names = [f.name for f in test_funcs]
    assert "test_add" in test_func_names
    assert "test_subtract" in test_func_names
    assert "test_multiply" in test_func_names
    assert "test_divide" in test_func_names
    assert "test_divide_by_zero" in test_func_names
    assert "test_calculator_compute" in test_func_names
    assert "test_calculator_last_result" in test_func_names


def test_parse_calculator_signatures(rust_plugin, sample_rust_repo, sample_calculator_rs):
    info = rust_plugin.parse_file(sample_calculator_rs, sample_rust_repo)

    add_func = next(f for f in info.functions if f.name == "add")
    assert "a: f64" in add_func.signature
    assert "b: f64" in add_func.signature
    assert "-> f64" in add_func.signature


def test_parse_calculator_doc_comments(rust_plugin, sample_rust_repo, sample_calculator_rs):
    info = rust_plugin.parse_file(sample_calculator_rs, sample_rust_repo)

    add_func = next(f for f in info.functions if f.name == "add")
    assert add_func.docstring is not None
    assert "Add two numbers" in add_func.docstring


# -- File parsing: utils.rs --

def test_parse_utils(rust_plugin, sample_rust_repo, sample_utils_rs):
    info = rust_plugin.parse_file(sample_utils_rs, sample_rust_repo)

    assert not info.is_test_file
    func_names = [f.name for f in info.functions]
    assert "validate_number" in func_names
    assert "clamp" in func_names


def test_parse_utils_calls(rust_plugin, sample_rust_repo, sample_utils_rs):
    info = rust_plugin.parse_file(sample_utils_rs, sample_rust_repo)

    # clamp should call validate_number
    clamp_func = next(f for f in info.functions if f.name == "clamp")
    assert "validate_number" in clamp_func.calls


def test_parse_utils_docstrings(rust_plugin, sample_rust_repo, sample_utils_rs):
    info = rust_plugin.parse_file(sample_utils_rs, sample_rust_repo)

    validate_func = next(f for f in info.functions if f.name == "validate_number")
    assert validate_func.docstring is not None
    assert "Validate" in validate_func.docstring

    clamp_func = next(f for f in info.functions if f.name == "clamp")
    assert clamp_func.docstring is not None
    assert "Clamp" in clamp_func.docstring


# -- File parsing: lib.rs --

def test_parse_lib(rust_plugin, sample_rust_repo, sample_lib_rs):
    info = rust_plugin.parse_file(sample_lib_rs, sample_rust_repo)

    assert info.name == "lib.rs"
    assert info.language == "rust"


# -- Module name --

def test_module_name(rust_plugin):
    assert rust_plugin.module_name("src/foo/bar.rs") == "crate::foo::bar"
    assert rust_plugin.module_name("src/calculator.rs") == "crate::calculator"
    assert rust_plugin.module_name("src/lib.rs") == "crate"
    assert rust_plugin.module_name("src/main.rs") == "crate"
    assert rust_plugin.module_name("src/foo/mod.rs") == "crate::foo"


def test_module_name_no_src_prefix(rust_plugin):
    # Files not under src/ still get crate:: prefix
    assert rust_plugin.module_name("tests/integration.rs") == "crate::tests::integration"


# -- Heuristic stem --

def test_heuristic_test_stem(rust_plugin):
    assert rust_plugin.heuristic_test_stem("test_calculator") == "calculator"
    assert rust_plugin.heuristic_test_stem("calculator_test") == "calculator"
    assert rust_plugin.heuristic_test_stem("calculator") is None
    assert rust_plugin.heuristic_test_stem("utils") is None


# -- Self-call resolution --

def test_resolve_self_calls(rust_plugin):
    assert rust_plugin.resolve_self_calls("Calculator", "self.compute") == "Calculator.compute"
    assert rust_plugin.resolve_self_calls("Calculator", "self.last_result") == "Calculator.last_result"
    assert rust_plugin.resolve_self_calls("Calculator", "add") == "add"


# -- Test output parsing --

def test_parse_cargo_test_output_summary(rust_plugin):
    output = """
running 7 tests
test tests::test_add ... ok
test tests::test_subtract ... ok
test tests::test_multiply ... ok
test tests::test_divide ... ok
test tests::test_divide_by_zero ... ok
test tests::test_calculator_compute ... ok
test tests::test_calculator_last_result ... ok

test result: ok. 7 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
"""
    result = rust_plugin.parse_test_output(output)
    assert result["passed"] == 7
    assert result["failed"] == 0
    assert result["errors"] == 0


def test_parse_cargo_test_output_with_failures(rust_plugin):
    output = """
running 3 tests
test tests::test_add ... ok
test tests::test_subtract ... ok
test tests::test_divide ... FAILED

test result: FAILED. 2 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s
"""
    result = rust_plugin.parse_test_output(output)
    assert result["passed"] == 2
    assert result["failed"] == 1
    assert result["errors"] == 0


def test_parse_cargo_test_output_fallback(rust_plugin):
    """When there is no summary line, fall back to counting individual lines."""
    output = """
test tests::test_add ... ok
test tests::test_subtract ... ok
test tests::test_divide ... FAILED
"""
    result = rust_plugin.parse_test_output(output)
    assert result["passed"] == 2
    assert result["failed"] == 1
    assert result["errors"] == 0


def test_parse_empty_output(rust_plugin):
    result = rust_plugin.parse_test_output("")
    assert result["passed"] == 0
    assert result["failed"] == 0
    assert result["errors"] == 0


# -- Test runner command --

def test_test_runner_command(rust_plugin, sample_rust_repo):
    cmd = rust_plugin.test_runner_command(sample_rust_repo, ["test_add"])
    assert cmd[0] == "cargo"
    assert cmd[1] == "test"
    assert "test_add" in cmd
    assert "--nocapture" in cmd


def test_test_runner_command_multiple(rust_plugin, sample_rust_repo):
    cmd = rust_plugin.test_runner_command(sample_rust_repo, ["test_add", "test_subtract"])
    assert "test_add" in cmd
    assert "test_subtract" in cmd
    assert "--" in cmd


# -- Test class detection --

def test_is_test_class(rust_plugin):
    assert rust_plugin.is_test_class("tests")
    assert rust_plugin.is_test_class("test_helpers")
    assert not rust_plugin.is_test_class("Calculator")
    assert not rust_plugin.is_test_class("utils")
