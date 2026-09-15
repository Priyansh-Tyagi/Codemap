"""
Architecture classification.

Heuristic, path-based categorization - not a formal architecture detector,
just an informative label so the UI can group/color files meaningfully.

Two signals, checked in order of specificity:
1. Exact filename match (e.g. "views.py") - the strongest signal, since it
   catches the extremely common Django convention of a flat per-app layout
   (blog/models.py, blog/views.py, blog/urls.py, no subfolders at all).
   A folder-name check alone would miss all of these entirely, since
   "models" as a path SEGMENT never matches a file literally named
   "models.py".
2. Folder name (a path segment) - the JS-oriented rules from Phase 6,
   plus Python/Django folder conventions added here.
"""

from __future__ import annotations

# Exact filename match (with extension) - checked first, since a
# single-file convention is a stronger signal than a folder-name guess.
FILENAME_RULES: dict[str, str] = {
    "models.py": "Model",
    "views.py": "Controller",  # Django "views" are request handlers - closer to Controller than Page
    "urls.py": "Route",
    "admin.py": "Admin",
    "serializers.py": "Serializer",
    "forms.py": "Form",
    "settings.py": "Config",
    "apps.py": "Config",
    "tests.py": "Test",
    "conftest.py": "Test",
    "manage.py": "Config",
}

# Order matters: checked top to bottom, first match wins. More specific
# folder names should come before more general ones.
FOLDER_RULES: list[tuple[str, str]] = [
    ("components", "Component"),
    ("controllers", "Controller"),
    ("services", "Service"),
    ("serializers", "Serializer"),
    ("migrations", "Migration"),
    ("management", "Command"),
    ("admin", "Admin"),
    ("models", "Model"),
    ("middleware", "Middleware"),
    ("routes", "Route"),
    ("hooks", "Hook"),
    ("pages", "Page"),
    ("views", "Page"),
    ("config", "Config"),
    ("utils", "Util"),
    ("lib", "Util"),
    ("tests", "Test"),
    ("__tests__", "Test"),
]

TEST_FILENAME_MARKERS = (".test.", ".spec.")


def classify_architecture(file_path: str) -> str:
    """
    file_path: project-relative path, e.g. "src/components/Button.tsx"
        or "blog/models.py"
    """
    lower_path = file_path.lower()
    segments = lower_path.split("/")
    filename = segments[-1] if segments else lower_path

    if filename in FILENAME_RULES:
        return FILENAME_RULES[filename]

    for folder_name, label in FOLDER_RULES:
        if folder_name in segments:
            return label

    if any(marker in filename for marker in TEST_FILENAME_MARKERS):
        return "Test"

    return "Unknown"
