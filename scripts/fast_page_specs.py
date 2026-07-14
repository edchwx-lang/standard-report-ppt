from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "5.7"
LABELS = {
    "global": "全球竞争格局",
    "localization": "国产化进展",
    "bottleneck": "核心瓶颈",
    "shenzhen": "深圳基础",
    "action": "建议行动",
}


def _technology_spec(slide: dict) -> dict:
    modules = slide["modules"]
    comparison = modules[0]
    metrics = [
        {"label": str(label), "value": f"{left} → {right}"}
        for label, left, right in comparison.get("metrics", [])
    ]
    elements: list[dict] = [
        {"type": "section_header", "box": [0.0, 0.04, 12.2, 0.32], "text": comparison.get("title", "")},
        {"type": "metric_strip", "box": [0.0, 0.39, 12.2, 0.63], "metrics": metrics},
    ]
    card_w, gap = 2.92, 0.17
    for index, module in enumerate(modules[1:5]):
        body = f"{module.get('headline', '')}\n\n{module.get('detail', '')}".strip()
        elements.append({
            "type": "text_card",
            "box": [index * (card_w + gap), 1.16, card_w, 3.25],
            "title": module.get("title", ""),
            "body": body,
        })
    return {"elements": elements}


def _value_chain_spec(slide: dict) -> dict:
    upstream, middle, downstream, focus = slide["modules"]
    elements: list[dict] = [
        {"type": "section_header", "box": [0.0, 0.04, 7.25, 0.32], "text": upstream.get("title", "")},
        {"type": "text", "box": [5.1, 0.08, 2.05, 0.24], "text": upstream.get("share", ""), "font_size": 9, "bold": True, "color": "#C00000", "align": 3},
    ]
    row_h = 0.77
    for index, pair in enumerate(upstream.get("groups", [])[:4]):
        label, detail = pair
        y = 0.45 + index * (row_h + 0.12)
        elements.extend([
            {"type": "text", "box": [0.0, y, 1.55, row_h], "text": label, "font_size": 8.2, "bold": True, "color": "#FFFFFF", "fill": "#7399C5", "align": 2},
            {"type": "text", "box": [1.55, y, 5.70, row_h], "text": detail, "font_size": 8.1, "line": "#D9D9D9"},
        ])
    right_x, right_w = 7.48, 4.72
    for index, module in enumerate((middle, downstream, focus)):
        elements.append({
            "type": "text_card",
            "box": [right_x, 0.04 + index * 1.40, right_w, 1.22],
            "title": module.get("title", ""),
            "body": module.get("detail", ""),
        })
    return {"elements": elements}


def _market_spec(slide: dict) -> dict:
    modules = slide["modules"]
    metrics = [
        {"label": item.get("title", ""), "value": item.get("value", ""), "note": item.get("note", "")}
        for item in modules[:3]
    ]
    chart = modules[3]
    data = [{"label": str(label), "value": float(value)} for label, value in chart.get("items", [])]
    landscape = modules[4]
    return {
        "elements": [
            {"type": "metric_strip", "box": [0.0, 0.04, 12.2, 0.72], "metrics": metrics},
            {"type": "section_header", "box": [0.0, 0.92, 8.35, 0.32], "text": chart.get("title", "")},
            {"type": "hbar_chart", "box": [0.0, 1.28, 8.35, 3.05], "data": data},
            {"type": "text_card", "box": [8.58, 0.92, 3.62, 3.41], "title": landscape.get("title", ""), "body": landscape.get("detail", "")},
        ]
    }


def _material_spec(slide: dict) -> dict:
    data = slide["modules"][0]
    metrics = [{"label": str(label), "value": str(value)} for label, value in data.get("metrics", [])]
    return {
        "elements": [
            {"type": "section_header", "box": [0.0, 0.04, 12.2, 0.32], "text": f"{data.get('name', '')}关键指标"},
            {"type": "metric_strip", "box": [0.0, 0.39, 12.2, 0.62], "metrics": metrics},
            {"type": "text_card", "box": [0.0, 1.15, 3.88, 1.65], "title": LABELS["global"], "body": data.get("global", "")},
            {"type": "text_card", "box": [4.16, 1.15, 3.88, 1.65], "title": LABELS["localization"], "body": f"{data.get('localization_text', '')}\n\n{data.get('value', '')}".strip()},
            {"type": "text_card", "box": [8.32, 1.15, 3.88, 1.65], "title": LABELS["bottleneck"], "body": data.get("bottleneck", "")},
            {"type": "text_card", "box": [0.0, 3.04, 5.95, 1.37], "title": LABELS["shenzhen"], "body": data.get("shenzhen", "")},
            {"type": "text_card", "box": [6.25, 3.04, 5.95, 1.37], "title": LABELS["action"], "body": data.get("action", "")},
        ]
    }


def build_page_specs(slides: list[dict]) -> dict[str, dict]:
    specs: dict[str, dict] = {}
    for slide in slides:
        slide_id = slide["slide_id"]
        page_type = slide.get("page_type")
        if page_type == "technology_overview":
            specs[slide_id] = _technology_spec(slide)
        elif page_type == "value_chain":
            specs[slide_id] = _value_chain_spec(slide)
        elif page_type == "market_overview":
            specs[slide_id] = _market_spec(slide)
        elif page_type == "material_analysis":
            specs[slide_id] = _material_spec(slide)
        else:
            cards = []
            for index, module in enumerate(slide.get("modules", [])[:4]):
                cards.append({
                    "type": "text_card",
                    "box": [(index % 2) * 6.15, (index // 2) * 2.18 + 0.04, 5.95, 1.98],
                    "title": module.get("title", module.get("name", "")),
                    "body": module.get("detail") or module.get("content", ""),
                })
            specs[slide_id] = {"elements": cards}
    return specs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic V5.7 fast-mode page specifications.")
    parser.add_argument("slides", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    slides = json.loads(args.slides.read_text(encoding="utf-8"))
    specs = build_page_specs(slides)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(specs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
