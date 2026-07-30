import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest


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
    width=960,
    height=540,
    vector=(0.8, -6.0),
    reverse_vector=None,
    reverse_bias=(0.0, 0.0),
    translation=(0.0, 0.0),
    randomize=False,
    clipped=False,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    scale_x = width / 960.0
    scale_y = height / 540.0
    offsets = [0, 10, 20, 20, 10, 0]
    rng = np.random.default_rng(44)
    texture = [
        (
            float(rng.uniform(0.05, 0.95)),
            float(rng.uniform(0.08, 0.92)),
            int(rng.integers(50, 190)),
        )
        for _index in range(250)
    ]
    paths = []
    for index, offset in enumerate(offsets):
        if clipped:
            image = np.full((height, width, 3), 255, dtype=np.uint8)
        elif randomize:
            image = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
        else:
            image = np.full((height, width, 3), 25, dtype=np.uint8)
            # Long, strong, stationary enclosure lines must not win.
            cv2.rectangle(
                image,
                (int(0.02 * width), int(0.03 * height)),
                (int(0.98 * width), int(0.97 * height)),
                (70, 70, 70),
                max(2, int(round(5 * scale_x))),
            )
            cv2.line(
                image,
                (int(0.07 * width), int(0.18 * height)),
                (int(0.93 * width), int(0.18 * height)),
                (125, 125, 125),
                max(2, int(round(4 * scale_y))),
            )
            active_vector = (
                reverse_vector if reverse_vector is not None and index >= 3 else vector
            )
            bias = reverse_bias if index >= 3 else (0.0, 0.0)
            dx = (active_vector[0] * offset + bias[0] + translation[0]) * scale_x
            dy = (active_vector[1] * offset + bias[1] + translation[1]) * scale_y

            # The tab has a long top edge, textured body, a stronger but shorter
            # lower reflection, and a cable-like sloped feature.
            polygon = np.asarray(
                [[210, 260], [700, 260], [780, 420], [260, 420]],
                dtype=float,
            )
            polygon[:, 0] = polygon[:, 0] * scale_x + dx
            polygon[:, 1] = polygon[:, 1] * scale_y + dy
            cv2.fillPoly(
                image,
                [np.round(polygon).astype(np.int32)],
                (70, 70, 70),
            )
            for fraction_x, fraction_y, value in texture:
                x = (230 + fraction_x * 500) * scale_x + dx
                y = (275 + fraction_y * 125) * scale_y + dy
                cv2.circle(
                    image,
                    (round(x), round(y)),
                    max(1, round(2 * scale_x)),
                    (value, value, value),
                    -1,
                )
            cv2.line(
                image,
                (round(220 * scale_x + dx), round(260 * scale_y + dy)),
                (round(690 * scale_x + dx), round(260 * scale_y + dy)),
                (235, 235, 235),
                max(3, round(5 * scale_y)),
            )
            cv2.line(
                image,
                (round(340 * scale_x + dx), round(382 * scale_y + dy)),
                (round(600 * scale_x + dx), round(382 * scale_y + dy)),
                (255, 255, 255),
                max(3, round(7 * scale_y)),
            )
            cv2.line(
                image,
                (round(290 * scale_x + dx), round(300 * scale_y + dy)),
                (round(690 * scale_x + dx), round(330 * scale_y + dy)),
                (180, 180, 180),
                max(2, round(4 * scale_y)),
            )
        path = tmp_path / f"frame_{index}.jpg"
        assert cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 98])
        paths.append(path)
    return paths


def test_discovers_tab_top_edge_and_recovers_known_vector(tmp_path):
    module = _load()
    result = module.analyze(
        _synthetic_frames(tmp_path),
        tmp_path / "analysis",
        localizer={"kind": "bed_tab_top_edge", "version": 1},
    )

    assert result["accepted"], result["reasons"]
    assert result["localizer"] == {
        "kind": "bed_tab_top_edge",
        "version": 1,
        "configured_position": None,
    }
    assert result["discovered_candidate_count"] >= 2
    assert result["selected_candidate_id"]
    assert result["observed_target"]["span_fraction"] >= 0.45
    assert result["observed_target"]["reference_tab_side"]["vertical_drop_px"] > 100
    lower_reflections = [
        candidate
        for candidate in result["candidates"]
        if candidate["reference_line_px"][1] > 350
    ]
    assert lower_reflections
    assert all(
        "missing descending bed-tab side geometry"
        in (candidate["rejection_reason"] or "")
        for candidate in lower_reflections
    )
    assert np.allclose(result["axis_vector_px_per_mm"], [0.8, -6.0], atol=0.08)
    assert result["median_correlation"] >= 0.90
    assert set(result["artifacts"]) == {
        "edge_localization",
        "edge_tracking_overlay",
        "contact_sheet",
        "displacement_vs_y",
        "forward_reverse",
    }
    overlay = cv2.imread(
        result["artifacts"]["edge_tracking_overlay"]["path"],
        cv2.IMREAD_COLOR,
    )
    assert overlay is not None
    assert overlay.shape[:2] == (720, 1920)
    json.dumps(result, allow_nan=False)


