// CAM tab: a job on a saved part for a 3-axis machine in the manner of the FreeCAD CAM workbench: job tree
// (operations with their dressups, model with its placement, stock, setup sheet, tool controllers), a command window in
// the view for the operation being edited (base geometry picked in the view, depths, heights, fields of the
// type) with a live preview of the toolpaths, the stock cut by the tool on the server, the tool bit library,
// sanity check, G-code inspection and the post-processed file.
import * as THREE from "three";
import { TumbleControls } from "/static/vendor/TumbleControls.js";
import { updateAxes } from "/static/axes.js";
import { createNavCube } from "/static/navcube.js";

const CM = { doc: null, dirty: false, three: null, geo: null, bbox: null, size: 100,
             sel: null,          // selected tree item: "job" | "ops" | "model" | "part" | "pc:<id>" | "stock" | "setup" | "tools" | "tc:<id>" | op id | "dr:<op id>:<i>"
             cmd: null,          // {id, dr, step, snapshot} while an operation (or its dressup dr) is edited in the command window
             res: null,          // result of the last run or preview
             resUpto: null,      // index of the last operation of a preview run (null: the whole job)
             setup: null,        // {stock_bbox, part_bbox, origin, clearance_z}
             hidden: {},         // tree items whose geometry is hidden (eye)
             fold: { tools: true },   // folded tree items
             placeRes: null,     // result of the last placement solve {messages, unsatisfied}
             bits: [], posts: [], meta: null, sketches: [], seq: 0, previewTimer: null, previewSeq: 0, chipHover: null, cmdPos: null,
             client: Math.random().toString(36).slice(2) };   // id of this page for the cancel of superseded previews
const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const fmt = (v, d = 4) => {
  if (v === null || v === undefined || !isFinite(v)) return "-";
  let s = Number(v).toPrecision(Math.max(d, 1));
  if (s.includes(".") && !s.includes("e")) s = s.replace(/\.?0+$/, "");
  return s === "-0" ? "0" : s;
};
const num = v => { const x = window.numv(String(v)); return isFinite(x) ? x : NaN; };
const COLORS = { part: 0x9aa7b5, under: 0x74c0fc, sel: 0xf08c00, pickable: 0xa5d8ff, stock: 0x4c6ef5, left: 0xe03131, hm: 0x8ce99a,
                 rapid: 0xe8590c, plunge: 0x1c7ed6, feed: 0x2b8a3e, arc: 0x7048e8, dim: 0xadb5bd, edgeSel: 0xf08c00, gouge: 0xe64980 };
/** Points along an arc from a to b about c (XY), Z interpolated, 24 segments per turn. */
function arcPoints(a, b, c, cw) {
  const ax = a[0] - c[0], ay = a[1] - c[1], bx = b[0] - c[0], by = b[1] - c[1];
  const r = Math.hypot(ax, ay), t0 = Math.atan2(ay, ax);
  let d = Math.atan2(by, bx) - t0;
  if (cw) { while (d > -1e-9) d -= 2 * Math.PI; } else { while (d < 1e-9) d += 2 * Math.PI; }
  const n = Math.max(2, Math.ceil(Math.abs(d) / (2 * Math.PI) * 24)), out = [];
  for (let i = 1; i <= n; i++) { const t = t0 + d * i / n; out.push([c[0] + r * Math.cos(t), c[1] + r * Math.sin(t), a[2] + (b[2] - a[2]) * i / n]); }
  return out;
}

// ------------------------------------------------------------------ operation and dressup definitions

const num_ = (k, label, title, def) => ({ k, label, kind: "num", title, def });
const sel_ = (k, label, opts, title, def) => ({ k, label, kind: "sel", opts, title, def: def === undefined ? (opts.length ? opts[0][0] : "") : def });
const chk_ = (k, label, title, def) => ({ k, label, kind: "chk", title, def: !!def });
const txt_ = (k, label, title, def) => ({ k, label, kind: "txt", title, def: def || "" });
const area_ = (k, label, title, def) => ({ k, label, kind: "area", title, def: def || "" });
const CW = [["CW", "Climb (CW)"], ["CCW", "Conventional (CCW)"]];
const PATTERNS = [["offset", "Offset"], ["zigzag", "ZigZag"], ["zigzag_offset", "ZigZag then offset"], ["line", "Line"], ["spiral", "Spiral"]];
const STEP = num_("stepover_pct", "Step over (% of D)", "Distance between the passes as a percentage of the tool diameter", 40);
const TEXT_FIELDS = [txt_("text", "Text", "Text to engrave; empty: none"), num_("size", "Size (mm)", "Height of the capital letters", 10), txt_("font", "Font", "Font file name (arial.ttf, DejaVuSans.ttf; empty: the default)"),
                     num_("x", "X (mm)", "Start of the base line in part coordinates", 0), num_("y", "Y (mm)", "", 0), num_("angle", "Angle (deg)", "Rotation of the text about its start", 0),
                     sel_("align", "Align", [["left", "Left"], ["centre", "Centre"], ["right", "Right"]])];
/** Operation types: label, tool shapes, base geometry (faces / edges / points with the face kinds taken), depths and
 *  heights sections, fields of the Operation section, sketch and text sources. */
const OPS = {
  profile: { label: "Profile", finish: { def: "off", leave: ["extra_offset", "Extra offset (mm)"] }, tools: ["endmill", "bullnose", "ballend", "tslot", "custom"], base: { faces: true, edges: true, hint: "Faces or edges of the contour (none: the outline of the part)" }, depths: true,
    fields: [sel_("side", "Side", [["outside", "Outside"], ["inside", "Inside"]]), sel_("direction", "Direction", CW), num_("extra_offset", "Extra offset (mm)", "Material left on the contour", 0),
             num_("passes", "Passes", "Passes stepping out from the contour", 1), num_("extra", "Below the bottom (mm)", "The lowest level below the bottom of the contour", 0.2),
             chk_("process_perimeter", "Process perimeter", "", true), chk_("process_holes", "Process holes", "The inner contours of picked faces"), chk_("process_circles", "Process circles", "Circular holes of picked faces")] },
  pocket: { label: "Pocket Shape", finish: { def: "level", leave: ["extra_offset", "Extra offset (mm)"] }, tools: ["endmill", "bullnose", "tslot", "custom"], base: { faces: true, kinds: ["floor"], required: true, hint: "Floor faces: horizontal faces with the material above them" }, depths: true,
    fields: [sel_("pattern", "Pattern", PATTERNS), STEP, num_("angle", "Angle (deg)", "Direction of the ZigZag and Line passes", 0), sel_("cut_mode", "Cut mode", CW), sel_("start_at", "Start at", [["centre", "Centre"], ["boundary", "Boundary"]]),
             num_("extra_offset", "Extra offset (mm)", "Material left on the walls by the pattern", 0),
             sel_("entry", "Entry", [["helix", "Helix"], ["plunge", "Plunge"]]), num_("helix_pitch", "Helix pitch (mm)", "Depth per turn", 1), chk_("keep_down", "Keep tool down", "Links inside the region at the level", true),
             chk_("use_outline", "Use outline", "Islands ignored: the outline of the floor")] },
  drilling: { label: "Drilling", tools: ["drill", "endmill"], base: { faces: true, kinds: ["hole"], required: true, hint: "Hole faces: cylindrical faces with a vertical axis" }, depths: true,
    fields: [chk_("cycles", "Canned cycles", "G81 / G82 / G83 for the posts that have them (LinuxCNC, Mach3); the others get the moves"), num_("peck", "Peck depth (mm)", "0: one plunge", 0), num_("dwell", "Dwell (s)", "At the bottom of the hole", 0), num_("retract", "Retract height (mm)", "Above the start depth between pecks", 1),
             sel_("through", "Depth", [["auto", "From the hole"], ["through", "Through"], ["bottom", "Hole bottom"]], "From the hole: through when the hole reaches the part bottom", "auto"),
             num_("breakthrough", "Breakthrough (mm)", "Below the part bottom of a through hole", 1), chk_("tip", "Add the drill tip", "The tip length added to the depth", true)] },
  face: { label: "Face", tools: ["endmill", "bullnose", "custom"], base: { faces: true, hint: "Faces to face (with Boundary: faces); none: the stock top" }, depths: true,
    fields: [sel_("boundary", "Boundary", [["stock", "Stock"], ["boundbox", "Part bounding box"], ["faces", "Picked faces"]]), sel_("pattern", "Pattern", [["zigzag", "ZigZag"], ["line", "Line"], ["offset", "Offset"], ["spiral", "Spiral"]]),
             num_("stepover_pct", "Step over (% of D)", "", 60), num_("angle", "Angle (deg)", "Direction of the passes", 0), num_("overhang", "Overhang (mm)", "Tool centre beyond the boundary at the pass ends, in addition to the radius", 1), sel_("cut_mode", "Cut mode", CW)] },
  helix: { label: "Helix", tools: ["endmill", "bullnose"], base: { faces: true, kinds: ["hole"], required: true, hint: "Hole faces larger than the tool" }, depths: true,
    fields: [sel_("direction", "Direction", CW), sel_("start_side", "Start side", [["outside", "Outside"], ["inside", "Inside"]]), num_("stepover_pct", "Step over (% of D)", "", 50),
             num_("extra_offset", "Extra offset (mm)", "Material left on the wall", 0), num_("breakthrough", "Breakthrough (mm)", "Below the part bottom of a through hole", 1)] },
  adaptive: { label: "Adaptive", finish: { def: "off", leave: ["stock_to_leave", "Stock to leave (mm)"] }, tools: ["endmill", "bullnose"], base: { faces: true, kinds: ["floor"], hint: "Floor faces (none: the stock over the part)" }, depths: true,
    fields: [sel_("mode", "Mode", [["clearing", "Clearing"], ["profiling", "Profiling"]]), num_("stepover_pct", "Step over (% of D)", "", 20), num_("tolerance", "Tolerance (mm)", "Path simplification", 0.02),
             num_("helix_angle", "Helix ramp angle (deg)", "", 3), num_("helix_diameter", "Helix diameter (mm)", "0: half the tool diameter", 0), num_("lift", "Lift (mm)", "Lift between separate regions", 1),
             num_("stock_to_leave", "Stock to leave (mm)", "", 0), num_("passes", "Passes (profiling)", "", 2), chk_("use_outline", "Use outline", "Islands ignored")] },
  slot: { label: "Slot", tools: ["endmill", "bullnose", "ballend", "tapered", "tslot", "custom"], base: { faces: true, edges: true, points: 2, hint: "Two points (click the model), an edge (a line or an arc) or the slot floor" }, depths: true,
    fields: [num_("extend_start", "Extend start (mm)", "", 0), num_("extend_end", "Extend end (mm)", "", 0), num_("radius_offset", "Radius offset (mm)", "Of a circular slot from an arc edge", 0),
             sel_("layer", "Layer mode", [["multi", "Multi pass"], ["single", "Single pass"]]), chk_("reverse", "Reverse direction")] },
  engrave: { label: "Engrave", tools: ["vbit", "chamfer", "ballend", "tapered", "endmill"], base: { edges: true, hint: "Edges to follow, or a saved sketch, or a text" }, depths: true, sketch: true, text: true,
    fields: [num_("depth", "Depth (mm)", "Below the surface (when the final depth is empty)", 0.3), num_("start_vertex", "Start vertex", "Start of a closed path", 0)] },
  deburr: { label: "Deburr", tools: ["vbit", "chamfer"], base: { edges: true, faces: true, required: true, hint: "Edges (or the outer edges of faces) to chamfer" }, depths: false,
    fields: [num_("width", "Width (mm)", "Width of the chamfer", 1), num_("extra_depth", "Extra depth (mm)", "Tip below the chamfer", 0.5), sel_("direction", "Direction", CW), num_("entry", "Entry point", "Start vertex of a closed path", 0)] },
  vcarve: { label: "Vcarve", tools: ["vbit"], base: { faces: true, hint: "Faces whose outlines are carved, or a saved sketch with closed loops, or a text" }, depths: true, sketch: true, text: true,
    fields: [num_("discretize", "Discretize (mm)", "Step along the outline for the centre lines", 0.2), num_("threshold", "Threshold", "Centre lines of the inner corners dropped below this (0..0.9)", 0.25), num_("colinear", "Colinear filter (mm)", "", 0.01)] },
  undercut: { label: "Undercut", finish: { def: "level", leave: ["allowance", "Allowance (mm)"] }, tools: ["dovetail"], base: { faces: true, kinds: ["undercut"], required: true, hint: "Undercut faces: inclined faces with the material above them, straight and open at both ends" }, depths: false,
    fields: [num_("stepover", "Step over (mm)", "Step of the roughing passes into the undercut", 1), num_("allowance", "Allowance (mm)", "Left by the roughing passes and removed by the finish pass", 0.2), num_("runout", "Run-out (mm)", "Cutter beyond the face ends", 2), chk_("reverse", "Reverse")] },
  pocket3d: { label: "3D Pocket", tools: ["endmill", "bullnose", "ballend", "tapered", "custom"], base: { faces: true, required: true, hint: "Faces: the volume above them is cleared" }, depths: true,
    fields: [sel_("boundary", "Boundary", [["faces", "Picked faces"], ["stock", "Stock"]]), sel_("pattern", "Pattern", PATTERNS), num_("stepover_pct", "Step over (% of D)", "", 40), num_("angle", "Angle (deg)", "", 0),
             num_("sample", "Sample interval (mm)", "Grid of the height map", 0.5), num_("depth_offset", "Depth offset (mm)", "Left on the surface", 0), sel_("cut_mode", "Cut mode", CW), sel_("entry", "Entry", [["helix", "Helix"], ["plunge", "Plunge"]]), num_("helix_pitch", "Helix pitch (mm)", "", 1)] },
  surface: { label: "3D Surface", tools: ["ballend", "tapered", "bullnose", "endmill", "custom"], base: { faces: true, hint: "Faces of the area (with Boundary: faces); none: the stock" }, depths: true,
    fields: [sel_("boundary", "Boundary", [["stock", "Stock"], ["faces", "Picked faces"]]), num_("boundary_adjust", "Boundary adjust (mm)", "Positive: outward", 0), sel_("boundary_shape", "Boundary shape", [["faces", "Faces"], ["boundbox", "Bounding box"]]),
             sel_("pattern", "Pattern", [["zigzag", "ZigZag"], ["line", "Line"], ["circular", "Circular"], ["circular_zigzag", "Circular ZigZag"], ["offset", "Offset"], ["spiral", "Spiral"]]), num_("angle", "Angle (deg)", "", 0),
             num_("stepover_pct", "Step over (% of D)", "", 25), num_("sample", "Sample interval (mm)", "Grid of the height map and step along the lines", 0.5), num_("depth_offset", "Depth offset (mm)", "Left on the surface", 0),
             sel_("layer", "Layer mode", [["single", "Single pass"], ["multi", "Multi pass"]]), chk_("optimize", "Optimize", "Collinear points removed", true), chk_("boundary_enforce", "Boundary enforcement", "", true)] },
  waterline: { label: "Waterline", tools: ["endmill", "ballend", "tapered", "bullnose", "custom"], base: { faces: true, hint: "Faces of the area (with Boundary: faces); none: the stock" }, depths: true,
    fields: [sel_("boundary", "Boundary", [["stock", "Stock"], ["faces", "Picked faces"]]), num_("boundary_adjust", "Boundary adjust (mm)", "", 0), num_("sample", "Sample interval (mm)", "", 0.5), num_("depth_offset", "Depth offset (mm)", "", 0),
             sel_("cut_mode", "Cut mode", CW), chk_("optimize", "Optimize", "", true), chk_("clear_last", "Clear last level", "The last level cleared as a pocket")] },
  thread: { label: "Thread milling", tools: ["threadmill", "endmill"], base: { faces: true, kinds: ["hole"], required: true, hint: "Hole faces (internal) or cylindrical bosses (external) with a vertical axis" }, depths: true,
    fields: [sel_("side", "Thread", [["internal", "Internal"], ["external", "External"]]), num_("pitch", "Pitch (mm)", "", 1.5), num_("diameter", "Thread diameter (mm)", "Major diameter; empty: hole diameter + pitch (internal), boss diameter (external)"),
             num_("depth", "Thread depth (mm)", "Radial; empty: 0.5413 x pitch internal, 0.6134 x pitch external"), sel_("hand", "Hand", [["right", "Right"], ["left", "Left"]]),
             sel_("direction", "Direction", [["climb", "Climb"], ["conventional", "Conventional"]]), num_("passes", "Radial passes", "", 1)] },
  hop: { label: "Hop", supplemental: true, fields: [num_("height", "Height Z (mm)", "Rapid lift to this height (job coordinates); empty: the clearance height")] },
  probe: { label: "Probe", supplemental: true, fields: [num_("nx", "Points X", "", 3), num_("ny", "Points Y", "", 3), num_("xmin", "X min (mm)", "Empty: the stock"), num_("xmax", "X max (mm)"), num_("ymin", "Y min (mm)"), num_("ymax", "Y max (mm)"),
             num_("start_z", "Start Z (mm)", "Empty: stock top + 2 mm"), num_("depth", "Probe to Z (mm)", "Empty: stock top - 5 mm"), num_("feed", "Probe feed (mm/min)", "", 50), txt_("output", "Output file", "LinuxCNC: the probe results written to this file (PROBEOPEN)")] },
  fixture: { label: "Fixture", supplemental: true, fields: [sel_("fixture", "Work offset", ["G54", "G55", "G56", "G57", "G58", "G59"].map(g => [g, g])), num_("sx", "Shift X (mm)", "Estlcam: the coordinates shifted", 0), num_("sy", "Shift Y (mm)", "", 0), num_("sz", "Shift Z (mm)", "", 0)] },
  comment: { label: "Comment", supplemental: true, fields: [txt_("text", "Text")] },
  stop: { label: "Stop", supplemental: true, fields: [chk_("optional", "Optional stop (M01)")] },
  custom: { label: "Custom", supplemental: true, fields: [area_("gcode", "G-code", "Lines written as they are")] },
  copy: { label: "Copy", derived: true, fields: [sel_("of", "Operation", [])] },
  array: { label: "Array", derived: true, fields: [sel_("of", "Operation", []), sel_("kind", "Type", [["linear", "Linear"], ["polar", "Polar"]]), num_("count", "Copies", "Including the base position", 2),
           num_("dx", "Offset X (mm)", "", 20), num_("dy", "Offset Y (mm)", "", 0), num_("angle", "Angle (deg)", "Polar: total angle", 360), num_("cx", "Centre X (mm)", "", 0), num_("cy", "Centre Y (mm)", "", 0)] },
};
const DRESSUPS = {
  tag: { label: "Tag", fields: [num_("count", "Tags", "Tags spaced along the closed path", 4), num_("width", "Width (mm)", "", 6), num_("height", "Height (mm)", "", 2), num_("angle", "Angle (deg)", "Of the flanks; 90: vertical", 45)] },
  ramp: { label: "Ramp entry", fields: [sel_("method", "Method", [["ramp1", "RampMethod1 (ramp, back at the level)"], ["ramp2", "RampMethod2 (ramp then feed on)"], ["zigzag", "ZigZag"], ["helix", "Helix"]]), num_("angle", "Angle (deg)", "", 3), chk_("use_start_depth", "Ramp from the start depth"), num_("feed", "Ramp feed (mm/min)", "Empty: the plunge feed")] },
  leadinout: { label: "Lead in/out", fields: [sel_("style", "Style", [["arc", "Arc"], ["tangent", "Tangent"], ["perpendicular", "Perpendicular"]]), num_("length", "Length (mm)", "Radius of the arc or length of the line", 5), chk_("lead_in", "Lead in", "", true), chk_("lead_out", "Lead out", "", true), num_("extend", "Extend (mm)", "", 0)] },
  dogbone: { label: "Dogbone", fields: [sel_("style", "Style", [["dogbone", "Dogbone"], ["tbone_h", "T-bone horizontal"], ["tbone_v", "T-bone vertical"], ["tbone_long", "T-bone long edge"], ["tbone_short", "T-bone short edge"]]), sel_("side", "Side", [["left", "Left"], ["right", "Right"]]),
             sel_("incision", "Incision", [["adaptive", "Adaptive"], ["fixed", "Fixed"], ["custom", "Custom"]]), num_("length", "Length (mm)", "Custom incision", 0)] },
  axismap: { label: "Axis map", fields: [sel_("axis", "Mapped axis", [["y", "Y to A"], ["x", "X to A"]]), num_("radius", "Radius (mm)", "Radius of the part on the rotary axis: A = coordinate / (2 pi r) x 360 deg", 10), chk_("invert", "Invert", "A turns the other way")] },
  boundary: { label: "Boundary", fields: [num_("xmin", "X min (mm)"), num_("xmax", "X max (mm)"), num_("ymin", "Y min (mm)"), num_("ymax", "Y max (mm)"), chk_("inside", "Keep inside", "", true)] },
};
const ORIGIN_XY = [["stock_min", "Stock corner (min X, min Y)"], ["stock_centre", "Stock centre"], ["part", "Part origin"], ["point", "Picked vertex"]];
const ORIGIN_Z = [["stock_top", "Stock top"], ["stock_bottom", "Stock bottom (table)"], ["part", "Part origin"], ["point", "Picked vertex"]];
const TOOL_MATS = [["carbide", "Carbide"], ["hss", "HSS"]];
const COATINGS = [["none", "Uncoated"], ["tin", "TiN"], ["ticn", "TiCN"], ["tialn", "TiAlN"], ["altin", "AlTiN"], ["dlc", "DLC"], ["zrn", "ZrN"]];
const SHAPES = [["endmill", "End mill"], ["ballend", "Ball end mill"], ["bullnose", "Bull nose"], ["vbit", "V bit"], ["chamfer", "Chamfer"], ["drill", "Drill"], ["dovetail", "Dovetail"], ["tapered", "Tapered ball nose"],
                ["threadmill", "Thread mill"], ["tslot", "T-slot cutter"], ["custom", "Custom profile"]];
/** The geometry fields of the bit editor by shape: [key, label, help]; then the neck and shank fields of every shape. */
const BIT_GEOM = {
  endmill: [["d", "Diameter D (mm)"], ["height", "Cutting height (mm)", "Length of the flutes"]],
  ballend: [["d", "Diameter D (mm)"], ["height", "Cutting height (mm)", "Length of the flutes, from the tip"]],
  bullnose: [["d", "Diameter D (mm)"], ["corner", "Corner radius (mm)"], ["height", "Cutting height (mm)"]],
  vbit: [["d", "Diameter D (mm)", "Diameter at the top of the cone"], ["angle", "Included angle (deg)"], ["tip", "Tip diameter (mm)", "Flat at the tip; 0: a point"], ["height", "Cutting height (mm)"]],
  chamfer: [["d", "Diameter D (mm)", "Largest diameter of the cutting edge"], ["angle", "Included angle (deg)"], ["tip", "Tip diameter (mm)"], ["height", "Cutting height (mm)"]],
  drill: [["d", "Diameter D (mm)"], ["angle", "Point angle (deg)"], ["height", "Flute length (mm)", "Above the point"]],
  dovetail: [["d", "Large diameter D (mm)", "At the bottom of the cutter"], ["angle", "Flank angle (deg)", "Between the flank and the base plane (60 for a 60 deg dovetail)"], ["height", "Flank height (mm)"]],
  tapered: [["corner", "Tip radius (mm)"], ["angle", "Taper per side (deg)"], ["height", "Cutting height (mm)"]],
  threadmill: [["d", "Diameter over the tooth D (mm)"], ["angle", "Thread angle (deg)"], ["height", "Cutting height (mm)"]],
  tslot: [["d", "Disc diameter D (mm)"], ["height", "Disc thickness (mm)", "The cutting width of the disc"]],
  custom: [],
};
const BIT_BODY = [["neck", "Neck diameter (mm)", "Empty: D (a T-slot cutter: smaller than D)"], ["neck_length", "Neck length (mm)", "From the top of the cutting part"], ["shank", "Shank diameter (mm)"], ["shank_length", "Shank length (mm)", "Out of the holder"]];
const DEPTH_FIELDS = [["start_depth", "Start depth (mm)", "Top of the cut in part coordinates; empty: the stock top (the floor top for pockets)"], ["final_depth", "Final depth (mm)", "Bottom of the cut; empty: from the geometry"],
                      ["step_down", "Step down (mm)", "Depth of a level; empty: the setup sheet"], ["finish_depth", "Finish depth (mm)", "Height of the last level; empty: the setup sheet"]];
const HEIGHT_FIELDS = [["clearance_height", "Clearance height (mm)", "Rapid moves between operations; empty: start depth + the setup sheet offset"], ["safe_height", "Safe height (mm)", "Rapid moves inside the operation; empty: start depth + the setup sheet offset"]];

