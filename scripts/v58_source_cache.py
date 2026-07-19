from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "5.8"
MODERN_SCHEMA_VERSIONS = {"5.8", "5.9"}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_records(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        records.append(
            {
                "path": str(path),
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return sorted(records, key=lambda item: (item["name"].casefold(), item["path"].casefold()))


def source_set_sha256(paths: Iterable[str | Path]) -> str:
    payload = json.dumps(_source_records(paths), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_source_digest(
    project_dir: str | Path,
    sources: Iterable[str | Path],
    parsed_payload: dict[str, Any],
    *,
    schema_version: str = "5.8",
) -> Path:
    if schema_version not in MODERN_SCHEMA_VERSIONS:
        raise ValueError("source digest schema_version must be 5.8 or 5.9")
    project_dir = Path(project_dir).resolve()
    source_records = _source_records(sources)
    fingerprint = hashlib.sha256(
        json.dumps(source_records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    payload = {
        "schema_version": schema_version,
        "parsed_once": True,
        "source_set_sha256": fingerprint,
        "sources": source_records,
        "parsed_payload": parsed_payload,
    }
    destination = project_dir / ".build" / "source_digest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination


def load_source_digest(project_dir: str | Path, sources: Iterable[str | Path]) -> dict[str, Any] | None:
    path = Path(project_dir).resolve() / ".build" / "source_digest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if payload.get("schema_version") not in MODERN_SCHEMA_VERSIONS or payload.get("parsed_once") is not True:
        return None
    if payload.get("source_set_sha256") != source_set_sha256(sources):
        return None
    return payload


def validate_source_digest(project_dir: str | Path) -> list[str]:
    path = Path(project_dir).resolve() / ".build" / "source_digest.json"
    if not path.is_file():
        return ["V5.8 source digest is missing; parse and hash all source material exactly once before compilation"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"V5.8 source digest is unreadable: {exc}"]
    errors: list[str] = []
    if payload.get("schema_version") not in MODERN_SCHEMA_VERSIONS:
        errors.append("source digest schema_version must be 5.8 or 5.9")
    if payload.get("parsed_once") is not True:
        errors.append("source digest parsed_once must be true")
    if not isinstance(payload.get("sources"), list) or not payload["sources"]:
        errors.append("source digest must contain at least one hashed source")
    if not isinstance(payload.get("parsed_payload"), dict) or not payload["parsed_payload"]:
        errors.append("source digest must contain the canonical parsed_payload")
    fingerprint = payload.get("source_set_sha256")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        errors.append("source digest source_set_sha256 must be a SHA-256 hex digest")
    sources = payload.get("sources")
    current_records: list[dict[str, Any]] = []
    if isinstance(sources, list):
        for index, record in enumerate(sources):
            if not isinstance(record, dict):
                errors.append(f"source digest sources[{index}] must be a mapping")
                continue
            raw_path = record.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                errors.append(f"source digest sources[{index}] path is missing")
                continue
            source = Path(raw_path).expanduser()
            try:
                resolved = source.resolve(strict=True)
                if not resolved.is_file():
                    raise FileNotFoundError(resolved)
                current = {
                    "path": str(resolved),
                    "name": resolved.name,
                    "size": resolved.stat().st_size,
                    "sha256": sha256_file(resolved),
                }
            except (OSError, FileNotFoundError) as exc:
                errors.append(f"source file is missing or unreadable: {source}: {exc}")
                continue
            current_records.append(current)
            if record.get("size") != current["size"]:
                errors.append(f"source file size changed: {resolved}")
            if record.get("sha256") != current["sha256"]:
                errors.append(f"source file SHA-256 changed: {resolved}")
        current_records.sort(key=lambda item: (item["name"].casefold(), item["path"].casefold()))
        if current_records:
            current_fingerprint = hashlib.sha256(
                json.dumps(
                    current_records,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if isinstance(fingerprint, str) and fingerprint != current_fingerprint:
                errors.append("source digest source_set_sha256 does not match the current source files")
    return errors
