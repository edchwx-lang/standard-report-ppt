from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


MAX_BUILD_ATTEMPTS = 2
GROSS_SCORE = 0.20
GROSS_LAYOUT_SCORE = 0.18
GROSS_MASS_RATIO = 0.35
BLANK_RENDER_DENSITY = 0.005


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _issue(code: str, message: str, slide_id: str = "") -> dict[str, Any]:
    return {
        "code": code,
        "severity": "blocker",
        "stage": "postbuild_release",
        "slide_id": slide_id,
        "message": message,
        "metrics": {},
    }


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_strings(item)


def _encoding_errors(value: Any) -> list[str]:
    errors: list[str] = []
    for text in _walk_strings(value):
        if re.search(r"\?{3,}", text):
            errors.append("question_mark_run")
        if "\ufffd" in text:
            errors.append("replacement_character")
        if any(0x80 <= ord(char) <= 0x9F for char in text):
            errors.append("c1_control")
    return sorted(set(errors))


def write_json_atomic_checked(path: str | Path, value: Any) -> Path:
    destination = Path(path)
    errors = _encoding_errors(value)
    if errors:
        raise ValueError(
            "refusing to write corrupted UTF-8 JSON: " + ", ".join(errors)
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    reread = json.loads(temporary.read_text(encoding="utf-8"))
    errors = _encoding_errors(reread)
    if errors:
        temporary.unlink(missing_ok=True)
        raise ValueError(
            "UTF-8 JSON verification failed: " + ", ".join(errors)
        )
    temporary.replace(destination)
    return destination


def _text_blockers(report: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for message in report.get("errors", []):
        text = str(message)
        normalized = text.lower()
        if any(
            marker in normalized
            for marker in (
                "question_mark_run",
                "replacement",
                "mojibake",
                "c1 control",
                "invalid slide xml",
                "critical text missing",
            )
        ):
            blockers.append(
                _issue("POSTBUILD_TEXT_CORRUPTION", text)
            )
        else:
            blockers.append(
                _issue("POSTBUILD_CRITICAL_TEXT_MISSING", text)
            )
    return blockers


def _fidelity_blockers(report: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for page in report.get("pages", []):
        if not isinstance(page, dict):
            continue
        slide_id = str(page.get("slide_id", ""))
        score = float(page.get("score", 1.0))
        layout = float(page.get("layout_score", 1.0))
        mass = float(page.get("ink_mass_ratio", 1.0))
        density = float(page.get("render_ink_density", 1.0))
        gross = (
            density < BLANK_RENDER_DENSITY
            or score < GROSS_SCORE
            or (layout < GROSS_LAYOUT_SCORE and mass < GROSS_MASS_RATIO)
        )
        if gross:
            issue = _issue(
                "POSTBUILD_GROSS_FIDELITY",
                "render is blank or differs grossly from the locked blueprint",
                slide_id,
            )
            issue["metrics"] = {
                "score": score,
                "layout_score": layout,
                "ink_mass_ratio": mass,
                "render_ink_density": density,
            }
            blockers.append(issue)
    return blockers


def _asset_blockers(report: dict[str, Any]) -> list[dict[str, Any]]:
    if report.get("ok") is True:
        return []
    messages = report.get("errors") or ["declared visual asset audit failed"]
    return [
        _issue("POSTBUILD_ASSET_CONTRACT", str(message))
        for message in messages
    ]


def _previous_attempt(project: Path) -> int:
    path = project / ".build" / "postbuild_release.json"
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0
    attempt = payload.get("build_attempt", 0)
    return attempt if isinstance(attempt, int) and attempt >= 0 else 0


def write_postbuild_release(
    project_dir: str | Path,
    pptx_path: str | Path,
    *,
    quality_report: dict[str, Any],
    text_audit: dict[str, Any],
    fidelity_report: dict[str, Any],
    asset_audit: dict[str, Any],
    build_attempt: int | None = None,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    pptx = Path(pptx_path).resolve()
    if not pptx.is_file():
        raise FileNotFoundError(pptx)
    attempt = build_attempt or (_previous_attempt(project) + 1)
    brief_path = project / "project_brief.json"
    skill_version = "5.9.5"
    if brief_path.is_file():
        try:
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            brief = {}
        if brief.get("pipeline_revision") in {"5.9.5", "5.9.6"}:
            skill_version = str(brief["pipeline_revision"])
    blockers = []
    blockers.extend(_text_blockers(text_audit))
    blockers.extend(_fidelity_blockers(fidelity_report))
    blockers.extend(_asset_blockers(asset_audit))
    blockers.extend(
        item
        for item in quality_report.get("blockers", [])
        if isinstance(item, dict)
    )
    decision = "repair_required" if blockers else "package"
    payload = {
        "schema_version": "5.9",
        "skill_version": skill_version,
        "pptx": str(pptx),
        "pptx_sha256": sha256_file(pptx),
        "build_attempt": attempt,
        "catastrophic_blocker_count": len(blockers),
        "advisory_warning_count": len(quality_report.get("warnings", []))
        + len(text_audit.get("warnings", [])),
        "catastrophic_blockers": blockers,
        "decision": decision,
        "build_locked": not blockers,
    }
    write_json_atomic_checked(
        project / ".build" / "postbuild_release.json",
        payload,
    )
    return payload


def locked_release(
    project_dir: str | Path,
    pptx_path: str | Path,
) -> dict[str, Any] | None:
    project = Path(project_dir).resolve()
    pptx = Path(pptx_path).resolve()
    path = project / ".build" / "postbuild_release.json"
    if not path.is_file() or not pptx.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if (
        payload.get("decision") == "package"
        and payload.get("build_locked") is True
        and payload.get("pptx_sha256") == sha256_file(pptx)
    ):
        return payload
    return None


def rebuild_allowed(
    project_dir: str | Path,
    *,
    catastrophic_repair: bool = False,
    user_revision: bool = False,
) -> bool:
    if user_revision:
        return True
    project = Path(project_dir).resolve()
    path = project / ".build" / "postbuild_release.json"
    if not path.is_file():
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if payload.get("build_locked") is True:
        return False
    return (
        catastrophic_repair
        and payload.get("decision") == "repair_required"
        and int(payload.get("build_attempt", MAX_BUILD_ATTEMPTS))
        < MAX_BUILD_ATTEMPTS
    )
