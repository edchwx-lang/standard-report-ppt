# V6 deconstruction alignment contract

Use only after the immutable `blueprints/SNN.png` files have been locked and the
full page plus Q1–Q4 visual review has been inspected. Do not regenerate,
retouch, repaint, or replace a blueprint.

For every page, transcribe the visible body topology into
`resolved_page_spec.elements` using editable text, charts, tables, flows, and
basic geometry wherever those semantics are visible. Keep a bounded `asset`
only for one genuinely non-native visual subject such as a map, photo, or
illustration. Never emit `body_asset` in deconstruction mode.

Every `structure_modules[]` record must contain:

- a stable `module_id`;
- `module_kind`, exactly one of `pure_visual`, `text`, `chart`, `table`, `flow`,
  `geometry`, or `mixed`;
- boolean `contains_editable_text`.

Every `text_decisions[]` record must include `module_id` when the selected text
belongs to a body module. Skeleton roles may omit `module_id`.

Every visible module must have one `reconstruction_contract.module_bindings[]`
record that maps its `module_id` to one or more stable `element_ids`. An
asset-only module is permitted only when its module contract is
`module_kind: pure_visual`, `contains_editable_text: false`, it binds exactly one
asset, and the visual inventory classifies that asset as a map, photo, or
illustration. Text, chart, table, flow, geometry, and mixed modules must never be
collapsed into an image.

Forbid all composite-body shortcuts, including:

- one image bound to multiple modules;
- multiple editable modules bound to the same image;
- all body modules bound to one large asset;
- an asset that contains wording which should be native editable text;
- a skeleton plus one page-body screenshot.

For both `windows_com_v584` and `mac_python_pptx_v2` V6 deconstruction, the
V5.9.6 G0–G3 full-page and Q1–Q4 review is authoritative. Every cropped visual
must additionally record:

- `crop_scope: independent_subject`;
- `subject_count: 1`;
- `tight_crop: true`;
- `contains_editable_text: false`;
- `contains_native_geometry: false`.

These fields certify the actual crop pixels, not merely the module label. A
crop containing a timeline, process connector, chart/table structure, editable
wording, or more than one independent subject must be split. Record each
editable visual primitive in the same G0–G3 visual census with
`treatment: native`, its stable `element_id`, `source_px`, `target_box_in`,
`review_tile_ids`, and a supported `rebuild_recipe`. Deconstruction prebuild rejects a
native flow, line, arrow, chart, table, rectangle, or oval that has no matching
native census record. Every deconstruction picture must have no outline, and a
crop whose pixels contain a complete dark perimeter frame must be rejected.

If a structure cannot be expressed by the target backend, return
`MAC_RECONSTRUCTION_UNSUPPORTED` or the applicable blocking contract error.
Never change the selected construction mode.
