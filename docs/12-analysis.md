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
| **Solver** | **CalculiX** (this pane) or **OpenCourant (explicit)**: the explicit pane on the same document and model ([section 13.0](13-explicit.md#130-one-document-with-the-analysis-tab)) |
| **Geometry** | Saved assembly or part of the project, or **(none: members and plates)**. A part is one body. The analysis uses the saved file of the assembly. The sketches of a part that no feature of the part uses are drawn (purple lines and points); a part with sketches only is not a body. The surface bodies of a component are shells ([section 12.3](#123-model)), drawn translucent in their colour of the Part tab (shells set to **off** faint). Parts are imported and placed in the Assembly tab (**Add part**, **Add STEP**, **Position**, mates, **Drag**, **Move 2 pts**, [section 11](11-assembly.md#11-assembly)) and the assembly is the geometry. Member ends and plate points snap to the sketch points ([section 12.4](#124-members)). **Import CalculiX .inp or Radioss .rad…**: a meshed CalculiX / Abaqus input file or Radioss starter deck as the geometry ([section 12.3.3](#1233-mesh-file-as-geometry)) |
| **Update** | Loads the geometry again from the saved assembly and parts (a mesh file: from the file); the mesh and the results of the old geometry are cleared. The server compares the assembly file and the files of its parts (and their imported STEP files), or the modification time and size of a mesh file, with the loaded geometry when the tab is shown, every 4 s and when the window gets the focus; a change marks **Update** orange. Face, edge and node set references keep their face and edge numbers |
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
| **State** | **Total**; with a fastener preload also **Step 1 preload** and **Step 2 loads**; nonlinear step: **End of the step** and **Increment k: time t**, one entry per output increment (at most 40, evenly spaced); several steps ([section 12.8.1](#1281-steps-amplitudes-and-initial-velocities)): **End of the last step**, **End of step k: name** per step and **Increment k: step name, time t** (total time); modal and buckling: **Mode 1: f Hz** or **Mode 1: factor x**, one entry per mode |
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
| **Faces**, **Edges**, **Vertices**, **Bodies**, **Ref. points** | Item types that clicks and boxes in the view take on **Show** **Model** (several at once). With no type on, a click selects members, supports, loads and bodies for their panels. The vertices of a component are the end points of its edges |
| **Nodes**, **Elements** | Mesh nodes and elements, on **Show** **Mesh** (after **Mesh**; **Shell thickness** off). Turning one on shows the mesh. A click takes the node within 10 px of the cursor (**Nodes**) or the element of the face under the cursor (**Elements**); a box takes the nodes and elements of the drawn surface of the mesh. The selection keeps the node and element numbers of the mesh: a mesh that changes after the selection (another element size, a changed geometry) stops the solve with the number of nodes or elements not found |
| **Single**, **Tangent**, **Connected**, **Whole body** | What a click on a face or an edge adds (or removes, when the clicked face or edge is selected). **Single**: the face or edge. **Tangent** with the angle field (deg, default 10): the faces of the same body joined to it across common edges where the face normals differ by at most the angle, repeated from each added face; the edges joined at their end points where the direction turns by at most the angle. **Connected**: all faces of the same body connected to it by common edges; all edges connected to it by end points. **Whole body**: all faces of its body. Faces of surface bodies compare the lines of the normals (either side). A plain click (no type on) uses the same setting |
| **Box** | Left drag draws a box (left drag no longer rotates; the middle and right buttons pan). Drag to the right: the items fully inside the box (window, solid outline). Drag to the left: the items inside or crossing the box (crossing, dashed outline). Ctrl or Alt held at release: the items leave the selection. Items hidden behind others are taken |
| **Clear** | Clears the selection |
| **Suppress**, **Unsuppress** | Sets the selected bodies, and the section of each selected face (a face in no section: its body), to **off** (left out of the mesh and the solve, drawn faint); **Unsuppress** sets them back to their model before **Suppress** (kept as `prev_off`) |
| Count | Number of selected faces, edges, bodies and reference points |
| **Done**, **Cancel** | Shown during a selection for a target: **Done** (or Enter) gives the selection to the target, **Cancel** (or Esc) ends it without change |

A click toggles the item under the cursor: a reference point within 10 px, a vertex within 10 px, an edge within 8 px, else the face (**Faces**) or its body (**Bodies**: the solid of the component or the surface body of the face). Selected faces are orange, faces of selected bodies light orange, selected edges red, selected vertices and mesh nodes red points, selected reference points orange, selected elements orange on **Show** **Mesh**. Esc turns the types off and keeps the selection.

Supports and loads (force) take vertices, mesh nodes and elements: a vertex is the mesh node nearest to it (within 1e-4 of the model size + 0.01 mm), an element gives its nodes; a force on vertices, nodes or elements is shared equally by their nodes, and they take no other items in the same load.

Targets take the selection: **Support**, **Load**, **Pick** of a support or load, **Selection** of the node sets, **Add faces** and **Add edges** of a reference point, **Selected faces**, **Selected edges**, **Set** and **Bodies** of the node sets, **New from selection** and **+** of the sections and of the refinement regions, **New from selection**, **+** and **Set** of the surfaces, and **Add contact** and **Set from selection** of the contact pairs. With items of the accepted types selected, the target takes them at once; else the target sets the types, and clicks and boxes select until **Done** or Enter. A target that takes faces only takes the faces of the selected bodies. **Show** of a support or load selects its target in the view.

### 12.2.2 Model tree

The panel holds the **Model tree** over a property pane. The property pane shows the panel of the selected node and the panels of the nodes below it; **Analysis (CalculiX)** (the top node) shows all panels and the **Panels** row.

| Node | Panel |
|---|---|
| **Settings** | **Settings** |
| **Model** | **Input file** (mesh file geometry), **Materials**, **Bodies**, **Sections**, **Surfaces**, **Node sets**, **Reference points**, **Members and plates** (**Members**, **Plates**, **Fasteners**), **Constraints** (**Springs**, **Joints**, **Equations**), **Contact** |
| **Steps** (static analysis); **Step (modal)**, **Step (buckling)** | **Step list** (the steps as items), **Supports**, **Loads**, **Amplitudes**, **Initial velocities** |
| **Results** | **Results** |

A node gives the number of its items and lists them below it: **Materials** the material names, **Bodies** the solids and surface bodies of the geometry (`solid <component>`, `shell <component> / <surface body>`), the other nodes the names of their items. A click on an item shows the panel of its node and selects the item: a body in the view (**Bodies** selection), the faces of a section or surface, a reference point, or the member, plate, fastener, support, load or contact pair in its panel. A node of a panel hidden by **Panels** is grey. ▸ / ▾ folds and unfolds a node. A member, plate, fastener, support, load or contact pair selected in the view or in a list selects its node when the selected node does not show it. The lower edge of the tree is dragged to change its height. ⇄ in the panel header moves the panel to the other side of the view. The selected node, the folded nodes, the tree height and the side are kept on this PC.

## 12.3 Model

| Panel | Function |
|---|---|
| **Panels** | Check boxes that show or hide the **Sections**, **Node sets**, **Members**, **Plates**, **Fasteners**, **Reference points**, **Springs**, **Joints**, **Equations** and **Contact** cards; kept in the analysis (`panels_hidden`). A hidden card with items shows their number. Hidden items still act in the solve |
| **Settings** | **Solver (ccx)**; **Analysis type** and **Number of modes** ([section 12.10](#1210-modal-and-buckling-analysis)); **Default material**; **Mesh** ([section 12.3.1](#1231-mesh-settings)); **Bonded contact between touching bodies**: touching solid bodies of one mesh strategy are meshed with shared nodes at the contact faces (gmsh fragment); plates and bodies of other strategies are tied (`*TIE`) to the faces they touch; bodies of a contact pair are meshed apart and not tied ([section 12.7.2](#1272-contact)). Without it the bodies are connected only by members, fasteners and contact pairs; **Nonlinear step** ([section 12.3.2](#1232-materials-and-nonlinear-step)) |
| **Materials** | Name, E (MPa), nu, rho (kg/m^3), **Law**, **Library** ([section 12.3.2](#1232-materials-and-nonlinear-step)). **Add material**, × deletes. **Material** drop-downs (bodies, shells, sections, members, plates, fasteners): **(default: ...)** with the default material, the model materials as `name - library entry` or `name - law, E MPa, nu, rho kg/m^3`, and under **Library** the library entries not used by a model material; choosing a library entry adds a model material of that entry (named after the entry without the bracketed part) and assigns it |
| **Shells** | The surface bodies of the components are shells. Their inputs are set in **Sections** only: every face of a surface body is in a section, and faces in no section (a new geometry, a removed section) get one section per surface body (named `<COMPONENT>_<SURFACE BODY>`). **Bodies** gives the number of surface bodies. Shell inputs of older documents (`shells`) are taken over by those sections. The faces of all shells are meshed together (**Shell elements**, **Shell mesh** in [section 12.3.1](#1231-mesh-settings)); with **Bonded contact between touching bodies**, shells that touch or cross share their nodes on the common lines (gmsh fragment), and shell nodes on the faces of solid bodies are tied to them (`*TIE`). A face shared by two shells belongs to the shell listed first |
| **Sections** | Groups of faces of the surface bodies of any components with one thickness, position, material and element size (one ELSET each, named by the section). **From surface bodies**: one section per surface body (replaces the sections; a section of the same name keeps its values). **By geometry**: connected faces on the same plane (within **angle**, deg) or on the same cylinder form one section, named `PLATE_Z<z>` (plane normal to z), `WEB_X<x>` or `WEB_Y<y>` (plane normal to x or y), `PLANE`, `CYL_R<r>` (cylinder of radius r) or `SURF`; a second section of the same name gets `_2`. **New from selection**: a section of the selected faces of shells (selected faces of solids are left out). **Remove all** deletes the sections (one section per surface body is made again). **Select faces**: turns the **Faces** type of the selection on or off ([section 12.2.1](#1221-selection)); **Select unassigned** (faces in no section), **Select all**, **Invert**, **Clear selection**. Each section takes two lines: colour of the faces in the view, name, number of faces, **Sel** (selects them), **+** (adds the selected faces), × (deletes the section); **Model** **shell** or **off**; **t (mm)** thickness (empty: 10 mm); **Position** **mid** (the surface is the mid-surface), **positive** or **negative** (the shell lies on that side of the surface, along the element normal; `*SHELL SECTION` `OFFSET` 0.5 or -0.5); **Material**; **Size (mm)** element size; **Layers** (S8R shell elements only, 1 to 20; empty: 1): `*SHELL SECTION, COMPOSITE` with that number of layers of t / n of the material, each layer with its own integration points through the thickness (other shell elements: one layer and a warning). Sections set to off are drawn pale; their faces are left out of the mesh and the solve. A face belongs to one section. Selected faces are orange |
| **Surfaces** | Named groups of faces of solids and shells (`surfaces`). **New from selection** (name `SURFACE_<n>`). Per surface: colour, name, number of faces, **Sel** (selects the faces), **+** (adds the selected faces), **Set** (replaces the faces with the selection), **Show** / **Hide** (the faces drawn in the colour of the surface), ×. Supports, loads on faces and contact sides take a surface (**or surface**): the faces of the surface when the model is built; a surface that is not found or has no faces stops the build |
| **Node sets** | Named groups of mesh nodes. **Plane**: the nodes within the tolerance (mm) of the plane x, y or z = value. **Section edges**: **free edges** (element edges of the section or shell bounding one shell element of the whole model) or **outline** (element edges bounding one element of the section or shell); a new node set takes the first section, else the first shell. **Selected edges**: the nodes of the selected edges (**Select edges** turns the **Edges** type on or off). **Selected faces**: the nodes of the selected faces of solids and shells and of the faces of the selected bodies (**Select faces** in **Node sets** or **Sections**). **Bodies**: all nodes of the checked bodies (solids, shells, sections; a new node set takes the selected bodies); a shell whose faces are in sections gives the nodes of those faces. **Selection**: the nodes of the selected faces, edges, vertices, bodies, mesh nodes and elements (kind `selection`); **Set** replaces them with the selection. **Set** replaces the edges or faces with the selection, **Show** selects them in the view, **Support** adds a support with the node set as target ([section 12.7](#127-supports)). A mesh file geometry adds one node set per `*NSET` (.inp) or `/GRNOD/NODE` (.rad) of the file, of kind **inp** (`*NSET <name> of the .inp`, `/GRNOD <name> of the .rad`): the nodes of that set |
| **Bodies** | One row per component of the geometry with a solid: **Model** **solid** (meshed with the strategy in **Mesh**), **plate** (C3D8I through the thickness, C3D6 for the triangles left by the quadrangle mesh) or **off** (left out); **Mesh**: the strategy of the body (**tet**, **hex**, **hex sub**; in brackets: the default of **Settings**); **Material**; **Size (mm)** of the elements of the body |

### 12.3.1 Mesh settings

| Field | Function |
|---|---|
| **Strategy** | Default for the solid bodies. **Tetrahedra (free)**. **Hexahedra, structured (block cells)**: transfinite mesh; every cell of the body must be a block (6 faces with 4 edges each) or a prism (wedge elements); bodies are cut into such cells with **Partition** in the Part tab; a body with other cells stops the mesh with its name. **Hexahedra by subdivision**: each tetrahedron of a free mesh is divided into four hexahedra (any geometry; element distortion is higher) |
| **Tetrahedra** | **C3D10** (second order) or **C3D4** (first order) |
| **Hexahedra** | **C3D8I** (incompatible modes), **C3D8**, **C3D8R** (reduced integration), **C3D20**, **C3D20R** (second order). Wedges in prism cells: C3D6, or C3D15 with C3D20 and C3D20R |
| **Element size (mm)** | Largest element size. Empty (automatic): model size / 20, and every face of the tetrahedral bodies and shells without a size of their own gets at most its width / 3 (3 elements across; width = face area / largest extent of its bounding box); shell faces not smaller than the thickness t of their section. **Size (mm)** in **Bodies** and **Sections** sets it per body or section |
| **Minimum size (mm)** | Smallest element size (empty: element size / 5; automatic element size: element size / 10) |
| **Refinement** | **Add from selection**: a refinement region of the selected faces (selected bodies: their faces; with nothing selected, a selection until **Done**). Per region: name, number of faces (**Sel** selects them, **+** adds the selected faces), **Size (mm)**, ×. Each face of a region gives a box (its bounding box) with the region size inside; outside the box the size grows to the element size of the body over 3 x the region size (gmsh Box fields, tetrahedra and free shell faces). Structured shell faces inside a box take the region size; next to them the shell mesh changes to free faces. The minimum element size follows the smallest region size. Kept in the document (`refine`) |
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
| **Library** | Material library ([section 13.5](13-explicit.md#135-build)): E, nu, rho and the hardening table of the material (DNVGL curves as given; Johnson-Cook entries sampled as a + b eps_p^n at 16 plastic strains from 0 to 1, without the rate term). A library material sets **Law** to plastic (isotropic) when it has a hardening curve; E, nu, rho and the table are then not editable |
| Hardening table | Plastic materials: one row per line: yield stress (MPa), plastic strain; the first row at plastic strain 0 (the yield stress). New plastic material: 250 MPa at 0, 300 MPa at 0.1 |
| **C10**, **C01**, **D1** | Hyperelastic materials: C10, C01 (Mooney-Rivlin) in MPa, D1 in 1/MPa (bulk modulus 2 / D1) |
| **Curve** | Plot of the material chosen in **Curve** (plastic and hyperelastic materials). Plastic: the hardening table, true stress (MPa) against **true plastic strain** or **true total strain** (plastic strain + stress / E, from 0). Hyperelastic: uniaxial nominal stress (MPa) against nominal strain -0.3 to 1, incompressible, 2 (lambda - lambda^-2) (C10 + C01 / lambda). The value at the cursor is shown in the upper left. **CSV** downloads the curve |
| **Large deformation (NLGEOM)** | Equilibrium in the deformed geometry; always on with a hyperelastic material |
| **Initial increment**, **Max increment**, **Min increment** | Increment sizes as fractions of the step (step time 1); defaults 0.1, 0.25, 1e-5 |
| **Max increments** | Largest number of increments of a step (default 100) |
| **Output every n increments** | Results (`*NODE FILE`, `*EL FILE`, `*NODE PRINT`, `*EL PRINT`) every n increments (default 1) |
| **Solver controls (*CONTROLS)** | `*CONTROLS` cards written in each nonlinear step after `*STATIC` or `*DYNAMIC`, for example `*CONTROLS, PARAMETERS=TIME INCREMENTATION` with its data lines (more iterations before a cutback). Keyword lines must be `*CONTROLS`, data lines numbers and commas; other text is refused. Empty: none |

A nonlinear static step (`*STEP, INC=n` with `*STATIC` increments) is used with a contact pair other than tied, a plastic or hyperelastic material, or **Large deformation**; the heading of **Nonlinear step** states whether it is used. Loads and prescribed displacements are ramped linearly over the step. In a nonlinear or dynamic step, beams are written as B31 elements (`*BEAM SECTION` RECT, CIRC for ROUND, PIPE or BOX; CalculiX expands them to 3D elements), so large deformation and the material law apply to them; I and GENERAL sections are refused there. B31 beams give displacements and the reactions of their supports (forces), not section forces (the member table shows zeros). Fasteners (U1 elements with preload) are linear only: a nonlinear or dynamic solve with fasteners is refused (**Mesh**: a warning). Rods (T3D2) take any law. The report lists the law of each material, the hardening tables, the hyperelastic constants and the increment settings.

### 12.3.3 Mesh file as geometry

**Geometry** **Import CalculiX .inp or Radioss .rad…** opens a file dialog; the file becomes the geometry (`source` `{"type": "inp", "path", "name"}`). The nodes and elements of the file are the mesh: **Mesh** and **Solve** do not mesh, and the mesh settings, refinement regions and plates do not apply. The solve writes a new `job.inp` with the supports, loads, contact pairs and other items of the tab.
`*INCLUDE, INPUT=<file>` lines are read in place (nested; a relative path from the folder of the file that includes it; an absolute path; quotes allowed). An include file that is not found is a warning of the import; a change of an include file is read at the next view. The Explicit build writes the included lines into its `.inp` for inp2rad. **File text** of the **Input file** page shows the lines of the main file only.

The import also reads the step data of an .inp (not of a .rad) into the tab (`drawgen/inpsteps.py`), so the model is ready to solve:

| In the file | In the tab |
|---|---|
| `*BOUNDARY` (degrees of freedom 1 to 6, a value; `ENCASTRE`, `PINNED`, `XSYMM`, `YSYMM`, `ZSYMM`, `XASYMM`, `YASYMM`, `ZASYMM`) | A support per node set of the file (target the node set) or per group of node numbers with the same degrees of freedom (target the mesh nodes): **dofs** with the held components, **displacement** with the values when a value is not 0. Named by the `** Name:` comment above the keyword (PrePoMax), else `BC <set>` |
| `*CLOAD` (degrees of freedom 1 to 3) | A force on the node set (or the nodes): the value x the number of nodes, shared equally by the nodes (the same nodal forces as the file). `AMPLITUDE=`: the amplitude of the file in **Amplitudes** |
| `*DLOAD` `GRAV` | A gravity load (g x direction, mm/s^2) |
| `*STEP` `NLGEOM`, `INC` | **Large deformation (NLGEOM)**, **Max increments** |
| `*STATIC` / `*DYNAMIC` data line (first increment, step time, minimum, maximum increment) | One step: **Initial increment**, **Min increment**, **Max increment** (fractions of the step time, at most 1). Several steps: the **Steps** with kind and time, the supports and loads with a factor per step (a load whose direction is the same in every step: one load with the factors, else one per step) |
| `*CONTROLS` | **Solver controls (*CONTROLS)** (several steps with different controls: the controls of each step) |
| `*FREQUENCY`, `*BUCKLE` | **Analysis type** modal or buckling with **Number of modes** (the other steps not read) |

Model data before the first step act in every step; `OP=NEW` removes the boundary conditions or loads of the steps before; boundary conditions and loads carry over to the next step otherwise. Not read (listed in the note): `*DLOAD` pressures, `*DSLOAD`, moments of `*CLOAD` (degrees of freedom 4 to 6), `*BOUNDARY, TYPE=VELOCITY`, the amplitude of a `*BOUNDARY`, `*NODE PRINT`, `*EL PRINT` (set them in **History output**) and the output requests (the tab writes its own). The **Input file** page gives the note: "Read from the file: n support(s), m load(s), ..." with what was not read. The import is made once per file; items added to the document before stay.

| Item of the file | In the tab |
|---|---|
| Element set with a `*SOLID SECTION` or `*SHELL SECTION` (.inp); part (`/PART`, .rad) | One component, named by the element set or the part title (upper case; a part without title: `PART_<id>`). Elements in no section: one component per element type, `<TYPE>_ELEMENTS` |
| Solid elements C3D4, C3D10, C3D6, C3D15, C3D8, C3D8R, C3D8I, C3D20, C3D20R; .rad `/BRICK` (C3D8; degenerate bricks C3D6 or C3D4), `/TETRA4` (C3D4) | A solid body; **Bodies** row with the material of the section |
| Shell elements S3, S3R, S6, S4, S4R, S8, S8R; .rad `/SHELL` (S4, S3 when node 4 is 0 or repeats node 3), `/SH3N` (S3) | A shell (one surface body); its faces in a section with the thickness, position (`OFFSET`) and material of the file (.rad: thickness of `/PROP/SHELL`) |
| `*MATERIAL` with `*ELASTIC`, `*DENSITY` and `*PLASTIC`; .rad `/MAT/<law>` (density, E and nu of its first two lines) | Materials; a density below 0.001 is read as t/mm^3 and converted to kg/m^3 |
| `*NSET`; .rad `/GRNOD/NODE` | Node sets of kind **inp** ([section 12.3](#123-model)) |
| .rad `#include` files | Read in place (paths relative to the deck) |
| Steps, boundary conditions, loads and other element types | Not read; other element types are listed in the status line |

The faces of a body are its exterior element faces, grouped into connected faces with normals within 30 deg. The edges are the boundaries between faces and the free boundaries of shells, split where the direction turns by more than 30 deg. Faces and edges take supports, loads, contact sides, surfaces and node sets as on a CAD geometry. **Edges** draws the element edges of the file on the faces (grey) with the face edges (black). The inputs of the file (materials, body materials, sections, node sets) are taken into the analysis once per file; later changes in the tab are kept. The status line gives the file name, the numbers of nodes, elements and bodies, and the warnings of the reader. Lengths are read as mm (a .rad with input length units other than mm: a warning). The report gives the volume of a solid body from its exterior element faces.

**Input file** (model tree node under **Model**, shown with a mesh file geometry; also in the explicit pane) lists the contents of the file (`drawgen/inpinfo.py`):

| Section | Content |
|---|---|
| Summary line | File name, size (kB), lines, heading, nodes, elements per type, mass |
| **Checks** | Elements with nodes that are not in the file, unreadable element lines, coincident nodes (distance below 1e-6 x the model diagonal), nodes in no element, inverted elements (zero or negative volume), zero-length element edges, element types not used as geometry, sections whose element set or material is not in the file, elements in no section, materials in no section, node and element sets with numbers that are not in the file, keywords not used by the program |
| **File** | Path, size, lines (with the `*INCLUDE` files), heading, the include files and their lines |
| **File text** | The lines of the file (not of its include files) with line numbers, in a scrolled box: 300 lines first, 200 more loaded when the box is scrolled to its top or bottom (at most 2000 lines held). Keyword lines in blue, comment lines in grey. **Line** and **Go** (or Enter) show a line; **Find** with **text** (case-insensitive), **node number** or **element number** (the data line of the node or element under `*NODE` / `*ELEMENT`; .rad: `/NODE`, `/SHELL`, `/SH3N`, `/BRICK`, `/TETRA4`, `/TETRA10`, `/BEAM`, `/TRUSS`, `/SPRING`); ▼ (or Enter) the next line, ▲ (or Shift+Enter) the previous line from the highlighted line. A click on a line highlights it. A keyword in **Keywords** and **line** in a row of **Search** show its line |
| **Nodes** | Count, first and last number, extent x / y / z (mm), size, diagonal, coincident nodes, nodes in no element, elements with missing nodes |
| **Element types** | Per type: count, first and last number, family (solid, shell, membrane, continuum shell, beam, truss, spring, dashpot, mass, rigid, connector, plane stress, plane strain, axisymmetric, heat transfer), shape, order (linear, quadratic), nodes per element given in the file, integration (full, reduced, incompatible modes, hybrid, modified), used as geometry; a description of each type |
| **Mesh quality** | Per type, from the corner nodes: edge length min / mean / max (mm), aspect ratio (longest / shortest edge) min / mean / max and the count above 10; solids: volume min / mean / max and total (mm^3), inverted elements; shells: area min / mean / max and total (mm^2), corner angle min / max (deg) and the count below 30 deg, warping of quadrilaterals (largest angle between the two triangles of a diagonal, deg) and the count above 10 deg |
| **Element sets** | Elements (and numbers not in the file), element types, section kind, material, volume (mm^3; shells: area x thickness), area (mm^2), mass (kg, with the density of the material), extent; the total mass and the centre of mass of the sets with a section and a density |
| **Node sets** | Nodes (and numbers not in the file), `GENERATE`, extent |
| **Surfaces** | `*SURFACE` name, type and data lines |
| **Materials** | E (MPa), nu, density (kg/m^3; t/mm^3 below 1e-3 converted), plastic curve (points, yield stress, last stress and strain), expansion, hyperelastic constants, damping, the material keywords with their parameters, used by a section |
| **Sections** | Element set, kind (solid, shell, beam, membrane, ...), material, elements, thickness, parameters (`OFFSET`, `SECTION`, `ORIENTATION`, ...), data line values |
| **Constraints, interactions, amplitudes, initial conditions** | `*TIE` (surface pairs, parameters), `*COUPLING` (reference node, surface, kinematic or distributing), `*MPC`, `*EQUATION`, `*RIGID BODY`, `*CONTACT PAIR`, `*SURFACE INTERACTION` (behaviour, friction coefficient), `*SPRING`, `*MASS`, `*ORIENTATION`, `*TRANSFORM`, `*AMPLITUDE` (points, time range), `*INITIAL CONDITIONS` (type, lines) |
| **Steps** | Per step: name, step parameters (`NLGEOM`, `INC`, ...), procedure (`*STATIC`, `*DYNAMIC`, `*FREQUENCY`, `*BUCKLE`, `*HEAT TRANSFER`, ...) with its parameters and data line (time increments or number of modes), `*BOUNDARY` lines and their node sets, `*CLOAD` lines and the total force (N) and moment (N mm) (a node set entry: the value x the nodes of the set), `*DLOAD` lines per load type, `*DSLOAD` lines, amplitudes, output requests (`*NODE FILE`, `*EL FILE`, `*NODE PRINT`, ...) with their variables, other keywords |
| **Material curves, amplitudes, functions** | Plots: the `*PLASTIC` table of each material (true stress against true plastic strain or true total strain; one curve per temperature), the `*AMPLITUDE` points (factor against step time, or total time with `TIME=TOTAL TIME`); .rad: `/MAT/PLAS_TAB` (its `/FUNCT` curves times Fscale, one per strain rate), `/MAT/PLAS_JOHNS` (Iflag 0: a + b eps_p^n) and the `/FUNCT` curves. **Curve** chooses one curve or **(all)** (all by default up to 8 curves); **CSV** downloads the curves shown |
| **Keywords** | Every keyword with its count and whether the program reads it; a click on a keyword shows its first line in **File text** |

.rad files: file, keywords (`/NODE`, `/SHELL`, `/MAT/<law>`, ...), nodes, element types, mesh quality, parts as element sets (property kind, thickness, material, mass) and materials.

**Search** (top of the **Input file** page) finds nodes or elements of the file (`drawgen/inpquery.py`):

| Search | Nodes | Elements |
|---|---|---|
| **number** | Numbers and ranges, for example `5, 10-20, 33` | Numbers and ranges |
| **box** | x, y, z ranges (mm; an empty field: open) | Centroid in the ranges |
| **near a point** | Point x, y, z (mm), **radius** (mm) and / or **nearest** (count; both empty: the nearest one); **Pick in view** takes a point clicked on the model | Centroid near the point |
| **set** | A `*NSET` (.rad `/GRNOD`) | A `*ELSET` (.rad part) |
| **type** | The nodes of the elements of a type | The elements of a type |
| **of elements** / **on nodes** | The nodes of the given elements (mid-side nodes included) | The elements on the given nodes |
| **coincident** / **quality** | Coincident nodes within a tolerance (mm; empty: 1e-6 x the model diagonal), in groups | **inverted** (volume <= 0), **aspect ratio above**, **warping above** (deg), **corner angle below** (deg), **shortest edge below** (mm), **volume / area below**; sorted from the worst |

**rows** limits the listed rows (default 500); the count of all found items is given.
Node rows: number, x, y, z (mm), distance to the point, the sets of the node, the elements on the node.
Element rows: number, type, nodes, sets, section kind and material of its set, centroid (mm), distance, volume (mm^3) or area (mm^2) and inverted, shortest and longest edge (mm), aspect ratio, smallest and largest corner angle (deg), warping (deg).
The rows found are marked in the view: nodes and element centroids as red points, the element edges as orange lines.
A click on a row highlights that node or element in the view (blue point, blue edges and faces of the element) and in the table; a second click on the row, or **Show all**, removes the highlight.
**Select in view** picks nodes or elements (the first drop-down of **Search**) by clicks on the model: a node is the node nearest to the clicked point; an element is the element at the clicked point (else the element with the nearest centroid). With **set** or **type** and a set or type chosen, the pick is restricted to that set or type. A click replaces the rows with the picked item; Shift+click adds it to the rows. The picked item is highlighted. **Stop selecting** or Esc ends the selection.
**Clear** removes the results and the marks; **CSV** downloads the rows.
The search and its results are kept while the page is drawn again.
**Report** shows the contents as a 96-column text in a new browser window; **Download report** saves it as `<file>_contents.txt`; **↻** reads the file again (the contents are kept per file until it changes). The open sections stay open when the page is drawn again.

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
| Surface | As several faces (the faces of the surface; **or surface** in the support panel) |
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
| **Master**, **Slave**: **Set from selection**, **Clear**, **or surface…**, **Swap**, **Select** | Faces of each side from the face selection, or a surface (`master_surface`, `slave_surface`); **Swap** exchanges the sides; **Select** puts the faces of the pair into the selection |
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

A surface (**or surface** in the load panel) acts as its faces. Several faces: a force or moment is distributed over all faces together by area (one total), a pressure acts on each face. Several edges: a line load on each edge. A load takes faces or edges, not both, and not bodies (the faces of selected bodies are taken).

**Pick** in the load panel takes the selected faces, edges or reference point, or starts a selection (a click on a member end or a member takes it), and sets the type to match (pressure: faces only; line load on an edge: edges only); **Show** selects the target in the view. Forces, moments and pressures on a face of a shell are distributed over the shell nodes of the face.

### 12.8.1 Steps, amplitudes and initial velocities

| Panel | Function |
|---|---|
| **Steps** | The steps of a static analysis, solved in sequence. Without steps the analysis has one static step with the increments of **Nonlinear step** ([section 12.3.2](#1232-materials-and-nonlinear-step)). **Add step** makes the steps **Step 1** and **Step 2** (then one more each time). Per step: name; **Kind** **static** (`*STATIC`), **dynamic (implicit)** (`*DYNAMIC, ALPHA=-0.05`) or **dynamic (explicit)** (`*DYNAMIC, EXPLICIT`); **Time (s)** (static default 1, dynamic 0.01); **1st inc.** and **Max inc.** (fractions of the step time; static 0.1 and 0.25, dynamic 0.01 and 0.05; explicit: **1st inc.** is the time increment); **Incs** (largest number of increments; static 100, dynamic 10000); **Every** (results every n increments). ▲ moves a step up, × deletes it |
| **Steps** factors (support and load properties) | With two or more steps, the properties of a support or load show one factor per step (default 1 in every step). A load is its value times the factor (0: removed). A support with factor 0 is released in that step; its prescribed displacements are scaled by the factor |
| **Amplitudes** | Tabular amplitudes: name and one point per line (time in s from the start of the step, factor), linear between the points (`*AMPLITUDE`), constant outside. **Amplitude** in the load properties: the load follows the amplitude over the step time. Below the amplitudes: the plot of the amplitudes (factor against step time), **Curve** (one amplitude or **(all)**) and **CSV**. The amplitudes are those of the OpenCourant pane ([section 13.4](13-explicit.md)) |
| **Initial velocities** | Velocity (mm/s, global x y z) of the nodes of a target at the start of the analysis (`*INITIAL CONDITIONS, TYPE=VELOCITY`): **Pick** takes the selected bodies, faces, edges, vertices, mesh nodes or elements |
| **History output** | Time history requests (`*NODE PRINT`, `*EL PRINT` in each step, output in `job.dat`). **Add request** adds a request and starts a selection. Per request: name; **nodes** or **elements**; **Pick** (nodes: the selected faces, edges, vertices, bodies, mesh nodes or elements; elements: the selected bodies or mesh elements), or a node set, or a reference point; the quantities; **every** (output every n increments; empty: the **Every** of the step). Nodes: **displacement** (`U`), **velocity** (`V`, dynamic steps only), **reaction force** (`RF`, `TOTALS=ONLY`). Elements: **stress** (`S`), **strain** (`E`), **PEEQ** (plastic materials only), **internal energy** (`ELSE`, `TOTALS=ONLY`), **kinetic energy** (`ELKE`, dynamic steps only). **contact**: a contact pair of the document (not tied) in the drop-down; `*CONTACT PRINT, SLAVE=C<n>S, MASTER=C<n>M` with `CF`. **section**: **Pick** faces of solid bodies; `*SURFACE, NAME=HS<n>, TYPE=ELEMENT` of the element faces of the bodies on the faces and `*SECTION PRINT, SURFACE=HS<n>, NAME=SP<n>` with `SOF, SOM` (the stresses integrated over the element faces). Each node or element request writes the node set `H<n>` or the element set `HE<n>` |

Static steps ramp the loads linearly from the values at the end of the step before; dynamic steps apply them at once. A dynamic step needs densities. A dynamic step makes all steps incremental (`*STEP, INC`), with `ENER` in the element output of the first step. `*BOUNDARY, OP=NEW` is written in the first step and in a step where a support is released; in the other steps the boundary conditions are modified. Loads of two amplitudes (or one with and one without an amplitude) on the same node and direction in one step are refused (CalculiX takes one amplitude per node and direction). The reactions and the applied load of an increment are those of the loads at its time (ramp, step or amplitude). The report lists the steps with their kind, time, increments and loads, and the supports released in a step.

## 12.9 Results

| Table | Content |
|---|---|
| Bodies | **Show** (check box): the body is drawn in **Show** **Mesh** and **Results**; the colour range is taken from the bodies shown, members are not drawn while a body is hidden. **Show all**; **Show selected**: only the bodies selected in **Show** **Model** (**Bodies**; a selected face gives its body or section; a surface body meshed in sections gives those sections). Largest displacement \|u\|, ux, uy, uz (the component of largest magnitude, signed), largest von Mises stress (nodal values averaged by CalculiX) and, with a plastic material, largest equivalent plastic strain (PEEQ) per body and shell. Shells: CalculiX writes the expanded 3D elements; the displacement of a shell node is the mean of its bottom and top layer nodes, the stress that of the layer with the larger von Mises stress |
| Members | Largest section forces in the local axes: N (tension positive), V1, V2, T, M1, M2, and sig = \|N\| / A + \|M1\| c2 / I22 + \|M2\| c1 / I11 (ROUND and PIPE: \|N\| / A + M r / I). Section forces are those of the positive face (force of the part towards end B on the part towards end A), evaluated at both element ends and at the quarter points |
| Fasteners | N, shear V, bending moment M, torsion T, and sig = \|N\| / A + M d / (2 I) |
| Shell mesh | After **Mesh** and with the results: structured and free faces of the shells, element quality (gamma, 1 for a square, 0 for a degenerate element) minimum, mean and number below 0.3, shortest and longest element edge (mm). The report lists the same values per shell and section |
| Reactions | Force and moment of each support (moment about the weighted face centre or about the member node), their sum, and the applied loads (increments: the loads x the step time) |
| Load history | Nonlinear step: one point per output increment; **x** and **y** from: step time, max \|u\|, Fx, Fy, Fz, \|F\| of each support, ux, uy, uz, \|u\| of each reference point, max von Mises, max PEEQ. A click on a point shows that increment |
| Time history | The curves of a history request against the total time (s; a static step without increments: one point at the end of the step). **Increments (job.sta)** (with two or more increments): increment size (s), iterations, attempt and step of each increment. **Request** chooses the request, the check boxes the curves. Nodes: ux, uy, uz mean (mm), \|u\| max (mm), vx, vy, vz mean and \|v\| max (mm/s), RFx, RFy, RFz total (N). Elements: von Mises max and mean (MPa) over the integration points, equivalent strain max, PEEQ max, internal energy and kinetic energy (mJ). Contact: Fx, Fy, Fz total on the slave surface, normal force (+ = tension), shear force (N), area (mm^2). Section: Fx, Fy, Fz total, normal force, shear force (N), torque, bending moment, Mx, My, Mz about the centre of the faces (N mm), area (mm^2). The values at the cursor are shown in the upper-left of the plot. A click shows the nearest increment. **CSV** downloads the curves shown, a time column per curve |
| Probe and path | Static analyses. **Probe**: a click on the result adds the nearest node of the clicked face (up to 8 nodes; **Probe** again ends the clicks); the curves are the **Result** field at the nodes against the total time (s) over the increments, else against the step number over the steps. A click on the curve shows the nearest increment. **Path**: clicks on the two ends; the curve is the **Result** field of the state shown along the straight line between the two nodes (61 points, distance in mm), at the nearest point of the undeformed body surfaces (linear on the surface triangle). **Clear** removes the probes and the path; **CSV** downloads the curves. The probes and the path are drawn on the result |

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

Run monitor: while the solver runs, **Results** shows the run, read every 1.5 s from `solver.log`, `job.sta`, `job.cvg` and `job.dat`:

| Item | Content |
|---|---|
| Stage | The computation step of the solver from the last matching line of `solver.log`: Reading the input file, Setting up the matrix structure, Assembling the stiffness matrix, Factorising the system of equations, Computing the stresses and writing the results, Finished. A step with increments: step, increment, attempt and iteration from `job.cvg` before the stage. The last increment of `job.sta`: step, increment, attempt, cutback, iterations, step time, total time, increment size, number of increments |
| Process | Elapsed time (s), threads (`OMP_NUM_THREADS`, the number of processor cores), CPU use (% of one core, over the last poll interval), resident memory (MB) of the `ccx` process, and with two or more increments the share of the analysis time (the sum of the step periods) done and the remaining time estimated from the rate of the last six increments |
| Stages | The stages and their durations (s): the stages before the first increment, then Increments, then Finished; for a linear step the stages of the whole run |
| **Convergence** | The iterations of `job.cvg` against the iteration count: residual force and displacement correction (% of the convergence limit; 100 % is the limit), contact elements, attempt. Logarithmic value axis; dashed lines at the first iteration of each increment attempt (step, increment, attempt in the tooltip). The check boxes choose the curves |
| **Time history** | The curves of the history requests and of **Increments (job.sta)** so far |
| **Solver output** | The last 24 kB of `solver.log`. **Follow** scrolls to the end at each update; **Open solver.log** opens the whole file in a new tab (`/api/analysis/log/<Name>`). CalculiX writes the increments and iterations as it runs and the messages of the input reading (`*INFO`, `*WARNING`, `STEP`) when it exits |

A solve that stops with an error keeps the run monitor with the solver output until the next **Solve**. After a solve the **Run** block of **Results** gives the solver time, the threads, the stages, the numbers of increments and iterations, **Convergence** and **Solver output** (folded) of that run; they are stored in `results.json.gz`.

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
| `--batch explicit <Name>` | Meshes and writes `explicit/<Name>/model/<Name>.inp` as **Mesh** of the explicit pane (**Solver** **OpenCourant (explicit)**); prints the bodies, the shell mesh values and the node sets |
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
