from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import tempfile
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree


CODE_FILES = (
    "project_brief.json",
    "slide_specs.json",
    "blueprint_geometry.json",
    "blueprint_generation_manifest.json",
    "project_manifest.json",
    "metrics.json",
)
REQUIRED_PROJECT_FILES = (
    "project_brief.json",
    "slide_specs.json",
    "blueprint_geometry.json",
    "blueprint_generation_manifest.json",
)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_delivery_zip(path: str | Path, pptx_name: str) -> dict:
    """Verify the exact V5.5 delivery shape, including both nested archives."""

    path = Path(path).resolve()
    expected = [pptx_name, "blueprints.zip", "py.zip"]
    with ZipFile(path) as archive:
        entries = archive.namelist()
        if entries != expected:
            raise ValueError(f"delivery ZIP outer entries must be exactly {expected}; got {entries}")
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError(f"delivery ZIP integrity failed at {bad_member}")
        with tempfile.TemporaryDirectory(prefix=".ppt_delivery_verify_", dir=path.parent) as directory:
            directory = Path(directory)
            archive.extract("blueprints.zip", directory)
            archive.extract("py.zip", directory)
            with ZipFile(directory / "blueprints.zip") as blueprints:
                if blueprints.testzip():
                    raise ValueError("blueprints.zip failed its integrity check")
            with ZipFile(directory / "py.zip") as code:
                if code.namelist() != ["generate_deck.py"] or code.testzip():
                    raise ValueError("py.zip must contain only a valid generate_deck.py")
    return {"outer_entries": expected, "zip_sha256": sha256_file(path)}


