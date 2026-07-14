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


class BlueprintCompositionTests(unittest.TestCase):
    def test_composer_rejects_non_widescreen_source(self):
        composer = load_module("compose_blueprint_ratio", SKILL / "scripts" / "compose_blueprint.py")
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "square.png"
            Image.new("RGB", (900, 900), "white").save(source)
            with self.assertRaisesRegex(ValueError, "16:9"):
                composer.compose_blueprint(source, Path(directory) / "out.png", {
                    "chapter": "章节", "title": "标题", "core_points": ["判断"], "source": "来源", "page_number": 1
                })

    def test_composed_blueprint_uses_fixed_skeleton_without_top_rule(self):
        module_path = SKILL / "scripts" / "compose_blueprint.py"
        self.assertTrue(module_path.is_file(), "V5.1 blueprint composer is missing")
        composer = load_module("compose_blueprint", module_path)

        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "body.png"
            output = Path(directory) / "blueprint.png"
            Image.new("RGB", (1600, 900), "#EFEFEF").save(source)
            record = composer.compose_blueprint(
                source,
                output,
                {
                    "chapter": "一、行业机会",
                    "title": "本页标题",
                    "core_points": ["核心判断用于验证确定性骨架。"],
                    "source": "资料来源：测试",
                    "page_number": 1,
                },
            )
            image = Image.open(output).convert("RGB")
            self.assertEqual(image.size, (1600, 900))
            self.assertEqual(record["anchors"]["chapter_left"], record["anchors"]["title_left"])
            self.assertEqual(record["anchors"]["title_left"], record["anchors"]["core_left"])
            self.assertFalse(composer.has_forbidden_top_rule(image))
            self.assertTrue(output.with_suffix(".composition.json").is_file())
            self.assertEqual(record["output_sha256"], composer.sha256_file(output))


class AssetCompletenessTests(unittest.TestCase):
    def test_complex_visual_requires_crop_record_and_file(self):
        direct = load_module("direct_project", SKILL / "scripts" / "direct_project.py")
        self.assertTrue(hasattr(direct, "validate_complex_visual_assets"), "V5.1 asset validator is missing")
        slides = [{"slide_id": "S01", "complex_visuals": [{"asset_id": "S01_A01", "kind": "pictogram"}]}]
        errors = direct.validate_complex_visual_assets(slides, {}, Path("."), require_files=False)
        self.assertTrue(any("S01_A01" in error for error in errors))

    def test_complex_visual_passes_with_bounded_crop(self):
        direct = load_module("direct_project_pass", SKILL / "scripts" / "direct_project.py")
        self.assertTrue(hasattr(direct, "validate_complex_visual_assets"), "V5.1 asset validator is missing")
        slides = [{"slide_id": "S01", "complex_visuals": [{"asset_id": "S01_A01", "kind": "pictogram"}]}]
        crops = {"S01_A01": {"slide_id": "S01", "source_px": [10, 10, 90, 90], "target_box_in": [1, 2, 1, 1], "fit_mode": "contain", "padding_px": 4}}
        self.assertEqual(direct.validate_complex_visual_assets(slides, crops, Path("."), require_files=False), [])

    def test_page_builder_must_use_declared_asset_id(self):
        direct = load_module("direct_project_usage", SKILL / "scripts" / "direct_project.py")
        self.assertTrue(hasattr(direct, "validate_complex_visual_builder_usage"))
        slides = [{"slide_id": "S01", "complex_visuals": [{"asset_id": "S01_A01", "kind": "pictogram"}]}]
        source = "def build_slide_S01(presentation, slide, spec, body, project_dir):\n    slide.Shapes.AddShape(1, 0, 0, 10, 10)\n"
        errors = direct.validate_complex_visual_builder_usage(source, slides)
        self.assertTrue(any("S01_A01" in error for error in errors))

    def test_page_builder_usage_passes_with_add_blueprint_asset(self):
        direct = load_module("direct_project_usage_pass", SKILL / "scripts" / "direct_project.py")
        self.assertTrue(hasattr(direct, "validate_complex_visual_builder_usage"))
        slides = [{"slide_id": "S01", "complex_visuals": [{"asset_id": "S01_A01", "kind": "pictogram"}]}]
        source = "def build_slide_S01(presentation, slide, spec, body, project_dir):\n    add_blueprint_asset(slide, project_dir, 'S01', 'S01_A01')\n"
        self.assertEqual(direct.validate_complex_visual_builder_usage(source, slides), [])


