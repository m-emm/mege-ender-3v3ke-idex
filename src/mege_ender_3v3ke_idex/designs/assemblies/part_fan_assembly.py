"""Part-fan duct assembly fed by one injected radial blower."""

from shellforgepy.simple import *


def _create_blower_bridge(*, blower_outlet, blower_ring, wall_thickness):
    """Build a minimal hollow transition from the blower outlet into the ring."""

    outlet_outer = materialize_bounding_box(
        blower_outlet,
        x_enlargement=wall_thickness,
        y_enlargement=wall_thickness,
        z_enlargement=wall_thickness,
    )

    ring_entry_outer = create_box(*get_bounding_box_size(outlet_outer))
    ring_entry_outer = align(
        ring_entry_outer,
        blower_ring.leader,
        Alignment.CENTER,
        axes=[0, 2],
    )
    ring_entry_outer = align(
        ring_entry_outer,
        blower_ring.leader,
        Alignment.STACK_FRONT,
    )

    ring_entry_inner = create_box(*get_bounding_box_size(blower_outlet))
    ring_entry_inner = align(ring_entry_inner, ring_entry_outer, Alignment.CENTER)

    bridge_outer = create_convex_hull(outlet_outer, ring_entry_outer)
    bridge_inner = create_convex_hull(blower_outlet, ring_entry_inner)

    blower_join_anchor = outlet_outer.cut(blower_outlet)
    ring_join_anchor = ring_entry_outer.cut(ring_entry_inner)

    return (
        bridge_outer.cut(bridge_inner),
        ring_entry_inner,
        blower_join_anchor,
        ring_join_anchor,
    )


def create_part_fan_assembly(
    *, sprite_extruder, blower, blower_ring, blower_wall_thickness
):
    """Create a blower-fed bridge and retain the existing nozzle-ring output."""

    blower_outlet = blower.get_named_cutter("duct_cutter")
    central_blower = blower_ring.get_named_follower("central_blower")

    (
        blower_bridge,
        ring_entry_cutter,
        blower_join_anchor,
        ring_join_anchor,
    ) = _create_blower_bridge(
        blower_outlet=blower_outlet,
        blower_ring=blower_ring,
        wall_thickness=blower_wall_thickness,
    )

    blower_ring_with_entry = blower_ring.leader.cut(ring_entry_cutter)
    central_blower = central_blower.cut(ring_entry_cutter)

    part_fans = blower_ring_with_entry.fuse(blower_bridge)
    part_fans = sprite_extruder.use_as_cutter_on(part_fans)
    central_blower = sprite_extruder.use_as_cutter_on(central_blower)

    retval = LeaderFollowersCuttersPart(part_fans)
    retval.add_named_follower(central_blower, "central_blower")
    retval.add_named_non_production_part(blower_bridge, "blower_bridge")
    retval.add_named_non_production_part(blower_join_anchor, "side_mount_plate")
    retval.add_named_non_production_part(
        ring_join_anchor,
        "duct_back_mount_plate_connector",
    )

    for name, screw_part in blower_ring.get_named_non_production_part_items():
        if name.startswith("joining_screw_"):
            retval.add_named_non_production_part(screw_part, name)

    retval.add_consumed_part_ref(blower.part_ref_for_named_cutter("duct_cutter"))
    retval.add_consumed_part_ref(blower_ring.part_ref_for_leader())
    retval.add_consumed_part_ref(blower_ring.part_ref_for_named_follower("feeder_ring"))
    retval.add_consumed_part_ref(
        blower_ring.part_ref_for_named_follower("central_blower")
    )

    return retval
