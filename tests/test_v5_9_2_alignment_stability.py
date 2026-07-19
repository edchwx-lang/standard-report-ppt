from __future__ import annotations

import hashlib
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class V592AlignmentStabilityTests(unittest.TestCase):
    def _v592_alignment_fixture(self):
        from tests.test_v5_8_4_alignment import V584AlignmentTests, sha256

        fixture = V584AlignmentTests(methodName="runTest")
        fixture.setUp()
        fixture.brief.update(
            {
                "schema_version": "5.9",
                "pipeline_revision": "5.9.2",
                "blueprint_engine": "builtin_imagegen",
                "platform_target": "auto",
                "source_files": ["C:/fixture/source.docx"],
            }
        )
        (fixture.project / "project_brief.json").write_text(
            json.dumps(fixture.brief, ensure_ascii=False),
            encoding="utf-8",
        )
        fixture.bundle.update(
            {
                "schema_version": "5.9",
                "pipeline_revision": "5.9.2",
            }
        )
        fixture.bundle_path.write_text(
            json.dumps(fixture.bundle, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        fixture.alignment.update(
            {
                "schema_version": "5.9",
                "skill_version": "5.9.2",
            }
        )
        fixture.alignment["pages"]["S01"]["authoring_bundle_sha256"] = sha256(
            fixture.bundle_path
        )
        return fixture

    def test_locked_artifact_hashes_survive_materialize_and_alignment(self):
        gate = load_module(
            "v592_gate_provenance",
            SKILL / "scripts" / "v59_blueprint_gate.py",
        )
        authoring = load_module(
            "v592_authoring_provenance",
            SKILL / "scripts" / "v583_authoring.py",
        )
        alignment = load_module(
            "v592_alignment_provenance",
            SKILL / "scripts" / "v584_blueprint_alignment.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            brief = {
                "schema_version": "5.9",
                "pipeline_revision": "5.9.2",
                "requested_page_count": 1,
                "production_mode": "blueprint",
                "blueprint_engine": "builtin_imagegen",
                "platform_target": "auto",
                "source_files": ["C:/fixture/source.docx"],
            }
            (project / "project_brief.json").write_text(
                json.dumps(brief),
                encoding="utf-8",
            )
            bundle = {
                "schema_version": "5.9",
                "pipeline_revision": "5.9.2",
                "slides": [
                    {
                        "slide_id": "S01",
                        "chapter": "Chapter",
                        "title": "Title",
                        "core_points": ["Core point"],
                        "source": "Source",
                        "visual_route": {
                            "data_kind": "qualitative",
                            "qualitative_form": "parallel",
                        },
                        "evidence_inventory": [],
                    }
                ],
                "page_specs": {"S01": {"elements": []}},
                "visual_manifest": {
                    "schema_version": "5.9",
                    "pages": {"S01": {}},
                },
            }
            bundle_path = build / "authoring_bundle.json"
            bundle_path.write_text(
                json.dumps(bundle, indent=2),
                encoding="utf-8",
            )
            source = build / "incoming" / "S01.png"
            source.parent.mkdir()
            Image.new("RGB", (1600, 900), "white").save(source)

            record = gate.record_artifact(
                project,
                "S01",
                Path(".build") / "incoming" / "S01.png",
                transport_attempt_count=1,
            )
            authoring.materialize_project(project)
            locked_bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            locked_page = locked_bundle["visual_manifest"]["pages"]["S01"]
            self.assertEqual(
                record["artifact_sha256"],
                locked_page["formal_blueprint_sha256"],
            )

            payload = {
                "schema_version": "5.9",
                "skill_version": "5.9.2",
                "pages": {
                    "S01": {
                        "design_draft_sha256": record["artifact_sha256"],
                        "authoring_bundle_sha256": sha256(bundle_path),
                        "reviewed": True,
                        "review_method": "visual_agent",
                        "slide_text": {
                            "chapter": "Chapter",
                            "title": "Title",
                            "core_points": ["Core point"],
                            "source": "Source",
                        },
                        "text_decisions": [
                            {
                                "role": role,
                                "canonical": text,
                                "observed": text,
                                "selected": text,
                                "resolution": "blueprint",
                            }
                            for role, text in (
                                ("chapter", "Chapter"),
                                ("title", "Title"),
                                ("core_point", "Core point"),
                            )
                        ],
                        "resolved_page_spec": {"elements": []},
                        "structure_modules": [],
                        "visuals": [],
                        "visual_census_result": "no_independent_subjects",
                    }
                },
            }
            (build / "blueprint_alignment.json").write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )

            alignment.apply_project_alignment(project)
            first = gate.assert_blueprint_gate(project)
            alignment.apply_project_alignment(project)
            second = gate.assert_blueprint_gate(project)

            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])

    def test_v592_uses_existing_local_backend_and_shared_schema(self):
        pipeline = load_module(
            "v592_pipeline_revision",
            SKILL / "scripts" / "project_pipeline.py",
        )
        contracts = load_module(
            "v592_contract_revision",
            SKILL / "scripts" / "v591_contracts.py",
        )
        brief = {
            "schema_version": "5.9",
            "pipeline_revision": "5.9.2",
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "blueprint_engine": "builtin_imagegen",
            "platform_target": "auto",
            "source_files": ["C:/fixture/source.docx"],
        }

        self.assertEqual([], pipeline.validate_brief(brief))
        self.assertTrue(contracts.is_v592(brief))
        self.assertTrue(contracts.uses_modern_blueprint_contract(brief))
        self.assertEqual(
            "blocker",
            contracts.audit_policy(brief, "reconstruction_contract"),
        )

    def test_v592_documentation_states_the_lightweight_boundaries(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8").lower()
        prompt = (
            SKILL / "prompts" / "blueprint_alignment_prompt.md"
        ).read_text(encoding="utf-8").lower()
        normalized = " ".join((skill + "\n" + prompt).split())

        self.assertIn("standard report ppt v5.9.2", normalized)
        self.assertIn('"pipeline_revision": "5.9.5"', normalized)
        self.assertIn("transport_timeout", normalized)
        self.assertIn("critical text", normalized)
        self.assertIn("no fidelity-driven rebuild", normalized)
        self.assertIn("detail differences", normalized)
        self.assertIn("semantic visual omissions", normalized)

    def test_mac_quality_fields_keep_shared_alignment_warnings(self):
        pipeline = load_module(
            "v592_mac_combined_quality",
            SKILL / "scripts" / "project_pipeline.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            (build / "runtime_report.json").write_text(
                json.dumps({"builder_backend": "mac_python_pptx_v1"}),
                encoding="utf-8",
            )
            (build / "quality_report.json").write_text(
                json.dumps(
                    {
                        "status": "pass_with_warnings",
                        "warnings": [
                            {
                                "code": "BLUEPRINT_DETAIL_TEXT_UNREVIEWED",
                                "severity": "warning",
                                "message": "detail text warning",
                            }
                        ],
                        "blockers": [],
                        "warning_count": 1,
                        "blocker_count": 0,
                    }
                ),
                encoding="utf-8",
            )
            (build / "mac_quality_report.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "visual_verification": True,
                        "warnings": [],
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )

            fields = pipeline._quality_fields(project)

            self.assertEqual("pass_with_warnings", fields["quality_status"])
            self.assertEqual(1, fields["warning_count"])
            self.assertEqual(0, fields["blocker_count"])

    def test_v592_blocks_only_missing_high_salience_text_review(self):
        fixture = self._v592_alignment_fixture()
        try:
            alignment = load_module(
                "v592_alignment_critical_text",
                SKILL / "scripts" / "v584_blueprint_alignment.py",
            )
            report = alignment.diagnose_alignment(
                fixture.project,
                fixture.brief,
                fixture.bundle,
                fixture.bundle["visual_manifest"],
                fixture.alignment,
            )

            self.assertIn(
                "BLUEPRINT_CRITICAL_TEXT_UNREVIEWED",
                {item["code"] for item in report["blockers"]},
            )
        finally:
            fixture.tearDown()

    def test_v592_cannot_bypass_review_by_omitting_slide_text_fields(self):
        fixture = self._v592_alignment_fixture()
        try:
            page = fixture.alignment["pages"]["S01"]
            page["slide_text"] = {"title": page["slide_text"]["title"]}
            alignment = load_module(
                "v592_alignment_omitted_fields",
                SKILL / "scripts" / "v584_blueprint_alignment.py",
            )

            report = alignment.diagnose_alignment(
                fixture.project,
                fixture.brief,
                fixture.bundle,
                fixture.bundle["visual_manifest"],
                fixture.alignment,
            )

            self.assertIn(
                "BLUEPRINT_CRITICAL_TEXT_UNREVIEWED",
                {item["code"] for item in report["blockers"]},
            )
        finally:
            fixture.tearDown()

    def test_fact_guard_and_uncertain_fallback_satisfy_critical_coverage(self):
        fixture = self._v592_alignment_fixture()
        try:
            page = fixture.alignment["pages"]["S01"]
            slide_text = page["slide_text"]
            page["text_decisions"] = [
                {
                    "role": "chapter",
                    "canonical": slide_text["chapter"],
                    "observed": slide_text["chapter"],
                    "selected": slide_text["chapter"],
                    "resolution": "blueprint",
                },
                {
                    "role": "title",
                    "canonical": slide_text["title"],
                    "observed": "Blueprint title",
                    "selected": slide_text["title"],
                    "resolution": "fact_guard",
                },
                {
                    "role": "core_point",
                    "canonical": slide_text["core_points"][0],
                    "observed": "",
                    "selected": slide_text["core_points"][0],
                    "resolution": "uncertain_fallback",
                },
            ]
            alignment = load_module(
                "v592_alignment_explicit_differences",
                SKILL / "scripts" / "v584_blueprint_alignment.py",
            )
            report = alignment.diagnose_alignment(
                fixture.project,
                fixture.brief,
                fixture.bundle,
                fixture.bundle["visual_manifest"],
                fixture.alignment,
            )

            self.assertNotIn(
                "BLUEPRINT_CRITICAL_TEXT_UNREVIEWED",
                {item["code"] for item in report["blockers"]},
            )
            warning_codes = {item["code"] for item in report["warnings"]}
            self.assertIn("BLUEPRINT_TEXT_FACT_GUARD", warning_codes)
            self.assertIn("BLUEPRINT_TEXT_UNCERTAIN", warning_codes)
        finally:
            fixture.tearDown()

    def test_invalid_resolution_does_not_satisfy_critical_coverage(self):
        fixture = self._v592_alignment_fixture()
        try:
            page = fixture.alignment["pages"]["S01"]
            slide_text = page["slide_text"]
            page["text_decisions"] = [
                {
                    "role": role,
                    "canonical": text,
                    "observed": text,
                    "selected": text,
                    "resolution": "bogus",
                }
                for role, text in (
                    ("chapter", slide_text["chapter"]),
                    ("title", slide_text["title"]),
                    ("core_point", slide_text["core_points"][0]),
                )
            ]
            alignment = load_module(
                "v592_alignment_invalid_resolution",
                SKILL / "scripts" / "v584_blueprint_alignment.py",
            )

            report = alignment.diagnose_alignment(
                fixture.project,
                fixture.brief,
                fixture.bundle,
                fixture.bundle["visual_manifest"],
                fixture.alignment,
            )

            self.assertIn(
                "BLUEPRINT_CRITICAL_TEXT_UNREVIEWED",
                {item["code"] for item in report["blockers"]},
            )
        finally:
            fixture.tearDown()

    def test_three_page_blueprint_prebuild_is_one_pass_with_soft_visual_warning(self):
        gate = load_module(
            "v592_three_page_gate",
            SKILL / "scripts" / "v59_blueprint_gate.py",
        )
        authoring = load_module(
            "v592_three_page_authoring",
            SKILL / "scripts" / "v583_authoring.py",
        )
        pipeline = load_module(
            "v592_three_page_pipeline",
            SKILL / "scripts" / "project_pipeline.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            brief = {
                "schema_version": "5.9",
                "pipeline_revision": "5.9.2",
                "requested_page_count": 3,
                "production_mode": "blueprint",
                "blueprint_engine": "builtin_imagegen",
                "platform_target": "auto",
                "source_files": ["C:/fixture/source.docx"],
            }
            (project / "project_brief.json").write_text(
                json.dumps(brief),
                encoding="utf-8",
            )
            slides = []
            page_specs = {}
            visual_pages = {}
            for index in range(1, 4):
                slide_id = f"S{index:02d}"
                slides.append(
                    {
                        "slide_id": slide_id,
                        "chapter": f"Chapter {index}",
                        "title": f"Title {index}",
                        "core_points": [f"Core point {index}"],
                        "source": "Source",
                        "visual_route": {
                            "data_kind": "qualitative",
                            "qualitative_form": "parallel",
                        },
                        "modules": [{"module_id": f"module_{index}"}],
                        "primary_visual_module_id": f"module_{index}",
                        "evidence_inventory": [],
                    }
                )
                page_specs[slide_id] = {
                    "elements": [
                        {
                            "element_id": f"{slide_id}_HEADER",
                            "module_id": f"module_{index}",
                            "type": "section_header",
                            "text": f"Section {index}",
                            "box": [0.2, 0.2, 3.0, 0.4],
                        },
                        {
                            "element_id": f"{slide_id}_CARD",
                            "module_id": f"module_{index}",
                            "type": "text_card",
                            "title": f"Card {index}",
                            "body": f"Body {index}",
                            "box": [0.2, 0.8, 5.0, 1.8],
                        },
                    ]
                }
                visual_pages[slide_id] = {}
            bundle = {
                "schema_version": "5.9",
                "pipeline_revision": "5.9.2",
                "slides": slides,
                "page_specs": page_specs,
                "visual_manifest": {
                    "schema_version": "5.9",
                    "pages": visual_pages,
                },
            }
            bundle_path = build / "authoring_bundle.json"
            bundle_path.write_text(
                json.dumps(bundle, indent=2),
                encoding="utf-8",
            )
            records = {}
            for index in range(1, 4):
                slide_id = f"S{index:02d}"
                source = build / "incoming" / f"{slide_id}.png"
                source.parent.mkdir(exist_ok=True)
                Image.new(
                    "RGB",
                    (1600, 900),
                    (245 - index, 245 - index, 245 - index),
                ).save(source)
                records[slide_id] = gate.record_artifact(
                    project,
                    slide_id,
                    Path(".build") / "incoming" / f"{slide_id}.png",
                    transport_attempt_count=1,
                )
            authoring.materialize_project(project)
            bundle_hash = sha256(bundle_path)
            pages = {}
            for index in range(1, 4):
                slide_id = f"S{index:02d}"
                critical = [
                    ("chapter", f"Chapter {index}"),
                    ("title", f"Title {index}"),
                    ("core_point", f"Core point {index}"),
                    ("section_header", f"Section {index}"),
                    ("text_card_title", f"Card {index}"),
                    ("text_card_body", f"Body {index}"),
                ]
                visuals = []
                census_result = "no_independent_subjects"
                if slide_id == "S02":
                    visuals = [
                        {
                            "visual_id": "S02_WORLD_FLOW",
                            "kind": "world_flow_map",
                            "description": "World flow map",
                            "treatment": "omit",
                            "omit_reason": "unreliable_crop",
                        }
                    ]
                    census_result = "reviewed_inventory"
                pages[slide_id] = {
                    "design_draft_sha256": records[slide_id][
                        "artifact_sha256"
                    ],
                    "authoring_bundle_sha256": bundle_hash,
                    "reviewed": True,
                    "review_method": "visual_agent",
                    "slide_text": {
                        "chapter": f"Chapter {index}",
                        "title": f"Title {index}",
                        "core_points": [f"Core point {index}"],
                        "source": "Source",
                    },
                    "text_decisions": [
                        {
                            "role": role,
                            "canonical": text,
                            "observed": text,
                            "selected": text,
                            "resolution": "blueprint",
                        }
                        for role, text in critical
                    ],
                    "resolved_page_spec": page_specs[slide_id],
                    "structure_modules": [
                        {"module_id": f"module_{index}"}
                    ],
                    "visuals": visuals,
                    "visual_census_result": census_result,
                    "reconstruction_contract": {
                        "visual_subject_count": len(visuals),
                        "supported_backends": [
                            "windows_com_v584",
                            "mac_python_pptx_v1",
                        ],
                        "module_bindings": [
                            {
                                "module_id": f"module_{index}",
                                "element_ids": [
                                    f"{slide_id}_HEADER",
                                    f"{slide_id}_CARD",
                                ],
                            }
                        ],
                    },
                }
            (build / "blueprint_alignment.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.9",
                        "skill_version": "5.9.2",
                        "pages": pages,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (build / "runtime_report.json").write_text(
                json.dumps({"builder_backend": "windows_com_v584"}),
                encoding="utf-8",
            )

            report = pipeline.prebuild_project(project)
            precheck = json.loads(
                (build / "reconstruction_precheck.json").read_text(
                    encoding="utf-8"
                )
            )
            benchmark = json.loads(
                (build / "blueprint_text_benchmark.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(0, report["blocker_count"])
            self.assertIn(
                "SEMANTIC_VISUAL_OMITTED",
                {item["code"] for item in precheck["warnings"]},
            )
            self.assertIn(
                "BLUEPRINT_DETAIL_TEXT_UNREVIEWED",
                {item["code"] for item in report["warnings"]},
            )
            self.assertEqual("5.9", benchmark["schema_version"])
            self.assertEqual("5.9.2", benchmark["skill_version"])
            self.assertFalse(benchmark["pages"]["S01"]["exact_match"])
            self.assertFalse((project / "output" / "report.pptx").exists())


if __name__ == "__main__":
    unittest.main()
