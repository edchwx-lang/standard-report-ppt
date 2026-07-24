from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
                        "data": [{"label": "A", "value": 2}],
                    },
                    {
                        "type": "rect",
                        "element_id": "S01_RECT",
                        "absolute_box": [2.5, 2.0, 1.0, 0.6],
                        "fill": "abcdef",
                        "line_color": "#001122",
                        "vertical_alignment": 3,
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
                            {"label": "2025", "column": 10, "line": 20},
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
        self.assertEqual("absolute", rect["coord_space"])
        self.assertEqual("#ABCDEF", rect["fill"])
        self.assertEqual("#001122", rect["line_color"])
        self.assertEqual("middle", rect["vertical_alignment"])
        self.assertEqual("contain", asset["fit"])
        self.assertEqual(20, combo["data"][0]["line"])
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


if __name__ == "__main__":
    unittest.main()
