from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = REPO_ROOT / "klipper_setup/klipper_config/calib.yaml"
FIXED_CALIBRATION = REPO_ROOT / "klipper_setup/klipper_config/calib_config.yaml"
PRIMARY_BED_MESH = (
    REPO_ROOT / "klipper_setup/klipper_host/klippy/extras/bed_mesh.py"
)
IMAGE_BED_MESH = (
    REPO_ROOT
    / "klipper_setup/image_build/overlays/stage2/99-klipperpi/files"
    / "klipper_host/klippy/extras/bed_mesh.py"
)
UPDATER = REPO_ROOT / "klipper_setup/klipper_config/update_menderpi.sh"
IMAGE_INSTALLER = (
    REPO_ROOT
    / "klipper_setup/image_build/overlays/stage2/99-klipperpi/01-run-chroot.sh"
)


def test_bare_bed_mesh_calibrate_defaults_to_tap_and_keeps_nozzle_coordinates():
    source = PRIMARY_BED_MESH.read_text(encoding="utf-8")

    assert "'_BED_MESH_CALIBRATE_NATIVE'" in source
    assert 'probe_method = gcmd.get("METHOD", "tap").lower()' in source
    assert 'method = gcmd.get("METHOD", "tap").lower()' in source
    assert 'self.probe_helper.use_xy_offsets(method != "tap")' in source
    assert 'if method == "rapid_scan" and can_scan:' in source


def test_generated_mesh_commands_use_the_canonical_tap_macro():
    config = (REPO_ROOT / "klipper_setup/klipper_config/printer.cfg").read_text(
        encoding="utf-8"
    )
    fixed_calibration = yaml.safe_load(
        FIXED_CALIBRATION.read_text(encoding="utf-8")
    )

    canonical = config.split("[gcode_macro BED_MESH_CALIBRATE]", 1)[1].split(
        "[gcode_macro BED_MESH_IDEX_CALIBRATE]", 1
    )[0]
    compatibility = config.split("[gcode_macro BED_MESH_IDEX_CALIBRATE]", 1)[1].split(
        "[bed_mesh]", 1
    )[0]

    assert "T0\n    _BED_MESH_CALIBRATE_NATIVE" in canonical
    assert "METHOD=tap" in config
    assert "TAP_THRESHOLD={threshold}" in config
    assert "SETTLE_MS={settle_ms}" in config
    assert "BED_MESH_CALIBRATE SAMPLES={samples} SETTLE_MS={settle_ms}" in compatibility
    assert "\n    T0\n" not in compatibility
    assert "_BED_MESH_CALIBRATE_NATIVE" not in compatibility
    assert "PROFILE=default METHOD=tap" in config
    assert "[bed_mesh default]" in config
    assert "BED_MESH_PROFILE LOAD=default" in config
    assert "SAMPLES={samples}" in config
    assert "SAMPLES_RESULT=median" in config
    assert "default(1)" in config
    assert f"default({fixed_calibration['bed_mesh_settle_ms']})" in config
    assert "zero_reference_position: 150.000,150.000" in config
    assert "horizontal_move_z: 5.000" in config
    assert "probe_count: 7,7" in config


def test_tap_mesh_supports_an_explicit_per_point_settle_diagnostic():
    source = PRIMARY_BED_MESH.read_text(encoding="utf-8")

    assert "class SettledProbePointsHelper(probe.ProbePointsHelper):" in source
    assert 'gcmd.get_int("SETTLE_MS", 0, minval=0)' in source
    assert "super()._move_next(probe_num)" in source
    assert 'lookup_object("toolhead").dwell(self._settle_seconds)' in source


def test_direct_mesh_zero_reference_is_applied_once_to_an_aliased_matrix():
    source = PRIMARY_BED_MESH.read_text(encoding="utf-8")

    assert "# IDEX-managed override:" in source
    assert "matrices = [self.probed_matrix]" in source
    assert "if self.mesh_matrix is not self.probed_matrix:" in source
    assert "matrices.append(self.mesh_matrix)" in source


def test_tap_bed_mesh_primary_and_image_sources_match_and_are_managed():
    assert PRIMARY_BED_MESH.is_file()
    assert not IMAGE_BED_MESH.exists()

    updater = UPDATER.read_text(encoding="utf-8")
    assert 'SOURCE_HOST_ROOT="$SETUP_DIR/klipper_host"' in updater
    assert 'REMOTE_TMP_IDEX_MANUAL_TUNING' not in updater
    assert 'managed-overlay.json' in updater
    assert 'deadline = time.monotonic() + 60' in updater
    assert 'state") != "startup"' in updater

    image_installer = IMAGE_INSTALLER.read_text(encoding="utf-8")
    assert 'require_dir "${FILES_DIR}/klipper_host"' in image_installer
    assert '"${FILES_DIR}/klipper_host/klippy/" /opt/klipper/' in image_installer
