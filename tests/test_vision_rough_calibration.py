import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)
ROUGH_PATH = FILES / "vision_rough_calibration.py"
VISION_PATH = FILES / "vision_nozzle_align.py"
CALIB_PATH = ROOT / "klipper_setup" / "klipper_config" / "calib.yaml"
CONFIG_PATH = ROOT / "klipper_setup" / "klipper_config" / "printer.cfg"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fit(jacobian, intercept):
    return {
        "ok": True,
        "jacobian": jacobian,
        "intercept": intercept,
        "fit_rms": 0.1,
        "condition_number": 2.0,
    }


def test_solve_recovers_endstop_correction_sign_and_rejects_bad_geometry():
    np = pytest.importorskip("numpy")
    rough = _load(ROUGH_PATH, "rough_correction_test")
    jacobian = np.asarray(
        [[8.0, 0.2, 0.5], [0.1, -8.0, 1.0], [0.01, 0.03, -5.0]]
    )
    correction = np.asarray([-10.0, 0.7, -0.3])
    t0 = _fit(jacobian.tolist(), [20.0, 30.0, 40.0])
    t1 = _fit(
        jacobian.tolist(),
        (np.asarray(t0["intercept"]) + jacobian @ correction).tolist(),
    )

    result = rough.solve_pass_correction(t0, t1)

    assert result["ok"] is True
    assert result["correction_mm"]["x"] == pytest.approx(-10.0)
    assert result["correction_mm"]["y"] == pytest.approx(0.7)
    assert result["correction_mm"]["z"] == pytest.approx(-0.3)

    incompatible = _fit((jacobian * [1.5, 1.0, 1.0]).tolist(), t1["intercept"])
    assert rough.solve_pass_correction(t0, incompatible)["ok"] is False

    singular = _fit([[8, 0, 0], [0, 8, 0], [0, 0, 0]], t1["intercept"])
    rejected = rough.solve_pass_correction(singular, singular)
    assert rejected["ok"] is False
    assert "singular" in "; ".join(rejected["hard_failures"]).lower()


def test_nozzle_detector_accepts_ring_and_orifice_and_rejects_ambiguity():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    rough = _load(ROUGH_PATH, "rough_detector_test")

    image = np.full((1080, 1920, 3), 35, dtype=np.uint8)
    cv2.rectangle(image, (986, 370), (1014, 440), (0, 0, 255), -1)
    cv2.circle(image, (1035, 510), 72, (220, 220, 220), 4)
    cv2.circle(image, (1035, 510), 10, (245, 245, 245), 3)
    accepted = rough.detect_nozzle_observation(image)
    assert accepted["accepted"] is True
    assert accepted["center_px"] == pytest.approx([1035, 510], abs=2)

    missing = rough.detect_nozzle_observation(np.zeros_like(image))
    assert missing["accepted"] is False

    ambiguous = np.full((1080, 1920, 3), 35, dtype=np.uint8)
    cv2.rectangle(ambiguous, (986, 370), (1014, 440), (0, 0, 255), -1)
    for center_x in (1020, 1050):
        cv2.circle(ambiguous, (center_x, 510), 60, (220, 220, 220), 4)
        cv2.circle(ambiguous, (center_x, 510), 10, (245, 245, 245), 3)
    rejected = rough.detect_nozzle_observation(ambiguous)
    assert rejected["accepted"] is False
    assert rejected["rejection_reason"] == "ambiguous nozzle-face rings"


def test_tool_local_visibility_gate_excludes_hidden_or_displaced_nozzle():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    rough = _load(ROUGH_PATH, "rough_visibility_gate_test")

    center = (1035, 510)
    radius = 62
    visible = np.full((1080, 1920, 3), 35, dtype=np.uint8)
    cv2.circle(visible, center, radius, (220, 220, 220), 4)
    cv2.circle(visible, center, 10, (245, 245, 245), 3)
    accepted = rough.detect_nozzle_observation(
        visible,
        expected_center_px=center,
        expected_radius_px=radius,
    )
    assert accepted["accepted"] is True

    displaced = np.full_like(visible, 35)
    displaced_center = (center[0] + 45, center[1])
    cv2.circle(displaced, displaced_center, radius, (220, 220, 220), 4)
    cv2.circle(displaced, displaced_center, 10, (245, 245, 245), 3)
    rejected = rough.detect_nozzle_observation(
        displaced,
        expected_center_px=center,
        expected_radius_px=radius,
    )
    assert rejected["accepted"] is False
    assert rejected["exclusion_reason"] == "nozzle_not_visible"

    hidden = visible.copy()
    cv2.rectangle(hidden, (970, 475), (1100, 575), (35, 35, 35), -1)
    rejected = rough.detect_nozzle_observation(
        hidden,
        expected_center_px=center,
        expected_radius_px=radius,
    )
    assert rejected["accepted"] is False
    assert rejected["exclusion_reason"] == "nozzle_not_visible"


