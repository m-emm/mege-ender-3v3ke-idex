import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
FILES = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)


def _load(monkeypatch, tmp_path):
    calibration_root = tmp_path / "vision" / "calibration"
    gcode_root = tmp_path / "gcodes" / "vision_jobs"
    framebuffer = tmp_path / "framebuffer"
    framebuffer.mkdir(parents=True)
    image = np.full((120, 200, 3), 100, dtype=np.uint8)
    assert cv2.imwrite(str(framebuffer / "latest.jpg"), image)
    (framebuffer / "latest.json").write_text(
        json.dumps(
            {
                "frame_seq": 12,
                "width": 200,
                "height": 120,
                "camera_profile": {"profile_names": ["analysis"]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VISION_CALIBRATION_ROOT", str(calibration_root))
    monkeypatch.setenv("VISION_CALIBRATION_GCODE_ROOT", str(gcode_root))
    monkeypatch.setenv(
        "VISION_CALIBRATION_REGISTRY", str(FILES / "vision_job_types.json")
    )
    monkeypatch.setenv(
        "VISION_CAMERA_PROFILE_FILE", str(FILES / "nozzle_cam_profiles.json")
    )
    monkeypatch.setenv(
        "VISION_CALIBRATION_PRIOR_FILE",
        str(FILES / "vision_calibration_priors.json"),
    )
    monkeypatch.setenv("VISION_FRAMEBUFFER_DIR", str(framebuffer))
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    name = f"vision_calibration_job_test_{len(sys.modules)}"
    spec = importlib.util.spec_from_file_location(name, FILES / "vision_calibration.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _status(*, homed="xyz", virtual_sd=False, y_max=230.0):
    return {
        "webhooks": {"state": "ready"},
        "print_stats": {"state": "standby", "filename": ""},
        "virtual_sdcard": {"is_active": virtual_sd, "progress": 0.0},
        "toolhead": {
            "homed_axes": homed,
            "position": [0.0, 0.0, 20.0, 0.0],
            "axis_minimum": [-80.4, -14.8, 0.0],
            "axis_maximum": [357.5, y_max, 293.75],
        },
        "gcode_move": {"gcode_position": [0.0, 0.0, 20.0, 0.0]},
        "configfile": {
            "save_config_pending": False,
            "settings": {
                "stepper_x": {
                    "position_min": -80.4,
                    "position_endstop": -80.4,
                    "position_max": 230.0,
                },
                "stepper_y": {
                    "position_min": -14.8,
                    "position_endstop": -14.8,
                    "position_max": 230.0,
                    "rotation_distance": 40.0,
                    "microsteps": 16,
                },
                "stepper_z": {
                    "position_min": 0.0,
                    "position_endstop": 293.75,
                    "position_max": 293.75,
                },
                "dual_carriage": {
                    "position_min": 110.0,
                    "position_endstop": 357.532,
                    "position_max": 357.532,
                },
                "gcode_macro nozzle_cam_y_feature_light": {
                    "gcode": "VISION_LIGHT_OFF\nSET_LED LED=vision_light INDEX=2 RED=0.45"
                },
                "gcode_macro nozzle_cam_analysis_light": {
                    "gcode": "VISION_LIGHT_OFF\nSET_LED LED=vision_light INDEX=5 RED=0.20"
                },
            },
        },
        "gcode_macro _IDEX_CONFIG_FINGERPRINT": {"source_sha256": "sha256:active"},
        "extruder": {"temperature": 24.0, "target": 0.0},
        "extruder1": {"temperature": 24.0, "target": 0.0},
        "heater_bed": {"temperature": 23.0, "target": 0.0},
    }


def _publish_test_bed_y_fact(module):
    fact_set = {
        "schema": module.FACT_SET_SCHEMA,
        "schema_version": 1,
        "fact_set_id": "seed:test-bed-y",
        "job_id": "seed:test-bed-y",
        "analysis_run_id": "revision-1",
        "analysis_hash": module.canonical_hash({"test": "bed-y"}),
        "created_at_utc": "2026-07-30T00:00:00+00:00",
        "accepted": True,
        "publication_eligible": True,
        "applicability_hash": module.canonical_hash({"test": "bed-y-scope"}),
        "facts": [
            {
                "name": "camera.nozzle_cam.bed_tab.y_parallax_model",
                "definition_version": 4,
                "role": "coordinate_system",
                "dependencies": [],
                "value_items": [
                    {
                        "field": "axis_vector_px_per_mm",
                        "role": "coordinate_system",
                    },
                    {"field": "observed_target", "role": "diagnostic"},
                ],
                "value": {
                    "axis_vector_px_per_mm": [-0.22, -10.5],
                    "observed_target": {
                        "reference_line_px": [690.0, 426.0, 811.0],
                        "reference_seam_y_px": 425.0,
                        "reference_tab_side": {
                            "x0": 925.0,
                            "y0": 432.0,
                            "x1": 960.0,
                            "y1": 525.0,
                        },
                    },
                },
            }
        ],
        "provenance": {"source": "test"},
        "fact_set_hash": "",
    }
    fact_set["fact_set_hash"] = module.content_hash(fact_set, "fact_set_hash")
    path = (
        module.CALIBRATION_ROOT
        / "seeds"
        / fact_set["fact_set_hash"][7:23]
        / "fact_set.json"
    )
    module.atomic_write_json(path, fact_set, immutable=True)
    module.publish_seed_fact_set(module.CALIBRATION_ROOT, path)
    return fact_set


def _publish_test_partial_bed_fact(module, bed_y):
    fact_set = {
        "schema": module.FACT_SET_SCHEMA,
        "schema_version": 1,
        "fact_set_id": "seed:test-partial-bed",
        "job_id": "seed:test-partial-bed",
        "analysis_run_id": "revision-1",
        "analysis_hash": module.canonical_hash({"test": "partial-bed"}),
        "created_at_utc": "2026-07-30T00:00:00+00:00",
        "accepted": True,
        "publication_eligible": True,
        "applicability_hash": module.canonical_hash({"test": "partial-bed-scope"}),
        "facts": [
            {
                "name": "camera.nozzle_cam.partial_bed_coordinate_system",
                "definition_version": 4,
                "role": "coordinate_system",
                "dependencies": [
                    {
                        "fact_name": "camera.nozzle_cam.bed_tab.y_parallax_model",
                        "fact_set_hash": bed_y["fact_set_hash"],
                    }
                ],
                "value_items": [
                    {"field": "corner_pixel_xy_px", "role": "coordinate_system"},
                    {"field": "corner_printer_xyz_mm", "role": "coordinate_system"},
                    {
                        "field": "image_y_axis_vector_px_per_mm",
                        "role": "coordinate_system",
                    },
                    {
                        "field": "tab_to_print_plane_z_mm",
                        "role": "coordinate_system",
                    },
                ],
                "value": {
                    "corner_pixel_xy_px": [922.0, 216.5],
                    "corner_printer_xyz_mm": [170.0, -20.0, 0.0],
                    "image_y_axis_vector_px_per_mm": [-0.22, -10.5],
                    "tab_to_print_plane_z_mm": 0.0,
                },
            }
        ],
        "provenance": {"source": "test"},
        "fact_set_hash": "",
    }
    fact_set["fact_set_hash"] = module.content_hash(fact_set, "fact_set_hash")
    path = (
        module.CALIBRATION_ROOT
        / "seeds"
        / fact_set["fact_set_hash"][7:23]
        / "fact_set.json"
    )
    module.atomic_write_json(path, fact_set, immutable=True)
    module.publish_seed_fact_set(module.CALIBRATION_ROOT, path)
    return fact_set


def test_prepare_red_marker_sweep_binds_facts_and_discards_transition_frames(
    monkeypatch, tmp_path
):
    module = _load(monkeypatch, tmp_path)
    bed_y = _publish_test_bed_y_fact(module)
    partial = _publish_test_partial_bed_fact(module, bed_y)
    result = module.prepare_job(
        "red_marker",
        job_type="idex_tool_red_marker_x_sweep",
        expected_fingerprint="sha256:active",
        status=_status(),
    )
    job_dir = Path(result["job_dir"])
    manifest = json.loads((job_dir / "manifest.json").read_text())
    gcode = (job_dir / "acquisition.gcode").read_text()

    assert manifest["frame_count"] == 12
    assert [(frame["tool"], frame["x_mm"]) for frame in manifest["frames"]] == [
        (tool, x)
        for tool in ("T0", "T1")
        for x in (160, 170, 180, 190, 200, 210)
    ]
    assert all(frame["discard_fresh_frames"] == 1 for frame in manifest["frames"])
    assert manifest["active_calibration_snapshot"] == {
        "t0_x_endstop_mm": -80.4,
        "t1_x_endstop_mm": 357.532,
    }
    bindings = {item["requirement"]: item for item in manifest["input_facts"]}
    assert bindings["bed_y_model"]["fact_set_hash"] == bed_y["fact_set_hash"]
    assert (
        bindings["partial_bed_coordinate_system"]["fact_set_hash"]
        == partial["fact_set_hash"]
    )
    assert "G28" not in gcode
    assert gcode.count("VISION_CAPTURE_SYNC ") == 12
    assert gcode.index("\nT0\n") < gcode.index("FRAME=00_t0_x160")
    assert gcode.index("\nT1\n") < gcode.index("FRAME=06_t1_x160")
    assert "G1 Z5.000000 F3600.000\nT0\nG1 Z5.000000 F3600.000" in gcode
    assert gcode.rindex("\nT0\n") < gcode.index("VISION_JOB_END")
    assert gcode.index("VISION_JOB_END") < gcode.index("VISION_LIGHT_OFF")


def test_prepare_resolves_active_limits_and_generates_exact_motion(
    monkeypatch, tmp_path
):
    module = _load(monkeypatch, tmp_path)
    result = module.prepare_job(
        "unit", expected_fingerprint="sha256:active", status=_status()
    )
    job_dir = Path(result["job_dir"])
    manifest = json.loads((job_dir / "manifest.json").read_text())
    gcode = (job_dir / "acquisition.gcode").read_text()

    assert manifest["motion"]["resolved_pose"] == {
        "x_mm": -80.4,
        "y_base_mm": -14.8,
        "y_endstop_mm": -14.8,
        "z_mm": 293.75,
    }
    assert [frame["y_offset_mm"] for frame in manifest["frames"]] == [
        0,
        10,
        20,
        20,
        10,
        0,
    ]
    assert [frame["pass"] for frame in manifest["frames"]] == [
        "forward",
        "forward",
        "forward",
        "reverse",
        "reverse",
        "reverse",
    ]
    assert manifest["publish_on_accept"] is True
    assert manifest["definition_version"] == 4
    assert manifest["localizer"] == {
        "kind": "bed_tab_top_edge",
        "version": 1,
    }
    assert manifest["applicability"]["localizer"] == manifest["localizer"]
    assert "G28" not in gcode
    assert gcode.count("VISION_CAPTURE_SYNC ") == 6
    assert gcode.index("\nT0\n") < gcode.index("VISION_CAPTURE_SYNC ")
    assert gcode.index("NOZZLE_CAM_Y_FEATURE_LIGHT") < gcode.index("\nT0\n")
    assert gcode.rindex("G1 Y-14.800000") < gcode.index("VISION_JOB_END")
    assert gcode.index("VISION_JOB_END") < gcode.index("VISION_LIGHT_OFF")
    assert gcode.count("F3600.000") == 8
    assert (module.GCODE_ROOT / f"{manifest['job_id']}.gcode").is_file()
    assert (module.VISION_ROOT / "index.html").is_file()


def test_prepare_corner_binds_current_facts_and_generates_fixed_duplicates(
    monkeypatch, tmp_path
):
    module = _load(monkeypatch, tmp_path)
    module.sync_seed_facts()
    bed_y = _publish_test_bed_y_fact(module)
    result = module.prepare_job(
        "corner",
        job_type="nozzle_cam_bed_tab_corner",
        expected_fingerprint="sha256:active",
        status=_status(),
    )
    job_dir = Path(result["job_dir"])
    manifest = json.loads((job_dir / "manifest.json").read_text())
    gcode = (job_dir / "acquisition.gcode").read_text()

    assert manifest["job_type"] == "nozzle_cam_bed_tab_corner"
    assert manifest["definition_version"] == 1
    assert manifest["frame_count"] == 5
    assert [frame["duplicate_index"] for frame in manifest["frames"]] == list(range(5))
    assert (
        len({tuple(frame["commanded_position_mm"]) for frame in manifest["frames"]})
        == 1
    )
    assert manifest["frames"][0]["commanded_position_mm"] == pytest.approx(
        [
            -80.4,
            5.2,
            293.75,
        ]
    )
    bindings = {item["requirement"]: item for item in manifest["input_facts"]}
    assert bindings["bed_y_model"]["fact_set_hash"] == bed_y["fact_set_hash"]
    assert set(bindings) == {
        "bed_y_model",
        "bed_tab_corner_prior",
        "tab_plane_z",
    }
    assert manifest["corner_reference"]["corner_printer_xyz_mm"] == [
        170.0,
        -20.0,
        0.0,
    ]
    assert manifest["corner_reference"]["prior_provisional"] is True
    assert (
        np.linalg.norm(
            np.asarray(manifest["corner_reference"]["expected_corner_px"])
            - np.asarray([917.96, 215.0])
        )
        < 1.0
    )
    assert gcode.count("VISION_CAPTURE_SYNC ") == 5
    assert gcode.count("G1 Y5.200000") == 1
    assert "G28" not in gcode


def test_corner_analysis_publishes_dependency_bound_partial_coordinate_system(
    monkeypatch, tmp_path
):
    module = _load(monkeypatch, tmp_path)
    module.sync_seed_facts()
    _publish_test_bed_y_fact(module)
    prepared = module.prepare_job(
        "corner-analysis",
        job_type="nozzle_cam_bed_tab_corner",
        expected_fingerprint="sha256:active",
        status=_status(),
    )
    job_dir = Path(prepared["job_dir"])
    manifest = json.loads((job_dir / "manifest.json").read_text())
    source = module.FRAMEBUFFER_DIR / "latest.jpg"
    for frame in manifest["frames"]:
        image_path = job_dir / "frames" / f"{frame['frame']}.jpg"
        image_path.write_bytes(source.read_bytes())
        (job_dir / "frames" / f"{frame['frame']}.json").write_text(
            json.dumps(
                {
                    "job_seq": frame["seq"],
                    "capture_errors": 0,
                    "width": 200,
                    "height": 120,
                    "camera_profile": {"profile_names": ["analysis"]},
                    "framebuffer_seq": 200 + frame["seq"],
                    "sha256": module.sha256_file(image_path),
                }
            ),
            encoding="utf-8",
        )
    module._update_state(job_dir, state="acquired", committed_frame_count=5)
    monkeypatch.setattr(
        module,
        "_analysis_run_id",
        lambda _manifest: "20260730T130000.000000Z-corner",
    )

    def accepted(_frames, output_dir, *, expected_corner_px, localizer):
        assert expected_corner_px == manifest["corner_reference"]["expected_corner_px"]
        assert localizer == {"kind": "bed_tab_corner", "version": 1}
        output_dir.mkdir(parents=True)
        localization = output_dir / "corner_localization.jpg"
        duplicates = output_dir / "corner_duplicate_registration.jpg"
        assert cv2.imwrite(
            str(localization), np.full((120, 200, 3), 80, dtype=np.uint8)
        )
        assert cv2.imwrite(str(duplicates), np.full((120, 200, 3), 90, dtype=np.uint8))
        return {
            "accepted": True,
            "reasons": [],
            "warnings": [],
            "missing_frames": [],
            "localizer": {"kind": "bed_tab_corner", "version": 1},
            "expected_corner_px": expected_corner_px,
            "selected_candidate": {
                "candidate_id": "corner_00",
                "corner_px": [921.8, 215.5],
            },
            "expected_distance_px": 4.5,
            "corner_pixel_xy_px": [921.8, 215.5],
            "usable_frame_count": 5,
            "line_confirmation_count": 5,
            "minimum_correlation": 0.98,
            "median_correlation": 0.995,
            "repeatability_rms_px": 0.2,
            "repeatability_max_px": 0.35,
            "maximum_representation_spread_px": 0.1,
            "maximum_forward_reverse_disagreement_px": 0.15,
            "candidates_by_frame": [],
            "observations": [],
            "artifacts": {
                "corner_localization": {
                    "path": str(localization),
                    "sha256": module.sha256_file(localization),
                },
                "corner_duplicate_registration": {
                    "path": str(duplicates),
                    "sha256": module.sha256_file(duplicates),
                },
            },
        }

    monkeypatch.setattr(module, "analyze_bed_tab_corner", accepted)
    result = module.analyze_job(manifest["job_id"])
    assert result["state"] == "accepted"
    fact_set = json.loads(Path(result["fact_set_path"]).read_text())
    fact = fact_set["facts"][0]
    assert fact["name"] == "camera.nozzle_cam.partial_bed_coordinate_system"
    assert fact["role"] == "coordinate_system"
    assert fact["value"]["corner_pixel_xy_px"] == [921.8, 215.5]
    assert fact["value"]["corner_printer_xyz_mm"] == [170.0, -20.0, 0.0]
    assert fact["value"]["image_y_axis_vector_px_per_mm"] == [-0.22, -10.5]
    assert fact["dependencies"] == [
        {
            "fact_name": item["fact_name"],
            "fact_set_hash": item["fact_set_hash"],
        }
        for item in manifest["input_facts"]
    ]
    catalog = json.loads((module.CALIBRATION_ROOT / "catalog.json").read_text())
    assert (
        catalog["heads"]["camera.nozzle_cam.partial_bed_coordinate_system"][
            "fact_set_hash"
        ]
        == fact_set["fact_set_hash"]
    )
    dashboard = (module.VISION_ROOT / "index.html").read_text()
    assert "[921.8000, 215.5000] px" in dashboard
    assert "[170.0000, -20.0000, 0.0000] mm" in dashboard
    assert "Corner repeatability" not in dashboard
    job_page = (job_dir / "index.html").read_text()
    assert "Automatically localized bed-tab corner" in job_page
    assert "Duplicate registration and line confirmation" in job_page


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (_status(homed="xy"), "already be homed"),
        (_status(virtual_sd=True), "virtual-SD"),
        (_status(y_max=0.0), "outside active limits"),
    ],
)
def test_prepare_rejects_unsafe_preconditions(monkeypatch, tmp_path, status, message):
    module = _load(monkeypatch, tmp_path)
    with pytest.raises(module.VisionCalibrationError, match=message):
        module.prepare_job("unsafe", status=status)


def test_prepare_rejects_fingerprint_drift(monkeypatch, tmp_path):
    module = _load(monkeypatch, tmp_path)
    with pytest.raises(module.VisionCalibrationError, match="does not match"):
        module.prepare_job(
            "drift",
            expected_fingerprint="sha256:other",
            status=_status(),
        )


def test_rejected_report_handles_unavailable_vector(monkeypatch, tmp_path):
    module = _load(monkeypatch, tmp_path)
    report = module._report_markdown(
        {"job_id": "job"},
        {
            "analysis_run_id": "analysis",
            "state": "rejected",
        },
        {
            "axis_vector_px_per_mm": None,
            "localizer": {"kind": "bed_tab_top_edge", "version": 1},
            "discovered_candidate_count": 0,
            "selected_candidate_id": None,
            "reasons": [
                "no discovered bed-tab top edge passed geometry and motion validation"
            ],
        },
    )
    assert "Axis vector: unavailable" in report
    assert (
        "no discovered bed-tab top edge passed geometry and motion validation" in report
    )


def test_accepted_analysis_is_published_immediately(monkeypatch, tmp_path):
    module = _load(monkeypatch, tmp_path)
    prepared = module.prepare_job(
        "auto_publish",
        expected_fingerprint="sha256:active",
        status=_status(),
    )
    job_dir = Path(prepared["job_dir"])
    manifest = json.loads((job_dir / "manifest.json").read_text())
    source = module.FRAMEBUFFER_DIR / "latest.jpg"
    for frame in manifest["frames"]:
        image_path = job_dir / "frames" / f"{frame['frame']}.jpg"
        image_path.write_bytes(source.read_bytes())
        sidecar = {
            "job_seq": frame["seq"],
            "capture_errors": 0,
            "width": 200,
            "height": 120,
            "camera_profile": {"profile_names": ["analysis"]},
            "framebuffer_seq": 100 + frame["seq"],
            "sha256": module.sha256_file(image_path),
        }
        (job_dir / "frames" / f"{frame['frame']}.json").write_text(
            json.dumps(sidecar), encoding="utf-8"
        )
    module._update_state(job_dir, state="acquired", committed_frame_count=6)
    monkeypatch.setattr(
        module,
        "_analysis_run_id",
        lambda _manifest: "20260730T120000.000000Z-auto",
    )

    def accepted(_frames, output_dir, *, offsets_mm, localizer):
        assert offsets_mm == [0.0, 10.0, 20.0, 20.0, 10.0, 0.0]
        assert localizer == {"kind": "bed_tab_top_edge", "version": 1}
        output_dir.mkdir(parents=True)
        localization_path = output_dir / "edge_localization.jpg"
        overlay_path = output_dir / "edge_tracking_overlay.jpg"
        assert cv2.imwrite(
            str(localization_path),
            np.full((120, 200, 3), 80, dtype=np.uint8),
        )
        assert cv2.imwrite(
            str(overlay_path),
            np.full((120, 200, 3), 90, dtype=np.uint8),
        )
        return {
            "accepted": True,
            "reasons": [],
            "warnings": ["duplicate-position disagreement is above 1.0 px"],
            "missing_frames": [],
            "usable_frame_count": 6,
            "commanded_span_mm": 20.0,
            "axis_vector_px_per_mm": [0.1, -11.3],
            "scale_px_per_mm": 11.3004,
            "inverse_scale_mm_per_px": 0.08849,
            "angle_deg": -89.493,
            "localizer": {
                "kind": "bed_tab_top_edge",
                "version": 1,
                "configured_position": None,
            },
            "discovered_candidate_count": 4,
            "selected_candidate_id": "edge_02",
            "observed_target": {
                "localizer": {
                    "kind": "bed_tab_top_edge",
                    "version": 1,
                },
                "candidate_id": "edge_02",
                "reference_line_px": [50.0, 60.0, 150.0],
                "duplicate_line_px": [51.0, 60.5, 151.0],
                "tracking_strip_px": [45, 45, 155, 75],
                "reference_seam_y_px": 60.0,
                "span_fraction": 0.5,
                "duplicate_y_delta_px": 0.5,
                "duplicate_overlap_fraction": 0.99,
                "edge_pair_score": 120.0,
                "edge_pair_ratio": 2.0,
                "reference_tab_side": {
                    "x0": 150.0,
                    "y0": 60.0,
                    "x1": 165.0,
                    "y1": 100.0,
                    "geometry_score": 80.0,
                },
                "duplicate_tab_side": {
                    "x0": 151.0,
                    "y0": 60.5,
                    "x1": 166.0,
                    "y1": 100.5,
                    "geometry_score": 79.0,
                },
            },
            "minimum_correlation": 0.91,
            "median_correlation": 0.97,
            "joint_residual_rms_px": 0.5,
            "joint_residual_rms_mm": 0.044,
            "duplicate_position_disagreement_px": 1.1,
            "duplicate_position_disagreement_mm": 0.097,
            "forward_vector_px_per_mm": [0.1, -11.3],
            "reverse_vector_px_per_mm": [0.11, -11.29],
            "forward_reverse_magnitude_delta_fraction": 0.001,
            "forward_reverse_angle_delta_deg": 0.1,
            "candidates": [],
            "observations": [],
            "artifacts": {
                "edge_localization": {
                    "path": str(localization_path),
                    "sha256": module.sha256_file(localization_path),
                },
                "edge_tracking_overlay": {
                    "path": str(overlay_path),
                    "sha256": module.sha256_file(overlay_path),
                },
            },
        }

    monkeypatch.setattr(module, "analyze_bed_tab_y_scale", accepted)
    result = module.analyze_job(manifest["job_id"])

    assert result["state"] == "accepted"
    assert result["publication"]["fact_set_hash"]
    catalog = json.loads((module.CALIBRATION_ROOT / "catalog.json").read_text())
    head = catalog["heads"]["camera.nozzle_cam.bed_tab.y_parallax_model"]
    assert head["fact_set_hash"] == result["publication"]["fact_set_hash"]
    assert len(list((module.CALIBRATION_ROOT / "publications").glob("*.json"))) == 1
    fact_set = json.loads(
        (job_dir / "analysis" / result["analysis_run_id"] / "fact_set.json").read_text()
    )
    fact = fact_set["facts"][0]
    assert fact["definition_version"] == 4
    assert fact["role"] == "coordinate_system"
    assert {item["field"]: item["role"] for item in fact["value_items"]} == {
        "axis_vector_px_per_mm": "coordinate_system",
        "camera": "diagnostic",
        "profile": "diagnostic",
        "light_macro": "diagnostic",
        "image_dimensions_px": "diagnostic",
        "applicability_hash": "diagnostic",
        "observed_target": "diagnostic",
        "quality": "diagnostic",
        "supporting_artifact_hashes": "diagnostic",
    }
    assert fact["value"]["observed_target"]["candidate_id"] == "edge_02"
    assert "accepted_patch_count" not in json.dumps(fact)
    job_page = (job_dir / "index.html").read_text()
    assert "Latest analysis" in job_page
    assert "Automatically discovered bed-tab top edge" in job_page
    assert "Measured edge versus fitted motion" in job_page
    assert 'class="hero-overlay"' in job_page
    assert job_page.index("Latest analysis") < job_page.index("<h2>Frames</h2>")
    dashboard = (module.VISION_ROOT / "index.html").read_text()
    facts_report = (
        module.VISION_ROOT / "calibration" / "facts" / "index.html"
    ).read_text()
    for page in (dashboard, facts_report):
        assert "Nozzle camera — bed-tab Y parallax" in page
        assert "[0.100000, -11.300000] px/mm" in page
        assert "11.300442 px/mm" in page
        assert "coordinate system" in page
    for diagnostic_text in (
        "Fit RMS",
        "Duplicate discrepancy",
        "Registration correlation",
        "Sweep coverage",
        "Image size",
        "Raw fact value and provenance",
        "duplicate-position disagreement is above 1.0 px",
    ):
        assert diagnostic_text not in dashboard
        assert diagnostic_text in facts_report
    assert "Full fact and diagnostics" in dashboard
    assert "camera.nozzle_cam.bed_tab.y_parallax_model" not in dashboard
    assert "camera.nozzle_cam.bed_tab.y_parallax_model" in facts_report
    assert "0.500 px / 0.0440 mm" in facts_report
    assert "0.910 minimum / 0.970 median" in facts_report
    assert "Coordinate-system fields:" in facts_report
    assert "Diagnostic fields:" in facts_report
    assert result["analysis_run_id"] not in dashboard
    assert result["analysis_run_id"] in facts_report
    assert "Open current facts report" in dashboard
    assert "Open calibration catalog JSON" in facts_report
    assert "../jobs/" in facts_report


def test_legacy_public_interfaces_and_runtime_fields_are_absent():
    capture = (FILES / "vision_capture.py").read_text()
    extra = (
        REPO_ROOT / "klipper_setup/klipper_host/klippy/extras/vision.py"
    ).read_text()
    template = (
        REPO_ROOT / "klipper_setup/klipper_config/printer.cfg.template"
    ).read_text()
    generator = (
        REPO_ROOT / "klipper_setup/klipper_config/generate_printer_cfg.py"
    ).read_text()
    combined = "\n".join((capture, extra, template, generator))
    for legacy in (
        "IDEX_BED_Y_VISION_SWEEP",
        "IDEX_MEASURE_BED_Y",
        "VISION_MEASURE_BED_Y",
        "--prepare-bed-y-job",
        "--run-bed-y-job",
        "printer_to_image",
        "bed_y_feature",
        "vision_nozzle_align",
        "vision_bed_y",
    ):
        assert legacy not in combined
    assert "IDEX_BED_TAB_Y_SCALE_CALIBRATE" in template
    assert "idex_bed_tab_y_scale_calibrate" in capture