function blankDoc(name) {
  return { name: name || "cam", source: { type: "part", name: "" }, stock: { kind: "offsets", xneg: 1, xpos: 1, yneg: 1, ypos: 1, zneg: 0, zpos: 1 },
           origin: { xy: "stock_min", z: "stock_top" }, setup: Object.assign({}, (CM.meta && CM.meta.setup) || { clearance_offset: 5, safe_offset: 3, step_down: 2, finish_depth: 0, hrapid: 3000, vrapid: 1000, coolant: "none" }),
           tools: [], post: "estlcam", output: { folder: "", name: "" }, operations: [], next: 1 };
}
function nid(p) { return p + (CM.doc.next++); }
function opOf(id) { return (CM.doc.operations || []).find(o => o.id === id); }
function opIndex(id) { return (CM.doc.operations || []).findIndex(o => o.id === id); }
function tcOf(id) { return (CM.doc.tools || []).find(t => t.id === id); }
function bitOf(id) { return CM.bits.find(t => t.id === id); }
function bitOfTc(tcid) { const tc = tcOf(tcid); return tc ? bitOf(tc.bit) : null; }
function opLabel(o) { return (OPS[o.type] || {}).label || (CM.meta && CM.meta.op_names && CM.meta.op_names[o.type]) || o.type; }
function hasSource() { return !!(CM.doc && CM.doc.source && CM.doc.source.name); }
/** A change of the document: dirty, the result of the last run is stale, a preview is scheduled. */
function changed(preview = true) {
  CM.dirty = true;
  if (FM) FM.render();
  if (preview) schedulePreview();
}

// ------------------------------------------------------------------ 3D view

function initThree() {
  const box = $("#cm-view");
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  box.insertBefore(renderer.domElement, box.firstChild);
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-100, 100, 100, -100, -100000, 100000);
  camera.up.set(0, 0, 1);
  camera.position.set(200, -200, 200);
  const controls = new TumbleControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.screenSpacePanning = true;
  controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.PAN };
  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.7);
  camera.add(d1);
  d1.position.set(1, 1, 2);
  scene.add(camera);
  const group = new THREE.Group();
  scene.add(group);
  const overlay = new THREE.Group();
  scene.add(overlay);
  updateAxes(scene, null, true);
  CM.three = { renderer, scene, camera, controls, group, overlay, box, zoomed: false, faceMesh: null, edgeLines: [], geos: [] };
  controls.addEventListener("change", render3);
  camera.userData.target = controls.target;
  CM.three.cube = createNavCube(box, camera, viewDir);
  let down = null;
  box.addEventListener("pointerdown", e => { if (e.target === renderer.domElement) startPartDrag(e); }, true);
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointermove", e => { if (!e.buttons) hoverView(e); });
  renderer.domElement.addEventListener("pointerleave", () => { clearHover(); render3(); });
  renderer.domElement.addEventListener("contextmenu", e => e.preventDefault());
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.abs(e.clientX - down[0]) + Math.abs(e.clientY - down[1]) > 4) { down = null; return; }
    down = null;
    if (e.button === 1) { const h = hitAt(e); if (h) { CM.three.controls.setTarget(h.point.clone(), true); render3(); } return; }
    if (e.button === 0) clickView(e);
  });
  new ResizeObserver(resize3).observe(box);
  resize3();
}
function resize3() {
  const t = CM.three;
  if (!t) return;
  const w = t.box.clientWidth || 1, h = t.box.clientHeight || 1;
  t.renderer.setSize(w, h);
  const c = t.camera, half = (c.top - c.bottom) / 2 || 100;
  c.left = -half * w / h; c.right = half * w / h;
  c.updateProjectionMatrix();
  render3();
}
function render3() { const t = CM.three; if (!t) return; t.renderer.render(t.scene, t.camera); if (t.cube) t.cube.render(); }
function viewDir(dir, up) {
  const t = CM.three;
  const dist = t.camera.position.distanceTo(t.controls.target) || 1;
  const d = dir.clone().normalize();
  const cur = new THREE.Vector3(0, 1, 0).applyQuaternion(t.camera.quaternion);
  let best = up, bd = -Infinity;
  for (const a of [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]) {
    const v = new THREE.Vector3(...a);
    if (Math.abs(v.dot(d)) > 1e-6) continue;
    const s = v.dot(cur);
    if (s > bd) { bd = s; best = v; }
  }
  t.camera.up.copy(best);
  t.camera.position.copy(t.controls.target.clone().add(d.multiplyScalar(dist)));
  t.controls.update();
  render3();
}
function view(name) {
  const t = CM.three;
  if (!t) return;
  const bb = CM.bbox || [-50, -50, -50, 50, 50, 50];
  const c = new THREE.Vector3((bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2);
  const size = Math.max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], 1);
  const dirs = { iso: [1, -1, 1], front: [0, -1, 0], top: [0, 0, 1], right: [1, 0, 0] };
  if (name !== "fit") {
    const d = new THREE.Vector3(...dirs[name]).normalize();
    t.camera.up.set(0, 0, 1);
    if (name === "top") t.camera.up.set(0, 1, 0);
    t.camera.position.copy(c.clone().add(d.multiplyScalar(size * 4)));
  } else {
    const d = t.camera.position.clone().sub(t.controls.target).normalize();
    t.camera.position.copy(c.clone().add(d.multiplyScalar(size * 4)));
  }
  t.controls.target.copy(c);
  const w = t.box.clientWidth || 1, h = t.box.clientHeight || 1;
  const half = size * 0.75;
  t.camera.top = half; t.camera.bottom = -half; t.camera.left = -half * w / h; t.camera.right = half * w / h;
  t.camera.zoom = 1;
  t.camera.updateProjectionMatrix();
  t.controls.update();
  render3();
}
function rayAt(e) {
  const t = CM.three;
  const r = t.renderer.domElement.getBoundingClientRect();
  const nd = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster();
  rc.setFromCamera(nd, t.camera);
  rc.params.Line.threshold = (t.camera.right - t.camera.left) / t.camera.zoom / r.width * 6;   // 6 px
  return rc;
}
function hitAt(e) { const t = CM.three; if (!t.faceMesh) return null; const h = rayAt(e).intersectObject(t.faceMesh, false); return h.length ? h[0] : null; }
/** What the cursor is over: {kind: "face", index} | {kind: "edge", index} | null; edges before faces within 6 px
 *  when the active step takes edges. */
function pickAt(e, kinds) {
  const t = CM.three;
  if (!CM.geo || !t.faceMesh) return null;
  const rc = rayAt(e);
  const px = (t.camera.right - t.camera.left) / t.camera.zoom / t.renderer.domElement.getBoundingClientRect().width;
  const fh = rc.intersectObject(t.faceMesh, false);
  const face = fh.length ? { kind: "face", index: CM.geo.face_of_tri[fh[0].faceIndex], dist: fh[0].distance, point: [fh[0].point.x, fh[0].point.y, fh[0].point.z] } : null;
  if (kinds.includes("edge") && t.edgeLines.length) {
    const hits = rc.intersectObjects(t.edgeLines, false);
    for (const h of hits) h.dr = rc.ray.distanceToPoint(h.point);
    hits.sort((a, b) => (Math.abs(a.dr - b.dr) > px * 1.5 ? a.dr - b.dr : a.distance - b.distance));
    if (hits.length && (!face || hits[0].distance < face.dist + px * 3)) return { kind: "edge", index: hits[0].object.userData.index, point: [hits[0].point.x, hits[0].point.y, hits[0].point.z] };
  }
  if (face && (kinds.includes("face") || kinds.includes("point"))) return face;
  return null;
}
function clearHover() {
  const t = CM.three;
  if (!t || !t.hover) return;
  t.scene.remove(t.hover);
  t.hover = null;
  t.renderer.domElement.style.cursor = "";
}
function faceGeo(fi) {
  const m = CM.geo, pos = [];
  m.triangles.forEach((tr, k) => { if (m.face_of_tri[k] === fi) for (const v of tr) pos.push(...m.vertices[v]); });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  return g;
}
function facesGeo(set) {
  const m = CM.geo, pos = [];
  m.triangles.forEach((tr, k) => { if (set.has(m.face_of_tri[k])) for (const v of tr) pos.push(...m.vertices[v]); });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  return g;
}
function edgeGeo(set) {
  const m = CM.geo, pos = [];
  m.edges.forEach((pl, i) => { if (set.has(i)) for (let k = 0; k + 1 < pl.length; k++) pos.push(...pl[k], ...pl[k + 1]); });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  return g;
}
/** The pick step of the command window: {kinds: ["face", "edge", "point"], faceKinds} or null. */
function pickStep() {
  const c = CM.cmd;
  if (c && c.place) return c.pick ? { kinds: [c.pickKind === "edges" ? "edge" : "face"], faceKinds: null, place: true, vertex: c.pickKind === "vertices" } : null;
  if (!c || c.dr !== undefined) return null;
  const o = opOf(c.id);
  if (!o || c.step !== 0) return null;
  const b = (OPS[o.type] || {}).base;
  if (!b) return null;
  const kinds = [];
  if (b.faces && c.mode !== "edges" && c.mode !== "points") kinds.push("face");
  if (b.edges && c.mode !== "faces" && c.mode !== "points") kinds.push("edge");
  if (b.points && c.mode === "points") kinds.push("point");
  return { kinds, faceKinds: b.kinds || null, points: b.points, op: o };
}
function hoverView(e) {
  if (CM.measure) { hoverMeasure(e); return; }
  if (CM.zeroPick || (CM.cmd && CM.cmd.place && CM.cmd.pick && CM.cmd.pickKind === "vertices")) { hoverZero(e); return; }
  const t = CM.three;
  const ps = pickStep();
  if (!t || !CM.doc || !ps) { if (t) { clearHover(); render3(); } return; }
  clearHover();
  const h = pickAt(e, ps.kinds);
  let ok = false;
  if (h && h.kind === "face" && ps.kinds.includes("face") && (!ps.faceKinds || ps.faceKinds.includes((CM.geo.face_kind || [])[h.index]))) {
    const fm = new THREE.Mesh(faceGeo(h.index), new THREE.MeshBasicMaterial({ color: COLORS.sel, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthTest: false }));
    fm.renderOrder = 10;
    t.hover = fm; t.scene.add(fm); ok = true;
  } else if (h && h.kind === "edge") {
    const l = new THREE.LineSegments(edgeGeo(new Set([h.index])), new THREE.LineBasicMaterial({ color: COLORS.sel, depthTest: false, linewidth: 3 }));
    l.renderOrder = 10;
    t.hover = l; t.scene.add(l); ok = true;
  } else if (h && ps.kinds.includes("point")) ok = true;
  t.renderer.domElement.style.cursor = ok ? "crosshair" : "";
  render3();
}
/** Index of the face of the geometry a stored face key refers to (nearest centre), or -1. */
function faceIndex(key) {
  if (!CM.geo || !key || !key.c) return -1;
  let best = -1, bd = Infinity;
  CM.geo.face_keys.forEach((k, i) => {
    if (!k) return;
    const d = Math.hypot(k.c[0] - key.c[0], k.c[1] - key.c[1], k.c[2] - key.c[2]);
    if (d < bd) { bd = d; best = i; }
  });
  return bd < 0.05 ? best : -1;
}
function edgeIndex(key) {
  if (!CM.geo || !key || !key.mid) return -1;
  let best = -1, bd = Infinity;
  (CM.geo.edge_keys || []).forEach((k, i) => {
    if (!k || !k.mid) return;
    const d = Math.hypot(k.mid[0] - key.mid[0], k.mid[1] - key.mid[1], k.mid[2] - key.mid[2]);
    if (d < bd) { bd = d; best = i; }
  });
  return bd < 0.05 ? best : -1;
}
function clickView(e) {
  if (CM.measure) { clickMeasure(e); return; }
  if (CM.zeroPick) { clickZero(e); return; }
  const ps = pickStep();
  if (!ps) { return; }
  if (ps.vertex) { const v = vertexAt(e); if (v) placePick({ vertex: v }); else status("No vertex under the cursor", true); return; }
  const h = pickAt(e, ps.kinds);
  if (!h) return;
  if (ps.place) {
    if (ps.vertex) { const v = vertexAt(e); if (v) placePick({ vertex: v }); else status("No vertex under the cursor", true); return; }
    if (h.kind === "face") placePick({ face: h.index });
    else if (h.kind === "edge") placePick({ edge: CM.geo.edge_keys[h.index].mid });
    return;
  }
  const op = ps.op;
  if (h.kind === "face" && ps.kinds.includes("point")) {
    const pts = op.points || (op.points = []);
    if (pts.length >= ps.points) pts.length = 0;
    pts.push([Math.round(h.point[0] * 1000) / 1000, Math.round(h.point[1] * 1000) / 1000, Math.round(h.point[2] * 1000) / 1000]);
    status(`${pts.length} of ${ps.points} point(s) of ${op.name}`);
  } else if (h.kind === "face") {
    if (ps.faceKinds && !ps.faceKinds.includes((CM.geo.face_kind || [])[h.index])) { status("Pick " + (OPS[op.type].base.hint || "a face"), true); return; }
    const key = CM.geo.face_keys[h.index];
    const k = (op.faces || []).findIndex(f => faceIndex(f) === h.index);
    if (k >= 0) op.faces.splice(k, 1); else (op.faces = op.faces || []).push({ c: key.c, n: key.n, area: key.area });
    status(`${op.faces.length} face(s) of ${op.name} (click again to deselect)`);
  } else if (h.kind === "edge") {
    const key = CM.geo.edge_keys[h.index];
    const k = (op.edges || []).findIndex(f => edgeIndex(f) === h.index);
    if (k >= 0) op.edges.splice(k, 1); else (op.edges = op.edges || []).push({ mid: key.mid, len: key.len });
    status(`${op.edges.length} edge(s) of ${op.name} (click again to deselect)`);
  }
  changed();
  renderCommand(); drawSelection();
}

// ------------------------------------------------------------------ geometry, setup and preview

async function loadGeometry() {
  const seq = ++CM.seq;
  const src = CM.doc.source || {};
  if (!src.name) { CM.geo = null; CM.res = null; CM.setup = null; $("#cm-info").textContent = "Choose a part"; draw(); renderAll(); return; }
  $("#cm-info").textContent = "Loading the part...";
  try {
    const r = await postJSON("/api/cam/geometry", { cam: CM.doc });
    const g = await r.json();
    if (seq !== CM.seq) return;
    CM.geo = g;
    if (CM.measure) { CM.measure.items = []; CM.measure.res = null; renderMeasure(); }     // the indices of the old geometry
    const nk = k => (g.face_kind || []).filter(x => x === k).length;
    $("#cm-info").textContent = `${src.name}: ${g.face_keys.length} faces (${nk("floor")} floor, ${nk("hole")} hole, ${g.undercuts.length} undercut), ${fmt(g.volume_mm3 / 1000, 4)} cm^3, ${g.bbox ? g.bbox.slice(3).map((v, i) => fmt(v - g.bbox[i], 5)).join(" x ") + " mm" : ""}`;
    if (CM.three) CM.three.zoomed = false;
    await loadSetup();
    draw(); renderAll();
    if ((CM.doc.operations || []).length && !placing()) schedulePreview(0);
  } catch (e) { if (seq === CM.seq) { CM.geo = null; $("#cm-info").textContent = ""; showErr(e); draw(); renderAll(); } }
}
let setupSeq = 0;
async function loadSetup() {
  const seq = ++setupSeq;
  if (!hasSource()) { CM.setup = null; return; }
  try {
    const su = await (await postJSON("/api/cam/setup", { cam: CM.doc })).json();
    if (seq === setupSeq) CM.setup = su;
  } catch (e) { if (seq === setupSeq) CM.setup = null; }
}
/** Preview after a change: the operations up to the edited one (the whole job when none is edited), 500 ms after
 *  the last change; the earlier operations come from the server cache. */
function schedulePreview(delay = 500) {
  if (CM.previewTimer) clearTimeout(CM.previewTimer);
  CM.previewTimer = setTimeout(runPreview, delay);
}
/** The Placement window is open: placement changes load the part and the stock only; the toolpaths are computed at OK. */
function placing() { return !!(CM.cmd && CM.cmd.place); }
/** Toolpaths of an earlier placement dropped: a pending or running preview is discarded (the server stops it). */
function dropPreview() {
  if (CM.previewTimer) { clearTimeout(CM.previewTimer); CM.previewTimer = null; }
  CM.previewSeq = (CM.previewSeq || 0) + 1;
  CM.res = null; CM.resUpto = null;
  postJSON("/api/cam/cancel", { preview: CM.client }).catch(() => {});
}
async function runPreview() {
  CM.previewTimer = null;
  if (!hasSource() || !(CM.doc.operations || []).length) { CM.res = null; draw(); renderTree(); renderProps(); return; }
  if (placing()) return;
  const upto = CM.cmd && CM.cmd.id ? opIndex(CM.cmd.id) : null;
  const seq = ++CM.previewSeq;
  $("#cm-info").textContent = "Computing the toolpaths...";
  try {
    const r = await postJSON("/api/cam/run", { cam: CM.doc, upto, meshes: true, preview: CM.client });
    const res = await r.json();
    if (seq !== CM.previewSeq || res.cancelled) return;
    CM.res = res; CM.resUpto = upto;
    const bad = res.operations.filter(o => !o.ok);
    $("#cm-info").textContent = bad.length ? `${bad[0].name}: ${bad[0].errors[0]}` : `${res.operations.length} operation(s), ${fmt(res.operations.reduce((s, o) => s + (o.time_s || 0), 0) / 60, 3)} min`;
  } catch (e) { if (seq === CM.previewSeq) { CM.res = null; $("#cm-info").textContent = e.message || String(e); } }
  renderTree(); renderProps(); renderCommand(); initPlay(); draw();
}

function clearView() {
  const t = CM.three;
  for (const g of t.geos) g.dispose();
  t.geos = [];
  t.group.clear();
  t.faceMesh = null; t.edgeLines = [];
}
function track(g) { CM.three.geos.push(g); return g; }
function meshGeo(m) {
  const geo = track(new THREE.BufferGeometry());
  geo.setAttribute("position", new THREE.Float32BufferAttribute(m.vertices.flat(), 3));
  geo.setIndex(m.triangles.flat());
  geo.computeVertexNormals();
  geo.computeBoundingBox();
  const pos = [];
  for (const pl of m.edges || []) for (let k = 0; k + 1 < pl.length; k++) pos.push(...pl[k], ...pl[k + 1]);
  const edgeGeo = track(new THREE.BufferGeometry());
  edgeGeo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  return { geo, edgeGeo };
}
/** The view turned about a new target: the point moved to the centre of the view, the camera moved with it. */
function focusPoint(c) {
  const t = CM.three;
  if (!t) return;
  const d = new THREE.Vector3(c[0], c[1], c[2]).sub(t.controls.target);
  t.controls.target.add(d);
  t.camera.position.add(d);
  t.controls.update();
  render3();
  status(`View centred at X ${fmt(c[0])} Y ${fmt(c[1])} Z ${fmt(c[2])} mm (job)`);
}
function addMesh(m, color, opts) {
  const t = CM.three;
  const { geo, edgeGeo } = meshGeo(m);
  const mat = new THREE.MeshStandardMaterial(Object.assign({ color, metalness: 0.1, roughness: 0.7, side: THREE.DoubleSide,
                                                             polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }, opts || {}));
  const mesh = new THREE.Mesh(geo, mat);
  t.group.add(mesh);
  if ($("#cm-edges").checked && (m.edges || []).length) t.group.add(new THREE.LineSegments(edgeGeo, new THREE.LineBasicMaterial({ color: 0x1d2125, transparent: !!(opts && opts.transparent), opacity: opts && opts.transparent ? 0.3 : 1 })));
  return mesh;
}
/** The moves of an operation record as line segments by kind. */
function pathSegments(moves, segs) {
  let prev = null;
  for (const m of moves || []) {
    if (!m.p) continue;
    if (prev) {
      if (m.k === "arc") { let q = prev; for (const a of arcPoints(prev, m.p, m.c, m.cw)) { segs.arc.push(...q, ...a); q = a; } }
      else (segs[m.k] || segs.feed).push(...prev, ...m.p);
    }
    prev = m.p;
  }
}
/** Everything in the view: the part (faces of the kind being picked tinted), the stock outline and the machine
 *  zero, the stock and the remaining material after the operations, the toolpaths (the edited operation in full
 *  colour, the others dimmed while a command is open). */
