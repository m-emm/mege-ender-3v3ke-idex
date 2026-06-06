#!/usr/bin/env python3
"""Run Klipper resonance tests and render shaper plots.

This script is intended to run on the Raspberry Pi. It talks to Moonraker on
localhost, asks Klipper to run TEST_RESONANCES when requested, then renders the
result with Klipper's calibrate_shaper.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_MOONRAKER_URL = "http://127.0.0.1:7125"
DEFAULT_OUTPUT_DIR = "~/printer_data/config/resonance"
DEFAULT_TMP_DIR = "/tmp"
DEFAULT_KLIPPER_PYTHON = "/opt/klipper-env/bin/python"
DEFAULT_CALIBRATE_SHAPER = "/opt/klipper/scripts/calibrate_shaper.py"
DEFAULT_PLOT_DPI = 300

CHIP_OBJECTS = {
    "left_toolhead": "adxl345 left_toolhead",
    "right_toolhead": "adxl345 right_toolhead",
}


class ResonanceError(RuntimeError):
    pass


def request_json(
    moonraker_url: str,
    path: str,
    *,
    method: str = "GET",
    data: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> dict:
    url = moonraker_url.rstrip("/") + path
    body = None
    headers = {}
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(errors="replace")
        raise ResonanceError(f"{method} {path} failed HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise ResonanceError(f"{method} {path} failed: {exc}") from exc


def ensure_klipper_ready(moonraker_url: str) -> None:
    payload = request_json(
        moonraker_url,
        "/printer/objects/query?webhooks",
        timeout=10,
    )
    status = payload.get("result", {}).get("status", {})
    webhooks = status.get("webhooks", {})
    state = webhooks.get("state")
    if state != "ready":
        message = webhooks.get("state_message") or "no state message"
        raise ResonanceError(f"Klipper is not ready: {state} ({message})")


def run_gcode(moonraker_url: str, script: str, timeout: float) -> None:
    request_json(
        moonraker_url,
        "/printer/gcode/script",
        method="POST",
        data={"script": script},
        timeout=timeout,
    )


def recent_gcode_store(moonraker_url: str, count: int = 20) -> str:
    try:
        payload = request_json(
            moonraker_url,
            f"/server/gcode_store?count={count}",
            timeout=10,
        )
    except ResonanceError as exc:
        return f"Unable to read gcode store: {exc}"

    lines = []
    for item in payload.get("result", {}).get("gcode_store", []):
        message = (item.get("message") or "").strip()
        if message:
            lines.append(f"{item.get('type')}: {message}")
    return "\n".join(lines)


def resonance_pattern(tmp_dir: Path, axis: str) -> str:
    return f"resonances_{axis.lower()}_*.csv"


def wait_for_new_resonance_csv(
    tmp_dir: Path,
    axis: str,
    known_files: set[Path],
    start_time: float,
    timeout: float,
    moonraker_url: str,
) -> Path:
    deadline = time.time() + timeout
    pattern = resonance_pattern(tmp_dir, axis)

    while time.time() < deadline:
        candidates = []
        for path in tmp_dir.glob(pattern):
            if path in known_files:
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            if stat.st_mtime >= start_time - 1:
                candidates.append((stat.st_mtime, path))

        if candidates:
            path = max(candidates, key=lambda item: item[0])[1]
            first_size = path.stat().st_size
            time.sleep(0.5)
            if path.exists() and path.stat().st_size == first_size:
                return path

        time.sleep(1)

    store = recent_gcode_store(moonraker_url)
    raise ResonanceError(
        f"No new {pattern} file appeared in {tmp_dir} within {timeout:.0f}s.\n"
        f"Recent gcode store:\n{store}"
    )


def infer_axis_from_csv(csv_path: Path) -> str:
    match = re.search(r"resonances_([a-z])_", csv_path.name, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return "CUSTOM"


def output_stem(csv_path: Path, axis: str) -> str:
    if csv_path.stem.startswith("resonances_"):
        return csv_path.stem
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"resonances_{axis.lower()}_{timestamp}"


def copy_if_different(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        if source.resolve() == destination.resolve():
            return
    except FileNotFoundError:
        pass
    shutil.copy2(source, destination)


def render_plot(
    *,
    csv_path: Path,
    axis: str,
    chip: str | None,
    output_dir: Path,
    klipper_python: Path,
    calibrate_shaper: Path,
    plot_dpi: int,
) -> dict[str, Path | str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = output_stem(csv_path, axis)
    raw_csv = output_dir / f"{stem}.csv"
    png = output_dir / f"{stem}.png"
    calibration_csv = output_dir / f"calibration_data_{axis.lower()}_{stem.removeprefix(f'resonances_{axis.lower()}_')}.csv"
    summary_txt = output_dir / f"{stem}.txt"

    copy_if_different(csv_path, raw_csv)

    command = [
        str(klipper_python),
        str(calibrate_shaper),
        str(raw_csv),
        "-o",
        str(png),
        "-c",
        str(calibration_csv),
    ]
    with tempfile.TemporaryDirectory(prefix="resonance_plot_") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        (tmp_dir / "matplotlibrc").write_text(
            "\n".join(
                [
                    "backend: Agg",
                    f"figure.dpi: {plot_dpi}",
                    f"savefig.dpi: {plot_dpi}",
                    "savefig.bbox: standard",
                ]
            )
            + "\n"
        )
        env = os.environ.copy()
        env["MPLCONFIGDIR"] = str(tmp_dir)
        env["MPLBACKEND"] = "Agg"
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=tmp_dir,
            env=env,
        )
    if result.returncode != 0:
        raise ResonanceError(
            "calibrate_shaper.py failed with exit code "
            f"{result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    summary = [
        f"axis: {axis}",
        f"chip: {chip or 'default'}",
        f"raw_csv: {raw_csv}",
        f"plot_png: {png}",
        f"plot_dpi: {plot_dpi}",
        f"calibration_csv: {calibration_csv}",
        "",
        "calibrate_shaper.py output:",
        result.stdout.strip(),
    ]
    if result.stderr.strip():
        summary.extend(["", "stderr:", result.stderr.strip()])
    summary_txt.write_text("\n".join(summary).rstrip() + "\n")

    latest_prefix = output_dir / f"latest_{axis.lower()}"
    copy_if_different(png, latest_prefix.with_suffix(".png"))
    copy_if_different(summary_txt, latest_prefix.with_suffix(".txt"))
    copy_if_different(raw_csv, output_dir / f"latest_{axis.lower()}_raw.csv")
    copy_if_different(
        calibration_csv,
        output_dir / f"latest_{axis.lower()}_calibration.csv",
    )

    return {
        "raw_csv": raw_csv,
        "plot_png": png,
        "calibration_csv": calibration_csv,
        "summary_txt": summary_txt,
        "latest_png": latest_prefix.with_suffix(".png"),
        "latest_txt": latest_prefix.with_suffix(".txt"),
        "calibration_output": result.stdout.strip(),
    }


def chip_object_name(chip: str) -> str:
    if chip in CHIP_OBJECTS:
        return CHIP_OBJECTS[chip]
    if chip.startswith("adxl345 "):
        return chip
    raise ResonanceError(
        f"Unknown chip '{chip}'. Expected one of: {', '.join(CHIP_OBJECTS)}"
    )


def build_test_gcode(axis: str, chip: str) -> str:
    chip_object = chip_object_name(chip)
    return f'TEST_RESONANCES AXIS={axis} CHIPS="{chip_object}"'


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Klipper resonance test and render the shaper plot."
    )
    parser.add_argument("--axis", choices=("X", "Y", "Z", "x", "y", "z"))
    parser.add_argument(
        "--chip",
        default="left_toolhead",
        choices=("left_toolhead", "right_toolhead"),
        help="Accelerometer chip to use for TEST_RESONANCES.",
    )
    parser.add_argument(
        "--render-only",
        metavar="CSV",
        help="Render an existing resonances CSV without running printer motion.",
    )
    parser.add_argument("--moonraker-url", default=os.environ.get("MOONRAKER_URL", DEFAULT_MOONRAKER_URL))
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--tmp-dir", default=DEFAULT_TMP_DIR)
    parser.add_argument("--klipper-python", default=DEFAULT_KLIPPER_PYTHON)
    parser.add_argument("--calibrate-shaper", default=DEFAULT_CALIBRATE_SHAPER)
    parser.add_argument(
        "--plot-dpi",
        type=int,
        default=DEFAULT_PLOT_DPI,
        help=f"PNG render DPI. Default: {DEFAULT_PLOT_DPI}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=900.0,
        help="Seconds to wait for the resonance gcode request.",
    )
    parser.add_argument(
        "--file-timeout",
        type=float,
        default=600.0,
        help="Seconds to wait for the resonance CSV to appear.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).expanduser()
    klipper_python = Path(args.klipper_python)
    calibrate_shaper = Path(args.calibrate_shaper)
    if args.plot_dpi < 72:
        raise ResonanceError("--plot-dpi must be at least 72")

    if args.render_only:
        csv_path = Path(args.render_only).expanduser()
        if not csv_path.is_file():
            raise ResonanceError(f"Render-only CSV does not exist: {csv_path}")
        axis = (args.axis.upper() if args.axis else infer_axis_from_csv(csv_path))
        chip = args.chip
    else:
        if not args.axis:
            raise ResonanceError("--axis is required unless --render-only is used")
        axis = args.axis.upper()
        chip = args.chip
        ensure_klipper_ready(args.moonraker_url)

        tmp_dir = Path(args.tmp_dir)
        known_files = set(tmp_dir.glob(resonance_pattern(tmp_dir, axis)))
        gcode = build_test_gcode(axis, chip)
        start_time = time.time()

        print(f"Running: {gcode}")
        run_gcode(args.moonraker_url, gcode, timeout=args.timeout)
        csv_path = wait_for_new_resonance_csv(
            tmp_dir,
            axis,
            known_files,
            start_time,
            args.file_timeout,
            args.moonraker_url,
        )
        print(f"Found resonance CSV: {csv_path}")

    outputs = render_plot(
        csv_path=csv_path,
        axis=axis,
        chip=chip,
        output_dir=output_dir,
        klipper_python=klipper_python,
        calibrate_shaper=calibrate_shaper,
        plot_dpi=args.plot_dpi,
    )

    print(outputs["calibration_output"])
    print("")
    print(f"Plot: {outputs['plot_png']}")
    print(f"Summary: {outputs['summary_txt']}")
    print(f"Latest plot: {outputs['latest_png']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ResonanceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
