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
CAPTURE_PATH = FILES / "vision_capture.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _module(monkeypatch, tmp_path):
    framebuffer = tmp_path / "framebuffer"
    framebuffer.mkdir()
    assert cv2.imwrite(
        str(framebuffer / "latest.jpg"),
        np.full((100, 160, 3), 80, dtype=np.uint8),
    )
    (framebuffer / "latest.json").write_text(
        json.dumps(
            {
                "frame_seq": 10,
                "width": 160,
                "height": 100,
                "camera_profile": {
                    "profile_names": ["analysis", "nozzle_cam_analysis"]
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VISION_FRAMEBUFFER_DIR", str(framebuffer))
    monkeypatch.setenv(
        "VISION_CAMERA_PROFILE_REQUEST_FILE",
        str(framebuffer / "profile_request.json"),
    )
    monkeypatch.setenv("VISIOND_SOCKET_ENABLED", "0")
    return _load(CAPTURE_PATH, "vision_capture_clean_test")


def _prepare(module, tmp_path):
    job_root = tmp_path / "calibration" / "jobs"
    job_id = "bed_tab_y_test"
    job_dir = job_root / job_id
    (job_dir / "frames").mkdir(parents=True)
    frames = [
        {
            "seq": seq,
            "frame": f"y_{seq:02d}_{offset:02d}mm",
            "camera": "nozzle_cam",
            "profile": "analysis",
            "tool": "T0",
            "y_offset_mm": offset,
            "commanded_position_mm": [-80.0, -14.0 + offset, 300.0],
            "pass": "forward" if seq <= 4 else "reverse",
        }
        for seq, offset in enumerate((0, 5, 10, 15, 20, 15, 10, 5, 0))
    ]
    gcode = (
        f"VISION_JOB_BEGIN JOB={job_id} "
        f"MANIFEST_HASH={module.HASH_PLACEHOLDER} "
        f"GCODE_HASH={module.HASH_PLACEHOLDER}\n"
    )
    manifest = {
        "schema": "vision-calibration-acquisition-manifest",
        "schema_version": 1,
        "job_id": job_id,
        "job_type": "nozzle_cam_bed_tab_y_scale",
        "definition_version": 1,
        "created_at_utc": "2026-07-30T00:00:00+00:00",
        "camera": "nozzle_cam",
        "profile": "analysis",
        "light_macro": "NOZZLE_CAM_Y_FEATURE_LIGHT",
        "frame_count": 9,
        "frames": frames,
        "motion": {},
        "applicability": {},
        "applicability_hash": module.canonical_hash({}),
        "provenance": {},
        "gcode_file": "acquisition.gcode",
        "gcode_hash": module.compute_gcode_hash(gcode),
        "manifest_hash": module.HASH_PLACEHOLDER,
    }
    manifest["manifest_hash"] = module.compute_manifest_hash(manifest)
    final_gcode = gcode.replace(
        f"MANIFEST_HASH={module.HASH_PLACEHOLDER}",
        f"MANIFEST_HASH={manifest['manifest_hash']}",
    ).replace(
        f"GCODE_HASH={module.HASH_PLACEHOLDER}",
        f"GCODE_HASH={manifest['gcode_hash']}",
    )
    (job_dir / "acquisition.gcode").write_text(final_gcode, encoding="utf-8")
    (job_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (job_dir / "state.json").write_text(
        json.dumps({"state": "prepared", "committed_frame_count": 0}),
        encoding="utf-8",
    )
    return job_root, manifest


def _begin(manifest):
    return {
        "job": manifest["job_id"],
        "manifest_hash": manifest["manifest_hash"],
        "gcode_hash": manifest["gcode_hash"],
    }


def test_capture_api_rejects_old_actions_and_bad_hash(monkeypatch, tmp_path):
    module = _module(monkeypatch, tmp_path)
    job_root, manifest = _prepare(module, tmp_path)
    api = module.VisionJobApi(job_root=job_root)

    response = api.handle({"action": "measure_bed_y", "params": {}})
    assert not response["ok"]
    assert "unknown request action" in response["error"]

    with pytest.raises(module.CaptureError, match="manifest hash mismatch"):
        api.job_begin(
            {
                **_begin(manifest),
                "manifest_hash": "sha256:" + "0" * 64,
            }
        )


def test_capture_api_commits_nine_fresh_frames(monkeypatch, tmp_path):
    module = _module(monkeypatch, tmp_path)
    job_root, manifest = _prepare(module, tmp_path)
    api = module.VisionJobApi(job_root=job_root)
    source = module.FRAMEBUFFER_LATEST_IMAGE
    sequence = {"value": 10}

    def fresh(previous_seq, *, timeout, profile):
        assert profile == "analysis"
        sequence["value"] += 1
        return source, {
            "frame_seq": sequence["value"],
            "captured_at_utc": f"2026-07-30T00:00:{sequence['value']:02d}+00:00",
            "camera_profile": {
                "profile_names": ["analysis", "nozzle_cam_analysis"]
            },
        }

    monkeypatch.setattr(module, "wait_for_new_frame", fresh)
    assert api.job_begin(_begin(manifest))["state"] == "acquiring"
    for frame in manifest["frames"]:
        result = api.capture(
            {
                "job": manifest["job_id"],
                "seq": frame["seq"],
                "frame": frame["frame"],
                "camera": "nozzle_cam",
                "profile": "analysis",
                "tool": "T0",
                "toolhead_position": frame["commanded_position_mm"] + [0.0],
                "gcode_position": frame["commanded_position_mm"] + [0.0],
                "homed_axes": "xyz",
                "temperatures": {"heater_bed": {"temperature": 23.0}},
            }
        )
        assert result["framebuffer_seq"] == 11 + frame["seq"]
        assert result["actual_toolhead_position_mm"]
        assert result["temperatures"]["heater_bed"]["temperature"] == 23.0
    assert api.job_end(
        {"job": manifest["job_id"], "expected_frames": 9}
    )["state"] == "acquired"
    assert not (job_root / ".active_job.json").exists()
