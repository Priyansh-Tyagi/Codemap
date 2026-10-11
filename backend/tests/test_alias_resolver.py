"""
Path-alias resolution (tsconfig paths / baseUrl / extends, vite aliases,
"@/" -> src fallback) - unit tests plus end-to-end through the graph builder
and the GitHub tarball extractor.
"""

import io
import os
import sys
import tarfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from analyzer.alias_resolver import (
    ALIAS_CONFIG_FILE_RE, AliasResolver, AliasStatus, parse_jsonc, parse_vite_aliases,
)
from analyzer.github_fetcher import _safe_extract, _wanted_member
from graph.builder import build_dependency_graph


def write(root, rel, text=""):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def resolve(root, importing, spec):
    r = AliasResolver(str(root))
    path, status = r.resolve(os.path.join(str(root), *importing.split("/")), spec)
    rel = os.path.relpath(path, str(root)).replace(os.sep, "/") if path else None
    return rel, status


# ---------------------------------------------------------------- JSONC

def test_jsonc_comments_trailing_commas_and_urls_in_strings():
    data = parse_jsonc('''\ufeff{
      // line comment
      "a": "http://example.com/*not a comment*/",  /* block */
      "b": [1, 2,],
    }''')
    assert data == {"a": "http://example.com/*not a comment*/", "b": [1, 2]}


def test_malformed_config_is_ignored_not_fatal(tmp_path):
    write(tmp_path, "tsconfig.json", "{ this is not json")
    write(tmp_path, "src/a.ts")
    assert resolve(tmp_path, "src/b.ts", "@/a") == ("src/a.ts", AliasStatus.LOCAL)  # fallback still works


# ---------------------------------------------------------------- tsconfig paths

def test_paths_wildcard_with_baseurl(tmp_path):
    write(tmp_path, "tsconfig.json", '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}')
    write(tmp_path, "src/lib/utils.ts")
    write(tmp_path, "src/app/page.ts")
    assert resolve(tmp_path, "src/app/page.ts", "@/lib/utils") == ("src/lib/utils.ts", AliasStatus.LOCAL)


def test_paths_without_baseurl_are_relative_to_the_config_file(tmp_path):
    write(tmp_path, "tsconfig.json", '{"compilerOptions":{"paths":{"~/*":["./app/*"]}}}')
    write(tmp_path, "app/x.ts")
    assert resolve(tmp_path, "app/y.ts", "~/x") == ("app/x.ts", AliasStatus.LOCAL)


def test_paths_exact_pattern_and_index_directory(tmp_path):
    write(tmp_path, "tsconfig.json", '{"compilerOptions":{"paths":{"@store":["./src/store"]}}}')
    write(tmp_path, "src/store/index.ts")
    assert resolve(tmp_path, "src/a.ts", "@store") == ("src/store/index.ts", AliasStatus.LOCAL)


def test_longest_prefix_wins_and_later_targets_are_fallbacks(tmp_path):
    write(tmp_path, "tsconfig.json", '''{"compilerOptions":{"paths":{
        "@/*": ["./src/*"],
        "@/ui/*": ["./packages/ui/*", "./src/ui/*"]
    }}}''')
    write(tmp_path, "src/ui/button.ts")          # only the 2nd target of the more specific rule exists
    write(tmp_path, "src/other.ts")
    assert resolve(tmp_path, "src/a.ts", "@/ui/button") == ("src/ui/button.ts", AliasStatus.LOCAL)
    assert resolve(tmp_path, "src/a.ts", "@/other") == ("src/other.ts", AliasStatus.LOCAL)


def test_baseurl_only_resolves_bare_local_specifier(tmp_path):
    write(tmp_path, "tsconfig.json", '{"compilerOptions":{"baseUrl":"src"}}')
    write(tmp_path, "src/lib/helpers.ts")
    assert resolve(tmp_path, "src/a.ts", "lib/helpers") == ("src/lib/helpers.ts", AliasStatus.LOCAL)
    # no such local file -> it is just an npm package
    assert resolve(tmp_path, "src/a.ts", "react") == (None, AliasStatus.NOT_ALIAS)


