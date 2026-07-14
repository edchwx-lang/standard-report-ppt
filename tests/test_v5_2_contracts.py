from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V52SkeletonContractTests(unittest.TestCase):
    def test_composer_uses_exact_v52_vertical_positions(self):
        composer = load_module("compose_blueprint_v52", SKILL / "scripts" / "compose_blueprint.py")
        self.assertEqual(composer.CHAPTER_TOP, 19)
        self.assertEqual(composer.TITLE_TOP, 71)
        self.assertEqual(composer.CORE_TOP, 128)

        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "body.png"
            output = Path(directory) / "blueprint.png"
            Image.new("RGB", (1600, 900), "white").save(source)
            record = composer.compose_blueprint(source, output, {
                "chapter": "一、测试",
                "title": "测试标题",
                "core_points": ["核心判断用于验证V5.3垂直骨架位置。"],
                "source": "资料来源：测试",
                "page_number": 1,
            })
            self.assertEqual(record["schema_version"], "5.5")
            self.assertEqual(record["tops_px"], {"chapter": 19, "title": 71, "core": 128})

    def test_skeleton_audit_rejects_old_v51_top_positions(self):
        audit = load_module("ppt_skeleton_audit_v52", SKILL / "scripts" / "ppt_skeleton_audit.py")
        shapes = {
            "SKEL_CHAPTER": {"left": 40.0, "top": 24.0, "font_name": "Microsoft YaHei", "font_size": 20.0},
            "SKEL_TITLE": {"left": 40.0, "top": 71.0, "font_name": "Microsoft YaHei", "font_size": 16.0, "alignment": 1},
            "SKEL_CORE": {"left": 40.0, "top": 104.0, "font_name": "Microsoft YaHei", "font_size": 12.0, "dash_style": 4, "line_weight": 1.0},
            "SKEL_SOURCE": {"left": 40.0, "top": 519.0, "font_name": "Microsoft YaHei", "font_size": 7.5},
            "SKEL_PAGE_NUMBER": {"left": 880.0, "top": 519.0, "font_name": "Microsoft YaHei", "font_size": 8.0},
        }
        result = audit.audit_manifest({"pages": [{"page": 1, "shapes": shapes, "forbidden_top_rules": [], "footer_separators": []}]})
        self.assertFalse(result["ok"])
        self.assertTrue(any("top must be" in error for error in result["errors"]))


