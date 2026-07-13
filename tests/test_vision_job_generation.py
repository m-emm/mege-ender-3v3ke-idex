import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path


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


def _load_vision_nozzle_align_module():
    spec = importlib.util.spec_from_file_location(
        "vision_nozzle_align_for_test", VISION_NOZZLE_ALIGN_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: dict) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _canonicalize_gcode_for_hash(gcode: str) -> str:
    normalized = gcode.replace("\r\n", "\n").replace("\r", "\n")

    def replace_token(match: re.Match) -> str:
        return f"{match.group(1)}=sha256:PLACEHOLDER"

    return re.sub(r"\b(MANIFEST_HASH|GCODE_HASH)=sha256:\S+", replace_token, normalized)


def test_prepare_job_cli_generates_immutable_manifest_and_gcode(tmp_path, capsys):
    module = _load_vision_nozzle_align_module()
    job_root = tmp_path / "jobs"

    assert (
        module.main(
            [
                "--prepare-job",
                "--job-root",
                str(job_root),
                "--job-id",
                "test_idex_nozzle_job",
                "--name",
                "test",
                "--x",
                "195",
                "--y",
                "-14.8",
                "--z",
                "20",
                "--dx",
                "0,3",
                "--settle-time",
                "0.25",
            ]
        )
        == 0
    )

    summary = json.loads(capsys.readouterr().out)
    job_dir = Path(summary["job_dir"])
    manifest_path = Path(summary["manifest_path"])
    gcode_path = Path(summary["gcode_path"])
    state_path = Path(summary["state_path"])
    events_path = Path(summary["events_path"])

    assert summary["ok"] is True
    assert summary["state"] == "prepared"
    assert summary["frame_count"] == 4
    assert job_dir == job_root / "test_idex_nozzle_job"
    assert manifest_path.exists()
    assert gcode_path.exists()
    assert state_path.exists()
    assert events_path.exists()
    assert (job_dir / "frames").is_dir()
    assert (job_dir / "analysis").is_dir()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    event = json.loads(events_path.read_text(encoding="utf-8").strip())
    gcode = gcode_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in gcode.splitlines() if line.strip()]

    assert manifest["schema_version"] == 1
    assert manifest["kind"] == "idex_nozzle_sweep"
    assert manifest["job_id"] == "test_idex_nozzle_job"
    assert manifest["state"] == "prepared"
    assert manifest["frame_count"] == len(manifest["frames"]) == 4
    assert state["state"] == "prepared"
    assert state["committed_frame_count"] == 0
    assert event["event"] == "prepared"
    assert event["state"] == "prepared"

    sequences = [frame["seq"] for frame in manifest["frames"]]
    frame_ids = [frame["frame"] for frame in manifest["frames"]]
    assert sequences == list(range(len(sequences)))
    assert len(frame_ids) == len(set(frame_ids))
    assert [frame["tool"] for frame in manifest["frames"]] == ["T0", "T0", "T1", "T1"]
    assert all(
        frame["capture_command"] == "VISION_CAPTURE_SYNC"
        for frame in manifest["frames"]
    )

    capture_lines = [
        line for line in lines if line.startswith("VISION_CAPTURE_SYNC ")
    ]
    assert sum(line.startswith("VISION_JOB_BEGIN ") for line in lines) == 1
    assert sum(line.startswith("VISION_JOB_END ") for line in lines) == 1
    assert len(capture_lines) == manifest["frame_count"]
    assert f"EXPECTED_FRAMES={manifest['frame_count']}" in lines[-1]

    for index, line in enumerate(lines):
        if line.startswith("VISION_CAPTURE_SYNC "):
            assert lines[index - 2] == "M400"
            assert lines[index - 1] == "G4 P250"
            assert re.search(r"\bSEQ=\d+\b", line)
            assert re.search(r"\bFRAME=\S+\b", line)
            assert "CAMERA=nozzle_cam" in line
            assert "PROFILE=analysis" in line

    assert not re.search(r"^G28\b", gcode, flags=re.MULTILINE)
    assert not re.search(r"^NOZZLE_CAM_CAPTURE\b", gcode, flags=re.MULTILINE)
    assert not re.search(r"^VISION_CAPTURE\b", gcode, flags=re.MULTILINE)
    assert "IDEX_NOZZLE_VISION_SWEEP" not in gcode
    assert "restore" not in gcode.lower()
    assert "park" not in gcode.lower()
    assert "sha256:PLACEHOLDER" not in gcode
    assert f"MANIFEST_HASH={manifest['manifest_hash']}" in gcode
    assert f"GCODE_HASH={manifest['gcode_hash']}" in gcode

    recomputed_gcode_hash = _sha256_prefixed(
        _canonicalize_gcode_for_hash(gcode).encode("utf-8")
    )
    manifest_for_hash = copy.deepcopy(manifest)
    manifest_for_hash["manifest_hash"] = "sha256:PLACEHOLDER"
    recomputed_manifest_hash = _sha256_prefixed(
        _canonical_json_bytes(manifest_for_hash)
    )
    assert manifest["gcode_hash"] == recomputed_gcode_hash
    assert manifest["manifest_hash"] == recomputed_manifest_hash
    assert summary["gcode_hash"] == manifest["gcode_hash"] == state["gcode_hash"]
    assert (
        summary["manifest_hash"] == manifest["manifest_hash"] == state["manifest_hash"]
    )


