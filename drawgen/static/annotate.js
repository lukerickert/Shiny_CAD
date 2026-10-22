"use strict";
// Interactive dimensions and notes on a previewed drawing.
// Annotation coordinates are stored in view coordinates (model mm) of the picked view,
// so they follow the view when the sheet, scale or layout changes.

const ED = {
  d: null,            // current drawing (preview record)
  anns: [],
  sel: null,          // selected annotation id
  tool: "select",
  pick: [],           // picks of the current tool: {view, x, y} or {view, c, r}
  hist: [],
  vb: null,           // current viewBox [x, y, w, h]
  snapPts: [],        // [{X, Y, view, x, y, kind}]
  circles: [],        // [{X, Y, R, view, c:[x,y], r}]
  lines: [],          // straight edges [{A:[X,Y], B:[X,Y], view, seg:[x1,y1,x2,y2]}] (angle dimensions)
  drag: null,
  pan: null,
  mouse: null,
  busy: false,
};
const SVGNS = "http://www.w3.org/2000/svg";
// default: letters (e.key); left-handed: physical keys on the right side of the keyboard (e.code)
const TOOL_KEYS = { s: "select", h: "h", v: "v", a: "a", g: "angle", d: "diameter", r: "radius", n: "note", l: "leader", b: "balloon", e: "detail", k: "sketch" };
const TOOL_CODES_LEFT = { KeyJ: "select", KeyH: "h", KeyI: "v", Slash: "a", Semicolon: "angle", KeyO: "diameter", KeyU: "radius", KeyN: "note",
                          KeyL: "leader", KeyK: "balloon", KeyY: "detail", KeyP: "sketch" };
const FIT_KEY = { default: "f", left: "KeyM" };
const TOOL_NAMES = { select: "Select", h: "Horizontal dimension", v: "Vertical dimension", a: "Aligned dimension", angle: "Angle dimension", diameter: "Diameter",
                     radius: "Radius", note: "Note", leader: "Note with leader", balloon: "Item balloon", detail: "Detail view",
                     sketch: "Sketch on a view or on the sheet" };
function annToolKey(tool) {
  if (leftKeys()) { const c = Object.keys(TOOL_CODES_LEFT).find(k => TOOL_CODES_LEFT[k] === tool); return c ? codeLabel(c) : ""; }
  const k = Object.keys(TOOL_KEYS).find(x => TOOL_KEYS[x] === tool);
  return k ? k.toUpperCase() : "";
}
function annFitKey() { return leftKeys() ? codeLabel(FIT_KEY.left) : "F"; }
function annKeyTitles() {
  document.querySelectorAll("#ann-tools button[data-tool]").forEach(b => setKeyTitle(b, annToolKey(b.dataset.tool)));
  setKeyTitle($("#ann-fitview"), annFitKey());
}
window.SHORTCUTS.push({ tab: "Drawings", rows: () =>
  Object.keys(TOOL_NAMES).map(t => [annToolKey(t), TOOL_NAMES[t]]).concat([[annFitKey(), "Fit sheet"], ["Ctrl+Z", "Undo"], ["Delete", "Delete selection"], ["Esc", "Cancel / deselect"]]) });
const HINTS = {
  sketch: "Sketch: click a view to sketch on it (view coordinates in mm, the sketch moves with the view), or the sheet outside the views (sheet coordinates in mm).",
  select: "Drag a view to move it. Drag a dimension or note to move it, click it to edit. Shift+drag or middle button pans, wheel zooms.",
  h: ["Horizontal: pick the first point.", "Pick the second point.", "Click to place the dimension line."],
  v: ["Vertical: pick the first point.", "Pick the second point.", "Click to place the dimension line."],
  a: ["Aligned: pick the first point.", "Pick the second point.", "Click to place the dimension line."],
  angle: ["Angle: pick the first line (a straight edge of a view).", "Pick the second line.",
          "Click to place the dimension arc (the side of the vertex chooses the angle)."],
  diameter: ["Diameter: pick a circle or arc, or the first edge point of a shaft or bore (side view).",
             "Pick the opposite edge point.", "Click to place the dimension line."],
  radius: ["Radius: pick an arc or circle.", "Click to place the text."],
  note: ["Note: click the text position."],
  leader: ["Leader note: pick the point the arrow points to.", "Click the text position."],
  balloon: ["Balloon: pick the point on the part.", "Click the balloon position."],
  detail: ["Detail view: click the centre of the detail on a view.", "Click a point on the detail circle."],
};

// ------------------------------------------------------------------ geometry helpers

function mapOf(view) { return ED.d.maps[view]; }
function toSheet(view, x, y) {
  if (!view) return [x, y];
  const m = mapOf(view);
  return [m[0] + m[2] * (x - m[3]), m[1] + m[2] * (y - m[4])];
}
function toModel(view, X, Y) {
  if (!view) return [X, Y];
  const m = mapOf(view);
  return [m[3] + (X - m[0]) / m[2], m[4] + (Y - m[1]) / m[2]];
}
function viewAt(X, Y) {
  for (const [n, m] of Object.entries(ED.d.maps)) {
    if (n === "iso") continue;
    if (X >= m[5] - 2 && X <= m[7] + 2 && Y >= m[6] - 2 && Y <= m[8] + 2) return n;
  }
  return null;
}
function svgEl() { return $("#ann-canvas svg"); }
function eventSheet(e) {
  const svg = svgEl();
  const pt = svg.createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  return [p.x, ED.d.size[1] - p.y];
}
function tolMM() {
  const svg = svgEl();
  return 10 * ED.vb[2] / Math.max(svg.clientWidth, 1);
}
function nearestPoint(X, Y, view) {
  let best = null, bd = tolMM();
  for (const p of ED.snapPts) {
    if (view && p.view !== view) continue;
    const d = Math.hypot(p.X - X, p.Y - Y);
    if (d < bd) { bd = d; best = p; }
  }
  return best;
}
function nearestCircle(X, Y) {
  let best = null, bd = tolMM();
  for (const c of ED.circles) {
    const dc = Math.hypot(c.X - X, c.Y - Y);
    const d = Math.min(Math.abs(dc - c.R), dc);
    if (d < bd) { bd = d; best = c; }
  }
  return best;
}
/** The straight edge nearest to (X, Y) within the pick tolerance (in view, when given). */
function nearestLine(X, Y, view) {
  let best = null, bd = tolMM();
  for (const l of ED.lines) {
    if (view && l.view !== view) continue;
    const [ax, ay] = l.A, [bx, by] = l.B, dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
    const t = Math.max(0, Math.min(1, ((X - ax) * dx + (Y - ay) * dy) / (L2 || 1)));
    const d = Math.hypot(ax + dx * t - X, ay + dy * t - Y);
    if (d < bd) { bd = d; best = l; }
  }
  return best;
}
/** Angle dimension from two picked lines (view coordinates): vertex at the intersection, a point on each line
 *  (the end farther from the vertex); null for parallel lines. */