function draw() {
  const t = CM.three;
  if (!t) return;
  clearHover();
  clearView();
  const box = new THREE.Box3();
  if (CM.geo && $("#cm-showpart").checked && !CM.hidden.model && !CM.hidden.job) {
    const n0 = t.group.children.length;
    const mesh = addMesh(CM.geo, COLORS.part);
    for (const o of t.group.children.slice(n0)) o.userData.part = true;
    t.faceMesh = mesh;
    box.expandByObject(mesh);
    const ps = pickStep();
    if (ps && ps.kinds.includes("edge")) {
      // the edges as pickable lines
      CM.geo.edges.forEach((pl, i) => {
        if (pl.length < 2) return;
        const g = track(new THREE.BufferGeometry());
        g.setAttribute("position", new THREE.Float32BufferAttribute(pl.flat(), 3));
        const l = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0x1d2125 }));
        l.userData = { index: i };
        t.group.add(l); t.edgeLines.push(l);
      });
    }
    const under = new Set($("#cm-showunder").checked ? CM.geo.undercuts || [] : []);
    if (ps && ps.faceKinds) (CM.geo.face_kind || []).forEach((k, i) => { if (ps.faceKinds.includes(k)) under.add(i); });
    if (under.size) {
      const fm = new THREE.Mesh(track(facesGeo(under)), new THREE.MeshBasicMaterial({ color: ps && ps.faceKinds ? COLORS.pickable : COLORS.under, transparent: true, opacity: 0.3, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
      t.group.add(fm);
    }
  }
  const su = CM.setup;
  if (su && su.stock_bbox && !CM.hidden.stock && !CM.hidden.job) {
    const b = su.stock_bbox, pos = [];
    if (su.stock_mesh && (su.stock_mesh.edges || []).length) {
      // STEP stock: the edges of the solid (its bounding box is not the stock)
      for (const pl of su.stock_mesh.edges) for (let k = 0; k + 1 < pl.length; k++) pos.push(...pl[k], ...pl[k + 1]);
    } else {
      const c = [[b[0], b[1]], [b[3], b[1]], [b[3], b[4]], [b[0], b[4]]];
      for (let k = 0; k < 4; k++) {
        const p = c[k], q = c[(k + 1) % 4];
        pos.push(p[0], p[1], b[2], q[0], q[1], b[2], p[0], p[1], b[5], q[0], q[1], b[5], p[0], p[1], b[2], p[0], p[1], b[5]);
      }
    }
    const g = track(new THREE.BufferGeometry());
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    const l = new THREE.LineSegments(g, new THREE.LineDashedMaterial({ color: 0x5c7cfa, dashSize: 2, gapSize: 1.5 }));
    l.computeLineDistances();
    t.group.add(l);
    box.expandByObject(l);
  }
  if (su && su.origin && !CM.hidden.job) {
    const o = su.origin, b = su.stock_bbox, s = Math.max(5, Math.min(b[3] - b[0], b[4] - b[1]) * 0.15);
    for (const [d, col] of [[[1, 0, 0], 0xe03131], [[0, 1, 0], 0x2b8a3e], [[0, 0, 1], 0x1c7ed6]]) {
      const ga = track(new THREE.BufferGeometry());
      ga.setAttribute("position", new THREE.Float32BufferAttribute([o[0], o[1], o[2], o[0] + d[0] * s, o[1] + d[1] * s, o[2] + d[2] * s], 3));
      const la = new THREE.Line(ga, new THREE.LineBasicMaterial({ color: col, depthTest: false, linewidth: 2 }));
      la.renderOrder = 6;
      t.group.add(la);
    }
  }
  const r = CM.res;
  if (!r && su && su.stock_mesh && su.stock_mesh.triangles.length && !CM.hidden.stock && !CM.hidden.job)
    box.expandByObject(addMesh(su.stock_mesh, COLORS.stock, { transparent: true, opacity: 0.25, depthWrite: false }));
  if (r) {
    if ($("#cm-showstock").checked && !CM.hidden.stock && !CM.hidden.job && r.stock_mesh && r.stock_mesh.triangles.length) box.expandByObject(addMesh(r.stock_mesh, COLORS.stock, { transparent: true, opacity: 0.25, depthWrite: false }));
    if ($("#cm-showleft").checked && !CM.hidden.job && r.left_mesh && r.left_mesh.triangles.length) box.expandByObject(addMesh(r.left_mesh, COLORS.left));
    if ($("#cm-showhm").checked) for (const op of r.operations) {
      if (op.hm && op.hm.mesh && op.hm.mesh.triangles.length && !hiddenItem(op.id)) box.expandByObject(addMesh(op.hm.mesh, COLORS.hm, { transparent: true, opacity: 0.6 }));
    }
    // the part material cut (gouge): drawn over the part, with a point at each place
    const gp = [];
    for (const op of r.operations) {
      if (hiddenItem(op.finish_of || op.id) || !op.gouges || !op.gouges.length) continue;
      if (op.gouge_mesh && op.gouge_mesh.triangles.length) {
        const gm = addMesh(op.gouge_mesh, COLORS.gouge, { transparent: true, opacity: 0.85, depthTest: false });
        gm.renderOrder = 8;
      }
      for (const g of op.gouges) gp.push(...g.c);
    }
    if (gp.length) {
      const g = track(new THREE.BufferGeometry());
      g.setAttribute("position", new THREE.Float32BufferAttribute(gp, 3));
      const pm = new THREE.Points(g, new THREE.PointsMaterial({ color: COLORS.gouge, size: 9, sizeAttenuation: false, depthTest: false }));
      pm.renderOrder = 9;
      t.group.add(pm);
    }
    if ($("#cm-showpath").checked) {
      const cur = CM.cmd ? CM.cmd.id : null;
      const full = { rapid: [], plunge: [], feed: [], arc: [] }, dim = { rapid: [], plunge: [], feed: [], arc: [] };
      for (const op of r.operations) {
        if (hiddenItem(op.id)) continue;
        pathSegments(op.moves, cur && (op.finish_of || op.id) !== cur ? dim : full);
      }
      for (const [segs, dimmed] of [[dim, true], [full, false]]) for (const k of Object.keys(segs)) {
        if (!segs[k].length || (k === "rapid" && !$("#cm-showrapid").checked)) continue;
        const g = track(new THREE.BufferGeometry());
        g.setAttribute("position", new THREE.Float32BufferAttribute(segs[k], 3));
        const l = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: dimmed ? COLORS.dim : COLORS[k], depthTest: k === "rapid" || k === "plunge", transparent: dimmed, opacity: dimmed ? 0.5 : 1 }));
        l.renderOrder = 5;
        t.group.add(l);
        box.expandByObject(l);
      }
    }
  }
  if (CM.cmd && CM.cmd.place) drawDatums(box);
  CM.mach = null;
  if (CM.machine && CM.setup && !CM.hidden.job && ($("#cm-showmachine").checked || (CM.play && CM.play.frac > 0))) drawMachine();
  t.group.updateMatrixWorld(true);
  const bb = box.isEmpty() ? null : [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z];
  CM.bbox = bb;
  if (bb) CM.size = Math.max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], 1);
  updateAxes(t.scene, bb, $("#cm-axes").checked);
  drawSelection(false);
  if (!t.zoomed && bb) { view("iso"); t.zoomed = true; } else render3();
}
/** The faces, edges and points of the selected or edited operation, and the chip under the mouse, as an overlay. */
function drawSelection(doRender = true) {
  const t = CM.three;
  if (!t) return;
  t.overlay.clear();
  const id = CM.cmd ? CM.cmd.id : CM.sel;
  const op = id && opOf(id);
  const pcs = (CM.doc && CM.doc.placement && CM.doc.placement.constraints) || [];
  const pcSel = CM.cmd && CM.cmd.place ? pcs : CM.sel && CM.sel.startsWith("pc:") ? pcs.filter(c => "pc:" + c.id === CM.sel) : [];
  if (pcSel.length && CM.geo && t.faceMesh) {
    const hv = CM.chipHover && CM.chipHover.pc;
    const fs = new Set(pcSel.filter(c => !c.suppressed && c.id !== hv && c.face != null && c.edge == null && c.vertex == null).map(c => +c.face).filter(i => i >= 0 && i < CM.geo.face_keys.length));
    const plc = placementOf(), Rm = rotMatrix(plc.rot), placed = q => { const v = mv(Rm, q); return [v[0] + plc.pos[0], v[1] + plc.pos[1], v[2] + plc.pos[2]]; };
    const es = new Set(pcSel.filter(c => !c.suppressed && c.ec).map(c => edgeIndex({ mid: placed(c.ec) })).filter(i => i >= 0));
    if (es.size) { const l = new THREE.LineSegments(edgeGeo(es), new THREE.LineBasicMaterial({ color: COLORS.edgeSel, depthTest: false })); l.renderOrder = 9; t.overlay.add(l); }
    const vs = pcSel.filter(c => !c.suppressed && c.vc).map(c => placed(c.vc));
    if (vs.length) { const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(vs.flat(), 3)); const pm = new THREE.Points(g, new THREE.PointsMaterial({ color: COLORS.sel, size: 10, sizeAttenuation: false, depthTest: false })); pm.renderOrder = 11; t.overlay.add(pm); }
    if (fs.size) t.overlay.add(new THREE.Mesh(facesGeo(fs), new THREE.MeshBasicMaterial({ color: COLORS.sel, transparent: true, opacity: 0.45, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 })));
    const hc = hv && pcs.find(c => c.id === hv);
    if (hc && hc.face != null && hc.edge == null && hc.vertex == null) { const fm = new THREE.Mesh(faceGeo(+hc.face), new THREE.MeshBasicMaterial({ color: 0xffd43b, transparent: true, opacity: 0.7, side: THREE.DoubleSide, depthTest: false })); fm.renderOrder = 11; t.overlay.add(fm); }
  }
  if (op && CM.geo && t.faceMesh) {
    const fs = new Set((op.faces || []).map(faceIndex).filter(i => i >= 0));
    const es = new Set((op.edges || []).map(edgeIndex).filter(i => i >= 0));
    if (fs.size) {
      const fm = new THREE.Mesh(facesGeo(fs), new THREE.MeshBasicMaterial({ color: COLORS.sel, transparent: true, opacity: 0.55, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 }));
      t.overlay.add(fm);
    }
    if (es.size) {
      const l = new THREE.LineSegments(edgeGeo(es), new THREE.LineBasicMaterial({ color: COLORS.edgeSel, depthTest: false, linewidth: 3 }));
      l.renderOrder = 9;
      t.overlay.add(l);
    }
    const hv = CM.chipHover;
    if (hv) {
      const fi = faceIndex(hv), ei = edgeIndex(hv);
      if (fi >= 0) { const fm = new THREE.Mesh(faceGeo(fi), new THREE.MeshBasicMaterial({ color: 0xffd43b, transparent: true, opacity: 0.6, side: THREE.DoubleSide, depthTest: false })); fm.renderOrder = 11; t.overlay.add(fm); }
      if (ei >= 0) { const l = new THREE.LineSegments(edgeGeo(new Set([ei])), new THREE.LineBasicMaterial({ color: 0xffd43b, depthTest: false })); l.renderOrder = 11; t.overlay.add(l); }
    }
    if (op.points && op.points.length) {
      const z = CM.geo.bbox ? CM.geo.bbox[5] : 0;
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(op.points.flatMap(p => [p[0], p[1], p.length >= 3 ? p[2] : z]), 3));
      const pm = new THREE.Points(g, new THREE.PointsMaterial({ color: COLORS.sel, size: 8, sizeAttenuation: false, depthTest: false }));
      pm.renderOrder = 11;
      t.overlay.add(pm);
    }
  }
  drawMeasure();
  if (doRender) render3();
}

// ------------------------------------------------------------------ measure

const MEAS_COL = 0x0ca678;
/** Measure mode on / off (Measure button, Esc): a click on a vertex (within 12 px), an edge or a face of the part. */
function setMeasure(on) {
  if (on && CM.zeroPick) endZeroPick();
  CM.measure = on ? { items: [], res: null } : null;
  $("#cm-measure-btn").classList.toggle("active", !!on);
  $("#cm-measure").hidden = !on;
  clearHover();
  renderMeasure();
  drawSelection();
  status(on ? "Measure: click a face, an edge or a vertex of the part, then a second one (Esc ends)" : "Measuring ended");
}
function renderMeasure() {
  const m = CM.measure;
  if (!m) return;
  $("#cm-measure-body").innerHTML = measureHtml(m.res, m.res ? (m.items.length < 2 ? "Click a second item to measure between them." : "A click starts a new measurement.") : "Click a face, an edge or a vertex of the part. Coordinates in mm, job coordinates unless marked machine coordinates.");
}
/** The measure item under the cursor: {vertex: point} | {edge: index} | {face: index} | null. */
function measureAt(e) {
  if (!CM.geo || !CM.three || !CM.three.faceMesh) return null;
  const v = vertexAt(e);
  if (v) return { vertex: v };
  const h = pickAt(e, ["edge", "face"]);
  if (!h) return null;
  return h.kind === "edge" ? { edge: h.index } : { face: h.index };
}
function hoverMeasure(e) {
  const t = CM.three;
  if (!t) return;
  clearHover();
  const it = measureAt(e);
  if (it && it.vertex) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(it.vertex, 3));
    t.hover = new THREE.Points(g, new THREE.PointsMaterial({ color: MEAS_COL, size: 11, sizeAttenuation: false, depthTest: false }));
  } else if (it && it.edge !== undefined) {
    t.hover = new THREE.LineSegments(edgeGeo(new Set([it.edge])), new THREE.LineBasicMaterial({ color: MEAS_COL, depthTest: false }));
  } else if (it) {
    t.hover = new THREE.Mesh(faceGeo(it.face), new THREE.MeshBasicMaterial({ color: MEAS_COL, transparent: true, opacity: 0.3, side: THREE.DoubleSide, depthTest: false }));
  }
  if (t.hover) { t.hover.renderOrder = 12; t.scene.add(t.hover); }
  t.renderer.domElement.style.cursor = it ? "crosshair" : "";
  render3();
}
function clickMeasure(e) {
  const it = measureAt(e);
  if (it) addMeasureItem(it);
}
async function addMeasureItem(it) {
  const m = CM.measure;
  if (!m || !hasSource()) return;
  if (m.items.length >= 2) m.items = [];
  m.items.push(it);
  m.res = null;
  drawSelection();
  try {
    const r = await postJSON("/api/cam/measure", { cam: CM.doc, items: m.items });
    const j = await r.json();
    if (CM.measure !== m) return;
    m.res = j;
    renderMeasure();
    drawSelection();
    const md = (j.rows.find(x => x[0] === "Minimum distance") || [])[1];
    status(md ? "Minimum distance " + md : j.rows.length ? j.rows[0][0] + ": " + j.rows[0][1] : "");
  } catch (err) { showErr(err); }
}
/** Measured items (green) and the minimum distance line, in the selection overlay. */
function drawMeasure() {
  const m = CM.measure, t = CM.three;
  if (!m || !t || !CM.geo) return;
  const fs = new Set(m.items.filter(x => x.face !== undefined).map(x => x.face));
  const es = new Set(m.items.filter(x => x.edge !== undefined).map(x => x.edge));
  if (fs.size) t.overlay.add(new THREE.Mesh(facesGeo(fs), new THREE.MeshBasicMaterial({ color: MEAS_COL, transparent: true, opacity: 0.5, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 })));
  if (es.size) { const l = new THREE.LineSegments(edgeGeo(es), new THREE.LineBasicMaterial({ color: MEAS_COL, depthTest: false })); l.renderOrder = 12; t.overlay.add(l); }
  const pts = m.items.filter(x => x.vertex).map(x => x.vertex);
  if (m.items.some(x => x.ref === "zero") && CM.setup && CM.setup.origin) pts.push(CM.setup.origin);
  if (m.res && m.res.points && m.items.length === 2) {
    const [a, b] = m.res.points;
    const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...a), new THREE.Vector3(...b)]);
    const ln = new THREE.Line(g, new THREE.LineBasicMaterial({ color: MEAS_COL, depthTest: false }));
    ln.renderOrder = 12;
    t.overlay.add(ln);
    pts.push(a, b);
  }
  if (pts.length) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pts.flat(), 3));
    const pm = new THREE.Points(g, new THREE.PointsMaterial({ color: MEAS_COL, size: 9, sizeAttenuation: false, depthTest: false }));
    pm.renderOrder = 12;
    t.overlay.add(pm);
  }
}

// ------------------------------------------------------------------ side panel: job tree

function bindPanelSplit() {
  const bar = $("#cm-split"), panel = $("#cm-panel");
  if (!bar || bar.dataset.bound) return;
  bar.dataset.bound = "1";
  try { const w = +localStorage.getItem("cm_panel_w"); if (w >= 300) panel.style.width = w + "px"; } catch (e) { /* no storage */ }
  bar.onmousedown = e => {
    e.preventDefault();
    const w0 = panel.getBoundingClientRect().width, x0 = e.clientX;
    bar.classList.add("drag");
    const move = ev => { panel.style.width = Math.max(300, Math.min(window.innerWidth * 0.75, w0 + x0 - ev.clientX)) + "px"; };
    const up = () => {
      bar.classList.remove("drag");
      window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up);
      try { localStorage.setItem("cm_panel_w", parseInt(panel.style.width)); } catch (err) { /* no storage */ }
    };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  };
}
function renderAll() {
  if (!CM.doc) return;
  bindPanelSplit();
  renderTree(); renderProps(); renderBits(); renderPost();
}
const EYE = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>`;
const ico = (key, alt) => (window.treeIcon && window.treeIcon(key)) || `<span class="ico">${alt || "•"}</span>`;
const OP_ICON = t => ({ copy: "copy", array: "pattern" })[t] || "cam_" + t;
const PC_ICON = { coincident: "mate_coincident", distance: "mate_distance", parallel: "mate_parallel", angle: "mate_angle", concentric: "mate_concentric" };
function recOf(id) { return CM.res && CM.res.operations.find(x => x.id === id); }
/** Hidden in the view: the item or the Job. */
function hiddenItem(id) {
  id = String(id || "").replace(/:finish$/, "");
  return !!(CM.hidden.job || CM.hidden[id] || (id !== "model" && id !== "stock" && id !== "job" && CM.hidden.ops && opOf(id)));
}
/** The job tree in the manner of the FreeCAD CAM workbench: Job with Operations, Model (the part and its placement
 *  constraints), Stock, SetupSheet and Tools (tool controllers); folders fold, eyes hide geometry. */
function renderTree() {
  const d = CM.doc, box = $("#cm-tree");
  const fold = CM.fold;
  const row = (id, level, icon, name, o) => {
    o = o || {};
    const tw = o.kids === undefined ? `<span class="cm-tw"></span>` : `<span class="cm-tw${o.kids ? "" : " none"}" data-k="fold">${o.kids ? (fold[id] ? "▸" : "▾") : ""}</span>`;
    const eye = o.eye ? `<button type="button" data-k="eye" class="cm-eye${CM.hidden[id] ? " off" : ""}" title="Show / hide">${EYE}</button>` : `<span class="cm-eye"></span>`;
    return `<div class="pt-feat cm-tr${id === CM.sel ? " sel" : ""}${o.supp ? " supp" : ""}${o.cmd ? " editing" : ""}${level >= 2 ? " cm-child" : ""}${o.dim ? " hid" : ""}" data-id="${esc(id)}" style="padding-left:${4 + level * 16}px">` +
      `<span class="cm-lead">${tw}${eye}${o.toggle ? `<input type="checkbox" data-k="on" title="Active"${o.supp ? "" : " checked"}>` : ""}${icon}</span>` +
      `<span class="nm">${esc(name)}${o.sub ? ` <span class="hint">${esc(o.sub)}</span>` : ""}${o.state || ""}</span>` +
      `<span class="ops">` + (o.ops ? `<button type="button" data-k="up" title="Move up">&#9650;</button><button type="button" data-k="down" title="Move down">&#9660;</button>` : "") +
      (o.del ? `<button type="button" data-k="del" title="Delete">&#10005;</button>` : "") + `</span>` +
      (o.err ? `<span class="err">${esc(o.err)}</span>` : "") + "</div>";
  };
  const ops = d.operations || [], tcs = d.tools || [], pl = d.placement || {}, pcs = pl.constraints || [];
  const hj = !!CM.hidden.job;
  let h = row("job", 0, ico("cam_job"), d.name || "Job", { kids: true, eye: true, dim: hj, sub: `${(CM.posts.find(p => p.id === d.post) || {}).name || d.post || ""}` });
  if (!fold.job) {
    h += row("ops", 1, ico("cam_folder"), "Operations", { kids: ops.length > 0, eye: true, dim: hj || CM.hidden.ops, sub: ops.length ? `${ops.length}` : "" });
    if (!fold.ops) ops.forEach(o => {
      const r0 = recOf(o.id), rf = recOf(o.id + ":finish"), ot = OPS[o.type] || {};
      const r = r0 && rf && r0.ok && !rf.ok ? rf : r0;
      const gz = (r0 ? r0.gouge_mm3 : 0) + (rf ? rf.gouge_mm3 : 0);
      const state = !r ? "" : r.ok ? (gz > 0.05 ? ` <span class="cm-warn" title="gouge">⚠</span>` : ` <span class="cm-ok">✓</span>`) : ` <span class="cm-err">✗</span>`;
      const fin = ot.finish && o.finish_mode === "separate" ? `, finish ${o.finish_tc || o.tc}` : "";
      const sub = ot.supplemental ? "" : ot.derived ? `of ${(opOf(o.of) || {}).name || "?"}` : (o.tc || "no tool") + fin + ((ot.base && (o.faces || []).length) ? `, ${o.faces.length} face(s)` : "") + ((o.edges || []).length ? `, ${o.edges.length} edge(s)` : "");
      const drs = o.dressups || [];
      h += row(o.id, 2, ico(OP_ICON(o.type), "⟲"), o.name, { kids: drs.length > 0, toggle: true, ops: true, del: true, supp: o.active === false, eye: !ot.supplemental, dim: hiddenItem(o.id),
                                                             sub: `${opLabel(o)}${sub ? ", " + sub : ""}`, state, cmd: CM.cmd && CM.cmd.id === o.id && CM.cmd.dr === undefined, err: r && !r.ok && r.errors && r.errors[0] });
      if (!fold[o.id]) drs.forEach((dr, k) => {
        const id = `dr:${o.id}:${k}`;
        h += row(id, 3, ico("cam_dr_" + dr.type, "✧"), (DRESSUPS[dr.type] || {}).label || dr.type, { del: true, cmd: CM.cmd && CM.cmd.id === o.id && CM.cmd.dr === k });
      });
    });
    const src = d.source && d.source.name;
    h += row("model", 1, ico("cam_folder"), "Model", { kids: !!src, eye: true, dim: hj || CM.hidden.model, cmd: CM.cmd && CM.cmd.place });
    if (!fold.model && src) {
      h += row("part", 2, ico("cam_model"), src, { kids: pcs.length > 0, dim: hj || CM.hidden.model, sub: placementText(pl) });
      if (!fold.part) pcs.forEach(c => {
        const bad = CM.placeRes && (CM.placeRes.unsatisfied || {})[c.id];
        h += row("pc:" + c.id, 3, ico(PC_ICON[c.type], "⊥"), pcLabel(c), { del: true, supp: !!c.suppressed, err: bad || "" });
      });
    }
    h += row("stock", 1, ico("cam_stock"), "Stock", { eye: true, dim: hj || CM.hidden.stock, sub: stockText() });
    h += row("setup", 1, ico("cam_sheet"), "SetupSheet");
    const tcm = travelCheck();
    h += row("machine", 1, ico("cam_machine"), "Machine", { eye: true, dim: hj || CM.hidden.machine, sub: CM.machine ? `${fmt(CM.machine.travel_x)} x ${fmt(CM.machine.travel_y)} x ${fmt(CM.machine.travel_z)} mm` : "",
                                                             state: tcm && tcm.count ? ` <span class="cm-err" title="moves outside the travel">✗</span>` : "" });
    h += row("tools", 1, ico("cam_folder"), "Tools", { kids: tcs.length > 0, sub: `${tcs.length}` });
    if (!fold.tools) for (const tc of tcs) {
      const b = bitOf(tc.bit);
      h += row("tc:" + tc.id, 2, ico("cam_tool", "⚙"), `${tc.id} ${tc.name || ""}`, { sub: `T${tc.number} ${b ? fmt(b.d) + " mm" : "(no bit: " + tc.bit + ")"}`, del: true });
    }
  }
  box.innerHTML = h;
  box.querySelectorAll(".pt-feat").forEach(el => {
    const id = el.dataset.id;
    el.onclick = e => {
      const kEl = e.target.closest("[data-k]"), k = kEl && kEl.dataset.k;
      if (k === "fold") { fold[id] = !fold[id]; saveFold(); renderTree(); return; }
      if (k === "eye") { CM.hidden[id] = !CM.hidden[id]; renderTree(); draw(); return; }
      if (id.startsWith("tc:")) {
        if (k === "del") { deleteTc(id.slice(3)); return; }
        select(id); return;
      }
      if (id.startsWith("pc:")) {
        if (k === "del") { deleteConstraint(id.slice(3)); return; }
        select(id); return;
      }
      if (id.startsWith("dr:")) {
        const [, oid, k2] = id.split(":");
        if (k === "del") { const o = opOf(oid); o.dressups.splice(+k2, 1); if (CM.cmd && CM.cmd.id === oid) closeCommand(false); changed(); renderAll(); return; }
        select(id); return;
      }
      const o = opOf(id);
      if (!o) { select(id); return; }
      const i = opIndex(id);
      if (k === "on") { o.active = e.target.checked; changed(); renderTree(); return; }
      if (k === "up" && i > 0) { [ops[i - 1], ops[i]] = [ops[i], ops[i - 1]]; changed(); renderTree(); return; }
      if (k === "down" && i < ops.length - 1) { [ops[i + 1], ops[i]] = [ops[i], ops[i + 1]]; changed(); renderTree(); return; }
      if (k === "del") { deleteOp(id); return; }
      select(id);
    };
    el.ondblclick = e => {
      if (e.target.closest("[data-k]")) return;
      if (id.startsWith("dr:")) { const [, oid, k2] = id.split(":"); openCommand(oid, +k2); return; }
      if (id === "model" || id === "part" || id.startsWith("pc:")) { openPlacement(); return; }
      if (["job", "ops", "tools"].includes(id)) { fold[id] = !fold[id]; saveFold(); renderTree(); return; }
      if (opOf(id)) openCommand(id);
    };
  });
}
function saveFold() { try { localStorage.setItem("cm-fold", JSON.stringify(CM.fold)); } catch (e) { /* this session */ } }
function placementText(pl) {
  const p = (pl && pl.pos) || [0, 0, 0], r = (pl && pl.rot) || [0, 0, 0];
  if (![...p, ...r].some(v => Math.abs(v) > 1e-9)) return "not moved";
  return `at ${p.map(v => fmt(v, 5)).join(", ")} mm, turned ${r.map(v => fmt(v, 4)).join(", ")} deg`;
}
function pcWhat(c) { return c.edge != null ? `edge ${(+c.edge) + 1}` : c.vertex != null ? `vertex ${(+c.vertex) + 1}` : `face ${(+c.face) + 1}`; }
function pcLabel(c) {
  const t = (PC_TYPES.find(x => x[0] === c.type) || [0, c.type])[1];
  return `${t} ${pcWhat(c)} / ${c.datum || "?"}${c.type === "distance" ? ` ${fmt(c.value)} mm` : c.type === "angle" ? ` ${fmt(c.value)} deg` : ""}${c.flip ? ", flipped" : ""}`;
}
function stockText() {
  const st = CM.doc.stock || {}, m = st.material ? materialName(st.material) : "";
  return stockShape(st) + (m ? ", " + m : "");
}
function stockShape(st) {
  if (st.kind === "part_filled") return "part with the undercuts filled";
  if (st.kind === "box") return "box";
  if (st.kind === "step") return "STEP " + String(st.path || "(no file)").split(/[\\/]/).pop();
  return `offsets ${fmt(st.xneg)}/${fmt(st.xpos)} ${fmt(st.yneg)}/${fmt(st.ypos)} ${fmt(st.zneg)}/${fmt(st.zpos)} mm`;
}
function select(id) {
  CM.sel = id;
  renderTree(); renderProps(); drawSelection();
}
function deleteOp(id) {
  const o = opOf(id);
  if (!o || !confirm(`Delete ${o.name}?`)) return;
  if (CM.cmd && CM.cmd.id === id) closeCommand(false);
  CM.doc.operations = CM.doc.operations.filter(x => x.id !== id);
  // copies and arrays of the operation lose their source
  for (const x of CM.doc.operations) if (x.of === id) x.of = "";
  if (CM.sel === id) CM.sel = null;
  changed(); renderAll(); draw();
}
function deleteTc(id) {
  const used = (CM.doc.operations || []).filter(o => o.tc === id);
  if (!confirm(`Delete tool controller ${id}?${used.length ? ` ${used.length} operation(s) use it.` : ""}`)) return;
  CM.doc.tools = CM.doc.tools.filter(t => t.id !== id);
  if (CM.sel === "tc:" + id) CM.sel = "tools";
  changed(); renderAll();
}

// ------------------------------------------------------------------ side panel: properties

