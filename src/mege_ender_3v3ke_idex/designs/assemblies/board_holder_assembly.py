"""Assembly wrapper for the simplified MCU board holder."""

import math

from mege_ender_3v3ke_idex.designs.plug_and_hole import create_plug
from shellforgepy.simple import *

COVER_PLUG_GRID_PLACES = 20
COVER_PLUG_BOARD_CLEARANCE = 1.5
COVER_PLUG_MIN_DISTANCE = 18

BOARD_HOLDER_SIDE_WALL_THICKNESS = 2.2

BOARD_HOLDER_LID_THICKNESS = 1.2
BOARD_HOLDER_LID_BODY_CLEARANCE = 0.4
BOARD_HOLDER_LID_FILLET_RADIUS = 3.0
BOARD_HOLDER_LID_RIM_HEIGHT = 5.0
BOARD_HOLDER_LID_RIM_THICKNESS = BOARD_HOLDER_SIDE_WALL_THICKNESS
BOARD_HOLDER_LID_RIM_CLEARANCE = 0.25
BOARD_HOLDER_LID_RIM_FILLET_RADIUS = min(
    0.8,
    BOARD_HOLDER_LID_RIM_THICKNESS * 0.4,
)
BOARD_HOLDER_LID_HOLDER_BODY_CLEARANCE = 0.4
BOARD_HOLDER_LID_HOLDER_DIAMETER = (
    BOARD_HOLDER_LID_RIM_HEIGHT * 0.75 - 2 * BOARD_HOLDER_LID_HOLDER_BODY_CLEARANCE
)
BOARD_HOLDER_LID_HOLDER_X_INSET = 20.0
BOARD_HOLDER_LID_HOLDER_CLEARANCE = 0.2
BOARD_HOLDER_LID_AIR_HOLE_SIZE = 4.0
BOARD_HOLDER_LID_AIR_HOLE_SPACING = 10.0
BOARD_HOLDER_LID_AIR_HOLE_BORDER = 6.0
BOARD_HOLDER_MOUNT_HARDWARE_CLEARANCE = 1.2
BOARD_HOLDER_MOUNT_SCREW_EXPOSED_THREAD = 1.0


board_holder_elko_diameter = 10.15
board_holder_elko_height = 15.61
board_holder_elko_pin_pitch = 4.2
board_holder_elko_pin_length = 8
board_holder_elko_pin_diameter = 0.8
board_holder_elko_sleve_wall = 1.0
board_holder_elko_sleve_clearance = 0.1
BOARD_HOLDER_ELKO_SLEEVE_BODY_INSERTION = 15
BOARD_HOLDER_ELKO_SLEEVE_PIN_TOP_CLEARANCE = 0.1
BOARD_HOLDER_ELKO_SOCKET_PLATE_THICKNESS = 1.2
BOARD_HOLDER_ELKO_SOCKET_PLATE_MARGIN = 1.2
BIG_THING = 500


def create_elko():

    body = create_cylinder(board_holder_elko_diameter / 2, board_holder_elko_height)
    pins = PartCollector()
    for i in [0, 1]:
        pin = create_cylinder(
            board_holder_elko_pin_diameter / 2,
            board_holder_elko_pin_length,
            origin=(
                0,
                (-1) ** i * board_holder_elko_pin_pitch / 2,
                -board_holder_elko_pin_length,
            ),
        )
        pins = pins.fuse(pin)

    pins = align(pins, body, Alignment.CENTER)
    pins = align(pins, body, Alignment.STACK_TOP)

    return body.fuse(pins)


def create_elko_sleeve():
    sleeve_height = (
        board_holder_elko_pin_length
        + board_holder_elko_sleve_wall
        + BOARD_HOLDER_ELKO_SLEEVE_BODY_INSERTION
        + BOARD_HOLDER_ELKO_SLEEVE_PIN_TOP_CLEARANCE
    )
    elko_sleeve_body = create_cylinder(
        board_holder_elko_diameter / 2
        + board_holder_elko_sleve_wall
        + board_holder_elko_sleve_clearance,
        sleeve_height,
    )

    elko_sleeve_inner_cutter = create_cylinder(
        board_holder_elko_diameter / 2 + board_holder_elko_sleve_clearance,
        BIG_THING + sleeve_height,
        origin=(0, 0, -BIG_THING),
    )
    elko_sleeve_cutter = align(
        elko_sleeve_inner_cutter,
        elko_sleeve_body,
        Alignment.CENTER,
        axes=[0, 1],
    )
    elko_sleeve_cutter = translate(
        0,
        0,
        -board_holder_elko_sleve_wall,
    )(elko_sleeve_cutter)
    elko_sleeve = elko_sleeve_body.cut(elko_sleeve_cutter)

    return elko_sleeve


def _create_elko_sleeve_with_elko():
    sleeve = create_elko_sleeve()
    elko = create_elko()
    elko = align(elko, sleeve, Alignment.CENTER, axes=[0, 1])
    elko_bbox = get_bounding_box(elko)
    sleeve_bbox = get_bounding_box(sleeve)
    elko_pin_top_z = (
        sleeve_bbox[1][2]
        - board_holder_elko_sleve_wall
        - BOARD_HOLDER_ELKO_SLEEVE_PIN_TOP_CLEARANCE
    )
    elko = translate(0, 0, elko_pin_top_z - elko_bbox[1][2])(elko)

    return LeaderFollowersCuttersPart(
        leader=sleeve,
        non_production_parts=[elko],
        non_production_names=["elko"],
    )


def _create_elko_socket_assembly_for_tmc_board(
    *,
    tmc_board,
):
    tmc_dil = tmc_board.get_follower_part_by_name("dil")
    sleeve_with_elko = _create_elko_sleeve_with_elko()
    sleeve_with_elko = rotate(90, axis=(0, 1, 0))(sleeve_with_elko)
    sleeve_with_elko = rotate(90, axis=(0, 0, 1))(sleeve_with_elko)
    sleeve_with_elko = rotate(180, axis=(0, 0, 1))(sleeve_with_elko)

    tmc_dil_size = get_bounding_box_size(tmc_dil)
    sleeve_size = get_bounding_box_size(sleeve_with_elko.leader)
    socket_plate = create_box(
        tmc_dil_size[0] + 2 * BOARD_HOLDER_ELKO_SOCKET_PLATE_MARGIN,
        tmc_dil_size[1] / 2,
        BOARD_HOLDER_ELKO_SOCKET_PLATE_THICKNESS,
    )
    socket_plate = align(socket_plate, tmc_dil, Alignment.CENTER, axes=[0])
    socket_plate = align(socket_plate, tmc_dil, Alignment.FRONT)
    socket_plate = align(socket_plate, tmc_dil, Alignment.BOTTOM)
    socket_plate = socket_plate.cut(
        tmc_board.get_cutter_part_by_name("left_pin_cutters")
    )
    socket_plate = socket_plate.cut(
        tmc_board.get_cutter_part_by_name("right_pin_cutters")
    )

    sleeve_with_elko = align(
        sleeve_with_elko,
        socket_plate,
        Alignment.CENTER,
        axes=[0],
    )
    sleeve_with_elko = align(sleeve_with_elko, socket_plate, Alignment.FRONT)
    sleeve_with_elko = align(
        sleeve_with_elko,
        socket_plate,
        Alignment.STACK_BOTTOM,
        stack_gap=-board_holder_elko_sleve_wall,
    )

    socket = socket_plate.fuse(sleeve_with_elko.leader)
    return LeaderFollowersCuttersPart(
        leader=socket,
        non_production_parts=[sleeve_with_elko.get_non_production_part_by_name("elko")],
        additional_data={
            "socket_plate_bbox": get_bounding_box(socket_plate),
            "sleeve_bbox": get_bounding_box(sleeve_with_elko.leader),
        },
        non_production_names=["elko"],
    )