function angleFromLines(l1, l2) {
  const [a, b, c, d] = l1.seg, [e, f, g, h] = l2.seg;
  const d1 = [c - a, d - b], d2 = [g - e, h - f];
  const den = d1[0] * d2[1] - d1[1] * d2[0];
  if (Math.abs(den) < 1e-9 * Math.hypot(...d1) * Math.hypot(...d2)) return null;
  const t = ((e - a) * d2[1] - (f - b) * d2[0]) / den;
  const C = [a + d1[0] * t, b + d1[1] * t];
  const far = (p, q) => (Math.hypot(p[0] - C[0], p[1] - C[1]) >= Math.hypot(q[0] - C[0], q[1] - C[1]) ? p : q);
  return { c: C, p1: far([a, b], [c, d]), p2: far([e, f], [g, h]) };
}
/** Angle (deg) of the sector between the lines c-p1 and c-p2 that holds q (annotate.angle_sector). */
function angleValue(c, p1, p2, q) {
  const tw = 2 * Math.PI, at = (p) => Math.atan2(p[1] - c[1], p[0] - c[0]);
  const t1 = at(p1), t2 = at(p2), tq = at(q);
  let best = null;
  for (const A of [t1, t1 + Math.PI]) for (const B of [t2, t2 + Math.PI]) for (const [s0, s1] of [[A, B], [B, A]]) {
    const span = ((s1 - s0) % tw + tw) % tw;
    if (span < 1e-9 || span > Math.PI + 1e-9) continue;
    if (((tq - s0) % tw + tw) % tw <= span + 1e-9 && (best === null || span < best)) best = span;
  }
  return (best === null ? ((t2 - t1) % tw + tw) % tw : best) * 180 / Math.PI;
}

