"""Tests for the Java language plugin."""

import pytest
from pathlib import Path

# Skip all tests if tree-sitter is not installed
ts = pytest.importorskip("tree_sitter", reason="tree-sitter not installed")
pytest.importorskip("tree_sitter_java", reason="tree-sitter-java not installed")

from tdad.languages.java import JavaPlugin
from tdad.languages.base import FileInfo


@pytest.fixture
def java_plugin():
    return JavaPlugin()


@pytest.fixture
def sample_java_repo():
    return Path(__file__).parent / "fixtures" / "sample_java_repo"


@pytest.fixture
def sample_calculator_java(sample_java_repo):
    return sample_java_repo / "src" / "main" / "java" / "calculator" / "Calculator.java"


@pytest.fixture
def sample_utils_java(sample_java_repo):
    return sample_java_repo / "src" / "main" / "java" / "utils" / "Utils.java"


@pytest.fixture
def sample_test_calculator_java(sample_java_repo):
    return sample_java_repo / "src" / "test" / "java" / "calculator" / "CalculatorTest.java"


@pytest.fixture
def sample_test_utils_java(sample_java_repo):
    return sample_java_repo / "src" / "test" / "java" / "utils" / "UtilsTest.java"


# -- Test file detection --

def test_is_test_file(java_plugin):
    assert java_plugin.is_test_file("CalculatorTest.java")
    assert java_plugin.is_test_file("TestCalculator.java")
    assert java_plugin.is_test_file("CalculatorTests.java")
    assert java_plugin.is_test_file("CalculatorTestCase.java")
    assert not java_plugin.is_test_file("Calculator.java")
    assert not java_plugin.is_test_file("Utils.java")


def test_is_test_function(java_plugin):
    assert java_plugin.is_test_function("testAdd")
    assert java_plugin.is_test_function("testSubtract")
    assert not java_plugin.is_test_function("add")
    assert not java_plugin.is_test_function("getLastResult")


def test_is_test_class(java_plugin):
    assert java_plugin.is_test_class("CalculatorTest")
    assert java_plugin.is_test_class("TestCalculator")
    assert java_plugin.is_test_class("CalculatorTests")
    assert java_plugin.is_test_class("CalculatorTestCase")
    assert not java_plugin.is_test_class("Calculator")
    assert not java_plugin.is_test_class("Utils")


# -- File parsing --

def test_parse_calculator(java_plugin, sample_java_repo, sample_calculator_java):
    info = java_plugin.parse_file(sample_calculator_java, sample_java_repo)

    assert isinstance(info, FileInfo)
    assert info.name == "Calculator.java"
    assert info.language == "java"
    assert not info.is_test_file
    assert info.content_hash

    # Should find Calculator class
    class_names = [c.name for c in info.classes]
    assert "Calculator" in class_names

    # Calculator class should have methods
    calc_class = next(c for c in info.classes if c.name == "Calculator")
    method_names = [m.name for m in calc_class.methods]
    assert "Calculator" in method_names  # constructor
    assert "add" in method_names
    assert "subtract" in method_names
    assert "getLastResult" in method_names

    # Should detect imports
    assert any("utils.Utils" in imp for imp in info.imports)


def test_parse_utils(java_plugin, sample_java_repo, sample_utils_java):
    info = java_plugin.parse_file(sample_utils_java, sample_java_repo)

    assert not info.is_test_file

    # Should find Utils class
    class_names = [c.name for c in info.classes]
    assert "Utils" in class_names

    utils_class = next(c for c in info.classes if c.name == "Utils")
    method_names = [m.name for m in utils_class.methods]
    assert "validateNumber" in method_names
    assert "clamp" in method_names

    # clamp should call validateNumber
    clamp_method = next(m for m in utils_class.methods if m.name == "clamp")
    assert "validateNumber" in clamp_method.calls


def test_parse_test_file(java_plugin, sample_java_repo, sample_test_calculator_java):
    info = java_plugin.parse_file(sample_test_calculator_java, sample_java_repo)

    assert info.is_test_file
    assert info.name == "CalculatorTest.java"

    # Should find CalculatorTest class
    class_names = [c.name for c in info.classes]
    assert "CalculatorTest" in class_names

    # Methods with @Test annotation should be detected as tests
    test_class = next(c for c in info.classes if c.name == "CalculatorTest")
    test_methods = [m for m in test_class.methods if m.is_test]
    test_method_names = [m.name for m in test_methods]
    assert "testAdd" in test_method_names
    assert "testSubtract" in test_method_names
    assert "testLastResult" in test_method_names
    assert len(test_methods) == 3


def test_parse_test_utils(java_plugin, sample_java_repo, sample_test_utils_java):
    info = java_plugin.parse_file(sample_test_utils_java, sample_java_repo)

    assert info.is_test_file
    test_class = next(c for c in info.classes if c.name == "UtilsTest")
    test_methods = [m for m in test_class.methods if m.is_test]
    assert len(test_methods) == 3


def test_parse_file_has_javadoc(java_plugin, sample_java_repo, sample_calculator_java):
    info = java_plugin.parse_file(sample_calculator_java, sample_java_repo)

    calc_class = next(c for c in info.classes if c.name == "Calculator")
    assert calc_class.docstring is not None
    assert "Simple calculator" in calc_class.docstring

    # Check method docstrings
    add_method = next(m for m in calc_class.methods if m.name == "add")
    assert add_method.docstring is not None
    assert "Add two numbers" in add_method.docstring


