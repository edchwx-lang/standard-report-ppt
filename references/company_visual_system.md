# Company visual system V5.5

## Character

- Formal Chinese policy, industry-research, and consulting presentation.
- White background with restrained blue-gray structure and dark-red data emphasis.
- Medium density: evidence-rich, readable at normal zoom, and free of miniature dashboard grids.
- Reference pages contribute structure, information density, and chart placement only. They never transfer brand identity, fonts, colors, logos, or decorative style.

## Fixed palette

| Role | HEX | Use |
|---|---|---|
| Navy | `#1E386B` | Chapter/page hierarchy, primary series, major borders |
| Blue | `#7399C5` | Secondary series, module headers, selected columns |
| Neutral gray | `#A6A6A6` | Secondary data and labels |
| Light gray | `#D9D9D9` | Dividers, table rules, neutral fills |
| Dark red | `#C00000` | Key figures, deltas, and risk marks only |
| White/black | `#FFFFFF` / `#000000` | Background and text |

Do not introduce purple, green, orange, neon, or another main hue. Dark red is never a title fill, card fill, section fill, or large background region.

## Typography

Use Microsoft YaHei for Chinese, English, numbers, chart labels, and citations.

| Level | Size | Weight | Treatment |
|---|---:|---|---|
| Chapter title | 20 pt | Bold | Navy or black |
| Page title | 16 pt | Bold | White in navy bar |
| Core judgment | 12 pt | Regular with selective bold | Black |
| Module title | 10–12 pt | Bold | Navy or white on approved blue |
| Body | 8–12 pt | Regular | Black/dark gray |
| Chart label | 8–9 pt | Regular | Black/gray/navy |
| Source | 7–8 pt | Regular | Dark gray |
| Key number | 10–14 pt | Bold | Dark red |

## Deterministic five-layer skeleton

1. Chapter title.
2. Navy page-title bar.
3. Adaptive core-judgment box.
4. Main analytical body.
5. Source and page number.

Chapter text, page-title text, and the first pixel of the first core bullet share one left anchor. The page title is left-aligned. No line, rule, band, or decorative stroke appears above the chapter title. No separator appears above the source.

The core has white fill and a black 1 pt short-dash border. It has no label, badge, or blue block reading “核心判断”. Measure `TextFrame2.TextRange.BoundHeight`, fit the box to the wrapped text, and move the body origin below it.
Set the top positions of chapter, page title, and core judgment to 0.4 cm, 1.5 cm, and 2.7 cm.

The palette is a design specification only. `assets/company_template.pptx` is the master authority. Never render palette swatches, RGB labels, theme-color cards, or other design-reference blocks on or beside a slide; sanitize slides, slide masters, and custom layouts before saving.

## Python paragraph formatting

### Core judgment

- One or two square-bullet judgments totaling 80–160 non-whitespace characters.
- Left-aligned; never justify the core text.
- Microsoft YaHei 12 pt, 1.2 line spacing.
- Use a 0.64 cm hanging indent for manual square bullets.
- Use up to 6 pt after each point; the final point has 0 pt paragraph-after spacing.

### Body

- Microsoft YaHei 8–12 pt.
- Narrative bullets and sufficiently wide prose blocks may use justified alignment, 0.64 cm hanging indent, 6 pt paragraph-after spacing, and 1.2 line spacing.
- Labels, tables, chart annotations, short bullets, and narrow cards remain left-aligned; do not force justification into them.
- Never shrink below 8 pt to preserve an overfilled composition. Edit the content structure instead.

## Editability and effects

Keep titles, text, numbers, sources, cards, tables, lines, arrows, and chart elements editable. Use bounded raster crops only for one independent complex subject at a time, such as a logo, pictogram, photo subject, decorative motif, traffic-light mark, or map base. Never combine neighboring objects or use the whole blueprint as a background.

Do not use gradients, shadow, reflection, glow, soft edge, 3D, glass effects, poster composition, magazine composition, launch-event styling, or decorative full-slide imagery. Explicitly neutralize theme-inherited effects on generated shapes, masters, and custom layouts.
