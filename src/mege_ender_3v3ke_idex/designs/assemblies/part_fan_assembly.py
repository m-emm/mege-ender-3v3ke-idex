"""Temporary direct-mount placeholder for the future blower duct."""

import math

from shellforgepy.simple import *


def create_part_fan_assembly(
    *, sprite_extruder, blower, blower_body_size, blower_thickness
):
    """Create a full-body placeholder positioned directly behind the blower."""

    mount_plate_thickness = 4
    inner_gap = 25
    duct_size = 11
    nozzle_length = 40
    oblique_nozzle_size = 4
    oblique_nozzle_bottom_thickness = 9
    oblique_nozzle_wall=1.5

    nozzle_thickness = 3
    nozzle_struts_thickness = 2
    nozzle_struts_pitch = 9
    nozzle_wall = 2

    side_mount_plate_thickness = 4
    side_mount_plate_height = 40
    side_mount_plate_depth = 30

    mount_plate_blower_clearance = 0.8
    mount_plate_extra_radius = 2

    hotend = sprite_extruder.get_named_non_production_part("hotend")

    placeholder = create_box(
        blower_body_size,
        nozzle_length,
        blower_thickness,
    )

    placeholder = align(placeholder, blower, Alignment.CENTER)
    placeholder = align(placeholder, hotend, Alignment.CENTER, axes=[0])
    placeholder = align(placeholder, blower, Alignment.STACK_BACK)

    blower_mount_plate = materialize_bounding_box(
        blower, z_size=mount_plate_thickness, y_enlargement=nozzle_length
    )
    blower_mount_plate = align(blower_mount_plate, blower, Alignment.STACK_BOTTOM)
    blower_mount_plate = align(blower_mount_plate, blower, Alignment.FRONT)

    hole_extensions = PartCollector()
    for name, cutter in blower.get_named_cutter_items():
        if name == "duct_cutter":
            continue
        cutter_size = get_bounding_box_size(cutter)
        hole_extension = create_cylinder(
            cutter_size[0] / 2 + mount_plate_extra_radius,
            mount_plate_thickness,
        )
        hole_extension = align(hole_extension, cutter, Alignment.CENTER)
        hole_extension = align(hole_extension, blower_mount_plate, Alignment.BOTTOM)
        hole_extensions = hole_extensions.fuse(hole_extension)



    blower_mount_plate = blower.use_as_cutter_on(blower_mount_plate)    
    placeholder = placeholder.fuse(blower_mount_plate)

    duct_cutter = blower.get_named_cutter("duct_cutter")

    duct_cutter = translate(0, 10, 0)(duct_cutter)

    inner_cutter = create_box(inner_gap, 100, 100)
    inner_cutter = align(inner_cutter, placeholder, Alignment.CENTER)
    inner_cutter = align(inner_cutter, hotend, Alignment.CENTER, axes=[0])
    inner_cutter = align(
        inner_cutter,
        placeholder,
        Alignment.STACK_BACK,
        stack_gap=-nozzle_length + duct_size,
    )

    placeholder = placeholder.cut(inner_cutter)

    oblique_nozzles = PartCollector()
    nozzle_cutters = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        oblique_nozzle_bottom = create_box(
            oblique_nozzle_size, nozzle_length, oblique_nozzle_bottom_thickness
        )

        oblique_nozzle_bottom = align(
            oblique_nozzle_bottom, placeholder, Alignment.CENTER
        )
        oblique_nozzle_bottom = align(
            oblique_nozzle_bottom, placeholder, Alignment.BOTTOM
        )
        oblique_nozzle_bottom = align(
            oblique_nozzle_bottom, placeholder, Alignment.BACK
        )

        oblique_nozzle_bottom = align(oblique_nozzle_bottom, inner_cutter, lr)

        oblique_nozzle_rim = create_right_triangle(
            oblique_nozzle_size,
            oblique_nozzle_size,
            nozzle_length,
            extrusion_direction=(0, 1, 0),
            a_normal=(0, 0, -1),
            b_normal=(-lr.sign, 0, 0),
        )
        oblique_nozzle_rim = align(
            oblique_nozzle_rim, oblique_nozzle_bottom, Alignment.CENTER
        )
        oblique_nozzle_rim = align(
            oblique_nozzle_rim, oblique_nozzle_bottom, Alignment.STACK_TOP
        )

        oblique_nozzle = oblique_nozzle_bottom.fuse(oblique_nozzle_rim)

        oblique_nozzles = oblique_nozzles.fuse(oblique_nozzle)

        nozzle_cutter_depth = nozzle_length - duct_size - 2 * nozzle_wall

        nozzle_cutter_bottom = create_right_triangle(
            nozzle_thickness, 
            oblique_nozzle_size,
            nozzle_cutter_depth,
            extrusion_direction=(0, 1, 0),            
            a_normal=(0, 0, 1),
            b_normal=(lr.sign, 0, 0),
        )

        nozzle_cutter_top = create_right_triangle(
            nozzle_thickness*2, 
            oblique_nozzle_size,
            nozzle_cutter_depth,
            extrusion_direction=(0, 1, 0),            
            a_normal=(0, 0, -1),
            b_normal=(-lr.sign, 0, 0),
        )

        nozzle_cutter_top = align(
            nozzle_cutter_top, nozzle_cutter_bottom, Alignment.CENTER
        )

        nozzle_cutter_top = align(
            nozzle_cutter_top, nozzle_cutter_bottom, lr
        )

        nozzle_cutter_top = align(
            nozzle_cutter_top, nozzle_cutter_bottom, Alignment.STACK_TOP
        )

        nozzle_cutter = nozzle_cutter_bottom.fuse(nozzle_cutter_top)
        nozzle_cutter = align(nozzle_cutter, oblique_nozzle, Alignment.CENTER)
        nozzle_cutter = align(nozzle_cutter, inner_cutter,lr)
        nozzle_cutter = align(nozzle_cutter, placeholder    , Alignment.BOTTOM)
        nozzle_cutter = align(nozzle_cutter, placeholder    , Alignment.BACK)
        nozzle_cutter = translate(0,-nozzle_wall ,nozzle_wall)(nozzle_cutter)












        nozzle_struts = PartCollector()
        num_struts = int(nozzle_cutter_depth / nozzle_struts_pitch)
        for i in range(num_struts):
            strut = create_box(
                500,
                nozzle_struts_thickness,
                500
            )
            strut = translate(0, i * nozzle_struts_pitch, 0)(strut)

            nozzle_struts = nozzle_struts.fuse(strut)

        nozzle_struts = align(nozzle_struts, nozzle_cutter, Alignment.CENTER)
        nozzle_cutter = nozzle_cutter.cut(nozzle_struts)

        nozzle_wall_cutter =materialize_bounding_box(nozzle_cutter, x_size=4*nozzle_wall, z_size=2*nozzle_thickness)
        nozzle_wall_cutter = align(nozzle_wall_cutter, nozzle_cutter, lr.stack_alignment)
        nozzle_wall_cutter = align(nozzle_wall_cutter, nozzle_cutter, Alignment.TOP)
        nozzle_cutter = nozzle_cutter.fuse(nozzle_wall_cutter)



        oblique_nozzle_bounding_box = get_bounding_box(oblique_nozzle)

        nozzle_cutters = nozzle_cutters.fuse(nozzle_cutter)

        inner_duct_cutter = create_box(
            duct_size - 2 * nozzle_wall,
            nozzle_length - 2 * nozzle_wall,
            blower_thickness - 2 * nozzle_wall,
        )
        inner_duct_cutter = align(inner_duct_cutter, placeholder, Alignment.CENTER)
        inner_duct_cutter = align(inner_duct_cutter, placeholder, Alignment.BACK)
        inner_duct_cutter = align(inner_duct_cutter, placeholder, lr)
        inner_duct_cutter = translate(-lr.sign * nozzle_wall, -nozzle_wall, 0)(
            inner_duct_cutter
        )
        placeholder = placeholder.cut(inner_duct_cutter)


    front_nozzle_cutter = create_box(blower_body_size-2*nozzle_wall, duct_size-2*nozzle_wall, blower_thickness-2*nozzle_wall)
    front_nozzle_cutter = align(front_nozzle_cutter, placeholder, Alignment.CENTER)
    front_nozzle_cutter = align(front_nozzle_cutter, blower, Alignment.STACK_BACK, stack_gap=nozzle_wall)


    placeholder = placeholder.fuse(oblique_nozzles)

    placeholder = placeholder.cut(nozzle_cutters)
    placeholder = placeholder.cut(duct_cutter)
    placeholder = placeholder.cut(front_nozzle_cutter)


    side_mount_plate = create_box(side_mount_plate_thickness, side_mount_plate_depth, side_mount_plate_height)
    side_mount_plate = align(side_mount_plate, placeholder, Alignment.CENTER)
    side_mount_plate = align(side_mount_plate, placeholder, Alignment.BOTTOM)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.STACK_RIGHT)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.FRONT)

    side_mount_plate = sprite_extruder.use_as_cutter_on(side_mount_plate)

    blower_cutter = materialize_bounding_box(blower, y_enlargement=2*mount_plate_blower_clearance, x_enlargement=2*mount_plate_blower_clearance, z_enlargement=mount_plate_blower_clearance)
    blower_cutter = align(blower_cutter, blower, Alignment.BOTTOM)
    blower_cutter = align(blower_cutter, blower, Alignment.BACK)

    side_mount_plate = side_mount_plate.cut(blower_cutter)

    placeholder = placeholder.fuse(side_mount_plate)

    blower_mount_plate = blower_mount_plate.fuse(hole_extensions)

    blower_mount_plate = blower.use_as_cutter_on(blower_mount_plate)    
    blower_mount_plate = blower_mount_plate.cut(inner_cutter)
    placeholder = placeholder.fuse(blower_mount_plate)





    return LeaderFollowersCuttersPart(placeholder)
