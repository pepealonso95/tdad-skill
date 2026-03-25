"""Tests for the Dart language plugin."""

import pytest
from pathlib import Path

# Skip all tests if tree-sitter-dart-orchard is not installed
ts = pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
pytest.importorskip("tree_sitter_dart_orchard", reason="tree-sitter-dart-orchard not installed")

from tdad.languages.dart import DartPlugin
from tdad.languages.base import FileInfo


@pytest.fixture
def dart_plugin():
    return DartPlugin()


@pytest.fixture
def sample_dart_repo():
    return Path(__file__).parent / "fixtures" / "sample_dart_repo"


@pytest.fixture
def sample_calculator_dart(sample_dart_repo):
    return sample_dart_repo / "lib" / "calculator.dart"


@pytest.fixture
def sample_utils_dart(sample_dart_repo):
    return sample_dart_repo / "lib" / "utils.dart"


@pytest.fixture
def sample_test_calculator_dart(sample_dart_repo):
    return sample_dart_repo / "test" / "calculator_test.dart"


@pytest.fixture
def sample_test_utils_dart(sample_dart_repo):
    return sample_dart_repo / "test" / "utils_test.dart"


# -- Test file detection --

def test_is_test_file(dart_plugin):
    assert dart_plugin.is_test_file("calculator_test.dart")
    assert dart_plugin.is_test_file("test_calculator.dart")
    assert not dart_plugin.is_test_file("calculator.dart")
    assert not dart_plugin.is_test_file("utils.dart")


def test_is_test_function(dart_plugin):
    assert dart_plugin.is_test_function("test:should add numbers")
    assert dart_plugin.is_test_function("testWidgets:renders widget")
    assert dart_plugin.is_test_function("group")
    assert dart_plugin.is_test_function("setUp")
    assert not dart_plugin.is_test_function("add")
    assert not dart_plugin.is_test_function("compute")


def test_is_test_class(dart_plugin):
    assert dart_plugin.is_test_class("CalculatorTest")
    assert dart_plugin.is_test_class("TestUtils")
    assert not dart_plugin.is_test_class("Calculator")


# -- File parsing --

def test_parse_calculator(dart_plugin, sample_dart_repo, sample_calculator_dart):
    info = dart_plugin.parse_file(sample_calculator_dart, sample_dart_repo)

    assert isinstance(info, FileInfo)
    assert info.name == "calculator.dart"
    assert info.language == "dart"
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

    # Calculator should have methods
    calc_class = next(c for c in info.classes if c.name == "Calculator")
    method_names = [m.name for m in calc_class.methods]
    assert "compute" in method_names

    # Should find AdvancedCalculator extending Calculator
    assert "AdvancedCalculator" in class_names
    adv_class = next(c for c in info.classes if c.name == "AdvancedCalculator")
    assert "Calculator" in adv_class.bases

    # Should detect imports
    assert any("utils" in imp for imp in info.imports)


def test_parse_calculator_calls(dart_plugin, sample_dart_repo, sample_calculator_dart):
    info = dart_plugin.parse_file(sample_calculator_dart, sample_dart_repo)

    # add() should call validateNumber
    add_func = next(f for f in info.functions if f.name == "add")
    assert "validateNumber" in add_func.calls


def test_parse_calculator_docstrings(dart_plugin, sample_dart_repo, sample_calculator_dart):
    info = dart_plugin.parse_file(sample_calculator_dart, sample_dart_repo)

    add_func = next(f for f in info.functions if f.name == "add")
    assert add_func.docstring is not None
    assert "Add two numbers" in add_func.docstring


def test_parse_calculator_constructors(dart_plugin, sample_dart_repo, sample_calculator_dart):
    info = dart_plugin.parse_file(sample_calculator_dart, sample_dart_repo)

    calc_class = next(c for c in info.classes if c.name == "Calculator")
    method_names = [m.name for m in calc_class.methods]
    assert "Calculator" in method_names  # default constructor


def test_parse_utils(dart_plugin, sample_dart_repo, sample_utils_dart):
    info = dart_plugin.parse_file(sample_utils_dart, sample_dart_repo)

    assert not info.is_test_file
    func_names = [f.name for f in info.functions]
    assert "validateNumber" in func_names
    assert "clamp" in func_names

    # clamp should call validateNumber
    clamp_func = next(f for f in info.functions if f.name == "clamp")
    assert "validateNumber" in clamp_func.calls


