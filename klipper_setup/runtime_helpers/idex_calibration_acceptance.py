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
import contextlib
import datetime as dt
import hashlib
import json
import os
import tempfile
import uuid
import fcntl
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
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _ledger_lock(root: Path):
    lock_path = root / "data" / ".acceptance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _release_ledger_lock(handle) -> None:
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


def _activity_path(root: Path) -> Path:
    return root / "data" / "activity.json"


@contextlib.contextmanager
def _activity_lock(root: Path):
    lock_path = root / "data" / ".activity.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _read_activity(root: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(_activity_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _activity_time(value: Any) -> float:
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return float("-inf")


def _publish_activity(root: Path, payload: dict[str, Any], *, terminal: str | None = None) -> dict[str, Any] | None:
    """Publish volatile activity without touching the acceptance projection."""
    with _activity_lock(root):
        current = _read_activity(root)
        attempt_id = payload.get("attempt_id")
        state = load_state(root / "data" / "accepted.json")
        active = state.get("attempt") or {}
        if not attempt_id or active.get("attempt_id") != attempt_id:
            return current
        incoming_started = payload.get("started_at") or utc_now()
        if current and _activity_time(incoming_started) < _activity_time(current.get("started_at")):
            return current
        record = copy.deepcopy(current or {})
        record.update({
            "schema_version": 1,
            "kind": "idex_calibration_activity",
            "attempt_id": attempt_id,
            "activity_id": payload.get("activity_id") or record.get("activity_id") or str(uuid.uuid4()),
            "owner": payload.get("owner") or record.get("owner") or "calibration",
            "state": terminal or payload.get("state") or "busy",
            "step": payload.get("step", record.get("step")),
            "operation": payload.get("operation", record.get("operation", "Calibration")),
            "progress": payload.get("progress", record.get("progress", "")),
            "started_at": incoming_started,
            "heartbeat_at": payload.get("heartbeat_at") or utc_now(),
            "updated_at": utc_now(),
        })
        atomic_write_json(_activity_path(root), record)
        return record


