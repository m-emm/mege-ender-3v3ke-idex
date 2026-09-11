import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "klipper_setup/runtime_helpers/idex_calibration_acceptance.py"


def load_module():
    spec = importlib.util.spec_from_file_location("idex_acceptance", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_heartbeat_is_attempt_owned_and_does_not_change_chapters(tmp_path):
    module = load_module()
    root = tmp_path
    state = module.empty_state()
    state["accepted"] = {"tool_alignment": {
        "status": "accepted", "data": {"calibration": {"plot": "old.png"}},
        "attempt_id": "old",
    }}
    state["attempt"] = {
        "attempt_id": "new", "batch_id": "new", "status": "running",
        "chapters": {"tool_alignment": {"calibration": {"runs": {}}}},
    }
    module.write_state(root, state)
    module.apply_command(root, "heartbeat", {
        "attempt_id": "old", "activity": {"step": 4, "operation": "late"},
    })
    current = json.loads((root / "data/current.json").read_text())
    assert current["attempt"].get("activity", {}).get("operation") != "late"

    module.apply_command(root, "activity", {
        "attempt_id": "new", "activity_id": "activity-new", "step": 4,
        "operation": "T0 contacts", "started_at": "2026-09-11T11:59:00+00:00",
    })
    module.apply_command(root, "heartbeat", {
        "attempt_id": "new", "activity_id": "activity-new",
        "heartbeat_at": "2026-09-11T12:00:00+00:00",
    })
    current = json.loads((root / "data/current.json").read_text())
    # Heartbeats are volatile and intentionally never rewrite the projection.
    assert "activity" not in current["attempt"]
    activity = json.loads((root / "data/activity.json").read_text())
    assert activity["operation"] == "T0 contacts"
    assert current["chapters"]["tool_alignment"]["calibration"]["runs"] == {}
    assert "plot" not in current["chapters"]["tool_alignment"]["calibration"]


def test_live_chapter_replaces_old_detail_but_keeps_non_owned_mesh(tmp_path):
    module = load_module()
    root = tmp_path
    state = module.empty_state()
    state["accepted"] = {
        "bed_reference": {"status": "accepted", "data": {"reference": {"old": True}}},
        "mesh": {"status": "accepted", "data": {"mesh": {"plot": "mesh.png"}}},
    }
    state["attempt"] = {
        "attempt_id": "new", "batch_id": "new", "run_scope": "bed_reference",
        "status": "running", "chapters": {"bed_calibration": {"reference": {"progress": {"completed": 1}}}},
    }
    module.write_state(root, state)
    current = json.loads((root / "data/current.json").read_text())
    assert current["chapters"]["bed_calibration"]["reference"]["progress"]["completed"] == 1
    assert current["chapters"]["bed_calibration"]["mesh"]["plot"] == "mesh.png"
    assert "old" not in current["chapters"]["bed_calibration"]["reference"]


def test_active_attempt_cannot_report_printable_even_with_complete_acceptance(tmp_path):
    module = load_module()
    root = tmp_path
    state = module.empty_state()
    state["accepted"] = {
        chapter: {"status": "accepted", "data": {}, "attempt_id": "old"}
        for chapter in module.CHAPTERS
    }
    state["attempt"] = {
        "attempt_id": "new", "batch_id": "new", "status": "running",
        "activity": {"step": 4, "operation": "T0 contacts"},
    }
    module.write_state(root, state)
    module.apply_command(root, "heartbeat", {"attempt_id": "new", "activity": {"step": 4}})
    current = json.loads((root / "data/current.json").read_text())
    assert current["readiness"]["printable"] is False
    assert "active calibration attempt" in current["readiness"]["reasons"][0]


def test_stale_mesh_acceptance_status_is_visible_to_dashboard_roadmap(tmp_path):
    module = load_module()
    state = module.empty_state()
    state["accepted"] = {
        "mesh": {
            "status": "stale",
            "stale_reason": "T0 frame changed",
            "data": {"mesh": {"status": "completed", "plot": "historical.png"}},
        },
    }
    module.write_state(tmp_path, state)
    current = json.loads((tmp_path / "data/current.json").read_text())
    mesh = current["chapters"]["bed_calibration"]["mesh"]
    assert mesh["status"] == "stale"
    assert mesh["stale_reason"] == "T0 frame changed"