def test_tight_roi_template_tracks_relative_motion_and_rejects_hidden_frame():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    rough = _load(ROUGH_PATH, "rough_relative_template_test")

    center = (1035, 510)
    image = np.full((1080, 1920, 3), 35, dtype=np.uint8)
    cv2.circle(image, center, 60, (220, 220, 220), 5)
    cv2.circle(image, center, 38, (120, 120, 120), 3)
    cv2.circle(image, center, 10, (245, 245, 245), 3)
    cv2.line(image, (995, 510), (1075, 510), (180, 180, 180), 2)
    cv2.line(image, (1035, 470), (1035, 550), (180, 180, 180), 2)
    template = rough.make_nozzle_tracking_template(image, center)

    shifted = cv2.warpAffine(
        image,
        np.float32([[1, 0, 8], [0, 1, -3]]),
        (1920, 1080),
        borderValue=(35, 35, 35),
    )
    tracked = rough.track_nozzle_template(
        shifted,
        template,
        (1043, 507),
        minimum_correlation=0.80,
        maximum_center_error_px=10,
    )
    assert tracked["accepted"] is True
    assert tracked["center_px"] == pytest.approx([1043, 507], abs=0.05)
    assert tracked["correlation"] > 0.99

    hidden = shifted.copy()
    cv2.rectangle(hidden, (975, 445), (1110, 575), (35, 35, 35), -1)
    rejected = rough.track_nozzle_template(
        hidden,
        template,
        (1043, 507),
        minimum_correlation=0.80,
        maximum_center_error_px=10,
    )
    assert rejected["accepted"] is False
    assert "correlation" in rejected["rejection_reason"]


def test_relative_template_motion_gate_rejects_trajectory_outlier():
    vision = _load(VISION_PATH, "rough_relative_trajectory_test")
    samples = []
    for index, x in enumerate((-6, -3, 0, 3, 6, 9)):
        center = [1000 + 9 * x, 500.0]
        if x == 9:
            center = [900.0, 560.0]
        samples.append(
            {
                "prefix": f"frame_{index}",
                "pose": {"x": x},
                "detection": {"center_px": center},
            }
        )

    result = vision._rough_motion_gate(samples)

    assert result["ok"] is True
    assert result["accepted_count"] == 5
    assert result["outlier_prefixes"] == ["frame_5"]
    assert result["axis_magnitude_px_per_mm"] == pytest.approx(9.0)


def test_rough_job_motion_is_center_out_hashed_cold_and_never_below_z1(tmp_path):
    vision = _load(VISION_PATH, "rough_job_generation_test")
    summary = vision.prepare_rough_relative_vision_job(
        SimpleNamespace(
            name="rough",
            job_root=tmp_path / "jobs",
            job_id="rough_job",
            t0_anchor_x=185.0,
            t1_anchor_x=195.0,
            anchor_y=-14.0,
            anchor_z=3.0,
            rough_travel_z=5.0,
            current_t1_x_endstop=357.532,
            current_t1_y_endstop=-15.820,
            current_t1_z_endstop=293.650,
            mode="MEASURE",
            source_calib=CALIB_PATH,
            active_config_fingerprint="fingerprint",
            feedrate=3600.0,
            settle_time=0.1,
            camera="nozzle_cam",
            profile="analysis",
        )
    )
    manifest = json.loads(Path(summary["manifest_path"]).read_text())
    gcode = Path(summary["gcode_path"]).read_text()

    assert manifest["kind"] == vision.ROUGH_RELATIVE_JOB_KIND
    assert manifest["frame_count"] == 116
    assert manifest["preconditions"]["require_heaters_off"] is True
    assert manifest["measurement_parameters"]["source_calib_sha256"].startswith(
        "sha256:"
    )
    first_search = [
        frame
        for frame in manifest["frames"]
        if frame["pass_index"] == 1
        and frame["tool"] == "T0"
        and frame["role"] == "search"
    ]
    assert [frame["sample_value"] for frame in first_search] == [
        0,
        -3,
        3,
        -6,
        6,
        -9,
        9,
        -12,
        12,
        -15,
        15,
        -18,
        18,
    ]
    assert min(frame["pose"]["z"] for frame in manifest["frames"]) >= 1.0
    assert "G1 Z5.000" in gcode
    assert "G1 Z0." not in gcode
    assert "G28" not in gcode
    assert "SAVE_CONFIG" not in gcode


