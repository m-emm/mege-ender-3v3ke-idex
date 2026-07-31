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


def _module(filename, name):
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(name, FILES / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fact_set(graph, *, fact_name, value, value_roles, serial):
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
                "role": "coordinate_system",
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
    assert all(len(fine["x_offsets_from_bed_tab_mm"]) == 7 for fine in fine_jobs)
    assert all(len(fine["full_row_z_mm"]) == 4 for fine in fine_jobs)
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


def test_fine_nozzle_marker_selection_rejects_distant_red_distractor(monkeypatch):
    fine = _module("vision_nozzle_fine_xz.py", "vision_fine_marker_selection_test")
    expected = np.asarray([1083.0, 412.0])
    distractor = {"center_px": [1100.0, 521.0]}
    monkeypatch.setattr(fine, "_red_candidates", lambda _image, _index: [distractor])

    center, record = fine._select_marker(
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        expected,
        0,
    )

    np.testing.assert_allclose(center, expected)
    assert record is None


def test_fine_nozzle_physical_tip_sector_excludes_lower_tracking_anchor():
    fine = _module("vision_nozzle_fine_xz.py", "vision_fine_tip_sector_test")

    assert fine._is_physical_tip_delta(np.asarray([17.5, -2.0]), 63.0)
    assert not fine._is_physical_tip_delta(np.asarray([7.0, 16.0]), 63.0)


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


def test_priors_define_fiducial_plane_without_uncertainties():
    priors = json.loads(
        (FILES / "vision_calibration_priors.json").read_text(encoding="utf-8")
    )
    seeds = {item["name"]: item for item in priors["seeds"]}

    assert set(seeds) == {
        "bed.tab_corner.printer_xyz",
        "bed.fiducial_patch.physical_reference",
        "bed.fiducial_patch.printer_z_mm",
    }
    assert seeds["bed.tab_corner.printer_xyz"]["value"]["xyz_mm"] == [
        173.0,
        -18.0,
        0.0,
    ]
    assert seeds["bed.fiducial_patch.printer_z_mm"]["value"]["z_mm"] == -0.6
    assert "uncert" not in json.dumps(priors).lower()


def test_fine_grid_localizes_the_nozzle_tip_inside_the_outer_ring():
    analyzer = _module("vision_nozzle_fine_xz.py", "vision_nozzle_tip_localizer_test")
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
