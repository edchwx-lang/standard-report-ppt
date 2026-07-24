from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.0"
PIPELINE_REVISION = "6.0.0"
IMAGEGEN_UNAVAILABLE = "IMAGEGEN_UNAVAILABLE"
BLUEPRINT_TRANSPORT_FAILED = "BLUEPRINT_TRANSPORT_FAILED"
_IMMEDIATE_FAILURES = {"tool_unavailable", "auth_or_policy"}


def _load_v59():
    path = Path(__file__).with_name("v59_blueprint_gate.py")
    spec = importlib.util.spec_from_file_location("standard_report_v59_gate_for_v6", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a mapping")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _brief(project: Path) -> dict[str, Any]:
    value = _read(project / "project_brief.json")
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("pipeline_revision") != PIPELINE_REVISION
        or value.get("production_mode") != "blueprint"
        or value.get("construction_mode") not in {"deconstruct", "bitmap"}
    ):
        raise ValueError("V6 blueprint gate requires a valid explicit construction mode")
    return value


def _normalize_reports(project: Path, construction_mode: str) -> None:
    for relative in (
        ".build/imagegen_transport_report.json",
        ".build/visual_manifest.json",
    ):
        path = project / relative
        if not path.is_file():
            continue
        payload = _read(path)
        payload["schema_version"] = SCHEMA_VERSION
        payload["pipeline_revision"] = PIPELINE_REVISION
        payload["construction_mode"] = construction_mode
        _write(path, payload)


def record_artifact(
    project_dir: str | Path,
    slide_id: str,
    source_path: str | Path,
    *,
    transport_attempt_count: int,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    brief = _brief(project)
    result = _load_v59().record_artifact(
        project,
        slide_id,
        source_path,
        transport_attempt_count=transport_attempt_count,
    )
    result.update(
        {
            "schema_version": SCHEMA_VERSION,
            "pipeline_revision": PIPELINE_REVISION,
            "construction_mode": brief["construction_mode"],
            "error_code": None,
        }
    )
    _normalize_reports(project, str(brief["construction_mode"]))
    return result


def record_failure(
    project_dir: str | Path,
    slide_id: str,
    failure_class: str,
    *,
    transport_attempt_count: int,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    brief = _brief(project)
    result = _load_v59().record_failure(
        project,
        slide_id,
        failure_class,
        transport_attempt_count=transport_attempt_count,
    )
    if failure_class in _IMMEDIATE_FAILURES:
        result["resumable"] = False
        error_code = IMAGEGEN_UNAVAILABLE
    elif transport_attempt_count == 2:
        result["resumable"] = False
        error_code = BLUEPRINT_TRANSPORT_FAILED
    else:
        error_code = None
    result.update(
        {
            "schema_version": SCHEMA_VERSION,
            "pipeline_revision": PIPELINE_REVISION,
            "construction_mode": brief["construction_mode"],
            "error_code": error_code,
        }
    )
    path = project / ".build" / "imagegen_transport_report.json"
    payload = _read(path)
    payload["pages"][slide_id] = dict(result)
    if payload.get("history"):
        payload["history"][-1] = dict(result)
    _write(path, payload)
    _normalize_reports(project, str(brief["construction_mode"]))
    return result


def diagnose_blueprint_gate(
    project_dir: str | Path, *, require_alignment: bool | None = None
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    brief = _brief(project)
    if require_alignment is None:
        require_alignment = brief["construction_mode"] == "deconstruct"
    result = _load_v59().diagnose_blueprint_gate(project, require_alignment=False)
    if require_alignment:
        alignment_path = project / ".build" / "blueprint_alignment.json"
        alignment_pages = (
            _read(alignment_path).get("pages", {}) if alignment_path.is_file() else {}
        )
        for slide_id, page_result in result.get("pages", {}).items():
            page = (
                alignment_pages.get(slide_id, {})
                if isinstance(alignment_pages, dict)
                else {}
            )
            blueprint = project / "blueprints" / f"{slide_id}.png"
            digest = _load_v59().sha256_file(blueprint) if blueprint.is_file() else None
            errors = []
            if not isinstance(page, dict) or page.get("reviewed") is not True:
                errors.append("reviewed blueprint alignment is missing")
            elif page.get("design_draft_sha256") != digest:
                errors.append("reviewed blueprint alignment is stale")
            elif not isinstance(page.get("resolved_page_spec"), dict):
                errors.append("reviewed blueprint alignment has no resolved page spec")
            if errors:
                page_result["ok"] = False
                page_result["errors"].extend(errors)
                result["errors"].extend(
                    f"{slide_id}: {message}" for message in errors
                )
        result["ok"] = not result["errors"]
    result.update(
        {
            "schema_version": SCHEMA_VERSION,
            "pipeline_revision": PIPELINE_REVISION,
            "construction_mode": brief["construction_mode"],
        }
    )
    return result


def assert_blueprint_gate(
    project_dir: str | Path, *, require_alignment: bool | None = None
) -> dict[str, Any]:
    result = diagnose_blueprint_gate(project_dir, require_alignment=require_alignment)
    if not result["ok"]:
        raise ValueError("blueprint gate failed: " + "; ".join(result["errors"]))
    return result
