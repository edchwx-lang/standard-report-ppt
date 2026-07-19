from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V595PostbuildReleaseTests(unittest.TestCase):
    def setUp(self):
        self.module_path = SKILL / "scripts" / "v595_release.py"

    def release_module(self):
        self.assertTrue(
            self.module_path.is_file(),
            "V5.9.5 postbuild release module is not implemented",
        )
        return load_module("v595_release", self.module_path)

    def test_advisory_warnings_lock_the_first_build_for_packaging(self):
        release = self.release_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx = project / "report.pptx"
            pptx.write_bytes(b"pptx")
            report = release.write_postbuild_release(
                project,
                pptx,
                quality_report={
                    "warnings": [{"code": "VISUAL_PALETTE"}],
                    "blockers": [],
                },
                text_audit={"ok": True, "errors": [], "warnings": []},
                fidelity_report={
                    "passed": False,
                    "pages": [
                        {
                            "slide_id": "S01",
                            "score": 0.40,
                            "layout_score": 0.35,
                            "ink_mass_ratio": 0.50,
                            "render_ink_density": 0.04,
                        }
                    ],
                },
                asset_audit={"ok": True, "errors": []},
            )
            self.assertEqual("package", report["decision"])
            self.assertTrue(report["build_locked"])
            self.assertEqual(1, report["build_attempt"])
            self.assertEqual(0, report["catastrophic_blocker_count"])

    def test_extreme_fidelity_difference_blocks_packaging(self):
        release = self.release_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx = project / "report.pptx"
            pptx.write_bytes(b"pptx")
            report = release.write_postbuild_release(
                project,
                pptx,
                quality_report={"warnings": [], "blockers": []},
                text_audit={"ok": True, "errors": [], "warnings": []},
                fidelity_report={
                    "passed": False,
                    "pages": [
                        {
                            "slide_id": "S01",
                            "score": 0.10,
                            "layout_score": 0.12,
                            "ink_mass_ratio": 0.20,
                            "render_ink_density": 0.002,
                        }
                    ],
                },
                asset_audit={"ok": True, "errors": []},
            )
            self.assertEqual("repair_required", report["decision"])
            self.assertFalse(report["build_locked"])
            self.assertIn(
                "POSTBUILD_GROSS_FIDELITY",
                {item["code"] for item in report["catastrophic_blockers"]},
            )

    def test_question_mark_corruption_is_catastrophic(self):
        release = self.release_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx = project / "report.pptx"
            pptx.write_bytes(b"pptx")
            report = release.write_postbuild_release(
                project,
                pptx,
                quality_report={"warnings": [], "blockers": []},
                text_audit={
                    "ok": False,
                    "errors": ["S01: question_mark_run at 3 length=8"],
                    "warnings": [],
                },
                fidelity_report={"passed": True, "pages": []},
                asset_audit={"ok": True, "errors": []},
            )
            self.assertEqual("repair_required", report["decision"])
            self.assertIn(
                "POSTBUILD_TEXT_CORRUPTION",
                {item["code"] for item in report["catastrophic_blockers"]},
            )

    def test_second_failed_repair_cannot_start_a_third_build(self):
        release = self.release_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            (build / "postbuild_release.json").write_text(
                json.dumps(
                    {
                        "decision": "repair_required",
                        "build_locked": False,
                        "build_attempt": 2,
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(
                release.rebuild_allowed(project, catastrophic_repair=True)
            )

    def test_checked_utf8_writer_rejects_placeholder_corruption(self):
        release = self.release_module()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "payload.json"
            with self.assertRaises(ValueError):
                release.write_json_atomic_checked(
                    destination,
                    {"title": "????????"},
                )
            self.assertFalse(destination.exists())

    def test_locked_result_hash_must_match_the_current_pptx(self):
        release = self.release_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            pptx = project / "report.pptx"
            pptx.write_bytes(b"current")
            (build / "postbuild_release.json").write_text(
                json.dumps(
                    {
                        "decision": "package",
                        "build_locked": True,
                        "build_attempt": 1,
                        "pptx_sha256": hashlib.sha256(b"other").hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(release.locked_release(project, pptx))

    def test_detail_text_loss_is_advisory_but_critical_text_loss_blocks(self):
        audit = load_module(
            "v595_text_audit",
            SKILL / "scripts" / "ppt_text_audit.py",
        )
        slides = [{
            "slide_id": "S01",
            "chapter": "章节",
            "title": "标题",
            "core_points": ["核心判断"],
            "source": "来源",
        }]
        page_specs = {
            "S01": {
                "elements": [{
                    "type": "chart",
                    "box": [1, 1, 4, 3],
                    "label": "细节标签",
                }]
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            pptx = Path(directory) / "report.pptx"
            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr(
                    "ppt/slides/slide1.xml",
                    '<p:sld xmlns:p="urn:p"><a:t xmlns:a="urn:a">'
                    "章节标题核心判断"
                    "</a:t></p:sld>",
                )
            result = audit.audit_pptx_text(
                pptx,
                slides=slides,
                page_specs=page_specs,
                critical_only=True,
            )
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["warnings"], result)

            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr(
                    "ppt/slides/slide1.xml",
                    '<p:sld xmlns:p="urn:p"><a:t xmlns:a="urn:a">'
                    "章节核心判断"
                    "</a:t></p:sld>",
                )
            result = audit.audit_pptx_text(
                pptx,
                slides=slides,
                page_specs=page_specs,
                critical_only=True,
            )
            self.assertFalse(result["ok"], result)
            self.assertTrue(
                any("critical text missing" in error for error in result["errors"]),
                result,
            )

    def test_locked_pipeline_run_returns_before_runtime_or_builder(self):
        pipeline = load_module(
            "v595_locked_pipeline",
            SKILL / "scripts" / "project_pipeline.py",
        )
        release = self.release_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            output = project / "output" / "report.pptx"
            output.parent.mkdir()
            output.write_bytes(b"locked")
            (project / "project_brief.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.9",
                        "pipeline_revision": "5.9.5",
                        "requested_page_count": 1,
                        "production_mode": "blueprint",
                        "blueprint_engine": "builtin_imagegen",
                        "platform_target": "auto",
                        "source_files": ["C:/fixture/source.docx"],
                    }
                ),
                encoding="utf-8",
            )
            build = project / ".build"
            build.mkdir()
            result = {
                "schema_version": "5.9",
                "skill_version": "5.9.5",
                "ok": True,
                "pptx": str(output),
                "pptx_sha256": release.sha256_file(output),
                "pages": 1,
            }
            (build / "pipeline_result.json").write_text(
                json.dumps(result),
                encoding="utf-8",
            )
            release.write_postbuild_release(
                project,
                output,
                quality_report={"warnings": [], "blockers": []},
                text_audit={"ok": True, "errors": [], "warnings": []},
                fidelity_report={"passed": True, "pages": []},
                asset_audit={"ok": True, "errors": []},
            )
            cached = pipeline.run_project(
                project,
                output,
                auto_package=False,
            )
            self.assertTrue(cached["cached"])
            self.assertEqual(result["pptx_sha256"], cached["pptx_sha256"])

    def test_packaging_requires_hash_bound_release_authorization(self):
        pack = load_module(
            "v595_release_packaging",
            SKILL / "scripts" / "pack_delivery.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx = project / "report.pptx"
            pptx.write_bytes(b"pptx")
            brief = {
                "schema_version": "5.9",
                "pipeline_revision": "5.9.5",
            }
            self.assertTrue(
                pack.validate_v595_postbuild_release(project, pptx, brief)
            )
            build = project / ".build"
            build.mkdir()
            (build / "postbuild_release.json").write_text(
                json.dumps(
                    {
                        "decision": "package",
                        "build_locked": True,
                        "catastrophic_blocker_count": 0,
                        "pptx_sha256": pack.sha256_file(pptx),
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                [],
                pack.validate_v595_postbuild_release(project, pptx, brief),
            )

    def test_old_delivery_record_cannot_mask_a_new_locked_pptx(self):
        pipeline = load_module(
            "v595_delivery_cache_binding",
            SKILL / "scripts" / "project_pipeline.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            pptx = project / "report.pptx"
            pptx.write_bytes(b"new")
            delivery = project / "old.zip"
            delivery.write_bytes(b"old delivery")
            (build / "delivery_record.json").write_text(
                json.dumps(
                    {
                        "zip_path": str(delivery),
                        "zip_sha256": hashlib.sha256(
                            delivery.read_bytes()
                        ).hexdigest(),
                        "pptx_sha256": hashlib.sha256(b"old").hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(pipeline._current_delivery(project, pptx))


if __name__ == "__main__":
    unittest.main()
