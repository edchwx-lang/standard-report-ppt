from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location(
        "v61_deconstruction_acceptance_tests",
        ROOT / "scripts" / "v61_deconstruction_acceptance.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ACCEPTANCE = load()


class V61DeconstructionAcceptanceTests(unittest.TestCase):
    def make_project(self, project: Path) -> Path:
        (project / ".build" / "assets" / "S01").mkdir(parents=True)
        pptx = project / "report.pptx"
        pptx.write_bytes(b"pptx")
        (project / ".build" / "assets" / "S01" / "ICON_1.png").write_bytes(
            b"png"
        )
        (project / ".build" / "blueprint_alignment.json").write_text(
            json.dumps(
                {
                    "schema_version": "6.0",
                    "pipeline_revision": "6.0.0",
                    "construction_mode": "deconstruct",
                    "pages": {
                        "S01": {
                            "text_decisions": [
                                {"role": "body", "selected": "保留文字"}
                            ],
                            "structure_modules": [
                                {
                                    "module_id": "M1",
                                    "module_kind": "mixed",
                                    "contains_editable_text": True,
                                }
                            ],
                            "visuals": [
                                {
                                    "visual_id": "ICON_1",
                                    "asset_id": "ICON_1",
                                    "kind": "icon",
                                    "treatment": "crop",
                                }
                            ],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (project / ".build" / "page_specs.json").write_text(
            json.dumps(
                {
                    "S01": {
                        "elements": [
                            {
                                "type": "text",
                                "element_id": "TEXT_1",
                                "module_id": "M1",
                                "text": "保留文字",
                            },
                            {
                                "type": "asset",
                                "element_id": "ASSET_1",
                                "module_id": "M1",
                                "asset_id": "ICON_1",
                            },
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        return pptx

    def evaluate(self, project: Path, **overrides):
        values = {
            "project_dir": project,
            "pptx_path": project / "report.pptx",
            "brief": {
                "schema_version": "6.0",
                "pipeline_revision": "6.0.0",
                "construction_mode": "deconstruct",
                "requested_page_count": 1,
            },
            "builder_backend": "windows_com_v584",
            "precheck": {"ok": True, "status": "pass", "blockers": []},
            "editability_audit": {
                "ok": True,
                "status": "pass",
                "blockers": [],
            },
            "render_result": {
                "ok": True,
                "status": "pass",
                "visual_verification": True,
            },
            "fidelity_report": {"passed": False, "failed_slide_ids": ["S01"]},
        }
        values.update(overrides)
        return ACCEPTANCE.evaluate_deconstruction_acceptance(**values)

    def test_overlap_and_low_fidelity_are_advisory_when_contract_is_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.make_project(project)
            result = self.evaluate(project)
            self.assertTrue(result["accepted"])
            self.assertEqual("accept", result["decision"])
            self.assertEqual([], result["blockers"])
            self.assertIn(
                "D61_FIDELITY_ADVISORY",
                [item["code"] for item in result["warnings"]],
            )

    def test_missing_crop_asset_blocks_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.make_project(project)
            (project / ".build" / "assets" / "S01" / "ICON_1.png").unlink()
            result = self.evaluate(project)
            self.assertFalse(result["accepted"])
            self.assertIn(
                "D61_CROP_MISSING",
                [item["code"] for item in result["blockers"]],
            )

    def test_missing_selected_text_blocks_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.make_project(project)
            result = self.evaluate(
                project,
                editability_audit={
                    "ok": False,
                    "status": "blocked",
                    "blockers": [
                        {
                            "code": "DECONSTRUCTION_EDITABILITY_FAILED",
                            "message": "selected text absent from OOXML",
                        }
                    ],
                },
            )
            self.assertFalse(result["accepted"])
            self.assertIn(
                "D61_TEXT_MISMATCH",
                [item["code"] for item in result["blockers"]],
            )

    def test_topology_mismatch_blocks_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.make_project(project)
            result = self.evaluate(
                project,
                precheck={
                    "ok": False,
                    "status": "blocked",
                    "blockers": [
                        {
                            "code": "DECONSTRUCTION_TOPOLOGY_MISMATCH",
                            "message": "flow was reconstructed as a matrix",
                        }
                    ],
                },
            )
            self.assertFalse(result["accepted"])
            self.assertIn(
                "D61_TOPOLOGY_MISMATCH",
                [item["code"] for item in result["blockers"]],
            )

    def test_reviewed_sequential_flow_rebuilt_as_matrix_blocks_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.make_project(project)
            alignment_path = project / ".build" / "blueprint_alignment.json"
            alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
            page = alignment["pages"]["S01"]
            page["structure_modules"] = [
                {
                    "module_id": "M1",
                    "module_kind": "flow",
                    "contains_editable_text": True,
                    "observed_topology": "sequential_flow",
                }
            ]
            page["reconstruction_contract"] = {
                "module_bindings": [
                    {
                        "module_id": "M1",
                        "element_ids": ["MATRIX_1", "ASSET_1"],
                    }
                ]
            }
            alignment_path.write_text(json.dumps(alignment), encoding="utf-8")
            spec_path = project / ".build" / "page_specs.json"
            specs = json.loads(spec_path.read_text(encoding="utf-8"))
            specs["S01"]["elements"].append(
                {
                    "type": "matrix",
                    "element_id": "MATRIX_1",
                    "module_id": "M1",
                    "headers": ["阶段", "内容"],
                    "rows": [["一", "开始"], ["二", "结束"]],
                }
            )
            spec_path.write_text(json.dumps(specs), encoding="utf-8")
            result = self.evaluate(project)
            self.assertFalse(result["accepted"])
            self.assertIn(
                "D61_TOPOLOGY_MISMATCH",
                [item["code"] for item in result["blockers"]],
            )

    def test_unverified_render_blocks_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.make_project(project)
            result = self.evaluate(
                project,
                render_result={
                    "ok": False,
                    "status": "structurally_valid_unrendered",
                    "visual_verification": False,
                },
            )
            self.assertFalse(result["accepted"])
            self.assertIn(
                "D61_RENDER_INVALID",
                [item["code"] for item in result["blockers"]],
            )


if __name__ == "__main__":
    unittest.main()
