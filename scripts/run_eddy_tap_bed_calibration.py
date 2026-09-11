#!/usr/bin/env python3
"""Automatically establish T0 bed Z=0 and persist the canonical Tap mesh."""

from __future__ import annotations

import base64
import concurrent.futures
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import matplotlib
import yaml

matplotlib.use("Agg")
from matplotlib import pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "klipper_setup/klipper_config"
sys.path.insert(0, str(CONFIG_DIR))

from calibration_data import (  # noqa: E402
    CalibrationDataError,
    atomic_update,
    endstops,
    load_measured,
    sha256_file,
)
from generate_printer_cfg import (  # noqa: E402
    active_config_fingerprint,
    compute_config_fingerprint,
    load_calibration,
)


CALIB_PATH = CONFIG_DIR / "calib.yaml"
CALIB_CONFIG_PATH = CONFIG_DIR / "calib_config.yaml"
TEMPLATE_PATH = CONFIG_DIR / "printer.cfg.template"
PRINTER_CFG_PATH = CONFIG_DIR / "printer.cfg"
GENERATOR_PATH = CONFIG_DIR / "generate_printer_cfg.py"
DEPLOY_PATH = CONFIG_DIR / "update_menderpi.sh"
DEFAULT_MOONRAKER_URL = "http://menderpi.local:7125"
DEFAULT_REMOTE_HOST = "pi@menderpi.local"
REMOTE_DASHBOARD_ROOT = "/home/pi/printer_data/calibration"
REFERENCE_TAP_COUNT = 5
REFERENCE_MAX_SPAN_MM = 0.030
REFERENCE_ZERO_TOLERANCE_MM = 0.030
INITIAL_PREPARE_Z_MM = 30.0
INITIAL_PREPARE_SPEED_MM_MIN = 8000.0
DISCOVERY_START_Z_MM = 10.0
DISCOVERY_BAND_MM = 4.0
# Move the four-millimetre window down by only one millimetre at a time.  Thus
# every height is covered by four discovery attempts, and a trigger near one
# window boundary is still covered by several following attempts.
DISCOVERY_STEP_MM = 1.0
DISCOVERY_OVERLAP_MM = DISCOVERY_BAND_MM - DISCOVERY_STEP_MM
DISCOVERY_FINAL_Z_MM = -2.2
NARROW_START_MARGIN_MM = 2.0
NARROW_BELOW_CONTACT_MM = 1.0
# The Eddy fit needs a sufficiently long pullback sample window.  This is
# deliberately independent of the two-millimetre height margin: the nozzle
# starts two millimetres above the discovered contact, but retracts four
# millimetres after a trigger so the fit has enough data to validate it.
DISCOVERY_RETRACT_MM = 4.0
NARROW_RETRACT_MM = 4.0
# Mesh-aware physical residual acceptance: +/-55 um at validation points.
MESH_AWARE_TOLERANCE_MM = 0.055
VALID_PHASES = {"full", "reference", "mesh"}
ACCEPTANCE_MODULE = REPO_ROOT / "klipper_setup/runtime_helpers/idex_calibration_acceptance.py"


class CalibrationError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def acceptance_call(remote_host: str, command: str, payload: dict[str, Any]) -> None:
    """Publish through the single schema-v4 acceptance writer on the Pi."""
    subprocess.run(
        [
            "ssh",
            remote_host,
            "python3 ~/printer_data/config/idex_calibration_acceptance.py "
            f"{command} --root {shlex.quote(REMOTE_DASHBOARD_ROOT)}",
        ],
        input=json.dumps(payload),
        text=True,
        check=True,
        capture_output=True,
        timeout=30,
    )


