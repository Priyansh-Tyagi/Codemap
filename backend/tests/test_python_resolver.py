import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from analyzer.python_resolver import resolve_python_import, ResolutionKind


@pytest.fixture
def pkg(tmp_path):
    """
    tmp_path/
      myapp/
        __init__.py
        services/
          __init__.py
          auth.py
          user_service.py
        models/
          __init__.py
          user.py
        shared/
          __init__.py
          utils.py
    """
    myapp = tmp_path / "myapp"
    myapp.mkdir()
    (myapp / "__init__.py").write_text("")

    services = myapp / "services"
    services.mkdir()
    (services / "__init__.py").write_text("")
    (services / "auth.py").write_text("")
    (services / "user_service.py").write_text("")

    models = myapp / "models"
    models.mkdir()
    (models / "__init__.py").write_text("")
    (models / "user.py").write_text("")

    shared = myapp / "shared"
    shared.mkdir()
    (shared / "__init__.py").write_text("")
    (shared / "utils.py").write_text("")

    return tmp_path


def test_absolute_import_resolves_to_module_file(pkg):
    importing_file = str(pkg / "myapp" / "services" / "user_service.py")
    resolved, kind = resolve_python_import(importing_file, "myapp.models.user", 0, str(pkg))
    assert kind == ResolutionKind.LOCAL
    assert resolved == str(pkg / "myapp" / "models" / "user.py")


def test_absolute_import_resolves_to_package_init(pkg):
    importing_file = str(pkg / "myapp" / "services" / "user_service.py")
    resolved, kind = resolve_python_import(importing_file, "myapp.models", 0, str(pkg))
    assert kind == ResolutionKind.LOCAL
    assert resolved == str(pkg / "myapp" / "models" / "__init__.py")


def test_stdlib_import_is_external(pkg):
    importing_file = str(pkg / "myapp" / "services" / "user_service.py")
    resolved, kind = resolve_python_import(importing_file, "os", 0, str(pkg))
    assert kind == ResolutionKind.EXTERNAL
    assert resolved is None


def test_pip_package_import_is_external(pkg):
    importing_file = str(pkg / "myapp" / "services" / "user_service.py")
    resolved, kind = resolve_python_import(importing_file, "requests", 0, str(pkg))
    assert kind == ResolutionKind.EXTERNAL
    assert resolved is None


def test_relative_level_1_resolves_within_same_package(pkg):
    """from . import auth, imported from user_service.py (same dir as auth.py)"""
    importing_file = str(pkg / "myapp" / "services" / "user_service.py")
    resolved, kind = resolve_python_import(importing_file, "auth", 1, str(pkg))
    assert kind == ResolutionKind.LOCAL
    assert resolved == str(pkg / "myapp" / "services" / "auth.py")


def test_relative_level_2_resolves_to_parent_packages_sibling(pkg):
    """from ..models.user import User, imported from myapp/services/user_service.py"""
    importing_file = str(pkg / "myapp" / "services" / "user_service.py")
    resolved, kind = resolve_python_import(importing_file, "models.user", 2, str(pkg))
    assert kind == ResolutionKind.LOCAL
    assert resolved == str(pkg / "myapp" / "models" / "user.py")


def test_relative_import_to_nonexistent_name_is_unresolved_not_external(pkg):
    importing_file = str(pkg / "myapp" / "services" / "user_service.py")
    resolved, kind = resolve_python_import(importing_file, "does_not_exist", 1, str(pkg))
    assert kind == ResolutionKind.UNRESOLVED
    assert resolved is None


def test_excessive_relative_level_is_contained_not_leaked(pkg):
    """More '..' than the project is deep must not escape project_root."""
    importing_file = str(pkg / "myapp" / "services" / "auth.py")
    resolved, kind = resolve_python_import(importing_file, "etc.passwd", 5, str(pkg))
    assert kind == ResolutionKind.UNRESOLVED
    assert resolved is None


def test_local_module_that_shadows_a_common_pip_name_still_resolves_local(pkg):
    """
    A project with its own myapp/services/requests.py should resolve THAT
    file for an absolute `import myapp.services.requests`, not treat it as
    external just because "requests" is also a well-known pip package name.
    """
    (pkg / "myapp" / "services" / "requests.py").write_text("")
    importing_file = str(pkg / "myapp" / "services" / "user_service.py")
    resolved, kind = resolve_python_import(
        importing_file, "myapp.services.requests", 0, str(pkg)
    )
    assert kind == ResolutionKind.LOCAL
    assert resolved == str(pkg / "myapp" / "services" / "requests.py")
