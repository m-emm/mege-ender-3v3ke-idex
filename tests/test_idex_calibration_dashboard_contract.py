import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "klipper_setup/klipper_config/calibration_dashboard"


def load_tool_runner():
    path = (
        ROOT
        / "klipper_setup/runtime_helpers/multi_head_zero_probe/run_multi_head_zero_contact_map.py"
    )
    spec = importlib.util.spec_from_file_location("multi_head_zero_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dashboard_uses_three_ordered_chapters():
    html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    script = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    assert "Chapter 1 · steps 1–3" in html
    assert "Chapter 2 · step 4" in html
    assert "Chapter 3 · steps 5–7" in html
    assert "Chapter 1A" not in html
    assert "Chapter 1B" not in html
    assert 'id="last-successful"' in html
    assert "last_successful.json" in script
    assert "run_scope" in script or "partial" in script


def test_mesh_refresh_is_a_no_argument_mesh_phase_wrapper():
    wrapper = (ROOT / "scripts/refresh_idex_bed_mesh.sh").read_text(encoding="utf-8")
    assert 'if [[ "$#" -ne 0 ]]' in wrapper
    assert "IDEX_EDDY_PHASE=mesh" in wrapper
    assert "run_eddy_tap_bed_calibration.sh" in wrapper

    full = (ROOT / "scripts/run_idex_calibration.sh").read_text(encoding="utf-8")
    assert '"${SCRIPT_DIR}/refresh_idex_bed_mesh.sh"' in full
    assert 'printer.cfg.template" "${batch_dir}/source/printer.cfg.template"' in full


def test_new_dashboard_batch_does_not_inherit_old_chapters(tmp_path, monkeypatch):
    runner = load_tool_runner()
    monkeypatch.setattr(runner, "DEFAULT_DASHBOARD_ROOT", str(tmp_path))
    current = tmp_path / "data" / "current.json"
    current.parent.mkdir()
    current.write_text(
        json.dumps(
            {
                "batch_id": "old",
                "chapters": {"bed_calibration": {"mesh": {"status": "passed"}}},
                "last_successful_batch_id": "old",
            }
        ),
        encoding="utf-8",
    )

    dashboard = runner.DashboardPublisher("new", "calibration", "both")
    chapter = dashboard.payload["chapters"]["tool_alignment"]["calibration"]
    assert chapter["run_id"] == "new"
    assert chapter["runs"] == {}
    assert "bed_calibration" not in dashboard.payload["chapters"]
    dashboard.finish("completed")
    saved = json.loads(current.read_text(encoding="utf-8"))
    assert "bed_calibration" not in saved["chapters"]
    assert saved["readiness"]["printable"] is False
    assert saved["readiness"]["reasons"]
    assert saved["last_successful_batch_id"] == "old"
