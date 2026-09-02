# V6 pre-ImageGen visual-freedom patch

Apply this patch after canonical content, evidence routing, `visual_brief`, `visual_plan`, and `page_specs` are drafted, and before each V6 ImageGen call. It changes no source parsing, blueprint locking, reconstruction, bitmap handling, audit, rendering, or packaging behavior.

## Constraint authority

Build the ImageGen request from the canonical page content, the evidence-selected expression, the user's explicit requirements, and the existing design rules in `imagegen_blueprint_prompt.md`, `company_visual_system.md`, and `layout_and_chart_rules.md`. Agent-added negative constraints are forbidden. Do not add bans on photos, icons, maps, people, devices, products, or illustrations unless the user or those existing design rules explicitly require that ban. Do not turn an editability preference into a visual ban; post-blueprint reconstruction decides whether an observed subject is native, cropped, or omitted.

## Executable V6.2.2 gate

Write the exact candidate ImageGen prompt to a UTF-8 text file and run
`python scripts/v622_prompt_guard.py <prompt-file>`. The report must pass before the ImageGen call. If it blocks, rewrite only the prompt into the positive shape below; do not alter canonical content, evidence routing, page specs, generation count, construction mode, or any other blueprint-production setting. Never bypass the gate by paraphrasing a category ban as an editability or reconstruction requirement.

## Positive prompt shape

State, in order: the page conclusion and strongest evidence; the evidence-selected primary expression; its visual story and hierarchy; relevant supporting subjects or visual anchors; the fixed report skeleton and existing color/style contract; and the exact canonical text. Describe what the page should contain instead of expanding the prompt with a new exclusion list.

Do not force a text-card-only page when the evidence supports a chart, annotated structure, visual-node chain, image-text comparison, map, subject illustration, true process, or another relevant visual anchor. For qualitative pages, use the existing `parallel`, `narrative`, or `causal` route and give parallel/narrative content a relevant visual anchor. A genuinely text-led page remains valid when the source and user request call for it, but repeated cards are not an automatic fallback.

Do not force a fixed card count, grid, matrix, flow, or top/bottom split unless it follows from the evidence or an explicit user requirement. `visual_plan` may be empty only when the selected expression genuinely needs no independent supporting raster subject; it must never be emptied merely to simplify later reconstruction.

## Cross-platform scope

The same pre-ImageGen contract applies on Windows and macOS, and to both `deconstruct` and `bitmap`. Platform and construction mode are not inputs to visual routing or ImageGen prompt freedom; they affect only the existing post-lock path.
