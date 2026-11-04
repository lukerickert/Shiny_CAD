// Explicit tab: explicit analysis with OpenCourant (ORC**3 core, drawgen/explicit). Model from the ShinyCAD geometry
// (bodies, materials, supports, mesh, .inp) or an external .inp; run folders; deck build; local and remote solve; job
// status board and console; results: animation frames on the 3D view, KE/IE curves, post-processing commands.
import * as THREE from "three";
import { TumbleControls } from "/static/vendor/TumbleControls.js";
import { updateAxes } from "/static/axes.js";
import { createNavCube } from "/static/navcube.js";
import { addBodyGroups, bodyMaterials, edgeAt as edgeAtScreen, edgeSegments, edgeLabel } from "/static/bodyview.js";
import * as SM from "/static/shellmodel.js";
import * as RP from "/static/refpoints.js";
import { thicken } from "/static/shellthick.js";
import { drawBcLoads } from "/static/bcglyphs.js";
import * as PN from "/static/panels.js";
import * as MS from "/static/matsel.js";
import * as VS from "/static/viewsel.js";

const XP = { doc: null, dirty: false, meta: null, env: null, envInfo: null, three: null, geo: null, asm: null,
             bbox: null, size: 100, pick: null, sel: null,
             mesh: null, meshSummary: null,                    // view data of the model .inp (Mesh, Show mesh)
             runs: [], runsDir: "",
             res: { folder: "", job: "", data: null, geo: null, frame: null, k: 0, playing: false },
             logSeq: 0, logLines: [], status: null, lastBuild: null, offerSeq: 0, prevRows: {}, seq: 0, timer: null,
             curves: {}, curveSel: "", plotView: { ke: true, ie: false, tot: false, overlay: false }, zoom: {},   // Results energy plot
             rvCurves: {}, rvSummary: "No curve extracted yet.", tools: null, lastEnv: null, histSel: null };
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
const SEL = 0xf08c00, SUP = 0x1c7ed6, MASS = 0x862e9c;
const DOF6 = ["ux", "uy", "uz", "rx", "ry", "rz"];
const SUP_PRESETS = [["", "chosen"], ["fixed", "fixed"], ["pinned", "pinned"], ["xsymm", "symmetry X"], ["ysymm", "symmetry Y"], ["zsymm", "symmetry Z"]];
const PRESET_DOFS = { fixed: [1, 1, 1, 1, 1, 1], pinned: [1, 1, 1, 0, 0, 0], xsymm: [1, 0, 0, 0, 1, 1], ysymm: [0, 1, 0, 1, 0, 1], zsymm: [0, 0, 1, 1, 1, 0] };

function blankDoc(name) {
  return { name: name || "explicit", source: { kind: "shinycad", type: "assembly", name: "", inp: "" },
           materials: { "S355": { library: "Steel S355 (DNVGL 19-Point Standard)", E: 210000, nu: 0.3, rho: 7850 },
                        "Rigid": { library: "", E: 210000, nu: 0.3, rho: 7850 } },
           default_material: "S355", mesh: { size: 0, strategy: "tet", tet_type: "C3D4", hex_type: "C3D8R" }, bonded: true,
           bodies: {}, supports: [], settings: {}, next: 1 };
}
function changed() { XP.dirty = true; if (FM) FM.render(); renderStatusBar(); }
/** Host of the sections and node sets panels (shellmodel.js). */
const SH = {
  doc: () => XP.doc,
  comps: () => ((XP.geo && XP.geo.components) || []).filter(c => c.mesh),
  compName: id => (((XP.asm && XP.asm.components) || []).find(x => x.id === id) || {}).name || id,
  matOptions: cur => matOpts(cur),
  modes: [["shell", "deformable"], ["rigid", "rigid"], ["off", "off"]], nid: p => p + (XP.doc.next++),
  changed: () => changed(), draw: () => draw(), render: () => renderModel(),
  status: (t, e) => status(t, e), postJSON: (u, b) => postJSON(u, b), fmt: v => fmt(v, 6), esc: v => esc(v),
  setTypes: types => VS.setTypes(SH, types),
  suppressCfg: (kind, id) => {
    const d = XP.doc;
    if (kind === "section") { const s = (d.sections || []).find(x => x.id === id); return s ? [s, "mode", "shell"] : null; }
    if (kind === "shell") { d.shells = d.shells || {}; return [d.shells[id] = d.shells[id] || {}, "mode", "shell"]; }
    d.bodies = d.bodies || {};
    return [d.bodies[id] = d.bodies[id] || {}, "role", "deformable"];
  },
  view: {
    canvas: () => XP.three.renderer.domElement, camera: () => XP.three.camera, box: () => $("#xp-view"),
    modelShown: () => $("#xp-show").value === "model",
    showModel: () => { $("#xp-show").value = "model"; draw(); },
    comps: () => ((XP.geo && XP.geo.components) || []).filter(c => c.mesh).map(c => ({ id: c.id, mesh: c.mesh, matrix: matOf(c), surfaces: c.surfaces || [] })),
    points: () => (XP.doc.points || []).filter(p => p.xyz),
    faceAt: e => faceUnder(e), edgeAt: e => edgeUnder(e),
  },
  onNsetSupport: ns => {
    const id = "s" + (XP.doc.next++);
    XP.doc.supports.push({ id, name: "Support " + (XP.doc.supports.length + 1), target: { nset: ns.id }, dofs: [1, 1, 1, 0, 0, 0] });
    XP.sel = { sup: id }; changed(); renderModel(); draw();
  },
};
/** Host of the reference point, spring, joint and equation panels (refpoints.js). */
const CON_KINDS = { rp: 1, spring: 1, joint: 1, eq: 1 };
const RH = {
  doc: () => XP.doc,
  comps: () => ((XP.geo && XP.geo.components) || []).filter(c => c.mesh).map(c => ({ id: c.id, mesh: c.mesh, matrix: matOf(c) })),
  faceRef: r => faceRef(r), edgeRef: r => edgeRefG(r), refText: r => faceText(r),
  nid: p => p + (XP.doc.next++), changed: () => changed(), render: () => renderModel(), draw: () => draw(),
  status: (t, e) => status(t, e), fmt: v => fmt(v, 6), esc: v => esc(v),
  pickPoint: (t, cb) => startPick(t, hit => { cb(hit); status(`Point (${hit.xyz.map(v => fmt(v, 6)).join(", ")}) mm`); }, { snap: true }),
  pickFace: (t, cb) => startPick(t, ref => { if (ref.face !== undefined) cb(ref); }, { only: "face" }),
  pickEdge: (t, cb) => startPick(t, ref => { if (ref.edge !== undefined) cb(ref); }, { only: "edge" }),
  sel: () => XP.csel || null,
  select: (k, id) => { XP.csel = k ? { kind: k, id } : null; renderModel(); draw(); },
  selPoints: () => SM.selState(SH).points,
  collect: opts => VS.collect(SH, opts),
};
function edgeRefG(ref) {
  const c = ref && compOf(ref.comp);
  const r = c && c.erefs && c.erefs[ref.edge];
  if (!r) return null;
  const M = matOf(c);
  return { kind: r.kind, c: new THREE.Vector3(...r.c).applyMatrix4(M).toArray(), dir: r.n ? new THREE.Vector3(...r.n).transformDirection(M).toArray() : null };
}
/** The point a point pick takes under the cursor (refpoints.js snapPoint). */
function snapAt(e) {
  const t = XP.three, rect = t.renderer.domElement.getBoundingClientRect();
  const pts = (XP.doc.points || []).filter(p => p.xyz).map(p => ({ xyz: p.xyz, kind: "rp", label: p.name }));
  const ctx = { x: e.clientX, y: e.clientY, camera: t.camera, rect, points: pts, comps: RH.comps(), mesh: null, face: null };
  const rc = rayAt(e);
  if ($("#xp-show").value === "model") {
    const h = rc.intersectObjects(t.pickables, false).find(x => x.object.userData && x.object.userData.comp !== undefined);
    if (h) {
      const c = compOf(h.object.userData.comp), fi = c && c.mesh ? c.mesh.face_of_tri[h.faceIndex] : null;
      const ref = fi !== null && fi !== undefined ? { comp: c.id, face: fi } : null, fr = ref && faceRef(ref);
      const n = fr && fr.kind === "plane" && fr.n ? fr.n : h.face ? h.face.normal.clone().transformDirection(h.object.matrixWorld).toArray() : null;
      ctx.face = { xyz: h.point.toArray(), normal: n, ref };
    }
  } else {
    const mo = [];
    t.group.traverse(o => { if (o.isMesh && o.userData && o.userData.kind === "mesh") mo.push(o); });
    const h = rc.intersectObjects(mo, false)[0];
    if (h) {
      const g = h.object.geometry;
      ctx.mesh = { pos: g.attributes.position.array, tri: g.index ? g.index.array : null, faceIndex: h.faceIndex };
      ctx.face = { xyz: h.point.toArray(), normal: h.face.normal.clone().transformDirection(h.object.matrixWorld).toArray(), ref: null };
    }
  }
  const sp = RP.snapPoint(ctx);
  if (sp) sp.xyz = sp.xyz.map(v => Math.round(v * 1e6) / 1e6);
  return sp;
}
/** Document setting (the ORC**3 defaults when not set). */
function S(k) { const v = (XP.doc.settings || {})[k]; return v === undefined ? (XP.meta.defaults[k]) : v; }
function setS(k, v) { XP.doc.settings = XP.doc.settings || {}; XP.doc.settings[k] = v; changed(); }
function E(k) { return XP.env ? XP.env[k] : ""; }
function srcKind() { return (XP.doc.source || {}).kind || "shinycad"; }
function isShiny() { return srcKind() === "shinycad"; }
function isDeck() { return srcKind() === "deck"; }
/** The model .inp of the document is written by Mesh (ShinyCAD geometry or deck generator). */
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
  VS.attach(SH);
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
  if (XP.pick && XP.pick.snap) {
    const sp = snapAt(e), r = (XP.size || 100) / 300;
    if (sp) {
      const b = new THREE.Mesh(new THREE.SphereGeometry(r * 2.6, 16, 12), new THREE.MeshBasicMaterial({ color: SEL, transparent: true, opacity: 0.7, depthTest: false }));
      b.position.set(...sp.xyz);
      b.renderOrder = 10;
      t.hover = b;
      t.scene.add(b);
      info(`${sp.label}: (${sp.xyz.map(v => fmt(v, 5)).join(", ")}) mm`);
    }
    t.renderer.domElement.style.cursor = sp ? "crosshair" : "";
    render3();
    return;
  }
  const ty = VS.active(SH) && !XP.pick ? SM.selState(SH).types : null;
  if ((!XP.pick && !ty) || $("#xp-show").value !== "model") { render3(); return; }
  const eg = ty ? (ty.has("edges") ? edgeUnder(e) : null) : XP.pick && XP.pick.only === "face" ? null : edgeUnder(e);
  if (eg) {
    const c = compOf(eg.comp);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(edgeSegments(c.mesh, eg.edge), 3));
    const ls = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: SEL, depthTest: false }));
    ls.matrixAutoUpdate = false;
    ls.matrix.copy(matOf(c));
    ls.renderOrder = 10;
    t.hover = ls;
    t.scene.add(ls);
    t.renderer.domElement.style.cursor = "crosshair";
    render3();
    return;
  }
  const h = rayAt(e).intersectObjects(t.pickables, false).find(x => x.object.userData && x.object.userData.comp !== undefined);
  const c = h && compOf(h.object.userData.comp);
  const fi = c && c.mesh ? c.mesh.face_of_tri[h.faceIndex] : null;
  if (fi !== null && fi !== undefined && !(XP.pick && XP.pick.only === "edge") && !(ty && !ty.has("faces") && !ty.has("bodies"))) {
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
  if (!XP.pick && VS.click(SH, e)) return;                    // selection (viewsel.js): faces, edges, bodies, points
  if (!XP.pick) {
    const h = hitAt(e), ud = (h && h.object.userData) || {};
    const prev = JSON.stringify([XP.sel, XP.csel]);
    if (CON_KINDS[ud.kind]) { XP.csel = { kind: ud.kind, id: ud.id }; XP.sel = null; }
    else { XP.sel = ud.comp !== undefined && $("#xp-show").value === "model" ? { comp: ud.comp } : null; XP.csel = null; }
    if (JSON.stringify([XP.sel, XP.csel]) !== prev) { renderModel(); draw(); }
    return;
  }
  if (XP.pick.snap) {
    const sp = snapAt(e);
    if (!sp) return;
    const cb = XP.pick.cb;
    XP.pick = null;
    cb({ xyz: sp.xyz, normal: sp.normal || null, face: sp.face || null, kind: sp.kind });
    changed(); renderModel(); draw();
    return;
  }
  if (XP.pick.rp) {                                             // a reference point within 10 px
    const t = XP.three, r = t.renderer.domElement.getBoundingClientRect();
    for (const p of XP.doc.points || []) if (p.xyz) {
      const v = new THREE.Vector3(...p.xyz).project(t.camera);
      if (Math.hypot((v.x + 1) / 2 * r.width + r.left - e.clientX, (1 - v.y) / 2 * r.height + r.top - e.clientY) < 10) {
        const cb = XP.pick.cb;
        XP.pick = null;
        cb({ point: p.id });
        changed(); renderModel(); draw();
        return;
      }
    }
  }
  const eg = XP.pick.only === "face" ? null : edgeUnder(e);
  if (eg) {
    const cb = XP.pick.cb;
    XP.pick = null;
    cb(eg);
    changed(); renderModel(); draw();
    return;
  }
  if (XP.pick.only === "edge") return;
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
function startPick(text, cb, opts) {
  opts = opts || {};
  if (!opts.snap && $("#xp-show").value !== "model") { $("#xp-show").value = "model"; draw(); }
  XP.pick = Object.assign({ text, cb }, opts);
  status(text + " (Esc cancels)");
  renderModel();
}
function endPick() { XP.pick = null; renderModel(); draw(); }
/** The face of a component under the cursor: {comp, face}, or null. */
function faceUnder(e) {
  if (!XP.three) return null;
  const h = rayAt(e).intersectObjects(XP.three.pickables, false).find(x => x.object.userData && x.object.userData.comp !== undefined);
  const c = h && compOf(h.object.userData.comp);
  const fi = c && c.mesh ? c.mesh.face_of_tri[h.faceIndex] : null;
  return fi !== null && fi !== undefined ? { comp: c.id, face: fi } : null;
}
/** The edge of a component within 8 px of the cursor: {comp, edge}, or null. */
function edgeUnder(e) {
  const comps = ((XP.geo && XP.geo.components) || []).filter(c => c.mesh).map(c => ({ id: c.id, mesh: c.mesh, matrix: matOf(c) }));
  const h = edgeAtScreen(comps, XP.three.camera, XP.three.renderer.domElement.getBoundingClientRect(), e.clientX, e.clientY, 8);
  return h ? { comp: h.comp, edge: h.edge } : null;
}

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
  if (r.p) out.p = new THREE.Vector3(...r.p).applyMatrix4(M).toArray();
  return out;
}
function faceText(ref) {
  if (!ref) return "(none)";
  const mt = VS.multiText(ref);
  if (mt) return mt;
  const comp = ((XP.asm && XP.asm.components) || []).find(x => x.id === ref.comp);
  if (ref.nset !== undefined) { const ns = (XP.doc.nsets || []).find(x => x.id === ref.nset); return "node set " + (ns ? ns.name : ref.nset); }
  if (ref.point !== undefined) { const p = (XP.doc.points || []).find(x => x.id === ref.point); return "reference point " + (p ? p.name : ref.point); }
  if (ref.edge !== undefined) { const c = compOf(ref.comp); return (comp ? comp.name : ref.comp) + " : " + edgeLabel(c && c.erefs, ref.edge, v => fmt(v, 4)); }
  const r = faceRef(ref);
  return (comp ? comp.name : ref.comp) + " : " + (r ? r.kind + (r.r ? " Ø" + fmt(2 * r.r, 4) : "") + " face " + ref.face : "face " + ref.face);
}
async function sourceAsm() {
  const s = XP.doc.source || {};
  if (s.kind === "inp" || !s.name) return { components: [] };
  if (s.type === "part") return { components: [{ id: "1", name: s.name, source: { type: "part", name: s.name }, pos: [0, 0, 0], rot: [0, 0, 0] }] };
  return await (await api("/api/assembly/file/" + encodeURIComponent(s.name))).json();
}
/** State key of the assembly or part of the geometry (server: sha1 of the assembly file and of its sources). */
async function geometryKey(src) {
  if (!src || !src.name) return "";
  try { return (await (await postJSON("/api/geometry/state", { source: { type: src.type, name: src.name } })).json()).key || ""; } catch (e) { return null; }
}
/** A changed assembly or part marks Update (the update itself is manual). */
async function checkGeometry() {
  if (!XP.doc || $("#tab-xp").hidden || !isShiny() || XP.geoKey === undefined) return;
  const k = await geometryKey(XP.doc.source);
  if (k === null) return;
  const stale = k !== XP.geoKey;
  if (stale !== !!XP.geoStale) {
    XP.geoStale = stale;
    $("#xp-update").classList.toggle("cm-stale", stale);
    $("#xp-update").title = stale ? "The assembly or one of its parts has changed: Update loads the geometry again" : "Load the geometry again (after a change of the assembly or its parts)";
    if (stale) status((XP.doc.source.type === "part" ? "The part " : "The assembly ") + XP.doc.source.name + " has changed: Update loads the geometry again");
  }
}
/** Update: the geometry loaded again; the mesh of the old geometry is cleared (Mesh writes the model .inp again). */
async function updateGeometry() {
  XP.mesh = null; XP.meshSummary = null;
  $("#xp-show").value = "model";
  await loadGeometry();
  renderModel();
  status("Geometry updated");
}

