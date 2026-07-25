from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image
from docx import Document


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PIPELINE = load("v6_pipeline_tests", "scripts/project_pipeline.py")
GATE = load("v6_gate_tests", "scripts/v6_blueprint_gate.py")
BITMAP = load("v6_bitmap_pipeline_tests", "scripts/v6_bitmap.py")


def brief(mode: str | None = "deconstruct") -> dict:
    value = {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "requested_page_count": 1,
        "production_mode": "blueprint",
        "blueprint_engine": "builtin_imagegen",
        "platform_target": "auto",
        "source_files": ["C:/source.docx"],
    }
    if mode is not None:
        value["construction_mode"] = mode
    return value


class V6PipelineTests(unittest.TestCase):
    def test_v6_init_reuses_shared_source_ingest_with_v59_digest_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            source = root / "source.docx"
            document = Document()
            document.add_paragraph("全球顶尖科学家迁移趋势")
            document.save(source)
            value = brief("bitmap")
            value["source_files"] = [str(source)]
            (project / "project_brief.json").write_text(
                json.dumps(value, ensure_ascii=False), encoding="utf-8"
            )

            with mock.patch.object(
                PIPELINE,
                "_ensure_project_runtime",
                return_value={"ok": True, "backend": "windows_com_v584"},
            ):
                result = PIPELINE.init_project(project)

            self.assertEqual("6.0", result["schema_version"])
            digest = json.loads(
                (project / ".build" / "source_digest.json").read_text(
                    encoding="utf-8"
                )
            )
            extract = json.loads(
                (project / ".build" / "source_extract.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("5.9", digest["schema_version"])
            self.assertEqual("6.0", extract["schema_version"])
            self.assertEqual(
                "6.0",
                json.loads(
                    (project / "project_brief.json").read_text(encoding="utf-8")
                )["schema_version"],
            )

    def test_v6_materialize_reuses_v59_text_benchmark_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            build = project / ".build"
            drafts = build / "design_drafts"
            drafts.mkdir(parents=True)
            Image.new("RGB", (1600, 900), "white").save(drafts / "S01.png")
            (project / "project_brief.json").write_text(
                json.dumps(brief("bitmap"), ensure_ascii=False), encoding="utf-8"
            )
            bundle = {
                "schema_version": "6.0",
                "slides": [
                    {
                        "slide_id": "S01",
                        "chapter": "第一章",
                        "title": "V6共享文本基准",
                        "core_points": ["共享算法保持不变"],
                        "source": "资料来源：测试",
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
                    "pages": {
                        "S01": {
                            "design_draft_path": ".build/design_drafts/S01.png"
                        }
                    },
                },
            }
            (build / "authoring_bundle.json").write_text(
                json.dumps(bundle, ensure_ascii=False), encoding="utf-8"
            )

            result = PIPELINE.materialize_project(project)

            benchmark = json.loads(
                (build / "blueprint_text_benchmark.json").read_text(
                    encoding="utf-8"
                )
            )
            manifest = json.loads(
                (build / "visual_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("6.0", result["schema_version"])
            self.assertEqual("6.0", benchmark["schema_version"])
            self.assertEqual("6.0.0", manifest["pipeline_revision"])
            self.assertEqual("bitmap", manifest["construction_mode"])
            self.assertEqual("v583_authoring", result["shared_pre_blueprint_algorithm"])

    def make_locked_project(
        self, project: Path, mode: str = "deconstruct", page_count: int = 1
    ) -> dict:
        value = brief(mode)
        value["requested_page_count"] = page_count
        (project / ".build").mkdir()
        (project / "blueprints").mkdir()
        alignment_pages = {}
        for index in range(1, page_count + 1):
            slide_id = f"S{index:02d}"
            Image.new("RGB", (100, 100), (index, 2, 3)).save(
                project / "blueprints" / f"{slide_id}.png"
            )
            alignment_pages[slide_id] = {
                "source_px": [0, 10, 100, 90]
            }
        alignment_name = (
            "blueprint_alignment.json"
            if mode == "deconstruct"
            else "bitmap_alignment.json"
        )
        (project / ".build" / alignment_name).write_text(
            json.dumps(
                {
                    "schema_version": "6.0",
                    "pipeline_revision": "6.0.0",
                    "construction_mode": mode,
                    "pages": alignment_pages,
                }
            ),
            encoding="utf-8",
        )
        (project / "project_brief.json").write_text(
            json.dumps(value), encoding="utf-8"
        )
        return value

    def run_with_fakes(
        self,
        project: Path,
        value: dict,
        *,
        backend: str = "windows_com_v584",
        compile_error: Exception | None = None,
        mac_status: str = "pass",
        repair: bool = False,
    ):
        generator = project / "generate_deck.py"
        generator.write_text("print('ok')\n", encoding="utf-8")
        (project / ".build" / "deconstruction_precheck.json").write_text(
            json.dumps(
                {"ok": True, "allowed_large_visual_assets_by_page": {}}
            ),
            encoding="utf-8",
        )
        (project / ".build" / "page_specs.json").write_text(
            json.dumps({"S01": {"elements": []}}), encoding="utf-8"
        )
        loaded: list[str] = []
        real_loader = PIPELINE._load_module

        def loader(name, path):
            loaded.append(name)
            if "windows_runtime" in name:
                return SimpleNamespace(ensure_windows_runtime=lambda **kwargs: {})
            if "postbuild_editability" in name:
                return SimpleNamespace(
                    audit_deconstruction_pptx=lambda *args, **kwargs: {
                        "ok": True,
                        "status": "pass",
                        "blockers": [],
                    },
                    audit_bitmap_pptx=lambda *args, **kwargs: {
                        "ok": True,
                        "status": "pass",
                        "blockers": [],
                    },
                )
            if "macos_render" in name:
                return SimpleNamespace(
                    render_project=lambda *args, **kwargs: {
                        "ok": True,
                        "status": "pass",
                        "visual_verification": True,
                    }
                )
            if "macos_quality" in name:
                return SimpleNamespace(
                    audit_mac_pptx=lambda *args, **kwargs: {
                        "ok": mac_status != "blocked",
                        "status": mac_status,
                        "errors": ["blocked"] if mac_status == "blocked" else [],
                    }
                )
            return real_loader(name, path)

        def run(command, **kwargs):
            if "--output" in command:
                Path(command[command.index("--output") + 1]).write_bytes(b"pptx")
            return SimpleNamespace(returncode=0)

        compile_side_effect = compile_error or generator
        with (
            mock.patch.object(
                PIPELINE,
                "_ensure_project_runtime",
                return_value={
                    "builder_backend": backend,
                    "construction_mode": value["construction_mode"],
                },
            ),
            mock.patch.object(PIPELINE, "prebuild_project", return_value={"ok": True}),
            mock.patch.object(
                PIPELINE,
                "_execute_v6_preprocess_batches",
                side_effect=lambda _project, _brief, _backend, plan, reused: {
                    slide_id
                    for batch in plan["batches"]
                    for slide_id in batch["slide_ids"]
                },
            ),
            mock.patch.object(
                PIPELINE, "compile_project", side_effect=(
                    compile_side_effect
                    if isinstance(compile_side_effect, Exception)
                    else None
                ), return_value=(
                    None
                    if isinstance(compile_side_effect, Exception)
                    else compile_side_effect
                )
            ),
            mock.patch.object(PIPELINE, "_run", side_effect=run),
            mock.patch.object(PIPELINE, "_load_module", side_effect=loader),
        ):
            result = PIPELINE._run_v6_project(
                project,
                value,
                None,
                catastrophic_repair=repair,
                user_revision=False,
                auto_package=False,
            )
        self.assertFalse(any("imagegen" in name.lower() for name in loaded))
        return result

    def test_v6_requires_explicit_mode_and_rejects_fast(self):
        self.assertIn("V6_CONSTRUCTION_MODE_REQUIRED", PIPELINE.validate_brief(brief(None)))
        value = brief("bitmap")
        value["production_mode"] = "fast"
        self.assertIn("V6_PRODUCTION_MODE_INVALID", PIPELINE.validate_brief(value))

    def test_v6_output_path_is_absolute_before_powerpoint_build(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            relative = Path("output") / "report.pptx"
            self.assertEqual(
                relative.resolve(),
                PIPELINE._resolve_v6_output_path(
                    project,
                    relative,
                    "bitmap",
                ),
            )
            self.assertEqual(
                (project / "output" / f"{project.name}_位图版.pptx").resolve(),
                PIPELINE._resolve_v6_output_path(project, None, "bitmap"),
            )

    def test_user_mode_aliases_are_explicitly_normalized(self):
        contracts = load("v6_alias_contracts", "scripts/v6_contracts.py")
        for value in ("解构", "可编辑", "1"):
            self.assertEqual("deconstruct", contracts.normalize_construction_mode(value))
        for value in ("位图", "快速位图", "2"):
            self.assertEqual("bitmap", contracts.normalize_construction_mode(value))
        self.assertIsNone(contracts.normalize_construction_mode("蓝图模式"))

    def test_v59_fast_remains_valid(self):
        value = {
            "schema_version": "5.9",
            "pipeline_revision": "5.9.6",
            "requested_page_count": 1,
            "production_mode": "fast",
            "platform_target": "auto",
            "source_files": ["C:/source.docx"],
        }
        self.assertEqual([], PIPELINE.validate_brief(value))

    def test_v6_backend_mapping_is_version_aware(self):
        self.assertEqual("windows_com_v584", PIPELINE.select_v6_backend("Windows"))
        self.assertEqual("mac_python_pptx_v2", PIPELINE.select_v6_backend("Darwin"))
        with self.assertRaises(RuntimeError):
            PIPELINE.select_v6_backend("Linux")

    def test_review_actions_are_mode_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "project_brief.json").write_text(
                json.dumps(brief("bitmap")), encoding="utf-8"
            )
            (project / "blueprints").mkdir()
            Image.new("RGB", (1600, 900), "white").save(project / "blueprints" / "S01.png")
            bitmap = PIPELINE.prepare_bitmap_review(project)
            self.assertEqual("full_page_only", bitmap["review_scope"])
            with self.assertRaises(ValueError):
                PIPELINE.prepare_visual_review(project)

    def make_reviewed_deconstruct_alignment(self, project: Path) -> tuple[dict, Path]:
        self.make_locked_project(project)
        manifest = PIPELINE.prepare_visual_review(project)
        manifest_path = project / ".build" / "visual_review_tiles.json"
        digest = PIPELINE._sha256_file(project / "blueprints" / "S01.png")
        visual = {
            "visual_id": "V01",
            "review_tile_ids": ["Q1"],
        }
        alignment = {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "construction_mode": "deconstruct",
            "pages": {
                "S01": {
                    "reviewed": True,
                    "design_draft_sha256": digest,
                    "resolved_page_spec": {"elements": []},
                    "visuals": [visual],
                    "visual_review_tiles": {
                        "full_page_reviewed": True,
                        "tile_manifest_sha256": PIPELINE._sha256_file(manifest_path),
                        "blueprint_sha256": digest,
                        "reviewed_tile_ids": ["Q1", "Q2", "Q3", "Q4"],
                        "tile_subjects": {
                            "Q1": ["V01"],
                            "Q2": [],
                            "Q3": [],
                            "Q4": [],
                        },
                    },
                }
            },
        }
        self.assertEqual({"Q1", "Q2", "Q3", "Q4"}, {
            item["tile_id"] for item in manifest["pages"]["S01"]["tiles"]
        })
        self.assertEqual("6.0", manifest["schema_version"])
        self.assertEqual("6.0.0-rc1", manifest["skill_version"])
        return alignment, manifest_path

    def test_v6_deconstruct_alignment_requires_hash_bound_full_page_and_q1_q4(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            alignment, _ = self.make_reviewed_deconstruct_alignment(project)
            PIPELINE._validate_v6_deconstruct_alignment(
                project, brief("deconstruct"), alignment
            )

    def test_v6_deconstruct_review_rejects_missing_review_evidence_fields(self):
        for field in (
            "full_page_reviewed",
            "reviewed_tile_ids",
            "tile_subjects",
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                alignment, _ = self.make_reviewed_deconstruct_alignment(project)
                alignment["pages"]["S01"]["visual_review_tiles"].pop(field)
                with self.assertRaisesRegex(ValueError, "visual review failed"):
                    PIPELINE._validate_v6_deconstruct_alignment(
                        project, brief("deconstruct"), alignment
                    )

    def test_v6_deconstruct_review_rejects_incomplete_visual_tile_index(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            alignment, _ = self.make_reviewed_deconstruct_alignment(project)
            alignment["pages"]["S01"]["visual_review_tiles"]["tile_subjects"][
                "Q1"
            ] = []
            with self.assertRaisesRegex(ValueError, "visual review failed"):
                PIPELINE._validate_v6_deconstruct_alignment(
                    project, brief("deconstruct"), alignment
                )

    def test_v6_deconstruct_review_rejects_missing_visual_tile_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            alignment, _ = self.make_reviewed_deconstruct_alignment(project)
            alignment["pages"]["S01"]["visuals"][0].pop("review_tile_ids")
            with self.assertRaisesRegex(ValueError, "visual review failed"):
                PIPELINE._validate_v6_deconstruct_alignment(
                    project, brief("deconstruct"), alignment
                )

    def test_v6_deconstruct_review_rejects_duplicate_review_indexes(self):
        mutations = (
            lambda page: page["visual_review_tiles"]["reviewed_tile_ids"].append("Q4"),
            lambda page: page["visual_review_tiles"]["tile_subjects"]["Q1"].append(
                "V01"
            ),
            lambda page: page["visuals"][0]["review_tile_ids"].append("Q1"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                alignment, _ = self.make_reviewed_deconstruct_alignment(project)
                mutate(alignment["pages"]["S01"])
                with self.assertRaisesRegex(ValueError, "visual review failed"):
                    PIPELINE._validate_v6_deconstruct_alignment(
                        project, brief("deconstruct"), alignment
                    )

    def test_prebuild_accepts_the_exact_v6_prepare_visual_review_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            alignment, _ = self.make_reviewed_deconstruct_alignment(project)
            (project / ".build" / "blueprint_alignment.json").write_text(
                json.dumps(alignment), encoding="utf-8"
            )
            (project / ".build" / "runtime_report.json").write_text(
                json.dumps({"builder_backend": "windows_com_v584"}),
                encoding="utf-8",
            )
            slide = {
                "slide_id": "S01",
                "chapter": "chapter",
                "title": "title",
                "core_points": ["judgment"],
                "source": "source",
            }
            (project / ".build" / "slides.json").write_text(
                json.dumps([slide]), encoding="utf-8"
            )
            (project / ".build" / "visual_manifest.json").write_text(
                json.dumps({"pages": {"S01": {}}}), encoding="utf-8"
            )
            real_loader = PIPELINE._load_module

            def loader(name, path):
                if "blueprint_gate_prebuild" in name:
                    return SimpleNamespace(assert_blueprint_gate=lambda *a, **k: {})
                if "alignment_merge" in name:
                    return SimpleNamespace(
                        _merge_page=lambda slide, spec, page, alignment, **kwargs: (
                            slide,
                            spec,
                            page,
                        )
                    )
                if "reconstruction_contract" in name:
                    return SimpleNamespace(
                        validate_reconstruction_contract=lambda *a, **k: {
                            "blockers": []
                        }
                    )
                if "deconstruction_prebuild" in name:
                    return SimpleNamespace(
                        validate_deconstruction_prebuild=lambda *a, **k: {
                            "ok": True,
                            "blockers": [],
                            "allowed_large_visual_assets_by_page": {},
                        }
                    )
                return real_loader(name, path)

            with (
                mock.patch.object(PIPELINE, "_load_module", side_effect=loader),
                mock.patch.object(
                    PIPELINE,
                    "_materialize_v6_formal_blueprint_manifest",
                    return_value={},
                ),
            ):
                report = PIPELINE.prebuild_project(project)
            self.assertEqual("pass", report["status"])
            self.assertTrue(
                (project / ".build" / "blueprint_alignment_audit.json").is_file()
            )
            self.assertIn("blueprint_alignment_audit", report)

    def test_v6_deconstruct_alignment_blocks_missing_stale_and_wrong_mode_reviews(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            alignment, _ = self.make_reviewed_deconstruct_alignment(project)
            tile = project / ".build" / "visual_review_tiles" / "S01" / "Q1.png"
            tile.unlink()
            with self.assertRaisesRegex(ValueError, "review"):
                PIPELINE._validate_v6_deconstruct_alignment(
                    project, brief("deconstruct"), alignment
                )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            alignment, _ = self.make_reviewed_deconstruct_alignment(project)
            Image.new("RGB", (100, 100), "red").save(
                project / "blueprints" / "S01.png"
            )
            with self.assertRaisesRegex(ValueError, "stale"):
                PIPELINE._validate_v6_deconstruct_alignment(
                    project, brief("deconstruct"), alignment
                )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            alignment, _ = self.make_reviewed_deconstruct_alignment(project)
            alignment["construction_mode"] = "bitmap"
            with self.assertRaisesRegex(ValueError, "header"):
                PIPELINE._validate_v6_deconstruct_alignment(
                    project, brief("deconstruct"), alignment
                )

    def test_imagegen_failures_do_not_switch_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "project_brief.json").write_text(
                json.dumps(brief("deconstruct")), encoding="utf-8"
            )
            unavailable = GATE.record_failure(
                project, "S01", "tool_unavailable", transport_attempt_count=1
            )
            self.assertEqual("IMAGEGEN_UNAVAILABLE", unavailable["error_code"])
            self.assertFalse(unavailable["resumable"])
            self.assertEqual("deconstruct", unavailable["construction_mode"])

    def test_transport_failure_allows_only_one_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "project_brief.json").write_text(
                json.dumps(brief("bitmap")), encoding="utf-8"
            )
            first = GATE.record_failure(
                project, "S01", "empty_response", transport_attempt_count=1
            )
            second = GATE.record_failure(
                project, "S01", "empty_response", transport_attempt_count=2
            )
            self.assertTrue(first["resumable"])
            self.assertIsNone(first["error_code"])
            self.assertFalse(second["resumable"])
            self.assertEqual("BLUEPRINT_TRANSPORT_FAILED", second["error_code"])
            source = project / "candidate.png"
            Image.new("RGB", (1600, 900), "white").save(source)
            with self.assertRaisesRegex(ValueError, "terminal"):
                GATE.record_artifact(
                    project, "S01", source, transport_attempt_count=2
                )

    def test_blueprint_transport_terminal_state_is_irreversible(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "project_brief.json").write_text(
                json.dumps(brief("deconstruct")), encoding="utf-8"
            )
            GATE.record_failure(
                project, "S01", "tool_unavailable", transport_attempt_count=1
            )
            source = project / "candidate.png"
            Image.new("RGB", (1600, 900), "white").save(source)
            with self.assertRaisesRegex(ValueError, "terminal"):
                GATE.record_artifact(
                    project, "S01", source, transport_attempt_count=1
                )
            with self.assertRaisesRegex(ValueError, "terminal"):
                GATE.record_failure(
                    project, "S01", "empty_response", transport_attempt_count=1
                )

    def test_blueprint_transport_rejects_repeated_attempt_one(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "project_brief.json").write_text(
                json.dumps(brief("bitmap")), encoding="utf-8"
            )
            GATE.record_failure(
                project, "S01", "empty_response", transport_attempt_count=1
            )
            with self.assertRaisesRegex(ValueError, "next transport attempt"):
                GATE.record_failure(
                    project, "S01", "empty_response", transport_attempt_count=1
                )

    def test_compile_dispatches_without_silent_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "project_brief.json").write_text(
                json.dumps(brief("deconstruct")), encoding="utf-8"
            )
            (project / ".build").mkdir()
            (project / ".build" / "runtime_report.json").write_text(
                json.dumps({"builder_backend": "mac_python_pptx_v2"}), encoding="utf-8"
            )
            with (
                mock.patch.object(PIPELINE, "prebuild_project") as prebuild,
                mock.patch.object(PIPELINE, "_load_module") as loader,
            ):
                compiler = SimpleNamespace(
                    compile_project=lambda *args, **kwargs: project / "generate_deck.py"
                )
                loader.return_value = compiler
                PIPELINE.compile_project(project)
                prebuild.assert_called_once_with(project)
                self.assertTrue(
                    str(loader.call_args_list[-1].args[1]).endswith(
                        "project_compiler_mac_v2.py"
                    )
                )

    def test_bitmap_compile_materializes_post_lock_inputs_before_compiler_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            (project / "project_brief.json").write_text(
                json.dumps(brief("bitmap")), encoding="utf-8"
            )
            (build / "runtime_report.json").write_text(
                json.dumps({"builder_backend": "windows_com_v584"}),
                encoding="utf-8",
            )
            source = project / "source.png"
            Image.new("RGB", (1600, 900), "white").save(source)
            GATE.record_artifact(
                project,
                "S01",
                source,
                transport_attempt_count=1,
            )
            (build / "slides.json").write_text(
                json.dumps(
                    [
                        {
                            "slide_id": "S01",
                            "chapter": "Chapter",
                            "title": "Title",
                            "core_points": ["Core"],
                            "source": "Source",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            review = BITMAP.prepare_bitmap_review(project)
            (build / "bitmap_alignment.json").write_text(
                json.dumps(
                    {
                        "schema_version": "6.0",
                        "pipeline_revision": "6.0.0",
                        "construction_mode": "bitmap",
                        "pages": {
                            "S01": {
                                "reviewed_full_page": True,
                                "blueprint_sha256": review["pages"]["S01"][
                                    "blueprint_sha256"
                                ],
                                "source_px": [20, 250, 1580, 850],
                                "excluded_skeleton_regions": list(
                                    BITMAP.EXCLUDED_SKELETON_REGIONS
                                ),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            generator = PIPELINE.compile_project(project)

            self.assertTrue(generator.is_file())
            for name in (
                "formal_blueprint_manifest.json",
                "bitmap_contract.json",
                "bitmap_page_specs.json",
            ):
                self.assertTrue((build / name).is_file(), name)

    def test_formal_blueprint_bytes_are_identical_across_modes(self):
        payload = Image.new("RGB", (20, 20), "blue")
        outputs = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for mode in ("deconstruct", "bitmap"):
                project = root / mode
                (project / ".build" / "design_drafts").mkdir(parents=True)
                (project / "blueprints").mkdir()
                payload.save(project / "blueprints" / "S01.png")
                draft = project / ".build" / "design_drafts" / "S01.png"
                draft.write_bytes((project / "blueprints" / "S01.png").read_bytes())
                digest = PIPELINE._sha256_file(draft)
                (project / ".build" / "visual_manifest.json").write_text(
                    json.dumps(
                        {
                            "pages": {
                                "S01": {
                                    "design_draft_sha256": digest,
                                    "formal_blueprint_sha256": digest,
                                    "formal_blueprint_path": "blueprints/S01.png",
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                PIPELINE._materialize_v6_formal_blueprint_manifest(
                    project, brief(mode)
                )
                outputs.append((project / "blueprints" / "S01.png").read_bytes())
        self.assertEqual(outputs[0], outputs[1])

    def test_nine_page_preprocess_batches_resume_and_isolate_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project, page_count=9)
            first, reusable = PIPELINE._v6_preprocess_batches(
                project, value, "windows_com_v584"
            )
            self.assertEqual([5, 4], [len(item["slide_ids"]) for item in first["batches"]])
            self.assertEqual(set(), reusable)
            alignment = json.loads(
                (project / ".build" / "blueprint_alignment.json").read_text(
                    encoding="utf-8"
                )
            )
            for item in first["batches"]:
                PIPELINE._write_v6_batch_receipt(
                    project, value, item, alignment
                )
            PIPELINE._complete_v6_preprocess_batches(project, first)
            second, reusable = PIPELINE._v6_preprocess_batches(
                project, value, "windows_com_v584"
            )
            self.assertEqual(9, len(reusable))
            self.assertTrue(
                all(item["preprocess_status"] == "reused" for item in second["batches"])
            )
            bitmap = dict(value, construction_mode="bitmap")
            source = project / ".build" / "blueprint_alignment.json"
            target = project / ".build" / "bitmap_alignment.json"
            payload = json.loads(source.read_text(encoding="utf-8"))
            payload["construction_mode"] = "bitmap"
            target.write_text(json.dumps(payload), encoding="utf-8")
            third, reusable = PIPELINE._v6_preprocess_batches(
                project, bitmap, "windows_com_v584"
            )
            self.assertEqual(set(), reusable)
            self.assertTrue(
                all(item["preprocess_status"] == "pending" for item in third["batches"])
            )
            self.assertFalse(third["whole_deck_build_batched"])

    def test_batch_two_failure_persists_batch_one_and_repair_reuses_it(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project, page_count=9)
            plan, reusable = PIPELINE._v6_preprocess_batches(
                project, value, "windows_com_v584"
            )
            seen = []

            def fail_second(_project, alignment, **kwargs):
                slide_ids = sorted(alignment["pages"])
                seen.append(slide_ids)
                if "S06" in slide_ids:
                    raise RuntimeError("batch two failed")

            with (
                mock.patch.object(
                    PIPELINE, "_validate_v6_deconstruct_alignment"
                ),
                mock.patch.object(
                    PIPELINE,
                    "_materialize_v6_deconstruct_assets",
                    side_effect=fail_second,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "batch two"):
                    PIPELINE._execute_v6_preprocess_batches(
                        project, value, "windows_com_v584", plan, reusable
                    )
            persisted = json.loads(
                (project / ".build" / "v6_batch_plan.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("complete", persisted["batches"][0]["preprocess_status"])
            self.assertEqual("failed", persisted["batches"][1]["preprocess_status"])
            repair_plan, reusable = PIPELINE._v6_preprocess_batches(
                project, value, "windows_com_v584"
            )
            self.assertEqual(set(repair_plan["batches"][0]["slide_ids"]), reusable)
            seen.clear()
            with (
                mock.patch.object(
                    PIPELINE, "_validate_v6_deconstruct_alignment"
                ),
                mock.patch.object(
                    PIPELINE,
                    "_materialize_v6_deconstruct_assets",
                    side_effect=lambda _p, alignment, **kwargs: seen.append(
                        sorted(alignment["pages"])
                    ),
                ),
            ):
                PIPELINE._execute_v6_preprocess_batches(
                    project, value, "windows_com_v584", repair_plan, reusable
                )
            self.assertEqual([["S06", "S07", "S08", "S09"]], seen)

    def test_first_success_locks_the_v6_build(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project)
            result = self.run_with_fakes(project, value)
            self.assertTrue(result["ok"])
            attempt = json.loads(
                (project / ".build" / "v6_build_attempt.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("success", attempt["status"])
            with self.assertRaisesRegex(ValueError, "build is locked"):
                self.run_with_fakes(project, value)

    def test_v6_windows_deconstruct_runs_blueprint_fidelity_audit(self):
        self.assertTrue(
            hasattr(
                PIPELINE,
                "_run_v6_windows_deconstruct_fidelity_audit",
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project)
            with mock.patch.object(
                PIPELINE,
                "_run_v6_windows_deconstruct_fidelity_audit",
                return_value={"passed": True, "failed_slide_ids": []},
            ) as fidelity:
                self.run_with_fakes(project, value)
            fidelity.assert_called_once()

    def test_first_catastrophic_failure_allows_exactly_one_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project)
            with self.assertRaisesRegex(RuntimeError, "compile failed"):
                self.run_with_fakes(
                    project, value, compile_error=RuntimeError("compile failed")
                )
            attempt = json.loads(
                (project / ".build" / "v6_build_attempt.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("catastrophic_failed", attempt["status"])
            result = self.run_with_fakes(project, value, repair=True)
            self.assertEqual(2, result["build_attempt"])
            with self.assertRaisesRegex(ValueError, "requires one catastrophic"):
                self.run_with_fakes(project, value, repair=True)

    def test_catastrophic_repair_cannot_switch_construction_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project)
            with self.assertRaisesRegex(RuntimeError, "compile failed"):
                self.run_with_fakes(
                    project, value, compile_error=RuntimeError("compile failed")
                )
            switched = dict(value)
            switched["construction_mode"] = "bitmap"
            with self.assertRaisesRegex(ValueError, "construction mode"):
                self.run_with_fakes(project, switched, repair=True)

    def test_catastrophic_repair_cannot_switch_builder_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project)
            with self.assertRaisesRegex(RuntimeError, "compile failed"):
                self.run_with_fakes(
                    project, value, compile_error=RuntimeError("compile failed")
                )
            with self.assertRaisesRegex(ValueError, "builder backend"):
                self.run_with_fakes(
                    project,
                    value,
                    backend="mac_python_pptx_v2",
                    repair=True,
                )

    def test_bitmap_repair_rejects_changes_outside_bitmap_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project, mode="bitmap")
            with self.assertRaisesRegex(RuntimeError, "compile failed"):
                self.run_with_fakes(
                    project, value, compile_error=RuntimeError("compile failed")
                )
            (project / ".build" / "slides.json").write_text(
                json.dumps([{"slide_id": "S01", "title": "tampered"}]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "repair contract"):
                self.run_with_fakes(project, value, repair=True)

    def test_deconstruct_repair_rejects_changes_outside_blueprint_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project)
            with self.assertRaisesRegex(RuntimeError, "compile failed"):
                self.run_with_fakes(
                    project, value, compile_error=RuntimeError("compile failed")
                )
            (project / ".build" / "visual_manifest.json").write_text(
                json.dumps({"pages": {"S01": {"tampered": True}}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "repair contract"):
                self.run_with_fakes(project, value, repair=True)

    def test_repair_locks_all_build_json_including_imagegen_transport_state(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project)
            transport = project / ".build" / "imagegen_transport_report.json"
            transport.write_text(
                json.dumps({"status": "succeeded", "attempt_count": 1}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "compile failed"):
                self.run_with_fakes(
                    project, value, compile_error=RuntimeError("compile failed")
                )
            transport.write_text(
                json.dumps({"status": "pending", "attempt_count": 0}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "repair contract"):
                self.run_with_fakes(project, value, repair=True)

    def test_second_catastrophic_failure_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project)
            for repair in (False, True):
                with self.assertRaises(RuntimeError):
                    self.run_with_fakes(
                        project,
                        value,
                        compile_error=RuntimeError("compile failed"),
                        repair=repair,
                    )
            with self.assertRaisesRegex(ValueError, "requires one catastrophic"):
                self.run_with_fakes(project, value, repair=True)

    def test_mac_quality_block_is_recorded_and_repairable_once(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            value = self.make_locked_project(project)
            with self.assertRaisesRegex(ValueError, "Mac PPTX audit failed"):
                self.run_with_fakes(
                    project,
                    value,
                    backend="mac_python_pptx_v2",
                    mac_status="blocked",
                )
            attempt = json.loads(
                (project / ".build" / "v6_build_attempt.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("catastrophic_failed", attempt["status"])
            self.assertEqual("mac_quality", attempt["failed_stage"])
            result = self.run_with_fakes(
                project,
                value,
                backend="mac_python_pptx_v2",
                repair=True,
            )
            self.assertEqual(2, result["build_attempt"])


if __name__ == "__main__":
    unittest.main()
