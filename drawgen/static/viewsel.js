// Selection in the 3D views of the Analysis and Explicit tabs: type filter (faces, edges, vertices, bodies, reference
// points; on Show Mesh: mesh nodes and elements), click to select or deselect, propagation of a face or edge click
// (tangent within an angle, connected, whole body), box select and selection for a target (supports, loads, masses,
// reference point couplings, node sets, sections).
//
// The selection lives in H.sel (shellmodel.selState): faces Set("<comp>:<face>"), edges Set("<comp>:<edge>"), vertices
// Set("<comp>:<vertex>"), bodies Set(body id: component id for a solid, "<comp>:<surface id>" for a surface body),
// points Set(reference point id), nodes Set(mesh node id), elements Set(mesh element id), types Set of the types a
// click or a box takes (empty: selection off), box (left drag draws a box), collect (a selection for a target: {text,
// types, cb}), prop ("single" | "angle" | "connected" | "body": what a face or edge click adds), angle (deg).
//
// Vertices of a component: the end points of the edge polylines of its view mesh (index in the order of the edges).
// A vertex item is {comp, vertex, xyz (global)}; the analysis takes the mesh node at xyz.
//
// Host H (the shellmodel.js host) with H.view:
//   canvas(), camera(), box() (the view element), modelShown() (Show is Model), showModel() (Show Model),
//   comps() [{id, mesh {vertices, triangles, face_of_tri, face_body, edges}, matrix (THREE.Matrix4), surfaces}],
//   points() [{id, xyz}], faceAt(e) {comp, face} | null, edgeAt(e) {comp, edge} | null,
//   meshShown() (Show is Mesh), mesh() {pos (global, Float32Array), ids (node id per point), tri (Uint32Array),
//   triElem (element id per triangle)} | null, meshHit(e) {tri, point: [x, y, z]} | null (the mesh triangle under
//   the cursor)
// and H.render(), H.draw(), H.status(text, isError), H.esc(s).
//
// Box: drag to the right selects the items fully inside the box (window), drag to the left the items inside or
// crossing it (crossing). Ctrl or Alt at release: the items leave the selection. Items behind others are taken too.
import * as THREE from "three";
import { selState } from "/static/shellmodel.js";

export const TYPES = [["faces", "Faces"], ["edges", "Edges"], ["vertices", "Vertices"], ["bodies", "Bodies"], ["points", "Ref. points"],
                      ["nodes", "Nodes"], ["elements", "Elements"]];
const MESH_TYPES = new Set(["nodes", "elements"]);
const NAMES = { faces: "face(s)", edges: "edge(s)", vertices: "vertex(es)", bodies: "body(ies)", points: "reference point(s)", nodes: "mesh node(s)", elements: "element(s)" };
const PROPS = [["single", "Single"], ["angle", "Tangent"], ["connected", "Connected"], ["body", "Whole body"]];
const fkey = r => r.comp + ":" + r.face;
const ekey = r => r.comp + ":" + r.edge;
const split = k => { const i = k.lastIndexOf(":"); return [k.slice(0, i), +k.slice(i + 1)]; };
const plural = k => NAMES[k].replace("(s)", "s").replace("(ies)", "ies").replace("(es)", "es");

export function active(H) {
  const S = selState(H);
  if (!S.types.size) return false;
  if (!H.view || H.view.modelShown()) return true;
  return !!(H.view.meshShown && H.view.meshShown() && [...S.types].some(t => MESH_TYPES.has(t)));
}
/** Mesh selection (nodes, elements): Show is Mesh and a mesh type is on. */
function meshMode(H) { return !!(H.view && H.view.meshShown && H.view.meshShown() && !H.view.modelShown()); }

// ------------------------------------------------------------------ topology of the view meshes

