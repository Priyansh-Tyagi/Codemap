import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from analyzer.architecture import classify_architecture


def test_component_folder():
    assert classify_architecture("src/components/Button.tsx") == "Component"


def test_service_folder():
    assert classify_architecture("src/services/payment.js") == "Service"


def test_util_folder():
    assert classify_architecture("src/utils/format.js") == "Util"


def test_model_folder():
    assert classify_architecture("src/models/User.js") == "Model"


def test_hook_folder():
    assert classify_architecture("src/hooks/useAuth.js") == "Hook"


def test_route_folder():
    assert classify_architecture("src/routes/userRoutes.js") == "Route"


def test_page_and_view_both_map_to_page():
    assert classify_architecture("src/pages/Home.jsx") == "Page"
    assert classify_architecture("src/views/Home.jsx") == "Page"


def test_test_filename_marker_without_test_folder():
    assert classify_architecture("src/utils/format.test.js") == "Util"
    # Note: "utils" folder rule matches before the filename-based test check,
    # since folder rules are checked first. This documents that behavior
    # rather than treating it as a bug - folder location is a stronger signal.


def test_test_folder_takes_precedence_over_no_folder():
    assert classify_architecture("src/__tests__/app.js") == "Test"


def test_unclassified_file_returns_unknown():
    assert classify_architecture("src/index.js") == "Unknown"


def test_case_insensitive():
    assert classify_architecture("SRC/COMPONENTS/Button.tsx") == "Component"


def test_django_flat_layout_models_file():
    """blog/models.py - no models/ FOLDER, just a file - would be missed by folder rules alone."""
    assert classify_architecture("blog/models.py") == "Model"


def test_django_flat_layout_views_file():
    assert classify_architecture("blog/views.py") == "Controller"


def test_django_flat_layout_urls_file():
    assert classify_architecture("blog/urls.py") == "Route"


def test_django_admin_file():
    assert classify_architecture("blog/admin.py") == "Admin"


def test_drf_serializers_file():
    assert classify_architecture("blog/serializers.py") == "Serializer"


def test_django_settings_file():
    assert classify_architecture("myproject/settings.py") == "Config"


def test_django_migrations_folder():
    assert classify_architecture("blog/migrations/0001_initial.py") == "Migration"


def test_django_management_commands_folder():
    assert classify_architecture("blog/management/commands/seed_data.py") == "Command"


def test_conftest_file():
    assert classify_architecture("tests/conftest.py") == "Test"


def test_filename_rule_takes_precedence_over_folder_rule():
    """
    A file named "views.py" sitting inside a folder that ALSO happens to
    match a rule (here "utils/") should use the more specific filename
    rule (Controller), not the folder rule (Util).
    """
    assert classify_architecture("myapp/utils/views.py") == "Controller"


def test_plain_python_file_with_no_convention_is_unknown():
    assert classify_architecture("myapp/helpers.py") == "Unknown"
