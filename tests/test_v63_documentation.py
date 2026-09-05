from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class V63DocumentationTests(unittest.TestCase):
    def test_skill_documents_visual_reverse_compilation_and_scope_boundary(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Standard Report PPT V6.3", text)
        self.assertIn("蓝图锁定后的解构路径", text)
        self.assertIn("五个母版占位符", text)
        self.assertIn("主体蓝图是视觉最高权威", text)
        self.assertIn("最多一次定向主体重构", text)
        self.assertIn("mac_native_render_unverified", text)

    def test_cross_platform_contract_names_shared_scene_artifacts(self):
        text = (ROOT / "references" / "cross_platform_backend_contract.md").read_text(
            encoding="utf-8"
        )

        for artifact in (
            "v63_visual_census.json",
            "v63_scene_graph.json",
            "v63_asset_ledger.json",
        ):
            self.assertIn(artifact, text)
        self.assertIn("Windows", text)
        self.assertIn("mac_native_render_unverified", text)

    def test_quality_policy_separates_structural_blockers_from_visual_warnings(self):
        text = (ROOT / "references" / "ppt_quality_check_rules.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("V6.3 hard structural blockers", text)
        self.assertIn("V6.3 ordinary visual warnings", text)
        self.assertIn("one targeted body refinement", text)


if __name__ == "__main__":
    unittest.main()
