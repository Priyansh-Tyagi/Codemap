"""
Path-alias resolution for JS/TS imports like `@/lib/utils` or `~/components/Button`.

Why this exists: the plain classifier treats every non-relative specifier as an
external npm package. That is wrong for the (very common) projects that map a
prefix onto their own source tree - shadcn/ui, Vite and Next.js templates all
do - and it silently drops real edges from the graph and inflates the
"external dependency" count with the project's own files.

Where aliases are read from, nearest-config-first (so monorepo packages each
use their own config):
  1. tsconfig*.json / jsconfig.json  `compilerOptions.paths` + `baseUrl`
     (JSONC tolerated: comments, trailing commas; `extends` followed)
  2. vite.config.*  `resolve.alias` (object or array form, best-effort static
     read - the config is never executed)
  3. Fallback: `@/...` -> the nearest `src/` directory. An npm scope cannot be
     empty, so `@/x` is never a real package; guessing is safe.

Design notes:
  - One AliasResolver is built per analysis run and caches parsed configs for
    that run only. Nothing is cached across runs: users edit their configs,
    and a stale cache would silently show a wrong graph (same reasoning as
    never caching local-path analyses).
  - File matching (extensions, index files, project-root containment) is
    delegated to resolver.resolve_candidate, identical to relative imports.
  - A specifier that matches an alias pointing INSIDE the project but finds no
    file is reported UNRESOLVED (a genuinely broken import). One that merely
    isn't an alias at all stays NOT_ALIAS and is counted as external.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum

from analyzer.resolver import resolve_candidate

TS_CONFIG_NAMES = ["tsconfig.json", "tsconfig.app.json", "tsconfig.base.json", "jsconfig.json"]
VITE_CONFIG_NAMES = [f"vite.config.{e}" for e in ("ts", "js", "mjs", "cjs", "mts", "cts")]

# Used by the GitHub tarball extractor so config files actually reach disk
# (it otherwise extracts only scannable source files).
ALIAS_CONFIG_FILE_RE = re.compile(
    r"^(?:(?:tsconfig|jsconfig)[\w.\-]*\.json|vite\.config\.(?:js|ts|mjs|cjs|mts|cts))$",
    re.IGNORECASE,
)

_MAX_EXTENDS_DEPTH = 8


class AliasStatus(str, Enum):
    LOCAL = "local"            # resolved to a project file
    UNRESOLVED = "unresolved"  # clearly an in-project alias, but no such file
    NOT_ALIAS = "not_alias"    # not an alias: treat as an external package


# --------------------------------------------------------------------------
# JSONC / JS text helpers (string-aware, so "http://x" is never a comment)
# --------------------------------------------------------------------------

def _strip_comments(text: str, quotes: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    quote = ""
    while i < n:
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = ""
            i += 1
            continue
        if c in quotes:
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        elif c == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(c)
        i += 1
    return "".join(out)


def parse_jsonc(text: str) -> dict | None:
    """Parse tsconfig-style JSON (comments + trailing commas). None on failure."""
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        data = json.loads(_strip_trailing_commas(_strip_comments(text, '"')))
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _read(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


# --------------------------------------------------------------------------
# tsconfig / jsconfig
# --------------------------------------------------------------------------

@dataclass
class _TsOptions:
    base_url: str | None = None          # absolute
    paths: dict[str, list[str]] | None = None
    paths_dir: str | None = None         # dir of the config that defined `paths`


def _resolve_extends(config_dir: str, ref: str) -> str | None:
    if not ref.startswith("."):
        return None  # package-based preset (would live in node_modules)
    path = os.path.normpath(os.path.join(config_dir, ref))
    for candidate in (path, path + ".json"):
        if os.path.isfile(candidate):
            return candidate
    return None


def _load_ts_options(path: str, seen: frozenset[str] = frozenset(), depth: int = 0) -> _TsOptions:
    result = _TsOptions()
    real = os.path.abspath(path)
    if real in seen or depth > _MAX_EXTENDS_DEPTH:
        return result
    text = _read(real)
    data = parse_jsonc(text) if text is not None else None
    if data is None:
        return result

    config_dir = os.path.dirname(real)
    seen = seen | {real}

    extends = data.get("extends")
    refs = [extends] if isinstance(extends, str) else (extends if isinstance(extends, list) else [])
    for ref in refs:
        if not isinstance(ref, str):
            continue
        parent_path = _resolve_extends(config_dir, ref)
        if parent_path is None:
            continue
        parent = _load_ts_options(parent_path, seen, depth + 1)
        if parent.base_url is not None:
            result.base_url = parent.base_url
        if parent.paths is not None:
            result.paths, result.paths_dir = parent.paths, parent.paths_dir

    opts = data.get("compilerOptions")
    if isinstance(opts, dict):
        base_url = opts.get("baseUrl")
        if isinstance(base_url, str):
            result.base_url = os.path.normpath(os.path.join(config_dir, base_url))
        paths = opts.get("paths")
        if isinstance(paths, dict):
            clean = {
                k: [t for t in v if isinstance(t, str)]
                for k, v in paths.items()
                if isinstance(v, list)
            }
            result.paths, result.paths_dir = clean, config_dir
    return result


# --------------------------------------------------------------------------
# vite.config.* (static, best-effort - the file is never executed)
# --------------------------------------------------------------------------

def _balanced_block(text: str, open_idx: int) -> str | None:
    pairs = {"{": "}", "[": "]", "(": ")"}
    stack = [pairs[text[open_idx]]]
    i, n = open_idx + 1, len(text)
    quote = ""
    while i < n:
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = ""
        elif c in "'\"`":
            quote = c
        elif c in pairs:
            stack.append(pairs[c])
        elif c == stack[-1]:
            stack.pop()
            if not stack:
                return text[open_idx + 1:i]
        i += 1
    return None


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth, start, quote = 0, 0, ""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = ""
        elif c in "'\"`":
            quote = c
        elif c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


_STR = r"""(?:'[^']*'|"[^"]*")"""
_DIRNAME_CALL = re.compile(
    rf"(?:path\.)?(?:resolve|join)\(\s*__dirname((?:\s*,\s*{_STR})*)\s*\)"
)
_NEW_URL = re.compile(r"""new\s+URL\(\s*(['"])(.*?)\1\s*,\s*import\.meta\.url""")
_DIRNAME_PLUS = re.compile(r"""__dirname\s*\+\s*(['"])(.*?)\1""")
_BARE_CALL = re.compile(
    rf"(?:path\.)?(?:resolve|join)\(\s*(?:process\.cwd\(\)\s*,\s*)?({_STR}(?:\s*,\s*{_STR})*)\s*\)"
)
_PLAIN = re.compile(r"""^\s*(['"])(.*?)\1\s*$""", re.DOTALL)
_STR_ARG = re.compile(_STR)


