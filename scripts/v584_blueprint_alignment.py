from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image


SCHEMA_VERSION = "5.8"
SKILL_VERSION = "5.8.4"
ALIGNMENT_FILENAME = "blueprint_alignment.json"
ALLOWED_RESOLUTIONS = {"blueprint", "fact_guard", "uncertain_fallback"}
ALLOWED_TREATMENTS = {"crop", "native", "omit"}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _ensure_composition_record(draft: Path) -> None:
    """Record crop coordinates for the immutable draft without repainting it."""

    with Image.open(draft) as image:
        width, height = image.size
    record = {
        "schema_version": SCHEMA_VERSION,
        "complete_slide_reference": True,
        "metadata_only": True,
        "output": str(draft),
        "body_roi": [0, 0, width, height],
        "output_sha256": _sha256_file(draft),
    }
    _write_json_atomic(draft.with_suffix(".composition.json"), record)


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def critical_alignment_texts(
    slide_text: dict[str, Any],
    resolved_page_spec: dict[str, Any],
) -> list[str]:
    values: list[str] = []
    for field in ("chapter", "title"):
        value = slide_text.get(field)
        if isinstance(value, str):
            values.append(value)
    values.extend(
        item
        for item in slide_text.get("core_points", [])
        if isinstance(item, str)
    )
    for element in resolved_page_spec.get("elements", []):
        if not isinstance(element, dict):
            continue
        if element.get("type") == "section_header":
            values.append(str(element.get("text", "")))
        elif element.get("type") == "text_card":
            values.extend(
                [
                    str(element.get("title", "")),
                    str(element.get("body", "")),
                ]
            )
    return [value for value in values if _normalized(value)]


def _flatten_display_values(value: Any) -> list[str]:
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_flatten_display_values(item))
        return values
    if isinstance(value, dict):
        values = []
        for item in value.values():
            values.extend(_flatten_display_values(item))
        return values
    return []


def _detail_alignment_texts(
    slide_text: dict[str, Any],
    resolved_page_spec: dict[str, Any],
) -> list[str]:
    values: list[str] = []
    source = slide_text.get("source")
    if isinstance(source, str):
        values.append(source)
    display_keys = {
        "annotation",
        "annotations",
        "data_label",
        "data_labels",
        "label",
        "legend",
        "legends",
        "name",
        "row_annotations",
        "text",
        "title",
        "body",
        "value",
        "values",
    }

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in display_keys:
                    values.extend(_flatten_display_values(item))
                elif isinstance(item, (dict, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(resolved_page_spec.get("elements", []))
    critical = {
        _normalized(value)
        for value in critical_alignment_texts(slide_text, resolved_page_spec)
    }
    return [
        value
        for value in values
        if _normalized(value) and _normalized(value) not in critical
    ]


def _issue(code: str, severity: str, message: str, slide_id: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "stage": "blueprint_alignment",
        "slide_id": slide_id,
        "message": message,
        "metrics": {},
    }


def _valid_box(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and value[2] > 0
        and value[3] > 0
    )


def _valid_source_px(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, int) for item in value)
        and value[0] < value[2]
        and value[1] < value[3]
    )