def test_parse_file_line_numbers(java_plugin, sample_java_repo, sample_calculator_java):
    info = java_plugin.parse_file(sample_calculator_java, sample_java_repo)

    calc_class = next(c for c in info.classes if c.name == "Calculator")
    # Class should start after the imports and package declaration
    assert calc_class.start_line > 1
    assert calc_class.end_line > calc_class.start_line

    # Methods should have sensible line ranges
    for method in calc_class.methods:
        assert method.start_line >= calc_class.start_line
        assert method.end_line <= calc_class.end_line
        assert method.end_line >= method.start_line


# -- Module name --

def test_module_name_from_source(java_plugin):
    source = 'package calculator;\n\npublic class Calculator {}\n'
    assert java_plugin.module_name("src/main/java/calculator/Calculator.java", source=source) == "calculator"


def test_module_name_from_path(java_plugin):
    assert java_plugin.module_name("src/main/java/calculator/Calculator.java") == "calculator.Calculator"
    assert java_plugin.module_name("src/test/java/utils/UtilsTest.java") == "utils.UtilsTest"


def test_module_name_no_standard_prefix(java_plugin):
    assert java_plugin.module_name("com/example/Foo.java") == "com.example.Foo"


# -- Heuristic stem --

def test_heuristic_test_stem(java_plugin):
    assert java_plugin.heuristic_test_stem("CalculatorTest") == "Calculator"
    assert java_plugin.heuristic_test_stem("TestCalculator") == "Calculator"
    assert java_plugin.heuristic_test_stem("CalculatorTests") == "Calculator"
    assert java_plugin.heuristic_test_stem("CalculatorTestCase") == "Calculator"
    assert java_plugin.heuristic_test_stem("Calculator") is None


# -- Self-call resolution --

def test_resolve_self_calls(java_plugin):
    assert java_plugin.resolve_self_calls("Calculator", "this.add") == "Calculator.add"
    assert java_plugin.resolve_self_calls("Calculator", "Utils.validate") == "Utils.validate"


# -- Test output parsing --

def test_parse_maven_output(java_plugin):
    output = """
[INFO] -------------------------------------------------------
[INFO]  T E S T S
[INFO] -------------------------------------------------------
[INFO] Running calculator.CalculatorTest
[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
[INFO] Results:
[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
[INFO] BUILD SUCCESS
"""
    result = java_plugin.parse_test_output(output)
    assert result["passed"] == 3
    assert result["failed"] == 0
    assert result["errors"] == 0


def test_parse_maven_output_with_failures(java_plugin):
    output = """
[INFO] Running calculator.CalculatorTest
[INFO] Tests run: 5, Failures: 1, Errors: 1, Skipped: 0
"""
    result = java_plugin.parse_test_output(output)
    assert result["passed"] == 3
    assert result["failed"] == 1
    assert result["errors"] == 1


def test_parse_gradle_output(java_plugin):
    output = """
> Task :test
calculator.CalculatorTest > testAdd PASSED
calculator.CalculatorTest > testSubtract PASSED
calculator.CalculatorTest > testLastResult FAILED

3 tests completed, 1 failed
"""
    result = java_plugin.parse_test_output(output)
    assert result["passed"] == 2
    assert result["failed"] == 1


def test_parse_gradle_output_all_pass(java_plugin):
    output = """
> Task :test
3 tests completed
BUILD SUCCESSFUL
"""
    result = java_plugin.parse_test_output(output)
    assert result["passed"] == 3
    assert result["failed"] == 0


# -- Build tool detection --

def test_detect_maven(java_plugin, sample_java_repo):
    runner = java_plugin._detect_build_tool(sample_java_repo)
    assert runner == "maven"


def test_detect_gradle(java_plugin, tmp_path):
    (tmp_path / "build.gradle").write_text("apply plugin: 'java'\n")
    runner = java_plugin._detect_build_tool(tmp_path)
    assert runner == "gradle"


def test_detect_gradle_kts(java_plugin, tmp_path):
    (tmp_path / "build.gradle.kts").write_text("plugins { java }\n")
    runner = java_plugin._detect_build_tool(tmp_path)
    assert runner == "gradle"


# -- Test runner command --

def test_test_runner_command_maven(java_plugin, sample_java_repo):
    cmd = java_plugin.test_runner_command(sample_java_repo, ["calculator.CalculatorTest"])
    assert cmd[0] == "mvn"
    assert "test" in cmd
    assert "-Dtest=calculator.CalculatorTest" in cmd


def test_test_runner_command_gradle(java_plugin, tmp_path):
    (tmp_path / "build.gradle").write_text("apply plugin: 'java'\n")
    cmd = java_plugin.test_runner_command(tmp_path, ["calculator.CalculatorTest"])
    assert cmd[0] == "gradle"
    assert "test" in cmd
    assert "--tests" in cmd
    assert "calculator.CalculatorTest" in cmd


# -- File extensions and name --

def test_file_extensions(java_plugin):
    assert java_plugin.file_extensions == {".java"}


def test_plugin_name(java_plugin):
    assert java_plugin.name == "java"
