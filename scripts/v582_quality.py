from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageStat, UnidentifiedImageError


SKILL_VERSION = "5.8.2"
TRANSIENT_IMAGEGEN_ERRORS = {
    "api_error",
    "connection",
    "http_5xx",
    "network",
    "rate_limit",
    "server_error",
    "service_unavailable",
    "timeout",
    "transport",
}
NATIVE_VISUAL_FALLBACKS = {
    "arrow",
    "chart",
    "decorative_motif",
    "line",
    "oval",
    "pictogram",
    "primitive",
    "rect",
    "table",
    "text",
}


def issue(
    code: str,
    severity: str,
    stage: str,
    message: str,
    slide_id: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if severity not in {"warning", "blocker"}:
        raise ValueError("severity must be warning or blocker")
    record: dict[str, Any] = {
        "code": str(code),
        "severity": severity,
        "stage": str(stage),
        "slide_id": str(slide_id) if slide_id is not None else None,
        "message": str(message),
        "metrics": dict(metrics or {}),
    }
    return record


def _normalize_issues(records: Iterable[dict[str, Any]], severity: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item["severity"] = severity
        normalized.append(item)
    return normalized


def summarize(
    warnings: Iterable[dict[str, Any]],
    blockers: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    warning_items = _normalize_issues(warnings, "warning")
    blocker_items = _normalize_issues(blockers, "blocker")
    status = "blocked" if blocker_items else "pass_with_warnings" if warning_items else "pass"
    return {
        "schema_version": "5.8",
        "skill_version": SKILL_VERSION,
        "status": status,
        "warning_count": len(warning_items),
        "blocker_count": len(blocker_items),
        "warnings": warning_items,
        "blockers": blocker_items,
        "issues": warning_items + blocker_items,
    }


def merge(*reports: dict[str, Any] | None) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for report in reports:
        if not isinstance(report, dict):
            continue
        for severity, destination in (("warnings", warnings), ("blockers", blockers)):
            for record in report.get(severity, []):
                if not isinstance(record, dict):
                    continue
                normalized = issue(
                    str(record.get("code", "QUALITY_ISSUE")),
                    "warning" if severity == "warnings" else "blocker",
                    str(record.get("stage", "quality")),
                    str(record.get("message", "quality issue")),
                    record.get("slide_id"),
                    record.get("metrics") if isinstance(record.get("metrics"), dict) else {},
                )
                identity = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
                if identity not in seen:
                    seen.add(identity)
                    destination.append(normalized)
    return summarize(warnings, blockers)


def write_report(project_dir: str | Path, *reports: dict[str, Any] | None) -> dict[str, Any]:
    payload = merge(*reports)
    brief_path = Path(project_dir) / "project_brief.json"
    if brief_path.is_file():
        try:
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            brief = {}
        revision = str(brief.get("pipeline_revision", ""))
        if brief.get("schema_version") == "5.9" and revision in {
        "5.9.0",
        "5.9.1",
        "5.9.2",
        "5.9.4",
        "5.9.5",
        "5.9.6",
        }:
            payload["schema_version"] = "5.9"
            payload["skill_version"] = revision
        elif brief.get("schema_version") == "5.8" and revision in {"5.8.3", "5.8.4"}:
            payload["skill_version"] = revision
    destination = Path(project_dir) / ".build" / "quality_report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return payload


def _effective_foreground_ratio(
    image: Image.Image,
    background: tuple[int, int, int] | None = None,
) -> tuple[float, tuple[int, int, int]]:
    rgb = image.convert("RGB")
    if background is None:
        quantized = rgb.quantize(colors=16).convert("RGB")
        colors = quantized.getcolors(maxcolors=max(1, quantized.width * quantized.height)) or []
        background = max(colors, default=(0, (255, 255, 255)))[1]
    pixels = rgb.width * rgb.height
    getter = getattr(rgb, "get_flattened_data", None)
    pixels_data = getter() if getter is not None else rgb.getdata()
    foreground = sum(
        1
        for pixel in pixels_data
        if max(abs(pixel[index] - background[index]) for index in range(3)) >= 12
    )
    return (foreground / pixels if pixels else 0.0), background


def assess_blueprint(path: str | Path, slide_id: str | None = None) -> dict[str, Any]:
    blueprint = Path(path)
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {"path": str(blueprint)}
    try:
        with Image.open(blueprint) as opened:
            opened.load()
            image = opened.convert("RGB")
    except (FileNotFoundError, IsADirectoryError, OSError, UnidentifiedImageError) as exc:
        blockers.append(
            issue(
                "BLUEPRINT_UNREADABLE",
                "blocker",
                "blueprint",
                f"blueprint artifact is missing or unreadable: {exc}",
                slide_id,
                {"path": str(blueprint)},
            )
        )
        result = summarize(warnings, blockers)
        result.update(metadata)
        return result

    width, height = image.size
    aspect_ratio = width / height if height else 0.0
    metadata.update({"width": width, "height": height, "aspect_ratio": aspect_ratio})
    if width < 640 or height < 360:
        warnings.append(
            issue(
                "BLUEPRINT_RESOLUTION",
                "warning",
                "blueprint",
                f"blueprint is too small for reconstruction: {width}x{height}",
                slide_id,
                {"width": width, "height": height},
            )
        )
    if not 1.50 <= aspect_ratio <= 2.05:
        blockers.append(
            issue(
                "BLUEPRINT_ASPECT_RATIO",
                "blocker",
                "blueprint",
                f"blueprint must be a usable widescreen page; got aspect ratio {aspect_ratio:.3f}",
                slide_id,
                {"aspect_ratio": aspect_ratio, "minimum": 1.50, "maximum": 2.05},
            )
        )

    sample = image.copy()
    sample.thumbnail((320, 180))
    content_ratio, background = _effective_foreground_ratio(sample)
    luminance_stddev = float(ImageStat.Stat(sample.convert("L")).stddev[0])
    body = sample.crop(
        (
            round(sample.width * 0.025),
            round(sample.height * 0.27),
            round(sample.width * 0.975),
            round(sample.height * 0.90),
        )
    )
    body_content_ratio, _ = _effective_foreground_ratio(body, background)
    metadata.update(
        {
            "content_ratio": content_ratio,
            "body_content_ratio": body_content_ratio,
            "luminance_stddev": luminance_stddev,
        }
    )
    if content_ratio < 0.005 or body_content_ratio < 0.0025:
        blockers.append(
            issue(
                "BLUEPRINT_BLANK",
                "blocker",
                "blueprint",
                "blueprint has insufficient visible structure for deterministic reconstruction",
                slide_id,
                {
                    "content_ratio": content_ratio,
                    "minimum_content_ratio": 0.005,
                    "body_content_ratio": body_content_ratio,
                    "minimum_body_content_ratio": 0.0025,
                },
            )
        )

    result = summarize(warnings, blockers)
    result.update(metadata)
    return result


def should_retry_imagegen(
    attempt_count: int,
    *,
    artifact_exists: bool,
    error_kind: str,
) -> bool:
    return (
        attempt_count == 1
        and not artifact_exists
        and str(error_kind).strip().lower() in TRANSIENT_IMAGEGEN_ERRORS
    )


def visual_fallback(kind: str, *, crop_succeeded: bool) -> str:
    if crop_succeeded:
        return "crop"
    return "native_rebuild" if str(kind) in NATIVE_VISUAL_FALLBACKS else "omitted"
