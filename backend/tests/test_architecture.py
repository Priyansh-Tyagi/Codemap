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