const tkey = (p, q) => p < q ? p + "|" + q : q + "|" + p;
/** Vertices of a component mesh: the distinct end points of its edge polylines (local coordinates). */
export function compVertices(m) {
  if (m._vtx) return m._vtx;
  const out = [], seen = new Map(), bb = m.bbox || null;
  const size = bb ? Math.hypot(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]) || 1 : 1, q = 1e-6 * size;
  const k = p => p.map(v => Math.round(v / q)).join(",");
  for (const pl of m.edges || []) for (const p of [pl[0], pl[pl.length - 1]]) {
    if (!p) continue;
    const kk = k(p);
    if (!seen.has(kk)) { seen.set(kk, out.length); out.push(p); }
  }
  m._vtx = out;
  m._vtxKey = seen;
  m._vq = k;
  return out;
}
/** Face adjacency of a component mesh: Map face -> Map(neighbour face -> largest angle (deg) between the triangle
 *  normals across their common triangle edges). Faces of surface bodies: the angle between the lines of the normals. */
function faceAdjacency(m) {
  if (m._adj) return m._adj;
  const V = m.vertices, T = m.triangles, F = m.face_of_tri, fb = m.face_body || [];
  let lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (const p of V) for (let i = 0; i < 3; i++) { lo[i] = Math.min(lo[i], p[i]); hi[i] = Math.max(hi[i], p[i]); }
  const q = 1e-6 * (Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) || 1);
  const pk = i => V[i].map(v => Math.round(v / q)).join(",");
  const keys = V.map((_, i) => pk(i));
  const nrm = tr => { const a = V[tr[0]], b = V[tr[1]], c = V[tr[2]]; const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    const n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]; const l = Math.hypot(...n) || 1; return n.map(x => x / l); };
  const byEdge = new Map();
  T.forEach((tr, t) => {
    const n = nrm(tr);
    for (let j = 0; j < 3; j++) {
      const e = tkey(keys[tr[j]], keys[tr[(j + 1) % 3]]);
      if (!byEdge.has(e)) byEdge.set(e, []);
      byEdge.get(e).push([F[t], n]);
    }
  });
  const adj = new Map();
  const put = (a, b, ang) => { if (!adj.has(a)) adj.set(a, new Map()); const mm = adj.get(a); mm.set(b, Math.max(mm.get(b) || 0, ang)); };
  for (const lst of byEdge.values()) for (let i = 0; i < lst.length; i++) for (let j = i + 1; j < lst.length; j++) {
    const [fa, na] = lst[i], [fb2, nb] = lst[j];
    if (fa === fb2) continue;
    let d = na[0] * nb[0] + na[1] * nb[1] + na[2] * nb[2];
    const surf = (fb[fa] !== null && fb[fa] !== undefined) || (fb[fb2] !== null && fb[fb2] !== undefined);
    if (surf) d = Math.abs(d);
    const ang = Math.acos(Math.max(-1, Math.min(1, d))) * 180 / Math.PI;
    put(fa, fb2, ang); put(fb2, fa, ang);
  }
  m._adj = adj;
  return adj;
}
/** Faces reached from face fi: "angle" across edges with an angle up to deg, "connected" across any common edge,
 *  "body" all faces of its body. */
export function propagateFaces(c, fi, mode, deg) {
  const m = c.mesh;
  if (mode === "body") {
    const b = bodyOfFace(c, fi), out = [];
    let n = (m.face_body || []).length;
    for (const f of m.face_of_tri) if (f + 1 > n) n = f + 1;
    for (let f = 0; f < n; f++) if (bodyOfFace(c, f) === b) out.push(f);
    return out;
  }
  if (mode !== "angle" && mode !== "connected") return [fi];
  const adj = faceAdjacency(m), body = bodyOfFace(c, fi), seen = new Set([fi]), st = [fi];
  while (st.length) {
    const f = st.pop();
    for (const [g, ang] of adj.get(f) || []) {
      if (seen.has(g) || bodyOfFace(c, g) !== body) continue;
      if (mode === "angle" && ang > deg + 1e-9) continue;
      seen.add(g); st.push(g);
    }
  }
  return [...seen];
}
/** Edges reached from edge ei through their end points: "angle" where the direction turns by at most deg,
 *  "connected" / "body" all edges connected to it. */
