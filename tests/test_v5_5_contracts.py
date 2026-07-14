from __future__ import annotations

import importlib.util
import json
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


def valid_brief(mode: str = "blueprint", page_count: int = 3) -> dict:
    brief = {
        "schema_version": "5.5",
        "requested_page_count": page_count,
        "page_mapping": [],
        "production_mode": mode,
        "confirmation_source": "user_explicit",
    }
    if mode == "blueprint":
        brief["blueprint_engine"] = "direct"
    return brief


class V55BootstrapTests(unittest.TestCase):
    def test_fast_mode_uses_the_common_bootstrap(self):
        direct = load_module("direct_project_v55_fast", SKILL / "scripts" / "direct_project.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "fast"
            project.mkdir()
            (project / "project_brief.json").write_text(
                json.dumps(valid_brief("fast", 15)), encoding="utf-8"
            )
            template = root / "master.pptx"
            template.write_bytes(b"master")
            generator = direct.bootstrap_project(
                project,
                template_path=template,
                generator_template=SKILL / "assets" / "direct_blueprint_generator_template.py",
            )
            source = generator.read_text(encoding="utf-8")
            self.assertIn('"schema_version": "5.5"', source)
            self.assertIn('"production_mode": "fast"', source)
            self.assertIn('"page_count": 15', source)
            self.assertFalse((project / "direct_blueprint_state.json").exists())
            self.assertFalse((project / "blueprints").exists())
            for relative in (".build", ".build/rendered/current", "output"):
                self.assertTrue((project / relative).is_dir(), relative)


class V55EvidenceContractTests(unittest.TestCase):
    def test_must_keep_evidence_must_map_to_a_real_module(self):
        direct = load_module("direct_project_v55_evidence", SKILL / "scripts" / "direct_project.py")
        slide = {
            "slide_id": "S01",
            "modules": [{"module_id": "M01"}],
            "primary_visual_module_id": "M01",
            "evidence_inventory": [
                {
                    "evidence_id": "E01",
                    "statement": "2025年市场规模达到100亿元",
                    "priority": "must_keep",
                    "module_id": None,
                }
            ],
        }
        errors = direct.validate_evidence_inventory(slide)
        self.assertTrue(any("must_keep" in error and "module" in error for error in errors), errors)

    def test_supporting_evidence_coverage_must_reach_eighty_percent(self):
        direct = load_module("direct_project_v55_coverage", SKILL / "scripts" / "direct_project.py")
        slide = {
            "slide_id": "S01",
            "modules": [{"module_id": "M01"}],
            "primary_visual_module_id": "M01",
            "evidence_inventory": [
                {"evidence_id": "E01", "statement": "结论证据1", "priority": "must_keep", "module_id": "M01"},
                {"evidence_id": "E02", "statement": "支持证据2", "priority": "supporting", "module_id": None},
                {"evidence_id": "E03", "statement": "支持证据3", "priority": "supporting", "module_id": None},
                {"evidence_id": "E04", "statement": "支持证据4", "priority": "supporting", "module_id": None},
                {"evidence_id": "E05", "statement": "支持证据5", "priority": "supporting", "module_id": None},
            ],
        }
        errors = direct.validate_evidence_inventory(slide)
        self.assertTrue(any("80%" in error for error in errors), errors)

    def test_materialized_generator_fails_before_powerpoint_when_evidence_is_unmapped(self):
        template = load_module(
            "generator_template_v55_evidence_gate",
            SKILL / "assets" / "direct_blueprint_generator_template.py",
        )
        template.DECK_META = {"page_count": 1, "production_mode": "fast"}
        template.SLIDES = [{
            "slide_id": "S01",
            "chapter": "一、测试",
            "title": "测试",
            "core_points": ["核心判断" * 20],
            "source": "资料来源：测试",
            "density_profile": "medium",
            "modules": [{"module_id": "M01"}],
            "primary_visual_module_id": "M01",
            "evidence_inventory": [{
                "evidence_id": "E01",
                "statement": "必须保留的关键证据",
                "priority": "must_keep",
                "module_id": None,
            }],
        }]
        template.PAGE_BUILDERS = {"S01": lambda *args: None}
        with self.assertRaisesRegex(ValueError, "must_keep"):
            template.validate_embedded_contract()


class V55VisualInventoryTests(unittest.TestCase):
    def test_reviewed_no_raster_requires_hash_bound_review_evidence(self):
        direct = load_module("direct_project_v55_review_evidence", SKILL / "scripts" / "direct_project.py")
        slides = [{
            "slide_id": "S01",
            "visual_review": "reviewed_no_raster",
            "visual_inventory": [],
            "complex_visuals": [],
        }]
        errors = direct.validate_visual_inventory(slides, production_mode="blueprint")
        self.assertTrue(any("visual_review_evidence" in error for error in errors), errors)

    def test_crop_disposition_cannot_be_hidden_by_empty_complex_visuals(self):
        direct = load_module("direct_project_v55_crop_disposition", SKILL / "scripts" / "direct_project.py")
        slides = [{
            "slide_id": "S01",
            "visual_review": "reviewed_no_raster",
            "visual_review_evidence": {
                "blueprint_sha256": "a" * 64,
                "full_page_reviewed": True,
                "checked_classes": ["photo", "logo", "map", "pictogram", "decorative_motif"],
                "decision_reason": "All intended marks are native shapes.",
            },
            "visual_inventory": [{
                "visual_id": "V01",
                "kind": "pictogram",
                "description": "人物图标",
                "disposition": "crop",
                "asset_id": "S01_A01",
            }],
            "complex_visuals": [],
        }]
        errors = direct.validate_visual_inventory(slides, production_mode="blueprint")
        self.assertTrue(any("crop" in error and "complex_visuals" in error for error in errors), errors)

    def test_asset_extractor_rejects_unbound_empty_review(self):
        extractor = load_module(
            "extract_direct_assets_v55_fail_closed",
            SKILL / "scripts" / "extract_direct_assets.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            generator = project / "generate_deck.py"
            generator.write_text(
                "SLIDES=[{'slide_id':'S01','visual_review':'reviewed_no_raster',"
                "'visual_inventory':[],'complex_visuals':[]}]\n"
                "BLUEPRINTS={}\nASSET_CROPS={}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "visual_review_evidence"):
                extractor.extract_direct_assets(generator, project)


class V55SkeletonAndEffectsTests(unittest.TestCase):
    def test_audit_rejects_title_core_overlap_and_any_effect(self):
        audit = load_module("ppt_skeleton_audit_v55", SKILL / "scripts" / "ppt_skeleton_audit.py")
        manifest = {
            "pages": [{
                "page": 1,
                "shapes": {
                    "SKEL_CHAPTER": {"font_name": "Microsoft YaHei", "font_size": 20, "left": 40, "top": 0.4 / 2.54 * 72, "height": 20},
                    "SKEL_TITLE": {"font_name": "Microsoft YaHei", "font_size": 16, "left": 40, "top": 1.5 / 2.54 * 72, "height": 35, "alignment": 1},
                    "SKEL_CORE": {"font_name": "Microsoft YaHei", "font_size": 12, "left": 40, "top": 2.7 / 2.54 * 72, "height": 50, "dash_style": 4, "line_weight": 1},
                    "SKEL_SOURCE": {"font_name": "Microsoft YaHei", "font_size": 7.5, "left": 40, "top": 520, "height": 10},
                    "SKEL_PAGE_NUMBER": {"font_name": "Microsoft YaHei", "font_size": 8, "left": 900, "top": 520, "height": 10},
                },
                "forbidden_top_rules": [],
                "footer_separators": [],
                "forbidden_effects": [{"shape": "Card 1", "effect": "reflection"}],
            }],
            "global_forbidden_effects": [],
        }
        result = audit.audit_manifest(manifest)
        self.assertFalse(result["ok"])
        self.assertTrue(any("gap" in error or "overlap" in error for error in result["errors"]), result)
        self.assertTrue(any("reflection" in error for error in result["errors"]), result)

    def test_generator_template_exposes_effect_cleanup_and_shared_components(self):
        template = load_module(
            "generator_template_v55_components",
            SKILL / "assets" / "direct_blueprint_generator_template.py",
        )
        for name in (
            "clear_shape_effects",
            "clear_presentation_effects",
            "add_section_header",
            "add_text_card",
            "add_metric_strip",
            "add_hbar_chart",
            "add_matrix",
        ):
            self.assertTrue(hasattr(template, name), name)


class V55DocumentationContractTests(unittest.TestCase):
    def test_skill_and_prompts_name_the_new_contracts(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        outline = (SKILL / "prompts" / "page_outline_prompt.md").read_text(encoding="utf-8")
        reconstruction = (SKILL / "prompts" / "python_reconstruction_prompt.md").read_text(encoding="utf-8")
        self.assertIn("Standard Report PPT V5.7", skill)
        self.assertIn("project_pipeline.py", skill)
        self.assertIn("evidence_inventory", outline)
        self.assertIn("80%", outline)
        self.assertIn("shared runtime", reconstruction)
        self.assertIn("逐对象", reconstruction)


if __name__ == "__main__":
    unittest.main()
