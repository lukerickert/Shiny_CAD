// Explicit tab: explicit analysis with OpenCourant (ORC**3 core, drawgen/explicit). Model from the ShinyCAD geometry
// (bodies, materials, supports, mesh, .inp) or an external .inp; run folders; deck build; local and remote solve; job
// status board and console; results: animation frames on the 3D view, KE/IE curves, post-processing commands.
import * as THREE from "three";
import { TumbleControls } from "/static/vendor/TumbleControls.js";
import { updateAxes } from "/static/axes.js";
import { createNavCube } from "/static/navcube.js";

const XP = { doc: null, dirty: false, meta: null, env: null, envInfo: null, three: null, geo: null, asm: null,
             bbox: null, size: 100, pick: null, sel: null,
             mesh: null, meshSummary: null,                    // view data of the model .inp (Write .inp, Show mesh)
             runs: [], runsDir: "",
             res: { folder: "", job: "", data: null, geo: null, frame: null, k: 0, playing: false },
             logSeq: 0, logLines: [], status: null, lastBuild: null, offerSeq: 0, prevRows: {}, seq: 0, timer: null };
const MESHES = new Map();
const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const fmt = (v, d = 4) => {
  if (v === null || v === undefined || !isFinite(v)) return "-";
  const a = Math.abs(v);
  if (a !== 0 && (a >= 1e6 || a < 1e-3)) return Number(v).toExponential(Math.max(1, d - 1));
  let s = Number(v).toPrecision(Math.max(d, 1));
  if (s.includes(".") && !s.includes("e")) s = s.replace(/\.?0+$/, "");
  return s === "-0" ? "0" : s;
};
const fnum = v => { const x = window.numv ? window.numv(String(v)) : parseFloat(v); return isFinite(x) ? x : NaN; };
const ROLE_COLOR = { deformable: 0x9aa7b5, rigid: 0xd08c3a, off: 0xced4da };
const PART_COLORS = [0x9aa7b5, 0xd08c3a, 0x74a9cf, 0x8fbc8f, 0xc994c7, 0xe0c068, 0x80b1d3, 0xbc80bd, 0xa6cee3, 0xfdb462];
const SEL = 0xf08c00, SUP = 0x1c7ed6;

function blankDoc(name) {
  return { name: name || "explicit", source: { kind: "shinycad", type: "assembly", name: "", inp: "" },
           materials: { "S355": { library: "Steel S355 (DNVGL 19-Point Standard)", E: 210000, nu: 0.3, rho: 7850 },
                        "Rigid": { library: "", E: 210000, nu: 0.3, rho: 7850 } },
           default_material: "S355", mesh: { size: 0, strategy: "tet", tet_type: "C3D4", hex_type: "C3D8R" }, bonded: true,
           bodies: {}, supports: [], settings: {}, next: 1 };
}
function changed() { XP.dirty = true; if (FM) FM.render(); }
/** Document setting (the ORC**3 defaults when not set). */
function S(k) { const v = (XP.doc.settings || {})[k]; return v === undefined ? (XP.meta.defaults[k]) : v; }
function setS(k, v) { XP.doc.settings = XP.doc.settings || {}; XP.doc.settings[k] = v; changed(); }
function E(k) { return XP.env ? XP.env[k] : ""; }
function srcKind() { return (XP.doc.source || {}).kind || "shinycad"; }
function isShiny() { return srcKind() === "shinycad"; }
function isDeck() { return srcKind() === "deck"; }
/** The model .inp of the document is written by Write .inp (ShinyCAD geometry or deck generator). */
function isModel() { return srcKind() !== "inp"; }
/** Request body of the server operations: the document and its settings. */
function req(extra) { return Object.assign({ name: XP.doc.name, doc: XP.doc, settings: Object.assign({}, XP.doc.settings || {}) }, extra || {}); }
function info(t) { $("#xp-info").textContent = t || ""; }

// ------------------------------------------------------------------ 3D view

function initThree() {
  const box = $("#xp-view");
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  box.appendChild(renderer.domElement);
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
  updateAxes(scene, null, true);
  XP.three = { renderer, scene, camera, controls, group, box, zoomed: false, pickables: [], geos: [] };
  controls.addEventListener("change", render3);
  camera.userData.target = controls.target;
  XP.three.cube = createNavCube(box, camera, viewDir);
  let down = null;
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; clearHover(); });
  renderer.domElement.addEventListener("pointermove", e => { if (!e.buttons) hoverView(e); });
  renderer.domElement.addEventListener("pointerleave", () => { clearHover(); render3(); });
  renderer.domElement.addEventListener("contextmenu", e => e.preventDefault());
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.abs(e.clientX - down[0]) + Math.abs(e.clientY - down[1]) > 4) { down = null; return; }
    down = null;
    if (e.button === 1) { const h = hitAt(e); if (h) { XP.three.controls.setTarget(h.point.clone(), true); render3(); } return; }
    if (e.button === 0) clickView(e);
  });
  new ResizeObserver(resize3).observe(box);
  resize3();
}
function resize3() {
  const t = XP.three;
  if (!t) return;
  const w = t.box.clientWidth || 1, h = t.box.clientHeight || 1;
  t.renderer.setSize(w, h);
  const c = t.camera, half = (c.top - c.bottom) / 2 || 100;
  c.left = -half * w / h; c.right = half * w / h;
  c.updateProjectionMatrix();
  render3();
}
function render3() { const t = XP.three; if (!t) return; t.renderer.render(t.scene, t.camera); if (t.cube) t.cube.render(); }
function viewDir(dir, up) {
  const t = XP.three;
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
  const t = XP.three;
  if (!t) return;
  const bb = XP.bbox || [-50, -50, -50, 50, 50, 50];
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
  const t = XP.three;
  const r = t.renderer.domElement.getBoundingClientRect();
  const nd = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster();
  rc.setFromCamera(nd, t.camera);
  return rc;
}
function hitAt(e) { const h = rayAt(e).intersectObjects(XP.three.pickables, false); return h.length ? h[0] : null; }
function clearHover() {
  const t = XP.three;
  if (!t || !t.hover) return;
  t.scene.remove(t.hover);
  t.hover = null;
  t.renderer.domElement.style.cursor = "";
}
function faceTris(c, fi) {
  const m = c.mesh, pos = [];
  m.triangles.forEach((tr, k) => { if (m.face_of_tri[k] === fi) for (const v of tr) pos.push(...m.vertices[v]); });
  return pos;
}
function hoverView(e) {
  const t = XP.three;
  if (!t || !XP.doc) return;
  clearHover();
  if (!XP.pick || $("#xp-show").value !== "model") { render3(); return; }
  const h = rayAt(e).intersectObjects(t.pickables, false).find(x => x.object.userData && x.object.userData.comp !== undefined);
  const c = h && compOf(h.object.userData.comp);
  const fi = c && c.mesh ? c.mesh.face_of_tri[h.faceIndex] : null;
  if (fi !== null && fi !== undefined) {
    const fg = new THREE.BufferGeometry();
    fg.setAttribute("position", new THREE.Float32BufferAttribute(faceTris(c, fi), 3));
    const fm = new THREE.Mesh(fg, new THREE.MeshBasicMaterial({ color: SEL, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthTest: false }));
    fm.matrixAutoUpdate = false;
    fm.matrix.copy(matOf(c));
    fm.renderOrder = 10;
    t.hover = fm;
    t.scene.add(fm);
    t.renderer.domElement.style.cursor = "crosshair";
  }
  render3();
}
function clickView(e) {
  if (!XP.pick) {
    const h = hitAt(e), ud = (h && h.object.userData) || {};
    const prev = JSON.stringify(XP.sel);
    XP.sel = ud.comp !== undefined && $("#xp-show").value === "model" ? { comp: ud.comp } : null;
    if (JSON.stringify(XP.sel) !== prev) { renderModel(); draw(); }
    return;
  }
  const h = rayAt(e).intersectObjects(XP.three.pickables, false).find(x => x.object.userData && x.object.userData.comp !== undefined);
  if (!h) return;
  const cid = h.object.userData.comp, c = compOf(cid);
  const fi = c && c.mesh ? c.mesh.face_of_tri[h.faceIndex] : null;
  if (fi === null || fi === undefined) return;
  const cb = XP.pick.cb;
  XP.pick = null;
  cb({ comp: cid, face: fi });
  changed(); renderModel(); draw();
}
function startPick(text, cb) {
  if ($("#xp-show").value !== "model") { $("#xp-show").value = "model"; draw(); }
  XP.pick = { text, cb };
  status(text + " (Esc cancels)");
  renderModel();
}
function endPick() { XP.pick = null; renderModel(); draw(); }

function clearView() {
  const t = XP.three;
  for (const g of t.geos) g.dispose();
  t.geos = [];
  t.group.clear();
  t.pickables = [];
}
function track(g) { XP.three.geos.push(g); return g; }

// ------------------------------------------------------------------ geometry of the ShinyCAD model

function compOf(cid) { return XP.geo && XP.geo.components.find(c => c.id === cid); }
function matOf(c) { const m = c.matrix; return new THREE.Matrix4().set(m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], m[9], m[10], m[11], 0, 0, 0, 1); }
function faceRef(ref) {
  const c = ref && compOf(ref.comp);
  const r = c && c.refs && c.refs[ref.face];
  if (!r) return null;
  const M = matOf(c);
  const out = Object.assign({}, r);
  out.c = new THREE.Vector3(...r.c).applyMatrix4(M).toArray();
  if (r.n) out.n = new THREE.Vector3(...r.n).transformDirection(M).toArray();
  return out;
}
function faceText(ref) {
  if (!ref) return "(none)";
  const comp = ((XP.asm && XP.asm.components) || []).find(x => x.id === ref.comp);
  const r = faceRef(ref);
  return (comp ? comp.name : ref.comp) + " : " + (r ? r.kind + (r.r ? " Ø" + fmt(2 * r.r, 4) : "") + " face " + ref.face : "face " + ref.face);
}
async function sourceAsm() {
  const s = XP.doc.source || {};
  if (s.kind === "inp" || !s.name) return { components: [] };
  if (s.type === "part") return { components: [{ id: "1", name: s.name, source: { type: "part", name: s.name }, pos: [0, 0, 0], rot: [0, 0, 0] }] };
  return await (await api("/api/assembly/file/" + encodeURIComponent(s.name))).json();
}
async function loadGeometry() {
  const seq = ++XP.seq;
  XP.geo = { components: [] };
  XP.asm = { components: [] };
  if (isDeck()) { draw(); renderModel(); deckRefresh(); return; }
  if (!isShiny()) { draw(); renderModel(); return; }
  info("Loading the geometry...");
  try {
    const asm = await sourceAsm();
    if (seq !== XP.seq) return;
    XP.asm = asm;
    if (!asm.components.length) { info(""); draw(); renderModel(); return; }
    const r = await postJSON("/api/assembly/build", { assembly: asm, have: [...MESHES.keys()] });
    const j = await r.json();
    if (seq !== XP.seq) return;
    for (const c of j.components) if (c.mkey && c.mesh) MESHES.set(c.mkey, { mesh: c.mesh, refs: c.refs || [] });
    for (const c of j.components) if (c.mkey && MESHES.has(c.mkey)) { const e = MESHES.get(c.mkey); c.mesh = e.mesh; c.refs = e.refs; }
    XP.geo = j;
    const errs = j.components.filter(c => c.error && c.mesh).map(c => c.error);
    info(`${j.components.length} component(s)` + (errs.length ? ": " + errs.join("; ") : ""));
    if (XP.three) XP.three.zoomed = false;
    draw(); renderModel();
  } catch (e) { if (seq === XP.seq) { info(""); showErr(e); } }
}
function meshGeo(mkey) {
  const e = MESHES.get(mkey);
  if (!e) return null;
  if (!e.geo) {
    const m = e.mesh;
    e.geo = new THREE.BufferGeometry();
    e.geo.setAttribute("position", new THREE.Float32BufferAttribute(m.vertices.flat(), 3));
    e.geo.setIndex(m.triangles.flat());
    e.geo.computeVertexNormals();
    e.geo.computeBoundingBox();
    const pos = [];
    for (const pl of m.edges) for (let k = 0; k + 1 < pl.length; k++) pos.push(...pl[k], ...pl[k + 1]);
    e.edgeGeo = new THREE.BufferGeometry();
    e.edgeGeo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  }
  return e;
}

// ------------------------------------------------------------------ drawing

function draw() {
  const t = XP.three;
  if (!t || !XP.doc) return;
  clearHover();
  clearView();
  $("#xp-legend").hidden = true;
  const show = $("#xp-show").value;
  const box = new THREE.Box3();
  if (show === "results" && XP.res.geo && XP.res.frame) drawResults(box);
  else if (show === "mesh" && XP.mesh) drawPayload(box, decoded(XP.mesh), null);
  else if (isDeck()) drawDeck(box);
  else drawModel(box);
  t.group.updateMatrixWorld(true);
  const bb = box.isEmpty() ? null : [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z];
  if (bb) { XP.bbox = bb; XP.size = Math.max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], 1); }
  updateAxes(t.scene, bb, $("#xp-axes").checked);
  if (!t.zoomed && bb) { view("iso"); t.zoomed = true; } else render3();
}

