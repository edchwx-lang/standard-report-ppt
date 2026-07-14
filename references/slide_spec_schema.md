# V5.6 compiled project contract

All JSON and Python source files use UTF-8 without encoding fallback.

## Project inputs

`project_brief.json` records the confirmed mode and final page count:

```json
{
  "schema_version": "5.6",
  "requested_page_count": 3,
  "page_mapping": [],
  "production_mode": "blueprint",
  "blueprint_engine": "direct",
  "confirmation_source": "user_explicit"
}
```

Both modes use the same manifest workspace:

- `.build/slides.json`: canonical content and evidence;
- `.build/page_specs.json`: literal page elements and coordinates;
- `.build/visual_manifest.json`: blueprint provenance and bounded crops;
- `.build/page_cache.json`: content-addressed per-page cache;
- `.build/pipeline_timing.json`: measured stage durations.

V5.6 does not create or consume `direct_blueprint_state.json`. State is derived from hashes of real inputs and outputs.

## Canonical slides

`slides.json` is an ordered list with exact `S01`–`SNN` coverage. Each slide contains chapter, title, one or two core points, source, page type, layout intent, medium density, modules, primary visual module, and evidence inventory.

Rules:

- Core points total 80–160 non-whitespace characters and do not include the visible square bullet.
- Every `must_keep` item and at least 80% of `must_keep + supporting` evidence maps to a real module.
- Internal IDs are never visible.
- Numbering appears only for a real sequence, stage, rank, or ordered method.
- No string may contain `???`, U+FFFD, C1 controls, or recognized mojibake sequences.

## Page specifications

`page_specs.json` contains exact slide IDs and literal geometry:

```json
{
  "S01": {
    "elements": [
      {"type": "section_header", "box": [0.55, 3.05, 5.2, 0.34], "text": "市场格局"},
      {"type": "text", "box": [0.65, 3.55, 4.7, 0.55], "text": "全球需求持续扩张"}
    ]
  }
}
```

The compiler emits one thin `build_slide_SNN` wrapper per page. Runtime helpers render only the literal elements; they do not select, cycle, or infer layouts.

## Blueprint visual manifest

Blueprint mode requires one manifest page per slide:

```json
{
  "schema_version": "5.6",
  "pages": {
    "S01": {
      "blueprint_path": "blueprints/S01.png",
      "blueprint_sha256": "<64 lowercase hex>",
      "candidate_count": 1,
      "visuals": [
        {
          "asset_id": "S01_A01",
          "kind": "pictogram",
          "description": "independent factory pictogram",
          "disposition": "crop",
          "source_px": [120, 410, 340, 650],
          "target_box_in": [0.75, 3.25, 1.55, 1.65],
          "fit_mode": "contain",
          "padding_px": 4
        }
      ]
    }
  }
}
```

Photos, logos, maps, pictograms, compound marks, decorative motifs, chemical structures, devices, products, and characters always use `crop`. Native rebuild is limited to text, rectangles, lines, arrows, ovals, charts, tables, and allowlisted primitive recipes.

If `candidate_count > 0`, zero crops is invalid. One independent subject equals one asset ID, one crop rectangle, one extracted PNG, and one insertion. Crop rectangles must stay in the body and exclude neighboring text, borders, and other subjects.

## Compiled generator

`project_compiler.py` produces the only root Python file, `generate_deck.py`. It contains `DECK_META`, `SLIDES`, `PAGE_SPECS`, derived `BLUEPRINTS`, derived `ASSET_CROPS`, one wrapper per slide, `PAGE_BUILDERS`, and `build_deck()`.

The generator is deterministic and must not be hand-edited. A manifest change invalidates only affected page cache entries; a template or runtime change invalidates all pages.

## Legacy compatibility

V5.5 direct-state projects remain readable by `direct_project.py`. That script is compatibility-only and is not the entry point for new V5.6 projects.
