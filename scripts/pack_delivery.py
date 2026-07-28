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


def validate_contract_hashes(
    project_dir: str | Path,
    expected: dict[str, str],
) -> list[str]:
    project = Path(project_dir).resolve()
    module_path = Path(__file__).with_name("v591_contracts.py")
    spec = importlib.util.spec_from_file_location(
        "standard_report_v591_contract_hashes_pack",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    current = module.contract_hashes(project)
    errors: list[str] = []
    for key, expected_hash in expected.items():
        actual = current.get(key)
        if actual != expected_hash:
            label = key.removesuffix("_sha256")
            errors.append(f"{label} hash mismatch after compilation")
    return errors


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_v594(brief: dict) -> bool:
    return (
        brief.get("schema_version") == "5.9"
        and brief.get("pipeline_revision") == "5.9.4"
    )


def _is_v595(brief: dict) -> bool:
    return (
        brief.get("schema_version") == "5.9"
        and brief.get("pipeline_revision") in {"5.9.5", "5.9.6"}
    )


def validate_packaging_visual_manifest(
    contracts: object,
    manifest: dict,
    brief: dict,
) -> list[str]:
    if _is_v594(brief) or _is_v595(brief):
        report = contracts.diagnose_visual_manifest(manifest)
        return [
            str(item["message"])
            for item in report.get("blockers", [])
            if isinstance(item, dict)
        ]
    return contracts.validate_visual_manifest(manifest)


def validate_project_python_policy(
    project_dir: str | Path,
    generator_path: str | Path,
    brief: dict,
) -> list[str]:
    project = Path(project_dir).resolve()
    generator = Path(generator_path).resolve()
    if brief.get("schema_version") == "5.8" or _is_v594(brief) or _is_v595(brief):
        return []
    project_python = sorted(
        path.resolve()
        for path in project.rglob("*.py")
        if path.is_file()
    )
    if project_python == [generator]:
        return []
    return [
        "Direct Blueprint delivery requires exactly one project Python file "
        f"named generate_deck.py; found={[path.name for path in project_python]}"
    ]


def validate_v594_asset_audit(
    project_dir: str | Path,
    pptx_path: str | Path,
    brief: dict,
) -> list[str]:
    if not (
        (_is_v594(brief) or _is_v595(brief))
        and brief.get("production_mode") == "blueprint"
    ):
        return []
    project = Path(project_dir).resolve()
    pptx = Path(pptx_path).resolve()
    audit_path = project / ".build" / "ppt_asset_audit.json"
    if not audit_path.is_file():
        return ["missing audit: .build/ppt_asset_audit.json"]
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"could not read .build/ppt_asset_audit.json: {exc}"]
    errors: list[str] = []
    if audit.get("ok") is not True:
        errors.append("audit did not pass: .build/ppt_asset_audit.json")
    if not pptx.is_file() or audit.get("pptx_sha256") != sha256_file(pptx):
        errors.append("ppt_asset_audit.json PPTX SHA-256 mismatch")
    counts = [
        audit.get("declared_assets"),
        audit.get("inserted_assets"),
        audit.get("census_crop_assets"),
    ]
    if not all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in counts
    ) or len(set(counts)) != 1:
        errors.append(
            "ppt_asset_audit.json crop counts must satisfy "
            "declared_assets == inserted_assets == census_crop_assets"
        )
    return errors


def validate_v595_postbuild_release(
    project_dir: str | Path,
    pptx_path: str | Path,
    brief: dict,
) -> list[str]:
    if not _is_v595(brief):
        return []
    project = Path(project_dir).resolve()
    pptx = Path(pptx_path).resolve()
    path = project / ".build" / "postbuild_release.json"
    if not path.is_file():
        return ["missing V5.9.5+ artifact: .build/postbuild_release.json"]
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"could not read .build/postbuild_release.json: {exc}"]
    errors: list[str] = []
    if report.get("decision") != "package" or report.get("build_locked") is not True:
        errors.append("postbuild_release.json does not authorize packaging")
    if report.get("catastrophic_blocker_count") != 0:
        errors.append("postbuild_release.json contains catastrophic blockers")
    if not pptx.is_file() or report.get("pptx_sha256") != sha256_file(pptx):
        errors.append("postbuild_release.json PPTX SHA-256 mismatch")
    return errors