export function propagateEdges(c, ei, mode, deg) {
  const m = c.mesh, E = m.edges || [];
  if (mode === "single" || !E[ei]) return [ei];
  compVertices(m);
  const k = m._vq;
  const ends = new Map();                    // vertex key -> [[edge, direction leaving the vertex]]
  const dir = (a, b) => { const d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]; const l = Math.hypot(...d) || 1; return d.map(x => x / l); };
  E.forEach((pl, i) => {
    if (pl.length < 2) return;
    const n = pl.length;
    for (const [p, d] of [[pl[0], dir(pl[0], pl[1])], [pl[n - 1], dir(pl[n - 1], pl[n - 2])]]) {
      const kk = k(p);
      if (!ends.has(kk)) ends.set(kk, []);
      ends.get(kk).push([i, d]);
    }
  });
  const seen = new Set([ei]), st = [ei];
  while (st.length) {
    const i = st.pop(), pl = E[i], n = pl.length;
    if (n < 2) continue;
    for (const [p, d] of [[pl[0], dir(pl[0], pl[1])], [pl[n - 1], dir(pl[n - 1], pl[n - 2])]]) {
      for (const [j, dj] of ends.get(k(p)) || []) {
        if (seen.has(j)) continue;
        // through the vertex: the angle between the arriving direction (-d) and the leaving direction of j
        const ang = Math.acos(Math.max(-1, Math.min(1, -(d[0] * dj[0] + d[1] * dj[1] + d[2] * dj[2])))) * 180 / Math.PI;
        if (mode === "angle" && ang > deg + 1e-9) continue;
        seen.add(j); st.push(j);
      }
    }
  }
  return [...seen];
}

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

/** Global coordinates of vertex vi of component c (view data). */
function vertexXyz(c, vi) {
  const p = compVertices(c.mesh)[vi];
  if (!p) return null;
  const v = new THREE.Vector3(...p);
  if (c.matrix) v.applyMatrix4(c.matrix);
  return [v.x, v.y, v.z];
}

/** The selected items of the types: {faces: [refs], edges: [refs], vertices: [{comp, vertex, xyz}], bodies: [ids],
 *  points: [ids], nodes: [ids], elements: [ids]}. expand: the faces of the selected bodies are added to the faces
 *  (bodies left empty). */
export function items(H, types, expand) {
  const S = selState(H), ok = new Set(types || TYPES.map(t => t[0]));
  const out = { faces: [], edges: [], vertices: [], bodies: [], points: [], nodes: [], elements: [] };
  if (ok.has("faces")) out.faces = [...S.faces].map(k => { const [comp, face] = split(k); return { comp, face }; });
  if (ok.has("edges")) out.edges = [...S.edges].map(k => { const [comp, edge] = split(k); return { comp, edge }; });
  if (ok.has("vertices") && S.vertices.size && H.view) {
    const comps = new Map(H.view.comps().map(c => [c.id, c]));
    for (const k of S.vertices) {
      const [comp, vertex] = split(k), c = comps.get(comp), xyz = c ? vertexXyz(c, vertex) : null;
      if (xyz) out.vertices.push({ comp, vertex, xyz });
    }
  }
  if (ok.has("nodes")) out.nodes = [...S.nodes].map(Number);
  if (ok.has("elements")) out.elements = [...S.elements].map(Number);
  if (ok.has("bodies")) {
    if (expand && ok.has("faces")) {
      const have = new Set(out.faces.map(fkey));
      for (const b of S.bodies) for (const r of facesOfBody(H, b)) if (!have.has(fkey(r))) { have.add(fkey(r)); out.faces.push(r); }
    } else out.bodies = [...S.bodies];
  }
  if (ok.has("points")) out.points = [...S.points];
  return out;
}
export function count(it) { return TYPES.reduce((a, [k]) => a + (it[k] || []).length, 0); }
export function clear(H) { const S = selState(H); for (const [k] of TYPES) S[k] = new Set(); }

