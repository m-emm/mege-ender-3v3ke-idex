#!/usr/bin/env python3
"""Replay guard for the XZ sweep captured with a stale T1 XY prior."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


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
    / "20260810_idex_tool_xz_sweep_after_xy_endstop_update_20260810"
)


def _analyzer_module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_idex_tool_xz_sweep_after_endstop_update_replay",
        FILES / "vision_tool_xz_sweep.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dataset() -> tuple[dict, list[Path]]:
    manifest_path = DATASET_ROOT / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip(f"captured dataset is absent: {DATASET_ROOT}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    image_paths = [
        DATASET_ROOT / "frames" / f"{frame['frame']}.jpg"
        for frame in manifest["frames"]
    ]
    missing = [path for path in image_paths if not path.is_file()]
    if missing:
        pytest.skip(f"captured frame is absent, e.g. {missing[0]}")
    return manifest, image_paths


def test_captured_xz_run_rejects_stale_prior_before_decoding():
    manifest, image_paths = _dataset()
    assert manifest["job_type"] == "idex_tool_xz_sweep_report"
    assert len(manifest["frames"]) == 96

    references = copy.deepcopy(manifest["tool_xz_reference"])
    references["t0"]["nozzle_image_prior_source"] = {
        "acquisition_endstop_xy_mm": [-85.472, -14.800],
        "fact_name": "tool.t0.vision_xy_datum",
        "fact_set_hash": "sha256:stale-t0",
    }
    references["t1"]["nozzle_image_prior_source"] = {
        "acquisition_endstop_xy_mm": [341.145, -13.537],
        "fact_name": "tool.t1.vision_xy_datum",
        "fact_set_hash": "sha256:stale-t1",
    }

    analyzer = _analyzer_module()
    with pytest.raises(
        analyzer.ToolXZSweepError,
        match="T1 X/Z reference uses a stale XY prior",
    ):
        analyzer.analyze(
            image_paths,
            DATASET_ROOT / "strict_stale_prior_rejection_artifacts",
            frames=manifest["frames"],
            references=references,
            acquisition_calibration=manifest["acquisition_calibration"],
        )
