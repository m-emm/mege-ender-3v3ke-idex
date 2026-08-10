"""Local integration replay for the red-marker -> tool-XY handover.

This deliberately exercises the boundary that a printer run crosses: the
red-marker publication supplies a model object, XY preparation serializes it
into the manifest reference, and XY analysis consumes that exact reference.
The recorded XY frames are used for both tools so the test remains fast and
does not move a printer.
"""

import importlib.util
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


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
FIXTURE = Path(__file__).parent / "fixtures" / "tool_xy_measurement"
OUTPUT_ROOT = REPO_ROOT / "output" / "vision_red_marker_to_xy_integration"


def _module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    name = f"vision_tool_xy_integration_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(
        name, FILES / "vision_tool_xy_calibration.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fact_value(fact_set, fact_name):
    return next(fact["value"] for fact in fact_set["facts"] if fact["name"] == fact_name)


def _line_model_from_recorded_xy_sidecars(frames):
    x_values = np.asarray([float(frame["x_mm"]) for frame in frames], dtype=np.float64)
    marker_centers = np.asarray(
        [frame["expected_marker_pixel_px"] for frame in frames], dtype=np.float64
    )
    design = np.column_stack((np.ones_like(x_values), x_values))
    coefficients, _, _, _ = np.linalg.lstsq(design, marker_centers, rcond=None)
    return {
        "model": "linear_commanded_x_to_image_uv_v1",
        "coefficients_px": coefficients.tolist(),
    }


def _resolved():
    return {
        "axis_minimum": [-80.0, -14.8, 0.0],
        "axis_maximum": [355.0, 296.0, 300.0],
        "active_tool_calibration": {
            "tool_xy_endstops_mm": {
                "t0": {"x": -77.635, "y": -14.8},
                "t1": {"x": 351.739, "y": -13.8},
            },
            "tool_y_offsets_mm": {"t0": 0.0, "t1": -1.0},
        },
    }


def test_local_red_marker_publication_handover_runs_both_xy_tools():
    """Run the local red-marker line-model handover through both XY analyses."""
    module = _module()
    fixture = json.loads((FIXTURE / "fixture.json").read_text(encoding="utf-8"))
    source_facts = json.loads(
        (FIXTURE / fixture["source_fact_sets"]["red_marker_and_mapping"]["path"])
        .read_text(encoding="utf-8")
    )
    metric_facts = json.loads(
        (FIXTURE / fixture["source_fact_sets"]["bed_metric"]["path"])
        .read_text(encoding="utf-8")
    )
    mapping = _fact_value(
        source_facts, "camera.nozzle_cam.bed_fiducial.printer_xy_mapping"
    )
    metric = _fact_value(
        metric_facts, "camera.nozzle_cam.bed_fiducial.local_metric_model"
    )
    run_root = OUTPUT_ROOT / "runs" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )

    for tool in ("T0", "T1"):
        case = fixture["cases"][tool]
        directory = FIXTURE / case["directory"]
        source_manifest = json.loads(
            (directory / "source_manifest.json").read_text(encoding="utf-8")
        )
        frames = [
            frame
            for frame in source_manifest["frames"]
            if int(frame["seq"]) in set(case["source_sequences"])
        ]
        frame_paths = [directory / f"{frame['frame']}.jpg" for frame in frames]
        marker = dict(
            _fact_value(
                source_facts, f"tool.{tool.lower()}.red_marker_to_bed_tab_x_mm"
            )
        )
        # The fixture predates the published line-model field.  Reconstruct
        # the same four-number model from its recorded commanded-X sidecars,
        # which is the local replay equivalent of the red-marker publication.
        marker["image_line_model"] = _line_model_from_recorded_xy_sidecars(frames)
        marker["image_line_capture_y_mm"] = float(
            frames[0]["commanded_position_mm"][1]
        )
        input_values = {
            "bed_metric": metric,
            "bed_fiducial_printer_xy_mapping": mapping,
            f"{tool.lower()}_red_marker_offset": marker,
        }

        prepared = module.prepare_measurement(
            json.loads(
                (FILES / "vision_job_types.json").read_text(encoding="utf-8")
            )["job_types"][f"idex_tool_xy_measure_{tool.lower()}"],
            input_values=input_values,
            resolved=_resolved(),
        )
        handed_over_model = prepared["reference"]["marker_image_line_model"]
        assert handed_over_model["model"] == "linear_commanded_x_to_image_uv_v1"
        assert np.asarray(handed_over_model["coefficients_px"]).shape == (2, 2)

        artifact_dir = run_root / tool.lower() / "artifacts"
        result = module.analyze_measurement(
            frame_paths,
            artifact_dir,
            frames=frames,
            reference=prepared["reference"],
            acquisition_calibration=source_manifest["acquisition_calibration"],
            require_locator=False,
        )
        assert result["records"]
        localized = [
            record
            for record in result["records"]
            if record.get("center_px") is not None
        ]
        assert localized, f"no bright-circle detections for {tool}"
        assert all(
            record["localization_method"] == "bright_circle_roi_v1"
            for record in localized
        )
        for artifact in result["artifacts"].values():
            path = Path(artifact["path"])
            assert path.exists(), path
            _logger.info("Overlay %s", path.resolve())

        (run_root / tool.lower() / "result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _logger.info(
            "handover tool=%s accepted=%s localized=%d/%d",
            tool,
            result["accepted"],
            len(localized),
            len(result["records"]),
        )
