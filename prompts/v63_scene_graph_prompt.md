# V6.3 atomic scene graph

Read the locked blueprint body, all overlapping review tiles, and the validated
`v63_visual_census.json`. Write `.build/v63_scene_graph.json` as a visual reverse
compilation of the body.

Use blueprint pixel coordinates. Recreate every editable census candidate with
atomic `text`, `rect`, `round_rect`, `ellipse`, `freeform`, `line`, `connector`,
or `arrow` elements. Recreate charts and tables from those editable atoms and
use `group` only for hierarchy. Use `image_crop` only for an approved photo,
complex logo, map base, illustration, or complex icon. Map labels, markers, and
connectors remain separate editable atoms.

Every candidate must have one explicit resolution that lists its element IDs.
Every rendered atom must reverse-reference its census candidate. Preserve the
blueprint's body boxes, colors, strokes, z-order, overlaps, labels, and
relationships. Do not emit `matrix`, `flow`, `text_card`, a fixed component
grid, a substituted palette, or a full-body image.

The five skeleton objects are absent from this scene graph. They are owned by
the PowerPoint template and receive text-only updates later.

For measured small rounded corners, set `round_rect.style.corner_radius_px`
in source pixels. The shared normalizer produces an editable freeform outline
on both platforms. Do not rely on default PowerPoint rounding for a measured radius.

For the repair path declare `coordinate_mode: source_pixels_contain` per page.
Do not pre-stretch coordinates; body points and crops share one contain transform.
Use `points_px` as path geometry authority, and `closed: false` for open paths.
Horizontal/vertical lines may have zero height/width. Preserve mixed-color text
as runs, not a single substituted color.

Preserve observed line breaks; short labels and numeric percentages use
`word_wrap:false`. If native font metrics need fitting, opt in with
`fit:"shrink_to_box"`: one measurement/scale, no loop, BODY only. Review any
substantial shrink and keep five template placeholders untouched. Mac writes
Office text-to-fit intent but cannot claim verified typography without rendering.

Map bases and complex icons use `image_crop` with `crop_recipe`. Start with
`rect_crop`; use `masked_crop` exclusion polygons (local crop pixel coordinates)
bound to `overlay_element_ids` to remove native text/markers/lines. `local_cleanup`
may sample a reviewed uniform background only. Never redraw an unknown map edge.
Native labels go over the cleaned base, not over old baked-in text. Record holes
in source geography hidden under the original labels; moving labels may expose
them. Never combine charts, phones, logos and report labels into one crop.

After native rendering inspect the actual output against the source body and
write the hash-bound `v63_visual_review.json` object findings. Awaiting this
internal review does not require user approval or another build. Metrics alone
cannot accept missing objects. At most two actual builds and one visual revision.