function diaOrient() {
  // diameter between two edge points: measured across the larger coordinate difference
  const a = ED.pick[0], b = ED.pick[1];
  if (!a || !b) return "v";
  return Math.abs(b.y - a.y) >= Math.abs(b.x - a.x) ? "v" : "h";
}
function uid() { return "a" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
function fmtNum(v) { return (+v.toFixed(3)).toString(); }

// deviations are stored in mm and entered in µm (inch with the inch option, app.js devToField / devFromField)
function devUm(v) { return devToField(v); }
function devMm(s) { return devFromField(s); }

function measured(a) {
  if (a.type === "linear") {
    const dx = a.p2[0] - a.p1[0], dy = a.p2[1] - a.p1[1];
    return a.orient === "h" ? Math.abs(dx) : a.orient === "v" ? Math.abs(dy) : Math.hypot(dx, dy);
  }
  if (a.type === "diameter") return 2 * a.r;
  if (a.type === "radius") return a.r;
  if (a.type === "angle") return angleValue(a.c, a.p1, a.p2, a.pos);
  return null;
}

// ------------------------------------------------------------------ drawing list

function annotatorDrawingsChanged() {
  const sel = $("#ann-drawing");
  const cur = ED.d ? ED.d.name : sel.value;
  sel.innerHTML = "";
  (state.drawings || []).forEach(d => sel.add(new Option(`${d.name}  (${d.sheet}, ${d.scale})`, d.name)));
  if (cur && (state.drawings || []).some(d => d.name === cur)) {
    sel.value = cur;
    loadDrawing(state.drawings.find(d => d.name === cur), true);
  } else if (state.drawings && state.drawings.length) {
    loadDrawing(state.drawings[0], false);
  }
}
window.annotatorDrawingsChanged = annotatorDrawingsChanged;

function annotatorShown() {
  if (ED.d && !ED.vb) fitView();
  drawCanvas(true);
}
window.annotatorShown = annotatorShown;

/** Parts list check box of an assembly drawing (layout "parts_list"). */
function renderPlist() {
  const box = $("#ann-plist-box");
  if (!box) return;
  box.hidden = !(ED.d && ED.d.has_parts_list);
  if (ED.d) $("#ann-plist").checked = !!ED.d.parts_list_shown;
}

function loadDrawing(d, keepView) {
  const same = ED.d && ED.d.name === d.name && ED.d.sheet === d.sheet;
  ED.d = d;
  ED.anns = JSON.parse(JSON.stringify(d.annotations || []));
  if (!keepView || !same) { ED.vb = null; ED.hist = []; ED.sel = null; }
  ED.pick = [];
  buildSnaps();
  renderPlist();
  drawCanvas(keepView && same);
  annShowProps();
  renderViewToggles();
  renderDetails();
  renderSketches();
}

function buildSnaps() {
  ED.snapPts = []; ED.circles = []; ED.lines = [];
  for (const [view, s] of Object.entries(ED.d.snaps || {})) {
    for (const p of s.points) {
      const [X, Y] = toSheet(view, p[0], p[1]);
      ED.snapPts.push({ X, Y, view, x: p[0], y: p[1], kind: p[2] });
    }
    const f = mapOf(view)[2];
    for (const c of s.circles) {
      const [X, Y] = toSheet(view, c[0], c[1]);
      ED.circles.push({ X, Y, R: c[2] * f, view, c: [c[0], c[1]], r: c[2], kind: c[3] });
    }
    for (const q of s.lines || []) ED.lines.push({ A: toSheet(view, q[0], q[1]), B: toSheet(view, q[2], q[3]), view, seg: q });
  }
}

// ------------------------------------------------------------------ canvas

function drawCanvas(keepVB) {
  const box = $("#ann-canvas");
  if (!ED.d) return;
  box.innerHTML = ED.d.svg;
  const svg = svgEl();
  svg.removeAttribute("width"); svg.removeAttribute("height");
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  if (!ED.vb) fitView(); else svg.setAttribute("viewBox", ED.vb.join(" "));
  const ov = document.createElementNS(SVGNS, "g");
  ov.setAttribute("id", "ann-overlay");
  ov.setAttribute("pointer-events", "none");
  svg.appendChild(ov);
  thinLines(svg);
  svg.querySelectorAll("g.ann").forEach(g => g.classList.toggle("sel", g.dataset.ann === ED.sel));
  svg.addEventListener("mousedown", onDown);
  svg.addEventListener("mousemove", onMove);
  svg.addEventListener("mouseup", onUp);
  svg.addEventListener("wheel", onWheel, { passive: false });
  svg.addEventListener("dblclick", e => e.preventDefault());
  box.classList.toggle("select", ED.tool === "select");
  updateHint();
}

// Editor display: line widths in screen pixels independent of zoom (vector-effect non-scaling-stroke)
function thinLines(svg) {
  const px = mm => Math.max(0.6, 0.4 + mm * 1.6);
  svg.querySelectorAll("[stroke-width]").forEach(el => {
    if (el.closest("#ann-overlay")) return;
    const mm = parseFloat(el.getAttribute("stroke-width")) || 0.25;
    if (el.getAttribute("stroke") === "transparent") { el.style.strokeWidth = "8px"; return; }
    el.style.strokeWidth = px(mm) + "px";
  });
}

function fitView() {
  if (!ED.d) return;
  const [W, H] = ED.d.size || [420, 297];
  ED.vb = [-5, -5, W + 10, H + 10];
  const svg = svgEl();
  if (svg) svg.setAttribute("viewBox", ED.vb.join(" "));
}

function onWheel(e) {
  e.preventDefault();
  const svg = svgEl();
  const k = e.deltaY > 0 ? 1.2 : 1 / 1.2;
  const pt = svg.createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  const [x, y, w, h] = ED.vb;
  const nw = Math.min(Math.max(w * k, 5), ED.d.size[0] * 3);
  const nh = h * nw / w;
  ED.vb = [p.x - (p.x - x) * nw / w, p.y - (p.y - y) * nh / h, nw, nh];
  svg.setAttribute("viewBox", ED.vb.join(" "));
  drawOverlay();
}

// ------------------------------------------------------------------ overlay (snap marker and rubber band)

function ovClear() { const g = $("#ann-overlay"); if (g) g.innerHTML = ""; return g; }
function svgY(Y) { return ED.d.size[1] - Y; }
function ovLine(g, A, B, color) {
  const l = document.createElementNS(SVGNS, "line");
  l.setAttribute("x1", A[0]); l.setAttribute("y1", svgY(A[1]));
  l.setAttribute("x2", B[0]); l.setAttribute("y2", svgY(B[1]));
  l.setAttribute("stroke", color || "#1f5fae");
  l.setAttribute("stroke-width", 1.5);
  l.setAttribute("stroke-dasharray", "1.5,1");
  g.appendChild(l);
}
function ovMark(g, X, Y, kind) {
  const s = tolMM() * 0.5;
  const el = document.createElementNS(SVGNS, kind === "centre" ? "circle" : "rect");
  if (kind === "centre") { el.setAttribute("cx", X); el.setAttribute("cy", svgY(Y)); el.setAttribute("r", s * 0.6); }
  else { el.setAttribute("x", X - s / 2); el.setAttribute("y", svgY(Y) - s / 2); el.setAttribute("width", s); el.setAttribute("height", s); }
  el.setAttribute("fill", "none");
  el.setAttribute("stroke", kind === "mid" ? "#2e8b57" : "#d0451b");
  el.setAttribute("stroke-width", 2);
  g.appendChild(el);
}
function ovCircle(g, c) {
  const el = document.createElementNS(SVGNS, "circle");
  el.setAttribute("cx", c.X); el.setAttribute("cy", svgY(c.Y)); el.setAttribute("r", c.R);
  el.setAttribute("fill", "none"); el.setAttribute("stroke", "#d0451b");
  el.setAttribute("stroke-width", 2);
  g.appendChild(el);
}

function linearFeet(P1, P2, Q, orient) {
  let u;
  if (orient === "h") u = [1, 0];
  else if (orient === "v") u = [0, 1];
  else { const L = Math.hypot(P2[0] - P1[0], P2[1] - P1[1]) || 1; u = [(P2[0] - P1[0]) / L, (P2[1] - P1[1]) / L]; }
  const n = [-u[1], u[0]];
  const foot = P => { const d = (Q[0] - P[0]) * n[0] + (Q[1] - P[1]) * n[1]; return [P[0] + n[0] * d, P[1] + n[1] * d]; };
  return [foot(P1), foot(P2)];
}

function drawOverlay() {
  const g = ovClear();
  if (!g || !ED.mouse) return;
  const [X, Y] = ED.mouse;
  const t = ED.tool;
  if (["h", "v", "a", "leader", "balloon"].includes(t) && ED.pick.length < (t === "leader" || t === "balloon" ? 1 : 2)) {
    const view = ED.pick.length ? ED.pick[0].view : null;
    const s = nearestPoint(X, Y, view);
    if (s) ovMark(g, s.X, s.Y, s.kind);
  }
  if ((t === "diameter" || t === "radius") && ED.pick.length === 0) {
    const c = nearestCircle(X, Y);
    if (c) ovCircle(g, c);
    else if (t === "diameter") { const s = nearestPoint(X, Y, null); if (s) ovMark(g, s.X, s.Y, s.kind); }
  }
  if (t === "diameter" && ED.pick.length === 1 && ED.pick[0].x !== undefined) {
    const s = nearestPoint(X, Y, ED.pick[0].view);
    if (s) ovMark(g, s.X, s.Y, s.kind);
    ovLine(g, toSheet(ED.pick[0].view, ED.pick[0].x, ED.pick[0].y), [X, Y]);
  }
  if (t === "diameter" && ED.pick.length === 2) {
    const P1 = toSheet(ED.pick[0].view, ED.pick[0].x, ED.pick[0].y);
    const P2 = toSheet(ED.pick[1].view, ED.pick[1].x, ED.pick[1].y);
    const [A, B] = linearFeet(P1, P2, [X, Y], diaOrient());
    ovLine(g, P1, A); ovLine(g, P2, B); ovLine(g, A, B, "#d0451b");
  }
  if (["h", "v", "a"].includes(t) && ED.pick.length >= 1) {
    const P1 = toSheet(ED.pick[0].view, ED.pick[0].x, ED.pick[0].y);
    if (ED.pick.length === 1) ovLine(g, P1, [X, Y]);
    else {
      const P2 = toSheet(ED.pick[1].view, ED.pick[1].x, ED.pick[1].y);
      const [A, B] = linearFeet(P1, P2, [X, Y], t);
      ovLine(g, P1, A); ovLine(g, P2, B); ovLine(g, A, B, "#d0451b");
    }
  }
  if ((t === "diameter" || t === "radius") && ED.pick.length === 1 && ED.pick[0].c) {
    const p = ED.pick[0];
    const C = toSheet(p.view, p.c[0], p.c[1]);
    ovLine(g, C, [X, Y], "#d0451b");
  }
  if ((t === "leader" || t === "balloon") && ED.pick.length === 1) {
    const p = ED.pick[0];
    ovLine(g, toSheet(p.view, p.x, p.y), [X, Y], "#d0451b");
  }
  if (t === "angle") {
    for (const l of ED.pick) ovLine(g, l.A, l.B, "#d0451b");
    if (ED.pick.length < 2) {
      const l = nearestLine(X, Y, ED.pick.length ? ED.pick[0].view : null);
      if (l) ovLine(g, l.A, l.B, "#1c7ed6");
    } else {
      const an = angleFromLines(ED.pick[0], ED.pick[1]);
      if (an) { const C = toSheet(ED.pick[0].view, an.c[0], an.c[1]); ovMark(g, C[0], C[1], "centre"); ovCircle(g, { X: C[0], Y: C[1], R: Math.hypot(X - C[0], Y - C[1]) }); }
    }
  }
  if (t === "detail" && ED.pick.length === 1) {
    const p = ED.pick[0], C = toSheet(p.view, p.x, p.y);
    ovCircle(g, { X: C[0], Y: C[1], R: Math.hypot(X - C[0], Y - C[1]) });
  }
  if (ED.drag && ED.drag.moved) ovMark(g, X, Y, "end");
  if (ED.vdrag && ED.vdrag.moved) {
    const [dX, dY] = viewDelta(ED.vdrag, X, Y);
    const moving = ED.vdrag.view === "front" ? ["front", "top", "right"] : [ED.vdrag.view];
    moving.filter(n => ED.d.maps[n]).forEach(n => {
      const m = ED.d.maps[n];
      const r = document.createElementNS(SVGNS, "rect");
      r.setAttribute("x", m[5] + dX); r.setAttribute("y", svgY(m[8] + dY));
      r.setAttribute("width", m[7] - m[5]); r.setAttribute("height", m[8] - m[6]);
      r.setAttribute("fill", "rgba(31,95,174,0.06)"); r.setAttribute("stroke", "#1f5fae");
      r.setAttribute("stroke-width", 1.5); r.setAttribute("stroke-dasharray", "6,4");
      g.appendChild(r);
    });
  }
}

// ------------------------------------------------------------------ mouse

function pickPoint(X, Y, view) {
  const s = nearestPoint(X, Y, view);
  if (s) return { view: s.view, x: s.x, y: s.y };
  const v = view || viewAt(X, Y);
  if (!v) return null;
  const [x, y] = toModel(v, X, Y);
  return { view: v, x, y };
}

function onDown(e) {
  if (!ED.d) return;
  const svg = svgEl();
  if (e.button === 0 && ED.tool === "select" && !e.shiftKey && !e.target.closest("g.ann")) {
    const [X0, Y0] = eventSheet(e);
    const v = viewHit(X0, Y0);
    if (v) {
      ED.vdrag = { view: v, X0, Y0, x: e.clientX, y: e.clientY, moved: false };
      e.preventDefault();
      return;
    }
  }
  if (e.button === 1 || (e.button === 0 && ED.tool === "select" && !e.target.closest("g.ann"))) {
    ED.pan = { x: e.clientX, y: e.clientY, vb: ED.vb.slice(), moved: false };
    $("#ann-canvas").classList.add("panning");
    e.preventDefault();
    return;
  }
  if (e.button !== 0) return;
  const [X, Y] = eventSheet(e);
  if (ED.tool === "select") {
    const g = e.target.closest("g.ann");
    if (g) {
      select(g.dataset.ann);
      ED.drag = { id: g.dataset.ann, moved: false, x: e.clientX, y: e.clientY };
    }
    return;
  }
  toolClick(X, Y);
  e.preventDefault();
  void svg;
}

function onMove(e) {
  if (!ED.d) return;
  if (ED.pan) {
    const svg = svgEl();
    const k = ED.vb[2] / svg.clientWidth;
    const scale = Math.max(k, ED.vb[3] / svg.clientHeight);
    const dx = (e.clientX - ED.pan.x) * scale, dy = (e.clientY - ED.pan.y) * scale;
    ED.vb = [ED.pan.vb[0] - dx, ED.pan.vb[1] - dy, ED.pan.vb[2], ED.pan.vb[3]];
    svg.setAttribute("viewBox", ED.vb.join(" "));
    return;
  }
  ED.mouse = eventSheet(e);
  if (ED.drag && Math.hypot(e.clientX - ED.drag.x, e.clientY - ED.drag.y) > 3) ED.drag.moved = true;
  if (ED.vdrag && Math.hypot(e.clientX - ED.vdrag.x, e.clientY - ED.vdrag.y) > 3) ED.vdrag.moved = true;
  if (ED.tool === "select" && !ED.vdrag) {
    const onAnn = e.target.closest && e.target.closest("g.ann");
    svgEl().style.cursor = onAnn ? "pointer" : viewHit(ED.mouse[0], ED.mouse[1]) ? "move" : "default";
  }
  drawOverlay();
}

// ------------------------------------------------------------------ moving views

function viewHit(X, Y) {
  for (const [n, m] of Object.entries(ED.d.maps)) {
    if (X >= m[5] - 1 && X <= m[7] + 1 && Y >= m[6] - 1 && Y <= m[8] + 1) return n;
  }
  return null;
}

function viewDelta(vd, X, Y) {
  let dX = X - vd.X0, dY = Y - vd.Y0;
  if (vd.view === "top") dX = 0;      // stays below the front view
  if (vd.view === "right") dY = 0;    // stays beside the front view
  return [dX, dY];
}

async function moveView(vd, dX, dY) {
  const lay = JSON.parse(JSON.stringify(ED.d.layout || {}));
  if (vd.view.startsWith("detail_")) {
    const det = (lay.details || []).find(d => "detail_" + d.id === vd.view);
    const cur = (ED.d.details || []).find(d => "detail_" + d.id === vd.view);
    if (det && cur) { det.pos = [cur.pos[0] + dX, cur.pos[1] + dY]; await saveLayout(lay); }
    return;
  }
  lay.offsets = lay.offsets || {};
  const o = lay.offsets[vd.view] || [0, 0];
  lay.offsets[vd.view] = [o[0] + dX, o[1] + dY];
  await saveLayout(lay);
}

async function saveLayout(lay) {
  try {
    await api("/api/layout/" + encodeURIComponent(ED.d.ann_name || ED.d.name),
              { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lay) });
    await saveAndRefresh();
  } catch (e) { showErr(e); }
}

