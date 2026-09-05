from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts" / "v63_visual_tiles.py"
    spec = importlib.util.spec_from_file_location("v63_visual_tiles_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V63VisualTileTests(unittest.TestCase):
    def test_default_grid_covers_body_with_overlapping_neighbors(self):
        boxes = load_module().overlapping_tile_boxes([60, 150, 1080, 450])

        self.assertEqual(6, len(boxes))
        self.assertEqual([60, 150], boxes[0][0:2])
        self.assertEqual([1140, 600], boxes[-1][2:4])
        self.assertGreater(boxes[0][2], boxes[1][0])
        self.assertGreater(boxes[0][3], boxes[3][1])

    def test_generation_writes_full_body_and_six_hash_bound_tiles(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "blueprints").mkdir()
            Image.new("RGB", (1200, 675), "white").save(
                project / "blueprints" / "S01.png"
            )
            manifest = module.generate_review_tiles(
                project,
                template_path=ROOT / "assets" / "company_template.pptx",
                legacy_template_roi=True,
            )

            page = manifest["pages"]["S01"]
            files = [project / item["path"] for item in page["tiles"]]
            stored = json.loads(
                (project / ".build" / "v63_visual_review_tiles.json").read_text(
                    encoding="utf-8"
                )
            )
            files_exist = all(path.is_file() for path in files)

        self.assertEqual("6.3", manifest["schema_version"])
        self.assertEqual("6.3.1", manifest["deconstruction_runtime_revision"])
        self.assertEqual(["FULL", "B01", "B02", "B03", "B04", "B05", "B06"], [item["tile_id"] for item in page["tiles"]])
        self.assertTrue(files_exist)
        self.assertEqual(manifest, stored)


if __name__ == "__main__":
    unittest.main()
