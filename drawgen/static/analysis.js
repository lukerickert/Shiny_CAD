// Analysis tab: linear static analysis with CalculiX of an assembly or part: bodies (solid or plate), beams, rods,
// fasteners with preload, supports, loads; mesh, solve, deformed shape with contours, result tables and report.
import * as THREE from "three";
import { TumbleControls } from "/static/vendor/TumbleControls.js";
import { updateAxes } from "/static/axes.js";
import { createNavCube } from "/static/navcube.js";

const FA = { doc: null, dirty: false, three: null, geo: null, bbox: null, size: 100,
             sel: null,        // {kind: "member" | "fastener" | "support" | "load" | "rp", id}
             pick: null,       // {text, face: bool, point: bool, cb(hit)} while a face or point is picked in the view
             mesh: null,       // mesh payload (Mesh or Solve)
             res: null,        // solve result {payload, tables, states, summary, files}
             job: null, solver: null, seq: 0 };
const MESHES = new Map();      // assembly view meshes by mkey
const fesc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const ffmt = (v, d = 4) => {
  if (v === null || v === undefined || !isFinite(v)) return "-";
  const a = Math.abs(v);
  if (a !== 0 && (a >= 1e6 || a < 1e-3)) return Number(v).toExponential(Math.max(1, d - 1));
  let s = Number(v).toPrecision(Math.max(d, 1));
  if (s.includes(".") && !s.includes("e")) s = s.replace(/\.?0+$/, "");
  return s === "-0" ? "0" : s;
};
const fnum = v => { const x = window.numv(String(v)); return isFinite(x) ? x : NaN; };
const SECTION_DIMS = { RECT: ["b", "h"], ROUND: ["d"], PIPE: ["d", "t"], BOX: ["b", "h", "t"], I: ["b", "h", "tf", "tw"],
                       GENERAL: ["A", "I11", "I22", "J", "c1", "c2"] };
const DIM_LABEL = { b: "b (mm)", h: "h (mm)", d: "d (mm)", t: "t (mm)", tf: "tf (mm)", tw: "tw (mm)", A: "A (mm^2)",
                    I11: "I11 (mm^4)", I22: "I22 (mm^4)", J: "J (mm^4)", c1: "c1 (mm)", c2: "c2 (mm)" };
const LOAD_TYPES = { force: "Force on a face", pressure: "Pressure on a face", moment: "Moment on a face",
                     mforce: "Force at a member end or reference point", mmoment: "Moment at a member end or reference point", line: "Line load on a member",
                     gravity: "Gravity" };
const COLORS = { support: 0x1c7ed6, load: 0xe03131, fastener: 0xe8590c, connect: 0x2f9e44, beam: 0x364fc7, rod: 0x0c8599,
                 sel: 0xf08c00, sketch: 0x7048e8 };

function blankDoc(name) {
  return { name: name || "analysis", source: { type: "assembly", name: "" },
           materials: { "Steel": { E: 210000, nu: 0.3, rho: 7850 }, "Aluminium": { E: 70000, nu: 0.33, rho: 2700 } },
           default_material: "Steel", mesh: { size: 0 }, bonded: true, bodies: {},
           members: [], plates: [], fasteners: [], supports: [], loads: [], next: 1 };
}
function nid(p) { return p + (FA.doc.next++); }
function changed() { FA.dirty = true; if (FM) FM.render(); }
function findItem(kind, id) { return (FA.doc[{ member: "members", fastener: "fasteners", support: "supports", load: "loads", plate: "plates", rp: "points" }[kind]] || []).find(x => x.id === id); }

// ------------------------------------------------------------------ 3D view

function initThree() {
  const box = $("#fa-view");
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
  FA.three = { renderer, scene, camera, controls, group, box, zoomed: false, pickables: [], geos: [] };
  controls.addEventListener("change", render3);
  camera.userData.target = controls.target;
  FA.three.cube = createNavCube(box, camera, viewDir);
  let down = null;
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; clearHover(); });
  renderer.domElement.addEventListener("pointermove", e => { if (!e.buttons) hoverView(e); });
  renderer.domElement.addEventListener("pointerleave", () => { clearHover(); render3(); });
  renderer.domElement.addEventListener("contextmenu", e => e.preventDefault());
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.abs(e.clientX - down[0]) + Math.abs(e.clientY - down[1]) > 4) { down = null; return; }
    down = null;
    if (e.button === 1) { const h = hitAt(e); if (h) { FA.three.controls.setTarget(h.point.clone(), true); render3(); } return; }
    if (e.button === 0) clickView(e);
  });
  new ResizeObserver(resize3).observe(box);
  resize3();
}
function resize3() {
  const t = FA.three;
  if (!t) return;
  const w = t.box.clientWidth || 1, h = t.box.clientHeight || 1;
  t.renderer.setSize(w, h);
  const c = t.camera, half = (c.top - c.bottom) / 2 || 100;
  c.left = -half * w / h; c.right = half * w / h;
  c.updateProjectionMatrix();
  render3();
}
function render3() { const t = FA.three; if (!t) return; t.renderer.render(t.scene, t.camera); if (t.cube) t.cube.render(); }
function viewDir(dir, up) {
  const t = FA.three;
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
  const t = FA.three;
  if (!t) return;
  const bb = FA.bbox || [-50, -50, -50, 50, 50, 50];
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
  const t = FA.three;
  const r = t.renderer.domElement.getBoundingClientRect();
  const nd = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster();
  rc.params.Line.threshold = FA.size / 150;
  rc.setFromCamera(nd, t.camera);
  return rc;
}
function hitAt(e) { const h = rayAt(e).intersectObjects(FA.three.pickables, false); return h.length ? h[0] : null; }
function toScreen(p) {
  const t = FA.three, r = t.renderer.domElement.getBoundingClientRect();
  const v = new THREE.Vector3(...p).project(t.camera);
  return [(v.x + 1) / 2 * r.width + r.left, (1 - v.y) / 2 * r.height + r.top];
}

/** Sketch curves of a component (world coordinates), and whether the component has sketches but no solid. */
function sketchesOf(cid) { const e = (FA.sketches || []).find(x => x.id === cid); return e ? e.sketches : []; }
function sketchOnly(cid) {
  const g = FA.geo && FA.geo.components.find(c => c.id === cid);
  return sketchesOf(cid).length > 0 && !(g && g.mkey);
}
function sketchPoints() { return (FA.sketches || []).flatMap(e => e.sketches.flatMap(s => s.points)); }
function sketchLines() { return (FA.sketches || []).flatMap(e => e.sketches.flatMap(s => s.lines)); }

/** The member end nearest to the cursor within 10 px: {member, end, xyz}, or null. */
function endAt(e) {
  let best = null, bd = 10;
  for (const m of FA.doc.members) for (const k of ["a", "b"]) if (m[k] && m[k].xyz) {
    const s = toScreen(m[k].xyz), d = Math.hypot(s[0] - e.clientX, s[1] - e.clientY);
    if (d < bd) { bd = d; best = { member: m.id, end: k, xyz: m[k].xyz }; }
  }
  return best;
}
/** A plate corner or sketch point within 10 px: [x, y, z], or null. */
function snapPointAt(e) {
  for (const q of [...(FA.doc.plates || []).flatMap(p => p.points || []), ...sketchPoints()]) {
    const s = toScreen(q);
    if (Math.hypot(s[0] - e.clientX, s[1] - e.clientY) < 10) return q;
  }
  return null;
}
/** The member end selected in the view (click on an end): {member, end}, or null. */
function selEnd() {
  const s = FA.sel;
  if (s && s.kind === "rp") return { point: s.id };
  return s && s.kind === "member" && s.end ? { member: s.id, end: s.end } : null;
}

/** Hover marker: the end or point under the cursor (orange ball), or the face a pick would take (orange overlay). */
function clearHover() {
  const t = FA.three;
  if (!t || !t.hover) return;
  t.scene.remove(t.hover);
  t.hover = null;
  t.renderer.domElement.style.cursor = "";
}
function hoverView(e) {
  const t = FA.three;
  if (!t || !FA.doc) return;
  clearHover();
  if ($("#fa-show").value !== "model") { render3(); return; }
  const pk = FA.pick, r = (FA.size || 100) / 300;
  let pt = null, face = null, item = false;
  const end = !pk || pk.end || pk.point ? endAt(e) : null;
  if (end) pt = end.xyz;
  else if (pk && pk.point) pt = snapPointAt(e);
  if (!pt && pk && !pk.noFace) {
    const h = rayAt(e).intersectObjects(t.pickables, false).find(x => x.object.userData && x.object.userData.comp !== undefined);
    const c = h && compOf(h.object.userData.comp);
    const fi = c && c.mesh ? c.mesh.face_of_tri[h.faceIndex] : null;
    if (fi !== null && fi !== undefined) face = { c, fi };
  }
  if (!pt && !face && !pk) {
    const h = hitAt(e);
    item = !!(h && h.object.userData && (h.object.userData.kind || h.object.userData.comp !== undefined));
  }
  if (pt || face) {
    const g = new THREE.Group();
    if (pt) {
      const b = new THREE.Mesh(new THREE.SphereGeometry(r * 3.2, 16, 12), new THREE.MeshBasicMaterial({ color: COLORS.sel, transparent: true, opacity: 0.55, depthTest: false }));
      b.position.set(...pt);
      b.renderOrder = 10;
      g.add(b);
    } else {
      const m = face.c.mesh, pos = [];
      m.triangles.forEach((tr, k) => { if (m.face_of_tri[k] === face.fi) for (const v of tr) pos.push(...m.vertices[v]); });
      const fg = new THREE.BufferGeometry();
      fg.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      const fm = new THREE.Mesh(fg, new THREE.MeshBasicMaterial({ color: COLORS.sel, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthTest: false }));
      fm.matrixAutoUpdate = false;
      fm.matrix.copy(matOf(face.c));
      fm.renderOrder = 10;
      g.add(fm);
    }
    t.hover = g;
    t.scene.add(g);
  }
  t.renderer.domElement.style.cursor = pk ? (pt || face ? "crosshair" : "") : (end || item) ? "pointer" : "";
  render3();
}

// ------------------------------------------------------------------ geometry (assembly view data)

function compOf(cid) { return FA.geo && FA.geo.components.find(c => c.id === cid); }
function matOf(c) { const m = c.matrix; return new THREE.Matrix4().set(m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], m[9], m[10], m[11], 0, 0, 0, 1); }
/** Face reference of a component in global coordinates: {kind, c, n, r, area}. */
function faceRef(ref) {
  const c = ref && compOf(ref.comp);
  const r = c && c.refs && c.refs[ref.face];
  if (!r) return null;
  const M = matOf(c);
  const out = Object.assign({}, r);
  out.c = new THREE.Vector3(...r.c).applyMatrix4(M).toArray();
  if (r.n) out.n = new THREE.Vector3(...r.n).transformDirection(M).toArray();
  if (r.p) out.p = new THREE.Vector3(...r.p).applyMatrix4(M).toArray();
  return out;
}
function faceText(ref) {
  if (!ref) return "(none)";
  const comp = (FA.asm && FA.asm.components || []).find(x => x.id === ref.comp) ||
    (FA.doc.plates || []).map(p => ({ id: plateComp(p), name: p.name })).find(x => x.id === ref.comp);
  const r = faceRef(ref);
  return (comp ? comp.name : ref.comp) + " : " + (r ? r.kind + (r.r ? " Ø" + ffmt(2 * r.r, 4) : "") + " face " + ref.face : "face " + ref.face);
}

async function sourceAsm() {
  const s = FA.doc.source || {};
  if (!s.name) return { components: [] };
  if (s.type === "part") return { components: [{ id: "1", name: s.name, source: { type: "part", name: s.name }, pos: [0, 0, 0], rot: [0, 0, 0] }] };
  return await (await api("/api/assembly/file/" + encodeURIComponent(s.name))).json();
}

async function loadGeometry() {
  const seq = ++FA.seq;
  $("#fa-info").textContent = "Loading the geometry...";
  try {
    const asm = await sourceAsm();
    if (seq !== FA.seq) return;
    FA.asm = asm;
    FA.sketches = [];
    if (!asm.components.length) { FA.geo = { components: [] }; await loadPlates(true); $("#fa-info").textContent = "No geometry: members and plates only"; draw(); renderAll(); return; }
    try { FA.sketches = (await (await postJSON("/api/assembly/sketches", { assembly: asm })).json()).components; } catch (e) { FA.sketches = []; }
    if (seq !== FA.seq) return;
    const r = await postJSON("/api/assembly/build", { assembly: asm, have: [...MESHES.keys()] });
    const j = await r.json();
    if (seq !== FA.seq) return;
    for (const c of j.components) if (c.mkey && c.mesh) MESHES.set(c.mkey, { mesh: c.mesh, refs: c.refs || [] });
    for (const c of j.components) if (c.mkey && MESHES.has(c.mkey)) { const e = MESHES.get(c.mkey); c.mesh = e.mesh; c.refs = e.refs; }
    FA.geo = j;
    await loadPlates(true);
    const errs = j.components.filter(c => c.error && !c.plate && !(c.mesh === null && sketchOnly(c.id))).map(c => c.error);
    $("#fa-info").textContent = `${j.components.length} component(s)` + (errs.length ? ": " + errs.join("; ") : "");
    if (FA.three) FA.three.zoomed = false;
    draw(); renderAll();
  } catch (e) { if (seq === FA.seq) { $("#fa-info").textContent = ""; showErr(e); } }
}

/** View data of the plate items (server: plate_views), kept in FA.geo.components as "plate_<id>". */
let plateTimer = null, plateSeq = 0;
function schedulePlates() { clearTimeout(plateTimer); plateTimer = setTimeout(() => loadPlates(false), 250); }
async function loadPlates(quiet) {
  if (!FA.geo) return;
  const seq = ++plateSeq;
  let res = [];
  if ((FA.doc.plates || []).length) {
    try { res = (await (await postJSON("/api/analysis/plates", { analysis: FA.doc })).json()).plates; } catch (e) { if (!quiet) showErr(e); return; }
  }
  if (seq !== plateSeq || !FA.geo) return;
  FA.geo.components = FA.geo.components.filter(c => !c.plate);
  FA.plateErr = {};
  for (const p of res) {
    if (p.error) { FA.plateErr[p.id] = p.error; continue; }
    if (!MESHES.has(p.mkey)) MESHES.set(p.mkey, { mesh: p.mesh, refs: p.refs });
    FA.geo.components.push(p);
  }
  if (!quiet) { draw(); renderPlates(); }
}
function plateComp(p) { return "plate_" + p.id; }

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

function clearView() {
  const t = FA.three;
  for (const g of t.geos) g.dispose();
  t.geos = [];
  t.group.clear();
  t.pickables = [];
}
function track(g) { FA.three.geos.push(g); return g; }

function draw() {
  const t = FA.three;
  if (!t) return;
  clearHover();
  clearView();
  const show = $("#fa-show").value;
  $("#fa-legend").hidden = true;
  const box = new THREE.Box3();
  const nsk = (FA.sketches || []).reduce((n, e) => n + e.sketches.length, 0);
  if (show !== "results" && !FA.job) $("#fa-info").textContent = FA.geo ? `${FA.geo.components.length} component(s)` + (nsk ? `, ${nsk} sketch(es)` : "") : "";
  if (show === "model" || !FA.mesh) drawModel(box);
  else drawMesh(box, show === "results" && FA.res ? $("#fa-state").value : null);
  t.group.updateMatrixWorld(true);
  const bb = box.isEmpty() ? null : [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z];
  FA.bbox = bb;
  if (bb) FA.size = Math.max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], 1);
  updateAxes(t.scene, bb, $("#fa-axes").checked);
  if (!t.zoomed && bb) { view("iso"); t.zoomed = true; } else render3();
}

function highlights() {
  const out = [];                                              // [ref, color, strong]
  const d = FA.doc, sel = FA.sel || {};
  for (const s of d.supports) if (s.target && s.target.comp !== undefined) out.push([s.target, COLORS.support, sel.kind === "support" && sel.id === s.id]);
  for (const l of d.loads) if (l.target && l.target.comp !== undefined) out.push([l.target, COLORS.load, sel.kind === "load" && sel.id === l.id]);
  for (const f of d.fasteners) for (const r of f.faces || []) if (r) out.push([r, COLORS.fastener, sel.kind === "fastener" && sel.id === f.id]);
  for (const m of d.members) for (const k of ["a", "b"]) if (m[k] && m[k].face) out.push([m[k].face, COLORS.connect, sel.kind === "member" && sel.id === m.id]);
  for (const p of d.points || []) for (const r of p.faces || []) out.push([r, 0x7048e8, sel.kind === "rp" && sel.id === p.id]);
  return out;
}

