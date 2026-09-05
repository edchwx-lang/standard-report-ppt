from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts" / "v63_scene_graph.py"
    spec = importlib.util.spec_from_file_location("v63_scene_graph_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def census() -> dict:
    return {
        "schema_version": "6.3",
        "deconstruction_runtime_revision": "6.3.1",
        "pages": {
            "S01": {
                "blueprint_sha256": "a" * 64,
                "body_roi_px": [100, 150, 1000, 400],
                "candidates": [
                    {"candidate_id": "C1", "kind": "panel", "expected_treatment": "editable"},
                    {"candidate_id": "C2", "kind": "logo", "expected_treatment": "crop"},
                    {"candidate_id": "C3", "kind": "text", "expected_treatment": "editable"},
                ],
            }
        },
    }


def scene() -> dict:
    return {
        "schema_version": "6.3",
        "deconstruction_runtime_revision": "6.3.1",
        "color_authority": "blueprint_body",
        "pages": {
            "S01": {
                "blueprint_sha256": "a" * 64,
                "body_roi_px": [100, 150, 1000, 400],
                "elements": [
                    {"element_id": "E1", "type": "rect", "bbox_px": [100, 150, 600, 350], "z_order": 1, "group_id": "G1", "style": {"fill": "#244A82", "line": "#244A82"}, "source_candidate_ids": ["C1"]},
                    {"element_id": "E2", "type": "image_crop", "bbox_px": [650, 180, 800, 260], "z_order": 2, "group_id": "G1", "asset_id": "LOGO_1", "intrinsic_text_only": True, "style": {}, "source_candidate_ids": ["C2"]},
                    {"element_id": "E3", "type": "text", "bbox_px": [150, 190, 450, 240], "z_order": 3, "group_id": "G1", "text": "Editable", "style": {"font_size": 12, "color": "#FFFFFF"}, "source_candidate_ids": ["C3"]},
                    {"element_id": "G1", "type": "group", "bbox_px": [100, 150, 800, 350], "z_order": 0, "style": {}, "source_candidate_ids": []},
                ],
                "candidate_resolutions": {
                    "C1": {"mode": "editable", "element_ids": ["E1"]},
                    "C2": {"mode": "crop", "element_ids": ["E2"]},
                    "C3": {"mode": "editable", "element_ids": ["E3"]},
                },
            }
        },
    }


class V63SceneGraphTests(unittest.TestCase):
    def test_atomic_graph_reconciles_every_census_candidate(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".build").mkdir()
            (project / ".build" / "v63_visual_census.json").write_text(
                json.dumps(census()), encoding="utf-8"
            )
            report = module.validate_and_write_scene_graph(project, scene())
            written = (project / ".build" / "v63_scene_graph.json").is_file()

        self.assertTrue(report["ok"], report["blockers"])
        self.assertTrue(written)
        self.assertEqual(4, report["element_count"])

    def test_unresolved_candidate_and_generic_component_are_blocked(self):
        module = load_module()
        invalid = deepcopy(scene())
        invalid["pages"]["S01"]["candidate_resolutions"].pop("C3")
        invalid["pages"]["S01"]["elements"][0]["type"] = "matrix"
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".build").mkdir()
            (project / ".build" / "v63_visual_census.json").write_text(
                json.dumps(census()), encoding="utf-8"
            )
            report = module.validate_scene_graph(project, invalid)

        codes = {item["code"] for item in report["blockers"]}
        self.assertIn("V63_SCENE_CANDIDATE_UNRESOLVED", codes)
        self.assertIn("V63_SCENE_GENERIC_COMPONENT_FORBIDDEN", codes)

    def test_pixel_box_maps_to_template_body_without_layout_redesign(self):
        actual = load_module().pixel_box_to_slide_box(
            [100, 150, 600, 350], [100, 150, 1000, 400], [0.5, 1.8, 12.0, 5.0]
        )
        self.assertEqual([0.5, 1.8, 6.0, 2.5], actual)


if __name__ == "__main__":
    unittest.main()
