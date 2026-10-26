"""Command-line entry point for P7 held-out test evaluation."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ..config import get_config
from .report import RESULTS_DIR, write_report
from .runner import run_evaluation


def _git_revision(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _source_fingerprint(root: Path) -> str:
    """Hash source/config files, including uncommitted and new files."""
    paths = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--modified",
            "--others",
            "--exclude-standard",
            "--",
            "Makefile",
            "backend/src",
            "backend/tests",
            "configs",
            "scripts",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    digest = hashlib.sha256()
    for relative in sorted(set(paths)):
        candidate = (root / relative).resolve()
        if candidate.is_file() and candidate.is_relative_to(root.resolve()):
            digest.update(relative.replace("\\", "/").encode("utf-8"))
            digest.update(b"\0")
            digest.update(candidate.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _git_dirty(root: Path) -> bool:
    try:
        return bool(
            subprocess.run(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--",
                    "Makefile",
                    "backend/src",
                    "backend/tests",
                    "configs",
                    "scripts",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return True


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=1000)
    parser.add_argument("--runs", type=int, default=200, help="Runs per scenario; SPEC default is 200")
    parser.add_argument("--duration", type=int, default=None, help="Override simulated seconds per run")
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args(argv)
    if args.runs < 1 or args.workers < 1 or args.start_seed < 0:
        parser.error("runs/workers must be positive and start-seed non-negative")

    config = get_config()
    duration = int(args.duration or config.simulation.duration)
    start = time.perf_counter()
    results = run_evaluation(
        start_seed=args.start_seed,
        run_count=args.runs,
        duration_s=duration,
        workers=args.workers,
    )
    elapsed = time.perf_counter() - start
    metadata = {
        "git_hash": _git_revision(RESULTS_DIR.parent.parent),
        "git_dirty": _git_dirty(RESULTS_DIR.parent.parent),
        "source_hash": _source_fingerprint(RESULTS_DIR.parent.parent),
        "config_hash": config.config_hash(),
        "seeds": results["seeds"],
        "runtime_seconds": elapsed,
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "workers": args.workers,
    }
    write_report(results, results_dir=args.output_dir, metadata=metadata)
    print(f"Evaluation complete: {args.runs} runs × 7 scenarios in {elapsed:.1f}s")
    print(f"Results: {args.output_dir / 'results.json'}")
    print(f"Metadata: {args.output_dir / 'meta.json'}")


if __name__ == "__main__":
    main()
