from __future__ import annotations

import argparse
import importlib.util
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


SCHEMA_VERSION = "5.6"


def _contracts():
    path = Path(__file__).with_name("v56_contracts.py")
    spec = importlib.util.spec_from_file_location("standard_report_v56_contracts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def audit_pptx_text(pptx_path: str | Path) -> dict:
    pptx_path = Path(pptx_path)
    errors: list[str] = []
    pages = 0
    contracts = _contracts()
    with zipfile.ZipFile(pptx_path) as archive:
        slide_names = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=lambda value: int(re.search(r"\d+", value).group()),
        )
        pages = len(slide_names)
        for page_number, name in enumerate(slide_names, start=1):
            raw = archive.read(name)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError as exc:
                errors.append(f"S{page_number:02d}: invalid slide XML: {exc}")
                continue
            text = "".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
            errors.extend(contracts.scan_text_integrity(text, location=f"S{page_number:02d}"))
    return {"schema_version": SCHEMA_VERSION, "ok": not errors, "errors": errors, "pages": pages}


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

