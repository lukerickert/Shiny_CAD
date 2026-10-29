[Contents](../README.md) · [← 15. Limitations](15-limitations.md)

# 16. CAM

The **CAM** tab makes the program of a 3-axis milling machine from a saved part of the project. The tab follows the FreeCAD CAM workbench: a job holds the operations, the model with its placement, the stock, the setup sheet and the tool controllers; an operation is edited in a command window in the view with the sections **Base geometry**, **Depths**, **Heights** and **Operation**; dressups change the path of an operation; the operations are simulated on the stock; the post-processor writes the G-code file. The interface is the interface of the Part tab: a tree in the side panel, a command window in the view, faces and edges picked by clicks in the view and listed as chips.

Coordinates: the moves are computed in the job coordinates (mm, Z up): the part coordinates of the Part tab moved by the model placement ([Model placement](#model-placement)). Without a placement the job coordinates are the part coordinates. The G-code is written in machine coordinates: the job coordinates less the machine zero of the stock. Feeds in mm/min, spindle speed in 1/min.

| Control | Function |
|---|---|
| **File ▾** | **Job** list of the saved jobs of the project; **New**, **Save**, **Save as…**, **Rename…**, **Open file…**, **Save as file…** (`.sccam`); **G-code folder** (empty: the `cam/` folder of the project; no project: download); **Post-processor**; **File name** of the G-code (empty: `<job>.nc`); **Post process**, **Download G-code**, **Inspect G-code** ([section 16.7](#167-post-process)); **Export template**, **Import template…** ([section 16.8](#168-job-template)); **Open** opens the `cam/` folder |
| **Part** | The saved part the operations machine. A change of the part reloads the geometry; the operations and their geometry are kept |
| **Refresh** | Loads the part again after a change in the Part tab. The part file is compared with the loaded geometry when the window gets the focus and every 4 s; a changed part marks **Refresh** orange (the update itself is made by **Refresh**). After the reload the picked faces and edges of the operations are found again by their centres; the picks not found are listed in the status line and in the **Model** properties |
| **Zero** | Machine zero at a vertex: a click on a vertex of the part in the view (the vertex nearest the cursor within 12 px is marked) sets **Machine zero X Y** and **Machine zero Z** to **Picked vertex** at that vertex. Esc cancels |
| **Placement** | Opens the **Model placement** command window ([Model placement](#model-placement)) |
| **Measure** | Opens the **Measure** window. A click on a vertex of the part (the nearest within 12 px), an edge or a face picks an item; a second click measures between the two; a third click starts a new measurement. **Add**: **Machine zero** (a point), **Stock top** and **Stock bottom** (planes). One item: its rows (face: plane normal and centre, or cylinder Ø and axis; straight edge: length, direction, start, end; circular edge: Ø, centre, axis, arc; vertex: point) and its point, centre or midpoint in machine coordinates. Two items: minimum distance (green line in the view), angle and distance between planes, lines and axes, distance from a point to a plane, line or axis, distance between the centres with dx, dy, dz. Coordinates are in mm in job coordinates unless marked machine coordinates. A change of the part or the placement clears the items. Esc ends |
| **Face**, **Profile**, **Pocket**, **Adaptive**, **Drilling**, **Helix**, **Slot**, **Undercut**, **Engrave**, **Vcarve**, **Deburr**, **Thread** | Toolbar buttons with icons. Adds the operation at the end of the list and opens its command window ([section 16.3](#163-operations)) |
| **3D Pocket**, **3D Surface**, **Waterline** | Toolbar buttons with icons ([section 16.4](#164-3d-operations)) |
| **Dressup ▾** | **Tag**, **Ramp entry**, **Lead in/out**, **Dogbone**, **Boundary**, **Axis map**: adds the dressup to the selected operation and opens its command window ([section 16.5](#165-dressups)) |
| **More ▾** | **Fixture**, **Comment**, **Stop**, **Custom**, **Hop**, **Probe** (supplemental operations without a cut), **Copy**, **Array** (the moves of another operation again) ([section 16.6](#166-supplemental-copy-and-array)) |
| **Simulate** | Computes all toolpaths and cuts the stock with the tool ([section 16.7](#167-simulation-sanity-check-and-results)) |
| **Sanity check** | Checks of the job in the properties panel |
| **G-code** | G-code of the selected operation (no operation selected: the whole job) in a window, as **Inspect G-code** |
| **Iso**, **Front**, **Top**, **Right**, **Fit** | Views |
| **Show ▾** | **Edges**, **Axes**, **Part**, **Stock after the operations** (translucent blue), **Remaining material** (red: the stock outside the part after the operations, films thinner than 0.02 mm left out), **Toolpaths** (plunges blue, feed moves green, arcs violet), **Rapid moves** (orange), **Undercut faces** (tinted blue), **3D surfaces** (the cut surface of a 3D Surface operation from its height map, green), **Machine** (the router model, [Machine and playback](#machine-and-playback)) |
| **Panel** | Hides or shows the side panel (Ctrl+B) |

The side panel: **Tree** ([section 16.1](#161-job-tree)), **Properties** of the selected tree item and **Tool bits** ([section 16.2](#162-tool-bits-and-tool-controllers), folded by default). The bar between the view and the panel sets the panel width.

## 16.1 Job tree

The tree is arranged as the job tree of the FreeCAD CAM workbench:

```
Job
  Operations
    <operation>
      <dressup>
  Model
    <part>
      <placement constraint>
  Stock
  SetupSheet
  Machine
  Tools
    TC1, TC2, …
```

**▸** and **▾** fold and unfold an item with children (a double click on **Job**, **Operations** or **Tools** does the same); the folded items are kept for the next session (**Tools** folded by default). The eye hides the geometry of the item in the view: **Job** everything, **Operations** all toolpaths, an operation its toolpath, **Model** the part, **Stock** the stock outline, the machine zero and the stock after the operations, **Machine** the machine model. A hidden item is shown grey. A click selects the item (its properties in the panel); a double click on an operation or a dressup opens its command window, on **Model**, the part or a constraint the **Model placement** window.

| Item | Properties |
|---|---|
| **Job** (the job name) | **Post-processor**, **File name**, **Folder**, **Post process**, **Download** |
| **Operations** | Number of operations and the cycle time of the last run |
| `<operation>` | The checkbox sets it active (inactive: no moves, the stock unchanged), the icon of the type, the name, the type, the tool controller, the number of faces and edges, the state after a run (✓, ⚠ gouge, ✗ error with the message), **▲** and **▼** change the order, **×** deletes it. Properties: the summary and the results of the last run; **Edit** opens the command window. A dressup is a row under its operation |
| **Model** | **Part**, its face count, volume and bounding box in job coordinates, the picks not found after the last **Refresh**, the placement and the number of constraints; **Edit** opens the **Model placement** window |
| `<part>` | The part name and its position and rotation. The placement constraints are rows under it; **×** deletes one |
| **Stock** | **Material**: the workpiece material of the feeds and speeds calculator ([Feeds and speeds](#feeds-and-speeds)). **Stock**: **Part bounding box with offsets** (**X neg**, **X pos**, **Y neg**, **Y pos**, **Z neg**, **Z pos** in mm beyond the part bounding box), **Box (coordinates)** (**X min** to **Z max** in job coordinates; empty: the part bounding box), **Part with the undercuts filled** (the finished part with the material under every undercut face still in place, the stock an earlier program with an end mill leaves), **STEP file** (**STEP file**: a path, or a file name in the `step/` folder of the project; **…** chooses the file; the solids of the file in the coordinates of the part; several solids are fused; **Rot X**, **Rot Y**, **Rot Z** (deg) turn the solid about the part origin, about X, then Y, then Z; **X offset**, **Y offset**, **Z offset** (mm, part coordinates) then move it; the result moves with the model placement; before the first run the view shows the STEP solid transparent). **Machine zero X Y**: **Stock corner (min X, min Y)**, **Stock centre**, **Part origin** (the origin of the job coordinates), **Picked vertex**. **Machine zero Z**: **Stock top**, **Stock bottom (table)**, **Part origin**, **Picked vertex**. **Pick vertex** (or **Zero** in the toolbar) starts the vertex click; the picked vertex is shown in job coordinates and moves with the part when the placement changes. The line below gives the stock size, the machine zero in job coordinates and the clearance height in machine coordinates. The view shows the stock outline dashed (STEP stock: the edges of the solid; the other kinds: the box) and the machine zero as a triad |
| **SetupSheet** | The defaults of the operations: **Clearance height offset (mm)** and **Safe height offset (mm)** above the start depth, **Step down (mm)**, **Finish depth (mm)**, **Horizontal rapid (mm/min)** and **Vertical rapid (mm/min)** for the cycle time, **Coolant**. **Machine**: **Spindle min (rpm)**, **Spindle max (rpm)**, **Rated speed (rpm)**, **Spindle power (kW)**, **Max feed (mm/min)**, **Rigidity (%)**, **Ramp angle (deg)** for the feeds and speeds calculator and the sanity check |
| **Machine** | The router model ([Machine and playback](#machine-and-playback)); ✗ when moves are outside the travel |
| **Tools** | The list of the controllers; **Add from bit** and **Add controller** make a controller from a bit of the library; **Feeds and speeds for all** sets **Feed (mm/min)**, **Plunge feed (mm/min)**, **Ramp feed (mm/min)** and **Spindle (rpm)** of every controller from the calculator with the **ae (mm)** and **ap (mm)** of each controller |
| `TC1`, `TC2`, … | A tool controller ([section 16.2](#162-tool-bits-and-tool-controllers)); **×** deletes it |

### Model placement

**Placement** in the toolbar opens the **Model placement** command window. It moves and turns the part in the job coordinate system. The XY plane of the job coordinate system is the table plane and +Z is the spindle axis. The stock, the machine zero and the operations are worked out on the placed part. While the window is open the view shows the datum planes **XY** (orange), **XZ** (green) and **YZ** (red) through the job origin.

| Section | Content |
|---|---|
| **Constraints** | **Coincident**, **Distance**, **Parallel**, **Angle**, **Concentric**: a click on the type, then a click on a face, an edge or a vertex of the part (**Faces**, **Edges**, **Vertices** choose what the click picks), adds a constraint of it to a datum plane or axis (the assembly mates of [section 11](11-assembly.md) with the datums fixed). The datum and **Flip** of a new constraint are set from the current position: for a face the datum plane (or axis for a cylindrical face) nearest in direction, **Flip** on when the face normal points along the datum normal (**Angle**: when it points against it, so **Value** 0 is the current position); for a straight edge the datum axis most parallel to it (**Parallel**) or the nearest datum plane that contains its direction (**Coincident**, **Distance**, **Angle**); for a circular edge the datum axis most parallel to its axis; for a vertex the nearest datum plane. A Distance constraint starts at the current distance. **Drag**: a left drag on the part in the view moves it in X and Y (Shift: in Z; Ctrl: 1 mm steps); at the release the constraints are solved from the moved position, so the part keeps the motion the constraints leave free. Each row: the type and the face, edge or vertex number, **Datum** (**XY**, **XZ**, **YZ**, **X**, **Y**, **Z**), **Value** (Distance: mm; Angle: deg), **Flip** (the face turned the other way), **Off** (suppressed), **×** deletes it. Every change solves the constraints. A constraint that is not satisfied, or is left out after a conflict, is shown red with the reason. The faces, edges and vertices of the constraints are orange in the view; the row under the mouse is highlighted yellow. Esc cancels a pending face click |
| **Position** | **X (mm)**, **Y (mm)**, **Z (mm)** of the part origin and **Rot X (deg)**, **Rot Y (deg)**, **Rot Z (deg)** (rotations about the fixed X, then Y, then Z axis about the part origin, before the translation). **X +90°**, **Y +90°**, **Z +90°** turn the part about a job axis through the centre of its bounding box. **Onto XY at 0, 0** moves the part so that its bounding box starts at X 0, Y 0, Z 0. **Reset** sets position and rotation to 0 and keeps the constraints. With active constraints a value typed here is the start of the next solve |

| Constraint | Face, edge or vertex | Datum | Result |
|---|---|---|---|
| **Coincident** | Planar | Plane | The face in the datum plane; the part on the side of the datum normal (**Flip**: the other side) |
| **Coincident** | Cylindrical | Axis | The cylinder axis on the datum axis |
| **Distance** | Planar | Plane | The face parallel to the datum plane at **Value** mm |
| **Parallel** | Planar or cylindrical | Plane or axis | The face (or the cylinder axis) parallel to the datum |
| **Angle** | Planar | Plane | The face at **Value** deg to the datum plane. A face parallel to the datum plane at the start of the solve is turned about its longest straight edge; a negative **Value** turns it in the other direction |
| **Concentric** | Cylindrical | Axis | The cylinder axis on the datum axis |
| **Concentric**, **Coincident** | Circular edge | Axis | The circle axis on the datum axis |
| **Coincident** | Straight edge | Plane / axis | The edge in the datum plane / on the datum axis |
| **Distance** | Straight edge | Plane | The edge parallel to the datum plane at **Value** mm |
| **Parallel** | Straight edge | Axis or plane | The edge parallel to the datum |
| **Angle** | Straight edge | Plane / axis | The edge at **Value** deg to the datum plane / axis |
| **Coincident** | Vertex | Plane / axis | The vertex in the datum plane / on the datum axis |
| **Distance** | Vertex | Plane | The vertex at **Value** mm from the datum plane |

A change of the placement moves the picked faces, edges and points of the operations and a picked machine zero with the part (a Slot point keeps the Z of the clicked surface for this). **OK** closes the window. **Cancel** restores the placement and the picks of the operations to their state when the window opened. A constraint keeps the centre of its face (the midpoint of its edge, its vertex) in part coordinates and finds it again after a change of the part; one that is no longer found is reported and the constraint left out. In the solve a turn of the part costs as much as a translation of 100 mm per degree, so the part turns only where the constraints need it. A straight edge on or parallel to a datum axis keeps its current direction along the axis (**Flip** is not used). While the window is open a change of the placement loads the part and the stock again; the toolpaths are computed after **OK** (or **Cancel**, from the cache).

## 16.2 Tool bits and tool controllers

The tool bit library is saved in `config.json` (`cam_tools`) with **Save bits**. It is the same for all projects. The panel lists the bits (**Id**, **Name**, **Shape**, **D (mm)**); a click on a row opens the bit in the editor below the list. **New bit** adds an end mill and opens it; **Copy** adds a copy of the bit (id `T<n>`, name with "copy"); **×** deletes the bit. **Library…** opens the standard metric library: **Library group**, the bits of the group with checkboxes (bits already in the list are marked and cannot be added again), **Select all**, **Add selected** (then **Save bits**).

| Library group | Bits |
|---|---|
| Flat end mills | D 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12 mm, 2 flutes; 3 flutes from 2 mm (ids `EM2-<D>`, `EM3-<D>`). Shank 3 mm up to D 3, 6 mm up to D 6, else D; a neck of D - 0.1 mm over 3 D below a larger shank; cutting height 3 D (3 to 26 mm) |
| Ball end mills | The same diameters, 2 flutes (`BE2-<D>`) |
| Single flute end mills | D 3, 4, 6 mm (`EM1-<D>`) |
| Chamfer mills | 90 deg and 60 deg, D 6 and 12 mm (`CH90-6` …) |
| Tapered ball nose | Tip radius 0.25, 0.5, 0.75, 1 mm × taper 1.5, 3, 5 deg per side, cutting height 20 mm, shank 6 mm (`TB-R<r>-<deg>`) |
| Thread mills | 60 deg single form, D 4.7, 6, 8 mm (`TM60-<D>`) |
| Spoilboard | Surfacing tool D 25 mm, shank 12 mm (`SB-25`); **D (mm)** is set to the tool used |

The feed, plunge feed and spindle speed of a library bit come from the calculator in wrought aluminium (the spoilboard tool in MDF) with the default machine fields.

The bit editor shows the fields of the shape and a drawing of the tool (the cutting part orange, the neck and the shank grey) with D, the cutting height and the length; a bit that cannot be built gives the reason in place of the drawing. Changes apply to the session; **Save bits** keeps them.

| Field | Content |
|---|---|
| **Id**, **Name** | Identifier of the bit (unique) and its text |
| **Shape** | **End mill**, **Ball end mill**, **Bull nose**, **V bit**, **Chamfer**, **Drill**, **Dovetail**, **Tapered ball nose**, **Thread mill**, **T-slot cutter**, **Custom profile** |
| End mill, ball end mill | **Diameter D (mm)**, **Cutting height (mm)** |
| Bull nose | **Diameter D (mm)**, **Corner radius (mm)**, **Cutting height (mm)** |
| V bit, chamfer | **Diameter D (mm)** (at the top of the cone), **Included angle (deg)**, **Tip diameter (mm)**, **Cutting height (mm)** |
| Drill | **Diameter D (mm)**, **Point angle (deg)**, **Flute length (mm)** |
| Dovetail | **Large diameter D (mm)** (at the bottom), **Flank angle (deg)** (between the flank and the base plane), **Flank height (mm)**. The flank ends at a radius of D/2 - height / tan(angle); a height that leaves no radius is refused |
| Tapered ball nose | **Tip radius (mm)**, **Taper per side (deg)**, **Cutting height (mm)**; **Diameter D (mm)** is set from them (the diameter at the top of the flutes) |
| Thread mill | **Diameter over the tooth D (mm)**, **Thread angle (deg)** (the tooth between the neck radius and D/2), **Cutting height (mm)** |
| T-slot cutter | **Disc diameter D (mm)**, **Disc thickness (mm)**; **Neck diameter (mm)** must be smaller than D |
| Custom profile | The points of the cutting edge from the tip up: **r (mm)** and **z (mm)**, z starting at 0 and never going down; **Add point**, **×**. D is twice the largest r, the cutting height the last z |
| **Neck diameter (mm)**, **Neck length (mm)** | The neck above the cutting part (empty diameter: D) |
| **Shank diameter (mm)**, **Shank length (mm)** | The shank above the neck, out of the holder |
| **Flutes** | Number of flutes |
| **Tool material** | **Carbide** or **HSS** (feeds and speeds calculator) |
| **Coating** | **Uncoated**, **TiN**, **TiCN**, **TiAlN**, **AlTiN**, **DLC**, **ZrN** (feeds and speeds calculator) |
| **Feed (mm/min)**, **Plunge (mm/min)**, **Spindle (rpm)** | The values a new tool controller takes |

The bit is a solid of revolution: the cutting part is the profile of the shape, the neck and the shank are cylinders. The cutting part cuts the stock; the neck and the shank are checked against the stock.

A tool controller is a bit with the values of the job: **Id**, **Name**, **Tool bit**, **Tool number** (the `T` number of the G-code), **Feed (mm/min)**, **Plunge feed (mm/min)**, **Ramp feed (mm/min)** (ramp entries and the helix entry of a pocket; empty: the plunge feed of a ramp, the feed of the helix), **Spindle (rpm)**, **Direction** (**CW (M03)**, **CCW (M04)**). Operations refer to a controller. An operation added to a job without a controller for its tool shape gets one made from the first bit of that shape in the library.

| Operation | Tool shapes |
|---|---|
| Pocket Shape | End mill, bull nose, T-slot cutter, custom profile |
| Profile | End mill, bull nose, ball end mill, T-slot cutter, custom profile |
| Face | End mill, bull nose, custom profile |
| Helix, Adaptive | End mill, bull nose |
| Drilling | Drill, end mill |
| Slot | End mill, bull nose, ball end mill, tapered ball nose, T-slot cutter, custom profile |
| 3D Pocket, 3D Surface, Waterline | End mill, bull nose, ball end mill, tapered ball nose, custom profile |
| Engrave | V bit, chamfer, ball end mill, tapered ball nose, end mill |
| Deburr | V bit, chamfer |
| Vcarve | V bit |
| Undercut | Dovetail |
| Thread milling | Thread mill, end mill |

### Feeds and speeds

The properties of a tool controller have a **Feeds and speeds** section. It uses the **Material** of the stock, the tool bit (shape, **D (mm)**, **Flutes**, **Tool mat.**, **Coating**, angle, tip and corner radius), the **Machine** fields of the SetupSheet, **ae (mm)** (width of cut; empty: D) and **ap (mm)** (depth of cut; empty: the step down of the SetupSheet). The result is shown on every change; **Apply** writes **Spindle (rpm)**, **Feed (mm/min)**, **Plunge feed (mm/min)** and **Ramp feed (mm/min)** of the controller. **ae (mm)** and **ap (mm)** are saved with the controller.

| Quantity | Calculation |
|---|---|
| Effective diameter Deff | D. Ball end mill below ap = D/2: 2 sqrt(ap (D - ap)). V bit and chamfer: tip + 2 ap tan(angle / 2), at most D. Tapered ball nose: the profile diameter at ap |
| Spindle speed n | Vc × 1000 / (π Deff), Vc from the material table (carbide or HSS column; dovetail × 0.8, drill × 0.7; × the coating factor of the material group: TiN 1.1, TiCN 1.15, TiAlN 1.3 and AlTiN 1.4 in steel and 0.9 / 0.8 in aluminium, DLC 1.25 and ZrN 1.15 in aluminium), limited to **Spindle min (rpm)** .. **Spindle max (rpm)** |
| Chip load fz | fz10 × (D / 10)^0.8 from the material table, × 0.8 ball end mill, × 0.6 V bit, chamfer and tapered ball nose, × 0.5 dovetail, × 0.4 thread mill, × 0.8 HSS, × **Rigidity (%)** / 100 |
| Radial chip thinning | fz × 1 / sqrt(1 - (1 - 2 ae / Deff)^2) for ae below Deff / 2, at most × 3 |
| Feed | fz (thinned) × flutes × n, at most **Max feed (mm/min)**. Drill: feed per revolution fdrill × D × n |
| Plunge feed | Feed × the plunge fraction of the material (0.25 to 0.6). Drill: the feed |
| Ramp feed | The feed up to a **Ramp angle (deg)** of 2 deg, falling linearly to the plunge feed at 15 deg |
| Mean chip thickness hm | fz (thinned) × sqrt(ae / Deff). Drill: fz sin(point angle / 2) |
| Removal rate | ae × ap × feed / 1000 cm^3/min. Drill: π D^2 / 4 × feed |
| Power | removal rate × kc / 60000 / 0.8 kW, kc = kc1.1 × hm^-mc |
| Available power | **Spindle power (kW)** × n / **Rated speed (rpm)** below the rated speed, else **Spindle power (kW)**. Above it the feed is lowered until the power fits |

Messages: the spindle speed raised to **Spindle min (rpm)**, the feed limited by the spindle power, a mean chip thickness below 0.008 mm in metals (the edge rubs). **Limited by** names **Spindle max (rpm)**, **Max feed (mm/min)** or the spindle power.

| Group | Materials |
|---|---|
| Aluminium | Aluminium wrought (6061, 6082), Aluminium 7075, Aluminium cast (AlSi) |
| Steel | Free-cutting steel (11SMnPb30), Structural steel (S235, S355), Alloy steel annealed (42CrMo4), Tool steel annealed (1.2842, 1.2379), Stainless steel (304, 316) |
| Brass and bronze | Brass (CuZn39Pb3), Bronze (CuSn8, CuSn12) |
| Plastics | POM (acetal), PA (nylon), PE, UHMW-PE, PMMA (acrylic), PVC |
| Wood and boards | Hardwood (oak, beech), Softwood (pine, spruce), MDF, Plywood (birch) |

The table values are in `drawgen/cam/feeds.py` (`MATERIALS`: Vc carbide and HSS m/min, fz10 mm/tooth, kc1.1 N/mm^2, mc, plunge fraction, fdrill mm/rev per mm). They are starting values for a rigid set-up (a router frame and spindle usually need lower values).

## 16.3 Operations

The command window of an operation opens when the operation is added, on a double click of its row, or with **Edit** in its properties. It has the name of the operation and the sections below; the active section is framed. **OK** closes the window. **Cancel** restores the operation to its state when the window opened; a new operation is removed. Every change in the window reruns the operations up to the edited one and shows the toolpaths (the edited operation in colour, the earlier ones grey), the stock and the messages (preview). The G-code of the edited operation is shown with **Inspect G-code**.

| Section | Content |
|---|---|
| **Base geometry** | The faces, edges or points the operation works on. **Faces**, **Edges** or **Points** chooses what a click in the view picks when the operation takes several kinds; the faces the operation can take are tinted blue; a click adds a face or an edge, a second click removes it; the picks are listed as chips (**×** removes one, **Clear** all; the chip under the mouse is highlighted in the view). Engrave and Vcarve also take a **Sketch**: a saved sketch of the project (**Project sketches**: the Sketch tab, on the XY plane of the job) or a sketch of the part (**Sketches of the part**: on its plane, principal, offset, plane feature, face or normal plane; the plane moved by the model placement must be horizontal within 0.5 deg, else the operation stops with a message to turn the part with **Placement**), and a **Text** (**Text**, **Size (mm)** the cap height, **Font** file name, **X (mm)**, **Y (mm)** of the base line start, **Angle (deg)**, **Align**) |
| **Depths** | **Start depth (mm)**, **Final depth (mm)**, **Step down (mm)**, **Finish depth (mm)** in job coordinates. An empty field takes the default: the start depth is the top of the stock over the geometry (a pocket: the stock over the floor; an engraving: the part surface under the path), the final depth comes from the geometry (the floor, the hole bottom, the part bottom), step down and finish depth from the setup sheet. The resolved values are shown greyed after a preview. Pocket Shape starts its levels at the lower of **Start depth (mm)** and the top of the stock over the floor; a **Start depth (mm)** above the stock does not change the levels |
| **Heights** | **Clearance height (mm)** for the rapid moves between operations and **Safe height (mm)** for the rapid moves inside the operation; empty: the start depth plus the setup sheet offsets |
| **Finish** | Pocket Shape, Profile, Adaptive and Undercut ([Finishing](#finishing)) |
| **Operation** | **Tool controller** (the controllers of the job, then **+ New controller:** with each bit of the tool bit library: choosing one adds a controller for that bit to the job with the feeds and spindle speed of the bit and sets it), the fields of the type (below), **Feed (mm/min)**, **Plunge (mm/min)**, **Ramp feed (mm/min)**, **Spindle (rpm)** (empty: the controller values), **Calculate** (the four fields from the feeds and speeds calculator: ae the step over of Adaptive, Face, Helix, 3D Pocket, 3D Surface and Waterline, the step of the Undercut passes, else D; ap the step down of the operation, the depth of Engrave, the width plus extra depth of Deburr, the flank height of a dovetail; the line below gives ae, ap, the chip load, the power and the limits), **Comment** (written in the G-code before the operation) |

### Finishing

The **Finish** section of Pocket Shape, Profile, Adaptive and Undercut sets how the stock left by the roughing is removed. The stock left is the field of the type in the **Operation** section (shown greyed as **Stock left (mm)**): **Extra offset (mm)** (Pocket Shape, Profile), **Stock to leave (mm)** (Adaptive), **Allowance (mm)** (Undercut).

| Field | Function |
|---|---|
| **Finish** | **Off**: no finish pass; the stock left stays. **In each level**: after the roughing of each level a pass along the walls (Pocket Shape, Adaptive), the contour (Profile) or the face (Undercut) at no stock left, with the tool and spindle speed of the operation. **After roughing**: all levels roughed first, then the finish passes as a toolpath of their own with the finish tool, feeds and step down. Defaults: **In each level** for Pocket Shape and Undercut, **Off** for Profile and Adaptive |
| **Finish tool controller** | After roughing: the controller of the finish passes; **(the operation's)** keeps the roughing tool; **+ New controller:** adds a controller for a bit of the library as in **Tool controller**. A different tool gives a tool change in the G-code |
| **Finish step down (mm)** | After roughing: the step down of the finish levels; empty: the step down of the operation |
| **Finish feed (mm/min)** | The feed of the finish passes. Empty: the feed of the operation; after roughing with a different tool: the feed of the finish controller |
| **Finish plunge (mm/min)**, **Finish spindle (rpm)** | After roughing: the plunge feed and spindle speed of the finish passes (empty: as the feed) |
| **Spring pass** | The finish pass of the last level once more at the same offset |
| **Calculate** | The finish feeds from the feeds and speeds calculator: ae the stock left (at least 5 % of D), ap the finish step down |

After roughing, the run gives two results: the roughing under the operation id and the finish as "<name> (finish)". The tree row names the finish controller and shows ✗ when either fails; the properties list **Roughing** and **Finish (<controller>)**; the G-code writes the finish after the roughing of the operation; **Inspect G-code** of the operation shows both. The sanity check reports a finish controller that is not in the job. An older document: Pocket Shape **Finish pass** on becomes **In each level**, Adaptive **Finish profile** on becomes **In each level**.

The levels of an operation: the first level is one step down below the start depth, the last level is the final depth; with a finish depth above 0 the level before the last is at final depth + finish depth. The depth of a level is at most the cutting height of the tool. The paths are polylines (G01) and arcs (G02, G03); offset paths round the corners with 12 segments per quarter circle and keep the chords clear of the walls by the chord sag. **Step over (% of D)** is the distance between passes as a percentage of the tool diameter.

### Profile

The contour of the part, of the picked faces or of the picked edges, cut in levels.

| Field | Function |
|---|---|
| **Base geometry** | Faces or edges of the contour. None: the outline of the part section just above the bottom |
| **Side** | **Outside** or **Inside** of the contour |
| **Direction** | **Climb (CW)** or **Conventional (CCW)** |
| **Extra offset (mm)** | Material left on the contour |
| **Passes** | Passes stepping out from the contour by the step over |
| **Below the bottom (mm)** | The lowest level below the bottom of the contour |
| **Process perimeter**, **Process holes**, **Process circles** | The outer contour, the inner contours and the circular holes of the picked faces |

Each level is entered with a plunge at the contour start (a Ramp entry dressup replaces the plunges).

### Pocket Shape

The material above the picked floor faces cleared in levels. A floor face is a horizontal face of the part with the material above it: the floor of a pocket, or the top of a step beside a boss or a rail. Picked wall faces that enclose a region are cleared as the region.

| Field | Function |
|---|---|
| **Pattern** | **Offset** (loops from the inside out), **ZigZag**, **ZigZag then offset** (ZigZag passes and a loop along the boundary), **Line**, **Spiral**. ZigZag and Line: the first and the last pass run along the two bounds of the region across the passes (the last pass closer than the step over to the one before it when needed), so walls parallel to the passes are cut; between them the walls at an angle to the passes keep the scallops of the step over |
| **Step over (% of D)**, **Angle (deg)** | Distance and direction of the passes |
| **Cut mode** | **Climb (CW)** or **Conventional (CCW)** |
| **Start at** | **Centre** (the loops from the innermost outward) or **Boundary** |
| **Extra offset (mm)** | Material left on the walls by the pattern |
| **Entry** | **Helix**: arcs down to the level about a point with the tool inside the region, quarter turns, a flat turn at the level, then a move to the first pass. **Plunge**: straight down at the first pass. When the region of a level reaches past the stock (an open side, a stock edge), the tool goes down there beside the stock (no stock within R + 0.5 mm in the level) and moves in at the level; **Entry** applies only when the stock covers the whole region |
| **Helix pitch (mm)** | Depth per turn of the helix. The helix radius is 0.5 x R, 0.35 x R or 0.25 x R, the largest with room in the region; without room the level starts with a plunge (message) |
| **Keep tool down** | A link between passes is a feed move at the level when its line lies in the region; else the tool lifts to the safe height and plunges again (message with the count) |
| **Use outline** | Islands ignored: the outline of the floor |

Region of a level: the floor polygon, with the holes that go down (a pocket or a hole in the floor) filled in and the islands (faces rising from the floor) kept; an edge of the outer boundary whose other face does not rise above the floor is open, and the region extends beyond it by 2 x R + extra offset + 1 mm; the section of the part between the level and the reach of the tool above it (the cutting height), offset by the extra offset, is taken away (walls, islands and overhangs); the result is offset inward by the tool radius. The levels start at the top of the stock over the floor polygon. After the levels the material left above the floor within the floor polygon is reported.

### Drilling

| Field | Function |
|---|---|
| **Base geometry** | Cylindrical faces with a vertical axis; one hole per axis position |
| **Canned cycles** | With the LinuxCNC and Mach3 posts each hole is written as one canned cycle: `G83 … Q<peck>` with a peck depth, else `G82 … P<dwell>` with a dwell, else `G81`, with `G98`, `R` at the retract height, the plunge feed, and `G80` after the holes. The other posts write the moves |
| **Peck depth (mm)** | Depth per peck: after each peck the tool retracts to the retract height and comes back to 0.5 mm above the depth reached. 0: one plunge |
| **Dwell (s)** | At the bottom of the hole (`G4` of the generic post; a comment in the Estlcam post) |
| **Retract height (mm)** | Above the start depth between pecks |
| **Depth** | **From the hole** (through when the hole reaches the part bottom, else to the hole bottom), **Through**, **Hole bottom** |
| **Breakthrough (mm)** | Below the part bottom of a through hole |
| **Add the drill tip** | The tip length (from the point angle) added to the depth |

The start depth is the top of the hole when the stock above it is cleared. A hole whose diameter differs from the tool diameter by more than 0.05 mm is drilled with a message.

### Thread milling

Thread milling with a thread mill (or an end mill) along a helix of the pitch.

| Field | Function |
|---|---|
| **Base geometry** | Cylindrical faces with a vertical axis: holes (internal) or bosses (external); one thread per axis position |
| **Thread** | **Internal**, **External** |
| **Pitch (mm)** | Rise per turn |
| **Thread diameter (mm)** | Major diameter; empty: the hole diameter + the pitch (internal), the boss diameter (external) |
| **Thread depth (mm)** | Radial depth; empty: 0.5413 × pitch internal, 0.6134 × pitch external |
| **Hand** | **Right**, **Left** |
| **Direction** | **Climb** (counter-clockwise inside, clockwise outside with an M3 spindle), **Conventional** |
| **Radial passes** | Passes stepping the thread depth to the full diameter |

A right-hand thread is cut counter-clockwise going up and clockwise going down; a left-hand thread the reverse. Each pass: a half-arc lead-in from the hole centre (internal) or a line from outside (external), the helix over the depth of the hole (start and final depth) in whole turns, the lead-out and a retract. The stock is cut by the ring between the hole and the thread diameter (internal) or between the minor diameter and the boss (external); the part has no thread form, so the part material in the ring is reported as cut from the part.

### Face

| Field | Function |
|---|---|
| **Boundary** | **Stock** (the stock bounding box in X and Y), **Part bounding box**, **Picked faces** |
| **Pattern** | **ZigZag**, **Line** (passes in one direction with a lift between them), **Offset**, **Spiral** |
| **Step over (% of D)**, **Angle (deg)** | Distance and direction of the passes |
| **Overhang (mm)** | Tool centre beyond the boundary at the pass ends, in addition to the tool radius |
| **Cut mode** | **Climb (CW)** or **Conventional (CCW)** |

The default depths are the stock top and the part top.

### Helix

The picked holes cleared with helical passes of an end mill smaller than the hole.

| Field | Function |
|---|---|
| **Direction** | **Climb (CW)** or **Conventional (CCW)** |
| **Start side** | **Outside** (the pass along the wall first, stepping in) or **Inside** |
| **Step over (% of D)** | Distance between the passes |
| **Extra offset (mm)** | Material left on the wall |
| **Breakthrough (mm)** | Below the part bottom of a through hole |

The pitch of the helix is the step down.

### Adaptive

Clearing or profiling with continuous spiral paths of the tool centre whose radial engagement stays at the step over: the loops of the region offset inward by multiples of the step over, from the innermost outward, each loop morphed into the next.

| Field | Function |
|---|---|
| **Base geometry** | Floor faces. None: the stock over the part |
| **Mode** | **Clearing** of the region or **Profiling** of a band of **Passes (profiling)** x step over around the walls |
| **Step over (% of D)** | Radial engagement |
| **Tolerance (mm)** | Path simplification |
| **Helix ramp angle (deg)**, **Helix diameter (mm)** | The helix entry (diameter 0: half the tool diameter) |
| **Lift (mm)** | Lift above the level between separate regions |
| **Stock to leave (mm)** | Material left on the walls |
| **Use outline** | Islands ignored |

### Slot

A straight or circular slot along its centre line.

| Field | Function |
|---|---|
| **Base geometry** | Two points (**Points**: a click on the model gives a point; **P1 X**, **P1 Y**, **P2 X**, **P2 Y** in mm), an edge (a line, or an arc or a circle for a circular slot) or the slot floor (a face with two rounded ends: the centre line between the ends) |
| **Extend start (mm)**, **Extend end (mm)** | The centre line extended |
| **Radius offset (mm)** | Of a circular slot from an arc edge |
| **Layer mode** | **Multi pass** (levels) or **Single pass** at the final depth |
| **Reverse direction** | |

The default start depth is the part surface under the slot; the default final depth is the bottom of the edge or of the floor, else the part bottom.

### Engrave

Picked edges, the curves of a saved sketch or the outlines of a text followed at the levels from the start depth to the final depth.

| Field | Function |
|---|---|
| **Base geometry** | Edges; **Sketch** (a project sketch or a sketch of the part); **Text** |
| **Depth (mm)** | Below the surface (when the final depth is empty) |
| **Start vertex** | Start of a closed path |

The default start depth is the part surface under the paths. The volume cut from the part is reported as cut from the part (an engraving cuts the part by design and is not a gouge).

### Deburr

A chamfer along the picked edges (or the outer edges of the picked faces) with a V bit or a chamfer bit.

| Field | Function |
|---|---|
| **Width (mm)** | Width of the chamfer |
| **Extra depth (mm)** | The tip below the chamfer |
| **Direction** | **Climb (CW)** or **Conventional (CCW)** |
| **Entry point** | Start vertex of a closed path |

### Vcarve

Closed regions carved along their centre lines with a V bit: the depth at a point of the centre line is the depth at which the bit touches both sides of the region. Parts of a region wider than the bit at the final depth are cleared at the final depth.

| Field | Function |
|---|---|
| **Base geometry** | Faces (their outlines are the regions), a **Sketch** with closed loops, a **Text** |
| **Discretize (mm)** | Step along the outline for the centre lines |
| **Threshold** | Centre lines of the inner corners dropped below this value (0 to 0.9) |
| **Colinear filter (mm)** | Collinear points of the centre lines removed |

The moves vary in Z continuously. The stock is simulated on a height map; the solid stock is cut by the envelope of the regions ([section 16.7](#167-simulation-sanity-check-and-results)).

### Undercut

The material under an inclined face removed with a dovetail cutter. The faces are straight, open at both ends and cleared by an earlier operation (a pocket on the floor beside the rail) to their base Z.

| Field | Function |
|---|---|
| **Base geometry** | Undercut faces: planar faces whose outward normal points downward and sideways |
| **Step over (mm)** | Step of the roughing passes into the undercut |
| **Allowance (mm)** | Material left on the face by the roughing passes and removed by the finish pass. 0: the last roughing step is the finish pass |
| **Run-out (mm)** | Distance of the cutter edge beyond the face ends at the start and the end of a pass |
| **Reverse** | Passes in the other direction along the face |

Geometry read from each face: the angle to the base plane, the height, the undercut depth (height / tan(angle)), the base Z, the bottom edge and its direction, the length and the horizontal direction out of the material. Passes of each face, all at the base Z: the cutter axis is at D/2 outside the bottom edge for the finish pass; the roughing passes start at the undercut depth minus the step over outside that position and step in by the step over until the allowance is reached, then a pass at the allowance and the finish pass. Each pass: rapid to the clearance height above the start point, which is D/2 plus the run-out beyond the face end; plunge to the base Z; feed along the face to D/2 plus the run-out beyond the other end; rapid up.

Checks before any cut of a face (the operation is refused with the message): the tool is a dovetail cutter; the cutter angle is within 0.5 deg of the face angle; the cutting height is at least the undercut height; the cutter radius is more than the undercut depth. Checks of each pass against the stock as cut by the earlier passes and operations: the whole tool plunged to the pass start and lifted from the pass end is outside the stock (the end of the undercut is not open or the stock is not cleared); the neck and the shank swept along the pass are outside the stock. The swept cutting part is subtracted from the stock exactly.

## 16.4 3D operations

The 3D operations work on a height map of the part (the tapered ball nose is also taken): the highest Z of the part at every point of a grid with the **Sample interval (mm)** as the step, from the tessellation of the solid. The height of the tool centre at every grid point comes from the surface dilated by the tool profile (ball, bull nose and flat end mills), with one grid cell of margin. An undercut is not represented (one Z per point).

| Field (all three) | Function |
|---|---|
| **Boundary** | **Stock** (the stock area), **Picked faces** (the area of the faces), Face: **Bounding box** of the faces |
| **Boundary adjust (mm)** | The boundary offset; positive outward |
| **Sample interval (mm)** | Grid of the height map and step along the lines |
| **Depth offset (mm)** | Left on the surface |
| **Optimize** | Collinear points removed |

### 3D Pocket

The volume above the picked faces cleared in levels; at every level the region is where the tool centre may stand over the surface, cleared with **Pattern**, **Step over (% of D)**, **Angle (deg)**, **Cut mode**, **Entry** and **Helix pitch (mm)** as a Pocket Shape.

### 3D Surface

The tool follows the surface along a pattern: **Line**, **ZigZag**, **Circular**, **Circular ZigZag**, **Offset**, **Spiral** with **Step over (% of D)** and **Angle (deg)**; **Layer mode** **Single pass** on the surface or **Multi pass** (levels clipped at the surface); **Boundary enforcement** keeps the tool inside the boundary. A change of Z larger than two sample intervals between consecutive points is taken as a step: the tool moves at the higher Z over the lower point before descending.

### Waterline

At every level from the start depth to the final depth the contours where the tool touches the surface, inside the boundary; **Cut mode**; **Clear last level** clears the last level as a pocket.

## 16.5 Dressups

A dressup changes the moves of its operation. The dressups of an operation are applied in the order Dogbone, Tag, Lead in/out, Ramp entry, Boundary, Axis map. A dressup is added to the selected operation (or to the operation open in the command window) from **Dressup ▾**; its command window has the fields below; its row in the tree is under the operation.

| Dressup | Fields |
|---|---|
| **Tag** | Holding tags on the lowest closed loop of the operation: **Tags** spaced along the loop, **Width (mm)** between the tool edges, **Height (mm)**, **Angle (deg)** of the flanks (90: vertical). The tool rises over a tag and comes down behind it |
| **Ramp entry** | The plunges to a level replaced by ramps along the path at **Angle (deg)**: **RampMethod1** (ramp down along the path, back to the start at the level, then the path), **RampMethod2** (ramp down, then the path on from there), **ZigZag** (back and forth over the ramp length), **Helix** (a helix at the start point). **Ramp from the start depth**; **Ramp feed (mm/min)** (empty: the ramp feed of the operation or the tool controller, else the plunge feed) |
| **Lead in/out** | **Style** **Arc**, **Tangent** or **Perpendicular**, **Length (mm)** (the arc radius or the line length), **Lead in**, **Lead out**, **Extend (mm)** along the path |
| **Dogbone** | Inside corners of the path cut out so that a square part fits: **Style** **Dogbone** (along the bisector), **T-bone horizontal**, **T-bone vertical**, **T-bone long edge**, **T-bone short edge**; **Side** of the material (**Left**, **Right**); **Incision** **Adaptive** (to the corner), **Fixed** (the tool radius), **Custom** (**Length (mm)**) |
| **Axis map** | A linear axis written as the rotary axis A for a part on a rotary axis: **Mapped axis** **Y to A** or **X to A**, **Radius (mm)** of the part on the axis, **Invert**. A = coordinate / (2 π radius) × 360 deg. The arcs become lines of at most 1 mm. The view and the simulation keep the unmapped coordinates; the posts write `A<deg>` in place of the mapped axis |
| **Boundary** | The path cut at the rectangle **X min (mm)**, **X max (mm)**, **Y min (mm)**, **Y max (mm)**; **Keep inside** keeps the part of the path inside the rectangle (else outside); the tool lifts at the cuts |

## 16.6 Supplemental, Copy and Array

| Operation | Fields and G-code |
|---|---|
| **Fixture** | **Work offset** `G54` to `G59`; **Shift X (mm)**, **Shift Y (mm)**, **Shift Z (mm)**. The generic post writes the G-code; the Estlcam controller has no coordinate systems, so the Estlcam post shifts the coordinates of the following moves by the shift and writes a comment |
| **Comment** | **Text**, written as a comment in parentheses (parentheses in the text become brackets) |
| **Stop** | `M00`, or `M01` with **Optional stop (M01)**; the spindle is stopped before `M00` |
| **Custom** | **G-code** lines written as they are |
| **Hop** | A rapid lift to **Height Z (mm)** (job coordinates; empty: the clearance height) |
| **Probe** | A grid of probe points: **Points X**, **Points Y** over **X min (mm)** to **Y max (mm)** (empty: the stock), from **Start Z (mm)** (empty: stock top + 2 mm) down to **Probe to Z (mm)** (empty: stock top − 5 mm) at **Probe feed (mm/min)**: `G0 X Y Z<start>`, `G38.2 Z<depth> F<feed>`, `G0 Z<start>` per point in a zigzag order. **Output file**: LinuxCNC writes the results with `(PROBEOPEN <file>)` and `(PROBECLOSE)`. The Estlcam post writes a comment and `M00` per point (the sanity check warns) |
| **Copy** | The moves of **Operation** (an earlier cutting operation) again, with its tool controller |
| **Array** | The moves of **Operation** repeated: **Type** **Linear** with **Copies** (including the base position), **Offset X (mm)**, **Offset Y (mm)**; **Polar** with **Copies** over **Angle (deg)** about **Centre X (mm)**, **Centre Y (mm)**. The base operation stays in the job; it is set inactive when its position is in the array |

## 16.7 Simulation, sanity check and results

**Simulate** computes the operations in the list order. The stock of an operation is the stock left by the earlier operations. An operation that fails leaves the stock unchanged; the later operations run on that stock. The preview of the command window runs the operations up to the edited one; the results of the earlier operations are kept on the server, so a change of one operation recomputes that operation and the later ones.

The stock is cut as follows. The moves are grouped by Z level (a sloping move in pieces of 1 mm assigned to the nearest level at or below). At each level the path of the tool centre is swept by the cutting profile of the tool as a stack of slabs (a flat end mill: a cylinder of the tool radius; a ball end mill, a V bit or a drill: steps of the profile of at most 0.3 mm or D/8 radius change, each step with its larger radius) from the level up to the cutting height, and subtracted from the stock; the neck and the shank over the path are checked against the stock before the level is cut (the message "the neck or shank of the tool collides with the stock" refuses the operation). The part material cut by an operation (its gouge) is the part inside the stock before the operation less the part inside the stock after it; a gouge above 0.05 mm^3 is reported and marked ⚠ in the tree. An engraving operation (Engrave, Deburr, Vcarve) cuts the part by design: its volume is reported as cut from the part.

The Undercut operation cuts the stock with the exact swept solids of the dovetail cutter. Thread milling cuts the stock by the thread ring. The 3D operations and Vcarve are also simulated on a height map of the stock with the tool profile (removed volume, gouge and the material left over the part within the boundary, on the grid of the sample interval). 3D Surface and Vcarve cut the solid stock by the cut surface of the height map: the grid cells where the height map was lowered (with one cell of margin, sampled to at most 100 points per side) form a triangulated solid from the cut surface up to above the stock, which is subtracted from the stock; when that solid cannot be made, Vcarve cuts by the envelope of its regions and 3D Surface leaves the solid stock unchanged (a message says which). 3D Surface also shows the cut surface in the view (**3D surfaces**); Waterline and 3D Pocket cut the solid stock by their levels. The height map leaves up to one grid cell of material along steep walls.

The properties of an operation after a run: ok or error with the messages; the resolved heights (clearance, safe, start, final, step); the removed volume, the material left (pockets), the gouge, the cut and rapid lengths, the cycle time (feeds and the rapid speeds of the setup sheet), the feeds, the spindle speed and the number of moves; a table of the levels with **Z (mm)**, **Length (mm)** of the cut moves, **Removed (mm^3)** and, with a gouge, **Gouge (mm^3)** (the part material in the slabs of the level). With a gouge the properties also list **Gouges**: each place of part material cut (the largest 20) with **Volume (mm^3)**, its centre in job coordinates and in machine coordinates, and the first cutting move whose tool reaches its bounding box (the move number in the toolpath, its start and end points). A click on a row centres the view on the place. The view draws the part material cut in pink over the part, with a point at each centre. The status line after **Simulate** gives the number of operations, the cycle time, the volume of the stock outside the part (films thinner than 0.02 mm left out) and the volume of the part cut away.

**Sanity check** lists errors, warnings and information in the properties panel: no part chosen, a Probe with the Estlcam post, no tool controller, a controller whose bit is not in the library or whose feeds are 0, two controllers with one tool number, an operation without a controller or without base geometry, a final depth not below the start depth, a controller spindle speed outside **Spindle min (rpm)** to **Spindle max (rpm)**, a controller feed above **Max feed (mm/min)**, a copy of an operation that is not in the job, a stock that does not cover the part, an empty output file name, and after a run the errors and gouges of the operations. **Simulate** shows the sanity check when it has errors or warnings.

### Machine and playback

**Machine** in the tree holds the router model; **Show ▾** **Machine** draws it. The machine fields are the same for all jobs (`config.json` `cam_machine`, **Save machine**): **Travel X (mm)**, **Travel Y (mm)**, **Travel Z (mm)**, **Table X (mm)**, **Table Y (mm)**, **Table thickness (mm)**, **Travel start X on the table (mm)**, **Travel start Y on the table (mm)**, **Tool tip at the top of Z (mm above the table)**, **Gantry clearance (mm above the table)**, **Spindle diameter (mm)**, **Spindle length (mm)**. Machine coordinates: the table top at Z 0, the table corner at X 0, Y 0. **Job on the table**: **Machine zero X on the table (mm)** and **Machine zero Y on the table (mm)** place the machine zero X Y of the job on the table (saved with the job; **Default**: the stock corner 20 mm from the start of the travel); the stock bottom stands on the table top.

The view shows the base, the table, the rails, the gantry (moves in Y), the carriage (X), the Z slide with the spindle and the tool, and the travel of the tool tip as a green box. After a run the travel check lists the moves outside the travel (first operation and point) and the range of the tool tip in machine coordinates; the **Machine** row shows ✗ when moves are outside.

The playback bar at the bottom of the view appears after a run: **▶** plays the toolpaths with the tool (and the machine when shown) at the feeds and the rapid speeds of the setup sheet, × the speed (**×1**, **×5**, **×20**, **×100**); the slider sets the position; the line gives the operation, the time and the tool tip position in job coordinates. The playback moves the tool; the stock is shown as computed by the run.

## 16.8 Post process

**Post process** runs the operations and writes the G-code file to the **G-code folder** (empty: `cam/` of the project; no project open: download) under the **File name** of the output (empty: `<job>.nc`). A file of that name is overwritten after a question. **Download G-code** sends the file to the browser. An operation with an error gives no file. **Inspect G-code** shows the G-code of the selected operation (no selection: the whole job) in a window in the view.

The post-processors write mm, absolute machine coordinates with three decimals and a decimal point, parentheses comments, a comment with the machine zero in job coordinates, per cutting operation a comment with the type, the name and the tool controller, a tool change when the tool number changes, the moves as rapid `X Y Z`, feed `X Y Z F<feed>` and arcs `X Y Z I J F<feed>` (I and J from the start point of the arc, Z along the arc for a helix); the feed word is written when the feed changes.

| Post-processor | File |
|---|---|
| **Estlcam controller** (default) | The commands of the Estlcam controller (https://www.estlcam.de/steuerung_cnc_programme.php): `G00`, `G01`, `G02`, `G03` with the G-code on every move line, one G-code and one M-code per line; `M06 T<n>` at a tool change (the controller stops for the manual tool change; the tool setter routine runs from the controller), `S<rpm>`, `M03`, `G00 Z<clearance>`, the moves, `M05` before a tool change and at the end; `M00` and `M01` for a Stop; a dwell and a fixture as comments (the fixture shift applied to the coordinates); at the end `G00 Z<clearance>` and the comment `(end)`. No unit, plane, coordinate system or program end commands |
| **Generic (G21 G90 G54, M30)** | `%`, `G21 G90 G17 G40 G49 G54`, `G94`; `T<n> M6`, `S<rpm> M3` (`M4` for a CCW controller), `M8` / `M7` for the coolant of the setup sheet, `G0 Z<clearance>`, the moves as `G0`, `G1`, `G2` and `G3`, `G4 P<s>` for a dwell, `G54` to `G59` for a fixture, `M0` and `M1` for a Stop, `G38.2` for a Probe, `M5`, `M9`; at the end `G0 Z<clearance>`, `M30`, `%` |
| **GRBL 1.1** | `G21 G90 G17 G94`; no tool changer: a tool change is a comment with the tool and `M0`; otherwise as the generic post (no canned cycles); at the end `M30` |
| **LinuxCNC** | `G21 G90 G17 G40 G49 G54 G64 P0.01`, `G94`; `T<n> M6` and `G43 H<n>`; canned cycles of Drilling ([Drilling](#drilling)); Probe with `(PROBEOPEN <file>)` / `(PROBECLOSE)`; at the end `M2` |
| **Mach3 / Mach4** | `%`, `G21 G90 G17 G40 G49 G80 G54`, `G94`; `T<n> M6` and `G43 H<n>`; canned cycles; at the end `M30`, `%` |

A Hop is written as `G0 Z<height>`. The moves of an Axis map dressup are written with `A<deg>` in place of the mapped axis.

## 16.9 Job template

**Export template** downloads the job as `<job>.camtemplate.json`: the setup sheet, the tool controllers, the post-processor, the stock, the machine zero and the operations without their base geometry. **Import template…** applies a template file to the open job: its setup sheet, controllers, post-processor, stock, machine zero and operations replace those of the job (the base geometry of the operations is empty afterwards, the operations get new ids).

## 16.10 Files

| File | Content |
|---|---|
| `work/<name>.cam.json` | The job: `name`, `source` (the part), `stock`, `origin`, `setup`, `tools` (the controllers), `post`, `output`, `operations` (id, name, type, active, tc, comment, the heights and depths, dressups, the fields of the type, faces as face keys and edges as edge keys of the part, points, sketch name, text), `next` |
| `<name>.sccam` | Document file of the job ([section 2.2](02-files.md#22-document-files)); the part is in `uses/` |
| `cam/<name>.nc` | The G-code file |
| `config.json` `cam_tools` | The tool bit library |

A job saved by an earlier version (stock as `top`, `sides`, `bottom`; `clearance`; operations with `tool` and `suppressed`; `drill`; profile `tabs` and `ramp_angle`) is read in the current form: offsets, a setup sheet, tool controllers made from the tool ids, `drilling`, Tag and Ramp entry dressups.

The faces of an operation are stored as face keys (centre, normal, area) and the edges as edge keys (midpoint, length) of the part. A face or an edge is found again after a rebuild of the part by its key (within 0.05 mm); one that is not found is left out, and an operation without geometry reports it.

## 16.11 FreeCAD CAM workbench correspondence

| FreeCAD | ShinyCAD CAM |
|---|---|
| Job (Model, Stock, SetupSheet, Tools, Operations, Output) | The job tree ([section 16.1](#161-job-tree)) |
| ToolBit library, ToolController | Tool bits ([section 16.2](#162-tool-bits-and-tool-controllers)), tool controllers |
| Profile, Pocket Shape, Drilling, Face, Helix, Adaptive, Slot, Engrave, Deburr, Vcarve, Thread milling | The operations of [section 16.3](#163-operations) |
| 3D Pocket, 3D Surface, Waterline | [Section 16.4](#164-3d-operations) |
| Tag, RampEntry, LeadInOut, Dogbone, Boundary, AxisMap dressups | [Section 16.5](#165-dressups) |
| Fixture, Comment, Stop, Custom, Probe, Hop, Copy, Array | [Section 16.6](#166-supplemental-copy-and-array) |
| Simulator, Sanity check, Inspect G-code, Post process, Export template | [Sections 16.7](#167-simulation-sanity-check-and-results) to [16.9](#169-job-template) |
| Pocket (legacy), Shape (legacy) | Not available |
| Undercut | Added: the dovetail cutter operation |
| Job placement (Set orientation, model placement) | Model placement by constraints to the datum planes and axes ([Model placement](#model-placement)) |
| Machine (Camotics simulation) | The router model and the playback ([Machine and playback](#machine-and-playback)) |

[Contents](../README.md) · [← 15. Limitations](15-limitations.md)
