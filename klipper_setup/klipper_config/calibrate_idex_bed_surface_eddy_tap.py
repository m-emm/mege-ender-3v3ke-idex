#!/usr/bin/env python3
"""Run the guarded IDEX Z Iteration 1 physical/sensor calibration.

The script deliberately keeps measured mesh data out of the repository.  Eddy
drive current, its height/frequency table, and the verified tap threshold are
the only measured values that become canonical configuration.  The mesh made
by ``BED_MESH_CALIBRATE`` remains session-local evidence.

Most of this module is intentionally dependency-light.  The pure calculation
helpers are useful in tests and make it possible to run ``--dry-run`` without
opening a printer connection or changing a file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlencode

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
CALIB_PATH = SCRIPT_DIR / "calib.yaml"
TEMPLATE_PATH = SCRIPT_DIR / "printer.cfg.template"
CONFIG_PATH = SCRIPT_DIR / "printer.cfg"
GENERATOR_PATH = SCRIPT_DIR / "generate_printer_cfg.py"
DEPLOY_PATH = SCRIPT_DIR / "update_menderpi.sh"
RUN_ROOT = REPO_ROOT / "runs" / "idex_z_iteration_1"
DEFAULT_HOST = os.environ.get("MENDERPI_HOST", "pi@menderpi.local")
EXPECTED_KLIPPER_COMMIT = "ca8230d505b7ba7fd225bfa6ed9655bc4520e805"

REFERENCE_X = 150.0
REFERENCE_Y = 150.0
CONTACT_Z = 0.0
TAP_SUCCESS_COUNT = 7
TAP_MAX_ATTEMPTS = 10
TAP_MAX_SPAN = 0.030
TAP_MAX_STDDEV = 0.010
CENTER_MEAN_TOLERANCE = 0.010
CENTER_SPAN_TOLERANCE = 0.020
MESH_CENTER_TOLERANCE = 0.005
MESH_POINT_TOLERANCE = 0.030
MESH_RMS_TOLERANCE = 0.015
DEFAULT_TAP_THRESHOLD = 5000
ARMING_PHRASE = "CALIBRATE IDEX Z ITERATION 1"


class CalibrationError(RuntimeError):
    """A calibration gate failed and the run must stop."""


class Phase(str, Enum):
    PREFLIGHT = "I1.0"
    BOOTSTRAP_TAP = "I1.1"
    ENDSTOPS = "I1.2"
    CENTER_VERIFY = "I1.3"
    DRIVE_CURRENT = "I1.4"
    EDDY_CALIBRATION = "I1.5"
    TAP_THRESHOLD = "I1.6"
    REANCHOR = "I1.7"
    MESH_SCAN = "I1.8"
    MESH_VERIFY = "I1.9"
    FINISH = "I1.10"


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class AxisBounds:
    minimum: float
    maximum: float

    def contains(self, value: float, margin: float = 0.0) -> bool:
        return self.minimum + margin <= value <= self.maximum - margin


@dataclass(frozen=True)
class TapSummary:
    successful: tuple[float, ...]
    rejected_attempts: int
    mean: float
    median: float
    standard_deviation: float
    span: float


@dataclass
class RunState:
    run_id: str
    phase: str
    committed_phase: str | None = None
    source_hashes: dict[str, str] | None = None
    evidence: dict[str, Any] | None = None


@dataclass(frozen=True)
class MeshPoint:
    x: float
    y: float


def utc_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_taps(
    successful: Sequence[float],
    *,
    attempts: int | None = None,
) -> TapSummary:
    """Return robust tap statistics and account for rejected attempts."""

    values = tuple(float(value) for value in successful)
    if not values:
        raise CalibrationError("no successful tap samples were acquired")
    attempts = len(values) if attempts is None else int(attempts)
    if attempts < len(values):
        raise ValueError("attempt count cannot be smaller than successes")
    return TapSummary(
        successful=values,
        rejected_attempts=attempts - len(values),
        mean=statistics.fmean(values),
        median=statistics.median(values),
        standard_deviation=statistics.pstdev(values),
        span=max(values) - min(values),
    )


def require_tap_acceptance(
    summary: TapSummary,
    *,
    required_successes: int = TAP_SUCCESS_COUNT,
    max_rejected: int = TAP_MAX_ATTEMPTS - TAP_SUCCESS_COUNT,
    max_span: float = TAP_MAX_SPAN,
    max_standard_deviation: float = TAP_MAX_STDDEV,
) -> None:
    if len(summary.successful) != required_successes:
        raise CalibrationError(
            f"expected {required_successes} successful taps, got "
            f"{len(summary.successful)}"
        )
    if summary.rejected_attempts > max_rejected:
        raise CalibrationError(
            f"rejected tap attempts {summary.rejected_attempts} exceed "
            f"maximum {max_rejected}"
        )
    if summary.span > max_span:
        raise CalibrationError(
            f"tap span {summary.span:.6f} mm exceeds {max_span:.6f} mm"
        )
    if summary.standard_deviation > max_standard_deviation:
        raise CalibrationError(
            "tap standard deviation "
            f"{summary.standard_deviation:.6f} mm exceeds "
            f"{max_standard_deviation:.6f} mm"
        )


def common_endstop_update(
    t0_old: float,
    t1_old: float,
    tap_contact_z: float,
) -> tuple[float, float, float]:
    """Translate both endstops so the observed T0 contact becomes Z=0."""

    delta = CONTACT_Z - float(tap_contact_z)
    return t0_old + delta, t1_old + delta, delta


def assert_relative_alignment(
    old_t0: float,
    old_t1: float,
    new_t0: float,
    new_t1: float,
    *,
    expected_delta: float | None = None,
    tolerance: float = 1e-9,
) -> None:
    old_delta = float(old_t0) - float(old_t1)
    new_delta = float(new_t0) - float(new_t1)
    if not math.isclose(old_delta, new_delta, abs_tol=tolerance):
        raise CalibrationError(
            f"common endstop update changed T0/T1 relative Z: "
            f"{old_delta:.9f} -> {new_delta:.9f}"
        )
    if expected_delta is not None and not math.isclose(
        old_delta, float(expected_delta), abs_tol=tolerance
    ):
        raise CalibrationError(
            f"stored vision T1/T0 Z delta {expected_delta!r} does not match "
            f"current source delta {old_delta:.9f}"
        )


def validate_vision_relative_provenance(
    calibration: Mapping[str, Any],
    *,
    tolerance: float | None = None,
) -> float:
    provenance = calibration.get("vision_relative_alignment")
    if not isinstance(provenance, Mapping):
        raise CalibrationError(
            "calib.yaml is missing vision_relative_alignment provenance"
        )
    try:
        expected = float(provenance["t0_minus_t1_z"])
        declared_tolerance = float(provenance["tolerance_mm"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CalibrationError(
            "vision_relative_alignment must declare t0_minus_t1_z and " "tolerance_mm"
        ) from exc
    if declared_tolerance <= 0:
        raise CalibrationError("vision relative-alignment tolerance must be positive")
    if tolerance is not None and declared_tolerance > tolerance:
        raise CalibrationError(
            "vision relative-alignment provenance tolerance is broader than "
            "the workflow acceptance tolerance"
        )
    return expected


def coil_over_target_pose(
    target: Pose,
    nozzle_to_coil: Pose,
) -> Pose:
    """Return the nozzle pose that places the Eddy coil at ``target``."""

    return Pose(
        x=target.x - nozzle_to_coil.x,
        y=target.y - nozzle_to_coil.y,
        z=target.z - nozzle_to_coil.z,
    )


def validate_pose(
    pose: Pose,
    *,
    x: AxisBounds,
    y: AxisBounds,
    z: AxisBounds,
    label: str = "pose",
) -> None:
    if not x.contains(pose.x) or not y.contains(pose.y) or not z.contains(pose.z):
        raise CalibrationError(
            f"{label} is outside motion limits: "
            f"({pose.x:.3f}, {pose.y:.3f}, {pose.z:.3f})"
        )


def mesh_corrected_contact_z(raw_tap_z: float, mesh_correction_z: float) -> float:
    """Apply the bed-mesh inverse to a raw kinematic tap result."""

    return float(raw_tap_z) - float(mesh_correction_z)


def mesh_correction_at(
    matrix: Sequence[Sequence[float]],
    *,
    mesh_min: MeshPoint,
    mesh_max: MeshPoint,
    point: MeshPoint,
) -> float:
    """Bilinearly interpolate a Klipper mesh matrix at a validation point."""

    if not matrix or not matrix[0] or len({len(row) for row in matrix}) != 1:
        raise CalibrationError("active mesh matrix is empty or ragged")
    rows = len(matrix)
    columns = len(matrix[0])
    if (
        not mesh_min.x <= point.x <= mesh_max.x
        or not mesh_min.y <= point.y <= mesh_max.y
    ):
        raise CalibrationError(f"mesh lookup point is outside the active mesh: {point}")
    x_fraction = (point.x - mesh_min.x) / (mesh_max.x - mesh_min.x)
    y_fraction = (point.y - mesh_min.y) / (mesh_max.y - mesh_min.y)
    x_position = x_fraction * (columns - 1)
    y_position = y_fraction * (rows - 1)
    x0 = min(int(math.floor(x_position)), columns - 1)
    x1 = min(x0 + 1, columns - 1)
    y0 = min(int(math.floor(y_position)), rows - 1)
    y1 = min(y0 + 1, rows - 1)
    dx = x_position - x0
    dy = y_position - y0
    lower = float(matrix[y0][x0]) * (1.0 - dx) + float(matrix[y0][x1]) * dx
    upper = float(matrix[y1][x0]) * (1.0 - dx) + float(matrix[y1][x1]) * dx
    return lower * (1.0 - dy) + upper * dy


def mesh_tap_acceptance(
    tap_samples: Mapping[MeshPoint, Sequence[float]],
    mesh_corrections: Mapping[MeshPoint, float],
    *,
    point_tolerance: float = MESH_POINT_TOLERANCE,
    rms_tolerance: float = MESH_RMS_TOLERANCE,
) -> dict[str, Any]:
    """Calculate and gate raw-tap minus mesh-correction results."""

    corrected: dict[str, dict[str, float]] = {}
    residuals: list[float] = []
    for point, samples in tap_samples.items():
        if point not in mesh_corrections:
            raise CalibrationError(f"missing mesh correction for tap point {point}")
        summary = summarize_taps(samples, attempts=len(samples))
        if summary.rejected_attempts or summary.span > 0.020:
            raise CalibrationError(f"tap repeatability failed at {point}")
        corrected_z = mesh_corrected_contact_z(summary.mean, mesh_corrections[point])
        residuals.append(corrected_z)
        corrected[f"{point.x:.3f},{point.y:.3f}"] = {
            "raw_mean": summary.mean,
            "mesh_correction": float(mesh_corrections[point]),
            "mesh_corrected_mean": corrected_z,
            "span": summary.span,
        }
    if not residuals:
        raise CalibrationError("no tap-safe mesh validation points were measured")
    rms = math.sqrt(statistics.fmean(value * value for value in residuals))
    if any(abs(value) > point_tolerance for value in residuals):
        raise CalibrationError(
            f"mesh-corrected tap exceeds point tolerance: {residuals}"
        )
    if rms > rms_tolerance:
        raise CalibrationError(
            f"mesh-corrected tap RMS {rms:.6f} exceeds {rms_tolerance:.6f}"
        )
    return {"points": corrected, "rms": rms, "max_abs": max(map(abs, residuals))}


def derive_safe_tap_grid(
    *,
    nozzle_x: AxisBounds,
    nozzle_y: AxisBounds,
    mesh_x: AxisBounds,
    mesh_y: AxisBounds,
    coil_offset_x: float,
    coil_offset_y: float,
    margin: float = 5.0,
    count: int = 3,
) -> tuple[MeshPoint, ...]:
    """Derive a grid in the intersection safe for both nozzle and coil taps."""

    if count < 2:
        raise ValueError("tap validation grid needs at least two points per axis")
    x_min = max(nozzle_x.minimum, mesh_x.minimum, mesh_x.minimum - coil_offset_x)
    x_max = min(nozzle_x.maximum, mesh_x.maximum, mesh_x.maximum - coil_offset_x)
    y_min = max(nozzle_y.minimum, mesh_y.minimum, mesh_y.minimum - coil_offset_y)
    y_max = min(nozzle_y.maximum, mesh_y.maximum, mesh_y.maximum - coil_offset_y)
    x_min += margin
    x_max -= margin
    y_min += margin
    y_max -= margin
    if x_min >= x_max or y_min >= y_max:
        raise CalibrationError("no safe nozzle/coil overlap exists for tap validation")
    xs = [x_min + (x_max - x_min) * i / (count - 1) for i in range(count)]
    ys = [y_min + (y_max - y_min) * i / (count - 1) for i in range(count)]
    return tuple(MeshPoint(x, y) for y in ys for x in xs)


def extract_pending_value(
    pending: Mapping[str, Any] | Sequence[Any],
    section: str,
    option: str,
) -> Any:
    """Extract a Klipper ``save_config_pending_items`` value.

    Klipper has represented this status as both a section mapping and a list
    of records across versions; accepting both keeps the runner pinned to the
    printer's declared Klipper revision without hard-coding one JSON shape.
    """

    section_names = {section, f"[{section}]"}

    def unwrap(value: Any) -> Any:
        if isinstance(value, Mapping) and "value" in value:
            return value["value"]
        return value

    if isinstance(pending, Mapping):
        for name in section_names:
            candidate = pending.get(name)
            if isinstance(candidate, Mapping) and option in candidate:
                return unwrap(candidate[option])
        for candidate in pending.values():
            try:
                return extract_pending_value(candidate, section, option)
            except KeyError:
                pass
    elif isinstance(pending, Sequence) and not isinstance(pending, (str, bytes)):
        for item in pending:
            if not isinstance(item, Mapping):
                continue
            item_section = item.get("section", item.get("name"))
            item_option = item.get("option", item.get("key"))
            if item_section in section_names and item_option == option:
                return unwrap(item.get("value"))
            try:
                return extract_pending_value(item, section, option)
            except KeyError:
                pass
    raise KeyError(f"pending config value not found: [{section}] {option}")


def pending_sections(pending: Any, *, _root: bool = True) -> set[str]:
    """Collect section names from a pending-config object for gate checks."""

    found: set[str] = set()
    if isinstance(pending, Mapping):
        for key, value in pending.items():
            if isinstance(key, str) and (
                key.startswith("[")
                or key in {"bed_mesh", "probe_eddy_current btt_eddy"}
                or (_root and isinstance(value, Mapping))
            ):
                found.add(key.strip("[]"))
            found.update(pending_sections(value, _root=False))
    elif isinstance(pending, Sequence) and not isinstance(pending, (str, bytes)):
        for item in pending:
            if isinstance(item, Mapping):
                section = item.get("section", item.get("name"))
                if isinstance(section, str):
                    found.add(section.strip("[]"))
                found.update(pending_sections(item, _root=False))
    return found


def require_only_transient_mesh_pending(pending: Any) -> None:
    sections = pending_sections(pending)
    unexpected = sections - {"bed_mesh default", "bed_mesh"}
    if unexpected:
        raise CalibrationError(
            "unexpected pending config after mesh scan: "
            + ", ".join(sorted(unexpected))
        )


def reject_mesh_data_in_canonical(data: Mapping[str, Any]) -> None:
    forbidden = {"mesh_matrix", "probed_matrix", "mesh_points", "bed_mesh"}
    present = forbidden.intersection(data)
    if present:
        raise CalibrationError(
            "measured mesh data must remain runtime-only; found "
            + ", ".join(sorted(present))
        )


def _set_scalar_at_path(text: str, path: Sequence[str], value: str) -> str:
    lines = text.splitlines(keepends=True)
    stack: list[tuple[int, str]] = []
    target = tuple(path)
    found = False
    for index, line in enumerate(lines):
        match = re.match(r"^(?P<indent>\s*)(?P<key>[^#:\n]+):(?P<rest>.*)$", line)
        if not match or not match.group("key").strip():
            continue
        indent = len(match.group("indent"))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key = match.group("key").strip()
        current = tuple(item[1] for item in stack) + (key,)
        if current == target:
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f"{match.group('indent')}{key}: {value}{newline}"
            found = True
            break
        stack.append((indent, key))
    if not found:
        raise CalibrationError(
            "cannot update missing calibration field " + ".".join(path)
        )
    return "".join(lines)


def _set_block_scalar_at_path(text: str, path: Sequence[str], value: str) -> str:
    lines = text.splitlines(keepends=True)
    stack: list[tuple[int, str]] = []
    target = tuple(path)
    for index, line in enumerate(lines):
        match = re.match(r"^(?P<indent>\s*)(?P<key>[^#:\n]+):(?P<rest>.*)$", line)
        if not match:
            continue
        indent = len(match.group("indent"))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key = match.group("key").strip()
        current = tuple(item[1] for item in stack) + (key,)
        if current != target:
            stack.append((indent, key))
            continue
        if "|" not in match.group("rest"):
            raise CalibrationError("calibration table must use a YAML block scalar")
        end = index + 1
        while end < len(lines):
            continuation = lines[end]
            if (
                continuation.strip()
                and len(continuation) - len(continuation.lstrip()) <= indent
            ):
                break
            end += 1
        rendered = value.strip()
        replacement = [f"{match.group('indent')}{key}: |\n"]
        replacement.extend(
            f"{' ' * (indent + 4)}{part.strip()}\n" for part in rendered.splitlines()
        )
        lines[index:end] = replacement
        return "".join(lines)
    raise CalibrationError("cannot update missing calibration table " + ".".join(path))


def atomic_update_calibration(path: Path, updates: Mapping[Sequence[str], Any]) -> None:
    """Update only known scalar/table fields while preserving comments."""

    original = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(original)
    if not isinstance(parsed, Mapping):
        raise CalibrationError("calib.yaml must contain a mapping")
    reject_mesh_data_in_canonical(parsed)
    updated = original
    for path_parts, value in updates.items():
        path_parts = tuple(path_parts)
        if path_parts[-1] == "calibrate":
            updated = _set_block_scalar_at_path(updated, path_parts, str(value))
        else:
            if value is None:
                rendered = "null"
            elif isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, int):
                rendered = str(value)
            else:
                rendered = f"{float(value):.3f}"
            updated = _set_scalar_at_path(updated, path_parts, rendered)
    updated_data = yaml.safe_load(updated)
    if not isinstance(updated_data, Mapping):
        raise CalibrationError("updated calib.yaml is not a mapping")
    reject_mesh_data_in_canonical(updated_data)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        shutil.copystat(path, temp_name)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


class MoonrakerClient:
    """Small Moonraker-over-SSH client with injectable transport for tests."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        *,
        request_fn: (
            Callable[[str, Mapping[str, Any] | None, float], dict[str, Any]] | None
        ) = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.host = host
        self.request_fn = request_fn
        self.runner = runner

    def request(
        self,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        if self.request_fn is not None:
            return self.request_fn(path, payload, timeout)
        query = ""
        if payload is not None and path.startswith("/printer/objects/query"):
            query = "?" + urlencode(payload)
        request_script = f"""
import json
import urllib.request
url = {('http://127.0.0.1:7125' + path + query)!r}
payload = {dict(payload or {})!r}
if payload and not url.endswith("query") and "?" not in url:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={{"Content-Type": "application/json"}})
else:
    request = urllib.request.Request(url)
with urllib.request.urlopen(request, timeout={float(timeout)!r}) as response:
    print(response.read().decode())
"""
        result = self.runner(
            ["ssh", self.host, "python3", "-"],
            input=request_script,
            text=True,
            capture_output=True,
            check=True,
            timeout=timeout + 10.0,
        )
        body = json.loads(result.stdout)
        return body.get("result", body)

    def status(self, objects: Iterable[str] | None = None) -> dict[str, Any]:
        object_names = list(objects or ["webhooks", "configfile"])
        query = "&".join(f"{name}=" for name in object_names)
        result = self.request(f"/printer/objects/query?{query}")
        if "result" in result and isinstance(result["result"], Mapping):
            result = result["result"]
        return result.get("status", result)

    def gcode(self, script: str, *, timeout: float = 60.0) -> dict[str, Any]:
        return self.request(
            "/printer/gcode/script", {"script": script}, timeout=timeout
        )

    def restart(self, *, timeout: float = 30.0) -> dict[str, Any]:
        return self.request(
            "/machine/services/restart", {"service": "klipper"}, timeout=timeout
        )

    def emergency_stop(self) -> dict[str, Any]:
        return self.gcode("M112", timeout=10.0)


class ArtifactStore:
    def __init__(self, root: Path, run_id: str, *, enabled: bool = True) -> None:
        self.path = root / run_id
        self.enabled = enabled
        if enabled:
            self.path.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, value: Any) -> None:
        if not self.enabled:
            return
        destination = self.path / name
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)

    def copy(self, source: Path, name: str) -> None:
        if self.enabled:
            shutil.copy2(source, self.path / name)


