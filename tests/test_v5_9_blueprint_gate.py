from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V59BlueprintGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        build = self.project / ".build"
        build.mkdir()
        (self.project / "project_brief.json").write_text(json.dumps({
            "schema_version": "5.9", "pipeline_revision": "5.9.0",
            "requested_page_count": 1, "production_mode": "blueprint",
            "blueprint_engine": "builtin_imagegen", "platform_target": "auto",
            "source_files": ["/tmp/source.docx"],
        }), encoding="utf-8")
        (build / "page_specs.json").write_text(json.dumps({"S01": {"elements": []}}), encoding="utf-8")
        self.source = self.project / "source.png"
        Image.new("RGB", (1600, 900), "white").save(self.source)
        self.gate = load_module("v59_gate", SKILL / "scripts" / "v59_blueprint_gate.py")

    def tearDown(self):
        self.temporary.cleanup()

    def test_record_artifact_locks_pair_and_manifest(self):
        record = self.gate.record_artifact(self.project, "S01", self.source, transport_attempt_count=1)
        draft = self.project / ".build" / "design_drafts" / "S01.png"
        formal = self.project / "blueprints" / "S01.png"
        self.assertEqual(draft.read_bytes(), formal.read_bytes())
        manifest = json.loads((self.project / ".build" / "visual_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(record["artifact_sha256"], manifest["pages"]["S01"]["design_draft_sha256"])
        Image.new("RGB", (1600, 900), "blue").save(self.source)
        with self.assertRaisesRegex(ValueError, "already locked"):
            self.gate.record_artifact(self.project, "S01", self.source, transport_attempt_count=2)

    def test_gate_requires_reviewed_alignment_consumed_by_page_specs(self):
        record = self.gate.record_artifact(self.project, "S01", self.source, transport_attempt_count=1)
        self.assertFalse(self.gate.diagnose_blueprint_gate(self.project)["ok"])
        (self.project / ".build" / "blueprint_alignment.json").write_text(json.dumps({
            "schema_version": "5.9",
            "pages": {"S01": {
                "reviewed": True,
                "design_draft_sha256": record["artifact_sha256"],
                "resolved_page_spec": {"elements": []},
            }},
        }), encoding="utf-8")
        self.assertTrue(self.gate.assert_blueprint_gate(self.project)["ok"])

    def test_second_no_artifact_failure_stops_retry(self):
        first = self.gate.record_failure(
            self.project, "S01", "transport_timeout", transport_attempt_count=1
        )
        second = self.gate.record_failure(
            self.project, "S01", "empty_response", transport_attempt_count=2
        )
        self.assertTrue(first["resumable"])
        self.assertFalse(second["resumable"])

    def test_project_relative_artifact_path_is_resolved_from_project(self):
        relative = Path(".build") / "incoming" / "S01.png"
        absolute = self.project / relative
        absolute.parent.mkdir(parents=True)
        Image.new("RGB", (1600, 900), "white").save(absolute)

        record = self.gate.record_artifact(
            self.project,
            "S01",
            relative,
            transport_attempt_count=1,
        )

        self.assertTrue(record["artifact_received"])

    def test_transport_failures_remain_in_append_only_history(self):
        self.gate.record_failure(
            self.project,
            "S01",
            "transport_timeout",
            transport_attempt_count=1,
        )
        self.gate.record_failure(
            self.project,
            "S01",
            "transport_timeout",
            transport_attempt_count=2,
        )

        report = json.loads(
            (
                self.project / ".build" / "imagegen_transport_report.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(2, len(report["history"]))
        self.assertTrue(report["history"][0]["resumable"])
        self.assertFalse(report["history"][1]["resumable"])