function resetViews() {
  if (ED.d) saveLayout(Object.assign({}, ED.d.layout || {}, { offsets: {}, hidden: (ED.d.layout || {}).hidden || [], details: ((ED.d.layout || {}).details || []).map(d => { const e = Object.assign({}, d); delete e.pos; return e; }) }));
}

/** List of the detail views with scale and delete. */
function renderDetails() {
  const box = $("#ann-details"), list = $("#ann-detail-list");
  if (!box || !ED.d) return;
  const dets = (ED.d.layout || {}).details || [];
  box.hidden = !dets.length;
  list.innerHTML = dets.map((d, i) => `<div class="row detail-row"><span>${d.id}: ${VIEW_LABELS[d.view] || d.view}, R ${(+d.r).toFixed(1)} mm</span><label class="inline">Magnification<input type="text" class="numf sk-tiny" data-det="${i}" value="${d.factor || 2}"></label><button type="button" data-detdel="${i}" title="Remove the detail view">×</button></div>`).join("");
  list.querySelectorAll("input[data-det]").forEach(inp => inp.onchange = () => {
    const k = numv(inp.value); if (!(k > 0)) return;
    const lay = JSON.parse(JSON.stringify(ED.d.layout || {})); lay.details[+inp.dataset.det].factor = k; saveLayout(lay);
  });
  list.querySelectorAll("button[data-detdel]").forEach(b => b.onclick = () => {
    const lay = JSON.parse(JSON.stringify(ED.d.layout || {}));
    const d = lay.details.splice(+b.dataset.detdel, 1)[0];
    ED.anns = ED.anns.filter(a => a.view !== "detail_" + d.id);
    saveLayout(lay);
  });
}

