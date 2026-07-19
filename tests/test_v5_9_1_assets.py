from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V591AssetCensusTests(unittest.TestCase):
    def setUp(self):
        self.contracts = load_module(
            "v591_visual_contracts",
            SKILL / "scripts" / "v591_reconstruction_contract.py",
        )

    def test_generic_native_analytical_element_is_forbidden(self):
        report = self.contracts.validate_visual_page(
            "S03",
            {
                "visual_reviewed": True,
                "observed_candidate_count": 1,
                "candidate_count": 1,
                "visuals": [
                    {
                        "visual_id": "S03_V01",
                        "kind": "native_analytical_element",
                        "description": "native analytical placeholder",
                        "treatment": "native",
                        "element_id": "S03_E01",
                        "rebuild_recipe": "basic_shape",
                    }
                ],
            },
        )
        self.assertIn(
            "VISUAL_KIND_UNSUPPORTED",
            {item["code"] for item in report["blockers"]},
        )

    def test_zero_crop_page_can_have_native_and_omitted_subjects(self):
        report = self.contracts.validate_visual_page(
            "S03",
            {
                "visual_reviewed": True,
                "observed_candidate_count": 2,
                "candidate_count": 2,
                "visuals": [
                    {
                        "visual_id": "V01",
                        "kind": "arrow",
                        "description": "direction arrow",
                        "treatment": "native",
                        "element_id": "E01",
                        "rebuild_recipe": "line_arrow",
                    },
                    {
                        "visual_id": "V02",
                        "kind": "decoration",
                        "description": "decorative mark",
                        "treatment": "omit",
                        "omit_reason": "non_evidence_decoration",
                    },
                ],
            },
        )
        self.assertEqual([], report["blockers"])

    def test_true_zero_subject_page_requires_explicit_census_result(self):
        incomplete = self.contracts.validate_visual_page(
            "S01",
            {
                "visual_reviewed": True,
                "observed_candidate_count": 0,
                "candidate_count": 0,
                "visuals": [],
            },
        )
        complete = self.contracts.validate_visual_page(
            "S01",
            {
                "visual_reviewed": True,
                "visual_census_result": "no_independent_subjects",
                "observed_candidate_count": 0,
                "candidate_count": 0,
                "visuals": [],
            },
        )
        self.assertTrue(incomplete["blockers"])
        self.assertEqual([], complete["blockers"])

    def test_crop_requires_source_and_target_geometry(self):
        report = self.contracts.validate_visual_page(
            "S03",
            {
                "visual_reviewed": True,
                "observed_candidate_count": 1,
                "candidate_count": 1,
                "visuals": [
                    {
                        "visual_id": "S03_TRAIN",
                        "asset_id": "S03_TRAIN",
                        "kind": "pictogram",
                        "description": "train",
                        "treatment": "crop",
                    }
                ],
            },
        )
        self.assertIn(
            "VISUAL_CROP_GEOMETRY_REQUIRED",
            {item["code"] for item in report["blockers"]},
        )

    def test_compiler_slide_fields_preserve_reviewed_inventory(self):
        legacy_contracts = load_module(
            "v591_legacy_visual_adapter",
            SKILL / "scripts" / "v56_contracts.py",
        )
        fields = legacy_contracts.visual_page_to_slide_fields(
            {
                "design_draft_sha256": "a" * 64,
                "visuals": [
                    {
                        "visual_id": "S03_TRAIN",
                        "asset_id": "S03_TRAIN",
                        "kind": "pictogram",
                        "description": "train",
                        "disposition": "crop",
                    }
                ],
            },
            pipeline_revision="5.9.1",
        )
        self.assertEqual("reviewed_inventory", fields["visual_review"])
        self.assertEqual(1, len(fields["complex_visuals"]))

    def test_asset_audit_does_not_allow_crop_census_to_pass_as_zero_zero(self):
        audit = load_module(
            "v591_asset_audit",
            SKILL / "scripts" / "ppt_asset_audit.py",
        )
        report = audit.audit_manifest(
            {"pages": []},
            {},
            {"assets": []},
            census_crop_ids={"S03_TRAIN"},
        )
        self.assertFalse(report["complete_inventory"])
        self.assertTrue(
            any("S03_TRAIN" in error for error in report["errors"]),
            report,
        )


if __name__ == "__main__":
    unittest.main()
