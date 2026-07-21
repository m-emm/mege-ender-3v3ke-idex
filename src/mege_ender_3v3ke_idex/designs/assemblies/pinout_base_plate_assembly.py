"""Generate a fitted electronics base plate from a mege-circuits pinout."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from mege_circuits.simple import PinoutPhysicalComponent, load_pinout_config
from shellforgepy.simple import *


@dataclass(frozen=True)
class ComponentProfile:
    """Assembly-supplied physical body dimensions around a pin envelope."""

    left_margin_mm: float
    right_margin_mm: float
    top_margin_mm: float
    bottom_margin_mm: float
    body_height_mm: float


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
    profiles: dict[str, ComponentProfile] = {}
    for component_type, raw_profile in raw_profiles.items():
        if not isinstance(raw_profile, Mapping):
            raise ValueError(f"Component profile {component_type!r} must be a mapping")
        missing_fields = [name for name in field_names if name not in raw_profile]
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
        profiles[str(component_type)] = ComponentProfile(**values)
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
    reference_frame_width_mm = float(pinout_base_plate_reference_frame_width)
    reference_frame_height_mm = float(pinout_base_plate_reference_frame_height)

    positive_dimensions = {
        "pinout_base_plate_raster_pitch": raster_pitch_mm,
        "pinout_base_plate_thickness": plate_thickness_mm,
        "pinout_base_plate_pin_tail_width": pin_tail_width_mm,
        "pinout_base_plate_reference_frame_width": reference_frame_width_mm,
        "pinout_base_plate_reference_frame_height": reference_frame_height_mm,
    }
    for name, value in positive_dimensions.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    if plate_border_mm < 0 or pin_clearance_mm < 0:
        raise ValueError(
            "Plate border and pin pass-through clearance must be non-negative"
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

    through_pin_names: list[tuple[PinoutPhysicalComponent, str]] = []
    for component in pinout_project.physical_components:
        for pin_set_id in component.through_pin_sets:
            for pin_name in pinout_project.pin_sets[pin_set_id]:
                through_pin_names.append((component, pin_name))

    pin_hole_size_mm = pin_tail_width_mm + 2 * pin_clearance_mm
    pin_pass_throughs = PartCollector()
    pin_pass_through_centers_mm: list[dict[str, Any]] = []
    for component, pin_name in through_pin_names:
        source_x, source_y = pinout_project.pin_positions[pin_name]
        center_x_mm = source_x * raster_pitch_mm - plate_source_minimum_x_mm
        center_y_mm = source_y * raster_pitch_mm - plate_source_minimum_y_mm
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
        pin_pass_throughs = pin_pass_throughs.fuse(pin_pass_through)
        pin_pass_through_centers_mm.append(
            {
                "component_id": component.id,
                "pin_name": pin_name,
                "center_mm": [center_x_mm, center_y_mm],
                "source_raster": [source_x, source_y],
            }
        )

    if through_pin_names:
        base_plate = base_plate.cut(pin_pass_throughs)

    assembly = LeaderFollowersCuttersPart(base_plate)
    if through_pin_names:
        assembly.add_named_cutter(pin_pass_throughs, "pin_pass_throughs")

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
            "component_envelopes": normalized_envelopes,
        }
    )
    return assembly