class Moonraker:
    def __init__(self, base_url: str = DEFAULT_MOONRAKER_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        body = None
        headers = {}
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        result = payload.get("result", payload)
        # Moonraker's gcode-script endpoint legitimately returns a JSON null
        # result after accepting the command.  Treat that acknowledgement as
        # success; query endpoints still return their normal mappings.
        if result is None or (path == "/printer/gcode/script" and result == "ok"):
            return {}
        if not isinstance(result, dict):
            raise CalibrationError(f"unexpected Moonraker response for {path}")
        return result

    def status(self, *objects: str) -> dict[str, Any]:
        # Object names may contain spaces (for example ``temperature_probe
        # btt_eddy``); quote each query value while preserving Moonraker's
        # ampersand-separated object list.
        query = "&".join(
            urllib.parse.quote(object_name, safe="") for object_name in objects
        )
        return self.request(f"/printer/objects/query?{query}").get("status", {})

    def gcode(self, script: str, *, timeout: float = 60.0) -> None:
        self.request("/printer/gcode/script", data={"script": script}, timeout=timeout)

    def gcode_store(self, count: int = 300) -> list[dict[str, Any]]:
        result = self.request(f"/server/gcode_store?count={count}")
        store = result.get("gcode_store", [])
        return store if isinstance(store, list) else []


class DashboardPublisher:
    def __init__(self, batch_id: str, remote_host: str) -> None:
        self.batch_id = batch_id
        self.remote_host = remote_host
        self.run_scope = os.environ.get("IDEX_CALIBRATION_RUN_SCOPE", "bed_reference")
        self.bed: dict[str, Any] = {
            "status": "preparing",
            "stage": "preflight",
            "reference": {},
            "mesh": {},
        }
        self.events: list[dict[str, str]] = []
        self._attempt: dict[str, Any] = {
            "attempt_id": batch_id,
            "batch_id": batch_id,
            "run_scope": self.run_scope,
            "workflow": "bed_calibration",
            "status": "preparing",
            "stage": "bed_calibration.preflight",
            "chapters": {"bed_calibration": self.bed},
        }
        self._activity_stop = threading.Event()
        self._activity_thread = None
        self._activity_id = str(uuid.uuid4())
        self._activity_started = utc_now()
        acceptance_call(self.remote_host, "begin", {"attempt": self._attempt})
        self.activity(1, "Bed Center Z=0 measurement", "Preparing Eddy reference")
        self._activity_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._activity_thread.start()
        self.publish()

    def event(self, message: str, *, status: str | None = None) -> None:
        self.events = (self.events + [{"at": utc_now(), "message": message}])[-24:]
        if status is not None:
            self.bed["status"] = status
        self.publish()

    def activity(self, step: int, operation: str, progress: str = "") -> None:
        now = utc_now()
        self._activity = {
            "state": "busy",
            "attempt_id": self.batch_id,
            "activity_id": self._activity_id,
            "owner": "eddy-bed-calibration",
            "step": step,
            "operation": operation,
            "started_at": self._activity_started,
            "heartbeat_at": now,
            "progress": progress,
        }
        acceptance_call(self.remote_host, "activity", self._activity)

    def _heartbeat_loop(self) -> None:
        while not self._activity_stop.wait(5.0):
            activity = dict(getattr(self, "_activity", {}) or {})
            if not activity:
                continue
            now = utc_now()
            activity["heartbeat_at"] = now
            try:
                acceptance_call(self.remote_host, "heartbeat", {
                    "attempt_id": self.batch_id,
                    "activity_id": self._activity_id,
                    "heartbeat_at": now,
                    "progress": activity.get("progress", ""),
                })
            except Exception:
                pass

    def stop_activity(self) -> None:
        if hasattr(self, "_activity_stop"):
            self._activity_stop.set()

    def finish_activity(self, state: str, progress: str = "") -> None:
        record = dict(getattr(self, "_activity", {}) or {})
        if record:
            record.update({"state": state, "progress": progress or record.get("progress", ""), "heartbeat_at": utc_now()})
            acceptance_call(self.remote_host, "activity", record)

    def publish(self) -> None:
        self._attempt.update(
            {
                "status": self.bed.get("status", "running"),
                "stage": f"bed_calibration.{self.bed.get('stage', 'unknown')}",
                "updated_at": utc_now(),
                "events": self.events,
                "chapters": {"bed_calibration": self.bed},
            }
        )
        acceptance_call(self.remote_host, "update", self._attempt)

    def upload(self, source: Path, name: str) -> str:
        relative = f"artifacts/{self.batch_id}_{name}"
        subprocess.run(
            [
                "scp",
                "-q",
                str(source),
                f"{self.remote_host}:{REMOTE_DASHBOARD_ROOT}/{relative}",
            ],
            check=True,
            timeout=60,
        )
        return relative

    def upload_run_evidence(self, source: Path) -> None:
        remote = f"{REMOTE_DASHBOARD_ROOT}/runs/{self.batch_id}/bed_calibration"
        producer = subprocess.Popen(
            ["tar", "-C", str(source), "-cf", "-", "."],
            stdout=subprocess.PIPE,
        )
        assert producer.stdout is not None
        consumer = subprocess.run(
            [
                "ssh",
                self.remote_host,
                f"mkdir -p {shlex.quote(remote)} && "
                f"tar -xf - -C {shlex.quote(remote)}",
            ],
            stdin=producer.stdout,
            check=False,
            timeout=120,
        )
        producer.stdout.close()
        producer_status = producer.wait(timeout=30)
        if producer_status or consumer.returncode:
            raise CalibrationError("failed to upload immutable Eddy run evidence")


def console(client: Moonraker, message: str) -> None:
    safe = message.replace('"', "'")
    client.gcode(f'RESPOND TYPE=echo MSG="IDEX calibration: {safe}"')
    print(f"IDEX calibration: {message}", flush=True)


def config_fingerprint(status: dict[str, Any]) -> str:
    value = active_config_fingerprint(status)
    if not value:
        raise CalibrationError("live Klipper configuration fingerprint is missing")
    return value


def acceptance_fixed_inputs() -> dict[str, str]:
    return {
        "calib_config_sha256": sha256_file(CALIB_CONFIG_PATH),
        "printer_cfg_template_sha256": sha256_file(TEMPLATE_PATH),
    }


def acceptance_entry(
    *,
    chapter: str,
    batch_id: str,
    run_scope: str,
    artifact: str,
    data: dict[str, Any],
    invariants: dict[str, Any],
    checkpoint: str,
) -> dict[str, Any]:
    return {
        "status": "accepted",
        "chapter": chapter,
        "attempt_id": batch_id,
        "run_scope": run_scope,
        "accepted_at": utc_now(),
        "artifact": artifact,
        "data": data,
        "invariants": invariants,
        "checkpoint": checkpoint,
    }


def require_ready(client: Moonraker) -> dict[str, Any]:
    status = client.status(
        "webhooks",
        "print_stats",
        "toolhead",
        "configfile",
        "gcode_move",
        "bed_mesh",
        "idex_manual_tuning",
        "multi_head_zero_probe",
    )
    if status.get("webhooks", {}).get("state") != "ready":
        raise CalibrationError("Klipper is not ready")
    if status.get("print_stats", {}).get("state") not in {"standby", "complete"}:
        raise CalibrationError("printer is not idle")
    return status


def prepare_t0(client: Moonraker) -> bool:
    status = require_ready(client)
    homed = status.get("toolhead", {}).get("homed_axes", "")
    needed = not all(axis in homed for axis in "xyz")
    preparation_commands = [
        "M140 S0",
        "M104 T0 S0",
        "M104 T1 S0",
        "BED_MESH_CLEAR",
        "SET_GCODE_OFFSET X=0 Y=0 Z=0 MOVE=0",
    ]
    if needed:
        client.gcode("\n".join((*preparation_commands, "G28", "M400")), timeout=180)
        client.gcode("QUERY_MULTI_HEAD_ZERO")
        post_home_status = require_ready(client)
        post_home_switch = post_home_status.get("multi_head_zero_probe", {}).get(
            "state"
        )
        if post_home_switch != "RELEASED":
            message = (
                "FAULT immediately after G28: multi-head-zero must be RELEASED "
                "with the axes at home, observed "
                f"{post_home_switch or 'unknown'}; aborting before bed-calibration motion"
            )
            console(client, message)
            raise CalibrationError(message)
        console(client, "post-home multi-head-zero safety check passed: RELEASED")
        client.gcode("T0\nM400", timeout=180)
    else:
        client.gcode("\n".join((*preparation_commands, "T0", "M400")), timeout=180)
    # Move once to a sensible working height after preparation. The tap
    # transaction owns its five-tap motion and restores this height only after
    # the batch, so callers never pay this move per tap.
    client.gcode(
        "G90\nG1 Z%.3f F%.0f\nM400"
        % (INITIAL_PREPARE_Z_MM, INITIAL_PREPARE_SPEED_MM_MIN),
        timeout=60,
    )
    status = require_ready(client)
    if status.get("idex_manual_tuning", {}).get("active_tool") != 0:
        raise CalibrationError("T0 is not physically active after preparation")
    if (
        abs(float(status.get("idex_manual_tuning", {}).get("manual_z_adjust", 0)))
        > 1e-9
    ):
        raise CalibrationError("manual Z adjustment is not zero")
    mesh = status.get("bed_mesh", {})
    if mesh.get("profile_name") or any(mesh.get("mesh_matrix", [])):
        raise CalibrationError("bed mesh remained active after BED_MESH_CLEAR")
    return needed


def reference_sample(
    client: Moonraker,
    *,
    x: float,
    y: float,
    index: int,
    phase: str,
    start_z: float,
    target_z: float,
    retract: float,
    count: int = 1,
    allow_rejected: bool = False,
) -> dict[str, Any]:
    rejected = " ALLOW_REJECTED=1" if allow_rejected else ""
    client.gcode(
        f"_EDDY_TAP_MEASURE X={x:.3f} Y={y:.3f} COUNT={count:d} EDDY_MODE=none "
        f"START_Z={start_z:.6f} TAP_TARGET_Z={target_z:.6f} "
        f"SAMPLE_RETRACT_DIST={retract:.6f}{rejected}",
        timeout=90,
    )
    status = client.status(
        "eddy_tap_measure",
        "gcode_move",
        "toolhead",
        "bed_mesh",
        "idex_manual_tuning",
        "temperature_probe btt_eddy",
        "configfile",
    )
    measurement = status.get("eddy_tap_measure", {}).get("last_tap_measurement")
    if not isinstance(measurement, dict):
        raise CalibrationError("EDDY_TAP_MEASURE did not publish a measurement")
    tap = measurement.get("tap", {})
    if tap.get("status") == "no_trigger":
        return {
            "status": "no_trigger",
            "index": index,
            "phase": phase,
            "x": x,
            "y": y,
            "start_z": float(start_z),
            "target_z": float(target_z),
            "retract": float(retract),
        }
    if tap.get("status") == "rejected":
        return {
            "status": "rejected",
            "index": index,
            "phase": phase,
            "x": x,
            "y": y,
            "start_z": float(start_z),
            "target_z": float(target_z),
            "retract": float(retract),
            "error": tap.get("error", "rejected tap"),
            "diagnostics": tap.get("diagnostics", {}),
        }
    samples = tap.get("samples")
    if not isinstance(samples, list) or len(samples) != count:
        raise CalibrationError(
            f"EDDY_TAP_MEASURE did not publish exactly {count} tap(s)"
        )
    for sample in samples:
        if abs(float(sample["x"]) - x) > 0.020 or abs(float(sample["y"]) - y) > 0.020:
            raise CalibrationError("Eddy Tap contact occurred at the wrong XY coordinate")
    if measurement.get("mesh", {}).get("active_transform_z") is not None:
        raise CalibrationError("reference Tap unexpectedly used an active mesh")
    tuning = status.get("idex_manual_tuning", {})
    if (
        tuning.get("active_tool") != 0
        or abs(float(tuning.get("manual_z_adjust", 0))) > 1e-9
    ):
        raise CalibrationError("reference Tap did not use clean T0 state")
    common = {
        "phase": phase,
        "temperature_c": status.get("temperature_probe btt_eddy", {}).get(
            "temperature"
        ),
        "gcode_origin": status.get("gcode_move", {}).get("homing_origin"),
        "machine_position": status.get("toolhead", {}).get("position"),
        "config_fingerprint": config_fingerprint(status),
    }
    if count == 1:
        sample = samples[0]
        return {
            "status": "contact",
            "index": index,
            "x": float(sample["x"]),
            "y": float(sample["y"]),
            "z": float(sample["z"]),
            **common,
        }
    return {
        "status": "contact_batch",
        "index": index,
        "x": x,
        "y": y,
        "samples": [
            {"x": float(sample["x"]), "y": float(sample["y"]), "z": float(sample["z"])}
            for sample in samples
        ],
        **common,
    }


def discover_reference(
    client: Moonraker,
    dashboard: DashboardPublisher,
    *,
    x: float,
    y: float,
    phase: str,
) -> dict[str, Any]:
    """Find one valid physical tap in fixed, descending 2 mm bands."""
    status = client.status("toolhead")
    toolhead = status.get("toolhead", {})
    axis_minimum = toolhead.get("axis_minimum")
    if not isinstance(axis_minimum, list) or len(axis_minimum) < 3:
        raise CalibrationError("cannot determine the live Z minimum for staged search")
    z_min = float(axis_minimum[2])
    if abs(z_min - DISCOVERY_FINAL_Z_MM) > 1.0e-6:
        raise CalibrationError(
            f"live Z minimum {z_min:.6f} differs from required "
            f"{DISCOVERY_FINAL_Z_MM:.6f}"
        )
    bands = []
    start_z = DISCOVERY_START_Z_MM
    band_index = 0
    while start_z > z_min + 1.0e-9:
        # Keep the final band aligned with the documented Z=0 handoff; it is
        # intentionally 2.2 mm wide rather than introducing a second
        # overlapping window below zero.
        target_z = z_min if start_z <= 0.0 else max(z_min, start_z - DISCOVERY_BAND_MM)
        band_index += 1
        message = (
            f"Eddy reference {phase} discovery band {band_index}: "
            f"Z={start_z:.3f}->{target_z:.3f}"
        )
        dashboard.event(message, status="running")
        console(client, message)
        sample = reference_sample(
            client,
            x=x,
            y=y,
            index=band_index,
            phase=f"{phase}_discovery",
            start_z=start_z,
            target_z=target_z,
            retract=DISCOVERY_RETRACT_MM,
            allow_rejected=True,
        )
        band = {
            "index": band_index,
            "start_z": start_z,
            "target_z": target_z,
            "status": sample["status"],
        }
        bands.append(band)
        if sample["status"] == "contact":
            found_z = float(sample["z"])
            console(
                client, f"Eddy reference {phase} discovery contact Z={found_z:+.6f}"
            )
            dashboard.event(
                f"Eddy reference {phase} discovery contact Z={found_z:+.6f}",
                status="running",
            )
            return {
                "target": {"x": x, "y": y, "z": 0.0},
                "bands": bands,
                "contact": sample,
                "found_z": found_z,
                "z_min": z_min,
            }
        if sample["status"] == "rejected":
            diagnostics = sample.get("diagnostics", {})
            trigger_z = diagnostics.get("trigger_z")
            endpoint_tolerance = 0.010
            release_candidates = diagnostics.get("release_candidates", {})
            rejection_reasons = release_candidates.get("rejections", {})
            coverage_rejected = rejection_reasons.get(
                "insufficient_calibrated_coverage", 0
            )
            band["trigger_z"] = float(trigger_z) if trigger_z is not None else None
            band["error"] = sample.get("error", "rejected tap")
            if coverage_rejected:
                band["status"] = "coverage_rejected"
                message = (
                    f"Eddy reference {phase} rejected an uncalibrated high-Z "
                    "feature; retrying in next overlapping band"
                )
            elif (
                trigger_z is not None
                and abs(float(trigger_z) - target_z) <= endpoint_tolerance
                and target_z > z_min + 1.0e-9
            ):
                band["status"] = "boundary_rejected"
                message = (
                    f"Eddy reference {phase} boundary trigger at "
                    f"Z={float(trigger_z):+.6f}; retrying in next overlapping band"
                )
            else:
                band["status"] = "fit_rejected"
                message = (
                    f"Eddy reference {phase} rejected tap in band "
                    f"{start_z:.3f}->{target_z:.3f}; retrying in next overlapping band: "
                    f"{sample.get('error', 'unknown error')}"
                )
            console(client, message)
            dashboard.event(message, status="running")
        # Descend by one millimetre while retaining a two-millimetre guarded
        # window.  The final clamped band is emitted once and then terminates.
        if target_z <= z_min + 1.0e-9:
            break
        start_z = target_z + DISCOVERY_OVERLAP_MM
    raise CalibrationError(
        f"Eddy reference {phase} staged search reached Z minimum without a valid tap"
    )


def summarize(samples: list[dict[str, Any]]) -> dict[str, float]:
    values = [float(sample["z"]) for sample in samples]
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "span": max(values) - min(values),
        "standard_deviation": statistics.pstdev(values),
    }


