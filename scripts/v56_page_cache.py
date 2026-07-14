from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = "5.6"


def fingerprint(paths: Iterable[str | Path], *, salt: str = "") -> str:
    digest = hashlib.sha256(salt.encode("utf-8"))
    for path in sorted((Path(item) for item in paths), key=lambda item: item.as_posix()):
        digest.update(path.name.encode("utf-8"))
        if not path.is_file():
            digest.update(b"<missing>")
            continue
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _load(path: Path) -> dict:
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "pages": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != SCHEMA_VERSION or not isinstance(value.get("pages"), dict):
        return {"schema_version": SCHEMA_VERSION, "pages": {}}
    return value


def page_cache_hit(
    state_path: str | Path,
    slide_id: str,
    inputs: Iterable[str | Path],
    outputs: Iterable[str | Path],
    *,
    salt: str = "",
) -> bool:
    output_paths = [Path(path) for path in outputs]
    if not output_paths or not all(path.is_file() and path.stat().st_size > 0 for path in output_paths):
        return False
    record = _load(Path(state_path))["pages"].get(slide_id)
    return isinstance(record, dict) and record.get("fingerprint") == fingerprint(inputs, salt=salt)


def update_page_cache(
    state_path: str | Path,
    slide_id: str,
    inputs: Iterable[str | Path],
    outputs: Iterable[str | Path],
    *,
    salt: str = "",
) -> Path:
    state_path = Path(state_path)
    output_paths = [Path(path) for path in outputs]
    if not output_paths or not all(path.is_file() and path.stat().st_size > 0 for path in output_paths):
        raise FileNotFoundError("page cache outputs are missing or empty")
    state = _load(state_path)
    state["pages"][slide_id] = {
        "fingerprint": fingerprint(inputs, salt=salt),
        "outputs": [str(path) for path in output_paths],
        "updated_at_utc": time.time(),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(state_path)
    return state_path

