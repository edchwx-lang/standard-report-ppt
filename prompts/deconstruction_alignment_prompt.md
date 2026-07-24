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

If a structure cannot be expressed by the target backend, return
`MAC_RECONSTRUCTION_UNSUPPORTED` or the applicable blocking contract error.
Never change the selected construction mode.
