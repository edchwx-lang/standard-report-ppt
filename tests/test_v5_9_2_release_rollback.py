from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
REMOVED_REVISION = "5.9." + "3"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V592ReleaseRollbackTests(unittest.TestCase):
    def test_v596_is_the_latest_and_removed_revision_is_rejected(self):
        pipeline = load_module(
            "v592_release_pipeline",
            SKILL / "scripts" / "project_pipeline.py",
        )
        removed_brief = {
            "schema_version": "5.9",
            "pipeline_revision": REMOVED_REVISION,
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "blueprint_engine": "builtin_imagegen",
            "platform_target": "auto",
            "source_files": ["C:/fixture/source.docx"],
        }
        v595_brief = {
            **removed_brief,
            "pipeline_revision": "5.9.5",
        }
        v596_brief = {
            **removed_brief,
            "pipeline_revision": "5.9.6",
        }

        self.assertEqual("5.9.6", pipeline.LATEST_SKILL_VERSION)
        self.assertTrue(pipeline.validate_brief(removed_brief))
        self.assertEqual([], pipeline.validate_brief(v595_brief))
        self.assertEqual([], pipeline.validate_brief(v596_brief))

    def test_removed_revision_is_absent_from_production_contracts(self):
        paths = [
            SKILL / "SKILL.md",
            *sorted((SKILL / "prompts").glob("*.md")),
            *sorted((SKILL / "references").glob("*.md")),
            *sorted((SKILL / "scripts").glob("*.py")),
            *sorted((SKILL / "assets").glob("*.py")),
        ]
        offenders = [
            path.relative_to(SKILL).as_posix()
            for path in paths
            if REMOVED_REVISION in path.read_text(encoding="utf-8")
        ]

        self.assertEqual([], offenders)

    def test_imagegen_prompt_keeps_visual_freedom_without_v593_contract(self):
        prompt = (
            SKILL / "prompts" / "imagegen_blueprint_prompt.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(prompt.lower().split())

        self.assertIn("icons, people, devices, products, maps, illustrations", normalized)
        self.assertNotIn("expected_treatment", normalized)
        self.assertNotIn(REMOVED_REVISION, normalized)


if __name__ == "__main__":
    unittest.main()