def collect_reference(
    client: Moonraker,
    dashboard: DashboardPublisher,
    *,
    x: float,
    y: float,
    phase: str,
    discovery: dict[str, Any] | None,
) -> dict[str, Any]:
    if discovery is None:
        # Post-rebase verification is deliberately not another search.  The
        # first discovery established the physical datum and the common Z
        # correction was deployed; verify that datum in a fixed logical-Z
        # window only.
        start_z = NARROW_START_MARGIN_MM
        target_z = -NARROW_BELOW_CONTACT_MM
        method = "fixed_zero_window"
    else:
        discovery_z = float(discovery["found_z"])
        start_z = discovery_z + NARROW_START_MARGIN_MM
        target_z = max(float(discovery["z_min"]), discovery_z - NARROW_BELOW_CONTACT_MM)
        method = "discovery_relative_window"
    window = {
        "start_z": start_z,
        "target_z": target_z,
        "retract": NARROW_RETRACT_MM,
    }
    # Keep the five verification taps in one transaction. The Klipper helper
    # moves to the reference height once, performs the complete batch, and
    # restores the caller's height only after the final tap.
    batch = reference_sample(
        client,
        x=x,
        y=y,
        index=1,
        phase=phase,
        start_z=start_z,
        target_z=target_z,
        retract=NARROW_RETRACT_MM,
        count=REFERENCE_TAP_COUNT,
    )
    if batch["status"] != "contact_batch":
        raise CalibrationError(
            f"{phase} reference batch did not produce {REFERENCE_TAP_COUNT} taps"
        )
    samples = []
    for index, raw_sample in enumerate(batch["samples"], 1):
        sample = {
            "status": "contact",
            "index": index,
            "phase": phase,
            "x": float(raw_sample["x"]),
            "y": float(raw_sample["y"]),
            "z": float(raw_sample["z"]),
            "temperature_c": batch.get("temperature_c"),
            "gcode_origin": batch.get("gcode_origin"),
            "machine_position": batch.get("machine_position"),
            "config_fingerprint": batch.get("config_fingerprint"),
        }
        samples.append(sample)
        summary = summarize(samples)
        dashboard.bed["stage"] = phase
        dashboard.bed["reference"][phase] = {
            "target": {"x": x, "y": y, "z": 0.0},
            "discovery": discovery,
            "window": window,
            "progress": {"completed": len(samples), "total": REFERENCE_TAP_COUNT},
            "samples": samples,
            "summary": summary,
        }
        message = (
            f"Eddy reference {phase} tap {index}/{REFERENCE_TAP_COUNT}: "
            f"Z={sample['z']:.6f} mm"
        )
        dashboard.event(message, status="running")
        console(client, message)
    summary = summarize(samples)
    if summary["span"] > REFERENCE_MAX_SPAN_MM:
        raise CalibrationError(
            f"reference Tap span {summary['span']:.6f} exceeds "
            f"{REFERENCE_MAX_SPAN_MM:.3f} mm"
        )
    return {
        "target": {"x": x, "y": y, "z": 0.0},
        "verification_method": method,
        **({"discovery": discovery} if discovery is not None else {}),
        "window": window,
        "samples": samples,
        "summary": summary,
    }


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".rollback", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def generated_fingerprint() -> str:
    return compute_config_fingerprint(CALIB_PATH, TEMPLATE_PATH, CALIB_CONFIG_PATH)


