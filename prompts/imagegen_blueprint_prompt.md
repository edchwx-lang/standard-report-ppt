# Per-page complete ImageGen blueprint prompt V5.7

## Preconditions

- The user confirmed `production_mode: blueprint`.
- `project_brief.json` has an exact final page count and `blueprint_engine: direct`.
- The canonical `SLIDES` content is complete.
- The visual system and layout rules have been read.

Use one ImageGen generation per final slide by default. Generate one separate 16:9 **完整页面**视觉稿, not a body-only image and not a page with a blank reserved top. Never combine pages. The draft must visibly include the approximate 章节标题、本页标题、核心判断, body, source, and page number so it can be reviewed as a complete PPT page. Exact fonts, wrapping, and vertical positions are only visual references at this stage; `compose_blueprint.py` replaces the top skeleton and footer deterministically before acceptance. Only that composed output may be called a blueprint, shown to the user, saved as `blueprints/SNN.png`, or hashed.

## Fixed five-layer skeleton

1. Chapter title: Microsoft YaHei, bold, 20 pt, navy or black.
2. Page title: Microsoft YaHei, bold, 16 pt, left-aligned white text in a navy bar.
3. Core judgment: Microsoft YaHei, 12 pt, black text in a white box with a black 1 pt short-dash border.
4. Body: charts, tables, cards, flows, comparisons, or maps using 8–12 pt text.
5. Source and page number: 7–8 pt dark gray, with no separator line above the source.

Chapter text, page-title text, and the core bullet symbols should share one approximate left edge in the ImageGen draft. The page title is never centered. No decorative line appears above the chapter. The core contains **one or two** square-bullet points totaling **80–160** characters and has no label, tab, badge, or blue block reading “核心判断”. Do not leave the top three layers blank. `compose_blueprint.py` later enforces their exact 0.4 cm, 1.5 cm, and 2.7 cm top positions.

## Body composition

Use a reference-style **analytical canvas** with medium density and one clear primary visual focus. Arrange two or three large aligned evidence regions. Build the body mainly from editable charts, tables, matrices, flows, metric strips, and concise analytical cards. Use white space and consistent baselines; the page should read like a consulting report, not an image poster.

Inputs:

- page purpose: `{{page_type}}`
- conclusion: `{{title}}`
- canonical core: `{{core_points}}`
- module titles, roles, and final content: `{{canonical_modules_without_internal_ids}}`
- quantitative evidence: `{{quantitative_evidence}}`
- source: `{{source}}`
- reviewed visual manifest subjects: `{{complex_visuals}}`
- intended subject inventory: `{{visual_inventory}}`

Never show internal IDs such as `S01`, `M01`, or group identifiers. Do not automatically number modules or parallel cards. Use visible numbers only when the content is a genuine sequence, stage, rank, or ordered method.

Borrow from reference images only their structure, text density, and chart placement. Do not inherit reference colors, fonts, logos, brand style, decorative language, or copy.

Use white, navy `#1E386B`, blue `#7399C5`, approved gray, black, and pale blue/gray tints. Dark red `#C00000` is limited to key numbers and very small data marks. Do not use a red header, large red card, red section fill, or red background region.

Do not draw a color palette, RGB value swatches, theme reference blocks, design annotations, or pasteboard objects on the left side or anywhere else in the blueprint.

Charts prove facts; nearby text explains the meaning. Before ImageGen, enumerate every intended visual subject. After deterministic composition, write `.build/visual_manifest.json` and bind it to the accepted SHA-256. Photos, logos, maps, pictograms, compound marks, decorative motifs, chemical structures, devices, products, and characters always use `crop`; native rebuild is limited to allowlisted primitives with a concrete recipe. Record `candidate_count`; a positive count can never yield zero crops. Place each crop candidate on its own clean background. Three icons require three subjects, asset IDs, rectangles, PNGs, and insertion calls.

Keep charts, tables, matrices, and flows as the primary evidence-bearing body. Metric strips and concise cards support them. Use small pictograms, supplied logos, flags, or bounded schematic accents only as supporting accents. Optional supporting accents occupy **6-12% of the body area** in total. Put each accent in a **reserved icon lane** beside a heading, regional label, or metric block. The reserved icon lane is separate from body copy and chart labels. Use blue line-art or flat two-tone accents with simple silhouettes; use one accent only when it clarifies a real concept. A normal analytical page may have no raster subject. Use a large photo, map, device, or product only when it is primary evidence, such as product anatomy or geographic strategy. Never fabricate an official logo. After composition, declare, crop, inspect, and insert each non-native accent independently with aspect-preserving contain fit.

Avoid poster, dashboard, magazine, launch-event, glass, neon, gradient, 3D, glow, heavy-shadow, and full-slide-image styles.

## One-shot acceptance gate

Accept the first output when:

- the page is readable and contains one page only;
- all required canonical content regions are present;
- 章节标题、本页标题、核心判断三层均可见，页面不是正文残片；
- the body has a coherent primary focus and medium density;
- every non-native subject is in `visual_inventory`; every crop disposition is mirrored exactly in `complex_visuals` and can be cropped one object at a time without labels, rules, or neighboring objects;
- red fill is restrained;
- no palette swatches, RGB labels, or design-reference blocks are visible;
- native shapes plus bounded crops can reproduce the page.

The fixed top skeleton is corrected deterministically after ImageGen, so do not regenerate for recoverable font or vertical-position differences. Retry the affected page once only for generation failure, unreadable output, multi-page output, missing top layer, missing required content, or unusable body composition; record it as `catastrophic_retry`. After a second catastrophic failure, ask whether to change modes or stop.

## Provenance and state

- Save the raw complete-slide ImageGen draft under `.build/raw_blueprints/SNN.png`; it is internal and must never be shown or delivered as the blueprint. Run `compose_blueprint.py` and save/show only its output as `blueprints/SNN.png`.
- Record the real SHA-256 and ImageGen generation record.
- Set the page state to `blueprint_saved` only after the file and hash exist.
- The next required action is writing that page’s `build_slide_SNN` function in the one whole-deck generator.
