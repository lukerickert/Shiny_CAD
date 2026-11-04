// Reference points, springs, joints and equations of the Analysis and Explicit tabs (drawgen/constraints.py).
//
// Reference point: {id, name, xyz, place: {m, pts: [{xyz} | {rp}], d: [dx, dy, dz], t, dist, n, ref}, coupling,
//                   dofs: [6 flags], faces: [face refs], edges: [edge refs], nsets: [node set ids]}
// Placement (place.m): xyz typed; point (a picked point or a reference point); normal (a point on a face and a
// distance along the face normal); between (two points, fraction t); centroid3 / circle3 (three points: centroid,
// centre of the circle through them); face (face centre); edge (edge centre: circle centre, line midpoint). Offset
// d is added (all but xyz). Picked points: reference points, member ends, vertices, mesh nodes (Show Mesh), points
// on edges and faces.
//
// Host H:
//   doc(), comps() [{id, mesh, matrix (THREE.Matrix4)}], faceRef(ref) {c, n, kind} global, edgeRef(ref) {c, kind}
//   global, refText(ref), nid(prefix), changed(), render(), draw(), status(text, isError), fmt(v), esc(s),
//   pickPoint(prompt, cb({xyz, normal?, face?})), pickFace(prompt, cb(ref), again), pickEdge(prompt, cb(ref), again),
//   sel() {kind, id} | null, select(kind, id), extraEnds (optional): text of the end kinds of the tab.
import * as THREE from "three";

export const COUPLINGS = [["rigid", "rigid (all six)"], ["kinematic", "kinematic, chosen components (RBE2)"],
                          ["distributing", "distributing (RBE3)"], ["none", "none"]];
export const METHODS = [["xyz", "typed coordinates"], ["point", "a point (picked or a reference point)"],
                        ["normal", "point on a face + distance along the normal"], ["between", "between two points"],
                        ["centroid3", "centroid of three points"], ["circle3", "centre of the circle through three points"],
                        ["face", "centre of a face"], ["edge", "centre of an edge (circle centre, line midpoint)"]];
const NPTS = { xyz: 0, point: 1, normal: 1, between: 2, centroid3: 3, circle3: 3, face: 0, edge: 0 };
export const JOINTS = [["ball", "ball (ux uy uz equal)"], ["hinge", "hinge (ux uy uz and the rotations normal to the axis equal)"],
                       ["weld", "weld (all six equal)"], ["dofs", "chosen components equal"]];
export const DOFS = ["ux", "uy", "uz", "rx", "ry", "rz"];
export const RP_COLOR = 0x7048e8, LINK_COLOR = { spring: 0x2b8a3e, joint: 0xe8590c, eq: 0x495057 };

// ------------------------------------------------------------------ geometry

const V = a => new THREE.Vector3(a[0], a[1], a[2]);
function circumcentre(a, b, c) {
  const A = V(a), B = V(b), C = V(c);
  const ab = B.clone().sub(A), ac = C.clone().sub(A);
  const n = ab.clone().cross(ac), n2 = n.lengthSq();
  if (n2 < 1e-12 * Math.max(ab.lengthSq() * ac.lengthSq(), 1e-30)) return null;
  const t1 = n.clone().cross(ab).multiplyScalar(ac.lengthSq()), t2 = ac.clone().cross(n).multiplyScalar(ab.lengthSq());
  return A.add(t1.add(t2).multiplyScalar(1 / (2 * n2))).toArray();
}
function ptXyz(H, q) {
  if (!q) return null;
  if (q.rp !== undefined) { const r = (H.doc().points || []).find(x => x.id === q.rp); return r && r.xyz ? r.xyz : null; }
  return q.xyz && q.xyz.length === 3 && q.xyz.every(v => isFinite(Number(v))) ? q.xyz.map(Number) : null;
}
/** Coordinates of a reference point from its placement, or null (inputs missing). */
export function placeXyz(H, p) {
  const pl = p.place || { m: "xyz" };
  if (pl.m === "xyz") return p.xyz || null;
  const P = (pl.pts || []).map(q => ptXyz(H, q));
  let x = null;
  if (pl.m === "point") x = P[0];
  else if (pl.m === "normal") x = P[0] && pl.n ? V(P[0]).addScaledVector(V(pl.n).normalize(), Number(pl.dist) || 0).toArray() : null;
  else if (pl.m === "between") { const t = pl.t === undefined || pl.t === "" ? 0.5 : Number(pl.t); x = P[0] && P[1] ? V(P[0]).lerp(V(P[1]), t).toArray() : null; }
  else if (pl.m === "centroid3") x = P[0] && P[1] && P[2] ? V(P[0]).add(V(P[1])).add(V(P[2])).multiplyScalar(1 / 3).toArray() : null;
  else if (pl.m === "circle3") x = P[0] && P[1] && P[2] ? circumcentre(P[0], P[1], P[2]) : null;
  else if (pl.m === "face") {
    const r = pl.ref && H.faceRef(pl.ref);
    if (r && r.kind === "cylinder" && r.p && r.n) { const n = V(r.n).normalize(); x = V(r.p).addScaledVector(n, V(r.c).sub(V(r.p)).dot(n)).toArray(); }
    else x = r ? r.c : null;
  }
  else if (pl.m === "edge") { const r = pl.ref && H.edgeRef(pl.ref); x = r ? r.c : null; }
  if (!x) return null;
  const d = (pl.d || [0, 0, 0]).map(v => Number(v) || 0);
  return x.map((v, i) => Math.round((v + d[i]) * 1e6) / 1e6);
}
/** Recomputes the coordinates of all reference points (points placed from other points follow them). */
export function updatePoints(H) {
  const pts = H.doc().points || [];
  for (let pass = 0; pass < pts.length + 1; pass++) {
    let moved = false;
    for (const p of pts) {
      if (!p.place || p.place.m === "xyz") continue;
      const x = placeXyz(H, p);
      if (x && (!p.xyz || x.some((v, i) => Math.abs(v - p.xyz[i]) > 1e-9))) { p.xyz = x; moved = true; }
    }
    if (!moved) break;
  }
}

