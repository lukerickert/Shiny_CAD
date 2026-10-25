[Contents](../README.md) · [← 7. DXF](07-dxf.md) · [9. Sketch →](09-sketch.md)

# 8. FCStd

The .FCStd file contains:

| Object | Content |
|---|---|
| `Part` | The part (or the selected parts as a compound) as Part::Feature, hidden in the 3D view |
| `Page` | TechDraw page with the same sheet size and scale as the PDF |
| `Template` | SVG template with the frame and title block. Field values are editable texts (double-click the field on the page) |
| `Front`, `Top`, `Right`, `Isometric` | TechDraw views (DrawViewPart) at the PDF positions |
| `Section` | Section view A-A (DrawViewSection), base view `Front` |
| `SectionCaption` | Annotation "A-A" |

TechDraw computes the view geometry when the file is opened.
Dimensions, centre lines and annotations are added with the TechDraw tools.
The section cut surface is a grey fill.
A 45 deg hatch is set by changing **Cut Surface Display** of `Section` to **SvgHatch** (the hatch file is included).
View positions can differ from the PDF by a few mm because TechDraw centres views on the 3D bounding box.

[Contents](../README.md) · [← 7. DXF](07-dxf.md) · [9. Sketch →](09-sketch.md)