function drawModel(box) {
  const t = XP.three;
  const sups = (XP.doc.supports || []).filter(s => s.target);
  for (const c of (XP.geo && XP.geo.components) || []) {
    const e = c.mkey && meshGeo(c.mkey);
    if (!e) continue;
    const inner = new THREE.Group();
    inner.matrixAutoUpdate = false;
    inner.matrix.copy(matOf(c));
    t.group.add(inner);
    const role = ((XP.doc.bodies || {})[c.id] || {}).role || "deformable";
    const sel = XP.sel && XP.sel.comp === c.id;
    const mat = new THREE.MeshStandardMaterial({ color: sel ? SEL : ROLE_COLOR[role], metalness: 0.1, roughness: 0.7, side: THREE.DoubleSide,
                                                 transparent: role === "off", opacity: role === "off" ? 0.15 : 1,
                                                 polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    const mesh = new THREE.Mesh(e.geo, mat);
    mesh.userData = { comp: c.id };
    inner.add(mesh);
    t.pickables.push(mesh);
    if ($("#xp-edges").checked) inner.add(new THREE.LineSegments(e.edgeGeo, new THREE.LineBasicMaterial({ color: 0x1d2125 })));
    for (const s of sups) {
      if (s.target.comp !== c.id) continue;
      const pos = faceTris(c, s.target.face);
      if (!pos.length) continue;
      const g = track(new THREE.BufferGeometry());
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      const strong = XP.sel && XP.sel.sup === s.id;
      inner.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: strong ? SEL : SUP, transparent: true, opacity: strong ? 0.75 : 0.5, side: THREE.DoubleSide,
                                                               polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
    }
    box.union(e.geo.boundingBox.clone().applyMatrix4(inner.matrix));
  }
}

function b64(s, T) {
  const bin = atob(s || "");
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return new T(u8.buffer);
}
function decoded(p) {
  if (!p._d) p._d = { pos: b64(p.pos, Float32Array), tri: b64(p.tri, Uint32Array), cell: b64(p.tri_cell, Uint32Array),
                      kind: p.tri_kind ? b64(p.tri_kind, Uint8Array) : null, part: p.part ? b64(p.part, Int32Array) : null,
                      lines: p.lines ? b64(p.lines, Uint32Array) : null, n: p.count };
  return p._d;
}
/** Rainbow colour scale in 12 bands (blue low, red high). */
function bandColor(t) {
  const n = 12;
  const k = Math.min(n - 1, Math.max(0, Math.floor(t * n)));
  return new THREE.Color().setHSL((1 - k / (n - 1)) * 240 / 360, 0.9, 0.5);
}
/** Triangles (non-indexed) of the view data with positions pos, cell values or nodal values, hidden cells. */
function drawPayload(box, d, opt) {
  const t = XP.three;
  opt = opt || {};
  const pos = opt.pos || d.pos;
  const vis = opt.active || null;
  const tri = d.tri, cell = d.cell, kind = d.kind;
  const ntri = tri.length / 3;
  const P = [], Col = [], L = [];
  const span = (opt.hi - opt.lo) || 1;
  const partCol = PART_COLORS.map(c => new THREE.Color(c));
  for (let k = 0; k < ntri; k++) {
    const c = cell[k];
    if (vis && !vis[c]) continue;
    const a = tri[3 * k], b = tri[3 * k + 1], cc = tri[3 * k + 2];
    for (const v of [a, b, cc]) P.push(pos[3 * v], pos[3 * v + 1], pos[3 * v + 2]);
    let ca, cb, ccol;
    if (opt.values && opt.loc === "cell") { ca = cb = ccol = bandColor((opt.values[c] - opt.lo) / span); }
    else if (opt.values) { ca = bandColor((opt.values[a] - opt.lo) / span); cb = bandColor((opt.values[b] - opt.lo) / span); ccol = bandColor((opt.values[cc] - opt.lo) / span); }
    else { ca = cb = ccol = partCol[(d.part ? d.part[c] : 0) % partCol.length]; }
    Col.push(ca.r, ca.g, ca.b, cb.r, cb.g, cb.b, ccol.r, ccol.g, ccol.b);
    const kk = kind ? kind[k] : 0;                        // element edges: no quadrangle diagonals
    if (kk === 0) L.push(a, b, b, cc, cc, a);
    else if (kk === 1) L.push(a, b, b, cc);
    else L.push(b, cc, cc, a);
  }
  const g = track(new THREE.BufferGeometry());
  g.setAttribute("position", new THREE.Float32BufferAttribute(P, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(Col, 3));
  g.computeVertexNormals();
  const mat = opt.values ? new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 })
    : new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.1, roughness: 0.75, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  const m = new THREE.Mesh(g, mat);
  m.userData = { kind: "mesh" };
  t.group.add(m);
  if ($("#xp-edges").checked && L.length < 6000000) {
    const eg = track(new THREE.BufferGeometry());
    eg.setAttribute("position", new THREE.BufferAttribute(pos instanceof Float32Array ? pos : new Float32Array(pos), 3));
    eg.setIndex(L);
    t.group.add(new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0x343a40, transparent: true, opacity: opt.values ? 0.3 : 0.6 })));
  }
  if (d.lines && d.lines.length) {
    const lg = track(new THREE.BufferGeometry());
    lg.setAttribute("position", new THREE.BufferAttribute(pos instanceof Float32Array ? pos : new Float32Array(pos), 3));
    lg.setIndex(Array.from(d.lines));
    t.group.add(new THREE.LineSegments(lg, new THREE.LineBasicMaterial({ color: 0x1d2125 })));
  }
  if (opt.undeformed) {
    const ug = track(new THREE.BufferGeometry());
    ug.setAttribute("position", new THREE.BufferAttribute(d.pos, 3));
    ug.setIndex(L);
    t.group.add(new THREE.LineSegments(ug, new THREE.LineBasicMaterial({ color: 0x868e96, transparent: true, opacity: 0.35 })));
  }
  g.computeBoundingBox();
  if (!g.boundingBox.isEmpty()) box.union(g.boundingBox);
}

function legend(title, sub, lo, hi) {
  const el = $("#xp-legend");
  const stops = [];
  for (let k = 0; k < 12; k++) { const c = bandColor((k + 0.5) / 12); stops.push(`#${c.getHexString()} ${k / 12 * 100}%`, `#${c.getHexString()} ${(k + 1) / 12 * 100}%`); }
  const ticks = [];
  for (let k = 12; k >= 0; k -= 2) ticks.push(`<span>${fmt(lo + (hi - lo) * k / 12, 4)}</span>`);
  el.innerHTML = `<div class="ttl">${esc(title)}</div><div class="hint" style="margin:0 0 4px">${esc(sub)}</div>` +
    `<span class="bar" style="background:linear-gradient(to top, ${stops.join(", ")})"></span><span class="ticks">${ticks.join("")}</span>`;
  el.hidden = false;
}

function drawResults(box) {
  const g = XP.res.geo, f = XP.res.frame;
  const d = decoded(g.payload);
  const n = d.n;
  if (!f._d) f._d = { pos: b64(f.pos, Float32Array), values: f.values ? b64(f.values, Float32Array) : null, active: f.active ? b64(f.active, Uint8Array) : null };
  const fd = f._d;
  const sv = fnum($("#xp-scale").value);
  const s = isFinite(sv) ? sv : 1;
  const pos = new Float32Array(3 * n);
  if (fd.pos.length === 3 * n) for (let i = 0; i < 3 * n; i++) pos[i] = d.pos[i] + s * (fd.pos[i] - d.pos[i]);
  else pos.set(d.pos);
  let lo = fnum($("#xp-min").value), hi = fnum($("#xp-max").value);
  const vals = fd.values;
  if (vals && (!isFinite(lo) || !isFinite(hi))) {
    let a = Infinity, b = -Infinity;
    if (f.loc === "cell") { for (let i = 0; i < vals.length; i++) if (!fd.active || !$("#xp-eroded").checked || fd.active[i]) { const v = vals[i]; if (isFinite(v)) { if (v < a) a = v; if (v > b) b = v; } } }
    else for (let i = 0; i < vals.length; i++) { const v = vals[i]; if (isFinite(v)) { if (v < a) a = v; if (v > b) b = v; } }
    if (!isFinite(a)) { a = 0; b = 0; }
    if (!isFinite(lo)) lo = a;
    if (!isFinite(hi)) hi = b;
  }
  drawPayload(box, d, { pos, values: vals, loc: f.loc, lo, hi, active: $("#xp-eroded").checked ? fd.active : null, undeformed: $("#xp-undef").checked });
  const fl = (g.fields || []).find(x => x.key === $("#xp-field").value);
  const tt = f.time !== null && f.time !== undefined ? `t = ${fmt(f.time, 5)} s` : "";
  if (vals) legend(fl ? fl.label : "", `frame ${f.index + 1} / ${g.frames.length}, ${tt}, deformation x ${fmt(s, 3)}`, lo, hi);
  info(`${XP.res.job}: frame ${f.index + 1} / ${g.frames.length}, ${tt}` + (f.eroded ? `, ${f.eroded} eroded element(s)` + ($("#xp-eroded").checked ? " hidden" : "") : ""));
}

// ------------------------------------------------------------------ form helpers

const optList = (list, cur) => list.map(v => Array.isArray(v) ? v : [v, v]).map(([v, t]) => `<option value="${esc(v)}"${String(v) === String(cur) ? " selected" : ""}>${esc(t)}</option>`).join("");
/** Inputs bound to document settings (data-s), machine settings (data-e). */
function inS(k, label, w, title) {
  return `<label class="inline xp-f"${title ? ` title="${esc(title)}"` : ""}>${esc(label)}<input type="text" data-s="${k}" value="${esc(S(k))}" style="width:${w || 70}px"></label>`;
}
function selS(k, label, list, title) {
  return `<label class="inline xp-f"${title ? ` title="${esc(title)}"` : ""}>${esc(label)}<select data-s="${k}">${optList(list, S(k))}</select></label>`;
}
function chkS(k, label, title) {
  return `<label class="check inline"${title ? ` title="${esc(title)}"` : ""}><input type="checkbox" data-s="${k}"${S(k) ? " checked" : ""}> ${esc(label)}</label>`;
}
function inE(k, label, w, title, browse) {
  const b = browse ? `<button type="button" class="small" data-browse-e="${k}" data-kind="${browse}">…</button>` : "";
  return `<label class="inline xp-f"${title ? ` title="${esc(title)}"` : ""}>${esc(label)}<input type="text" data-e="${k}" value="${esc(E(k))}" style="width:${w || 120}px">${b}</label>`;
}
function chkE(k, label, title) {
  return `<label class="check inline"${title ? ` title="${esc(title)}"` : ""}><input type="checkbox" data-e="${k}"${E(k) ? " checked" : ""}> ${esc(label)}</label>`;
}
let envTimer = null;
function bindFields(box, after) {
  box.querySelectorAll("[data-s]").forEach(el => el.onchange = () => {
    setS(el.dataset.s, el.type === "checkbox" ? el.checked : el.value);
    if (after) after(el.dataset.s);
  });
  box.querySelectorAll("[data-e]").forEach(el => el.onchange = () => {
    XP.env[el.dataset.e] = el.type === "checkbox" ? el.checked : el.value;
    clearTimeout(envTimer);
    envTimer = setTimeout(saveEnv, 200);
    if (after) after(el.dataset.e);
  });
  box.querySelectorAll("[data-browse-e]").forEach(b => b.onclick = async () => {
    const k = b.dataset.browseE;
    try {
      const p = await window.browse(b.dataset.kind, "", E(k) || "");
      if (p) { XP.env[k] = p; await saveEnv(); renderSolve(); }
    } catch (e) { showErr(e); }
  });
}
async function saveEnv() {
  try {
    const j = await (await api("/api/explicit/env", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(XP.env) })).json();
    XP.env = j.env; XP.envInfo = j;
    renderExecInfo();
  } catch (e) { showErr(e); }
}
function section(id) { return $("#" + id); }
function hidden(sec) {
  const spec = (XP.meta.mode_spec[S("analysis_mode")] || {}).hide_sections || [];
  return spec.includes(sec);
}

// ------------------------------------------------------------------ Model panel

