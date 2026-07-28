from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GATE = load_module(
    "v6_imagegen_invocation_gate_tests",
    "scripts/v6_blueprint_gate.py",
)
PIPELINE = load_module(
    "v6_imagegen_invocation_pipeline_tests",
    "scripts/project_pipeline.py",
)


def brief(mode: str) -> dict:
    return {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "requested_page_count": 1,
        "production_mode": "blueprint",
        "construction_mode": mode,
        "blueprint_engine": "builtin_imagegen",
        "platform_target": "auto",
        "source_files": ["C:/source.docx"],
    }


class V6ImageGenInvocationGateTests(unittest.TestCase):
    def make_project_without_invocation(
        self,
        project: Path,
        mode: str,
    ) -> None:
        build = project / ".build"
        drafts = build / "design_drafts"
        drafts.mkdir(parents=True)
        (project / "blueprints").mkdir()
        (project / "project_brief.json").write_text(
            json.dumps(brief(mode)),
            encoding="utf-8",
        )
        source = project / "manual.png"
        Image.new("RGB", (1600, 900), "white").save(source)
        draft = drafts / "S01.png"
        formal = project / "blueprints" / "S01.png"
        draft.write_bytes(source.read_bytes())
        formal.write_bytes(source.read_bytes())
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        page = {
            "design_draft_path": ".build/design_drafts/S01.png",
            "design_draft_sha256": digest,
            "formal_blueprint_path": "blueprints/S01.png",
            "formal_blueprint_sha256": digest,
            "imagegen_mode": "builtin",
            "imagegen_attempt_count": 1,
            "transport_attempt_count": 1,
        }
        (build / "visual_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "6.0",
                    "pipeline_revision": "6.0.0",
                    "construction_mode": mode,
                    "pages": {"S01": page},
                }
            ),
            encoding="utf-8",
        )
        (build / "imagegen_transport_report.json").write_text(
            json.dumps(
                {
                    "schema_version": "6.0",
                    "pipeline_revision": "6.0.0",
                    "construction_mode": mode,
                    "pages": {
                        "S01": {
                            "slide_id": "S01",
                            "imagegen_mode": "builtin",
                            "imagegen_attempt_count": 1,
                            "transport_attempt_count": 1,
                            "artifact_received": True,
                            "artifact_sha256": digest,
                            "failure_class": "artifact_received",
                            "resumable": True,
                        }
                    },
                    "history": [],
                }
            ),
            encoding="utf-8",
        )
        (build / "authoring_bundle.json").write_text(
            json.dumps(
                {
                    "schema_version": "6.0",
                    "slides": [
                        {
                            "slide_id": "S01",
                            "chapter": "chapter",
                            "title": "title",
                            "core_points": ["judgment"],
                            "source": "source",
                            "visual_route": {
                                "data_kind": "qualitative",
                                "qualitative_form": "parallel",
                            },
                            "evidence_inventory": [],
                        }
                    ],
                    "page_specs": {"S01": {"elements": []}},
                    "visual_manifest": {
                        "schema_version": "6.0",
                        "pages": {"S01": page},
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_blueprint_gate_rejects_files_without_imagegen_success_history(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.make_project_without_invocation(project, "bitmap")

            with self.assertRaisesRegex(
                ValueError,
                "V6_IMAGEGEN_INVOCATION_REQUIRED",
            ):
                GATE.assert_blueprint_gate(project, require_alignment=False)

    def test_materialize_stops_before_writing_outputs_without_imagegen_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.make_project_without_invocation(project, "bitmap")

            with self.assertRaisesRegex(
                ValueError,
                "V6_IMAGEGEN_INVOCATION_REQUIRED",
            ):
                PIPELINE.materialize_project(project)

            self.assertFalse(
                (project / ".build" / "authoring_report.json").exists()
            )
            self.assertFalse(
                (project / ".build" / "blueprint_text_benchmark.json").exists()
            )

    def test_review_steps_stop_without_imagegen_invocation(self):
        for mode, action, output in (
            (
                "deconstruct",
                PIPELINE.prepare_visual_review,
                ".build/visual_review_tiles.json",
            ),
            (
                "bitmap",
                PIPELINE.prepare_bitmap_review,
                ".build/bitmap_review.json",
            ),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                self.make_project_without_invocation(project, mode)

                with self.assertRaisesRegex(
                    ValueError,
                    "V6_IMAGEGEN_INVOCATION_REQUIRED",
                ):
                    action(project)

                self.assertFalse((project / output).exists())

    def test_compile_and_run_stop_before_creating_downstream_state(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.make_project_without_invocation(project, "bitmap")

            with self.assertRaisesRegex(
                ValueError,
                "V6_IMAGEGEN_INVOCATION_REQUIRED",
            ):
                PIPELINE.compile_project(project)
            with self.assertRaisesRegex(
                ValueError,
                "V6_IMAGEGEN_INVOCATION_REQUIRED",
            ):
                PIPELINE.run_project(project)

            self.assertFalse((project / "generate_deck.py").exists())
            self.assertFalse((project / ".build" / "compile_report.json").exists())
            self.assertFalse((project / ".build" / "v6_build_attempt.json").exists())


if __name__ == "__main__":
    unittest.main()
