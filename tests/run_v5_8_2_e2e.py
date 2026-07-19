from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    pipeline = load_module("v582_e2e_pipeline", SKILL / "scripts" / "project_pipeline.py")
    benchmark = load_module("v582_e2e_benchmark", SKILL / "scripts" / "v58_text_benchmark.py")
    source_cache = load_module("v582_e2e_source_cache", SKILL / "scripts" / "v58_source_cache.py")
    pack = load_module("v582_e2e_pack", SKILL / "scripts" / "pack_delivery.py")

    with tempfile.TemporaryDirectory(prefix="standard_report_v582_e2e_") as directory:
        project = Path(directory) / "fresh_v582_project"
        project.mkdir()
        brief = {
            "schema_version": "5.8",
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "blueprint_engine": "direct",
            "confirmation_source": "test_explicit",
        }
        (project / "project_brief.json").write_text(
            json.dumps(brief, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        pipeline.init_project(project)

        draft_dir = project / ".build" / "design_drafts"
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft = draft_dir / "S01.png"
        image = Image.new("RGB", (1600, 900), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((50, 65, 1550, 155), fill="#1E386B")
        draw.rectangle((80, 275, 1000, 735), fill="#F5F5F5", outline="#3F628F", width=6)
        draw.rectangle((1040, 275, 1510, 735), fill="#EDEDED", outline="#7391B3", width=6)
        for index, height in enumerate((110, 185, 265)):
            x = 180 + index * 230
            draw.rectangle((x, 660 - height, x + 100, 660), fill=(63, 98, 143))
        draw.line((190, 575, 420, 500, 650, 390), fill="#C00000", width=8)
        image.save(draft)
        draft.with_suffix(".composition.json").write_text("{invalid crop metadata", encoding="utf-8")
        draft_hash = hashlib.sha256(draft.read_bytes()).hexdigest()

        slides = [
            {
                "slide_id": "S01",
                "chapter": "一、算力基础设施",
                "title": "AI服务器需求扩张带动核心部件持续升级",
                "core_points": ["■ 训练与推理负载增长推动带宽、功耗和散热能力同步升级。"],
                "source": "资料来源：V5.8.2 合成端到端测试",
                "page_number": 1,
                "density_profile": "adaptive",
                "visual_route": {
                    "data_kind": "time_series",
                    "data": [
                        {"label": "2023", "value": 100},
                        {"label": "2024", "value": 145},
                        {"label": "2025E", "value": 210},
                    ],
                },
                "visual_brief": {
                    "primary_expression": "line_chart",
                    "visual_story": "Show accelerating demand and explain the component implication",
                    "supporting_visuals": [],
                },
                "modules": [
                    {"module_id": "M01", "title": "需求趋势"},
                    {"module_id": "M02", "title": "投资含义"},
                ],
                "primary_visual_module_id": "M01",
                "evidence_inventory": [
                    {
                        "evidence_id": "E01",
                        "statement": "2023-2025E需求指数由100升至210",
                        "priority": "must_keep",
                        "module_id": "M01",
                    }
                ],
            }
        ]
        page_specs = {
            "S01": {
                "elements": [
                    {
                        "type": "line_chart",
                        "role": "primary_evidence",
                        "box": [0.2, 0.25, 7.7, 3.65],
                        "data": [
                            {"label": "2023", "value": 100},
                            {"label": "2024", "value": 145},
                            {"label": "2025E", "value": 210, "highlight": True, "fill": "#C00000"},
                        ],
                    },
                    {
                        "type": "text_card",
                        "box": [8.15, 0.25, 3.85, 3.65],
                        "title": "投资含义",
                        "body": "高带宽互连、先进封装与液冷材料的价值量随系统复杂度提升。",
                        "title_fill": "#7391B3",
                        "body_fill": "#EDEDED",
                    },
                    {
                        "type": "asset",
                        "box": [9.0, 2.75, 1.7, 0.75],
                        "asset_id": "A01",
                    },
                ]
            }
        }
        manifest = {
            "schema_version": "5.8",
            "pages": {
                "S01": {
                    "design_draft_path": ".build/design_drafts/S01.png",
                    "design_draft_sha256": draft_hash,
                    "imagegen_attempt_count": 1,
                    "transport_attempt_count": 1,
                    "visual_plan": [
                        {
                            "visual_id": "V01",
                            "kind": "pictogram",
                            "description": "AI server component symbol",
                        }
                    ],
                    "visual_reviewed": True,
                    "observed_candidate_count": 1,
                    "candidate_count": 1,
                    "visuals": [
                        {
                            "visual_id": "V01",
                            "asset_id": "A01",
                            "kind": "pictogram",
                            "description": "AI server component symbol",
                            "disposition": "crop",
                            "source_px": [1050, 300, 1200, 450],
                            "target_box_in": [9.0, 2.75, 1.7, 0.75],
                        }
                    ],
                }
            },
        }
        build = project / ".build"
        (build / "slides.json").write_text(json.dumps(slides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (build / "page_specs.json").write_text(json.dumps(page_specs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (build / "visual_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        source = project / "source.txt"
        source.write_text("V5.8.2 fresh end-to-end source material", encoding="utf-8")
        source_cache.write_source_digest(
            project,
            [source],
            {"source_text": source.read_text(encoding="utf-8")},
        )
        text_benchmark = benchmark.make_benchmark(slides, page_specs, {"S01": draft_hash})
        page = text_benchmark["pages"]["S01"]
        page["reviewed"] = True
        page["exact_match"] = False
        page["differences"] = [{"expected": "AI服务器", "observed": "AI伺服器"}]
        (build / "blueprint_text_benchmark.json").write_text(
            json.dumps(text_benchmark, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        output = project / "output" / "v582_e2e.pptx"
        result = pipeline.run_project(project, output)
        delivery = project / "delivery" / "v582_e2e.zip"
        pack.package_direct_delivery(
            project_dir=project,
            pptx_path=output,
            generator_path=project / "generate_deck.py",
            output_zip=delivery,
            desktop_dir=project / "not_the_output_directory",
        )
        quality = json.loads((build / "quality_report.json").read_text(encoding="utf-8"))
        assert result["ok"] is True
        assert result["blocker_count"] == 0
        assert result["quality_status"] in {"pass", "pass_with_warnings"}
        assert quality["skill_version"] == "5.8.2"
        assert quality["blocker_count"] == 0
        assert output.is_file() and output.stat().st_size > 0
        with zipfile.ZipFile(output) as archive:
            slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        assert "ASSET_FALLBACK_A01" in slide_xml
        assert (project / "blueprints" / "S01.png").read_bytes() == draft.read_bytes()
        assert delivery.is_file() and delivery.stat().st_size > 0
        print(
            json.dumps(
                {
                    "ok": True,
                    "quality_status": result["quality_status"],
                    "warning_count": result["warning_count"],
                    "blocker_count": result["blocker_count"],
                    "warning_codes": [item["code"] for item in quality["warnings"]],
                    "pptx_bytes": output.stat().st_size,
                    "zip_bytes": delivery.stat().st_size,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
