# Manifest-compiled blueprint reconstruction prompt V5.6

Describe each accepted page as literal UTF-8 elements and coordinates; compile the manifests into one editable PowerPoint generator.

## Inputs

- confirmed `project_brief.json`;
- ordered canonical `SLIDES` content;
- accepted `blueprints/SNN.png` images and SHA-256 values;
- visual system and layout/chart rules;
- `assets/direct_blueprint_generator_template.py`.

## Required project structure

Create `.build/slides.json`, `.build/page_specs.json`, and `.build/visual_manifest.json`. Run `project_compiler.py`; it creates only `<project>/generate_deck.py` at the project root and embeds:

- literal `DECK_META`;
- ordered literal `SLIDES`;
- literal `BLUEPRINTS` mapping every final `SNN` to its accepted image;
- literal `ASSET_CROPS` with one-object source rectangles and aspect-preserving target containers;
- a distinct thin `build_slide_SNN` wrapper for each final page;
- literal `PAGE_BUILDERS`;
- one `build_deck()` that opens PowerPoint once and builds the full deck.

Do not create per-page Python files, default geometry JSON, or reusable fixed-layout page loops.

## Reconstruction sequence per page

1. Inspect the page’s accepted blueprint at full resolution.
2. Identify the primary visual, supporting regions, alignment anchors, relative widths/heights, internal gutters, chart position, and bounded complex visual candidates.
3. Add the fixed skeleton with native editable objects. Measure the real core text with `TextFrame2.TextRange.BoundHeight`, resize the short-dash black box, and derive that page’s body rectangle from the measured bottom edge.
4. Write literal page-specific regions and coordinates into `.build/page_specs.json`. The compiler emits wrappers and the shared runtime renders the declared elements; it never selects a layout.
5. Rebuild titles, text, numbers, cards, tables, lines, arrows, and chart components as editable PowerPoint objects.
6. Inspect the accepted blueprint at full size. Record every visual in `.build/visual_manifest.json`. Non-native visual kinds must use crop; `native_rebuild` requires an allowlisted recipe.
7. For every crop item, add one precise `ASSET_CROPS` entry with `source_px`, `target_box_in`, `fit_mode: contain`, and `padding_px`. Follow the artificial-feed 逐对象 insertion pattern: explicit object rectangle, batch extraction, independent background trim, verified PNG/montage, independent contain-fit insertion. A separate icon, logo, map, or picture always receives a separate entry and call.
8. Run `extract_direct_assets.py` once before the build. Inspect the montage and require reviewed crop count = declared count = extracted count; if a crop includes another subject, title, label, border, or rule, correct its `source_px` rather than accepting it.
9. Insert only the pre-extracted PNG through `add_blueprint_asset`; it must preserve aspect ratio, stay inside `target_box_in`, be named `ASSET_<asset_id>`, and produce inserted count = declared count.
10. Use `assets/company_template.pptx` without adding a masking rectangle. Never create palette swatches, RGB reference cards, or pasteboard objects. Sanitize slides, masters, and custom layouts before and after building. Clear shadow, reflection, glow, soft edge, and 3D effects on every generated shape and again across slides, masters, and custom layouts before save. Name the five skeleton shapes `SKEL_CHAPTER`, `SKEL_TITLE`, `SKEL_CORE`, `SKEL_SOURCE`, and `SKEL_PAGE_NUMBER`.
11. Render the page and compare it with its own complete blueprint. Revise the same `build_slide_SNN` until the page and complete visual inventory pass, then run both PPT audits on the final deck.

## Content and density

- Core judgment: one or two points totaling 80–160 non-whitespace characters.
- Core points are left-aligned with true or consistently rendered square bullets; the final point has no paragraph-after space.
- Body density is medium and evidence-rich. Every `must_keep` and at least 80% of `must_keep + supporting` evidence must map to modules; module count follows content and composition and has no fixed minimum.
- Internal slide/module/group IDs are never visible.
- Parallel regions are not numbered. Visible numbering requires a genuine sequence, stage, rank, or ordered method.

## Mode integrity

Blueprint mode forbids importing or calling `fast_geometry`, using `runtime_archetype`, cycling a layout list, modulo-based page selection, or using page type to replace blueprint geometry. If a page cannot be reproduced, improve that page builder or crop a bounded complex asset. Do not switch modes without explicit user approval.

## Completion

Run `project_pipeline.py <project> --run`. It derives work from hashes, records stage timing, and runs text, skeleton, asset, and fidelity gates. The deck is deliverable only when all gates pass.
