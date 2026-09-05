from __future__ import annotations

import importlib.util
import hashlib
import inspect
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


class V58VersionAndTimingTests(unittest.TestCase):
    def test_v58_schema_is_supported_without_dropping_v56_or_v57(self):
        pipeline = load_module("v58_pipeline_version", SKILL / "scripts" / "project_pipeline.py")
        compiler = load_module("v58_compiler_version", SKILL / "scripts" / "project_compiler.py")
        contracts = load_module("v58_contracts_version", SKILL / "scripts" / "v56_contracts.py")
        self.assertEqual("5.9", pipeline.SCHEMA_VERSION)
        for module in (compiler, contracts):
            self.assertEqual("5.8", module.SCHEMA_VERSION)
        for module in (pipeline, compiler, contracts):
            self.assertTrue({"5.6", "5.7", "5.8"}.issubset(module.SUPPORTED_SCHEMA_VERSIONS))

    def test_v58_timing_records_seconds_and_minutes(self):
        pipeline = load_module("v58_pipeline_timing", SKILL / "scripts" / "project_pipeline.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project_brief.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.8",
                        "requested_page_count": 1,
                        "production_mode": "fast",
                        "confirmation_source": "user_explicit",
                    }
                ),
                encoding="utf-8",
            )
            (root / ".build").mkdir()
            (root / ".build" / "pipeline_timing.json").write_text(
                json.dumps({"schema_version": "5.8", "stages": []}), encoding="utf-8"
            )
            pipeline._record_timing(root, "source_parse", 10.0, 130.0, ok=True)
            timing = json.loads((root / ".build" / "pipeline_timing.json").read_text(encoding="utf-8"))
        record = timing["stages"][-1]
        self.assertEqual(120.0, record["duration_seconds"])
        self.assertIn("duration_minutes", record)
        self.assertEqual(2.0, record["duration_minutes"])


