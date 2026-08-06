import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT
    / "klipper_setup"
    / "klipper_config"
    / "fetch_apply_vision_tool_z_offset_candidate.sh"
)
FACT_NAME = "camera.nozzle_cam.nozzle_tip.xz_sweep_report"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def test_z_offset_candidate_reduces_top_endstop_to_raise_t1(tmp_path):
    source_t0 = 293.5
    source_t1 = 292.95
    fitted_delta = -0.6
    remote_fact_path = "jobs/xz-report/analysis/shared-fit/fact_set.json"
    fact_set = {
        "facts": [
            {
                "name": FACT_NAME,
                "role": "diagnostic",
                "definition_version": 1,
                "value": {
                    "shared_z_curve_fit": {
                        "available": True,
                        "t1_z_delta_mm": fitted_delta,
                        "rms_slope_px_per_mm": 0.01,
                        "included_rows": [{"tool": "T0"}, {"tool": "T1"}],
                        "excluded_rows": [],
                    },
                    "acquisition_calibration": {
                        "tool_z_endstops_mm": {
                            "t0": source_t0,
                            "t1": source_t1,
                        }
                    },
                },
            }
        ]
    }
    fact_hash = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                fact_set,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    )
    fact_set["fact_set_hash"] = fact_hash
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "heads": {
                    FACT_NAME: {
                        "fact_set_hash": fact_hash,
                        "fact_set_path": remote_fact_path,
                    }
                },
                "stale_fact_sets": {},
            }
        ),
        encoding="utf-8",
    )
    fact_set_path = tmp_path / "fact_set.json"
    fact_set_path.write_text(json.dumps(fact_set), encoding="utf-8")
    calib_path = tmp_path / "calib.yaml"
    calib_path.write_text(
        yaml.safe_dump(
            {
                "tools": {
                    "t0": {"z_endstop": source_t0},
                    "t1": {"z_endstop": source_t1},
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "ssh", '#!/bin/sh\ncat "${FAKE_CATALOG}"\n')
    _write_executable(
        fake_bin / "scp",
        '#!/bin/bash\ncp "${FAKE_FACT_SET}" "${!#}"\n',
    )
    generator_marker = tmp_path / "generator-ran"
    generator_path = tmp_path / "generator.py"
    generator_path.write_text(
        "import os\nfrom pathlib import Path\n"
        "Path(os.environ['FAKE_GENERATOR_MARKER']).touch()\n",
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
            "MENDERPI_HOST": "fake-printer",
            "VISION_CALIB_PATH": str(calib_path),
            "VISION_PRINTER_CFG_GENERATOR": str(generator_path),
            "FAKE_CATALOG": str(catalog_path),
            "FAKE_FACT_SET": str(fact_set_path),
            "FAKE_GENERATOR_MARKER": str(generator_marker),
        }
    )
    result = subprocess.run(
        [str(SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    updated = yaml.safe_load(calib_path.read_text(encoding="utf-8"))
    assert updated["tools"]["t0"]["z_endstop"] == pytest.approx(source_t0)
    assert updated["tools"]["t1"]["z_endstop"] == pytest.approx(
        source_t1 + fitted_delta
    )
    assert updated["tools"]["t1"]["z_endstop"] < source_t1
    assert "expected T1 nozzle direction: higher" in result.stdout
    assert generator_marker.is_file()
    assert os.access(SCRIPT, os.X_OK)