class V52SingleAssetContractTests(unittest.TestCase):
    def test_direct_contract_requires_target_box_and_contain_fit(self):
        direct = load_module("direct_project_v52", SKILL / "scripts" / "direct_project.py")
        slides = [{"slide_id": "S01", "complex_visuals": [{"asset_id": "S01_A01", "kind": "pictogram"}]}]
        legacy = {"S01_A01": {"slide_id": "S01", "source_px": [10, 10, 90, 90], "target_in": [1, 2, 1, 1]}}
        errors = direct.validate_complex_visual_assets(slides, legacy, Path("."), require_files=False)
        self.assertTrue(any("target_box_in" in error for error in errors))

    def test_extractor_exposes_single_object_analysis(self):
        extractor_path = SKILL / "scripts" / "extract_direct_assets.py"
        self.assertTrue(extractor_path.is_file(), "V5.3 Direct asset extractor is missing")
        extractor = load_module("extract_direct_assets_v52", extractor_path)
        self.assertTrue(hasattr(extractor, "analyze_single_object_crop"))

    def test_single_object_analysis_rejects_grouped_and_rule_polluted_crops(self):
        extractor_path = SKILL / "scripts" / "extract_direct_assets.py"
        self.assertTrue(extractor_path.is_file(), "V5.3 Direct asset extractor is missing")
        extractor = load_module("extract_direct_assets_analysis", extractor_path)
        from PIL import Image, ImageDraw

        single = Image.new("RGB", (220, 140), "white")
        ImageDraw.Draw(single).ellipse((70, 25, 150, 115), fill="#1E386B")
        self.assertTrue(extractor.analyze_single_object_crop(single, kind="pictogram")["valid"])

        grouped = Image.new("RGB", (360, 120), "white")
        draw = ImageDraw.Draw(grouped)
        for left in (20, 140, 260):
            draw.ellipse((left, 20, left + 80, 100), fill="#1E386B")
        grouped_result = extractor.analyze_single_object_crop(grouped, kind="pictogram")
        self.assertFalse(grouped_result["valid"])
        self.assertIn("multiple_macro_objects", grouped_result["errors"])

        polluted = Image.new("RGB", (300, 160), "white")
        draw = ImageDraw.Draw(polluted)
        draw.rectangle((5, 5, 295, 15), fill="#1E386B")
        draw.ellipse((110, 45, 190, 125), fill="#1E386B")
        polluted_result = extractor.analyze_single_object_crop(polluted, kind="pictogram")
        self.assertFalse(polluted_result["valid"])
        self.assertIn("long_rule_contamination", polluted_result["errors"])

        tight_round_mark = Image.new("RGB", (100, 100), "white")
        ImageDraw.Draw(tight_round_mark).ellipse((2, 2, 97, 97), fill="#1E386B")
        self.assertTrue(
            extractor.analyze_single_object_crop(tight_round_mark, kind="pictogram")["valid"],
            "a tight round icon must not be mistaken for a thin horizontal rule",
        )

    def test_contain_rect_preserves_aspect_ratio(self):
        extractor_path = SKILL / "scripts" / "extract_direct_assets.py"
        self.assertTrue(extractor_path.is_file(), "V5.3 Direct asset extractor is missing")
        extractor = load_module("extract_direct_assets_contain", extractor_path)
        x, y, width, height = extractor.contain_rect((400, 200), [2.0, 3.0, 3.0, 3.0])
        self.assertAlmostEqual(width / height, 2.0, places=6)
        self.assertGreaterEqual(x, 2.0)
        self.assertGreaterEqual(y, 3.0)
        self.assertLessEqual(x + width, 5.0)
        self.assertLessEqual(y + height, 6.0)

    def test_generator_template_uses_aspect_preserving_target_box(self):
        source = (SKILL / "assets" / "direct_blueprint_generator_template.py").read_text(encoding="utf-8")
        self.assertIn("target_box_in", source)
        self.assertIn("contain_rect", source)
        self.assertIn('shape.Name = f"ASSET_{asset_id}"', source)

    def test_asset_audit_rejects_aspect_drift_and_target_miss(self):
        audit_path = SKILL / "scripts" / "ppt_asset_audit.py"
        self.assertTrue(audit_path.is_file(), "V5.3 PPT asset auditor is missing")
        audit = load_module("ppt_asset_audit_v52", audit_path)
        crops = {"S01_A01": {"slide_id": "S01", "target_box_in": [2.0, 3.0, 2.0, 1.5]}}
        report = {"assets": [{"asset_id": "S01_A01", "aspect_ratio": 2.0}]}
        good_manifest = {"pages": [{"slide_id": "S01", "assets": {
            "S01_A01": [{"left": 144.0, "top": 234.0, "width": 144.0, "height": 72.0}]
        }, "core_bottom": 180.0, "footer_top": 519.0}]}
        self.assertTrue(audit.audit_manifest(good_manifest, crops, report)["ok"])

        bad_manifest = {"pages": [{"slide_id": "S01", "assets": {
            "S01_A01": [{"left": 40.0, "top": 150.0, "width": 144.0, "height": 144.0}]
        }, "core_bottom": 180.0, "footer_top": 519.0}]}
        result = audit.audit_manifest(bad_manifest, crops, report)
        self.assertFalse(result["ok"])
        self.assertTrue(any("aspect ratio" in error for error in result["errors"]))
        self.assertTrue(any("target box" in error or "body" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
