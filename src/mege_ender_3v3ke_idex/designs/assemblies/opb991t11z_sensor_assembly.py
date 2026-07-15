"""OPB991T11Z wired optical interrupter reference assembly."""

from shellforgepy.simple import *


def create_opb991t11z_sensor_assembly(
    *,
    opb991t11z_body_width,
    opb991t11z_body_depth,
    opb991t11z_base_height,
    opb991t11z_slot_width,
    opb991t11z_mount_tab_width,
    opb991t11z_mount_tab_depth,
    opb991t11z_mount_tab_thickness,
    opb991t11z_both_tower_width,
    opb991t11z_tower_height,
    opb991t11z_connector_towers_width,
    opb991t11z_connector_towers_depth,
    opb991t11z_connector_towers_height,
    opb991t11z_connector_towers_gap,
    opb991t11z_mount_hole_diameter,
    opb991t11z_mount_hole_pitch,
):
    """Create a simplified datasheet-sized OPB991T11Z sensor model."""

    base = create_box(
        opb991t11z_body_width,
        opb991t11z_body_depth,
        opb991t11z_base_height,
    )

    tab = create_rounded_slab(
        opb991t11z_mount_tab_width,
        opb991t11z_mount_tab_depth,
        opb991t11z_mount_tab_thickness,
        opb991t11z_mount_tab_depth / 2,
    )
    tab = align(tab, base, Alignment.CENTER)

    two_towers = create_box(
        opb991t11z_both_tower_width,
        opb991t11z_body_depth,
        opb991t11z_tower_height,
    )

    slot = create_box(
        opb991t11z_slot_width,
        100,
        100,
    )
    slot = align(slot, two_towers, Alignment.CENTER)
    two_towers = two_towers.cut(slot)

    two_towers = align(two_towers, tab, Alignment.CENTER)
    two_towers = align(two_towers, tab, Alignment.STACK_TOP)

    light = create_cylinder(0.05, opb991t11z_both_tower_width)
    light = rotate(90, axis=(0, 1, 0))(light)
    light = align(light, two_towers, Alignment.CENTER)

    connector_towers = create_box(
        opb991t11z_connector_towers_width,
        opb991t11z_connector_towers_depth,
        opb991t11z_connector_towers_height,
    )
    connector_towers_slot_cutter = create_box(
        opb991t11z_connector_towers_gap,
        100,
        100,
    )
    connector_towers_slot_cutter = align(
        connector_towers_slot_cutter,
        connector_towers,
        Alignment.CENTER,
    )
    connector_towers_slot_cutter = align(
        connector_towers_slot_cutter,
        connector_towers,
        Alignment.TOP,
    )
    connector_towers_slot_cutter = translate(
        0,
        0,
        -opb991t11z_connector_towers_gap / 2,
    )(connector_towers_slot_cutter)

    connector_towers = connector_towers.cut(connector_towers_slot_cutter)
    connector_towers_arc_cutter = create_cylinder(
        opb991t11z_connector_towers_gap / 2,
        100,
    )
    connector_towers_arc_cutter = rotate(90, axis=(1, 0, 0))(
        connector_towers_arc_cutter
    )
    connector_towers_arc_cutter = align(
        connector_towers_arc_cutter,
        connector_towers,
        Alignment.CENTER,
    )
    connector_towers_arc_cutter = align(
        connector_towers_arc_cutter,
        connector_towers,
        Alignment.TOP,
    )
    connector_towers = connector_towers.cut(connector_towers_arc_cutter)

    connector_towers = align(connector_towers, tab, Alignment.CENTER)
    connector_towers = align(connector_towers, tab, Alignment.STACK_BOTTOM)

    holes_fused = PartCollector()

    holes = []
    for i in range(2):
        hole = create_cylinder(
            opb991t11z_mount_hole_diameter / 2,
            100,
        )
        hole = translate(i * opb991t11z_mount_hole_pitch, 0, 0)(hole)
        holes_fused = holes_fused.fuse(hole)
        holes.append(hole)

    hole_drills = LeaderFollowersCuttersPart(leader=holes_fused)
    for i, hole in enumerate(holes):
        hole_drills.add_named_cutter(hole, f"hole_{i+1}")

    hole_drills = align(hole_drills, tab, Alignment.CENTER)
    tab = tab.cut(hole_drills.leader)

    leader = tab.fuse(two_towers)
    leader = leader.fuse(connector_towers)

    sensor = LeaderFollowersCuttersPart(leader=leader)
    for name, hole in hole_drills.get_named_cutter_items():
        sensor.add_named_cutter(hole, name)

    sensor.add_named_non_production_part(tab, "mount_tab_reference")
    sensor.add_named_non_production_part(light, "light_reference")
    connector_towers_cutter = materialize_bounding_box(
        connector_towers, x_enlargement=1, y_enlargement=1, z_enlargement=1
    )
    sensor.add_named_cutter(connector_towers_cutter, "connector_towers_cutter")

    return sensor