function drawModel(box) {
  const t = FA.three;
  const hl = highlights();
  for (const c of (FA.geo && FA.geo.components) || []) {
    const e = c.mkey && meshGeo(c.mkey);
    if (!e) continue;
    const inner = new THREE.Group();
    inner.matrixAutoUpdate = false;
    inner.matrix.copy(matOf(c));
    t.group.add(inner);
    const mode = c.plate ? "plate" : ((FA.doc.bodies || {})[c.id] || {}).mode || "solid";
    const selP = c.plate && FA.sel && FA.sel.kind === "plate" && plateComp({ id: FA.sel.id }) === c.id;
    const col = selP ? COLORS.sel : mode === "plate" ? 0xc9a96e : 0x9aa7b5;
    const mat = new THREE.MeshStandardMaterial({ color: col, metalness: 0.1, roughness: 0.7, side: THREE.DoubleSide, transparent: mode === "off", opacity: mode === "off" ? 0.15 : 1,
                                                 polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    const mesh = new THREE.Mesh(e.geo, mat);
    mesh.userData = c.plate ? { comp: c.id, kind: "plate", id: c.id.slice(6) } : { comp: c.id };
    inner.add(mesh);
    t.pickables.push(mesh);
    if ($("#fa-edges").checked) inner.add(new THREE.LineSegments(e.edgeGeo, new THREE.LineBasicMaterial({ color: 0x1d2125 })));
    const m = c.mesh;
    for (const [ref, color, strong] of hl) {
      if (ref.comp !== c.id) continue;
      const pos = [];
      m.triangles.forEach((tr, k) => { if (m.face_of_tri[k] === ref.face) for (const v of tr) pos.push(...m.vertices[v]); });
      if (!pos.length) continue;
      const g = track(new THREE.BufferGeometry());
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      inner.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: strong ? COLORS.sel : color, transparent: true, opacity: strong ? 0.75 : 0.5, side: THREE.DoubleSide,
                                                               polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
    }
    box.union(e.geo.boundingBox.clone().applyMatrix4(inner.matrix));
  }
  for (const m of FA.doc.members) for (const k of ["a", "b"]) if (m[k] && m[k].xyz) box.expandByPoint(new THREE.Vector3(...m[k].xyz));
  const comps = new Set(((FA.asm && FA.asm.components) || []).filter(c => c.visible !== false).map(c => c.id));
  const skPos = [], skPts = [];
  for (const e of FA.sketches || []) {
    if (!comps.has(e.id)) continue;
    for (const sk of e.sketches) {
      for (const ln of sk.lines) for (let k = 0; k + 1 < ln.length; k++) skPos.push(...ln[k], ...ln[k + 1]);
      for (const q of sk.points) { skPts.push(...q); box.expandByPoint(new THREE.Vector3(...q)); }
    }
  }
  for (let k = 0; k < skPos.length; k += 3) box.expandByPoint(new THREE.Vector3(skPos[k], skPos[k + 1], skPos[k + 2]));
  if (skPos.length) {
    const g = track(new THREE.BufferGeometry());
    g.setAttribute("position", new THREE.Float32BufferAttribute(skPos, 3));
    const ls = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: COLORS.sketch }));
    ls.renderOrder = 5;
    t.group.add(ls);
  }
  if (skPts.length) {
    const g = track(new THREE.BufferGeometry());
    g.setAttribute("position", new THREE.Float32BufferAttribute(skPts, 3));
    t.group.add(new THREE.Points(g, new THREE.PointsMaterial({ color: COLORS.sketch, size: 6, sizeAttenuation: false })));
  }
  const size = box.isEmpty() ? 100 : Math.max(...box.getSize(new THREE.Vector3()).toArray(), 1);
  FA.size = size;
  const rad = size / 300;
  const sel = FA.sel || {};
  for (const m of FA.doc.members) {
    if (!m.a || !m.b || !m.a.xyz || !m.b.xyz) continue;
    const s = sel.kind === "member" && sel.id === m.id;
    addRod(m.a.xyz, m.b.xyz, m.kind === "rod" ? rad * 0.7 : rad, s ? COLORS.sel : COLORS[m.kind] || COLORS.beam, { kind: "member", id: m.id });
    for (const k of ["a", "b"]) {
      const se = s && sel.end === k;                         // the selected end: large orange ball
      addBall(m[k].xyz, se ? rad * 3.2 : rad * 1.8, se || (s && !sel.end) ? COLORS.sel : 0x343a40, { kind: "member", id: m.id, end: k });
    }
  }
  for (const f of FA.doc.fasteners) {
    const ra = faceRef(f.faces && f.faces[0]), rb = faceRef(f.faces && f.faces[1]);
    if (!ra || !rb) continue;
    let A = new THREE.Vector3(...ra.c), B = new THREE.Vector3(...rb.c);
    const ax = [ra, rb].find(r => r.kind === "cylinder");
    if (ax) {
      const p = new THREE.Vector3(...ax.p), n = new THREE.Vector3(...ax.n).normalize();
      A = p.clone().addScaledVector(n, A.clone().sub(p).dot(n));
      B = p.clone().addScaledVector(n, B.clone().sub(p).dot(n));
    }
    const s = sel.kind === "fastener" && sel.id === f.id;
    addRod(A.toArray(), B.toArray(), Math.max((Number(f.d) || 10) / 2, rad), s ? COLORS.sel : COLORS.fastener, { kind: "fastener", id: f.id });
  }
  // reference points: violet balls with lines to the centres of their faces
  for (const rp of FA.doc.points || []) {
    if (!rp.xyz) continue;
    const s = sel.kind === "rp" && sel.id === rp.id;
    addBall(rp.xyz, rad * 2.6, s ? COLORS.sel : 0x7048e8, { kind: "rp", id: rp.id });
    const lp = [];
    for (const r of rp.faces || []) { const f = faceRef(r); if (f && f.c) lp.push(...rp.xyz, ...f.c); }
    if (lp.length) {
      const g = track(new THREE.BufferGeometry());
      g.setAttribute("position", new THREE.Float32BufferAttribute(lp, 3));
      FA.three.group.add(new THREE.LineSegments(g, new THREE.LineDashedMaterial({ color: 0x7048e8 })));
    }
    box.expandByPoint(new THREE.Vector3(...rp.xyz));
  }
  // supports at member ends and reference points: cubes; loads: arrows
  for (const sp of FA.doc.supports) {
    const p = targetPoint(sp.target);
    if (p && (sp.target.member !== undefined || sp.target.point !== undefined)) addBox(p, rad * 5, sel.kind === "support" && sel.id === sp.id ? COLORS.sel : COLORS.support, { kind: "support", id: sp.id });
  }
  for (const l of FA.doc.loads) drawLoad(l, size, sel.kind === "load" && sel.id === l.id);
}

function targetPoint(tg) {
  if (!tg) return null;
  if (tg.point !== undefined) { const p = (FA.doc.points || []).find(x => x.id === tg.point); return p && p.xyz; }
  if (tg.member !== undefined) {
    const m = FA.doc.members.find(x => x.id === tg.member);
    return m && m[tg.end || "a"] && m[tg.end || "a"].xyz;
  }
  if (tg.comp !== undefined) { const r = faceRef(tg); return r && r.c; }
  return null;
}

function drawLoad(l, size, strong) {
  const col = strong ? COLORS.sel : (l.type === "moment" || l.type === "mmoment") ? 0x9c36b5 : COLORS.load;
  const L = size * 0.15;
  const arrow = (p, dir, len) => {
    const d = new THREE.Vector3(...dir);
    if (d.lengthSq() < 1e-20) return;
    d.normalize();
    const start = new THREE.Vector3(...p).addScaledVector(d, -len);
    const a = new THREE.ArrowHelper(d, start, len, col, len * 0.25, len * 0.12);
    a.traverse(o => { o.userData = { kind: "load", id: l.id }; });
    FA.three.group.add(a);
  };
  const v = Array.isArray(l.value) ? l.value.map(Number) : null;
  if (l.type === "gravity") return;
  if (l.type === "line") {
    const m = FA.doc.members.find(x => x.id === (l.target || {}).member);
    if (!m || !m.a || !m.b || !v) return;
    for (let k = 0; k <= 4; k++) {
      const p = m.a.xyz.map((a, i) => a + (m.b.xyz[i] - a) * k / 4);
      arrow(p, v, L * 0.5);
    }
    return;
  }
  const p = targetPoint(l.target);
  if (!p) return;
  if (l.type === "pressure") {
    const r = faceRef(l.target);
    if (!r || !r.n) return;
    const n = r.kind === "plane" ? r.n : [0, 0, 1];
    arrow(p, n.map(x => -x * Math.sign(Number(l.value) || 1)), L);
    return;
  }
  if (v) arrow(p, v, L);
}

function addRod(a, b, r, color, ud) {
  const A = new THREE.Vector3(...a), B = new THREE.Vector3(...b);
  const L = A.distanceTo(B);
  if (L < 1e-9) return;
  const g = track(new THREE.CylinderGeometry(r, r, L, 12));
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color, metalness: 0.2, roughness: 0.5 }));
  m.position.copy(A.clone().add(B).multiplyScalar(0.5));
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), B.clone().sub(A).normalize());
  m.userData = ud;
  FA.three.group.add(m);
  FA.three.pickables.push(m);
}
function addBall(p, r, color, ud) {
  const g = track(new THREE.SphereGeometry(r, 12, 8));
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color }));
  m.position.set(...p);
  m.userData = ud;
  FA.three.group.add(m);
  FA.three.pickables.push(m);
}
function addBox(p, s, color, ud) {
  const g = track(new THREE.BoxGeometry(s, s, s));
  const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color, transparent: true, opacity: 0.8 }));
  m.position.set(...p);
  m.userData = ud;
  FA.three.group.add(m);
  FA.three.pickables.push(m);
}

// ------------------------------------------------------------------ mesh and results drawing

function b64(s, T) {
  const bin = atob(s);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return new T(u8.buffer);
}
function decoded(p) {
  if (!p._d) {
    p._d = { pos: b64(p.pos, Float32Array), tri: b64(p.tri, Uint32Array), edges: p.edges ? b64(p.edges, Uint32Array) : null, states: {} };
  }
  return p._d;
}
function stateData(p, st) {
  const d = decoded(p);
  if (!d.states[st]) d.states[st] = { U: b64(p.states[st].U, Float32Array), vm: b64(p.states[st].vm, Float32Array),
                                       lvm: p.states[st].lvm ? b64(p.states[st].lvm, Float32Array) : null };
  return d.states[st];
}

/** Rainbow colour scale in 12 bands (blue low, red high). */
function bandColor(t) {
  const n = 12;
  const k = Math.min(n - 1, Math.max(0, Math.floor(t * n)));
  const h = (1 - k / (n - 1)) * 240 / 360;
  return new THREE.Color().setHSL(h, 0.9, 0.5);
}

function drawMesh(box, st) {
  const t = FA.three, p = FA.mesh;
  const d = decoded(p);
  const n = p.count;
  const pos = new Float32Array(d.pos);
  let vals = null, lo = 0, hi = 1, scale = 0, lvm = null;
  if (modeResult() && $("#fa-field").value === "vm") $("#fa-field").value = "u";
  const field = $("#fa-field").value;
  if (st && p.states && p.states[st]) {
    const s = stateData(p, st);
    let umax = 0;
    for (let i = 0; i < n; i++) umax = Math.max(umax, Math.hypot(s.U[3 * i], s.U[3 * i + 1], s.U[3 * i + 2]));
    const bb = new THREE.Box3().setFromArray(d.pos);
    const size = Math.max(...bb.getSize(new THREE.Vector3()).toArray(), 1);
    const sv = fnum($("#fa-scale").value);
    scale = isFinite(sv) ? sv : (umax > 0 ? 0.05 * size / umax : 0);
    for (let i = 0; i < 3 * n; i++) pos[i] += scale * s.U[i];
    vals = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const ux = s.U[3 * i], uy = s.U[3 * i + 1], uz = s.U[3 * i + 2];
      vals[i] = field === "vm" ? s.vm[i] : field === "u" ? Math.hypot(ux, uy, uz) : field === "ux" ? ux : field === "uy" ? uy : uz;
    }
    // range of the nodes of the body faces only (member nodes have no stress)
    lo = Infinity; hi = -Infinity;
    for (let k = 0; k < d.tri.length; k++) { const v = vals[d.tri[k]]; if (v < lo) lo = v; if (v > hi) hi = v; }
    lvm = s.lvm;
    let k = 0;
    for (const ln of p.lines) for (const [a, b] of ln.segs) {
      if (field !== "vm") for (const q of [a, b]) { lo = Math.min(lo, vals[q]); hi = Math.max(hi, vals[q]); }
      else if (lvm && ln.kind !== "fastener") for (const v of [lvm[k], lvm[k + 1]]) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      k += 2;
    }
    if (!isFinite(lo)) { lo = 0; hi = 0; }
    legend(field, lo, hi, scale, st);
    $("#fa-info").textContent = modeResult() ? `${stateName(st)}: mode shape (largest displacement 1), scale ${ffmt(scale, 3)}`
      : `${stateName(st)}: max |u| ${ffmt(p.states[st].umax)} mm, max von Mises ${ffmt(p.states[st].vmmax)} MPa, scale ${ffmt(scale, 3)}`;
  }
  const g = track(new THREE.BufferGeometry());
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setIndex(new THREE.BufferAttribute(d.tri, 1));
  g.computeVertexNormals();
  let mat;
  if (vals) {
    const col = new Float32Array(3 * n);
    const span = hi - lo || 1;
    for (let i = 0; i < n; i++) { const c = bandColor((vals[i] - lo) / span); col[3 * i] = c.r; col[3 * i + 1] = c.g; col[3 * i + 2] = c.b; }
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    mat = new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  } else {
    mat = new THREE.MeshStandardMaterial({ color: 0xb8c2cc, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  }
  const mesh = new THREE.Mesh(g, mat);
  mesh.userData = { kind: "mesh" };
  t.group.add(mesh);
  if ($("#fa-edges").checked && (!vals || d.tri.length < 600000)) {
    const eg = track(new THREE.BufferGeometry());
    const idx = elemEdges(d);
    eg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    eg.setIndex(idx);
    t.group.add(new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0x343a40, transparent: true, opacity: vals ? 0.25 : 0.6 })));
  }
  // members and fasteners (deformed): tubes coloured with the field (members: stress of the member table for von
  // Mises), dark without results; element ends as points (the member mesh)
  const lp = [], lc = [], ends = [];
  const span = hi - lo || 1;
  let k = 0;
  for (const ln of p.lines) for (const [a, b] of ln.segs) {
    lp.push(pos[3 * a], pos[3 * a + 1], pos[3 * a + 2], pos[3 * b], pos[3 * b + 1], pos[3 * b + 2]);
    ends.push(pos[3 * a], pos[3 * a + 1], pos[3 * a + 2], pos[3 * b], pos[3 * b + 1], pos[3 * b + 2]);
    if (vals) {
      const va = field === "vm" ? (lvm && ln.kind !== "fastener" ? lvm[k] : null) : vals[a];
      const vb = field === "vm" ? (lvm && ln.kind !== "fastener" ? lvm[k + 1] : null) : vals[b];
      for (const v of [va, vb]) { const c = v === null ? new THREE.Color(0x495057) : bandColor((v - lo) / span); lc.push(c.r, c.g, c.b); }
    }
    k += 2;
  }
  if (lp.length) {
    const bb = new THREE.Box3().setFromArray(lp.concat(Array.from(d.pos)));
    const size = Math.max(...bb.getSize(new THREE.Vector3()).toArray(), 1);
    t.group.add(memberTubes(lp, vals ? lc : null, size * 0.004));
    const pg = track(new THREE.BufferGeometry());
    pg.setAttribute("position", new THREE.Float32BufferAttribute(ends, 3));
    t.group.add(new THREE.Points(pg, new THREE.PointsMaterial({ color: 0x1d2125, size: vals ? 3 : 5, sizeAttenuation: false })));
  }
  if (vals && $("#fa-undef").checked) {
    const ug = track(new THREE.BufferGeometry());
    ug.setAttribute("position", new THREE.BufferAttribute(d.pos, 3));
    const idx = elemEdges(d).slice();
    for (const ln of p.lines) for (const [a, b] of ln.segs) idx.push(a, b);
    ug.setIndex(idx);
    t.group.add(new THREE.LineSegments(ug, new THREE.LineBasicMaterial({ color: 0x868e96, transparent: true, opacity: 0.35 })));
  }
  g.computeBoundingBox();
  box.union(g.boundingBox);
  if (lp.length) box.expandByPoint(new THREE.Vector3(...lp.slice(0, 3)));
  for (let i = 0; i + 2 < lp.length; i += 3) box.expandByPoint(new THREE.Vector3(lp[i], lp[i + 1], lp[i + 2]));
}

/** Element edges of the drawn faces (index pairs): from the payload (quadrangles without diagonals), else the
 *  triangle edges. */
function elemEdges(d) {
  if (d.edges) return Array.from(d.edges);
  const idx = [];
  for (let k = 0; k < d.tri.length; k += 3) { const a = d.tri[k], b = d.tri[k + 1], c = d.tri[k + 2]; idx.push(a, b, b, c, c, a); }
  return idx;
}

/** Tubes (8 sides) along line segments [x1, y1, z1, x2, y2, z2, ...] with colours at the segment ends (or dark). */
function memberTubes(lp, cols, r) {
  const P = [], C = [], I = [];
  const nside = 8;
  const dark = new THREE.Color(0x1d2125);
  for (let s = 0; s < lp.length / 6; s++) {
    const A = new THREE.Vector3(lp[6 * s], lp[6 * s + 1], lp[6 * s + 2]), B = new THREE.Vector3(lp[6 * s + 3], lp[6 * s + 4], lp[6 * s + 5]);
    const dir = B.clone().sub(A);
    if (dir.length() < 1e-12) continue;
    dir.normalize();
    const u = Math.abs(dir.z) < 0.9 ? new THREE.Vector3(0, 0, 1).cross(dir).normalize() : new THREE.Vector3(1, 0, 0).cross(dir).normalize();
    const v = dir.clone().cross(u);
    const base = P.length / 3;
    for (let end = 0; end < 2; end++) {
      const O = end ? B : A;
      const c = cols ? new THREE.Color(cols[6 * s + 3 * end], cols[6 * s + 3 * end + 1], cols[6 * s + 3 * end + 2]) : dark;
      for (let k = 0; k < nside; k++) {
        const a = 2 * Math.PI * k / nside;
        const q = O.clone().addScaledVector(u, r * Math.cos(a)).addScaledVector(v, r * Math.sin(a));
        P.push(q.x, q.y, q.z); C.push(c.r, c.g, c.b);
      }
    }
    for (let k = 0; k < nside; k++) {
      const k2 = (k + 1) % nside;
      I.push(base + k, base + k2, base + nside + k2, base + k, base + nside + k2, base + nside + k);
    }
  }
  const g = track(new THREE.BufferGeometry());
  g.setAttribute("position", new THREE.Float32BufferAttribute(P, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(C, 3));
  g.setIndex(I);
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }));
  m.userData = { kind: "members" };
  return m;
}

