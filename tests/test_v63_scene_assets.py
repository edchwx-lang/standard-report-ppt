from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts" / "v63_extract_scene_assets.py"
    spec = importlib.util.spec_from_file_location("v63_scene_assets_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_project(root: Path, *, framed: bool = False, subject_count: int = 1):
    (root / "blueprints").mkdir()
    (root / ".build").mkdir()
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    if framed:
        draw.rectangle((100, 100, 199, 179), fill="white", outline="black", width=4)
    else:
        draw.rectangle((100, 100, 199, 179), fill="#d71920")
    image.save(root / "blueprints" / "S01.png")
    census = {
        "pages": {
            "S01": {
                "blueprint_sha256": "unused",
                "candidates": [
                    {"candidate_id": "C1", "kind": "logo", "expected_treatment": "crop"}
                ],
            }
        }
    }
    graph = {
        "pages": {
            "S01": {
                "elements": [
                    {
                        "element_id": "E1",
                        "type": "image_crop",
                        "asset_id": "LOGO_1",
                        "bbox_px": [100, 100, 200, 180],
                        "source_px": [100, 100, 200, 180],
                        "source_candidate_ids": ["C1"],
                        "subject_count": subject_count,
                        "tight_crop": True,
                        "contains_editable_text": False,
                        "contains_native_geometry": False,
                        "intrinsic_text_only": True,
                    }
                ]
            }
        }
    }
    (root / ".build" / "v63_visual_census.json").write_text(json.dumps(census), encoding="utf-8")
    (root / ".build" / "v63_scene_graph.json").write_text(json.dumps(graph), encoding="utf-8")


class V63SceneAssetTests(unittest.TestCase):
    def test_extracts_each_scene_crop_once_and_writes_hash_ledger(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write_project(project)
            report = module.extract_scene_assets(project)
            asset = project / ".build" / "assets" / "S01" / "LOGO_1.png"
            ledger = json.loads((project / ".build" / "v63_asset_ledger.json").read_text(encoding="utf-8"))
            with Image.open(asset) as cropped:
                size = cropped.size

        self.assertTrue(report["ok"], report["blockers"])
        self.assertEqual((100, 80), size)
        self.assertEqual("LOGO_1", ledger["assets"][0]["asset_id"])
        self.assertEqual(1, ledger["assets"][0]["expected_insertions"])

    def test_rejects_non_atomic_or_framed_crop(self):
        module = load_module()
        for framed, subject_count, expected_code in (
            (False, 2, "V63_ASSET_NON_ATOMIC"),
            (True, 1, "V63_ASSET_FRAME_INCLUDED"),
        ):
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                write_project(project, framed=framed, subject_count=subject_count)
                report = module.extract_scene_assets(project)
                self.assertFalse(report["ok"])
                self.assertIn(expected_code, {item["code"] for item in report["blockers"]})


if __name__ == "__main__":
    unittest.main()
