from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V596 = importlib.util.spec_from_file_location(
    "v596_boundary_reference", ROOT / "tests" / "test_v5_9_6_boundary.py"
)
MODULE = importlib.util.module_from_spec(V596)
assert V596.loader is not None
V596.loader.exec_module(MODULE)


class V6BoundaryTests(unittest.TestCase):
    def test_frozen_pre_blueprint_files_remain_byte_identical(self):
        actual = {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in MODULE.FROZEN_SHA256
        }
        self.assertEqual(MODULE.FROZEN_SHA256, actual)

    def test_gate_copy_and_rc_version_are_documented(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Standard Report PPT V6.0.0-rc1", skill)
        self.assertIn(
            "解构模式（较慢）：逐页拆解蓝图并重建为可编辑 PPT；复杂非原生视觉可保留为局部位图。",
            skill,
        )

    def test_v6_intake_has_only_the_construction_mode_gate(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertEqual(1, skill.count("### Gate 1 — construction mode"))
        self.assertNotIn("### Gate 1 — production mode", skill)
        self.assertNotIn("1. `ImageGen 蓝图还原（默认推荐）`", skill)
        self.assertNotIn("2. `快速生成`", skill)
        self.assertNotIn(
            "If ImageGen is unavailable, ask whether to switch to fast mode or stop.",
            skill,
        )
        self.assertIn("`解构 / 可编辑 / 1`", skill)
        self.assertIn("`位图 / 快速位图 / 2`", skill)

    def test_v6_preflight_lists_new_review_resources(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        source = (ROOT / "scripts" / "project_pipeline.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('skill_dir / "prompts" / "deconstruction_alignment_prompt.md"', source)
        self.assertIn('skill_dir / "prompts" / "bitmap_alignment_prompt.md"', source)
        self.assertIn('"v596_visual_review.py"', source)
        self.assertIn(
            "位图模式（较快）：章节、标题、核心判断、来源和页码可编辑；主体蓝图裁切后作为不可编辑图片放入。",
            skill,
        )

    def test_post_lock_cache_is_mode_isolated_but_upstream_is_shared(self):
        spec = importlib.util.spec_from_file_location(
            "v6_contracts_boundary", ROOT / "scripts" / "v6_contracts.py"
        )
        contracts = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(contracts)
        base = {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "requested_page_count": 9,
            "production_mode": "blueprint",
            "blueprint_engine": "builtin_imagegen",
            "platform_target": "auto",
            "source_files": ["C:/source.docx"],
        }
        deconstruct = dict(base, construction_mode="deconstruct")
        bitmap = dict(base, construction_mode="bitmap")
        self.assertEqual(
            contracts.upstream_cache_payload(deconstruct),
            contracts.upstream_cache_payload(bitmap),
        )
        self.assertNotEqual(
            contracts.post_lock_cache_payload(deconstruct, "windows_com_v584"),
            contracts.post_lock_cache_payload(bitmap, "windows_com_v584"),
        )

    def test_nine_page_brief_preserves_requested_count(self):
        brief = json.loads(
            json.dumps(
                {
                    "schema_version": "6.0",
                    "pipeline_revision": "6.0.0",
                    "requested_page_count": 9,
                    "production_mode": "blueprint",
                    "construction_mode": "deconstruct",
                    "blueprint_engine": "builtin_imagegen",
                    "platform_target": "auto",
                    "source_files": ["C:/source.docx"],
                }
            )
        )
        self.assertEqual(9, brief["requested_page_count"])
        spec = importlib.util.spec_from_file_location(
            "v6_batch_pipeline", ROOT / "scripts" / "project_pipeline.py"
        )
        pipeline = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(pipeline)
        self.assertEqual(
            [
                ["S01", "S02", "S03", "S04", "S05"],
                ["S06", "S07", "S08", "S09"],
            ],
            pipeline.v6_page_batches(9),
        )


if __name__ == "__main__":
    unittest.main()