def _publish_heartbeat(root: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    with _activity_lock(root):
        current = _read_activity(root)
        if not current:
            return None
        active = (load_state(root / "data" / "accepted.json").get("attempt") or {}).get("attempt_id")
        if payload.get("attempt_id") != active:
            return current
        if payload.get("attempt_id") != current.get("attempt_id") or payload.get("activity_id") != current.get("activity_id"):
            return current
        heartbeat_at = payload.get("heartbeat_at") or utc_now()
        if _activity_time(heartbeat_at) < _activity_time(current.get("heartbeat_at")):
            return current
        record = copy.deepcopy(current)
        record["heartbeat_at"] = heartbeat_at
        record["updated_at"] = utc_now()
        if payload.get("progress") is not None:
            record["progress"] = payload["progress"]
        atomic_write_json(_activity_path(root), record)
        return record


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
        target["mesh"] = copy.deepcopy(mesh.get("mesh", mesh))

    attempt = state.get("attempt")
    if isinstance(attempt, dict):
        attempt_chapters = attempt.get("chapters") or {}
        # A live chapter is rendered in place, while the accepted version is
        # retained in accepted_sources for the dashboard's provenance panel.
        # Do not merge accepted detail into an owned live chapter: that makes
        # old plots and contacts look like they belong to the new attempt.
        for key, value in attempt_chapters.items():
            if key in {"bed_calibration", "tool_alignment"}:
                live = copy.deepcopy(value)
                # Bed reference and mesh are separate accepted chapters even
                # though legacy snapshots nest them under bed_calibration.
                # Preserve the non-owned side while replacing the chapter
                # currently being re-measured.
                accepted_bed = chapters.get("bed_calibration") or {}
                if key == "bed_calibration" and isinstance(live, dict):
                    if "reference" not in live and "reference" in accepted_bed:
                        live["reference"] = copy.deepcopy(accepted_bed["reference"])
                    if "mesh" not in live and "mesh" in accepted_bed:
                        live["mesh"] = copy.deepcopy(accepted_bed["mesh"])
                chapters[key] = live
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
        "attempt": {key: copy.deepcopy(value) for key, value in attempt.items() if key != "activity"},
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
    # Callers may construct an initial state directly (not through a command);
    # keep its readiness projection coherent without embedding live activity.
    if not state.get("readiness", {}).get("checks"):
        state["readiness"] = readiness(state.get("accepted") or {})
        if (state.get("attempt") or {}).get("status") in {"preparing", "running"}:
            state["readiness"]["printable"] = False
            state["readiness"]["reasons"] = ["An active calibration attempt is still running"] + state["readiness"].get("reasons", [])
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


def _apply_command_unlocked(root: Path, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = load_state(root / "data" / "accepted.json")
    if command == "begin":
        incoming = copy.deepcopy(payload.get("attempt") or {})
        existing = state.get("attempt")
        # Child chapter runners share the coordinator's attempt ID.  Joining
        # that attempt preserves its history while allowing the child to own
        # and replace its chapter payload.
        if (
            isinstance(existing, dict)
            and existing.get("attempt_id")
            and existing.get("attempt_id") == incoming.get("attempt_id")
        ):
            attempt = copy.deepcopy(existing)
            for key, value in incoming.items():
                if key != "chapters":
                    attempt[key] = value
            if "chapters" in incoming:
                _deep_merge(attempt.setdefault("chapters", {}), incoming["chapters"])
        else:
            attempt = incoming
        attempt.setdefault("status", "running")
        attempt.setdefault("chapters", {})
        # A new attempt must not inherit a stale error/rollback message from
        # an earlier failed or interrupted attempt.
        for key in ("error", "rollback", "message", "printable"):
            attempt.pop(key, None)
        attempt.pop("activity", None)
        state["attempt"] = attempt
    elif command == "heartbeat":
        return _publish_activity(root, payload)
    elif command == "activity":
        return _publish_activity(root, payload)
    elif command == "update":
        incoming_attempt_id = payload.get("attempt_id") or payload.get("batch_id")
        existing_attempt = state.get("attempt")
        # An update for a different attempt starts a fresh live candidate.
        # Never carry nested chapter detail (contacts, plots, errors, or
        # terminal statuses) across attempt IDs; accepted chapters are
        # projected separately and remain available through provenance.
        if (
            incoming_attempt_id
            and isinstance(existing_attempt, dict)
            and existing_attempt.get("attempt_id")
            and existing_attempt.get("attempt_id") != incoming_attempt_id
        ):
            state["attempt"] = {}
        attempt = state.setdefault("attempt", {})
        attempt.pop("activity", None)
        attempt.update({k: copy.deepcopy(v) for k, v in payload.items() if k not in {"chapters", "activity"}})
        if "chapters" in payload:
            _deep_merge(attempt.setdefault("chapters", {}), payload["chapters"])
    elif command == "accept":
        chapter = str(payload["chapter"])
        entry = copy.deepcopy(payload["entry"])
        if isinstance(state.get("attempt"), dict):
            state["attempt"].pop("activity", None)
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
        attempt.pop("activity", None)
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
    active = state.get("attempt") or {}
    if active.get("status") in {"preparing", "running"}:
        state["readiness"]["printable"] = False
        state["readiness"]["reasons"] = ["An active calibration attempt is still running"] + state["readiness"].get("reasons", [])
    if command == "ready" and state["readiness"]["printable"]:
        state["readiness"]["reasons"] = []
    return write_state(root, state)


def apply_command(root: Path, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Apply a serialized ledger mutation or publish volatile activity."""
    if command == "heartbeat":
        return _publish_heartbeat(root, payload)
    if command == "activity":
        return _publish_activity(root, payload, terminal=payload.get("state") if payload.get("state") in {"failed", "completed"} else None)
    lock = _ledger_lock(root)
    try:
        result = _apply_command_unlocked(root, command, payload)
        # Terminal ledger mutations leave a diagnostic activity record behind.
        if command == "fail":
            _publish_activity(root, {
                "attempt_id": payload.get("attempt_id") or payload.get("batch_id") or (result.get("attempt") or {}).get("attempt_id"),
                "activity_id": payload.get("activity_id"),
                "owner": "ledger",
                "step": payload.get("step"),
                "operation": payload.get("stage", "Calibration failed"),
                "progress": payload.get("error", ""),
                "state": "failed",
            }, terminal="failed")
        elif command == "ready" and result.get("readiness", {}).get("printable"):
            attempt_id = (result.get("attempt") or {}).get("attempt_id") or payload.get("batch_id")
            _publish_activity(root, {
                "attempt_id": attempt_id,
                "owner": "ledger",
                "operation": "Calibration chain ready",
                "progress": "All accepted chapters passed",
                "state": "completed",
            }, terminal="completed")
        return result
    finally:
        _release_ledger_lock(lock)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("begin", "update", "activity", "heartbeat", "accept", "fail", "ready"))
    parser.add_argument("--root", default="/home/pi/printer_data/calibration")
    args = parser.parse_args(argv)
    payload = json.loads(sys.stdin.read() or "{}")
    apply_command(Path(args.root), args.command, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
