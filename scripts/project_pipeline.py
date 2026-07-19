from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = "5.9"
SUPPORTED_SCHEMA_VERSIONS = {"5.6", "5.7", "5.8", "5.9"}
LATEST_SKILL_VERSION = "5.9.6"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _audit_policy(brief: dict, audit_name: str) -> str:
    policy = _load_module(
        "standard_report_v591_contracts",
        Path(__file__).with_name("v591_contracts.py"),
    )
    return str(policy.audit_policy(brief, audit_name))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def formalize_blueprints(project_dir: str | Path, pptx_path: str | Path) -> dict:
    """Promote immutable ImageGen drafts to the formal V5.8 blueprint set."""

    project_dir = Path(project_dir).resolve()
    pptx_path = Path(pptx_path).resolve()
    brief = _read_json(project_dir / "project_brief.json")
    if brief.get("schema_version") not in {"5.8", "5.9"} or brief.get("production_mode") != "blueprint":
        raise ValueError("formal blueprints are a modern blueprint-mode artifact")
    if not pptx_path.is_file():
        raise FileNotFoundError(pptx_path)
    visual_manifest = _read_json(project_dir / ".build" / "visual_manifest.json")
    blueprint_dir = project_dir / "blueprints"
    blueprint_dir.mkdir(parents=True, exist_ok=True)
    pages: dict[str, dict[str, str]] = {}
    for index in range(1, int(brief["requested_page_count"]) + 1):
        slide_id = f"S{index:02d}"
        rendered = project_dir / ".build" / "rendered" / "current" / f"{slide_id}.png"
        if not rendered.is_file():
            raise FileNotFoundError(rendered)
        draft_record = visual_manifest.get("pages", {}).get(slide_id, {})
        draft = project_dir / str(draft_record.get("design_draft_path", ""))
        if not draft.is_file():
            raise FileNotFoundError(draft)
        draft_hash = _sha256_file(draft)
        if draft_hash != draft_record.get("design_draft_sha256"):
            raise ValueError(f"{slide_id}: ImageGen design draft SHA-256 mismatch")
        formal = blueprint_dir / f"{slide_id}.png"
        if brief.get("schema_version") == "5.9":
            if not formal.is_file():
                raise FileNotFoundError(formal)
        else:
            shutil.copyfile(draft, formal)
        render_hash = _sha256_file(rendered)
        formal_hash = _sha256_file(formal)
        if formal_hash != draft_hash:
            raise ValueError(f"{slide_id}: formal blueprint differs from original ImageGen result")
        pages[slide_id] = {
            "design_draft_path": draft.relative_to(project_dir).as_posix(),
            "design_draft_sha256": draft_hash,
            "render_path": rendered.relative_to(project_dir).as_posix(),
            "render_sha256": render_hash,
            "formal_blueprint_path": formal.relative_to(project_dir).as_posix(),
            "formal_blueprint_sha256": formal_hash,
        }
    payload = {
        "schema_version": str(brief["schema_version"]),
        "pptx_path": str(pptx_path),
        "pptx_sha256": _sha256_file(pptx_path),
        "pages": pages,
    }
    _write_json_atomic(project_dir / ".build" / "formal_blueprint_manifest.json", payload)
    return payload


def _timing_path(project_dir: Path) -> Path:
    return project_dir / ".build" / "pipeline_timing.json"


def _project_schema_version(project_dir: Path) -> str:
    brief_path = project_dir / "project_brief.json"
    if brief_path.is_file():
        try:
            version = _read_json(brief_path).get("schema_version")
            if version in SUPPORTED_SCHEMA_VERSIONS:
                return version
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return SCHEMA_VERSION


