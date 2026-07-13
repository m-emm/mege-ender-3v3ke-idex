import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


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
        "vision_nozzle_align_ui_test", VISION_NOZZLE_ALIGN_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _configure_ui_paths(monkeypatch, module, tmp_path):
    root = tmp_path / "vision"
    camera_root = root / "nozzle_cam"
    job_root = camera_root / "jobs"
    monkeypatch.setattr(module, "VISION_ROOT_DIR", root)
    monkeypatch.setattr(module, "VISION_DIR", camera_root)
    monkeypatch.setattr(module, "NOZZLE_CAMERA_VISION_DIR", camera_root)
    monkeypatch.setattr(module, "NOZZLE_JOB_ROOT", job_root)
    monkeypatch.setattr(module, "NOZZLE_SWEEP_DIR", camera_root / "nozzle_sweep")
    monkeypatch.setattr(module, "VISION_URL_PREFIX", "/vision/nozzle_cam")
    monkeypatch.setattr(module, "VISION_ROOT_URL_PREFIX", "/vision")
    return root, job_root


def _prepare_job(module, job_root, *, job_id, dx="0", created=None):
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
    state_path = Path(summary["state_path"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if created:
        state["created_at_utc"] = created
        state["updated_at_utc"] = created
        module.atomic_write_json(state_path, state)
    return summary


def _prepare_bed_y_job(module, job_root, *, job_id, created=None):
    summary = module.prepare_bed_y_sweep_job(
        SimpleNamespace(
            name="bed_y",
            job_root=job_root,
            job_id=job_id,
            x=-80.4,
            y=-14.8,
            z=293.75,
            y_offsets="0,5,10,15,20",
            feedrate=3600.0,
            settle_time=0.2,
            camera="nozzle_cam",
            profile="analysis",
        )
    )
    state_path = Path(summary["state_path"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if created:
        state["created_at_utc"] = created
        state["updated_at_utc"] = created
        module.atomic_write_json(state_path, state)
    return summary


def _commit_frames(module, summary):
    job_dir = Path(summary["job_dir"])
    manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
    for frame in manifest["frames"]:
        frame_id = frame["frame"]
        (job_dir / "frames" / f"{frame_id}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        (job_dir / "frames" / f"{frame_id}.json").write_text(
            json.dumps(
                {
                    "job_seq": frame["seq"],
                    "framebuffer_seq": 300 + frame["seq"],
                    "source_frame": {
                        "timestamp_utc": f"2026-07-12T00:00:0{frame['seq']}+00:00"
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
    state_path = Path(summary["state_path"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "state": "completed",
            "committed_frame_count": manifest["frame_count"],
            "updated_at_utc": "2026-07-12T01:00:00+00:00",
            "analysis_completed_at_utc": "2026-07-12T01:00:00+00:00",
        }
    )
    module.atomic_write_json(state_path, state)
    return manifest


def _write_analysis_artifacts(module, summary):
    job_dir = Path(summary["job_dir"])
    manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
    paths = module.job_analysis_paths(job_dir)
    paths["overlays_dir"].mkdir(parents=True, exist_ok=True)
    paths["raw_contact_sheet"].write_bytes(b"\xff\xd8\xff\xd9")
    paths["overlay_contact_sheet"].write_bytes(b"\xff\xd8\xff\xd9")
    paths["result"].write_text(
        json.dumps({"ok": True, "message": "accepted"}) + "\n",
        encoding="utf-8",
    )
    paths["facts"].write_text(
        json.dumps(
            {
                "accepted": True,
                "job_id": manifest["job_id"],
                "nozzle_delta_t1_minus_t0": {
                    "along_x_mm_approx": -1.23456,
                    "along_x_px": -9.8765,
                    "perpendicular_mm_approx": 0.34567,
                    "perpendicular_px": 2.7654,
                    "dx": -9.88,
                    "dy": 2.76,
                    "measurement_source": "global_roi_cross_match",
                },
                "quality": {
                    "cross_match": {
                        "usable_pair_count": 42,
                        "residual_rms_px": 1.2345,
                        "correlation_median": 0.8765,
                        "feature_mode": "gray",
                        "axis_px_per_mm": 8.7654,
                        "axis_angle_deg": -0.1234,
                    }
                },
                "hard_failures": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for frame in manifest["frames"]:
        (paths["overlays_dir"] / f"{frame['frame']}_overlay.jpg").write_bytes(
            b"\xff\xd8\xff\xd9"
        )


def _write_bed_y_analysis_artifacts(module, summary):
    job_dir = Path(summary["job_dir"])
    manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
    paths = module.job_analysis_paths(job_dir)
    paths["overlays_dir"].mkdir(parents=True, exist_ok=True)
    paths["raw_contact_sheet"].write_bytes(b"\xff\xd8\xff\xd9")
    paths["overlay_contact_sheet"].write_bytes(b"\xff\xd8\xff\xd9")
    paths["result"].write_text(
        json.dumps({"ok": True, "message": "Bed Y feature motion accepted."}) + "\n",
        encoding="utf-8",
    )
    paths["facts"].write_text(
        json.dumps(
            {
                "accepted": True,
                "ok": True,
                "job_id": manifest["job_id"],
                "kind": "nozzle_cam_bed_y_sweep",
                "measurement": "nozzle_cam_bed_y_motion",
                "bed_y_axis_vector_px_per_mm": [-0.2, -10.5],
                "bed_y_scale_px_per_mm": 10.502,
                "bed_y_mm_per_px": 0.09522,
                "bed_y_axis_angle_deg": -91.091,
                "bed_y_cross_axis_px_per_mm": -0.2,
                "bed_y_fit_residual_rms_px": 0.123,
                "bed_y_correlation_min": 0.8123,
                "bed_y_correlation_median": 0.9345,
                "bed_y_parallax_spread": {
                    "accepted_roi_count": 2,
                    "accepted_rois": ["marked_line_tight", "marked_line_context"],
                    "axis_vector_spread_px_per_mm": 0.08,
                    "scale_spread_px_per_mm": 0.05,
                    "scale_spread_percent": 0.48,
                    "angle_spread_deg": 0.2,
                    "meaning": "local perspective variation between accepted bed-feature ROIs; not a full Z-height solve",
                },
                "lighting": "NOZZLE_CAM_Y_FEATURE_LIGHT",
                "quality": {
                    "selected_roi": "marked_line_tight",
                    "feature_mode": "grad_y",
                    "reference_frame": "bed_y_0p0",
                    "reference_y_offset": 0.0,
                },
                "hard_failures": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for frame in manifest["frames"]:
        (paths["overlays_dir"] / f"{frame['frame']}_overlay.jpg").write_bytes(
            b"\xff\xd8\xff\xd9"
        )


def test_prepare_job_generates_static_ui(monkeypatch, tmp_path, capsys):
    module = _load_module()
    root, job_root = _configure_ui_paths(monkeypatch, module, tmp_path)

    assert (
        module.main(
            [
                "--prepare-job",
                "--job-root",
                str(job_root),
                "--job-id",
                "ui_prepared",
                "--dx",
                "0",
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)

    assert summary["ui"]["entrypoint_url"] == "/vision/"
    assert summary["ui"]["entrypoint_public_url"] == "http://menderpi.local/vision/"
    assert summary["ui"]["index_url"] == "/vision/index.html"
    assert (root / "index.html").exists()
    assert (root / "jobs.json").exists()
    assert (job_root / "ui_prepared" / "index.html").exists()
    jobs = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
    assert jobs["entrypoint_url"] == "/vision/"
    assert jobs["counts_by_state"] == {"prepared": 1}
    assert jobs["jobs"][0]["page_url"] == "/vision/nozzle_cam/jobs/ui_prepared/index.html"


def test_completed_job_page_links_analysis_and_frames(monkeypatch, tmp_path):
    module = _load_module()
    root, job_root = _configure_ui_paths(monkeypatch, module, tmp_path)
    summary = _prepare_job(module, job_root, job_id="ui_completed", dx="0,3")
    manifest = _commit_frames(module, summary)
    _write_analysis_artifacts(module, summary)

    ui = module.refresh_vision_ui(job_root)

    assert ui["ok"] is True
    page = (job_root / "ui_completed" / "index.html").read_text(encoding="utf-8")
    assert "result.json" in page
    assert "facts.json" in page
    assert "raw_contact_sheet.jpg" in page
    assert "overlay_contact_sheet.jpg" in page
    assert "Measurement Result" in page
    assert "T1 - T0 along X" in page
    assert "-1.235 mm" in page
    assert "-9.877 px" in page
    assert "42 pairs" in page
    assert "corr median 0.876" in page
    assert f"{manifest['frames'][0]['frame']}_overlay.jpg" in page
    assert "framebuffer" in page.lower()
    for frame in manifest["frames"]:
        assert f"{frame['frame']}.jpg" in page
        assert f"{frame['frame']}.json" in page
    jobs = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
    assert jobs["counts_by_state"] == {"completed": 1}
    assert jobs["jobs"][0]["artifacts"]["facts"]["exists"] is True


def test_completed_bed_y_job_page_renders_bed_y_facts(monkeypatch, tmp_path):
    module = _load_module()
    root, job_root = _configure_ui_paths(monkeypatch, module, tmp_path)
    summary = _prepare_bed_y_job(module, job_root, job_id="ui_bed_y_completed")
    manifest = _commit_frames(module, summary)
    _write_bed_y_analysis_artifacts(module, summary)

    ui = module.refresh_vision_ui(job_root)

    assert ui["ok"] is True
    page = (job_root / "ui_bed_y_completed" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "Nozzle Camera Bed Y Sweep" in page
    assert "Bed Y scale" in page
    assert "Image vector" in page
    assert "negative image Y means the feature moves upward" in page
    assert "NOZZLE_CAM_Y_FEATURE_LIGHT" in page
    assert "Parallax spread" in page
    assert "marked_line_tight" in page
    assert "T1 - T0 along X" not in page
    assert "result.json" in page
    assert "facts.json" in page
    assert "raw_contact_sheet.jpg" in page
    assert "overlay_contact_sheet.jpg" in page
    assert f"{manifest['frames'][0]['frame']}_overlay.jpg" in page
    jobs = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
    assert jobs["jobs"][0]["kind"] == "nozzle_cam_bed_y_sweep"
    assert jobs["jobs"][0]["artifacts"]["facts"]["exists"] is True


def test_failed_job_page_exposes_failure(monkeypatch, tmp_path):
    module = _load_module()
    _root, job_root = _configure_ui_paths(monkeypatch, module, tmp_path)
    summary = _prepare_job(module, job_root, job_id="ui_failed", dx="0")
    state_path = Path(summary["state_path"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "state": "failed",
            "failure": "red marker fit failed",
            "updated_at_utc": "2026-07-12T02:00:00+00:00",
        }
    )
    module.atomic_write_json(state_path, state)

    module.refresh_vision_ui(job_root)

    page = (job_root / "ui_failed" / "index.html").read_text(encoding="utf-8")
    assert "red marker fit failed" in page
    assert "state-failed" in page
    assert "accepted" not in page


def test_jobs_json_sorts_newest_first_and_counts_states(monkeypatch, tmp_path):
    module = _load_module()
    root, job_root = _configure_ui_paths(monkeypatch, module, tmp_path)
    _prepare_job(
        module,
        job_root,
        job_id="older_prepared",
        created="2026-07-12T01:00:00+00:00",
    )
    newer = _prepare_job(
        module,
        job_root,
        job_id="newer_failed",
        created="2026-07-12T02:00:00+00:00",
    )
    state_path = Path(newer["state_path"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({"state": "failed", "failure": "capture boom"})
    module.atomic_write_json(state_path, state)

    module.refresh_vision_ui(job_root)

    jobs = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
    assert [job["job_id"] for job in jobs["jobs"]] == [
        "newer_failed",
        "older_prepared",
    ]
    assert jobs["counts_by_state"] == {"failed": 1, "prepared": 1}


def test_refresh_ui_does_not_touch_printer_or_camera(monkeypatch, tmp_path, capsys):
    module = _load_module()
    _root, job_root = _configure_ui_paths(monkeypatch, module, tmp_path)
    _prepare_job(module, job_root, job_id="offline_refresh", dx="0")
    monkeypatch.setattr(
        module,
        "query_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("moonraker")),
    )
    monkeypatch.setattr(
        module,
        "run_gcode",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("motion")),
    )
    monkeypatch.setattr(
        module,
        "analyze_sweep_frames",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("analysis")),
    )

    assert module.main(["--refresh-ui", "--job-root", str(job_root)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
    assert summary["job_count"] == 1


def test_camera_scoped_output_dir_still_generates_root_index(monkeypatch, tmp_path):
    module = _load_module()
    root = tmp_path / "printer_data" / "vision"
    camera_root = root / "nozzle_cam"
    job_root = camera_root / "jobs"
    monkeypatch.setattr(module, "VISION_DIR", camera_root)
    monkeypatch.setattr(module, "VISION_ROOT_DIR", root)
    monkeypatch.setattr(module, "VISION_URL_PREFIX", "/vision/nozzle_cam")
    monkeypatch.setattr(module, "VISION_ROOT_URL_PREFIX", "/vision")
    monkeypatch.setattr(module, "NOZZLE_SWEEP_DIR", camera_root / "nozzle_sweep")
    _prepare_job(module, job_root, job_id="camera_scoped", dx="0")

    ui = module.refresh_vision_ui(job_root)

    assert ui["entrypoint_path"] == str(root / "index.html")
    assert ui["entrypoint_url"] == "/vision/"
    assert ui["index_url"] == "/vision/index.html"
    assert (root / "index.html").exists()
    assert (camera_root / "jobs" / "camera_scoped" / "index.html").exists()
