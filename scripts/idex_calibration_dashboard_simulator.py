#!/usr/bin/env python3
"""Local-only IDEX calibration dashboard simulator.

It deliberately reuses the acceptance ledger to build dashboard projections,
but never opens an SSH, Moonraker, or printer connection.  It is intended for
fast UI and Playwright scenarios only.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import mimetypes
import shutil
import sys
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = REPO_ROOT / "klipper_setup/klipper_config/calibration_dashboard"
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/idex_calibration_dashboard"
sys.path.insert(0, str(REPO_ROOT / "klipper_setup/runtime_helpers"))
import idex_calibration_acceptance as ledger  # noqa: E402


STEPS = {
    1: ("bed_calibration.reference", "Bed Center Z=0 measurement"),
    2: ("bed_calibration.reference_deployment", "Bed Center Z=0 calibration update"),
    3: ("bed_calibration.reference_verification", "Bed Center Z=0 verification"),
    4: ("tool_alignment.calibration", "T0/T1 toolhead alignment"),
    5: ("bed_calibration.mesh_acquisition", "Acquire and save the Tap mesh"),
    6: ("bed_calibration.mesh_deployment", "Redeploy and verify the mesh"),
    7: ("completed", "Accepted calibration chain readiness"),
}
CHAPTER_STEPS = {"bed_reference": (1, 2, 3), "tool_alignment": (4,), "mesh": (5, 6)}
CALIBRATION_CONTACT_COUNT = 47


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return copy.deepcopy(default)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iso_before(seconds: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=seconds)).isoformat()


class Simulator:
    def __init__(self, state_root: Path, fixture_root: Path = FIXTURE_ROOT):
        self.root = state_root.resolve()
        if self.root in {Path("/"), REPO_ROOT, REPO_ROOT.parent}:
            raise ValueError("--state-dir must be a dedicated simulator state directory")
        self.fixture_root = fixture_root
        self.lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.root / "simulator.json"
        self.reset()

    @property
    def data_root(self) -> Path:
        return self.root / "data"

    def fixture(self, name: str, default: Any) -> Any:
        return read_json(self.fixture_root / name, default)

    def _source_accepted(self) -> dict[str, Any]:
        seed = self.fixture("seed_accepted.json", ledger.empty_state())
        return copy.deepcopy(seed.get("accepted") or {})

    def _meta(self) -> dict[str, Any]:
        return read_json(self.meta_path, {})

    def _write_meta(self, meta: dict[str, Any]) -> None:
        write_json(self.meta_path, meta)

    def reset(self) -> dict[str, Any]:
        with self.lock:
            if self.data_root.exists():
                shutil.rmtree(self.data_root)
            state = ledger.empty_state()
            state["accepted"] = self._source_accepted()
            state["attempt"] = None
            state["readiness"] = ledger.readiness(state["accepted"])
            ledger.write_state(self.root, state)
            ledger.atomic_write_json(
                self.data_root / "activity.json",
                {"schema_version": 1, "kind": "idex_calibration_activity", "state": "idle", "progress": "Waiting for a simulated calibration workflow"},
            )
            self._write_meta({
                "scenario": "idle",
                "console": self.fixture("moonraker_console.json", []),
                "printer": self.fixture("moonraker_status.json", self._printer("ready")),
                "events": ["Simulator reset"],
            })
            return self.snapshot()

    def _printer(self, state: str = "ready") -> dict[str, Any]:
        status = self.fixture("moonraker_status.json", {})
        if not status:
            status = {
                "result": {"status": {
                    "webhooks": {"state": "ready", "state_message": "Printer is ready"},
                    "toolhead": {"position": [0.0, -14.152, 30.0, 0.0], "homed_axes": "xyz"},
                    "gcode_move": {"gcode_position": [0.0, -14.152, 30.0, 0.0]},
                    "print_stats": {"state": "standby"},
                    "extruder": {"temperature": 20.5}, "extruder1": {"temperature": 21.3}, "heater_bed": {"temperature": 21.0},
                }}
            }
        result = copy.deepcopy(status)
        values = result.setdefault("result", {}).setdefault("status", {})
        values.setdefault("webhooks", {})["state"] = "ready" if state == "ready" else "error" if state == "error" else "startup"
        values["webhooks"]["state_message"] = {"ready": "Printer is ready", "not_homed": "Printer requires homing", "error": "Simulated printer error"}[state]
        values.setdefault("toolhead", {})["homed_axes"] = "xyz" if state == "ready" else ""
        return result

    def _console(self, message: str, command: bool = False) -> None:
        meta = self._meta()
        entries = meta.setdefault("console", [])
        entries.append({"time": dt.datetime.now().timestamp(), "type": "command" if command else "response", "message": message})
        meta["console"] = entries[-80:]
        meta.setdefault("events", []).append(message)
        meta["events"] = meta["events"][-32:]
        self._write_meta(meta)

    def _move_printer_for_step(self, step: int) -> None:
        """Update only the local Moonraker-shaped status fixture."""
        positions = {
            1: (150.0, 150.0, 10.0), 2: (150.0, 150.0, 30.0),
            3: (150.0, 150.0, 2.0), 4: (75.0, -9.0, 4.0),
            5: (30.0, 30.0, 5.0), 6: (150.0, 150.0, 2.0),
            7: (0.0, -14.152, 30.0),
        }
        x, y, z = positions[step]
        meta = self._meta()
        printer = meta.get("printer") or self._printer()
        status = printer.setdefault("result", {}).setdefault("status", {})
        status.setdefault("toolhead", {})["position"] = [x, y, z, 0.0]
        status.setdefault("gcode_move", {})["gcode_position"] = [x, y, z, 0.0]
        meta["printer"] = printer
        self._write_meta(meta)

    def _attempt_id(self) -> str:
        return "sim-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]

    def _active_attempt(self) -> dict[str, Any]:
        return ledger.load_state(self.data_root / "accepted.json").get("attempt") or {}

    def _activity(self) -> dict[str, Any]:
        return read_json(self.data_root / "activity.json", {})

    def _record_activity(self, step: int, operation: str, progress: str, state: str = "busy") -> None:
        attempt = self._active_attempt()
        existing = self._activity()
        payload = {
            "attempt_id": attempt.get("attempt_id"),
            "activity_id": existing.get("activity_id") or uuid.uuid4().hex,
            "owner": "local-simulator",
            "state": state,
            "step": step,
            "operation": operation,
            "progress": progress,
            "started_at": existing.get("started_at") or now(),
            "heartbeat_at": now(),
        }
        ledger.apply_command(self.root, "activity", payload)

    @staticmethod
    def _three_round_calibration_records(run: dict[str, Any]) -> list[dict[str, Any]]:
        """Expand the captured legacy Phase-3 ring into credible v3 fixture data.

        Captured production evidence remains deliberately immutable 31-contact
        history.  A live simulated candidate, however, needs the actual new
        47-contact sequence.  The three deterministic offsets make the three
        samples at each angle visibly separate without pretending they were
        captured on the printer.
        """
        records = copy.deepcopy(run.get("records", []))
        phase_three = [record for record in records if record.get("phase") == "phase_3_ring"]
        if len(phase_three) != 8:
            return records
        prefix = [record for record in records if record.get("phase") != "phase_4_centre" and record.get("phase") != "phase_3_ring"]
        centre = [record for record in records if record.get("phase") == "phase_4_centre"]
        expanded = []
        for round_index, offset in enumerate((-0.0006, 0.0, 0.0006), start=1):
            for angle_index, record in enumerate(phase_three):
                item = copy.deepcopy(record)
                item["round_index"] = round_index
                item["angle_degrees"] = angle_index * 45.0
                if isinstance(item.get("trigger_z"), (int, float)):
                    item["trigger_z"] = float(item["trigger_z"]) + offset
                expanded.append(item)
        candidate = prefix + expanded + centre
        for index, record in enumerate(candidate, start=1):
            record["sample_index"] = index
        return candidate

    def _stage_payload(self, step: int, completed: int = 0, total: int | None = None) -> dict[str, Any]:
        accepted = self._source_accepted()
        if step <= 3:
            reference = copy.deepcopy((accepted.get("bed_reference") or {}).get("data", {}).get("reference", {}))
            if step == 1:
                before = copy.deepcopy(reference.get("before_rebase", {}))
                samples = before.get("samples", [])[:completed]
                reference = {"before_rebase": {"samples": samples, "progress": {"completed": completed, "total": total or 5}}}
            elif step == 2:
                reference = {key: copy.deepcopy(reference.get(key, {})) for key in ("before_rebase", "rebase")}
            else:
                after = copy.deepcopy(reference.get("after_rebase", {}))
                samples = after.get("samples", [])[:completed]
                reference = {key: copy.deepcopy(reference.get(key, {})) for key in ("before_rebase", "rebase")}
                reference["after_rebase"] = {"samples": samples, "progress": {"completed": completed, "total": total or 5}}
            return {"bed_calibration": {"reference": reference}}
        if step == 4:
            source = copy.deepcopy((accepted.get("tool_alignment") or {}).get("data", {}).get("calibration", {}))
            runs = source.get("runs", {})
            visible = {}
            for tool in ("t0", "t1"):
                run = copy.deepcopy(runs.get(tool, {}))
                records = self._three_round_calibration_records(run)
                # Simulate the normal T0-then-T1 sequence. T1 is explicitly
                # awaiting re-measurement while T0 is still collecting data.
                tool_records = records[:completed] if tool == "t0" else []
                visible[tool] = {"workflow": "calibration", "state": "running", "progress": {"completed": len(tool_records), "total": total or CALIBRATION_CONTACT_COUNT}, "records": tool_records}
            return {"tool_alignment": {"calibration": {"status": "running", "runs": visible}}}
        source_mesh = copy.deepcopy((accepted.get("mesh") or {}).get("data", {}).get("mesh", {}))
        points = source_mesh.get("points", [])[:completed]
        mesh = {"status": "running", "progress": {"completed": len(points), "total": total or max(len(source_mesh.get("points", [])), 49)}, "points": points}
        if points:
            mesh["latest_point"] = points[-1]
        if step == 6:
            mesh["verification"] = {"status": "running", "active": False}
        return {"bed_calibration": {"mesh": mesh}}

    def _clear_live_chapter(self, chapter: str) -> None:
        """Let newly accepted evidence render as accepted, not as a candidate."""
        state = ledger.load_state(self.data_root / "accepted.json")
        chapters = (state.get("attempt") or {}).setdefault("chapters", {})
        if chapter == "tool_alignment":
            chapters.pop("tool_alignment", None)
        else:
            bed = chapters.get("bed_calibration")
            if isinstance(bed, dict):
                bed.pop("reference" if chapter == "bed_reference" else "mesh", None)
                if not bed:
                    chapters.pop("bed_calibration", None)
        ledger.write_state(self.root, state)

    def _new_tool_alignment_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Turn captured legacy evidence into a deterministic v3 simulator result."""
        source = copy.deepcopy(entry)
        calibration = source.setdefault("data", {}).setdefault("calibration", {})
        for run in calibration.get("runs", {}).values():
            records = self._three_round_calibration_records(run)
            run["records"] = records
            run["progress"] = {"completed": CALIBRATION_CONTACT_COUNT, "total": CALIBRATION_CONTACT_COUNT}
            run["state"] = "completed"
        result = calibration.setdefault("result", {}).setdefault("data", {})
        procedure = {
            "algorithm": "three_stage_sphere_ring_calibration_v3",
            "contact_count": CALIBRATION_CONTACT_COUNT,
            "refined_ring_unique_contact_count": 8,
            "refined_ring_round_count": 3,
            "refined_ring_contact_count": 24,
        }
        result["schema_version"] = 5
        result["calibration_procedure"] = procedure
        source.setdefault("invariants", {}).setdefault("fixed_inputs", {})[
            "calibration_procedure"
        ] = procedure
        return source

    def start(self, scope: str = "full") -> dict[str, Any]:
        if scope not in {"full", "bed_reference", "tool_alignment", "mesh_refresh"}:
            raise ValueError("scope must be full, bed_reference, tool_alignment, or mesh_refresh")
        first_step = {"full": 1, "bed_reference": 1, "tool_alignment": 4, "mesh_refresh": 5}[scope]
        attempt_id = self._attempt_id()
        stage, operation = STEPS[first_step]
        with self.lock:
            ledger.apply_command(self.root, "begin", {"attempt": {
                "attempt_id": attempt_id, "batch_id": attempt_id, "run_scope": scope,
                "status": "running", "stage": stage, "chapters": self._stage_payload(first_step, 0),
            }})
            self._record_activity(first_step, operation, "Preparing simulated measurement")
            self._move_printer_for_step(first_step)
            self._console(f"IDEX simulator: started {scope} attempt {attempt_id}")
            meta = self._meta(); meta["scenario"] = f"active-step-{first_step}"; self._write_meta(meta)
            return self.snapshot()

    def step(self, number: int, operation: str | None = None, completed: int = 0, total: int | None = None) -> dict[str, Any]:
        if number not in STEPS:
            raise ValueError("step must be 1 through 7")
        with self.lock:
            attempt = self._active_attempt()
            if not attempt or attempt.get("status") not in {"running", "preparing"}:
                raise ValueError("start a simulation before selecting a step")
            stage, default_operation = STEPS[number]
            ledger.apply_command(self.root, "update", {
                "attempt_id": attempt["attempt_id"], "batch_id": attempt["batch_id"], "run_scope": attempt.get("run_scope", "full"),
                "status": "running", "stage": stage, "chapters": self._stage_payload(number, completed, total),
            })
            self._record_activity(number, operation or default_operation, f"{completed}/{total or (CALIBRATION_CONTACT_COUNT if number == 4 else 49 if number in {5, 6} else 5)} simulated contacts")
            self._move_printer_for_step(number)
            self._console(f"IDEX simulator: Step {number} — {operation or default_operation}")
            return self.snapshot()

    def progress(self, completed: int, total: int) -> dict[str, Any]:
        activity = self._activity(); step = int(activity.get("step") or 1)
        return self.step(step, activity.get("operation"), completed, total)

    def heartbeat(self) -> dict[str, Any]:
        with self.lock:
            activity = self._activity()
            ledger.apply_command(self.root, "heartbeat", {"attempt_id": activity.get("attempt_id"), "activity_id": activity.get("activity_id"), "heartbeat_at": now(), "progress": activity.get("progress", "")})
            return self.snapshot()

    def complete_step(self, number: int) -> dict[str, Any]:
        total = CALIBRATION_CONTACT_COUNT if number == 4 else 49 if number in {5, 6} else 5
        self.step(number, completed=total, total=total)
        next_step = number + 1
        if next_step <= 7 and self._active_attempt().get("run_scope") == "full":
            return self.step(next_step)
        return self.snapshot()

    def complete_chapter(self, chapter: str) -> dict[str, Any]:
        if chapter not in CHAPTER_STEPS:
            raise ValueError("chapter must be bed_reference, tool_alignment, or mesh")
        with self.lock:
            attempt = self._active_attempt()
            if not attempt:
                raise ValueError("start a simulation before completing a chapter")
            source = copy.deepcopy(self._source_accepted().get(chapter))
            if not source:
                raise ValueError(f"fixture has no accepted {chapter} evidence")
            if chapter == "tool_alignment":
                source = self._new_tool_alignment_entry(source)
            # A captured mesh can legitimately be stale on the live printer
            # after a later tool-frame change. Completing a simulated mesh
            # chapter represents a new, verified persisted matrix, so use the
            # captured measurements but make this simulated acceptance explicit.
            source["status"] = "accepted"
            source["attempt_id"] = attempt["attempt_id"]
            source["accepted_at"] = now()
            terminal = CHAPTER_STEPS[chapter][-1]
            self.step(terminal, operation=f"Completing simulated {chapter.replace('_', ' ')}")
            ledger.apply_command(self.root, "accept", {
                "chapter": chapter, "entry": source,
                "status": "running", "stage": STEPS[terminal][0], "batch_id": attempt["batch_id"], "run_scope": attempt.get("run_scope", "full"),
            })
            self._clear_live_chapter(chapter)
            self._console(f"IDEX simulator: accepted {chapter}")
            if chapter == "mesh" and attempt.get("run_scope") == "full":
                ledger.apply_command(self.root, "update", {
                    "attempt_id": attempt["attempt_id"], "batch_id": attempt["batch_id"],
                    "run_scope": "full", "status": "completed", "stage": "completed", "chapters": {},
                })
                ledger.apply_command(self.root, "ready", {"batch_id": attempt["batch_id"]})
                self._record_activity(7, STEPS[7][1], "All simulated chapters accepted", "completed")
            elif attempt.get("run_scope") != "full":
                ledger.apply_command(self.root, "update", {
                    "attempt_id": attempt["attempt_id"], "batch_id": attempt["batch_id"],
                    "run_scope": attempt.get("run_scope"), "status": "completed", "stage": STEPS[terminal][0], "chapters": {},
                })
                self._record_activity(terminal, STEPS[terminal][1], f"Simulated {chapter.replace('_', ' ')} completed", "completed")
            return self.snapshot()

    def fail_step(self, number: int, reason: str) -> dict[str, Any]:
        with self.lock:
            attempt = self._active_attempt()
            if not attempt:
                raise ValueError("start a simulation before failing a step")
            ledger.apply_command(self.root, "fail", {"attempt_id": attempt["attempt_id"], "batch_id": attempt["batch_id"], "step": number, "stage": STEPS[number][0], "error": reason, "rollback": "Simulated accepted checkpoint preserved"})
            self._record_activity(number, STEPS[number][1], reason, "failed")
            self._console(f"IDEX simulator: Step {number} failed — {reason}")
            return self.snapshot()

    def set_heartbeat_age(self, seconds: int) -> dict[str, Any]:
        with self.lock:
            record = self._activity()
            record["heartbeat_at"] = iso_before(seconds)
            ledger.atomic_write_json(self.data_root / "activity.json", record)
            return self.snapshot()

    def set_printer(self, state: str) -> dict[str, Any]:
        if state not in {"ready", "not_homed", "error"}:
            raise ValueError("printer state must be ready, not_homed, or error")
        with self.lock:
            meta = self._meta(); meta["printer"] = self._printer(state); self._write_meta(meta)
            return self.snapshot()

    def scenario(self, name: str) -> dict[str, Any]:
        aliases = {"idle", "delayed-heartbeat", "stale-heartbeat", "failed-bed", "failed-tool", "failed-mesh", "accepted-bed-active-tool", "failed-tool-rerun", "stale-mesh", "ready", "invalid-mixed-state"}
        if name.startswith("active-step-"):
            number = int(name.rsplit("-", 1)[1])
            self.reset(); self.start("full"); result = self.step(number)
            meta = self._meta(); meta["scenario"] = name; self._write_meta(meta)
            return result
        if name not in aliases:
            raise ValueError(f"unknown scenario: {name}")
        self.reset()
        if name == "idle":
            return self.snapshot()
        if name in {"delayed-heartbeat", "stale-heartbeat"}:
            self.start("full"); self.step(3, completed=2, total=5); return self.set_heartbeat_age(20 if name == "delayed-heartbeat" else 61)
        if name in {"accepted-bed-active-tool", "failed-tool-rerun"}:
            self.start("tool_alignment"); self.step(4, completed=8, total=CALIBRATION_CONTACT_COUNT)
            if name == "failed-tool-rerun": return self.fail_step(4, "Simulated paired X/Y limit failed")
            return self.snapshot()
        if name.startswith("failed-"):
            step = {"failed-bed": 3, "failed-tool": 4, "failed-mesh": 6}[name]
            self.start("full"); self.step(step, completed=2, total=5 if step == 3 else CALIBRATION_CONTACT_COUNT if step == 4 else 49); return self.fail_step(step, "Simulated verification limit exceeded")
        if name == "stale-mesh":
            self.start("tool_alignment"); self.complete_chapter("tool_alignment")
            state = ledger.load_state(self.data_root / "accepted.json")
            state["accepted"].setdefault("mesh", {})["status"] = "stale"
            state["accepted"]["mesh"]["stale_reason"] = "Simulated T0 frame change"
            ledger.write_state(self.root, state)
            return self.snapshot()
        if name == "ready":
            self.start("full")
            for chapter in ("bed_reference", "tool_alignment", "mesh"):
                self.complete_chapter(chapter)
            attempt = self._active_attempt()
            ledger.apply_command(self.root, "update", {"attempt_id": attempt["attempt_id"], "batch_id": attempt["batch_id"], "run_scope": "full", "status": "completed", "stage": "completed", "chapters": {}})
            ledger.apply_command(self.root, "ready", {"batch_id": attempt["batch_id"]})
            self._record_activity(7, STEPS[7][1], "Simulated calibration chain ready", "completed")
            return self.snapshot()
        # Intentionally corrupt only the simulator projection; diagnostics must expose it.
        self.start("full")
        current = read_json(self.data_root / "current.json", {})
        current.setdefault("attempt", {})["attempt_id"] = "sim-current"
        ledger.atomic_write_json(self.data_root / "current.json", current)
        record = self._activity(); record["attempt_id"] = "sim-other"; ledger.atomic_write_json(self.data_root / "activity.json", record)
        meta = self._meta(); meta["scenario"] = name; self._write_meta(meta)
        return self.snapshot()

    def diagnostics(self) -> list[str]:
        current = read_json(self.data_root / "current.json", {})
        activity = self._activity()
        attempt = current.get("attempt") or {}
        messages = []
        if activity.get("state") in {"busy", "running", "preparing"} and activity.get("attempt_id") != attempt.get("attempt_id"):
            messages.append("Activity attempt ID does not match current attempt")
        step = activity.get("step")
        if step and step not in STEPS:
            messages.append("Activity step is outside the seven-step workflow")
        if attempt.get("status") in {"running", "preparing"} and not step:
            messages.append("Active attempt has no active step")
        return messages

    def snapshot(self) -> dict[str, Any]:
        meta = self._meta()
        return {
            "scenario": meta.get("scenario", "custom"),
            "current": read_json(self.data_root / "current.json", {}),
            "activity": self._activity(),
            "printer": meta.get("printer", self._printer()),
            "console": meta.get("console", []),
            "events": meta.get("events", []),
            "diagnostics": self.diagnostics(),
        }

    def dispatch(self, body: dict[str, Any]) -> dict[str, Any]:
        action = body.get("action")
        if action == "reset": return self.reset()
        if action == "scenario": return self.scenario(str(body["name"]))
        if action == "start": return self.start(str(body.get("scope", "full")))
        if action == "step": return self.step(int(body["number"]), body.get("operation"), int(body.get("completed", 0)), body.get("total"))
        if action == "progress": return self.progress(int(body["completed"]), int(body["total"]))
        if action == "heartbeat": return self.heartbeat()
        if action == "complete-step": return self.complete_step(int(body["number"]))
        if action == "complete-chapter": return self.complete_chapter(str(body["chapter"]))
        if action == "fail-step": return self.fail_step(int(body["number"]), str(body.get("reason", "Simulated failure")))
        if action == "restart": return self.start(str(body.get("scope", "full")))
        if action == "set-heartbeat-age": return self.set_heartbeat_age(int(body["seconds"]))
        if action == "set-printer": return self.set_printer(str(body["state"]))
        raise ValueError(f"unknown action: {action}")


