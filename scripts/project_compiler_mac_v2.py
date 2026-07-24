from __future__ import annotations

import hashlib
import importlib.util
import json
import pprint
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.0"
PIPELINE_REVISION = "6.0.0"
BUILDER_BACKEND = "mac_python_pptx_v2"


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
        raise ValueError(f"Mac v2 generator requires exactly one {marker!r} marker")
    return source.replace(marker, value, 1)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a mapping")
    return payload


def _contract_hashes(project: Path, mode: str) -> dict[str, str]:
    files = {
        "authoring_bundle": ".build/authoring_bundle.json",
        "blueprint_alignment": ".build/blueprint_alignment.json",
        "slides": ".build/slides.json",
        "visual_manifest": ".build/visual_manifest.json",
        "mac_spec_report": ".build/mac_spec_report.json",
    }
    if mode == "deconstruct":
        files["page_specs"] = ".build/page_specs.json"
        files["mac_page_specs"] = ".build/mac_page_specs.json"
    else:
        files["bitmap_page_specs"] = ".build/bitmap_page_specs.json"
        files["bitmap_contract"] = ".build/bitmap_contract.json"
    return {
        f"{name}_sha256": sha256_file(project / relative)
        for name, relative in files.items()
        if (project / relative).is_file()
    }


def _blueprint_hashes(project: Path, expected: list[str]) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for slide_id in expected:
        path = project / "blueprints" / f"{slide_id}.png"
        if not path.is_file():
            raise FileNotFoundError(f"{slide_id}: immutable blueprint is missing")
        records[slide_id] = {
            "path": path.relative_to(project).as_posix(),
            "sha256": sha256_file(path),
        }
    return records