function renderModel() {
  const box = section("xp-model");
  if (!box || !XP.doc) return;
  const src = XP.doc.source || {};
  let h = `<div class="row"><label class="inline">Source<select id="xp-kind">${optList([["shinycad", "ShinyCAD geometry (assembly or part)"], ["deck", "Deck generator (stiffened panel, shells)"], ["inp", "External .inp (PrePoMax)"]], src.kind || "shinycad")}</select></label></div>`;
  if (src.kind === "inp") {
    h += `<div class="row"><label class="inline" style="flex:1">.inp<input type="text" id="xp-inp" value="${esc(src.inp || "")}" style="flex:1;width:auto" placeholder="path of the meshed .inp"></label>` +
      `<button type="button" id="xp-inp-b" class="small" title="Choose the .inp">…</button><button type="button" id="xp-inp-show" title="Show the mesh of the .inp">Show mesh</button></div>`;
    h += XP.meshSummary ? summaryHtml(XP.meshSummary) : `<p class="hint">Show mesh reads the nodes and elements of the .inp.</p>`;
    box.innerHTML = h;
    $("#xp-kind").onchange = setKind;
    $("#xp-inp").onchange = () => { XP.doc.source.inp = $("#xp-inp").value.trim().replace(/^"|"$/g, ""); XP.mesh = null; XP.meshSummary = null; changed(); renderAllPanels(); };
    $("#xp-inp-b").onclick = async () => { try { const p = await window.browse("open", "inp", src.inp || ""); if (p) { $("#xp-inp").value = p; $("#xp-inp").onchange(); } } catch (e) { showErr(e); } };
    $("#xp-inp-show").onclick = showInpMesh;
    return;
  }
  if (src.kind === "deck") {
    if (!XP.doc.deck) XP.doc.deck = JSON.parse(JSON.stringify(XP.meta.deck_default));
    box.innerHTML = h + deckHtml();
    $("#xp-kind").onchange = setKind;
    bindDeck(box);
    return;
  }
  const mats = XP.doc.materials || {};
  h += materialsHtml();
  const comps = (XP.asm && XP.asm.components) || [];
  h += `<h3 class="xp-h">Bodies</h3>`;
  if (!comps.length) h += `<p class="hint">Choose the geometry in the toolbar.</p>`;
  else h += `<table class="fa-tbl xp-bodies"><tr><th>Component</th><th>Role</th><th>Material</th><th>Size (mm)</th><th>Mesh</th></tr>` +
    comps.map(c => {
      const b = (XP.doc.bodies || {})[c.id] || {};
      const sel = XP.sel && XP.sel.comp === c.id;
      return `<tr data-b="${esc(c.id)}"${sel ? ' class="sel"' : ""}><td title="${esc(c.name)}">${esc(c.name)}</td>` +
        `<td><select data-bk="role">${optList([["deformable", "deformable"], ["rigid", "rigid (impactor)"], ["off", "off"]], b.role || "deformable")}</select></td>` +
        `<td><select data-bk="material"><option value="">(default)</option>${optList(Object.keys(mats), b.material || "")}</select></td>` +
        `<td><input type="text" data-bk="size" value="${esc(b.size || "")}" style="width:46px" placeholder="auto"></td>` +
        `<td><select data-bk="strategy"><option value="">(default)</option>${optList(MESH_STRATEGIES, b.strategy || "")}</select></td></tr>`;
    }).join("") + `</table><p class="hint">Rigid: *RIGID BODY over the nodes of the body, REF NODE at its centre of mass (the /RBODY main node driven by the Build loading). Rigid bodies are meshed apart from the deformable bodies.</p>`;
  const m = XP.doc.mesh || {};
  h += `<h3 class="xp-h">Mesh</h3><div class="row wrap">` +
    `<label class="inline xp-f">Element size (mm)<input type="text" data-mesh="size" value="${esc(m.size || "")}" placeholder="auto" style="width:60px"></label>` +
    `<label class="inline xp-f">Minimum size (mm)<input type="text" data-mesh="size_min" value="${esc(m.size_min || "")}" placeholder="auto" style="width:60px"></label>` +
    `<label class="inline xp-f">Strategy<select data-mesh="strategy">${optList(MESH_STRATEGIES, m.strategy || "tet")}</select></label>` +
    `<label class="inline xp-f">Tetrahedra<select data-mesh="tet_type">${optList([["C3D4", "C3D4 (first order)"], ["C3D10", "C3D10 (second order)"]], m.tet_type || "C3D4")}</select></label>` +
    `<label class="inline xp-f">Hexahedra<select data-mesh="hex_type">${optList([["C3D8R", "C3D8R (reduced integration)"], ["C3D8", "C3D8 (full integration)"]], m.hex_type || "C3D8R")}</select></label>` +
    `<label class="inline xp-f">Elements per 360 deg<input type="text" data-mesh="curvature" value="${esc(m.curvature === undefined ? "" : m.curvature)}" placeholder="12" style="width:40px"></label>` +
    `<label class="check inline"><input type="checkbox" id="xp-bonded"${XP.doc.bonded !== false ? " checked" : ""}> Bonded: touching deformable bodies share nodes</label></div>`;
  h += `<h3 class="xp-h">Supports</h3>` + ((XP.doc.supports || []).length ? `<table class="fa-tbl xp-sups"><tr><th>Name</th><th>Face</th><th>ux</th><th>uy</th><th>uz</th><th></th></tr>` +
    XP.doc.supports.map(s => `<tr data-sup="${esc(s.id)}"${XP.sel && XP.sel.sup === s.id ? ' class="sel"' : ""}><td><input type="text" data-sk="name" value="${esc(s.name)}" style="width:80px"></td><td class="xp-face">${esc(faceText(s.target))}</td>` +
      [0, 1, 2].map(i => `<td><input type="checkbox" data-sd="${i}"${(s.dofs || [1, 1, 1])[i] ? " checked" : ""}></td>`).join("") +
      `<td><button type="button" class="small" data-spick="${esc(s.id)}" title="Pick the face again">Pick</button><button type="button" class="small" data-sdel="${esc(s.id)}" title="Delete">×</button></td></tr>`).join("") + `</table>`
    : `<p class="hint">Support in the toolbar: click a face of a deformable body. The checked displacements of its nodes are held (*BOUNDARY).</p>`);
  if (XP.pick) h += `<p class="fa-pick">${esc(XP.pick.text)}</p>`;
  h += XP.meshSummary ? summaryHtml(XP.meshSummary) : `<p class="hint">Write .inp meshes the bodies and writes the model .inp.</p>`;
  box.innerHTML = h;
  $("#xp-kind").onchange = setKind;
  bindMaterials(box);
  box.querySelectorAll("tr[data-b]").forEach(tr => {
    const cid = tr.dataset.b;
    tr.querySelectorAll("[data-bk]").forEach(el => el.onchange = () => {
      XP.doc.bodies = XP.doc.bodies || {};
      const b = XP.doc.bodies[cid] = XP.doc.bodies[cid] || {};
      const v = el.value;
      if (el.dataset.bk === "size") { const x = fnum(v); if (isFinite(x) && x > 0) b.size = x; else delete b.size; }
      else if (v) b[el.dataset.bk] = v; else delete b[el.dataset.bk];
      changed(); draw();
    });
    tr.onclick = e => { if (e.target.closest("select, input")) return; XP.sel = { comp: cid }; renderModel(); draw(); };
  });
  box.querySelectorAll("[data-mesh]").forEach(el => el.onchange = () => {
    const k = el.dataset.mesh, v = el.value.trim();
    XP.doc.mesh = XP.doc.mesh || {};
    if (["size", "size_min", "curvature"].includes(k)) { const x = fnum(v); if (v !== "" && isFinite(x)) XP.doc.mesh[k] = x; else delete XP.doc.mesh[k]; }
    else XP.doc.mesh[k] = v;
    changed();
  });
  $("#xp-bonded").onchange = () => { XP.doc.bonded = $("#xp-bonded").checked; changed(); };
  box.querySelectorAll("tr[data-sup]").forEach(tr => {
    const s = XP.doc.supports.find(x => x.id === tr.dataset.sup);
    tr.querySelector("[data-sk=name]").onchange = e => { s.name = e.target.value; changed(); };
    tr.querySelectorAll("[data-sd]").forEach(el => el.onchange = () => { s.dofs = s.dofs || [1, 1, 1]; s.dofs[+el.dataset.sd] = el.checked ? 1 : 0; changed(); });
    tr.onclick = e => { if (e.target.closest("input, button")) return; XP.sel = { sup: s.id }; renderModel(); draw(); };
  });
  box.querySelectorAll("[data-sdel]").forEach(b => b.onclick = () => { XP.doc.supports = XP.doc.supports.filter(x => x.id !== b.dataset.sdel); changed(); renderModel(); draw(); });
  box.querySelectorAll("[data-spick]").forEach(b => b.onclick = () => {
    const s = XP.doc.supports.find(x => x.id === b.dataset.spick);
    startPick("Click the face of support " + s.name, ref => { s.target = ref; });
  });
}
/** Materials table of the document (ShinyCAD and deck generator sources). */
function materialsHtml() {
  let h = "";
  const mats = XP.doc.materials || {};
  const libs = Object.keys(XP.meta.library);
  h += `<h3 class="xp-h">Materials</h3><table class="fa-tbl xp-mats"><tr><th>Name</th><th>Library</th><th>E (MPa)</th><th>nu</th><th>rho (kg/m^3)</th><th></th></tr>` +
    Object.entries(mats).map(([n, m]) => {
      const L = m.library && XP.meta.library[m.library];
      const v = k => L ? (k === "rho" ? fmt(L.rho, 5) : fmt(L[k], 6)) : esc(m[k] === undefined ? "" : m[k]);
      return `<tr data-m="${esc(n)}"><td><input type="text" data-mk="name" value="${esc(n)}" style="width:80px"></td>` +
        `<td><select data-mk="library"><option value="">(elastic: E, nu, rho)</option>${optList(libs, m.library || "")}</select></td>` +
        ["E", "nu", "rho"].map(k => `<td><input type="text" data-mk="${k}" value="${v(k)}"${L ? " disabled" : ""} style="width:62px"></td>`).join("") +
        `<td><button type="button" class="small" data-mdel="${esc(n)}" title="Delete">×</button></td></tr>`;
    }).join("") + `</table><div class="row"><button type="button" id="xp-mat-add" class="small">Add material</button>` +
    `<label class="inline">Default<select id="xp-mat-def">${optList(Object.keys(mats), XP.doc.default_material)}</select></label></div>` +
    `<p class="hint">A material with a library entry is written to the .inp with the E, nu and density of the entry and replaced in the deck by the library card (Build, Library materials). Other materials: *ELASTIC and *DENSITY.</p>`;
  return h;
}
function bindMaterials(box) {
  box.querySelectorAll("tr[data-m]").forEach(tr => {
    const n = tr.dataset.m;
    tr.querySelectorAll("[data-mk]").forEach(el => el.onchange = () => {
      const k = el.dataset.mk, mm = XP.doc.materials;
      if (k === "name") {
        const nn = el.value.trim().replace(/[^A-Za-z0-9_\-]+/g, "_");
        if (!nn || mm[nn]) { el.value = n; return; }
        const o = {};
        for (const [a, b] of Object.entries(mm)) o[a === n ? nn : a] = b;
        XP.doc.materials = o;
        for (const b of Object.values(XP.doc.bodies || {})) if (b.material === n) b.material = nn;
        if (XP.doc.deck && XP.doc.deck.material === n) XP.doc.deck.material = nn;
        if (XP.doc.default_material === n) XP.doc.default_material = nn;
      } else if (k === "library") mm[n].library = el.value;
      else mm[n][k] = fnum(el.value);
      changed(); renderModel(); renderBuild();
    });
  });
  box.querySelectorAll("[data-mdel]").forEach(b => b.onclick = () => {
    const n = b.dataset.mdel;
    if (Object.keys(XP.doc.materials).length < 2) return;
    delete XP.doc.materials[n];
    if (XP.doc.default_material === n) XP.doc.default_material = Object.keys(XP.doc.materials)[0];
    changed(); renderModel(); renderBuild();
  });
  $("#xp-mat-add").onclick = () => {
    let k = 1; while (XP.doc.materials["Material" + k]) k++;
    XP.doc.materials["Material" + k] = { library: "", E: 210000, nu: 0.3, rho: 7850 };
    changed(); renderModel();
  };
  $("#xp-mat-def").onchange = () => { XP.doc.default_material = $("#xp-mat-def").value; changed(); };
}
const MESH_STRATEGIES = [["tet", "Tetrahedra (free)"], ["hex", "Hexahedra, structured (block cells)"], ["hexsub", "Hexahedra by subdivision"]];
function summaryHtml(s) {
  let h = `<p class="hint">${s.nodes} nodes, ${s.elements} elements` + (s.supports !== undefined ? `, ${s.supports} support condition(s)` : "") + `</p>`;
  if (s.bodies) h += `<table class="fa-tbl"><tr><th>Body</th><th>Role</th><th>ELSET</th><th>Material</th><th>Elements</th><th>Ref node</th></tr>` +
    s.bodies.map(b => `<tr><td>${esc(b.name)}</td><td>${esc(b.role)}</td><td>${esc(b.elset)}</td><td>${esc(b.material)}</td><td>${b.elements} ${esc((b.types || []).join(" "))}</td><td>${b.ref_node || ""}</td></tr>`).join("") + `</table>`;
  if (s.parts) h += `<table class="fa-tbl"><tr><th>ELSET</th><th>Type</th></tr>` + s.parts.map(p => `<tr><td>${esc(p.elset)}</td><td>${esc(p.type)}</td></tr>`).join("") + `</table>`;
  if (s.warnings && s.warnings.length) h += `<p class="hint">${s.warnings.map(esc).join("<br>")}</p>`;
  return h;
}
function setKind() {
  const k = $("#xp-kind").value;
  XP.doc.source = Object.assign({ type: "assembly", name: "", inp: "" }, XP.doc.source || {}, { kind: k });
  if (k === "deck" && !XP.doc.deck) XP.doc.deck = JSON.parse(JSON.stringify(XP.meta.deck_default));
  XP.deckSel = new Set(); XP.deckCheck = null; XP.pattern = null;
  XP.mesh = null; XP.meshSummary = null;
  changed(); refreshSources(); loadGeometry(); renderAllPanels();
}
async function pollJob(jid, label) {
  for (;;) {
    const j = await (await api("/api/explicit/job/" + jid)).json();
    if (j.state !== "running") return j;
    info(`${label}: ${j.message || j.stage}`);
    await new Promise(r => setTimeout(r, 400));
  }
}
async function writeInp() {
  if (!isModel()) { showInpMesh(); return; }
  if (isShiny() && !(XP.doc.source || {}).name) { status("Choose the geometry first", true); return; }
  busy(true, "Writing the model .inp ...");
  try {
    const j = await pollJob((await (await postJSON("/api/explicit/model", req())).json()).job, "Write .inp");
    if (j.state === "error") throw new Error(j.error);
    XP.mesh = j.result.payload; XP.meshSummary = j.result.summary;
    $("#xp-show").value = "mesh";
    if (XP.three) XP.three.zoomed = false;
    status("Model .inp written: " + j.result.inp);
    info(`${XP.meshSummary.nodes} nodes, ${XP.meshSummary.elements} elements`);
    renderModel(); renderBuild(); draw();
  } catch (e) { showErr(e); info(""); } finally { busy(false); }
}
async function showInpMesh() {
  const p = (XP.doc.source || {}).inp;
  if (!p) { status("Enter the path of the .inp", true); return; }
  busy(true, "Reading the mesh of the .inp ...");
  try {
    const j = await pollJob((await (await postJSON("/api/explicit/inp_view", { path: p })).json()).job, "Read .inp");
    if (j.state === "error") throw new Error(j.error);
    XP.mesh = j.result.payload; XP.meshSummary = j.result.summary;
    $("#xp-show").value = "mesh";
    if (XP.three) XP.three.zoomed = false;
    info(`${XP.meshSummary.nodes} nodes, ${XP.meshSummary.elements} elements`);
    status(`Mesh of ${p}: ${XP.meshSummary.nodes} nodes, ${XP.meshSummary.elements} elements`);
    renderModel(); draw();
  } catch (e) { showErr(e); info(""); } finally { busy(false); }
}
function addSupport() {
  if (!isShiny()) { status(isDeck() ? "Deck generator: Edge supports in Model" : "Supports are defined for the ShinyCAD geometry; an external .inp carries its own *BOUNDARY", true); return; }
  startPick("Click the face of the support", ref => {
    const id = "s" + (XP.doc.next++);
    XP.doc.supports.push({ id, name: "Support " + (XP.doc.supports.length + 1), target: ref, dofs: [1, 1, 1] });
    XP.sel = { sup: id };
  });
}

// ------------------------------------------------------------------ Deck generator source (DECK_GENERATOR)

const DECK_COLS = [["name", 64], ["axis", 0], ["pos", 52], ["h", 44], ["bf_top", 44], ["bf_bot", 44], ["t_web", 36], ["t_flange", 36]];
const DECK_NUM = new Set(["pos", "h", "bf_top", "bf_bot", "t_web", "t_flange"]);
const DECK_PALETTE = ["#1c7ed6", "#e8590c", "#2b8a3e", "#ae3ec9", "#f08c00", "#0c8599", "#c2255c", "#5c940d"];
const DECK_EDGES = [["x0", "x = 0"], ["xL", "x = X distance"], ["y0", "y = 0"], ["yB", "y = Y distance"]];
const EDGE_MODES = [["free", "free"], ["pinned", "pinned (ux uy uz)"], ["clamped", "clamped (ux uy uz rx ry rz)"]];
const PATTERN_RULES = [["bays", "equal bays - ends clear"], ["ends", "first and last on the ends"], ["steps", "equal steps from the start"]];
const COINCIDENT_TOL = 0.5, NEAR_TOL = 10;      // mm, same axis

function D() { return XP.doc.deck; }
const fmtv = v => (isFinite(v) ? String(+(+v).toFixed(6)) : "");
/** Positions are measured along y for an x beam and along x for a y beam: the limit of that coordinate. */
function deckLimit(axis) { const d = D(); return axis === "x" ? +d.B : +d.L; }
function deckSelected() { return [...(XP.deckSel || new Set())].filter(i => i < D().beams.length).sort((a, b) => a - b); }

function deckHtml() {
  const d = D();
  const sel = new Set(deckSelected());
  const fld = (k, label, w, title) => `<label class="inline xp-f"${title ? ` title="${esc(title)}"` : ""}>${esc(label)}<input type="text" data-dk="${k}" value="${esc(d[k] === undefined ? "" : d[k])}" style="width:${w}px"></label>`;
  let h = `<h3 class="xp-h">Panel</h3><div class="row wrap">${fld("L", "X distance [mm]", 60)}${fld("B", "Y distance [mm]", 60)}` +
    `${fld("snipe", "Flange snipe [mm]", 40, "Lower flange of the shallower beam stops this far from the web of a deeper beam it crosses")}${fld("deck_t", "Deck thickness [mm]", 40)}</div>`;
  h += `<h3 class="xp-h">Beams</h3><div class="xp-beams-wrap"><table class="fa-tbl xp-beams"><tr><th></th>${DECK_COLS.map(c => `<th>${c[0]}</th>`).join("")}</tr>` +
    d.beams.map((b, i) => `<tr data-bi="${i}"${sel.has(i) ? ' class="sel"' : ""}><td><input type="checkbox" data-bsel${sel.has(i) ? " checked" : ""}></td>` +
      DECK_COLS.map(([k, w]) => k === "axis" ? `<td><select data-bk="axis">${optList(["x", "y"], b.axis || "x")}</select></td>`
        : `<td><input type="text" data-bk="${k}" value="${esc(k === "name" ? b.name : fmtv(b[k]))}" style="width:${w}px"></td>`).join("") + `</tr>`).join("") +
    `</table></div><div class="row"><button type="button" class="small" id="xp-dk-add" title="New row: a copy of the selected row (or the last row) in the largest gap along its axis">Add</button>` +
    `<button type="button" class="small" id="xp-dk-del" title="Delete the selected rows">Delete</button>` +
    `<button type="button" class="small" id="xp-dk-pat" title="Repeat the selected beam along its own position coordinate">Pattern…</button>` +
    `<button type="button" class="small" id="xp-dk-none">Clear selection</button><span class="hint">${d.beams.length} beam(s), ${sel.size} selected</span></div>` +
    `<p class="hint">axis: direction of the beam. pos: y of an x beam, x of a y beam. h: deck midplane to lower flange midplane. bf_top: top flange width in the deck plane (it replaces the deck there). bf_bot: lower flange width (0: flat bar). t_flange applies to both flanges. Beams with one name form one element set and one section. Lengths in mm; fields take sums (400-12, 6000/8, 12,5).</p>`;
  h += `<div id="xp-dk-pattern">${patternHtml()}</div>`;
  h += `<svg id="xp-dk-plan" class="xp-svg xp-dk-svg"></svg><svg id="xp-dk-sec" class="xp-svg xp-dk-svg"></svg>`;
  h += `<div id="xp-dk-check">${deckCheckHtml()}</div>`;
  h += `<h3 class="xp-h">Mesh</h3><div class="row wrap">${fld("size", "Max element size [mm]", 50)}${fld("min_div", "Min divisions per interval", 30)}` +
    `<label class="inline xp-f">Shell type<select data-dk="shell">${optList([["S4", "S4 / S3"], ["S4R", "S4R / S3R"]], d.shell || "S4")}</select></label>` +
    `<label class="check inline"><input type="checkbox" data-dk="tri"${d.tri ? " checked" : ""}> Triangles</label>` +
    `<label class="inline xp-f">Material<select data-dk="material"><option value="">(default)</option>${optList(Object.keys(XP.doc.materials || {}), d.material || "")}</select></label></div>` +
    `<p class="hint">Structured mesh: every interval between break coordinates (panel edges, beam lines, flange edges, web depths) gets ceil(length / max element size) divisions; the plates are cut at the break lines and meshed transfinite, conformal across the junctions.</p>`;
  h += `<h3 class="xp-h">Edge supports</h3><div class="row wrap">` + DECK_EDGES.map(([k, t]) => `<label class="inline xp-f">${esc(t)}<select data-edge="${k}">${optList(EDGE_MODES, (d.edges || {})[k] || "free")}</select></label>`).join("") +
    `</div><p class="hint">The nodes on the edge plane (deck and webs) are held: *NSET EDGE_X0, EDGE_XL, EDGE_Y0, EDGE_YB and *BOUNDARY.</p>`;
  h += materialsHtml();
  const st = XP.deckStep;
  h += `<h3 class="xp-h">STEP</h3><div class="row"><button type="button" id="xp-dk-step" title="STEP of the deck structure and a ShinyCAD part with the components as surface bodies">Generate STEP</button>` +
    (st ? `<button type="button" class="small" id="xp-dk-openpart">Open part ${esc(st.part)}</button>` : "") + `</div>` +
    `<p class="hint">Writes &lt;name&gt;_deck.step (one named component per element set) and &lt;name&gt;_deck_model.json to the step folder of the project, and the part &lt;name&gt;_deck with one Import surface feature per component.</p>` +
    (st ? `<p class="hint">${esc(st.step)}: ${esc(st.components.join(", "))}</p>` : "");
  h += XP.meshSummary ? deckSummaryHtml(XP.meshSummary) : `<p class="hint">Write .inp meshes the deck and writes the model .inp.</p>`;
  return h;
}

