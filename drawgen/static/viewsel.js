// Selection in the 3D views of the Analysis and Explicit tabs: type filter (faces, edges, bodies, reference points),
// click to select or deselect, box select and selection for a target (supports, loads, masses, reference point
// couplings, node sets, sections).
//
// The selection lives in H.sel (shellmodel.selState): faces Set("<comp>:<face>"), edges Set("<comp>:<edge>"), bodies
// Set(body id: component id for a solid, "<comp>:<surface id>" for a surface body), points Set(reference point id),
// types Set of the types a click or a box takes (empty: selection off), box (left drag draws a box), collect (a
// selection for a target: {text, types, cb}).
//
// Host H (the shellmodel.js host) with H.view:
//   canvas(), camera(), box() (the view element), modelShown() (Show is Model), showModel() (Show Model),
//   comps() [{id, mesh {vertices, triangles, face_of_tri, face_body, edges}, matrix (THREE.Matrix4), surfaces}],
//   points() [{id, xyz}], faceAt(e) {comp, face} | null, edgeAt(e) {comp, edge} | null
// and H.render(), H.draw(), H.status(text, isError), H.esc(s).
//
// Box: drag to the right selects the items fully inside the box (window), drag to the left the items inside or
// crossing it (crossing). Ctrl or Alt at release: the items leave the selection. Items behind others are taken too.
import * as THREE from "three";
import { selState } from "/static/shellmodel.js";

export const TYPES = [["faces", "Faces"], ["edges", "Edges"], ["bodies", "Bodies"], ["points", "Ref. points"]];
const NAMES = { faces: "face(s)", edges: "edge(s)", bodies: "body(ies)", points: "reference point(s)" };
const fkey = r => r.comp + ":" + r.face;
const ekey = r => r.comp + ":" + r.edge;
const split = k => { const i = k.lastIndexOf(":"); return [k.slice(0, i), +k.slice(i + 1)]; };

export function active(H) { const S = selState(H); return S.types.size > 0 && (!H.view || H.view.modelShown()); }

/** Number of selected items of each type, as text. */
export function countText(H) {
  const S = selState(H);
  const parts = TYPES.map(([k]) => [k, S[k].size]).filter(([, n]) => n).map(([k, n]) => `${n} ${NAMES[k]}`);
  return parts.length ? parts.join(", ") : "nothing selected";
}

/** Body id of a face of a component (view data): the component id for a solid face, "<comp>:<surface id>" for a
 *  face of a surface body. */
export function bodyOfFace(c, fi) {
  const fb = (c.mesh && c.mesh.face_body) || [];
  const b = fb[fi];
  if (b === null || b === undefined) return c.id;
  const sf = (c.surfaces || [])[b];
  return sf ? c.id + ":" + sf.id : c.id;
}
/** Faces of a body: [{comp, face}]. */
export function facesOfBody(H, bid) {
  const out = [];
  for (const c of H.view.comps()) {
    const fot = (c.mesh && c.mesh.face_of_tri) || [];
    let n = ((c.mesh && c.mesh.face_body) || []).length;
    for (const fi of fot) if (fi + 1 > n) n = fi + 1;
    for (let fi = 0; fi < n; fi++) if (bodyOfFace(c, fi) === bid) out.push({ comp: c.id, face: fi });
  }
  return out;
}

/** The selected items of the types: {faces: [refs], edges: [refs], bodies: [ids], points: [ids]}. expand: the faces
 *  of the selected bodies are added to the faces (bodies left empty). */
export function items(H, types, expand) {
  const S = selState(H), ok = new Set(types || TYPES.map(t => t[0]));
  const out = { faces: [], edges: [], bodies: [], points: [] };
  if (ok.has("faces")) out.faces = [...S.faces].map(k => { const [comp, face] = split(k); return { comp, face }; });
  if (ok.has("edges")) out.edges = [...S.edges].map(k => { const [comp, edge] = split(k); return { comp, edge }; });
  if (ok.has("bodies")) {
    if (expand && ok.has("faces")) {
      const have = new Set(out.faces.map(fkey));
      for (const b of S.bodies) for (const r of facesOfBody(H, b)) if (!have.has(fkey(r))) { have.add(fkey(r)); out.faces.push(r); }
    } else out.bodies = [...S.bodies];
  }
  if (ok.has("points")) out.points = [...S.points];
  return out;
}
export function count(it) { return it.faces.length + it.edges.length + it.bodies.length + it.points.length; }
export function clear(H) { const S = selState(H); S.faces = new Set(); S.edges = new Set(); S.bodies = new Set(); S.points = new Set(); }