function changed(H, text) { renderBar(H); H.render(); H.draw(); if (text !== undefined) H.status(text); }

/** Sets the types a click or a box takes (empty: selection off). */
export function setTypes(H, types) {
  const S = selState(H);
  S.types = new Set(types);
  const mesh = [...S.types].some(t => MESH_TYPES.has(t));
  if (mesh && H.view && H.view.showMesh && !H.view.meshShown()) H.view.showMesh();
  if (!mesh && [...S.types].length && H.view && !H.view.modelShown() && H.view.showModel) H.view.showModel();
  changed(H, S.types.size ? `Selecting ${[...S.types].map(plural).join(", ")}: click to select or deselect${S.box ? ", drag a box (to the right: inside, to the left: crossing)" : ""} (Esc ends)` : "Selection ended: " + countText(H));
}

// ------------------------------------------------------------------ toolbar

/** Selection toolbar of the view into el (the type buttons, Box, Clear, the count; Done and Cancel of a selection
 *  for a target). */
export function renderBar(H, el) {
  el = el || H.selBar;
  if (!el) return;
  H.selBar = el;
  const S = selState(H), esc = H.esc;
  let h = `<span class="vs-lbl">Select</span>` + TYPES.map(([k, t]) => `<button type="button" class="small${S.types.has(k) ? " on" : ""}" data-vs="${k}" title="${MESH_TYPES.has(k) ? "Show Mesh: clicks and boxes take " + plural(k) + " of the mesh" : "Clicks and boxes take " + plural(k)}">${t}</button>`).join("") +
    `<select class="vs-prop" data-vsp="prop" title="What a click on a face or an edge adds: the face or edge alone; the faces (edges) joined to it at an angle up to Angle; all faces (edges) connected to it; all faces of its body">` +
    PROPS.map(([k, t]) => `<option value="${k}"${S.prop === k ? " selected" : ""}>${t}</option>`).join("") + `</select>` +
    (S.prop === "angle" ? `<input type="text" class="numf vs-angle" data-vsp="angle" value="${S.angle}" style="width:36px" title="Angle (deg): faces whose normals differ by at most this across their common edge, edges whose directions turn by at most this">°` : "") +
    `<button type="button" class="small${S.box ? " on" : ""}" data-vs="box" title="Left drag draws a box: to the right the items fully inside, to the left the items inside or crossing; Ctrl or Alt: deselect">Box</button>` +
    `<button type="button" class="small" data-vs="clear" title="Clear the selection">Clear</button>` +
    (H.suppressCfg ? `<button type="button" class="small" data-vs="sup" title="Set the selected bodies, and the sections (or bodies) of the selected faces, to off: left out of the mesh and the solve">Suppress</button>` +
      `<button type="button" class="small" data-vs="unsup" title="Set the selected bodies, and the sections (or bodies) of the selected faces, back to their model before Suppress">Unsuppress</button>` : "") +
    `<span class="hint vs-count">${esc(countText(H))}</span>`;
  if (S.collect) h += `<span class="vs-collect">${esc(S.collect.text)}</span><button type="button" class="small primary" data-vs="done" title="Use the selection (Enter)">Done</button><button type="button" class="small" data-vs="cancel" title="Esc">Cancel</button>`;
  el.innerHTML = h;
  el.querySelectorAll("[data-vsp]").forEach(x => x.onchange = () => {
    if (x.dataset.vsp === "prop") S.prop = x.value;
    else { const v = parseFloat(String(x.value).replace(",", ".")); if (isFinite(v) && v >= 0 && v <= 180) S.angle = v; }
    renderBar(H);
    H.status(S.prop === "angle" ? `A face or edge click adds the faces or edges joined at up to ${S.angle}°` : S.prop === "connected" ? "A face or edge click adds all connected faces or edges" : S.prop === "body" ? "A face click adds all faces of its body" : "A click takes the face or edge alone");
  });
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
  if (H.view && !H.view.modelShown() && H.view.showModel && !(meshMode(H) && opts.types.some(t => MESH_TYPES.has(t)))) H.view.showModel();
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
  if (meshMode(H)) return meshClick(H, e);
  if (S.types.has("vertices")) {
    const vx = vertexAt(H, e);
    if (vx) { toggle(S.vertices, vx); changed(H, countText(H)); return true; }
  }
  if (S.types.has("edges")) {
    const eg = V.edgeAt(e);
    if (eg) { toggleGroup(S.edges, propEdges(H, eg).map(i => eg.comp + ":" + i), ekey(eg)); changed(H, countText(H)); return true; }
  }
  if (S.types.has("faces") || S.types.has("bodies")) {
    const f = V.faceAt(e);
    if (f) {
      if (S.types.has("faces")) toggleGroup(S.faces, propFaces(H, f).map(i => f.comp + ":" + i), fkey(f));
      else { const c = V.comps().find(x => x.id === f.comp); if (c) toggle(S.bodies, bodyOfFace(c, f.face)); }
      changed(H, countText(H));
      return true;
    }
  }
  return true;                                              // a click on empty space while selecting does nothing
}
/** A group of keys toggled by the state of the clicked key: all added, or all removed when it was selected. */
function toggleGroup(set, keys, clicked) {
  const on = !set.has(clicked);
  for (const k of keys) { if (on) set.add(k); else set.delete(k); }
}
function propFaces(H, f) {
  const S = selState(H), c = H.view.comps().find(x => x.id === f.comp);
  return c && S.prop !== "single" ? propagateFaces(c, f.face, S.prop, S.angle) : [f.face];
}
function propEdges(H, eg) {
  const S = selState(H), c = H.view.comps().find(x => x.id === eg.comp);
  return c && S.prop !== "single" ? propagateEdges(c, eg.edge, S.prop, S.angle) : [eg.edge];
}
/** Vertex key "<comp>:<vertex>" within 10 px of the cursor, the nearest. */
function vertexAt(H, e) {
  const V = H.view, r = V.canvas().getBoundingClientRect(), cam = V.camera(), v = new THREE.Vector3();
  let best = null;
  for (const c of V.comps()) {
    const vs = compVertices(c.mesh);
    vs.forEach((p, i) => {
      v.set(...p);
      if (c.matrix) v.applyMatrix4(c.matrix);
      v.project(cam);
      const d = Math.hypot((v.x + 1) / 2 * r.width + r.left - e.clientX, (1 - v.y) / 2 * r.height + r.top - e.clientY);
      if (d < 10 && (!best || d < best.d)) best = { k: c.id + ":" + i, d };
    });
  }
  return best ? best.k : null;
}
/** A click on Show Mesh: the element of the triangle under the cursor (Elements), or its node nearest to the hit
 *  point (Nodes). */