const numField = (label, k, v, title, cls = "numf") => `<label class="cm-f"${title ? ` title="${esc(title)}"` : ""}>${esc(label)}<input type="text" class="${cls}" data-k="${k}" value="${v === null || v === undefined ? "" : esc(typeof v === "number" ? fmt(v, 6) : v)}"></label>`;
const selField = (label, k, cur, list, title) => `<label class="cm-f"${title ? ` title="${esc(title)}"` : ""}>${esc(label)}<select data-k="${k}">${list.map(([v, l]) => `<option value="${esc(v)}"${String(v) === String(cur) ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`;
const chkField = (label, k, cur, title) => `<label class="check inline"${title ? ` title="${esc(title)}"` : ""}><input type="checkbox" data-k="${k}"${cur ? " checked" : ""}> ${esc(label)}</label>`;
/** Binds the fields of a form (data-k) to an object: numbers (empty: null when allowNull), selects, checkboxes, text. */
function bindFields(box, obj, onChange, allowNull = true) {
  for (const inp of box.querySelectorAll("[data-k]")) inp.onchange = () => {
    const k = inp.dataset.k;
    if (inp.tagName === "SELECT") obj[k] = inp.value;
    else if (inp.type === "checkbox") obj[k] = inp.checked;
    else if (inp.classList.contains("numf")) {
      if (inp.value.trim() === "") { if (allowNull) obj[k] = null; else { inp.value = fmt(obj[k], 6); return; } }
      else { const v = num(inp.value); if (!isFinite(v)) { inp.value = obj[k] === null || obj[k] === undefined ? "" : fmt(obj[k], 6); return; } obj[k] = v; }
    } else obj[k] = inp.value;
    onChange(k);
  };
}

function renderProps() {
  const box = $("#cm-props"), d = CM.doc, id = CM.sel;
  if (!d) return;
  if (!id) { box.innerHTML = `<p class="hint">Select an item of the job tree. Double-click an operation to edit it in the command window.</p>`; return; }
  if (id === "model" || id === "part") return renderModelProps(box);
  if (id === "job" || id === "output") return renderJobProps(box);
  if (id === "ops") return renderOpsProps(box);
  if (id === "machine") return renderMachineProps(box);
  if (id.startsWith("pc:")) return renderPcProps(box, id.slice(3));
  if (id === "stock") return renderStockProps(box);
  if (id === "setup") return renderSetupProps(box);
  if (id === "tools") return renderToolsProps(box);
  if (id.startsWith("tc:")) return renderTcProps(box, id.slice(3));
  if (id.startsWith("dr:")) { const [, oid, k] = id.split(":"); const o = opOf(oid); const dr = o && (o.dressups || [])[+k]; if (!dr) { CM.sel = null; return renderProps(); } box.innerHTML = `<div class="row"><strong>${esc((DRESSUPS[dr.type] || {}).label || dr.type)}</strong> of ${esc(o.name)}</div><div class="row"><button type="button" id="cm-edit">Edit</button></div>`; $("#cm-edit").onclick = () => openCommand(oid, +k); return; }
  const o = opOf(id);
  if (!o) { CM.sel = null; return renderProps(); }
  renderOpProps(box, o);
}
function renderModelProps(box) {
  const g = CM.geo, d = CM.doc, pl = d.placement || {};
  box.innerHTML = `<div class="row"><label class="cm-f">Part<select data-k="name">${$("#cm-source").innerHTML}</select></label></div>` +
    (g ? `<div class="hint">${g.face_keys.length} faces, ${fmt(g.volume_mm3 / 1000, 4)} cm^3, ${g.bbox.slice(3).map((v, i) => fmt(v - g.bbox[i], 5)).join(" x ")} mm (X ${fmt(g.bbox[0])}..${fmt(g.bbox[3])}, Y ${fmt(g.bbox[1])}..${fmt(g.bbox[4])}, Z ${fmt(g.bbox[2])}..${fmt(g.bbox[5])}, job coordinates)</div>` : "") +
    ((CM.lostPicks || []).length ? `<div class="cm-warn">Picks not found after the last refresh: ${esc(CM.lostPicks.join(", "))}</div>` : "") +
    `<div class="row"><strong>Placement</strong> <span class="hint">${esc(placementText(pl))}; ${(pl.constraints || []).length} constraint(s)</span><button type="button" id="cm-place-edit" class="small">Edit</button></div>`;
  box.querySelector("select").value = (d.source || {}).name || "";
  box.querySelector("select").onchange = e => { d.source = { type: "part", name: e.target.value }; $("#cm-source").value = e.target.value; changed(false); loadGeometry(); };
  $("#cm-place-edit").onclick = openPlacement;
}
function renderOpsProps(box) {
  const ops = CM.doc.operations || [];
  const t = CM.res ? CM.res.operations.reduce((s, o) => s + (o.time_s || 0), 0) : null;
  box.innerHTML = `<div class="hint">${ops.length} operation(s), run in the order of the list${t !== null ? `; ${fmt(t / 60, 3)} min after the last run` : ""}. The toolbar adds an operation at the end of the list; double-click an operation to edit it.</div>`;
}
function renderPcProps(box, id) {
  const c = ((CM.doc.placement || {}).constraints || []).find(x => x.id === id);
  if (!c) { CM.sel = "part"; return renderProps(); }
  const bad = CM.placeRes && (CM.placeRes.unsatisfied || {})[id];
  box.innerHTML = `<div class="row"><strong>${esc(pcLabel(c))}</strong><button type="button" id="cm-place-edit" class="small">Edit</button></div>` + (bad ? `<div class="cm-err">${esc(bad)}</div>` : "");
  $("#cm-place-edit").onclick = openPlacement;
}
function renderStockProps(box) {
  const d = CM.doc, st = d.stock || (d.stock = { kind: "offsets" }), og = d.origin || (d.origin = { xy: "stock_min", z: "stock_top" });
  let h = `<div class="row">${selField("Stock", "kind", st.kind || "offsets", [["offsets", "Part bounding box with offsets"], ["box", "Box (coordinates)"], ["part_filled", "Part with the undercuts filled"], ["step", "STEP file"]], "Part with the undercuts filled: the stock an earlier program with an end mill leaves. STEP file: a solid in the coordinates of the part, moved with the model placement")}${materialField(st.material)}</div>`;
  if (st.kind === "step") h += `<div class="row"><label class="cm-f">STEP file<input type="text" class="cm-path" data-k="path" value="${esc(st.path || "")}" placeholder="file path, or a name in the STEP folder of the project"></label><button type="button" class="small" id="cm-stock-browse" title="Choose the STEP file of the stock">…</button></div><div class="row">${numField("X offset", "dx", st.dx, "mm, part coordinates")}${numField("Y offset", "dy", st.dy, "mm, part coordinates")}${numField("Z offset", "dz", st.dz, "mm, part coordinates")}</div>` +
    `<div class="row">${numField("Rot X", "rx", st.rx, "deg about the X axis of the part")}${numField("Rot Y", "ry", st.ry, "deg about the Y axis of the part")}${numField("Rot Z", "rz", st.rz, "deg about the Z axis of the part")}</div>` +
    `<div class="hint">The solid is in the coordinates of the part: turned about the part origin (X, then Y, then Z), moved by the offset (mm, deg), then moved with the model placement.</div>`;
  else if (st.kind === "box") h += `<div class="row">${numField("X min", "xmin", st.xmin)}${numField("X max", "xmax", st.xmax)}${numField("Y min", "ymin", st.ymin)}${numField("Y max", "ymax", st.ymax)}${numField("Z min", "zmin", st.zmin)}${numField("Z max", "zmax", st.zmax)}</div><div class="hint">mm, part coordinates; empty: the part bounding box</div>`;
  else if (st.kind !== "part_filled") h += `<div class="row">${numField("X neg", "xneg", st.xneg)}${numField("X pos", "xpos", st.xpos)}${numField("Y neg", "yneg", st.yneg)}${numField("Y pos", "ypos", st.ypos)}${numField("Z neg", "zneg", st.zneg)}${numField("Z pos", "zpos", st.zpos)}</div><div class="hint">mm beyond the part bounding box</div>`;
  h += `<div class="row">${selField("Machine zero X Y", "oxy", og.xy, ORIGIN_XY, "Work offset in X and Y")}${selField("Machine zero Z", "oz", og.z, ORIGIN_Z)}` +
    `<button type="button" id="cm-zero-pick" class="small${CM.zeroPick ? " primary" : ""}" title="Click a vertex of the part in the view: the machine zero X, Y and Z at that vertex (Esc: cancel)">Pick vertex</button></div>` +
    (og.point ? `<div class="hint">Picked vertex X ${fmt(og.point[0])} Y ${fmt(og.point[1])} Z ${fmt(og.point[2])} mm (job coordinates)</div>` : "") + `<div class="hint" id="cm-setup-hint"></div>`;
  box.innerHTML = h;
  setupHint();
  const again = () => { changed(); loadSetup().then(() => { setupHint(); draw(); renderTree(); }); };
  bindFields(box, st, k => {
    if (k === "kind") renderStockProps(box);
    if (k === "material") { changed(false); renderTree(); return; }
    if (st.kind === "step" && !st.path) { changed(false); status("Choose the STEP file of the stock"); return; }   // nothing to load yet
    again();
  }, true);
  box.querySelectorAll("select[data-k=oxy], select[data-k=oz]").forEach(sel => sel.onchange = () => {
    og[sel.dataset.k === "oxy" ? "xy" : "z"] = sel.value;
    if (sel.value === "point" && !og.point) { startZeroPick(); return; }
    again();
  });
  $("#cm-zero-pick").onclick = startZeroPick;
  const sb = $("#cm-stock-browse");
  if (sb) sb.onclick = async () => { const p = await window.browse("open", "step", st.path || "", "STEP file of the stock"); if (p) { st.path = p; renderStockProps(box); again(); } };
}
function setupHint() {
  const su = CM.setup, el = $("#cm-setup-hint");
  if (!el) return;
  el.textContent = su && su.stock_bbox ? `Stock ${fmt(su.stock_bbox[3] - su.stock_bbox[0], 5)} x ${fmt(su.stock_bbox[4] - su.stock_bbox[1], 5)} x ${fmt(su.stock_bbox[5] - su.stock_bbox[2], 5)} mm; machine zero at part X ${fmt(su.origin[0])} Y ${fmt(su.origin[1])} Z ${fmt(su.origin[2])}; clearance Z ${fmt(su.clearance_z - su.origin[2])} mm (machine)` : "";
}
function renderSetupProps(box) {
  const su = CM.doc.setup || (CM.doc.setup = Object.assign({}, (CM.meta && CM.meta.setup) || {}));
  box.innerHTML = `<div class="hint">Defaults of the operations (an operation's own value, when set, is used instead).</div>
    <div class="row">${numField("Clearance height offset (mm)", "clearance_offset", su.clearance_offset, "Above the start depth: rapid moves between operations")}${numField("Safe height offset (mm)", "safe_offset", su.safe_offset, "Above the start depth: rapid moves inside an operation")}</div>
    <div class="row">${numField("Step down (mm)", "step_down", su.step_down)}${numField("Finish depth (mm)", "finish_depth", su.finish_depth, "Height of the last level; 0: none")}</div>
    <div class="row">${numField("Horizontal rapid (mm/min)", "hrapid", su.hrapid, "For the cycle time")}${numField("Vertical rapid (mm/min)", "vrapid", su.vrapid)}${selField("Coolant", "coolant", su.coolant || "none", [["none", "None"], ["flood", "Flood (M08)"], ["mist", "Mist (M07)"]])}</div>
    <div class="pt-sec">Machine</div><div class="hint">Spindle limits for the feeds and speeds calculator and the sanity check.</div>
    <div class="row">${numField("Spindle min (rpm)", "rpm_min", su.rpm_min)}${numField("Spindle max (rpm)", "rpm_max", su.rpm_max)}${numField("Rated speed (rpm)", "rpm_rated", su.rpm_rated, "The spindle gives its rated power from this speed up; below it the torque is constant (power proportional to the speed)")}${numField("Spindle power (kW)", "power_kw", su.power_kw)}${numField("Max feed (mm/min)", "feed_max", su.feed_max)}${numField("Rigidity (%)", "rigidity", su.rigidity, "The chip load is scaled by this: 100 for a rigid machine; lower for a light router frame or a long tool stick-out")}${numField("Ramp angle (deg)", "ramp_angle", su.ramp_angle, "Angle of the ramp and helix entries the calculator gives the ramp feed for")}</div>`;
  bindFields(box, su, () => changed(), false);
}
function renderToolsProps(box) {
  const d = CM.doc;
  box.innerHTML = `<div class="hint">A tool controller: a tool bit of the library with its feeds, spindle speed and tool number. Operations refer to a controller.</div>
    <div class="row"><label class="cm-f">Add from bit<select id="cm-tc-bit">${CM.bits.map(b => `<option value="${esc(b.id)}">${esc(b.id)} ${esc(b.name || "")}</option>`).join("")}</select></label><button type="button" id="cm-tc-add" class="small">Add controller</button>
    <button type="button" id="cm-fs-all" class="small" title="Feed, plunge feed and spindle speed of every controller from the feeds and speeds calculator (the material of the stock, the ae and ap of each controller)">Feeds and speeds for all</button></div>
    ${(d.tools || []).length ? `<table class="fa-tbl"><tr><th>Id</th><th>Name</th><th>Bit</th><th>T</th><th>Feed</th><th>Plunge</th><th>rpm</th></tr>${d.tools.map(t => `<tr><td>${esc(t.id)}</td><td>${esc(t.name || "")}</td><td>${esc(t.bit)}</td><td>${esc(t.number)}</td><td>${fmt(t.hfeed)}</td><td>${fmt(t.vfeed)}</td><td>${fmt(t.rpm)}</td></tr>`).join("")}</table>` : ""}`;
  $("#cm-tc-add").onclick = () => { addTc($("#cm-tc-bit").value); };
  $("#cm-fs-all").onclick = applyFeedsAll;
}
/** A new tool controller for a bit (the defaults of the bit) in the job; returns it. */
function makeTc(bitId) {
  const b = bitOf(bitId);
  if (!b) return null;
  const tcs = CM.doc.tools || (CM.doc.tools = []);
  let n = tcs.length + 1;
  while (tcs.some(t => t.id === "TC" + n || t.number === n)) n++;
  const tc = { id: "TC" + n, name: b.name || b.id, bit: b.id, number: n, hfeed: b.feed || 500, vfeed: b.plunge || 150, rpm: b.rpm || 10000, dir: "CW" };
  tcs.push(tc);
  return tc;
}
/** A tool controller for a bit, selected in the tree; returns its id. */
function addTc(bitId) {
  const tc = makeTc(bitId);
  if (!tc) return null;
  changed(); CM.sel = "tc:" + tc.id; renderAll();
  return tc.id;
}
/** Options of a tool controller select: the controllers of the job, then every bit of the library as a new
 *  controller ("bit:<id>"). */
function tcChoices(first) {
  const shapeName = b => (CM.meta && CM.meta.shapes && CM.meta.shapes[b.shape]) || b.shape;
  const out = (first || []).concat((CM.doc.tools || []).map(t => { const b = bitOf(t.bit); return [t.id, `${t.id} ${t.name || ""}${b ? ` (${shapeName(b)} ${fmt(b.d)} mm)` : ""}`]; }));
  return out.concat(CM.bits.map(b => ["bit:" + b.id, `+ New controller: ${b.id} ${b.name || ""} (${shapeName(b)} ${fmt(b.d)} mm)`]));
}
function renderTcProps(box, id) {
  const tc = tcOf(id);
  if (!tc) { CM.sel = "tools"; return renderProps(); }
  const b = bitOf(tc.bit);
  box.innerHTML = `<div class="row">${numField("Id", "id", tc.id, "", "cm-name")}${numField("Name", "name", tc.name, "", "cm-name")}</div>
    <div class="row">${selField("Tool bit", "bit", tc.bit, CM.bits.map(x => [x.id, `${x.id} ${x.name || ""} (${fmt(x.d)} mm)`]))}${numField("Tool number", "number", tc.number, "T number of the G-code")}</div>
    <div class="row">${numField("Feed (mm/min)", "hfeed", tc.hfeed)}${numField("Plunge feed (mm/min)", "vfeed", tc.vfeed)}${numField("Ramp feed (mm/min)", "rfeed", tc.rfeed, "Ramp and helix entries; empty: the feed of the helix arcs, the plunge feed of a ramp")}${numField("Spindle (rpm)", "rpm", tc.rpm)}${selField("Direction", "dir", tc.dir || "CW", [["CW", "CW (M03)"], ["CCW", "CCW (M04)"]])}</div>
    ${b ? `<div class="hint">${esc((CM.meta && CM.meta.shapes && CM.meta.shapes[b.shape]) || b.shape)} D ${fmt(b.d)} mm${b.angle ? `, ${fmt(b.angle)} deg` : ""}, cutting height ${fmt(b.height)} mm, neck ${fmt(b.neck)} mm, shank ${fmt(b.shank)} mm, ${b.flutes || "-"} flutes, ${b.tool_material === "hss" ? "HSS" : "carbide"}</div>` : `<div class="cm-err">The bit ${esc(tc.bit)} is not in the library.</div>`}
    ${b ? feedsSection(tc, b) : ""}`;
  bindFields(box, tc, k => {
    if (k === "id") { const nn = String(tc.id || "").trim() || id; tc.id = nn; for (const o of CM.doc.operations || []) if (o.tc === id) o.tc = nn; CM.sel = "tc:" + nn; }
    if (k === "bit" && b && (tc.name === b.name || !tc.name)) { const nb = bitOf(tc.bit); if (nb) tc.name = nb.name || nb.id; }
    changed(); renderAll();
  }, false);
  if (b) bindFeedsSection(box, tc, b);
}

// ------------------------------------------------------------------ feeds and speeds

function materialName(id) { const m = ((CM.meta && CM.meta.materials) || []).find(x => x.id === id); return m ? m.name : ""; }
/** Workpiece material select (grouped) for the Stock properties. */
function materialField(cur) {
  const groups = {};
  for (const m of (CM.meta && CM.meta.materials) || []) (groups[m.group] = groups[m.group] || []).push(m);
  return `<label class="cm-f" title="Workpiece material for the feeds and speeds calculator">Material<select data-k="material"><option value="">(not set)</option>` +
    Object.keys(groups).map(g => `<optgroup label="${esc(g)}">${groups[g].map(m => `<option value="${esc(m.id)}"${m.id === cur ? " selected" : ""}>${esc(m.name)}</option>`).join("")}</optgroup>`).join("") + `</select></label>`;
}
/** Feeds and speeds of a tool controller's bit (server feeds.calc). */
async function calcFeeds(tcid, ae, ap) {
  const r = await postJSON("/api/cam/feeds", { cam: CM.doc, tc: tcid, ae, ap });
  return r.json();
}
function feedsResultHtml(r) {
  const lim = { rpm_max: "spindle max", feed_max: "max feed", power: "spindle power" };
  return `<table class="fa-tbl cm-fs"><tr><td>Spindle</td><td>${fmt(r.rpm, 5)} rpm</td><td>Cutting speed</td><td>${fmt(r.vc, 4)} m/min at D ${fmt(r.deff, 4)} mm</td></tr>
    <tr><td>Feed</td><td>${fmt(r.feed, 5)} mm/min</td><td>Plunge feed</td><td>${fmt(r.plunge, 5)} mm/min</td></tr>
    <tr><td>Ramp feed</td><td>${fmt(r.ramp, 5)} mm/min</td><td>at</td><td>${fmt(r.ramp_angle, 3)} deg; ${esc((COATINGS.find(c => c[0] === r.coating) || [0, r.coating])[1])}, rigidity ${fmt(r.rigidity, 3)} %</td></tr>
    <tr><td>Chip load</td><td>${fmt(r.fz_adj, 3)} mm/tooth</td><td>Table / thinning</td><td>${fmt(r.fz, 3)} mm/tooth × ${fmt(r.rctf, 3)}</td></tr>
    <tr><td>Chip thickness</td><td>${fmt(r.hm, 3)} mm</td><td>Removal rate</td><td>${fmt(r.mrr, 4)} cm^3/min</td></tr>
    <tr><td>Power</td><td>${fmt(r.power_kw, 3)} kW</td><td>Available</td><td>${fmt(r.power_avail_kw, 3)} kW, torque ${fmt(r.torque_nm, 3)} N·m</td></tr></table>` +
    (r.limited.length ? `<div class="hint">Limited by: ${r.limited.map(x => lim[x] || x).join(", ")}</div>` : "") +
    r.warnings.map(w => `<div class="cm-warn">${esc(w)}</div>`).join("");
}
function feedsSection(tc, b) {
  const fs = tc.fs || {}, su = CM.doc.setup || {}, mat = (CM.doc.stock || {}).material;
  return `<div class="pt-sec">Feeds and speeds</div>` +
    (mat ? `<div class="hint">Material ${esc(materialName(mat))} (Stock)</div>` : `<div class="cm-warn">No workpiece material: set Material in the Stock properties.</div>`) +
    `<div class="row"><label class="cm-f" title="Width of cut (radial engagement); empty: D (slot)">ae (mm)<input type="text" class="numf" data-fs="ae" value="${fs.ae == null ? "" : fmt(fs.ae, 6)}" placeholder="${fmt(b.d, 4)}"></label>` +
    `<label class="cm-f" title="Depth of cut (axial engagement); empty: the step down of the setup sheet${b.shape === "drill" ? "; not used for a drill" : ""}">ap (mm)<input type="text" class="numf" data-fs="ap" value="${fs.ap == null ? "" : fmt(fs.ap, 6)}" placeholder="${fmt(su.step_down, 4)}"></label>` +
    `<button type="button" class="small primary" id="cm-fs-apply" title="Feed, plunge feed and spindle speed of the controller from the calculation"${mat ? "" : " disabled"}>Apply</button></div><div id="cm-fs-res"></div>`;
}
function bindFeedsSection(box, tc, b) {
  const out = box.querySelector("#cm-fs-res");
  let last = null;
  const run = async () => {
    if (!(CM.doc.stock || {}).material) return;
    const fs = tc.fs || {};
    try {
      last = await calcFeeds(tc.id, fs.ae, fs.ap == null ? (CM.doc.setup || {}).step_down : fs.ap);
      if (last.error) throw new Error(last.error);
      out.innerHTML = feedsResultHtml(last);
    } catch (e) { last = null; out.innerHTML = `<div class="cm-err">${esc(e.message || e)}</div>`; }
  };
  box.querySelectorAll("[data-fs]").forEach(inp => inp.onchange = () => {
    const v = inp.value.trim() === "" ? null : num(inp.value);
    if (v !== null && !(v > 0)) { inp.value = ""; return; }
    tc.fs = Object.assign({}, tc.fs || {}, { [inp.dataset.fs]: v });
    changed(false); run();
  });
  box.querySelector("#cm-fs-apply").onclick = async () => {
    if (!last) await run();
    if (!last) return;
    tc.rpm = last.rpm; tc.hfeed = last.feed; tc.vfeed = last.plunge; tc.rfeed = last.ramp;
    changed(); renderAll();
    status(`${tc.id}: ${fmt(last.rpm, 5)} rpm, feed ${fmt(last.feed, 5)} mm/min, plunge ${fmt(last.plunge, 5)} mm/min`);
  };
  run();
}
/** All tool controllers from the calculator with their own ae and ap. */
async function applyFeedsAll() {
  if (!(CM.doc.stock || {}).material) { status("Set the material of the stock first", true); return; }
  const done = [];
  for (const tc of CM.doc.tools || []) {
    const fs = tc.fs || {};
    try {
      const r = await calcFeeds(tc.id, fs.ae, fs.ap == null ? (CM.doc.setup || {}).step_down : fs.ap);
      if (r.error) throw new Error(r.error);
      tc.rpm = r.rpm; tc.hfeed = r.feed; tc.vfeed = r.plunge; tc.rfeed = r.ramp;
      done.push(tc.id);
    } catch (e) { status(`${tc.id}: ${e.message || e}`, true); }
  }
  changed(); renderAll();
  if (done.length) status(`Feeds and speeds applied to ${done.join(", ")}`);
}
/** Width and depth of cut of an operation for the calculator: ae the step over (Adaptive, Face, 3D Surface,
 *  Waterline, 3D Pocket, Helix) or the step of the Undercut passes, else D (a pocket and a profile start with a full
 *  slot); ap the step down of the operation (resolved after a preview), the engraving depth, or the flank of a
 *  dovetail. */
function opEngagement(o, b) {
  const D = +b.d || 6, r = recOf(o.id), su = CM.doc.setup || {};
  let ae = D;
  if (["adaptive", "face", "surface", "waterline", "pocket3d", "helix"].includes(o.type) && o.stepover_pct > 0) ae = D * o.stepover_pct / 100;
  if (o.type === "undercut") ae = +o.stepover || 1;
  let ap = o.step_down != null ? o.step_down : r && r.heights && r.heights.step ? r.heights.step : su.step_down;
  if (o.type === "engrave") ap = o.depth || ap;
  if (o.type === "deburr") ap = (+o.width || 1) + (+o.extra_depth || 0);
  if (o.type === "undercut") ap = +b.height || ap;
  return { ae: Math.min(ae, D), ap };
}
async function applyFeedsOp(o) {
  const ot = OPS[o.type] || {}, tc = tcOf(o.tc), b = tc && bitOf(tc.bit);
  if (!b || ot.supplemental || ot.derived) { status("The operation has no tool controller", true); return; }
  if (!(CM.doc.stock || {}).material) { status("Set the material of the stock first", true); return; }
  const { ae, ap } = opEngagement(o, b);
  try {
    const r = await calcFeeds(tc.id, ae, ap);
    if (r.error) throw new Error(r.error);
    o.feed = r.feed; o.plunge = r.plunge; o.rpm = r.rpm; o.ramp_feed = r.ramp;
    CM.fsOp = { id: o.id, r };
    changed(); renderCommand(true); renderProps();
    status(`${o.name}: ae ${fmt(r.ae, 4)} mm, ap ${fmt(r.ap, 4)} mm: ${fmt(r.rpm, 5)} rpm, feed ${fmt(r.feed, 5)} mm/min, plunge ${fmt(r.plunge, 5)} mm/min`);
  } catch (e) { showErr(e); }
}
function renderJobProps(box) {
  const d = CM.doc, out = d.output || (d.output = { folder: "", name: "" });
  box.innerHTML = `<div class="row"><span class="hint">Job ${esc(d.name || "")} (File ▾ saves and renames it)</span></div>
    <div class="row">${selField("Post-processor", "post", d.post || "estlcam", CM.posts.map(p => [p.id, p.name]))}</div>
    <div class="row">${numField("File name", "name", out.name, "Empty: <job name>.nc", "cm-name")}</div>
    <div class="row">${numField("Folder", "folder", out.folder, "Empty: the cam folder of the project", "cm-path")}</div>
    <div class="row"><button type="button" id="cm-out-post" class="primary">Post process</button><button type="button" id="cm-out-dl">Download</button></div>`;
  bindFields(box, out, () => { changed(false); renderTree(); }, false);
  box.querySelector("select[data-k=post]").onchange = e => { d.post = e.target.value; changed(false); renderPost(); renderTree(); };
  $("#cm-out-post").onclick = () => writeGcode(false);
  $("#cm-out-dl").onclick = () => writeGcode(true);
}
/** Properties of an operation: its summary and the results of the last run. */
function renderOpProps(box, o) {
  const r = recOf(o.id), ot = OPS[o.type] || {};
  let h = `<div class="row"><strong>${esc(o.name)}</strong> <span class="hint">${esc(opLabel(o))}</span><button type="button" id="cm-edit" class="small">Edit</button></div>`;
  if (!ot.supplemental) {
    const tc = tcOf(o.tc), b = tc && bitOf(tc.bit);
    h += `<div class="hint">${tc ? `${esc(tc.id)} ${esc(tc.name || "")}${b ? `, D ${fmt(b.d)} mm` : ""}` : "no tool controller"}${(o.faces || []).length ? `; ${o.faces.length} face(s)` : ""}${(o.edges || []).length ? `; ${o.edges.length} edge(s)` : ""}${(o.dressups || []).length ? `; dressups: ${o.dressups.map(x => (DRESSUPS[x.type] || {}).label || x.type).join(", ")}` : ""}</div>`;
  }
  const rf = recOf(o.id + ":finish");
  for (const [r, title] of [[recOf(o.id), rf ? "Roughing" : ""], [rf, "Finish"]]) {
  if (title === "Finish" && !r) continue;
  if (title) h += `<div class="pt-sec">${title}${title === "Finish" && r.tool ? " (" + esc(r.tool) + ")" : ""}</div>`;
  if (r) {
    h += `<div class="fa-props">` + (r.ok ? `<span class="cm-ok">ok</span>` : `<span class="cm-err">error</span>`);
    for (const e of r.errors || []) h += `<div class="cm-err">${esc(e)}</div>`;
    for (const m of r.messages || []) h += `<div class="hint">${esc(m)}</div>`;
    if (r.heights) h += `<div class="hint">clearance Z ${fmt(r.heights.clearance)}, safe Z ${fmt(r.heights.safe)}, start Z ${fmt(r.heights.start)}, final Z ${fmt(r.heights.final)} mm (part), step ${fmt(r.heights.step)} mm</div>`;
    if (r.ok && r.moves && r.moves.length && r.time_s != null)
      h += `<div class="hint">removed ${fmt(r.removed_mm3, 5)} mm^3${r.remaining_mm3 > 0.001 ? `, ${fmt(r.remaining_mm3, 4)} mm^3 left` : ""}${r.gouge_mm3 > 0.05 ? `, <span class="cm-err">gouge ${fmt(r.gouge_mm3, 4)} mm^3</span>` : ""}; cut ${fmt(r.cut_mm, 5)} mm, rapid ${fmt(r.rapid_mm, 5)} mm, ${fmt(r.time_s / 60, 3)} min; feed ${fmt(r.feed)} mm/min, plunge ${fmt(r.plunge)} mm/min, ${fmt(r.rpm)} rpm; ${r.moves.length} moves</div>`;
    if ((r.gouges || []).length) {
      const og = (CM.setup && CM.setup.origin) || [0, 0, 0];
      h += `<div class="pt-sec cm-err">Gouges</div><div class="hint">The part material cut, pink in the view. Centre in job coordinates (machine coordinates below it); the first cutting move whose tool reaches the place, from and to. A click on a row centres the view on the place.</div>` +
        `<table class="fa-tbl cm-gouges"><tr><th>#</th><th>Volume (mm^3)</th><th>Centre X, Y, Z (mm)</th></tr>` +
        r.gouges.map((g, i) => `<tr data-gouge="${esc(r.id)}|${i}" title="Centre the view on this place"><td>${i + 1}</td><td>${fmt(g.volume, 4)}</td><td>${g.c.map(v => fmt(v, 5)).join(", ")}<br><span class="hint">${g.c.map((v, k) => fmt(v - og[k], 5)).join(", ")} (machine)</span></td></tr>` +
          `<tr data-gouge="${esc(r.id)}|${i}"><td></td><td colspan="2" class="hint">${g.move != null ? `Move ${g.move + 1}: ${g.from ? g.from.map(v => fmt(v, 5)).join(", ") + " to " : ""}${g.p.map(v => fmt(v, 5)).join(", ")}` : "No cutting move found"}</td></tr>`).join("") + `</table>`;
    }
    const lg = (r.levels || []).some(l => l.gouge_mm3);
    if ((r.levels || []).length) h += `<table class="fa-tbl"><tr><th>Level</th><th>Z (mm)</th><th>Length (mm)</th><th>Removed (mm^3)</th>${lg ? "<th>Gouge (mm^3)</th>" : ""}</tr>` + r.levels.map((l, i) => `<tr><td>${i + 1}</td><td>${fmt(l.z)}</td><td>${fmt(l.length_mm, 5)}</td><td>${fmt(l.removed_mm3, 5)}</td>${lg ? `<td${l.gouge_mm3 ? ' class="cm-err"' : ""}>${l.gouge_mm3 ? fmt(l.gouge_mm3, 4) : ""}</td>` : ""}</tr>`).join("") + `</table>`;
    h += `</div>`;
  } else h += `<div class="hint">Not computed yet.</div>`;
  }
  box.innerHTML = h;
  $("#cm-edit").onclick = () => openCommand(o.id);
  box.querySelectorAll("[data-gouge]").forEach(tr => tr.onclick = () => {
    const [rid, i] = tr.dataset.gouge.split("|"), rec = recOf(rid), g = rec && rec.gouges[+i];
    if (g) focusPoint(g.c);
  });
}