function deckCheckHtml() {
  const c = XP.deckCheck;
  if (!c) return "";
  let h = "";
  if (c.sections.length) h += `<h3 class="xp-h">Sections</h3><table class="fa-tbl"><tr><th>ELSET</th><th>Parameter</th><th>t [mm]</th></tr>` +
    c.sections.map(s => `<tr><td>${esc(s.set)}</td><td>${esc(s.param)}</td><td${s.t > 0 ? "" : ' class="xp-bad"'}>${fmt(s.t, 5)}</td></tr>`).join("") + `</table>`;
  const bad = c.errors.concat(c.inp_errors);
  if (bad.length) h += `<p class="xp-bad">${bad.map(esc).join("<br>")}</p>`;
  if (c.warnings.length) h += `<p class="hint">${c.warnings.map(esc).join("<br>")}</p>`;
  return h;
}

function deckSummaryHtml(s) {
  let h = `<h3 class="xp-h">Mesh written</h3><p class="hint">${s.nodes} nodes, ${s.elements} elements, ${s.supports} support condition(s), material ${esc(s.material)}</p>` +
    `<table class="fa-tbl"><tr><th>ELSET</th><th>Elements</th><th>z [mm]</th><th>t [mm]</th><th>Section</th><th>Parameter</th></tr>` +
    s.sets.map(x => `<tr><td>${esc(x.set)}</td><td>${x.elements}</td><td>${Math.abs(x.z[1] - x.z[0]) < 1e-6 ? fmt(x.z[0], 5) : fmt(x.z[0], 5) + " .. " + fmt(x.z[1], 5)}</td>` +
      `<td>${fmt(x.t, 5)}</td><td>${esc(x.section)}</td><td>${esc(x.param)}</td></tr>`).join("") + `</table>` +
    `<p class="hint">Longest element edge ${fmt(s.longest_edge, 5)} mm. Aspect ratio: median ${fmt(s.ar_median, 3)}, worst ${fmt(s.ar_worst, 3)}. ` +
    `Element edges by number of plates sharing them: ${Object.entries(s.junctions || {}).map(([k, v]) => `${k}: ${v}`).join(", ")} (1 free edge, 2 inside a plate, 3 T junction, 4 cruciform).</p>`;
  if (s.warnings && s.warnings.length) h += `<p class="hint">${s.warnings.map(esc).join("<br>")}</p>`;
  return h;
}

/** Same-axis neighbour of beam i at pos: [distance, beam] of the nearest, or null. */
function deckNearest(i, axis, pos) {
  let best = null;
  D().beams.forEach((b, j) => {
    if (j === i || b.axis !== axis || !isFinite(+b.pos)) return;
    const dd = Math.abs(+b.pos - pos);
    if (!best || dd < best[0]) best = [dd, b];
  });
  return best;
}
/** Coincident (within 0.5 mm) is refused, near (within 10 mm) is confirmed. */
function deckAllow(i, axis, pos) {
  const n = deckNearest(i, axis, pos);
  if (!n) return true;
  if (n[0] <= COINCIDENT_TOL) { status(`${n[1].name} is at ${fmtv(n[1].pos)} mm on axis ${axis}: two beams on one line`, true); return false; }
  if (n[0] <= NEAR_TOL) return confirm(`${n[1].name} is at ${fmtv(n[1].pos)} mm, ${fmtv(n[0])} mm away. The gap meshes as elements ${fmtv(n[0])} mm wide. Keep it?`);
  return true;
}

function bindDeck(box) {
  const d = D();
  box.querySelectorAll("[data-dk]").forEach(el => el.onchange = () => {
    const k = el.dataset.dk;
    if (el.type === "checkbox") d[k] = el.checked;
    else if (el.tagName === "SELECT") d[k] = el.value;
    else {
      const v = fnum(el.value);
      if (!isFinite(v)) { el.value = fmtv(d[k]); status(`${k}: not a number or a sum`, true); return; }
      d[k] = k === "min_div" ? Math.max(1, Math.round(v)) : v;
      el.value = fmtv(d[k]);
    }
    changed(); deckChanged();
  });
  box.querySelectorAll("[data-edge]").forEach(el => el.onchange = () => { d.edges = d.edges || {}; d.edges[el.dataset.edge] = el.value; changed(); });
  box.querySelectorAll("tr[data-bi]").forEach(tr => {
    const i = +tr.dataset.bi, b = d.beams[i];
    tr.querySelectorAll("[data-bk]").forEach(el => el.onchange = () => {
      const k = el.dataset.bk;
      if (k === "name") { b.name = el.value.trim().replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "").toUpperCase() || "BEAM"; el.value = b.name; }
      else if (k === "axis") {
        if (!deckAllow(i, el.value, +b.pos)) { el.value = b.axis; return; }
        b.axis = el.value;
      } else {
        const v = fnum(el.value);
        if (!isFinite(v) || (k === "h" && v <= 0) || v < 0) { el.value = fmtv(b[k]); status(`${b.name} ${k}: ${k === "h" ? "more than 0" : "0 or more"} mm, a number or a sum`, true); return; }
        if (k === "pos" && !deckAllow(i, b.axis, v)) { el.value = fmtv(b[k]); return; }
        b[k] = v; el.value = fmtv(v);
      }
      changed(); deckChanged();
    });
    tr.querySelector("[data-bsel]").onchange = e => { deckSelect(i, e.target.checked); };
    tr.onclick = e => { if (e.target.closest("input, select")) return; deckSelect(i, !XP.deckSel.has(i)); };
  });
  $("#xp-dk-add").onclick = deckAdd;
  $("#xp-dk-del").onclick = () => {
    const s = deckSelected();
    if (!s.length) { status("Select the rows to delete", true); return; }
    if (s.length > 1 && !confirm(`Delete ${s.length} selected beams?`)) return;
    d.beams = d.beams.filter((_b, i) => !s.includes(i));
    XP.deckSel = new Set(); XP.pattern = null;
    changed(); renderModel(); deckChanged();
  };
  $("#xp-dk-pat").onclick = () => {
    const s = deckSelected();
    if (s.length !== 1) { status(s.length ? `${s.length} rows are selected: Pattern repeats one beam` : "Select the beam row to repeat", true); return; }
    const b = d.beams[s[0]], lim = deckLimit(b.axis);
    XP.pattern = { i: s[0], mode: "spacing", n: "5", sp: "660", len: fmtv(Math.max(0, lim - b.pos)), rule: "bays", p0: fmtv(b.pos) };
    $("#xp-dk-pattern").innerHTML = patternHtml(); bindPattern();
  };
  $("#xp-dk-none").onclick = () => { XP.deckSel = new Set(); renderModel(); };
  $("#xp-dk-step").onclick = deckStep;
  if ($("#xp-dk-openpart")) $("#xp-dk-openpart").onclick = async () => {
    const cur = window.__partCurrent && window.__partCurrent();
    if (cur && cur.dirty && !confirm(`Discard the changes to part ${cur.name}?`)) return;
    showTab("part");
    try { await window.__partLoadNamed(XP.deckStep.part); status("Loaded part " + XP.deckStep.part); } catch (e) { showErr(e); }
  };
  bindMaterials(box);
  bindPattern();
  drawDeckDiagrams();
}

function deckSelect(i, on) {
  XP.deckSel = XP.deckSel || new Set();
  if (on) XP.deckSel.add(i); else XP.deckSel.delete(i);
  const tr = document.querySelector(`#xp-model tr[data-bi="${i}"]`);
  if (tr) { tr.classList.toggle("sel", on); tr.querySelector("[data-bsel]").checked = on; }
  const n = document.querySelector("#xp-model .xp-beams-wrap + .row .hint");
  if (n) n.textContent = `${D().beams.length} beam(s), ${XP.deckSel.size} selected`;
  drawDeckDiagrams();
}

/** New row: a copy of the selected (or last) row placed at the middle of the largest free gap along its axis. */
function deckAdd() {
  const d = D();
  const s = deckSelected();
  const src = d.beams[s.length ? s[s.length - 1] : d.beams.length - 1] || { name: "BEAM", axis: "x", pos: 0, h: 200, bf_top: 0, bf_bot: 0, t_web: 8, t_flange: 0 };
  const lim = deckLimit(src.axis);
  const ps = [0, lim, ...d.beams.filter(b => b.axis === src.axis).map(b => +b.pos)].filter(isFinite).sort((a, b) => a - b);
  let best = [0, lim / 2];
  for (let k = 0; k + 1 < ps.length; k++) if (ps[k + 1] - ps[k] > best[0]) best = [ps[k + 1] - ps[k], (ps[k] + ps[k + 1]) / 2];
  const b = Object.assign({}, src, { pos: +best[1].toFixed(3) });
  d.beams.push(b);
  XP.deckSel = new Set([d.beams.length - 1]);
  changed(); renderModel(); deckChanged();
  status(`Added ${b.name} ${b.axis} at ${fmtv(b.pos)} mm`);
}

// --- Pattern: repeat one beam along its position coordinate (by spacing, or a count over a length)

function patternRows() {
  const p = XP.pattern, d = D();
  if (!p) return null;
  const b = d.beams[p.i];
  if (!b) return null;
  const n = Math.round(fnum(p.n)), p0 = fnum(p.p0), lim = deckLimit(b.axis);
  let step, span = null;
  if (p.mode === "spacing") step = fnum(p.sp);
  else {
    span = fnum(p.len);
    step = p.rule === "bays" ? span / (n + 1) : p.rule === "ends" ? (n > 1 ? span / (n - 1) : 0) : span / n;
  }
  if (!(n >= 1) || !isFinite(p0) || !isFinite(step) || (span !== null && !(span > 0))) return null;
  const first = p.mode === "length" && p.rule === "bays" ? 1 : 0;
  const seen = d.beams.filter(x => x.axis === b.axis).map(x => +x.pos);
  const rows = [];
  for (let k = 0; k < n; k++) {
    const q = p0 + (k + first) * step;
    if (q < -1e-9 || q > lim + 1e-9) rows.push([q, "out"]);
    else if (seen.some(x => Math.abs(x - q) <= COINCIDENT_TOL)) rows.push([q, "dup"]);
    else { rows.push([q, seen.some(x => Math.abs(x - q) <= NEAR_TOL) ? "near" : "new"]); seen.push(q); }
  }
  return { rows, step, span, lim, b };
}
function patternHtml() {
  const p = XP.pattern;
  if (!p) return "";
  const b = D().beams[p.i];
  if (!b) return "";
  const ax = b.axis === "x" ? "y" : "x";
  const inp = (k, label, w, dis) => `<label class="inline xp-f">${esc(label)}<input type="text" data-pt="${k}" value="${esc(p[k])}" style="width:${w}px"${dis ? " disabled" : ""}></label>`;
  return `<div class="xp-pattern"><h3 class="xp-h">Pattern ${esc(b.name)} (axis ${b.axis}, h ${fmtv(b.h)} mm): positions along ${ax}, ${ax} = 0 to ${fmtv(deckLimit(b.axis))} mm</h3>` +
    `<div class="row wrap"><label class="check inline"><input type="radio" name="xp-ptm" value="spacing"${p.mode === "spacing" ? " checked" : ""}> By spacing</label>` +
    `<label class="check inline"><input type="radio" name="xp-ptm" value="length"${p.mode === "length" ? " checked" : ""}> By length</label></div>` +
    `<div class="row wrap">${inp("n", "Count", 40)}${inp("sp", "Spacing [mm]", 56, p.mode !== "spacing")}${inp("len", "Length to fill [mm]", 56, p.mode !== "length")}` +
    `<label class="inline xp-f">Beams sit<select data-pt="rule"${p.mode !== "length" ? " disabled" : ""}>${optList(PATTERN_RULES, p.rule)}</select></label>${inp("p0", "Start position [mm]", 56)}</div>` +
    `<p class="hint" id="xp-pt-prev"></p><div class="row"><button type="button" class="small primary" id="xp-pt-ok">Add beams</button><button type="button" class="small" id="xp-pt-cancel">Cancel</button></div></div>`;
}
function patternPreview() {
  const el = $("#xp-pt-prev");
  if (!el) return;
  const r = patternRows();
  if (!r) { el.textContent = "Count at least 1; spacing, length and start must be numbers (length more than 0)."; el.className = "xp-bad"; $("#xp-pt-ok").disabled = true; return; }
  const mark = { new: "", near: "~", dup: "*", out: "*" };
  const keep = r.rows.filter(x => x[1] === "new" || x[1] === "near");
  const cnt = s => r.rows.filter(x => x[1] === s).length;
  const ax = r.b.axis === "x" ? "y" : "x";
  const notes = [];
  if (XP.pattern.mode === "length") notes.push(`spacing ${fmtv(r.step)} mm over ${fmtv(r.span)} mm`);
  notes.push(`${keep.length} new`);
  if (cnt("dup")) notes.push(`${cnt("dup")} already there`);
  if (cnt("out")) notes.push(`${cnt("out")} outside ${ax} 0 to ${fmtv(r.lim)} mm`);
  if (cnt("dup") || cnt("out")) notes.push("* skipped");
  if (cnt("near")) notes.push(`~ ${cnt("near")} within ${NEAR_TOL} mm of another beam`);
  el.textContent = "Positions: " + r.rows.slice(0, 12).map(x => fmtv(x[0]) + mark[x[1]]).join(", ") + (r.rows.length > 12 ? " ..." : "") + ". " + notes.join(", ") + ".";
  el.className = keep.length ? "hint" : "xp-bad";
  $("#xp-pt-ok").disabled = !keep.length;
}
function bindPattern() {
  const p = XP.pattern;
  if (!p || !$("#xp-pt-ok")) return;
  document.querySelectorAll("#xp-dk-pattern [data-pt]").forEach(el => {
    el.oninput = el.onchange = () => {
      p[el.dataset.pt] = el.value;
      if (el.tagName !== "SELECT" && el.type === "text" && document.activeElement !== el) { const v = fnum(el.value); if (isFinite(v)) { el.value = fmtv(v); p[el.dataset.pt] = el.value; } }
      patternPreview();
    };
  });
  document.querySelectorAll('#xp-dk-pattern input[name="xp-ptm"]').forEach(el => el.onchange = () => { p.mode = el.value; $("#xp-dk-pattern").innerHTML = patternHtml(); bindPattern(); });
  $("#xp-pt-cancel").onclick = () => { XP.pattern = null; $("#xp-dk-pattern").innerHTML = ""; };
  $("#xp-pt-ok").onclick = () => {
    const r = patternRows();
    if (!r) return;
    const keep = r.rows.filter(x => x[1] === "new" || x[1] === "near").map(x => +x[0].toFixed(6));
    const d = D();
    for (const q of keep) d.beams.push(Object.assign({}, r.b, { pos: q }));
    XP.pattern = null;
    changed(); renderModel(); deckChanged();
    status(`Patterned ${r.b.name}: ${keep.length} beam(s) added`);
  };
  patternPreview();
}

