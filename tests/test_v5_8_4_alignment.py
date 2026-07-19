from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    if not path.is_file():
        raise AssertionError(f"required V5.8.4 module is missing: {path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class V584AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="V584_alignment_")
        self.project = Path(self.temporary.name)
        self.build = self.project / ".build"
        self.drafts = self.build / "design_drafts"
        self.drafts.mkdir(parents=True)
        self.blueprints = self.project / "blueprints"
        self.blueprints.mkdir()
        self.draft = self.drafts / "S01.png"
        image = Image.new("RGB", (1600, 900), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((30, 60, 1570, 150), fill="#1E386B")
        draw.rectangle((60, 285, 780, 720), outline="#3F628F", width=4)
        draw.rectangle((820, 285, 1540, 720), outline="#7391B3", width=4)
        draw.ellipse((70, 300, 170, 400), fill="#9DB4CC")
        image.save(self.draft)
        (self.blueprints / "S01.png").write_bytes(self.draft.read_bytes())

        self.brief = {
            "schema_version": "5.8",
            "pipeline_revision": "5.8.4",
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "blueprint_engine": "direct",
        }
        (self.project / "project_brief.json").write_text(
            json.dumps(self.brief, ensure_ascii=False),
            encoding="utf-8",
        )
        self.bundle = {
            "schema_version": "5.8",
            "slides": [
                {
                    "slide_id": "S01",
                    "chapter": "三、洲际流动与AI人才分工",
                    "title": "洲际流动6,984人高于洲内流动4,447人",
                    "core_points": ["洲际流动规模高于洲内流动。"],
                    "source": "资料来源：测试报告",
                    "visual_route": {"data_kind": "category_comparison"},
                    "modules": [{"module_id": "continent_flow"}],
                    "primary_visual_module_id": "continent_flow",
                    "evidence_inventory": [
                        {
                            "evidence_id": "E01",
                            "statement": "洲际流动6,984人，洲内流动4,447人。",
                            "priority": "must_keep",
                            "module_id": "continent_flow",
                        }
                    ],
                }
            ],
            "page_specs": {
                "S01": {
                    "elements": [
                        {
                            "type": "grouped_hbar_chart",
                            "role": "primary_evidence",
                            "box": [0.2, 0.2, 7.0, 3.4],
                            "data": [
                                {"label": "亚洲", "values": [2158, 2018]},
                                {"label": "欧洲", "values": [2057, 2056]},
                                {"label": "北美洲", "values": [1901, 1908]},
                            ],
                        }
                    ]
                }
            },
            "visual_manifest": {
                "schema_version": "5.8",
                "pages": {
                    "S01": {
                        "design_draft_path": ".build/design_drafts/S01.png",
                        "imagegen_attempt_count": 1,
                        "transport_attempt_count": 1,
                        "visual_plan": ["世界地图节点", "跨境箭头"],
                    }
                },
            },
        }
        self.bundle_path = self.build / "authoring_bundle.json"
        self.bundle_path.write_text(
            json.dumps(self.bundle, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        resolved_spec = {
            "elements": [
                {
                    "type": "grouped_hbar_chart",
                    "role": "primary_evidence",
                    "layout": "paired_columns",
                    "box": [0.2, 0.2, 7.0, 3.4],
                    "series": [
                        {"name": "流入", "fill": "#1E386B"},
                        {"name": "流出", "fill": "#9DB4CC"},
                    ],
                    "show_legend": True,
                    "show_data_labels": True,
                    "data_label_format": "#,##0",
                    "row_annotations": ["+140", "+1", "-7"],
                    "data": [
                        {"label": "亚洲", "values": [2158, 2018]},
                        {"label": "欧洲", "values": [2057, 2056]},
                        {"label": "北美洲", "values": [1901, 1908]},
                    ],
                },
                {
                    "type": "asset",
                    "asset_id": "S01_V01",
                    "box": [0.1, 0.1, 0.8, 0.8],
                },
                {
                    "type": "text",
                    "text": "跨境流动",
                    "box": [7.6, 0.5, 1.4, 0.4],
                },
            ]
        }
        self.alignment = {
            "schema_version": "5.8",
            "skill_version": "5.8.4",
            "pages": {
                "S01": {
                    "design_draft_sha256": sha256(self.draft),
                    "authoring_bundle_sha256": sha256(self.bundle_path),
                    "reviewed": True,
                    "review_method": "visual_agent",
                    "display_text_policy": "blueprint_first_fact_guard",
                    "slide_text": {
                        "chapter": "三、洲际流动与AI人才分工",
                        "title": "洲际流动6,984人高于洲内流动4,447人",
                        "core_points": ["蓝图表达：洲际流动规模明显更高。"],
                        "source": "资料来源：测试报告",
                    },
                    "text_decisions": [
                        {
                            "role": "title",
                            "canonical": "洲际流动6,984人高于洲内流动4,447人",
                            "observed": "洲际流动6984人高于洲内流动44447人",
                            "selected": "洲际流动6,984人高于洲内流动4,447人",
                            "resolution": "fact_guard",
                        }
                    ],
                    "resolved_page_spec": resolved_spec,
                    "structure_modules": [
                        {
                            "module_id": "continent_flow",
                            "observed_expression": "paired_hbar_columns",
                            "data_labels": 6,
                        }
                    ],
                    "visuals": [
                        {
                            "asset_id": "S01_V01",
                            "kind": "pictogram",
                            "description": "世界地图科研节点",
                            "source_px": [70, 300, 170, 400],
                            "target_box_in": [0.1, 0.1, 0.8, 0.8],
                            "treatment": "crop",
                            "fallback": "native",
                        },
                        {
                            "asset_id": "S01_V02",
                            "kind": "arrow",
                            "description": "跨境箭头",
                            "treatment": "native",
                        },
                        {
                            "asset_id": "S01_V03",
                            "kind": "decoration",
                            "description": "低价值装饰点",
                            "treatment": "omit",
                        },
                    ],
                }
            },
        }
        (self.build / "blueprint_alignment.json").write_text(
            json.dumps(self.alignment, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_alignment_never_changes_or_regenerates_locked_blueprint(self):
        alignment = load_module(
            "v584_alignment_immutable",
            SKILL / "scripts" / "v584_blueprint_alignment.py",
        )
        before = self.draft.read_bytes()
        result = alignment.apply_project_alignment(self.project)
        manifest = read_json(self.build / "visual_manifest.json")
        self.assertTrue(result["ok"])
        self.assertEqual(before, self.draft.read_bytes())
        self.assertEqual(before, (self.blueprints / "S01.png").read_bytes())
        self.assertEqual(1, manifest["pages"]["S01"]["imagegen_attempt_count"])

    def test_blueprint_wording_is_selected_except_factual_correction(self):
        alignment = load_module(
            "v584_alignment_text",
            SKILL / "scripts" / "v584_blueprint_alignment.py",
        )
        alignment.apply_project_alignment(self.project)
        slides = read_json(self.build / "slides.json")
        benchmark = read_json(self.build / "blueprint_text_benchmark.json")
        self.assertEqual(
            "洲际流动6,984人高于洲内流动4,447人",
            slides[0]["title"],
        )
        self.assertEqual(
            "蓝图表达：洲际流动规模明显更高。",
            slides[0]["core_points"][0],
        )
        item = next(
            item
            for item in benchmark["pages"]["S01"]["items"]
            if item.get("role") == "title"
        )
        self.assertEqual(
            "洲际流动6984人高于洲内流动44447人",
            item["observed"],
        )
        self.assertEqual("fact_guard", item["resolution"])

    def test_missing_decision_is_not_fabricated_as_exact_blueprint_match(self):
        alignment = load_module(
            "v584_alignment_honest_benchmark",
            SKILL / "scripts" / "v584_blueprint_alignment.py",
        )

        alignment.apply_project_alignment(self.project)
        page = read_json(
            self.build / "blueprint_text_benchmark.json"
        )["pages"]["S01"]

        self.assertFalse(page["exact_match"])
        self.assertTrue(
            any(
                item["observed"] == "" and not item["match_blueprint"]
                for item in page["items"]
            )
        )

    def test_reviewed_visuals_feed_crop_manifest_and_page_assets(self):
        alignment = load_module(
            "v584_alignment_visuals",
            SKILL / "scripts" / "v584_blueprint_alignment.py",
        )
        alignment.apply_project_alignment(self.project)
        manifest = read_json(self.build / "visual_manifest.json")
        specs = read_json(self.build / "page_specs.json")
        slide = read_json(self.build / "slides.json")[0]
        page = manifest["pages"]["S01"]
        self.assertTrue(page["visual_reviewed"])
        self.assertEqual(3, page["observed_candidate_count"])
        self.assertEqual(
            {"crop", "native", "omit"},
            {item["treatment"] for item in page["visuals"]},
        )
        self.assertTrue(
            any(item["type"] == "asset" for item in specs["S01"]["elements"])
        )
        self.assertEqual("extract_declared", slide["visual_review"])
        self.assertEqual(1, len(slide["complex_visuals"]))

    def test_paired_column_chart_keeps_series_labels_values_and_net_annotations(self):
        alignment = load_module(
            "v584_alignment_chart",
            SKILL / "scripts" / "v584_blueprint_alignment.py",
        )
        alignment.apply_project_alignment(self.project)
        chart = next(
            item
            for item in read_json(self.build / "page_specs.json")["S01"]["elements"]
            if item["type"] == "grouped_hbar_chart"
        )
        self.assertEqual("paired_columns", chart["layout"])
        self.assertTrue(chart["show_data_labels"])
        self.assertEqual(
            ["流入", "流出"],
            [item["name"] for item in chart["series"]],
        )
        self.assertEqual(["+140", "+1", "-7"], chart["row_annotations"])

    def test_stale_alignment_is_the_single_new_completeness_blocker(self):
        alignment = load_module(
            "v584_alignment_stale",
            SKILL / "scripts" / "v584_blueprint_alignment.py",
        )
        payload = read_json(self.build / "blueprint_alignment.json")
        payload["pages"]["S01"]["design_draft_sha256"] = "0" * 64
        (self.build / "blueprint_alignment.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "BLUEPRINT_ALIGNMENT_STALE"):
            alignment.apply_project_alignment(self.project)

    def test_pipeline_materialization_consumes_alignment_without_user_gate(self):
        pipeline = load_module(
            "v584_pipeline_materialize",
            SKILL / "scripts" / "project_pipeline.py",
        )
        result = pipeline.materialize_project(self.project)
        slides = read_json(self.build / "slides.json")
        self.assertEqual("5.8.4", result["skill_version"])
        self.assertEqual(1, result["aligned_pages"])
        self.assertEqual(
            "蓝图表达：洲际流动规模明显更高。",
            slides[0]["core_points"][0],
        )

    def test_unchanged_alignment_is_reused_without_rematerializing(self):
        alignment = load_module(
            "v584_alignment_cache",
            SKILL / "scripts" / "v584_blueprint_alignment.py",
        )
        first = alignment.apply_project_alignment(self.project)
        second = alignment.apply_project_alignment(self.project)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])

    def test_pipeline_prebuild_requires_alignment_but_not_visual_perfection(self):
        pipeline = load_module(
            "v584_pipeline_gate",
            SKILL / "scripts" / "project_pipeline.py",
        )
        (self.build / "blueprint_alignment.json").unlink()
        with self.assertRaisesRegex(ValueError, "BLUEPRINT_ALIGNMENT_REQUIRED"):
            pipeline.prebuild_project(self.project)

    def test_runtime_template_implements_paired_columns_and_data_labels(self):
        source = (
            SKILL / "assets" / "direct_blueprint_generator_template.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def add_paired_hbar_columns", source)
        self.assertIn('element.get("layout") == "paired_columns"', source)
        self.assertIn("show_data_labels", source)
        self.assertIn("row_annotations", source)
        compile(source, "direct_blueprint_generator_template.py", "exec")

    def test_standard_grouped_chart_supports_series_legend_and_data_labels(self):
        source = (
            SKILL / "assets" / "direct_blueprint_generator_template.py"
        ).read_text(encoding="utf-8")
        self.assertIn('show_labels = bool(element.get("show_data_labels"))', source)
        self.assertIn('show_legend = bool(element.get("show_legend"))', source)
        self.assertGreaterEqual(source.count("_format_chart_value("), 3)

    def test_cropped_assets_use_the_page_element_body_box_for_placement(self):
        source = (
            SKILL / "assets" / "direct_blueprint_generator_template.py"
        ).read_text(encoding="utf-8")
        self.assertIn("target_box: list[float] | None = None", source)
        self.assertIn('target_box or crop_spec["target_box_in"]', source)
        self.assertIn("target_box = list(_element_box(element, body))", source)

    def test_asset_audit_translates_body_relative_target_boxes(self):
        audit = load_module(
            "v584_ppt_asset_audit",
            SKILL / "scripts" / "ppt_asset_audit.py",
        )
        core_bottom_in = 1.6
        body_top = core_bottom_in + 0.12
        target = [0.1, 0.2, 0.8, 0.6]
        manifest = {
            "pages": [
                {
                    "slide_id": "S01",
                    "core_bottom": core_bottom_in * 72,
                    "footer_top": 7.215 * 72,
                    "assets": {
                        "S01_V01": [
                            {
                                "left": (0.56 + target[0]) * 72,
                                "top": (body_top + target[1]) * 72,
                                "width": target[2] * 72,
                                "height": target[3] * 72,
                            }
                        ]
                    },
                }
            ]
        }
        crops = {
            "S01_V01": {
                "slide_id": "S01",
                "target_box_in": target,
                "target_coord_space": "body",
            }
        }
        report = {"assets": [{"asset_id": "S01_V01", "aspect_ratio": 4 / 3}]}
        self.assertTrue(audit.audit_manifest(manifest, crops, report)["ok"])

    def test_quality_report_records_v584_release_version(self):
        quality = load_module(
            "v584_quality",
            SKILL / "scripts" / "v582_quality.py",
        )
        report = quality.write_report(self.project, quality.summarize([], []))
        self.assertEqual("5.8.4", report["skill_version"])

    def test_documentation_limits_v584_to_the_post_blueprint_path(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        alignment_prompt = (
            SKILL / "prompts" / "blueprint_alignment_prompt.md"
        ).read_text(encoding="utf-8")
        imagegen_prompt = (
            SKILL / "prompts" / "imagegen_blueprint_prompt.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Standard Report PPT V5.8.4", skill)
        self.assertIn("blueprint_alignment.json", skill)
        self.assertIn("never regenerate", alignment_prompt.lower())
        self.assertIn("crop | native | omit", alignment_prompt)
        self.assertIn("V5.8.3", imagegen_prompt)
        self.assertNotIn("at most five", (skill + alignment_prompt).lower())


if __name__ == "__main__":
    unittest.main()