def _create_elko_socket_assemblies_for_tmc_boards(
    *,
    positioned_tmc_boards,
):
    socket_assemblies = []
    socket_plate_bboxes = []
    socket_sleeve_bboxes = []
    for tmc_index, current_tmc_board in enumerate(positioned_tmc_boards):
        socket_assembly = _create_elko_socket_assembly_for_tmc_board(
            tmc_board=current_tmc_board,
        )
        socket_plate_bboxes.append(socket_assembly.additional_data["socket_plate_bbox"])
        socket_sleeve_bboxes.append(socket_assembly.additional_data["sleeve_bbox"])
        socket_assemblies.append(socket_assembly.prefixed_copy(f"elko_{tmc_index + 1}"))

    sockets = _fuse_parts(socket_assemblies)
    for socket_index, socket_assembly in enumerate(socket_assemblies, start=1):
        sockets.add_named_follower(
            socket_assembly.leader,
            f"elko_sleeve_plate_{socket_index}",
        )
    sockets.additional_data["socket_plate_bboxes"] = socket_plate_bboxes
    sockets.additional_data["socket_sleeve_bboxes"] = socket_sleeve_bboxes
    return sockets


def _create_enclosing_base_plate(
    *,
    enclosure_reference,
    base_plate_border,
    base_plate_thickness,
    board_z_offset,
):
    enclosure_size = get_bounding_box_size(enclosure_reference)
    base_plate_x_size = enclosure_size[0] + 2 * base_plate_border
    base_plate_y_size = enclosure_size[1] + 2 * base_plate_border

    base_plate = create_box(
        base_plate_x_size,
        base_plate_y_size,
        base_plate_thickness,
    )
    base_plate = align(base_plate, enclosure_reference, Alignment.CENTER, axes=[0, 1])
    base_plate_bbox = get_bounding_box(base_plate)
    base_plate = translate(0, 0, board_z_offset - base_plate_bbox[1][2])(base_plate)

    return base_plate


def _fuse_parts(parts):
    if not parts:
        raise ValueError("Need at least one part to fuse.")

    fused = parts[0]
    for part in parts[1:]:
        fused = fused.fuse(part)
    return fused


def _create_y_facing_hemisphere(radius, front_back, big_thing):
    if front_back not in [Alignment.FRONT, Alignment.BACK]:
        raise ValueError("Hemisphere direction must be FRONT or BACK")

    sphere = create_sphere(radius)
    cut_positive_y = front_back == Alignment.FRONT
    cutter = create_box(
        big_thing,
        big_thing,
        big_thing,
        origin=(
            -big_thing / 2,
            0 if cut_positive_y else -big_thing,
            -big_thing / 2,
        ),
    )
    return sphere.cut(cutter)


def _create_board_holder_lid_air_hole_cutter(lid, big_thing):
    lid_size = get_bounding_box_size(lid)

    num_air_holes_x = math.floor(
        (lid_size[0] - 2 * BOARD_HOLDER_LID_AIR_HOLE_BORDER)
        / BOARD_HOLDER_LID_AIR_HOLE_SPACING
    )
    num_air_holes_y = math.floor(
        (lid_size[1] - 2 * BOARD_HOLDER_LID_AIR_HOLE_BORDER)
        / BOARD_HOLDER_LID_AIR_HOLE_SPACING
    )

    air_holes = PartCollector()
    for x_index in range(max(0, num_air_holes_x)):
        for y_index in range(max(0, num_air_holes_y)):
            air_hole = create_box(
                BOARD_HOLDER_LID_AIR_HOLE_SIZE,
                BOARD_HOLDER_LID_AIR_HOLE_SIZE,
                big_thing,
            )
            air_hole = rotate(45, axis=(0, 0, 1))(air_hole)
            air_hole = translate(
                x_index * BOARD_HOLDER_LID_AIR_HOLE_SPACING,
                y_index * BOARD_HOLDER_LID_AIR_HOLE_SPACING,
                0,
            )(air_hole)
            air_holes = air_holes.fuse(air_hole)

    air_holes = align(air_holes, lid, Alignment.CENTER)
    return air_holes


def _create_board_holder_lid_holders(rim, holder_z_alignment, big_thing):
    if holder_z_alignment not in [Alignment.TOP, Alignment.BOTTOM]:
        raise ValueError("Lid holder z alignment must be TOP or BOTTOM")

    holder_radius = BOARD_HOLDER_LID_HOLDER_DIAMETER / 2
    cutter_radius = holder_radius + BOARD_HOLDER_LID_HOLDER_CLEARANCE

    holders = PartCollector()
    holder_cutters = []
    holder_cutter_names = []

    for left_right in [Alignment.LEFT, Alignment.RIGHT]:
        for front_back in [Alignment.FRONT, Alignment.BACK]:
            holder = _create_y_facing_hemisphere(
                holder_radius,
                front_back,
                big_thing,
            )
            holder = align(holder, rim, left_right.edge_alignment)
            holder = translate(
                -left_right.sign * BOARD_HOLDER_LID_HOLDER_X_INSET,
                0,
                0,
            )(holder)
            holder = align(holder, rim, holder_z_alignment)
            holder = align(holder, rim, front_back.stack_alignment)
            holders = holders.fuse(holder)

            holder_cutter = _create_y_facing_hemisphere(
                cutter_radius,
                front_back,
                big_thing,
            )
            holder_cutter = align(holder_cutter, rim, left_right.edge_alignment)
            holder_cutter = translate(
                -left_right.sign * BOARD_HOLDER_LID_HOLDER_X_INSET,
                0,
                0,
            )(holder_cutter)
            holder_cutter = align(holder_cutter, rim, Alignment.CENTER, axes=[2])
            holder_cutter = align(holder_cutter, rim, front_back.stack_alignment)
            holder_cutters.append(holder_cutter)
            holder_cutter_names.append(
                f"lid_holder_dimple_{left_right.name.lower()}_"
                f"{front_back.name.lower()}"
            )

    return LeaderFollowersCuttersPart(
        holders,
        cutters=holder_cutters,
        cutter_names=holder_cutter_names,
    )


