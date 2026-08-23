import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml


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


def _module(filename, name):
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(name, FILES / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fact_set(
    graph,
    *,
    fact_name,
    value,
    value_roles,
    serial,
    fact_role="coordinate_system",
):
    record = {
        "schema": graph.FACT_SET_SCHEMA,
        "schema_version": 1,
        "fact_set_id": f"seed:{fact_name}:{serial}",
        "job_id": f"seed:{fact_name}",
        "analysis_run_id": serial,
        "analysis_hash": graph.canonical_hash({"serial": serial}),
        "created_at_utc": "2026-07-30T00:00:00+00:00",
        "accepted": True,
        "publication_eligible": True,
        "applicability_hash": graph.canonical_hash({"scope": fact_name}),
        "facts": [
            {
                "name": fact_name,
                "definition_version": 1,
                "role": fact_role,
                "dependencies": [],
                "value_items": [
                    {"field": field, "role": role}
                    for field, role in value_roles.items()
                ],
                "value": value,
            }
        ],
        "fact_set_hash": "",
    }
    record["fact_set_hash"] = graph.content_hash(record, "fact_set_hash")
    return record


def test_registry_has_valid_extensible_job_definitions():
    graph = _module("vision_calibration_graph.py", "vision_graph_registry_test")
    registry = graph.validate_registry(
        json.loads((FILES / "vision_job_types.json").read_text(encoding="utf-8"))
    )

    assert set(registry["job_types"]) >= graph.JOB_TYPES
    assert all(
        definition["definition_version"] == 1
        and isinstance(definition["publish_on_accept"], bool)
        and definition["fact_names"]
        for definition in registry["job_types"].values()
    )


def test_registry_does_not_pin_tunable_job_values():
    graph = _module("vision_calibration_graph.py", "vision_graph_tuning_test")
    registry = json.loads((FILES / "vision_job_types.json").read_text(encoding="utf-8"))
    measurement = registry["job_types"]["idex_tool_xy_measure_t0"]
    measurement["tool"] = "T1"
    measurement["x_offsets_from_fiducial_mm"] = [22.0, 10.0, 22.0]
    measurement["commanded_z_mm"] = 1.25
    measurement["capture_endstop_gap_mm"] = 0.75
    measurement["safe_tool_change_z_mm"] = 12.0
    measurement["publish_on_accept"] = False

    assert graph.validate_registry(registry) == registry


def test_xz_sweep_shared_delta_summary_is_prominent_and_reports_unavailable():
    calibration = _module("vision_calibration.py", "vision_calibration_ui_summary_test")

    available = calibration._shared_z_fit_summary_html(
        {
            "diagnostics": {
                "shared_z_curve_fit": {
                    "available": True,
                    "t1_z_delta_mm": -0.6,
                    "rms_slope_px_per_mm": 0.0123,
                    "included_rows": [{"tool": "T0"}],
                    "excluded_rows": [{"tool": "T1"}],
                }
            }
        }
    )
    assert "Shared T1 Z offset" in available
    assert "T1 ΔZ = -0.6000 mm" in available
    assert "reducing the top-endstop value" in available
    assert "included rows: 1" in available
    assert "excluded rows: 1" in available

    unavailable = calibration._shared_z_fit_summary_html(
        {
            "diagnostics": {
                "shared_z_curve_fit": {
                    "available": False,
                    "reason": "not enough usable tool/Z rows",
                }
            }
        }
    )
    assert "T1 ΔZ = unavailable" in unavailable
    assert "not enough usable tool/Z rows" in unavailable


def test_generated_acquisition_gcode_homes_before_job_motion():
    calibration = _module("vision_calibration.py", "vision_gcode_homing_test")
    manifest = {
        "job_type": "nozzle_cam_bed_fiducial_y_metric",
        "motion": {
            "resolved_pose": {
                "x_mm": -77.635,
                "y_base_mm": -14.8,
                "z_mm": 283.669,
            }
        },
        "frames": [
            {
                "seq": 0,
                "frame": "metric_y_00_00mm",
                "profile": "vision",
                "light_pixels": {str(index): 0.45 for index in range(1, 9)},
                "commanded_position_mm": [-77.635, -14.8, 283.669],
            }
        ],
    }

    lines = calibration._gcode(
        "test-job",
        "sha256:manifest",
        "sha256:gcode",
        manifest,
        {"velocity_mm_s": 60, "settle_ms": 300},
    ).splitlines()

    assert lines[:4] == [
        "; vision calibration job test-job",
        "G28",
        "G90",
        (
            "VISION_JOB_BEGIN JOB=test-job "
            "MANIFEST_HASH=sha256:manifest GCODE_HASH=sha256:gcode"
        ),
    ]
    assert "G1 Z283.669000 F3600.000" in lines
    assert "G1 Z293.669000 F3600.000" not in lines


def test_bed_capture_z_stays_below_top_after_active_mesh_correction(monkeypatch):
    calibration = _module(
        "vision_calibration.py", "vision_bed_capture_z_clearance_test"
    )
    definition = json.loads(
        (FILES / "vision_job_types.json").read_text(encoding="utf-8")
    )["job_types"]["nozzle_cam_bed_fiducial_y_metric"]
    status = {
        "webhooks": {"state": "ready"},
        "print_stats": {"state": "standby"},
        "virtual_sdcard": {"is_active": False},
        "configfile": {
            "settings": {
                "stepper_x": {
                    "position_min": -85.472,
                    "position_max": 255.0,
                    "position_endstop": -85.472,
                },
                "dual_carriage": {
                    "position_min": 16.0,
                    "position_max": 346.104,
                    "position_endstop": 346.104,
                },
                "stepper_y": {"position_min": -14.8, "position_max": 296.0},
                "stepper_z": {"position_min": -2.2, "position_max": 293.669},
            }
        },
        "gcode_macro _IDEX_CONFIG_FINGERPRINT": {"source_sha256": "test"},
        "gcode_macro _IDEX_TOOL_STATE": {
            "t0_y_endstop": -14.8,
            "t1_y_endstop": -13.284,
            "t0_z_endstop": 293.669,
            "t1_z_endstop": 293.175,
        },
        "bed_mesh": {"mesh_matrix": [[0.075355, 0.163638], [0.02, -0.01]]},
        "extruder": {"temperature": 20.0, "target": 0.0},
        "extruder1": {"temperature": 20.0, "target": 0.0},
        "heater_bed": {"temperature": 20.0, "target": 0.0},
    }
    monkeypatch.setattr(calibration, "_profile_names", lambda: {"vision"})
    monkeypatch.setattr(
        calibration,
        "_framebuffer_status",
        lambda: {"frame_seq": 1, "width": 1920, "height": 1080},
    )

    resolved = calibration._preflight(
        status,
        "nozzle_cam_bed_fiducial_y_metric",
        definition,
        None,
    )

    assert resolved["pose"]["z_mm"] == pytest.approx(283.669)
    assert resolved["pose"]["capture_z_below_top_mm"] == pytest.approx(10.0)
    assert resolved["pose"]["active_mesh_positive_max_mm"] == pytest.approx(0.163638)


def test_bed_capture_z_rejects_mesh_correction_beyond_clearance(monkeypatch):
    calibration = _module(
        "vision_calibration.py", "vision_bed_capture_z_mesh_limit_test"
    )
    definition = json.loads(
        (FILES / "vision_job_types.json").read_text(encoding="utf-8")
    )["job_types"]["nozzle_cam_bed_fiducial_y_metric"]
    definition["capture_z_below_top_mm"] = 0.1
    status = {
        "webhooks": {"state": "ready"},
        "print_stats": {"state": "standby"},
        "virtual_sdcard": {"is_active": False},
        "configfile": {
            "settings": {
                "stepper_x": {"position_min": -85.0, "position_max": 255.0},
                "dual_carriage": {"position_max": 346.0},
                "stepper_y": {"position_min": -14.8, "position_max": 296.0},
                "stepper_z": {"position_min": -2.2, "position_max": 293.669},
            }
        },
        "gcode_macro _IDEX_CONFIG_FINGERPRINT": {"source_sha256": "test"},
        "bed_mesh": {"mesh_matrix": [[0.2]]},
        "extruder": {"temperature": 20.0, "target": 0.0},
        "extruder1": {"temperature": 20.0, "target": 0.0},
        "heater_bed": {"temperature": 20.0, "target": 0.0},
    }
    monkeypatch.setattr(calibration, "_profile_names", lambda: {"vision"})
    monkeypatch.setattr(
        calibration,
        "_framebuffer_status",
        lambda: {"frame_seq": 1, "width": 1920, "height": 1080},
    )

    with pytest.raises(calibration.VisionCalibrationError, match="exceeds Z maximum"):
        calibration._preflight(
            status,
            "nozzle_cam_bed_fiducial_y_metric",
            definition,
            None,
        )


def test_acquisition_print_error_marks_job_failed(tmp_path, monkeypatch):
    calibration = _module("vision_calibration.py", "vision_acquisition_error_test")
    calibration.CALIBRATION_ROOT = tmp_path / "calibration"
    job_id = "test-print-error"
    job_dir = calibration.CALIBRATION_ROOT / "jobs" / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "state.json").write_text(
        json.dumps({"job_id": job_id, "state": "acquiring"}),
        encoding="utf-8",
    )
    (job_dir / "events.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(
        calibration,
        "_moonraker_get",
        lambda _path: {
            "status": {
                "print_stats": {
                    "state": "error",
                    "filename": f"vision_jobs/{job_id}.gcode",
                    "message": "Move out of range: 0.000 -14.800 293.744 [0.000]",
                }
            }
        },
    )

    with pytest.raises(calibration.VisionCalibrationError, match="failed"):
        calibration._wait_for_acquisition(job_id, timeout=1.0)

    state = json.loads((job_dir / "state.json").read_text(encoding="utf-8"))
    assert state["state"] == "failed"
    assert state["failure"] == "Move out of range: 0.000 -14.800 293.744 [0.000]"
    assert "\"event\":\"failed\"" in (
        job_dir / "events.jsonl"
    ).read_text(encoding="utf-8")


