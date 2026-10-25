[Contents](../README.md) · [← 11. Assembly](11-assembly.md) · [13. Explicit →](13-explicit.md)

# 12. Analysis

The **Analysis** tab runs a linear static, modal or linear buckling analysis with CalculiX (`ccx`, version 2.21). The model holds the bodies of a saved assembly or part, plates, beams, rods and fasteners. Plates and members are defined in the tab; a model of members and plates needs no geometry. The CalculiX input file, the result files and a text report are written to `analysis/<Name>/` of the project.

Units: mm, N, s, t (tonne): stress and pressure MPa (N/mm^2), moment N mm, line load N/mm, acceleration mm/s^2. Densities are entered in kg/m^3 (converted to t/mm^3).

The panel at the right is 480 px wide; the bar at its left edge changes the width (kept in the browser).

## 12.1 Solver

**Solver (ccx)** under **Settings** is the path of the CalculiX executable (written to `config.local.json` > `ccx_path`). When it is empty, the program uses the first `ccx*.exe` in `solvers\` of the program ([section 1.1](01-installation.md#11-solvers)), `ccx` on PATH, or `ccx_static.exe` / `ccx_dynamic.exe` of a `PrePoMax*` folder (for example `PrePoMax v3.0.0 RC2`) in `Program Files`, `%LOCALAPPDATA%`, the user folder, its `Desktop`, `Downloads` and `Documents`, or the root of the system drive. The line below the field gives the executable in use. `OMP_NUM_THREADS` and `CCX_NPROC_STIFFNESS` are set to the number of processor cores.

## 12.2 Controls

| Control | Function |
|---|---|
| **File ▾** | Project header, **Analysis** (saved analyses of the open project), **New**, **Save**, **Save as…**, **Rename…**, **Open run folder** (`analysis/<Name>/`), **Write input file** (mesh and `job.inp` without solving) |
| **Geometry** | Saved assembly or part of the project, or **(none: members and plates)**. A part is one body. The analysis uses the saved file of the assembly. The sketches of a part that no feature of the part uses are drawn (purple lines and points); a part with sketches only is not a body. Member ends and plate points snap to the sketch points ([section 12.4](#124-members)) |
| **Mesh** | Meshes the bodies, writes `job.inp` and shows the mesh. The status line gives the node and element counts and the element types per body. **Edges** draws the element edges (quadrangle faces of hexahedra without diagonals) |
| **Solve** | Meshes, writes `job.inp`, runs CalculiX and shows the results. The status line gives the stage and the time |
| **Stop** | Stops the solver |
| **Beam**, **Rod** | Adds a member: pick end A, then end B in the view ([section 12.4](#124-members)). The member gets the section, material, group, up vector, elements and hinges of the selected member of the same kind, else of the last one. After end B the next member starts with the same properties; Esc (or another toolbar command) ends the drawing and removes the member without ends. Esc on the first member keeps it for typed coordinates. **Sketch beams** uses the same properties |
| **Sketch beams** | Adds a beam on each straight line of the sketches of the geometry. Lines that already have a member are skipped. Members meeting at a point share the node |
| **Plate on face**, **Plate by points** | Adds a plate ([section 12.5](#125-plates)) |
| **Fastener** | Adds a fastener ([section 12.6](#126-fasteners)) |
| **Ref. point** | Adds a reference point ([section 12.6.1](#1261-reference-points)): click the faces to connect (the first face sets the point at its centre); Esc ends the face picking |
| **Support** | Adds a support at the selected member end or reference point; with no member end selected, starts the pick of a face or a member end ([section 12.7](#127-supports)) |
| **Load** | Adds a force at the selected member end; with no member end selected, starts the pick of a face, a member end (force at the end) or a member (line load, 1 N/mm downwards) ([section 12.8](#128-loads)) |
| **Show** | **Model** (bodies, members, fasteners, supports and loads), **Mesh**, **Results** |
| **Result** | **von Mises stress**, **Displacement \|u\|**, **ux**, **uy**, **uz** as contours on the deformed shape, with the colour scale (12 bands) in the upper left of the view |
| **State** | **Total**; with a fastener preload also **Step 1 preload** and **Step 2 loads**; modal and buckling: **Mode 1: f Hz** or **Mode 1: factor x**, one entry per mode |
| **Scale** | Deformation scale (empty: the largest displacement is drawn as 5 % of the model size) |
| **Undeformed** | Outline of the undeformed mesh |
| **Iso**, **Front**, **Top**, **Right**, **Fit**, **Edges**, **Axes** | As in the Assembly tab |

A click on a member, fastener, support or load in the 3D view selects it in the panel. A click within 10 px of a member end selects the end: the end is drawn as a large orange ball and **Members** shows its coordinates. A click on empty space clears the selection. The member end, point or face under the cursor is marked orange before a click (cursor: pointer for selection, crosshair during a pick). Esc cancels a pick.

## 12.3 Model

| Panel | Function |
|---|---|
| **Settings** | **Solver (ccx)**; **Analysis type** and **Number of modes** ([section 12.10](#1210-modal-and-buckling-analysis)); **Default material**; **Mesh** ([section 12.3.1](#1231-mesh-settings)); **Bonded contact between touching bodies**: touching solid bodies of one mesh strategy are meshed with shared nodes at the contact faces (gmsh fragment); plates and bodies of other strategies are tied (`*TIE`) to the faces they touch. Without it the bodies are connected only by members and fasteners |
| **Materials** | Name, E (MPa), nu, rho (kg/m^3). **Add material**, × deletes |
| **Bodies** | One row per component of the geometry: **Model** **solid** (meshed with the strategy in **Mesh**), **plate** (C3D8I through the thickness, C3D6 for the triangles left by the quadrangle mesh) or **off** (left out); **Mesh**: the strategy of the body (**tet**, **hex**, **hex sub**; in brackets: the default of **Settings**); **Material**; **Size (mm)** of the elements of the body |

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

The solid bodies of one strategy are meshed together (shared nodes with **Bonded contact**); bodies of different strategies, and plates, are tied where they touch. Body weight is distributed with the consistent nodal fractions of the element type. The report gives the mesh settings and the element counts per body and type.
| **Members** | List and properties of the members. See 12.4 |
| **Plates** | **Plate on face**: pick a planar face of a body. **Plate by points**: click the outline points in the view (Esc ends) or type them. See 12.5 |
| **Fasteners** | **Fastener**: pick face A (head side: hole or bearing face), then face B (nut or thread side). See 12.6 |
| **Supports** | **Support**: pick the face, or choose a member end in the panel. See 12.7 |
| **Loads** | **Load**: pick the face; **Type** changes the load. See 12.8 |
| **Results** | Tables of the selected **State**, **Report**, **Download report**, **Open run folder**. See 12.9 |

A plate body must be a prism of its largest planar face (the opposite face has the same area at the thickness distance). The face is meshed with quadrangles and the mesh is extruded through the thickness (one element layer).

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

A reference point is a point rigidly connected to faces of the bodies and plates (CalculiX `*RIGID BODY`: the connected face nodes move as a rigid body with the point). It is drawn as a violet ball with dashed lines to the centres of its faces.

| Field | Function |
|---|---|
| **Name** | |
| **Point (mm)** | Coordinates; **Pick**: a point on a face or a member end; **Centre**: the centre of the clicked face |
| **Rigidly connected faces** | **Add faces**: click faces (Esc ends); **Clear faces** |

Supports and loads act on a reference point: select it (in the list or the view) and press **Support** or **Load**, pick it with **Pick** (within 10 px), or choose it under **or reference point**. Supports take six components (ux, uy, uz, rx, ry, rz); loads are a force (N) or a moment (N mm). A member end at the point follows the point (translations, and rotations at a beam end). Supported face nodes and nodes already constrained are left out of the rigid connection (a warning in the report). The results list the displacement and rotation (rad) of each reference point.

## 12.7 Supports

| Target | Type |
|---|---|
| Face | **fixed**: ux, uy, uz of all face nodes. **normal to the face (planar)**: displacement normal to the face (`*TRANSFORM`), 0 or **Normal displacement (mm, along the outward normal)**. **chosen components**: ux, uy, uz, rx, ry, rz as checked. **prescribed displacement**: the checked components prescribed (mm, rad), the others free. With rx, ry or rz checked the face is rigidly coupled (kinematic coupling) to a node at its weighted centre, which carries all checked components; the face then stays rigid |
| Reference point | As a member end: **fixed** (all six), **pinned**, **chosen components**, **prescribed displacement** ([section 12.6.1](#1261-reference-points)) |
| Member end | **fixed**: all six. **pinned**: ux, uy, uz. **chosen components**: as checked. **prescribed displacement**: the checked components of ux, uy, uz (mm) and rx, ry, rz (rad). At a rod-only node the rotations are left out |

Prescribed displacements act in the load step; with a fastener preload step they are 0 in the preload step. The reaction of a support is the force needed to hold or move its nodes.

**Pick** in the support panel takes a face or a member end. A supported member end cannot also be connected to a face.

## 12.8 Loads

| Type | Value |
|---|---|
| **Force on a face** | Total force (N, global x y z), distributed over the face nodes by area (consistent loads: mid-side nodes of the 6-node triangles) |
| **Pressure on a face** | MPa, positive into the face; per element face along its normal |
| **Moment on a face** | N mm about the weighted face centre, distributed as nodal forces by area (the RBE3 distribution) |
| **Force at a member end**, **Moment at a member end** | N, N mm (global) at the end node. A moment needs a beam end |
| **Line load on a member** | N/mm (global) along the whole member |
| **Gravity** | Acceleration (mm/s^2), for example (0, 0, -9810). Bodies: consistent nodal loads of the element weights (C3D10: corner nodes -1/20, mid-side nodes 1/5 of the element weight). Members: line load rho A g. Fasteners: none |

**Pick** in the load panel takes a face, a member end or a member and sets the type to match (pressure: a face only).

## 12.9 Results

| Table | Content |
|---|---|
| Bodies | Largest displacement and largest von Mises stress (nodal values averaged by CalculiX) per body |
| Members | Largest section forces in the local axes: N (tension positive), V1, V2, T, M1, M2, and sig = \|N\| / A + \|M1\| c2 / I22 + \|M2\| c1 / I11 (ROUND and PIPE: \|N\| / A + M r / I). Section forces are those of the positive face (force of the part towards end B on the part towards end A), evaluated at both element ends and at the quarter points |
| Fasteners | N, shear V, bending moment M, torsion T, and sig = \|N\| / A + M d / (2 I) |
| Reactions | Force and moment of each support (moment about the weighted face centre or about the member node), their sum, and the applied loads |

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

## 12.10 Modal and buckling analysis

| **Analysis type** | CalculiX step | Result |
|---|---|---|
| **Linear static** | `*STATIC` | Sections 12.2 to 12.9 |
| **Modal (natural frequencies)** | `*FREQUENCY` with **Number of modes** (1 to 100) | Natural frequencies (Hz), effective modal mass per direction as a percentage of the total effective mass, mode shapes |
| **Linear buckling** | `*BUCKLE` with **Number of modes** | Buckling factors and mode shapes. Critical loads: buckling factor x the applied loads and prescribed displacements; a negative factor: buckling under the reversed loads |

Modal and buckling analyses take solid bodies, plates and rods. Beams and fasteners are refused (the CalculiX U1 beam element has no mass and no stress stiffness). A modal analysis needs a density for every material used and does not use the loads; supports hold their degrees of freedom with prescribed displacements set to 0. A buckling analysis needs loads or prescribed displacements.

The mode shapes are normalised to a largest displacement of 1; **Result** offers **Displacement |u|**, **ux**, **uy**, **uz** (the legend reads "normalised"). The results panel lists the modes; a click on a row shows the mode. The report gives the analysis type, the table of frequencies (with the effective modal mass) or buckling factors, and the largest mode shape displacement per body and mode.

[Contents](../README.md) · [← 11. Assembly](11-assembly.md) · [13. Explicit →](13-explicit.md)
