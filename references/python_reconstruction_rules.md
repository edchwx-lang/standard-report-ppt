# Python reconstruction rules V5.6

## Architecture

- Initialize, compile, and run through `project_pipeline.py`.
- Treat UTF-8 manifests as source of truth; never hand-edit `generate_deck.py`.
- Compile one root generator with one thin page wrapper per final slide.
- Open PowerPoint once for the whole build and close it once.
- Cache each page independently from content, geometry, blueprint, asset, template, and runtime hashes.
- Put all visible text in `slides.json` or `page_specs.json`; runtime helpers contain no page labels.

## Blueprint reconstruction

- Use the composed accepted page as the visual benchmark.
- Record hierarchy, region order, asymmetry, area, alignment, and whitespace as literal page elements.
- Keep text, cards, tables, lines, arrows, and charts native and editable.
- Crop every non-native visual subject: pictogram, logo, photo, map, compound mark, decorative motif, chemical structure, device, product, or character.
- Follow the artificial-feed pattern: one subject, one explicit crop rectangle, one trimmed PNG, one contain-fit insertion.
- Never crop an icon group, labels, rule, or surrounding card together.
- Run one batch extraction before PowerPoint; do not crop during deck generation.
- Never use a whole blueprint or a large page crop as a slide background.

## Skeleton and typography

- Use the clean `company_template.pptx`; do not add masking rectangles or reference swatches.
- Name the five skeleton shapes `SKEL_CHAPTER`, `SKEL_TITLE`, `SKEL_CORE`, `SKEL_SOURCE`, and `SKEL_PAGE_NUMBER`.
- Chapter, title, and core tops are 0.4 cm, 1.5 cm, and 2.7 cm.
- Their text shares one left anchor, within 0.02 inches.
- Keep at least 0.06 inches between title-bar bottom and core-box top.
- Measure core text height, resize the box, and derive the body origin below it.
- Use 20/16/12 pt Microsoft YaHei for chapter/title/core. Body is 8–12 pt and source/page number 7–8 pt.
- Remove shadow, reflection, glow, soft edge, and 3D from slides, masters, and layouts before save.

## Fast mode

Fast mode skips ImageGen and the visual manifest. It still uses the same template, compiler, COM runtime, skeleton, effects cleanup, UTF-8 source audit, final PPTX XML text audit, rendering, and skeleton audit. Deterministic grids may be selected once when creating `page_specs.json`; the delivery runtime does not select layouts.

## Failure handling and timing

- Every subprocess has a 120-second ceiling and writes start/end/duration/status to `pipeline_timing.json`.
- A Word COM timeout falls back immediately to structural parsing.
- A changed page rebuilds only that page; unchanged blueprints and crops are reused.
- A text audit, crop audit, skeleton audit, or blueprint-fidelity failure blocks delivery.
- Do not retry an identical blocking command without changing the cause.

## Compatibility

`direct_project.py` and V5.5 state files are supported only for existing projects. New V5.6 projects do not create manual page state.