def test_new_job_replaces_abandoned_acquisition_lock(tmp_path):
    capture = _module("vision_capture.py", "vision_capture_lock_replacement_test")
    api = capture.VisionJobApi(job_root=tmp_path)
    abandoned_job = "abandoned-job"
    abandoned_dir = tmp_path / abandoned_job
    abandoned_dir.mkdir()
    (abandoned_dir / "state.json").write_text(
        json.dumps({"state": "acquiring", "committed_frame_count": 3}),
        encoding="utf-8",
    )
    assert api._acquire_lock(abandoned_job) is None

    displaced = api._acquire_lock("replacement-job")

    assert displaced == abandoned_job
    assert json.loads(api.lock_path.read_text(encoding="utf-8"))["job"] == (
        "replacement-job"
    )
    abandoned_state = json.loads(
        (abandoned_dir / "state.json").read_text(encoding="utf-8")
    )
    assert abandoned_state["state"] == "failed"
    assert abandoned_state["committed_frame_count"] == 3
    assert abandoned_state["superseded_by_job"] == "replacement-job"
    assert "acquisition_lock_replaced" in (abandoned_dir / "events.jsonl").read_text(
        encoding="utf-8"
    )


def test_marker_selection_rejects_distant_red_distractor(monkeypatch):
    locator = _module(
        "vision_nozzle_tip_localization.py",
        "vision_marker_selection_test",
    )
    expected = np.asarray([1083.0, 412.0])
    distractor = {"center_px": [1100.0, 521.0]}
    monkeypatch.setattr(locator, "_red_candidates", lambda _image, _index: [distractor])

    center, record = locator._select_marker(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        expected,
        0,
    )

    np.testing.assert_allclose(center, expected)
    assert record is None