class Handler(BaseHTTPRequestHandler):
    simulator: Simulator

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value: Any, status: int = 200) -> None:
        self._send(status, json.dumps(value, indent=2).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/calibration":
            self.send_response(HTTPStatus.FOUND); self.send_header("Location", "/calibration/"); self.end_headers(); return
        if path == "/__sim__/state":
            self._json(self.simulator.snapshot()); return
        if path == "/__sim__/controls.js":
            self._send(200, (REPO_ROOT / "scripts/idex_calibration_dashboard_simulator_ui.js").read_bytes(), "application/javascript; charset=utf-8"); return
        if path == "/favicon.ico":
            self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon"); return
        if path == "/printer/objects/query":
            self._json(self.simulator.snapshot()["printer"]); return
        if path == "/server/gcode_store":
            count = int(parse_qs(parsed.query).get("count", [80])[0])
            self._json({"result": {"gcode_store": self.simulator.snapshot()["console"][-count:]}}); return
        if path == "/webcam/" or path == "/webcam":
            image = self.simulator.fixture_root / "camera.jpg"
            if image.is_file(): self._send(200, image.read_bytes(), "image/jpeg")
            else: self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")
            return
        if path.startswith("/calibration/data/"):
            name = Path(path).name
            allowed = {"current.json", "activity.json", "last_successful.json"}
            if name in allowed:
                target = self.simulator.data_root / name
                if target.is_file(): self._send(200, target.read_bytes(), "application/json; charset=utf-8")
                else: self._json({})
                return
        if path.startswith("/calibration/artifacts/"):
            target = self.simulator.fixture_root / "artifacts" / Path(path).name
            if target.is_file():
                self._send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            else: self._json({"fixture": "curated acceptance evidence", "source": path, "note": "This artifact was not selected for the compact local fixture set."})
            return
        if path.startswith("/calibration/runs/"):
            # Accepted provenance can legitimately point to a full immutable
            # archive. The simulator deliberately does not copy those archives,
            # but its link remains inspectable rather than becoming a 404.
            self._json({"fixture": "curated acceptance evidence", "source": path, "note": "Full run archives are intentionally excluded from local simulator fixtures."})
            return
        if path in {"/calibration/", "/calibration/index.html"}:
            html = (DASHBOARD_ROOT / "index.html").read_text(encoding="utf-8")
            html = html.replace("</body>", '<script>window.__IDEX_SIMULATOR__=true;</script><script src="/__sim__/controls.js"></script></body>')
            self._send(200, html.encode(), "text/html; charset=utf-8"); return
        if path.startswith("/calibration/"):
            target = (DASHBOARD_ROOT / path.removeprefix("/calibration/")).resolve()
            if target.parent == DASHBOARD_ROOT and target.is_file():
                self._send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream"); return
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/__sim__/event":
            self._json({"error": "not found"}, 404); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            self._json(self.simulator.dispatch(body))
        except (ValueError, KeyError, TypeError) as exc:
            self._json({"error": str(exc)}, 400)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--state-dir", type=Path, default=REPO_ROOT / ".cache/idex-calibration-simulator")
    parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_ROOT)
    args = parser.parse_args()
    simulator = Simulator(args.state_dir, args.fixture_dir)
    Handler.simulator = simulator
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"IDEX calibration simulator: http://127.0.0.1:{args.port}/calibration/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
