from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _pages(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    pages = value.get("pages")
    return pages if isinstance(pages, dict) else value


def _issue(code: str, message: str, slide_id: str = "") -> dict[str, str]:
    return {
        "code": code,
        "severity": "blocker",
        "stage": "deconstruction_acceptance",
        "slide_id": slide_id,
        "message": message,
    }


def _warning(code: str, message: str, slide_id: str = "") -> dict[str, str]:
    value = _issue(code, message, slide_id)
    value["severity"] = "warning"
    return value


def _classify_precheck(blocker: Any) -> dict[str, str]:
    item = blocker if isinstance(blocker, dict) else {}
    code = str(item.get("code", ""))
    message = str(item.get("message", blocker))
    slide_id = str(item.get("slide_id", ""))
    if "TOPOLOGY" in code:
        return _issue("D61_TOPOLOGY_MISMATCH", message, slide_id)
    return _issue("D61_VISUAL_SEMANTICS", message, slide_id)


def _classify_editability(blocker: Any) -> dict[str, str]:
    item = blocker if isinstance(blocker, dict) else {}
    message = str(item.get("message", blocker))
    slide_id = str(item.get("slide_id", ""))
    normalized = message.lower()
    if any(marker in normalized for marker in ("selected text", "encoding", "mojibake")):
        return _issue("D61_TEXT_MISMATCH", message, slide_id)
    return _issue("D61_VISUAL_SEMANTICS", message, slide_id)


def evaluate_deconstruction_acceptance(
    *,
    project_dir: str | Path,
    pptx_path: str | Path,
    brief: dict[str, Any],
    builder_backend: str,
    precheck: dict[str, Any],
    editability_audit: dict[str, Any],
    render_result: dict[str, Any],
    fidelity_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    pptx = Path(pptx_path).resolve()
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if (
        brief.get("schema_version") != "6.0"
        or brief.get("pipeline_revision") != "6.0.0"
        or brief.get("construction_mode") != "deconstruct"
    ):
        blockers.append(
            _issue("D61_CONTRACT_INVALID", "not a V6 deconstruction project")
        )
    if not pptx.is_file():
        blockers.append(_issue("D61_RENDER_INVALID", "PPTX is missing"))

    expected_ids = {
        f"S{index:02d}"
        for index in range(1, int(brief.get("requested_page_count", 0)) + 1)
    }
    try:
        alignment = _read_json(project / ".build" / "blueprint_alignment.json")
        page_specs = _read_json(project / ".build" / "page_specs.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(_issue("D61_CONTRACT_INVALID", str(exc)))
        alignment = {}
        page_specs = {}
    aligned_pages = _pages(alignment)
    spec_pages = _pages(page_specs)
    if set(aligned_pages) != expected_ids or set(spec_pages) != expected_ids:
        blockers.append(
            _issue(
                "D61_CONTRACT_INVALID",
                "alignment, page specs, and requested page ids must match",
            )
        )

    for slide_id in sorted(expected_ids):
        page = aligned_pages.get(slide_id, {})
        spec = spec_pages.get(slide_id, {})
        visuals = page.get("visuals", []) if isinstance(page, dict) else []
        elements = spec.get("elements", []) if isinstance(spec, dict) else []
        expected_crops = [
            item.get("asset_id")
            for item in visuals
            if isinstance(item, dict) and item.get("treatment") == "crop"
        ]
        actual_crops = [
            item.get("asset_id")
            for item in elements
            if isinstance(item, dict) and item.get("type") == "asset"
        ]
        for asset_id in expected_crops:
            valid_id = isinstance(asset_id, str) and bool(asset_id)
            asset_path = (
                project / ".build" / "assets" / slide_id / f"{asset_id}.png"
                if valid_id
                else None
            )
            if (
                not valid_id
                or actual_crops.count(asset_id) != 1
                or asset_path is None
                or not asset_path.is_file()
            ):
                blockers.append(
                    _issue(
                        "D61_CROP_MISSING",
                        f"declared crop {asset_id!r} must be extracted and inserted exactly once",
                        slide_id,
                    )
                )

    if precheck.get("ok") is not True:
        reported = precheck.get("blockers", [])
        if reported:
            blockers.extend(_classify_precheck(item) for item in reported)
        else:
            blockers.append(
                _issue("D61_VISUAL_SEMANTICS", "deconstruction precheck failed")
            )
    if editability_audit.get("ok") is not True:
        reported = editability_audit.get("blockers", [])
        if reported:
            blockers.extend(_classify_editability(item) for item in reported)
        else:
            blockers.append(
                _issue("D61_TEXT_MISMATCH", "deconstruction editability audit failed")
            )
    if (
        render_result.get("visual_verification") is not True
        or render_result.get("status") not in {"pass", "pass_with_warnings"}
    ):
        blockers.append(
            _issue(
                "D61_RENDER_INVALID",
                "render must be visually verified and nonblank before acceptance",
            )
        )
    if isinstance(fidelity_report, dict) and fidelity_report.get("passed") is False:
        for slide_id in fidelity_report.get("failed_slide_ids", []) or [""]:
            warnings.append(
                _warning(
                    "D61_FIDELITY_ADVISORY",
                    "pixel-level blueprint fidelity is advisory and does not authorize reconstruction",
                    str(slide_id),
                )
            )

    accepted = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline_revision": "6.0.0",
        "construction_mode": "deconstruct",
        "builder_backend": builder_backend,
        "accepted": accepted,
        "decision": "accept" if accepted else "repair_required",
        "pptx": str(pptx),
        "pptx_sha256": _sha256(pptx) if pptx.is_file() else None,
        "page_count": len(expected_ids),
        "criteria": {
            "selected_text_present": not any(
                item["code"] == "D61_TEXT_MISMATCH" for item in blockers
            ),
            "declared_crops_complete": not any(
                item["code"] == "D61_CROP_MISSING" for item in blockers
            ),
            "visual_semantics_preserved": not any(
                item["code"]
                in {"D61_TOPOLOGY_MISMATCH", "D61_VISUAL_SEMANTICS"}
                for item in blockers
            ),
            "render_valid": not any(
                item["code"] == "D61_RENDER_INVALID" for item in blockers
            ),
        },
        "manual_adjustment_allowed": [
            "asset_text_overlap",
            "text_capacity",
            "spacing",
            "alignment",
            "ordinary_fidelity",
        ],
        "warnings": warnings,
        "blockers": blockers,
        "warning_count": len(warnings),
        "blocker_count": len(blockers),
    }


def write_deconstruction_acceptance(
    project_dir: str | Path, result: dict[str, Any]
) -> Path:
    path = Path(project_dir).resolve() / ".build" / "deconstruction_acceptance.json"
    _write_json(path, result)
    return path


def locked_deconstruction_acceptance(
    project_dir: str | Path, pptx_path: str | Path
) -> dict[str, Any] | None:
    path = Path(project_dir).resolve() / ".build" / "deconstruction_acceptance.json"
    pptx = Path(pptx_path).resolve()
    if not path.is_file() or not pptx.is_file():
        return None
    try:
        result = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if (
        result.get("schema_version") == SCHEMA_VERSION
        and result.get("construction_mode") == "deconstruct"
        and result.get("accepted") is True
        and result.get("decision") == "accept"
        and result.get("pptx_sha256") == _sha256(pptx)
    ):
        return result
    return None
