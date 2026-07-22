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
from shellforgepy.simple import (
    Alignment,
    MScrew,
    align,
    get_bounding_box,
    get_bounding_box_center,
    get_volume,
)

ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"
RESOURCE_FILE = ASSEMBLIES_DIR / "y_axis_driver_board_holder_joiner.yaml"
HOLDER_ASSEMBLY_NAME = "y_axis_driver_board_holder_assembly"
DRIVER_ASSEMBLY_NAME = "bigtreetech_stepper_driver_tmc_5160t_plus_assembly"
JOINED_ASSEMBLY_NAME = "y_axis_driver_board_holder_joined_assembly"
REFERENCE_DRIVER_NAME = "reference_tmc5160t_plus_driver"


def _bbox_values(part):
    return tuple(value for corner in get_bounding_box(part) for value in corner)


def _intersection_volume(part, cutter):
    return get_volume(part) - get_volume(part.cut(cutter))


def _configured_holder_kwargs():
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    holder_config = next(
        entry for entry in config["assemblies"] if entry["name"] == HOLDER_ASSEMBLY_NAME
    )
    kwargs = {}
    for name, value in holder_config["parameters"].items():
        if isinstance(value, dict) and "$ref" in value:
            kwargs[name] = DEFAULTS[value["$ref"]]
        elif name == "pinout_base_plate_pinout_yaml_path":
            kwargs[name] = str(ASSEMBLIES_DIR.parents[1] / value)
        else:
            kwargs[name] = value
    return kwargs


@pytest.fixture(scope="module")
def positioned_inputs():
    holder = create_pinout_base_plate_assembly(**_configured_holder_kwargs())
    holder.additional_data["part_ref_origin"] = {"assembly_name": HOLDER_ASSEMBLY_NAME}
    driver = create_bigtreetech_stepper_driver_tmc_5160t_plus_assembly(
        **assembly_kwargs(create_bigtreetech_stepper_driver_tmc_5160t_plus_assembly)
    )
    driver.additional_data["part_ref_origin"] = {"assembly_name": DRIVER_ASSEMBLY_NAME}
    reference = holder.get_named_non_production_part(REFERENCE_DRIVER_NAME)
    driver = align(driver, reference, Alignment.CENTER, axes=[0, 1])
    driver = align(driver, reference, Alignment.BOTTOM)
    baseline = {
        "holder_bbox": _bbox_values(holder.leader),
        "holder_volume": get_volume(holder.leader),
        "driver_bbox": _bbox_values(driver.leader),
        "driver_volume": get_volume(driver.leader),
    }
    return holder, driver, baseline


@pytest.fixture(scope="module")
def joined_result(positioned_inputs):
    holder, driver, _baseline = positioned_inputs
    return join_y_axis_driver_board_holder_with_tmc5160t_plus(
        y_axis_driver_board_holder=holder,
        bigtreetech_stepper_driver=driver,
        board_holder_mount_screw_hole_inset=DEFAULTS[
            "board_holder_mount_screw_hole_inset"
        ],
    )


def test_joiner_returns_only_replacement_holder_without_mutating_inputs(
    positioned_inputs,
    joined_result,
):
    holder, driver, baseline = positioned_inputs

    assert set(joined_result) == {"y_axis_driver_board_holder"}
    joined_holder = joined_result["y_axis_driver_board_holder"]
    assert joined_holder is not holder
    assert REFERENCE_DRIVER_NAME in joined_holder.non_production_indices_by_name
    assert _bbox_values(holder.leader) == pytest.approx(baseline["holder_bbox"])
    assert get_volume(holder.leader) == pytest.approx(baseline["holder_volume"])
    assert _bbox_values(driver.leader) == pytest.approx(baseline["driver_bbox"])
    assert get_volume(driver.leader) == pytest.approx(baseline["driver_volume"])


def test_joined_holder_preserves_named_artifacts_and_consumes_only_original_holder(
    positioned_inputs,
    joined_result,
):
    holder, _driver, _baseline = positioned_inputs
    joined_holder = joined_result["y_axis_driver_board_holder"]

    assert set(joined_holder.follower_indices_by_name) == set(
        holder.follower_indices_by_name
    )
    assert set(joined_holder.cutter_indices_by_name) == {
        *holder.cutter_indices_by_name,
        "mount_screw_holes",
    }
    assert set(joined_holder.non_production_indices_by_name) == set(
        holder.non_production_indices_by_name
    )
    assert joined_holder.hidden_by_default_names == holder.hidden_by_default_names
    assert joined_holder.hidden_by_default_names is not holder.hidden_by_default_names

    expected_consumed_refs = {
        holder.part_ref_for_leader(),
        *(
            holder.part_ref_for_named_follower(name)
            for name in holder.follower_indices_by_name
        ),
        *(
            holder.part_ref_for_named_cutter(name)
            for name in holder.cutter_indices_by_name
        ),
        *(
            holder.part_ref_for_named_non_production_part(name)
            for name in holder.non_production_indices_by_name
        ),
    }
    assert set(joined_holder.consumed_part_refs()) == expected_consumed_refs
    assert all(
        not part_ref.startswith(f"{DRIVER_ASSEMBLY_NAME}.")
        for part_ref in joined_holder.consumed_part_refs()
    )


