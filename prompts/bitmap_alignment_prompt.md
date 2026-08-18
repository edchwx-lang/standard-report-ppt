# V6 bitmap full-page alignment

Use this only when `construction_mode` is `bitmap`. Review each locked,
immutable `blueprints/SNN.png` once as a complete full page. This is a single
full-page visual review, not a reconstruction task.

First run `prepare_bitmap_review(project_dir)`. It creates
`.build/bitmap_review.json`; every page record supplies the exact
`blueprint_path`, `blueprint_sha256`, and `pixel_size` that this alignment must
repeat.

Write one UTF-8 `.build/bitmap_alignment.json` using this exact contract:

```json
{
  "schema_version": "6.0",
  "pipeline_revision": "6.0.0",
  "construction_mode": "bitmap",
  "pages": {
    "S01": {
      "reviewed_full_page": true,
      "blueprint_sha256": "<exact hash from bitmap_review.json>",
      "source_px": [left, top, right, bottom],
      "excluded_skeleton_regions": [
        "chapter",
        "page_title",
        "core_judgment",
        "source",
        "page_number"
      ]
    }
  }
}
```

`source_px` uses integer source pixels and must be in bounds, non-empty,
and smaller than the entire source image. The five excluded skeleton region
names must appear exactly as shown and in that order. The crop becomes one
full body bitmap fitted to the deterministic runtime body box. If the
blueprint body is surrounded by a rectangular frame, place every `source_px`
edge inside that frame so the selected bitmap contains no perimeter border or
long partial frame line touching a crop edge.
The derived page element and bitmap contract always use `outline: "none"`.
A crop whose four edges form one continuous dark rectangle is blocked as
`V6_BITMAP_BODY_FRAME_INCLUDED`; repair only `bitmap_alignment.json`.
A long skeleton/frame fragment touching one crop edge is blocked as
`V6_BITMAP_SKELETON_EDGE_INCLUDED` before the first build.

V6.2 crop finality: make this single review carefully, then stop. Once the PPTX
passes its structural postbuild audit, the bitmap crop is locked. Whitespace,
small crop offsets, or a visually negligible crop improvement are manual-only
delivery notes and never authorize another automatic crop/build cycle. Only a
catastrophic structural failure permits the one bounded repair.

Do not request Q1-Q4 tiles. Do not perform OCR or text transcription. Do not
create editable reconstruction, editable charts, or manual element boxes. Do
not alter, repaint, regenerate, or crop the locked blueprint during review.
