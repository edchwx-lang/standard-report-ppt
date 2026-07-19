from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image


FAILURE_CLASSES = {
    "tool_unavailable", "transport_timeout", "empty_response",
    "auth_or_policy", "rate_limit", "invalid_artifact",
}


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def resolve_artifact_source(project: Path, source_path: str | Path) -> Path:
    source = Path(source_path)
    if not source.is_absolute():
        source = project / source
    return source.resolve(strict=True)


def _record_transport_event(
    report: dict[str, Any],
    record: dict[str, Any],
) -> None:
    report.setdefault("pages", {})[record["slide_id"]] = record
    report.setdefault("history", []).append(dict(record))


def _bind_authoring_bundle(
    project: Path,
    slide_id: str,
    digest: str,
    transport_attempt_count: int,
) -> None:
    path = project / ".build" / "authoring_bundle.json"
    if not path.is_file():
        return
    bundle = _read(path, {})
    page = (
        bundle.setdefault("visual_manifest", {})
        .setdefault("pages", {})
        .setdefault(slide_id, {})
    )
    page.update(
        {
            "design_draft_path": f".build/design_drafts/{slide_id}.png",
            "design_draft_sha256": digest,
            "formal_blueprint_path": f"blueprints/{slide_id}.png",
            "formal_blueprint_sha256": digest,
            "imagegen_mode": "builtin",
            "imagegen_attempt_count": 1,
            "transport_attempt_count": transport_attempt_count,
        }
    )
    _write(path, bundle)


def _expected_ids(project: Path) -> list[str]:
    count = _read(project / "project_brief.json", {}).get("requested_page_count")
    if not isinstance(count, int) or count <= 0:
        raise ValueError("requested_page_count must be a positive integer")
    return [f"S{index:02d}" for index in range(1, count + 1)]


def _validate_image(path: Path) -> None:
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    ratio = width / height if height else 0
    if not 1.50 <= ratio <= 2.05:
        raise ValueError(f"blueprint aspect ratio outside 1.50-2.05: {ratio:.3f}")


