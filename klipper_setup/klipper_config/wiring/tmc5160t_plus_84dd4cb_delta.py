"""Generate one-off assembly deltas for the 84dd4cb TMC5160T Plus redesign."""

from __future__ import annotations

import argparse
import copy
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from xml.etree import ElementTree as ET

from mege_circuits.pinout import (
    PinoutProject,
    generate_discrete_top_svg,
    generate_routed_svg,
    load_pinout_config,
    route_problematic_connections,
    write_svg,
)

REDESIGN_COMMIT = "84dd4cb8893484caddba66566d9eebe7c9a82bb7"
REDESIGN_BASE_REF = f"{REDESIGN_COMMIT}^"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
SVG_TAG = f"{{{SVG_NAMESPACE}}}"
DELTA_PURPLE = "#7e22ce"
REMOVED_PURPLE = "#c026d3"

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
CONFIG_PATH = SCRIPT_DIR / "rp2040plus_btt_tmc5160t_plus_y.yaml"
CONFIG_REPO_PATH = CONFIG_PATH.relative_to(REPO_ROOT).as_posix()
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "diagrams"
TOP_DELTA_FILENAME = "rp2040plus_btt_tmc5160t_plus_y_top_discrete_84dd4cb_delta.svg"
BOTTOM_DELTA_FILENAME = "rp2040plus_btt_tmc5160t_plus_y_bottom_84dd4cb_delta.svg"

ET.register_namespace("", SVG_NAMESPACE)


@dataclass(frozen=True)
class ComponentDelta:
    """Component refs classified against the redesign commit's first parent."""

    added: tuple[str, ...]
    changed: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: tuple[str, ...]