async function loadGeometry() {
  const seq = ++XP.seq;
  XP.geo = { components: [] };
  XP.asm = { components: [] };
  if (isDeck()) { draw(); renderModel(); deckRefresh(); return; }
  if (!isShiny()) { draw(); renderModel(); return; }
  info("Loading the geometry...");
  try {
    const key = await geometryKey(XP.doc.source);
    const asm = await sourceAsm();
    if (seq !== XP.seq) return;
    XP.asm = asm;
    if (!asm.components.length) { info(""); draw(); renderModel(); return; }
    const r = await postJSON("/api/assembly/build", { assembly: asm, have: [...MESHES.keys()] });
    const j = await r.json();
    if (seq !== XP.seq) return;
    for (const c of j.components) if (c.mkey && c.mesh) MESHES.set(c.mkey, { mesh: c.mesh, refs: c.refs || [], erefs: c.erefs || [], surfaces: c.surfaces || [] });
    for (const c of j.components) if (c.mkey && MESHES.has(c.mkey)) { const e = MESHES.get(c.mkey); c.mesh = e.mesh; c.refs = e.refs; c.erefs = e.erefs; c.surfaces = e.surfaces; }
    XP.geo = j;
    XP.geoKey = key === null ? undefined : key;
    XP.geoStale = false;
    $("#xp-update").classList.remove("cm-stale");
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
    e.groups = addBodyGroups(e.geo, m);
  }
  return e;
}
/** Shell settings of a surface body of a component (doc.shells["<component>:<surface>"]). */
function shellCfg(cid, sid) { return (XP.doc.shells || {})[cid + ":" + sid] || {}; }

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
  else if (show === "mesh" && XP.mesh) {
    drawPayload(box, decoded(XP.mesh), null);
    drawCons(box);
    if ($("#xp-bcs").checked && (XP.mesh.bcs || []).length && !box.isEmpty()) {     // supports at the mesh nodes
      const sz = box.getSize(new THREE.Vector3());
      drawBcLoads(t.group, track, decoded(XP.mesh).pos, XP.mesh, Math.max(sz.x, sz.y, sz.z, 1), { loads: false, box });
    }
  }
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
    if (c.mesh.vertices.length) {
      const sm = { shell: undefined, rigid: ROLE_COLOR.rigid, off: undefined };
      const mats = e.groups ? bodyMaterials(mat, c.surfaces, (k, sf) => { const md = shellCfg(c.id, sf.id).mode || "shell"; return { color: sel ? SEL : sm[md], opacity: md === "off" ? 0.12 : 0.6 }; }) : mat;
      const mesh = new THREE.Mesh(e.geo, mats);
      mesh.userData = { comp: c.id };
      inner.add(mesh);
      t.pickables.push(mesh);
      if ($("#xp-edges").checked) inner.add(new THREE.LineSegments(e.edgeGeo, new THREE.LineBasicMaterial({ color: 0x1d2125 })));
      box.union(e.geo.boundingBox.clone().applyMatrix4(inner.matrix));
    }
    for (const o of SM.overlays(SH, c.id)) {                // sections (colour), selected faces and edges
      const g = track(new THREE.BufferGeometry());
      if (o.edge !== undefined) {
        g.setAttribute("position", new THREE.Float32BufferAttribute(edgeSegments(c.mesh, o.edge), 3));
        const ls = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: o.color, depthTest: false }));
        ls.renderOrder = 7;
        inner.add(ls);
        continue;
      }
      g.setAttribute("position", new THREE.Float32BufferAttribute(faceTris(c, o.face), 3));
      inner.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: o.color, transparent: true, opacity: o.opacity, side: THREE.DoubleSide,
                                                               polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 })));
    }
    for (const s of sups) for (const tr of [...VS.targetRefs(SH, s.target).faces, ...VS.targetRefs(SH, s.target).edges]) {
      if (tr.comp !== c.id) continue;
      const strongE = XP.sel && XP.sel.sup === s.id;
      if (tr.edge !== undefined) {
        const g = track(new THREE.BufferGeometry());
        g.setAttribute("position", new THREE.Float32BufferAttribute(edgeSegments(c.mesh, tr.edge), 3));
        const ls = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: strongE ? SEL : SUP, depthTest: false }));
        ls.renderOrder = 8;
        inner.add(ls);
        const pm = new THREE.Points(g, new THREE.PointsMaterial({ color: strongE ? SEL : SUP, size: 5, sizeAttenuation: false, depthTest: false }));
        pm.renderOrder = 8;
        inner.add(pm);
        continue;
      }
      const pos = faceTris(c, tr.face);
      if (!pos.length) continue;
      const g = track(new THREE.BufferGeometry());
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      const strong = XP.sel && XP.sel.sup === s.id;
      inner.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: strong ? SEL : SUP, transparent: true, opacity: strong ? 0.75 : 0.5, side: THREE.DoubleSide,
                                                               polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
    }
    for (const mm of XP.doc.masses || []) {                // distributed masses on faces: purple
      if (mm.kind !== "distributed" || !(mm.target && mm.target.faces)) continue;
      for (const fr of mm.target.faces) {
        if (fr.comp !== c.id) continue;
        const pos = faceTris(c, fr.face);
        if (!pos.length) continue;
        const g = track(new THREE.BufferGeometry());
        g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
        inner.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: MASS, transparent: true, opacity: 0.45, side: THREE.DoubleSide,
                                                                 polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
      }
    }
  }
  drawCons(box);
}
/** Reference points, springs, joints and equations (refpoints.js) and the supports on reference points (cubes). */
function drawCons(box) {
  if (!isShiny()) return;
  const t = XP.three;
  const size = box.isEmpty() ? 100 : Math.max(...box.getSize(new THREE.Vector3()).toArray(), 1);
  RH.pickables = t.pickables;
  RP.drawConstraints(RH, t.group, track, size);
  for (const p of XP.doc.points || []) if (p.xyz) box.expandByPoint(new THREE.Vector3(...p.xyz));
  for (const v of XP.doc.velocities || []) {             // velocities: teal arrows at the body centre or the point
    const t = v.target || {}, vv = new THREE.Vector3(...(v.v || [0, 0, 0]));
    if (vv.lengthSq() < 1e-20) continue;
    let p = null;
    if (t.point !== undefined) p = ((XP.doc.points || []).find(x => x.id === t.point) || {}).xyz || null;
    else if (t.body !== undefined) {
      const c = compOf(String(t.body).startsWith("sec:") ? null : String(t.body).split(":")[0]), e = c && c.mkey && meshGeo(c.mkey);
      if (e) p = e.geo.boundingBox.getCenter(new THREE.Vector3()).applyMatrix4(matOf(c)).toArray();
    }
    if (!p) continue;
    const L = size * 0.2, dir = vv.normalize();
    const a = new THREE.ArrowHelper(dir, new THREE.Vector3(...p).addScaledVector(dir, -L), L, v.kind === "imposed" ? 0x0b7285 : 0x0c8599, L * 0.25, L * 0.12);
    XP.three.group.add(a);
  }
  for (const mm of XP.doc.masses || []) {                // point masses: purple spheres at the reference point
    const p = mm.kind === "point" && mm.target && mm.target.point !== undefined && (XP.doc.points || []).find(x => x.id === mm.target.point);
    if (!p || !p.xyz) continue;
    const m = new THREE.Mesh(track(new THREE.SphereGeometry(size / 45, 16, 12)), new THREE.MeshStandardMaterial({ color: MASS }));
    m.position.set(...p.xyz);
    t.group.add(m);
  }
  for (const s of XP.doc.supports || []) {
    const p = s.target && s.target.point !== undefined && (XP.doc.points || []).find(x => x.id === s.target.point);
    if (!p || !p.xyz) continue;
    const m = new THREE.Mesh(track(new THREE.BoxGeometry(size / 40, size / 40, size / 40)), new THREE.MeshStandardMaterial({ color: XP.sel && XP.sel.sup === s.id ? SEL : SUP, transparent: true, opacity: 0.8 }));
    m.position.set(...p.xyz);
    t.group.add(m);
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
                      lines: p.lines ? b64(p.lines, Uint32Array) : null, n: p.count, thick: p.part_thick || null };
  return p._d;
}
/** Rainbow colour scale in 12 bands (blue low, red high). */
function bandColor(t) {
  if (!isFinite(t)) return new THREE.Color(0xadb5bd);   // no value (element field of another element dimension)
  const n = 12;
  const k = Math.min(n - 1, Math.max(0, Math.floor(t * n)));
  return new THREE.Color().setHSL((1 - k / (n - 1)) * 240 / 360, 0.9, 0.5);
}
/** Triangles (non-indexed) of the view data with positions pos, cell values or nodal values, hidden cells. */
function drawPayload(box, d, opt) {
  const t = XP.three;
  opt = opt || {};
  let pos = opt.pos || d.pos;
  const vis = opt.active || null;
  let tri = d.tri, cell = d.cell, kind = d.kind, Lthick = null;
  // Shell thickness (mesh view): the shell parts with a *SHELL SECTION as slabs of their thickness and offset
  if ($("#xp-thick").checked && d.thick && d.part && !opt.values) {
    const groups = new Map();
    for (let k = 0; k < tri.length / 3; k++) {
      const j = d.part[cell[k]];
      if (d.thick[j]) { if (!groups.has(j)) groups.set(j, []); groups.get(j).push(k); }
    }
    if (groups.size) {
      const E0 = [];
      for (let k = 0; k < tri.length / 3; k++) {
        const a = tri[3 * k], b = tri[3 * k + 1], c = tri[3 * k + 2], kk = kind ? kind[k] : 0;
        if (kk === 0) E0.push(a, b, b, c, c, a); else if (kk === 1) E0.push(a, b, b, c); else E0.push(b, c, c, a);
      }
      const th = thicken(pos, tri, [...groups].map(([j, tris]) => ({ tris, t: d.thick[j][0], off: d.thick[j][1] })), E0);
      pos = th.pos; tri = th.tri; cell = Uint32Array.from(th.tsrc, k => d.cell[k]); kind = null; Lthick = th.edges;
    }
  }
  const ntri = tri.length / 3;
  const P = [], Col = [], L = [];
  const span = (opt.hi - opt.lo) || 1;
  const partCol = PART_COLORS.map(c => new THREE.Color(c));
  const hp = opt.hideParts && d.part ? opt.hideParts : null;
  for (let k = 0; k < ntri; k++) {
    const c = cell[k];
    if (vis && !vis[c]) continue;
    if (hp && hp.has(d.part[c])) continue;
    const a = tri[3 * k], b = tri[3 * k + 1], cc = tri[3 * k + 2];
    for (const v of [a, b, cc]) P.push(pos[3 * v], pos[3 * v + 1], pos[3 * v + 2]);
    let ca, cb, ccol;
    if (opt.values && opt.loc === "cell") { ca = cb = ccol = bandColor((opt.values[c] - opt.lo) / span); }
    else if (opt.values) { ca = bandColor((opt.values[a] - opt.lo) / span); cb = bandColor((opt.values[b] - opt.lo) / span); ccol = bandColor((opt.values[cc] - opt.lo) / span); }
    else { ca = cb = ccol = partCol[(d.part ? d.part[c] : 0) % partCol.length]; }
    Col.push(ca.r, ca.g, ca.b, cb.r, cb.g, cb.b, ccol.r, ccol.g, ccol.b);
    const kk = kind ? kind[k] : 0;                        // element edges: no quadrangle diagonals
    if (Lthick) continue;
    if (kk === 0) L.push(a, b, b, cc, cc, a);
    else if (kk === 1) L.push(a, b, b, cc);
    else L.push(b, cc, cc, a);
  }
  if (Lthick) for (const v of Lthick) L.push(v);
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

/** Parts of the results not shown (Results: Show column): Set of part indices, or null. */
function partHide() { return XP.partHide && XP.partHide.size ? XP.partHide : null; }
/** Parts of the results (PART_ID of the animation file or VTK cells, names of the parts): Show, max |d|, dx dy dz of
 *  largest magnitude, range of the field of the frame. */
function renderParts() {
  const box = $("#xp-parts");
  if (!box) return;
  const g = XP.res.geo, f = XP.res.frame;
  if (!g || !g.parts || !g.parts.length) { box.innerHTML = ""; return; }
  const hide = XP.partHide || new Set(), P = (f && f.parts) || [];
  const fl = (g.fields || []).find(x => x.key === $("#xp-field").value);
  box.innerHTML = `<div class="row wrap"><button type="button" class="small" id="xp-pall">Show all</button>` +
    `<button type="button" class="small" id="xp-psel" title="Show only the parts of the bodies and sections selected in Show Model (Bodies; faces give their body or section), by name">Show selected</button>` +
    `<span class="hint">${hide.size ? hide.size + " part(s) hidden" : ""}</span></div>` +
    `<div class="fa-wide"><table class="fa-tbl xp-parts"><tr><th>Show</th><th>Part</th><th>max |d| (mm)</th><th>dx (mm)</th><th>dy (mm)</th><th>dz (mm)</th><th>${esc(fl ? fl.label : "Field")} min</th><th>max</th></tr>` +
    g.parts.map((p, j) => { const q = P[j] || {}; return `<tr><td><input type="checkbox" data-pshow="${j}"${hide.has(j) ? "" : " checked"}></td><td>${esc(p.id + " " + p.name)}</td>` +
      [q.umax, ...(q.ucomp || [undefined, undefined, undefined]), q.min, q.max].map(v => `<td>${v === undefined ? "-" : fmt(v)}</td>`).join("") + `</tr>`; }).join("") +
    `</table></div><p class="hint">Frame ${f ? f.index + 1 : "-"}. dx, dy, dz: the component of largest magnitude over the nodes of the part. Show: the parts drawn; the colour range is taken from the parts shown.</p>`;
  box.querySelectorAll("[data-pshow]").forEach(cb => cb.onchange = () => {
    XP.partHide = XP.partHide || new Set();
    if (cb.checked) XP.partHide.delete(+cb.dataset.pshow); else XP.partHide.add(+cb.dataset.pshow);
    draw(); renderParts();
  });
  $("#xp-pall").onclick = () => { XP.partHide = new Set(); draw(); renderParts(); };
  $("#xp-psel").onclick = () => {
    // part names of inp2rad: the ELSET of the body (B_<NAME>) or of the section (<NAME>)
    const names = new Set();
    for (const [kind, id] of VS.suppressTargets(SH, VS.items(SH, ["faces", "bodies"]))) {
      if (kind === "section") { const s = (XP.doc.sections || []).find(x => x.id === id); if (s) names.add(String(s.name).toUpperCase()); }
      else { const n = bodyElsetName(id); if (n) names.add(n); }
    }
    if (!names.size) { status("Select bodies (Bodies) or faces in Show Model first", true); return; }
    const keep = new Set(g.parts.map((p, j) => [p, j]).filter(([p]) => { const t = String(p.name).toUpperCase().trim(); return names.has(t) || names.has(t.replace(/^B_/, "")) || [...names].some(n => t === "B_" + n); }).map(([, j]) => j));
    if (!keep.size) { status("No part of the results has the name of the selected bodies or sections", true); return; }
    XP.partHide = new Set(g.parts.map((p, j) => j).filter(j => !keep.has(j)));
    draw(); renderParts();
  };
}
/** Name of the body in the model .inp (model_inp.py: the component name, "component / surface body" for a shell,
 *  as safe upper case). */
function bodyElsetName(bid) {
  const comps = (XP.asm && XP.asm.components) || [];
  const cid = bid.includes(":") ? bid.slice(0, bid.lastIndexOf(":")) : bid;
  const c = comps.find(x => x.id === cid);
  if (!c) return null;
  let n = c.name || cid;
  if (bid.includes(":")) {
    const g = ((XP.geo && XP.geo.components) || []).find(x => x.id === cid), sid = bid.slice(bid.lastIndexOf(":") + 1);
    const sf = g && (g.surfaces || []).find(x => String(x.id) === sid);
    n += " / " + (sf ? sf.name : sid);
  }
  return (String(n).replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "") || "X").slice(0, 40).toUpperCase();
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
    const hp = partHide();
    if (hp && f.parts) { f.parts.forEach((q, j) => { if (!hp.has(j) && q.min !== undefined) { a = Math.min(a, q.min); b = Math.max(b, q.max); } }); }
    else if (f.loc === "cell") { for (let i = 0; i < vals.length; i++) if (!fd.active || !$("#xp-eroded").checked || fd.active[i]) { const v = vals[i]; if (isFinite(v)) { if (v < a) a = v; if (v > b) b = v; } } }
    else for (let i = 0; i < vals.length; i++) { const v = vals[i]; if (isFinite(v)) { if (v < a) a = v; if (v > b) b = v; } }
    if (!isFinite(a)) { a = 0; b = 0; }
    if (!isFinite(lo)) lo = a;
    if (!isFinite(hi)) hi = b;
  }
  drawPayload(box, d, { pos, values: vals, loc: f.loc, lo, hi, active: $("#xp-eroded").checked ? fd.active : null, undeformed: $("#xp-undef").checked, hideParts: partHide() });
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
  // document settings with a file dialog: data-browse-s="<key>" data-kind="open|folder|save" data-filter="json|rad|..."
  box.querySelectorAll("[data-browse-s]").forEach(b => b.onclick = async () => {
    const k = b.dataset.browseS;
    const cur = String(S(k) || "").trim();
    try {
      const p = await window.browse(b.dataset.kind || "open", b.dataset.filter || "", b.dataset.kind === "folder" ? cur : cur.replace(/[\\/][^\\/]*$/, ""));
      if (p) { setS(k, p.replace(/\\/g, "/")); if (after) after(k); }
    } catch (e) { showErr(e); }
  });
  bindHelp(box);
}
/** Text field of a document setting with a file dialog button. */
function inSB(k, label, w, kind, filter, title) {
  return `<label class="inline xp-f"${title ? ` title="${esc(title)}"` : ""}>${esc(label)}<input type="text" data-s="${k}" value="${esc(S(k))}" style="width:${w || 160}px"></label>` +
    `<button type="button" class="small" data-browse-s="${k}" data-kind="${kind}" data-filter="${filter || ""}" title="Browse">…</button>`;
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
  if ((sec === "rigidify" || sec === "point_mass") && isModel()) return true;   // Model: Bodies role rigid, Masses
  const spec = (XP.meta.mode_spec[S("analysis_mode")] || {}).hide_sections || [];
  return spec.includes(sec);
}

