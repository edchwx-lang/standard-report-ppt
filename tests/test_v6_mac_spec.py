from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V6MacSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(
            "v6_mac_spec_under_test",
            ROOT / "scripts" / "v6_mac_spec.py",
        )

    def test_deconstruct_normalization_preserves_semantics_and_normalizes_values(self):
        page_specs = {
            "S01": {
                "elements": [
                    {
                        "type": "text",
                        "element_id": "S01_TEXT",
                        "module_id": "claim",
                        "body_box": [0.2, 0.3, 2.0, 0.5],
                        "text": "Editable",
                        "color": 0x112233,
                        "align": -4108,
                        "valign": 3,
                        "fill": "F0F1F2",
                        "line": "001122",
                        "margin_left": 0.08,
                        "margin_right": 0.06,
                        "margin_top": 0.03,
                        "margin_bottom": 0.02,
                        "data": [{"label": "A", "value": 2}],
                    },
                    {
                        "type": "rect",
                        "element_id": "S01_RECT",
                        "absolute_box": [2.5, 2.0, 1.0, 0.6],
                        "fill": "abcdef",
                        "line_color": "#001122",
                    },
                    {
                        "type": "asset",
                        "element_id": "S01_MAP",
                        "module_id": "map",
                        "asset_id": "A01",
                        "box": [5.0, 1.0, 2.0, 1.0],
                        "coord_space": "absolute",
                    },
                    {
                        "type": "combo_chart",
                        "element_id": "S01_COMBO",
                        "box": [7.2, 1.0, 2.0, 1.0],
                        "data": [
                            {"label": "2025", "value": 10, "line_value": 20},
                        ],
                    },
                ]
            }
        }
        normalized, report = self.module.normalize_mac_page_specs(
            page_specs, "deconstruct"
        )
        text, rect, asset, combo = normalized["S01"]["elements"]
        self.assertEqual("S01_TEXT", text["element_id"])
        self.assertEqual("claim", text["module_id"])
        self.assertEqual([{"label": "A", "value": 2}], text["data"])
        self.assertEqual([0.2, 0.3, 2.0, 0.5], text["box"])
        self.assertEqual("body", text["coord_space"])
        self.assertEqual("#332211", text["color"])
        self.assertEqual("center", text["align"])
        self.assertEqual("middle", text["valign"])
        self.assertEqual("#F0F1F2", text["fill"])
        self.assertEqual("#001122", text["line"])
        self.assertEqual("absolute", rect["coord_space"])
        self.assertEqual("#ABCDEF", rect["fill"])
        self.assertEqual("#001122", rect["line_color"])
        self.assertEqual("contain", asset["fit"])
        self.assertEqual(20, combo["data"][0]["line_value"])
        self.assertTrue(report["ok"])
        self.assertEqual("deconstruct", report["construction_mode"])

    def test_deconstruct_rejects_body_asset_and_unsupported_structure(self):
        for element in (
            {
                "type": "body_asset",
                "element_id": "S01_BODY_BITMAP",
                "asset_id": "S01_BODY_BITMAP",
            },
            {
                "type": "three_dimensional_scene",
                "element_id": "S01_SCENE",
                "box": [0, 0, 1, 1],
            },
            {
                "type": "asset",
                "element_id": "S01_UNBOUNDED",
                "asset_id": "A01",
            },
        ):
            with self.subTest(element=element["type"]):
                with self.assertRaisesRegex(
                    ValueError, "MAC_RECONSTRUCTION_UNSUPPORTED"
                ):
                    self.module.normalize_mac_page_specs(
                        {"S01": {"elements": [element]}}, "deconstruct"
                    )

    def test_element_ids_are_page_scoped_and_invalid_style_is_stable_error(self):
        repeated = {
            slide_id: {
                "elements": [
                    {
                        "type": "text",
                        "element_id": "TITLE",
                        "text": slide_id,
                        "box": [0, 0, 1, 1],
                    }
                ]
            }
            for slide_id in ("S01", "S02")
        }
        normalized, report = self.module.normalize_mac_page_specs(
            repeated, "deconstruct"
        )
        self.assertEqual(["S01", "S02"], list(normalized))
        self.assertTrue(report["ok"])
        repeated["S01"]["elements"][0]["color"] = "not-a-color"
        with self.assertRaisesRegex(ValueError, "MAC_RECONSTRUCTION_UNSUPPORTED"):
            self.module.normalize_mac_page_specs(repeated, "deconstruct")

    def test_style_contract_accepts_rendered_fields_and_rejects_ignored_style(self):
        valid = {
            "S01": {
                "elements": [
                    {
                        "type": "text_card",
                        "element_id": "CARD",
                        "box": [0, 0, 3, 1],
                        "title": "Finding",
                        "body": "Evidence",
                        "title_fill": "#112233",
                        "body_fill": "#F1F2F3",
                        "title_color": "#FF0000",
                        "body_color": "#008000",
                    },
                    {
                        "type": "metric_strip",
                        "element_id": "METRICS",
                        "box": [3, 0, 3, 1],
                        "metrics": [
                            {
                                "label": "Growth",
                                "value": "20%",
                                "value_color": "#123456",
                                "label_color": "#654321",
                            }
                        ],
                    },
                    {
                        "type": "flow",
                        "element_id": "FLOW",
                        "box": [0, 1.2, 6, 1],
                        "steps": [
                            {
                                "title": "Discover",
                                "body": "Evidence",
                                "detail": "Caveat",
                                "title_color": "#ABCDEF",
                                "body_color": "#234567",
                            },
                            {"title": "Decide", "body": "Action"},
                        ],
                    },
                    {
                        "type": "column_chart",
                        "element_id": "CHART",
                        "box": [6, 0, 3, 2],
                        "style": 12,
                        "data": [{"label": "A", "value": 1}],
                    },
                ]
            }
        }
        normalized, _ = self.module.normalize_mac_page_specs(
            valid, "deconstruct"
        )
        self.assertEqual(
            "#FF0000", normalized["S01"]["elements"][0]["title_color"]
        )
        self.assertEqual(
            "#123456",
            normalized["S01"]["elements"][1]["metrics"][0]["value_color"],
        )
        self.assertEqual(
            "#234567",
            normalized["S01"]["elements"][2]["steps"][0]["body_color"],
        )
        self.assertEqual(12, normalized["S01"]["elements"][3]["style"])

        invalid_elements = (
            {
                "type": "text",
                "element_id": "TEXT",
                "box": [0, 0, 2, 1],
                "text": "No silent style",
                "style": {"font": "ignored"},
            },
            {
                "type": "column_chart",
                "element_id": "CHART_TEXT_STYLE",
                "box": [0, 0, 2, 1],
                "style": "12",
                "data": [{"label": "A", "value": 1}],
            },
            {
                "type": "column_chart",
                "element_id": "CHART_RANGE",
                "box": [0, 0, 2, 1],
                "style": 99,
                "data": [{"label": "A", "value": 1}],
            },
            {
                "type": "metric_strip",
                "element_id": "METRIC_STYLE",
                "box": [0, 0, 2, 1],
                "metrics": [
                    {"label": "A", "value": 1, "style": "ignored"}
                ],
            },
            {
                "type": "flow",
                "element_id": "FLOW_STYLE",
                "box": [0, 0, 3, 1],
                "steps": [
                    {"title": "A", "body": "B", "style": "ignored"},
                    {"title": "C", "body": "D"},
                ],
            },
        )
        for element in invalid_elements:
            with self.subTest(element=element["element_id"]):
                with self.assertRaisesRegex(
                    ValueError, "MAC_RECONSTRUCTION_UNSUPPORTED"
                ):
                    self.module.normalize_mac_page_specs(
                        {"S01": {"elements": [element]}}, "deconstruct"
                    )

    def test_real_contract_payloads_are_normalized_and_malformed_payloads_block(self):
        valid = {
            "S01": {
                "elements": [
                    {
                        "type": "combo_chart",
                        "element_id": "COMBO",
                        "box": [0, 0, 3, 2],
                        "data": [
                            {"label": "2025", "value": 10, "line_value": 20},
                            {"label": "2026", "value": 12, "line_value": 18},
                        ],
                    },
                    {
                        "type": "flow",
                        "element_id": "FLOW",
                        "box": [0, 2, 6, 1],
                        "steps": [
                            {"title": "Discover", "body": "Evidence"},
                            {"label": "Decide", "detail": "Action"},
                        ],
                    },
                    {
                        "type": "matrix",
                        "element_id": "TABLE",
                        "box": [6, 0, 4, 2],
                        "headers": ["A", "B"],
                        "rows": [["x", "y"], ["m", "n"]],
                    },
                    {
                        "type": "metric_strip",
                        "element_id": "METRICS",
                        "box": [0, 3.1, 6, 0.8],
                        "metrics": [{"label": "Growth", "value": "20%"}],
                    },
                    {
                        "type": "text_card",
                        "element_id": "CARD",
                        "box": [6, 2.1, 4, 1.2],
                        "title": "Finding",
                        "body": "Evidence-backed conclusion",
                    },
                ]
            }
        }
        normalized, _ = self.module.normalize_mac_page_specs(
            valid, "deconstruct"
        )
        self.assertEqual(
            20,
            normalized["S01"]["elements"][0]["data"][0]["line_value"],
        )
        bad_elements = (
            {
                "type": "column_chart",
                "element_id": "BAD_CHART",
                "box": [0, 0, 2, 1],
                "data": [{"label": "A", "value": "not-numeric"}],
            },
            {
                "type": "combo_chart",
                "element_id": "BAD_COMBO",
                "box": [0, 0, 2, 1],
                "data": [{"label": "A", "value": 1}],
            },
            {
                "type": "flow",
                "element_id": "ONE_STEP",
                "box": [0, 0, 2, 1],
                "steps": [{"title": "Only"}],
            },
            {
                "type": "matrix",
                "element_id": "RAGGED",
                "box": [0, 0, 2, 1],
                "headers": ["A", "B"],
                "rows": [["x"]],
            },
            {
                "type": "text_card",
                "element_id": "EMPTY_CARD",
                "box": [0, 0, 2, 1],
                "title": "Finding",
            },
        )
        for element in bad_elements:
            with self.subTest(element=element["element_id"]):
                with self.assertRaisesRegex(
                    ValueError, "MAC_RECONSTRUCTION_UNSUPPORTED"
                ):
                    self.module.normalize_mac_page_specs(
                        {"S01": {"elements": [element]}}, "deconstruct"
                    )

    def test_asset_ids_and_invalid_construction_mode_are_blocked_early(self):
        for asset_id in ("../../outside", "..", "/absolute", r"C:\absolute"):
            element = {
                "type": "asset",
                "element_id": "ASSET",
                "asset_id": asset_id,
                "box": [0, 0, 2, 1],
            }
            with self.subTest(asset_id=asset_id):
                with self.assertRaisesRegex(
                    ValueError, "MAC_RECONSTRUCTION_UNSUPPORTED"
                ):
                    self.module.normalize_mac_page_specs(
                        {"S01": {"elements": [element]}}, "deconstruct"
                    )
        with tempfile.TemporaryDirectory(prefix="v6_mac_mode_") as directory:
            project = Path(directory)
            (project / ".build").mkdir()
            (project / "project_brief.json").write_text(
                json.dumps(
                    {
                        "schema_version": "6.0",
                        "pipeline_revision": "6.0.0",
                        "production_mode": "blueprint",
                        "construction_mode": "fast",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, "MAC_RECONSTRUCTION_UNSUPPORTED"
            ):
                self.module.materialize_mac_page_specs(project)

    def test_bitmap_accepts_exactly_one_runtime_body_asset_per_page(self):
        valid = {
            "S01": {
                "elements": [
                    {
                        "type": "body_asset",
                        "element_id": "S01_BODY_BITMAP",
                        "asset_id": "S01_BODY_BITMAP",
                        "fit": "contain",
                        "target": "runtime_body_box",
                    }
                ]
            }
        }
        normalized, report = self.module.normalize_mac_page_specs(valid, "bitmap")
        self.assertEqual(valid, normalized)
        self.assertTrue(report["ok"])
        for invalid in (
            {"S01": {"elements": []}},
            {
                "S01": {
                    "elements": valid["S01"]["elements"] + valid["S01"]["elements"]
                }
            },
            {
                "S01": {
                    "elements": [
                        {
                            "type": "text",
                            "element_id": "S01_TEXT",
                            "box": [0, 0, 1, 1],
                        }
                    ]
                }
            },
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    ValueError, "MAC_RECONSTRUCTION_UNSUPPORTED"
                ):
                    self.module.normalize_mac_page_specs(invalid, "bitmap")

    def test_materialize_reads_mode_specific_input_and_writes_report(self):
        with tempfile.TemporaryDirectory(prefix="v6_mac_spec_") as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            (project / "project_brief.json").write_text(
                json.dumps(
                    {
                        "schema_version": "6.0",
                        "pipeline_revision": "6.0.0",
                        "production_mode": "blueprint",
                        "construction_mode": "deconstruct",
                    }
                ),
                encoding="utf-8",
            )
            source = {
                "S01": {
                    "elements": [
                        {
                            "type": "text",
                            "element_id": "S01_TEXT",
                            "text": "Editable",
                            "box": [0.1, 0.2, 1.0, 0.4],
                            "color": "123456",
                        }
                    ]
                }
            }
            (build / "page_specs.json").write_text(
                json.dumps(source), encoding="utf-8"
            )
            report = self.module.materialize_mac_page_specs(project)
            output = json.loads(
                (build / "mac_page_specs.json").read_text(encoding="utf-8")
            )
            persisted = json.loads(
                (build / "mac_spec_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual("#123456", output["S01"]["elements"][0]["color"])
            self.assertEqual(report, persisted)
            self.assertEqual("mac_python_pptx_v2", report["builder_backend"])
            self.assertEqual("pass", report["status"])
            self.assertEqual(".build/page_specs.json", report["source_path"])
            self.assertEqual(
                sha256_file(build / "page_specs.json"),
                report["source_sha256"],
            )
            self.assertEqual(
                ".build/mac_page_specs.json",
                report["normalized_path"],
            )
            self.assertEqual(
                sha256_file(build / "mac_page_specs.json"),
                report["normalized_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
