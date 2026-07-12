import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VISION_CAPTURE_PATH = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
    / "vision_capture.py"
)
VISION_NOZZLE_ALIGN_PATH = VISION_CAPTURE_PATH.with_name("vision_nozzle_align.py")


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_vision_capture(monkeypatch, tmp_path):
    output_dir = tmp_path / "vision" / "nozzle_cam"
    framebuffer_dir = tmp_path / "framebuffer"
    profile_request = framebuffer_dir / "profile_request.json"
    framebuffer_dir.mkdir(parents=True)
    (framebuffer_dir / "latest.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (framebuffer_dir / "latest.json").write_text(
        json.dumps(
            {
                "frame_seq": 10,
                "width": 1920,
                "height": 1080,
                "camera_profile": {
                    "requested_profile": "analysis",
                    "active_profile": "nozzle_cam_analysis",
                    "profile_names": ["analysis", "nozzle_cam_analysis"],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VISION_OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("VISION_FRAMEBUFFER_DIR", str(framebuffer_dir))
    monkeypatch.setenv("VISION_CAMERA_PROFILE_REQUEST_FILE", str(profile_request))
    monkeypatch.setenv("VISION_JOB_ROOT", str(output_dir / "jobs"))
    monkeypatch.setenv("VISIOND_SOCKET", str(tmp_path / "visiond.sock"))
    monkeypatch.setenv("VISIOND_SOCKET_ENABLED", "0")
    monkeypatch.setenv("VISIOND_SOCKET_REQUEST_TIMEOUT", "0.2")
    return _load_module(VISION_CAPTURE_PATH, "vision_capture_job_api_test")


def _prepare_job(tmp_path, *, job_id="job_api_test", dx="0"):
    nozzle_align = _load_module(VISION_NOZZLE_ALIGN_PATH, "vision_nozzle_align_job_api_test")
    job_root = tmp_path / "vision" / "nozzle_cam" / "jobs"
    summary = nozzle_align.prepare_nozzle_sweep_job(
        SimpleNamespace(
            name="test",
            job_root=str(job_root),
            job_id=job_id,
            x=195.0,
            y=-14.8,
            z=20.0,
            dx=dx,
            feedrate=12000.0,
            settle_time=0.15,
            camera="nozzle_cam",
            profile="analysis",
        )
    )
    manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
    return job_root, summary, manifest


def _begin_params(manifest):
    return {
        "job": manifest["job_id"],
        "manifest_hash": manifest["manifest_hash"],
        "gcode_hash": manifest["gcode_hash"],
    }


def test_job_begin_rejects_wrong_hashes_and_non_prepared_state(monkeypatch, tmp_path):
    module = _load_vision_capture(monkeypatch, tmp_path)
    job_root, _summary, manifest = _prepare_job(tmp_path)
    api = module.VisionJobApi(job_root=job_root, request_timeout=0.2)

    bad_hash = dict(_begin_params(manifest))
    bad_hash["manifest_hash"] = "sha256:" + "0" * 64
    with pytest.raises(module.CaptureError, match="manifest hash mismatch"):
        api.job_begin(bad_hash)

    state_path = job_root / manifest["job_id"] / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["state"] = "failed"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(module.CaptureError, match="expected 'prepared'"):
        api.job_begin(_begin_params(manifest))


def test_capture_rejects_contract_violations(monkeypatch, tmp_path):
    module = _load_vision_capture(monkeypatch, tmp_path)
    job_root, _summary, manifest = _prepare_job(tmp_path)
    api = module.VisionJobApi(job_root=job_root, request_timeout=0.2)
    api.job_begin(_begin_params(manifest))

    frame = manifest["frames"][0]
    valid = {
        "job": manifest["job_id"],
        "seq": frame["seq"],
        "frame": frame["frame"],
        "camera": "nozzle_cam",
        "profile": "analysis",
        "tool": frame["tool"],
    }
    with pytest.raises(module.CaptureError, match="expected job seq 0"):
        api.capture({**valid, "seq": 1})
    with pytest.raises(module.CaptureError, match="frame is"):
        api.capture({**valid, "frame": "wrong_frame"})
    with pytest.raises(module.CaptureError, match="profile is"):
        api.capture({**valid, "profile": "auto"})

    frames_dir = job_root / manifest["job_id"] / "frames"
    (frames_dir / f"{frame['frame']}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    with pytest.raises(module.CaptureError, match="refusing to overwrite"):
        api.capture(valid)


def test_successful_job_capture_commits_frames_and_acquires(monkeypatch, tmp_path):
    module = _load_vision_capture(monkeypatch, tmp_path)
    job_root, _summary, manifest = _prepare_job(tmp_path)
    api = module.VisionJobApi(job_root=job_root, request_timeout=0.2)
    source_image = module.FRAMEBUFFER_LATEST_IMAGE
    seq = {"value": 10}

    def fake_wait_for_frame_seq_after(
        *, previous_frame_seq, timeout, required_profile=None
    ):
        assert required_profile == "analysis"
        assert previous_frame_seq <= seq["value"]
        seq["value"] += 1
        metadata = {
            "frame_seq": seq["value"],
            "width": 1920,
            "height": 1080,
            "camera_profile": {
                "profile_names": ["analysis", "nozzle_cam_analysis"],
            },
        }
        return source_image, metadata

    monkeypatch.setattr(
        module, "wait_for_buffered_frame_seq_after", fake_wait_for_frame_seq_after
    )

    assert api.job_begin(_begin_params(manifest))["state"] == "acquiring"
    assert api.profile({"camera": "nozzle_cam", "profile": "analysis"})[
        "framebuffer_seq"
    ] == 10

    first = manifest["frames"][0]
    api.capture(
        {
            "job": manifest["job_id"],
            "seq": first["seq"],
            "frame": first["frame"],
            "camera": "nozzle_cam",
            "profile": "analysis",
            "tool": first["tool"],
            "toolhead_position": [195.0, -14.8, 20.0, 0.0],
            "gcode_position": [195.0, -14.8, 20.0, 0.0],
            "homed_axes": "xyz",
        }
    )
    with pytest.raises(module.CaptureError, match="has 1 committed frames"):
        api.job_end({"job": manifest["job_id"], "expected_frames": manifest["frame_count"]})

    second = manifest["frames"][1]
    api.capture(
        {
            "job": manifest["job_id"],
            "seq": second["seq"],
            "frame": second["frame"],
            "camera": "nozzle_cam",
            "profile": "analysis",
            "tool": second["tool"],
        }
    )
    result = api.job_end(
        {"job": manifest["job_id"], "expected_frames": manifest["frame_count"]}
    )

    assert result["state"] == "acquired"
    frames_dir = job_root / manifest["job_id"] / "frames"
    for frame in manifest["frames"]:
        image = frames_dir / f"{frame['frame']}.jpg"
        sidecar = frames_dir / f"{frame['frame']}.json"
        assert image.exists()
        assert sidecar.exists()
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        assert payload["job_seq"] == frame["seq"]
        assert payload["framebuffer_seq"] > 10
        assert payload["klipper"]["camera"] == "nozzle_cam"

    state = json.loads((job_root / manifest["job_id"] / "state.json").read_text())
    assert state["state"] == "acquired"
    assert state["committed_frame_count"] == manifest["frame_count"]
    assert not (job_root / ".active_job.json").exists()
