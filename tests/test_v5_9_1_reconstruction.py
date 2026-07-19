from __future__ import annotations

import importlib.util
import json
import unittest
from copy import deepcopy
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BRIEF = {
    "schema_version": "5.9",
    "pipeline_revision": "5.9.1",
    "production_mode": "blueprint",
}

SLIDE = {
    "slide_id": "S03",
    "modules": [
        {"module_id": "career_window"},
        {"module_id": "early_policy"},
    ],
}

ALIGNMENT = {
    "schema_version": "5.9",
    "pages": {
        "S03": {
            "reviewed": True,
            "structure_modules": [
                {"module_id": "career_window"},
                {"module_id": "early_policy"},
            ],
            "visuals": [
                {
                    "visual_id": "S03_TRAIN",
                    "asset_id": "S03_TRAIN",
                    "kind": "pictogram",
                    "description": "早班车",
                    "treatment": "crop",
                    "source_px": [1200, 600, 1300, 700],
                    "target_box_in": [9.2, 2.8, 0.7, 0.7],
                    "target_coord_space": "body",
                }
            ],
            "reconstruction_contract": {
                "visual_subject_count": 1,
                "supported_backends": [
                    "windows_com_v584",
                    "mac_python_pptx_v1",
                ],
                "module_bindings": [
                    {
                        "module_id": "career_window",
                        "element_ids": ["S03_CHART"],
                    },
                    {
                        "module_id": "early_policy",
                        "element_ids": ["S03_POLICY", "S03_TRAIN_ELEMENT"],
                    },
                ],
            },
        }
    },
}

COMPLETE_SPEC = {
    "elements": [
        {
            "element_id": "S03_CHART",
            "module_id": "career_window",
            "type": "column_chart",
            "box": [0.1, 0.2, 5.8, 2.2],
            "data": [{"label": "11-20年", "value": 47.5}],
        },
        {
            "element_id": "S03_POLICY",
            "module_id": "early_policy",
            "type": "text_card",
            "box": [7.0, 2.7, 4.0, 1.2],
            "title": "早班车",
            "body": "覆盖35岁以下科研人员",
        },
        {
            "element_id": "S03_TRAIN_ELEMENT",
            "module_id": "early_policy",
            "type": "asset",
            "asset_id": "S03_TRAIN",
            "box": [9.2, 2.8, 0.7, 0.7],
        },
    ]
}


