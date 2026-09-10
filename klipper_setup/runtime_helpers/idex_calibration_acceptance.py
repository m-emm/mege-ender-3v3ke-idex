#!/usr/bin/env python3
"""Shared acceptance-ledger helpers for the IDEX calibration workflows.

The runners deliberately keep immutable attempt artifacts separate from the
small mutable dashboard snapshot.  This module owns the latter's schema and
the dependency rules used when a chapter is accepted from a different run.
It is deployed with the runtime helper bundle and can also be imported by the
workstation-side orchestration scripts and tests.
"""

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 4
CHAPTERS = ("bed_reference", "tool_alignment", "mesh")
STEP_RANGES = {
    "bed_reference": (1, 3),
    "tool_alignment": (4, 4),
    "mesh": (5, 6),
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "idex_calibration_acceptance",
        "updated_at": utc_now(),
        "accepted": {},
        "attempt": None,
        "readiness": {
            "printable": False,
            "checks": [],
            "reasons": ["No accepted calibration chapters yet"],
        },
        "history": [],
    }


def load_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A schema-v3 installation only has current.json.  Preserve that
        # snapshot as history while starting an empty acceptance working set.
        legacy_path = path.with_name("current.json")
        try:
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            legacy = None
        if isinstance(legacy, dict) and legacy.get("schema_version", 3) <= 3:
            state = empty_state()
            state["history"] = [{
                "kind": "schema-v3-history",
                "batch_id": legacy.get("batch_id"),
                "status": legacy.get("status"),
                "snapshot": legacy,
            }]
            state["last_successful_batch_id"] = legacy.get("last_successful_batch_id")
            return state
        return empty_state()
    if not isinstance(state, dict):
        return empty_state()
    # Older snapshots are useful history, but are not acceptance ledgers.
    if not isinstance(state.get("accepted"), dict):
        state["accepted"] = {}
    state.setdefault("history", [])
    state.setdefault("attempt", None)
    state.setdefault("readiness", {})
    state["schema_version"] = SCHEMA_VERSION
    state["kind"] = "idex_calibration_acceptance"
    return state


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _same(left: Any, right: Any, tolerance: float = 1.0e-9) -> bool:
    a, b = _number(left), _number(right)
    if a is None or b is None:
        return left == right
    return abs(a - b) <= tolerance


def _same_vector(left: Any, right: Any, tolerance: float = 1.0e-9) -> bool:
    if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
        return False
    return len(left) == len(right) and all(
        _same(a, b, tolerance) for a, b in zip(left, right)
    )