// ------------------------------------------------------------------ adding operations and dressups

function defaults(fields) {
  const o = {};
  for (const f of fields || []) if (f.def !== undefined) o[f.k] = f.def;
  return o;
}
/** The tool controller for a type: the first whose bit has one of the type's shapes, made from the library when
 *  the job has none. */
function tcFor(ot) {
  const tcs = CM.doc.tools || [];
  const ok = tcs.find(t => { const b = bitOf(t.bit); return b && ot.tools.includes(b.shape); });
  if (ok) return ok.id;
  const b = CM.bits.find(x => ot.tools.includes(x.shape));
  if (b) { const id = addTc(b.id); return id; }
  return tcs.length ? tcs[0].id : "";
}
function addOp(type) {
  if (!hasSource()) { status("Choose a part first", true); return; }
  const ot = OPS[type];
  if (!ot) return;
  const n = (CM.doc.operations || []).filter(o => o.type === type).length + 1;
  const op = Object.assign({ id: nid("op"), name: ot.label + (n > 1 ? " " + n : ""), type, active: true, comment: "", dressups: [] }, defaults(ot.fields));
  if (type === "fixture") { op.shift = [0, 0, 0]; delete op.sx; delete op.sy; delete op.sz; }
  if (!ot.supplemental && !ot.derived) {
    op.tc = tcFor(ot);
    for (const k of ["clearance_height", "safe_height", "start_depth", "final_depth", "step_down", "finish_depth"]) op[k] = null;
    op.feed = null; op.plunge = null; op.ramp_feed = null; op.rpm = null;
    if (ot.finish) Object.assign(op, { finish_mode: ot.finish.def, finish_tc: "", finish_feed: null, finish_plunge: null, finish_rpm: null, finish_step: null, finish_spring: false });
    if (ot.base) { if (ot.base.faces) op.faces = []; if (ot.base.edges) op.edges = []; if (ot.base.points) op.points = []; }
    if (ot.text) op.text = defaults(TEXT_FIELDS);
    if (ot.sketch) op.sketch = null;
    if (type === "drilling") op.through = null;
  }
  if (ot.derived) {
    const cands = (CM.doc.operations || []).filter(o => !(OPS[o.type] || {}).supplemental && !(OPS[o.type] || {}).derived);
    op.of = CM.sel && opOf(CM.sel) && cands.some(o => o.id === CM.sel) ? CM.sel : (cands.length ? cands[cands.length - 1].id : "");
  }
  (CM.doc.operations = CM.doc.operations || []).push(op);
  CM.sel = op.id;
  changed(false);
  renderAll();
  openCommand(op.id, undefined, true);
}
function addDressup(type) {
  const o = CM.cmd ? opOf(CM.cmd.id) : (CM.sel && opOf(CM.sel));
  if (!o) { status("Select an operation first", true); return; }
  const ot = OPS[o.type] || {};
  if (ot.supplemental || ot.derived) { status("A dressup applies to a cutting operation", true); return; }
  if (type === "tag" && (o.dressups || []).some(x => x.type === "tag")) { status("The operation has a Tag dressup", true); return; }
  const dr = Object.assign({ type }, defaults((DRESSUPS[type] || {}).fields));
  if (type === "boundary" && CM.setup && CM.setup.stock_bbox) { const b = CM.setup.stock_bbox; Object.assign(dr, { xmin: b[0], xmax: b[3], ymin: b[1], ymax: b[4] }); }
  (o.dressups = o.dressups || []).push(dr);
  changed(false);
  renderAll();
  openCommand(o.id, o.dressups.length - 1, true);
}

// ------------------------------------------------------------------ machine model and playback

const MACHINE_FIELDS = [["travel_x", "Travel X (mm)"], ["travel_y", "Travel Y (mm)"], ["travel_z", "Travel Z (mm)"], ["table_x", "Table X (mm)"], ["table_y", "Table Y (mm)"], ["table_t", "Table thickness (mm)"],
                        ["home_x", "Travel start X on the table (mm)"], ["home_y", "Travel start Y on the table (mm)"], ["tip_top", "Tool tip at the top of Z (mm above the table)"], ["gantry_clear", "Gantry clearance (mm above the table)"],
                        ["spindle_d", "Spindle diameter (mm)"], ["spindle_len", "Spindle length (mm)"]];
/** Table position (machine coordinates) of the machine zero X Y of the job: doc.machine_pos, else the stock corner
 *  20 mm from the start of the travel. */
function machinePos() {
  const m = CM.machine, su = CM.setup, mp = CM.doc.machine_pos;
  if (mp && isFinite(mp.x) && isFinite(mp.y)) return [mp.x, mp.y];
  if (!m || !su) return [0, 0];
  return [m.home_x + 20 + su.origin[0] - su.stock_bbox[0], m.home_y + 20 + su.origin[1] - su.stock_bbox[1]];
}
/** Job coordinates to machine coordinates: the stock bottom on the table top (Z 0), the machine zero X Y at machinePos. */
function machineOffset() {
  const su = CM.setup;
  if (!su) return [0, 0, 0];
  const [mx, my] = machinePos();
  return [mx - su.origin[0], my - su.origin[1], -su.stock_bbox[2]];
}
/** Moves of the job outside the machine travel: {count, first, ranges}. */
function travelCheck() {
  const m = CM.machine, r = CM.res;
  if (!m || !r || !CM.setup) return null;
  const d = machineOffset(), lo = [m.home_x, m.home_y, m.tip_top - m.travel_z], hi = [m.home_x + m.travel_x, m.home_y + m.travel_y, m.tip_top];
  let count = 0, first = null;
  const mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
  for (const op of r.operations) for (const mv of op.moves || []) {
    if (!mv.p) continue;
    const q = [0, 1, 2].map(i => mv.p[i] + d[i]);
    for (let i = 0; i < 3; i++) { mn[i] = Math.min(mn[i], q[i]); mx[i] = Math.max(mx[i], q[i]); }
    if (q.some((v, i) => v < lo[i] - 1e-6 || v > hi[i] + 1e-6)) { count++; if (!first) first = { op: op.name, p: mv.p }; }
  }
  return { count, first, min: mn, max: mx, lo, hi };
}
function box3(x0, x1, y0, y1, z0, z1, color, opacity) {
  const g = track(new THREE.BoxGeometry(x1 - x0, y1 - y0, z1 - z0));
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color, metalness: 0.2, roughness: 0.7, transparent: opacity < 1, opacity: opacity || 1 }));
  m.position.set((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
  return m;
}
function toolMesh(profile, color) {
  const pts = [new THREE.Vector2(0, profile[0][1])].concat(profile.map(([r, z]) => new THREE.Vector2(Math.max(r, 1e-3), z)));
  pts.push(new THREE.Vector2(0, profile[profile.length - 1][1]));
  const g = track(new THREE.LatheGeometry(pts, 32));
  g.rotateX(Math.PI / 2);
  return new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color, metalness: 0.6, roughness: 0.35, side: THREE.DoubleSide }));
}
/** The router in the view (machine coordinates in a group moved to job coordinates): base, table, rails, gantry
 *  (moves in Y), carriage (X), Z slide with the spindle and the tool; the tool at the playback position. */
function drawMachine() {
  const t = CM.three, m = CM.machine;
  if (!m || !CM.setup) return;
  const d = machineOffset();
  const root = new THREE.Group();
  root.position.set(-d[0], -d[1], -d[2]);
  const show = $("#cm-showmachine").checked && !CM.hidden.machine;
  const tx = m.table_x, ty = m.table_y, tt = m.table_t, gc = m.gantry_clear, sr = m.spindle_d / 2;
  if (show) {
    root.add(box3(-60, tx + 60, -40, ty + 40, -tt - 80, -tt, 0x495057));
    root.add(box3(0, tx, 0, ty, -tt, 0, 0xadb5bd, 0.9));
    root.add(box3(-50, -15, -40, ty + 40, -tt, 25, 0x868e96));
    root.add(box3(tx + 15, tx + 50, -40, ty + 40, -tt, 25, 0x868e96));
    // the travel as a dashed box of the tool tip
    const lo = [m.home_x, m.home_y, m.tip_top - m.travel_z], hi = [m.home_x + m.travel_x, m.home_y + m.travel_y, m.tip_top];
    const tb = new THREE.Box3(new THREE.Vector3(...lo), new THREE.Vector3(...hi));
    const bh = new THREE.Box3Helper(tb, 0x40c057);
    root.add(bh);
  }
  const gantry = new THREE.Group(), carriage = new THREE.Group(), zs = new THREE.Group();
  const s = sr + 40;
  if (show) {
    gantry.add(box3(-50, -10, s - 30, s + 60, 25, gc + 90, 0x1c7ed6));
    gantry.add(box3(tx + 10, tx + 50, s - 30, s + 60, 25, gc + 90, 0x1c7ed6));
    gantry.add(box3(-50, tx + 50, s, s + 60, gc, gc + 90, 0x1971c2));
    carriage.add(box3(-70, 70, s - 25, s, gc - 30, gc + 120, 0x228be6));
  }
  root.add(gantry); gantry.add(carriage); carriage.add(zs);
  CM.mach = { root, gantry, carriage, zs, tool: null, profileOf: null };
  t.group.add(root);
  const pop = CM.play && CM.play.pos && CM.res ? CM.res.operations[CM.play.opi] : null;
  setMachineTool(pop ? pop.profile : null);
  placeMachine(CM.play ? CM.play.pos : null);
}
/** Spindle and tool of the Z slide for the profile of an operation's tool. */
function setMachineTool(profile) {
  const M = CM.mach, m = CM.machine;
  if (!M) return;
  if (M.profileOf === profile && M.zs.children.length) return;
  M.zs.clear();
  M.profileOf = profile;
  const show = $("#cm-showmachine").checked && !CM.hidden.machine;
  const top = profile ? profile[profile.length - 1][1] : 40;
  if (profile) M.zs.add(toolMesh(profile, 0xe9ecef));
  if (show) {
    const g = track(new THREE.CylinderGeometry(m.spindle_d / 2, m.spindle_d / 2, m.spindle_len, 32));
    g.rotateX(Math.PI / 2);
    const sp = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: 0xf1f3f5, metalness: 0.5, roughness: 0.4 }));
    sp.position.set(0, 0, top + 15 + m.spindle_len / 2);
    M.zs.add(sp);
    const nut = new THREE.Mesh(track(new THREE.CylinderGeometry(14, 14, 15, 24)).rotateX(Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x868e96 }));
    nut.position.set(0, 0, top + 7.5);
    M.zs.add(nut);
    M.zs.add(box3(-50, 50, m.spindle_d / 2, m.spindle_d / 2 + 15, top + 30, top + m.spindle_len, 0x74c0fc));
  }
}
/** The gantry, carriage and Z slide at a tool tip position (job coordinates); null: the tool tip at the machine zero, Z at the top. */
function placeMachine(p) {
  const M = CM.mach, m = CM.machine;
  if (!M || !m) return;
  const d = machineOffset();
  const q = p ? [p[0] + d[0], p[1] + d[1], p[2] + d[2]] : [CM.setup.origin[0] + d[0], CM.setup.origin[1] + d[1], m.tip_top];
  M.gantry.position.set(0, q[1], 0);
  M.carriage.position.set(q[0], 0, 0);
  M.zs.position.set(0, 0, q[2]);
}
/** Playback samples of the toolpaths: [{t (s), p, op}] with the moves at their feeds and the rapids at the rapid speeds. */
function playSamples() {
  const r = CM.res, out = [];
  if (!r) return out;
  const su = CM.doc.setup || {}, hr = su.hrapid || 3000, vr = su.vrapid || 1000;
  let t = 0, prev = null;
  r.operations.forEach((op, oi) => {
    if (hiddenItem(op.id)) return;
    for (const mv of op.moves || []) {
      if (!mv.p) continue;
      if (!prev) { prev = mv.p; out.push({ t, p: mv.p, op: oi }); continue; }
      const pts = mv.k === "arc" ? arcPoints(prev, mv.p, mv.c, mv.cw) : [mv.p];
      let q = prev;
      for (const a of pts) {
        const L = Math.hypot(a[0] - q[0], a[1] - q[1], a[2] - q[2]);
        const v = mv.k === "rapid" ? (Math.abs(a[2] - q[2]) > 1e-9 && Math.hypot(a[0] - q[0], a[1] - q[1]) < 1e-9 ? vr : hr) : (mv.f || (mv.k === "plunge" ? op.plunge : op.feed) || 500);
        t += L / v * 60;
        out.push({ t, p: a, op: oi });
        q = a;
      }
      prev = mv.p;
    }
  });
  return out;
}
function playAt(frac) {
  const P = CM.play;
  if (!P || !P.samples.length) return;
  const T = P.samples[P.samples.length - 1].t * Math.max(0, Math.min(1, frac));
  let lo = 0, hi = P.samples.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (P.samples[mid].t <= T) lo = mid; else hi = mid; }
  const a = P.samples[lo], b = P.samples[hi];
  const f = b.t > a.t ? (T - a.t) / (b.t - a.t) : 0;
  const p = [0, 1, 2].map(i => a.p[i] + (b.p[i] - a.p[i]) * Math.min(1, Math.max(0, f)));
  P.pos = p; P.frac = frac; P.opi = b.op;
  const op = CM.res.operations[b.op];
  if (!CM.mach) drawMachine();
  setMachineTool(op && op.profile);
  placeMachine(p);
  const mm = x => `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, "0")}`;
  $("#cm-play-info").textContent = `${op ? op.name : ""}  ${mm(T)} / ${mm(P.samples[P.samples.length - 1].t)}  X ${fmt(p[0], 5)} Y ${fmt(p[1], 5)} Z ${fmt(p[2], 5)} mm`;
  render3();
}
function initPlay() {
  const ok = CM.res && CM.res.operations.some(o => (o.moves || []).length);
  $("#cm-play").hidden = !ok;
  if (!ok) { CM.play = null; return; }
  const frac = CM.play ? CM.play.frac : 0;
  CM.play = { samples: playSamples(), frac, pos: null, running: false };
  $("#cm-play-slider").value = Math.round(frac * 1000);
  if (frac > 0) playAt(frac);
}
function playStep(ts) {
  const P = CM.play;
  if (!P || !P.running) return;
  if (P.last != null) {
    const total = P.samples.length ? P.samples[P.samples.length - 1].t : 0;
    const f = P.frac + (ts - P.last) / 1000 * (+$("#cm-play-speed").value || 1) / Math.max(total, 1e-6);
    if (f >= 1) { P.running = false; $("#cm-play-btn").textContent = "▶"; }
    playAt(Math.min(1, f));
    $("#cm-play-slider").value = Math.round(Math.min(1, f) * 1000);
  }
  P.last = ts;
  if (P.running) requestAnimationFrame(playStep);
}
function renderMachineProps(box) {
  const m = CM.machine || {}, mp = machinePos(), tc = travelCheck();
  box.innerHTML = `<div class="hint">Router model for the view and the travel check (the same for all jobs; Save machine keeps it in the configuration). Machine coordinates: table top Z 0, table corner X 0 Y 0.</div>
    <div class="row">${MACHINE_FIELDS.map(([k, l]) => numField(l, k, m[k])).join("")}</div>
    <div class="row"><button type="button" id="cm-mach-save" class="small primary">Save machine</button></div>
    <div class="pt-sec">Job on the table</div>
    <div class="row"><label class="cm-f" title="Table position of the machine zero X of the job">Machine zero X on the table (mm)<input type="text" class="numf" data-mp="x" value="${fmt(mp[0], 6)}"></label><label class="cm-f">Machine zero Y on the table (mm)<input type="text" class="numf" data-mp="y" value="${fmt(mp[1], 6)}"></label><button type="button" class="small" id="cm-mp-reset" title="The stock corner 20 mm from the start of the travel">Default</button></div>
    <div class="hint">The stock bottom stands on the table top.</div>` +
    (tc ? (tc.count ? `<div class="cm-err">${tc.count} move(s) outside the travel; first in ${esc(tc.first.op)} at X ${fmt(tc.first.p[0])} Y ${fmt(tc.first.p[1])} Z ${fmt(tc.first.p[2])} mm (job)</div>` : `<div class="cm-ok">All moves inside the travel</div>`) +
      `<div class="hint">Tool tip range X ${fmt(tc.min[0], 5)}..${fmt(tc.max[0], 5)}, Y ${fmt(tc.min[1], 5)}..${fmt(tc.max[1], 5)}, Z ${fmt(tc.min[2], 5)}..${fmt(tc.max[2], 5)} mm (machine); travel X ${fmt(tc.lo[0])}..${fmt(tc.hi[0])}, Y ${fmt(tc.lo[1])}..${fmt(tc.hi[1])}, Z ${fmt(tc.lo[2])}..${fmt(tc.hi[2])} mm</div>` : `<div class="hint">Simulate for the travel check.</div>`);
  bindFields(box, m, () => { CM.mach = null; draw(); renderMachineProps(box); }, false);
  box.querySelectorAll("[data-mp]").forEach(inp => inp.onchange = () => {
    const v = num(inp.value);
    if (!isFinite(v)) { renderMachineProps(box); return; }
    const cur = machinePos();
    CM.doc.machine_pos = { x: cur[0], y: cur[1] };
    CM.doc.machine_pos[inp.dataset.mp] = v;
    changed(false); draw(); renderMachineProps(box);
  });
  $("#cm-mp-reset").onclick = () => { delete CM.doc.machine_pos; changed(false); draw(); renderMachineProps(box); };
  $("#cm-mach-save").onclick = async () => {
    try { CM.machine = await (await api("/api/cam/machine", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(m) })).json(); status("Machine saved"); draw(); renderMachineProps(box); } catch (e) { showErr(e); }
  };
}

// ------------------------------------------------------------------ part refresh

/** The part file compared with the loaded geometry: a changed part marks Refresh (the update itself is manual). */
async function checkPart() {
  if (!CM.doc || !hasSource() || !CM.geo || $("#tab-cam").hidden) return;
  try {
    const r = await (await postJSON("/api/cam/part_state", { cam: CM.doc })).json();
    const stale = !!(r.key && CM.geo && CM.geo.part_key && r.key !== CM.geo.part_key);
    if (stale !== !!CM.partStale) {
      CM.partStale = stale;
      $("#cm-refresh").classList.toggle("cm-stale", stale);
      $("#cm-refresh").title = stale ? "The part has changed since it was loaded: Refresh loads it again" : "Load the part again (after a change in the Part tab)";
      if (stale) status("The part " + CM.doc.source.name + " has changed: Refresh updates the CAM model");
    }
  } catch (e) { /* the next check */ }
}
/** The part loaded again; the picks of the operations are found again by their centres and the ones that are not
 *  found are listed. */