class V591ReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.contracts = load_module(
            "v591_reconstruction",
            SKILL / "scripts" / "v591_reconstruction_contract.py",
        )

    def test_contract_rejects_unbound_modules_and_missing_crop_element(self):
        report = self.contracts.validate_reconstruction_contract(
            BRIEF,
            [SLIDE],
            {
                "S03": {
                    "elements": [
                        {
                            "element_id": "S03_CHART",
                            "module_id": "career_window",
                            "type": "column_chart",
                            "box": [0.1, 0.2, 5.8, 2.2],
                            "data": [{"label": "11-20年", "value": 47.5}],
                        }
                    ]
                }
            },
            ALIGNMENT,
            "windows_com_v584",
        )
        codes = {item["code"] for item in report["blockers"]}
        self.assertIn("RECONSTRUCTION_MODULE_UNBOUND", codes)
        self.assertIn("RECONSTRUCTION_CROP_ELEMENT_MISSING", codes)

    def test_fully_bound_contract_passes_before_builder(self):
        report = self.contracts.validate_reconstruction_contract(
            BRIEF,
            [SLIDE],
            {"S03": COMPLETE_SPEC},
            ALIGNMENT,
            "windows_com_v584",
        )
        self.assertEqual([], report["blockers"])

    def test_backend_support_is_checked(self):
        alignment = {
            **ALIGNMENT,
            "pages": {
                "S03": {
                    **ALIGNMENT["pages"]["S03"],
                    "reconstruction_contract": {
                        **ALIGNMENT["pages"]["S03"]["reconstruction_contract"],
                        "supported_backends": ["windows_com_v584"],
                    },
                }
            },
        }
        report = self.contracts.validate_reconstruction_contract(
            BRIEF,
            [SLIDE],
            {"S03": COMPLETE_SPEC},
            alignment,
            "mac_python_pptx_v1",
        )
        self.assertIn(
            "RECONSTRUCTION_BACKEND_UNSUPPORTED",
            {item["code"] for item in report["blockers"]},
        )

    def test_omitted_semantic_map_warns_but_does_not_block(self):
        alignment = deepcopy(ALIGNMENT)
        alignment["pages"]["S03"]["visuals"].append(
            {
                "visual_id": "S03_MAP",
                "kind": "world_flow_map",
                "description": "World flow map",
                "treatment": "omit",
                "omit_reason": "unreliable_crop",
            }
        )
        alignment["pages"]["S03"]["reconstruction_contract"][
            "visual_subject_count"
        ] += 1

        report = self.contracts.validate_reconstruction_contract(
            {
                **BRIEF,
                "pipeline_revision": "5.9.2",
            },
            [SLIDE],
            {"S03": COMPLETE_SPEC},
            alignment,
            "windows_com_v584",
        )

        self.assertEqual([], report["blockers"])
        self.assertIn(
            "SEMANTIC_VISUAL_OMITTED",
            {item["code"] for item in report["warnings"]},
        )

    def test_pipeline_materializes_complete_census_before_local_builder(self):
        from tests.test_v5_8_4_alignment import V584AlignmentTests, sha256

        fixture = V584AlignmentTests(methodName="runTest")
        fixture.setUp()
        try:
            fixture.brief.update(
                {
                    "schema_version": "5.9",
                    "pipeline_revision": "5.9.1",
                }
            )
            (fixture.project / "project_brief.json").write_text(
                json.dumps(fixture.brief, ensure_ascii=False),
                encoding="utf-8",
            )
            fixture.bundle.update(
                {
                    "schema_version": "5.9",
                    "pipeline_revision": "5.9.1",
                }
            )
            fixture.bundle_path.write_text(
                json.dumps(fixture.bundle, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            page = fixture.alignment["pages"]["S01"]
            page["authoring_bundle_sha256"] = sha256(fixture.bundle_path)
            page["resolved_page_spec"]["elements"].append(
                {
                    "element_id": "S01_ARROW",
                    "module_id": "continent_flow",
                    "type": "arrow",
                    "box": [7.7, 1.1, 1.0, 0.4],
                }
            )
            for index, element in enumerate(
                page["resolved_page_spec"]["elements"],
                start=1,
            ):
                element.setdefault("element_id", f"S01_E{index:02d}")
                element["module_id"] = "continent_flow"
            page["visuals"][0]["visual_id"] = "S01_V01"
            page["visuals"][1].update(
                {
                    "visual_id": "S01_V02",
                    "element_id": "S01_ARROW",
                    "rebuild_recipe": "line_arrow",
                }
            )
            page["visuals"][2].update(
                {
                    "visual_id": "S01_V03",
                    "omit_reason": "non_evidence_decoration",
                }
            )
            element_ids = [
                item["element_id"]
                for item in page["resolved_page_spec"]["elements"]
            ]
            page["reconstruction_contract"] = {
                "visual_subject_count": 3,
                "supported_backends": [
                    "windows_com_v584",
                    "mac_python_pptx_v1",
                ],
                "module_bindings": [
                    {
                        "module_id": "continent_flow",
                        "element_ids": element_ids,
                    }
                ],
            }
            fixture.alignment.update(
                {
                    "schema_version": "5.9",
                    "skill_version": "5.9.1",
                }
            )
            (fixture.build / "blueprint_alignment.json").write_text(
                json.dumps(fixture.alignment, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (fixture.build / "runtime_report.json").write_text(
                json.dumps({"builder_backend": "windows_com_v584"}),
                encoding="utf-8",
            )
            pipeline = load_module(
                "v591_pipeline_integration",
                SKILL / "scripts" / "project_pipeline.py",
            )
            report = pipeline.prebuild_project(fixture.project)
            precheck = json.loads(
                (fixture.build / "reconstruction_precheck.json").read_text(
                    encoding="utf-8"
                )
            )
            manifest = json.loads(
                (fixture.build / "visual_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            slides = json.loads(
                (fixture.build / "slides.json").read_text(encoding="utf-8")
            )
            self.assertTrue(report["ok"])
            self.assertEqual(0, precheck["blocker_count"])
            self.assertEqual(
                "reviewed_inventory",
                slides[0]["visual_review"],
            )
            self.assertEqual(
                3,
                len(manifest["pages"]["S01"]["visuals"]),
            )
        finally:
            fixture.tearDown()

    def test_documentation_defines_one_pass_reconstruction_contract(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8").lower()
        reconstruction = (
            SKILL / "prompts" / "python_reconstruction_prompt.md"
        ).read_text(encoding="utf-8")
        alignment = (
            SKILL / "prompts" / "blueprint_alignment_prompt.md"
        ).read_text(encoding="utf-8")
        self.assertIn("reconstruction_contract", reconstruction)
        self.assertIn("element_id", reconstruction)
        self.assertIn("module_bindings", reconstruction)
        self.assertIn("reviewed_inventory", alignment)
        self.assertIn(
            "native_analytical_element is forbidden",
            alignment.lower(),
        )
        self.assertIn(
            "fidelity deviations do not trigger a rebuild",
            skill,
        )
        normalized_alignment = " ".join(alignment.lower().split())
        self.assertIn("generic text cards", normalized_alignment)
        self.assertIn(
            "minor spacing and wording differences are allowed",
            normalized_alignment,
        )

if __name__ == "__main__":
    unittest.main()
