from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V6BitmapTests(unittest.TestCase):
    def setUp(self):
        self.bitmap = load_module("v6_bitmap", ROOT / "scripts" / "v6_bitmap.py")

    def write_blueprint(self, project: Path, slide_id: str = "S01") -> Path:
        destination = project / "blueprints" / f"{slide_id}.png"
        destination.parent.mkdir()
        Image.new("RGB", (200, 100), "navy").save(destination)
        return destination

    def alignment(self, review: dict, slide_id: str = "S01") -> dict:
        return {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "construction_mode": "bitmap",
            "pages": {
                slide_id: {
                    "reviewed_full_page": True,
                    "blueprint_sha256": review["pages"][slide_id]["blueprint_sha256"],
                    "source_px": [10, 20, 190, 90],
                    "excluded_skeleton_regions": list(
                        self.bitmap.EXCLUDED_SKELETON_REGIONS
                    ),
                }
            },
        }

    def test_prepare_review_binds_full_pages_without_quadrant_tiles(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_blueprint(project)
            review = self.bitmap.prepare_bitmap_review(project)
            self.assertEqual([200, 100], review["pages"]["S01"]["pixel_size"])
            self.assertEqual(
                "blueprints/S01.png", review["pages"]["S01"]["blueprint_path"]
            )
            self.assertTrue((project / ".build" / "bitmap_review.json").is_file())
            self.assertFalse((project / ".build" / "visual_review_tiles").exists())
            self.assertNotIn("tiles", review["pages"]["S01"])

    def test_alignment_requires_a_fresh_full_page_review_and_exact_skeleton_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_blueprint(project)
            review = self.bitmap.prepare_bitmap_review(project)
            payload = self.alignment(review)
            self.assertEqual([], self.bitmap.validate_bitmap_alignment(project, payload))
            payload["pages"]["S01"]["reviewed_full_page"] = False
            payload["pages"]["S01"]["excluded_skeleton_regions"] = []
            errors = self.bitmap.validate_bitmap_alignment(project, payload)
            self.assertIn(self.bitmap.ERROR_REVIEW_REQUIRED, errors)
            self.assertIn(self.bitmap.ERROR_EXCLUDED_REGIONS, errors)

    def test_alignment_requires_exact_v6_bitmap_metadata_and_source_px_field(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_blueprint(project)
            review = self.bitmap.prepare_bitmap_review(project)
            payload = self.alignment(review)
            self.assertEqual([], self.bitmap.validate_bitmap_alignment(project, payload))
            payload["schema_version"] = "6"
            payload["pipeline_revision"] = "6.0"
            payload["construction_mode"] = "Bitmap"
            payload["pages"]["S01"]["body_crop_px"] = payload["pages"]["S01"].pop(
                "source_px"
            )
            errors = self.bitmap.validate_bitmap_alignment(project, payload)
            self.assertIn(self.bitmap.ERROR_ALIGNMENT_SCHEMA_VERSION, errors)
            self.assertIn(self.bitmap.ERROR_ALIGNMENT_PIPELINE_REVISION, errors)
            self.assertIn(self.bitmap.ERROR_ALIGNMENT_CONSTRUCTION_MODE, errors)
            self.assertIn(self.bitmap.ERROR_CROP_BOUNDS, errors)

    def test_alignment_rejects_wrong_case_excluded_region_names(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_blueprint(project)
            review = self.bitmap.prepare_bitmap_review(project)
            payload = self.alignment(review)
            payload["pages"]["S01"]["excluded_skeleton_regions"][0] = "Chapter"
            self.assertIn(
                self.bitmap.ERROR_EXCLUDED_REGIONS,
                self.bitmap.validate_bitmap_alignment(project, payload),
            )

    def test_alignment_rejects_stale_hash_and_invalid_crop_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_blueprint(project)
            review = self.bitmap.prepare_bitmap_review(project)
            payload = self.alignment(review)
            payload["pages"]["S01"]["blueprint_sha256"] = "0" * 64
            payload["pages"]["S01"]["source_px"] = [0, 0, 200, 100]
            errors = self.bitmap.validate_bitmap_alignment(project, payload)
            self.assertIn(self.bitmap.ERROR_BLUEPRINT_HASH, errors)
            self.assertIn(self.bitmap.ERROR_FULL_IMAGE_CROP, errors)

    def test_materialize_writes_single_bitmap_asset_and_runtime_spec_per_page(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_blueprint(project)
            review = self.bitmap.prepare_bitmap_review(project)
            alignment = self.alignment(review)
            destination = project / ".build" / "bitmap_alignment.json"
            destination.write_text(json.dumps(alignment), encoding="utf-8")
            contract = self.bitmap.materialize_bitmap_assets(project)
            page = contract["pages"]["S01"]
            asset = project / page["asset_path"]
            self.assertTrue(asset.is_file())
            self.assertEqual([10, 20, 190, 90], page["source_px"])
            self.assertEqual("contain", page["fit"])
            self.assertEqual("runtime_body_box", page["target"])
            self.assertEqual("bitmap", contract["construction_mode"])
            with Image.open(asset) as image:
                self.assertEqual((180, 70), image.size)
            specs = json.loads(
                (project / ".build" / "bitmap_page_specs.json").read_text(
                    encoding="utf-8"
                )
            )
            elements = specs["S01"]["elements"]
            self.assertEqual(1, len(elements))
            self.assertEqual("body_asset", elements[0]["type"])
            self.assertNotIn("box", elements[0])

    def test_materialize_refuses_missing_review_record(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.write_blueprint(project)
            review = self.bitmap.prepare_bitmap_review(project)
            alignment = self.alignment(review)
            (project / ".build" / "bitmap_alignment.json").write_text(
                json.dumps(alignment), encoding="utf-8"
            )
            (project / ".build" / "bitmap_review.json").unlink()
            with self.assertRaisesRegex(ValueError, self.bitmap.ERROR_REVIEW_RECORD):
                self.bitmap.materialize_bitmap_assets(project)

    def test_materialize_refuses_a_review_stale_after_the_locked_blueprint_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            blueprint = self.write_blueprint(project)
            review = self.bitmap.prepare_bitmap_review(project)
            alignment = self.alignment(review)
            (project / ".build" / "bitmap_alignment.json").write_text(
                json.dumps(alignment), encoding="utf-8"
            )
            Image.new("RGB", (200, 100), "red").save(blueprint)
            with self.assertRaisesRegex(ValueError, self.bitmap.ERROR_REVIEW_STALE):
                self.bitmap.materialize_bitmap_assets(project)


if __name__ == "__main__":
    unittest.main()
