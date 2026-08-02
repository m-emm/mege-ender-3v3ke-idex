#!/usr/bin/env python3
"""Consumer-focused access to persisted printer calibration and vision priors."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import yaml


def _default_path(env_name: str, deployed_name: str) -> Path:
    configured = os.environ.get(env_name)
    if configured:
        return Path(configured)
    deployed = Path("/usr/local/share/vision") / deployed_name
    if deployed.is_file():
        return deployed
    source = Path(__file__).resolve().parents[5] / "klipper_config" / deployed_name
    return source if source.is_file() else deployed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


class CalibDAO:
    def __init__(
        self,
        calib_path: Path | str | None = None,
        priors_path: Path | str | None = None,
    ) -> None:
        self.calib_path = (
            Path(calib_path)
            if calib_path
            else _default_path("VISION_CALIBRATION_CALIB_FILE", "calib.yaml")
        )
        self.priors_path = (
            Path(priors_path)
            if priors_path
            else _default_path("VISION_CALIBRATION_PRIORS_FILE", "priors.yaml")
        )

    @staticmethod
    def _load(path: Path, label: str) -> dict[str, Any]:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError(f"missing {label}: {path}") from None
        if not isinstance(value, dict):
            raise ValueError(f"{path} must contain a YAML mapping")
        return value

    @staticmethod
    def _vector(
        values: dict[str, Any], key: str, length: int, path: Path
    ) -> list[float]:
        value = values.get(key)
        if (
            not isinstance(value, list)
            or len(value) != length
            or any(not isinstance(item, (int, float)) for item in value)
        ):
            raise ValueError(f"{path} requires numeric {key}[{length}]")
        return [float(item) for item in value]

    def bed_corner(self) -> list[float]:
        priors = self._load(self.priors_path, "vision priors")
        return self._vector(priors, "bed_corner_xyz_mm", 3, self.priors_path)

    def fiducial_centers(self) -> list[list[float]]:
        priors = self._load(self.priors_path, "vision priors")
        x, y = self._vector(priors, "fiducial_origin_xy_mm", 2, self.priors_path)
        dx, dy = self._vector(priors, "fiducial_spacing_xy_mm", 2, self.priors_path)
        return [[x, y], [x + dx, y], [x, y + dy], [x + dx, y + dy]]

    def fiducial_z(self) -> float:
        priors = self._load(self.priors_path, "vision priors")
        value = priors.get("fiducial_z_mm")
        if not isinstance(value, (int, float)):
            raise ValueError(f"{self.priors_path} requires numeric fiducial_z_mm")
        return float(value)

    def fiducial_angles(self) -> tuple[float, float]:
        priors = self._load(self.priors_path, "vision priors")
        value = priors.get("fiducial_right_angle_deg")
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"{self.priors_path} requires numeric fiducial_right_angle_deg"
            )
        right = float(value)
        return right, right - 90.0

    def tool_datums(self) -> dict[str, dict[str, float]]:
        calib = self._load(self.calib_path, "synchronized calibration")
        tools = calib.get("tools")
        if not isinstance(tools, dict):
            raise ValueError(f"{self.calib_path} does not contain tools calibration")
        result: dict[str, dict[str, float]] = {}
        for tool in ("t0", "t1"):
            source = tools.get(tool)
            if not isinstance(source, dict):
                raise ValueError(f"{self.calib_path} lacks tools.{tool}")
            result[tool] = {}
            for axis in ("x", "y", "z"):
                key = f"{axis}_endstop"
                value = source.get(key)
                if not isinstance(value, (int, float)):
                    raise ValueError(
                        f"{self.calib_path} lacks numeric tools.{tool}.{key}"
                    )
                result[tool][key] = float(value)
        return result

    def calib_hash(self) -> str:
        return _sha256(self.calib_path)

    def priors_hash(self) -> str:
        return _sha256(self.priors_path)

    def write_candidate(
        self, path: Path | str, new_datums: dict[str, dict[str, float]]
    ) -> str:
        candidate = self._load(self.calib_path, "synchronized calibration")
        tools = candidate.get("tools")
        if not isinstance(tools, dict):
            raise ValueError(f"{self.calib_path} does not contain tools calibration")
        for tool in ("t0", "t1"):
            target = tools.get(tool)
            source = new_datums.get(tool)
            if not isinstance(target, dict) or not isinstance(source, dict):
                raise ValueError(f"candidate requires {tool} calibration")
            for axis in ("x", "y", "z"):
                value = source.get(axis)
                if not isinstance(value, (int, float)):
                    raise ValueError(f"candidate requires numeric {tool}.{axis}")
                target[f"{axis}_endstop"] = float(value)
        destination = Path(path)
        destination.write_text(
            yaml.safe_dump(candidate, sort_keys=False), encoding="utf-8"
        )
        return _sha256(destination)