def _unquote_args(blob: str) -> list[str]:
    return [m[1:-1] for m in _STR_ARG.findall(blob)]


def _eval_path_expr(expr: str, config_dir: str) -> str | None:
    if m := _DIRNAME_CALL.search(expr):
        return os.path.normpath(os.path.join(config_dir, *_unquote_args(m.group(1))))
    if m := _NEW_URL.search(expr):
        return os.path.normpath(os.path.join(config_dir, m.group(2)))
    if m := _DIRNAME_PLUS.search(expr):
        return os.path.normpath(os.path.join(config_dir, m.group(2).lstrip("/\\")))
    if m := _BARE_CALL.search(expr):
        return os.path.normpath(os.path.join(config_dir, *_unquote_args(m.group(1))))
    if m := _PLAIN.match(expr):
        return os.path.normpath(os.path.join(config_dir, m.group(2).lstrip("/\\")))
    return None


_OBJ_ENTRY = re.compile(
    r"""^(?:'([^']*)'|"([^"]*)"|([A-Za-z_$][\w$\-]*))\s*:\s*(.+)$""", re.DOTALL
)
_FIND = re.compile(r"""\bfind\s*:\s*(['"])(.*?)\1""")


def parse_vite_aliases(text: str, config_dir: str) -> list[tuple[str, str]]:
    """Return [(alias_key, absolute_target_path)] from `resolve.alias`."""
    text = _strip_comments(text, "'\"`")
    found: list[tuple[str, str]] = []
    for m in re.finditer(r"\balias\s*:\s*([\[{])", text):
        inner = _balanced_block(text, m.end() - 1)
        if inner is None:
            continue
        is_array = m.group(1) == "["
        for entry in _split_top_level(inner):
            if is_array:
                if not entry.startswith("{"):
                    continue
                body = _balanced_block(entry, 0) or ""
                find = _FIND.search(body)
                repl = next(
                    (p.split(":", 1)[1] for p in _split_top_level(body)
                     if re.match(r"replacement\s*:", p)),
                    None,
                )
                if find and repl:
                    target = _eval_path_expr(repl, config_dir)
                    if target:
                        found.append((find.group(2), target))
            else:
                em = _OBJ_ENTRY.match(entry)
                if not em:
                    continue
                key = em.group(1) or em.group(2) or em.group(3)
                target = _eval_path_expr(em.group(4), config_dir)
                if key and target:
                    found.append((key, target))
    return found


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