def test_vite_template_split_config_tsconfig_app_json(tmp_path):
    # tsconfig.json only has "references"; the paths live in tsconfig.app.json
    write(tmp_path, "tsconfig.json", '{"files":[],"references":[{"path":"./tsconfig.app.json"}]}')
    write(tmp_path, "tsconfig.app.json", '{"compilerOptions":{"paths":{"@/*":["./src/*"]}}}')
    write(tmp_path, "src/lib/utils.ts")
    assert resolve(tmp_path, "src/main.tsx", "@/lib/utils") == ("src/lib/utils.ts", AliasStatus.LOCAL)


def test_extends_inherits_paths_relative_to_defining_config(tmp_path):
    write(tmp_path, "tsconfig.base.json", '{"compilerOptions":{"paths":{"@lib/*":["./libs/*"]}}}')
    write(tmp_path, "apps/web/tsconfig.json", '{"extends":"../../tsconfig.base.json"}')
    write(tmp_path, "libs/core.ts")
    # "./libs/*" is relative to tsconfig.base.json (repo root), not to apps/web
    assert resolve(tmp_path, "apps/web/src/a.ts", "@lib/core") == ("libs/core.ts", AliasStatus.LOCAL)


def test_child_paths_replace_parent_paths_like_tsc(tmp_path):
    write(tmp_path, "base.json", '{"compilerOptions":{"paths":{"@old/*":["./old/*"]}}}')
    write(tmp_path, "tsconfig.json",
          '{"extends":"./base.json","compilerOptions":{"paths":{"@new/*":["./new/*"]}}}')
    write(tmp_path, "old/a.ts")
    write(tmp_path, "new/a.ts")
    assert resolve(tmp_path, "x.ts", "@new/a") == ("new/a.ts", AliasStatus.LOCAL)
    assert resolve(tmp_path, "x.ts", "@old/a")[1] != AliasStatus.LOCAL


def test_extends_cycle_does_not_hang(tmp_path):
    write(tmp_path, "tsconfig.json", '{"extends":"./b.json"}')
    write(tmp_path, "b.json", '{"extends":"./tsconfig.json"}')
    write(tmp_path, "src/a.ts")
    assert resolve(tmp_path, "src/x.ts", "@/a") == ("src/a.ts", AliasStatus.LOCAL)


# ---------------------------------------------------------------- vite

def test_vite_alias_object_forms(tmp_path):
    cfg = '''
    import path from 'path'
    import { fileURLToPath, URL } from 'node:url'
    export default {
      resolve: {
        // "@x": path.resolve(__dirname, "./nope"),
        alias: {
          '@': path.resolve(__dirname, './src'),
          "~comp": fileURLToPath(new URL('./src/components', import.meta.url)),
          utils: path.join(__dirname, 'src', 'utils'),
          '#root': '/src/root',
        },
      },
    }'''
    got = dict(parse_vite_aliases(cfg, str(tmp_path)))
    assert got["@"] == os.path.join(str(tmp_path), "src")
    assert got["~comp"] == os.path.join(str(tmp_path), "src", "components")
    assert got["utils"] == os.path.join(str(tmp_path), "src", "utils")
    assert got["#root"] == os.path.join(str(tmp_path), "src", "root")
    assert "@x" not in got                       # commented out


def test_vite_alias_array_form(tmp_path):
    cfg = '''export default { resolve: { alias: [
        { find: '@', replacement: path.resolve(__dirname, 'src') },
        { find: /^~/, replacement: 'x' },
    ] } }'''
    assert parse_vite_aliases(cfg, str(tmp_path)) == [("@", os.path.join(str(tmp_path), "src"))]


def test_vite_alias_end_to_end_when_tsconfig_has_none(tmp_path):
    # the real-world FastAPI full-stack template shape: alias only in vite.config
    write(tmp_path, "vite.config.ts",
          "export default { resolve: { alias: { '@': path.resolve(__dirname, './src') } } }")
    write(tmp_path, "src/client/index.ts")
    assert resolve(tmp_path, "src/routes/a.tsx", "@/client") == ("src/client/index.ts", AliasStatus.LOCAL)


