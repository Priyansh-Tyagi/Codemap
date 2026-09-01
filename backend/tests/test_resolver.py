import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from analyzer.resolver import resolve_specifier


@pytest.fixture
def fake_project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.js").write_text("// app")
    (src / "auth.ts").write_text("// auth")

    utils = src / "utils"
    utils.mkdir()
    (utils / "index.js").write_text("// utils index")

    helpers = src / "helpers"
    helpers.mkdir()
    (helpers / "format.tsx").write_text("// format")

    models = tmp_path / "models"
    models.mkdir()
    (models / "User.js").write_text("// user")

    return tmp_path


def test_resolves_exact_file_with_extension_given(fake_project):
    importing = str(fake_project / "src" / "app.js")
    resolved = resolve_specifier(importing, "./auth.ts", str(fake_project))
    assert resolved == str(fake_project / "src" / "auth.ts")


def test_resolves_by_guessing_extension(fake_project):
    importing = str(fake_project / "src" / "app.js")
    resolved = resolve_specifier(importing, "./auth", str(fake_project))
    assert resolved == str(fake_project / "src" / "auth.ts")


def test_resolves_directory_index(fake_project):
    importing = str(fake_project / "src" / "app.js")
    resolved = resolve_specifier(importing, "./utils", str(fake_project))
    assert resolved == str(fake_project / "src" / "utils" / "index.js")


def test_resolves_parent_relative_path(fake_project):
    importing = str(fake_project / "src" / "app.js")
    resolved = resolve_specifier(importing, "../models/User", str(fake_project))
    assert resolved == str(fake_project / "models" / "User.js")


def test_resolves_nested_extension_guess(fake_project):
    importing = str(fake_project / "src" / "app.js")
    resolved = resolve_specifier(importing, "./helpers/format", str(fake_project))
    assert resolved == str(fake_project / "src" / "helpers" / "format.tsx")


def test_unresolvable_specifier_returns_none(fake_project):
    importing = str(fake_project / "src" / "app.js")
    resolved = resolve_specifier(importing, "./does-not-exist", str(fake_project))
    assert resolved is None


def test_specifier_escaping_project_root_returns_none(fake_project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "secret.js").write_text("// secret")

    importing = str(fake_project / "src" / "app.js")
    # relative path that walks out of the project root
    rel = os.path.relpath(str(outside / "secret"), str(fake_project / "src"))
    resolved = resolve_specifier(importing, rel.replace(os.sep, "/"), str(fake_project))
    assert resolved is None
