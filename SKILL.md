---
name: tdad
description: >-
  Test-driven regression guard for AI coding agents. After every code change,
  look up impacted tests via the .tdad/test_map.txt file and run only the
  affected tests before submitting a patch. Supports Python, JavaScript,
  TypeScript, Go, Java, Rust, and Dart projects. Use when fixing bugs,
  implementing features, or refactoring code to prevent regressions. Activates
  when there is a .tdad/ directory in the repository.
license: MIT
compatibility: >-
  Requires Python 3.10+ and the tdad package (pip install tdad).
  Python projects work out of the box. For JavaScript/TypeScript, Go, Java,
  Rust, or Dart projects, install the appropriate tree-sitter extra
  (e.g., pip install tdad[treesitter-all]).
metadata:
  author: pepealonso95
  version: "0.2.0"
  homepage: https://github.com/pepealonso95/tdad-skill
---

# TDAD — Test-Driven AI Development

Prevent regressions by checking impacted tests before submitting any patch.

## Setup (one-time per repo)

If `.tdad/test_map.txt` does not exist yet:

```bash
pip install tdad
tdad index .
```

This creates `.tdad/test_map.txt` mapping source files to their related tests.

For non-Python projects, install tree-sitter support first:

```bash
pip install tdad[treesitter-all]   # JS/TS, Go, Java, Rust, Dart
tdad index .                       # auto-detects languages
```

Or target specific languages:

```bash
tdad index . --languages python,javascript
```

## Bug Fix / Feature Workflow

### 1. Make the change

Read the source, identify the root cause or feature location, and make the minimal change needed.

### 2. Find impacted tests

For **each file you changed**, look up its tests:

```bash
grep 'path/to/changed_file' .tdad/test_map.txt
```

Output format: `source_file: test_a test_b test_c`

Collect all unique test files from every changed source file.

### 3. Run impacted tests

Pick the right runner for the project:

```bash
# Python
python -m pytest <test_files> -x -q 2>&1 | head -50

# JavaScript/TypeScript
npx jest <test_files> 2>&1 | head -50

# Go
go test -run 'TestName' -v ./... 2>&1 | head -50

# Java (Maven)
mvn test -Dtest=TestClass 2>&1 | tail -30

# Rust
cargo test test_name 2>&1 | head -50

# Dart
dart test <test_files> 2>&1 | head -50
```

- If all tests pass, proceed to step 4.
- If any test fails, diagnose and fix before proceeding. Re-run until green.

### 4. Write a regression test

**Every change must include at least one new test** that covers the specific behavior being added or fixed. This test will catch future regressions.

- **Bug fix:** Write a test that reproduces the original bug. It should fail without your fix and pass with it.
- **New feature:** Write a test that exercises the new code path. Cover the main behavior and at least one edge case.
- **Refactor:** If existing tests already cover the refactored behavior, confirm they still pass. If the refactor changes an interface or adds a new code path, add a test for it.

Place the new test in the appropriate test file following the project's conventions:

**Python:** `tests/test_<module>.py` — add a `test_<description>` function
**JavaScript/TypeScript:** `<module>.test.js` or `<module>.spec.ts` — add a `test('description', ...)` block
**Go:** `<module>_test.go` — add a `func Test<Description>(t *testing.T)` function
**Java:** `<Module>Test.java` — add a `@Test void test<Description>()` method
**Rust:** `#[test] fn test_<description>()` in the same file or `tests/` directory
**Dart:** `test/<module>_test.dart` — add a `test('description', ...)` block

### 5. Run all impacted tests + the new test

Re-run the impacted tests together with the new test to confirm everything passes:

```bash
# Example (Python)
python -m pytest <impacted_test_files> <new_test_file> -x -q 2>&1 | head -50
```

All tests — existing and new — must pass before submitting.

### 6. If test_map.txt has no entry

Fall back to finding tests by convention:

**Python:** `src/foo/bar.py` → `tests/test_bar.py`
**JavaScript/TypeScript:** `src/calculator.js` → `tests/calculator.test.js` or `tests/calculator.spec.ts`
**Go:** `calculator/calculator.go` → `calculator/calculator_test.go`
**Java:** `src/main/java/Foo.java` → `src/test/java/FooTest.java`
**Rust:** look for `#[cfg(test)]` module in the same file, or `tests/` directory
**Dart:** `lib/calculator.dart` → `test/calculator_test.dart`

Or search for imports: `grep -r 'changed_module' tests/`

## Rules

- **Never submit a patch without running impacted tests first.**
- **Every change must include a new test** that covers the fix or feature. No exceptions for bug fixes — the test proves the bug existed and is now fixed.
- Run the minimum set of tests needed (not the full suite) for speed.
- If `.tdad/test_map.txt` is missing and `tdad` is not installed, use the naming convention fallback in step 6.
