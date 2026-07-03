import importlib.util
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
KLIPPER_CONFIG_DIR = REPO_ROOT / "klipper_setup" / "klipper_config"
WIRING_DIR = KLIPPER_CONFIG_DIR / "wiring"
VALIDATOR_PATH = WIRING_DIR / "validate_wiring.py"


EXPECTED_KLIPPER_TAGS = {
    "stepper_x.step_pin",
    "stepper_x.dir_pin",
    "stepper_x.enable_pin",
    "stepper_x.endstop_pin",
    "tmc2209 stepper_x.uart_pin",
    "dual_carriage.step_pin",
    "dual_carriage.dir_pin",
    "dual_carriage.enable_pin",
    "dual_carriage.endstop_pin",
    "tmc2209 dual_carriage.uart_pin",
    "stepper_y.step_pin",
    "stepper_y.dir_pin",
    "stepper_y.enable_pin",
    "stepper_y.endstop_pin",
    "tmc2209 stepper_y.uart_pin",
    "stepper_z.step_pin",
    "stepper_z.dir_pin",
    "stepper_z.enable_pin",
    "stepper_z.endstop_pin",
    "tmc2209 stepper_z.uart_pin",
    "stepper_z1.step_pin",
    "stepper_z1.dir_pin",
    "stepper_z1.enable_pin",
    "stepper_z1.endstop_pin",
    "tmc2209 stepper_z1.uart_pin",
    "heater_bed.heater_pin",
    "heater_bed.boost_pin",
    "heater_bed.sensor_pin",
}


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_wiring", VALIDATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_active_wiring_matches_klipper_template():
    validator = _load_validator_module()

    assert validator.validate_wiring() == []


def test_active_wiring_tags_cover_expected_pico_klipper_pins():
    validator = _load_validator_module()
    tags = set(validator.iter_tagged_wiring_refs(validator.DEFAULT_WIRING_FILES))

    assert tags == EXPECTED_KLIPPER_TAGS


def test_generated_wiring_svgs_are_current():
    subprocess.run(
        [str(WIRING_DIR / "generate_wiring_svgs.sh"), "--check"],
        cwd=REPO_ROOT,
        check=True,
    )


def test_generated_yz_wiring_svg_includes_bed_thermistor_damping_capacitor():
    for view in ("top", "bottom"):
        svg_text = (
            WIRING_DIR / "diagrams" / f"pico_w_btt_tmc2226_y_z_{view}.svg"
        ).read_text()

        assert "C_BED_THERM_DAMP_100UF_POS" in svg_text
        assert "C_BED_THERM_DAMP_100UF_NEG" in svg_text


def test_active_looking_legacy_wiring_paths_are_removed():
    assert not (KLIPPER_CONFIG_DIR / "archive" / "wiring").exists()
    assert not (KLIPPER_CONFIG_DIR / "archive" / "snippets").exists()
    assert not (KLIPPER_CONFIG_DIR / "archive" / "scripts").exists()
    assert not (KLIPPER_CONFIG_DIR / "archive" / "legacy_configs").exists()