def test_prepare_bed_y_job_cli_generates_immutable_manifest_and_gcode(
    tmp_path, capsys
):
    module = _load_vision_nozzle_align_module()
    job_root = tmp_path / "jobs"

    assert (
        module.main(
            [
                "--prepare-bed-y-job",
                "--job-root",
                str(job_root),
                "--job-id",
                "test_bed_y_job",
                "--name",
                "bed_y",
                "--x",
                "-80.4",
                "--y",
                "-14.8",
                "--z",
                "293.75",
                "--y-offsets",
                "0,5,10,15,20",
                "--settle-time",
                "0.25",
            ]
        )
        == 0
    )

    summary = json.loads(capsys.readouterr().out)
    job_dir = Path(summary["job_dir"])
    manifest_path = Path(summary["manifest_path"])
    gcode_path = Path(summary["gcode_path"])
    state_path = Path(summary["state_path"])

    assert summary["ok"] is True
    assert summary["state"] == "prepared"
    assert summary["frame_count"] == 5
    assert job_dir == job_root / "test_bed_y_job"
    assert manifest_path.exists()
    assert gcode_path.exists()
    assert state_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    gcode = gcode_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in gcode.splitlines() if line.strip()]

    assert manifest["kind"] == "nozzle_cam_bed_y_sweep"
    assert manifest["frame_count"] == len(manifest["frames"]) == 5
    assert manifest["measurement_parameters"]["lighting"] == "NOZZLE_CAM_Y_FEATURE_LIGHT"
    assert manifest["measurement_parameters"]["y_offsets"] == [0.0, 5.0, 10.0, 15.0, 20.0]
    sequences = [frame["seq"] for frame in manifest["frames"]]
    frame_ids = [frame["frame"] for frame in manifest["frames"]]
    assert sequences == list(range(5))
    assert frame_ids == ["bed_y_0p0", "bed_y_5p0", "bed_y_10p0", "bed_y_15p0", "bed_y_20p0"]
    assert len(frame_ids) == len(set(frame_ids))
    assert [frame["phase"] for frame in manifest["frames"]] == ["bed_y_sweep"] * 5
    assert [frame["target"] for frame in manifest["frames"]] == ["bed_features"] * 5
    assert [frame["y_offset"] for frame in manifest["frames"]] == [0.0, 5.0, 10.0, 15.0, 20.0]
    assert all(frame["lighting"] == "NOZZLE_CAM_Y_FEATURE_LIGHT" for frame in manifest["frames"])
    assert all(frame["capture_command"] == "VISION_CAPTURE_SYNC" for frame in manifest["frames"])

    capture_lines = [
        line for line in lines if line.startswith("VISION_CAPTURE_SYNC ")
    ]
    assert sum(line.startswith("VISION_JOB_BEGIN ") for line in lines) == 1
    assert sum(line.startswith("VISION_JOB_END ") for line in lines) == 1
    assert len(capture_lines) == manifest["frame_count"]
    assert "NOZZLE_CAM_Y_FEATURE_LIGHT" in lines
    assert "NOZZLE_CAM_ANALYSIS_LIGHT" not in lines
    assert not re.search(r"^G28\b", gcode, flags=re.MULTILINE)
    assert not re.search(r"^NOZZLE_CAM_CAPTURE\b", gcode, flags=re.MULTILINE)
    assert not re.search(r"^VISION_CAPTURE\b", gcode, flags=re.MULTILINE)
    assert "restore" not in gcode.lower()
    assert "park" not in gcode.lower()
    assert "sha256:PLACEHOLDER" not in gcode

    recomputed_gcode_hash = _sha256_prefixed(
        _canonicalize_gcode_for_hash(gcode).encode("utf-8")
    )
    manifest_for_hash = copy.deepcopy(manifest)
    manifest_for_hash["manifest_hash"] = "sha256:PLACEHOLDER"
    recomputed_manifest_hash = _sha256_prefixed(
        _canonical_json_bytes(manifest_for_hash)
    )
    assert manifest["gcode_hash"] == recomputed_gcode_hash
    assert manifest["manifest_hash"] == recomputed_manifest_hash
    assert summary["gcode_hash"] == manifest["gcode_hash"] == state["gcode_hash"]


