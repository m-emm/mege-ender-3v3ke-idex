"""Generate a fitted electronics base plate from a mege-circuits pinout."""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from mege_circuits.simple import PinoutDownholderKind, load_pinout_config
from mege_ender_3v3ke_idex.designs.assemblies.pin_header_board_helpers import (
    create_sil_header,
    create_sil_pin_line_clamp,
)
from shellforgepy.simple import *


@dataclass(frozen=True)
class ComponentProfile:
    """Assembly-supplied physical body dimensions around a pin envelope."""

    left_margin_mm: float
    right_margin_mm: float
    top_margin_mm: float
    bottom_margin_mm: float
    body_height_mm: float
    clamp_surface_height_mm: float
    pass_through_style: str


@dataclass(frozen=True)
class ComponentEnvelope:
    """One resolved component footprint in the pinout source coordinate system."""

    component_id: str
    minimum_x_mm: float
    minimum_y_mm: float
    maximum_x_mm: float
    maximum_y_mm: float
    body_height_mm: float | None
    box_id: str | None

    @property
    def width_mm(self) -> float:
        return self.maximum_x_mm - self.minimum_x_mm

    @property
    def depth_mm(self) -> float:
        return self.maximum_y_mm - self.minimum_y_mm


@dataclass(frozen=True)
class DownholderPlan:
    """One assembly-owned retainer in the source X/Y coordinate system."""

    component_id: str
    kind: PinoutDownholderKind
    minimum_x_mm: float
    minimum_y_mm: float
    maximum_x_mm: float
    maximum_y_mm: float
    screw_centers_mm: tuple[tuple[float, float], ...]


def resolve_component_profiles(
    raw_profiles: Mapping[str, Any],
) -> dict[str, ComponentProfile]:
    """Normalize the mechanical profile registry supplied by the assembly."""

    if not isinstance(raw_profiles, Mapping):
        raise ValueError("pinout_base_plate_component_profiles must be a mapping")

    field_names = (
        "left_margin_mm",
        "right_margin_mm",
        "top_margin_mm",
        "bottom_margin_mm",
        "body_height_mm",
    )
    allowed_pass_through_styles = {"individual_holes", "row_slot"}
    profiles: dict[str, ComponentProfile] = {}
    for component_type, raw_profile in raw_profiles.items():
        if not isinstance(raw_profile, Mapping):
            raise ValueError(f"Component profile {component_type!r} must be a mapping")
        required_fields = (*field_names, "pass_through_style")
        missing_fields = [name for name in required_fields if name not in raw_profile]
        if missing_fields:
            raise ValueError(
                f"Component profile {component_type!r} is missing: {missing_fields}"
            )
        values = {name: float(raw_profile[name]) for name in field_names}
        if any(values[name] < 0 for name in field_names[:-1]):
            raise ValueError(
                f"Component profile {component_type!r} margins must be non-negative"
            )
        if values["body_height_mm"] <= 0:
            raise ValueError(
                f"Component profile {component_type!r} body_height_mm must be positive"
            )
        clamp_surface_height_mm = float(
            raw_profile.get("clamp_surface_height_mm", values["body_height_mm"])
        )
        if clamp_surface_height_mm <= 0:
            raise ValueError(
                f"Component profile {component_type!r} "
                "clamp_surface_height_mm must be positive"
            )
        pass_through_style = str(raw_profile["pass_through_style"]).strip()
        if pass_through_style not in allowed_pass_through_styles:
            raise ValueError(
                f"Component profile {component_type!r} pass_through_style must be "
                f"one of {sorted(allowed_pass_through_styles)}"
            )
        profiles[str(component_type)] = ComponentProfile(
            **values,
            clamp_surface_height_mm=clamp_surface_height_mm,
            pass_through_style=pass_through_style,
        )
    return profiles


def resolve_component_envelopes(
    *,
    pinout_project,
    raster_pitch_mm: float,
    component_profiles: Mapping[str, ComponentProfile],
) -> tuple[ComponentEnvelope, ...]:
    """Resolve physical components without introducing a second X/Y origin."""

    boxes_by_id = {box.id: box for box in pinout_project.boxes}
    envelopes: list[ComponentEnvelope] = []

    for component in pinout_project.physical_components:
        if component.box_id is not None:
            box = boxes_by_id[component.box_id]
            minimum_x_mm = box.top_left[0] * raster_pitch_mm
            maximum_y_mm = box.top_left[1] * raster_pitch_mm
            maximum_x_mm = minimum_x_mm + box.size_pitches[0] * raster_pitch_mm
            minimum_y_mm = maximum_y_mm - box.size_pitches[1] * raster_pitch_mm
            envelopes.append(
                ComponentEnvelope(
                    component_id=component.id,
                    minimum_x_mm=minimum_x_mm,
                    minimum_y_mm=minimum_y_mm,
                    maximum_x_mm=maximum_x_mm,
                    maximum_y_mm=maximum_y_mm,
                    body_height_mm=None,
                    box_id=box.id,
                )
            )
            continue

        if component.component_type not in component_profiles:
            raise ValueError(
                f"Physical component {component.id!r} uses unknown mechanical "
                f"profile {component.component_type!r}"
            )
        profile = component_profiles[component.component_type]
        pin_names = [
            pin_name
            for pin_set_id in component.pin_sets
            for pin_name in pinout_project.pin_sets[pin_set_id]
        ]
        pin_coordinates = [pinout_project.pin_positions[name] for name in pin_names]
        minimum_pin_x = min(coordinate[0] for coordinate in pin_coordinates)
        maximum_pin_x = max(coordinate[0] for coordinate in pin_coordinates)
        minimum_pin_y = min(coordinate[1] for coordinate in pin_coordinates)
        maximum_pin_y = max(coordinate[1] for coordinate in pin_coordinates)
        envelopes.append(
            ComponentEnvelope(
                component_id=component.id,
                minimum_x_mm=(minimum_pin_x * raster_pitch_mm - profile.left_margin_mm),
                minimum_y_mm=(
                    minimum_pin_y * raster_pitch_mm - profile.bottom_margin_mm
                ),
                maximum_x_mm=(
                    maximum_pin_x * raster_pitch_mm + profile.right_margin_mm
                ),
                maximum_y_mm=(maximum_pin_y * raster_pitch_mm + profile.top_margin_mm),
                body_height_mm=profile.body_height_mm,
                box_id=None,
            )
        )

    return tuple(envelopes)


