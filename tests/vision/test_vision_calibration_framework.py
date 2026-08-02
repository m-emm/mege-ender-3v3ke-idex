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


def test_registry_is_exact_clean_chain():
    graph = _module("vision_calibration_graph.py", "vision_graph_registry_test")
    registry = graph.validate_registry(
        json.loads((FILES / "vision_job_types.json").read_text(encoding="utf-8"))
    )

    assert set(registry["job_types"]) == graph.JOB_TYPES
    assert all(
        definition["definition_version"] == 1
        and definition["publish_on_accept"] is True
        for definition in registry["job_types"].values()
    )
    fine_jobs = [
        registry["job_types"][f"idex_nozzle_fine_xz_grid_{tool.lower()}"]
        for tool in ("T0", "T1")
    ]
    assert [fine["tool"] for fine in fine_jobs] == ["T0", "T1"]
    assert all(fine["x_offsets_from_bed_tab_mm"] for fine in fine_jobs)
    assert all(fine["full_row_z_mm"] for fine in fine_jobs)
    assert all(
        fine["x_offsets_from_bed_tab_mm"]
        == sorted(set(fine["x_offsets_from_bed_tab_mm"]))
        for fine in fine_jobs
    )
    assert all(
        fine["full_row_z_mm"] == sorted(set(fine["full_row_z_mm"]))
        for fine in fine_jobs
    )
    assert all(
        fine["x_offsets_from_bed_tab_mm"] == fine_jobs[0]["x_offsets_from_bed_tab_mm"]
        and fine["full_row_z_mm"] == fine_jobs[0]["full_row_z_mm"]
        for fine in fine_jobs
    )
    assert [fine["fact_names"] for fine in fine_jobs] == [
        ["camera.nozzle_cam.nozzle_tip.t0_projection_model"],
        ["camera.nozzle_cam.nozzle_tip.t1_projection_model"],
    ]
    assert "idex_fine_tool_xy_verify" not in registry["job_types"]


def test_generated_acquisition_gcode_homes_before_job_motion():
    calibration = _module("vision_calibration.py", "vision_gcode_homing_test")
    manifest = {
        "job_type": "nozzle_cam_bed_fiducial_y_metric",
        "motion": {
            "resolved_pose": {
                "x_mm": -77.635,
                "y_base_mm": -14.8,
                "z_mm": 293.75,
            }
        },
        "frames": [
            {
                "seq": 0,
                "frame": "metric_y_00_00mm",
                "profile": "vision",
                "light_pixels": {str(index): 0.45 for index in range(1, 9)},
                "commanded_position_mm": [-77.635, -14.8, 293.75],
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
    assert "acquisition_lock_replaced" in (
        abandoned_dir / "events.jsonl"
    ).read_text(encoding="utf-8")


def test_fine_nozzle_marker_selection_rejects_distant_red_distractor(monkeypatch):
    locator = _module(
        "vision_nozzle_tip_localization.py",
        "vision_fine_marker_selection_test",
    )
    expected = np.asarray([1083.0, 412.0])
    distractor = {"center_px": [1100.0, 521.0]}
    monkeypatch.setattr(
        locator, "_red_candidates", lambda _image, _index: [distractor]
    )

    center, record = locator._select_marker(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        expected,
        0,
    )

    np.testing.assert_allclose(center, expected)
    assert record is None


def test_fine_nozzle_physical_tip_sector_excludes_lower_tracking_anchor():
    locator = _module(
        "vision_nozzle_tip_localization.py", "vision_fine_tip_sector_test"
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
        record["publication_hash"] = graph.content_hash(
            record, "publication_hash"
        )
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
    assert "Rerun the calibration" in (
        catalog["warnings"][0]["suggested_action"]
    )
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
        "bed.tab_corner.printer_xyz",
        "bed.fiducial_patch.physical_reference",
        "bed.fiducial_patch.printer_z_mm",
    }

    assert set(priors) == {
        "bed_corner_xyz_mm",
        "fiducial_origin_xy_mm",
        "fiducial_spacing_xy_mm",
        "fiducial_z_mm",
        "fiducial_right_angle_deg",
    }
    assert not (FILES / "vision_calibration_priors.json").exists()
    assert all(
        requirement["fact_name"] not in retired
        for definition in registry["job_types"].values()
        for requirement in definition["requires"]
    )
    calibration_source = (FILES / "vision_calibration.py").read_text(
        encoding="utf-8"
    )
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


def test_fine_grid_overlay_lists_both_tools_acquisition_xy_endstops():
    analyzer = _module("vision_nozzle_fine_xz.py", "vision_nozzle_endstop_overlay_test")
    snapshot = {
        "tool_xy_endstops_mm": {
            "t0": {"x": -70.125, "y": -14.25},
            "t1": {"x": 350.75, "y": -13.5},
        }
    }

    assert analyzer._acquisition_xy_endstop_line(snapshot) == (
        "acquire calib endstops: T0 X=-70.125 Y=-14.250 | "
        "T1 X=350.750 Y=-13.500"
    )
    assert analyzer._acquisition_xy_endstop_line(None) == (
        "acquire calib endstops: unavailable (legacy manifest)"
    )


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


def test_fine_grid_analyzer_streams_frames_and_publishes_projection_only():
    source = (FILES / "vision_nozzle_fine_xz.py").read_text(encoding="utf-8")
    graph_source = (FILES / "vision_calibration_graph.py").read_text(encoding="utf-8")
    registry = json.loads((FILES / "vision_job_types.json").read_text(encoding="utf-8"))
    fine = registry["job_types"]["idex_nozzle_fine_xz_grid_t0"]

    assert "images.append" not in source
    assert "commanded_z_at_print_plane_mm" not in source
    assert "fine X/Y verification may not command below Z=3" not in graph_source
    assert fine["fact_names"] == ["camera.nozzle_cam.nozzle_tip.t0_projection_model"]


def test_fine_tool_candidate_changes_only_the_selected_tool():
    calculator = _module(
        "vision_fine_tool_calibration.py",
        "vision_fine_tool_candidate_scope_test",
    )
    old_datums = {
        "t0": {"x_endstop": 1.0, "y_endstop": 2.0, "z_endstop": 3.0},
        "t1": {"x_endstop": 4.0, "y_endstop": 5.0, "z_endstop": 6.0},
    }

    for tool, target, other in (
        ("T0", "t0", "t1"),
        ("T1", "t1", "t0"),
    ):
        result = calculator.generated_calibration(
            old_datums,
            tool=tool,
            residual_xyz_mm=[0.1, 0.2, 0.3],
        )

        assert result["persisted_calib"]["new"][target] == {
            "x": old_datums[target]["x_endstop"] + 0.1,
            "y": old_datums[target]["y_endstop"] + 0.2,
            "z": old_datums[target]["z_endstop"] + 0.3,
        }
        assert result["persisted_calib"]["new"][other] == {
            axis: old_datums[other][f"{axis}_endstop"] for axis in ("x", "y", "z")
        }
