"""Audit the deterministic V5.6 PowerPoint skeleton and forbidden effects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED = {
    "SKEL_CHAPTER": ("Microsoft YaHei", 20.0),
    "SKEL_TITLE": ("Microsoft YaHei", 16.0),
    "SKEL_CORE": ("Microsoft YaHei", 12.0),
    "SKEL_SOURCE": ("Microsoft YaHei", 7.5),
    "SKEL_PAGE_NUMBER": ("Microsoft YaHei", 8.0),
}
ANCHOR_TOLERANCE_PT = 0.02 * 72.0
TOP_TOLERANCE_PT = 0.02 * 72.0
MIN_TITLE_CORE_GAP_PT = 0.06 * 72.0
EXPECTED_TOP_PT = {
    "SKEL_CHAPTER": 0.4 / 2.54 * 72.0,
    "SKEL_TITLE": 1.5 / 2.54 * 72.0,
    "SKEL_CORE": 2.7 / 2.54 * 72.0,
}


def audit_manifest(manifest: dict) -> dict:
    errors: list[str] = []
    for page in manifest.get("pages", []):
        page_no = page.get("page", "?")
        shapes = page.get("shapes", {})
        for name, (font_name, font_size) in EXPECTED.items():
            shape = shapes.get(name)
            if not shape:
                errors.append(f"page {page_no}: missing {name}")
                continue
            if shape.get("font_name") != font_name:
                errors.append(f"page {page_no}: {name} font must be {font_name}")
            if abs(float(shape.get("font_size", 0)) - font_size) > 0.2:
                errors.append(f"page {page_no}: {name} font size must be {font_size}")
            if name in EXPECTED_TOP_PT and abs(float(shape.get("top", -9999)) - EXPECTED_TOP_PT[name]) > TOP_TOLERANCE_PT:
                errors.append(f"page {page_no}: {name} top must be {EXPECTED_TOP_PT[name]:.4f} pt")
        anchors = [shapes.get(name, {}).get("left") for name in ("SKEL_CHAPTER", "SKEL_TITLE", "SKEL_CORE")]
        if all(value is not None for value in anchors) and max(anchors) - min(anchors) > ANCHOR_TOLERANCE_PT:
            errors.append(f"page {page_no}: top three layers do not share one left anchor")
        title = shapes.get("SKEL_TITLE", {})
        if title and title.get("alignment") != 1:
            errors.append(f"page {page_no}: page title must be left aligned")
        core = shapes.get("SKEL_CORE", {})
        if core:
            if core.get("dash_style") != 4:
                errors.append(f"page {page_no}: core border must use short dash style 4")
            if abs(float(core.get("line_weight", 0)) - 1.0) > 0.1:
                errors.append(f"page {page_no}: core border must be 1 pt")
        if title and core:
            gap = float(core.get("top", 0)) - (
                float(title.get("top", 0)) + float(title.get("height", 0))
            )
            if gap < MIN_TITLE_CORE_GAP_PT:
                errors.append(
                    f"page {page_no}: title-to-core gap must be at least "
                    f"{MIN_TITLE_CORE_GAP_PT:.2f} pt; got {gap:.2f} pt (overlap if negative)"
                )
        if page.get("forbidden_top_rules"):
            errors.append(f"page {page_no}: forbidden decorative top rule detected")
        if page.get("footer_separators"):
            errors.append(f"page {page_no}: footer separator detected")
        for effect in page.get("forbidden_effects", []):
            errors.append(
                f"page {page_no}: forbidden {effect.get('effect', 'effect')} on "
                f"{effect.get('shape', '?')}"
            )
    for effect in manifest.get("global_forbidden_effects", []):
        errors.append(
            f"{effect.get('scope', 'master/layout')}: forbidden "
            f"{effect.get('effect', 'effect')} on {effect.get('shape', '?')}"
        )
    return {"schema_version": "5.6", "ok": not errors, "errors": errors, "pages": len(manifest.get("pages", []))}


def _shape_effects(shape) -> list[str]:
    effects: list[str] = []
    try:
        if int(shape.Shadow.Visible) != 0:
            effects.append("shadow")
    except Exception:
        pass
    try:
        if int(shape.Reflection.Type) != 0:
            effects.append("reflection")
    except Exception:
        pass
    try:
        if float(shape.Glow.Radius) > 0:
            effects.append("glow")
    except Exception:
        pass
    try:
        if float(shape.SoftEdge.Radius) > 0:
            effects.append("soft_edge")
    except Exception:
        pass
    try:
        if int(shape.ThreeD.Visible) != 0:
            effects.append("3d")
    except Exception:
        pass
    return effects


def _collect_scope_effects(shapes, scope: str) -> list[dict]:
    records: list[dict] = []
    for index in range(1, shapes.Count + 1):
        shape = shapes(index)
        for effect in _shape_effects(shape):
            records.append({"scope": scope, "shape": str(shape.Name), "effect": effect})
    return records


def extract_manifest(pptx_path: str | Path) -> dict:
    import win32com.client

    app = win32com.client.DispatchEx("PowerPoint.Application")
    presentation = app.Presentations.Open(str(Path(pptx_path).resolve()), False, True, False)
    pages = []
    global_forbidden_effects = []
    try:
        for page_no in range(1, presentation.Slides.Count + 1):
            slide = presentation.Slides(page_no)
            shape_records = {}
            forbidden_top_rules = []
            footer_separators = []
            forbidden_effects = []
            slide_width = float(presentation.PageSetup.SlideWidth)
            for index in range(1, slide.Shapes.Count + 1):
                shape = slide.Shapes(index)
                name = str(shape.Name)
                record = {"left": float(shape.Left), "top": float(shape.Top), "width": float(shape.Width), "height": float(shape.Height)}
                if name in EXPECTED:
                    text_range = shape.TextFrame2.TextRange
                    record.update({
                        "font_name": str(text_range.Font.Name),
                        "font_size": float(text_range.Font.Size),
                        "alignment": int(text_range.ParagraphFormat.Alignment),
                        "dash_style": int(shape.Line.DashStyle) if shape.Line.Visible else None,
                        "line_weight": float(shape.Line.Weight) if shape.Line.Visible else 0.0,
                    })
                    shape_records[name] = record
                for effect in _shape_effects(shape):
                    forbidden_effects.append({"shape": name, "effect": effect})
                is_long_thin = float(shape.Width) >= slide_width * 0.45 and float(shape.Height) <= 10.0
                if is_long_thin and float(shape.Top) < 70.0 and name != "SKEL_TITLE":
                    forbidden_top_rules.append(record)
                if is_long_thin and float(shape.Top) > 500.0:
                    footer_separators.append(record)
            pages.append({
                "page": page_no,
                "shapes": shape_records,
                "forbidden_top_rules": forbidden_top_rules,
                "footer_separators": footer_separators,
                "forbidden_effects": forbidden_effects,
            })
        designs = getattr(presentation, "Designs", None)
        if designs is not None:
            for design_index in range(1, designs.Count + 1):
                master = designs(design_index).SlideMaster
                global_forbidden_effects.extend(
                    _collect_scope_effects(master.Shapes, f"master {design_index}")
                )
                for layout_index in range(1, master.CustomLayouts.Count + 1):
                    layout = master.CustomLayouts(layout_index)
                    global_forbidden_effects.extend(
                        _collect_scope_effects(
                            layout.Shapes,
                            f"master {design_index}/layout {layout_index}",
                        )
                    )
    finally:
        presentation.Close()
        app.Quit()
    return {"pages": pages, "global_forbidden_effects": global_forbidden_effects}


def audit_pptx(pptx_path: str | Path, output_path: str | Path | None = None) -> dict:
    result = audit_manifest(extract_manifest(pptx_path))
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit V5.6 PowerPoint skeleton geometry, typography, gaps, and effects.")
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_pptx(args.pptx, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
