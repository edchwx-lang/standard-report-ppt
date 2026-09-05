from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load():
    path = ROOT / "scripts" / "v63_visual_delta.py"
    spec = importlib.util.spec_from_file_location("v63_visual_delta_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_pipeline():
    path = ROOT / "scripts" / "project_pipeline.py"
    spec = importlib.util.spec_from_file_location("v63_stopping_pipeline_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V63StoppingPolicyTests(unittest.TestCase):
    def test_first_material_delta_allows_exactly_one_targeted_refinement(self):
        decision = load().evaluate_visual_delta(
            build_attempt=1,
            structural_ok=True,
            fidelity_report={
                "passed": False,
                "failed_slide_ids": ["S01"],
                "pages": [{"slide_id": "S01", "score": 0.42, "layout_score": 0.35, "ink_mass_ratio": 0.7}],
            },
        )

        self.assertEqual("targeted_refinement", decision["action"])
        self.assertTrue(decision["refinement_allowed"])
        self.assertFalse(decision["delivery_blocked"])

    def test_second_structurally_valid_build_delivers_with_warnings(self):
        decision = load().evaluate_visual_delta(
            build_attempt=2,
            structural_ok=True,
            fidelity_report={
                "passed": False,
                "failed_slide_ids": ["S01"],
                "pages": [{"slide_id": "S01", "score": 0.43, "layout_score": 0.36, "ink_mass_ratio": 0.72}],
            },
        )

        self.assertEqual("deliver_with_warnings", decision["action"])
        self.assertFalse(decision["refinement_allowed"])
        self.assertFalse(decision["delivery_blocked"])

    def test_passed_comparison_delivers_without_refinement(self):
        decision = load().evaluate_visual_delta(
            build_attempt=1,
            structural_ok=True,
            fidelity_report={"passed": True, "failed_slide_ids": [], "pages": []},
        )

        self.assertEqual("deliver", decision["action"])
        self.assertEqual([], decision["warnings"])

    def test_structural_failure_remains_a_hard_blocker(self):
        decision = load().evaluate_visual_delta(
            build_attempt=2,
            structural_ok=False,
            fidelity_report={"passed": True, "failed_slide_ids": [], "pages": []},
        )

        self.assertEqual("block", decision["action"])
        self.assertTrue(decision["delivery_blocked"])

    def test_refinement_contract_allows_scene_changes_but_not_blueprint_changes(self):
        pipeline = load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".build").mkdir()
            (project / "blueprints").mkdir()
            (project / "project_brief.json").write_text("{}", encoding="utf-8")
            (project / ".build" / "slides.json").write_text("[]", encoding="utf-8")
            (project / ".build" / "formal_blueprint_manifest.json").write_text("{}", encoding="utf-8")
            (project / ".build" / "v63_visual_census.json").write_text("{}", encoding="utf-8")
            (project / ".build" / "v63_scene_graph.json").write_text("{}", encoding="utf-8")
            blueprint = project / "blueprints" / "S01.png"
            blueprint.write_bytes(b"locked")
            snapshot = pipeline._v63_refinement_contract_snapshot(project)
            (project / ".build" / "v63_scene_graph.json").write_text('{"changed": true}', encoding="utf-8")
            pipeline._assert_v63_refinement_contract_unchanged(project, snapshot)
            blueprint.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "blueprints/S01.png"):
                pipeline._assert_v63_refinement_contract_unchanged(project, snapshot)

    def test_catastrophic_repair_uses_v63_snapshot_and_allows_scene_change(self):
        pipeline = load_pipeline()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".build").mkdir()
            (project / "blueprints").mkdir()
            (project / "project_brief.json").write_text("{}", encoding="utf-8")
            (project / ".build" / "slides.json").write_text("[]", encoding="utf-8")
            (project / ".build" / "formal_blueprint_manifest.json").write_text("{}", encoding="utf-8")
            (project / ".build" / "v63_visual_census.json").write_text("{}", encoding="utf-8")
            (project / ".build" / "v63_scene_graph.json").write_text("{}", encoding="utf-8")
            blueprint = project / "blueprints" / "S01.png"
            blueprint.write_bytes(b"locked")
            snapshot = pipeline._v63_refinement_contract_snapshot(project)
            (project / ".build" / "v63_scene_graph.json").write_text(
                '{"changed": true}', encoding="utf-8"
            )
            previous = {
                "attempt_count": 1,
                "status": "catastrophic_failed",
                "repair_contract_snapshot": snapshot,
            }

            pipeline._assert_v6_repair_inputs_unchanged(
                project,
                construction_mode="deconstruct",
                previous=previous,
                uses_v63=True,
            )


if __name__ == "__main__":
    unittest.main()
