from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "5.8"
SUPPORTED_SCHEMA_VERSIONS = {"5.6", "5.7", "5.8", "5.9"}
MODERN_SCHEMA_VERSIONS = {"5.8", "5.9"}
MANDATORY_CROP_KINDS = {
    "photo",
    "logo",
    "map",
    "pictogram",
    "compound_mark",
    "decorative_motif",
    "chemical_structure",
    "device",
    "product",
    "character",
}
NATIVE_KINDS = {"text", "rect", "line", "arrow", "oval", "chart", "table", "primitive"}
ALLOWED_REBUILD_RECIPES = {
    "text",
    "rect",
    "line",
    "arrow",
    "oval",
    "bar_chart",
    "column_chart",
    "line_chart",
    "combo_chart",
    "donut_chart",
    "grouped_hbar_chart",
    "table",
    "circle_plus_text",
    "bars_plus_arrow",
    "line_arrow",
    "basic_shape",
    "editable_chart",
    "editable_table",
    "editable_text",
}


def _load_quality():
    path = Path(__file__).with_name("v582_quality.py")
    spec = importlib.util.spec_from_file_location("standard_report_v582_visual_quality", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load V5.8.2 quality policy from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scan_text_integrity(text: str, *, location: str = "text") -> list[str]:
    errors: list[str] = []
    for match in re.finditer(r"\?{3,}", text):
        errors.append(f"{location}: question_mark_run at {match.start()} length={len(match.group(0))}")
    if "\ufffd" in text:
        errors.append(f"{location}: unicode_replacement_character")
    if re.search(r"[\x80-\x9f]", text):
        errors.append(f"{location}: c1_control_character")
    for token in ("锟斤拷", "ï¿½", "Ã¤", "Â·"):
        if token in text:
            errors.append(f"{location}: mojibake_token {token!r}")
    return errors


def iter_visible_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from iter_visible_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_visible_strings(item)


def validate_structured_text(value: Any, *, location: str) -> list[str]:
    errors: list[str] = []
    for index, text in enumerate(iter_visible_strings(value)):
        errors.extend(scan_text_integrity(text, location=f"{location}[{index}]"))
    return errors


def _valid_source_rect(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, int) for item in value)
        and value[0] < value[2]
        and value[1] < value[3]
    )


def _valid_target_box(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and value[2] > 0
        and value[3] > 0
    )


