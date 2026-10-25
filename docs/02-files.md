[Contents](../README.md) · [← 1. Installation (Windows)](01-installation.md) · [3. Use →](03-use.md)

# 2. Files

| File | Function |
|---|---|
| `start.bat` | Creates the environment on first start and starts the server |
| `run.py` | Starts the server and the worker processes |
| `config.json` | Defaults: sheet, scale, views, line widths, sheet sizes, frame, title block layout and field values, options |
| `config.local.json` | Settings of this PC: projects folder, open project, Explicit settings, browser command, CalculiX path. Created at the first change; settings of this PC found in `config.json` (older versions) are moved here at start. Not in the repository |
| `publish.bat` | Publishes the program folder to GitHub ([section 2.2](#22-publishing-to-github)) |
| `requirements.txt` | Python packages |
| `logo.png` | Logo of the title block |
| `solvers/` | Solver packages: PrePoMax (CalculiX) and OpenCourant, unpacked here ([section 1.1](01-installation.md#11-solvers)); `solvers/README.txt` |
| `INSTALL.txt` | Installation, troubleshooting and first use, short form |
| `README.md` | Overview, quick start and the contents of the manual |
| `docs/` | Manual, one page per section (`01-installation.md` to `15-limitations.md`) |
| `.gitattributes`, `.gitignore` | Git: line endings normalised (LF in the repository, CRLF for the `.bat` files); not tracked: `__pycache__`, the contents of `solvers/` except `README.txt`, `config.local.json`, the document and output folders of the program folder (`parts/`, `sketches/`, `assemblies/`, `annotations/`, `stacks/`, `analysis/`, `explicit/`, `_export/`) and STEP and .inp files in the program folder |
| `drawgen/web.py` | Web server |
| `drawgen/pool.py` | Worker processes for the drawing views and the assembly builds |
| `drawgen/model.py` | STEP reading: solids and their names |
| `drawgen/project.py` | Hidden-line removal, section cut, hatching |
| `drawgen/drawing.py` | Views, layout, sheet and scale selection, title block values |
| `drawgen/titleblock.py` | Frame and title block |
| `drawgen/render.py` | SVG, PDF and DXF output |
| `drawgen/fcstd.py` | FCStd output |
| `drawgen/annotate.py` | Dimensions and notes |
| `drawgen/fits.py` | ISO 286 limits |
| `drawgen/units.py` | Options (drawing units, keyboard shortcuts) and the number formats of the drawing units ([section 3.1](03-use.md#31-options)) |
| `drawgen/measure.py` | Measurement between faces, planes and axes ([section 10.11](10-part.md#1011-measure)) |
| `drawgen/fasteners.py` | Thread and hole reference tables ([section 6.1](06-drawings.md#61-threads-and-holes-reference)) |
| `drawgen/roughness.py` | Achievable roughness Ra by manufacturing process ([section 6.1](06-drawings.md#61-threads-and-holes-reference)) |
| `drawgen/sketch.py` | Sketch DXF import, DXF and PDF export |
| `drawgen/stlimport.py` | STL import: mesh reading, flat faces, fitted cylinders, cones and spheres, solid ([section 10.12](10-part.md#1012-stl-import)) |
| `drawgen/sketchimage.py` | Reference images of sketches: import, lens correction, perspective correction, corrected image file ([section 9.5](09-sketch.md#95-images)) |
| `drawgen/part.py` | Part features, 3D view mesh, STEP export |
| `drawgen/surfaces.py` | Surface bodies of the Part tab |
| `drawgen/assembly.py` | Assembly placement, mates, mass, interference, view cache, STEP export |
| `drawgen/fea.py` | FEA mesh export (gmsh) |
| `drawgen/analysis.py` | Analysis model, CalculiX input file, result reading, report ([section 12](12-analysis.md#12-analysis)) |
| `drawgen/explicit/` | Explicit tab ([section 13](13-explicit.md#13-explicit)): `routes.py` server requests, `host.py` settings, console and status board, `build.py` deck build, `materials.py` material, failure and time step cards, `runs.py` run folders and settings report, `solve.py` local and remote runs, `post.py` post-processing, `constants.py` material library and modes, `modes.py` analysis types, `scripts.py` ParaView scripts, `model_inp.py` .inp of the ShinyCAD geometry, `meshview.py` mesh view data and .inp and VTK readers, `results.py` frames and fields, `inp2rad.py` and `inp2rad_run.py` .inp to .rad converter, `inp_to_linear.py` second-order to first-order elements, `inertia_calc.py` concentrated mass from primitives, `deck.py` deck generator source (check, model .inp, STEP and part), `deck_mesh.py` and `deck_stepgen.py` DECK_GENERATOR mesh and geometry |
| `drawgen/femesh.py` | Analysis mesh of the bodies and plates (gmsh) |
| `drawgen/projects.py` | Projects: folders, documents, versions, states ([section 2.1](#21-projects)) |
| `drawgen/dialogs.py` | Windows file and folder dialogs (tkinter) |
| `drawgen/static/index.html`, `style.css` | Web interface |
| `drawgen/static/app.js` | Models, settings, preview, tabs, File menus of the Part and Assembly tabs |
| `drawgen/static/annotate.js` | Drawings tab: dimensions, notes, balloons, detail views |
| `drawgen/static/project.js` | Project tab |
| `drawgen/static/sketch.js` | Sketch editor and constraint solver: **Sketches** pane, sketches on drawings, feature sketches of the Part tab |
| `drawgen/static/part.js` | Part tab and 3D view |
| `drawgen/static/assembly.js` | Assembly tab |
| `drawgen/static/analysis.js` | Analysis tab |
| `drawgen/static/explicit.js` | Explicit tab |
| `drawgen/static/reference.js`, `refdiagrams.js` | Thread and hole reference tables and profile diagrams |
| `drawgen/static/icons.js` | Toolbar icons |
| `drawgen/static/navcube.js`, `axes.js` | Navigation cube and coordinate axes of the 3D views |
| `run_tests.bat`, `tests/` | Automatic tests ([section 14](14-tests.md#14-tests)) |
| `drawgen/static/vendor/` | three.js 0.160.0 (MIT licence, `three.LICENSE`) and `TumbleControls.js` for the 3D views |
| `parts/`, `sketches/`, `assemblies/`, `annotations/` | Documents when no project is open ([section 2.1](#21-projects)) |
| `%LOCALAPPDATA%\drawgen\venv` | Python environment |
| `%LOCALAPPDATA%\drawgen\viewcache` | View cache of the assembly sources ([section 11](11-assembly.md#11-assembly)); can be deleted |

## 2.1 Projects

The **Project** tab is the first tab. A project is a folder under the projects folder (**Projects folder**, set once; written to `config.local.json` > `projects_root`):

| Folder | Content |
|---|---|
| `project.json` | Name, description, creation date, document versions and notes |
| `work/` | The working documents: `<name>.part.json`, `<name>.sketch.json`, `<name>.asm.json`, `<name>.fea.json`, `<name>.exp.json` |
| `work/annotations/` | Dimensions, notes and view layouts of the drawings |
| `work/images/` | Reference images of the sketches and their corrected files `<image>_c<key>.png` / `.jpg` ([section 9.5](09-sketch.md#95-images)) |
| `drawings/` | Exported PDF, DXF, SVG and FCStd files (the default output folder of **Export** when the folder field is empty) |
| `step/` | Exported STEP and mesh files (default folder of **Export STEP** and **Export mesh**) |
| `step_import/` | Local copies of imported STEP files. **Open** in Models and the **Import STEP** feature of a saved part use the copy |
| `analysis/<name>/` | Solver files and report of an analysis ([section 12](12-analysis.md#12-analysis)) |
| `explicit/<name>/` | Model .inp and run folders of an explicit analysis ([section 13](13-explicit.md#13-explicit)) |
| `versions/` | Document versions `<name>.part.v<N>.json` with a `.meta.json` note |
| `states/` | Saved project states |
| `trash/` | Deleted documents |

| Control | Function |
|---|---|
| **Projects folder**, **…**, **Set** | The folder that holds the projects |
| **Project**, **Open** | Opens a project. The saved lists of the **Sketches** pane, the Part and Assembly tabs and **Models** follow the open project; `config.local.json` > `current_project` keeps it for the next start |
| **New…** | Creates and opens a project (name, description) |
| **Take over existing files…** | Shown while the projects folder has no project: creates a project and moves the parts, sketches, assemblies, stacks and annotations of the program folder into it |
| **Rename**, **Description**, **Open folder** | Of the open project |
| **Documents** | All documents of the project: name, type, version, note, date, size, **Uses** (parts of an assembly and the solids of its STEP files, each with the number of components using it as ×N, below the STEP file name; imported STEP files of a part), **Used by** (assemblies using the part, analyses using the part or assembly), **Exports** (files in `drawings/` and `step/` named after the document). **Open** loads the document in its tab; **Rename** (assemblies referencing a renamed part, and analyses referencing a renamed part or assembly, are updated); **Copy** (a part copy gets a new uid and an empty drawing); **Version** stores a numbered snapshot with a note; **Versions…** lists the snapshots with **Restore** (replaces the working file) and **Restore as copy…**; **Move…** moves or copies the document to another project (**Project**, **Move** or **Copy**; its versions, drawing annotations and layouts, sketch images and analysis folders go along; **With the documents it uses**: the parts of an assembly, the part or assembly of an analysis, each moved only when no other document left in the project uses it, else copied; a name that exists in the target project is refused); **×** moves the document to `trash/` |
| **Exports** | The files in `drawings/`, `step/` and `step_import/`, with buttons that open the folders on this PC |
| **Project states** | **Save current state** stores which documents are open in the Part, Assembly and Analysis tabs and the **Sketches** pane, the **Models** list with the checked parts, the drawing settings (sheet, scale, mode, views, density) and the active tab. **Load** restores all of it: parts and assemblies are rebuilt from their saved files, STEP files reopened from their paths |

Without an open project the documents are read from and written to the folders of the program: `parts/`, `sketches/`, `assemblies/` and `annotations/`. File locations in the following sections are given for an open project.

## 2.2 Publishing to GitHub

The program folder is a clone of https://github.com/lukerickert/Shiny_CAD (git remote `origin`). `publish.bat` (double-click) adds all changed, new and deleted files except those of `.gitignore`, lists them, asks for a description (Enter: `Update <date>`), commits, pulls the repository with rebase and pushes; `publish.bat "text"` takes the description from the command line. With no changes it pushes the commits not yet pushed. The window stays open with the result.

| Requirement | |
|---|---|
| Git for Windows | https://git-scm.com/download/win, default options. Without it `publish.bat` stops with the download address |
| GitHub sign-in | At the first push Git Credential Manager opens the browser for the GitHub login; the credential is stored in the Windows credential manager |
| Name and e-mail of the commits | Asked at the first run when git has none; stored for this folder (`git config user.name`, `user.email`) |

When the pull finds a conflict (the same lines changed on GitHub and in the folder), `publish.bat` stops with the git messages.

[Contents](../README.md) · [← 1. Installation (Windows)](01-installation.md) · [3. Use →](03-use.md)
