# -*- coding: utf-8 -*-
"""Tools section of the Explicit tab (ORC**3 Tools tab): the companion scripts of the workspace, the model-generation
scripts of the SCRIPTS_AND_MACROS folder and the scripts of the user.

Built-in tools: TOOLS (the ORC**3 list; script paths relative to this folder, _REPO = the SCRIPTS_AND_MACROS folder,
three levels above drawgen/explicit). User tools and the keys of hidden built-in tools: tools.json next to the
ShinyCAD config.json (format: TOOLS_FILE_README; on first use the ORC**3 %APPDATA%\\ORC3\\tools.json is copied).

Launch (launch()): empty box -> the auto_arg of the tool ("inp": Source .inp, "dir": Output Dir, else Project Dir);
kind "gui" -> detached process; "cli" on Windows -> own console window (cmd /k); "cli" elsewhere -> output captured
into the console; "auto" -> "gui" with an empty box, else "cli". The scripts run with the Python of ShinyCAD from their
own folder. RIVET_CAL_CONFIG names a workspace_config.json with the current settings (rivet_calibration/wsconfig.py).
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))

TOOLS_FILE_README = [
    "Tools tab: your own scripts, and which built-ins to hide.",
    "Edit by hand or use the Add / Remove buttons on the Tools tab, then press",
    "Reload there (or restart). Built-in tools live in workspace_constants.py.",
    "",
    "tools[] entries:",
    "  script  REQUIRED  path to the .py (absolute, or relative to this folder)",
    "  title   REQUIRED  what the row is called",
    "  kind              'cli'  own console window, stays open after the run",
    "                    'gui'  opens its own window, launched detached",
    "                    'auto' GUI when the Args box is empty, console with args",
    "  desc              one line under the row (optional)",
    "  args              pre-filled input box (optional)",
    "  no_args   true    the script takes no input - show no box at all",
    "  arg_label         what to call the box, e.g. 'File:' or 'Folder:'",
    "  arg_hint          grey note after the box, e.g. 'empty = uses X'",
    "  group             section heading (optional, default 'My scripts')",
    "  key               unique id; auto-filled from the file name if omitted",
    "",
    "hidden[]: keys of BUILT-IN tools to leave out of the list (reversible -",
    "delete the key here, or use Show hidden -> Restore on the tab).",
]

_REPO = os.path.join("..", "..", "..")
TOOLS_BUILTIN_GROUP = "Workspace companions"
TOOLS_USER_GROUP = "My scripts"

# v21.6: what the input box on each row IS. It used to be labelled "Args:" on
# every row - programmer jargon, and shown even on tools that accept nothing.
# Now each entry says what that tool wants (arg_label / arg_hint) or opts out
# entirely (no_args), and this text explains the idea once, behind the '?' at
# the top of the tab.
TOOLS_ARGS_DOC = (
    "Some of these tools can be told WHAT to work on when they start - a file, "
    "a folder, or a switch that changes what they do. The box on each row is "
    "where that goes. It is the same thing you would type after the script "
    "name at a command prompt:\n"
    "\n"
    "    job_audit.py  C:\\runs\\proj  -o report\n"
    "                  \\_________/  \\_______/\n"
    "                    a folder     a switch\n"
    "\n"
    "## You can usually leave it empty\n"
    "* The grey note after each box says what happens then: either the "
    "workspace fills in the obvious thing for you (the Build tab's Source "
    ".inp, your Output Dir), or the tool needs nothing at all.\n"
    "* Rows that say '(nothing to set)' have no box - those scripts take no "
    "input; they read their settings from the file itself or from "
    "workspace_config.json.\n"
    "\n"
    "## When you do type something\n"
    "* A file or folder: just the path. Quote it if it contains spaces - "
    "\"C:\\My runs\\proj\".\n"
    "* A switch: starts with one or two dashes, e.g. -o report, --drop, "
    "--list-columns. Each tool's own '?' lists the ones it understands; a "
    "switch a tool does not know is usually reported by that tool in its "
    "console window.\n"
    "* Several are allowed, separated by spaces.\n"
    "\n"
    "## Notes\n"
    "* What you type applies to the NEXT launch only - it changes nothing "
    "inside the script. The text is remembered between sessions so you do not "
    "have to retype it.\n"
    "* Typing something into a box whose tool would otherwise use a default "
    "(e.g. a specific folder for Job audit) simply overrides that default for "
    "that launch.")
# repo deck scripts written for cadquery: the build123d port of deck_stepgen when cadquery is not installed
SUBSTITUTE_STEPGEN = {"needs": "cadquery", "modules": {"deck_stepgen": "drawgen.explicit.deck_stepgen"}}

TOOLS = [
    {"key": "inertia_builder", "no_args": True, "script": "inertia_builder.py", "kind": "gui",
     "auto_arg": None, "default_args": "",
     "title": "Inertia builder  (GUI)",
     "desc": "Build an impactor from box primitives: parts table, live side-view, "
             "live mass/CG/inertia tensor. Saves the JSON payload the Inertia tab consumes.",
     "doc": (
        "GUI front end for inertia_calc.py - the same window the Inertia tab's "
        "'Open inertia builder' button launches.\n"
        "\n"
        "* Table of box primitives: name, mass, CG position, dimensions.\n"
        "* Live scaled side-view with per-part CG dots and the assembly CG.\n"
        "* Live totals: mass, CG, inertia tensor about the CG, radii of gyration.\n"
        "* JSON save/load shares the inertia_calc.py schema, so files move freely "
        "between the GUI, the command-line tool and the Build merge.\n"
        "* Export the /RBODY payload (mass, cx..cz, Jxx..Jxz) and point the Inertia "
        "tab at it.")},
    {"key": "inertia_calc", "arg_label": "Options:", "arg_hint": "--demo, or a primitives JSON file", "script": "inertia_calc.py", "kind": "cli",
     "auto_arg": None, "default_args": "--demo",
     "title": "Inertia calc  (CLI)",
     "desc": "Command-line mass-properties engine behind the builder: JSON in, "
             "mass/CG/tensor/principals report out. '--demo' runs a worked example.",
     "doc": (
        "Rigid-body mass properties from box primitives - the math lives here, "
        "in exactly one place; the builder GUI imports it.\n"
        "\n"
        "* In the box: a primitives JSON file, or --demo for a worked example.\n"
        "* Reports total mass, CG, full 3x3 inertia tensor about the CG (parallel "
        "axis theorem), principal values, radii of gyration, and a per-primitive "
        "own-vs-transport contribution report.\n"
        "* Units are whatever you feed it, consistently (mm + tonne for MM_TON_S "
        "decks -> t*mm^2).")},
    {"key": "inp2rad", "arg_label": "File:", "arg_hint": "empty = the Build tab's Source .inp", "script": "inp2rad.py", "kind": "cli",
     "auto_arg": "inp", "default_args": "",
     "title": "inp2rad converter  (CLI)",
     "desc": "The raw .inp -> .rad converter the Build pipeline drives. Run it "
             "standalone to debug a conversion in isolation.",
     "doc": (
        "The Abaqus/CalculiX .inp -> OpenRadioss .rad translator. The Build tab "
        "runs it automatically (with card injection on top), so launching it here "
        "is for DEBUGGING a conversion in isolation.\n"
        "\n"
        "* In the box: the .inp to convert. Leave it empty to use the Build tab's "
        "current Source .inp.\n"
        "* Writes <model>_0000.rad / _0001.rad next to the input.\n"
        "* Interactive: it prompts y/n for constructs it cannot handle - answer in "
        "the console window (the Build pipeline auto-answers 'y').\n"
        "* First-order elements only - downgrade quadratic meshes first (below).")},
    {"key": "inp_to_linear", "arg_label": "File:", "arg_hint": "empty = the Build tab's Source .inp", "script": "inp_to_linear.py", "kind": "cli",
     "auto_arg": "inp", "default_args": "",
     "title": "2nd-order -> linear  (CLI)",
     "desc": "Downgrade a quadratic .inp to linear elements (writes *_linear.inp). "
             "Same code the Build tab's downgrade checkbox runs.",
     "doc": (
        "Downgrades a CalculiX/PrePoMax .inp from 2nd-order (quadratic) to "
        "1st-order (linear) elements so inp2rad / OpenRadioss can read it. The "
        "'Downgrade 2nd-order -> linear' checkbox on the Build tab runs this same "
        "module in-process (with prune disabled).\n"
        "\n"
        "* In the box: the .inp to convert (empty = the current Source .inp); writes "
        "<model>_linear.inp beside it.\n"
        "* Rewrites every *ELEMENT block: quadratic TYPE -> linear TYPE, midside "
        "nodes dropped from the connectivity.\n"
        "* Prunes nodes no element references after the downgrade (--keep-nodes "
        "disables; the Build checkbox always keeps them to protect RP nodes).\n"
        "* Filters *NSET/*ELSET so dropped midside nodes leave node sets too.\n"
        "* Unknown TYPEs pass through unchanged, with a warning.")},
    {"key": "job_audit", "arg_label": "Folder:", "arg_hint": "empty = your Output Dir", "script": "job_audit.py", "kind": "cli",
     "auto_arg": "dir", "default_args": "",
     "title": "Job audit  (CLI)",
     "desc": "Walk a runs tree and report ground truth per job from the decks on "
             "disk: strain output? /RBODY sane? actual contact/ties/Tstop?",
     "doc": (
        "Audits every job (each *_0000*.rad) under a folder from the ACTUAL "
        "artifacts on disk - starter deck, engine deck, settings report, pv "
        "manifest, converted VTK. Ground truth from the files, NOT the GUI's "
        "intended settings.\n"
        "\n"
        "* In the box: the root folder to walk (empty = Output Dir, else Project "
        "Dir), plus optional -o report_name.\n"
        "* Answers per job: will it produce max principal strain (Istrain + ANIM "
        "cards + VTK arrays)? Is any /RBODY malformed (the 9-field / grnd_ID!=0 "
        "Error-274 check)? What contact / tie / material / mass-scaling / Tstop "
        "was actually used?\n"
        "* Writes a human-readable .txt and a one-row-per-job .csv.")},
    {"key": "make_gauge_rings", "arg_label": "Options:", "arg_hint": "empty = the current model", "script": os.path.join("rivet_calibration", "make_gauge_rings.py"),
     "kind": "cli", "auto_arg": None, "default_args": "",
     "title": "Gauge rings  (CLI)",
     "desc": "Build /TH/NODE gauge rings around a rivet hole (no added stiffness). "
             "Reads the current model; the Rivet tab runs the same code.",
     "doc": (
        "Picks a ring of nodes at a given radius from the rivet-hole axis on each "
        "plate and writes the /TH/NODE cards plus a JSON manifest for the "
        "post-processor.\n"
        "\n"
        "* The point: measure RELATIVE displacement across the joint without "
        "perturbing the model - no rigid bodies, no constraints, no stiffness "
        "where the plate is yielding.\n"
        "* No args: uses the GUI's current model via workspace_config.json, with "
        "interactive prompts for the gauge geometry.\n"
        "* The Rivet tab calls the same build_rings() code - both paths are "
        "identical; this console route is for scripted/manual use.")},
    {"key": "relative_disp", "arg_label": "Options:", "arg_hint": "--list-columns lists the CSV columns", "script": os.path.join("rivet_calibration", "relative_disp.py"),
     "kind": "cli", "auto_arg": None, "default_args": "--list-columns",
     "title": "Relative displacement  (CLI)",
     "desc": "Force vs relative-displacement curve from a T01 CSV (ring-averaged). "
             "Start with --list-columns to see what the CSV holds.",
     "doc": (
        "Builds a force vs relative-displacement curve from the CSV that "
        "th_to_csv produces: averages each gauge ring, subtracts one ring from "
        "the other, pairs the result with the driving force, and reports peak "
        "force and displacement at failure.\n"
        "\n"
        "* Typical: --force-col \"RBODY 12 FX\"  (finds CSV + manifest via "
        "workspace_config.json automatically).\n"
        "* Or explicit: run_T01.csv gauge_rings.json --force-col ... --out "
        "curve.csv\n"
        "* --list-columns (the default here) just shows what columns exist - run "
        "that first.\n"
        "* The Rivet tab calls the same compute() code; this is the "
        "scripted/manual route.")},

    # ---- model generation (SCRIPTS_AND_MACROS repo root) --------------------
    {"key": "deck_builder", "no_args": True, "script": os.path.join(_REPO, "deck_builder.py"),
     "kind": "cli", "auto_arg": None, "default_args": "",
     "group": "Model generation (repo scripts)",
     "title": "Deck builder  (CLI)",
     "desc": "Parametric + freeform shell parts -> OCC conformal fragment -> gmsh "
             "quad-dominant mesh -> CalculiX .inp with per-part ELSETs/sections. "
             "Run = the demo panel; edit __main__ for your own model. Needs gmsh.",
     "doc": (
        "Full geometry-to-mesh pipeline in one script: parts (parametric "
        "builders, raw polygons, or imported STEP) -> OCC fragment (mutual "
        "imprint, conformality guaranteed) -> gmsh shell mesh -> CalculiX .inp "
        "ready for PrePoMax or directly for inp2rad.\n"
        "\n"
        "* A 'Part' is a named bag of surfaces + thickness/material/mesh size; "
        "polygons, plate/flat_bar/tee_girder helpers and step= imports mix freely.\n"
        "* Overlap rule: parts LATER in the list claim shared fragments (an "
        "insert plate listed after the deck takes the coplanar region).\n"
        "* Writes one ELSET per part, *SHELL SECTION + *MATERIAL cards, and an "
        "EDGE_CLAMP perimeter node set. Units mm / tonne / s / MPa.\n"
        "* Launching runs the demo model (panel + insert + bracket) and writes "
        "demo_panel.inp NEXT TO THE SCRIPT (v21.4 fixed a hardcoded path that "
        "crashed on Windows); edit the __main__ block for real models.\n"
        "* Requires the gmsh Python package in the workspace interpreter.")},
    {"key": "deck_gui", "no_args": True, "script": os.path.join(_REPO, "DECK_GENERATOR", "deck_gui.py"),
     "kind": "gui", "auto_arg": None, "default_args": "", "substitute": SUBSTITUTE_STEPGEN,
     "group": "Model generation (repo scripts)",
     "title": "Deck generator  (GUI)",
     "desc": "Deck-structure front end for deck_stepgen: beam table, live plan + "
             "cross-section diagrams, JSON save/load, Generate partitioned STEP "
             "+ the _model.json that Deck element sets reads.",
     "doc": (
        "GUI for the parametric deck -> partitioned named STEP pipeline "
        "(deck_stepgen.py next to it does the geometry).\n"
        "\n"
        "* One Beam type covers flat bar / T / I via flange widths; webs are "
        "pre-split at crossings, deeper beams claim crossing squares, shallower "
        "bottom flanges snipe short - no dangling imprints, so PrePoMax can "
        "glue the result.\n"
        "* Deck definitions save/load as JSON for the project repo.\n"
        "* The diagrams work standalone; the Generate button needs cadquery "
        "installed (import failure is shown in the window, not a crash). When "
        "cadquery is not installed in the Python of ShinyCAD, the tool starts with "
        "the build123d version of deck_stepgen of ShinyCAD "
        "(drawgen/explicit/deck_stepgen.py, same functions).")},
    {"key": "deck_mesh", "arg_label": "Model json:",
     "arg_hint": "add --size 100 for element size",
     "script": os.path.join(_REPO, "DECK_GENERATOR", "deck_mesh.py"),
     "substitute": SUBSTITUTE_STEPGEN, "kind": "cli", "auto_arg": None, "default_args": "",
     "group": "Model generation (repo scripts)",
     "title": "Deck mesh  (CLI)",
     "desc": "Structured quad mesh straight from the deck model, with the "
             "section element sets AND the *SHELL SECTION / *MATERIAL cards "
             "already in it - a ready-to-solve deck in one command.",
     "doc": (
        "Geometry -> conformal quad mesh -> .inp carrying DECK, GIRDER_WEB, "
        "GIRDER_FLANGE ... as element sets. The sets are EXACT here rather "
        "than inferred: at mesh time the face-to-part ownership is still "
        "known, so nothing has to be recovered afterwards.\n"
        "\n"
        "## Why the mesh comes out regular\n"
        "* A max element size alone lets gmsh choose its own divisions per "
        "edge, so neighbouring plates disagree and the node layout changes "
        "completely whenever anything moves.\n"
        "* Instead every break coordinate in the model (panel edges, beam "
        "lines, flange edges, web depths) is collected per axis to give "
        "INTERVALS; each interval gets ceil(length / size) divisions, so no "
        "element exceeds the size you asked for.\n"
        "* Each plate is then cut at those lines, so every face spans exactly "
        "one interval each way and opposite sides always match - including a "
        "web whose top edge is chopped up by the members crossing it, the "
        "case a per-edge rule cannot handle.\n"
        "* The result is a true rectangular grid: structured, conformal, and "
        "stable when you edit one member and re-generate.\n"
        "\n"
        "## Sections\n"
        "* Plate thicknesses come from the model (t_web / t_flange per beam, "
        "deck_t for the plating) and are written as one *SHELL SECTION per "
        "element set, plus the *MATERIAL cards - so the deck arrives with its "
        "plating assigned rather than needing it set group by group.\n"
        "* Sets are named per beam NAME and role, so a thickness belongs to a "
        "group. Two beams sharing a name but not a plate is reported and the "
        "first is used - give them different names to split the group.\n"
        "* Models saved before thicknesses existed fall back to 8 mm web / "
        "12 mm flange / 8 mm deck. --no-sections writes the sets only.\n"
        "\n"
        "## Options\n"
        "* --size 100 max element size [mm]; --min-div 1 minimum divisions per "
        "interval; --tri to keep triangles; --order 2 for second-order.\n"
        "* --no-transfinite meshes unstructured instead, for comparison.\n"
        "* -o out.inp to choose the output name.\n"
        "* --isolate X0 Y0 X1 Y1 cuts that rectangular patch of plan into its "
        "own file and leaves the remainder as ONE conformal mesh - the cut for "
        "replacing a bay and tying it back in. Only the patch perimeter is a "
        "seam; every other junction stays shared-node. On the demo deck that "
        "is 116 cut edges against 632 for a per-section split.\n"
        "* --split writes one .inp PER element set instead of one file, so "
        "each imports as its own part. Numbering is kept consistent between "
        "them - a node where plates meet has the same id and coordinates in "
        "every file it appears in - so merging coincident nodes after import "
        "reconnects them into one model. The shared-node count is reported.\n"
        "\n"
        "Needs gmsh (pip install gmsh). The Deck generator GUI has the same "
        "thing on a 'Generate mesh (.inp)' button.")},
    {"key": "deck_elsets", "arg_label": "Meshed .inp:",
     "arg_hint": "the mesh to add sets to",
     "script": os.path.join(_REPO, "DECK_GENERATOR", "deck_elsets.py"),
     "kind": "cli", "auto_arg": None, "default_args": "",
     "group": "Model generation (repo scripts)",
     "title": "Deck element sets  (CLI)",
     "desc": "Rebuild the section groups (DECK, GIRDER_WEB, ...) on a MESHED "
             "deck .inp - the step you would otherwise do by hand in "
             "PrePoMax after merging the parts.",
     "doc": (
        "Merging the parts before meshing is what makes the mesh conformal - "
        "and it is also what discards the STEP component names, which is why "
        "the element sets have to be recreated by selection afterwards. That "
        "selection is pure geometry, so this computes it instead.\n"
        "\n"
        "* In the box: the meshed .inp exported from PrePoMax. It also needs "
        "the <name>_model.json that deck_stepgen writes beside the STEP - "
        "found automatically if it sits next to the .inp, else pass "
        "-m <file>.\n"
        "* Classifies every SHELL element by its centroid against the same "
        "rules the geometry was built with: horizontal at z=0 is a top FLANGE "
        "if it falls within bf_top/2 of a beam line and DECK otherwise; "
        "horizontal at z=-h is that beam's LOWER_FLANGE; vertical on a beam "
        "line is its WEB. At a crossing the deeper beam claims the flange, "
        "equal depths go to the beam listed first.\n"
        "* Writes <input>_sets.inp (or --in-place, which keeps a .bak) - the "
        "original file plus the *ELSET blocks. Re-import and convert the sets "
        "into parts as usual.\n"
        "* Re-running replaces its own sets rather than duplicating them.\n"
        "* Non-shell records (line/beam elements) are skipped and reported - "
        "they are not plates. Any shell the rules miss goes into UNCLASSIFIED "
        "with a warning, so a manifest that does not match the mesh is loud "
        "rather than silently wrong. --dry-run reports without writing.")},
    {"key": "stiffened_panel", "no_args": True, "script": os.path.join(_REPO, "stiffened_panel.py"),
     "kind": "cli", "auto_arg": None, "default_args": "",
     "group": "Model generation (repo scripts)",
     "title": "Stiffened panel  (CLI)",
     "desc": "Quick parametric midsurface panel -> STEP (plate + flat-bar "
             "stiffeners + T-girder). Parameters are constants at the top of the file.",
     "doc": (
        "Parametric midsurface stiffened deck panel written as a single STEP "
        "compound (shell faces only, zero thickness - assign shell thickness in "
        "PrePoMax).\n"
        "\n"
        "* Geometry: deck plate, flat-bar longitudinal stiffener webs, one "
        "transverse T-girder (web + flange) at mid-length. Units mm.\n"
        "* No arguments: edit the parameter constants at the top (L, B, ns, hw, "
        "girder_hw, girder_bf) and launch.\n"
        "* Writes stiffened_panel_midsurface.step NEXT TO THE SCRIPT (v21.4 "
        "fixed a hardcoded path that crashed on Windows).\n"
        "* Faces are NOT imprinted - use the conformal variant below when the "
        "mesh must share nodes at junctions. Requires cadquery.")},
    {"key": "stiffened_panel_conformal", "no_args": True,
     "script": os.path.join(_REPO, "stiffened_panel_conformal.py"),
     "kind": "cli", "auto_arg": None, "default_args": "",
     "group": "Model generation (repo scripts)",
     "title": "Stiffened panel, conformal  (CLI)",
     "desc": "Same panel but pre-partitioned: OCCT general fuse + non-manifold "
             "sewn shell STEP, ready for compound-part shell meshing.",
     "doc": (
        "The conformal variant: all faces mutually imprinted/split at "
        "intersections and sewn into ONE non-manifold shell, exported with "
        "OCCT's non-manifold STEP mode so shared-edge topology survives.\n"
        "\n"
        "* Partial-depth junctions (stiffener web meeting a deeper girder web) "
        "are pre-split into full-height fields, so every junction is a real "
        "boundary edge on every face - dangling internal imprints do not "
        "survive STEP round-trips; boundary edges do.\n"
        "* No arguments: edit the parameter constants at the top and launch.\n"
        "* Writes stiffened_panel_conformal.step NEXT TO THE SCRIPT (v21.4 "
        "fixed a hardcoded path that crashed on Windows).\n"
        "* Requires cadquery + OCP.")},
    {"key": "deck_strip", "arg_label": "File:", "arg_hint": "empty = opens its own window",
     "script": os.path.join(_REPO, "INPUT_FILE_STRIPPER", "deck_strip.py"),
     "kind": "auto", "auto_arg": None, "default_args": "",
     "group": "Model generation (repo scripts)",
     "title": "Deck stripper  (GUI/CLI)",
     "desc": "Shrink an .inp/.rad deck for upload: bulk blocks (nodes/elements/"
             "sets) truncated, everything else byte-for-byte.",
     "doc": (
        "Shrinks an Abaqus .inp or OpenRadioss .rad deck so it can be shared/"
        "uploaded, while staying READABLE as a model description.\n"
        "\n"
        "* Only bulk blocks are truncated (nodes, elements, group/surface "
        "members); materials, properties, contacts, steps and engine cards "
        "pass through byte-for-byte.\n"
        "* Leave the box empty and its own window opens (pick file + options there).\n"
        "* With args = console mode:  model.inp   |   model_0000.rad -k 3   |   "
        "model_0000.rad --drop (blank bulk entirely)   |   model.inp --max 40 "
        "(cap any other block too).\n"
        "* Format chosen by extension; .rad, .inp, .inc and _0001.rad all work.")},
    {"key": "inp2unv", "arg_label": "File:", "arg_hint": "the .unv mesh to convert", "script": os.path.join(_REPO, "inp2unv", "inp2unv.py"),
     "kind": "cli", "auto_arg": None, "default_args": "",
     "group": "Model generation (repo scripts)",
     "title": "UNV -> INP converter  (CLI)",
     "desc": "Converts a Salome .unv mesh to a CalculiX .inp "
             "(Ihor Mirzov's unv2ccx, GPLv3).",
     "doc": (
        "Converts a UNV mesh exported from Salome into a CalculiX .inp - the "
        "route into this pipeline for models meshed in Salome.\n"
        "\n"
        "* In the box: the .unv file; the .inp is written beside it.\n"
        "* Third-party: (c) Ihor Mirzov, GNU GPL v3 (folder 'inp2unv'; the tool "
        "itself is the unv2ccx converter - the folder name understates it).\n"
        "* The companion modules (reader/writer/mesh/clean) must stay next to "
        "the script - they are imported from its folder.")},
]

TOOLS.insert(5, {"key": "rad_preview", "no_args": True, "script": "rad_preview.py", "kind": "gui",
                 "auto_arg": None, "default_args": "",
                 "title": "Rad preview  (GUI)",
                 "desc": "One-cycle geometry preview of starter decks in ParaView (starter + one-cycle engine "
                         "+ anim_to_vtk in a _preview folder).",
                 "doc": (
                    "Displays a starter deck (<job>_0000.rad) in ParaView before the real solve.\n"
                    "\n"
                    "* Each selected deck is copied into its own preview folder together with the files it includes.\n"
                    "* A one-cycle engine deck is written there, the starter and engine are run, the first animation "
                    "file is converted to legacy ASCII VTK with anim_to_vtk_win64, and ParaView is launched on the result.\n"
                    "* The original run folder is not written to.\n"
                    "* starter_win64, engine_win64 and anim_to_vtk_win64 must be on PATH. The paraview.exe path is "
                    "read from %APPDATA%\\ORC3\\workspace_config.json.")})


def tools_file(config_path):
    """tools.json next to the ShinyCAD config.json; the ORC**3 tools.json is copied there once."""
    p = os.path.join(os.path.dirname(os.path.abspath(config_path)), "tools.json")
    if not os.path.isfile(p) and os.environ.get("APPDATA"):
        orc = os.path.join(os.environ["APPDATA"], "ORC3", "tools.json")
        if os.path.isfile(orc):
            try:
                shutil.copy2(orc, p)
            except OSError:
                pass
    return p


def load_tools_file(path):
    """(user tools, hidden keys, error or None) of tools.json (no file: no user tools)."""
    if not os.path.isfile(path):
        return [], set(), None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [], set(), "%s could not be read (%s)" % (os.path.basename(path), e)
    if not isinstance(data, dict):
        return [], set(), "%s must contain a JSON object" % os.path.basename(path)
    out, bad = [], []
    for i, t in enumerate(data.get("tools") or []):
        if not isinstance(t, dict) or not t.get("script") or not t.get("title"):
            bad.append(str(i + 1))
            continue
        kind = t.get("kind", "cli")
        if kind not in ("cli", "gui", "auto"):
            kind = "cli"
        key = t.get("key") or ("user:" + re.sub(r"[^A-Za-z0-9_]+", "_",
                                                os.path.splitext(os.path.basename(str(t["script"])))[0]).strip("_").lower())
        out.append({"key": key, "script": str(t["script"]), "kind": kind, "auto_arg": None,
                    "default_args": t.get("args", ""), "group": t.get("group") or TOOLS_USER_GROUP,
                    "title": str(t["title"]), "desc": t.get("desc", ""), "no_args": bool(t.get("no_args", False)),
                    "arg_label": t.get("arg_label", "Options:"), "arg_hint": t.get("arg_hint", "")})
    err = ("%d entry/entries in %s were skipped (no 'script' or no 'title'): #%s"
           % (len(bad), os.path.basename(path), ", #".join(bad))) if bad else None
    return out, set(data.get("hidden") or []), err


def save_tools_file(path, user_tools, hidden):
    """Writes tools.json (with the _readme block). Returns None, else the error text."""
    payload = {
        "_readme": TOOLS_FILE_README,
        "tools": [{k: v for k, v in (
                       ("key", t.get("key", "")), ("title", t.get("title", "")),
                       ("script", t.get("script", "")), ("kind", t.get("kind", "cli")),
                       ("args", t.get("default_args", "")), ("desc", t.get("desc", "")),
                       ("group", t.get("group", TOOLS_USER_GROUP)), ("no_args", t.get("no_args", False)),
                       ("arg_label", t.get("arg_label", "")), ("arg_hint", t.get("arg_hint", "")))
                   if v not in ("", False) or k in ("key", "title", "script", "kind", "args")}
                  for t in user_tools],
        "hidden": sorted(hidden),
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return None
    except Exception as e:
        return str(e)


def user_tool_doc(tool):
    kind = {"gui": "GUI: own window, launched detached.",
            "cli": "Console: own console window, open after the run.",
            "auto": "Auto: empty box = the GUI of the script; any text in the box = console."}.get(tool.get("kind"), tool.get("kind"))
    return ("Script of the user (tools.json).\n"
            "\n"
            "* Script: %s\n"
            "* Launch mode: %s\n"
            "* Runs with the Python of ShinyCAD, from the folder of the script.\n"
            "* The text of the box is passed to the script as typed (quote paths with spaces).\n"
            "* arg_label / arg_hint / no_args of the entry in tools.json set the box.\n"
            "* Remove takes the entry off the list; the file is not deleted." % (tool.get("script"), kind))


def script_path(tool):
    s = tool["script"]
    return s if os.path.isabs(s) else os.path.normpath(os.path.join(HERE, s))


def all_tools(user_tools, hidden):
    """Built-in tools then user tools, with builtin, hidden, path, exists and doc."""
    out = []
    for t in TOOLS:
        d = dict(t)
        d["builtin"] = True
        out.append(d)
    for t in user_tools:
        d = dict(t)
        d["builtin"] = False
        d.setdefault("group", TOOLS_USER_GROUP)
        d.setdefault("auto_arg", None)
        d.setdefault("default_args", "")
        d.setdefault("desc", "")
        d["doc"] = user_tool_doc(d)
        out.append(d)
    for d in out:
        d["hidden"] = d["builtin"] and d["key"] in hidden
        d["path"] = script_path(d).replace("\\", "/")
        d["exists"] = os.path.isfile(script_path(d))
        d.setdefault("group", TOOLS_BUILTIN_GROUP)
    return out


def new_user_tool(path, title, kind, existing_keys, user_tools):
    """Entry of a script added on the Tools section; raises ValueError."""
    path = (path or "").strip().strip('"')
    if not path:
        raise ValueError("no script chosen")
    if not os.path.isfile(path):
        raise ValueError("%s does not exist" % path)
    title = (title or "").strip() or os.path.splitext(os.path.basename(path))[0]
    kind = kind if kind in ("cli", "gui", "auto") else "cli"
    base = "user:" + re.sub(r"[^A-Za-z0-9_]+", "_", os.path.splitext(os.path.basename(path))[0]).strip("_").lower()
    key, n = base, 2
    while key in existing_keys:
        key = "%s_%d" % (base, n)
        n += 1
    if any(os.path.normcase(os.path.abspath(t.get("script", ""))) == os.path.normcase(os.path.abspath(path)) for t in user_tools):
        raise ValueError("%s is already in the list" % os.path.basename(path))
    return {"key": key, "script": path, "kind": kind, "auto_arg": None, "default_args": "", "group": TOOLS_USER_GROUP,
            "title": "%s  (%s)" % (title, kind.upper()), "desc": "User script: %s" % path}


def split_args(raw):
    """Arguments of the box (Windows paths kept; quotes removed). Raises ValueError on an unclosed quote."""
    raw = (raw or "").strip()
    if not raw:
        return []
    args = shlex.split(raw, posix=False)
    return [a[1:-1] if len(a) > 1 and a[0] == a[-1] and a[0] in "\"'" else a for a in args]


_BOOT = ("import importlib, os, runpy, sys\n"
         "root, subs, path = sys.argv[1], sys.argv[2], sys.argv[3]\n"
         "sys.path.insert(0, root)\n"
         "for pair in subs.split(','):\n"
         "    name, mod = pair.split('=')\n"
         "    sys.modules[name] = importlib.import_module(mod)\n"
         "sys.argv = sys.argv[3:]\n"
         "sys.path.insert(0, os.path.dirname(os.path.abspath(path)))\n"
         "runpy.run_path(path, run_name='__main__')\n")


def command(tool, path, args):
    """Command line of a tool: the Python of ShinyCAD with the script. A tool with "substitute" {"needs": module,
    "modules": {name: ShinyCAD module}} whose module is not installed starts through _BOOT, which puts the ShinyCAD
    modules in place of those names before the script runs."""
    sub = tool.get("substitute")
    if sub:
        import importlib.util
        try:
            have = importlib.util.find_spec(sub["needs"]) is not None
        except (ImportError, ValueError):
            have = False
        if not have:
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            subs = ",".join("%s=%s" % kv for kv in sub["modules"].items())
            return [sys.executable, "-c", _BOOT, root, subs, path] + list(args)
    return [sys.executable, path] + list(args)


def launch(tool, raw, inp_path, out_dir, project_dir, log, env=None):
    """Starts the tool. Returns (True, message) or (False, message)."""
    path = script_path(tool)
    if not os.path.isfile(path):
        return False, "Tools: %s not found at %s" % (tool["title"], path)
    try:
        args = split_args(raw)
    except ValueError as e:
        return False, "Tools: the box of %s cannot be read (%s): a quote is not closed" % (tool["title"], e)
    note = ""
    if not args and not tool.get("no_args"):
        if tool.get("auto_arg") == "inp":
            if not (inp_path or "").strip():
                return False, ("Tools: %s needs a file. The box is empty and there is no Source .inp; "
                               "type a file path into the box." % tool["title"])
            args, note = [inp_path.strip()], "  [Source .inp]"
        elif tool.get("auto_arg") == "dir":
            cur = (out_dir or "").strip() or (project_dir or "").strip()
            if not cur:
                return False, ("Tools: %s needs a folder. The box is empty and there is no Output Dir or Project Dir; "
                               "type a folder path into the box." % tool["title"])
            args, note = [cur], "  [Output Dir]" if (out_dir or "").strip() else "  [Project Dir]"
    workdir = os.path.dirname(path)
    kind = tool.get("kind", "cli")
    if kind == "auto":
        kind = "cli" if args else "gui"
    cmd = command(tool, path, args)
    if cmd[1] == "-c":
        note += "  [cadquery not installed: deck_stepgen of ShinyCAD (build123d)]"
    try:
        if kind == "gui":
            subprocess.Popen(cmd, cwd=workdir, env=env)
        elif os.name == "nt":
            subprocess.Popen(["cmd", "/k"] + cmd, cwd=workdir, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            threading.Thread(target=_run_captured, args=(tool["title"], cmd, workdir, log, env), daemon=True).start()
    except Exception as e:
        return False, "Tools: %s could not be started: %s" % (tool["title"], e)
    return True, "Tools: launched %s%s%s" % (tool["title"], ("  with: " + " ".join(args)) if args else "", note)


def _run_captured(title, cmd, workdir, log, env):
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, env=env,
                              stdin=subprocess.DEVNULL, timeout=3600)
        for stream, tag in ((proc.stdout, ""), (proc.stderr, "stderr: ")):
            for ln in (stream or "").strip().splitlines():
                log("  [%s] %s%s" % (title, tag, ln))
        log("Tools: %s finished (exit %d)." % (title, proc.returncode))
    except Exception as e:
        log("Tools: %s failed: %s" % (title, e))
