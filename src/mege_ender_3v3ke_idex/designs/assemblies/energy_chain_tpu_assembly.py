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

    plate = create_box(
        energy_chain_width,
        energy_chain_link_length,
        energy_chain_base_thickness,
    )
    return LeaderFollowersCuttersPart(leader=plate)
