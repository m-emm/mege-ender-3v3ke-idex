import inspect

import pytest
import yaml

pytest.importorskip("cadquery")

from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.bigtreetech_stepper_driver_tmc_5160t_plus_assembly import (
    create_bigtreetech_stepper_driver_tmc_5160t_plus_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.pinout_base_plate_assembly import (
    create_pinout_base_plate_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.y_axis_driver_board_holder_joiner import (
    join_y_axis_driver_board_holder_with_tmc5160t_plus,
)
from mege_ender_3v3ke_idex.designs.assemblies.y_axis_power_drive_housing_assembly import (
    CUTTER_OVERSIZE,
    LID_SCREW_ENGAGEMENT,
    LID_SCREW_SIZE,
    create_y_axis_power_drive_housing_assembly,
)
from shellforgepy.simple import (
    Alignment,
    MScrew,
    align,
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
)

ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"
RESOURCE_FILE = ASSEMBLIES_DIR / "y_axis_power_drive_housing_assembly.yaml"
ASSEMBLY_NAME = "y_axis_power_drive_housing_assembly"
PARAMETER_PREFIX = "y_axis_power_drive_housing_"


def _load_config():
    return yaml.load(
        ASSEMBLIES_FILE.read_text(),
        Loader=AssemblyDefaultsLoader,
    )


def _load_resource():
    return yaml.load(
        RESOURCE_FILE.read_text(),
        Loader=AssemblyDefaultsLoader,
    )


def _holder_kwargs():
    entry = next(
        assembly
        for assembly in _load_config()["assemblies"]
        if assembly["name"] == "y_axis_driver_board_holder_assembly"
    )
    kwargs = {}
    for name, value in entry["parameters"].items():
        if isinstance(value, dict) and "$ref" in value:
            kwargs[name] = DEFAULTS[value["$ref"]]
        elif name == "pinout_base_plate_pinout_yaml_path":
            kwargs[name] = str(ASSEMBLIES_DIR.parents[1] / value)
        else:
            kwargs[name] = value
    return kwargs


def _combined_bbox(parts):
    bounding_boxes = [get_bounding_box(part) for part in parts]
    return (
        tuple(
            min(bounding_box[0][axis] for bounding_box in bounding_boxes)
            for axis in range(3)
        ),
        tuple(
            max(bounding_box[1][axis] for bounding_box in bounding_boxes)
            for axis in range(3)
        ),
    )


def _intersection_volume(part, cutter):
    return get_volume(part) - get_volume(part.cut(cutter))


@pytest.fixture(scope="module")
def housing_inputs():
    holder = create_pinout_base_plate_assembly(**_holder_kwargs())
    holder.additional_data["part_ref_origin"] = {
        "assembly_name": "y_axis_driver_board_holder_assembly"
    }

    driver = create_bigtreetech_stepper_driver_tmc_5160t_plus_assembly(
        **assembly_kwargs(create_bigtreetech_stepper_driver_tmc_5160t_plus_assembly)
    )
    driver.additional_data["part_ref_origin"] = {
        "assembly_name": "bigtreetech_stepper_driver_tmc_5160t_plus_assembly"
    }
    driver_reference = holder.get_named_non_production_part(
        "reference_tmc5160t_plus_driver"
    )
    driver = align(driver, driver_reference, Alignment.CENTER, axes=[0, 1])
    driver = align(driver, driver_reference, Alignment.BOTTOM)

    joined_holder = join_y_axis_driver_board_holder_with_tmc5160t_plus(
        y_axis_driver_board_holder=holder,
        bigtreetech_stepper_driver=driver,
        board_holder_mount_screw_hole_inset=DEFAULTS[
            "y_axis_driver_board_holder_mount_screw_hole_inset"
        ],
    )["y_axis_driver_board_holder"]

    housing = create_y_axis_power_drive_housing_assembly(
        **assembly_kwargs(
            create_y_axis_power_drive_housing_assembly,
            y_axis_driver_board_holder_joined=joined_holder,
            bigtreetech_stepper_driver=driver,
        )
    )
    return joined_holder, driver, housing


def test_y_axis_power_drive_housing_exports_stable_artifacts(housing_inputs):
    _joined_holder, _driver, housing = housing_inputs

    assert get_volume(housing.leader) > 0
    assert set(housing.follower_indices_by_name) == {
        "y_axis_power_drive_housing_top_lid",
        "y_axis_power_drive_housing_bottom_lid",
    }

    expected_cutters = {"inner_space"}
    expected_non_production = set()
    for lid_name in ["top", "bottom"]:
        for index in range(2):
            prefix = f"{lid_name}_lid_mount_screw_{index}"
            expected_cutters.update(
                {
                    f"{prefix}_clearance_hole",
                    f"{prefix}_thread_inset_pocket",
                }
            )
            expected_non_production.update(
                {
                    f"{prefix}_screw",
                    f"{prefix}_thread_inset",
                }
            )

    assert set(housing.cutter_indices_by_name) == expected_cutters
    assert set(housing.non_production_indices_by_name) == expected_non_production
    assert housing.additional_data["lid_screw_size"] == LID_SCREW_SIZE
    assert housing.additional_data["lid_screw_length"] == pytest.approx(
        DEFAULTS["y_axis_power_drive_housing_lid_thickness"] + LID_SCREW_ENGAGEMENT
    )

    all_names = (
        set(housing.follower_indices_by_name)
        | set(housing.cutter_indices_by_name)
        | set(housing.non_production_indices_by_name)
    )
    forbidden_fragments = ("fan", "cooling", "cable", "mount_flange")
    assert not any(
        fragment in name for name in all_names for fragment in forbidden_fragments
    )


def test_housing_envelope_includes_all_physical_artifacts(housing_inputs):
    joined_holder, driver, housing = housing_inputs
    physical_parts = [
        joined_holder.leader,
        *joined_holder.followers,
        *joined_holder.non_production_parts,
        driver.leader,
        *driver.non_production_parts,
    ]
    expected_physical_bbox = _combined_bbox(physical_parts)

    assert tuple(
        value
        for corner in housing.additional_data["physical_envelope_bbox"]
        for value in corner
    ) == pytest.approx(
        tuple(value for corner in expected_physical_bbox for value in corner)
    )

    leader_only_bbox = _combined_bbox([joined_holder.leader, driver.leader])
    assert expected_physical_bbox[0][2] < leader_only_bbox[0][2]
    assert expected_physical_bbox[1][2] > leader_only_bbox[1][2]
    assert expected_physical_bbox[0][2] == pytest.approx(
        min(get_bounding_box(part)[0][2] for part in joined_holder.non_production_parts)
    )
    assert expected_physical_bbox[1][2] == pytest.approx(
        max(get_bounding_box(part)[1][2] for part in driver.non_production_parts)
    )

    inner_space_bbox = get_bounding_box(housing.get_named_cutter("inner_space"))
    board_wall_clearance = DEFAULTS["y_axis_power_drive_housing_board_wall_clearance"]
    assert inner_space_bbox[0][0] == pytest.approx(
        expected_physical_bbox[0][0] - board_wall_clearance
    )
    assert inner_space_bbox[1][0] == pytest.approx(
        expected_physical_bbox[1][0] + board_wall_clearance
    )
    assert inner_space_bbox[0][1] == pytest.approx(
        expected_physical_bbox[0][1] - board_wall_clearance
    )
    assert inner_space_bbox[1][1] == pytest.approx(
        expected_physical_bbox[1][1] + board_wall_clearance
    )
    assert inner_space_bbox[0][2] == pytest.approx(
        expected_physical_bbox[0][2]
        - DEFAULTS["y_axis_power_drive_housing_z_clearance_bottom"]
        - CUTTER_OVERSIZE / 2
    )
    assert inner_space_bbox[1][2] == pytest.approx(
        expected_physical_bbox[1][2]
        + DEFAULTS["y_axis_power_drive_housing_z_clearance_top"]
        + CUTTER_OVERSIZE / 2
    )


def test_two_lid_fasteners_share_opposite_diagonal_posts(housing_inputs):
    _joined_holder, _driver, housing = housing_inputs
    inner_space_bbox = get_bounding_box(housing.get_named_cutter("inner_space"))
    post_centers = housing.additional_data["post_centers"]

    assert set(post_centers) == {"front_left", "back_right"}
    assert post_centers["front_left"][:2] == pytest.approx(
        [inner_space_bbox[0][0], inner_space_bbox[0][1]]
    )
    assert post_centers["back_right"][:2] == pytest.approx(
        [inner_space_bbox[1][0], inner_space_bbox[1][1]]
    )

    for index in range(2):
        top_hole = housing.get_named_cutter(
            f"top_lid_mount_screw_{index}_clearance_hole"
        )
        bottom_hole = housing.get_named_cutter(
            f"bottom_lid_mount_screw_{index}_clearance_hole"
        )
        assert get_bounding_box_center(top_hole)[:2] == pytest.approx(
            get_bounding_box_center(bottom_hole)[:2]
        )


def test_lid_hardware_uses_m3_clearance_and_lid_side_insert_pockets(housing_inputs):
    _joined_holder, _driver, housing = housing_inputs
    screw = MScrew.from_size(LID_SCREW_SIZE)
    body_bbox = get_bounding_box(housing.leader)

    for lid_name in ["top", "bottom"]:
        for index in range(2):
            prefix = f"{lid_name}_lid_mount_screw_{index}"
            clearance_hole = housing.get_named_cutter(f"{prefix}_clearance_hole")
            insert_pocket = housing.get_named_cutter(f"{prefix}_thread_inset_pocket")
            thread_inset = housing.get_named_non_production_part(
                f"{prefix}_thread_inset"
            )

            assert get_bounding_box_size(clearance_hole)[:2] == pytest.approx(
                [screw.clearance_hole_loose, screw.clearance_hole_loose]
            )
            assert get_bounding_box_size(thread_inset)[2] == pytest.approx(
                screw.thread_inset_length
            )
            if lid_name == "top":
                assert get_bounding_box(insert_pocket)[1][2] == pytest.approx(
                    body_bbox[1][2]
                )
            else:
                assert get_bounding_box(insert_pocket)[0][2] == pytest.approx(
                    body_bbox[0][2]
                )


def test_housing_posts_and_lid_rims_clear_the_physical_envelope(housing_inputs):
    _joined_holder, _driver, housing = housing_inputs
    physical_bbox = housing.additional_data["physical_envelope_bbox"]
    post_centers = housing.additional_data["post_centers"]
    post_radius = housing.additional_data["post_radius"]
    assert post_centers["front_left"][0] + post_radius < physical_bbox[0][0]
    assert post_centers["front_left"][1] + post_radius < physical_bbox[0][1]
    assert post_centers["back_right"][0] - post_radius > physical_bbox[1][0]
    assert post_centers["back_right"][1] - post_radius > physical_bbox[1][1]

    for lid_name in ["top", "bottom"]:
        lid = housing.get_named_follower(f"y_axis_power_drive_housing_{lid_name}_lid")
        assert _intersection_volume(housing.leader, lid) == pytest.approx(
            0,
            abs=0.01,
        )


def test_resource_and_builder_registration_match_the_small_parameter_contract():
    resource = _load_resource()
    parameter_names = set(resource["Parameters"])
    configurable_parameters = set(
        inspect.signature(create_y_axis_power_drive_housing_assembly).parameters
    ) - {
        "y_axis_driver_board_holder_joined",
        "bigtreetech_stepper_driver",
    }

    assert parameter_names == configurable_parameters
    assert all(name.startswith(PARAMETER_PREFIX) for name in parameter_names)
    generator = resource["Parts"]["YAxisPowerDriveHousingAssembly"]["Properties"][
        "Generator"
    ]
    assert generator.endswith(
        ".y_axis_power_drive_housing_assembly."
        "create_y_axis_power_drive_housing_assembly"
    )

    assemblies = {entry["name"]: entry for entry in _load_config()["assemblies"]}
    entry = assemblies[ASSEMBLY_NAME]
    assert entry["depends_on"] == [
        "y_axis_driver_board_holder_joined_assembly",
        "bigtreetech_stepper_driver_tmc_5160t_plus_assembly",
    ]
    assert entry["inject_parts"] == {
        "y_axis_driver_board_holder_joined": (
            "y_axis_driver_board_holder_joined_assembly"
        ),
        "bigtreetech_stepper_driver": (
            "bigtreetech_stepper_driver_tmc_5160t_plus_assembly"
        ),
    }
    assert set(entry["parameters"]) == parameter_names
    assert all(value == {"$ref": name} for name, value in entry["parameters"].items())


def test_visualization_and_production_contracts_exclude_cutters_and_split_plates():
    resource = _load_resource()
    visualization = resource["Builder"]["Visualization"]
    assert all(part["artifact"] != "cutters" for part in visualization["parts"])

    injected_rules = [
        part for part in visualization["parts"] if part["source"] == "injected"
    ]
    assert {(part["assembly"], part["artifact"]) for part in injected_rules} == {
        ("y_axis_driver_board_holder_joined", "leader"),
        ("y_axis_driver_board_holder_joined", "followers"),
        ("y_axis_driver_board_holder_joined", "non_production_parts"),
        ("bigtreetech_stepper_driver", "leader"),
        ("bigtreetech_stepper_driver", "non_production_parts"),
    }

    production = resource["Builder"]["Production"]
    assert production["process_data_preset"] == ("petgcf_max_strength_high_speed_06")
    plates = production["arrange"]["plates"]
    assert [plate["name"] for plate in plates] == [
        "y_axis_power_drive_housing",
        "y_axis_power_drive_housing_top_lid",
        "y_axis_power_drive_housing_bottom_lid",
    ]
    assert all(len(plate["parts"]) == 1 for plate in plates)
    assert plates[0]["process_data"]["overrides"]["process_overrides"] == {
        "enable_support": "1"
    }
    assert all("process_data" not in plate for plate in plates[1:])
    assert production["arrange"]["auto_assign_plates"] is False