def test_physical_tip_sector_excludes_lower_tracking_anchor():
    locator = _module(
        "vision_nozzle_tip_localization.py", "vision_tip_sector_test"
    )

    assert locator._is_physical_tip_delta(np.asarray([17.5, -2.0]), 63.0)
    assert not locator._is_physical_tip_delta(np.asarray([7.0, 16.0]), 63.0)


def test_canonical_hash_is_order_independent_and_strict():
    graph = _module("vision_calibration_graph.py", "vision_graph_hash_test")
    assert graph.canonical_hash({"b": 2, "a": 1}) == graph.canonical_hash(
        {"a": 1, "b": 2}
    )
    with pytest.raises(ValueError):
        graph.canonical_hash({"bad": float("nan")})


def test_fact_items_are_exact_and_uncertainty_is_rejected():
    graph = _module("vision_calibration_graph.py", "vision_graph_fact_test")
    record = _fact_set(
        graph,
        fact_name="bed.tab_corner.printer_xyz",
        value={"xyz_mm": [173.0, -18.0, 0.0]},
        value_roles={"xyz_mm": "coordinate_system"},
        serial="one",
    )
    assert graph.validate_fact_set(record) == record

    undeclared = json.loads(json.dumps(record))
    undeclared["facts"][0]["value"]["quality"] = 1
    undeclared["fact_set_hash"] = graph.content_hash(undeclared, "fact_set_hash")
    with pytest.raises(graph.CalibrationGraphError, match="exactly cover"):
        graph.validate_fact_set(undeclared)

    uncertain = json.loads(json.dumps(record))
    uncertain["facts"][0]["value"]["uncertainty_mm"] = 0.1
    uncertain["facts"][0]["value_items"].append(
        {"field": "uncertainty_mm", "role": "diagnostic"}
    )
    uncertain["fact_set_hash"] = graph.content_hash(uncertain, "fact_set_hash")
    with pytest.raises(graph.CalibrationGraphError, match="uncertainty"):
        graph.validate_fact_set(uncertain)