class V58SourceCacheTests(unittest.TestCase):
    def test_source_digest_is_order_stable_and_invalidates_on_content_change(self):
        module_path = SKILL / "scripts" / "v58_source_cache.py"
        self.assertTrue(module_path.is_file(), "V5.8 source cache module is missing")
        cache = load_module("v58_source_cache", module_path)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_a = root / "a.txt"
            source_b = root / "b.txt"
            source_a.write_text("alpha", encoding="utf-8")
            source_b.write_text("beta", encoding="utf-8")
            first = cache.source_set_sha256([source_a, source_b])
            second = cache.source_set_sha256([source_b, source_a])
            digest_path = cache.write_source_digest(
                root,
                [source_a, source_b],
                {"evidence_inventory": [{"evidence_id": "E01", "statement": "alpha"}]},
            )
            current = cache.load_source_digest(root, [source_b, source_a])
            source_b.write_text("changed", encoding="utf-8")
            stale = cache.load_source_digest(root, [source_a, source_b])
        self.assertEqual(first, second)
        self.assertTrue(digest_path.name == "source_digest.json")
        self.assertTrue(current["parsed_once"])
        self.assertIsNone(stale)

    def test_source_digest_validation_rejects_missing_or_unparsed_projects(self):
        cache = load_module("v58_source_cache_gate", SKILL / "scripts" / "v58_source_cache.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = cache.validate_source_digest(root)
            (root / ".build").mkdir()
            (root / ".build" / "source_digest.json").write_text(
                json.dumps({"schema_version": "5.8", "parsed_once": False}),
                encoding="utf-8",
            )
            unparsed = cache.validate_source_digest(root)
        self.assertTrue(any("missing" in error for error in missing), missing)
        self.assertTrue(any("parsed_once" in error for error in unparsed), unparsed)

    def test_preflight_requires_the_source_cache_module(self):
        pipeline = load_module("v58_pipeline_source_resource", SKILL / "scripts" / "project_pipeline.py")
        self.assertIn("v58_source_cache.py", inspect.getsource(pipeline.preflight_project))


class V58BlueprintLifecycleTests(unittest.TestCase):
    def test_v58_visual_manifest_reports_extra_generation_as_a_warning(self):
        contracts = load_module("v58_contracts_draft", SKILL / "scripts" / "v56_contracts.py")
        digest = hashlib.sha256(b"draft").hexdigest()
        manifest = {
            "schema_version": "5.8",
            "pages": {
                "S01": {
                    "design_draft_path": ".build/design_drafts/S01.png",
                    "design_draft_sha256": digest,
                    "imagegen_attempt_count": 2,
                    "visual_plan": [],
                    "visual_reviewed": True,
                    "observed_candidate_count": 0,
                    "candidate_count": 0,
                    "visuals": [],
                }
            },
        }
        diagnostics = contracts.diagnose_visual_manifest(manifest)
        self.assertEqual([], diagnostics["blockers"])
        self.assertTrue(any(item["code"] == "IMAGEGEN_ATTEMPT_COUNT" for item in diagnostics["warnings"]))
        self.assertEqual([], contracts.validate_visual_manifest(manifest))
        manifest["pages"]["S01"]["imagegen_attempt_count"] = 1
        self.assertEqual([], contracts.validate_visual_manifest(manifest))

    def test_formal_blueprint_is_byte_identical_to_original_imagegen_draft(self):
        pipeline = load_module("v58_pipeline_formalize", SKILL / "scripts" / "project_pipeline.py")
        self.assertTrue(hasattr(pipeline, "formalize_blueprints"), "formalize_blueprints is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            drafts = root / ".build" / "design_drafts"
            rendered = root / ".build" / "rendered" / "current"
            drafts.mkdir(parents=True)
            rendered.mkdir(parents=True)
            draft_bytes = b"original-imagegen-png"
            render_bytes = b"final-render-png-is-only-a-benchmark"
            (drafts / "S01.png").write_bytes(draft_bytes)
            (rendered / "S01.png").write_bytes(render_bytes)
            pptx = root / "output" / "report.pptx"
            pptx.parent.mkdir()
            pptx.write_bytes(b"pptx")
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
            (root / ".build" / "visual_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.8",
                        "pages": {
                            "S01": {
                                "design_draft_path": ".build/design_drafts/S01.png",
                                "design_draft_sha256": hashlib.sha256(draft_bytes).hexdigest(),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = pipeline.formalize_blueprints(root, pptx)
            formal = root / "blueprints" / "S01.png"
            formal_bytes = formal.read_bytes()
            manifest = json.loads((root / ".build" / "formal_blueprint_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(draft_bytes, formal_bytes)
        self.assertEqual(result["pages"]["S01"]["design_draft_sha256"], manifest["pages"]["S01"]["formal_blueprint_sha256"])
        self.assertNotEqual(result["pages"]["S01"]["render_sha256"], manifest["pages"]["S01"]["formal_blueprint_sha256"])
        self.assertEqual(hashlib.sha256(b"pptx").hexdigest(), manifest["pptx_sha256"])

    def test_v58_compiler_embeds_design_drafts_separately_from_formal_blueprints(self):
        compiler = load_module("v58_compiler_drafts", SKILL / "scripts" / "project_compiler.py")
        self.assertIn("design_drafts", inspect.signature(compiler.compile_generator_source).parameters)
        template = (SKILL / "assets" / "direct_blueprint_generator_template.py").read_text(encoding="utf-8")
        slide = {
            "slide_id": "S01",
            "chapter": "章节",
            "title": "标题",
            "core_points": ["一" * 80],
            "density_profile": "medium",
            "modules": [{"module_id": "M01", "title": "模块"}],
            "primary_visual_module_id": "M01",
            "evidence_inventory": [{"evidence_id": "E01", "statement": "证据", "priority": "must_keep", "module_id": "M01"}],
        }
        source = compiler.compile_generator_source(
            template,
            {"schema_version": "5.8", "requested_page_count": 1, "production_mode": "blueprint"},
            [slide],
            {"S01": {"elements": [{"type": "text_card", "box": [0, 0, 2, 2], "title": "模块", "body": "证据"}]}},
            {},
            {},
            SKILL / "assets" / "company_template.pptx",
            design_drafts={"S01": {"path": ".build/design_drafts/S01.png", "sha256": "a" * 64}},
        )
        self.assertIn("DESIGN_DRAFTS = {'S01':", source)
        self.assertIn("BLUEPRINTS = {}", source)

    def test_packaging_rejects_a_formal_blueprint_that_differs_from_imagegen_draft(self):
        pack = load_module("v58_pack_formal", SKILL / "scripts" / "pack_delivery.py")
        self.assertTrue(
            hasattr(pack, "validate_formal_blueprint_manifest"),
            "formal blueprint packaging validator is missing",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rendered = root / ".build" / "rendered" / "current"
            drafts = root / ".build" / "design_drafts"
            formal_dir = root / "blueprints"
            rendered.mkdir(parents=True)
            drafts.mkdir(parents=True)
            formal_dir.mkdir()
            pptx = root / "report.pptx"
            pptx.write_bytes(b"pptx")
            (rendered / "S01.png").write_bytes(b"render")
            (drafts / "S01.png").write_bytes(b"draft")
            (formal_dir / "S01.png").write_bytes(b"different")
            render_hash = hashlib.sha256(b"render").hexdigest()
            draft_hash = hashlib.sha256(b"draft").hexdigest()
            formal_hash = hashlib.sha256(b"different").hexdigest()
            (root / ".build" / "formal_blueprint_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.8",
                        "pptx_sha256": hashlib.sha256(b"pptx").hexdigest(),
                        "pages": {
                            "S01": {
                                "design_draft_path": ".build/design_drafts/S01.png",
                                "design_draft_sha256": draft_hash,
                                "render_path": ".build/rendered/current/S01.png",
                                "render_sha256": render_hash,
                                "formal_blueprint_path": "blueprints/S01.png",
                                "formal_blueprint_sha256": formal_hash,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            errors = pack.validate_formal_blueprint_manifest(root, pptx, ["S01"])
        self.assertTrue(any("ImageGen" in error for error in errors), errors)


class V58VisualRoutingTests(unittest.TestCase):
    def _policy(self):
        path = SKILL / "scripts" / "v58_visual_policy.py"
        self.assertTrue(path.is_file(), "V5.8 visual policy module is missing")
        return load_module("v58_visual_policy", path)

    def test_chartable_data_requires_a_chart_as_primary_evidence(self):
        policy = self._policy()
        cases = [
            ("time_series", "line_chart"),
            ("category_comparison", "hbar_chart"),
            ("composition", "donut_chart"),
            ("multi_metric_comparison", "grouped_hbar_chart"),
        ]
        for data_kind, accepted_type in cases:
            slide = {"slide_id": "S01", "visual_route": {"data_kind": data_kind}}
            accepted = {"elements": [{"type": accepted_type, "role": "primary_evidence", "box": [0, 0, 8, 3]}]}
            matrix = {"elements": [{"type": "matrix", "role": "primary_evidence", "box": [0, 0, 8, 3]}]}
            self.assertEqual([], policy.validate_visual_route(slide, accepted), data_kind)
            self.assertTrue(policy.validate_visual_route(slide, matrix), data_kind)

    def test_qualitative_page_does_not_require_a_chart(self):
        policy = self._policy()
        slide = {
            "slide_id": "S01",
            "visual_route": {"data_kind": "qualitative", "qualitative_form": "parallel"},
        }
        spec = {"elements": [{"type": "text_card", "role": "primary_evidence", "box": [0, 0, 5.8, 3.2]}]}
        self.assertEqual([], policy.validate_visual_route(slide, spec))

    def test_parallel_qualitative_points_cannot_be_misrepresented_as_a_flow(self):
        policy = self._policy()
        slide = {
            "slide_id": "S01",
            "visual_route": {"data_kind": "qualitative", "qualitative_form": "parallel"},
        }
        cards = {"elements": [{"type": "text_card", "role": "primary_evidence", "box": [0, 0, 8, 3.2]}]}
        flow = {"elements": [{"type": "flow", "role": "primary_evidence", "box": [0, 0, 8, 3.2]}]}
        self.assertEqual([], policy.validate_visual_route(slide, cards))
        self.assertTrue(any("parallel" in error for error in policy.validate_visual_route(slide, flow)))

    def test_qualitative_route_requires_an_explicit_semantic_form(self):
        policy = self._policy()
        slide = {"slide_id": "S01", "visual_route": {"data_kind": "qualitative"}}
        spec = {"elements": [{"type": "text_card", "role": "primary_evidence", "box": [0, 0, 8, 3.2]}]}
        self.assertTrue(any("qualitative_form" in error for error in policy.validate_visual_route(slide, spec)))

    def test_density_uses_adaptive_occupancy_bands_not_a_fixed_module_count(self):
        policy = self._policy()
        spec = {
            "elements": [
                {"type": "line_chart", "box": [0, 0, 7.2, 3.8]},
                {"type": "text_card", "box": [7.45, 0, 4.75, 3.8]},
            ]
        }
        occupancy = policy.body_occupancy(spec)
        self.assertGreater(occupancy, 0.80)
        self.assertEqual((0.60, 0.96), policy.density_band("time_series"))
        self.assertEqual((0.48, 0.90), policy.density_band("qualitative"))

    def test_fast_specs_use_visual_route_instead_of_falling_back_to_matrix(self):
        fast = load_module("v58_fast_route", SKILL / "scripts" / "fast_page_specs.py")
        slide = {
            "slide_id": "S01",
            "visual_route": {
                "data_kind": "time_series",
                "data": [
                    {"label": "2022", "value": 100},
                    {"label": "2023", "value": 130},
                    {"label": "2024", "value": 170},
                ],
            },
            "modules": [{"module_id": "M01", "title": "趋势", "detail": "连续增长"}],
        }
        spec = fast.build_page_specs([slide])["S01"]
        primary = [element for element in spec["elements"] if element.get("role") == "primary_evidence"]
        self.assertTrue(primary, "fast specs did not create a routed primary evidence visual")
        self.assertEqual("line_chart", primary[0]["type"])

    def test_shared_contract_enforces_route_and_density_for_v58(self):
        contracts = load_module("v58_contracts_route", SKILL / "scripts" / "v56_contracts.py")
        self.assertTrue(hasattr(contracts, "validate_v58_page_policy"), "shared V5.8 policy gate is missing")
        slide = {"slide_id": "S01", "visual_route": {"data_kind": "category_comparison"}}
        spec = {"S01": {"elements": [{"type": "matrix", "role": "primary_evidence", "box": [0, 0, 12.2, 3.8]}]}}
        errors = contracts.validate_v58_page_policy([slide], spec)
        self.assertTrue(any("category_comparison" in error for error in errors), errors)


class V58ChartRuntimeTests(unittest.TestCase):
    def test_runtime_implements_all_chart_first_element_types(self):
        runtime = load_module("v58_chart_runtime", SKILL / "assets" / "direct_blueprint_generator_template.py")
        for function_name in (
            "add_column_chart",
            "add_line_chart",
            "add_combo_chart",
            "add_donut_chart",
            "add_grouped_hbar_chart",
        ):
            self.assertTrue(hasattr(runtime, function_name), f"missing {function_name}")
        source = (SKILL / "assets" / "direct_blueprint_generator_template.py").read_text(encoding="utf-8")
        for element_type in (
            "column_chart",
            "line_chart",
            "combo_chart",
            "donut_chart",
            "grouped_hbar_chart",
        ):
            self.assertIn(f'kind == "{element_type}"', source)

    def test_nested_chart_and_metric_colors_are_normalized_before_com_assignment(self):
        runtime = load_module("v58_color_runtime", SKILL / "assets" / "direct_blueprint_generator_template.py")
        self.assertEqual(runtime.DARK_RED, runtime._spec_color("#C00000", runtime.NAVY))
        source = (SKILL / "assets" / "direct_blueprint_generator_template.py").read_text(encoding="utf-8")
        self.assertNotIn('color=metric.get("color", NAVY)', source)
        self.assertNotIn('fill = DARK_RED if item.get("highlight") else item.get("fill", BLUE)', source)

    def test_runtime_and_prebuild_support_the_flow_type_used_by_visual_routing(self):
        runtime = load_module("v58_flow_runtime", SKILL / "assets" / "direct_blueprint_generator_template.py")
        prebuild = load_module("v58_flow_prebuild", SKILL / "scripts" / "v58_prebuild.py")
        policy = load_module("v58_flow_policy", SKILL / "scripts" / "v58_visual_policy.py")
        self.assertTrue(hasattr(runtime, "add_flow"))
        self.assertIn("flow", prebuild.ALLOWED_ELEMENT_TYPES)
        supported = set().union(*policy.ROUTE_TYPES.values())
        self.assertTrue(supported.issubset(prebuild.ALLOWED_ELEMENT_TYPES), supported - prebuild.ALLOWED_ELEMENT_TYPES)


class V58VisualSystemTests(unittest.TestCase):
    def test_visual_plan_and_observed_counts_are_advisory(self):
        contracts = load_module("v58_visual_inventory_contract", SKILL / "scripts" / "v56_contracts.py")
        digest = "a" * 64
        base = {
            "schema_version": "5.8",
            "pages": {
                "S01": {
                    "design_draft_path": ".build/design_drafts/S01.png",
                    "design_draft_sha256": digest,
                    "imagegen_attempt_count": 1,
                    "visual_reviewed": True,
                    "visual_plan": [
                        {"visual_id": "V01", "kind": "pictogram", "description": "driver icon"}
                    ],
                    "observed_candidate_count": 0,
                    "candidate_count": 0,
                    "visuals": [],
                }
            },
        }
        diagnostics = contracts.diagnose_visual_manifest(base)
        self.assertEqual([], diagnostics["blockers"])
        self.assertTrue(diagnostics["warnings"])
        self.assertEqual([], contracts.validate_visual_manifest(base))

        page = base["pages"]["S01"]
        page["visual_plan"] = [
            {"visual_id": f"V{index:02d}", "kind": "pictogram", "description": "icon"}
            for index in range(1, 7)
        ]
        page["observed_candidate_count"] = 6
        page["candidate_count"] = 6
        diagnostics = contracts.diagnose_visual_manifest(base)
        self.assertEqual([], diagnostics["blockers"])
        self.assertTrue(any(item["code"] == "VISUAL_COUNT_HIGH" for item in diagnostics["warnings"]))

    def test_missing_reviewed_crop_is_reported_as_an_advisory(self):
        policy = load_module("v58_visual_policy_crop_binding", SKILL / "scripts" / "v58_visual_policy.py")
        manifest_page = {
            "visuals": [
                {
                    "visual_id": "V01",
                    "asset_id": "S01_A01",
                    "kind": "pictogram",
                    "disposition": "crop",
                    "role": "decorative_visual",
                }
            ]
        }
        native_substitute = {
            "elements": [
                {"type": "oval", "box": [0, 0, 1, 1], "fill": "#EDEDED", "text": "IP"},
                {"type": "rect", "box": [0, 1, 12.2, 0.4], "fill": "#EDEDED"},
            ]
        }
        errors = policy.validate_palette_and_visuals(native_substitute, manifest_page)
        self.assertTrue(any("asset crop" in error for error in errors), errors)

    def test_current_master_is_guide_independent_and_hash_bound(self):
        module_path = SKILL / "scripts" / "v58_template_contract.py"
        self.assertTrue(module_path.is_file(), "V5.8 template contract module is missing")
        template = load_module("v58_template_contract", module_path)
        result = template.inspect_template(SKILL / "assets" / "company_template.pptx")
        self.assertEqual(
            "591551aa5d9bb2c8d256943ddb381244a34b0f855504af50d0edd9b0ef5c2918",
            result["sha256"],
        )
        self.assertEqual(0, result["guide_count"])
        self.assertAlmostEqual(16 / 9, result["aspect_ratio"], places=3)

    def test_decorative_visuals_have_no_hard_count_cap(self):
        policy = load_module("v58_visual_policy_assets", SKILL / "scripts" / "v58_visual_policy.py")
        self.assertTrue(hasattr(policy, "validate_palette_and_visuals"), "visual-system validator is missing")
        page_spec = {"elements": [
            {"type": "line_chart", "box": [0, 0, 12, 3.8]},
            {"type": "rect", "box": [0, 3.8, 12, 0.4], "fill": "#EDEDED"},
            *[
                {"type": "asset", "asset_id": f"A{index}", "box": [index * 0.2, 3.8, 0.15, 0.15]}
                for index in range(6)
            ],
        ]}
        visual = {
            "kind": "pictogram",
            "disposition": "crop",
            "role": "decorative_visual",
        }
        five = {"visuals": [dict(visual, asset_id=f"A{index}") for index in range(5)]}
        six = {"visuals": [dict(visual, asset_id=f"A{index}") for index in range(6)]}
        self.assertEqual([], policy.validate_palette_and_visuals(page_spec, five))
        self.assertEqual([], policy.validate_palette_and_visuals(page_spec, six))

    def test_red_is_data_emphasis_only_and_navy_cannot_dominate_the_body(self):
        policy = load_module("v58_visual_policy_palette", SKILL / "scripts" / "v58_visual_policy.py")
        self.assertTrue(hasattr(policy, "validate_palette_and_visuals"), "visual-system validator is missing")
        bad_red = {"elements": [{"type": "rect", "box": [0, 0, 2, 1], "fill": "#C00000"}]}
        good_red = {
            "elements": [
                {
                    "type": "hbar_chart",
                    "box": [0, 0, 8, 3.8],
                    "data": [{"label": "重点", "value": 10, "highlight": True, "fill": "#C00000"}],
                },
                {"type": "rect", "box": [0, 3.3, 12.2, 0.5], "fill": "#EDEDED"},
            ]
        }
        navy_dominant = {"elements": [{"type": "rect", "box": [0, 0, 12.2, 2.0], "fill": "#1E386B"}]}
        self.assertTrue(any("data emphasis" in error for error in policy.validate_palette_and_visuals(bad_red, {})))
        self.assertEqual([], policy.validate_palette_and_visuals(good_red, {}))
        self.assertTrue(any("navy" in error for error in policy.validate_palette_and_visuals(navy_dominant, {})))

    def test_neutral_gray_is_required_and_navy_body_cap_is_twenty_percent(self):
        policy = load_module("v58_visual_policy_neutral_gray", SKILL / "scripts" / "v58_visual_policy.py")
        no_gray = {"elements": [{"type": "rect", "box": [0, 0, 12.2, 1.0], "fill": "#3F628F"}]}
        with_gray = {
            "elements": [
                {"type": "rect", "box": [0, 0, 12.2, 0.5], "fill": "#EDEDED"},
                {"type": "rect", "box": [0, 0.5, 12.2, 2.7], "fill": "#FFFFFF"},
            ]
        }
        navy_over_cap = {
            "elements": [
                {"type": "rect", "box": [0, 0, 12.2, 1.0], "fill": "#1E386B"},
                {"type": "rect", "box": [0, 1.0, 12.2, 0.5], "fill": "#EDEDED"},
            ]
        }
        self.assertTrue(any("neutral gray" in error for error in policy.validate_palette_and_visuals(no_gray, {})))
        self.assertEqual([], policy.validate_palette_and_visuals(with_gray, {}))
        self.assertTrue(any("20%" in error for error in policy.validate_palette_and_visuals(navy_over_cap, {})))


class V58CanonicalTextBenchmarkTests(unittest.TestCase):
    def test_ppt_text_audit_rejects_missing_canonical_literal(self):
        audit = load_module("v58_text_audit_canonical", SKILL / "scripts" / "ppt_text_audit.py")
        with tempfile.TemporaryDirectory() as directory:
            pptx = Path(directory) / "sample.pptx"
            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr(
                    "ppt/slides/slide1.xml",
                    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>标题</a:t></p:sld>',
                )
            result = audit.audit_pptx_text(
                pptx,
                slides=[{"slide_id": "S01", "chapter": "章节", "title": "标题", "core_points": ["核心判断"], "source": "来源"}],
                page_specs={"S01": {"elements": []}},
            )
        self.assertFalse(result["ok"])
        self.assertTrue(any("canonical text missing" in error for error in result["errors"]), result)

    def test_blueprint_text_benchmark_mismatch_is_advisory(self):
        benchmark = load_module("v58_text_benchmark", SKILL / "scripts" / "v58_text_benchmark.py")
        slides = [{"slide_id": "S01", "chapter": "章节", "title": "标题", "core_points": ["判断"], "source": "来源"}]
        specs = {"S01": {"elements": []}}
        draft_hash = "a" * 64
        payload = benchmark.make_benchmark(slides, specs, {"S01": draft_hash})
        payload["pages"]["S01"]["reviewed"] = True
        payload["pages"]["S01"]["exact_match"] = False
        payload["pages"]["S01"]["differences"] = [{"expected": "标题", "observed": "标題"}]
        errors = benchmark.validate_benchmark(payload, slides, specs, {"S01": draft_hash})
        diagnostics = benchmark.diagnose_benchmark(payload, slides, specs, {"S01": draft_hash})
        self.assertEqual([], errors)
        self.assertTrue(any(item["code"] == "BLUEPRINT_TEXT_MISMATCH" for item in diagnostics["warnings"]))


class V58PrebuildTests(unittest.TestCase):
    def _validator(self):
        path = SKILL / "scripts" / "v58_prebuild.py"
        self.assertTrue(path.is_file(), "V5.8 prebuild validator is missing")
        return load_module("v58_prebuild", path)

    def test_prebuild_blocks_runtime_structure_but_warns_on_color_policy(self):
        validator = self._validator()
        brief = {"schema_version": "5.8", "requested_page_count": 1, "production_mode": "fast"}
        slides = [{
            "slide_id": "S01",
            "chapter": "章节",
            "title": "标题",
            "core_points": ["核心判断"],
            "source": "来源",
            "visual_route": {"data_kind": "time_series"},
        }]
        page_specs = {
            "S01": {
                "elements": [
                    {"type": "unknown", "box": [0, 0, 1, 1]},
                    {"type": "rect", "box": [0, 0, -1, 1], "fill": "not-a-color"},
                    {"type": "line_chart", "role": "primary_evidence", "box": [0, 0, 8, 3], "data": [{"label": "2024", "value": "x"}]},
                ]
            }
        }
        errors = validator.validate_project_specs(brief, slides, page_specs)
        self.assertTrue(any("unsupported type" in error for error in errors), errors)
        self.assertTrue(any("positive" in error for error in errors), errors)
        self.assertTrue(any("invalid color" in error for error in errors), errors)
        self.assertTrue(any("numeric" in error for error in errors), errors)

    def test_valid_v58_specs_pass_without_importing_powerpoint(self):
        validator = self._validator()
        brief = {"schema_version": "5.8", "requested_page_count": 1, "production_mode": "fast"}
        slides = [{
            "slide_id": "S01",
            "chapter": "章节",
            "title": "标题",
            "core_points": ["核心判断"],
            "source": "来源",
            "visual_route": {"data_kind": "time_series"},
        }]
        page_specs = {
            "S01": {
                "elements": [
                    {
                        "type": "line_chart",
                        "role": "primary_evidence",
                        "box": [0, 0, 8, 3.8],
                        "data": [
                            {"label": "2022", "value": 10},
                            {"label": "2023", "value": 12},
                            {"label": "2024", "value": 15, "highlight": True, "fill": "#C00000"},
                        ],
                    },
                    {"type": "text_card", "box": [8.2, 0, 4, 3.8], "title": "解读", "body": "持续增长"},
                    {"type": "rect", "box": [0, 3.8, 12.2, 0.4], "fill": "#EDEDED"},
                ]
            }
        }
        self.assertEqual([], validator.validate_project_specs(brief, slides, page_specs))

    def test_runtime_validates_before_com_and_saves_atomically(self):
        source = (SKILL / "assets" / "direct_blueprint_generator_template.py").read_text(encoding="utf-8")
        validation_index = source.index("selected_ids = validate_embedded_contract")
        import_index = source.index("import win32com.client")
        self.assertLess(validation_index, import_index)
        self.assertIn("temporary_output.replace(output)", source)
        self.assertIn("presentation.SaveAs(str(temporary_output), 24)", source)


class V58DocumentationContractTests(unittest.TestCase):
    def test_skill_and_prompts_define_the_v58_lifecycle_and_boundaries(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        outline = (SKILL / "prompts" / "page_outline_prompt.md").read_text(encoding="utf-8")
        imagegen = (SKILL / "prompts" / "imagegen_blueprint_prompt.md").read_text(encoding="utf-8")
        reconstruction = (SKILL / "prompts" / "python_reconstruction_prompt.md").read_text(encoding="utf-8")
        layout = (SKILL / "references" / "layout_and_chart_rules.md").read_text(encoding="utf-8")
        visual = (SKILL / "references" / "company_visual_system.md").read_text(encoding="utf-8")
        schema = (SKILL / "references" / "slide_spec_schema.md").read_text(encoding="utf-8")
        agent = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertIn("Standard Report PPT V5.8.4", skill)
        self.assertIn('schema_version\": \"5.8', skill)
        for text in (skill, imagegen, reconstruction, schema):
            self.assertIn("design draft", text.lower())
            self.assertIn("formal blueprint", text.lower())
        for text in (skill, imagegen):
            self.assertIn("one successful ImageGen", text)
            self.assertIn("transport retry", text.lower())
        for text in (skill, outline, layout):
            self.assertIn("chart-first", text.lower())
            self.assertIn("qualitative", text.lower())
            self.assertIn("adaptive density", text.lower())
        for color in ("#1E386B", "#3F628F", "#7391B3", "#9DB4CC", "#EDEDED", "#D9D9D9", "#C00000"):
            self.assertIn(color, visual)
        self.assertNotIn("at most five", skill)
        self.assertIn("visual_plan", skill)
        self.assertIn("original ImageGen", skill)
        self.assertIn("PowerPoint editor guides", skill)
        # The entry point follows the current release; legacy lifecycle
        # compatibility is covered by the contracts above, not its UI label.
        self.assertIn("Use $standard-report-ppt", agent)
        self.assertIn("follow SKILL.md", agent)
        self.assertIn("allow_implicit_invocation: true", agent)


if __name__ == "__main__":
    unittest.main()
