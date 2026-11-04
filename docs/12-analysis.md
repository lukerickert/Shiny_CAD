[Contents](../README.md) · [← 11. Assembly](11-assembly.md) · [13. Explicit →](13-explicit.md)

# 12. Analysis

The **Analysis** tab runs a static (linear, or nonlinear with contact, plastic and hyperelastic materials and large deformation), modal or linear buckling analysis with CalculiX (`ccx`, version 2.21). The model holds the bodies of a saved assembly or part, shells (the surface bodies of the parts and the surface components of STEP files), plates, beams, rods and fasteners. Plates and members are defined in the tab; a model of members and plates needs no geometry. The CalculiX input file, the result files and a text report are written to `analysis/<Name>/` of the project.

Units: mm, N, s, t (tonne): stress and pressure MPa (N/mm^2), moment N mm, line load N/mm, acceleration mm/s^2. Densities are entered in kg/m^3 (converted to t/mm^3).

The panel at the right is 480 px wide; the bar at its left edge changes the width (kept in the browser).

## 12.1 Solver

**Solver (ccx)** under **Settings** is the path of the CalculiX executable (written to `config.local.json` > `ccx_path`). When it is empty, the program uses the first `ccx*.exe` in `solvers\` of the program ([section 1.1](01-installation.md#11-solvers)), `ccx` on PATH, or `ccx_static.exe` / `ccx_dynamic.exe` of a `PrePoMax*` folder (for example `PrePoMax v3.0.0 RC2`) in `Program Files`, `%LOCALAPPDATA%`, the user folder, its `Desktop`, `Downloads` and `Documents`, or the root of the system drive. The line below the field gives the executable in use. `OMP_NUM_THREADS` and `CCX_NPROC_STIFFNESS` are set to the number of processor cores.

## 12.2 Controls

| Control | Function |
|---|---|
| **File ▾** | Project header, **Analysis** (saved analyses of the open project), **New**, **Save**, **Save as…**, **Rename…**, **Open run folder** (`analysis/<Name>/`), **Write input file** (mesh and `job.inp` without solving) |
| **Geometry** | Saved assembly or part of the project, or **(none: members and plates)**. A part is one body. The analysis uses the saved file of the assembly. The sketches of a part that no feature of the part uses are drawn (purple lines and points); a part with sketches only is not a body. The surface bodies of a component are shells ([section 12.3](#123-model)), drawn translucent in their colour of the Part tab (shells set to **off** faint). Parts are imported and placed in the Assembly tab (**Add part**, **Add STEP**, **Position**, mates, **Drag**, **Move 2 pts**, [section 11](11-assembly.md#11-assembly)) and the assembly is the geometry. Member ends and plate points snap to the sketch points ([section 12.4](#124-members)) |
| **Update** | Loads the geometry again from the saved assembly and parts; the mesh and the results of the old geometry are cleared. The server compares the assembly file and the files of its parts (and their imported STEP files) with the loaded geometry when the tab is shown, every 4 s and when the window gets the focus; a change marks **Update** orange. Face, edge and node set references keep their face and edge numbers |
| **Mesh** | Meshes the bodies and shells, writes `job.inp` and shows the mesh (**Show** **Mesh**). Supports are not required: supports, loads, fasteners and members without their targets or points are left out, and a support or load whose target is not found is listed as a warning. The status line gives the node and element counts and the element types per body. **Edges** draws the element edges (quadrangle faces of hexahedra without diagonals) |
| **Solve** | Meshes, writes `job.inp`, runs CalculiX and shows the results. The status line gives the stage and the time. **Show** changes to **Mesh** when the model is built, and stays there when the solve stops at an error in a support or load (the mesh holds the items that could be applied) |
| **Stop** | Stops the solver |
| **Beam**, **Rod** | Adds a member: pick end A, then end B in the view ([section 12.4](#124-members)). The member gets the section, material, group, up vector, elements and hinges of the selected member of the same kind, else of the last one. After end B the next member starts with the same properties; Esc (or another toolbar command) ends the drawing and removes the member without ends. Esc on the first member keeps it for typed coordinates. **Sketch beams** uses the same properties |
| **Sketch beams** | Adds a beam on each straight line of the sketches of the geometry. Lines that already have a member are skipped. Members meeting at a point share the node |
| **Plate on face**, **Plate by points** | Adds a plate ([section 12.5](#125-plates)) |
| **Fastener** | Adds a fastener ([section 12.6](#126-fasteners)) |
| **Ref. point** | Adds a reference point and starts the pick of its location ([section 12.6.1](#1261-reference-points)); Esc: typed coordinates |
| **Support** | Adds a support at the selected member end or reference point; else on the selected faces, edges, bodies or reference point ([section 12.2.1](#1221-selection)); with nothing selected, starts a selection for the support (a click on a member end takes the end) ([section 12.7](#127-supports)) |
| **Load** | Adds a force at the selected member end; else on the selected faces, edges (line load, 1 N/mm downwards) or reference point; with nothing selected, starts a selection for the load (a click on a member end takes the end, a click on a member gives a line load of 1 N/mm downwards) ([section 12.8](#128-loads)) |
| **Show** | **Model** (bodies, members, fasteners, supports and loads), **Mesh**, **Results** |
| **Result** | **von Mises stress**, **Displacement \|u\|**, **ux**, **uy**, **uz**, **PEEQ (equivalent plastic strain**, plastic materials) as contours on the deformed shape, with the colour scale (12 bands) in the upper left of the view |
| **State** | **Total**; with a fastener preload also **Step 1 preload** and **Step 2 loads**; nonlinear step: **End of the step** and **Increment k: time t**, one entry per output increment (at most 40, evenly spaced); modal and buckling: **Mode 1: f Hz** or **Mode 1: factor x**, one entry per mode |
| **Scale** | Deformation scale (empty: the largest displacement is drawn as 5 % of the model size) |
| **Undeformed** | Outline of the undeformed mesh |
| **Supports and loads** | Draws the supports and loads ([section 12.7.1](#1271-display-of-supports-and-loads)) |
| **Iso**, **Front**, **Top**, **Right**, **Fit**, **Edges**, **Axes** | As in the Assembly tab |
| **Select** | Selection toolbar of the view ([section 12.2.1](#1221-selection)) |
| **Shell thickness** | **Show** **Mesh** and **Results**: shell elements drawn as slabs of the thickness **t** of their shell row or section, placed by **Position** (mid-surface, positive or negative side of the element normal; the normal at a node is the area-weighted mean of the element normals of the shell or section at the node), with side faces at the free edges; results colours of the mid-surface nodes on both surfaces |

A click on a member, fastener, support or load in the 3D view selects it in the panel. A click within 10 px of a member end selects the end: the end is drawn as a large orange ball and **Members** shows its coordinates. A click on empty space clears the selection. The member end, point, edge or face under the cursor is marked orange before a click (cursor: pointer for selection, crosshair during a pick). During the pick of a support or a load, an edge of a component within 8 px of the cursor is taken before the face under it. Esc cancels a pick.

### 12.2.1 Selection

| Control | Function |
|---|---|
| **Faces**, **Edges**, **Bodies**, **Ref. points** | Item types that clicks and boxes in the view take (several at once). With no type on, a click selects members, supports, loads and bodies for their panels |
| **Box** | Left drag draws a box (left drag no longer rotates; the middle and right buttons pan). Drag to the right: the items fully inside the box (window, solid outline). Drag to the left: the items inside or crossing the box (crossing, dashed outline). Ctrl or Alt held at release: the items leave the selection. Items hidden behind others are taken |
| **Clear** | Clears the selection |
| **Suppress**, **Unsuppress** | Sets the selected bodies, and the section of each selected face (a face in no section: its body), to **off** (left out of the mesh and the solve, drawn faint); **Unsuppress** sets them back to their model before **Suppress** (kept as `prev_off`) |
| Count | Number of selected faces, edges, bodies and reference points |
| **Done**, **Cancel** | Shown during a selection for a target: **Done** (or Enter) gives the selection to the target, **Cancel** (or Esc) ends it without change |

A click toggles the item under the cursor: a reference point within 10 px, an edge within 8 px, else the face (**Faces**) or its body (**Bodies**: the solid of the component or the surface body of the face). Selected faces are orange, faces of selected bodies light orange, selected edges red, selected reference points orange. Esc turns the types off and keeps the selection.

Targets take the selection: **Support**, **Load**, **Pick** of a support or load, **Add faces** and **Add edges** of a reference point, **Selected faces**, **Selected edges** and **Bodies** of the node sets, **New from selection** and **+** of the sections, and **Add contact** and **Set from selection** of the contact pairs. With items of the accepted types selected, the target takes them at once; else the target sets the types, and clicks and boxes select until **Done** or Enter. A target that takes faces only takes the faces of the selected bodies. **Show** of a support or load selects its target in the view.

## 12.3 Model

| Panel | Function |
|---|---|
| **Panels** | Check boxes that show or hide the **Sections**, **Node sets**, **Members**, **Plates**, **Fasteners**, **Reference points**, **Springs**, **Joints**, **Equations** and **Contact** cards; kept in the analysis (`panels_hidden`). A hidden card with items shows their number. Hidden items still act in the solve |
| **Settings** | **Solver (ccx)**; **Analysis type** and **Number of modes** ([section 12.10](#1210-modal-and-buckling-analysis)); **Default material**; **Mesh** ([section 12.3.1](#1231-mesh-settings)); **Bonded contact between touching bodies**: touching solid bodies of one mesh strategy are meshed with shared nodes at the contact faces (gmsh fragment); plates and bodies of other strategies are tied (`*TIE`) to the faces they touch; bodies of a contact pair are meshed apart and not tied ([section 12.7.2](#1272-contact)). Without it the bodies are connected only by members, fasteners and contact pairs; **Nonlinear step** ([section 12.3.2](#1232-materials-and-nonlinear-step)) |
| **Materials** | Name, E (MPa), nu, rho (kg/m^3), **Law**, **Library** ([section 12.3.2](#1232-materials-and-nonlinear-step)). **Add material**, × deletes. **Material** drop-downs (bodies, shells, sections, members, plates, fasteners): **(default: ...)** with the default material, the model materials as `name - library entry` or `name - law, E MPa, nu, rho kg/m^3`, and under **Library** the library entries not used by a model material; choosing a library entry adds a model material of that entry (named after the entry without the bracketed part) and assigns it |
| **Shells** | One row per surface body of a component (**Component / surface body**): **Model** **shell** or **off**; **t (mm)** thickness (empty: 10 mm); **Position** **mid** (the surface is the mid-surface), **positive** or **negative** (the shell lies on that side of the surface, along the element normal; `*SHELL SECTION` `OFFSET` 0.5 or -0.5); **Material**; **Size (mm)** element size of the shell; **Layers** (S8R shell elements only, 1 to 20; empty: 1): `*SHELL SECTION, COMPOSITE` with that number of layers of t / n of the material, each layer with its own integration points through the thickness (other shell elements: one layer and a warning). The faces of all shells are meshed together (**Shell elements**, **Shell mesh** in [section 12.3.1](#1231-mesh-settings)); with **Bonded contact between touching bodies**, shells that touch or cross share their nodes on the common lines (gmsh fragment), and shell nodes on the faces of solid bodies are tied to them (`*TIE`). A face shared by two shells belongs to the shell listed first |
| **Sections** | Groups of faces of the surface bodies of any components with one thickness, position, material and element size (one ELSET each, named by the section). **From surface bodies**: one section per surface body, with the values of its **Shells** row. **By geometry**: connected faces on the same plane (within **angle**, deg) or on the same cylinder form one section, named `PLATE_Z<z>` (plane normal to z), `WEB_X<x>` or `WEB_Y<y>` (plane normal to x or y), `PLANE`, `CYL_R<r>` (cylinder of radius r) or `SURF`; a second section of the same name gets `_2`. **New from selection**: a section of the selected faces of shells (selected faces of solids are left out). **Remove all** deletes the sections. **Select faces**: turns the **Faces** type of the selection on or off ([section 12.2.1](#1221-selection)); **Select unassigned** (faces in no section), **Select all**, **Invert**, **Clear selection**. Each section takes two lines: colour of the faces in the view, name, number of faces, **Sel** (selects them), **+** (adds the selected faces), × (deletes the section); **Model** **shell** or **off**, **t (mm)** (empty: 10 mm), **Position**, **Material**, **Size (mm)**, **Layers** (as in **Shells**). Sections set to off are drawn pale. A face belongs to one section; faces in no section take the **Shells** row of their surface body. Selected faces are orange |
| **Node sets** | Named groups of mesh nodes. **Plane**: the nodes within the tolerance (mm) of the plane x, y or z = value. **Section edges**: **free edges** (element edges of the section or shell bounding one shell element of the whole model) or **outline** (element edges bounding one element of the section or shell); a new node set takes the first section, else the first shell. **Selected edges**: the nodes of the selected edges (**Select edges** turns the **Edges** type on or off). **Selected faces**: the nodes of the selected faces of solids and shells and of the faces of the selected bodies (**Select faces** in **Node sets** or **Sections**). **Bodies**: all nodes of the checked bodies (solids, shells, sections; a new node set takes the selected bodies); a shell whose faces are in sections gives the nodes of those faces. **Set** replaces the edges or faces with the selection, **Show** selects them in the view, **Support** adds a support with the node set as target ([section 12.7](#127-supports)) |
| **Bodies** | One row per component of the geometry with a solid: **Model** **solid** (meshed with the strategy in **Mesh**), **plate** (C3D8I through the thickness, C3D6 for the triangles left by the quadrangle mesh) or **off** (left out); **Mesh**: the strategy of the body (**tet**, **hex**, **hex sub**; in brackets: the default of **Settings**); **Material**; **Size (mm)** of the elements of the body |

### 12.3.1 Mesh settings

| Field | Function |
|---|---|
| **Strategy** | Default for the solid bodies. **Tetrahedra (free)**. **Hexahedra, structured (block cells)**: transfinite mesh; every cell of the body must be a block (6 faces with 4 edges each) or a prism (wedge elements); bodies are cut into such cells with **Partition** in the Part tab; a body with other cells stops the mesh with its name. **Hexahedra by subdivision**: each tetrahedron of a free mesh is divided into four hexahedra (any geometry; element distortion is higher) |
| **Tetrahedra** | **C3D10** (second order) or **C3D4** (first order) |
| **Hexahedra** | **C3D8I** (incompatible modes), **C3D8**, **C3D8R** (reduced integration), **C3D20**, **C3D20R** (second order). Wedges in prism cells: C3D6, or C3D15 with C3D20 and C3D20R |
| **Element size (mm)** | Largest element size (empty: model size / 20). **Size (mm)** in **Bodies** sets it per body |
| **Minimum size (mm)** | Smallest element size (empty: element size / 5) |
| **Elements per 360 deg of curvature** | Refinement on curved faces (empty: 12; 0: off) |
| **3D algorithm** | **Delaunay**, **Frontal**, **HXT** (parallel Delaunay) for the tetrahedra |
| **Optimise the mesh** | gmsh optimisation of the elements |
| **Shell elements** | **S4** (CalculiX expands it to C3D8I elements), **S8R** (second order) or **S3** (triangles). The triangles the quadrangle mesh leaves are S3 (S6 with S8R) |
| **Shell mesh** | gmsh surface algorithm of the shells: **Quasi-structured quadrangles** (the algorithm makes elements of about half the size it reads; the size is set at twice the element size), **Frontal-Delaunay for quadrangles**, **Delaunay, recombined**, **Triangles only** (S3). A face with an element edge longer than 3 x its element size after **Quasi-structured quadrangles** or **Frontal-Delaunay for quadrangles** (for example a cylindrical face meshed without inner nodes) is meshed again with **Delaunay, recombined**; the mesh warnings list the faces |
| **Structured quadrangles on axis-aligned rectangles** | Shell faces that are rectangles with edges along x, y or z get a structured quadrangle mesh (transfinite). The coordinates of all curve ends of the shells form an interval grid along each axis; each interval gets ceil(interval / size) divisions, at least **Min divisions per interval**. With **Quasi-structured quadrangles** and structured faces, the other faces are meshed with **Frontal-Delaunay for quadrangles** |
| **Min divisions per interval** | Lowest number of elements between two grid coordinates (empty: 1) |
| **Section sizes** | **local, free transition**: a curve takes the smallest size of the shells and sections of its faces; a face with sizes that differ on opposite sides is meshed free. **along the grid, all structured**: each grid interval takes the smallest size of the curves along it, and all rectangles are structured |
| **Fuzzy (mm)** | Tolerance of the general fuse of the shells (gmsh fragment, `Geometry.ToleranceBoolean`): faces and edges closer than this are joined (empty: 0, exact) |

The solid bodies of one strategy are meshed together (shared nodes with **Bonded contact**); bodies of different strategies, and plates, are tied where they touch. Body weight is distributed with the consistent nodal fractions of the element type. The report gives the mesh settings and the element counts per body and type.
| **Members** | List and properties of the members. See 12.4 |
| **Plates** | **Plate on face**: pick a planar face of a body. **Plate by points**: click the outline points in the view (Esc ends) or type them. See 12.5 |
| **Fasteners** | **Fastener**: pick face A (head side: hole or bearing face), then face B (nut or thread side). See 12.6 |
| **Supports** | **Support**: pick the face, or choose a member end in the panel. See 12.7 |
| **Loads** | **Load**: pick the face; **Type** changes the load. See 12.8 |
| **Results** | Tables of the selected **State**, **Report**, **Download report**, **Open run folder**. See 12.9 |

A plate body must be a prism of its largest planar face (the opposite face has the same area at the thickness distance). The face is meshed with quadrangles and the mesh is extruded through the thickness (one element layer).

### 12.3.2 Materials and nonlinear step

| Control | Function |
|---|---|
| **Law** | **linear elastic** (`*ELASTIC`); **plastic, isotropic hardening** and **plastic, kinematic hardening** (`*ELASTIC` and `*PLASTIC, HARDENING=ISOTROPIC` or `KINEMATIC`); **hyperelastic Neo-Hooke** and **hyperelastic Mooney-Rivlin** (`*HYPERELASTIC`) |
| **Library** | ORC\*\*3 material library ([section 13.5](13-explicit.md#135-build)): E, nu, rho and the hardening table of the material (DNVGL curves as given; Johnson-Cook entries sampled as a + b eps_p^n at 16 plastic strains from 0 to 1, without the rate term). A library material sets **Law** to plastic (isotropic) when it has a hardening curve; E, nu, rho and the table are then not editable |
| Hardening table | Plastic materials: one row per line: yield stress (MPa), plastic strain; the first row at plastic strain 0 (the yield stress). New plastic material: 250 MPa at 0, 300 MPa at 0.1 |
| **C10**, **C01**, **D1** | Hyperelastic materials: C10, C01 (Mooney-Rivlin) in MPa, D1 in 1/MPa (bulk modulus 2 / D1) |
| **Large deformation (NLGEOM)** | Equilibrium in the deformed geometry; always on with a hyperelastic material |
| **Initial increment**, **Max increment**, **Min increment** | Increment sizes as fractions of the step (step time 1); defaults 0.1, 0.25, 1e-5 |
| **Max increments** | Largest number of increments of a step (default 100) |
| **Output every n increments** | Results (`*NODE FILE`, `*EL FILE`, `*NODE PRINT`, `*EL PRINT`) every n increments (default 1) |

A nonlinear static step (`*STEP, INC=n` with `*STATIC` increments) is used with a contact pair other than tied, a plastic or hyperelastic material, or **Large deformation**; the heading of **Nonlinear step** states whether it is used. Loads and prescribed displacements are ramped linearly over the step. Beams and fasteners (U1 elements) are linear only: a nonlinear solve with members of kind beam or fasteners is refused (**Mesh**: a warning). Rods (T3D2) take any law. The report lists the law of each material, the hardening tables, the hyperelastic constants and the increment settings.

## 12.4 Members

The **Members** panel has two tables. **Groups**: name, kind, section, material and the number of members of each group; a click selects a group and opens its fields (**Name**, **Kind**, **Material**, **Section** and its dimensions); × deletes the group (its members keep the values). **Add group** makes a group from the properties of the selected member (and adds the member to it), or a PIPE 48.3 x 3.2 beam group.

**Members** is a grid with one row per member: **Member** (name), **Group**, **Kind** (beam or rod), **Section** (RECT, ROUND, PIPE, BOX, I, GENERAL), **Dimensions (mm)** (the section dimensions in the order of the section, for example `48.3 x 3.2` for PIPE d x t), **Material** (empty: the default material), **Elem.** (empty: automatic), **Hinge** (a, b, ab or empty) and **L (mm)**; × deletes the member. A member in a group takes kind, section and material from the group; these cells are grey and read-only.

| Action | Function |
|---|---|
| Click, drag, Shift+click, arrow keys | Select a cell or a range of cells; the row of the active cell is the selected member (its fields open below the grid) |
| Typing, double-click, Enter, F2 | Edits the active cell. Enter commits and moves down, Tab moves right, Esc cancels |
| **Group** cell | The name of a group; a new name makes a group from the properties of the member |
| Square at the corner of the selection | Drag down or up: the selected values are repeated in the rows dragged over |
| Ctrl+C, Ctrl+V | Copy and paste tab-separated text (also to and from a spreadsheet). One copied value pastes into every selected cell |
| Delete | Clears **Group**, **Material**, **Elem.** and **Hinge** in the selected cells |

A value that is not allowed is refused and the status line gives the allowed values.

A member that lies on a plate (along an edge, or across the mid-surface within 0.51 times the plate thickness of a plate surface) is tied to the plate (`*TIE`, the member nodes follow the plate). Supported member nodes and member ends connected to a face are left out of the tie. This needs **Bonded contact between touching bodies**.

| Field | Function |
|---|---|
| **Name**, **Kind** | **beam**: CalculiX U1 elements (two nodes, six degrees of freedom per node, Euler-Bernoulli); **rod**: T3D2 elements (axial force only) |
| **End A**, **End B** | Coordinates (mm). **Pick**: the clicked point on a face, or an existing member end, plate point or sketch point within 10 pixels (members at one point share the node). **Centre**: the centre of the clicked face |
| **Connected to …** | Set by a pick on a face. The end is connected to the face by RBE3 equations: the end node moves with the weighted mean of the face nodes (weights: the nodal areas of the face). Clearing the check box leaves the end free |
| **Coupling** | **distributing (RBE3)**: the end moves with the weighted mean of the face nodes (the face deforms freely). **rigid**: the face nodes move rigidly with the end (u = u_end + rotation x r; at a rod end the face nodes take the end translation) |
| **Connection radius (mm)** | Only the face nodes within this distance of the end are connected (empty: the whole face). **Pick** on a face sets it to the larger section dimension (b, h or d); **Centre** leaves it empty |
| **Section** | **RECT** (b, h), **ROUND** (d), **PIPE** (d, t), **BOX** (b, h, t), **I** (b, h, tf, tw), **GENERAL** (A, I11, I22, J, c1, c2). The line below gives A, I11, I22 and J |
| **Section up vector** | Direction of the section depth h (local 2-axis), projected normal to the member. Local 1-axis = 2-axis x member axis. For a member parallel to the vector, the global X (or Y) axis is used |
| **Hinge** | Bending moments released at end A, end B or both ends; the translations and the torsion are connected. With both ends released, torsion is connected at one end |
| **Elements** | Elements along the member (empty: length / element size, at least 4). Rods have one element between nodes |

Members meet where their end points coincide (tolerance 1e-6 x model size). An end point of another member lying on a member splits it there. Line loads give consistent nodal forces and moments; the section forces between the nodes include the line load.

Section properties: I11 is the integral of x1^2 dA (bending in the local 1-direction), I22 the integral of x2^2 dA (bending in the local 2-direction). J of RECT: Roark formula; BOX: thin-walled closed section; I: sum of b t^3 / 3. The torsional stiffness of the U1 element is G (I11 + I22); J is used only in the report. The U1 shear factor is 1e7, giving bending without shear deformation.

## 12.5 Plates

A plate item is a layer of C3D8I elements (C3D6 for the triangles left by the quadrangle mesh) built in the tab. It is listed under **Plates**, drawn tan in the view, and its faces are picked for supports, loads, fasteners and member ends like the faces of a body.

The **Plates** panel has two tables, as **Members**. **Groups**: name, thickness, material, element size and the number of plates of each group; a click selects a group and opens its fields; × deletes the group (its plates keep the values); **Add group** makes a group from the selected plate (and adds the plate to it). **Plates** is a grid with one row per plate: **Plate** (name), **Group**, **Thickness (mm)**, **Material**, **Elem. size (mm)**, **Position** (mid, positive, negative) and **Geometry** (the face, or the number of outline points). The grid works as the member grid (selection, editing, **Group** cell with a new name making a group, fill square, Ctrl+C / Ctrl+V, Delete clears **Group**, **Material** and **Elem. size**). A plate in a group takes thickness, material and element size from the group; these cells are grey. The fields of the selected plate (outline points, face) open below the grid.

| Field | Function |
|---|---|
| **Name**, **Material** | |
| **Thickness (mm)** | Plate thickness |
| **Element size (mm)** | Element size of the plate (empty: the element size of the analysis) |
| **Position** | Outline points: **outline is the mid-surface**, **on the positive side** (normal by the right-hand rule of the point order), **on the negative side**. Face: **on the face (outside the body)**, **centred on the face**, **inside the body** |
| **Face**, **Pick** | Plate on a face: the planar face of a body; holes in the face are holes in the plate. The body itself can be **off** |
| **Outline points (mm)** | Plate by points: the corners in order (at least 3, in one plane); **Pick points** adds clicked points (snaps to member ends, plate corners and sketch points), **Add row**, × deletes a point |

With **Bonded contact between touching bodies**, each plate is tied (`*TIE`) to the faces of the bodies and plates it touches, within 0.51 x the larger plate thickness of the pair. A plate edge on the mid-surface of another plate (a T-joint of mid-surface plates) is tied to the nearer face of that plate. Of several touching faces of one body, the face with the fewest supported nodes is used.

## 12.6 Fasteners

A fastener is a U1 beam of diameter **d** (ROUND section) between face A and face B, on the axis of the first cylindrical face of the two (without a cylindrical face: the line between the face centres). Each end is connected to its face by RBE3 equations. Supported nodes of a face are left out of its equations.

| Field | Function |
|---|---|
| **d (mm)** | Diameter of the section. Default: the smaller hole diameter of the picked faces |
| **Preload (N)** | Axial force. The fastener is cut at mid-length: the axial displacement across the cut is a degree of freedom of an extra node (spring 1e-6 N/mm to ground); the other translations and the rotations are tied across the cut. Step 1 applies the preload as a force on this degree of freedom, without the loads. Step 2 applies the loads with this degree of freedom fixed (fastener length held). **Total** is the sum of both steps |
| **Material** | Material of the fastener |

The preload needs a load path between the clamped parts (bonded contact or another connection). Without one, the solve stops with "the preload has no reaction path".

### 12.6.1 Reference points

A reference point is a node with six components (ux, uy, uz, rx, ry, rz) coupled to the nodes of faces, edges and node sets, or not coupled. It is drawn as a violet octahedron with dashed lines to the centres of its faces and edges. **Add reference point** (panel) and **Ref. point** (toolbar) add a point and start the pick of its location (Esc: typed coordinates).

| Field | Function |
|---|---|
| **Name** | |
| **Location** | **typed coordinates** (x y z, **Pick**); **a point (picked or a reference point)**: P1; **point on a face + distance along the normal**: P1 picked on a face, **Normal** (the normal of the face at the point, editable), **Distance (mm)**; **between two points**: P1, P2 and **Fraction t from P1 to P2** (0.5: midpoint); **centroid of three points**: P1, P2, P3; **centre of the circle through three points**: P1, P2, P3 (for example three points on the edge of a hole); **centre of a face**: **Pick face** (area centroid; cylinder: the area centroid projected onto the axis); **centre of an edge**: **Pick edge** (circle: centre; line: midpoint) |
| **P1**, **P2**, **P3** | **picked point** (x y z, typed or **Pick**) or a reference point (the point follows it) |
| **Offset dx dy dz (mm)** | Added to the location (all but typed coordinates) |
| **x y z (mm)** | Resulting coordinates |
| **Coupling** | **rigid (all six)**: the coupled nodes move rigidly with the point; **kinematic, chosen components (RBE2)**: the checked translations of the nodes follow the rigid motion of the point, the checked rotations of beam nodes equal those of the point; **distributing (RBE3)**: the checked components of the point are the weighted mean motion of the nodes (face nodes weighted by tributary area, edge and node set nodes 1); **none**: the point is connected by springs, joints, equations, member ends or supports only |
| **Components** | ux uy uz rx ry rz of the kinematic and distributing couplings |
| **Faces**, **Edges**, **Node sets** | **Add faces** (faces, and the faces of bodies), **Add edges**: the selected items, or a selection until **Done** ([section 12.2.1](#1221-selection)); **Clear** removes faces, edges and node sets; **Node sets**: check the node sets ([section 12.3](#123-model)) |

Picked points: reference points, member ends, plate and sketch points, vertices within 10 px; mesh nodes within 10 px in **Show** **Mesh** and **Results**; points on edges within 8 px; points on faces. Vertices and edge points behind the face under the cursor (beyond the face point by more than 0.2 % of the visible height) are not taken. The point under the cursor is marked orange and its coordinates are shown next to the toolbar.

Supports and loads act on a reference point: select it (in the list or the view) and press **Support** or **Load**, pick it with **Pick** (within 10 px), or choose it under **or reference point**. Supports take six components (ux, uy, uz, rx, ry, rz); loads are a force (N) or a moment (N mm). A member end at the point follows the point (translations, and rotations at a beam end). Supported nodes and nodes already constrained are left out of the coupling (a warning in the report). The couplings are linear equations (`*EQUATION`); the rotations of a point are the translations of a second node at the point. A rotation of a point that nothing uses is held. A point that nothing connects stops the solve. The results list the displacement and rotation (rad) of each reference point.

### 12.6.2 Springs, joints and equations

| Panel | Function |
|---|---|
| **Springs** | **Add spring**. **End A**, **End B**: a reference point, **mesh node at a point** (x y z, typed or **Pick**: the mesh node nearest to the point), or **ground** (End B). **kx ky kz** (N/mm), **krx kry krz** (N mm/rad) in the global axes. CalculiX: one `SPRING2` element (`SPRING1` to ground) per component with a stiffness. Rotational stiffnesses need rotations at both ends (reference points) |
| **Joints** | **Add joint**. **Type**: **ball** (ux uy uz of B equal to those of A), **hinge** (ux uy uz and the rotations about the two axes normal to **Axis** equal; **From edge**: direction of a straight edge or axis of a circular edge), **weld** (all six equal), **chosen components equal**. **End A**, **End B** as for springs; rotations need reference points (or beam ends) |
| **Equations** | **Add equation**: sum of **Coefficient** x **Component** of **Point** = 0; **Add term**, × deletes a term. A term is a reference point or the mesh node nearest to a point |

Joints and equations are written as `*EQUATION`. The dependent term of each equation is the one with the largest coefficient whose component is not held or already dependent. The report lists the couplings, springs, joints and equations. Springs, joints and equations are drawn as green, orange and grey dashed lines between their ends; a joint has a ring at end B (in the plane normal to the hinge axis).

## 12.7 Supports

| Target | Type |
|---|---|
| Edge, face of a shell | **fixed**: all six components; **pinned**: ux, uy, uz; **symmetry X** (ux, ry, rz), **symmetry Y** (uy, rx, rz), **symmetry Z** (uz, rx, ry); **chosen components**; **prescribed displacement**; on a face of a shell also **normal to the face (planar)**. The translations act on all nodes of the edge or face, the rotations on its shell nodes (nodes of solid elements have no rotations: a warning in the report). The nodes of an edge are the mesh nodes of the bodies and shells of the component on the edge curve |
| Face | **fixed**: ux, uy, uz of all face nodes. **normal to the face (planar)**: displacement normal to the face (`*TRANSFORM`), 0 or **Normal displacement (mm, along the outward normal)**. **chosen components**: ux, uy, uz, rx, ry, rz as checked. **prescribed displacement**: the checked components prescribed (mm, rad), the others free. With rx, ry or rz checked the face is rigidly coupled (kinematic coupling) to a node at its weighted centre, which carries all checked components; the face then stays rigid |
| Several faces, edges and bodies | As an edge of a shell: **fixed**, **pinned**, **symmetry X**, **symmetry Y**, **symmetry Z**, **chosen components**, **prescribed displacement** on the nodes of all items (target `{"faces", "edges", "bodies"}`); **normal to the face (planar)** takes one face |
| Node set | As an edge of a shell: **fixed**, **pinned**, **symmetry X**, **symmetry Y**, **symmetry Z**, **chosen components**, **prescribed displacement**. The translations act on all nodes of the set, the rotations on its shell nodes. **or node set** in the support panel sets the target ([section 12.3](#123-model)) |
| Reference point | As a member end: **fixed** (all six), **pinned**, **chosen components**, **prescribed displacement** ([section 12.6.1](#1261-reference-points)) |
| Member end | **fixed**: all six. **pinned**: ux, uy, uz. **chosen components**: as checked. **prescribed displacement**: the checked components of ux, uy, uz (mm) and rx, ry, rz (rad). At a rod-only node the rotations are left out |

Prescribed displacements act in the load step; with a fastener preload step they are 0 in the preload step. The reaction of a support is the force needed to hold or move its nodes.

**Pick** in the support panel takes the selected faces, edges, bodies or reference point, or starts a selection (a click on a member end takes the end); **Show** selects the target in the view. A supported member end cannot also be connected to a face.

### 12.7.1 Display of supports and loads

| Item | **Show** **Mesh** and **Results** | **Show** **Model** |
|---|---|---|
| Held translation | Cone along the axis of the component, tip at the node, at each node of the support | Cones at points along the edge or on the face; at the nodes of the last mesh when the support has not changed since |
| Held rotation | Cube at each shell or reference node | As the cones |
| Prescribed displacement | Green cones | Green cones |
| Force, pressure, line load on an edge | Arrow ending at each loaded node, length scaled by the largest nodal force of the load (35 % to 100 %) | Arrows on the face or along the edge; at the nodes of the last mesh when the load has not changed since |
| Moment at a node | Arrow with two heads (violet) | Arrow at the face centre or member end |
| Line load on a member | Arrows along the member | Arrows along the member |
| Gravity | One arrow above the model | One arrow above the model |

Supports are blue, loads red, the selected support or load orange. Supports on member ends and reference points are also drawn as cubes in **Show** **Model**. More than 4000 nodes per support or load: every k-th node is drawn.

### 12.7.2 Contact

| Control | Function |
|---|---|
| **Add contact** | New contact pair from the selected faces: the faces of the first selected component are the master, the others the slave |
| **Select faces** | Turns the **Faces** type of the selection on or off ([section 12.2.1](#1221-selection)); the count follows the button. **Add contact** also takes the faces of selected bodies |
| **Gap (mm)**, **Search** | Pairs of faces of different bodies, shells and sections whose triangle centres lie within the gap of the other face and whose normals are parallel within 60 deg (faces meeting only along an edge are not pairs); one contact pair per pair of bodies, master: the side with the larger face area; pairs with the same faces as an existing pair are not added |
| Name, **Type** | **surface-to-surface (penalty)** (`*CONTACT PAIR, TYPE=SURFACE TO SURFACE`, element faces on both sides), **node-to-surface (penalty)** (`TYPE=NODE TO SURFACE`, the slave nodes against the master faces), **tied (bonded)** (`*TIE, ADJUST=YES`; linear) |
| **Master**, **Slave**: **Set from selection**, **Clear**, **Swap**, **Select** | Faces of each side from the face selection; **Swap** exchanges the sides; **Select** puts the faces of the pair into the selection |
| **Slave node set** | Node-to-surface and tied: a node set as the slave in place of the slave faces |
| **Friction** | Coulomb coefficient (`*FRICTION`, stick slope 0.1 x the penalty stiffness); 0: frictionless |
| **Stiffness (N/mm^3)** | Slope of the linear pressure-overclosure law (`*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR`); empty: 10 x the largest E of the model materials per mm. Node-to-surface: tension at large clearance 1e-5 x the stiffness |
| **Adjust (mm)** | Slave nodes within this distance of the master are moved onto it at the start (`ADJUST=`) |
| **Position tolerance (mm)** | Tied: slave nodes within this distance are tied (empty: 1 % of the model size) |

The view draws master faces teal and slave faces pink (orange when the pair is selected). The bodies of a contact pair are meshed apart (no gmsh fragment between them, no shared nodes) and are not tied by **Bonded contact between touching bodies**; master and slave faces that share nodes are refused. Shell faces in contact use the element side that faces the other surface (`SPOS` or `SNEG`). Modal and buckling analyses take no contact pairs. The report lists the pairs with type, face counts, friction and stiffness.

## 12.8 Loads

| Type | Value |
|---|---|
| **Force on a face** | Total force (N, global x y z), distributed over the face nodes by area (consistent loads: mid-side nodes of the 6-node triangles) |
| **Pressure on a face** | MPa, positive into the face; per element face along its normal |
| **Moment on a face** | N mm about the weighted face centre, distributed as nodal forces by area (the RBE3 distribution) |
| **Force at a member end**, **Moment at a member end** | N, N mm (global) at the end node. A moment needs a beam end |
| **Line load on a member** | N/mm (global) along the whole member |
| **Line load on an edge** | N/mm (global) along an edge of a body or shell, distributed over the edge nodes by their tributary length |
| **Gravity** | Acceleration (mm/s^2), for example (0, 0, -9810). Bodies: consistent nodal loads of the element weights (C3D10: corner nodes -1/20, mid-side nodes 1/5 of the element weight). Members: line load rho A g. Fasteners: none |

Several faces: a force or moment is distributed over all faces together by area (one total), a pressure acts on each face. Several edges: a line load on each edge. A load takes faces or edges, not both, and not bodies (the faces of selected bodies are taken).

**Pick** in the load panel takes the selected faces, edges or reference point, or starts a selection (a click on a member end or a member takes it), and sets the type to match (pressure: faces only; line load on an edge: edges only); **Show** selects the target in the view. Forces, moments and pressures on a face of a shell are distributed over the shell nodes of the face.

## 12.9 Results

| Table | Content |
|---|---|
| Bodies | **Show** (check box): the body is drawn in **Show** **Mesh** and **Results**; the colour range is taken from the bodies shown, members are not drawn while a body is hidden. **Show all**; **Show selected**: only the bodies selected in **Show** **Model** (**Bodies**; a selected face gives its body or section; a surface body meshed in sections gives those sections). Largest displacement \|u\|, ux, uy, uz (the component of largest magnitude, signed), largest von Mises stress (nodal values averaged by CalculiX) and, with a plastic material, largest equivalent plastic strain (PEEQ) per body and shell. Shells: CalculiX writes the expanded 3D elements; the displacement of a shell node is the mean of its bottom and top layer nodes, the stress that of the layer with the larger von Mises stress |
| Members | Largest section forces in the local axes: N (tension positive), V1, V2, T, M1, M2, and sig = \|N\| / A + \|M1\| c2 / I22 + \|M2\| c1 / I11 (ROUND and PIPE: \|N\| / A + M r / I). Section forces are those of the positive face (force of the part towards end B on the part towards end A), evaluated at both element ends and at the quarter points |
| Fasteners | N, shear V, bending moment M, torsion T, and sig = \|N\| / A + M d / (2 I) |
| Shell mesh | After **Mesh** and with the results: structured and free faces of the shells, element quality (gamma, 1 for a square, 0 for a degenerate element) minimum, mean and number below 0.3, shortest and longest element edge (mm). The report lists the same values per shell and section |
| Reactions | Force and moment of each support (moment about the weighted face centre or about the member node), their sum, and the applied loads (increments: the loads x the step time) |
| Load history | Nonlinear step: one point per output increment; **x** and **y** from: step time, max \|u\|, Fx, Fy, Fz, \|F\| of each support, ux, uy, uz, \|u\| of each reference point, max von Mises, max PEEQ. A click on a point shows that increment |

In the view the members are drawn as tubes on the deformed shape. With **Result** **von Mises stress** they carry the colour of sig (the member table stress) at the ends of each element, with the displacement fields the colour of the nodal value; the colour scale covers the bodies and the members. The element ends are drawn as points (**Show** **Mesh** and **Results**).

Face supports: the reaction is the CalculiX nodal reaction minus the loads applied at the supported degrees of freedom. Member end supports: from the element end forces at the node and the loads at the node.

The report `analysis/<Name>/<Name>_report.txt` (96 columns) lists the model (materials, bodies with element counts and volumes, members with section properties, fasteners, supports, loads) and per state the result tables, the applied loads and the sum of reactions and applied loads.

| File in `analysis/<Name>/` | Content |
|---|---|
| `job.inp` | CalculiX input file |
| `job.frd`, `job.dat`, `job.sta`, `job.cvg` | CalculiX results |
| `solver.log` | Solver output |
| `<Name>_report.txt` | Report |
| `results.json.gz` | Results of the view and the tables; loaded with the analysis |
| `body_<id>.brep` | Placed bodies and plates passed to gmsh |

Meshing runs in a separate process (`drawgen/femesh.py`) and stops after 1800 s. The solver runs in the background; other tabs stay usable.

## 12.11 Batch mode

`run.py --batch` meshes or solves a saved analysis, or writes the model .inp of a saved explicit document, without the server and the browser. The documents are those of the open project of `config.json`, or of `--project`.

```
python run.py --batch analysis <Name> [--project <Project>] [--mesh-only]
python run.py --batch explicit <Name> [--project <Project>] [--rad] [--radv 2025 | 2023]
```

| Option | Function |
|---|---|
| `--batch analysis <Name>` | Meshes and solves `analysis/<Name>` as **Solve**; prints the node and element counts per body, the shell mesh values ([section 12.9](#129-results)), the warnings and the files |
| `--mesh-only` | Meshes and writes `job.inp` as **Mesh** |
| `--batch explicit <Name>` | Meshes and writes `explicit/<Name>/model/<Name>.inp` as **Mesh** of the Explicit tab; prints the bodies, the shell mesh values and the node sets |
| `--rad` | Runs inp2rad on the .inp: `<Name>_0000.rad` and `<Name>_0001.rad` next to it |
| `--radv` | Radioss input format of inp2rad (default 2025) |
| `--project <Project>` | Opens the project first |

Exit code: 0 done, 1 mesh, solver or inp2rad failed, 2 document or project not found.

## 12.10 Modal and buckling analysis

| **Analysis type** | CalculiX step | Result |
|---|---|---|
| **Linear static** | `*STATIC` | Sections 12.2 to 12.9 |
| **Modal (natural frequencies)** | `*FREQUENCY` with **Number of modes** (1 to 100) | Natural frequencies (Hz), effective modal mass per direction as a percentage of the total effective mass, mode shapes |
| **Linear buckling** | `*BUCKLE` with **Number of modes** | Buckling factors and mode shapes. Critical loads: buckling factor x the applied loads and prescribed displacements; a negative factor: buckling under the reversed loads |

Modal and buckling analyses take solid bodies, shells, plates and rods. Beams and fasteners are refused (the CalculiX U1 beam element has no mass and no stress stiffness). A modal analysis needs a density for every material used and does not use the loads; supports hold their degrees of freedom with prescribed displacements set to 0. A buckling analysis needs loads or prescribed displacements.

The mode shapes are normalised to a largest displacement of 1; **Result** offers **Displacement |u|**, **ux**, **uy**, **uz** (the legend reads "normalised"). The results panel lists the modes; a click on a row shows the mode. The report gives the analysis type, the table of frequencies (with the effective modal mass) or buckling factors, and the largest mode shape displacement per body and mode.

[Contents](../README.md) · [← 11. Assembly](11-assembly.md) · [13. Explicit →](13-explicit.md)