def test_complete_yaml_candidate_preserves_unrelated_sections(tmp_path):
    rough = _load(ROUGH_PATH, "rough_yaml_candidate_test")
    source = tmp_path / "calib.yaml"
    source_payload = {
        "bed_grid_zero": {"x": 1, "y": 2},
        "tools": {
            "t0": {"x_endstop": -1, "y_endstop": -2, "z_endstop": 3},
            "t1": {"x_endstop": 10, "y_endstop": 20, "z_endstop": 30},
        },
        "cameras": {"nozzle_cam": {"keep": {"nested": [1, 2, 3]}}},
        "eddy_relative_calibration": {"keep": True},
    }
    source.write_text(yaml.safe_dump(source_payload, sort_keys=False))

    result = rough.write_calib_candidate(
        source_path=source,
        destination=tmp_path / "candidate.yaml",
        correction_mm={"x": -5.25, "y": 0.5, "z": -0.125},
    )
    candidate = yaml.safe_load(Path(result["candidate_path"]).read_text())

    assert candidate["tools"]["t0"] == source_payload["tools"]["t0"]
    assert candidate["tools"]["t1"] == {
        "x_endstop": 4.75,
        "y_endstop": 20.5,
        "z_endstop": 29.875,
    }
    assert candidate["bed_grid_zero"] == source_payload["bed_grid_zero"]
    assert candidate["cameras"] == source_payload["cameras"]
    assert (
        candidate["eddy_relative_calibration"]
        == source_payload["eddy_relative_calibration"]
    )


def test_lighting_duplicate_quality_and_macro_report_only_contract():
    rough = _load(ROUGH_PATH, "rough_lighting_quality_test")
    good = [
        {
            "accepted": True,
            "center_px": [100.0 + index * 0.05, 200.0],
            "score": 100.0 + index,
            "clipped_fraction": 0.001,
        }
        for index in range(5)
    ]
    correlated = rough.validate_lighting_duplicates(
        good, correlations=[1.0, 0.99, 0.98, 0.99, 0.98]
    )
    assert correlated["ok"] is True
    assert correlated["correlation_min"] == pytest.approx(0.98)
    unstable = [dict(item) for item in good]
    unstable[-1]["center_px"] = [103.0, 200.0]
    assert rough.validate_lighting_duplicates(unstable)["ok"] is False
    assert (
        rough.validate_lighting_duplicates(
            good, correlations=[1.0, 0.99, 0.98, 0.99, 0.70]
        )["ok"]
        is False
    )

    config = CONFIG_PATH.read_text()
    rough_macro = config.split(
        "[gcode_macro IDEX_NOZZLE_ROUGH_CALIBRATE]", 1
    )[1].split("[gcode_macro", 1)[0]
    lighting_macro = config.split(
        "[gcode_macro IDEX_EDDY_VISION_LIGHT_SWEEP]", 1
    )[1].split("[thermistor", 1)[0]
    for macro in (rough_macro, lighting_macro):
        assert "heater targets to be zero" in macro
        assert "requires X/Y/Z homed" in macro
        assert "SAVE_CONFIG" not in macro
    assert "MODE must be MEASURE or VERIFY" in rough_macro
    assert "eddy_anchor_z=3.0" in lighting_macro


def test_eddy_lighting_scorer_tracks_only_the_fixed_fiducial_roi():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    rough = _load(ROUGH_PATH, "rough_eddy_lighting_detector_test")

    image = np.full((1080, 1920, 3), 35, dtype=np.uint8)
    center = rough.EDDY_LIGHT_EXPECTED_CENTER_1080
    for radius in rough.EDDY_LIGHT_RING_RADII_1080:
        cv2.circle(image, center, radius, (190, 190, 190), 2)
    cv2.line(
        image,
        (center[0] - 7, center[1]),
        (center[0] + 7, center[1]),
        (220, 220, 220),
        2,
    )
    cv2.line(
        image,
        (center[0], center[1] - 7),
        (center[0], center[1] + 7),
        (220, 220, 220),
        2,
    )
    accepted = rough.score_eddy_lighting(image)
    assert accepted["accepted"] is True
    assert accepted["ring_count"] >= 3
    assert accepted["center_px"] == pytest.approx(center, abs=1)

    missing = rough.score_eddy_lighting(np.full_like(image, 35))
    assert missing["accepted"] is False

    clipped = image.copy()
    x, y, width, height = rough.EDDY_LIGHT_ROI_1080
    clipped[y : y + height, x : x + width] = 255
    assert rough.score_eddy_lighting(clipped)["accepted"] is False
