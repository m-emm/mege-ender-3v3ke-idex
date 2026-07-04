#!/usr/bin/env python3
"""Run a Y TMC2226 StallGuard diagnostic over Klipper's API socket.

By default this script sends itself to menderpi over SSH and runs against the
printer's local Klipper API socket. Use --local to connect to a local socket.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_REMOTE = os.environ.get("MENDERPI_HOST", "pi@menderpi.local")
DEFAULT_UDS = os.environ.get("KLIPPY_UDS", "/home/pi/printer_data/comms/klippy.sock")
MESSAGE_TERMINATOR = b"\x03"


class KlipperApi:
    def __init__(self, uds_path: str):
        self.uds_path = uds_path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(uds_path)
        self.sock.setblocking(False)
        self.buffer = b""
        self.next_request_id = 1
        self.stallguard_samples: list[list[float]] = []
        self.gcode_output: list[str] = []

    def close(self) -> None:
        self.sock.close()

    def clear_stallguard_samples(self) -> None:
        self.stallguard_samples.clear()

    def send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        request_id = self.next_request_id
        self.next_request_id += 1
        request = {"id": request_id, "method": method, "params": params or {}}
        self.sock.sendall(json.dumps(request).encode("utf-8") + MESSAGE_TERMINATOR)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for message in self.read_messages(timeout=0.1):
                if message.get("id") == request_id:
                    if "error" in message:
                        error = message["error"]
                        raise RuntimeError(
                            f"{method} failed: {error.get('message', error)}"
                        )
                    return message.get("result", {})
                self.handle_async_message(message)
        raise TimeoutError(f"Timed out waiting for {method}")

    def read_messages(self, *, timeout: float = 0.0) -> list[dict[str, Any]]:
        readable, _, _ = select.select([self.sock], [], [], timeout)
        if not readable:
            return []

        chunk = self.sock.recv(65536)
        if not chunk:
            raise RuntimeError("Klipper API socket closed")
        self.buffer += chunk

        messages: list[dict[str, Any]] = []
        while MESSAGE_TERMINATOR in self.buffer:
            raw, self.buffer = self.buffer.split(MESSAGE_TERMINATOR, 1)
            if raw:
                messages.append(json.loads(raw.decode("utf-8")))
        return messages

    def handle_async_message(self, message: dict[str, Any]) -> None:
        stream = message.get("stream")
        params = message.get("params", {})
        if stream == "stallguard":
            self.stallguard_samples.extend(params.get("data", []))
        elif stream == "gcode":
            response = params.get("response")
            if response:
                self.gcode_output.append(response)

    def drain(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            for message in self.read_messages(timeout=0.05):
                self.handle_async_message(message)

    def run_gcode(self, script: str, *, timeout: float = 60.0) -> None:
        self.send_request("gcode/script", {"script": script}, timeout=timeout)
        self.drain(0.2)


def thermal_bucket(drv_status: dict[str, Any] | None) -> str:
    drv_status = drv_status or {}
    if drv_status.get("t157"):
        return ">=157C"
    if drv_status.get("t150"):
        return "about 150-156C"
    if drv_status.get("t143"):
        return "about 143-149C"
    if drv_status.get("t120"):
        return "about 120-142C"
    return "<120C typical junction comparator"


def query_status(api: KlipperApi) -> dict[str, Any]:
    result = api.send_request(
        "objects/query",
        {
            "objects": {
                "webhooks": None,
                "toolhead": None,
                "print_stats": None,
                "tmc2209 stepper_y": None,
                "gcode_button y_tmc_diag": None,
            }
        },
        timeout=10.0,
    )
    return result.get("status", {})


def summarize_samples(
    label: str, threshold: int, samples: list[list[float]]
) -> dict[str, Any]:
    values = [int(sample[1]) for sample in samples if len(sample) >= 2 and sample[1] >= 0]
    if not values:
        print(f"{label}: no StallGuard samples captured", flush=True)
        return {"count": 0, "crossed": False}

    compare_value = threshold * 2
    crossed = min(values) <= compare_value
    mean_value = statistics.fmean(values)
    print(
        f"{label}: samples={len(values)} min={min(values)} "
        f"mean={mean_value:.1f} max={max(values)} "
        f"threshold_compare={compare_value} crossed={crossed}",
        flush=True,
    )
    return {
        "count": len(values),
        "min": min(values),
        "mean": mean_value,
        "max": max(values),
        "compare": compare_value,
        "crossed": crossed,
    }


def print_driver_status(api: KlipperApi, label: str) -> dict[str, Any]:
    status = query_status(api)
    tmc_y = status.get("tmc2209 stepper_y", {})
    drv_status = tmc_y.get("drv_status") or {}
    diag = status.get("gcode_button y_tmc_diag", {})
    print(
        f"{label}: thermal={thermal_bucket(drv_status)} "
        f"drv_status={drv_status} diag={diag}",
        flush=True,
    )
    return status


def run_move(
    api: KlipperApi,
    *,
    label: str,
    script: str,
    threshold: int,
    timeout: float,
) -> dict[str, Any]:
    print(f"\n== {label} ==", flush=True)
    api.clear_stallguard_samples()
    api.gcode_output.clear()
    api.run_gcode(script + "\nM400", timeout=timeout)
    api.drain(0.5)
    sample_summary = summarize_samples(label, threshold, api.stallguard_samples)
    status = print_driver_status(api, label)
    diag_state = (
        status.get("gcode_button y_tmc_diag", {}).get("state", "UNKNOWN")
    )
    diag_asserted = any("Y TMC2226 DIAG asserted" in line for line in api.gcode_output)
    if diag_asserted:
        print(f"{label}: DIAG press message observed in gcode output", flush=True)
    return {
        "sample_summary": sample_summary,
        "diag_state": diag_state,
        "diag_asserted": diag_asserted,
        "triggered": sample_summary["crossed"] or diag_asserted or diag_state == "PRESSED",
    }


def parse_accel_steps(value: str) -> list[int]:
    steps = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        steps.append(int(item))
    if not steps:
        raise ValueError("At least one acceleration step is required")
    for step in steps:
        if step <= 0:
            raise ValueError("Acceleration steps must be positive")
    return steps


def run_accel_sweep(api: KlipperApi, args: argparse.Namespace) -> bool:
    accel_steps = parse_accel_steps(args.sweep_accels)
    feed = args.sweep_velocity * 60.0
    low_y = args.sweep_low_y
    high_y = args.sweep_high_y
    current_y = low_y
    target_y = high_y

    print(
        "\nStarting acceleration sweep: "
        f"threshold={args.threshold}, compare={args.threshold * 2}, "
        f"velocity={args.sweep_velocity:g}mm/s, "
        f"steps={','.join(str(step) for step in accel_steps)}, "
        f"travel=Y{low_y:g}<->Y{high_y:g}",
        flush=True,
    )
    api.run_gcode(
        "\n".join(
            [
                (
                    "SET_VELOCITY_LIMIT "
                    "VELOCITY=200 ACCEL=1000 SQUARE_CORNER_VELOCITY=5"
                ),
                f"G1 Y{low_y:g} F12000",
                "M400",
            ]
        ),
        timeout=args.move_timeout,
    )

    for index, accel in enumerate(accel_steps, start=1):
        result = run_move(
            api,
            label=(
                f"accel sweep {index}/{len(accel_steps)}: "
                f"Y{current_y:g}->Y{target_y:g} at "
                f"{args.sweep_velocity:g}mm/s, {accel}mm/s^2"
            ),
            threshold=args.threshold,
            timeout=args.move_timeout,
            script="\n".join(
                [
                    (
                        "SET_VELOCITY_LIMIT "
                        f"VELOCITY={args.sweep_velocity:g} "
                        f"ACCEL={accel} "
                        f"SQUARE_CORNER_VELOCITY={args.sweep_scv:g}"
                    ),
                    f"G1 Y{target_y:g} F{feed:g}",
                ]
            ),
        )
        if result["triggered"]:
            print(
                "Stopping acceleration sweep after first StallGuard/DIAG trigger "
                f"at accel={accel}mm/s^2.",
                flush=True,
            )
            return True
        current_y, target_y = target_y, low_y if target_y == high_y else high_y

    print("Acceleration sweep completed without StallGuard/DIAG trigger.", flush=True)
    return False


def run_on_printer(args: argparse.Namespace) -> int:
    api = KlipperApi(args.uds)
    rehome_after_test = False
    old_limits: dict[str, Any] = {}

    try:
        api.send_request(
            "info",
            {"client_info": {"program": "run_y_tmc_stallguard_diagnostic.py"}},
            timeout=5.0,
        )
        api.send_request(
            "gcode/subscribe_output",
            {"response_template": {"stream": "gcode"}},
            timeout=5.0,
        )
        api.send_request(
            "tmc/stallguard_dump",
            {"name": "stepper_y", "response_template": {"stream": "stallguard"}},
            timeout=5.0,
        )

        status = query_status(api)
        old_limits = status.get("toolhead", {})
        print_driver_status(api, "initial")

        setup_gcode = "\n".join(
            [
                "Y_TMC_THERMAL_STATUS",
                "SET_TMC_CURRENT STEPPER=stepper_y CURRENT=2.0",
                "G90",
                "G28 Y",
                "SET_VELOCITY_LIMIT VELOCITY=60 ACCEL=500 SQUARE_CORNER_VELOCITY=5",
                "G1 Y20 F3600",
                "M400",
                f"Y_TMC_STALLGUARD_ARM THRESHOLD={args.threshold}",
            ]
        )
        api.run_gcode(setup_gcode, timeout=args.home_timeout)
        print_driver_status(api, "after arm")

        run_move(
            api,
            label="normal Y20->Y120 at 100mm/s, 1000mm/s^2",
            threshold=args.threshold,
            timeout=args.move_timeout,
            script="\n".join(
                [
                    "SET_VELOCITY_LIMIT VELOCITY=100 ACCEL=1000 SQUARE_CORNER_VELOCITY=5",
                    "G1 Y120 F6000",
                ]
            ),
        )
        run_move(
            api,
            label="normal Y120->Y20 at 100mm/s, 1000mm/s^2",
            threshold=args.threshold,
            timeout=args.move_timeout,
            script="G1 Y20 F6000",
        )

        for cycle in range(args.heat_cycles):
            run_move(
                api,
                label=f"2.0A heat cycle {cycle + 1}: Y30->Y220",
                threshold=args.threshold,
                timeout=args.move_timeout,
                script="\n".join(
                    [
                        "SET_VELOCITY_LIMIT VELOCITY=200 ACCEL=3000 SQUARE_CORNER_VELOCITY=8",
                        "G1 Y30 F12000",
                        "G1 Y220 F12000",
                    ]
                ),
            )

        if args.accel_sweep:
            rehome_after_test = True
            run_accel_sweep(api, args)

        if args.aggressive:
            rehome_after_test = True
            run_move(
                api,
                label="aggressive Y20->Y260 at 500mm/s, 8000mm/s^2",
                threshold=args.threshold,
                timeout=args.move_timeout,
                script="\n".join(
                    [
                        "SET_VELOCITY_LIMIT VELOCITY=500 ACCEL=8000 SQUARE_CORNER_VELOCITY=10",
                        "G1 Y20 F12000",
                        "G1 Y260 F30000",
                    ]
                ),
            )
        else:
            print("\nAggressive leg skipped; pass --aggressive to run it.", flush=True)

        return 0
    finally:
        restore_velocity = old_limits.get("max_velocity", 500)
        restore_accel = old_limits.get("max_accel", 8000)
        restore_scv = old_limits.get("square_corner_velocity", 10)
        restore_lines = [
            "Y_TMC_STALLGUARD_DISARM",
            (
                "SET_VELOCITY_LIMIT "
                f"VELOCITY={restore_velocity} "
                f"ACCEL={restore_accel} "
                f"SQUARE_CORNER_VELOCITY={restore_scv}"
            ),
        ]
        if rehome_after_test:
            restore_lines.append("G28 Y")
        try:
            api.run_gcode("\n".join(restore_lines), timeout=args.home_timeout)
            print_driver_status(api, "final")
        finally:
            api.close()


def run_remote(args: argparse.Namespace) -> int:
    source = Path(__file__).read_text(encoding="utf-8")
    remote_args = [
        "python3",
        "-",
        "--on-printer",
        "--uds",
        args.uds,
        "--threshold",
        str(args.threshold),
        "--heat-cycles",
        str(args.heat_cycles),
        "--home-timeout",
        str(args.home_timeout),
        "--move-timeout",
        str(args.move_timeout),
    ]
    if args.accel_sweep:
        remote_args.append("--accel-sweep")
        remote_args.extend(["--sweep-accels", args.sweep_accels])
        remote_args.extend(["--sweep-velocity", str(args.sweep_velocity)])
        remote_args.extend(["--sweep-low-y", str(args.sweep_low_y)])
        remote_args.extend(["--sweep-high-y", str(args.sweep_high_y)])
        remote_args.extend(["--sweep-scv", str(args.sweep_scv)])
    if args.aggressive:
        remote_args.append("--aggressive")
    command = ["ssh", args.remote, *remote_args]
    completed = subprocess.run(command, input=source, text=True, check=False)
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stream Y TMC2226 StallGuard data while running guarded Y moves."
    )
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--uds", default=DEFAULT_UDS)
    parser.add_argument("--local", action="store_true", help="Use local UDS.")
    parser.add_argument("--on-printer", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--threshold", type=int, default=4)
    parser.add_argument("--heat-cycles", type=int, default=4)
    parser.add_argument("--accel-sweep", action="store_true")
    parser.add_argument("--sweep-accels", default="1000,2500,4000,6000,8000")
    parser.add_argument("--sweep-velocity", type=float, default=500.0)
    parser.add_argument("--sweep-low-y", type=float, default=30.0)
    parser.add_argument("--sweep-high-y", type=float, default=260.0)
    parser.add_argument("--sweep-scv", type=float, default=10.0)
    parser.add_argument("--aggressive", action="store_true")
    parser.add_argument("--home-timeout", type=float, default=90.0)
    parser.add_argument("--move-timeout", type=float, default=45.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    args = build_parser().parse_args(argv)
    if not 0 <= args.threshold <= 255:
        raise SystemExit("--threshold must be between 0 and 255")
    if args.heat_cycles < 0:
        raise SystemExit("--heat-cycles must be >= 0")
    try:
        parse_accel_steps(args.sweep_accels)
    except ValueError as exc:
        raise SystemExit(f"--sweep-accels invalid: {exc}") from exc
    if args.sweep_velocity <= 0:
        raise SystemExit("--sweep-velocity must be > 0")
    if args.sweep_low_y >= args.sweep_high_y:
        raise SystemExit("--sweep-low-y must be below --sweep-high-y")
    if args.local or args.on_printer:
        return run_on_printer(args)
    return run_remote(args)


if __name__ == "__main__":
    raise SystemExit(main())
