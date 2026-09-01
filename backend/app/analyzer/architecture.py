"""
Architecture classification.

Heuristic, path-based categorization - not a formal architecture detector,
just an informative label so the UI can group/color files meaningfully.
Checks path segments (folder names) first since they're the strongest
signal, then falls back to filename patterns for things like tests.
"""

from __future__ import annotations

# Order matters: checked top to bottom, first match wins. More specific
# folder names should come before more general ones.
FOLDER_RULES: list[tuple[str, str]] = [
    ("components", "Component"),
    ("controllers", "Controller"),
    ("services", "Service"),
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
    """
    lower_path = file_path.lower()
    segments = lower_path.split("/")

    for folder_name, label in FOLDER_RULES:
        if folder_name in segments:
            return label

    filename = segments[-1] if segments else lower_path
    if any(marker in filename for marker in TEST_FILENAME_MARKERS):
        return "Test"

    return "Unknown"
