[Contents](../README.md) · [← 8. FCStd](08-fcstd.md) · [10. Part →](10-part.md)

# 9. Sketch

**Drawings** / **Sketches** at the upper left of the **Drawings** tab switch between the drawings of the models and the sketch editor.
The **Sketches** pane is a 2D editor in model coordinates (drawing units of the DXF file, mm for a new sketch). It also edits sketches on drawings ([section 6.3](06-drawings.md#63-sketches-on-drawings)) and the feature sketches of the Part tab.
**New** starts a blank sketch on the selected sheet with the layers `0`, `CENTRE` (CENTER) and `HIDDEN` (DASHED).

## 9.1 Files

| Control | Function |
|---|---|
| **New** | Blank sketch |
| **File…** (feature sketch) | Shows or hides this file row while a part sketch is edited; it starts hidden |
| **Open DXF** | Imports a DXF file from the browser |
| Path field, **Open** | Imports a DXF file by path. **Folder** is set to the folder of the file |
| Saved sketch list, **Load** | Opens a saved sketch |
| **Save** | Writes the sketch with layers, constraints, dimensions and notes to `work/<Name>.sketch.json` |
| **Name** | Sketch name and output file name |
| **Scale** | Drawing scale (`1:2`, `2:1`). Dimension text height on paper is `dim_text_height_mm` at this scale |
| **Sheet** | A4 to A0: the sheet is shown in the editor and the geometry is drawn on it. **None (extents)**: no sheet; the PDF page size is the drawing extents at **Scale** + 10 mm margin |
| **Title block** | Frame and title block on the sheet, with the values from **Title block** in the side panel. Changed field values update the sheet |
| **Centre on sheet** | Moves the sheet so that the drawing is centred in the drawing area |
| **Folder** | Output folder. Empty: the browser downloads the file. An existing file is overwritten after confirmation |
| **Export DXF** | DXF R2010 with the layers, colours, line types and units of the sketch. Dimensions and notes are on layer `DIM`. With a sheet and title block, the frame and title block are written at the drawing scale on layers `FRAME`, `TITLE` and `TEXT` |
| **Export PDF** | PDF of the sheet as shown in the editor (or of the extents). Black lines. Line width is the layer lineweight, otherwise 0.5 mm for continuous and 0.25 mm for other line types |

A new sketch starts on an A3 sheet with the lower-left sheet corner at model (0, 0); at 1:1 model coordinates are sheet coordinates in mm.
An opened DXF file is centred in the drawing area when a sheet is selected.
The sheet position is stored in the saved sketch.

DXF import:

| DXF entity | Imported as |
|---|---|
| LINE, CIRCLE, ARC, POINT | Line, circle, arc, point |
| LWPOLYLINE, POLYLINE (2D) | Lines and arcs. A LWPOLYLINE with more than 50 vertices and no arcs is kept as a polyline |
| SPLINE, ELLIPSE, 3D POLYLINE | Polyline (0.01 mm chord deviation) |
| TEXT, MTEXT, ATTRIB | Text |
| SOLID, TRACE | Filled polyline |
| INSERT (blocks), DIMENSION, LEADER, MULTILEADER | Exploded into the entities above |
| Other (HATCH, IMAGE, 3DFACE, ...) | Not imported. The count is shown in the status bar and in **Properties** |

Construction geometry is not exported.
Constraints exist only in the saved sketch file and are not written to the DXF.

## 9.2 Drawing and modify tools

| Tool | Key | Picks |
|---|---|---|
| **Select** | Space | Click selects (Shift adds). Window from left to right selects entities inside; from right to left selects entities crossing. Dragging an end point, a line, a circle edge (radius) or a dimension moves it; constrained geometry moves only in its free directions and a fully constrained point stays in place (the constraints and driving dimensions are solved after each move step, so they hold during the drag). **Filter ▾** in the sketch bar sets what clicks and windows select: **Points** (end points, centres, fit points, point entities), **Lines** (lines, arcs, circles, curves, polylines, text), **Dimensions**, **Constraints** (symbols). With the cursor resting 0.5 s over two or more items, a list of them opens at the cursor; an entry highlights its item and a click on it selects it (Shift or Ctrl adds) |
| **Line** | Q | Chain of lines; Esc or right click ends |
| **Rectangle** | W | Two corners |
| **3-pt rect.** | | First corner, second corner (the first side at any angle; horizontal or vertical within the capture angle), then a point on the opposite side or the typed width (on the side of the cursor). Four lines with coincident ends; the second side perpendicular to the first, the opposite sides parallel. With **Auto constraints** the first two corners take the snapped geometry and a horizontal or vertical first side gets that constraint. DOF 5 (inclined), 4 (horizontal or vertical first side) |
| **Centre rect.** | | Centre, then a corner (typed @x,y from the centre: half width, half height). Four lines with coincident ends, horizontal and vertical; two construction diagonals with their ends on the corners and a construction point at the midpoint of the first diagonal. With **Auto constraints** the centre point and the corner take the snapped geometry. DOF 4 |
| **Slot** | | Straight slot: the centres of the two end arcs (Shift or **Auto constraints**: horizontal or vertical), then a point on a side (half width from the line through the centres) or the typed width. Two lines, two arcs and a construction centre line: lines tangent to the arcs at their shared ends, arcs of equal radius, centre line from centre to centre. Properties: **Points at the ends (tips) of the slot**: the first two points are the outermost points of the slot ends (the arc centres are the half width inside them). DOF 5 (4 with a horizontal or vertical centre line) |
| **Circle** | E | Centre, point on the circle or typed radius |
| **Circle 3P** | | Three points on the circle (typed or snapped). With **Auto constraints** each point snapped to an end point or centre of the sketch geometry lies on the circle (point on object) |
| **Arc** | R | Centre, start point, end point (counter-clockwise) |
| **Tangent arc** | | End of a line, arc, spline or conic, then the end point. The arc starts tangent to that end (coincident and tangent constraints). The next click continues with an arc tangent to the new end; Esc ends |
| **Polygon** | Shift+W | **Number of sides** (dialog), centre, then a vertex (circumscribed circle through the cursor) or the typed distance across flats. Creates the sides as lines with coincident, equal and point-on-circle constraints on a construction circle (DOF: position, rotation, size) |
| **P3G** | | Polygon profile: parameters in **Properties** when the tool is chosen, then the centre, then the direction of a lobe (point or typed angle). **Preset**: **DIN 32711 P3G (trochoid, k = n = 3)**, **4 lobes (trochoid, k = n = 4)**, **Schaublin K-profile Dm 22, R2 6 (SV13, 125, 135 change gears)**, **Two-arc K-profile, custom Dm and R2**, **Trochoid, custom n and k**. Trochoid (Filemon 1959, Periodica Polytechnica; DIN 32711 for k = n): **Nominal diameter d1 (mm)**, **Eccentricity e (mm)**, **Lobes n**, **Lever ratio k**; **Outer circle d2** and **Inner circle d3** set d1 = (d2 + d3)/2 and e = (d2 − d3)/4; x = R cos α − e cos α cos nα − k e sin nα sin α, y = R sin α − e sin α cos nα + k e sin nα cos α, R = d1/2; a closed polyline of 60 n points, used in extrude, cut, revolve and loft as one periodic spline through the points. Selecting the polyline shows its parameters in **Properties** (**Centre x**, **Centre y**, **d1**, **e**, **n**, **k**, **Rotation (deg)**, **Outer circle d2**, **Inner circle d3**); a change regenerates the polyline. Its only grip is the centre. Two-arc K-profile (the Schaublin change-gear bore, not DIN 32711): **Width Dm (mm)** and **Corner radius R2 (mm)**; three corner arcs R2 centred on an equilateral triangle of side R1 − R2 and three flank arcs R1 = Dm − R2 centred on the opposite corner, constant width Dm (Schaublin: Dm 22 mm, R2 6 mm, R1 16 mm, side 10 mm, outer circle 23.547 mm, inner circle 20.453 mm); created as six arcs with coincident and tangent constraints. Both add a construction point at the centre; the status line reports the outer and inner circle |
| **Ellipse** | Shift+E | Centre, end of the first axis (direction and half length, or typed), then the half length of the second axis (a point, or typed). **Properties**: centre, half axes, rotation, start and end angle (equal: closed ellipse; different: elliptical arc). Solver geometry: constraints and dimensions use the centre, the four axis ends and the arc ends; **Tangent** at an arc end holds the end direction. Grips move the centre, the axis ends and the arc ends. Exported to DXF as ELLIPSE; forms profiles and surfaces exactly |
| **Conic** | Shift+D | Conic section (rational quadratic Bezier): start point, end point, tangent intersection (the tangents at the start and at the end meet there), then the shoulder point on the curve or a typed rho (Enter: 0.5). Rho below 0.5: elliptical arc; 0.5: parabola; above 0.5: hyperbola. A start or end point snapped to the end of a line, arc or curve gets the **End condition** set in **Properties** while the tool is active (see below); with a tangent start or end the tangent intersection lies on that tangent, and with both ends tangent the tangent intersection is the intersection of the two tangents and the next point gives rho. The shoulder point lies on the line from the chord midpoint to the tangent intersection at the fraction rho. **Properties**: start, end, tangent intersection, **Rho**, the end conditions; **Restore the whole conic** after a trim. Grips move the start, the end, the tangent intersection and the shoulder point (changes rho). Solver geometry: constraints and dimensions use the start, the end and the tangent intersection; **Tangent** at an end holds the end direction (the tangent intersection moves). **Trim** and **Fillet** work as for splines. Exported to DXF as a degree-2 rational SPLINE (a trimmed conic through sampled points); profiles and surfaces use the exact rational Bezier curve |
| **Spline** | Shift+F | Cubic spline through fit points: click the points; Enter, Esc or a double click ends the spline, a click on the first point closes it. A first or last point snapped to the end of a line, arc or curve gets the **End condition** set in **Properties** while the tool is active (see below). **Properties**: **Closed**, the fit point coordinates, the end conditions, **Convert to conic**, **Explode to lines**. Grips move the fit points. Chord-length parameters, natural ends (closed: periodic). A tangent end holds the end derivative of the spline (2 degrees of freedom: direction and length); a G2 end also holds the end curvature (1 degree of freedom) with an extra knot at the middle of the end span. The fit points stay in place. Solver geometry: constraints and dimensions use the fit points and the curve ends; **Tangent** at an end holds the end direction through the fit points. **Trim** and **Fillet** shorten a spline by its parameter range; the trimmed end gets a point-on-object or coincident constraint to the cutter; the curve itself is unchanged and **Restore the whole spline** in **Properties** removes the trim. A free spline with n fit points has 2n degrees of freedom. Exported to DXF as SPLINE (fit points; a trimmed spline through sampled points); profiles and surfaces use the same cubic as the sketch, span by span |
| **Point** | Shift+Q | Position |
| **Move** | V | Base point, destination (selection) |
| **Copy** | Shift+V | Base point, destinations; Esc ends (selection) |
| **Rotate** | Shift+R | Centre, angle typed in deg or a point (selection) |
| **Mirror** | Shift+B | Two points on the mirror line; copies are created (selection) |
| **Offset** | B | Distance (dialog), entity, side. Lines, circles, arcs, polylines, ellipses, splines and conics. A line or arc is offset with the chain of lines and arcs connected to it end to end: the offsets are joined at the corners (extended or shortened to their intersection) and get coincident constraints; Shift+click offsets the entity alone. An ellipse, spline or conic is offset as a spline through offset points of the curve (closed for a closed curve), with fit points added until the spline is within max(0.001 mm, 1e-5 x the curve size) of the exact offset; the status line gives the number of fit points. An offset larger than the radius of curvature on the concave side is refused |
| **Trim** | T | Part of a line, circle, arc, polyline, ellipse, spline or conic between intersections (the sketch axes do not count) to remove (an ellipse becomes an elliptical arc; a spline or conic keeps its curve and narrows its parameter range). With **Auto constraints** each new end is constrained to the cutting entity: coincident when it falls on an end of the cutter (within 1e-4 mm, replacing a point-on-object constraint of that end from an earlier trim), tangent anchored at the shared end when the curves touch there, tangent plus point on object when the curves touch elsewhere, otherwise point on object. With the button held, every part the cursor moves over is trimmed (one undo step) |
| **Extend** | Shift+T | Line or arc near the end to extend to the next intersection |
| **Fillet** | G | First entity, second entity: lines, arcs, splines, ellipses and conics in any combination (two curves must meet or have ends within **Gap tolerance (mm)** of each other; a closed curve is trimmed first). Each entity is clicked on the side to keep; where the two entities meet at a corner, the end at the corner is the one moved. Radius: automatic from the two clicks: the fillet starts at the click nearer to the corner (tangent length t = the smaller distance of the clicks from the corner, R = t tan(phi / 2), phi the angle between the directions from the corner to the clicks; the corner is the intersection of the lines, extended, or of the entities nearest to the clicks); without a corner (and for two selected entities) a quarter of the shorter entity (lines and arcs: length; circles: circumference; curves: extent). The radius is rounded to 1, 1.5, 2, 2.5 ... x 10^n and halved up to 6 times while the fillet does not fit; a value typed while the tool is active (command field) is used instead until the tool is started again. The fillet arc has no radius dimension: dragging the arc with **Select** makes it pass through the cursor, kept tangent, while the joined lines stay on their lines (their ends at the fillet slide along them) and joined arcs keep their centre and radius; a **Dimension** on the arc sets the radius in the same way. Radius 0 (typed) joins the lines at the corner. With two lines selected before **Fillet**, the fillet is applied at once and the longer part of each line is kept. Curves are trimmed by their parameter range; the fillet arc gets coincident and tangent constraints to both entities **Properties** while the tool is active: **Radius from the click positions** (default) or **Radius** with **Radius (mm)**: every fillet of the tool gets that radius. The setting is kept for the next use of the tool in the session; a number typed while the tool is active sets **Radius** |
| **Chamfer** | Shift+G | Distance (dialog), first line, second line, as **Fillet** |
| **Pattern** | | Copies of the selected entities on a grid, set in **Properties**: **Count, direction 1**, **Direction 1 dx, dy (mm)**, **Count, direction 2**, **Direction 2 dx, dy (mm)**, **Row offset (mm)** (every second row shifted along direction 1). Counts include the original. The copies carry no constraints |
| **Construction** | C | Toggles construction geometry for the selection. Without a selection: new geometry is construction geometry |
| **Select tangent chain** (right-click menu) | Shift+C | Adds to the selection the lines and arcs joined with tangent continuity to the selected ones; **Select connected chain** adds those joined end to end. The selection is then the chain for **Offset**, **Move**, **Copy**, **Mirror**, **Pattern** and **Delete** |
| **Delete** | X, Delete | Removes the selection, and the constraints and dimensions that use it |
| **Undo**, **Redo** | Z, Shift+Z (Ctrl+Z, Ctrl+Y) | |
| **Fit** | F | Zooms to the drawing |
| **Check** | | Lists the sketch issues in **Properties**: gaps between two ends within **Gap tolerance (mm)** (default 0.5 mm), open ends, junctions that are nearly tangent within **Tangent tolerance (deg)** (default 2 deg), tangent junctions without a tangent constraint, touching ends without a coincident constraint, entities shorter than **Tiny length (mm)** (default 0.1 mm), consecutive collinear lines (directions within the tangent tolerance) and co-circular arcs (centres and radii within the gap tolerance) with no other entity at the shared end, crossings and T-junctions of lines, arcs and circles, overlaps (collinear lines whose segments overlap, with the overlap length in mm; arcs and circles with the same centre and radius whose spans overlap, with the overlap angle in deg; identical ellipses, splines, conics and polylines). A click on an issue selects the entities and centres the view on it. One button per kind of issue fixes that kind; **Fix all** fixes every kind in the order of the buttons. **Remove overlaps** merges overlapping lines and arcs into the one with more constraints (extended to the union; a full union of arcs becomes a circle) and removes the duplicate of two identical curves. **Remove tiny entities** removes each tiny entity and joins the entities at its two ends with a coincident constraint. **Close gaps** closes each gap at the midpoint with a coincident constraint (at the curve end when one side is a trimmed curve). **Close open ends** closes an open end within **Open end reach (mm)** (default 5 mm): two open ends of lines are extended to the intersection of the lines, other pairs of open ends are joined by a new line, and a single open end of a line or arc is extended to the nearest entity (coincident constraint at an end of that entity, else point on object); an open end with nothing within the reach is listed only. **Merge chains** replaces each pair of collinear lines or co-circular arcs by one entity, repeated along a chain. **Split at crossings** splits lines, arcs and circles (two or more points) at crossings and T-junctions; the pieces get coincident constraints, lines stay collinear (parallel, or the horizontal or vertical constraint of the line) and arcs stay concentric with equal radii; a length dimension becomes the distance between the outer ends and an equal or midpoint constraint of a split line is removed. **Add tangent constraints** and **Add coincident constraints** add the missing constraints. Each fix is kept only when the solver accepts it; only the geometry connected to the issue through constraints is solved. A fix the solver refuses is marked (fix not possible with the present constraints) and not offered again until the next **Check**; the status line gives the numbers fixed, not possible and remaining. Joints between two entities that cannot move (a fix constraint on the whole entity, as on included edges, or fully constrained geometry) are not listed as missing tangent or coincident constraints; a gap or near tangent between two such entities, and a tiny entity whose neighbours cannot move, are listed with (both fixed) or (neighbours fixed) and no fix. Constraints and dimensions of a removed entity are dropped. **Convert N polyline(s)** turns every polyline of the sketch into solver or curve geometry: an arc or a circle when its vertices lie on one circle, a spline through the vertices when it is a sampled curve (5 or more vertices with turns below 30°), else lines |

With **Corner construction lines** checked, fillet and chamfer add two construction lines from the trimmed line ends to the original corner.
With **Auto constraints** the construction lines are parallel to the lines, meet at the corner, and (chamfer) have equal length.
Dimensions to the corner point (end point of the construction lines) drive the outline; a dimension along one construction line drives the chamfer distance.
**Fillet** also applies between a line and an arc, and between two arcs (click each on the side to keep, or select both and press **Fillet**). The fillet is tangent to both and is constrained with coincident and tangent constraints. A full circle is trimmed to an arc first. Corner construction lines are added for two lines only.
**Chamfer** applies to two lines.
A fillet or chamfer on a corner that already has one replaces it: the old arc or chamfer line and its corner construction lines are removed first. A polyline clicked with **Fillet** or **Chamfer** is converted first (arc, circle, spline or lines, as **Convert polylines** in **Check**) and the piece under the cursor is used.
Tool messages are shown in the status bar and next to the tool hint below the drawing.

Snap points: end (square), mid (triangle), centre (circle), quadrant (diamond), intersection (cross), nearest (hourglass).
Shift while picking the next point gives a horizontal or vertical direction.
Mouse wheel zooms, the middle button or dragging with the right button pans, Esc cancels the current pick and then returns to **Select**.
The default keys are placed for the left hand. **L**, **P**, **M**, **O** and **N** also start Line, Point, Move, Offset and Note. The left-handed set ([section 3.1](03-use.md#31-options)) mirrors them to the right side of the keyboard.
**Keys** lists the shortcuts.

A right click without dragging opens a menu:

| Menu part | Content |
|---|---|
| First item | **End / cancel** (current tool) |
| With a selection | The constraints that apply to the selection, **Fillet** and **Chamfer** (two lines), **Move**, **Copy**, **Rotate**, **Mirror**, **Construction on/off**, **Delete** |
| Always | Drawing tools, **Dimension**, **Note**, **Undo**, **Redo**, **Fit**; without a selection also **Trim**, **Extend**, **Fillet**, **Chamfer**, **Offset** |

A right click on a point or entity with nothing selected selects it first.

Coordinates and values are typed in the command field below the drawing (typing a digit with a tool active starts the input):

| Input | Point |
|---|---|
| `x,y` | Absolute |
| `@dx,dy` | Relative to the previous point |
| `@L<A` | Distance L at angle A (deg, counter-clockwise from +x) from the previous point |
| `L` | Distance L from the previous point towards the cursor; radius, angle, offset distance, fillet radius or chamfer distance where the tool asks for a value |

**Next** below the drawing lists suggested operations for the current selection with their keys, with the **Select** tool and no pick in progress: drawing tools for an empty sketch; dimension tools for an unconstrained sketch; constraints and a dimension for the selected points, lines, circles and arcs; the value input for a selected driving dimension; **Finish sketch** (Ctrl+E, Ctrl+Enter, or a triple click with the **Select** tool) for a feature sketch.
A click on an entry runs it.

**Properties** shows the selected entity: layer, line type (**ByLayer** or a named line type), construction, coordinates, length and angle, centre, radius and angles, text.
Changed values are applied with the constraints.
For a polyline, **Convert to arc** / **circle** (offered when the vertices lie on one circle, with the radius), **Convert to spline** and **Convert to conic** (offered for an open polyline whose end tangents meet on the convex side, with the maximum deviation of the vertices from the conic in mm) replace it by solver or curve geometry. **Convert to conic** fits the end tangent directions and rho to the vertices. **Explode to lines (N)** makes one line per segment; a sampled curve (5 or more vertices with turns below 30°) is marked "sampled curve" and becomes N short lines with open ends. An open spline also offers **Convert to conic**. **Convert N to conics** (**Properties** with nothing selected or with several entities selected, and the **Check** list) converts every open spline and polyline of the selection, or of the sketch when nothing is selected, whose conic is within **Tolerance (mm)** (default 0.05 mm); the status line gives the number converted and the number kept (deviation above the tolerance, or no conic: the end tangents do not meet on the convex side). Polylines included from the model (**Include**, **Include section**, **Include edges**) are converted on inclusion.

**End conditions** of a spline or conic end that meets the end of a line, arc or curve (joined by a coincident constraint or at the same point) are listed in **Properties** of the curve as **Start** and **End** (with the joined entity): **Coincident** (coincident constraint only), **Tangent** (coincident and tangent constraints), **Curvature continuous (G2)** (coincident, tangent and curvature constraints). The Spline and Conic tools show **End condition** in **Properties** while the tool is active (default **Tangent**); it applies at a first or last point snapped to the end of a line, arc or curve. A G2 end of a spline matches the curvature of the joined entity (0 for a line, 1/R for an arc). A G2 end of a conic is solved through rho and the tangent intersection; when it cannot be satisfied the end stays tangent and the status line says so. A change that the solver cannot satisfy leaves the end unchanged (message in the status line). Closing a spline removes its end conditions.

**Layers**: visibility, current layer (radio button), colour, line type and lineweight. **Add layer** creates a layer.

## 9.3 Constraints

The constraint buttons (icon and name: **Coincident**, **Horiz.**, **Vert.**, **Parallel**, **Perp.**, **Tangent**, **Equal**, **On**, **Mid**, **Conc.**, **Sym.**, **Fix**) are in one group with the dimension tools **Dimension**, **Horizontal** and **Vertical** (left of them); **Note** and **Leader** follow in their own group.
The constraint buttons apply to the selected points and entities.
A constraint button (or its key or menu entry) pressed with nothing selected, or with a selection that does not complete the constraint, starts the pick mode for that constraint (button highlighted, hint in the status line) with the selection kept: the points and entities clicked next are added without Shift and the constraint is applied as soon as the selection fits it, after which the next pick starts. Esc, the same button or a drawing tool ends the pick mode.
The constraint keys work with the **Select** tool; with a drawing tool active, digits start the coordinate input.
Points are selected by clicking an end point or centre; Shift+click adds a line, circle or arc to the selection.
The entity selected as reference (the line for a point on a line, the first line for parallel, perpendicular, equal and tangent) is held where possible and the other entity moves.

| Button | Key | Selection |
|---|---|---|
| **Coincident** | 1 | Two or more points (the first selected point moves to the others), points and one line, circle, arc or curve (point on object), or two lines (collinear: both ends of the second line on the first line). Curve points: spline fit points, conic start, end and tangent intersection, ellipse centre, axis ends and arc ends |
| **H**, **V** | 2, 3 | Lines, or two points |
| **∥** | 4 | Two or more lines |
| **⊥** | 5 | Two lines |
| **Tangent** | 6 | Line and circle/arc, two circles/arcs, or a spline, ellipse or conic with a line, arc, circle or another curve. With a common end point the tangency is at that point (for a curve: its end direction). Without a common end point (line, arc or circle with a curve) the contact point is a point of the curve found by the solver; two curves need a common end point |
| **=** | Shift+1 | Lines (length) or circles/arcs (radius) |
| **On** | Shift+2 | Points and one line, circle, arc, spline, ellipse or conic (the curve parameter of the point is solved) |
| **Mid** | Shift+3 | Point and line |
| **Conc.** | Shift+4 | Circles/arcs; or one circle/arc and a point (the centre is placed at the point) or a line (the centre lies on the line) |
| **Sym.** | Shift+5 | Two points and a line |
| **Fix** | Shift+6 | Points or entities |

The **Curvature (G2)** constraint (symbol G2) is added by the end conditions of splines and conics: equal curvature at the shared end of two entities.

With **Auto constraints** the drawing tools add coincident constraints at snapped end points and centres, point-on-object at nearest snaps, midpoint at mid snaps, horizontal and vertical constraints for lines drawn within the capture angle (the angle of 8 pixels across the line on the screen, between 3 deg and 8 deg; H or V is shown at the cursor while it applies; a point snapped to geometry is not moved), and the coincident and tangent constraints of fillets and chamfers.
Constraints are shown as symbols (coincident: green dot) when **Show constraints** is checked.
Clicking a symbol selects the constraint; **Delete** removes it.
Coincident constraints are listed in **Properties** of the entity and are selected there.
Conflicting and redundant constraints are not added (message in the status bar).
The status bar shows the remaining degrees of freedom (**DOF** n, blue) or **Fully constrained** (white on green). Once the sketch has a constraint or a driving dimension, solver geometry that can still move is drawn blue and fully constrained geometry in its layer colour (construction and included geometry keep their own colours).

Closed profiles (the chains of lines, arcs and curves joined end to end that extrude and the other profile features use, and circles) have a light green fill; nested profiles alternate. A red circle marks a chain end that joins no other entity: the profile is not closed there.
Move, rotate, trim, extend, fillet and chamfer remove the constraints that are no longer satisfied.

## 9.4 Dimensions and notes

| Tool | Key | Picks |
|---|---|---|
| **Dimension** | A | Line (length), circle (diameter), arc (radius), two points (horizontal or vertical from the position, otherwise aligned), point and line (distance), two lines (angle); then the position |
| **Horizontal**, **Vertical** | S, D | Line or two points; then the position |
| **Note** | Shift+A | Text position, then the text (Enter = new line, Ctrl+Enter or OK = place) |
| **Leader** | Shift+S | Arrow point, text position, then the text |

With **Driving dimensions** checked a dimension on lines, circles, arcs and points becomes a constraint and the value is requested in an input field at the dimension text (Enter applies, Escape cancels).
A dimension that is redundant with the existing constraints, or that refers to polyline vertices or text, is a reference dimension.
Driving dimensions are green in the editor.
Double-clicking a driving dimension opens the same input field with the current value.
With a single driving dimension selected, typing a digit opens the input field with that digit, and Enter opens it with the current value.
After a dimension value changes, the view stays as it is (**Fit** fits it).
A changed value keeps the other radii, the construction line lengths and the first picked point where the other constraints allow. The radius or diameter of an arc joined to other entities (a fillet) first keeps the joined lines on their lines and the joined arcs in place. The value entered when a dimension is placed also scales its position with the geometry: a radius or diameter leader keeps its direction at the same distance relative to the radius, a linear dimension keeps its offset relative to the length.
**Properties** of a dimension: **Driving**, **Value**, **Orientation**, **Type** (diameter/radius), Ø symbol, **Prefix**, **Text override**, text centred, **Tolerance** (as in [section 6](06-drawings.md#6-drawings)).
Dimensions and notes are drawn at `dim_text_height_mm` on paper at the sketch **Scale**.

## 9.5 Images

**Images** in the side panel of the sketch editor holds reference images drawn under the sketch geometry. Images are available in the **Sketches** pane, in feature sketches of the Part tab and in sketches on drawings. They are stored with the sketch and are not exported to DXF or PDF.

| Control | Function |
|---|---|
| **Import image** | Image file from the browser: PNG, JPG, GIF, WebP, BMP, TIFF |
| Path field, **…**, **Open** | Image file by path on this PC |
| Image list | Check box: visible. A click on the name selects the image (orange outline) and shows its properties; a second click deselects it. **×** removes the image from the sketch; the file stays in `work/images/` |

The image file is copied to `work/images/` of the project (no project open: `sketches/images/`). The EXIF orientation of a photo is applied to the pixels of the copy. TIFF is copied as PNG. A file with the same name and the same content is used again; a different file with the same name gets a suffix (`photo_2.jpg`).
A new image is placed in the middle of the view at 60 % of the view width or height.

Properties of the selected image (with nothing else selected):

| Field or button | Function |
|---|---|
| **Width (mm)**, **Height (mm)**, **Scale (mm/px)** | Size of the shown image; a changed value scales the image about its centre |
| **Rotation (deg)**, **Centre x**, **Centre y** | Rotation of the image x axis from the sketch x axis, position of the image centre |
| **Opacity** | 0.1 to 1 (default 0.6) |
| **Show when the sketch is closed** | Feature sketches of the Part tab: the image is drawn on the sketch plane in the 3D view while the sketch is closed, with its opacity (`images[].show3d`). **Show ▾** > **Sketches** and the eye of the sketch in the tree hide it with the sketch curves |
| **Scale from distance** | Two points on the image, then the distance between them in mm (dialog). The image is scaled about the first point. Shift: second point horizontal or vertical from the first |
| **Scale from circle** | Three points on a circle on the image (the circle through them is drawn while picking), then its diameter in mm (dialog). The image is scaled about the centre of the circle |
| **Align to axis** | Two points on an image edge that is horizontal or vertical on the object. The image is rotated about the first point by the smallest angle that makes the edge parallel to the sketch x or y axis |
| **Move** | A point on the image, then its position in the sketch (snaps to the sketch geometry, typed coordinates) |
| **Lens correction** | Points along edges that are straight on the object: at least 3 points per line, Enter or **End line** ends a line, **Apply** or Enter on an empty line fits the correction, Esc cancels. Lines near the image border give the best fit. A lens correction removes the perspective, round part and control point corrections |
| **Perspective** | **Width (mm, corner 1 to 2)** and **Height (mm, corner 2 to 3)** of a rectangle on the object, **Pick corners**, then the 4 corners in order around the rectangle. Corner 1 to corner 2 is placed along the sketch x axis; corner 1 stays at its picked position |
| **Round part** | Points on circles of one plane face of a round part (at least 5 per circle, spread around it). **Diameter of circle 1 (mm)** (empty: the current scale); **Points on**: **Circle 1**, **Circle 2, concentric** or **Centre** (centre hole, centre mark) selects the set the clicks go to. A centre outside the fitted ellipse of circle 1 is refused. Circle 2 lies on the same plane as circle 1 (the bottom of a counterbore and the face around it are two planes). The fitted ellipse of each circle is drawn while picking; the panel gives the ellipse size in px and its axis ratio. **Apply** or Enter applies, **Remove last** removes the last point of the selected set, Esc cancels. Circle 1 only: affine correction. Circle 1 and the centre, or circles 1 and 2: perspective correction. The circle centre stays at its picked position and the image x axis at the centre stays along the sketch x axis. The status line gives the radial deviation of the points (rms and maximum, mm) and the diameter of circle 2 |
| **Control points** | A point on the image, then its position in the sketch (snaps to the sketch geometry, typed coordinates x,y), repeated; **Apply** or Enter applies, **Remove last** removes the last point, Esc cancels. 2 pairs: scale, rotation and position. 3 pairs: affine map (scale in two directions, shear, rotation, position). 4 or more pairs: perspective correction (least squares for more than 4 pairs; the status line gives the rms and maximum deviation of the points in mm). The known geometry is drawn in the sketch first, for example as constrained and dimensioned lines |
| **Remove corrections** | Shows the image file without the lens and perspective corrections |

Each image is placed by an affine map from the pixels of the shown file to the sketch (`images[].A` in the sketch file).

Corrections:

| Correction | Model |
|---|---|
| Lens | Radial distortion: q = c + (p − c)(1 + k1 r^2), p the image pixel, c the image centre, r = \|p − c\| / half diagonal. k1 (−0.4 to 0.4) minimises the sum of (distance from the best-fit line / line length)^2 of the picked points. The status line gives k1 and the rms distance of the points from their lines in px before and after |
| Round part | Ellipse fitted to the points of each circle (direct least squares fit restricted to ellipses, Halir and Flusser). Affine: the ellipse is stretched along its minor axis to a circle of the given diameter. Centre: the polar line of the centre with respect to ellipse 1 is the vanishing line of the face; the homography maps it to infinity and ellipse 1 to the circle. Concentric: the pencil of the two ellipses holds the vanishing line as a double line; its pole with respect to ellipse 1 is the centre, then as for the centre. A perspective correction is replaced by the affine correction when its scale changes across circle 1 by more than √(1 − r^2) + 0.02 (r = axis ratio of ellipse 1, a plane tilt with cos(tilt) = r and a circle diameter up to the camera distance); the status line gives the reason. Two circles on different planes or a misplaced centre give such a scale change. When the corrected image reaches the horizon of the plane or extends beyond 11 times the circle diameter, it is cut to 11 times the circle diameter |
| Perspective, control points | Homography from the lens-corrected pixels to the sketch plane (normalised DLT). The corrected file has the pixel density of the picked points, at most 8000 px per side and 40 Mpx. When the image reaches the horizon of the plane or extends beyond 11 times the extent of the picked points, the corrected file is cut to 11 times that extent (message in the status line) |

The corrected file is written to `work/images/<image>_c<key>` (PNG with transparent pixels outside the image for PNG, GIF, WebP and BMP files; JPEG with white for JPG files). The key depends on the image and the correction values; a missing corrected file is written again when the sketch is opened.
Order of the steps: lens correction, perspective, round part or control points, then **Scale from distance**, **Align to axis** and **Move**.
A perspective correction needs 4 points on one plane of the object, no 3 of them on one line, or a circle with its centre or two concentric circles on one plane.
The affine round part correction is exact only for a part that is small compared with its distance from the camera. 3 points (for example the corners of a 30°/60° set square) give an affine map, which leaves the perspective of a photo uncorrected.
The lens model is fitted with the image centre as the distortion centre.

[Contents](../README.md) · [← 8. FCStd](08-fcstd.md) · [10. Part →](10-part.md)