const VIEW_LABELS = { front: "Front", top: "Top", right: "Right", section: "A-A", iso: "Iso" };
function targetLabel(t) { return t === "sheet" ? "Sheet" : t.startsWith("detail_") ? "Detail " + t.slice(7) : (VIEW_LABELS[t] || t); }

/** Opens the sketch editor on the drawing: target "sheet" or a view name (sketch.js sketchEditForDrawing). */
function openSketch(target) {
  if (!ED.d) return status("Press Preview and select a drawing first", true);
  window.sketchEditForDrawing(ED.d, target, targetLabel(target), ok => { if (ok) saveAndRefresh(); });
}

/** List of the sketches on the drawing with Edit and delete. */
function renderSketches() {
  const box = $("#ann-sketches"), list = $("#ann-sketch-list");
  if (!box || !ED.d) return;
  const sks = ED.d.sketches || [];
  box.hidden = !sks.length;
  list.innerHTML = sks.map(t => `<div class="row detail-row"><span>${targetLabel(t)}</span><button type="button" class="small" data-skedit="${t}">Edit</button><button type="button" data-skdel="${t}" title="Remove the sketch">×</button></div>`).join("");
  list.querySelectorAll("button[data-skedit]").forEach(b => b.onclick = () => openSketch(b.dataset.skedit));
  list.querySelectorAll("button[data-skdel]").forEach(b => b.onclick = async () => {
    if (!confirm("Remove the sketch on " + targetLabel(b.dataset.skdel) + "?")) return;
    try {
      await api("/api/drawing/sketch/" + encodeURIComponent(ED.d.ann_name || ED.d.name) + "/" + b.dataset.skdel,
                { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ doc: {} }) });
      await saveAndRefresh();
    } catch (e) { showErr(e); }
  });
}
async function autoBalloons() {
  if (!ED.d) return;
  if (!ED.d.balloon_anchors || !ED.d.balloon_anchors.length) return status("Auto balloons: this drawing is not an assembly drawing", true);
  const view = ["front", "iso", "top", "right"].find(v => ED.d.maps[v]);
  if (!view) return;
  try {
    const r = await postJSON("/api/balloons/" + encodeURIComponent(ED.d.name), { anchors: ED.d.balloon_anchors, view, maps: ED.d.maps });
    const list = await r.json();
    commit(() => { ED.anns = ED.anns.filter(a => a.type !== "balloon").concat(list.map(a => Object.assign(a, { id: uid() }))); }, null);
    status(list.length + " balloon(s) placed; drag them to adjust");
  } catch (e) { showErr(e); }
}