// --- plan and section diagrams (SVG, panel width)

function svgDim(x1, y1, x2, y2, text, vertical) {
  const tx = (x1 + x2) / 2, ty = (y1 + y2) / 2;
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#868e96" marker-start="url(#xpdka)" marker-end="url(#xpdka)"/>` +
    (vertical ? `<text x="${tx - 4}" y="${ty}" text-anchor="middle" transform="rotate(-90 ${tx - 4} ${ty})">${esc(text)}</text>`
      : `<text x="${tx}" y="${ty - 4}" text-anchor="middle">${esc(text)}</text>`);
}
function drawDeckDiagrams() {
  const plan = $("#xp-dk-plan"), sec = $("#xp-dk-sec");
  if (!plan || !sec) return;
  const d = D(), L = +d.L, B = +d.B;
  const W = Math.max(280, Math.round(plan.getBoundingClientRect().width || 480));
  const marker = `<defs><marker id="xpdka" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 2 L10 5 L0 8 z" fill="#868e96"/></marker></defs>`;
  if (!(L > 0 && B > 0)) { plan.innerHTML = ""; sec.innerHTML = ""; return; }
  const m = 34, H = Math.round(Math.min(W * 0.75, Math.max(160, (W - 2 * m) * B / L + 2 * m)));
  plan.setAttribute("viewBox", `0 0 ${W} ${H}`); plan.setAttribute("height", H);
  const s = Math.min((W - 2 * m) / L, (H - 2 * m) / B);
  const x0 = (W - L * s) / 2, y0 = (H + B * s) / 2;
  const X = x => x0 + x * s, Y = y => y0 - y * s;
  const beams = d.beams.filter(b => isFinite(+b.pos) && isFinite(+b.h));
  const depths = [...new Set(beams.map(b => +b.h))].sort((a, b) => b - a);
  const col = h => DECK_PALETTE[depths.indexOf(+h) % DECK_PALETTE.length] || "#606060";
  const sel = new Set(deckSelected());
  let g = marker;
  for (const b of beams) {
    if (!(+b.bf_top > 0)) continue;
    const w = +b.bf_top / 2;
    if (b.axis === "x") { const e0 = Math.max(0, b.pos - w), e1 = Math.min(B, +b.pos + w); if (e1 > e0) g += `<rect x="${X(0)}" y="${Y(e1)}" width="${L * s}" height="${(e1 - e0) * s}" fill="#e8e0d0" stroke="#b0a890" stroke-width="0.5"/>`; }
    else { const e0 = Math.max(0, b.pos - w), e1 = Math.min(L, +b.pos + w); if (e1 > e0) g += `<rect x="${X(e0)}" y="${Y(B)}" width="${(e1 - e0) * s}" height="${B * s}" fill="#e8e0d0" stroke="#b0a890" stroke-width="0.5"/>`; }
  }
  g += `<rect x="${X(0)}" y="${Y(B)}" width="${L * s}" height="${B * s}" fill="none" stroke="#212529" stroke-width="1.5"/>`;
  d.beams.forEach((b, i) => {
    if (!isFinite(+b.pos)) return;
    const on = sel.has(i), c = col(b.h);
    const tip = `<title>${esc(b.name)} ${b.axis === "x" ? "y" : "x"} = ${fmtv(b.pos)} mm, h ${fmtv(b.h)} mm</title>`;
    if (b.axis === "y") g += `<line x1="${X(b.pos)}" y1="${Y(0)}" x2="${X(b.pos)}" y2="${Y(B)}" stroke="${c}" stroke-width="${on ? 3 : 1.6}">${tip}</line>`;
    else g += `<line x1="${X(0)}" y1="${Y(b.pos)}" x2="${X(L)}" y2="${Y(b.pos)}" stroke="${c}" stroke-width="${on ? 3 : 1.6}">${tip}</line>`;
    if (on) g += b.axis === "y" ? `<text x="${X(b.pos)}" y="${Y(B) - 4}" text-anchor="middle" fill="${c}">${esc(b.name)} x=${fmtv(b.pos)}</text>`
      : `<text x="${X(L) - 2}" y="${Y(b.pos) - 3}" text-anchor="end" fill="${c}">${esc(b.name)} y=${fmtv(b.pos)}</text>`;
  });
  g += svgDim(X(0), Y(0) + 16, X(L), Y(0) + 16, `x = ${fmtv(L)}`) + svgDim(X(0) - 16, Y(0), X(0) - 16, Y(B), `y = ${fmtv(B)}`, true);
  g += `<text x="${W / 2}" y="12" text-anchor="middle" font-weight="600">PLAN (deck between the top flanges)</text>`;
  plan.innerHTML = g;
  // section of the selected beam (first beam when none or several are selected)
  const s1 = deckSelected();
  const b = d.beams[s1.length === 1 ? s1[0] : 0];
  const HS = 170;
  sec.setAttribute("viewBox", `0 0 ${W} ${HS}`); sec.setAttribute("height", HS);
  if (!b || !(+b.h > 0)) { sec.innerHTML = ""; return; }
  const h = +b.h, bt = +b.bf_top || 0, bb = +b.bf_bot || 0;
  const ss = Math.min((HS - 70) / h, (W * 0.5) / Math.max(bt, bb, 60));
  const cx = W / 2, zy = 40, Z = z => zy - z * ss;
  let q = marker + `<text x="${W / 2}" y="12" text-anchor="middle" font-weight="600">SECTION ${esc(b.name)} (${b.axis === "x" ? "y" : "x"} = ${fmtv(b.pos)} mm)</text>`;
  q += `<line x1="${cx - W * 0.4}" y1="${Z(0)}" x2="${cx + W * 0.4}" y2="${Z(0)}" stroke="#868e96" stroke-width="2"/><text x="${cx - W * 0.4}" y="${Z(0) - 4}">deck midplane z = 0</text>`;
  const c = "#3060a0";
  if (bt > 0) q += `<line x1="${cx - bt * ss / 2}" y1="${Z(0)}" x2="${cx + bt * ss / 2}" y2="${Z(0)}" stroke="${c}" stroke-width="5"/>` + svgDim(cx - bt * ss / 2, Z(0) - 12, cx + bt * ss / 2, Z(0) - 12, `bf_top = ${fmtv(bt)}`);
  q += `<line x1="${cx}" y1="${Z(0)}" x2="${cx}" y2="${Z(-h)}" stroke="${c}" stroke-width="3"/>`;
  const dx = cx + Math.max(bt, bb, 40) * ss / 2 + 40;
  q += svgDim(dx, Z(0), dx, Z(-h), `h = ${fmtv(h)}`, true);
  if (bb > 0) q += `<line x1="${cx - bb * ss / 2}" y1="${Z(-h)}" x2="${cx + bb * ss / 2}" y2="${Z(-h)}" stroke="${c}" stroke-width="5"/>` + svgDim(cx - bb * ss / 2, Z(-h) + 14, cx + bb * ss / 2, Z(-h) + 14, `bf_bot = ${fmtv(bb)}`);
  else q += `<text x="${cx}" y="${Z(-h) + 14}" text-anchor="middle">free edge (flat bar)</text>`;
  q += `<text x="${cx - 8}" y="${Z(-h / 2)}" text-anchor="end">t_web ${fmtv(b.t_web)}${bt > 0 || bb > 0 ? `, t_flange ${fmtv(b.t_flange)}` : ""}</text>`;
  sec.innerHTML = q;
}

// --- server check (plates of deck_model, sections, clashes) and the 3D view of the plates

let deckTimer = null;
function deckChanged() {
  drawDeckDiagrams();
  if (XP.mesh && isDeck()) { XP.mesh = null; XP.meshSummary = null; if ($("#xp-show").value === "mesh") $("#xp-show").value = "model"; }
  clearTimeout(deckTimer);
  deckTimer = setTimeout(deckRefresh, 250);
}
async function deckRefresh() {
  if (!XP.doc || !isDeck()) return;
  const seq = ++XP.seq;
  try {
    const c = await (await postJSON("/api/explicit/deck/check", { deck: D() })).json();
    if (seq !== XP.seq || !isDeck()) return;
    XP.deckCheck = c;
    const el = $("#xp-dk-check");
    if (el) el.innerHTML = deckCheckHtml();
    info(c.errors.length ? c.errors[0] : `${c.parts.length} plate group(s), ${c.parts.reduce((a, p) => a + p.polys.length, 0)} plates`);
    if ($("#xp-show").value === "model") draw();
  } catch (e) { showErr(e); }
}
function drawDeck(box) {
  const t = XP.three, c = XP.deckCheck;
  if (!c) return;
  c.parts.forEach((p, k) => {
    const P = [], E = [];
    for (const poly of p.polys) {
      for (let j = 1; j + 1 < poly.length; j++) P.push(...poly[0], ...poly[j], ...poly[j + 1]);
      for (let j = 0; j < poly.length; j++) E.push(...poly[j], ...poly[(j + 1) % poly.length]);
    }
    if (!P.length) return;
    const g = track(new THREE.BufferGeometry());
    g.setAttribute("position", new THREE.Float32BufferAttribute(P, 3));
    g.computeVertexNormals(); g.computeBoundingBox();
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: PART_COLORS[k % PART_COLORS.length], metalness: 0.1, roughness: 0.7, side: THREE.DoubleSide,
                                                                 polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }));
    m.userData = { deckPart: p.name };
    t.group.add(m);
    if ($("#xp-edges").checked) {
      const eg = track(new THREE.BufferGeometry());
      eg.setAttribute("position", new THREE.Float32BufferAttribute(E, 3));
      t.group.add(new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0x1d2125 })));
    }
    box.union(g.boundingBox);
  });
}

async function deckStep() {
  busy(true, "Writing the deck STEP ...");
  try {
    const j = await pollJob((await (await postJSON("/api/explicit/deck/step", req())).json()).job, "Generate STEP");
    if (j.state === "error") throw new Error(j.error);
    XP.deckStep = j.result;
    status(`STEP written: ${j.result.step}; part ${j.result.part} (${j.result.components.length} surface bodies)`);
    if (window.__partRefresh) try { window.__partRefresh(); } catch (e) { /* Part tab not opened */ }
    refreshSources(); renderModel();
  } catch (e) { showErr(e); } finally { busy(false); }
}

// ------------------------------------------------------------------ Runs panel

async function refreshRuns() {
  try {
    const j = await (await postJSON("/api/explicit/runs", req())).json();
    XP.runs = j.runs; XP.runsDir = j.project_dir;
  } catch (e) { XP.runs = []; }
  renderRuns(); renderSolve(); renderResultsJobs();
}
function runOf(path) { return XP.runs.find(r => r.path === path); }
function renderRuns() {
  const box = section("xp-runs");
  if (!box || !XP.doc) return;
  const cur = S("out_dir");
  let h = `<div class="row"><span class="hint" style="flex:1" title="${esc(XP.runsDir)}">${esc(XP.runsDir)}</span><button type="button" id="xp-run-folder" class="small">Open folder</button></div>` +
    `<div class="row wrap"><label class="inline xp-f">Description<input type="text" id="xp-run-desc" style="width:160px" placeholder="short description"></label>` +
    `<label class="inline xp-f">Notes<input type="text" id="xp-run-notes" style="width:160px"></label><button type="button" id="xp-run-new" title="Creates the numbered run folder and archives the source .inp in it">New run</button></div>`;
  h += `<table class="fa-tbl xp-runs"><tr><th>Run</th><th>Builds</th><th>Decks</th><th></th></tr>` +
    `<tr data-run=""${!cur ? ' class="sel"' : ""}><td colspan="3">(no run: decks next to the .inp)</td><td></td></tr>` +
    XP.runs.map(r => `<tr data-run="${esc(r.path)}"${r.path === cur ? ' class="sel"' : ""}><td title="${esc(r.description + (r.notes ? " | " + r.notes : ""))}">${esc(r.name)}</td><td>${r.builds}</td><td>${r.decks.length}</td>` +
      `<td><button type="button" class="small" data-rop="open">Open</button><button type="button" class="small" data-rop="clean" title="Delete the regenerable solver output (A-files, .vtk, .rst, T-files)">Clean…</button>` +
      `<button type="button" class="small" data-rop="settings" title="Restore the settings of the last build of the run">Settings</button></td></tr>`).join("") + `</table>`;
  const r = runOf(cur);
  if (r && r.decks.length) h += `<p class="hint">Decks: ${r.decks.map(d => `<a href="#" data-deck="${esc(d)}">${esc(d.split("/").pop())}</a>`).join(", ")}</p>`;
  box.innerHTML = h;
  $("#xp-run-folder").onclick = () => postJSON("/api/explicit/open_folder", { path: XP.runsDir }).catch(showErr);
  $("#xp-run-new").onclick = async () => {
    const d = $("#xp-run-desc").value.trim();
    if (!d) { status("Enter a short description of the run", true); return; }
    try {
      if (XP.dirty && FM.isSaved()) await saveDoc(XP.doc.name);
      const j = await (await postJSON("/api/explicit/run/new", req({ description: d, notes: $("#xp-run-notes").value }))).json();
      setS("out_dir", j.run);
      XP.runs = j.runs;
      renderRuns(); renderBuild(); renderResultsJobs();
      status("Run folder " + j.run);
    } catch (e) { showErr(e); }
  };
  box.querySelectorAll("tr[data-run]").forEach(tr => tr.onclick = async e => {
    const path = tr.dataset.run;
    const b = e.target.closest("button[data-rop]");
    if (b) {
      if (b.dataset.rop === "open") postJSON("/api/explicit/open_folder", { path }).catch(showErr);
      if (b.dataset.rop === "clean") {
        try {
          const j = await (await postJSON("/api/explicit/run/clean", { path })).json();
          if (!j.files) { status("Nothing to clean in " + path.split("/").pop()); return; }
          const where = Object.entries(j.folders).map(([k, v]) => `  ${k}: ${v} file(s)`).join("\n");
          if (!confirm(`Delete ${j.files} regenerable output file(s) (${j.mb.toFixed(1)} MB) from ${path.split("/").pop()} and its build folders?\n\n${where}\n\nDecks, model/, run.json, CSVs and PNGs are kept.`)) return;
          await postJSON("/api/explicit/run/clean", { path, confirm: true });
          refreshRuns();
        } catch (err) { showErr(err); }
      }
      if (b.dataset.rop === "settings") {
        try {
          const j = await (await postJSON("/api/explicit/run/settings", { path })).json();
          const skip = new Set(["project_dir", "out_dir", "inp_path", "rad_target", ...XP.meta.env_keys, "job_queue", "self_contact"]);
          for (const [k, v] of Object.entries(j.settings)) if (!skip.has(k) && (k in XP.meta.defaults || k === "mat_slots")) XP.doc.settings[k] = v;
          if (!j.settings.mat_slots && j.settings.mat1 !== undefined) XP.doc.settings.mat_slots = [1, 2, 3].map(i => [j.settings["mat" + i], j.settings["mat" + i + "_name"]]);
          changed(); renderBuild(); status("Settings of the last build of " + path.split("/").pop() + " restored (paths unchanged)");
        } catch (err) { showErr(err); }
      }
      return;
    }
    setS("out_dir", path);
    const r = runOf(path);
    if (r && r.decks.length) setS("rad_target", r.decks[r.decks.length - 1]);
    renderRuns(); renderBuild(); renderSolve(); renderResultsJobs();
  });
  box.querySelectorAll("[data-deck]").forEach(a => a.onclick = e => { e.preventDefault(); setS("rad_target", a.dataset.deck); renderSolve(); });
}

