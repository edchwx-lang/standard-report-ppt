from __future__ import annotations

import hashlib
import importlib.util
import json
import pprint
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _literal(value: Any) -> str:
    return pprint.pformat(value, width=120, sort_dicts=False)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _replace_once(source: str, marker: str, value: str) -> str:
    if source.count(marker) != 1:
        raise ValueError(f"Mac generator template requires exactly one {marker!r} marker")
    return source.replace(marker, value, 1)


def _aligned_assets(manifest: dict) -> dict[str, dict]:
    assets: dict[str, dict] = {}
    for slide_id, page in manifest.get("pages", {}).items():
        if not isinstance(page, dict):
            continue
        for visual in page.get("visuals", []):
            if not isinstance(visual, dict):
                continue
            treatment = visual.get("treatment", visual.get("disposition"))
            if treatment != "crop":
                continue
            asset_id = visual.get("asset_id")
            source_px = visual.get("source_px")
            target_box = visual.get("target_box_in")
            if (
                not isinstance(asset_id, str)
                or not asset_id
                or not isinstance(source_px, list)
                or len(source_px) != 4
                or not all(isinstance(value, int) for value in source_px)
                or not source_px[0] < source_px[2]
                or not source_px[1] < source_px[3]
                or not isinstance(target_box, list)
                or len(target_box) != 4
                or not all(isinstance(value, (int, float)) for value in target_box)
            ):
                raise ValueError(f"{slide_id}: invalid aligned crop visual")
            if asset_id in assets:
                raise ValueError(f"duplicate asset_id: {asset_id}")
            assets[asset_id] = {
                "slide_id": slide_id,
                "kind": str(visual.get("kind", "")),
                "source_px": source_px,
                "target_box_in": target_box,
                "target_coord_space": str(visual.get("target_coord_space", "body")),
                "padding_px": int(visual.get("padding_px", 4)),
            }
    return assets


