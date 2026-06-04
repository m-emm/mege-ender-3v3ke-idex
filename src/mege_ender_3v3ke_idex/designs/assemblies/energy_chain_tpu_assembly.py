"""TPU energy chain skeleton assembly."""

from mege_ender_3v3ke_idex.designs.plug_and_hole import create_plug
from shellforgepy.simple import *

BIG_THING = 500


def create_energy_chain_tpu_assembly(
    *,
    energy_chain_num_links,
    energy_chain_width,
    energy_chain_base_thickness,
    energy_chain_link_length,
    energy_chain_link_connector_thickness,
    energy_chain_link_connector_width,
    energy_chain_plug_diameter,
    energy_chain_plug_angle_deg,
    energy_chain_plug_height,
    energy_chain_plug_slit_width,
    energy_chain_plug_base_thickness,
    energy_chain_plug_fillet_radius,
    energy_chain_plug_wall_thickness,
    energy_chain_plug_lip_height,
    energy_chain_plug_lip_size,
    energy_chain_plug_lip_top_gap,
    energy_chain_plug_hole_slack,
    energy_chain_channel_wall_thickness,
    energy_chain_channel_link_thickness,
    energy_chain_channel_link_width,
    energy_chain_channel_height,
    energy_chain_plug_plate_width,
):
    """Create the initial TPU energy-chain plate skeleton."""

    link_pitch = energy_chain_link_length + energy_chain_link_connector_width
    closure_rotation_center = (
        energy_chain_base_thickness
        + energy_chain_channel_height
        + energy_chain_channel_link_width / 2,
        0,
        energy_chain_channel_link_thickness * 0.75,
    )

    chain = PartCollector()
    walls_2 = PartCollector()
    for i in range(energy_chain_num_links):

        fixed_link_body = PartCollector()

        plate = create_box(
            energy_chain_base_thickness,
            energy_chain_link_length,
            energy_chain_width,
        )

        plate = translate(0, i * link_pitch, 0)(plate)
        fixed_link_body = fixed_link_body.fuse(plate)

        link = create_box(
            energy_chain_link_connector_thickness,
            energy_chain_link_connector_width,
            energy_chain_width,
        )
        link = align(link, plate, Alignment.CENTER)
        link = align(link, plate, Alignment.STACK_BACK)
        link = align(link, plate, Alignment.LEFT)
        fixed_link_body = fixed_link_body.fuse(link)

        channel_wall_1 = create_box(
            energy_chain_channel_height,
            energy_chain_link_length,
            energy_chain_channel_wall_thickness,
        )

        channel_wall_1 = align(channel_wall_1, plate, Alignment.CENTER)
        channel_wall_1 = align(channel_wall_1, plate, Alignment.BOTTOM)
        channel_wall_1 = align(channel_wall_1, plate, Alignment.STACK_RIGHT)
        fixed_link_body = fixed_link_body.fuse(channel_wall_1)

        channel_link_1 = create_box(
            energy_chain_channel_link_width,
            energy_chain_link_length,
            energy_chain_channel_link_thickness,
        )
        channel_link_1 = align(channel_link_1, channel_wall_1, Alignment.CENTER)
        channel_link_1 = align(channel_link_1, channel_wall_1, Alignment.STACK_RIGHT)
        channel_link_1 = align(channel_link_1, channel_wall_1, Alignment.BOTTOM)
        fixed_link_body = fixed_link_body.fuse(channel_link_1)

        channel_wall_2 = create_box(
            energy_chain_width - energy_chain_plug_plate_width,
            energy_chain_link_length,
            energy_chain_channel_wall_thickness,
        )

        channel_wall_2 = align(channel_wall_2, channel_link_1, Alignment.CENTER)
        channel_wall_2 = align(channel_wall_2, channel_link_1, Alignment.BOTTOM)
        channel_wall_2 = align(channel_wall_2, channel_link_1, Alignment.STACK_RIGHT)

        plug_base = create_box(
            energy_chain_plug_plate_width - energy_chain_channel_link_width,
            energy_chain_link_length,
            energy_chain_channel_wall_thickness + energy_chain_channel_height,
        )

        plug_base = align(plug_base, channel_wall_2, Alignment.CENTER)
        plug_base = align(plug_base, channel_wall_2, Alignment.BOTTOM)
        plug_base = align(plug_base, channel_wall_2, Alignment.STACK_RIGHT)

        channel_wall_2 = channel_wall_2.fuse(plug_base)

        plug = create_plug(
            plug_diameter=energy_chain_plug_diameter,
            plug_angle_deg=energy_chain_plug_angle_deg,
            plug_height=energy_chain_plug_height,
            plug_wall_thickness=energy_chain_plug_wall_thickness,
            plug_base_thickness=energy_chain_plug_base_thickness,
            plug_slit_width=energy_chain_plug_slit_width,
            fillet_radius=energy_chain_plug_fillet_radius,
            plug_lip_height=energy_chain_plug_lip_height,
            plug_lip_size=energy_chain_plug_lip_size,
            plug_lip_top_gap=energy_chain_plug_lip_top_gap,
        )
        plug = align(plug, plug_base, Alignment.CENTER, axes=[0, 1])
        plug = align(plug, plug_base, Alignment.STACK_TOP)
        channel_wall_2 = channel_wall_2.fuse(plug)

        hole_cutter = create_cylinder(
            energy_chain_plug_diameter / 2 + energy_chain_plug_hole_slack,
            BIG_THING,
        )
        hole_cutter = align(hole_cutter, plug, Alignment.CENTER)
        hole_cutter = rotate(-90, axis=(0, 1, 0), center=closure_rotation_center)(
            hole_cutter
        )

        fixed_link_body = fixed_link_body.cut(hole_cutter)
        chain = chain.fuse(fixed_link_body)
        chain = chain.fuse(channel_wall_2)

        walls_2 = walls_2.fuse(channel_wall_2)

    retval = LeaderFollowersCuttersPart(leader=chain)
    retval.add_named_non_production_part(walls_2, "walls_2")
    return retval