const STATE_NAME = { total: "Total", preload: "Step 1 preload", loads: "Step 2 loads" };
/** Name of a result state: static states, or "Mode k: f Hz" / "Mode k: factor" of a modal or buckling result. */
function stateName(st) {
  if (STATE_NAME[st]) return STATE_NAME[st];
  const m = /^m(\d+)$/.exec(st || "");
  const md = m && FA.res && FA.res.modes ? FA.res.modes[+m[1] - 1] : null;
  if (!md) return st;
  return FA.res.atype === "modal" ? `Mode ${md.mode}: ${ffmt(md.value, 5)} Hz` : `Mode ${md.mode}: factor ${ffmt(md.value, 5)}`;
}
function modeResult() { return !!(FA.res && FA.res.atype && FA.res.atype !== "static"); }
const FIELD_NAME = { vm: "von Mises (MPa)", u: "|u| (mm)", ux: "ux (mm)", uy: "uy (mm)", uz: "uz (mm)" };
function legend(field, lo, hi, scale, st) {
  const el = $("#fa-legend");
  const stops = [];
  for (let k = 0; k < 12; k++) { const c = bandColor((k + 0.5) / 12); stops.push(`#${c.getHexString()} ${k / 12 * 100}%`, `#${c.getHexString()} ${(k + 1) / 12 * 100}%`); }
  const ticks = [];
  for (let k = 12; k >= 0; k -= 2) ticks.push(`<span>${ffmt(lo + (hi - lo) * k / 12, 4)}</span>`);
  const ttl = modeResult() ? FIELD_NAME[field].replace(" (mm)", " (normalised)") : FIELD_NAME[field];
  el.innerHTML = `<div class="ttl">${ttl}</div><div class="hint" style="margin:0 0 4px">${stateName(st)}, deformation x ${ffmt(scale, 3)}</div>` +
    `<span class="bar" style="background:linear-gradient(to top, ${stops.join(", ")})"></span><span class="ticks">${ticks.join("")}</span>`;
  el.hidden = false;
}

// ------------------------------------------------------------------ picking

function startPick(text, opts, cb) {
  if ($("#fa-show").value !== "model") { $("#fa-show").value = "model"; draw(); }
  FA.pick = Object.assign({ text, cb }, opts);
  status(text + " (Esc cancels)");
  renderAll();
}
function endPick() { const p = FA.pick; FA.pick = null; if (p && p.onCancel) p.onCancel(); renderAll(); draw(); }

function clickView(e) {
  const t = FA.three;
  const hits = rayAt(e).intersectObjects(t.pickables, false);
  if (FA.pick) {
    const done = hit => { const cb = FA.pick.cb; FA.pick = null; cb(hit); changed(); renderAll(); draw(); schedulePlates(); };
    // supports and loads: a member end within 10 px, or a member
    if (FA.pick.end) {
      for (const rp of FA.doc.points || []) if (rp.xyz) { const s = toScreen(rp.xyz); if (Math.hypot(s[0] - e.clientX, s[1] - e.clientY) < 10) return done({ point: rp.id, xyz: rp.xyz.slice() }); }
      const h = endAt(e); if (h) return done({ member: h.member, end: h.end, xyz: h.xyz.slice() });
    }
    if (FA.pick.member) {
      const h = hits.find(x => x.object.userData && x.object.userData.kind === "member" && x.object.userData.end === undefined);
      if (h) return done({ member: h.object.userData.id });
    }
    // points: member ends within 10 px first
    if (FA.pick.point) {
      for (const m of FA.doc.members) for (const k of ["a", "b"]) if (m[k] && m[k].xyz) {
        const s = toScreen(m[k].xyz);
        if (Math.hypot(s[0] - e.clientX, s[1] - e.clientY) < 10) { const cb = FA.pick.cb; FA.pick = null; cb({ xyz: m[k].xyz.slice(), member: m.id, end: k }); changed(); renderAll(); draw(); schedulePlates(); return; }
      }
      for (const q of [...(FA.doc.plates || []).flatMap(p => p.points || []), ...sketchPoints()]) {
        const s = toScreen(q);
        if (Math.hypot(s[0] - e.clientX, s[1] - e.clientY) < 10) { const cb = FA.pick.cb; FA.pick = null; cb({ xyz: q.slice() }); changed(); renderAll(); draw(); schedulePlates(); return; }
      }
    }
    if (FA.pick.noFace) return;
    const h = hits.find(x => x.object.userData && x.object.userData.comp !== undefined);
    if (!h) return;
    const cid = h.object.userData.comp, c = compOf(cid);
    const fi = c && c.mesh ? c.mesh.face_of_tri[h.faceIndex] : null;
    if (fi === null || fi === undefined) return;
    const ref = { comp: cid, face: fi };
    if (FA.pick.cylinder && (faceRef(ref) || {}).kind !== "cylinder" && (faceRef(ref) || {}).kind !== "plane") { status("Pick a cylindrical or planar face", true); return; }
    const cb = FA.pick.cb;
    FA.pick = null;
    const p = h.point.toArray().map(v => Math.round(v * 1000) / 1000);
    cb({ face: ref, xyz: p, centre: (faceRef(ref) || {}).c });
    changed(); renderAll(); draw(); schedulePlates();
    return;
  }
  // selection: a member end within 10 px, else the item under the cursor, else nothing
  const end = $("#fa-show").value === "model" ? endAt(e) : null;
  const h = hits[0], ud = (h && h.object.userData) || {};
  const prev = JSON.stringify(FA.sel || null);
  FA.sel = end ? { kind: "member", id: end.member, end: end.end } : ud.kind && ud.id ? { kind: ud.kind, id: ud.id } : null;
  if (JSON.stringify(FA.sel) === prev) return;
  if (FA.sel && FA.sel.end) status(targetText({ member: FA.sel.id, end: FA.sel.end }) + " selected: Support or Load applies to it");
  renderAll(); draw();
}

// ------------------------------------------------------------------ panels

function renderAll() {
  if (!FA.doc) return;
  renderSettings(); renderMats(); renderBodies(); renderMembers(); renderPlates(); renderFasts(); renderRps(); renderSups(); renderLoads(); renderResults();
}

function matOptions(cur) {
  const names = Object.keys(FA.doc.materials || {});
  return `<option value="">(default: ${fesc(FA.doc.default_material)})</option>` + names.map(n => `<option value="${fesc(n)}"${n === cur ? " selected" : ""}>${fesc(n)}</option>`).join("");
}

const MESH_STRATEGIES = [["tet", "Tetrahedra (free)"], ["hex", "Hexahedra, structured (block cells)"], ["hexsub", "Hexahedra by subdivision"]];
const TET_TYPES = [["C3D10", "C3D10 (second order)"], ["C3D4", "C3D4 (first order)"]];
const HEX_TYPES = [["C3D8I", "C3D8I (incompatible modes)"], ["C3D8", "C3D8 (full integration)"], ["C3D8R", "C3D8R (reduced integration)"],
                   ["C3D20", "C3D20 (second order)"], ["C3D20R", "C3D20R (second order, reduced)"]];
const ALGOS = [["delaunay", "Delaunay"], ["frontal", "Frontal"], ["hxt", "HXT (parallel Delaunay)"]];
const optList = (list, cur) => list.map(([v, t]) => `<option value="${v}"${v === cur ? " selected" : ""}>${fesc(t)}</option>`).join("");

/** Mesh settings of the analysis (doc.mesh): strategy, element types, size, minimum size, curvature, 3D algorithm. */
function meshSettingsHtml(m) {
  return `<p class="hint" style="margin:8px 0 2px"><strong>Mesh</strong></p>` +
    `<label title="Default mesh of the solid bodies; a body can override it in Bodies">Strategy<select id="fs-strategy">${optList(MESH_STRATEGIES, m.strategy || "tet")}</select></label>` +
    `<div class="grid2"><label>Tetrahedra<select id="fs-tettype">${optList(TET_TYPES, m.tet_type || "C3D10")}</select></label>` +
    `<label>Hexahedra (wedges C3D6 / C3D15)<select id="fs-hextype">${optList(HEX_TYPES, m.hex_type || "C3D8I")}</select></label></div>` +
    `<div class="grid2"><label title="Element size of the bodies (mm). Empty: model size / 20">Element size (mm)<input type="text" class="numf" id="fs-size" value="${m.size || ""}" placeholder="auto"></label>` +
    `<label title="Smallest element size (mm). Empty: element size / 5">Minimum size (mm)<input type="text" class="numf" id="fs-smin" value="${m.size_min || ""}" placeholder="auto"></label></div>` +
    `<div class="grid2"><label title="Elements per 360 deg of curvature of the faces (0: off)">Elements per 360 deg of curvature<input type="text" class="numf" id="fs-curv" value="${m.curvature === undefined || m.curvature === null ? "" : m.curvature}" placeholder="12"></label>` +
    `<label>3D algorithm<select id="fs-algo">${optList(ALGOS, m.algorithm || "delaunay")}</select></label></div>` +
    `<label class="check"><input type="checkbox" id="fs-opt"${m.optimize === false ? "" : " checked"}> Optimise the mesh</label>` +
    `<p class="hint">Structured hexahedra need bodies whose cells are blocks (6 faces with 4 edges each) or prisms (Part tab, Partition). Bodies of different strategies, and plates, are tied where they touch.</p>`;
}
function bindMeshSettings(d) {
  const m = () => (d.mesh = d.mesh || {});
  const num = (id, k, allowZero) => { $(id).onchange = () => { const raw = $(id).value.trim(), v = fnum(raw); if (raw !== "" && (v > 0 || (allowZero && v === 0))) m()[k] = v; else delete m()[k]; changed(); }; };
  num("#fs-size", "size"); num("#fs-smin", "size_min"); num("#fs-curv", "curvature", true);
  $("#fs-strategy").onchange = () => { m().strategy = $("#fs-strategy").value; changed(); renderBodies(); };
  $("#fs-tettype").onchange = () => { m().tet_type = $("#fs-tettype").value; changed(); };
  $("#fs-hextype").onchange = () => { m().hex_type = $("#fs-hextype").value; changed(); };
  $("#fs-algo").onchange = () => { m().algorithm = $("#fs-algo").value; changed(); };
  $("#fs-opt").onchange = () => { m().optimize = $("#fs-opt").checked; changed(); };
}

/** Width of the analysis panel: drag of the bar at its left edge, kept in the browser (localStorage). */
function bindPanelSplit() {
  const bar = $("#fa-split"), panel = $("#fa-panel");
  if (!bar || bar.dataset.bound) return;
  bar.dataset.bound = "1";
  try { const w = +localStorage.getItem("fa_panel_w"); if (w >= 300) panel.style.width = w + "px"; } catch (e) { /* no storage */ }
  bar.onmousedown = e => {
    e.preventDefault();
    const w0 = panel.getBoundingClientRect().width, x0 = e.clientX;
    bar.classList.add("drag");
    const move = ev => { panel.style.width = Math.max(300, Math.min(window.innerWidth * 0.75, w0 + x0 - ev.clientX)) + "px"; };
    const up = () => {
      bar.classList.remove("drag");
      window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up);
      try { localStorage.setItem("fa_panel_w", parseInt(panel.style.width)); } catch (err) { /* no storage */ }
    };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  };
}

function renderSettings() {
  bindPanelSplit();
  const d = FA.doc, s = FA.solver || {};
  $("#fa-settings").innerHTML =
    `<label title="CalculiX executable (ccx). Empty: ccx in the solvers folder of the program, ccx on PATH, or the Solver folder of a PrePoMax folder">Solver (ccx)<input type="text" id="fs-ccx" value="${fesc(s.configured || "")}" placeholder="${fesc(s.path || "not found")}"></label>` +
    `<p class="hint">${s.path ? "Using " + fesc(s.path) : "CalculiX not found: unpack PrePoMax (prepomax.fs.um.si/downloads) to the solvers folder of the program, or give the path of the ccx executable in its Solver folder"}</p>` +
    `<div class="grid2"><label title="Linear static: loads, displacements, stresses, reactions. Modal: natural frequencies and mode shapes (densities required; loads not used). Linear buckling: buckling factors of the loads. Modal and buckling: solid bodies, plates and rods only">Analysis type<select id="fs-atype">` +
    [["static", "Linear static"], ["modal", "Modal (natural frequencies)"], ["buckling", "Linear buckling"]].map(([v, n]) => `<option value="${v}"${(d.analysis_type || "static") === v ? " selected" : ""}>${n}</option>`).join("") + `</select></label>` +
    `<label title="Number of natural frequencies or buckling factors (1 to 100)">Number of modes<input type="text" inputmode="numeric" id="fs-modes" value="${d.modes || 6}"${(d.analysis_type || "static") === "static" ? " disabled" : ""}></label></div>` +
    `<label>Default material<select id="fs-defmat">${Object.keys(d.materials).map(n => `<option${n === d.default_material ? " selected" : ""}>${fesc(n)}</option>`).join("")}</select></label>` +
    `<p class="hint">Units: mm, N, s, t (tonne): stress and pressure MPa (N/mm^2), moment N mm, acceleration mm/s^2; densities are entered in kg/m^3.</p>` +
    meshSettingsHtml(d.mesh || {}) +
    `<label class="check" title="Touching solid bodies share their nodes; plates are tied to the faces they touch"><input type="checkbox" id="fs-bonded"${d.bonded !== false ? " checked" : ""}> Bonded contact between touching bodies</label>`;
  $("#fs-ccx").onchange = async () => {
    try { FA.solver = await (await api("/api/analysis/solver", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: $("#fs-ccx").value }) })).json(); } catch (e) { showErr(e); }
    renderSettings();
  };
  bindMeshSettings(d);
  $("#fs-defmat").onchange = () => { d.default_material = $("#fs-defmat").value; changed(); renderAll(); };
  $("#fs-bonded").onchange = () => { d.bonded = $("#fs-bonded").checked; changed(); };
  $("#fs-atype").onchange = () => { d.analysis_type = $("#fs-atype").value; changed(); renderSettings(); };
  $("#fs-modes").onchange = () => { const v = Math.round(fnum($("#fs-modes").value)); if (isFinite(v) && v >= 1 && v <= 100) { d.modes = v; changed(); } else { status("Number of modes: 1 to 100"); renderSettings(); } };
}

function renderMats() {
  const d = FA.doc;
  const rows = Object.entries(d.materials).map(([n, m]) => `<tr data-n="${fesc(n)}"><td><input type="text" data-k="name" value="${fesc(n)}"></td>` +
    `<td><input type="text" class="numf" data-k="E" value="${m.E}"></td><td><input type="text" class="numf" data-k="nu" value="${m.nu}"></td>` +
    `<td><input type="text" class="numf" data-k="rho" value="${m.rho || ""}"></td><td><button type="button" class="small" data-k="del" title="Delete">&#10005;</button></td></tr>`).join("");
  $("#fa-mats").innerHTML = `<table class="pc-table"><tr><th>Name</th><th>E (MPa)</th><th>nu</th><th>rho (kg/m^3)</th><th></th></tr>${rows}</table>` +
    `<button type="button" class="small" id="fm-add">Add material</button>`;
  $("#fa-mats").querySelectorAll("tr[data-n]").forEach(tr => {
    const n = tr.dataset.n;
    tr.querySelectorAll("input").forEach(inp => inp.onchange = () => {
      const k = inp.dataset.k, m = d.materials[n];
      if (k === "name") {
        const nn = inp.value.trim();
        if (!nn || d.materials[nn]) { inp.value = n; return; }
        const o = {};
        for (const [a, b] of Object.entries(d.materials)) o[a === n ? nn : a] = b;
        d.materials = o;
        if (d.default_material === n) d.default_material = nn;
        for (const arr of [d.members, d.fasteners]) for (const x of arr) if (x.material === n) x.material = nn;
        for (const b of Object.values(d.bodies)) if (b.material === n) b.material = nn;
      } else m[k] = fnum(inp.value) || 0;
      changed(); renderAll();
    });
    tr.querySelector("[data-k=del]").onclick = () => {
      if (Object.keys(d.materials).length < 2) return;
      delete d.materials[n];
      if (d.default_material === n) d.default_material = Object.keys(d.materials)[0];
      changed(); renderAll();
    };
  });
  $("#fm-add").onclick = () => { let k = 1; while (d.materials["Material " + k]) k++; d.materials["Material " + k] = { E: 210000, nu: 0.3, rho: 7850 }; changed(); renderAll(); };
}