def compile_project(project_dir: str | Path) -> Path:
    project = Path(project_dir).resolve()
    skill = Path(__file__).resolve().parents[1]
    brief = json.loads((project / "project_brief.json").read_text(encoding="utf-8"))
    if brief.get("schema_version") != "5.9":
        raise ValueError("Mac compiler requires schema_version 5.9")
    if brief.get("pipeline_revision") not in {"5.9.0", "5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}:
        raise ValueError(
            "Mac compiler requires pipeline_revision 5.9.0, 5.9.1, 5.9.2, 5.9.4, 5.9.5, or 5.9.6"
        )
    if brief.get("production_mode") == "blueprint":
        gate = _load_module(
            "standard_report_v59_blueprint_gate_mac",
            Path(__file__).with_name("v59_blueprint_gate.py"),
        )
        gate.assert_blueprint_gate(project, require_alignment=True)
    slides = json.loads((project / ".build" / "slides.json").read_text(encoding="utf-8"))
    page_specs = json.loads(
        (project / ".build" / "page_specs.json").read_text(encoding="utf-8")
    )
    manifest_path = project / ".build" / "visual_manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else {"schema_version": "5.9", "pages": {}}
    )
    expected = [
        f"S{index:02d}"
        for index in range(1, int(brief["requested_page_count"]) + 1)
    ]
    if [slide.get("slide_id") for slide in slides] != expected:
        raise ValueError("canonical slide order mismatch")
    if sorted(page_specs) != expected:
        raise ValueError("canonical page-spec coverage mismatch")
    template_path = skill / "assets" / "company_template.pptx"
    generator_template = skill / "assets" / "python_pptx_generator_template.py"
    vendor = skill / "assets" / "vendor" / "fonttools-4.63.0-py3.zip"
    for required in (template_path, generator_template, vendor):
        if not required.is_file():
            raise FileNotFoundError(required)
    source = generator_template.read_text(encoding="utf-8")
    replacements = {
        "__PROJECT_SCHEMA_VERSION__": "5.9",
        "__PRODUCTION_MODE__": str(brief["production_mode"]),
        "__COMPANY_TEMPLATE_PATH__": template_path.as_posix(),
        "__COMPANY_TEMPLATE_SHA256__": sha256_file(template_path),
        "__FONTTOOLS_VENDOR_PATH__": vendor.as_posix(),
    }
    for token, value in replacements.items():
        source = _replace_once(source, token, value)
    source = _replace_once(
        source, "0,  # __PAGE_COUNT__",
        f"{len(slides)},  # materialized page count",
    )
    contract_hashes = (
        _load_module(
            "standard_report_v591_contract_hashes_mac",
            Path(__file__).with_name("v591_contracts.py"),
        ).contract_hashes(project)
        if brief.get("pipeline_revision") in {"5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}
        else {}
    )
    source = _replace_once(
        source,
        "{},  # __CONTRACT_HASHES__",
        f"{_literal(contract_hashes)},  # compiled contract hashes",
    )
    source = _replace_once(source, "SLIDES = []", f"SLIDES = {_literal(slides)}")
    source = _replace_once(
        source, "PAGE_SPECS = {}", f"PAGE_SPECS = {_literal(page_specs)}"
    )
    pages = manifest.get("pages", {}) if isinstance(manifest, dict) else {}
    drafts = {
        slide_id: {
            "path": str(page.get("design_draft_path", "")),
            "sha256": str(page.get("design_draft_sha256", "")),
        }
        for slide_id, page in pages.items()
        if isinstance(page, dict)
    }
    source = _replace_once(
        source, "DESIGN_DRAFTS = {}", f"DESIGN_DRAFTS = {_literal(drafts)}"
    )
    source = _replace_once(
        source, "ASSET_CROPS = {}",
        f"ASSET_CROPS = {_literal(_aligned_assets(manifest))}",
    )
    metrics_source = (skill / "scripts" / "mac_text_metrics.py").read_text(
        encoding="utf-8"
    )
    ooxml_source = (skill / "scripts" / "mac_pptx_ooxml.py").read_text(
        encoding="utf-8"
    )
    source = _replace_once(
        source, 'TEXT_METRICS_SOURCE = ""',
        f"TEXT_METRICS_SOURCE = {metrics_source!r}",
    )
    source = _replace_once(
        source, 'OOXML_ADAPTER_SOURCE = ""',
        f"OOXML_ADAPTER_SOURCE = {ooxml_source!r}",
    )
    wrappers = []
    mappings = []
    for slide_id in expected:
        wrappers.append(
            f"def build_slide_{slide_id}(slide, spec, body, project_dir):\n"
            f"    render_page_spec(slide, PAGE_SPECS[{slide_id!r}], body, project_dir, {slide_id!r})\n"
        )
        mappings.append(f"    {slide_id!r}: build_slide_{slide_id},")
    generated = (
        "\n\n".join(wrappers)
        + "\n\nPAGE_BUILDERS = {\n"
        + "\n".join(mappings)
        + "\n}\n"
    )
    source = _replace_once(source, "# __PAGE_BUILDERS__", generated)
    destination = project / "generate_deck.py"
    temporary = destination.with_suffix(".py.tmp")
    compile(source, str(destination), "exec")
    temporary.write_text(source, encoding="utf-8")
    temporary.replace(destination)
    report = {
        "schema_version": "5.9",
        "pipeline_revision": str(brief["pipeline_revision"]),
        "builder_backend": "mac_python_pptx_v1",
        "generator": destination.name,
        "generator_sha256": sha256_file(destination),
        "template_sha256": sha256_file(template_path),
        "pages": len(slides),
        "assets": len(_aligned_assets(manifest)),
        "contract_hashes": contract_hashes,
    }
    report_path = project / ".build" / "compile_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Compile a V5.9 Mac generator.")
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(compile_project(args.project))


if __name__ == "__main__":
    main()