def diagnose_visual_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    quality = _load_quality()
    if not isinstance(manifest, dict):
        blocker = quality.issue(
            "VISUAL_MANIFEST_STRUCTURE",
            "blocker",
            "blueprint",
            "visual manifest must be a mapping",
        )
        return quality.summarize([], [blocker])
    if manifest.get("schema_version") not in MODERN_SCHEMA_VERSIONS:
        blockers = [
            quality.issue("VISUAL_MANIFEST_LEGACY", "blocker", "blueprint", message)
            for message in _validate_visual_manifest_legacy(manifest)
        ]
        return quality.summarize([], blockers)

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def add_blocker(code: str, message: str, slide_id: str | None = None) -> None:
        blockers.append(quality.issue(code, "blocker", "blueprint", message, slide_id))

    def add_warning(code: str, message: str, slide_id: str | None = None) -> None:
        warnings.append(quality.issue(code, "warning", "blueprint", message, slide_id))

    pages = manifest.get("pages")
    if not isinstance(pages, dict) or not pages:
        add_blocker("VISUAL_MANIFEST_PAGES", "visual manifest pages must be a non-empty mapping")
        return quality.summarize(warnings, blockers)

    asset_ids: set[str] = set()
    for slide_id, page in pages.items():
        prefix = str(slide_id)
        if not isinstance(page, dict):
            add_blocker("VISUAL_PAGE_STRUCTURE", "visual page record must be a mapping", prefix)
            continue

        draft_path = page.get("design_draft_path")
        draft_hash = page.get("design_draft_sha256")
        if not isinstance(draft_path, str) or not draft_path:
            add_blocker("DESIGN_DRAFT_PATH", "design_draft_path must be a non-empty string", prefix)
        if not isinstance(draft_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", draft_hash):
            add_blocker(
                "DESIGN_DRAFT_HASH",
                "design_draft_sha256 must be 64 lowercase hex characters",
                prefix,
            )
        if page.get("imagegen_attempt_count") != 1:
            add_warning(
                "IMAGEGEN_ATTEMPT_COUNT",
                "ImageGen artifact count differs from the preferred single generation",
                prefix,
            )
        transport_attempts = page.get("transport_attempt_count")
        if isinstance(transport_attempts, int) and transport_attempts > 2:
            add_warning(
                "IMAGEGEN_TRANSPORT_ATTEMPTS",
                f"ImageGen transport used {transport_attempts} attempts",
                prefix,
            )

        visual_plan = page.get("visual_plan", [])
        if not isinstance(visual_plan, list):
            add_warning("VISUAL_PLAN_STRUCTURE", "visual_plan should be a list; treating it as empty", prefix)
            visual_plan = []
        elif len(visual_plan) > 5:
            add_warning(
                "VISUAL_COUNT_HIGH",
                f"visual_plan contains {len(visual_plan)} decorative/supporting visuals",
                prefix,
            )
        if page.get("visual_reviewed") is not True:
            add_warning("VISUAL_REVIEW_PENDING", "full ImageGen page has not been marked reviewed", prefix)

        visuals = page.get("visuals", [])
        if not isinstance(visuals, list):
            add_warning("VISUALS_STRUCTURE", "visuals should be a list; treating it as empty", prefix)
            visuals = []

        observed = page.get("observed_candidate_count", len(visuals))
        if not isinstance(observed, int) or isinstance(observed, bool) or observed < 0:
            add_warning(
                "OBSERVED_COUNT_STRUCTURE",
                "observed_candidate_count should be a non-negative integer; inferred from visuals",
                prefix,
            )
            observed = len(visuals)
        elif observed > 5:
            add_warning(
                "VISUAL_COUNT_HIGH",
                f"observed ImageGen result contains {observed} decorative/supporting visuals",
                prefix,
            )

        candidates = page.get("candidate_count", len(visuals))
        if not isinstance(candidates, int) or isinstance(candidates, bool) or candidates < 0:
            add_warning(
                "CANDIDATE_COUNT_STRUCTURE",
                "candidate_count should be a non-negative integer; inferred from visuals",
                prefix,
            )
            candidates = len(visuals)
        if len(visuals) > 5:
            add_warning(
                "VISUAL_COUNT_HIGH",
                f"reviewed visuals list contains {len(visuals)} decorative/supporting visuals",
                prefix,
            )
        if candidates != observed:
            add_warning(
                "VISUAL_COUNT_MISMATCH",
                "candidate_count differs from observed_candidate_count",
                prefix,
            )
        if candidates != len(visuals):
            add_warning(
                "VISUAL_COUNT_MISMATCH",
                "candidate_count differs from the reviewed visuals list",
                prefix,
            )
        if visual_plan and observed == 0:
            add_warning(
                "VISUAL_PLAN_UNOBSERVED",
                "planned visuals were not observed in the ImageGen page",
                prefix,
            )

        planned_ids = {
            item.get("visual_id")
            for item in visual_plan
            if isinstance(item, dict) and isinstance(item.get("visual_id"), str) and item.get("visual_id")
        }
        observed_ids = {
            item.get("visual_id")
            for item in visuals
            if isinstance(item, dict) and isinstance(item.get("visual_id"), str) and item.get("visual_id")
        }
        missing_planned = sorted(planned_ids - observed_ids)
        if missing_planned:
            add_warning(
                "VISUAL_PLAN_MISMATCH",
                f"planned visual IDs missing from reviewed output: {missing_planned}",
                prefix,
            )

        crop_count = 0
        for index, visual in enumerate(visuals):
            label = f"visual[{index}]"
            if not isinstance(visual, dict):
                add_warning("VISUAL_ITEM_STRUCTURE", f"{label} is not a mapping and will be omitted", prefix)
                continue
            kind = visual.get("kind")
            disposition = visual.get("disposition")
            if disposition == "crop":
                crop_count += 1
                asset_id = visual.get("asset_id")
                if not isinstance(asset_id, str) or not asset_id:
                    add_warning("VISUAL_ASSET_ID", f"{label} crop has no asset_id and will be omitted", prefix)
                elif asset_id in asset_ids:
                    add_warning("VISUAL_ASSET_ID", f"{label} duplicate asset_id {asset_id}; duplicate will be omitted", prefix)
                else:
                    asset_ids.add(asset_id)
                if not _valid_source_rect(visual.get("source_px")):
                    add_warning("VISUAL_SOURCE_RECT", f"{label} crop has an invalid source_px and will fall back", prefix)
                if not _valid_target_box(visual.get("target_box_in")):
                    add_warning("VISUAL_TARGET_BOX", f"{label} crop has an invalid target_box_in and will fall back", prefix)
            elif disposition == "native_rebuild":
                add_warning(
                    "VISUAL_NATIVE_FALLBACK",
                    f"{label} {kind!r} uses a nonblocking native reconstruction fallback",
                    prefix,
                )
                if kind not in NATIVE_KINDS and kind not in MANDATORY_CROP_KINDS:
                    add_warning("VISUAL_NATIVE_KIND", f"{label} has unsupported native kind {kind!r}", prefix)
                if visual.get("rebuild_recipe") not in ALLOWED_REBUILD_RECIPES:
                    add_warning(
                        "VISUAL_NATIVE_RECIPE",
                        f"{label} native_rebuild has no recognized rebuild_recipe",
                        prefix,
                    )
            elif disposition == "omitted":
                add_warning(
                    "VISUAL_OMITTED_FALLBACK",
                    f"{label} {kind!r} was omitted after crop fallback",
                    prefix,
                )
            else:
                add_warning(
                    "VISUAL_DISPOSITION",
                    f"{label} disposition is unknown and will be omitted",
                    prefix,
                )

        if candidates > 0 and crop_count == 0:
            add_warning(
                "VISUAL_ZERO_CROPS",
                f"candidate_count={candidates} produced no usable crops",
                prefix,
            )
        if candidates < crop_count:
            add_warning(
                "VISUAL_COUNT_MISMATCH",
                "candidate_count is smaller than crop count",
                prefix,
            )

    for message in validate_structured_text(manifest, location="visual_manifest"):
        add_warning("VISUAL_TEXT_INTEGRITY", message)
    return quality.summarize(warnings, blockers)


def validate_visual_manifest(manifest: dict[str, Any]) -> list[str]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") == "5.8":
        diagnostics = diagnose_visual_manifest(manifest)
        return [str(item["message"]) for item in diagnostics["blockers"]]
    return _validate_visual_manifest_legacy(manifest)


def _validate_visual_manifest_legacy(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"visual manifest schema_version must be one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    pages = manifest.get("pages")
    if not isinstance(pages, dict) or not pages:
        return errors + ["visual manifest pages must be a non-empty mapping"]
    asset_ids: set[str] = set()
    for slide_id, page in pages.items():
        prefix = str(slide_id)
        if not isinstance(page, dict):
            errors.append(f"{prefix}: visual page record must be a mapping")
            continue
        if manifest.get("schema_version") == "5.8":
            draft_path = page.get("design_draft_path")
            draft_hash = page.get("design_draft_sha256")
            attempt_count = page.get("imagegen_attempt_count")
            if not isinstance(draft_path, str) or not draft_path:
                errors.append(f"{prefix}: design_draft_path must be a non-empty string")
            if not isinstance(draft_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", draft_hash):
                errors.append(f"{prefix}: design_draft_sha256 must be 64 lowercase hex characters")
            if attempt_count != 1:
                errors.append(f"{prefix}: ImageGen requires exactly one design draft attempt")
            visual_plan = page.get("visual_plan")
            if not isinstance(visual_plan, list):
                errors.append(f"{prefix}: visual_plan must be a reviewed list created before ImageGen")
                visual_plan = []
            if len(visual_plan) > 5:
                errors.append(f"{prefix}: visual_plan permits at most five decorative/supporting visuals")
            if page.get("visual_reviewed") is not True:
                errors.append(f"{prefix}: visual_reviewed must be true after inspecting the full ImageGen page")
            observed = page.get("observed_candidate_count")
            if not isinstance(observed, int) or observed < 0:
                errors.append(f"{prefix}: observed_candidate_count must be a non-negative integer")
                observed = 0
            if observed > 5:
                errors.append(f"{prefix}: observed ImageGen result permits at most five decorative/supporting visuals")
        else:
            blueprint_hash = page.get("blueprint_sha256")
            if not isinstance(blueprint_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", blueprint_hash):
                errors.append(f"{prefix}: blueprint_sha256 must be 64 lowercase hex characters")
        candidates = page.get("candidate_count")
        if not isinstance(candidates, int) or candidates < 0:
            errors.append(f"{prefix}: candidate_count must be a non-negative integer")
            candidates = 0
        visuals = page.get("visuals")
        if not isinstance(visuals, list):
            errors.append(f"{prefix}: visuals must be a list")
            continue
        if manifest.get("schema_version") == "5.8":
            if candidates != observed:
                errors.append(f"{prefix}: candidate_count must equal observed_candidate_count")
            if candidates != len(visuals):
                errors.append(f"{prefix}: candidate_count must equal the complete reviewed visuals list")
            if visual_plan and observed == 0:
                errors.append(f"{prefix}: a planned visual cannot pass with zero observed candidates")
            planned_ids = {
                item.get("visual_id") for item in visual_plan if isinstance(item, dict) and item.get("visual_id")
            }
            observed_ids = {
                item.get("visual_id") for item in visuals if isinstance(item, dict) and item.get("visual_id")
            }
            missing_planned = sorted(planned_ids - observed_ids)
            if missing_planned:
                errors.append(f"{prefix}: planned visual IDs missing from reviewed crops: {missing_planned}")
        crop_count = 0
        for index, visual in enumerate(visuals):
            label = f"{prefix}/visual[{index}]"
            if not isinstance(visual, dict):
                errors.append(f"{label}: visual must be a mapping")
                continue
            kind = visual.get("kind")
            disposition = visual.get("disposition")
            if kind in MANDATORY_CROP_KINDS and disposition != "crop":
                errors.append(f"{label}: {kind} must use crop")
            if manifest.get("schema_version") == "5.8" and disposition != "crop":
                errors.append(f"{label}: every reviewed ImageGen visual must use a blueprint crop")
            if disposition == "crop":
                crop_count += 1
                asset_id = visual.get("asset_id")
                if not isinstance(asset_id, str) or not asset_id:
                    errors.append(f"{label}: crop requires asset_id")
                elif asset_id in asset_ids:
                    errors.append(f"{label}: duplicate asset_id {asset_id}")
                else:
                    asset_ids.add(asset_id)
                if not _valid_source_rect(visual.get("source_px")):
                    errors.append(f"{label}: crop requires a valid source_px rectangle")
                if not _valid_target_box(visual.get("target_box_in")):
                    errors.append(f"{label}: crop requires a valid target_box_in")
            elif disposition == "native_rebuild":
                if kind not in NATIVE_KINDS:
                    errors.append(f"{label}: unsupported native kind {kind!r}")
                if visual.get("rebuild_recipe") not in ALLOWED_REBUILD_RECIPES:
                    errors.append(f"{label}: native_rebuild requires an allowed rebuild_recipe")
            else:
                errors.append(f"{label}: disposition must be crop or native_rebuild")
        if candidates > 0 and crop_count == 0:
            errors.append(f"{prefix}: candidate_count={candidates} forbids a zero-asset review")
        if candidates < crop_count:
            errors.append(f"{prefix}: candidate_count cannot be smaller than crop count")
    errors.extend(validate_structured_text(manifest, location="visual_manifest"))
    return errors


def visual_page_to_slide_fields(
    page: dict[str, Any],
    *,
    pipeline_revision: str | None = None,
) -> dict[str, Any]:
    raw_visuals = page.get("visuals", [])
    visuals = [visual for visual in raw_visuals if isinstance(visual, dict)] if isinstance(raw_visuals, list) else []
    crops = [
        visual
        for visual in visuals
        if visual.get("disposition") == "crop"
        and isinstance(visual.get("asset_id"), str)
        and visual.get("asset_id")
    ]
    return {
        "visual_review": (
            "reviewed_inventory"
            if pipeline_revision in {"5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}
            else ("extract_declared" if crops else "reviewed_no_raster")
        ),
        "visual_review_evidence": {
            "blueprint_sha256": page.get("design_draft_sha256", page.get("blueprint_sha256")),
            "full_page_reviewed": True,
            "checked_classes": ["photo", "logo", "map", "pictogram", "decorative_motif"],
            "decision_reason": "The manifest gate resolved every visual candidate before compilation.",
        },
        "visual_inventory": [
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
            for visual in visuals
        ],
        "complex_visuals": [
            {"asset_id": visual["asset_id"], "kind": visual.get("kind", "pictogram"), "description": visual.get("description", "")}
            for visual in crops
        ],
    }


def validate_blueprint_visual_balance(
    page_specs: dict[str, Any],
    manifest: dict[str, Any],
    *,
    body_box: tuple[float, float, float, float] = (0.72, 2.90, 12.00, 3.80),
) -> list[str]:
    """Enforce the V5.7 analytical-canvas recipe without imposing an image quota.

    Supporting raster accents are optional. When present, they must stay inside
    a compact 6-12% body-area band and no single accent may become a hero image.
    """

    if manifest.get("schema_version") != "5.7":
        return []
    errors: list[str] = []
    analytical_types = {
        "hbar_chart",
        "bar_chart",
        "column_chart",
        "line_chart",
        "table",
        "matrix",
        "flow",
        "text_card",
        "metric_strip",
        "process",
    }
    body_area = float(body_box[2] * body_box[3])
    for slide_id, page in manifest.get("pages", {}).items():
        spec = page_specs.get(slide_id, {}) if isinstance(page_specs, dict) else {}
        elements = spec.get("elements", []) if isinstance(spec, dict) else []
        if not any(isinstance(item, dict) and item.get("type") in analytical_types for item in elements):
            errors.append(f"{slide_id}: analytical canvas requires at least one chart, table, matrix, flow, card, or metric strip")
        accent_ids = {
            item.get("asset_id")
            for item in page.get("visuals", [])
            if isinstance(item, dict)
            and item.get("disposition") == "crop"
            and item.get("role", "supporting_accent") == "supporting_accent"
            and item.get("asset_id")
        }
        accent_area = 0.0
        for element in elements:
            if not isinstance(element, dict) or element.get("asset_id") not in accent_ids:
                continue
            box = element.get("box")
            if not _valid_target_box(box):
                continue
            width, height = float(box[2]), float(box[3])
            accent_area += width * height
            if width > 1.40 or height > 1.40:
                errors.append(f"{slide_id}/{element.get('asset_id')}: supporting accent must remain inside a reserved icon lane")
        if accent_area:
            ratio = accent_area / body_area
            if ratio < 0.06 or ratio > 0.12:
                errors.append(
                    f"{slide_id}: supporting accents must occupy 6-12% of the body area; got {ratio:.1%}"
                )
    return errors


def validate_v58_page_policy(slides: list[dict[str, Any]], page_specs: dict[str, Any]) -> list[str]:
    path = Path(__file__).with_name("v58_visual_policy.py")
    spec = importlib.util.spec_from_file_location("standard_report_v58_visual_policy", path)
    if spec is None or spec.loader is None:
        return ["could not load V5.8 visual policy"]
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    errors: list[str] = []
    for slide in slides:
        slide_id = str(slide.get("slide_id", "?"))
        page_spec = page_specs.get(slide_id, {}) if isinstance(page_specs, dict) else {}
        errors.extend(policy.validate_visual_route(slide, page_spec))
        errors.extend(policy.validate_density(slide, page_spec))
    return errors


def validate_v58_visual_system(page_specs: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    path = Path(__file__).with_name("v58_visual_policy.py")
    spec = importlib.util.spec_from_file_location("standard_report_v58_visual_system", path)
    if spec is None or spec.loader is None:
        return ["could not load V5.8 visual policy"]
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    errors: list[str] = []
    pages = manifest.get("pages", {}) if isinstance(manifest, dict) else {}
    for slide_id, page_spec in page_specs.items():
        errors.extend(policy.validate_palette_and_visuals(page_spec, pages.get(slide_id, {})))
    return errors
