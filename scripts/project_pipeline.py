from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time
import platform as host_platform
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = "5.9"
SUPPORTED_SCHEMA_VERSIONS = {"5.6", "5.7", "5.8", "5.9", "6.0"}
LATEST_SKILL_VERSION = "5.9.6"
_V6_ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _ingest_project_sources(project_dir: Path, brief: dict, ingest: Any) -> dict:
    if brief.get("schema_version") != "6.0":
        return ingest.ingest_project_sources(project_dir)

    original_loader = ingest._load_module

    def v6_compatible_loader(name: str, path: Path):
        module = original_loader(name, path)
        if Path(path).name != "v58_source_cache.py":
            return module
        original_write = module.write_source_digest

        def write_source_digest(
            cache_project_dir,
            sources,
            parsed_payload,
            *,
            schema_version: str = "5.8",
        ):
            cache_schema = "5.9" if schema_version == "6.0" else schema_version
            return original_write(
                cache_project_dir,
                sources,
                parsed_payload,
                schema_version=cache_schema,
            )

        module.write_source_digest = write_source_digest
        return module

    ingest._load_module = v6_compatible_loader
    try:
        return ingest.ingest_project_sources(project_dir)
    finally:
        ingest._load_module = original_loader


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
        if brief.get("schema_version") == "6.0":
            if brief.get("pipeline_revision") != "6.0.0":
                raise ValueError("V6 pipeline_revision must be 6.0.0")
            return "6.0.1"
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


def select_v6_backend(system_name: str | None = None) -> str:
    system = system_name or host_platform.system()
    if system == "Windows":
        return "windows_com_v584"
    if system == "Darwin":
        return "mac_python_pptx_v2"
    raise RuntimeError(f"{system} is unsupported by Standard Report PPT V6")


