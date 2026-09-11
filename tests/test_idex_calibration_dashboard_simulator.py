import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/idex_calibration_dashboard_simulator.py"
FIXTURES = ROOT / "tests/fixtures/idex_calibration_dashboard"


def load_simulator_module():
    spec = importlib.util.spec_from_file_location("idex_dashboard_simulator", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def simulator(tmp_path):
    module = load_simulator_module()
    return module.Simulator(tmp_path / "simulation", FIXTURES)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixture_set_has_read_only_provenance_and_real_dashboard_inputs():
    provenance = json.loads((FIXTURES / "provenance.json").read_text())
    paths = {item["path"] for item in provenance["files"]}
    assert provenance["read_only"] is True
    assert provenance["source_calibration_root"] == "/home/pi/printer_data/calibration"
    assert {"seed_accepted.json", "captured_context.json", "moonraker_status.json", "moonraker_console.json", "camera.jpg"} <= paths
    assert any(path.endswith("T0_calibration.png") for path in paths)
    assert any(path.endswith("bed_mesh.png") for path in paths)
    for item in provenance["files"]:
        assert sha256(FIXTURES / item["path"]) == item["sha256"]


def test_active_candidate_replaces_old_accepted_tool_detail_without_leaking_plots(tmp_path):
    sim = simulator(tmp_path)
    sim.start("tool_alignment")
    sim.step(4, completed=8, total=31)
    current = sim.snapshot()["current"]
    candidate = current["chapters"]["tool_alignment"]["calibration"]
    assert candidate["status"] == "running"
    assert "verification" not in current["chapters"]["tool_alignment"]
    assert candidate["runs"]["t0"]["progress"] == {"completed": 8, "total": 31}
    assert "plot" not in candidate["runs"]["t0"]
    assert "plot" not in candidate["runs"]["t1"]
    assert current["accepted_sources"]["tool_alignment"]["attempt_id"]


def test_heartbeat_changes_only_activity_file_and_keeps_current_projection_byte_identical(tmp_path):
    sim = simulator(tmp_path)
    sim.start("full")
    current_path = sim.data_root / "current.json"
    accepted_path = sim.data_root / "accepted.json"
    before_current = sha256(current_path)
    before_accepted = sha256(accepted_path)
    before_activity = sha256(sim.data_root / "activity.json")
    sim.heartbeat()
    assert sha256(current_path) == before_current
    assert sha256(accepted_path) == before_accepted
    assert sha256(sim.data_root / "activity.json") != before_activity


def test_failed_rerun_preserves_accepted_history_and_terminal_activity(tmp_path):
    sim = simulator(tmp_path)
    original = sim.snapshot()["current"]["accepted"]["tool_alignment"]["attempt_id"]
    result = sim.scenario("failed-tool-rerun")
    assert result["current"]["status"] == "failed"
    assert result["current"]["accepted"]["tool_alignment"]["attempt_id"] == original
    assert result["activity"]["state"] == "failed"
    assert result["current"]["rollback"] == "Simulated accepted checkpoint preserved"


def test_ready_scenario_composes_captured_chapters_and_marks_printable(tmp_path):
    sim = simulator(tmp_path)
    result = sim.scenario("ready")
    assert result["current"]["status"] == "completed"
    assert result["current"]["readiness"]["printable"] is True
    assert result["activity"]["state"] == "completed"
    assert all(result["current"]["accepted"][chapter]["status"] == "accepted" for chapter in ("bed_reference", "tool_alignment", "mesh"))


def test_invalid_mixed_state_is_explicitly_diagnosed(tmp_path):
    sim = simulator(tmp_path)
    result = sim.scenario("invalid-mixed-state")
    assert result["diagnostics"] == ["Activity attempt ID does not match current attempt"]


def test_fresh_start_uses_new_attempt_and_does_not_inherit_candidate_progress(tmp_path):
    sim = simulator(tmp_path)
    first = sim.start("tool_alignment")["current"]["attempt"]["attempt_id"]
    sim.step(4, completed=11, total=31)
    second = sim.dispatch({"action": "restart", "scope": "tool_alignment"})["current"]
    assert second["attempt"]["attempt_id"] != first
    candidate = second["chapters"]["tool_alignment"]["calibration"]
    assert candidate["runs"]["t0"]["progress"]["completed"] == 0
