import json
import importlib.util
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

from mege_3devops.process_data.mege_ender_3v3ke_idex import (
    SAFE_XY_ACCEL_MM_S2,
    SAFE_XY_SPEED_MM_S,
    copy_dual_petgcf_tpu95a_06_demo_process_data,
)
from mege_ender_3v3ke_idex.designs import (
    two_material_offset_line_calibration_grid as grid_calibration,
    two_material_offset_line_calibration_grid_x as x_grid_calibration,
    two_material_offset_line_calibration_grid_xy as xy_grid_calibration,
    two_material_offset_line_calibration_grid_y as y_grid_calibration,
)
from mege_ender_3v3ke_idex.designs.two_material_offset_line_calibration import (
    LINE_SEGMENT_LENGTH_MM,
    OFFSET_COUNT_EACH_SIDE,
    OFFSET_CANDIDATES_MM,
    OFFSET_STEP_MM,
    ZERO_CANDIDATE_INDEX,
    ZERO_LINE_SEGMENT_LENGTH_MM,
    format_offset_label,
    format_right_endpoint_label,
    parse_idex_calibration_values,
    segment_length_for_candidate,
    x_nominal_center_for_candidate,
    x_t1_center_for_endpoint_delta,
)


KLIPPER_CONFIG_DIR = (
    Path(__file__).resolve().parents[1] / "klipper_setup" / "klipper_config"
)
IMAGE_BUILD_FILES_DIR = (
    Path(__file__).resolve().parents[1]
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)
IMAGE_BUILD_STAGE_DIR = IMAGE_BUILD_FILES_DIR.parent
README_PATH = Path(__file__).resolve().parents[1] / "README.md"
VISION_JOB_CONCEPT_PATH = Path(__file__).resolve().parents[1] / "VISION_JOB_CONCEPT.md"
CONFIG_PATH = KLIPPER_CONFIG_DIR / "printer.cfg"
CALIB_PATH = KLIPPER_CONFIG_DIR / "calib.yaml"
TEMPLATE_PATH = KLIPPER_CONFIG_DIR / "printer.cfg.template"
GENERATOR_PATH = KLIPPER_CONFIG_DIR / "generate_printer_cfg.py"
NOZZLE_VISION_CALIBRATION_PATH = (
    KLIPPER_CONFIG_DIR / "apply_nozzle_vision_calibration.py"
)
Y_STEP_LOSS_GENERATOR_PATH = KLIPPER_CONFIG_DIR / "generate_y_step_loss_test_gcode.py"
Y_TMC_STALLGUARD_RUNNER_PATH = KLIPPER_CONFIG_DIR / "run_y_tmc_stallguard_diagnostic.py"

SYNTHETIC_CALIBRATION_VALUES = {
    "bed_grid_zero": (113.3, 107.0),
    "t0_x_endstop": -80.4,
    "t1_x_endstop": 355.7,
    "t0_y_endstop": -14.8,
    "t1_y_endstop": -15.6,
}

SYNTHETIC_CALIBRATION_YAML = """\
bed_grid_zero:
  x: 113.3
  y: 107.0
tools:
  t0:
    x_endstop: -80.4
    y_endstop: -14.8
    z_endstop: 293.75
  t1:
    x_endstop: 355.7
    y_endstop: -15.6
    z_endstop: 293.65
"""

SYNTHETIC_CONFIG_TEXT = """\
[dual_carriage]
position_endstop: 355.700
position_max: 355.700

[gcode_macro _IDEX_TOOL_STATE]
variable_t0_y_offset: 0.000
variable_t1_y_offset: 0.800
variable_t1_z_offset: 0.100
"""


