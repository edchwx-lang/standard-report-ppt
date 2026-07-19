from __future__ import annotations

import importlib.util
import ast
import json
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V591PipelineTests(unittest.TestCase):
    def test_new_revision_is_accepted_without_new_schema(self):
        pipeline = load_module(
            "v591_pipeline",
            SKILL / "scripts" / "project_pipeline.py",
        )
        brief = {
            "schema_version": "5.9",
            "pipeline_revision": "5.9.1",
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "blueprint_engine": "builtin_imagegen",
            "platform_target": "auto",
            "source_files": ["C:/fixture/source.docx"],
        }
        self.assertEqual([], pipeline.validate_brief(brief))

    def test_v59_visual_audits_are_advisory(self):
        policy = load_module(
            "v591_policy",
            SKILL / "scripts" / "v591_contracts.py",
        )
        for revision in ("5.9.0", "5.9.1"):
            brief = {"schema_version": "5.9", "pipeline_revision": revision}
            self.assertEqual(
                "warning",
                policy.audit_policy(brief, "blueprint_fidelity"),
            )
            self.assertEqual(
                "warning",
                policy.audit_policy(brief, "ppt_asset_audit"),
            )

    def test_reconstruction_contract_is_blocking_only_for_v591(self):
        policy = load_module(
            "v591_contract_policy",
            SKILL / "scripts" / "v591_contracts.py",
        )
        self.assertEqual(
            "blocker",
            policy.audit_policy(
                {"schema_version": "5.9", "pipeline_revision": "5.9.1"},
                "reconstruction_contract",
            ),
        )
        self.assertEqual(
            "warning",
            policy.audit_policy(
                {"schema_version": "5.9", "pipeline_revision": "5.9.0"},
                "reconstruction_contract",
            ),
        )

    def test_windows_generator_embeds_contract_hashes(self):
        compiler = load_module(
            "v591_windows_compiler",
            SKILL / "scripts" / "project_compiler.py",
        )
        expected = {"visual_manifest_sha256": "a" * 64}
        source = compiler.compile_generator_source(
            (
                SKILL / "assets" / "direct_blueprint_generator_template.py"
            ).read_text(encoding="utf-8"),
            {
                "schema_version": "5.9",
                "pipeline_revision": "5.9.1",
                "requested_page_count": 1,
                "production_mode": "fast",
            },
            [{"slide_id": "S01"}],
            {"S01": {"elements": []}},
            {},
            {},
            SKILL / "assets" / "company_template.pptx",
            design_drafts={},
            contract_hashes=expected,
        )
        tree = ast.parse(source)
        assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "DECK_META"
                for target in node.targets
            )
        )
        self.assertEqual(expected, ast.literal_eval(assignment.value)["contract_hashes"])

    def test_quality_and_timing_report_v591_release(self):
        quality = load_module(
            "v591_quality",
            SKILL / "scripts" / "v582_quality.py",
        )
        timing = load_module(
            "v591_timing",
            SKILL / "scripts" / "v583_timing.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".build").mkdir()
            (root / "project_brief.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.9",
                        "pipeline_revision": "5.9.1",
                    }
                ),
                encoding="utf-8",
            )
            report = quality.write_report(root, quality.summarize([], []))
            timing.initialize_timing(root, preserve=False)
            timing_report = json.loads(
                (root / ".build" / "pipeline_timing.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual("5.9.1", report["skill_version"])
        self.assertEqual("5.9.1", timing_report["skill_version"])

if __name__ == "__main__":
    unittest.main()