function changed(H, text) { renderBar(H); H.render(); H.draw(); if (text !== undefined) H.status(text); }

/** Sets the types a click or a box takes (empty: selection off). */
export function setTypes(H, types) {
  const S = selState(H);
  S.types = new Set(types);
  changed(H, S.types.size ? `Selecting ${[...S.types].map(t => NAMES[t].replace("(s)", "s").replace("(ies)", "ies")).join(", ")}: click to select or deselect${S.box ? ", drag a box (to the right: inside, to the left: crossing)" : ""} (Esc ends)` : "Selection ended: " + countText(H));
}

// ------------------------------------------------------------------ toolbar

/** Selection toolbar of the view into el (the type buttons, Box, Clear, the count; Done and Cancel of a selection
 *  for a target). */
export function renderBar(H, el) {
  el = el || H.selBar;
  if (!el) return;
  H.selBar = el;
  const S = selState(H), esc = H.esc;
  let h = `<span class="vs-lbl">Select</span>` + TYPES.map(([k, t]) => `<button type="button" class="small${S.types.has(k) ? " on" : ""}" data-vs="${k}" title="Clicks and boxes take ${NAMES[k].replace("(s)", "s").replace("(ies)", "ies")}">${t}</button>`).join("") +
    `<button type="button" class="small${S.box ? " on" : ""}" data-vs="box" title="Left drag draws a box: to the right the items fully inside, to the left the items inside or crossing; Ctrl or Alt: deselect">Box</button>` +
    `<button type="button" class="small" data-vs="clear" title="Clear the selection">Clear</button>` +
    (H.suppressCfg ? `<button type="button" class="small" data-vs="sup" title="Set the selected bodies, and the sections (or bodies) of the selected faces, to off: left out of the mesh and the solve">Suppress</button>` +
      `<button type="button" class="small" data-vs="unsup" title="Set the selected bodies, and the sections (or bodies) of the selected faces, back to their model before Suppress">Unsuppress</button>` : "") +
    `<span class="hint vs-count">${esc(countText(H))}</span>`;
  if (S.collect) h += `<span class="vs-collect">${esc(S.collect.text)}</span><button type="button" class="small primary" data-vs="done" title="Use the selection (Enter)">Done</button><button type="button" class="small" data-vs="cancel" title="Esc">Cancel</button>`;
  el.innerHTML = h;
  el.querySelectorAll("[data-vs]").forEach(b => b.onclick = () => {
    const k = b.dataset.vs;
    if (k === "box") { S.box = !S.box; if (S.box && !S.types.size) S.types = new Set(["faces"]); changed(H, S.box ? "Box: drag to the right for the items inside, to the left for the items inside or crossing (Ctrl or Alt: deselect)" : "Box off"); }
    else if (k === "clear") { clear(H); changed(H, "Selection cleared"); }
    else if (k === "sup" || k === "unsup") suppress(H, k === "sup");
    else if (k === "done") finish(H);
    else if (k === "cancel") cancel(H);
    else { const t = new Set(S.types); if (t.has(k)) t.delete(k); else t.add(k); setTypes(H, [...t]); }
  });
}

// ------------------------------------------------------------------ selection for a target

/** Selection for a target: the selected items of opts.types go to opts.cb(items) at once when there are any; else
 *  clicks and boxes take items of those types until Done or Enter. cb returns an error text to keep the selection
 *  open. opts: {text, types, cb, expand (the faces of selected bodies as faces), extra (e => a target of the tab
 *  under the cursor or null), cbExtra (hit => error text or nothing)}. */
export function collect(H, opts) {
  const S = selState(H);
  const it = items(H, opts.types, opts.expand);
  if (count(it)) {
    const err = opts.cb(it);
    if (err) { H.status(err, true); return; }
    clear(H); changed(H);
    return;
  }
  S.collect = Object.assign({ prev: [...S.types] }, opts);
  S.types = new Set(opts.types);
  if (H.view && !H.view.modelShown() && H.view.showModel) H.view.showModel();
  changed(H, opts.text + ": select, then Done or Enter (Esc cancels)");
}
export function finish(H) {
  const S = selState(H), c = S.collect;
  if (!c) return false;
  const it = items(H, c.types, c.expand);
  if (!count(it)) { H.status("Nothing selected: " + c.text, true); return true; }
  const err = c.cb(it);
  if (err) { H.status(err, true); return true; }
  S.collect = null;
  S.types = new Set(c.prev);
  clear(H);
  changed(H, c.text + ": " + count(it) + " item(s)");
  return true;
}
export function cancel(H) {
  const S = selState(H), c = S.collect;
  if (!c) return false;
  S.collect = null;
  S.types = new Set(c.prev);
  changed(H, "Cancelled");
  return true;
}

