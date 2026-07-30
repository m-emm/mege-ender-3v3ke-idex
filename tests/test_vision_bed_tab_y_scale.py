import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
    / "vision_bed_tab_y_scale.py"
)


def _load():
    files = str(MODULE_PATH.parent)
    if files not in sys.path:
        sys.path.insert(0, files)
    spec = importlib.util.spec_from_file_location("bed_tab_y_scale_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic_frames(
    tmp_path,
    *,
    vector=(2.0, -6.0),
    reverse_vector=None,
    randomize=False,
    clipped=False,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260730)
    height, width = 540, 960
    texture = np.zeros((height, width, 3), dtype=np.uint8)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.rectangle(mask, (170, 145), (790, 440), 255, -1)
    texture[:] = (35, 35, 35)
    for _index in range(700):
        x = int(rng.integers(180, 780))
        y = int(rng.integers(155, 430))
        radius = int(rng.integers(2, 8))
        value = int(rng.integers(55, 235))
        cv2.circle(texture, (x, y), radius, (value, value, value), -1)
    cv2.line(texture, (180, 300), (770, 260), (245, 245, 245), 5)
    cv2.rectangle(texture, (260, 190), (680, 390), (130, 130, 130), 4)

    offsets = [0, 5, 10, 15, 20, 15, 10, 5, 0]
    paths = []
    for index, offset in enumerate(offsets):
        background = np.full((height, width, 3), 18, dtype=np.uint8)
        cv2.rectangle(background, (20, 20), (940, 520), (75, 75, 75), 7)
        cv2.putText(
            background,
            "STATIONARY ENCLOSURE",
            (280, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (150, 150, 150),
            2,
        )
        if clipped:
            image = np.full_like(background, 255)
        elif randomize:
            image = rng.integers(0, 255, background.shape, dtype=np.uint8)
        else:
            active_vector = (
                reverse_vector if reverse_vector is not None and index >= 5 else vector
            )
            matrix = np.float32(
                [
                    [1.0, 0.0, active_vector[0] * offset],
                    [0.0, 1.0, active_vector[1] * offset],
                ]
            )
            moved_texture = cv2.warpAffine(
                texture, matrix, (width, height), borderValue=(0, 0, 0)
            )
            moved_mask = cv2.warpAffine(mask, matrix, (width, height))
            image = background
            image[moved_mask > 0] = moved_texture[moved_mask > 0]
        path = tmp_path / f"frame_{index}.jpg"
        assert cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 98])
        paths.append(path)
    return paths


def test_recovers_known_two_dimensional_vector_and_direction(tmp_path):
    module = _load()
    expected = np.asarray([2.0, -6.0])
    result = module.analyze(
        _synthetic_frames(tmp_path),
        tmp_path / "analysis",
    )
    assert result["accepted"], result["reasons"]
    assert result["accepted_patch_count"] >= 3
    assert np.allclose(result["axis_vector_px_per_mm"], expected, atol=0.08)
    assert result["joint_residual_rms_px"] <= 0.75
    assert result["duplicate_position_disagreement_px"] <= 1.0
    assert result["median_correlation"] >= 0.90
    assert set(result["artifacts"]) == {
        "patch_selection",
        "contact_sheet",
        "displacement_vs_y",
        "forward_reverse",
    }


def test_registration_uses_two_consistent_representations():
    module = _load()
    rng = np.random.default_rng(17)
    reference = np.zeros((180, 240), dtype=np.uint8)
    patch = rng.integers(15, 240, (44, 56), dtype=np.uint8)
    rect = (80, 65, 136, 109)
    reference[65:109, 80:136] = patch

    agreeing_target = np.zeros_like(reference)
    agreeing_target[74:118, 92:148] = patch
    disagreeing_target = np.zeros_like(reference)
    disagreeing_target[30:74, 25:81] = patch
    position, correlation, spread, error = module._match_patch(
        {
            "gray": reference,
            "clahe": reference,
            "gradient": reference,
        },
        {
            "gray": agreeing_target,
            "clahe": agreeing_target,
            "gradient": disagreeing_target,
        },
        rect,
        90,
    )

    assert error is None
    assert correlation >= 0.99
    assert spread <= 0.1
    assert np.allclose(position, (120.0, 96.0), atol=0.1)


def test_rejects_stationary_background_dark_clipped_and_low_correlation(tmp_path):
    module = _load()
    stationary = module.analyze(
        _synthetic_frames(tmp_path / "stationary", vector=(0.0, 0.0)),
        tmp_path / "stationary_analysis",
    )
    assert not stationary["accepted"]
    assert any(
        "stationary" in reason or "scale" in reason for reason in stationary["reasons"]
    )
    json.dumps(stationary, allow_nan=False)

    clipped = module.analyze(
        _synthetic_frames(tmp_path / "clipped", clipped=True),
        tmp_path / "clipped_analysis",
    )
    assert not clipped["accepted"]
    assert clipped["accepted_patch_count"] == 0
    json.dumps(clipped, allow_nan=False)

    random_result = module.analyze(
        _synthetic_frames(tmp_path / "random", randomize=True),
        tmp_path / "random_analysis",
    )
    assert not random_result["accepted"]
    assert any(
        "correlation" in reason or "patch" in reason
        for reason in random_result["reasons"]
    )
    json.dumps(random_result, allow_nan=False)


def test_rejects_missing_frames_insufficient_span_and_direction_disagreement(
    tmp_path,
):
    module = _load()
    missing = _synthetic_frames(tmp_path / "missing")
    for index in (1, 3, 6):
        missing[index].unlink()
    missing_result = module.analyze(missing, tmp_path / "missing_analysis")
    assert not missing_result["accepted"]
    assert "fewer than seven usable frames" in missing_result["reasons"]
    json.dumps(missing_result, allow_nan=False)

    short = module.analyze(
        _synthetic_frames(tmp_path / "short", vector=(10.0, -3.0)),
        tmp_path / "short_analysis",
        offsets_mm=[0, 1, 2, 3, 4, 3, 2, 1, 0],
    )
    assert not short["accepted"]
    assert "commanded span is below 15 mm" in short["reasons"]

    direction = module.analyze(
        _synthetic_frames(
            tmp_path / "direction",
            vector=(2.0, -6.0),
            reverse_vector=(3.0, -5.0),
        ),
        tmp_path / "direction_analysis",
    )
    assert not direction["accepted"]
    assert any("forward/reverse" in reason for reason in direction["reasons"])


def test_ambiguous_equal_patch_vector_clusters_are_rejected():
    module = _load()

    def track(index, slope):
        return module.PatchTrack(
            patch_id=f"p{index}",
            rect=(0, 0, 20, 20),
            positions=[(0.0, 0.0)] * 9,
            correlations=[0.99] * 9,
            representation_spread_px=[0.0] * 9,
            slope=slope,
            residual_rms_px=0.0,
        )

    selected, error = module._cluster_tracks(
        [
            track(0, (2.0, -6.0)),
            track(1, (2.05, -6.02)),
            track(2, (-5.0, 4.0)),
            track(3, (-5.03, 3.98)),
        ]
    )
    assert selected == []
    assert "ambiguous" in error
