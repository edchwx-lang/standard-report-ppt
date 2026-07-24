from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def brief(mode: str = "deconstruct") -> dict:
    return {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "construction_mode": mode,
    }


def composite_spec() -> tuple[dict, dict]:
    return (
        {
            "S01": {
                "elements": [
                    {"element_id": "COMPOSITE", "type": "asset", "asset_id": "COMPOSITE"}
                ],
                "reconstruction_contract": {
                    "module_bindings": [
                        {"module_id": "table", "element_ids": ["COMPOSITE"]},
                        {"module_id": "chart", "element_ids": ["COMPOSITE"]},
                    ],
                    "text_decisions": [{"selected": "Editable conclusion"}],
                },
            }
        },
        {"pages": {"S01": {"visuals": []}}},
    )


class V6DeconstructionTests(unittest.TestCase):
    def setUp(self):
        self.subject = load_module(
            "v6_deconstruction", ROOT / "scripts" / "v6_deconstruction.py"
        )

    def test_non_v6_or_bitmap_is_a_passing_noop(self):
        report = self.subject.validate_deconstruction_prebuild(
            {"schema_version": "5.9"}, {}, {}, "windows_com_v584"
        )
        self.assertTrue(report["ok"])
        self.assertEqual("pass", report["status"])
        self.assertEqual([], report["blockers"])

    def test_composite_body_asset_is_blocked_on_windows_and_mac(self):
        specs, alignment = composite_spec()
        for backend in ("windows_com_v584", "mac_python_pptx_v2"):
            with self.subTest(backend=backend):
                report = self.subject.validate_deconstruction_prebuild(
                    brief(), specs, alignment, backend
                )
                self.assertFalse(report["ok"])
                self.assertIn(
                    "DECONSTRUCTION_BODY_BITMAP_FORBIDDEN",
                    [item["code"] for item in report["blockers"]],
                )

    def test_body_asset_and_classic_skeleton_composite_are_blocked(self):
        specs = {
            "S01": {
                "elements": [
                    {"element_id": "BODY", "type": "body_asset"},
                    {"element_id": "COMPOSITE", "type": "asset"},
                ],
                "reconstruction_contract": {
                    "module_bindings": [{"module_id": "body", "element_ids": ["COMPOSITE"]}]
                },
            }
        }
        report = self.subject.validate_deconstruction_prebuild(
            brief(), specs, {"pages": {"S01": {}}}, "windows_com_v584"
        )
        codes = [item["code"] for item in report["blockers"]]
        self.assertIn("DECONSTRUCTION_BODY_BITMAP_FORBIDDEN", codes)

    def test_single_subject_pure_visual_map_can_use_a_large_asset(self):
        specs = {
            "S01": {
                "elements": [{"element_id": "MAP", "type": "asset", "asset_id": "MAP"}],
                "reconstruction_contract": {
                    "module_bindings": [{"module_id": "map", "element_ids": ["MAP"]}],
                    "text_decisions": [],
                },
            }
        }
        alignment = {
            "pages": {"S01": {"visuals": [{"asset_id": "MAP", "kind": "map"}]}}
        }
        report = self.subject.validate_deconstruction_prebuild(
            brief(), specs, alignment, "mac_python_pptx_v2"
        )
        self.assertTrue(report["ok"])
        self.assertEqual(["MAP"], report["allowed_large_visual_asset_ids"])

    def test_mac_rejects_unsupported_element_types(self):
        specs = {
            "S01": {
                "elements": [{"element_id": "X", "type": "unsupported_magic"}],
                "reconstruction_contract": {"module_bindings": [{"module_id": "x", "element_ids": ["X"]}]},
            }
        }
        report = self.subject.validate_deconstruction_prebuild(
            brief(), specs, {"pages": {"S01": {}}}, "mac_python_pptx_v2"
        )
        self.assertIn("MAC_RECONSTRUCTION_UNSUPPORTED", [item["code"] for item in report["blockers"]])


if __name__ == "__main__":
    unittest.main()
