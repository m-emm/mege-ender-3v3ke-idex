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
        "vision_nozzle_align_execution_test", VISION_NOZZLE_ALIGN_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _status(*, print_state="standby", homed_axes="xyz", webhooks_state="ready"):
    return {
        "webhooks": {"state": webhooks_state},
        "print_stats": {"state": print_state, "message": ""},
        "toolhead": {
            "homed_axes": homed_axes,
            "axis_minimum": [-80.4, -14.8, -1.0, 0],
            "axis_maximum": [244.0, 296.0, 293.75, 0],
        },
        "gcode_move": {"gcode_position": [195.0, -14.8, 20.0, 0.0]},
    }


def _prepare_job(module, tmp_path, *, job_id="execution_job", dx="0"):
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
    return job_root, summary, json.loads(Path(summary["manifest_path"]).read_text())


def _start_args(tmp_path, job_root, job_id, *, monitor_timeout=5.0):
    return SimpleNamespace(
        start_prepared_job=job_id,
        job_id=None,
        job_root=job_root,
        moonraker_url="http://moonraker.test",
        ready_timeout=1.0,
        virtual_sd_root=tmp_path / "gcodes",
        virtual_sd_subdir="vision_jobs",
        monitor_timeout=monitor_timeout,
    )


def _commit_fake_frames(module, summary, manifest):
    job_dir = Path(summary["job_dir"])
    frames_dir = job_dir / "frames"
    for frame in manifest["frames"]:
        frame_id = frame["frame"]
        image = frames_dir / f"{frame_id}.jpg"
        sidecar = frames_dir / f"{frame_id}.json"
        image.write_bytes(b"\xff\xd8\xff\xd9")
        sidecar.write_text(
            json.dumps(
                {
                    "job_seq": frame["seq"],
                    "framebuffer_seq": 100 + frame["seq"],
                    "image_sha256": "sha256:" + str(frame["seq"]).zfill(64),
                }
            )
            + "\n",
            encoding="utf-8",
        )
    state_path = job_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "state": "acquired",
            "committed_frame_count": manifest["frame_count"],
            "updated_at_utc": "2026-07-12T00:00:00+00:00",
        }
    )
    module.atomic_write_json(state_path, state)


def test_start_prepared_job_copies_starts_and_succeeds(monkeypatch, tmp_path):
    module = _load_module()
    job_root, summary, manifest = _prepare_job(module, tmp_path)
    args = _start_args(tmp_path, job_root, manifest["job_id"])
    commands = []
    statuses = [_status(print_state="standby"), _status(print_state="complete")]

    def fake_query_status(_base_url):
        if len(statuses) > 1:
            return statuses.pop(0)
        return statuses[0]

    def fake_run_gcode(_base_url, script, *, timeout=60.0):
        commands.append(script)
        _commit_fake_frames(module, summary, manifest)

    monkeypatch.setattr(module, "query_status", fake_query_status)
    monkeypatch.setattr(module, "run_gcode", fake_run_gcode)

    result = module.start_prepared_job(args)

    assert result["ok"] is True
    assert result["state"] == "acquired"
    assert result["committed_frame_count"] == manifest["frame_count"]
    assert commands == ["SDCARD_PRINT_FILE FILENAME=vision_jobs/execution_job.gcode"]
    staged = tmp_path / "gcodes" / "vision_jobs" / "execution_job.gcode"
    assert staged.exists()
    assert module.compute_gcode_hash(staged.read_text()) == manifest["gcode_hash"]
    state = json.loads(Path(summary["state_path"]).read_text(encoding="utf-8"))
    assert state["virtual_sd_filename"] == "vision_jobs/execution_job.gcode"
    assert state["virtual_sd_gcode_hash"] == manifest["gcode_hash"]
    assert state["started_by"] == "vision_nozzle_align.py"
    assert state["moonraker_url"] == "http://moonraker.test"
    assert [frame["frame"] for frame in result["frames"]] == [
        frame["frame"] for frame in manifest["frames"]
    ]


@pytest.mark.parametrize(
    ("mutate", "status", "match"),
    [
        (
            lambda module, root, summary: None,
            _status(print_state="printing"),
            "Printer did not become ready and idle",
        ),
        (
            lambda module, root, summary: None,
            _status(homed_axes="xy"),
            "required axes are not homed: z",
        ),
        (
            lambda module, root, summary: None,
            {
                **_status(),
                "toolhead": {
                    **_status()["toolhead"],
                    "axis_maximum": [100.0, 296.0, 293.75, 0],
                },
            },
            "outside Klipper limits",
        ),
        (
            lambda module, root, summary: module.atomic_write_json(
                Path(summary["state_path"]),
                {
                    **json.loads(Path(summary["state_path"]).read_text()),
                    "state": "acquired",
                },
            ),
            _status(),
            "expected 'prepared'",
        ),
        (
            lambda module, root, summary: module.atomic_write_json(
                root / ".active_job.json", {"job": "other_job"}
            ),
            _status(),
            "another vision job is active",
        ),
    ],
)
def test_start_prepared_job_preflight_failures(
    monkeypatch, tmp_path, mutate, status, match
):
    module = _load_module()
    job_root, summary, manifest = _prepare_job(module, tmp_path)
    args = _start_args(tmp_path, job_root, manifest["job_id"])
    args.ready_timeout = 0.01
    mutate(module, job_root, summary)
    monkeypatch.setattr(module, "query_status", lambda _base_url: status)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    with pytest.raises(Exception, match=match):
        module.start_prepared_job(args)


