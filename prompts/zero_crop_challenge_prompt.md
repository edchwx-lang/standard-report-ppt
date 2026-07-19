# V5.9.5 zero-subject challenge

Use this only after the full locked blueprint has been reviewed and the proposed
page grade is `G0`. It is a post-blueprint visual challenge, not an ImageGen
prompt and not a user confirmation.

Inspect the complete blueprint at full resolution. Record whether any separate
subject is visibly present in each class:

- icon
- pictogram
- logo
- map
- photo
- illustration
- device
- person
- product
- flag

Write:

```json
{
  "review_result": "reviewed_no_raster",
  "presence_flags": {
    "icon": false,
    "pictogram": false,
    "logo": false,
    "map": false,
    "photo": false,
    "illustration": false,
    "device": false,
    "person": false,
    "product": false,
    "flag": false
  },
  "blueprint_sha256": "<locked design_draft_sha256>",
  "zero_subject_reason": "text_chart_table_basic_geometry_only"
}
```

If any flag is true, reject G0, assign G1-G3, and inventory every subject. Do
not infer zero subjects from an empty `visuals` array or from a zero crop count.
This review never calls ImageGen and never changes the locked blueprint.