def deploy_candidate(
    updates: dict[str, Any],
    *,
    expected_calib_sha256: str,
    run_dir: Path,
    label: str,
) -> str:
    prior_calib = CALIB_PATH.read_bytes()
    prior_printer = PRINTER_CFG_PATH.read_bytes()
    (run_dir / f"calib.yaml.before-{label}").write_bytes(prior_calib)
    (run_dir / f"printer.cfg.before-{label}").write_bytes(prior_printer)
    try:
        atomic_update(CALIB_PATH, updates, expected_sha256=expected_calib_sha256)
        subprocess.run([sys.executable, str(GENERATOR_PATH)], check=True)
        subprocess.run([str(DEPLOY_PATH)], check=True)
        subprocess.run([str(DEPLOY_PATH), "--check"], check=True)
    except BaseException:
        _write_bytes_atomic(CALIB_PATH, prior_calib)
        _write_bytes_atomic(PRINTER_CFG_PATH, prior_printer)
        try:
            subprocess.run([str(DEPLOY_PATH)], check=True)
            subprocess.run([str(DEPLOY_PATH), "--check"], check=True)
        except BaseException as rollback_error:
            raise CalibrationError(
                f"{label} deployment failed and automatic rollback failed: "
                f"{rollback_error}"
            ) from rollback_error
        raise
    (run_dir / f"calib.yaml.after-{label}").write_bytes(CALIB_PATH.read_bytes())
    (run_dir / f"printer.cfg.after-{label}").write_bytes(PRINTER_CFG_PATH.read_bytes())
    return generated_fingerprint()