function renderBodies() {
  const d = FA.doc;
  const all = (FA.asm && FA.asm.components) || [];
  if (!all.length) { $("#fa-bodies").innerHTML = '<p class="hint">No bodies: Geometry is (none).</p>'; return; }
  const comps = all.filter(c => !sketchOnly(c.id));
  if (!comps.length) { $("#fa-bodies").innerHTML = `<p class="hint">No bodies: ${all.map(c => fesc(c.name)).join(", ")} has sketches only (members and plates snap to the sketch points).</p>`; return; }
  const defStrat = ((d.mesh || {}).strategy) || "tet";
  const stratShort = { tet: "tet", hex: "hex", hexsub: "hex sub" };
  $("#fa-bodies").innerHTML = `<table class="pc-table"><tr><th>Body</th><th>Model</th><th>Mesh</th><th>Material</th><th>Size (mm)</th></tr>` + comps.map(c => {
    const b = d.bodies[c.id] || {};
    const strat = `<select data-k="strategy"${b.mode === "plate" || b.mode === "off" ? " disabled" : ""}><option value="">(${stratShort[defStrat]})</option>` +
      ["tet", "hex", "hexsub"].map(k => `<option value="${k}"${b.strategy === k ? " selected" : ""}>${stratShort[k]}</option>`).join("") + `</select>`;
    return `<tr data-id="${fesc(c.id)}"><td>${fesc(c.name)}</td><td><select data-k="mode">${["solid", "plate", "off"].map(m => `<option${(b.mode || "solid") === m ? " selected" : ""}>${m}</option>`).join("")}</select></td>` +
      `<td>${strat}</td><td><select data-k="material">${matOptions(b.material)}</select></td><td><input type="text" class="numf" data-k="size" value="${b.size || ""}" placeholder="auto"></td></tr>`;
  }).join("") + `</table><p class="hint">solid: meshed with the strategy in Mesh (tet: tetrahedra; hex: structured hexahedra; hex sub: hexahedra by subdivision; in brackets: the default of Settings); plate: prismatic part meshed through the thickness (C3D8I); off: left out.</p>`;
  $("#fa-bodies").querySelectorAll("tr[data-id]").forEach(tr => {
    const id = tr.dataset.id;
    tr.querySelectorAll("[data-k]").forEach(el => el.onchange = () => {
      const b = d.bodies[id] = d.bodies[id] || {};
      const k = el.dataset.k;
      if (k === "size") { const v = fnum(el.value); if (v > 0) b.size = v; else delete b.size; }
      else if (el.value) b[k] = el.value; else delete b[k];
      changed(); draw();
      if (k === "mode") renderBodies();
    });
  });
}

function itemRow(kind, x, title, sub) {
  const s = FA.sel && FA.sel.kind === kind && FA.sel.id === x.id;
  return `<div class="fa-item${s ? " sel" : ""}" data-kind="${kind}" data-id="${fesc(x.id)}"><span>${fesc(title)}</span>` +
    `<span class="ops"><button type="button" data-k="del" title="Delete">&#10005;</button></span>${sub ? `<span class="sub">${fesc(sub)}</span>` : ""}</div>`;
}
function bindRows(box, kind, arrName) {
  box.querySelectorAll(".fa-item").forEach(row => {
    row.onclick = e => {
      const id = row.dataset.id;
      if (e.target.dataset && e.target.dataset.k === "del") {
        FA.doc[arrName] = FA.doc[arrName].filter(x => x.id !== id);
        if (kind === "rp") {
          FA.doc.supports = FA.doc.supports.filter(s => !(s.target && s.target.point === id));
          FA.doc.loads = FA.doc.loads.filter(l => !(l.target && l.target.point === id));
        }
        if (kind === "member") {
          FA.doc.supports = FA.doc.supports.filter(s => !(s.target && s.target.member === id));
          FA.doc.loads = FA.doc.loads.filter(l => !(l.target && l.target.member === id));
        }
        if (kind === "plate") {
          const pc = plateComp({ id });
          FA.doc.supports = FA.doc.supports.filter(s => !(s.target && s.target.comp === pc));
          FA.doc.loads = FA.doc.loads.filter(l => !(l.target && l.target.comp === pc));
          for (const m of FA.doc.members) for (const k of ["a", "b"]) if (m[k] && m[k].face && m[k].face.comp === pc) delete m[k].face;
          schedulePlates();
        }
        if (FA.sel && FA.sel.id === id) FA.sel = null;
        changed(); renderAll(); draw(); return;
      }
      FA.sel = (FA.sel && FA.sel.id === id && FA.sel.kind === kind) ? null : { kind, id };
      renderAll(); draw();
    };
  });
}
const pickHint = () => FA.pick ? `<p class="fa-pick">${fesc(FA.pick.text)}</p>` : "";
const v3 = (id, v) => `<div class="grid3">${["x", "y", "z"].map((a, i) => `<label>${a}<input type="text" class="numf" id="${id}${i}" value="${v ? ffmt(v[i], 8) : ""}"></label>`).join("")}</div>`;
const read3 = id => [0, 1, 2].map(i => fnum($("#" + id + i).value) || 0);

/** Group of a member (doc.groups): a named set of kind, section and material shared by its members. */
function groupOf(m) { return m && m.group ? (FA.doc.groups || []).find(g => g.id === m.group) || null : null; }
/** Effective kind, section and material of a member (from its group when it has one). */
function memberEff(m) {
  const g = groupOf(m);
  return g ? { kind: g.kind || m.kind, section: g.section || m.section, material: g.material || m.material, group: g } : { kind: m.kind, section: m.section, material: m.material, group: null };
}
const SECTION_DEFAULTS = { RECT: { b: 20, h: 40 }, ROUND: { d: 20 }, PIPE: { d: 48.3, t: 3.2 }, BOX: { b: 50, h: 100, t: 4 }, I: { b: 100, h: 200, tf: 8.5, tw: 5.6 }, GENERAL: { A: 1000, I11: 1e5, I22: 1e6, J: 1e4, c1: 50, c2: 100 } };

/** Groups table: name, kind, section, material and the number of members; the selected group is edited below. */
function groupsHtml() {
  const d = FA.doc, gs = d.groups || [];
  let h = `<p class="hint" style="margin:6px 0 2px"><strong>Groups</strong> (kind, section and material shared by the members of the group)</p>`;
  if (gs.length) {
    h += `<table class="pc-table fa-gtable"><tr><th>Group</th><th>Kind</th><th>Section</th><th>Material</th><th>Members</th><th></th></tr>` + gs.map(g => {
      const sel = FA.selGroup === g.id;
      return `<tr class="fa-grow${sel ? " sel" : ""}" data-gid="${fesc(g.id)}"><td>${fesc(g.name)}</td><td>${g.kind || "beam"}</td><td>${fesc(sectionText(g.section))}</td>` +
        `<td>${fesc(g.material || "(default)")}</td><td>${d.members.filter(m => m.group === g.id).length}</td><td><button type="button" class="small" data-gdel="${fesc(g.id)}" title="Delete the group (its members keep the properties)">&#10005;</button></td></tr>`;
    }).join("") + `</table>`;
  }
  h += `<div class="buttons"><button type="button" class="small" id="fgr-add" title="New group; with a member selected: from its properties, and the member joins it">Add group</button></div>`;
  const g = gs.find(x => x.id === FA.selGroup);
  if (g) {
    const sec = g.section || { shape: "ROUND", d: 20 };
    h += `<div class="fa-props"><div class="grid3"><label>Name<input type="text" id="fgr-name" value="${fesc(g.name)}"></label>` +
      `<label>Kind<select id="fgr-kind"><option value="beam"${(g.kind || "beam") === "beam" ? " selected" : ""}>beam</option><option value="rod"${g.kind === "rod" ? " selected" : ""}>rod (axial)</option></select></label>` +
      `<label>Material<select id="fgr-mat">${matOptions(g.material)}</select></label></div>` +
      `<div class="grid3"><label>Section<select id="fgr-shape">${Object.keys(SECTION_DIMS).map(k => `<option${k === sec.shape ? " selected" : ""}>${k}</option>`).join("")}</select></label>` +
      SECTION_DIMS[sec.shape].map(k => `<label>${DIM_LABEL[k]}<input type="text" class="numf" data-gdim="${k}" value="${sec[k] !== undefined ? sec[k] : ""}"></label>`).join("") + `</div></div>`;
  }
  return h;
}
/** Copies kind, section and material of every group to its members (the members carry the values the solver and
 *  the view use). */
function syncGroups() {
  const d = FA.doc;
  for (const m of d.members) {
    const g = groupOf(m);
    if (!g) continue;
    m.kind = g.kind || "beam";
    m.section = JSON.parse(JSON.stringify(g.section || m.section));
    if (g.material) m.material = g.material; else delete m.material;
  }
}
function bindGroups(box) {
  const d = FA.doc;
  const upd = () => { syncGroups(); changed(); renderMembers(); draw(); };
  box.querySelectorAll("tr.fa-grow").forEach(tr => tr.onclick = e => {
    if (e.target.dataset.gdel) { const id = e.target.dataset.gdel; d.groups = (d.groups || []).filter(g => g.id !== id);
      for (const m of d.members) if (m.group === id) delete m.group;
      if (FA.selGroup === id) FA.selGroup = null; upd(); return; }
    FA.selGroup = FA.selGroup === tr.dataset.gid ? null : tr.dataset.gid; renderMembers();
  });
  $("#fgr-add").onclick = () => {
    const m = FA.sel && FA.sel.kind === "member" && findItem("member", FA.sel.id);
    const e = m ? memberEff(m) : { kind: "beam", section: { shape: "PIPE", d: 48.3, t: 3.2 }, material: undefined };
    d.groups = d.groups || [];
    let k = d.groups.length + 1;
    while (d.groups.some(g => g.name === "Group " + k)) k++;
    const g = { id: nid("g"), name: "Group " + k, kind: e.kind || "beam", section: JSON.parse(JSON.stringify(e.section || { shape: "ROUND", d: 20 })) };
    if (e.material) g.material = e.material;
    d.groups.push(g);
    if (m) m.group = g.id;
    FA.selGroup = g.id; upd();
  };
  const g = (d.groups || []).find(x => x.id === FA.selGroup);
  if (!g) return;
  $("#fgr-name").onchange = () => { g.name = $("#fgr-name").value.trim() || g.name; upd(); };
  $("#fgr-kind").onchange = () => { g.kind = $("#fgr-kind").value; upd(); };
  $("#fgr-mat").onchange = () => { if ($("#fgr-mat").value) g.material = $("#fgr-mat").value; else delete g.material; upd(); };
  $("#fgr-shape").onchange = () => { const k = $("#fgr-shape").value; g.section = Object.assign({ shape: k }, SECTION_DEFAULTS[k]); upd(); };
  box.querySelectorAll("[data-gdim]").forEach(inp => inp.onchange = () => { g.section = Object.assign({}, g.section, { [inp.dataset.gdim]: fnum(inp.value) || 0 }); upd(); });
}

// ------------------------------------------------------------------ member property grid (spreadsheet)

/** Columns of the member grid: text get / set (set returns an error text or null); ro: read-only for the member. */
const MEMBER_COLS = [
  { key: "name", title: "Member", get: m => m.name, set: (m, v) => { if (!v) return "a name is needed"; m.name = v; return null; } },
  { key: "group", title: "Group", get: m => (groupOf(m) || {}).name || "", set: (m, v) => setMemberGroup(m, v) },
  { key: "kind", title: "Kind", ro: m => !!groupOf(m), get: m => m.kind || "beam",
    set: (m, v) => { v = v.toLowerCase(); if (v !== "beam" && v !== "rod") return "kind: beam or rod"; m.kind = v; return null; } },
  { key: "shape", title: "Section", ro: m => !!groupOf(m), get: m => (m.section || {}).shape || "",
    set: (m, v) => { v = v.toUpperCase(); if (!SECTION_DIMS[v]) return "section: " + Object.keys(SECTION_DIMS).join(", ");
      if ((m.section || {}).shape !== v) m.section = Object.assign({ shape: v }, SECTION_DEFAULTS[v]); return null; } },
  { key: "dims", title: "Dimensions (mm)", ro: m => !!groupOf(m),
    get: m => { const sc = m.section || {}; return (SECTION_DIMS[sc.shape] || []).map(k => sc[k] === undefined ? "" : ffmt(sc[k], 6)).join(" x "); },
    set: (m, v) => { const sc = m.section || {}; const keys = SECTION_DIMS[sc.shape] || []; const nums = v.split(/[x*,;\s]+/).filter(Boolean).map(Number);
      if (nums.length !== keys.length || nums.some(n => !(n > 0))) return `dimensions: ${keys.join(" x ")} (${keys.length} positive values)`;
      m.section = Object.assign({ shape: sc.shape }, Object.fromEntries(keys.map((k, i) => [k, nums[i]]))); return null; } },
  { key: "material", title: "Material", ro: m => !!groupOf(m), get: m => m.material || "",
    set: (m, v) => { if (!v) { delete m.material; return null; } const n = Object.keys(FA.doc.materials).find(k => k.toLowerCase() === v.toLowerCase());
      if (!n) return "material not defined: " + v; m.material = n; return null; } },
  { key: "n", title: "Elem.", get: m => m.n ? String(m.n) : "",
    set: (m, v) => { if (!v) { delete m.n; return null; } const n = Math.round(Number(v)); if (!(n > 0)) return "elements: a positive whole number or empty"; m.n = n; return null; } },
  { key: "release", title: "Hinge", get: m => m.release || "",
    set: (m, v) => { v = v.toLowerCase().replace(/[^ab]/g, ""); if (!["", "a", "b", "ab", "ba"].includes(v)) return "hinge: a, b, ab or empty"; m.release = v === "ba" ? "ab" : v; return null; } },
  { key: "L", title: "L (mm)", ro: () => true, get: m => ffmt(mlen(m), 5) },
];
/** Group of a member by name: empty removes the group; a new name makes a group from the member's properties. */
function setMemberGroup(m, v) {
  const d = FA.doc;
  d.groups = d.groups || [];
  if (!v) { delete m.group; return null; }
  let g = d.groups.find(x => x.name === v);
  if (!g) {
    g = { id: nid("g"), name: v, kind: m.kind || "beam", section: JSON.parse(JSON.stringify(m.section || { shape: "ROUND", d: 20 })) };
    if (m.material) g.material = m.material;
    d.groups.push(g);
  }
  m.group = g.id;
  return null;
}

/** Property grid (members, plates): cells selected by click or drag (Shift+click extends), arrows move, typing or
 *  double click edits (Enter commits and moves down, Tab right, Esc cancels), Ctrl+C / Ctrl+V copy and paste
 *  tab-separated text (to and from a spreadsheet), the square at the corner of the selection drags the selected
 *  values down or up, Delete clears the cells that may be empty.
 *  cfg: {id, rows: () => items, cols, state: FA key of the selection, kind: FA.sel kind, clear: column keys that
 *  Delete empties, empty: html without rows, hint, after: () => called after a change (sync and redraw),
 *  render: () => re-render of the panel, del: id => delete the item}. */
function gridTable(cfg) {
  const rows = cfg.rows();
  if (!rows.length) return cfg.empty;
  const G = FA[cfg.state] = FA[cfg.state] || { r0: 0, c0: 1, r1: 0, c1: 1 };
  G.r0 = Math.min(G.r0, rows.length - 1); G.r1 = Math.min(G.r1, rows.length - 1);
  const [ra, rb] = [Math.min(G.r0, G.r1), Math.max(G.r0, G.r1)], [ca, cb] = [Math.min(G.c0, G.c1), Math.max(G.c0, G.c1)];
  const selRow = FA.sel && FA.sel.kind === cfg.kind ? rows.findIndex(m => m.id === FA.sel.id) : -1;
  return `<div class="fa-wide fa-grid-wrap" tabindex="0" id="${cfg.id}"><table class="pc-table fa-grid"><tr><th></th>${cfg.cols.map(c => `<th>${c.title}</th>`).join("")}<th></th></tr>` +
    rows.map((m, r) => `<tr${r === selRow ? ' class="selrow"' : ""}><td class="rh">${r + 1}</td>` + cfg.cols.map((c, ci) => {
      const inSel = r >= ra && r <= rb && ci >= ca && ci <= cb;
      const ro = !c.set || (c.ro && c.ro(m));
      const corner = r === rb && ci === cb ? '<span class="fill" title="Drag to copy the selected values down or up"></span>' : "";
      return `<td data-r="${r}" data-c="${ci}" class="${inSel ? "in" : ""}${r === G.r0 && ci === G.c0 ? " act" : ""}${ro ? " ro" : ""}">${fesc(c.get(m))}${corner}</td>`;
    }).join("") + `<td><button type="button" class="small" data-gdelrow="${fesc(m.id)}" title="Delete">&#10005;</button></td></tr>`).join("") +
    `</table></div><p class="hint">${cfg.hint}</p>`;
}

