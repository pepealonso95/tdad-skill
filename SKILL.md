---
name: tdad
---

## Bug Fix Workflow

1. **Fix the bug**: Read the source, identify the root cause, make the minimal change.

2. **Find related tests**: Look up tests for each file you changed:
   ```bash
   grep 'path/to/changed_file.py' .tdad/test_map.txt
   ```
   Output format: `source.py: test1.py test2.py`

3. **Verify**: Run the matched tests:
   ```bash
   python -m pytest <test_files> -x -q 2>&1 | head -50
   ```
   If tests fail, adjust and re-run.