/** Keys of the view: Enter ends a selection for a target, Esc cancels it or ends the selection. Returns true when
 *  the key was taken. */
export function key(H, e) {
  const S = selState(H);
  if (e.key === "Enter" && S.collect) { finish(H); return true; }
  if (e.key === "Escape") {
    if (S.collect) return cancel(H);
    if (S.types.size || S.box) { S.types = new Set(); S.box = false; changed(H, "Selection ended: " + countText(H)); return true; }
  }
  return false;
}

// ------------------------------------------------------------------ click

function toggle(set, k) { if (set.has(k)) set.delete(k); else set.add(k); }
/** A click in the view while selecting: toggles the reference point (within 10 px), the edge (within 8 px), the face
 *  or the body under the cursor, of the types on. Returns true when the click was taken. */
export function click(H, e) {
  if (!active(H)) return false;
  const S = selState(H), V = H.view;
  if (S.collect && S.collect.extra) {                       // a target of the tab (a member end, a member) ends the selection
    const hit = S.collect.extra(e);
    if (hit) {
      const c = S.collect, err = c.cbExtra(hit);
      if (err) { H.status(err, true); return true; }
      S.collect = null; S.types = new Set(c.prev); clear(H);
      changed(H, c.text + ": done");
      return true;
    }
  }
  if (S.types.has("points")) {
    const r = V.canvas().getBoundingClientRect(), cam = V.camera(), v = new THREE.Vector3();
    let best = null;
    for (const p of V.points()) {
      v.set(...p.xyz).project(cam);
      const d = Math.hypot((v.x + 1) / 2 * r.width + r.left - e.clientX, (1 - v.y) / 2 * r.height + r.top - e.clientY);
      if (d < 10 && (!best || d < best.d)) best = { id: p.id, d };
    }
    if (best) { toggle(S.points, best.id); changed(H, countText(H)); return true; }
  }
  if (S.types.has("edges")) {
    const eg = V.edgeAt(e);
    if (eg) { toggle(S.edges, ekey(eg)); changed(H, countText(H)); return true; }
  }
  if (S.types.has("faces") || S.types.has("bodies")) {
    const f = V.faceAt(e);
    if (f) {
      if (S.types.has("faces")) toggle(S.faces, fkey(f));
      else { const c = V.comps().find(x => x.id === f.comp); if (c) toggle(S.bodies, bodyOfFace(c, f.face)); }
      changed(H, countText(H));
      return true;
    }
  }
  return true;                                              // a click on empty space while selecting does nothing
}

// ------------------------------------------------------------------ box

