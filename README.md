# SHINYCAD

Local web application that creates ISO drawings from STEP files.
Each drawing has an ISO 5457 frame, an ISO 7200 title block, first-angle Front / Top / Right views, section A-A through the part centre and an isometric view.
Dimensions, notes and ISO 286 tolerances are added interactively.
Output is PDF, DXF, SVG and FCStd (FreeCAD / AstoCAD document with a TechDraw page).
The **Sketches** pane of the **Drawings** tab creates 2D sketches on a blank sheet and edits DXF files, with geometric constraints and driving dimensions. The same editor sketches on a view or on the sheet of a model drawing.
The **Part** tab creates 3D parts from sketches with extrude, cut and revolve features.
The **Analysis** tab runs linear static analyses of assemblies and parts with CalculiX: solid bodies, plates, beams, rods and preloaded fasteners.
The **Explicit** tab builds and runs OpenRadioss explicit analyses (ORC\*\*3 core) from the ShinyCAD geometry or a PrePoMax .inp, locally or on a Linux server, and shows the results.
AstoCAD is not used at run time. Projection and hidden-line removal use OpenCascade through build123d.

## 1. Installation (Windows)

1. Install Python 3.10 to 3.14 from python.org (64-bit). `py -0` lists the versions known to the py launcher.
2. Extract the zip file (right-click > **Extract All...**) to a folder with a short path, for example `C:\SHINYCAD`, with all files in the same folder.
3. Double-click `start.bat`.

`start.bat` uses the py launcher and selects the newest installed version from 3.14 to 3.10; without the py launcher it uses `python.exe` on PATH (not the Microsoft Store alias in `WindowsApps`) when it is version 3.10 to 3.14.
`start.bat` runs only from the extracted folder: started from inside the zip file, it reports the missing files and stops.
An environment whose Python no longer starts (Python removed or reinstalled) is created again.
The first start creates the environment in `%LOCALAPPDATA%\drawgen\venv` and installs `build123d`, `flask`, `ezdxf`, `reportlab` and `gmsh` (approximately 500 MB, internet connection required).
Later starts use the existing environment. When `requirements.txt` differs from the installed copy, the packages are installed again before the start.
The server runs at `http://localhost:8765` and the browser opens automatically.
Close the command window to stop the server.

| Message or behaviour of `start.bat` | Cause and action |
|---|---|
| Windows protected your PC (SmartScreen) | The zip came from the internet. **More info** > **Run anyway**, or before extracting: right-click the zip > **Properties** > **Unblock** |
| run.py, requirements.txt or drawgen\web.py is missing | Started from inside the zip. Extract the zip (**Extract All...**) and start `start.bat` in the extracted folder |
| Python 3.10 to 3.14 was not found | Install Python 3.14 (64-bit) from python.org with **py launcher** and **Add python.exe to PATH** |
| Package installation failed | No connection to pypi.org (internet, proxy, firewall) on the first start |
| SHINYCAD stopped with an error | The lines above the message give the cause, for example Port 8765 is already in use |

Manual installation:

```
py -3.14 -m venv %LOCALAPPDATA%\drawgen\venv
%LOCALAPPDATA%\drawgen\venv\Scripts\python.exe -m pip install -r requirements.txt
%LOCALAPPDATA%\drawgen\venv\Scripts\python.exe run.py
```

The **Analysis** tab needs the CalculiX solver `ccx` (not installed by `start.bat`): the `ccx_static.exe` of PrePoMax, or a CalculiX build for Windows (section 12.1).
The **Explicit** tab needs OpenRadioss (not installed by `start.bat`), and ParaView for the strain extraction and the renders (section 13.1).

`run.py --port 9000` sets a different port and `run.py --no-browser` does not open the browser.
`run.py --browser "<command>"` opens the program in that browser for this start (section 3.1 **Browser**).
The server listens on 127.0.0.1 only.

## 2. Files

| File | Function |
|---|---|
| `start.bat` | Creates the environment on first start and starts the server |
| `run.py` | Starts the server and the worker processes |
| `config.json` | Defaults: sheet, scale, views, line widths, sheet sizes, frame, title block layout and field values; projects folder and open project |
| `requirements.txt` | Python packages |
| `logo.png` | Logo of the title block |
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
| `drawgen/units.py` | Options (drawing units, keyboard shortcuts) and the number formats of the drawing units (section 3.1) |
| `drawgen/measure.py` | Measurement between faces, planes and axes (section 10.11) |
| `drawgen/fasteners.py` | Thread and hole reference tables (section 6.1) |
| `drawgen/roughness.py` | Achievable roughness Ra by manufacturing process (section 6.1) |
| `drawgen/sketch.py` | Sketch DXF import, DXF and PDF export |
| `drawgen/part.py` | Part features, 3D view mesh, STEP export |
| `drawgen/surfaces.py` | Surface bodies of the Part tab |
| `drawgen/assembly.py` | Assembly placement, mates, mass, interference, view cache, STEP export |
| `drawgen/fea.py` | FEA mesh export (gmsh) |
| `drawgen/analysis.py` | Analysis model, CalculiX input file, result reading, report (section 12) |
| `drawgen/explicit/` | Explicit tab (section 13): `routes.py` server requests, `host.py` settings, console and status board, `build.py` deck build, `materials.py` material, failure and time step cards, `runs.py` run folders and settings report, `solve.py` local and remote runs, `post.py` post-processing, `constants.py` material library and modes, `modes.py` analysis types, `scripts.py` ParaView scripts, `model_inp.py` .inp of the ShinyCAD geometry, `meshview.py` mesh view data and .inp and VTK readers, `results.py` frames and fields, `inp2rad.py` and `inp2rad_run.py` .inp to .rad converter, `inp_to_linear.py` second-order to first-order elements, `inertia_calc.py` concentrated mass from primitives, `deck.py` deck generator source (check, model .inp, STEP and part), `deck_mesh.py` and `deck_stepgen.py` DECK_GENERATOR mesh and geometry |
| `drawgen/femesh.py` | Analysis mesh of the bodies and plates (gmsh) |
| `drawgen/projects.py` | Projects: folders, documents, versions, states (section 2.1) |
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
| `run_tests.bat`, `tests/` | Automatic tests (section 14) |
| `drawgen/static/vendor/` | three.js 0.160.0 (MIT licence, `three.LICENSE`) and `TumbleControls.js` for the 3D views |
| `parts/`, `sketches/`, `assemblies/`, `annotations/` | Documents when no project is open (section 2.1) |
| `%LOCALAPPDATA%\drawgen\venv` | Python environment |
| `%LOCALAPPDATA%\drawgen\viewcache` | View cache of the assembly sources (section 11); can be deleted |

### 2.1 Projects

The **Project** tab is the first tab. A project is a folder under the projects folder (**Projects folder**, set once; written to `config.json` > `projects_root`):

| Folder | Content |
|---|---|
| `project.json` | Name, description, creation date, document versions and notes |
| `work/` | The working documents: `<name>.part.json`, `<name>.sketch.json`, `<name>.asm.json`, `<name>.fea.json`, `<name>.exp.json` |
| `work/annotations/` | Dimensions, notes and view layouts of the drawings |
| `drawings/` | Exported PDF, DXF, SVG and FCStd files (the default output folder of **Export** when the folder field is empty) |
| `step/` | Exported STEP and mesh files (default folder of **Export STEP** and **Export mesh**) |
| `step_import/` | Local copies of imported STEP files. **Open** in Models and the **Import STEP** feature of a saved part use the copy |
| `analysis/<name>/` | Solver files and report of an analysis (section 12) |
| `explicit/<name>/` | Model .inp and run folders of an explicit analysis (section 13) |
| `versions/` | Document versions `<name>.part.v<N>.json` with a `.meta.json` note |
| `states/` | Saved project states |
| `trash/` | Deleted documents |

| Control | Function |
|---|---|
| **Projects folder**, **…**, **Set** | The folder that holds the projects |
| **Project**, **Open** | Opens a project. The saved lists of the **Sketches** pane, the Part and Assembly tabs and **Models** follow the open project; `config.json` > `current_project` keeps it for the next start |
| **New…** | Creates and opens a project (name, description) |
| **Take over existing files…** | Shown while the projects folder has no project: creates a project and moves the parts, sketches, assemblies, stacks and annotations of the program folder into it |
| **Rename**, **Description**, **Open folder** | Of the open project |
| **Documents** | All documents of the project: name, type, version, note, date, size, **Uses** (parts of an assembly and the solids of its STEP files, each with the number of components using it as ×N, below the STEP file name; imported STEP files of a part), **Used by** (assemblies using the part, analyses using the part or assembly), **Exports** (files in `drawings/` and `step/` named after the document). **Open** loads the document in its tab; **Rename** (assemblies referencing a renamed part, and analyses referencing a renamed part or assembly, are updated); **Copy** (a part copy gets a new uid and an empty drawing); **Version** stores a numbered snapshot with a note; **Versions…** lists the snapshots with **Restore** (replaces the working file) and **Restore as copy…**; **×** moves the document to `trash/` |
| **Exports** | The files in `drawings/`, `step/` and `step_import/`, with buttons that open the folders on this PC |
| **Project states** | **Save current state** stores which documents are open in the Part, Assembly and Analysis tabs and the **Sketches** pane, the **Models** list with the checked parts, the drawing settings (sheet, scale, mode, views, density) and the active tab. **Load** restores all of it: parts and assemblies are rebuilt from their saved files, STEP files reopened from their paths |

Without an open project the documents are read from and written to the folders of the program: `parts/`, `sketches/`, `assemblies/` and `annotations/`. File locations in the following sections are given for an open project.

## 3. Use

1. Drop STEP files on **Models**, or enter a file or folder path in the path field and press **Open**. Each solid in a STEP file is listed as a part, named from the STEP labels. The **↻** button of an entry reloads the file from its path (or rebuilds a part or assembly made in the program) and redraws.
2. Select the parts.
3. Set **Sheet size**, **Scale**, **Mode**, views and title block values.
4. Press **Preview**. The drawings open in the **Drawings** tab, one at a time, selected in the drawing list. With **Auto** checked, the preview is computed again after every change to the parts, sheet, scale, mode, views, density, title block fields, line widths or title block (0.4 s after the change). The setting is kept in the browser.
5. Press **Export**.

The left panel (**Models**, **Sheet**, **Views**, **Title block**) is shown on the **Drawings** tab only.

| Control | Function |
|---|---|
| **Sheet size** | A4 (portrait), A3 to A0 (landscape), or **Auto**. Default A3 |
| **Scale** | **Auto** or an ISO 5455 scale. **Auto** uses the largest scale that fits the sheet |
| **Mode** | **One drawing per part** or **One drawing per file** (all selected parts of a file on one drawing) |
| **Section A-A**, **Plane normal**, **Offset**, **Reverse** | Section plane normal to X, Y or Z, offset in mm from the bounding box centre, viewing direction reversed |
| **Hidden lines** | Hidden lines in the Front, Top and Right views |
| **Tangent edges** | Edges between tangent faces |
| **Isometric scale factor** | Isometric view scale relative to the drawing scale. A value other than 1 adds the isometric scale below the view |
| **Density (kg/m^3)** | Mass in the title block is volume x density when > 0 |
| Title block fields | Values for this run. **Guide** next to **Surface finish** opens the **Surface roughness** table (section 6.1). Empty Title, Identification number and Date of issue are filled with the part name, the title in upper case and today's date |
| **Output folder** | Files are written to this folder. Empty: the `drawings/` folder of the open project; with no project open, the browser downloads one file, or `drawings.zip` for several files |
| **Write to a drawings folder next to each opened STEP file** | Writes to `<STEP folder>\drawings` for files opened by path |
| **Save as defaults** | Writes the current settings and fields to `config.json`. Title, Supplementary title, Identification number, Date, Mass and Material are not stored |

Output file names are `<STEP file>.pdf` for a STEP file with one part and `<STEP file>_<part>.pdf` for several parts.
With **Auto** sheet size the smallest sheet from A4 to A0 is used where the scale is >= `auto_sheet_min_scale` (default 1:1).

Path fields (**Folder or STEP file path on this PC**, **Output folder**, the **Folder** fields of the **Sketches** pane and the Part and Assembly tabs, **DXF path**, **STEP file path** of **Import STEP**) have a **…** button that opens the Windows file or folder dialog on this PC; **Add STEP** in the Assembly tab opens it directly. The dialog needs tkinter, which is part of the python.org installation.

The status line in the header is one line; a longer message is cut off and its full text is the tooltip.

### 3.1 Options

**Options** at the upper right opens the program options. They are stored in `config.json` (`options`) and apply at once, except **Browser**.

| Option | Choices |
|---|---|
| **Drawing units** | **mm** (default) or **inch, decimal point**. Applies to dimension text, tolerances, hole callouts (**Thread & hole callouts**), the title block **Units** field (`mm` is printed as `in`) and the deviation fields of the dimension properties. The model, the other input fields and the exports of the Part, Assembly and Analysis tabs are in mm |
| **Keyboard shortcuts** | **Default** or **Left-handed** (keys on the right side of the keyboard). The dialog lists the keys of the selected set for each tab. Tooltips show the key of the selected set |
| **Browser** | Command that `run.py` uses to open the program at start. Empty (default): the system default browser. `{url}` in the command is replaced by the address; without `{url}` the address is added at the end. Example: `"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --app={url}` (window without tabs and address bar). Stored in `config.json` (`browser`) and used at the next start. When the command fails the default browser is used |

Number formats of the drawing units:

| | mm | inch |
|---|---|---|
| Dimension | 0.001 mm, trailing zeros removed: `40`, `Ø15` | 3 decimals, leading zero omitted below 1 in (ASME Y14.5): `1.575`, `Ø.591` |
| Deviations | µm: `+27`, `0`, `-40` | 4 decimals with a sign, also on zero: `+.0011`, `-.0000` |
| Symmetric tolerance | `±20` (µm) | `±.0008` |
| Deviation fields (**Upper**, **Lower**) | µm | in |

Left-handed keys (default keys in parentheses). The keys are physical key positions; the labels follow the keyboard layout where the browser reports it.