def test_prepare_nozzle_z_job_cli_generates_two_phase_manifest_and_gcode(
    tmp_path, capsys
):
    module = _load_vision_nozzle_align_module()
    job_root = tmp_path / "jobs"

    assert (
        module.main(
            [
                "--prepare-nozzle-z-job",
                "--job-root",
                str(job_root),
                "--job-id",
                "test_nozzle_z_job",
                "--name",
                "nozzle_z",
                "--bed-y-x",
                "-80.4",
                "--bed-y-y",
                "-14.8",
                "--bed-y-z",
                "293.75",
                "--tool-x",
                "195",
                "--tool-y",
                "-14.8",
                "--travel-z",
                "20",
                "--y-offsets",
                "0,5,10,15,20",
                "--x-offsets",
                "0,3,6,9,12",
                "--z-values",
                "1,2,4,8",
                "--bed-feature-z-mm",
                "-0.1",
                "--settle-time",
                "0.25",
            ]
        )
        == 0
    )

    summary = json.loads(capsys.readouterr().out)
    job_dir = Path(summary["job_dir"])
    manifest_path = Path(summary["manifest_path"])
    gcode_path = Path(summary["gcode_path"])
    state_path = Path(summary["state_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    gcode = gcode_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in gcode.splitlines() if line.strip()]

    assert summary["ok"] is True
    assert summary["state"] == "prepared"
    assert summary["frame_count"] == 45
    assert job_dir == job_root / "test_nozzle_z_job"
    assert manifest["kind"] == "nozzle_cam_nozzle_z_sweep"
    assert manifest["frame_count"] == len(manifest["frames"]) == 45
    assert state["state"] == "prepared"
    assert manifest["measurement_parameters"]["bed_feature_z_mm"] == -0.1
    assert manifest["measurement_parameters"]["z_capture_order"] == [8.0, 4.0, 2.0, 1.0]
    assert manifest["measurement_parameters"]["lighting"] == {
        "bed_y_sweep": {"macro": "NOZZLE_CAM_Y_FEATURE_LIGHT"},
        "tool_xz_sweep": {"macro": "NOZZLE_CAM_ANALYSIS_LIGHT"},
    }

    sequences = [frame["seq"] for frame in manifest["frames"]]
    frame_ids = [frame["frame"] for frame in manifest["frames"]]
    assert sequences == list(range(45))
    assert len(frame_ids) == len(set(frame_ids))
    assert [frame["phase"] for frame in manifest["frames"][:5]] == ["bed_y_sweep"] * 5
    assert [frame["phase"] for frame in manifest["frames"][5:]] == ["tool_xz_sweep"] * 40
    assert all(
        frame["lighting"] == "NOZZLE_CAM_Y_FEATURE_LIGHT"
        for frame in manifest["frames"][:5]
    )
    assert all(
        frame["lighting"] == "NOZZLE_CAM_ANALYSIS_LIGHT"
        for frame in manifest["frames"][5:]
    )
    assert [frame["z_sample"] for frame in manifest["frames"][5:9]] == [
        8.0,
        4.0,
        2.0,
        1.0,
    ]
    assert [frame["capture_command"] for frame in manifest["frames"]] == [
        "VISION_CAPTURE_SYNC"
    ] * 45

    capture_lines = [
        line for line in lines if line.startswith("VISION_CAPTURE_SYNC ")
    ]
    assert sum(line.startswith("VISION_JOB_BEGIN ") for line in lines) == 1
    assert sum(line.startswith("VISION_JOB_END ") for line in lines) == 1
    assert len(capture_lines) == manifest["frame_count"]
    first_bed_capture = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("VISION_CAPTURE_SYNC ") and "FRAME=bed_y_0p0" in line
    )
    last_bed_capture = max(
        index
        for index, line in enumerate(lines)
        if line.startswith("VISION_CAPTURE_SYNC ") and "FRAME=bed_y_" in line
    )
    first_tool_capture = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("VISION_CAPTURE_SYNC ") and "FRAME=t0_x0p0_z8p0" in line
    )
    y_light = lines.index("NOZZLE_CAM_Y_FEATURE_LIGHT")
    tool_light = lines.index("NOZZLE_CAM_ANALYSIS_LIGHT")
    assert y_light < first_bed_capture
    assert last_bed_capture < tool_light < first_tool_capture
    assert lines[y_light + 1] == "G4 P750"
    assert lines[tool_light + 1] == "G4 P750"
    assert "G1 X198.000 Y-14.800 Z20.000 F3600" in lines

    for index, line in enumerate(lines):
        if line.startswith("VISION_CAPTURE_SYNC "):
            assert lines[index - 2] == "M400"
            assert lines[index - 1] == "G4 P250"

    assert not re.search(r"^G28\b", gcode, flags=re.MULTILINE)
    assert not re.search(r"^NOZZLE_CAM_CAPTURE\b", gcode, flags=re.MULTILINE)
    assert not re.search(r"^VISION_CAPTURE\b", gcode, flags=re.MULTILINE)
    assert "restore" not in gcode.lower()
    assert "park" not in gcode.lower()
    assert "sha256:PLACEHOLDER" not in gcode

    recomputed_gcode_hash = _sha256_prefixed(
        _canonicalize_gcode_for_hash(gcode).encode("utf-8")
    )
    manifest_for_hash = copy.deepcopy(manifest)
    manifest_for_hash["manifest_hash"] = "sha256:PLACEHOLDER"
    recomputed_manifest_hash = _sha256_prefixed(
        _canonical_json_bytes(manifest_for_hash)
    )
    assert manifest["gcode_hash"] == recomputed_gcode_hash
    assert manifest["manifest_hash"] == recomputed_manifest_hash
    assert summary["gcode_hash"] == manifest["gcode_hash"] == state["gcode_hash"]
    assert (
        summary["manifest_hash"] == manifest["manifest_hash"] == state["manifest_hash"]
    )