function bindGrid(box, cfg) {
  const wrap = box.querySelector("#" + cfg.id);
  if (!wrap) return;
  const rows = cfg.rows(), cols = cfg.cols, G = FA[cfg.state];
  const nr = rows.length, nc = cols.length;
  const cellAt = (r, c) => wrap.querySelector(`td[data-r="${r}"][data-c="${c}"]`);
  const rect = () => [Math.min(G.r0, G.r1), Math.max(G.r0, G.r1), Math.min(G.c0, G.c1), Math.max(G.c0, G.c1)];
  const inRect = (r, c) => { const [ra, rb, ca, cb] = rect(); return r >= ra && r <= rb && c >= ca && c <= cb; };
  const focus = () => { const w = $("#" + cfg.id); if (w) w.focus({ preventScroll: true }); };
  const refresh = () => { cfg.render(); draw(); focus(); };
  const select = (r, c, extend) => {
    if (extend) { G.r1 = r; G.c1 = c; } else { G.r0 = G.r1 = r; G.c0 = G.c1 = c; }
    const m = rows[G.r0];
    if (m && !(FA.sel && FA.sel.kind === cfg.kind && FA.sel.id === m.id)) { FA.sel = { kind: cfg.kind, id: m.id }; renderAll(); draw(); focus(); return; }
    refresh();
  };
  const apply = (r, c, v) => {
    const col = cols[c], m = rows[r];
    if (!col || !m || !col.set || (col.ro && col.ro(m))) return null;
    const err = col.set(m, String(v).trim());
    return err ? `${m.name}: ${err}` : null;
  };
  const commit = errs => { cfg.after(); changed(); const e = errs.filter(Boolean); if (e.length) status(e[0] + (e.length > 1 ? ` (+${e.length - 1})` : ""), true); refresh(); };
  const edit = (r, c, initial) => {
    const td = cellAt(r, c), col = cols[c], m = rows[r];
    if (!td || !col.set || (col.ro && col.ro(m))) return;
    const inp = document.createElement("input");
    inp.type = "text"; inp.className = "fa-cell-edit"; inp.value = initial !== undefined ? initial : col.get(m);
    td.textContent = ""; td.appendChild(inp); inp.focus();
    if (initial === undefined) inp.select(); else inp.setSelectionRange(inp.value.length, inp.value.length);
    let done = false;
    const finish = (save, dr, dc) => {
      if (done) return; done = true;
      const err = save ? apply(r, c, inp.value) : null;
      G.r0 = G.r1 = Math.max(0, Math.min(nr - 1, r + (dr || 0))); G.c0 = G.c1 = Math.max(0, Math.min(nc - 1, c + (dc || 0)));
      commit([err]);
    };
    inp.onkeydown = e => {
      e.stopPropagation();
      if (e.key === "Enter") { e.preventDefault(); finish(true, e.shiftKey ? -1 : 1, 0); }
      else if (e.key === "Tab") { e.preventDefault(); finish(true, 0, e.shiftKey ? -1 : 1); }
      else if (e.key === "Escape") { e.preventDefault(); finish(false); }
    };
    inp.onblur = () => finish(true);
  };
  // drag state on the selection object: kept when the panel is drawn again during a drag
  wrap.querySelectorAll("td[data-r]").forEach(td => {
    td.onmousedown = e => {
      if (e.target.tagName === "INPUT") return;
      const r = +td.dataset.r, c = +td.dataset.c;
      e.preventDefault();
      if (e.target.classList.contains("fill")) { G.fill = { to: r }; return; }
      G.drag = !e.shiftKey;
      G.r1 = r; G.c1 = c;
      if (!e.shiftKey) { G.r0 = r; G.c0 = c; }
      wrap.querySelectorAll("td[data-r]").forEach(x => x.classList.toggle("in", inRect(+x.dataset.r, +x.dataset.c)));
      focus();
    };
    td.onmouseenter = () => {
      const r = +td.dataset.r, c = +td.dataset.c;
      if (G.drag) { G.r1 = r; G.c1 = c; wrap.querySelectorAll("td[data-r]").forEach(x => x.classList.toggle("in", inRect(+x.dataset.r, +x.dataset.c))); }
      if (G.fill) { G.fill.to = r; const [ra, rb, ca, cb] = rect(); wrap.querySelectorAll("td[data-r]").forEach(x => { const xr = +x.dataset.r, xc = +x.dataset.c;
        x.classList.toggle("fillto", xc >= ca && xc <= cb && ((r > rb && xr > rb && xr <= r) || (r < ra && xr < ra && xr >= r))); }); }
    };
    td.ondblclick = () => edit(+td.dataset.r, +td.dataset.c);
  });
  const up = () => {
    if (G.drag) { G.drag = false; select(G.r1, G.c1, true); }
    if (G.fill) {
      const [ra, rb, ca, cb] = rect(), to = G.fill.to, errs = [];
      G.fill = null;
      const h = rb - ra + 1;
      if (to > rb) { for (let r = rb + 1; r <= to; r++) for (let c = ca; c <= cb; c++) errs.push(apply(r, c, cols[c].get(rows[ra + (r - rb - 1) % h]))); G.r1 = to; }
      else if (to < ra) { for (let r = ra - 1; r >= to; r--) for (let c = ca; c <= cb; c++) errs.push(apply(r, c, cols[c].get(rows[rb - (ra - 1 - r) % h]))); G.r0 = to; G.r1 = rb; }
      commit(errs);
    }
  };
  FA.gridUps = FA.gridUps || {};
  if (FA.gridUps[cfg.id]) window.removeEventListener("mouseup", FA.gridUps[cfg.id]);
  FA.gridUps[cfg.id] = up;
  window.addEventListener("mouseup", up);
  wrap.onkeydown = e => {
    if (e.target !== wrap) return;
    const [ra, rb, ca, cb] = rect();
    const mv = (dr, dc) => { e.preventDefault(); const r = Math.max(0, Math.min(nr - 1, (e.shiftKey ? G.r1 : G.r0) + dr)), c = Math.max(0, Math.min(nc - 1, (e.shiftKey ? G.c1 : G.c0) + dc)); select(r, c, e.shiftKey); };
    if (e.key === "ArrowDown") return mv(1, 0);
    if (e.key === "ArrowUp") return mv(-1, 0);
    if (e.key === "ArrowLeft") return mv(0, -1);
    if (e.key === "ArrowRight" || e.key === "Tab") return mv(0, e.key === "Tab" && e.shiftKey ? -1 : 1);
    if (e.key === "Enter" || e.key === "F2") { e.preventDefault(); return edit(G.r0, G.c0); }
    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      const errs = [];
      for (let r = ra; r <= rb; r++) for (let c = ca; c <= cb; c++) if (cfg.clear.includes(cols[c].key)) errs.push(apply(r, c, ""));
      return commit(errs);
    }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); return edit(G.r0, G.c0, e.key); }
  };
  wrap.oncopy = e => {
    const [ra, rb, ca, cb] = rect();
    const out = [];
    for (let r = ra; r <= rb; r++) { const row = []; for (let c = ca; c <= cb; c++) row.push(cols[c].get(rows[r])); out.push(row.join("\t")); }
    e.clipboardData.setData("text/plain", out.join("\n"));
    e.preventDefault();
    status(`${rb - ra + 1} x ${cb - ca + 1} cell(s) copied`);
  };
  wrap.onpaste = e => {
    const text = (e.clipboardData.getData("text/plain") || "").replace(/\r/g, "").replace(/\n$/, "");
    if (!text) return;
    e.preventDefault();
    const src = text.split("\n").map(l => l.split("\t"));
    const [ra, rb, ca, cb] = rect();
    const errs = [];
    if (src.length === 1 && src[0].length === 1) {           // one value: into every selected cell
      for (let r = ra; r <= rb; r++) for (let c = ca; c <= cb; c++) errs.push(apply(r, c, src[0][0]));
    } else {
      const h = Math.max(src.length, rb - ra + 1);
      for (let i = 0; i < h && ra + i < nr; i++) { const row = src[i % src.length]; for (let j = 0; j < row.length && ca + j < nc; j++) errs.push(apply(ra + i, ca + j, row[j])); }
    }
    commit(errs);
  };
  wrap.querySelectorAll("[data-gdelrow]").forEach(b => b.onclick = e => {
    e.stopPropagation();
    const id = b.dataset.gdelrow;
    cfg.del(id);
    if (FA.sel && FA.sel.id === id) FA.sel = null;
    changed(); renderAll(); draw();
  });
}

const MEMBER_GRID = {
  id: "fa-mgrid", state: "grid", kind: "member", rows: () => FA.doc.members, get cols() { return MEMBER_COLS; },
  clear: ["group", "material", "n", "release"],
  empty: '<p class="hint">Beams and rods between two points; an end can be connected to a face of a body. A member on a plate (edge or mid-surface) is tied to the plate.</p>',
  hint: "Click or drag to select cells; type or double-click to edit; Ctrl+C / Ctrl+V copy and paste (also from a spreadsheet); drag the square at the corner of the selection to copy values to other rows. Grey cells come from the group.",
  after: () => syncGroups(), render: () => renderMembers(),
  del: id => { const d = FA.doc; d.members = d.members.filter(x => x.id !== id);
    d.supports = d.supports.filter(s => !(s.target && s.target.member === id)); d.loads = d.loads.filter(l => !(l.target && l.target.member === id)); },
};
function membersTable() { return gridTable(MEMBER_GRID); }
function bindMemberGrid(box) { bindGrid(box, MEMBER_GRID); }

function renderMembers() {
  const d = FA.doc, box = $("#fa-members");
  let h = groupsHtml() + `<p class="hint" style="margin:8px 0 2px"><strong>Members</strong></p>` + membersTable();
  const m = FA.sel && FA.sel.kind === "member" && findItem("member", FA.sel.id);
  const eff = m ? memberEff(m) : null;
  const sec = (eff && eff.section) || { shape: "ROUND", d: 20 };
  if (m && FA.sel.end && m[FA.sel.end]) h += `<p class="fa-pick">End ${FA.sel.end.toUpperCase()} selected (${m[FA.sel.end].xyz.map(v => ffmt(v, 6)).join(", ")}) mm: Support and Load apply to it</p>`;
  if (m) {
    const gdis = eff.group ? " disabled" : "";
    h += `<div class="fa-props"><div class="grid2"><label>Name<input type="text" id="fmb-name" value="${fesc(m.name)}"></label>` +
      `<label>Kind<select id="fmb-kind"${gdis}><option value="beam"${eff.kind === "beam" ? " selected" : ""}>beam</option><option value="rod"${eff.kind === "rod" ? " selected" : ""}>rod (axial)</option></select></label></div>` +
      (eff.group ? `<p class="hint">Kind, section and material from group ${fesc(eff.group.name)} (Group: none in the table to set them here).</p>` : "");
    for (const k of ["a", "b"]) {
      const e = m[k] || {};
      h += `<p class="hint" style="margin:6px 0 2px">End ${k.toUpperCase()} (mm) <button type="button" class="small" data-pick="${k}" title="Click a point on a face (snaps to member ends, plate corners and sketch points), or a face centre with Centre">Pick</button>` +
        `<button type="button" class="small" data-pickc="${k}" title="Centre of the clicked face">Centre</button></p>${v3("fmb-" + k, e.xyz)}` +
        `<label class="check" title="The end is connected to the face by an RBE3 coupling (weighted mean motion of the face nodes)"><input type="checkbox" id="fmb-${k}-face"${e.face ? " checked" : ""}${e.face ? "" : " disabled"}> Connected to ${fesc(e.face ? faceText(e.face) : "a face (pick on a face)")}</label>` +
        (e.face ? `<div class="grid2"><label title="Only the face nodes within this distance of the end are connected (empty: the whole face)">Connection radius (mm)<input type="text" class="numf" id="fmb-${k}-r" value="${e.r || ""}" placeholder="whole face"></label>` +
          `<label title="Distributing: the end moves with the weighted mean of the face nodes (RBE3); rigid: the face nodes move rigidly with the end">Coupling<select id="fmb-${k}-cpl"><option value="">distributing (RBE3)</option><option value="rigid"${e.coupling === "rigid" ? " selected" : ""}>rigid</option></select></label></div>` : "");
    }
    h += `<div class="grid2"><label>Section<select id="fmb-shape"${gdis}>${Object.keys(SECTION_DIMS).map(s => `<option${s === sec.shape ? " selected" : ""}>${s}</option>`).join("")}</select></label>` +
      `<label>Material<select id="fmb-mat"${gdis}>${matOptions(eff.material)}</select></label></div>` +
      `<div class="grid3">${SECTION_DIMS[sec.shape].map(k => `<label>${DIM_LABEL[k]}<input type="text" class="numf" data-dim="${k}" value="${sec[k] !== undefined ? sec[k] : ""}"${gdis}></label>`).join("")}</div>` +
      `<p class="hint" id="fmb-props"></p>`;
    if (eff.kind === "beam") {
      h += `<p class="hint" style="margin:6px 0 2px" title="Direction of the section depth h (local 2-axis), projected normal to the member">Section up vector (local 2-axis, depth h)</p>${v3("fmb-up", m.up || [0, 0, 1])}` +
        `<div class="grid2"><label title="Moments released at the end (hinge); torsion stays connected">Hinge<select id="fmb-rel">${[["", "none"], ["a", "end A"], ["b", "end B"], ["ab", "both ends"]].map(([v, t]) => `<option value="${v}"${(m.release || "") === v ? " selected" : ""}>${t}</option>`).join("")}</select></label>` +
        `<label title="Number of elements (empty: from the element size, at least 4)">Elements<input type="text" class="numf" id="fmb-n" value="${m.n || ""}" placeholder="auto"></label></div>`;
    }
    h += pickHint() + `</div>`;
  }
  box.innerHTML = h;
  bindGroups(box);
  bindMemberGrid(box);
  if (!m) return;
  const upd = () => { changed(); renderMembers(); draw(); };
  $("#fmb-name").onchange = () => { m.name = $("#fmb-name").value.trim() || m.name; upd(); };
  $("#fmb-kind").onchange = () => { m.kind = $("#fmb-kind").value; upd(); };
  for (const k of ["a", "b"]) {
    [0, 1, 2].forEach(i => $(`#fmb-${k}${i}`).onchange = () => { m[k] = Object.assign({}, m[k], { xyz: read3("fmb-" + k) }); upd(); });
    $(`#fmb-${k}-face`).onchange = () => { if (!$(`#fmb-${k}-face`).checked) { delete m[k].face; delete m[k].r; } upd(); };
    if ($(`#fmb-${k}-cpl`)) $(`#fmb-${k}-cpl`).onchange = () => { if ($(`#fmb-${k}-cpl`).value) m[k].coupling = "rigid"; else delete m[k].coupling; changed(); };
    if ($(`#fmb-${k}-r`)) $(`#fmb-${k}-r`).onchange = () => { const v = fnum($(`#fmb-${k}-r`).value); if (v > 0) m[k].r = v; else delete m[k].r; changed(); };
    box.querySelector(`[data-pick="${k}"]`).onclick = () => startPick(`Click the point of end ${k.toUpperCase()}`, { point: true }, hit => {
      m[k] = { xyz: hit.xyz };
      if (hit.face) { m[k].face = hit.face; m[k].r = sectionSize(m.section); }
    });
    box.querySelector(`[data-pickc="${k}"]`).onclick = () => startPick(`Click the face for end ${k.toUpperCase()} (its centre)`, {}, hit => {
      m[k] = { xyz: (hit.centre || hit.xyz).map(v => Math.round(v * 1000) / 1000), face: hit.face };
    });
  }
  $("#fmb-shape").onchange = () => {
    const s = $("#fmb-shape").value;
    const defs = { RECT: { b: 20, h: 40 }, ROUND: { d: 20 }, PIPE: { d: 48.3, t: 3.2 }, BOX: { b: 50, h: 100, t: 4 }, I: { b: 100, h: 200, tf: 8.5, tw: 5.6 }, GENERAL: { A: 1000, I11: 1e5, I22: 1e6, J: 1e4, c1: 50, c2: 100 } };
    m.section = Object.assign({ shape: s }, defs[s]);
    upd();
  };
  box.querySelectorAll("[data-dim]").forEach(inp => inp.onchange = () => { m.section = Object.assign({}, sec, { [inp.dataset.dim]: fnum(inp.value) || 0 }); upd(); });
  $("#fmb-mat").onchange = () => { if ($("#fmb-mat").value) m.material = $("#fmb-mat").value; else delete m.material; changed(); };
  if ($("#fmb-up0")) [0, 1, 2].forEach(i => $("#fmb-up" + i).onchange = () => { m.up = read3("fmb-up"); upd(); });
  if ($("#fmb-rel")) $("#fmb-rel").onchange = () => { m.release = $("#fmb-rel").value; changed(); };
  if ($("#fmb-n")) $("#fmb-n").onchange = () => { const v = Math.round(fnum($("#fmb-n").value)); if (v > 0) m.n = v; else delete m.n; changed(); };
  postJSON("/api/analysis/sections", { section: sec }).then(r => r.json()).then(j => {
    const el = $("#fmb-props");
    if (!el) return;
    el.textContent = j.error ? j.error : `A ${ffmt(j.props.A)} mm^2, I11 ${ffmt(j.props.Ia)} mm^4, I22 ${ffmt(j.props.Ib)} mm^4, J ${ffmt(j.props.J)} mm^4`;
  }).catch(() => {});
}
/** Connection radius of a member end picked on a face: the larger section dimension. */
function sectionSize(sec) {
  sec = sec || {};
  const v = sec.shape === "GENERAL" ? 2 * Math.max(Number(sec.c1) || 0, Number(sec.c2) || 0) : Math.max(...["b", "h", "d"].map(k => Number(sec[k]) || 0));
  return v > 0 ? Math.round(v * 100) / 100 : 20;
}

// ------------------------------------------------------------------ plates

const PLATE_POS = { points: [["mid", "outline is the mid-surface"], ["positive", "on the positive side (right-hand rule of the points)"], ["negative", "on the negative side"]],
                    face: [["positive", "on the face (outside the body)"], ["mid", "centred on the face"], ["negative", "inside the body"]] };
// ------------------------------------------------------------------ plate groups and plate grid