// ------------------------------------------------------------------ "?" pop-ups (ORC**3 *_DOC texts)
// doc: text, or {mode: text} (one section per mode; the current mode first). Markup: "## " sub-heading, "* " bullet,
// 4-space indent code line, other lines paragraphs.
const HELP = new Map();
function helpBtn(title, doc, current) {
  HELP.set(title, { doc, current });
  return `<button type="button" class="small xp-q" data-help="${esc(title)}" title="${esc(title)}">?</button>`;
}
function bindHelp(box) { box.querySelectorAll("[data-help]").forEach(b => b.onclick = () => showHelp(b.dataset.help)); }
function docHtml(body) {
  let h = "", ul = false;
  for (const ln of String(body || "").split("\n")) {
    const li = ln.startsWith("* ");
    if (li && !ul) { h += "<ul>"; ul = true; }
    if (!li && ul) { h += "</ul>"; ul = false; }
    if (ln.startsWith("## ")) h += `<h4>${esc(ln.slice(3))}</h4>`;
    else if (li) h += `<li>${esc(ln.slice(2))}</li>`;
    else if (ln.startsWith("    ") && ln.trim()) h += `<pre>${esc(ln.replace(/^ {4}/, ""))}</pre>`;
    else if (ln.trim()) h += `<p>${esc(ln)}</p>`;
  }
  return h + (ul ? "</ul>" : "");
}
function showHelp(title) {
  const e = HELP.get(title);
  if (!e) return;
  let secs = typeof e.doc === "object" ? Object.entries(e.doc) : [[null, e.doc]];
  if (e.current !== undefined && e.current !== null) secs = [...secs.filter(s => s[0] === e.current), ...secs.filter(s => s[0] !== e.current)];
  let dlg = $("#xp-help");
  if (!dlg) {
    document.body.insertAdjacentHTML("beforeend", `<div id="xp-help" class="modal" hidden><div class="modal-box xp-helpbox"><strong id="xp-help-t"></strong><div id="xp-help-b" class="xp-helpbody"></div><div class="buttons"><button type="button" id="xp-help-close">Close</button></div></div></div>`);
    dlg = $("#xp-help");
    $("#xp-help-close").onclick = () => { dlg.hidden = true; };
    dlg.onclick = ev => { if (ev.target === dlg) dlg.hidden = true; };
    document.addEventListener("keydown", ev => { if (ev.key === "Escape" && !dlg.hidden) dlg.hidden = true; });
  }
  $("#xp-help-t").textContent = title;
  $("#xp-help-b").innerHTML = secs.map(([k, body]) => (k === null ? "" : `<h3 class="${k === e.current ? "" : "dim"}">${k === e.current ? "●" : "○"} ${esc(k)}${k === e.current ? " (selected)" : ""}</h3>`) + docHtml(body)).join("");
  dlg.hidden = false;
  $("#xp-help-b").scrollTop = 0;
}

// ------------------------------------------------------------------ line plots (energy, rivet F-d): SVG with zoom
// series: [{name, x, y, color, dash, peak: [x, y]}]; opts: {xlabel, ylabel, title, empty, height}.
// Drag a rectangle: zoom; double-click: full range (XP.zoom[key]).
const PLOT_COLORS = ["#1f5fae", "#e8590c", "#2f9e44", "#ae3ec9", "#c2255c", "#0c8599", "#f08c00", "#5c940d"];
function svgPlot(box, key, series, opts = {}) {
  if (!box) return;
  XP.zoom = XP.zoom || {};
  const W = Math.max(280, box.clientWidth || 440), H = opts.height || 220, L = 62, R = 10, T = opts.title ? 22 : 12, B = 32;
  if (!series.length) { box.innerHTML = `<p class="hint">${esc(opts.empty || "No curves.")}</p>`; return; }
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const s of series) for (let i = 0; i < s.x.length; i++) {
    const x = s.x[i], y = s.y[i];
    if (!isFinite(x) || !isFinite(y)) continue;
    if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
  }
  if (!isFinite(x0)) { x0 = 0; x1 = 1; y0 = 0; y1 = 1; }
  if (opts.zeroY !== false && y0 > 0) y0 = 0;
  if (x1 === x0) x1 = x0 + 1;
  if (y1 === y0) y1 = y0 + 1;
  const z = XP.zoom[key];
  if (z) ({ x0, x1, y0, y1 } = z);
  const X = v => L + (v - x0) / (x1 - x0) * (W - L - R), Y = v => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  let s = `<svg width="${W}" height="${H}" class="xp-svg" data-plot="${esc(key)}"><defs><clipPath id="clip-${esc(key)}"><rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}"/></clipPath></defs>`;
  s += `<rect x="0" y="0" width="${W}" height="${H}" fill="#fff"/>`;
  for (let k = 0; k <= 4; k++) {
    const yv = y0 + (y1 - y0) * k / 4, xv = x0 + (x1 - x0) * k / 4;
    s += `<line x1="${L}" x2="${W - R}" y1="${Y(yv)}" y2="${Y(yv)}" class="g"/><text x="${L - 4}" y="${Y(yv) + 4}" text-anchor="end">${fmt(yv, 3)}</text>`;
    s += `<line y1="${T}" y2="${H - B}" x1="${X(xv)}" x2="${X(xv)}" class="g"/><text x="${X(xv)}" y="${H - B + 14}" text-anchor="middle">${fmt(xv, 3)}</text>`;
  }
  s += `<text x="${W - R}" y="${H - 3}" text-anchor="end">${esc(opts.xlabel || "")}</text><text x="4" y="10">${esc(opts.ylabel || "")}</text>`;
  if (opts.title) s += `<text x="${(L + W - R) / 2}" y="14" text-anchor="middle" font-weight="600">${esc(opts.title)}</text>`;
  s += `<g clip-path="url(#clip-${esc(key)})">`;
  series.forEach(sr => {
    const pts = [];
    for (let i = 0; i < sr.x.length; i++) if (isFinite(sr.x[i]) && isFinite(sr.y[i])) pts.push(X(sr.x[i]).toFixed(1) + "," + Y(sr.y[i]).toFixed(1));
    s += `<polyline fill="none" stroke="${sr.color}" stroke-width="1.6"${sr.dash ? ` stroke-dasharray="${sr.dash}"` : ""} points="${pts.join(" ")}"/>`;
    if (sr.peak && isFinite(sr.peak[0]) && isFinite(sr.peak[1])) s += `<circle cx="${X(sr.peak[0])}" cy="${Y(sr.peak[1])}" r="3" fill="${sr.color}"/>`;
  });
  if (opts.marker !== undefined && opts.marker !== null && isFinite(opts.marker)) s += `<line x1="${X(opts.marker)}" x2="${X(opts.marker)}" y1="${T}" y2="${H - B}" stroke="#f08c00" stroke-dasharray="3,3"/>`;
  s += `</g>`;
  if (series.length > 1 || opts.legend) series.forEach((sr, i) => { s += `<text x="${W - R - 4}" y="${T + 12 + 13 * i}" text-anchor="end" fill="${sr.color}">${esc(sr.name)}</text>`; });
  s += `<rect class="xp-zoomrect" x="0" y="0" width="0" height="0" fill="rgba(31,95,174,0.12)" stroke="#1f5fae" stroke-dasharray="3,2" visibility="hidden"/></svg>`;
  box.innerHTML = s + `<p class="hint xp-plothint">Drag: zoom · double-click: full range</p>`;
  const svg = box.querySelector("svg");
  const rect = svg.querySelector(".xp-zoomrect");
  const inv = (px, py) => [x0 + (px - L) / (W - L - R) * (x1 - x0), y0 + (1 - (py - T) / (H - T - B)) * (y1 - y0)];
  const loc = ev => { const b = svg.getBoundingClientRect(); return [ev.clientX - b.left, ev.clientY - b.top]; };
  svg.onmousedown = ev => {
    if (ev.button !== 0) return;
    ev.preventDefault();
    const [ax, ay] = loc(ev);
    const move = e2 => {
      const [bx, by] = loc(e2);
      rect.setAttribute("x", Math.min(ax, bx)); rect.setAttribute("y", Math.min(ay, by));
      rect.setAttribute("width", Math.abs(bx - ax)); rect.setAttribute("height", Math.abs(by - ay));
      rect.setAttribute("visibility", "visible");
    };
    const up = e2 => {
      window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up);
      rect.setAttribute("visibility", "hidden");
      const [bx, by] = loc(e2);
      if (Math.abs(bx - ax) < 6 || Math.abs(by - ay) < 6) return;
      const [u0, v1] = inv(Math.min(ax, bx), Math.min(ay, by)), [u1, v0] = inv(Math.max(ax, bx), Math.max(ay, by));
      XP.zoom[key] = { x0: u0, x1: u1, y0: v0, y1: v1 };
      svgPlot(box, key, series, opts);
    };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  };
  svg.ondblclick = () => { delete XP.zoom[key]; svgPlot(box, key, series, opts); };
}
/** PNG (data URL) of the SVG of a plot box, scale 2. */
function plotPng(box) {
  const svg = box && box.querySelector("svg");
  if (!svg) return Promise.reject(new Error("no plot"));
  const w = +svg.getAttribute("width"), h = +svg.getAttribute("height");
  const c = svg.cloneNode(true);
  c.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  c.querySelectorAll(".xp-zoomrect").forEach(r => r.remove());
  c.querySelectorAll("text").forEach(t => { if (!t.getAttribute("fill")) t.setAttribute("fill", "#495057"); t.setAttribute("font-family", "sans-serif"); t.setAttribute("font-size", "10"); });
  c.querySelectorAll("line.g").forEach(l => l.setAttribute("stroke", "#dee2e6"));
  const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(c));
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => {
      const cv = document.createElement("canvas");
      cv.width = w * 2; cv.height = h * 2;
      const g = cv.getContext("2d");
      g.scale(2, 2); g.fillStyle = "#fff"; g.fillRect(0, 0, w, h); g.drawImage(img, 0, 0);
      res(cv.toDataURL("image/png"));
    };
    img.onerror = () => rej(new Error("the plot could not be rendered"));
    img.src = url;
  });
}
async function savePlotPng(box, name, initial) {
  try {
    const p = await window.browse("save", "png", initial || "", "Save plot as PNG", name);
    if (!p) return;
    const data = await plotPng(box);
    const j = await (await postJSON("/api/explicit/save_png", { path: p, data })).json();
    status("Plot saved: " + j.path);
    poll();
  } catch (e) { showErr(e); }
}

// ------------------------------------------------------------------ Model panel