// ------------------------------------------------------------------ Build panel

function renderBuild() {
  const box = section("xp-buildp");
  if (!box || !XP.doc) return;
  const M = XP.meta;
  const mode = S("analysis_mode");
  const spec = M.mode_spec[mode] || {};
  const rbvs = spec.rbv_values || M.rbv_modes;
  let h = `<div class="row">${selS("analysis_mode", "Analysis", M.analysis_modes)}</div><p class="hint">${esc(M.mode_help[mode] || "")}</p>`;
  const inp = isModel() ? "(model .inp of the document: Write .inp)" : ((XP.doc.source || {}).inp || "(choose the .inp in Model)");
  h += `<p class="hint">Source .inp: ${esc(inp)}<br>Output Dir: ${esc(S("out_dir") || "(next to the .inp)")}</p>`;
  h += `<div class="row wrap">${inS("tstop", "Time (Tstop) [s]", 60)}${inS("anim_frames", "Frames", 46)}${inS("fric", "Fric", 46)}` +
    `${inS("dt_min", "Min dt [s]", 70, "Mass scaling floor (/DT/NODA/CST DTmin); 0 = off")}${inS("dt_target_dmm", "target DM/M %", 36)}` +
    `<button type="button" id="xp-mindt" class="small" title="Reads the /DT/NODA/CST added-mass table of the starter output of the Target .rad (Run Starter Only)">Suggest Min dt…</button></div>`;
  if (!hidden("floor")) h += `<div class="row wrap">${selS("test_mode", "Rigid floor", M.test_modes)}${S("test_mode").includes("Rigid Floor") ? inS("floor_z", "Floor Z [mm]", 60) : ""}<span class="hint">infinite /RWALL/PLANE, normal +Z, uses Fric</span></div>`;
  // library materials
  const auto = isModel() ? libSlotsOfModel() : [];
  const slots = S("mat_slots") || XP.meta.slots_default;
  h += `<h3 class="xp-h">Library materials</h3><table class="fa-tbl xp-slots"><tr><th>Library</th><th>Name in model</th><th></th></tr>` +
    auto.map(([l, n]) => `<tr class="ro"><td>${esc(l)}</td><td>${esc(n)}</td><td class="hint">Model</td></tr>`).join("") +
    slots.map(([l, n], i) => `<tr data-slot="${i}"><td><select data-sl="0">${optList([M.library_none, ...Object.keys(M.library)], l)}</select></td>` +
      `<td><input type="text" data-sl="1" value="${esc(n)}" style="width:90px"></td><td><button type="button" class="small" data-sldel="${i}">×</button></td></tr>`).join("") +
    `</table><div class="row"><button type="button" id="xp-slot-add" class="small">Add slot</button></div>`;
  // failure
  const fm = S("fail_model");
  h += `<h3 class="xp-h">Failure</h3><div class="row wrap">${selS("fail_model", "Model", M.fail_models)}${inS("fail_strain", "Plastic fail strain", 50)}</div>`;
  if (fm === M.fail_models[1]) h += `<div class="row wrap">JC:${["jc_d1", "jc_d2", "jc_d3", "jc_d4", "jc_d5"].map((k, i) => inS(k, "D" + (i + 1), 44)).join("")}${inS("jc_eps0", "eps0", 40)}${inS("jc_ifail_sh", "Ifail_sh", 30)}</div>`;
  if (fm === M.fail_models[2]) h += `<div class="row wrap">TENS:${inS("ts_et1", "et1", 50)}${inS("ts_et2", "et2", 50)}${inS("ts_soften", "SoftBand", 40)}${inS("ts_sflag", "S_Flag", 30)}${inS("ts_failip", "FAILIP", 30)}</div>`;
  h += `<p class="hint">${esc(M.fail_hint[fm] || "")}</p>`;
  // options
  h += `<div class="row wrap">${chkS("gravity", "Gravity")}${selS("contact_mode", "Contact", M.contact_modes)}${chkS("build_subdirs", "Subfolder per build")}</div><p class="hint">${esc(M.contact_hint[S("contact_mode")] || "")}</p>`;
  // loading
  const rv = rbvs.includes(S("rigid_vel_mode")) ? S("rigid_vel_mode") : S("rigid_vel_mode");
  h += `<h3 class="xp-h">Loading (rigid-body driver)</h3><div class="row wrap">${selS("rigid_vel_mode", "Driver", rbvs.includes(rv) ? rbvs : [...rbvs, rv])}`;
  if (rv === M.rbv_modes[0]) h += inS("rigid_vel", "Vx Vy Vz [mm/s]", 110);
  h += `</div>`;
  if (!hidden("target_rp")) h += `<div class="row">${inS("rigid_rp_target", "Target RP", 120)}<span class="hint">/RBODY name or id (blank = the single RBODY)</span></div>`;
  if (rv === M.rbv_modes[1] || rv === M.rbv_modes[2]) {
    h += `<div class="row wrap">${inS("lhu_peak", rv === M.rbv_modes[2] ? "Peak force" : "Peak disp", 56)}${selS("lhu_dir", "Dir", ["X", "Y", "Z"])}${inS("lhu_rampup", "Ramp up [s]", 44)}` +
      `${inS("lhu_hold", "Hold [s]", 44)}${inS("lhu_rampdn", "Ramp down [s]", 44)}${inS("lhu_settle", "Settle [s]", 44)}${selS("lhu_easing", "Ease", M.lhu_easings)}${inS("lhu_npramp", "Pts/ramp", 36)}</div>`;
  }
  if (!hidden("rigidify")) h += `<div class="row">${inS("rigid_part", "Rigidify part(s)", 160, "PID or part name substring; comma between several (blank = off)")}<button type="button" class="small" id="xp-listparts" title="Lists PID: name of the /PART cards of the Target .rad (or the newest deck in Output Dir) in the console">List Parts</button></div>`;
  if (!hidden("point_mass")) h += `<div class="row">${inS("point_mass_json", "Concentrated mass JSON", 200, "inertia_builder / inertia_calc payload or primitives file (blank = off)")}</div>`;
  h += `<p class="hint">${esc(M.rbv_hint[rv] || "")}</p>`;
  // ties
  const tm = S("tie_mode");
  h += `<h3 class="xp-h">Ties (bonded connections)</h3><div class="row wrap">${selS("tie_mode", "Tie Mode", M.tie_modes)}${tm !== M.tie_modes[3] ? inS("tie_dist", tm === M.tie_modes[0] ? "Fallback dist [mm]" : "Tie dist [mm]", 50) : ""}</div>`;
  if (tm === M.tie_modes[1]) h += `<textarea data-s="tie_pairs" rows="3" style="width:100%" placeholder="secondary > master : distance">${esc(S("tie_pairs"))}</textarea>`;
  h += `<p class="hint">${esc(M.tie_hint[tm] || "")}</p>`;
  if (!hidden("advanced")) h += `<h3 class="xp-h">Advanced / niche options</h3><div class="row wrap">${chkS("align_norms", "Heal Normals")}${chkS("apply_vel_model", "Disp -> Velocity")}${chkS("purge_prev", "Purge older builds")}${chkS("downgrade_quad", "Downgrade 2nd-order → linear")}</div>`;
  const notes = hiddenActive();
  if (notes.length) h += `<p class="fa-pick">Hidden by the analysis type but active at build time: ${esc(notes.join("; "))}</p>`;
  h += `<div class="row"><button type="button" id="xp-build2" class="primary" title="BUILD RADIOSS DECK: inp2rad and the cards of these settings; decks into the run folder">Build deck</button></div>`;
  box.innerHTML = h;
  bindFields(box, k => { if (["analysis_mode", "fail_model", "tie_mode", "rigid_vel_mode", "test_mode", "contact_mode"].includes(k)) renderBuild(); });
  box.querySelectorAll("tr[data-slot]").forEach(tr => tr.querySelectorAll("[data-sl]").forEach(el => el.onchange = () => {
    const sl = (S("mat_slots") || XP.meta.slots_default).map(x => x.slice());
    sl[+tr.dataset.slot][+el.dataset.sl] = el.value.trim();
    setS("mat_slots", sl);
  }));
  box.querySelectorAll("[data-sldel]").forEach(b => b.onclick = () => { const sl = (S("mat_slots") || XP.meta.slots_default).map(x => x.slice()); sl.splice(+b.dataset.sldel, 1); setS("mat_slots", sl); renderBuild(); });
  $("#xp-slot-add").onclick = () => { const sl = (S("mat_slots") || XP.meta.slots_default).map(x => x.slice()); sl.push([XP.meta.library_none, ""]); setS("mat_slots", sl); renderBuild(); };
  $("#xp-build2").onclick = build;
  $("#xp-mindt").onclick = suggestMinDt;
  if ($("#xp-listparts")) $("#xp-listparts").onclick = () => postJSON("/api/explicit/list_parts", req()).then(poll).catch(showErr);
}
function libSlotsOfModel() {
  const out = [];
  for (const [n, m] of Object.entries(XP.doc.materials || {})) if (m.library && XP.meta.library[m.library]) out.push([m.library, n.replace(/[^A-Za-z0-9_]+/g, "_").toUpperCase()]);
  return out;
}
/** Hidden fields of the analysis type that still act at build time (ORC**3 MK2 rule). */
function hiddenActive() {
  const out = [];
  if (hidden("floor") && S("test_mode").includes("Rigid Floor")) out.push("rigid floor");
  if (hidden("rigidify") && String(S("rigid_part") || "").trim()) out.push("Rigidify part(s) " + S("rigid_part"));
  if (hidden("point_mass") && String(S("point_mass_json") || "").trim()) out.push("concentrated mass");
  if (hidden("target_rp") && String(S("rigid_rp_target") || "").trim()) out.push("Target RP " + S("rigid_rp_target"));
  if (hidden("advanced")) {
    if (S("purge_prev")) out.push("Purge older builds");
    if (S("downgrade_quad")) out.push("Downgrade 2nd-order");
    if (!S("align_norms")) out.push("Heal Normals off");
    if (!S("apply_vel_model")) out.push("Disp -> Velocity off");
  }
  const spec = XP.meta.mode_spec[S("analysis_mode")] || {};
  if (spec.rbv_values && !spec.rbv_values.includes(S("rigid_vel_mode"))) out.push("Driver " + S("rigid_vel_mode"));
  return out;
}
async function build() {
  try {
    if (XP.dirty && FM.isSaved()) await saveDoc(XP.doc.name);
    await postJSON("/api/explicit/build", req());
    status("Build started (Console)");
    openSection("xp-sec-console");
    poll();
  } catch (e) { showErr(e); }
}
async function suggestMinDt() {
  const rad = S("rad_target");
  if (!rad) { status("Set the Target .rad (Solve) and run the starter first", true); return; }
  try {
    const j = await (await postJSON("/api/explicit/post", req({ op: "min_dt", job: rad.split("/").pop().replace(/_0000\.rad$/, ""), folder: rad.replace(/\/[^/]*$/, "") }))).json();
    offerMinDt(j.offer);
  } catch (e) { showErr(e); }
}
function offerMinDt(o) {
  if (!o) return;
  if (o.error) { alert("Suggest Min dt\n\n" + o.error); return; }
  const rows = o.rows.map(r => `    ${fmt(r.dmm * 100, 3)}%   ->   ${fmt(r.dt_09, 4)} s (0.9)   |   ${fmt(r.dt_067, 4)} s (0.67)`).join("\n");
  const floor = o.floor ? `Natural nodal-dt floor: ${fmt(o.floor, 4)} s (Min dt below this adds NO mass, but runs slowest).\n` : "";
  if (confirm(`File: ${o.file.split(/[\\/]/).pop()}\n${floor}\n/DT/NODA/CST first-cycle estimate (0.9 | 0.67):\n${rows}\n\n` +
              `For target ${fmt(o.target_pct, 3)}% first-cycle added mass:\n    Recommended Min dt = ${fmt(o.dt, 4)} s\n    (${o.note})\n\n` +
              `NOTE: this is a FIRST-CYCLE estimate. Deformation and contact make added mass GROW during the run, so treat it as a lower bound and watch the live DM/M column.\n\nSet Min dt to ${fmt(o.dt, 4)} now?`)) {
    setS("dt_min", String(o.dt));
    renderBuild();
    status(`Min dt = ${fmt(o.dt, 4)} s (target ${fmt(o.target_pct, 3)}%)`);
  }
}

// ------------------------------------------------------------------ Solve panel

