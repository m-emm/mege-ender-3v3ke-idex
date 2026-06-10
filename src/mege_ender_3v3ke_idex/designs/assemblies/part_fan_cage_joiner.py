"""Join part fan and extruder cage assemblies with a shared flange."""

from shellforgepy.simple import *


def _create_flange_block(width, depth, height, fillet_radius, attachment_alignment):
    if fillet_radius > 0:
        return create_filleted_box(
            width,
            depth,
            height,
            fillet_radius=fillet_radius,
            no_fillets_at=[attachment_alignment, Alignment.TOP, Alignment.BOTTOM],
        )
    return create_box(width, depth, height)


def _flange_layout(anchor_part, extension_alignment, flange_extension):
    anchor_size = get_bounding_box_size(anchor_part)
    if extension_alignment == Alignment.STACK_LEFT:
        return {
            "flange_size": (anchor_size[0] + flange_extension, anchor_size[1]),
            "tab_size": (flange_extension, anchor_size[1]),
            "attachment_alignment": Alignment.RIGHT,
            "center_axes": [1],
        }
    if extension_alignment == Alignment.STACK_RIGHT:
        return {
            "flange_size": (anchor_size[0] + flange_extension, anchor_size[1]),
            "tab_size": (flange_extension, anchor_size[1]),
            "attachment_alignment": Alignment.LEFT,
            "center_axes": [1],
        }
    if extension_alignment == Alignment.STACK_BACK:
        return {
            "flange_size": (anchor_size[0], anchor_size[1] + flange_extension),
            "tab_size": (anchor_size[0], flange_extension),
            "attachment_alignment": Alignment.FRONT,
            "center_axes": [0],
        }
    if extension_alignment == Alignment.STACK_FRONT:
        return {
            "flange_size": (anchor_size[0], anchor_size[1] + flange_extension),
            "tab_size": (anchor_size[0], flange_extension),
            "attachment_alignment": Alignment.BACK,
            "center_axes": [0],
        }
    raise ValueError(f"Unsupported flange extension alignment: {extension_alignment}")


def _create_join_flange_halves(
    *,
    anchor_part=None,
    side_mount_plate=None,
    extension_alignment=Alignment.STACK_LEFT,
    flange_extension,
    flange_half_height,
    screw_size,
    clearance_type,
    fillet_radius,
):
    if anchor_part is None:
        anchor_part = side_mount_plate
    layout = _flange_layout(
        anchor_part,
        extension_alignment,
        flange_extension,
    )
    flange_width, flange_depth = layout["flange_size"]
    tab_width, tab_depth = layout["tab_size"]
    attachment_alignment = layout["attachment_alignment"]
    center_axes = layout["center_axes"]

    bottom_flange = _create_flange_block(
        flange_width,
        flange_depth,
        flange_half_height,
        fillet_radius,
        attachment_alignment,
    )
    bottom_flange = align(
        bottom_flange,
        anchor_part,
        Alignment.CENTER,
        axes=center_axes,
    )
    bottom_flange = align(bottom_flange, anchor_part, attachment_alignment)
    bottom_flange = align(bottom_flange, anchor_part, Alignment.TOP)

    top_flange = _create_flange_block(
        flange_width,
        flange_depth,
        flange_half_height,
        fillet_radius,
        attachment_alignment,
    )
    top_flange = align(top_flange, bottom_flange, Alignment.CENTER, axes=[0, 1])
    top_flange = align(top_flange, bottom_flange, Alignment.STACK_TOP)

    tab_reference = create_box(tab_width, tab_depth, flange_half_height)
    tab_reference = align(
        tab_reference,
        anchor_part,
        Alignment.CENTER,
        axes=center_axes,
    )
    tab_reference = align(tab_reference, anchor_part, extension_alignment)
    tab_reference = align(tab_reference, anchor_part, Alignment.TOP)

    flange_stack = bottom_flange.fuse(top_flange)
    clearance_hole = create_cylinder(
        get_clearance_hole_diameter(screw_size, clearance_type) / 2,
        flange_half_height * 2 + 2,
    )
    clearance_hole = align(clearance_hole, flange_stack, Alignment.CENTER)
    clearance_hole = align(clearance_hole, tab_reference, Alignment.CENTER, axes=[0, 1])

    bottom_flange = bottom_flange.cut(clearance_hole)
    top_flange = top_flange.cut(clearance_hole)

    return bottom_flange, top_flange, clearance_hole


def join_part_fans_with_extruder_cage(
    *,
    part_fans,
    extruder_cage,
    flange_extension=8.0,
    flange_half_height=3.0,
    screw_size="M3",
    clearance_type="loose",
    fillet_radius=0.0,
):
    """Return joined output assemblies for a part fan and extruder cage pair."""

    flange_specs = [
        ("side_mount_plate", Alignment.STACK_LEFT),
        ("duct_back_mount_plate_connector", Alignment.STACK_BACK),
    ]

    bottom_flanges = []
    top_flanges = []
    consumed_part_fan_refs = []
    for anchor_name, extension_alignment in flange_specs:
        anchor_part = part_fans.get_named_non_production_part(anchor_name)
        consumed_part_fan_refs.append(
            part_fans.part_ref_for_named_non_production_part(anchor_name)
        )
        bottom_flange, top_flange, _ = _create_join_flange_halves(
            anchor_part=anchor_part,
            extension_alignment=extension_alignment,
            flange_extension=flange_extension,
            flange_half_height=flange_half_height,
            screw_size=screw_size,
            clearance_type=clearance_type,
            fillet_radius=fillet_radius,
        )
        bottom_flanges.append(bottom_flange)
        top_flanges.append(top_flange)

    joined_part_fans = part_fans.copy()
    joined_extruder_cage = extruder_cage.copy()

    for bottom_flange in bottom_flanges:
        joined_part_fans.leader = joined_part_fans.leader.fuse(bottom_flange)
    for top_flange in top_flanges:
        joined_extruder_cage.leader = joined_extruder_cage.leader.fuse(top_flange)
    for consumed_part_fan_ref in consumed_part_fan_refs:
        joined_part_fans.add_consumed_part_ref(consumed_part_fan_ref)

    return {
        "part_fans": joined_part_fans,
        "extruder_cage": joined_extruder_cage,
    }
