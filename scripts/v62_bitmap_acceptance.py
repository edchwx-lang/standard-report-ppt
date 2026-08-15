from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.2"
ACCEPTANCE_PATH = ".build/bitmap_acceptance.json"
MAX_BUILD_ATTEMPTS = 2
MINOR_CROP_REASON = "minor_crop_visual_gain"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read(project: Path) -> dict[str, Any] | None:
    path = project / ACCEPTANCE_PATH
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_acceptance(
    project_dir: str | Path,
    pptx_path: str | Path,
    *,
    bitmap_audit: dict[str, Any],
    build_attempt: int,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    pptx = Path(pptx_path).resolve()
    if not pptx.is_file():
        raise FileNotFoundError(pptx)
    blockers = bitmap_audit.get("blockers", [])
    if bitmap_audit.get("ok") is not True or blockers:
        raise ValueError("V6.2 bitmap acceptance requires a passing structural audit")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "construction_mode": "bitmap",
        "decision": "accept",
        "build_locked": True,
        "build_attempt": int(build_attempt),
        "pptx": str(pptx),
        "pptx_sha256": sha256_file(pptx),
        "catastrophic_blockers": [],
        "minor_crop_adjustment": "manual_only",
        "automatic_recrop_allowed": False,
        "policy": "first_structurally_valid_output_wins",
    }
    _write_json_atomic(project / ACCEPTANCE_PATH, payload)
    return payload


def write_catastrophic_failure(
    project_dir: str | Path,
    *,
    stage: str,
    message: str,
    build_attempt: int,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    blocker = {
        "code": "BITMAP_CATASTROPHIC_FAILURE",
        "stage": stage,
        "message": message,
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "construction_mode": "bitmap",
        "decision": "catastrophic_repair_required",
        "build_locked": False,
        "build_attempt": int(build_attempt),
        "catastrophic_blockers": [blocker],
        "minor_crop_adjustment": "manual_only",
        "automatic_recrop_allowed": False,
    }
    _write_json_atomic(project / ACCEPTANCE_PATH, payload)
    return payload


def locked_acceptance(
    project_dir: str | Path,
    pptx_path: str | Path,
) -> dict[str, Any] | None:
    project = Path(project_dir).resolve()
    pptx = Path(pptx_path).resolve()
    payload = _read(project)
    if payload is None or not pptx.is_file():
        return None
    if (
        payload.get("schema_version") == SCHEMA_VERSION
        and payload.get("construction_mode") == "bitmap"
        and payload.get("decision") == "accept"
        and payload.get("build_locked") is True
        and payload.get("pptx_sha256") == sha256_file(pptx)
    ):
        return payload
    return None


def rebuild_allowed(
    project_dir: str | Path,
    *,
    catastrophic_repair: bool,
    reason: str,
) -> bool:
    payload = _read(Path(project_dir).resolve())
    if payload is None:
        return not catastrophic_repair
    if payload.get("build_locked") is True:
        return False
    if reason == MINOR_CROP_REASON:
        return False
    return (
        catastrophic_repair
        and payload.get("decision") == "catastrophic_repair_required"
        and int(payload.get("build_attempt", MAX_BUILD_ATTEMPTS))
        < MAX_BUILD_ATTEMPTS
        and bool(payload.get("catastrophic_blockers"))
    )
