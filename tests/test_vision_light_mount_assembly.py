import pytest
import yaml

pytest.importorskip("cadquery")

from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.apa_strip_assembly import (
    create_apa_strip_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.vision_light_mount_assembly import (
    create_vision_light_mount_assembly,
)
from shellforgepy.simple import (
    Alignment,
    LeaderFollowersCuttersPart,
    align,
    create_box,
    get_bounding_box,
    get_bounding_box_size,
    get_volume,
    rotate,
)


APA_RESOURCE_FILE = ASSEMBLIES_DIR / "apa_strip_assembly.yaml"
VISION_RESOURCE_FILE = ASSEMBLIES_DIR / "vision_light_mount_assembly.yaml"
UNDERCARRIAGE_RESOURCE_FILE = (
    ASSEMBLIES_DIR / "print_bed_undercarriage_assembly.yaml"
)
WHOLE_PRINTER_RESOURCE_FILE = ASSEMBLIES_DIR / "whole_printer_assembly.yaml"


def _load_yaml(path):
    return yaml.load(path.read_text(), Loader=AssemblyDefaultsLoader)


def _load_assemblies_config():
    return _load_yaml(ASSEMBLIES_DIR / "assemblies.yaml")


def _create_strip(density="D60pm", num_leds=2):
    return create_apa_strip_assembly(
        apa_strip_density=density,
        apa_strip_num_leds=num_leds,
        apa_strip_with_hull=False,
    )


def _placed_strip_ring(aperture_size=30.0):
    aperture_reference = create_box(aperture_size, aperture_size, 0.1)
    aperture_reference = align(
        aperture_reference,
        None,
        Alignment.CENTER,
        axes=[0, 1],
    )

    front = align(_create_strip(), None, Alignment.CENTER, axes=[0, 1])
    front = align(front, aperture_reference, Alignment.STACK_FRONT)

    back = align(_create_strip(), None, Alignment.CENTER, axes=[0, 1])
    back = align(back, aperture_reference, Alignment.STACK_BACK)

    left = align(_create_strip(), None, Alignment.CENTER, axes=[0, 1])
    left = rotate(90, axis=(0, 0, 1), center=(0, 0, 0))(left)
    left = align(left, aperture_reference, Alignment.CENTER, axes=[1])
    left = align(left, aperture_reference, Alignment.STACK_LEFT)

    right = align(_create_strip(), None, Alignment.CENTER, axes=[0, 1])
    right = rotate(90, axis=(0, 0, 1), center=(0, 0, 0))(right)
    right = align(right, aperture_reference, Alignment.CENTER, axes=[1])
    right = align(right, aperture_reference, Alignment.STACK_RIGHT)

    return {
        "apa_strip_front": front,
        "apa_strip_back": back,
        "apa_strip_left": left,
        "apa_strip_right": right,
    }


def _print_bed_reference():
    bed = create_box(90, 90, 3)
    bed = align(bed, None, Alignment.CENTER, axes=[0, 1])
    return LeaderFollowersCuttersPart(bed)


def _undercarriage_reference():
    front_left = create_box(30, 16, 20)
    front_left = align(front_left, None, Alignment.CENTER, axes=[1])

    front_right = create_box(30, 16, 20)
    front_right = align(front_right, front_left, Alignment.STACK_RIGHT)

    leader = front_left.fuse(front_right)
    undercarriage = LeaderFollowersCuttersPart(leader)
    undercarriage.add_named_follower(front_left, "front_left_uc")
    undercarriage.add_named_follower(front_right, "front_right_uc")
    return undercarriage


def _build_mount():
    return create_vision_light_mount_assembly(
        **assembly_kwargs(
            create_vision_light_mount_assembly,
            print_bed=_print_bed_reference(),
            print_bed_undercarriage=_undercarriage_reference(),
            **_placed_strip_ring(),
        )
    )


def test_apa_strip_assembly_uses_pcb_as_alignment_leader():
    strip = _create_strip()

    assert get_volume(strip.leader) > 0
    assert {"apa_led_1", "apa_led_2"} <= set(strip.follower_indices_by_name)
    assert len(
        [name for name in strip.follower_indices_by_name if name.startswith("apa_pad_")]
    ) == 8

    leader_size = get_bounding_box_size(strip.leader)
    assert leader_size[0] > leader_size[1] > leader_size[2]

    leader_bbox = get_bounding_box(strip.leader)
    led_bbox = get_bounding_box(strip.get_named_follower("apa_led_1"))
    assert led_bbox[0][2] >= leader_bbox[1][2]


def test_apa_strip_density_changes_length_on_x_axis():
    d60 = _create_strip("D60pm")
    d144 = _create_strip("D144pm")

    assert get_bounding_box_size(d60.leader)[0] > get_bounding_box_size(d144.leader)[0]
    assert get_bounding_box_size(d60.leader)[1] != get_bounding_box_size(d144.leader)[1]


def test_vision_light_mount_derives_aperture_and_exports_only_own_references():
    mount = _build_mount()

    assert get_volume(mount.leader) > 0
    assert set(mount.follower_indices_by_name) == {"vision_light_mount_clamp_cap"}
    assert set(mount.non_production_indices_by_name) == {"clamp_screws", "clamp_nuts"}
    assert {
        "aperture",
        "strip_pockets",
        "undercarriage_keepout",
        "clamp_screw_holes",
    } <= set(mount.cutter_indices_by_name)

    aperture_size = get_bounding_box_size(mount.get_named_cutter("aperture"))
    assert aperture_size[0] == pytest.approx(aperture_size[1], abs=0.05)
    assert aperture_size[0] == pytest.approx(
        DEFAULTS["vision_light_mount_aperture_size"]
    )


def test_vision_light_mount_saddle_brackets_front_spar_keepout():
    mount = _build_mount()

    leader_bbox = get_bounding_box(mount.leader)
    cap_bbox = get_bounding_box(mount.get_named_follower("vision_light_mount_clamp_cap"))
    keepout_bbox = get_bounding_box(mount.get_named_cutter("undercarriage_keepout"))

    assert leader_bbox[0][1] < keepout_bbox[0][1]
    assert leader_bbox[1][1] >= keepout_bbox[1][1]
    assert leader_bbox[0][2] < keepout_bbox[0][2]
    assert leader_bbox[1][2] > keepout_bbox[1][2]
    assert cap_bbox[0][1] >= keepout_bbox[1][1] - 0.05


def test_vision_light_mount_yaml_wiring_and_preview_context():
    config = _load_assemblies_config()
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    mount_entry = assemblies["vision_light_mount_assembly"]
    assert mount_entry["resource_file"] == "vision_light_mount_assembly.yaml"
    assert mount_entry["inject_parts"] == {
        "print_bed": "print_bed_assembly",
        "print_bed_undercarriage": "print_bed_undercarriage_assembly",
        "apa_strip_front": "apa_strip_front_assembly",
        "apa_strip_back": "apa_strip_back_assembly",
        "apa_strip_left": "apa_strip_left_assembly",
        "apa_strip_right": "apa_strip_right_assembly",
    }

    resource = _load_yaml(VISION_RESOURCE_FILE)
    visualization = resource["Builder"]["Visualization"]["parts"]
    injected = {
        part.get("assembly")
        for part in visualization
        if part.get("source") == "injected"
    }
    assert {
        "print_bed",
        "print_bed_undercarriage",
        "apa_strip_front",
        "apa_strip_back",
        "apa_strip_left",
        "apa_strip_right",
    } <= injected
    assert not any(
        part.get("source") == "self"
        and part.get("artifact") == "non_production_parts"
        and "apa_strip_*" in part.get("names", [])
        for part in visualization
    )

    production = resource["Builder"]["Production"]
    assert production["process_data_preset"] == "petgcf_max_strength_high_speed_06"
    assert production["parts"] == [
        {
            "source": "self",
            "artifact": "leader",
            "name": "vision_light_mount",
        },
        {
            "source": "self",
            "artifact": "followers",
            "names": ["vision_light_mount_clamp_cap"],
            "name_template": "{name}",
        },
    ]


def test_undercarriage_preview_exists_and_whole_printer_is_unmodified():
    undercarriage_resource = _load_yaml(UNDERCARRIAGE_RESOURCE_FILE)
    preview = undercarriage_resource["Builder"]["Visualization"]["preview"]
    assert preview["enabled"] is True
    assert {"isometric", "top", "front"} <= set(preview["views"])

    config = _load_assemblies_config()
    whole_printer = {
        assembly["name"]: assembly for assembly in config["assemblies"]
    }["whole_printer_assembly"]
    assert "vision_light_mount_assembly" not in whole_printer["depends_on"]
    assert "vision_light_mount" not in whole_printer["inject_parts"]

    whole_printer_resource = _load_yaml(WHOLE_PRINTER_RESOURCE_FILE)
    visualization = whole_printer_resource["Builder"]["Visualization"]["parts"]
    assert not any(part.get("assembly") == "vision_light_mount" for part in visualization)
    assert not any(
        part.get("assembly", "").startswith("apa_strip_") for part in visualization
    )


def test_apa_strip_resource_has_no_production_parts_or_default_hull_visual():
    resource = _load_yaml(APA_RESOURCE_FILE)
    visualization = resource["Builder"]["Visualization"]["parts"]

    assert resource["Builder"]["Production"]["parts"] == []
    assert not any("apa_strip_hull" in part.get("names", []) for part in visualization)
