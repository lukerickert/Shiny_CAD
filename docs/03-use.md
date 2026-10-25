[Contents](../README.md) · [← 2. Files](02-files.md) · [4. Title block editor →](04-title-block-editor.md)

# 3. Use

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
| Title block fields | Values for this run. **Guide** next to **Surface finish** opens the **Surface roughness** table ([section 6.1](06-drawings.md#61-threads-and-holes-reference)). Empty Title, Identification number and Date of issue are filled with the part name, the title in upper case and today's date |
| **Output folder** | Files are written to this folder. Empty: the `drawings/` folder of the open project; with no project open, the browser downloads one file, or `drawings.zip` for several files |
| **Write to a drawings folder next to each opened STEP file** | Writes to `<STEP folder>\drawings` for files opened by path |
| **Save as defaults** | Writes the current settings and fields to `config.json`. Title, Supplementary title, Identification number, Date, Mass and Material are not stored |

Output file names are `<STEP file>.pdf` for a STEP file with one part and `<STEP file>_<part>.pdf` for several parts.
With **Auto** sheet size the smallest sheet from A4 to A0 is used where the scale is >= `auto_sheet_min_scale` (default 1:1).

Path fields (**Folder or STEP file path on this PC**, **Output folder**, the **Folder** fields of the **Sketches** pane and the Part and Assembly tabs, **DXF path**, **STEP file path** of **Import STEP**) have a **…** button that opens the Windows file or folder dialog on this PC; **Add STEP** in the Assembly tab opens it directly. The dialog needs tkinter, which is part of the python.org installation.

**Search ⌕** at the right end of the tab bar, or Ctrl+K, opens the command search. It lists the buttons of all tabs whose text, tooltip, tab or menu name, or other name (for example `stl` for **Import STEP**, `array` for **Pattern**, `pocket` for **Cut**) contain every typed word, best match first, with the tab and menu and the tooltip. Up and Down select, Enter or a click runs the command in its tab, Esc or a click outside closes the window. A command that is not available in the current state is shown dimmed and is not run.

The status line in the header is one line; a longer message is cut off and its full text is the tooltip.

## 3.1 Options

**Options** at the upper right opens the program options. They are stored in `config.json` (`options`; **Browser** in `config.local.json`) and apply at once, except **Browser**.

| Option | Choices |
|---|---|
| **Drawing units** | **mm** (default) or **inch, decimal point**. Applies to dimension text, tolerances, hole callouts (**Thread & hole callouts**), the title block **Units** field (`mm` is printed as `in`) and the deviation fields of the dimension properties. The model, the other input fields and the exports of the Part, Assembly and Analysis tabs are in mm |
| **Keyboard shortcuts** | **Default** or **Left-handed** (keys on the right side of the keyboard). The dialog lists the keys of the selected set for each tab. Tooltips show the key of the selected set |
| **Browser** | Command that `run.py` uses to open the program at start. Empty (default): the system default browser. `{url}` in the command is replaced by the address; without `{url}` the address is added at the end. Example: `"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --app={url}` (window without tabs and address bar). Stored in `config.local.json` (`browser`) and used at the next start. When the command fails the default browser is used |

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

[Contents](../README.md) · [← 2. Files](02-files.md) · [4. Title block editor →](04-title-block-editor.md)