def test_parse_test_file(dart_plugin, sample_dart_repo, sample_test_calculator_dart):
    info = dart_plugin.parse_file(sample_test_calculator_dart, sample_dart_repo)

    assert info.is_test_file
    assert info.name == "calculator_test.dart"

    # Should find test functions
    test_funcs = [f for f in info.functions if f.is_test]
    assert len(test_funcs) > 0

    # Should have specific test names
    test_names = [f.name for f in test_funcs]
    assert any("should add two numbers" in n for n in test_names)
    assert any("should subtract two numbers" in n for n in test_names)

    # Should have imports
    assert any("calculator" in imp for imp in info.imports)


def test_parse_test_utils(dart_plugin, sample_dart_repo, sample_test_utils_dart):
    info = dart_plugin.parse_file(sample_test_utils_dart, sample_dart_repo)

    assert info.is_test_file
    test_funcs = [f for f in info.functions if f.is_test]
    assert len(test_funcs) > 0


# -- Module name --

def test_module_name(dart_plugin):
    assert dart_plugin.module_name("lib/calculator.dart") == "calculator"
    assert dart_plugin.module_name("lib/src/utils.dart") == "src.utils"
    assert dart_plugin.module_name("test/calculator_test.dart") == "test.calculator_test"


# -- Heuristic stem --

def test_heuristic_test_stem(dart_plugin):
    assert dart_plugin.heuristic_test_stem("calculator_test") == "calculator"
    assert dart_plugin.heuristic_test_stem("test_calculator") == "calculator"
    assert dart_plugin.heuristic_test_stem("calculator") is None


# -- Self-call resolution --

def test_resolve_self_calls(dart_plugin):
    assert dart_plugin.resolve_self_calls("Calculator", "this.compute") == "Calculator.compute"
    assert dart_plugin.resolve_self_calls("Calculator", "add") == "add"


# -- Test output parsing --

def test_parse_dart_test_output_pass(dart_plugin):
    output = """
00:02 +6: All tests passed!
"""
    result = dart_plugin.parse_test_output(output)
    assert result["passed"] == 6
    assert result["failed"] == 0


def test_parse_dart_test_output_with_failures(dart_plugin):
    output = """
00:03 +4 -2: Some tests failed.
"""
    result = dart_plugin.parse_test_output(output)
    assert result["passed"] == 4
    assert result["failed"] == 2


def test_parse_dart_test_output_empty(dart_plugin):
    result = dart_plugin.parse_test_output("")
    assert result["passed"] == 0
    assert result["failed"] == 0


# -- Test runner --

def test_test_runner_command_plain(dart_plugin, tmp_path):
    # No pubspec.yaml → plain dart test
    cmd = dart_plugin.test_runner_command(tmp_path, ["test/calculator_test.dart"])
    assert "dart" in cmd
    assert "test" in cmd
    assert "test/calculator_test.dart" in cmd


def test_test_runner_command_flutter(dart_plugin, tmp_path):
    # With flutter in pubspec
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text("name: myapp\nflutter:\n  sdk: flutter\n")
    cmd = dart_plugin.test_runner_command(tmp_path, ["test/widget_test.dart"])
    assert "flutter" in cmd
    assert "test" in cmd


def test_test_runner_command_dart_with_pubspec(dart_plugin, sample_dart_repo):
    # sample_dart_repo has pubspec.yaml without flutter
    cmd = dart_plugin.test_runner_command(sample_dart_repo, ["test/calculator_test.dart"])
    assert "dart" in cmd
    assert "flutter" not in cmd


# -- Plugin metadata --

def test_file_extensions(dart_plugin):
    assert dart_plugin.file_extensions == {".dart"}


def test_plugin_name(dart_plugin):
    assert dart_plugin.name == "dart"


def test_signature(dart_plugin, sample_dart_repo, sample_calculator_dart):
    info = dart_plugin.parse_file(sample_calculator_dart, sample_dart_repo)
    add_func = next(f for f in info.functions if f.name == "add")
    assert "int" in add_func.signature
    assert "add" in add_func.signature
