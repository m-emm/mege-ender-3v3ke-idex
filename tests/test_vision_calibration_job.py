import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FILES = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)


def _load(monkeypatch, tmp_path):
    calibration_root = tmp_path / "vision" / "calibration"
    gcode_root = tmp_path / "gcodes" / "vision_jobs"
    framebuffer = tmp_path / "framebuffer"
    framebuffer.mkdir(parents=True)
    image = np.full((120, 200, 3), 100, dtype=np.uint8)
    assert cv2.imwrite(str(framebuffer / "latest.jpg"), image)
    (framebuffer / "latest.json").write_text(
        json.dumps(
            {
                "frame_seq": 12,
                "width": 200,
                "height": 120,
                "camera_profile": {"profile_names": ["analysis"]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VISION_CALIBRATION_ROOT", str(calibration_root))
    monkeypatch.setenv("VISION_CALIBRATION_GCODE_ROOT", str(gcode_root))
    monkeypatch.setenv(
        "VISION_CALIBRATION_REGISTRY", str(FILES / "vision_job_types.json")
    )
    monkeypatch.setenv(
        "VISION_CAMERA_PROFILE_FILE", str(FILES / "nozzle_cam_profiles.json")
    )
    monkeypatch.setenv("VISION_FRAMEBUFFER_DIR", str(framebuffer))
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    name = f"vision_calibration_job_test_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(name, FILES / "vision_calibration.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _status(*, homed="xyz", virtual_sd=False, y_max=230.0):
    return {
        "webhooks": {"state": "ready"},
        "print_stats": {"state": "standby", "filename": ""},
        "virtual_sdcard": {"is_active": virtual_sd, "progress": 0.0},
        "toolhead": {
            "homed_axes": homed,
            "position": [0.0, 0.0, 20.0, 0.0],
            "axis_minimum": [-80.4, -14.8, 0.0],
            "axis_maximum": [357.5, y_max, 293.75],
        },
        "gcode_move": {"gcode_position": [0.0, 0.0, 20.0, 0.0]},
        "configfile": {
            "save_config_pending": False,
            "settings": {
                "stepper_x": {
                    "position_min": -80.4,
                    "position_endstop": -80.4,
                    "position_max": 230.0,
                },
                "stepper_y": {
                    "position_min": -14.8,
                    "position_endstop": -14.8,
                    "position_max": 230.0,
                    "rotation_distance": 40.0,
                    "microsteps": 16,
                },
                "stepper_z": {
                    "position_min": 0.0,
                    "position_endstop": 293.75,
                    "position_max": 293.75,
                },
                "gcode_macro nozzle_cam_y_feature_light": {
                    "gcode": "VISION_LIGHT_OFF\nSET_LED LED=vision_light INDEX=2 RED=0.45"
                },
            },
        },
        "gcode_macro _IDEX_CONFIG_FINGERPRINT": {"source_sha256": "sha256:active"},
        "extruder": {"temperature": 24.0, "target": 0.0},
        "extruder1": {"temperature": 24.0, "target": 0.0},
        "heater_bed": {"temperature": 23.0, "target": 0.0},
    }


def test_prepare_resolves_active_limits_and_generates_exact_motion(
    monkeypatch, tmp_path
):
    module = _load(monkeypatch, tmp_path)
    result = module.prepare_job(
        "unit", expected_fingerprint="sha256:active", status=_status()
    )
    job_dir = Path(result["job_dir"])
    manifest = json.loads((job_dir / "manifest.json").read_text())
    gcode = (job_dir / "acquisition.gcode").read_text()

    assert manifest["motion"]["resolved_pose"] == {
        "x_mm": -80.4,
        "y_base_mm": -14.8,
        "y_endstop_mm": -14.8,
        "z_mm": 293.75,
    }
    assert [frame["y_offset_mm"] for frame in manifest["frames"]] == [
        0,
        5,
        10,
        15,
        20,
        15,
        10,
        5,
        0,
    ]
    assert "G28" not in gcode
    assert gcode.count("VISION_CAPTURE_SYNC ") == 9
    assert gcode.index("\nT0\n") < gcode.index("VISION_CAPTURE_SYNC ")
    assert gcode.index("NOZZLE_CAM_Y_FEATURE_LIGHT") < gcode.index("\nT0\n")
    assert gcode.rindex("G1 Y-14.800000") < gcode.index("VISION_JOB_END")
    assert gcode.index("VISION_JOB_END") < gcode.index("VISION_LIGHT_OFF")
    assert gcode.count("F3600.000") == 11
    assert (module.GCODE_ROOT / f"{manifest['job_id']}.gcode").is_file()
    assert (module.VISION_ROOT / "index.html").is_file()


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (_status(homed="xy"), "already be homed"),
        (_status(virtual_sd=True), "virtual-SD"),
        (_status(y_max=0.0), "outside active limits"),
    ],
)
def test_prepare_rejects_unsafe_preconditions(monkeypatch, tmp_path, status, message):
    module = _load(monkeypatch, tmp_path)
    with pytest.raises(module.VisionCalibrationError, match=message):
        module.prepare_job("unsafe", status=status)


def test_prepare_rejects_fingerprint_drift(monkeypatch, tmp_path):
    module = _load(monkeypatch, tmp_path)
    with pytest.raises(module.VisionCalibrationError, match="does not match"):
        module.prepare_job(
            "drift",
            expected_fingerprint="sha256:other",
            status=_status(),
        )


def test_rejected_report_handles_unavailable_vector(monkeypatch, tmp_path):
    module = _load(monkeypatch, tmp_path)
    report = module._report_markdown(
        {"job_id": "job"},
        {
            "analysis_run_id": "analysis",
            "state": "rejected",
        },
        {
            "axis_vector_px_per_mm": None,
            "accepted_patch_count": 0,
            "reasons": ["fewer than three independent moving patches"],
        },
    )
    assert "Axis vector: unavailable" in report
    assert "fewer than three independent moving patches" in report


def test_legacy_public_interfaces_and_runtime_fields_are_absent():
    capture = (FILES / "vision_capture.py").read_text()
    extra = (
        REPO_ROOT / "klipper_setup/klipper_host/klippy/extras/vision.py"
    ).read_text()
    template = (
        REPO_ROOT / "klipper_setup/klipper_config/printer.cfg.template"
    ).read_text()
    generator = (
        REPO_ROOT / "klipper_setup/klipper_config/generate_printer_cfg.py"
    ).read_text()
    combined = "\n".join((capture, extra, template, generator))
    for legacy in (
        "IDEX_BED_Y_VISION_SWEEP",
        "IDEX_MEASURE_BED_Y",
        "VISION_MEASURE_BED_Y",
        "--prepare-bed-y-job",
        "--run-bed-y-job",
        "printer_to_image",
        "bed_y_feature",
        "vision_nozzle_align",
        "vision_bed_y",
    ):
        assert legacy not in combined
    assert "IDEX_BED_TAB_Y_SCALE_CALIBRATE" in template
    assert "idex_bed_tab_y_scale_calibrate" in capture
