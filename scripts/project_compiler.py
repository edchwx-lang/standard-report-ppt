from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pprint
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "5.7"
SUPPORTED_SCHEMA_VERSIONS = {"5.6", "5.7"}


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _contracts():
    path = Path(__file__).with_name("v56_contracts.py")
    spec = importlib.util.spec_from_file_location("standard_report_v56_contracts_compiler", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _literal(value: Any) -> str:
    return pprint.pformat(value, width=120, sort_dicts=False, compact=False)


def compile_generator_source(
    template_source: str,
    brief: dict,
    slides: list[dict],
    page_specs: dict[str, dict],
    blueprints: dict[str, dict],
    asset_crops: dict[str, dict],
    master_path: str | Path,
) -> str:
    page_count = int(brief["requested_page_count"])
    expected_ids = [f"S{index:02d}" for index in range(1, page_count + 1)]
    if [slide.get("slide_id") for slide in slides] != expected_ids:
        raise ValueError("slides must match the confirmed canonical order")
    if sorted(page_specs) != expected_ids:
        raise ValueError("page_specs must cover every final slide")
    master_path = Path(master_path).expanduser().resolve()
    if not master_path.is_file():
        raise FileNotFoundError(master_path)
    replacements = {
        "__PROJECT_SCHEMA_VERSION__": str(brief["schema_version"]),
        "__PRODUCTION_MODE__": str(brief["production_mode"]),
        "__COMPANY_TEMPLATE_PATH__": master_path.as_posix(),
        "__COMPANY_TEMPLATE_SHA256__": sha256_file(master_path),
    }
    source = template_source
    for token, value in replacements.items():
        source = source.replace(token, value)
    source = source.replace("0,  # __PAGE_COUNT__", f"{page_count},  # materialized page count")
    assignments = {
        "SLIDES = []": f"SLIDES = {_literal(slides)}",
        "BLUEPRINTS = {}": f"BLUEPRINTS = {_literal(blueprints)}",
        "ASSET_CROPS = {}": f"ASSET_CROPS = {_literal(asset_crops)}",
        "PAGE_SPECS = {}": f"PAGE_SPECS = {_literal(page_specs)}",
    }
    for old, new in assignments.items():
        if old not in source:
            raise ValueError(f"generator template is missing marker {old!r}")
        source = source.replace(old, new, 1)
    wrappers = []
    mapping = []
    for slide_id in expected_ids:
        wrappers.append(
            f"def build_slide_{slide_id}(presentation, slide, spec, body, project_dir):\n"
            f"    render_page_spec(slide, PAGE_SPECS[{slide_id!r}], body, project_dir, {slide_id!r})\n"
        )
        mapping.append(f"    {slide_id!r}: build_slide_{slide_id},")
    generated = "\n\n".join(wrappers) + "\n\nPAGE_BUILDERS = {\n" + "\n".join(mapping) + "\n}\n"
    if "# __PAGE_BUILDERS__" not in source:
        raise ValueError("generator template is missing # __PAGE_BUILDERS__")
    source = source.replace("# __PAGE_BUILDERS__", generated, 1)
    errors = _contracts().scan_text_integrity(source, location="generate_deck.py")
    if errors:
        raise ValueError("; ".join(errors))
    return source


def compile_project(project_dir: str | Path) -> Path:
    project_dir = Path(project_dir).resolve()
    skill_dir = Path(__file__).resolve().parents[1]
    brief = json.loads((project_dir / "project_brief.json").read_text(encoding="utf-8"))
    if brief.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"project brief schema_version must be one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    slides = json.loads((project_dir / ".build" / "slides.json").read_text(encoding="utf-8"))
    page_specs = json.loads((project_dir / ".build" / "page_specs.json").read_text(encoding="utf-8"))
    contracts = _contracts()
    text_errors = contracts.validate_structured_text({"slides": slides, "page_specs": page_specs}, location="project")
    if text_errors:
        raise ValueError("; ".join(text_errors))
    blueprints: dict[str, dict] = {}
    asset_crops: dict[str, dict] = {}
    manifest: dict[str, Any] = {"pages": {}}
    compiled_slides = deepcopy(slides)
    if brief["production_mode"] == "blueprint":
        manifest = json.loads((project_dir / ".build" / "visual_manifest.json").read_text(encoding="utf-8"))
        visual_errors = contracts.validate_visual_manifest(manifest)
        visual_errors.extend(contracts.validate_blueprint_visual_balance(page_specs, manifest))
        if visual_errors:
            raise ValueError("; ".join(visual_errors))
        by_id = {slide["slide_id"]: slide for slide in compiled_slides}
        for slide_id, page in manifest["pages"].items():
            blueprint = project_dir / "blueprints" / f"{slide_id}.png"
            if not blueprint.is_file():
                raise FileNotFoundError(blueprint)
            actual_hash = sha256_file(blueprint)
            if actual_hash != page["blueprint_sha256"]:
                raise ValueError(f"{slide_id}: visual manifest blueprint hash mismatch")
            blueprints[slide_id] = {"path": f"blueprints/{slide_id}.png", "sha256": actual_hash}
            by_id[slide_id].update(contracts.visual_page_to_slide_fields(page))
            for visual in page["visuals"]:
                if visual.get("disposition") != "crop":
                    continue
                asset_crops[visual["asset_id"]] = {
                    "slide_id": slide_id,
                    "source_px": visual["source_px"],
                    "target_box_in": visual["target_box_in"],
                    "fit_mode": "contain",
                    "padding_px": int(visual.get("padding_px", 4)),
                }
    template_source = (skill_dir / "assets" / "direct_blueprint_generator_template.py").read_text(encoding="utf-8")
    master_path = skill_dir / "assets" / "company_template.pptx"
    source = compile_generator_source(
        template_source, brief, compiled_slides, page_specs, blueprints, asset_crops, master_path
    )
    destination = project_dir / "generate_deck.py"
    temporary = destination.with_suffix(".py.tmp")
    temporary.write_text(source, encoding="utf-8")
    temporary.replace(destination)
    report = {
        "schema_version": brief["schema_version"],
        "generator": destination.name,
        "generator_sha256": sha256_file(destination),
        "pages": len(compiled_slides),
        "assets": len(asset_crops),
    }
    report_path = project_dir / ".build" / "compile_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    runtime_hash = sha256_file(skill_dir / "assets" / "direct_blueprint_generator_template.py")
    template_hash = sha256_file(master_path)
    pages_dir = project_dir / ".build" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    by_id = {slide["slide_id"]: slide for slide in slides}
    visual_pages = manifest.get("pages", {}) if isinstance(manifest, dict) else {}
    for slide_id in [f"S{index:02d}" for index in range(1, int(brief["requested_page_count"]) + 1)]:
        page_input = {
            "schema_version": brief["schema_version"],
            "production_mode": brief["production_mode"],
            "runtime_sha256": runtime_hash,
            "template_sha256": template_hash,
            "slide": by_id[slide_id],
            "page_spec": page_specs[slide_id],
            "visual": visual_pages.get(slide_id),
        }
        (pages_dir / f"{slide_id}.input.json").write_text(
            json.dumps(page_input, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile V5.7 manifests into one deterministic generate_deck.py.")
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(compile_project(args.project))


if __name__ == "__main__":
    main()
