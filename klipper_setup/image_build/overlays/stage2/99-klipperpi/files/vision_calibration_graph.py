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
FACT_ROLES = {"coordinate_system", "diagnostic", "acquisition_profile"}
JOB_TYPES = {
    "nozzle_cam_bed_fiducial_lighting_sweep",
    "nozzle_cam_bed_fiducial_y_metric",
    "nozzle_cam_bed_tab_corner",
    "idex_tool_red_marker_x_sweep",
    "idex_rough_tool_x_verify",
    "idex_nozzle_fine_xz_grid",
    "idex_fine_tool_xy_verify",
}
SEED_FACT_NAMES = {
    "bed.tab_corner.printer_xyz",
    "bed.fiducial_patch.physical_reference",
    "bed.fiducial_patch.printer_z_mm",
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
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_bytes(canonical_json_bytes(payload) + b"\n")
    if immutable and path.exists():
        temporary.unlink(missing_ok=True)
        raise CalibrationGraphError(f"immutable record already exists: {path}")
    temporary.replace(path)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CalibrationGraphError(f"missing record: {path}") from None
    except json.JSONDecodeError as exc:
        raise CalibrationGraphError(f"invalid JSON in {path}: {exc}") from None


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CalibrationGraphError(f"{name} must be an object")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise CalibrationGraphError(f"{name} must be an array")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationGraphError(f"{name} must be a non-empty string")
    return value


def _header(record: dict[str, Any], schema: str, name: str) -> None:
    if record.get("schema") != schema:
        raise CalibrationGraphError(f"{name}.schema must be {schema!r}")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise CalibrationGraphError(
            f"{name}.schema_version must be {SCHEMA_VERSION}"
        )


def validate_registry(record: Any) -> dict[str, Any]:
    record = _mapping(record, "registry")
    _header(record, REGISTRY_SCHEMA, "registry")
    job_types = _mapping(record.get("job_types"), "registry.job_types")
    if set(job_types) != JOB_TYPES:
        raise CalibrationGraphError(
            f"registry job set must be exactly {sorted(JOB_TYPES)}"
        )
    for job_type, value in job_types.items():
        definition = _mapping(value, f"registry.job_types.{job_type}")
        if definition.get("definition_version") != 1:
            raise CalibrationGraphError(
                f"{job_type} definition_version must be 1"
            )
        if definition.get("fact_definition_version") != 1:
            raise CalibrationGraphError(
                f"{job_type} fact_definition_version must be 1"
            )
        if definition.get("camera") != "nozzle_cam":
            raise CalibrationGraphError(f"{job_type} camera must be nozzle_cam")
        if definition.get("publish_on_accept") is not True:
            raise CalibrationGraphError(
                f"{job_type} must publish immediately when accepted"
            )
        _mapping(definition.get("localizer"), f"{job_type}.localizer")
        facts = _list(definition.get("fact_names"), f"{job_type}.fact_names")
        if not facts or not all(isinstance(item, str) and item for item in facts):
            raise CalibrationGraphError(f"{job_type} has an invalid fact contract")
        requirements = _list(definition.get("requires"), f"{job_type}.requires")
        names = set()
        for index, value in enumerate(requirements):
            requirement = _mapping(value, f"{job_type}.requires[{index}]")
            name = _string(requirement.get("requirement"), "requirement")
            if name in names:
                raise CalibrationGraphError(
                    f"{job_type} has duplicate requirement {name}"
                )
            names.add(name)
            _string(requirement.get("fact_name"), "requirement.fact_name")
            if requirement.get("fact_definition_version") != 1:
                raise CalibrationGraphError(
                    f"{job_type} requirements must bind definition version 1"
                )
    if (
        job_types["nozzle_cam_bed_fiducial_y_metric"].get("y_offsets_mm")
        != [0, 10, 20, 20, 10, 0]
    ):
        raise CalibrationGraphError("bed metric motion order is invalid")
    if (
        job_types["idex_tool_red_marker_x_sweep"].get("x_positions_mm")
        != [160, 170, 180, 190, 200, 210]
    ):
        raise CalibrationGraphError("red-marker X motion order is invalid")
    fine = job_types["idex_nozzle_fine_xz_grid"]
    if fine.get("x_offsets_from_bed_tab_mm") != [10, 13, 16, 19, 22, 25]:
        raise CalibrationGraphError("fine nozzle X offsets are invalid")
    if fine.get("full_row_z_mm") != [1, 5, 9]:
        raise CalibrationGraphError("fine nozzle full-row Z values are invalid")
    if fine.get("center_only_z_mm") != [3, 7]:
        raise CalibrationGraphError("fine nozzle center-only Z values are invalid")
    if fine.get("safe_tool_change_z_mm") != 9:
        raise CalibrationGraphError("fine nozzle tool-change Z is invalid")
    verify = job_types["idex_fine_tool_xy_verify"]
    if (
        verify.get("center_x_offset_from_bed_tab_mm") != 16
        or verify.get("x_dither_mm") != 3
        or verify.get("y_dither_mm") != 3
    ):
        raise CalibrationGraphError("fine X/Y verification dithers are invalid")
    if verify.get("capture_z_mm") != 5 or verify.get("safe_tool_change_z_mm") != 9:
        raise CalibrationGraphError("fine X/Y verification Z poses are invalid")
    return record


def _validate_input_facts(record: dict[str, Any]) -> None:
    bindings = _list(record.get("input_facts", []), "manifest.input_facts")
    requirements = set()
    for index, value in enumerate(bindings):
        binding = _mapping(value, f"manifest.input_facts[{index}]")
        requirement = _string(binding.get("requirement"), "input requirement")
        if requirement in requirements:
            raise CalibrationGraphError(
                f"duplicate input-fact requirement {requirement}"
            )
        requirements.add(requirement)
        _string(binding.get("fact_name"), "input fact name")
        fact_set_hash = _string(binding.get("fact_set_hash"), "input fact set hash")
        if not fact_set_hash.startswith("sha256:"):
            raise CalibrationGraphError("input fact set hash must be canonical")
        if binding.get("fact_definition_version") != 1:
            raise CalibrationGraphError("input fact definition_version must be 1")


def validate_manifest(record: Any) -> dict[str, Any]:
    record = _mapping(record, "manifest")
    _header(record, MANIFEST_SCHEMA, "manifest")
    _string(record.get("job_id"), "manifest.job_id")
    job_type = record.get("job_type")
    if job_type not in JOB_TYPES:
        raise CalibrationGraphError("manifest has an unsupported job_type")
    if record.get("definition_version") != 1:
        raise CalibrationGraphError("manifest definition_version must be 1")
    if record.get("camera") != "nozzle_cam":
        raise CalibrationGraphError("manifest.camera must be nozzle_cam")
    if record.get("publish_on_accept") is not True:
        raise CalibrationGraphError("manifest must publish accepted facts")
    _mapping(record.get("localizer"), "manifest.localizer")
    frames = _list(record.get("frames"), "manifest.frames")
    if record.get("frame_count") != len(frames):
        raise CalibrationGraphError("manifest frame_count mismatch")
    for index, value in enumerate(frames):
        frame = _mapping(value, f"manifest.frames[{index}]")
        if frame.get("seq") != index:
            raise CalibrationGraphError(f"manifest frame {index} has wrong seq")
        _string(frame.get("frame"), f"manifest.frames[{index}].frame")
    _validate_input_facts(record)

    if job_type == "nozzle_cam_bed_fiducial_lighting_sweep":
        if len(frames) != 24:
            raise CalibrationGraphError("lighting sweep must contain 24 frames")
        for frame in frames:
            _string(frame.get("profile"), "lighting frame profile")
            pixels = _mapping(frame.get("light_pixels"), "lighting frame pixels")
            if set(pixels) != {str(index) for index in range(1, 9)}:
                raise CalibrationGraphError(
                    "lighting frame must define all eight light pixels"
                )
    elif job_type == "nozzle_cam_bed_fiducial_y_metric":
        if [frame.get("y_offset_mm") for frame in frames] != [
            0,
            10,
            20,
            20,
            10,
            0,
        ]:
            raise CalibrationGraphError("metric manifest Y motion order is invalid")
    elif job_type == "nozzle_cam_bed_tab_corner":
        if len(frames) != 5:
            raise CalibrationGraphError("corner job must contain five duplicates")
        if [frame.get("duplicate_index") for frame in frames] != list(range(5)):
            raise CalibrationGraphError("corner duplicate order is invalid")
    elif job_type == "idex_tool_red_marker_x_sweep":
        expected = [
            (tool, x)
            for tool in ("T0", "T1")
            for x in (160, 170, 180, 190, 200, 210)
        ]
        if [(frame.get("tool"), frame.get("x_mm")) for frame in frames] != expected:
            raise CalibrationGraphError("red-marker motion order is invalid")
    elif job_type == "idex_rough_tool_x_verify":
        if len(frames) != 2 or [frame.get("tool") for frame in frames] != [
            "T0",
            "T1",
        ]:
            raise CalibrationGraphError("rough-X verification frames are invalid")
    elif job_type == "idex_nozzle_fine_xz_grid":
        if len(frames) != 40:
            raise CalibrationGraphError("fine nozzle grid must contain 40 frames")
        if any(float(frame.get("z_mm", -1)) < 1.0 for frame in frames):
            raise CalibrationGraphError("fine nozzle grid may not command below Z=1")
        if [frame.get("tool") for frame in frames[:20]] != ["T0"] * 20:
            raise CalibrationGraphError("fine nozzle grid must acquire T0 first")
        if [frame.get("tool") for frame in frames[20:]] != ["T1"] * 20:
            raise CalibrationGraphError("fine nozzle grid must acquire T1 second")
    elif job_type == "idex_fine_tool_xy_verify":
        expected = [
            (tool, pose)
            for tool in ("T0", "T1")
            for pose in ("center", "x_dither", "y_dither")
        ]
        if [(frame.get("tool"), frame.get("pose")) for frame in frames] != expected:
            raise CalibrationGraphError(
                "fine X/Y verification frame order is invalid"
            )
        if any(
            float(frame.get("commanded_position_mm", [0, 0, -1])[2]) < 3.0
            for frame in frames
        ):
            raise CalibrationGraphError(
                "fine X/Y verification may not command below Z=3"
            )

    expected_hash = content_hash(record, "manifest_hash")
    if record.get("manifest_hash") != expected_hash:
        raise CalibrationGraphError("manifest hash mismatch")
    return record


def validate_analysis(record: Any) -> dict[str, Any]:
    record = _mapping(record, "analysis")
    _header(record, ANALYSIS_SCHEMA, "analysis")
    _string(record.get("analysis_run_id"), "analysis.analysis_run_id")
    _string(record.get("job_id"), "analysis.job_id")
    if record.get("state") not in ("accepted", "rejected"):
        raise CalibrationGraphError("analysis.state must be accepted or rejected")
    if record.get("state") == "rejected" and record.get("fact_set_path") is not None:
        raise CalibrationGraphError("rejected analysis cannot publish facts")
    if record.get("analysis_hash") != content_hash(record, "analysis_hash"):
        raise CalibrationGraphError("analysis hash mismatch")
    return record


def _numeric_vector(value: Any, length: int, name: str) -> list[Any]:
    result = _list(value, name)
    if len(result) != length or not all(
        isinstance(item, (int, float)) for item in result
    ):
        raise CalibrationGraphError(
            f"{name} must contain {length} numeric components"
        )
    return result


def validate_fact_set(record: Any) -> dict[str, Any]:
    record = _mapping(record, "fact_set")
    _header(record, FACT_SET_SCHEMA, "fact_set")
    if (
        record.get("accepted") is not True
        or record.get("publication_eligible") is not True
    ):
        raise CalibrationGraphError(
            "fact set must be accepted and publication eligible"
        )
    encoded = canonical_json_bytes(record).decode("utf-8")
    for forbidden in ("uncertainty", "uncertainties", "covariance"):
        if forbidden in encoded:
            raise CalibrationGraphError(f"fact sets must not contain {forbidden}")
    facts = _list(record.get("facts"), "fact_set.facts")
    if not facts:
        raise CalibrationGraphError("fact set must contain facts")
    names = set()
    for index, value in enumerate(facts):
        fact = _mapping(value, f"fact_set.facts[{index}]")
        name = _string(fact.get("name"), "fact.name")
        if name in names:
            raise CalibrationGraphError(f"duplicate fact name {name}")
        names.add(name)
        if fact.get("definition_version") != 1:
            raise CalibrationGraphError("fact definition_version must be 1")
        role = _string(fact.get("role"), "fact.role")
        if role not in FACT_ROLES:
            raise CalibrationGraphError(f"invalid fact role {role}")
        fact_value = _mapping(fact.get("value"), "fact.value")
        declarations = _list(fact.get("value_items"), "fact.value_items")
        declared = {}
        for declaration_value in declarations:
            declaration = _mapping(declaration_value, "fact value item")
            field = _string(declaration.get("field"), "fact item field")
            item_role = _string(declaration.get("role"), "fact item role")
            if item_role not in FACT_ROLES:
                raise CalibrationGraphError(f"invalid fact item role {item_role}")
            if field in declared:
                raise CalibrationGraphError(f"duplicate fact item {field}")
            declared[field] = item_role
        if set(declared) != set(fact_value):
            raise CalibrationGraphError(
                "fact item declarations must exactly cover value fields"
            )
        if role == "coordinate_system" and not any(
            item == "coordinate_system" for item in declared.values()
        ):
            raise CalibrationGraphError(
                "coordinate-system fact must contain coordinate-system items"
            )
        if role == "diagnostic" and any(
            item == "coordinate_system" for item in declared.values()
        ):
            raise CalibrationGraphError(
                "diagnostic fact cannot contain coordinate-system items"
            )
        if role == "acquisition_profile" and any(
            item == "coordinate_system" for item in declared.values()
        ):
            raise CalibrationGraphError(
                "acquisition profile cannot contain coordinate-system items"
            )
        dependencies = _list(fact.get("dependencies"), "fact.dependencies")
        for dependency_value in dependencies:
            dependency = _mapping(dependency_value, "fact dependency")
            _string(dependency.get("fact_name"), "dependency.fact_name")
            bound_hash = _string(
                dependency.get("fact_set_hash"), "dependency.fact_set_hash"
            )
            if not bound_hash.startswith("sha256:"):
                raise CalibrationGraphError(
                    "dependency fact_set_hash must be canonical"
                )

        if name == "bed.tab_corner.printer_xyz":
            _numeric_vector(fact_value.get("xyz_mm"), 3, "bed-tab XYZ")
        elif name == "bed.fiducial_patch.printer_z_mm":
            if not isinstance(fact_value.get("z_mm"), (int, float)):
                raise CalibrationGraphError("fiducial printer Z must be numeric")
        elif name == "camera.nozzle_cam.bed_fiducial.local_metric_model":
            _numeric_vector(
                fact_value.get("image_y_axis_vector_px_per_mm"),
                2,
                "metric printer-Y vector",
            )
        elif name == "camera.nozzle_cam.partial_bed_coordinate_system":
            _numeric_vector(
                fact_value.get("corner_pixel_xy_px"), 2, "corner pixel"
            )
            _numeric_vector(
                fact_value.get("corner_printer_xyz_mm"), 3, "corner printer XYZ"
            )
        elif name == "camera.nozzle_cam.image_x_axis_vector_px_per_mm_at_z2":
            _numeric_vector(
                fact_value.get("axis_vector_px_per_mm"), 2, "image X vector"
            )
        elif name in {
            "tool.t0.red_marker_to_bed_tab_x_mm",
            "tool.t1.red_marker_to_bed_tab_x_mm",
        }:
            for field in ("offset_mm", "reference_commanded_x_mm"):
                if not isinstance(fact_value.get(field), (int, float)):
                    raise CalibrationGraphError(f"red-marker {field} must be numeric")
    if record.get("fact_set_hash") != content_hash(record, "fact_set_hash"):
        raise CalibrationGraphError("fact set hash mismatch")
    return record


def validate_publication(record: Any) -> dict[str, Any]:
    record = _mapping(record, "publication")
    _header(record, PUBLICATION_SCHEMA, "publication")
    _string(record.get("publication_id"), "publication.publication_id")
    _string(record.get("fact_set_hash"), "publication.fact_set_hash")
    _list(record.get("facts"), "publication.facts")
    if record.get("publication_hash") != content_hash(
        record, "publication_hash"
    ):
        raise CalibrationGraphError("publication hash mismatch")
    return record


def _publication_files(directory: Path) -> Iterable[Path]:
    return sorted(directory.glob("*.json")) if directory.exists() else ()


def _fact_sets(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    paths = []
    jobs = root / "jobs"
    if jobs.exists():
        paths.extend(jobs.glob("*/analysis/*/fact_set.json"))
    seeds = root / "seeds"
    if seeds.exists():
        paths.extend(seeds.glob("*/fact_set.json"))
    result = {}
    for path in sorted(paths):
        fact_set = validate_fact_set(load_json(path))
        fact_set_hash = fact_set["fact_set_hash"]
        if fact_set_hash in result:
            raise CalibrationGraphError(f"duplicate fact set {fact_set_hash}")
        result[fact_set_hash] = (path, fact_set)
    return result


def _detect_cycles(fact_sets: dict[str, tuple[Path, dict[str, Any]]]) -> None:
    graph = {
        fact_set_hash: {
            dependency["fact_set_hash"]
            for fact in fact_set["facts"]
            for dependency in fact.get("dependencies", [])
            if dependency["fact_set_hash"] in fact_sets
        }
        for fact_set_hash, (_path, fact_set) in fact_sets.items()
    }
    visiting = set()
    visited = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise CalibrationGraphError(f"fact dependency cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def rebuild_catalog(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    fact_sets = _fact_sets(root)
    _detect_cycles(fact_sets)
    publications = []
    heads: dict[str, dict[str, Any]] = {}
    for path in _publication_files(root / "publications"):
        publication = validate_publication(load_json(path))
        if publication["fact_set_hash"] not in fact_sets:
            raise CalibrationGraphError(
                f"publication {path} references missing fact set"
            )
        fact_set_path, fact_set = fact_sets[publication["fact_set_hash"]]
        names = [fact["name"] for fact in fact_set["facts"]]
        if publication["facts"] != names:
            raise CalibrationGraphError("publication fact list mismatch")
        supersedes = publication.get("supersedes") or {}
        for name in names:
            previous = heads.get(name, {}).get("fact_set_hash")
            if supersedes.get(name) != previous:
                raise CalibrationGraphError(
                    f"publication conflict for {name}: expected "
                    f"{supersedes.get(name)!r}, current {previous!r}"
                )
            heads[name] = {
                "fact_set_hash": fact_set["fact_set_hash"],
                "job_id": fact_set["job_id"],
                "analysis_run_id": fact_set["analysis_run_id"],
                "publication_id": publication["publication_id"],
                "published_at_utc": publication["created_at_utc"],
                "applicability_hash": fact_set["applicability_hash"],
                "fact_set_path": str(fact_set_path.relative_to(root)),
                "source_kind": (
                    "seed"
                    if (root / "seeds").resolve() in fact_set_path.resolve().parents
                    else (
                        "operation"
                        if str(fact_set["job_id"]).startswith("operation:")
                        else "analysis"
                    )
                ),
            }
        publications.append(publication)

    stale: dict[str, list[str]] = {}
    changed = True
    while changed:
        changed = False
        for fact_set_hash, (_path, fact_set) in fact_sets.items():
            reasons = set(stale.get(fact_set_hash, []))
            for fact in fact_set["facts"]:
                for dependency in fact.get("dependencies", []):
                    head = heads.get(dependency["fact_name"], {}).get("fact_set_hash")
                    if head != dependency["fact_set_hash"]:
                        reasons.add(
                            f"{dependency['fact_name']} head {head!r} differs "
                            f"from bound {dependency['fact_set_hash']!r}"
                        )
                    if dependency["fact_set_hash"] in stale:
                        reasons.add(
                            f"dependency {dependency['fact_set_hash']} is stale"
                        )
            if reasons and sorted(reasons) != stale.get(fact_set_hash):
                stale[fact_set_hash] = sorted(reasons)
                changed = True

    jobs = []
    jobs_root = root / "jobs"
    if jobs_root.exists():
        for job_dir in sorted(item for item in jobs_root.iterdir() if item.is_dir()):
            if not (job_dir / "manifest.json").exists() or not (
                job_dir / "state.json"
            ).exists():
                continue
            manifest = validate_manifest(load_json(job_dir / "manifest.json"))
            state = load_json(job_dir / "state.json")
            analyses = []
            for result_path in sorted(job_dir.glob("analysis/*/result.json")):
                result = validate_analysis(load_json(result_path))
                fact_path = result_path.with_name("fact_set.json")
                fact_set_hash = (
                    validate_fact_set(load_json(fact_path))["fact_set_hash"]
                    if fact_path.exists()
                    else None
                )
                analyses.append(
                    {
                        "analysis_run_id": result["analysis_run_id"],
                        "state": result["state"],
                        "analysis_hash": result["analysis_hash"],
                        "fact_set_hash": fact_set_hash,
                        "stale": fact_set_hash in stale,
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
        "stale_fact_sets": stale,
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


def _publish(root: Path, fact_set_path: Path) -> dict[str, Any]:
    fact_set = validate_fact_set(load_json(fact_set_path))
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
    publication_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-"
        + fact_set["fact_set_hash"][7:17]
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
        "supersedes": {
            fact["name"]: catalog["heads"]
            .get(fact["name"], {})
            .get("fact_set_hash")
            for fact in fact_set["facts"]
        },
        "publication_hash": "",
    }
    publication["publication_hash"] = content_hash(publication, "publication_hash")
    validate_publication(publication)
    publication_path = root / "publications" / f"{publication_id}.json"
    atomic_write_json(publication_path, publication, immutable=True)
    return {
        "publication": publication,
        "publication_path": str(publication_path),
        "catalog": rebuild_catalog(root),
        "already_published": False,
    }


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
    fact_set_path = analysis_dir / "fact_set.json"
    fact_set = validate_fact_set(load_json(fact_set_path))
    if fact_set["analysis_hash"] != result["analysis_hash"]:
        raise CalibrationGraphError("fact set is not bound to this analysis")
    if (
        active_applicability_hash is not None
        and fact_set["applicability_hash"] != active_applicability_hash
    ):
        raise CalibrationGraphError("active applicability hash has changed")
    published = _publish(root, fact_set_path)
    if published["already_published"]:
        raise CalibrationGraphError(
            f"fact set is already published by "
            f"{published['publication']['publication_id']}"
        )
    return published


def publish_seed_fact_set(root: Path, fact_set_path: Path) -> dict[str, Any]:
    seeds_root = (root / "seeds").resolve()
    resolved = fact_set_path.resolve()
    if seeds_root not in resolved.parents:
        raise CalibrationGraphError(
            f"seed fact set must be beneath {seeds_root}: {resolved}"
        )
    return _publish(root, fact_set_path)