async function refreshPart() {
  if (!hasSource()) { status("Choose a part first", true); return; }
  await loadGeometry();
  CM.partStale = false;
  $("#cm-refresh").classList.remove("cm-stale");
  const lost = [];
  for (const o of CM.doc.operations || []) {
    (o.faces || []).forEach((f, i) => { if (faceIndex(f) < 0) lost.push(`${o.name} face ${i + 1}`); });
    (o.edges || []).forEach((e, i) => { if (edgeIndex(e) < 0) lost.push(`${o.name} edge ${i + 1}`); });
  }
  CM.lostPicks = lost;
  status(lost.length ? `Part reloaded; ${lost.length} pick(s) not found: ${lost.slice(0, 4).join(", ")}${lost.length > 4 ? ", …" : ""}` : "Part reloaded; all picks found", !!lost.length);
  if (CM.placeRes !== undefined && (placementOf().constraints || []).length) solvePlacement();
  renderTree(); renderProps();
}

// ------------------------------------------------------------------ machine zero at a vertex

/** The vertices of the part: the end points of its edges (job coordinates). */
function geoVertices() {
  const g = CM.geo;
  if (!g) return [];
  if (g._verts) return g._verts;
  const out = [], seen = new Set();
  for (const pl of g.edges || []) for (const p of pl.length ? [pl[0], pl[pl.length - 1]] : []) {
    const k = p.map(v => Math.round(v * 1e4)).join(",");
    if (!seen.has(k)) { seen.add(k); out.push(p); }
  }
  return (g._verts = out);
}
/** The vertex nearest to the cursor within 12 px, or null. */
function vertexAt(e) {
  const t = CM.three, r = t.renderer.domElement.getBoundingClientRect();
  t.camera.updateMatrixWorld(true);
  let best = null, bd = 12;
  for (const p of geoVertices()) {
    const q = new THREE.Vector3(p[0], p[1], p[2]).project(t.camera);
    const d = Math.hypot(r.left + (q.x + 1) / 2 * r.width - e.clientX, r.top + (1 - q.y) / 2 * r.height - e.clientY);
    if (d < bd) { bd = d; best = p; }
  }
  return best;
}
function startZeroPick() {
  if (!CM.geo) { status("Choose a part first", true); return; }
  if (CM.measure) setMeasure(false);
  CM.zeroPick = true;
  $("#cm-zero").classList.add("active");
  status("Click a vertex of the part: the machine zero (Esc: cancel)");
  if (CM.sel === "stock") renderProps();
}
function endZeroPick() {
  CM.zeroPick = false;
  $("#cm-zero").classList.remove("active");
  clearHover(); render3();
  if (CM.sel === "stock") renderProps();
}
function hoverZero(e) {
  const t = CM.three;
  clearHover();
  const p = vertexAt(e);
  if (p) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
    const m = new THREE.Points(g, new THREE.PointsMaterial({ color: COLORS.sel, size: 11, sizeAttenuation: false, depthTest: false }));
    m.renderOrder = 12;
    t.hover = m; t.scene.add(m);
  }
  t.renderer.domElement.style.cursor = p ? "crosshair" : "";
  render3();
}
function clickZero(e) {
  const p = vertexAt(e);
  if (!p) { status("No vertex under the cursor", true); return; }
  const og = CM.doc.origin || (CM.doc.origin = {});
  og.xy = "point"; og.z = "point"; og.point = p.map(v => Math.round(v * 1e4) / 1e4 + 0);
  endZeroPick();
  CM.sel = "stock";
  changed();
  loadSetup().then(() => { renderTree(); renderProps(); setupHint(); draw(); });
  status(`Machine zero at X ${fmt(og.point[0])} Y ${fmt(og.point[1])} Z ${fmt(og.point[2])} mm`);
}

// ------------------------------------------------------------------ model placement

/** Drag of the part in the view (placement window, Drag on): left drag on the part moves it in the plane Z = the
 *  grabbed point (Shift: along Z); the part is shown moved, the release solves the constraints with the drag. */
function startPartDrag(e) {
  const c = CM.cmd, t = CM.three;
  if (!c || !c.place || !c.drag || e.button !== 0 || !t.faceMesh) return;
  const h = hitAt(e);
  if (!h) return;
  t.controls.enabled = false;
  const g0 = h.point.clone(), vertical = e.shiftKey;
  const n = vertical ? new THREE.Vector3().subVectors(t.camera.position, t.controls.target).setZ(0).normalize() : new THREE.Vector3(0, 0, 1);
  if (vertical && n.lengthSq() < 1e-9) n.set(0, -1, 0);
  const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(n, g0);
  const parts = t.group.children.filter(o => o === t.faceMesh || o.userData.part);
  let delta = new THREE.Vector3();
  const move = ev => {
    const q = new THREE.Vector3();
    if (!rayAt(ev).ray.intersectPlane(plane, q)) return;
    delta = q.sub(g0);
    if (vertical) delta.set(0, 0, delta.z); else delta.z = 0;
    if (ev.ctrlKey) delta.set(Math.round(delta.x), Math.round(delta.y), Math.round(delta.z));
    for (const o of parts) o.position.copy(delta);
    status(`Drag ${fmt(delta.x, 4)}, ${fmt(delta.y, 4)}, ${fmt(delta.z, 4)} mm${ev.ctrlKey ? " (1 mm steps)" : " (Ctrl: 1 mm steps)"}`);
    render3();
  };
  const up = async () => {
    window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
    t.controls.enabled = true;
    if (delta.lengthSq() < 1e-12) { for (const o of parts) o.position.set(0, 0, 0); render3(); return; }
    try {
      const r = await (await postJSON("/api/cam/placement", { cam: CM.doc, drag: { delta: [delta.x, delta.y, delta.z] } })).json();
      CM.placeRes = r;
      placementOf().constraints = r.constraints;
      if (!setPlacement(r.pos, r.rot)) draw();
    } catch (err) { showErr(err); draw(); }
    renderPlacementAll();
  };
  window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  e.stopPropagation();
}

const PC_TYPES = [["coincident", "Coincident"], ["distance", "Distance"], ["parallel", "Parallel"], ["angle", "Angle"], ["concentric", "Concentric"]];
const PC_HELP = { coincident: "A planar face or a straight edge in a datum plane, a vertex on a datum plane or axis, a cylinder axis or straight edge on a datum axis", distance: "A planar face, straight edge or vertex at a distance from a datum plane",
                  parallel: "A planar face parallel to a datum plane, or a cylinder axis or straight edge parallel to a datum axis", angle: "A planar face or a straight edge at an angle to a datum plane, or a straight edge at an angle to a datum axis (a face parallel to the datum turns about its longest straight edge; a negative value turns it the other way)",
                  concentric: "A cylindrical face or circular edge on a datum axis" };
const DATUM_OPTS = [["XY", "XY plane (table)"], ["XZ", "XZ plane"], ["YZ", "YZ plane"], ["X", "X axis"], ["Y", "Y axis"], ["Z", "Z axis"]];
/** Rotation matrix Rz Ry Rx of rotations (deg) about the fixed X, Y, Z axes (assembly convention). */
function rotMatrix(rot) {
  const [ax, ay, az] = (rot || [0, 0, 0]).map(v => (v || 0) * Math.PI / 180);
  const cx = Math.cos(ax), sx = Math.sin(ax), cy = Math.cos(ay), sy = Math.sin(ay), cz = Math.cos(az), sz = Math.sin(az);
  return [[cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx], [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx], [-sy, cy * sx, cy * cx]];
}
const mv = (R, v) => [0, 1, 2].map(i => R[i][0] * v[0] + R[i][1] * v[1] + R[i][2] * v[2]);
const mtv = (R, v) => [0, 1, 2].map(i => R[0][i] * v[0] + R[1][i] * v[1] + R[2][i] * v[2]);
/** The picked faces, edges and points of the operations moved with the part from one placement to another. */
function remapPicks(from, to) {
  const Ro = rotMatrix(from.rot), Rn = rotMatrix(to.rot), po = from.pos || [0, 0, 0], pn = to.pos || [0, 0, 0];
  const pt = p => { const l = mtv(Ro, [p[0] - po[0], p[1] - po[1], p[2] - po[2]]); const q = mv(Rn, l); return [q[0] + pn[0], q[1] + pn[1], q[2] + pn[2]].map(v => Math.round(v * 1e6) / 1e6); };
  const dir = n => mv(Rn, mtv(Ro, n)).map(v => Math.round(v * 1e9) / 1e9);
  for (const o of CM.doc.operations || []) {
    for (const f of o.faces || []) { if (f.c) f.c = pt(f.c); if (f.n) f.n = dir(f.n); }
    for (const e of o.edges || []) if (e.mid) e.mid = pt(e.mid);
    if (o.points) o.points = o.points.map(p => p.length >= 3 ? pt(p) : pt([p[0], p[1], 0]).slice(0, 2));
  }
  const og = CM.doc.origin;
  if (og && og.point) og.point = pt(og.point);
}
function placementOf() {
  const pl = CM.doc.placement || (CM.doc.placement = { pos: [0, 0, 0], rot: [0, 0, 0], constraints: [], next: 1 });
  pl.pos = pl.pos || [0, 0, 0]; pl.rot = pl.rot || [0, 0, 0]; pl.constraints = pl.constraints || []; pl.next = pl.next || pl.constraints.length + 1;
  return pl;
}
/** A new position and rotation of the part: the picks of the operations follow, the geometry and the stock are loaded again. */
function setPlacement(pos, rot) {
  const pl = placementOf();
  const from = { pos: pl.pos.slice(), rot: pl.rot.slice() };
  const same = from.pos.every((v, i) => Math.abs(v - pos[i]) < 1e-9) && from.rot.every((v, i) => Math.abs(v - rot[i]) < 1e-9);
  pl.pos = pos.slice(); pl.rot = rot.slice();
  if (same) return false;
  remapPicks(from, pl);
  if (placing()) dropPreview();
  changed(false);
  if (CM.three) CM.three.zoomed = false;
  loadGeometry();
  return true;
}
/** Solve of the placement constraints on the server from the current placement. */
async function solvePlacement() {
  const pl = placementOf();
  if (!pl.constraints.some(c => !c.suppressed)) { CM.placeRes = null; renderPlacementAll(); return; }
  const seq = (CM.placeSeq = (CM.placeSeq || 0) + 1);
  try {
    const r = await (await postJSON("/api/cam/placement", { cam: CM.doc })).json();
    if (seq !== CM.placeSeq) return;
    CM.placeRes = r;
    pl.constraints = r.constraints;
    if (!setPlacement(r.pos, r.rot)) changed(false);
  } catch (e) { showErr(e); }
  renderPlacementAll();
}
/** Tree, properties, the placement window (after the event that called it: a change event fires during a blur) and the selection. */
function renderPlacementAll() { renderTree(); renderProps(); drawSelection(); setTimeout(() => { if (CM.cmd && CM.cmd.place) renderCommand(true); }, 0); }
function openPlacement() {
  if (!hasSource()) { status("Choose a part first", true); return; }
  if (CM.cmd && !CM.cmd.place) closeCommand(true);
  if (!CM.cmd) CM.cmd = { place: true, id: null, pick: null, snapshot: JSON.stringify(placementOf()), snapOps: JSON.stringify(CM.doc.operations || []) };
  CM.sel = "model";
  renderTree(); renderProps(); renderCommand(true); draw();
}
function closePlacement(keep) {
  const c = CM.cmd;
  if (!keep) {
    const old = JSON.parse(c.snapshot), cur = placementOf();
    CM.doc.operations = JSON.parse(c.snapOps);
    CM.doc.placement = old;
    const moved = old.pos.some((v, i) => Math.abs(v - cur.pos[i]) > 1e-9) || old.rot.some((v, i) => Math.abs(v - cur.rot[i]) > 1e-9);
    changed(false);
    if (moved) { if (CM.three) CM.three.zoomed = false; loadGeometry(); }
    CM.placeRes = null;
  }
  CM.cmd = null;
  if (!CM.res && hasSource() && (CM.doc.operations || []).length) schedulePreview(0);
  $("#cm-cmdwin").hidden = true;
  clearHover();
  renderTree(); renderProps(); draw();
}
function deleteConstraint(id) {
  const pl = placementOf();
  pl.constraints = pl.constraints.filter(c => c.id !== id);
  if (CM.sel === "pc:" + id) CM.sel = "part";
  changed(false);
  solvePlacement();
}
/** A face of the part clicked while a constraint type is chosen: the constraint with the datum and Flip that keep the
 *  part where it is (the server suggests them), then the solve. */
async function placePick(what) {
  const c = CM.cmd, type = c.pick;
  if (typeof what === "number") what = { face: what };
  try {
    const sg = await (await postJSON("/api/cam/placement", { cam: CM.doc, suggest: Object.assign({ type }, what) })).json();
    const pl = placementOf();
    const pc = { id: "pc" + (pl.next++), type, datum: sg.datum, flip: sg.flip, value: sg.value, suppressed: false };
    if (what.face !== undefined) pc.face = what.face;
    if (sg.edge !== undefined) { pc.edge = sg.edge; pc.ec = sg.ec; }
    if (sg.vertex !== undefined) { pc.vertex = sg.vertex; pc.vc = sg.vc; }
    pl.constraints.push(pc);
    c.pick = null;
    c.last = pc.id;
    status(`${pcLabel(pc)} added`);
    await solvePlacement();
  } catch (e) { showErr(e); }
}
function placementHtml(c) {
  const pl = placementOf(), res = CM.placeRes;
  let h = `<p class="hint">Constraints of faces, edges and vertices of the part to the datum planes and axes of the job coordinate system (XY: the table plane, +Z: the spindle). Position and rotation without constraints, or the start of the solve.</p>`;
  h += `<div class="cw-pcbtns">${PC_TYPES.map(([t, l]) => `<button type="button" class="small ico-mini${c.pick === t ? " active" : ""}" data-pctype="${t}" title="${esc(PC_HELP[t])}: click the type, then a face of the part">${(window.treeIcon && window.treeIcon(PC_ICON[t], 18)) || ""}${l}</button>`).join("")}</div>`;
  const pk = c.pickKind || "faces";
  h += `<div class="cw-modes">${[["faces", "Faces"], ["edges", "Edges"], ["vertices", "Vertices"]].map(([v, l]) => `<label class="check"><input type="radio" name="cm-pkind" value="${v}"${v === pk ? " checked" : ""}> ${l}</label>`).join("")}
    <button type="button" class="small${c.drag ? " active primary" : ""}" id="cm-pdrag" title="Drag mode: left drag on the part moves it in X and Y (Shift: in Z) as far as the constraints allow">Drag</button></div>`;
  if (c.pick) h += `<p class="hint cw-hint">${esc(PC_HELP[c.pick])}: click ${pk === "edges" ? "an edge" : pk === "vertices" ? "a vertex" : "a face"} of the part (Esc: cancel)</p>`;
  if (pl.constraints.length) {
    h += `<table class="fa-tbl cw-pctbl"><tr><th>Constraint</th><th>Datum</th><th>Value</th><th>Flip</th><th>Off</th><th></th></tr>`;
    for (const k of pl.constraints) {
      const bad = res && (res.unsatisfied || {})[k.id];
      const val = k.type === "distance" || k.type === "angle" ? `<input type="text" class="numf" data-pcv="${esc(k.id)}" value="${fmt(k.value, 6)}" title="${k.type === "distance" ? "mm" : "deg (negative: the turn in the other direction)"}">` : "";
      h += `<tr data-pc="${esc(k.id)}" class="${bad ? "bad" : ""}${k.id === c.last ? " last" : ""}"><td>${(PC_TYPES.find(x => x[0] === k.type) || [0, k.type])[1]} ${pcWhat(k)}</td>` +
        `<td><select data-pcd="${esc(k.id)}">${DATUM_OPTS.map(([v, l]) => `<option value="${v}"${v === k.datum ? " selected" : ""}>${v}</option>`).join("")}</select></td><td>${val}</td>` +
        `<td><input type="checkbox" data-pcf="${esc(k.id)}"${k.flip ? " checked" : ""} title="Turn the face the other way"></td><td><input type="checkbox" data-pcs="${esc(k.id)}"${k.suppressed ? " checked" : ""} title="Suppressed"></td>` +
        `<td><button type="button" class="small" data-pcdel="${esc(k.id)}" title="Delete">×</button></td></tr>` + (bad ? `<tr class="bad"><td colspan="6" class="cm-err">${esc(bad)}</td></tr>` : "");
    }
    h += `</table>`;
  }
  return h;
}
function positionHtml() {
  const pl = placementOf();
  return `<div class="cm-grid cm-grid3">${[0, 1, 2].map(i => `<label class="cm-f">${"XYZ"[i]} (mm)<input type="text" class="numf" data-ppos="${i}" value="${fmt(pl.pos[i], 7)}"></label>`).join("")}` +
    `${[0, 1, 2].map(i => `<label class="cm-f" title="Rotations about the fixed X, then Y, then Z axis about the part origin, before the translation">Rot ${"XYZ"[i]} (deg)<input type="text" class="numf" data-prot="${i}" value="${fmt(pl.rot[i], 7)}"></label>`).join("")}</div>
    <div class="buttons">${["X", "Y", "Z"].map((a, i) => `<button type="button" class="small" data-pturn="${i}" title="Turn the part 90 deg about the job ${a} axis through the centre of the part">${a} +90°</button>`).join("")}
    <button type="button" class="small" data-pdrop="1" title="Move the part so that its lowest point is on the XY plane and its bounding box starts at X 0, Y 0">Onto XY at 0, 0</button>
    <button type="button" class="small" data-preset="1" title="Position and rotation 0 (the constraints are kept)">Reset</button></div>
    ${pl.constraints.some(c => !c.suppressed) ? `<p class="hint">With active constraints a change here is the start of a new solve.</p>` : ""}`;
}
/** Turn about a job axis through the centre of the part bounding box. */
function turnPart(axis) {
  const pl = placementOf(), g = CM.geo;
  const ctr = g && g.bbox ? [0, 1, 2].map(i => (g.bbox[i] + g.bbox[i + 3]) / 2) : pl.pos.slice();
  const Rq = rotMatrix([axis === 0 ? 90 : 0, axis === 1 ? 90 : 0, axis === 2 ? 90 : 0]);
  const R = rotMatrix(pl.rot), Rn = [0, 1, 2].map(i => [0, 1, 2].map(j => Rq[i][0] * R[0][j] + Rq[i][1] * R[1][j] + Rq[i][2] * R[2][j]));
  // Euler angles of Rn in the convention of rotMatrix
  const sy = Math.max(-1, Math.min(1, -Rn[2][0])), ry = Math.asin(sy);
  let rx, rz;
  if (Math.abs(sy) < 0.999999) { rx = Math.atan2(Rn[2][1], Rn[2][2]); rz = Math.atan2(Rn[1][0], Rn[0][0]); } else { rx = Math.atan2(-Rn[1][2], Rn[1][1]); rz = 0; }
  const rot = [rx, ry, rz].map(v => Math.round(v * 180 / Math.PI * 1e6) / 1e6 + 0);
  const d = [pl.pos[0] - ctr[0], pl.pos[1] - ctr[1], pl.pos[2] - ctr[2]], q = mv(Rq, d);
  return { pos: [0, 1, 2].map(i => Math.round((ctr[i] + q[i]) * 1e6) / 1e6), rot };
}
function bindPlacement(box) {
  const c = CM.cmd, pl = placementOf();
  const find = id => pl.constraints.find(k => k.id === id);
  box.querySelectorAll("[data-pctype]").forEach(b => b.onclick = () => { c.pick = c.pick === b.dataset.pctype ? null : b.dataset.pctype; c.drag = false; renderCommand(true); draw(); });
  box.querySelectorAll("input[name=cm-pkind]").forEach(r => r.onchange = () => { c.pickKind = r.value; renderCommand(true); draw(); });
  box.querySelector("#cm-pdrag").onclick = () => { c.drag = !c.drag; if (c.drag) c.pick = null; renderCommand(true); draw(); };
  box.querySelectorAll("[data-pcd]").forEach(sel => sel.onchange = () => { find(sel.dataset.pcd).datum = sel.value; changed(false); solvePlacement(); });
  box.querySelectorAll("[data-pcv]").forEach(inp => inp.onchange = () => { const v = num(inp.value); if (!isFinite(v)) { renderPlacementAll(); return; } find(inp.dataset.pcv).value = v; changed(false); solvePlacement(); });
  box.querySelectorAll("[data-pcf]").forEach(inp => inp.onchange = () => { find(inp.dataset.pcf).flip = inp.checked; changed(false); solvePlacement(); });
  box.querySelectorAll("[data-pcs]").forEach(inp => inp.onchange = () => { find(inp.dataset.pcs).suppressed = inp.checked; changed(false); solvePlacement(); });
  box.querySelectorAll("[data-pcdel]").forEach(b => b.onclick = () => deleteConstraint(b.dataset.pcdel));
  box.querySelectorAll("tr[data-pc]").forEach(tr => {
    tr.onmouseenter = () => { CM.chipHover = { pc: tr.dataset.pc }; drawSelection(); };
    tr.onmouseleave = () => { CM.chipHover = null; drawSelection(); };
  });
  const after = () => { if (pl.constraints.some(k => !k.suppressed)) solvePlacement(); else renderPlacementAll(); };
  box.querySelectorAll("[data-ppos], [data-prot]").forEach(inp => inp.onchange = () => {
    const v = num(inp.value);
    if (!isFinite(v)) { renderPlacementAll(); return; }
    const pos = pl.pos.slice(), rot = pl.rot.slice();
    if (inp.dataset.ppos !== undefined) pos[+inp.dataset.ppos] = v; else rot[+inp.dataset.prot] = v;
    setPlacement(pos, rot); after();
  });
  box.querySelectorAll("[data-pturn]").forEach(b => b.onclick = () => { const t = turnPart(+b.dataset.pturn); setPlacement(t.pos, t.rot); after(); });
  const dr = box.querySelector("[data-pdrop]");
  if (dr) dr.onclick = () => { const g = CM.geo; if (!g || !g.bbox) return; setPlacement([pl.pos[0] - g.bbox[0], pl.pos[1] - g.bbox[1], pl.pos[2] - g.bbox[2]], pl.rot); after(); };
  const rs = box.querySelector("[data-preset]");
  if (rs) rs.onclick = () => { setPlacement([0, 0, 0], [0, 0, 0]); after(); };
}
/** The datum planes XY, XZ, YZ (translucent squares) and the axes of the job coordinate system while the placement is edited. */
function drawDatums(box) {
  const t = CM.three, g = CM.geo;
  const s = g && g.bbox ? Math.max(g.bbox[3] - g.bbox[0], g.bbox[4] - g.bbox[1], g.bbox[5] - g.bbox[2], 10) * 0.6 : 50;
  const planes = [["XY", 0xf08c00, [[-s, -s, 0], [s, -s, 0], [s, s, 0], [-s, s, 0]]], ["XZ", 0x2b8a3e, [[-s, 0, -s], [s, 0, -s], [s, 0, s], [-s, 0, s]]], ["YZ", 0xe03131, [[0, -s, -s], [0, s, -s], [0, s, s], [0, -s, s]]]];
  for (const [, col, q] of planes) {
    const gm = track(new THREE.BufferGeometry());
    gm.setAttribute("position", new THREE.Float32BufferAttribute([...q[0], ...q[1], ...q[2], ...q[0], ...q[2], ...q[3]], 3));
    const m = new THREE.Mesh(gm, new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false }));
    t.group.add(m);
    const ge = track(new THREE.BufferGeometry());
    ge.setAttribute("position", new THREE.Float32BufferAttribute([...q[0], ...q[1], ...q[1], ...q[2], ...q[2], ...q[3], ...q[3], ...q[0]], 3));
    t.group.add(new THREE.LineSegments(ge, new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.6 })));
    box.expandByObject(m);
  }
}

// ------------------------------------------------------------------ command window

/** Opens the command window for an operation (dr: the index of one of its dressups; isNew: Cancel removes it). */
function openCommand(id, dr, isNew) {
  const o = opOf(id);
  if (!o) return;
  if (CM.cmd && (CM.cmd.id !== id || CM.cmd.dr !== dr)) closeCommand(true);
  const ot = OPS[o.type] || {};
  CM.cmd = { id, dr, isNew: !!isNew, step: dr === undefined && ot.base ? 0 : dr === undefined && ot.depths ? 1 : 3, mode: null, snapshot: JSON.stringify(o) };
  CM.sel = dr === undefined ? id : `dr:${id}:${dr}`;
  renderTree(); renderProps(); renderCommand(true); draw();
  schedulePreview(0);
}
/** Closes the window; keep false: the operation as it was when the window opened (a new operation or dressup
 *  removed). */
