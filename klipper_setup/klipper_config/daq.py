#!/usr/bin/env python3
"""Generic host CLI for persistent printer DAQ jobs."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import eddy_daq


_logger = logging.getLogger(__name__)
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_HOST = os.environ.get("MENDERPI_HOST", "pi@menderpi.local")
DEFAULT_DB_PATH = "/home/pi/printer_data/database/daq.sqlite"
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


def _job_id(value: str) -> str:
    if not JOB_ID_RE.fullmatch(value):
        raise ValueError("job id contains unsupported characters")
    return value


def _default_job_id() -> str:
    return "daq_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_heights(value: str) -> tuple[float, ...]:
    try:
        heights = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("heights must be comma-separated numbers") from exc
    if not heights:
        raise argparse.ArgumentTypeError("heights cannot be empty")
    return heights


def _remote_python(host: str, source: str, *, env: dict[str, str] | None = None) -> str:
    remote_command = ["env"]
    for key, value in (env or {}).items():
        remote_command.append("%s=%s" % (key, value))
    remote_command.extend(["/opt/klipper-env/bin/python3", "-"])
    command = ["ssh", host, shlex.join(remote_command)]
    completed = subprocess.run(
        command,
        input=source,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            "remote DAQ command failed: %s" % (completed.stderr.strip() or completed.stdout.strip())
        )
    return completed.stdout


def _remote_json(host: str, source: str, *, env: dict[str, str] | None = None) -> Any:
    output = _remote_python(host, source, env=env)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("remote DAQ command returned invalid JSON: %s" % output) from exc


def _moonraker(host: str, method: str, path: str, payload: dict | None = None) -> dict:
    source = """\
import json
import os
import urllib.request

method = os.environ["DAQ_HTTP_METHOD"]
path = os.environ["DAQ_HTTP_PATH"]
payload = json.loads(os.environ.get("DAQ_HTTP_PAYLOAD", "null"))
data = None if payload is None else json.dumps(payload).encode("utf-8")
request = urllib.request.Request(
    "http://127.0.0.1:7125" + path, data=data, method=method,
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=15) as response:
    print(response.read().decode("utf-8"))
"""
    return _remote_json(
        host,
        source,
        env={
            "DAQ_HTTP_METHOD": method,
            "DAQ_HTTP_PATH": path,
            "DAQ_HTTP_PAYLOAD": json.dumps(payload),
        },
    )


def _remote_jobs(host: str, database_path: str, job_id: str | None = None) -> Any:
    source = """\
import json
import os
from sqlitedict import SqliteDict

database_path = os.environ["DAQ_DATABASE_PATH"]
job_id = os.environ.get("DAQ_JOB_ID")
db = SqliteDict(database_path, autocommit=True)
try:
    if job_id:
        metadata = db[job_id]
        prefix = job_id + "_"
        records = [
            value for key, value in db.items()
            if key.startswith(prefix) and isinstance(value, dict)
            and value.get("record_kind") == "measurement"
        ]
        records.sort(key=lambda value: value["record_index"])
        print(json.dumps({"metadata": metadata, "records": records}, allow_nan=False))
    else:
        jobs = [
            value for value in db.values()
            if isinstance(value, dict) and value.get("record_kind") == "job"
        ]
        jobs.sort(key=lambda value: value.get("created_at", ""), reverse=True)
        print(json.dumps(jobs, allow_nan=False))
finally:
    db.close()