def rollback_deployment(run_dir: Path, label: str) -> None:
    """Restore and deploy the exact source snapshot for a rejected candidate."""
    _write_bytes_atomic(
        CALIB_PATH, (run_dir / f"calib.yaml.before-{label}").read_bytes()
    )
    _write_bytes_atomic(
        PRINTER_CFG_PATH, (run_dir / f"printer.cfg.before-{label}").read_bytes()
    )
    subprocess.run([str(DEPLOY_PATH)], check=True)
    subprocess.run([str(DEPLOY_PATH), "--check"], check=True)


def matrix_hash(points: list[list[float]]) -> str:
    canonical = json.dumps(points, separators=(",", ":"), sort_keys=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mesh_plot(points: list[list[float]], path: Path) -> None:
    figure, (surface_axis, heat_axis) = plt.subplots(
        1,
        2,
        figsize=(13, 5.5),
        subplot_kw={"projection": "3d"},
    )
    # Replace the second 3D axis with a conventional heatmap axis.
    figure.delaxes(heat_axis)
    heat_axis = figure.add_subplot(1, 2, 2)
    fixed = yaml.safe_load(CALIB_CONFIG_PATH.read_text(encoding="utf-8"))
    x_min, x_max = float(fixed["bed_mesh_min_x_mm"]), float(fixed["bed_mesh_max_x_mm"])
    y_min, y_max = float(fixed["bed_mesh_min_y_mm"]), float(fixed["bed_mesh_max_y_mm"])
    import numpy as np

    x_values = np.linspace(x_min, x_max, len(points[0]))
    y_values = np.linspace(y_min, y_max, len(points))
    xx, yy = np.meshgrid(x_values, y_values)
    zz = np.asarray(points)
    surface_axis.plot_surface(xx, yy, zz, cmap="coolwarm", edgecolor="#334155")
    surface_axis.set_title("Persistent Eddy-Tap bed mesh")
    surface_axis.set_xlabel("X (mm)")
    surface_axis.set_ylabel("Y (mm)")
    surface_axis.set_zlabel("Z deviation (mm)")
    image = heat_axis.imshow(
        zz,
        origin="lower",
        extent=(x_min, x_max, y_min, y_max),
        aspect="auto",
        cmap="coolwarm",
        vmin=-max(abs(float(zz.min())), abs(float(zz.max()))),
        vmax=max(abs(float(zz.min())), abs(float(zz.max()))),
    )
    heat_axis.contour(xx, yy, zz, levels=[0.0], colors="black", linewidths=1.5)
    heat_axis.scatter(
        [150.0], [150.0], marker="*", s=100, color="gold", edgecolor="black"
    )
    heat_axis.set_title("Zero-referenced at X=150, Y=150")
    heat_axis.set_xlabel("X (mm)")
    heat_axis.set_ylabel("Y (mm)")
    figure.colorbar(image, ax=heat_axis, label="Z deviation (mm)")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def run_mesh(
    client: Moonraker,
    dashboard: DashboardPublisher,
    *,
    fixed: dict[str, Any],
) -> dict[str, Any]:
    total = int(fixed["bed_mesh_x_count"]) * int(fixed["bed_mesh_y_count"])
    dashboard.bed["stage"] = "mesh_acquisition"
    dashboard.bed["mesh"] = {
        "status": "running",
        "progress": {"completed": 0, "total": total},
    }
    dashboard.event("Eddy Tap mesh acquisition started", status="running")
    console(client, f"mesh acquisition started: 0/{total} points")
    previous = {
        (entry.get("time"), entry.get("type"), entry.get("message"))
        for entry in client.gcode_store()
    }
    command = (
        f"BED_MESH_CALIBRATE SAMPLES={int(fixed['bed_mesh_samples'])} "
        f"SETTLE_MS={int(fixed['bed_mesh_settle_ms'])}"
    )
    pattern = re.compile(
        r"IDEX calibration mesh point (\d+)/(\d+): probing X=([-0-9.]+) Y=([-0-9.]+)"
    )
    seen: set[tuple[Any, Any, Any]] = set(previous)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.gcode, command, timeout=1200)
        while not future.done():
            for entry in client.gcode_store():
                marker = (entry.get("time"), entry.get("type"), entry.get("message"))
                if marker in seen:
                    continue
                seen.add(marker)
                match = pattern.search(str(entry.get("message", "")))
                if not match:
                    continue
                index = int(match.group(1))
                dashboard.bed["mesh"]["progress"] = {
                    "completed": max(0, index - 1),
                    "current": index,
                    "total": int(match.group(2)),
                }
                dashboard.bed["mesh"]["latest_point"] = {
                    "x": float(match.group(3)),
                    "y": float(match.group(4)),
                }
                dashboard.publish()
            time.sleep(0.75)
        future.result()

    status = client.status("bed_mesh", "configfile", "save_config_pending_items")
    mesh = status.get("bed_mesh", {})
    profile = str(fixed["bed_mesh_profile"])
    if mesh.get("profile_name") != profile:
        raise CalibrationError(f"new mesh did not activate profile {profile}")
    matrix = mesh.get("probed_matrix") or mesh.get("mesh_matrix")
    if not isinstance(matrix, list) or len(matrix) != int(fixed["bed_mesh_y_count"]):
        raise CalibrationError("new mesh has the wrong Y dimension")
    points = [[float(value) for value in row] for row in matrix]
    if any(len(row) != int(fixed["bed_mesh_x_count"]) for row in points):
        raise CalibrationError("new mesh has the wrong X dimension")
    if any(not math.isfinite(value) for row in points for value in row):
        raise CalibrationError("new mesh contains non-finite values")
    config_bed_mesh = (
        status.get("configfile", {}).get("settings", {}).get("bed_mesh", {})
    )
    zero_reference = config_bed_mesh.get("zero_reference_position")
    if [round(float(value), 6) for value in zero_reference or []] != [150.0, 150.0]:
        raise CalibrationError("active mesh is not zero-referenced at X=150 Y=150")
    flat = [value for row in points for value in row]
    result = {
        "status": "completed",
        "profile": profile,
        "points": points,
        "point_count": len(flat),
        "minimum": min(flat),
        "maximum": max(flat),
        "range": max(flat) - min(flat),
        "mean": statistics.fmean(flat),
        "matrix_sha256": matrix_hash(points),
        "zero_reference_position": [150.0, 150.0],
    }
    dashboard.bed["mesh"].update(result)
    dashboard.bed["mesh"]["progress"] = {"completed": total, "total": total}
    dashboard.publish()
    return result


