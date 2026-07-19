from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


VISIBLE_KEYS = {
    "text",
    "title",
    "body",
    "label",
    "series_name",
    "unit",
    "note",
    "value_text",
    "delta_text",
}


def _load_quality():
    path = Path(__file__).with_name("v582_quality.py")
    spec = importlib.util.spec_from_file_location("standard_report_v582_text_quality", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load V5.8.2 quality policy from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _iter_page_literals(value: Any, key: str | None = None):
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _iter_page_literals(child, str(child_key))
    elif isinstance(value, list):
        for child in value:
            yield from _iter_page_literals(child, key)
    elif isinstance(value, str) and key in VISIBLE_KEYS and _normalized(value):
        yield value


def required_ppt_literals(slide: dict[str, Any], page_spec: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("chapter", "title"):
        if isinstance(slide.get(field), str):
            values.append(slide[field])
    for point in slide.get("core_points", []):
        if isinstance(point, str):
            values.append(point)
    if isinstance(slide.get("source"), str):
        values.append(slide["source"])
    values.extend(_iter_page_literals(page_spec))
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalized(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result


def canonical_sha256(slide: dict[str, Any], page_spec: dict[str, Any]) -> str:
    payload = json.dumps(
        {"slide": slide, "page_spec": page_spec},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_benchmark(
    slides: list[dict[str, Any]],
    page_specs: dict[str, Any],
    design_draft_hashes: dict[str, str],
    *,
    schema_version: str = "5.8",
) -> dict[str, Any]:
    if schema_version not in {"5.8", "5.9"}:
        raise ValueError("benchmark schema_version must be 5.8 or 5.9")
    pages: dict[str, Any] = {}
    for slide in slides:
        slide_id = str(slide["slide_id"])
        page_spec = page_specs.get(slide_id, {})
        pages[slide_id] = {
            "canonical_sha256": canonical_sha256(slide, page_spec),
            "design_draft_sha256": design_draft_hashes.get(slide_id, ""),
            "reviewed": False,
            "review_method": "visual_or_ocr",
            "exact_match": False,
            "differences": [],
            "items": [
                {"expected": text, "observed": "", "match": False}
                for text in required_ppt_literals(slide, page_spec)
            ],
        }
    return {"schema_version": schema_version, "ok": False, "pages": pages}


def diagnose_benchmark(
    benchmark: dict[str, Any],
    slides: list[dict[str, Any]],
    page_specs: dict[str, Any],
    design_draft_hashes: dict[str, str],
) -> dict[str, Any]:
    quality = _load_quality()
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(benchmark, dict):
        warning = quality.issue(
            "BLUEPRINT_BENCHMARK_STRUCTURE",
            "warning",
            "blueprint",
            "blueprint text benchmark should be a mapping; canonical PPT text remains authoritative",
        )
        return quality.summarize([warning], [])
    if not isinstance(slides, list) or any(not isinstance(slide, dict) for slide in slides):
        warning = quality.issue(
            "BLUEPRINT_CANONICAL_STRUCTURE",
            "warning",
            "blueprint",
            "benchmark could not inspect canonical slides; the main prebuild validator owns this structure",
        )
        return quality.summarize([warning], [])
    if not isinstance(page_specs, dict):
        blockers.append(
            quality.issue(
                "BLUEPRINT_CANONICAL_STRUCTURE",
                "blocker",
                "blueprint",
                "canonical page_specs must be a mapping",
            )
        )
        page_specs = {}
    if not isinstance(design_draft_hashes, dict):
        blockers.append(
            quality.issue(
                "BLUEPRINT_DRAFT_STRUCTURE",
                "blocker",
                "blueprint",
                "design draft hashes must be a mapping",
            )
        )
        design_draft_hashes = {}
    if benchmark.get("schema_version") not in {"5.8", "5.9"}:
        blockers.append(
            quality.issue(
                "BLUEPRINT_BENCHMARK_SCHEMA",
                "blocker",
                "blueprint",
                "blueprint text benchmark schema_version must be 5.8 or 5.9",
            )
        )
    expected_ids = [str(slide.get("slide_id")) for slide in slides]
    pages = benchmark.get("pages", {})
    if not isinstance(pages, dict):
        blockers.append(
            quality.issue(
                "BLUEPRINT_BENCHMARK_STRUCTURE",
                "blocker",
                "blueprint",
                "blueprint text benchmark pages must be a mapping",
            )
        )
        pages = {}
    if sorted(pages) != sorted(expected_ids):
        blockers.append(
            quality.issue(
                "BLUEPRINT_BENCHMARK_COVERAGE",
                "blocker",
                "blueprint",
                f"blueprint text benchmark must cover {expected_ids}",
            )
        )
    by_id = {str(slide.get("slide_id")): slide for slide in slides}
    for slide_id in expected_ids:
        page = pages.get(slide_id, {})
        if not isinstance(page, dict):
            blockers.append(
                quality.issue(
                    "BLUEPRINT_BENCHMARK_STRUCTURE",
                    "blocker",
                    "blueprint",
                    "blueprint text benchmark page must be a mapping",
                    slide_id,
                )
            )
            continue
        expected_hash = canonical_sha256(by_id[slide_id], page_specs.get(slide_id, {}))
        if page.get("canonical_sha256") != expected_hash:
            blockers.append(
                quality.issue(
                    "BLUEPRINT_CANONICAL_STALE",
                    "blocker",
                    "blueprint",
                    "canonical text/layout hash is stale",
                    slide_id,
                )
            )
        if page.get("design_draft_sha256") != design_draft_hashes.get(slide_id):
            blockers.append(
                quality.issue(
                    "BLUEPRINT_DRAFT_STALE",
                    "blocker",
                    "blueprint",
                    "benchmark design draft hash is stale",
                    slide_id,
                )
            )
        if page.get("reviewed") is not True:
            warnings.append(
                quality.issue(
                    "BLUEPRINT_TEXT_UNREVIEWED",
                    "warning",
                    "blueprint",
                    "blueprint text benchmark has not been visually or OCR reviewed",
                    slide_id,
                )
            )
        if page.get("exact_match") is not True or page.get("differences"):
            warnings.append(
                quality.issue(
                    "BLUEPRINT_TEXT_MISMATCH",
                    "warning",
                    "blueprint",
                    "blueprint text differs from canonical editable content",
                    slide_id,
                )
            )
        items = page.get("items")
        if not isinstance(items, list):
            blockers.append(
                quality.issue(
                    "BLUEPRINT_BENCHMARK_ITEMS",
                    "blocker",
                    "blueprint",
                    "blueprint text benchmark items must be a list",
                    slide_id,
                )
            )
            items = []
        expected_items = {_normalized(value) for value in required_ppt_literals(by_id[slide_id], page_specs.get(slide_id, {}))}
        reviewed_items = {
            _normalized(str(item.get("expected", "")))
            for item in items
            if isinstance(item, dict) and item.get("match") is True
        }
        if expected_items - reviewed_items:
            warnings.append(
                quality.issue(
                    "BLUEPRINT_TEXT_COVERAGE",
                    "warning",
                    "blueprint",
                    "blueprint text review does not match all canonical text items",
                    slide_id,
                )
            )
    # The benchmark is diagnostic in V5.8.2. Its own stale or incomplete
    # metadata cannot block a build whose canonical manifests are valid.
    warnings.extend(
        quality.issue(
            str(item.get("code", "BLUEPRINT_BENCHMARK_ADVISORY")),
            "warning",
            str(item.get("stage", "blueprint")),
            str(item.get("message", "blueprint benchmark advisory")),
            item.get("slide_id"),
            item.get("metrics") if isinstance(item.get("metrics"), dict) else {},
        )
        for item in blockers
    )
    return quality.summarize(warnings, [])


def validate_benchmark(
    benchmark: dict[str, Any],
    slides: list[dict[str, Any]],
    page_specs: dict[str, Any],
    design_draft_hashes: dict[str, str],
) -> list[str]:
    diagnostics = diagnose_benchmark(benchmark, slides, page_specs, design_draft_hashes)
    return [str(item["message"]) for item in diagnostics["blockers"]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or validate a V5.8 blueprint text benchmark.")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()
    project = args.project.resolve()
    slides = json.loads((project / ".build" / "slides.json").read_text(encoding="utf-8"))
    page_specs = json.loads((project / ".build" / "page_specs.json").read_text(encoding="utf-8"))
    manifest = json.loads((project / ".build" / "visual_manifest.json").read_text(encoding="utf-8"))
    draft_hashes = {
        slide_id: str(page.get("design_draft_sha256", ""))
        for slide_id, page in manifest.get("pages", {}).items()
    }
    path = project / ".build" / "blueprint_text_benchmark.json"
    if args.create:
        payload = make_benchmark(slides, page_specs, draft_hashes)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_benchmark(payload, slides, page_specs, draft_hashes)
    payload["ok"] = not errors
    payload["errors"] = errors
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 2)


if __name__ == "__main__":
    main()
