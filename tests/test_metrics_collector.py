from mege_ender_3v3ke_idex.designs.metrics_collector import (
    Material,
    build_metrics_report_lines,
    record_length_metric,
    record_mark_metric,
    record_measured_mass_metric,
    record_weight_metric,
    reset_metrics,
)


def setup_function():
    reset_metrics()


def test_build_metrics_report_lines_groups_duplicate_lengths():
    record_length_metric(
        "extrusion_profile",
        "4040",
        "left_z_axis_profile",
        550,
    )
    record_length_metric(
        "extrusion_profile",
        "4040",
        "right_z_axis_profile",
        550.0,
    )
    record_length_metric(
        "linear_rail",
        "MGN12",
        "x_axis_rail",
        450,
    )

    assert build_metrics_report_lines() == [
        "Cut stock metrics:",
        "extrusion_profile 4040:",
        "  550 mm x2",
        "    - left_z_axis_profile",
        "    - right_z_axis_profile",
        "linear_rail MGN12:",
        "  450 mm x1",
        "    - x_axis_rail",
    ]


def test_build_metrics_report_lines_handles_empty_collector():
    assert build_metrics_report_lines() == ["Cut stock metrics: no metrics recorded."]


def test_build_metrics_report_lines_rounds_lengths_to_whole_millimeters():
    record_length_metric(
        "extrusion_profile",
        "2020",
        "y_axis_profile_left",
        499.7,
    )

    assert build_metrics_report_lines() == [
        "Cut stock metrics:",
        "extrusion_profile 2020:",
        "  500 mm x1",
        "    - y_axis_profile_left",
    ]


def test_build_metrics_report_lines_includes_stock_marks():
    record_mark_metric(
        stock_type="2020",
        part_name="x_axis_lower_profile",
        stock_length_mm=600,
        mark_name="mount_shield_mount_screw_left",
        position_mm=87.6,
    )

    assert build_metrics_report_lines() == [
        "Cut stock metrics:",
        "Stock marks:",
        "x_axis_lower_profile (2020, 600 mm):",
        "  mark at 88 mm - mount_shield_mount_screw_left",
    ]


def test_build_metrics_report_lines_includes_weight_breakdown():
    record_weight_metric(
        "y_axis_moving_mass",
        Material.ALUMINUM,
        1000,
        part_id="print_bed_main",
    )
    record_weight_metric(
        "y_axis_moving_mass",
        Material.STEEL,
        1000,
        part_id="print_bed_mount_screws",
    )
    record_weight_metric(
        "y_axis_moving_mass",
        Material.STEEL,
        1000,
        part_id="print_bed_mount_screws",
    )

    assert build_metrics_report_lines() == [
        "Weight metrics:",
        "y_axis_moving_mass: 0.018400 kg",
        "  ALUMINUM: 0.002700 kg",
        "  STEEL: 0.015700 kg",
        "  print_bed_main (ALUMINUM): 0.002700 kg",
        "  print_bed_mount_screws (STEEL): 0.015700 kg",
    ]


def test_build_metrics_report_lines_supports_measured_mass_metrics():
    record_measured_mass_metric(
        "y_axis_moving_mass",
        Material.ALUMINUM,
        0.760,
        part_id="print_bed_main",
    )
    record_measured_mass_metric(
        "y_axis_moving_mass",
        Material.STEEL,
        0.414,
        part_id="print_bed_magnetic_foil",
    )

    assert build_metrics_report_lines() == [
        "Weight metrics:",
        "y_axis_moving_mass: 1.174000 kg",
        "  ALUMINUM: 0.760000 kg",
        "  STEEL: 0.414000 kg",
        "  print_bed_magnetic_foil (STEEL): 0.414000 kg",
        "  print_bed_main (ALUMINUM): 0.760000 kg",
    ]
