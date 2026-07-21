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
        pass_through_style = str(raw_profile["pass_through_style"]).strip()
        if pass_through_style not in allowed_pass_through_styles:
            raise ValueError(
                f"Component profile {component_type!r} pass_through_style must be "
                f"one of {sorted(allowed_pass_through_styles)}"
            )
        profiles[str(component_type)] = ComponentProfile(
            **values,
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


def create_pinout_base_plate_assembly(
    *,
    pinout_base_plate_pinout_yaml_path,
    pinout_base_plate_raster_pitch,
    pinout_base_plate_thickness,
    pinout_base_plate_border,
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
    pinout_base_plate_component_profiles,
) -> LeaderFollowersCuttersPart:
    """Create the Phase 2 base plate, pin holes, and reference geometry."""

    raster_pitch_mm = float(pinout_base_plate_raster_pitch)
    plate_thickness_mm = float(pinout_base_plate_thickness)
    plate_border_mm = float(pinout_base_plate_border)
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
    }
    for name, value in positive_dimensions.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    non_negative_dimensions = {
        "pinout_base_plate_border": plate_border_mm,
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
            "Plate border and pin-row/pass-through clearances must be non-negative"
        )

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

    component_minimum_x_mm = min(
        envelope.minimum_x_mm for envelope in component_envelopes
    )
    component_minimum_y_mm = min(
        envelope.minimum_y_mm for envelope in component_envelopes
    )
    component_maximum_x_mm = max(
        envelope.maximum_x_mm for envelope in component_envelopes
    )
    component_maximum_y_mm = max(
        envelope.maximum_y_mm for envelope in component_envelopes
    )
    plate_source_minimum_x_mm = component_minimum_x_mm - plate_border_mm
    plate_source_minimum_y_mm = component_minimum_y_mm - plate_border_mm
    plate_width_mm = (
        component_maximum_x_mm - component_minimum_x_mm + 2 * plate_border_mm
    )
    plate_depth_mm = (
        component_maximum_y_mm - component_minimum_y_mm + 2 * plate_border_mm
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
                base_plate,
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
                f"Pin-line clamp component {component.id!r} requires one through pin set"
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
            base_plate,
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
        }
    )
    return assembly