def verify_persistent_mesh(
    client: Moonraker,
    *,
    expected: list[list[float]],
    profile: str,
    fixed: dict[str, Any],
) -> dict[str, Any]:
    prepare_t0(client)
    client.gcode(f"BED_MESH_PROFILE LOAD={profile}\nM400")
    status = client.status("bed_mesh", "configfile", "gcode_move", "idex_manual_tuning")
    mesh = status.get("bed_mesh", {})
    points = mesh.get("profiles", {}).get(profile, {}).get("points")
    points = [[float(value) for value in row] for row in points or []]
    if points != expected:
        raise CalibrationError("deployed persistent mesh differs from accepted matrix")
    if mesh.get("profile_name") != profile:
        raise CalibrationError("persistent default mesh is not active")
    return {
        "status": "passed",
        "profile": profile,
        "matrix_sha256": matrix_hash(points),
        "active": True,
        "manual_z_adjust": status.get("idex_manual_tuning", {}).get("manual_z_adjust"),
    }


def verify_active_mesh_contacts(
    client: Moonraker, fixed: dict[str, Any]
) -> dict[str, Any]:
    x_min = float(fixed["bed_mesh_min_x_mm"])
    x_max = float(fixed["bed_mesh_max_x_mm"])
    y_min = float(fixed["bed_mesh_min_y_mm"])
    y_max = float(fixed["bed_mesh_max_y_mm"])
    reference_x = float(fixed["eddy_bed_reference_x_mm"])
    reference_y = float(fixed["eddy_bed_reference_y_mm"])
    verification_points = (
        (reference_x, reference_y),
        (x_min, y_min),
        (x_max, y_min),
        (x_min, y_max),
        (x_max, y_max),
    )
    residuals = []
    for x, y in verification_points:
        client.gcode(
            f"EDDY_TAP_MEASURE X={x:.3f} Y={y:.3f} COUNT=1 EDDY_MODE=none",
            timeout=90,
        )
        measurement = (
            client.status("eddy_tap_measure")
            .get("eddy_tap_measure", {})
            .get("last_tap_measurement")
        )
        if not isinstance(measurement, dict):
            raise CalibrationError("mesh-aware Tap did not publish a measurement")
        residual = measurement.get("mesh", {}).get("commanded_z_for_tap_median")
        if residual is None:
            raise CalibrationError("mesh-aware Tap did not use the active mesh")
        residual = float(residual)
        residuals.append({"x": x, "y": y, "logical_contact_z": residual})
        if abs(residual) > MESH_AWARE_TOLERANCE_MM:
            raise CalibrationError(
                f"mesh-aware contact at X={x:.3f} Y={y:.3f} is "
                f"Z={residual:+.6f}, outside {MESH_AWARE_TOLERANCE_MM:.3f} mm"
            )
    return {
        "status": "passed",
        "physical_checks": residuals,
        "physical_check_tolerance_mm": MESH_AWARE_TOLERANCE_MM,
    }


def persist_mesh(
    client: Moonraker,
    dashboard: DashboardPublisher,
    *,
    run_dir: Path,
    fixed: dict[str, Any],
    mesh: dict[str, Any],
) -> dict[str, Any]:
    """Persist an accepted live mesh and prove the deployed profile matches it."""
    mesh_path = run_dir / "mesh_points.csv"
    with mesh_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(mesh["points"])
    plot_path = run_dir / "mesh.png"
    mesh_plot(mesh["points"], plot_path)
    dashboard.bed["mesh"]["plot"] = dashboard.upload(plot_path, "bed_mesh.png")
    atomic_json(run_dir / "mesh_result.json", mesh)
    dashboard.publish()
    mesh_source_sha = sha256_file(CALIB_PATH)
    dashboard.bed["stage"] = "mesh_deployment"
    dashboard.event("Persisting and deploying accepted bed mesh", status="running")
    console(client, "persisting and deploying accepted bed mesh")
    mesh_fingerprint = deploy_candidate(
        {"bed_mesh_points": mesh["points"]},
        expected_calib_sha256=mesh_source_sha,
        run_dir=run_dir,
        label="mesh",
    )
    try:
        verification = verify_persistent_mesh(
            client,
            expected=mesh["points"],
            profile=str(fixed["bed_mesh_profile"]),
            fixed=fixed,
        )
    except BaseException:
        # Deployment is transactional: leave the previously accepted mesh and
        # calibration active when reload/parity verification rejects a
        # candidate.
        rollback_deployment(run_dir, "mesh")
        raise
    verification["target_config_fingerprint"] = mesh_fingerprint
    atomic_json(run_dir / "mesh_verification.json", verification)
    dashboard.bed["mesh"]["verification"] = verification
    dashboard.bed["mesh"]["status"] = "passed"
    dashboard.bed["stage"] = "completed"
    dashboard.bed["status"] = "completed"
    dashboard.event("Persistent Eddy Tap mesh deployed and active", status="completed")
    console(client, "persistent Eddy Tap mesh deployed and active")
    dashboard.publish()
    return {
        "mesh": mesh,
        "mesh_verification": verification,
        "target_config_fingerprint": mesh_fingerprint,
    }


