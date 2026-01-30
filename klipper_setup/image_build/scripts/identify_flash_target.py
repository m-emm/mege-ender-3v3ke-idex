#!/usr/bin/env python3
"""Identify likely flash target disks on macOS.

This script never writes anything; it only inspects disks via `diskutil`.

It is intentionally conservative: it provides a scored, sorted list of
*candidates* and the user must decide what to flash.
"""

from __future__ import annotations

import argparse
import math
import plistlib
import re
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class DiskCandidate:
    device: str  # /dev/diskN
    device_identifier: str  # diskN
    size_bytes: int
    content: str  # partition map type for whole disk (e.g. FDisk_partition_scheme)
    bus_protocol: str
    media_name: str
    removable: bool
    internal: bool
    partitions_content: tuple[str, ...]


def _run(cmd: list[str]) -> bytes:
    return subprocess.check_output(cmd, stderr=subprocess.DEVNULL)


def _run_plist(cmd: list[str]) -> dict:
    out = _run(cmd)
    return plistlib.loads(out)


def list_external_physical_disks() -> list[str]:
    # `diskutil list external physical` is the most reliable way to discover candidates.
    # It prints lines starting with /dev/diskN.
    try:
        text = subprocess.check_output(
            ["diskutil", "list", "external", "physical"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []

    disks: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^(/dev/disk\d+)\b", line.strip())
        if m:
            disks.append(m.group(1))

    # stable ordering; will be re-sorted by score later.
    return sorted(set(disks))


def parse_candidate(disk_dev: str) -> DiskCandidate:
    info = _run_plist(["diskutil", "info", "-plist", disk_dev])
    listing = _run_plist(["diskutil", "list", "-plist", disk_dev])

    all_parts = listing.get("AllDisksAndPartitions", [])
    whole = all_parts[0] if all_parts else {}
    partitions = whole.get("Partitions", []) or []
    partitions_content = tuple(p.get("Content", "") for p in partitions if p.get("Content"))

    size_bytes = int(
        info.get("TotalSize")
        or info.get("DiskSize")
        or info.get("IOKitSize")
        or whole.get("Size")
        or 0
    )

    return DiskCandidate(
        device=info.get("DeviceNode", disk_dev),
        device_identifier=info.get("DeviceIdentifier", disk_dev.replace("/dev/", "")),
        size_bytes=size_bytes,
        content=info.get("Content", ""),
        bus_protocol=info.get("BusProtocol", ""),
        media_name=info.get("MediaName", ""),
        removable=bool(info.get("Removable", False)),
        internal=bool(info.get("Internal", False)),
        partitions_content=partitions_content,
    )


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    size_component: float
    scheme_component: float
    linux_component: float
    apfs_component: float


def score_candidate(c: DiskCandidate) -> ScoreBreakdown:
    # Weighted score (higher is better / more likely to be the intended flash target).
    # Heuristics reflect typical SD cards / Pi images, but are NOT guarantees.

    # Disk size: larger => worse, on a log scale.
    # This is intentionally a *penalty* (negative number).
    # Example: 32GB => -log10(32) ~= -1.51, 2000GB => -log10(2000) ~= -3.30
    size_weight = 2.0
    size_gb = max(c.size_bytes / (1024**3), 0.001)
    size_component = -size_weight * math.log10(size_gb)

    # Partition scheme: FDisk more likely, GUID less likely.
    scheme_component = 0.0
    if c.content == "FDisk_partition_scheme":
        scheme_component = 2.5
    elif c.content == "GUID_partition_scheme":
        scheme_component = -2.5

    # Partitions: Linux is common on flashed Pi images.
    linux_component = 0.0
    if any(p == "Linux" for p in c.partitions_content):
        linux_component = 3.5

    # Strong malus for APFS (very likely a real external mac disk).
    apfs_component = 0.0
    if any(p.startswith("Apple_APFS") or p == "Apple_APFS" for p in c.partitions_content):
        apfs_component = -7.0

    # Small additional guardrails (not requested, but high-value):
    # - removable false: probably an external SSD/HDD
    # - internal true: should never be a flash target
    extra = 0.0
    if not c.removable:
        extra -= 3.0
    if c.internal:
        extra -= 100.0

    total = size_component + scheme_component + linux_component + apfs_component + extra

    return ScoreBreakdown(
        total=total,
        size_component=size_component,
        scheme_component=scheme_component,
        linux_component=linux_component,
        apfs_component=apfs_component,
    )


def fmt_bytes(n: int) -> str:
    if n <= 0:
        return "?"
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    for u in units:
        if v < 1024 or u == units[-1]:
            if u in {"GB", "TB"}:
                return f"{v:.1f}{u}"
            return f"{v:.0f}{u}"
        v /= 1024
    return f"{v:.1f}TB"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Score and sort likely flash target disks on macOS (read-only)."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="(reserved) print machine-readable output (not implemented yet)",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="print score breakdown details",
    )
    args = parser.parse_args(argv)

    disks = list_external_physical_disks()
    if not disks:
        print("No external, physical disks found.", file=sys.stderr)
        return 0

    candidates: list[tuple[DiskCandidate, ScoreBreakdown]] = []
    for d in disks:
        try:
            c = parse_candidate(d)
        except Exception:
            continue
        candidates.append((c, score_candidate(c)))

    candidates.sort(key=lambda t: t[1].total, reverse=True)

    print("Scored external, physical disks (you must decide what to flash):")
    print()

    for idx, (c, s) in enumerate(candidates, start=1):
        parts = ",".join(c.partitions_content) if c.partitions_content else "(none)"
        flags = []
        if c.removable:
            flags.append("removable")
        if c.bus_protocol:
            flags.append(c.bus_protocol.lower())
        flags_str = f" [{', '.join(flags)}]" if flags else ""

        print(
            f"{idx:>2}. {c.device:<10} score={s.total:+7.2f}  size={fmt_bytes(c.size_bytes):>7}  map={c.content or '?'}{flags_str}"
        )
        if c.media_name:
            print(f"    media: {c.media_name}")
        print(f"    parts: {parts}")
        if args.details:
            print(
                f"    score: size= {s.size_component:+.2f} scheme= {s.scheme_component:+.2f} linux= {s.linux_component:+.2f} apfs= {s.apfs_component:+.2f}"
            )
        print()

    best = candidates[0][0]
    print("Legend:")
    print("  Higher score = more likely flash target. Negative = less likely.")
    print()

    print("Recommendation (still verify!):")
    print(f"  Most likely flash target: {best.device} ({best.media_name or best.device_identifier})")
    print("  Best practice: unplug other externals, then compare before/after insertion.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
