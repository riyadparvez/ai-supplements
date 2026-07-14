#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_refactor import verify


class VerifyRefactorTests(unittest.TestCase):
    def check(self, before: str, after: str, before_file: str = "sample.py"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / "old", root / "new"
            old.mkdir()
            new.mkdir()
            (old / before_file).write_text(before)
            (new / before_file).write_text(after)
            return verify(old, new)

    def test_allows_rename_and_import(self):
        violations, mappings = self.check(
            "def old(x):\n    return x + 1\n\ny = old(2)\n",
            "import math\n\ndef new(x):\n    return x + 1\n\ny = new(2)\n",
        )
        self.assertEqual([], violations)
        self.assertEqual({"sample.py": {"old": "new"}}, mappings)

    def test_rejects_added_line_in_function(self):
        violations, _ = self.check(
            "def f(x):\n    return x\n",
            "def f(x):\n    x += 1\n    return x\n",
        )
        self.assertTrue(any(v.rule in {"ast-change", "function-body"} for v in violations))

    def test_rejects_commenting_out_code(self):
        violations, _ = self.check(
            "def f(x):\n    return x\n",
            "def f(x):\n    # return x\n    pass\n",
        )
        self.assertTrue(any(v.rule == "comments" for v in violations))

    def test_rejects_uncommenting_code(self):
        violations, _ = self.check(
            "def f(x):\n    # return x\n    pass\n",
            "def f(x):\n    return x\n",
        )
        self.assertTrue(any(v.rule == "comments" for v in violations))

    def test_rejects_non_call_identifier_change(self):
        violations, _ = self.check(
            "def f(value):\n    return value\n",
            "def f(item):\n    return item\n",
        )
        self.assertTrue(violations)

    def test_rejects_variable_rename_unrelated_to_function(self):
        """Renaming a variable that is NOT the function is rejected."""
        violations, _ = self.check(
            "def func(): pass\nresult = func()\n",
            "def func(): pass\nresult2 = func()\n",
        )
        # Variable rename (result -> result2) without function rename is rejected
        self.assertTrue(any(v.rule in {"ast-change", "function-body"} for v in violations))

    def test_allows_method_rename_in_class(self):
        """Function renames work inside classes."""
        violations, mappings = self.check(
            "class C:\n    def method(self): pass\nc = C()\nc.method()\n",
            "class C:\n    def renamed_method(self): pass\nc = C()\nc.renamed_method()\n",
        )
        self.assertEqual([], violations)
        self.assertIn("method", str(mappings))

    def test_allows_nested_function_rename(self):
        """Nested function renames are allowed."""
        violations, mappings = self.check(
            "def outer():\n    def inner(): pass\n    inner()\nouter()\n",
            "def outer():\n    def renamed_inner(): pass\n    renamed_inner()\nouter()\n",
        )
        self.assertEqual([], violations)

    def test_rejects_removed_import(self):
        """Removing imports is not allowed."""
        violations, _ = self.check(
            "import sys\nprint(sys.version)\n",
            "print('version')\n",
        )
        self.assertTrue(any(v.rule == "imports" for v in violations))

    def test_rejects_modified_import(self):
        """Modifying imports is not allowed."""
        violations, _ = self.check(
            "import os\nprint(os.name)\n",
            "import sys\nprint(os.name)\n",
        )
        self.assertTrue(any(v.rule == "imports" for v in violations))

    def test_allows_new_import_addition(self):
        """Adding new imports is allowed."""
        violations, _ = self.check(
            "print('hello')\n",
            "import sys\nprint('hello')\n",
        )
        self.assertEqual([], violations)

    def test_rejects_function_added(self):
        """Adding new functions is not allowed."""
        violations, _ = self.check(
            "def f(): pass\n",
            "def f(): pass\ndef g(): pass\n",
        )
        self.assertTrue(any(v.rule == "function-count" for v in violations))

    def test_rejects_function_removed(self):
        """Removing functions is not allowed."""
        violations, _ = self.check(
            "def f(): pass\ndef g(): pass\n",
            "def f(): pass\n",
        )
        self.assertTrue(any(v.rule == "function-count" for v in violations))

    def test_allows_whitespace_only_change(self):
        """Extra whitespace between tokens is not itself a violation (tokenize ignores it)."""
        violations, _ = self.check(
            "def f(x):\n    return x\n",
            "def f(x):\n    return  x\n",
        )
        self.assertEqual([], violations)

    def test_rejects_inconsistent_renames(self):
        """One function renamed to multiple different names."""
        violations, _ = self.check(
            "def old():\n    pass\n",
            "def new1():\n    pass\ndef new2():\n    pass\n",
        )
        self.assertTrue(violations)

    def test_rejects_rename_collision(self):
        """Multiple functions renamed to the same name."""
        violations, _ = self.check(
            "def f1(): pass\ndef f2(): pass\n",
            "def same(): pass\ndef same(): pass\n",
        )
        self.assertTrue(any(v.rule == "rename-collision" for v in violations))

    def test_allows_multiple_files_with_renames(self):
        """Renames in multiple files are allowed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / "old", root / "new"
            old.mkdir()
            new.mkdir()
            (old / "a.py").write_text("def old_a(): pass\nx = old_a()\n")
            (old / "b.py").write_text("def old_b(): pass\ny = old_b()\n")
            (new / "a.py").write_text("def new_a(): pass\nx = new_a()\n")
            (new / "b.py").write_text("def new_b(): pass\ny = new_b()\n")
            violations, mappings = verify(old, new)
            self.assertEqual([], violations)
            self.assertEqual(2, len(mappings))

    def test_rejects_file_added(self):
        """Adding files is not allowed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / "old", root / "new"
            old.mkdir()
            new.mkdir()
            (old / "a.py").write_text("def f(): pass\n")
            (new / "a.py").write_text("def f(): pass\n")
            (new / "b.py").write_text("def g(): pass\n")
            violations, _ = verify(old, new)
            self.assertTrue(any(v.rule == "file-added" for v in violations))

    def test_rejects_file_removed(self):
        """Removing files is not allowed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / "old", root / "new"
            old.mkdir()
            new.mkdir()
            (old / "a.py").write_text("def f(): pass\n")
            (old / "b.py").write_text("def g(): pass\n")
            (new / "a.py").write_text("def f(): pass\n")
            violations, _ = verify(old, new)
            self.assertTrue(any(v.rule == "file-removed" for v in violations))

    def test_allows_async_function_rename(self):
        """Async function renames are allowed."""
        violations, mappings = self.check(
            "async def old_async():\n    pass\nawait old_async()\n",
            "async def new_async():\n    pass\nawait new_async()\n",
        )
        self.assertEqual([], violations)

    def test_rejects_decorator_change(self):
        """Changing decorators is not allowed."""
        violations, _ = self.check(
            "def f(): pass\n",
            "@decorator\ndef f(): pass\n",
        )
        self.assertTrue(violations)

    def test_rejects_parameter_default_change(self):
        """Changing parameter defaults is not allowed."""
        violations, _ = self.check(
            "def f(x=1): return x\n",
            "def f(x=2): return x\n",
        )
        self.assertTrue(violations)

    def test_rejects_type_annotation_change(self):
        """Changing type annotations is not allowed."""
        violations, _ = self.check(
            "def f(x: int) -> int: return x\n",
            "def f(x: str) -> str: return x\n",
        )
        self.assertTrue(violations)

    def test_documents_identifier_masking_limitation(self):
        """Known limitation: renames are applied as global text substitution, not
        scope-aware. An unrelated local variable that happens to collide with the
        renamed function's old/new name gets silently masked instead of flagged.

        Here `other`'s local variable `calc` (unrelated to the module-level `calc`
        function) is illegitimately renamed to `helper` alongside the sanctioned
        `calc` -> `helper` function rename. The verifier cannot tell the two apart
        and reports no violations. This test pins the current (buggy) behavior so
        a future scope-aware fix is a deliberate, visible change to this test.
        """
        violations, _ = self.check(
            "def calc(x):\n    return x\n\ndef other():\n    calc = 5\n    return calc\n\ny = calc(2)\n",
            "def helper(x):\n    return x\n\ndef other():\n    helper = 5\n    return helper\n\ny = helper(2)\n",
        )
        self.assertEqual([], violations)

    def test_violation_includes_line_number(self):
        """Violations include line number information."""
        violations, _ = self.check(
            "def f(x):\n    return x\n",
            "def f(x):\n    return x + 1\n",
        )
        self.assertTrue(violations)
        # At least one violation should have a line number
        self.assertTrue(any(v.line is not None for v in violations))


if __name__ == "__main__":
    unittest.main()
