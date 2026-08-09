import importlib.util
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
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
LIVE_EXP600_FIXTURE = (
    REPO_ROOT / "tests" / "vision" / "fixtures" / "red_marker_x_sweep_live_exp600"
)
OUTPUT_ROOT = REPO_ROOT / "output" / "vision_red_marker_x_sweep_replay"


def _module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    name = f"vision_red_marker_test_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(
        name, FILES / "vision_red_marker_x_sweep.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic_frames(tmp_path):
    paths = []
    frames = []
    x_values = (160, 170, 180, 190, 200, 210)
    for tool in ("T0", "T1"):
        for x_mm in x_values:
            image = np.full((540, 960, 3), (52, 48, 44), dtype=np.uint8)
            cv2.line(image, (80, 180), (880, 180), (100, 100, 100), 5)
            marker_x = round(
                350 + 4.05 * (x_mm - 160) + (-40 if tool == "T1" else 0)
            )
            marker_y = 210
            hidden = (tool == "T0" and x_mm < 180) or (
                tool == "T1" and x_mm < 190
            )
            if not hidden:
                cv2.rectangle(
                    image,
                    (marker_x - 28, marker_y - 28),
                    (marker_x + 28, marker_y + 28),
                    (105, 105, 105),
                    -1,
                )
                cv2.rectangle(
                    image,
                    (marker_x - 10, marker_y - 23),
                    (marker_x + 10, marker_y + 23),
                    (20, 20, 230),
                    -1,
                )
                cv2.circle(image, (marker_x, marker_y), 5, (10, 10, 10), -1)
                cv2.line(
                    image,
                    (marker_x - 22, marker_y + 15),
                    (marker_x + 22, marker_y + 15),
                    (220, 220, 220),
                    2,
                )
            if tool == "T1":
                # A larger red distractor must not win merely by area.
                cable_x = 250 + round(1.3 * (x_mm - 160))
                cv2.ellipse(
                    image,
                    (cable_x, 105),
                    (25, 45),
                    20,
                    0,
                    300,
                    (20, 20, 220),
                    10,
                )
            path = tmp_path / f"{tool.lower()}_x{x_mm}.jpg"
            assert cv2.imwrite(str(path), image)
            paths.append(path)
            frames.append({"tool": tool, "x_mm": x_mm})
    return paths, frames


def _run_id() -> str:
    return (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + f"-{uuid.uuid4().hex[:8]}"
    )


def _write_frame_overlay(
    image: np.ndarray,
    frame: dict,
    candidates: list[dict],
    selected_ids: set[str],
    path: Path,
    selection_note: str | None = None,
) -> None:
    overlay = image.copy()
    for candidate in candidates:
        selected = candidate["candidate_id"] in selected_ids
        color = (45, 220, 45) if selected else (40, 40, 230)
        x0, y0, x1, y1 = candidate["bbox_px"]
        center = tuple(np.rint(candidate["center_px"]).astype(int))
        cv2.rectangle(overlay, (x0, y0), (x1, y1), color, 3)
        cv2.drawMarker(overlay, center, color, cv2.MARKER_CROSS, 28, 2)
        cv2.putText(
            overlay,
            f"{candidate['candidate_id']} area={candidate['area_px']} "
            f"V={candidate['median_value']:.0f} bright={candidate['bright_core_fraction']:.2f} "
            f"red={candidate['red_dominance_median']:.2f}",
            (x0, max(24, y0 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2.LINE_AA,
        )
    cv2.putText(
        overlay,
        f"{frame['frame']}  {frame['tool']}  X={frame['x_mm']} mm",
        (28, 52),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 255),
        3,
        cv2.LINE_AA,
    )
    legend = selection_note or (
        "green=selected trajectory candidate  red=other red component"
    )
    cv2.putText(
        overlay,
        legend,
        (28, 88),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), overlay):
        raise AssertionError(f"could not write overlay {path}")


