[Contents](../README.md) · [← 12. Analysis](12-analysis.md) · [14. Tests →](14-tests.md)

# 13. Explicit

The **Explicit** tab builds OpenCourant decks from an Abaqus .inp, runs them on this PC or on a Linux server, and shows the results.
The deck build, the run folders, the solver control and the post-processing are the ORC\*\*3 v1.0 code (OpenRadioss CalculiX Converter and Control) in `drawgen/explicit/`.
`inp2rad.py` (Altair Engineering, MIT licence) converts the .inp to the starter deck.
OpenCourant (https://github.com/OpenCourant), the community continuation of OpenRadioss, runs the decks (installation: [section 1.1](01-installation.md#11-solvers)).
The .inp comes from the ShinyCAD geometry ([section 13.3](#133-model)), from the deck generator ([section 13.3.1](#1331-deck-generator)) or from PrePoMax.

Units: mm, t, s, N, MPa; density in t/mm^3 in the .inp and the decks, in kg/m^3 in the **Materials** table; velocity in mm/s; energy in mJ.

## 13.1 Executables and settings of this PC

| Program | Use |
|---|---|
| OpenCourant for Windows: `starter_win64`, `engine_win64`, `anim_to_vtk_win64`, `th_to_csv_win64` | Local runs. Taken from **OpenCourant exec folder** (Solve panel); when the field is empty, from the first `solvers\*\exec` or `solvers\*\*\exec` folder of the program that holds `starter_win64.exe` ([section 1.1](01-installation.md#11-solvers)), else from PATH |
| `ssh`, `scp` (OpenSSH of Windows) | Remote runs. Task-spooler (`tsp`) and OpenCourant (`starter_linux64_gf`, `engine_linux64_gf`, `anim_to_vtk_linux64_gf`, `th_to_csv_linux64_gf`) on the server |
| ParaView `pvbatch.exe`, `paraview.exe` | **Extract Strains**, **PV Images**, **Open in ParaView**. Empty fields: searched in `C:\Program Files\ParaView*`, `Documents\ParaView*` and `C:\ParaView*` |
| matplotlib (optional, not installed by `start.bat`) | `<job>_KE.png` in the build folder |

With an exec folder (**OpenCourant exec folder**, or found in `solvers\`), the local solver processes get the exec folder and the existing folders `extlib\hm_reader\win64`, `extlib\h3d\lib\win64` and `extlib\intelOneAPI_runtime\win64` of the OpenCourant folder (the parent of the exec folder) on PATH, `RAD_CFG_PATH` = `<OpenCourant folder>\hm_cfg_files`, `RAD_H3D_PATH` and `KMP_STACKSIZE` = `OMP_STACKSIZE` = 400m, where these are not set.
The line below the fields in the Solve panel gives the executables found.

The fields **Env**, **Threads**, **OpenCourant exec folder**, **Server (user@host)**, **SSH Port**, **Env script**, **Exec dir**, **Scratch dir**, **Share map**, **pvbatch** and **paraview** are settings of this PC and are written to `config.local.json` > `explicit`.
When there is no `explicit` entry, they are read from the ORC\*\*3 configuration `%APPDATA%\ORC3\workspace_config.json` when it exists.
All other fields are stored in the explicit document.

## 13.2 Documents and folders

| Path | Content |
|---|---|
| `work/<Name>.exp.json` | Explicit document: source, materials, bodies, mesh settings, supports and the Build, Solve and Results settings |
| `explicit/<Name>/model/<Name>.inp` | .inp written from the ShinyCAD geometry or the deck generator (**Write .inp**); `mesh/` holds the bodies passed to gmsh; `<Name>_Parameters.pmp` holds the PrePoMax parameter table of the deck generator thicknesses |
| `step/<Name>_deck.step`, `step/<Name>_deck_model.json`, `step/<Name>_deck_properties.txt`, `work/<Name>_deck.part.json` | Deck generator **Generate STEP**: STEP of the deck structure, deck model (input of `deck_elsets.py` of DECK_GENERATOR), properties report, part with one **Import surface** feature per component |
| `explicit/<Name>/runs/<date>_r<NNN>_<description>/` | Run folder: `run.json` (description, notes, archived model, settings of every build), `model/` (copy of the source .inp, and of the .pmx with the same name next to it), `console.log` (the console lines while the run is selected), one build folder per build |
| `<run>/<job>_b<NN>/` | Build folder: `<job>_bNN_0000.rad` (starter), `<job>_bNN_0001.rad` (engine), `<job>_bNN_settings.txt` (settings report, 96 columns), solver listings `_0000.out` and `_0001.out`, animation files `<job>_bNNA001...`, with **Convert to VTK** `<job>_bNN_001.vtk ...` and `<job>_bNN.vtk.series`, time history `<job>_bNNT01`, `<job>_bNN_Results.csv`, `<job>_bNN_KE.png`, ParaView session `<job>_bNN_pv.py` and `<job>_bNN_pv.json`, `principal_strains_summary.csv` |
| `explicit/run_history.json` | Finished jobs of the project (200 newest) |

The job name is the name of the source .inp with the build number: `<inp name>_b01`, `_b02`, ... (the highest number in the output folder plus one).
Renaming the document in the **Project** tab renames `explicit/<Name>/` and the model .inp.
Without an open project the folders are `explicit/` and the document folder of the program.

## 13.3 Model

| Control | Function |
|---|---|
| **Source** | **ShinyCAD geometry (assembly or part)**: the saved assembly or part chosen in **Geometry** (toolbar); the surface bodies of a part that are not hidden are drawn translucent and are not meshed. **Deck generator (stiffened panel, shells)**: [section 13.3.1](#1331-deck-generator). **External .inp (PrePoMax)**: the meshed .inp in the **.inp** field |
| **Update** | ShinyCAD geometry: loads the geometry again from the saved assembly and parts; the mesh of the old geometry is cleared. The server compares the assembly file and the files of its parts (and their imported STEP files) with the loaded geometry when the tab is shown, every 4 s and when the window gets the focus; a change marks **Update** orange. Face, edge and node set references keep their face and edge numbers |
| **.inp**, **…**, **Show mesh** | External .inp: path; **Show mesh** draws the nodes and elements (*NODE, *ELEMENT; solids C3D4, C3D10, C3D8, C3D8R, C3D8I, C3D20, C3D6, C3D15; shells S3, S4, S4R, S8R, R3D3, R3D4, M3D3, M3D4) with one colour per ELSET |
| **Materials** | **Name**, **Library** (an entry of the ORC\*\*3 material library, or **(elastic: E, nu, rho)**), **E (MPa)**, **nu**, **rho (kg/m^3)**; **Add material**, × deletes; **Default**: material of the bodies without one. **Material** drop-downs (bodies, shells, sections): **(default: ...)** with the default material, the model materials as `name - library entry` or `name - law, E MPa, nu, rho kg/m^3`, and under **Library** the library entries not used by a model material; choosing a library entry adds a model material of that entry (named after the entry without the bracketed part) and assigns it |
| **Bodies** | One row per component with a solid: **Role** **deformable**, **rigid (impactor)** or **off**; **Material**; **Size (mm)** element size of the body (empty: **Element size**); **Mesh** strategy of the body |
| **Shells** | One row per surface body of a component: **Role** **deformable**, **rigid (impactor)** or **off**; **t (mm)** (empty: 10 mm); **Position** **mid**, **positive (SPOS)**, **negative (SNEG)** (`*SHELL SECTION` `OFFSET`; inp2rad does not read it); **Material**; **Size (mm)**. Deformable shells are meshed together and share their nodes where they touch (**Bonded**) |
| **Sections**, **Node sets** | Shown with shells, as in the Analysis tab ([section 12.3](12-analysis.md#123-model)); **Model** of a section: **deformable**, **rigid (impactor)** or **off**. A support takes a node set as target (**Support** in the node set row) |
| **Reference points**, **Springs**, **Joints**, **Equations** | As in the Analysis tab ([section 12.6.1](12-analysis.md#1261-reference-points), [section 12.6.2](12-analysis.md#1262-springs-joints-and-equations)); also for the ShinyCAD geometry without shells. Rotations at a mesh node: shell nodes. Support (toolbar) also takes a reference point (click within 10 px) |
| **Mesh** | **Element size (mm)** (empty: bounding box diagonal / 20), **Minimum size (mm)** (empty: element size / 5), **Strategy** (**Tetrahedra (free)**, **Hexahedra, structured (block cells)**, **Hexahedra by subdivision**; [section 12.3.1](12-analysis.md#1231-mesh-settings)), **Tetrahedra** C3D4 or C3D10, **Hexahedra** C3D8R or C3D8, **Elements per 360 deg** (empty: 12), **Shell elements** S4R, S4 or S3, **Shell mesh** (as in [section 12.3.1](12-analysis.md#1231-mesh-settings)), **Bonded: touching deformable bodies share nodes** ; **Structured quadrangles**, **Min divisions per interval**, **Section sizes**, **Fuzzy (mm)** ([section 12.3.1](12-analysis.md#1231-mesh-settings)) |
| **Velocities** | **Add initial velocity**, **Add imposed velocity**. **Target**: a body (solid, shell or section; rigid bodies marked), a reference point or a node set. A shell whose faces are in sections is listed with the section names (`(in section IMPACTOR)`); as a target it gives the nodes of its faces, and a shell in a rigid section gives the rigid body of that section. **vx vy vz** (mm/s). Initial: all nodes of the target (a rigid body: also its reference node; a rigidly coupled reference point: also the coupled nodes), `*INITIAL CONDITIONS, TYPE=VELOCITY`, inp2rad /INIVEL/TRA. Imposed: the reference node of a rigid body or the node of a reference point, else all nodes of the target; **wx wy wz** (rad/s); **Components** imposed (a component at 0 is held); **Ramp (s)**: 0 to the value in the ramp time, then constant; `*AMPLITUDE` and `*BOUNDARY, TYPE=VELOCITY`, inp2rad /IMPVEL with its /FUNCT. An imposed velocity on nodes held by a support stops **Mesh** with the support name. Teal arrow at the body centre or the reference point |
| **Masses** | **Add point mass**, **Add distributed mass**. Point mass: **Reference point**, **Mass** (kg) on the node of the point. Distributed mass: **Target** **faces (picked)** (**Add faces**: the selected faces and the faces of the selected bodies, or a selection until **Done**; **Clear**), a body or a node set; **total mass** (kg) or, on faces, **mass per area** (kg/m^2). Faces: consistent area weights of the face nodes; body: element volume (solids) or area (shells) in equal shares to the element corners (a shell with faces in sections: area weights of those faces); node set: equal shares. Written as /ADMAS type 5 (mass of single nodes) in `**RAD` lines of the .inp and taken into the starter deck by the build. Mass only (no rotational inertia). Purple sphere at the reference point, purple faces |
| Mass checks (**Mesh**) | A rigid body without mass (density 0 and no masses on it) stops **Mesh**. An initial velocity on a reference point with **Coupling** none, no point mass and no spring stops **Mesh**. The summary gives the model mass (kg) and the mass of each rigid body with its added mass |
| **Initial state (static)** | Static solve (CalculiX) on the mesh of the last **Mesh**: **Analysis** (an Analysis document of the project: its supports, loads, fasteners, reference points, springs, joints, equations, contacts, node sets and nonlinear step settings), **Materials** **elastic (E, nu, rho)** or **as Explicit (library curves, nonlinear)**, **Solve static** (writes the model .inp first when it is out of date). The bodies, shells, sections and materials are those of this model; rigid bodies are left out; S4R elements are solved as S4 and C3D8R as C3D8I (same nodes). The line below gives the analysis, time, element counts, maximum displacement (mm), von Mises stress (MPa) and plastic strain, and the warnings (members and plates of the analysis left out; fasteners in the static solve only). **Use in Build**: the build moves the /NODE coordinates by the displacements (**Deformed geometry**) and writes `/INIBRI/STRS_FGLO` for the solids (1 integration point: the mean of the CalculiX integration points; 8-node bricks Isolid 1, 4-node tetrahedra Isolid 0; internal energy 0.5 s : C : s, density of the material) and `/INISHE/STRS_F/GLOB`, `/INISH3/STRS_F/GLOB` for the shells (5 points through the thickness at T = -1, -0.5, 0, 0.5, 1, linear through the two integration point layers of the expanded element; membrane and bending energy) (**Stresses**), with the plastic strain (**Plastic strain**). Files: `model/<Name>_mesh.json.gz` (mesh of the last **Mesh**), `model/<Name>_initial.json.gz` (result), `model/initial/` (CalculiX job). A result of an older .inp is refused |
| Reference point on a rigid body | A reference point coupled to faces, edges or node sets of one rigid body is a node of that rigid body (its `*NSET RB_<body>`, the /RBODY node group); no coupling is written. Velocities and supports of the point act on the REF NODE of the rigid body; with the point away from the REF NODE, an imposed velocity or support needs rx, ry, rz held (imposed angular velocity 0), else **Mesh** stops with the offset. A point mass on the point adds to the rigid body. A point coupled to a rigid body and to other bodies stops **Mesh** |
| **Panels** | Check boxes that show or hide the **Sections**, **Node sets**, **Reference points**, **Springs**, **Joints**, **Equations**, **Velocities**, **Masses** and **Initial state** panels; kept in the document (`panels_hidden`). A hidden panel with items shows their number. Hidden items are still written to the .inp |
| **Supports** | **Support** (toolbar): a support on the selected faces, edges and bodies or on the selected reference point; with nothing selected, a selection for the support until **Done** or Enter ([section 12.2.1](12-analysis.md#1221-selection)). Several items: one support on the nodes of all of them (target `{"faces", "edges", "bodies"}`). **Preset** (**fixed**, **pinned**, **symmetry X**, **symmetry Y**, **symmetry Z**) sets the check boxes; **ux**, **uy**, **uz**, **rx**, **ry**, **rz**: the held components; the translations act on all nodes of the target, the rotations on its shell nodes. **Pick** replaces the target in the same way; **Show** selects the target in the view; × deletes |
| **Mesh** (toolbar) | Meshes the bodies and shells (gmsh), writes `explicit/<Name>/model/<Name>.inp` and draws the mesh (**Show** **Mesh**). The table gives the nodes, elements, ELSET, material and reference node of each body, shell and section, the shell mesh values ([section 12.9](12-analysis.md#129-results)) and the node count of each node set. `run.py --batch explicit` does the same without the browser ([section 12.11](12-analysis.md#1211-batch-mode)) |

The .inp of the ShinyCAD geometry holds:

| Keyword | Content |
|---|---|
| `*NODE` | Mesh nodes; one reference node per rigid body at the centre of mass of the body (the last node numbers) |
| `*ELEMENT, TYPE=<type>, ELSET=B_<BODY>` | Elements of each body (body name in upper case) |
| `*NSET, NSET=RB_<BODY>` | Nodes of a rigid body |
| `*NSET, NSET=<NODE SET>` | Nodes of each node set (name in upper case) |
| `*NSET, NSET=VEL_<n>_<NAME>`, `*INITIAL CONDITIONS, TYPE=VELOCITY` | Nodes and components of each initial velocity (inp2rad /INIVEL/TRA) |
| `*AMPLITUDE, NAME=VA_<n>`, `*BOUNDARY, AMPLITUDE=VA_<n> , TYPE=VELOCITY` | Ramp and components of each imposed velocity (inp2rad /FUNCT and /IMPVEL; a component at 0: /BCS) |
| `*NSET, NSET=SUP_<n>_<NAME>`, `SUP_<n>_<NAME>_R` | Nodes of the face or edge of a support; `_R`: its shell nodes (rotations) |
| `*MATERIAL, NAME=<NAME>` | `*ELASTIC` and `*DENSITY`; with a library entry the E, nu and density of the entry |
| `*SOLID SECTION, ELSET=B_<BODY>, MATERIAL=<NAME>` | Section of each body |
| `*SHELL SECTION, ELSET=B_<COMPONENT>_<SURFACE>, MATERIAL=<NAME>[, OFFSET=SPOS \| SNEG]` | Section of each shell and of each section (`ELSET=B_<SECTION>`), the thickness on the next line |
| `*RIGID BODY, NSET=RB_<BODY>, REF NODE=<n>` | Rigid bodies; inp2rad writes an /RBODY with the reference node as main node (ICoG 3) |
| `*NSET, NSET=RP_<POINT>`, `*RIGID BODY, NSET=RP_<POINT>, REF NODE=<n>` | Rigid coupling of a reference point (node n); inp2rad /RBODY |
| `*NSET, NSET=SPRING_GROUND` | Nodes of the springs to ground (at end A), held in all six components |
| `**RAD` comment lines | Radioss cards of the kinematic couplings (/RBE2 with /GRNOD/NODE), distributing couplings (/RBE3, one node group per weight), springs (/PART, /PROP/TYPE13 with K1 to K6, /SPRING) and joints and equations (/MPC: node, component 1 to 6, skew 0, alpha per term) |
| `*BOUNDARY` | `SUP_<n>_<NAME>, <dof>, <dof>` for each held translation, `SUP_<n>_<NAME>_R, <dof>, <dof>` for each held rotation |

Rigid bodies are meshed apart from the deformable bodies and share no nodes with them.
After inp2rad, `inp2rad_run.py` writes the `**RAD` cards into `<Name>_0000.rad` before `/END` (`drawgen/explicit/radcards.py`), with identifiers above all identifiers, node and element numbers of the deck. The /PROP/TYPE13 spring acts in the local axes of the spring for ends apart (X from end A to end B).
Each material with a library entry is added to **Library materials** of the build with its name as **Name in model** (rows marked **Model**).

Status bar (below the toolbar): one item per input of the deck build, green when set, amber when it needs a check, red when missing, grey when optional and empty.

| Item | Green | Amber / red |
|---|---|---|
| **Geometry** | ShinyCAD geometry chosen, External .inp path, or Deck generator | red: none |
| **Materials** | every material with a library entry or E > 0, 0 <= nu < 0.5 and rho > 0, and every material used by a body, shell or section defined | red |
| **Bodies** | number of deformable and rigid bodies, shells and sections | red: no deformable body |
| **Sections** | number of sections (shown when there are sections) | |
| **Mesh** | nodes and elements of the last **Mesh** | amber: a model input (geometry, materials, bodies, shells, sections, node sets, supports, constraints, velocities, masses, mesh settings) changed after the last **Mesh**; red: not written |
| **Supports** | number of supports, or the rigid floor of Build | amber: none |
| **Loading** | velocities, the Build **Driver** (not None) and **Gravity** | amber: gravity only; red: none |
| **Mass** | after **Mesh**: the mass (kg) of each rigid body (material and added masses) and the added mass, or the model mass without rigid bodies | amber: a rigid shell without added mass; amber before **Mesh** with rigid bodies or masses (Mesh to check) |
| **Constraints** | number of reference points, springs, joints and equations | grey: none |
| **Initial state** | shown when an Analysis is chosen in **Initial state (static)** or **Use in Build** is on: the analysis, maximum displacement and von Mises stress of the static solve | red: **Use in Build** on and not solved or solved for an older .inp; grey: not used in Build |
| **Deck** | file name of **Target .rad** | grey: not built |

A click on **Materials**, **Bodies**, **Sections**, **Mesh** (with the **Mesh** button), **Supports** (with **Add support**), **Loading** (velocities, **Driver**, **Vx Vy Vz [mm/s]**, **Gravity**), **Masses**, **Constraints** or **Initial state** opens a pop-up with the controls of that input; a second click, × or Esc closes it. The pop-up and the panels show the same values: a change in one is shown in the other. The pop-up opens over the panel column and is moved by its title bar. **Geometry** and **Deck** scroll to the Model and Build panels.

### 13.3.1 Deck generator

The deck generator source is the DECK_GENERATOR code (`deck_stepgen.py`, `deck_mesh.py`) in `drawgen/explicit/`.
It models a flat rectangular deck panel with beams along x and y as shell midsurfaces: the deck plate and the top flanges at z = 0, webs and lower flanges below.
`deck_mesh.py` is unchanged apart from the package import and the usage lines of its module text.
In `deck_stepgen.py` cadquery is replaced by build123d (same OpenCascade calls through OCP).

| Control | Function |
|---|---|
| **X distance [mm]**, **Y distance [mm]** | Panel size (model keys `L`, `B`) |
| **Flange snipe [mm]** | Distance from the web of a crossing beam at which the lower flange of the shallower beam stops |
| **Deck thickness [mm]** | Thickness of the DECK section |
| **Beams** | One row per beam: **name**, **axis** (`x`: the beam runs along x at y = pos; `y`: along y at x = pos), **pos**, **h** (deck midplane to lower flange midplane), **bf_top** (top flange width in the deck plane; it replaces the deck plate there), **bf_bot** (lower flange width; 0: flat bar), **t_web**, **t_flange** (both flanges). The check box selects the row; a click on the row toggles it. Number fields take sums (`400-12`, `6000/8`, `12,5`) and show the result |
| **Add** | New row: a copy of the selected row (or the last row) at the middle of the largest gap along its position coordinate |
| **Delete**, **Clear selection** | Deletes the selected rows (several rows: after confirmation); clears the selection |
| **Pattern…** | Repeats the one selected beam along its position coordinate: **By spacing** (**Count**, **Spacing [mm]**, **Start position [mm]**) or **By length** (**Count**, **Length to fill [mm]**, **Beams sit** **equal bays - ends clear**, **first and last on the ends** or **equal steps from the start**). The preview lists the positions: `*` skipped (outside the panel, or within 0.5 mm of a beam of the same axis), `~` within 10 mm of a beam of the same axis. **Add beams** adds the rows |
| Plan, section | Plan of the panel (deck plate drawn without the regions of the top flanges, as in the mesh and the STEP; top flanges shaded, beam lines coloured by depth, selected beams labelled; the hover text gives name, position and h) and the section of the selected beam (the first beam when none or several are selected) |
| **Sections** | Element set, parameter name and thickness of each section. Beams with one name form one element set; both flanges of a beam share the parameter `<NAME>_FLANGE_t` |
| **Max element size [mm]**, **Min divisions per interval** | Structured mesh: every interval between break coordinates (panel edges, beam lines, flange edges, web depths) gets ceil(length / max element size) divisions, at least the minimum; the plates are cut at the break lines and meshed transfinite, conformal across the junctions |
| **Shell type**, **Triangles** | S4 / S3 or S4R / S3R; **Triangles**: no recombination to quadrangles |
| **Material** | Material of all sections (**(default)**: the **Default** material of the **Materials** table) |
| **Edge supports** | **x = 0**, **x = X distance**, **y = 0**, **y = Y distance**: **free**, **pinned (ux uy uz)** or **clamped (ux uy uz rx ry rz)** for the nodes on the edge plane (deck and webs) |
| **Mesh** (toolbar) | Meshes the deck (gmsh, in a separate process), writes `explicit/<Name>/model/<Name>.inp` and `<Name>_Parameters.pmp` and draws the mesh. The table gives the elements, z range, thickness, PrePoMax section number and parameter of each element set; below: longest element edge, aspect ratio, element edges by the number of plates sharing them (1 free edge, 2 inside a plate, 3 T junction, 4 cruciform) |
| **Generate STEP** | Writes `<Name>_deck.step` (assembly DECK_STRUCTURE, one named and coloured component of sewn shells per element set) `<Name>_deck_model.json` and `<Name>_deck_properties.txt` to the step folder of the project, and the part `<Name>_deck` with one **Import surface** feature per component. A second **Generate STEP** replaces the **Import surface** features of that STEP and keeps the other features of the part. **Open part** opens it in the **Part** tab |

Two beams of one axis within 0.5 mm of each other are refused when typed and reported as an error by **Write .inp** and **Generate STEP**.

`<Name>_deck_properties.txt` is a 96-column text report with these sections:

| Section | Content |
|---|---|
| PANEL | Deck plate name, X distance L, Y distance B, deck thickness, flange snipe, material (library entry), density, max element size, element type |
| EDGE SUPPORTS | Edge, plane, node set (`EDGE_X0`, `EDGE_XL`, `EDGE_Y0`, `EDGE_YB`), support, fixed dofs |
| BEAMS | Per beam: name, axis, web line (position and extent), h, bf_top, bf_bot, t_web, t_flange, section type (FB flat bar, T flange at z = -h, I both flanges) |
| SECTION PROPERTIES | Per beam name and section: designation (`FB 150x6`, `T h x t_web / b x t_flange`, `I h x t_web / b_top x t_flange / b_bot x t_flange`), area A (mm^2), centroid zc from the deck midplane (mm), second moment I about the centroid (mm^4), mass per length (kg/m). Midsurface dimensions; the deck plate is not included |
| ELEMENT SETS AND SHELL SECTIONS | Element set, parameter name, thickness (mm), number of plates, area (mm^2), mass (kg), totals, STEP components |
| PLATES | Every plate region of every element set: x, y and z min and max (mm), area (mm^2). The top flange regions are cut from the deck plate |
A gap below 10 mm is confirmed when typed and listed as a warning.
A beam position outside the panel and a section thickness of 0 mm are errors.

The model view (**Show** **Model**) draws the plates of the deck model, one colour per element set.
The plates come from `deck_stepgen.deck_model`, the one definition of the crossing rules for the mesh and the STEP: webs are split at every crossing, top flanges are continuous and the deeper beam takes the crossing square (equal depth: the beam listed later), lower flanges of the shallower beam stop **Flange snipe** short of the crossing web (equal depth: the beam listed first is continuous).
The z = 0 elements cover the panel area X distance x Y distance exactly once.

The .inp of the deck generator holds:

| Keyword | Content |
|---|---|
| `*NODE` | Mesh nodes (gmsh numbering) |
| `*ELEMENT, TYPE=<type>, ELSET=<SET>` | One block per element set and element type: DECK, `<NAME>_WEB`, `<NAME>_FLANGE` (top), `<NAME>_LOWER_FLANGE` |
| `*NSET, NSET=EDGE_X0`, `EDGE_XL`, `EDGE_Y0`, `EDGE_YB` | Nodes on the supported edge planes |
| `*MATERIAL, NAME=<NAME>` | `*ELASTIC` and `*DENSITY` of the material |
| `*SHELL SECTION, ELSET=<SET>, MATERIAL=<NAME>` | One section per element set with the thickness of the beam table, in the order of the element sets (PrePoMax Section-1, Section-2, ...) |
| `*BOUNDARY` | `EDGE_<edge>, 1, 3` (pinned) or `EDGE_<edge>, 1, 6` (clamped) |

The nodes, elements and element sets are those of `deck_mesh.py` for the same model; the element blocks per set replace the single `ALL_S4` block of `deck_mesh.py`, because inp2rad assigns properties by the ELSET of the *ELEMENT block.

## 13.4 Runs

| Control | Function |
|---|---|
| Path, **Open folder** | `explicit/<Name>` of the document |
| **Description**, **Notes**, **New run** | Creates `runs/<date>_r<NNN>_<description>/` (NNN: the highest number in `runs/` plus one) with `run.json` and a copy of the source .inp in `model/`, and selects it |
| Run list | **(no run: decks next to the .inp)** and the run folders, newest first, with the number of builds and decks and the PrePoMax version of the archived .inp (**PMX**). A click selects the run: **Output Dir** of the build, and the newest deck becomes **Target .rad**. **Decks** lists the decks of the selected run; a click sets **Target .rad** |
| **Open** | Opens the run folder on this PC |
| **Clean…** | Lists the regenerable solver output of the run and its build folders (A-files, T-files, `.vtk`, `.vtk.series`, `.rst`, `_extract_principal_strain.py`) with the number of files per folder and the size in MB, and deletes them after confirmation. Decks, `model/`, `run.json`, CSV and PNG files are kept |
| **Settings** | Restores the Build and Solve settings of the last build of the run from `run.json`; paths are kept. Settings of older ORC\*\*3 versions are converted (table in section 13.5) |

## 13.5 Build

**Build** (toolbar) or **Build deck** builds the decks with the settings of the Build panel.
With the ShinyCAD geometry, **Build** first writes the model .inp again (**Mesh**) when there is no .inp of the document or a model input changed after the last **Mesh** (the **Mesh** item of the status bar is amber), and with **Use in Build** of **Initial state (static)** solves the static model when it is not solved for that .inp. A build with **Use in Build** stops when no static result of the model .inp exists.

| Field | Function |
|---|---|
| **Analysis** | **Impact / drop test**, **Quasi-static (load-hold-unload)**, **Rivet coupon calibration**, **Advanced (all features)** (default); selects the fields and the Rivet section shown (table below) |
| **Import ORC\*\*3 settings** | Build settings of the ORC\*\*3 configuration `%APPDATA%\ORC3\workspace_config.json`; paths are kept |
| **Downgrade 2nd-order → linear** | Second-order elements of the .inp converted to first order (`inp_to_linear.py`, nodes kept) before inp2rad |
| **Output Dir**, … | Folder of the build: the selected run folder, or any folder (… : folder dialog); empty: next to the .inp |
| **Time (Tstop) [s]** | End time of the /RUN card |
| **Frames** | Animation frames: /ANIM/DT = Tstop / Frames |
| **Fric** | Friction coefficient of the general contact and the rigid floor |
| **Min dt [s]** | /DT/NODA/CST DTmin: nodal mass is added to hold the time step at this value; 0 = off |
| **target DM/M %**, **Suggest Min dt…** | Reads the added-mass table of the starter output `_0000.out` of **Target .rad** (**Run Starter Only**) and offers the Min dt for the target first-cycle added mass, interpolated in the /DT/NODA/CST table (scale 0.9) |
| **Rigid floor**, **Floor Z [mm]** | **Add Infinite Rigid Floor (Drop Test)**: /RWALL/PLANE at Z, normal +Z, friction **Fric**, all nodes |
| **Library materials** | **Library** and **Name in model**: the material of the .inp with this name (case-insensitive) is replaced by the library card; the first matching row applies. **Add slot**, × deletes |
| **Failure**: **Model**, **Plastic fail strain** | **Equivalent plastic strain**: the strain is written to every LAW2 and LAW36 material. **Johnson-Cook (triaxiality)**: /FAIL/JOHNSON with **D1** to **D5**, **eps0**, **Ifail_sh** on the library materials. **Max principal strain**: /FAIL/TENSSTRAIN with **et1**, **et2**, **SoftBand**, **S_Flag** (23: max principal true strain), **FAILIP** on the library materials. The help line gives the rule of the model |
| **Gravity** | /GRAV -Z, 9810 mm/s^2, ramped over the first 5 % of Tstop, all nodes |
| **Contact** | **TYPE7 (node-to-surface)**, **TYPE19 (TYPE7 + edge-to-edge)**, **TYPE24 (constant stiffness)**, **None**; one interface over all parts. TYPE7 has Idel = 1 when the failure model deletes elements |
| **Subfolder per build** | Decks and solver output in `<Output Dir>/<job>_bNN/` |
| **Driver** | **Explicit (Vx Vy Vz below)**: /INIVEL/TRA on the main node of the /RBODY. **Load-hold-unload (imposed disp)**: /IMPDISP, **Load-hold-unload (force /CLOAD)**: /CLOAD on the main node with a /FUNCT ramp-hold-ramp-settle profile (**Peak disp** or **Peak force**, **Dir**, **Ramp up [s]**, **Hold [s]**, **Ramp down [s]**, **Settle [s]**, **Ease**, **Pts/ramp**). **None (deck as-is)** |
| **Vx Vy Vz [mm/s]** | Initial velocity of the impactor |
| **Travel** | Explicit driver: \|V\| = sqrt(Vx^2 + Vy^2 + Vz^2) in mm/s, the distance covered in Tstop, and the time in s for 100 mm, 500 mm and 1000 mm at \|V\| (NOT reached: the time exceeds Tstop). Nothing is written to the deck |
| **Target RP** | /RBODY name or id driven by **Driver** (empty: the deck must have one /RBODY) |
| **Rigid parts**, **List Parts** | External .inp only (a ShinyCAD model sets rigid bodies in **Bodies**, **Shells** and **Sections**). PID or part name substring (comma between several): each part becomes an /RBODY over its nodes with the main node at its centre of gravity. **List Parts** writes the PID and name of each /PART of the newest deck to the console |
| **Inertia payload (JSON)**, … | External .inp only (a ShinyCAD model uses **Masses**). Mass and inertia of the impactor (inertia_builder / inertia_calc file, flat payload or primitives file) merged into the single /RBODY of the deck (ICoG 3), or a free-node /RBODY when the deck has none; … : file dialog |
| **Reload / verify** | Summary of the payload: mass, CG, inertia tensor about the CG, largest product of inertia as % of the largest diagonal term, STATUS READY or INVALID (mass and the three diagonal terms > 0) |
| **Open inertia builder** | Starts `inertia_builder.py` (Tools) |
| **Clear (disable)** | Empties **Inertia payload (JSON)** |
| **Tie Mode**, **Tie dist [mm]** / **Fallback dist [mm]**, **List Parts** | **Tie dist** is disabled in **Scoped pairs** and **None**. **Auto (*TIE from INP)**: /INTER/TYPE2 from the *TIE of the .inp (position tolerance, else **Fallback dist**). **Scoped pairs (box below)**: one line `secondary > master : distance` per tie (PID or part name substring). **Single global tie**: one TYPE2 over all parts within **Tie dist**. **None** |
| **Heal Normals** | Shell normals made consistent in each connected area |
| **Disp -> Velocity** | /IMPDISP of the .inp written as /IMPVEL with constant velocity over Tstop |
| **Purge older builds** | Deletes the older build folders of the job after a successful build |
| **?** | Description of each mode of **Model** (failure), **Contact**, **Driver**, **Tie Mode**, of the travel table and of the concentrated mass; the selected mode first |

| Analysis | Hidden fields |
|---|---|
| **Impact / drop test** | **Target RP**, advanced options, Rivet section; **Driver** offers **Explicit** and **None** |
| **Quasi-static (load-hold-unload)** | Rigid floor, **Rigid parts**, concentrated mass, advanced options, Rivet section; **Driver** offers the load-hold-unload drivers and **None** |
| **Rivet coupon calibration** | Rigid floor, **Rigid parts**, concentrated mass, advanced options |
| **Advanced (all features)** | none |

Hidden fields keep their values and act at build time; the Build panel names a hidden field that is active.

The build reads the .inp, removes the velocity *BOUNDARY, runs inp2rad in a temporary folder and adds to the starter deck: the library materials and their /FUNCT curves, the failure cards, Istrain = 1 in /PROP/SHELL, the rigidified parts and the concentrated mass, the groups /GRNOD/PART/9999998 (all parts) and /SURF/PART/EXT/9999999, gravity, contact, ties, rigid floor and the driver.
The engine deck holds /RUN, /DT/NODA/CST, /DT/INTER/DEL, /DT/SHELL/DEL and /DT/SH3N/DEL when elements are deleted, /ANIM/DT and the animation outputs (velocity, displacement, contact forces, von Mises, plastic strain, energy, shell strain tensors at the membrane, upper and lower surface, brick strain tensor), /TH/TITLE and /TFILE.
The build stops with BUILD HALTED and the cause for a CAD file instead of a mesh, element types inp2rad does not convert, elements without a section (/SHELL/0) and two different /INIVEL on one node.

Settings of older ORC\*\*3 versions (**Settings** of a run, **Import ORC\*\*3 settings**):

| Older setting | Converted to |
|---|---|
| Auto-tie on | **Tie Mode** Auto |
| Auto-tie off, scoped pairs given | Scoped pairs |
| Auto-tie off, tie distance > 0 | Single global tie |
| Auto-tie off, otherwise | None |
| Self contact on / off | **Contact** TYPE7 / None |
| No driver mode, velocity given / empty | **Driver** Explicit / None; a build with the old rigid-part mode gives a console note |
| Aluminium 6061-T6 (Johnson-Cook, Lesuer) | Aluminium 6061-T6 (Johnson-Cook) |
| Unknown analysis type | Advanced (all features) |

Reserved ids: 9999997 gravity, 9999998 all-node group and global tie, 9999999 surface and general contact, 999xxxx ties and driver, 9970xxx rigidify, 997xxxx concentrated mass, 9000 + 10 x material id library curves.

### 13.5.1 Rivet

Shown for **Rivet coupon calibration** and **Advanced (all features)**.
The gauge rings measure the relative displacement across a rivet: /TH/NODE output of nodes on a ring around the hole on each plate, averaged per ring.
The code is `rivet_calibration/make_gauge_rings.py` and `rivet_calibration/relative_disp.py` (also in Tools).

| Control | Function |
|---|---|
| **Hole centre** **X**, **Y**, **Z**, **Ring radius [mm]**, **Shank axis** | Ring centre, radius and axis |
| **Plate mid-surfaces** **1**, **2** | Axis coordinate of the mid-surface of each plate |
| **Radial tol [mm]**, **Axial tol [mm]**, **Max nodes/ring**, **First TH grp** | Node search tolerances; nodes per ring (spread by angle); id of the first /TH/NODE group |
| **Build Gauge Rings** | Reads the /NODE block of **Target .rad** and writes `th_gauge_rings.inc` (/TH/NODE, DX DY DZ) and `gauge_rings.json` next to it; the console lists the nodes found per ring. The .inc is included in the starter deck by the user; the engine deck needs /TH/TITLE |
| **Force column**, **Columns…** | Column of the results CSV with the driving force; **Columns…** lists the columns in the console and as choices of the field |
| **Force scale** | Factor on the force (2.0 for a symmetry half-model) |
| **Component**, **Load angle [deg]**, **Shear dir**, **Axis dir** | Relative displacement: **mag**, **x**, **y**, **z**, or **axis** (shear direction · cos(angle) + axis direction · sin(angle); 0 deg shear, 90 deg tension) |
| **Filter [Hz]** | Moving average of force and displacement (empty: none) |
| **Case ID** | Curve label (empty: the CSV name) |
| **Extract F-d** | Curve of the results CSV of the job of **Target .rad** (searched in the deck folder, **Output Dir** and its build folders); writes `<csv>_fd.csv`; peak force and the displacement at failure (force below 5 % of the peak after the peak) in the summary line and the console |
| **Load F-d CSV…** | Curve of an `_fd.csv` file |
| **Clear Curves**, **Save PNG…** | Removes the curves; the plot as a PNG file (file dialog) |

The plot shows all curves (force vs relative displacement, the peak as a dot); drag a rectangle to zoom, double-click for the full range.

## 13.6 Solve

| Control | Function |
|---|---|
| **Target .rad**, …, decks… | Starter deck `<job>_0000.rad` to run; … : file dialog; decks… lists the decks of the selected run |
| **Env** | **Local** (this PC) or **Remote (Linux)**. **Target .rad** and **Output Dir** are remembered per Env (`config.local.json` > `explicit` > `env_dirs`) and restored when the Env changes; for **Remote (Linux)** the console states whether the Target .rad runs in place on a mapped share or by SCP transfer to **Scratch dir** |
| **Threads** | Engine threads (`-nt`) |
| **Stream remote output** | Follows the remote job to the end (status, copy-back, post-processing); required for SCP transfer |
| **Plot KE**, **Extract Strains**, **PV Images** | Post-processing after a run: KE curve and PNG; principal strain summary (pvbatch, stopped after 600 s); PNG renders (pvbatch, stopped after 1800 s). The status row is **Post-processing** with the running step as note (KE plot, ParaView files, Extract Strains, PV Images) until the last step ends |
| **Convert to VTK** | anim_to_vtk conversion of the A-files to `<job>_<n>.vtk` and `<job>.vtk.series` after the engine (default on). Required for **Extract Strains**, **PV Images** and **Open in ParaView**. Off: no `.vtk` files; remote SCP jobs copy the A-files back instead of the `.vtk` files. The 3D view of the Results reads the A-files in both cases |
| **OpenCourant exec folder** | Local executables ([section 13.1](#131-executables-and-settings-of-this-pc)) |
| **Server (user@host)**, **SSH Port**, **Env script**, **Exec dir**, **Scratch dir**, **Share map** | Remote run: `ssh`/`scp` target; script sourced before `tsp`; folder of the Linux executables; work folder for SCP transfer; `WIN => LINUX` path pairs separated by `;` (a run folder on a mapped share runs in place on the server, other folders are copied to **Scratch dir** and the results copied back) |
| **pvbatch**, **paraview** | ParaView executables (empty: searched) |
| **Run Simulation** (toolbar **Run**) | Runs **Target .rad**, or the queue when **Target .rad** is empty or in the queue |
| **Run Starter Only** (toolbar **Starter**) | Starter only; the added-mass table of the `_0000.out` is offered as **Min dt** (confirmation) |
| **Kill** | Local: stops the starter and engine. Remote: kills the running job and empties the tsp queue |
| **Shutdown Server** | `sudo shutdown -h now` on the server (confirmation) |
| Queue: **Add Current**, **Remove Selected**, **Clear List** | Decks run one after the other; the queue is kept in `config.local.json` > `explicit` > `job_queue` and restored when ShinyCAD starts |
| Server: **Show Queue**, **Kill+Flush Server** | Running solver and tsp queue of the server in the status board; kill and flush (confirmation) |

Local run: starter, engine, conversion of the A-files to `<job>_<n>.vtk` and `<job>.vtk.series` (**Convert to VTK**), `th_to_csv` to `<job>_Results.csv`, KE curve, ParaView session files, strain extraction and PNG renders as checked.
Remote run: the same pipeline as one `tsp` job on the server.
Local and remote runs are independent; one batch per environment at a time.

The status board has one row per job: **Status** (Queued, Starter, Starting engine, Running, Post-processing, Done, Starter done, Failed, Killed, Skipped), **Progress** and **T / Tstop** from the engine cycle lines, **ETA**, **ERR** (energy error) and **DM/M** (added mass ratio).
Rows are yellow at |ERR| >= 5 % or DM/M >= 0.02, red at |ERR| >= 15 % or DM/M >= 0.10.
A job fails on `** RUN KILLED`, `MESSAGE ID`, `ERROR TERMINATION`, `** ERROR`, `forrtl: severe` or `Segmentation fault` in the solver output, and on a non-zero exit code of a local run; the note gives the message.
A click on a row selects it for **Remove Selected** and loads its results.
**Run history** lists the finished jobs with date, status, environment, ERR, DM/M and wall time; a click selects the row and loads the results.
**Load Selected** sets **Target .rad** (when `<job>_0000.rad` is in the folder) and **Output Dir** to the folder of the row; **Open folder** opens it; **Remove** deletes the row, **Clear** all rows (confirmation); run folders are not changed.

## 13.7 Results

| Control | Function |
|---|---|
| **Job**, **↻** | Job of the selected run or the status board; **↻** reads the frames and curves again |
| **Plot KE** | Rebuilds the KE curve and `<job>_KE.png` from the results CSV; without a CSV, `th_to_csv` writes `<job>_Results.csv` from the T-file first. Without a job: the newest `_Results.csv` (or T-file) of **Output Dir** |
| **Salvage Results** | Converts the A-files (**Convert to VTK**) and the T-file of a killed job (a frame written at the kill is skipped), rebuilds `.vtk.series` and `_Results.csv`; remote SCP jobs are converted on the server and copied back |
| **Extract Strains** | pvbatch: max principal total strain at the membrane, upper and lower surface of the last frame of each `.vtk.series` in the folder, `principal_strains_summary.csv` |
| **PV Images** | pvbatch: PNG renders of the last frame and the frame of the peak strain |
| **Open in ParaView** | Writes `<job>_pv.json` and `<job>_pv.py` and starts `paraview --script=<job>_pv.py` |
| **Install PV Macro** | `Eps1_View.py` in `%APPDATA%\ParaView\Macros` |
| **Suggest Min dt** | As in Build, from the `_0000.out` of the job |
| **Load CSV…** | Adds the curves of a results CSV (`<job>_Results.csv` or `<job>T01.csv`) of any folder (file dialog) |
| **Save PNG…** | The plot as a PNG file (file dialog) |
| **Kinetic**, **Internal**, **KE+IE** | Curves of the results CSV (time in s, energy in mJ); the dashed line is the time of the frame shown |
| **Overlay all**, **Curve** | All loaded curves in one plot; otherwise the curve chosen in **Curve** (the selected job when its CSV is read) |
| Plot | Drag a rectangle: zoom; double-click: full range |
| **starter .out**, **engine .out**, **settings report**, **open folder** | The solver listings and the settings report (last 400 kB) in a browser window; the build folder on this PC |

The table below the curves is `principal_strains_summary.csv` of the folder.

3D view (toolbar):

| Control | Function |
|---|---|
| **Show** | **Model** (ShinyCAD geometry, roles in colour, supports blue), **Mesh** (the mesh of **Write .inp** or **Show mesh**), **Results** (frame of the selected job) |
| **Field** | Point and cell arrays of the frame: scalars; vectors as magnitude and x, y, z; tensors as max principal and min principal value (strain tensors: max principal total strain) and the components xx, yy, zz, xy, yz, xz. Without a Displacement vector in the frames: **Displacement** magnitude and x, y, z from the node coordinates minus those of the first frame |
| ▶, frame slider | Plays the frames; the slider selects a frame |
| **Scale** | Deformation scale (empty: 1, the true deformation) |
| **Range** min, max | Colour range (empty: the range of the frame, of the drawn elements) |
| **Hide eroded** | Elements with EROSION_STATUS < 0.5 are not drawn; elements of rigid bodies of the deck (/RBODY groups) are drawn |
| **Undeformed** | Element edges of the first frame |
| Parts (Results panel) | One row per part of the frames (PART_ID; name from the animation file, else from the /PART cards of `<job>_0000.rad`): **Show** (the part is drawn; the colour range is taken from the parts shown), max \|d\|, dx, dy, dz (the component of largest magnitude, signed) and the minimum and maximum of the **Field** of the frame. **Show all**; **Show selected**: the parts named after the bodies and sections selected in **Show** **Model** (ELSET `B_<name>` of the model .inp) |
| **Edges**, **Axes**, **Iso**, **Front**, **Top**, **Right**, **Fit** | As in the Analysis tab |
| **Select** | Selection toolbar of the view: **Faces**, **Edges**, **Bodies**, **Ref. points**, **Box**, **Clear**, **Done**, **Cancel**, as in the Analysis tab ([section 12.2.1](12-analysis.md#1221-selection)). Targets: **Support**, **Pick** of a support, **Add faces** of a distributed mass, **Add faces** and **Add edges** of a reference point, the node sets and the sections. **Suppress**: the selected bodies and sections to role **off** |
| **Shell thickness** | **Show** **Mesh**: shell elements drawn with the thickness and OFFSET of the *SHELL SECTION of their *ELEMENT ELSET in the .inp (ShinyCAD geometry: **t** and **Position** of the shell row or section). Not in **Results** (the animation files hold no thickness) |
| **Supports** | **Show** **Mesh** (ShinyCAD geometry): the supports at the mesh nodes, as in the Analysis tab: a cone along each held translation, a cube at nodes with held rotations |

Frames: the animation files `<job>A001`, `<job>A002`, ... of the build folder, read directly (binary, OpenRadioss format FASTMAGI10), with the time of the file header; without A-files, `<job>.vtk.series` or `<job>_<n>.vtk`.
Field names are those of anim_to_vtk: nodal scalars and vectors by their name (spaces as `_`), element values `1DELEM_`, `2DELEM_` and `3DELEM_` plus the name, `PART_ID`, `EROSION_STATUS` (1 active, 0 eroded).
Shell tensors (xx, yy, xy) are completed with zeros to 3 x 3. Elements of another dimension than the field (for example solids with a `2DELEM_` field) are drawn grey.
Elements with 3 different nodes are triangles, 8-node elements with 4 different nodes tetrahedra. SPH particles are not read.
Cell fields are drawn flat per element, point fields interpolated; the colour scale has 12 bands.
The exterior faces of solid elements and all shell elements are drawn.

## 13.8 Tools

Companion scripts of ORC\*\*3 and the model-generation scripts of the SCRIPTS_AND_MACROS folder, started with the Python of ShinyCAD from the folder of the script.
**Deck generator (GUI)** and **Deck mesh (CLI)** import `deck_stepgen.py`, which builds the STEP with cadquery. When cadquery is not installed in the Python of ShinyCAD, they start with the build123d version of ShinyCAD (`drawgen/explicit/deck_stepgen.py`, same functions) in its place; the console line of the launch says so.

| Group | Tools |
|---|---|
| Workspace companions (`drawgen/explicit/`) | Inertia builder (GUI), Inertia calc (CLI), inp2rad converter (CLI), 2nd-order -> linear (CLI), Job audit (CLI), Rad preview (GUI), Gauge rings (CLI), Relative displacement (CLI) |
| Model generation (repo scripts, three folders above `drawgen/explicit/`) | Deck builder, Deck generator (GUI), Deck mesh, Deck element sets, Stiffened panel, Stiffened panel conformal, Deck stripper (GUI/CLI), UNV -> INP converter |
| My scripts | Scripts added by the user |

| Control | Function |
|---|---|
| Box (**File:**, **Folder:**, **Options:** …) | Arguments of the next launch (quote paths with spaces); remembered in `config.local.json` > `explicit` > `tool_args`. Empty box: the grey note states the substitute (**Source .inp** for inp2rad and 2nd-order -> linear, **Output Dir** else Project Dir for Job audit). **(nothing to set)**: the script takes no arguments |
| **Launch** | GUI tools: detached process. Console tools: own console window on Windows (`cmd /k`, open after the run); elsewhere the output is written to the console. Deck stripper: window with an empty box, console with arguments. `RIVET_CAL_CONFIG` names `explicit/workspace_config.json` with the current settings (Gauge rings and Relative displacement without arguments) |
| **?** | Description of the tool; at the top: description of the box |
| **×** | Built-in tool: hidden; user script: removed from the list (confirmation; the file is kept) |
| **Show hidden**, **Restore** | Lists the hidden built-in tools; **Restore** shows one again |
| **Edit tools.json**, **Reload list** | Opens `tools.json` (next to `config.json`; created with a `_readme` block when missing); **Reload list** reads it again. Entries without `script` or `title` are skipped and named in red |
| **Add a script**: **Script**, …, **Name**, **Type**, **Add** | Adds a Python script (**cli**, **gui** or **auto**) under My scripts in `tools.json` |

On the first start without `tools.json` the ORC\*\*3 `%APPDATA%\ORC3\tools.json` is copied; the box texts are read once from the ORC\*\*3 configuration.
A row whose script is missing shows FILE NOT FOUND and the path.

## 13.9 Console

The console lists the messages of the build, the solver output and the post-processing.
**find** filters the lines, **Clear** empties the console, **Follow** scrolls to the newest line.
The strip at the bottom of the 3D view shows the running build, runs and post-processing commands and the newest console line.
The server keeps the last 20000 lines; the page shows the last 6000.

[Contents](../README.md) · [← 12. Analysis](12-analysis.md) · [14. Tests →](14-tests.md)