class SkeletonAuditTests(unittest.TestCase):
    def test_manifest_rejects_anchor_drift_and_top_rule(self):
        module_path = SKILL / "scripts" / "ppt_skeleton_audit.py"
        self.assertTrue(module_path.is_file(), "V5.1 PPT skeleton auditor is missing")
        audit = load_module("ppt_skeleton_audit", module_path)
        manifest = {
            "pages": [{
                "page": 1,
                "shapes": {
                    "SKEL_CHAPTER": {"left": 40.0, "top": 24.0, "font_name": "Microsoft YaHei", "font_size": 20.0},
                    "SKEL_TITLE": {"left": 44.0, "top": 71.0, "font_name": "Microsoft YaHei", "font_size": 16.0, "alignment": 1},
                    "SKEL_CORE": {"left": 40.0, "top": 104.0, "font_name": "Microsoft YaHei", "font_size": 12.0, "dash_style": 4, "line_weight": 1.0},
                    "SKEL_SOURCE": {"left": 40.0, "top": 519.0, "font_name": "Microsoft YaHei", "font_size": 7.5},
                    "SKEL_PAGE_NUMBER": {"left": 880.0, "top": 519.0, "font_name": "Microsoft YaHei", "font_size": 8.0},
                },
                "forbidden_top_rules": [{"left": 0, "top": 61, "width": 960, "height": 5, "color": "#1E386B"}],
                "footer_separators": [],
            }]
        }
        result = audit.audit_manifest(manifest)
        self.assertFalse(result["ok"])
        self.assertTrue(any("left anchor" in error for error in result["errors"]))
        self.assertTrue(any("top rule" in error for error in result["errors"]))

    def test_valid_manifest_passes(self):
        audit = load_module("ppt_skeleton_audit_pass", SKILL / "scripts" / "ppt_skeleton_audit.py")
        shapes = {
            "SKEL_CHAPTER": {"left": 40.0, "top": 0.4 / 2.54 * 72.0, "font_name": "Microsoft YaHei", "font_size": 20.0},
            "SKEL_TITLE": {"left": 40.0, "top": 1.5 / 2.54 * 72.0, "font_name": "Microsoft YaHei", "font_size": 16.0, "alignment": 1},
            "SKEL_CORE": {"left": 40.0, "top": 2.7 / 2.54 * 72.0, "font_name": "Microsoft YaHei", "font_size": 12.0, "dash_style": 4, "line_weight": 1.0},
            "SKEL_SOURCE": {"left": 40.0, "top": 519.0, "font_name": "Microsoft YaHei", "font_size": 7.5},
            "SKEL_PAGE_NUMBER": {"left": 880.0, "top": 519.0, "font_name": "Microsoft YaHei", "font_size": 8.0},
        }
        result = audit.audit_manifest({"pages": [{"page": 1, "shapes": shapes, "forbidden_top_rules": [], "footer_separators": []}]})
        self.assertTrue(result["ok"], result["errors"])


class WorkflowIntegrationTests(unittest.TestCase):
    def test_generator_template_names_skeleton_shapes_and_disables_master_artifacts(self):
        source = (SKILL / "assets" / "direct_blueprint_generator_template.py").read_text(encoding="utf-8")
        for name in ("SKEL_CHAPTER", "SKEL_TITLE", "SKEL_CORE", "SKEL_SOURCE", "SKEL_PAGE_NUMBER"):
            self.assertIn(name, source)
        self.assertNotIn("SKEL_TOP_MASK", source)
        self.assertIn("FollowMasterBackground = 0", source)
        self.assertNotIn("PAGE_BUILDERS = {}", source)
        self.assertIn("__COMPANY_TEMPLATE_PATH__", source)
        self.assertIn("__COMPANY_TEMPLATE_SHA256__", source)

    def test_final_validator_requires_skeleton_audit_artifact(self):
        source = (SKILL / "scripts" / "direct_project.py").read_text(encoding="utf-8")
        self.assertIn("ppt_skeleton_audit.json", source)
        self.assertIn("ppt_asset_audit.json", source)
        self.assertIn("direct_asset_report.json", source)
        self.assertIn("skeleton audit", source.lower())
        self.assertIn("composition.json", source)

    def test_skill_declares_current_version_and_blueprint_composition(self):
        source = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("V5.5", source)
        self.assertIn("compose_blueprint.py", source)

    def test_reference_contract_separates_blueprint_geometry_from_python_typography(self):
        visual = (SKILL / "references" / "company_visual_system.md").read_text(encoding="utf-8")
        layout = (SKILL / "references" / "layout_and_chart_rules.md").read_text(encoding="utf-8")
        python_rules = (SKILL / "references" / "python_reconstruction_rules.md").read_text(encoding="utf-8")
        self.assertIn("0.64 cm", visual)
        self.assertIn("narrative", visual.lower())
        self.assertIn("0.02 inches", layout)
        self.assertIn("no decorative", layout.lower())
        self.assertIn("SKEL_CHAPTER", python_rules)

    def test_prompts_require_composition_asset_retention_and_skeleton_audit(self):
        blueprint = (SKILL / "prompts" / "imagegen_blueprint_prompt.md").read_text(encoding="utf-8")
        reconstruction = (SKILL / "prompts" / "python_reconstruction_prompt.md").read_text(encoding="utf-8")
        quality = (SKILL / "references" / "ppt_quality_check_rules.md").read_text(encoding="utf-8")
        self.assertIn("compose_blueprint.py", blueprint)
        self.assertIn("complex_visuals", blueprint)
        self.assertIn("add_blueprint_asset", reconstruction)
        self.assertIn("extract_direct_assets.py", reconstruction)
        self.assertIn("target_box_in", reconstruction)
        self.assertIn("ppt_skeleton_audit.py", quality)
        self.assertIn("ppt_asset_audit.py", quality)


if __name__ == "__main__":
    unittest.main()