function meshClick(H, e) {
  const S = selState(H), V = H.view, md = V.mesh && V.mesh(), hit = V.meshHit && V.meshHit(e);
  if (!md || !hit) return true;
  if (S.types.has("nodes")) {
    let best = null;
    for (let j = 0; j < 3; j++) {
      const i = md.tri[3 * hit.tri + j];
      const d = Math.hypot(md.pos[3 * i] - hit.point[0], md.pos[3 * i + 1] - hit.point[1], md.pos[3 * i + 2] - hit.point[2]);
      if (!best || d < best.d) best = { i, d };
    }
    // a click near a node takes the node; else the element (when Elements is on)
    if (best && (!S.types.has("elements") || nodeNear(H, md, best.i, e))) { toggle(S.nodes, md.ids[best.i]); changed(H, countText(H)); return true; }
  }
  if (S.types.has("elements") && md.triElem) { toggle(S.elements, md.triElem[hit.tri]); changed(H, countText(H)); }
  return true;
}
function nodeNear(H, md, i, e) {
  const V = H.view, r = V.canvas().getBoundingClientRect(), v = new THREE.Vector3(md.pos[3 * i], md.pos[3 * i + 1], md.pos[3 * i + 2]).project(V.camera());
  return Math.hypot((v.x + 1) / 2 * r.width + r.left - e.clientX, (1 - v.y) / 2 * r.height + r.top - e.clientY) < 10;
}