function closeCommand(keep) {
  const c = CM.cmd;
  if (!c) return;
  if (c.place) { closePlacement(keep); return; }
  if (!keep) {
    const i = opIndex(c.id);
    if (i >= 0) {
      if (c.isNew && c.dr === undefined) { CM.doc.operations.splice(i, 1); if (CM.sel === c.id) CM.sel = null; }
      else if (c.isNew) { (CM.doc.operations[i].dressups || []).splice(c.dr, 1); CM.sel = c.id; }
      else CM.doc.operations[i] = JSON.parse(c.snapshot);
      changed(false);
    }
  }
  CM.cmd = null; CM.chipHover = null;
  $("#cm-cmdwin").hidden = true;
  clearHover();
  renderTree(); renderProps(); draw();
  schedulePreview(0);
}
function renderCommand(force) {
  const c = CM.cmd, box = $("#cm-cmdbody");
  if (!c) { $("#cm-cmdwin").hidden = true; return; }
  const ae = document.activeElement;
  if (!force && ae && box.contains(ae) && ae.matches("input, select, textarea")) return;
  if (c.place) {
    const res = CM.placeRes;
    let h = `<div class="cmd cw">` + section(0, true, true, "Constraints", placementHtml(c), `${placementOf().constraints.length}`) + section(1, true, true, "Position", positionHtml(), placementText(placementOf()));
    h += `<div class="cw-result">${((res && res.messages) || []).map(m => `<p class="hint err">${esc(m)}</p>`).join("")}</div>`;
    h += `<div class="cw-foot cmd-foot"><button type="button" id="cm-cmd-ok" class="primary">OK</button><button type="button" id="cm-cmd-cancel" title="The placement as it was when the window opened">Cancel</button></div></div>`;
    box.innerHTML = h;
    $("#cm-cmdwin-title").textContent = "Model placement";
    bindPlacement(box);
    box.querySelector("#cm-cmd-ok").onclick = () => closeCommand(true);
    box.querySelector("#cm-cmd-cancel").onclick = () => closeCommand(false);
    $("#cm-cmdwin").hidden = false;
    placeCmdWin();
    return;
  }
  const o = opOf(c.id);
  if (!o) { CM.cmd = null; $("#cm-cmdwin").hidden = true; return; }
  const ot = OPS[o.type] || {};
  const r = recOf(o.id);
  let h = `<div class="cmd cw">`;
  if (c.dr !== undefined) {
    const dr = (o.dressups || [])[c.dr];
    if (!dr) { closeCommand(true); return; }
    const dd = DRESSUPS[dr.type] || { fields: [] };
    h += `<div class="cw-name"><label>Dressup of<span>${esc(o.name)}</span></label></div>`;
    h += section(3, true, false, dd.label, fieldsHtml(dd.fields, dr), "");
    $("#cm-cmdwin-title").textContent = dd.label;
  } else {
    h += `<div class="cw-name"><label>Name<input type="text" id="cm-opname" value="${esc(o.name)}"></label></div>`;
    if (ot.base || ot.sketch || ot.text) h += section(0, c.step === 0, baseDone(o, ot), "Base geometry", baseHtml(o, ot, c), baseSummary(o));
    if (ot.depths) h += section(1, c.step === 1, true, "Depths", depthsHtml(o, r), "");
    if (ot.depths) h += section(2, c.step === 2, true, "Heights", heightsHtml(o, r), "");
    h += section(3, c.step === 3, true, "Operation", opHtml(o, ot), "");
    if (ot.finish) h += section(4, c.step === 4, true, "Finish", finishHtml(o, ot), finishSummary(o));
    $("#cm-cmdwin-title").textContent = opLabel(o);
  }
  h += `<div class="cw-result">`;
  if (r) { for (const e of r.errors || []) h += `<p class="hint err">${esc(e)}</p>`; for (const m of (r.messages || []).slice(0, 4)) h += `<p class="hint">${esc(m)}</p>`; }
  else if (CM.previewTimer || CM.previewSeq) h += `<p class="hint">Computing…</p>`;
  h += `</div><div class="cw-foot cmd-foot"><button type="button" id="cm-cmd-ok" class="primary">OK</button><button type="button" id="cm-cmd-cancel" title="${c.isNew ? "Remove the new operation" : "The operation as it was when the window opened"}">Cancel</button></div></div>`;
  box.innerHTML = h;
  const nm = box.querySelector("#cm-opname");
  if (nm) nm.onchange = () => { o.name = nm.value.trim() || o.name; changed(false); renderTree(); };
  box.querySelectorAll(".cw-sec").forEach(sec => {
    const i = +sec.dataset.step;
    sec.querySelector(".cw-sec-head").onclick = () => { if (i !== c.step) { c.step = i; renderCommand(true); draw(); } };
    sec.addEventListener("focusin", () => { if (CM.cmd && i !== c.step) { c.step = i; box.querySelectorAll(".cw-sec").forEach(s => s.classList.toggle("active", +s.dataset.step === i)); draw(); } });
  });
  const target = c.dr !== undefined ? (o.dressups || [])[c.dr] : o;
  bindFields(box, target, k => {
    if ((k === "tc" || k === "finish_tc") && String(target[k] || "").startsWith("bit:")) {
      const tc = makeTc(target[k].slice(4));
      target[k] = tc ? tc.id : null;
      if (tc) status(`${tc.id} ${tc.name} added to the job`);
      renderCommand(true);
    }
    if (k === "through") target.through = target.through === "auto" ? null : target.through === "through";
    if (k === "of" || k === "kind" || k === "boundary" || k === "pattern" || k === "mode" || k === "finish_mode" || k === "finish_tc") renderCommand(true);
    changed(); renderTree();
  }, true);
  if (c.dr === undefined) bindBase(box, o, ot, c);
  // fields of nested objects: the text {text, size, ...} and the fixture shift
  box.querySelectorAll("[data-tk]").forEach(inp => inp.onchange = () => {
    const tx = o.text || (o.text = {}); const k = inp.dataset.tk;
    if (inp.tagName === "SELECT" || k === "text" || k === "font") tx[k] = inp.value; else { const v = num(inp.value); tx[k] = isFinite(v) ? v : 0; }
    changed();
  });
  box.querySelectorAll("[data-sk]").forEach(inp => inp.onchange = () => { const v = num(inp.value); o.shift = o.shift || [0, 0, 0]; o.shift[+inp.dataset.sk] = isFinite(v) ? v : 0; changed(); });
  box.querySelector("#cm-cmd-ok").onclick = () => closeCommand(true);
  box.querySelector("#cm-cmd-cancel").onclick = () => closeCommand(false);
  const fsb = box.querySelector("#cm-fs-op");
  if (fsb) fsb.onclick = () => applyFeedsOp(o);
  const ffb = box.querySelector("#cm-fs-fin");
  if (ffb) ffb.onclick = () => applyFeedsFinish(o);
  $("#cm-cmdwin").hidden = false;
  placeCmdWin();
}
const section = (i, active, done, label, body, sum) => `<section class="cw-sec${active ? " active" : ""}${done ? " done" : ""}${i === 0 ? " pick" : ""}" data-step="${i}">` +
  `<div class="cw-sec-head"><span class="cw-mark">${done ? "✓" : "●"}</span><span class="lbl">${esc(label)}</span><span class="sum">${esc(sum || "")}</span></div><div class="cw-sec-body">${body}</div></section>`;
function fieldHtml(f, obj, attr = "data-k") {
  const v = obj[f.k];
  if (f.kind === "sel") {
    let opts = f.opts;
    if (f.k === "of") opts = (CM.doc.operations || []).filter(x => x.id !== obj.id && !(OPS[x.type] || {}).supplemental && !(OPS[x.type] || {}).derived).map(x => [x.id, x.name]);
    return `<label class="cm-f"${f.title ? ` title="${esc(f.title)}"` : ""}>${esc(f.label)}<select ${attr}="${f.k}">${opts.map(([a, b]) => `<option value="${esc(a)}"${String(a) === String(v === null || v === undefined ? "auto" : v) ? " selected" : ""}>${esc(b)}</option>`).join("")}</select></label>`;
  }
  if (f.kind === "chk") return `<label class="check inline"${f.title ? ` title="${esc(f.title)}"` : ""}><input type="checkbox" ${attr}="${f.k}"${v ? " checked" : ""}> ${esc(f.label)}</label>`;
  if (f.kind === "txt") return `<label class="cm-f cm-wide"${f.title ? ` title="${esc(f.title)}"` : ""}>${esc(f.label)}<input type="text" class="cm-name" ${attr}="${f.k}" value="${esc(v == null ? "" : v)}"></label>`;
  if (f.kind === "area") return `<label class="cm-f cm-wide"${f.title ? ` title="${esc(f.title)}"` : ""}>${esc(f.label)}<textarea ${attr}="${f.k}" rows="5">${esc(v == null ? "" : v)}</textarea></label>`;
  return `<label class="cm-f"${f.title ? ` title="${esc(f.title)}"` : ""}>${esc(f.label)}<input type="text" class="numf" ${attr}="${f.k}" value="${v === null || v === undefined ? "" : esc(fmt(v, 6))}"></label>`;
}
function fieldsHtml(fields, obj, attr) { return `<div class="cm-grid">${(fields || []).map(f => fieldHtml(f, obj, attr)).join("")}</div>`; }
function baseDone(o, ot) {
  const b = ot.base || {};
  if ((o.faces || []).length || (o.edges || []).length || (o.points || []).length >= (b.points || 99)) return true;
  if (ot.text && o.text && o.text.text) return true;
  if (ot.sketch && o.sketch && (o.sketch.name || o.sketch.feature)) return true;
  return !b.required;
}
function baseSummary(o) {
  const p = [];
  if ((o.faces || []).length) p.push(`${o.faces.length} face(s)`);
  if ((o.edges || []).length) p.push(`${o.edges.length} edge(s)`);
  if ((o.points || []).length) p.push(`${o.points.length} point(s)`);
  if (o.text && o.text.text) p.push(`text "${o.text.text}"`);
  if (o.sketch && (o.sketch.name || o.sketch.feature)) p.push(`sketch ${o.sketch.name || ((CM.geo && (CM.geo.part_sketches || []).find(x => x.id === o.sketch.feature)) || {}).name || o.sketch.feature}`);
  return p.join(", ");
}
function baseHtml(o, ot, c) {
  const b = ot.base || {};
  let h = "";
  if (b.faces || b.edges || b.points) {
    const modes = [];
    if (b.faces) modes.push(["faces", "Faces"]);
    if (b.edges) modes.push(["edges", "Edges"]);
    if (b.points) modes.push(["points", "Points"]);
    const cur = c.mode || modes[0][0];
    if (!c.mode) c.mode = cur;
    h += `<p class="hint cw-hint">${esc(b.hint || "Click the geometry in the view")}</p>`;
    if (modes.length > 1) h += `<div class="cw-modes">${modes.map(([v, l]) => `<label class="check"><input type="radio" name="cm-mode" value="${v}"${v === cur ? " checked" : ""}> ${l}</label>`).join("")}</div>`;
    const chips = [];
    (o.faces || []).forEach((f, i) => chips.push(`<span class="cw-chip" data-prop="faces" data-i="${i}" title="Face at (${f.c.map(q => fmt(q, 3)).join(", ")})">Face ${i + 1} · ${fmt(f.area, 3)} mm^2<button type="button" data-cwdel="faces:${i}" title="Remove">×</button></span>`));
    (o.edges || []).forEach((e, i) => chips.push(`<span class="cw-chip" data-prop="edges" data-i="${i}" title="Edge at (${e.mid.map(q => fmt(q, 3)).join(", ")})">Edge ${i + 1} · ${fmt(e.len, 3)} mm<button type="button" data-cwdel="edges:${i}" title="Remove">×</button></span>`));
    (o.points || []).forEach((p, i) => chips.push(`<span class="cw-chip" data-prop="points" data-i="${i}">P${i + 1} (${fmt(p[0], 4)}, ${fmt(p[1], 4)})<button type="button" data-cwdel="points:${i}" title="Remove">×</button></span>`));
    if (chips.length) h += `<div class="cw-chips">${chips.join("")}<button type="button" class="cw-clear small" data-cwclear="1">Clear</button></div>`;
    if (b.points) h += `<div class="cm-grid">${[0, 1].map(i => `<label class="cm-f">P${i + 1} X<input type="text" class="numf" data-pt="${i}:0" value="${o.points && o.points[i] ? fmt(o.points[i][0], 6) : ""}"></label><label class="cm-f">P${i + 1} Y<input type="text" class="numf" data-pt="${i}:1" value="${o.points && o.points[i] ? fmt(o.points[i][1], 6) : ""}"></label>`).join("")}</div>`;
  }
  if (ot.sketch) {
    const ps = (CM.geo && CM.geo.part_sketches) || [];
    h += `<div class="cm-grid"><label class="cm-f cm-wide" title="A saved sketch of the project (Sketch tab, XY plane of the job), or a sketch of the part on any plane that is horizontal after the model placement">Sketch<select data-sketch="1"><option value="">(none)</option>` +
      (CM.sketches.length ? `<optgroup label="Project sketches">${CM.sketches.map(n => `<option value="n:${esc(n)}"${o.sketch && o.sketch.name === n && !o.sketch.part ? " selected" : ""}>${esc(n)}</option>`).join("")}</optgroup>` : "") +
      (ps.length ? `<optgroup label="Sketches of the part">${ps.map(x => `<option value="p:${esc(x.id)}"${o.sketch && o.sketch.part && o.sketch.feature === x.id ? " selected" : ""}>${esc(x.name)} (${esc(x.plane)}${x.offset ? " " + fmt(x.offset) + " mm" : ""})</option>`).join("")}</optgroup>` : "") + `</select></label></div>`;
  }
  if (ot.text) h += `<div class="pt-sec">Text</div>` + fieldsHtml(TEXT_FIELDS, o.text || {}, "data-tk");
  return h;
}
function bindBase(box, o, ot, c) {
  box.querySelectorAll("input[name=cm-mode]").forEach(r => r.onchange = () => { c.mode = r.value; draw(); });
  box.querySelectorAll("[data-cwdel]").forEach(b => b.onclick = e => { e.stopPropagation(); const [prop, i] = b.dataset.cwdel.split(":"); CM.chipHover = null; o[prop].splice(+i, 1); changed(); renderCommand(true); drawSelection(); });
  box.querySelectorAll(".cw-chip").forEach(ch => {
    ch.onmouseenter = () => { CM.chipHover = (o[ch.dataset.prop] || [])[+ch.dataset.i] || null; drawSelection(); };
    ch.onmouseleave = () => { CM.chipHover = null; drawSelection(); };
  });
  box.querySelectorAll("[data-cwclear]").forEach(b => b.onclick = () => { for (const k of ["faces", "edges", "points"]) if (o[k]) o[k] = []; changed(); renderCommand(true); drawSelection(); });
  box.querySelectorAll("[data-pt]").forEach(inp => inp.onchange = () => {
    const [i, j] = inp.dataset.pt.split(":").map(Number), v = num(inp.value);
    if (!isFinite(v)) return;
    o.points = o.points || [];
    while (o.points.length <= i) o.points.push([0, 0]);
    if (o.points[i].length >= 3) o.points[i] = o.points[i].slice(0, 2);
    o.points[i][j] = v;
    changed(); drawSelection();
  });
  const sk = box.querySelector("[data-sketch]");
  if (sk) sk.onchange = () => {
    const v = sk.value;
    o.sketch = !v ? null : v.startsWith("p:") ? { part: CM.doc.source.name, feature: v.slice(2) } : { name: v.slice(2) };
    changed(); renderCommand(true);
  };
}
function depthsHtml(o, r) {
  const hv = r && r.heights;
  return `<div class="cm-grid">${DEPTH_FIELDS.map(([k, l, t]) => `<label class="cm-f" title="${esc(t)}">${esc(l)}<input type="text" class="numf" data-k="${k}" value="${o[k] === null || o[k] === undefined ? "" : esc(fmt(o[k], 6))}" placeholder="${hv ? esc(fmt(hv[{ start_depth: "start", final_depth: "final", step_down: "step", finish_depth: "finish" }[k]], 5)) : ""}"></label>`).join("")}</div>
    <p class="hint">Part coordinates; empty fields take the default (shown greyed after a preview).</p>`;
}
function heightsHtml(o, r) {
  const hv = r && r.heights;
  return `<div class="cm-grid">${HEIGHT_FIELDS.map(([k, l, t]) => `<label class="cm-f" title="${esc(t)}">${esc(l)}<input type="text" class="numf" data-k="${k}" value="${o[k] === null || o[k] === undefined ? "" : esc(fmt(o[k], 6))}" placeholder="${hv ? esc(fmt(hv[{ clearance_height: "clearance", safe_height: "safe" }[k]], 5)) : ""}"></label>`).join("")}</div>`;
}
function opHtml(o, ot) {
  let h = "";
  if (!ot.supplemental && !ot.derived) {
    h += `<div class="cm-grid">${selField("Tool controller", "tc", o.tc, tcChoices((CM.doc.tools || []).length ? [] : [["", "(none)"]]), (ot.tools ? "Tool shapes: " + ot.tools.join(", ") + ". " : "") + "+ New controller: a controller for a bit of the library, added to the job")}</div>`;
  }
  if (o.type === "fixture") h += `<div class="cm-grid">${fieldHtml(ot.fields[0], o)}${[0, 1, 2].map(i => `<label class="cm-f" title="Estlcam: the coordinates shifted">Shift ${"XYZ"[i]} (mm)<input type="text" class="numf" data-sk="${i}" value="${fmt((o.shift || [0, 0, 0])[i], 6)}"></label>`).join("")}</div>`;
  else h += fieldsHtml(ot.fields, o);
  if (!ot.supplemental && !ot.derived) {
    h += `<div class="pt-sec">Feeds</div><div class="cm-grid">${numField("Feed (mm/min)", "feed", o.feed, "Empty: the tool controller")}${numField("Plunge (mm/min)", "plunge", o.plunge, "Empty: the tool controller")}${numField("Ramp feed (mm/min)", "ramp_feed", o.ramp_feed, "Ramp and helix entries; empty: the tool controller")}${numField("Spindle (rpm)", "rpm", o.rpm, "Empty: the tool controller")}` +
      `<button type="button" class="small" id="cm-fs-op" title="Feed, plunge feed and spindle speed of this operation from the feeds and speeds calculator: the material of the stock, the tool bit, the step over (ae) and the step down (ap) of the operation">Calculate</button></div>`;
    const fo = CM.fsOp && CM.fsOp.id === o.id ? CM.fsOp.r : null;
    if (fo) h += `<p class="hint">ae ${fmt(fo.ae, 4)} mm, ap ${fmt(fo.ap, 4)} mm, chip load ${fmt(fo.fz_adj, 3)} mm/tooth, ${fmt(fo.power_kw, 3)} of ${fmt(fo.power_avail_kw, 3)} kW${fo.limited.length ? "; limited by " + fo.limited.join(", ") : ""}</p>` + fo.warnings.map(w => `<p class="hint err">${esc(w)}</p>`).join("");
  }
  if (!ot.supplemental) h += `<div class="cm-grid">${numField("Comment", "comment", o.comment || "", "Written in the G-code before the operation", "cm-name")}</div>`;
  return h;
}
const FINISH_MODES = [["off", "Off"], ["level", "In each level"], ["separate", "After roughing"]];
function finishSummary(o) {
  const m = o.finish_mode || "off";
  return m === "off" ? "off" : m === "level" ? "in each level" : `after roughing, ${o.finish_tc || o.tc || ""}`;
}
/** The Finish section: the mode, the stock left for it (a field of the type), and the properties of the finish passes. */
function finishHtml(o, ot) {
  const m = o.finish_mode || "off", lv = ot.finish.leave;
  let h = `<div class="cm-grid">${selField("Finish", "finish_mode", m, FINISH_MODES, "Off: the stock to leave stays. In each level: a finish pass after the roughing of every level. After the roughing: the roughing first, then the finish passes as their own toolpath")}` +
    `<label class="cm-f" title="The material the roughing leaves for the finish; set in the Operation section">Stock left (mm)<input type="text" class="numf" value="${fmt(o[lv[0]] || 0, 6)}" disabled></label></div>`;
  if (m === "off") return h + `<p class="hint">${esc(lv[1])} in the Operation section sets the material left.</p>`;
  if (m === "separate") {
    h += `<div class="cm-grid">${selField("Finish tool controller", "finish_tc", o.finish_tc || "", tcChoices([["", "(the operation's)"]]), ot.tools ? "Tool shapes: " + ot.tools.join(", ") : "")}` +
      `${numField("Finish step down (mm)", "finish_step", o.finish_step, "Empty: the step down of the operation")}</div>`;
  }
  h += `<div class="cm-grid">${numField("Finish feed (mm/min)", "finish_feed", o.finish_feed, m === "separate" ? "Empty: the operation's feed with the same tool, else the finish tool controller" : "Empty: the feed of the operation")}`;
  if (m === "separate") h += `${numField("Finish plunge (mm/min)", "finish_plunge", o.finish_plunge, "Empty: as the feed")}${numField("Finish spindle (rpm)", "finish_rpm", o.finish_rpm, "Empty: as the feed")}`;
  h += `${chkField("Spring pass", "finish_spring", o.finish_spring, "The last finish pass once more at the same offset")}` +
    `<button type="button" class="small" id="cm-fs-fin" title="The finish feeds from the feeds and speeds calculator: ae the stock left, ap the finish step down">Calculate</button></div>`;
  if (m === "level") h += `<p class="hint">The finish pass uses the tool and spindle speed of the operation.</p>`;
  return h;
}
async function applyFeedsFinish(o) {
  const ot = OPS[o.type] || {};
  if (!(CM.doc.stock || {}).material) { status("Set the material of the stock first", true); return; }
  const tcid = (o.finish_mode === "separate" && o.finish_tc) || o.tc;
  const tc = tcOf(tcid), b = tc && bitOf(tc.bit);
  if (!b) { status("No tool controller for the finish", true); return; }
  const leave = +o[ot.finish.leave[0]] || 0;
  const { ap } = opEngagement(Object.assign({}, o, { step_down: o.finish_step != null ? o.finish_step : o.step_down }), b);
  try {
    const r = await calcFeeds(tcid, Math.max(leave, 0.05 * b.d), ap);
    if (r.error) throw new Error(r.error);
    o.finish_feed = r.feed;
    if (o.finish_mode === "separate") { o.finish_plunge = r.plunge; o.finish_rpm = r.rpm; }
    changed(); renderCommand(true);
    status(`${o.name} finish: ae ${fmt(r.ae, 4)} mm, ap ${fmt(r.ap, 4)} mm: ${fmt(r.rpm, 5)} rpm, feed ${fmt(r.feed, 5)} mm/min`);
  } catch (e) { showErr(e); }
}
function placeCmdWin() {
  const w = $("#cm-cmdwin"), v = $("#cm-view");
  if (!w || !v) return;
  let pos = CM.cmdPos;
  if (!pos) { try { pos = JSON.parse(localStorage.getItem("cm-cmdwin-pos") || "null"); } catch (e) { pos = null; } }
  pos = pos || { x: 12, y: 12 };
  const maxX = Math.max(0, v.clientWidth - w.offsetWidth - 4), maxY = Math.max(0, v.clientHeight - 60);
  pos = { x: Math.min(Math.max(0, pos.x), maxX), y: Math.min(Math.max(0, pos.y), maxY) };
  CM.cmdPos = pos;
  w.style.left = pos.x + "px"; w.style.top = pos.y + "px";
}
function bindDrag(headId, winId, key, onMove) {
  const head = $(headId);
  head.addEventListener("mousedown", e => {
    if (e.button !== 0 || e.target.closest("button")) return;
    const w = $(winId), x0 = e.clientX, y0 = e.clientY, p0 = { x: w.offsetLeft, y: w.offsetTop };
    const move = ev => onMove({ x: p0.x + ev.clientX - x0, y: p0.y + ev.clientY - y0 });
    const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); try { localStorage.setItem(key, JSON.stringify({ x: $(winId).offsetLeft, y: $(winId).offsetTop })); } catch (err) { /* this session */ } };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
    e.preventDefault();
  });
}

// ------------------------------------------------------------------ simulate, sanity check, G-code, template

