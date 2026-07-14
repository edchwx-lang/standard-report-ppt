from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(project_dir: Path) -> dict:
    records = []
    allowed = {".json", ".md", ".png", ".jpg", ".jpeg", ".pptx"}
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        if path.name in {"project_manifest.json", ".stage_cache.json"}:
            continue
        if any(part in {"tmp", "output", "__pycache__"} for part in path.parts):
            continue
        stat = path.stat()
        records.append(
            {
                "path": path.relative_to(project_dir).as_posix(),
                "sha256": sha256(path),
                "size": stat.st_size,
            }
        )
    canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": "4.0",
        "manifest_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "files": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic stage manifest.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.project_dir / "project_manifest.json"
    output.write_text(
        json.dumps(build_manifest(args.project_dir), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
