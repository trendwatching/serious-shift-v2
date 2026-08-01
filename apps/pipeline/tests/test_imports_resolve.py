"""
Every import in the package must resolve — including the deferred ones.

Splitting `steps/scraper.py` into a package moved its modules one level deeper,
so `from ..core import …` became wrong. The module-level imports were caught
immediately; three *function-local* ones inside the paper handlers were not,
because nothing imports a function body. They failed only at runtime, on the
weekly cron, against arXiv and OpenAlex — and the only reason that surfaced at
all is that errors now persist to Postgres.

Static, so it needs no database, no network and no API key.
"""
import ast
import importlib
import pkgutil

import serious_shift_pipeline as pkg


def _modules():
    return [m.name for m in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + ".")]


def test_every_module_imports():
    failures = []
    for name in _modules():
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 — collecting, then reporting all
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, "modules failed to import:\n  " + "\n  ".join(failures)


def _relative_imports(module):
    """Every `from .x import y` in a module, as (level, module_name, lineno)."""
    src = importlib.import_module(module)
    if not getattr(src, "__file__", None) or not src.__file__.endswith(".py"):
        return []
    tree = ast.parse(open(src.__file__, encoding="utf-8").read())
    return [
        (n.level, n.module, n.lineno)
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.level
    ]


def test_every_relative_import_resolves():
    """Resolve each relative import against its package, at its own depth.

    This is the check that would have caught the split: a `from ..core import x`
    sitting inside a function three packages deep parses fine, imports fine at
    module level, and only explodes when that function is called.
    """
    failures = []
    for name in _modules():
        parts = name.split(".")
        # One dot means "my own package". For a plain module that is its parent;
        # for a package's __init__ it is the package itself, so it keeps one
        # more component. Getting this wrong flags every `from .x` in an
        # __init__.py as broken.
        is_pkg = hasattr(importlib.import_module(name), "__path__")
        anchor = parts if is_pkg else parts[:-1]

        for level, target, lineno in _relative_imports(name):
            up = level - 1
            base = anchor[: len(anchor) - up] if up <= len(anchor) else []
            if not base:
                failures.append(f"{name}:{lineno}: {'.' * level}{target or ''} escapes the package")
                continue
            resolved = ".".join(base + ([target] if target else []))
            try:
                importlib.import_module(resolved)
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    f"{name}:{lineno}: {'.' * level}{target or ''} → "
                    f"{resolved} ({type(exc).__name__})"
                )
    assert not failures, "unresolvable relative imports:\n  " + "\n  ".join(failures)
