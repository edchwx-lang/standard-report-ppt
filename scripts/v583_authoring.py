from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "5.8"
SKILL_VERSION = "5.8.3"
MODERN_SCHEMA_VERSIONS = {"5.8", "5.9"}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_bundle(bundle: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    schema_version = str(bundle.get("schema_version", ""))
    if schema_version not in MODERN_SCHEMA_VERSIONS:
        raise ValueError("authoring bundle schema_version must be 5.8 or 5.9")
    slides = bundle.get("slides")
    page_specs = bundle.get("page_specs")
    manifest = bundle.get("visual_manifest", {"schema_version": schema_version, "pages": {}})
    if not isinstance(slides, list) or not slides:
        raise ValueError("authoring bundle slides must be a non-empty list")
    if not isinstance(page_specs, dict):
        raise ValueError("authoring bundle page_specs must be a mapping")
    expected_ids = [f"S{index:02d}" for index in range(1, len(slides) + 1)]
    if [slide.get("slide_id") for slide in slides if isinstance(slide, dict)] != expected_ids:
        raise ValueError(f"authoring bundle slides must use canonical IDs {expected_ids}")
    if sorted(page_specs) != expected_ids:
        raise ValueError(f"authoring bundle page_specs must cover {expected_ids}")
    if not isinstance(manifest, dict):
        raise ValueError("authoring bundle visual_manifest must be a mapping")
    manifest["schema_version"] = schema_version
    manifest.setdefault("schema_version", SCHEMA_VERSION)
    manifest.setdefault("pages", {})
    return deepcopy(slides), deepcopy(page_specs), deepcopy(manifest)


def _bind_design_drafts(project: Path, manifest: dict[str, Any], slide_ids: list[str]) -> dict[str, str]:
    draft_hashes: dict[str, str] = {}
    pages = manifest.setdefault("pages", {})
    for slide_id in slide_ids:
        page = pages.setdefault(slide_id, {})
        relative = page.setdefault("design_draft_path", f".build/design_drafts/{slide_id}.png")
        draft = (project / str(relative)).resolve()
        if draft.is_file():
            digest = _sha256_file(draft)
            page["design_draft_sha256"] = digest
            draft_hashes[slide_id] = digest
        else:
            page.pop("design_draft_sha256", None)
            draft_hashes[slide_id] = ""
    return draft_hashes


def _merge_review_if_current(new_payload: dict[str, Any], previous: dict[str, Any] | None) -> None:
    if not isinstance(previous, dict):
        return
    previous_pages = previous.get("pages", {})
    for slide_id, page in new_payload.get("pages", {}).items():
        old = previous_pages.get(slide_id) if isinstance(previous_pages, dict) else None
        if not isinstance(old, dict):
            continue
        if (
            old.get("canonical_sha256") == page.get("canonical_sha256")
            and old.get("design_draft_sha256") == page.get("design_draft_sha256")
        ):
            for field in ("reviewed", "review_method", "exact_match", "differences", "items"):
                if field in old:
                    page[field] = deepcopy(old[field])


def materialize_project(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    build = project / ".build"
    bundle_path = build / "authoring_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    slides, page_specs, manifest = _validate_bundle(bundle)
    slide_ids = [str(slide["slide_id"]) for slide in slides]
    draft_hashes = _bind_design_drafts(project, manifest, slide_ids)
    benchmark_module = _load_module(
        "standard_report_v583_text_benchmark",
        Path(__file__).with_name("v58_text_benchmark.py"),
    )
    benchmark_path = build / "blueprint_text_benchmark.json"
    previous_benchmark = None
    if benchmark_path.is_file():
        try:
            previous_benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            previous_benchmark = None
    schema_version = str(bundle.get("schema_version"))
    benchmark = benchmark_module.make_benchmark(
        slides, page_specs, draft_hashes, schema_version=schema_version
    )
    _merge_review_if_current(benchmark, previous_benchmark)
    _write_json_atomic(build / "slides.json", slides)
    _write_json_atomic(build / "page_specs.json", page_specs)
    _write_json_atomic(build / "visual_manifest.json", manifest)
    _write_json_atomic(benchmark_path, benchmark)
    result = {
        "schema_version": schema_version,
        "skill_version": "5.9.0" if schema_version == "5.9" else SKILL_VERSION,
        "ok": True,
        "authoring_bundle_sha256": _sha256_file(bundle_path),
        "design_draft_hashes": draft_hashes,
        "slides": len(slides),
        "bound_design_drafts": sum(bool(value) for value in draft_hashes.values()),
        "outputs": [
            ".build/slides.json",
            ".build/page_specs.json",
            ".build/visual_manifest.json",
            ".build/blueprint_text_benchmark.json",
        ],
    }
    _write_json_atomic(build / "authoring_report.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize V5.8.3 canonical manifests from one authoring bundle.")
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(json.dumps(materialize_project(args.project), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
