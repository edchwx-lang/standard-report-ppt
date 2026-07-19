from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V582QualityPolicyTests(unittest.TestCase):
    def _quality(self):
        path = SKILL / "scripts" / "v582_quality.py"
        self.assertTrue(path.is_file(), "V5.8.2 quality policy module is missing")
        return load_module("v582_quality", path)

    def test_quality_report_separates_blockers_from_warnings(self):
        quality = self._quality()
        payload = quality.summarize(
            [quality.issue("BLUEPRINT_TEXT_MISMATCH", "warning", "blueprint", "typo", "S01")],
            [quality.issue("PPTX_PAGE_COUNT", "blocker", "delivery", "wrong count")],
        )
        self.assertEqual("blocked", payload["status"])
        self.assertEqual(1, payload["warning_count"])
        self.assertEqual(1, payload["blocker_count"])
        self.assertEqual("5.8.2", payload["skill_version"])
        self.assertEqual("5.8", payload["schema_version"])
        self.assertEqual(
            {"code", "severity", "stage", "slide_id", "message", "metrics"},
            set(payload["warnings"][0]),
        )

        warning_only = quality.summarize(payload["warnings"], [])
        self.assertEqual("pass_with_warnings", warning_only["status"])

    def test_blueprint_usability_blocks_only_structural_failures(self):
        quality = self._quality()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            usable = root / "usable.png"
            page = Image.new("RGB", (1600, 900), "white")
            draw = ImageDraw.Draw(page)
            draw.rectangle((40, 70, 1560, 150), fill="#1E386B")
            draw.rectangle((80, 280, 760, 760), outline="#3F628F", width=8)
            draw.rectangle((840, 280, 1520, 760), outline="#7F7F7F", width=8)
            page.save(usable)

            blank = root / "blank.png"
            Image.new("RGB", (1600, 900), "white").save(blank)
            square = root / "square.png"
            Image.new("RGB", (900, 900), "#1E386B").save(square)

            self.assertEqual([], quality.assess_blueprint(usable, "S01")["blockers"])
            self.assertTrue(quality.assess_blueprint(blank, "S01")["blockers"])
            self.assertTrue(quality.assess_blueprint(square, "S01")["blockers"])

    def test_imagegen_retries_once_only_when_no_artifact_exists(self):
        quality = self._quality()
        self.assertTrue(quality.should_retry_imagegen(1, artifact_exists=False, error_kind="network"))
        self.assertFalse(quality.should_retry_imagegen(2, artifact_exists=False, error_kind="network"))
        self.assertFalse(quality.should_retry_imagegen(1, artifact_exists=True, error_kind="text_mismatch"))

    def test_visual_crop_failure_uses_nonblocking_fallback(self):
        quality = self._quality()
        self.assertEqual("native_rebuild", quality.visual_fallback("pictogram", crop_succeeded=False))
        self.assertEqual("omitted", quality.visual_fallback("logo", crop_succeeded=False))
        self.assertEqual("crop", quality.visual_fallback("device", crop_succeeded=True))
        template = (SKILL / "assets" / "direct_blueprint_generator_template.py").read_text(encoding="utf-8")
        self.assertIn("add_native_visual_fallback", template)
        self.assertIn("ASSET_FALLBACK_", template)
        self.assertIn('element.get("fallback_policy") == "native_rebuild"', template)

    def test_invalid_composition_is_a_v58_asset_warning(self):
        extractor = load_module("v582_asset_extractor_warning", SKILL / "scripts" / "extract_direct_assets.py")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            draft_dir = project / ".build" / "design_drafts"
            draft_dir.mkdir(parents=True)
            draft = draft_dir / "S01.png"
            Image.new("RGB", (1600, 900), "white").save(draft)
            draft.with_suffix(".composition.json").write_text("{invalid", encoding="utf-8")
            generator = project / "generate_deck.py"
            generator.write_text(
                "\n".join(
                    [
                        "DECK_META = {'schema_version': '5.8'}",
                        "SLIDES = [{'slide_id': 'S01', 'visual_review': 'extract_declared', "
                        "'visual_review_evidence': {}, 'complex_visuals': "
                        "[{'asset_id': 'A01', 'kind': 'pictogram'}]}]",
                        "DESIGN_DRAFTS = {'S01': {'path': '.build/design_drafts/S01.png'}}",
                        "ASSET_CROPS = {'A01': {'slide_id': 'S01', 'source_px': [10, 10, 100, 100], "
                        "'target_box_in': [1, 1, 1, 1]}}",
                    ]
                ),
                encoding="utf-8",
            )
            report = extractor.extract_direct_assets(generator, project)
        self.assertTrue(report["ok"])
        self.assertEqual("pass_with_warnings", report["status"])
        self.assertTrue(any("composition record is unreadable" in item for item in report["warnings"]))