def test_translation_and_resolution_do_not_require_position_configuration(tmp_path):
    module = _load()
    original = module.analyze(
        _synthetic_frames(tmp_path / "original"),
        tmp_path / "original_analysis",
    )
    scaled = module.analyze(
        _synthetic_frames(
            tmp_path / "scaled",
            width=640,
            height=360,
            translation=(80, 40),
        ),
        tmp_path / "scaled_analysis",
    )

    assert original["accepted"], original["reasons"]
    assert scaled["accepted"], scaled["reasons"]
    normalized_original = np.asarray(original["axis_vector_px_per_mm"]) / [960, 540]
    normalized_scaled = np.asarray(scaled["axis_vector_px_per_mm"]) / [640, 360]
    assert np.allclose(normalized_original, normalized_scaled, atol=0.0002)
    assert (
        original["observed_target"]["reference_line_px"]
        != scaled["observed_target"]["reference_line_px"]
    )


def test_line_clustering_uses_only_relative_geometry():
    module = _load()
    clusters = module._cluster_horizontal_segments(
        [
            {"x0": 100.0, "x1": 200.0, "y": 204.0, "length": 100.0},
            {"x0": 260.0, "x1": 430.0, "y": 200.0, "length": 170.0},
            {"x0": 205.0, "x1": 255.0, "y": 206.0, "length": 50.0},
            {"x0": 20.0, "x1": 80.0, "y": 400.0, "length": 60.0},
        ],
        (540, 960),
    )
    merged = next(cluster for cluster in clusters if cluster["x0"] == 100.0)
    assert merged["x1"] == 430.0
    assert merged["segment_count"] == 3


def test_stationary_missing_clipped_and_random_inputs_are_rejected(tmp_path):
    module = _load()
    stationary = module.analyze(
        _synthetic_frames(tmp_path / "stationary", vector=(0.0, 0.0)),
        tmp_path / "stationary_analysis",
    )
    assert not stationary["accepted"]

    missing = _synthetic_frames(tmp_path / "missing")
    missing[0].unlink()
    missing_result = module.analyze(missing, tmp_path / "missing_analysis")
    assert not missing_result["accepted"]
    assert "both zero-offset frames are required" in " ".join(missing_result["reasons"])

    for name, options in (
        ("clipped", {"clipped": True}),
        ("random", {"randomize": True}),
    ):
        result = module.analyze(
            _synthetic_frames(tmp_path / name, **options),
            tmp_path / f"{name}_analysis",
        )
        assert not result["accepted"]
        json.dumps(result, allow_nan=False)


def test_direction_disagreement_warns_but_does_not_discard_fit(tmp_path):
    module = _load()
    result = module.analyze(
        _synthetic_frames(
            tmp_path / "direction",
            vector=(0.8, -6.0),
            reverse_vector=(0.9, -5.6),
        ),
        tmp_path / "direction_analysis",
    )
    assert result["accepted"], result["reasons"]
    assert any("forward/reverse" in warning for warning in result["warnings"])


def test_equal_distinct_edge_candidates_are_ambiguous():
    module = _load()

    def candidate(identifier, y, span, rms):
        item = module.EdgeCandidate(
            candidate_id=identifier,
            reference_line=(100.0, y, 100.0 + span * 960),
            duplicate_line=(100.0, y, 100.0 + span * 960),
            strip_rect=(80, int(y - 30), 700, int(y + 30)),
            span_fraction=span,
            duplicate_y_delta_px=0.0,
            duplicate_overlap_fraction=1.0,
        )
        item.residual_rms_mm = rms
        return item

    selected, error = module._select_candidate(
        [
            candidate("top", 200.0, 0.50, 0.030),
            candidate("lower", 260.0, 0.48, 0.031),
        ]
    )
    assert selected is None
    assert "equally supported" in error

    selected, error = module._select_candidate(
        [
            candidate("long", 200.0, 0.60, 0.045),
            candidate("short", 260.0, 0.35, 0.020),
        ]
    )
    assert error is None
    assert selected.candidate_id == "long"


def test_invalid_motion_or_localizer_contract_is_rejected(tmp_path):
    module = _load()
    frames = _synthetic_frames(tmp_path / "frames")
    with pytest.raises(ValueError, match="0,10,20"):
        module.analyze(
            frames,
            tmp_path / "motion_analysis",
            offsets_mm=[0, 2, 4, 4, 2, 0],
        )
    with pytest.raises(ValueError, match="localizer"):
        module.analyze(
            frames,
            tmp_path / "localizer_analysis",
            localizer={"kind": "fixed_roi", "version": 1},
        )