function renderExecInfo() {
  const el = $("#xp-execinfo");
  if (!el || !XP.envInfo) return;
  const ex = E("run_target") === XP.meta.remote ? {} : (XP.envInfo.executables || {});
  el.innerHTML = Object.entries(ex).map(([k, v]) => `${esc(k)}: ${v.found ? esc(v.found) : `<span class="xp-bad">${esc(v.exe)} not found</span>`}`).join("<br>") +
    (Object.keys(ex).length ? "<br>" : "") + `pvbatch: ${XP.envInfo.pvbatch ? esc(XP.envInfo.pvbatch) : "not found"}; paraview: ${XP.envInfo.paraview ? esc(XP.envInfo.paraview) : "not found"}` +
    (XP.envInfo.from_orc3 ? `<br>Machine settings read from ${esc(XP.envInfo.from_orc3)}` : "");
}
function renderSolve() {
  const box = section("xp-solvep");
  if (!box || !XP.doc || !XP.env) return;
  const r = runOf(S("out_dir"));
  const decks = r ? r.decks : [];
  const tgt = S("rad_target");
  const remote = E("run_target") === XP.meta.remote;
  let h = `<div class="row"><label class="inline" style="flex:1">Target .rad<input type="text" data-s="rad_target" value="${esc(tgt)}" style="flex:1;width:auto"></label>` +
    (decks.length ? `<select id="xp-decks" title="Decks of the selected run"><option value="">decks…</option>${optList(decks.map(d => [d, d.split("/").pop()]), "")}</select>` : "") + `</div>`;
  h += `<div class="row wrap"><label class="inline xp-f">Env<select data-e="run_target">${optList([[XP.meta.local, "Local"], [XP.meta.remote, "Remote (Linux)"]], E("run_target"))}</select></label>` +
    `${inE("ssh_threads", "Threads", 30)}${chkE("stream_remote", "Stream remote output")}${chkS("plot_ke", "Plot KE")}${chkS("extract_strains", "Extract Strains")}${chkS("pv_images", "PV Images")}</div>`;
  if (!remote) h += `<div class="row">${inE("or_exec", "OpenCourant exec folder", 260, "Folder of starter_win64, engine_win64, anim_to_vtk_win64, th_to_csv_win64 (empty: the exec folder of a package in the solvers folder of the program, else PATH)", "folder")}</div>`;
  else h += `<div class="row wrap">${inE("ssh_host", "Server (user@host)", 150)}${inE("ssh_port", "SSH Port", 40)}</div>` +
    `<div class="row wrap">${inE("remote_env", "Env script", 160)}${inE("remote_exec", "Exec dir", 200)}</div>` +
    `<div class="row wrap">${inE("remote_scratch", "Scratch dir", 160)}${inE("share_map", "Share map", 200, "WIN => LINUX; ';' separated. No match = SCP to scratch")}</div>`;
  h += `<div class="row wrap">${inE("pvbatch_path", "pvbatch", 180, "pvbatch.exe of ParaView (empty: searched)", "open")}${inE("paraview_path", "paraview", 180, "paraview.exe (empty: next to pvbatch, or searched)", "open")}</div>`;
  h += `<p class="hint" id="xp-execinfo"></p>`;
  h += `<div class="row wrap"><button type="button" class="primary" id="xp-run2">Run Simulation</button><button type="button" id="xp-starter2" title="Starter only: writes the /DT/NODA/CST added-mass table and offers a Min dt">Run Starter Only</button>` +
    `<button type="button" id="xp-kill2" class="xp-kill">Kill</button>${remote ? `<button type="button" id="xp-shutdown">Shutdown Server</button>` : ""}</div>`;
  h += `<div class="row wrap">Queue: <button type="button" class="small" data-q="add">Add Current</button><button type="button" class="small" data-q="remove">Remove Selected</button><button type="button" class="small" data-q="clear">Clear List</button>` +
    (remote ? ` | Server: <button type="button" class="small" data-srv="show">Show Queue</button><button type="button" class="small" data-srv="clear">Kill+Flush Server</button>` : "") + `</div>`;
  h += `<div id="xp-board"></div>`;
  h += `<details class="xp-hist"><summary class="sk-h">Run history</summary><div id="xp-history"></div></details>`;
  box.innerHTML = h;
  bindFields(box, k => { if (k === "run_target") renderSolve(); });
  if ($("#xp-decks")) $("#xp-decks").onchange = () => { if ($("#xp-decks").value) { setS("rad_target", $("#xp-decks").value); renderSolve(); } };
  $("#xp-run2").onclick = () => solve("run");
  $("#xp-starter2").onclick = () => solve("starter");
  $("#xp-kill2").onclick = kill;
  if ($("#xp-shutdown")) $("#xp-shutdown").onclick = () => { if (confirm("Are you sure you want to power off the remote server?")) postJSON("/api/explicit/server", { op: "shutdown" }).then(poll).catch(showErr); };
  box.querySelectorAll("[data-q]").forEach(b => b.onclick = async () => {
    if (b.dataset.q === "remove" && !XP.boardSel) { status("Select a queued deck or a finished status row", true); return; }
    try { await postJSON("/api/explicit/queue", req({ op: b.dataset.q, key: XP.boardSel })); XP.boardSel = null; poll(); } catch (e) { showErr(e); }
  });
  box.querySelectorAll("[data-srv]").forEach(b => b.onclick = () => {
    if (b.dataset.srv === "clear" && !confirm("This kills any running OpenCourant job on the server and flushes the task-spooler queue. Continue?")) return;
    postJSON("/api/explicit/server", { op: b.dataset.srv }).then(poll).catch(showErr);
  });
  renderExecInfo();
  renderBoard();
}
async function solve(mode) {
  if (!S("rad_target") && !(XP.status && XP.status.queue.length)) { status("Set the Target .rad (Build, or a deck of the run)", true); return; }
  try {
    if (XP.dirty && FM.isSaved()) await saveDoc(XP.doc.name);
    await postJSON("/api/explicit/solve", req({ mode }));
    status(mode === "starter" ? "Starter started" : "Run started");
    poll();
  } catch (e) { showErr(e); }
}
function kill() { postJSON("/api/explicit/kill", { env: E("run_target") }).then(poll).catch(showErr); }
function renderBoard() {
  const box = $("#xp-board");
  if (!box) return;
  const st = XP.status;
  const rows = st ? st.rows : [];
  let h = `<table class="fa-tbl xp-board"><tr><th>Job</th><th>Status</th><th>Progress</th><th>T / Tstop</th><th>ETA</th><th>ERR</th><th>DM/M</th></tr>`;
  if (st && st.server_queue) h += st.server_queue.map(l => `<tr><td colspan="7" class="xp-mono">${esc(l)}</td></tr>`).join("");
  h += rows.map(r => `<tr data-key="${esc(r.id)}" class="xp-${r.tag}${XP.boardSel === r.id ? " sel" : ""}"><td title="${esc(r.folder)}">${esc(r.job)}${r.note ? ` <span class="hint">(${esc(r.note)})</span>` : ""}</td>` +
    `<td>${esc(r.status)}</td><td>${r.progress === null || r.progress === undefined ? "" : `<span class="xp-prog"><span style="width:${r.progress.toFixed(0)}%"></span></span> ${r.progress.toFixed(0)}%`}</td>` +
    `<td>${r.t !== null && r.t !== undefined ? fmt(r.t, 4) : "-"} / ${r.tstop ? fmt(r.tstop, 4) : "?"}</td><td>${esc(r.eta_text || "")}</td>` +
    `<td>${r.err !== null && r.err !== undefined ? (r.err > 0 ? "+" : "") + r.err.toFixed(1) + "%" : ""}</td><td>${r.dmm !== null && r.dmm !== undefined ? Number(r.dmm).toExponential(1) : ""}</td></tr>`).join("");
  h += `</table>`;
  if (!rows.length && !(st && st.server_queue)) h = `<p class="hint">No jobs. Run Simulation runs the Target .rad (or the queue).</p>`;
  box.innerHTML = h;
  box.querySelectorAll("tr[data-key]").forEach(tr => tr.onclick = () => {
    XP.boardSel = tr.dataset.key;
    const r = rows.find(x => x.id === XP.boardSel);
    if (r && r.id.startsWith("s::") && r.folder) selectResult(r.folder, r.job);
    renderBoard();
  });
  const hb = $("#xp-history");
  if (hb && st) hb.innerHTML = st.history.length ? `<table class="fa-tbl"><tr><th>Job</th><th>Date</th><th>Status</th><th>Env</th><th>ERR</th><th>DM/M</th><th>Wall</th></tr>` +
    st.history.map(e => `<tr data-hf="${esc(e.folder)}" data-hj="${esc(e.job)}"><td title="${esc(e.folder)}">${esc(e.job)}</td><td>${esc(e.date)}</td><td>${esc(e.status)}</td><td>${esc(e.env)}</td>` +
      `<td>${e.err !== null && e.err !== undefined ? e.err.toFixed(1) + "%" : ""}</td><td>${e.dmm !== null && e.dmm !== undefined ? Number(e.dmm).toExponential(1) : ""}</td><td>${e.elapsed ? fmt(e.elapsed, 4) + " s" : ""}</td></tr>`).join("") + `</table>` : `<p class="hint">No finished jobs.</p>`;
  if (hb) hb.querySelectorAll("tr[data-hf]").forEach(tr => tr.onclick = () => selectResult(tr.dataset.hf.replace(/\\/g, "/"), tr.dataset.hj));
}

// ------------------------------------------------------------------ Results panel

/** Jobs for the Results job list: the decks of the selected run and the jobs of the status board. */
function resultJobs() {
  const out = [], seen = new Set();
  const add = (folder, job) => { const k = folder + "|" + job; if (!seen.has(k) && folder && job) { seen.add(k); out.push({ folder, job }); } };
  const r = runOf(S("out_dir"));
  for (const d of (r ? r.decks : [])) add(d.replace(/\/[^/]*$/, ""), d.split("/").pop().replace(/_0000\.rad$/, ""));
  for (const row of (XP.status ? XP.status.rows : [])) if (row.id.startsWith("s::")) add(row.folder, row.job);
  if (XP.res.folder && XP.res.job) add(XP.res.folder, XP.res.job);
  return out;
}
function renderResultsJobs() {
  const sel = $("#xp-resjob");
  if (!sel) return;
  const jobs = resultJobs();
  const cur = XP.res.folder + "|" + XP.res.job;
  sel.innerHTML = `<option value="">(job)</option>` + jobs.map(j => `<option value="${esc(j.folder + "|" + j.job)}"${j.folder + "|" + j.job === cur ? " selected" : ""} title="${esc(j.folder)}">${esc(j.job)}</option>`).join("");
}
function renderResults() {
  const box = section("xp-results");
  if (!box || !XP.doc) return;
  const d = XP.res.data;
  let h = `<div class="row"><label class="inline" style="flex:1">Job<select id="xp-resjob" style="flex:1"></select></label><button type="button" id="xp-resload" class="small" title="Reload the frames and curves">↻</button></div>`;
  h += `<div class="row wrap">` +
    [["plot_ke", "Plot KE", "Rebuild the KE curve and PNG from the results CSV"], ["salvage", "Salvage Results", "Convert the A-files and T01 of a killed job, rebuild the .vtk.series and CSV"],
     ["extract", "Extract Strains", "pvbatch: max principal strain summary of the .vtk.series of the folder"], ["images", "PV Images", "pvbatch: PNG renders of the last frame and the peak frame"],
     ["paraview", "Open in ParaView", "ParaView with the session script of the job"], ["macro", "Install PV Macro", "Eps1_View macro in the ParaView Macros folder"],
     ["min_dt", "Suggest Min dt", "Added-mass table of the starter output of the job"]]
      .map(([op, t, ti]) => `<button type="button" class="small" data-post="${op}" title="${esc(ti)}">${esc(t)}</button>`).join("") + `</div>`;
  if (d) {
    h += `<div class="xp-plotbar"><label class="check inline"><input type="checkbox" id="xp-ke" checked> Kinetic</label><label class="check inline"><input type="checkbox" id="xp-ie"> Internal</label><label class="check inline"><input type="checkbox" id="xp-tot"> KE+IE</label></div>`;
    h += d.energy ? `<div id="xp-plot" class="xp-plot"></div>` + (d.energy.note ? `<p class="hint">${esc(d.energy.note)}</p>` : "") : `<p class="hint">No results CSV of ${esc(d.job)}.</p>`;
    h += `<p class="hint">${d.frames.length} frame(s)` + (d.outs["0000"] ? ` · <a href="#" data-out="0000">starter .out</a>` : "") + (d.outs["0001"] ? ` · <a href="#" data-out="0001">engine .out</a>` : "") +
      ` · <a href="#" data-out="settings">settings report</a> · <a href="#" data-folder="1">open folder</a></p>`;
    if (d.strains && d.strains.length > 1) h += `<div class="fa-wide"><table class="fa-tbl"><tr>${d.strains[0].map(c => `<th>${esc(c)}</th>`).join("")}</tr>` + d.strains.slice(1).map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("") + `</table></div>`;
  } else h += `<p class="hint">Choose a job of the run, or click a row of the status board.</p>`;
  box.innerHTML = h;
  renderResultsJobs();
  $("#xp-resjob").onchange = () => { const v = $("#xp-resjob").value; if (v) { const i = v.lastIndexOf("|"); selectResult(v.slice(0, i), v.slice(i + 1)); } };
  $("#xp-resload").onclick = () => { if (XP.res.job) selectResult(XP.res.folder, XP.res.job, true); };
  box.querySelectorAll("[data-post]").forEach(b => b.onclick = () => postOp(b.dataset.post));
  for (const id of ["#xp-ke", "#xp-ie", "#xp-tot"]) if ($(id)) $(id).onchange = plotEnergy;
  box.querySelectorAll("[data-out]").forEach(a => a.onclick = e => {
    e.preventDefault();
    const k = a.dataset.out;
    showText(k === "settings" ? `${XP.res.folder}/${XP.res.job}_settings.txt` : `${XP.res.folder}/${XP.res.job}_${k}.out`);
  });
  box.querySelectorAll("[data-folder]").forEach(a => a.onclick = e => { e.preventDefault(); postJSON("/api/explicit/open_folder", { path: XP.res.folder }).catch(showErr); });
  plotEnergy();
}
async function postOp(op) {
  const needJob = !["macro", "extract"].includes(op);
  if (needJob && !XP.res.job) { status("Choose a job in Results", true); return; }
  try {
    const folder = XP.res.folder || S("out_dir");
    const j = await (await postJSON("/api/explicit/post", req({ op, job: XP.res.job, folder }))).json();
    if (op === "min_dt") offerMinDt(j.offer);
    poll();
    openSection("xp-sec-console");
  } catch (e) { showErr(e); }
}
async function showText(path) {
  try {
    const j = await (await postJSON("/api/explicit/text", { path })).json();
    const w = window.open("", "_blank");
    if (w) { w.document.title = path.split("/").pop(); w.document.body.innerHTML = `<pre style="font:12px Consolas,monospace;white-space:pre-wrap">${esc((j.cut ? "(last part of the file)\n" : "") + j.text)}</pre>`; }
  } catch (e) { showErr(e); }
}
async function selectResult(folder, job, reload) {
  if (!folder || !job) return;
  if (!reload && XP.res.folder === folder && XP.res.job === job && XP.res.data) return;
  XP.res = { folder, job, data: null, geo: null, frame: null, k: 0, playing: false };
  try {
    XP.res.data = await (await postJSON("/api/explicit/results", { folder, job })).json();
  } catch (e) { showErr(e); }
  renderResults();
  if (XP.res.data && XP.res.data.frames.length) {
    try {
      XP.res.geo = await (await postJSON("/api/explicit/geometry", { folder, job })).json();
      const fs = $("#xp-field");
      const cur = fs.value;
      fs.innerHTML = XP.res.geo.fields.map(f => `<option value="${esc(f.key)}">${esc(f.label)}</option>`).join("");
      const pref = XP.res.geo.fields.find(f => f.key === cur) || XP.res.geo.fields.find(f => /Strain.*\|eps1$/i.test(f.key)) ||
        XP.res.geo.fields.find(f => /Von_Mises|VONM/i.test(f.key)) || XP.res.geo.fields.find(f => /Displacement\|mag/.test(f.key));
      if (pref) fs.value = pref.key;
      const sl = $("#xp-frame");
      sl.max = XP.res.geo.frames.length - 1;
      sl.value = sl.max;
      if (XP.three) XP.three.zoomed = false;
      await loadFrame(+sl.value);
      $("#xp-show").value = "results";
      draw();
    } catch (e) { showErr(e); }
  } else if ($("#xp-show").value === "results") { $("#xp-show").value = XP.mesh ? "mesh" : "model"; draw(); }
}
async function loadFrame(k) {
  if (!XP.res.geo) return;
  const f = await (await postJSON("/api/explicit/frame", { folder: XP.res.folder, job: XP.res.job, index: k, field: $("#xp-field").value })).json();
  XP.res.frame = f; XP.res.k = f.index;
  const fr = XP.res.geo.frames[f.index];
  $("#xp-ftime").textContent = `${f.index + 1}/${XP.res.geo.frames.length}` + (f.time !== null && f.time !== undefined ? ` t=${fmt(f.time, 4)} s` : "");
  if (fr) $("#xp-frame").value = f.index;
}
async function play() {
  if (XP.res.playing) { XP.res.playing = false; $("#xp-play").textContent = "▶"; return; }
  if (!XP.res.geo) return;
  XP.res.playing = true; $("#xp-play").textContent = "■";
  const n = XP.res.geo.frames.length;
  let k = XP.res.k >= n - 1 ? 0 : XP.res.k + 1;
  while (XP.res.playing && k < n) {
    try { await loadFrame(k); draw(); } catch (e) { showErr(e); break; }
    await new Promise(r => setTimeout(r, 120));
    k++;
  }
  XP.res.playing = false; $("#xp-play").textContent = "▶";
}