def record_artifact(
    project_dir: str | Path,
    slide_id: str,
    source_path: str | Path,
    *,
    transport_attempt_count: int,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    if slide_id not in _expected_ids(project):
        raise ValueError(f"unknown slide_id: {slide_id}")
    if transport_attempt_count not in {1, 2}:
        raise ValueError("transport_attempt_count must be 1 or 2")
    source = resolve_artifact_source(project, source_path)
    _validate_image(source)
    digest = sha256_file(source)
    draft = project / ".build" / "design_drafts" / f"{slide_id}.png"
    formal = project / "blueprints" / f"{slide_id}.png"
    for locked in (draft, formal):
        if locked.is_file() and sha256_file(locked) != digest:
            raise ValueError(f"{slide_id} is already locked to a different ImageGen artifact")
    draft.parent.mkdir(parents=True, exist_ok=True)
    formal.parent.mkdir(parents=True, exist_ok=True)
    if not draft.is_file():
        shutil.copyfile(source, draft)
    if not formal.is_file():
        shutil.copyfile(draft, formal)
    if sha256_file(draft) != sha256_file(formal):
        raise ValueError(f"{slide_id}: formal blueprint differs from ImageGen draft")
    _bind_authoring_bundle(
        project,
        slide_id,
        digest,
        transport_attempt_count,
    )
    record = {
        "slide_id": slide_id, "imagegen_mode": "builtin",
        "imagegen_attempt_count": 1, "transport_attempt_count": transport_attempt_count,
        "artifact_received": True, "artifact_sha256": digest,
        "failure_class": "artifact_received", "resumable": True,
    }
    report_path = project / ".build" / "imagegen_transport_report.json"
    report = _read(report_path, {"schema_version": "5.9", "pages": {}})
    _record_transport_event(report, record)
    _write(report_path, report)
    manifest_path = project / ".build" / "visual_manifest.json"
    manifest = _read(manifest_path, {"schema_version": "5.9", "pages": {}})
    manifest.setdefault("pages", {})[slide_id] = {
        **manifest.get("pages", {}).get(slide_id, {}),
        "design_draft_path": f".build/design_drafts/{slide_id}.png",
        "design_draft_sha256": digest,
        "formal_blueprint_path": f"blueprints/{slide_id}.png",
        "formal_blueprint_sha256": digest,
        "imagegen_mode": "builtin",
        "imagegen_attempt_count": 1,
        "transport_attempt_count": transport_attempt_count,
    }
    manifest["schema_version"] = "5.9"
    _write(manifest_path, manifest)
    return record


def record_failure(
    project_dir: str | Path,
    slide_id: str,
    failure_class: str,
    *,
    transport_attempt_count: int,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    if slide_id not in _expected_ids(project):
        raise ValueError(f"unknown slide_id: {slide_id}")
    if failure_class not in FAILURE_CLASSES:
        raise ValueError(f"unsupported failure_class: {failure_class}")
    if transport_attempt_count not in {1, 2}:
        raise ValueError("transport_attempt_count must be 1 or 2")
    if (project / ".build" / "design_drafts" / f"{slide_id}.png").is_file():
        raise ValueError("cannot record a no-artifact failure after an artifact exists")
    record = {
        "slide_id": slide_id, "imagegen_mode": "builtin",
        "imagegen_attempt_count": 1, "transport_attempt_count": transport_attempt_count,
        "artifact_received": False, "artifact_sha256": None,
        "failure_class": failure_class, "resumable": transport_attempt_count < 2,
    }
    path = project / ".build" / "imagegen_transport_report.json"
    report = _read(path, {"schema_version": "5.9", "pages": {}})
    _record_transport_event(report, record)
    _write(path, report)
    return record


def diagnose_blueprint_gate(project_dir: str | Path, *, require_alignment: bool = True) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    brief = _read(project / "project_brief.json", {})
    if brief.get("production_mode") != "blueprint":
        return {"schema_version": "5.9", "ok": True, "pages": {}, "errors": []}
    manifest_pages = _read(project / ".build" / "visual_manifest.json", {}).get("pages", {})
    transport_pages = _read(project / ".build" / "imagegen_transport_report.json", {}).get("pages", {})
    alignment_pages = _read(project / ".build" / "blueprint_alignment.json", {}).get("pages", {})
    page_specs = _read(project / ".build" / "page_specs.json", {})
    pages: dict[str, Any] = {}
    errors: list[str] = []
    for slide_id in _expected_ids(project):
        draft = project / ".build" / "design_drafts" / f"{slide_id}.png"
        formal = project / "blueprints" / f"{slide_id}.png"
        page_errors: list[str] = []
        for label, path in (("design draft", draft), ("formal blueprint", formal)):
            if not path.is_file():
                page_errors.append(f"{label} is missing")
            else:
                try:
                    _validate_image(path)
                except (OSError, ValueError) as exc:
                    page_errors.append(f"{label} is invalid: {exc}")
        digest = sha256_file(draft) if draft.is_file() else None
        if draft.is_file() and formal.is_file() and sha256_file(formal) != digest:
            page_errors.append("formal blueprint is not byte-identical to design draft")
        manifest = manifest_pages.get(slide_id, {})
        if (
            manifest.get("design_draft_sha256") != digest
            or manifest.get("formal_blueprint_sha256") != digest
        ):
            page_errors.append("visual manifest does not bind the locked blueprint pair")
        transport = transport_pages.get(slide_id, {})
        if (
            transport.get("artifact_received") is not True
            or transport.get("artifact_sha256") != digest
            or transport.get("imagegen_attempt_count") != 1
        ):
            page_errors.append("ImageGen transport report does not bind the received artifact")
        if require_alignment:
            alignment = alignment_pages.get(slide_id, {})
            if alignment.get("reviewed") is not True:
                page_errors.append("reviewed blueprint alignment is missing")
            elif alignment.get("design_draft_sha256") != digest:
                page_errors.append("reviewed blueprint alignment is stale")
            elif alignment.get("resolved_page_spec") != page_specs.get(slide_id):
                page_errors.append("page_specs do not consume the reviewed alignment")
        pages[slide_id] = {"ok": not page_errors, "errors": page_errors}
        errors.extend(f"{slide_id}: {message}" for message in page_errors)
    return {"schema_version": "5.9", "ok": not errors, "pages": pages, "errors": errors}


def assert_blueprint_gate(project_dir: str | Path, *, require_alignment: bool = True) -> dict[str, Any]:
    result = diagnose_blueprint_gate(project_dir, require_alignment=require_alignment)
    if not result["ok"]:
        raise ValueError("blueprint gate failed: " + "; ".join(result["errors"]))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--slide-id")
    parser.add_argument("--record-artifact", type=Path)
    parser.add_argument("--record-failure", choices=sorted(FAILURE_CLASSES))
    parser.add_argument("--transport-attempt-count", type=int)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.record_artifact:
        payload = record_artifact(
            args.project, args.slide_id, args.record_artifact,
            transport_attempt_count=args.transport_attempt_count,
        )
    elif args.record_failure:
        payload = record_failure(
            args.project, args.slide_id, args.record_failure,
            transport_attempt_count=args.transport_attempt_count,
        )
    elif args.check:
        payload = assert_blueprint_gate(args.project)
    else:
        parser.error("choose --record-artifact, --record-failure, or --check")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