def _project_skill_version(project_dir: str | Path) -> str:
    project_dir = Path(project_dir)
    brief_path = project_dir / "project_brief.json"
    if brief_path.is_file():
        try:
            brief = _read_json(brief_path)
        except (OSError, ValueError, json.JSONDecodeError):
            brief = {}
        if brief.get("schema_version") == "5.9":
            revision = str(brief.get("pipeline_revision", ""))
            if revision not in {"5.9.0", "5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}:
                raise ValueError(
                    "V5.9 pipeline_revision must be 5.9.0, 5.9.1, 5.9.2, 5.9.4, 5.9.5, or 5.9.6"
                )
            return revision
        if brief.get("schema_version") == "5.8":
            revision = str(brief.get("pipeline_revision", ""))
            return revision if revision in {"5.8.3", "5.8.4"} else "5.8.2"
        if brief.get("schema_version") in {"5.6", "5.7"}:
            return str(brief["schema_version"])
    return SCHEMA_VERSION


def _uses_v583_authoring(project_dir: str | Path) -> bool:
    return _project_skill_version(project_dir) in {
        "5.8.3",
        "5.8.4",
        "5.9.0",
        "5.9.1",
        "5.9.2",
        "5.9.4",
        "5.9.5",
        "5.9.6",
    }


def _uses_v584_alignment(project_dir: str | Path) -> bool:
    return _project_skill_version(project_dir) in {
        "5.8.4",
        "5.9.0",
        "5.9.1",
        "5.9.2",
        "5.9.4",
        "5.9.5",
        "5.9.6",
    }


def _is_v583(project_dir: str | Path) -> bool:
    """Compatibility alias for callers that imported the former private helper."""
    return _uses_v583_authoring(project_dir)


def _is_v584(project_dir: str | Path) -> bool:
    """Compatibility alias for callers that imported the former private helper."""
    return _uses_v584_alignment(project_dir)


def _ensure_project_runtime(
    project_dir: Path,
    brief: dict,
    *,
    probe_windows_com: bool,
) -> dict:
    if brief.get("schema_version") != "5.9":
        runtime = _load_module(
            "standard_report_windows_runtime_legacy",
            Path(__file__).with_name("ensure_windows_runtime.py"),
        )
        return runtime.ensure_windows_runtime(
            project_dir=project_dir, probe_com=probe_windows_com
        )
    platform = _load_module(
        "standard_report_v59_platform_runtime",
        Path(__file__).with_name("v59_platform.py"),
    )
    selection = platform.require_supported_backend(platform.select_backend())
    report = platform.write_runtime_report(project_dir, selection)
    if selection.backend == "windows_com_v584":
        runtime = _load_module(
            "standard_report_windows_runtime_v59",
            Path(__file__).with_name("ensure_windows_runtime.py"),
        )
        runtime.ensure_windows_runtime(
            project_dir=project_dir, probe_com=probe_windows_com
        )
    elif selection.backend == "mac_python_pptx_v1":
        runtime = _load_module(
            "standard_report_macos_runtime_v59",
            Path(__file__).with_name("ensure_macos_runtime.py"),
        )
        runtime.ensure_macos_runtime(project_dir=project_dir)
    else:
        raise RuntimeError(f"unsupported builder backend: {selection.backend}")
    return report


def _record_timing(project_dir: Path, stage: str, start: float, end: float, *, ok: bool, note: str = "") -> None:
    if _uses_v583_authoring(project_dir):
        timing = _load_module(
            "standard_report_v583_timing_record",
            Path(__file__).with_name("v583_timing.py"),
        )
        timing.record_stage(project_dir, stage, start, end, ok=ok, note=note)
        return
    path = _timing_path(project_dir)
    payload = _read_json(path) if path.is_file() else {"schema_version": _project_schema_version(project_dir), "stages": []}
    payload["stages"].append({
        "stage": stage,
        "start_epoch": start,
        "end_epoch": end,
        "duration_seconds": round(end - start, 3),
        "duration_minutes": round((end - start) / 60.0, 3),
        "ok": ok,
        "note": note,
    })
    _write_json_atomic(path, payload)


def _stage(project_dir: Path, name: str, action: Callable[[], Any]) -> Any:
    start = time.time()
    try:
        result = action()
    except Exception as exc:
        _record_timing(project_dir, name, start, time.time(), ok=False, note=str(exc))
        raise
    _record_timing(project_dir, name, start, time.time(), ok=True)
    return result


def validate_brief(brief: dict) -> list[str]:
    errors: list[str] = []
    if brief.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"schema_version must be one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    count = brief.get("requested_page_count")
    if not isinstance(count, int) or count <= 0:
        errors.append("requested_page_count must be a positive integer")
    mode = brief.get("production_mode")
    if mode not in {"blueprint", "fast"}:
        errors.append("production_mode must be blueprint or fast")
    schema = brief.get("schema_version")
    revision = brief.get("pipeline_revision")
    if schema == "5.9":
        if revision not in {"5.9.0", "5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}:
            errors.append(
                "V5.9 pipeline_revision must be 5.9.0, 5.9.1, 5.9.2, 5.9.4, 5.9.5, or 5.9.6"
            )
        if brief.get("platform_target") != "auto":
            errors.append("V5.9 platform_target must be auto")
        if mode == "blueprint" and brief.get("blueprint_engine") != "builtin_imagegen":
            errors.append("V5.9 blueprint mode requires blueprint_engine=builtin_imagegen")
        source_files = brief.get("source_files")
        if not isinstance(source_files, list) or not source_files:
            errors.append("V5.9 requires a non-empty source_files list")
    else:
        if mode == "blueprint" and brief.get("blueprint_engine") != "direct":
            errors.append("blueprint mode requires blueprint_engine=direct")
        if revision is not None and revision not in {"5.8.3", "5.8.4"}:
            errors.append("pipeline_revision must be 5.8.3 or 5.8.4 when supplied")
        if revision in {"5.8.3", "5.8.4"}:
            source_files = brief.get("source_files")
            if not isinstance(source_files, list) or not source_files:
                errors.append(f"V{revision} requires a non-empty source_files list")
    return errors


def preflight_project(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir).resolve()
    skill_dir = Path(__file__).resolve().parent.parent
    brief_path = project_dir / "project_brief.json"
    if not brief_path.is_file():
        raise FileNotFoundError(brief_path)
    brief = _read_json(brief_path)
    errors = validate_brief(brief)
    if errors:
        raise ValueError("; ".join(errors))
    runtime_report = _ensure_project_runtime(
        project_dir, brief, probe_windows_com=True
    )

    required = [
        skill_dir / "assets" / "company_template.pptx",
        skill_dir / "assets" / "direct_blueprint_generator_template.py",
        skill_dir / "scripts" / "project_compiler.py",
        skill_dir / "scripts" / "v56_contracts.py",
        skill_dir / "scripts" / "v56_page_cache.py",
        skill_dir / "scripts" / "v58_prebuild.py",
        skill_dir / "scripts" / "v58_visual_policy.py",
        skill_dir / "scripts" / "v58_template_contract.py",
        skill_dir / "scripts" / "v58_source_cache.py",
        skill_dir / "scripts" / "v58_text_benchmark.py",
        skill_dir / "scripts" / "v582_quality.py",
        skill_dir / "scripts" / "ensure_windows_runtime.py",
        skill_dir / "scripts" / "render_slides.py",
        skill_dir / "scripts" / "ppt_text_audit.py",
        skill_dir / "scripts" / "ppt_skeleton_audit.py",
        skill_dir / "scripts" / "pack_delivery.py",
        skill_dir / "requirements-windows.lock",
    ]
    if brief.get("pipeline_revision") in {
        "5.8.3",
        "5.8.4",
        "5.9.0",
        "5.9.1",
        "5.9.2",
        "5.9.4",
        "5.9.5",
        "5.9.6",
    }:
        required.extend([
            skill_dir / "scripts" / "v583_source_ingest.py",
            skill_dir / "scripts" / "v583_authoring.py",
            skill_dir / "scripts" / "v583_timing.py",
        ])
    if brief.get("pipeline_revision") in {
        "5.8.4",
        "5.9.0",
        "5.9.1",
        "5.9.2",
        "5.9.4",
        "5.9.5",
        "5.9.6",
    }:
        required.extend([
            skill_dir / "scripts" / "v583_source_ingest.py",
            skill_dir / "scripts" / "v583_authoring.py",
            skill_dir / "scripts" / "v583_timing.py",
            skill_dir / "scripts" / "v584_blueprint_alignment.py",
            skill_dir / "scripts" / "blueprint_alignment_audit.py",
        ])
    if brief.get("pipeline_revision") in {"5.9.0", "5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}:
        required.extend([
            skill_dir / "scripts" / "v59_platform.py",
            skill_dir / "scripts" / "v59_blueprint_gate.py",
            skill_dir / "scripts" / "ensure_macos_runtime.py",
            skill_dir / "scripts" / "project_compiler_mac.py",
            skill_dir / "scripts" / "mac_render_slides.py",
            skill_dir / "scripts" / "mac_quality.py",
            skill_dir / "scripts" / "v591_contracts.py",
            skill_dir / "scripts" / "v591_reconstruction_contract.py",
            skill_dir / "scripts" / "v595_release.py",
            skill_dir / "scripts" / "v596_visual_review.py",
            skill_dir / "assets" / "python_pptx_generator_template.py",
            skill_dir / "assets" / "vendor" / "fonttools-4.63.0-py3.zip",
            skill_dir / "requirements-macos.lock",
        ])
    if brief["production_mode"] == "blueprint":
        required.extend([
            skill_dir / "scripts" / "compose_blueprint.py",
            skill_dir / "scripts" / "extract_direct_assets.py",
            skill_dir / "scripts" / "ppt_asset_audit.py",
            skill_dir / "scripts" / "blueprint_fidelity.py",
        ])
    missing = [str(path.relative_to(skill_dir)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing manifest-pipeline resources: " + ", ".join(missing))

    for path in required:
        if path.suffix == ".py":
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    packager = _load_module("standard_report_packager_preflight", skill_dir / "scripts" / "pack_delivery.py")
    validator = {
        "5.6": "_validate_v56_project",
        "5.7": "_validate_v57_project",
        "5.8": "_validate_v58_project",
        "5.9": "_validate_v59_project",
    }[brief["schema_version"]]
    if not hasattr(packager, validator):
        raise RuntimeError(f"pack_delivery.py does not provide native {brief['schema_version']} validation")

    app = None
    presentation = None
    com_initialized = False
    try:
        if runtime_report.get("builder_backend") == "mac_python_pptx_v1":
            from pptx import Presentation

            presentation = Presentation(
                skill_dir / "assets" / "company_template.pptx"
            )
            if presentation.slide_width <= 0 or presentation.slide_height <= 0:
                raise RuntimeError("company template has invalid slide dimensions")
            presentation = None
            return {
                "schema_version": brief["schema_version"],
                "ok": True,
                "mode": brief["production_mode"],
                "builder_backend": "mac_python_pptx_v1",
                "checks": [
                    "brief", "resources", "python_syntax",
                    "macos_runtime", "python_pptx_template",
                ],
            }
        import win32com.client
        import pythoncom

        pythoncom.CoInitialize()
        com_initialized = True
        app = win32com.client.DispatchEx("PowerPoint.Application")
        presentation = app.Presentations.Open(
            str(skill_dir / "assets" / "company_template.pptx"), False, True, False
        )
        if presentation.PageSetup.SlideWidth <= 0 or presentation.PageSetup.SlideHeight <= 0:
            raise RuntimeError("company template has invalid slide dimensions")
    finally:
        if presentation is not None:
            presentation.Close()
        if app is not None:
            app.Quit()
        if com_initialized:
            pythoncom.CoUninitialize()

    return {
        "schema_version": brief["schema_version"],
        "ok": True,
        "mode": brief["production_mode"],
        "checks": ["brief", "resources", "python_syntax", "v56_packager", "windows_runtime", "powerpoint_template"],
    }


def init_project(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir).resolve()
    brief_path = project_dir / "project_brief.json"
    if not brief_path.is_file():
        raise FileNotFoundError(brief_path)
    brief = _read_json(brief_path)
    errors = validate_brief(brief)
    if errors:
        raise ValueError("; ".join(errors))
    runtime_report = _ensure_project_runtime(
        project_dir, brief, probe_windows_com=False
    )
    directories = [".build", ".build/pages", ".build/rendered/current", "output"]
    if brief["production_mode"] == "blueprint":
        directories.extend(["blueprints", ".build/raw_blueprints", ".build/design_drafts", ".build/assets"])
    for relative in directories:
        (project_dir / relative).mkdir(parents=True, exist_ok=True)
    if brief["schema_version"] in {"5.8", "5.9"}:
        skill_dir = Path(__file__).resolve().parents[1]
        template_contract = _load_module(
            "standard_report_v58_template_contract_init",
            Path(__file__).with_name("v58_template_contract.py"),
        )
        _write_json_atomic(
            project_dir / ".build" / "template_contract.json",
            template_contract.inspect_template(skill_dir / "assets" / "company_template.pptx"),
        )
    if brief.get("pipeline_revision") in {
        "5.8.3",
        "5.8.4",
        "5.9.0",
        "5.9.1",
        "5.9.2",
        "5.9.4",
    }:
        timing = _load_module(
            "standard_report_v583_timing_init",
            Path(__file__).with_name("v583_timing.py"),
        )
        timing.initialize_timing(project_dir, preserve=True)
        ingest = _load_module(
            "standard_report_v583_source_ingest_init",
            Path(__file__).with_name("v583_source_ingest.py"),
        )
        start = time.time()
        try:
            ingest_result = ingest.ingest_project_sources(project_dir)
        except Exception as exc:
            timing.record_stage(
                project_dir,
                "source_parse",
                start,
                time.time(),
                ok=False,
                note=str(exc),
            )
            raise
        for record in ingest_result.get("stages", []):
            if not isinstance(record, dict):
                continue
            timing.record_stage(
                project_dir,
                str(record.get("stage", "source_parse")),
                float(record.get("start_epoch", start)),
                float(record.get("end_epoch", time.time())),
                ok=True,
                cache_hit=bool(record.get("cache_hit")),
                attempt_count=1,
            )
    else:
        timing = {"schema_version": brief["schema_version"], "stages": []}
        _write_json_atomic(_timing_path(project_dir), timing)
    return {
        "schema_version": brief["schema_version"],
        "skill_version": _project_skill_version(project_dir),
        "project": str(project_dir),
        "mode": brief["production_mode"],
        "builder_backend": runtime_report.get("builder_backend"),
    }


def materialize_project(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir).resolve()
    if not _uses_v583_authoring(project_dir):
        return {"schema_version": _project_schema_version(project_dir), "ok": True, "compatibility": True}
    authoring = _load_module(
        "standard_report_v583_authoring_pipeline",
        Path(__file__).with_name("v583_authoring.py"),
    )
    result = _stage(project_dir, "canonical_materialize", lambda: authoring.materialize_project(project_dir))
    if (
        _project_skill_version(project_dir) == "5.9.6"
        and any((project_dir / "blueprints").glob("S[0-9][0-9].png"))
    ):
        review = _load_module(
            "standard_report_v596_visual_review_materialize",
            Path(__file__).with_name("v596_visual_review.py"),
        )
        _stage(
            project_dir,
            "visual_review_tiles",
            lambda: review.generate_review_tiles(project_dir),
        )
    alignment_path = project_dir / ".build" / "blueprint_alignment.json"
    if _uses_v584_alignment(project_dir) and alignment_path.is_file():
        alignment = _load_module(
            "standard_report_v584_alignment_materialize",
            Path(__file__).with_name("v584_blueprint_alignment.py"),
        )
        return _stage(
            project_dir,
            "blueprint_alignment",
            lambda: alignment.apply_project_alignment(project_dir),
        )
    if _uses_v584_alignment(project_dir):
        result = dict(result)
        result["skill_version"] = _project_skill_version(project_dir)
        result["alignment_pending"] = True
    return result


def prepare_visual_review(project_dir: str | Path) -> dict:
    project = Path(project_dir).resolve()
    brief = _read_json(project / "project_brief.json")
    if (
        brief.get("schema_version") != "5.9"
        or brief.get("pipeline_revision") != "5.9.6"
        or brief.get("production_mode") != "blueprint"
    ):
        raise ValueError(
            "visual review tiles are a V5.9.6 blueprint-mode post-lock artifact"
        )
    generator = _load_module(
        "standard_report_v596_prepare_visual_review",
        Path(__file__).with_name("v596_visual_review.py"),
    )
    return generator.generate_review_tiles(project)


def _materialize_v583_if_present(project_dir: Path) -> None:
    bundle = project_dir / ".build" / "authoring_bundle.json"
    if not _uses_v583_authoring(project_dir) or not bundle.is_file():
        return
    if _uses_v584_alignment(project_dir):
        alignment = _load_module(
            "standard_report_v584_alignment_runtime",
            Path(__file__).with_name("v584_blueprint_alignment.py"),
        )
        _stage(
            project_dir,
            "blueprint_alignment",
            lambda: alignment.apply_project_alignment(project_dir),
        )
        return
    report_path = project_dir / ".build" / "authoring_report.json"
    if report_path.is_file():
        try:
            report = _read_json(report_path)
        except (OSError, ValueError, json.JSONDecodeError):
            report = {}
        manifests_current = all(
            (project_dir / ".build" / name).is_file()
            for name in ("slides.json", "page_specs.json", "visual_manifest.json", "blueprint_text_benchmark.json")
        )
        draft_hashes_current = False
        if manifests_current:
            try:
                manifest = _read_json(project_dir / ".build" / "visual_manifest.json")
            except (OSError, ValueError, json.JSONDecodeError):
                manifest = {}
            current_hashes: dict[str, str] = {}
            for slide_id, page in manifest.get("pages", {}).items():
                if not isinstance(page, dict):
                    continue
                relative = page.get("design_draft_path")
                draft = project_dir / str(relative) if isinstance(relative, str) else project_dir / ".missing"
                current_hashes[str(slide_id)] = _sha256_file(draft) if draft.is_file() else ""
            draft_hashes_current = report.get("design_draft_hashes") == current_hashes
        if (
            report.get("authoring_bundle_sha256") == _sha256_file(bundle)
            and manifests_current
            and draft_hashes_current
        ):
            return
    materialize_project(project_dir)


def compile_project(project_dir: str | Path) -> Path:
    project_dir = Path(project_dir).resolve()
    _materialize_v583_if_present(project_dir)
    brief = _read_json(project_dir / "project_brief.json")
    runtime_path = project_dir / ".build" / "runtime_report.json"
    if brief.get("schema_version") != "5.9" and not runtime_path.is_file():
        compiler = _load_module(
            "standard_report_legacy_compiler",
            Path(__file__).with_name("project_compiler.py"),
        )
        return _stage(
            project_dir, "compile", lambda: compiler.compile_project(project_dir)
        )
    if (
        brief.get("schema_version") == "5.9"
        and brief.get("production_mode") == "blueprint"
    ):
        gate = _load_module(
            "standard_report_v59_blueprint_gate_compile",
            Path(__file__).with_name("v59_blueprint_gate.py"),
        )
        gate.assert_blueprint_gate(project_dir, require_alignment=True)
    if not runtime_path.is_file():
        raise RuntimeError("V5.9 runtime report is missing; run --init first")
    backend = _read_json(runtime_path).get("builder_backend")
    if backend == "mac_python_pptx_v1":
        compiler_path = Path(__file__).with_name("project_compiler_mac.py")
        module_name = "standard_report_v59_mac_compiler"
    elif backend == "windows_com_v584":
        compiler_path = Path(__file__).with_name("project_compiler.py")
        module_name = "standard_report_v59_windows_compiler"
    else:
        raise RuntimeError(f"unsupported or missing builder backend: {backend}")
    compiler = _load_module(module_name, compiler_path)
    return _stage(project_dir, "compile", lambda: compiler.compile_project(project_dir))


def _quality_module():
    return _load_module(
        "standard_report_v582_quality_pipeline",
        Path(__file__).with_name("v582_quality.py"),
    )


def _quality_fields(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir)
    runtime_path = project / ".build" / "runtime_report.json"
    runtime = _read_json(runtime_path) if runtime_path.is_file() else {}
    shared_path = project / ".build" / "quality_report.json"
    shared = _read_json(shared_path) if shared_path.is_file() else {}
    if runtime.get("builder_backend") == "mac_python_pptx_v1":
        mac_path = project / ".build" / "mac_quality_report.json"
        mac = _read_json(mac_path) if mac_path.is_file() else {}
        warning_count = int(
            shared.get("warning_count", len(shared.get("warnings", [])))
        ) + int(mac.get("warning_count", len(mac.get("warnings", []))))
        blocker_count = int(
            shared.get("blocker_count", len(shared.get("blockers", [])))
        ) + int(mac.get("blocker_count", len(mac.get("errors", []))))
        mac_status = str(mac.get("status", "pass"))
        if blocker_count or mac_status == "blocked":
            status = "blocked"
        elif mac_status == "structurally_valid_unrendered":
            status = "structurally_valid_unrendered"
        elif warning_count or mac_status == "pass_with_warnings":
            status = "pass_with_warnings"
        else:
            status = "pass"
        return {
            "quality_status": status,
            "warning_count": warning_count,
            "blocker_count": blocker_count,
        }
    if not shared:
        return {"quality_status": "pass", "warning_count": 0, "blocker_count": 0}
    return {
        "quality_status": str(shared.get("status", "pass")),
        "warning_count": int(
            shared.get("warning_count", len(shared.get("warnings", [])))
        ),
        "blocker_count": int(
            shared.get("blocker_count", len(shared.get("blockers", [])))
        ),
    }


def _append_quality(project_dir: Path, *, warnings: list[dict] | None = None, blockers: list[dict] | None = None) -> dict:
    quality = _quality_module()
    path = project_dir / ".build" / "quality_report.json"
    existing = _read_json(path) if path.is_file() else quality.summarize([], [])
    added = quality.summarize(warnings or [], blockers or [])
    return quality.write_report(project_dir, existing, added)


def _warning_only_quality(payload: dict | None) -> dict:
    quality = _quality_module()
    warnings = [
        item
        for item in (payload or {}).get("warnings", [])
        if isinstance(item, dict)
    ]
    return quality.summarize(warnings, [])


def _v596_review_tile_report(
    project_dir: str | Path,
    brief: dict,
    alignment_payload: dict,
) -> dict:
    if brief.get("pipeline_revision") != "5.9.6":
        return {
            "schema_version": "5.9",
            "skill_version": str(brief.get("pipeline_revision", "")),
            "status": "pass",
            "ok": True,
            "warnings": [],
            "blockers": [],
            "warning_count": 0,
            "blocker_count": 0,
        }
    validator = _load_module(
        "standard_report_v596_review_tiles",
        Path(__file__).with_name("v596_visual_review.py"),
    )
    errors = validator.validate_review_tiles(project_dir, alignment_payload)
    blockers = [
        {
            "code": "VISUAL_REVIEW_TILE_CONTRACT",
            "severity": "blocker",
            "stage": "blueprint_alignment",
            "slide_id": None,
            "message": str(message),
            "metrics": {},
        }
        for message in errors
    ]
    return {
        "schema_version": "5.9",
        "skill_version": "5.9.6",
        "status": "blocked" if blockers else "pass",
        "ok": not blockers,
        "warnings": [],
        "blockers": blockers,
        "warning_count": 0,
        "blocker_count": len(blockers),
    }


def prebuild_project(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir).resolve()
    brief = _read_json(project_dir / "project_brief.json")
    if (
        brief.get("schema_version") == "5.9"
        and brief.get("pipeline_revision") in {"5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}
        and brief.get("production_mode") == "blueprint"
    ):
        alignment = _load_module(
            "standard_report_v591_alignment_prebuild",
            Path(__file__).with_name("v584_blueprint_alignment.py"),
        )
        alignment.apply_project_alignment(project_dir)
        slides = _read_json(project_dir / ".build" / "slides.json")
        page_specs = _read_json(project_dir / ".build" / "page_specs.json")
        alignment_payload = _read_json(
            project_dir / ".build" / "blueprint_alignment.json"
        )
        tile_report = _v596_review_tile_report(
            project_dir,
            brief,
            alignment_payload,
        )
        runtime = _read_json(project_dir / ".build" / "runtime_report.json")
        validator = _load_module(
            "standard_report_v591_reconstruction_prebuild",
            Path(__file__).with_name("v591_reconstruction_contract.py"),
        )
        report = validator.validate_reconstruction_contract(
            brief,
            slides,
            page_specs,
            alignment_payload,
            str(runtime.get("builder_backend", "")),
        )
        _write_json_atomic(
            project_dir / ".build" / "reconstruction_precheck.json",
            report,
        )
        alignment_report = _read_json(
            project_dir / ".build" / "blueprint_alignment_report.json"
        )
        quality = _quality_module()
        quality_report = quality.write_report(
            project_dir,
            alignment_report,
            tile_report,
            report,
        )
        result = {
            "schema_version": "5.9",
            "skill_version": str(brief.get("pipeline_revision")),
            "ok": quality_report["blocker_count"] == 0,
            "errors": [
                item["message"] for item in quality_report["blockers"]
            ],
            "warnings": quality_report["warnings"],
            "quality_status": quality_report["status"],
            "warning_count": quality_report["warning_count"],
            "blocker_count": quality_report["blocker_count"],
        }
        _write_json_atomic(project_dir / ".build" / "prebuild_report.json", result)
        combined_blockers = tile_report["blockers"] + report["blockers"]
        if combined_blockers:
            raise ValueError(
                "prebuild validation failed: "
                + "; ".join(item["message"] for item in combined_blockers)
            )
        return result
    if brief.get("schema_version") != "5.8":
        return {"schema_version": brief.get("schema_version"), "ok": True, "compatibility": True}
    if brief.get("pipeline_revision") == "5.8.4" and brief.get("production_mode") == "blueprint":
        alignment = _load_module(
            "standard_report_v584_alignment_prebuild",
            Path(__file__).with_name("v584_blueprint_alignment.py"),
        )
        alignment.apply_project_alignment(project_dir)
    slides = _read_json(project_dir / ".build" / "slides.json")
    page_specs = _read_json(project_dir / ".build" / "page_specs.json")
    manifest_path = project_dir / ".build" / "visual_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else None
    quality = _quality_module()
    validator = _load_module("standard_report_v58_prebuild_pipeline", Path(__file__).with_name("v58_prebuild.py"))
    diagnostics = [validator.diagnose_project_specs(brief, slides, page_specs, manifest)]
    if brief.get("pipeline_revision") in {"5.8.3", "5.8.4"}:
        layout_report = validator.diagnose_layout(page_specs)
        _write_json_atomic(project_dir / ".build" / "layout_precheck.json", layout_report)
    if brief.get("pipeline_revision") == "5.8.4":
        alignment_report_path = project_dir / ".build" / "blueprint_alignment_report.json"
        if alignment_report_path.is_file():
            diagnostics.append(_read_json(alignment_report_path))
        alignment_audit = _load_module(
            "standard_report_v584_alignment_audit_prebuild",
            Path(__file__).with_name("blueprint_alignment_audit.py"),
        )
        diagnostics.append(alignment_audit.audit_project(project_dir))
    if brief.get("production_mode") == "blueprint":
        contracts = _load_module(
            "standard_report_v582_visual_contracts_pipeline",
            Path(__file__).with_name("v56_contracts.py"),
        )
        if not isinstance(manifest, dict):
            diagnostics.append(
                quality.summarize(
                    [],
                    [quality.issue("VISUAL_MANIFEST_MISSING", "blocker", "blueprint", "visual_manifest.json is missing")],
                )
            )
        else:
            diagnostics.append(contracts.diagnose_visual_manifest(manifest))
            for slide_id, page in manifest.get("pages", {}).items():
                if not isinstance(page, dict):
                    continue
                relative = page.get("design_draft_path")
                draft = project_dir / relative if isinstance(relative, str) else project_dir / ".missing-blueprint"
                assessment = quality.assess_blueprint(draft, str(slide_id))
                diagnostics.append(assessment)
                if draft.is_file() and isinstance(page.get("design_draft_sha256"), str):
                    actual_hash = _sha256_file(draft)
                    if actual_hash != page.get("design_draft_sha256"):
                        diagnostics.append(
                            quality.summarize(
                                [],
                                [
                                    quality.issue(
                                        "BLUEPRINT_HASH_MISMATCH",
                                        "blocker",
                                        "blueprint",
                                        "locked ImageGen blueprint hash does not match visual_manifest.json",
                                        str(slide_id),
                                    )
                                ],
                            )
                        )
    if brief.get("production_mode") == "blueprint":
        benchmark_module = _load_module(
            "standard_report_v58_text_benchmark_pipeline",
            Path(__file__).with_name("v58_text_benchmark.py"),
        )
        benchmark_path = project_dir / ".build" / "blueprint_text_benchmark.json"
        if not benchmark_path.is_file():
            diagnostics.append(
                quality.summarize(
                    [
                        quality.issue(
                            "BLUEPRINT_TEXT_BENCHMARK_MISSING",
                            "warning",
                            "blueprint",
                            "blueprint_text_benchmark.json is missing; canonical PPT text remains authoritative",
                        )
                    ],
                    [],
                )
            )
        elif isinstance(manifest, dict):
            draft_hashes = {
                slide_id: str(page.get("design_draft_sha256", ""))
                for slide_id, page in manifest.get("pages", {}).items()
                if isinstance(page, dict)
            }
            try:
                benchmark_payload = _read_json(benchmark_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                diagnostics.append(
                    quality.summarize(
                        [quality.issue("BLUEPRINT_TEXT_BENCHMARK_INVALID", "warning", "blueprint", str(exc))],
                        [],
                    )
                )
            else:
                benchmark_diagnostics = benchmark_module.diagnose_benchmark(
                    benchmark_payload, slides, page_specs, draft_hashes
                )
                diagnostics.append(benchmark_diagnostics)
                benchmark_payload["ok"] = not benchmark_diagnostics["blockers"]
                benchmark_payload["quality_status"] = benchmark_diagnostics["status"]
                benchmark_payload["warnings"] = benchmark_diagnostics["warnings"]
                benchmark_payload["errors"] = [item["message"] for item in benchmark_diagnostics["blockers"]]
                _write_json_atomic(benchmark_path, benchmark_payload)
    quality_report = quality.write_report(project_dir, *diagnostics)
    errors = [str(item["message"]) for item in quality_report["blockers"]]
    result = {
        "schema_version": brief["schema_version"],
        "skill_version": _project_skill_version(project_dir),
        "ok": not errors,
        "errors": errors,
        "warnings": quality_report["warnings"],
        "quality_status": quality_report["status"],
        "warning_count": quality_report["warning_count"],
        "blocker_count": quality_report["blocker_count"],
    }
    _write_json_atomic(project_dir / ".build" / "prebuild_report.json", result)
    if errors:
        raise ValueError("prebuild validation failed: " + "; ".join(errors))
    return result


def _run(command: list[str], *, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )


def _audit_ok(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        value = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return bool(value.get("ok", value.get("passed", False)))


def _audit_matches_pptx(audit_path: str | Path, pptx_path: str | Path) -> bool:
    audit_path = Path(audit_path)
    pptx_path = Path(pptx_path)
    if not audit_path.is_file() or not pptx_path.is_file():
        return False
    try:
        value = _read_json(audit_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return value.get("ok") is True and value.get("pptx_sha256") == _sha256_file(pptx_path)


def _formal_blueprints_current(project_dir: Path, page_count: int) -> bool:
    path = project_dir / ".build" / "formal_blueprint_manifest.json"
    if not path.is_file():
        return False
    try:
        manifest = _read_json(path)
        for index in range(1, page_count + 1):
            page = manifest.get("pages", {}).get(f"S{index:02d}", {})
            draft = project_dir / str(page.get("design_draft_path", ""))
            formal = project_dir / str(page.get("formal_blueprint_path", ""))
            if not draft.is_file() or not formal.is_file():
                return False
            if _sha256_file(draft) != _sha256_file(formal):
                return False
        return True
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False


def _page_cache_status(project_dir: Path, page_count: int) -> tuple[Any, Path, list[str], bool]:
    cache = _load_module("standard_report_v56_page_cache_pipeline", Path(__file__).with_name("v56_page_cache.py"))
    state_path = project_dir / ".build" / "page_cache.json"
    slide_ids = [f"S{index:02d}" for index in range(1, page_count + 1)]
    all_hit = all(
        cache.page_cache_hit(
            state_path,
            slide_id,
            [project_dir / ".build" / "pages" / f"{slide_id}.input.json"],
            [project_dir / ".build" / "rendered" / "current" / f"{slide_id}.png"],
            salt=_project_schema_version(project_dir),
        )
        for slide_id in slide_ids
    )
    return cache, state_path, slide_ids, all_hit


def _current_delivery(
    project_dir: Path,
    pptx_path: Path,
) -> Path | None:
    record_path = project_dir / ".build" / "delivery_record.json"
    if not record_path.is_file():
        return None
    try:
        record = _read_json(record_path)
        path = Path(str(record.get("zip_path", "")))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if (
        path.is_file()
        and record.get("zip_sha256") == _sha256_file(path)
        and pptx_path.is_file()
        and record.get("pptx_sha256") == _sha256_file(pptx_path)
    ):
        return path
    return None


def _package_v595(
    project_dir: Path,
    pptx_path: Path,
    generator_path: Path,
    *,
    force: bool = False,
) -> Path:
    existing = (
        None
        if force
        else _current_delivery(project_dir, pptx_path)
    )
    if existing is not None:
        return existing
    packager = _load_module(
        "standard_report_v595_auto_package",
        Path(__file__).with_name("pack_delivery.py"),
    )
    return packager.package_direct_delivery(
        project_dir=project_dir,
        pptx_path=pptx_path,
        generator_path=generator_path,
        output_zip=Path.home() / "Desktop" / f"{project_dir.name}.zip",
    )


def run_project(
    project_dir: str | Path,
    output_path: str | Path | None = None,
    *,
    catastrophic_repair: bool = False,
    user_revision: bool = False,
    auto_package: bool = True,
) -> dict:
    project_dir = Path(project_dir).resolve()
    brief = _read_json(project_dir / "project_brief.json")
    errors = validate_brief(brief)
    if errors:
        raise ValueError("; ".join(errors))
    output = Path(output_path) if output_path else project_dir / "output" / "report.pptx"
    is_v595 = brief.get("pipeline_revision") in {"5.9.5", "5.9.6"}
    release = None
    if is_v595:
        release = _load_module(
            "standard_report_v595_release_pipeline",
            Path(__file__).with_name("v595_release.py"),
        )
        locked = release.locked_release(project_dir, output)
        if locked is not None and not user_revision:
            result_path = project_dir / ".build" / "pipeline_result.json"
            if not result_path.is_file():
                raise ValueError(
                    "V5.9.5 locked build is missing pipeline_result.json"
                )
            result = _read_json(result_path)
            result["cached"] = True
            result["postbuild_release"] = locked
            if auto_package:
                result["delivery"] = str(
                    _package_v595(
                        project_dir,
                        output,
                        project_dir / "generate_deck.py",
                    )
                )
                _write_json_atomic(result_path, result)
            return result
        if not release.rebuild_allowed(
            project_dir,
            catastrophic_repair=catastrophic_repair,
            user_revision=user_revision,
        ):
            raise ValueError(
                "V5.9.5 rebuild denied: use --repair-catastrophic only for "
                "the one permitted catastrophic repair, or --user-revision "
                "for an explicit user-requested revision"
            )
    runtime_report = _ensure_project_runtime(
        project_dir,
        brief,
        probe_windows_com=brief.get("schema_version") != "5.9",
    )
    backend = runtime_report.get("builder_backend", "windows_com_v584")
    _materialize_v583_if_present(project_dir)
    slides = _read_json(project_dir / ".build" / "slides.json")
    page_specs = _read_json(project_dir / ".build" / "page_specs.json")
    skill_dir = Path(__file__).resolve().parents[1]
    previous_quality_path = project_dir / ".build" / "quality_report.json"
    previous_quality = _read_json(previous_quality_path) if previous_quality_path.is_file() else None
    _stage(project_dir, "prebuild_validate", lambda: prebuild_project(project_dir))
    generator = compile_project(project_dir)
    cache, cache_state, slide_ids, all_pages_cached = _page_cache_status(
        project_dir, brief["requested_page_count"]
    )
    if is_v595:
        # A V5.9.5 build is reusable only through its hash-bound release lock.
        all_pages_cached = False
    text_audit_path = project_dir / ".build" / "ppt_text_audit.json"
    common_audits_ok = (
        _audit_matches_pptx(text_audit_path, output)
        if brief["schema_version"] == "5.8"
        else _audit_ok(text_audit_path)
    )
    if brief["schema_version"] != "5.8":
        skeleton_path = project_dir / ".build" / "ppt_skeleton_audit.json"
        common_audits_ok = common_audits_ok and (
            skeleton_path.is_file()
            if _audit_policy(brief, "ppt_skeleton_audit") == "warning"
            else _audit_ok(skeleton_path)
        )
    blueprint_audits_ok = True
    if brief["production_mode"] == "blueprint":
        if brief["schema_version"] == "5.8":
            blueprint_audits_ok = _formal_blueprints_current(project_dir, brief["requested_page_count"])
        else:
            direct_asset_path = project_dir / ".build" / "direct_asset_report.json"
            ppt_asset_path = project_dir / ".build" / "ppt_asset_audit.json"
            fidelity_path = project_dir / ".build" / "blueprint_fidelity.json"
            blueprint_audits_ok = (
                direct_asset_path.is_file()
                and (
                    ppt_asset_path.is_file()
                    if _audit_policy(brief, "ppt_asset_audit") == "warning"
                    else _audit_ok(ppt_asset_path)
                )
                and (
                    fidelity_path.is_file()
                    if _audit_policy(brief, "blueprint_fidelity") == "warning"
                    else _audit_ok(fidelity_path)
                )
            )
    if output.is_file() and all_pages_cached and common_audits_ok and blueprint_audits_ok:
        if brief["schema_version"] == "5.8" and isinstance(previous_quality, dict):
            quality = _quality_module()
            current_quality = _read_json(project_dir / ".build" / "quality_report.json")
            quality.write_report(
                project_dir,
                current_quality,
                _warning_only_quality(previous_quality),
            )
        quality_fields = _quality_fields(project_dir)
        if quality_fields["blocker_count"] != 0:
            raise ValueError("cached V5.8 result contains blocking quality issues")
        now = time.time()
        _record_timing(project_dir, "full_deck_cache", now, now, ok=True, note="all page fingerprints and audits matched")
        result = {
            "schema_version": brief["schema_version"],
            "skill_version": _project_skill_version(project_dir),
            "ok": True,
            "cached": True,
            "pptx": str(output),
            "pptx_sha256": _sha256_file(output),
            "pages": brief["requested_page_count"],
            "timing": str(_timing_path(project_dir)),
            **quality_fields,
        }
        _write_json_atomic(project_dir / ".build" / "pipeline_result.json", result)
        if _is_v583(project_dir):
            timing = _load_module(
                "standard_report_v583_timing_cached_summary",
                Path(__file__).with_name("v583_timing.py"),
            )
            timing.summarize_timing(project_dir)
        return result
    if brief["production_mode"] == "blueprint":
        _stage(
            project_dir,
            "extract_assets",
            lambda: _run([
                sys.executable,
                str(skill_dir / "scripts" / "extract_direct_assets.py"),
                "--project",
                str(project_dir),
                "--generator",
                str(generator),
            ]),
        )
        if brief["schema_version"] == "5.8":
            asset_report_path = project_dir / ".build" / "direct_asset_report.json"
            if asset_report_path.is_file():
                asset_report = _read_json(asset_report_path)
                if asset_report.get("warnings"):
                    _append_quality(
                        project_dir,
                        warnings=[
                            _quality_module().issue("ASSET_CROP_ADVISORY", "warning", "asset", str(message))
                            for message in asset_report["warnings"]
                        ],
                    )
    if backend == "windows_com_v584":
        windows_runtime = _load_module(
            "standard_report_windows_runtime_build",
            skill_dir / "scripts" / "ensure_windows_runtime.py",
        )
        windows_runtime.ensure_windows_runtime(
            project_dir=project_dir, probe_com=True
        )
        _stage(
            project_dir,
            "build",
            lambda: _run(
                [sys.executable, str(generator), "--output", str(output)],
                timeout=120,
            ),
        )
        _stage(
            project_dir,
            "render",
            lambda: _run([
                sys.executable,
                str(skill_dir / "scripts" / "render_slides.py"),
                str(output),
                "--project",
                str(project_dir),
                "--expected",
                str(brief["requested_page_count"]),
                "--timeout",
                "45",
            ], timeout=120),
        )
        render_result = {
            "ok": True,
            "renderer": "powerpoint_windows",
            "visual_verification": True,
            "status": "pass",
        }
    elif backend == "mac_python_pptx_v1":
        _stage(
            project_dir,
            "build",
            lambda: _run(
                [sys.executable, str(generator), "--output", str(output)],
                timeout=120,
            ),
        )
        mac_renderer = _load_module(
            "standard_report_macos_render",
            skill_dir / "scripts" / "mac_render_slides.py",
        )
        render_result = _stage(
            project_dir,
            "render",
            lambda: mac_renderer.render_project(
                output,
                project_dir,
                expected_page_count=brief["requested_page_count"],
            ),
        )
        mac_quality = _load_module(
            "standard_report_macos_quality",
            skill_dir / "scripts" / "mac_quality.py",
        )
        font_report_path = project_dir / ".build" / "font_report.json"
        font_fallbacks = (
            _read_json(font_report_path).get("fallbacks", [])
            if font_report_path.is_file()
            else []
        )
        mac_report = mac_quality.audit_mac_pptx(
            output,
            expected_page_count=brief["requested_page_count"],
            render_result=render_result,
            project_dir=project_dir,
            font_fallbacks=font_fallbacks,
        )
        _write_json_atomic(
            project_dir / ".build" / "mac_quality_report.json", mac_report
        )
        if mac_report["status"] == "blocked":
            raise ValueError(
                "Mac PPTX audit failed: " + "; ".join(mac_report["errors"])
            )
    else:
        raise RuntimeError(f"unsupported V5.9 builder backend: {backend}")
    if (
        brief["production_mode"] == "blueprint"
        and brief["schema_version"] in {"5.8", "5.9"}
        and render_result.get("visual_verification") is True
    ):
        _stage(
            project_dir,
            "formalize_blueprints",
            lambda: formalize_blueprints(project_dir, output),
        )
    text_audit = _load_module("standard_report_v56_text_pipeline", skill_dir / "scripts" / "ppt_text_audit.py")
    text_result = _stage(
        project_dir,
        "text_audit",
        lambda: text_audit.audit_pptx_text(
            output,
            slides=slides,
            page_specs=page_specs,
            critical_only=is_v595,
        ),
    )
    _write_json_atomic(project_dir / ".build" / "ppt_text_audit.json", text_result)
    if not text_result["ok"] and not is_v595:
        raise ValueError("PPT text audit failed: " + "; ".join(text_result["errors"]))
    _stage(
        project_dir,
        "skeleton_audit",
        lambda: _run([
            sys.executable,
            str(skill_dir / "scripts" / "ppt_skeleton_audit.py"),
            str(output),
            "--output",
            str(project_dir / ".build" / "ppt_skeleton_audit.json"),
        ], check=_audit_policy(brief, "ppt_skeleton_audit") != "warning"),
    )
    skeleton_path = project_dir / ".build" / "ppt_skeleton_audit.json"
    if _audit_policy(brief, "ppt_skeleton_audit") == "warning" and not _audit_ok(skeleton_path):
        audit = _read_json(skeleton_path) if skeleton_path.is_file() else {"errors": ["skeleton audit did not produce a report"]}
        _append_quality(
            project_dir,
            warnings=[
                _quality_module().issue("PPT_SKELETON_ADVISORY", "warning", "audit", str(message))
                for message in audit.get("errors", ["skeleton audit did not pass"])
            ],
        )
    if (
        brief["production_mode"] == "blueprint"
        and render_result.get("visual_verification") is True
    ):
        _stage(
            project_dir,
            "asset_audit",
            lambda: _run([
                sys.executable,
                str(skill_dir / "scripts" / "ppt_asset_audit.py"),
                str(output),
                "--project",
                str(project_dir),
                "--generator",
                str(generator),
                "--output",
                str(project_dir / ".build" / "ppt_asset_audit.json"),
            ], check=(
                _audit_policy(brief, "ppt_asset_audit") != "warning"
                and not is_v595
            )),
        )
        asset_audit_path = project_dir / ".build" / "ppt_asset_audit.json"
        if _audit_policy(brief, "ppt_asset_audit") == "warning" and not _audit_ok(asset_audit_path):
            audit = _read_json(asset_audit_path) if asset_audit_path.is_file() else {"errors": ["asset audit did not produce a report"]}
            _append_quality(
                project_dir,
                warnings=[
                    _quality_module().issue("PPT_ASSET_ADVISORY", "warning", "audit", str(message))
                    for message in audit.get("errors", ["asset audit did not pass"])
                ],
            )
        fidelity = _load_module("standard_report_v56_fidelity_pipeline", skill_dir / "scripts" / "blueprint_fidelity.py")
        page_pairs = []
        visual_manifest = _read_json(project_dir / ".build" / "visual_manifest.json")
        for index in range(1, brief["requested_page_count"] + 1):
            slide_id = f"S{index:02d}"
            if brief["schema_version"] == "5.8":
                design_source = project_dir / visual_manifest["pages"][slide_id]["design_draft_path"]
            else:
                design_source = project_dir / "blueprints" / f"{slide_id}.png"
            page_pairs.append((slide_id, design_source, project_dir / ".build" / "rendered" / "current" / f"{slide_id}.png"))
        fidelity_result = _stage(project_dir, "fidelity", lambda: fidelity.compare_deck(page_pairs, expected_page_count=brief["requested_page_count"]))
        _write_json_atomic(project_dir / ".build" / "blueprint_fidelity.json", fidelity_result)
        if (
            not fidelity_result["passed"]
            and _audit_policy(brief, "blueprint_fidelity") != "warning"
        ):
            raise ValueError(
                "blueprint fidelity failed: "
                + ", ".join(fidelity_result["failed_slide_ids"])
            )
        if (
            not fidelity_result["passed"]
            and _audit_policy(brief, "blueprint_fidelity") == "warning"
        ):
            _append_quality(
                project_dir,
                warnings=[
                    _quality_module().issue(
                        "BLUEPRINT_FIDELITY_ADVISORY",
                        "warning",
                        "fidelity",
                        "PPT render differs from the locked ImageGen visual benchmark",
                        str(slide_id),
                    )
                    for slide_id in fidelity_result.get("failed_slide_ids", [])
                ],
            )
    if render_result.get("visual_verification") is True:
        for slide_id in slide_ids:
            cache.update_page_cache(
                cache_state,
                slide_id,
                [project_dir / ".build" / "pages" / f"{slide_id}.input.json"],
                [project_dir / ".build" / "rendered" / "current" / f"{slide_id}.png"],
                salt=brief["schema_version"],
            )
    result = {
        "schema_version": brief["schema_version"],
        "skill_version": _project_skill_version(project_dir),
        "ok": True,
        "pptx": str(output),
        "pptx_sha256": _sha256_file(output),
        "pages": brief["requested_page_count"],
        "timing": str(_timing_path(project_dir)),
        **_quality_fields(project_dir),
    }
    if is_v595:
        quality_path = project_dir / ".build" / "quality_report.json"
        fidelity_path = project_dir / ".build" / "blueprint_fidelity.json"
        asset_path = project_dir / ".build" / "ppt_asset_audit.json"
        postbuild = release.write_postbuild_release(
            project_dir,
            output,
            quality_report=(
                _read_json(quality_path)
                if quality_path.is_file()
                else {"warnings": [], "blockers": []}
            ),
            text_audit=text_result,
            fidelity_report=(
                _read_json(fidelity_path)
                if fidelity_path.is_file()
                else {"passed": True, "pages": []}
            ),
            asset_audit=(
                _read_json(asset_path)
                if asset_path.is_file()
                else {"ok": True, "errors": []}
            ),
            build_attempt=1 if user_revision else None,
        )
        result["postbuild_release"] = postbuild
        if postbuild["decision"] != "package":
            result["ok"] = False
            _write_json_atomic(
                project_dir / ".build" / "pipeline_result.json",
                result,
            )
            raise ValueError(
                "V5.9.5 catastrophic postbuild gate failed: "
                + "; ".join(
                    str(item.get("message", item))
                    for item in postbuild["catastrophic_blockers"]
                )
            )
    if (
        brief.get("schema_version") == "5.9"
        and backend == "mac_python_pptx_v1"
        and result.get("quality_status") == "structurally_valid_unrendered"
    ):
        packager = _load_module(
            "standard_report_v59_loose_delivery",
            skill_dir / "scripts" / "pack_delivery.py",
        )
        result["delivery"] = packager.write_v59_loose_delivery(
            project_dir, output
        )
    _write_json_atomic(project_dir / ".build" / "pipeline_result.json", result)
    if is_v595 and auto_package:
        result["delivery"] = str(
            _package_v595(
                project_dir,
                output,
                generator,
                force=catastrophic_repair or user_revision,
            )
        )
        _write_json_atomic(
            project_dir / ".build" / "pipeline_result.json",
            result,
        )
    if _is_v583(project_dir):
        timing = _load_module(
            "standard_report_v583_timing_result_summary",
            Path(__file__).with_name("v583_timing.py"),
        )
        timing.summarize_timing(project_dir)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="V5.8 manifest-driven PowerPoint project pipeline.")
    parser.add_argument("project", type=Path)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--preflight", action="store_true")
    actions.add_argument("--init", action="store_true")
    actions.add_argument("--compile", action="store_true")
    actions.add_argument("--materialize", action="store_true")
    actions.add_argument("--prepare-visual-review", action="store_true")
    actions.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--repair-catastrophic",
        action="store_true",
        help="V5.9.5 only: permit the single bounded catastrophic repair build",
    )
    parser.add_argument(
        "--user-revision",
        action="store_true",
        help="V5.9.5 only: explicit user-requested revision overrides the build lock",
    )
    parser.add_argument(
        "--no-package",
        action="store_true",
        help="V5.9.5 only: keep a valid loose PPTX instead of auto-packaging",
    )
    args = parser.parse_args()
    if args.preflight:
        payload = preflight_project(args.project)
    elif args.init:
        payload = init_project(args.project)
    elif args.compile:
        payload = {"schema_version": SCHEMA_VERSION, "generator": str(compile_project(args.project))}
    elif args.materialize:
        payload = materialize_project(args.project)
    elif args.prepare_visual_review:
        payload = prepare_visual_review(args.project)
    else:
        payload = run_project(
            args.project,
            args.output,
            catastrophic_repair=args.repair_catastrophic,
            user_revision=args.user_revision,
            auto_package=not args.no_package,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
