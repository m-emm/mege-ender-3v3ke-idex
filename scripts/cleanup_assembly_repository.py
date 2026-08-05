#!/usr/bin/env python3
"""Prune the assembly cache, deleting the oldest entries first."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path


REPOSITORY = (
    Path(__file__).resolve().parents[1] / "assembling" / "repository"
).resolve()
DEFAULT_MAX_SIZE_GB = 1.5
BYTES_PER_GB = 1_000_000_000
PROGRESS_INTERVAL_SECONDS = 3.0

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheEntry:
    paths: tuple[Path, ...]
    modified_at: float
    disk_usage: int


def allocated_size(path: Path) -> int:
    """Return allocated bytes without following symlinks."""
    stat_result = path.lstat()
    return getattr(stat_result, "st_blocks", 0) * 512 or stat_result.st_size


def disk_usage(path: Path) -> int:
    if path.is_symlink() or not path.is_dir():
        return allocated_size(path)

    total = allocated_size(path)
    for directory, directory_names, file_names in os.walk(
        path, topdown=True, followlinks=False
    ):
        directory_path = Path(directory)

        for name in directory_names:
            child = directory_path / name
            total += allocated_size(child)

        directory_names[:] = [
            name for name in directory_names if not (directory_path / name).is_symlink()
        ]

        for name in file_names:
            total += allocated_size(directory_path / name)

    return total


def cache_entries(repository: Path) -> list[CacheEntry]:
    entries: list[CacheEntry] = []
    for assembly_directory in repository.iterdir():
        if assembly_directory.name == "__mesh_cache__":
            grouped_mesh_files: dict[tuple[Path, str], list[Path]] = {}
            for path in assembly_directory.rglob("*"):
                if path.is_file() or path.is_symlink():
                    grouped_mesh_files.setdefault((path.parent, path.stem), []).append(
                        path
                    )

            for paths in grouped_mesh_files.values():
                sorted_paths = tuple(sorted(paths))
                entries.append(
                    CacheEntry(
                        paths=sorted_paths,
                        modified_at=max(path.lstat().st_mtime for path in sorted_paths),
                        disk_usage=sum(allocated_size(path) for path in sorted_paths),
                    )
                )
            continue

        if assembly_directory.is_dir() and not assembly_directory.is_symlink():
            candidates = assembly_directory.iterdir()
        else:
            candidates = (assembly_directory,)

        for candidate in candidates:
            entries.append(
                CacheEntry(
                    paths=(candidate,),
                    modified_at=candidate.lstat().st_mtime,
                    disk_usage=disk_usage(candidate),
                )
            )

    return sorted(entries, key=lambda entry: (entry.modified_at, str(entry.paths[0])))


def remove_entry(entry: CacheEntry) -> None:
    for path in entry.paths:
        if path.is_symlink() or not path.is_dir():
            path.unlink()
        else:
            shutil.rmtree(path)


def remove_empty_assembly_directories(repository: Path) -> None:
    for path in repository.iterdir():
        if path.is_dir() and not path.is_symlink():
            try:
                path.rmdir()
            except OSError:
                pass


def format_size(byte_count: int) -> str:
    return f"{byte_count / BYTES_PER_GB:.3f} GB"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Delete the oldest hashed assembly-cache entries until the cache is "
            "smaller than the requested size."
        )
    )
    parser.add_argument(
        "--max-size-gb",
        type=float,
        default=DEFAULT_MAX_SIZE_GB,
        help=f"maximum cache size in decimal GB (default: {DEFAULT_MAX_SIZE_GB})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be deleted without changing the cache",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()
    if args.max_size_gb <= 0:
        raise SystemExit("--max-size-gb must be greater than zero")
    if not REPOSITORY.is_dir():
        raise SystemExit(f"Assembly repository does not exist: {REPOSITORY}")

    limit = int(args.max_size_gb * BYTES_PER_GB)
    usage = disk_usage(REPOSITORY)
    _logger.info(f"Assembly repository: {REPOSITORY}")
    _logger.info(f"Current size: {format_size(usage)}")
    _logger.info(f"Target: less than {format_size(limit)}")

    if usage < limit:
        _logger.info(f"Nothing to delete.")
        return

    _logger.info(f"Inspecting cache entries and ordering them by age...")
    entries = cache_entries(REPOSITORY)
    _logger.info(f"Found {len(entries)} cache entries.")
    deleted_count = 0
    reclaimed_estimate = 0
    started_at = time.monotonic()
    last_progress_at = started_at

    for entry in entries:
        if usage < limit:
            break

        if not args.dry_run:
            remove_entry(entry)

        deleted_count += 1
        reclaimed_estimate += entry.disk_usage
        usage = max(0, usage - entry.disk_usage)

        if not args.dry_run and usage < limit:
            usage = disk_usage(REPOSITORY)

        now = time.monotonic()
        if now - last_progress_at >= PROGRESS_INTERVAL_SECONDS:
            elapsed = max(now - started_at, 0.001)
            action = "Would delete" if args.dry_run else "Deleted"
            _logger.info(
                f"{action} {deleted_count} entries; "
                f"about {format_size(reclaimed_estimate)} reclaimed; "
                f"estimated size {format_size(usage)}; "
                f"{deleted_count / elapsed:.0f} entries/s."
            )
            last_progress_at = now

    if args.dry_run:
        _logger.info(
            f"Dry run complete: {deleted_count} entries would be deleted; "
            f"estimated final size {format_size(usage)}."
        )
        return

    remove_empty_assembly_directories(REPOSITORY)
    final_usage = disk_usage(REPOSITORY)
    _logger.info(
        f"Cleanup complete: deleted {deleted_count} entries, reclaimed about "
        f"{format_size(reclaimed_estimate)}, final size {format_size(final_usage)}."
    )
    if final_usage >= limit:
        raise SystemExit(
            "All cache entries were removed, but the repository is still not below "
            "the requested limit."
        )


if __name__ == "__main__":
    main()
