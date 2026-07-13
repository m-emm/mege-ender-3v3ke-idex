import pytest
import yaml
from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.mgn7h_rail_with_carriage_assembly import (
    create_mgn7h_rail_with_carriage_assembly,
)
from shellforgepy.simple import get_volume


RESOURCE_FILE = ASSEMBLIES_DIR / "mgn7h_rail_with_carriage_assembly.yaml"


def _load_resource():
    return yaml.load(RESOURCE_FILE.read_text(), Loader=AssemblyDefaultsLoader)


def test_mgn7h_production_smoke_routes_printable_mockup():
    production = _load_resource()["Builder"]["Production"]

    assert production["parts"] == [
        {
            "source": "self",
            "artifact": "followers",
            "names": ["rail_mockup_printable"],
            "name": "mgn7h_rail_mockup",
        }
    ]
    assert production["arrange"]["export_individual_parts"] is False
    assert production["arrange"]["auto_assign_plates"] is False

    plate = production["arrange"]["plates"][0]
    assert plate["parts"] == ["mgn7h_rail_mockup"]
    assert plate["process_data_preset"] == "pla_medium_strength_max_quality_06"
    overrides = plate["process_data"]["overrides"]["process_overrides"]
    assert overrides["enable_support"] == "0"
    assert overrides["brim_type"] == "no_brim"


def test_mgn7h_assembly_smoke_builds_visible_and_printable_parts():
    kwargs = assembly_kwargs(create_mgn7h_rail_with_carriage_assembly)
    assembly = create_mgn7h_rail_with_carriage_assembly(**kwargs)

    assert get_volume(assembly.leader) > 0
    assert get_volume(assembly.get_named_follower("carriage")) > 0
    assert get_volume(assembly.get_named_follower("rail_mockup_printable")) > 0

    hole_span = (
        kwargs["mgn7h_rail_length"] - 2 * kwargs["mgn7h_rail_mount_hole_end_offset"]
    )
    pitch_steps = hole_span / kwargs["mgn7h_rail_mount_hole_pitch"]
    assert pitch_steps == pytest.approx(round(pitch_steps))

    mounting_hole_names = [
        name
        for name, _part in assembly.get_named_cutter_items()
        if name.startswith("mounting_hole_")
    ]
    assert len(mounting_hole_names) == int(round(pitch_steps)) + 1