function plateGroupOf(p) { return p && p.group ? (FA.doc.plate_groups || []).find(g => g.id === p.group) || null : null; }
/** Copies thickness, material and element size of every plate group to its plates. */
function syncPlateGroups() {
  for (const p of FA.doc.plates || []) {
    const g = plateGroupOf(p);
    if (!g) continue;
    p.t = g.t;
    if (g.material) p.material = g.material; else delete p.material;
    if (g.size) p.size = g.size; else delete p.size;
  }
}
function setPlateGroup(p, v) {
  const d = FA.doc;
  d.plate_groups = d.plate_groups || [];
  if (!v) { delete p.group; return null; }
  let g = d.plate_groups.find(x => x.name === v);
  if (!g) {
    g = { id: nid("pg"), name: v, t: p.t || 10 };
    if (p.material) g.material = p.material;
    if (p.size) g.size = p.size;
    d.plate_groups.push(g);
  }
  p.group = g.id;
  return null;
}
const PLATE_COLS = [
  { key: "name", title: "Plate", get: p => p.name, set: (p, v) => { if (!v) return "a name is needed"; p.name = v; return null; } },
  { key: "group", title: "Group", get: p => (plateGroupOf(p) || {}).name || "", set: (p, v) => setPlateGroup(p, v) },
  { key: "t", title: "Thickness (mm)", ro: p => !!plateGroupOf(p), get: p => p.t ? ffmt(p.t, 6) : "",
    set: (p, v) => { const n = Number(v); if (!(n > 0)) return "thickness: a positive value"; p.t = n; return null; } },
  { key: "material", title: "Material", ro: p => !!plateGroupOf(p), get: p => p.material || "",
    set: (p, v) => { if (!v) { delete p.material; return null; } const n = Object.keys(FA.doc.materials).find(k => k.toLowerCase() === v.toLowerCase());
      if (!n) return "material not defined: " + v; p.material = n; return null; } },
  { key: "size", title: "Elem. size (mm)", ro: p => !!plateGroupOf(p), get: p => p.size ? ffmt(p.size, 6) : "",
    set: (p, v) => { if (!v) { delete p.size; return null; } const n = Number(v); if (!(n > 0)) return "element size: a positive value or empty"; p.size = n; return null; } },
  { key: "position", title: "Position", get: p => p.position || (p.face ? "positive" : "mid"),
    set: (p, v) => { v = v.toLowerCase(); if (!["mid", "positive", "negative"].includes(v)) return "position: mid, positive or negative"; p.position = v; return null; } },
  { key: "source", title: "Geometry", get: p => p.face ? "face " + faceText(p.face) : (p.points || []).length + " points" },
];
const PLATE_GRID = {
  id: "fa-pgrid", state: "pgrid", kind: "plate", rows: () => FA.doc.plates || [], get cols() { return PLATE_COLS; },
  clear: ["group", "material", "size"],
  empty: '<p class="hint">Plates from a planar face of a body or from outline points; meshed through the thickness (C3D8I) and tied to the faces and plates they touch.</p>',
  hint: "Click or drag to select cells; type or double-click to edit; Ctrl+C / Ctrl+V copy and paste; drag the square at the corner of the selection to copy values to other rows. Grey cells come from the group. Position: mid (the outline or face is the mid-surface), positive, negative.",
  after: () => { syncPlateGroups(); schedulePlates(); }, render: () => renderPlates(),
  del: id => { const d = FA.doc, pc = plateComp({ id }); d.plates = d.plates.filter(x => x.id !== id);
    d.supports = d.supports.filter(s => !(s.target && s.target.comp === pc)); d.loads = d.loads.filter(l => !(l.target && l.target.comp === pc));
    for (const m of d.members) for (const k of ["a", "b"]) if (m[k] && m[k].face && m[k].face.comp === pc) delete m[k].face;
    schedulePlates(); },
};
/** Plate groups table: name, thickness, material, element size and the number of plates; the selected group is
 *  edited below. */
function plateGroupsHtml() {
  const d = FA.doc, gs = d.plate_groups || [];
  let h = `<p class="hint" style="margin:6px 0 2px"><strong>Groups</strong> (thickness, material and element size shared by the plates of the group)</p>`;
  if (gs.length) {
    h += `<table class="pc-table fa-gtable"><tr><th>Group</th><th>t (mm)</th><th>Material</th><th>Elem. size (mm)</th><th>Plates</th><th></th></tr>` + gs.map(g => {
      const sel = FA.selPGroup === g.id;
      return `<tr class="fa-pgrow${sel ? " sel" : ""}" data-pgid="${fesc(g.id)}"><td>${fesc(g.name)}</td><td>${ffmt(g.t, 6)}</td><td>${fesc(g.material || "(default)")}</td>` +
        `<td>${g.size ? ffmt(g.size, 6) : "auto"}</td><td>${(d.plates || []).filter(p => p.group === g.id).length}</td><td><button type="button" class="small" data-pgdel="${fesc(g.id)}" title="Delete the group (its plates keep the values)">&#10005;</button></td></tr>`;
    }).join("") + `</table>`;
  }
  h += `<div class="buttons"><button type="button" class="small" id="fpg-add" title="New group; with a plate selected: from its properties, and the plate joins it">Add group</button></div>`;
  const g = gs.find(x => x.id === FA.selPGroup);
  if (g) h += `<div class="fa-props"><div class="grid2"><label>Name<input type="text" id="fpg-name" value="${fesc(g.name)}"></label><label>Material<select id="fpg-mat">${matOptions(g.material)}</select></label></div>` +
    `<div class="grid2"><label>Thickness (mm)<input type="text" class="numf" id="fpg-t" value="${g.t || ""}"></label>` +
    `<label>Element size (mm)<input type="text" class="numf" id="fpg-size" value="${g.size || ""}" placeholder="auto"></label></div></div>`;
  return h;
}
function bindPlateGroups(box) {
  const d = FA.doc;
  const upd = () => { syncPlateGroups(); changed(); renderPlates(); schedulePlates(); };
  box.querySelectorAll("tr.fa-pgrow").forEach(tr => tr.onclick = e => {
    if (e.target.dataset.pgdel) { const id = e.target.dataset.pgdel; d.plate_groups = (d.plate_groups || []).filter(g => g.id !== id);
      for (const p of d.plates || []) if (p.group === id) delete p.group;
      if (FA.selPGroup === id) FA.selPGroup = null; upd(); return; }
    FA.selPGroup = FA.selPGroup === tr.dataset.pgid ? null : tr.dataset.pgid; renderPlates();
  });
  $("#fpg-add").onclick = () => {
    const p = FA.sel && FA.sel.kind === "plate" && findItem("plate", FA.sel.id);
    d.plate_groups = d.plate_groups || [];
    let k = d.plate_groups.length + 1;
    while (d.plate_groups.some(g => g.name === "Plates " + k)) k++;
    const g = { id: nid("pg"), name: "Plates " + k, t: (p && p.t) || 10 };
    if (p && p.material) g.material = p.material;
    if (p && p.size) g.size = p.size;
    d.plate_groups.push(g);
    if (p) p.group = g.id;
    FA.selPGroup = g.id; upd();
  };
  const g = (d.plate_groups || []).find(x => x.id === FA.selPGroup);
  if (!g) return;
  $("#fpg-name").onchange = () => { g.name = $("#fpg-name").value.trim() || g.name; upd(); };
  $("#fpg-mat").onchange = () => { if ($("#fpg-mat").value) g.material = $("#fpg-mat").value; else delete g.material; upd(); };
  $("#fpg-t").onchange = () => { const v = fnum($("#fpg-t").value); if (v > 0) g.t = v; upd(); };
  $("#fpg-size").onchange = () => { const v = fnum($("#fpg-size").value); if (v > 0) g.size = v; else delete g.size; upd(); };
}

function renderPlates() {
  const d = FA.doc, box = $("#fa-plates");
  d.plates = d.plates || [];
  const errs = FA.plateErr || {};
  let h = plateGroupsHtml() + `<p class="hint" style="margin:8px 0 2px"><strong>Plates</strong></p>` + gridTable(PLATE_GRID);
  const bad = d.plates.filter(p => errs[plateComp(p)]);
  if (bad.length) h += bad.map(p => `<p class="as-bad">${fesc(p.name)}: ${fesc(errs[plateComp(p)])}</p>`).join("");
  const p = FA.sel && FA.sel.kind === "plate" && findItem("plate", FA.sel.id);
  if (p) {
    const kind = p.face ? "face" : "points";
    const gdis = plateGroupOf(p) ? " disabled" : "";
    h += `<div class="fa-props"><div class="grid2"><label>Name<input type="text" id="fpl-name" value="${fesc(p.name)}"></label><label>Material<select id="fpl-mat"${gdis}>${matOptions(p.material)}</select></label></div>` +
      `<div class="grid2"><label>Thickness (mm)<input type="text" class="numf" id="fpl-t" value="${p.t || ""}"${gdis}></label>` +
      `<label title="Element size of the plate (empty: the element size of the analysis)">Element size (mm)<input type="text" class="numf" id="fpl-size" value="${p.size || ""}" placeholder="auto"${gdis}></label></div>` +
      (gdis ? `<p class="hint">Thickness, material and element size from group ${fesc(plateGroupOf(p).name)}.</p>` : "") +
      `<label>Position<select id="fpl-pos">${PLATE_POS[kind].map(([v, t]) => `<option value="${v}"${(p.position || PLATE_POS[kind][0][0]) === v ? " selected" : ""}>${t}</option>`).join("")}</select></label>`;
    if (p.face) h += `<p class="hint">Face: ${fesc(faceText(p.face))} <button type="button" class="small" id="fpl-pick">Pick</button></p>`;
    else h += `<p class="hint" style="margin:6px 0 2px">Outline points (mm), in order <button type="button" class="small" id="fpl-addpt" title="Click points in the view (snaps to member ends, plate corners and sketch points); Esc ends">Pick points</button></p>` +
      `<table class="pc-table">${(p.points || []).map((q, i) => `<tr data-i="${i}">${[0, 1, 2].map(j => `<td><input type="text" class="numf" data-j="${j}" value="${ffmt(q[j], 8)}"></td>`).join("")}<td><button type="button" class="small" data-del="${i}">&#10005;</button></td></tr>`).join("")}</table>` +
      `<button type="button" class="small" id="fpl-row">Add row</button>`;
    h += (errs[plateComp(p)] ? `<p class="as-bad">${fesc(errs[plateComp(p)])}</p>` : "") + pickHint() + `</div>`;
  }
  box.innerHTML = h;
  bindPlateGroups(box);
  bindGrid(box, PLATE_GRID);
  if (!p) return;
  const upd = () => { changed(); renderPlates(); schedulePlates(); };
  $("#fpl-name").onchange = () => { p.name = $("#fpl-name").value.trim() || p.name; changed(); renderPlates(); };
  $("#fpl-mat").onchange = () => { if ($("#fpl-mat").value) p.material = $("#fpl-mat").value; else delete p.material; changed(); };
  $("#fpl-t").onchange = () => { const v = fnum($("#fpl-t").value); if (v > 0) p.t = v; upd(); };
  $("#fpl-size").onchange = () => { const v = fnum($("#fpl-size").value); if (v > 0) p.size = v; else delete p.size; changed(); };
  $("#fpl-pos").onchange = () => { p.position = $("#fpl-pos").value; upd(); };
  if ($("#fpl-pick")) $("#fpl-pick").onclick = () => startPick("Click a planar face for the plate", {}, hit => { p.face = hit.face; });
  if ($("#fpl-addpt")) $("#fpl-addpt").onclick = () => pickPlatePoints(p);
  if ($("#fpl-row")) $("#fpl-row").onclick = () => { const q = (p.points || []).slice(-1)[0] || [0, 0, 0]; p.points = (p.points || []).concat([q.slice()]); upd(); };
  box.querySelectorAll("tr[data-i] input").forEach(inp => inp.onchange = () => { const i = +inp.closest("tr").dataset.i; p.points[i][+inp.dataset.j] = fnum(inp.value) || 0; upd(); });
  box.querySelectorAll("button[data-del]").forEach(b => b.onclick = () => { p.points.splice(+b.dataset.del, 1); upd(); });
}
function pickPlatePoints(p) {
  startPick(`Click outline point ${(p.points || []).length + 1} of ${p.name} (Esc ends)`, { point: true }, hit => {
    p.points = (p.points || []).concat([hit.xyz.map(v => Math.round(v * 1000) / 1000)]);
    setTimeout(() => pickPlatePoints(p), 0);
  });
}
function addPlate(kind) {
  const p = { id: nid("p"), name: "Plate " + ((FA.doc.plates || []).length + 1), t: 10 };
  if (kind === "face") p.position = "positive"; else { p.position = "mid"; p.points = []; }
  FA.doc.plates = (FA.doc.plates || []).concat([p]);
  FA.sel = { kind: "plate", id: p.id };
  changed();
  if (kind === "face") startPick("Click a planar face of a body for the plate", {}, hit => { p.face = hit.face; });
  else pickPlatePoints(p);
}

function mlen(m) { if (!m.a || !m.b || !m.a.xyz || !m.b.xyz) return 0; return Math.hypot(...m.a.xyz.map((a, i) => m.b.xyz[i] - a)); }
function sectionText(s) {
  s = s || {};
  const dims = (SECTION_DIMS[s.shape] || []).filter(k => s[k] !== undefined).map(k => ffmt(s[k], 4));
  return (s.shape || "?") + " " + dims.join(" x ");
}

/** Properties of a new member: those of the selected member of the same kind, else of the last member of that
 *  kind (section, material, group, up vector, elements, hinges), else the defaults. */
function memberTemplate(kind) {
  const sel = FA.sel && FA.sel.kind === "member" && findItem("member", FA.sel.id);
  const src = (sel && sel.kind === kind && sel) || [...FA.doc.members].reverse().find(x => x.kind === kind && x.a && x.b);
  const t = { section: kind === "rod" ? { shape: "ROUND", d: 12 } : { shape: "PIPE", d: 48.3, t: 3.2 }, up: [0, 0, 1] };
  if (src) for (const k of ["section", "material", "group", "up", "n", "release"]) if (src[k] !== undefined) t[k] = JSON.parse(JSON.stringify(src[k]));
  return t;
}
/** Beam or Rod: pick end A, then end B; the next member of the same properties starts at once (Esc ends it and
 *  removes the started member; Esc on the first member keeps it for typed coordinates). */
function addMember(kind, chained) {
  const m = Object.assign({ id: nid("m"), name: (kind === "rod" ? "Rod " : "Beam ") + (FA.doc.members.filter(x => x.kind === kind).length + 1), kind,
                            a: null, b: null }, memberTemplate(kind));
  FA.doc.members.push(m);
  FA.sel = { kind: "member", id: m.id };
  changed();
  const drop = () => { if (chained && !(m.a && m.b)) { FA.doc.members = FA.doc.members.filter(x => x !== m); if (FA.sel && FA.sel.id === m.id) FA.sel = null; changed(); } };
  startPick(`${m.name}: click the point of end A (on a face or at a member end)`, { point: true, onCancel: drop }, hit => {
    m.a = { xyz: hit.xyz }; if (hit.face) { m.a.face = hit.face; m.a.r = sectionSize(m.section); }
    setTimeout(() => startPick(`${m.name}: click the point of end B`, { point: true, onCancel: drop }, h2 => {
      m.b = { xyz: h2.xyz }; if (h2.face) { m.b.face = h2.face; m.b.r = sectionSize(m.section); }
      setTimeout(() => addMember(kind, true), 0);
    }), 0);
  });
}

/** Beams on the straight lines of the sketches; members already on a line are not repeated. */
function membersFromSketch() {
  const lines = sketchLines().filter(ln => ln.length === 2);
  if (!lines.length) return status("No straight sketch lines in the geometry", true);
  const key = (a, b) => [a, b].map(p => p.map(v => v.toFixed(3)).join(",")).sort().join("|");
  const have = new Set(FA.doc.members.filter(m => m.a && m.b && m.a.xyz && m.b.xyz).map(m => key(m.a.xyz, m.b.xyz)));
  let n = 0;
  for (const [a, b] of lines) {
    if (have.has(key(a, b))) continue;
    have.add(key(a, b));
    const m = Object.assign({ id: nid("m"), name: "Beam " + (FA.doc.members.filter(x => x.kind === "beam").length + 1), kind: "beam",
                              a: { xyz: a.slice() }, b: { xyz: b.slice() } }, memberTemplate("beam"));
    FA.doc.members.push(m);
    n++;
  }
  changed(); renderAll(); draw();
  status(n + " beam(s) on the sketch lines" + (n < lines.length ? ", " + (lines.length - n) + " line(s) already had a member" : ""));
}