| Tab | Keys |
|---|---|
| **Drawings** | **P** Sketch (K), **J** Select (S), **H** Horizontal (H), **I** Vertical (V), **/** Aligned (A), **;** Angle (G), **O** Diameter (D), **U** Radius (R), **N** Note (N), **L** Leader note (L), **K** Balloon (B), **Y** Detail (E), **M** Fit (F) |
| **Drawings**, **Sketches** pane | The default keys mirrored about the centre of the keyboard: Q↔P, W↔O, E↔I, R↔U, T↔Y, A↔;, S↔L, D↔K, F↔J, G↔H, Z↔/, X↔., C↔,, V↔M, B↔N, 1↔0, 2↔9, 3↔8, 4↔7, 5↔6, 6↔5; Shift as in the default set. **L**, **P**, **M**, **O** and **N** do not start Line, Point, Move, Offset and Note. With a drawing tool active, **.** and **,** start the coordinate input |
| **Part** | **7**, **8**, **9** run the **Next** commands (1, 2, 3) |
| **Assembly** | **K** Drag mode (D), **U** Rotate (R) |

Ctrl combinations, Esc, Enter, Delete and Space are the same in both sets.

## 4. Title block editor

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

## 5. Views and layout

| View | Direction |
|---|---|
| Front | Looking along +Y, X to the right, Z up |
| Top | From +Z, placed below the front view |
| Right | From +X, placed left of the front view |
| Section A-A, plane normal X | Cutting plane shown on the front view, viewed in +X (**Reverse**: -X) |
| Section A-A, plane normal Y | Cutting plane shown on the top view, viewed in +Y (**Reverse**: -Y) |
| Section A-A, plane normal Z | Cutting plane shown on the front view, viewed in -Z (**Reverse**: +Z) |
| Isometric | View direction (1, -1, 1) |

Two layouts are evaluated and the one giving the larger scale is used:

```
A:  Right | Front | A-A          B:  Right | Front | A-A | Iso
          | Top   | Iso                    | Top   |     |
```

Line widths follow ISO 128 in `config.json` > `line_widths_mm` (visible 0.5 mm, hidden, chain and hatch 0.25 mm, frame 0.7 mm) and are set in the **Title block editor** window (section 4).
Hatching is 45 deg at 2.5 mm spacing on paper (`hatch_angle_deg`, `hatch_spacing_mm`).

## 6. Drawings

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
| **Sketch** | K | A view (sketch on the view) or the sheet outside the views (sketch on the sheet); opens the sketch editor (section 6.3) |

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
The curves of a sketch made on the drawing (section 6.3) snap in the same way: line and polyline corners, mid points, arc ends and circle and arc centres. A point of a sketch on the sheet snaps in the view whose frame contains it.
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
| **Fit calculator** | Opens **ISO fits** (section 6.1) with the measured size and the class; **Use hole class for the dimension** or **Use shaft class for the dimension** sets **Class** |
| **Show deviations** | Adds the limit deviations of the class next to the class, in µm |
| **Upper (µm)**, **Lower (µm)** | Deviations for **Symmetric ±** (**Upper** only) and **Upper / lower deviation**, in µm (in with **Drawing units** inch, section 3.1). Decimal comma or point. The drawing text is in µm (`Ø15 H8 +27 / 0`, `4 ±20`): the lower deviation on the baseline of the nominal value, the upper deviation above it |

Dimensions are stored in view coordinates and follow the view when the sheet, scale or layout changes.
They are saved in `work/annotations/<drawing name>.json` and are included in PDF, DXF (layer `DIM`) and SVG exports.
Dimension text height is `dim_text_height_mm` (3.5 mm).

**Thread & hole callouts** places one note per hole feature (Part tab, **Hole**) and per external **Thread** feature of a part drawing: count, thread designation or diameter, counterbore, countersink and depth, for example `2x M8-6H, 15 deep` or `Ø9 H7, Ø15 counterbore 5 deep, through` (**Thread** and **Tolerance class** of the hole feature). A metric thread gets a second line with the size before threading and the nominal thread depth: `drill Ø6.8 (D1 6.647–6.912), thread depth 0.677` for a tapped hole, `turn Ø29.947–29.521, d3 25.652–25.306, thread depth 2.147` for an external thread (**Thread** feature), the limits for the tolerance class of the feature (6H or 6g when none is given); a trapezoidal thread (`Tr20x4`) gets `bore Ø16.000 (D1), D4 20.500, thread depth 2.250` or `turn Ø20, d3 15.500, thread depth 2.250, root radius max 0.250`; a unified or pipe thread gets `drill Ø5.1 (minor 4.975), thread depth 0.687, pitch 1.270` or `turn Ø6.350, minor 4.792, thread depth 0.779, root radius 0.183, pitch 1.270` (no class limits). An external thread callout is anchored on the outline at the middle of the thread length in a view across the axis. A hole whose axis is not along any view of the drawing (for example a hole along X with the Right view hidden) gets its note in a view across the axis, the leader pointing at the hole opening on the outline; with **Hidden lines** the hole itself is drawn there. The note is anchored at the top of the first hole of the feature in the view that looks along the hole axis (front, top or right) and placed above the view, in rows from left to right. A second use replaces the callouts placed before; the text is edited in **Text**.

### 6.1 Threads and holes reference

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

The same values are the presets of the **Hole** feature (section 10.4).

### 6.2 Detail views

**Detail** (key E) makes a magnified detail view: click the centre of the detail on the front, top, right or section view, then a point on the detail circle. A thin circle with a letter (B, C, …) marks the detail on the parent view; the content inside the circle is drawn magnified in a circle to the right of the views with the caption `B (2:1)`. **Detail views** in the side panel lists the details with **Magnification** (relative to the drawing scale; the caption shows the resulting scale) and a **×** button that removes the detail with its dimensions. A detail view is dragged like the other views. Dimensions and notes are placed in a detail view as in any view (snaps of the parent view inside the circle). Detail definitions are stored with the view layout (`<drawing name>.layout.json`, `details`); **Reset views** keeps the details and returns them to the default position.

### 6.3 Sketches on drawings

**Sketch** (key K) in the **Drawings** tab opens the sketch editor on the drawing. A click on a view sketches on that view, a click outside the views sketches on the sheet. **Sketches** in the side panel lists the sketches of the drawing with **Edit** and **×** (remove).

| Target | Coordinates | Behaviour |
|---|---|---|
| View (Front, Top, Right, A-A, Iso, detail views) | View coordinates in model mm at the view scale; dimensions show model sizes | Moves with the view; left out when the view is hidden |
| Sheet | Paper mm, origin at the lower-left sheet corner | Fixed on the sheet |

The editor shows the drawing without the edited sketch as the sheet. The edges of the view (all views for the sheet) are reference geometry: they snap, **Model edges** shows or hides them, **Include** and **Include edges** copy them into the sketch. All drawing, modify, constraint and dimension tools of the sketch editor are available (section 9). **Finish sketch** (Ctrl+E) stores the sketch with the drawing and returns to the **Drawings** tab; **Cancel** discards the changes.

The sketch is saved in `work/annotations/<drawing>.sketch.json` (one entry per target, the same key as the dimensions of the drawing) and is included in the preview and in PDF, DXF and SVG exports. Lines go to the drawing layers by their line type: continuous to `VISIBLE`, dashed to `HIDDEN`, centre lines to `CHAIN`; dimensions and notes of the sketch to `DIM`. Sketches on drawings are not written to the FCStd file.

## 7. DXF

DXF R2010, units mm, drawn at sheet size 1:1 (model coordinates are scaled by the drawing scale).
Layers: `VISIBLE`, `HIDDEN` (ISO_HIDDEN), `CHAIN` (ISO_CHAIN), `HATCH`, `TEXT`, `FRAME`, `TITLE`, with lineweights from `line_widths_mm`.
Circles and arcs in the projection plane are written as CIRCLE and ARC.
Other curves are written as LWPOLYLINE.

## 8. FCStd

The .FCStd file contains:

| Object | Content |
|---|---|
| `Part` | The part (or the selected parts as a compound) as Part::Feature, hidden in the 3D view |
| `Page` | TechDraw page with the same sheet size and scale as the PDF |
| `Template` | SVG template with the frame and title block. Field values are editable texts (double-click the field on the page) |
| `Front`, `Top`, `Right`, `Isometric` | TechDraw views (DrawViewPart) at the PDF positions |
| `Section` | Section view A-A (DrawViewSection), base view `Front` |
| `SectionCaption` | Annotation "A-A" |

TechDraw computes the view geometry when the file is opened.
Dimensions, centre lines and annotations are added with the TechDraw tools.
The section cut surface is a grey fill.
A 45 deg hatch is set by changing **Cut Surface Display** of `Section` to **SvgHatch** (the hatch file is included).
View positions can differ from the PDF by a few mm because TechDraw centres views on the 3D bounding box.

## 9. Sketch

**Drawings** / **Sketches** at the upper left of the **Drawings** tab switch between the drawings of the models and the sketch editor.
The **Sketches** pane is a 2D editor in model coordinates (drawing units of the DXF file, mm for a new sketch). It also edits sketches on drawings (section 6.3) and the feature sketches of the Part tab.
**New** starts a blank sketch on the selected sheet with the layers `0`, `CENTRE` (CENTER) and `HIDDEN` (DASHED).

### 9.1 Files

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

### 9.2 Drawing and modify tools

| Tool | Key | Picks |
|---|---|---|
| **Select** | Space | Click selects (Shift adds). Window from left to right selects entities inside; from right to left selects entities crossing. Dragging an end point, a line, a circle edge (radius) or a dimension moves it; constrained geometry moves only in its free directions and a fully constrained point stays in place |
| **Line** | Q | Chain of lines; Esc or right click ends |
| **Rectangle** | W | Two corners |
| **Circle** | E | Centre, point on the circle or typed radius |
| **Arc** | R | Centre, start point, end point (counter-clockwise) |
| **Polygon** | Shift+W | **Number of sides** (dialog), centre, then a vertex (circumscribed circle through the cursor) or the typed distance across flats. Creates the sides as lines with coincident, equal and point-on-circle constraints on a construction circle (DOF: position, rotation, size) |
| **P3G** | | Polygon profile: parameters in **Properties** when the tool is chosen, then the centre, then the direction of a lobe (point or typed angle). **Preset**: **DIN 32711 P3G (trochoid, k = n = 3)**, **4 lobes (trochoid, k = n = 4)**, **Schaublin K-profile Dm 22, R2 6 (SV13, 125, 135 change gears)**, **Two-arc K-profile, custom Dm and R2**, **Trochoid, custom n and k**. Trochoid (Filemon 1959, Periodica Polytechnica; DIN 32711 for k = n): **Nominal diameter d1 (mm)**, **Eccentricity e (mm)**, **Lobes n**, **Lever ratio k**; **Outer circle d2** and **Inner circle d3** set d1 = (d2 + d3)/2 and e = (d2 − d3)/4; x = R cos α − e cos α cos nα − k e sin nα sin α, y = R sin α − e sin α cos nα + k e sin nα cos α, R = d1/2; a closed polyline of 60 n points, used in extrude, cut, revolve and loft as one periodic spline through the points. Selecting the polyline shows its parameters in **Properties** (**Centre x**, **Centre y**, **d1**, **e**, **n**, **k**, **Rotation (deg)**, **Outer circle d2**, **Inner circle d3**); a change regenerates the polyline. Its only grip is the centre. Two-arc K-profile (the Schaublin change-gear bore, not DIN 32711): **Width Dm (mm)** and **Corner radius R2 (mm)**; three corner arcs R2 centred on an equilateral triangle of side R1 − R2 and three flank arcs R1 = Dm − R2 centred on the opposite corner, constant width Dm (Schaublin: Dm 22 mm, R2 6 mm, R1 16 mm, side 10 mm, outer circle 23.547 mm, inner circle 20.453 mm); created as six arcs with coincident and tangent constraints. Both add a construction point at the centre; the status line reports the outer and inner circle |
| **Ellipse** | Shift+E | Centre, end of the first axis (direction and half length, or typed), then the half length of the second axis (a point, or typed). **Properties**: centre, half axes, rotation, start and end angle (equal: closed ellipse; different: elliptical arc). Solver geometry: constraints and dimensions use the centre, the four axis ends and the arc ends; **Tangent** at an arc end holds the end direction. Grips move the centre, the axis ends and the arc ends. Exported to DXF as ELLIPSE; forms profiles and surfaces exactly |
| **Conic** | Shift+D | Conic section (rational quadratic Bezier): start point, end point, tangent intersection (the tangents at the start and at the end meet there), then the shoulder point on the curve or a typed rho (Enter: 0.5). Rho below 0.5: elliptical arc; 0.5: parabola; above 0.5: hyperbola. The shoulder point lies on the line from the chord midpoint to the tangent intersection at the fraction rho. **Properties**: start, end, tangent intersection, **Rho**; **Restore the whole conic** after a trim. Grips move the start, the end, the tangent intersection and the shoulder point (changes rho). Solver geometry: constraints and dimensions use the start, the end and the tangent intersection; **Tangent** at an end holds the end direction (the tangent intersection moves). **Trim** and **Fillet** work as for splines. Exported to DXF as a degree-2 rational SPLINE (a trimmed conic through sampled points); profiles and surfaces use the exact rational Bezier curve |
| **Spline** | Shift+F | Cubic spline through fit points: click the points; Enter, Esc or a double click ends the spline, a click on the first point closes it. **Properties**: **Closed**, the fit point coordinates, **Convert to conic**, **Explode to lines**. Grips move the fit points. Chord-length parameters, natural ends (closed: periodic). Solver geometry: constraints and dimensions use the fit points and the curve ends; **Tangent** at an end holds the end direction through the fit points. **Trim** and **Fillet** shorten a spline by its parameter range; the trimmed end gets a point-on-object or coincident constraint to the cutter; the curve itself is unchanged and **Restore the whole spline** in **Properties** removes the trim. A free spline with n fit points has 2n degrees of freedom. Exported to DXF as SPLINE (fit points; a trimmed spline through sampled points); profiles and surfaces use the same cubic as the sketch, span by span |
| **Point** | Shift+Q | Position |
| **Move** | V | Base point, destination (selection) |
| **Copy** | Shift+V | Base point, destinations; Esc ends (selection) |
| **Rotate** | Shift+R | Centre, angle typed in deg or a point (selection) |
| **Mirror** | Shift+B | Two points on the mirror line; copies are created (selection) |
| **Offset** | B | Distance (dialog), entity, side. Lines, circles, arcs, polylines. A line or arc is offset with the chain of lines and arcs connected to it end to end: the offsets are joined at the corners (extended or shortened to their intersection) and get coincident constraints; Shift+click offsets the entity alone |
| **Trim** | T | Part of a line, circle, arc, polyline, ellipse, spline or conic between intersections (the sketch axes do not count) to remove (an ellipse becomes an elliptical arc; a spline or conic keeps its curve and narrows its parameter range). With **Auto constraints** each new end is constrained to the cutting entity: coincident when it falls on an end of the cutter (within 1e-4 mm, replacing a point-on-object constraint of that end from an earlier trim), tangent anchored at the shared end when the curves touch there, tangent plus point on object when the curves touch elsewhere, otherwise point on object |
| **Extend** | Shift+T | Line or arc near the end to extend to the next intersection |
| **Fillet** | G | Radius (dialog), first entity, second entity: lines, arcs, splines, ellipses and conics in any combination (two curves must meet or have ends within **Gap tolerance (mm)** of each other; a closed curve is trimmed first). Each entity is clicked on the side to keep; where the two entities meet at a corner, the end at the corner is the one moved. Radius 0 joins the lines at the corner. With two lines selected before **Fillet**, the fillet is applied after the dialog and the longer part of each line is kept. Curves are trimmed by their parameter range; the fillet arc gets coincident and tangent constraints to both entities |
| **Chamfer** | Shift+G | Distance (dialog), first line, second line, as **Fillet** |
| **Pattern** | | Copies of the selected entities on a grid, set in **Properties**: **Count, direction 1**, **Direction 1 dx, dy (mm)**, **Count, direction 2**, **Direction 2 dx, dy (mm)**, **Row offset (mm)** (every second row shifted along direction 1). Counts include the original. The copies carry no constraints |
| **Construction** | C | Toggles construction geometry for the selection. Without a selection: new geometry is construction geometry |
| **Select tangent chain** (right-click menu) | Shift+C | Adds to the selection the lines and arcs joined with tangent continuity to the selected ones; **Select connected chain** adds those joined end to end. The selection is then the chain for **Offset**, **Move**, **Copy**, **Mirror**, **Pattern** and **Delete** |
| **Delete** | X, Delete | Removes the selection, and the constraints and dimensions that use it |
| **Undo**, **Redo** | Z, Shift+Z (Ctrl+Z, Ctrl+Y) | |
| **Fit** | F | Zooms to the drawing |
| **Check** | | Lists the sketch issues in **Properties**: gaps between two ends within **Gap tolerance (mm)** (default 0.5 mm), open ends, junctions that are nearly tangent within **Tangent tolerance (deg)** (default 2 deg), tangent junctions without a tangent constraint, touching ends without a coincident constraint, overlaps (collinear lines whose segments overlap, with the overlap length in mm; arcs and circles with the same centre and radius whose spans overlap, with the overlap angle in deg; identical ellipses, splines, conics and polylines). A click on an issue selects the entities and centres the view on it. **Fix** closes each gap at the midpoint with a coincident constraint (at the curve end when one side is a trimmed curve), adds the missing tangent and coincident constraints, merges overlapping lines and arcs into the one with more constraints (extended to the union; a full union of arcs becomes a circle) and removes the duplicate of two identical curves, and keeps each fix only when the solver accepts it. Constraints and dimensions of a removed entity are dropped. Open ends are listed only. **Convert N polyline(s)** turns every polyline of the sketch into solver or curve geometry: an arc or a circle when its vertices lie on one circle, a spline through the vertices when it is a sampled curve (5 or more vertices with turns below 30°), else lines |

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
The default keys are placed for the left hand. **L**, **P**, **M**, **O** and **N** also start Line, Point, Move, Offset and Note. The left-handed set (section 3.1) mirrors them to the right side of the keyboard.
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
For a polyline, **Convert to arc** / **circle** (offered when the vertices lie on one circle, with the radius), **Convert to spline** and **Convert to conic** (offered for an open polyline whose end tangents meet on the convex side, with the maximum deviation of the vertices from the conic in mm) replace it by solver or curve geometry. **Convert to conic** fits the end tangent directions and rho to the vertices. **Explode to lines (N)** makes one line per segment; a sampled curve (5 or more vertices with turns below 30°) is marked "sampled curve" and becomes N short lines with open ends. An open spline also offers **Convert to conic**. Polylines included from the model (**Include**, **Include section**, **Include edges**) are converted on inclusion.

**Layers**: visibility, current layer (radio button), colour, line type and lineweight. **Add layer** creates a layer.

### 9.3 Constraints

The constraint buttons (icon and name: **Coincident**, **Horiz.**, **Vert.**, **Parallel**, **Perp.**, **Tangent**, **Equal**, **On**, **Mid**, **Conc.**, **Sym.**, **Fix**) are in one group with the dimension tools **Dimension**, **Horizontal** and **Vertical** (left of them); **Note** and **Leader** follow in their own group.
The constraint buttons apply to the selected points and entities.
A constraint button pressed with nothing selected starts the pick mode for that constraint (button highlighted, hint in the status line): the points and entities clicked next are collected and the constraint is applied as soon as the selection fits it, after which the next pick starts. Esc, the same button or a drawing tool ends the pick mode.
The constraint keys work with the **Select** tool; with a drawing tool active, digits start the coordinate input.
Points are selected by clicking an end point or centre; Shift+click adds a line, circle or arc to the selection.
The entity selected as reference (the line for a point on a line, the first line for parallel, perpendicular, equal and tangent) is held where possible and the other entity moves.

| Button | Key | Selection |
|---|---|---|
| **Coincident** | 1 | Two or more points (the first selected point moves to the others), or points and one line, circle, arc or curve (point on object). Curve points: spline fit points, conic start, end and tangent intersection, ellipse centre, axis ends and arc ends |
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

With **Auto constraints** the drawing tools add coincident constraints at snapped end points and centres, point-on-object at nearest snaps, midpoint at mid snaps, horizontal and vertical constraints for lines within 1.5 deg, and the coincident and tangent constraints of fillets and chamfers.
Constraints are shown as symbols (coincident: green dot) when **Show constraints** is checked.
Clicking a symbol selects the constraint; **Delete** removes it.
Coincident constraints are listed in **Properties** of the entity and are selected there.
Conflicting and redundant constraints are not added (message in the status bar).
The status bar shows the remaining degrees of freedom (**DOF**) or **Fully constrained**.
Move, rotate, trim, extend, fillet and chamfer remove the constraints that are no longer satisfied.

### 9.4 Dimensions and notes

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
After a dimension value changes, a sketch with a sheet (and a sketch on a drawing) keeps the zoom; the view is only moved to the geometry when it left the window. A sketch without a sheet fits the view when the geometry leaves the window or fills less than a fifth of it.
A changed value keeps the other radii, the construction line lengths and the first picked point where the other constraints allow.
**Properties** of a dimension: **Driving**, **Value**, **Orientation**, **Type** (diameter/radius), Ø symbol, **Prefix**, **Text override**, text centred, **Tolerance** (as in section 6).
Dimensions and notes are drawn at `dim_text_height_mm` on paper at the sketch **Scale**.

## 10. Part

The **Part** tab builds a solid from a tree of items: reference planes, sketches, planes, features and the bodies they produce.
Elements are selected in the 3D view.
Every feature is defined with a step-based command bar.
The toolbar buttons of the Part tab, the **Drawings** tab and the **Sketches** pane show an icon with the command name (`static/icons.js`).
**Panel** (Ctrl+B) hides or shows the right side panel of the Part tab and the **Sketches** pane.

### 10.1 Tree

| Section | Items |
|---|---|
| **Reference planes** | **Top (XY)**, **Front (XZ)**, **Right (YZ)**: planes through the origin. Eye: show or hide |
| **Bodies** | **Solid 1**, **Solid 2**, ... (one per cell of the solid, with the volume when there are several) and the surface and curve bodies, named after the feature that produced them. Eye: show or hide |
| **Features** | The ordered list: sketches (✎), planes (▱), points (⊕), axes (⟋), features (●), surface and curve features (◈, ∿). Check box: active (unchecked: suppressed); ▲, ▼: order; ✕ or the Delete key: delete without confirmation (the status line names the features that used the item); eye on sketches, planes, points, axes and surface or curve features: show or hide. Ctrl+Z undoes a deletion or reordering, Ctrl+Y repeats it |

A click on an item selects it and highlights its geometry in the view (green): the faces created by a feature, the curves of a sketch, a plane, a body.
Hovering an item highlights it in the same way.
Double-click opens the definition of the feature in the command bar (a sketch: the sketch editor).
Double-click on a reference plane or a plane feature starts a Sketch on that plane and opens the sketch editor.
During a command, a click on a reference plane, a plane feature or a sketch in the tree feeds the active step.
**Command** below the tree shows the steps and values of the selected item with **Edit definition**.
**Next** in the same panel lists up to three suggested commands for the selection, started with keys 1, 2, 3 or a click: a sketch with closed profiles: **Extrude**, **Cut**, **Revolve**; an open sketch: **Extruded surface**, **Sweep** (path); a reference plane or plane feature: **Sketch** on it, **Plane**, **Partition**; a surface: **Thicken**, **Trim surface**, **Extend surface**; a curve: **Sweep**, **Plane**; a solid feature or nothing selected: **Sketch**, **Round**, **Chamfer** or **Hole**.

| Plane | Sketch x (u) | Sketch y (v) | Normal |
|---|---|---|---|
| XY | X | Y | +Z |
| XZ | X | Z | -Y |
| YZ | Y | Z | +X |

### 10.2 Selection in the view

Moving the mouse over the view highlights the element under the cursor (light green) with a tooltip: `Face (Extrude 1)` (the feature that created the face, and the solid when there are several), `Edge, 60 mm`, `Solid 1`, `Surface (Extruded surface 1)`, `Curve (Extract curve 1)`, `Sketch 1`, `Reference plane Top (XY)`, `Plane 1`, `Region 2, 603.2 mm^2`. A circular edge shows the diameter (`Edge, Ø20 mm`) when it spans 180° or more. A smaller arc shows the radius, the angle and the length (`Edge, R3 mm, arc 90°, length 4.71 mm`). A cylindrical face adds the diameter, or the radius below 180° (`Face (Extrude 1), Ø20 mm`, `Face (Fillet 1), R3 mm`).
A face belongs to the feature that created its surface; a face split or trimmed by a later feature keeps its owner.
Outside a command, a click selects the owner of the element in the tree (a face: its feature; an edge: nothing).
During a command, a click feeds the active step; only the element kinds the step accepts are highlighted.
Steps that take a point also take a vertex of the solid: a vertex within 8 px of the cursor and not hidden behind a face is highlighted with the tooltip `Vertex (x, y, z) mm`. A picked vertex is stored as its coordinates (it does not follow later changes of the part). Steps that take a vertex: **Point** (**Coordinates**: the coordinates are copied; **Offset from a point**, **Midpoint of two points**), **Axis** (**Point and direction**, **Two points**, **Normal to a plane**, **Parallel to an axis through a point**), **Plane** (**Point and normal**, **Through an axis and a point**, **Normal to an axis at a point**; **Three points**: point 1, 2 and 3 in turn), **Partition** (**Method**: a vertex sets **Point and normal** through it; **Three points**: point 1, 2 and 3 in turn) and the **Origin and x axis** step of **Sketch**.
Outside a command, a double-click on a reference plane, a plane feature, a planar face or an edge starts a Sketch on that plane and opens the sketch editor.
In the **Plane** step of the Sketch command, a double-click on one of these elements sets the plane and opens the sketch editor.

### 10.3 Command bar

A toolbar button starts a command.
Numeric fields of the commands, the sketch dimension values and the sketch command line accept arithmetic expressions with `+ - * / ^ ( )`, `sqrt()` and `pi` (for example `450/2`, `(120-2*8)/3`). A decimal comma is accepted.
The command bar replaces **Command** below the tree and a bar above the view shows the active step and its instruction.
The steps are listed in order: a numbered step is open, a green check marks a completed step, the active step is orange and expanded.
A step that takes elements (faces, edges, bodies, sketches, planes, regions) lists what is selected; a step with values shows its fields.
**Next** moves to the next step; a single-element step moves on when its element is clicked.
A click on a step row returns to it.
**Finish** (Enter, Ctrl+E, or a triple click in the view) closes the command; it is disabled until the required steps are complete.
A new Trim surface, Extend surface, Sew surfaces or Thicken hides the surface bodies it replaces (eye in **Bodies** shows them again). The hidden state is saved with the part. Where two surfaces coincide, the later feature is picked.
**Cancel** (Escape) removes a new feature or restores an edited one.
The feature exists in the tree while it is defined and the part rebuilds on every change.
During an element step of a feature that changes the solid the view shows the part before that feature (the bar above the view says so).
**Name** in the command head renames the feature.

### 10.4 Features

| Button | Steps |
|---|---|
| **Sketch** | **Plane**: click a reference plane, a plane feature, a planar face (sketch on the face through its centre; the sketch x axis is the principal direction X, Y or Z nearest the screen right direction of the view at the click, so the sketch opens as the face is seen) or an edge or curve (plane normal to it at **Position along the edge (0 to 1)**, **Flip the normal**) or an axis feature (plane normal to the axis at its origin), or choose it in **Plane**; **Offset (mm)** along the normal. **Origin and x axis** (optional): click an edge of the part (the sketch origin goes to the nearer end of the edge and the sketch x axis along it), a face (the origin goes to its centre), a point feature (the origin) or an axis feature (the sketch x axis), or type the origin (mm; projected onto the plane); **Plane origin and default x axis** resets. **Draw** opens the sketch editor (section 9); **Finish sketch** returns to the Part tab. A new sketch left empty is removed. The selected reference plane or plane feature is the default |
| **Plane** | **Method**: **Principal plane + offset**; **Parallel to a plane feature + offset** (**Reference plane**: click it); **Parallel to a planar face + offset** (**Planar face**); **Midplane between two parallel faces** (**Two parallel faces**); **Normal to an edge or curve** (**Edge or curve**: an edge of the solid, a curve body or a curve of a sketch; **Position along the edge**). A click on a sketch curve selects the chain of connected curves of that sketch nearest the click; with **Position along the curve** empty the plane is at the chain end nearer the click; **Through an edge, at an angle to a face** (**Planar face**, **Edge or curve**, **Angle from the face (deg)**: 0 is the plane of the face); **Point and normal** (**Point**: a point feature, **Normal axis**: an axis feature; or typed values); **Through an axis and a point** (**Axis**, **Point**); **Normal to an axis at a point** (**Axis**, **Point**: none is the axis origin); **Three points** (point 1 origin, point 2 sketch x). **Offset**: **Offset along the normal (mm)**, **Flip the normal**; shows the origin, normal and sketch x direction |
| **Extrude** | **Profile**: a sketch (click it in the view or the tree, choose it in **Sketch**, or **New sketch**: a sketch is created before the feature, drawn, and the command resumes); **Regions** (optional): the bounded regions of the sketch are shown (closed loops split by every crossing curve); click the ones to use, **All**, **None**; none picked: every closed loop, nested loops as holes; **Extent**: **Depth (mm)**, **Direction** (along the normal, against it, symmetric to the plane), **New body** (a separate solid, not fused with the part) |
| **Cut** | **Profile**; **Regions** as for Extrude; **Extent**: **Type** through all (both directions) or finite depth with **Depth (mm)** and **Direction**. A finite cut that removes nothing in its direction is made in the opposite direction and **Direction** is updated |
| **Revolve** | **Profile**; **Regions** as for Extrude; **Axis and extent**: **Axis** (sketch x axis, sketch y axis, a construction line of the sketch, or an axis feature: choose it or click it), **Angle (deg)**, **Mode** add or remove material, **New body** |
| **Point** | Reference point. **Method**: **Coordinates** (mm); **On an edge or curve** (**Edge or curve**: an edge of the solid, a curve body or a curve of a sketch, as for **Plane**; **Position along the edge (0 to 1)**); **Centre of a face** (**Face**); **Offset from a point** (**Point**); **On an axis at a distance** (**Axis**, **Distance from the axis origin (mm)**); **Axis and plane intersection** (**Axis**, **Plane**); **Midpoint of two points** (**Two points**). **Offset** (optional): dx, dy, dz (mm) added to the result. Drawn as a cross with its name; picked in the view and the tree |
| **Axis** | Reference axis (infinite line). **Method**: **Point and direction** (**Point**: a point feature or typed coordinates; **Direction** X, Y, Z or a vector); **Two points** (two point features, or typed coordinates); **Straight edge or curve** (**Edge or curve**); **Axis of a cylindrical face** (**Cylindrical face**: cylinder, cone or torus; the origin at the height of the face centre); **Intersection of two planes** (**Two planes**: plane features); **Normal to a plane** (**Plane**, **Point** optional: none is the plane origin); **Parallel to an axis through a point** (**Axis**, **Point**). **Direction**: **Flip the direction**. Drawn as a dash-dot line with its name |
| **Fillet** | **Edges** (click mode **Edge**, **Tangent chain**, **All edges of a face**; click again to deselect; **Clear**); **Radius (mm)**. A fillet that fails names the edges: an edge that fails alone is drawn red with its largest radius; when each edge works alone, the pairs of edges whose fillets overlap on a face are drawn red with the largest radius for all edges (search limited to 5 s) |
| **Chamfer** | **Edges**; **Distance (mm)** (equal distances). A failed chamfer is reported as for **Fillet** |
| **Shell** | **Open faces** (optional: the faces removed, none for a closed hollow part); **Thickness**: **Wall thickness (mm)** |
| **Hole** | **Positions**: a sketch whose points or circle centres are the hole positions; **Hole**: **Standard hole for a metric screw** (section 6.1) fills the fields below for the chosen screw size: tapped hole with the tap drill and 6H, clearance hole (ISO 273 fine, medium or coarse), counterbore for ISO 4762 or DIN 7984 screws (DIN 974-1 row 1), countersink 90° for ISO 10642 (DIN 74 F) or ISO 7721 head screws (ISO 15065); **Diameter (mm)**, **Depth (mm)** (empty: through), **Counterbore dia / depth**, **Countersink dia / angle**, **Thread** (`M8`, `M10x1.25`), **Tolerance class** (`H7`, `6H`), **Reverse direction**. The holes go from the sketch plane into the side where the part is |
| **Thread** | External thread on a cylindrical face of the solid. **Face**: the face; **Thread**: **Designation** (metric coarse or fine from the reference tables, or **Custom** such as `M10x1.25`), **Tolerance class** (6g), **Thread length (mm)** (empty: the whole face), **Start at the other end of the face**, **Turn the face down to d max of the class over the thread length** (the face diameter is reduced to the maximum major diameter of the class, for example 29.947 mm for M30-6g). The solid is otherwise unchanged; the thread is cosmetic on the drawing with a callout (section 6). **Type** selects metric coarse (ISO 261), metric fine (ISO 262), bearing lock nut threads (KM nuts DIN 981: M10x0.75 … M200x3, for example M17x1 for KM 3), trapezoidal (ISO 2904, class 7e), unified UNC and UNF (ASME B1.1, class 2A), pipe thread G (ISO 228-1, class A) or a custom designation (`M10x1.25`, `Tr20x4`, `1/4-20 UNC`, `G1/2`). The same designations are accepted in the **Thread** field of a **Hole** feature. Trapezoidal threads get nominal dimensions in the callout (d3, thread depth, root radius) without class limits |
| **Mirror** | **Features**: sketch features and holes to mirror (click a face of each, or check them), **Mirror the whole body (fused)**; **Mirror plane**: reference plane or plane feature with **Offset (mm)**, or a planar face of the solid. The mirrored tool bodies are cut or fused as in the original features. Mirrored holes keep their thread and callout |
| **Pattern** | **Parameters**: **Kind** linear (**Count** and **Direction 1 step** dx dy dz; **Count in direction 2** and **Direction 2 step**; **Row offset (mm)**: every second row shifted along direction 1) or circular (**Count**, **Axis**: X, Y, Z with the axis point, or an axis feature; **Total angle (deg)**; 360 spreads evenly), the sketch features and holes to repeat. Repeated holes keep their thread and callout |
| **Sweep** | **Profile**; **Path**: a sketch (one open chain of lines and arcs) or a curve body; **Mode** add or remove material, **New body**. The profile plane should be normal to the path at its start |
| **Boolean** | **Operation**: **Union (fuse)**, **Subtract (target minus tools)**, **Intersect (common volume)**; **Keep the tool solids**; **Target** and **Tools**: solids of the part (click them in the view or check them; numbered as in the tree before this feature). Separate solids come from Extrude, Revolve or Sweep with **New body**, from Partition or from an imported STEP file |

Profiles of a sketch: closed loops of lines, arcs, circles and polylines; construction geometry is ignored; a polygon profile (**P3G**), and a closed polyline of 12 or more vertices with every turn below 15 deg, is one periodic spline through its vertices (two smooth side faces when extruded). Sketch splines become cubic B-splines with simple knots at the chord-length parameters of the fit points (C2), so **Shell** and **Thicken** offset their faces; other polylines are straight segments; a loop inside another loop is a hole; a loop inside a hole is a separate profile. An open chain is ignored when the sketch has at least one closed profile (the command reports its end points as a note); a sketch with no closed profile fails with the open ends in the error.
Edges are identified by their mid point and length, faces by their centre.
An edge that no longer exists after a change to an earlier feature is skipped.
A failed feature shows its error in red in the tree and in the command; the feature is skipped in the build.
A cut whose profile does not pass through the part, or an extrude that adds nothing, is reported in the same way.

Reference geometry in the sketch editor: dashed lines are the section of the part and of the surface and curve bodies (features above the sketch) with the sketch plane; grey lines are the part seen along the plane normal with hidden edges dotted, and the edges of the surface and curve bodies projected (**Model edges** check box in the sketch bar); purple: point features projected onto the sketch plane (cross), axis features projected (dash-dot lines; an axis normal to the plane appears as a point) and plane features as their intersection line with the sketch plane. Curved edges that lie on a circle are reference circles or arcs; other curves are polylines. Reference geometry snaps but is not part of the sketch.
Dimensions of a feature sketch (and of any sketch without a sheet) are drawn at a fixed size on screen (text 12 px, arrows to match) whatever the zoom and the size of the part; on a sheet the dimension text height is the configured paper height.
The sketch axes are entities of a feature sketch: the x axis and the y axis (fixed construction lines, dash-dot, x red, y green) and the origin (fixed point). They take constraints (coincident to the origin, point on an axis, symmetric about an axis, parallel, perpendicular) and dimensions (distance from an axis). They cut in Trim; Extend does not stop at them. They are not exported, do not form profiles and are not deleted with **Delete**. **Axes** in the sketch toolbar removes them (with the constraints and dimensions on them) or adds them, also in a sketch outside the Part tab.
The sketch coordinate system is drawn at the sketch origin (x red, y green) when the sketch has no axis entities. The base coordinate system of the part, projected onto the sketch plane, is drawn dashed at the projection of the part origin (X, Y, Z; an axis normal to the plane is not drawn). Both origins are snap points (and can be included).
The editor opens fitted to the sketch and the reference geometry. A sketch without geometry opens with a view at least `sketch_view_width_mm` wide (`config.json`, default 200 mm) centred on the origin. The view is fitted again when the first geometry is drawn in an empty sketch and when a dimension value moves the geometry out of the view or leaves it smaller than a fifth of the view.
**Include** copies reference geometry into the sketch: click the reference lines, arcs and circles (Escape ends); **Include section** copies the whole section, **Include edges** all visible model edges. With **As construction** checked, included entities are fixed construction geometry (teal dashed): constraints and dimensions can use them (coincident, tangent, parallel, equal, a distance from an edge of the part), and they do not form profiles. With **As construction** unchecked, included entities are ordinary sketch geometry without constraints: editable, and used in profiles (a new sketch built from the model edges or the section). Unchecking **Construction** in the properties of an included entity makes it part of the profile. Included geometry is a copy; it does not follow later changes of the part.

Holes with a **Thread** are drawn with a cosmetic thread (ISO 6410-1): a thin 3/4 circle at the major diameter in the views along the hole axis and, when **Hidden lines** is checked, thin lines at the major diameter in the views across the axis. The major diameter comes from the designation (`M8`: 8 mm; `G1/4`: 13.157 mm). An external **Thread** feature is drawn with a thin 3/4 circle at the minor diameter d3 in the view onto the thread end, thin lines at d3 along the thread length and a thick line across the part at the thread end in the views across the axis. **Thread & hole callouts** in the **Drawings** tab writes the callout notes for both (section 6).

Part files (`<Name>.part.json`) are version 2: sketches are items of the tree and features reference them (`sketch_ref`, `path_ref`). A version 1 file (sketch embedded in each feature) is converted when loaded.

### 10.5 Configurations

**Configurations** lists every driving dimension of the sketches and the main value of each feature (depth, angle, radius, thickness, diameter, count, plane and sketch offsets).
A dimension can be given a **Name**.
**Add** creates a configuration with the current values; the active configuration is selected in the list.
A changed value is stored in the active configuration, the sketch is solved with the new value and the part is rebuilt.
Selecting another configuration applies all its values.
Configurations are stored in the part file.

### 10.6 3D view

| Control | Function |
|---|---|
| Left button drag | Rotate about the centre of rotation, without limit (horizontal movement about the screen vertical axis, vertical movement about the screen horizontal axis) |
| Middle or right button drag | Pan |
| Middle click on the model | Sets the centre of rotation at the clicked point (blue marker); the view does not move |
| Mouse wheel | Zoom about the cursor |
| Navigation cube (upper right of the view) | Turns with the view. A click on a face (**Front**, **Back**, **Left**, **Right**, **Top**, **Bottom**) turns the view to look at that face; the centre of rotation, the distance and the zoom are kept. The screen up direction becomes the axis direction nearest to the current one, so a view that is nearly square is squared up without being turned |
| **Iso**, **Front**, **Top**, **Right** | View directions as in the drawing (front: looking along +Y, Z up); the centre of rotation returns to the centre of the part |
| **Show ▾ → Section view** | Cuts the view with a plane. The box at the lower left of the view sets **Plane** (a reference plane or a datum plane), **Offset (mm)** along the plane normal (slider or value), **Flip** (the side kept) and **Cap** (the cut faces of the solid drawn grey with their outline, computed from the solid when the slider is released). Faces, edges, surface bodies and sketches on the removed side are not drawn. **Off** or the checkbox ends the section view |
| **Measure** | Measure mode (section 10.11). Click a face of the solid, a reference plane, a plane feature or an axis feature, then a second one. Esc or × ends |
| **Fit** | Fits the part in the current direction |
| **Show ▾** | Menu with **Edges**, **Axes**, **Planes** and **Sketches** |
| **Edges** | Shows the edges |
| **Axes** | Shows the coordinate system at the origin (X red, Y green, Z blue). **Edges**: edges of the visible solids |
| Space | Hides or shows the element under the cursor (its solid, a plane, a point, an axis, a sketch, a surface or a curve), else the selected tree item (a solid feature: the solid), else all planes, points and axes (**Planes**). Not while a text field has the focus |
| **Planes** | Shows the reference planes and the plane features as translucent squares with their names |
| **Sketches** | Shows the sketches as curves (construction geometry dashed blue) |

The bar above the view shows the volume, the mass (with **Density (kg/m^3)** from **Views**) and the size.

### 10.7 Files

The **File ▾** menu at the left of the toolbar holds these controls.

| Control | Function |
|---|---|
| Header | The open project (**Project** tab), or the program folder when no project is open. **Open folder** opens the project `work/` folder |
| **Part** | The saved parts of the open project. The current part is selected (`*`: changed since saved; **(not saved)**: no file in the open project). Choosing a part opens it |
| **New** | Empty part (**(not saved)** until the first **Save**) |
| **Save** (Ctrl+S) | Writes the part with all feature sketches to `<Name>.part.json` in the project `work/` folder (program folder: `parts/`). A part without a file in the open project asks for a name as **Save as…** |
| **Save as…** | Writes the part under a new name as a new document (new uid, separate drawing). An existing name is overwritten after confirmation |
| **Rename…** | Renames the saved part in the project, as **Rename** in the **Project** tab (assemblies using the part are updated). Requires an open project |
| **Output folder**, **…**, **Open** | Folder for **Export STEP** and **Export mesh**. Empty: the project `step/` folder (path shown in the field), or a download when no project is open. **Open** opens the project `step/` folder |
| **Export STEP** | Writes `<Name>.step` to the output folder, or downloads it |
| **Export mesh** | FEA mesh of the part (section 10.10) |
| **Make drawing** | Adds the part to **Models** as `<Name>.part` (other parts are deselected) and makes the drawing with the current settings |

After a change to the part, **Make drawing** replaces the part in **Models** and the drawing is computed again. The **↻** button of the entry in **Models** does the same from the **Drawings** tab: the part is taken from the **Part** tab when it holds that part, otherwise from the saved part file. Dimensions, notes and view positions of the drawing are kept.
Dimensions and notes added to the drawing are kept. For a part made in the program they are saved under the part's uid (`work/annotations/part_<uid>.json`), so two parts with the same name have separate drawings; a part saved before the uid existed takes over the annotations stored under its name once. STEP files keep the file name as the key.

### 10.8 Mesh preparation: import, partition, clean-up

The **Faces ▾** menu of the **Part** tab holds the features that prepare a part for a hexahedral mesh. They are features like the others: ordered, suppressible, rebuilt with the part.

| Feature | Function |
|---|---|
| **Import STEP** | Base geometry from a STEP file (**STEP file path on this PC**; **Solid in the file**: empty for all solids, or the index of one). The other features apply to the imported solids |
| **Place** | Moves the whole part (solid and surface bodies) to the principal planes and axes. **Face 1** is turned onto its target (**On plane / axis**: XY, XZ, YZ, X axis, Y axis or Z axis), **Face 2** is turned about the first target direction (plane normal or axis) onto its target, **Face 3** is only moved onto its target. A planar face lies on its plane with its outward normal against the plane normal, so the part is on the positive side; **Flip**: the negative side. A cylindrical face (hole, shaft) has its axis on the X, Y or Z axis with the axis direction along it; **Flip**: reversed. A plane selected for a cylindrical face means the axis normal to that plane. A direction already set by an earlier face is not moved again and the result line notes it (for example a hole on the X axis, then a face on XZ: the face gives the turn about X only). A click in the view picks the next empty face; while the command is open the view shows the part before **Place**. **Directions without a face**: **Keep the position**, **Bounding box centre to the plane** or **Bounding box minimum to the plane**. **Offset after placing (mm)** is added last. The result line gives the bounding box, and a note when face 3 ends up facing along its plane normal (part on the negative side). Features after **Place** use the moved part; an assembly component of the part moves with it |
| **Partition** | Cuts cells with a plane (CAE: Partition Cell). The command starts at **Method**; a click in the view there picks the tool and sets the method: a face (**Extend a face**), a reference plane or plane feature, an edge or curve (**Normal to an edge or curve**), a sketch or a surface body. **Method**: **Principal plane + offset** (**Plane** XY / XZ / YZ, **Offset (mm)** from the origin or, with the check box, from the minimum of the part); **Plane feature + offset** (**Plane**: click a plane feature); **Extend a face** (**Face**: click it; its surface, planar or curved, is extended through the cells; **Offset from the face (mm)**, positive away from the material); **Sketch extruded through the part** (**Sketch**: lines, arcs and circles extruded normal to the sketch plane through the whole part; CAE: partition by sketch); **Normal to an edge or curve** (**Edge or curve**, **Position along the edge** 0 to 1); **Surface body**; **Point and normal**; **Three points**; **Around a hole** (**Hole face**: four planes through the hole axis, two along the principal directions and two diagonals, applied to the cells around the hole). **Cells**: click a face of each cell to partition; none: all cells |
| **Merge faces** | Merges coplanar (and co-cylindrical) faces and collinear (and co-circular) edges left by imports and booleans (CAE: virtual topology, remove redundant entities). **Angular tolerance (deg)** 0 is exact |
| **Heal** | Fixes the topology of imported geometry. **Small edges below (mm)** drops edges shorter than the value; **Small faces narrower than (mm)** removes spot and strip faces (CAE: geometry repair, remove small edges / small faces). A result that is invalid or changes the volume by more than 1 % is rejected with an error |
| **Smooth surfaces** | Re-approximates the B-spline surfaces and curves of imported geometry with degree-3 splines of at most **Max spline segments per surface** within **Tolerance (mm)**, **Continuity** C2 or C1; analytic surfaces are kept (CAE: re-approximate / convert to precise). Removes the small-scale waviness of exported free-form faces. A result that is invalid or changes the volume by more than 1 % is rejected |
| **Replace faces** | The manual "offset surface" method: the surface of the largest picked face is cleaned (**Clean surface**: analytic plane / cylinder / cone / sphere / torus within **Tolerance (mm)**, else a smooth spline; or a smooth spline; or the original surface), moved by **Offset of the surface (mm)** (+ outward), and within the footprint of the picked faces the material outside the surface is cut away and the material up to the surface is added (**Pad depth (mm)** outward; also inward with a negative offset). The rest of the part is untouched. **Also small faces below (mm^2)** adds the slivers touching the picked faces to the footprint (CAE: replace faces). Works cell by cell; an invalid result is rejected |
| **Remove faces** | Removes the picked faces and extends the neighbouring faces to close the gap: fillets, chamfers, holes, bosses (CAE: remove faces / defeaturing). When the neighbours cannot be extended, the opening is closed with a smooth patch. **Also small faces below (mm^2)** includes the small faces touching the picked ones (slivers around a face); **Every face below that area in the part** removes all faces below the area without a pick (CAE: remove small faces). Works cell by cell |
| **Offset faces** | The picked faces move along their normals by **Distance (mm, + adds material)**; the neighbouring faces are extended or trimmed to meet them (CAD: offset face, push/pull). A cylindrical hole face with a negative distance enlarges the hole. **Include faces connected through tangent edges** (default on) adds the tangent-connected faces, for example the sides and the round top of a slot. Where the OCCT offset fails or changes the volume by more than 30 % from area x distance, the material between each face and its offset is added or removed: neighbouring faces at a right angle are extended or trimmed, other neighbouring faces keep their position (a step). Works cell by cell |
| **Move faces** | The picked faces move by **Move vector (mm)**. **Include faces connected through tangent edges** (default on) moves the tangent-connected faces with them, for example the round top of a slot with its flat top. Each face sweeps along the vector: the swept volume is added where the outward normal points along the vector and removed where it points against it; faces parallel to the vector are extended or trimmed (push/pull). Planar faces moved along their normals are offset as **Offset faces**. A face moved across its own curvature (a hole moved sideways) makes the picked faces a feature (all faces of a hole, boss or slot): the feature is removed (as **Remove faces**) and its volume is cut or added again at the moved position. Faces that **Remove faces** cannot take away are refused |
| **Combine faces** | Virtual topology for the mesh: the picked faces are meshed as one surface and their shared edges do not constrain the mesh; the geometry is unchanged (CAE: virtual topology, combine faces). **Combine every face below (mm^2) with its largest neighbour** does it for small faces. A group is skipped when an edge inside it also bounds a face outside the group. Free meshes only; structured blocks need real faces |
| **Hole mesh** | O-grid partition and mesh seeds for holes through a planar part (bolt and pin holes, several holes, counterbored and blind holes). **Pick hole faces**: one cylindrical face per hole; the cylinders on the same axis (counterbore) belong to the hole. Planes through each hole axis along the two in-plane directions (the global axes most perpendicular to the hole axis), the sides of a square around each hole and planes normal to the axis at the steps of the hole (counterbore, blind bottom) cut the whole part; the hole cylinders are extended through the cells of the square, and the two diagonals through the axis cut the cells of the square. The cells become blocks; below a blind hole the cells on the axis are prisms. **Square side / hole diameter** (default 2) sets the square; it is reduced so that the square stays inside the part and does not reach the lines of another hole; the feature is refused when the half side would be less than 1.1 x the hole radius. **Elements per 45 deg of the hole**, **Elements from the hole to the square**, **Radial bias (largest / smallest element)** and **Elements through the thickness** are used by **Export mesh** with **Hexahedra, structured** (section 10.10). The result line gives the square side and the number of blocks and prisms |

In the parameter panels of these features (and of the other features with a **Pick** button) a click on a face in the view picks it for the first pick of the panel; the **Pick** button is needed only for the other picks of the panel.

The status line shows the number of cells; **Bodies** in the tree lists them as **Solid 1**, **Solid 2**, ... with their volumes.

A cell is a block when it has 6 faces with 4 edges each. A block gets a structured hexahedral mesh. Typical partitions: a plate with a hole is cut by a plane through the hole axis along each principal direction, then **Around a hole** on the hole face; the cells next to the hole region are cut by the same principal planes so that the shared faces stay 4-sided. A cell is not a block when a neighbouring partition splits one of its faces.

### 10.9 Surfaces

The **Surfaces ▾** menu of the **Part** tab creates surface bodies (faces or shells) that are kept beside the solid, listed under **Bodies**, shown translucent blue in the 3D view (green when selected), and used as tools on the solid. Surface features are ordered, suppressible and rebuilt with the part. They are not exported to STEP or drawn.

| Feature | Function |
|---|---|
| **Extract surface** | **Faces**: click the faces, of the solid or of surface bodies; **Offset**: copy moved along the normals by **Offset along the normals (mm)** |
| **Fit surface** | One clean surface fitted to the largest picked face (faces of the solid or of surface bodies) (**Surface type**: analytic within **Tolerance (mm)** else smooth spline, smooth spline, or original), extended beyond the face by **Extension beyond the face (fraction)** and moved by **Offset (mm)** |
| **Extruded surface**, **Revolved surface** | **Profile**: a sketch; **Extent**: **Type** curves extruded normal to the plane (**Depth (mm)**, negative against the normal; **Symmetric to the plane**), planar face of the closed sketch, or curves revolved (**Angle (deg)**, negative reverses the direction; **Axis**: sketch x axis, sketch y axis or a construction line). **Revolved surface** starts the same feature with the revolved type |
| **Loft surface** | Loft through one chain of curves per section (**Section n plane**, **Offset**, **Edit sketch n**, **Add section**); **Ruled** for straight segments between sections; **Smooth sections** (default on): the curves of a section that meet at less than **Corner angle (deg)** (default 15) are joined into one B-spline through their end points, so a section drawn as a polyline or as many short curves gives one smooth face instead of one face per segment; corners at or above the angle are kept (a rectangle stays four faces). Off: a polygon profile or smooth closed polyline (section 10.4) is lofted segment by segment. Also applied to curve bodies |
| **Bridge surface** | Ruled surface between two chains of edges. **Side A**, **Side B**: edges of the solid or of surface bodies (click; again to deselect; each side one connected chain) or curve bodies. Straight lines join the ends of side A to the nearer ends of side B (corner to corner) and the points between. **Flip** joins the ends of side A to the other ends of side B. The result is a surface body; **Sew surfaces** joins it to the neighbouring surfaces |
| **Fill surface** | **Boundary**: a closed loop made of edges of the solid, edges of surface bodies, sketch curves (click the sketch in the view or check it: all its lines, arcs and circles) and curve bodies (checked), in any combination; a loop of one edge (a circle, an ellipse) is accepted; a planar loop the fill rejects becomes a plane face; **Options**: **Tangent to the adjacent faces** of the solid |
| **Offset surface** | **Surface**: a surface body, or faces of the solid (clicked in the view; sewn into one surface), or with **Pick single faces of surface bodies** a portion of a surface body; **Distance (mm)** along the normals. Adjacent faces are extended or trimmed to meet at the offset; when that fails the faces are offset one by one (note in the tree) |
| **Sew surfaces** | Several surface bodies sewn into one shell within **Tolerance (mm)** |
| **Import surface** | The faces of a STEP file as one surface body: **STEP file path on this PC**, **Component** (STEP label of one component; empty: all faces of the file). A component that is one shell is used as that shell; other faces are sewn. The file is copied to `step_import/` when it is outside the project. **Generate STEP** of the Explicit deck generator (section 13.3.1) writes parts made of these features |
| **Thicken** | **Surface**: a surface body, faces of the solid, or with **Pick single faces of surface bodies** a portion of a surface body; **Thickness (mm)**, **Side** (along the normal, against it, both), **Result** added to the part, removed from the part, or a new cell. A surface that does not offset as a whole (a sewn shell with three faces at one edge, faces left out of the sewing, a degenerate face) is thickened shell by shell, then face by face, and the pieces are fused; the result line says so. At the seams the result is the union of the pieces. Faces that do not offset alone are listed with their centre and area |
| **Cut with surface** | The solid is split by the surface body and the cells on the **Keep** side are kept; the surface must pass through the solid completely |
| **Trim surface** | **Target**: the surface body to trim; **Tool**: a surface body, a curve body or a sketch (projected onto the target along its normal), the solid (click a face of it) or a plane (reference plane or plane feature); **Regions**: the pieces of the target cut by the tool are shown (blue; the target and the solid translucent), a click removes a piece (red), a second click keeps it; **Invert** swaps kept and removed, **Keep all** keeps every piece. The tool must cross the target completely. Mutual trimming of two surfaces is two Trim features |
| **Extend surface** | **Surface**: a surface body or a face of the solid; **Edges**: click the boundary edges to extend (edges of the surface only); **Extent**: **Distance (mm)**, **Extend** across the selected edges (the trim of the surface, holes included, is kept) or the whole boundary as an untrimmed patch (**Sides**: all four sides, the side nearest to a point, or chosen parameter sides umin, umax, vmin, vmax; inner trims are dropped), **Fit tolerance (mm)**. Across an edge the surface is continued on its own surface by the distance measured along the surface; strips on a plane, cylinder, cone, sphere or torus merge into the face, strips on a B-spline surface lie on its tangent extrapolation and stay separate faces of the shell |
| **Inspect body** | Topology report of the selected surface body, or of the solid when none is selected (also **Inspect** in the properties of a body). Lists in the panel: gaps (two free edges running together within **Gap tolerance (mm)**, default 0.1 mm, with the gap width), vertex gaps (free edge ends within the tolerance that are not shared), non-manifold edges (shared by more than two faces), the remaining free edges with their length, small faces below **Small face below (mm^2)** (default 0.01 mm^2) and short edges below **Short edge below (mm)** (default 0.01 mm). The summary gives faces, edges, vertices, area, free edge count and length, shells and closed shells, and the BRepCheck validity. All issues are drawn in the view (orange; **Show all in the view**); a click on an issue draws it red and centres the view on it. **Run again** repeats the report with the current tolerances |
| **Extract curve** | **Edges**: edges of the solid or of surface bodies (click mode **Edge**, **Tangent chain**, **All edges of a face**); **Clean**: none; the chain joined into one smooth spline within **Tolerance (mm)**; a line or circular arc within the tolerance, else a smooth spline. **Project onto surface** projects the curve onto a surface body along its normal |
| **Intersection curve** | **Surface**: a surface body, faces of the solid, or with **Pick single faces of surface bodies** a portion of a surface body; **With**: a second surface body, or the solid (click a face of it) |
| **Surface from curve** | A curve body extruded along a **Direction** by **Length (mm)** (**Symmetric**), or revolved about **Axis point** / **Axis direction** by **Angle** |

Curve bodies are drawn as purple lines. **Fill surface** and **Loft surface** take curve bodies instead of edges or sketches (check the curves in their panels), and **Sweep** takes a curve body as path.

Two other features take a surface body: **Partition** with **Method** **Surface body**, and **Replace faces** with **Clean surface** **A surface body (one face)**. The manual repair method is therefore: **Extract surface** or **Fit surface** of the dirty face (with an offset), then **Replace faces** with that body, or **Cut with surface** and **Thicken**.

### 10.10 FEA mesh export

**Export mesh** (Part and Assembly tabs) meshes the solid with gmsh and writes the mesh to **Folder**, or downloads it when **Folder** is empty. **Preview mesh** (Part tab) meshes without writing a file and shows the boundary mesh in the 3D view with a report: node and element counts by type, blocks (structured cells) of all cells, quality (SICN minimum and mean, elements below 0.2, inverted elements), and the technique of each cell.

| Field | Function |
|---|---|
| **Format** | Abaqus / CalculiX `.inp`, gmsh `.msh` (4.1), Nastran `.bdf`, I-DEAS `.unv`, VTK `.vtk`, MED `.med`, CGNS `.cgns` |
| **Elements** | **Hexahedra, structured**: every cell must be a block, or a prism (wedge elements C3D6 / C3D15); otherwise the cells that are not blocks are named and the mesh is refused. The element counts of **Hole mesh** features apply to the edges around the holes and to the edges opposite them; other edges get length / **Element size**. **Hexahedra in block cells, tetrahedra elsewhere**: the interfaces between a block and a free cell are not conforming (a tie is needed in the solver). **All hexahedra by subdivision**: a tetrahedral mesh subdivided into 4 hexahedra per tetrahedron. **Tetrahedra**. **Surface triangles**. **Surface quadrangles** |
| **Element size (mm)** | Target size (empty: bounding box diagonal / 20) |
| **Minimum size (mm)** | Lower limit for the size (empty: size / 5) |
| **Order** | 1: C3D8 / C3D4 / S4 / S3; 2: C3D20 / C3D10 / S8R / STRI65 |
| **3D algorithm** | Delaunay, Frontal, or HXT (parallel); for the tetrahedral cells |
| **Elements per 2π of curvature** | Size from curvature (0: off) |
| **Block corner angle limit (deg)** | A face corner above this angle does not count as a corner of a 4-sided face |
| **Geometry fixes at import (tolerance mm)** | gmsh healing of the geometry before meshing: degenerated and small edges, small faces, sewing; for imported geometry that fails to mesh. 0: off |
| **Sets per face and solid** | Abaqus `.inp`: one node set per face (`F1` .. `Fn`) and one element set per cell (`S1` .. `Sn`). Other formats: one physical group per face and per cell |
| **Optimise (Netgen)** | Tetrahedra quality optimisation |

The Abaqus file of a solid mesh contains the volume elements only; the faces are node sets. Parts are passed to gmsh as BREP so that the faces shared by partition cells stay shared and the mesh is conforming across cells. An assembly is meshed as placed; the components are separate solids with separate nodes. Meshing runs in a separate process and stops after 900 s.

### 10.11 Measure

**Measure** in the Part and Assembly tabs. The first click picks item A, the second item B; a third click starts a new measurement with A. The items are drawn green; the minimum distance is drawn as a green line between the closest points. The **Measure** panel (lower left in the Assembly tab, lower right in the Part tab) gives the picked items and the values (mm, deg, 4 decimals; the model units):

| Items | Values |
|---|---|
| One face | Planar face: normal, centre, area. Cylinder: Ø and R, axis direction, a point on the axis, length along the axis, area. Other face: centre, area |
| Any two | **Minimum distance** between the faces (OCC BRepExtrema; reference planes and axes as a 10 m plane or line), **Distance between the centres** with dx, dy, dz |
| Two planes | **Angle between the planes**; parallel: **Distance between the planes** |
| Two cylinders or axes | **Angle between the axes**, **Distance between the axes** (parallel) or **Shortest distance between the axes**; two cylinders: **Diameters**, parallel: **Axis distance minus both radii** |
| Plane and cylinder or axis | **Angle between the axis and the plane**; parallel: **Distance from the axis to the plane**, for a cylinder **Axis distance minus radius** |

The status line gives the minimum distance. The Part tab measures the solid of the full feature list.

## 11. Assembly

The **Assembly** tab places components and builds the assembly from them. The **File ▾** menu at the left of the toolbar holds the project header, **Assembly** (saved assemblies of the open project), **New**, **Save**, **Save as…**, **Rename…**, **Output folder**, **Export STEP**, **Export mesh** and **Make drawing**, as in the Part tab (section 10.7).

| Control | Function |
|---|---|
| **Add part** | Adds a component from a saved part of the project. The component follows later changes to the part |
| **Add STEP** | Adds a component from a STEP file by path. With several solids in the file: all solids as separate components (one component per solid, at the positions in the file), all solids as one component, or one solid. The file is read once for all its components |
| **Duplicate**, **Delete** | Copy or remove the selected component |
| **Undo**, **Redo** (Ctrl+Z, Ctrl+Y) | Undo or redo the last change of the components or mates: placements, solves, drags, mate edits, suppressing (60 steps; loading an assembly clears the history) |
| **Rotate** (R) | Rotate mode: a left drag sideways on a component that is not fixed rotates it, 0.5 deg per pixel (Shift: 15 deg steps). The axis is the one its active mates leave free: the normal of a mated plane, the axis of a concentric or axis mate (pivot on that axis), the other normal of an angle mate; with no mates, the view direction through the component centre. A point mate sets the pivot. When the mates hold the component against rotation and it is mated to other components, the solver turns it with the chain it is mated in (target: the rotation about the view direction through the component centre), live while dragging and on release; the status line names the components that followed. In a group of mated components without a fixed component, the whole group rotates about the view direction through its centre when the mates hold the component against rotation, when the component has no mate axis, or with Ctrl+drag. The rotation is added to **Position** and **Rotation** on release. R or Esc ends the mode |
| **Box select** | Box select mode: a left drag from left to right selects the components entirely inside the box (blue box), from right to left the components the box touches (green dashed box). Ctrl + left drag draws a box at any time and adds to the selection; Ctrl + click (3D view or component list) adds or removes one component; a click on empty space or Esc clears the selection. The selected components are tinted orange. With several selected: Space hides them, **Delete** deletes them, and the component menu (right click on a selected component) offers **Hide**, **Show only**, **Fix** and **Unfix** for the selection |
| **Show all**, **Invert** | **Show all** (Shift+Space) shows all components. **Invert** (Ctrl+Space) shows the hidden components and hides the shown ones; with no component hidden it does nothing (status message) |
| Space | Hides the component under the cursor; with the cursor off the components, hides or shows the selected component. Shift+Space shows all components. The visibility is the check box in the component list |
| **Drag** (D) | Drag mode: a left drag on a component that is not fixed moves it in the screen plane; Shift+drag moves it along the global axis X, Y or Z with the largest movement. A mated component moves only in the directions its active mates leave free: coincident or distance of planes in the plane, concentric or coincident axes along the axis; a **Point** mate or three independent conditions hold it relative to its mated components. Conditions whose directions are within about 3° of each other count once, so redundant or nearly parallel mates do not lock the component. In a group of mated components without a fixed component, the preview moves the whole group in the held directions. A component held against its mated components in all directions follows the cursor in the preview. A component with mates is pulled through the solver while dragging (the mates the last solve left out are not solved again during the drag) (about every 0.3 s) and on release: the grabbed point follows the cursor movement as far as the fixed components and the mates allow, and the mated components that are not fixed follow (for example a cam held in a sliding jaw moves the jaw along its guide; a part that can only turn about its axis turns like a lever). Translations are preferred to rotations. The status line gives the distance and the number of components moved, or that the component is held. A component without mates: the movement is added to **Position** on release. A fixed component is not moved (cursor and status line say why). A drag that starts on a component never rotates the view; a left drag on empty space rotates it. D, Esc or the button ends the mode |
| Component list | Check box: visible; colour swatch; ▲ ▼: order. A click selects; a click in the 3D view selects the component under the cursor |
| Component menu | Right click on a component in the list or in the 3D view (without dragging). The browser menu is not shown over the 3D views, the sketch and drawing areas and the program menus. **Fix in space** / **Unfix** sets **Fixed (not moved by mates)**. **Show only … and the components mated to it** hides all other components. **Show only the connected components** also keeps the components connected through other components; the chain is not continued through a fixed component (the fixed component itself is shown). **Show all components** shows them again (also Shift+Space, **Show all**; **Invert** swaps). **Open part … in the Part tab** opens the saved part of the component; for a STEP component, **Open in the Part tab** creates a new part (not saved) with an **Import STEP** feature for the solid of the component. **Show linked mates (N)** lists only the mates of the component in **Mates** (**Show all** returns the full list) and marks their faces blue in the view; the mates are also listed in the menu, and a click selects the mate (faces orange) |
| 3D view | Left drag rotates about the centre of rotation without limit, middle or right drag pans, the wheel zooms about the cursor, a middle click on a component sets the centre of rotation; **Iso**, **Front**, **Top**, **Right**, **Fit** and the navigation cube as in the Part tab |
| **Position (mm)** | Translation of the component |
| **Rotation (deg)** | Rotations about the fixed X, then Y, then Z axis, about the component origin, applied before the translation |
| **Explode offset (mm)** | Extra translation used when **Exploded** is checked |
| **Colour**, **Density** | Display colour (shown while the colour picker is open; with several components selected, all get the colour); density for the mass (empty: **Density** from **Views**). Selected components keep their colour with a faint orange glow and orange edges |
| **Display** | **Shaded** (default); **Transparent**: faces see-through with edges; **Hidden lines removed**: the visible edges only; **Wireframe**: all edges. Combines with **Section** (the cut faces are drawn in **Shaded** only) |
| **Edges**, **Axes** | Edges of the components; coordinate system at the origin |
| **Exploded** | Shows, exports and draws the components at their explode offsets |
| **Section**, X / Y / Z, slider, **Reverse** | Cross-section of the 3D view: the components are cut by a plane normal to X, Y or Z; the slider sets its position within the assembly extents (tooltip: the coordinate in mm). The part below the plane is kept (**Reverse**: above); the cut surfaces show the inside faces in a darker colour. Clicks pick only the kept part. The section is a view setting; exports and drawings are unchanged |
| **Mates** | Opens or closes the mates window over the 3D view (top left): the list of mates and the editor of the selected mate. The mate type buttons and the linked mates of a component (component menu) open it; × closes it |
| **Coincident**, **Distance**, **Parallel**, **Angle**, **Concentric**, **Point** | Adds a mate of that type and starts the picking of its sides (section 11.1) |
| **Solve** | Solves the mates |
| **Check** | Mate check (section 11.2): solves, then marks each mate and gives the motions each component has left |
| **Measure** | Measure mode (section 10.11). Click a face of a component (with **Datums**: also a reference plane or axis while measuring), then a second one. Esc or × ends; Drag, Rotate and the mate buttons end it |
| **Interference check** | After each build, the overlapping volume of every pair of components (mm^3) |
| **Mass** | Volume and mass per component, total, and centre of mass. Collapsed below **Properties**; a click on **Mass** opens it |
| **Save** (**File ▾**) | Writes `<Name>.asm.json` to the project `work/` folder (no project open: `assemblies/`) |
| **Export STEP** | STEP file with one product per component, named after the components |
| **Export mesh** | FEA mesh of the assembly (section 10.10) |
| **Material** | Material text of the component for the parts list |
| **Parts list** | Shows the parts list above the title block of the assembly drawing: Item, Qty, Name, Material, Mass. The check box is the default of **Make drawing** and shows or hides the list on the existing drawing of the assembly at once (stored in the drawing layout); the Drawings tab has the same check box for an assembly drawing. Components with the same source and material are one item; a trailing number in the name is dropped |
| **Fixed (not moved by mates)** | The component keeps its placement when the mates are solved. In a group of mated components without a fixed one, the first component of the group in the list keeps its placement |
| **Make drawing** | Adds the assembly to **Models** as `<Name>.asm` (one solid per component), sets **Mode** to **One drawing per file** and makes the drawing. With **Exploded** checked, the components are drawn at their explode offsets with chain lines (trails) from the assembled to the exploded position |

Hidden components are left out of the mass, the interference check, the STEP file and the drawing.

The server keeps the shape, the 3D view mesh, the face references and the volume properties of each component source between builds, keyed by the source and its files (content of the part file and of the STEP files it imports, modification time and size of a STEP file). A build of an assembly whose sources are unchanged places the cached meshes with the component transforms and computes the mass from the cached volume and centre of mass; nothing is rebuilt or tessellated. The browser keeps the meshes and receives only those it does not hold. Components with the same source share one mesh. **Interference check** places the solids and intersects them on each build.
The view data of each source (mesh, face references, planes and axes, volume, centre of mass) is also written to `%LOCALAPPDATA%\drawgen\viewcache\<key>.json.gz` (the 500 newest are kept). After a server start, unchanged sources are read from there and their STEP or part files are loaded only for **Interference check**, **Export STEP**, **Export mesh** and **Make drawing**. Deleting the folder clears the cache.
Geometry work for assemblies runs in a pool of worker processes, one per processor core less one, at most 5 (environment variable `DRAWGEN_WORKERS` sets the number; 1 switches the pool off). The pool is shared with the drawing views and is started with the server. Sources that are not in the view cache are computed in the workers in parallel: a STEP file used by several components is read once by one worker, which writes its solids to the cache as BRep files (`<key>.brep`), and the solids are then meshed in all workers. **Interference check** splits the pairs of components whose boxes overlap over the workers. Later loads of a STEP component (interference, export, drawing) read its BRep file instead of the STEP file. The server answers other requests while the workers run.
The mate solver computes the Jacobian per component (a component's parameters change only the residuals of its own mates) and solves with numpy.

The views of an assembly drawing are projected from the fused solids, so faces inside other components (a pin in a hole) are not drawn. In the section view each component is hatched with its own direction and spacing (ISO 128-50): 45°, 135°, then the same with 1.5 and 2 times the spacing.

### 11.1 Mates

A mate type button (**Coincident**, **Distance**, **Parallel**, **Angle**, **Concentric**, **Point**) adds a mate of that type, opens the mates window over the 3D view with it, shows what to click in the status bar and starts the picking (it ends drag mode and the mate filter): a click in the 3D view on a face of one component (A), then of another component (B); the component lists below the sides are not needed. With **Datums** checked, while a side is picked, the reference axes of all components and the reference planes of the last component under the cursor are shown (purple) and can be picked: an axis within 6 px of its line, a plane where no part is under the cursor. Without **Datums**, reference planes and axes are chosen in the lists below the sides. The status bar names the face, plane or axis under the cursor. The cursor is a crosshair over a face, plane or axis that can be picked and a no-entry symbol over a face that is not planar or cylindrical. While a side is picked, a click picks also in Drag or Rotate mode; **Pick** and an empty **Component** list end drag mode. A selected mate with an empty side takes the next click for that side. **Pick** next to A or B repeats the pick for that side. Esc ends the picking. **Solve** moves the components that are not fixed until the mates are satisfied. The mates panel lists the mates with the two components below each; the check box suppresses a mate, × deletes it. **Isolate** in the head of the mates window shows only the components of the selected mate (with a mate filter: the component and the components mated to it); the other components are drawn faint and cannot be picked.

| Type | Faces | Function |
|---|---|---|
| **Coincident (faces)** | planes, or a plane and a cylinder axis | The faces lie in the same plane, facing each other |
| **Distance (faces)** | planes, or a plane and a cylinder axis | Parallel faces at **Distance (mm)**, measured along the normal of A |
| **Parallel (faces)** | planes or cylinders | Parallel normals or axes, no position condition |
| **Angle (faces)** | planes or cylinders | **Angle (deg)** between the normals or axes |
| **Concentric (cylinders)** | two cylinders | Common axis, axis directions opposite (**Flip**: the same direction). **Flip** turns the component end for end |
| **Point (face centres)** | any | The centres of the two faces coincide |

Each side (A, B) of a mate is a face picked in the 3D view (**Pick**) or a reference plane or axis of a component: **Component** and **Plane or axis** below the side. The list holds **Plane XY**, **Plane XZ**, **Plane YZ** and **Axis X**, **Axis Y**, **Axis Z** of the component (through its origin, in its own coordinates), **Centre plane XY**, **Centre plane XZ**, **Centre plane YZ** and **Centre axis X**, **Centre axis Y**, **Centre axis Z** (the same directions through the centre of the bounding box of the component, in its own coordinates) and the **Plane** and **Axis** features of a part. Two components mated centre plane to centre plane (**Coincident**) are centred on each other in that direction. The planes and axes of the selected mate are drawn orange; **Datums** in the toolbar draws those of the selected component (purple).

| Mate | With a reference axis |
|---|---|
| **Coincident** | Axis and plane: the axis lies in the plane. Axis and axis or cylinder: collinear, directions opposite (**Flip**: the same) |
| **Distance** | Axis and plane: the axis parallel to the plane at **Distance (mm)**. Axis and axis or cylinder: parallel at **Distance (mm)** |
| **Parallel** | Axis and plane: the axis parallel to the plane. Axis and axis or cylinder: parallel |
| **Concentric** | Axis or cylinder with axis or cylinder: common axis |

A reference plane mates as a planar face.

**Flip (same direction instead of facing)** reverses the direction of face B. When both sides of a coincident, distance, parallel or concentric mate are picked, **Flip** is set to the direction the components already have, so the solve turns them the least: planar faces of solids in a coincident or distance mate stay facing (the faces touch); concentric mates and reference planes and axes take the current direction. A **Flip** set by hand is kept. When the solve cannot satisfy a mate together with the mates before it, the mate is tried with **Flip** changed; when that works, **Flip** stays changed and the status line names the mate ("n mates flipped"); otherwise the mate is left out. **Min** and **Max** on a distance or angle mate add a slider that sets the value and solves on each change.

The solver is Gauss-Newton with a minimum-norm step. The solve ends when the largest residual is below 1e-7, or when it improves by less than 2 % over 4 iterations while below 0.0001 mm, or over 8 iterations at any size (mates that cannot all be satisfied) (imported models are rarely exact: a bore 0.001 rad off its slide leaves a small residual that does not go to zero). Each group of components connected by mates is solved on its own. When the mates of a group cannot all be satisfied, the newest mate and the two mates with the largest errors are each tried with **Flip** changed, then left out, in a solve of the whole group; the first that works is kept (flipped, or left out as a conflict). Otherwise the group is solved again from its starting placement adding one mate at a time, from the fixed components outwards in the order of the mate list: a mate that cannot be satisfied together with the mates before it is tried with **Flip** changed, then left out (tag "left out" in the mates list, status message "n mates left out"), and the other mates of the group are satisfied. Components that are not fixed and not in any mate keep their placement. The solved placement is written to **Position** and **Rotation**. A mate is not satisfied when its position error exceeds 0.01 mm or its direction error exceeds 0.1 deg. "n mates not satisfied" in the status line lists the three largest with components, type and error; the unsatisfied mates are red in the mates list, with the error as tooltip. Causes: conflicting mates, or a face reference lost after a part was rebuilt. Mates refer to faces by index into the component's face list; a change of the face count of a part changes the references.

### 11.2 Mate check

**Check** solves the mates (conflicting mates left out), opens the mates window and shows a summary above the mate list: the number of mates in conflict, not satisfied, redundant, skipped and suppressed, the number of components with free motion and the degrees of freedom of the assembly.

| Mate tag | Meaning |
|---|---|
| **conflict** | Cannot be satisfied together with the mates solved before it; left out of the solve |
| **not satisfied** | Error above 0.01 mm or 0.1 deg (tooltip: the error) |
| **redundant** | Adds no condition to the mates before it in the list |
| **skipped** | A side is not picked, its component was deleted, or its face reference is lost |

The tooltip of a mate without a tag gives the number of conditions it adds. Below each component in the component list: **fixed**, **no mates**, **held**, or **free:** with the translations and rotations its mates leave free while the other components are held. The counts come from the rank of the Jacobian of the mate residuals at the solved placement. **Suppress n conflicting** suppresses the mates in conflict and checks again; **Close check** hides the results. Any change of the components or mates hides them.

Parts list: in the **Drawings** tab, the **Parts list** check box (assembly drawings only) shows or hides the parts list of the drawing.

Balloons: in the **Drawings** tab, **Auto balloons** places one balloon per component of an assembly drawing, numbered as the parts list, around the front view (or the first view present). The **Balloon** tool (B) places a balloon by hand: point on the part, then the balloon position, then the item number. Balloons are dragged like notes; the number is edited in **Text**.
The 3D view controls are those of the **Part** tab.

## 12. Analysis

The **Analysis** tab runs a linear static analysis with CalculiX (`ccx`, version 2.21). The model holds the bodies of a saved assembly or part, plates, beams, rods and fasteners. Plates and members are defined in the tab; a model of members and plates needs no geometry. The CalculiX input file, the result files and a text report are written to `analysis/<Name>/` of the project.

Units: mm, N, s, t (tonne): stress and pressure MPa (N/mm^2), moment N mm, line load N/mm, acceleration mm/s^2. Densities are entered in kg/m^3 (converted to t/mm^3).

The panel at the right is 480 px wide; the bar at its left edge changes the width (kept in the browser).

### 12.1 Solver

**Solver (ccx)** under **Settings** is the path of the CalculiX executable (written to `config.json` > `ccx_path`). When it is empty, the program uses `ccx` on PATH, or `ccx_static.exe` / `ccx_dynamic.exe` of a PrePoMax installation under `Program Files`, `%LOCALAPPDATA%` or the user folder (`Desktop\PrePoMax`, `Downloads\PrePoMax`). The line below the field gives the executable in use. `OMP_NUM_THREADS` and `CCX_NPROC_STIFFNESS` are set to the number of processor cores.

### 12.2 Controls

| Control | Function |
|---|---|
| **File ▾** | Project header, **Analysis** (saved analyses of the open project), **New**, **Save**, **Save as…**, **Rename…**, **Open run folder** (`analysis/<Name>/`), **Write input file** (mesh and `job.inp` without solving) |
| **Geometry** | Saved assembly or part of the project, or **(none: members and plates)**. A part is one body. The analysis uses the saved file of the assembly. The sketches of a part that no feature of the part uses are drawn (purple lines and points); a part with sketches only is not a body. Member ends and plate points snap to the sketch points (section 12.4) |
| **Mesh** | Meshes the bodies, writes `job.inp` and shows the mesh. The status line gives the node and element counts and the element types per body. **Edges** draws the element edges (quadrangle faces of hexahedra without diagonals) |
| **Solve** | Meshes, writes `job.inp`, runs CalculiX and shows the results. The status line gives the stage and the time |
| **Stop** | Stops the solver |
| **Beam**, **Rod** | Adds a member: pick end A, then end B in the view (section 12.4). The member gets the section, material, group, up vector, elements and hinges of the selected member of the same kind, else of the last one. After end B the next member starts with the same properties; Esc (or another toolbar command) ends the drawing and removes the member without ends. Esc on the first member keeps it for typed coordinates. **Sketch beams** uses the same properties |
| **Sketch beams** | Adds a beam on each straight line of the sketches of the geometry. Lines that already have a member are skipped. Members meeting at a point share the node |
| **Plate on face**, **Plate by points** | Adds a plate (section 12.5) |
| **Fastener** | Adds a fastener (section 12.6) |
| **Ref. point** | Adds a reference point (section 12.6.1): click the faces to connect (the first face sets the point at its centre); Esc ends the face picking |
| **Support** | Adds a support at the selected member end or reference point; with no member end selected, starts the pick of a face or a member end (section 12.7) |
| **Load** | Adds a force at the selected member end; with no member end selected, starts the pick of a face, a member end (force at the end) or a member (line load, 1 N/mm downwards) (section 12.8) |
| **Show** | **Model** (bodies, members, fasteners, supports and loads), **Mesh**, **Results** |
| **Result** | **von Mises stress**, **Displacement \|u\|**, **ux**, **uy**, **uz** as contours on the deformed shape, with the colour scale (12 bands) in the upper left of the view |
| **State** | **Total**; with a fastener preload also **Step 1 preload** and **Step 2 loads** |
| **Scale** | Deformation scale (empty: the largest displacement is drawn as 5 % of the model size) |
| **Undeformed** | Outline of the undeformed mesh |
| **Iso**, **Front**, **Top**, **Right**, **Fit**, **Edges**, **Axes** | As in the Assembly tab |

A click on a member, fastener, support or load in the 3D view selects it in the panel. A click within 10 px of a member end selects the end: the end is drawn as a large orange ball and **Members** shows its coordinates. A click on empty space clears the selection. The member end, point or face under the cursor is marked orange before a click (cursor: pointer for selection, crosshair during a pick). Esc cancels a pick.

### 12.3 Model

| Panel | Function |
|---|---|
| **Settings** | **Solver (ccx)**; **Default material**; **Mesh** (section 12.3.1); **Bonded contact between touching bodies**: touching solid bodies of one mesh strategy are meshed with shared nodes at the contact faces (gmsh fragment); plates and bodies of other strategies are tied (`*TIE`) to the faces they touch. Without it the bodies are connected only by members and fasteners |
| **Materials** | Name, E (MPa), nu, rho (kg/m^3). **Add material**, × deletes |
| **Bodies** | One row per component of the geometry: **Model** **solid** (meshed with the strategy in **Mesh**), **plate** (C3D8I through the thickness, C3D6 for the triangles left by the quadrangle mesh) or **off** (left out); **Mesh**: the strategy of the body (**tet**, **hex**, **hex sub**; in brackets: the default of **Settings**); **Material**; **Size (mm)** of the elements of the body |

#### 12.3.1 Mesh settings

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

### 12.4 Members

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

### 12.5 Plates

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

### 12.6 Fasteners

A fastener is a U1 beam of diameter **d** (ROUND section) between face A and face B, on the axis of the first cylindrical face of the two (without a cylindrical face: the line between the face centres). Each end is connected to its face by RBE3 equations. Supported nodes of a face are left out of its equations.

| Field | Function |
|---|---|
| **d (mm)** | Diameter of the section. Default: the smaller hole diameter of the picked faces |
| **Preload (N)** | Axial force. The fastener is cut at mid-length: the axial displacement across the cut is a degree of freedom of an extra node (spring 1e-6 N/mm to ground); the other translations and the rotations are tied across the cut. Step 1 applies the preload as a force on this degree of freedom, without the loads. Step 2 applies the loads with this degree of freedom fixed (fastener length held). **Total** is the sum of both steps |
| **Material** | Material of the fastener |

The preload needs a load path between the clamped parts (bonded contact or another connection). Without one, the solve stops with "the preload has no reaction path".

#### 12.6.1 Reference points

A reference point is a point rigidly connected to faces of the bodies and plates (CalculiX `*RIGID BODY`: the connected face nodes move as a rigid body with the point). It is drawn as a violet ball with dashed lines to the centres of its faces.

| Field | Function |
|---|---|
| **Name** | |
| **Point (mm)** | Coordinates; **Pick**: a point on a face or a member end; **Centre**: the centre of the clicked face |
| **Rigidly connected faces** | **Add faces**: click faces (Esc ends); **Clear faces** |

Supports and loads act on a reference point: select it (in the list or the view) and press **Support** or **Load**, pick it with **Pick** (within 10 px), or choose it under **or reference point**. Supports take six components (ux, uy, uz, rx, ry, rz); loads are a force (N) or a moment (N mm). A member end at the point follows the point (translations, and rotations at a beam end). Supported face nodes and nodes already constrained are left out of the rigid connection (a warning in the report). The results list the displacement and rotation (rad) of each reference point.

### 12.7 Supports

| Target | Type |
|---|---|
| Face | **fixed**: ux, uy, uz of all face nodes. **normal to the face (planar)**: displacement normal to the face (`*TRANSFORM`), 0 or **Normal displacement (mm, along the outward normal)**. **chosen components**: ux, uy, uz, rx, ry, rz as checked. **prescribed displacement**: the checked components prescribed (mm, rad), the others free. With rx, ry or rz checked the face is rigidly coupled (kinematic coupling) to a node at its weighted centre, which carries all checked components; the face then stays rigid |
| Reference point | As a member end: **fixed** (all six), **pinned**, **chosen components**, **prescribed displacement** (section 12.6.1) |
| Member end | **fixed**: all six. **pinned**: ux, uy, uz. **chosen components**: as checked. **prescribed displacement**: the checked components of ux, uy, uz (mm) and rx, ry, rz (rad). At a rod-only node the rotations are left out |

Prescribed displacements act in the load step; with a fastener preload step they are 0 in the preload step. The reaction of a support is the force needed to hold or move its nodes.

**Pick** in the support panel takes a face or a member end. A supported member end cannot also be connected to a face.

### 12.8 Loads

| Type | Value |
|---|---|
| **Force on a face** | Total force (N, global x y z), distributed over the face nodes by area (consistent loads: mid-side nodes of the 6-node triangles) |
| **Pressure on a face** | MPa, positive into the face; per element face along its normal |
| **Moment on a face** | N mm about the weighted face centre, distributed as nodal forces by area (the RBE3 distribution) |
| **Force at a member end**, **Moment at a member end** | N, N mm (global) at the end node. A moment needs a beam end |
| **Line load on a member** | N/mm (global) along the whole member |
| **Gravity** | Acceleration (mm/s^2), for example (0, 0, -9810). Bodies: consistent nodal loads of the element weights (C3D10: corner nodes -1/20, mid-side nodes 1/5 of the element weight). Members: line load rho A g. Fasteners: none |

**Pick** in the load panel takes a face, a member end or a member and sets the type to match (pressure: a face only).

### 12.9 Results

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

## 13. Explicit

The **Explicit** tab builds OpenRadioss decks from an Abaqus .inp, runs them on this PC or on a Linux server, and shows the results.
The deck build, the run folders, the solver control and the post-processing are the ORC\*\*3 v1.0 code (OpenRadioss CalculiX Converter and Control) in `drawgen/explicit/`.
`inp2rad.py` (Altair Engineering, MIT licence) converts the .inp to the starter deck.
The .inp comes from the ShinyCAD geometry (section 13.3), from the deck generator (section 13.3.1) or from PrePoMax.

Units: mm, t, s, N, MPa; density in t/mm^3 in the .inp and the decks, in kg/m^3 in the **Materials** table; velocity in mm/s; energy in mJ.

### 13.1 Executables and settings of this PC

| Program | Use |
|---|---|
| OpenRadioss for Windows: `starter_win64`, `engine_win64`, `anim_to_vtk_win64`, `th_to_csv_win64` | Local runs. Taken from **OpenRadioss exec folder** (Solve panel), or from PATH when the field is empty |
| `ssh`, `scp` (OpenSSH of Windows) | Remote runs. Task-spooler (`tsp`) and OpenRadioss (`starter_linux64_gf`, `engine_linux64_gf`, `anim_to_vtk_linux64_gf`, `th_to_csv_linux64_gf`) on the server |
| ParaView `pvbatch.exe`, `paraview.exe` | **Extract Strains**, **PV Images**, **Open in ParaView**. Empty fields: searched in `C:\Program Files\ParaView*`, `Documents\ParaView*` and `C:\ParaView*` |
| matplotlib (optional, not installed by `start.bat`) | `<job>_KE.png` in the build folder |

With **OpenRadioss exec folder** set, the local solver processes get the exec folder and the existing folders `extlib\hm_reader\win64`, `extlib\h3d\lib\win64` and `extlib\intelOneAPI_runtime\win64` of the OpenRadioss folder (the parent of the exec folder) on PATH, `RAD_CFG_PATH` = `<OpenRadioss folder>\hm_cfg_files`, `RAD_H3D_PATH` and `KMP_STACKSIZE` = `OMP_STACKSIZE` = 400m, where these are not set.
The line below the fields in the Solve panel gives the executables found.

The fields **Env**, **Threads**, **OpenRadioss exec folder**, **Server (user@host)**, **SSH Port**, **Env script**, **Exec dir**, **Scratch dir**, **Share map**, **pvbatch** and **paraview** are settings of this PC and are written to `config.json` > `explicit`.
When `config.json` has no `explicit` entry, they are read from the ORC\*\*3 configuration `%APPDATA%\ORC3\workspace_config.json` when it exists.
All other fields are stored in the explicit document.

### 13.2 Documents and folders

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

### 13.3 Model

| Control | Function |
|---|---|
| **Source** | **ShinyCAD geometry (assembly or part)**: the saved assembly or part chosen in **Geometry** (toolbar). **Deck generator (stiffened panel, shells)**: section 13.3.1. **External .inp (PrePoMax)**: the meshed .inp in the **.inp** field |
| **.inp**, **…**, **Show mesh** | External .inp: path; **Show mesh** draws the nodes and elements (*NODE, *ELEMENT; solids C3D4, C3D10, C3D8, C3D8R, C3D8I, C3D20, C3D6, C3D15; shells S3, S4, S4R, S8R, R3D3, R3D4, M3D3, M3D4) with one colour per ELSET |
| **Materials** | **Name**, **Library** (an entry of the ORC\*\*3 material library, or **(elastic: E, nu, rho)**), **E (MPa)**, **nu**, **rho (kg/m^3)**; **Add material**, × deletes; **Default**: material of the bodies without one |
| **Bodies** | One row per component: **Role** **deformable**, **rigid (impactor)** or **off**; **Material**; **Size (mm)** element size of the body (empty: **Element size**); **Mesh** strategy of the body |
| **Mesh** | **Element size (mm)** (empty: bounding box diagonal / 20), **Minimum size (mm)** (empty: element size / 5), **Strategy** (**Tetrahedra (free)**, **Hexahedra, structured (block cells)**, **Hexahedra by subdivision**; section 12.3.1), **Tetrahedra** C3D4 or C3D10, **Hexahedra** C3D8R or C3D8, **Elements per 360 deg** (empty: 12), **Bonded: touching deformable bodies share nodes** |
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

#### 13.3.1 Deck generator

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

### 13.4 Runs

| Control | Function |
|---|---|
| Path, **Open folder** | `explicit/<Name>` of the document |
| **Description**, **Notes**, **New run** | Creates `runs/<date>_r<NNN>_<description>/` (NNN: the highest number in `runs/` plus one) with `run.json` and a copy of the source .inp in `model/`, and selects it |
| Run list | **(no run: decks next to the .inp)** and the run folders, newest first, with the number of builds and decks. A click selects the run: **Output Dir** of the build, and the newest deck becomes **Target .rad**. **Decks** lists the decks of the selected run; a click sets **Target .rad** |
| **Open** | Opens the run folder on this PC |
| **Clean…** | Lists the regenerable solver output of the run and its build folders (A-files, T-files, `.vtk`, `.vtk.series`, `.rst`, `_extract_principal_strain.py`) with the number of files per folder and the size in MB, and deletes them after confirmation. Decks, `model/`, `run.json`, CSV and PNG files are kept |
| **Settings** | Restores the Build and Solve settings of the last build of the run from `run.json`; paths are kept |

### 13.5 Build

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

### 13.6 Solve

| Control | Function |
|---|---|
| **Target .rad**, decks… | Starter deck `<job>_0000.rad` to run; decks… lists the decks of the selected run |
| **Env** | **Local** (this PC) or **Remote (Linux)** |
| **Threads** | Engine threads (`-nt`) |
| **Stream remote output** | Follows the remote job to the end (status, copy-back, post-processing); required for SCP transfer |
| **Plot KE**, **Extract Strains**, **PV Images** | Post-processing after a run: KE curve and PNG; principal strain summary (pvbatch); PNG renders (pvbatch) |
| **OpenRadioss exec folder** | Local executables (section 13.1) |
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

### 13.7 Results

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

### 13.8 Console

The console lists the messages of the build, the solver output and the post-processing.
**find** filters the lines, **Clear** empties the console, **Follow** scrolls to the newest line.
The strip at the bottom of the 3D view shows the running build, runs and post-processing commands and the newest console line.
The server keeps the last 20000 lines; the page shows the last 6000.

## 14. Tests

`run_tests.bat` runs the automatic tests in `tests\` with pytest in the program's Python environment (created by `start.bat`). The first run installs pytest, pyflakes and Playwright with its Chromium browser (`tests\requirements-test.txt`, about 150 MB). `run_tests.bat fast` leaves out the browser tests; other arguments are passed to pytest (`run_tests.bat -k mate`).
The tests use a copy of `config.json`, a projects folder and a view cache in a temporary folder (environment variables `DRAWGEN_CONFIG` and `LOCALAPPDATA`); `config.json`, the projects and `%LOCALAPPDATA%\drawgen` of the PC are not changed.

| File | Content |
|---|---|
| `tests/conftest.py` | Temporary configuration and project, test client, server on a free port, helpers for test parts |
| `tests/test_static.py` | Python and JS syntax, undefined names (pyflakes), element ids used in the JS present in `index.html`, names used across modules, names that `sketch.js` assigns to `window` not defined again in the other scripts |
| `tests/test_units.py` | ISO 286 limits (grades IT1 to IT18, sizes to 3150 mm, letters a, b, c, u, fits), deviation text in µm, inch drawing text (dimensions, deviations, hole callouts, title block Units), ISO 965 thread limits (6g, 6H), trapezoidal profile, mate solver (concentric with **Flip**, coincident, reference axes, incomplete and conflicting mates), view meshes |
| `tests/test_models.py` | Point, axis and plane features from vertex coordinates; part rebuild with the volume computed by hand: extrude, cut, revolve, fillet, chamfer, hole, pattern, shell, **Remove faces**, **Offset faces** (top face, hole face, faces of a slot with a round top), **Move faces** (planar face, hole moved, flat top of a slot with tangent round corners moved up), **Partition**, suppressed and failed features; **Place** with planar and cylindrical faces; failed fillet with the failing edges and the largest radius; loft with smooth sections; bridge surface between edges of two surface bodies (area, Flip); thicken of a sewn shell face by face; plane and point at the end of a sketch curve |
| `tests/test_api.py` | Server requests: projects and documents (rename, copy, version, delete, states), part build, STEP export and read back, drawing preview, options (inch dimension text in the preview, invalid values refused), snap points of a sketch on a drawing, PDF / DXF / SVG export (sheet size, layers, entities), annotations, sketches on drawings (view map, layers, background without the edited sketch), sketch DXF export, assembly build, view cache, mates on reference planes and axes, interference, STEP export, components from a STEP file and their listing in **Documents**; parallel saves of one file |
| `tests/test_hole_mesh.py` | **Hole mesh**: blocks and prisms for a through hole, two holes, a blind and a counterbored hole, a hole near the edge; holes too close; structured mesh with only C3D8 (and C3D6 below a blind hole), shared nodes, 24 nodes on the hole circle for 3 elements per 45 deg, 4 elements through the thickness |
| `tests/test_analysis.py` | Analysis against hand calculations: section properties, member axes, cantilever (tip deflection P L^3 / 3 E I, root moment and reaction), simply supported beam under a line load (5 q L^4 / 384 E I, q L^2 / 8), two-rod truss, portal frame with a hinged beam (equilibrium, q L^2 / 8), bonded blocks with a preloaded fastener (preload force, sum of the steps, weight, equilibrium), preload without a load path refused, plate tied to a block with a beam on the plate (pressure total, moment, reactions); plate items: solid from points (position, normal, errors), cantilever plate between beam and plate theory, T-joint of two plates with a post connected within a radius, deck plate on four columns without geometry (weight, equilibrium); API: save, mesh, solve, saved results, report, document links; cantilever block with tetrahedra (C3D10, C3D4), structured hexahedra (C3D8I, C3D8, C3D20R) and hexahedra by subdivision (tip deflection within 6 %); prescribed displacement and normal support with a value on a hexahedral block tied to a tetrahedral block (reactions); member section from its group; member stresses in the view data; triangular plate tied to the beams along its edges; plate group resolution; reference point rigidly connected to a block end (reaction force and moment, point displacement and rotation, report), face support with rotations (guided cantilever moment P L / 2), beam end at a reference point and beam end with a rigid face coupling (moment transfer, face stays plane). Skipped without `ccx` |
| `tests/test_explicit.py` | Explicit tab with `tests/fake_openradioss.py` in place of the OpenRadioss executables: mesh view data of solids and shells, .inp and ASCII and BINARY VTK reading, max principal strain; settings of ORC\*\*3 snapshots, executables and environment, remote paths; deck build of a shell model (library material, /FAIL/TENSSTRAIN with SoftBand, *TIE ties, normal healing, Istrain, TYPE7 Idel, /INIVEL on the /RBODY main node, engine deck, build numbers); BUILD HALTED on a CAD file; .inp of the ShinyCAD geometry (roles, rigid body reference node at the centre of mass, supports); deck generator: .inp equal in nodes, elements, element sets and sections to `deck_mesh.py`, element type, edge supports, parameter table, z = 0 area equal to the panel area, check errors (coincident beams, position outside the panel, zero thickness) and warnings, deck build (/PROP/SHELL thicknesses, /BCS), **Generate STEP** and the part with **Import surface** bodies (z = 0 area), second **Generate STEP** keeping other features; run folder, build, starter only with the Min dt offer, run, status board, run history, results, frames, eroded elements, salvage, clean, run settings, killed engine, queue; explicit documents in **Documents**, rename of the geometry and of the document |
| `tests/test_pool.py` | Worker processes: view data and interference equal to the values computed in the server |
| `tests/test_browser.py` | The interface in headless Chromium: all tabs; **Title block editor** window (opened from the Drawings toolbar and the drawing settings panel, filled from the saved configuration, preview, save, Close, Esc); sketch, extrude and save in the Part tab; **File ▾** load and **Make drawing** (opens **Drawings**); **Sketch** tool on a front view, line typed in view coordinates, **Finish sketch**; **Hole mesh** command; **Remove faces** pick by a click without **Pick faces**; hover text Ø and length of edges; **Point** coordinates from a vertex click; **Partition** face click in **Method**; assembly **Add part**, **Drag**, **Fix in space**, mate on reference planes, mate sides by clicking faces and a reference axis; drag of a mated component in its free plane; a drag on a fixed component leaves the view unchanged; Space hides a component, Shift+Space shows all; mate type buttons (**Coincident**, **Concentric**) in a long mate list with incomplete mates; unsatisfied mates red in the list and a one-line status; mate picking cursor in Drag mode; **Rotate** of a plane-mated component about Z, **Section** clipping and slider, mates window, collapsed **Mass**; sketch rectangle (DOF 4), constraint buttons with icons in the group of the dimension tools; **Surface finish** **Guide** sets the field from the roughness table; **ISO fits** calculator (H7/u6 interference, H7/g6 clearance, H7/k6 transition); **Drawings**: properties of a selected dimension, ISO 286 class and deviations in µm; **Options**: inch units relabel the deviation fields, left-handed keys relabel the tooltips and select the tools; **Analysis**: load, beam by coordinates, face pick, **Solve**, results, states and fields; plate by typed points; **Analysis** with a sketch-only part as geometry (sketch drawn, **Beam** ends snapped to sketch corners, **Sketch beams**, member end selection, hover marker, **Support** at the selected end, end and member picks, solve); drag of an unfixed mated pair; drag of a component held in a sliding component (the chain follows); conflicting mate left out, **Check**, **Suppress conflicting**, Ctrl+Z / Ctrl+Y; live drag of a chain; **Rotate** of a held component turns the chain; **Isolate**; default **Flip** from the current directions; **Measure** in the Assembly and Part tabs; **Show all** and **Invert**; component menu **Show only** the mated or connected components; **Box select**; Drawings **Angle** dimension; **Parts list** on and off; Analysis mesh settings (hexahedra by subdivision) and prescribed displacement support; Analysis member grid (typing, group creation, fill drag, paste, refused value, Delete), plate grid and plate groups, groups, member colours in the results and panel width; beam drawing with repeated properties; reference point with faces, support with six components and a moment load; Part **Place**; **Plane** normal to a sketch curve at its end; sketch x axis on a face from the view; **Bridge surface** command (side A and side B edges of surface bodies); **Display** modes; **Explicit**: geometry, rigid impactor, support face, **Write .inp**, **New run**, **Build**, **Run**, status board, results with the frame slider and hidden eroded elements, energy curve, **Save as…**; deck generator source: sum in a field, coincident position refused, **Pattern…** with skipped positions, plan and section diagrams, plates in the 3D view, edge support, **Write .inp**, **Generate STEP**, **Open part** with the surface bodies. A JavaScript error on the page fails the test |

## 15. Limitations

- Input is STEP only. AstoCAD models are exported with **File > Export** > STEP.
- Dimensions and notes are not written to the FCStd file.
- Dimensions in the DXF are lines and text, not DIMENSION entities.
- One section view per drawing.
- Sketch: arcs from three points cannot be drawn. Dimensions on a curve (radius of an ellipse, length of a spline) are not available; dimensions between curve points are. Imported splines and ellipses are polylines (**Convert to arc** / **spline** / **conic** in **Properties**, or **Convert N polyline(s)** in **Check**).
- Sketch: constraints are not written to the DXF file. The sketch file (**Save**) keeps them.
- Sketch: hatching is not imported or drawn.
- Part: fillet and chamfer are equal-distance on edges only; no draft. Loft is a surface feature (**Loft surface**).
- Assembly: mates use planar and cylindrical faces and the reference planes and axes of the components; no edge, vertex, tangent or gear mates.
- Cosmetic threads and hole callouts come from the **Hole** feature of parts; threads of imported STEP files and of assembly drawings are not drawn. Holes copied by a **Pattern** or a **Mirror** carry the thread and the callout of the source hole, and the callout count includes the copies.
- FEA mesh: structured hexahedra need block cells (6 faces with 4 edges each); no swept meshing of non-block cells, no contact or boundary condition definitions.
- Analysis: linear static only; no contact (touching bodies are bonded or not connected), no shell elements, no buckling or modal analysis. U1 beams: no shear deformation; torsional stiffness G (I11 + I22), exact for ROUND and PIPE only. Body plates are prismatic parts and plate items are flat; both have one element layer.
- Explicit: the ShinyCAD geometry gives solid elements only (no shells); shell models come from the deck generator or an external .inp. The deck generator models a flat rectangular panel with beams along x and y, one material and no rigid bodies (impactors come from an external .inp; the rigid floor applies). Supports hold displacements of face nodes; loads other than the driver, gravity and the rigid floor come from the .inp. The results view reads legacy VTK files of anim_to_vtk.
- Projection time depends on the number of B-spline faces (approximately 10 s to 30 s per part for a 7 MB STEP part with 234 faces on a 2-core machine). Views are computed in parallel on machines with more than 2 cores.