def test_vite_alias_into_node_modules_stays_external(tmp_path):
    write(tmp_path, "vite.config.ts",
          "export default { resolve: { alias: { vue: path.resolve(__dirname, 'node_modules/vue/dist/vue.js') } } }")
    assert resolve(tmp_path, "src/a.ts", "vue") == (None, AliasStatus.NOT_ALIAS)


# ---------------------------------------------------------------- fallback + classification

def test_at_slash_falls_back_to_nearest_src(tmp_path):
    write(tmp_path, "src/lib/utils.ts")
    assert resolve(tmp_path, "src/components/ui/button.tsx", "@/lib/utils") == (
        "src/lib/utils.ts", AliasStatus.LOCAL)


def test_at_slash_to_missing_file_is_unresolved_not_external(tmp_path):
    write(tmp_path, "src/a.ts")
    assert resolve(tmp_path, "src/b.ts", "@/does/not/exist") == (None, AliasStatus.UNRESOLVED)


def test_real_packages_are_never_mistaken_for_aliases(tmp_path):
    write(tmp_path, "tsconfig.json", '{"compilerOptions":{"paths":{"@/*":["./src/*"]}}}')
    write(tmp_path, "src/react.ts")              # a local file that merely shares a name
    for spec in ("react", "@tanstack/react-query", "@radix-ui/react-slot", "lodash/fp", "node:fs"):
        assert resolve(tmp_path, "src/a.ts", spec) == (None, AliasStatus.NOT_ALIAS), spec


def test_relative_specifiers_are_not_the_alias_resolvers_job(tmp_path):
    assert resolve(tmp_path, "src/a.ts", "./b") == (None, AliasStatus.NOT_ALIAS)


def test_alias_target_outside_project_root_is_refused(tmp_path):
    outside = tmp_path / "outside"
    proj = tmp_path / "proj"
    write(outside, "secret.ts")
    write(proj, "tsconfig.json", '{"compilerOptions":{"paths":{"@x/*":["../outside/*"]}}}')
    assert resolve(proj, "a.ts", "@x/secret")[0] is None


# ---------------------------------------------------------------- monorepo scoping

def test_each_package_uses_its_own_alias_config(tmp_path):
    for pkg in ("web", "admin"):
        write(tmp_path, f"packages/{pkg}/tsconfig.json",
              '{"compilerOptions":{"paths":{"@/*":["./src/*"]}}}')
        write(tmp_path, f"packages/{pkg}/src/util.ts")
    assert resolve(tmp_path, "packages/web/src/a.ts", "@/util")[0] == "packages/web/src/util.ts"
    assert resolve(tmp_path, "packages/admin/src/a.ts", "@/util")[0] == "packages/admin/src/util.ts"


def test_configs_are_reread_on_a_new_resolver_never_cached_across_runs(tmp_path):
    write(tmp_path, "tsconfig.json", '{"compilerOptions":{"paths":{"@/*":["./one/*"]}}}')
    write(tmp_path, "one/a.ts")
    write(tmp_path, "two/a.ts")
    assert resolve(tmp_path, "x.ts", "@/a")[0] == "one/a.ts"
    with open(os.path.join(str(tmp_path), "tsconfig.json"), "w") as fh:
        fh.write('{"compilerOptions":{"paths":{"@/*":["./two/*"]}}}')
    assert resolve(tmp_path, "x.ts", "@/a")[0] == "two/a.ts"


# ---------------------------------------------------------------- end to end via the builder

def test_builder_turns_alias_imports_into_edges_and_stops_counting_them_external(tmp_path):
    write(tmp_path, "tsconfig.json", '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}')
    write(tmp_path, "src/lib/utils.ts", "export const cn = () => 1;\nexport const other = 2;\n")
    write(tmp_path, "src/components/Button.tsx",
          "import { cn } from '@/lib/utils';\n"
          "import { other } from '../lib/utils';\n"        # same target via a relative path
          "import React from 'react';\n"
          "import { missing } from '@/lib/nope';\n")
    result = build_dependency_graph(str(tmp_path))
    g = result.graph

    assert g.has_edge("src/components/Button.tsx", "src/lib/utils.ts")
    assert g.number_of_edges() == 1                        # merged, not duplicated
    assert sorted(g["src/components/Button.tsx"]["src/lib/utils.ts"]["symbols"]) == ["cn", "other"]
    assert result.external_dependencies == {"react": 1}    # no "@/lib/utils" pollution
    assert [u["specifier"] for u in result.unresolved_imports] == ["@/lib/nope"]