/** The point to pick near the cursor. ctx: {x, y, camera, rect, points: [{xyz, label}], comps: [{id, mesh, matrix}],
 *  mesh: {pos (Float32Array), tri (null: not indexed), faceIndex} | null (the mesh triangle under the cursor), face: {xyz, normal,
 *  ref} | null}. Order: listed points and vertices and mesh nodes within 10 px, a point on an edge within 8 px, the
 *  face point. Vertices and edge points behind the face under the cursor are left out. Returns {xyz, kind, label,
 *  normal?, face?} or null. */
export function snapPoint(ctx) {
  const v = new THREE.Vector3();
  // vertices and edge points behind the face under the cursor are not taken (depth along the view direction beyond
  // the face point + 0.2 % of the visible height)
  const cam = ctx.camera, vd = cam.getWorldDirection(new THREE.Vector3()), cp = cam.getWorldPosition(new THREE.Vector3());
  const depth = p => (p[0] - cp.x) * vd.x + (p[1] - cp.y) * vd.y + (p[2] - cp.z) * vd.z;
  const visH = cam.isOrthographicCamera ? (cam.top - cam.bottom) / (cam.zoom || 1) : 1000;
  const fd = ctx.face ? depth(ctx.face.xyz) : null, dtol = 2e-3 * visH;
  const hidden = p => fd !== null && depth(p) > fd + dtol;
  const scr = (p, M) => { v.set(p[0], p[1], p[2]); if (M) v.applyMatrix4(M); v.project(ctx.camera); return [(v.x + 1) / 2 * ctx.rect.width + ctx.rect.left, (1 - v.y) / 2 * ctx.rect.height + ctx.rect.top, v.z]; };
  let best = null;
  const offer = (xyz, kind, label, d, z) => { if (d <= 10 && (!best || d < best.d - 0.5 || (Math.abs(d - best.d) <= 0.5 && z < best.z))) best = { xyz, kind, label, d, z }; };
  for (const q of ctx.points || []) { const s = scr(q.xyz); offer(q.xyz.slice(), q.kind || "point", q.label, Math.hypot(s[0] - ctx.x, s[1] - ctx.y), s[2]); }
  for (const c of ctx.comps || []) {
    const m = c.mesh;
    if (!m || !m.edges) continue;
    for (const pl of m.edges) for (const q of [pl[0], pl[pl.length - 1]]) {
      const s = scr(q, c.matrix), g = V(q).applyMatrix4(c.matrix).toArray();
      if (!hidden(g)) offer(g, "vertex", "vertex", Math.hypot(s[0] - ctx.x, s[1] - ctx.y), s[2]);
    }
  }
  if (ctx.mesh) {
    const { pos, tri, faceIndex } = ctx.mesh;
    for (let k = 0; k < 3; k++) {
      const n = tri ? tri[3 * faceIndex + k] : 3 * faceIndex + k, q = [pos[3 * n], pos[3 * n + 1], pos[3 * n + 2]], s = scr(q);
      offer(q, "node", "mesh node", Math.hypot(s[0] - ctx.x, s[1] - ctx.y), s[2]);
    }
  }
  if (best) return best;
  // a point on an edge polyline within 8 px
  let eb = null;
  for (const c of ctx.comps || []) {
    const m = c.mesh;
    if (!m || !m.edges) continue;
    for (const pl of m.edges) {
      let prev = null, pq = null;
      for (const q of pl) {
        const s = scr(q, c.matrix);
        if (prev) {
          const dx = s[0] - prev[0], dy = s[1] - prev[1], L2 = dx * dx + dy * dy;
          const t = L2 > 0 ? Math.max(0, Math.min(1, ((ctx.x - prev[0]) * dx + (ctx.y - prev[1]) * dy) / L2)) : 0;
          const d = Math.hypot(prev[0] + t * dx - ctx.x, prev[1] + t * dy - ctx.y), z = prev[2] + t * (s[2] - prev[2]);
          if (d <= 8 && (!eb || d < eb.d - 0.5 || (Math.abs(d - eb.d) <= 0.5 && z < eb.z))) {
            const g = V(pq).lerp(V(q), t).applyMatrix4(c.matrix).toArray();
            if (!hidden(g)) eb = { xyz: g, kind: "edge", label: "point on an edge", d, z };
          }
        }
        prev = s; pq = q;
      }
    }
  }
  if (eb) return eb;
  if (ctx.face) return { xyz: ctx.face.xyz, kind: "face", label: "point on a face", normal: ctx.face.normal, face: ctx.face.ref };
  return null;
}

