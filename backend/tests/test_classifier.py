import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from analyzer.classifier import is_local_specifier, classify_imports


def test_relative_specifiers_are_local():
    assert is_local_specifier("./utils")
    assert is_local_specifier("../models/User")
    assert is_local_specifier("./components/Button")


def test_absolute_root_specifier_is_local():
    assert is_local_specifier("/src/utils")


def test_bare_package_specifiers_are_external():
    assert not is_local_specifier("react")
    assert not is_local_specifier("@scope/pkg")
    assert not is_local_specifier("node:fs")
    assert not is_local_specifier("lodash/debounce")


def test_empty_specifier_is_not_local():
    assert not is_local_specifier("")
    assert not is_local_specifier("   ")


def test_classify_imports_splits_correctly():
    raw = [
        {"specifier": "react", "type": "import"},
        {"specifier": "./auth", "type": "import"},
        {"specifier": "../models/User", "type": "import"},
        {"specifier": "./database", "type": "require"},
        {"specifier": "@scope/pkg", "type": "import"},
    ]
    local, external = classify_imports(raw)

    assert {i["specifier"] for i in local} == {"./auth", "../models/User", "./database"}
    assert {i["specifier"] for i in external} == {"react", "@scope/pkg"}