def test_publication_fact_copy_removes_forbidden_fit_detail_fields():
    graph = _module("vision_calibration_graph.py", "vision_graph_safe_fact_test")
    calibration = _module(
        "vision_calibration.py", "vision_calibration_safe_fact_test"
    )
    fact = calibration._fact(
        "camera.nozzle_cam.nozzle_tip.xz_sweep_report",
        "diagnostic",
        {
            "fit": {
                "slope_uncertainty_px_per_mm": 0.04,
                "slope_px_per_mm": 9.4,
            },
            "covariance_matrix": [[1.0]],
            "records": [{"uncertainties": [0.1], "seq": 1}],
        },
        [],
    )
    assert fact["value"] == {
        "fit": {"slope_px_per_mm": 9.4},
        "records": [{"seq": 1}],
    }
    record = _fact_set(
        graph,
        fact_name=fact["name"],
        value=fact["value"],
        value_roles={
            item["field"]: item["role"] for item in fact["value_items"]
        },
        serial="safe-fit-details",
        fact_role=fact["role"],
    )
    assert graph.validate_fact_set(record) == record


def test_tool_xy_candidate_publication_is_a_valid_coordinate_fact():
    graph = _module("vision_calibration_graph.py", "vision_graph_xy_candidate_test")
    calibration = _module(
        "vision_calibration.py", "vision_calibration_xy_candidate_fact_test"
    )
    value = {
        "x_alignment_error_mm": 0.54,
        "y_alignment_error_mm": -0.12,
        "source_t0_endstop_xy_mm": [-77.635, -14.8],
        "source_t1_endstop_xy_mm": [351.739, -13.8],
        "suggested_t1_endstop_xy_mm": [351.199, -13.68],
        "candidate_calib_sha256": "sha256:candidate",
    }
    fact = calibration._tool_xy_candidate_publication_fact(value, [])
    record = _fact_set(
        graph,
        fact_name=fact["name"],
        value=fact["value"],
        value_roles={item["field"]: item["role"] for item in fact["value_items"]},
        serial="tool-xy-candidate",
        fact_role=fact["role"],
    )

    assert fact["role"] == "coordinate_system"
    assert graph.validate_fact_set(record) == record


def test_catalog_rebuild_accepts_retired_acquisition_profile_facts(tmp_path):
    graph = _module("vision_calibration_graph.py", "vision_graph_retired_role_test")
    record = _fact_set(
        graph,
        fact_name="camera.nozzle_cam.bed_fiducial.lighting_profile",
        value={"profile": "retired"},
        value_roles={"profile": "acquisition_profile"},
        serial="historical-lighting",
        fact_role="acquisition_profile",
    )
    fact_set_path = (
        tmp_path
        / "jobs"
        / "historical-lighting"
        / "analysis"
        / "historical-lighting"
        / "fact_set.json"
    )
    fact_set_path.parent.mkdir(parents=True)
    fact_set_path.write_text(json.dumps(record), encoding="utf-8")

    catalog = graph.rebuild_catalog(tmp_path)

    assert catalog["heads"] == {}