async function holeCallouts() {
  if (!ED.d) return;
  if (!ED.d.holes || !ED.d.holes.length) return status("Hole callouts: this drawing has no hole features (Part tab, Hole)", true);
  try {
    const r = await postJSON("/api/hole_callouts/" + encodeURIComponent(ED.d.name), { holes: ED.d.holes, maps: ED.d.maps, settings: readSettings() });
    const list = await r.json();
    if (!list.length) return status("Hole callouts: no view looks along a hole axis", true);
    const old = new Set(ED.anns.filter(a => a.type === "note" && a.hole).map(a => a.id));
    commit(() => { ED.anns = ED.anns.filter(a => !old.has(a.id)).concat(list.map(a => Object.assign(a, { id: uid(), hole: true }))); }, null);
    status(list.length + " hole callout(s) placed; drag them to adjust, edit the text in Text");
  } catch (e) { showErr(e); }
}

function renderViewToggles() {
  const box = $("#ann-views");
  if (!box) return;
  if (!ED.d || !ED.d.all_views) { box.innerHTML = ""; return; }
  const hidden = new Set(ED.d.hidden_views || []);
  box.innerHTML = '<span class="hint">Views</span>' + ED.d.all_views.map(v =>
    `<label class="check inline"><input type="checkbox" data-view="${v}"${hidden.has(v) ? "" : " checked"}> ${VIEW_LABELS[v] || v}</label>`).join("");
  box.querySelectorAll("input[data-view]").forEach(cb => cb.onchange = () => {
    const lay = JSON.parse(JSON.stringify(ED.d.layout || {}));
    const h = new Set(lay.hidden || []);
    if (cb.checked) h.delete(cb.dataset.view); else h.add(cb.dataset.view);
    if (h.size >= ED.d.all_views.length) { cb.checked = true; status("At least one view stays on the drawing", true); return; }
    lay.hidden = [...h];
    saveLayout(lay);
  });
}

function onUp(e) {
  if (ED.vdrag) {
    const vd = ED.vdrag;
    ED.vdrag = null;
    if (vd.moved) {
      const [X, Y] = eventSheet(e);
      const [dX, dY] = viewDelta(vd, X, Y);
      moveView(vd, dX, dY);
    }
    drawOverlay();
    return;
  }
  if (ED.pan) {
    ED.pan = null;
    $("#ann-canvas").classList.remove("panning");
    return;
  }
  if (ED.drag) {
    const dr = ED.drag;
    ED.drag = null;
    if (dr.moved) {
      const a = ED.anns.find(x => x.id === dr.id);
      if (a) {
        const [X, Y] = eventSheet(e);
        commit(() => { a.pos = toModel(a.view, X, Y); if (a.type === "linear") a.text_free = true; });
      }
    }
    drawOverlay();
  }
}

function toolClick(X, Y) {
  const t = ED.tool;
  if (t === "sketch") {
    const v = viewAt(X, Y);
    setTool("select");
    openSketch(v || "sheet");
    return;
  }
  if (t === "detail") {
    if (!ED.pick.length) {
      const v = viewAt(X, Y);
      if (!v || v.startsWith("detail_") || v === "iso") return status("Click inside a front, top, right or section view", true);
      const [x, y] = toModel(v, X, Y);
      ED.pick.push({ view: v, x, y });
      updateHint();
    } else {
      const p = ED.pick[0], m = mapOf(p.view), C = toSheet(p.view, p.x, p.y);
      const r = Math.hypot(X - C[0], Y - C[1]) / m[2];
      ED.pick = [];
      if (r <= 0.1) return status("Click a point on the detail circle", true);
      const lay = JSON.parse(JSON.stringify(ED.d.layout || {}));
      lay.details = lay.details || [];
      const used = new Set(lay.details.map(d => d.id));
      let id = "B";
      for (const ch of "BCDEFGHJKLMNPQRSTUVWXYZ") { if (!used.has(ch)) { id = ch; break; } }
      lay.details.push({ id, view: p.view, c: [p.x, p.y], r: +r.toFixed(3), factor: 2 });
      updateHint();
      saveLayout(lay);
    }
    return;
  }
  if (t === "angle") {
    if (ED.pick.length < 2) {
      const l = nearestLine(X, Y, ED.pick.length ? ED.pick[0].view : null);
      if (!l) return status(ED.pick.length ? "Pick a straight edge in the same view" : "Pick a straight edge of a view", true);
      if (ED.pick.length && l === ED.pick[0]) return;
      if (ED.pick.length && !angleFromLines(ED.pick[0], l)) return status("The lines are parallel: pick a line at an angle", true);
      ED.pick.push(l);
    } else {
      const v = ED.pick[0].view, an = angleFromLines(ED.pick[0], ED.pick[1]);
      const a = { id: uid(), type: "angle", view: v, c: an.c, p1: an.p1, p2: an.p2, pos: toModel(v, X, Y), tol: { mode: "none" } };
      ED.pick = [];
      commit(() => ED.anns.push(a), a.id);
    }
    updateHint();
    drawOverlay();
    return;
  }
  if (["h", "v", "a"].includes(t)) {
    if (ED.pick.length < 2) {
      const p = pickPoint(X, Y, ED.pick.length ? ED.pick[0].view : null);
      if (!p) return status("Pick a point inside a view", true);
      if (ED.pick.length && p.x === ED.pick[0].x && p.y === ED.pick[0].y) return;
      ED.pick.push(p);
    } else {
      const v = ED.pick[0].view;
      const a = { id: uid(), type: "linear", view: v, orient: t, p1: [ED.pick[0].x, ED.pick[0].y],
                  p2: [ED.pick[1].x, ED.pick[1].y], pos: toModel(v, X, Y), tol: { mode: "none" } };
      ED.pick = [];
      commit(() => ED.anns.push(a), a.id);
    }
  } else if (t === "diameter" && (ED.pick.length && ED.pick[0].c === undefined ||
                                   !ED.pick.length && !nearestCircle(X, Y))) {
    // diameter between two edge points (shaft or bore in a side view)
    if (ED.pick.length < 2) {
      const p = pickPoint(X, Y, ED.pick.length ? ED.pick[0].view : null);
      if (!p) return status("Pick a point inside a view", true);
      if (ED.pick.length && p.x === ED.pick[0].x && p.y === ED.pick[0].y) return;
      ED.pick.push(p);
    } else {
      const v = ED.pick[0].view;
      const a = { id: uid(), type: "linear", dia: true, view: v, orient: diaOrient(), p1: [ED.pick[0].x, ED.pick[0].y],
                  p2: [ED.pick[1].x, ED.pick[1].y], pos: toModel(v, X, Y), tol: { mode: "none" } };
      ED.pick = [];
      commit(() => ED.anns.push(a), a.id);
    }
  } else if (t === "diameter" || t === "radius") {
    if (!ED.pick.length) {
      const c = nearestCircle(X, Y);
      if (!c) return status("No circle or arc at this position", true);
      ED.pick.push(c);
    } else {
      const c = ED.pick[0];
      const a = { id: uid(), type: t, view: c.view, c: c.c, r: c.r, pos: toModel(c.view, X, Y), tol: { mode: "none" } };
      ED.pick = [];
      commit(() => ED.anns.push(a), a.id);
    }
  } else if (t === "note") {
    const v = viewAt(X, Y);
    const pos = toModel(v, X, Y);
    askText("").then(text => {
      if (!text) return;
      const a = { id: uid(), type: "note", view: v, pos, anchor: null, text };
      commit(() => ED.anns.push(a), a.id);
    });
  } else if (t === "balloon") {
    if (!ED.pick.length) {
      const p = pickPoint(X, Y, null);
      ED.pick.push(p || { view: null, x: X, y: Y });
    } else {
      const p = ED.pick[0];
      const pos = toModel(p.view, X, Y);
      ED.pick = [];
      const next = ED.anns.filter(a => a.type === "balloon").length + 1;
      askValue("Item number", String(next), true).then(text => {
        if (!text) { drawOverlay(); updateHint(); return; }
        const a = { id: uid(), type: "balloon", view: p.view, anchor: [p.x, p.y], pos, text };
        commit(() => ED.anns.push(a), a.id);
      });
    }
  } else if (t === "leader") {
    if (!ED.pick.length) {
      const p = pickPoint(X, Y, null);
      ED.pick.push(p || { view: null, x: X, y: Y });
    } else {
      const p = ED.pick[0];
      const pos = toModel(p.view, X, Y);
      ED.pick = [];
      askText("").then(text => {
        if (!text) { drawOverlay(); updateHint(); return; }
        const a = { id: uid(), type: "note", view: p.view, anchor: [p.x, p.y], pos, text };
        commit(() => ED.anns.push(a), a.id);
      });
    }
  }
  updateHint();
  drawOverlay();
}

