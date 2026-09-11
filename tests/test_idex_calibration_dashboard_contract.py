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
    style = (DASHBOARD / "style.css").read_text(encoding="utf-8")
    assert "Chapter 1 · steps 1–3" in html
    assert "Chapter 2 · step 4" in html
    assert "Chapter 3 · steps 5–7" in html
    assert "Chapter 1A" not in html
    assert "Chapter 1B" not in html
    assert 'id="last-successful"' in html
    assert 'id="activity"' in html
    assert 'id="activity-title"' in html
    assert 'class="printer-panels"' in html
    assert 'id="printer-console"' in html
    assert 'data-stream-url="/webcam/?action=stream"' in html
    assert "Units: coordinates, absolute Z, and the common Z correction are shown in mm" in html
    assert "31 contacts per tool" in html
    assert "13 contacts per tool" in html
    assert 'id="events"' not in html
    assert "last_successful.json" in script
    assert "run_scope" in script or "partial" in script
    for label in (
        "Bed Center Z=0 measurement",
        "Bed Center Z=0 calibration update",
        "Bed Center Z=0 verification",
        "T0/T1 toolhead alignment",
        "Acquire and save the Tap mesh",
        "Redeploy and verify the mesh",
        "Accepted calibration chain readiness",
    ):
        assert label in script
    for roadmap_id in (
        'id="bed-reference-roadmap"',
        'id="tool-alignment-roadmap"',
        'id="bed-mesh-roadmap"',
    ):
        assert roadmap_id in html
    assert "WORKFLOW_STEPS" in script
    assert "renderRoadmap" in script
    assert "centreTapStats" in script
    assert "verification-checks" in script
    assert "checks failed" in script
    assert "refreshPrinterContext" in script
    assert "startCameraStream" in script
    assert "printerCamera.src" in script
    assert "formatMillimetres" in script
    assert "formatConsoleTimestamp" in script
    assert "dashboardContentHash" in script
    assert "slice(-60).reverse()" in script
    assert "printerConsole.scrollTop = 0" in script
    assert "Initial discovery taps" in script
    assert "Post-correction verification taps" in script
    assert 'Bed centre</dt><dd>(150, 150), target Z=0 mm' in script
    assert '<th>Z (${discovery ? "mm" : "µm"})</th>' in script
    assert 'X (mm)</th><th>Y (mm)' not in script
    assert "/printer/objects/query?webhooks&toolhead&gcode_move&print_stats&extruder&extruder1&heater_bed" in script
    assert "/server/gcode_store?count=80" in script
    assert "humaniseConsoleMessage" in script
    assert "periphery" not in script.lower()
    assert "periphery" not in html.lower()
    assert 'bedReferenceChapter.hidden = false' in script
    assert 'bedMeshChapter.hidden = false' in script
    for state in ("pending", "running", "passed", "failed", "blocked"):
        assert f".workflow-step.{state}" in style
    assert ".workflow-step.remeasuring" in style
    assert "heartbeat_at" in script
    assert "BUSY · Step" in script
    assert "border-bottom: 1px solid #2b3745" in style


def test_mesh_refresh_is_a_no_argument_mesh_phase_wrapper():
    wrapper = (ROOT / "scripts/refresh_idex_bed_mesh.sh").read_text(encoding="utf-8")
    assert 'if [[ "$#" -ne 0 ]]' in wrapper
    assert "IDEX_EDDY_PHASE=mesh" in wrapper
    assert "run_eddy_tap_bed_calibration.sh" in wrapper

    full = (ROOT / "scripts/run_idex_calibration.sh").read_text(encoding="utf-8")
    assert '"${SCRIPT_DIR}/refresh_idex_bed_mesh.sh"' in full
    assert 'printer.cfg.template" "${batch_dir}/source/printer.cfg.template"' in full


def test_local_dashboard_simulator_is_explicitly_local_and_has_public_event_scripts():
    simulator = (ROOT / "scripts/idex_calibration_dashboard_simulator.py").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts/run_idex_calibration_dashboard_simulator.sh").read_text(encoding="utf-8")
    events = (ROOT / "scripts/idex_calibration_simulate.sh").read_text(encoding="utf-8")
    controls = (ROOT / "scripts/idex_calibration_dashboard_simulator_ui.js").read_text(encoding="utf-8")
    capture = (ROOT / "scripts/capture_idex_calibration_dashboard_simulator_fixtures.sh").read_text(encoding="utf-8")
    assert 'ThreadingHTTPServer(("127.0.0.1", args.port)' in simulator
    assert '"/printer/objects/query"' in simulator
    assert '"/server/gcode_store"' in simulator
    assert '"/webcam/"' in simulator
    assert 'window.__IDEX_SIMULATOR__=true' in simulator
    assert "--port" in launcher
    for action in ("reset", "scenario", "start", "step", "progress", "heartbeat", "complete-step", "complete-chapter", "fail-step", "restart", "set-heartbeat-age", "set-printer"):
        assert action in events
    assert "Local simulator" in controls
    assert "Consistency checks" in controls
    assert "Event log" in controls
    assert "sim-progress" in controls
    assert "read-only" in capture


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