def test_catalog_rebuild_ignores_an_invalid_unpublished_fact_set(tmp_path):
    graph = _module("vision_calibration_graph.py", "vision_graph_invalid_history_test")
    record = _fact_set(
        graph,
        fact_name="calibration.idex_tool_xy.candidate",
        value={"suggested_t1_endstop_xy_mm": [351.0, -13.5]},
        value_roles={"suggested_t1_endstop_xy_mm": "coordinate_system"},
        serial="broken-candidate",
        fact_role="diagnostic",
    )
    fact_set_path = (
        tmp_path
        / "jobs"
        / "failed-candidate"
        / "analysis"
        / "failed-analysis"
        / "fact_set.json"
    )
    fact_set_path.parent.mkdir(parents=True)
    fact_set_path.write_text(json.dumps(record), encoding="utf-8")

    catalog = graph.rebuild_catalog(tmp_path)

    assert catalog["heads"] == {}
    assert len(catalog["warnings"]) == 1
    assert catalog["warnings"][0]["code"] == "invalid_fact_set_ignored"
    assert catalog["warnings"][0]["fact_set_path"] == (
        "jobs/failed-candidate/analysis/failed-analysis/fact_set.json"
    )


def test_seed_superseding_selects_new_head(tmp_path):
    graph = _module("vision_calibration_graph.py", "vision_graph_publish_test")
    root = tmp_path / "calibration"
    paths = []
    for serial, x_value in (("one", 173.0), ("two", 174.0)):
        record = _fact_set(
            graph,
            fact_name="bed.tab_corner.printer_xyz",
            value={"xyz_mm": [x_value, -18.0, 0.0]},
            value_roles={"xyz_mm": "coordinate_system"},
            serial=serial,
        )
        path = root / "seeds" / serial / "fact_set.json"
        graph.atomic_write_json(path, record, immutable=True)
        paths.append((path, record))

    first = graph.publish_seed_fact_set(root, paths[0][0])
    second = graph.publish_seed_fact_set(root, paths[1][0])

    assert not first["already_published"]
    assert not second["already_published"]
    catalog = graph.rebuild_catalog(root)
    assert catalog["heads"]["bed.tab_corner.printer_xyz"]["fact_set_hash"] == (
        paths[1][1]["fact_set_hash"]
    )
    assert len(catalog["publications"]) == 2


