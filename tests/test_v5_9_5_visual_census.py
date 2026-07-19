from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
HASH = "a" * 64


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def page(**overrides):
    payload = {
        "pipeline_revision": "5.9.5",
        "visual_reviewed": True,
        "visual_review": "reviewed_inventory",
        "visual_census_result": "reviewed_inventory",
        "page_graphics_grade": "G1",
        "design_draft_sha256": HASH,
        "observed_candidate_count": 0,
        "candidate_count": 0,
        "visuals": [],
    }
    payload.update(overrides)
    return payload


class V595VisualCensusTests(unittest.TestCase):
    def setUp(self):
        self.contracts = load_module(
            "v595_visual_census",
            SKILL / "scripts" / "v591_reconstruction_contract.py",
        )

    def test_g1_through_g3_pages_cannot_claim_an_empty_inventory(self):
        for grade in ("G1", "G2", "G3"):
            with self.subTest(grade=grade):
                report = self.contracts.validate_visual_page(
                    "S01",
                    page(page_graphics_grade=grade),
                )
                self.assertIn(
                    "VISUAL_GRADE_REQUIRES_SUBJECTS",
                    {item["code"] for item in report["blockers"]},
                )

    def test_g0_requires_a_hash_bound_zero_subject_challenge(self):
        report = self.contracts.validate_visual_page(
            "S01",
            page(
                visual_review="reviewed_no_raster",
                visual_census_result="no_independent_subjects",
                page_graphics_grade="G0",
            ),
        )
        self.assertIn(
            "VISUAL_ZERO_CHALLENGE_REQUIRED",
            {item["code"] for item in report["blockers"]},
        )

    def test_g0_passes_only_when_every_presence_flag_is_false(self):
        flags = {
            name: False
            for name in (
                "icon",
                "pictogram",
                "logo",
                "map",
                "photo",
                "illustration",
                "device",
                "person",
                "product",
                "flag",
            )
        }
        report = self.contracts.validate_visual_page(
            "S01",
            page(
                visual_review="reviewed_no_raster",
                visual_census_result="no_independent_subjects",
                page_graphics_grade="G0",
                zero_subject_challenge={
                    "review_result": "reviewed_no_raster",
                    "presence_flags": flags,
                    "blueprint_sha256": HASH,
                    "zero_subject_reason": "text_chart_table_basic_geometry_only",
                },
            ),
        )
        self.assertEqual([], report["blockers"], report)

        flags["pictogram"] = True
        report = self.contracts.validate_visual_page(
            "S01",
            page(
                visual_review="reviewed_no_raster",
                visual_census_result="no_independent_subjects",
                page_graphics_grade="G0",
                zero_subject_challenge={
                    "review_result": "reviewed_no_raster",
                    "presence_flags": flags,
                    "blueprint_sha256": HASH,
                    "zero_subject_reason": "text_chart_table_basic_geometry_only",
                },
            ),
        )
        self.assertIn(
            "VISUAL_ZERO_CHALLENGE_CONTRADICTED",
            {item["code"] for item in report["blockers"]},
        )

    def test_retention_grade_a_cannot_be_omitted(self):
        visual = {
            "visual_id": "S01_MAP",
            "kind": "map",
            "description": "world flow map",
            "retention_grade": "A",
            "treatment": "omit",
            "omit_reason": "unreliable_crop",
        }
        report = self.contracts.validate_visual_page(
            "S01",
            page(
                page_graphics_grade="G2",
                observed_candidate_count=1,
                candidate_count=1,
                visuals=[visual],
            ),
        )
        self.assertIn(
            "VISUAL_GRADE_A_OMITTED",
            {item["code"] for item in report["blockers"]},
        )

    def test_retention_grade_b_omission_is_advisory(self):
        visual = {
            "visual_id": "S01_ICON",
            "kind": "pictogram",
            "description": "supporting pictogram",
            "retention_grade": "B",
            "treatment": "omit",
            "omit_reason": "non_evidence_decoration",
        }
        report = self.contracts.validate_visual_page(
            "S01",
            page(
                observed_candidate_count=1,
                candidate_count=1,
                visuals=[visual],
            ),
        )
        self.assertEqual([], report["blockers"], report)
        self.assertIn(
            "VISUAL_GRADE_B_OMITTED",
            {item["code"] for item in report["warnings"]},
        )

    def test_v594_zero_crop_compatibility_remains_valid(self):
        report = self.contracts.validate_visual_page(
            "S01",
            {
                "pipeline_revision": "5.9.4",
                "visual_reviewed": True,
                "visual_census_result": "no_independent_subjects",
                "observed_candidate_count": 0,
                "candidate_count": 0,
                "visuals": [],
            },
        )
        self.assertEqual([], report["blockers"], report)


if __name__ == "__main__":
    unittest.main()