function renderModel() {
  const box = section("xp-model");
  if (!box || !XP.doc) return;
  renderStatusBar();
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
  h += `<div id="xp-panels"></div>`;
  h += materialsHtml();
  const comps = (XP.asm && XP.asm.components) || [];
  h += `<h3 class="xp-h">Bodies</h3>` + bodiesHtml();
  h += `<h3 class="xp-h">Mesh</h3>` + meshHtml();
  const opt = (k, title, div) => PN.isHidden(XP.doc, k) ? "" : `<h3 class="xp-h" id="xp-h-${k}">${title}</h3>` + div;
  if (comps.some(c => ((compOf(c.id) || {}).surfaces || []).length)) h += opt("sections", "Sections", `<div id="xp-sections"></div>`);
  h += opt("nsets", "Node sets", `<div id="xp-nsets"></div>`) + opt("rps", "Reference points", `<div id="xp-rps"></div>`) +
    opt("springs", "Springs", `<div id="xp-springs"></div>`) + opt("joints", "Joints", `<div id="xp-joints"></div>`) + opt("eqs", "Equations", `<div id="xp-eqs"></div>`);
  h += `<h3 class="xp-h">Supports</h3>` + supportsHtml();
  h += opt("vels", "Velocities", `<div id="xp-vels"></div>`) + opt("masses", "Masses", `<div id="xp-masses"></div>`) +
    opt("init", "Initial state (static)", `<div id="xp-init"></div>`);
  if (XP.pick) h += `<p class="fa-pick">${esc(XP.pick.text)}</p>`;
  h += XP.meshSummary ? summaryHtml(XP.meshSummary) : `<p class="hint">Mesh (toolbar) meshes the bodies and shells, writes the model .inp and shows the mesh.</p>`;
  box.innerHTML = h;
  $("#xp-kind").onchange = setKind;
  bindMaterials(box);
  bindBodies(box);
  bindMesh(box);
  bindSupports(box);
  if ($("#xp-sections")) SM.renderSections(SH, $("#xp-sections"));
  if ($("#xp-nsets")) SM.renderNsets(SH, $("#xp-nsets"));
  renderVelocities($("#xp-vels"));
  renderMasses($("#xp-masses"));
  renderInit($("#xp-init"));
  if ($("#xp-rps")) RP.renderPoints(RH, $("#xp-rps"));
  if ($("#xp-springs")) RP.renderSprings(RH, $("#xp-springs"));
  if ($("#xp-joints")) RP.renderJoints(RH, $("#xp-joints"));
  if ($("#xp-eqs")) RP.renderEquations(RH, $("#xp-eqs"));
  const d0 = XP.doc;
  PN.renderToggles($("#xp-panels"), d0, [["sections", "Sections", (d0.sections || []).length], ["nsets", "Node sets", (d0.nsets || []).length],
    ["rps", "Reference points", (d0.points || []).length], ["springs", "Springs", (d0.springs || []).length], ["joints", "Joints", (d0.joints || []).length],
    ["eqs", "Equations", (d0.equations || []).length], ["vels", "Velocities", (d0.velocities || []).length], ["masses", "Masses", (d0.masses || []).length],
    ["init", "Initial state", (d0.initial_state || {}).analysis ? 1 : 0]]
    .map(([key, label, count]) => ({ key, label, count })), () => { changed(); renderModel(); });
  if (XP.popup) renderPopup();
}
/** Bodies and shells tables. */
function bodiesHtml() {
  let h = "";
  const mats = XP.doc.materials || {};
  const comps = (XP.asm && XP.asm.components) || [];
  if (!comps.length) h += `<p class="hint">Choose the geometry in the toolbar.</p>`;
  const hasSolid = c => { const g = compOf(c.id); const m = g && g.mesh; return !m || (m.triangles.length > 0 && (!m.face_body || m.face_body.some(v => v === null || v === undefined))); };
  const shells = [];
  for (const c of comps) { const g = compOf(c.id); for (const sf of (g && g.surfaces) || []) shells.push([c, sf]); }
  if (comps.length && comps.some(hasSolid)) h += `<table class="fa-tbl xp-bodies"><tr><th>Component</th><th>Role</th><th>Material</th><th>Size (mm)</th><th>Mesh</th></tr>` +
    comps.filter(hasSolid).map(c => {
      const b = (XP.doc.bodies || {})[c.id] || {};
      const sel = XP.sel && XP.sel.comp === c.id;
      return `<tr data-b="${esc(c.id)}"${sel ? ' class="sel"' : ""}><td title="${esc(c.name)}">${esc(c.name)}</td>` +
        `<td><select data-bk="role">${optList([["deformable", "deformable"], ["rigid", "rigid (impactor)"], ["off", "off"]], b.role || "deformable")}</select></td>` +
        `<td><select data-bk="material" class="xp-matsel">${matOpts(b.material)}</select></td>` +
        `<td><input type="text" data-bk="size" value="${esc(b.size || "")}" style="width:46px" placeholder="auto"></td>` +
        `<td><select data-bk="strategy"><option value="">(default)</option>${optList(MESH_STRATEGIES, b.strategy || "")}</select></td></tr>`;
    }).join("") + `</table><p class="hint">Rigid: *RIGID BODY over the nodes of the body, REF NODE at its centre of mass with the masses on it (the /RBODY main node driven by the Build loading or the Velocities). A reference point coupled to a rigid body is a node of it. Rigid bodies are meshed apart from the deformable bodies.</p>`;
  if (shells.length) h += `<table class="fa-tbl xp-shells"><tr><th>Shell</th><th>Role</th><th>t (mm)</th><th>Position</th><th>Material</th><th>Size (mm)</th></tr>` +
    shells.map(([c, sf]) => {
      const key = c.id + ":" + sf.id, b = (XP.doc.shells || {})[key] || {};
      return `<tr data-shell="${esc(key)}"><td title="${esc(c.name)} / ${esc(sf.name)}">${esc(c.name)} / ${esc(sf.name)}</td>` +
        `<td><select data-hk="mode">${optList([["shell", "deformable"], ["rigid", "rigid (impactor)"], ["off", "off"]], b.mode || "shell")}</select></td>` +
        `<td><input type="text" data-hk="t" value="${esc(b.t || "")}" style="width:46px" placeholder="10"></td>` +
        `<td><select data-hk="offset">${optList([["mid", "mid"], ["positive", "positive (SPOS)"], ["negative", "negative (SNEG)"]], b.offset || "mid")}</select></td>` +
        `<td><select data-hk="material" class="xp-matsel">${matOpts(b.material)}</select></td>` +
        `<td><input type="text" data-hk="size" value="${esc(b.size || "")}" style="width:46px" placeholder="auto"></td></tr>`;
    }).join("") + `</table><p class="hint">Shells: the surface bodies of the parts, meshed with shell elements (Shell elements in Mesh) of thickness t (empty: 10 mm), *SHELL SECTION per shell. Position: OFFSET=SPOS / SNEG (inp2rad does not read the offset). Touching shells share their nodes (Bonded).</p>`;
  return h;
}
function bindBodies(box) {
  box.querySelectorAll("tr[data-b]").forEach(tr => {
    const cid = tr.dataset.b;
    tr.querySelectorAll("[data-bk]").forEach(el => el.onchange = () => {
      XP.doc.bodies = XP.doc.bodies || {};
      const b = XP.doc.bodies[cid] = XP.doc.bodies[cid] || {};
      const v = el.value;
      if (el.dataset.bk === "size") { const x = fnum(v); if (isFinite(x) && x > 0) b.size = x; else delete b.size; }
      else if (v) b[el.dataset.bk] = v; else delete b[el.dataset.bk];
      changed(); renderModel(); draw();
    });
    tr.onclick = e => { if (e.target.closest("select, input")) return; XP.sel = { comp: cid }; renderModel(); draw(); };
  });
  box.querySelectorAll("tr[data-shell]").forEach(tr => {
    const key = tr.dataset.shell;
    tr.querySelectorAll("[data-hk]").forEach(el => el.onchange = () => {
      XP.doc.shells = XP.doc.shells || {};
      const b = XP.doc.shells[key] = XP.doc.shells[key] || {};
      const k = el.dataset.hk, v = el.value;
      if (k === "t" || k === "size") { const x = fnum(v); if (isFinite(x) && x > 0) b[k] = x; else delete b[k]; }
      else if (v && !(k === "mode" && v === "shell") && !(k === "offset" && v === "mid")) b[k] = v; else delete b[k];
      if (!Object.keys(b).length) delete XP.doc.shells[key];
      changed(); renderModel(); draw();
    });
  });
}
/** Mesh settings. */
function meshHtml() {
  let h = "";
  const m = XP.doc.mesh || {};
  h += `<div class="row wrap">` +
    `<label class="inline xp-f">Element size (mm)<input type="text" data-mesh="size" value="${esc(m.size || "")}" placeholder="auto" style="width:60px"></label>` +
    `<label class="inline xp-f">Minimum size (mm)<input type="text" data-mesh="size_min" value="${esc(m.size_min || "")}" placeholder="auto" style="width:60px"></label>` +
    `<label class="inline xp-f">Strategy<select data-mesh="strategy">${optList(MESH_STRATEGIES, m.strategy || "tet")}</select></label>` +
    `<label class="inline xp-f">Tetrahedra<select data-mesh="tet_type">${optList([["C3D4", "C3D4 (first order)"], ["C3D10", "C3D10 (second order)"]], m.tet_type || "C3D4")}</select></label>` +
    `<label class="inline xp-f">Hexahedra<select data-mesh="hex_type">${optList([["C3D8R", "C3D8R (reduced integration)"], ["C3D8", "C3D8 (full integration)"]], m.hex_type || "C3D8R")}</select></label>` +
    `<label class="inline xp-f">Elements per 360 deg<input type="text" data-mesh="curvature" value="${esc(m.curvature === undefined ? "" : m.curvature)}" placeholder="12" style="width:40px"></label>` +
    `<label class="inline xp-f">Shell elements<select data-mesh="shell_type">${optList([["S4R", "S4R"], ["S4", "S4"], ["S3", "S3 (triangles)"]], m.shell_type || "S4R")}</select></label>` +
    `<label class="inline xp-f">Shell mesh<select data-mesh="shell_algorithm">${optList([["quasi", "Quasi-structured quadrangles"], ["frontal", "Frontal-Delaunay for quadrangles"], ["delaunay", "Delaunay, recombined"], ["tri", "Triangles only"]], m.shell_algorithm || "quasi")}</select></label>` +
    `<label class="check inline" title="Structured quadrangles on axis-aligned rectangles of the shells (step2shell)"><input type="checkbox" data-xpm="shstruct"${m.shell_structured === false ? "" : " checked"}> Structured quadrangles</label>` +
    `<label class="inline xp-f" title="Lowest number of elements between two break coordinates of the structured mesh">Min divisions per interval<input type="text" data-mesh="shell_min_div" value="${esc(m.shell_min_div || "")}" placeholder="1" style="width:36px"></label>` +
    `<label class="inline xp-f">Section sizes<select data-mesh="shell_size_mode">${optList([["local", "local, free transition"], ["grid", "along the grid, all structured"]], m.shell_size_mode || "local")}</select></label>` +
    `<label class="inline xp-f" title="Tolerance of the general fuse of the shells (mm). 0: exact">Fuzzy (mm)<input type="text" data-mesh="fuzzy" value="${esc(m.fuzzy || "")}" placeholder="0" style="width:46px"></label>` +
    `<label class="check inline"><input type="checkbox" data-xpm="bonded"${XP.doc.bonded !== false ? " checked" : ""}> Bonded: touching deformable bodies share nodes</label></div>`;
  return h;
}
function bindMesh(box) {
  box.querySelectorAll("[data-mesh]").forEach(el => el.onchange = () => {
    const k = el.dataset.mesh, v = el.value.trim();
    XP.doc.mesh = XP.doc.mesh || {};
    if (["size", "size_min", "curvature", "fuzzy", "shell_min_div"].includes(k)) { const x = fnum(v); if (v !== "" && isFinite(x)) XP.doc.mesh[k] = k === "shell_min_div" ? Math.max(1, Math.round(x)) : x; else delete XP.doc.mesh[k]; }
    else XP.doc.mesh[k] = v;
    changed(); renderModel();
  });
  const bo = box.querySelector("[data-xpm=bonded]"), st = box.querySelector("[data-xpm=shstruct]");
  if (bo) bo.onchange = () => { XP.doc.bonded = bo.checked; changed(); renderModel(); };
  if (st) st.onchange = () => { XP.doc.mesh = XP.doc.mesh || {}; if (st.checked) delete XP.doc.mesh.shell_structured; else XP.doc.mesh.shell_structured = false; changed(); renderModel(); };
}
/** Supports table. */
function supportsHtml() {
  let h = "";
  h += ((XP.doc.supports || []).length ? `<table class="fa-tbl xp-sups"><tr><th>Name</th><th>Face or edge</th><th>Preset</th>${DOF6.map(n => `<th>${n}</th>`).join("")}<th></th></tr>` +
    XP.doc.supports.map(s => { const dofs = (s.dofs || [1, 1, 1]).concat([0, 0, 0]).slice(0, 6); const pre = (SUP_PRESETS.find(([v]) => v && PRESET_DOFS[v].every((x, i) => x === dofs[i])) || [""])[0];
      return `<tr data-sup="${esc(s.id)}"${XP.sel && XP.sel.sup === s.id ? ' class="sel"' : ""}><td><input type="text" data-sk="name" value="${esc(s.name)}" style="width:80px"></td><td class="xp-face">${esc(faceText(s.target))}</td>` +
      `<td><select data-spre>${optList(SUP_PRESETS, pre)}</select></td>` +
      DOF6.map((n, i) => `<td><input type="checkbox" data-sd="${i}"${dofs[i] ? " checked" : ""}></td>`).join("") +
      `<td><button type="button" class="small" data-spick="${esc(s.id)}" title="Replace the target with the selection (or select, then Done)">Pick</button><button type="button" class="small" data-sshow="${esc(s.id)}" title="Select the target in the view">Show</button><button type="button" class="small" data-sdel="${esc(s.id)}" title="Delete">×</button></td></tr>`; }).join("") + `</table>` +
      `<p class="hint">The checked components of the nodes of the face or edge are held (*BOUNDARY); rx, ry, rz act on the shell nodes only.</p>`
    : `<p class="hint">Support in the toolbar: the selected faces, edges, bodies or reference point, or select them and press Done. The checked components of their nodes are held (*BOUNDARY).</p>`);
  return h;
}
function bindSupports(box) {
  box.querySelectorAll("tr[data-sup]").forEach(tr => {
    const s = XP.doc.supports.find(x => x.id === tr.dataset.sup);
    tr.querySelector("[data-sk=name]").onchange = e => { s.name = e.target.value; changed(); };
    tr.querySelectorAll("[data-sd]").forEach(el => el.onchange = () => { s.dofs = (s.dofs || [1, 1, 1]).concat([0, 0, 0]).slice(0, 6); s.dofs[+el.dataset.sd] = el.checked ? 1 : 0; changed(); renderModel(); });
    tr.querySelector("[data-spre]").onchange = e => { if (e.target.value) { s.dofs = PRESET_DOFS[e.target.value].slice(); changed(); renderModel(); } };
    tr.onclick = e => { if (e.target.closest("input, button")) return; XP.sel = { sup: s.id }; renderModel(); draw(); };
  });
  box.querySelectorAll("[data-sdel]").forEach(b => b.onclick = () => { XP.doc.supports = XP.doc.supports.filter(x => x.id !== b.dataset.sdel); changed(); renderModel(); draw(); });
  box.querySelectorAll("[data-sshow]").forEach(b => b.onclick = () => VS.show(SH, (XP.doc.supports.find(x => x.id === b.dataset.sshow) || {}).target));
  box.querySelectorAll("[data-spick]").forEach(b => b.onclick = () => {
    const s = XP.doc.supports.find(x => x.id === b.dataset.spick);
    VS.collect(SH, { text: "Support " + s.name + ": faces, edges, bodies or a reference point", types: ["faces", "edges", "bodies", "points"],
                     cb: it => { const r = VS.targetOf(it); if (r.error) return r.error; s.target = r.target; XP.sel = { sup: s.id }; changed(); } });
  });
}
/** Velocities (model_inp.py "velocities"): initial (*INITIAL CONDITIONS, inp2rad /INIVEL/TRA) on all nodes of a body,
 *  reference point (with its rigid coupling) or node set; imposed (*BOUNDARY TYPE=VELOCITY with an *AMPLITUDE ramp,
 *  inp2rad /IMPVEL) on the main node of a rigid body or rigidly coupled reference point, else on all nodes. */
function isRigidBody(id) {
  if (id.startsWith("sec:")) return ((XP.doc.sections || []).find(x => "sec:" + x.id === id) || {}).mode === "rigid";
  if (id.includes(":")) return ((XP.doc.shells || {})[id] || {}).mode === "rigid";
  return ((XP.doc.bodies || {})[id] || {}).role === "rigid";
}
function velTargets() {
  return SM.bodyList(SH).map(([id, t]) => ["b:" + id, t + (isRigidBody(id) ? " (rigid)" : "")])
    .concat((XP.doc.points || []).map(p => ["p:" + p.id, "reference point " + p.name]))
    .concat((XP.doc.nsets || []).map(n => ["n:" + n.id, "node set " + n.name]));
}
const velKey = t => !t ? "" : t.body !== undefined ? "b:" + t.body : t.point !== undefined ? "p:" + t.point : t.nset !== undefined ? "n:" + t.nset : "";
function renderVelocities(box) {
  if (!box) return;
  const d = XP.doc;
  d.velocities = d.velocities || [];
  const tg = velTargets();
  const v3 = (k, a, unit) => `<span class="rp-v3">${[0, 1, 2].map(i => `<input type="text" class="numf" data-vv="${k}" data-i="${i}" value="${esc(fmt((a || [0, 0, 0])[i] || 0, 8))}" style="width:64px">`).join("")}</span> ${unit}`;
  let h = `<div class="buttons sm-tools"><button type="button" class="small" data-va="initial">Add initial velocity</button><button type="button" class="small" data-va="imposed">Add imposed velocity</button></div>`;
  h += d.velocities.map(v => {
    const imp = v.kind === "imposed", f = (v.dofs || [1, 1, 1, 0, 0, 0]).concat([0, 0, 0, 0, 0, 0]).slice(0, 6);
    return `<div class="fa-props rp-props xp-vel" data-vel="${esc(v.id)}"><div class="rp-slot"><input type="text" data-vk="name" value="${esc(v.name)}" style="width:110px">` +
      `<select data-vk="kind">${optList([["initial", "initial (/INIVEL)"], ["imposed", "imposed (/IMPVEL)"]], v.kind || "initial")}</select>` +
      `<button type="button" class="small" data-vdel="${esc(v.id)}" title="Delete">&#10005;</button></div>` +
      `<div class="rp-slot">Target <select data-vk="target"><option value="">(choose)</option>${optList(tg, velKey(v.target))}</select></div>` +
      `<div class="rp-slot">vx vy vz ${v3("v", v.v, "mm/s")}</div>` +
      (imp ? `<div class="rp-slot">wx wy wz ${v3("w", v.w, "rad/s")}</div><div class="rp-slot">Components ${DOF6.map((n, i) => `<label class="check inline"><input type="checkbox" data-vf="${i}"${f[i] ? " checked" : ""}> ${n}</label>`).join("")}</div>` +
        `<div class="rp-slot"><label class="inline">Ramp (s)<input type="text" class="numf" data-vk="ramp" value="${esc(v.ramp || 0)}" style="width:64px"></label> 0 to the value in the ramp time, then constant; a component at 0 is held</div>` : "") + `</div>`;
  }).join("");
  if (!d.velocities.length) h += `<p class="hint">Initial velocity of all nodes of a body, reference point or node set (a rigid body: its nodes and its reference node); imposed velocity of the main node of a rigid body or rigidly coupled reference point, else of all nodes. Not together with a Build loading that drives the same rigid body.</p>`;
  box.innerHTML = h;
  box.querySelectorAll("[data-va]").forEach(b => b.onclick = () => {
    const imp = b.dataset.va === "imposed", t0 = tg.find(([k]) => k.startsWith("b:") && isRigidBody(k.slice(2))) || tg[0];
    const t = t0 ? (t0[0][0] === "b" ? { body: t0[0].slice(2) } : t0[0][0] === "p" ? { point: t0[0].slice(2) } : { nset: t0[0].slice(2) }) : null;
    d.velocities.push(Object.assign({ id: "v" + (d.next++), name: (imp ? "Imposed " : "Initial ") + (d.velocities.length + 1), kind: b.dataset.va, target: t, v: [0, 0, -1000] },
      imp ? { w: [0, 0, 0], dofs: [1, 1, 1, 0, 0, 0], ramp: 0 } : {}));
    changed(); renderModel(); draw();
  });
  box.querySelectorAll("[data-vdel]").forEach(b => b.onclick = () => { d.velocities = d.velocities.filter(x => x.id !== b.dataset.vdel); changed(); renderModel(); draw(); });
  box.querySelectorAll("[data-vel]").forEach(el => {
    const v = d.velocities.find(x => x.id === el.dataset.vel);
    el.querySelectorAll("[data-vk]").forEach(inp => inp.onchange = () => {
      const k = inp.dataset.vk, val = inp.value;
      if (k === "name") v.name = val.trim() || v.name;
      else if (k === "kind") { v.kind = val; if (val === "imposed") { v.w = v.w || [0, 0, 0]; v.dofs = v.dofs || [1, 1, 1, 0, 0, 0]; v.ramp = v.ramp || 0; } }
      else if (k === "target") v.target = !val ? null : val[0] === "b" ? { body: val.slice(2) } : val[0] === "p" ? { point: val.slice(2) } : { nset: val.slice(2) };
      else if (k === "ramp") { const x = fnum(val); v.ramp = isFinite(x) && x > 0 ? x : 0; }
      changed(); renderModel(); draw();
    });
    el.querySelectorAll("[data-vv]").forEach(inp => inp.onchange = () => {
      const k = inp.dataset.vv, a = [0, 1, 2].map(i => fnum(el.querySelector(`[data-vv="${k}"][data-i="${i}"]`).value));
      if (a.every(isFinite)) v[k] = a;
      changed(); draw();
    });
    el.querySelectorAll("[data-vf]").forEach(inp => inp.onchange = () => { v.dofs = [...el.querySelectorAll("[data-vf]")].map(x => x.checked ? 1 : 0); changed(); });
  });
}
/** Status bar (top of the tab): the inputs of the deck build. state "ok" (green), "warn" (amber), "bad" (red), "none"
 *  (grey, optional and empty). */