// ------------------------------------------------------------------ panels

const num = v => { const x = parseFloat(String(v).replace(",", ".")); return isFinite(x) ? x : null; };
function v3(H, id, a, ro) {
  return `<span class="rp-v3">${[0, 1, 2].map(i => `<input type="text" class="numf" data-v3="${id}" data-i="${i}" value="${a && a[i] !== undefined && a[i] !== null ? H.esc(H.fmt(a[i])) : ""}"${ro ? " readonly" : ""} style="width:64px">`).join("")}</span>`;
}
function read3(box, id) {
  const out = [0, 1, 2].map(i => num(box.querySelector(`[data-v3="${id}"][data-i="${i}"]`).value));
  return out.every(v => v !== null) ? out : null;
}
function flagsHtml(H, key, f) {
  return DOFS.map((n, i) => `<label class="check inline"><input type="checkbox" data-flag="${key}" data-i="${i}"${f[i] ? " checked" : ""}> ${n}</label>`).join("");
}
function readFlags(box, key) { return [...box.querySelectorAll(`[data-flag="${key}"]`)].map(x => x.checked ? 1 : 0); }
const pointName = (H, id) => { const p = (H.doc().points || []).find(x => x.id === id); return p ? p.name : "(deleted point)"; };
function endText(H, e) {
  if (!e) return "ground";
  if (e.point !== undefined) return pointName(H, e.point);
  if (e.at) return `node at (${e.at.map(v => H.fmt(v)).join(", ")})`;
  return "(pick)";
}
function itemList(H, kind, items, text) {
  const s = H.sel() || {};
  return items.map(x => `<div class="rp-item${s.kind === kind && s.id === x.id ? " sel" : ""}" data-pick="${kind}" data-id="${H.esc(x.id)}"><span>${H.esc(x.name)}</span><span class="hint">${H.esc(text(x))}</span><button type="button" class="small" data-del="${kind}" data-id="${H.esc(x.id)}" title="Delete">&#10005;</button></div>`).join("");
}
function bindList(H, box, kind, key) {
  box.querySelectorAll(`[data-pick="${kind}"]`).forEach(el => el.onclick = ev => {
    if (ev.target.dataset.del) return;
    const s = H.sel() || {};
    H.select(s.kind === kind && s.id === el.dataset.id ? null : kind, el.dataset.id);
  });
  box.querySelectorAll(`[data-del="${kind}"]`).forEach(b => b.onclick = () => {
    const d = H.doc();
    d[key] = (d[key] || []).filter(x => x.id !== b.dataset.id);
    if (kind === "rp") cleanRefs(H, b.dataset.id);
    H.changed(); H.render(); H.draw();
  });
}
/** References to a deleted reference point: placements become typed coordinates; ends of springs, joints and
 *  equations are cleared. */
function cleanRefs(H, id) {
  const d = H.doc();
  for (const p of d.points || []) if (p.place && (p.place.pts || []).some(q => q && q.rp === id)) p.place = { m: "xyz" };
  const fix = e => (e && e.point === id ? null : e);
  for (const s of d.springs || []) { s.a = fix(s.a) || { at: null }; if (s.b) s.b = fix(s.b) || { at: null }; }
  for (const j of d.joints || []) { j.a = fix(j.a) || { at: null }; j.b = fix(j.b) || { at: null }; }
  for (const q of d.equations || []) for (const t of q.terms || []) t.end = fix(t.end) || { at: null };
}

function pointSlot(H, p, i) {
  const q = (p.place.pts || [])[i] || {};
  const opts = `<option value="">picked point</option>` + (H.doc().points || []).filter(x => x.id !== p.id).map(x => `<option value="${H.esc(x.id)}"${q.rp === x.id ? " selected" : ""}>${H.esc(x.name)}</option>`).join("");
  return `<div class="rp-slot">P${i + 1} <select data-slot="${i}">${opts}</select>${q.rp === undefined ? v3(H, "pt" + i, q.xyz) + `<button type="button" class="small" data-pickpt="${i}">Pick</button>` : ""}</div>`;
}

