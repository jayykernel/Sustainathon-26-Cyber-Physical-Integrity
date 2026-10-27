"""Download and safely extract checksum-pinned CALCE CS2 cell archives."""

from __future__ import annotations

import argparse
import hashlib
import os
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw" / "calce"
ARCHIVES = {
    "CS2_33": "ce375e3826e840ff0986ceade0d324ba6515f0446697c947353aca097f232505",
    "CS2_34": "229dcdc836f140f746c26316569c357b346994fddd3be1223b1e457805c484b4",
}
BASE_URL = "https://web.calce.umd.edu/batteries/data"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download(cell_id: str) -> Path:
    destination = DATA_DIR / f"{cell_id}.zip"
    expected = ARCHIVES[cell_id]
    if destination.exists():
        actual = _sha256(destination)
        if actual != expected:
            raise ValueError(f"Existing {destination} checksum mismatch: {actual}")
        return destination

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".zip.tmp")
    url = f"{BASE_URL}/{cell_id}.zip"
    try:
        digest = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise ValueError(f"Downloaded {cell_id} checksum mismatch: {actual}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _extract(cell_id: str, archive_path: Path) -> Path:
    target = DATA_DIR / cell_id
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        for member in members:
            relative = PurePosixPath(member.filename)
            windows_relative = PureWindowsPath(member.filename)
            if (
                relative.is_absolute()
                or windows_relative.is_absolute()
                or windows_relative.drive
                or ".." in relative.parts
                or ".." in windows_relative.parts
            ):
                raise ValueError(f"Unsafe archive member in {archive_path.name}: {member.filename}")
        archive.extractall(DATA_DIR)
    if not target.is_dir() or not any(target.glob("*.xlsx")):
        raise ValueError(f"Archive {archive_path.name} did not contain {cell_id} workbooks")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cells", nargs="*", choices=tuple(ARCHIVES), default=list(ARCHIVES))
    args = parser.parse_args()
    for cell_id in args.cells:
        archive = _download(cell_id)
        folder = _extract(cell_id, archive)
        print(f"{cell_id}: verified {_sha256(archive)}; extracted {folder}")


if __name__ == "__main__":
    main()
