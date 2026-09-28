import zipfile

import pytest

from rarepipe.core.package import MANIFEST, PackageError, build


def test_manifest_lists_archive_paths_and_verifies(tmp_path):
    src = tmp_path / "report.md"
    src.write_text("report")
    out = build(tmp_path / "p.zip", {"upload/report.md": src, "records/x.json": "{}", "README.txt": "r"}, "PKG")
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        manifest = z.read(f"PKG/{MANIFEST}").decode()
    assert f"PKG/{MANIFEST}" in names and "PKG/upload/report.md" in names
    assert "  upload/report.md\n" in manifest and "  records/x.json\n" in manifest and MANIFEST not in manifest


def test_the_package_is_deterministic(tmp_path):
    files = {"a/b.txt": "one", "c.txt": "two"}
    first = build(tmp_path / "1.zip", files, "R").read_bytes()
    assert build(tmp_path / "2.zip", files, "R").read_bytes() == first


def test_illegal_paths_are_refused(tmp_path):
    for bad in ("/abs.txt", "../up.txt", MANIFEST):
        with pytest.raises(PackageError):
            build(tmp_path / "p.zip", {bad: "x"}, "R")