def _load_generator_module():
    spec = importlib.util.spec_from_file_location(
        "generate_printer_cfg", GENERATOR_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_y_step_loss_generator_module():
    spec = importlib.util.spec_from_file_location(
        "generate_y_step_loss_test_gcode", Y_STEP_LOSS_GENERATOR_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_nozzle_vision_calibration_module():
    spec = importlib.util.spec_from_file_location(
        "apply_nozzle_vision_calibration", NOZZLE_VISION_CALIBRATION_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _section(config_text: str, name: str) -> str:
    match = re.search(
        rf"^\[{re.escape(name)}\]\n(?P<body>.*?)(?=^\[|\Z)",
        config_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Missing [{name}] section"
    return match.group("body")


def _setting_float(section: str, setting_name: str) -> float:
    match = re.search(
        rf"^\s*{re.escape(setting_name)}\s*:\s*(?P<value>\S+)\s*$",
        section,
        flags=re.MULTILINE,
    )
    assert match is not None, f"Missing setting {setting_name}"
    return float(match.group("value"))


def _setting_value(section: str, setting_name: str) -> str:
    match = re.search(
        rf"^\s*{re.escape(setting_name)}\s*:\s*(?P<value>\S+)\s*$",
        section,
        flags=re.MULTILINE,
    )
    assert match is not None, f"Missing setting {setting_name}"
    return match.group("value")


def _macro_variable_float(section: str, variable_name: str) -> float:
    return _setting_float(section, f"variable_{variable_name}")


def _live_config_status(
    fingerprint: str | None,
    *,
    state: str = "ready",
    save_config_pending: bool = False,
) -> dict:
    macro_config = {}
    if fingerprint is not None:
        macro_config["variable_source_sha256"] = f'"{fingerprint}"'
    return {
        "webhooks": {"state": state},
        "configfile": {
            "save_config_pending": save_config_pending,
            "config": {"gcode_macro _IDEX_CONFIG_FINGERPRINT": macro_config},
        },
    }


def test_printer_cfg_is_generated_from_calibration_source():
    generator = _load_generator_module()

    assert generator.render_config(CALIB_PATH, TEMPLATE_PATH) == CONFIG_PATH.read_text(
        encoding="utf-8"
    )
    assert (
        generator.main(
            [
                "--check",
                "--calib",
                str(CALIB_PATH),
                "--template",
                str(TEMPLATE_PATH),
                "--output",
                str(CONFIG_PATH),
            ]
        )
        == 0
    )


def test_printer_cfg_check_rejects_stale_output(tmp_path):
    generator = _load_generator_module()
    stale_cfg = tmp_path / "printer.cfg"
    stale_cfg.write_text("# stale\n", encoding="utf-8")

    assert (
        generator.main(
            [
                "--check",
                "--calib",
                str(CALIB_PATH),
                "--template",
                str(TEMPLATE_PATH),
                "--output",
                str(stale_cfg),
            ]
        )
        == 1
    )


def test_printer_cfg_includes_generated_fingerprint_macro():
    generator = _load_generator_module()
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    fingerprint = generator.compute_config_fingerprint(CALIB_PATH, TEMPLATE_PATH)
    fingerprint_section = _section(config_text, "gcode_macro _IDEX_CONFIG_FINGERPRINT")

    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    assert f'variable_source_sha256: "{fingerprint}"' in fingerprint_section


def test_printer_motion_limits_match_proven_idex_axes():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    printer = _section(config_text, "printer")

    for setting_name in (
        "max_velocity",
        "max_accel",
        "max_z_velocity",
        "max_z_accel",
        "square_corner_velocity",
    ):
        assert _setting_float(printer, setting_name) > 0.0
    assert "[force_move]" not in config_text


def test_vision_light_dotstar_and_macros():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    dotstar = _section(config_text, "dotstar vision_light")
    light_macro = _section(config_text, "gcode_macro VISION_LIGHT")
    off_macro = _section(config_text, "gcode_macro VISION_LIGHT_OFF")
    analysis_light_macro = _section(config_text, "gcode_macro NOZZLE_CAM_ANALYSIS_LIGHT")
    y_feature_light_macro = _section(
        config_text, "gcode_macro NOZZLE_CAM_Y_FEATURE_LIGHT"
    )
    startup_light = _section(
        config_text, "delayed_gcode _NOZZLE_CAM_ANALYSIS_LIGHT_ON_STARTUP"
    )

    assert _setting_value(dotstar, "data_pin")
    assert _setting_value(dotstar, "clock_pin")
    assert _setting_float(dotstar, "chain_count") == 8.0
    for channel in ("initial_RED", "initial_GREEN", "initial_BLUE"):
        assert _setting_float(dotstar, channel) >= 0.0
    assert "default_channel = params.R|default(1.0)|float" in light_macro
    assert "green = params.G|default(default_channel)|float" in light_macro
    assert "blue = params.B|default(default_channel)|float" in light_macro
    assert "index = params.INDEX|default(0)|int" in light_macro
    assert "SET_LED LED=vision_light INDEX={index}" in light_macro
    assert "SET_LED LED=vision_light RED={red} GREEN={green} BLUE={blue}" in light_macro
    assert "SET_LED LED=vision_light RED=0 GREEN=0 BLUE=0" in off_macro
    assert set(re.findall(r"INDEX=(\d+)", analysis_light_macro)) == {
        "1",
        "2",
        "5",
        "6",
        "7",
        "8",
    }
    assert "INDEX=3" not in analysis_light_macro
    assert "INDEX=4" not in analysis_light_macro
    assert "INDEX=9" not in analysis_light_macro
    assert "VISION_LIGHT_OFF" in y_feature_light_macro
    assert "INDEX=2 RED=0.450 GREEN=0.450 BLUE=0.450" in y_feature_light_macro
    assert "INDEX=1" not in y_feature_light_macro
    assert "NOZZLE_CAM_ANALYSIS_LIGHT" in startup_light


def test_vision_capture_macro_and_host_files_exist():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    vision_section = _section(config_text, "vision")
    macro = _section(config_text, "gcode_macro VISION_CAPTURE")
    nozzle_capture_macro = _section(config_text, "gcode_macro NOZZLE_CAM_CAPTURE")
    nozzle_profile_macro = _section(config_text, "gcode_macro NOZZLE_CAM_PROFILE")
    nozzle_analysis_capture_macro = _section(
        config_text, "gcode_macro NOZZLE_CAM_ANALYSIS_CAPTURE"
    )
    nozzle_sweep_macro = _section(config_text, "gcode_macro IDEX_NOZZLE_VISION_SWEEP")
    bed_y_sweep_macro = _section(config_text, "gcode_macro IDEX_BED_Y_VISION_SWEEP")
    nozzle_z_sweep_macro = _section(
        config_text, "gcode_macro IDEX_NOZZLE_Z_VISION_SWEEP"
    )
    moonraker = (IMAGE_BUILD_FILES_DIR / "moonraker.conf").read_text(encoding="utf-8")
    nginx = (IMAGE_BUILD_FILES_DIR / "nginx-mainsail.conf").read_text(encoding="utf-8")
    image_packages = (IMAGE_BUILD_STAGE_DIR / "00-packages").read_text(encoding="utf-8")
    image_install = (IMAGE_BUILD_STAGE_DIR / "01-run-chroot.sh").read_text(
        encoding="utf-8"
    )
    live_klipper_deploy = (KLIPPER_CONFIG_DIR / "update_menderpi.sh").read_text(
        encoding="utf-8"
    )
    live_deploy = (KLIPPER_CONFIG_DIR / "deploy_webcam_vision.sh").read_text(
        encoding="utf-8"
    )
    capture_service = (IMAGE_BUILD_FILES_DIR / "vision-capture.service").read_text(
        encoding="utf-8"
    )
    framebuffer_service = (
        IMAGE_BUILD_FILES_DIR / "vision-framebuffer.service"
    ).read_text(encoding="utf-8")
    nozzle_framebuffer_service = (
        IMAGE_BUILD_FILES_DIR / "vision-framebuffer-nozzle-cam.service"
    ).read_text(encoding="utf-8")
    nozzle_capture_service = (
        IMAGE_BUILD_FILES_DIR / "vision-capture-nozzle-cam.service"
    ).read_text(encoding="utf-8")
    framebuffer_script = (IMAGE_BUILD_FILES_DIR / "vision_framebuffer.py").read_text(
        encoding="utf-8"
    )
    capture_script = (IMAGE_BUILD_FILES_DIR / "vision_capture.py").read_text(
        encoding="utf-8"
    )
    klipper_vision_extra = (
        Path(__file__).resolve().parents[1]
        / "klipper_setup"
        / "klipper_host"
        / "klippy"
        / "extras"
        / "vision.py"
    ).read_text(encoding="utf-8")
    image_klipper_vision_extra = (
        IMAGE_BUILD_FILES_DIR / "klipper_host" / "klippy" / "extras" / "vision.py"
    ).read_text(encoding="utf-8")
    nozzle_script = (IMAGE_BUILD_FILES_DIR / "vision_nozzle_align.py").read_text(
        encoding="utf-8"
    )
    runner_script = (IMAGE_BUILD_FILES_DIR / "vision_runner.py").read_text(
        encoding="utf-8"
    )
    nozzle_profiles = json.loads(
        (IMAGE_BUILD_FILES_DIR / "nozzle_cam_profiles.json").read_text(encoding="utf-8")
    )

    assert "socket_path: /run/vision-capture-nozzle_cam/visiond.sock" in vision_section
    assert "timeout: 20.0" in vision_section
    assert "bed_y_calibrated:" in vision_section
    assert "[vision]" in template_text
    assert 'action_call_remote_method("vision_capture"' in macro
    assert "printer.toolhead.position" in macro
    assert 'RESPOND TYPE=echo MSG="Vision capture requested' in macro
    assert 'action_call_remote_method("nozzle_cam_capture"' in nozzle_capture_macro
    assert (
        'RESPOND TYPE=echo MSG="Nozzle camera capture requested' in nozzle_capture_macro
    )
    assert 'params.PROFILE|default("analysis")' in nozzle_capture_macro
    assert "profile=profile" in nozzle_capture_macro
    assert 'action_call_remote_method("nozzle_cam_profile"' in nozzle_profile_macro
    assert (
        'RESPOND TYPE=echo MSG="Nozzle camera profile requested' in nozzle_profile_macro
    )
    assert 'params.PROFILE|default("analysis")' in nozzle_profile_macro
    assert "NOZZLE_CAM_PROFILE PROFILE=analysis" in nozzle_analysis_capture_macro
    assert "NOZZLE_CAM_ANALYSIS_LIGHT" in nozzle_analysis_capture_macro
    assert "NOZZLE_CAM_CAPTURE NAME={name} REASON=nozzle_analysis PROFILE=analysis" in (
        nozzle_analysis_capture_macro
    )
    assert "keep_light = params.KEEP_LIGHT|default(1)|int" in (
        nozzle_analysis_capture_macro
    )
    assert "IDEX_NOZZLE_VISION_CHECK" not in config_text
    assert "idex_nozzle_vision_check" not in config_text
    assert 'action_call_remote_method("idex_nozzle_vision_sweep"' in nozzle_sweep_macro
    assert "print_stats.state" in nozzle_sweep_macro
    assert "requires X/Y/Z homed" in nozzle_sweep_macro
    assert "dx=dx" in nozzle_sweep_macro
    assert 'action_call_remote_method("idex_bed_y_vision_sweep"' in bed_y_sweep_macro
    assert "Y_OFFSETS" in bed_y_sweep_macro
    assert "y_offsets=y_offsets" in bed_y_sweep_macro
    assert "print_stats.state" in bed_y_sweep_macro
    assert "requires X/Y/Z homed" in bed_y_sweep_macro
    assert (
        'action_call_remote_method("idex_nozzle_z_vision_sweep"'
        in nozzle_z_sweep_macro
    )
    assert "BED_FEATURE_Z" in nozzle_z_sweep_macro
    assert "X_OFFSETS" in nozzle_z_sweep_macro
    assert "Z_VALUES" in nozzle_z_sweep_macro
    assert "current_t0_z_endstop=state.t0_z_endstop" in nozzle_z_sweep_macro
    assert "current_t1_z_endstop=state.t1_z_endstop" in nozzle_z_sweep_macro
    assert "print_stats.state" in nozzle_z_sweep_macro
    assert "requires X/Y/Z homed" in nozzle_z_sweep_macro
    assert not (IMAGE_BUILD_FILES_DIR / "crowsnest.conf").exists()
    assert "[webcam Printer Camera]" not in moonraker
    assert "[update_manager crowsnest]" not in moonraker
    assert "location /webcam/" in nginx
    assert "location /nozzle_cam/" in nginx
    assert "proxy_pass http://127.0.0.1:8081/" in nginx
    assert "location /vision/" in nginx
    assert "location = /home/pi/printer_data/vision/index.html" in nginx
    assert "return 302 /vision/" in nginx
    assert "return 302 /vision/$1" in nginx
    assert "ExecStart=/usr/local/bin/vision_framebuffer.py" in framebuffer_service
    assert "VISION_FRAMEBUFFER_PORT=8081" in nozzle_framebuffer_service
    assert (
        "VISION_FRAMEBUFFER_DIR=/run/vision-preview-nozzle_cam"
        in nozzle_framebuffer_service
    )
    assert (
        "VISION_FRAMEBUFFER_PUBLIC_SNAPSHOT_URL=/nozzle_cam/?action=snapshot"
        in nozzle_framebuffer_service
    )
    assert (
        "VISION_CAMERA_PROFILE_FILE=/usr/local/share/vision/nozzle_cam_profiles.json"
        in nozzle_framebuffer_service
    )
    assert "VISION_CAMERA_DEFAULT_PROFILE=analysis" in nozzle_framebuffer_service
    assert (
        "VISION_CAMERA_PROFILE_REQUEST_FILE=/run/vision-preview-nozzle_cam/profile_request.json"
        in nozzle_framebuffer_service
    )
    assert (
        "usb-Vimicro_corp._PC-LM1E_Camera_PC-LM1E_Audio-video-index0"
        in nozzle_framebuffer_service
    )
    assert "ThreadingHTTPServer" in framebuffer_script
    assert "RUN_DIR = Path" in framebuffer_script
    assert "latest.jpg" in framebuffer_script
    assert "RING_DIR" in framebuffer_script
    assert "CameraProfileManager" in framebuffer_script
    assert "VISION_CAMERA_PROFILE_FILE" in framebuffer_script
    assert "--set-ctrl=" in framebuffer_script
    assert '"camera_profile": camera_profile' in framebuffer_script
    assert "1920" in framebuffer_script
    assert "1080" in framebuffer_script
    assert "FALLBACK_FPS" not in framebuffer_script
    assert "Falling back to capture profile" not in framebuffer_script
    assert '"frame_seq": self.state.frame_seq' in framebuffer_script
    assert '"frame_seq": self.frame_seq' in framebuffer_script
    assert "ExecStart=/usr/local/bin/vision_capture.py --daemon" in capture_service
    assert "VISION_REGISTER_NOZZLE_METHODS=0" in capture_service
    assert "VISIOND_SOCKET_ENABLED=0" in capture_service
    assert "vision-framebuffer.service" in capture_service
    assert "VISION_CAPTURE_REMOTE_METHOD=nozzle_cam_capture" in nozzle_capture_service
    assert (
        "VISION_OUTPUT_DIR=/home/pi/printer_data/vision/nozzle_cam"
        in nozzle_capture_service
    )
    assert (
        "VISION_WEBCAM_SNAPSHOT_URL=http://127.0.0.1/nozzle_cam/?action=snapshot"
        in nozzle_capture_service
    )
    assert "VISION_REGISTER_NOZZLE_METHODS=1" in nozzle_capture_service
    assert (
        "VISION_CAMERA_PROFILE_REQUEST_FILE=/run/vision-preview-nozzle_cam/profile_request.json"
        in nozzle_capture_service
    )
    assert "VISION_CAPTURE_DEFAULT_PROFILE=analysis" in nozzle_capture_service
    assert "VISION_PROFILE_REMOTE_METHOD=nozzle_cam_profile" in nozzle_capture_service
    assert "RuntimeDirectory=vision-capture-nozzle_cam" in nozzle_capture_service
    assert "VISIOND_SOCKET=/run/vision-capture-nozzle_cam/visiond.sock" in (
        nozzle_capture_service
    )
    assert "VISION_JOB_ROOT=/home/pi/printer_data/vision/nozzle_cam/jobs" in (
        nozzle_capture_service
    )
    assert "vision-framebuffer-nozzle-cam.service" in nozzle_capture_service
    assert "register_remote_method" in capture_script
    assert (
        'REMOTE_METHOD = os.environ.get("VISION_CAPTURE_REMOTE_METHOD"'
        in capture_script
    )
    assert "REGISTER_NOZZLE_METHODS" in capture_script
    assert "NOZZLE_PROFILE_REMOTE_METHOD" in capture_script
    assert "request_framebuffer_profile" in capture_script
    assert "metadata_matches_profile" in capture_script
    assert "idex_nozzle_vision_check" not in capture_script
    assert "idex_nozzle_vision_sweep" in capture_script
    assert "idex_bed_y_vision_sweep" in capture_script
    assert "idex_nozzle_z_vision_sweep" in capture_script
    assert "run_nozzle_cam_profile" in capture_script
    assert "run_idex_nozzle_vision_sweep" in capture_script
    assert "run_idex_bed_y_vision_sweep" in capture_script
    assert "run_idex_nozzle_z_vision_sweep" in capture_script
    assert "vision_nozzle_align.py" in capture_script
    assert '"--sweep"' in capture_script
    assert '"--run-bed-y-job"' in capture_script
    assert '"--run-nozzle-z-job"' in capture_script
    assert "FRAMEBUFFER_LATEST_IMAGE" in capture_script
    assert "wait_for_buffered_frame" in capture_script
    assert "VisionJobApi" in capture_script
    assert "wait_for_buffered_frame_seq_after" in capture_script
    assert "framebuffer_seq" in capture_script
    assert "VISIOND_SOCKET" in capture_script
    assert 'capture_source": "vision_framebuffer' in capture_script
    assert "VISION_JOB_BEGIN" in klipper_vision_extra
    assert "VISION_CAPTURE_SYNC" in klipper_vision_extra
    assert "VISION_MEASURE_BED_Y" in klipper_vision_extra
    assert "last_bed_y_measurement" in klipper_vision_extra
    assert "wait_moves()" in klipper_vision_extra
    assert "socket.AF_UNIX" in klipper_vision_extra
    assert image_klipper_vision_extra == klipper_vision_extra
    assert "NOZZLE_ALIGN_DIR" not in nozzle_script
    assert "NOZZLE_SWEEP_DIR" in nozzle_script
    assert "VISION_OUTPUT_URL_PREFIX" in nozzle_script
    assert "--run-acquisition-job" in nozzle_script
    assert "--start-prepared-job" in nozzle_script
    assert "--analyze-job" in nozzle_script
    assert "--run-job" in nozzle_script
    assert "--prepare-bed-y-job" in nozzle_script
    assert "--run-bed-y-job" in nozzle_script
    assert "--prepare-nozzle-z-job" in nozzle_script
    assert "--run-nozzle-z-acquisition-job" in nozzle_script
    assert "--run-nozzle-z-job" in nozzle_script
    assert "nozzle_cam_bed_y_sweep" in nozzle_script
    assert "nozzle_cam_bed_y_motion" in nozzle_script
    assert "nozzle_cam_nozzle_z_sweep" in nozzle_script
    assert "nozzle_cam_nozzle_z_offsets" in nozzle_script
    assert "bed_y_axis_vector_px_per_mm" in nozzle_script
    assert "bed_y_scale_px_per_mm" in nozzle_script
    assert "bed_y_parallax_spread" in nozzle_script
    assert "calibration_candidate" in nozzle_script
    assert "tool_zero_error_mm" in nozzle_script
    assert "suggested_calib_yaml" in nozzle_script
    assert "NOZZLE_CAM_Y_FEATURE_LIGHT" in nozzle_script
    assert "NOZZLE_CAM_ANALYSIS_LIGHT" in nozzle_script
    assert "--refresh-ui" in nozzle_script
    assert "--virtual-sd-root" in nozzle_script
    assert "SDCARD_PRINT_FILE FILENAME=" in nozzle_script
    assert "index.html" in nozzle_script
    assert "jobs.json" in nozzle_script
    assert "raw_contact_sheet.jpg" in nozzle_script
    assert "overlay_contact_sheet.jpg" in nozzle_script
    assert "facts.json" in nozzle_script
    assert "--fresh-after-utc" in nozzle_script
    assert '"--sweep"' in nozzle_script
    assert "vision_framebuffer" in nozzle_script
    assert "cv2.HoughCircles" in nozzle_script
    assert "dark_contour" in nozzle_script
    assert "detect_red_marker" in nozzle_script
    assert "derive_global_nozzle_roi" in nozzle_script
    assert "single-image nozzle vision check was removed" in nozzle_script
    assert "fit_global_roi_cross_match" in nozzle_script
    assert "pairwise_match_matrix" in nozzle_script
    assert "global_roi_cross_match" in nozzle_script
    assert "perpendicular_mm_approx" in nozzle_script
    assert "cols, rows = max(1, len(dx_labels)), 2" in nozzle_script
    assert "fit_points_by_dx" in nozzle_script
    assert "choose_motion_consistent_nozzle" in nozzle_script
    assert "contact_sheet.jpg" in nozzle_script
    assert "latest_contact_sheet.jpg" in nozzle_script
    assert "IDEX nozzle sweep report" in nozzle_script
    assert "offsets_applied" in nozzle_script
    assert "IDEX_SET_TOOL_OFFSET" not in nozzle_script
    helper = NOZZLE_VISION_CALIBRATION_PATH.read_text(encoding="utf-8")
    assert "old_x + along_x_mm" in helper
    assert "new_y_offset = current_y_offset - perpendicular_mm" in helper
    assert "--update-y" in helper
    assert "--update-z" in helper
    assert "--update-bed-y" in helper
    assert "--reference-y-offset" in helper
    assert "nozzle_cam_nozzle_z_offsets" in helper
    assert 'vision_capture.py", "--capture-once"' in runner_script
    assert "acl\n" in image_packages
    assert "python3-opencv" in image_packages
    readme = README_PATH.read_text(encoding="utf-8")
    klipper_readme = (KLIPPER_CONFIG_DIR / "README.md").read_text(encoding="utf-8")
    concept = VISION_JOB_CONCEPT_PATH.read_text(encoding="utf-8")
    assert "http://menderpi.local/vision/" in readme
    assert "do not paste the filesystem path" in readme
    assert "vision_nozzle_align.py --refresh-ui" in readme
    assert "vision_nozzle_align.py --run-job" in readme
    assert "/home/pi/printer_data/vision/index.html" in readme
    assert "Nozzle Camera Bed Y Sweep" in klipper_readme
    assert "vision_nozzle_align.py --run-bed-y-job --name bed_y" in klipper_readme
    assert "IDEX_BED_Y_VISION_SWEEP NAME=bed_y" in klipper_readme
    assert "http://menderpi.local/vision/nozzle_cam/jobs/<job_id>/" in klipper_readme
    assert "bed_y_axis_vector_px_per_mm" in klipper_readme
    assert "negative image Y means the feature moves upward" in klipper_readme
    assert "Nozzle Camera Z Calibration Sweep" in klipper_readme
    assert "vision_nozzle_align.py --run-nozzle-z-job --name nozzle_z" in klipper_readme
    assert "IDEX_NOZZLE_Z_VISION_SWEEP NAME=nozzle_z" in klipper_readme
    assert "tool_zero_error_mm.T0" in klipper_readme
    assert "suggested_runtime_t1_z_offset" in klipper_readme
    assert "read-only generated static HTML/JSON" in concept
    assert "libevent-dev" not in image_packages
    assert "libjpeg-dev" not in image_packages
    assert "libbsd-dev" not in image_packages
    assert "vision_framebuffer.py" in image_install
    assert "klipper_host/klippy/extras/vision.py" in image_install
    assert "vision-framebuffer.service" in image_install
    assert "vision-framebuffer-nozzle-cam.service" in image_install
    assert "vision-capture-nozzle-cam.service" in image_install
    assert "nozzle_cam_profiles.json" in image_install
    assert "vision_nozzle_align.py" in image_install
    assert "vision_bed_y.py" in image_install
    assert "vision_framebuffer.py" in live_deploy
    assert "vision-framebuffer.service" in live_deploy
    assert "vision-framebuffer-nozzle-cam.service" in live_deploy
    assert "vision-capture-nozzle-cam.service" in live_deploy
    assert "nozzle_cam_profiles.json" in live_deploy
    assert "vision_nozzle_align.py" in live_deploy
    assert "vision_bed_y.py" in live_deploy
    assert "vision_nozzle_align.py --refresh-ui" in live_deploy
    assert "SOURCE_VISION" in live_klipper_deploy
    assert "REMOTE_TMP_VISION" in live_klipper_deploy
    assert "vision.py" in live_klipper_deploy
    assert "SOURCE_BED_Y_TEMPLATE" in live_klipper_deploy

    assert "/run/vision-preview-nozzle_cam/profile_request.json" in live_deploy
    assert "setfacl -m u:www-data:--x" in image_install
    assert "setfacl -m u:www-data:--x" in live_deploy
    assert "github.com/mainsail-crew/crowsnest" not in image_install
    assert "github.com/mainsail-crew/crowsnest" not in live_deploy
    assert "ln -sfn /opt/crowsnest" not in image_install
    assert "ln -sfn /opt/crowsnest" not in live_deploy
    assert "systemctl disable crowsnest" in image_install
    assert "systemctl disable --now crowsnest" in live_deploy
    assert '"name": "Printer Camera"' in live_deploy
    assert '"name": "nozzle_cam"' in live_deploy
    assert '"/nozzle_cam/?action=stream"' in live_deploy
    assert "--state-url http://127.0.0.1:8081/state" in live_deploy
    assert '"target_fps": "1"' in live_deploy

    assert nozzle_profiles["aliases"] == {
        "analysis": "nozzle_cam_analysis",
        "auto": "nozzle_cam_auto",
        "baseline": "nozzle_cam_baseline",
        "vision": "nozzle_cam_vision",
    }
    profile_controls = {
        name: {control["name"]: control["value"] for control in profile["controls"]}
        for name, profile in nozzle_profiles["profiles"].items()
    }
    for name in ("nozzle_cam_vision", "nozzle_cam_baseline", "nozzle_cam_analysis"):
        control_names = [
            control["name"] for control in nozzle_profiles["profiles"][name]["controls"]
        ]
        assert control_names[:4] == [
            "auto_exposure",
            "exposure_time_absolute",
            "white_balance_automatic",
            "white_balance_temperature",
        ]
        assert profile_controls[name]["auto_exposure"] == 1
        assert profile_controls[name]["white_balance_automatic"] == 0
    assert (
        profile_controls["nozzle_cam_vision"]["exposure_time_absolute"]
        > profile_controls["nozzle_cam_baseline"]["exposure_time_absolute"]
    )
    assert (
        profile_controls["nozzle_cam_analysis"]["exposure_time_absolute"]
        < profile_controls["nozzle_cam_vision"]["exposure_time_absolute"]
    )
    assert profile_controls["nozzle_cam_analysis"]["brightness"] <= 0
    assert profile_controls["nozzle_cam_auto"]["auto_exposure"] == 3
    assert profile_controls["nozzle_cam_auto"]["white_balance_automatic"] == 1


def test_nozzle_z_apply_helper_requires_explicit_update_z(tmp_path):
    helper = _load_nozzle_vision_calibration_module()
    payload = {
        "ok": True,
        "measurement": "nozzle_cam_nozzle_z_offsets",
        "suggested_calib_yaml": {
            "tools": {
                "t0": {"z_endstop": 293.812},
                "t1": {"z_endstop": 293.577},
            }
        },
        "suggested_runtime_t1_z_offset": 0.235,
    }
    measurement = helper.extract_measurement(payload, "facts.json")
    assert measurement["measurement"] == "nozzle_cam_nozzle_z_offsets"
    assert measurement["t0_z_endstop"] == pytest.approx(293.812)
    assert measurement["t1_z_endstop"] == pytest.approx(293.577)

    calib_path = tmp_path / "calib.yaml"
    calib_path.write_text(SYNTHETIC_CALIBRATION_YAML, encoding="utf-8")
    calib = helper.load_calib(calib_path)
    helper.apply_z_measurement(
        calib,
        t0_z_endstop=measurement["t0_z_endstop"],
        t1_z_endstop=measurement["t1_z_endstop"],
        update_z=False,
    )
    assert calib["tools"]["t0"]["z_endstop"] == pytest.approx(293.75)
    assert calib["tools"]["t1"]["z_endstop"] == pytest.approx(293.65)

    helper.apply_z_measurement(
        calib,
        t0_z_endstop=measurement["t0_z_endstop"],
        t1_z_endstop=measurement["t1_z_endstop"],
        update_z=True,
    )
    assert calib["tools"]["t0"]["z_endstop"] == pytest.approx(293.812)
    assert calib["tools"]["t1"]["z_endstop"] == pytest.approx(293.577)


def test_y_tmc_stallguard_runner_streams_live_samples_and_keeps_aggressive_opt_in():
    source = Y_TMC_STALLGUARD_RUNNER_PATH.read_text(encoding="utf-8")

    assert "tmc/stallguard_dump" in source
    assert "Y_TMC_STALLGUARD_ARM THRESHOLD={args.threshold}" in source
    assert "Y_TMC_STALLGUARD_DISARM" in source
    assert "SET_TMC_CURRENT STEPPER=stepper_y CURRENT=2.0" in source
    assert "threshold_compare={compare_value}" in source
    assert "thermal_bucket" in source
    assert 'parser.add_argument("--threshold", type=int, default=4)' in source
    assert 'parser.add_argument("--accel-sweep", action="store_true")' in source
    assert (
        'parser.add_argument("--sweep-accels", default="1000,2500,4000,6000,8000")'
        in source
    )
    assert (
        'parser.add_argument("--sweep-velocity", type=float, default=500.0)' in source
    )
    assert "run_accel_sweep(api, args)" in source
    assert "Stopping acceleration sweep after first StallGuard/DIAG trigger" in source
    assert 'result["triggered"]' in source
    assert 'parser.add_argument("--aggressive", action="store_true")' in source
    assert "if args.aggressive:" in source
    assert "Aggressive leg skipped" in source


def test_y_step_loss_assert_macro_checks_stepper_y_endstop():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    macro = _section(config_text, "gcode_macro Y_STEP_LOSS_ASSERT_ENDSTOP")

    assert 'printer.query_endstops.last_query["stepper_y"]' in macro
    assert "action_raise_error" in macro
    assert "profile=" in macro
    assert "velocity=" in macro
    assert "Y hot dry-run characterization failed" in macro
    assert "Heaters may still be on" in macro
    assert "re-home Y before normal printing" in macro


def test_y_step_loss_generator_emits_cold_quick_accel_ladder_checks(tmp_path):
    generator = _load_y_step_loss_generator_module()
    printer = generator.load_printer_config(CONFIG_PATH)
    plan = generator.TestPlan()
    gcode = generator.generate_gcode(printer, plan)
    output = tmp_path / "y_step_loss_characterization.gcode"
    expected_profile_names = [profile.name for profile in plan.stress_profiles]

    assert generator.main(["--config", str(CONFIG_PATH), "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == gcode
    assert not hasattr(generator, "load_y_axis_config")
    assert "--pattern" in generator.build_parser().format_help()
    assert "--mode" not in generator.build_parser().format_help()

    lines = [line.strip() for line in gcode.splitlines() if line.strip()]
    assert "; Endstop verification key: stepper_y" in lines
    assert (
        f"; Y configured range: {generator._format_float(printer.y.position_min)}.."
        f"{generator._format_float(printer.y.position_max)}"
    ) in lines
    assert f"; Y reset target: {generator._format_float(plan.reset_y_mm)}" in lines
    assert f"; Y stress target: {generator._format_float(plan.stress_y_mm)}" in lines
    assert f"; Stress profiles: {', '.join(expected_profile_names)}" in lines
    total_checks = len(plan.stress_profiles) * plan.cycles_per_profile
    assert f"; Cycles per profile: {plan.cycles_per_profile}" in lines
    assert f"; Total endstop checks: {total_checks}" in lines
    assert "M104 S0" in lines
    assert "M140 S0" in lines
    assert "M190" not in gcode
    assert "M109" not in gcode
    assert not re.search(r"^M104\s+S(?!0\b)", gcode, flags=re.MULTILINE)
    assert not re.search(r"^M140\s+S(?!0\b)", gcode, flags=re.MULTILINE)
    assert "T0" not in lines
    assert "G28 Y" in lines
    assert "G28 X Y Z" not in lines
    assert (
        f"G1 Y{generator._format_float(plan.reset_y_mm)} "
        f"F{generator._feedrate(plan.reset_velocity_mm_s)}"
    ) in lines
    assert (
        f"G1 Y{generator._format_float(plan.stress_y_mm)} "
        f"F{generator._feedrate(plan.stress_profiles[0].velocity_mm_s)}"
    ) in lines
    assert (
        f"G1 Y{generator._format_float(printer.y_position_endstop)} "
        f"F{generator._feedrate(plan.creep_velocity_mm_s)}"
    ) in lines
    assert "hot" not in gcode
    assert "Y away distance" not in gcode
    assert "hammer_hot_dry" not in gcode
    assert not re.search(r"^G[01]\b.*\bE-?\d", gcode, flags=re.MULTILINE)
    assert not re.search(r"^G[01]\b.*\bX-?\d", gcode, flags=re.MULTILINE)
    assert not re.search(r"^G[01]\b.*\bZ-?\d", gcode, flags=re.MULTILINE)

    assertion_lines = [
        line for line in lines if line.startswith("Y_STEP_LOSS_ASSERT_ENDSTOP ")
    ]
    assert len(assertion_lines) == total_checks
    profile_names = [
        re.search(r"\bPROFILE=(\S+)\b", line).group(1) for line in assertion_lines
    ]
    assert set(profile_names) == set(expected_profile_names)
    assert {name: profile_names.count(name) for name in set(profile_names)} == {
        name: 2 for name in expected_profile_names
    }
    accel_values = [
        int(re.search(r"\bACCEL=(\d+)\b", line).group(1)) for line in assertion_lines
    ]
    velocity_values = [
        int(re.search(r"\bVELOCITY=(\d+)\b", line).group(1)) for line in assertion_lines
    ]
    scv_values = [
        int(re.search(r"\bSCV=(\d+)\b", line).group(1)) for line in assertion_lines
    ]
    assert set(accel_values) == {
        int(profile.accel_mm_s2) for profile in plan.stress_profiles
    }
    assert set(velocity_values) == {
        int(profile.velocity_mm_s) for profile in plan.stress_profiles
    }
    assert set(scv_values) == {
        int(profile.square_corner_velocity) for profile in plan.stress_profiles
    }

    for index, line in enumerate(lines):
        if line.startswith("Y_STEP_LOSS_ASSERT_ENDSTOP "):
            assert lines[index - 1] == "QUERY_ENDSTOPS"

    stepper_y = _section(CONFIG_PATH.read_text(encoding="utf-8"), "stepper_y")
    y_min = _setting_float(stepper_y, "position_min")
    y_max = _setting_float(stepper_y, "position_max")
    x_targets = [
        float(match.group(1)) for match in re.finditer(r"\bX(-?\d+(?:\.\d+)?)\b", gcode)
    ]
    y_targets = [
        float(match.group(1)) for match in re.finditer(r"\bY(-?\d+(?:\.\d+)?)\b", gcode)
    ]
    z_targets = [
        float(match.group(1)) for match in re.finditer(r"\bZ(-?\d+(?:\.\d+)?)\b", gcode)
    ]
    assert not x_targets
    assert y_targets
    assert not z_targets
    assert min(y_targets) >= y_min - 1e-9
    assert max(y_targets) <= y_max + 1e-9


def test_y_step_loss_generator_emits_print_replay_y_pattern(tmp_path):
    generator = _load_y_step_loss_generator_module()
    printer = generator.load_printer_config(CONFIG_PATH)
    plan = generator.PrintReplayYPlan()
    gcode = generator.generate_print_replay_y_gcode(printer, plan)
    output = tmp_path / "y_step_loss_print_replay.gcode"
    expected_profile_names = [profile.name for profile in plan.stress_profiles]

    assert (
        generator.main(
            [
                "--config",
                str(CONFIG_PATH),
                "--pattern",
                "print-replay-y",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.read_text(encoding="utf-8") == gcode

    lines = [line.strip() for line in gcode.splitlines() if line.strip()]
    assert (
        "; Y print-replay step-loss characterization generated by generate_y_step_loss_test_gcode.py"
        in lines
    )
    assert (
        "; Suspect print travel leg: Y147.651 -> Y84.417 toward the Y endstop." in lines
    )
    assert f"; Y high replay target: {generator._format_float(plan.high_y_mm)}" in lines
    assert f"; Y low replay target: {generator._format_float(plan.low_y_mm)}" in lines
    assert f"; Cycles per check: {plan.cycles_per_check}" in lines
    assert f"; Checks per profile: {plan.checks_per_profile}" in lines
    assert f"; Stress profiles: {', '.join(expected_profile_names)}" in lines
    total_checks = len(plan.stress_profiles) * plan.checks_per_profile
    assert f"; Total endstop checks: {total_checks}" in lines
    assert "M104 S0" in lines
    assert "M140 S0" in lines
    assert "M190" not in gcode
    assert "M109" not in gcode
    assert not re.search(r"^M104\s+S(?!0\b)", gcode, flags=re.MULTILINE)
    assert not re.search(r"^M140\s+S(?!0\b)", gcode, flags=re.MULTILINE)
    assert "G90" in lines
    assert "G28 Y" in lines
    assert "G28 X Y Z" not in lines
    assert "T0" not in lines
    assert (
        "SET_VELOCITY_LIMIT VELOCITY=200 ACCEL=2000 SQUARE_CORNER_VELOCITY=2" in lines
    )
    assert (
        f"G1 Y{generator._format_float(plan.high_y_mm)} "
        f"F{generator._feedrate(plan.reset_velocity_mm_s)}"
    ) in lines
    assert (
        f"G1 Y{generator._format_float(printer.y_position_endstop)} "
        f"F{generator._feedrate(plan.creep_velocity_mm_s)}"
    ) in lines
    assert "hot" not in gcode
    assert not re.search(r"^G[01]\b.*\bE-?\d", gcode, flags=re.MULTILINE)
    assert not re.search(r"^G[01]\b.*\bX-?\d", gcode, flags=re.MULTILINE)
    assert not re.search(r"^G[01]\b.*\bZ-?\d", gcode, flags=re.MULTILINE)

    for profile in plan.stress_profiles:
        low_y_move = (
            f"G1 Y{generator._format_float(plan.low_y_mm)} "
            f"F{generator._feedrate(profile.velocity_mm_s)}"
        )
        assert (
            lines.count(low_y_move) == plan.checks_per_profile * plan.cycles_per_check
        )

    assertion_lines = [
        line for line in lines if line.startswith("Y_STEP_LOSS_ASSERT_ENDSTOP ")
    ]
    assert len(assertion_lines) == total_checks
    profile_names = [
        re.search(r"\bPROFILE=(\S+)\b", line).group(1) for line in assertion_lines
    ]
    assert set(profile_names) == set(expected_profile_names)
    assert {name: profile_names.count(name) for name in set(profile_names)} == {
        name: plan.checks_per_profile for name in expected_profile_names
    }
    for index, line in enumerate(lines):
        if line.startswith("Y_STEP_LOSS_ASSERT_ENDSTOP "):
            assert lines[index - 1] == "QUERY_ENDSTOPS"

    stepper_y = _section(CONFIG_PATH.read_text(encoding="utf-8"), "stepper_y")
    y_min = _setting_float(stepper_y, "position_min")
    y_max = _setting_float(stepper_y, "position_max")
    x_targets = [
        float(match.group(1)) for match in re.finditer(r"\bX(-?\d+(?:\.\d+)?)\b", gcode)
    ]
    y_targets = [
        float(match.group(1)) for match in re.finditer(r"\bY(-?\d+(?:\.\d+)?)\b", gcode)
    ]
    z_targets = [
        float(match.group(1)) for match in re.finditer(r"\bZ(-?\d+(?:\.\d+)?)\b", gcode)
    ]
    assert not x_targets
    assert y_targets
    assert not z_targets
    assert min(y_targets) >= y_min - 1e-9
    assert max(y_targets) <= y_max + 1e-9


def test_y_step_loss_generator_default_output_path_is_timestamped(tmp_path):
    generator = _load_y_step_loss_generator_module()

    default_path = generator.timestamped_output_path(
        now=datetime(2026, 7, 2, 10, 1, 58),
    )
    assert default_path == (
        generator.DEFAULT_OUTPUT_DIR
        / "y_step_loss_characterization_20260702_100158.gcode"
    )

    output_path = generator.timestamped_output_path(
        tmp_path,
        now=datetime(2026, 7, 2, 10, 1, 58),
    )

    assert (
        output_path == tmp_path / "y_step_loss_characterization_20260702_100158.gcode"
    )


def test_config_fingerprint_changes_when_source_inputs_change(tmp_path):
    generator = _load_generator_module()
    calib = tmp_path / "calib.yaml"
    template = tmp_path / "printer.cfg.template"
    calib_text = CALIB_PATH.read_text(encoding="utf-8")
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    calib.write_text(calib_text, encoding="utf-8")
    template.write_text(template_text, encoding="utf-8")

    original = generator.compute_config_fingerprint(calib, template)
    calib.write_text(f"{calib_text}\n# changed calibration source\n", encoding="utf-8")
    assert generator.compute_config_fingerprint(calib, template) != original

    calib.write_text(calib_text, encoding="utf-8")
    template.write_text(
        f"{template_text}\n# changed template source\n", encoding="utf-8"
    )
    assert generator.compute_config_fingerprint(calib, template) != original


def test_live_config_check_accepts_matching_ready_config():
    generator = _load_generator_module()
    fingerprint = "a" * 64

    assert (
        generator.live_config_check_errors(
            local_sha256="b" * 64,
            remote_sha256="b" * 64,
            expected_fingerprint=fingerprint,
            status=_live_config_status(fingerprint),
        )
        == []
    )


def test_live_config_check_rejects_remote_hash_mismatch():
    generator = _load_generator_module()
    errors = generator.live_config_check_errors(
        local_sha256="a" * 64,
        remote_sha256="b" * 64,
        expected_fingerprint="c" * 64,
        status=_live_config_status("c" * 64),
    )

    assert any("sha256 does not match" in error for error in errors)


@pytest.mark.parametrize("live_fingerprint", [None, "d" * 64])
def test_live_config_check_rejects_missing_or_different_live_fingerprint(
    live_fingerprint,
):
    generator = _load_generator_module()
    errors = generator.live_config_check_errors(
        local_sha256="a" * 64,
        remote_sha256="a" * 64,
        expected_fingerprint="c" * 64,
        status=_live_config_status(live_fingerprint),
    )

    assert errors
    assert any("fingerprint" in error for error in errors)


def test_live_config_check_rejects_non_ready_klippy_state():
    generator = _load_generator_module()
    errors = generator.live_config_check_errors(
        local_sha256="a" * 64,
        remote_sha256="a" * 64,
        expected_fingerprint="c" * 64,
        status=_live_config_status("c" * 64, state="startup"),
    )

    assert any("expected 'ready'" in error for error in errors)


def test_live_config_check_rejects_pending_save_config():
    generator = _load_generator_module()
    errors = generator.live_config_check_errors(
        local_sha256="a" * 64,
        remote_sha256="a" * 64,
        expected_fingerprint="c" * 64,
        status=_live_config_status("c" * 64, save_config_pending=True),
    )

    assert any("save_config_pending" in error for error in errors)


def test_boosted_heatbed_config_uses_measured_60c_pid():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    heater_bed = _section(config_text, "heater_bed")

    assert _setting_value(heater_bed, "heater_pin")
    assert _setting_value(heater_bed, "boost_pin")
    assert _setting_float(heater_bed, "primary_heater_power") > 0.0
    assert _setting_float(heater_bed, "boost_heater_power") > 0.0
    assert _setting_float(heater_bed, "pwm_cycle_time") > 0.0
    assert _setting_value(heater_bed, "sensor_pin")
    assert "control: pid" in heater_bed
    for setting_name in ("pid_Kp", "pid_Ki", "pid_Kd"):
        assert _setting_float(heater_bed, setting_name) > 0.0
    assert "max_delta:" not in heater_bed


def test_idex_part_fan_pins_and_slicer_routing():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    assert "pin: nitehawk:gpio6" in _section(config_text, "fan_generic left_part_fan")
    assert "pin: right_nitehawk:gpio6" in _section(
        config_text, "fan_generic right_part_fan"
    )

    fan_state = _section(config_text, "gcode_macro _IDEX_PART_FAN_STATE")
    assert "variable_speed: 0.0" in fan_state

    m106 = _section(config_text, "gcode_macro M106")
    assert "rename_existing" not in m106
    assert "SET_GCODE_VARIABLE MACRO=_IDEX_PART_FAN_STATE VARIABLE=speed" in m106
    assert "_IDEX_APPLY_PART_FAN TOOL={tool_state.active_tool|int}" in m106

    m107 = _section(config_text, "gcode_macro M107")
    assert "rename_existing" not in m107
    assert "SET_FAN_SPEED FAN=left_part_fan SPEED=0" in m107
    assert "SET_FAN_SPEED FAN=right_part_fan SPEED=0" in m107

    apply_fan = _section(config_text, "gcode_macro _IDEX_APPLY_PART_FAN")
    assert "SET_FAN_SPEED FAN=left_part_fan SPEED={speed}" in apply_fan
    assert "SET_FAN_SPEED FAN=left_part_fan SPEED=0" in apply_fan
    assert "SET_FAN_SPEED FAN=right_part_fan SPEED={speed}" in apply_fan
    assert "SET_FAN_SPEED FAN=right_part_fan SPEED=0" in apply_fan

    diagnostic = _section(config_text, "gcode_macro IDEX_SET_PART_FAN")
    assert "SET_FAN_SPEED FAN=left_part_fan SPEED={speed}" in diagnostic
    assert "SET_FAN_SPEED FAN=right_part_fan SPEED={speed}" in diagnostic

    assert "_IDEX_APPLY_PART_FAN TOOL=0" in _section(config_text, "gcode_macro T0")
    assert "_IDEX_APPLY_PART_FAN TOOL=1" in _section(config_text, "gcode_macro T1")


def test_t1_tap_light_barrier_button_is_notification_only():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    button = _section(config_text, "gcode_button tap_t1_light_barrier")

    assert "pin: ^!right_nitehawk:gpio10" in button
    assert 'RESPOND TYPE=echo MSG="T1 Tap light barrier triggered"' in button
    assert 'RESPOND TYPE=echo MSG="T1 Tap light barrier untriggered"' in button

    pin_refs = re.findall(
        r"^\s*(?P<setting>[A-Za-z0-9_]*pin)\s*:\s*(?P<pin>[^\n#]+)",
        config_text,
        flags=re.MULTILINE,
    )
    right_gpio10_refs = [
        (setting, pin.strip())
        for setting, pin in pin_refs
        if "right_nitehawk:gpio10" in pin
    ]
    assert right_gpio10_refs == [("pin", "^!right_nitehawk:gpio10")]

    for forbidden_section in ("probe", "bltouch", "dockable_probe"):
        assert f"[{forbidden_section}]" not in config_text
    assert "right_nitehawk:gpio10" not in _section(config_text, "stepper_x")
    assert "right_nitehawk:gpio10" not in _section(config_text, "dual_carriage")


def test_bed_cooling_macro_moves_t0_to_center_and_waits_for_target():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    bed_cooling = _section(config_text, "gcode_macro BED_COOLING")

    for variable_name in (
        "target",
        "x_center",
        "y_center",
        "z_height",
        "xy_move_speed",
        "z_move_speed",
        "fan_speed",
    ):
        assert _macro_variable_float(bed_cooling, variable_name) > 0.0

    assert "params.TARGET|default(target)|float" in bed_cooling
    assert "SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=0" in bed_cooling
    assert '"x" not in homed or "y" not in homed or "z" not in homed' in bed_cooling
    assert re.search(r"^\s*G28\s*$", bed_cooling, flags=re.MULTILINE)
    assert re.search(r"^\s*T0\s*$", bed_cooling, flags=re.MULTILINE)
    assert "G1 Z{z} F{z_feed}" in bed_cooling
    assert "G1 X{x} Y{y} F{xy_feed}" in bed_cooling
    assert "IDEX_SET_PART_FAN TOOL=both SPEED={fan_speed}" in bed_cooling
    assert "TEMPERATURE_WAIT SENSOR=heater_bed MAXIMUM={target_temp}" in bed_cooling
    assert re.search(r"^\s*M107\s*$", bed_cooling, flags=re.MULTILINE)


def test_x_travel_test_macros_are_gui_safe_and_test_both_toolheads():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    expected_macros = [
        ("TEST_X_TRAVEL_ACCEL_FOURK", 4000),
        ("TEST_X_TRAVEL_ACCEL_SIXK", 6000),
        ("TEST_X_TRAVEL_ACCEL_EIGHTK", 8000),
    ]

    alias = _section(config_text, "gcode_macro TEST_X_TRAVEL")
    assert "TEST_X_TRAVEL_ACCEL_FOURK" in alias

    for macro_name, accel in expected_macros:
        macro = _section(config_text, f"gcode_macro {macro_name}")
        assert f"_TEST_X_TRAVEL_RUN ACCEL={accel}" in macro

    runner = _section(config_text, "gcode_macro _TEST_X_TRAVEL_RUN")
    assert "printer.configfile.settings.stepper_x" in runner
    assert "printer.configfile.settings.dual_carriage" in runner
    assert "(left_min + left_max) / 2.0" in runner
    assert "(right_min + right_max) / 2.0" in runner
    assert "SET_DUAL_CARRIAGE CARRIAGE=0 MODE=PRIMARY" in runner
    assert "SET_DUAL_CARRIAGE CARRIAGE=1 MODE=PRIMARY" in runner
    assert "G1 X{left_park_x} F{park_feed}" in runner
    assert "G1 X{right_park_x} F{park_feed}" in runner
    assert "G1 X{left_mid} F{center_velocity * 60.0}" in runner
    assert "G1 X{left_target} F{test_velocity * 60.0}" in runner
    assert "G1 X{right_mid} F{center_velocity * 60.0}" in runner
    assert "G1 X{right_target} F{test_velocity * 60.0}" in runner
    assert re.search(r"^\s*G28 X\s*$", runner, flags=re.MULTILINE)
    assert re.search(r"^\s*T0\s*$", runner, flags=re.MULTILINE) is None
    assert re.search(r"^\s*T1\s*$", runner, flags=re.MULTILINE) is None
    assert "SAVE_GCODE_STATE NAME=TEST_X_TRAVEL_STATE" not in runner
    assert "RESTORE_GCODE_STATE NAME=TEST_X_TRAVEL_STATE" not in runner

    assert "gcode_macro TEST_Y_TRAVEL" not in config_text
    assert "gcode_macro _TEST_Y_TRAVEL_RUN" not in config_text
    assert "TEST_Y_TRAVEL_ACCEL_FOURK" not in config_text
    assert "TEST_Y_TRAVEL_ACCEL_EIGHTK" not in config_text

    assert "gcode_macro Y_TEST_TRAVEL_100" not in config_text
    assert "Y_TEST_TRAVEL_100_A4000" not in config_text


def test_x_driver_currents_are_raised_for_travel_testing():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    left_x_tmc = _section(config_text, "tmc2209 stepper_x")
    right_x_tmc = _section(config_text, "tmc2209 dual_carriage")

    assert _setting_float(left_x_tmc, "run_current") > 0.0
    assert _setting_float(right_x_tmc, "run_current") > 0.0


def test_idex_tool_selection_skips_offset_move_at_axis_edges():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    for macro_name, tool in [("T0", 0), ("T1", 1)]:
        macro = _section(config_text, f"gcode_macro {macro_name}")
        assert "printer.toolhead.axis_minimum" in macro
        assert "printer.toolhead.axis_maximum" in macro
        assert "offset_target_y" in macro
        assert "offset_target_z" in macro
        assert "can_move_offsets" in macro
        assert f"_IDEX_APPLY_TOOL_OFFSET TOOL={tool} MOVE={{can_move_offsets}}" in macro
        assert "offset compensation move skipped at current Y/Z edge" in macro


def test_mainsail_pause_resume_cancel_macros_are_defined():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    pause = _section(config_text, "gcode_macro PAUSE")
    assert "rename_existing: PAUSE_BASE" in pause
    assert re.search(r"^\s*PAUSE_BASE\s*$", pause, flags=re.MULTILINE)

    resume = _section(config_text, "gcode_macro RESUME")
    assert "rename_existing: RESUME_BASE" in resume
    assert "RESUME_BASE {rawparams}" in resume

    cancel = _section(config_text, "gcode_macro CANCEL_PRINT")
    assert "rename_existing: CANCEL_PRINT_BASE" in cancel
    assert "M107" in cancel
    assert "TURN_OFF_HEATERS" in cancel
    assert "CLEAR_PAUSE" in cancel
    assert "_IDEX_CANCEL_PARK" in cancel
    assert cancel.rstrip().endswith("CANCEL_PRINT_BASE")
    assert "M84" not in cancel


def test_idex_cancel_park_is_homed_axis_guarded():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    cancel_park = _section(config_text, "gcode_macro _IDEX_CANCEL_PARK")

    assert '"z" in homed' in cancel_park
    assert '"x" in homed' in cancel_park
    assert '"y" in homed' in cancel_park
    assert "position.z|float + 5.0" in cancel_park
    assert "axis_max.z|float" in cancel_park
    assert "tool_state.active_tool|int == 0" in cancel_park
    assert "IDEX_SELECT_LEFT" in cancel_park
    assert "IDEX_SELECT_RIGHT" in cancel_park
    assert "axis_max.y|float - 5.0" in cancel_park
    assert "M84" not in cancel_park


def test_idex_next_printable_corner_cycles_configured_safe_corners():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    corner_macro = _section(config_text, "gcode_macro IDEX_NEXT_PRINTABLE_CORNER")

    assert "variable_corner_index: 0" in corner_macro
    x_min = _macro_variable_float(corner_macro, "x_min")
    x_max = _macro_variable_float(corner_macro, "x_max")
    y_min = _macro_variable_float(corner_macro, "y_min")
    y_max = _macro_variable_float(corner_macro, "y_max")
    assert x_min < x_max
    assert y_min < y_max
    assert _macro_variable_float(corner_macro, "z_travel") > 0.0
    assert _macro_variable_float(corner_macro, "z_touch") >= 0.0
    assert "variable_xy_move_speed:" in corner_macro
    assert "variable_z_move_speed:" in corner_macro

    assert '"x" not in homed' in corner_macro
    assert '"y" not in homed' in corner_macro
    assert '"z" not in homed' in corner_macro
    assert "Home X, Y, and Z before running IDEX_NEXT_PRINTABLE_CORNER." in corner_macro

    assert "front-left" in corner_macro
    assert "front-right" in corner_macro
    assert "back-right" in corner_macro
    assert "back-left" in corner_macro
    assert "next_index = (index + 1) % 4" in corner_macro
    assert (
        "SET_GCODE_VARIABLE MACRO=IDEX_NEXT_PRINTABLE_CORNER "
        "VARIABLE=corner_index VALUE={next_index}"
    ) in corner_macro

    assert "tool_state.active_tool|int == 0" in corner_macro
    assert "IDEX_SELECT_LEFT" in corner_macro
    assert "IDEX_SELECT_RIGHT" in corner_macro

    z_travel_index = corner_macro.index("G1 Z{z_travel|float}")
    xy_index = corner_macro.index("G1 X{target_x} Y{target_y}")
    z_touch_index = corner_macro.index("G1 Z{z_touch|float}")
    assert z_travel_index < xy_index < z_touch_index


def test_idex_tool_selection_resets_next_printable_corner():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    reset_counter = (
        "SET_GCODE_VARIABLE MACRO=IDEX_NEXT_PRINTABLE_CORNER "
        "VARIABLE=corner_index VALUE=0"
    )

    for macro_name in ["T0", "T1"]:
        tool_macro = _section(config_text, f"gcode_macro {macro_name}")
        assert reset_counter in tool_macro


def test_idex_tool_offsets_are_derived_from_calibration_values():
    generator = _load_generator_module()
    calibration = {
        "bed_grid_zero": {"x": 1.0, "y": 2.0},
        "tools": {
            "t0": {"x_endstop": -10.0, "y_endstop": -1.0, "z_endstop": 100.0},
            "t1": {"x_endstop": 220.0, "y_endstop": -1.4, "z_endstop": 99.7},
        },
    }

    values = generator.template_values(calibration, "synthetic-fingerprint")

    assert values["t0_x_endstop"] == "-10.000"
    assert values["t1_x_endstop"] == "220.000"
    assert values["t0_y_offset"] == "0.000"
    assert values["t1_y_offset"] == "0.400"
    assert values["t1_z_offset"] == "0.300"


def test_camera_repeatability_generator_is_y_only_and_defaults_to_one_safe_profile():
    generator = _load_y_step_loss_generator_module()
    printer = generator.PrinterConfig(
        x=generator.AxisRange(-80.4, 244.0),
        y=generator.AxisRange(-14.8, 296.0),
        z=generator.AxisRange(-1.0, 293.75),
        y_position_endstop=-14.8,
        max_velocity=500.0,
        max_accel=6000.0,
        square_corner_velocity=5.0,
        bed_y_calibrated=True,
        bed_y_reference_y_mm=-4.8,
        bed_y_profile="analysis",
    )
    plan = generator.CameraRepeatabilityPlan(run_id="test_camera_repeatability")
    gcode = generator.generate_camera_repeatability_gcode(printer, plan)
    lines = gcode.splitlines()

    measure_lines = [line for line in lines if line.startswith("VISION_MEASURE_BED_Y ")]
    assert len(measure_lines) == 21
    assert sum(line == "G28 Y" for line in lines) == 1
    assert "QUERY_ENDSTOPS" not in gcode
    assert "Y_STEP_LOSS_ASSERT_ENDSTOP" not in gcode
    assert "M104 S0" in lines
    assert "M140 S0" in lines
    motion_lines = [line for line in lines if re.match(r"^G[01]\s", line)]
    assert all(" X" not in line and " Z" not in line for line in motion_lines)
    assert not any(line in {"T0", "T1"} for line in lines)
    assert gcode.count("profile=accel_1000") == 20
    restore = "SET_VELOCITY_LIMIT VELOCITY=500 ACCEL=6000 SQUARE_CORNER_VELOCITY=5"
    for index, line in enumerate(lines):
        if line.startswith("VISION_MEASURE_BED_Y "):
            assert restore in lines[max(0, index - 5) : index]


def test_camera_repeatability_acceleration_ladder_is_cli_configurable():
    generator = _load_y_step_loss_generator_module()
    printer = generator.PrinterConfig(
        x=generator.AxisRange(-80.4, 244.0),
        y=generator.AxisRange(-14.8, 296.0),
        z=generator.AxisRange(-1.0, 293.75),
        y_position_endstop=-14.8,
        max_velocity=500.0,
        max_accel=6000.0,
        square_corner_velocity=5.0,
        bed_y_calibrated=True,
        bed_y_reference_y_mm=-4.8,
        bed_y_profile="analysis",
    )
    plan = generator.CameraRepeatabilityPlan(
        checks_per_profile=2,
        velocity_mm_s=500.0,
        accel_start_mm_s2=3500.0,
        accel_stop_mm_s2=4500.0,
        accel_step_mm_s2=500.0,
    )
    profiles = generator.camera_stress_profiles(plan)
    assert [profile.accel_mm_s2 for profile in profiles] == [3500.0, 4000.0, 4500.0]
    gcode = generator.generate_camera_repeatability_gcode(printer, plan)
    assert gcode.count("VISION_MEASURE_BED_Y ") == 7

    with pytest.raises(ValueError, match="step must be positive"):
        generator.camera_stress_profiles(
            generator.CameraRepeatabilityPlan(
                accel_start_mm_s2=1000.0,
                accel_stop_mm_s2=2000.0,
                accel_step_mm_s2=0.0,
            )
        )


def test_grid_calibration_reads_yaml_values(tmp_path):
    calib_path = tmp_path / "calib.yaml"
    calib_path.write_text(SYNTHETIC_CALIBRATION_YAML, encoding="utf-8")

    values = grid_calibration.read_grid_calibration(calib_path)

    assert values["bed_grid_zero"] == pytest.approx(
        SYNTHETIC_CALIBRATION_VALUES["bed_grid_zero"]
    )
    assert values["t0_x_endstop"] == pytest.approx(
        SYNTHETIC_CALIBRATION_VALUES["t0_x_endstop"]
    )
    assert values["t1_x_endstop"] == pytest.approx(
        SYNTHETIC_CALIBRATION_VALUES["t1_x_endstop"]
    )
    assert values["t0_y_endstop"] == pytest.approx(
        SYNTHETIC_CALIBRATION_VALUES["t0_y_endstop"]
    )
    assert values["t1_y_endstop"] == pytest.approx(
        SYNTHETIC_CALIBRATION_VALUES["t1_y_endstop"]
    )


def test_offset_line_calibration_parses_config_values():
    values = parse_idex_calibration_values(SYNTHETIC_CONFIG_TEXT)

    assert values["right_x_endpoint"] == pytest.approx(355.7)
    assert values["t0_y"] == pytest.approx(0.0)
    assert values["t1_y"] == pytest.approx(0.8)


def test_offset_line_calibration_rejects_nonzero_t0_y_offset():
    config_text = SYNTHETIC_CONFIG_TEXT
    config_text = re.sub(
        r"variable_t0_y_offset: \S+",
        "variable_t0_y_offset: 0.1",
        config_text,
    )

    with pytest.raises(ValueError, match="T0 Y offset must be 0.0"):
        parse_idex_calibration_values(config_text)


def test_offset_line_calibration_rejects_x_tool_offsets():
    config_text = SYNTHETIC_CONFIG_TEXT
    config_text = re.sub(
        r"variable_t0_y_offset: \S+",
        "variable_t0_x_offset: 0.0\nvariable_t0_y_offset: 0.0",
        config_text,
    )

    with pytest.raises(ValueError, match="variable_t0_x_offset"):
        parse_idex_calibration_values(config_text)


def test_offset_line_calibration_rejects_mismatched_right_endpoint_values():
    config_text = SYNTHETIC_CONFIG_TEXT
    dual_carriage = _section(config_text, "dual_carriage")
    right_endpoint = _setting_float(dual_carriage, "position_endstop")
    mismatched_max = right_endpoint - 0.2
    modified_dual_carriage, replacement_count = re.subn(
        r"(?m)^position_max: \S+",
        f"position_max: {mismatched_max:.3f}",
        dual_carriage,
        count=1,
    )
    assert replacement_count == 1
    config_text = config_text.replace(dual_carriage, modified_dual_carriage, 1)

    with pytest.raises(ValueError, match="position_endstop and position_max"):
        parse_idex_calibration_values(config_text)


def test_offset_line_calibration_formats_offset_labels():
    assert format_offset_label(0.0) == "0.0"
    assert format_offset_label(-0.0) == "0.0"
    assert format_offset_label(0.14) == "0.1"
    assert format_offset_label(-0.64) == "-0.6"


def test_offset_line_calibration_formats_right_endpoint_labels():
    assert format_right_endpoint_label(344.4) == "4.4"
    assert format_right_endpoint_label(344.9) == "4.9"
    assert format_right_endpoint_label(345.0) == "5.0"
    assert format_right_endpoint_label(345.4) == "5.4"


def test_offset_line_calibration_candidates_are_centered_on_zero():
    assert len(OFFSET_CANDIDATES_MM) == 2 * OFFSET_COUNT_EACH_SIDE + 1
    assert OFFSET_CANDIDATES_MM[ZERO_CANDIDATE_INDEX] == 0.0
    assert OFFSET_CANDIDATES_MM[0] == pytest.approx(
        -OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )
    assert OFFSET_CANDIDATES_MM[-1] == pytest.approx(
        OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )

    for index, candidate_offset in enumerate(OFFSET_CANDIDATES_MM):
        mirror_index = 2 * ZERO_CANDIDATE_INDEX - index
        assert OFFSET_CANDIDATES_MM[mirror_index] == pytest.approx(-candidate_offset)


def test_offset_line_calibration_long_marker_is_center_zero_candidate():
    for index in range(len(OFFSET_CANDIDATES_MM)):
        if index == ZERO_CANDIDATE_INDEX:
            assert segment_length_for_candidate(index) == ZERO_LINE_SEGMENT_LENGTH_MM
        else:
            assert segment_length_for_candidate(index) == LINE_SEGMENT_LENGTH_MM


def test_offset_line_calibration_labels_parsed_offsets():
    values = parse_idex_calibration_values(SYNTHETIC_CONFIG_TEXT)

    x_labels = [
        format_right_endpoint_label(values["right_x_endpoint"] + candidate_offset)
        for candidate_offset in OFFSET_CANDIDATES_MM
    ]
    y_labels = [
        format_offset_label(values["t1_y"] + candidate_offset)
        for candidate_offset in OFFSET_CANDIDATES_MM
    ]

    assert x_labels[ZERO_CANDIDATE_INDEX] == format_right_endpoint_label(
        values["right_x_endpoint"]
    )
    assert y_labels[ZERO_CANDIDATE_INDEX] == format_offset_label(values["t1_y"])
    assert x_labels[0] == format_right_endpoint_label(
        values["right_x_endpoint"] - OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )
    assert x_labels[-1] == format_right_endpoint_label(
        values["right_x_endpoint"] + OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )
    assert y_labels[0] == format_offset_label(
        values["t1_y"] - OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )
    assert y_labels[-1] == format_offset_label(
        values["t1_y"] + OFFSET_STEP_MM * OFFSET_COUNT_EACH_SIDE
    )


def test_offset_line_calibration_x_endpoint_delta_moves_t1_opposite_direction():
    middle_index = len(OFFSET_CANDIDATES_MM) // 2
    nominal_x = x_nominal_center_for_candidate(middle_index)

    assert x_t1_center_for_endpoint_delta(middle_index, 0.1) == pytest.approx(
        nominal_x - 0.1
    )
    assert x_t1_center_for_endpoint_delta(middle_index, -0.1) == pytest.approx(
        nominal_x + 0.1
    )


def test_absolute_y_calibration_candidates_move_same_direction():
    painted_grid_y = 107.0

    assert y_grid_calibration.y_line_center_for_calibration_offset(
        painted_grid_y, 0.3
    ) == pytest.approx(106.7)
    assert y_grid_calibration.y_line_center_for_calibration_offset(
        painted_grid_y, -0.3
    ) == pytest.approx(107.3)


def test_absolute_grid_plate_definitions_split_y_calibration():
    plate_definitions = y_grid_calibration.create_plate_definitions(
        {
            y_grid_calibration.Y_T0_PLATE_NAME: ("y_t0_preview",),
            y_grid_calibration.Y_T1_PLATE_NAME: ("y_t1_preview",),
        }
    )

    assert [plate["name"] for plate in plate_definitions] == [
        y_grid_calibration.Y_T0_PLATE_NAME,
        y_grid_calibration.Y_T1_PLATE_NAME,
    ]
    assert plate_definitions[0]["parts"] == [
        "y_t0_preview",
        y_grid_calibration.Y_T0_LINES_PART_NAME,
        y_grid_calibration.Y_T0_LABELS_PART_NAME,
    ]
    assert plate_definitions[1]["parts"] == [
        "y_t1_preview",
        y_grid_calibration.Y_T1_LINES_PART_NAME,
        y_grid_calibration.Y_T1_LABELS_PART_NAME,
    ]


def test_absolute_grid_plate_definitions_split_x_calibration():
    plate_definitions = x_grid_calibration.create_plate_definitions(
        {
            x_grid_calibration.X_T0_PLATE_NAME: ("x_t0_preview",),
            x_grid_calibration.X_T1_PLATE_NAME: ("x_t1_preview",),
        }
    )

    assert [plate["name"] for plate in plate_definitions] == [
        x_grid_calibration.X_T0_PLATE_NAME,
        x_grid_calibration.X_T1_PLATE_NAME,
    ]
    assert plate_definitions[0]["parts"] == [
        "x_t0_preview",
        x_grid_calibration.X_T0_LINES_PART_NAME,
        x_grid_calibration.X_T0_LABELS_PART_NAME,
    ]
    assert plate_definitions[1]["parts"] == [
        "x_t1_preview",
        x_grid_calibration.X_T1_LINES_PART_NAME,
        x_grid_calibration.X_T1_LABELS_PART_NAME,
    ]


def test_absolute_grid_y_part_metadata_routes_base_and_text_materials():
    metadata = y_grid_calibration.CALIBRATION_PART_METADATA

    assert metadata[y_grid_calibration.Y_T0_LINES_PART_NAME] == {
        "production_group": y_grid_calibration.Y_T0_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    }
    assert metadata[y_grid_calibration.Y_T0_LABELS_PART_NAME] == {
        "production_group": y_grid_calibration.Y_T0_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    }
    assert metadata[y_grid_calibration.Y_T1_LINES_PART_NAME] == {
        "production_group": y_grid_calibration.Y_T1_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    }
    assert metadata[y_grid_calibration.Y_T1_LABELS_PART_NAME] == {
        "production_group": y_grid_calibration.Y_T1_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    }


def test_absolute_grid_x_part_metadata_routes_base_and_text_materials():
    metadata = x_grid_calibration.CALIBRATION_PART_METADATA

    assert metadata[x_grid_calibration.X_T0_LINES_PART_NAME] == {
        "production_group": x_grid_calibration.X_T0_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    }
    assert metadata[x_grid_calibration.X_T0_LABELS_PART_NAME] == {
        "production_group": x_grid_calibration.X_T0_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    }
    assert metadata[x_grid_calibration.X_T1_LINES_PART_NAME] == {
        "production_group": x_grid_calibration.X_T1_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    }
    assert metadata[x_grid_calibration.X_T1_LABELS_PART_NAME] == {
        "production_group": x_grid_calibration.X_T1_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    }


def test_absolute_xy_calibration_uses_petgcf_tpu_process_structure():
    source = Path(xy_grid_calibration.__file__).read_text(encoding="utf-8")
    process_data = copy_dual_petgcf_tpu95a_06_demo_process_data()
    overrides = process_data["process_overrides"]
    outer_wall_line_width = float(overrides["outer_wall_line_width"])

    assert "copy_dual_petgcf_tpu95a_06_demo_process_data" in source
    assert "copy_dual_pla_06_standard_process_data" not in source
    assert "copy_xy_offset_calibration_process_data" not in source
    assert "wipe_tower_x" not in source
    assert "wipe_tower_y" not in source
    assert len(process_data["filaments"]) == 2
    assert process_data["filaments"][0] == process_data["filament"]
    assert process_data["filaments"][1] != process_data["filaments"][0]
    for key in (
        "enable_prime_tower",
        "wipe_tower_x",
        "wipe_tower_y",
        "hot_plate_temp",
        "hot_plate_temp_initial_layer",
        "travel_speed",
    ):
        assert key in overrides
    assert float(overrides["travel_speed"]) <= SAFE_XY_SPEED_MM_S
    for key in (
        "default_acceleration",
        "initial_layer_acceleration",
        "outer_wall_acceleration",
        "inner_wall_acceleration",
        "top_surface_acceleration",
        "travel_acceleration",
        "sparse_infill_acceleration",
        "internal_solid_infill_acceleration",
        "bridge_acceleration",
    ):
        assert float(overrides[key]) <= SAFE_XY_ACCEL_MM_S2
    assert len(overrides["z_hop"]) == 2
    assert len(overrides["z_hop_types"]) == 2
    assert float(overrides["filament_z_hop"]) > 0.0
    assert overrides["filament_z_hop_types"]
    assert float(overrides["line_width"]) >= outer_wall_line_width
    assert float(overrides["initial_layer_line_width"]) >= float(
        overrides["outer_wall_line_width"]
    )
    assert (
        grid_calibration.CALIBRATION_LABEL_STROKE_WIDTH_MM
        >= outer_wall_line_width * 1.5
    )
    assert grid_calibration.CALIBRATION_LABEL_TEXT_THICKNESS_MM >= float(
        overrides["layer_height"]
    )


def test_absolute_grid_y_label_slab_is_calibrated_tool_material():
    base_material, text_material = (
        y_grid_calibration.create_absolute_y_alignment_materials(
            bed_grid_zero=SYNTHETIC_CALIBRATION_VALUES["bed_grid_zero"],
            calibration_value_mm=SYNTHETIC_CALIBRATION_VALUES["t0_y_endstop"],
        )
    )

    base_min, _ = grid_calibration.get_bounding_box(base_material)
    text_min, text_max = grid_calibration.get_bounding_box(text_material)

    assert base_min[0] < text_min[0]
    assert base_min[0] == pytest.approx(grid_calibration.SAFE_BED_ORIGIN[0])
    assert text_min[1] < base_min[1]
    assert base_min[1] - text_min[1] == pytest.approx(
        grid_calibration.CALIBRATION_LABEL_GROUNDING_MARKER_GAP_MM
        + grid_calibration.CALIBRATION_LABEL_GROUNDING_MARKER_SIZE_MM
    )
    assert text_min[2] == pytest.approx(0.0)
    assert text_max[2] == pytest.approx(
        grid_calibration.CALIBRATION_LABEL_PAD_THICKNESS_MM
        + grid_calibration.CALIBRATION_LABEL_TEXT_THICKNESS_MM
    )


def test_absolute_grid_x_label_slab_has_writing_anchor():
    base_material, text_material, _, _ = (
        x_grid_calibration.create_absolute_x_alignment_materials(
            SYNTHETIC_CALIBRATION_VALUES
        )
    )

    base_min, _ = grid_calibration.get_bounding_box(base_material)
    text_min, text_max = grid_calibration.get_bounding_box(text_material)

    assert text_min[1] < base_min[1]
    assert base_min[1] - text_min[1] == pytest.approx(
        grid_calibration.CALIBRATION_LABEL_GROUNDING_MARKER_GAP_MM
        + grid_calibration.CALIBRATION_LABEL_GROUNDING_MARKER_SIZE_MM
    )
    assert text_min[2] == pytest.approx(0.0)
    assert text_max[2] == pytest.approx(
        grid_calibration.CALIBRATION_LABEL_PAD_THICKNESS_MM
        + grid_calibration.CALIBRATION_LABEL_TEXT_THICKNESS_MM
    )


def test_absolute_grid_x_materials_use_same_y_row_for_both_tools(monkeypatch):
    calls = []

    def create_pattern_spy(**kwargs):
        calls.append(kwargs)
        return object(), object()

    monkeypatch.setattr(
        x_grid_calibration,
        "create_absolute_x_alignment_pattern",
        create_pattern_spy,
    )

    x_grid_calibration.create_absolute_x_alignment_materials(
        SYNTHETIC_CALIBRATION_VALUES
    )

    assert len(calls) == 2
    assert (
        calls[0]["line_y_min_mm"]
        == calls[1]["line_y_min_mm"]
        == pytest.approx(
            grid_calibration.grid_coordinate(
                SYNTHETIC_CALIBRATION_VALUES["bed_grid_zero"][1],
                -1,
            )
        )
    )
    assert (
        calls[0]["line_y_max_mm"]
        == calls[1]["line_y_max_mm"]
        == pytest.approx(
            grid_calibration.grid_coordinate(
                SYNTHETIC_CALIBRATION_VALUES["bed_grid_zero"][1],
                0,
            )
        )
    )
    assert calls[0]["label_panel"] is calls[1]["label_panel"]
    assert calls[0]["label_panel"]["name"] == "z_guide_panel_outline"


def test_absolute_grid_x_and_y_parts_fit_dual_area():
    x_parts = x_grid_calibration.create_absolute_x_alignment_materials(
        SYNTHETIC_CALIBRATION_VALUES
    )
    y_t0_parts = y_grid_calibration.create_absolute_y_alignment_materials(
        bed_grid_zero=SYNTHETIC_CALIBRATION_VALUES["bed_grid_zero"],
        calibration_value_mm=SYNTHETIC_CALIBRATION_VALUES["t0_y_endstop"],
    )
    y_t1_parts = y_grid_calibration.create_absolute_y_alignment_materials(
        bed_grid_zero=SYNTHETIC_CALIBRATION_VALUES["bed_grid_zero"],
        calibration_value_mm=SYNTHETIC_CALIBRATION_VALUES["t1_y_endstop"],
    )

    grid_calibration.assert_absolute_patterns_fit_dual_area(
        [*x_parts, *y_t0_parts, *y_t1_parts]
    )


def test_idex_tool_parking_uses_full_speed_travel():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    tool_state = _section(config_text, "gcode_macro _IDEX_TOOL_STATE")
    select_left = _section(config_text, "gcode_macro IDEX_SELECT_LEFT")
    select_right = _section(config_text, "gcode_macro IDEX_SELECT_RIGHT")

    assert "variable_park_move_speed: 180.0" in tool_state
    for select_macro in [select_left, select_right]:
        assert "park_move_speed|float * 60.0" in select_macro
        assert "F{park_feed}" in select_macro
        assert "F3000" not in select_macro


def test_idex_tool_parking_uses_absolute_edges():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    select_left = _section(config_text, "gcode_macro IDEX_SELECT_LEFT")
    select_right = _section(config_text, "gcode_macro IDEX_SELECT_RIGHT")

    for select_macro in [select_left, select_right]:
        assert "dual_carriage.position_max|float" in select_macro
        assert "x_positive_offset_clearance" not in select_macro
        assert "x_negative_offset_clearance" not in select_macro

    assert "stepper_x.position_min|float" in select_right


def test_idex_tool_offset_macro_clears_x_and_rejects_t0_runtime_updates():
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    apply_offset = _section(config_text, "gcode_macro _IDEX_APPLY_TOOL_OFFSET")
    set_offset = _section(config_text, "gcode_macro IDEX_SET_TOOL_OFFSET")

    assert "SET_GCODE_OFFSET X=0 Y={y} Z={z}" in apply_offset
    assert "t0_x_offset" not in apply_offset
    assert "t1_x_offset" not in apply_offset
    assert "state.t0_z_offset" not in apply_offset
    assert "{% set z = 0.0 %}" in apply_offset
    assert "state.t1_z_offset|float" in apply_offset
    assert "params.X is defined" in set_offset
    assert "position_endstop and position_max together" in set_offset
    assert "params.Z is defined and tool == 0" in set_offset
    assert "T0 Z is calibrated mechanically" in set_offset
    assert "VARIABLE=t{tool}_x_offset" not in set_offset
