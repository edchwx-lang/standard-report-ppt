from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "5.8"
SKILL_VERSION = "5.8.3"


def _path(project_dir: str | Path) -> Path:
    return Path(project_dir).resolve() / ".build" / "pipeline_timing.json"


def _project_versions(project_dir: str | Path) -> tuple[str, str]:
    brief = Path(project_dir).resolve() / "project_brief.json"
    if brief.is_file():
        try:
            payload = json.loads(brief.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            payload = {}
        revision = str(payload.get("pipeline_revision", ""))
        schema = str(payload.get("schema_version", "5.8"))
        if schema == "5.9" and revision in {"5.9.0", "5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}:
            return "5.9", revision
        if revision in {"5.8.3", "5.8.4"}:
            return "5.8", revision
    return SCHEMA_VERSION, SKILL_VERSION


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("skill_version", SKILL_VERSION)
    payload.setdefault("run_id", uuid.uuid4().hex)
    payload.setdefault("started_epoch", time.time())
    payload.setdefault("stages", [])
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def initialize_timing(
    project_dir: str | Path,
    *,
    started_epoch: float | None = None,
    preserve: bool = True,
) -> dict[str, Any]:
    path = _path(project_dir)
    current_schema, current_version = _project_versions(project_dir)
    payload = _read(path) if preserve and path.is_file() else {
        "schema_version": current_schema,
        "skill_version": current_version,
        "run_id": uuid.uuid4().hex,
        "started_epoch": float(started_epoch if started_epoch is not None else time.time()),
        "stages": [],
    }
    if "started_epoch" not in payload:
        payload["started_epoch"] = float(started_epoch if started_epoch is not None else time.time())
    payload["skill_version"] = current_version
    payload["schema_version"] = current_schema
    _write(path, payload)
    return payload


def record_stage(
    project_dir: str | Path,
    stage: str,
    start_epoch: float,
    end_epoch: float,
    *,
    ok: bool,
    note: str = "",
    cache_hit: bool | None = None,
    attempt_count: int | None = None,
    retry_reason: str | None = None,
) -> dict[str, Any]:
    path = _path(project_dir)
    payload = _read(path)
    payload["schema_version"], payload["skill_version"] = _project_versions(project_dir)
    record: dict[str, Any] = {
        "stage": str(stage),
        "start_epoch": float(start_epoch),
        "end_epoch": float(end_epoch),
        "duration_seconds": round(float(end_epoch) - float(start_epoch), 3),
        "duration_minutes": round((float(end_epoch) - float(start_epoch)) / 60.0, 3),
        "ok": bool(ok),
        "note": str(note),
    }
    if cache_hit is not None:
        record["cache_hit"] = bool(cache_hit)
    if attempt_count is not None:
        record["attempt_count"] = int(attempt_count)
    if retry_reason is not None:
        record["retry_reason"] = str(retry_reason)
    payload["stages"].append(record)
    _write(path, payload)
    return record


def summarize_timing(
    project_dir: str | Path,
    *,
    ended_epoch: float | None = None,
) -> dict[str, Any]:
    path = _path(project_dir)
    payload = _read(path)
    payload["schema_version"], payload["skill_version"] = _project_versions(project_dir)
    ended = float(ended_epoch if ended_epoch is not None else time.time())
    started = float(payload.get("started_epoch", ended))
    active = sum(
        max(0.0, float(item.get("duration_seconds", 0.0)))
        for item in payload.get("stages", [])
        if isinstance(item, dict)
    )
    payload["ended_epoch"] = ended
    payload["wall_clock_seconds"] = round(max(0.0, ended - started), 3)
    payload["wall_clock_minutes"] = round(payload["wall_clock_seconds"] / 60.0, 3)
    payload["active_seconds"] = round(active, 3)
    payload["active_minutes"] = round(active / 60.0, 3)
    _write(path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Record V5.8.3/V5.8.4 pipeline stages outside the COM build loop.")
    parser.add_argument("project", type=Path)
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--stage")
    parser.add_argument("--start-epoch", type=float)
    parser.add_argument("--end-epoch", type=float)
    parser.add_argument("--cache-hit", action="store_true")
    parser.add_argument("--attempt-count", type=int)
    parser.add_argument("--retry-reason")
    args = parser.parse_args()
    if args.start:
        payload = initialize_timing(args.project, started_epoch=args.start_epoch)
    elif args.summary:
        payload = summarize_timing(args.project, ended_epoch=args.end_epoch)
    elif args.stage and args.start_epoch is not None and args.end_epoch is not None:
        record_stage(
            args.project,
            args.stage,
            args.start_epoch,
            args.end_epoch,
            ok=True,
            cache_hit=args.cache_hit,
            attempt_count=args.attempt_count,
            retry_reason=args.retry_reason,
        )
        payload = summarize_timing(args.project)
    else:
        parser.error("use --start, --summary, or --stage with both epoch values")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