function statusItems() {
  const d = XP.doc, src = d.source || {}, out = [];
  const add = (key, label, state, text, title) => out.push({ key, label, state, text, title: title || "" });
  const n = a => (a || []).length;
  if (isShiny()) add("geo", "Geometry", src.name ? "ok" : "bad", src.name || "not chosen");
  else if (isDeck()) add("geo", "Geometry", "ok", "deck generator");
  else add("geo", "Geometry", src.inp ? "ok" : "bad", src.inp ? src.inp.split(/[\\/]/).pop() : "no .inp");
  const mats = d.materials || {};
  const badMat = Object.entries(mats).filter(([, m]) => !(m.library && XP.meta.library[m.library]) && !(m.E > 0 && m.nu >= 0 && m.nu < 0.5 && m.rho > 0)).map(([k]) => k);
  if (isModel()) {
    const used = new Set([d.default_material]);
    for (const b of Object.values(d.bodies || {})) if (b.material && b.role !== "off") used.add(b.material);
    for (const b of Object.values(d.shells || {})) if (b.material && b.mode !== "off") used.add(b.material);
    for (const b of d.sections || []) if (b.material && b.mode !== "off") used.add(b.material);
    const missing = [...used].filter(k => k && !mats[k]);
    add("mats", "Materials", badMat.length || missing.length || !Object.keys(mats).length ? "bad" : "ok",
        badMat.length ? "check " + badMat.join(", ") : missing.length ? "missing " + missing.join(", ") : Object.keys(mats).length + " defined");
  }
  if (isShiny()) {
    const comps = (XP.asm && XP.asm.components) || [];
    let def = 0, rig = 0;
    for (const c of comps) {
      const g = compOf(c.id), role = ((d.bodies || {})[c.id] || {}).role || "deformable";
      const solid = !(g && g.mesh) || g.mesh.triangles.length > 0 && (!g.mesh.face_body || g.mesh.face_body.some(v => v === null || v === undefined));
      if (solid) { if (role === "deformable") def++; else if (role === "rigid") rig++; }
      for (const sf of (g && g.surfaces) || []) { const md = ((d.shells || {})[c.id + ":" + sf.id] || {}).mode || "shell"; if (md === "shell") def++; else if (md === "rigid") rig++; }
    }
    add("bodies", "Bodies", def ? "ok" : "bad", `${def} deformable, ${rig} rigid`);
    if (n(d.sections)) add("sections", "Sections", "ok", n(d.sections) + "");
    const ms = XP.meshSummary, stale = meshStale();
    if (stale) add("mesh", "Mesh", "warn", "model changed since Mesh (Build writes the .inp again)");
    else add("mesh", "Mesh", ms || d.mesh_key ? "ok" : "bad", ms ? `${ms.nodes} nodes, ${ms.elements} elements` : d.mesh_key ? ".inp written" : "not written (Mesh)");
    const floor = String(S("test_mode") || "").includes("Rigid Floor");
    add("sups", "Supports", n(d.supports) ? "ok" : floor ? "ok" : "warn", n(d.supports) ? n(d.supports) + "" : floor ? "rigid floor" : "none");
  }
  if (isDeck()) add("sups", "Supports", "ok", "edge supports of the deck");
  const drv = S("rigid_vel_mode"), drvOn = drv && drv !== (XP.meta.rbv_modes || [])[3];
  const ld = [];
  if (n(d.velocities)) ld.push(n(d.velocities) + " velocit" + (n(d.velocities) > 1 ? "ies" : "y"));
  if (drvOn) ld.push("driver " + String(drv).replace(/ \(.*$/, ""));
  if (S("gravity")) ld.push("gravity");
  add("loads", "Loading", n(d.velocities) || drvOn ? "ok" : S("gravity") ? "warn" : "bad", ld.join(", ") || "none");
  if (isShiny()) {
    const ms = meshStale() ? null : XP.meshSummary, rm = ms && ms.rigid_mass;
    const anyRigid = Object.values(d.bodies || {}).some(b => b.role === "rigid") || Object.values(d.shells || {}).some(b => b.mode === "rigid") ||
      (d.sections || []).some(b => b.mode === "rigid");
    if (rm && rm.length) {
      const low = rm.filter(r => r.shell && !(r.added_kg > 0));
      add("masses", "Mass", low.length ? "warn" : "ok",
          rm.map(r => `${r.name} ${fmt(r.kg, 4)} kg` + (r.added_kg > 0 ? ` (${fmt(r.added_kg, 4)} kg added)` : r.shell ? " (shell only, no added mass)" : "")).join(", ") +
          (n(d.masses) ? "" : "; no Masses"));
    } else if (ms && ms.total_kg !== undefined) add("masses", "Mass", "ok", `model ${fmt(ms.total_kg, 4)} kg` + (n(d.masses) ? `, ${n(d.masses)} added` : ""));
    else add("masses", "Mass", anyRigid || n(d.masses) ? "warn" : "none", (n(d.masses) ? n(d.masses) + " added; " : "") + (anyRigid || n(d.masses) ? "Mesh to check" : "none"));
    const nc = n(d.points) + n(d.springs) + n(d.joints) + n(d.equations);
    add("rps", "Constraints", nc ? "ok" : "none", nc ? `${n(d.points)} RP, ${n(d.springs)} spring, ${n(d.joints)} joint, ${n(d.equations)} equation` : "none");
  }
  if (isShiny() && (S("init_state") || (d.initial_state || {}).analysis)) {
    const st = XP.initStatus;
    add("init", "Initial state", !S("init_state") ? "none" : st && st.summary ? "ok" : "bad",
        !S("init_state") ? "not used in Build" : st && st.summary ? `${st.summary.analysis}, max ${fmt(st.summary.umax, 3)} mm, ${fmt(st.summary.smax, 3)} MPa`
          : st && st.stale ? "model changed: Solve static (Build does it)" : "not solved (Build solves it)");
  }
  const rad = String(S("rad_target") || "");
  add("deck", "Deck", rad ? "ok" : "none", rad ? rad.split(/[\\/]/).pop() : "not built (Build)");
  return out;
}
const STATUS_TARGET = { geo: "#xp-model", sections: "#xp-h-sections", deck: "#xp-buildp" };
/** Pop-up of one input of the status bar: the same controls as in the panels, both kept up to date. */
const POPUPS = {
  mats: ["Materials", box => { box.innerHTML = materialsHtml(); bindMaterials(box); }],
  bodies: ["Bodies", box => { box.innerHTML = bodiesHtml(); bindBodies(box); }],
  sections: ["Sections", box => SM.renderSections(SH, box)],
  mesh: ["Mesh", box => {
    box.innerHTML = meshHtml() + `<div class="row"><button type="button" data-popmesh="1" class="primary">Mesh</button></div>` +
      (XP.meshSummary ? summaryHtml(XP.meshSummary) : `<p class="hint">Mesh meshes the bodies and shells, writes the model .inp and shows the mesh.</p>`);
    bindMesh(box);
    box.querySelector("[data-popmesh]").onclick = () => writeInp();
  }],
  sups: ["Supports", box => {
    box.innerHTML = supportsHtml() + `<div class="row"><button type="button" data-popsup="1">Add support</button></div>`;
    bindSupports(box);
    box.querySelector("[data-popsup]").onclick = () => addSupport();
  }],
  loads: ["Loading", box => {
    const M = XP.meta, rv = S("rigid_vel_mode");
    box.innerHTML = `<h3 class="xp-h">Velocities</h3><div data-popv="1"></div><h3 class="xp-h">Build loading</h3><div class="row wrap">` +
      `${selS("rigid_vel_mode", "Driver", M.rbv_modes.includes(rv) ? M.rbv_modes : [...M.rbv_modes, rv])}${rv === M.rbv_modes[0] ? inS("rigid_vel", "Vx Vy Vz [mm/s]", 110) : ""}${chkS("gravity", "Gravity")}</div>` +
      `<p class="hint">${esc(M.rbv_hint[rv] || "")}</p>`;
    renderVelocities(box.querySelector("[data-popv]"));
    bindFields(box, () => { renderBuild(); renderPopup(); });
  }],
  masses: ["Masses", box => renderMasses(box)],
  init: ["Initial state (static)", box => renderInit(box)],
  rps: ["Constraints", box => {
    box.innerHTML = ["Reference points", "Springs", "Joints", "Equations"].map((t, i) => `<h3 class="xp-h">${t}</h3><div data-popc="${i}"></div>`).join("");
    const b = i => box.querySelector(`[data-popc="${i}"]`);
    RP.renderPoints(RH, b(0)); RP.renderSprings(RH, b(1)); RP.renderJoints(RH, b(2)); RP.renderEquations(RH, b(3));
  }],
};
function openPopup(key) {
  XP.popup = key;
  let el = $("#xp-pop");
  if (!el) {
    el = document.createElement("div");
    el.id = "xp-pop";
    el.className = "xp-pop";
    el.innerHTML = `<div class="xp-pop-head"><b></b><button type="button" class="small" data-popclose="1" title="Close (Esc)">&#10005;</button></div><div class="xp-pop-body"></div>`;
    $("#tab-xp").appendChild(el);
    el.querySelector("[data-popclose]").onclick = () => { closePopup(); renderStatusBar(); };
    const head = el.querySelector(".xp-pop-head");                 // moved by its title bar
    head.onpointerdown = e => {
      if (e.target.closest("button")) return;
      const r = el.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
      const mv = ev => { el.style.left = Math.max(0, ev.clientX - dx) + "px"; el.style.top = Math.max(0, ev.clientY - dy) + "px"; };
      const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); };
      window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
    };
    const bar = $("#xp-statusbar").getBoundingClientRect(), pan = $("#xp-panel").getBoundingClientRect();
    el.style.left = Math.max(8, Math.min(pan.left, window.innerWidth - 576)) + "px";   // over the panel column, the view stays free for picks
    el.style.top = (bar.bottom + 6) + "px";
  }
  el.hidden = false;
  renderPopup();
}
function closePopup() { XP.popup = null; const el = $("#xp-pop"); if (el) el.hidden = true; }
function renderPopup() {
  const el = $("#xp-pop");
  if (!el || !XP.popup || !XP.doc) return;
  const p = POPUPS[XP.popup];
  if (!p || !isShiny()) { closePopup(); return; }
  el.querySelector(".xp-pop-head b").textContent = p[0];
  const body = el.querySelector(".xp-pop-body"), top = body.scrollTop;
  p[1](body);
  if (XP.pick) body.insertAdjacentHTML("beforeend", `<p class="fa-pick">${esc(XP.pick.text)}</p>`);
  body.scrollTop = top;
}
function renderStatusBar() {
  const bar = $("#xp-statusbar");
  if (!bar) return;
  if (!XP.doc || !XP.meta) { bar.innerHTML = ""; return; }
  bar.innerHTML = statusItems().map(it => `<button type="button" class="xp-st ${it.state}${XP.popup === it.key ? " open" : ""}" data-st="${esc(it.key)}" title="${esc(it.label + ": " + it.text)}"><b>${esc(it.label)}</b> ${esc(it.text)}</button>`).join("");
  bar.querySelectorAll("[data-st]").forEach(b => b.onclick = () => {
    const k = b.dataset.st;
    if (POPUPS[k] && isShiny()) { if (XP.popup === k) closePopup(); else openPopup(k); renderStatusBar(); return; }
    const el = (STATUS_TARGET[k] || "#xp-model").split(",").map(q => document.querySelector(q.trim())).find(x => x);
    if (!el) return;
    const det = el.closest("details");
    if (det) det.open = true;
    el.scrollIntoView({ block: "start", behavior: "smooth" });
  });
}
/** Initial state (initstate.py): static solve (CalculiX) of an Analysis document on the mesh of the Explicit model;
 *  the Build moves the nodes by its displacements and writes its stresses and plastic strains as initial state. */
function initText() {
  const st = XP.initStatus;
  if (!st) return "Not solved.";
  if (st.stale) return "The model .inp changed after the static solve: Solve static again.";
  const m = st.summary;
  return `${m.analysis}, ${m.time}, materials ${m.materials}${m.nonlinear ? " (nonlinear)" : ""}: ${m.nodes} nodes, ${m.solids} solid and ${m.shells} shell elements; ` +
    `max displacement ${fmt(m.umax, 4)} mm, max von Mises ${fmt(m.smax, 4)} MPa` + (m.pemax > 0 ? `, max plastic strain ${fmt(m.pemax, 4)}` : "") +
    ((m.warnings || []).length ? ". " + m.warnings.join("; ") : "");
}
function renderInit(box) {
  if (!box) return;
  const c = XP.doc.initial_state || {};
  if (!XP.feaList) { XP.feaList = []; api("/api/analysis/list").then(r => r.json()).then(j => { XP.feaList = j || []; renderModel(); }).catch(() => {}); }
  box.innerHTML = `<div class="row wrap"><label class="inline">Analysis<select data-ik="analysis"><option value="">(choose)</option>${optList(XP.feaList, c.analysis || "")}</select></label>` +
    `<label class="inline" title="Materials of the static solve: E, nu, rho of the Explicit materials (or their library entries); or the library hardening curves (nonlinear step, plastic strain)">Materials<select data-ik="materials">${optList([["elastic", "elastic (E, nu, rho)"], ["explicit", "as Explicit (library curves, nonlinear)"]], c.materials || "elastic")}</select></label>` +
    `<button type="button" class="small" data-isolve="1">Solve static</button></div>` +
    `<div class="row wrap">${chkS("init_state", "Use in Build")}${chkS("init_geometry", "Deformed geometry")}${chkS("init_stress", "Stresses")}${chkS("init_peeq", "Plastic strain")}</div>` +
    `<p class="hint xp-init-st">${esc(initText())}</p>` +
    `<p class="hint">The static solve runs on the mesh of the last Mesh (S4R as S4, C3D8R as C3D8I) with the bodies and materials of this model (rigid bodies left out) and the supports, loads, fasteners, constraints, contacts and step settings of the Analysis document. Build: /NODE moved by the displacements, /INIBRI/STRS_FGLO (solids) and /INISHE/STRS_F/GLOB (shells, 5 points through the thickness).</p>`;
  box.querySelectorAll("[data-ik]").forEach(el => el.onchange = () => {
    XP.doc.initial_state = Object.assign({}, XP.doc.initial_state || {}, { [el.dataset.ik]: el.value });
    changed();
  });
  box.querySelector("[data-isolve]").onclick = () => solveInit();
  bindFields(box, () => renderStatusBar());
}
async function refreshInit() {
  if (!XP.doc || !isShiny()) { XP.initStatus = null; return; }
  try { XP.initStatus = (await (await api("/api/explicit/initial_state?name=" + encodeURIComponent(XP.doc.name))).json()).state; }
  catch (e) { XP.initStatus = null; }
  document.querySelectorAll(".xp-init-st").forEach(el => el.textContent = initText());
  renderStatusBar();
}
async function solveInit() {
  const c = XP.doc.initial_state || {};
  if (!c.analysis) { status("Choose the Analysis document of the static solve", true); return false; }
  if (!XP.doc.mesh_key || meshStale()) { if (!(await writeInp())) return false; }
  busy(true, "Static solve ...");
  try {
    const j = await pollJob((await (await postJSON("/api/explicit/initial_state", req())).json()).job, "Static solve");
    if (j.state === "error") throw new Error(j.error);
    status(`Static solve of ${c.analysis}: max displacement ${fmt(j.result.umax, 4)} mm, max von Mises ${fmt(j.result.smax, 4)} MPa`);
    return true;
  } catch (e) { showErr(e); return false; } finally { busy(false); await refreshInit(); }
}
/** Masses (model_inp.py "masses", /ADMAS type 5): point mass at a reference point; distributed mass on faces (total kg
 *  or kg/m^2), on a body or on a node set (total kg). */
