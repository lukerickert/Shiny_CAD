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
| `step/<Name>_deck.step`, `step/<Name>_deck_model.json`, `work/<Name>_deck.part.json` | Deck generator **Generate STEP**: STEP of the deck structure, deck model (input of `deck_elsets.py` of DECK_GENERATOR), part with one **Import surface** feature per component |
| `explicit/<Name>/runs/<date>_r<NNN>_<description>/` | Run folder: `run.json` (description, notes, archived model, settings of every build), `model/` (copy of the source .inp, and of the .pmx with the same name next to it), `console.log` (the console lines while the run is selected), one build folder per build |
| `<run>/<job>_b<NN>/` | Build folder: `<job>_bNN_0000.rad` (starter), `<job>_bNN_0001.rad` (engine), `<job>_bNN_settings.txt` (settings report, 96 columns), solver listings `_0000.out` and `_0001.out`, animation files `<job>_bNNA001...`, `<job>_bNN_001.vtk ...` and `<job>_bNN.vtk.series`, time history `<job>_bNNT01`, `<job>_bNN_Results.csv`, `<job>_bNN_KE.png`, ParaView session `<job>_bNN_pv.py` and `<job>_bNN_pv.json`, `principal_strains_summary.csv` |
| `explicit/run_history.json` | Finished jobs of the project (200 newest) |

The job name is the name of the source .inp with the build number: `<inp name>_b01`, `_b02`, ... (the highest number in the output folder plus one).
Renaming the document in the **Project** tab renames `explicit/<Name>/` and the model .inp.
Without an open project the folders are `explicit/` and the document folder of the program.

## 13.3 Model