# ---------------------------------------------------------------- GitHub extraction

def _tar(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return tarfile.open(fileobj=buf, mode="r:gz")


def test_config_filename_matcher():
    for ok in ("tsconfig.json", "tsconfig.app.json", "tsconfig.base.json", "jsconfig.json",
               "vite.config.ts", "vite.config.mts", "vite.config.js"):
        assert ALIAS_CONFIG_FILE_RE.match(ok), ok
    for bad in ("package.json", "tsconfig.txt", "vite.config.json", "my-tsconfig.json", "webpack.config.js"):
        assert not ALIAS_CONFIG_FILE_RE.match(bad), bad


def test_github_extraction_keeps_alias_configs_but_still_skips_junk(tmp_path):
    tar = _tar({
        "o-r-abc/frontend/tsconfig.json": b"{}",
        "o-r-abc/frontend/tsconfig.app.json": b"{}",
        "o-r-abc/frontend/vite.config.mts": b"export default {}",
        "o-r-abc/frontend/src/a.ts": b"1",
        "o-r-abc/package.json": b"{}",
        "o-r-abc/README.md": b"docs",
        "o-r-abc/node_modules/pkg/tsconfig.json": b"{}",
        "o-r-abc/.github/tsconfig.json": b"{}",
    })
    _safe_extract(tar, str(tmp_path))
    extracted = sorted(
        os.path.relpath(os.path.join(d, f), tmp_path).replace(os.sep, "/")
        for d, _, fs in os.walk(tmp_path) for f in fs
    )
    assert extracted == [
        "o-r-abc/frontend/src/a.ts",
        "o-r-abc/frontend/tsconfig.app.json",
        "o-r-abc/frontend/tsconfig.json",
        "o-r-abc/frontend/vite.config.mts",
    ]


def test_github_end_to_end_alias_edges_survive_extraction(tmp_path):
    tar = _tar({
        "o-r-abc/frontend/tsconfig.json": b'{"compilerOptions":{"paths":{"@/*":["./src/*"]}}}',
        "o-r-abc/frontend/src/lib/utils.ts": b"export const a = 1;",
        "o-r-abc/frontend/src/main.tsx": b"import { a } from '@/lib/utils';",
    })
    _safe_extract(tar, str(tmp_path))
    result = build_dependency_graph(str(tmp_path / "o-r-abc"))
    assert result.graph.has_edge("frontend/src/main.tsx", "frontend/src/lib/utils.ts")


# ---------------------------------------------------------------- .d.ts declaration files

def test_declaration_files_resolve_as_file_and_as_index_but_lose_to_real_sources(tmp_path):
    write(tmp_path, "tsconfig.json", '{"compilerOptions":{"baseUrl":"."}}')
    write(tmp_path, "types/index.d.ts")
    write(tmp_path, "env.d.ts")
    write(tmp_path, "both.d.ts")
    write(tmp_path, "both.ts")
    assert resolve(tmp_path, "src/a.ts", "types") == ("types/index.d.ts", AliasStatus.LOCAL)   # baseUrl + index.d.ts
    assert resolve(tmp_path, "src/a.ts", "env") == ("env.d.ts", AliasStatus.LOCAL)
    assert resolve(tmp_path, "src/a.ts", "both") == ("both.ts", AliasStatus.LOCAL)             # .ts beats .d.ts


def test_relative_import_of_declaration_file_resolves(tmp_path):
    from analyzer.resolver import resolve_specifier
    write(tmp_path, "src/types.d.ts")
    importing = write(tmp_path, "src/a.ts")
    assert resolve_specifier(importing, "./types", str(tmp_path)) == os.path.join(str(tmp_path), "src", "types.d.ts")
