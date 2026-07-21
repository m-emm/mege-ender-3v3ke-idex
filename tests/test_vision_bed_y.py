import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VISION_FILES = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)
BED_Y_PATH = VISION_FILES / "vision_bed_y.py"
CAPTURE_PATH = VISION_FILES / "vision_capture.py"
APPLY_PATH = (
    REPO_ROOT
    / "klipper_setup"
    / "klipper_config"
    / "apply_nozzle_vision_calibration.py"
)
GENERATOR_PATH = APPLY_PATH.with_name("generate_printer_cfg.py")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _textured_image(width=640, height=480):
    rng = np.random.default_rng(12345)
    image = rng.integers(20, 220, size=(height, width, 3), dtype=np.uint8)
    cv2.line(image, (180, 230), (420, 230), (245, 245, 245), 4)
    cv2.rectangle(image, (250, 205), (330, 255), (30, 180, 70), 3)
    return image


def test_projection_recovers_both_y_drift_directions_and_cross_axis():
    module = _load(BED_Y_PATH, "vision_bed_y_projection_test")
    vector = (-0.25, -10.5)
    reference = (320.0, 240.0)
    for delta_y in (-1.75, 2.25):
        pixel = (
            reference[0] + vector[0] * delta_y,
            reference[1] + vector[1] * delta_y,
        )
        result = module.project_pixel_to_y(
            pixel=pixel,
            reference_pixel=reference,
            reference_y_mm=-4.8,
            axis_vector_px_per_mm=vector,
        )
        assert result["measured_y_mm"] == pytest.approx(-4.8 + delta_y)
        assert result["cross_axis_px"] == pytest.approx(0.0, abs=1e-9)

    perpendicular = (10.5, -0.25)
    result = module.project_pixel_to_y(
        pixel=(reference[0] + perpendicular[0], reference[1] + perpendicular[1]),
        reference_pixel=reference,
        reference_y_mm=-4.8,
        axis_vector_px_per_mm=vector,
    )
    assert result["measured_y_mm"] == pytest.approx(-4.8, abs=1e-9)
    assert abs(result["cross_axis_px"]) > 10.0


