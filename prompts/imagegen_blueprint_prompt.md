# Per-page ImageGen design-draft prompt V5.9

For V5.9, use the real first slide as the only ImageGen capability probe.
Do not generate a circle or other throwaway image. Import every returned
artifact through `v59_blueprint_gate.py`, then lock it before platform
selection. Missing or stale blueprints stop both builders. The built-in
ImageGen tool is the default; CLI/API fallback requires explicit user approval
and a locally configured `OPENAI_API_KEY`.

V5.9 retains the V5.8.3 one-success ImageGen visual contract; V5.8.4 changes
only the post-blueprint alignment and reconstruction path.

Use this prompt only after the page count, blueprint mode, canonical content, visual route, and evidence inventory are complete.

## One-success contract

Before the call, create a non-blocking `visual_plan`. Request one successful ImageGen result per final slide. Save the immutable result as `.build/design_drafts/SNN.png`, copy it byte-for-byte to `blueprints/SNN.png`, and record `imagegen_attempt_count: 1`. `transport_attempt_count` starts at 1 and may reach 2 only when a network, timeout, or empty-response failure produced no image; this is the only transport retry. Once any image exists, lock it; text or visual-quality differences never trigger regeneration.

The locked image is both the immutable design draft and the formal blueprint benchmark.

Generate one separate 16:9 完整页面 using the canonical text supplied from `.build/slides.json` and `.build/page_specs.json`: 章节标题, 本页标题, 核心判断, body, source, and page number. Never combine pages. `compose_blueprint.py` may record skeleton/body ROI metadata but must not replace or repaint the formal ImageGen blueprint.

## Visual-first planning order

1. State the conclusion and strongest evidence.
2. Select the most truthful primary expression, independent of Python implementation convenience.
3. Plan supporting icons, people, devices, products, maps, illustrations, or decorative motifs that improve comprehension.
4. Only then consider how Python may rebuild or approximate the page.
5. Check evidence coverage and readability last.

## Expression routing

Use an analytical canvas with adaptive density near 70% of the approved dense reference. Do not force a fixed number of regions, card grids, matrices, or flow boxes.

- `time_series`: line for continuity, column for a few discrete snapshots, or combo only when a second comparable series exists.
- `category_comparison`: horizontal bar, grouped bar, or column chart.
- `composition`: donut composition.
- `multi_metric_comparison`: grouped bars.
- technical structure, material composition, or equipment principle: annotated structure diagram or subject illustration.
- industry chain or upstream/downstream relation: chain with meaningful visual nodes.
- object differences: image-text comparison.
- `lookup`: matrix when exact values matter.
- `process`: editable flow structure only for real steps.
- `qualitative/parallel`: peer modules without fake numbering or arrows.
- `qualitative/narrative`: concise prose with a visual anchor.
- `qualitative/causal`: a flow only when evidence contains a real cause-effect relationship.

Let the evidence select the form. Charts prove comparable facts; annotated structures explain technology; visual chains explain relationships; comparisons expose differences; matrices serve exact lookup; flows serve only real steps or causes.

## Visual assets

Use relevant supporting subjects without a numeric quota. A normal analytical page may contain no raster subject, while a technical or comparison page may justify several. Never fabricate an official logo.

After generation, inspect the entire page and record `visual_reviewed`, `observed_candidate_count`, `candidate_count`, `visual_inventory`, and `complex_visuals` when practical. These fields are diagnostics. Prefer one crop per independent photo, logo, map, pictogram, product, device, person, character, or decorative motif. Count differences and crop omissions become warnings; use native rebuild, simplified approximation, or omission when a crop is unusable.

## Color and style

Use a blue-gray system: `#1E386B` only for the top hierarchy, structural anchors, and strongest data series. Use neutral gray surfaces derived from `#EDEDED` alongside secondary blues; the body must not look entirely blue. Red `#C00000` is only for key numbers or very small highlighted data marks.

Avoid poster, dashboard, magazine, launch-event, glass, neon, gradient, 3D, glow, and heavy-shadow styles. Do not draw palette swatches, RGB labels, or pasteboard design notes.

## Acceptance and release

Release almost every produced full-page blueprint. Block only when the file is missing/unreadable, its aspect ratio is outside 1.50-2.05, full-page effective content is below 0.5%, or body-region effective content is below 0.25%. Text, number, punctuation, extra numbering, density, palette, visual-count, crop, and structural-fidelity differences are warnings. Python owns canonical PPT text and final formatting.

## V5.7 compatibility

For schema 5.7 only, retain the historical analytical canvas wording: Keep charts, tables, matrices, and flows as the primary evidence-bearing body. Use small pictograms, supplied logos, flags, or bounded schematic accents inside the 6-12% of the body area band and a reserved icon lane. This rule does not apply to V5.8.
