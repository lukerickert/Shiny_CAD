[Contents](../README.md) · [← 5. Views and layout](05-views-and-layout.md) · [7. DXF →](07-dxf.md)

# 6. Drawings

Press **Preview** and select the drawing in the drawing list at the upper left.

| Tool | Key | Picks |
|---|---|---|
| **Select** | S | Click a dimension or note to edit it. Drag it to move it. A linear dimension follows the mouse across (dimension line position) and along (text position); text dragged beyond an extension line gets an extended dimension line. **Text centred between extension lines** returns the text to the centre |
| **Horizontal** | H | First point, second point, dimension line position |
| **Vertical** | V | First point, second point, dimension line position |
| **Aligned** | A | First point, second point, dimension line position |
| **Angle** | G | First straight edge, second straight edge (same view, not parallel), arc position. The vertex is the intersection of the two lines (extended); the side of the vertex where the arc is placed chooses which of the angles is dimensioned. Text in deg with 2 decimals |
| **Diameter** | D | Circle or arc, then text position. In a side view of a shaft or bore: first edge point, opposite edge point, dimension line position (Ø added to the measured distance) |
| **Radius** | R | Arc or circle, text position |
| **Note** | N | Text position, then the text in a text box (Enter = new line, Ctrl+Enter or OK = place) |
| **Leader note** | L | Arrow point, text position, then the text in a text box (Enter = new line, Ctrl+Enter or OK = place) |
| **Balloon** | B | Point on the part, balloon position, then the item number |
| **Sketch** | K | A view (sketch on the view) or the sheet outside the views (sketch on the sheet); opens the sketch editor ([section 6.3](#63-sketches-on-drawings)) |

Views are moved by dragging them with **Select**:

| View | Movement |
|---|---|
| Front | Moves Front, Top and Right together |
| Top | Vertical only (stays aligned below Front) |
| Right | Horizontal only (stays aligned beside Front) |
| Section, Isometric | Free |

Dimensions and notes move with their view.
View positions are saved in `work/annotations/<drawing name>.layout.json` as offsets in mm from the automatic layout and are used for PDF, DXF, SVG and FCStd export.
**Reset views** returns all views to the automatic layout.
The **Views** check boxes (Front, Top, Right, A-A, Iso) hide and show the views of the drawing. The remaining views are laid out and scaled as if the hidden views did not exist. Hidden views are stored in the layout file and are left out of PDF, DXF, SVG and FCStd export. With the base view of the section hidden, the cutting line is not drawn.
Shift+drag or the middle mouse button pans.

Points snap to line end points (red square), line mid points (green square) and circle and arc centres (circle).
The curves of a sketch made on the drawing ([section 6.3](#63-sketches-on-drawings)) snap in the same way: line and polyline corners, mid points, arc ends and circle and arc centres. A point of a sketch on the sheet snaps in the view whose frame contains it.
Both points of a dimension are picked in the same view.
The isometric view has no snap points.
Line widths in the editor are shown at a fixed screen width at every zoom level.
Curves stored as B-splines that lie on a circle are recognised as circles for Diameter and Radius.
Mouse wheel zooms, dragging empty space, Shift+drag or the middle button pans, F fits the sheet, Esc cancels the current pick, Delete removes the selected item, Ctrl+Z undoes.

Existing note text is edited in the **Text** field of the properties panel (Enter = new line). The markers `\n` and ` /n ` in note text are also converted to line breaks.

Properties of the selected dimension:

| Field | Function |
|---|---|
| **Prefix** | Text before the value, for example `4x ` |
| **Text override** | Replaces the measured value |
| **Text height (mm)** | Text height of this dimension, note or balloon (empty: `dim_text_height_mm` from the **Title block editor**) |
| **Tolerance** | **None** (general tolerance from the title block), **ISO 286 fit**, **Symmetric ±**, **Upper / lower deviation** |
| **Class** | ISO 286 tolerance class, for example `H7` (hole, upper case) or `g6` (shaft, lower case). Grades IT1 to IT18. Letters A to U and a to u (a, b, c, d, e, f, g, h, js, k, m, n, p, r, s, u) for sizes up to 500 mm; H, h, JS and js up to 3150 mm |
| **Fit calculator** | Opens **ISO fits** ([section 6.1](#61-threads-and-holes-reference)) with the measured size and the class; **Use hole class for the dimension** or **Use shaft class for the dimension** sets **Class** |
| **Show deviations** | Adds the limit deviations of the class next to the class, in µm |
| **Upper (µm)**, **Lower (µm)** | Deviations for **Symmetric ±** (**Upper** only) and **Upper / lower deviation**, in µm (in with **Drawing units** inch, [section 3.1](03-use.md#31-options)). Decimal comma or point. The drawing text is in µm (`Ø15 H8 +27 / 0`, `4 ±20`): the lower deviation on the baseline of the nominal value, the upper deviation above it |

Dimensions are stored in view coordinates and follow the view when the sheet, scale or layout changes.
They are saved in `work/annotations/<drawing name>.json` and are included in PDF, DXF (layer `DIM`) and SVG exports.
Dimension text height is `dim_text_height_mm` (3.5 mm).

**Thread & hole callouts** places one note per hole feature (Part tab, **Hole**) and per external **Thread** feature of a part drawing: count, thread designation or diameter, counterbore, countersink and depth, for example `2x M8-6H, 15 deep` or `Ø9 H7, Ø15 counterbore 5 deep, through` (**Thread** and **Tolerance class** of the hole feature). A metric thread gets a second line with the size before threading and the nominal thread depth: `drill Ø6.8 (D1 6.647–6.912), thread depth 0.677` for a tapped hole, `turn Ø29.947–29.521, d3 25.652–25.306, thread depth 2.147` for an external thread (**Thread** feature), the limits for the tolerance class of the feature (6H or 6g when none is given); a trapezoidal thread (`Tr20x4`) gets `bore Ø16.000 (D1), D4 20.500, thread depth 2.250` or `turn Ø20, d3 15.500, thread depth 2.250, root radius max 0.250`; a unified or pipe thread gets `drill Ø5.1 (minor 4.975), thread depth 0.687, pitch 1.270` or `turn Ø6.350, minor 4.792, thread depth 0.779, root radius 0.183, pitch 1.270` (no class limits). An external thread callout is anchored on the outline at the middle of the thread length in a view across the axis. A hole whose axis is not along any view of the drawing (for example a hole along X with the Right view hidden) gets its note in a view across the axis, the leader pointing at the hole opening on the outline; with **Hidden lines** the hole itself is drawn there. The note is anchored at the top of the first hole of the feature in the view that looks along the hole axis (front, top or right) and placed above the view, in rows from left to right. A second use replaces the callouts placed before; the text is edited in **Text**.

## 6.1 Threads and holes reference

**Reference** in the **Drawings** tab opens the reference tables (`drawgen/fasteners.py`, `drawgen/fits.py`, `drawgen/roughness.py`, served at `/api/reference` and `/api/fits`). The thread and hole tabs have a profile diagram above the table (`static/refdiagrams.js`): the ISO 68-1 profile with the nut (internal thread, brown hatch) above and the bolt (external thread, grey hatch) below the shared basic profile, the diameters d, d2, d3 (bolt) and D, D2, D1 (nut) as dimension lines from the thread axis, H, h3, H1, P and the root radius; the trapezoidal profile in the same form with d, d2, d3, D4, D2, D1, ac, H1, h3, b, R1 and R2; the tapped hole, counterbore and countersink cross-sections with their dimensions.

| Tab | Content |
|---|---|
| **Metric coarse**, **Metric fine**, **Bearing nut threads** | ISO 261 / ISO 262 sizes and the bearing lock nut threads (KM nuts, DIN 981, with the nut number): pitch, d2, d3, D1, tap drill (DIN 336 for coarse, d − P for fine), external thread depth h3 = 0.6134 P, internal thread depth H1 = 0.5413 P, root radius R = 0.1443 P and the minimum root radius of the external thread 0.125 P, tensile stress area, and the limits of 6H (D2, D1) and 6g (d, d2, d3) |
| **UNC**, **UNF** | ASME B1.1 unified threads #1-64 to 2-4.5 UNC and #0-80 to 1 1/2-12 UNF: threads per inch, pitch in mm, d, d2, d3, D1, tap drill (d − P, approximate), h3, H1, root radius, stress area |
| **Pipe G** | ISO 228-1 pipe threads G1/16 to G3 (Whitworth form, 55°): threads per inch, pitch, major, pitch and minor diameters, thread depth h = 0.6403 P, radius r = 0.1373 P |
| **Trapezoidal** | ISO 2904 / DIN 103-1 sizes Tr8x1.5 to Tr200x18: crest clearance ac, d2, d3, D1, D4, thread depth h3 = 0.5 P + ac, overlap H1, root width b, radii R1 max and R2 max |
| **Tolerance limits** | Limits of one size for a class: internal 4H, 5H, 6H, 7H, 6G; external 4h, 6h, 6g, 6e, 8g (ISO 965-1; grade 6 from the tables of the standard, the other grades by the factors 0.63, 0.8, 1.25, 1.6). Pitches below 0.5 mm are not covered |
| **ISO fits** | Fit calculator: **Nominal size (mm)**, **Hole** and **Shaft** class (or a preferred fit of ISO 286-2: H11/c11, H9/d9, H8/f7, H7/g6, H7/h6, H7/k6, H7/n6, H7/p6, H7/s6, H7/u6 and the shaft-basis pairs C11/h11 to U7/h6). Result: upper and lower deviations, maximum and minimum sizes and tolerance of hole and shaft, maximum and minimum clearance (or interference), the kind of fit (clearance, transition, interference), and a diagram of the two tolerance zones about the zero line in µm. Below: the standard tolerance grades IT1 to IT18 for nominal sizes up to 3150 mm (ISO 286-1) and the deviations of h, js, H and JS from the grades |
| **Surface roughness** | Achievable Ra by process (casting, forming, cutting, machining, grinding, honing, lapping, polishing): one row per process, one column per Ra value of ISO 1302 (0.0125 µm to 50 µm, grades N1 to N12), cells green for fine (careful) production, blue for usual production, orange for rough production. The usual range is the average range of the ASME B46.1 chart of common production methods; fine and rough are its less frequent ends; sintering, wire EDM, waterjet and laser cutting, countersinking and plunge grinding from manufacturer data. Opened by **Guide** next to **Surface finish** in **Title block**: the current value is outlined and a click on a column sets the field to `Ra <value>` |
| **Holes for screws** | Tap drill, clearance holes ISO 273 (fine H12, medium H13, coarse H14), counterbore diameter and depth for ISO 4762 and DIN 7984 screws (DIN 974-1 row 1), countersink diameter and depth for ISO 10642 (DIN 74 form F) and ISO 7721 head screws (ISO 15065), all 90° |

The same values are the presets of the **Hole** feature ([section 10.4](10-part.md#104-features)).

## 6.2 Detail views

**Detail** (key E) makes a magnified detail view: click the centre of the detail on the front, top, right or section view, then a point on the detail circle. A thin circle with a letter (B, C, …) marks the detail on the parent view; the content inside the circle is drawn magnified in a circle to the right of the views with the caption `B (2:1)`. **Detail views** in the side panel lists the details with **Magnification** (relative to the drawing scale; the caption shows the resulting scale) and a **×** button that removes the detail with its dimensions. A detail view is dragged like the other views. Dimensions and notes are placed in a detail view as in any view (snaps of the parent view inside the circle). Detail definitions are stored with the view layout (`<drawing name>.layout.json`, `details`); **Reset views** keeps the details and returns them to the default position.

## 6.3 Sketches on drawings

**Sketch** (key K) in the **Drawings** tab opens the sketch editor on the drawing. A click on a view sketches on that view, a click outside the views sketches on the sheet. **Sketches** in the side panel lists the sketches of the drawing with **Edit** and **×** (remove).

| Target | Coordinates | Behaviour |
|---|---|---|
| View (Front, Top, Right, A-A, Iso, detail views) | View coordinates in model mm at the view scale; dimensions show model sizes | Moves with the view; left out when the view is hidden |
| Sheet | Paper mm, origin at the lower-left sheet corner | Fixed on the sheet |

The editor shows the drawing without the edited sketch as the sheet. The edges of the view (all views for the sheet) are reference geometry: they snap, **Model edges** shows or hides them, **Include** and **Include edges** copy them into the sketch. All drawing, modify, constraint and dimension tools of the sketch editor are available ([section 9](09-sketch.md#9-sketch)). **Finish sketch** (Ctrl+E) stores the sketch with the drawing and returns to the **Drawings** tab; **Cancel** discards the changes.

The sketch is saved in `work/annotations/<drawing>.sketch.json` (one entry per target, the same key as the dimensions of the drawing) and is included in the preview and in PDF, DXF and SVG exports. Lines go to the drawing layers by their line type: continuous to `VISIBLE`, dashed to `HIDDEN`, centre lines to `CHAIN`; dimensions and notes of the sketch to `DIM`. Sketches on drawings are not written to the FCStd file.

[Contents](../README.md) · [← 5. Views and layout](05-views-and-layout.md) · [7. DXF →](07-dxf.md)
