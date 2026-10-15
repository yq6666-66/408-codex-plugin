from __future__ import annotations

import ast
import unittest
from pathlib import Path


TESTS = Path(__file__).resolve().parent


def duplicate_test_methods(source: str, filename: str) -> list[str]:
    """Find test methods that Python would silently replace in a class body."""
    tree = ast.parse(source, filename=filename)
    duplicates: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        first_lines: dict[str, int] = {}
        for method in node.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not method.name.startswith("test_"):
                continue
            if method.name in first_lines:
                duplicates.append(
                    f"{filename}:{method.lineno}: {node.name}.{method.name} "
                    f"replaces definition at line {first_lines[method.name]}"
                )
            else:
                first_lines[method.name] = method.lineno
    return duplicates


class TestDiscoveryContractTests(unittest.TestCase):
    def test_repository_has_no_shadowed_test_methods(self) -> None:
        duplicates: list[str] = []
        for path in sorted(TESTS.rglob("test*.py")):
            duplicates.extend(
                duplicate_test_methods(path.read_text(encoding="utf-8"), path.relative_to(TESTS).as_posix())
            )
        self.assertEqual(duplicates, [], "\n".join(duplicates))

    def test_duplicate_sync_and_async_methods_are_reported_with_locations(self) -> None:
        source = (
            "class Example:\n"
            "    def test_hidden(self): pass\n"
            "    async def test_hidden(self): pass\n"
        )
        self.assertEqual(duplicate_test_methods(source, "fixture.py"), [
            "fixture.py:3: Example.test_hidden replaces definition at line 2",
        ])

    def test_same_test_name_in_distinct_classes_is_allowed(self) -> None:
        source = (
            "class First:\n"
            "    def test_shared(self): pass\n"
            "    def helper(self): pass\n"
            "    def helper(self): pass\n"
            "class Second:\n"
            "    def test_shared(self): pass\n"
        )
        self.assertEqual(duplicate_test_methods(source, "fixture.py"), [])


if __name__ == "__main__":
    unittest.main()
