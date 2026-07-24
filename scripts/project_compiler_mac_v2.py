from __future__ import annotations

import hashlib
import importlib.util
import json
import pprint
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.0"
PIPELINE_REVISION = "6.0.0"
BUILDER_BACKEND = "mac_python_pptx_v2"
ERROR_UNSUPPORTED = "MAC_RECONSTRUCTION_UNSUPPORTED"
ERROR_CONTRACT = "MAC_V6_CONTRACT_INVALID"
ERROR_ASSET = "MAC_ASSET_CONTRACT_MISMATCH"
ERROR_BLUEPRINT = "MAC_BLUEPRINT_HASH_MISMATCH"
_SAFE_ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


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


def _required_payload(project: Path, relative: str) -> Any:
    path = project / relative
    if not path.is_file():
        raise FileNotFoundError(f"{ERROR_CONTRACT}: missing {relative}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{ERROR_CONTRACT}: invalid {relative}") from exc


def _required_json(project: Path, relative: str) -> dict[str, Any]:
    payload = _required_payload(project, relative)
    if not isinstance(payload, dict):
        raise ValueError(f"{ERROR_CONTRACT}: {relative} must be a mapping")
    return payload


def _safe_asset_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(_SAFE_ASSET_ID.fullmatch(value))
        and ".." not in value
    )


def _canonical_project_path(
    project: Path,
    relative: Any,
    expected: str,
    *,
    error_code: str,
) -> Path:
    if not isinstance(relative, str) or relative != expected:
        raise ValueError(f"{error_code}: expected {expected}")
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ValueError(f"{error_code}: absolute path forbidden")
    resolved_project = project.resolve()
    resolved = (resolved_project / candidate).resolve()
    if resolved != resolved_project and resolved_project not in resolved.parents:
        raise ValueError(f"{error_code}: path escapes project")
    return resolved


def _contract_hashes(project: Path, mode: str) -> dict[str, str]:
    files = {
        "slides": ".build/slides.json",
        "formal_blueprint_manifest": ".build/formal_blueprint_manifest.json",
    }
    if mode == "deconstruct":
        files.update(
            {
                "authoring_bundle": ".build/authoring_bundle.json",
                "blueprint_alignment": ".build/blueprint_alignment.json",
                "visual_manifest": ".build/visual_manifest.json",
                "mac_spec_report": ".build/mac_spec_report.json",
                "page_specs": ".build/page_specs.json",
                "mac_page_specs": ".build/mac_page_specs.json",
            }
        )
    else:
        files["bitmap_page_specs"] = ".build/bitmap_page_specs.json"
        files["bitmap_contract"] = ".build/bitmap_contract.json"
    hashes: dict[str, str] = {}
    for name, relative in files.items():
        path = project / relative
        if not path.is_file():
            raise FileNotFoundError(f"{ERROR_CONTRACT}: missing {relative}")
        hashes[f"{name}_sha256"] = sha256_file(path)
    return hashes