def test_missing_published_fact_set_falls_back_and_can_be_superseded(tmp_path):
    graph = _module("vision_calibration_graph.py", "vision_graph_orphan_test")
    root = tmp_path / "calibration"
    fact_name = "bed.tab_corner.printer_xyz"

    def fact_set(serial, x_value):
        record = _fact_set(
            graph,
            fact_name=fact_name,
            value={"xyz_mm": [x_value, -18.0, 0.0]},
            value_roles={"xyz_mm": "coordinate_system"},
            serial=serial,
        )
        path = root / "seeds" / serial / "fact_set.json"
        graph.atomic_write_json(path, record, immutable=True)
        return path, record

    def publication(publication_id, fact_set_hash, supersedes):
        record = {
            "schema": graph.PUBLICATION_SCHEMA,
            "schema_version": 1,
            "publication_id": publication_id,
            "created_at_utc": "2026-08-02T00:00:00+00:00",
            "job_id": publication_id,
            "analysis_run_id": publication_id,
            "analysis_hash": graph.canonical_hash({"publication": publication_id}),
            "fact_set_hash": fact_set_hash,
            "facts": [fact_name],
            "supersedes": {fact_name: supersedes},
            "publication_hash": "",
        }
        record["publication_hash"] = graph.content_hash(record, "publication_hash")
        graph.atomic_write_json(
            root / "publications" / f"{publication_id}.json",
            record,
            immutable=True,
        )

    _first_path, first = fact_set("one", 173.0)
    publication("0001-first", first["fact_set_hash"], None)
    missing_hash = graph.canonical_hash({"deleted": "fact-set"})
    publication("0002-deleted", missing_hash, first["fact_set_hash"])

    catalog = graph.rebuild_catalog(root)

    assert catalog["heads"][fact_name]["fact_set_hash"] == first["fact_set_hash"]
    assert catalog["publication_heads"][fact_name] == missing_hash
    assert catalog["warnings"][0]["fallback_heads"] == {
        fact_name: first["fact_set_hash"]
    }
    assert catalog["warnings"][0]["missing_fallbacks"] == []
    assert "continuing with previous available facts" in (
        catalog["warnings"][0]["message"]
    )
    assert "Rerun the calibration" in (catalog["warnings"][0]["suggested_action"])
    assert catalog["publications"][-1]["fact_set_available"] is False

    _legacy_path, legacy = fact_set("legacy-recovery", 174.0)
    publication("0003-legacy-recovery", legacy["fact_set_hash"], first["fact_set_hash"])

    repaired = graph.rebuild_catalog(root)

    assert repaired["heads"][fact_name]["fact_set_hash"] == legacy["fact_set_hash"]
    assert repaired["publication_heads"][fact_name] == legacy["fact_set_hash"]
    repair_warning = repaired["warnings"][-1]
    assert repair_warning["code"] == "publication_lineage_repaired"
    assert repair_warning["declared_supersedes"] == first["fact_set_hash"]
    assert repair_warning["lineage_head"] == missing_hash
    assert repair_warning["available_head"] == first["fact_set_hash"]

    fourth_path, fourth = fact_set("four", 175.0)
    published = graph.publish_seed_fact_set(root, fourth_path)

    assert published["publication"]["supersedes"] == {
        fact_name: legacy["fact_set_hash"]
    }
    assert published["catalog"]["heads"][fact_name]["fact_set_hash"] == (
        fourth["fact_set_hash"]
    )


def test_flat_priors_replace_active_seed_fact_dependencies():
    priors_path = REPO_ROOT / "klipper_setup" / "klipper_config" / "priors.yaml"
    priors = yaml.safe_load(priors_path.read_text(encoding="utf-8"))
    registry = json.loads((FILES / "vision_job_types.json").read_text(encoding="utf-8"))
    retired = {
        "bed.fiducial_patch.physical_reference",
        "bed.fiducial_patch.printer_z_mm",
    }

    assert set(priors) == {
        "fiducial_reference_printer_xyz_mm",
        "fiducial_origin_xy_mm",
        "fiducial_spacing_xy_mm",
        "fiducial_z_mm",
    }
    assert not (FILES / "vision_calibration_priors.json").exists()
    assert all(
        requirement["fact_name"] not in retired
        for definition in registry["job_types"].values()
        for requirement in definition["requires"]
    )
    calibration_source = (FILES / "vision_calibration.py").read_text(encoding="utf-8")
    assert "sync-priors" not in calibration_source
    assert "sync_seed_facts" not in calibration_source


def test_old_manifests_drop_retired_prior_fact_bindings():
    calibration = _module("vision_calibration.py", "vision_retired_prior_binding_test")
    manifest = {
        "input_facts": [
            {
                "requirement": "physical_reference",
                "fact_name": "bed.fiducial_patch.physical_reference",
                "fact_definition_version": 1,
                "fact_set_hash": "sha256:retired",
            },
            {
                "requirement": "bed_metric",
                "fact_name": "camera.nozzle_cam.bed_fiducial.local_metric_model",
                "fact_definition_version": 1,
                "fact_set_hash": "sha256:active",
            },
        ]
    }

    assert calibration._active_input_facts(manifest) == [manifest["input_facts"][1]]
    assert calibration._dependencies(manifest) == [
        {
            "fact_name": "camera.nozzle_cam.bed_fiducial.local_metric_model",
            "fact_set_hash": "sha256:active",
        }
    ]