def test_template_matching_recovers_subpixel_axis_translation():
    module = _load(BED_Y_PATH, "vision_bed_y_match_test")
    image = _textured_image()
    x, y, width, height = 210, 190, 180, 100
    template = image[y : y + height, x : x + width]
    transform = np.float32([[1.0, 0.0, -1.35], [0.0, 1.0, -31.7]])
    shifted = cv2.warpAffine(
        image,
        transform,
        (image.shape[1], image.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )
    reference_anchor = (x + width / 2.0, y + height / 2.0)
    vector = (-0.45, -10.55)
    match = module.match_template(
        image=shifted,
        template_image=template,
        expected_anchor_px=reference_anchor,
        axis_vector_px_per_mm=vector,
        feature_mode="gray_norm",
        search_radius_mm=5.0,
        cross_axis_margin_px=8.0,
    )
    assert match["correlation"] > 0.8
    assert match["anchor_px"][0] == pytest.approx(reference_anchor[0] - 1.35, abs=0.35)
    assert match["anchor_px"][1] == pytest.approx(reference_anchor[1] - 31.7, abs=0.35)


def test_full_frame_template_matching_bootstraps_after_camera_translation():
    module = _load(BED_Y_PATH, "vision_bed_y_full_match_test")
    image = _textured_image()
    template = image[190:290, 230:410]
    shifted = cv2.warpAffine(
        image,
        np.float32([[1.0, 0.0, -3.0], [0.0, 1.0, -53.0]]),
        (image.shape[1], image.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )

    match = module.match_template_full_image(
        image=shifted,
        template_image=template,
        feature_mode="gray_norm",
    )

    assert match["correlation"] > 0.95
    assert match["anchor_px"][0] == pytest.approx(317.0, abs=0.4)
    assert match["anchor_px"][1] == pytest.approx(187.0, abs=0.4)
    assert match["search_boundary_hit"] is False


def _load_capture(monkeypatch, tmp_path):
    output = tmp_path / "vision" / "nozzle_cam"
    framebuffer = tmp_path / "framebuffer"
    framebuffer.mkdir(parents=True)
    monkeypatch.setenv("VISION_OUTPUT_DIR", str(output))
    monkeypatch.setenv("VISION_FRAMEBUFFER_DIR", str(framebuffer))
    monkeypatch.setenv("VISION_JOB_ROOT", str(output / "jobs"))
    monkeypatch.setenv("VISION_BED_Y_CHECK_ROOT", str(output / "bed_y_checks"))
    monkeypatch.setenv("VISIOND_SOCKET_ENABLED", "0")
    return _load(CAPTURE_PATH, f"vision_capture_bed_y_{tmp_path.name}")


def _measurement_params(template_path: Path, *, width=640, height=480):
    return {
        "camera": "nozzle_cam",
        "profile": "analysis",
        "image_width": width,
        "image_height": height,
        "reference_y_mm": -4.8,
        "reference_pixel_x": 320.0,
        "reference_pixel_y": 240.0,
        "axis_vector_x": -0.25,
        "axis_vector_y": -10.5,
        "template_path": str(template_path),
        "template_sha256": hashlib.sha256(template_path.read_bytes()).hexdigest(),
        "template_width": 180,
        "template_height": 100,
        "feature_mode": "gray_norm",
        "min_correlation": 0.95,
        "max_cross_axis_px": 3.0,
        "search_radius_mm": 5.0,
        "expected_y_mm": -4.8,
        "tolerance_mm": 0.25,
        "confirm": 1,
        "run": "test",
        "step": 0,
        "homed_axes": "xyz",
    }


def test_runtime_rejects_template_hash_and_frame_resolution(monkeypatch, tmp_path):
    module = _load_capture(monkeypatch, tmp_path)
    image = _textured_image()
    template_path = tmp_path / "template.png"
    cv2.imwrite(str(template_path), image[190:290, 230:410])
    params = _measurement_params(template_path)
    api = module.VisionJobApi(job_root=tmp_path / "jobs", request_timeout=0.2)

    with pytest.raises(module.CaptureError, match="template hash mismatch"):
        api._measure_bed_y_attempt({**params, "template_sha256": "0" * 64}, attempt=1)

    frame_path = tmp_path / "frame.jpg"
    cv2.imwrite(str(frame_path), image)
    monkeypatch.setattr(module, "read_framebuffer_metadata", lambda: {"frame_seq": 1})
    monkeypatch.setattr(
        module,
        "wait_for_buffered_frame_seq_after",
        lambda **_kwargs: (
            frame_path,
            {"frame_seq": 2, "width": image.shape[1], "height": image.shape[0]},
        ),
    )
    with pytest.raises(module.CaptureError, match="frame dimensions"):
        api._measure_bed_y_attempt({**params, "image_width": 1920}, attempt=1)


def test_runtime_quality_rejects_cross_axis_shift_and_low_correlation(
    monkeypatch, tmp_path
):
    module = _load_capture(monkeypatch, tmp_path)
    image = _textured_image()
    template_path = tmp_path / "template.png"
    cv2.imwrite(str(template_path), image[190:290, 230:410])
    params = _measurement_params(template_path)
    api = module.VisionJobApi(job_root=tmp_path / "jobs", request_timeout=0.2)
    monkeypatch.setattr(module, "read_framebuffer_metadata", lambda: {"frame_seq": 1})

    shifted = cv2.warpAffine(
        image,
        np.float32([[1.0, 0.0, 5.0], [0.0, 1.0, 0.0]]),
        (image.shape[1], image.shape[0]),
        borderMode=cv2.BORDER_REFLECT,
    )
    shifted_path = tmp_path / "shifted.jpg"
    cv2.imwrite(str(shifted_path), shifted)
    monkeypatch.setattr(
        module,
        "wait_for_buffered_frame_seq_after",
        lambda **_kwargs: (shifted_path, {"frame_seq": 2}),
    )
    shifted_result = api._measure_bed_y_attempt(params, attempt=1)
    assert shifted_result["correlation"] > 0.95
    assert shifted_result["quality_ok"] is False
    assert abs(shifted_result["cross_axis_px"]) > 3.0

    unrelated = np.random.default_rng(999).integers(
        0, 255, size=image.shape, dtype=np.uint8
    )
    unrelated_path = tmp_path / "unrelated.jpg"
    cv2.imwrite(str(unrelated_path), unrelated)
    monkeypatch.setattr(
        module,
        "wait_for_buffered_frame_seq_after",
        lambda **_kwargs: (unrelated_path, {"frame_seq": 3}),
    )
    unrelated_result = api._measure_bed_y_attempt(params, attempt=1)
    assert unrelated_result["correlation"] < 0.95
    assert unrelated_result["quality_ok"] is False


def test_runtime_confirms_suspicious_measurement_and_writes_summary(
    monkeypatch, tmp_path
):
    module = _load_capture(monkeypatch, tmp_path)
    api = module.VisionJobApi(job_root=tmp_path / "jobs", request_timeout=0.2)
    template_path = tmp_path / "template.png"
    cv2.imwrite(str(template_path), _textured_image()[190:290, 230:410])
    params = _measurement_params(template_path)
    attempts = iter(
        [
            {
                "attempt": 1,
                "accepted": False,
                "measured_y_mm": -4.4,
                "expected_y_mm": -4.8,
                "error_mm": 0.4,
                "correlation": 0.99,
                "cross_axis_px": 0.1,
                "failure_reason": "Y error",
                "_image_bytes": b"first",
            },
            {
                "attempt": 2,
                "accepted": True,
                "measured_y_mm": -4.79,
                "expected_y_mm": -4.8,
                "error_mm": 0.01,
                "correlation": 0.99,
                "cross_axis_px": 0.1,
                "failure_reason": "",
                "_image_bytes": b"second",
            },
        ]
    )
    monkeypatch.setattr(
        api, "_measure_bed_y_attempt", lambda *_args, **_kwargs: next(attempts)
    )
    result = api.measure_bed_y(params)
    assert result["accepted"] is True
    assert result["retry_used"] is True
    assert result["confirmation_count"] == 1
    summary = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))
    assert summary["measurement_count"] == 1
    assert summary["accepted_count"] == 1
    assert summary["retry_count"] == 1


