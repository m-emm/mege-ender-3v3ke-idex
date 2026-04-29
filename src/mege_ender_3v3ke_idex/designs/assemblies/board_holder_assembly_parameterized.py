"""Parameterized board holder assembly with rigid base and TPU cover."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from mege_ender_3v3ke_idex.designs.plug_and_hole import create_plug
from mege_ender_3v3ke_idex.designs.sil_dil import (
    create_dil_board,
    create_sil,
    create_sil_board,
    default_top_pin_length,
    dil_pitch,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_length,
    wire_wrap_pin_side,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

BIG_THING = 500
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"


@dataclass(frozen=True)
class BoardSpec:
    name: str
    board_type: str
    params: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BoardPlacementSpec:
    instance_name: str
    board_name: str
    align_to: str | None = None
    x_alignment: Alignment | None = None
    y_alignment: Alignment | None = None
    stack_gap: float = 0.0
    stack_gap_rastered: float = 0.0
    offset_x: float = 0.0
    offset_y: float = 0.0


@dataclass(frozen=True)
class PinLineSpec:
    instance_name: str
    pin_count: int
    border_alignment: Alignment
    along_border_alignment: Alignment = Alignment.CENTER
    along_border_offset: float = 0.0
    along_border_offset_rastered: float = 0.0
    params: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlugSpec:
    corner_inset: float = 5.0
    positions: Sequence[tuple[float, float]] | None = None
    plug_diameter: float = 7.0
    plug_angle_deg: float = 5.0
    plug_height: float = 4.0
    plug_wall_thickness: float = 1.2
    plug_base_thickness: float = 0.8
    plug_slit_width: float | None = 0.5
    fillet_radius: float = 0.5
    plug_lip_height: float | None = 0.8
    plug_lip_size: float | None = 0.5
    plug_lip_top_gap: float | None = 1.0
    no_inner_hole: bool = False
    hole_slack: float = 0.1


def _coerce_alignment(value):
    if value is None or isinstance(value, Alignment):
        return value
    if isinstance(value, str):
        try:
            return getattr(Alignment, value)
        except AttributeError as exc:
            raise ValueError(f"Unknown alignment '{value}'.") from exc
    raise TypeError(f"Unsupported alignment value {value!r}.")


def _coerce_board_spec(value):
    if isinstance(value, BoardSpec):
        return value
    if isinstance(value, Mapping):
        return BoardSpec(
            name=str(value["name"]),
            board_type=str(value["board_type"]),
            params=dict(value.get("params", {})),
        )
    raise TypeError(f"Unsupported board spec value {value!r}.")


def _coerce_board_placement_spec(value):
    if isinstance(value, BoardPlacementSpec):
        return value
    if isinstance(value, Mapping):
        return BoardPlacementSpec(
            instance_name=str(value["instance_name"]),
            board_name=str(value["board_name"]),
            align_to=value.get("align_to"),
            x_alignment=_coerce_alignment(value.get("x_alignment")),
            y_alignment=_coerce_alignment(value.get("y_alignment")),
            stack_gap=float(value.get("stack_gap", 0.0)),
            stack_gap_rastered=float(value.get("stack_gap_rastered", 0.0)),
            offset_x=float(value.get("offset_x", 0.0)),
            offset_y=float(value.get("offset_y", 0.0)),
        )
    raise TypeError(f"Unsupported board placement value {value!r}.")


def _coerce_pin_line_spec(value):
    if isinstance(value, PinLineSpec):
        return value
    if isinstance(value, Mapping):
        return PinLineSpec(
            instance_name=str(value["instance_name"]),
            pin_count=int(value["pin_count"]),
            border_alignment=_coerce_alignment(value["border_alignment"]),
            along_border_alignment=_coerce_alignment(
                value.get("along_border_alignment", Alignment.CENTER)
            ),
            along_border_offset=float(value.get("along_border_offset", 0.0)),
            along_border_offset_rastered=float(
                value.get("along_border_offset_rastered", 0.0)
            ),
            params=dict(value.get("params", {})),
        )
    raise TypeError(f"Unsupported pin line spec value {value!r}.")


def _coerce_plug_spec(value):
    if value is None or isinstance(value, PlugSpec):
        return value
    if isinstance(value, Mapping):
        return PlugSpec(**dict(value))
    raise TypeError(f"Unsupported plug spec value {value!r}.")


def _bbox_to_list(bbox):
    return [[bbox[0][0], bbox[0][1], bbox[0][2]], [bbox[1][0], bbox[1][1], bbox[1][2]]]


def _fuse_parts(parts):
    if not parts:
        raise ValueError("Need at least one part to fuse.")

    fused = parts[0]
    for part in parts[1:]:
        fused = fused.fuse(part)
    return fused


def _create_board_solid(
    *,
    board_x_size,
    board_y_size,
    board_thickness,
    board_corner_radius=None,
):
    if board_corner_radius is None:
        return create_box(board_x_size, board_y_size, board_thickness)
    return create_filleted_box(
        board_x_size,
        board_y_size,
        board_thickness,
        board_corner_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )


def _create_dil_board_outline(params):
    x_overhang_in_pins = params.get("x_overhang_in_pins", 0.0)
    y_overhang_in_pins = params.get("y_overhang_in_pins", 0.5)

    board_x_size = (
        params["int_x_distance"] * dil_pitch + 2.5 + 2 * x_overhang_in_pins * dil_pitch
    )
    board_y_size = params["num_y_pins"] * dil_pitch + 2 * y_overhang_in_pins * dil_pitch
    board_plain = _create_board_solid(
        board_x_size=board_x_size,
        board_y_size=board_y_size,
        board_thickness=params["board_thickness"],
        board_corner_radius=params.get("board_corner_radius"),
    )
    board_cutter = _create_board_solid(
        board_x_size=board_x_size + 2 * params.get("board_cutter_slack", 0.0),
        board_y_size=board_y_size + 2 * params.get("board_cutter_slack", 0.0),
        board_thickness=params["board_thickness"]
        + 2 * params.get("board_cutter_slack", 0.0),
        board_corner_radius=params.get("board_corner_radius"),
    )
    board_cutter = align(board_cutter, board_plain, Alignment.CENTER)
    return board_plain, board_cutter


def _create_sil_board_outline(params):
    y_overhang_in_pins = params.get("y_overhang_in_pins", 0.5)

    board_x_size = params["board_x_size_in_pins"] * dil_pitch
    board_y_size = params["num_y_pins"] * dil_pitch + 2 * y_overhang_in_pins * dil_pitch
    board_plain = _create_board_solid(
        board_x_size=board_x_size,
        board_y_size=board_y_size,
        board_thickness=params["board_thickness"],
        board_corner_radius=params.get("board_corner_radius"),
    )
    board_cutter = _create_board_solid(
        board_x_size=board_x_size + 2 * params.get("board_cutter_slack", 0.0),
        board_y_size=board_y_size + 2 * params.get("board_cutter_slack", 0.0),
        board_thickness=params["board_thickness"]
        + 2 * params.get("board_cutter_slack", 0.0),
        board_corner_radius=params.get("board_corner_radius"),
    )
    board_cutter = align(board_cutter, board_plain, Alignment.CENTER)
    return board_plain, board_cutter


def _create_catalog_board(spec: BoardSpec):
    params = dict(spec.params)
    board_type = spec.board_type.lower()

    if board_type == "dil":
        raw = create_dil_board(**params)
        board_plain, _ = _create_dil_board_outline(params)
        pins_name = "dil"
        pin_row_edges = ["LEFT", "RIGHT"]
        y_overhang_in_pins = params.get("y_overhang_in_pins", 0.5)
    elif board_type == "sil":
        raw = create_sil_board(**params)
        board_plain, _ = _create_sil_board_outline(params)
        pins_name = "sil"
        pin_row_edges = ["RIGHT"]
        y_overhang_in_pins = params.get("y_overhang_in_pins", 0.5)
    else:
        raise ValueError(f"Unsupported board_type '{spec.board_type}'.")

    normalized = raw.copy()
    board_part = normalized.get_follower_part_by_name("board")
    pins_part = normalized.get_follower_part_by_name(pins_name)

    if "pins" not in normalized.follower_indices_by_name:
        normalized.add_named_follower(pins_part, "pins")

    if "board_cutters" not in normalized.cutter_indices_by_name:
        if not normalized.cutters:
            raise ValueError(f"Board '{spec.name}' does not expose any cutters.")
        normalized.cutter_indices_by_name["board_cutters"] = 0

    normalized.additional_data.update(
        {
            "board_name": spec.name,
            "board_type": board_type,
            "num_y_pins": int(params["num_y_pins"]),
            "y_overhang_in_pins": float(y_overhang_in_pins),
            "pin_row_edges": pin_row_edges,
            "pins_follower_name": pins_name,
            "board_bbox": _bbox_to_list(get_bounding_box(board_part)),
            "board_outline_bbox": _bbox_to_list(get_bounding_box(board_plain)),
        }
    )

    return normalized


def _normalize_board_catalog(board_catalog):
    if isinstance(board_catalog, Mapping):
        specs = board_catalog.values()
    else:
        specs = board_catalog

    normalized = {}
    for spec in specs:
        spec = _coerce_board_spec(spec)
        if spec.name in normalized:
            raise ValueError(f"Duplicate board spec name '{spec.name}'.")
        normalized[spec.name] = _create_catalog_board(spec)
    return normalized


def _is_x_stack_alignment(alignment):
    return alignment in (Alignment.STACK_LEFT, Alignment.STACK_RIGHT)


def _is_y_stack_alignment(alignment):
    return alignment in (Alignment.STACK_FRONT, Alignment.STACK_BACK)


def _apply_x_alignment(part, target, alignment, stack_gap):
    if alignment is None:
        return part
    if alignment == Alignment.CENTER:
        return align(part, target, alignment, axes=[0])
    return align(
        part,
        target,
        alignment,
        stack_gap=stack_gap if _is_x_stack_alignment(alignment) else 0.0,
    )


def _apply_y_alignment(part, target, alignment, stack_gap):
    if alignment is None:
        return part
    if alignment == Alignment.CENTER:
        return align(part, target, alignment, axes=[1])
    return align(
        part,
        target,
        alignment,
        stack_gap=stack_gap if _is_y_stack_alignment(alignment) else 0.0,
    )


def _place_board_instances(board_catalog, board_placements, raster_pitch):
    if not board_placements:
        raise ValueError("At least one board placement is required.")

    placed_by_name = {}
    ordered_instances = []
    previous_instance_name = None

    for placement in board_placements:
        placement = _coerce_board_placement_spec(placement)
        if placement.instance_name in placed_by_name:
            raise ValueError(
                f"Duplicate board instance name '{placement.instance_name}'."
            )
        if placement.board_name not in board_catalog:
            raise KeyError(
                f"Unknown board_name '{placement.board_name}' for instance "
                f"'{placement.instance_name}'."
            )

        placed = board_catalog[placement.board_name].copy()
        stack_gap = placement.stack_gap + placement.stack_gap_rastered * raster_pitch

        target_name = placement.align_to
        if target_name is None and previous_instance_name is not None:
            target_name = previous_instance_name

        if target_name is None:
            placed = align(placed, None, Alignment.CENTER, axes=[0, 1])
        else:
            if target_name not in placed_by_name:
                raise KeyError(
                    f"Board instance '{placement.instance_name}' references unknown "
                    f"align_to target '{target_name}'."
                )
            target = placed_by_name[target_name]
            placed = _apply_x_alignment(
                placed, target, placement.x_alignment, stack_gap
            )
            placed = _apply_y_alignment(
                placed, target, placement.y_alignment, stack_gap
            )

        placed = translate(placement.offset_x, placement.offset_y, 0)(placed)
        placed.additional_data.update(
            {
                "instance_name": placement.instance_name,
                "board_name": placement.board_name,
                "align_to": target_name,
                "stack_gap": stack_gap,
            }
        )

        placed_by_name[placement.instance_name] = placed
        ordered_instances.append(placement.instance_name)
        previous_instance_name = placement.instance_name

    return placed_by_name, ordered_instances


def _create_pin_line(spec: PinLineSpec):
    pin_line = create_sil(num_y_pins=spec.pin_count, **dict(spec.params))
    if spec.border_alignment in (Alignment.FRONT, Alignment.BACK):
        pin_line = rotate(90)(pin_line)
    pin_line.additional_data.update(
        {
            "instance_name": spec.instance_name,
            "pin_count": spec.pin_count,
            "border_alignment": spec.border_alignment.name,
            "along_border_alignment": spec.along_border_alignment.name,
        }
    )
    return pin_line


def _place_pin_lines(pin_lines, base_plate, raster_pitch):
    placed = {}
    ordered_names = []

    for spec in pin_lines:
        spec = _coerce_pin_line_spec(spec)
        if spec.instance_name in placed:
            raise ValueError(
                f"Duplicate pin line instance name '{spec.instance_name}'."
            )

        pin_line = _create_pin_line(spec)
        pin_line = align(pin_line, base_plate, Alignment.TOP)
        pin_line = align(pin_line, base_plate, spec.border_alignment)
        pin_line = align(pin_line, base_plate, spec.along_border_alignment)

        along_border_offset = (
            spec.along_border_offset + spec.along_border_offset_rastered * raster_pitch
        )
        if spec.border_alignment in (Alignment.LEFT, Alignment.RIGHT):
            pin_line = translate(0, along_border_offset, 0)(pin_line)
        else:
            pin_line = translate(along_border_offset, 0, 0)(pin_line)

        placed[spec.instance_name] = pin_line
        ordered_names.append(spec.instance_name)

    return placed, ordered_names


def _create_cut_box_from_xy(
    x_min,
    x_max,
    y_min,
    y_max,
    *,
    z_min,
    z_height,
):
    return create_box(
        x_max - x_min,
        y_max - y_min,
        z_height,
        origin=(x_min, y_min, z_min),
    )


def _resolve_strap_definitions(board_instance, strap_pin_indices):
    board_part = board_instance.get_follower_part_by_name("board")
    board_bbox = get_bounding_box(board_part)

    if strap_pin_indices is None:
        return [
            {
                "pin_index": None,
                "center_y": (board_bbox[0][1] + board_bbox[1][1]) / 2,
            }
        ]

    y_overhang_in_pins = board_instance.additional_data["y_overhang_in_pins"]
    num_y_pins = board_instance.additional_data["num_y_pins"]
    strap_definitions = []
    for pin_index in strap_pin_indices:
        if pin_index < 0 or pin_index >= num_y_pins:
            raise ValueError(
                f"Cross strap pin index {pin_index} is outside the valid range "
                f"0..{num_y_pins - 1}."
            )
        center_y = (
            board_bbox[0][1]
            + y_overhang_in_pins * dil_pitch
            + (pin_index + 0.5) * dil_pitch
        )
        strap_definitions.append({"pin_index": int(pin_index), "center_y": center_y})

    return strap_definitions


def _create_tpu_cover(
    *,
    base_plate,
    board_instances,
    ordered_board_names,
    placed_pin_lines,
    tpu_cover_thickness,
    tpu_cover_gap_above_base,
    tpu_cover_pin_overlap_in_pitches,
    tpu_cover_cross_strap_pin_indices,
    tpu_cover_cross_strap_width_in_pitches,
    big_thing,
):
    base_bbox = get_bounding_box(base_plate)
    cover_z_min = base_bbox[1][2] + tpu_cover_gap_above_base
    cover = create_box(
        base_bbox[1][0] - base_bbox[0][0],
        base_bbox[1][1] - base_bbox[0][1],
        tpu_cover_thickness,
        origin=(base_bbox[0][0], base_bbox[0][1], cover_z_min),
    )

    overlap_mm = tpu_cover_pin_overlap_in_pitches * dil_pitch
    strap_width = tpu_cover_cross_strap_width_in_pitches * dil_pitch

    strap_parts = []
    strap_metadata = []

    for board_name in ordered_board_names:
        board_instance = board_instances[board_name]
        board_part = board_instance.get_follower_part_by_name("board")
        board_bbox = get_bounding_box(board_part)
        x_min = board_bbox[0][0]
        x_max = board_bbox[1][0]
        y_min = board_bbox[0][1]
        y_max = board_bbox[1][1]

        for edge_name in board_instance.additional_data["pin_row_edges"]:
            if edge_name == "LEFT":
                x_min += overlap_mm
            elif edge_name == "RIGHT":
                x_max -= overlap_mm

        if x_max <= x_min:
            raise ValueError(
                f"Cover overlap left no window width for board '{board_name}'."
            )

        board_window = _create_cut_box_from_xy(
            x_min,
            x_max,
            y_min,
            y_max,
            z_min=cover_z_min - 1.0,
            z_height=tpu_cover_thickness + 2.0,
        )
        cover = cover.cut(board_window)

        for strap_index, strap_definition in enumerate(
            _resolve_strap_definitions(
                board_instance,
                tpu_cover_cross_strap_pin_indices,
            )
        ):
            strap = create_box(
                x_max - x_min,
                strap_width,
                tpu_cover_thickness,
                origin=(
                    x_min,
                    strap_definition["center_y"] - strap_width / 2,
                    cover_z_min,
                ),
            )
            cover = cover.fuse(strap)
            strap_parts.append(strap)
            strap_metadata.append(
                {
                    "board_instance": board_name,
                    "strap_index": strap_index,
                    "pin_index": strap_definition["pin_index"],
                    "center_y": strap_definition["center_y"],
                    "width": strap_width,
                    "bbox": _bbox_to_list(get_bounding_box(strap)),
                }
            )

    for pin_line in placed_pin_lines.values():
        pin_line_bbox = get_bounding_box(pin_line.leaders_followers_fused())
        pin_line_window = _create_cut_box_from_xy(
            pin_line_bbox[0][0],
            pin_line_bbox[1][0],
            pin_line_bbox[0][1],
            pin_line_bbox[1][1],
            z_min=cover_z_min - 1.0,
            z_height=tpu_cover_thickness + 2.0,
        )
        cover = cover.cut(pin_line_window)

    return cover, strap_parts, strap_metadata


def _move_part_center_xy(part, x_pos, y_pos):
    center = get_bounding_box_center(part)
    return translate(x_pos - center[0], y_pos - center[1], 0)(part)


def _place_z_by_top(part, z_top):
    bbox = get_bounding_box(part)
    return translate(0, 0, z_top - bbox[1][2])(part)


def _create_cover_plugs(cover, plug_spec, big_thing):
    cover_bbox = get_bounding_box(cover)

    if plug_spec.positions is None:
        positions = [
            (
                cover_bbox[0][0] + plug_spec.corner_inset,
                cover_bbox[0][1] + plug_spec.corner_inset,
            ),
            (
                cover_bbox[1][0] - plug_spec.corner_inset,
                cover_bbox[0][1] + plug_spec.corner_inset,
            ),
            (
                cover_bbox[1][0] - plug_spec.corner_inset,
                cover_bbox[1][1] - plug_spec.corner_inset,
            ),
            (
                cover_bbox[0][0] + plug_spec.corner_inset,
                cover_bbox[1][1] - plug_spec.corner_inset,
            ),
        ]
    else:
        positions = list(plug_spec.positions)

    cover_with_plugs = cover
    plug_parts = []
    hole_cutters = []

    for x_pos, y_pos in positions:
        plug = create_plug(
            plug_diameter=plug_spec.plug_diameter,
            plug_angle_deg=plug_spec.plug_angle_deg,
            plug_height=plug_spec.plug_height,
            plug_wall_thickness=plug_spec.plug_wall_thickness,
            plug_base_thickness=plug_spec.plug_base_thickness,
            plug_slit_width=plug_spec.plug_slit_width,
            fillet_radius=plug_spec.fillet_radius,
            plug_lip_height=plug_spec.plug_lip_height,
            plug_lip_size=plug_spec.plug_lip_size,
            plug_lip_top_gap=plug_spec.plug_lip_top_gap,
            no_inner_hole=plug_spec.no_inner_hole,
        )
        plug = rotate(180, axis=(1, 0, 0))(plug)
        plug = _move_part_center_xy(plug, x_pos, y_pos)
        plug = _place_z_by_top(plug, cover_bbox[0][2])

        cover_with_plugs = cover_with_plugs.fuse(plug)
        plug_parts.append(plug)

        hole_cutter = create_cylinder(
            plug_spec.plug_diameter / 2 + plug_spec.hole_slack,
            big_thing,
        )
        # Match create_plugged_plate(): the counter hole is a slackened cylinder
        # centered on the full plug body so it cuts all the way through the base.
        hole_cutter = align(hole_cutter, plug, Alignment.CENTER)
        hole_cutters.append(hole_cutter)

    return cover_with_plugs, plug_parts, hole_cutters, positions


def _add_non_production_board_visuals(assembly, board_instance, prefix):
    assembly.add_named_non_production_part(
        board_instance.get_follower_part_by_name("board"),
        f"{prefix}_board",
    )
    assembly.add_named_non_production_part(
        board_instance.get_follower_part_by_name("pins"),
        f"{prefix}_pins",
    )
    return assembly


def _add_non_production_pin_line_visual(assembly, pin_line, prefix):
    assembly.add_named_non_production_part(
        pin_line.leaders_followers_fused(),
        prefix,
    )
    return assembly


def create_board_holder_assembly_parameterized(
    *,
    board_catalog,
    board_placements,
    pin_lines=None,
    big_thing=BIG_THING,
    raster_pitch=dil_pitch,
    base_plate_thickness=3.1,
    board_z_offset=0.005,
    base_border=7.0,
    base_border_left=None,
    base_border_right=None,
    base_border_front=None,
    base_border_back=None,
    tpu_cover_thickness=1.0,
    tpu_cover_gap_above_base=0.0,
    tpu_cover_pin_overlap_in_pitches=0.5,
    tpu_cover_cross_strap_pin_indices=None,
    tpu_cover_cross_strap_width_in_pitches=1.0,
    plug_spec=None,
) -> LeaderFollowersCuttersPart:
    if pin_lines is None:
        pin_lines = []
    plug_spec = _coerce_plug_spec(plug_spec)
    if plug_spec is None:
        plug_spec = PlugSpec()

    board_catalog_by_name = _normalize_board_catalog(board_catalog)
    board_instances, ordered_board_names = _place_board_instances(
        board_catalog_by_name,
        board_placements,
        raster_pitch,
    )

    board_visuals = [
        board_instances[name].leaders_followers_fused() for name in ordered_board_names
    ]
    board_visuals_fused = _fuse_parts(board_visuals)
    board_visuals_bbox = get_bounding_box(board_visuals_fused)

    base_border_left = base_border if base_border_left is None else base_border_left
    base_border_right = base_border if base_border_right is None else base_border_right
    base_border_front = base_border if base_border_front is None else base_border_front
    base_border_back = base_border if base_border_back is None else base_border_back

    base_plate = create_box(
        (board_visuals_bbox[1][0] - board_visuals_bbox[0][0])
        + base_border_left
        + base_border_right,
        (board_visuals_bbox[1][1] - board_visuals_bbox[0][1])
        + base_border_front
        + base_border_back,
        base_plate_thickness,
        origin=(
            board_visuals_bbox[0][0] - base_border_left,
            board_visuals_bbox[0][1] - base_border_front,
            board_z_offset - base_plate_thickness,
        ),
    )

    base_board_cutters = []
    base_plate_with_board_cutouts = base_plate
    for board_name in ordered_board_names:
        board_instance = board_instances[board_name]
        base_plate_with_board_cutouts = board_instance.use_as_cutter_on(
            base_plate_with_board_cutouts
        )
        base_board_cutters.extend(board_instance.cutters)

    placed_pin_lines, ordered_pin_line_names = _place_pin_lines(
        pin_lines,
        base_plate_with_board_cutouts,
        raster_pitch,
    )

    base_pin_line_cutters = []
    base_plate_with_all_cutouts = base_plate_with_board_cutouts
    for pin_line_name in ordered_pin_line_names:
        pin_line = placed_pin_lines[pin_line_name]
        base_plate_with_all_cutouts = pin_line.use_as_cutter_on(
            base_plate_with_all_cutouts
        )
        base_pin_line_cutters.extend(pin_line.cutters)

    tpu_cover, strap_parts, strap_metadata = _create_tpu_cover(
        base_plate=base_plate_with_all_cutouts,
        board_instances=board_instances,
        ordered_board_names=ordered_board_names,
        placed_pin_lines=placed_pin_lines,
        tpu_cover_thickness=tpu_cover_thickness,
        tpu_cover_gap_above_base=tpu_cover_gap_above_base,
        tpu_cover_pin_overlap_in_pitches=tpu_cover_pin_overlap_in_pitches,
        tpu_cover_cross_strap_pin_indices=tpu_cover_cross_strap_pin_indices,
        tpu_cover_cross_strap_width_in_pitches=tpu_cover_cross_strap_width_in_pitches,
        big_thing=big_thing,
    )
    tpu_cover, plug_parts, plug_hole_cutters, plug_positions = _create_cover_plugs(
        tpu_cover,
        plug_spec,
        big_thing,
    )

    if plug_hole_cutters:
        plug_hole_cutters_fused = _fuse_parts(plug_hole_cutters)
        final_base_plate = base_plate_with_all_cutouts.cut(plug_hole_cutters_fused)
    else:
        plug_hole_cutters_fused = None
        final_base_plate = base_plate_with_all_cutouts

    assembly = LeaderFollowersCuttersPart(final_base_plate)
    assembly.add_named_follower(tpu_cover, "tpu_cover")

    if plug_hole_cutters_fused is not None:
        assembly.add_named_cutter(plug_hole_cutters_fused, "cover_plug_holes")

    if base_board_cutters:
        assembly.add_named_cutter(_fuse_parts(base_board_cutters), "base_board_cutters")

    if base_pin_line_cutters:
        assembly.add_named_cutter(
            _fuse_parts(base_pin_line_cutters),
            "base_pin_line_cutters",
        )

    for board_name in ordered_board_names:
        board_instance = board_instances[board_name]
        assembly = _add_non_production_board_visuals(
            assembly,
            board_instance,
            board_name,
        )

    for pin_line_name in ordered_pin_line_names:
        pin_line = placed_pin_lines[pin_line_name]
        assembly = _add_non_production_pin_line_visual(
            assembly,
            pin_line,
            pin_line_name,
        )

    board_instance_bboxes = {}
    for board_name in ordered_board_names:
        board_instance_bboxes[board_name] = _bbox_to_list(
            get_bounding_box(
                assembly.get_named_non_production_part(f"{board_name}_board")
            )
        )

    pin_line_bboxes = {}
    for pin_line_name in ordered_pin_line_names:
        pin_line_bboxes[pin_line_name] = _bbox_to_list(
            get_bounding_box(assembly.get_named_non_production_part(pin_line_name))
        )

    assembly.additional_data.update(
        {
            "board_instance_order": ordered_board_names,
            "board_instance_bboxes": board_instance_bboxes,
            "pin_line_order": ordered_pin_line_names,
            "pin_line_bboxes": pin_line_bboxes,
            "tpu_cover_straps": strap_metadata,
            "plug_positions": [[x, y] for x, y in plug_positions],
            "base_bbox": _bbox_to_list(get_bounding_box(assembly.leader)),
        }
    )

    return assembly


def main():
    logging.basicConfig(level=logging.INFO)

    parts = PartList()

    board_catalog = [
        BoardSpec(
            name="pico_board",
            board_type="dil",
            params={
                "int_x_distance": 18,
                "num_y_pins": 20,
                "board_thickness": 1.6,
                "board_corner_radius": 2.0,
                "top_pin_length": default_top_pin_length,
                "pin_length": wire_wrap_pin_length,
                "pin_side": wire_wrap_pin_side,
                "base_thickness": wire_wrap_pin_base_thickness,
                "board_cutter_slack": 0.3,
                "base_cutter_slack": 0.3,
            },
        ),
        BoardSpec(
            name="tmc_board",
            board_type="sil",
            params={
                "num_y_pins": 8,
                "board_x_size_in_pins": 6,
                "board_thickness": 1.6,
                "board_corner_radius": 1.0,
                "top_pin_length": default_top_pin_length,
                "pin_length": wire_wrap_pin_length,
                "pin_side": wire_wrap_pin_side,
                "base_thickness": wire_wrap_pin_base_thickness,
                "board_cutter_slack": 0.3,
                "base_cutter_slack": 0.3,
            },
        ),
    ]

    board_placements = [
        BoardPlacementSpec(
            instance_name="pico_board",
            board_name="pico_board",
        ),
        BoardPlacementSpec(
            instance_name="tmc_board_1",
            board_name="tmc_board",
            x_alignment=Alignment.STACK_LEFT,
            stack_gap_rastered=5,
        ),
    ]

    pin_lines = [
        PinLineSpec(
            instance_name="right_pin_line",
            pin_count=10,
            border_alignment=Alignment.RIGHT,
            along_border_alignment=Alignment.CENTER,
            params={
                "top_pin_length": default_top_pin_length,
                "pin_length": wire_wrap_pin_length,
                "pin_side": wire_wrap_pin_side,
                "base_thickness": wire_wrap_pin_base_thickness,
                "base_cutter_slack": 0.3,
            },
        ),
        PinLineSpec(
            instance_name="back_pin_line",
            pin_count=24,
            border_alignment=Alignment.BACK,
            along_border_alignment=Alignment.CENTER,
            params={
                "top_pin_length": default_top_pin_length,
                "pin_length": wire_wrap_pin_length,
                "pin_side": wire_wrap_pin_side,
                "base_thickness": wire_wrap_pin_base_thickness,
                "base_cutter_slack": 0.3,
            },
        ),
    ]

    assembly = create_board_holder_assembly_parameterized(
        board_catalog=board_catalog,
        board_placements=board_placements,
        pin_lines=pin_lines,
        tpu_cover_cross_strap_pin_indices=[2, 7],
    )

    parts.add(assembly.leader, "board_holder_base", flip=False)
    parts.add(assembly.get_follower_part_by_name("tpu_cover"), "board_holder_tpu_cover")

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
    )


if __name__ == "__main__":
    main()
