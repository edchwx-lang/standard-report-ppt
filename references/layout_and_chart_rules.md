# PPT layout and chart placement rules V5.7

Reference pages contribute structure, information density, and chart placement only. The company visual system always controls color, type, branding, and paragraph formatting.

## Fixed skeleton geometry contract

| Layer | Rule |
|---|---|
| Chapter | 20 pt navy/black; no decorative line above it |
| Page title | 16 pt white text in a navy bar; left-aligned |
| Core judgment | 12 pt in a white box with black 1 pt short-dash border |
| Body | Charts, tables, cards, flows, comparisons, or maps; 8–12 pt |
| Footer | Source and page number; 7–8 pt; no separator above it |

The chapter text, page-title text, and first core bullet share one left anchor within 0.02 inches. The body begins below the measured core box. Blueprint mode obtains this skeleton through `compose_blueprint.py`; fast and blueprint modes reproduce it through the same Python skeleton helper.
Their exact top positions are 0.4 cm, 1.5 cm, and 2.7 cm in both modes.
Keep at least 0.06 inches of clear space between the page-title bar bottom and core-judgment box top.

Keep the pasteboard empty: do not place color swatches, RGB labels, reference cards, or any other generated object outside the slide canvas.

## Information hierarchy

Use conclusion → evidence → explanation. Every page has one conclusion and one dominant visual focus. Inventory source evidence before module design; map every must-keep item and at least 80% of must-keep plus supporting evidence.

Build the body as an **analytical canvas** with two or three large aligned regions. Keep charts, tables, matrices, and flows as the primary evidence-bearing body. Metric strips and concise cards support them. Use small pictograms, supplied logos, flags, or bounded schematic accents only as supporting accents. Optional supporting accents occupy **6-12% of the body area** in total and sit in a **reserved icon lane** beside a heading, regional label, or metric block. Keep the reserved icon lane outside body copy, chart labels, and borders. Use supplied logos only; never generate an official logo. A large photo, map, device, or product is valid only when it is primary evidence.

Reference-style body patterns:

- `2×2 analytical cards`: one line-art accent lane plus two judgments and three compact metrics per card.
- `chart + regional cards + implications`: one large editable chart, two comparison cards, and a bottom implication strip with small semantic accents.
- `value-chain + material matrix`: a short three-stage flow above a large editable matrix or grouped material cards.

## Body grids

| Grid | Use | Typical structure |
|---|---|---|
| Left-center-right | Main chart plus factors and outlook | Chart / interpretation / implication |
| Symmetric two-column | Two comparable objects | Matched hierarchy and row heights |
| Three-column | Three genuine paths or strategies | Equal headers with concise actions |
| Top-bottom | Logic followed by evidence | Reasoning above, chart/table below |
| Chart + commentary | Data-led analysis | Roughly 60% chart and 40% interpretation |
| Text + visual | Logic before map/diagram | Explanation left, visual right |
| Bottom-wide chart | Long trend or many periods | Analysis above, large chart below |
| Matrix | Many objects and dimensions | Navy row header, pale-blue focal column |

Do not automatically number parallel regions. Number only a genuine sequence, stage, rank, or ordered method.

## Page-type selection

| Content | Preferred page type |
|---|---|
| Market size, growth, years | Industry overview or trend chart |
| Two comparable objects | Symmetric two-column comparison |
| Three paths or actions | Three-column strategy cards |
| Stages or history | Timeline or stage evolution |
| TAM/SAM/SOM or revenue logic | Assumption-to-result chain |
| Growth causes | Driver split |
| Revenue, cost, profit, efficiency | Financial/operations comparison |
| Problem, chance, solution | Three causal regions |
| Regions or cities | Matrix plus map |
| Value chain | Central flow plus interpretation |
| Many technologies and metrics | Large editable matrix |

## Chart placement

| Chart | Position | Use |
|---|---|---|
| Bar | Left or bottom | Scale, count, annual comparison |
| Bar-line | Large left visual | Scale plus growth rate |
| Stacked bar | Left or center | Mix, share, composition |
| Line | Center or bottom | Long trend, forecast, history |
| Bubble/scatter | Large center | Attractiveness or positioning |
| Matrix | Right or full width | Many objects and metrics |
| Map | Center or right | Spatial strategy |
| Process arrows | Top or center | Stages, calculations, value chain |
| Metric cards | Beside the chart | Key number, growth, share, CAGR |

Charts prove; nearby words interpret. Every major chart has a conclusion, a descriptive title that states what it proves, and a source.

## Cards and tables

- Prefer navy/blue headers and white, pale-blue, or light-gray bodies.
- Use thin blue/gray rules; avoid thick black grids.
- Keep card gaps, column widths, baselines, and matched comparison rows consistent.
- Use dark red only for a key number or small risk mark.
- Use editable PowerPoint tables or shape grids.

## Blueprint and Python responsibility

ImageGen first produces a complete-page visual reference with approximate chapter, title, core judgment, body, source, and page number. Blueprint composition then locks the exact five-layer geometry, shared left anchor, absence of the decorative top rule, body ROI, and footer. Raw ImageGen output is never shown or delivered as the blueprint.

Python locks typography, paragraph spacing, hanging indent, text alignment, adaptive core height, editable charts/tables, and exact footer treatment. The full-page visual review must declare every non-native subject. Complex visuals must be retained as individual pre-extracted PNGs through one-object `ASSET_CROPS` and aspect-preserving `add_blueprint_asset` calls; declared, extracted, and inserted counts must match.
