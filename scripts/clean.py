"""Remove generated local caches and build outputs without touching user data."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / "backend" / ".mypy_cache",
    ROOT / "backend" / ".pytest_cache",
    ROOT / "frontend" / "dist",
    ROOT / "frontend" / "build",
)


def main() -> None:
    """Remove only generated test and build directories."""
    for target in TARGETS:
        if target.is_dir():
            shutil.rmtree(target)
            print(f"Removed {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
