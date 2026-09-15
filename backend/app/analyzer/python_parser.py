"""
Python import parser.

Uses the stdlib `ast` module directly - unlike the JS pipeline, this needs
no subprocess. Python ships its own real parser; we don't need Babel's
equivalent for a second language.

Output is intentionally NOT forced into the same {specifier, type, symbols}
shape the JS parser uses. Python's import statements carry structurally
different information (relative-import "level", and a `from X import a, b`
statement resolves to ONE target module with MULTIPLE symbols, whereas
`from . import a, b` resolves to TWO separate target submodules with no
shared parent) that doesn't map cleanly onto a single string "specifier".
Rather than force-fit it, every raw import statement is flattened here into
a uniform list of:

    {"module_path": "foo.bar", "level": 0, "symbols": ["baz"]}

where module_path is a dotted path representing exactly ONE resolution
target (never a comma-separated list), and level is 0 for an absolute
import or N for N dots of relative-ness (matching ast.ImportFrom.level:
1 = "from .", 2 = "from ..", etc). The Python resolver (python_resolver.py)
consumes this shape directly.
"""

from __future__ import annotations

import ast


def _flatten_import(node: ast.Import) -> list[dict]:
    """
    `import foo.bar, baz.qux` -> TWO independent records, one per name.
    Each is always level=0 (plain `import` is never relative in Python).

    Symbol is always the real dotted module path (alias.name), never the
    local `as` alias - same principle as the JS parser: report what the
    edge actually points at, not what the importing file calls it locally.
    """
    records = []
    for alias in node.names:
        records.append({"module_path": alias.name, "level": 0, "symbols": [alias.name]})
    return records


def _flatten_import_from(node: ast.ImportFrom) -> list[dict]:
    """
    Two genuinely different shapes, both spelled `from X import ...`:

    `from foo.bar import a, b`  -> module="foo.bar" (not None): ONE record,
        module_path="foo.bar", symbols=["a", "b"] - a and b are names
        DEFINED IN that one resolved module (source-side names, not any
        local `as` aliases - same principle as above).

    `from . import a, b`  -> module=None: TWO records, module_path="a" and
        module_path="b" separately - here a and b are each themselves a
        SUBMODULE being imported, not names within a shared module, so each
        needs its own resolution target.
    """
    if node.module is not None:
        symbols = [alias.name for alias in node.names]
        return [{"module_path": node.module, "level": node.level, "symbols": symbols}]

    records = []
    for alias in node.names:
        records.append({"module_path": alias.name, "level": node.level, "symbols": ["*"]})
    return records


def parse_python_file(absolute_path: str) -> dict:
    result = {
        "filePath": absolute_path,
        "linesOfCode": 0,
        "imports": [],
        "error": None,
    }

    try:
        with open(absolute_path, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError) as e:
        result["error"] = f"read failed: {e}"
        return result

    result["linesOfCode"] = source.count("\n") + 1

    try:
        tree = ast.parse(source, filename=absolute_path)
    except SyntaxError as e:
        result["error"] = f"parse failed: {e}"
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result["imports"].extend(_flatten_import(node))
        elif isinstance(node, ast.ImportFrom):
            result["imports"].extend(_flatten_import_from(node))

    return result


def parse_python_files(file_paths: list[str]) -> list[dict]:
    return [parse_python_file(p) for p in file_paths]