def v6_page_batches(page_count: int) -> list[list[str]]:
    """Split long V6 decks into deterministic three-to-five-page recovery batches."""
    if not isinstance(page_count, int) or page_count <= 0:
        raise ValueError("requested_page_count must be a positive integer")
    if page_count <= 5:
        return [[f"S{index:02d}" for index in range(1, page_count + 1)]]
    batch_count = (page_count + 4) // 5
    base, extra = divmod(page_count, batch_count)
    sizes = [base + (1 if index < extra else 0) for index in range(batch_count)]
    if any(size < 3 or size > 5 for size in sizes):
        raise ValueError("V6 recovery batches must contain three to five pages")
    result: list[list[str]] = []
    cursor = 1
    for size in sizes:
        result.append(
            [f"S{index:02d}" for index in range(cursor, cursor + size)]
        )
        cursor += size
    return result


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
    if brief.get("schema_version") == "6.0":
        backend = select_v6_backend()
        report = {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "construction_mode": brief.get("construction_mode"),
            "os_name": host_platform.system(),
            "machine": host_platform.machine(),
            "builder_backend": backend,
            "supported": True,
            "reason": None,
        }
        _write_json_atomic(project_dir / ".build" / "runtime_report.json", report)
        if backend == "windows_com_v584" and probe_windows_com:
            runtime = _load_module(
                "standard_report_windows_runtime_v6",
                Path(__file__).with_name("ensure_windows_runtime.py"),
            )
            runtime.ensure_windows_runtime(project_dir=project_dir, probe_com=True)
        elif backend == "mac_python_pptx_v2":
            runtime = _load_module(
                "standard_report_macos_runtime_v6",
                Path(__file__).with_name("ensure_macos_runtime.py"),
            )
            runtime.ensure_macos_runtime(project_dir=project_dir)
        return report
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
    if brief.get("schema_version") == "6.0":
        contracts = _load_module(
            "standard_report_v6_contracts_pipeline",
            Path(__file__).with_name("v6_contracts.py"),
        )
        errors = contracts.validate_v6_brief(brief)
        count = brief.get("requested_page_count")
        if not isinstance(count, int) or count <= 0:
            errors.append("requested_page_count must be a positive integer")
        source_files = brief.get("source_files")
        if not isinstance(source_files, list) or not source_files:
            errors.append("V6 requires a non-empty source_files list")
        return errors
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
    if brief.get("schema_version") == "6.0":
        required = [
            skill_dir / "assets" / "company_template.pptx",
            skill_dir / "assets" / "direct_blueprint_generator_template.py",
            skill_dir / "assets" / "python_pptx_generator_template_v2.py",
            skill_dir / "assets" / "vendor" / "fonttools-4.63.0-py3.zip",
            skill_dir / "prompts" / "deconstruction_alignment_prompt.md",
            skill_dir / "prompts" / "bitmap_alignment_prompt.md",
            *[
                skill_dir / "scripts" / name
                for name in (
                    "project_compiler.py",
                    "project_compiler_mac_v2.py",
                    "ensure_windows_runtime.py",
                    "ensure_macos_runtime.py",
                    "render_slides.py",
                    "mac_render_slides.py",
                    "mac_quality.py",
                    "v6_contracts.py",
                    "v6_blueprint_gate.py",
                    "v6_bitmap.py",
                    "v62_bitmap_acceptance.py",
                    "v6_deconstruction.py",
                    "v6_mac_spec.py",
                    "v6_editability_audit.py",
                    "v596_visual_review.py",
                    "pack_delivery.py",
                )
            ],
        ]
        missing = [
            str(path.relative_to(skill_dir)) for path in required if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError(
                "missing V6 resources: " + ", ".join(missing)
            )
        for path in required:
            if path.suffix == ".py":
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
        packager = _load_module(
            "standard_report_v6_packager_preflight",
            skill_dir / "scripts" / "pack_delivery.py",
        )
        if not hasattr(packager, "package_v6_delivery"):
            raise RuntimeError("pack_delivery.py does not provide V6 packaging")
        return {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "construction_mode": brief["construction_mode"],
            "ok": True,
            "mode": "blueprint",
            "builder_backend": runtime_report["builder_backend"],
            "checks": ["brief", "v6_resources", "python_syntax", "runtime"],
        }

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
    if brief["schema_version"] in {"5.8", "5.9", "6.0"}:
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
        "6.0.0",
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
            ingest_result = _ingest_project_sources(project_dir, brief, ingest)
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
    brief = _read_json(project_dir / "project_brief.json")
    if brief.get("schema_version") == "6.0":
        gate = _load_module(
            "standard_report_v6_imagegen_gate_materialize",
            Path(__file__).with_name("v6_blueprint_gate.py"),
        )
        gate.assert_imagegen_invocation_gate(project_dir)
        build = project_dir / ".build"
        bundle_path = build / "authoring_bundle.json"
        bundle = _read_json(bundle_path)
        compatibility_bundle = dict(bundle)
        compatibility_bundle["schema_version"] = "5.9"
        authoring = _load_module(
            "standard_report_v6_shared_authoring",
            Path(__file__).with_name("v583_authoring.py"),
        )
        slides, page_specs, manifest = authoring._validate_bundle(
            compatibility_bundle
        )
        manifest.update(
            {
                "schema_version": "6.0",
                "pipeline_revision": "6.0.0",
                "construction_mode": brief["construction_mode"],
            }
        )
        slide_ids = [str(slide["slide_id"]) for slide in slides]
        draft_hashes = authoring._bind_design_drafts(
            project_dir, manifest, slide_ids
        )
        benchmark_module = _load_module(
            "standard_report_v6_shared_text_benchmark",
            Path(__file__).with_name("v58_text_benchmark.py"),
        )
        benchmark = benchmark_module.make_benchmark(
            slides, page_specs, draft_hashes, schema_version="5.9"
        )
        benchmark["schema_version"] = "6.0"
        _write_json_atomic(build / "slides.json", slides)
        _write_json_atomic(build / "page_specs.json", page_specs)
        _write_json_atomic(build / "visual_manifest.json", manifest)
        _write_json_atomic(build / "blueprint_text_benchmark.json", benchmark)
        result = {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "skill_version": "6.0.1",
            "ok": True,
            "authoring_bundle_sha256": _sha256_file(bundle_path),
            "design_draft_hashes": draft_hashes,
            "slides": len(slides),
            "bound_design_drafts": sum(bool(value) for value in draft_hashes.values()),
            "shared_pre_blueprint_algorithm": "v583_authoring",
        }
        _write_json_atomic(build / "authoring_report.json", result)
        return result
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
    if brief.get("schema_version") == "6.0":
        if (
            brief.get("pipeline_revision") != "6.0.0"
            or brief.get("construction_mode") != "deconstruct"
        ):
            raise ValueError("--prepare-visual-review requires V6 deconstruct mode")
        gate = _load_module(
            "standard_report_v6_imagegen_gate_visual_review",
            Path(__file__).with_name("v6_blueprint_gate.py"),
        )
        gate.assert_imagegen_invocation_gate(project)
        generator = _load_module(
            "standard_report_v6_prepare_visual_review",
            Path(__file__).with_name("v596_visual_review.py"),
        )
        result = generator.generate_review_tiles(project)
        result["schema_version"] = "6.0"
        result["skill_version"] = "6.0.1"
        result["pipeline_revision"] = "6.0.0"
        result["construction_mode"] = "deconstruct"
        _write_json_atomic(project / ".build" / "visual_review_tiles.json", result)
        return result
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


def prepare_bitmap_review(project_dir: str | Path) -> dict:
    project = Path(project_dir).resolve()
    brief = _read_json(project / "project_brief.json")
    if (
        brief.get("schema_version") != "6.0"
        or brief.get("pipeline_revision") != "6.0.0"
        or brief.get("construction_mode") != "bitmap"
    ):
        raise ValueError("--prepare-bitmap-review requires V6 bitmap mode")
    gate = _load_module(
        "standard_report_v6_imagegen_gate_bitmap_review",
        Path(__file__).with_name("v6_blueprint_gate.py"),
    )
    gate.assert_imagegen_invocation_gate(project)
    module = _load_module(
        "standard_report_v6_prepare_bitmap_review",
        Path(__file__).with_name("v6_bitmap.py"),
    )
    return module.prepare_bitmap_review(project)


def _materialize_v6_deconstruct_assets(
    project: Path,
    alignment_payload: dict[str, Any],
    *,
    reuse_slide_ids: set[str] | None = None,
) -> None:
    """Crop only reviewed local visual modules; never rasterize the page body."""

    from PIL import Image

    reused = reuse_slide_ids or set()
    seen: set[str] = set()
    for slide_id, page in alignment_payload.get("pages", {}).items():
        if not isinstance(page, dict):
            continue
        blueprint = project / "blueprints" / f"{slide_id}.png"
        for visual in page.get("visuals", []):
            if (
                not isinstance(visual, dict)
                or visual.get("treatment", visual.get("disposition")) != "crop"
            ):
                continue
            asset_id = visual.get("asset_id")
            source_px = visual.get("source_px")
            if (
                not isinstance(asset_id, str)
                or not _V6_ASSET_ID.fullmatch(asset_id)
                or not isinstance(source_px, list)
                or len(source_px) != 4
                or not all(isinstance(value, int) for value in source_px)
            ):
                raise ValueError(f"{slide_id}: reviewed crop contract is invalid")
            if asset_id in seen:
                raise ValueError(f"{slide_id}: crop asset_id is reused across pages")
            seen.add(asset_id)
            destination = (
                project / ".build" / "assets" / slide_id / f"{asset_id}.png"
            ).resolve()
            expected_parent = (project / ".build" / "assets" / slide_id).resolve()
            if destination.parent != expected_parent:
                raise ValueError(f"{slide_id}/{asset_id}: crop path escapes project")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(blueprint) as image:
                left, top, right, bottom = source_px
                if not (
                    0 <= left < right <= image.width
                    and 0 <= top < bottom <= image.height
                ):
                    raise ValueError(f"{slide_id}/{asset_id}: crop is outside blueprint")
                expected = image.crop((left, top, right, bottom)).convert("RGBA")
                if slide_id in reused and destination.is_file():
                    with Image.open(destination) as existing:
                        actual = existing.convert("RGBA")
                        if (
                            expected.size == actual.size
                            and expected.tobytes() == actual.tobytes()
                        ):
                            continue
                expected.save(destination)


def _materialize_v6_formal_blueprint_manifest(
    project: Path, brief: dict[str, Any]
) -> dict[str, Any]:
    visual_path = project / ".build" / "visual_manifest.json"
    visual = _read_json(visual_path) if visual_path.is_file() else {"pages": {}}
    pages: dict[str, Any] = {}
    for index in range(1, int(brief["requested_page_count"]) + 1):
        slide_id = f"S{index:02d}"
        formal = project / "blueprints" / f"{slide_id}.png"
        draft = project / ".build" / "design_drafts" / f"{slide_id}.png"
        if not formal.is_file() or not draft.is_file():
            raise FileNotFoundError(f"{slide_id}: immutable blueprint pair is missing")
        digest = _sha256_file(formal)
        if _sha256_file(draft) != digest:
            raise ValueError(f"{slide_id}: formal blueprint differs from ImageGen draft")
        page = visual.get("pages", {}).get(slide_id, {})
        if (
            not isinstance(page, dict)
            or page.get("design_draft_sha256") != digest
            or page.get("formal_blueprint_sha256") != digest
            or page.get("formal_blueprint_path") != f"blueprints/{slide_id}.png"
        ):
            raise ValueError(f"{slide_id}: visual manifest does not bind blueprint lock")
        pages[slide_id] = {
            "design_draft_path": f".build/design_drafts/{slide_id}.png",
            "design_draft_sha256": digest,
            "formal_blueprint_path": f"blueprints/{slide_id}.png",
            "formal_blueprint_sha256": digest,
        }
    payload = {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "construction_mode": brief["construction_mode"],
        "pages": pages,
    }
    destination = project / ".build" / "formal_blueprint_manifest.json"
    if destination.is_file():
        if _read_json(destination) != payload:
            raise ValueError("BLUEPRINT_LOCK_TAMPERED")
    else:
        _write_json_atomic(destination, payload)
    return payload


def _validate_v6_deconstruct_alignment(
    project: Path,
    brief: dict[str, Any],
    alignment: dict[str, Any],
) -> None:
    expected = {
        f"S{index:02d}"
        for index in range(1, int(brief["requested_page_count"]) + 1)
    }
    if (
        not isinstance(alignment, dict)
        or alignment.get("schema_version") != "6.0"
        or alignment.get("pipeline_revision") != "6.0.0"
        or alignment.get("construction_mode") != "deconstruct"
        or not isinstance(alignment.get("pages"), dict)
        or set(alignment["pages"]) != expected
    ):
        raise ValueError("V6 deconstruction alignment header or page set is invalid")
    review_path = project / ".build" / "visual_review_tiles.json"
    if not review_path.is_file():
        raise ValueError("V6 deconstruction visual review manifest is missing")
    review_manifest = _read_json(review_path)
    if (
        review_manifest.get("schema_version") != "6.0"
        or review_manifest.get("skill_version") != "6.0.1"
        or review_manifest.get("pipeline_revision") != "6.0.0"
        or review_manifest.get("construction_mode") != "deconstruct"
        or not isinstance(review_manifest.get("pages"), dict)
        or set(review_manifest["pages"]) != expected
    ):
        raise ValueError("V6 deconstruction visual review page set is invalid")
    validator = _load_module(
        "standard_report_v596_visual_review_v6",
        Path(__file__).with_name("v596_visual_review.py"),
    )
    errors = validator.validate_review_tiles(project, alignment)
    if errors:
        raise ValueError(
            "V6 deconstruction visual review failed: " + "; ".join(errors)
        )


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


def _dispatch_v6_compiler(project_dir: Path, brief: dict[str, Any]) -> Path:
    runtime_path = project_dir / ".build" / "runtime_report.json"
    if not runtime_path.is_file():
        raise RuntimeError("V6 runtime report is missing; run --init first")
    backend = _read_json(runtime_path).get("builder_backend")
    if backend == "mac_python_pptx_v2":
        compiler_path = Path(__file__).with_name("project_compiler_mac_v2.py")
        module_name = "standard_report_v6_mac_compiler"
    elif backend == "windows_com_v584":
        compiler_path = Path(__file__).with_name("project_compiler.py")
        module_name = "standard_report_v6_windows_compiler"
    else:
        raise RuntimeError(f"unsupported or missing V6 builder backend: {backend}")
    compiler = _load_module(module_name, compiler_path)
    return _stage(
        project_dir, "compile", lambda: compiler.compile_project(project_dir)
    )


def compile_project(
    project_dir: str | Path,
    *,
    _v6_post_lock_prepared: bool = False,
) -> Path:
    project_dir = Path(project_dir).resolve()
    brief = _read_json(project_dir / "project_brief.json")
    if brief.get("schema_version") == "6.0":
        gate = _load_module(
            "standard_report_v6_imagegen_gate_compile",
            Path(__file__).with_name("v6_blueprint_gate.py"),
        )
        gate.assert_imagegen_invocation_gate(project_dir)
    _materialize_v583_if_present(project_dir)
    runtime_path = project_dir / ".build" / "runtime_report.json"
    if brief.get("schema_version") == "6.0":
        if not _v6_post_lock_prepared:
            prebuild_project(project_dir)
        return _dispatch_v6_compiler(project_dir, brief)
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


def prebuild_project(
    project_dir: str | Path,
    *,
    reuse_preprocessed_slide_ids: set[str] | None = None,
) -> dict:
    project_dir = Path(project_dir).resolve()
    brief = _read_json(project_dir / "project_brief.json")
    if brief.get("schema_version") == "6.0":
        gate = _load_module(
            "standard_report_v6_blueprint_gate_prebuild",
            Path(__file__).with_name("v6_blueprint_gate.py"),
        )
        mode = str(brief.get("construction_mode", ""))
        gate.assert_blueprint_gate(
            project_dir, require_alignment=mode == "deconstruct"
        )
        _materialize_v6_formal_blueprint_manifest(project_dir, brief)
        runtime = _read_json(project_dir / ".build" / "runtime_report.json")
        backend = str(runtime.get("builder_backend", ""))
        if mode == "bitmap":
            bitmap = _load_module(
                "standard_report_v6_bitmap_prebuild",
                Path(__file__).with_name("v6_bitmap.py"),
            )
            bitmap.materialize_bitmap_assets(
                project_dir,
                reuse_slide_ids=reuse_preprocessed_slide_ids,
            )
            report = {
                "schema_version": "6.0",
                "pipeline_revision": "6.0.0",
                "construction_mode": "bitmap",
                "builder_backend": backend,
                "ok": True,
                "status": "pass",
                "blockers": [],
            }
        elif mode == "deconstruct":
            alignment_payload = _read_json(
                project_dir / ".build" / "blueprint_alignment.json"
            )
            _validate_v6_deconstruct_alignment(
                project_dir, brief, alignment_payload
            )
            pages = alignment_payload.get("pages", {})
            if not isinstance(pages, dict):
                raise ValueError("V6 blueprint alignment pages must be a mapping")
            resolved_specs = {
                slide_id: page["resolved_page_spec"]
                for slide_id, page in pages.items()
                if isinstance(page, dict)
                and isinstance(page.get("resolved_page_spec"), dict)
            }
            expected = {
                f"S{index:02d}"
                for index in range(1, int(brief["requested_page_count"]) + 1)
            }
            if set(resolved_specs) != expected:
                raise ValueError("V6 deconstruction alignment is incomplete")
            slides = _read_json(project_dir / ".build" / "slides.json")
            visual_manifest = _read_json(
                project_dir / ".build" / "visual_manifest.json"
            )
            merge = _load_module(
                "standard_report_v6_shared_alignment_merge",
                Path(__file__).with_name("v584_blueprint_alignment.py"),
            )
            by_slide = {
                str(slide["slide_id"]): slide
                for slide in slides
                if isinstance(slide, dict) and slide.get("slide_id")
            }
            aligned_slides: list[dict[str, Any]] = []
            aligned_specs: dict[str, Any] = {}
            aligned_manifest = dict(visual_manifest)
            aligned_manifest["schema_version"] = "6.0"
            aligned_manifest["pipeline_revision"] = "6.0.0"
            aligned_manifest["construction_mode"] = "deconstruct"
            aligned_manifest.setdefault("pages", {})
            for slide_id in sorted(expected):
                aligned_slide, aligned_spec, aligned_page = merge._merge_page(
                    by_slide[slide_id],
                    resolved_specs[slide_id],
                    aligned_manifest["pages"].get(slide_id, {}),
                    pages[slide_id],
                    skill_version="5.9.6",
                )
                aligned_slides.append(aligned_slide)
                aligned_specs[slide_id] = aligned_spec
                aligned_manifest["pages"][slide_id] = aligned_page
            slides = aligned_slides
            resolved_specs = aligned_specs
            _write_json_atomic(project_dir / ".build" / "slides.json", slides)
            _write_json_atomic(
                project_dir / ".build" / "page_specs.json", resolved_specs
            )
            _write_json_atomic(
                project_dir / ".build" / "visual_manifest.json", aligned_manifest
            )
            reconstruction = _load_module(
                "standard_report_v6_reconstruction_contract",
                Path(__file__).with_name("v591_reconstruction_contract.py"),
            ).validate_reconstruction_contract(
                brief, slides, resolved_specs, alignment_payload, backend
            )
            alignment_audit = None
            if backend == "windows_com_v584":
                alignment_audit = _load_module(
                    "standard_report_v6_windows_alignment_audit",
                    Path(__file__).with_name("blueprint_alignment_audit.py"),
                ).audit_project(project_dir)
            guard = _load_module(
                "standard_report_v6_deconstruction_prebuild",
                Path(__file__).with_name("v6_deconstruction.py"),
            ).validate_deconstruction_prebuild(
                brief, resolved_specs, alignment_payload, backend
            )
            blockers = list(reconstruction.get("blockers", [])) + list(
                guard.get("blockers", [])
            )
            report = {
                "schema_version": "6.0",
                "pipeline_revision": "6.0.0",
                "construction_mode": "deconstruct",
                "builder_backend": backend,
                "ok": not blockers,
                "status": "blocked" if blockers else "pass",
                "blockers": blockers,
                "reconstruction": reconstruction,
                "deconstruction_guard": guard,
                "blueprint_alignment_audit": alignment_audit,
                "allowed_large_visual_assets_by_page": guard.get(
                    "allowed_large_visual_assets_by_page", {}
                ),
            }
            _write_json_atomic(
                project_dir / ".build" / "deconstruction_precheck.json", guard
            )
            if not blockers:
                _materialize_v6_deconstruct_assets(
                    project_dir,
                    alignment_payload,
                    reuse_slide_ids=reuse_preprocessed_slide_ids,
                )
            if backend == "mac_python_pptx_v2" and not blockers:
                _load_module(
                    "standard_report_v6_mac_spec_prebuild",
                    Path(__file__).with_name("v6_mac_spec.py"),
                ).materialize_mac_page_specs(project_dir)
            if blockers:
                raise ValueError(
                    "V6 deconstruction prebuild failed: "
                    + "; ".join(str(item.get("message", item)) for item in blockers)
                )
        else:
            raise ValueError("V6_CONSTRUCTION_MODE_REQUIRED")
        _write_json_atomic(project_dir / ".build" / "prebuild_report.json", report)
        return report
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


def _v6_preprocess_batches(
    project: Path,
    brief: dict[str, Any],
    backend: str,
) -> tuple[dict[str, Any], set[str]]:
    """Plan resumable post-lock parsing/cropping; PPT construction stays whole-deck."""

    mode = str(brief["construction_mode"])
    alignment_name = (
        "blueprint_alignment.json"
        if mode == "deconstruct"
        else "bitmap_alignment.json"
    )
    alignment = _read_json(project / ".build" / alignment_name)
    alignment_pages = alignment.get("pages", {})
    plan_path = project / ".build" / "v6_batch_plan.json"
    previous = _read_json(plan_path) if plan_path.is_file() else {}
    prior_batches = {
        tuple(item.get("slide_ids", [])): item
        for item in previous.get("batches", [])
        if isinstance(item, dict)
    }
    reusable: set[str] = set()
    batches: list[dict[str, Any]] = []
    for index, slide_ids in enumerate(
        v6_page_batches(int(brief["requested_page_count"])), start=1
    ):
        fingerprint_payload = {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "construction_mode": mode,
            "builder_backend": backend,
            "pages": {
                slide_id: {
                    "blueprint_sha256": _sha256_file(
                        project / "blueprints" / f"{slide_id}.png"
                    ),
                    "alignment": alignment_pages.get(slide_id),
                }
                for slide_id in slide_ids
            },
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload, ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
        ).hexdigest()
        prior = prior_batches.get(tuple(slide_ids), {})
        can_reuse = (
            previous.get("construction_mode") == mode
            and previous.get("builder_backend") == backend
            and prior.get("preprocess_status") == "complete"
            and prior.get("fingerprint_sha256") == fingerprint
            and _v6_batch_receipt_valid(
                project,
                int(prior.get("batch_id", index)),
                slide_ids,
                fingerprint,
            )
        )
        if can_reuse:
            reusable.update(slide_ids)
        batches.append(
            {
                "batch_id": index,
                "slide_ids": slide_ids,
                "fingerprint_sha256": fingerprint,
                "preprocess_status": "reused" if can_reuse else "pending",
            }
        )
    payload = {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "construction_mode": mode,
        "builder_backend": backend,
        "recovery_scope": "post_lock_preprocess_only",
        "whole_deck_build_batched": False,
        "whole_deck_build_status": "pending",
        "batches": batches,
    }
    _write_json_atomic(plan_path, payload)
    return payload, reusable


def _v6_batch_receipt_path(project: Path, batch_id: int) -> Path:
    return (
        project
        / ".build"
        / "v6_preprocess_batches"
        / f"batch_{batch_id:02d}.json"
    )


def _v6_batch_receipt_valid(
    project: Path,
    batch_id: int,
    slide_ids: list[str],
    fingerprint: str,
) -> bool:
    path = _v6_batch_receipt_path(project, batch_id)
    if not path.is_file():
        return False
    try:
        receipt = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if (
        receipt.get("schema_version") != "6.0"
        or receipt.get("pipeline_revision") != "6.0.0"
        or receipt.get("fingerprint_sha256") != fingerprint
        or receipt.get("slide_ids") != slide_ids
        or not isinstance(receipt.get("assets"), dict)
    ):
        return False
    for record in receipt["assets"].values():
        if not isinstance(record, dict):
            return False
        relative = record.get("path")
        if not isinstance(relative, str):
            return False
        asset = (project / relative).resolve()
        try:
            asset.relative_to(project)
        except ValueError:
            return False
        if not asset.is_file() or record.get("sha256") != _sha256_file(asset):
            return False
    return True


def _write_v6_batch_receipt(
    project: Path,
    brief: dict[str, Any],
    batch: dict[str, Any],
    alignment: dict[str, Any],
) -> None:
    mode = str(brief["construction_mode"])
    slide_ids = list(batch["slide_ids"])
    assets: dict[str, Any] = {}
    parsed: dict[str, Any] = {}
    for slide_id in slide_ids:
        page = alignment["pages"][slide_id]
        if mode == "deconstruct":
            parsed[slide_id] = page.get("resolved_page_spec")
            visuals = [
                item
                for item in page.get("visuals", [])
                if isinstance(item, dict)
                and item.get("treatment", item.get("disposition")) == "crop"
            ]
            asset_ids = [str(item.get("asset_id")) for item in visuals]
        else:
            parsed[slide_id] = {"source_px": page.get("source_px")}
            asset_ids = [f"{slide_id}_BODY_BITMAP"]
        for asset_id in asset_ids:
            if not _V6_ASSET_ID.fullmatch(asset_id):
                raise ValueError(f"{slide_id}: unsafe V6 batch asset_id")
            relative = f".build/assets/{slide_id}/{asset_id}.png"
            asset = (project / relative).resolve()
            if not asset.is_file():
                raise FileNotFoundError(asset)
            assets[f"{slide_id}/{asset_id}"] = {
                "path": relative,
                "sha256": _sha256_file(asset),
            }
    _write_json_atomic(
        _v6_batch_receipt_path(project, int(batch["batch_id"])),
        {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "construction_mode": mode,
            "batch_id": int(batch["batch_id"]),
            "slide_ids": slide_ids,
            "fingerprint_sha256": batch["fingerprint_sha256"],
            "parsed_pages": parsed,
            "assets": assets,
        },
    )


def _complete_v6_preprocess_batches(
    project: Path, payload: dict[str, Any]
) -> None:
    completed = dict(payload)
    completed["batches"] = [
        {**item, "preprocess_status": "complete"}
        for item in payload.get("batches", [])
    ]
    _write_json_atomic(project / ".build" / "v6_batch_plan.json", completed)


def _execute_v6_preprocess_batches(
    project: Path,
    brief: dict[str, Any],
    backend: str,
    payload: dict[str, Any],
    reusable_slide_ids: set[str],
) -> set[str]:
    """Persist each post-lock parsing/cropping batch independently."""

    del backend
    mode = str(brief["construction_mode"])
    alignment_name = (
        "blueprint_alignment.json"
        if mode == "deconstruct"
        else "bitmap_alignment.json"
    )
    alignment = _read_json(project / ".build" / alignment_name)
    if mode == "deconstruct":
        _validate_v6_deconstruct_alignment(project, brief, alignment)
        bitmap = None
    else:
        bitmap = _load_module(
            "standard_report_v6_bitmap_batch",
            Path(__file__).with_name("v6_bitmap.py"),
        )
    completed = set(reusable_slide_ids)
    plan_path = project / ".build" / "v6_batch_plan.json"
    batches = payload.get("batches", [])
    for index, batch in enumerate(batches):
        slide_ids = list(batch.get("slide_ids", []))
        if batch.get("preprocess_status") == "reused":
            completed.update(slide_ids)
            continue
        try:
            if mode == "deconstruct":
                subset = {
                    **alignment,
                    "pages": {
                        slide_id: alignment["pages"][slide_id]
                        for slide_id in slide_ids
                    },
                }
                _materialize_v6_deconstruct_assets(project, subset)
            else:
                assert bitmap is not None
                bitmap.materialize_bitmap_batch_assets(project, slide_ids)
        except Exception as exc:
            batches[index] = {
                **batch,
                "preprocess_status": "failed",
                "error": str(exc),
            }
            payload["batches"] = batches
            _write_json_atomic(plan_path, payload)
            raise
        _write_v6_batch_receipt(project, brief, batch, alignment)
        batches[index] = {
            **batch,
            "preprocess_status": "complete",
        }
        completed.update(slide_ids)
        payload["batches"] = batches
        _write_json_atomic(plan_path, payload)
    return completed


def _mark_v6_whole_deck_built(project: Path) -> None:
    path = project / ".build" / "v6_batch_plan.json"
    payload = _read_json(path)
    payload["whole_deck_build_status"] = "built"
    _write_json_atomic(path, payload)


def _v6_repair_contract_snapshot(
    project: Path,
    construction_mode: str,
) -> dict[str, str | None]:
    mutable_alignment = (
        ".build/blueprint_alignment.json"
        if construction_mode == "deconstruct"
        else ".build/bitmap_alignment.json"
    )
    contract_paths = {"project_brief.json", "generate_deck.py"}
    contract_paths.update(
        path.relative_to(project).as_posix()
        for path in (project / ".build").rglob("*.json")
        if path.name != "v6_build_attempt.json"
    )
    contract_paths.discard(mutable_alignment)
    for pattern in ("blueprints/S[0-9][0-9].png", ".build/design_drafts/S[0-9][0-9].png"):
        contract_paths.update(
            path.relative_to(project).as_posix() for path in project.glob(pattern)
        )
    snapshot: dict[str, str | None] = {}
    for relative in sorted(contract_paths):
        path = project / relative
        snapshot[relative] = _sha256_file(path) if path.is_file() else None
    return snapshot


def _assert_v6_repair_contract_unchanged(
    project: Path,
    construction_mode: str,
    expected: Any,
) -> None:
    if not isinstance(expected, dict):
        raise ValueError("V6 repair contract snapshot is missing")
    actual = _v6_repair_contract_snapshot(project, construction_mode)
    changed = sorted(
        relative
        for relative in set(expected) | set(actual)
        if expected.get(relative) != actual.get(relative)
    )
    if changed:
        raise ValueError(
            "V6 repair contract changed outside the permitted alignment file: "
            + ", ".join(changed)
        )


def _resolve_v6_output_path(
    project_dir: Path,
    output_path: str | Path | None,
    construction_mode: str,
) -> Path:
    if output_path is not None:
        return Path(output_path).expanduser().resolve()
    suffix = "解构版" if construction_mode == "deconstruct" else "位图版"
    return (
        project_dir / "output" / f"{project_dir.name}_{suffix}.pptx"
    ).resolve()


def _run_v6_windows_deconstruct_fidelity_audit(
    project_dir: Path,
    brief: dict[str, Any],
) -> dict[str, Any]:
    """Run the V5.8.4/V5.9.6 blueprint benchmark on the V6 Windows route."""

    fidelity = _load_module(
        "standard_report_v6_windows_blueprint_fidelity",
        Path(__file__).with_name("blueprint_fidelity.py"),
    )
    pairs = []
    missing_render_ids = []
    for index in range(1, int(brief["requested_page_count"]) + 1):
        slide_id = f"S{index:02d}"
        blueprint = project_dir / "blueprints" / f"{slide_id}.png"
        rendered = (
            project_dir
            / ".build"
            / "rendered"
            / "current"
            / f"{slide_id}.png"
        )
        if not rendered.is_file():
            missing_render_ids.append(slide_id)
            continue
        pairs.append((slide_id, blueprint, rendered))
    report = fidelity.compare_deck(
        pairs,
        expected_page_count=int(brief["requested_page_count"]),
    )
    if missing_render_ids:
        report["missing_render_slide_ids"] = missing_render_ids
    _write_json_atomic(
        project_dir / ".build" / "blueprint_fidelity.json",
        report,
    )
    return report


def _run_v6_project(
    project_dir: Path,
    brief: dict[str, Any],
    output_path: str | Path | None,
    *,
    catastrophic_repair: bool,
    user_revision: bool,
    auto_package: bool,
) -> dict[str, Any]:
    if user_revision:
        raise ValueError("V6 user revisions require a new explicit project run")
    mode = str(brief["construction_mode"])
    output = _resolve_v6_output_path(project_dir, output_path, mode)
    bitmap_release = None
    if mode == "bitmap":
        bitmap_release = _load_module(
            "standard_report_v62_bitmap_acceptance",
            Path(__file__).with_name("v62_bitmap_acceptance.py"),
        )
        locked = bitmap_release.locked_acceptance(project_dir, output)
        if locked is not None and not catastrophic_repair:
            result_path = project_dir / ".build" / "pipeline_result.json"
            if not result_path.is_file():
                raise ValueError("V6.2 locked bitmap build is missing pipeline_result.json")
            result = _read_json(result_path)
            result["cached"] = True
            result["bitmap_acceptance"] = locked
            return result
    attempt_path = project_dir / ".build" / "v6_build_attempt.json"
    previous = _read_json(attempt_path) if attempt_path.is_file() else {}
    previous_count = int(previous.get("attempt_count", 0))
    if (
        not catastrophic_repair
        and mode == "deconstruct"
        and previous_count == 1
        and previous.get("status") == "success"
    ):
        acceptance_module = _load_module(
            "standard_report_v61_deconstruction_acceptance_reuse",
            Path(__file__).with_name("v61_deconstruction_acceptance.py"),
        )
        acceptance = acceptance_module.locked_deconstruction_acceptance(
            project_dir, output
        )
        result_path = project_dir / ".build" / "pipeline_result.json"
        if acceptance is not None and result_path.is_file():
            result = _read_json(result_path)
            if result.get("pptx_sha256") != _sha256_file(output):
                raise ValueError("V6.1 accepted deconstruction result hash is stale")
            result["cached"] = True
            result["deconstruction_acceptance"] = str(
                project_dir / ".build" / "deconstruction_acceptance.json"
            )
            if auto_package:
                delivery = Path(str(result.get("delivery", "")))
                if not delivery.is_file():
                    packager = _load_module(
                        "standard_report_v6_packager_cached_deconstruction",
                        Path(__file__).with_name("pack_delivery.py"),
                    )
                    delivery = (
                        project_dir / "output" / f"{project_dir.name}_解构版.zip"
                    )
                    result["delivery"] = str(
                        packager.package_v6_delivery(
                            project_dir,
                            output,
                            project_dir / "generate_deck.py",
                            delivery,
                        )
                    )
            _write_json_atomic(result_path, result)
            return result
    if catastrophic_repair:
        if (
            previous_count != 1
            or previous.get("status") != "catastrophic_failed"
        ):
            raise ValueError(
                "V6 repair requires one catastrophic first-attempt failure"
            )
        if previous.get("construction_mode") != brief.get("construction_mode"):
            raise ValueError("V6 repair cannot change construction mode")
        if bitmap_release is not None and not bitmap_release.rebuild_allowed(
            project_dir,
            catastrophic_repair=True,
            reason="BITMAP_CATASTROPHIC_FAILURE",
        ):
            raise ValueError(
                "V6.2 bitmap repair denied: only one recorded catastrophic repair is allowed"
            )
        _assert_v6_repair_contract_unchanged(
            project_dir,
            str(brief["construction_mode"]),
            previous.get("repair_contract_snapshot"),
        )
        attempt_count = 2
    else:
        if previous_count:
            raise ValueError(
                "V6 build is locked; use --repair-catastrophic for its one repair"
            )
        attempt_count = 1
    runtime = _ensure_project_runtime(
        project_dir, brief, probe_windows_com=False
    )
    backend = str(runtime["builder_backend"])
    if catastrophic_repair:
        if previous.get("builder_backend") != backend:
            raise ValueError("V6 repair cannot change builder backend")
    suffix = "解构版" if mode == "deconstruct" else "位图版"
    output.parent.mkdir(parents=True, exist_ok=True)
    attempt = {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "construction_mode": mode,
        "builder_backend": backend,
        "attempt_count": attempt_count,
        "imagegen_reused": True,
        "status": "in_progress",
    }
    _write_json_atomic(attempt_path, attempt)

    def guarded(stage_name: str, action: Callable[[], Any]) -> Any:
        try:
            return action()
        except Exception as exc:
            # A bitmap PPTX already accepted by V6.2 is never rebuilt merely
            # because the optional delivery ZIP failed.
            if bitmap_release is not None and stage_name == "package":
                raise
            failed = dict(attempt)
            failed.update(
                {
                    "status": "catastrophic_failed",
                    "failed_stage": stage_name,
                    "error": str(exc),
                    "repair_contract_snapshot": _v6_repair_contract_snapshot(
                        project_dir, mode
                    ),
                }
            )
            _write_json_atomic(attempt_path, failed)
            if bitmap_release is not None:
                bitmap_release.write_catastrophic_failure(
                    project_dir,
                    stage=stage_name,
                    message=str(exc),
                    build_attempt=attempt_count,
                )
            raise

    batch_plan, reusable_slides = guarded(
        "preprocess_plan",
        lambda: _v6_preprocess_batches(project_dir, brief, backend),
    )
    preprocessed_slides = guarded(
        "preprocess_batches",
        lambda: _execute_v6_preprocess_batches(
            project_dir,
            brief,
            backend,
            batch_plan,
            reusable_slides,
        ),
    )
    guarded(
        "prebuild_validate",
        lambda: _stage(
            project_dir,
            "prebuild_validate",
            lambda: prebuild_project(
                project_dir,
                reuse_preprocessed_slide_ids=preprocessed_slides,
            ),
        ),
    )
    generator = guarded(
        "compile",
        lambda: compile_project(
            project_dir,
            _v6_post_lock_prepared=True,
        ),
    )
    if backend == "windows_com_v584":
        guarded(
            "windows_runtime",
            lambda: _load_module(
                "standard_report_windows_runtime_v6_build",
                Path(__file__).with_name("ensure_windows_runtime.py"),
            ).ensure_windows_runtime(project_dir=project_dir, probe_com=True),
        )
    guarded(
        "build",
        lambda: _stage(
            project_dir,
            "build",
            lambda: _run(
                [sys.executable, str(generator), "--output", str(output)],
                timeout=180,
            ),
        ),
    )
    guarded("build", lambda: _mark_v6_whole_deck_built(project_dir))
    if backend == "windows_com_v584":
        guarded(
            "render",
            lambda: _stage(
                project_dir,
                "render",
                lambda: _run(
                    [
                        sys.executable,
                        str(Path(__file__).with_name("render_slides.py")),
                        str(output),
                        "--project",
                        str(project_dir),
                        "--expected",
                        str(brief["requested_page_count"]),
                        "--timeout",
                        "45",
                    ],
                    timeout=180,
                ),
            ),
        )
        render_result = {
            "ok": True,
            "status": "pass",
            "renderer": "powerpoint_windows",
            "visual_verification": True,
        }
    else:
        renderer = guarded(
            "render",
            lambda: _load_module(
                "standard_report_v6_macos_render",
                Path(__file__).with_name("mac_render_slides.py"),
            ),
        )
        render_result = guarded(
            "render",
            lambda: _stage(
                project_dir,
                "render",
                lambda: renderer.render_project(
                    output,
                    project_dir,
                    expected_page_count=int(brief["requested_page_count"]),
                ),
            ),
        )
        mac_quality = guarded(
            "mac_quality",
            lambda: _load_module(
                "standard_report_v6_macos_quality",
                Path(__file__).with_name("mac_quality.py"),
            ),
        )
        font_path = project_dir / ".build" / "font_report.json"
        mac_report = guarded(
            "mac_quality",
            lambda: mac_quality.audit_mac_pptx(
                output,
                expected_page_count=int(brief["requested_page_count"]),
                render_result=render_result,
                project_dir=project_dir,
                font_fallbacks=(
                    _read_json(font_path).get("fallbacks", [])
                    if font_path.is_file()
                    else []
                ),
            ),
        )
        guarded(
            "mac_quality",
            lambda: _write_json_atomic(
                project_dir / ".build" / "mac_quality_report.json", mac_report
            ),
        )
        if mac_report.get("status") == "blocked":
            guarded(
                "mac_quality",
                lambda: (_ for _ in ()).throw(
                    ValueError(
                        "Mac PPTX audit failed: "
                        + "; ".join(
                            str(item) for item in mac_report.get("errors", [])
                        )
                    )
                ),
            )
    fidelity_report = None
    if mode == "deconstruct" and backend == "windows_com_v584":
        fidelity_report = guarded(
            "blueprint_fidelity",
            lambda: _run_v6_windows_deconstruct_fidelity_audit(
                project_dir,
                brief,
            ),
        )
    audit_module = guarded(
        "postbuild_audit",
        lambda: _load_module(
            "standard_report_v6_postbuild_editability",
            Path(__file__).with_name("v6_editability_audit.py"),
        ),
    )
    if mode == "deconstruct":
        precheck = guarded(
            "postbuild_audit",
            lambda: _read_json(
                project_dir / ".build" / "deconstruction_precheck.json"
            ),
        )
        audit = guarded(
            "postbuild_audit",
            lambda: audit_module.audit_deconstruction_pptx(
                output,
                _read_json(project_dir / ".build" / "page_specs.json"),
                _read_json(project_dir / ".build" / "blueprint_alignment.json"),
                allowed_large_visual_assets_by_page=precheck.get(
                    "allowed_large_visual_assets_by_page", {}
                ),
                builder_backend=backend,
            ),
        )
        audit_path = project_dir / ".build" / "deconstruction_editability_audit.json"
    else:
        audit = guarded(
            "postbuild_audit",
            lambda: audit_module.audit_bitmap_pptx(
                output,
                _read_json(project_dir / ".build" / "bitmap_contract.json"),
                project_dir,
            ),
        )
        audit_path = project_dir / ".build" / "bitmap_pptx_audit.json"
    guarded(
        "postbuild_audit",
        lambda: audit.update(
            {
                "pptx_sha256": _sha256_file(output),
                "construction_mode": mode,
                "builder_backend": backend,
            }
        ),
    )
    guarded(
        "postbuild_audit", lambda: _write_json_atomic(audit_path, audit)
    )
    if not audit.get("ok") and mode != "deconstruct":
        guarded(
            "postbuild_audit",
            lambda: (_ for _ in ()).throw(
                ValueError(
                    "V6 postbuild audit failed: "
                    + "; ".join(
                        str(item.get("message", item))
                        for item in audit.get("blockers", [])
                    )
                )
            ),
        )
    acceptance = None
    acceptance_path = None
    if mode == "deconstruct":
        acceptance_module = guarded(
            "deconstruction_acceptance",
            lambda: _load_module(
                "standard_report_v61_deconstruction_acceptance",
                Path(__file__).with_name("v61_deconstruction_acceptance.py"),
            ),
        )
        acceptance = guarded(
            "deconstruction_acceptance",
            lambda: acceptance_module.evaluate_deconstruction_acceptance(
                project_dir=project_dir,
                pptx_path=output,
                brief=brief,
                builder_backend=backend,
                precheck=precheck,
                editability_audit=audit,
                render_result=render_result,
                fidelity_report=fidelity_report,
            ),
        )
        acceptance_path = guarded(
            "deconstruction_acceptance",
            lambda: acceptance_module.write_deconstruction_acceptance(
                project_dir, acceptance
            ),
        )
        if not acceptance.get("accepted"):
            guarded(
                "deconstruction_acceptance",
                lambda: (_ for _ in ()).throw(
                    ValueError(
                        "V6.1 deconstruction acceptance failed: "
                        + "; ".join(
                            str(item.get("message", item))
                            for item in acceptance.get("blockers", [])
                        )
                    )
                ),
            )
    contracts = guarded(
        "finalize",
        lambda: _load_module(
            "standard_report_v6_cache_contracts",
            Path(__file__).with_name("v6_contracts.py"),
        ),
    )

    def finalize_cache() -> dict[str, Any]:
        cache = contracts.post_lock_cache_payload(brief, backend)
        cache["blueprint_hashes"] = {
            f"S{index:02d}": _sha256_file(
                project_dir / "blueprints" / f"S{index:02d}.png"
            )
            for index in range(1, int(brief["requested_page_count"]) + 1)
        }
        cache["fingerprint_sha256"] = hashlib.sha256(
            json.dumps(cache, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        _write_json_atomic(
            project_dir / ".build" / "v6_cache_fingerprint.json", cache
        )
        return cache

    cache_payload = guarded("finalize", finalize_cache)
    result = {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "skill_version": "6.1.0" if mode == "deconstruct" else "6.0.1",
        "production_mode": "blueprint",
        "construction_mode": mode,
        "builder_backend": backend,
        "ok": True,
        "pptx": str(output),
        "pptx_sha256": _sha256_file(output),
        "pages": int(brief["requested_page_count"]),
        "build_attempt": attempt_count,
        "postbuild_audit": str(audit_path),
        "render_status": render_result.get("status"),
        "blueprint_fidelity": (
            str(project_dir / ".build" / "blueprint_fidelity.json")
            if fidelity_report is not None
            else None
        ),
        "visual_verification": bool(render_result.get("visual_verification")),
        "deconstruction_acceptance": (
            str(acceptance_path) if acceptance_path is not None else None
        ),
    }
    if bitmap_release is not None:
        acceptance = guarded(
            "finalize",
            lambda: bitmap_release.write_acceptance(
                project_dir,
                output,
                bitmap_audit=audit,
                build_attempt=attempt_count,
            ),
        )
        result["skill_version"] = "6.2"
        result["bitmap_acceptance"] = acceptance
        result["automatic_recrop_allowed"] = False
    guarded(
        "finalize",
        lambda: _write_json_atomic(
            project_dir / ".build" / "pipeline_result.json", result
        ),
    )
    successful_attempt = dict(attempt)
    successful_attempt.update(
        {
            "status": "success",
            "pptx_sha256": result["pptx_sha256"],
            "postbuild_audit": str(audit_path),
        }
    )
    guarded(
        "finalize", lambda: _write_json_atomic(attempt_path, successful_attempt)
    )
    if (
        auto_package
        and render_result.get("status") != "structurally_valid_unrendered"
    ):
        packager = _load_module(
            "standard_report_v6_packager",
            Path(__file__).with_name("pack_delivery.py"),
        )
        delivery = project_dir / "output" / f"{project_dir.name}_{suffix}.zip"
        result["delivery"] = str(
            guarded(
                "package",
                lambda: packager.package_v6_delivery(
                    project_dir, output, generator, delivery
                ),
            )
        )
        guarded(
            "package",
            lambda: _write_json_atomic(
                project_dir / ".build" / "pipeline_result.json", result
            ),
        )
    elif auto_package:
        result["delivery_blocked_reason"] = "MAC_RENDERER_UNAVAILABLE"
        guarded(
            "package",
            lambda: _write_json_atomic(
                project_dir / ".build" / "pipeline_result.json", result
            ),
        )
    return result


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
    if brief.get("schema_version") == "6.0":
        gate = _load_module(
            "standard_report_v6_imagegen_gate_run",
            Path(__file__).with_name("v6_blueprint_gate.py"),
        )
        gate.assert_imagegen_invocation_gate(project_dir)
        return _run_v6_project(
            project_dir,
            brief,
            output_path,
            catastrophic_repair=catastrophic_repair,
            user_revision=user_revision,
            auto_package=auto_package,
        )
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
    parser = argparse.ArgumentParser(description="Version-aware Standard Report PPT project pipeline.")
    parser.add_argument("project", type=Path)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--preflight", action="store_true")
    actions.add_argument("--init", action="store_true")
    actions.add_argument("--compile", action="store_true")
    actions.add_argument("--materialize", action="store_true")
    actions.add_argument("--prepare-visual-review", action="store_true")
    actions.add_argument("--prepare-bitmap-review", action="store_true")
    actions.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--repair-catastrophic",
        action="store_true",
        help="Permit the single bounded catastrophic repair build (V5.9.5 or V6.2 bitmap)",
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
        payload = {
            "schema_version": _project_schema_version(args.project),
            "generator": str(compile_project(args.project)),
        }
    elif args.materialize:
        payload = materialize_project(args.project)
    elif args.prepare_visual_review:
        payload = prepare_visual_review(args.project)
    elif args.prepare_bitmap_review:
        payload = prepare_bitmap_review(args.project)
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
