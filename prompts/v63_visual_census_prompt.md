# V6.3 locked-blueprint visual census

Use only after the formal blueprint is locked. First inspect the complete source
page and write `.build/v63_source_body_rois.json` with each page's blueprint SHA,
`source_body_roi_px: [left, top, width, height]` and review basis. The source ROI
is observed in the image, NOT inferred from the output template. Inspect `PAGE`,
then the body-only `FULL`
image and every overlapping `B01`-`B06` tile before describing the page.

Inventory every material visible body object independently of the existing
alignment and page spec. Include text blocks, numbers, panels, section bars,
charts and their visible parts, table cells, arrows, connectors, photos, maps,
logos, icons, and illustrations. An object crossing a tile boundary remains one
candidate and lists every tile in which it was reviewed.

Write `.build/v63_visual_census.json`. Each candidate requires a stable ID,
kind, blueprint pixel box, parent candidate when applicable, reviewed tile IDs,
expected treatment (`editable`, `crop`, or `ignore`), and confidence. `ignore`
is limited to negligible texture or anti-aliasing and requires a reason.

Do not copy the inventory from `page_specs.json`. Do not omit a logo, photo,
connector, label, data value, chart part, or meaningful geometry because it is
small. The locked blueprint body is the visual authority.

Record `observed_subject` independently of implementation kind. A world map is
`kind: map, observed_subject: world_map, expected_treatment: crop`, never several
invented polygons. Every independent logo and icon needs its own candidate;
use parent/child candidate IDs for organization, not a single generic "icons"
candidate covering multiple subjects. Reproduce the observed icon, not a circle
with a concept word. Complex icons prefer crops; genuine basic geometry remains
editable. Inventory chart ticks, axis units, values, legend and connectors.

Inspect the numbered census preview once while reconciling the scene. Coverage
checks prove declared bindings, not complete image recognition; do not claim
otherwise. Corrections found after rendering use the single bounded amendment
record, not deletion of requirements or a second full redesign.