/** View objects of the mesh selection on Show Mesh: the selected nodes (points) and elements (their triangles). */
export function meshOverlays(H) {
  const S = selState(H), V = H.view, md = V && V.mesh && V.mesh();
  if (!md || (!S.nodes.size && !S.elements.size)) return [];
  const out = [];
  if (S.elements.size && md.triElem) {
    const pos = [];
    for (let t = 0; t < md.triElem.length; t++) if (S.elements.has(md.triElem[t])) for (let j = 0; j < 3; j++) { const i = md.tri[3 * t + j]; pos.push(md.pos[3 * i], md.pos[3 * i + 1], md.pos[3 * i + 2]); }
    if (pos.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      const o = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0xf08c00, transparent: true, opacity: 0.75, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
      o.renderOrder = 6;
      out.push(o);
    }
  }
  if (S.nodes.size) {
    const pos = [];
    for (let i = 0; i < md.ids.length; i++) if (S.nodes.has(md.ids[i])) pos.push(md.pos[3 * i], md.pos[3 * i + 1], md.pos[3 * i + 2]);
    if (pos.length) out.push(pointsObject(pos, 0xe03131));
  }
  return out;
}
/** Points drawn over the model (8 px squares). */
export function pointsObject(pos, color) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  const o = new THREE.Points(g, new THREE.PointsMaterial({ color, size: 8, sizeAttenuation: false, depthTest: false }));
  o.renderOrder = 9;
  return o;
}
/** Local coordinates of the selected vertices of component cid (for the overlay of the component). */
export function selectedVertices(H, cid) {
  const S = selState(H), out = [];
  if (!S.vertices.size || !H.view) return out;
  const c = H.view.comps().find(x => x.id === cid);
  if (!c) return out;
  const vs = compVertices(c.mesh);
  for (const k of S.vertices) { const [comp, vi] = split(k); if (comp === cid && vs[vi]) out.push(...vs[vi]); }
  return out;
}

/** A click with no type on (Show Model): toggles the face under the cursor (the Faces type is the default of a
 *  plain click). Returns true when a face was toggled. */
export function quickFace(H, e) {
  const S = selState(H);
  if (S.types.size || !H.view || !H.view.modelShown()) return false;
  const f = H.view.faceAt(e);
  if (!f) return false;
  toggleGroup(S.faces, propFaces(H, f).map(i => f.comp + ":" + i), fkey(f));
  changed(H, countText(H) + " (a click selects or deselects a face; Faces, Edges, Vertices, Bodies, Ref. points for other items)");
  return true;
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
  const out = { faces: [], edges: [], vertices: [], bodies: [], points: [], nodes: [], elements: [] };
  const want = new Set(types);
  if (meshMode(H)) {                                        // Show Mesh: nodes and elements
    const md = V.mesh && V.mesh();
    if (!md) return out;
    const n = md.ids.length, P = new Array(n), Pin = new Uint8Array(n);
    for (let i = 0; i < n; i++) { P[i] = scr(md.pos[3 * i], md.pos[3 * i + 1], md.pos[3 * i + 2]); Pin[i] = inside(P[i]) ? 1 : 0; }
    if (want.has("nodes")) for (let i = 0; i < n; i++) if (Pin[i]) out.nodes.push(md.ids[i]);
    if (want.has("elements") && md.triElem) {
      const all = new Map(), any = new Map();
      for (let t = 0; t < md.triElem.length; t++) {
        const el = md.triElem[t], ii = [md.tri[3 * t], md.tri[3 * t + 1], md.tri[3 * t + 2]];
        const ins = ii.map(i => Pin[i] === 1);
        all.set(el, (all.has(el) ? all.get(el) : true) && ins.every(Boolean));
        let hit = ins.some(Boolean);
        if (!hit && crossing) { const [a, b, d] = ii.map(i => P[i]); hit = segHitsRect(a, b, R) || segHitsRect(b, d, R) || segHitsRect(d, a, R) || inTri([R.x0, R.y0], a, b, d); }
        any.set(el, any.get(el) || hit);
      }
      for (const [el, ok] of (crossing ? any : all)) if (ok) out.elements.push(el);
    }
    return out;
  }
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
    if (want.has("vertices")) compVertices(m).forEach((p, i) => { if (inside(scr(p[0], p[1], p[2], c.matrix))) out.vertices.push(c.id + ":" + i); });
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
      for (const [k] of TYPES) for (const id of got[k] || []) { n++; if (remove) S[k].delete(id); else S[k].add(id); }
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
  for (const k of ["faces", "edges", "vertices", "bodies", "nodes", "elements"]) if ((it[k] || []).length) t[k] = it[k];
  return { target: t };
}
/** Faces, edges and vertices of a target (bodies as their faces): {faces: [refs], edges: [refs], vertices: [{comp,
 *  vertex, xyz}]}. */