def test_positioned_driver_cutters_pass_through_replacement_plate(
    positioned_inputs,
    joined_result,
):
    _holder, driver, _baseline = positioned_inputs
    joined_holder = joined_result["y_axis_driver_board_holder"]

    for _name, cutter in driver.get_named_cutter_items():
        assert _intersection_volume(joined_holder.leader, cutter) == pytest.approx(
            0,
            abs=0.01,
        )


def test_outer_mount_holes_use_m3_normal_clearance_and_symmetric_edge_inset(
    joined_result,
):
    joined_holder = joined_result["y_axis_driver_board_holder"]
    centers = joined_holder.additional_data["mount_screw_hole_centers"]
    diameter = joined_holder.additional_data["mount_screw_hole_diameter"]
    inset = DEFAULTS["board_holder_mount_screw_hole_inset"]
    leader_bbox = get_bounding_box(joined_holder.leader)

    assert len(centers) == 4
    assert diameter == pytest.approx(MScrew.from_size("M3").clearance_hole_normal)
    assert len({round(center[0], 6) for center in centers}) == 2
    assert len({round(center[1], 6) for center in centers}) == 2
    for center in centers:
        assert min(
            abs(center[0] - leader_bbox[0][0]),
            abs(leader_bbox[1][0] - center[0]),
        ) == pytest.approx(inset)
        assert min(
            abs(center[1] - leader_bbox[0][1]),
            abs(leader_bbox[1][1] - center[1]),
        ) == pytest.approx(inset)


def test_joiner_resource_and_configuration_define_one_holder_output():
    resource = yaml.safe_load(RESOURCE_FILE.read_text())
    properties = resource["Parts"]["YAxisDriverBoardHolderJoiner"]["Properties"]
    configurable_parameters = set(
        inspect.signature(join_y_axis_driver_board_holder_with_tmc5160t_plus).parameters
    ) - {"y_axis_driver_board_holder", "bigtreetech_stepper_driver"}

    assert set(resource["Parameters"]) == configurable_parameters
    assert properties["Joiner"].endswith(
        ".y_axis_driver_board_holder_joiner."
        "join_y_axis_driver_board_holder_with_tmc5160t_plus"
    )
    assert set(resource["Builder"]["Outputs"]) == {"y_axis_driver_board_holder"}
    output = resource["Builder"]["Outputs"]["y_axis_driver_board_holder"]
    visualization = output["Visualization"]
    injected_driver_rules = [
        rule
        for rule in visualization["parts"]
        if rule["source"] == "injected"
        and rule["assembly"] == "bigtreetech_stepper_driver"
    ]
    assert {rule["artifact"] for rule in injected_driver_rules} == {
        "leader",
        "non_production_parts",
    }

    production = output["Production"]
    assert production["process_data_preset"] == ("petgcf_max_strength_high_speed_06")
    assert {part["artifact"] for part in production["parts"]} == {
        "leader",
        "followers",
    }
    assert all(part["source"] == "self" for part in production["parts"])

    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    assemblies = {entry["name"]: entry for entry in config["assemblies"]}
    join = assemblies["y_axis_driver_board_holder_join"]
    assert join["inject_parts"] == {
        "y_axis_driver_board_holder": HOLDER_ASSEMBLY_NAME,
        "bigtreetech_stepper_driver": DRIVER_ASSEMBLY_NAME,
    }
    assert join["outputs"] == {"y_axis_driver_board_holder": JOINED_ASSEMBLY_NAME}


def test_configuration_places_driver_before_joining_and_rigidly_groups_replacement():
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    placement = config["placement"]["alignments"]
    reference = f"{HOLDER_ASSEMBLY_NAME}.non_production_parts.{REFERENCE_DRIVER_NAME}"

    center_index = next(
        index
        for index, step in enumerate(placement)
        if step.get("part") == DRIVER_ASSEMBLY_NAME
        and step.get("to") == reference
        and step.get("alignment") == "CENTER"
        and step.get("axes") == [0, 1]
    )
    bottom_index = next(
        index
        for index, step in enumerate(placement)
        if step.get("part") == DRIVER_ASSEMBLY_NAME
        and step.get("to") == reference
        and step.get("alignment") == "BOTTOM"
    )
    input_group_index = next(
        index
        for index, step in enumerate(placement)
        if step.get("rigid_group") == [DRIVER_ASSEMBLY_NAME]
        and step.get("to") == HOLDER_ASSEMBLY_NAME
    )
    output_group_index = next(
        index
        for index, step in enumerate(placement)
        if step.get("rigid_group") == [JOINED_ASSEMBLY_NAME]
        and step.get("to") == DRIVER_ASSEMBLY_NAME
    )

    assert center_index < bottom_index < input_group_index < output_group_index