def _write_code_zip(project_dir: Path, runtime_dir: Path, destination: Path) -> None:
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for name in CODE_FILES:
            path = project_dir / name
            if path.exists():
                archive.write(path, name)
        for path in sorted(runtime_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            archive.write(path, f"runtime/{path.name}")


def _write_blueprints_zip(project_dir: Path, destination: Path, *, mode: str = "blueprint") -> None:
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        written = 0
        blueprint_dir = project_dir / "blueprints"
        if blueprint_dir.exists():
            for path in sorted(blueprint_dir.rglob("*")):
                is_composition_record = path.name.endswith(".composition.json")
                if path.is_file() and (path.suffix.lower() in {".png", ".jpg", ".jpeg"} or is_composition_record):
                    archive.write(path, path.relative_to(blueprint_dir).as_posix())
                    written += 1
        asset_dir = project_dir / "blueprint_assets"
        if asset_dir.exists():
            for path in sorted(asset_dir.rglob("*")):
                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    archive.write(path, path.relative_to(project_dir).as_posix())
                    written += 1
        state_path = project_dir / "direct_blueprint_state.json"
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            recorded_assets = [
                item
                for page in state.get("pages", [])
                if isinstance(page, dict)
                for item in page.get("assets", [])
                if isinstance(item, dict)
            ]
            for item in sorted(recorded_assets, key=lambda record: record.get("asset_id", "")):
                relative = item.get("path")
                asset_id = item.get("asset_id")
                if not isinstance(relative, str) or not isinstance(asset_id, str):
                    continue
                path = project_dir / relative
                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    slide_id = path.parent.name
                    archive.write(path, f"assets/{slide_id}/{asset_id}{path.suffix.lower()}")
                    written += 1
        visual_manifest_path = project_dir / ".build" / "visual_manifest.json"
        if visual_manifest_path.is_file():
            manifest = json.loads(visual_manifest_path.read_text(encoding="utf-8"))
            for slide_id, page in sorted(manifest.get("pages", {}).items()):
                for visual in page.get("visuals", []):
                    if visual.get("disposition") != "crop":
                        continue
                    asset_id = visual.get("asset_id")
                    if not isinstance(asset_id, str) or not asset_id:
                        continue
                    asset_path = project_dir / ".build" / "assets" / slide_id / f"{asset_id}.png"
                    if asset_path.is_file():
                        archive.write(asset_path, f"assets/{slide_id}/{asset_id}.png")
                        written += 1
        if written == 0 and mode == "fast":
            archive.writestr("MODE.txt", "Fast mode: ImageGen blueprints were intentionally not used.\n")


def _write_py_zip(generator_path: Path, destination: Path) -> None:
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        archive.write(generator_path, "generate_deck.py")


def _validate_direct_project(project_dir: Path) -> list[str]:
    module_path = Path(__file__).resolve().with_name("direct_project.py")
    spec = importlib.util.spec_from_file_location("standard_report_ppt_direct_project_pack", module_path)
    if spec is None or spec.loader is None:
        return ["could not load Direct Blueprint validator"]
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_direct_project(project_dir)


def _load_v56_contracts():
    module_path = Path(__file__).resolve().with_name("v56_contracts.py")
    spec = importlib.util.spec_from_file_location("standard_report_ppt_v56_contracts_pack", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load V5.6 contracts")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"missing literal assignment {name}")


def _validate_manifest_project(
    project_dir: Path,
    pptx_path: Path,
    generator_path: Path,
    *,
    schema_version: str,
) -> list[str]:
    errors: list[str] = []
    brief_path = project_dir / "project_brief.json"
    slides_path = project_dir / ".build" / "slides.json"
    page_specs_path = project_dir / ".build" / "page_specs.json"
    result_path = project_dir / ".build" / "pipeline_result.json"
    required = [brief_path, slides_path, page_specs_path, result_path]
    for path in required:
        if not path.is_file():
            errors.append(f"missing V{schema_version} artifact: {path.relative_to(project_dir)}")
    if errors:
        return errors

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    slides = json.loads(slides_path.read_text(encoding="utf-8"))
    page_specs = json.loads(page_specs_path.read_text(encoding="utf-8"))
    pipeline_result = json.loads(result_path.read_text(encoding="utf-8"))
    contracts = _load_v56_contracts()

    if brief.get("schema_version") != schema_version:
        errors.append(f"project brief schema_version must be {schema_version}")
    expected_count = brief.get("requested_page_count")
    if not isinstance(expected_count, int) or expected_count <= 0:
        errors.append("requested_page_count must be a positive integer")
        expected_count = 0
    expected_ids = [f"S{index:02d}" for index in range(1, expected_count + 1)]
    slide_ids = [slide.get("slide_id") for slide in slides] if isinstance(slides, list) else []
    if slide_ids != expected_ids:
        errors.append(f"slides.json must cover {expected_ids}; got {slide_ids}")
    if sorted(page_specs) != expected_ids:
        errors.append(f"page_specs.json must cover {expected_ids}; got {sorted(page_specs)}")
    errors.extend(contracts.validate_structured_text(
        {"brief": brief, "slides": slides, "page_specs": page_specs}, location="delivery"
    ))

    mode = brief.get("production_mode")
    if mode == "blueprint":
        manifest_path = project_dir / ".build" / "visual_manifest.json"
        if not manifest_path.is_file():
            errors.append(f"missing V{schema_version} artifact: .build/visual_manifest.json")
        else:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            errors.extend(contracts.validate_visual_manifest(manifest))
            if schema_version == "5.7":
                errors.extend(contracts.validate_blueprint_visual_balance(page_specs, manifest))
            pages = manifest.get("pages", {})
            if sorted(pages) != expected_ids:
                errors.append(f"visual_manifest.json must cover {expected_ids}; got {sorted(pages)}")
            for slide_id in expected_ids:
                page = pages.get(slide_id, {})
                relative = page.get("blueprint_path")
                blueprint_path = project_dir / relative if isinstance(relative, str) else None
                if blueprint_path is None or not blueprint_path.is_file():
                    errors.append(f"{slide_id}: accepted blueprint is missing")
                    continue
                if sha256_file(blueprint_path) != page.get("blueprint_sha256"):
                    errors.append(f"{slide_id}: accepted blueprint SHA-256 mismatch")

    if pipeline_result.get("schema_version") != schema_version or pipeline_result.get("ok") is not True:
        errors.append(f"V{schema_version} pipeline_result.json must report ok=true")
    if pipeline_result.get("pages") != expected_count:
        errors.append(f"V{schema_version} pipeline result page count mismatch")
    audit_requirements = {
        "ppt_text_audit.json": "ok",
        "ppt_skeleton_audit.json": "ok",
    }
    if mode == "blueprint":
        audit_requirements.update({"ppt_asset_audit.json": "ok", "blueprint_fidelity.json": "passed"})
    for filename, field in audit_requirements.items():
        audit_path = project_dir / ".build" / filename
        if not audit_path.is_file():
            errors.append(f"missing audit: .build/{filename}")
            continue
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get(field) is not True:
            errors.append(f"audit did not pass: .build/{filename}")

    generator_text = generator_path.read_text(encoding="utf-8")
    try:
        deck_meta = _read_literal_assignment(generator_path, "DECK_META")
    except (SyntaxError, ValueError) as exc:
        errors.append(f"could not read DECK_META: {exc}")
        deck_meta = {}
    if deck_meta.get("schema_version") != schema_version:
        errors.append(f"DECK_META schema_version must be {schema_version}")
    for marker in ("fast_geometry", "runtime_archetype"):
        if marker in generator_text:
            errors.append(f"V{schema_version} blueprint generator contains forbidden marker: {marker}")
    for slide_id in expected_ids:
        if f"def build_slide_{slide_id}(" not in generator_text:
            errors.append(f"missing page-specific builder for {slide_id}")
    if _pptx_page_count(pptx_path) != expected_count:
        errors.append("PPTX page count does not match requested_page_count")
    return errors


def _validate_v56_project(project_dir: Path, pptx_path: Path, generator_path: Path) -> list[str]:
    return _validate_manifest_project(project_dir, pptx_path, generator_path, schema_version="5.6")


def _validate_v57_project(project_dir: Path, pptx_path: Path, generator_path: Path) -> list[str]:
    return _validate_manifest_project(project_dir, pptx_path, generator_path, schema_version="5.7")


def _run_skeleton_audit(project_dir: Path, pptx_path: Path) -> dict:
    module_path = Path(__file__).resolve().with_name("ppt_skeleton_audit.py")
    spec = importlib.util.spec_from_file_location("standard_report_ppt_skeleton_audit_pack", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PPT skeleton audit")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = project_dir / ".build" / "ppt_skeleton_audit.json"
    result = module.audit_pptx(pptx_path, output)
    if result.get("ok") is not True:
        raise ValueError("PPT skeleton audit failed:\n- " + "\n- ".join(result.get("errors", [])))
    return result


def _run_asset_audit(project_dir: Path, pptx_path: Path, generator_path: Path) -> dict:
    module_path = Path(__file__).resolve().with_name("ppt_asset_audit.py")
    spec = importlib.util.spec_from_file_location("standard_report_ppt_asset_audit_pack", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PPT asset audit")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = project_dir / ".build" / "ppt_asset_audit.json"
    result = module.audit_pptx(pptx_path, generator_path, project_dir, output)
    if result.get("ok") is not True:
        raise ValueError("PPT asset audit failed:\n- " + "\n- ".join(result.get("errors", [])))
    return result


def _pptx_page_count(path: Path) -> int:
    try:
        with ZipFile(path) as archive:
            payload = archive.read("ppt/presentation.xml")
    except Exception as exc:
        raise ValueError(f"invalid PPTX package: {exc}") from exc
    root = ElementTree.fromstring(payload)
    namespace = "http://schemas.openxmlformats.org/presentationml/2006/main"
    return len(root.findall(f".//{{{namespace}}}sldId"))


def package_direct_delivery(
    *,
    project_dir: str | Path,
    pptx_path: str | Path,
    generator_path: str | Path,
    output_zip: str | Path,
    desktop_dir: str | Path | None = None,
) -> Path:
    """Create the V5 desktop handoff with exactly three outer entries.

    The project retains working files internally, but the user-facing location
    receives only this ZIP: the PPTX, blueprints.zip, and py.zip. The project
    Python is deliberately restricted to one whole-deck generator.
    """

    project_dir = Path(project_dir).resolve()
    pptx_path = Path(pptx_path).resolve()
    generator_path = Path(generator_path).resolve()
    output_zip = Path(output_zip).resolve()
    desktop_dir = Path(desktop_dir or (Path.home() / "Desktop")).resolve()
    if output_zip.parent != desktop_dir:
        raise ValueError(f"final Direct Blueprint ZIP must be written directly to the desktop: {desktop_dir}")
    if not pptx_path.is_file():
        raise FileNotFoundError(pptx_path)
    if not generator_path.is_file():
        raise FileNotFoundError(generator_path)
    if generator_path.parent != project_dir or generator_path.name != "generate_deck.py":
        raise ValueError("the project generator must be <project>/generate_deck.py")
    project_python = sorted(path.resolve() for path in project_dir.rglob("*.py") if path.is_file())
    if project_python != [generator_path]:
        raise ValueError(
            "Direct Blueprint delivery requires exactly one project Python file named generate_deck.py; "
            f"found={[path.name for path in project_python]}"
        )
    brief_path = project_dir / "project_brief.json"
    if not brief_path.is_file():
        raise FileNotFoundError(brief_path)
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    mode = brief.get("production_mode")
    expected_page_count = brief.get("requested_page_count")
    blueprint_files = [
        path
        for path in (project_dir / "blueprints").rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ] if (project_dir / "blueprints").is_dir() else []
    if mode == "blueprint" and not blueprint_files:
        raise FileNotFoundError("no blueprint images found in <project>/blueprints")

    schema_version = brief.get("schema_version")
    if schema_version == "5.7":
        validation_errors = _validate_v57_project(project_dir, pptx_path, generator_path)
    elif schema_version == "5.6":
        _run_skeleton_audit(project_dir, pptx_path)
        if mode == "blueprint":
            _run_asset_audit(project_dir, pptx_path, generator_path)
        validation_errors = _validate_v56_project(project_dir, pptx_path, generator_path)
    else:
        _run_skeleton_audit(project_dir, pptx_path)
        if mode == "blueprint":
            _run_asset_audit(project_dir, pptx_path, generator_path)
        validation_errors = _validate_direct_project(project_dir)
    if validation_errors:
        raise ValueError("Direct Blueprint validation failed:\n- " + "\n- ".join(validation_errors))
    actual_page_count = _pptx_page_count(pptx_path)
    if actual_page_count != expected_page_count:
        raise ValueError(
            f"PPTX page count mismatch: expected {expected_page_count}, got {actual_page_count}"
        )
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    package_start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=".ppt_direct_delivery_", dir=output_zip.parent) as tmp:
        tmp_path = Path(tmp)
        py_zip = tmp_path / "py.zip"
        blueprints_zip = tmp_path / "blueprints.zip"
        temporary_bundle = tmp_path / output_zip.name
        _write_py_zip(generator_path, py_zip)
        _write_blueprints_zip(project_dir, blueprints_zip, mode=mode)
        with ZipFile(py_zip) as archive:
            if archive.namelist() != ["generate_deck.py"] or archive.testzip():
                raise ValueError("py.zip must contain only a valid generate_deck.py")
        with ZipFile(blueprints_zip) as archive:
            if archive.testzip():
                raise ValueError("blueprints.zip failed its integrity check")
        with ZipFile(temporary_bundle, "w", ZIP_DEFLATED) as archive:
            archive.write(pptx_path, pptx_path.name)
            archive.write(blueprints_zip, "blueprints.zip")
            archive.write(py_zip, "py.zip")
        with ZipFile(temporary_bundle) as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"delivery ZIP integrity check failed at {bad_member}")
        temporary_bundle.replace(output_zip)
    package_seconds = round(time.perf_counter() - package_start, 3)
    verify_start = time.perf_counter()
    verification = verify_delivery_zip(output_zip, pptx_path.name)
    delivery_verify_seconds = round(time.perf_counter() - verify_start, 3)
    record = {
        "schema_version": str(brief.get("schema_version", "5.5")),
        "zip_path": str(output_zip),
        "zip_sha256": verification["zip_sha256"],
        "pptx_page_count": actual_page_count,
        "outer_entries": verification["outer_entries"],
        "package_seconds": package_seconds,
        "delivery_verify_seconds": delivery_verify_seconds,
    }
    record_path = project_dir / ".build" / "delivery_record.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_record = record_path.with_suffix(".json.tmp")
    temporary_record.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_record.replace(record_path)
    return output_zip


def package_delivery(
    *,
    project_dir: str | Path,
    pptx_path: str | Path,
    output_zip: str | Path,
    runtime_dir: str | Path,
) -> Path:
    project_dir = Path(project_dir)
    pptx_path = Path(pptx_path)
    output_zip = Path(output_zip)
    runtime_dir = Path(runtime_dir)
    if not pptx_path.exists():
        raise FileNotFoundError(pptx_path)
    missing = [name for name in REQUIRED_PROJECT_FILES if not (project_dir / name).is_file()]
    if missing:
        raise FileNotFoundError("required project files missing: " + ", ".join(missing))
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ppt_delivery_") as tmp:
        tmp_path = Path(tmp)
        code_zip = tmp_path / "code.zip"
        blueprints_zip = tmp_path / "blueprints.zip"
        _write_code_zip(project_dir, runtime_dir, code_zip)
        _write_blueprints_zip(project_dir, blueprints_zip)
        with ZipFile(output_zip, "w", ZIP_DEFLATED) as archive:
            archive.write(pptx_path, pptx_path.name)
            archive.write(code_zip, "code.zip")
            archive.write(blueprints_zip, "blueprints.zip")
    return output_zip


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a legacy V4 or Direct Blueprint V5 delivery ZIP.")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument(
        "--generator",
        type=Path,
        help="V5 mode: one whole-deck generate_deck.py; produces PPTX + blueprints.zip + py.zip",
    )
    parser.add_argument("--legacy", action="store_true", help="Use the V4 compatibility package format")
    args = parser.parse_args()
    if args.generator:
        print(
            package_direct_delivery(
                project_dir=args.project,
                pptx_path=args.pptx,
                generator_path=args.generator,
                output_zip=args.output,
            )
        )
        return
    if not args.legacy:
        parser.error("V5 Direct Blueprint packaging requires --generator; pass --legacy only for a V4 project")
    runtime = args.runtime or Path(__file__).resolve().parent
    print(
        package_delivery(
            project_dir=args.project,
            pptx_path=args.pptx,
            output_zip=args.output,
            runtime_dir=runtime,
        )
    )


if __name__ == "__main__":
    main()
