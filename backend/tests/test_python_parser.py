import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from analyzer.python_parser import parse_python_file


def write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    return str(path)


def test_plain_import(tmp_path):
    path = write(tmp_path, "a.py", "import os\n")
    result = parse_python_file(path)
    assert result["imports"] == [{"module_path": "os", "level": 0, "symbols": ["os"]}]


def test_plain_import_multiple_names_on_one_line(tmp_path):
    path = write(tmp_path, "a.py", "import sys, json\n")
    result = parse_python_file(path)
    assert result["imports"] == [
        {"module_path": "sys", "level": 0, "symbols": ["sys"]},
        {"module_path": "json", "level": 0, "symbols": ["json"]},
    ]


def test_plain_import_with_alias_reports_real_path_not_alias(tmp_path):
    path = write(tmp_path, "a.py", "import myapp.models as models\n")
    result = parse_python_file(path)
    assert result["imports"] == [
        {"module_path": "myapp.models", "level": 0, "symbols": ["myapp.models"]}
    ]


def test_from_import_with_named_symbols(tmp_path):
    path = write(tmp_path, "a.py", "from myapp.services import get_user, create_user\n")
    result = parse_python_file(path)
    assert result["imports"] == [
        {"module_path": "myapp.services", "level": 0, "symbols": ["get_user", "create_user"]}
    ]


def test_from_import_alias_reports_source_side_name(tmp_path):
    path = write(tmp_path, "a.py", "from myapp.services.auth import authenticate as auth\n")
    result = parse_python_file(path)
    assert result["imports"] == [
        {"module_path": "myapp.services.auth", "level": 0, "symbols": ["authenticate"]}
    ]


def test_relative_import_from_dot_only(tmp_path):
    """`from . import x, y` - x and y are each separate submodule targets."""
    path = write(tmp_path, "a.py", "from . import helpers, validators\n")
    result = parse_python_file(path)
    assert result["imports"] == [
        {"module_path": "helpers", "level": 1, "symbols": ["*"]},
        {"module_path": "validators", "level": 1, "symbols": ["*"]},
    ]


def test_relative_import_with_module(tmp_path):
    path = write(tmp_path, "a.py", "from .database import query\n")
    result = parse_python_file(path)
    assert result["imports"] == [
        {"module_path": "database", "level": 1, "symbols": ["query"]}
    ]


def test_double_dot_relative_import(tmp_path):
    path = write(tmp_path, "a.py", "from ..shared.utils import log\n")
    result = parse_python_file(path)
    assert result["imports"] == [
        {"module_path": "shared.utils", "level": 2, "symbols": ["log"]}
    ]


def test_wildcard_import(tmp_path):
    path = write(tmp_path, "a.py", "from myapp.constants import *\n")
    result = parse_python_file(path)
    assert result["imports"] == [
        {"module_path": "myapp.constants", "level": 0, "symbols": ["*"]}
    ]


def test_syntax_error_does_not_crash(tmp_path):
    path = write(tmp_path, "broken.py", "def foo(:\n    pass\n")
    result = parse_python_file(path)
    assert result["error"] is not None
    assert result["imports"] == []


def test_missing_file_does_not_crash(tmp_path):
    result = parse_python_file(str(tmp_path / "does-not-exist.py"))
    assert result["error"] is not None


def test_lines_of_code_counted(tmp_path):
    path = write(tmp_path, "a.py", "import os\nimport sys\nprint('hi')\n")
    result = parse_python_file(path)
    # Matches the JS parser's convention (source.split("\n").length) for a
    # trailing-newline-terminated file, so linesOfCode is comparable
    # cross-language as a risk-score input - not a naive "3 lines" count.
    assert result["linesOfCode"] == 4
