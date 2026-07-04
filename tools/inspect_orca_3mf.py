#!/usr/bin/env python3
"""Inspect OrcaSlicer filament metadata inside a 3MF project."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def _load_json(project_zip: zipfile.ZipFile, name: str):
    if name not in project_zip.namelist():
        return None
    return json.loads(project_zip.read(name).decode("utf-8"))


def _load_xml(project_zip: zipfile.ZipFile, name: str):
    if name not in project_zip.namelist():
        return None
    return ET.fromstring(project_zip.read(name))


def _project_field(project_settings: dict | None, key: str):
    if not project_settings:
        return None
    return project_settings.get(key)


def inspect_orca_3mf(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as project_zip:
        project_settings = _load_json(project_zip, "Metadata/project_settings.config")
        plate_json = next(
            (
                _load_json(project_zip, name)
                for name in project_zip.namelist()
                if name.startswith("Metadata/plate_") and name.endswith(".json")
            ),
            None,
        )
        slice_info = _load_xml(project_zip, "Metadata/slice_info.config")
        model_settings = _load_xml(project_zip, "Metadata/model_settings.config")

    slice_filaments = []
    if slice_info is not None:
        for element in slice_info.findall(".//filament"):
            slice_filaments.append(
                {
                    "id": element.get("id"),
                    "tray_info_idx": element.get("tray_info_idx"),
                    "type": element.get("type"),
                    "color": element.get("color"),
                }
            )

    object_extruders = []
    if model_settings is not None:
        for element in model_settings.findall(".//metadata"):
            if element.get("key") == "extruder":
                object_extruders.append(element.get("value"))

    return {
        "path": str(path),
        "project": {
            "filament_settings_id": _project_field(
                project_settings,
                "filament_settings_id",
            ),
            "default_filament_profile": _project_field(
                project_settings,
                "default_filament_profile",
            ),
            "filament_ids": _project_field(project_settings, "filament_ids"),
            "filament_type": _project_field(project_settings, "filament_type"),
            "filament_colour": _project_field(project_settings, "filament_colour"),
            "default_filament_colour": _project_field(
                project_settings,
                "default_filament_colour",
            ),
            "nozzle_temperature": _project_field(
                project_settings,
                "nozzle_temperature",
            ),
            "nozzle_temperature_initial_layer": _project_field(
                project_settings,
                "nozzle_temperature_initial_layer",
            ),
            "hot_plate_temp": _project_field(project_settings, "hot_plate_temp"),
        },
        "plate": {
            "filament_colors": (plate_json or {}).get("filament_colors"),
            "filament_ids": (plate_json or {}).get("filament_ids"),
            "first_extruder": (plate_json or {}).get("first_extruder"),
        },
        "slice_filaments": slice_filaments,
        "object_extruders": object_extruders,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect_orca_3mf(args.path), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