def resolve_downholder_plans(
    *,
    pinout_project,
    component_envelopes: tuple[ComponentEnvelope, ...],
    raster_pitch_mm: float,
    pin_row_base_width_mm: float,
    mount_eye_diameter_mm: float,
    corner_rail_width_mm: float,
    center_strip_width_mm: float,
    perimeter_frame_rail_width_mm: float,
    perimeter_frame_crossbar_width_mm: float,
) -> tuple[DownholderPlan, ...]:
    """Resolve retainer extents and screw centres without a second layout."""

    envelopes_by_id = {
        envelope.component_id: envelope for envelope in component_envelopes
    }
    plans: list[DownholderPlan] = []
    eye_radius_mm = mount_eye_diameter_mm / 2

    for component in pinout_project.physical_components:
        envelope = envelopes_by_id[component.id]
        if component.downholder is PinoutDownholderKind.NONE:
            continue
        if component.downholder is PinoutDownholderKind.PIN_LINE_CLAMP:
            continue

        if component.downholder is PinoutDownholderKind.CORNER:
            if len(component.pin_sets) != 2:
                raise ValueError(
                    f"Corner downholder {component.id!r} requires exactly two pin rows"
                )
            row_x_coordinates = []
            all_y_coordinates = []
            for pin_set_id in component.pin_sets:
                coordinates = [
                    pinout_project.pin_positions[name]
                    for name in pinout_project.pin_sets[pin_set_id]
                ]
                if not all(
                    math.isclose(coordinate[0], coordinates[0][0])
                    for coordinate in coordinates
                ):
                    raise ValueError(
                        f"Corner downholder {component.id!r} requires vertical rows"
                    )
                row_x_coordinates.append(coordinates[0][0] * raster_pitch_mm)
                all_y_coordinates.extend(
                    coordinate[1] * raster_pitch_mm for coordinate in coordinates
                )
            minimum_y_mm = min(all_y_coordinates)
            maximum_y_mm = max(all_y_coordinates)
            eye_center_offset_mm = eye_radius_mm + corner_rail_width_mm / 2
            plans.append(
                DownholderPlan(
                    component_id=component.id,
                    kind=component.downholder,
                    minimum_x_mm=(
                        min(row_x_coordinates) - eye_center_offset_mm - eye_radius_mm
                    ),
                    minimum_y_mm=minimum_y_mm,
                    maximum_x_mm=(
                        max(row_x_coordinates) + eye_center_offset_mm + eye_radius_mm
                    ),
                    maximum_y_mm=maximum_y_mm,
                    screw_centers_mm=(
                        (
                            min(row_x_coordinates) - eye_center_offset_mm,
                            minimum_y_mm + eye_radius_mm,
                        ),
                        (
                            min(row_x_coordinates) - eye_center_offset_mm,
                            maximum_y_mm - eye_radius_mm,
                        ),
                        (
                            max(row_x_coordinates) + eye_center_offset_mm,
                            minimum_y_mm + eye_radius_mm,
                        ),
                        (
                            max(row_x_coordinates) + eye_center_offset_mm,
                            maximum_y_mm - eye_radius_mm,
                        ),
                    ),
                )
            )
            continue

        if component.downholder is PinoutDownholderKind.PERIMETER_FRAME:
            vertical_pin_rows = []
            for pin_set_id in component.pin_sets:
                coordinates = [
                    pinout_project.pin_positions[name]
                    for name in pinout_project.pin_sets[pin_set_id]
                ]
                if len(coordinates) > 1 and all(
                    math.isclose(coordinate[0], coordinates[0][0])
                    for coordinate in coordinates
                ):
                    vertical_pin_rows.append(coordinates)
            if len(vertical_pin_rows) != 2:
                raise ValueError(
                    f"Perimeter-frame downholder {component.id!r} requires "
                    "exactly two vertical long-side pin rows"
                )
            if len(vertical_pin_rows[0]) != len(vertical_pin_rows[1]):
                raise ValueError(
                    f"Perimeter-frame downholder {component.id!r} requires "
                    "equally long side rows"
                )
            row_x_coordinates_mm = sorted(
                row[0][0] * raster_pitch_mm for row in vertical_pin_rows
            )
            row_y_coordinates_mm = sorted(
                {
                    coordinate[1] * raster_pitch_mm
                    for row in vertical_pin_rows
                    for coordinate in row
                }
            )
            bottom_crossbar_center_y_mm = row_y_coordinates_mm[0] - raster_pitch_mm
            top_crossbar_center_y_mm = row_y_coordinates_mm[-1] + raster_pitch_mm
            center_x_mm = sum(row_x_coordinates_mm) / 2
            bottom_screw_center_y_mm = (
                bottom_crossbar_center_y_mm
                - perimeter_frame_crossbar_width_mm / 2
                - eye_radius_mm
            )
            top_screw_center_y_mm = (
                top_crossbar_center_y_mm
                + perimeter_frame_crossbar_width_mm / 2
                + eye_radius_mm
            )
            plans.append(
                DownholderPlan(
                    component_id=component.id,
                    kind=component.downholder,
                    minimum_x_mm=min(
                        row_x_coordinates_mm[0] - perimeter_frame_rail_width_mm / 2,
                        center_x_mm - eye_radius_mm,
                    ),
                    minimum_y_mm=bottom_screw_center_y_mm - eye_radius_mm,
                    maximum_x_mm=max(
                        row_x_coordinates_mm[-1] + perimeter_frame_rail_width_mm / 2,
                        center_x_mm + eye_radius_mm,
                    ),
                    maximum_y_mm=top_screw_center_y_mm + eye_radius_mm,
                    screw_centers_mm=(
                        (center_x_mm, bottom_screw_center_y_mm),
                        (center_x_mm, top_screw_center_y_mm),
                    ),
                )
            )
            continue

        if component.downholder is not PinoutDownholderKind.CENTER_STRIP:
            raise ValueError(
                f"Unsupported downholder {component.downholder.value!r} on "
                f"{component.id!r}"
            )
        if len(component.pin_sets) != 2:
            raise ValueError(
                f"Center-strip downholder {component.id!r} requires two pin rows"
            )

        pin_rows = []
        for pin_set_id in component.pin_sets:
            coordinates = [
                pinout_project.pin_positions[name]
                for name in pinout_project.pin_sets[pin_set_id]
            ]
            if not all(
                math.isclose(coordinate[0], coordinates[0][0])
                for coordinate in coordinates
            ):
                raise ValueError(
                    f"Center-strip downholder {component.id!r} requires vertical rows"
                )
            pin_rows.append(coordinates)

        row_centers_x_mm = [row[0][0] * raster_pitch_mm for row in pin_rows]
        channel_width_mm = (
            abs(row_centers_x_mm[1] - row_centers_x_mm[0]) - pin_row_base_width_mm
        )
        if center_strip_width_mm > channel_width_mm:
            raise ValueError(
                f"Center-strip downholder {component.id!r} has only "
                f"{channel_width_mm:.3f} mm between socket rows, less than its "
                f"{center_strip_width_mm:.3f} mm strip"
            )
        center_x_mm = sum(row_centers_x_mm) / 2
        plans.append(
            DownholderPlan(
                component_id=component.id,
                kind=component.downholder,
                minimum_x_mm=center_x_mm - eye_radius_mm,
                minimum_y_mm=envelope.minimum_y_mm - mount_eye_diameter_mm,
                maximum_x_mm=center_x_mm + eye_radius_mm,
                maximum_y_mm=envelope.maximum_y_mm + mount_eye_diameter_mm,
                screw_centers_mm=(
                    (center_x_mm, envelope.minimum_y_mm - eye_radius_mm),
                    (center_x_mm, envelope.maximum_y_mm + eye_radius_mm),
                ),
            )
        )

    return tuple(plans)


def _create_clearance_hole_at(
    *, center_x_mm, center_y_mm, minimum_z_mm, length_mm, diameter_mm
):
    hole = create_cylinder(diameter_mm / 2, length_mm)
    return translate(center_x_mm, center_y_mm, minimum_z_mm)(hole)


def _create_screw_preview_at(
    *, center_x_mm, center_y_mm, holder_top_z_mm, screw_size, screw_length_mm
):
    screw = create_cylinder_screw(screw_size, screw_length_mm)
    screw = translate(0, 0, -screw_length_mm)(screw)
    return translate(center_x_mm, center_y_mm, holder_top_z_mm)(screw)


def _parts_have_common_volume(first, second, *, tolerance_mm3=1e-5) -> bool:
    """Return whether two solids overlap by volume, with a cheap bbox guard."""

    first_bbox = get_bounding_box(first)
    second_bbox = get_bounding_box(second)
    if any(
        min(first_bbox[1][axis], second_bbox[1][axis])
        - max(first_bbox[0][axis], second_bbox[0][axis])
        <= 1e-6
        for axis in range(3)
    ):
        return False
    separate_volume = get_volume(first) + get_volume(second)
    fused_volume = get_volume(first.fuse(second))
    return separate_volume - fused_volume > tolerance_mm3


