from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKELETON_ROLES = {"chapter", "title", "core_point", "source", "page_number"}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def brief() -> dict:
    return {"schema_version": "6.0", "pipeline_revision": "6.0.0", "construction_mode": "deconstruct"}


def alignment(bindings, *, decisions=None, visuals=None, modules=None) -> dict:
    return {"pages": {"S01": {
        "reconstruction_contract": {"module_bindings": bindings},
        "text_decisions": decisions or [],
        "visuals": visuals or [],
        "structure_modules": modules or [],
    }}}


class V6DeconstructionTests(unittest.TestCase):
    def setUp(self):
        self.subject = load_module("v6_deconstruction", ROOT / "scripts" / "v6_deconstruction.py")

    def test_non_v6_is_a_passing_noop(self):
        report = self.subject.validate_deconstruction_prebuild({"schema_version": "5.9"}, {}, {}, "windows_com_v584")
        self.assertTrue(report["ok"])

    def test_real_alignment_contract_blocks_composite_for_both_backends(self):
        specs = {"S01": {"elements": [{"element_id": "COMPOSITE", "asset_id": "COMPOSITE", "type": "asset"}]}}
        reviewed = alignment(
            [{"module_id": "table", "element_ids": ["COMPOSITE"]}, {"module_id": "chart", "element_ids": ["COMPOSITE"]}],
            decisions=[{"role": "body", "selected": "Editable body conclusion"}],
        )
        for backend in ("windows_com_v584", "mac_python_pptx_v2"):
            with self.subTest(backend=backend):
                report = self.subject.validate_deconstruction_prebuild(brief(), specs, reviewed, backend)
                self.assertIn("DECONSTRUCTION_BODY_BITMAP_FORBIDDEN", [item["code"] for item in report["blockers"]])

    def test_pure_map_allows_only_skeleton_text_decisions(self):
        specs = {"S01": {"elements": [{"element_id": "MAP", "asset_id": "MAP_ASSET", "type": "asset"}, {"element_id": "TEXT", "type": "text"}]}}
        skeleton = [{"role": role, "selected": role} for role in SKELETON_ROLES]
        reviewed = alignment(
            [{"module_id": "map", "element_ids": ["MAP"]}, {"module_id": "text", "element_ids": ["TEXT"]}], decisions=skeleton + [{"module_id": "text", "role": "body", "selected": "Body copy"}],
            visuals=[{"asset_id": "MAP_ASSET", "kind": "map"}],
            modules=[{"module_id": "map", "module_kind": "pure_visual", "contains_editable_text": False}, {"module_id": "text", "module_kind": "text", "contains_editable_text": True}],
        )
        report = self.subject.validate_deconstruction_prebuild(brief(), specs, reviewed, "mac_python_pptx_v2")
        self.assertTrue(report["ok"])
        self.assertEqual({"S01": ["MAP_ASSET"]}, report["allowed_large_visual_assets_by_page"])
        self.assertNotIn("allowed_large_visual_asset_ids", report)
        reviewed["pages"]["S01"]["text_decisions"].append({"module_id": "map", "role": "body", "selected": "Map label"})
        self.assertFalse(self.subject.validate_deconstruction_prebuild(brief(), specs, reviewed, "mac_python_pptx_v2")["ok"])

    def test_asset_only_chart_and_missing_module_semantics_are_blocked(self):
        # module_kind/contains_editable_text are emitted by the V6 post-blueprint
        # deconstruction prompt; no frozen pre-blueprint contract is changed.
        specs = {"S01": {"elements": [{"element_id": "CHART_IMAGE", "asset_id": "A", "type": "asset"}]}}
        chart = alignment([{"module_id": "chart", "element_ids": ["CHART_IMAGE"]}], visuals=[{"asset_id": "A", "kind": "map"}], modules=[{"module_id": "chart", "module_kind": "chart", "contains_editable_text": False}])
        self.assertFalse(self.subject.validate_deconstruction_prebuild(brief(), specs, chart, "windows_com_v584")["ok"])
        missing = alignment([{"module_id": "chart", "element_ids": ["CHART_IMAGE"]}], visuals=[{"asset_id": "A", "kind": "map"}])
        self.assertFalse(self.subject.validate_deconstruction_prebuild(brief(), specs, missing, "windows_com_v584")["ok"])

    def test_body_asset_and_unsupported_mac_type_are_blocked(self):
        specs = {"S01": {"elements": [{"element_id": "BODY", "type": "body_asset"}, {"element_id": "X", "type": "magic"}]}}
        report = self.subject.validate_deconstruction_prebuild(brief(), specs, alignment([]), "mac_python_pptx_v2")
        self.assertIn("DECONSTRUCTION_BODY_BITMAP_FORBIDDEN", [item["code"] for item in report["blockers"]])
        self.assertIn("MAC_RECONSTRUCTION_UNSUPPORTED", [item["code"] for item in report["blockers"]])


if __name__ == "__main__":
    unittest.main()