@dataclass
class _Rule:
    mode: str                      # "paths" (tsconfig) or "vite"
    prefix: str
    suffix: str = ""
    wildcard: bool = False
    targets: list[str] = field(default_factory=list)  # absolute; may contain "*"
    local: bool = True             # targets live inside the project

    def candidates(self, spec: str) -> list[str] | None:
        if self.mode == "vite":
            key = self.prefix.rstrip("/")
            if spec == key:
                return list(self.targets)
            if spec.startswith(key + "/"):
                rest = spec[len(key) + 1:]
                return [os.path.normpath(os.path.join(t, rest)) for t in self.targets]
            return None
        if self.wildcard:
            if (
                spec.startswith(self.prefix)
                and spec.endswith(self.suffix)
                and len(spec) >= len(self.prefix) + len(self.suffix)
            ):
                middle = spec[len(self.prefix):len(spec) - len(self.suffix)]
                return [t.replace("*", middle) for t in self.targets]
            return None
        return list(self.targets) if spec == self.prefix else None


@dataclass
class _DirConfig:
    rules: list[_Rule] = field(default_factory=list)
    base_url: str | None = None


def _is_local_target(template: str, root: str) -> bool:
    path = os.path.abspath(template.replace("*", ""))
    if "node_modules" in path.replace("\\", "/").split("/"):
        return False
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        return False


class AliasResolver:
    """Per-analysis-run alias resolver. Build one per build_dependency_graph call."""

    def __init__(self, project_root: str):
        self.root = os.path.abspath(project_root)
        self._dir_cache: dict[str, _DirConfig] = {}

    # -- config discovery ---------------------------------------------------

    def _ancestors(self, importing_file: str) -> list[str]:
        dirs: list[str] = []
        current = os.path.dirname(os.path.abspath(importing_file))
        while True:
            dirs.append(current)
            if current == self.root or len(current) <= len(self.root):
                break
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        return dirs

    def _config_for(self, directory: str) -> _DirConfig:
        cached = self._dir_cache.get(directory)
        if cached is not None:
            return cached
        cfg = _DirConfig()
        ts_rules: list[_Rule] = []

        for name in TS_CONFIG_NAMES:
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            opts = _load_ts_options(path)
            if opts.base_url and cfg.base_url is None:
                cfg.base_url = opts.base_url
            if opts.paths:
                base = opts.base_url or opts.paths_dir or directory
                for pattern, targets in opts.paths.items():
                    if pattern.count("*") > 1 or not targets:
                        continue
                    abs_targets = [os.path.normpath(os.path.join(base, t)) for t in targets]
                    if "*" in pattern:
                        prefix, suffix = pattern.split("*", 1)
                        wildcard = True
                    else:
                        prefix, suffix, wildcard = pattern, "", False
                    ts_rules.append(_Rule(
                        mode="paths", prefix=prefix, suffix=suffix, wildcard=wildcard,
                        targets=abs_targets,
                        local=all(_is_local_target(t, self.root) for t in abs_targets),
                    ))

        # TS semantics: exact patterns first, then longest matching prefix.
        ts_rules.sort(key=lambda r: (r.wildcard, -len(r.prefix)))

        vite_rules: list[_Rule] = []
        for name in VITE_CONFIG_NAMES:
            path = os.path.join(directory, name)
            text = _read(path) if os.path.isfile(path) else None
            if text is None:
                continue
            for key, target in parse_vite_aliases(text, directory):
                vite_rules.append(_Rule(
                    mode="vite", prefix=key, targets=[target],
                    local=_is_local_target(target, self.root),
                ))
        vite_rules.sort(key=lambda r: -len(r.prefix))

        cfg.rules = ts_rules + vite_rules
        self._dir_cache[directory] = cfg
        return cfg

    # -- resolution ---------------------------------------------------------

    def resolve(self, importing_file: str, specifier: str) -> tuple[str | None, AliasStatus]:
        spec = specifier.strip()
        if not spec or spec.startswith((".", "/", "node:")):
            return None, AliasStatus.NOT_ALIAS

        ancestors = self._ancestors(importing_file)
        matched_local_alias = False

        for directory in ancestors:
            cfg = self._config_for(directory)
            for rule in cfg.rules:
                candidates = rule.candidates(spec)
                if candidates is None:
                    continue
                if rule.local and rule.prefix:
                    matched_local_alias = True
                for candidate in candidates:
                    resolved = resolve_candidate(candidate, self.root)
                    if resolved:
                        return resolved, AliasStatus.LOCAL
            if cfg.base_url:
                resolved = resolve_candidate(os.path.join(cfg.base_url, spec), self.root)
                if resolved:
                    return resolved, AliasStatus.LOCAL

        if spec.startswith("@/"):
            rest = spec[2:]
            for directory in ancestors:
                src = os.path.join(directory, "src")
                if os.path.isdir(src):
                    resolved = resolve_candidate(os.path.join(src, rest), self.root)
                    if resolved:
                        return resolved, AliasStatus.LOCAL
            return None, AliasStatus.UNRESOLVED

        if matched_local_alias:
            return None, AliasStatus.UNRESOLVED
        return None, AliasStatus.NOT_ALIAS
