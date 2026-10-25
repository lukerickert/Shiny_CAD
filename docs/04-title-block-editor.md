[Contents](../README.md) · [← 3. Use](03-use.md) · [5. Views and layout →](05-views-and-layout.md)

# 4. Title block editor

The **Title block editor** window edits `config.json` > `title_block` and `border`.
**Title block…** in the toolbar of the **Drawings** tab and **Edit…** in the **Title block** section of the drawing settings panel open it.
Each opening fills the window from the saved configuration; changes that were not saved with **Save title block** are discarded.
**Close** or Esc closes the window.

| Control | Function |
|---|---|
| **Width**, **Height** | Title block size in mm (default 180 mm x 40 mm) |
| **Label height** | Text height of the cell labels in mm |
| **Font** | Font family for SVG output. PDF uses Helvetica |
| **Logo cell**, **Projection cell** | `x, y, w, h` in mm |
| **Binding edge**, **Other edges** | Frame margins in mm (ISO 5457: 20 mm and 10 mm) |
| **Logo** | PNG or JPG placed in the logo cell (PDF and SVG only) |
| Cell table | One row per field: **Key** (field name), **Label**, **x**, **y**, **w**, **h**, **Text h** (value text height in mm) |
| **Add cell** | New row. A new key adds a field to the title block fields |
| **Update preview** | Shows the sheet and the title block |
| **Line widths and text (mm)** | Line widths for visible, hidden, chain, hatch, dimension, frame, title block and text lines, and the heights of view text (section letters, captions) and dimension text. Written to `config.json` > `line_widths_mm`, `text_height_mm`, `dim_text_height_mm` |
| **Save title block** | Writes the title block, border, line widths and text heights to `config.json` |

Cell coordinates are in mm from the top-left corner of the title block.

[Contents](../README.md) · [← 3. Use](03-use.md) · [5. Views and layout →](05-views-and-layout.md)