| Control | Function |
|---|---|
| **Source** | **ShinyCAD geometry (assembly or part)**: the saved assembly or part chosen in **Geometry** (toolbar). **Deck generator (stiffened panel, shells)**: [section 13.3.1](#1331-deck-generator). **External .inp (PrePoMax)**: the meshed .inp in the **.inp** field |
| **.inp**, **…**, **Show mesh** | External .inp: path; **Show mesh** draws the nodes and elements (*NODE, *ELEMENT; solids C3D4, C3D10, C3D8, C3D8R, C3D8I, C3D20, C3D6, C3D15; shells S3, S4, S4R, S8R, R3D3, R3D4, M3D3, M3D4) with one colour per ELSET |
| **Materials** | **Name**, **Library** (an entry of the ORC\*\*3 material library, or **(elastic: E, nu, rho)**), **E (MPa)**, **nu**, **rho (kg/m^3)**; **Add material**, × deletes; **Default**: material of the bodies without one |
| **Bodies** | One row per component: **Role** **deformable**, **rigid (impactor)** or **off**; **Material**; **Size (mm)** element size of the body (empty: **Element size**); **Mesh** strategy of the body |
| **Mesh** | **Element size (mm)** (empty: bounding box diagonal / 20), **Minimum size (mm)** (empty: element size / 5), **Strategy** (**Tetrahedra (free)**, **Hexahedra, structured (block cells)**, **Hexahedra by subdivision**; [section 12.3.1](12-analysis.md#1231-mesh-settings)), **Tetrahedra** C3D4 or C3D10, **Hexahedra** C3D8R or C3D8, **Elements per 360 deg** (empty: 12), **Bonded: touching deformable bodies share nodes** |
| **Supports** | **Support** (toolbar), then a click on a face of a deformable body. **ux**, **uy**, **uz**: the held displacements of the face nodes; **Pick** picks the face again; × deletes |
| **Write .inp** (toolbar) | Meshes the bodies (gmsh), writes `explicit/<Name>/model/<Name>.inp` and draws the mesh (**Show** **Mesh**). The table gives the nodes, elements, ELSET, material and reference node of each body |

The .inp of the ShinyCAD geometry holds:

| Keyword | Content |
|---|---|
| `*NODE` | Mesh nodes; one reference node per rigid body at the centre of mass of the body (the last node numbers) |
| `*ELEMENT, TYPE=<type>, ELSET=B_<BODY>` | Elements of each body (body name in upper case) |
| `*NSET, NSET=RB_<BODY>` | Nodes of a rigid body |
| `*NSET, NSET=SUP_<n>_<NAME>` | Face nodes of a support |
| `*MATERIAL, NAME=<NAME>` | `*ELASTIC` and `*DENSITY`; with a library entry the E, nu and density of the entry |
| `*SOLID SECTION, ELSET=B_<BODY>, MATERIAL=<NAME>` | Section of each body |
| `*RIGID BODY, NSET=RB_<BODY>, REF NODE=<n>` | Rigid bodies; inp2rad writes an /RBODY with the reference node as main node (ICoG 3) |
| `*BOUNDARY` | `SUP_<n>_<NAME>, <dof>, <dof>` for each held displacement |

Rigid bodies are meshed apart from the deformable bodies and share no nodes with them.
Each material with a library entry is added to **Library materials** of the build with its name as **Name in model** (rows marked **Model**).

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
| Plan, section | Plan of the panel (top flanges shaded, beam lines coloured by depth, selected beams labelled; the hover text gives name, position and h) and the section of the selected beam (the first beam when none or several are selected) |
| **Sections** | Element set, parameter name and thickness of each section. Beams with one name form one element set; both flanges of a beam share the parameter `<NAME>_FLANGE_t` |
| **Max element size [mm]**, **Min divisions per interval** | Structured mesh: every interval between break coordinates (panel edges, beam lines, flange edges, web depths) gets ceil(length / max element size) divisions, at least the minimum; the plates are cut at the break lines and meshed transfinite, conformal across the junctions |
| **Shell type**, **Triangles** | S4 / S3 or S4R / S3R; **Triangles**: no recombination to quadrangles |
| **Material** | Material of all sections (**(default)**: the **Default** material of the **Materials** table) |
| **Edge supports** | **x = 0**, **x = X distance**, **y = 0**, **y = Y distance**: **free**, **pinned (ux uy uz)** or **clamped (ux uy uz rx ry rz)** for the nodes on the edge plane (deck and webs) |
| **Write .inp** (toolbar) | Meshes the deck (gmsh, in a separate process), writes `explicit/<Name>/model/<Name>.inp` and `<Name>_Parameters.pmp` and draws the mesh. The table gives the elements, z range, thickness, PrePoMax section number and parameter of each element set; below: longest element edge, aspect ratio, element edges by the number of plates sharing them (1 free edge, 2 inside a plate, 3 T junction, 4 cruciform) |
| **Generate STEP** | Writes `<Name>_deck.step` (assembly DECK_STRUCTURE, one named and coloured component of sewn shells per element set) and `<Name>_deck_model.json` to the step folder of the project, and the part `<Name>_deck` with one **Import surface** feature per component. A second **Generate STEP** replaces the **Import surface** features of that STEP and keeps the other features of the part. **Open part** opens it in the **Part** tab |

Two beams of one axis within 0.5 mm of each other are refused when typed and reported as an error by **Write .inp** and **Generate STEP**.
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
| Run list | **(no run: decks next to the .inp)** and the run folders, newest first, with the number of builds and decks. A click selects the run: **Output Dir** of the build, and the newest deck becomes **Target .rad**. **Decks** lists the decks of the selected run; a click sets **Target .rad** |
| **Open** | Opens the run folder on this PC |
| **Clean…** | Lists the regenerable solver output of the run and its build folders (A-files, T-files, `.vtk`, `.vtk.series`, `.rst`, `_extract_principal_strain.py`) with the number of files per folder and the size in MB, and deletes them after confirmation. Decks, `model/`, `run.json`, CSV and PNG files are kept |
| **Settings** | Restores the Build and Solve settings of the last build of the run from `run.json`; paths are kept |

## 13.5 Build

**Build** (toolbar) or **Build deck** builds the decks with the settings of the Build panel.

| Field | Function |
|---|---|
| **Analysis** | **Impact / drop test**, **Quasi-static (load-hold-unload)**, **Advanced (all features)**; selects the fields shown (table below) |
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
| **Target RP** | /RBODY name or id driven by **Driver** (empty: the deck must have one /RBODY) |
| **Rigidify part(s)**, **List Parts** | PID or part name substring (comma between several): each part becomes an /RBODY over its nodes with the main node at its centre of gravity. **List Parts** writes the PID and name of each /PART of the newest deck to the console |
| **Concentrated mass JSON** | Mass and inertia of the impactor (inertia_builder / inertia_calc file) merged into the single /RBODY of the deck (ICoG 3), or a free-node /RBODY when the deck has none |
| **Tie Mode**, **Tie dist [mm]** / **Fallback dist [mm]** | **Auto (*TIE from INP)**: /INTER/TYPE2 from the *TIE of the .inp (position tolerance, else **Fallback dist**). **Scoped pairs (box below)**: one line `secondary > master : distance` per tie (PID or part name substring). **Single global tie**: one TYPE2 over all parts within **Tie dist**. **None** |
| **Heal Normals** | Shell normals made consistent in each connected area |
| **Disp -> Velocity** | /IMPDISP of the .inp written as /IMPVEL with constant velocity over Tstop |
| **Purge older builds** | Deletes the older build folders of the job after a successful build |
| **Downgrade 2nd-order → linear** | Second-order elements of the .inp converted to first order (`inp_to_linear.py`) before inp2rad |

| Analysis | Hidden fields |
|---|---|
| **Impact / drop test** | **Target RP**, advanced options; **Driver** offers **Explicit** and **None** |
| **Quasi-static (load-hold-unload)** | Rigid floor, **Rigidify part(s)**, **Concentrated mass JSON**, advanced options; **Driver** offers the load-hold-unload drivers and **None** |
| **Advanced (all features)** | none |

Hidden fields keep their values and act at build time; the Build panel names a hidden field that is active.

The build reads the .inp, removes the velocity *BOUNDARY, runs inp2rad in a temporary folder and adds to the starter deck: the library materials and their /FUNCT curves, the failure cards, Istrain = 1 in /PROP/SHELL, the rigidified parts and the concentrated mass, the groups /GRNOD/PART/9999998 (all parts) and /SURF/PART/EXT/9999999, gravity, contact, ties, rigid floor and the driver.
The engine deck holds /RUN, /DT/NODA/CST, /DT/INTER/DEL, /DT/SHELL/DEL and /DT/SH3N/DEL when elements are deleted, /ANIM/DT and the animation outputs (velocity, displacement, contact forces, von Mises, plastic strain, energy, shell strain tensors at the membrane, upper and lower surface, brick strain tensor), /TH/TITLE and /TFILE.
The build stops with BUILD HALTED and the cause for a CAD file instead of a mesh, element types inp2rad does not convert, elements without a section (/SHELL/0) and two different /INIVEL on one node.

Reserved ids: 9999997 gravity, 9999998 all-node group and global tie, 9999999 surface and general contact, 999xxxx ties and driver, 9970xxx rigidify, 997xxxx concentrated mass, 9000 + 10 x material id library curves.

## 13.6 Solve

| Control | Function |
|---|---|
| **Target .rad**, decks… | Starter deck `<job>_0000.rad` to run; decks… lists the decks of the selected run |
| **Env** | **Local** (this PC) or **Remote (Linux)** |
| **Threads** | Engine threads (`-nt`) |
| **Stream remote output** | Follows the remote job to the end (status, copy-back, post-processing); required for SCP transfer |
| **Plot KE**, **Extract Strains**, **PV Images** | Post-processing after a run: KE curve and PNG; principal strain summary (pvbatch); PNG renders (pvbatch) |
| **OpenCourant exec folder** | Local executables ([section 13.1](#131-executables-and-settings-of-this-pc)) |
| **Server (user@host)**, **SSH Port**, **Env script**, **Exec dir**, **Scratch dir**, **Share map** | Remote run: `ssh`/`scp` target; script sourced before `tsp`; folder of the Linux executables; work folder for SCP transfer; `WIN => LINUX` path pairs separated by `;` (a run folder on a mapped share runs in place on the server, other folders are copied to **Scratch dir** and the results copied back) |
| **pvbatch**, **paraview** | ParaView executables (empty: searched) |
| **Run Simulation** (toolbar **Run**) | Runs **Target .rad**, or the queue when **Target .rad** is empty or in the queue |
| **Run Starter Only** (toolbar **Starter**) | Starter only; the added-mass table of the `_0000.out` is offered as **Min dt** (confirmation) |
| **Kill** | Local: stops the starter and engine. Remote: kills the running job and empties the tsp queue |
| **Shutdown Server** | `sudo shutdown -h now` on the server (confirmation) |
| Queue: **Add Current**, **Remove Selected**, **Clear List** | Decks run one after the other; the queue is kept until the server stops |
| Server: **Show Queue**, **Kill+Flush Server** | Running solver and tsp queue of the server in the status board; kill and flush (confirmation) |

Local run: starter, engine, conversion of the A-files to `<job>_<n>.vtk` and `<job>.vtk.series`, `th_to_csv` to `<job>_Results.csv`, KE curve, ParaView session files, strain extraction and PNG renders as checked.
Remote run: the same pipeline as one `tsp` job on the server.
Local and remote runs are independent; one batch per environment at a time.

The status board has one row per job: **Status** (Queued, Starter, Starting engine, Running, Post-processing, Done, Starter done, Failed, Killed, Skipped), **Progress** and **T / Tstop** from the engine cycle lines, **ETA**, **ERR** (energy error) and **DM/M** (added mass ratio).
Rows are yellow at |ERR| >= 5 % or DM/M >= 0.02, red at |ERR| >= 15 % or DM/M >= 0.10.
A job fails on `** RUN KILLED`, `MESSAGE ID`, `ERROR TERMINATION`, `** ERROR`, `forrtl: severe` or `Segmentation fault` in the solver output, and on a non-zero exit code of a local run; the note gives the message.
A click on a row selects it for **Remove Selected** and loads its results.
**Run history** lists the finished jobs with date, status, environment, ERR, DM/M and wall time; a click loads the results.

## 13.7 Results

| Control | Function |
|---|---|
| **Job**, **↻** | Job of the selected run or the status board; **↻** reads the frames and curves again |
| **Plot KE** | Rebuilds the KE curve and `<job>_KE.png` from the results CSV |
| **Salvage Results** | Converts the A-files and the T-file of a killed job (a frame written at the kill is skipped), rebuilds `.vtk.series` and `_Results.csv`; remote SCP jobs are converted on the server and copied back |
| **Extract Strains** | pvbatch: max principal total strain at the membrane, upper and lower surface of the last frame of each `.vtk.series` in the folder, `principal_strains_summary.csv` |
| **PV Images** | pvbatch: PNG renders of the last frame and the frame of the peak strain |
| **Open in ParaView** | Writes `<job>_pv.json` and `<job>_pv.py` and starts `paraview --script=<job>_pv.py` |
| **Install PV Macro** | `Eps1_View.py` in `%APPDATA%\ParaView\Macros` |
| **Suggest Min dt** | As in Build, from the `_0000.out` of the job |
| **Kinetic**, **Internal**, **KE+IE** | Curves of the results CSV (time in s, energy in mJ); the dashed line is the time of the frame shown |
| **starter .out**, **engine .out**, **settings report**, **open folder** | The solver listings and the settings report (last 400 kB) in a browser window; the build folder on this PC |

The table below the curves is `principal_strains_summary.csv` of the folder.

3D view (toolbar):

| Control | Function |
|---|---|
| **Show** | **Model** (ShinyCAD geometry, roles in colour, supports blue), **Mesh** (the mesh of **Write .inp** or **Show mesh**), **Results** (frame of the selected job) |
| **Field** | Point and cell arrays of the frame: scalars; vectors as magnitude and x, y, z; tensors as max principal and min principal value (strain tensors: max principal total strain) |
| ▶, frame slider | Plays the frames; the slider selects a frame |
| **Scale** | Deformation scale (empty: 1, the true deformation) |
| **Range** min, max | Colour range (empty: the range of the frame, of the drawn elements) |
| **Hide eroded** | Elements with EROSION_STATUS < 0.5 are not drawn; elements of rigid bodies of the deck (/RBODY groups) are drawn |
| **Undeformed** | Element edges of the first frame |
| **Edges**, **Axes**, **Iso**, **Front**, **Top**, **Right**, **Fit** | As in the Analysis tab |

Cell fields are drawn flat per element, point fields interpolated; the colour scale has 12 bands.
The exterior faces of solid elements and all shell elements are drawn.

## 13.8 Console

The console lists the messages of the build, the solver output and the post-processing.
**find** filters the lines, **Clear** empties the console, **Follow** scrolls to the newest line.
The strip at the bottom of the 3D view shows the running build, runs and post-processing commands and the newest console line.
The server keeps the last 20000 lines; the page shows the last 6000.

[Contents](../README.md) · [← 12. Analysis](12-analysis.md) · [14. Tests →](14-tests.md)