def compatibility(
    chapter: str,
    accepted: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a deterministic compatibility result for one accepted chapter.

    The current values are intentionally semantic rather than a generated
    config fingerprint: a common Z rebase may change both Z endstops without
    invalidating tool alignment, while a T0 frame change invalidates a mesh.
    """

    if not accepted:
        return {"valid": False, "reason": "No accepted evidence"}
    if accepted.get("status") not in {"passed", "accepted", "completed"}:
        return {"valid": False, "reason": "Accepted evidence is not passed"}
    saved = accepted.get("invariants") or {}
    observed = current or {}
    if saved.get("fixed_inputs") != observed.get("fixed_inputs"):
        return {"valid": False, "reason": "Fixed calibration inputs changed"}
    if chapter == "bed_reference":
        for key in ("reference", "t0_z_endstop"):
            if key == "reference":
                equal = _same_vector(saved.get(key), observed.get(key))
            else:
                equal = _same(saved.get(key), observed.get(key))
            if not equal:
                return {"valid": False, "reason": f"Bed reference invariant changed: {key}"}
    elif chapter == "tool_alignment":
        for key in ("t0_xy", "t1_xy", "relative_z_delta"):
            if key.endswith("_xy"):
                equal = _same_vector(saved.get(key), observed.get(key))
            else:
                equal = _same(saved.get(key), observed.get(key))
            if not equal:
                return {"valid": False, "reason": f"Tool alignment invariant changed: {key}"}
    elif chapter == "mesh":
        for key in ("reference", "t0_frame", "matrix_sha256"):
            if key == "matrix_sha256":
                equal = saved.get(key) == observed.get(key)
            else:
                equal = _same_vector(saved.get(key), observed.get(key))
            if not equal:
                return {"valid": False, "reason": f"Mesh invariant changed: {key}"}
    else:
        return {"valid": False, "reason": f"Unknown chapter: {chapter}"}
    return {"valid": True, "reason": "Semantic invariants and fixed inputs match"}


def accepted_chapter(
    chapter: str,
    *,
    attempt_id: str,
    run_scope: str,
    chapter_data: dict[str, Any],
    artifact: str,
    invariants: dict[str, Any],
    checkpoint: str | None = None,
) -> dict[str, Any]:
    if chapter not in CHAPTERS:
        raise ValueError(f"unknown chapter: {chapter}")
    return {
        "status": "accepted",
        "chapter": chapter,
        "attempt_id": attempt_id,
        "run_scope": run_scope,
        "accepted_at": utc_now(),
        "compatibility": {"state": "compatible"},
        "artifact": artifact,
        "data": copy.deepcopy(chapter_data),
        "invariants": copy.deepcopy(invariants),
        "checkpoint": checkpoint,
    }


def _chapter_data(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not entry:
        return None
    data = entry.get("data")
    return copy.deepcopy(data) if isinstance(data, dict) else None


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge live chapter patches without dropping contact/plot detail."""
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def readiness(
    accepted: dict[str, Any], current_invariants: dict[str, Any] | None = None
) -> dict[str, Any]:
    checks = []
    reasons = []
    for chapter in CHAPTERS:
        entry = accepted.get(chapter)
        current = (current_invariants or {}).get(chapter)
        result = compatibility(chapter, entry, current) if current is not None else {
            "valid": bool(entry and entry.get("status") == "accepted"),
            "reason": "Accepted evidence recorded" if entry else "No accepted evidence",
        }
        checks.append(
            {
                "chapter": chapter,
                "steps": list(range(STEP_RANGES[chapter][0], STEP_RANGES[chapter][1] + 1)),
                "passed": result["valid"],
                "attempt_id": entry.get("attempt_id") if entry else None,
                "reason": result["reason"],
            }
        )
        if not result["valid"]:
            reasons.append(f"{chapter}: {result['reason']}")
    return {"printable": not reasons, "checks": checks, "reasons": reasons}


def project_current(state: dict[str, Any]) -> dict[str, Any]:
    """Project accepted chapters and the active attempt into current.json."""

    accepted = state.get("accepted") or {}
    chapters: dict[str, Any] = {}
    bed = _chapter_data(accepted.get("bed_reference"))
    tools = _chapter_data(accepted.get("tool_alignment"))
    mesh = _chapter_data(accepted.get("mesh"))
    if bed:
        chapters["bed_calibration"] = copy.deepcopy(bed)
    if tools:
        chapters["tool_alignment"] = copy.deepcopy(tools)
    if mesh:
        target = chapters.setdefault("bed_calibration", {})
        target["mesh"] = copy.deepcopy(mesh)

    attempt = state.get("attempt")
    if isinstance(attempt, dict):
        attempt_chapters = attempt.get("chapters") or {}
        # A live chapter is rendered in place, while the accepted version is
        # retained in accepted_sources for the dashboard's provenance panel.
        for key, value in attempt_chapters.items():
            if key in {"bed_calibration", "tool_alignment"}:
                # Keep accepted detail (contacts, plots, tables) visible when
                # a later attempt only publishes a small progress patch.
                # Nested dictionaries are merged; an explicitly published
                # scalar still replaces its accepted counterpart.
                existing = chapters.setdefault(key, {})
                if isinstance(existing, dict) and isinstance(value, dict):
                    _deep_merge(existing, value)
                else:
                    chapters[key] = copy.deepcopy(value)
        if attempt.get("status") in {"failed", "completed"}:
            # Failed attempts do not become accepted evidence, but their
            # summary remains available for explicit failure details.
            pass

    current = {
        "schema_version": SCHEMA_VERSION,
        "kind": "idex_calibration_dashboard",
        "batch_id": attempt.get("batch_id") if isinstance(attempt, dict) else None,
        "run_id": attempt.get("attempt_id") if isinstance(attempt, dict) else None,
        "run_scope": attempt.get("run_scope") if isinstance(attempt, dict) else None,
        "status": attempt.get("status", "idle") if isinstance(attempt, dict) else "idle",
        "stage": attempt.get("stage", "idle") if isinstance(attempt, dict) else "idle",
        "updated_at": state.get("updated_at"),
        "attempt": copy.deepcopy(attempt),
        "accepted": copy.deepcopy(accepted),
        "accepted_sources": {
            chapter: {
                key: value
                for key, value in entry.items()
                if key in {"attempt_id", "run_scope", "accepted_at", "artifact", "status", "checkpoint", "compatibility"}
            }
            for chapter, entry in accepted.items()
            if isinstance(entry, dict)
        },
        "chapters": chapters,
        "readiness": copy.deepcopy(state.get("readiness") or readiness(accepted)),
        "history": copy.deepcopy(state.get("history") or []),
    }
    if isinstance(attempt, dict):
        current["events"] = copy.deepcopy(attempt.get("events") or [])
        for key in ("message", "error", "rollback", "printable"):
            if key in attempt:
                current[key] = copy.deepcopy(attempt[key])
    if state.get("last_successful_batch_id"):
        current["last_successful_batch_id"] = state["last_successful_batch_id"]
    return current


def write_state(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    state["schema_version"] = SCHEMA_VERSION
    state["kind"] = "idex_calibration_acceptance"
    state["updated_at"] = utc_now()
    state_path = root / "data" / "accepted.json"
    current_path = root / "data" / "current.json"
    atomic_write_json(state_path, state)
    current = project_current(state)
    atomic_write_json(current_path, current)
    # Keep the last printable composition as a separate immutable-ish view.
    # It is deliberately not used to populate the active attempt; the
    # dashboard may show it as history only.
    if state.get("readiness", {}).get("printable"):
        atomic_write_json(root / "data" / "last_successful.json", current)
    return state


def apply_command(root: Path, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = load_state(root / "data" / "accepted.json")
    if command == "begin":
        attempt = copy.deepcopy(payload.get("attempt") or {})
        attempt.setdefault("status", "running")
        attempt.setdefault("chapters", {})
        # A new attempt must not inherit a stale error/rollback message from
        # an earlier failed or interrupted attempt.
        for key in ("error", "rollback", "message", "printable"):
            attempt.pop(key, None)
        state["attempt"] = attempt
    elif command == "update":
        attempt = state.setdefault("attempt", {})
        attempt.update({k: copy.deepcopy(v) for k, v in payload.items() if k != "chapters"})
        if "chapters" in payload:
            _deep_merge(attempt.setdefault("chapters", {}), payload["chapters"])
    elif command == "accept":
        chapter = str(payload["chapter"])
        entry = copy.deepcopy(payload["entry"])
        if isinstance(state.get("attempt"), dict):
            state["attempt"].update(
                {
                    key: copy.deepcopy(payload[key])
                    for key in ("status", "stage", "batch_id", "run_scope")
                    if key in payload
                }
            )
        previous = copy.deepcopy(state.setdefault("accepted", {}).get(chapter))
        state["accepted"][chapter] = entry
        old_mesh = state["accepted"].get("mesh")
        if old_mesh and chapter in {"bed_reference", "tool_alignment"}:
            # Mesh points are expressed in the accepted T0 frame.  A bed
            # reference update changes that frame only when its reference
            # invariant changed; a tool update does so only when T0 XY/Z
            # changed.  Re-running a chapter with identical owned values is
            # therefore safe and does not unnecessarily discard a mesh.
            old_frame = (old_mesh.get("invariants") or {}).get("t0_frame")
            new_invariants = entry.get("invariants") or {}
            if chapter == "bed_reference":
                changed = (
                    previous is None
                    or not _same_vector(
                        (previous.get("invariants") or {}).get("reference"),
                        new_invariants.get("reference"),
                    )
                    or not _same(
                        (previous.get("invariants") or {}).get("t0_z_endstop"),
                        new_invariants.get("t0_z_endstop"),
                    )
                )
            else:
                changed = (
                    previous is None
                    or old_frame != new_invariants.get("t0_frame")
                )
            mesh_frame_changed = old_frame is not None and new_invariants.get("t0_frame") is not None and old_frame != new_invariants.get("t0_frame")
            if changed or mesh_frame_changed:
                old_mesh["status"] = "stale"
                old_mesh["stale_reason"] = "T0 bed frame changed; rerun the mesh refresh"
        state.setdefault("history", []).append(
            {
                "chapter": chapter,
                "attempt_id": entry.get("attempt_id"),
                "accepted_at": entry.get("accepted_at", utc_now()),
                "artifact": entry.get("artifact"),
            }
        )
        state["history"] = state["history"][-40:]
    elif command == "fail":
        attempt = state.setdefault("attempt", {})
        attempt.update(
            {
                "status": "failed",
                "error": payload.get("error", ""),
                "rollback": payload.get("rollback", "accepted checkpoint preserved"),
                "stage": payload.get("stage", attempt.get("stage", "failed")),
                "batch_id": payload.get("batch_id", attempt.get("batch_id")),
            }
        )
    elif command == "ready":
        state["last_successful_batch_id"] = payload.get("batch_id")
    else:
        raise ValueError(f"unknown acceptance command: {command}")
    state["readiness"] = readiness(state.get("accepted") or {}, payload.get("current_invariants"))
    if command == "ready" and state["readiness"]["printable"]:
        state["readiness"]["reasons"] = []
    return write_state(root, state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("begin", "update", "accept", "fail", "ready"))
    parser.add_argument("--root", default="/home/pi/printer_data/calibration")
    args = parser.parse_args(argv)
    payload = json.loads(sys.stdin.read() or "{}")
    apply_command(Path(args.root), args.command, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