def test_prepared_job_frames_can_be_adapted_for_later_analysis(tmp_path, capsys):
    module = _load_vision_nozzle_align_module()
    job_root = tmp_path / "jobs"

    assert (
        module.main(
            [
                "--prepare-job",
                "--job-root",
                str(job_root),
                "--job-id",
                "analysis_adapter_job",
                "--dx",
                "0",
            ]
        )
        == 0
    )

    summary = json.loads(capsys.readouterr().out)
    manifest_path = Path(summary["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames_dir = manifest_path.parent / "frames"

    for frame in manifest["frames"]:
        (frames_dir / f"{frame['frame']}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        (frames_dir / f"{frame['frame']}.json").write_text(
            json.dumps({"job_seq": frame["seq"]}) + "\n",
            encoding="utf-8",
        )

    records = module.load_job_frames_for_analysis(manifest_path)

    assert len(records) == manifest["frame_count"]
    assert [record["prefix"] for record in records] == [
        frame["frame"] for frame in manifest["frames"]
    ]
    assert [record["tool"] for record in records] == ["t0", "t1"]
    assert records[0]["macro"] == "T0"
    assert records[1]["macro"] == "T1"
    assert all(Path(record["image_path"]).exists() for record in records)
    assert all(Path(record["metadata_path"]).exists() for record in records)