def _config_hashes() -> dict[str, str]:
    return {
        "calib.yaml": sha256_file(CALIB_PATH),
        "printer.cfg.template": sha256_file(TEMPLATE_PATH),
        "printer.cfg": sha256_file(CONFIG_PATH),
    }


def _load_raw_calibration() -> dict[str, Any]:
    value = yaml.safe_load(CALIB_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CalibrationError("calib.yaml must contain a mapping")
    reject_mesh_data_in_canonical(value)
    return value


def _run_local(
    command: Sequence[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=REPO_ROOT, text=True, capture_output=True, check=check
    )


class Iteration1Runner:
    def __init__(
        self,
        *,
        client: MoonrakerClient,
        store: ArtifactStore,
        bootstrap_threshold: int,
        dry_run: bool = False,
        assume_yes: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        snapshot: bool = True,
    ) -> None:
        self.client = client
        self.store = store
        self.bootstrap_threshold = int(bootstrap_threshold)
        self.dry_run = dry_run
        self.assume_yes = assume_yes
        self.sleep = sleep
        self.tap_threshold = self.bootstrap_threshold
        self.state = RunState(run_id=store.path.name, phase=Phase.PREFLIGHT.value)
        self.raw_calibration = _load_raw_calibration()
        if snapshot:
            self.store.copy(CALIB_PATH, "calib.yaml.before")
            self.store.copy(CONFIG_PATH, "printer.cfg.before")

    def checkpoint(
        self, phase: Phase, *, committed: bool = False, **evidence: Any
    ) -> None:
        self.state.phase = phase.value
        if committed:
            self.state.committed_phase = phase.value
        self.state.source_hashes = _config_hashes()
        self.state.evidence = {**(self.state.evidence or {}), **evidence}
        self.store.write_json("state.json", asdict(self.state))

    def confirm(self) -> None:
        if self.dry_run or self.assume_yes:
            return
        print(
            f"This moves and probes the printer through IDEX Z Iteration 1. "
            f"Type {ARMING_PHRASE!r} to continue: ",
            end="",
            flush=True,
        )
        if input().strip() != ARMING_PHRASE:
            raise CalibrationError("arming confirmation did not match")

    def preflight(self, *, checkpoint_state: bool = True) -> dict[str, Any]:
        if not CONFIG_PATH.exists():
            raise CalibrationError("generated printer.cfg is missing")
        _run_local([sys.executable, str(GENERATOR_PATH), "--check"])
        expected_delta = validate_vision_relative_provenance(self.raw_calibration)
        tools = self.raw_calibration.get("tools", {})
        t0 = tools.get("t0", {})
        t1 = tools.get("t1", {})
        assert_relative_alignment(
            float(t0["z_endstop"]),
            float(t1["z_endstop"]),
            float(t0["z_endstop"]),
            float(t1["z_endstop"]),
            expected_delta=expected_delta,
            tolerance=float(
                self.raw_calibration["vision_relative_alignment"]["tolerance_mm"]
            ),
        )
        status = self.client.status(
            [
                "webhooks",
                "print_stats",
                "virtual_sdcard",
                "configfile",
                "toolhead",
                "gcode_move",
                "heater_bed",
                "extruder",
                "extruder1",
                "temperature_probe btt_eddy",
            ]
        )
        self._validate_status_preflight(status)
        if checkpoint_state:
            self.checkpoint(Phase.PREFLIGHT, committed=True, status=status)
        return status

    def _validate_status_preflight(self, status: Mapping[str, Any]) -> None:
        webhooks = status.get("webhooks", {})
        if webhooks.get("state") != "ready":
            raise CalibrationError(f"Klippy is not ready: {webhooks!r}")
        print_state = status.get("print_stats", {}).get("state")
        if print_state not in {None, "standby", "complete", "cancelled", "error"}:
            raise CalibrationError(
                f"printer is not idle: print_stats.state={print_state!r}"
            )
        if status.get("virtual_sdcard", {}).get("is_active", False):
            raise CalibrationError("virtual SD print is active")
        configfile = status.get("configfile", {})
        if configfile.get("save_config_pending") not in {None, False}:
            raise CalibrationError("a SAVE_CONFIG change is already pending")
        pending = configfile.get("save_config_pending_items", {})
        if pending:
            raise CalibrationError(
                "pending configuration items must be empty before calibration"
            )
        for name in ("heater_bed", "extruder", "extruder1"):
            temperature = status.get(name, {}).get("temperature")
            if temperature is not None and float(temperature) > (
                40.0 if name == "heater_bed" else 50.0
            ):
                raise CalibrationError(
                    f"{name} is too hot for the cold baseline: {temperature}"
                )
        eddy_temperature = status.get("temperature_probe btt_eddy", {}).get(
            "temperature"
        )
        if eddy_temperature is not None and not math.isfinite(float(eddy_temperature)):
            raise CalibrationError("Eddy temperature is not finite")
        homing_origin = status.get("gcode_move", {}).get("homing_origin", [0, 0, 0])
        if any(abs(float(value)) > 1e-6 for value in homing_origin[:3]):
            raise CalibrationError(
                f"visible G-code offset is not zero: {homing_origin}"
            )

    def _gcode(self, script: str, *, timeout: float = 60.0) -> dict[str, Any]:
        if self.dry_run:
            self.store.write_json(
                "dry_run_command.json",
                {"script": script, "timeout": timeout},
            )
            return {}
        try:
            result = self.client.gcode(script, timeout=timeout)
        except Exception as exc:
            try:
                self.client.emergency_stop()
            except Exception:
                pass
            raise CalibrationError(
                f"G-code failed; emergency stop sent: {exc}"
            ) from exc
        self.store.write_json(
            f"command-{int(time.time() * 1000)}.json",
            {"script": script, "result": result},
        )
        return result

    def _home_clean_frame(self) -> None:
        self._gcode(
            "M140 S0\nM104 T0 S0\nM104 T1 S0\n"
            "BED_MESH_CLEAR\nSET_GCODE_OFFSET X=0 Y=0 Z=0 MOVE=0\n"
            "G28\nT0"
        )

    def collect_taps(
        self,
        *,
        x: float,
        y: float,
        count: int,
        max_attempts: int,
        tap_threshold: int,
    ) -> tuple[TapSummary, list[dict[str, Any]]]:
        samples: list[float] = []
        attempts: list[dict[str, Any]] = []
        for attempt in range(max_attempts):
            if len(samples) >= count:
                break
            try:
                self._gcode(
                    f"G90\nG1 X{x:.3f} Y{y:.3f} Z5 F1200\n"
                    f"PROBE METHOD=tap TAP_THRESHOLD={tap_threshold}"
                )
                if self.dry_run:
                    value = 0.0
                else:
                    status = self.client.status(["toolhead"])
                    value = float(status["toolhead"]["position"][2])
                samples.append(value)
                attempts.append({"attempt": attempt + 1, "ok": True, "z": value})
            except Exception as exc:
                attempts.append(
                    {"attempt": attempt + 1, "ok": False, "error": str(exc)}
                )
                if not self.dry_run and attempt + 1 >= max_attempts:
                    break
        summary = summarize_taps(samples, attempts=len(attempts))
        return summary, attempts

    def bootstrap_tap(self) -> TapSummary:
        self._home_clean_frame()
        summary, attempts = self.collect_taps(
            x=REFERENCE_X,
            y=REFERENCE_Y,
            count=TAP_SUCCESS_COUNT,
            max_attempts=TAP_MAX_ATTEMPTS,
            tap_threshold=self.bootstrap_threshold,
        )
        require_tap_acceptance(summary)
        self.checkpoint(
            Phase.BOOTSTRAP_TAP,
            committed=True,
            bootstrap_taps=attempts,
            bootstrap_summary=asdict(summary),
        )
        return summary

    def update_endstops(self, tap_center_z: float) -> tuple[float, float]:
        tools = self.raw_calibration["tools"]
        t0_old = float(tools["t0"]["z_endstop"])
        t1_old = float(tools["t1"]["z_endstop"])
        expected = validate_vision_relative_provenance(self.raw_calibration)
        t0_new, t1_new, delta = common_endstop_update(t0_old, t1_old, tap_center_z)
        assert_relative_alignment(
            t0_old, t1_old, t0_new, t1_new, expected_delta=expected, tolerance=1e-9
        )
        if self.dry_run:
            self.checkpoint(
                Phase.ENDSTOPS,
                committed=False,
                proposed_endstops={"t0": t0_new, "t1": t1_new, "delta": delta},
            )
            return t0_new, t1_new
        atomic_update_calibration(
            CALIB_PATH,
            {
                ("tools", "t0", "z_endstop"): t0_new,
                ("tools", "t1", "z_endstop"): t1_new,
            },
        )
        _run_local([sys.executable, str(GENERATOR_PATH)])
        _run_local([str(DEPLOY_PATH)])
        _run_local([str(DEPLOY_PATH), "--check"])
        self.client.restart()
        self.checkpoint(
            Phase.ENDSTOPS,
            committed=True,
            endstops={"t0": t0_new, "t1": t1_new, "delta": delta},
        )
        return t0_new, t1_new

    def verify_center(self, phase: Phase = Phase.CENTER_VERIFY) -> TapSummary:
        self._home_clean_frame()
        summary, attempts = self.collect_taps(
            x=REFERENCE_X,
            y=REFERENCE_Y,
            count=5,
            max_attempts=5,
            tap_threshold=self.bootstrap_threshold,
        )
        if (
            abs(summary.mean) > CENTER_MEAN_TOLERANCE
            or summary.span > CENTER_SPAN_TOLERANCE
        ):
            raise CalibrationError(
                f"center tap is not native Z=0: mean={summary.mean:.6f}, span={summary.span:.6f}"
            )
        if summary.rejected_attempts:
            raise CalibrationError("center verification rejected a tap")
        self.checkpoint(
            phase,
            committed=True,
            center_verification=attempts,
            center_summary=asdict(summary),
        )
        return summary

    def capture_pending(self, section: str, option: str) -> Any:
        status = self.client.status(["configfile"])
        pending = status.get("configfile", {}).get("save_config_pending_items", {})
        try:
            return extract_pending_value(pending, section, option)
        except KeyError as exc:
            raise CalibrationError(str(exc)) from exc

    def deploy_value(
        self, updates: Mapping[Sequence[str], Any], phase: Phase, **evidence: Any
    ) -> None:
        if self.dry_run:
            self.checkpoint(phase, committed=False, **evidence)
            return
        atomic_update_calibration(CALIB_PATH, updates)
        _run_local([sys.executable, str(GENERATOR_PATH)])
        _run_local([str(DEPLOY_PATH)])
        _run_local([str(DEPLOY_PATH), "--check"])
        self.client.restart()
        self.checkpoint(phase, committed=True, **evidence)

    def calibrate_drive_current(self) -> None:
        self._home_clean_frame()
        eddy = self.raw_calibration["eddy_relative_calibration"]["nozzle_to_coil"]
        coil_pose = coil_over_target_pose(
            Pose(REFERENCE_X, REFERENCE_Y, 20.0), Pose(**eddy)
        )
        self._gcode(
            f"G1 X{coil_pose.x:.3f} Y{coil_pose.y:.3f} Z{coil_pose.z:.3f} F1200"
        )
        self._gcode("LDC_CALIBRATE_DRIVE_CURRENT CHIP=btt_eddy", timeout=120.0)
        if self.dry_run:
            self.checkpoint(
                Phase.DRIVE_CURRENT, committed=False, coil_pose=asdict(coil_pose)
            )
            return
        current = int(
            self.capture_pending("probe_eddy_current btt_eddy", "reg_drive_current")
        )
        if not 0 <= current <= 31:
            raise CalibrationError(
                f"proposed Eddy drive current is outside 0..31: {current}"
            )
        self.deploy_value(
            {("eddy_relative_calibration", "klipper", "reg_drive_current"): current},
            Phase.DRIVE_CURRENT,
            drive_current=current,
            coil_pose=asdict(coil_pose),
        )

    def calibrate_eddy_curve(self) -> None:
        self._home_clean_frame()
        self._gcode(f"G1 X{REFERENCE_X:.3f} Y{REFERENCE_Y:.3f} Z5 F1200")
        self._gcode("PROBE_EDDY_CURRENT_CALIBRATE CHIP=btt_eddy", timeout=300.0)
        if self.dry_run:
            self.checkpoint(Phase.EDDY_CALIBRATION, committed=False)
            return
        status = self.client.status(["manual_probe"])
        manual_probe = status.get("manual_probe", {})
        if not manual_probe.get("is_active"):
            raise CalibrationError("Eddy calibration did not enter manual-probe mode")
        current_z = float(manual_probe["z_position"])
        delta = -current_z
        if current_z + delta < -0.01:
            raise CalibrationError(
                "manual-probe targeting would descend below native contact"
            )
        self._gcode(f"TESTZ Z={delta:.6f}")
        status = self.client.status(["manual_probe"])
        final_z = float(status.get("manual_probe", {}).get("z_position", math.nan))
        if not math.isfinite(final_z) or abs(final_z) > 0.004:
            raise CalibrationError(
                f"manual-probe target did not reach Z=0: {final_z!r}"
            )
        self._gcode("ACCEPT")
        curve = str(self.capture_pending("probe_eddy_current btt_eddy", "calibrate"))
        pairs = [part.strip() for part in curve.split(",") if part.strip()]
        if len(pairs) < 9:
            raise CalibrationError("Eddy calibration returned fewer than nine pairs")
        for pair in pairs:
            height, frequency = pair.split(":", 1)
            if not math.isfinite(float(height)) or not math.isfinite(float(frequency)):
                raise CalibrationError("Eddy calibration contains a non-finite pair")
        self.deploy_value(
            {("eddy_relative_calibration", "klipper", "calibrate"): curve},
            Phase.EDDY_CALIBRATION,
            eddy_calibration=curve,
        )

    def calibrate_tap_threshold(self) -> None:
        self._home_clean_frame()
        for mode in ("guess", "refine", "verify"):
            self._gcode(
                f"G1 X{REFERENCE_X:.3f} Y{REFERENCE_Y:.3f} Z5 F1200\n"
                f"PROBE_EDDY_CURRENT_TAP_CALIBRATE TAP={mode}",
                timeout=180.0,
            )
        if self.dry_run:
            self.checkpoint(Phase.TAP_THRESHOLD, committed=False, tap_z_offset=0.0)
            return
        threshold = int(
            self.capture_pending("probe_eddy_current btt_eddy", "tap_threshold")
        )
        if threshold <= 0:
            raise CalibrationError(f"invalid proposed tap threshold: {threshold}")
        self.deploy_value(
            {
                ("eddy_relative_calibration", "klipper", "tap_threshold"): threshold,
                ("eddy_relative_calibration", "klipper", "tap_z_offset"): 0.0,
            },
            Phase.TAP_THRESHOLD,
            tap_threshold=threshold,
            tap_z_offset=0.0,
        )
        self.tap_threshold = threshold

    def verify_mesh_against_tap(self, mesh_status: Mapping[str, Any]) -> dict[str, Any]:
        matrix = mesh_status.get("mesh_matrix") or mesh_status.get("probed_matrix")
        if not matrix:
            raise CalibrationError(
                "active mesh did not expose a matrix for verification"
            )
        mesh_min_values = mesh_status.get("mesh_min", [0.0, 20.0])
        mesh_max_values = mesh_status.get("mesh_max", [190.0, 275.0])
        if isinstance(mesh_min_values, Mapping):
            mesh_min_values = [mesh_min_values["x"], mesh_min_values["y"]]
        if isinstance(mesh_max_values, Mapping):
            mesh_max_values = [mesh_max_values["x"], mesh_max_values["y"]]
        mesh_min = MeshPoint(float(mesh_min_values[0]), float(mesh_min_values[1]))
        mesh_max = MeshPoint(float(mesh_max_values[0]), float(mesh_max_values[1]))
        eddy = self.raw_calibration["eddy_relative_calibration"]["nozzle_to_coil"]
        grid = derive_safe_tap_grid(
            nozzle_x=AxisBounds(0.0, 255.0),
            nozzle_y=AxisBounds(-15.0, 296.0),
            mesh_x=AxisBounds(mesh_min.x, mesh_max.x),
            mesh_y=AxisBounds(mesh_min.y, mesh_max.y),
            coil_offset_x=float(eddy["x"]),
            coil_offset_y=float(eddy["y"]),
        )
        tap_samples: dict[MeshPoint, tuple[float, ...]] = {}
        corrections: dict[MeshPoint, float] = {}
        for point in grid:
            summary, attempts = self.collect_taps(
                x=point.x,
                y=point.y,
                count=3,
                max_attempts=3,
                tap_threshold=self.tap_threshold,
            )
            if summary.rejected_attempts:
                raise CalibrationError(
                    f"final mesh tap rejected at {point}: {attempts}"
                )
            tap_samples[point] = summary.successful
            corrections[point] = mesh_correction_at(
                matrix,
                mesh_min=mesh_min,
                mesh_max=mesh_max,
                point=point,
            )
        return mesh_tap_acceptance(tap_samples, corrections)

    def final_mesh(self) -> None:
        self._home_clean_frame()
        if not self.dry_run:
            before = self.client.status(["configfile"])
            pending = before.get("configfile", {}).get("save_config_pending_items", {})
            if pending:
                raise CalibrationError("pending configuration exists before mesh scan")
        self._gcode(
            "BED_MESH_CALIBRATE METHOD=scan PROFILE=default HORIZONTAL_MOVE_Z=2",
            timeout=900.0,
        )
        self._gcode(
            "BED_MESH_CALIBRATE METHOD=scan PROFILE=default HORIZONTAL_MOVE_Z=1",
            timeout=900.0,
        )
        status = (
            self.client.status(["bed_mesh", "configfile"]) if not self.dry_run else {}
        )
        if not self.dry_run:
            require_only_transient_mesh_pending(
                status.get("configfile", {}).get("save_config_pending_items", {})
            )
            mesh = status.get("bed_mesh", {})
            if not mesh.get("profile_name") and not mesh.get("mesh_matrix"):
                raise CalibrationError(
                    "mesh scan did not leave an active in-memory mesh"
                )
            verification = self.verify_mesh_against_tap(mesh)
        if self.dry_run:
            self.checkpoint(Phase.MESH_SCAN, committed=False)
        else:
            self.checkpoint(Phase.MESH_SCAN, committed=True, mesh_status=status)
            self.checkpoint(
                Phase.MESH_VERIFY, committed=True, mesh_verification=verification
            )

    def resume(self) -> RunState:
        """Continue only from the last committed phase boundary."""

        committed = self.state.committed_phase
        if committed is None:
            raise CalibrationError("run has no committed phase boundary")
        self.confirm()
        self.preflight(checkpoint_state=False)
        phase = Phase(committed)
        phases = list(Phase)
        index = phases.index(phase)
        if index <= phases.index(Phase.PREFLIGHT):
            self.bootstrap_tap()
            index = phases.index(Phase.BOOTSTRAP_TAP)
        elif index == phases.index(Phase.BOOTSTRAP_TAP):
            summary_data = (self.state.evidence or {}).get("bootstrap_summary")
            if not summary_data:
                raise CalibrationError("resume state lacks bootstrap tap summary")
            self.update_endstops(float(summary_data["median"]))
        if index <= phases.index(Phase.ENDSTOPS):
            self.verify_center()
        if index <= phases.index(Phase.CENTER_VERIFY):
            self.calibrate_drive_current()
        if index <= phases.index(Phase.DRIVE_CURRENT):
            self.calibrate_eddy_curve()
        if index <= phases.index(Phase.EDDY_CALIBRATION):
            self.calibrate_tap_threshold()
        if index <= phases.index(Phase.TAP_THRESHOLD):
            self.verify_center(Phase.REANCHOR)
        if index <= phases.index(Phase.REANCHOR):
            self.final_mesh()
        elif phase is Phase.MESH_SCAN:
            status = self.client.status(["bed_mesh", "configfile"])
            verification = self.verify_mesh_against_tap(status.get("bed_mesh", {}))
            self.checkpoint(
                Phase.MESH_VERIFY, committed=True, mesh_verification=verification
            )
        self.checkpoint(Phase.FINISH, committed=True, note="Iteration 1 complete")
        self.write_final_report()
        return self.state

    def write_final_report(self) -> None:
        self.store.write_json("final-report.json", asdict(self.state))
        if self.store.enabled:
            report = self.store.path / "final-report.md"
            report.write_text(
                "# IDEX Z Iteration 1 report\n\n"
                f"- Run: `{self.state.run_id}`\n"
                f"- Final committed phase: `{self.state.committed_phase}`\n"
                "- Mesh validation scope: tap-safe region\n"
                "- Measured mesh data: runtime-only; not written to canonical configuration\n",
                encoding="utf-8",
            )

    def run(self) -> RunState:
        self.confirm()
        self.preflight()
        if self.dry_run:
            eddy = self.raw_calibration["eddy_relative_calibration"]["nozzle_to_coil"]
            coil_pose = coil_over_target_pose(
                Pose(REFERENCE_X, REFERENCE_Y, 20.0), Pose(**eddy)
            )
            self.checkpoint(
                Phase.FINISH, committed=True, dry_run=True, coil_pose=asdict(coil_pose)
            )
            return self.state
        summary = self.bootstrap_tap()
        self.update_endstops(summary.median)
        self.verify_center()
        self.calibrate_drive_current()
        self.calibrate_eddy_curve()
        self.calibrate_tap_threshold()
        self.verify_center(Phase.REANCHOR)
        self.final_mesh()
        self.checkpoint(Phase.FINISH, committed=True, note="Iteration 1 complete")
        self.write_final_report()
        return self.state


def rollback(run_directory: Path, *, host: str, assume_yes: bool) -> None:
    if not assume_yes:
        raise CalibrationError(
            "rollback requires --yes because it deploys a prior configuration"
        )
    calib_backup = run_directory / "calib.yaml.before"
    config_backup = run_directory / "printer.cfg.before"
    if not calib_backup.exists() or not config_backup.exists():
        raise CalibrationError(
            f"run directory lacks rollback snapshots: {run_directory}"
        )
    shutil.copy2(calib_backup, CALIB_PATH)
    shutil.copy2(config_backup, CONFIG_PATH)
    _run_local([sys.executable, str(GENERATOR_PATH), "--check"])
    _run_local([str(DEPLOY_PATH)])
    _run_local([str(DEPLOY_PATH), "--check"])
    MoonrakerClient(host).restart()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument(
        "--bootstrap-tap-threshold", type=int, default=DEFAULT_TAP_THRESHOLD
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--rollback", type=Path)
    parser.add_argument("--yes", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.rollback:
            rollback(args.rollback, host=args.host, assume_yes=args.yes)
            return 0
        if args.resume:
            state_path = args.resume / "state.json"
            if not state_path.exists():
                raise CalibrationError(f"resume state is missing: {state_path}")
            state_data = json.loads(state_path.read_text(encoding="utf-8"))
            saved_hashes = state_data.get("source_hashes") or {}
            if saved_hashes and saved_hashes != _config_hashes():
                raise CalibrationError(
                    "source hashes changed since the last committed phase"
                )
            store = ArtifactStore(args.resume.parent, args.resume.name, enabled=True)
            runner = Iteration1Runner(
                client=MoonrakerClient(args.host),
                store=store,
                bootstrap_threshold=args.bootstrap_tap_threshold,
                dry_run=False,
                assume_yes=args.yes,
                snapshot=False,
            )
            runner.state = RunState(
                run_id=state_data["run_id"],
                phase=state_data["phase"],
                committed_phase=state_data.get("committed_phase"),
                source_hashes=state_data.get("source_hashes"),
                evidence=state_data.get("evidence"),
            )
            state = runner.resume()
            print(json.dumps(asdict(state), indent=2, sort_keys=True, default=str))
            return 0
        run_id = utc_run_id()
        store = ArtifactStore(RUN_ROOT, run_id, enabled=not args.dry_run)
        runner = Iteration1Runner(
            client=MoonrakerClient(args.host),
            store=store,
            bootstrap_threshold=args.bootstrap_tap_threshold,
            dry_run=args.dry_run,
            assume_yes=args.yes,
        )
        state = runner.run()
        print(json.dumps(asdict(state), indent=2, sort_keys=True, default=str))
        return 0
    except (CalibrationError, subprocess.CalledProcessError, OSError) as exc:
        print(f"Iteration 1 aborted: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
