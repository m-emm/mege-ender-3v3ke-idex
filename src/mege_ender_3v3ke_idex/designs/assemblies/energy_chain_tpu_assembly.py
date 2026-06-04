"""TPU energy chain skeleton assembly."""

from shellforgepy.simple import *


def create_energy_chain_tpu_assembly(
    *,
    energy_chain_num_links,
    energy_chain_width,
    energy_chain_base_thickness,
    energy_chain_link_length,
    energy_chain_link_connector_thickness,
    energy_chain_link_connector_width,
    energy_chain_plug_diameter,
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

    chain = PartCollector()
    walls_2 = PartCollector()
    for i in range(energy_chain_num_links):

        plate = create_box(
            energy_chain_base_thickness,
            energy_chain_link_length,
            energy_chain_width,
        )

        plate = translate(0, i * link_pitch, 0)(plate)
        chain = chain.fuse(plate)

        link = create_box(
            energy_chain_link_connector_thickness,
            energy_chain_link_connector_width,
            energy_chain_width,
        )
        link = align(link, plate, Alignment.CENTER)
        link = align(link, plate, Alignment.STACK_BACK)
        link = align(link, plate, Alignment.LEFT)
        chain = chain.fuse(link)

        channel_wall_1 = create_box(
            energy_chain_channel_height,
            energy_chain_link_length,
            energy_chain_channel_wall_thickness,
        )

        channel_wall_1 = align(channel_wall_1, plate, Alignment.CENTER)
        channel_wall_1 = align(channel_wall_1, plate, Alignment.BOTTOM)
        channel_wall_1 = align(channel_wall_1, plate, Alignment.STACK_RIGHT)
        chain = chain.fuse(channel_wall_1)

        channel_link_1 = create_box(
            energy_chain_channel_link_width,
            energy_chain_link_length,
            energy_chain_channel_link_thickness,
        )
        channel_link_1 = align(channel_link_1, channel_wall_1, Alignment.CENTER)
        channel_link_1 = align(channel_link_1, channel_wall_1, Alignment.STACK_RIGHT)
        channel_link_1 = align(channel_link_1, channel_wall_1, Alignment.BOTTOM)
        chain = chain.fuse(channel_link_1)

        channel_wall_2 = create_box(
            energy_chain_width - energy_chain_plug_plate_width,
            energy_chain_link_length,
            energy_chain_channel_wall_thickness,
        )

        channel_wall_2 = align(channel_wall_2, channel_link_1, Alignment.CENTER)
        channel_wall_2 = align(channel_wall_2, channel_link_1, Alignment.BOTTOM)
        channel_wall_2 = align(channel_wall_2, channel_link_1, Alignment.STACK_RIGHT)
        chain = chain.fuse(channel_wall_2)

        walls_2 = walls_2.fuse(channel_wall_1).fuse(channel_wall_2)

    unused_parameters = (
        energy_chain_num_links,
        energy_chain_link_connector_thickness,
        energy_chain_link_connector_width,
        energy_chain_plug_diameter,
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
    )
    del unused_parameters

    retval = LeaderFollowersCuttersPart(leader=chain)
    retval.add_named_non_production_part(walls_2, "walls_2")
    return retval