function renderMasses(box) {
  if (!box) return;
  const d = XP.doc;
  d.masses = d.masses || [];
  const pts = (d.points || []).map(p => [p.id, p.name]);
  const dt = [["f:", "faces (picked)"]].concat(SM.bodyList(SH).map(([id, t]) => ["b:" + id, t + (isRigidBody(id) ? " (rigid)" : "")]))
    .concat((d.nsets || []).map(n => ["n:" + n.id, "node set " + n.name]));
  const tkey = t => !t ? "" : t.faces ? "f:" : t.body !== undefined ? "b:" + t.body : t.nset !== undefined ? "n:" + t.nset : "";
  let h = `<div class="buttons sm-tools"><button type="button" class="small" data-ma="point">Add point mass</button><button type="button" class="small" data-ma="distributed">Add distributed mass</button></div>`;
  h += d.masses.map(m => {
    const pt = m.kind === "point", faces = !pt && m.target && m.target.faces;
    const area = faces && m.mode === "area";
    return `<div class="fa-props rp-props xp-mass" data-mass="${esc(m.id)}"><div class="rp-slot"><input type="text" data-mk2="name" value="${esc(m.name)}" style="width:110px">` +
      `<select data-mk2="kind">${optList([["point", "point mass"], ["distributed", "distributed mass"]], m.kind || "point")}</select>` +
      `<button type="button" class="small" data-mdel2="${esc(m.id)}" title="Delete">&#10005;</button></div>` +
      (pt ? `<div class="rp-slot">Reference point <select data-mk2="point"><option value="">(choose)</option>${optList(pts, m.target && m.target.point)}</select></div>`
        : `<div class="rp-slot">Target <select data-mk2="target"><option value="">(choose)</option>${optList(dt, tkey(m.target))}</select></div>` +
          (faces ? `<div class="rp-slot"><span class="hint">${m.target.faces.length ? m.target.faces.map(faceText).map(esc).join("; ") : "no faces"}</span> ` +
            `<button type="button" class="small" data-mface="${esc(m.id)}" title="Add the selected faces (or select, then Done)">Add faces</button><button type="button" class="small" data-mclear="${esc(m.id)}">Clear</button></div>` +
            `<div class="rp-slot"><select data-mk2="mode">${optList([["total", "total mass"], ["area", "mass per area"]], m.mode || "total")}</select></div>` : "")) +
      `<div class="rp-slot"><label class="inline">${area ? "Mass per area" : "Mass"}<input type="text" class="numf" data-mk2="m" value="${esc(m.m === undefined ? "" : m.m)}" style="width:70px"></label> ${area ? "kg/m^2" : "kg"}</div></div>`;
  }).join("");
  if (!d.masses.length) h += `<p class="hint">Point mass: on the node of a reference point (a point coupled to a rigid body adds to the rigid body). Distributed mass: on the nodes of faces (area weights), of a body (element volume or area) or of a node set (equal shares). /ADMAS cards; mass only, no rotational inertia.</p>`;
  box.innerHTML = h;
  box.querySelectorAll("[data-ma]").forEach(b => b.onclick = () => {
    const pt = b.dataset.ma === "point";
    d.masses.push({ id: "m" + (d.next++), name: (pt ? "Point mass " : "Mass ") + (d.masses.length + 1), kind: b.dataset.ma,
                    target: pt ? (pts[0] ? { point: pts[0][0] } : null) : { faces: [] }, m: 1, mode: "total" });
    changed(); renderModel(); draw();
  });
  box.querySelectorAll("[data-mdel2]").forEach(b => b.onclick = () => { d.masses = d.masses.filter(x => x.id !== b.dataset.mdel2); changed(); renderModel(); draw(); });
  box.querySelectorAll("[data-mface]").forEach(b => b.onclick = () => {
    const m = d.masses.find(x => x.id === b.dataset.mface);
    VS.collect(SH, { text: m.name + ": faces (bodies: their faces)", types: ["faces", "bodies"], expand: true, cb: it => {
      m.target = m.target && m.target.faces ? m.target : { faces: [] };
      for (const ref of it.faces) if (!m.target.faces.some(f => f.comp === ref.comp && f.face === ref.face)) m.target.faces.push({ comp: ref.comp, face: ref.face });
      changed();
    } });
  });
  box.querySelectorAll("[data-mclear]").forEach(b => b.onclick = () => { const m = d.masses.find(x => x.id === b.dataset.mclear); m.target = { faces: [] }; changed(); renderModel(); draw(); });
  box.querySelectorAll("[data-mass]").forEach(el => {
    const m = d.masses.find(x => x.id === el.dataset.mass);
    el.querySelectorAll("[data-mk2]").forEach(inp => inp.onchange = () => {
      const k = inp.dataset.mk2, val = inp.value;
      if (k === "name") m.name = val.trim() || m.name;
      else if (k === "kind") { m.kind = val; m.target = val === "point" ? (pts[0] ? { point: pts[0][0] } : null) : { faces: [] }; }
      else if (k === "point") m.target = val ? { point: val } : null;
      else if (k === "target") { m.target = !val ? null : val === "f:" ? { faces: [] } : val[0] === "b" ? { body: val.slice(2) } : { nset: val.slice(2) }; if (!m.target || !m.target.faces) m.mode = "total"; }
      else if (k === "mode") m.mode = val;
      else if (k === "m") { const x = fnum(val); if (isFinite(x) && x > 0) m.m = x; else { inp.value = m.m; return; } }
      changed(); renderModel(); draw();
    });
  });
}
/** Material drop-downs: model materials with their library entry or values, library entries (adds a material). */
function libraryNames() { return Object.keys((XP.meta && XP.meta.library) || {}); }
function matOpts(cur) { return MS.matOptions(XP.doc, cur || "", libraryNames()); }
function addLibraryMaterial(entry) {
  const L = XP.meta.library[entry];
  if (!L) return null;
  const n = MS.nameForLibrary(XP.doc, entry);
  XP.doc.materials = XP.doc.materials || {};
  XP.doc.materials[n] = { library: entry, E: L.E, nu: L.nu, rho: Math.round(L.rho * 1000) / 1000 };
  return n;
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
    }).join("") + `</table><div class="row"><button type="button" data-xpmat="add" class="small">Add material</button>` +
    `<label class="inline">Default<select data-xpmat="def" class="xp-matsel">${MS.matOptions(XP.doc, XP.doc.default_material, libraryNames(), false)}</select></label></div>` +
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
        for (const b of Object.values(XP.doc.shells || {})) if (b.material === n) b.material = nn;
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
  box.querySelector("[data-xpmat=add]").onclick = () => {
    let k = 1; while (XP.doc.materials["Material" + k]) k++;
    XP.doc.materials["Material" + k] = { library: "", E: 210000, nu: 0.3, rho: 7850 };
    changed(); renderModel();
  };
  const md = box.querySelector("[data-xpmat=def]");
  md.onchange = () => { XP.doc.default_material = md.value; changed(); renderModel(); };
}
const MESH_STRATEGIES = [["tet", "Tetrahedra (free)"], ["hex", "Hexahedra, structured (block cells)"], ["hexsub", "Hexahedra by subdivision"]];
function summaryHtml(s) {
  let h = `<p class="hint">${s.nodes} nodes, ${s.elements} elements` + (s.supports !== undefined ? `, ${s.supports} support condition(s)` : "") + `</p>`;
  if (s.bodies) h += `<table class="fa-tbl"><tr><th>Body</th><th>Role</th><th>ELSET</th><th>Material</th><th>Elements</th><th>Ref node</th></tr>` +
    s.bodies.map(b => `<tr><td>${esc(b.name)}</td><td>${esc(b.role)}</td><td>${esc(b.elset)}</td><td>${esc(b.material)}</td><td>${b.elements} ${esc((b.types || []).join(" "))}</td><td>${b.ref_node || ""}</td></tr>`).join("") + `</table>`;
  if (s.parts) h += `<table class="fa-tbl"><tr><th>ELSET</th><th>Type</th></tr>` + s.parts.map(p => `<tr><td>${esc(p.elset)}</td><td>${esc(p.type)}</td></tr>`).join("") + `</table>`;
  const r = s.shell;
  if (r) h += `<p class="hint xp-shellrep">Shells: ${r.structured} of ${r.faces} face(s) structured, ${r.free} free; element quality (gamma) min ${fmt(r.min_quality, 3)}, mean ${fmt(r.mean_quality, 3)}, below 0.3: ${r.below_03}; element edges ${fmt(r.min_edge, 4)} mm to ${fmt(r.max_edge, 4)} mm</p>`;
  if (s.nsets && s.nsets.length) h += `<p class="hint">Node sets: ${s.nsets.map(n => esc(n.name) + " " + n.nodes).join(", ")}</p>`;
  if (s.velocities && s.velocities.length) h += `<p class="hint">Velocities: ${s.velocities.map(v => esc(v.name) + " (" + esc(v.kind) + ")").join(", ")}</p>`;
  if (s.masses && s.masses.length) h += `<p class="hint">Masses (/ADMAS): ${s.masses.map(m => `${esc(m.name)} ${fmt(m.kg, 5)} kg on ${m.nodes} node(s)`).join(", ")}</p>`;
  if (s.total_kg !== undefined) h += `<p class="hint">Mass: model ${fmt(s.total_kg, 5)} kg` +
    (s.rigid_mass || []).map(r => `; rigid body ${esc(r.name)} ${fmt(r.kg, 5)} kg${r.added_kg > 0 ? ` (${fmt(r.added_kg, 5)} kg added)` : ""}`).join("") + `</p>`;
  if (s.points && s.points.length) h += `<p class="hint">Reference points: ${s.points.map(p => `${esc(p.name)} node ${p.node} (${esc(p.coupling)}${p.nodes ? ", " + p.nodes + " nodes" : ""})`).join(", ")}` +
    (s.springs || s.equations ? `; ${s.springs || 0} spring(s), ${s.equations || 0} equation(s) (/MPC)` : "") + `</p>`;
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
/** Inputs of the model .inp (ShinyCAD geometry): a change after Mesh makes the .inp out of date. */
function modelKey() {
  const d = XP.doc;
  return JSON.stringify([d.source, d.materials, d.default_material, d.mesh, d.bonded, d.bodies, d.shells, d.sections, d.nsets, d.supports,
                         d.points, d.springs, d.joints, d.equations, d.velocities, d.masses, XP.geoKey === undefined ? null : XP.geoKey]);
}
function meshStale() { return isShiny() && !!XP.doc.mesh_key && XP.doc.mesh_key !== modelKey(); }
async function writeInp() {
  if (!isModel()) { showInpMesh(); return false; }
  if (isShiny() && !(XP.doc.source || {}).name) { status("Choose the geometry first", true); return false; }
  busy(true, "Writing the model .inp ...");
  try {
    const j = await pollJob((await (await postJSON("/api/explicit/model", req())).json()).job, "Mesh");
    if (j.state === "error") throw new Error(j.error);
    XP.mesh = j.result.payload; XP.meshSummary = j.result.summary;
    if (isShiny()) { XP.doc.mesh_key = modelKey(); changed(); refreshInit(); }
    $("#xp-show").value = "mesh";
    if (XP.three) XP.three.zoomed = false;
    status("Model .inp written: " + j.result.inp);
    info(`${XP.meshSummary.nodes} nodes, ${XP.meshSummary.elements} elements`);
    renderModel(); renderBuild(); draw();
    return true;
  } catch (e) { showErr(e); info(""); return false; } finally { busy(false); }
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
  VS.collect(SH, { text: "New support: faces, edges, bodies or a reference point", types: ["faces", "edges", "bodies", "points"], cb: it => {
    const r = VS.targetOf(it);
    if (r.error) return r.error;
    const id = "s" + (XP.doc.next++);
    XP.doc.supports.push({ id, name: "Support " + (XP.doc.supports.length + 1), target: r.target, dofs: [1, 1, 1] });
    XP.sel = { sup: id };
    changed();
  } });
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
    `<p class="hint">Writes &lt;name&gt;_deck.step (one named component per element set), &lt;name&gt;_deck_model.json and &lt;name&gt;_deck_properties.txt (locations, sections, thicknesses) to the step folder of the project, and the part &lt;name&gt;_deck with one Import surface feature per component.</p>` +
    (st ? `<p class="hint">${esc(st.step)}: ${esc(st.components.join(", "))}</p>` +
      (st.report ? `<p class="hint">Properties: ${esc(st.report)}</p>` : "") : "");
  h += XP.meshSummary ? deckSummaryHtml(XP.meshSummary) : `<p class="hint">Mesh meshes the deck and writes the model .inp.</p>`;
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
  (c.view || c.parts).forEach((p, k) => {                   // view: a top flange cuts the deck plate (deck.claimed)
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
  h += `<table class="fa-tbl xp-runs"><tr><th>Run</th><th>Builds</th><th>Decks</th><th title="PrePoMax version of the archived .inp">PMX</th><th></th></tr>` +
    `<tr data-run=""${!cur ? ' class="sel"' : ""}><td colspan="4">(no run: decks next to the .inp)</td><td></td></tr>` +
    XP.runs.map(r => `<tr data-run="${esc(r.path)}"${r.path === cur ? ' class="sel"' : ""}><td title="${esc(r.description + (r.notes ? " | " + r.notes : ""))}">${esc(r.name)}</td><td>${r.builds}</td><td>${r.decks.length}</td><td>${r.prepomax_version ? "v" + esc(r.prepomax_version) : ""}</td>` +
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
      if (b.dataset.rop === "settings") await restoreSettings({ path }, "the last build of " + path.split("/").pop());
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
  renderStatusBar();
  if (XP.popup === "loads") renderPopup();
  const M = XP.meta;
  const mode = S("analysis_mode");
  const spec = M.mode_spec[mode] || {};
  const rbvs = spec.rbv_values || M.rbv_modes;
  let h = `<div class="row">${selS("analysis_mode", "Analysis", M.analysis_modes)}<button type="button" class="small" id="xp-orc3set" title="Build settings of the ORC**3 configuration (%APPDATA%\\ORC3\\workspace_config.json); paths unchanged">Import ORC**3 settings</button></div><p class="hint">${esc(M.mode_help[mode] || "")}</p>`;
  const inp = isModel() ? "(model .inp of the document: Mesh)" : ((XP.doc.source || {}).inp || "(choose the .inp in Model)");
  h += `<p class="hint">Source .inp: ${esc(inp)}</p><div class="row">${chkS("downgrade_quad", "Downgrade 2nd-order → linear", "Quadratic elements of the source .inp to linear elements before inp2rad (inp_to_linear.py; nodes kept)")}</div>`;
  h += `<div class="row">${inSB("out_dir", "Output Dir", 240, "folder", "", "Folder of the build (a run folder of Runs, or any folder; empty: next to the .inp)")}</div>`;
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
  h += `<h3 class="xp-h">Failure</h3><div class="row wrap">${selS("fail_model", "Model", M.fail_models)}${helpBtn("Failure models", M.fail_doc, fm)}${inS("fail_strain", "Plastic fail strain", 50)}</div>`;
  if (fm === M.fail_models[1]) h += `<div class="row wrap">JC:${["jc_d1", "jc_d2", "jc_d3", "jc_d4", "jc_d5"].map((k, i) => inS(k, "D" + (i + 1), 44)).join("")}${inS("jc_eps0", "eps0", 40)}${inS("jc_ifail_sh", "Ifail_sh", 30)}</div>`;
  if (fm === M.fail_models[2]) h += `<div class="row wrap">TENS:${inS("ts_et1", "et1", 50)}${inS("ts_et2", "et2", 50)}${inS("ts_soften", "SoftBand", 40)}${inS("ts_sflag", "S_Flag", 30)}${inS("ts_failip", "FAILIP", 30)}</div>`;
  h += `<p class="hint">${esc(M.fail_hint[fm] || "")}</p>`;
  // options
  h += `<div class="row wrap">${chkS("gravity", "Gravity")}${selS("contact_mode", "Contact", M.contact_modes)}${helpBtn("General contact modes", M.contact_doc, S("contact_mode"))}${chkS("build_subdirs", "Subfolder per build")}</div><p class="hint">${esc(M.contact_hint[S("contact_mode")] || "")}</p>`;
  // loading
  const rv = S("rigid_vel_mode");
  h += `<h3 class="xp-h">Loading (rigid-body driver)</h3><div class="row wrap">${selS("rigid_vel_mode", "Driver", rbvs.includes(rv) ? rbvs : [...rbvs, rv])}${helpBtn("Rigid-body drivers (loading)", M.rbv_doc, rv)}`;
  if (rv === M.rbv_modes[0]) h += inS("rigid_vel", "Vx Vy Vz [mm/s]", 110);
  h += `</div>`;
  if (rv === M.rbv_modes[0]) h += `<div class="row xp-travel" id="xp-travel">${travelHtml()}</div>`;
  if (!hidden("target_rp")) h += `<div class="row">${inS("rigid_rp_target", "Target RP", 120)}<span class="hint">/RBODY name or id (blank = the single RBODY)</span></div>`;
  if (rv === M.rbv_modes[1] || rv === M.rbv_modes[2]) {
    h += `<div class="row wrap">${inS("lhu_peak", rv === M.rbv_modes[2] ? "Peak force" : "Peak disp", 56)}${selS("lhu_dir", "Dir", ["X", "Y", "Z"])}${inS("lhu_rampup", "Ramp up [s]", 44)}` +
      `${inS("lhu_hold", "Hold [s]", 44)}${inS("lhu_rampdn", "Ramp down [s]", 44)}${inS("lhu_settle", "Settle [s]", 44)}${selS("lhu_easing", "Ease", M.lhu_easings)}${inS("lhu_npramp", "Pts/ramp", 36)}</div>`;
  }
  if (!hidden("rigidify")) h += `<div class="row">${inS("rigid_part", "Rigid parts", 160, "PID or part name substring; comma between several (blank = off)")}<button type="button" class="small" data-listparts="1" title="Lists PID: name of the /PART cards of the Target .rad (or the newest deck in Output Dir) in the console">List Parts</button></div>`;
  h += `<p class="hint">${esc(M.rbv_hint[rv] || "")}</p>`;
  // concentrated mass (ORC**3 Inertia tab)
  if (!hidden("point_mass")) {
    h += `<h3 class="xp-h">Concentrated mass (unmeshed rigid body)</h3><div class="row">${inSB("point_mass_json", "Inertia payload (JSON)", 200, "open", "json", "inertia_builder / inertia_calc payload or primitives file (blank = off)")}</div>` +
      `<div class="row wrap"><button type="button" class="small" id="xp-in-verify">Reload / verify</button><button type="button" class="small" id="xp-in-builder" title="inertia_builder.py (Tools)">Open inertia builder</button>` +
      `<button type="button" class="small" id="xp-in-clear">Clear (disable)</button>${helpBtn("Concentrated mass: how this reaches the deck", M.inertia_doc)}</div>` +
      `<pre id="xp-inertia" class="xp-log xp-inertia"></pre><p class="hint">On Build the payload merges into the single /RBODY of the model (mass and inertia; the main node stays at the RP of the model).</p>`;
  }
  // ties
  const tm = S("tie_mode");
  const tdOn = tm === M.tie_modes[0] || tm === M.tie_modes[2];
  h += `<h3 class="xp-h">Ties (bonded connections)</h3><div class="row wrap">${selS("tie_mode", "Tie Mode", M.tie_modes)}${helpBtn("Tie modes (bonded connections)", M.tie_doc, tm)}` +
    `<label class="inline xp-f">${tm === M.tie_modes[0] ? "Fallback dist [mm]" : "Tie dist [mm]"}<input type="text" data-s="tie_dist" value="${esc(S("tie_dist"))}" style="width:50px"${tdOn ? "" : " disabled"}></label>` +
    `<button type="button" class="small" data-listparts="1" title="Lists PID: name of the /PART cards of the Target .rad (or the newest deck in Output Dir) in the console">List Parts</button></div>`;
  if (tm === M.tie_modes[1]) h += `<textarea data-s="tie_pairs" rows="3" style="width:100%" placeholder="secondary > master : distance">${esc(S("tie_pairs"))}</textarea>`;
  h += `<p class="hint">${esc(M.tie_hint[tm] || "")}</p>`;
  if (!hidden("advanced")) h += `<h3 class="xp-h">Advanced / niche options</h3><div class="row wrap">${chkS("align_norms", "Heal Normals")}${chkS("apply_vel_model", "Disp -> Velocity")}${chkS("purge_prev", "Purge older builds")}</div>`;
  const notes = hiddenActive();
  if (notes.length) h += `<p class="fa-pick">Hidden by the analysis type but active at build time: ${esc(notes.join("; "))}</p>`;
  h += `<div class="row"><button type="button" id="xp-build2" class="primary" title="BUILD RADIOSS DECK: inp2rad and the cards of these settings; decks into the run folder">Build deck</button></div>`;
  box.innerHTML = h;
  bindFields(box, k => {
    if (["analysis_mode", "fail_model", "tie_mode", "rigid_vel_mode", "test_mode", "contact_mode"].includes(k)) { renderBuild(); if (k === "analysis_mode") renderRivet(); }
    if (k === "point_mass_json") { renderBuild(); }
    if (k === "out_dir") { renderRuns(); renderSolve(); renderResultsJobs(); renderBuild(); }
    if ((k === "rigid_vel" || k === "tstop") && $("#xp-travel")) $("#xp-travel").innerHTML = travelHtml(), bindHelp($("#xp-travel"));
  });
  for (const k of ["rigid_vel", "tstop"]) {
    const el = box.querySelector(`[data-s="${k}"]`);
    if (el) el.oninput = () => { XP.doc.settings[k] = el.value; if ($("#xp-travel")) { $("#xp-travel").innerHTML = travelHtml(); bindHelp($("#xp-travel")); } };
  }
  box.querySelectorAll("tr[data-slot]").forEach(tr => tr.querySelectorAll("[data-sl]").forEach(el => el.onchange = () => {
    const sl = (S("mat_slots") || XP.meta.slots_default).map(x => x.slice());
    sl[+tr.dataset.slot][+el.dataset.sl] = el.value.trim();
    setS("mat_slots", sl);
  }));
  box.querySelectorAll("[data-sldel]").forEach(b => b.onclick = () => { const sl = (S("mat_slots") || XP.meta.slots_default).map(x => x.slice()); sl.splice(+b.dataset.sldel, 1); setS("mat_slots", sl); renderBuild(); });
  $("#xp-slot-add").onclick = () => { const sl = (S("mat_slots") || XP.meta.slots_default).map(x => x.slice()); sl.push([XP.meta.library_none, ""]); setS("mat_slots", sl); renderBuild(); };
  $("#xp-build2").onclick = build;
  $("#xp-mindt").onclick = suggestMinDt;
  $("#xp-orc3set").onclick = () => restoreSettings({ orc3: true }, "the ORC**3 configuration");
  box.querySelectorAll("[data-listparts]").forEach(b => b.onclick = () => postJSON("/api/explicit/list_parts", req()).then(() => { poll(); openSection("xp-sec-console"); }).catch(showErr));
  if ($("#xp-in-verify")) {
    $("#xp-in-verify").onclick = inertiaRefresh;
    $("#xp-in-builder").onclick = () => launchTool("inertia_builder", "");
    $("#xp-in-clear").onclick = () => { setS("point_mass_json", ""); renderBuild(); };
    inertiaRefresh();
  }
}
/** Travel table of the Explicit driver (ORC**3 _update_travel_table): time for TRAVEL_MM at |V|, against Tstop. */
function travelHtml() {
  const M = XP.meta;
  const raw = String(S("rigid_vel") || "").trim();
  const help = helpBtn("Travel table (distance vs time)", M.travel_doc);
  let err = null, v = [0, 0, 0];
  if (!raw) err = "enter Vx Vy Vz above to see it";
  else {
    const c = raw.replace(/,/g, " ").split(/\s+/).map(Number);
    if (c.some(x => !isFinite(x))) err = `'${raw}' is not readable as up to 3 numbers`;
    else { while (c.length < 3) c.push(0); v = c.slice(0, 3); }
  }
  const speed = Math.hypot(...v);
  if (!err && speed <= 0) err = "|V| is zero - the impactor never moves";
  if (err) return `<span class="xp-h0">Travel:</span> <span class="hint">${esc(err)}</span>${help}`;
  let tstop = parseFloat(String(S("tstop") || "").trim());
  if (!(tstop > 0)) tstop = null;
  const cap = tstop !== null ? `Time ${fmt(tstop, 4)} s covers ${fmt(speed * tstop, 4)} mm` : "Time (Tstop) not readable - no reach check";
  const cells = M.travel_mm.map(d => {
    const t = d / speed;
    return tstop !== null && t > tstop ? `<span class="xp-bad">${fmt(d, 4)} mm: ${fmt(t, 4)} s (NOT reached)</span>` : `<span>${fmt(d, 4)} mm: ${fmt(t, 4)} s</span>`;
  }).join(" · ");
  return `<span class="xp-h0">Travel:</span> <span class="hint">|V| = ${fmt(speed, 6)} mm/s (${v.map(x => fmt(x, 6)).join(", ")}) · ${esc(cap)}</span><br>${cells}${help}`;
}
async function inertiaRefresh() {
  const el = $("#xp-inertia");
  if (!el) return;
  try {
    const j = await (await postJSON("/api/explicit/inertia", { path: S("point_mass_json") || "" })).json();
    el.textContent = j.text;
    el.className = "xp-log xp-inertia xp-in-" + j.state;
  } catch (e) { el.textContent = String(e.message || e); }
}
/** Settings of the last build of a run ({path}) or of the ORC**3 configuration ({orc3: true}); paths unchanged. */
async function restoreSettings(body, what) {
  try {
    const j = await (await postJSON("/api/explicit/run/settings", body)).json();
    const skip = new Set(["project_dir", "out_dir", "inp_path", "rad_target", ...XP.meta.env_keys, "job_queue", "self_contact"]);
    for (const [k, v] of Object.entries(j.settings)) if (!skip.has(k) && (k in XP.meta.defaults || k === "mat_slots")) XP.doc.settings[k] = v;
    if (!j.settings.mat_slots && j.settings.mat1 !== undefined) XP.doc.settings.mat_slots = [1, 2, 3].map(i => [j.settings["mat" + i], j.settings["mat" + i + "_name"]]);
    changed(); renderBuild(); renderRivet();
    status("Settings of " + what + " restored (paths unchanged)" + (j.notes && j.notes.length ? "; " + j.notes.join("; ") : ""));
    poll();
  } catch (err) { showErr(err); }
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
  if (hidden("rigidify") && String(S("rigid_part") || "").trim()) out.push("Rigid parts " + S("rigid_part"));
  if (hidden("point_mass") && String(S("point_mass_json") || "").trim()) out.push("concentrated mass");
  if (hidden("target_rp") && String(S("rigid_rp_target") || "").trim()) out.push("Target RP " + S("rigid_rp_target"));
  if (hidden("advanced")) {
    if (S("purge_prev")) out.push("Purge older builds");
    if (!S("align_norms")) out.push("Heal Normals off");
    if (!S("apply_vel_model")) out.push("Disp -> Velocity off");
  }
  const spec = XP.meta.mode_spec[S("analysis_mode")] || {};
  if (spec.rbv_values && !spec.rbv_values.includes(S("rigid_vel_mode"))) out.push("Driver " + S("rigid_vel_mode"));
  return out;
}
async function build() {
  try {
    if (isShiny() && (!XP.doc.mesh_key || meshStale())) {
      status(XP.doc.mesh_key ? "The model changed since the last Mesh: writing the model .inp first" : "Writing the model .inp first");
      if (!(await writeInp())) return;
    }
    if (isShiny() && S("init_state")) {
      await refreshInit();
      if (!XP.initStatus || XP.initStatus.stale) { status("Use in Build: static solve first"); if (!(await solveInit())) return; }
    }
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
  let h = `<div class="row"><label class="inline" style="flex:1">Target .rad<input type="text" data-s="rad_target" value="${esc(tgt)}" style="flex:1;width:auto"></label><button type="button" class="small" data-browse-s="rad_target" data-kind="open" data-filter="rad" title="Browse for the starter deck (..._0000.rad)">…</button>` +
    (decks.length ? `<select id="xp-decks" title="Decks of the selected run"><option value="">decks…</option>${optList(decks.map(d => [d, d.split("/").pop()]), "")}</select>` : "") + `</div>`;
  h += `<div class="row wrap"><label class="inline xp-f">Env<select data-e="run_target">${optList([[XP.meta.local, "Local"], [XP.meta.remote, "Remote (Linux)"]], E("run_target"))}</select></label>` +
    `${inE("ssh_threads", "Threads", 30)}${chkE("stream_remote", "Stream remote output")}${chkS("plot_ke", "Plot KE")}${chkS("extract_strains", "Extract Strains")}${chkS("pv_images", "PV Images")}${chkS("vtk_convert", "Convert to VTK", "anim_to_vtk conversion of the animation files after the engine (ParaView, PV Images, Extract Strains). The 3D view reads the animation files directly.")}</div>`;
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
  h += `<details class="xp-hist"${XP.histOpen ? " open" : ""}><summary class="sk-h">Run history</summary><div class="row wrap"><button type="button" class="small" data-hop="load" title="Target .rad and Output Dir of the selected entry">Load Selected</button>` +
    `<button type="button" class="small" data-hop="open">Open folder</button><button type="button" class="small" data-hop="remove">Remove</button><button type="button" class="small" data-hop="clear">Clear</button></div><div id="xp-history"></div></details>`;
  box.innerHTML = h;
  box.querySelector(".xp-hist").ontoggle = e => { XP.histOpen = e.target.open; };
  bindFields(box, k => {
    if (k === "run_target") { envSwitch(); renderSolve(); }
    if (k === "rad_target") renderSolve();
  });
  box.querySelectorAll("[data-hop]").forEach(b => b.onclick = () => historyOp(b.dataset.hop));
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
/** Env changed: Target .rad and Output Dir remembered per Env (ORC**3 env_dirs). */
async function envSwitch() {
  const nw = E("run_target"), old = XP.lastEnv;
  XP.lastEnv = nw;
  if (!old || old === nw) return;
  try {
    const j = await (await postJSON("/api/explicit/env_switch", { old, new: nw, rad_target: S("rad_target") || "", out_dir: S("out_dir") || "" })).json();
    if (j.rad_target) XP.doc.settings.rad_target = j.rad_target;
    if (j.out_dir) XP.doc.settings.out_dir = j.out_dir;
    if (j.rad_target || j.out_dir) { changed(); renderRuns(); renderBuild(); renderSolve(); renderResultsJobs(); }
    poll();
  } catch (e) { showErr(e); }
}
async function historyOp(op) {
  const hist = (XP.status && XP.status.history) || [];
  const e = hist.find(x => x.index === XP.histSel);
  if (op !== "clear" && !e) { status("Run history: select a row first", true); return; }
  if (op === "clear" && !confirm(`Remove all history entries?\n\nRun folders on disk are not touched.`)) return;
  try {
    const j = await (await postJSON("/api/explicit/history", { op, index: e ? e.index : -1, job: e ? e.job : "", folder: e ? e.folder : "" })).json();
    if (op === "load") {
      if (j.rad_target) XP.doc.settings.rad_target = j.rad_target;
      XP.doc.settings.out_dir = j.out_dir;
      changed(); renderRuns(); renderBuild(); renderSolve(); renderResultsJobs();
      selectResult(j.out_dir, e.job);
    }
    if (op === "remove" || op === "clear") XP.histSel = null;
    poll();
  } catch (err) { showErr(err); }
}
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
    st.history.map(e => `<tr data-hf="${esc(e.folder)}" data-hj="${esc(e.job)}" data-hi="${e.index}" class="${e.status === "Failed" || e.status === "Killed" ? "xp-failed" : "xp-done"}${XP.histSel === e.index ? " sel" : ""}"><td title="${esc(e.folder)}">${esc(e.job)}</td><td>${esc(e.date)}</td><td>${esc(e.status)}</td><td>${esc(e.env)}</td>` +
      `<td>${e.err !== null && e.err !== undefined ? e.err.toFixed(1) + "%" : ""}</td><td>${e.dmm !== null && e.dmm !== undefined ? Number(e.dmm).toExponential(1) : ""}</td><td>${e.elapsed ? fmt(e.elapsed, 4) + " s" : ""}</td></tr>`).join("") + `</table>` : `<p class="hint">No finished jobs.</p>`;
  if (hb) hb.querySelectorAll("tr[data-hf]").forEach(tr => tr.onclick = () => {
    XP.histSel = +tr.dataset.hi;
    hb.querySelectorAll("tr[data-hi]").forEach(x => x.classList.toggle("sel", x === tr));
    selectResult(tr.dataset.hf.replace(/\\/g, "/"), tr.dataset.hj);
  });
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
  const pv = XP.plotView;
  h += `<div class="row wrap xp-plotbar"><button type="button" class="small" id="xp-csvload" title="Results CSV of any folder (<job>_Results.csv or <job>T01.csv)">Load CSV…</button>` +
    `<button type="button" class="small" id="xp-pngsave">Save PNG…</button>` +
    `<label class="check inline"><input type="checkbox" data-pv="ke"${pv.ke ? " checked" : ""}> Kinetic</label><label class="check inline"><input type="checkbox" data-pv="ie"${pv.ie ? " checked" : ""}> Internal</label>` +
    `<label class="check inline"><input type="checkbox" data-pv="tot"${pv.tot ? " checked" : ""}> KE+IE</label><label class="check inline" title="All loaded curves"><input type="checkbox" data-pv="overlay"${pv.overlay ? " checked" : ""}> Overlay all</label>` +
    (Object.keys(XP.curves).length ? `<label class="inline">Curve<select id="xp-curvesel">${optList(Object.keys(XP.curves).sort(), XP.curveSel)}</select></label>` : "") + `</div>`;
  h += `<div id="xp-plot" class="xp-plot"></div><div id="xp-parts"></div>`;
  if (d && d.energy && d.energy.note) h += `<p class="hint">${esc(d.energy.note)}</p>`;
  if (d) {
    if (!d.energy) h += `<p class="hint">No results CSV of ${esc(d.job)} (Plot KE rebuilds it from the T-file).</p>`;
    h += `<p class="hint">${d.frames.length} frame(s)` + (d.outs["0000"] ? ` · <a href="#" data-out="0000">starter .out</a>` : "") + (d.outs["0001"] ? ` · <a href="#" data-out="0001">engine .out</a>` : "") +
      ` · <a href="#" data-out="settings">settings report</a> · <a href="#" data-folder="1">open folder</a></p>`;
    if (d.strains && d.strains.length > 1) h += `<div class="fa-wide"><table class="fa-tbl"><tr>${d.strains[0].map(c => `<th>${esc(c)}</th>`).join("")}</tr>` + d.strains.slice(1).map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("") + `</table></div>`;
  } else h += `<p class="hint">Choose a job of the run, or click a row of the status board.</p>`;
  box.innerHTML = h;
  renderResultsJobs();
  $("#xp-resjob").onchange = () => { const v = $("#xp-resjob").value; if (v) { const i = v.lastIndexOf("|"); selectResult(v.slice(0, i), v.slice(i + 1)); } };
  $("#xp-resload").onclick = () => { if (XP.res.job) selectResult(XP.res.folder, XP.res.job, true); };
  box.querySelectorAll("[data-post]").forEach(b => b.onclick = () => postOp(b.dataset.post));
  box.querySelectorAll("[data-pv]").forEach(c => c.onchange = () => { XP.plotView[c.dataset.pv] = c.checked; delete (XP.zoom || {}).energy; plotEnergy(); });
  if ($("#xp-curvesel")) $("#xp-curvesel").onchange = () => { XP.curveSel = $("#xp-curvesel").value; delete (XP.zoom || {}).energy; plotEnergy(); };
  $("#xp-csvload").onclick = async () => {
    try {
      const p = await window.browse("open", "csv", XP.res.folder || S("out_dir") || "", "Select a results CSV (<job>_Results.csv or <job>T01.csv)");
      if (!p) return;
      const j = await (await postJSON("/api/explicit/results_csv", { path: p })).json();
      XP.curves[j.job] = { t: j.t, ke: j.ke, ie: j.ie, src: j.csv };
      XP.curveSel = j.job;
      renderResults();
      poll();
    } catch (e) { showErr(e); }
  };
  $("#xp-pngsave").onclick = () => {
    if (!Object.keys(XP.curves).length) { status("Results: nothing to save yet", true); return; }
    savePlotPng($("#xp-plot"), (XP.curveSel || "energy") + "_KE.png", XP.res.folder || S("out_dir") || "");
  };
  box.querySelectorAll("[data-out]").forEach(a => a.onclick = e => {
    e.preventDefault();
    const k = a.dataset.out;
    showText(k === "settings" ? `${XP.res.folder}/${XP.res.job}_settings.txt` : `${XP.res.folder}/${XP.res.job}_${k}.out`);
  });
  box.querySelectorAll("[data-folder]").forEach(a => a.onclick = e => { e.preventDefault(); postJSON("/api/explicit/open_folder", { path: XP.res.folder }).catch(showErr); });
  plotEnergy();
}
async function postOp(op) {
  const needJob = !["macro", "extract"].includes(op) && !(op === "plot_ke" && S("out_dir"));
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
  XP.partHide = new Set();
  try {
    XP.res.data = await (await postJSON("/api/explicit/results", { folder, job })).json();
    if (XP.res.data.energy) { XP.curveSel = job; delete XP.zoom.energy; }
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
  renderParts();
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

/** KE / IE / KE+IE curves (ORC**3 Results tab): the selected curve, or all loaded curves (Overlay all). */
function plotEnergy() {
  const box = $("#xp-plot");
  if (!box) return;
  const d = XP.res.data;
  if (d && d.energy) {
    XP.curves[d.job] = { t: d.energy.t, ke: d.energy.ke, ie: d.energy.ie, src: d.energy.csv };
    if (!XP.curveSel) XP.curveSel = d.job;
  }
  const pv = XP.plotView;
  const names = pv.overlay ? Object.keys(XP.curves).sort() : (XP.curves[XP.curveSel] ? [XP.curveSel] : []);
  const series = [];
  let ci = 0;
  for (const n of names) {
    const c = XP.curves[n];
    const pre = names.length > 1 ? n + " - " : "";
    const col = PLOT_COLORS[ci++ % PLOT_COLORS.length];
    if (pv.ke) series.push({ name: pre + "Kinetic", x: c.t, y: c.ke, color: names.length > 1 ? col : "#1f5fae" });
    if (pv.ie && c.ie) series.push({ name: pre + "Internal", x: c.t, y: c.ie, color: names.length > 1 ? col : "#e8590c", dash: "6,3" });
    if (pv.tot && c.ie) series.push({ name: pre + "KE+IE", x: c.t, y: c.ke.map((v, i) => v + c.ie[i]), color: names.length > 1 ? col : "#2f9e44", dash: "2,3" });
  }
  const f = XP.res.frame;
  svgPlot(box, "energy", series, { xlabel: "Time (s)", ylabel: "Energy (mJ)", title: names.length === 1 ? names[0] : names.length > 1 ? `${names.length} jobs overlaid` : "",
    empty: "No curves loaded. Run a job (Plot KE ticked), or Load CSV…", marker: !pv.overlay && f && XP.curveSel === XP.res.job ? f.time : null, legend: series.length > 1 });
}

// ------------------------------------------------------------------ Rivet panel (ORC**3 Rivet tab)

function renderRivet() {
  const sec = $("#xp-sec-rivet"), box = section("xp-rivet");
  if (!box || !XP.doc || !XP.meta) return;
  sec.hidden = hidden("rivet");
  const R = XP.meta.rivet;
  if (R.import_error) { box.innerHTML = `<p class="xp-bad">The rivet_calibration package could not be imported: ${esc(R.import_error)}</p>`; return; }
  const ax = R.axes;
  let h = `<h3 class="xp-h">Gauge rings (relative displacement across the rivet)</h3>` +
    `<div class="row wrap">Hole centre${inS("rv_centre_x", "X", 56)}${inS("rv_centre_y", "Y", 56)}${inS("rv_centre_z", "Z", 56)}${inS("rv_radius", "Ring radius [mm]", 50)}${selS("rv_axis", "Shank axis", ax)}</div>` +
    `<div class="row wrap">Plate mid-surfaces${inS("rv_plate1", "1", 50)}${inS("rv_plate2", "2", 50)}${inS("rv_rtol", "Radial tol [mm]", 40)}${inS("rv_atol", "Axial tol [mm]", 40)}` +
    `${inS("rv_maxnodes", "Max nodes/ring", 34)}${inS("rv_thgroup", "First TH grp", 44)}</div>` +
    `<div class="row wrap"><button type="button" id="xp-rv-rings" class="primary">Build Gauge Rings</button><span class="hint">th_gauge_rings.inc and gauge_rings.json next to the Target .rad; #include the .inc in the starter deck and add /TH/TITLE to the engine deck</span></div>` +
    `<h3 class="xp-h">Force - relative displacement</h3>` +
    `<div class="row wrap"><label class="inline xp-f">Force column<input type="text" data-s="rv_force_col" value="${esc(S("rv_force_col"))}" style="width:150px" list="xp-rv-cols"></label><datalist id="xp-rv-cols">${(XP.rvColumns || []).map(c => `<option value="${esc(c)}">`).join("")}</datalist>` +
    `<button type="button" class="small" id="xp-rv-cols-b" title="Columns of the results CSV (console)">Columns…</button>${inS("rv_force_scale", "Force scale", 40)}<span class="hint">(2.0 for a symmetry half-model)</span></div>` +
    `<div class="row wrap">${selS("rv_component", "Component", R.components)}${inS("rv_angle", "Load angle [deg]", 40)}<span class="hint">(0 = shear, 90 = tension)</span>${selS("rv_shear_dir", "Shear dir", ax)}${selS("rv_axis_dir", "Axis dir", ax)}</div>` +
    `<div class="row wrap">${inS("rv_filter_hz", "Filter [Hz]", 56)}<span class="hint">blank = none; the same value on every case</span>${inS("rv_case_id", "Case ID", 56)}<span class="hint">(run sheet label, e.g. A1)</span></div>` +
    `<div class="row wrap"><button type="button" id="xp-rv-extract" class="primary">Extract F-d</button><button type="button" class="small" id="xp-rv-load">Load F-d CSV…</button>` +
    `<button type="button" class="small" id="xp-rv-clear">Clear Curves</button><button type="button" class="small" id="xp-rv-png">Save PNG…</button></div>` +
    `<pre class="xp-mono xp-rvsum">${esc(XP.rvSummary)}</pre><div id="xp-rvplot" class="xp-plot"></div>`;
  box.innerHTML = h;
  bindFields(box);
  const op = async (o, extra) => {
    try {
      if (XP.dirty && FM.isSaved()) await saveDoc(XP.doc.name);
      const j = await (await postJSON("/api/explicit/rivet", req(Object.assign({ op: o }, extra || {})))).json();
      poll();
      return j;
    } catch (e) { if (o === "extract") { XP.rvSummary = "Failed: " + (e.message || e); renderRivet(); } showErr(e); poll(); return null; }
  };
  $("#xp-rv-rings").onclick = async () => { const j = await op("rings"); if (j) { status(`Gauge rings: ${j.rings.map(r => r.tag + " " + r.nodes.length + " nodes").join(", ")}`); openSection("xp-sec-console"); } };
  $("#xp-rv-cols-b").onclick = async () => { const j = await op("columns"); if (j) { XP.rvColumns = j.columns; renderRivet(); openSection("xp-sec-console"); } };
  $("#xp-rv-extract").onclick = async () => { const j = await op("extract"); if (j) rivetShow(j.curve); };
  $("#xp-rv-load").onclick = async () => {
    try {
      const p = await window.browse("open", "fdcsv", "", "Select an F-d CSV written by Extract F-d");
      if (!p) return;
      const j = await op("load_fd", { path: p });
      if (j) rivetShow(j.curve);
    } catch (e) { showErr(e); }
  };
  $("#xp-rv-clear").onclick = () => { XP.rvCurves = {}; XP.rvSummary = "No curve extracted yet."; delete XP.zoom.rivet; renderRivet(); };
  $("#xp-rv-png").onclick = () => {
    if (!Object.keys(XP.rvCurves).length) { status("Rivet: nothing to save yet", true); return; }
    savePlotPng($("#xp-rvplot"), (String(S("rv_case_id") || "").trim() || "rivet") + "_Fd.png", "");
  };
  plotRivet();
}
function rivetShow(c) {
  XP.rvCurves[c.label] = c;
  XP.rvSummary = c.summary;
  delete XP.zoom.rivet;
  renderRivet();
}
function plotRivet() {
  const names = Object.keys(XP.rvCurves).sort();
  const series = names.map((n, i) => {
    const c = XP.rvCurves[n];
    return { name: n, x: c.disp, y: c.force, color: PLOT_COLORS[i % PLOT_COLORS.length], peak: c.peak_index !== null && c.peak_index !== undefined ? [c.peak_disp, c.peak_force] : null };
  });
  svgPlot($("#xp-rvplot"), "rivet", series, { xlabel: "Relative displacement across the rivet", ylabel: "Force", zeroY: false,
    title: names.length === 1 ? names[0] : "", empty: "No curve yet. Build the gauge rings, run the job, then Extract F-d." });
}

// ------------------------------------------------------------------ Tools panel (ORC**3 Tools tab)

async function loadTools() {
  try { XP.tools = await (await api("/api/explicit/tools")).json(); } catch (e) { XP.tools = null; showErr(e); }
  renderTools();
}
function renderTools() {
  const box = section("xp-tools");
  if (!box) return;
  const T = XP.tools;
  if (!T) { box.innerHTML = `<p class="hint">Loading…</p>`; return; }
  const showH = !!XP.toolsShowHidden;
  let h = `<p class="hint">Launch: the script runs with the Python of ShinyCAD from its own folder. Console tools open their own console window (Windows) and it stays open after the run. The grey note after each box states what an empty box does. ${helpBtn("The File / Folder / Options box", T.args_doc)}</p>` +
    `<div class="row wrap"><button type="button" class="small" id="xp-tl-edit" title="${esc(T.file)}">Edit tools.json</button><button type="button" class="small" id="xp-tl-reload">Reload list</button>` +
    `<label class="check inline"><input type="checkbox" id="xp-tl-hidden"${showH ? " checked" : ""}> Show hidden (${T.hidden.length})</label></div>`;
  if (T.file_error) h += `<p class="xp-bad">tools.json: ${esc(T.file_error)}</p>`;
  const groups = new Map();
  for (const t of T.tools) {
    if (t.hidden && !showH) continue;
    if (!groups.has(t.group)) groups.set(t.group, []);
    groups.get(t.group).push(t);
  }
  if (!groups.size) h += `<p class="hint">Every tool is hidden. Tick Show hidden to restore one.</p>`;
  for (const [g, list] of groups) {
    h += `<h3 class="xp-h">${esc(g)}</h3><div class="xp-tools">`;
    for (const t of list) {
      const box2 = t.no_args ? `<span class="hint">(nothing to set)</span>` :
        `<label class="inline xp-f">${esc(t.arg_label || "Options:")}<input type="text" data-targ="${esc(t.key)}" value="${esc(t.args || "")}" style="width:150px"></label>${t.arg_hint ? `<span class="hint">${esc(t.arg_hint)}</span>` : ""}`;
      h += `<div class="xp-tool${t.hidden ? " xp-tool-h" : ""}"><div class="row wrap"><b class="xp-tool-t">${esc(t.title)}${t.hidden ? " [hidden]" : ""}</b>${box2}` +
        `<span style="flex:1"></span><button type="button" class="small primary" data-tlaunch="${esc(t.key)}"${t.exists ? "" : " disabled"}>Launch</button>${helpBtn(t.title, t.doc || "")}` +
        (t.hidden ? `<button type="button" class="small" data-trestore="${esc(t.key)}">Restore</button>` :
          `<button type="button" class="small" data-tremove="${esc(t.key)}" title="${t.builtin ? "Hide (built-in; Show hidden -> Restore)" : "Remove from the list (the file is not deleted)"}">×</button>`) + `</div>` +
        `<div class="hint">${esc(t.desc || "")}${t.exists ? "" : ` <span class="xp-bad">[FILE NOT FOUND: ${esc(t.path)}]</span>`}</div></div>`;
    }
    h += `</div>`;
  }
  h += `<h3 class="xp-h">Add a script</h3><div class="row"><label class="inline" style="flex:1">Script<input type="text" id="xp-tl-path" style="flex:1;width:auto" value="${esc(XP.toolNew ? XP.toolNew.path : "")}"></label><button type="button" class="small" id="xp-tl-browse">…</button></div>` +
    `<div class="row wrap"><label class="inline xp-f">Name<input type="text" id="xp-tl-title" style="width:150px" value="${esc(XP.toolNew ? XP.toolNew.title : "")}"></label>` +
    `<label class="inline xp-f">Type<select id="xp-tl-kind">${optList(["cli", "gui", "auto"], XP.toolNew ? XP.toolNew.kind : "cli")}</select></label><button type="button" class="small primary" id="xp-tl-add">Add</button></div>` +
    `<p class="hint">cli = own console window | gui = own window | auto = window when the box is empty. Blank Name = the file name. Added scripts are written to ${esc(T.file)}; Reload list reads the file after editing.</p>`;
  box.innerHTML = h;
  bindHelp(box);
  const after = j => { XP.tools = j; renderTools(); poll(); };
  const top = (body) => postJSON("/api/explicit/tools", body).then(r => r.json()).then(after).catch(e => { showErr(e); poll(); });
  $("#xp-tl-edit").onclick = () => top({ op: "open_file" });
  $("#xp-tl-reload").onclick = () => top({ op: "reload" });
  $("#xp-tl-hidden").onchange = e => { XP.toolsShowHidden = e.target.checked; renderTools(); };
  box.querySelectorAll("[data-targ]").forEach(el => el.onchange = () => {
    const t = XP.tools.tools.find(x => x.key === el.dataset.targ);
    if (t) t.args = el.value;
    postJSON("/api/explicit/tools", { op: "args", key: el.dataset.targ, args: el.value }).catch(showErr);
  });
  box.querySelectorAll("[data-tlaunch]").forEach(b => b.onclick = () => {
    const el = box.querySelector(`[data-targ="${CSS.escape(b.dataset.tlaunch)}"]`);
    launchTool(b.dataset.tlaunch, el ? el.value : "");
  });
  box.querySelectorAll("[data-tremove]").forEach(b => b.onclick = () => {
    const t = XP.tools.tools.find(x => x.key === b.dataset.tremove);
    if (t && !t.builtin && !confirm(`Remove '${t.title}' from the Tools list?\n\n${t.script}\n\nThe file is not deleted.`)) return;
    top({ op: "remove", key: b.dataset.tremove });
  });
  box.querySelectorAll("[data-trestore]").forEach(b => b.onclick = () => top({ op: "restore", key: b.dataset.trestore }));
  const keepNew = () => { XP.toolNew = { path: $("#xp-tl-path").value, title: $("#xp-tl-title").value, kind: $("#xp-tl-kind").value }; };
  for (const id of ["#xp-tl-path", "#xp-tl-title", "#xp-tl-kind"]) $(id).onchange = keepNew;
  $("#xp-tl-browse").onclick = async () => {
    try {
      const p = await window.browse("open", "py", "", "Script");
      if (!p) return;
      $("#xp-tl-path").value = p;
      if (!$("#xp-tl-title").value.trim()) $("#xp-tl-title").value = p.split(/[\\/]/).pop().replace(/\.[^.]*$/, "");
      keepNew();
    } catch (e) { showErr(e); }
  };
  $("#xp-tl-add").onclick = () => {
    keepNew();
    postJSON("/api/explicit/tools", Object.assign({ op: "add" }, XP.toolNew)).then(r => r.json()).then(j => { XP.toolNew = null; after(j); }).catch(e => { showErr(e); poll(); });
  };
}
async function launchTool(key, args) {
  try {
    if (XP.dirty && FM.isSaved()) await saveDoc(XP.doc.name);
    const j = await (await postJSON("/api/explicit/tools", req({ op: "launch", key, args: args || "" }))).json();
    status(j.message || "Launched");
  } catch (e) { showErr(e); }
  poll();
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
  renderModel(); renderRuns(); renderBuild(); renderRivet(); renderSolve(); renderResults();
  if (!XP.tools) loadTools(); else renderTools();
  $("#xp-supbtn").disabled = !isShiny();
  $("#xp-update").disabled = !isShiny();
  const mb = $("#xp-model-btn");
  (mb.querySelector(".tb-lbl") || mb).textContent = isModel() ? "Mesh" : "Show mesh";
  $("#xp-model-btn").title = isDeck() ? "Mesh the deck (structured shells), write the model .inp and show the mesh" : isShiny() ? "Mesh the bodies and shells, write the model .inp and show the mesh" : "Show the mesh of the .inp";
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
  XP.sel = null; XP.pick = null; XP.mesh = null; VS.clear(SH); SM.selState(SH).collect = null; VS.renderBar(SH); XP.meshSummary = null;
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
  await refreshInit();
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
    if (!XP.env) { XP.envInfo = await (await api("/api/explicit/env")).json(); XP.env = XP.envInfo.env; XP.lastEnv = XP.env.run_target; }
  } catch (e) { showErr(e); return; }
  if (!XP.three) initThree();
  MS.installLibraryPick($("#tab-xp"), addLibraryMaterial);
  if (!XP.consoleReady) { renderConsole(); XP.consoleReady = true; }
  if (!XP.doc) await loadDoc(blankDoc("explicit"));
  else { refreshList(); renderAllPanels(); }
  startPolling();
  poll();
  checkGeometry();
  setTimeout(resize3, 0);
};

(function bindXp() {
  VS.renderBar(SH, $("#xp-selbar"));
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && XP.pick && !$("#tab-xp").hidden) { endPick(); status("Pick cancelled"); }
    else if (e.key === "Escape" && XP.popup && !$("#tab-xp").hidden) { closePopup(); renderStatusBar(); }
    else if ((e.key === "Escape" || (e.key === "Enter" && !e.target.closest("input, textarea, select"))) && !$("#tab-xp").hidden && VS.key(SH, e)) e.preventDefault();
  });
  $("#xp-source").onchange = () => {
    const v = $("#xp-source").value;
    const i = v.indexOf(":");
    XP.doc.source = Object.assign({}, XP.doc.source, v ? { kind: "shinycad", type: v.slice(0, i), name: v.slice(i + 1) } : { kind: "shinycad", type: "assembly", name: "" });
    XP.mesh = null; XP.meshSummary = null;
    $("#xp-show").value = "model";
    changed(); loadGeometry();
  };
  $("#xp-update").onclick = updateGeometry;
  window.addEventListener("focus", checkGeometry);
  setInterval(checkGeometry, 4000);
  $("#xp-model-btn").onclick = writeInp;
  $("#xp-build").onclick = build;
  $("#xp-run").onclick = () => solve("run");
  $("#xp-starter").onclick = () => solve("starter");
  $("#xp-kill").onclick = kill;
  $("#xp-supbtn").onclick = addSupport;
  document.querySelectorAll("#tab-xp [data-xpview]").forEach(b => b.onclick = () => view(b.dataset.xpview));
  $("#xp-show").onchange = () => {
    if ($("#xp-show").value === "mesh" && !XP.mesh) { $("#xp-show").value = "model"; status(isModel() ? "Mesh first" : "Show mesh first", true); }
    if ($("#xp-show").value === "results" && !XP.res.frame) { $("#xp-show").value = XP.mesh ? "mesh" : "model"; status("Choose a job with frames in Results", true); }
    if (XP.three) XP.three.zoomed = false;
    draw();
  };
  for (const id of ["#xp-edges", "#xp-thick", "#xp-bcs", "#xp-axes", "#xp-scale", "#xp-undef", "#xp-eroded", "#xp-min", "#xp-max"]) $(id).onchange = draw;
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

window.__xp = { XP, SH, renderModel, draw };
window.__xpLoadNamed = async function (name) { await loadDoc(await (await api("/api/explicit/file/" + encodeURIComponent(name))).json()); if (FM) FM.markSaved(name); };
window.__xpSetName = name => { if (XP.doc) { XP.doc.name = name; if (FM) FM.markSaved(name); } };
window.__xpRefresh = () => { if (XP.doc) refreshList(); };
window.__xpCurrent = () => (XP.doc ? { name: XP.doc.name, dirty: !!XP.dirty } : null);
