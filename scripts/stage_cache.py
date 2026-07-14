from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = "1.0"


def _files(paths: Iterable[str | Path]) -> list[tuple[str, Path]]:
    records: list[tuple[str, Path]] = []
    for index, raw in enumerate(paths):
        path = Path(raw)
        if path.is_dir():
            for child in sorted(item for item in path.rglob("*") if item.is_file()):
                records.append((f"{index}:{child.relative_to(path).as_posix()}", child))
        else:
            records.append((f"{index}:{path.name}", path))
    return records


def fingerprint(paths: Iterable[str | Path], *, salt: str = "") -> str:
    digest = hashlib.sha256()
    digest.update(salt.encode("utf-8"))
    for label, path in _files(paths):
        digest.update(label.encode("utf-8"))
        if not path.is_file():
            digest.update(b"<missing>")
            continue
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "stages": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": SCHEMA_VERSION, "stages": {}}
    if not isinstance(value, dict) or not isinstance(value.get("stages"), dict):
        return {"schema_version": SCHEMA_VERSION, "stages": {}}
    return value


def cache_hit(
    state_path: str | Path,
    stage: str,
    inputs: Iterable[str | Path],
    outputs: Iterable[str | Path],
    *,
    salt: str = "",
) -> bool:
    output_paths = [Path(path) for path in outputs]
    if not output_paths or not all(path.is_file() and path.stat().st_size > 0 for path in output_paths):
        return False
    state = _load_state(Path(state_path))
    record = state["stages"].get(stage)
    if not isinstance(record, dict):
        return False
    return record.get("fingerprint") == fingerprint(inputs, salt=salt)


def update_cache(
    state_path: str | Path,
    stage: str,
    inputs: Iterable[str | Path],
    outputs: Iterable[str | Path],
    *,
    salt: str = "",
) -> Path:
    state_path = Path(state_path)
    output_paths = [Path(path) for path in outputs]
    missing = [str(path) for path in output_paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError("stage outputs missing or empty: " + ", ".join(missing))
    state = _load_state(state_path)
    state["schema_version"] = SCHEMA_VERSION
    state["stages"][stage] = {
        "fingerprint": fingerprint(inputs, salt=salt),
        "outputs": [str(path) for path in output_paths],
        "updated_at_utc": time.time(),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(state_path)
    return state_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Check or update a content-addressed stage cache.")
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output", action="append", required=True, type=Path)
    parser.add_argument("--salt", default="")
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    if args.update:
        update_cache(args.state, args.stage, args.input, args.output, salt=args.salt)
        payload = {"stage": args.stage, "updated": True, "hit": True}
    else:
        payload = {
            "stage": args.stage,
            "updated": False,
            "hit": cache_hit(args.state, args.stage, args.input, args.output, salt=args.salt),
        }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