def _deconstruct_assets(
    project: Path, manifest: dict[str, Any], page_specs: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for slide_id, page in manifest.get("pages", {}).items():
        if not isinstance(page, dict):
            continue
        for visual in page.get("visuals", []):
            if not isinstance(visual, dict):
                continue
            if visual.get("treatment", visual.get("disposition")) != "crop":
                continue
            asset_id = visual.get("asset_id")
            if not isinstance(asset_id, str) or not asset_id:
                raise ValueError(f"{slide_id}: aligned crop requires asset_id")
            if asset_id in records:
                raise ValueError(f"duplicate asset_id: {asset_id}")
            asset_path = project / ".build" / "assets" / slide_id / f"{asset_id}.png"
            if not asset_path.is_file():
                raise FileNotFoundError(f"{slide_id}: missing aligned asset {asset_id}")
            records[asset_id] = {
                "slide_id": slide_id,
                "asset_id": asset_id,
                "asset_path": asset_path.relative_to(project).as_posix(),
                "asset_sha256": sha256_file(asset_path),
                "kind": str(visual.get("kind", "")),
                "fit": "contain",
            }
    used = {
        str(element["asset_id"])
        for page in page_specs.values()
        if isinstance(page, dict)
        for element in page.get("elements", [])
        if isinstance(element, dict) and element.get("type") == "asset"
    }
    if used != set(records):
        raise ValueError(
            "MAC_RECONSTRUCTION_UNSUPPORTED: page assets and aligned manifest differ"
        )
    return records


def _bitmap_assets(
    project: Path, contract: dict[str, Any], expected: list[str]
) -> dict[str, dict[str, Any]]:
    if (
        contract.get("schema_version") != SCHEMA_VERSION
        or contract.get("pipeline_revision") != PIPELINE_REVISION
        or contract.get("construction_mode") != "bitmap"
        or not isinstance(contract.get("pages"), dict)
        or set(contract["pages"]) != set(expected)
    ):
        raise ValueError("MAC_RECONSTRUCTION_UNSUPPORTED: invalid bitmap contract")
    records: dict[str, dict[str, Any]] = {}
    for slide_id in expected:
        raw = contract["pages"][slide_id]
        if not isinstance(raw, dict):
            raise ValueError(f"{slide_id}: invalid bitmap asset contract")
        asset_id = raw.get("asset_id")
        relative = raw.get("asset_path")
        if not isinstance(asset_id, str) or not asset_id or not isinstance(relative, str):
            raise ValueError(f"{slide_id}: bitmap asset identity is invalid")
        path = project / relative
        if (
            not path.is_file()
            or raw.get("asset_sha256") != sha256_file(path)
            or raw.get("fit") != "contain"
            or raw.get("target") != "runtime_body_box"
        ):
            raise ValueError(f"{slide_id}: bitmap asset contract is stale")
        if asset_id in records:
            raise ValueError(f"duplicate bitmap asset_id: {asset_id}")
        records[asset_id] = dict(raw, slide_id=slide_id)
    return records


def compile_project(project_dir: str | Path) -> Path:
    project = Path(project_dir).resolve()
    skill = Path(__file__).resolve().parents[1]
    brief = _read_json(project / "project_brief.json")
    if (
        brief.get("schema_version") != SCHEMA_VERSION
        or brief.get("pipeline_revision") != PIPELINE_REVISION
        or brief.get("production_mode") != "blueprint"
        or brief.get("construction_mode") not in {"deconstruct", "bitmap"}
    ):
        raise ValueError("Mac v2 compiler requires V6.0.0 blueprint construction")
    mode = str(brief["construction_mode"])
    slides = json.loads(
        (project / ".build" / "slides.json").read_text(encoding="utf-8")
    )
    if not isinstance(slides, list):
        raise ValueError("slides.json must contain a list")
    expected = [
        f"S{index:02d}"
        for index in range(1, int(brief["requested_page_count"]) + 1)
    ]
    if [slide.get("slide_id") for slide in slides] != expected:
        raise ValueError("canonical slide order mismatch")
    specs_name = "mac_page_specs.json" if mode == "deconstruct" else "bitmap_page_specs.json"
    page_specs = _read_json(project / ".build" / specs_name)
    if sorted(page_specs) != expected:
        raise ValueError("canonical page-spec coverage mismatch")
    normalizer = _load_module(
        "standard_report_v6_mac_spec_compiler",
        Path(__file__).with_name("v6_mac_spec.py"),
    )
    normalized, _ = normalizer.normalize_mac_page_specs(page_specs, mode)
    if normalized != page_specs:
        raise ValueError(
            "MAC_RECONSTRUCTION_UNSUPPORTED: compiler input is not normalized"
        )

    manifest_path = project / ".build" / "visual_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {"pages": {}}
    if mode == "deconstruct":
        asset_registry = _deconstruct_assets(project, manifest, page_specs)
    else:
        asset_registry = _bitmap_assets(
            project,
            _read_json(project / ".build" / "bitmap_contract.json"),
            expected,
        )
    blueprint_hashes = _blueprint_hashes(project, expected)
    contract_hashes = _contract_hashes(project, mode)

    template_path = skill / "assets" / "company_template.pptx"
    generator_template = skill / "assets" / "python_pptx_generator_template_v2.py"
    vendor = skill / "assets" / "vendor" / "fonttools-4.63.0-py3.zip"
    for required in (template_path, generator_template, vendor):
        if not required.is_file():
            raise FileNotFoundError(required)
    source = generator_template.read_text(encoding="utf-8")
    replacements = {
        "__PROJECT_SCHEMA_VERSION__": SCHEMA_VERSION,
        "__PIPELINE_REVISION__": PIPELINE_REVISION,
        "__PRODUCTION_MODE__": "blueprint",
        "__CONSTRUCTION_MODE__": mode,
        "__COMPANY_TEMPLATE_PATH__": template_path.as_posix(),
        "__COMPANY_TEMPLATE_SHA256__": sha256_file(template_path),
        "__FONTTOOLS_VENDOR_PATH__": vendor.as_posix(),
    }
    for token, value in replacements.items():
        source = _replace_once(source, token, value)
    source = _replace_once(
        source,
        "0,  # __PAGE_COUNT__",
        f"{len(slides)},  # materialized page count",
    )
    source = _replace_once(
        source,
        "{},  # __CONTRACT_HASHES__",
        f"{_literal(contract_hashes)},  # compiled contract hashes",
    )
    source = _replace_once(source, "SLIDES = []", f"SLIDES = {_literal(slides)}")
    source = _replace_once(
        source,
        "PAGE_SPECS = {}",
        f"PAGE_SPECS = {_literal(page_specs)}",
    )
    source = _replace_once(
        source,
        "BLUEPRINT_HASHES = {}",
        f"BLUEPRINT_HASHES = {_literal(blueprint_hashes)}",
    )
    source = _replace_once(
        source,
        "ASSET_REGISTRY = {}",
        f"ASSET_REGISTRY = {_literal(asset_registry)}",
    )
    metrics_source = (skill / "scripts" / "mac_text_metrics.py").read_text(
        encoding="utf-8"
    )
    ooxml_source = (skill / "scripts" / "mac_pptx_ooxml.py").read_text(
        encoding="utf-8"
    )
    source = _replace_once(
        source,
        'TEXT_METRICS_SOURCE = ""',
        f"TEXT_METRICS_SOURCE = {metrics_source!r}",
    )
    source = _replace_once(
        source,
        'OOXML_ADAPTER_SOURCE = ""',
        f"OOXML_ADAPTER_SOURCE = {ooxml_source!r}",
    )
    wrappers: list[str] = []
    mappings: list[str] = []
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
        "schema_version": SCHEMA_VERSION,
        "pipeline_revision": PIPELINE_REVISION,
        "production_mode": "blueprint",
        "construction_mode": mode,
        "builder_backend": BUILDER_BACKEND,
        "generator": destination.name,
        "generator_sha256": sha256_file(destination),
        "template_sha256": sha256_file(template_path),
        "pages": len(slides),
        "assets": len(asset_registry),
        "blueprint_hashes": blueprint_hashes,
        "contract_hashes": contract_hashes,
    }
    report_path = project / ".build" / "compile_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Compile a V6 Mac generator.")
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(compile_project(args.project))


if __name__ == "__main__":
    main()