async function runOps() {
  if (!hasSource()) { status("Choose a part first", true); return; }
  if (CM.cmd) closeCommand(true);
  if (CM.previewTimer) { clearTimeout(CM.previewTimer); CM.previewTimer = null; }
  const seq = ++CM.previewSeq;
  busy(true, "Computing the toolpaths...");
  try {
    const r = await postJSON("/api/cam/run", { cam: CM.doc, meshes: true });
    const res = await r.json();
    if (seq === CM.previewSeq) {
      CM.res = res; CM.resUpto = null;
      const bad = res.operations.filter(o => !o.ok);
      const t = res.operations.reduce((s, o) => s + (o.time_s || 0), 0);
      status(bad.length ? `${bad.length} operation(s) failed: ${bad[0].errors[0]}` : `${res.operations.length} operation(s), ${fmt(t / 60, 3)} min; ${fmt(res.left_mm3, 5)} mm^3 left${res.gone_mm3 > 0.05 ? `, ${fmt(res.gone_mm3, 5)} mm^3 of the part cut` : ""}`, !!bad.length);
      showSanity(res.sanity, false);
    }
  } catch (e) { CM.res = null; showErr(e); }
  busy(false);
  renderAll(); initPlay(); draw();
}
function showSanity(list, always) {
  const bad = (list || []).filter(x => x.level !== "info");
  if (!bad.length && !always) return;
  const box = $("#cm-props");
  CM.sel = null; renderTree();
  box.innerHTML = `<div class="row"><strong>Sanity check</strong></div>` + (list || []).map(x => `<div class="${x.level === "error" ? "cm-err" : x.level === "warning" ? "cm-warn" : "hint"}">${x.level}: ${esc(x.text)}</div>`).join("");
}
async function sanityCheck() {
  try {
    const r = await (await postJSON("/api/cam/sanity", { cam: CM.doc })).json();
    showSanity(r, true);
  } catch (e) { showErr(e); }
}
async function writeGcode(download) {
  if (!hasSource()) { status("Choose a part first", true); return; }
  const folder = download ? "-" : ($("#cm-folder").value.trim() || (CM.doc.output || {}).folder || "");
  busy(true, "Writing the G-code...");
  try {
    let r = await fetch("/api/cam/gcode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cam: CM.doc, folder }) });
    if (r.status === 409) {
      const j = await r.json();
      if (!confirm(`${j.exists} exists. Overwrite?`)) { busy(false); return; }
      r = await fetch("/api/cam/gcode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cam: CM.doc, folder, overwrite: true }) });
    }
    if (!r.ok) throw new Error((await r.json()).error || r.statusText);
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("json")) {
      const j = await r.json();
      status(`Written ${j.written.join(", ")} (${j.lines} lines)`);
      if (window.projectRefreshDocs) window.projectRefreshDocs();
    } else {
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      const nm = (CM.doc.output || {}).name || CM.doc.name || "cam";
      a.download = nm.replace(/[^A-Za-z0-9_\-.]+/g, "_") + (/\.(nc|gcode|tap|ngc)$/i.test(nm) ? "" : ".nc");
      a.click();
      status("G-code downloaded");
    }
  } catch (e) { showErr(e); }
  busy(false);
}
/** G-code of the selected operation (or the whole job) in the G-code window. */
async function inspectGcode() {
  if (!hasSource()) { status("Choose a part first", true); return; }
  const id = CM.cmd ? CM.cmd.id : CM.sel;
  const i = id ? opIndex(id) : -1;
  busy(true, "G-code...");
  try {
    const r = await (await postJSON("/api/cam/gcode", { cam: CM.doc, inspect: i >= 0 ? i : null })).json();
    $("#cm-gcodewin-title").textContent = `G-code: ${i >= 0 ? opOf(id).name : CM.doc.name} (${r.lines} lines)`;
    $("#cm-gcodebody").textContent = r.text;
    $("#cm-gcodewin").hidden = false;
  } catch (e) { showErr(e); }
  busy(false);
}
async function exportTemplate() {
  try {
    const t = await (await postJSON("/api/cam/template", { cam: CM.doc })).json();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(t, null, 1)], { type: "application/json" }));
    a.download = (CM.doc.name || "cam") + ".camtemplate.json";
    a.click();
    status("Template downloaded");
  } catch (e) { showErr(e); }
}
async function importTemplate(file) {
  try {
    const tpl = JSON.parse(await file.text());
    if (!confirm("Replace the setup sheet, tool controllers, stock, post-processor and operations of this job with the template? The base geometry of the operations is empty afterwards.")) return;
    const d = await (await postJSON("/api/cam/template", { cam: CM.doc, apply: tpl })).json();
    if (CM.cmd) { CM.cmd = null; $("#cm-cmdwin").hidden = true; }
    d.name = CM.doc.name;
    CM.doc = d; CM.sel = null;
    changed(); renderAll(); draw();
    status("Template applied");
  } catch (e) { showErr(e); }
}

// ------------------------------------------------------------------ tool bit library

function renderBits() {
  const box = $("#cm-tools");
  if (box.hidden) return;
  if (CM.bitSel == null || CM.bitSel >= CM.bits.length) CM.bitSel = CM.bits.length ? 0 : null;
  const shapeName = v => (SHAPES.find(x => x[0] === v) || [v, v])[1];
  box.innerHTML = `<table class="fa-tbl cm-bitlist"><tr><th>Id</th><th>Name</th><th>Shape</th><th>D (mm)</th><th></th></tr>` +
    CM.bits.map((t, i) => `<tr data-bi="${i}" class="${i === CM.bitSel ? "sel" : ""}" title="Edit this bit"><td>${esc(t.id)}</td><td>${esc(t.name || "")}</td><td>${esc(shapeName(t.shape))}</td><td>${fmt(t.d)}</td>` +
      `<td class="cm-bitbtns"><button type="button" class="small" data-tdup="${i}" title="Copy of the bit">Copy</button><button type="button" class="small" data-tdel="${i}" title="Delete the bit">×</button></td></tr>`).join("") + `</table>
    <div class="row"><button type="button" id="cm-tool-add" class="small">New bit</button><button type="button" id="cm-lib-toggle" class="small" title="The standard metric tool library: flat, ball, single flute, chamfer, tapered ball nose and spoilboard surfacing tools">Library…</button><button type="button" id="cm-tool-save" class="small primary" title="Save the tool bit library (config.json)">Save bits</button></div>
    ${libraryHtml()}
    <div id="cm-bited">${CM.bitSel != null ? bitEditorHtml(CM.bits[CM.bitSel]) : ""}</div>`;
  box.querySelectorAll("tr[data-bi]").forEach(tr => tr.onclick = e => { if (e.target.closest("button")) return; CM.bitSel = +tr.dataset.bi; renderBits(); });
  box.querySelectorAll("button[data-tdel]").forEach(b => b.onclick = () => { CM.bits.splice(+b.dataset.tdel, 1); if (CM.bitSel >= CM.bits.length) CM.bitSel = CM.bits.length - 1; renderBits(); });
  box.querySelectorAll("button[data-tdup]").forEach(b => b.onclick = () => {
    const t = JSON.parse(JSON.stringify(CM.bits[+b.dataset.tdup]));
    t.id = newBitId(); t.name = (t.name || "") + " copy";
    CM.bits.push(t); CM.bitSel = CM.bits.length - 1; renderBits();
  });
  bindLibrary(box);
  $("#cm-tool-add").onclick = () => {
    CM.bits.push({ id: newBitId(), name: "", shape: "endmill", d: 6, height: 18, neck: null, neck_length: 0, shank: 6, shank_length: 30, flutes: 2, tool_material: "carbide", feed: 800, plunge: 200, rpm: 12000 });
    CM.bitSel = CM.bits.length - 1;
    renderBits();
  };
  $("#cm-tool-save").onclick = async () => {
    try {
      const r = await api("/api/cam/tools", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(CM.bits) });
      CM.bits = await r.json();
      status("Tool bit library saved");
      renderAll();
      schedulePreview(0);
    } catch (e) { showErr(e); }
  };
  if (CM.bitSel != null) bindBitEditor($("#cm-bited"), CM.bits[CM.bitSel]);
}
function newBitId() {
  let n = CM.bits.length + 1;
  while (CM.bits.some(t => t.id === "T" + n)) n++;
  return "T" + n;
}
/** The editor of one bit: Id, Name, Shape, the geometry fields of the shape (a custom profile: its points), neck and
 *  shank, flutes, material, coating, the feeds; a drawing of the profile. */
function bitEditorHtml(t) {
  const sh = t.shape || "endmill";
  const f = ([k, l, h]) => numField(l, k, t[k], h || "");
  let h = `<div class="cm-bited"><div class="pt-sec">Bit ${esc(t.id)}</div><div class="cm-bited-grid"><div class="cm-bited-fields">
    <div class="row">${numField("Id", "id", t.id, "", "cm-name")}${numField("Name", "name", t.name || "", "", "cm-name")}</div>
    <div class="row">${selField("Shape", "shape", sh, SHAPES)}</div>`;
  if (sh === "custom") {
    const pts = t.profile && t.profile.length ? t.profile : [[0, 0], [3, 0], [3, 10]];
    t.profile = pts;
    h += `<div class="hint">The cutting edge from the tip up: radius r and height z (mm); z starts at 0 and never goes down. D and the cutting height are taken from the points.</div>
      <table class="fa-tbl cm-prof"><tr><th>#</th><th>r (mm)</th><th>z (mm)</th><th></th></tr>${pts.map((p, i) => `<tr><td>${i + 1}</td><td><input type="text" class="numf" data-pr="${i}" data-pc="0" value="${fmt(p[0], 6)}"></td><td><input type="text" class="numf" data-pr="${i}" data-pc="1" value="${fmt(p[1], 6)}"></td><td><button type="button" class="small" data-pdel="${i}" title="Delete the point">×</button></td></tr>`).join("")}</table>
      <div class="row"><button type="button" class="small" id="cm-padd">Add point</button></div>`;
  } else h += `<div class="cm-grid">${(BIT_GEOM[sh] || []).map(f).join("")}${sh === "tapered" ? `<label class="cm-f" title="From the tip radius, the taper and the cutting height">Diameter D (mm)<input type="text" class="numf" value="${fmt(t.d)}" disabled></label>` : ""}</div>`;
  h += `<div class="cm-grid">${BIT_BODY.map(f).join("")}</div>
    <div class="cm-grid">${numField("Flutes", "flutes", t.flutes)}${selField("Tool material", "tool_material", t.tool_material || "carbide", TOOL_MATS)}${selField("Coating", "coating", t.coating || "none", COATINGS)}</div>
    <div class="cm-grid">${numField("Feed (mm/min)", "feed", t.feed, "Default of a tool controller made from the bit")}${numField("Plunge (mm/min)", "plunge", t.plunge)}${numField("Spindle (rpm)", "rpm", t.rpm)}</div>
    </div><div class="cm-bited-draw"><svg id="cm-bit-svg" viewBox="0 0 160 240" width="160" height="240"></svg><div class="hint" id="cm-bit-info"></div></div></div>
    <p class="hint">Changes apply to this session; Save bits keeps them.</p></div>`;
  return h;
}
function bindBitEditor(el, t) {
  if (!el || !t) return;
  el.querySelectorAll("[data-k]").forEach(inp => inp.onchange = () => {
    const k = inp.dataset.k;
    if (k === "id" || k === "name" || k === "shape" || k === "tool_material" || k === "coating") {
      const v = inp.value.trim();
      if (k === "id" && (!v || CM.bits.some(b => b !== t && b.id === v))) { status(v ? `The id ${v} is used by another bit` : "A bit needs an id", true); inp.value = t.id; return; }
      t[k] = v;
    } else if (inp.value.trim() === "") t[k] = null;
    else { const v = num(inp.value); if (!isFinite(v)) { inp.value = t[k] == null ? "" : fmt(t[k], 6); return; } t[k] = v; }
    renderBits();
  });
  el.querySelectorAll("[data-pr]").forEach(inp => inp.onchange = () => {
    const v = num(inp.value);
    if (!isFinite(v)) { inp.value = fmt(t.profile[+inp.dataset.pr][+inp.dataset.pc], 6); return; }
    t.profile[+inp.dataset.pr][+inp.dataset.pc] = v;
    renderBits();
  });
  el.querySelectorAll("[data-pdel]").forEach(b => b.onclick = () => { if (t.profile.length > 2) { t.profile.splice(+b.dataset.pdel, 1); renderBits(); } });
  const pa = el.querySelector("#cm-padd");
  if (pa) pa.onclick = () => { const l = t.profile[t.profile.length - 1]; t.profile.push([l[0], l[1] + 2]); renderBits(); };
  drawBitProfile(t);
}
/** The tool outline from the server profile: the cutting part orange, the neck and shank grey, with D, the cutting
 *  height and the length. */
async function drawBitProfile(t) {
  const seq = (CM.bitDrawSeq = (CM.bitDrawSeq || 0) + 1);
  let pr;
  try { pr = await (await postJSON("/api/cam/tool_profile", { bit: t })).json(); } catch (e) { pr = { error: e.message || String(e) }; }
  if (seq !== CM.bitDrawSeq) return;
  const svg = $("#cm-bit-svg"), info = $("#cm-bit-info");
  if (!svg) return;
  if (pr.error) { svg.innerHTML = ""; info.innerHTML = `<span class="cm-err">${esc(pr.error)}</span>`; return; }
  if (t.shape === "custom" || t.shape === "tapered") { if (Math.abs((t.d || 0) - pr.d) > 1e-6) { t.d = pr.d; const r = $("#cm-tools tr[data-bi].sel td:nth-child(4)"); if (r) r.textContent = fmt(t.d); } }
  const all = pr.cut.concat(pr.body), W = 160, H = 240, m = 12;
  const rmax = Math.max(...all.map(p => p[0]), 0.1), zmax = Math.max(...all.map(p => p[1]), 0.1);
  const k = Math.min((W - 2 * m) / (2 * rmax), (H - 2 * m) / zmax);
  const X = r => W / 2 + r * k, Y = z => H - m - z * k;
  const outline = pts => pts.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).concat(pts.slice().reverse().map(p => `${X(-p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`)).join(" ");
  const body = [[0, pr.body[0][1]]].concat(pr.body).concat([[0, pr.body[pr.body.length - 1][1]]]);
  const cut = pr.cut.concat([[0, pr.cut[pr.cut.length - 1][1]]]);
  svg.innerHTML = `<polygon points="${outline(body)}" fill="#adb5bd" stroke="#495057" stroke-width="1"/><polygon points="${outline(cut)}" fill="#f08c00" stroke="#7a4300" stroke-width="1"/>` +
    `<line x1="${W / 2}" y1="${m / 2}" x2="${W / 2}" y2="${H - m / 2}" stroke="#868e96" stroke-dasharray="4 3" stroke-width="0.8"/>`;
  info.textContent = `D ${fmt(pr.d, 5)} mm, cutting height ${fmt(pr.height, 5)} mm, length ${fmt(pr.length, 5)} mm`;
}
/** The standard library picker in the bit library: a group, its tools with checkboxes, Add selected. */
function libraryHtml() {
  if (!CM.libOpen) return "";
  const lib = CM.library || [];
  const groups = [...new Set(lib.map(t => t.group))];
  const g = CM.libGroup && groups.includes(CM.libGroup) ? CM.libGroup : groups[0];
  const have = new Set(CM.bits.map(b => b.id));
  return `<div class="cm-lib"><div class="row"><label class="cm-f">Library group<select id="cm-lib-group">${groups.map(x => `<option${x === g ? " selected" : ""}>${esc(x)}</option>`).join("")}</select></label>
    <button type="button" class="small" id="cm-lib-all">Select all</button><button type="button" class="small primary" id="cm-lib-add">Add selected</button></div>
    <div class="cm-lib-list">${lib.filter(t => t.group === g).map(t => `<label class="check inline" title="${esc(`${t.id}: D ${fmt(t.d, 4)} mm, ${t.flutes} flutes, cutting height ${fmt(t.height, 4)} mm, shank ${fmt(t.shank)} mm`)}"><input type="checkbox" data-lib="${esc(t.id)}"${have.has(t.id) ? " disabled" : ""}> ${esc(t.name)}${have.has(t.id) ? " (in the table)" : ""}</label>`).join("")}</div></div>`;
}
function bindLibrary(box) {
  const tg = box.querySelector("#cm-lib-toggle");
  tg.onclick = async () => {
    CM.libOpen = !CM.libOpen;
    if (CM.libOpen && !CM.library) { try { CM.library = await (await api("/api/cam/library")).json(); } catch (e) { CM.library = []; showErr(e); } }
    renderBits();
  };
  if (!CM.libOpen) return;
  const gs = box.querySelector("#cm-lib-group");
  gs.onchange = () => { CM.libGroup = gs.value; renderBits(); };
  box.querySelector("#cm-lib-all").onclick = () => box.querySelectorAll("[data-lib]:not(:disabled)").forEach(c => { c.checked = true; });
  box.querySelector("#cm-lib-add").onclick = () => {
    const ids = [...box.querySelectorAll("[data-lib]:checked")].map(c => c.dataset.lib);
    for (const id of ids) {
      const t = Object.assign({}, CM.library.find(x => x.id === id));
      delete t.group;
      CM.bits.push(t);
    }
    status(ids.length ? `${ids.length} bit(s) added; Save bits keeps them` : "No bit selected", !ids.length);
    renderBits();
  };
}
function bindToolsFold() {
  const h = $("#cm-tools-toggle"), box = $("#cm-tools");
  let open = false;
  try { open = localStorage.getItem("cm-tools-open") === "1"; } catch (e) { /* folded */ }
  const show = () => { box.hidden = !open; h.querySelector(".fold").textContent = open ? "▾" : "▸"; if (open) renderBits(); };
  h.onclick = () => { open = !open; try { localStorage.setItem("cm-tools-open", open ? "1" : "0"); } catch (e) { /* this session */ } show(); };
  show();
}

// ------------------------------------------------------------------ documents

let FM = null;
function refreshList() { if (FM) FM.refresh(); refreshSources(); }
async function refreshSources() {
  let parts = [];
  try { parts = await (await api("/api/part/list")).json(); } catch (e) { /* none */ }
  try { CM.sketches = await (await api("/api/sketch/list")).json(); } catch (e) { CM.sketches = []; }
  const s = CM.doc ? CM.doc.source || {} : {};
  $("#cm-source").innerHTML = `<option value="">(choose a part)</option>` + parts.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  if (s.name && !parts.includes(s.name)) $("#cm-source").insertAdjacentHTML("beforeend", `<option value="${esc(s.name)}">${esc(s.name)} (missing)</option>`);
  $("#cm-source").value = s.name || "";
}
async function loadMeta() {
  try { CM.machine = await (await api("/api/cam/machine")).json(); } catch (e) { CM.machine = null; }
  try { CM.bits = await (await api("/api/cam/tools")).json(); } catch (e) { CM.bits = []; }
  try { CM.meta = await (await api("/api/cam/meta")).json(); CM.posts = CM.meta.posts; } catch (e) { CM.meta = null; CM.posts = []; }
}
function renderPost() {
  const sel = $("#cm-post"), cur = (CM.doc && CM.doc.post) || "estlcam";
  sel.innerHTML = CM.posts.map(p => `<option value="${esc(p.id)}"${p.id === cur ? " selected" : ""}>${esc(p.name)}</option>`).join("");
  $("#cm-outname").value = (CM.doc && CM.doc.output && CM.doc.output.name) || "";
  $("#cm-folder").value = (CM.doc && CM.doc.output && CM.doc.output.folder) || "";
}
async function loadDoc(d) {
  const b = blankDoc(d.name);
  for (const k of Object.keys(b)) if (d[k] === undefined) d[k] = b[k];
  if (CM.cmd) { CM.cmd = null; $("#cm-cmdwin").hidden = true; }
  CM.doc = d;
  CM.sel = null; CM.res = null; CM.hidden = {}; CM.placeRes = null;
  CM.dirty = false;
  if (CM.three) CM.three.zoomed = false;
  if (FM) FM.render();
  await refreshSources();
  renderAll();
  await loadGeometry();
}
async function saveDoc(name) {
  CM.doc.name = name;
  const r = await api("/api/cam/file/" + encodeURIComponent(name), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(CM.doc) });
  const j = await r.json();
  CM.dirty = false;
  status("Saved " + j.path);
}

window.camShown = async function () {
  if (!CM.three) { initThree(); try { const f = JSON.parse(localStorage.getItem("cm-fold") || "null"); if (f) CM.fold = f; } catch (e) { /* folded as default */ } }
  if (!CM.meta) await loadMeta();
  if (!CM.doc) await loadDoc(blankDoc("cam"));
  refreshList();
  renderAll();
  setTimeout(resize3, 0);
  checkPart();
};

(function bindCam() {
  document.addEventListener("keydown", e => {
    if ($("#tab-cam").hidden) return;
    if (e.key === "Escape") {
      if (!$("#cm-gcodewin").hidden) { $("#cm-gcodewin").hidden = true; return; }
      if (CM.measure) { setMeasure(false); return; }
      if (CM.zeroPick) { endZeroPick(); status("Machine zero pick cancelled"); return; }
      if (CM.cmd && CM.cmd.place && CM.cmd.pick) { CM.cmd.pick = null; renderCommand(true); draw(); return; }
      if (CM.cmd) closeCommand(true);
    }
  });
  $("#cm-source").onchange = () => {
    CM.doc.source = { type: "part", name: $("#cm-source").value };
    changed(false); loadGeometry();
  };
  document.querySelectorAll("#tab-cam [data-addop]").forEach(b => b.onclick = () => addOp(b.dataset.addop));
  document.querySelectorAll("#tab-cam [data-adddr]").forEach(b => b.onclick = () => addDressup(b.dataset.adddr));
  $("#cm-run").onclick = runOps;
  $("#cm-sanity").onclick = sanityCheck;
  $("#cm-post").onchange = () => { CM.doc.post = $("#cm-post").value; changed(false); renderTree(); };
  $("#cm-outname").onchange = () => { (CM.doc.output = CM.doc.output || {}).name = $("#cm-outname").value.trim(); changed(false); };
  $("#cm-folder").onchange = () => { (CM.doc.output = CM.doc.output || {}).folder = $("#cm-folder").value.trim(); changed(false); };
  $("#cm-gcode").onclick = () => writeGcode(false);
  $("#cm-gcode-dl").onclick = () => writeGcode(true);
  $("#cm-inspect").onclick = inspectGcode;
  $("#cm-inspect-tb").onclick = inspectGcode;
  $("#cm-place").onclick = openPlacement;
  $("#cm-zero").onclick = () => (CM.zeroPick ? endZeroPick() : startZeroPick());
  $("#cm-measure-btn").onclick = () => { if (!CM.measure && !hasSource()) { status("Choose a part first", true); return; } setMeasure(!CM.measure); };
  $("#cm-measure-close").onclick = () => setMeasure(false);
  document.querySelectorAll("#cm-measure [data-mref]").forEach(b => b.onclick = () => addMeasureItem({ ref: b.dataset.mref }));
  $("#cm-refresh").onclick = refreshPart;
  $("#cm-play-slider").oninput = () => { if (CM.play) { CM.play.running = false; $("#cm-play-btn").textContent = "▶"; playAt(+$("#cm-play-slider").value / 1000); } };
  $("#cm-play-btn").onclick = () => {
    const P = CM.play;
    if (!P) return;
    P.running = !P.running;
    $("#cm-play-btn").textContent = P.running ? "❚❚" : "▶";
    if (P.running) { if (P.frac >= 1) P.frac = 0; P.last = null; requestAnimationFrame(playStep); }
  };
  window.addEventListener("focus", checkPart);
  setInterval(checkPart, 4000);
  $("#cm-tpl-export").onclick = exportTemplate;
  $("#cm-tpl-import").onclick = () => $("#cm-tpl-file").click();
  $("#cm-tpl-file").onchange = () => { const f = $("#cm-tpl-file").files[0]; if (f) importTemplate(f); $("#cm-tpl-file").value = ""; };
  $("#cm-cmdwin-x").onclick = () => closeCommand(true);
  $("#cm-gcodewin-x").onclick = () => { $("#cm-gcodewin").hidden = true; };
  bindDrag("#cm-cmdwin-head", "#cm-cmdwin", "cm-cmdwin-pos", p => { CM.cmdPos = p; placeCmdWin(); });
  bindDrag("#cm-gcodewin-head", "#cm-gcodewin", "cm-gcodewin-pos", p => { const w = $("#cm-gcodewin"); w.style.left = Math.max(0, p.x) + "px"; w.style.top = Math.max(0, p.y) + "px"; });
  document.querySelectorAll("#tab-cam [data-cmview]").forEach(b => b.onclick = () => view(b.dataset.cmview));
  for (const id of ["#cm-showmachine", "#cm-edges", "#cm-axes", "#cm-showpart", "#cm-showstock", "#cm-showleft", "#cm-showpath", "#cm-showrapid", "#cm-showunder", "#cm-showhm"]) $(id).onchange = draw;
  bindToolsFold();
  FM = docFileMenu({ pre: "cm", type: "cam", label: "CAM job", pane: "#tab-cam", listUrl: "/api/cam/list",
    cur: () => (CM.doc ? { name: CM.doc.name, dirty: !!CM.dirty } : null),
    load: async name => loadDoc(await (await api("/api/cam/file/" + encodeURIComponent(name))).json()),
    save: saveDoc, blank: () => loadDoc(blankDoc("cam")), setName: name => { CM.doc.name = name; },
    folderHint: d => d.cam ? "empty: " + d.cam : "empty: download" });
  $("#cm-openstep").onclick = () => postJSON("/api/cam/open_folder", {}).catch(showErr);
  window.addEventListener("beforeunload", e => { if (CM.dirty) { e.preventDefault(); e.returnValue = ""; } });
})();

window.__cam = { CM, focusPoint, setMeasure, addMeasureItem, measureAt, travelCheck, playAt, machineOffset, checkPart, refreshPart, openCommand, closeCommand, addOp, addDressup, runOps, openPlacement, placePick, solvePlacement, setPlacement, applyFeedsAll, applyFeedsOp, opEngagement };
window.__camLoadNamed = async function (name) { await loadDoc(await (await api("/api/cam/file/" + encodeURIComponent(name))).json()); if (FM) FM.markSaved(name); };
window.__camSetName = name => { if (CM.doc) { CM.doc.name = name; if (FM) FM.markSaved(name); } };
window.__camRefresh = refreshList;
window.__camCurrent = () => (CM.doc ? { name: CM.doc.name, dirty: !!CM.dirty } : null);