def main(argv: list[str]) -> int:
    if argv:
        raise CalibrationError(
            "this prescribed workflow accepts no command-line options"
        )
    batch_id = os.environ.get("IDEX_CALIBRATION_BATCH_ID") or dt.datetime.now(
        dt.timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    phase = os.environ.get("IDEX_EDDY_PHASE", "full").strip().lower()
    if phase not in VALID_PHASES:
        raise CalibrationError(
            f"unsupported IDEX_EDDY_PHASE {phase!r}; expected full, reference, or mesh"
        )
    run_dir = Path(
        os.environ.get(
            "IDEX_BED_CALIBRATION_RUN_DIR",
            REPO_ROOT / "runs/idex_calibration" / batch_id / "bed_calibration",
        )
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    remote_host = os.environ.get("MENDERPI_HOST", DEFAULT_REMOTE_HOST)
    client = Moonraker(os.environ.get("MOONRAKER_URL", DEFAULT_MOONRAKER_URL))
    dashboard = DashboardPublisher(batch_id, remote_host)
    measured = load_measured(CALIB_PATH)
    fixed = yaml.safe_load(CALIB_CONFIG_PATH.read_text(encoding="utf-8"))
    source_sha = sha256_file(CALIB_PATH)
    source_fingerprint = generated_fingerprint()
    shutil.copy2(CALIB_PATH, run_dir / "calib.yaml.source")
    shutil.copy2(CALIB_CONFIG_PATH, run_dir / "calib_config.yaml.source")
    shutil.copy2(PRINTER_CFG_PATH, run_dir / "printer.cfg.source")
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "workflow": f"idex_eddy_tap_bed_calibration_v2_{phase}",
        "phase": phase,
        "batch_id": batch_id,
        "started_at": utc_now(),
        "status": "running",
        "source_calib_sha256": source_sha,
        "source_config_fingerprint": source_fingerprint,
        "source_endstops": endstops(measured),
        "reference": {
            "x": float(fixed["eddy_bed_reference_x_mm"]),
            "y": float(fixed["eddy_bed_reference_y_mm"]),
            "z": 0.0,
        },
    }
    atomic_json(run_dir / "manifest.json", manifest)
    try:
        live = require_ready(client)
        if config_fingerprint(live) != source_fingerprint:
            raise CalibrationError(
                "live configuration does not match local calibration source"
            )
        if phase == "mesh":
            dashboard.activity(5, "Tap mesh acquisition", "Preparing the bed mesh run")
            homed = prepare_t0(client)
            dashboard.bed["homing_required"] = homed
            dashboard.event("Eddy mesh preflight passed", status="running")
            console(client, f"Eddy mesh stage started; homing_required={homed}")
            mesh = run_mesh(client, dashboard, fixed=fixed)
            mesh["active_physical_verification"] = verify_active_mesh_contacts(
                client, fixed
            )
            dashboard.bed["mesh"].update(mesh)
            dashboard.publish()
            dashboard.activity(6, "Redeploy and verify the mesh", "Persisting and checking the active mesh")
            persisted = persist_mesh(
                client, dashboard, run_dir=run_dir, fixed=fixed, mesh=mesh
            )
            manifest.update(
                {
                    "status": "completed",
                    "finished_at": utc_now(),
                    "mesh": mesh,
                    "mesh_verification": persisted["mesh_verification"],
                    "target_config_fingerprint": persisted["target_config_fingerprint"],
                }
            )
        else:
            homed = prepare_t0(client)
            dashboard.bed["homing_required"] = homed
            dashboard.event("Eddy bed reference preflight passed", status="running")
            console(client, f"Eddy bed reference started; homing_required={homed}")

            x, y = manifest["reference"]["x"], manifest["reference"]["y"]
            dashboard.activity(1, "Bed Center Z=0 measurement", "Banded centre discovery")
            before_discovery = discover_reference(
                client, dashboard, x=x, y=y, phase="before_rebase"
            )
            before = collect_reference(
                client,
                dashboard,
                x=x,
                y=y,
                phase="before_rebase",
                discovery=before_discovery,
            )
            atomic_json(run_dir / "reference_before.json", before)
            common_delta = -float(before["summary"]["median"])
            if not -DISCOVERY_START_Z_MM <= common_delta <= -DISCOVERY_FINAL_Z_MM:
                raise CalibrationError(
                    f"refusing common Z correction {common_delta:+.6f} mm; "
                    "outside the staged-search envelope"
                )
            source = endstops(load_measured(CALIB_PATH))
            target_t0 = round(source["t0"]["z_endstop"] + common_delta, 3)
            target_t1 = round(source["t1"]["z_endstop"] + common_delta, 3)
            source_difference = source["t1"]["z_endstop"] - source["t0"]["z_endstop"]
            target_difference = target_t1 - target_t0
            if abs(source_difference - target_difference) > 1.0e-9:
                raise CalibrationError(
                    "common Z rebase would change T1-T0 Z difference"
                )
            rebase = {
                "source_endstops": source,
                "common_delta_mm": common_delta,
                "target_endstops": {
                    "t0_z_endstop": target_t0,
                    "t1_z_endstop": target_t1,
                },
                "source_t1_minus_t0_mm": source_difference,
                "target_t1_minus_t0_mm": target_difference,
                "difference_preserved": True,
            }
            dashboard.bed["reference"]["rebase"] = rebase
            dashboard.activity(2, "Bed Center Z=0 calibration update", "Deploying the common T0/T1 Z correction")
            atomic_json(run_dir / "z_rebase_result.json", rebase)
            dashboard.bed["stage"] = "reference_deployment"
            dashboard.event(
                f"Applying common Z delta {common_delta:+.6f} mm to T0 and T1",
                status="running",
            )
            console(
                client,
                f"common Z delta={common_delta:+.6f} mm; T1-T0 difference preserved",
            )
            target_fingerprint = deploy_candidate(
                {"t0_z_endstop": target_t0, "t1_z_endstop": target_t1},
                expected_calib_sha256=source_sha,
                run_dir=run_dir,
                label="z-rebase",
            )
            dashboard.bed["reference"]["rebase"][
                "target_config_fingerprint"
            ] = target_fingerprint
            atomic_json(run_dir / "z_rebase_result.json", rebase)
            prepare_t0(client)
            dashboard.activity(3, "Bed Center Z=0 verification", "Five fixed-window centre taps")
            after = collect_reference(
                client,
                dashboard,
                x=x,
                y=y,
                phase="after_rebase",
                discovery=None,
            )
            atomic_json(run_dir / "reference_after.json", after)
            residual = float(after["summary"]["median"])
            if abs(residual) > REFERENCE_ZERO_TOLERANCE_MM:
                rollback_deployment(run_dir, "z-rebase")
                raise CalibrationError(
                    f"post-rebase reference Z {residual:+.6f} exceeds "
                    f"{REFERENCE_ZERO_TOLERANCE_MM:.3f} mm"
                )
            dashboard.bed["reference"]["result"] = {
                "status": "passed",
                "residual_mm": residual,
            }
            dashboard.event(
                f"Post-deploy bed reference passed: Z={residual:+.6f} mm",
                status="running",
            )
            console(client, f"bed reference passed at Z={residual:+.6f} mm")
            reference_result = {
                "reference_before": before,
                "z_rebase": rebase,
                "reference_after": after,
                "target_config_fingerprint": target_fingerprint,
            }
            if phase == "reference":
                dashboard.bed["stage"] = "reference_complete"
                dashboard.bed["status"] = "completed"
                dashboard.event(
                    "Eddy bed reference deployed and verified", status="completed"
                )
                console(client, "Eddy bed reference deployed and verified")
                manifest.update(
                    {
                        "status": "completed",
                        "finished_at": utc_now(),
                        **reference_result,
                    }
                )
            else:
                dashboard.activity(5, "Tap mesh acquisition", "Measuring the bed surface")
                mesh = run_mesh(client, dashboard, fixed=fixed)
                mesh["active_physical_verification"] = verify_active_mesh_contacts(
                    client, fixed
                )
                dashboard.bed["mesh"].update(mesh)
                dashboard.publish()
                dashboard.activity(6, "Redeploy and verify the mesh", "Persisting and checking the active mesh")
                persisted = persist_mesh(
                    client, dashboard, run_dir=run_dir, fixed=fixed, mesh=mesh
                )
                manifest.update(
                    {
                        "status": "completed",
                        "finished_at": utc_now(),
                        **reference_result,
                        "mesh": mesh,
                        "mesh_verification": persisted["mesh_verification"],
                        "target_config_fingerprint": persisted[
                            "target_config_fingerprint"
                        ],
                    }
                )
    except BaseException as exc:
        manifest.update(
            {"status": "failed", "finished_at": utc_now(), "error": str(exc)}
        )
        dashboard.bed["stage"] = "failed"
        dashboard.bed["status"] = "failed"
        dashboard.bed["error"] = str(exc)
        try:
            dashboard.event(f"Eddy bed calibration FAILED: {exc}", status="failed")
            console(client, f"Eddy bed calibration FAILED: {exc}")
        except BaseException:
            pass
        try:
            dashboard.stop_activity()
        except BaseException:
            pass
        try:
            acceptance_call(
                remote_host,
                "fail",
                {
                    "batch_id": batch_id,
                    "status": "failed",
                    "stage": f"bed_calibration.{phase}",
                    "error": str(exc),
                },
            )
        except BaseException:
            pass
        atomic_json(run_dir / "manifest.json", manifest)
        try:
            dashboard.upload_run_evidence(run_dir)
        except BaseException:
            pass
        raise
    atomic_json(run_dir / "manifest.json", manifest)
    atomic_json(run_dir / "bed_calibration_result.json", manifest)
    dashboard.upload_run_evidence(run_dir)
    # Commit only after the immutable attempt is complete and all deployment /
    # physical checks have passed.  A failed attempt never overwrites the
    # accepted working set; the acceptance writer keeps it available for a
    # later compatible chapter rerun.
    checkpoint_name = f"{batch_id}_{phase}_accepted_calib.yaml"
    checkpoint = dashboard.upload(CALIB_PATH, checkpoint_name)
    fixed_inputs = acceptance_fixed_inputs()
    current_calib = endstops(load_measured(CALIB_PATH))
    if phase == "reference":
        reference_data = {
            "before_rebase": manifest.get("reference_before"),
            "after_rebase": manifest.get("reference_after"),
            "rebase": manifest.get("z_rebase"),
            "result": {"status": "passed", "residual_mm": manifest.get("reference_after", {}).get("summary", {}).get("median")},
        }
        invariants = {
            "fixed_inputs": fixed_inputs,
            "reference": [manifest["reference"]["x"], manifest["reference"]["y"]],
            "t0_z_endstop": current_calib["t0"]["z_endstop"],
        }
        chapter_data = {"reference": reference_data}
    else:
        mesh_data = manifest.get("mesh") or {}
        matrix = mesh_data.get("points") or []
        invariants = {
            "fixed_inputs": fixed_inputs,
            "reference": [manifest["reference"]["x"], manifest["reference"]["y"]],
            "t0_frame": [
                current_calib["t0"]["x_endstop"],
                current_calib["t0"]["y_endstop"],
                current_calib["t0"]["z_endstop"],
            ],
            "matrix_sha256": hashlib.sha256(
                json.dumps(matrix, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        chapter_data = {"mesh": mesh_data, "reference": manifest.get("reference_before")}
    acceptance_call(
        remote_host,
        "accept",
        {
            "chapter": "bed_reference" if phase == "reference" else "mesh",
            "entry": acceptance_entry(
                chapter="bed_reference" if phase == "reference" else "mesh",
                batch_id=batch_id,
                run_scope=os.environ.get("IDEX_CALIBRATION_RUN_SCOPE", "bed_reference"),
                artifact=f"runs/{batch_id}/bed_calibration/{run_dir.name}/bed_calibration_result.json",
                data=chapter_data,
                invariants=invariants,
                checkpoint=checkpoint,
            ),
        },
    )
    dashboard.finish_activity("completed", "Eddy bed workflow completed")
    dashboard.stop_activity()
    print(f"Eddy bed calibration complete: {run_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (
        CalibrationError,
        CalibrationDataError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
