"""Minimal pytest-free test runner (sandbox lacks pytest/PyPI access).

Discovers test_* functions in tests/test_*.py and runs them sequentially.
"""
import importlib, pathlib, sys, traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

failed = passed = 0
for path in sorted(pathlib.Path(__file__).resolve().parents[1].glob("tests/test_*.py")):
    mod = importlib.import_module(f"tests.{path.stem}")
    for name in sorted(dir(mod)):
        if name.startswith("test_") and callable(getattr(mod, name)):
            try:
                getattr(mod, name)()
                passed += 1
            except Exception:
                failed += 1
                print(f"FAIL {path.stem}::{name}")
                traceback.print_exc()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