class V582IntegrityBindingTests(unittest.TestCase):
    def test_cached_quality_keeps_warnings_but_drops_historical_blockers(self):
        pipeline = load_module("v582_pipeline_warning_cache", SKILL / "scripts" / "project_pipeline.py")
        quality = pipeline._warning_only_quality(
            {
                "warnings": [
                    {
                        "code": "OLD_WARNING",
                        "severity": "warning",
                        "stage": "audit",
                        "slide_id": "S01",
                        "message": "still advisory",
                        "metrics": {},
                    }
                ],
                "blockers": [
                    {
                        "code": "OLD_BLOCKER",
                        "severity": "blocker",
                        "stage": "source",
                        "slide_id": None,
                        "message": "already resolved",
                        "metrics": {},
                    }
                ],
            }
        )
        self.assertEqual(1, quality["warning_count"])
        self.assertEqual(0, quality["blocker_count"])
        self.assertEqual("pass_with_warnings", quality["status"])

    def test_text_audit_and_pipeline_bind_to_the_exact_pptx(self):
        audit = load_module("v582_ppt_text_audit", SKILL / "scripts" / "ppt_text_audit.py")
        pipeline = load_module("v582_pipeline_hash_binding", SKILL / "scripts" / "project_pipeline.py")
        pack = load_module("v582_pack_hash_binding", SKILL / "scripts" / "pack_delivery.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pptx = root / "report.pptx"
            with zipfile.ZipFile(pptx, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "ppt/slides/slide1.xml",
                    '<p:sld xmlns:p="urn:p"><a:t xmlns:a="urn:a">canonical</a:t></p:sld>',
                )
            result = audit.audit_pptx_text(pptx)
            expected_hash = hashlib.sha256(pptx.read_bytes()).hexdigest()
            self.assertEqual(expected_hash, result["pptx_sha256"])
            audit_path = root / "ppt_text_audit.json"
            audit_path.write_text(json.dumps(result), encoding="utf-8")
            self.assertTrue(pipeline._audit_matches_pptx(audit_path, pptx))
            self.assertEqual(
                [],
                pack.validate_pptx_hash_bindings(
                    pptx,
                    {"pptx_sha256": expected_hash},
                    result,
                ),
            )
            pptx.write_bytes(pptx.read_bytes() + b"tampered")
            self.assertFalse(pipeline._audit_matches_pptx(audit_path, pptx))
            self.assertTrue(
                pack.validate_pptx_hash_bindings(
                    pptx,
                    {"pptx_sha256": expected_hash},
                    result,
                )
            )

    def test_source_digest_revalidates_source_files_and_hashes(self):
        source_cache = load_module("v582_source_cache_integrity", SKILL / "scripts" / "v58_source_cache.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.txt"
            source.write_text("canonical source", encoding="utf-8")
            source_cache.write_source_digest(root, [source], {"text": "canonical source"})
            self.assertEqual([], source_cache.validate_source_digest(root))
            source.write_text("changed source", encoding="utf-8")
            errors = source_cache.validate_source_digest(root)
        self.assertTrue(any("SHA-256" in message or "changed" in message for message in errors), errors)

    def test_missing_source_digest_is_a_compiler_blocker(self):
        compiler = load_module("v582_compiler_source_blocker", SKILL / "scripts" / "project_compiler.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".build").mkdir()
            (root / "project_brief.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.8",
                        "requested_page_count": 1,
                        "production_mode": "fast",
                        "blueprint_engine": "none",
                    }
                ),
                encoding="utf-8",
            )
            (root / ".build" / "slides.json").write_text("[]", encoding="utf-8")
            (root / ".build" / "page_specs.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source digest is missing"):
                compiler.compile_project(root)


class V582DiagnosticsTests(unittest.TestCase):
    def test_blueprint_text_differences_are_warnings(self):
        benchmark = load_module("v582_text_benchmark", SKILL / "scripts" / "v58_text_benchmark.py")
        slides = [{"slide_id": "S01", "chapter": "章节", "title": "标题", "core_points": ["判断"], "source": "来源"}]
        specs = {"S01": {"elements": []}}
        digest = "a" * 64
        payload = benchmark.make_benchmark(slides, specs, {"S01": digest})
        payload["pages"]["S01"].update(
            reviewed=True,
            exact_match=False,
            differences=[{"expected": "电子氟化液", "observed": "电子氧化液"}],
        )
        diagnostics = benchmark.diagnose_benchmark(payload, slides, specs, {"S01": digest})
        self.assertEqual([], diagnostics["blockers"])
        self.assertTrue(any(item["code"] == "BLUEPRINT_TEXT_MISMATCH" for item in diagnostics["warnings"]))

    def test_visual_counts_and_more_than_five_are_warnings_for_v58(self):
        contracts = load_module("v582_visual_contracts", SKILL / "scripts" / "v56_contracts.py")
        visuals = [
            {
                "visual_id": f"V{index:02d}",
                "kind": "pictogram",
                "description": "icon",
                "disposition": "native_rebuild",
                "rebuild_recipe": "circle_plus_text",
            }
            for index in range(1, 8)
        ]
        manifest = {
            "schema_version": "5.8",
            "pages": {
                "S01": {
                    "design_draft_path": ".build/design_drafts/S01.png",
                    "design_draft_sha256": "a" * 64,
                    "imagegen_attempt_count": 1,
                    "transport_attempt_count": 2,
                    "visual_plan": [],
                    "visual_reviewed": True,
                    "observed_candidate_count": 9,
                    "candidate_count": 7,
                    "visuals": visuals,
                }
            },
        }
        diagnostics = contracts.diagnose_visual_manifest(manifest)
        self.assertEqual([], diagnostics["blockers"])
        self.assertGreaterEqual(len(diagnostics["warnings"]), 1)
        self.assertEqual([], contracts.validate_visual_manifest(manifest))

    def test_route_density_palette_and_evidence_are_advisory(self):
        prebuild = load_module("v582_prebuild", SKILL / "scripts" / "v58_prebuild.py")
        brief = {"schema_version": "5.8", "requested_page_count": 1}
        slides = [
            {
                "slide_id": "S01",
                "chapter": "章节",
                "title": "标题",
                "source": "来源",
                "visual_route": {"data_kind": "time_series"},
                "core_points": ["短判断"],
                "modules": [{"module_id": "M01"}],
                "primary_visual_module_id": "M01",
                "evidence_inventory": [
                    {"evidence_id": "E01", "statement": "证据", "priority": "supporting", "module_id": None}
                ],
            }
        ]
        specs = {
            "S01": {
                "elements": [
                    {"type": "matrix", "box": [0, 0, 3, 1], "headers": ["A"], "rows": [["B"]], "fill": "#1E386B"}
                ]
            }
        }
        diagnostics = prebuild.diagnose_project_specs(brief, slides, specs, {"pages": {"S01": {"visuals": []}}})
        self.assertEqual([], diagnostics["blockers"])
        self.assertGreaterEqual(len(diagnostics["warnings"]), 3)
        self.assertEqual([], prebuild.validate_project_specs(brief, slides, specs, {"pages": {"S01": {"visuals": []}}}))

    def test_stale_blueprint_text_benchmark_metadata_is_advisory(self):
        benchmark = load_module("v582_text_benchmark_stale", SKILL / "scripts" / "v58_text_benchmark.py")
        slides = [{"slide_id": "S01", "chapter": "章节", "title": "标题", "core_points": ["判断"], "source": "来源"}]
        specs = {"S01": {"elements": []}}
        payload = benchmark.make_benchmark(slides, specs, {"S01": "a" * 64})
        payload["pages"]["S01"]["canonical_sha256"] = "b" * 64
        payload["pages"]["S01"]["design_draft_sha256"] = "c" * 64
        diagnostics = benchmark.diagnose_benchmark(payload, slides, specs, {"S01": "a" * 64})
        self.assertEqual([], diagnostics["blockers"])
        self.assertGreaterEqual(len(diagnostics["warnings"]), 2)
        self.assertEqual([], benchmark.validate_benchmark(payload, slides, specs, {"S01": "a" * 64}))

    def test_runtime_data_structure_blocks_but_arbitrary_size_limits_warn(self):
        prebuild = load_module("v582_prebuild_runtime_structure", SKILL / "scripts" / "v58_prebuild.py")
        brief = {"schema_version": "5.8", "requested_page_count": 1, "production_mode": "fast"}
        slide = {
            "slide_id": "S01",
            "chapter": "章节",
            "title": "标题",
            "core_points": ["判断"],
            "source": "来源",
            "visual_route": {"data_kind": "process"},
        }
        invalid = {
            "S01": {
                "elements": [
                    {"type": "asset", "box": [0, 0, 1, 1]},
                    {"type": "matrix", "box": [1, 0, 3, 2], "headers": None, "rows": []},
                    {"type": "flow", "box": [4, 0, 4, 2], "steps": "not-a-list"},
                    {"type": "rect", "box": [8, 0, 1, 1], "fill": "bad-color"},
                ]
            }
        }
        blockers = prebuild.validate_project_specs(brief, [slide], invalid)
        self.assertTrue(any("asset_id" in message for message in blockers), blockers)
        self.assertTrue(any("matrix headers" in message for message in blockers), blockers)
        self.assertTrue(any("flow steps" in message for message in blockers), blockers)
        self.assertTrue(any("invalid color" in message for message in blockers), blockers)

        advisory = {
            "S01": {
                "elements": [
                    {
                        "type": "flow",
                        "role": "primary_evidence",
                        "box": [0, 0, 7, 3],
                        "steps": [{"title": f"步骤{index}"} for index in range(1, 8)],
                    },
                    {"type": "rect", "box": [0, 3.1, 7, 0.4], "fill": "#EDEDED"},
                ]
            }
        }
        diagnostics = prebuild.diagnose_project_specs(brief, [slide], advisory)
        self.assertEqual([], diagnostics["blockers"])
        self.assertTrue(any("two to six" in item["message"] for item in diagnostics["warnings"]))

    def test_blueprint_manifest_page_coverage_is_structural(self):
        prebuild = load_module("v582_prebuild_manifest_coverage", SKILL / "scripts" / "v58_prebuild.py")
        brief = {
            "schema_version": "5.8",
            "requested_page_count": 1,
            "production_mode": "blueprint",
        }
        slides = [{
            "slide_id": "S01",
            "chapter": "章节",
            "title": "标题",
            "core_points": ["判断"],
            "source": "来源",
            "visual_route": {"data_kind": "qualitative", "qualitative_form": "narrative"},
        }]
        specs = {"S01": {"elements": [{"type": "text_card", "box": [0, 0, 4, 2]}]}}
        diagnostics = prebuild.diagnose_project_specs(
            brief,
            slides,
            specs,
            {"schema_version": "5.8", "pages": {"S02": {}}},
        )
        self.assertTrue(any(item["code"] == "VISUAL_PAGE_COVERAGE" for item in diagnostics["blockers"]))


class V582RuntimeActivationTests(unittest.TestCase):
    def test_pywin32_activation_clears_failed_imports_and_adds_runtime_paths(self):
        runtime = load_module("v582_windows_runtime", SKILL / "scripts" / "ensure_windows_runtime.py")
        with tempfile.TemporaryDirectory() as directory:
            site_packages = Path(directory)
            for relative in ("win32", "win32/lib", "pythonwin", "pywin32_system32"):
                (site_packages / relative).mkdir(parents=True)
            original = dict(sys.modules)
            try:
                sys.modules["pywintypes"] = None
                activated = runtime.activate_pywin32_runtime(site_packages)
                self.assertNotIn("pywintypes", sys.modules)
                self.assertIn(str(site_packages / "win32"), activated)
                self.assertIn(str(site_packages / "win32" / "lib"), activated)
            finally:
                sys.modules.clear()
                sys.modules.update(original)


class V582DocumentationTests(unittest.TestCase):
    def test_skill_declares_visual_first_smooth_pipeline(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        image_prompt = (SKILL / "prompts" / "imagegen_blueprint_prompt.md").read_text(encoding="utf-8")
        layout = (SKILL / "references" / "layout_and_chart_rules.md").read_text(encoding="utf-8")
        agent = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        combined = "\n".join((skill, image_prompt, layout, agent)).lower()
        self.assertIn("v5.8.2", combined)
        self.assertIn("visual-first", combined)
        self.assertIn("pass_with_warnings", combined)
        self.assertNotIn("at most five", combined)
        self.assertNotIn("zero to five", combined)


class V582PipelinePolicyTests(unittest.TestCase):
    @staticmethod
    def _write_prebuild_project(root: Path, *, blank: bool = False) -> None:
        build = root / ".build"
        drafts = build / "design_drafts"
        drafts.mkdir(parents=True)
        draft = drafts / "S01.png"
        image = Image.new("RGB", (1600, 900), "white")
        if not blank:
            draw = ImageDraw.Draw(image)
            draw.rectangle((40, 70, 1560, 150), fill="#1E386B")
            draw.rectangle((80, 280, 1520, 760), outline="#7F7F7F", width=8)
        image.save(draft)
        (root / "project_brief.json").write_text(
            json.dumps(
                {
                    "schema_version": "5.8",
                    "requested_page_count": 1,
                    "production_mode": "blueprint",
                    "blueprint_engine": "direct",
                }
            ),
            encoding="utf-8",
        )
        slides = [
            {
                "slide_id": "S01",
                "chapter": "第一章",
                "title": "测试页",
                "core_points": ["短判断"],
                "source": "测试材料",
                "visual_route": {"data_kind": "qualitative", "qualitative_form": "parallel"},
                "modules": [{"module_id": "M01"}],
                "primary_visual_module_id": "M01",
                "evidence_inventory": [
                    {"evidence_id": "E01", "statement": "证据", "priority": "supporting", "module_id": None}
                ],
            }
        ]
        page_specs = {
            "S01": {
                "elements": [
                    {"type": "text_card", "box": [0.2, 0.2, 11.8, 3.8], "title": "测试", "body": "正文"}
                ]
            }
        }
        (build / "slides.json").write_text(json.dumps(slides, ensure_ascii=False), encoding="utf-8")
        (build / "page_specs.json").write_text(json.dumps(page_specs, ensure_ascii=False), encoding="utf-8")
        (build / "visual_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "5.8",
                    "pages": {
                        "S01": {
                            "design_draft_path": ".build/design_drafts/S01.png",
                            "design_draft_sha256": hashlib.sha256(draft.read_bytes()).hexdigest(),
                            "imagegen_attempt_count": 1,
                            "transport_attempt_count": 1,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_prebuild_writes_warning_report_and_allows_ordinary_blueprint_defects(self):
        pipeline = load_module("v582_pipeline_warning", SKILL / "scripts" / "project_pipeline.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_prebuild_project(root)
            result = pipeline.prebuild_project(root)
            quality = json.loads((root / ".build" / "quality_report.json").read_text(encoding="utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual("pass_with_warnings", result["quality_status"])
        self.assertEqual("pass_with_warnings", quality["status"])
        self.assertEqual(0, quality["blocker_count"])

    def test_prebuild_blocks_blank_blueprint(self):
        pipeline = load_module("v582_pipeline_blank", SKILL / "scripts" / "project_pipeline.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_prebuild_project(root, blank=True)
            with self.assertRaisesRegex(ValueError, "BLUEPRINT_BLANK|insufficient visible structure"):
                pipeline.prebuild_project(root)

    def test_pipeline_result_quality_fields_are_derived_from_report(self):
        pipeline = load_module("v582_pipeline_result", SKILL / "scripts" / "project_pipeline.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".build").mkdir()
            (root / ".build" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.8",
                        "skill_version": "5.8.2",
                        "status": "pass_with_warnings",
                        "warning_count": 3,
                        "blocker_count": 0,
                        "warnings": [],
                        "blockers": [],
                    }
                ),
                encoding="utf-8",
            )
            fields = pipeline._quality_fields(root)
        self.assertEqual(
            {"quality_status": "pass_with_warnings", "warning_count": 3, "blocker_count": 0},
            fields,
        )


class V582DeliveryPolicyTests(unittest.TestCase):
    @staticmethod
    def _minimal_pptx(path: Path) -> None:
        payload = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:sldIdLst><p:sldId id="256" r:id="rId1" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            '</p:sldIdLst></p:presentation>'
        )
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("ppt/presentation.xml", payload)

    def test_v58_delivery_allows_explicit_path_and_extra_project_python(self):
        pack = load_module("v582_pack_smooth", SKILL / "scripts" / "pack_delivery.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            (project / "blueprints").mkdir()
            (project / "blueprints" / "S01.png").write_bytes(b"png")
            pptx = project / "report.pptx"
            self._minimal_pptx(pptx)
            generator = project / "generate_deck.py"
            generator.write_text("# generator\n", encoding="utf-8")
            (project / "helper.py").write_text("# harmless project helper\n", encoding="utf-8")
            (project / "project_brief.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.8",
                        "requested_page_count": 1,
                        "production_mode": "blueprint",
                        "blueprint_engine": "direct",
                    }
                ),
                encoding="utf-8",
            )
            output = root / "custom" / "delivery.zip"
            with patch.object(pack, "_validate_v58_project", return_value=[]):
                result = pack.package_direct_delivery(
                    project_dir=project,
                    pptx_path=pptx,
                    generator_path=generator,
                    output_zip=output,
                    desktop_dir=root / "Desktop",
                )
        self.assertEqual(output, result)


if __name__ == "__main__":
    unittest.main()