function segHitsRect(a, b, R) {
  // Liang-Barsky clip of segment a-b against the rectangle
  let t0 = 0, t1 = 1;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const p = [-dx, dx, -dy, dy], q = [a[0] - R.x0, R.x1 - a[0], a[1] - R.y0, R.y1 - a[1]];
  for (let i = 0; i < 4; i++) {
    if (p[i] === 0) { if (q[i] < 0) return false; continue; }
    const t = q[i] / p[i];
    if (p[i] < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
  }
  return true;
}
function inTri(p, a, b, c) {
  const s = (u, v, w) => (u[0] - w[0]) * (v[1] - w[1]) - (v[0] - w[0]) * (u[1] - w[1]);
  const d1 = s(p, a, b), d2 = s(p, b, c), d3 = s(p, c, a);
  return !((d1 < 0 || d2 < 0 || d3 < 0) && (d1 > 0 || d2 > 0 || d3 > 0));
}

/** Items of the types in the screen rectangle R {x0, y0, x1, y1} (canvas pixels): {faces, edges, bodies, points}
 *  as key lists. crossing: inside or crossing; else fully inside. */
export function inBox(H, R, crossing, types) {
  const V = H.view, cam = V.camera(), cv = V.canvas(), W = cv.clientWidth || 1, Hh = cv.clientHeight || 1;
  const v = new THREE.Vector3();
  const scr = (x, y, z, M) => { v.set(x, y, z); if (M) v.applyMatrix4(M); v.project(cam); return [(v.x + 1) / 2 * W, (1 - v.y) / 2 * Hh]; };
  const inside = q => q[0] >= R.x0 && q[0] <= R.x1 && q[1] >= R.y0 && q[1] <= R.y1;
  const out = { faces: [], edges: [], bodies: [], points: [] };
  const want = new Set(types);
  for (const c of V.comps()) {
    const m = c.mesh;
    if (!m) continue;
    if (want.has("faces") || want.has("bodies")) {
      const P = m.vertices.map(q => scr(q[0], q[1], q[2], c.matrix)), Pin = P.map(inside);
      const all = new Map(), touch = new Map();
      m.triangles.forEach((tr, k) => {
        const fi = m.face_of_tri[k];
        if (!all.has(fi)) { all.set(fi, true); touch.set(fi, false); }
        const ins = tr.map(i => Pin[i]);
        if (!ins.every(Boolean)) all.set(fi, false);
        if (touch.get(fi)) return;
        if (ins.some(Boolean)) { touch.set(fi, true); return; }
        if (!crossing) return;
        const [a, b, d] = tr.map(i => P[i]);
        if (segHitsRect(a, b, R) || segHitsRect(b, d, R) || segHitsRect(d, a, R) || inTri([R.x0, R.y0], a, b, d)) touch.set(fi, true);
      });
      const hit = fi => crossing ? touch.get(fi) : all.get(fi);
      if (want.has("faces")) for (const fi of all.keys()) if (hit(fi)) out.faces.push(c.id + ":" + fi);
      if (want.has("bodies")) {
        const bAll = new Map(), bAny = new Map();
        for (const fi of all.keys()) {
          const b = bodyOfFace(c, fi);
          bAll.set(b, (bAll.has(b) ? bAll.get(b) : true) && all.get(fi));
          bAny.set(b, bAny.get(b) || touch.get(fi));
        }
        for (const [b, ok] of (crossing ? bAny : bAll)) if (ok) out.bodies.push(b);
      }
    }
    if (want.has("edges") && m.edges) {
      m.edges.forEach((pl, ei) => {
        const P = pl.map(q => scr(q[0], q[1], q[2], c.matrix));
        const ins = P.map(inside);
        let ok = crossing ? ins.some(Boolean) : ins.every(Boolean);
        if (!ok && crossing) for (let i = 1; i < P.length && !ok; i++) ok = segHitsRect(P[i - 1], P[i], R);
        if (ok) out.edges.push(c.id + ":" + ei);
      });
    }
  }
  if (want.has("points")) for (const p of V.points()) if (inside(scr(...p.xyz))) out.points.push(p.id);
  return out;
}

/** Box drag on the view element: installed once per host. */
export function attach(H) {
  const V = H.view, el = V.box();
  if (!el || el.dataset.vsBox) return;
  el.dataset.vsBox = "1";
  el.addEventListener("pointerdown", e => {
    const S = selState(H);
    if (e.button !== 0 || !S.box || !active(H) || e.target !== V.canvas()) return;
    e.stopPropagation();
    e.preventDefault();
    const cr = V.canvas().getBoundingClientRect(), er = el.getBoundingClientRect();
    const x0 = e.clientX, y0 = e.clientY;
    const div = document.createElement("div");
    div.className = "vs-box";
    el.appendChild(div);
    const place = (x, y) => {
      const l = Math.min(x0, x), t = Math.min(y0, y);
      Object.assign(div.style, { left: (l - er.left) + "px", top: (t - er.top) + "px", width: Math.abs(x - x0) + "px", height: Math.abs(y - y0) + "px" });
      div.classList.toggle("crossing", x < x0);
    };
    place(x0, y0);
    const move = ev => place(ev.clientX, ev.clientY);
    const up = ev => {
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", up, true);
      div.remove();
      if (Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) < 4) { click(H, ev); return; }
      const R = { x0: Math.min(x0, ev.clientX) - cr.left, x1: Math.max(x0, ev.clientX) - cr.left,
                  y0: Math.min(y0, ev.clientY) - cr.top, y1: Math.max(y0, ev.clientY) - cr.top };
      const crossing = ev.clientX < x0, remove = ev.ctrlKey || ev.altKey || ev.metaKey;
      const got = inBox(H, R, crossing, [...S.types]);
      let n = 0;
      for (const k of ["faces", "edges", "bodies", "points"]) for (const id of got[k]) { n++; if (remove) S[k].delete(id); else S[k].add(id); }
      changed(H, `Box (${crossing ? "crossing" : "inside"}): ${n} item(s) ${remove ? "deselected" : "selected"}; ${countText(H)}`);
    };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", up, true);
  }, true);
}