def create_pinout_base_plate_assembly(
    *,
    pinout_base_plate_pinout_yaml_path,
    pinout_base_plate_raster_pitch,
    pinout_base_plate_thickness,
    pinout_base_plate_border_left,
    pinout_base_plate_border_right,
    pinout_base_plate_border_top,
    pinout_base_plate_border_bottom,
    pinout_base_plate_corner_radius,
    pinout_base_plate_pin_tail_width,
    pinout_base_plate_pin_pass_through_clearance,
    pinout_base_plate_pin_row_base_width,
    pinout_base_plate_pin_row_slot_clearance,
    pinout_base_plate_pin_row_vertical_clearance,
    pinout_base_plate_wire_wrap_pin_length,
    pinout_base_plate_wire_wrap_pin_base_thickness,
    pinout_base_plate_top_pin_length,
    pinout_base_plate_pin_line_clamp_base_length,
    pinout_base_plate_pin_line_clamp_holder_slack,
    pinout_base_plate_pin_line_clamp_vertical_slack,
    pinout_base_plate_pin_line_clamp_lip_size,
    pinout_base_plate_pin_line_clamp_slit_width,
    pinout_base_plate_reference_frame_width,
    pinout_base_plate_reference_frame_height,
    pinout_base_plate_mount_screw_size,
    pinout_base_plate_mount_screw_length,
    pinout_base_plate_mount_screw_clearance_type,
    pinout_base_plate_self_threading_core_radius_adjustment,
    pinout_base_plate_mount_eye_diameter_clearance,
    pinout_base_plate_downholder_profiles,
    pinout_base_plate_usb_bridge_wall_thickness,
    pinout_base_plate_usb_cable_hole_width,
    pinout_base_plate_usb_cable_hole_height,
    pinout_base_plate_pico_usb_connector_width,
    pinout_base_plate_pico_usb_connector_thickness,
    pinout_base_plate_pico_usb_connector_depth,
    pinout_base_plate_pico_usb_connector_offset,
    pinout_base_plate_component_profiles,
) -> LeaderFollowersCuttersPart:
    """Create the fitted plate, wire-wrap carriers, and rigid downholders."""

    raster_pitch_mm = float(pinout_base_plate_raster_pitch)
    plate_thickness_mm = float(pinout_base_plate_thickness)
    plate_border_left_mm = float(pinout_base_plate_border_left)
    plate_border_right_mm = float(pinout_base_plate_border_right)
    plate_border_top_mm = float(pinout_base_plate_border_top)
    plate_border_bottom_mm = float(pinout_base_plate_border_bottom)
    plate_corner_radius_mm = float(pinout_base_plate_corner_radius)
    pin_tail_width_mm = float(pinout_base_plate_pin_tail_width)
    pin_clearance_mm = float(pinout_base_plate_pin_pass_through_clearance)
    pin_row_base_width_mm = float(pinout_base_plate_pin_row_base_width)
    pin_row_slot_clearance_mm = float(pinout_base_plate_pin_row_slot_clearance)
    pin_row_vertical_clearance_mm = float(pinout_base_plate_pin_row_vertical_clearance)
    wire_wrap_pin_length_mm = float(pinout_base_plate_wire_wrap_pin_length)
    wire_wrap_pin_base_thickness_mm = float(
        pinout_base_plate_wire_wrap_pin_base_thickness
    )
    top_pin_length_mm = float(pinout_base_plate_top_pin_length)
    pin_line_clamp_base_length_mm = float(pinout_base_plate_pin_line_clamp_base_length)
    pin_line_clamp_holder_slack_mm = float(
        pinout_base_plate_pin_line_clamp_holder_slack
    )
    pin_line_clamp_vertical_slack_mm = float(
        pinout_base_plate_pin_line_clamp_vertical_slack
    )
    pin_line_clamp_lip_size_mm = float(pinout_base_plate_pin_line_clamp_lip_size)
    pin_line_clamp_slit_width_mm = float(pinout_base_plate_pin_line_clamp_slit_width)
    reference_frame_width_mm = float(pinout_base_plate_reference_frame_width)
    reference_frame_height_mm = float(pinout_base_plate_reference_frame_height)
    mount_screw_size = str(pinout_base_plate_mount_screw_size)
    mount_screw_length_mm = float(pinout_base_plate_mount_screw_length)
    mount_screw_clearance_type = str(pinout_base_plate_mount_screw_clearance_type)
    self_threading_core_radius_adjustment_mm = float(
        pinout_base_plate_self_threading_core_radius_adjustment
    )
    mount_eye_diameter_clearance_mm = float(
        pinout_base_plate_mount_eye_diameter_clearance
    )
    if not isinstance(pinout_base_plate_downholder_profiles, Mapping):
        raise ValueError("pinout_base_plate_downholder_profiles must be a mapping")
    corner_profile = pinout_base_plate_downholder_profiles.get("corner")
    center_strip_profile = pinout_base_plate_downholder_profiles.get("center_strip")
    perimeter_frame_profile = pinout_base_plate_downholder_profiles.get(
        "perimeter_frame"
    )
    if (
        not isinstance(corner_profile, Mapping)
        or not isinstance(center_strip_profile, Mapping)
        or not isinstance(perimeter_frame_profile, Mapping)
    ):
        raise ValueError(
            "Downholder profiles require corner, center_strip, and "
            "perimeter_frame mappings"
        )
    corner_holder_thickness_mm = float(corner_profile["thickness_mm"])
    corner_rail_width_mm = float(corner_profile["rail_width_mm"])
    corner_bridge_width_mm = float(corner_profile["bridge_width_mm"])
    corner_bridge_indices = tuple(
        int(index) for index in corner_profile["bridge_pin_indices_from_bottom"]
    )
    center_strip_holder_thickness_mm = float(center_strip_profile["thickness_mm"])
    center_strip_width_mm = float(center_strip_profile["strip_width_mm"])
    perimeter_frame_holder_thickness_mm = float(perimeter_frame_profile["thickness_mm"])
    perimeter_frame_rail_width_mm = float(perimeter_frame_profile["rail_width_mm"])
    perimeter_frame_crossbar_width_mm = float(
        perimeter_frame_profile["crossbar_width_mm"]
    )
    screw_record = MScrew.from_size(mount_screw_size)
    loose_hole_diameter_mm = screw_record.get_clearance_hole_diameter(
        mount_screw_clearance_type
    )
    mount_eye_diameter_mm = (
        screw_record.cylinder_head_diameter + mount_eye_diameter_clearance_mm
    )
    mount_eye_fillet_radius_mm = mount_eye_diameter_mm / 2 - 0.01
    usb_bridge_wall_thickness_mm = float(pinout_base_plate_usb_bridge_wall_thickness)
    usb_cable_hole_width_mm = float(pinout_base_plate_usb_cable_hole_width)
    usb_cable_hole_height_mm = float(pinout_base_plate_usb_cable_hole_height)
    pico_usb_connector_width_mm = float(pinout_base_plate_pico_usb_connector_width)
    pico_usb_connector_thickness_mm = float(
        pinout_base_plate_pico_usb_connector_thickness
    )
    pico_usb_connector_depth_mm = float(pinout_base_plate_pico_usb_connector_depth)
    pico_usb_connector_offset_mm = float(pinout_base_plate_pico_usb_connector_offset)

    positive_dimensions = {
        "pinout_base_plate_raster_pitch": raster_pitch_mm,
        "pinout_base_plate_thickness": plate_thickness_mm,
        "pinout_base_plate_pin_tail_width": pin_tail_width_mm,
        "pinout_base_plate_pin_row_base_width": pin_row_base_width_mm,
        "pinout_base_plate_wire_wrap_pin_length": wire_wrap_pin_length_mm,
        "pinout_base_plate_wire_wrap_pin_base_thickness": (
            wire_wrap_pin_base_thickness_mm
        ),
        "pinout_base_plate_top_pin_length": top_pin_length_mm,
        "pinout_base_plate_pin_line_clamp_base_length": (pin_line_clamp_base_length_mm),
        "pinout_base_plate_pin_line_clamp_lip_size": pin_line_clamp_lip_size_mm,
        "pinout_base_plate_pin_line_clamp_slit_width": (pin_line_clamp_slit_width_mm),
        "pinout_base_plate_reference_frame_width": reference_frame_width_mm,
        "pinout_base_plate_reference_frame_height": reference_frame_height_mm,
        "pinout_base_plate_mount_screw_length": mount_screw_length_mm,
        "pinout_base_plate_mount_eye_diameter_clearance": (
            mount_eye_diameter_clearance_mm
        ),
        "corner_holder_thickness": corner_holder_thickness_mm,
        "corner_rail_width": corner_rail_width_mm,
        "corner_bridge_width": corner_bridge_width_mm,
        "center_strip_holder_thickness": center_strip_holder_thickness_mm,
        "center_strip_width": center_strip_width_mm,
        "perimeter_frame_holder_thickness": perimeter_frame_holder_thickness_mm,
        "perimeter_frame_rail_width": perimeter_frame_rail_width_mm,
        "perimeter_frame_crossbar_width": perimeter_frame_crossbar_width_mm,
        "usb_bridge_wall_thickness": usb_bridge_wall_thickness_mm,
        "usb_cable_hole_width": usb_cable_hole_width_mm,
        "usb_cable_hole_height": usb_cable_hole_height_mm,
        "pico_usb_connector_width": pico_usb_connector_width_mm,
        "pico_usb_connector_thickness": pico_usb_connector_thickness_mm,
        "pico_usb_connector_depth": pico_usb_connector_depth_mm,
    }
    for name, value in positive_dimensions.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    non_negative_dimensions = {
        "pinout_base_plate_border_left": plate_border_left_mm,
        "pinout_base_plate_border_right": plate_border_right_mm,
        "pinout_base_plate_border_top": plate_border_top_mm,
        "pinout_base_plate_border_bottom": plate_border_bottom_mm,
        "pinout_base_plate_pin_pass_through_clearance": pin_clearance_mm,
        "pinout_base_plate_pin_row_slot_clearance": pin_row_slot_clearance_mm,
        "pinout_base_plate_pin_row_vertical_clearance": (pin_row_vertical_clearance_mm),
        "pinout_base_plate_pin_line_clamp_holder_slack": (
            pin_line_clamp_holder_slack_mm
        ),
        "pinout_base_plate_pin_line_clamp_vertical_slack": (
            pin_line_clamp_vertical_slack_mm
        ),
    }
    if any(value < 0 for value in non_negative_dimensions.values()):
        raise ValueError(
            "Plate margins and pin-row/pass-through clearances must be non-negative"
        )
    if not corner_bridge_indices or any(index <= 0 for index in corner_bridge_indices):
        raise ValueError("Pico bridge indices must be positive and non-empty")
    if pico_usb_connector_offset_mm < 0:
        raise ValueError("Pico USB connector offset must be non-negative")

    pinout_yaml_path = Path(pinout_base_plate_pinout_yaml_path).expanduser()
    pinout_project = load_pinout_config(pinout_yaml_path)
    if not pinout_project.physical_components:
        raise ValueError(
            f"Pinout {pinout_yaml_path} has no physical_components topology"
        )

    component_profiles = resolve_component_profiles(
        pinout_base_plate_component_profiles
    )
    component_envelopes = resolve_component_envelopes(
        pinout_project=pinout_project,
        raster_pitch_mm=raster_pitch_mm,
        component_profiles=component_profiles,
    )
    downholder_plans = resolve_downholder_plans(
        pinout_project=pinout_project,
        component_envelopes=component_envelopes,
        raster_pitch_mm=raster_pitch_mm,
        pin_row_base_width_mm=pin_row_base_width_mm,
        mount_eye_diameter_mm=mount_eye_diameter_mm,
        corner_rail_width_mm=corner_rail_width_mm,
        center_strip_width_mm=center_strip_width_mm,
        perimeter_frame_rail_width_mm=perimeter_frame_rail_width_mm,
        perimeter_frame_crossbar_width_mm=perimeter_frame_crossbar_width_mm,
    )

    component_minimum_x_mm = min(
        [envelope.minimum_x_mm for envelope in component_envelopes]
        + [plan.minimum_x_mm for plan in downholder_plans]
    )
    component_minimum_y_mm = min(
        [envelope.minimum_y_mm for envelope in component_envelopes]
        + [plan.minimum_y_mm for plan in downholder_plans]
    )
    component_maximum_x_mm = max(
        [envelope.maximum_x_mm for envelope in component_envelopes]
        + [plan.maximum_x_mm for plan in downholder_plans]
    )
    component_maximum_y_mm = max(
        [envelope.maximum_y_mm for envelope in component_envelopes]
        + [plan.maximum_y_mm for plan in downholder_plans]
    )
    plate_source_minimum_x_mm = component_minimum_x_mm - plate_border_left_mm
    plate_source_minimum_y_mm = component_minimum_y_mm - plate_border_bottom_mm
    plate_width_mm = (
        component_maximum_x_mm
        - component_minimum_x_mm
        + plate_border_left_mm
        + plate_border_right_mm
    )
    plate_depth_mm = (
        component_maximum_y_mm
        - component_minimum_y_mm
        + plate_border_bottom_mm
        + plate_border_top_mm
    )
    if (
        plate_corner_radius_mm < 0
        or plate_corner_radius_mm > min(plate_width_mm, plate_depth_mm) / 2
    ):
        raise ValueError("pinout_base_plate_corner_radius is outside the plate")

    base_plate = create_filleted_box(
        plate_width_mm,
        plate_depth_mm,
        plate_thickness_mm,
        fillet_radius=plate_corner_radius_mm,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    plate_surface_reference = base_plate

    pico_usb_cable_cutter = None
    pico_usb_connector_preview = None
    pico_usb_bridge_metadata = None
    pico_usb_bridge = None
    pico_components = [
        component
        for component in pinout_project.physical_components
        if component.component_type == "rp2040_plus_2x20"
    ]
    if len(pico_components) > 1:
        raise ValueError("Only one RP2040-Plus USB bridge is supported per plate")
    if pico_components:
        pico_component = pico_components[0]
        pico_profile = component_profiles[pico_component.component_type]
        pico_pin_coordinates = [
            pinout_project.pin_positions[pin_name]
            for pin_set_id in pico_component.pin_sets
            for pin_name in pinout_project.pin_sets[pin_set_id]
        ]
        pico_row_x_coordinates_mm = sorted(
            {
                coordinate[0] * raster_pitch_mm - plate_source_minimum_x_mm
                for coordinate in pico_pin_coordinates
            }
        )
        pico_maximum_pin_y_mm = (
            max(coordinate[1] for coordinate in pico_pin_coordinates) * raster_pitch_mm
            - plate_source_minimum_y_mm
        )
        pico_center_x_mm = sum(pico_row_x_coordinates_mm) / 2
        bridge_opening_width_mm = max(
            usb_cable_hole_width_mm,
            pico_row_x_coordinates_mm[-1]
            - pico_row_x_coordinates_mm[0]
            + corner_rail_width_mm,
        )
        bridge_minimum_y_mm = pico_maximum_pin_y_mm + corner_rail_width_mm / 2
        bridge_depth_mm = plate_depth_mm - bridge_minimum_y_mm
        if bridge_depth_mm <= 0:
            raise ValueError(
                "The configured top plate margin leaves no depth for the Pico "
                "USB bridge"
            )
        bridge_outer_width_mm = (
            bridge_opening_width_mm + 2 * usb_bridge_wall_thickness_mm
        )
        bridge_outer_height_mm = usb_cable_hole_height_mm + usb_bridge_wall_thickness_mm
        connector_minimum_y_mm = pico_maximum_pin_y_mm - pico_usb_connector_offset_mm
        pico_usb_bridge = create_box(
            bridge_outer_width_mm,
            bridge_depth_mm,
            bridge_outer_height_mm,
            origin=(
                pico_center_x_mm - bridge_outer_width_mm / 2,
                bridge_minimum_y_mm,
                plate_thickness_mm,
            ),
        )
        pico_usb_cable_cutter = create_box(
            bridge_opening_width_mm,
            plate_depth_mm - connector_minimum_y_mm + 1,
            plate_thickness_mm + usb_cable_hole_height_mm + 1,
            origin=(
                pico_center_x_mm - bridge_opening_width_mm / 2,
                connector_minimum_y_mm,
                -1,
            ),
        )
        pico_usb_bridge = pico_usb_bridge.cut(pico_usb_cable_cutter)
        base_plate = base_plate.fuse(pico_usb_bridge)
        base_plate = base_plate.cut(pico_usb_cable_cutter)

        pico_usb_connector_preview = create_box(
            pico_usb_connector_width_mm,
            pico_usb_connector_depth_mm,
            pico_usb_connector_thickness_mm,
            origin=(
                pico_center_x_mm - pico_usb_connector_width_mm / 2,
                connector_minimum_y_mm,
                plate_thickness_mm + pico_profile.body_height_mm,
            ),
        )
        pico_usb_bridge_metadata = {
            "component_id": pico_component.id,
            "opening_width_mm": bridge_opening_width_mm,
            "opening_height_mm": usb_cable_hole_height_mm,
            "plate_cutout_minimum_y_mm": connector_minimum_y_mm,
            "minimum_y_mm": bridge_minimum_y_mm,
            "maximum_y_mm": plate_depth_mm,
        }

    pin_hole_size_mm = pin_tail_width_mm + 2 * pin_clearance_mm
    individual_pin_pass_throughs = PartCollector()
    pin_row_slots = PartCollector()
    pin_pass_through_centers_mm: list[dict[str, Any]] = []
    individual_pin_pass_through_metadata: list[dict[str, Any]] = []
    pin_row_slot_metadata: list[dict[str, Any]] = []
    pin_row_slot_parts = {}
    positioned_pin_headers = []
    row_slot_count = 0
    individual_hole_count = 0
    for component in pinout_project.physical_components:
        if not component.through_pin_sets:
            continue
        profile = component_profiles[component.component_type]
        for pin_set_id in component.through_pin_sets:
            pin_names = pinout_project.pin_sets[pin_set_id]
            source_coordinates = [
                pinout_project.pin_positions[pin_name] for pin_name in pin_names
            ]
            normalized_centers_mm = []
            for pin_name, (source_x, source_y) in zip(
                pin_names,
                source_coordinates,
                strict=True,
            ):
                center_x_mm = source_x * raster_pitch_mm - plate_source_minimum_x_mm
                center_y_mm = source_y * raster_pitch_mm - plate_source_minimum_y_mm
                normalized_centers_mm.append((center_x_mm, center_y_mm))
                pin_pass_through_centers_mm.append(
                    {
                        "component_id": component.id,
                        "pin_set_id": pin_set_id,
                        "pin_name": pin_name,
                        "center_mm": [center_x_mm, center_y_mm],
                        "source_raster": [source_x, source_y],
                    }
                )

            if profile.pass_through_style == "individual_holes":
                for pin_name, (center_x_mm, center_y_mm) in zip(
                    pin_names,
                    normalized_centers_mm,
                    strict=True,
                ):
                    pin_pass_through = create_box(
                        pin_hole_size_mm,
                        pin_hole_size_mm,
                        plate_thickness_mm + 2 * pin_clearance_mm,
                        origin=(
                            center_x_mm - pin_hole_size_mm / 2,
                            center_y_mm - pin_hole_size_mm / 2,
                            -pin_clearance_mm,
                        ),
                    )
                    individual_pin_pass_throughs = individual_pin_pass_throughs.fuse(
                        pin_pass_through
                    )
                    individual_pin_pass_through_metadata.append(
                        {
                            "component_id": component.id,
                            "pin_set_id": pin_set_id,
                            "pin_name": pin_name,
                            "center_mm": [center_x_mm, center_y_mm],
                        }
                    )
                    individual_hole_count += 1
                continue

            if len(source_coordinates) == 1:
                orientation = "vertical"
            else:
                x_coordinates = [coordinate[0] for coordinate in source_coordinates]
                y_coordinates = [coordinate[1] for coordinate in source_coordinates]
                is_vertical = all(
                    math.isclose(x, x_coordinates[0]) for x in x_coordinates
                )
                is_horizontal = all(
                    math.isclose(y, y_coordinates[0]) for y in y_coordinates
                )
                if not is_vertical and not is_horizontal:
                    raise ValueError(
                        f"Row-slot pin set {pin_set_id!r} must be collinear"
                    )
                orientation = "vertical" if is_vertical else "horizontal"
                active_coordinates = y_coordinates if is_vertical else x_coordinates
                steps = [
                    second - first
                    for first, second in zip(
                        active_coordinates,
                        active_coordinates[1:],
                    )
                ]
                if any(
                    not math.isclose(abs(step), 1.0, abs_tol=1e-9) for step in steps
                ):
                    raise ValueError(
                        f"Row-slot pin set {pin_set_id!r} must use one-pitch spacing"
                    )
                if any(
                    not math.isclose(step, steps[0], abs_tol=1e-9) for step in steps[1:]
                ):
                    raise ValueError(
                        f"Row-slot pin set {pin_set_id!r} must use regular spacing"
                    )

            x_centers = [center[0] for center in normalized_centers_mm]
            y_centers = [center[1] for center in normalized_centers_mm]
            slot_length_mm = (
                (len(pin_names) - 1) * raster_pitch_mm
                + raster_pitch_mm
                + 2 * pin_row_slot_clearance_mm
            )
            slot_width_mm = pin_row_base_width_mm + 2 * pin_row_slot_clearance_mm
            if orientation == "vertical":
                slot_size_x_mm = slot_width_mm
                slot_size_y_mm = slot_length_mm
                slot_minimum_x_mm = x_centers[0] - slot_width_mm / 2
                slot_minimum_y_mm = (
                    min(y_centers) - raster_pitch_mm / 2 - pin_row_slot_clearance_mm
                )
            else:
                slot_size_x_mm = slot_length_mm
                slot_size_y_mm = slot_width_mm
                slot_minimum_x_mm = (
                    min(x_centers) - raster_pitch_mm / 2 - pin_row_slot_clearance_mm
                )
                slot_minimum_y_mm = y_centers[0] - slot_width_mm / 2

            pin_row_slot = create_box(
                slot_size_x_mm,
                slot_size_y_mm,
                plate_thickness_mm + 2 * pin_row_vertical_clearance_mm,
                origin=(
                    slot_minimum_x_mm,
                    slot_minimum_y_mm,
                    -pin_row_vertical_clearance_mm,
                ),
            )
            pin_row_slots = pin_row_slots.fuse(pin_row_slot)
            pin_row_slot_parts[(component.id, pin_set_id)] = pin_row_slot
            pin_row_slot_metadata.append(
                {
                    "component_id": component.id,
                    "pin_set_id": pin_set_id,
                    "pin_names": list(pin_names),
                    "orientation": orientation,
                    "minimum_mm": [slot_minimum_x_mm, slot_minimum_y_mm],
                    "maximum_mm": [
                        slot_minimum_x_mm + slot_size_x_mm,
                        slot_minimum_y_mm + slot_size_y_mm,
                    ],
                }
            )
            row_slot_count += 1

            if component.downholder is PinoutDownholderKind.PIN_LINE_CLAMP:
                continue

            if len(source_coordinates) == 1:
                angle_degrees = 0
            else:
                delta_x = source_coordinates[1][0] - source_coordinates[0][0]
                delta_y = source_coordinates[1][1] - source_coordinates[0][1]
                angle_degrees = {
                    (0.0, 1.0): 0,
                    (1.0, 0.0): -90,
                    (0.0, -1.0): 180,
                    (-1.0, 0.0): 90,
                }[(delta_x, delta_y)]

            pin_header = create_sil_header(
                num_y_pins=len(pin_names),
                dil_pitch=raster_pitch_mm,
                wire_wrap_pin_side=pin_tail_width_mm,
                wire_wrap_pin_length=wire_wrap_pin_length_mm,
                wire_wrap_pin_base_thickness=wire_wrap_pin_base_thickness_mm,
                wire_wrap_pin_base_width=pin_row_base_width_mm,
                top_pin_length=top_pin_length_mm,
                pin_cutter_slack=pin_clearance_mm,
            )
            pin_header = rotate(angle_degrees)(pin_header)
            pin_header = pin_header.aligned_from_cutter(
                "pin_cutters",
                pin_row_slot,
                Alignment.CENTER,
                axes=[0, 1],
            )
            pin_header = align(
                pin_header,
                plate_surface_reference,
                Alignment.TOP,
            )
            positioned_pin_headers.append((component.id, pin_set_id, pin_header))

    pin_line_clamp_recesses = PartCollector()
    pin_line_clamp_recess_count = 0
    positioned_pin_line_clamps = []
    pin_line_clamp_component_ids = set()
    for component in pinout_project.physical_components:
        if component.downholder is not PinoutDownholderKind.PIN_LINE_CLAMP:
            continue
        if (
            len(component.pin_sets) != 1
            or component.through_pin_sets != component.pin_sets
        ):
            raise ValueError(
                f"Pin-line clamp component {component.id!r} requires one through "
                "pin set"
            )
        profile = component_profiles[component.component_type]
        if profile.pass_through_style != "row_slot":
            raise ValueError(
                f"Pin-line clamp component {component.id!r} requires row_slot"
            )

        pin_set_id = component.pin_sets[0]
        pin_names = pinout_project.pin_sets[pin_set_id]
        source_coordinates = [
            pinout_project.pin_positions[pin_name] for pin_name in pin_names
        ]
        if len(source_coordinates) == 1:
            angle_degrees = 0
        else:
            delta_x = source_coordinates[1][0] - source_coordinates[0][0]
            delta_y = source_coordinates[1][1] - source_coordinates[0][1]
            angle_degrees = {
                (0.0, 1.0): 0,
                (1.0, 0.0): -90,
                (0.0, -1.0): 180,
                (-1.0, 0.0): 90,
            }[(delta_x, delta_y)]

        pin_line_clamp = create_sil_pin_line_clamp(
            num_pins=len(pin_names),
            dil_pitch=raster_pitch_mm,
            wire_wrap_pin_side=pin_tail_width_mm,
            wire_wrap_pin_length=wire_wrap_pin_length_mm,
            wire_wrap_pin_base_thickness=wire_wrap_pin_base_thickness_mm,
            wire_wrap_pin_base_width=pin_row_base_width_mm,
            top_pin_length=top_pin_length_mm,
            base_plate_length=pin_line_clamp_base_length_mm,
            base_plate_thickness=plate_thickness_mm,
            holder_slack=pin_line_clamp_holder_slack_mm,
            base_cutter_vertical_slack=pin_line_clamp_vertical_slack_mm,
            lip_size=pin_line_clamp_lip_size_mm,
            slit_width=pin_line_clamp_slit_width_mm,
        )
        pin_line_clamp = rotate(angle_degrees)(pin_line_clamp)
        pin_line_clamp = pin_line_clamp.aligned_from_cutter(
            "pin_cutters",
            pin_row_slot_parts[(component.id, pin_set_id)],
            Alignment.CENTER,
            axes=[0, 1],
        )
        pin_line_clamp = pin_line_clamp.aligned_from_follower(
            "additional_pins_base_plate",
            plate_surface_reference,
            Alignment.BOTTOM,
        )

        flat_base_plate = pin_line_clamp.get_follower_part_by_name(
            "additional_pins_base_plate"
        )
        clamp_recess = materialize_bounding_box(flat_base_plate)
        pin_line_clamp_recesses = pin_line_clamp_recesses.fuse(clamp_recess)
        pin_line_clamp_recess_count += 1
        base_plate = base_plate.cut(clamp_recess)
        base_plate = base_plate.fuse(pin_line_clamp.leader)
        positioned_pin_line_clamps.append((component.id, pin_line_clamp))
        pin_line_clamp_component_ids.add(component.id)

    components_by_id = {
        component.id: component for component in pinout_project.physical_components
    }
    envelopes_by_id = {
        envelope.component_id: envelope for envelope in component_envelopes
    }
    downholder_plans_by_id = {plan.component_id: plan for plan in downholder_plans}
    pin_headers_by_component = {}
    for component_id, pin_set_id, pin_header in positioned_pin_headers:
        pin_headers_by_component.setdefault(component_id, {})[pin_set_id] = pin_header

    positioned_downholders = []
    downholder_screw_previews = []
    downholder_loose_holes = PartCollector()
    downholder_self_threading_holes = PartCollector()
    downholder_metadata = []
    all_screw_centers = []

    for component_id, plan in downholder_plans_by_id.items():
        component = components_by_id[component_id]
        envelope = envelopes_by_id[component_id]
        profile = component_profiles[component.component_type]
        normalized_screw_centers = tuple(
            (
                center_x_mm - plate_source_minimum_x_mm,
                center_y_mm - plate_source_minimum_y_mm,
            )
            for center_x_mm, center_y_mm in plan.screw_centers_mm
        )

        if plan.kind is PinoutDownholderKind.CENTER_STRIP:
            holder_bottom_z_mm = plate_thickness_mm + profile.clamp_surface_height_mm
            center_x_mm = (
                plan.minimum_x_mm + plan.maximum_x_mm
            ) / 2 - plate_source_minimum_x_mm
            minimum_y_mm = normalized_screw_centers[0][1]
            maximum_y_mm = normalized_screw_centers[1][1]
            holder = create_box(
                center_strip_width_mm,
                maximum_y_mm - minimum_y_mm,
                center_strip_holder_thickness_mm,
                origin=(
                    center_x_mm - center_strip_width_mm / 2,
                    minimum_y_mm,
                    holder_bottom_z_mm,
                ),
            )
            for screw_center_x_mm, screw_center_y_mm in normalized_screw_centers:
                eye = create_cylinder(
                    mount_eye_diameter_mm / 2,
                    center_strip_holder_thickness_mm,
                )
                eye = translate(
                    screw_center_x_mm,
                    screw_center_y_mm,
                    holder_bottom_z_mm,
                )(eye)
                holder = holder.fuse(eye)
            holder_thickness_mm = center_strip_holder_thickness_mm
            feature_metadata = {
                "strip_count": 1,
                "eye_count": 2,
            }
        elif plan.kind is PinoutDownholderKind.PERIMETER_FRAME:
            holder_bottom_z_mm = plate_thickness_mm + profile.clamp_surface_height_mm
            vertical_source_rows = []
            for pin_set_id in component.pin_sets:
                source_coordinates = [
                    pinout_project.pin_positions[name]
                    for name in pinout_project.pin_sets[pin_set_id]
                ]
                if len(source_coordinates) > 1 and all(
                    math.isclose(coordinate[0], source_coordinates[0][0])
                    for coordinate in source_coordinates
                ):
                    vertical_source_rows.append(source_coordinates)
            row_x_coordinates_mm = sorted(
                row[0][0] * raster_pitch_mm - plate_source_minimum_x_mm
                for row in vertical_source_rows
            )
            row_y_coordinates_mm = sorted(
                {
                    coordinate[1] * raster_pitch_mm - plate_source_minimum_y_mm
                    for row in vertical_source_rows
                    for coordinate in row
                }
            )
            crossbar_center_y_coordinates_mm = (
                row_y_coordinates_mm[0] - raster_pitch_mm,
                row_y_coordinates_mm[-1] + raster_pitch_mm,
            )
            holder = PartCollector()
            for row_x_mm in row_x_coordinates_mm:
                holder = holder.fuse(
                    create_box(
                        perimeter_frame_rail_width_mm,
                        crossbar_center_y_coordinates_mm[1]
                        - crossbar_center_y_coordinates_mm[0],
                        perimeter_frame_holder_thickness_mm,
                        origin=(
                            row_x_mm - perimeter_frame_rail_width_mm / 2,
                            crossbar_center_y_coordinates_mm[0],
                            holder_bottom_z_mm,
                        ),
                    )
                )
            crossbars_by_alignment = {}
            for front_back_alignment, crossbar_center_y_mm in zip(
                (Alignment.FRONT, Alignment.BACK),
                crossbar_center_y_coordinates_mm,
                strict=True,
            ):
                crossbar = create_box(
                    row_x_coordinates_mm[-1]
                    - row_x_coordinates_mm[0]
                    + perimeter_frame_rail_width_mm,
                    perimeter_frame_crossbar_width_mm,
                    perimeter_frame_holder_thickness_mm,
                    origin=(
                        row_x_coordinates_mm[0] - perimeter_frame_rail_width_mm / 2,
                        crossbar_center_y_mm - perimeter_frame_crossbar_width_mm / 2,
                        holder_bottom_z_mm,
                    ),
                )
                holder = holder.fuse(crossbar)
                crossbars_by_alignment[front_back_alignment] = crossbar
            for front_back_alignment, crossbar in crossbars_by_alignment.items():
                eye = create_filleted_box(
                    mount_eye_diameter_mm,
                    mount_eye_diameter_mm,
                    perimeter_frame_holder_thickness_mm,
                    fillet_radius=mount_eye_fillet_radius_mm,
                    no_fillets_at=[
                        Alignment.TOP,
                        Alignment.BOTTOM,
                        front_back_alignment.opposite,
                    ],
                )
                eye = align(eye, crossbar, Alignment.CENTER, axes=[0])
                eye = align(eye, crossbar, front_back_alignment.stack_alignment)
                eye = align(eye, crossbar, Alignment.BOTTOM)
                holder = holder.fuse(eye)
            holder_thickness_mm = perimeter_frame_holder_thickness_mm
            feature_metadata = {
                "rail_count": 2,
                "crossbar_count": 2,
                "crossbar_offset_pitches": 1,
                "eye_count": 2,
            }
        elif plan.kind is PinoutDownholderKind.CORNER:
            headers = pin_headers_by_component.get(component_id, {})
            if set(headers) != set(component.pin_sets):
                raise ValueError(
                    f"Corner downholder {component_id!r} requires preview pin rows"
                )
            holder_bottom_z_mm = max(
                get_bounding_box(header.get_follower_part_by_name("top_pins"))[1][2]
                for header in headers.values()
            )
            source_rows = [
                [
                    pinout_project.pin_positions[name]
                    for name in pinout_project.pin_sets[pin_set_id]
                ]
                for pin_set_id in component.pin_sets
            ]
            row_x_coordinates_mm = sorted(
                row[0][0] * raster_pitch_mm - plate_source_minimum_x_mm
                for row in source_rows
            )
            row_y_coordinates_mm = sorted(
                {
                    coordinate[1] * raster_pitch_mm - plate_source_minimum_y_mm
                    for row in source_rows
                    for coordinate in row
                }
            )
            holder = PartCollector()
            rails_by_alignment = {}
            for left_right_alignment, row_x_mm in zip(
                (Alignment.LEFT, Alignment.RIGHT),
                row_x_coordinates_mm,
                strict=True,
            ):
                rail = create_box(
                    corner_rail_width_mm,
                    row_y_coordinates_mm[-1] - row_y_coordinates_mm[0],
                    corner_holder_thickness_mm,
                    origin=(
                        row_x_mm - corner_rail_width_mm / 2,
                        row_y_coordinates_mm[0],
                        holder_bottom_z_mm,
                    ),
                )
                holder = holder.fuse(rail)
                rails_by_alignment[left_right_alignment] = rail
            for pin_index in corner_bridge_indices:
                if pin_index > len(row_y_coordinates_mm):
                    raise ValueError(
                        f"Pico bridge index {pin_index} exceeds the "
                        f"{len(row_y_coordinates_mm)} pin rows"
                    )
                bridge_y_mm = row_y_coordinates_mm[pin_index - 1]
                holder = holder.fuse(
                    create_box(
                        row_x_coordinates_mm[-1]
                        - row_x_coordinates_mm[0]
                        + corner_rail_width_mm,
                        corner_bridge_width_mm,
                        corner_holder_thickness_mm,
                        origin=(
                            row_x_coordinates_mm[0] - corner_rail_width_mm / 2,
                            bridge_y_mm - corner_bridge_width_mm / 2,
                            holder_bottom_z_mm,
                        ),
                    )
                )
            for left_right_alignment, rail in rails_by_alignment.items():
                for front_back_alignment in (Alignment.FRONT, Alignment.BACK):
                    eye = create_filleted_box(
                        mount_eye_diameter_mm,
                        mount_eye_diameter_mm,
                        corner_holder_thickness_mm,
                        fillet_radius=mount_eye_fillet_radius_mm,
                        no_fillets_at=[
                            Alignment.TOP,
                            Alignment.BOTTOM,
                            left_right_alignment.opposite,
                        ],
                    )
                    eye = align(eye, rail, front_back_alignment)
                    eye = align(eye, rail, left_right_alignment.stack_alignment)
                    eye = align(eye, rail, Alignment.BOTTOM)
                    holder = holder.fuse(eye)
            holder_thickness_mm = corner_holder_thickness_mm
            feature_metadata = {
                "rail_count": 2,
                "bridge_count": len(corner_bridge_indices),
                "bridge_pin_indices_from_bottom": list(corner_bridge_indices),
                "eye_count": 4,
            }
        else:
            raise ValueError(
                f"Unsupported rigid downholder {plan.kind.value!r} on {component_id!r}"
            )

        holder_top_z_mm = holder_bottom_z_mm + holder_thickness_mm
        if mount_screw_length_mm <= holder_top_z_mm:
            raise ValueError(
                f"{component_id!r} M2.5 screw does not reach through the base plate"
            )

        component_loose_holes = PartCollector()
        component_self_threading_holes = PartCollector()
        for screw_index, (screw_center_x_mm, screw_center_y_mm) in enumerate(
            normalized_screw_centers,
            start=1,
        ):
            loose_hole = _create_clearance_hole_at(
                center_x_mm=screw_center_x_mm,
                center_y_mm=screw_center_y_mm,
                minimum_z_mm=holder_bottom_z_mm - 1,
                length_mm=holder_thickness_mm + 2,
                diameter_mm=loose_hole_diameter_mm,
            )
            component_loose_holes = component_loose_holes.fuse(loose_hole)
            downholder_loose_holes = downholder_loose_holes.fuse(loose_hole)

            self_threading_hole = create_self_threading_hole_cutter(
                mount_screw_size,
                plate_thickness_mm + 2,
                lead_in=True,
                core_radius_adjustment=self_threading_core_radius_adjustment_mm,
            )
            self_threading_hole = translate(
                screw_center_x_mm,
                screw_center_y_mm,
                -1,
            )(self_threading_hole)
            component_self_threading_holes = component_self_threading_holes.fuse(
                self_threading_hole
            )
            downholder_self_threading_holes = downholder_self_threading_holes.fuse(
                self_threading_hole
            )
            downholder_screw_previews.append(
                (
                    f"downholder_{component_id}_screw_{screw_index}",
                    _create_screw_preview_at(
                        center_x_mm=screw_center_x_mm,
                        center_y_mm=screw_center_y_mm,
                        holder_top_z_mm=holder_top_z_mm,
                        screw_size=mount_screw_size,
                        screw_length_mm=mount_screw_length_mm,
                    ),
                )
            )
            all_screw_centers.append(
                {
                    "component_id": component_id,
                    "center_mm": [screw_center_x_mm, screw_center_y_mm],
                }
            )

        holder = holder.cut(component_loose_holes)
        positioned_downholders.append((component_id, holder))
        downholder_metadata.append(
            {
                "component_id": component_id,
                "kind": plan.kind.value,
                "screw_centers_mm": [
                    list(center) for center in normalized_screw_centers
                ],
                "holder_bottom_z_mm": holder_bottom_z_mm,
                "holder_top_z_mm": holder_top_z_mm,
                "loose_hole_count": len(normalized_screw_centers),
                **feature_metadata,
            }
        )

    if positioned_downholders:
        base_plate = base_plate.cut(downholder_self_threading_holes)

    loose_hole_radius_mm = loose_hole_diameter_mm / 2
    for screw_center in all_screw_centers:
        center_x_mm, center_y_mm = screw_center["center_mm"]
        for slot in pin_row_slot_metadata:
            minimum_x_mm, minimum_y_mm = slot["minimum_mm"]
            maximum_x_mm, maximum_y_mm = slot["maximum_mm"]
            closest_x_mm = min(max(center_x_mm, minimum_x_mm), maximum_x_mm)
            closest_y_mm = min(max(center_y_mm, minimum_y_mm), maximum_y_mm)
            distance_mm = math.hypot(
                center_x_mm - closest_x_mm,
                center_y_mm - closest_y_mm,
            )
            if distance_mm < loose_hole_radius_mm - 1e-6:
                raise ValueError(
                    f"Downholder screw for {screw_center['component_id']!r} "
                    f"collides with pin slot {slot['component_id']!r}/"
                    f"{slot['pin_set_id']!r}"
                )

    if row_slot_count:
        base_plate = base_plate.cut(pin_row_slots)
    if individual_hole_count:
        base_plate = base_plate.cut(individual_pin_pass_throughs)

    assembly = LeaderFollowersCuttersPart(base_plate)
    if row_slot_count:
        assembly.add_named_cutter(pin_row_slots, "pin_row_slots")
    if individual_hole_count:
        assembly.add_named_cutter(
            individual_pin_pass_throughs,
            "individual_pin_pass_throughs",
        )
    if pin_line_clamp_recess_count:
        assembly.add_named_cutter(
            pin_line_clamp_recesses,
            "pin_line_clamp_recesses",
        )
    if positioned_downholders:
        assembly.add_named_cutter(
            downholder_self_threading_holes,
            "downholder_self_threading_holes",
        )
        assembly.add_named_cutter(
            downholder_loose_holes,
            "downholder_loose_holes",
        )
    if pico_usb_cable_cutter is not None:
        assembly.add_named_cutter(
            pico_usb_cable_cutter,
            "pico_usb_cable_passage",
        )
        assembly.add_named_non_production_part(
            pico_usb_connector_preview,
            "pico_usb_connector",
        )

    for component_id, holder in positioned_downholders:
        assembly.add_named_follower(holder, f"downholder_{component_id}")
    for screw_name, screw in downholder_screw_previews:
        assembly.add_named_non_production_part(screw, screw_name)

    for component_id, pin_line_clamp in positioned_pin_line_clamps:
        assembly.add_named_non_production_part(
            pin_line_clamp.get_named_non_production_part("pins"),
            f"pin_line_{component_id}_pins",
        )
        assembly.add_named_non_production_part(
            pin_line_clamp.get_named_non_production_part("top_pins"),
            f"pin_line_{component_id}_top_pins",
        )

    for component_id, pin_set_id, pin_header in positioned_pin_headers:
        preview_name = f"pin_header_{component_id}_{pin_set_id}"
        assembly.add_named_non_production_part(
            pin_header.leader,
            f"{preview_name}_pins",
        )
        assembly.add_named_non_production_part(
            pin_header.get_follower_part_by_name("top_pins"),
            f"{preview_name}_top_pins",
        )

    normalized_envelopes: dict[str, dict[str, Any]] = {}
    component_preview_parts = {}
    for envelope in component_envelopes:
        minimum_x_mm = envelope.minimum_x_mm - plate_source_minimum_x_mm
        minimum_y_mm = envelope.minimum_y_mm - plate_source_minimum_y_mm
        normalized_envelopes[envelope.component_id] = {
            "minimum_mm": [minimum_x_mm, minimum_y_mm],
            "maximum_mm": [
                envelope.maximum_x_mm - plate_source_minimum_x_mm,
                envelope.maximum_y_mm - plate_source_minimum_y_mm,
            ],
            "box_id": envelope.box_id,
        }

        if envelope.box_id is None:
            if envelope.component_id in pin_line_clamp_component_ids:
                continue
            component_body = create_box(
                envelope.width_mm,
                envelope.depth_mm,
                envelope.body_height_mm,
                origin=(minimum_x_mm, minimum_y_mm, plate_thickness_mm),
            )
            assembly.add_named_non_production_part(
                component_body,
                f"component_{envelope.component_id}",
            )
            component_preview_parts[envelope.component_id] = component_body
            continue

        if reference_frame_width_mm * 2 >= min(envelope.width_mm, envelope.depth_mm):
            raise ValueError(f"Reference frame is too wide for box {envelope.box_id!r}")
        frame = PartCollector()
        frame = frame.fuse(
            create_box(
                envelope.width_mm,
                reference_frame_width_mm,
                reference_frame_height_mm,
                origin=(minimum_x_mm, minimum_y_mm, plate_thickness_mm),
            )
        )
        frame = frame.fuse(
            create_box(
                envelope.width_mm,
                reference_frame_width_mm,
                reference_frame_height_mm,
                origin=(
                    minimum_x_mm,
                    minimum_y_mm + envelope.depth_mm - reference_frame_width_mm,
                    plate_thickness_mm,
                ),
            )
        )
        frame = frame.fuse(
            create_box(
                reference_frame_width_mm,
                envelope.depth_mm - 2 * reference_frame_width_mm,
                reference_frame_height_mm,
                origin=(
                    minimum_x_mm,
                    minimum_y_mm + reference_frame_width_mm,
                    plate_thickness_mm,
                ),
            )
        )
        frame = frame.fuse(
            create_box(
                reference_frame_width_mm,
                envelope.depth_mm - 2 * reference_frame_width_mm,
                reference_frame_height_mm,
                origin=(
                    minimum_x_mm + envelope.width_mm - reference_frame_width_mm,
                    minimum_y_mm + reference_frame_width_mm,
                    plate_thickness_mm,
                ),
            )
        )
        assembly.add_named_non_production_part(
            frame,
            f"reference_{envelope.box_id}",
        )
        component_preview_parts[envelope.component_id] = frame

    for holder_index, (component_id, holder) in enumerate(positioned_downholders):
        if pico_usb_bridge is not None and _parts_have_common_volume(
            holder, pico_usb_bridge
        ):
            raise ValueError(
                f"Downholder {component_id!r} collides with the Pico USB bridge"
            )
        for other_component_id, other_part in component_preview_parts.items():
            if other_component_id == component_id:
                continue
            if _parts_have_common_volume(holder, other_part):
                raise ValueError(
                    f"Downholder {component_id!r} collides with component "
                    f"{other_component_id!r}"
                )
        for other_component_id, other_holder in positioned_downholders[
            holder_index + 1 :
        ]:
            if _parts_have_common_volume(holder, other_holder):
                raise ValueError(
                    f"Downholder {component_id!r} collides with downholder "
                    f"{other_component_id!r}"
                )

    assembly.additional_data.update(
        {
            "pinout_yaml_path": str(pinout_yaml_path),
            "raster_pitch_mm": raster_pitch_mm,
            "plate_source_origin_mm": [
                plate_source_minimum_x_mm,
                plate_source_minimum_y_mm,
            ],
            "plate_size_mm": [plate_width_mm, plate_depth_mm, plate_thickness_mm],
            "pin_hole_size_mm": pin_hole_size_mm,
            "pin_pass_throughs": pin_pass_through_centers_mm,
            "individual_pin_pass_throughs": individual_pin_pass_through_metadata,
            "pin_row_slots": pin_row_slot_metadata,
            "pin_line_clamp_component_ids": sorted(pin_line_clamp_component_ids),
            "component_envelopes": normalized_envelopes,
            "downholders": downholder_metadata,
            "downholder_screw_centers": all_screw_centers,
            "plate_margins_mm": {
                "left": plate_border_left_mm,
                "right": plate_border_right_mm,
                "top": plate_border_top_mm,
                "bottom": plate_border_bottom_mm,
            },
            "pico_usb_bridge": pico_usb_bridge_metadata,
        }
    )
    return assembly