export function renderPoints(H, box) {
  const d = H.doc();
  d.points = d.points || [];
  updatePoints(H);
  const s = H.sel() || {};
  const p = s.kind === "rp" && d.points.find(x => x.id === s.id);
  const summary = x => `${x.xyz ? "(" + x.xyz.map(v => H.fmt(v)).join(", ") + ") mm" : "no coordinates"}, ${(COUPLINGS.find(c => c[0] === (x.coupling || "rigid")) || ["", ""])[0]}` +
    ((x.coupling || "rigid") !== "none" ? `: ${(x.faces || []).length} face(s), ${(x.edges || []).length} edge(s), ${(x.nsets || []).length} node set(s)` : "");
  let h = `<div class="buttons sm-tools"><button type="button" class="small" data-rpa="add">Add reference point</button></div>` +
    itemList(H, "rp", d.points, summary);
  if (!d.points.length) h += `<p class="hint">A reference point is a node coupled to the nodes of faces, edges and node sets (rigid, kinematic or distributing) or not coupled. Supports and loads act on it; springs, joints and equations connect it.</p>`;
  if (p) {
    p.place = p.place || { m: "xyz" };
    const pl = p.place, m = pl.m;
    h += `<div class="fa-props rp-props"><label>Name<input type="text" data-rp="name" value="${H.esc(p.name)}"></label>` +
      `<label>Location<select data-rp="m">${METHODS.map(([v, t]) => `<option value="${v}"${m === v ? " selected" : ""}>${t}</option>`).join("")}</select></label>`;
    if (m === "xyz") h += `<div class="rp-slot">x y z (mm) ${v3(H, "xyz", p.xyz)}<button type="button" class="small" data-rpa="pickxyz">Pick</button></div>`;
    for (let i = 0; i < (NPTS[m] || 0); i++) h += pointSlot(H, p, i);
    if (m === "normal") h += `<div class="rp-slot">Normal ${v3(H, "n", pl.n)} <label class="inline">Distance (mm)<input type="text" class="numf" data-rp="dist" value="${H.esc(pl.dist === undefined ? 0 : pl.dist)}" style="width:64px"></label></div><p class="hint">Pick P1 on a face: the normal of the face at the point is taken.</p>`;
    if (m === "between") h += `<label class="inline">Fraction t from P1 to P2<input type="text" class="numf" data-rp="t" value="${H.esc(pl.t === undefined ? 0.5 : pl.t)}" style="width:56px"></label>`;
    if (m === "face" || m === "edge") h += `<div class="rp-slot">${pl.ref ? H.esc(H.refText(pl.ref)) : "(none)"} <button type="button" class="small" data-rpa="pickref">Pick ${m}</button></div>`;
    if (m !== "xyz") h += `<div class="rp-slot">Offset dx dy dz (mm) ${v3(H, "d", pl.d || [0, 0, 0])}</div><div class="rp-slot">x y z (mm) ${v3(H, "res", p.xyz, true)}</div>`;
    const cp = p.coupling || "rigid";
    h += `<label>Coupling<select data-rp="coupling">${COUPLINGS.map(([v, t]) => `<option value="${v}"${cp === v ? " selected" : ""}>${t}</option>`).join("")}</select></label>`;
    if (cp === "kinematic" || cp === "distributing") h += `<div class="rp-slot">Components ${flagsHtml(H, "rpd", p.dofs || [1, 1, 1, 0, 0, 0])}</div>`;
    if (cp !== "none") {
      const ns = d.nsets || [];
      h += `<div class="rp-slot">Faces: ${(p.faces || []).length} <button type="button" class="small" data-rpa="faces">Add faces</button> Edges: ${(p.edges || []).length} <button type="button" class="small" data-rpa="edges">Add edges</button> <button type="button" class="small" data-rpa="clear">Clear</button></div>` +
        (ns.length ? `<div class="rp-slot">Node sets ${ns.map(x => `<label class="check inline"><input type="checkbox" data-rpns="${H.esc(x.id)}"${(p.nsets || []).includes(x.id) ? " checked" : ""}> ${H.esc(x.name)}</label>`).join("")}</div>` : "");
    }
    h += `</div>`;
  }
  box.innerHTML = h;
  box.querySelector('[data-rpa="add"]').onclick = () => {
    const np = { id: H.nid("p"), name: "RP " + (d.points.length + 1), xyz: null, place: { m: "point", pts: [{}], d: [0, 0, 0] }, coupling: "none", faces: [], edges: [], nsets: [] };
    d.points.push(np);
    H.select("rp", np.id);
    H.changed();
    H.pickPoint(`${np.name}: click the point (Esc: type it)`, hit => { np.place.pts = [{ xyz: hit.xyz }]; if (hit.normal) np.place.n = hit.normal; updatePoints(H); });
  };
  bindList(H, box, "rp", "points");
  if (!p) return;
  const pl = p.place;
  const upd = () => { updatePoints(H); H.changed(); H.render(); H.draw(); };
  box.querySelectorAll("[data-rp]").forEach(el => el.onchange = () => {
    const k = el.dataset.rp;
    if (k === "name") p.name = el.value.trim() || p.name;
    else if (k === "m") {
      const keep = (pl.pts || []).slice();
      if (el.value === "xyz") { p.place = { m: "xyz" }; }
      else { p.place = Object.assign({}, pl, { m: el.value, pts: Array.from({ length: NPTS[el.value] || 0 }, (_, i) => keep[i] || {}), d: pl.d || [0, 0, 0] }); }
    } else if (k === "dist" || k === "t") { const v = num(el.value); if (v !== null) pl[k] = v; }
    else if (k === "coupling") { p.coupling = el.value; if ((el.value === "kinematic" || el.value === "distributing") && !p.dofs) p.dofs = [1, 1, 1, 0, 0, 0]; }
    upd();
  });
  box.querySelectorAll("[data-v3]").forEach(el => el.onchange = () => {
    const id = el.dataset.v3, a = read3(box, id);
    if (!a) return;
    if (id === "xyz") p.xyz = a;
    else if (id === "d") pl.d = a;
    else if (id === "n") pl.n = a;
    else if (id.startsWith("pt")) { pl.pts = pl.pts || []; pl.pts[+id.slice(2)] = { xyz: a }; }
    upd();
  });
  box.querySelectorAll("[data-slot]").forEach(el => el.onchange = () => { pl.pts = pl.pts || []; pl.pts[+el.dataset.slot] = el.value ? { rp: el.value } : { xyz: ptXyz(H, pl.pts[+el.dataset.slot]) || null }; upd(); });
  box.querySelectorAll("[data-pickpt]").forEach(b => b.onclick = () => {
    const i = +b.dataset.pickpt;
    H.pickPoint(`${p.name}: click P${i + 1}`, hit => { pl.pts = pl.pts || []; pl.pts[i] = { xyz: hit.xyz }; if (pl.m === "normal" && hit.normal) pl.n = hit.normal; updatePoints(H); });
  });
  box.querySelectorAll("[data-flag=rpd]").forEach(el => el.onchange = () => { p.dofs = readFlags(box, "rpd"); upd(); });
  box.querySelectorAll("[data-rpns]").forEach(el => el.onchange = () => {
    const id = el.dataset.rpns;
    p.nsets = (p.nsets || []).filter(x => x !== id);
    if (el.checked) p.nsets.push(id);
    upd();
  });
  const act = (k, fn) => { const b = box.querySelector(`[data-rpa="${k}"]`); if (b) b.onclick = fn; };
  act("pickxyz", () => H.pickPoint(`${p.name}: click the point`, hit => { p.xyz = hit.xyz; }));
  act("pickref", () => (pl.m === "face" ? H.pickFace : H.pickEdge)(`${p.name}: click the ${pl.m}`, ref => { pl.ref = ref; updatePoints(H); }));
  const addRefs = (kind) => {
    if (H.collect) {                                 // the selection (viewsel.js): faces and edges, bodies as their faces
      H.collect({ text: `${p.name}: ${kind === "faces" ? "faces or bodies" : "edges"} to couple`, types: kind === "faces" ? ["faces", "bodies"] : ["edges"], expand: true, cb: it => {
        for (const [k, key] of [["faces", "face"], ["edges", "edge"]]) {
          p[k] = p[k] || [];
          for (const ref of it[k]) if (!p[k].some(r => r.comp === ref.comp && r[key] === ref[key])) p[k].push(ref);
        }
        upd();
      } });
      return;
    }
    const pick = kind === "faces" ? H.pickFace : H.pickEdge;
    const more = () => pick(`${p.name}: click a ${kind === "faces" ? "face" : "edge"} to couple (Esc ends)`, ref => {
      p[kind] = p[kind] || [];
      const k = kind === "faces" ? "face" : "edge";
      if (!p[kind].some(r => r.comp === ref.comp && r[k] === ref[k])) p[kind].push(ref);
      setTimeout(more, 0);
    });
    more();
  };
  act("faces", () => addRefs("faces"));
  act("edges", () => addRefs("edges"));
  act("clear", () => { p.faces = []; p.edges = []; p.nsets = []; upd(); });
}