export function targetRefs(H, t) {
  const out = { faces: [], edges: [], vertices: [] };
  if (!t) return out;
  if (t.face !== undefined) out.faces.push(t);
  else if (t.edge !== undefined) out.edges.push(t);
  if (t.surface !== undefined) { const f = (H.doc().surfaces || []).find(x => x.id === t.surface); if (f) out.faces.push(...(f.faces || [])); }
  for (const r of t.faces || []) out.faces.push(r);
  for (const r of t.edges || []) out.edges.push(r);
  for (const r of t.vertices || []) out.vertices.push(r);
  if (H.view) for (const b of t.bodies || []) out.faces.push(...facesOfBody(H, b));
  return out;
}
/** Text of a multi-item target, or null for other targets. */
export function multiText(t) {
  if (!t || !["faces", "edges", "vertices", "bodies", "nodes", "elements"].some(k => t[k])) return null;
  const parts = [];
  for (const k of ["faces", "edges", "vertices", "bodies", "nodes", "elements"]) if ((t[k] || []).length) parts.push(t[k].length + " " + NAMES[k]);
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
  if (t.surface !== undefined) for (const r of targetRefs(H, t).faces) S.faces.add(fkey(r));
  for (const r of t.faces || []) S.faces.add(fkey(r));
  for (const r of t.edges || []) S.edges.add(ekey(r));
  for (const r of t.vertices || []) S.vertices.add(r.comp + ":" + r.vertex);
  for (const b of t.bodies || []) S.bodies.add(b);
  for (const n of t.nodes || []) S.nodes.add(n);
  for (const n of t.elements || []) S.elements.add(n);
  changed(H, countText(H));
}

// ------------------------------------------------------------------ suppress

/** Bodies and sections of the selection: selected bodies; a selected face gives its section, else its body.
 *  Returns [[kind ("body" | "shell" | "section"), id]]. */
export function suppressTargets(H, it) {
  const out = new Map(), d = H.doc();
  const add = (kind, id) => out.set(kind + "|" + id, [kind, id]);
  const comps = H.view.comps();
  const secOf = r => (d.sections || []).find(x => (x.faces || []).some(q => q.comp === r.comp && q.face === r.face));
  for (const b of it.bodies) {
    if (!b.includes(":")) { add("body", b); continue; }
    // a surface body: the sections of its faces (faces in no section: the surface body)
    let rest = false;
    for (const r of facesOfBody(H, b)) { const sec = secOf(r); if (sec) add("section", sec.id); else rest = true; }
    if (rest) add("shell", b);
  }
  for (const r of it.faces) {
    const sec = secOf(r);
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
