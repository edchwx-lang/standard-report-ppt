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
        self.reconstruction = load_module(
            "v591_reconstruction_contract_for_v6",
            ROOT / "scripts" / "v591_reconstruction_contract.py",
        )

    def _zero_visual_contract(self) -> tuple[list[dict], dict, dict]:
        slides = [{"slide_id": "S01"}]
        specs = {
            "S01": {
                "elements": [
                    {
                        "element_id": "S01_E01",
                        "type": "rect",
                        "box": [0.5, 0.5, 2.0, 1.0],
                    }
                ]
            }
        }
        reviewed = {
            "pages": {
                "S01": {
                    "reviewed": True,
                    "visual_review": "reviewed_inventory",
                    "visual_census_result": "no_independent_subjects",
                    "page_graphics_grade": "G2",
                    "design_draft_sha256": "a" * 64,
                    "observed_candidate_count": 0,
                    "candidate_count": 0,
                    "visuals": [],
                    "structure_modules": [{"module_id": "body"}],
                    "reconstruction_contract": {
                        "supported_backends": [
                            "windows_com_v584",
                            "mac_python_pptx_v2",
                        ],
                        "module_bindings": [
                            {
                                "module_id": "body",
                                "element_ids": ["S01_E01"],
                            }
                        ],
                        "visual_subject_count": 0,
                    },
                }
            }
        }
        return slides, specs, reviewed

    def test_v6_windows_deconstruct_inherits_v596_visual_census_gate(self):
        slides, specs, reviewed = self._zero_visual_contract()
        report = self.reconstruction.validate_reconstruction_contract(
            brief(),
            slides,
            specs,
            reviewed,
            "windows_com_v584",
        )
        codes = {item["code"] for item in report["blockers"]}
        self.assertIn("VISUAL_GRADE_REQUIRES_SUBJECTS", codes)
        self.assertIn("VISUAL_REVIEW_TILES_REQUIRED", codes)

    def test_v6_mac_deconstruct_inherits_v596_visual_census_gate(self):
        slides, specs, reviewed = self._zero_visual_contract()
        report = self.reconstruction.validate_reconstruction_contract(
            brief(),
            slides,
            specs,
            reviewed,
            "mac_python_pptx_v2",
        )
        codes = {item["code"] for item in report["blockers"]}
        self.assertIn("VISUAL_GRADE_REQUIRES_SUBJECTS", codes)
        self.assertIn("VISUAL_REVIEW_TILES_REQUIRED", codes)

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

    def test_unbound_asset_and_missing_binding_element_are_blocked(self):
        specs = {"S01": {"elements": [{"element_id": "COMPOSITE", "asset_id": "A", "type": "asset"}, {"element_id": "DUMMY", "type": "rect"}]}}
        unbound = alignment([{"module_id": "dummy", "element_ids": ["DUMMY"]}], modules=[{"module_id": "dummy", "module_kind": "geometry", "contains_editable_text": False}])
        report = self.subject.validate_deconstruction_prebuild(brief(), specs, unbound, "windows_com_v584")
        self.assertFalse(report["ok"])
        self.assertTrue(any("asset element COMPOSITE must have exactly one valid module binding" in item["message"] for item in report["blockers"]))
        missing = alignment([{"module_id": "map", "element_ids": ["MISSING"]}])
        report = self.subject.validate_deconstruction_prebuild(brief(), specs, missing, "windows_com_v584")
        self.assertTrue(any("references missing element MISSING" in item["message"] for item in report["blockers"]))

    def test_page_specs_and_alignment_page_sets_must_match(self):
        report = self.subject.validate_deconstruction_prebuild(brief(), {"S01": {"elements": []}}, {"pages": {"S02": {}}}, "windows_com_v584")
        self.assertFalse(report["ok"])
        self.assertTrue(any("page spec ids must exactly equal alignment page ids" in item["message"] for item in report["blockers"]))

    def test_both_deconstruct_backends_reject_composite_crop_mislabeled_as_pure_visual(self):
        specs = {
            "S01": {
                "elements": [
                    {
                        "element_id": "PANEL",
                        "asset_id": "PANEL_ASSET",
                        "type": "asset",
                    }
                ]
            }
        }
        reviewed = alignment(
            [{"module_id": "timeline", "element_ids": ["PANEL"]}],
            visuals=[
                {
                    "visual_id": "S01_V01",
                    "asset_id": "PANEL_ASSET",
                    "kind": "illustration",
                    "treatment": "crop",
                    "source_px": [35, 320, 1630, 655],
                    "target_box_in": [0.0, 0.05, 12.2, 2.35],
                }
            ],
            modules=[
                {
                    "module_id": "timeline",
                    "module_kind": "pure_visual",
                    "contains_editable_text": False,
                }
            ],
        )

        for backend in ("windows_com_v584", "mac_python_pptx_v2"):
            with self.subTest(backend=backend):
                report = self.subject.validate_deconstruction_prebuild(
                    brief(), specs, reviewed, backend
                )
                self.assertFalse(report["ok"])
                self.assertIn(
                    "DECONSTRUCTION_NON_ATOMIC_CROP_FORBIDDEN",
                    {item["code"] for item in report["blockers"]},
                )

    def test_both_deconstruct_backends_require_native_visual_census_for_flow(self):
        specs = {
            "S01": {
                "elements": [
                    {
                        "element_id": "FLOW",
                        "type": "flow",
                    }
                ]
            }
        }
        reviewed = alignment(
            [{"module_id": "flow", "element_ids": ["FLOW"]}],
            modules=[
                {
                    "module_id": "flow",
                    "module_kind": "flow",
                    "contains_editable_text": True,
                }
            ],
        )

        for backend in ("windows_com_v584", "mac_python_pptx_v2"):
            with self.subTest(backend=backend):
                report = self.subject.validate_deconstruction_prebuild(
                    brief(), specs, reviewed, backend
                )
                self.assertFalse(report["ok"])
                self.assertTrue(
                    any(
                        "native visual census" in item["message"]
                        for item in report["blockers"]
                    )
                )

    def test_both_deconstruct_backends_accept_atomic_icon_crop_and_reviewed_native_flow(self):
        specs = {
            "S01": {
                "elements": [
                    {
                        "element_id": "ICON",
                        "asset_id": "ICON_ASSET",
                        "type": "asset",
                    },
                    {
                        "element_id": "FLOW",
                        "type": "flow",
                    },
                ]
            }
        }
        reviewed = alignment(
            [
                {
                    "module_id": "flow",
                    "element_ids": ["ICON", "FLOW"],
                }
            ],
            visuals=[
                {
                    "visual_id": "S01_V01",
                    "asset_id": "ICON_ASSET",
                    "kind": "icon",
                    "treatment": "crop",
                    "source_px": [120, 520, 210, 610],
                    "target_box_in": [0.4, 2.8, 0.6, 0.6],
                    "crop_scope": "independent_subject",
                    "subject_count": 1,
                    "tight_crop": True,
                    "contains_editable_text": False,
                    "contains_native_geometry": False,
                },
                {
                    "visual_id": "S01_V02",
                    "element_id": "FLOW",
                    "kind": "line",
                    "treatment": "native",
                    "source_px": [220, 540, 1450, 590],
                    "target_box_in": [1.1, 2.9, 10.3, 0.3],
                    "rebuild_recipe": "line_arrow",
                },
            ],
            modules=[
                {
                    "module_id": "flow",
                    "module_kind": "mixed",
                    "contains_editable_text": True,
                }
            ],
        )

        for backend in ("windows_com_v584", "mac_python_pptx_v2"):
            with self.subTest(backend=backend):
                report = self.subject.validate_deconstruction_prebuild(
                    brief(), specs, reviewed, backend
                )
                self.assertTrue(report["ok"], report["blockers"])


if __name__ == "__main__":
    unittest.main()