/** End selector of a spring, joint or equation term: a reference point or the mesh node nearest to a point. */
function endHtml(H, key, e, ground) {
  const pts = H.doc().points || [];
  const cur = e === null ? "ground" : e && e.point !== undefined ? "p:" + e.point : "at";
  let h = `<select data-end="${key}">` + (ground ? `<option value="ground"${cur === "ground" ? " selected" : ""}>ground</option>` : "") +
    pts.map(p => `<option value="p:${H.esc(p.id)}"${cur === "p:" + p.id ? " selected" : ""}>${H.esc(p.name)}</option>`).join("") +
    `<option value="at"${cur === "at" ? " selected" : ""}>mesh node at a point</option></select>`;
  if (cur === "at") h += v3(H, "at_" + key, e && e.at) + `<button type="button" class="small" data-endpick="${key}">Pick</button>`;
  return h;
}
function bindEnds(H, box, get, set, prompt) {
  box.querySelectorAll("[data-end]").forEach(el => el.onchange = () => {
    const k = el.dataset.end, v = el.value;
    set(k, v === "ground" ? null : v === "at" ? { at: (get(k) || {}).at || null } : { point: v.slice(2) });
    H.changed(); H.render(); H.draw();
  });
  box.querySelectorAll("[data-v3^=at_]").forEach(el => el.onchange = () => {
    const k = el.dataset.v3.slice(3), a = read3(box, el.dataset.v3);
    if (a) { set(k, { at: a }); H.changed(); H.render(); H.draw(); }
  });
  box.querySelectorAll("[data-endpick]").forEach(b => b.onclick = () => {
    const k = b.dataset.endpick;
    H.pickPoint(prompt(k), hit => set(k, { at: hit.xyz }));
  });
}
const defEnd = H => { const p = (H.doc().points || [])[0]; return p ? { point: p.id } : { at: null }; };

