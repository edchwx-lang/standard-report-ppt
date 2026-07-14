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


class _Shape:
    def __init__(self, left, top, width, height):
        self.Left, self.Top, self.Width, self.Height = left, top, width, height
        self.deleted = False

    def Delete(self):
        self.deleted = True


class _Shapes:
    def __init__(self, shapes):
        self.items = shapes

    @property
    def Count(self):
        return len(self.items)

    def __call__(self, index):
        return self.items[index - 1]


class _Layouts:
    def __init__(self, layouts):
        self.items = layouts

    @property
    def Count(self):
        return len(self.items)

    def __call__(self, index):
        return self.items[index - 1]


class _Designs(_Layouts):
    pass


class V53PasteboardTests(unittest.TestCase):
    def test_template_sanitizes_slide_master_and_layout_pasteboards(self):
        template = load_module("generator_template_v53", SKILL / "assets" / "direct_blueprint_generator_template.py")
        self.assertTrue(hasattr(template, "sanitize_presentation_pasteboard"))

        on_slide = _Shape(10, 10, 100, 100)
        off_slide = _Shape(-100, 10, 50, 50)
        master_off = _Shape(1000, 10, 40, 40)
        layout_off = _Shape(20, 600, 40, 40)
        slide = type("Slide", (), {"Shapes": _Shapes([on_slide, off_slide])})()
        layout = type("Layout", (), {"Shapes": _Shapes([layout_off])})()
        master = type("Master", (), {"Shapes": _Shapes([master_off]), "CustomLayouts": _Layouts([layout])})()
        design = type("Design", (), {"SlideMaster": master})()
        presentation = type(
            "Presentation",
            (),
            {
                "PageSetup": type("PageSetup", (), {"SlideWidth": 960.0, "SlideHeight": 540.0})(),
                "Slides": _Layouts([slide]),
                "Designs": _Designs([design]),
            },
        )()

        report = template.sanitize_presentation_pasteboard(presentation)
        self.assertFalse(on_slide.deleted)
        self.assertTrue(off_slide.deleted)
        self.assertTrue(master_off.deleted)
        self.assertTrue(layout_off.deleted)
        self.assertEqual(report["deleted"], 3)
        source = (SKILL / "assets" / "direct_blueprint_generator_template.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("sanitize_presentation_pasteboard(presentation)"), 2)


class V53VisualInventoryTests(unittest.TestCase):
    def test_single_object_globe_line_is_not_rule_contamination(self):
        extractor = load_module("extract_direct_assets_v53_globe", SKILL / "scripts" / "extract_direct_assets.py")
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (90, 90), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((5, 5, 85, 85), outline="#1E386B", width=8)
        draw.line((5, 45, 85, 45), fill="#1E386B", width=4)
        result = extractor.analyze_single_object_crop(image, kind="compound_mark")
        self.assertTrue(result["valid"], result)

    def test_blueprint_requires_explicit_visual_review_state(self):
        direct = load_module("direct_project_v53_inventory", SKILL / "scripts" / "direct_project.py")
        missing = [{"slide_id": "S01", "complex_visuals": []}]
        errors = direct.validate_visual_inventory(missing, production_mode="blueprint")
        self.assertTrue(any("visual_review" in error for error in errors))

    def test_extract_declared_review_cannot_have_empty_inventory(self):
        direct = load_module("direct_project_v53_extract_declared", SKILL / "scripts" / "direct_project.py")
        slides = [{"slide_id": "S01", "visual_review": "extract_declared", "complex_visuals": []}]
        errors = direct.validate_visual_inventory(slides, production_mode="blueprint")
        self.assertTrue(any("at least one" in error for error in errors))

    def test_reviewed_no_raster_requires_empty_inventory(self):
        direct = load_module("direct_project_v53_no_raster", SKILL / "scripts" / "direct_project.py")
        slides = [{
            "slide_id": "S01",
            "visual_review": "reviewed_no_raster",
            "complex_visuals": [{"asset_id": "S01_A01", "kind": "pictogram", "description": "globe"}],
        }]
        errors = direct.validate_visual_inventory(slides, production_mode="blueprint")
        self.assertTrue(any("must be empty" in error for error in errors))

    def test_asset_audit_reports_declared_and_inserted_counts(self):
        audit = load_module("ppt_asset_audit_v53_counts", SKILL / "scripts" / "ppt_asset_audit.py")
        manifest = {"pages": [{"slide_id": "S01", "assets": {"S01_A01": [{"left": 72, "top": 216, "width": 72, "height": 72}]}, "core_bottom": 180, "footer_top": 510}]}
        crops = {"S01_A01": {"slide_id": "S01", "target_box_in": [1, 3, 1, 1]}}
        report = {"assets": [{"asset_id": "S01_A01", "aspect_ratio": 1.0}]}
        result = audit.audit_manifest(manifest, crops, report)
        self.assertEqual(result["declared_assets"], 1)
        self.assertEqual(result["inserted_assets"], 1)
        self.assertTrue(result["complete_inventory"])

    def test_extractor_rejects_declared_visual_without_crop(self):
        extractor = load_module("extract_direct_assets_v53_inventory", SKILL / "scripts" / "extract_direct_assets.py")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            generator = project / "generate_deck.py"
            generator.write_text(
                "SLIDES=[{'slide_id':'S01','visual_review':'extract_declared',"
                "'visual_review_evidence':{'blueprint_sha256':'" + "a" * 64 + "','full_page_reviewed':True,"
                "'checked_classes':['photo','logo','map','pictogram','decorative_motif'],"
                "'decision_reason':'one pictogram'},"
                "'visual_inventory':[{'visual_id':'V01','kind':'pictogram','description':'globe',"
                "'disposition':'crop','asset_id':'S01_A01'}],'complex_visuals':["
                "{'asset_id':'S01_A01','kind':'pictogram','description':'globe'}]}]\n"
                "BLUEPRINTS={}\nASSET_CROPS={}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing from ASSET_CROPS"):
                extractor.extract_direct_assets(generator, project)
            report = (project / ".build" / "direct_asset_report.json").read_text(encoding="utf-8")
            self.assertIn('"declared_assets": 1', report)
            self.assertIn('"extracted_assets": 0', report)


class V53CompleteBlueprintTests(unittest.TestCase):
    def test_composition_marks_complete_slide_reference(self):
        composer = load_module("compose_blueprint_v53_complete", SKILL / "scripts" / "compose_blueprint.py")
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "raw.png"
            output = Path(directory) / "blueprint.png"
            Image.new("RGB", (1600, 900), "white").save(source)
            record = composer.compose_blueprint(source, output, {
                "chapter": "一、测试",
                "title": "完整蓝图",
                "core_points": ["核心判断用于验证完整蓝图的三层骨架与正文参考。"],
                "source": "资料来源：测试",
                "page_number": 1,
            })
            self.assertEqual(record["schema_version"], "5.5")
            self.assertTrue(record["complete_slide_reference"])
            self.assertEqual(record["raw_input_role"], "complete_slide_draft")

    def test_imagegen_prompt_requests_complete_top_skeleton(self):
        prompt = (SKILL / "prompts" / "imagegen_blueprint_prompt.md").read_text(encoding="utf-8")
        self.assertIn("完整页面", prompt)
        self.assertIn("章节标题", prompt)
        self.assertIn("本页标题", prompt)
        self.assertIn("核心判断", prompt)
        self.assertNotIn("body-composition image", prompt)
        self.assertNotIn("预留约27%", prompt)


if __name__ == "__main__":
    unittest.main()
