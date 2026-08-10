#!/usr/bin/env python3
"""Local replay of the fresh post-endstop X/Z sweep."""

from __future__ import annotations

import copy
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
FILES = REPO_ROOT / "klipper_setup/image_build/overlays/stage2/99-klipperpi/files"
DATASET_ROOT = (
    REPO_ROOT
    / "resources/vision_datasets/20260810_idex_tool_xz_sweep_after_post_endstop_xy_check_20260810"
)
OUTPUT_ROOT = REPO_ROOT / "output/vision_idex_tool_xz_sweep_replay"


def _analyzer_module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_idex_tool_xz_sweep_after_post_endstop_xy_check_replay",
        FILES / "vision_tool_xz_sweep.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_root() -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex[:8]
    root = OUTPUT_ROOT / "runs" / run_id / "after_post_endstop_xy_check_replay"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _dataset():
    manifest_path = DATASET_ROOT / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip(f"captured dataset is absent: {DATASET_ROOT}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    image_paths = [DATASET_ROOT / "frames" / f"{frame['frame']}.jpg" for frame in manifest["frames"]]
    sidecar_paths = [DATASET_ROOT / "frames" / f"{frame['frame']}.json" for frame in manifest["frames"]]
    missing = [path for path in [*image_paths, *sidecar_paths] if not path.is_file()]
    if missing:
        pytest.skip(f"captured frame or sidecar is absent, e.g. {missing[0]}")
    return manifest, image_paths, sidecar_paths


def _references(manifest: dict) -> dict:
    references = copy.deepcopy(manifest["tool_xz_reference"])
    for tool in ("t0", "t1"):
        endstop = manifest["acquisition_calibration"]["tool_xy_endstops_mm"][tool]
        references[tool]["nozzle_image_prior_source"] = {
            "acquisition_endstop_xy_mm": [endstop["x"], endstop["y"]],
            "fact_name": f"tool.{tool}.vision_xy_datum",
            "fact_set_hash": f"sha256:replay-{tool}",
        }
    return references


def test_replay_fresh_post_endstop_xz_sweep_writes_overlays_and_plots(monkeypatch):
    manifest, image_paths, sidecar_paths = _dataset()
    assert manifest["job_type"] == "idex_tool_xz_sweep_report"
    assert len(manifest["frames"]) == 96

    analyzer = _analyzer_module()
    monkeypatch.setattr(analyzer, "GENERATE_OVERLAYS", True)
    root = _run_root()
    result = analyzer.analyze(
        image_paths,
        root / "artifacts",
        frames=manifest["frames"],
        references=_references(manifest),
        acquisition_calibration=manifest["acquisition_calibration"],
    )
    (root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    overlay_paths = []
    plot_paths = []
    for key, artifact in result["artifacts"].items():
        path = Path(artifact["path"])
        if key.startswith("tool_xz_sweep_overlay_"):
            overlay_paths.append(path)
        elif path.suffix.lower() == ".png":
            plot_paths.append(path)
    assert len(overlay_paths) == len(image_paths)
    for frame, image_path, sidecar_path in zip(
        manifest["frames"], image_paths, sidecar_paths
    ):
        overlay_path = next(
            path for path in overlay_paths
            if path.name.startswith(f"{int(frame['seq']):02d}_")
        )
        source = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        overlay = cv2.imread(str(overlay_path), cv2.IMREAD_COLOR)
        assert source is not None and overlay is not None
        assert overlay.shape == source.shape
        assert sidecar_path.is_file()
        _logger.info("Overlay %s", overlay_path.resolve())
    for path in sorted(plot_paths):
        assert path.is_file()
        _logger.info("Plot %s", path.resolve())

    records = result["records"]
    _logger.info(
        "Replay summary root=%s frames=%d fiducials=%d nozzle=%d accepted=%s",
        root.resolve(),
        len(records),
        sum(record["fiducials_detected"] for record in records),
        sum(record["nozzle_detected"] for record in records),
        result["accepted"],
    )
    assert len(records) == 96
    assert all(
        record["localization"]["localization_method"] == "bright_circle_roi_v1"
        and record["localization"]["prior_center_px"] is not None
        and record["localization"]["roi_px"] is not None
        for record in records
    )