// Multi-line text entry: Enter = new line, Ctrl+Enter or OK = accept, Esc = cancel
function askText(initial) {
  return new Promise(resolve => {
    const dlg = $("#text-dialog"), ta = $("#text-dialog-input");
    ta.value = initial || "";
    dlg.hidden = false;
    ta.focus();
    const done = (val) => {
      dlg.hidden = true;
      $("#text-dialog-ok").onclick = $("#text-dialog-cancel").onclick = ta.onkeydown = null;
      resolve(val);
    };
    $("#text-dialog-ok").onclick = () => done(ta.value.replace(/\s+$/, ""));
    $("#text-dialog-cancel").onclick = () => done(null);
    ta.onkeydown = (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); done(ta.value.replace(/\s+$/, "")); }
      if (e.key === "Escape") { e.preventDefault(); done(null); }
    };
  });
}

function setTool(t) {
  ED.tool = t;
  ED.pick = [];
  document.querySelectorAll("#ann-tools button").forEach(b => b.classList.toggle("active", b.dataset.tool === t));
  $("#ann-canvas").classList.toggle("select", t === "select");
  updateHint();
  drawOverlay();
}

function updateHint() {
  const h = HINTS[ED.tool];
  let i = ED.pick.length;
  if (ED.tool === "diameter" && ED.pick.length && ED.pick[0].c) i = 2;   // circle picked: place text
  $("#ann-hint").textContent = typeof h === "string" ? h : h[Math.min(i, h.length - 1)];
}

// ------------------------------------------------------------------ save and refresh

async function commit(fn, selectId) {
  ED.hist.push(JSON.stringify(ED.anns));
  if (ED.hist.length > 100) ED.hist.shift();
  fn();
  if (selectId) ED.sel = selectId;
  await saveAndRefresh();
}

async function saveAndRefresh() {
  const d = ED.d;
  try {
    await api("/api/annotations/" + encodeURIComponent(d.ann_name || d.name),
              { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(ED.anns) });
    const req = { selection: [d.selection], settings: readSettings(), fields: readFields() };
    const r = await postJSON("/api/preview", req);
    const nd = (await r.json()).drawings.find(x => x.name === d.name);
    if (!nd) return;
    const i = state.drawings.findIndex(x => x.name === d.name);
    if (i >= 0) state.drawings[i] = nd;
    ED.d = nd;
    ED.anns = JSON.parse(JSON.stringify(nd.annotations || []));
    buildSnaps();
    drawCanvas(true);
    annShowProps();
    renderDetails();
  renderSketches();
  } catch (e) { showErr(e); }
}

async function undo() {
  if (!ED.hist.length) return;
  ED.anns = JSON.parse(ED.hist.pop());
  if (ED.sel && !ED.anns.some(a => a.id === ED.sel)) ED.sel = null;
  await saveAndRefresh();
}

// ------------------------------------------------------------------ properties

function select(id) {
  ED.sel = id;
  const svg = svgEl();
  if (svg) svg.querySelectorAll("g.ann").forEach(g => g.classList.toggle("sel", g.dataset.ann === id));
  annShowProps();
}

function current() { return ED.anns.find(a => a.id === ED.sel) || null; }