def test_live_exp600_t0_x170_component_gate_debug_overlay():
    """Render each component considered before trajectory matching exists."""
    module = _module()
    manifest = json.loads((LIVE_EXP600_FIXTURE / "manifest.json").read_text())
    frame_index, frame = next(
        (index, frame)
        for index, frame in enumerate(manifest["frames"])
        if frame["tool"] == "T0" and frame["x_mm"] == 170
    )
    image_path = LIVE_EXP600_FIXTURE / "frames" / f"{frame['frame']}.jpg"
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    assert image is not None, image_path

    candidates = module._red_candidates(image, frame_index)
    assert candidates, "the captured frame must expose component-gate candidates"
    assert all(
        candidate["bright_core_fraction"] >= module.MIN_BRIGHT_CORE_FRACTION
        for candidate in candidates
    )
    assert all(
        candidate["red_dominance_median"] >= module.MIN_RED_DOMINANCE_MEDIAN
        and candidate["strong_red_fraction"] >= module.MIN_STRONG_RED_FRACTION
        for candidate in candidates
    )

    run_root = OUTPUT_ROOT / "runs" / _run_id()
    overlay_path = (
        run_root
        / "single_frame_overlays"
        / f"{frame_index:02d}_{frame['frame']}_components.png"
    )
    _write_frame_overlay(
        image,
        frame,
        candidates,
        selected_ids=set(),
        path=overlay_path,
        selection_note="single-frame diagnostic: component gates only; no trajectory match",
    )
    (run_root / "component_candidates.json").write_text(
        json.dumps(candidates, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _logger.info("Overlay %s", overlay_path.resolve())


def test_recovers_marker_axis_and_rejects_larger_red_distractor(tmp_path):
    module = _module()
    paths, frames = _synthetic_frames(tmp_path)
    result = module.analyze(
        paths,
        tmp_path / "artifacts",
        frames=frames,
        reference={
            "corner_pixel_xy_px": [300.0, 100.0],
            "corner_printer_xyz_mm": [170.0, -20.0, 0.0],
            "image_y_axis_vector_px_per_mm": [-0.11, -5.25],
            "corner_pixel_capture_y_mm": -20.0,
            "capture_y_mm": -14.0,
        },
        localizer={"kind": "red_marker_trajectory", "version": 1},
    )

    assert result["accepted"]
    assert set(result["accepted_x_mm"]) == {"T0", "T1"}
    assert all(
        len(values) == 3 and max(values) - min(values) >= 20
        for values in result["accepted_x_mm"].values()
    )
    assert result["common_axis_vector_px_per_mm"] == pytest.approx(
        [4.05, 0.0], abs=0.1
    )
    assert set(result["artifacts"]) == {
        "contact_sheet",
        "marker_selection",
        "core_registration",
        "cross_tool_registration",
        "trajectory",
    }


def test_rejects_missing_tool_trajectory(tmp_path):
    module = _module()
    paths, frames = _synthetic_frames(tmp_path)
    for path, frame in zip(paths, frames):
        if frame["tool"] == "T1":
            image = np.full((540, 960, 3), 50, dtype=np.uint8)
            assert cv2.imwrite(str(path), image)
    result = module.analyze(
        paths,
        tmp_path / "missing-artifacts",
        frames=frames,
        reference={
            "corner_pixel_xy_px": [300.0, 100.0],
            "corner_printer_xyz_mm": [170.0, -20.0, 0.0],
            "image_y_axis_vector_px_per_mm": [-0.11, -5.25],
            "corner_pixel_capture_y_mm": -20.0,
            "capture_y_mm": -14.0,
        },
        localizer={"kind": "red_marker_trajectory", "version": 1},
    )
    assert not result["accepted"]
    assert any("T1" in reason for reason in result["reasons"])


def test_live_exp600_fixture_emits_debug_overlays():
    """Replay the failed live capture and always retain its visual audit trail."""
    module = _module()
    manifest_path = LIVE_EXP600_FIXTURE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    frames = manifest["frames"]
    frame_paths = [
        LIVE_EXP600_FIXTURE / "frames" / f"{frame['frame']}.jpg"
        for frame in frames
    ]
    run_root = OUTPUT_ROOT / "runs" / _run_id()
    artifact_dir = run_root / "artifacts"
    frame_overlay_dir = run_root / "frame_overlays"
    assert len(frame_paths) == 12
    candidates_by_frame = {}
    for index, (frame, path) in enumerate(zip(frames, frame_paths)):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        assert image is not None, path
        candidates_by_frame[index] = module._red_candidates(image, index)

    t1_x200 = cv2.imread(str(frame_paths[10]), cv2.IMREAD_COLOR)
    assert t1_x200 is not None
    t1_x200_candidates = module._red_candidates(t1_x200, 10)
    assert any(
        candidate["bbox_px"][2] - candidate["bbox_px"][0]
        > 0.085 * t1_x200.shape[1]
        for candidate in t1_x200_candidates
    ), "the wide true T1 X=200 marker must remain available to trajectory selection"

    result = module.analyze(
        frame_paths,
        artifact_dir,
        frames=frames,
        reference=manifest["red_marker_reference"],
        localizer=manifest["localizer"],
    )
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    selected_ids = set(result["selected_candidate_ids"])
    for index, (frame, source_path) in enumerate(zip(frames, frame_paths)):
        image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
        assert image is not None, source_path
        overlay_path = frame_overlay_dir / f"{index:02d}_{frame['frame']}_red_marker.png"
        _write_frame_overlay(
            image,
            frame,
            candidates_by_frame[index],
            selected_ids,
            overlay_path,
        )
        _logger.info("Overlay %s", overlay_path.resolve())

    for name, artifact in sorted(result["artifacts"].items()):
        path = Path(artifact["path"])
        assert path.exists(), f"missing {name} overlay: {path}"
        _logger.info("Overlay %s", path.resolve())

    assert result["accepted"], result["reasons"]
    assert all(
        len(values) == 3 and max(values) - min(values) >= 20
        for values in result["accepted_x_mm"].values()
    )
    assert set(result["artifacts"]) == {
        "contact_sheet",
        "marker_selection",
        "core_registration",
        "cross_tool_registration",
        "trajectory",
    }
    assert len(list(frame_overlay_dir.glob("*.png"))) == len(frames)


def test_pair_registration_excludes_one_inconsistent_representation(monkeypatch):
    module = _module()
    calls = iter(
        [
            {"shift_px": [80.0, -1.0], "correlation": 0.75, "boundary_hit": False},
            {"shift_px": [-76.0, 1.0], "correlation": 0.72, "boundary_hit": False},
            {"shift_px": [79.0, -1.2], "correlation": 0.81, "boundary_hit": False},
            {"shift_px": [-79.4, 1.0], "correlation": 0.79, "boundary_hit": False},
        ]
    )

    monkeypatch.setattr(
        module,
        "_one_way_registration",
        lambda *_args, **_kwargs: next(calls),
    )
    representations = {
        "gray": np.zeros((20, 20), dtype=np.uint8),
        "clahe": np.zeros((20, 20), dtype=np.uint8),
    }
    registration = module._pair_registration(
        representations,
        np.asarray([10.0, 10.0]),
        representations,
        np.asarray([10.0, 10.0]),
    )

    assert registration["usable_representations"] == ["clahe"]
    assert registration["shift_px"] == pytest.approx([79.2, -1.1])
    assert registration["minimum_correlation"] == pytest.approx(0.79)
    assert registration["representation_spread_px"] == 0.0
    assert not registration["boundary_hit"]