def _alignment_required(brief: dict[str, Any]) -> bool:
    return (
        (
            (brief.get("schema_version") == "5.8" and brief.get("pipeline_revision") == "5.8.4")
            or (
                brief.get("schema_version") == "5.9"
                and brief.get("pipeline_revision")
            in {"5.9.0", "5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}
            )
        )
        and brief.get("production_mode") == "blueprint"
    )


def _project_versions(brief: dict[str, Any]) -> tuple[str, str]:
    if brief.get("schema_version") == "5.9":
        return ("5.9", str(brief.get("pipeline_revision", "5.9.0")))
    return (SCHEMA_VERSION, SKILL_VERSION)


def _load_payload(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"BLUEPRINT_ALIGNMENT_REQUIRED: unreadable alignment: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("BLUEPRINT_ALIGNMENT_REQUIRED: alignment must be a JSON object")
    return payload


def diagnose_alignment(
    project: Path,
    brief: dict[str, Any],
    bundle: dict[str, Any],
    manifest: dict[str, Any],
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    schema_version, skill_version = _project_versions(brief)
    required = _alignment_required(brief)
    if payload is None:
        if required:
            blockers.append(
                _issue(
                    "BLUEPRINT_ALIGNMENT_REQUIRED",
                    "blocker",
                    "V5.8.4 blueprint projects require one reviewed post-blueprint alignment",
                )
            )
        return {
            "schema_version": schema_version,
            "skill_version": skill_version,
            "status": "blocked" if blockers else "pass",
            "warnings": warnings,
            "blockers": blockers,
            "warning_count": len(warnings),
            "blocker_count": len(blockers),
        }
    if payload.get("schema_version") != schema_version:
        blockers.append(
            _issue(
                "BLUEPRINT_ALIGNMENT_REQUIRED",
                "blocker",
                f"blueprint alignment schema_version must be {schema_version}",
            )
        )
    pages = payload.get("pages")
    if not isinstance(pages, dict):
        blockers.append(
            _issue(
                "BLUEPRINT_ALIGNMENT_REQUIRED",
                "blocker",
                "blueprint alignment pages must be a mapping",
            )
        )
        pages = {}
    slides = bundle.get("slides", [])
    expected_ids = [
        str(item.get("slide_id"))
        for item in slides
        if isinstance(item, dict) and isinstance(item.get("slide_id"), str)
    ]
    bundle_slides = {
        str(item.get("slide_id")): item
        for item in slides
        if isinstance(item, dict) and isinstance(item.get("slide_id"), str)
    }
    if sorted(pages) != sorted(expected_ids):
        blockers.append(
            _issue(
                "BLUEPRINT_ALIGNMENT_REQUIRED",
                "blocker",
                f"blueprint alignment must cover {expected_ids}",
            )
        )
    bundle_hash = _sha256_file(project / ".build" / "authoring_bundle.json")
    manifest_pages = manifest.get("pages", {}) if isinstance(manifest, dict) else {}
    for slide_id in expected_ids:
        page = pages.get(slide_id)
        if not isinstance(page, dict):
            continue
        if page.get("reviewed") is not True:
            blockers.append(
                _issue(
                    "BLUEPRINT_ALIGNMENT_REQUIRED",
                    "blocker",
                    "alignment page must be internally reviewed before compilation",
                    slide_id,
                )
            )
        if page.get("authoring_bundle_sha256") != bundle_hash:
            blockers.append(
                _issue(
                    "BLUEPRINT_ALIGNMENT_STALE",
                    "blocker",
                    "alignment authoring-bundle hash is stale",
                    slide_id,
                )
            )
        manifest_page = manifest_pages.get(slide_id, {}) if isinstance(manifest_pages, dict) else {}
        draft_relative = manifest_page.get(
            "design_draft_path",
            f".build/design_drafts/{slide_id}.png",
        )
        draft = (project / str(draft_relative)).resolve()
        if not draft.is_file():
            blockers.append(
                _issue(
                    "BLUEPRINT_ALIGNMENT_STALE",
                    "blocker",
                    "locked design draft is missing",
                    slide_id,
                )
            )
        elif page.get("design_draft_sha256") != _sha256_file(draft):
            blockers.append(
                _issue(
                    "BLUEPRINT_ALIGNMENT_STALE",
                    "blocker",
                    "alignment design-draft hash is stale",
                    slide_id,
                )
            )
        else:
            _ensure_composition_record(draft)
        slide_text = page.get("slide_text")
        if not isinstance(slide_text, dict):
            blockers.append(
                _issue(
                    "BLUEPRINT_ALIGNMENT_REQUIRED",
                    "blocker",
                    "alignment slide_text must be a mapping",
                    slide_id,
                )
            )
        review_text = {
            field: deepcopy(bundle_slides.get(slide_id, {}).get(field))
            for field in ("chapter", "title", "core_points", "source")
        }
        if isinstance(slide_text, dict):
            for field in ("chapter", "title", "core_points", "source"):
                if field in slide_text:
                    review_text[field] = deepcopy(slide_text[field])
        resolved = page.get("resolved_page_spec")
        if not isinstance(resolved, dict) or not isinstance(resolved.get("elements"), list):
            blockers.append(
                _issue(
                    "BLUEPRINT_ALIGNMENT_REQUIRED",
                    "blocker",
                    "alignment resolved_page_spec.elements must be a list",
                    slide_id,
                )
            )
        else:
            for index, element in enumerate(resolved["elements"]):
                if not isinstance(element, dict) or not isinstance(element.get("type"), str):
                    blockers.append(
                        _issue(
                            "BLUEPRINT_ALIGNMENT_REQUIRED",
                            "blocker",
                            f"resolved element[{index}] must define a type",
                            slide_id,
                        )
                    )
                elif not _valid_box(element.get("box")):
                    blockers.append(
                        _issue(
                            "BLUEPRINT_ALIGNMENT_REQUIRED",
                            "blocker",
                            f"resolved element[{index}] requires a positive box",
                            slide_id,
                        )
                    )
        decisions = page.get("text_decisions", [])
        if not isinstance(decisions, list):
            blockers.append(
                _issue(
                    "BLUEPRINT_ALIGNMENT_REQUIRED",
                    "blocker",
                    "alignment text_decisions must be a list",
                    slide_id,
                )
            )
        else:
            for decision in decisions:
                resolution = decision.get("resolution") if isinstance(decision, dict) else None
                if resolution not in ALLOWED_RESOLUTIONS:
                    warnings.append(
                        _issue(
                            "BLUEPRINT_TEXT_UNRESOLVED",
                            "warning",
                            "invalid text resolution falls back to canonical runtime text",
                            slide_id,
                        )
                    )
                elif resolution != "blueprint":
                    warnings.append(
                        _issue(
                            "BLUEPRINT_TEXT_FACT_GUARD"
                            if resolution == "fact_guard"
                            else "BLUEPRINT_TEXT_UNCERTAIN",
                            "warning",
                            "PPT text intentionally differs from the original blueprint",
                            slide_id,
                        )
                    )
            if (
                brief.get("schema_version") == "5.9"
        and brief.get("pipeline_revision") in {"5.9.2", "5.9.4", "5.9.5", "5.9.6"}
                and isinstance(resolved, dict)
            ):
                reviewed = {
                    _normalized(decision.get("selected"))
                    for decision in decisions
                    if isinstance(decision, dict)
                    and decision.get("resolution") in ALLOWED_RESOLUTIONS
                    and _normalized(decision.get("selected"))
                }
                missing_critical = [
                    value
                    for value in critical_alignment_texts(review_text, resolved)
                    if _normalized(value) not in reviewed
                ]
                if missing_critical:
                    blockers.append(
                        _issue(
                            "BLUEPRINT_CRITICAL_TEXT_UNREVIEWED",
                            "blocker",
                            "high-salience blueprint text has no reviewed decision",
                            slide_id,
                        )
                    )
                missing_detail = [
                    value
                    for value in _detail_alignment_texts(review_text, resolved)
                    if _normalized(value) not in reviewed
                ]
                if missing_detail:
                    warnings.append(
                        _issue(
                            "BLUEPRINT_DETAIL_TEXT_UNREVIEWED",
                            "warning",
                            "detail blueprint text lacks a reviewed decision",
                            slide_id,
                        )
                    )
        visuals = page.get("visuals", [])
        if not isinstance(visuals, list):
            blockers.append(
                _issue(
                    "BLUEPRINT_ALIGNMENT_REQUIRED",
                    "blocker",
                    "alignment visuals must be a list",
                    slide_id,
                )
            )
            visuals = []
        for visual in visuals:
            treatment = visual.get("treatment") if isinstance(visual, dict) else None
            if treatment not in ALLOWED_TREATMENTS:
                warnings.append(
                    _issue(
                        "ALIGNMENT_VISUAL_UNRESOLVED",
                        "warning",
                        "visual treatment must be crop, native, or omit; unresolved visual will be omitted",
                        slide_id,
                    )
                )
            elif treatment == "crop" and (
                not _valid_source_px(visual.get("source_px"))
                or not _valid_box(visual.get("target_box_in"))
            ):
                warnings.append(
                    _issue(
                        "ALIGNMENT_CROP_INVALID",
                        "warning",
                        "crop visual has unusable coordinates and will use its fallback",
                        slide_id,
                    )
                )
            elif treatment == "omit":
                warnings.append(
                    _issue(
                        "ALIGNMENT_VISUAL_OMITTED",
                        "warning",
                        "reviewed low-value visual was intentionally omitted",
                        slide_id,
                    )
                )
        visual_plan = manifest_page.get("visual_plan", []) if isinstance(manifest_page, dict) else []
        if visual_plan and not visuals:
            warnings.append(
                _issue(
                    "ALIGNMENT_VISUAL_EMPTY",
                    "warning",
                    "planned visuals exist but the reviewed blueprint recorded no visual subjects",
                    slide_id,
                )
            )
    status = "blocked" if blockers else ("pass_with_warnings" if warnings else "pass")
    return {
        "schema_version": schema_version,
        "skill_version": skill_version,
        "status": status,
        "warnings": warnings,
        "blockers": blockers,
        "warning_count": len(warnings),
        "blocker_count": len(blockers),
    }


def _merge_page(
    slide: dict[str, Any],
    page_spec: dict[str, Any],
    manifest_page: dict[str, Any],
    alignment_page: dict[str, Any],
    *,
    skill_version: str = SKILL_VERSION,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    aligned_slide = deepcopy(slide)
    aligned_spec = deepcopy(page_spec)
    aligned_manifest = deepcopy(manifest_page)
    slide_text = alignment_page.get("slide_text", {})
    for field in ("chapter", "title", "core_points", "source"):
        value = slide_text.get(field)
        if field == "core_points":
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                aligned_slide[field] = deepcopy(value)
        elif isinstance(value, str):
            aligned_slide[field] = value
    resolved = alignment_page.get("resolved_page_spec", {})
    aligned_spec = deepcopy(resolved)
    raw_visuals = alignment_page.get("visuals", [])
    normalized_visuals: list[dict[str, Any]] = []
    crop_visuals: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_visuals):
        if not isinstance(raw, dict):
            continue
        visual = deepcopy(raw)
        treatment = str(visual.get("treatment", "omit"))
        if treatment not in ALLOWED_TREATMENTS:
            treatment = "omit"
        visual["treatment"] = treatment
        visual["disposition"] = "native_rebuild" if treatment == "native" else treatment
        visual.setdefault("visual_id", visual.get("asset_id", f"V{index + 1:02d}"))
        visual.setdefault("kind", "pictogram")
        visual.setdefault("description", "")
        if treatment == "crop" and _valid_source_px(visual.get("source_px")) and _valid_box(
            visual.get("target_box_in")
        ):
            crop_visuals.append(visual)
        normalized_visuals.append(visual)
    aligned_manifest.update(
        {
            "visual_reviewed": True,
            "visual_census_result": alignment_page.get("visual_census_result"),
            "observed_candidate_count": alignment_page.get(
                "observed_candidate_count",
                len(normalized_visuals),
            ),
            "candidate_count": alignment_page.get(
                "candidate_count",
                len(normalized_visuals),
            ),
            "visuals": normalized_visuals,
            "alignment_review_method": alignment_page.get("review_method", "visual_agent"),
            "alignment_authoring_bundle_sha256": alignment_page.get("authoring_bundle_sha256"),
        }
    )
    if skill_version in {"5.9.5", "5.9.6"}:
        aligned_manifest["page_graphics_grade"] = alignment_page.get(
            "page_graphics_grade"
        )
        aligned_manifest["zero_subject_challenge"] = deepcopy(
            alignment_page.get("zero_subject_challenge")
        )
        aligned_manifest["design_draft_sha256"] = alignment_page.get(
            "design_draft_sha256",
            aligned_manifest.get("design_draft_sha256"),
        )
        if skill_version == "5.9.6":
            aligned_manifest["visual_review_tiles"] = deepcopy(
                alignment_page.get("visual_review_tiles")
            )
        aligned_slide["visual_review"] = str(
            alignment_page.get(
                "visual_review",
                "reviewed_inventory"
                if normalized_visuals
                else "reviewed_no_raster",
            )
        )
    else:
        aligned_slide["visual_review"] = "extract_declared" if crop_visuals else "reviewed_no_raster"
    aligned_slide["visual_review_evidence"] = {
        "blueprint_sha256": aligned_manifest.get("design_draft_sha256"),
        "full_page_reviewed": True,
        "checked_classes": ["photo", "logo", "map", "pictogram", "decorative_motif"],
        "decision_reason": "V5.8.4 post-blueprint alignment reviewed every observed subject.",
    }
    aligned_slide["visual_inventory"] = [
        {
            key: visual[key]
            for key in (
                "visual_id",
                "kind",
                "description",
                "treatment",
                "disposition",
                "asset_id",
                "rebuild_recipe",
                "element_id",
                "omit_reason",
                "retention_grade",
            )
            if key in visual
        }
        for visual in normalized_visuals
    ]
    aligned_slide["complex_visuals"] = [
        {
            "asset_id": str(visual["asset_id"]),
            "kind": str(visual.get("kind", "pictogram")),
            "description": str(visual.get("description", "")),
        }
        for visual in crop_visuals
        if isinstance(visual.get("asset_id"), str) and visual.get("asset_id")
    ]
    return aligned_slide, aligned_spec, aligned_manifest


def _make_alignment_benchmark(
    slides: list[dict[str, Any]],
    page_specs: dict[str, Any],
    manifest: dict[str, Any],
    alignment: dict[str, Any],
    *,
    schema_version: str,
    skill_version: str,
) -> dict[str, Any]:
    benchmark_module = _load_module(
        "standard_report_v584_text_benchmark",
        Path(__file__).with_name("v58_text_benchmark.py"),
    )
    draft_hashes = {
        slide_id: str(page.get("design_draft_sha256", ""))
        for slide_id, page in manifest.get("pages", {}).items()
        if isinstance(page, dict)
    }
    benchmark = benchmark_module.make_benchmark(
        slides,
        page_specs,
        draft_hashes,
        schema_version=schema_version,
    )
    alignment_pages = alignment.get("pages", {})
    for slide in slides:
        slide_id = str(slide["slide_id"])
        benchmark_page = benchmark["pages"][slide_id]
        alignment_page = alignment_pages.get(slide_id, {})
        decisions = [
            deepcopy(item)
            for item in alignment_page.get("text_decisions", [])
            if isinstance(item, dict)
        ]
        by_selected = {
            _normalized(item.get("selected")): item
            for item in decisions
            if _normalized(item.get("selected"))
        }
        enriched: list[dict[str, Any]] = []
        for item in benchmark_page.get("items", []):
            expected = str(item.get("expected", ""))
            decision = by_selected.get(_normalized(expected))
            if decision is None:
                enriched.append(
                    {
                        "expected": expected,
                        "canonical": expected,
                        "observed": "",
                        "selected": expected,
                        "resolution": "uncertain_fallback",
                        "match": False,
                        "match_blueprint": False,
                    }
                )
                continue
            observed = str(decision.get("observed", ""))
            selected = str(decision.get("selected", expected))
            resolution = str(decision.get("resolution", "uncertain_fallback"))
            enriched.append(
                {
                    "role": decision.get("role", ""),
                    "expected": selected,
                    "canonical": str(decision.get("canonical", expected)),
                    "observed": observed,
                    "selected": selected,
                    "resolution": resolution,
                    "match": _normalized(observed) == _normalized(selected),
                    "match_blueprint": _normalized(observed) == _normalized(selected),
                }
            )
        benchmark_page["reviewed"] = True
        benchmark_page["review_method"] = alignment_page.get("review_method", "visual_agent")
        benchmark_page["items"] = enriched
        differences = [
            {
                "role": item.get("role", ""),
                "observed": item.get("observed", ""),
                "selected": item.get("selected", ""),
                "resolution": item.get("resolution", ""),
            }
            for item in enriched
            if item.get("match_blueprint") is not True
        ]
        benchmark_page["differences"] = differences
        benchmark_page["exact_match"] = not differences
    benchmark["ok"] = True
    benchmark["skill_version"] = skill_version
    return benchmark


def apply_project_alignment(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    build = project / ".build"
    brief = json.loads((project / "project_brief.json").read_text(encoding="utf-8"))
    schema_version, skill_version = _project_versions(brief)
    bundle_path = build / "authoring_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    alignment_path = build / ALIGNMENT_FILENAME
    payload = _load_payload(alignment_path)
    result_path = build / "blueprint_alignment_result.json"
    runtime_paths = {
        "slides": build / "slides.json",
        "page_specs": build / "page_specs.json",
        "visual_manifest": build / "visual_manifest.json",
        "benchmark": build / "blueprint_text_benchmark.json",
    }
    if payload is not None and result_path.is_file() and all(path.is_file() for path in runtime_paths.values()):
        try:
            previous = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            previous = {}
        expected_runtime_hashes = previous.get("runtime_sha256", {})
        runtime_current = (
            isinstance(expected_runtime_hashes, dict)
            and all(
                expected_runtime_hashes.get(name) == _sha256_file(path)
                for name, path in runtime_paths.items()
            )
        )
        drafts_current = all(
            isinstance(page, dict)
            and isinstance(page.get("design_draft_sha256"), str)
            and (build / "design_drafts" / f"{slide_id}.png").is_file()
            and page["design_draft_sha256"]
            == _sha256_file(build / "design_drafts" / f"{slide_id}.png")
            for slide_id, page in payload.get("pages", {}).items()
        )
        if (
            previous.get("authoring_bundle_sha256") == _sha256_file(bundle_path)
            and previous.get("alignment_sha256") == _sha256_file(alignment_path)
            and runtime_current
            and drafts_current
        ):
            cached = dict(previous)
            cached["cache_hit"] = True
            return cached
    authoring = _load_module(
        "standard_report_v584_base_authoring",
        Path(__file__).with_name("v583_authoring.py"),
    )
    authoring.materialize_project(project)
    base_slides = json.loads((build / "slides.json").read_text(encoding="utf-8"))
    base_page_specs = json.loads((build / "page_specs.json").read_text(encoding="utf-8"))
    base_manifest = json.loads((build / "visual_manifest.json").read_text(encoding="utf-8"))
    report = diagnose_alignment(project, brief, bundle, base_manifest, payload)
    _write_json_atomic(build / "blueprint_alignment_report.json", report)
    if report["blockers"]:
        messages = "; ".join(
            f"{item['code']}: {item['message']}" for item in report["blockers"]
        )
        raise ValueError(messages)
    if payload is None:
        return {
            "schema_version": schema_version,
            "skill_version": skill_version,
            "ok": True,
            "status": report["status"],
            "aligned_pages": 0,
        }
    _write_json_atomic(build / "canonical_slides.json", base_slides)
    _write_json_atomic(build / "planned_page_specs.json", base_page_specs)
    by_slide = {str(slide["slide_id"]): slide for slide in base_slides}
    aligned_slides: list[dict[str, Any]] = []
    aligned_specs: dict[str, Any] = {}
    aligned_manifest = deepcopy(base_manifest)
    for slide_id in [str(slide["slide_id"]) for slide in base_slides]:
        slide, spec, page = _merge_page(
            by_slide[slide_id],
            base_page_specs[slide_id],
            base_manifest["pages"][slide_id],
            payload["pages"][slide_id],
            skill_version=skill_version,
        )
        if skill_version in {"5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}:
            if skill_version not in {"5.9.5", "5.9.6"}:
                slide["visual_review"] = "reviewed_inventory"
            slide["visual_review_evidence"]["decision_reason"] = (
                f"V{skill_version} reviewed the complete independent visual-subject census."
            )
        aligned_slides.append(slide)
        aligned_specs[slide_id] = spec
        aligned_manifest["pages"][slide_id] = page
    benchmark = _make_alignment_benchmark(
        aligned_slides,
        aligned_specs,
        aligned_manifest,
        payload,
        schema_version=schema_version,
        skill_version=skill_version,
    )
    _write_json_atomic(build / "slides.json", aligned_slides)
    _write_json_atomic(build / "page_specs.json", aligned_specs)
    _write_json_atomic(build / "visual_manifest.json", aligned_manifest)
    _write_json_atomic(build / "blueprint_text_benchmark.json", benchmark)
    result = {
        "schema_version": schema_version,
        "skill_version": skill_version,
        "ok": True,
        "status": report["status"],
        "aligned_pages": len(aligned_slides),
        "warning_count": report["warning_count"],
        "blocker_count": 0,
        "authoring_bundle_sha256": _sha256_file(bundle_path),
        "alignment_sha256": _sha256_file(alignment_path),
        "runtime_sha256": {
            "slides": _sha256_file(build / "slides.json"),
            "page_specs": _sha256_file(build / "page_specs.json"),
            "visual_manifest": _sha256_file(build / "visual_manifest.json"),
            "benchmark": _sha256_file(build / "blueprint_text_benchmark.json"),
        },
        "cache_hit": False,
    }
    _write_json_atomic(build / "blueprint_alignment_result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply V5.8.4 post-blueprint alignment.")
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(json.dumps(apply_project_alignment(args.project), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