export function renderSprings(H, box) {
  const d = H.doc();
  d.springs = d.springs || [];
  const s = H.sel() || {};
  const sp = s.kind === "spring" && d.springs.find(x => x.id === s.id);
  let h = `<div class="buttons sm-tools"><button type="button" class="small" data-sa="add">Add spring</button></div>` +
    itemList(H, "spring", d.springs, x => `${endText(H, x.a)} to ${endText(H, x.b)}`);
  if (!d.springs.length) h += `<p class="hint">Spring between two reference points or mesh nodes, or to ground: stiffnesses kx ky kz (N/mm) and krx kry krz (N mm/rad) in the global axes.</p>`;
  if (sp) {
    const k = (sp.k || []).concat([0, 0, 0, 0, 0, 0]).slice(0, 6);
    h += `<div class="fa-props rp-props"><label>Name<input type="text" data-s="name" value="${H.esc(sp.name)}"></label>` +
      `<div class="rp-slot">End A ${endHtml(H, "a", sp.a, false)}</div><div class="rp-slot">End B ${endHtml(H, "b", sp.b, true)}</div>` +
      `<div class="rp-slot">${DOFS.map((n, i) => `<label class="inline">k${n.slice(1)} ${i < 3 ? "(N/mm)" : "(N mm/rad)"}<input type="text" class="numf" data-k="${i}" value="${H.esc(k[i] || "")}" placeholder="0" style="width:64px"></label>`).join("")}</div>` +
      `<p class="hint">Rotational stiffnesses need rotations at both ends (reference points; Explicit: also shell nodes). Explicit: /PROP/TYPE13 spring (local axes of the spring for ends apart).</p></div>`;
  }
  box.innerHTML = h;
  box.querySelector('[data-sa="add"]').onclick = () => {
    const x = { id: H.nid("k"), name: "Spring " + (d.springs.length + 1), a: defEnd(H), b: null, k: [0, 0, 1000, 0, 0, 0] };
    d.springs.push(x); H.select("spring", x.id); H.changed();
  };
  bindList(H, box, "spring", "springs");
  if (!sp) return;
  box.querySelector('[data-s="name"]').onchange = e => { sp.name = e.target.value.trim() || sp.name; H.changed(); H.render(); };
  box.querySelectorAll("[data-k]").forEach(el => el.onchange = () => { sp.k = [0, 1, 2, 3, 4, 5].map(i => num(box.querySelector(`[data-k="${i}"]`).value) || 0); H.changed(); H.render(); });
  bindEnds(H, box, k => sp[k], (k, v) => { sp[k] = v; }, k => `${sp.name}: click end ${k.toUpperCase()}`);
}