def test_start_prepared_job_preserves_visiond_failed_state(monkeypatch, tmp_path):
    module = _load_module()
    job_root, summary, manifest = _prepare_job(module, tmp_path)
    args = _start_args(tmp_path, job_root, manifest["job_id"])
    statuses = [_status(print_state="standby"), _status(print_state="error")]

    def fake_query_status(_base_url):
        if len(statuses) > 1:
            return statuses.pop(0)
        return statuses[0]

    def fake_run_gcode(_base_url, _script, *, timeout=60.0):
        state_path = Path(summary["state_path"])
        state = json.loads(state_path.read_text())
        state.update(
            {
                "state": "failed",
                "failure": "capture boom",
                "committed_frame_count": 0,
            }
        )
        module.atomic_write_json(state_path, state)

    monkeypatch.setattr(module, "query_status", fake_query_status)
    monkeypatch.setattr(module, "run_gcode", fake_run_gcode)

    result = module.start_prepared_job(args)

    assert result["ok"] is False
    assert result["state"] == "failed"
    assert result["failure"] == "capture boom"


def test_start_prepared_job_cancel_marks_abandoned_and_clears_lock(monkeypatch, tmp_path):
    module = _load_module()
    job_root, summary, manifest = _prepare_job(module, tmp_path)
    args = _start_args(tmp_path, job_root, manifest["job_id"])
    statuses = [_status(print_state="standby"), _status(print_state="cancelled")]

    def fake_query_status(_base_url):
        if len(statuses) > 1:
            return statuses.pop(0)
        return statuses[0]

    def fake_run_gcode(_base_url, _script, *, timeout=60.0):
        module.atomic_write_json(job_root / ".active_job.json", {"job": manifest["job_id"]})

    monkeypatch.setattr(module, "query_status", fake_query_status)
    monkeypatch.setattr(module, "run_gcode", fake_run_gcode)

    result = module.start_prepared_job(args)

    assert result["ok"] is False
    assert result["state"] == "abandoned"
    assert "virtual SD print ended in cancelled" in result["error"]
    assert not (job_root / ".active_job.json").exists()


def test_start_prepared_job_monitor_timeout_marks_failed(monkeypatch, tmp_path):
    module = _load_module()
    job_root, summary, manifest = _prepare_job(module, tmp_path)
    args = _start_args(tmp_path, job_root, manifest["job_id"], monitor_timeout=0.0)

    def fake_run_gcode(_base_url, _script, *, timeout=60.0):
        module.atomic_write_json(job_root / ".active_job.json", {"job": manifest["job_id"]})

    monkeypatch.setattr(module, "query_status", lambda _base_url: _status())
    monkeypatch.setattr(module, "run_gcode", fake_run_gcode)

    result = module.start_prepared_job(args)

    assert result["ok"] is False
    assert result["state"] == "failed"
    assert "timed out after 0.0s" in result["error"]
    assert not (job_root / ".active_job.json").exists()


def test_run_acquisition_job_prepares_and_starts(monkeypatch, tmp_path):
    module = _load_module()
    commands = []
    captured = {}

    def fake_query_status(_base_url):
        return _status(print_state="complete")

    def fake_run_gcode(_base_url, script, *, timeout=60.0):
        commands.append(script)
        job_id = script.rsplit("/", 1)[-1].removesuffix(".gcode")
        job_dir = tmp_path / "jobs" / job_id
        manifest = json.loads((job_dir / "manifest.json").read_text())
        summary = {
            "job_dir": str(job_dir),
            "state_path": str(job_dir / "state.json"),
        }
        _commit_fake_frames(module, summary, manifest)
        captured["job_id"] = job_id

    monkeypatch.setattr(module, "query_status", fake_query_status)
    monkeypatch.setattr(module, "run_gcode", fake_run_gcode)

    args = SimpleNamespace(
        name="run_acquisition",
        job_root=tmp_path / "jobs",
        job_id="run_acquisition_job",
        x=195.0,
        y=-14.8,
        z=20.0,
        dx="0",
        feedrate=3600.0,
        settle_time=0.2,
        camera="nozzle_cam",
        profile="analysis",
        moonraker_url="http://moonraker.test",
        ready_timeout=1.0,
        virtual_sd_root=tmp_path / "gcodes",
        virtual_sd_subdir="vision_jobs",
        monitor_timeout=5.0,
    )

    result = module.run_acquisition_job(args)

    assert result["ok"] is True
    assert captured["job_id"] == "run_acquisition_job"
    assert commands == [
        "SDCARD_PRINT_FILE FILENAME=vision_jobs/run_acquisition_job.gcode"
    ]
