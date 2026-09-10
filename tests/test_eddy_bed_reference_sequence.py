import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/run_eddy_tap_bed_calibration.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("eddy_bed_runner", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeDashboard:
    def __init__(self):
        self.bed = {"reference": {}}
        self.messages = []

    def event(self, message, *, status=None):
        self.messages.append((message, status))


class FakeClient:
    def __init__(self):
        self.commands = []

    def gcode(self, command, *, timeout=60):
        self.commands.append(command)

    def status(self, *objects):
        index = len(self.commands)
        command = next(
            (value for value in reversed(self.commands) if value.startswith("_EDDY_TAP_MEASURE")),
            "",
        )
        count = int(next((part.split("=", 1)[1] for part in command.split() if part.startswith("COUNT=")), "1"))
        samples = [
            {"x": 150.0, "y": 150.0, "z": -0.001 * (index + offset)}
            for offset in range(count)
        ]
        return {
            "eddy_tap_measure": {
                "last_tap_measurement": {
                    "tap": {
                        "status": "completed",
                        "samples": samples,
                    },
                    "mesh": {"active_transform_z": None},
                }
            },
            "gcode_move": {"homing_origin": [0, 0, 0, 0]},
            "toolhead": {
                "position": [150, 150, 2, 0],
                "axis_minimum": [0, 0, -2.2, 0],
            },
            "idex_manual_tuning": {"active_tool": 0, "manual_z_adjust": 0},
            "temperature_probe btt_eddy": {"temperature": 40.0},
            "configfile": {
                "settings": {
                    "gcode_macro _IDEX_CONFIG_FINGERPRINT": {
                        "source_sha256": "test-fingerprint"
                    }
                }
            },
        }


def test_initial_discovery_uses_single_tap_bands():
    runner = load_runner()
    client = FakeClient()
    dashboard = FakeDashboard()

    result = runner.discover_reference(
        client,
        dashboard,
        x=150.0,
        y=150.0,
        phase="initial",
    )

    assert result["bands"][0]["status"] == "contact"
    measurement_commands = [
        command
        for command in client.commands
        if command.startswith("_EDDY_TAP_MEASURE")
    ]
    assert len(measurement_commands) == 1
    assert "COUNT=1" in measurement_commands[0]
    assert "START_Z=10.000000" in measurement_commands[0]
    assert "TAP_TARGET_Z=6.000000" in measurement_commands[0]
    assert "SAMPLE_RETRACT_DIST=4.000000" in measurement_commands[0]


def test_post_rebase_reference_uses_fixed_window_without_discovery():
    runner = load_runner()
    client = FakeClient()
    dashboard = FakeDashboard()

    result = runner.collect_reference(
        client,
        dashboard,
        x=150.0,
        y=150.0,
        phase="after_rebase",
        discovery=None,
    )

    assert result["verification_method"] == "fixed_zero_window"
    assert "discovery" not in result
    assert result["window"] == {"start_z": 2.0, "target_z": -1.0, "retract": 4.0}
    assert len(result["samples"]) == 5
    measurement_commands = [
        command
        for command in client.commands
        if command.startswith("_EDDY_TAP_MEASURE")
    ]
    assert len(measurement_commands) == 1
    assert "COUNT=5" in measurement_commands[0]
    assert "START_Z=2.000000" in measurement_commands[0]
    assert "TAP_TARGET_Z=-1.000000" in measurement_commands[0]
    assert "SAMPLE_RETRACT_DIST=4.000000" in measurement_commands[0]