def _blueprint_hashes(
    project: Path,
    expected: list[str],
    formal_manifest: dict[str, Any],
    visual_manifest: dict[str, Any] | None,
) -> dict[str, dict[str, str]]:
    if (
        formal_manifest.get("schema_version") != SCHEMA_VERSION
        or not isinstance(formal_manifest.get("pages"), dict)
        or set(formal_manifest["pages"]) != set(expected)
    ):
        raise ValueError(f"{ERROR_CONTRACT}: invalid formal blueprint manifest")
    visual_pages = (
        visual_manifest.get("pages")
        if isinstance(visual_manifest, dict)
        else None
    )
    if visual_manifest is not None and (
        visual_manifest.get("schema_version") != SCHEMA_VERSION
        or not isinstance(visual_pages, dict)
        or set(visual_pages) != set(expected)
    ):
        raise ValueError(f"{ERROR_CONTRACT}: invalid visual manifest")
    records: dict[str, dict[str, str]] = {}
    for slide_id in expected:
        locked = formal_manifest["pages"].get(slide_id)
        if not isinstance(locked, dict):
            raise ValueError(f"{ERROR_CONTRACT}: {slide_id} blueprint lock")
        expected_path = f"blueprints/{slide_id}.png"
        path = _canonical_project_path(
            project,
            locked.get("formal_blueprint_path"),
            expected_path,
            error_code=ERROR_BLUEPRINT,
        )
        locked_hash = locked.get("formal_blueprint_sha256")
        if (
            not isinstance(locked_hash, str)
            or len(locked_hash) != 64
            or not path.is_file()
            or sha256_file(path) != locked_hash
        ):
            raise ValueError(f"{ERROR_BLUEPRINT}: {slide_id}")
        if visual_pages is not None:
            visual = visual_pages.get(slide_id)
            if (
                not isinstance(visual, dict)
                or visual.get("formal_blueprint_path") != expected_path
                or visual.get("formal_blueprint_sha256") != locked_hash
                or visual.get("design_draft_sha256") != locked_hash
            ):
                raise ValueError(
                    f"{ERROR_BLUEPRINT}: {slide_id} visual lock mismatch"
                )
        records[slide_id] = {
            "path": expected_path,
            "sha256": locked_hash,
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
            if not _safe_asset_id(asset_id):
                raise ValueError(f"{slide_id}: aligned crop requires asset_id")
            if asset_id in records:
                raise ValueError(f"duplicate asset_id: {asset_id}")
            expected_path = f".build/assets/{slide_id}/{asset_id}.png"
            asset_path = _canonical_project_path(
                project,
                expected_path,
                expected_path,
                error_code=ERROR_ASSET,
            )
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
        if not _safe_asset_id(asset_id):
            raise ValueError(f"{ERROR_ASSET}: {slide_id} asset identity")
        expected_path = f".build/assets/{slide_id}/{asset_id}.png"
        path = _canonical_project_path(
            project,
            relative,
            expected_path,
            error_code=ERROR_ASSET,
        )
        expected_blueprint = f"blueprints/{slide_id}.png"
        blueprint = _canonical_project_path(
            project,
            raw.get("source_blueprint"),
            expected_blueprint,
            error_code=ERROR_BLUEPRINT,
        )
        locked = contract["_locked_blueprints"][slide_id]
        if (
            not path.is_file()
            or raw.get("asset_sha256") != sha256_file(path)
            or raw.get("fit") != "contain"
            or raw.get("target") != "runtime_body_box"
        ):
            raise ValueError(f"{ERROR_ASSET}: {slide_id} bitmap asset is stale")
        if (
            not blueprint.is_file()
            or raw.get("source_blueprint_sha256") != locked["sha256"]
            or sha256_file(blueprint) != locked["sha256"]
        ):
            raise ValueError(f"{ERROR_BLUEPRINT}: {slide_id} bitmap source")
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
        raise ValueError(
            f"{ERROR_UNSUPPORTED}: Mac v2 compiler requires V6.0.0 blueprint construction"
        )
    mode = str(brief["construction_mode"])
    slides = _required_payload(project, ".build/slides.json")
    if not isinstance(slides, list):
        raise ValueError("slides.json must contain a list")
    expected = [
        f"S{index:02d}"
        for index in range(1, int(brief["requested_page_count"]) + 1)
    ]
    if [slide.get("slide_id") for slide in slides] != expected:
        raise ValueError("canonical slide order mismatch")
    specs_name = "mac_page_specs.json" if mode == "deconstruct" else "bitmap_page_specs.json"
    page_specs = _required_json(project, f".build/{specs_name}")
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

    formal_manifest = _required_json(
        project, ".build/formal_blueprint_manifest.json"
    )
    manifest = (
        _required_json(project, ".build/visual_manifest.json")
        if mode == "deconstruct"
        else (
            _read_json(project / ".build" / "visual_manifest.json")
            if (project / ".build" / "visual_manifest.json").is_file()
            else None
        )
    )
    if mode == "deconstruct":
        alignment = _required_json(project, ".build/blueprint_alignment.json")
        authoring = _required_json(project, ".build/authoring_bundle.json")
        if (
            alignment.get("schema_version") != SCHEMA_VERSION
            or not isinstance(alignment.get("pages"), dict)
            or set(alignment["pages"]) != set(expected)
            or authoring.get("schema_version") != SCHEMA_VERSION
        ):
            raise ValueError(f"{ERROR_CONTRACT}: invalid deconstruction contracts")
    blueprint_hashes = _blueprint_hashes(
        project,
        expected,
        formal_manifest,
        manifest,
    )
    if mode == "deconstruct":
        assert isinstance(manifest, dict)
        asset_registry = _deconstruct_assets(project, manifest, page_specs)
    else:
        bitmap_contract = _required_json(project, ".build/bitmap_contract.json")
        bitmap_contract["_locked_blueprints"] = blueprint_hashes
        asset_registry = _bitmap_assets(
            project,
            bitmap_contract,
            expected,
        )
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
