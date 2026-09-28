"""Submission packages whose checksums verify exactly as documented.

A sealed run's SHA256SUMS describes the run directory on the controlled drive, including private
files that are never exported, so ``shasum -c`` against it cannot pass inside a package. A package
therefore carries its own manifest, written over the paths as they appear in the archive, and the
package is only returned after that manifest has been checked with the documented command.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

MANIFEST = "MANIFEST.sha256"
VERIFY_COMMAND = f"shasum -a 256 -c {MANIFEST}"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


class PackageError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(output_zip: Path, files: dict[str, Path | str | bytes], root: str) -> Path:
    """``files`` maps an archive path (relative, no leading slash) to a file, text or bytes.

    Everything lands under ``root/`` so the archive unpacks into one folder, and ``root/MANIFEST.sha256``
    lists every other file by its path relative to that folder.
    """
    payload: dict[str, bytes] = {}
    for arcname, source in sorted(files.items()):
        if arcname.startswith("/") or ".." in Path(arcname).parts or arcname == MANIFEST:
            raise PackageError(f"illegal archive path: {arcname!r}")
        if isinstance(source, Path):
            payload[arcname] = source.read_bytes()
        elif isinstance(source, str):
            payload[arcname] = source.encode()
        else:
            payload[arcname] = source
    manifest = "".join(f"{_sha(data)}  {name}\n" for name, data in sorted(payload.items()))
    payload[MANIFEST] = manifest.encode()

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(f"{root}/{name}", date_time=FIXED_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    verify(output_zip, root)
    return output_zip


def verify(output_zip: Path, root: str) -> None:
    """Unpack and run the documented command. A package that fails its own instructions is not returned."""
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(output_zip) as z:
            z.extractall(tmp)
        folder = Path(tmp) / root
        listed = {line.split("  ", 1)[1] for line in (folder / MANIFEST).read_text().splitlines()}
        present = {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()} - {MANIFEST}
        if listed != present:
            raise PackageError(f"manifest and archive disagree: missing {sorted(present - listed)}, "
                               f"extra {sorted(listed - present)}")
        if shutil.which("shasum"):
            result = subprocess.run(VERIFY_COMMAND.split(), cwd=folder, capture_output=True, text=True)
            if result.returncode:
                raise PackageError(f"`{VERIFY_COMMAND}` failed inside the package:\n{result.stdout}{result.stderr}")
        else:
            for line in (folder / MANIFEST).read_text().splitlines():
                digest, name = line.split("  ", 1)
                if _sha((folder / name).read_bytes()) != digest:
                    raise PackageError(f"checksum mismatch for {name}")
