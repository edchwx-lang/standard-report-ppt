from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


SCHEMA_VERSION = "5.6"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contracts():
    path = Path(__file__).with_name("v56_contracts.py")
    spec = importlib.util.spec_from_file_location("standard_report_v56_contracts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _normalize_visible_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def audit_pptx_text(
    pptx_path: str | Path,
    *,
    slides: list[dict] | None = None,
    page_specs: dict | None = None,
    critical_only: bool = False,
) -> dict:
    pptx_path = Path(pptx_path)
    errors: list[str] = []
    warnings: list[str] = []
    pages = 0
    contracts = _contracts()
    with zipfile.ZipFile(pptx_path) as archive:
        slide_names = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=lambda value: int(re.search(r"\d+", value).group()),
        )
        pages = len(slide_names)
        by_id = {str(slide.get("slide_id")): slide for slide in slides or []}
        benchmark = None
        if slides is not None and page_specs is not None:
            benchmark_path = Path(__file__).with_name("v58_text_benchmark.py")
            spec = importlib.util.spec_from_file_location("standard_report_v58_ppt_text_literals", benchmark_path)
            benchmark = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(benchmark)
        for page_number, name in enumerate(slide_names, start=1):
            raw = archive.read(name)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError as exc:
                errors.append(f"S{page_number:02d}: invalid slide XML: {exc}")
                continue
            text = "".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
            errors.extend(contracts.scan_text_integrity(text, location=f"S{page_number:02d}"))
            slide_id = f"S{page_number:02d}"
            if benchmark is not None and slide_id in by_id:
                normalized_slide = _normalize_visible_text(text)
                slide = by_id[slide_id]
                critical_literals = [
                    value
                    for value in (
                        slide.get("chapter"),
                        slide.get("title"),
                        *slide.get("core_points", []),
                    )
                    if isinstance(value, str) and _normalize_visible_text(value)
                ]
                critical_normalized = {
                    _normalize_visible_text(value)
                    for value in critical_literals
                }
                for literal in benchmark.required_ppt_literals(
                    slide,
                    page_specs.get(slide_id, {}),
                ):
                    if _normalize_visible_text(literal) not in normalized_slide:
                        message = (
                            f"{slide_id}: canonical text missing from PPT XML: "
                            f"{literal!r}"
                        )
                        if (
                            critical_only
                            and _normalize_visible_text(literal)
                            not in critical_normalized
                        ):
                            warnings.append(message)
                        else:
                            errors.append(
                                f"{slide_id}: critical text missing from PPT XML: "
                                f"{literal!r}"
                                if critical_only
                                else message
                            )
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "pages": pages,
        "pptx_sha256": _sha256_file(pptx_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit PPTX text for encoding loss and placeholder runs.")
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_pptx_text(args.pptx)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
