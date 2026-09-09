import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTRA_PATH = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
    / "klipper_host"
    / "klippy"
    / "extras"
    / "probe_eddy_current.py"
)


def _load_module():
    sys.modules.setdefault("mcu", types.ModuleType("mcu"))
    sys.modules.setdefault("mathutil", types.ModuleType("mathutil"))
    sys.modules.setdefault("klippy", types.ModuleType("klippy"))
    extras = sys.modules.setdefault("klippy.extras", types.ModuleType("extras"))
    for name in ("ldc1612", "trigger_analog", "probe", "manual_probe"):
        module_name = "klippy.extras.%s" % name
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
        setattr(extras, name, module)
    spec = importlib.util.spec_from_file_location(
        "klippy.extras.probe_eddy_current_release_test", EXTRA_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class IdentityCalibration:
    def freq_to_height(self, frequency):
        return frequency


def _tap(module):
    tap = module.EddyTap.__new__(module.EddyTap)
    tap._calibration = IdentityCalibration()
    return tap


def _data(release_z, free_slope=1.0):
    samples = []
    for index in range(101):
        z = index * 0.01
        if z <= release_z:
            height = 0.15 + 0.08 * z
        else:
            height = 0.15 + 0.08 * release_z + free_slope * (z - release_z)
        height += (index % 5 - 2) * 0.0004
        samples.append((height, (0.0, 0.0, z)))
    return samples


def test_release_fit_selects_height_space_intersection_for_obvious_elbow():
    module = _load_module()
    fit, diagnostics = _tap(module)._find_release_fit(_data(0.12), 0.03, 0.25)

    assert fit is not None
    assert abs(fit["z_contact"] - 0.12) < 0.01
    assert abs(fit["free_height_slope"] - 1.0) < 0.03
    assert fit["height_slope_delta"] > 0.8
    assert diagnostics["valid_candidate_count"] > 0


def test_release_fit_rejects_a_retract_without_a_free_height_leg():
    module = _load_module()
    fit, diagnostics = _tap(module)._find_release_fit(
        _data(0.12, free_slope=0.12), 0.03, 0.25
    )

    assert fit is None
    assert diagnostics["rejections"]["free_slope"] > 0
