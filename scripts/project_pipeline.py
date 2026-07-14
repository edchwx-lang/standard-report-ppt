from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = "5.7"
SUPPORTED_SCHEMA_VERSIONS = {"5.6", "5.7"}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _timing_path(project_dir: Path) -> Path:
    return project_dir / ".build" / "pipeline_timing.json"


def _project_schema_version(project_dir: Path) -> str:
    brief_path = project_dir / "project_brief.json"
    if brief_path.is_file():
        try:
            version = _read_json(brief_path).get("schema_version")
            if version in SUPPORTED_SCHEMA_VERSIONS:
                return version
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return SCHEMA_VERSION


def _record_timing(project_dir: Path, stage: str, start: float, end: float, *, ok: bool, note: str = "") -> None:
    path = _timing_path(project_dir)
    payload = _read_json(path) if path.is_file() else {"schema_version": _project_schema_version(project_dir), "stages": []}
    payload["stages"].append({
        "stage": stage,
        "start_epoch": start,
        "end_epoch": end,
        "duration_seconds": round(end - start, 3),
        "ok": ok,
        "note": note,
    })
    _write_json_atomic(path, payload)


def _stage(project_dir: Path, name: str, action: Callable[[], Any]) -> Any:
    start = time.time()
    try:
        result = action()
    except Exception as exc:
        _record_timing(project_dir, name, start, time.time(), ok=False, note=str(exc))
        raise
    _record_timing(project_dir, name, start, time.time(), ok=True)
    return result


def validate_brief(brief: dict) -> list[str]:
    errors: list[str] = []
    if brief.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"schema_version must be one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    count = brief.get("requested_page_count")
    if not isinstance(count, int) or count <= 0:
        errors.append("requested_page_count must be a positive integer")
    mode = brief.get("production_mode")
    if mode not in {"blueprint", "fast"}:
        errors.append("production_mode must be blueprint or fast")
    if mode == "blueprint" and brief.get("blueprint_engine") != "direct":
        errors.append("blueprint mode requires blueprint_engine=direct")
    return errors