function renderFasts() {
  const d = FA.doc, box = $("#fa-fasts");
  let h = d.fasteners.map(f => itemRow("fastener", f, `${f.name}`, `d ${ffmt(f.d, 4)} mm, preload ${ffmt(f.preload || 0, 5)} N`)).join("") ||
    '<p class="hint">Bolt as a beam between two faces (hole or bearing faces); the ends are connected to the faces by RBE3 couplings.</p>';
  const f = FA.sel && FA.sel.kind === "fastener" && findItem("fastener", FA.sel.id);
  if (f) {
    h += `<div class="fa-props"><div class="grid2"><label>Name<input type="text" id="ffs-name" value="${fesc(f.name)}"></label><label>Material<select id="ffs-mat">${matOptions(f.material)}</select></label></div>` +
      `<div class="grid2"><label>d (mm)<input type="text" class="numf" id="ffs-d" value="${f.d || ""}"></label><label title="Axial force applied in step 1; step 2 keeps the fastener length">Preload (N)<input type="text" class="numf" id="ffs-pre" value="${f.preload || ""}" placeholder="0"></label></div>` +
      `<p class="hint">Face A: ${fesc(faceText(f.faces && f.faces[0]))} <button type="button" class="small" id="ffs-pa">Pick</button></p>` +
      `<p class="hint">Face B: ${fesc(faceText(f.faces && f.faces[1]))} <button type="button" class="small" id="ffs-pb">Pick</button></p>` +
      `<p class="hint">With a preload the clamped parts must be connected to each other (bonded contact).</p>${pickHint()}</div>`;
  }
  box.innerHTML = h;
  bindRows(box, "fastener", "fasteners");
  if (!f) return;
  $("#ffs-name").onchange = () => { f.name = $("#ffs-name").value.trim() || f.name; changed(); renderFasts(); };
  $("#ffs-mat").onchange = () => { if ($("#ffs-mat").value) f.material = $("#ffs-mat").value; else delete f.material; changed(); };
  $("#ffs-d").onchange = () => { f.d = fnum($("#ffs-d").value) || 0; changed(); renderFasts(); draw(); };
  $("#ffs-pre").onchange = () => { f.preload = fnum($("#ffs-pre").value) || 0; changed(); renderFasts(); };
  $("#ffs-pa").onclick = () => startPick("Click face A (head side)", { cylinder: true }, hit => { f.faces = [hit.face, (f.faces || [])[1] || null]; });
  $("#ffs-pb").onclick = () => startPick("Click face B (nut or thread side)", { cylinder: true }, hit => { f.faces = [(f.faces || [])[0] || null, hit.face]; });
}
function addFastener() {
  const f = { id: nid("f"), name: "Bolt " + (FA.doc.fasteners.length + 1), faces: [null, null], d: 0, preload: 0 };
  FA.doc.fasteners.push(f);
  FA.sel = { kind: "fastener", id: f.id };
  changed();
  startPick("Click face A of the fastener (hole or head bearing face)", { cylinder: true }, hit => {
    f.faces[0] = hit.face;
    const r = faceRef(hit.face);
    if (r && r.kind === "cylinder" && !f.d) f.d = Math.round(2 * r.r * 10) / 10;
    setTimeout(() => startPick("Click face B (nut or thread side)", { cylinder: true }, h2 => {
      f.faces[1] = h2.face;
      const r2 = faceRef(h2.face);
      if (r2 && r2.kind === "cylinder") f.d = Math.min(f.d || Infinity, Math.round(2 * r2.r * 10) / 10);
    }), 0);
  });
}

function targetText(tg) {
  if (!tg) return "(none)";
  if (tg.point !== undefined) { const p = (FA.doc.points || []).find(x => x.id === tg.point); return "reference point " + (p ? p.name : tg.point); }
  if (tg.member !== undefined) { const m = FA.doc.members.find(x => x.id === tg.member); return (m ? m.name : tg.member) + (tg.end ? " end " + tg.end.toUpperCase() : ""); }
  return faceText(tg);
}
function memberEndSelect(id, tg, withLine) {
  const opts = [];
  for (const m of FA.doc.members) {
    if (withLine) opts.push([m.id + ":", m.name + " (whole member)"]);
    else for (const k of ["a", "b"]) opts.push([m.id + ":" + k, m.name + " end " + k.toUpperCase()]);
  }
  const cur = tg && tg.member !== undefined ? tg.member + ":" + (withLine ? "" : tg.end || "a") : "";
  return `<select id="${id}"><option value="">(choose)</option>${opts.map(([v, t]) => `<option value="${fesc(v)}"${v === cur ? " selected" : ""}>${fesc(t)}</option>`).join("")}</select>`;
}

const DOF_NAMES = ["ux", "uy", "uz", "rx", "ry", "rz"];
function renderSups() {
  const d = FA.doc, box = $("#fa-sups");
  let h = d.supports.map(s => itemRow("support", s, `${s.name}: ${s.type}`, targetText(s.target))).join("") || '<p class="hint">Supports on faces of the bodies or at member ends.</p>';
  const s = FA.sel && FA.sel.kind === "support" && findItem("support", FA.sel.id);
  if (s) {
    const onMember = s.target && (s.target.member !== undefined || s.target.point !== undefined);
    const onPoint = s.target && s.target.point !== undefined;
    const types = onMember ? [["fixed", "fixed (all 6)"], ["pinned", "pinned (ux uy uz)"], ["dofs", "chosen components"], ["displacement", "prescribed displacement"]]
                           : [["fixed", "fixed (ux uy uz)"], ["normal", "normal to the face (planar)"], ["dofs", "chosen components"], ["displacement", "prescribed displacement"]];
    const dofs = s.dofs || [1, 1, 1, 0, 0, 0];
    const val = Array.isArray(s.value) ? s.value : [0, 0, 0, 0, 0, 0];
    const ndof = 6;
    h += `<div class="fa-props"><div class="grid2"><label>Name<input type="text" id="fsp-name" value="${fesc(s.name)}"></label>` +
      `<label>Type<select id="fsp-type">${types.map(([v, t]) => `<option value="${v}"${s.type === v ? " selected" : ""}>${t}</option>`).join("")}</select></label></div>` +
      `<p class="hint">Target: ${fesc(targetText(s.target))} <button type="button" class="small" id="fsp-pick" title="Click a face or a member end in the view">Pick</button></p>` +
      (d.members.length ? `<label>or member end${memberEndSelect("fsp-mem", s.target, false)}</label>` : "") +
      (s.type === "dofs" ? `<div class="fa-dofs">${DOF_NAMES.slice(0, ndof).map((n, i) => `<label><input type="checkbox" data-dof="${i}"${dofs[i] ? " checked" : ""}>${n}</label>`).join("")}</div>` : "") +
      (!onMember && (s.type === "dofs" || s.type === "displacement") ? `<p class="hint">rx, ry, rz on a face: the face is rigidly coupled (kinematic coupling) to a node at its centre, which carries the support.</p>` : "") +
      ((d.points || []).length ? `<label>or reference point<select id="fsp-rp"><option value="">(choose)</option>${d.points.map(p => `<option value="${fesc(p.id)}"${onPoint && s.target.point === p.id ? " selected" : ""}>${fesc(p.name)}</option>`).join("")}</select></label>` : "") +
      (s.type === "displacement" ? `<p class="hint">Checked components are prescribed (mm; rotations in rad); unchecked components are free.</p><table class="pc-table fa-disp">` +
        DOF_NAMES.slice(0, ndof).map((n, i) => `<tr><td><label><input type="checkbox" data-dof="${i}"${dofs[i] ? " checked" : ""}>${n}</label></td><td><input type="text" class="numf" data-dval="${i}" value="${val[i] || 0}"${dofs[i] ? "" : " disabled"}></td></tr>`).join("") + `</table>` : "") +
      (s.type === "normal" ? `<label title="Displacement along the outward normal of the face (mm); 0: held">Normal displacement (mm, along the outward normal)<input type="text" class="numf" id="fsp-nval" value="${typeof s.value === "number" ? s.value : 0}"></label>` : "") +
      pickHint() + `</div>`;
  }
  box.innerHTML = h;
  bindRows(box, "support", "supports");
  if (!s) return;
  $("#fsp-name").onchange = () => { s.name = $("#fsp-name").value.trim() || s.name; changed(); renderSups(); };
  $("#fsp-type").onchange = () => {
    s.type = $("#fsp-type").value;
    if (s.type === "displacement" && !Array.isArray(s.value)) { s.value = [0, 0, 0, 0, 0, 0]; if (!s.dofs) s.dofs = [1, 1, 1, 0, 0, 0]; }
    else if (s.type === "normal" && typeof s.value !== "number") s.value = 0;
    else if (s.type !== "displacement" && s.type !== "normal") delete s.value;
    changed(); renderSups(); draw(); };
  $("#fsp-pick").onclick = () => startPick("Click the supported face, a member end or a reference point", { end: true }, hit => supportHit(s, hit));
  if ($("#fsp-rp")) $("#fsp-rp").onchange = () => { if ($("#fsp-rp").value) { s.target = { point: $("#fsp-rp").value }; if (s.type === "normal") s.type = "fixed"; } changed(); renderSups(); draw(); };
  if ($("#fsp-mem")) $("#fsp-mem").onchange = () => { const [mid, end] = $("#fsp-mem").value.split(":"); if (mid) { s.target = { member: mid, end }; if (s.type === "normal") s.type = "fixed"; } changed(); renderSups(); draw(); };
  box.querySelectorAll("[data-dof]").forEach(cb => cb.onchange = () => { const v = (s.dofs || [1, 1, 1, 0, 0, 0]).slice(); v[+cb.dataset.dof] = cb.checked ? 1 : 0; s.dofs = v; changed(); if (s.type === "displacement") renderSups(); });
  box.querySelectorAll("[data-dval]").forEach(inp => inp.onchange = () => { const v = (Array.isArray(s.value) ? s.value : [0, 0, 0, 0, 0, 0]).slice(); v[+inp.dataset.dval] = fnum(inp.value) || 0; s.value = v; changed(); });
  if ($("#fsp-nval")) $("#fsp-nval").onchange = () => { s.value = fnum($("#fsp-nval").value) || 0; changed(); };
}
function supportHit(s, hit) {
  if (hit.point !== undefined && !hit.face) { s.target = { point: hit.point }; if (s.type === "normal") s.type = "fixed"; status(s.name + ": " + targetText(s.target)); return; }
  if (hit.end) { s.target = { member: hit.member, end: hit.end }; if (s.type === "normal") s.type = "fixed"; }
  else { s.target = hit.face; if (s.type === "pinned") s.type = "fixed"; }
  status(s.name + ": " + targetText(s.target));
}
/** Reference points: name, coordinates (typed or picked), faces rigidly connected (*RIGID BODY). */
function renderRps() {
  const d = FA.doc, box = $("#fa-rps");
  d.points = d.points || [];
  let h = d.points.map(p => itemRow("rp", p, p.name, `(${(p.xyz || []).map(v => ffmt(v, 5)).join(", ")}) mm, ${(p.faces || []).length} face(s)`)).join("") ||
    '<p class="hint">A reference point is rigidly connected to faces (CalculiX *RIGID BODY: the faces move as a rigid body with the point). Supports (6 components) and loads (force, moment) act on it; member ends at the point follow it.</p>';
  const p = FA.sel && FA.sel.kind === "rp" && d.points.find(x => x.id === FA.sel.id);
  if (p) {
    h += `<div class="fa-props"><label>Name<input type="text" id="frp-name" value="${fesc(p.name)}"></label>` +
      `<p class="hint" style="margin:6px 0 2px">Point (mm) <button type="button" class="small" id="frp-pick" title="Click a point on a face or a member end">Pick</button>` +
      `<button type="button" class="small" id="frp-centre" title="Centre of the clicked face">Centre</button></p>${v3("frp-p", p.xyz || [0, 0, 0])}` +
      `<p class="hint" style="margin:6px 0 2px">Rigidly connected faces: ${(p.faces || []).map(r => fesc(faceText(r))).join(", ") || "none"}</p>` +
      `<div class="buttons"><button type="button" class="small" id="frp-faces">Add faces</button><button type="button" class="small" id="frp-clear">Clear faces</button></div>` + pickHint() + `</div>`;
  }
  box.innerHTML = h;
  bindRows(box, "rp", "points");
  if (!p) return;
  const upd = () => { changed(); renderRps(); draw(); };
  $("#frp-name").onchange = () => { p.name = $("#frp-name").value.trim() || p.name; upd(); renderSups(); renderLoads(); };
  [0, 1, 2].forEach(i => $("#frp-p" + i).onchange = () => { p.xyz = read3("frp-p"); upd(); });
  $("#frp-pick").onclick = () => startPick(`${p.name}: click the point`, { point: true }, hit => { p.xyz = hit.xyz; });
  $("#frp-centre").onclick = () => startPick(`${p.name}: click the face (its centre)`, {}, hit => { p.xyz = (hit.centre || hit.xyz).map(v => Math.round(v * 1000) / 1000); });
  const addFaces = () => startPick(`${p.name}: click a face to connect (Esc ends)`, {}, hit => {
    p.faces = p.faces || [];
    if (!p.faces.some(r => r.comp === hit.face.comp && r.face === hit.face.face)) p.faces.push(hit.face);
    setTimeout(addFaces, 0);
  });
  $("#frp-faces").onclick = addFaces;
  $("#frp-clear").onclick = () => { p.faces = []; upd(); };
}
/** Ref. point: pick the faces (the point goes to the centre of the first face); Esc ends the face picking. */
function addRp() {
  const d = FA.doc;
  d.points = d.points || [];
  const p = { id: nid("p"), name: "RP " + (d.points.length + 1), xyz: null, faces: [] };
  d.points.push(p);
  FA.sel = { kind: "rp", id: p.id };
  changed();
  const more = () => startPick(`${p.name}: click a face to connect (Esc ends)`, {}, hit => {
    if (!p.xyz) p.xyz = (hit.centre || hit.xyz).map(v => Math.round(v * 1000) / 1000);
    if (!p.faces.some(r => r.comp === hit.face.comp && r.face === hit.face.face)) p.faces.push(hit.face);
    setTimeout(more, 0);
  });
  more();
}

function addSupport() {
  const at = selEnd();
  const s = { id: nid("s"), name: "Support " + (FA.doc.supports.length + 1), type: "fixed", target: at };
  FA.doc.supports.push(s);
  FA.sel = { kind: "support", id: s.id };
  changed();
  if (at) { renderAll(); draw(); status(s.name + ": " + targetText(at)); return; }
  startPick("Click the supported face, a member end or a reference point", { end: true }, hit => supportHit(s, hit));
}

function renderLoads() {
  const d = FA.doc, box = $("#fa-loads");
  const UNITS = { force: "N", mforce: "N", moment: "N mm", mmoment: "N mm", line: "N/mm", gravity: "mm/s^2", pressure: "MPa" };
  const valText = l => (Array.isArray(l.value) ? "(" + l.value.map(v => ffmt(v, 5)).join(", ") + ")" : ffmt(l.value, 5)) + " " + (UNITS[uiType(l)] || "");
  let h = d.loads.map(l => itemRow("load", l, `${l.name}: ${LOAD_TYPES[uiType(l)] || l.type}`, (l.type === "gravity" ? "" : targetText(l.target) + " ") + valText(l))).join("") ||
    '<p class="hint">Forces, moments and pressures on faces, loads at member ends, line loads on members, gravity.</p>';
  const l = FA.sel && FA.sel.kind === "load" && findItem("load", FA.sel.id);
  if (l) {
    const ut = uiType(l);
    const unit = { force: "N", mforce: "N", moment: "N mm", mmoment: "N mm", line: "N/mm", gravity: "mm/s^2" }[ut];
    h += `<div class="fa-props"><div class="grid2"><label>Name<input type="text" id="fld-name" value="${fesc(l.name)}"></label>` +
      `<label>Type<select id="fld-type">${Object.entries(LOAD_TYPES).map(([k, t]) => `<option value="${k}"${k === ut ? " selected" : ""}>${t}</option>`).join("")}</select></label></div>` +
      (ut === "pressure" ? `<label>Pressure (MPa, positive into the face)<input type="text" class="numf" id="fld-p" value="${ffmt(Number(l.value) || 0, 8)}"></label>`
                         : `<p class="hint" style="margin:6px 0 2px">${ut === "force" ? "Total force" : ut === "moment" ? "Moment about the face centre" : ut === "gravity" ? "Acceleration (-9810 in z: gravity down)" : "Value"} (${unit}, global x y z)</p>${v3("fld-v", l.value)}`) +
      (ut !== "gravity" ? `<p class="hint">Target: ${fesc(targetText(l.target))} <button type="button" class="small" id="fld-pick" title="${ut === "pressure" ? "Click a face" : "Click a face, a member end or a member (line load)"} in the view">Pick</button></p>` : "") +
      (["mforce", "mmoment"].includes(ut) ? `<label>Member end${memberEndSelect("fld-mem", l.target, false)}</label>` +
        ((d.points || []).length ? `<label>or reference point<select id="fld-rp"><option value="">(choose)</option>${d.points.map(p => `<option value="${fesc(p.id)}"${l.target && l.target.point === p.id ? " selected" : ""}>${fesc(p.name)}</option>`).join("")}</select></label>` : "") : "") +
      (ut === "line" ? `<label>Member${memberEndSelect("fld-mem", l.target, true)}</label>` : "") + pickHint() + `</div>`;
  }
  box.innerHTML = h;
  bindRows(box, "load", "loads");
  if (!l) return;
  const upd = () => { changed(); renderLoads(); draw(); };
  $("#fld-name").onchange = () => { l.name = $("#fld-name").value.trim() || l.name; upd(); };
  $("#fld-type").onchange = () => {
    const nt = $("#fld-type").value;
    l.type = { mforce: "force", mmoment: "moment" }[nt] || nt;
    if (nt === "pressure") l.value = 0.1; else if (!Array.isArray(l.value)) l.value = nt === "gravity" ? [0, 0, -9810] : [0, 0, -1000];
    if (nt === "gravity") l.target = null;
    if (["mforce", "mmoment", "line"].includes(nt) && !(l.target && (l.target.member !== undefined || (l.target.point !== undefined && nt !== "line")))) l.target = FA.doc.members.length ? { member: FA.doc.members[0].id, end: nt === "line" ? undefined : "b" } : null;
    if (["force", "pressure", "moment"].includes(nt) && l.target && (l.target.member !== undefined || l.target.point !== undefined)) l.target = null;
    l._ui = nt;
    upd();
  };
  if ($("#fld-p")) $("#fld-p").onchange = () => { l.value = fnum($("#fld-p").value) || 0; upd(); };
  if ($("#fld-v0")) [0, 1, 2].forEach(i => $("#fld-v" + i).onchange = () => { l.value = read3("fld-v"); upd(); });
  if ($("#fld-pick")) $("#fld-pick").onclick = () => uiType(l) === "pressure" ? startPick("Click the loaded face", {}, hit => loadHit(l, hit))
    : startPick("Click the loaded face, a member end, a reference point or a member (line load)", { end: true, member: true }, hit => loadHit(l, hit));
  if ($("#fld-rp")) $("#fld-rp").onchange = () => { if ($("#fld-rp").value) l.target = { point: $("#fld-rp").value }; upd(); };
  if ($("#fld-mem")) $("#fld-mem").onchange = () => { const [mid, end] = $("#fld-mem").value.split(":"); l.target = mid ? (end ? { member: mid, end } : { member: mid }) : null; upd(); };
}
function uiType(l) {
  if (l._ui) return l._ui;
  if (l.target && (l.target.member !== undefined || l.target.point !== undefined)) return l.type === "line" ? "line" : l.type === "moment" ? "mmoment" : "mforce";
  return l.type;
}
/** Target of a load from a pick: a member end (force or moment at the end), a member (line load), or a face. */
function loadHit(l, hit) {
  const moment = l.type === "moment";
  if (!Array.isArray(l.value)) l.value = [0, 0, -1000];
  if (hit.point !== undefined && !hit.face) { l.target = { point: hit.point }; if (l.type !== "moment") l.type = "force"; l._ui = l.type === "moment" ? "mmoment" : "mforce"; }
  else if (hit.end) { l.target = { member: hit.member, end: hit.end }; l.type = moment ? "moment" : "force"; l._ui = moment ? "mmoment" : "mforce"; }
  else if (hit.member !== undefined) { if (l.type !== "line") l.value = [0, 0, -1]; l.target = { member: hit.member }; l.type = "line"; l._ui = "line"; }
  else { l.target = hit.face; if (l.type === "line") { l.type = "force"; l.value = [0, 0, -1000]; } l._ui = l.type === "moment" ? "moment" : l.type === "pressure" ? "pressure" : "force"; }
  status(l.name + ": " + targetText(l.target));
}
function addLoad() {
  const at = selEnd();
  const l = { id: nid("l"), name: "Load " + (FA.doc.loads.length + 1), type: "force", target: at, value: [0, 0, -1000] };
  if (at) l._ui = "mforce";
  FA.doc.loads.push(l);
  FA.sel = { kind: "load", id: l.id };
  changed();
  if (at) { renderAll(); draw(); status(l.name + ": " + targetText(at)); return; }
  startPick("Click the loaded face, a member end or a member (line load)", { end: true, member: true }, hit => loadHit(l, hit));
}