def validate_formal_blueprint_manifest(
    project_dir: str | Path,
    pptx_path: str | Path,
    expected_ids: list[str],
) -> list[str]:
    project_dir = Path(project_dir).resolve()
    pptx_path = Path(pptx_path).resolve()
    manifest_path = project_dir / ".build" / "formal_blueprint_manifest.json"
    if not manifest_path.is_file():
        return ["missing V5.8 artifact: .build/formal_blueprint_manifest.json"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("schema_version") not in {"5.8", "5.9"}:
        errors.append("formal blueprint manifest schema_version must be 5.8 or 5.9")
    if not pptx_path.is_file() or manifest.get("pptx_sha256") != sha256_file(pptx_path):
        errors.append("formal blueprint manifest PPTX SHA-256 mismatch")
    pages = manifest.get("pages", {})
    if sorted(pages) != expected_ids:
        errors.append(f"formal blueprint manifest must cover {expected_ids}; got {sorted(pages)}")
    for slide_id in expected_ids:
        page = pages.get(slide_id, {})
        draft_path = project_dir / str(page.get("design_draft_path", ""))
        render_path = project_dir / str(page.get("render_path", ""))
        formal_path = project_dir / str(page.get("formal_blueprint_path", ""))
        if not draft_path.is_file() or not render_path.is_file() or not formal_path.is_file():
            errors.append(f"{slide_id}: ImageGen draft, formal blueprint, or final render is missing")
            continue
        draft_hash = sha256_file(draft_path)
        render_hash = sha256_file(render_path)
        formal_hash = sha256_file(formal_path)
        if draft_hash != page.get("design_draft_sha256"):
            errors.append(f"{slide_id}: ImageGen design draft SHA-256 mismatch")
        if render_hash != page.get("render_sha256"):
            errors.append(f"{slide_id}: final render SHA-256 mismatch")
        if formal_hash != page.get("formal_blueprint_sha256"):
            errors.append(f"{slide_id}: formal blueprint SHA-256 mismatch")
        if formal_hash != draft_hash:
            errors.append(f"{slide_id}: formal blueprint must be byte-identical to the original ImageGen result")
    return errors


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


def _combined_mac_quality(project: Path) -> dict:
    quality_path = project / ".build" / "mac_quality_report.json"
    if not quality_path.is_file():
        raise ValueError("missing Mac quality report")
    mac = json.loads(quality_path.read_text(encoding="utf-8"))
    shared_path = project / ".build" / "quality_report.json"
    shared = (
        json.loads(shared_path.read_text(encoding="utf-8"))
        if shared_path.is_file()
        else {}
    )
    shared_warnings = list(shared.get("warnings", []))
    shared_blockers = list(shared.get("blockers", []))
    warnings = list(mac.get("warnings", [])) + shared_warnings
    errors = list(mac.get("errors", [])) + [
        str(item.get("message", item)) if isinstance(item, dict) else str(item)
        for item in shared_blockers
    ]
    blocker_count = int(
        shared.get("blocker_count", len(shared_blockers))
    ) + int(mac.get("blocker_count", len(mac.get("errors", []))))
    warning_count = int(
        shared.get("warning_count", len(shared_warnings))
    ) + int(mac.get("warning_count", len(mac.get("warnings", []))))
    mac_status = str(mac.get("status", "pass"))
    if blocker_count or mac_status == "blocked":
        status = "blocked"
    elif mac_status == "structurally_valid_unrendered":
        status = "structurally_valid_unrendered"
    elif warning_count or mac_status == "pass_with_warnings":
        status = "pass_with_warnings"
    else:
        status = "pass"
    return {
        **mac,
        "status": status,
        "ok": blocker_count == 0,
        "warnings": warnings,
        "errors": errors,
        "warning_count": warning_count,
        "blocker_count": blocker_count,
        "shared_quality_status": shared.get("status", "pass"),
    }


def validate_v59_delivery_status(project_dir: str | Path) -> dict:
    project = Path(project_dir).resolve()
    runtime = json.loads(
        (project / ".build" / "runtime_report.json").read_text(encoding="utf-8")
    )
    backend = runtime.get("builder_backend")
    if backend == "mac_python_pptx_v1":
        quality = _combined_mac_quality(project)
        if quality.get("shared_quality_status") == "blocked":
            raise ValueError("shared quality report blocks formal delivery")
        if quality.get("visual_verification") is not True:
            raise ValueError(
                "formal V5.9 delivery requires local visual verification"
            )
        if quality.get("status") not in {"pass", "pass_with_warnings"}:
            raise ValueError("Mac quality status does not allow formal delivery")
        return quality
    if backend == "windows_com_v584":
        quality_path = project / ".build" / "quality_report.json"
        if not quality_path.is_file():
            raise ValueError("missing Windows quality report")
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        if quality.get("status") not in {"pass", "pass_with_warnings"}:
            raise ValueError("Windows quality status does not allow formal delivery")
        return {"visual_verification": True, **quality}
    raise ValueError(f"unsupported V5.9 builder backend: {backend}")


def write_v59_loose_delivery(
    project_dir: str | Path,
    pptx_path: str | Path,
) -> dict:
    project = Path(project_dir).resolve()
    pptx = Path(pptx_path).resolve()
    if not pptx.is_file():
        raise FileNotFoundError(pptx)
    runtime = json.loads(
        (project / ".build" / "runtime_report.json").read_text(encoding="utf-8")
    )
    if runtime.get("builder_backend") != "mac_python_pptx_v1":
        raise ValueError("loose V5.9 delivery is only for the Mac backend")
    quality = _combined_mac_quality(project)
    if quality.get("status") != "structurally_valid_unrendered":
        raise ValueError(
            "loose V5.9 delivery requires structurally_valid_unrendered status"
        )
    destination = project / "output" / "quality_report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "structurally_valid_unrendered",
        "pptx": str(pptx),
        "quality_report": str(destination),
        "formal_zip_created": False,
    }


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


