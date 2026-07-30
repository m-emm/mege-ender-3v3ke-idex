import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
    / "vision_calibration_graph.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("vision_graph_test", GRAPH_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest(module, job_id):
    frames = [
        {
            "seq": seq,
            "frame": f"y_{seq}",
            "y_offset_mm": offset,
        }
        for seq, offset in enumerate((0, 5, 10, 15, 20, 15, 10, 5, 0))
    ]
    record = {
        "schema": module.MANIFEST_SCHEMA,
        "schema_version": 1,
        "job_id": job_id,
        "job_type": "nozzle_cam_bed_tab_y_scale",
        "definition_version": 1,
        "created_at_utc": "2026-07-30T00:00:00+00:00",
        "camera": "nozzle_cam",
        "frame_count": 9,
        "frames": frames,
        "manifest_hash": "",
    }
    record["manifest_hash"] = module.content_hash(record, "manifest_hash")
    return record


def _analysis_and_fact_set(
    module,
    root,
    *,
    job_id,
    analysis_id,
    fact_name,
    dependencies=(),
):
    analysis_dir = root / "jobs" / job_id / "analysis" / analysis_id
    analysis_dir.mkdir(parents=True)
    job_dir = root / "jobs" / job_id
    (job_dir / "manifest.json").write_text(
        json.dumps(_manifest(module, job_id)), encoding="utf-8"
    )
    (job_dir / "state.json").write_text(
        json.dumps({"state": "analyzed"}), encoding="utf-8"
    )
    result = {
        "schema": module.ANALYSIS_SCHEMA,
        "schema_version": 1,
        "analysis_run_id": analysis_id,
        "job_id": job_id,
        "state": "accepted",
        "fact_set_path": "fact_set.json",
        "analysis_hash": "",
    }
    result["analysis_hash"] = module.content_hash(result, "analysis_hash")
    (analysis_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    value = {"value": analysis_id}
    if fact_name == "camera.nozzle_cam.bed_tab.y_parallax_model":
        value["axis_vector_px_per_mm"] = [1.0, -8.0]
    fact_set = {
        "schema": module.FACT_SET_SCHEMA,
        "schema_version": 1,
        "fact_set_id": f"{job_id}:{analysis_id}",
        "job_id": job_id,
        "analysis_run_id": analysis_id,
        "analysis_hash": result["analysis_hash"],
        "accepted": True,
        "publication_eligible": True,
        "applicability_hash": "sha256:scope",
        "facts": [
            {
                "name": fact_name,
                "dependencies": list(dependencies),
                "value": value,
            }
        ],
        "fact_set_hash": "",
    }
    fact_set["fact_set_hash"] = module.content_hash(fact_set, "fact_set_hash")
    (analysis_dir / "fact_set.json").write_text(json.dumps(fact_set), encoding="utf-8")
    return fact_set


def test_canonical_hash_is_order_independent_and_rejects_old_schema():
    module = _load()
    assert module.canonical_hash({"b": 2, "a": 1}) == module.canonical_hash(
        {"a": 1, "b": 2}
    )
    with pytest.raises(module.CalibrationGraphError, match="schema"):
        module.validate_manifest(
            {
                "schema": "legacy-vision-job",
                "schema_version": 1,
            }
        )


def test_analysis_records_and_publications_are_immutable(tmp_path):
    module = _load()
    target = tmp_path / "immutable.json"
    module.atomic_write_json(target, {"value": 1}, immutable=True)
    with pytest.raises(module.CalibrationGraphError, match="immutable"):
        module.atomic_write_json(target, {"value": 2}, immutable=True)

    fact_set = _analysis_and_fact_set(
        module,
        tmp_path,
        job_id="job_a",
        analysis_id="analysis_a",
        fact_name="root.fact",
    )
    published = module.publish_fact_set(tmp_path, "job_a", "analysis_a")
    assert published["publication"]["fact_set_hash"] == fact_set["fact_set_hash"]
    with pytest.raises(module.CalibrationGraphError, match="already published"):
        module.publish_fact_set(tmp_path, "job_a", "analysis_a")


def test_superseding_propagates_staleness_to_exact_consumers(tmp_path):
    module = _load()
    first = _analysis_and_fact_set(
        module,
        tmp_path,
        job_id="job_root_a",
        analysis_id="analysis_root_a",
        fact_name="root.fact",
    )
    module.publish_fact_set(tmp_path, "job_root_a", "analysis_root_a")
    consumer = _analysis_and_fact_set(
        module,
        tmp_path,
        job_id="job_consumer",
        analysis_id="analysis_consumer",
        fact_name="consumer.fact",
        dependencies=[
            {
                "fact_name": "root.fact",
                "fact_set_hash": first["fact_set_hash"],
            }
        ],
    )
    module.publish_fact_set(tmp_path, "job_consumer", "analysis_consumer")
    second = _analysis_and_fact_set(
        module,
        tmp_path,
        job_id="job_root_b",
        analysis_id="analysis_root_b",
        fact_name="root.fact",
    )
    module.publish_fact_set(tmp_path, "job_root_b", "analysis_root_b")
    catalog = module.rebuild_catalog(tmp_path)
    assert catalog["heads"]["root.fact"]["fact_set_hash"] == second["fact_set_hash"]
    assert consumer["fact_set_hash"] in catalog["stale_fact_sets"]


def test_cycle_and_publication_conflicts_are_rejected(tmp_path):
    module = _load()
    first = _analysis_and_fact_set(
        module,
        tmp_path,
        job_id="job_a",
        analysis_id="analysis_a",
        fact_name="fact.a",
        dependencies=[{"fact_name": "fact.b", "fact_set_hash": "sha256:b"}],
    )
    second = _analysis_and_fact_set(
        module,
        tmp_path,
        job_id="job_b",
        analysis_id="analysis_b",
        fact_name="fact.b",
        dependencies=[
            {
                "fact_name": "fact.a",
                "fact_set_hash": first["fact_set_hash"],
            }
        ],
    )
    first_path = tmp_path / "jobs/job_a/analysis/analysis_a/fact_set.json"
    first["facts"][0]["dependencies"][0]["fact_set_hash"] = second["fact_set_hash"]
    first["fact_set_hash"] = module.content_hash(first, "fact_set_hash")
    first_path.write_text(json.dumps(first), encoding="utf-8")
    second["facts"][0]["dependencies"][0]["fact_set_hash"] = first["fact_set_hash"]
    second["fact_set_hash"] = module.content_hash(second, "fact_set_hash")
    (tmp_path / "jobs/job_b/analysis/analysis_b/fact_set.json").write_text(
        json.dumps(second), encoding="utf-8"
    )
    # Rebind A to B's final hash to close the cycle.
    first["facts"][0]["dependencies"][0]["fact_set_hash"] = second["fact_set_hash"]
    first["fact_set_hash"] = module.content_hash(first, "fact_set_hash")
    first_path.write_text(json.dumps(first), encoding="utf-8")
    # Hash-addressed cycles cannot be constructed without a fixed point. Exercise
    # the detector directly with explicit graph keys instead.
    with pytest.raises(module.CalibrationGraphError, match="cycle"):
        module._detect_cycles(
            {
                "sha256:a": (
                    Path("a"),
                    {"facts": [{"dependencies": [{"fact_set_hash": "sha256:b"}]}]},
                ),
                "sha256:b": (
                    Path("b"),
                    {"facts": [{"dependencies": [{"fact_set_hash": "sha256:a"}]}]},
                ),
            }
        )

    conflict_root = tmp_path / "conflict"
    _analysis_and_fact_set(
        module,
        conflict_root,
        job_id="job_first",
        analysis_id="analysis_first",
        fact_name="root.fact",
    )
    module.publish_fact_set(conflict_root, "job_first", "analysis_first")
    replacement = _analysis_and_fact_set(
        module,
        conflict_root,
        job_id="job_second",
        analysis_id="analysis_second",
        fact_name="root.fact",
    )
    publication = {
        "schema": module.PUBLICATION_SCHEMA,
        "schema_version": 1,
        "publication_id": "zz-conflict",
        "created_at_utc": "2026-07-30T01:00:00+00:00",
        "job_id": "job_second",
        "analysis_run_id": "analysis_second",
        "analysis_hash": replacement["analysis_hash"],
        "fact_set_hash": replacement["fact_set_hash"],
        "facts": ["root.fact"],
        "supersedes": {"root.fact": None},
        "publication_hash": "",
    }
    publication["publication_hash"] = module.content_hash(
        publication, "publication_hash"
    )
    (conflict_root / "publications" / "zz-conflict.json").write_text(
        json.dumps(publication), encoding="utf-8"
    )
    with pytest.raises(module.CalibrationGraphError, match="publication conflict"):
        module.rebuild_catalog(conflict_root)
