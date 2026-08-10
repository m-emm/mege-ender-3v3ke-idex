"""Tests for the mandatory post-endstop XY-prior refresh workflow."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FILES = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)


def _module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_post_endstop_xy_check_test",
        FILES / "vision_calibration.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _active():
    return {
        "active_fingerprint": "sha256:active",
        "tool_xy_endstops_mm": {
            "t0": {"x": -85.472, "y": -14.8},
            "t1": {"x": 346.104, "y": -13.284},
        },
    }


def _fact(tool: str, source: list[float]) -> dict:
    return {
        "acquisition_endstop_xy_mm": source,
        "nozzle_image_prior": {
            "model": "linear_commanded_x_to_image_uv_v1",
            "coefficients_px": [[-800.0, 500.0], [10.0, 0.0]],
        },
        "x_datum_mm": 160.0,
        "y_datum_mm": -14.0,
        "commanded_z_mm": 0.5,
        "tool": tool,
    }


def test_post_endstop_fact_rejects_stale_source_and_accepts_matching_source():
    module = _module()
    active = _active()
    good = _fact("T1", [346.104, -13.284])

    prior = module._validate_post_endstop_xy_fact(
        good,
        tool="T1",
        active_calibration=active,
    )
    assert prior == good["nozzle_image_prior"]

    stale = _fact("T1", [341.145, -13.537])
    with pytest.raises(module.ToolXZSweepError, match="is stale"):
        module._validate_post_endstop_xy_fact(
            stale,
            tool="T1",
            active_calibration=active,
        )


def test_post_endstop_xy_check_runs_both_jobs_and_returns_fresh_priors(monkeypatch):
    module = _module()
    active = _active()
    calls = []
    facts = {
        "t0": _fact("T0", [-85.472, -14.8]),
        "t1": _fact("T1", [346.104, -13.284]),
    }

    monkeypatch.setattr(module, "query_printer_status", lambda: {})
    monkeypatch.setattr(module, "_active_tool_xy_calibration", lambda _status: active)

    def fake_run_job(name, *, job_type, expected_fingerprint, timeout):
        calls.append((name, job_type, expected_fingerprint, timeout))
        tool = "T0" if job_type.endswith("t0") else "T1"
        return {
            "job_id": f"job-{tool.lower()}",
            "analysis": {
                "state": "accepted",
                "analysis_run_id": f"analysis-{tool.lower()}",
                "publication": {"publication_id": f"pub-{tool.lower()}"},
                "review_url": f"/vision/{tool.lower()}",
                "details": {"reasons": []},
            },
        }

    def fake_resolve(requirement, fact_name, definition_version):
        tool = "t0" if requirement == "t0_xy_datum" else "t1"
        return (
            {
                "requirement": requirement,
                "fact_name": fact_name,
                "fact_definition_version": definition_version,
                "fact_set_hash": f"sha256:{tool}",
                "fact_set_path": f"jobs/{tool}/fact_set.json",
            },
            {"value": facts[tool]},
        )

    monkeypatch.setattr(module, "run_job", fake_run_job)
    monkeypatch.setattr(module, "_resolve_current_fact", fake_resolve)

    result = module.post_endstop_xy_check("refresh", timeout=12.0)

    assert result["accepted"] is True
    assert [call[1] for call in calls] == [
        "idex_tool_xy_measure_t0",
        "idex_tool_xy_measure_t1",
    ]
    assert all(call[2] == "sha256:active" for call in calls)
    assert all(call[3] == 12.0 for call in calls)
    assert result["tools"]["T1"]["nozzle_image_prior"]["coefficients_px"] == [
        [-800.0, 500.0],
        [10.0, 0.0],
    ]