def test_new_bed_metric_manifest_uses_dao_without_seed_facts(tmp_path):
    calibration = _module("vision_calibration.py", "vision_dao_manifest_test")
    calibration.CALIBRATION_ROOT = tmp_path / "calibration"
    calibration.VISION_ROOT = tmp_path / "vision"
    calibration.GCODE_ROOT = tmp_path / "gcodes"
    calibration.REGISTRY_PATH = FILES / "vision_job_types.json"
    calibration.PROFILE_PATH = FILES / "nozzle_cam_profiles.json"
    calibration.CALIB = calibration.CalibDAO(
        REPO_ROOT / "klipper_setup" / "klipper_config" / "calib.yaml",
        REPO_ROOT / "klipper_setup" / "klipper_config" / "priors.yaml",
    )
    calibration._preflight = lambda *_args, **_kwargs: {
        "pose": {"x_mm": -77.635, "y_base_mm": -14.8, "z_mm": 293.75},
        "axis_minimum": [-80.0, -20.0, 0.0],
        "axis_maximum": [355.0, 320.0, 300.0],
        "fingerprint": "test-fingerprint",
        "temperatures": {},
        "framebuffer": {},
        "active_calibration_snapshot": {},
        "scope": {"printer": "test"},
        "applicability_hash": "unused-before-input-binding",
    }

    prepared = calibration.prepare_job(
        "dao-metric",
        job_type="nozzle_cam_bed_fiducial_y_metric",
        status={"test": True},
    )
    manifest = json.loads(
        (Path(prepared["job_dir"]) / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["input_facts"] == []
    assert manifest["provenance"]["priors"]["fiducial_centers_xy_mm"] == [
        [3.0, 3.0],
        [11.0, 3.0],
        [3.0, 11.0],
        [11.0, 11.0],
    ]


def test_fine_grid_localizes_the_nozzle_tip_inside_the_outer_ring():
    analyzer = _module(
        "vision_nozzle_tip_localization.py", "vision_nozzle_tip_localizer_test"
    )
    image = np.full((240, 240, 3), 24, dtype=np.uint8)
    ring_center = np.asarray([120.0, 120.0])
    cv2.circle(image, (120, 120), 52, (130, 130, 130), 7)
    cv2.circle(image, (129, 118), 5, (252, 252, 252), -1)

    candidates = analyzer._tip_candidates(
        image,
        {"center_px": ring_center.tolist(), "radius_px": 52.0},
    )

    assert candidates
    recovered = np.asarray(candidates[0]["center_px"])
    assert np.linalg.norm(recovered - np.asarray([129.0, 118.0])) < 2.0
    assert np.linalg.norm(recovered - ring_center) > 5.0


def test_fine_grid_acquisition_snapshot_comes_from_dao():
    calibration = _module(
        "vision_calibration.py", "vision_fine_acquisition_calibration_test"
    )

    class TestCalib:
        @staticmethod
        def tool_datums():
            return {
                "t0": {
                    "x_endstop": -70.125,
                    "y_endstop": -14.25,
                    "z_endstop": 290.0,
                },
                "t1": {
                    "x_endstop": 350.75,
                    "y_endstop": -13.5,
                    "z_endstop": 291.0,
                },
            }

        @staticmethod
        def calib_hash():
            return "sha256:acquisition-calib"

    calibration.CALIB = TestCalib()

    assert calibration._acquisition_calibration_snapshot() == {
        "calib_sha256": "sha256:acquisition-calib",
        "tool_xy_endstops_mm": {
            "t0": {"x": -70.125, "y": -14.25},
            "t1": {"x": 350.75, "y": -13.5},
        },
    }


def test_tool_sweep_acquisition_snapshot_includes_z_endstops():
    calibration = _module("vision_calibration.py", "vision_tool_sweep_z_snapshot_test")
    status = {
        "configfile": {
            "settings": {
                "stepper_x": {"position_endstop": -70.125},
                "dual_carriage": {"position_endstop": 350.75},
            }
        },
        "gcode_macro _IDEX_CONFIG_FINGERPRINT": {"source_sha256": "sha256:test-active"},
        "gcode_macro _IDEX_TOOL_STATE": {
            "t0_y_endstop": -14.25,
            "t1_y_endstop": -13.5,
            "t0_y_offset": 0.0,
            "t1_y_offset": -0.75,
            "t0_z_endstop": 290.0,
            "t1_z_endstop": 289.4,
        },
    }

    snapshot = calibration._active_tool_xy_calibration(status)

    assert snapshot["tool_z_endstops_mm"] == {"t0": 290.0, "t1": 289.4}
