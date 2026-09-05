from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.3"
RUNTIME_REVISION = "6.3.1"


def _load(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"v63_deconstruction_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _issue(code: str, slide_id: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "blocker",
        "stage": "v63_deconstruction_prebuild",
        "slide_id": slide_id,
        "message": message,
    }


def _formal_blueprint_hashes(
    project: Path, brief: dict[str, Any]
) -> tuple[dict[str, str], list[dict[str, str]]]:
    path = project / ".build" / "formal_blueprint_manifest.json"
    if not path.is_file():
        return {}, [_issue("V63_BLUEPRINT_LOCK_REQUIRED", "", str(path))]
    manifest = _read_json(path)
    expected = {
        f"S{index:02d}" for index in range(1, int(brief.get("requested_page_count", 0)) + 1)
    }
    pages = manifest.get("pages", {})
    if (
        manifest.get("schema_version") != "6.0"
        or manifest.get("pipeline_revision") != "6.0.0"
        or manifest.get("construction_mode") != "deconstruct"
        or not isinstance(pages, dict)
        or set(pages) != expected
    ):
        return {}, [_issue("V63_BLUEPRINT_LOCK_REQUIRED", "", "formal blueprint manifest is invalid")]
    hashes: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    for slide_id in sorted(expected):
        record = pages[slide_id]
        relative = record.get("formal_blueprint_path") if isinstance(record, dict) else None
        candidate = (project / str(relative)).resolve() if isinstance(relative, str) else None
        expected_hash = record.get("formal_blueprint_sha256") if isinstance(record, dict) else None
        if (
            candidate is None
            or project not in candidate.parents
            or not candidate.is_file()
            or _sha256(candidate) != expected_hash
        ):
            errors.append(_issue("V63_BLUEPRINT_LOCK_TAMPERED", slide_id, "formal blueprint file or hash mismatch"))
        else:
            hashes[slide_id] = str(expected_hash)
    return hashes, errors


def prepare_deconstruction(
    project_dir: str | Path,
    *,
    backend: str,
    template_path: str | Path,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    brief = _read_json(project / "project_brief.json")
    blockers: list[dict[str, str]] = []
    if (
        brief.get("schema_version") != "6.0"
        or brief.get("pipeline_revision") != "6.0.0"
        or brief.get("production_mode") != "blueprint"
        or brief.get("construction_mode") != "deconstruct"
    ):
        blockers.append(_issue("V63_DECONSTRUCTION_ONLY", "", "V6.3 requires locked V6 deconstruction mode"))
    hashes, lock_errors = _formal_blueprint_hashes(project, brief)
    blockers.extend(lock_errors)
    skeleton_contract: dict[str, Any] | None = None
    try:
        skeleton_contract = _load("v63_skeleton_contract").read_template_contract(template_path)
    except Exception as exc:
        blockers.append(_issue("V63_SKELETON_CONTRACT_INVALID", "", str(exc)))
    census_report: dict[str, Any] | None = None
    scene_report: dict[str, Any] | None = None
    asset_report: dict[str, Any] | None = None
    census_path = project / ".build" / "v63_visual_census.json"
    scene_path = project / ".build" / "v63_scene_graph.json"
    if not census_path.is_file():
        blockers.append(_issue("V63_CENSUS_MISSING", "", str(census_path)))
    else:
        census_report = _load("v63_visual_census").validate_visual_census(
            project, _read_json(census_path)
        )
        blockers.extend(census_report.get("blockers", []))
    if not scene_path.is_file():
        blockers.append(_issue("V63_SCENE_GRAPH_MISSING", "", str(scene_path)))
    elif census_report is not None and census_report.get("ok"):
        scene_report = _load("v63_scene_graph").validate_scene_graph(
            project, _read_json(scene_path)
        )
        blockers.extend(scene_report.get("blockers", []))
    if not blockers:
        asset_report = _load("v63_extract_scene_assets").extract_scene_assets(project)
        blockers.extend(asset_report.get("blockers", []))
    cache_payload = None
    if not lock_errors and not blockers:
        cache_payload = _load("v6_contracts").v63_post_lock_cache_payload(
            brief, backend, hashes
        )
    report = {
        "schema_version": SCHEMA_VERSION,
        "deconstruction_runtime_revision": RUNTIME_REVISION,
        "construction_mode": "deconstruct",
        "builder_backend": backend,
        "ok": not blockers,
        "status": "pass" if not blockers else "blocked",
        "formal_blueprint_hashes": hashes,
        "skeleton_contract": skeleton_contract,
        "census": census_report,
        "scene_graph": scene_report,
        "assets": asset_report,
        "cache_payload": cache_payload,
        "blockers": blockers,
    }
    _write_json_atomic(project / ".build" / "v63_deconstruction_precheck.json", report)
    return report