export function renderJoints(H, box) {
  const d = H.doc();
  d.joints = d.joints || [];
  const s = H.sel() || {};
  const j = s.kind === "joint" && d.joints.find(x => x.id === s.id);
  let h = `<div class="buttons sm-tools"><button type="button" class="small" data-ja="add">Add joint</button></div>` +
    itemList(H, "joint", d.joints, x => `${x.type || "ball"}: ${endText(H, x.a)} to ${endText(H, x.b)}`);
  if (!d.joints.length) h += `<p class="hint">Joint between two reference points (or mesh nodes for ball and translations): ball, hinge about an axis, weld, or chosen components equal (CalculiX *EQUATION; Radioss /MPC).</p>`;
  if (j) {
    h += `<div class="fa-props rp-props"><label>Name<input type="text" data-j="name" value="${H.esc(j.name)}"></label>` +
      `<label>Type<select data-j="type">${JOINTS.map(([v, t]) => `<option value="${v}"${(j.type || "ball") === v ? " selected" : ""}>${t}</option>`).join("")}</select></label>` +
      `<div class="rp-slot">End A ${endHtml(H, "a", j.a, false)}</div><div class="rp-slot">End B ${endHtml(H, "b", j.b, false)}</div>` +
      (j.type === "hinge" ? `<div class="rp-slot">Axis ${v3(H, "axis", j.axis || [0, 0, 1])}<button type="button" class="small" data-ja="axisedge" title="Direction of a straight edge, or the axis of a circular edge">From edge</button></div>` : "") +
      (j.type === "dofs" ? `<div class="rp-slot">${flagsHtml(H, "jd", j.dofs || [1, 1, 1, 0, 0, 0])}</div>` : "") + `</div>`;
  }
  box.innerHTML = h;
  box.querySelector('[data-ja="add"]').onclick = () => {
    const pts = d.points || [];
    const x = { id: H.nid("j"), name: "Joint " + (d.joints.length + 1), type: "ball", a: pts[0] ? { point: pts[0].id } : { at: null }, b: pts[1] ? { point: pts[1].id } : { at: null }, axis: [0, 0, 1] };
    d.joints.push(x); H.select("joint", x.id); H.changed();
  };
  bindList(H, box, "joint", "joints");
  if (!j) return;
  box.querySelectorAll("[data-j]").forEach(el => el.onchange = () => {
    if (el.dataset.j === "name") j.name = el.value.trim() || j.name; else j.type = el.value;
    H.changed(); H.render();
  });
  box.querySelectorAll("[data-v3=axis]").forEach(el => el.onchange = () => { const a = read3(box, "axis"); if (a && a.some(v => v)) { j.axis = a; H.changed(); H.render(); H.draw(); } });
  box.querySelectorAll("[data-flag=jd]").forEach(el => el.onchange = () => { j.dofs = readFlags(box, "jd"); H.changed(); H.render(); });
  const ae = box.querySelector('[data-ja="axisedge"]');
  if (ae) ae.onclick = () => H.pickEdge(`${j.name}: click the edge of the axis`, ref => { const r = H.edgeRef(ref); if (r && r.dir) j.axis = r.dir.map(v => Math.round(v * 1e6) / 1e6); else H.status("No direction for this edge", true); });
  bindEnds(H, box, k => j[k], (k, v) => { j[k] = v; }, k => `${j.name}: click end ${k.toUpperCase()}`);
}

export function renderEquations(H, box) {
  const d = H.doc();
  d.equations = d.equations || [];
  const s = H.sel() || {};
  const q = s.kind === "eq" && d.equations.find(x => x.id === s.id);
  const txt = x => (x.terms || []).map((t, i) => `${i ? (Number(t.coef) < 0 ? " - " : " + ") : Number(t.coef) < 0 ? "-" : ""}${H.fmt(Math.abs(Number(t.coef) || 0))} ${endText(H, t.end)} ${DOFS[(t.dof || 1) - 1]}`).join("") + " = 0";
  let h = `<div class="buttons sm-tools"><button type="button" class="small" data-qa="add">Add equation</button></div>` + itemList(H, "eq", d.equations, txt);
  if (!d.equations.length) h += `<p class="hint">Linear equation sum coef x component = 0 between reference points and mesh nodes (CalculiX *EQUATION; Radioss /MPC).</p>`;
  if (q) {
    h += `<div class="fa-props rp-props"><label>Name<input type="text" data-q="name" value="${H.esc(q.name)}"></label><table class="pc-table rp-terms"><tr><th>Coefficient</th><th>Point</th><th>Component</th><th></th></tr>` +
      (q.terms || []).map((t, i) => `<tr data-term="${i}"><td><input type="text" class="numf" data-tc="${i}" value="${H.esc(t.coef)}" style="width:56px"></td><td>${endHtml(H, "t" + i, t.end, false)}</td>` +
        `<td><select data-td="${i}">${DOFS.map((n, k) => `<option value="${k + 1}"${(t.dof || 1) === k + 1 ? " selected" : ""}>${n}</option>`).join("")}</select></td><td><button type="button" class="small" data-tdel="${i}">&#10005;</button></td></tr>`).join("") +
      `</table><button type="button" class="small" data-qa="term">Add term</button></div>`;
  }
  box.innerHTML = h;
  box.querySelector('[data-qa="add"]').onclick = () => {
    const pts = d.points || [], e2 = pts[1] ? { point: pts[1].id } : defEnd(H);
    const x = { id: H.nid("q"), name: "Equation " + (d.equations.length + 1), terms: [{ end: defEnd(H), dof: 1, coef: 1 }, { end: e2, dof: 1, coef: -1 }] };
    d.equations.push(x); H.select("eq", x.id); H.changed();
  };
  bindList(H, box, "eq", "equations");
  if (!q) return;
  box.querySelector('[data-q="name"]').onchange = e => { q.name = e.target.value.trim() || q.name; H.changed(); H.render(); };
  box.querySelectorAll("[data-tc]").forEach(el => el.onchange = () => { const v = num(el.value); if (v !== null) q.terms[+el.dataset.tc].coef = v; H.changed(); H.render(); });
  box.querySelectorAll("[data-td]").forEach(el => el.onchange = () => { q.terms[+el.dataset.td].dof = +el.value; H.changed(); H.render(); });
  box.querySelectorAll("[data-tdel]").forEach(b => b.onclick = () => { q.terms.splice(+b.dataset.tdel, 1); H.changed(); H.render(); H.draw(); });
  box.querySelector('[data-qa="term"]').onclick = () => { q.terms.push({ end: defEnd(H), dof: 1, coef: 1 }); H.changed(); H.render(); };
  bindEnds(H, box, k => q.terms[+k.slice(1)].end, (k, v) => { q.terms[+k.slice(1)].end = v; }, k => `${q.name}: click the point of term ${+k.slice(1) + 1}`);
}

