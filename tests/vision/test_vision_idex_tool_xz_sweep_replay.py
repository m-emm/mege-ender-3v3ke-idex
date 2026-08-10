#!/usr/bin/env python3
"""Replay the 2026-08-10 live IDEX tool X/Z sweep with full overlays.

The dataset is copied from the printer job named in ``DATASET_ROOT``.  Run:

    pytest -q -s tests/vision/test_vision_idex_tool_xz_sweep_replay.py
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import pytest


_logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
FILES = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)
DATASET_ROOT = (
    REPO_ROOT
    / "resources"
    / "vision_datasets"
    / "20260810_idex_tool_xz_sweep_report_test_coords"
)
OUTPUT_ROOT = REPO_ROOT / "output" / "vision_idex_tool_xz_sweep_replay"


def _analyzer_module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_idex_tool_xz_sweep_replay", FILES / "vision_tool_xz_sweep.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_root() -> Path:
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex[:8]
    )
    root = OUTPUT_ROOT / "runs" / run_id / "full_replay"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _dataset() -> tuple[dict, list[Path], list[Path]]:
    manifest_path = DATASET_ROOT / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip(f"local captured dataset is absent: {DATASET_ROOT}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = manifest["frames"]
    image_paths = [
        DATASET_ROOT / "frames" / f"{frame['frame']}.jpg" for frame in frames
    ]
    sidecar_paths = [
        DATASET_ROOT / "frames" / f"{frame['frame']}.json" for frame in frames
    ]
    missing = [path for path in [*image_paths, *sidecar_paths] if not path.is_file()]
    if missing:
        pytest.skip(f"captured frame or sidecar is absent, e.g. {missing[0]}")
    return manifest, image_paths, sidecar_paths


def _write_result(root: Path, result: dict) -> None:
    (root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_replay_live_idex_tool_xz_sweep_writes_overlays(monkeypatch):
    manifest, image_paths, sidecar_paths = _dataset()
    assert manifest["job_type"] == "idex_tool_xz_sweep_report"
    assert len(manifest["frames"]) == 60
    assert len(image_paths) == len(sidecar_paths) == len(manifest["frames"])

    analyzer = _analyzer_module()
    monkeypatch.setattr(analyzer, "GENERATE_OVERLAYS", True)
    root = _run_root()
    result = analyzer.analyze(
        image_paths,
        root / "artifacts",
        frames=manifest["frames"],
        references=manifest["tool_xz_reference"],
        acquisition_calibration=manifest["acquisition_calibration"],
    )
    _write_result(root, result)

    overlays = {
        key: Path(artifact["path"])
        for key, artifact in result["artifacts"].items()
        if key.startswith("tool_xz_sweep_overlay_")
    }
    assert len(overlays) == len(manifest["frames"])
    for frame, image_path, sidecar_path in zip(
        manifest["frames"], image_paths, sidecar_paths
    ):
        overlay_path = overlays[f"tool_xz_sweep_overlay_{int(frame['seq']):02d}"]
        source = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        overlay = cv2.imread(str(overlay_path), cv2.IMREAD_COLOR)
        assert source is not None
        assert overlay is not None
        assert overlay.shape == source.shape
        assert sidecar_path.is_file()
        record = result["records"][int(frame["seq"])]
        _logger.info(
            "Overlay %s tool=%s x=%.3f z=%.3f fiducials=%s nozzle=%s accepted=%s",
            overlay_path.resolve(),
            frame["tool"],
            float(frame["x_mm"]),
            float(frame["z_mm"]),
            "yes" if record["fiducials_detected"] else "no",
            "yes" if record["nozzle_detected"] else "no",
            "yes" if record["accepted_for_u_x_fit"] else "no",
        )

    assert len(result["records"]) == 60
    assert {record["tool"] for record in result["records"]} == {"T0", "T1"}
    assert "fit_strategy_comparison" in result
    assert Path(result["artifacts"]["fit_strategy_comparison"]["path"]).is_file()
    assert Path(result["artifacts"]["fit_strategy_comparison_plot"]["path"]).is_file()
    _logger.info(
        "Replay summary %s frames=%d fiducials=%d nozzle=%d accepted=%s",
        root.resolve(),
        len(result["records"]),
        sum(record["fiducials_detected"] for record in result["records"]),
        sum(record["nozzle_detected"] for record in result["records"]),
        result["accepted"],
    )