"""
    env = {"DAQ_DATABASE_PATH": database_path}
    if job_id:
        env["DAQ_JOB_ID"] = _job_id(job_id)
    return _remote_json(host, source, env=env)


def generate_eddy(args: argparse.Namespace) -> int:
    job_id = _job_id(args.job_id or _default_job_id())
    run_dir = args.run_dir.resolve() if args.run_dir else REPO_ROOT / "runs" / "daq" / job_id
    run_dir.mkdir(parents=True, exist_ok=False)
    config_path = args.config.resolve()
    calib_path = args.calib.resolve()
    config_text = config_path.read_text(encoding="utf-8")
    geometry = eddy_daq.derive_geometry(
        config_text,
        columns=args.grid_x,
        rows=args.grid_y,
        left_border_mm=args.left_border,
    )
    threshold = args.tap_threshold or eddy_daq.load_tap_threshold(calib_path)
    endstop_positions = eddy_daq.load_endstop_positions(calib_path)
    config_fingerprint = eddy_daq.fingerprint(config_path, calib_path)
    gcode = eddy_daq.render_gcode(
        job_id=job_id,
        geometry=geometry,
        tap_threshold=threshold,
        tap_count=args.tap_count,
        heights=args.heights,
        sample_duration=args.duration,
        safe_z=args.safe_z,
        xy_speed=args.xy_speed,
        z_speed=args.z_speed,
        config_fingerprint=config_fingerprint,
        endstop_positions=endstop_positions,
    )
    manifest = eddy_daq.manifest(
        job_id=job_id,
        geometry=geometry,
        tap_threshold=threshold,
        tap_count=args.tap_count,
        heights=args.heights,
        sample_duration=args.duration,
        safe_z=args.safe_z,
        xy_speed=args.xy_speed,
        z_speed=args.z_speed,
        config_fingerprint=config_fingerprint,
        endstop_positions=endstop_positions,
    )
    (run_dir / "eddy_grid.gcode").write_text(gcode, encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _logger.info(
        "generated Eddy DAQ job: job_id=%s grid=%dx%d area=X%.3f..%.3f Y%.3f..%.3f records=%d run_dir=%s",
        job_id,
        geometry.columns,
        geometry.rows,
        geometry.x.minimum,
        geometry.x.maximum,
        geometry.y.minimum,
        geometry.y.maximum,
        manifest["expected_records"],
        run_dir,
    )
    return 0


def download_job(host: str, database_path: str, job_id: str, output_dir: Path) -> tuple[Path, Path]:
    payload = _remote_jobs(host, database_path, job_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = output_dir / (job_id + ".json")
    records_path = output_dir / (job_id + ".jsonl")
    metadata_path.write_text(
        json.dumps(payload["metadata"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with records_path.open("w", encoding="utf-8") as stream:
        for record in payload["records"]:
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
    _logger.info(
        "downloaded DAQ job: job_id=%s records=%d metadata=%s records_jsonl=%s",
        job_id,
        len(payload["records"]),
        metadata_path,
        records_path,
    )
    return metadata_path, records_path


def run_job(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    job_id = _job_id(manifest["job_id"])
    gcode_path = run_dir / "eddy_grid.gcode"
    remote_directory = "printer_data/gcodes/daq"
    remote_filename = "daq/%s.gcode" % job_id
    _logger.info("uploading DAQ job: job_id=%s host=%s", job_id, args.host)
    subprocess.run(["ssh", args.host, "mkdir", "-p", remote_directory], check=True)
    subprocess.run(
        ["scp", str(gcode_path), "%s:%s/%s.gcode" % (args.host, remote_directory, job_id)],
        check=True,
    )
    status = _moonraker(args.host, "GET", "/printer/objects/query?webhooks&print_stats&virtual_sdcard")
    printer = status["result"]["status"]
    if printer["webhooks"].get("state") != "ready":
        raise RuntimeError("printer is not ready")
    if printer.get("virtual_sdcard", {}).get("is_active"):
        raise RuntimeError("printer already has an active virtual-SD job")
    _moonraker(args.host, "POST", "/printer/print/start", {"filename": remote_filename})
    _logger.info("DAQ print started: %s", remote_filename)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        status = _moonraker(args.host, "GET", "/printer/objects/query?print_stats&virtual_sdcard")
        printer = status["result"]["status"]
        print_state = printer.get("print_stats", {}).get("state")
        progress = printer.get("virtual_sdcard", {}).get("progress", 0.0)
        _logger.info("DAQ print progress: state=%s progress=%.1f%%", print_state, progress * 100.0)
        if print_state == "complete":
            break
        if print_state in {"error", "cancelled"}:
            raise RuntimeError("DAQ print ended with state=%s" % print_state)
        time.sleep(args.poll_interval)
    else:
        raise RuntimeError("DAQ print exceeded timeout of %.0f seconds" % args.timeout)
    download_job(args.host, args.database_path, job_id, run_dir)
    return 0


def list_jobs(args: argparse.Namespace) -> int:
    jobs = _remote_jobs(args.host, args.database_path)
    for job in jobs:
        print(
            "%s type=%s status=%s created=%s records=%s/%s errors=%s"
            % (
                job.get("job_id"),
                job.get("job_type"),
                job.get("status"),
                job.get("created_at"),
                job.get("record_count"),
                job.get("expected_records", "?"),
                job.get("error_count"),
            )
        )
    return 0


def download_command(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve() if args.output_dir else REPO_ROOT / "runs" / "daq" / args.job_id
    download_job(args.host, args.database_path, _job_id(args.job_id), output_dir)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate-eddy", help="Generate an Eddy grid DAQ G-code job.")
    generate.add_argument("--run-dir", type=Path)
    generate.add_argument("--job-id")
    generate.add_argument("--config", type=Path, default=SCRIPT_DIR / "printer.cfg")
    generate.add_argument("--calib", type=Path, default=SCRIPT_DIR / "calib.yaml")
    generate.add_argument("--grid-x", type=int, default=eddy_daq.DEFAULT_GRID_X)
    generate.add_argument("--grid-y", type=int, default=eddy_daq.DEFAULT_GRID_Y)
    generate.add_argument("--left-border", type=float, default=eddy_daq.DEFAULT_LEFT_BORDER_MM)
    generate.add_argument("--tap-count", type=int, default=1)
    generate.add_argument("--tap-threshold", type=float)
    generate.add_argument("--heights", type=_parse_heights, default=eddy_daq.DEFAULT_HEIGHTS)
    generate.add_argument("--duration", type=float, default=eddy_daq.DEFAULT_SAMPLE_DURATION)
    generate.add_argument("--safe-z", type=float, default=eddy_daq.DEFAULT_SAFE_Z)
    generate.add_argument("--xy-speed", type=float, default=eddy_daq.DEFAULT_XY_SPEED)
    generate.add_argument("--z-speed", type=float, default=eddy_daq.DEFAULT_Z_SPEED)
    generate.set_defaults(func=generate_eddy)
    run = subparsers.add_parser("run", help="Upload, print, poll, and download a generated DAQ job.")
    run.add_argument("--run-dir", type=Path, required=True)
    run.add_argument("--host", default=DEFAULT_HOST)
    run.add_argument("--database-path", default=DEFAULT_DB_PATH)
    run.add_argument("--timeout", type=float, default=7200.0)
    run.add_argument("--poll-interval", type=float, default=5.0)
    run.set_defaults(func=run_job)
    jobs = subparsers.add_parser("jobs", help="List persisted printer DAQ jobs.")
    jobs.add_argument("--host", default=DEFAULT_HOST)
    jobs.add_argument("--database-path", default=DEFAULT_DB_PATH)
    jobs.set_defaults(func=list_jobs)
    download = subparsers.add_parser("download", help="Download a DAQ job as metadata JSON and flat JSONL.")
    download.add_argument("--job-id", required=True)
    download.add_argument("--host", default=DEFAULT_HOST)
    download.add_argument("--database-path", default=DEFAULT_DB_PATH)
    download.add_argument("--output-dir", type=Path)
    download.set_defaults(func=download_command)
    return root


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        _logger.error("DAQ command failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
