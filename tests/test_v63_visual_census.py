from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_project(root: Path):
    (root / "blueprints").mkdir()
    image = Image.new("RGB", (1200, 675), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((120, 200, 500, 500), fill="#244a82")
    image.save(root / "blueprints" / "S01.png")
    return load("v63_visual_tiles").generate_review_tiles(
        root, template_path=ROOT / "assets" / "company_template.pptx", legacy_template_roi=True
    )


class V63VisualCensusTests(unittest.TestCase):
    def test_valid_census_is_hash_bound_and_written(self):
        module = load("v63_visual_census")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            tiles = make_project(project)
            page = tiles["pages"]["S01"]
            census = {
                "schema_version": "6.3",
                "deconstruction_runtime_revision": "6.3.1",
                "pages": {
                    "S01": {
                        "blueprint_sha256": page["blueprint_sha256"],
                        "body_roi_px": page["body_roi_px"],
                        "reviewed_tile_ids": [item["tile_id"] for item in page["tiles"]],
                        "candidates": [
                            {
                                "candidate_id": "S01-C001",
                                "kind": "panel",
                                "bbox_px": [120, 200, 500, 500],
                                "review_tile_ids": ["FULL", "B01", "B04"],
                                "expected_treatment": "editable",
                                "confidence": "high"
                            }
                        ]
                    }
                }
            }
            report = module.validate_and_write_visual_census(project, census)
            stored = (project / ".build" / "v63_visual_census.json").is_file()

        self.assertTrue(report["ok"], report["blockers"])
        self.assertTrue(stored)

    def test_nonblank_body_cannot_self_certify_an_empty_census(self):
        module = load("v63_visual_census")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            tiles = make_project(project)
            page = tiles["pages"]["S01"]
            census = {
                "schema_version": "6.3",
                "deconstruction_runtime_revision": "6.3.1",
                "pages": {
                    "S01": {
                        "blueprint_sha256": page["blueprint_sha256"],
                        "body_roi_px": page["body_roi_px"],
                        "reviewed_tile_ids": [item["tile_id"] for item in page["tiles"]],
                        "candidates": []
                    }
                }
            }
            report = module.validate_visual_census(project, census)

        self.assertFalse(report["ok"])
        self.assertTrue(any(item["code"] == "V63_CENSUS_EMPTY_NONBLANK" for item in report["blockers"]))

    def test_crop_and_ignore_are_limited_to_explicit_visual_classes(self):
        module = load("v63_visual_census")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            tiles = make_project(project)
            page = tiles["pages"]["S01"]
            census = {
                "schema_version": "6.3",
                "deconstruction_runtime_revision": "6.3.1",
                "pages": {
                    "S01": {
                        "blueprint_sha256": page["blueprint_sha256"],
                        "body_roi_px": page["body_roi_px"],
                        "reviewed_tile_ids": [item["tile_id"] for item in page["tiles"]],
                        "candidates": [
                            {
                                "candidate_id": "S01-C001",
                                "kind": "text",
                                "bbox_px": [120, 200, 300, 240],
                                "review_tile_ids": ["FULL", "B01"],
                                "expected_treatment": "crop",
                                "confidence": "high"
                            },
                            {
                                "candidate_id": "S01-C002",
                                "kind": "logo",
                                "bbox_px": [320, 200, 430, 250],
                                "review_tile_ids": ["FULL", "B01"],
                                "expected_treatment": "ignore",
                                "confidence": "high",
                                "ignore_reason": "small"
                            }
                        ]
                    }
                }
            }
            report = module.validate_visual_census(project, census)

        codes = {item["code"] for item in report["blockers"]}
        self.assertIn("V63_CENSUS_EDITABLE_CLASS_CROPPED", codes)
        self.assertIn("V63_CENSUS_MATERIAL_OBJECT_IGNORED", codes)


if __name__ == "__main__":
    unittest.main()