def _validate_v6_project(
    project_dir: Path, pptx_path: Path, generator_path: Path
) -> list[str]:
    errors: list[str] = []
    try:
        gate_path = Path(__file__).with_name("v6_blueprint_gate.py")
        spec = importlib.util.spec_from_file_location(
            "standard_report_v6_imagegen_gate_delivery",
            gate_path,
        )
        gate = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(gate)
        gate.assert_imagegen_invocation_gate(project_dir)
    except Exception as exc:
        errors.append(str(exc))
    try:
        brief = json.loads(
            (project_dir / "project_brief.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"V6 project brief is unreadable: {exc}"]
    mode = brief.get("construction_mode")
    if (
        brief.get("schema_version") != "6.0"
        or brief.get("pipeline_revision") != "6.0.0"
        or brief.get("production_mode") != "blueprint"
        or mode not in {"deconstruct", "bitmap"}
    ):
        errors.append("V6 project contract is invalid")
    runtime_path = project_dir / ".build" / "runtime_report.json"
    runtime = (
        json.loads(runtime_path.read_text(encoding="utf-8"))
        if runtime_path.is_file()
        else {}
    )
    if runtime.get("builder_backend") not in {
        "windows_com_v584",
        "mac_python_pptx_v2",
    }:
        errors.append("V6 builder_backend is missing or invalid")
    if runtime.get("construction_mode") != mode:
        errors.append("V6 runtime construction_mode differs from the brief")
    result_path = project_dir / ".build" / "pipeline_result.json"
    result = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.is_file()
        else {}
    )
    if (
        result.get("schema_version") != "6.0"
        or result.get("pipeline_revision") != "6.0.0"
        or result.get("construction_mode") != mode
        or result.get("builder_backend") != runtime.get("builder_backend")
        or result.get("ok") is not True
    ):
        errors.append("V6 pipeline_result metadata is missing or invalid")
    audit_name = (
        "deconstruction_editability_audit.json"
        if mode == "deconstruct"
        else "bitmap_pptx_audit.json"
    )
    audit_path = project_dir / ".build" / audit_name
    audit = (
        json.loads(audit_path.read_text(encoding="utf-8"))
        if audit_path.is_file()
        else {}
    )
    if (
        audit.get("ok") is not True
        or audit.get("status") != "pass"
        or audit.get("construction_mode") != mode
        or audit.get("builder_backend") != runtime.get("builder_backend")
        or audit.get("pptx_sha256") != sha256_file(pptx_path)
    ):
        errors.append(f"V6 mode-specific audit did not pass: {audit_name}")
    if mode == "deconstruct":
        precheck_path = project_dir / ".build" / "deconstruction_precheck.json"
        precheck = (
            json.loads(precheck_path.read_text(encoding="utf-8"))
            if precheck_path.is_file()
            else {}
        )
        if precheck.get("ok") is not True:
            errors.append("V6 deconstruction precheck did not pass")
    lock_path = project_dir / ".build" / "formal_blueprint_manifest.json"
    if not lock_path.is_file():
        errors.append("V6 formal_blueprint_manifest.json is missing")
    else:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        expected_ids = {
            f"S{index:02d}"
            for index in range(1, int(brief.get("requested_page_count", 0)) + 1)
        }
        if (
            lock.get("schema_version") != "6.0"
            or lock.get("pipeline_revision") != "6.0.0"
            or lock.get("construction_mode") != mode
            or not isinstance(lock.get("pages"), dict)
            or set(lock["pages"]) != expected_ids
        ):
            errors.append("V6 formal blueprint lock header or page set is invalid")
        else:
            for slide_id in sorted(expected_ids):
                record = lock["pages"].get(slide_id, {})
                path = project_dir / "blueprints" / f"{slide_id}.png"
                if (
                    record.get("formal_blueprint_path")
                    != f"blueprints/{slide_id}.png"
                    or not path.is_file()
                    or record.get("formal_blueprint_sha256") != sha256_file(path)
                ):
                    errors.append(f"{slide_id}: V6 formal blueprint lock is stale")
    if mode == "bitmap":
        contract_path = project_dir / ".build" / "bitmap_contract.json"
        if not contract_path.is_file():
            errors.append("V6 bitmap_contract.json is missing")
        else:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            if (
                contract.get("schema_version") != "6.0"
                or contract.get("pipeline_revision") != "6.0.0"
                or contract.get("construction_mode") != "bitmap"
            ):
                errors.append("V6 bitmap_contract.json header is invalid")
            elif (
                not isinstance(contract.get("pages"), dict)
                or set(contract["pages"])
                != {
                    f"S{index:02d}"
                    for index in range(
                        1, int(brief.get("requested_page_count", 0)) + 1
                    )
                }
            ):
                errors.append("V6 bitmap_contract.json pages are invalid")
            else:
                for slide_id, record in contract["pages"].items():
                    if not isinstance(record, dict):
                        errors.append(f"{slide_id}: V6 bitmap contract is invalid")
                        continue
                    asset_id = record.get("asset_id")
                    expected = f".build/assets/{slide_id}/{asset_id}.png"
                    path = project_dir / expected
                    if (
                        not isinstance(asset_id, str)
                        or record.get("asset_path") != expected
                        or not path.is_file()
                        or record.get("asset_sha256") != sha256_file(path)
                    ):
                        errors.append(f"{slide_id}: V6 bitmap asset lock is stale")
    if not pptx_path.is_file():
        errors.append("V6 PPTX is missing")
    if generator_path.parent != project_dir or generator_path.name != "generate_deck.py":
        errors.append("V6 generator must be <project>/generate_deck.py")
    compile_path = project_dir / ".build" / "compile_report.json"
    compile_report = (
        json.loads(compile_path.read_text(encoding="utf-8"))
        if compile_path.is_file()
        else {}
    )
    if (
        compile_report.get("schema_version") != "6.0"
        or compile_report.get("pipeline_revision") != "6.0.0"
        or compile_report.get("construction_mode") != mode
        or compile_report.get("builder_backend") != runtime.get("builder_backend")
        or compile_report.get("generator") != "generate_deck.py"
        or not generator_path.is_file()
        or compile_report.get("generator_sha256") != sha256_file(generator_path)
    ):
        errors.append("V6 generator does not match compile_report.json")
    try:
        compiler_path = Path(__file__).with_name("project_compiler.py")
        spec = importlib.util.spec_from_file_location(
            "standard_report_v6_delivery_provenance", compiler_path
        )
        compiler = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(compiler)
        expected = [
            f"S{index:02d}"
            for index in range(1, int(brief.get("requested_page_count", 0)) + 1)
        ]
        blueprints = compiler._validate_v6_blueprint_chain(
            project_dir, brief, expected
        )
        specs_name = (
            "page_specs.json"
            if mode == "deconstruct"
            else "bitmap_page_specs.json"
        )
        page_specs = json.loads(
            (project_dir / ".build" / specs_name).read_text(encoding="utf-8")
        )
        if set(page_specs) != set(expected):
            raise ValueError("V6 page spec set is invalid")
        if mode == "deconstruct":
            visual = json.loads(
                (project_dir / ".build" / "visual_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            compiler._validate_v6_deconstruct_assets(
                project_dir, expected, page_specs, visual
            )
        else:
            compiler._validate_v6_bitmap_assets(
                project_dir, expected, page_specs, blueprints
            )
    except Exception as exc:
        errors.append(f"V6 provenance/asset derivation validation failed: {exc}")
    return errors


def package_v6_delivery(
    project_dir: str | Path,
    pptx_path: str | Path,
    generator_path: str | Path,
    output_zip: str | Path,
) -> Path:
    """Package a V6 result as exactly PPTX, blueprints.zip, and py.zip."""

    project = Path(project_dir).resolve()
    pptx = Path(pptx_path).resolve()
    generator = Path(generator_path).resolve()
    output = Path(output_zip).resolve()
    errors = _validate_v6_project(project, pptx, generator)
    if errors:
        raise ValueError("V6 delivery validation failed:\n- " + "\n- ".join(errors))
    brief = json.loads((project / "project_brief.json").read_text(encoding="utf-8"))
    mode = str(brief["construction_mode"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ppt_v6_delivery_", dir=output.parent) as tmp:
        temporary = Path(tmp)
        py_zip = temporary / "py.zip"
        blueprints_zip = temporary / "blueprints.zip"
        bundle = temporary / output.name
        _write_py_zip(generator, py_zip)
        with ZipFile(blueprints_zip, "w", ZIP_DEFLATED) as archive:
            for path in sorted((project / "blueprints").glob("S[0-9][0-9].png")):
                archive.write(path, f"blueprints/{path.name}")
            lock_path = project / ".build" / "formal_blueprint_manifest.json"
            if lock_path.is_file():
                archive.write(lock_path, "formal_blueprint_manifest.json")
            if mode == "deconstruct":
                manifest_path = project / ".build" / "visual_manifest.json"
                if manifest_path.is_file():
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    for slide_id, page in manifest.get("pages", {}).items():
                        if not isinstance(page, dict):
                            continue
                        for visual in page.get("visuals", []):
                            if (
                                not isinstance(visual, dict)
                                or visual.get(
                                    "treatment", visual.get("disposition")
                                )
                                != "crop"
                            ):
                                continue
                            asset_id = visual.get("asset_id")
                            path = (
                                project
                                / ".build"
                                / "assets"
                                / str(slide_id)
                                / f"{asset_id}.png"
                            )
                            if isinstance(asset_id, str) and path.is_file():
                                archive.write(
                                    path, f"assets/{slide_id}/{asset_id}.png"
                                )
            else:
                contract_path = project / ".build" / "bitmap_contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                archive.write(contract_path, "bitmap_contract.json")
                for record in contract.get("pages", {}).values():
                    if not isinstance(record, dict):
                        continue
                    path = project / str(record.get("asset_path", ""))
                    if path.is_file():
                        archive.write(path, f"body/{path.name}")
        with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
            archive.write(pptx, pptx.name)
            archive.write(blueprints_zip, "blueprints.zip")
            archive.write(py_zip, "py.zip")
        verification = verify_delivery_zip(bundle, pptx.name)
        bundle.replace(output)
    record = {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "construction_mode": mode,
        "builder_backend": json.loads(
            (project / ".build" / "runtime_report.json").read_text(encoding="utf-8")
        )["builder_backend"],
        "zip_path": str(output),
        "zip_sha256": sha256_file(output),
        "pptx_sha256": sha256_file(pptx),
        "outer_entries": verification["outer_entries"],
    }
    (project / ".build" / "delivery_record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output


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


def validate_pptx_hash_bindings(
    pptx_path: str | Path,
    pipeline_result: dict,
    text_audit: dict,
) -> list[str]:
    pptx_path = Path(pptx_path)
    if not pptx_path.is_file():
        return ["PPTX is missing"]
    actual_hash = sha256_file(pptx_path)
    errors: list[str] = []
    if pipeline_result.get("pptx_sha256") != actual_hash:
        errors.append("pipeline_result.json PPTX SHA-256 mismatch")
    if text_audit.get("pptx_sha256") != actual_hash:
        errors.append("ppt_text_audit.json PPTX SHA-256 mismatch")
    return errors


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
            errors.extend(
                validate_packaging_visual_manifest(
                    contracts,
                    manifest,
                    brief,
                )
            )
            if schema_version == "5.7":
                errors.extend(contracts.validate_blueprint_visual_balance(page_specs, manifest))
            pages = manifest.get("pages", {})
            if sorted(pages) != expected_ids:
                errors.append(f"visual_manifest.json must cover {expected_ids}; got {sorted(pages)}")
            for slide_id in expected_ids:
                page = pages.get(slide_id, {})
                if schema_version in {"5.8", "5.9"}:
                    relative = page.get("design_draft_path")
                    draft_path = project_dir / relative if isinstance(relative, str) else None
                    if draft_path is None or not draft_path.is_file():
                        errors.append(f"{slide_id}: design draft is missing")
                        continue
                    if sha256_file(draft_path) != page.get("design_draft_sha256"):
                        errors.append(f"{slide_id}: design draft SHA-256 mismatch")
                else:
                    relative = page.get("blueprint_path")
                    blueprint_path = project_dir / relative if isinstance(relative, str) else None
                    if blueprint_path is None or not blueprint_path.is_file():
                        errors.append(f"{slide_id}: accepted blueprint is missing")
                        continue
                    if sha256_file(blueprint_path) != page.get("blueprint_sha256"):
                        errors.append(f"{slide_id}: accepted blueprint SHA-256 mismatch")
            if schema_version in {"5.8", "5.9"}:
                errors.extend(validate_formal_blueprint_manifest(project_dir, pptx_path, expected_ids))

    if pipeline_result.get("schema_version") != schema_version or pipeline_result.get("ok") is not True:
        errors.append(f"V{schema_version} pipeline_result.json must report ok=true")
    if pipeline_result.get("pages") != expected_count:
        errors.append(f"V{schema_version} pipeline result page count mismatch")
    audit_requirements = {"ppt_text_audit.json": "ok"}
    if schema_version not in {"5.8", "5.9"}:
        audit_requirements["ppt_skeleton_audit.json"] = "ok"
    if mode == "blueprint" and schema_version not in {"5.8", "5.9"}:
        audit_requirements.update({
            "ppt_asset_audit.json": "ok",
            "blueprint_fidelity.json": "passed",
            "blueprint_text_benchmark.json": "ok",
        })
    text_audit: dict = {}
    for filename, field in audit_requirements.items():
        audit_path = project_dir / ".build" / filename
        if not audit_path.is_file():
            errors.append(f"missing audit: .build/{filename}")
            continue
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if filename == "ppt_text_audit.json":
            text_audit = audit
        if audit.get(field) is not True:
            errors.append(f"audit did not pass: .build/{filename}")

    if schema_version in {"5.8", "5.9"}:
        errors.extend(validate_pptx_hash_bindings(pptx_path, pipeline_result, text_audit))
    if schema_version == "5.8":
        quality_path = project_dir / ".build" / "quality_report.json"
        if not quality_path.is_file():
            errors.append("missing V5.8 artifact: .build/quality_report.json")
        else:
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            revision = str(brief.get("pipeline_revision", ""))
            expected_skill_version = revision if revision in {"5.8.3", "5.8.4"} else "5.8.2"
            if quality.get("skill_version") != expected_skill_version:
                errors.append(
                    f"quality_report.json skill_version must be {expected_skill_version}"
                )
            quality_blockers = quality.get("blocker_count")
            if not isinstance(quality_blockers, int) or isinstance(quality_blockers, bool):
                errors.append("quality_report.json blocker_count must be an integer")
                quality_blockers = 1
            if quality.get("status") == "blocked" or quality_blockers > 0:
                errors.append("quality_report.json contains blocking issues")
        if pipeline_result.get("quality_status") not in {"pass", "pass_with_warnings"}:
            errors.append("V5.8 pipeline_result.json quality_status must allow delivery")
        pipeline_blockers = pipeline_result.get("blocker_count")
        if not isinstance(pipeline_blockers, int) or isinstance(pipeline_blockers, bool) or pipeline_blockers != 0:
            errors.append("V5.8 pipeline_result.json must report blocker_count=0")

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


def _validate_v58_project(project_dir: Path, pptx_path: Path, generator_path: Path) -> list[str]:
    return _validate_manifest_project(project_dir, pptx_path, generator_path, schema_version="5.8")


def _validate_v59_project(
    project_dir: Path,
    pptx_path: Path,
    generator_path: Path,
) -> list[str]:
    errors = _validate_manifest_project(
        project_dir, pptx_path, generator_path, schema_version="5.9"
    )
    brief = json.loads(
        (project_dir / "project_brief.json").read_text(encoding="utf-8")
    )
    if brief.get("pipeline_revision") in {"5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}:
        try:
            deck_meta = _read_literal_assignment(generator_path, "DECK_META")
        except (SyntaxError, ValueError) as exc:
            errors.append(f"could not read V5.9 contract hashes: {exc}")
        else:
            expected = deck_meta.get("contract_hashes")
            if not isinstance(expected, dict) or not expected:
                errors.append("V5.9 generator is missing contract hashes")
            else:
                errors.extend(validate_contract_hashes(project_dir, expected))
    try:
        validate_v59_delivery_status(project_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    errors.extend(validate_v594_asset_audit(project_dir, pptx_path, brief))
    errors.extend(validate_v595_postbuild_release(project_dir, pptx_path, brief))
    return errors


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

    wall_start = time.time()
    project_dir = Path(project_dir).resolve()
    pptx_path = Path(pptx_path).resolve()
    generator_path = Path(generator_path).resolve()
    output_zip = Path(output_zip).resolve()
    desktop_dir = Path(desktop_dir or (Path.home() / "Desktop")).resolve()
    if not pptx_path.is_file():
        raise FileNotFoundError(pptx_path)
    if not generator_path.is_file():
        raise FileNotFoundError(generator_path)
    if generator_path.parent != project_dir or generator_path.name != "generate_deck.py":
        raise ValueError("the project generator must be <project>/generate_deck.py")
    brief_path = project_dir / "project_brief.json"
    if not brief_path.is_file():
        raise FileNotFoundError(brief_path)
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    schema_version = brief.get("schema_version")
    if schema_version not in {"5.8", "5.9"} and output_zip.parent != desktop_dir:
        raise ValueError(f"final Direct Blueprint ZIP must be written directly to the desktop: {desktop_dir}")
    python_policy_errors = validate_project_python_policy(
        project_dir,
        generator_path,
        brief,
    )
    if python_policy_errors:
        raise ValueError("\n".join(python_policy_errors))
    mode = brief.get("production_mode")
    expected_page_count = brief.get("requested_page_count")
    blueprint_files = [
        path
        for path in (project_dir / "blueprints").rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ] if (project_dir / "blueprints").is_dir() else []
    if mode == "blueprint" and not blueprint_files:
        raise FileNotFoundError("no blueprint images found in <project>/blueprints")

    if schema_version == "5.9":
        validation_errors = _validate_v59_project(
            project_dir, pptx_path, generator_path
        )
    elif schema_version == "5.8":
        validation_errors = _validate_v58_project(project_dir, pptx_path, generator_path)
    elif schema_version == "5.7":
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
        "pptx_sha256": sha256_file(pptx_path),
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
    if brief.get("schema_version") == "5.8" and brief.get("pipeline_revision") in {"5.8.3", "5.8.4"}:
        timing_path = Path(__file__).with_name("v583_timing.py")
        spec = importlib.util.spec_from_file_location("standard_report_v583_timing_package", timing_path)
        timing = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(timing)
        timing.record_stage(
            project_dir,
            "package",
            wall_start,
            time.time(),
            ok=True,
            attempt_count=1,
        )
        timing.summarize_timing(project_dir)
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