def _create_board_holder_lid(
    *,
    side_walls,
    lid_alignment,
    big_thing,
    clearance_cutters=None,
):
    if lid_alignment not in [Alignment.TOP, Alignment.BOTTOM]:
        raise ValueError("Board holder lid alignment must be TOP or BOTTOM")

    side_walls_size = get_bounding_box_size(side_walls)

    lid = create_filleted_box(
        side_walls_size[0],
        side_walls_size[1],
        BOARD_HOLDER_LID_THICKNESS,
        fillet_radius=BOARD_HOLDER_LID_FILLET_RADIUS,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    lid = align(lid, side_walls, Alignment.CENTER, axes=[0, 1])
    lid = align(
        lid,
        side_walls,
        lid_alignment.stack_alignment,
        stack_gap=BOARD_HOLDER_LID_BODY_CLEARANCE,
    )

    lid = lid.cut(_create_board_holder_lid_air_hole_cutter(lid, big_thing))

    rim_outer_length = (
        side_walls_size[0]
        - 2 * BOARD_HOLDER_SIDE_WALL_THICKNESS
        - 2 * BOARD_HOLDER_LID_RIM_CLEARANCE
    )
    rim_outer_width = (
        side_walls_size[1]
        - 2 * BOARD_HOLDER_SIDE_WALL_THICKNESS
        - 2 * BOARD_HOLDER_LID_RIM_CLEARANCE
    )
    rim_inner_length = rim_outer_length - 2 * BOARD_HOLDER_LID_RIM_THICKNESS
    rim_inner_width = rim_outer_width - 2 * BOARD_HOLDER_LID_RIM_THICKNESS

    if rim_inner_length <= 0 or rim_inner_width <= 0:
        raise ValueError("Board holder lid inner rim dimensions must be positive")

    rim = create_filleted_box(
        rim_outer_length,
        rim_outer_width,
        BOARD_HOLDER_LID_RIM_HEIGHT,
        fillet_radius=BOARD_HOLDER_LID_RIM_FILLET_RADIUS,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    rim_inner_cutter = create_filleted_box(
        rim_inner_length,
        rim_inner_width,
        big_thing,
        fillet_radius=BOARD_HOLDER_LID_RIM_FILLET_RADIUS,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    rim_inner_cutter = align(rim_inner_cutter, rim, Alignment.CENTER, axes=[0, 1])
    rim_inner_cutter = align(rim_inner_cutter, rim, Alignment.CENTER, axes=[2])
    rim = rim.cut(rim_inner_cutter)

    rim = align(rim, lid, Alignment.CENTER, axes=[0, 1])
    if lid_alignment == Alignment.TOP:
        rim = align(rim, lid, Alignment.STACK_BOTTOM)
        holder_z_alignment = Alignment.BOTTOM
    else:
        rim = align(rim, lid, Alignment.STACK_TOP)
        holder_z_alignment = Alignment.TOP

    holders = _create_board_holder_lid_holders(
        rim,
        holder_z_alignment,
        big_thing,
    )
    lid_part = LeaderFollowersCuttersPart(lid.fuse(rim))
    lid_part = lid_part.fuse(holders)

    if clearance_cutters is not None:
        lid_part.leader = lid_part.leader.cut(clearance_cutters)

    return lid_part


def _get_mount_hardware_clearance_radius(screw_size):
    screw = MScrew.from_size(screw_size)
    nut_corner_diameter = screw.nut_size / math.cos(math.radians(30))
    return (
        max(
            screw.cylinder_head_diameter,
            screw.nut_circle_diameter,
            nut_corner_diameter,
        )
        / 2
        + BOARD_HOLDER_MOUNT_HARDWARE_CLEARANCE
    )


def _create_mount_hardware_lid_clearance_cutters(
    *,
    mount_screw_positions,
    screw_size,
    big_thing,
):
    clearance_radius = _get_mount_hardware_clearance_radius(screw_size)
    cutters = PartCollector()
    for position in mount_screw_positions:
        cutter = create_cylinder(
            clearance_radius,
            big_thing,
            origin=(position[0], position[1], -big_thing / 2),
        )
        cutters = cutters.fuse(cutter)

    return cutters


def _create_mount_hardware(
    *,
    mount_screw_positions,
    screw_size,
    screw_head_bottom_z,
    side_walls,
):
    screw = MScrew.from_size(screw_size)
    side_walls_bbox = get_bounding_box(side_walls)
    screw_shaft_bottom_z = (
        side_walls_bbox[0][2]
        - screw.nut_thickness
        - BOARD_HOLDER_MOUNT_SCREW_EXPOSED_THREAD
    )
    screw_length = screw_head_bottom_z - screw_shaft_bottom_z
    if screw_length <= 0:
        raise ValueError("Mount screw visual length must be positive")

    mount_screws = PartCollector()
    mount_nuts = PartCollector()
    for position in mount_screw_positions:
        mount_screw = create_cylinder_screw(screw_size, screw_length)
        mount_screw = translate(
            position[0],
            position[1],
            screw_shaft_bottom_z,
        )(mount_screw)
        mount_screws = mount_screws.fuse(mount_screw)

        mount_nut = create_nut(screw_size)
        mount_nut = rotate(30)(mount_nut)
        mount_nut = translate(
            position[0],
            position[1],
            side_walls_bbox[0][2] - screw.nut_thickness,
        )(mount_nut)
        mount_nuts = mount_nuts.fuse(mount_nut)

    return mount_screws, mount_nuts


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


def _create_cut_box_from_bbox(
    part,
    *,
    z_min,
    z_height,
    x_enlargement=0.0,
    y_enlargement=0.0,
):
    bbox = get_bounding_box(part)
    return _create_cut_box_from_xy(
        bbox[0][0] - x_enlargement,
        bbox[1][0] + x_enlargement,
        bbox[0][1] - y_enlargement,
        bbox[1][1] + y_enlargement,
        z_min=z_min,
        z_height=z_height,
    )


def _resolve_strap_definitions(
    *,
    board_part,
    dil_pitch,
    strap_pin_indices,
    y_overhang_in_pins=0.5,
):
    board_bbox = get_bounding_box(board_part)

    if strap_pin_indices is None:
        return [
            {
                "pin_index": None,
                "center_y": (board_bbox[0][1] + board_bbox[1][1]) / 2,
            }
        ]

    num_y_pins = int(
        round(
            ((board_bbox[1][1] - board_bbox[0][1]) - 2 * y_overhang_in_pins * dil_pitch)
            / dil_pitch
        )
    )
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


def _get_board_part(board_assembly):
    if "board" in board_assembly.follower_indices_by_name:
        return board_assembly.get_follower_part_by_name("board")

    board_follower_names = [
        name
        for name in board_assembly.follower_indices_by_name
        if name.endswith("_board")
    ]
    if len(board_follower_names) != 1:
        raise ValueError("Could not resolve a unique board follower.")
    return board_assembly.get_follower_part_by_name(board_follower_names[0])


def _cut_cover_window_for_dil_board(
    *,
    cover,
    board_part,
    cover_z_min,
    tpu_cover_thickness,
    overlap_mm,
    strap_width,
    dil_pitch,
    strap_pin_indices,
):
    board_bbox = get_bounding_box(board_part)
    x_min = board_bbox[0][0] + overlap_mm
    x_max = board_bbox[1][0] - overlap_mm
    y_min = board_bbox[0][1] + overlap_mm
    y_max = board_bbox[1][1] - overlap_mm

    if x_max <= x_min:
        raise ValueError("Cover overlap left no window width for board.")

    board_window = _create_cut_box_from_xy(
        x_min,
        x_max,
        y_min,
        y_max,
        z_min=cover_z_min - 1.0,
        z_height=tpu_cover_thickness + 2.0,
    )
    cover = cover.cut(board_window)

    strap_metadata = []
    for strap_index, strap_definition in enumerate(
        _resolve_strap_definitions(
            board_part=board_part,
            dil_pitch=dil_pitch,
            strap_pin_indices=strap_pin_indices,
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
        strap_metadata.append(
            {
                "pin_index": strap_definition["pin_index"],
                "center_y": strap_definition["center_y"],
                "width": strap_width,
                "bbox": get_bounding_box(strap),
            }
        )

    return cover, strap_metadata


def _cut_cover_window_for_part_bbox(
    *,
    cover,
    part,
    cover_z_min,
    tpu_cover_thickness,
    x_enlargement=0.0,
    y_enlargement=0.0,
):
    window = _create_cut_box_from_bbox(
        part,
        z_min=cover_z_min - 1.0,
        z_height=tpu_cover_thickness + 2.0,
        x_enlargement=x_enlargement,
        y_enlargement=y_enlargement,
    )
    return cover.cut(window)


def _create_tpu_cover(
    *,
    base_plate,
    pico_board,
    translated_tmc_boards,
    additional_pins,
    mosfet_driver_board,
    x_axis_mcu_dil_pitch,
    board_holder_tpu_cover_thickness,
    board_holder_tpu_cover_gap_above_base,
    board_holder_tpu_cover_pin_overlap_in_pitches,
    board_holder_tpu_cover_cross_strap_width_in_pitches,
):
    if board_holder_tpu_cover_gap_above_base < 0:
        raise ValueError("board_holder_tpu_cover_gap_above_base must be non-negative.")

    base_bbox = get_bounding_box(base_plate)
    cover_z_min = base_bbox[1][2] + board_holder_tpu_cover_gap_above_base
    cover = create_box(
        base_bbox[1][0] - base_bbox[0][0],
        base_bbox[1][1] - base_bbox[0][1],
        board_holder_tpu_cover_thickness,
        origin=(base_bbox[0][0], base_bbox[0][1], cover_z_min),
    )

    overlap_mm = board_holder_tpu_cover_pin_overlap_in_pitches * x_axis_mcu_dil_pitch
    strap_width = (
        board_holder_tpu_cover_cross_strap_width_in_pitches * x_axis_mcu_dil_pitch
    )

    strap_metadata = {"pico_board": [], "tmc_boards": []}

    cover, strap_metadata["pico_board"] = _cut_cover_window_for_dil_board(
        cover=cover,
        board_part=_get_board_part(pico_board),
        cover_z_min=cover_z_min,
        tpu_cover_thickness=board_holder_tpu_cover_thickness,
        overlap_mm=overlap_mm,
        strap_width=strap_width,
        dil_pitch=x_axis_mcu_dil_pitch,
        strap_pin_indices=[3, 10, 17],
    )

    connector_part = pico_board.get_non_production_part_by_name("micro_usb_socket")
    connector_size = get_bounding_box_size(connector_part)
    connector_window = materialize_bounding_box(
        connector_part,
        x_enlargement=0.5 * connector_size[0],
        y_enlargement=2 * connector_size[1],
        z_enlargement=board_holder_tpu_cover_thickness + 1.0,
    )
    connector_window = align(connector_window, connector_part, Alignment.FRONT)
    cover = cover.cut(connector_window)

    for tmc_board in translated_tmc_boards:
        cover, current_tmc_strap_metadata = _cut_cover_window_for_dil_board(
            cover=cover,
            board_part=_get_board_part(tmc_board),
            cover_z_min=cover_z_min,
            tpu_cover_thickness=board_holder_tpu_cover_thickness,
            overlap_mm=overlap_mm,
            strap_width=strap_width,
            dil_pitch=x_axis_mcu_dil_pitch,
            strap_pin_indices=[5],
        )
        strap_metadata["tmc_boards"].append(current_tmc_strap_metadata)

    if mosfet_driver_board is not None:
        mosfet_clearance_reference = _fuse_parts(
            [
                mosfet_driver_board.get_follower_part_by_name("terminal_block_front"),
                mosfet_driver_board.get_follower_part_by_name("terminal_block_back"),
                mosfet_driver_board.get_follower_part_by_name("mosfet_package_front"),
                mosfet_driver_board.get_follower_part_by_name("mosfet_package_back"),
            ]
        )

        mosfet_clearance_reference = materialize_bounding_box(
            mosfet_clearance_reference, x_enlargement=0.5, y_enlargement=2
        )

        cover = _cut_cover_window_for_part_bbox(
            cover=cover,
            part=mosfet_clearance_reference,
            cover_z_min=cover_z_min,
            tpu_cover_thickness=board_holder_tpu_cover_thickness,
            x_enlargement=0.25 * x_axis_mcu_dil_pitch,
            y_enlargement=0.25 * x_axis_mcu_dil_pitch,
        )

    return cover, strap_metadata


def _distance_xy(point_a, point_b):
    x_distance = point_a[0] - point_b[0]
    y_distance = point_a[1] - point_b[1]
    return (x_distance * x_distance + y_distance * y_distance) ** 0.5


def _distance_to_bbox_xy(point, bbox):
    x_distance = max(bbox[0][0] - point[0], 0, point[0] - bbox[1][0])
    y_distance = max(bbox[0][1] - point[1], 0, point[1] - bbox[1][1])
    return (x_distance * x_distance + y_distance * y_distance) ** 0.5


def _point_clears_board_keepouts(point, board_keepout_bboxes, required_clearance):
    for board_keepout_bbox in board_keepout_bboxes:
        if _distance_to_bbox_xy(point, board_keepout_bbox) < required_clearance:
            return False
    return True


def _point_clears_plugs(point, existing_points):
    for existing_point in existing_points:
        if _distance_xy(point, existing_point) < COVER_PLUG_MIN_DISTANCE:
            return False
    return True


def _point_matches_existing_plug(point, existing_points):
    for existing_point in existing_points:
        if _distance_xy(point, existing_point) < 1e-6:
            return True
    return False


def _grid_values(min_value, max_value):
    step = (max_value - min_value) / (COVER_PLUG_GRID_PLACES - 1)
    return [min_value + step * index for index in range(COVER_PLUG_GRID_PLACES)]


def _create_cover_plug_positions(
    *,
    cover,
    board_keepout_bboxes,
    board_holder_plug_corner_inset,
    board_holder_plug_diameter,
):
    cover_bbox = get_bounding_box(cover)
    x_min = cover_bbox[0][0] + board_holder_plug_corner_inset
    x_max = cover_bbox[1][0] - board_holder_plug_corner_inset
    y_min = cover_bbox[0][1] + board_holder_plug_corner_inset
    y_max = cover_bbox[1][1] - board_holder_plug_corner_inset

    if x_max <= x_min or y_max <= y_min:
        raise ValueError("Cover is too small for inset cover plug placement.")

    board_clearance = board_holder_plug_diameter / 2 + COVER_PLUG_BOARD_CLEARANCE
    plug_positions = [
        (x_min, y_min),
        (x_min, y_max),
        (x_max, y_min),
        (x_max, y_max),
    ]

    for plug_index, plug_position in enumerate(plug_positions):
        if not _point_clears_board_keepouts(
            plug_position,
            board_keepout_bboxes,
            board_clearance,
        ):
            raise ValueError(
                f"Corner cover plug {plug_index} violates board clearance."
            )
        if not _point_clears_plugs(plug_position, plug_positions[:plug_index]):
            raise ValueError("Corner cover plugs are closer than the minimum distance.")

    candidate_positions = []
    for x_pos in _grid_values(x_min, x_max):
        for y_pos in _grid_values(y_min, y_max):
            candidate_position = (x_pos, y_pos)
            if _point_matches_existing_plug(candidate_position, plug_positions):
                continue
            if _point_clears_board_keepouts(
                candidate_position,
                board_keepout_bboxes,
                board_clearance,
            ):
                candidate_positions.append(candidate_position)

    while True:
        valid_candidate_positions = [
            candidate_position
            for candidate_position in candidate_positions
            if _point_clears_plugs(candidate_position, plug_positions)
        ]
        if not valid_candidate_positions:
            break

        best_candidate_position = max(
            valid_candidate_positions,
            key=lambda candidate_position: min(
                _distance_xy(candidate_position, plug_position)
                for plug_position in plug_positions
            ),
        )
        plug_positions.append(best_candidate_position)
        candidate_positions.remove(best_candidate_position)

    return plug_positions


def _create_cover_plugs(
    *,
    cover,
    base_part,
    big_thing,
    board_keepout_bboxes,
    board_holder_tpu_cover_gap_above_base,
    board_holder_plug_corner_inset,
    board_holder_plug_diameter,
    board_holder_plug_angle_deg,
    board_holder_plug_height,
    board_holder_plug_wall_thickness,
    board_holder_plug_base_thickness,
    board_holder_plug_slit_width,
    board_holder_plug_fillet_radius,
    board_holder_plug_lip_height,
    board_holder_plug_lip_size,
    board_holder_plug_lip_top_gap,
    board_holder_plug_no_inner_hole,
    board_holder_plug_hole_slack,
):
    anchor_thickness = 1e-3
    lip_clearance_below_base = 0.1
    plug_positions = _create_cover_plug_positions(
        cover=cover,
        board_keepout_bboxes=board_keepout_bboxes,
        board_holder_plug_corner_inset=board_holder_plug_corner_inset,
        board_holder_plug_diameter=board_holder_plug_diameter,
    )

    plug_anchors = []
    for x_pos, y_pos in plug_positions:
        plug_anchor = create_box(
            anchor_thickness,
            anchor_thickness,
            anchor_thickness,
            origin=(
                x_pos - anchor_thickness / 2,
                y_pos - anchor_thickness / 2,
                -anchor_thickness / 2,
            ),
        )
        plug_anchor = align(plug_anchor, cover, Alignment.BOTTOM)
        plug_anchors.append(plug_anchor)

    cover_with_plugs = cover
    hole_cutters = []
    nominal_effective_plug_height = (
        board_holder_plug_height + board_holder_tpu_cover_gap_above_base
    )
    base_bottom_z = get_bounding_box(base_part)[0][2]
    cover_bottom_z = get_bounding_box(cover)[0][2]
    cover_to_base_bottom_distance = cover_bottom_z - base_bottom_z

    if (
        board_holder_plug_lip_height is not None
        and board_holder_plug_lip_top_gap is not None
    ):
        minimum_effective_plug_height = (
            cover_to_base_bottom_distance
            - board_holder_plug_base_thickness
            + board_holder_plug_lip_top_gap
            + board_holder_plug_lip_height
            + lip_clearance_below_base
        )
    else:
        minimum_effective_plug_height = (
            cover_to_base_bottom_distance
            - board_holder_plug_base_thickness
            + lip_clearance_below_base
        )

    effective_plug_height = max(
        nominal_effective_plug_height,
        minimum_effective_plug_height,
    )

    for plug_anchor in plug_anchors:
        plug = create_plug(
            plug_diameter=board_holder_plug_diameter,
            plug_angle_deg=board_holder_plug_angle_deg,
            plug_height=effective_plug_height,
            plug_wall_thickness=board_holder_plug_wall_thickness,
            plug_base_thickness=board_holder_plug_base_thickness,
            plug_slit_width=board_holder_plug_slit_width,
            fillet_radius=board_holder_plug_fillet_radius,
            plug_lip_height=board_holder_plug_lip_height,
            plug_lip_size=board_holder_plug_lip_size,
            plug_lip_top_gap=board_holder_plug_lip_top_gap,
            no_inner_hole=board_holder_plug_no_inner_hole,
        )
        plug = rotate(180, axis=(1, 0, 0))(plug)
        plug = align(plug, plug_anchor, Alignment.CENTER, axes=[0, 1])
        plug = align(plug, plug_anchor, Alignment.STACK_BOTTOM, stack_gap=0)
        cover_with_plugs = cover_with_plugs.fuse(plug)

        hole_cutter = create_cylinder(
            board_holder_plug_diameter / 2 + board_holder_plug_hole_slack,
            big_thing,
        )
        hole_cutter = align(hole_cutter, plug, Alignment.CENTER)
        hole_cutters.append(hole_cutter)

    return cover_with_plugs, hole_cutters, plug_positions


def _get_named_tmc_board_visual_prefix(index):
    if index == 0:
        return "tmc_board"
    return f"tmc_board_{index + 1}"


def _get_named_tmc_holder_prefix(index):
    if index == 0:
        return "tmc"
    return f"tmc_{index + 1}"


def _cut_base_plate_for_mosfet_driver(
    *,
    base_plate,
    mosfet_driver_board,
):
    base_plate = base_plate.cut(
        mosfet_driver_board.get_cutter_part_by_name("board_clearance")
    )
    base_plate = base_plate.cut(
        mosfet_driver_board.get_cutter_part_by_name("j1_connector_clearance")
    )
    return base_plate


def _create_usb_cover_bridge_parts(
    *,
    pico_board,
    board_holder_usb_cable_hole_width,
    board_holder_usb_cable_hole_height,
    big_thing,
):
    connector_part = pico_board.get_non_production_part_by_name("micro_usb_socket")
    usb_cable_cutter = create_box(
        board_holder_usb_cable_hole_width,
        big_thing,
        board_holder_usb_cable_hole_height,
    )
    usb_cable_cutter = align(usb_cable_cutter, connector_part, Alignment.CENTER)
    usb_cable_cutter = align(usb_cable_cutter, connector_part, Alignment.FRONT)

    bridge_wall_thickness = 2
    usb_cover_bridge = materialize_bounding_box(
        usb_cable_cutter,
        x_enlargement=bridge_wall_thickness,
        z_enlargement=bridge_wall_thickness,
    )
    usb_cover_bridge = usb_cover_bridge.cut(usb_cable_cutter)
    usb_cover_bridge = fit_part_between(
        usb_cover_bridge, (0, 1, 0), limiting_start_part=connector_part
    )

    return connector_part, usb_cable_cutter, usb_cover_bridge


def create_board_holder_assembly(
    *,
    pico_w_board_assembly,
    tmc_board_assembly,
    additional_pins_assembly,
    mosfet_driver_board_assembly=None,
    board_holder_base_plate_border,
    board_holder_base_plate_thickness,
    board_holder_board_z_offset,
    board_holder_mount_screw_size,
    board_holder_mount_screw_hole_inset,
    board_holder_tmc_board_count,
    board_holder_pico_to_tmc_gap_x,
    board_holder_tmc_to_additional_pins_gap_x,
    board_holder_usb_cable_hole_width,
    board_holder_usb_cable_hole_height,
    x_axis_mcu_dil_pitch,
    board_holder_tpu_cover_thickness,
    board_holder_tpu_cover_gap_above_base,
    board_holder_tpu_cover_pin_overlap_in_pitches,
    board_holder_tpu_cover_cross_strap_width_in_pitches,
    board_holder_plug_corner_inset,
    board_holder_plug_diameter,
    board_holder_plug_angle_deg,
    board_holder_plug_height,
    board_holder_plug_wall_thickness,
    board_holder_plug_base_thickness,
    board_holder_plug_slit_width,
    board_holder_plug_fillet_radius,
    board_holder_plug_lip_height,
    board_holder_plug_lip_size,
    board_holder_plug_lip_top_gap,
    board_holder_plug_no_inner_hole,
    board_holder_plug_hole_slack,
    board_holder_frame_mount_eyes_enabled,
    board_holder_frame_mount_eye_screw_size,
    board_holder_frame_mount_eye_width,
    board_holder_frame_mount_eye_thickness,
    board_holder_frame_mount_eye_fillet_radius,
    BIG_THING,
):
    """Create the simplified MCU board holder assembly."""

    pico_board = pico_w_board_assembly.copy()

    if board_holder_tmc_board_count < 1:
        raise ValueError("tmc_board_count must be at least 1")

    pico_board_part = pico_board.get_follower_part_by_name("board")

    positioned_mosfet_driver_board = None
    if mosfet_driver_board_assembly is not None:
        positioned_mosfet_driver_board = rotate(-90)(mosfet_driver_board_assembly)

        positioned_mosfet_driver_board = (
            positioned_mosfet_driver_board.aligned_from_follower(
                "board",
                pico_board_part,
                Alignment.CENTER,
                axes=[0],
            )
        )
        positioned_mosfet_driver_board = (
            positioned_mosfet_driver_board.aligned_from_follower(
                "board", pico_board_part, Alignment.STACK_FRONT, stack_gap=4
            )
        )

    first_tmc_board = tmc_board_assembly.copy()
    first_tmc_board = first_tmc_board.aligned_from_follower(
        "board",
        pico_board_part,
        Alignment.BACK,
    )
    first_tmc_board = first_tmc_board.aligned_from_follower(
        "board",
        pico_board_part,
        Alignment.STACK_RIGHT,
        stack_gap=board_holder_pico_to_tmc_gap_x,
    )

    tmc_board_size = get_bounding_box_size(
        first_tmc_board.get_follower_part_by_name("board")
    )
    pico_board_size = get_bounding_box_size(pico_board_part)
    # Keep the two-board row spanning the same front/back envelope as the Pico board.
    inter_tmc_board_gap = pico_board_size[1] - 2 * tmc_board_size[1]
    if inter_tmc_board_gap < 0:
        raise ValueError("TMC board row gap became negative")

    positioned_tmc_boards = [first_tmc_board]
    tmc_boards = [first_tmc_board]
    previous_tmc_board = first_tmc_board

    for tmc_index in range(1, board_holder_tmc_board_count):
        previous_tmc_board_part = previous_tmc_board.get_follower_part_by_name("board")
        current_tmc_board = tmc_board_assembly.copy()
        current_tmc_board = current_tmc_board.aligned_from_follower(
            "board",
            previous_tmc_board_part,
            Alignment.CENTER,
            axes=[0],
        )
        current_tmc_board = current_tmc_board.aligned_from_follower(
            "board",
            previous_tmc_board_part,
            Alignment.STACK_FRONT,
            stack_gap=inter_tmc_board_gap,
        )
        positioned_tmc_boards.append(current_tmc_board)
        tmc_boards.append(
            current_tmc_board.prefixed_copy(_get_named_tmc_holder_prefix(tmc_index))
        )
        previous_tmc_board = current_tmc_board

    positioned_tmc_board_row = _fuse_parts(tmc_boards)
    first_tmc_board_part = first_tmc_board.get_follower_part_by_name("board")

    additional_pins = additional_pins_assembly.copy()
    additional_pins = additional_pins.aligned_from_follower(
        "additional_pins_base_plate",
        positioned_tmc_board_row,
        Alignment.CENTER,
        axes=[1],
    )
    additional_pins = additional_pins.aligned_from_follower(
        "additional_pins_base_plate",
        first_tmc_board_part,
        Alignment.STACK_RIGHT,
        stack_gap=board_holder_tmc_to_additional_pins_gap_x,
    )

    additional_pins_base_plate = additional_pins.get_follower_part_by_name(
        "additional_pins_base_plate"
    )
    additional_pins_base_plate_bbox = materialize_bounding_box(
        additional_pins_base_plate
    )
    enclosure_reference = pico_board.leaders_followers_fused().fuse(
        positioned_tmc_board_row.leaders_followers_fused()
    )
    enclosure_reference = enclosure_reference.fuse(additional_pins_base_plate_bbox)
    if positioned_mosfet_driver_board is not None:
        enclosure_reference = enclosure_reference.fuse(
            positioned_mosfet_driver_board.leaders_followers_fused()
        )

    base_plate = _create_enclosing_base_plate(
        enclosure_reference=enclosure_reference,
        base_plate_border=board_holder_base_plate_border,
        base_plate_thickness=board_holder_base_plate_thickness,
        board_z_offset=board_holder_board_z_offset,
    )
    additional_pins = additional_pins.aligned_from_follower(
        "additional_pins_base_plate",
        base_plate,
        Alignment.BOTTOM,
    )
    additional_pins_base_plate = additional_pins.get_follower_part_by_name(
        "additional_pins_base_plate"
    )
    additional_pins_base_plate_bbox = materialize_bounding_box(
        additional_pins_base_plate
    )
    base_plate = pico_board.use_as_cutter_on(base_plate)
    base_plate = positioned_tmc_board_row.use_as_cutter_on(base_plate)
    base_plate = base_plate.cut(additional_pins_base_plate_bbox)
    if positioned_mosfet_driver_board is not None:
        base_plate = _cut_base_plate_for_mosfet_driver(
            base_plate=base_plate,
            mosfet_driver_board=positioned_mosfet_driver_board,
        )
    base_plate_mount_top_z = get_bounding_box(base_plate)[1][2]

    all_holders = LeaderFollowersCuttersPart(base_plate.fuse(additional_pins.leader))

    tpu_cover, tpu_cover_strap_metadata = _create_tpu_cover(
        base_plate=all_holders.leader,
        pico_board=pico_board,
        translated_tmc_boards=positioned_tmc_boards,
        additional_pins=additional_pins,
        mosfet_driver_board=positioned_mosfet_driver_board,
        x_axis_mcu_dil_pitch=x_axis_mcu_dil_pitch,
        board_holder_tpu_cover_thickness=board_holder_tpu_cover_thickness,
        board_holder_tpu_cover_gap_above_base=board_holder_tpu_cover_gap_above_base,
        board_holder_tpu_cover_pin_overlap_in_pitches=board_holder_tpu_cover_pin_overlap_in_pitches,
        board_holder_tpu_cover_cross_strap_width_in_pitches=board_holder_tpu_cover_cross_strap_width_in_pitches,
    )
    connector_part, usb_cable_cutter, usb_cover_bridge = _create_usb_cover_bridge_parts(
        pico_board=pico_board,
        board_holder_usb_cable_hole_width=board_holder_usb_cable_hole_width,
        board_holder_usb_cable_hole_height=board_holder_usb_cable_hole_height,
        big_thing=BIG_THING,
    )

    board_keepout_bboxes = [get_bounding_box(_get_board_part(pico_board))]
    for current_tmc_board in positioned_tmc_boards:
        board_keepout_bboxes.append(
            get_bounding_box(_get_board_part(current_tmc_board))
        )
    if positioned_mosfet_driver_board is not None:
        board_keepout_bboxes.append(
            get_bounding_box(_get_board_part(positioned_mosfet_driver_board))
        )
    board_keepout_bboxes.append(
        get_bounding_box(additional_pins.get_non_production_part_by_name("pins"))
    )
    board_keepout_bboxes.append(
        get_bounding_box(additional_pins.get_non_production_part_by_name("top_pins"))
    )
    usb_cover_bridge_keepout_bbox = get_bounding_box(
        materialize_bounding_box(
            usb_cover_bridge,
            x_enlargement=0.2,
            y_enlargement=0.2,
        )
    )
    board_keepout_bboxes.append(usb_cover_bridge_keepout_bbox)

    tpu_cover, cover_plug_hole_cutters, cover_plug_positions = _create_cover_plugs(
        cover=tpu_cover,
        base_part=all_holders.leader,
        big_thing=BIG_THING,
        board_keepout_bboxes=board_keepout_bboxes,
        board_holder_tpu_cover_gap_above_base=board_holder_tpu_cover_gap_above_base,
        board_holder_plug_corner_inset=board_holder_plug_corner_inset,
        board_holder_plug_diameter=board_holder_plug_diameter,
        board_holder_plug_angle_deg=board_holder_plug_angle_deg,
        board_holder_plug_height=board_holder_plug_height,
        board_holder_plug_wall_thickness=board_holder_plug_wall_thickness,
        board_holder_plug_base_thickness=board_holder_plug_base_thickness,
        board_holder_plug_slit_width=board_holder_plug_slit_width,
        board_holder_plug_fillet_radius=board_holder_plug_fillet_radius,
        board_holder_plug_lip_height=board_holder_plug_lip_height,
        board_holder_plug_lip_size=board_holder_plug_lip_size,
        board_holder_plug_lip_top_gap=board_holder_plug_lip_top_gap,
        board_holder_plug_no_inner_hole=board_holder_plug_no_inner_hole,
        board_holder_plug_hole_slack=board_holder_plug_hole_slack,
    )
    cover_plug_holes = _fuse_parts(cover_plug_hole_cutters)
    all_holders.leader = all_holders.leader.cut(cover_plug_holes)
    all_holders.add_named_cutter(cover_plug_holes, "cover_plug_holes")
    all_holders = all_holders.merge_except_leader(
        pico_board.prefixed_copy("pico_board")
    )
    additional_pins_prefixed = additional_pins.prefixed_copy("additional_pins")
    for name, part in additional_pins_prefixed.get_named_non_production_part_items():
        all_holders.add_named_non_production_part(part, name)

    for tmc_index, current_tmc_board in enumerate(positioned_tmc_boards):
        all_holders = all_holders.merge_except_leader(
            current_tmc_board.prefixed_copy(
                _get_named_tmc_board_visual_prefix(tmc_index)
            )
        )

    if positioned_mosfet_driver_board is not None:
        all_holders = all_holders.merge_except_leader(
            positioned_mosfet_driver_board.prefixed_copy("mosfet_driver_board")
        )

    base_plate_cutter = materialize_bounding_box(all_holders)

    side_wall_thickness = BOARD_HOLDER_SIDE_WALL_THICKNESS
    side_wall_top_height = 22
    side_wall_bottom_height = 20
    mount_plate_extension = 7
    side_wall_clearance = 0.6

    base_plate_enlargement = materialize_bounding_box(
        all_holders,
        x_enlargement=2 * mount_plate_extension,
        y_enlargement=2 * mount_plate_extension,
    )

    base_plate_enlargement = base_plate_enlargement.cut(base_plate_cutter)
    all_holders = all_holders.fuse(base_plate_enlargement)

    base_plate_size = get_bounding_box_size(all_holders)

    def create_side_wall(length, width, thickness):
        return create_box(length, width, thickness)

    side_walls = PartCollector()
    for fb in [Alignment.FRONT, Alignment.BACK]:

        side_wall_top = create_side_wall(
            base_plate_size[0] + 2 * side_wall_thickness + 2 * side_wall_clearance,
            side_wall_top_height + board_holder_base_plate_thickness,
            side_wall_thickness,
        )
        side_wall_top = rotate(90, axis=(1, 0, 0))(side_wall_top)
        side_wall_top = align(side_wall_top, all_holders, Alignment.CENTER, axes=[0])
        side_wall_top = align(
            side_wall_top,
            all_holders,
            fb.stack_alignment,
            stack_gap=side_wall_clearance,
        )
        side_wall_top = align(side_wall_top, all_holders, Alignment.BOTTOM)
        side_walls = side_walls.fuse(side_wall_top)

        side_wall_bottom = create_box(
            base_plate_size[0] + 2 * side_wall_thickness + 2 * side_wall_clearance,
            side_wall_thickness,
            side_wall_bottom_height,
        )
        side_wall_bottom = align(
            side_wall_bottom, all_holders, Alignment.CENTER, axes=[0]
        )
        side_wall_bottom = align(
            side_wall_bottom,
            all_holders,
            fb.stack_alignment,
            stack_gap=side_wall_clearance,
        )
        side_wall_bottom = align(side_wall_bottom, all_holders, Alignment.STACK_BOTTOM)
        side_walls = side_walls.fuse(side_wall_bottom)

    top_side_walls = PartCollector()
    bottom_side_walls = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        side_wall_top = create_side_wall(
            base_plate_size[1] + 2 * side_wall_thickness + 2 * side_wall_clearance,
            side_wall_top_height + board_holder_base_plate_thickness,
            side_wall_thickness,
        )
        side_wall_top = rotate(90, axis=(1, 0, 0))(side_wall_top)
        side_wall_top = rotate(90)(side_wall_top)

        side_wall_top = align(side_wall_top, all_holders, Alignment.CENTER, axes=[1])
        side_wall_top = align(
            side_wall_top,
            all_holders,
            lr.stack_alignment,
            stack_gap=side_wall_clearance,
        )
        side_wall_top = align(side_wall_top, all_holders, Alignment.BOTTOM)
        top_side_walls = top_side_walls.fuse(side_wall_top)
        side_walls = side_walls.fuse(side_wall_top)

        side_wall_bottom = create_box(
            side_wall_thickness,
            base_plate_size[1] + 2 * side_wall_thickness + 2 * side_wall_clearance,
            side_wall_bottom_height,
        )

        side_wall_bottom = align(
            side_wall_bottom, all_holders, Alignment.CENTER, axes=[1]
        )
        side_wall_bottom = align(
            side_wall_bottom,
            all_holders,
            lr.stack_alignment,
            stack_gap=side_wall_clearance,
        )
        side_wall_bottom = align(side_wall_bottom, all_holders, Alignment.STACK_BOTTOM)

        side_walls = side_walls.fuse(side_wall_bottom)
        bottom_side_walls = bottom_side_walls.fuse(side_wall_bottom)

    num_cable_holes = 8
    cable_hole_diameter = 4
    cable_hole_pitch = 8

    cable_hole_drills = PartCollector()
    for i in range(num_cable_holes):
        cable_hole_drill = create_cylinder(cable_hole_diameter / 2, BIG_THING)
        cable_hole_drill = rotate(90, axis=(0, 1, 0))(cable_hole_drill)

        cable_hole_drill = translate(0, i * cable_hole_pitch, 0)(cable_hole_drill)
        cable_hole_drills = cable_hole_drills.fuse(cable_hole_drill)

    cable_hole_drills = align(cable_hole_drills, top_side_walls, Alignment.CENTER)

    side_walls = side_walls.cut(cable_hole_drills)

    bottom_cable_hole_pitch = 12
    bottom_cable_hole_size = 6
    bottom_cable_hole_drills = PartCollector()
    for i in range(num_cable_holes):
        bottom_cable_hole_drill = create_box(
            BIG_THING, bottom_cable_hole_size, bottom_cable_hole_size
        )
        bottom_cable_hole_drill = rotate(45, axis=(1, 0, 0))(bottom_cable_hole_drill)
        bottom_cable_hole_drill = translate(0, i * bottom_cable_hole_pitch, 0)(
            bottom_cable_hole_drill
        )
        bottom_cable_hole_drills = bottom_cable_hole_drills.fuse(
            bottom_cable_hole_drill
        )

    bottom_cable_hole_drills = align(
        bottom_cable_hole_drills, bottom_side_walls, Alignment.CENTER
    )
    side_walls = side_walls.cut(bottom_cable_hole_drills)

    mount_screw_hole_diameter = MScrew.from_size(
        board_holder_mount_screw_size
    ).clearance_hole_normal
    mount_screw_holes = PartCollector()
    mount_screw_positions = []
    for left_right_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        for front_back_alignment in [Alignment.FRONT, Alignment.BACK]:
            screw_hole = create_cylinder(
                mount_screw_hole_diameter / 2,
                BIG_THING,
            )
            screw_hole = align(screw_hole, all_holders, Alignment.CENTER)
            screw_hole = align(screw_hole, all_holders, left_right_alignment)
            screw_hole = align(screw_hole, all_holders, front_back_alignment)
            screw_hole = translate(
                -left_right_alignment.sign * board_holder_mount_screw_hole_inset,
                -front_back_alignment.sign * board_holder_mount_screw_hole_inset,
                0,
            )(screw_hole)
            mount_screw_holes = mount_screw_holes.fuse(screw_hole)
            mount_screw_positions.append(get_bounding_box_center(screw_hole))

    all_holders = all_holders.cut(mount_screw_holes)
    all_holders.add_named_cutter(mount_screw_holes, "mount_screw_holes")

    walls_bottom_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    walls_bottom_cutter = align(walls_bottom_cutter, side_walls, Alignment.CENTER)
    walls_bottom_cutter = align(walls_bottom_cutter, side_walls, Alignment.STACK_BOTTOM)

    mount_posts = PartCollector()
    mount_post_size = (
        2 * mount_screw_hole_diameter
        + board_holder_mount_screw_hole_inset
        + side_wall_clearance
    )
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            mount_post = create_box(mount_post_size, mount_post_size, BIG_THING)
            mount_post = align(mount_post, side_walls, Alignment.CENTER)
            mount_post = align(mount_post, side_walls, lr)
            mount_post = align(mount_post, side_walls, fb)
            mount_post = align(mount_post, all_holders, Alignment.STACK_BOTTOM)
            mount_post = mount_post.cut(walls_bottom_cutter)
            mount_posts = mount_posts.fuse(mount_post)

    side_walls = side_walls.cut(usb_cable_cutter)

    side_walls = side_walls.fuse(mount_posts)
    side_walls = side_walls.cut(mount_screw_holes)

    mount_screws, mount_nuts = _create_mount_hardware(
        mount_screw_positions=mount_screw_positions,
        screw_size=board_holder_mount_screw_size,
        screw_head_bottom_z=base_plate_mount_top_z,
        side_walls=side_walls,
    )
    bottom_lid_hardware_clearance_cutters = (
        _create_mount_hardware_lid_clearance_cutters(
            mount_screw_positions=mount_screw_positions,
            screw_size=board_holder_mount_screw_size,
            big_thing=BIG_THING,
        )
    )
    top_lid = _create_board_holder_lid(
        side_walls=side_walls,
        lid_alignment=Alignment.TOP,
        big_thing=BIG_THING,
    )
    bottom_lid = _create_board_holder_lid(
        side_walls=side_walls,
        lid_alignment=Alignment.BOTTOM,
        big_thing=BIG_THING,
        clearance_cutters=bottom_lid_hardware_clearance_cutters,
    )
    side_walls = top_lid.use_as_cutter_on(side_walls)
    side_walls = bottom_lid.use_as_cutter_on(side_walls)

    all_holders_size = get_bounding_box_size(all_holders)

    usb_cover_bridge_cutter = create_box_hole_cutter(
        all_holders_size[0], all_holders_size[1], BIG_THING, cutter_size=2000
    )
    usb_cover_bridge_cutter = align(
        usb_cover_bridge_cutter, all_holders, Alignment.CENTER
    )
    usb_cover_bridge_cutter = align(
        usb_cover_bridge_cutter, all_holders, Alignment.BOTTOM
    )

    usb_cover_bridge = usb_cover_bridge_cutter.use_as_cutter_on(usb_cover_bridge)

    all_holders = all_holders.fuse(usb_cover_bridge)

    usb_cover_bridge_bottom_cutter = fit_part_between(
        usb_cable_cutter, (0, 1, 0), limiting_start_part=connector_part
    )

    all_holders = all_holders.cut(usb_cover_bridge_bottom_cutter)

    usb_cover_bridge_outside_cutter = materialize_bounding_box(
        usb_cover_bridge, x_enlargement=0.2, y_enlargement=0.2
    )

    tpu_cover = tpu_cover.cut(usb_cover_bridge_outside_cutter)

    all_holders.add_named_follower(tpu_cover, "tpu_cover")
    all_holders.additional_data["tpu_cover_straps"] = tpu_cover_strap_metadata
    all_holders.additional_data["plug_positions"] = [
        [x_pos, y_pos] for x_pos, y_pos in cover_plug_positions
    ]
    all_holders.additional_data["usb_cover_bridge_keepout_bbox"] = [
        list(usb_cover_bridge_keepout_bbox[0]),
        list(usb_cover_bridge_keepout_bbox[1]),
    ]
    all_holders.additional_data["mount_screw_positions"] = [
        list(position) for position in mount_screw_positions
    ]
    all_holders.additional_data["bottom_lid_hardware_clearance_radius"] = (
        _get_mount_hardware_clearance_radius(board_holder_mount_screw_size)
    )

    if board_holder_frame_mount_eyes_enabled:
        side_walls_size = get_bounding_box_size(side_walls)
        frame_mount_eyes = PartCollector()
        for side in [Alignment.LEFT, Alignment.RIGHT]:
            frame_mount_eye = create_filleted_box(
                board_holder_frame_mount_eye_width,
                side_walls_size[2],
                board_holder_frame_mount_eye_thickness,
                fillet_radius=board_holder_frame_mount_eye_fillet_radius,
                no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, side.opposite],
            )
            frame_mount_eye_screw_hole_cutter = create_cylinder(
                MScrew.from_size(
                    board_holder_frame_mount_eye_screw_size
                ).clearance_hole_normal
                / 2,
                BIG_THING,
            )
            frame_mount_eye_screw_hole_cutter = align(
                frame_mount_eye_screw_hole_cutter,
                frame_mount_eye,
                Alignment.CENTER,
            )
            frame_mount_eye = frame_mount_eye.cut(frame_mount_eye_screw_hole_cutter)
            frame_mount_eye = rotate(90, axis=(1, 0, 0))(frame_mount_eye)
            frame_mount_eye = align(frame_mount_eye, side_walls, Alignment.CENTER)
            frame_mount_eye = align(
                frame_mount_eye,
                side_walls,
                side.stack_alignment,
            )
            frame_mount_eye = align(frame_mount_eye, side_walls, Alignment.FRONT)
            frame_mount_eyes = frame_mount_eyes.fuse(frame_mount_eye)

        side_walls = side_walls.fuse(frame_mount_eyes)

    elko_socket_assemblies = _create_elko_socket_assemblies_for_tmc_boards(
        positioned_tmc_boards=positioned_tmc_boards,
    )
    all_holders.add_named_follower(
        elko_socket_assemblies.leader,
        "elko_sleeve_plates",
    )
    for name, part in elko_socket_assemblies.get_named_follower_items():
        all_holders.add_named_follower(part, name)
    for name, part in elko_socket_assemblies.get_named_non_production_part_items():
        all_holders.add_named_non_production_part(part, name)
    all_holders.additional_data["elko_socket_plate_bboxes"] = [
        [list(corner) for corner in socket_plate_bbox]
        for socket_plate_bbox in elko_socket_assemblies.additional_data[
            "socket_plate_bboxes"
        ]
    ]
    all_holders.additional_data["elko_socket_sleeve_bboxes"] = [
        [list(corner) for corner in socket_sleeve_bbox]
        for socket_sleeve_bbox in elko_socket_assemblies.additional_data[
            "socket_sleeve_bboxes"
        ]
    ]
    all_holders.add_named_follower(top_lid.leader, "top_lid")
    all_holders.add_named_follower(bottom_lid.leader, "bottom_lid")
    all_holders.add_named_follower(side_walls, "side_walls")
    all_holders.add_named_non_production_part(mount_screws, "mount_screws")
    all_holders.add_named_non_production_part(mount_nuts, "mount_nuts")

    return all_holders
