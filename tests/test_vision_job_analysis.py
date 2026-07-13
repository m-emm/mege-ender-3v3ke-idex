import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


VISION_NOZZLE_ALIGN_PATH = (
    Path(__file__).resolve().parents[1]
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
    / "vision_nozzle_align.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "vision_nozzle_align_analysis_test", VISION_NOZZLE_ALIGN_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _prepare_acquired_job(module, tmp_path, *, job_id="analysis_job", dx="0,3"):
    job_root = tmp_path / "jobs"
    summary = module.prepare_nozzle_sweep_job(
        SimpleNamespace(
            name="test",
            job_root=job_root,
            job_id=job_id,
            x=195.0,
            y=-14.8,
            z=20.0,
            dx=dx,
            feedrate=3600.0,
            settle_time=0.2,
            camera="nozzle_cam",
            profile="analysis",
        )
    )
    job_dir = Path(summary["job_dir"])
    manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
    for frame in manifest["frames"]:
        frame_id = frame["frame"]
        (job_dir / "frames" / f"{frame_id}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        (job_dir / "frames" / f"{frame_id}.json").write_text(
            json.dumps(
                {
                    "job_seq": frame["seq"],
                    "framebuffer_seq": 200 + frame["seq"],
                    "image_sha256": "sha256:" + str(frame["seq"]).zfill(64),
                }
            )
            + "\n",
            encoding="utf-8",
        )
    state = json.loads(Path(summary["state_path"]).read_text(encoding="utf-8"))
    state.update(
        {
            "state": "acquired",
            "committed_frame_count": manifest["frame_count"],
            "updated_at_utc": "2026-07-12T00:00:00+00:00",
        }
    )
    module.atomic_write_json(Path(summary["state_path"]), state)
    return job_root, job_dir, manifest


def _prepare_acquired_bed_y_job(
    module, tmp_path, *, job_id="bed_y_analysis_job", y_offsets="0,5,10,15,20"
):
    job_root = tmp_path / "jobs"
    summary = module.prepare_bed_y_sweep_job(
        SimpleNamespace(
            name="bed_y",
            job_root=job_root,
            job_id=job_id,
            x=-80.4,
            y=-14.8,
            z=293.75,
            y_offsets=y_offsets,
            feedrate=3600.0,
            settle_time=0.2,
            camera="nozzle_cam",
            profile="analysis",
        )
    )
    job_dir = Path(summary["job_dir"])
    manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
    state = json.loads(Path(summary["state_path"]).read_text(encoding="utf-8"))
    state.update(
        {
            "state": "acquired",
            "committed_frame_count": manifest["frame_count"],
            "updated_at_utc": "2026-07-12T00:00:00+00:00",
        }
    )
    module.atomic_write_json(Path(summary["state_path"]), state)
    return job_root, job_dir, manifest


def _write_bed_y_synthetic_frames(job_dir, manifest, *, vector=(-0.2, -10.5)):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    rng = np.random.default_rng(123)
    base = np.full((1080, 1920, 3), 28, dtype=np.uint8)
    x, y, w, h = 690, 438, 300, 125
    texture = rng.integers(70, 185, size=(h, w, 1), dtype=np.uint8)
    base[y : y + h, x : x + w] = np.repeat(texture, 3, axis=2)
    cv2.line(base, (700, 492), (970, 492), (238, 238, 238), 4, cv2.LINE_AA)
    cv2.line(base, (718, 528), (962, 528), (34, 34, 34), 2, cv2.LINE_AA)
    cv2.circle(base, (842, 471), 11, (220, 220, 220), -1, cv2.LINE_AA)

    for frame in manifest["frames"]:
        y_offset = float(frame["y_offset"])
        dx = vector[0] * y_offset
        dy = vector[1] * y_offset
        transform = np.float32([[1, 0, dx], [0, 1, dy]])
        image = cv2.warpAffine(
            base,
            transform,
            (base.shape[1], base.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(18, 18, 18),
        )
        frame_id = frame["frame"]
        assert cv2.imwrite(
            str(job_dir / "frames" / f"{frame_id}.jpg"),
            image,
            [int(cv2.IMWRITE_JPEG_QUALITY), 95],
        )
        (job_dir / "frames" / f"{frame_id}.json").write_text(
            json.dumps(
                {
                    "job_seq": frame["seq"],
                    "framebuffer_seq": 500 + frame["seq"],
                    "image_sha256": "sha256:" + str(frame["seq"]).zfill(64),
                }
            )
            + "\n",
            encoding="utf-8",
        )


def _write_bed_y_blank_frames(job_dir, manifest):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    image = np.full((1080, 1920, 3), 28, dtype=np.uint8)
    for frame in manifest["frames"]:
        frame_id = frame["frame"]
        assert cv2.imwrite(
            str(job_dir / "frames" / f"{frame_id}.jpg"),
            image,
            [int(cv2.IMWRITE_JPEG_QUALITY), 95],
        )
        (job_dir / "frames" / f"{frame_id}.json").write_text(
            json.dumps({"job_seq": frame["seq"], "framebuffer_seq": 600 + frame["seq"]})
            + "\n",
            encoding="utf-8",
        )


def _install_fake_reporters(monkeypatch, module, *, accepted=True):
    def fake_analyze(frames, _run_dir, overlay_dir=None):
        overlay_root = Path(overlay_dir)
        overlay_root.mkdir(parents=True, exist_ok=True)
        for frame in frames:
            overlay = overlay_root / f"{frame['prefix']}_overlay.jpg"
            overlay.write_bytes(b"\xff\xd8\xff\xd9")
            frame["overlay_path"] = str(overlay)
            frame["overlay_url"] = module.safe_vision_url(overlay)
        return {
            "ok": accepted,
            "proxy_only": not accepted,
            "message": (
                "Global ROI cross-match accepted."
                if accepted
                else "Nozzle vision sweep failed hard: no nozzle candidates"
            ),
            "hard_failures": [] if accepted else ["no nozzle candidates"],
            "red_marker_fits": {"t0": {"ok": True}, "t1": {"ok": True}},
            "red_marker_delta_t1_minus_t0": {"dx": 1.0, "dy": 2.0},
            "cross_match": {"accepted": accepted, "usable_pair_count": 4},
            "nozzle_delta_t1_minus_t0": (
                {
                    "dx": 10.0,
                    "dy": -2.0,
                    "along_x_mm_approx": 0.5,
                    "perpendicular_mm_approx": -0.1,
                }
                if accepted
                else None
            ),
        }

    def fake_contact_sheet(_frames, _analysis, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"\xff\xd8\xff\xd9")

    monkeypatch.setattr(module, "analyze_sweep_frames", fake_analyze)
    monkeypatch.setattr(module, "write_contact_sheet", fake_contact_sheet)


def _analyze_args(job_root, job_id):
    return SimpleNamespace(analyze_job=job_id, job_id=None, job_root=job_root)


def test_analyze_acquired_job_writes_reports_and_completes(
    monkeypatch, tmp_path
):
    module = _load_module()
    monkeypatch.setattr(module, "NOZZLE_SWEEP_DIR", tmp_path / "nozzle_sweep")
    _install_fake_reporters(monkeypatch, module, accepted=True)
    job_root, job_dir, manifest = _prepare_acquired_job(module, tmp_path)

    result = module.analyze_acquired_job(
        _analyze_args(job_root, manifest["job_id"])
    )

    assert result["ok"] is True
    assert result["state"] == "completed"
    analysis_dir = job_dir / "analysis"
    assert (analysis_dir / "result.json").exists()
    assert (analysis_dir / "facts.json").exists()
    assert (analysis_dir / "raw_contact_sheet.jpg").exists()
    assert (analysis_dir / "overlay_contact_sheet.jpg").exists()
    assert all(
        (analysis_dir / "overlays" / f"{frame['frame']}_overlay.jpg").exists()
        for frame in manifest["frames"]
    )

    state = json.loads((job_dir / "state.json").read_text(encoding="utf-8"))
    facts = json.loads((analysis_dir / "facts.json").read_text(encoding="utf-8"))
    assert state["state"] == "completed"
    assert state["analysis_result_path"] == str(analysis_dir / "result.json")
    assert facts["accepted"] is True
    assert facts["nozzle_delta_t1_minus_t0"]["dx"] == 10.0
    assert not (tmp_path / "nozzle_sweep" / "latest_result.json").exists()
    assert not (tmp_path / "nozzle_sweep" / "latest_contact_sheet.jpg").exists()


def test_analyze_acquired_job_rejection_writes_diagnostics_and_fails(
    monkeypatch, tmp_path
):
    module = _load_module()
    monkeypatch.setattr(module, "NOZZLE_SWEEP_DIR", tmp_path / "nozzle_sweep")
    _install_fake_reporters(monkeypatch, module, accepted=False)
    job_root, job_dir, manifest = _prepare_acquired_job(module, tmp_path)

    result = module.analyze_acquired_job(
        _analyze_args(job_root, manifest["job_id"])
    )

    assert result["ok"] is False
    assert result["state"] == "failed"
    analysis_dir = job_dir / "analysis"
    state = json.loads((job_dir / "state.json").read_text(encoding="utf-8"))
    facts = json.loads((analysis_dir / "facts.json").read_text(encoding="utf-8"))
    assert state["state"] == "failed"
    assert "no nozzle candidates" in state["failure"]
    assert facts["accepted"] is False
    assert facts["nozzle_delta_t1_minus_t0"] is None
    assert (analysis_dir / "result.json").exists()
    assert (analysis_dir / "overlay_contact_sheet.jpg").exists()


def test_analyze_bed_y_job_recovers_synthetic_motion(tmp_path):
    module = _load_module()
    job_root, job_dir, manifest = _prepare_acquired_bed_y_job(module, tmp_path)
    _write_bed_y_synthetic_frames(job_dir, manifest)

    result = module.analyze_acquired_job(
        _analyze_args(job_root, manifest["job_id"])
    )

    analysis_dir = job_dir / "analysis"
    facts = json.loads((analysis_dir / "facts.json").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["state"] == "completed"
    assert facts["measurement"] == "nozzle_cam_bed_y_motion"
    assert facts["accepted"] is True
    vector = facts["bed_y_axis_vector_px_per_mm"]
    assert vector[0] == pytest.approx(-0.2, abs=0.2)
    assert vector[1] == pytest.approx(-10.5, abs=0.35)
    assert facts["bed_y_scale_px_per_mm"] == pytest.approx(10.5, abs=0.4)
    assert facts["bed_y_mm_per_px"] == pytest.approx(1 / 10.5, abs=0.005)
    assert facts["bed_y_axis_angle_deg"] < -80
    assert facts["bed_y_cross_axis_px_per_mm"] == pytest.approx(vector[0], abs=1e-6)
    assert facts["bed_y_fit_residual_rms_px"] < 0.45
    assert facts["bed_y_correlation_min"] > 0.7
    assert facts["bed_y_correlation_median"] > 0.8
    assert facts["bed_y_parallax_spread"]["accepted_roi_count"] >= 1
    assert facts["lighting"] == "NOZZLE_CAM_Y_FEATURE_LIGHT"
    for key in (
        "bed_y_axis_vector_px_per_mm",
        "bed_y_scale_px_per_mm",
        "bed_y_mm_per_px",
        "bed_y_axis_angle_deg",
        "bed_y_cross_axis_px_per_mm",
        "bed_y_fit_residual_rms_px",
        "bed_y_correlation_min",
        "bed_y_correlation_median",
        "bed_y_parallax_spread",
    ):
        assert key in facts
    assert (analysis_dir / "result.json").exists()
    assert (analysis_dir / "raw_contact_sheet.jpg").exists()
    assert (analysis_dir / "overlay_contact_sheet.jpg").exists()
    assert all(
        (analysis_dir / "overlays" / f"{frame['frame']}_overlay.jpg").exists()
        for frame in manifest["frames"]
    )


def test_analyze_bed_y_job_rejection_still_writes_artifacts(tmp_path):
    module = _load_module()
    job_root, job_dir, manifest = _prepare_acquired_bed_y_job(module, tmp_path)
    _write_bed_y_blank_frames(job_dir, manifest)

    result = module.analyze_acquired_job(
        _analyze_args(job_root, manifest["job_id"])
    )

    analysis_dir = job_dir / "analysis"
    state = json.loads((job_dir / "state.json").read_text(encoding="utf-8"))
    facts = json.loads((analysis_dir / "facts.json").read_text(encoding="utf-8"))
    assert result["ok"] is False
    assert result["state"] == "failed"
    assert state["state"] == "failed"
    assert facts["measurement"] == "nozzle_cam_bed_y_motion"
    assert facts["accepted"] is False
    assert facts["bed_y_axis_vector_px_per_mm"] is None
    assert facts["bed_y_scale_px_per_mm"] is None
    assert facts["hard_failures"]
    assert (analysis_dir / "result.json").exists()
    assert (analysis_dir / "facts.json").exists()
    assert (analysis_dir / "raw_contact_sheet.jpg").exists()
    assert (analysis_dir / "overlay_contact_sheet.jpg").exists()


def test_analyze_job_requires_acquired_state(tmp_path):
    module = _load_module()
    job_root = tmp_path / "jobs"
    summary = module.prepare_nozzle_sweep_job(
        SimpleNamespace(
            name="test",
            job_root=job_root,
            job_id="prepared_only",
            x=195.0,
            y=-14.8,
            z=20.0,
            dx="0",
            feedrate=3600.0,
            settle_time=0.2,
            camera="nozzle_cam",
            profile="analysis",
        )
    )

    with pytest.raises(RuntimeError, match="expected 'acquired'"):
        module.analyze_acquired_job(_analyze_args(job_root, summary["job_id"]))


def test_analyze_job_refuses_to_overwrite_existing_reports(
    monkeypatch, tmp_path
):
    module = _load_module()
    monkeypatch.setattr(module, "NOZZLE_SWEEP_DIR", tmp_path / "nozzle_sweep")
    _install_fake_reporters(monkeypatch, module, accepted=True)
    job_root, job_dir, manifest = _prepare_acquired_job(module, tmp_path)
    (job_dir / "analysis" / "result.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        module.analyze_acquired_job(_analyze_args(job_root, manifest["job_id"]))


def test_run_full_job_runs_acquisition_then_analysis(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "NOZZLE_SWEEP_DIR", tmp_path / "nozzle_sweep")
    _install_fake_reporters(monkeypatch, module, accepted=True)
    job_root, _job_dir, manifest = _prepare_acquired_job(
        module, tmp_path, job_id="full_job"
    )

    monkeypatch.setattr(
        module,
        "run_acquisition_job",
        lambda _args: {
            "ok": True,
            "job_id": manifest["job_id"],
            "state": "acquired",
            "virtual_sd_filename": "vision_jobs/full_job.gcode",
            "committed_frame_count": manifest["frame_count"],
        },
    )

    result = module.run_full_job(
        SimpleNamespace(job_root=job_root, job_id="full_job", analyze_job=None)
    )

    assert result["ok"] is True
    assert result["state"] == "completed"
    assert result["acquisition"]["virtual_sd_filename"] == "vision_jobs/full_job.gcode"
