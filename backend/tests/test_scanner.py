import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from analyzer.scanner import scan_repository


@pytest.fixture
def fake_repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("console.log(1)")
    (tmp_path / "src" / "Button.tsx").write_text("export const x = 1")
    (tmp_path / "src" / "styles.css").write_text("body {}")  # not a supported ext

    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("console.log(1)")

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "bundle.js").write_text("console.log(1)")

    return tmp_path


def test_finds_supported_source_files(fake_repo):
    result = scan_repository(str(fake_repo))
    relative = {os.path.relpath(f, fake_repo) for f in result.files}
    assert relative == {os.path.join("src", "app.js"), os.path.join("src", "Button.tsx")}


def test_ignores_node_modules_and_dist(fake_repo):
    result = scan_repository(str(fake_repo))

    def path_segments(f):
        return set(os.path.relpath(f, fake_repo).split(os.sep))

    assert not any("node_modules" in path_segments(f) for f in result.files)
    assert not any("dist" in path_segments(f) for f in result.files)


def test_missing_path_raises(fake_repo):
    with pytest.raises(FileNotFoundError):
        scan_repository(str(fake_repo / "does-not-exist"))


def test_file_path_raises_not_a_directory(fake_repo):
    file_path = fake_repo / "src" / "app.js"
    with pytest.raises(NotADirectoryError):
        scan_repository(str(file_path))
