from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.0"
PIPELINE_REVISION = "6.0.0"
IMAGEGEN_UNAVAILABLE = "IMAGEGEN_UNAVAILABLE"
BLUEPRINT_TRANSPORT_FAILED = "BLUEPRINT_TRANSPORT_FAILED"
IMAGEGEN_INVOCATION_REQUIRED = "V6_IMAGEGEN_INVOCATION_REQUIRED"
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


def _transport_events(project: Path, slide_id: str) -> list[dict[str, Any]]:
    path = project / ".build" / "imagegen_transport_report.json"
    if not path.is_file():
        return []
    report = _read(path)
    history = report.get("history", [])
    events = [
        item
        for item in history
        if isinstance(item, dict) and item.get("slide_id") == slide_id
    ]
    if events:
        return events
    current = report.get("pages", {}).get(slide_id)
    return [current] if isinstance(current, dict) else []


def _assert_next_transport_event(
    project: Path, slide_id: str, transport_attempt_count: int
) -> None:
    events = _transport_events(project, slide_id)
    if not events:
        expected = 1
    else:
        current = events[-1]
        terminal = (
            current.get("artifact_received") is True
            or current.get("error_code")
            in {IMAGEGEN_UNAVAILABLE, BLUEPRINT_TRANSPORT_FAILED}
            or current.get("resumable") is False
        )
        if terminal:
            raise ValueError(f"{slide_id}: ImageGen transport state is terminal")
        prior = current.get("transport_attempt_count")
        if not isinstance(prior, int):
            raise ValueError(f"{slide_id}: ImageGen transport history is invalid")
        expected = prior + 1
    if transport_attempt_count != expected or expected not in {1, 2}:
        raise ValueError(
            f"{slide_id}: next transport attempt must be {expected}"
        )


def record_artifact(
    project_dir: str | Path,
    slide_id: str,
    source_path: str | Path,
    *,
    transport_attempt_count: int,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    brief = _brief(project)
    _assert_next_transport_event(project, slide_id, transport_attempt_count)
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
    _assert_next_transport_event(project, slide_id, transport_attempt_count)
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


def diagnose_imagegen_invocation_gate(
    project_dir: str | Path,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    brief = _brief(project)
    transport_path = project / ".build" / "imagegen_transport_report.json"
    transport = _read(transport_path) if transport_path.is_file() else {}
    manifest_path = project / ".build" / "visual_manifest.json"
    manifest = _read(manifest_path) if manifest_path.is_file() else {}
    history = transport.get("history", [])
    if not isinstance(history, list):
        history = []
    pages: dict[str, Any] = {}
    errors: list[str] = []
    count = int(brief["requested_page_count"])
    for index in range(1, count + 1):
        slide_id = f"S{index:02d}"
        draft = project / ".build" / "design_drafts" / f"{slide_id}.png"
        formal = project / "blueprints" / f"{slide_id}.png"
        digest = _load_v59().sha256_file(draft) if draft.is_file() else None
        page_errors: list[str] = []
        if digest is None or not formal.is_file():
            page_errors.append("immutable ImageGen artifact pair is missing")
        elif _load_v59().sha256_file(formal) != digest:
            page_errors.append("formal blueprint is not bound to the ImageGen artifact")
        manifest_page = manifest.get("pages", {}).get(slide_id, {})
        if (
            manifest_page.get("design_draft_sha256") != digest
            or manifest_page.get("formal_blueprint_sha256") != digest
        ):
            page_errors.append("visual manifest does not bind the ImageGen artifact")
        current = transport.get("pages", {}).get(slide_id, {})
        if (
            current.get("artifact_received") is not True
            or current.get("artifact_sha256") != digest
            or current.get("imagegen_mode") != "builtin"
            or current.get("imagegen_attempt_count") != 1
        ):
            page_errors.append("current ImageGen transport state is not successful")
        successes = [
            event
            for event in history
            if isinstance(event, dict)
            and event.get("slide_id") == slide_id
            and event.get("imagegen_mode") == "builtin"
            and event.get("imagegen_attempt_count") == 1
            and event.get("transport_attempt_count") in {1, 2}
            and event.get("artifact_received") is True
            and event.get("artifact_sha256") == digest
            and event.get("failure_class") == "artifact_received"
        ]
        if len(successes) != 1:
            page_errors.append(
                "exactly one hash-bound ImageGen success history event is required"
            )
        pages[slide_id] = {"ok": not page_errors, "errors": page_errors}
        errors.extend(f"{slide_id}: {message}" for message in page_errors)
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline_revision": PIPELINE_REVISION,
        "construction_mode": brief["construction_mode"],
        "ok": not errors,
        "pages": pages,
        "errors": errors,
    }


def diagnose_blueprint_gate(
    project_dir: str | Path, *, require_alignment: bool | None = None
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    brief = _brief(project)
    if require_alignment is None:
        require_alignment = brief["construction_mode"] == "deconstruct"
    result = _load_v59().diagnose_blueprint_gate(project, require_alignment=False)
    invocation = diagnose_imagegen_invocation_gate(project)
    for slide_id, invocation_page in invocation["pages"].items():
        page_result = result["pages"][slide_id]
        for message in invocation_page["errors"]:
            tagged = f"{IMAGEGEN_INVOCATION_REQUIRED}: {message}"
            page_result["errors"].append(tagged)
            result["errors"].append(f"{slide_id}: {tagged}")
        page_result["ok"] = not page_result["errors"]
    result["ok"] = not result["errors"]
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


def assert_imagegen_invocation_gate(
    project_dir: str | Path,
) -> dict[str, Any]:
    result = diagnose_imagegen_invocation_gate(project_dir)
    if not result["ok"]:
        raise ValueError(
            f"{IMAGEGEN_INVOCATION_REQUIRED}: "
            + "; ".join(result["errors"])
        )
    return result


def assert_blueprint_gate(
    project_dir: str | Path, *, require_alignment: bool | None = None
) -> dict[str, Any]:
    result = diagnose_blueprint_gate(project_dir, require_alignment=require_alignment)
    if not result["ok"]:
        raise ValueError("blueprint gate failed: " + "; ".join(result["errors"]))
    return result
