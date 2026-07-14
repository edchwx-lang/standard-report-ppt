from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import re
from pathlib import Path


def find_runtime_renderer() -> Path | None:
    root = Path.home() / ".codex" / "plugins" / "cache" / "openai-primary-runtime" / "presentations"
    candidates = sorted(
        root.glob("*/skills/presentations/container_tools/render_slides.py"), reverse=True
    )
    return candidates[0] if candidates else None


def render_slides(
    pptx_path: str | Path,
    output_dir: str | Path,
    timeout_seconds: int = 45,
) -> dict:
    pptx_path = Path(pptx_path)
    output_dir = Path(output_dir)
    renderer = find_runtime_renderer()
    if renderer is None:
        return {"ok": False, "warning": "bundled artifact-tool renderer not found"}
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("slide-*.png"):
        stale.unlink()
    env = os.environ.copy()
    # The bundled renderer resolves its Node packages from HOME. Some Codex
    # desktop shells set HOME to the workspace, while USERPROFILE still points
    # at the actual user runtime cache.
    env["HOME"] = str(Path.home())
    try:
        process = subprocess.run(
            [
                sys.executable,
                str(renderer),
                str(pptx_path),
                "--output_dir",
                str(output_dir),
                "--width",
                "1600",
                "--height",
                "900",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "warning": f"visual render timed out after {timeout_seconds}s"}
    images = sorted(
        path.name
        for path in output_dir.glob("slide-*.png")
        if path.is_file() and path.stat().st_size > 0
    )
    if process.returncode != 0:
        if images:
            return {
                "ok": True,
                "images": images,
                "warning": f"renderer exited non-zero ({process.returncode}) after producing usable images",
            }
        message = (process.stderr or process.stdout or "render failed").strip()
        return {"ok": False, "warning": message[-1200:]}
    return {"ok": bool(images), "images": images, "warning": None if images else "no images"}


def prepare_project_render_dir(project_dir: str | Path) -> Path:
    project_dir = Path(project_dir).resolve()
    rendered_root = (project_dir / ".build" / "rendered").resolve()
    if project_dir not in rendered_root.parents or rendered_root.parts[-2:] != (".build", "rendered"):
        raise ValueError(f"unsafe project render root: {rendered_root}")
    if rendered_root.exists():
        for child in rendered_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    current = rendered_root / "current"
    current.mkdir(parents=True, exist_ok=True)
    return current


def _exact_render_error(output_dir: Path, expected_page_count: int) -> tuple[list[str], str | None]:
    expected = [f"slide-{index}.png" for index in range(1, expected_page_count + 1)]
    actual = sorted(
        path.name
        for path in output_dir.glob("slide-*.png")
        if path.is_file() and path.stat().st_size > 0
    )
    if set(actual) == set(expected) and len(actual) == expected_page_count:
        return expected, None
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    return actual, (
        f"expected exactly {expected_page_count} rendered pages; "
        f"got {len(actual)}, missing={missing}, extra={extra}"
    )


def render_project(
    pptx_path: str | Path,
    project_dir: str | Path,
    *,
    expected_page_count: int,
    timeout_seconds: int = 45,
) -> dict:
    if expected_page_count <= 0:
        raise ValueError("expected_page_count must be positive")
    output_dir = prepare_project_render_dir(project_dir)
    result = render_slides(pptx_path, output_dir, timeout_seconds)
    result["output_dir"] = str(output_dir)
    if not result.get("ok"):
        return result
    actual, error = _exact_render_error(output_dir, expected_page_count)
    if error:
        return {
            "ok": False,
            "images": actual,
            "output_dir": str(output_dir),
            "warning": error,
        }
    mapped = []
    for index in range(1, expected_page_count + 1):
        source = output_dir / f"slide-{index}.png"
        destination = output_dir / f"S{index:02d}.png"
        source.replace(destination)
        mapped.append(destination.name)
    result["images"] = mapped
    return result


def render_batch(
    pptx_path: str | Path,
    project_dir: str | Path,
    slide_ids: list[str],
    *,
    timeout_seconds: int = 45,
) -> dict:
    if not slide_ids or len(slide_ids) > 5:
        raise ValueError("a Direct Blueprint working batch must contain one to five slide IDs")
    if len(set(slide_ids)) != len(slide_ids):
        raise ValueError("slide_ids must be unique")
    if any(re.fullmatch(r"S\d{2,3}", slide_id) is None for slide_id in slide_ids):
        raise ValueError("slide_ids must use SNN identifiers")
    indexes = [int(slide_id[1:]) for slide_id in slide_ids]
    if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
        raise ValueError("slide_ids must follow canonical consecutive order")
    project_dir = Path(project_dir).resolve()
    rendered_root = project_dir / ".build" / "rendered"
    current = rendered_root / "current"
    current.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="_batch_", dir=rendered_root) as temporary:
        temporary_dir = Path(temporary)
        result = render_slides(pptx_path, temporary_dir, timeout_seconds)
        result["output_dir"] = str(current)
        if not result.get("ok"):
            return result
        actual, error = _exact_render_error(temporary_dir, len(slide_ids))
        if error:
            return {
                "ok": False,
                "images": actual,
                "output_dir": str(current),
                "warning": error,
            }
        mapped = []
        for index, slide_id in enumerate(slide_ids, start=1):
            destination = current / f"{slide_id}.png"
            if destination.exists():
                destination.unlink()
            (temporary_dir / f"slide-{index}.png").replace(destination)
            mapped.append(destination.name)
        return {"ok": True, "images": mapped, "output_dir": str(current), "warning": result.get("warning")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded visual rendering through artifact-tool.")
    parser.add_argument("pptx", type=Path)
    parser.add_argument("output_dir", type=Path, nargs="?")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--expected", type=int)
    parser.add_argument("--slide-ids", help="Comma-separated SNN IDs for an active batch")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    if args.project:
        if args.slide_ids:
            slide_ids = [value.strip() for value in args.slide_ids.split(",") if value.strip()]
            payload = render_batch(
                args.pptx,
                args.project,
                slide_ids,
                timeout_seconds=args.timeout,
            )
        else:
            if args.expected is None:
                parser.error("--project requires --expected for a final full-deck render")
            payload = render_project(
                args.pptx,
                args.project,
                expected_page_count=args.expected,
                timeout_seconds=args.timeout,
            )
    else:
        if args.output_dir is None:
            parser.error("legacy rendering requires output_dir")
        payload = render_slides(args.pptx, args.output_dir, args.timeout)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload.get("ok") else 2)


if __name__ == "__main__":
    main()