// ------------------------------------------------------------------ targets

/** Support or load target from selected items: one reference point {point}, one face or edge (its reference), or
 *  {faces, edges, bodies}. Returns {target} or {error}. */
export function targetOf(it, opts) {
  opts = opts || {};
  const n = count(it);
  if (!n) return { error: "nothing selected" };
  if (it.points.length) {
    if (n > 1) return { error: "a reference point is a target of its own: select one reference point, or faces, edges and bodies" };
    return { target: { point: it.points[0] } };
  }
  if (it.faces.length === 1 && n === 1) return { target: it.faces[0] };
  if (it.edges.length === 1 && n === 1) return { target: it.edges[0] };
  const t = {};
  for (const k of ["faces", "edges", "bodies"]) if (it[k].length) t[k] = it[k];
  return { target: t };
}
/** Faces and edges of a target (bodies as their faces): {faces: [refs], edges: [refs]}. */
export function targetRefs(H, t) {
  const out = { faces: [], edges: [] };
  if (!t) return out;
  if (t.face !== undefined) out.faces.push(t);
  else if (t.edge !== undefined) out.edges.push(t);
  for (const r of t.faces || []) out.faces.push(r);
  for (const r of t.edges || []) out.edges.push(r);
  if (H.view) for (const b of t.bodies || []) out.faces.push(...facesOfBody(H, b));
  return out;
}
/** Text of a multi-item target, or null for other targets. */
export function multiText(t) {
  if (!t || !(t.faces || t.edges || t.bodies)) return null;
  const parts = [];
  if ((t.faces || []).length) parts.push(t.faces.length + " face(s)");
  if ((t.edges || []).length) parts.push(t.edges.length + " edge(s)");
  if ((t.bodies || []).length) parts.push(t.bodies.length + " body(ies)");
  return parts.join(", ") || "(none)";
}
/** Re-selects the items of a target in the view. */
export function show(H, t) {
  const S = selState(H);
  clear(H);
  if (!t) { changed(H); return; }
  if (t.face !== undefined) S.faces.add(fkey(t));
  else if (t.edge !== undefined) S.edges.add(ekey(t));
  else if (t.point !== undefined) S.points.add(t.point);
  for (const r of t.faces || []) S.faces.add(fkey(r));
  for (const r of t.edges || []) S.edges.add(ekey(r));
  for (const b of t.bodies || []) S.bodies.add(b);
  changed(H, countText(H));
}

// ------------------------------------------------------------------ suppress

/** Bodies and sections of the selection: selected bodies; a selected face gives its section, else its body.
 *  Returns [[kind ("body" | "shell" | "section"), id]]. */
export function suppressTargets(H, it) {
  const out = new Map(), d = H.doc();
  const add = (kind, id) => out.set(kind + "|" + id, [kind, id]);
  const comps = H.view.comps();
  for (const b of it.bodies) add(b.includes(":") ? "shell" : "body", b);
  for (const r of it.faces) {
    const sec = (d.sections || []).find(x => (x.faces || []).some(q => q.comp === r.comp && q.face === r.face));
    if (sec) { add("section", sec.id); continue; }
    const c = comps.find(x => x.id === r.comp);
    if (!c) continue;
    const b = bodyOfFace(c, r.face);
    add(b.includes(":") ? "shell" : "body", b);
  }
  return [...out.values()];
}
/** Suppress (on) or unsuppress the bodies and sections of the selection. H.suppressCfg(kind, id) returns [object,
 *  key of its model, default model]; the model before Suppress is kept in prev_off. */
export function suppress(H, on) {
  const it = items(H, ["faces", "bodies"]);
  if (!count(it)) { H.status("Select bodies or faces first (Bodies, Faces)", true); return; }
  let n = 0;
  for (const [kind, id] of suppressTargets(H, it)) {
    const r = H.suppressCfg(kind, id);
    if (!r) continue;
    const [o, k, def] = r;
    if (on && o[k] !== "off") { o.prev_off = o[k] || def; o[k] = "off"; n++; }
    else if (!on && o[k] === "off") { o[k] = o.prev_off || def; delete o.prev_off; n++; }
  }
  if (H.changed) H.changed();
  changed(H, `${n} ${on ? "suppressed" : "unsuppressed"}`);
}