@dataclass(frozen=True)
class GraphEdge:
    """One wiring edge identified by physical pin coordinates."""

    connection_index: int
    start_coordinate: tuple[float, float]
    end_coordinate: tuple[float, float]
    from_pin: str
    to_pin: str
    style: tuple[str, str]

    @property
    def coordinate_key(
        self,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        if self.start_coordinate <= self.end_coordinate:
            return self.start_coordinate, self.end_coordinate
        return self.end_coordinate, self.start_coordinate


@dataclass(frozen=True)
class ConnectionDelta:
    """Target edge states plus obsolete base edges."""

    target_status_by_index: dict[int, str]
    removed_edges: tuple[GraphEdge, ...]

    def count(self, status: str) -> int:
        """Count target connections assigned to one delta status."""
        return sum(
            edge_status == status
            for edge_status in self.target_status_by_index.values()
        )


@dataclass(frozen=True)
class DeltaRenderResult:
    """Generated paths and their audited delta classifications."""

    top_path: Path
    bottom_path: Path
    components: ComponentDelta
    connections: ConnectionDelta


def _git_show_text(revision: str, repo_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{revision}:{repo_path}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _load_revision_project(
    revision: str,
    *,
    temporary_directory: Path,
) -> PinoutProject:
    config_copy = temporary_directory / f"{revision.replace('^', '_parent')}.yaml"
    config_copy.write_text(
        _git_show_text(revision, CONFIG_REPO_PATH),
        encoding="utf-8",
    )
    return load_pinout_config(config_copy)


def _component_signature(project: PinoutProject, component) -> tuple:
    terminal_coordinates = tuple(
        sorted(
            (
                terminal,
                project.pin_positions[pin_name],
            )
            for terminal, pin_name in component.terminals.items()
        )
    )
    return (
        component.kind,
        component.value,
        component.part,
        component.pinout_variant,
        terminal_coordinates,
    )


def analyze_component_deltas(
    base_project: PinoutProject,
    target_project: PinoutProject,
) -> ComponentDelta:
    """Classify components by ref while comparing physical terminal coordinates."""
    base_components = {
        component.ref: component for component in base_project.component_placements
    }
    target_components = {
        component.ref: component for component in target_project.component_placements
    }
    common_refs = set(base_components) & set(target_components)
    changed = tuple(
        sorted(
            ref
            for ref in common_refs
            if _component_signature(base_project, base_components[ref])
            != _component_signature(target_project, target_components[ref])
        )
    )
    unchanged = tuple(sorted(common_refs - set(changed)))
    return ComponentDelta(
        added=tuple(sorted(set(target_components) - set(base_components))),
        changed=changed,
        removed=tuple(sorted(set(base_components) - set(target_components))),
        unchanged=unchanged,
    )


def _effective_connection_color(
    project: PinoutProject,
    connection: dict[str, object],
) -> str:
    explicit_color = connection.get("color")
    connection_type = str(connection.get("type", "default"))
    return str(
        explicit_color
        or project.color_map.get(connection_type, project.color_map["default"])
    )


def _graph_edges(project: PinoutProject) -> tuple[GraphEdge, ...]:
    edges = []
    for connection_index, connection in enumerate(project.connections):
        connection_type = str(connection.get("type", "default"))
        edges.append(
            GraphEdge(
                connection_index=connection_index,
                start_coordinate=project.pin_positions[connection["from"]],
                end_coordinate=project.pin_positions[connection["to"]],
                from_pin=str(connection["from"]),
                to_pin=str(connection["to"]),
                style=(
                    connection_type,
                    _effective_connection_color(project, connection),
                ),
            )
        )
    return tuple(edges)


def analyze_connection_deltas(
    base_project: PinoutProject,
    target_project: PinoutProject,
) -> ConnectionDelta:
    """Compare wiring as a multigraph whose nodes are physical coordinates."""
    base_by_coordinates: dict[
        tuple[tuple[float, float], tuple[float, float]],
        list[GraphEdge],
    ] = defaultdict(list)
    target_by_coordinates: dict[
        tuple[tuple[float, float], tuple[float, float]],
        list[GraphEdge],
    ] = defaultdict(list)
    for edge in _graph_edges(base_project):
        base_by_coordinates[edge.coordinate_key].append(edge)
    for edge in _graph_edges(target_project):
        target_by_coordinates[edge.coordinate_key].append(edge)

    target_status_by_index = {}
    removed_edges = []
    all_coordinate_keys = sorted(set(base_by_coordinates) | set(target_by_coordinates))
    for coordinate_key in all_coordinate_keys:
        unmatched_base = list(base_by_coordinates[coordinate_key])
        unmatched_target = list(target_by_coordinates[coordinate_key])

        for target_edge in tuple(unmatched_target):
            exact_base = next(
                (
                    base_edge
                    for base_edge in unmatched_base
                    if base_edge.style == target_edge.style
                ),
                None,
            )
            if exact_base is None:
                continue
            target_status_by_index[target_edge.connection_index] = "unchanged"
            unmatched_target.remove(target_edge)
            unmatched_base.remove(exact_base)

        while unmatched_base and unmatched_target:
            unmatched_base.pop(0)
            target_edge = unmatched_target.pop(0)
            target_status_by_index[target_edge.connection_index] = "changed"

        for target_edge in unmatched_target:
            target_status_by_index[target_edge.connection_index] = "new"
        removed_edges.extend(unmatched_base)

    return ConnectionDelta(
        target_status_by_index=target_status_by_index,
        removed_edges=tuple(
            sorted(removed_edges, key=lambda edge: edge.connection_index)
        ),
    )


def _local_name(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _style_component_group(group: ET.Element, status: str) -> None:
    group.set("class", f"discrete-component delta-component delta-{status}")
    group.set("data-delta", status)
    if status == "removed":
        group.set("opacity", "0.72")

    for node in group.iter():
        local_name = _local_name(node)
        if local_name == "text":
            node.set("fill", REMOVED_PURPLE if status == "removed" else DELTA_PURPLE)
            node.set("font-weight", "700")
            if status == "removed":
                node.set("text-decoration", "line-through")
            continue
        if node.attrib.get("stroke") in (None, "none"):
            continue
        node.set("stroke", REMOVED_PURPLE if status == "removed" else DELTA_PURPLE)
        existing_width = float(node.attrib.get("stroke-width", "1"))
        node.set(
            "stroke-width",
            f"{max(existing_width, 3.0 if status == 'removed' else 4.0):g}",
        )
        if status == "removed":
            node.set("stroke-dasharray", "8 5")


def _add_text(
    parent: ET.Element,
    content: str,
    *,
    x: float,
    y: float,
    size: float,
    weight: str = "normal",
    fill: str = "#111827",
) -> ET.Element:
    node = ET.SubElement(
        parent,
        f"{SVG_TAG}text",
        {
            "x": f"{x:g}",
            "y": f"{y:g}",
            "font-size": f"{size:g}px",
            "font-family": "sans-serif",
            "font-weight": weight,
            "fill": fill,
        },
    )
    node.text = content
    return node


def _expand_viewbox_up(root: ET.Element, required_top: float) -> None:
    x, y, width, height = (float(value) for value in root.attrib["viewBox"].split())
    if required_top >= y:
        return
    bottom = y + height
    expanded_height = bottom - required_top
    root.set(
        "viewBox",
        f"{x:g} {required_top:g} {width:g} {expanded_height:g}",
    )
    background = next(
        (node for node in root if node.attrib.get("class") == "discrete-background"),
        None,
    )
    if background is not None:
        background.set("y", f"{required_top:g}")
        background.set("height", f"{expanded_height:g}")


def _add_component_delta_legend(
    root: ET.Element,
    components: ComponentDelta,
) -> None:
    group = ET.SubElement(
        root,
        f"{SVG_TAG}g",
        {
            "class": "delta-legend",
            "data-redesign-commit": REDESIGN_COMMIT,
        },
    )
    legend_x = 20.0
    legend_y = -180.0
    legend_width = 1500.0
    legend_height = 105.0
    ET.SubElement(
        group,
        f"{SVG_TAG}rect",
        {
            "x": f"{legend_x:g}",
            "y": f"{legend_y:g}",
            "width": f"{legend_width:g}",
            "height": f"{legend_height:g}",
            "rx": "7",
            "fill": "#ffffff",
            "stroke": "#a855f7",
            "stroke-width": "2",
        },
    )
    _add_text(
        group,
        "84dd4cb REDESIGN DELTA — COMPONENT SIDE",
        x=legend_x + 15,
        y=legend_y + 24,
        size=15,
        weight="700",
        fill=DELTA_PURPLE,
    )
    _add_text(
        group,
        "PURPLE BOLD — INSTALL / REPLACE: "
        + ", ".join((*components.changed, *components.added)),
        x=legend_x + 15,
        y=legend_y + 49,
        size=12,
        weight="700",
        fill=DELTA_PURPLE,
    )
    _add_text(
        group,
        "PURPLE DASHED — REMOVE: R4 at A05-A16; " "DZ2 at A07-A14; R1 at HV08-HV13",
        x=legend_x + 15,
        y=legend_y + 72,
        size=12,
        weight="700",
        fill=REMOVED_PURPLE,
    )
    _add_text(
        group,
        "Dashed ghosts mark vacated positions; in-place swaps are labelled "
        "REPLACES. Unchanged parts retain normal styling.",
        x=legend_x + 15,
        y=legend_y + 94,
        size=11,
    )
    _expand_viewbox_up(root, legend_y - 20)


def _render_component_delta_svg(
    base_project: PinoutProject,
    display_project: PinoutProject,
    components: ComponentDelta,
) -> str:
    target_root = ET.fromstring(generate_discrete_top_svg(display_project))
    base_root = ET.fromstring(generate_discrete_top_svg(base_project))
    target_root.set("data-delta-kind", "component-placement")
    target_root.set("data-redesign-commit", REDESIGN_COMMIT)
    target_root.set("data-redesign-base", REDESIGN_BASE_REF)

    target_groups = {
        group.attrib["data-component"]: group
        for group in target_root.iter(f"{SVG_TAG}g")
        if group.attrib.get("class") == "discrete-component"
    }
    base_groups = {
        group.attrib["data-component"]: group
        for group in base_root.iter(f"{SVG_TAG}g")
        if group.attrib.get("class") == "discrete-component"
    }
    for ref in components.changed:
        _style_component_group(target_groups[ref], "changed")
    for ref in components.added:
        _style_component_group(target_groups[ref], "added")

    base_components = {
        component.ref: component for component in base_project.component_placements
    }
    display_components = {
        component.ref: component for component in display_project.component_placements
    }
    added_by_coordinates = {
        tuple(
            sorted(
                display_project.pin_positions[pin_name]
                for pin_name in display_components[ref].terminals.values()
            )
        ): ref
        for ref in components.added
    }
    replacement_by_removed_ref = {}
    for removed_ref in components.removed:
        removed_coordinates = tuple(
            sorted(
                base_project.pin_positions[pin_name]
                for pin_name in base_components[removed_ref].terminals.values()
            )
        )
        replacement_ref = added_by_coordinates.get(removed_coordinates)
        if replacement_ref is None:
            continue
        replacement_by_removed_ref[removed_ref] = replacement_ref
        replacement_group = target_groups[replacement_ref]
        replacement_group.set("data-replaces", removed_ref)
        value_label = next(
            node
            for node in replacement_group.iter(f"{SVG_TAG}text")
            if node.attrib.get("class") == "discrete-component-value"
        )
        replacement_label = _add_text(
            replacement_group,
            f"REPLACES {removed_ref}",
            x=float(value_label.attrib["x"]),
            y=float(value_label.attrib["y"]) + 8.0,
            size=5.5,
            weight="700",
            fill=REMOVED_PURPLE,
        )
        replacement_label.set("class", "delta-replacement-label")
        replacement_label.set(
            "text-anchor",
            value_label.attrib.get("text-anchor", "middle"),
        )

    root_children = list(target_root)
    first_component_index = next(
        index
        for index, child in enumerate(root_children)
        if child.attrib.get("class") == "discrete-component"
    )
    ghost_refs = [
        ref for ref in components.removed if ref not in replacement_by_removed_ref
    ]
    for offset, ref in enumerate(ghost_refs):
        removed_group = copy.deepcopy(base_groups[ref])
        _style_component_group(removed_group, "removed")
        target_root.insert(first_component_index + offset, removed_group)

    for text_node in target_root.iter(f"{SVG_TAG}text"):
        if text_node.attrib.get("class") == "discrete-title":
            text_node.text = (
                "RP2040-Plus / TMC5160T Plus component delta — " "84dd4cb — top side"
            )
        elif (
            text_node.attrib.get("class") == "discrete-note"
            and text_node.text
            and "use rp2040plus_btt_tmc5160t_plus_y_bottom.svg" in text_node.text
        ):
            text_node.text = (
                "Then flip the board and use "
                f"{BOTTOM_DELTA_FILENAME} for delta wrapping."
            )

    _add_component_delta_legend(target_root, components)
    return ET.tostring(target_root, encoding="unicode")


def _pin_screen_positions(
    root: ET.Element,
    project: PinoutProject,
    waypoint_count: int,
) -> dict[str, tuple[float, float]]:
    circles = list(root.iter(f"{SVG_TAG}circle"))
    pin_circles = circles[waypoint_count : waypoint_count + len(project.pin_positions)]
    if len(pin_circles) != len(project.pin_positions):
        raise ValueError("Could not identify generated bottom-view pin circles")
    return {
        pin_name: (
            float(circle.attrib["cx"]),
            float(circle.attrib["cy"]),
        )
        for pin_name, circle in zip(project.pin_positions, pin_circles, strict=True)
    }


def _screen_positions_by_coordinate(
    project: PinoutProject,
    pin_screen_positions: dict[str, tuple[float, float]],
) -> dict[tuple[float, float], tuple[float, float]]:
    screen_by_coordinate = {}
    for pin_name, coordinate in project.pin_positions.items():
        screen_position = pin_screen_positions[pin_name]
        prior = screen_by_coordinate.setdefault(coordinate, screen_position)
        if prior != screen_position:
            raise ValueError(
                f"Coordinate {coordinate} maps to inconsistent SVG positions"
            )
    return screen_by_coordinate


def _add_removed_wire_overlays(
    root: ET.Element,
    *,
    removed_edges: tuple[GraphEdge, ...],
    screen_by_coordinate: dict[tuple[float, float], tuple[float, float]],
) -> None:
    group = ET.Element(
        f"{SVG_TAG}g",
        {
            "class": "delta-removed-wires",
            "data-delta": "removed",
        },
    )
    for edge in removed_edges:
        start = screen_by_coordinate[edge.start_coordinate]
        end = screen_by_coordinate[edge.end_coordinate]
        ET.SubElement(
            group,
            f"{SVG_TAG}line",
            {
                "class": "delta-wire delta-removed",
                "data-delta": "removed",
                "data-base-connection-index": str(edge.connection_index),
                "data-from": edge.from_pin,
                "data-to": edge.to_pin,
                "x1": f"{start[0]:g}",
                "y1": f"{start[1]:g}",
                "x2": f"{end[0]:g}",
                "y2": f"{end[1]:g}",
                "stroke": REMOVED_PURPLE,
                "stroke-width": "4",
                "stroke-dasharray": "12 8",
                "stroke-linecap": "round",
                "opacity": "0.9",
            },
        )
        for endpoint in (start, end):
            ET.SubElement(
                group,
                f"{SVG_TAG}circle",
                {
                    "class": "delta-removed-endpoint",
                    "cx": f"{endpoint[0]:g}",
                    "cy": f"{endpoint[1]:g}",
                    "r": "9",
                    "fill": "none",
                    "stroke": REMOVED_PURPLE,
                    "stroke-width": "3",
                    "stroke-dasharray": "5 3",
                },
            )

    first_wire_index = next(
        index for index, child in enumerate(root) if _local_name(child) == "line"
    )
    root.insert(first_wire_index, group)


def _add_wiring_delta_legend(
    root: ET.Element,
    connections: ConnectionDelta,
) -> None:
    legend_x = 2840.0
    legend_y = 925.0
    legend_width = 635.0
    legend_height = 180.0
    group = ET.SubElement(
        root,
        f"{SVG_TAG}g",
        {
            "class": "delta-legend",
            "data-redesign-commit": REDESIGN_COMMIT,
        },
    )
    ET.SubElement(
        group,
        f"{SVG_TAG}rect",
        {
            "x": f"{legend_x:g}",
            "y": f"{legend_y:g}",
            "width": f"{legend_width:g}",
            "height": f"{legend_height:g}",
            "rx": "7",
            "fill": "#ffffff",
            "fill-opacity": "0.95",
            "stroke": "#64748b",
            "stroke-width": "2",
        },
    )
    _add_text(
        group,
        "84dd4cb WIRING DELTA — UNDERSIDE / MIRRORED",
        x=legend_x + 15,
        y=legend_y + 25,
        size=14,
        weight="700",
        fill=DELTA_PURPLE,
    )
    _add_text(
        group,
        f"THICK SOLID — ADD / REWRAP: "
        f"{connections.count('new') + connections.count('changed')} connections",
        x=legend_x + 15,
        y=legend_y + 53,
        size=12,
        weight="700",
    )
    _add_text(
        group,
        f"PURPLE DASHED — REMOVE: {len(connections.removed_edges)} connections",
        x=legend_x + 15,
        y=legend_y + 79,
        size=12,
        weight="700",
        fill=REMOVED_PURPLE,
    )
    _add_text(
        group,
        f"DIM THIN — KEEP: {connections.count('unchanged')} connections",
        x=legend_x + 15,
        y=legend_y + 105,
        size=12,
        fill="#475569",
    )
    _add_text(
        group,
        "Follow the labels at both ends of every highlighted edge.",
        x=legend_x + 15,
        y=legend_y + 135,
        size=11,
    )
    _add_text(
        group,
        "Dashed edges are old wraps to pull out; do not re-wrap them.",
        x=legend_x + 15,
        y=legend_y + 158,
        size=11,
        weight="700",
        fill=REMOVED_PURPLE,
    )


def _render_wiring_delta_svg(
    display_project: PinoutProject,
    connections: ConnectionDelta,
) -> str:
    waypoint_solutions = route_problematic_connections(
        display_project.pin_positions,
        display_project.connections,
    )
    root = ET.fromstring(
        generate_routed_svg(
            display_project.pin_positions,
            display_project.connections,
            waypoint_solutions,
            boxes=display_project.boxes,
            flip_x=True,
            version_label=display_project.version_label,
            notes_text=display_project.notes_text,
            color_map=display_project.color_map,
            svg_margins_px=display_project.svg_margins_px,
        )
    )
    root.set("data-delta-kind", "coordinate-graph")
    root.set("data-redesign-commit", REDESIGN_COMMIT)
    root.set("data-redesign-base", REDESIGN_BASE_REF)
    root.set("data-new-connections", str(connections.count("new")))
    root.set("data-changed-connections", str(connections.count("changed")))
    root.set("data-removed-connections", str(len(connections.removed_edges)))
    root.set("data-unchanged-connections", str(connections.count("unchanged")))
    viewbox_x, viewbox_y, viewbox_width, viewbox_height = (
        float(value) for value in root.attrib["viewBox"].split()
    )
    root.insert(
        0,
        ET.Element(
            f"{SVG_TAG}rect",
            {
                "class": "delta-background",
                "x": f"{viewbox_x:g}",
                "y": f"{viewbox_y:g}",
                "width": f"{viewbox_width:g}",
                "height": f"{viewbox_height:g}",
                "fill": "#ffffff",
            },
        ),
    )

    wire_lines = [child for child in root if _local_name(child) == "line"]
    expected_line_count = sum(
        2 if connection_index in waypoint_solutions else 1
        for connection_index in range(len(display_project.connections))
    )
    if len(wire_lines) != expected_line_count:
        raise ValueError(
            f"Expected {expected_line_count} generated wire segments, "
            f"found {len(wire_lines)}"
        )

    line_offset = 0
    for connection_index, connection in enumerate(display_project.connections):
        status = connections.target_status_by_index[connection_index]
        segment_count = 2 if connection_index in waypoint_solutions else 1
        for line in wire_lines[line_offset : line_offset + segment_count]:
            line.set("class", f"delta-wire delta-{status}")
            line.set("data-delta", status)
            line.set("data-connection-index", str(connection_index))
            line.set("data-from", str(connection["from"]))
            line.set("data-to", str(connection["to"]))
            line.set("stroke-linecap", "round")
            if status in {"new", "changed"}:
                line.set("stroke-width", "6")
            else:
                line.set("stroke-width", "1.5")
                line.set("stroke-opacity", "0.28")
        line_offset += segment_count

    circles = list(root.iter(f"{SVG_TAG}circle"))
    waypoint_indices = sorted(waypoint_solutions)
    for connection_index, circle in zip(
        waypoint_indices,
        circles[: len(waypoint_indices)],
        strict=True,
    ):
        status = connections.target_status_by_index[connection_index]
        circle.set("class", f"delta-waypoint delta-{status}")
        circle.set("data-delta", status)
        circle.set("data-connection-index", str(connection_index))
        if status in {"new", "changed"}:
            circle.set("r", "5")
            circle.set("stroke-width", "2")
        else:
            circle.set("opacity", "0.28")

    pin_screen_positions = _pin_screen_positions(
        root,
        display_project,
        len(waypoint_solutions),
    )
    screen_by_coordinate = _screen_positions_by_coordinate(
        display_project,
        pin_screen_positions,
    )
    _add_removed_wire_overlays(
        root,
        removed_edges=connections.removed_edges,
        screen_by_coordinate=screen_by_coordinate,
    )

    for text_node in root.iter(f"{SVG_TAG}text"):
        if text_node.text == "Underside View":
            text_node.text = "84dd4cb Wiring Delta — Underside View"
            text_node.set("fill", DELTA_PURPLE)
            text_node.set("class", "delta-title")
    _add_wiring_delta_legend(root, connections)
    return ET.tostring(root, encoding="unicode")


def _graph_signature(project: PinoutProject) -> tuple:
    return tuple(
        sorted(
            (
                edge.coordinate_key,
                edge.style,
            )
            for edge in _graph_edges(project)
        )
    )


def render_tmc5160t_plus_84dd4cb_delta(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> DeltaRenderResult:
    """Render the two board-rework diagrams for redesign commit 84dd4cb."""
    output_path = Path(output_dir)
    display_project = load_pinout_config(CONFIG_PATH)
    with tempfile.TemporaryDirectory(prefix="tmc5160t-delta-") as temporary_name:
        temporary_directory = Path(temporary_name)
        base_project = _load_revision_project(
            REDESIGN_BASE_REF,
            temporary_directory=temporary_directory,
        )
        target_project = _load_revision_project(
            REDESIGN_COMMIT,
            temporary_directory=temporary_directory,
        )

    if _graph_signature(display_project) != _graph_signature(target_project):
        raise ValueError(
            "Current wiring graph has diverged from redesign commit 84dd4cb; "
            "review the one-off delta baseline before regenerating"
        )

    component_delta = analyze_component_deltas(base_project, target_project)
    connection_delta = analyze_connection_deltas(base_project, target_project)
    top_path = write_svg(
        _render_component_delta_svg(
            base_project,
            display_project,
            component_delta,
        ),
        output_path / TOP_DELTA_FILENAME,
    )
    bottom_path = write_svg(
        _render_wiring_delta_svg(display_project, connection_delta),
        output_path / BOTTOM_DELTA_FILENAME,
    )
    print(
        "component_delta="
        f"added:{len(component_delta.added)},"
        f"changed:{len(component_delta.changed)},"
        f"removed:{len(component_delta.removed)},"
        f"unchanged:{len(component_delta.unchanged)}"
    )
    print(
        "connection_delta="
        f"new:{connection_delta.count('new')},"
        f"changed:{connection_delta.count('changed')},"
        f"removed:{len(connection_delta.removed_edges)},"
        f"unchanged:{connection_delta.count('unchanged')}"
    )
    print(top_path)
    print(bottom_path)
    return DeltaRenderResult(
        top_path=top_path,
        bottom_path=bottom_path,
        components=component_delta,
        connections=connection_delta,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the one-off 84dd4cb board-rework delta diagrams."
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for both SVG files.",
    )
    args = parser.parse_args(argv)
    render_tmc5160t_plus_84dd4cb_delta(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
