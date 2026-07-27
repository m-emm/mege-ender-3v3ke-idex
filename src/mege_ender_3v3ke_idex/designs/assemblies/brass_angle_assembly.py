"""Printable TPU umbilical cable guide for the x-axis."""

from shellforgepy.simple import *


thickness = 1.5
outer_size = 30
width= 14.2
hole_diameter = 4.8
hole_width_inset = 6
hole_outer_inset= 6.5
hole_outer_inset_2 = 21



def create_brass_angle_assembly(
    
):

    base = create_box(width, outer_size-2*thickness, thickness)

    abs_center_offset = width/2 - hole_width_inset
    center = width /2 

    for x,y in [( center - abs_center_offset, hole_outer_inset), (center + abs_center_offset, hole_outer_inset_2)]:

        drill = create_cylinder(hole_diameter/2, thickness+1)
        drill = translate(x,y,-thickness/2)(drill)

        base = base.cut(drill)


    back = rotate(90, axis=(1,0,0))(base)
    back = align(back, base, Alignment.STACK_BACK,stack_gap = thickness)
    back = align(back, base, Alignment.STACK_TOP,stack_gap = thickness)

    
    

    retval = base.fuse(back)

    bend = create_ring(2*thickness, thickness, width, angle=90)
    
    bend = rotate(90, axis=(0,1,0))(bend)

    bend = align(bend, base, Alignment.BOTTOM)
    bend = align(bend, base, Alignment.STACK_BACK)

    retval = retval.fuse(bend)

    return retval

        



    