function annShowProps() {
  const a = current();
  $("#ann-form").hidden = !a;
  if (!a) return;
  const names = { linear: { h: "Horizontal dimension", v: "Vertical dimension", a: "Aligned dimension" },
                  diameter: "Diameter", radius: "Radius", note: "Note", balloon: "Balloon" };
  $("#ann-kind").textContent = a.type === "linear" ? (a.dia ? "Diameter (side view)" : names.linear[a.orient]) : names[a.type];
  const v = measured(a);
  $("#ann-value").textContent = v === null ? "" : a.type === "angle" ? fmtNum(v) + "°" :
    (a.type === "diameter" || a.dia ? "Ø" : a.type === "radius" ? "R" : "") + (isInch() ? inchText(v, 3) + " in" : fmtNum(v) + " mm");
  const isNote = a.type === "note" || a.type === "balloon";
  $("#ann-dim-fields").hidden = isNote;
  $("#ann-note-fields").hidden = !isNote;
  $("#ann-height").value = a.height || "";
  if (isNote) { $("#ann-notetext").value = a.text || ""; return; }
  const tol = a.tol || { mode: "none" };
  $("#ann-prefix").value = a.prefix || "";
  $("#ann-text").value = a.text || "";
  $("#ann-centred-row").hidden = a.type !== "linear";
  $("#ann-centred").checked = !a.text_free;
  $("#ann-tolmode").value = tol.mode || "none";
  $("#ann-fit").value = tol.fit || "";
  $("#ann-showdev").checked = tol.show_dev !== false;
  $("#ann-plus").value = devUm(tol.plus);
  $("#ann-minus").value = devUm(tol.minus);
  $("#ann-fit-row").hidden = tol.mode !== "fit";
  $("#ann-fit-result").hidden = tol.mode !== "fit";
  $("#ann-dev-row").hidden = !(tol.mode === "sym" || tol.mode === "dev");
  $("#ann-minus").parentElement.hidden = tol.mode === "sym";
  if (tol.mode === "fit" && tol.fit) showFit(v, tol.fit);
}

async function showFit(size, cls) {
  try {
    const r = await postJSON("/api/fit", { size, cls });
    const f = await r.json();
    $("#ann-fit-result").textContent = `${cls}: ${devUm(f.upper)} / ${devUm(f.lower)} ${devUnit()}`;
  } catch (e) { $("#ann-fit-result").textContent = e.message; }
}

function propsChanged() {
  const a = current();
  if (!a) return;
  commit(() => {
    const hgt = parseFloat($("#ann-height").value);
    if (hgt > 0) a.height = hgt; else delete a.height;
    if (a.type === "note" || a.type === "balloon") { a.text = $("#ann-notetext").value.trim(); return; }
    a.prefix = $("#ann-prefix").value;
    a.text = $("#ann-text").value;
    if (a.type === "linear") a.text_free = !$("#ann-centred").checked;
    const mode = $("#ann-tolmode").value;
    a.tol = { mode };
    if (mode === "fit") { a.tol.fit = $("#ann-fit").value.trim(); a.tol.show_dev = $("#ann-showdev").checked; }
    if (mode === "sym") a.tol.plus = devMm($("#ann-plus").value);
    if (mode === "dev") { a.tol.plus = devMm($("#ann-plus").value); a.tol.minus = devMm($("#ann-minus").value); }
  }, a.id);
}

function deleteSelected() {
  const a = current();
  if (!a) return;
  commit(() => { ED.anns = ED.anns.filter(x => x.id !== a.id); ED.sel = null; });
}

// ------------------------------------------------------------------ init

(function initAnnotator() {
  document.querySelectorAll("#ann-tools button").forEach(b => b.onclick = () => setTool(b.dataset.tool));
  $("#ann-undo").onclick = undo;
  $("#ann-resetviews").onclick = resetViews;
  $("#ann-autoballoons").onclick = autoBalloons;
  $("#ann-plist").onchange = () => { if (ED.d) saveLayout(Object.assign({}, ED.d.layout || {}, { parts_list: $("#ann-plist").checked })); };
  $("#ann-holecallouts").onclick = holeCallouts;
  $("#ann-fitview").onclick = () => { fitView(); drawOverlay(); };
  $("#ann-delete").onclick = deleteSelected;
  $("#ann-fitcalc").onclick = () => {
    const a = current();
    if (!a || !window.openReference) return;
    window.openReference("fits", null, { size: measured(a), cls: $("#ann-fit").value, apply: cls => {
      $("#ann-tolmode").value = "fit"; $("#ann-fit").value = cls; propsChanged(); annShowProps(); } });
  };
  $("#ann-drawing").onchange = () => {
    const d = (state.drawings || []).find(x => x.name === $("#ann-drawing").value);
    if (d) loadDrawing(d, false);
  };
  ["#ann-prefix", "#ann-text", "#ann-centred", "#ann-tolmode", "#ann-fit", "#ann-showdev", "#ann-plus", "#ann-minus", "#ann-notetext", "#ann-height"]
    .forEach(s => $(s).addEventListener("change", propsChanged));
  document.addEventListener("keydown", e => {
    if ($("#tab-annotate").hidden || document.querySelector(".modal:not([hidden])")) return;   // keys of an open window
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); return; }
    if (e.key === "Escape") { if (ED.pick.length) { ED.pick = []; updateHint(); drawOverlay(); } else { ED.sel = null; select(null); } return; }
    if (e.key === "Delete" || e.key === "Backspace") { deleteSelected(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (leftKeys() ? e.code === FIT_KEY.left : e.key.toLowerCase() === "f") { fitView(); return; }
    const t = leftKeys() ? TOOL_CODES_LEFT[e.code] : TOOL_KEYS[e.key.toLowerCase()];
    if (t) setTool(t);
  });
  fetch("/api/fits").then(r => r.json()).then(f => {
    const dl = $("#fit-classes");
    [...(f.holes || []), ...(f.shafts || [])].forEach(c => { const o = document.createElement("option"); o.value = c; dl.appendChild(o); });
  });
  setTool("select");
  window.addEventListener("optionschanged", () => {
    annKeyTitles();
    document.querySelectorAll(".dev-unit").forEach(el => { el.textContent = devUnit(); });
    if (current()) annShowProps();
  });
})();
