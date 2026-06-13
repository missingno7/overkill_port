"""Minimal pytest-free test runner (sandbox lacks pytest/PyPI access).

Discovers test_* functions in tests/test_*.py and runs them sequentially.
"""
import importlib, pathlib, re, subprocess, sys, traceback, types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

lint_script = pathlib.Path(__file__).resolve().parent / "lint.py"
lint_result = subprocess.run([sys.executable, str(lint_script)])
if lint_result.returncode != 0:
    sys.exit(lint_result.returncode)

if "pytest" not in sys.modules:
    class _Raises:
        def __init__(self, exc_type, match=None):
            self.exc_type = exc_type
            self.match = match

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                raise AssertionError(f"did not raise {self.exc_type.__name__}")
            if not issubclass(exc_type, self.exc_type):
                return False
            if self.match is not None and re.search(self.match, str(exc)) is None:
                raise AssertionError(f"exception message did not match {self.match!r}: {exc}")
            return True

    pytest_stub = types.ModuleType("pytest")
    pytest_stub.raises = _Raises
    sys.modules["pytest"] = pytest_stub

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
