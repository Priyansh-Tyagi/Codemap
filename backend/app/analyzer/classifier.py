"""
Import classifier.

Decides whether a raw import specifier (as extracted by the Babel parser
bridge) refers to a LOCAL project file or an EXTERNAL package (npm, node
built-in, etc). Only local specifiers become graph edges.
"""

from __future__ import annotations


def is_local_specifier(specifier: str) -> bool:
    """
    Local specifiers start with '.' (./foo, ../foo) or '/' (absolute-from-root,
    rare but valid in some configs). Everything else - bare names like "react",
    "@scope/pkg", "node:fs" - is treated as external.

    Deliberately NOT resolving tsconfig `paths` aliases (e.g. "@/components/Button")
    in the MVP - documented limitation. They'll be classified as external here.
    """
    specifier = specifier.strip()
    if not specifier:
        return False
    return specifier.startswith(".") or specifier.startswith("/")


def classify_imports(raw_imports: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split a file's raw import list (as produced by parse.js) into
    (local_imports, external_imports). Each item keeps its original
    {specifier, type} shape.
    """
    local: list[dict] = []
    external: list[dict] = []
    for imp in raw_imports:
        specifier = imp.get("specifier", "")
        if is_local_specifier(specifier):
            local.append(imp)
        else:
            external.append(imp)
    return local, external
