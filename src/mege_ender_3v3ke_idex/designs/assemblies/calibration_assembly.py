from shellforgepy.simple import *


def create_calibration_assembly(
    *,
    BIG_THING=500,
):

    diameters = [2, 4, 8]
    base_thickness = 2
    post_height = 4
    x_gap = 10
    y_gap = 6  # Increased from 4 to 6 for better spacing
    border = 3
    font_size = 7  # ShellForgePy text size is in mm, much more reasonable
    text_x_offset = -3
    text_y_offset = 2.5

    base_width = sum(diameters) + (len(diameters) - 1) * x_gap + 2 * border
    base_height = 4 * max(diameters) + 5 * y_gap + 2 * border  # Space for 3 rows

    # Create base plate
    base = create_box(base_width, base_height, base_thickness)
    original_base = base  # Keep reference to original base for alignment

    # Collect all text objects for cutting
    text_collector = PartCollector()

    cur_x = border

    for i, d in enumerate(diameters):
        cur_x += d / 2

        # Create cylinder post (do this first to get position reference)
        x = cur_x
        y = base_height - border - max(diameters) / 2
        z = base_thickness

        post = create_cylinder(d / 2, post_height)
        post = translate(x, y, z)(post)

        x = cur_x
        y = base_height - border - max(diameters) / 2 - y_gap - max(diameters)
        z = base_thickness

        square_post = create_box(d, d, post_height)
        square_post = align(square_post, None, Alignment.CENTER, axes=[0, 1])

        square_post = translate(x, y, z)(square_post)

        # Add text label for diameter - centered on the cylinder in x-axis
        try:
            text_obj = create_text_object(
                str(d), size=font_size, thickness=base_thickness / 2
            )
            bbox_center = get_bounding_box_center(text_obj)
            text_obj = translate(-bbox_center[0], -bbox_center[1], -bbox_center[2])(
                text_obj
            )

            # Center text in x-axis to the cylinder, align to original base
            text_obj = align(
                text_obj, post, Alignment.CENTER, axes=[0]
            )  # x-axis centering
            text_obj = align(text_obj, original_base, Alignment.FRONT)
            text_obj = align(text_obj, original_base, Alignment.TOP)
            text_obj = translate(0, text_y_offset, 0)(text_obj)  # Only y offset needed

            # Collect the text for cutting instead of fusing
            text_collector = text_collector.fuse(text_obj)
        except:
            # If text creation fails, continue without text
            pass

        base = base.fuse(post)
        base = base.fuse(square_post)

        # Create test hole (second row)
        y -= max(diameters) + y_gap
        hole_cutter = create_cylinder(d / 2, base_thickness + 1)  # +1 for complete cut
        hole_cutter = translate(x, y, -0.5)(hole_cutter)  # -0.5 to ensure clean cut
        base = base.cut(hole_cutter)

        # Create test square (third row)
        y -= max(diameters) + y_gap
        square_cutter = create_box(
            d, d, base_thickness + 1
        )  # Square with side length = diameter
        square_cutter = translate(x - d / 2, y - d / 2, -0.5)(
            square_cutter
        )  # Center the square
        base = base.cut(square_cutter)

        cur_x += d / 2 + x_gap

    # Cut out the text from the base
    base = base.cut(text_collector)

    return LeaderFollowersCuttersPart(base)