/** KE / IE / KE+IE curves of the results CSV as SVG. */
function plotEnergy() {
  const box = $("#xp-plot");
  const en = XP.res.data && XP.res.data.energy;
  if (!box || !en) return;
  const series = [];
  if ($("#xp-ke").checked) series.push(["Kinetic", en.ke, "#1f5fae"]);
  if ($("#xp-ie").checked && en.ie) series.push(["Internal", en.ie, "#e8590c"]);
  if ($("#xp-tot").checked && en.ie) series.push(["KE+IE", en.ke.map((v, i) => v + en.ie[i]), "#2f9e44"]);
  const W = Math.max(280, box.clientWidth || 440), H = 210, L = 58, R = 10, T = 12, B = 30;
  const t = en.t;
  const x0 = Math.min(...t), x1 = Math.max(...t) || 1;
  let y0 = Infinity, y1 = -Infinity;
  for (const [, v] of series) for (const y of v) { if (y < y0) y0 = y; if (y > y1) y1 = y; }
  if (!isFinite(y0)) { y0 = 0; y1 = 1; }
  if (y0 > 0) y0 = 0;
  if (y1 === y0) y1 = y0 + 1;
  const X = v => L + (v - x0) / ((x1 - x0) || 1) * (W - L - R), Y = v => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  let s = `<svg width="${W}" height="${H}" class="xp-svg">`;
  for (let k = 0; k <= 4; k++) {
    const yv = y0 + (y1 - y0) * k / 4, xv = x0 + (x1 - x0) * k / 4;
    s += `<line x1="${L}" x2="${W - R}" y1="${Y(yv)}" y2="${Y(yv)}" class="g"/><text x="${L - 4}" y="${Y(yv) + 4}" text-anchor="end">${fmt(yv, 3)}</text>`;
    s += `<line y1="${T}" y2="${H - B}" x1="${X(xv)}" x2="${X(xv)}" class="g"/><text x="${X(xv)}" y="${H - B + 14}" text-anchor="middle">${fmt(xv, 3)}</text>`;
  }
  s += `<text x="${W - R}" y="${H - 3}" text-anchor="end">Time (s)</text><text x="4" y="10">Energy (mJ)</text>`;
  series.forEach(([name, v, col], i) => {
    s += `<polyline fill="none" stroke="${col}" stroke-width="1.6" points="${t.map((tv, k) => X(tv).toFixed(1) + "," + Y(v[k]).toFixed(1)).join(" ")}"/>`;
    s += `<text x="${W - R - 4}" y="${T + 12 + 13 * i}" text-anchor="end" fill="${col}">${esc(name)}</text>`;
  });
  const f = XP.res.frame;
  if (f && f.time !== null && f.time !== undefined) s += `<line x1="${X(f.time)}" x2="${X(f.time)}" y1="${T}" y2="${H - B}" stroke="#f08c00" stroke-dasharray="3,3"/>`;
  box.innerHTML = s + `</svg>`;
}

// ------------------------------------------------------------------ console and status

function renderConsole() {
  const box = section("xp-console");
  if (!box) return;
  box.innerHTML = `<div class="row"><input type="text" id="xp-cfind" placeholder="find" style="width:140px"><button type="button" class="small" id="xp-cclear">Clear</button>` +
    `<label class="check inline"><input type="checkbox" id="xp-cfollow" checked> Follow</label></div><pre id="xp-log" class="xp-log"></pre>`;
  $("#xp-cclear").onclick = async () => { XP.logLines = []; $("#xp-log").textContent = ""; try { await postJSON("/api/explicit/console/clear", {}); } catch (e) { /* ignore */ } };
  $("#xp-cfind").oninput = writeLog;
  writeLog();
}
function writeLog() {
  const el = $("#xp-log");
  if (!el) return;
  const q = ($("#xp-cfind") && $("#xp-cfind").value || "").toLowerCase();
  const lines = q ? XP.logLines.filter(l => l.toLowerCase().includes(q)) : XP.logLines;
  el.textContent = lines.join("\n");
  if ($("#xp-cfollow") && $("#xp-cfollow").checked) el.scrollTop = el.scrollHeight;
}
let pollTimer = null, polling = false;
async function poll() {
  if (polling) return;
  polling = true;
  try {
    const st = await (await api("/api/explicit/status?since=" + XP.logSeq)).json();
    if (st.log.length) {
      for (const [, l] of st.log) XP.logLines.push(l);
      if (XP.logLines.length > 6000) XP.logLines.splice(0, XP.logLines.length - 6000);
      XP.logSeq = st.log_seq;
      writeLog();
      const last = st.log[st.log.length - 1][1].trim();
      if (last) $("#xp-last").textContent = last.slice(0, 160);
    } else XP.logSeq = st.log_seq;
    const prev = XP.status;
    XP.status = st;
    renderBoard();
    $("#xp-busy").textContent = (st.building ? "building " : "") + st.busy.map(b => b + " run").join(", ") + (st.tasks.length ? " " + st.tasks.join(", ") : "");
    // a finished build: the new deck is the Target .rad
    if (st.last_build && (!XP.lastBuild || XP.lastBuild.time !== st.last_build.time) && XP.doc) {
      const first = prev === null;
      XP.lastBuild = st.last_build;
      if (!first) { setS("rad_target", st.last_build.rad); await refreshRuns(); status("Deck built: " + st.last_build.rad); }
    }
    if (st.min_dt_offer && st.min_dt_offer.seq !== XP.offerSeq) {
      const first = XP.offerSeq === 0 && prev === null;
      XP.offerSeq = st.min_dt_offer.seq;
      if (!first) offerMinDt(st.min_dt_offer);
    }
    // a job that finished: its results
    for (const r of st.rows) {
      const p = XP.prevRows[r.id];
      if (p && p !== r.status && ["Done", "Failed", "Killed"].includes(r.status) && r.folder) {
        if (XP.res.job === r.job || !XP.res.job || r.status === "Done") selectResult(r.folder, r.job, true);
        refreshRuns();
      }
    }
    XP.prevRows = Object.fromEntries(st.rows.map(r => [r.id, r.status]));
    if (XP.res.job && XP.res.data) {
      const live = st.rows.find(r => r.job === XP.res.job && r.tag && ["running", "warn", "bad"].includes(r.tag));
      if (live && !XP.res.liveT) XP.res.liveT = setTimeout(() => { XP.res.liveT = null; }, 5000);
    }
  } catch (e) { /* server busy */ } finally { polling = false; }
}
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    const active = XP.status && (XP.status.busy.length || XP.status.building || XP.status.tasks.length);
    if (!$("#tab-xp").hidden || active) poll();
  }, 1000);
}
function openSection(id) { const d = $("#" + id); if (d) d.open = true; }

// ------------------------------------------------------------------ documents

function renderAllPanels() {
  if (!XP.doc || !XP.meta) return;
  renderModel(); renderRuns(); renderBuild(); renderSolve(); renderResults();
  $("#xp-supbtn").disabled = !isShiny();
  const mb = $("#xp-model-btn");
  (mb.querySelector(".tb-lbl") || mb).textContent = isModel() ? "Write .inp" : "Show mesh";
  $("#xp-model-btn").title = isDeck() ? "Mesh the deck (structured shells) and write the model .inp" : isShiny() ? "Mesh the bodies and write the model .inp" : "Show the mesh of the .inp";
}
let FM = null;
function refreshList() { if (FM) FM.refresh(); refreshSources(); refreshRuns(); }
async function refreshSources() {
  let asms = [], parts = [];
  try { asms = await (await api("/api/assembly/list")).json(); } catch (e) { /* none */ }
  try { parts = await (await api("/api/part/list")).json(); } catch (e) { /* none */ }
  const s = XP.doc ? XP.doc.source || {} : {};
  const cur = (s.kind || "shinycad") === "shinycad" && s.name ? s.type + ":" + s.name : "";
  const sel = $("#xp-source");
  sel.innerHTML = `<option value="">(geometry)</option>` +
    (asms.length ? `<optgroup label="Assemblies">${asms.map(n => `<option value="assembly:${esc(n)}">${esc(n)}</option>`).join("")}</optgroup>` : "") +
    (parts.length ? `<optgroup label="Parts">${parts.map(n => `<option value="part:${esc(n)}">${esc(n)}</option>`).join("")}</optgroup>` : "");
  if (cur && ![...sel.options].some(o => o.value === cur)) sel.insertAdjacentHTML("beforeend", `<option value="${esc(cur)}">${esc(s.name)} (missing)</option>`);
  sel.value = cur;
  sel.disabled = (s.kind || "shinycad") !== "shinycad";
}
async function loadDoc(d) {
  const b = blankDoc(d.name);
  for (const k of Object.keys(b)) if (d[k] === undefined) d[k] = b[k];
  XP.doc = d;
  XP.sel = null; XP.pick = null; XP.mesh = null; XP.meshSummary = null;
  XP.deckSel = new Set(); XP.deckCheck = null; XP.pattern = null; XP.deckStep = null;
  if ((d.source || {}).kind === "deck" && !d.deck && XP.meta) d.deck = JSON.parse(JSON.stringify(XP.meta.deck_default));
  XP.res = { folder: "", job: "", data: null, geo: null, frame: null, k: 0, playing: false };
  XP.dirty = false;
  if (XP.three) XP.three.zoomed = false;
  $("#xp-show").value = "model";
  if (FM) FM.render();
  await refreshSources();
  await loadGeometry();
  await refreshRuns();
  renderAllPanels();
  const rad = S("rad_target");
  if (rad && /_0000\.rad$/.test(rad)) selectResult(rad.replace(/\/[^/]*$/, ""), rad.split("/").pop().replace(/_0000\.rad$/, ""));
}
async function saveDoc(name) {
  XP.doc.name = name;
  const r = await api("/api/explicit/file/" + encodeURIComponent(name), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(XP.doc) });
  const j = await r.json();
  XP.dirty = false;
  status("Saved " + j.path);
  refreshRuns();
}

window.xpShown = async function () {
  try {
    if (!XP.meta) XP.meta = await (await api("/api/explicit/meta")).json();
    if (!XP.env) { XP.envInfo = await (await api("/api/explicit/env")).json(); XP.env = XP.envInfo.env; }
  } catch (e) { showErr(e); return; }
  if (!XP.three) initThree();
  if (!XP.consoleReady) { renderConsole(); XP.consoleReady = true; }
  if (!XP.doc) await loadDoc(blankDoc("explicit"));
  else { refreshList(); renderAllPanels(); }
  startPolling();
  poll();
  setTimeout(resize3, 0);
};

(function bindXp() {
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && XP.pick && !$("#tab-xp").hidden) { endPick(); status("Pick cancelled"); }
  });
  $("#xp-source").onchange = () => {
    const v = $("#xp-source").value;
    const i = v.indexOf(":");
    XP.doc.source = Object.assign({}, XP.doc.source, v ? { kind: "shinycad", type: v.slice(0, i), name: v.slice(i + 1) } : { kind: "shinycad", type: "assembly", name: "" });
    XP.mesh = null; XP.meshSummary = null;
    $("#xp-show").value = "model";
    changed(); loadGeometry();
  };
  $("#xp-model-btn").onclick = writeInp;
  $("#xp-build").onclick = build;
  $("#xp-run").onclick = () => solve("run");
  $("#xp-starter").onclick = () => solve("starter");
  $("#xp-kill").onclick = kill;
  $("#xp-supbtn").onclick = addSupport;
  document.querySelectorAll("#tab-xp [data-xpview]").forEach(b => b.onclick = () => view(b.dataset.xpview));
  $("#xp-show").onchange = () => {
    if ($("#xp-show").value === "mesh" && !XP.mesh) { $("#xp-show").value = "model"; status(isModel() ? "Write .inp first" : "Show mesh first", true); }
    if ($("#xp-show").value === "results" && !XP.res.frame) { $("#xp-show").value = XP.mesh ? "mesh" : "model"; status("Choose a job with frames in Results", true); }
    if (XP.three) XP.three.zoomed = false;
    draw();
  };
  for (const id of ["#xp-edges", "#xp-axes", "#xp-scale", "#xp-undef", "#xp-eroded", "#xp-min", "#xp-max"]) $(id).onchange = draw;
  $("#xp-field").onchange = async () => { try { await loadFrame(XP.res.k); draw(); } catch (e) { showErr(e); } };
  $("#xp-frame").oninput = () => { $("#xp-ftime").textContent = `${+$("#xp-frame").value + 1}/${XP.res.geo ? XP.res.geo.frames.length : 0}`; };
  $("#xp-frame").onchange = async () => { try { await loadFrame(+$("#xp-frame").value); draw(); plotEnergy(); } catch (e) { showErr(e); } };
  $("#xp-play").onclick = () => play().then(plotEnergy);
  FM = docFileMenu({ pre: "xp", type: "explicit", label: "explicit analysis", pane: "#tab-xp", listUrl: "/api/explicit/list",
    cur: () => (XP.doc ? { name: XP.doc.name, dirty: !!XP.dirty } : null),
    load: async name => loadDoc(await (await api("/api/explicit/file/" + encodeURIComponent(name))).json()),
    save: saveDoc, blank: () => loadDoc(blankDoc("explicit")), setName: name => { XP.doc.name = name; refreshRuns(); } });
  $("#xp-openrun").onclick = () => { if (XP.runsDir) postJSON("/api/explicit/open_folder", { path: XP.runsDir }).catch(showErr); };
  window.addEventListener("beforeunload", e => { if (XP.dirty) { e.preventDefault(); e.returnValue = ""; } });
  bindSplit();
})();
function bindSplit() {
  const bar = $("#xp-split"), panel = $("#xp-panel");
  if (!bar || bar.dataset.bound) return;
  bar.dataset.bound = "1";
  try { const w = +localStorage.getItem("xp_panel_w"); if (w >= 300) panel.style.width = w + "px"; } catch (e) { /* no storage */ }
  bar.onmousedown = e => {
    e.preventDefault();
    const w0 = panel.getBoundingClientRect().width, x0 = e.clientX;
    bar.classList.add("drag");
    const move = ev => { panel.style.width = Math.max(300, Math.min(window.innerWidth * 0.75, w0 + x0 - ev.clientX)) + "px"; };
    const up = () => {
      bar.classList.remove("drag");
      window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up);
      try { localStorage.setItem("xp_panel_w", parseInt(panel.style.width)); } catch (err) { /* no storage */ }
      resize3();
    };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  };
}

window.__xp = { XP };
window.__xpLoadNamed = async function (name) { await loadDoc(await (await api("/api/explicit/file/" + encodeURIComponent(name))).json()); if (FM) FM.markSaved(name); };
window.__xpSetName = name => { if (XP.doc) { XP.doc.name = name; if (FM) FM.markSaved(name); } };
window.__xpRefresh = () => { if (XP.doc) refreshList(); };
window.__xpCurrent = () => (XP.doc ? { name: XP.doc.name, dirty: !!XP.dirty } : null);