def preflight_project(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir).resolve()
    skill_dir = Path(__file__).resolve().parent.parent
    brief_path = project_dir / "project_brief.json"
    if not brief_path.is_file():
        raise FileNotFoundError(brief_path)
    brief = _read_json(brief_path)
    errors = validate_brief(brief)
    if errors:
        raise ValueError("; ".join(errors))

    required = [
        skill_dir / "assets" / "company_template.pptx",
        skill_dir / "assets" / "direct_blueprint_generator_template.py",
        skill_dir / "scripts" / "project_compiler.py",
        skill_dir / "scripts" / "v56_contracts.py",
        skill_dir / "scripts" / "v56_page_cache.py",
        skill_dir / "scripts" / "render_slides.py",
        skill_dir / "scripts" / "ppt_text_audit.py",
        skill_dir / "scripts" / "ppt_skeleton_audit.py",
        skill_dir / "scripts" / "pack_delivery.py",
    ]
    if brief["production_mode"] == "blueprint":
        required.extend([
            skill_dir / "scripts" / "compose_blueprint.py",
            skill_dir / "scripts" / "extract_direct_assets.py",
            skill_dir / "scripts" / "ppt_asset_audit.py",
            skill_dir / "scripts" / "blueprint_fidelity.py",
        ])
    missing = [str(path.relative_to(skill_dir)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing manifest-pipeline resources: " + ", ".join(missing))

    for path in required:
        if path.suffix == ".py":
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    packager = _load_module("standard_report_packager_preflight", skill_dir / "scripts" / "pack_delivery.py")
    validator = "_validate_v57_project" if brief["schema_version"] == "5.7" else "_validate_v56_project"
    if not hasattr(packager, validator):
        raise RuntimeError(f"pack_delivery.py does not provide native {brief['schema_version']} validation")

    app = None
    presentation = None
    try:
        import win32com.client

        app = win32com.client.DispatchEx("PowerPoint.Application")
        presentation = app.Presentations.Open(
            str(skill_dir / "assets" / "company_template.pptx"), False, True, False
        )
        if presentation.PageSetup.SlideWidth <= 0 or presentation.PageSetup.SlideHeight <= 0:
            raise RuntimeError("company template has invalid slide dimensions")
    finally:
        if presentation is not None:
            presentation.Close()
        if app is not None:
            app.Quit()

    return {
        "schema_version": brief["schema_version"],
        "ok": True,
        "mode": brief["production_mode"],
        "checks": ["brief", "resources", "python_syntax", "v56_packager", "powerpoint_template"],
    }


def init_project(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir).resolve()
    brief_path = project_dir / "project_brief.json"
    if not brief_path.is_file():
        raise FileNotFoundError(brief_path)
    brief = _read_json(brief_path)
    errors = validate_brief(brief)
    if errors:
        raise ValueError("; ".join(errors))
    directories = [".build", ".build/pages", ".build/rendered/current", "output"]
    if brief["production_mode"] == "blueprint":
        directories.extend(["blueprints", ".build/raw_blueprints", ".build/assets"])
    for relative in directories:
        (project_dir / relative).mkdir(parents=True, exist_ok=True)
    timing = {"schema_version": brief["schema_version"], "stages": []}
    _write_json_atomic(_timing_path(project_dir), timing)
    return {"schema_version": brief["schema_version"], "project": str(project_dir), "mode": brief["production_mode"]}


def compile_project(project_dir: str | Path) -> Path:
    project_dir = Path(project_dir).resolve()
    compiler = _load_module("standard_report_v56_compiler_pipeline", Path(__file__).with_name("project_compiler.py"))
    return _stage(project_dir, "compile", lambda: compiler.compile_project(project_dir))


def _run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )


def _audit_ok(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        value = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return bool(value.get("ok", value.get("passed", False)))


def _page_cache_status(project_dir: Path, page_count: int) -> tuple[Any, Path, list[str], bool]:
    cache = _load_module("standard_report_v56_page_cache_pipeline", Path(__file__).with_name("v56_page_cache.py"))
    state_path = project_dir / ".build" / "page_cache.json"
    slide_ids = [f"S{index:02d}" for index in range(1, page_count + 1)]
    all_hit = all(
        cache.page_cache_hit(
            state_path,
            slide_id,
            [project_dir / ".build" / "pages" / f"{slide_id}.input.json"],
            [project_dir / ".build" / "rendered" / "current" / f"{slide_id}.png"],
            salt=_project_schema_version(project_dir),
        )
        for slide_id in slide_ids
    )
    return cache, state_path, slide_ids, all_hit


def run_project(project_dir: str | Path, output_path: str | Path | None = None) -> dict:
    project_dir = Path(project_dir).resolve()
    brief = _read_json(project_dir / "project_brief.json")
    errors = validate_brief(brief)
    if errors:
        raise ValueError("; ".join(errors))
    skill_dir = Path(__file__).resolve().parents[1]
    generator = compile_project(project_dir)
    output = Path(output_path) if output_path else project_dir / "output" / "report.pptx"
    cache, cache_state, slide_ids, all_pages_cached = _page_cache_status(
        project_dir, brief["requested_page_count"]
    )
    common_audits_ok = _audit_ok(project_dir / ".build" / "ppt_text_audit.json") and _audit_ok(
        project_dir / ".build" / "ppt_skeleton_audit.json"
    )
    blueprint_audits_ok = True
    if brief["production_mode"] == "blueprint":
        blueprint_audits_ok = (
            _audit_ok(project_dir / ".build" / "direct_asset_report.json")
            and _audit_ok(project_dir / ".build" / "ppt_asset_audit.json")
            and _audit_ok(project_dir / ".build" / "blueprint_fidelity.json")
        )
    if output.is_file() and all_pages_cached and common_audits_ok and blueprint_audits_ok:
        now = time.time()
        _record_timing(project_dir, "full_deck_cache", now, now, ok=True, note="all page fingerprints and audits matched")
        result = {
            "schema_version": brief["schema_version"],
            "ok": True,
            "cached": True,
            "pptx": str(output),
            "pages": brief["requested_page_count"],
            "timing": str(_timing_path(project_dir)),
        }
        _write_json_atomic(project_dir / ".build" / "pipeline_result.json", result)
        return result
    if brief["production_mode"] == "blueprint":
        _stage(
            project_dir,
            "extract_assets",
            lambda: _run([
                sys.executable,
                str(skill_dir / "scripts" / "extract_direct_assets.py"),
                "--project",
                str(project_dir),
                "--generator",
                str(generator),
            ]),
        )
    _stage(
        project_dir,
        "build",
        lambda: _run([sys.executable, str(generator), "--output", str(output)], timeout=120),
    )
    _stage(
        project_dir,
        "render",
        lambda: _run([
            sys.executable,
            str(skill_dir / "scripts" / "render_slides.py"),
            str(output),
            "--project",
            str(project_dir),
            "--expected",
            str(brief["requested_page_count"]),
            "--timeout",
            "45",
        ], timeout=120),
    )
    text_audit = _load_module("standard_report_v56_text_pipeline", skill_dir / "scripts" / "ppt_text_audit.py")
    text_result = _stage(project_dir, "text_audit", lambda: text_audit.audit_pptx_text(output))
    _write_json_atomic(project_dir / ".build" / "ppt_text_audit.json", text_result)
    if not text_result["ok"]:
        raise ValueError("PPT text audit failed: " + "; ".join(text_result["errors"]))
    _stage(
        project_dir,
        "skeleton_audit",
        lambda: _run([
            sys.executable,
            str(skill_dir / "scripts" / "ppt_skeleton_audit.py"),
            str(output),
            "--output",
            str(project_dir / ".build" / "ppt_skeleton_audit.json"),
        ]),
    )
    if brief["production_mode"] == "blueprint":
        _stage(
            project_dir,
            "asset_audit",
            lambda: _run([
                sys.executable,
                str(skill_dir / "scripts" / "ppt_asset_audit.py"),
                str(output),
                "--project",
                str(project_dir),
                "--generator",
                str(generator),
                "--output",
                str(project_dir / ".build" / "ppt_asset_audit.json"),
            ]),
        )
        fidelity = _load_module("standard_report_v56_fidelity_pipeline", skill_dir / "scripts" / "blueprint_fidelity.py")
        page_pairs = []
        for index in range(1, brief["requested_page_count"] + 1):
            slide_id = f"S{index:02d}"
            page_pairs.append((slide_id, project_dir / "blueprints" / f"{slide_id}.png", project_dir / ".build" / "rendered" / "current" / f"{slide_id}.png"))
        fidelity_result = _stage(project_dir, "fidelity", lambda: fidelity.compare_deck(page_pairs, expected_page_count=brief["requested_page_count"]))
        _write_json_atomic(project_dir / ".build" / "blueprint_fidelity.json", fidelity_result)
        if not fidelity_result["passed"]:
            raise ValueError("blueprint fidelity failed: " + ", ".join(fidelity_result["failed_slide_ids"]))
    for slide_id in slide_ids:
        cache.update_page_cache(
            cache_state,
            slide_id,
            [project_dir / ".build" / "pages" / f"{slide_id}.input.json"],
            [project_dir / ".build" / "rendered" / "current" / f"{slide_id}.png"],
            salt=brief["schema_version"],
        )
    result = {
        "schema_version": brief["schema_version"],
        "ok": True,
        "pptx": str(output),
        "pages": brief["requested_page_count"],
        "timing": str(_timing_path(project_dir)),
    }
    _write_json_atomic(project_dir / ".build" / "pipeline_result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="V5.7 manifest-driven PowerPoint project pipeline.")
    parser.add_argument("project", type=Path)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--preflight", action="store_true")
    actions.add_argument("--init", action="store_true")
    actions.add_argument("--compile", action="store_true")
    actions.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.preflight:
        payload = preflight_project(args.project)
    elif args.init:
        payload = init_project(args.project)
    elif args.compile:
        payload = {"schema_version": SCHEMA_VERSION, "generator": str(compile_project(args.project))}
    else:
        payload = run_project(args.project, args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