def test_run_local_reference_validates_one_mm_and_uses_live_vector(
    monkeypatch, tmp_path
):
    module = _load_capture(monkeypatch, tmp_path)
    api = module.VisionJobApi(job_root=tmp_path / "jobs", request_timeout=0.2)
    original = _textured_image()
    template_path = tmp_path / "template.png"
    cv2.imwrite(str(template_path), original[190:290, 230:410])
    params = _measurement_params(template_path)
    params.update(
        {
            "run": "dynamic_reference",
            "run_reference_y_mm": -4.8,
            "confirm": 0,
        }
    )

    baseline = cv2.warpAffine(
        original,
        np.float32([[1.0, 0.0, -3.0], [0.0, 1.0, -53.0]]),
        (original.shape[1], original.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )
    validation = cv2.warpAffine(
        baseline,
        np.float32([[1.0, 0.0, 0.0], [0.0, 1.0, 10.0]]),
        (original.shape[1], original.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )
    frame_paths = []
    for name, image in (
        ("baseline", baseline),
        ("validation", validation),
        ("return", baseline),
    ):
        frame_path = tmp_path / f"{name}.jpg"
        cv2.imwrite(str(frame_path), image)
        frame_paths.append(frame_path)
    frames = iter(
        (path, {"frame_seq": index + 2}) for index, path in enumerate(frame_paths)
    )
    monkeypatch.setattr(module, "read_framebuffer_metadata", lambda: {"frame_seq": 1})
    monkeypatch.setattr(
        module,
        "wait_for_buffered_frame_seq_after",
        lambda **_kwargs: next(frames),
    )

    reference = api.bed_y_reference(params)
    assert reference["bootstrap_correlation"] > 0.95
    assert reference["validated"] is False
    session_params = {
        **params,
        "session_id": reference["session_id"],
        "expected_delta_mm": -1.0,
        "tolerance_mm": 0.1,
        "phase": "startup_validation",
    }
    validation_result = api.validate_bed_y_reference(session_params)
    assert validation_result["accepted"] is True, validation_result
    assert validation_result["measured_delta_mm"] == pytest.approx(-1.0, abs=0.1)
    assert validation_result["live_axis_vector_px_per_mm"][0] == pytest.approx(
        -0.25, abs=0.5
    )
    assert validation_result["live_axis_vector_px_per_mm"][1] == pytest.approx(
        -10.5, abs=0.6
    )

    return_result = api.measure_bed_y_relative(
        {
            **session_params,
            "expected_delta_mm": 0.0,
            "phase": "startup_return",
        }
    )
    assert return_result["accepted"] is True, return_result
    assert return_result["error_mm"] == pytest.approx(0.0, abs=0.1)
    assert return_result["session_id"] == reference["session_id"]
    assert Path(return_result["summary_path"]).parent.name == reference["session_id"]


def test_bed_y_calibration_import_writes_valid_yaml_and_template(tmp_path):
    apply = _load(APPLY_PATH, "apply_bed_y_calibration_test")
    generator = _load(GENERATOR_PATH, "generate_bed_y_calibration_test")
    job_dir = tmp_path / "job"
    analysis_dir = job_dir / "analysis"
    frames_dir = job_dir / "frames"
    analysis_dir.mkdir(parents=True)
    frames_dir.mkdir()
    image = _textured_image()
    source_image = frames_dir / "bed_y_10p0.jpg"
    cv2.imwrite(str(source_image), image)
    source_hash = "sha256:" + hashlib.sha256(source_image.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "job_id": "fresh_bed_y",
        "camera": "nozzle_cam",
        "profile": "analysis",
        "kind": "nozzle_cam_bed_y_sweep",
        "manifest_hash": "sha256:PLACEHOLDER",
        "frames": [
            {
                "frame": "bed_y_10p0",
                "y_offset": 10.0,
                "pose": {"x": -80.4, "y": -4.8, "z": 293.75},
            }
        ],
    }
    manifest["manifest_hash"] = apply._compute_manifest_hash(manifest)
    (job_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (frames_dir / "bed_y_10p0.json").write_text(
        json.dumps(
            {
                "job_id": "fresh_bed_y",
                "frame": "bed_y_10p0",
                "camera": "nozzle_cam",
                "profile": "analysis",
                "image_sha256": source_hash,
                "width": 640,
                "height": 480,
            }
        ),
        encoding="utf-8",
    )
    payload = {
        "ok": True,
        "accepted": True,
        "measurement": "nozzle_cam_bed_y_motion",
        "camera": "nozzle_cam",
        "profile": "analysis",
        "job_id": "fresh_bed_y",
        "manifest_hash": manifest["manifest_hash"],
        "calibration_candidate": {
            "reference_y_offset_mm": 10.0,
            "reference_printer_y_mm": -4.8,
            "reference_pixel_px": [320.0, 240.0],
            "template_roi_px": [230.0, 190.0, 180.0, 100.0],
            "image_size_px": {"width": 640, "height": 480},
            "source_frame": "bed_y_10p0",
            "source_image_sha256": source_hash,
            "feature_mode": "gray_norm",
            "selected_roi": "marked_line_tight",
            "axis_vector_px_per_mm": [-0.25, -10.5],
            "fit_residual_rms_px": 0.2,
            "correlation_min": 0.99,
            "correlation_median": 0.995,
            "capture_pose": {"x": -80.4, "y": -4.8, "z": 293.75},
        },
    }
    facts_path = analysis_dir / "facts.json"
    facts_path.write_text(json.dumps(payload), encoding="utf-8")
    calib_path = tmp_path / "calib.yaml"
    calib_path.write_text(
        """bed_grid_zero:
  x: 113.3
  y: 107.0
tools:
  t0:
    x_endstop: -80.4
    y_endstop: -14.8
    z_endstop: 293.75
  t1:
    x_endstop: 357.532
    y_endstop: -15.82
    z_endstop: 293.65
""",
        encoding="utf-8",
    )
    measurement = apply.extract_measurement(payload, str(facts_path))
    mapping, template_path, template_sha = apply.build_bed_y_calibration(
        measurement,
        calib_path=calib_path,
        dry_run=False,
        reference_y_offset_mm=10.0,
    )
    calib = apply.load_calib(calib_path)
    calib.setdefault("cameras", {})["nozzle_cam"] = mapping
    apply.write_calib(calib_path, calib)

    assert template_path.is_file()
    assert hashlib.sha256(template_path.read_bytes()).hexdigest() == template_sha
    loaded = generator.load_calibration(calib_path)
    assert loaded["nozzle_cam"]["reference_y"] == pytest.approx(-4.8)
    assert loaded["nozzle_cam"]["axis_vector_y"] == pytest.approx(-10.5)
    assert loaded["nozzle_cam"]["template_width"] == 180

    manifest["frames"][0]["pose"]["y"] = -4.7
    (job_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest content hash mismatch"):
        apply.build_bed_y_calibration(
            measurement,
            calib_path=calib_path,
            dry_run=True,
            reference_y_offset_mm=10.0,
        )

    template_path.write_bytes(template_path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="template hash mismatch"):
        generator.load_calibration(calib_path)


def test_bed_y_calibration_import_rejects_incomplete_candidate():
    apply = _load(APPLY_PATH, "apply_bed_y_incomplete_test")
    with pytest.raises(ValueError, match="axis_vector_px_per_mm"):
        apply.extract_measurement(
            {
                "ok": True,
                "accepted": True,
                "measurement": "nozzle_cam_bed_y_motion",
                "calibration_candidate": {},
            },
            "facts.json",
        )
