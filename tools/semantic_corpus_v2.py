"""Independent synthetic furniture topologies added by semantic corpus v2."""
from __future__ import annotations

from typing import Any


V2_VIEW_PROFILES = (
    "full_three_view",
    "missing_front",
    "missing_side",
    "missing_top",
    "occluded_front",
)


def _item(identifier: str, role: str, bounds: tuple[float, ...]) -> dict[str, Any]:
    return {"occurrence_id": identifier, "role": role, "bounds_mm": list(bounds)}


def _design(
    project_id: str,
    family: str,
    split: str,
    occurrences: tuple[dict[str, Any], ...],
    relations: tuple[tuple[str, str, str], ...],
    alternative: tuple[str, str, str],
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "product_family": family,
        "split": split,
        "variants": V2_VIEW_PROFILES,
        "occurrences": occurrences,
        "relations": relations,
        "alternative_relation": alternative,
    }


def additional_designs_v2() -> tuple[dict[str, Any], ...]:
    """Return ten hand-authored designs, each with a distinct role graph."""

    return (
        _design(
            "dev-four-leg-desk", "workspace", "development",
            (
                _item("o1", "desktop", (0, 0, 720, 1400, 700, 750)),
                _item("o2", "leg", (60, 60, 0, 120, 120, 720)),
                _item("o3", "leg", (1280, 60, 0, 1340, 120, 720)),
                _item("o4", "leg", (60, 580, 0, 120, 640, 720)),
                _item("o5", "leg", (1280, 580, 0, 1340, 640, 720)),
                _item("o6", "rear_apron", (120, 610, 650, 1280, 640, 720)),
                _item("o7", "side_apron", (60, 120, 650, 120, 580, 720)),
                _item("o8", "side_apron", (1280, 120, 650, 1340, 580, 720)),
            ),
            (("desktop", "supported_by", "leg"), ("rear_apron", "fixed_to", "leg"),
             ("side_apron", "fixed_to", "leg")),
            ("desktop", "fixed_to", "leg"),
        ),
        _design(
            "dev-cubby-bench", "seating", "development",
            (
                _item("o1", "side_panel", (0, 0, 0, 20, 430, 500)),
                _item("o2", "side_panel", (1180, 0, 0, 1200, 430, 500)),
                _item("o3", "seat", (20, 0, 480, 1180, 430, 520)),
                _item("o4", "bottom_panel", (20, 0, 0, 1180, 430, 20)),
                _item("o5", "cubby_divider", (400, 20, 20, 420, 430, 480)),
                _item("o6", "cubby_divider", (780, 20, 20, 800, 430, 480)),
                _item("o7", "front_rail", (20, 0, 420, 1180, 20, 480)),
            ),
            (("seat", "supported_by", "side_panel"), ("bottom_panel", "fixed_to", "side_panel"),
             ("cubby_divider", "fixed_to", "seat"), ("front_rail", "fixed_to", "side_panel")),
            ("seat", "fixed_to", "side_panel"),
        ),
        _design(
            "hold-v2-bar-stool", "seating", "reserved",
            (
                _item("o1", "seat", (0, 0, 700, 450, 450, 740)),
                _item("o2", "leg", (30, 30, 0, 70, 70, 700)),
                _item("o3", "leg", (380, 30, 0, 420, 70, 700)),
                _item("o4", "leg", (30, 380, 0, 70, 420, 700)),
                _item("o5", "leg", (380, 380, 0, 420, 420, 700)),
                _item("o6", "front_footrest", (70, 30, 250, 380, 70, 280)),
                _item("o7", "rear_footrest", (70, 380, 250, 380, 420, 280)),
                _item("o8", "side_footrest", (30, 70, 250, 70, 380, 280)),
                _item("o9", "side_footrest", (380, 70, 250, 420, 380, 280)),
            ),
            (("seat", "supported_by", "leg"), ("front_footrest", "fixed_to", "leg"),
             ("rear_footrest", "fixed_to", "leg"), ("side_footrest", "fixed_to", "leg")),
            ("seat", "fixed_to", "leg"),
        ),
        _design(
            "dev-media-console", "storage", "development",
            (
                _item("o1", "side_panel", (0, 0, 0, 18, 420, 620)),
                _item("o2", "side_panel", (1582, 0, 0, 1600, 420, 620)),
                _item("o3", "top_panel", (18, 0, 602, 1582, 420, 620)),
                _item("o4", "bottom_panel", (18, 0, 0, 1582, 420, 18)),
                _item("o5", "center_divider", (791, 0, 18, 809, 420, 602)),
                _item("o6", "media_shelf", (18, 0, 300, 791, 420, 318)),
                _item("o7", "media_shelf", (809, 0, 300, 1582, 420, 318)),
                _item("o8", "sliding_front", (18, -18, 18, 791, 0, 602)),
                _item("o9", "sliding_front", (809, -18, 18, 1582, 0, 602)),
            ),
            (("top_panel", "fixed_to", "side_panel"), ("bottom_panel", "fixed_to", "side_panel"),
             ("center_divider", "fixed_to", "top_panel"), ("media_shelf", "supported_by", "side_panel"),
             ("sliding_front", "fixed_to", "top_panel")),
            ("media_shelf", "fixed_to", "side_panel"),
        ),
        _design(
            "dev-rail-wall-shelf", "shelving", "development",
            (
                _item("o1", "vertical_rail", (100, 300, 0, 130, 320, 1200)),
                _item("o2", "vertical_rail", (870, 300, 0, 900, 320, 1200)),
                _item("o3", "shelf", (0, 0, 280, 1000, 300, 300)),
                _item("o4", "shelf", (0, 0, 580, 1000, 300, 600)),
                _item("o5", "shelf", (0, 0, 880, 1000, 300, 900)),
                _item("o6", "bracket", (100, 250, 240, 130, 300, 280)),
                _item("o7", "bracket", (870, 250, 240, 900, 300, 280)),
                _item("o8", "bracket", (100, 250, 540, 130, 300, 580)),
                _item("o9", "bracket", (870, 250, 540, 900, 300, 580)),
                _item("o10", "bracket", (100, 250, 840, 130, 300, 880)),
                _item("o11", "bracket", (870, 250, 840, 900, 300, 880)),
            ),
            (("shelf", "supported_by", "bracket"), ("bracket", "fixed_to", "vertical_rail")),
            ("shelf", "fixed_to", "bracket"),
        ),
        _design(
            "hold-v2-drawer-chest", "storage", "reserved",
            (
                _item("o1", "side_panel", (0, 0, 0, 18, 500, 900)),
                _item("o2", "side_panel", (782, 0, 0, 800, 500, 900)),
                _item("o3", "top_panel", (18, 0, 882, 782, 500, 900)),
                _item("o4", "bottom_panel", (18, 0, 0, 782, 500, 18)),
                _item("o5", "back_panel", (18, 480, 18, 782, 500, 882)),
                _item("o6", "drawer_box", (18, 0, 80, 782, 480, 230)),
                _item("o7", "drawer_box", (18, 0, 280, 782, 480, 430)),
                _item("o8", "drawer_box", (18, 0, 480, 782, 480, 630)),
                _item("o9", "drawer_box", (18, 0, 680, 782, 480, 830)),
                _item("o10", "drawer_front", (18, -20, 60, 782, 0, 250)),
                _item("o11", "drawer_front", (18, -20, 260, 782, 0, 450)),
                _item("o12", "drawer_front", (18, -20, 460, 782, 0, 650)),
                _item("o13", "drawer_front", (18, -20, 660, 782, 0, 850)),
            ),
            (("top_panel", "fixed_to", "side_panel"), ("bottom_panel", "fixed_to", "side_panel"),
             ("back_panel", "fixed_to", "side_panel"), ("drawer_front", "fixed_to", "drawer_box"),
             ("drawer_box", "supported_by", "side_panel")),
            ("drawer_box", "fixed_to", "side_panel"),
        ),
        _design(
            "hold-v2-corner-workstation", "workspace", "reserved",
            (
                _item("o1", "main_desktop", (0, 0, 720, 1200, 500, 750)),
                _item("o2", "return_desktop", (700, 500, 720, 1200, 1000, 750)),
                _item("o3", "outer_leg", (40, 40, 0, 100, 100, 720)),
                _item("o4", "outer_leg", (1100, 40, 0, 1160, 100, 720)),
                _item("o5", "return_leg", (1100, 900, 0, 1160, 960, 720)),
                _item("o6", "corner_leg", (700, 500, 0, 760, 560, 720)),
                _item("o7", "cable_rail", (100, 450, 620, 700, 480, 670)),
            ),
            (("main_desktop", "supported_by", "outer_leg"), ("return_desktop", "supported_by", "return_leg"),
             ("return_desktop", "supported_by", "corner_leg"), ("cable_rail", "fixed_to", "main_desktop")),
            ("main_desktop", "fixed_to", "outer_leg"),
        ),
        _design(
            "hold-v2-armchair", "seating", "reserved",
            (
                _item("o1", "seat", (120, 100, 420, 680, 650, 460)),
                _item("o2", "front_leg", (120, 100, 0, 180, 160, 420)),
                _item("o3", "front_leg", (620, 100, 0, 680, 160, 420)),
                _item("o4", "rear_leg", (120, 590, 0, 180, 650, 420)),
                _item("o5", "rear_leg", (620, 590, 0, 680, 650, 420)),
                _item("o6", "backrest", (120, 620, 460, 680, 650, 1050)),
                _item("o7", "armrest", (70, 100, 650, 120, 620, 700)),
                _item("o8", "armrest", (680, 100, 650, 730, 620, 700)),
            ),
            (("seat", "supported_by", "front_leg"), ("seat", "supported_by", "rear_leg"),
             ("backrest", "fixed_to", "rear_leg"), ("armrest", "fixed_to", "backrest")),
            ("seat", "fixed_to", "rear_leg"),
        ),
        _design(
            "hold-v2-console-frame", "workspace", "reserved",
            (
                _item("o1", "console_top", (0, 0, 760, 1200, 360, 800)),
                _item("o2", "front_leg", (80, 40, 0, 130, 90, 760)),
                _item("o3", "front_leg", (1070, 40, 0, 1120, 90, 760)),
                _item("o4", "rear_leg", (80, 270, 0, 130, 320, 760)),
                _item("o5", "rear_leg", (1070, 270, 0, 1120, 320, 760)),
                _item("o6", "lower_stretcher", (130, 285, 180, 1070, 305, 230)),
                _item("o7", "upper_rail", (130, 285, 650, 1070, 305, 700)),
                _item("o8", "center_brace", (575, 285, 230, 625, 305, 650)),
            ),
            (("console_top", "supported_by", "front_leg"), ("console_top", "supported_by", "rear_leg"),
             ("lower_stretcher", "fixed_to", "rear_leg"), ("upper_rail", "fixed_to", "rear_leg"),
             ("center_brace", "fixed_to", "lower_stretcher")),
            ("console_top", "fixed_to", "rear_leg"),
        ),
        _design(
            "hold-v2-wardrobe", "storage", "reserved",
            (
                _item("o1", "side_panel", (0, 0, 0, 18, 600, 2100)),
                _item("o2", "side_panel", (1482, 0, 0, 1500, 600, 2100)),
                _item("o3", "top_panel", (18, 0, 2082, 1482, 600, 2100)),
                _item("o4", "bottom_panel", (18, 0, 0, 1482, 600, 18)),
                _item("o5", "back_panel", (18, 580, 18, 1482, 600, 2082)),
                _item("o6", "center_divider", (741, 0, 18, 759, 580, 2082)),
                _item("o7", "linen_shelf", (18, 0, 680, 741, 580, 698)),
                _item("o8", "linen_shelf", (18, 0, 1360, 741, 580, 1378)),
                _item("o9", "clothes_rail", (820, 280, 1500, 1420, 320, 1540)),
                _item("o10", "door", (18, -20, 18, 741, 0, 2082)),
                _item("o11", "door", (759, -20, 18, 1482, 0, 2082)),
            ),
            (("top_panel", "fixed_to", "side_panel"), ("bottom_panel", "fixed_to", "side_panel"),
             ("back_panel", "fixed_to", "side_panel"), ("center_divider", "fixed_to", "top_panel"),
             ("linen_shelf", "supported_by", "side_panel"), ("clothes_rail", "fixed_to", "side_panel"),
             ("door", "hinged_to", "side_panel")),
            ("linen_shelf", "fixed_to", "side_panel"),
        ),
    )