// ------------------------------------------------------------------ view

/** Reference points (violet octahedra), their coupling (dashed lines to the centres of the faces and edges), springs
 *  (green), joints (orange) and equations (grey dashed) between their ends. Ends at a mesh node: the point. */
export function drawConstraints(H, group, track, size) {
  const d = H.doc(), s = H.sel() || {}, r = size / 120;
  const pts = d.points || [];
  const at = e => !e ? null : e.point !== undefined ? ((pts.find(p => p.id === e.point) || {}).xyz || null) : e.at || null;
  const line = (a, b, color, dashed, ud) => {
    const g = track(new THREE.BufferGeometry());
    g.setAttribute("position", new THREE.Float32BufferAttribute([...a, ...b], 3));
    const l = new THREE.Line(g, dashed ? new THREE.LineDashedMaterial({ color, dashSize: r * 2, gapSize: r * 1.2 }) : new THREE.LineBasicMaterial({ color }));
    if (dashed) l.computeLineDistances();
    l.userData = ud || {};
    l.renderOrder = 7;
    group.add(l);
  };
  for (const p of pts) {
    if (!p.xyz) continue;
    const sel = (s.kind === "rp" && s.id === p.id) || !!(H.selPoints && H.selPoints().has(p.id));
    const m = new THREE.Mesh(track(new THREE.OctahedronGeometry(r * 2.4)), new THREE.MeshStandardMaterial({ color: sel ? 0xf08c00 : RP_COLOR }));
    m.position.set(...p.xyz);
    m.userData = { kind: "rp", id: p.id };
    m.renderOrder = 8;
    group.add(m);
    if (H.pickables) H.pickables.push(m);
    if ((p.coupling || "rigid") === "none") continue;
    for (const fr of p.faces || []) { const f = H.faceRef(fr); if (f) line(p.xyz, f.c, RP_COLOR, true); }
    for (const er of p.edges || []) { const e = H.edgeRef(er); if (e) line(p.xyz, e.c, RP_COLOR, true); }
  }
  for (const sp of d.springs || []) {
    const a = at(sp.a), b = sp.b ? at(sp.b) : (a ? [a[0], a[1], a[2] - size / 20] : null);
    if (a && b) line(a, b, s.kind === "spring" && s.id === sp.id ? 0xf08c00 : LINK_COLOR.spring, !sp.b, { kind: "spring", id: sp.id });
  }
  for (const j of d.joints || []) {
    const a = at(j.a), b = at(j.b);
    if (!a || !b) continue;
    const sel = s.kind === "joint" && s.id === j.id;
    if (Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) > 1e-9) line(a, b, sel ? 0xf08c00 : LINK_COLOR.joint, false, { kind: "joint", id: j.id });
    const t = new THREE.Mesh(track(new THREE.TorusGeometry(r * 3, r * 0.5, 6, 16)), new THREE.MeshStandardMaterial({ color: sel ? 0xf08c00 : LINK_COLOR.joint }));
    t.position.set(...b);
    if (j.type === "hinge" && j.axis) t.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), V(j.axis).normalize());
    group.add(t);
  }
  for (const q of d.equations || []) {
    const ends = (q.terms || []).map(t => at(t.end)).filter(Boolean);
    for (let k = 1; k < ends.length; k++) line(ends[0], ends[k], s.kind === "eq" && s.id === q.id ? 0xf08c00 : LINK_COLOR.eq, true, { kind: "eq", id: q.id });
  }
}
