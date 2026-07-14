from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V56TextIntegrityTests(unittest.TestCase):
    def test_source_scan_rejects_question_mark_runs_but_allows_real_question(self):
        contracts = load_module("v56_contracts_text", SKILL / "scripts" / "v56_contracts.py")
        self.assertTrue(contracts.scan_text_integrity("模块?????????", location="source"))
        self.assertEqual([], contracts.scan_text_integrity("为什么？", location="source"))

    def test_pptx_xml_scan_rejects_question_mark_runs(self):
        audit = load_module("v56_ppt_text_audit", SKILL / "scripts" / "ppt_text_audit.py")
        with tempfile.TemporaryDirectory() as directory:
            pptx = Path(directory) / "bad.pptx"
            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr(
                    "ppt/slides/slide1.xml",
                    "<a:t xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'>?????????</a:t>",
                )
            result = audit.audit_pptx_text(pptx)
        self.assertFalse(result["ok"])
        self.assertTrue(any("question_mark_run" in error for error in result["errors"]), result)


class V56VisualManifestTests(unittest.TestCase):
    def test_pictogram_cannot_be_declared_native_rebuild(self):
        contracts = load_module("v56_contracts_visual", SKILL / "scripts" / "v56_contracts.py")
        manifest = {
            "schema_version": "5.6",
            "pages": {
                "S01": {
                    "blueprint_sha256": "a" * 64,
                    "candidate_count": 1,
                    "visuals": [{
                        "visual_id": "V01",
                        "kind": "pictogram",
                        "description": "机械臂",
                        "disposition": "native_rebuild",
                        "rebuild_recipe": "circle + text",
                    }],
                }
            },
        }
        errors = contracts.validate_visual_manifest(manifest)
        self.assertTrue(any("must use crop" in error for error in errors), errors)

    def test_zero_asset_review_fails_when_candidates_exist(self):
        contracts = load_module("v56_contracts_zero_asset", SKILL / "scripts" / "v56_contracts.py")
        manifest = {
            "schema_version": "5.6",
            "pages": {
                "S01": {
                    "blueprint_sha256": "a" * 64,
                    "candidate_count": 2,
                    "visuals": [],
                }
            },
        }
        errors = contracts.validate_visual_manifest(manifest)
        self.assertTrue(any("candidate_count" in error for error in errors), errors)


class V56IncrementalCacheTests(unittest.TestCase):
    def test_changing_s02_does_not_invalidate_s01(self):
        cache = load_module("v56_page_cache", SKILL / "scripts" / "v56_page_cache.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            s01 = root / "S01.json"
            s02 = root / "S02.json"
            out01 = root / "S01.png"
            out02 = root / "S02.png"
            s01.write_text('{"title":"one"}', encoding="utf-8")
            s02.write_text('{"title":"two"}', encoding="utf-8")
            out01.write_bytes(b"one")
            out02.write_bytes(b"two")
            cache.update_page_cache(state, "S01", [s01], [out01], salt="runtime-1")
            cache.update_page_cache(state, "S02", [s02], [out02], salt="runtime-1")
            s02.write_text('{"title":"two changed"}', encoding="utf-8")
            self.assertTrue(cache.page_cache_hit(state, "S01", [s01], [out01], salt="runtime-1"))
            self.assertFalse(cache.page_cache_hit(state, "S02", [s02], [out02], salt="runtime-1"))


class V56CompilerTests(unittest.TestCase):
    def test_compiler_emits_page_specific_wrappers_from_utf8_manifests(self):
        compiler = load_module("v56_compiler", SKILL / "scripts" / "project_compiler.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.py"
            template.write_text(
                'DECK_META={"schema_version":"__PROJECT_SCHEMA_VERSION__","production_mode":"__PRODUCTION_MODE__","page_count":0,  # __PAGE_COUNT__\n"template_path":"__COMPANY_TEMPLATE_PATH__","template_sha256":"__COMPANY_TEMPLATE_SHA256__"}\n'
                'SLIDES = []\nBLUEPRINTS = {}\nASSET_CROPS = {}\nPAGE_SPECS = {}\n# __PAGE_BUILDERS__\n',
                encoding="utf-8",
            )
            master = root / "master.pptx"
            master.write_bytes(b"master")
            brief = {"schema_version": "5.6", "requested_page_count": 1, "production_mode": "fast"}
            slides = [{"slide_id": "S01", "chapter": "一、测试", "title": "中文标题", "core_points": ["核心判断" * 12], "source": "资料来源：测试", "density_profile": "medium", "modules": [{"module_id": "M01"}], "primary_visual_module_id": "M01", "evidence_inventory": [{"evidence_id": "E01", "statement": "证据", "priority": "must_keep", "module_id": "M01"}]}]
            page_specs = {"S01": {"elements": []}}
            source = compiler.compile_generator_source(
                template.read_text(encoding="utf-8"), brief, slides, page_specs, {}, {}, master
            )
        self.assertIn("def build_slide_S01", source)
        self.assertIn("中文标题", source)
        self.assertNotIn("???", source)


class V56PipelineTests(unittest.TestCase):
    def test_skill_starts_after_two_gates_without_standalone_preflight_step(self):
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("--preflight", skill_text)
        self.assertIn("begin production immediately", skill_text)

    def test_blueprint_guidance_uses_small_accents_without_forcing_hero_images(self):
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        prompt_text = (SKILL / "prompts" / "imagegen_blueprint_prompt.md").read_text(encoding="utf-8")
        layout_text = (SKILL / "references" / "layout_and_chart_rules.md").read_text(encoding="utf-8")
        primary_phrase = "Keep charts, tables, matrices, and flows as the primary evidence-bearing body."
        accent_phrase = "Use small pictograms, supplied logos, flags, or bounded schematic accents"
        for text in (skill_text, prompt_text, layout_text):
            self.assertIn(primary_phrase, text)
            self.assertIn(accent_phrase, text)
        self.assertIn("supporting accents rather than large hero images", skill_text)
        self.assertIn("does not require a photo, map, logo, device, or product image", skill_text)
        self.assertNotIn("at least one relevant complex raster subject", skill_text)
        self.assertNotIn("meaningful body region rather than a token icon", prompt_text)

    def test_init_creates_manifest_workspace_without_manual_state_machine(self):
        pipeline = load_module("v56_pipeline", SKILL / "scripts" / "project_pipeline.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project_brief.json").write_text(
                json.dumps({"schema_version": "5.6", "requested_page_count": 3, "production_mode": "blueprint", "blueprint_engine": "direct", "confirmation_source": "user_explicit"}),
                encoding="utf-8",
            )
            result = pipeline.init_project(root)
            self.assertTrue((root / ".build" / "pages").is_dir())
            self.assertTrue((root / ".build" / "pipeline_timing.json").is_file())
            self.assertFalse((root / "direct_blueprint_state.json").exists())
            self.assertEqual("5.6", result["schema_version"])


if __name__ == "__main__":
    unittest.main()
