from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V622DeconstructionPatchTests(unittest.TestCase):
    def test_prompt_guard_rejects_agent_added_visual_bans(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("V6.2.2 prompt-freedom", skill)
        self.assertIn("scripts/v622_prompt_guard.py", skill)
        guard = load("v622_guard_tests", ROOT / "scripts" / "v622_prompt_guard.py")
        blocked = guard.validate_prompt(
            "企业汇报蓝图。为便于解构，无图标照片人物地图logo，全部用可编辑矩形。"
        )
        self.assertFalse(blocked["ok"])
        self.assertIn(
            "V622_AGENT_VISUAL_BAN",
            {item["code"] for item in blocked["blockers"]},
        )
        self.assertTrue(
            guard.validate_prompt(
                "企业汇报蓝图。用产业链节点和园区实景作为视觉锚点，突出结论与证据。"
            )["ok"]
        )

    def test_deconstruct_and_bitmap_share_bundled_windows_render_environment(self):
        pipeline = load("v622_pipeline_tests", ROOT / "scripts" / "project_pipeline.py")
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / "dependencies" / "python" / "python.exe"
            node = python.parent.parent / "node" / "bin" / "node.exe"
            modules = python.parent.parent / "node" / "node_modules"
            python.parent.mkdir(parents=True)
            node.parent.mkdir(parents=True)
            modules.mkdir(parents=True)
            python.touch()
            node.touch()
            expected = pipeline._bitmap_render_environment(
                {"PATH": "existing"}, executable=python
            )
            self.assertEqual(
                expected,
                pipeline._windows_render_environment_for_mode(
                    "deconstruct", {"PATH": "existing"}, executable=python
                ),
            )
            self.assertEqual(
                expected,
                pipeline._windows_render_environment_for_mode(
                    "bitmap", {"PATH": "existing"}, executable=python
                ),
            )


if __name__ == "__main__":
    unittest.main()