// ------------------------------------------------------------------ results panel

function renderResults() {
  const box = $("#fa-results");
  const r = FA.res;
  if (!r || !r.tables) {
    const s = FA.mesh && FA.mesh._summary;
    box.innerHTML = s ? `<p class="hint">Mesh: ${s.nodes} nodes, ${s.elements} elements${s.ties ? ", " + s.ties + " tie(s)" : ""}. ${s.bodies.map(b => fesc(b.name) + " " + b.elements + " " + b.types.join("+")).join(", ")}</p>` : '<p class="hint">Solve to see the results.</p>';
    return;
  }
  const st = $("#fa-state").value || "total";
  const t = r.tables[st];
  if (!t) { box.innerHTML = ""; return; }
  const row = cells => `<tr>${cells.map(c => `<td>${c}</td>`).join("")}</tr>`;
  if (modeResult()) {
    const modal = r.atype === "modal";
    const eff = modal && r.modes.length && r.modes[0].frac;
    let h = `<p class="hint">${fesc(r.name)} solved ${fesc(r.time || "")}: ${modal ? "modal analysis" : "linear buckling analysis"}, ${r.summary.nodes} nodes, ${r.summary.elements} elements, solver ${ffmt(r.summary.solve_time, 3)} s. Shown: ${fesc(stateName(st))}.</p>`;
    h += `<div class="fa-wide"><table class="fa-tbl"><tr><th>Mode</th><th>${modal ? "f (Hz)" : "Buckling factor"}</th>${eff ? "<th>Eff. mass x (%)</th><th>Eff. mass y (%)</th><th>Eff. mass z (%)</th>" : ""}</tr>` +
      r.modes.map(m => `<tr data-mode="${m.mode}" class="${"m" + m.mode === st ? "sel" : ""}" style="cursor:pointer">` + [String(m.mode), ffmt(m.value, 6)].concat(eff ? m.frac.map(f => (100 * f).toFixed(1)) : []).map(c => `<td>${c}</td>`).join("") + "</tr>").join("") + `</table></div>` +
      `<p class="hint">${modal ? "Effective modal mass as a percentage of the total effective mass. Loads are not used." : "Critical loads: buckling factor x the applied loads and prescribed displacements. A negative factor: buckling under the reversed loads."} Mode shapes are normalised to a largest displacement of 1. A click on a row shows the mode.</p>`;
    h += `<div class="row" style="margin-top:8px"><button type="button" id="fr-report">Report</button><button type="button" id="fr-download">Download report</button><button type="button" id="fr-folder">Open run folder</button></div>`;
    box.innerHTML = h;
    box.querySelectorAll("tr[data-mode]").forEach(tr => tr.onclick = () => { $("#fa-state").value = "m" + tr.dataset.mode; draw(); renderResults(); });
    const nm = encodeURIComponent(r.name);
    $("#fr-report").onclick = () => window.open("/api/analysis/report/" + nm, "_blank");
    $("#fr-download").onclick = () => { const a = document.createElement("a"); a.href = "/api/analysis/report/" + nm + "?download=1"; document.body.appendChild(a); a.click(); a.remove(); };
    $("#fr-folder").onclick = () => postJSON("/api/analysis/open_folder", { name: r.name }).catch(showErr);
    return;
  }
  let h = `<p class="hint">${fesc(r.name)} solved ${fesc(r.time || "")}: ${r.summary.nodes} nodes, ${r.summary.elements} elements, solver ${ffmt(r.summary.solve_time, 3)} s. State: ${stateName(st)}.</p>`;
  h += `<div class="fa-wide"><table class="fa-tbl"><tr><th>Body</th><th>max |u| (mm)</th><th>max von Mises (MPa)</th></tr>` +
    t.bodies.map(b => row([fesc(b.name), ffmt(b.umax), ffmt(b.smax)])).join("") + `</table></div>`;
  if (t.members.length) h += `<p class="hint" style="margin:8px 0 2px">Members: maximum section forces (local axes)</p><div class="fa-wide"><table class="fa-tbl"><tr><th>Member</th><th>N (N)</th><th>V1 (N)</th><th>V2 (N)</th><th>T (N mm)</th><th>M1 (N mm)</th><th>M2 (N mm)</th><th>sig (MPa)</th></tr>` +
    t.members.map(m => row([fesc(m.name)].concat(m.max.map(v => ffmt(v)), [ffmt(m.stress)]))).join("") + `</table></div>`;
  if (t.fasteners.length) h += `<p class="hint" style="margin:8px 0 2px">Fasteners</p><div class="fa-wide"><table class="fa-tbl"><tr><th>Fastener</th><th>N (N)</th><th>V (N)</th><th>M (N mm)</th><th>T (N mm)</th><th>sig (MPa)</th></tr>` +
    t.fasteners.map(f => row([fesc(f.name), ffmt(f.N, 5), ffmt(f.V), ffmt(f.M), ffmt(f.T), ffmt(f.stress)])).join("") + `</table></div>`;
  const F = [0, 0, 0];
  for (const x of t.reactions) x.F.forEach((v, i) => { F[i] += v; });
  h += `<p class="hint" style="margin:8px 0 2px">Reactions (moments about the support centre)</p><div class="fa-wide"><table class="fa-tbl"><tr><th>Support</th><th>Fx (N)</th><th>Fy (N)</th><th>Fz (N)</th><th>Mx (N mm)</th><th>My (N mm)</th><th>Mz (N mm)</th></tr>` +
    t.reactions.map(x => row([fesc(x.name)].concat(x.F.map(v => ffmt(v)), x.M.map(v => ffmt(v))))).join("") +
    row(["Sum"].concat(F.map(v => ffmt(v)), ["", "", ""])) + row(["Applied"].concat(t.applied.map(v => ffmt(v)), ["", "", ""])) + `</table></div>`;
  if ((t.points || []).length) h += `<p class="hint" style="margin:8px 0 2px">Reference points</p><div class="fa-wide"><table class="fa-tbl"><tr><th>Point</th><th>ux (mm)</th><th>uy (mm)</th><th>uz (mm)</th><th>rx (rad)</th><th>ry (rad)</th><th>rz (rad)</th></tr>` +
    t.points.map(x => row([fesc(x.name)].concat(x.u.map(v => ffmt(v)), x.rot.map(v => ffmt(v))))).join("") + `</table></div>`;
  h += `<div class="row" style="margin-top:8px"><button type="button" id="fr-report">Report</button><button type="button" id="fr-download">Download report</button><button type="button" id="fr-folder">Open run folder</button></div>`;
  box.innerHTML = h;
  const name = encodeURIComponent(r.name);
  $("#fr-report").onclick = () => window.open("/api/analysis/report/" + name, "_blank");
  $("#fr-download").onclick = () => { const a = document.createElement("a"); a.href = "/api/analysis/report/" + name + "?download=1"; document.body.appendChild(a); a.click(); a.remove(); };
  $("#fr-folder").onclick = () => postJSON("/api/analysis/open_folder", { name: r.name }).catch(showErr);
}

function setStates() {
  const sel = $("#fa-state");
  const sts = !FA.res || !FA.res.states ? [] : modeResult() ? FA.res.states : ["total", "preload", "loads"].filter(s => FA.res.states.includes(s));
  sel.innerHTML = sts.map(s => `<option value="${s}">${fesc(stateName(s))}</option>`).join("");
  sel.disabled = sts.length < 2;
}

// ------------------------------------------------------------------ run

async function runJob(meshOnly) {
  if (FA.job) return;
  const name = (FA.doc.name || "analysis").replace(/[^A-Za-z0-9_\-.]+/g, "_");
  try {
    const j = await (await postJSON("/api/analysis/run", { name, analysis: FA.doc, mesh_only: !!meshOnly })).json();
    FA.job = j.job;
  } catch (e) { showErr(e); return; }
  $("#fa-cancel").disabled = false;
  $("#fa-solve").disabled = $("#fa-mesh").disabled = true;
  const t0 = Date.now();
  const poll = async () => {
    let s;
    try { s = await (await api("/api/analysis/job/" + FA.job)).json(); } catch (e) { s = { state: "error", error: e.message }; }
    if (s.state === "running") {
      $("#fa-info").textContent = `${s.message || s.stage} … ${Math.round((Date.now() - t0) / 1000)} s`;
      setTimeout(poll, 700);
      return;
    }
    FA.job = null;
    $("#fa-cancel").disabled = true;
    $("#fa-solve").disabled = $("#fa-mesh").disabled = false;
    if (s.state === "error") { $("#fa-info").textContent = ""; status(s.error, true); return; }
    const r = s.result;
    FA.mesh = r.payload;
    FA.mesh._summary = r.summary;
    if (r.mesh_only) {
      $("#fa-show").value = "mesh";
      status(`Mesh: ${r.summary.nodes} nodes, ${r.summary.elements} elements (${r.summary.bodies.map(b => b.types.join(" + ")).filter(Boolean).join(", ") || "members"}); input file ${r.files.inp}`);
    } else {
      FA.res = r;
      setStates();
      $("#fa-show").value = "results";
      status(`Solved in ${ffmt((Date.now() - t0) / 1000, 3)} s`);
    }
    renderResults(); draw();
  };
  setTimeout(poll, 400);
}

// ------------------------------------------------------------------ files

let FM = null;
function refreshList() { if (FM) FM.refresh(); refreshSources(); }

async function refreshSources() {
  let asms = [], parts = [];
  try { asms = await (await api("/api/assembly/list")).json(); } catch (e) { /* none */ }
  try { parts = await (await api("/api/part/list")).json(); } catch (e) { /* none */ }
  const s = FA.doc ? FA.doc.source || {} : {};
  const cur = s.name ? s.type + ":" + s.name : "";
  $("#fa-source").innerHTML = `<option value="">(none: members and plates)</option>` +
    (asms.length ? `<optgroup label="Assemblies">${asms.map(n => `<option value="assembly:${fesc(n)}">${fesc(n)}</option>`).join("")}</optgroup>` : "") +
    (parts.length ? `<optgroup label="Parts">${parts.map(n => `<option value="part:${fesc(n)}">${fesc(n)}</option>`).join("")}</optgroup>` : "");
  if (cur && ![...$("#fa-source").options].some(o => o.value === cur)) $("#fa-source").insertAdjacentHTML("beforeend", `<option value="${fesc(cur)}">${fesc(s.name)} (missing)</option>`);
  $("#fa-source").value = cur;
}

async function loadDoc(d) {
  const b = blankDoc(d.name);
  for (const k of Object.keys(b)) if (d[k] === undefined) d[k] = b[k];
  FA.doc = d;
  FA.sel = null; FA.pick = null; FA.mesh = null; FA.res = null;
  FA.dirty = false;
  if (FA.three) FA.three.zoomed = false;
  setStates();
  $("#fa-show").value = "model";
  if (FM) FM.render();
  await refreshSources();
  await loadGeometry();
  {
    try {
      const r = await api("/api/analysis/results/" + encodeURIComponent((d.name || "").replace(/[^A-Za-z0-9_\-.]+/g, "_")));
      const j = await r.json();
      if (FA.doc === d && j.tables) { FA.res = j; FA.mesh = j.payload; FA.mesh._summary = j.summary; setStates(); renderResults(); }
    } catch (e) { /* not solved yet */ }
  }
}

async function saveDoc(name, asNew) {
  FA.doc.name = name;
  const r = await api("/api/analysis/file/" + encodeURIComponent(name), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(FA.doc) });
  const j = await r.json();
  FA.dirty = false;
  status("Saved " + j.path);
}

window.feaShown = async function () {
  if (!FA.three) initThree();
  if (!FA.solver) { try { FA.solver = await (await api("/api/analysis/solver")).json(); } catch (e) { FA.solver = {}; } }
  if (!FA.doc) await loadDoc(blankDoc("analysis"));
  refreshList();
  renderAll();
  setTimeout(resize3, 0);
};

(function bindFea() {
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && FA.pick && !$("#tab-fea").hidden) { endPick(); status("Pick cancelled"); }
  });
  $("#fa-source").onchange = () => {
    const v = $("#fa-source").value;
    const i = v.indexOf(":");
    FA.doc.source = v ? { type: v.slice(0, i), name: v.slice(i + 1) } : { type: "assembly", name: "" };
    FA.mesh = null; FA.res = null; setStates();
    $("#fa-show").value = "model";
    changed(); loadGeometry();
  };
  $("#fa-mesh").onclick = () => runJob(true);
  $("#fa-inp").onclick = () => runJob(true);
  $("#fa-solve").onclick = () => runJob(false);
  $("#fa-cancel").onclick = () => { if (FA.job) postJSON("/api/analysis/cancel/" + FA.job, {}).catch(showErr); };
  $("#fa-openrun").onclick = () => postJSON("/api/analysis/open_folder", { name: (FA.doc.name || "analysis") }).catch(showErr);
  // a toolbar command ends a running pick (a beam chain drops its member without ends)
  document.querySelectorAll("#tab-fea .toolbar button:not([data-faview])").forEach(b => b.addEventListener("click", () => { if (FA.pick) endPick(); }, true));
  $("#fa-add-beam").onclick = () => addMember("beam");
  $("#fa-add-rod").onclick = () => addMember("rod");
  $("#fa-add-skm").onclick = membersFromSketch;
  $("#fa-add-fast").onclick = addFastener;
  $("#fa-add-pface").onclick = () => addPlate("face");
  $("#fa-add-ppts").onclick = () => addPlate("points");
  $("#fa-add-sup").onclick = addSupport;
  $("#fa-add-rp").onclick = addRp;
  $("#fa-add-load").onclick = addLoad;
  document.querySelectorAll("#tab-fea [data-faview]").forEach(b => b.onclick = () => view(b.dataset.faview));
  for (const id of ["#fa-show", "#fa-field", "#fa-scale", "#fa-undef", "#fa-edges", "#fa-axes"]) $(id).onchange = () => {
    if ($("#fa-show").value !== "model" && !FA.mesh) { $("#fa-show").value = "model"; status("Mesh or solve first", true); }
    if ($("#fa-show").value === "results" && !FA.res) { $("#fa-show").value = FA.mesh ? "mesh" : "model"; status("Solve first", true); }
    draw();
  };
  $("#fa-state").onchange = () => { draw(); renderResults(); };
  FM = docFileMenu({ pre: "fa", type: "analysis", label: "analysis", pane: "#tab-fea", listUrl: "/api/analysis/list",
    cur: () => (FA.doc ? { name: FA.doc.name, dirty: !!FA.dirty } : null),
    load: async name => loadDoc(await (await api("/api/analysis/file/" + encodeURIComponent(name))).json()),
    save: saveDoc, blank: () => loadDoc(blankDoc("analysis")), setName: name => { FA.doc.name = name; } });
  window.addEventListener("beforeunload", e => { if (FA.dirty) { e.preventDefault(); e.returnValue = ""; } });
})();

window.__fea = { FA };
window.__feaLoadNamed = async function (name) { await loadDoc(await (await api("/api/analysis/file/" + encodeURIComponent(name))).json()); if (FM) FM.markSaved(name); };
window.__feaSetName = name => { if (FA.doc) { FA.doc.name = name; if (FM) FM.markSaved(name); } };
window.__feaRefresh = refreshList;
window.__feaCurrent = () => (FA.doc ? { name: FA.doc.name, dirty: !!FA.dirty } : null);
