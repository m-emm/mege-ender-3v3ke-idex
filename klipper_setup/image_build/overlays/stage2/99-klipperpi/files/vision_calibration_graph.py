#!/usr/bin/env python3
"""Immutable fact publication and dependency catalog for vision calibration."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
FACT_CATALOG_SCHEMA = "vision-calibration-fact-catalog"
PUBLICATION_SCHEMA = "vision-calibration-publication"
FACT_SET_SCHEMA = "vision-calibration-fact-set"
ANALYSIS_SCHEMA = "vision-calibration-analysis"
MANIFEST_SCHEMA = "vision-calibration-acquisition-manifest"
REGISTRY_SCHEMA = "vision-calibration-job-registry"
FACT_ROLES = {"coordinate_system", "diagnostic"}
ROLE_AWARE_FACT_DEFINITION_VERSIONS = {4, 5}
PRIOR_FACT_NAMES = {
    "bed.tab_corner.printer_xyz",
    "bed.reference_plane.tab_to_print_plane_z_mm",
}


class CalibrationGraphError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def content_hash(value: dict[str, Any], hash_field: str) -> str:
    payload = dict(value)
    payload.pop(hash_field, None)
    return canonical_hash(payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def atomic_write_json(path: Path, payload: Any, *, immutable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        raise CalibrationGraphError(f"immutable record already exists: {path}")
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_bytes(canonical_json_bytes(payload) + b"\n")
    if immutable and path.exists():
        tmp.unlink(missing_ok=True)
        raise CalibrationGraphError(f"immutable record already exists: {path}")
    tmp.replace(path)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CalibrationGraphError(f"missing record: {path}") from None
    except json.JSONDecodeError as exc:
        raise CalibrationGraphError(f"invalid JSON in {path}: {exc}") from None


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CalibrationGraphError(f"{name} must be an object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise CalibrationGraphError(f"{name} must be an array")
    return value


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationGraphError(f"{name} must be a non-empty string")
    return value


def _validate_header(record: dict[str, Any], kind: str, name: str) -> None:
    if record.get("schema") != kind:
        raise CalibrationGraphError(
            f"{name}.schema must be {kind!r}, got {record.get('schema')!r}"
        )
    if record.get("schema_version") != SCHEMA_VERSION:
        raise CalibrationGraphError(
            f"{name}.schema_version must be {SCHEMA_VERSION}, "
            f"got {record.get('schema_version')!r}"
        )


def validate_registry(record: Any) -> dict[str, Any]:
    record = _require_mapping(record, "registry")
    _validate_header(record, REGISTRY_SCHEMA, "registry")
    job_types = _require_mapping(record.get("job_types"), "registry.job_types")
    if set(job_types) != {
        "nozzle_cam_bed_tab_y_scale",
        "nozzle_cam_bed_tab_corner",
        "idex_tool_red_marker_x_sweep",
        "idex_rough_tool_x_verify",
    }:
        raise CalibrationGraphError("registry has an invalid native job-type set")
    definition = _require_mapping(
        job_types["nozzle_cam_bed_tab_y_scale"],
        "registry.job_types.nozzle_cam_bed_tab_y_scale",
    )
    if definition.get("definition_version") != 5:
        raise CalibrationGraphError("bed-tab Y definition_version must be 5")
    if definition.get("fact_definition_version") != 5:
        raise CalibrationGraphError("bed-tab Y fact definition_version must be 5")
    if definition.get("publish_on_accept") is not True:
        raise CalibrationGraphError(
            "bed-tab Y job must publish accepted facts immediately"
        )
    if definition.get("fact_names") != ["camera.nozzle_cam.bed_tab.y_parallax_model"]:
        raise CalibrationGraphError("job registry has an invalid fact contract")
    if definition.get("localizer") != {
        "kind": "bed_tab_top_edge",
        "version": 1,
    }:
        raise CalibrationGraphError(
            "bed-tab Y job must use bed_tab_top_edge localizer version 1"
        )
    corner = _require_mapping(
        job_types["nozzle_cam_bed_tab_corner"],
        "registry.job_types.nozzle_cam_bed_tab_corner",
    )
    if corner.get("definition_version") != 5:
        raise CalibrationGraphError("bed-tab corner definition_version must be 5")
    if corner.get("fact_definition_version") != 5:
        raise CalibrationGraphError("bed-tab corner fact definition_version must be 5")
    if corner.get("publish_on_accept") is not True:
        raise CalibrationGraphError(
            "bed-tab corner job must publish accepted facts immediately"
        )
    if corner.get("fact_names") != ["camera.nozzle_cam.partial_bed_coordinate_system"]:
        raise CalibrationGraphError("bed-tab corner has an invalid fact contract")
    if corner.get("requires") != [
        {
            "requirement": "bed_y_model",
            "fact_name": "camera.nozzle_cam.bed_tab.y_parallax_model",
            "fact_definition_version": 5,
        },
        {
            "requirement": "bed_tab_corner_prior",
            "fact_name": "bed.tab_corner.printer_xyz",
            "fact_definition_version": 4,
        },
        {
            "requirement": "tab_plane_z",
            "fact_name": "bed.reference_plane.tab_to_print_plane_z_mm",
            "fact_definition_version": 4,
        },
    ]:
        raise CalibrationGraphError("bed-tab corner has invalid fact requirements")
    if corner.get("localizer") != {
        "kind": "bed_tab_corner",
        "version": 1,
    }:
        raise CalibrationGraphError(
            "bed-tab corner job must use bed_tab_corner localizer version 1"
        )
    if corner.get("duplicate_count") != 5:
        raise CalibrationGraphError("bed-tab corner job must acquire five duplicates")
    if corner.get("discard_fresh_frames") != 1:
        raise CalibrationGraphError(
            "bed-tab corner job must discard one fresh frame per duplicate"
        )
    red_marker = _require_mapping(
        job_types["idex_tool_red_marker_x_sweep"],
        "registry.job_types.idex_tool_red_marker_x_sweep",
    )
    if red_marker.get("definition_version") != 5:
        raise CalibrationGraphError("red-marker sweep definition_version must be 5")
    if red_marker.get("fact_definition_version") != 5:
        raise CalibrationGraphError("red-marker fact definition_version must be 5")
    if red_marker.get("publish_on_accept") is not True:
        raise CalibrationGraphError(
            "red-marker sweep must publish accepted facts immediately"
        )
    if red_marker.get("localizer") != {
        "kind": "red_marker_trajectory",
        "version": 1,
    }:
        raise CalibrationGraphError(
            "red-marker sweep must use red_marker_trajectory localizer version 1"
        )
    if red_marker.get("x_positions_mm") != [160, 170, 180, 190, 200, 210]:
        raise CalibrationGraphError("red-marker sweep has an invalid X motion order")
    if red_marker.get("discard_fresh_frames") != 1:
        raise CalibrationGraphError("red-marker sweep must discard one fresh frame")
    if red_marker.get("requires") != [
        {
            "requirement": "partial_bed_coordinate_system",
            "fact_name": "camera.nozzle_cam.partial_bed_coordinate_system",
            "fact_definition_version": 5,
        },
        {
            "requirement": "bed_y_model",
            "fact_name": "camera.nozzle_cam.bed_tab.y_parallax_model",
            "fact_definition_version": 5,
        },
    ]:
        raise CalibrationGraphError("red-marker sweep has invalid fact requirements")
    if red_marker.get("fact_names") != [
        "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2",
        "tool.t0.red_marker_to_bed_tab_x_mm",
        "tool.t1.red_marker_to_bed_tab_x_mm",
    ]:
        raise CalibrationGraphError("red-marker sweep has an invalid fact contract")
    verification = _require_mapping(
        job_types["idex_rough_tool_x_verify"],
        "registry.job_types.idex_rough_tool_x_verify",
    )
    if verification.get("definition_version") != 5:
        raise CalibrationGraphError(
            "rough-X verification definition_version must be 5"
        )
    if verification.get("fact_definition_version") != 5:
        raise CalibrationGraphError(
            "rough-X verification fact definition_version must be 5"
        )
    if verification.get("publish_on_accept") is not True:
        raise CalibrationGraphError(
            "rough-X verification must publish accepted facts immediately"
        )
    if verification.get("localizer") != {
        "kind": "rough_x_marker_verification",
        "version": 1,
    }:
        raise CalibrationGraphError(
            "rough-X verification has an invalid localizer"
        )
    if verification.get("verification_offset_x_mm") != 10:
        raise CalibrationGraphError(
            "rough-X verification must use the declared +10 mm offset"
        )
    if verification.get("requires") != [
        {
            "requirement": "partial_bed_coordinate_system",
            "fact_name": "camera.nozzle_cam.partial_bed_coordinate_system",
            "fact_definition_version": 5,
        },
        {
            "requirement": "image_x_axis",
            "fact_name": "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2",
            "fact_definition_version": 5,
        },
        {
            "requirement": "rough_x_active_snapshot",
            "fact_name": "calibration.rough_tool_x.active_snapshot",
            "fact_definition_version": 5,
        },
    ]:
        raise CalibrationGraphError(
            "rough-X verification has invalid fact requirements"
        )
    if verification.get("fact_names") != [
        "calibration.rough_tool_x.verified"
    ]:
        raise CalibrationGraphError(
            "rough-X verification has an invalid fact contract"
        )
    return record


def validate_manifest(record: Any) -> dict[str, Any]:
    record = _require_mapping(record, "manifest")
    _validate_header(record, MANIFEST_SCHEMA, "manifest")
    _require_string(record.get("job_id"), "manifest.job_id")
    job_type = record.get("job_type")
    if job_type not in (
        "nozzle_cam_bed_tab_y_scale",
        "nozzle_cam_bed_tab_corner",
        "idex_tool_red_marker_x_sweep",
        "idex_rough_tool_x_verify",
    ):
        raise CalibrationGraphError("manifest has an unsupported job_type")
    definition_version = record.get("definition_version")
    if record.get("camera") != "nozzle_cam":
        raise CalibrationGraphError("manifest.camera must be nozzle_cam")
    frames = _require_list(record.get("frames"), "manifest.frames")
    if job_type == "nozzle_cam_bed_tab_y_scale":
        if definition_version != 5:
            raise CalibrationGraphError(
                "bed-tab Y manifest definition_version must be 5"
            )
        if record.get("publish_on_accept") is not True:
            raise CalibrationGraphError(
                "bed-tab Y manifest must publish on acceptance"
            )
        if record.get("localizer") != {
            "kind": "bed_tab_top_edge",
            "version": 1,
        }:
            raise CalibrationGraphError(
                "bed-tab Y manifest has an invalid edge localizer"
            )
        expected_offsets = [0, 10, 20, 20, 10, 0]
        if len(frames) != len(expected_offsets) or record.get("frame_count") != len(
            expected_offsets
        ):
            raise CalibrationGraphError(
                "bed-tab Y manifest has the wrong frame count for its definition"
            )
        if [frame.get("y_offset_mm") for frame in frames] != expected_offsets:
            raise CalibrationGraphError("manifest has an invalid Y motion order")
    elif job_type == "nozzle_cam_bed_tab_corner":
        if definition_version != 5:
            raise CalibrationGraphError(
                "bed-tab corner manifest definition_version must be 5"
            )
        if record.get("publish_on_accept") is not True:
            raise CalibrationGraphError(
                "bed-tab corner manifest must publish on acceptance"
            )
        if record.get("localizer") != {
            "kind": "bed_tab_corner",
            "version": 1,
        }:
            raise CalibrationGraphError(
                "bed-tab corner manifest has an invalid localizer"
            )
        if len(frames) != 5 or record.get("frame_count") != 5:
            raise CalibrationGraphError(
                "bed-tab corner manifest must contain five duplicates"
            )
        if [frame.get("duplicate_index") for frame in frames] != list(range(5)):
            raise CalibrationGraphError("bed-tab corner duplicate order is invalid")
        if any(
            frame.get("discard_fresh_frames") != 1 for frame in frames
        ):
            raise CalibrationGraphError(
                "current bed-tab corner frames must discard one fresh frame"
            )
        positions = [frame.get("commanded_position_mm") for frame in frames]
        if not positions or any(position != positions[0] for position in positions):
            raise CalibrationGraphError(
                "bed-tab corner duplicates must use one fixed pose"
            )
        expected_requirements = {
            "bed_y_model": "camera.nozzle_cam.bed_tab.y_parallax_model",
            "bed_tab_corner_prior": "bed.tab_corner.printer_xyz",
            "tab_plane_z": "bed.reference_plane.tab_to_print_plane_z_mm",
        }
        input_facts = _require_list(record.get("input_facts"), "manifest.input_facts")
        normalized_input_facts = [
            _require_mapping(item, f"manifest.input_facts[{index}]")
            for index, item in enumerate(input_facts)
        ]
        if {
            item.get("requirement"): item.get("fact_name")
            for item in normalized_input_facts
        } != expected_requirements:
            raise CalibrationGraphError(
                "bed-tab corner manifest has invalid input fact bindings"
            )
        for binding in normalized_input_facts:
            _require_string(binding.get("fact_set_hash"), "input fact_set_hash")
        if {
            item["requirement"]: item.get("fact_definition_version")
            for item in normalized_input_facts
        } != {
            "bed_y_model": 5,
            "bed_tab_corner_prior": 4,
            "tab_plane_z": 4,
        }:
            raise CalibrationGraphError(
                "bed-tab corner has invalid input fact versions"
            )
    elif job_type == "idex_tool_red_marker_x_sweep":
        if definition_version != 5:
            raise CalibrationGraphError(
                "red-marker manifest definition_version must be 5"
            )
        if record.get("publish_on_accept") is not True:
            raise CalibrationGraphError(
                "red-marker manifest must publish on acceptance"
            )
        if record.get("localizer") != {
            "kind": "red_marker_trajectory",
            "version": 1,
        }:
            raise CalibrationGraphError(
                "red-marker manifest has an invalid localizer"
            )
        expected = [
            (tool, x)
            for tool in ("T0", "T1")
            for x in (160, 170, 180, 190, 200, 210)
        ]
        if len(frames) != 12 or record.get("frame_count") != 12:
            raise CalibrationGraphError(
                "red-marker manifest must contain twelve frames"
            )
        if [(frame.get("tool"), frame.get("x_mm")) for frame in frames] != expected:
            raise CalibrationGraphError(
                "red-marker manifest has an invalid tool/X motion order"
            )
        if any(frame.get("discard_fresh_frames") != 1 for frame in frames):
            raise CalibrationGraphError(
                "red-marker frames must discard one fresh framebuffer frame"
            )
        expected_requirements = {
            "partial_bed_coordinate_system":
                "camera.nozzle_cam.partial_bed_coordinate_system",
            "bed_y_model": "camera.nozzle_cam.bed_tab.y_parallax_model",
        }
        input_facts = _require_list(record.get("input_facts"), "manifest.input_facts")
        normalized_input_facts = [
            _require_mapping(item, f"manifest.input_facts[{index}]")
            for index, item in enumerate(input_facts)
        ]
        if {
            item.get("requirement"): item.get("fact_name")
            for item in normalized_input_facts
        } != expected_requirements:
            raise CalibrationGraphError(
                "red-marker manifest has invalid input fact bindings"
            )
        for binding in normalized_input_facts:
            _require_string(binding.get("fact_set_hash"), "input fact_set_hash")
        if {
            item["requirement"]: item.get("fact_definition_version")
            for item in normalized_input_facts
        } != {
            "partial_bed_coordinate_system": 5,
            "bed_y_model": 5,
        }:
            raise CalibrationGraphError(
                "red-marker manifest has invalid input fact versions"
            )
        snapshot = _require_mapping(
            record.get("active_calibration_snapshot"),
            "manifest.active_calibration_snapshot",
        )
        for key in ("t0_x_endstop_mm", "t1_x_endstop_mm"):
            if not isinstance(snapshot.get(key), (int, float)):
                raise CalibrationGraphError(
                    f"red-marker active calibration snapshot lacks {key}"
                )
    else:
        if definition_version != 5:
            raise CalibrationGraphError(
                "rough-X verification manifest definition_version must be 5"
            )
        if record.get("publish_on_accept") is not True:
            raise CalibrationGraphError(
                "rough-X verification manifest must publish on acceptance"
            )
        if record.get("localizer") != {
            "kind": "rough_x_marker_verification",
            "version": 1,
        }:
            raise CalibrationGraphError(
                "rough-X verification manifest has an invalid localizer"
            )
        if len(frames) != 2 or record.get("frame_count") != 2:
            raise CalibrationGraphError(
                "rough-X verification manifest must contain two frames"
            )
        expected_x = record.get("verification_reference", {}).get(
            "command_x_mm"
        )
        if not isinstance(expected_x, (int, float)):
            raise CalibrationGraphError(
                "rough-X verification command X is unavailable"
            )
        if [(frame.get("tool"), frame.get("x_mm")) for frame in frames] != [
            ("T0", expected_x),
            ("T1", expected_x),
        ]:
            raise CalibrationGraphError(
                "rough-X verification has an invalid tool/X motion order"
            )
        if any(frame.get("discard_fresh_frames") != 1 for frame in frames):
            raise CalibrationGraphError(
                "rough-X verification frames must discard one fresh frame"
            )
        expected_requirements = {
            "partial_bed_coordinate_system":
                "camera.nozzle_cam.partial_bed_coordinate_system",
            "image_x_axis":
                "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2",
            "rough_x_active_snapshot":
                "calibration.rough_tool_x.active_snapshot",
        }
        input_facts = _require_list(
            record.get("input_facts"), "manifest.input_facts"
        )
        normalized_input_facts = [
            _require_mapping(item, f"manifest.input_facts[{index}]")
            for index, item in enumerate(input_facts)
        ]
        if {
            item.get("requirement"): item.get("fact_name")
            for item in normalized_input_facts
        } != expected_requirements:
            raise CalibrationGraphError(
                "rough-X verification manifest has invalid input fact bindings"
            )
        for binding in normalized_input_facts:
            _require_string(binding.get("fact_set_hash"), "input fact_set_hash")
        if {
            item["requirement"]: item.get("fact_definition_version")
            for item in normalized_input_facts
        } != {
            "partial_bed_coordinate_system": 5,
            "image_x_axis": 5,
            "rough_x_active_snapshot": 5,
        }:
            raise CalibrationGraphError(
                "rough-X verification has invalid input fact versions"
            )
    for seq, frame_value in enumerate(frames):
        frame = _require_mapping(frame_value, f"manifest.frames[{seq}]")
        if frame.get("seq") != seq:
            raise CalibrationGraphError(f"manifest frame {seq} has the wrong seq")
        _require_string(frame.get("frame"), f"manifest.frames[{seq}].frame")
    expected_hash = content_hash(record, "manifest_hash")
    if record.get("manifest_hash") != expected_hash:
        raise CalibrationGraphError(
            f"manifest hash mismatch: {record.get('manifest_hash')} != {expected_hash}"
        )
    return record


def validate_analysis(record: Any) -> dict[str, Any]:
    record = _require_mapping(record, "analysis")
    _validate_header(record, ANALYSIS_SCHEMA, "analysis")
    _require_string(record.get("analysis_run_id"), "analysis.analysis_run_id")
    _require_string(record.get("job_id"), "analysis.job_id")
    if record.get("state") not in ("accepted", "rejected"):
        raise CalibrationGraphError("analysis.state must be accepted or rejected")
    if record.get("state") == "rejected" and record.get("fact_set_path") is not None:
        raise CalibrationGraphError("rejected analysis cannot publish facts")
    expected_hash = content_hash(record, "analysis_hash")
    if record.get("analysis_hash") != expected_hash:
        raise CalibrationGraphError("analysis hash mismatch")
    return record


def validate_fact_set(record: Any) -> dict[str, Any]:
    record = _require_mapping(record, "fact_set")
    _validate_header(record, FACT_SET_SCHEMA, "fact_set")
    if (
        record.get("accepted") is not True
        or record.get("publication_eligible") is not True
    ):
        raise CalibrationGraphError(
            "fact set must be accepted and publication eligible"
        )
    facts = _require_list(record.get("facts"), "fact_set.facts")
    if not facts:
        raise CalibrationGraphError("fact set must contain at least one fact")
    for forbidden in ("uncertainty", "uncertainties", "covariance"):
        if forbidden in canonical_json_bytes(record).decode("utf-8"):
            raise CalibrationGraphError(f"fact sets must not contain {forbidden}")
    names: set[str] = set()
    for fact_index, fact_value in enumerate(facts):
        fact = _require_mapping(fact_value, f"fact_set.facts[{fact_index}]")
        fact_name = _require_string(
            fact.get("name"), f"fact_set.facts[{fact_index}].name"
        )
        if fact_name in names:
            raise CalibrationGraphError(f"duplicate fact name {fact_name}")
        names.add(fact_name)
        value = _require_mapping(
            fact.get("value"), f"fact_set.facts[{fact_index}].value"
        )
        fact_definition_version = fact.get("definition_version")
        if fact_definition_version not in ROLE_AWARE_FACT_DEFINITION_VERSIONS:
            raise CalibrationGraphError(
                "fact definition_version must be 4 for retained priors or 5 "
                "for the current calibration chain"
            )
        if (
            fact_definition_version == 4
            and fact_name not in PRIOR_FACT_NAMES
        ):
            raise CalibrationGraphError(
                "definition-v4 facts are reserved for retained calibration priors"
            )
        declared_roles: dict[str, str] = {}
        if fact_definition_version in ROLE_AWARE_FACT_DEFINITION_VERSIONS:
            fact_role = _require_string(
                fact.get("role"), f"fact_set.facts[{fact_index}].role"
            )
            if fact_role not in FACT_ROLES:
                raise CalibrationGraphError(
                    f"fact role must be one of {sorted(FACT_ROLES)}"
                )
            value_items = _require_list(
                fact.get("value_items"),
                f"fact_set.facts[{fact_index}].value_items",
            )
            for item_index, item_value in enumerate(value_items):
                item = _require_mapping(
                    item_value,
                    f"fact_set.facts[{fact_index}].value_items[{item_index}]",
                )
                field = _require_string(
                    item.get("field"), f"fact.value_items[{item_index}].field"
                )
                role = _require_string(
                    item.get("role"), f"fact.value_items[{item_index}].role"
                )
                if role not in FACT_ROLES:
                    raise CalibrationGraphError(
                        f"fact item role must be one of {sorted(FACT_ROLES)}"
                    )
                if field in declared_roles:
                    raise CalibrationGraphError(
                        f"duplicate fact item declaration for {field}"
                    )
                declared_roles[field] = role
            if set(declared_roles) != set(value):
                missing = sorted(set(value) - set(declared_roles))
                extra = sorted(set(declared_roles) - set(value))
                raise CalibrationGraphError(
                    "fact item declarations must exactly cover value fields; "
                    f"missing={missing}, extra={extra}"
                )
            if fact_role == "coordinate_system" and not any(
                role == "coordinate_system" for role in declared_roles.values()
            ):
                raise CalibrationGraphError(
                    "coordinate-system fact must declare a coordinate-system item"
                )
            if fact_role == "diagnostic" and any(
                role == "coordinate_system" for role in declared_roles.values()
            ):
                raise CalibrationGraphError(
                    "diagnostic fact cannot declare coordinate-system items"
                )
        if fact_name == "camera.nozzle_cam.bed_tab.y_parallax_model":
            vector = _require_list(
                value.get("axis_vector_px_per_mm"),
                "bed-tab fact axis_vector_px_per_mm",
            )
            if len(vector) != 2 or not all(
                isinstance(item, (int, float)) for item in vector
            ):
                raise CalibrationGraphError(
                    "axis vector must contain two numeric values"
                )
            if (
                fact_definition_version in ROLE_AWARE_FACT_DEFINITION_VERSIONS
                and declared_roles.get("axis_vector_px_per_mm") != "coordinate_system"
            ):
                raise CalibrationGraphError(
                    "bed-tab axis vector must be a coordinate-system item"
                )
        if fact_name == "camera.nozzle_cam.partial_bed_coordinate_system":
            expected_lengths = {
                "corner_pixel_xy_px": 2,
                "corner_printer_xyz_mm": 3,
                "image_y_axis_vector_px_per_mm": 2,
            }
            for field, length in expected_lengths.items():
                item = _require_list(value.get(field), f"partial bed {field}")
                if len(item) != length or not all(
                    isinstance(component, (int, float)) for component in item
                ):
                    raise CalibrationGraphError(
                        f"partial bed {field} must contain {length} numeric values"
                    )
                if (
                    fact_definition_version in ROLE_AWARE_FACT_DEFINITION_VERSIONS
                    and declared_roles.get(field) != "coordinate_system"
                ):
                    raise CalibrationGraphError(
                        f"partial bed {field} must be a coordinate-system item"
                    )
            if not isinstance(value.get("tab_to_print_plane_z_mm"), (int, float)):
                raise CalibrationGraphError(
                    "partial bed tab_to_print_plane_z_mm must be numeric"
                )
            if fact_definition_version == 5:
                if not isinstance(
                    value.get("corner_pixel_capture_y_mm"), (int, float)
                ):
                    raise CalibrationGraphError(
                        "partial bed corner_pixel_capture_y_mm must be numeric"
                    )
                if (
                    declared_roles.get("corner_pixel_capture_y_mm")
                    != "coordinate_system"
                ):
                    raise CalibrationGraphError(
                        "partial bed corner_pixel_capture_y_mm must be a "
                        "coordinate-system item"
                    )
        if fact_name == (
            "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2"
        ):
            vector = _require_list(
                value.get("axis_vector_px_per_mm"),
                "red-marker image X axis_vector_px_per_mm",
            )
            if len(vector) != 2 or not all(
                isinstance(component, (int, float)) for component in vector
            ):
                raise CalibrationGraphError(
                    "red-marker image X vector must contain two numeric values"
                )
            if (
                fact_definition_version in ROLE_AWARE_FACT_DEFINITION_VERSIONS
                and declared_roles.get("axis_vector_px_per_mm")
                != "coordinate_system"
            ):
                raise CalibrationGraphError(
                    "red-marker image X vector must be a coordinate-system item"
                )
        if fact_name in (
            "tool.t0.red_marker_to_bed_tab_x_mm",
            "tool.t1.red_marker_to_bed_tab_x_mm",
        ):
            for field in ("offset_mm", "reference_commanded_x_mm"):
                if not isinstance(value.get(field), (int, float)):
                    raise CalibrationGraphError(
                        f"red-marker {field} must be numeric"
                    )
                if (
                    fact_definition_version in ROLE_AWARE_FACT_DEFINITION_VERSIONS
                    and declared_roles.get(field) != "coordinate_system"
                ):
                    raise CalibrationGraphError(
                        f"red-marker {field} must be a coordinate-system item"
                    )
        if fact_name == "calibration.rough_tool_x.active_snapshot":
            for field in (
                "bed_tab_x_mm",
                "t0_old_x_endstop_mm",
                "t0_calculated_correction_mm",
                "t0_applied_x_endstop_mm",
                "t1_old_x_endstop_mm",
                "t1_calculated_correction_mm",
                "t1_applied_x_endstop_mm",
            ):
                if not isinstance(value.get(field), (int, float)):
                    raise CalibrationGraphError(
                        f"rough-X active snapshot {field} must be numeric"
                    )
                if (
                    fact_definition_version in ROLE_AWARE_FACT_DEFINITION_VERSIONS
                    and declared_roles.get(field) != "coordinate_system"
                ):
                    raise CalibrationGraphError(
                        f"rough-X active snapshot {field} must be "
                        "a coordinate-system item"
                    )
        if fact_name == "calibration.rough_tool_x.verified":
            if (
                fact_definition_version in ROLE_AWARE_FACT_DEFINITION_VERSIONS
                and fact.get("role") != "diagnostic"
            ):
                raise CalibrationGraphError(
                    "rough-X verification must be a diagnostic fact"
                )
        dependencies = _require_list(
            fact.get("dependencies"),
            f"fact_set.facts[{fact_index}].dependencies",
        )
        for dependency_index, dependency_value in enumerate(dependencies):
            dependency = _require_mapping(
                dependency_value,
                f"fact.dependencies[{dependency_index}]",
            )
            _require_string(dependency.get("fact_name"), "dependency.fact_name")
            bound_hash = _require_string(
                dependency.get("fact_set_hash"), "dependency.fact_set_hash"
            )
            if not bound_hash.startswith("sha256:"):
                raise CalibrationGraphError(
                    "dependency fact_set_hash must be canonical"
                )
    expected_hash = content_hash(record, "fact_set_hash")
    if record.get("fact_set_hash") != expected_hash:
        raise CalibrationGraphError("fact set hash mismatch")
    return record


def validate_publication(record: Any) -> dict[str, Any]:
    record = _require_mapping(record, "publication")
    _validate_header(record, PUBLICATION_SCHEMA, "publication")
    _require_string(record.get("publication_id"), "publication.publication_id")
    _require_string(record.get("fact_set_hash"), "publication.fact_set_hash")
    _require_list(record.get("facts"), "publication.facts")
    expected_hash = content_hash(record, "publication_hash")
    if record.get("publication_hash") != expected_hash:
        raise CalibrationGraphError("publication hash mismatch")
    return record


def _publication_files(publications_dir: Path) -> Iterable[Path]:
    if not publications_dir.exists():
        return ()
    return sorted(publications_dir.glob("*.json"))


def _fact_set_index(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    jobs_dir = root / "jobs"
    paths = (
        list(jobs_dir.glob("*/analysis/*/fact_set.json")) if jobs_dir.exists() else []
    )
    seeds_dir = root / "seeds"
    if seeds_dir.exists():
        paths.extend(seeds_dir.glob("*/fact_set.json"))
    for path in sorted(paths):
        fact_set = validate_fact_set(load_json(path))
        fact_set_hash = fact_set["fact_set_hash"]
        if fact_set_hash in result:
            raise CalibrationGraphError(
                f"duplicate fact_set_hash {fact_set_hash}: {path}"
            )
        result[fact_set_hash] = (path, fact_set)
    return result


def _detect_cycles(
    facts_by_set: dict[str, tuple[Path, dict[str, Any]]],
) -> None:
    graph: dict[str, set[str]] = {}
    for fact_set_hash, (_path, fact_set) in facts_by_set.items():
        dependencies: set[str] = set()
        for fact in fact_set["facts"]:
            dependencies.update(
                dependency["fact_set_hash"]
                for dependency in fact.get("dependencies", [])
            )
        graph[fact_set_hash] = dependencies

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise CalibrationGraphError(f"fact dependency cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, ()):
            if dependency in graph:
                visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def rebuild_catalog(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    facts_by_set = _fact_set_index(root)
    _detect_cycles(facts_by_set)

    publications: list[dict[str, Any]] = []
    heads: dict[str, dict[str, Any]] = {}
    for path in _publication_files(root / "publications"):
        publication = validate_publication(load_json(path))
        fact_set_entry = facts_by_set.get(publication["fact_set_hash"])
        if fact_set_entry is None:
            raise CalibrationGraphError(
                f"publication {path} references a missing fact set"
            )
        fact_set_path, fact_set = fact_set_entry
        published_names = [fact["name"] for fact in fact_set["facts"]]
        if publication["facts"] != published_names:
            raise CalibrationGraphError(
                f"publication {path} does not exactly bind its fact set"
            )
        expected_previous = publication.get("supersedes") or {}
        for fact_name in published_names:
            actual_previous = heads.get(fact_name, {}).get("fact_set_hash")
            if expected_previous.get(fact_name) != actual_previous:
                raise CalibrationGraphError(
                    f"publication conflict for {fact_name}: expected "
                    f"{expected_previous.get(fact_name)!r}, current "
                    f"{actual_previous!r}"
                )
            heads[fact_name] = {
                "fact_set_hash": publication["fact_set_hash"],
                "job_id": fact_set["job_id"],
                "analysis_run_id": fact_set["analysis_run_id"],
                "publication_id": publication["publication_id"],
                "published_at_utc": publication["created_at_utc"],
                "applicability_hash": fact_set["applicability_hash"],
                "fact_set_path": str(fact_set_path.relative_to(root)),
                "source_kind": (
                    "operation"
                    if str(fact_set.get("job_id", "")).startswith("operation:")
                    else (
                        "seed"
                        if fact_set_path.parent.parent == root / "seeds"
                        else "analysis"
                    )
                ),
            }
        publications.append(publication)

    stale_sets: dict[str, list[str]] = {}
    changed = True
    while changed:
        changed = False
        for fact_set_hash, (_path, fact_set) in facts_by_set.items():
            reasons = list(stale_sets.get(fact_set_hash, []))
            for fact in fact_set["facts"]:
                for dependency in fact.get("dependencies", []):
                    dependency_hash = dependency["fact_set_hash"]
                    head_hash = heads.get(dependency["fact_name"], {}).get(
                        "fact_set_hash"
                    )
                    if head_hash != dependency_hash:
                        reasons.append(
                            f"{dependency['fact_name']} current head is "
                            f"{head_hash!r}, bound to {dependency_hash!r}"
                        )
                    if dependency_hash in stale_sets:
                        reasons.append(f"dependency {dependency_hash} is stale")
            unique = sorted(set(reasons))
            if unique and stale_sets.get(fact_set_hash) != unique:
                stale_sets[fact_set_hash] = unique
                changed = True

    jobs: list[dict[str, Any]] = []
    jobs_dir = root / "jobs"
    if jobs_dir.exists():
        for job_dir in sorted(path for path in jobs_dir.iterdir() if path.is_dir()):
            state_path = job_dir / "state.json"
            manifest_path = job_dir / "manifest.json"
            if not state_path.exists() or not manifest_path.exists():
                continue
            state = load_json(state_path)
            manifest = validate_manifest(load_json(manifest_path))
            analyses: list[dict[str, Any]] = []
            analysis_dir = job_dir / "analysis"
            if analysis_dir.exists():
                for result_path in sorted(analysis_dir.glob("*/result.json")):
                    result = validate_analysis(load_json(result_path))
                    fact_set_hash = None
                    fact_path = result_path.with_name("fact_set.json")
                    if fact_path.exists():
                        fact_set_hash = validate_fact_set(load_json(fact_path))[
                            "fact_set_hash"
                        ]
                    analyses.append(
                        {
                            "analysis_run_id": result["analysis_run_id"],
                            "state": result["state"],
                            "analysis_hash": result["analysis_hash"],
                            "fact_set_hash": fact_set_hash,
                            "stale": fact_set_hash in stale_sets,
                        }
                    )
            jobs.append(
                {
                    "job_id": manifest["job_id"],
                    "job_type": manifest["job_type"],
                    "state": state.get("state"),
                    "frame_count": manifest["frame_count"],
                    "committed_frame_count": state.get("committed_frame_count", 0),
                    "created_at_utc": manifest["created_at_utc"],
                    "analyses": analyses,
                }
            )

    catalog = {
        "schema": FACT_CATALOG_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "heads": heads,
        "stale_fact_sets": stale_sets,
        "publications": [
            {
                "publication_id": item["publication_id"],
                "publication_hash": item["publication_hash"],
                "fact_set_hash": item["fact_set_hash"],
                "facts": item["facts"],
                "created_at_utc": item["created_at_utc"],
            }
            for item in publications
        ],
        "jobs": jobs,
    }
    atomic_write_json(root / "catalog.json", catalog)
    return catalog


def publish_fact_set(
    root: Path,
    job_id: str,
    analysis_run_id: str,
    *,
    active_applicability_hash: str | None = None,
) -> dict[str, Any]:
    analysis_dir = root / "jobs" / job_id / "analysis" / analysis_run_id
    result = validate_analysis(load_json(analysis_dir / "result.json"))
    if result["state"] != "accepted":
        raise CalibrationGraphError("rejected analyses cannot be published")
    fact_set = validate_fact_set(load_json(analysis_dir / "fact_set.json"))
    if result["analysis_hash"] != fact_set["analysis_hash"]:
        raise CalibrationGraphError("fact set is not bound to this analysis")
    if active_applicability_hash is not None and (
        fact_set["applicability_hash"] != active_applicability_hash
    ):
        raise CalibrationGraphError(
            "active scoped configuration no longer matches the analyzed job"
        )

    catalog = rebuild_catalog(root)
    existing = [
        item
        for item in catalog["publications"]
        if item["fact_set_hash"] == fact_set["fact_set_hash"]
    ]
    if existing:
        raise CalibrationGraphError(
            f"fact set is already published by {existing[0]['publication_id']}"
        )
    supersedes = {
        fact["name"]: catalog["heads"].get(fact["name"], {}).get("fact_set_hash")
        for fact in fact_set["facts"]
    }
    publication_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + fact_set["fact_set_hash"].split(":", 1)[1][:10]
    )
    publication = {
        "schema": PUBLICATION_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "publication_id": publication_id,
        "created_at_utc": utc_now(),
        "job_id": job_id,
        "analysis_run_id": analysis_run_id,
        "analysis_hash": result["analysis_hash"],
        "fact_set_hash": fact_set["fact_set_hash"],
        "facts": [fact["name"] for fact in fact_set["facts"]],
        "supersedes": supersedes,
        "publication_hash": "",
    }
    publication["publication_hash"] = content_hash(publication, "publication_hash")
    validate_publication(publication)
    publication_path = root / "publications" / f"{publication_id}.json"
    atomic_write_json(publication_path, publication, immutable=True)
    catalog = rebuild_catalog(root)
    return {
        "publication": publication,
        "publication_path": str(publication_path),
        "catalog": catalog,
    }


def publish_seed_fact_set(root: Path, fact_set_path: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved_path = fact_set_path.resolve()
    seeds_root = (root / "seeds").resolve()
    if seeds_root not in resolved_path.parents:
        raise CalibrationGraphError(
            f"seed fact set must be beneath {seeds_root}: {resolved_path}"
        )
    fact_set = validate_fact_set(load_json(resolved_path))
    catalog = rebuild_catalog(root)
    existing = [
        item
        for item in catalog["publications"]
        if item["fact_set_hash"] == fact_set["fact_set_hash"]
    ]
    if existing:
        return {
            "publication": existing[0],
            "publication_path": None,
            "catalog": catalog,
            "already_published": True,
        }
    supersedes = {
        fact["name"]: catalog["heads"].get(fact["name"], {}).get("fact_set_hash")
        for fact in fact_set["facts"]
    }
    publication_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + fact_set["fact_set_hash"].split(":", 1)[1][:10]
    )
    publication = {
        "schema": PUBLICATION_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "publication_id": publication_id,
        "created_at_utc": utc_now(),
        "job_id": fact_set["job_id"],
        "analysis_run_id": fact_set["analysis_run_id"],
        "analysis_hash": fact_set["analysis_hash"],
        "fact_set_hash": fact_set["fact_set_hash"],
        "facts": [fact["name"] for fact in fact_set["facts"]],
        "supersedes": supersedes,
        "publication_hash": "",
    }
    publication["publication_hash"] = content_hash(publication, "publication_hash")
    validate_publication(publication)
    publication_path = root / "publications" / f"{publication_id}.json"
    atomic_write_json(publication_path, publication, immutable=True)
    catalog = rebuild_catalog(root)
    if resolved_root != root.resolve():
        raise CalibrationGraphError("calibration root changed during publication")
    return {
        "publication": publication,
        "publication_path": str(publication_path),
        "catalog": catalog,
        "already_published": False,
    }
