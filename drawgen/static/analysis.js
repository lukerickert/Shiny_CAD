// Analysis tab: linear static analysis with CalculiX of an assembly or part: bodies (solid or plate), beams, rods,
// fasteners with preload, supports, loads; mesh, solve, deformed shape with contours, result tables and report.
import * as THREE from "three";
import { TumbleControls } from "/static/vendor/TumbleControls.js";
import { updateAxes } from "/static/axes.js";
import { createNavCube } from "/static/navcube.js";
import { addBodyGroups, bodyMaterials, edgeAt as edgeAtScreen, edgeSegments, edgeLabel } from "/static/bodyview.js";
import * as SM from "/static/shellmodel.js";
import { drawBcLoads, hasNodeGlyphs, supportDofs } from "/static/bcglyphs.js";
import * as RP from "/static/refpoints.js";
import { thicken } from "/static/shellthick.js";
import * as PN from "/static/panels.js";
import * as MS from "/static/matsel.js";
import * as VS from "/static/viewsel.js";
import * as TP from "/static/paneltree.js";
import * as TH from "/static/thplot.js";
import * as HR from "/static/histreq.js";
import * as HO from "/static/handoff.js";
import * as IF from "/static/inpinfo.js";
import * as CV from "/static/curves.js";

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
                     eline: "Line load on an edge", gravity: "Gravity" };
const COLORS = { support: 0x1c7ed6, load: 0xe03131, fastener: 0xe8590c, connect: 0x2f9e44, beam: 0x364fc7, rod: 0x0c8599,
                 sel: 0xf08c00, sketch: 0x7048e8, surface: 0x5b7fb5, surfaceEdge: 0x3a5a8a, master: 0x0c8599, slave: 0xd6336c };

function blankDoc(name) {
  return { name: name || "analysis", source: { type: "assembly", name: "" },
           materials: { "Steel": { E: 210000, nu: 0.3, rho: 7850 }, "Aluminium": { E: 70000, nu: 0.33, rho: 2700 } },
           default_material: "Steel", mesh: { size: 0 }, bonded: true, bodies: {},
           members: [], plates: [], fasteners: [], supports: [], loads: [], next: 1 };
}
function nid(p) { return p + (FA.doc.next++); }
/** Host of the sections and node sets panels (shellmodel.js). */
const SH = {
  doc: () => FA.doc,
  comps: () => ((FA.geo && FA.geo.components) || []).filter(c => !c.plate && c.mesh),
  compName: id => (((FA.asm && FA.asm.components) || []).find(x => x.id === id) || {}).name || id,
  matOptions: cur => matOptions(cur), modes: [["shell", "shell"], ["off", "off"]], nid: p => nid(p),
  layers: () => ({ enabled: s8r(), title: LAYERS_TIP }),
  changed: () => changed(), draw: () => draw(), render: () => { renderSections(); renderNsets(); renderContacts(); renderSups(); if ($("#fs-refine")) SM.renderRefine(SH, $("#fs-refine")); },
  status: (t, e) => status(t, e), postJSON: (u, b) => postJSON(u, b), fmt: v => ffmt(v, 6), esc: s => fesc(s),
  setTypes: types => VS.setTypes(SH, types),
  collect: opts => VS.collect(SH, opts),
  suppressCfg: (kind, id) => {
    const d = FA.doc;
    if (kind === "section") { const s = (d.sections || []).find(x => x.id === id); return s ? [s, "mode", "shell"] : null; }
    if (kind === "shell") { d.shells = d.shells || {}; return [d.shells[id] = d.shells[id] || {}, "mode", "shell"]; }
    d.bodies = d.bodies || {};
    return [d.bodies[id] = d.bodies[id] || {}, "mode", "solid"];
  },
  view: {
    canvas: () => FA.three.renderer.domElement, camera: () => FA.three.camera, box: () => $("#fa-view"),
    modelShown: () => $("#fa-show").value === "model",
    showModel: () => { $("#fa-show").value = "model"; draw(); },
    comps: () => ((FA.geo && FA.geo.components) || []).filter(c => c.mesh && !c.plate).map(c => ({ id: c.id, mesh: c.mesh, matrix: matOf(c), surfaces: c.surfaces || [] })),
    points: () => (FA.doc.points || []).filter(p => p.xyz),
    faceAt: e => faceUnder(e), edgeAt: e => edgeUnder(e),
    meshShown: () => $("#fa-show").value === "mesh",
    showMesh: () => { if (FA.mesh) { $("#fa-show").value = "mesh"; draw(); } else status("Mesh first: the mesh nodes and elements are selected on Show Mesh", true); },
    mesh: () => FA.meshSel || null,
    meshHit: e => {
      if (!FA.meshSel || !FA.three) return null;
      const h = rayAt(e).intersectObjects(FA.three.group.children.filter(o => o.userData && o.userData.kind === "mesh"), false)[0];
      return h && h.faceIndex !== undefined && h.faceIndex < FA.meshSel.triElem.length ? { tri: h.faceIndex, point: h.point.toArray() } : null;
    },
  },
  onNsetSupport: ns => {
    const s = { id: nid("s"), name: "Support " + (FA.doc.supports.length + 1), type: "fixed", target: { nset: ns.id } };
    FA.doc.supports.push(s); FA.sel = { kind: "support", id: s.id }; changed(); renderAll(); draw();
    status(s.name + ": node set " + ns.name);
  },
};
/** Host of the reference point, spring, joint and equation panels (refpoints.js). */
const CON_KINDS = { rp: 1, spring: 1, joint: 1, eq: 1 };
const RH = {
  doc: () => FA.doc,
  comps: () => ((FA.geo && FA.geo.components) || []).filter(c => c.mesh && !c.plate).map(c => ({ id: c.id, mesh: c.mesh, matrix: matOf(c) })),
  faceRef: r => faceRef(r), edgeRef: r => edgeRefG(r), refText: r => targetText(r),
  nid: p => nid(p), changed: () => changed(), render: () => { renderRps(); renderCons(); renderSups(); renderLoads(); }, draw: () => draw(),
  status: (t, e) => status(t, e), fmt: v => ffmt(v, 6), esc: s => fesc(s),
  pickPoint: (t, cb) => startPick(t, { snap: true }, hit => { cb(hit); status(`Point (${hit.xyz.map(v => ffmt(v, 6)).join(", ")}) mm`); }),
  pickFace: (t, cb) => startPick(t, {}, hit => { if (hit.face) cb(hit.face); }),
  pickEdge: (t, cb) => startPick(t, { edge: true, noFace: true }, hit => { if (hit.edge) cb(hit.edge); }),
  sel: () => (FA.sel && CON_KINDS[FA.sel.kind] ? FA.sel : null),
  select: (k, id) => { FA.sel = k ? { kind: k, id } : null; renderAll(); draw(); },
  selPoints: () => SM.selState(SH).points,
  collect: opts => VS.collect(SH, opts),
};
/** Edge reference in global coordinates: {kind, c (centre of a circle, midpoint of a line), dir (line direction or
 *  circle axis)}. */
function edgeRefG(ref) {
  const c = ref && compOf(ref.comp);
  const r = c && c.erefs && c.erefs[ref.edge];
  if (!r) return null;
  const M = matOf(c);
  return { kind: r.kind, c: new THREE.Vector3(...r.c).applyMatrix4(M).toArray(), dir: r.n ? new THREE.Vector3(...r.n).transformDirection(M).toArray() : null };
}
function renderCons() {
  if ($("#fa-springs")) RP.renderSprings(RH, $("#fa-springs"));
  if ($("#fa-joints")) RP.renderJoints(RH, $("#fa-joints"));
  if ($("#fa-eqs")) RP.renderEquations(RH, $("#fa-eqs"));
}
function renderSections() { if ($("#fa-sections")) SM.renderSections(SH, $("#fa-sections")); }
function renderNsets() { if ($("#fa-nsets")) SM.renderNsets(SH, $("#fa-nsets")); if ($("#fa-surfaces")) SM.renderSurfaces(SH, $("#fa-surfaces")); }
function changed() { FA.dirty = true; if (FM) FM.render(); }
function findItem(kind, id) { return (FA.doc[{ member: "members", fastener: "fasteners", support: "supports", load: "loads", plate: "plates", rp: "points", contact: "contacts" }[kind]] || []).find(x => x.id === id); }

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
  VS.attach(SH);
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
/** The face of a component under the cursor: {comp, face}, or null. */
function faceUnder(e) {
  if (!FA.three) return null;
  const h = rayAt(e).intersectObjects(FA.three.pickables, false).find(x => x.object.userData && x.object.userData.comp !== undefined && x.object.userData.kind !== "plate");
  const c = h && compOf(h.object.userData.comp);
  const fi = c && c.mesh ? c.mesh.face_of_tri[h.faceIndex] : null;
  return fi !== null && fi !== undefined ? { comp: c.id, face: fi } : null;
}
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
/** The point a point pick takes under the cursor (refpoints.js snapPoint): reference points, member ends, plate and
 *  sketch points, vertices, mesh nodes (Show Mesh), points on edges and faces. */
function snapAt(e) {
  const t = FA.three, rect = t.renderer.domElement.getBoundingClientRect();
  const pts = [];
  for (const p of FA.doc.points || []) if (p.xyz) pts.push({ xyz: p.xyz, kind: "rp", label: p.name });
  for (const m of FA.doc.members) for (const k of ["a", "b"]) if (m[k] && m[k].xyz) pts.push({ xyz: m[k].xyz, kind: "end", label: "member end" });
  for (const q of [...(FA.doc.plates || []).flatMap(p => p.points || []), ...sketchPoints()]) pts.push({ xyz: q, kind: "point", label: "point" });
  const ctx = { x: e.clientX, y: e.clientY, camera: t.camera, rect, points: pts, comps: RH.comps(), mesh: null, face: null };
  const rc = rayAt(e);
  if ($("#fa-show").value === "model") {
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
      ctx.mesh = { pos: g.attributes.position.array, tri: g.index.array, faceIndex: h.faceIndex };
      ctx.face = { xyz: h.point.toArray(), normal: h.face.normal.clone().transformDirection(h.object.matrixWorld).toArray(), ref: null };
    }
  }
  if (FA.pick && FA.pick.raw) return ctx.face ? { xyz: ctx.face.xyz, normal: ctx.face.normal, face: ctx.face.ref, kind: "face" } : null;     // the point on the surface
  const sp = RP.snapPoint(ctx);
  if (sp) sp.xyz = sp.xyz.map(v => Math.round(v * 1e6) / 1e6);
  return sp;
}
function hoverView(e) {
  const t = FA.three;
  if (!t || !FA.doc) return;
  clearHover();
  if (FA.pick && FA.pick.snap) {
    const sp = snapAt(e), r = (FA.size || 100) / 300;
    if (sp) {
      const b = new THREE.Mesh(new THREE.SphereGeometry(r * 2.6, 16, 12), new THREE.MeshBasicMaterial({ color: COLORS.sel, transparent: true, opacity: 0.7, depthTest: false }));
      b.position.set(...sp.xyz);
      b.renderOrder = 10;
      t.hover = b;
      t.scene.add(b);
      $("#fa-info").textContent = `${sp.label}: (${sp.xyz.map(v => ffmt(v, 5)).join(", ")}) mm`;
    }
    t.renderer.domElement.style.cursor = sp ? "crosshair" : "";
    render3();
    return;
  }
  if ($("#fa-show").value !== "model") { render3(); return; }
  const S = SM.selState(SH), ty = VS.active(SH) && !FA.pick ? S.types : null;
  const pk = FA.pick || (ty ? { edge: ty.has("edges"), noFace: !ty.has("faces") && !ty.has("bodies"), end: !!(S.collect && S.collect.extra), text: "" } : null), r = (FA.size || 100) / 300;
  let pt = null, face = null, item = false;
  const end = !pk || pk.end || pk.point ? endAt(e) : null;
  if (end) pt = end.xyz;
  else if (pk && pk.point) pt = snapPointAt(e);
  let edge = null;
  if (!pt && pk && pk.edge) edge = edgeUnder(e);
  if (!pt && !edge && pk && !pk.noFace) {
    const h = rayAt(e).intersectObjects(t.pickables, false).find(x => x.object.userData && x.object.userData.comp !== undefined);
    const c = h && compOf(h.object.userData.comp);
    const fi = c && c.mesh ? c.mesh.face_of_tri[h.faceIndex] : null;
    if (fi !== null && fi !== undefined) face = { c, fi };
  }
  if (!pt && !face && !pk) {
    const h = hitAt(e);
    item = !!(h && h.object.userData && (h.object.userData.kind || h.object.userData.comp !== undefined));
  }
  if (pt || face || edge) {
    const g = new THREE.Group();
    if (edge) {
      const c = compOf(edge.comp), ep = edgeSegments(c.mesh, edge.edge);
      const eg = new THREE.BufferGeometry();
      eg.setAttribute("position", new THREE.Float32BufferAttribute(ep, 3));
      const ls = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: COLORS.sel, depthTest: false }));
      ls.matrixAutoUpdate = false;
      ls.matrix.copy(matOf(c));
      ls.renderOrder = 10;
      g.add(ls);
      const pts = new THREE.Points(eg, new THREE.PointsMaterial({ color: COLORS.sel, size: 6, sizeAttenuation: false, depthTest: false }));
      pts.matrixAutoUpdate = false;
      pts.matrix.copy(matOf(c));
      pts.renderOrder = 10;
      g.add(pts);
    } else if (pt) {
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
  t.renderer.domElement.style.cursor = pk ? (pt || face || edge ? "crosshair" : "") : (end || item) ? "pointer" : "";
  render3();
}

/** The edge of a component within 8 px of the cursor: {comp, edge}, or null. */
function edgeUnder(e) {
  const comps = ((FA.geo && FA.geo.components) || []).filter(c => c.mesh && !c.plate).map(c => ({ id: c.id, mesh: c.mesh, matrix: matOf(c) }));
  const h = edgeAtScreen(comps, FA.three.camera, FA.three.renderer.domElement.getBoundingClientRect(), e.clientX, e.clientY, 8);
  return h ? { comp: h.comp, edge: h.edge } : null;
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
  if (s.type === "inp" || !s.name) return { components: [] };
  if (s.type === "part") return { components: [{ id: "1", name: s.name, source: { type: "part", name: s.name }, pos: [0, 0, 0], rot: [0, 0, 0] }] };
  return await (await api("/api/assembly/file/" + encodeURIComponent(s.name))).json();
}

/** State key of the assembly or part of the geometry (server: sha1 of the assembly file and of its sources). */
async function geometryKey(src) {
  if (!src || !(src.name || src.path)) return "";
  try { return (await (await postJSON("/api/geometry/state", { source: src })).json()).key || ""; } catch (e) { return null; }
}
/** A changed assembly or part marks Update (the update itself is manual). */
async function checkGeometry() {
  if (!FA.doc || $("#tab-fea").hidden || FA.geoKey === undefined) return;
  const k = await geometryKey(FA.doc.source);
  if (k === null) return;
  const stale = k !== FA.geoKey;
  if (stale !== !!FA.geoStale) {
    FA.geoStale = stale;
    $("#fa-update").classList.toggle("cm-stale", stale);
    $("#fa-update").title = stale ? "The assembly or one of its parts has changed: Update loads the geometry again" : "Load the geometry again (after a change of the assembly or its parts)";
    if (stale) status(({ part: "The part ", inp: "The .inp file " }[FA.doc.source.type] || "The assembly ") + FA.doc.source.name + " has changed: Update loads the geometry again");
  }
}
/** Update: the geometry loaded again; the mesh and results of the old geometry are cleared. */
async function updateGeometry() {
  FA.mesh = null; FA.res = null; setStates();
  $("#fa-show").value = "model";
  await loadGeometry();
  status("Geometry updated");
}

async function loadGeometry() {
  const seq = ++FA.seq;
  $("#fa-info").textContent = "Loading the geometry...";
  try {
    const key = await geometryKey(FA.doc.source);
    if ((FA.doc.source || {}).type === "inp") { await loadInp(seq, key); return; }
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
    for (const c of j.components) if (c.mkey && c.mesh) MESHES.set(c.mkey, { mesh: c.mesh, refs: c.refs || [], erefs: c.erefs || [], surfaces: c.surfaces || [] });
    for (const c of j.components) if (c.mkey && MESHES.has(c.mkey)) { const e = MESHES.get(c.mkey); c.mesh = e.mesh; c.refs = e.refs; c.erefs = e.erefs; c.surfaces = e.surfaces; }
    FA.geo = j;
    if (SM.ensureSections(SH)) changed();                    // every surface body face in a section
    FA.geoKey = key === null ? undefined : key;
    FA.geoStale = false;
    $("#fa-update").classList.remove("cm-stale");
    await loadPlates(true);
    const errs = j.components.filter(c => c.error && !c.plate && !(c.mesh === null && sketchOnly(c.id))).map(c => c.error);
    $("#fa-info").textContent = `${j.components.length} component(s)` + (errs.length ? ": " + errs.join("; ") : "");
    if (FA.three) FA.three.zoomed = false;
    draw(); renderAll();
  } catch (e) { if (seq === FA.seq) { $("#fa-info").textContent = ""; showErr(e); } }
}

/** Geometry of a CalculiX .inp or Radioss .rad source (server: inpmodel.view): one component per body of the file. */
async function loadInp(seq, key) {
  const src = FA.doc.source;
  const j = await (await postJSON("/api/analysis/inp_geometry", { path: src.path })).json();
  if (seq !== FA.seq) return;
  for (const c of j.components) {
    if (!MESHES.has(c.mkey)) MESHES.set(c.mkey, { mesh: c.mesh, refs: c.refs || [], erefs: c.erefs || [], surfaces: c.surfaces || [] });
    const e = MESHES.get(c.mkey); c.mesh = e.mesh; c.refs = e.refs; c.erefs = e.erefs; c.surfaces = e.surfaces;
  }
  FA.asm = { components: j.components.map(c => ({ id: c.id, name: c.name })) };
  FA.sketches = [];
  FA.geo = { components: j.components };
  FA.inp = j;
  if (src.imported !== src.path) { importInp(j); src.imported = src.path; changed(); }
  if (SM.ensureSections(SH)) changed();
  FA.geoKey = key === null ? undefined : key;
  FA.geoStale = false;
  $("#fa-update").classList.remove("cm-stale");
  FA.inpInfo = `${src.name}: ${j.nodes} nodes, ${j.elements} elements, ${j.components.length} bod${j.components.length === 1 ? "y" : "ies"}` +
    (j.warnings.length ? "; " + j.warnings.join("; ") : "");
  $("#fa-info").textContent = FA.inpInfo;
  if (FA.three) FA.three.zoomed = false;
  draw(); renderAll();
}
/** Inputs of an .inp file into the document (once per file): materials, body materials, shell sections, node sets. */
function importInp(j) {
  const d = FA.doc;
  d.materials = d.materials || {};
  for (const [n, m] of Object.entries(j.materials || {})) if (!d.materials[n]) d.materials[n] = m;
  if (!d.default_material || !d.materials[d.default_material]) d.default_material = Object.keys(j.materials || {})[0] || d.default_material;
  d.bodies = d.bodies || {};
  for (const [id, b] of Object.entries(j.bodies || {})) d.bodies[id] = Object.assign({}, b, d.bodies[id] || {});
  d.shells = d.shells || {};
  for (const [id, s] of Object.entries(j.shells || {})) d.shells[id] = Object.assign({}, s, d.shells[id] || {});
  d.nsets = d.nsets || [];
  for (const n of j.nsets || []) if (!d.nsets.some(x => x.kind === "inp" && x.set === n)) d.nsets.push({ id: SH.nid("ns"), name: n, kind: "inp", set: n });
}
/** Import CalculiX .inp or Radioss .rad: a file dialog, then the file as the geometry source. */
async function chooseInp() {
  let p = "";
  try { p = await window.browse("open", "mesh", (FA.doc.source || {}).path || ""); } catch (e) { showErr(e); }
  if (!p) { refreshSources(); return; }
  FA.doc.source = { type: "inp", path: p, name: p.split(/[\\/]/).pop() };
  FA.mesh = null; FA.res = null; setStates();
  $("#fa-show").value = "model";
  changed(); await refreshSources(); loadGeometry();
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
    if (m.wire && m.wire.length) {                 // mesh file geometry: the element edges of the file
      e.wireGeo = new THREE.BufferGeometry();
      e.wireGeo.setAttribute("position", new THREE.Float32BufferAttribute(m.vertices.flat(), 3));
      e.wireGeo.setIndex(m.wire);
    }
    e.groups = addBodyGroups(e.geo, m);
  }
  return e;
}
/** Shell settings of a surface body of a component (doc.shells["<component>:<surface>"]). */
function shellCfg(cid, sid) { return (FA.doc.shells || {})[cid + ":" + sid] || {}; }
/** Whether a face of a component belongs to a surface body (a shell). */
function shellFace(ref) {
  const c = ref && ref.face !== undefined && compOf(ref.comp);
  const fb = c && c.mesh && c.mesh.face_body;
  return !!(fb && fb[ref.face] !== null && fb[ref.face] !== undefined);
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
  if (show !== "results" && !FA.job) $("#fa-info").textContent = (FA.doc.source || {}).type === "inp" && FA.inpInfo ? FA.inpInfo : FA.geo ? `${FA.geo.components.length} component(s)` + (nsk ? `, ${nsk} sketch(es)` : "") : "";
  if (show === "model" || !FA.mesh) drawModel(box);
  else drawMesh(box, show === "results" && FA.res ? $("#fa-state").value : null);
  if (FA.queryMarks) t.group.add(IF.marksGroup(FA.queryMarks, track));     // search results of the Input file page
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
  const refs = t => { const R = VS.targetRefs(SH, t); return [...R.faces, ...R.edges]; };
  for (const s of d.supports) for (const r of refs(s.target)) out.push([r, COLORS.support, sel.kind === "support" && sel.id === s.id]);
  for (const l of d.loads) for (const r of refs(l.target)) out.push([r, COLORS.load, sel.kind === "load" && sel.id === l.id]);
  for (const f of d.fasteners) for (const r of f.faces || []) if (r) out.push([r, COLORS.fastener, sel.kind === "fastener" && sel.id === f.id]);
  for (const m of d.members) for (const k of ["a", "b"]) if (m[k] && m[k].face) out.push([m[k].face, COLORS.connect, sel.kind === "member" && sel.id === m.id]);
  for (const p of d.points || []) for (const r of p.faces || []) out.push([r, 0x7048e8, sel.kind === "rp" && sel.id === p.id]);
  for (const c of d.contacts || []) {
    const on = sel.kind === "contact" && sel.id === c.id;
    for (const r of contactFaces(c, "master")) out.push([r, COLORS.master, on]);
    for (const r of contactFaces(c, "slave")) out.push([r, COLORS.slave, on]);
  }
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
    const m = c.mesh;
    if (m.vertices.length) {
      // surface bodies: shells drawn in their colour (translucent), shells set to off faint
      const mats = e.groups ? bodyMaterials(mat, c.surfaces, (k, sf) => ({ opacity: (shellCfg(c.id, sf.id).mode || "shell") === "off" ? 0.12 : 0.6 })) : mat;
      const mesh = new THREE.Mesh(e.geo, mats);
      mesh.userData = c.plate ? { comp: c.id, kind: "plate", id: c.id.slice(6) } : { comp: c.id };
      inner.add(mesh);
      t.pickables.push(mesh);
      if ($("#fa-edges").checked && e.wireGeo) inner.add(new THREE.LineSegments(e.wireGeo, new THREE.LineBasicMaterial({ color: 0x1d2125 })));
      if ($("#fa-edges").checked) inner.add(new THREE.LineSegments(e.edgeGeo, new THREE.LineBasicMaterial({ color: 0x1d2125 })));
      box.union(e.geo.boundingBox.clone().applyMatrix4(inner.matrix));
    }
    const vsel = VS.selectedVertices(SH, c.id);              // selected vertices
    if (vsel.length) { const o = VS.pointsObject(vsel, 0xe03131); track(o.geometry); inner.add(o); }
    for (const o of SM.overlays(SH, c.id)) {                // sections (colour), selected faces and edges
      const pos = [];
      if (o.edge !== undefined) {
        const ep = edgeSegments(m, o.edge);
        if (!ep.length) continue;
        const g = track(new THREE.BufferGeometry());
        g.setAttribute("position", new THREE.Float32BufferAttribute(ep, 3));
        const ls = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: o.color, depthTest: false }));
        ls.renderOrder = 7;
        inner.add(ls);
        continue;
      }
      m.triangles.forEach((tr, k) => { if (m.face_of_tri[k] === o.face) for (const v of tr) pos.push(...m.vertices[v]); });
      if (!pos.length) continue;
      const g = track(new THREE.BufferGeometry());
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      inner.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: o.color, transparent: true, opacity: o.opacity, side: THREE.DoubleSide,
                                                               polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 })));
    }
    for (const [ref, color, strong] of hl) {
      if (ref.comp !== c.id) continue;
      if (ref.edge !== undefined) {                          // an edge: thick line drawn over the faces
        const ep = edgeSegments(m, ref.edge);
        if (!ep.length) continue;
        const g = track(new THREE.BufferGeometry());
        g.setAttribute("position", new THREE.Float32BufferAttribute(ep, 3));
        const ls = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: strong ? COLORS.sel : color, depthTest: false }));
        ls.renderOrder = 8;
        inner.add(ls);
        const pg = track(new THREE.BufferGeometry());
        pg.setAttribute("position", new THREE.Float32BufferAttribute(ep, 3));
        const pm = new THREE.Points(pg, new THREE.PointsMaterial({ color: strong ? COLORS.sel : color, size: 5, sizeAttenuation: false, depthTest: false }));
        pm.renderOrder = 8;
        inner.add(pm);
        continue;
      }
      const pos = [];
      m.triangles.forEach((tr, k) => { if (m.face_of_tri[k] === ref.face) for (const v of tr) pos.push(...m.vertices[v]); });
      if (!pos.length) continue;
      const g = track(new THREE.BufferGeometry());
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      inner.add(new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: strong ? COLORS.sel : color, transparent: true, opacity: strong ? 0.6 : 0.3, side: THREE.DoubleSide,
                                                               polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
    }
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
  // reference points (violet) with dashed lines to the centres of their faces and edges; springs, joints, equations
  RH.pickables = FA.three.pickables;
  RP.drawConstraints(RH, FA.three.group, track, size);
  for (const rp of FA.doc.points || []) if (rp.xyz) box.expandByPoint(new THREE.Vector3(...rp.xyz));
  // supports at member ends and reference points: cubes; loads: arrows
  for (const sp of FA.doc.supports) {
    const p = targetPoint(sp.target);
    if (p && (sp.target.member !== undefined || sp.target.point !== undefined)) addBox(p, rad * 5, sel.kind === "support" && sel.id === sp.id ? COLORS.sel : COLORS.support, { kind: "support", id: sp.id });
  }
  if (!$("#fa-bcs").checked) { for (const l of FA.doc.loads) drawLoad(l, size, sel.kind === "load" && sel.id === l.id); return; }
  // supports and loads unchanged since the last mesh: at the mesh nodes; the others: supports at the points of their
  // edges and faces, loads as arrows at the face centre or along the edge or member
  const cur = meshedItems();
  for (const l of FA.doc.loads) if (!cur.loads.has(l.id)) drawLoad(l, size, sel.kind === "load" && sel.id === l.id);
  if (cur.sups.size || cur.loads.size) drawBcLoads(t.group, track, decoded(FA.mesh).pos, FA.mesh, size, { sel, only: cur.sups, onlyLoads: cur.loads });
  const gp = geometryGlyphs(cur.sups);
  for (const l of FA.doc.loads) if (l.type === "gravity" && !cur.loads.has(l.id)) gp.loads.push({ id: l.id, type: "gravity", value: l.value });
  if (gp.bcs.length || gp.loads.length) drawBcLoads(t.group, track, new Float32Array(gp.pos), gp, size, { sel, box });
}

/** Key of a support or load (target, type, components, value, node set definition) for meshedItems. */
function itemKey(x) {
  const t = x.target || null;
  const ns = t && t.nset !== undefined ? (FA.doc.nsets || []).find(n => n.id === t.nset) || null : null;
  return JSON.stringify([t, x.type || "", x.dofs || null, x.value === undefined ? null : x.value, ns]);
}
/** Ids of the supports and loads that have not changed since the mesh on show was made (their nodes are known). */
function meshedItems() {
  const out = { sups: new Set(), loads: new Set() };
  if (!FA.mesh || !FA.meshKeys) return out;
  const ok = (x, have) => FA.meshKeys[x.id] === itemKey(x) && have;
  for (const sp of FA.doc.supports) if (ok(sp, (FA.mesh.bcs || []).some(b => b.id === sp.id))) out.sups.add(sp.id);
  for (const l of FA.doc.loads) if (ok(l, hasNodeGlyphs(FA.mesh, l.id))) out.loads.add(l.id);
  return out;
}
/** About n points at equal spacing along the segments [x1, y1, z1, x2, y2, z2, ...] (end points included). */
function alongPolyline(ep, n) {
  const segs = [];
  let tot = 0;
  for (let k = 0; k + 5 < ep.length; k += 6) {
    const a = new THREE.Vector3(ep[k], ep[k + 1], ep[k + 2]), b = new THREE.Vector3(ep[k + 3], ep[k + 4], ep[k + 5]);
    segs.push([a, b]); tot += a.distanceTo(b);
  }
  if (!segs.length) return [];
  const step = tot / n, out = [segs[0][0].toArray()];
  let carry = 0;
  for (const [a, b] of segs) {
    const L = a.distanceTo(b);
    let s = step - carry;
    while (s <= L + 1e-9) { out.push(a.clone().lerp(b, L > 0 ? s / L : 0).toArray()); s += step; }
    carry = L - (s - step);
  }
  return out;
}
/** About n points on the triangles of face fi of a component view mesh (corners and interior points). */
function onTriangles(m, fi, n) {
  const tris = [];
  let area = 0;
  m.triangles.forEach((tr, k) => {
    if (m.face_of_tri[k] !== fi) return;
    const [a, b, c] = tr.map(v => new THREE.Vector3(...m.vertices[v]));
    const A = b.clone().sub(a).cross(c.clone().sub(a)).length() / 2;
    tris.push([a, b, c, A]); area += A;
  });
  const out = [];
  for (const [a, b, c, A] of tris) {
    const q = Math.max(1, Math.round(Math.sqrt(n * A / (area || 1))));      // subdivisions of the triangle sides
    for (let i = 0; i <= q; i++) for (let j = 0; i + j <= q; j++) {
      const u = i / q, v = j / q;
      out.push(a.clone().multiplyScalar(1 - u - v).addScaledVector(b, u).addScaledVector(c, v).toArray());
    }
  }
  const seen = new Set();                                    // shared triangle corners once
  return out.filter(p => { const k = p.map(x => x.toFixed(3)).join(","); if (seen.has(k)) return false; seen.add(k); return true; });
}
/** Supports on edges and faces of the geometry (not meshed): glyph data at up to 60 points of the edge or face. */
function geometryGlyphs(skip) {
  const pos = [], bcs = [];
  for (const sp of FA.doc.supports) {
    const tg = sp.target;
    if (skip.has(sp.id) || !tg) continue;
    const R = VS.targetRefs(SH, tg), pts = [];
    for (const r of [...R.edges, ...R.faces]) {
      const c = compOf(r.comp);
      if (!c || !c.mesh) continue;
      const M = matOf(c);
      const loc = r.edge !== undefined ? alongPolyline(edgeSegments(c.mesh, r.edge), 20) : onTriangles(c.mesh, r.face, 40);
      for (const q of loc) pts.push(new THREE.Vector3(...q).applyMatrix4(M).toArray());
    }
    if (!pts.length) continue;
    const [dofs, rdofs] = supportDofs(sp);
    const k = Math.max(1, Math.ceil(pts.length / 60)), nodes = [];
    for (let j = 0; j < pts.length; j += k) { nodes.push(pos.length / 3); pos.push(...pts[j]); }
    bcs.push({ id: sp.id, name: sp.name, nodes, dofs, rnodes: R.edges.length || R.faces.some(shellFace) ? nodes : [], rdofs,
               prescribed: sp.type === "displacement" && (sp.value || []).some(v => Number(v)) });
  }
  return { pos, bcs, loads: [] };
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
  if (VS.multiText(l.target) || (l.target && l.target.surface !== undefined)) {   // several faces or edges, a surface: each drawn
    const R = VS.targetRefs(SH, l.target);
    for (const r of [...R.faces, ...R.edges]) drawLoad(Object.assign({}, l, { target: r }), size, strong);
    return;
  }
  if (l.type === "line" && l.target && l.target.edge !== undefined) {   // edge: arrows along the edge polyline
    const c = compOf(l.target.comp);
    const ep = c && v ? edgeSegments(c.mesh, l.target.edge) : [];
    const M = c && matOf(c);
    for (const q of alongPolyline(ep, 8)) arrow(new THREE.Vector3(...q).applyMatrix4(M).toArray(), v, L * 0.5);
    return;
  }
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
  const c = l.target && l.target.comp !== undefined && l.target.face !== undefined ? compOf(l.target.comp) : null;
  const pts = c && c.mesh && l.type !== "moment" ? onTriangles(c.mesh, l.target.face, 16).map(q => new THREE.Vector3(...q).applyMatrix4(matOf(c)).toArray()) : [p];
  if (l.type === "pressure") {
    const r = faceRef(l.target);
    if (!r || !r.n) return;
    const n = r.kind === "plane" ? r.n : [0, 0, 1];
    for (const q of r.kind === "plane" ? pts : [p]) arrow(q, n.map(x => -x * Math.sign(Number(l.value) || 1)), L * 0.5);
    return;
  }
  if (v) for (const q of pts) arrow(q, v, pts.length > 1 ? L * 0.5 : L);
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
    p._d = { pos: b64(p.pos, Float32Array), tri: b64(p.tri, Uint32Array), edges: p.edges ? b64(p.edges, Uint32Array) : null, states: {},
             ids: p.node_ids ? b64(p.node_ids, Uint32Array) : null, triElem: p.tri_elem ? b64(p.tri_elem, Uint32Array) : null };
  }
  return p._d;
}
function stateData(p, st) {
  const d = decoded(p);
  if (!d.states[st]) d.states[st] = { U: b64(p.states[st].U, Float32Array), vm: b64(p.states[st].vm, Float32Array),
                                       lvm: p.states[st].lvm ? b64(p.states[st].lvm, Float32Array) : null,
                                       pe: p.states[st].pe ? b64(p.states[st].pe, Float32Array) : null };
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
  const d0 = decoded(p);
  const n = p.count;
  // bodies not shown (Results: Show column): their triangles and element edges left out, the range from the others
  const hide = FA.bodyHide && FA.bodyHide.size && (p.bodies || []).length ? FA.bodyHide : null;
  let d = d0, bodies = p.bodies || [];
  if (hide) {
    const keep = bodies.filter(b => !hide.has(b.id)), nt = keep.reduce((a, b) => a + b.count, 0);
    const tri = new Uint32Array(3 * nt), used = new Uint8Array(n);
    let o = 0;
    bodies = keep.map(b => { const r = Object.assign({}, b, { start: o / 3 }); tri.set(d0.tri.subarray(3 * b.start, 3 * (b.start + b.count)), o); o += 3 * b.count; return r; });
    for (const v of tri) used[v] = 1;
    const ed = elemEdges(d0), edges = [];
    for (let k = 0; k < ed.length; k += 2) if (used[ed[k]] && used[ed[k + 1]]) edges.push(ed[k], ed[k + 1]);
    d = Object.assign({}, d0, { tri, edges });
  }
  const pos = new Float32Array(d.pos);
  let vals = null, lo = 0, hi = 1, scale = 0, lvm = null;
  if (modeResult() && $("#fa-field").value === "vm") $("#fa-field").value = "u";
  if ($("#fa-field").value === "peeq" && !(st && p.states && p.states[st] && p.states[st].pe)) $("#fa-field").value = "vm";
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
      vals[i] = field === "vm" ? s.vm[i] : field === "peeq" ? s.pe[i] : field === "u" ? Math.hypot(ux, uy, uz) : field === "ux" ? ux : field === "uy" ? uy : uz;
    }
    // range of the nodes of the body faces only (member nodes have no stress)
    lo = Infinity; hi = -Infinity;
    for (let k = 0; k < d.tri.length; k++) { const v = vals[d.tri[k]]; if (v < lo) lo = v; if (v > hi) hi = v; }
    lvm = s.lvm;
    let k = 0;
    for (const ln of hide ? [] : p.lines) for (const [a, b] of ln.segs) {
      if (field !== "vm") for (const q of [a, b]) { lo = Math.min(lo, vals[q]); hi = Math.max(hi, vals[q]); }
      else if (lvm && ln.kind !== "fastener") for (const v of [lvm[k], lvm[k + 1]]) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      k += 2;
    }
    if (!isFinite(lo)) { lo = 0; hi = 0; }
    legend(field, lo, hi, scale, st);
    $("#fa-info").textContent = modeResult() ? `${stateName(st)}: mode shape (largest displacement 1), scale ${ffmt(scale, 3)}`
      : `${stateName(st)}: max |u| ${ffmt(p.states[st].umax)} mm, max von Mises ${ffmt(p.states[st].vmmax)} MPa, scale ${ffmt(scale, 3)}`;
  }
  // Shell thickness: shell bodies and sections as slabs of their thickness and offset
  let gpos = pos, gtri = d.tri, gvals = vals, gedges = null, vsrc = null;
  const shells = bodies.filter(b => b.t > 0 && b.count > 0);
  if ($("#fa-thick").checked && shells.length) {
    const groups = shells.map(b => ({ tris: Array.from({ length: b.count }, (_, i) => b.start + i), t: b.t, off: b.offset }));
    const th = thicken(pos, d.tri, groups, elemEdges(d));
    gpos = th.pos; gtri = th.tri; gedges = th.edges; vsrc = th.vsrc;
    if (vals) gvals = Float32Array.from(th.vsrc, v => vals[v]);
  }
  const g = track(new THREE.BufferGeometry());
  g.setAttribute("position", new THREE.BufferAttribute(gpos, 3));
  g.setIndex(new THREE.BufferAttribute(gtri, 1));
  g.computeVertexNormals();
  let mat;
  if (vals) {
    const gn = gpos.length / 3;
    const col = new Float32Array(3 * gn);
    const span = hi - lo || 1;
    for (let i = 0; i < gn; i++) { const c = bandColor((gvals[i] - lo) / span); col[3 * i] = c.r; col[3 * i + 1] = c.g; col[3 * i + 2] = c.b; }
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    mat = new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  } else {
    mat = new THREE.MeshStandardMaterial({ color: 0xb8c2cc, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  }
  const mesh = new THREE.Mesh(g, mat);
  mesh.userData = { kind: "mesh", vsrc };
  t.group.add(mesh);
  if (st) drawProbes(t, pos);
  // mesh selection (viewsel.js: nodes, elements) on the undeformed mesh without shell thickness
  FA.meshSel = null;
  if (!st && gtri === d.tri && d0.ids && d0.triElem) {
    let te = d0.triElem;
    if (hide) { te = new Uint32Array(d.tri.length / 3); let o = 0; for (const b of p.bodies || []) if (!hide.has(b.id)) { te.set(d0.triElem.subarray(b.start, b.start + b.count), o); o += b.count; } }
    FA.meshSel = { pos: d.pos, ids: d0.ids, tri: d.tri, triElem: te };
    for (const o of VS.meshOverlays(SH)) { track(o.geometry); t.group.add(o); }
  }
  if ($("#fa-edges").checked && (!vals || d.tri.length < 600000)) {
    const eg = track(new THREE.BufferGeometry());
    const idx = gedges || elemEdges(d);
    eg.setAttribute("position", new THREE.BufferAttribute(gpos, 3));
    eg.setIndex(idx);
    t.group.add(new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0x343a40, transparent: true, opacity: vals ? 0.25 : 0.6 })));
  }
  // members and fasteners (deformed): tubes coloured with the field (members: stress of the member table for von
  // Mises), dark without results; element ends as points (the member mesh)
  const lp = [], lc = [], ends = [];
  const span = hi - lo || 1;
  let k = 0;
  for (const ln of hide ? [] : p.lines) for (const [a, b] of ln.segs) {
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
  if ($("#fa-bcs").checked) {                               // supports and loads at the nodes
    const bb = new THREE.Box3().setFromArray(d.pos);
    const size = Math.max(...bb.getSize(new THREE.Vector3()).toArray(), 1);
    RH.pickables = null;
    RP.drawConstraints(RH, t.group, track, size);
    drawBcLoads(t.group, track, pos, p, size, { sel: FA.sel });
    const sel = FA.sel || {};
    for (const l of FA.doc.loads) if (l.type === "line" && l.target && l.target.member !== undefined && !hasNodeGlyphs(p, l.id)) drawLoad(l, size, sel.kind === "load" && sel.id === l.id);
  }
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
  const steps = (FA.res && FA.res.summary && FA.res.summary.steps) || [];
  if (STATE_NAME[st]) return st === "total" && steps.length > 1 ? "End of the last step" : FA.res && FA.res.increments && st === "total" ? "End of the step" : STATE_NAME[st];
  const sk = /^s(\d+)$/.exec(st || "");
  if (sk) return `End of step ${sk[1]}: ${(steps[+sk[1] - 1] || {}).name || ""}`;
  const ii = /^i(\d+)$/.exec(st || "");
  if (ii && FA.res && FA.res.increments) {
    const inc = FA.res.increments.find(x => x.state === st);
    const sn = inc && inc.user_step && steps.length > 1 ? (steps[inc.user_step - 1] || {}).name + ", " : "";
    if (inc) return `Increment ${ii[1]}: ${inc.preload ? "preload step, " : ""}${sn}time ${ffmt(inc.time, 4)}`;
  }
  const m = /^m(\d+)$/.exec(st || "");
  const md = m && FA.res && FA.res.modes ? FA.res.modes[+m[1] - 1] : null;
  if (!md) return st;
  return FA.res.atype === "modal" ? `Mode ${md.mode}: ${ffmt(md.value, 5)} Hz` : `Mode ${md.mode}: factor ${ffmt(md.value, 5)}`;
}
function modeResult() { return !!(FA.res && FA.res.atype && FA.res.atype !== "static"); }
const FIELD_NAME = { vm: "von Mises (MPa)", u: "|u| (mm)", ux: "ux (mm)", uy: "uy (mm)", uz: "uz (mm)", peeq: "PEEQ (equivalent plastic strain)" };
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
  if (!opts.snap && $("#fa-show").value !== "model") { $("#fa-show").value = "model"; draw(); }
  FA.pick = Object.assign({ text, cb }, opts);
  status(text + " (Esc cancels)");
  renderAll();
}
function endPick() { const p = FA.pick; FA.pick = null; if (p && p.onCancel) p.onCancel(); renderAll(); draw(); }

function clickView(e) {
  const t = FA.three;
  if (FA.probeMode && $("#fa-show").value === "results" && FA.res) { probeClick(e); return; }
  const hits = rayAt(e).intersectObjects(t.pickables, false);
  if (!FA.pick && VS.click(SH, e)) return;                  // selection (viewsel.js): faces, edges, bodies, points
  if (FA.pick) {
    const done = hit => { const cb = FA.pick.cb; FA.pick = null; cb(hit); changed(); renderAll(); draw(); schedulePlates(); };
    if (FA.pick.snap) { const sp = snapAt(e); if (sp) done({ xyz: sp.xyz, normal: sp.normal || null, face: sp.face || null, kind: sp.kind, shift: e.shiftKey }); return; }
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
    if (FA.pick.edge) {
      const eg = edgeUnder(e);
      if (eg) return done({ edge: eg });
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
  if (!end && !(ud.kind && ud.id) && VS.quickFace(SH, e)) { FA.sel = null; return; }   // a plain click selects or deselects the face
  FA.sel = end ? { kind: "member", id: end.member, end: end.end } : ud.kind && ud.id ? { kind: ud.kind, id: ud.id } : null;
  if (JSON.stringify(FA.sel) === prev) return;
  if (FA.sel && FA.sel.end) status(targetText({ member: FA.sel.id, end: FA.sel.end }) + " selected: Support or Load applies to it");
  renderAll(); draw();
}

// ------------------------------------------------------------------ panels

/** Optional cards (Panels row): shown or hidden per analysis (doc.panels_hidden). */
const OPT_CARDS = [["sections", "Sections", "sections"], ["surfaces", "Surfaces", "surfaces"], ["nsets", "Node sets", "nsets"], ["members", "Members", "members"],
                   ["plates", "Plates", "plates"], ["fasts", "Fasteners", "fasteners"], ["rps", "Reference points", "points"],
                   ["springs", "Springs", "springs"], ["joints", "Joints", "joints"], ["eqs", "Equations", "equations"],
                   ["contacts", "Contact", "contacts"]];
function renderPanels() {
  const d = FA.doc;
  PN.renderToggles($("#fa-panels"), d, OPT_CARDS.map(([k, l, f]) => ({ key: k, label: l, count: (d[f] || []).length })), () => { changed(); renderPanels(); });
  for (const [k] of OPT_CARDS) { const c = $("#fa-" + k + "-card"); if (c) c.hidden = PN.isHidden(d, k); }
}
function renderAll() {
  if (!FA.doc) return;
  installTree();
  renderPanels();
  renderInpFile(); renderSettings(); renderMats(); renderBodies(); renderSections(); renderNsets(); renderMembers(); renderPlates(); renderFasts(); renderRps(); renderCons(); renderContacts(); renderSteps(); renderSups(); renderLoads(); renderAmps(); renderIvel(); renderHist(); renderResults();
  // an item selected in the view or a list: its page in the property pane
  const sk = FA.sel ? FA.sel.kind + ":" + FA.sel.id : "";
  if (sk && sk !== FA.treeSel && FA.tree) FA.tree.reveal({ member: "members", plate: "plates", fastener: "fasts", support: "sups", load: "loads", contact: "contacts" }[FA.sel.kind]);
  FA.treeSel = sk;
  if (FA.tree) FA.tree.render();
}

/** Leaves of the model tree: the items of a list of the document [{id, label}]. */
function treeItems(field) { return ((FA.doc || {})[field] || []).map(x => ({ id: String(x.id), label: x.name || String(x.id) })); }
/** A body, the faces of a section or surface, or a reference point picked from the tree: selected in the view. */
function treePickView(field, id) {
  const d = FA.doc || {};
  if (field === "bodies") VS.show(SH, { bodies: [id] });
  else if (field === "points") VS.show(SH, { point: id });
  else { const x = (d[field] || []).find(q => String(q.id) === id); if (x) VS.show(SH, { faces: x.faces || [] }); }
  draw();
}
/** Bodies of the geometry as tree leaves: solids and surface bodies (shellmodel bodyList without the sections). */
function treeBodies() { return FA.geo ? SM.bodyList(SH).filter(([v]) => !v.startsWith("sec:")).map(([v, t]) => ({ id: v, label: t })) : []; }
/** Model tree of the panel (paneltree.js): the cards as pages. */
function installTree() {
  if (FA.tree) return;
  const card = k => () => [$("#fa-" + k + "-card")];
  const KIND = { members: "member", plates: "plate", fasteners: "fastener", supports: "support", loads: "load", contacts: "contact" };
  const pickOf = field => KIND[field] ? id => { FA.sel = { kind: KIND[field], id: FA.doc[field].find(x => String(x.id) === id).id }; renderAll(); draw(); }
    : ["sections", "surfaces", "points"].includes(field) ? id => treePickView(field, id) : null;
  const n = (k, label, field) => ({ id: k, label, els: card(k), count: field ? () => (FA.doc ? (FA.doc[field] || []).length : 0) : null,
                                     off: () => !!FA.doc && PN.isHidden(FA.doc, k), items: field ? () => treeItems(field) : null, pick: field ? pickOf(field) : null });
  const ATYPE = { static: "static", modal: "modal", buckling: "buckling" };
  FA.tree = TP.install({ key: "fa", panel: $("#fa-panel"), body: $("#fa-panel").parentElement, title: "Model tree",
    root: { id: "all", label: "Analysis (CalculiX)", els: () => [$("#fa-panels")], children: [
      { id: "settings", label: "Settings", els: card("settings") },
      { id: "model", label: "Model", children: [
        { id: "inpfile", label: "Input file", els: card("inpfile") },
        { id: "mats", label: "Materials", els: card("mats"), count: () => Object.keys((FA.doc || {}).materials || {}).length,
          items: () => Object.keys((FA.doc || {}).materials || {}).map(m => ({ id: m, label: m })) },
        { id: "bodies", label: "Bodies", els: card("bodies"), count: () => treeBodies().length, items: treeBodies, pick: id => treePickView("bodies", id) },
        n("sections", "Sections", "sections"), n("surfaces", "Surfaces", "surfaces"), n("nsets", "Node sets", "nsets"),
        n("rps", "Reference points", "points"),
        { id: "structure", label: "Members and plates", children: [n("members", "Members", "members"), n("plates", "Plates", "plates"), n("fasts", "Fasteners", "fasteners")] },
        { id: "constraints", label: "Constraints", children: [n("springs", "Springs", "springs"), n("joints", "Joints", "joints"), n("eqs", "Equations", "equations")] },
        n("contacts", "Contact", "contacts")] },
      { id: "step", label: () => (FA.doc || {}).analysis_type && FA.doc.analysis_type !== "static" ? "Step (" + ATYPE[FA.doc.analysis_type] + ")" : "Steps", children: [
        { id: "steps", label: "Step list", els: card("steps"), count: () => (((FA.doc || {}).steps || []).length || 1), items: () => stepList().map(st => ({ id: st.id, label: st.name + " (" + st.kind + ")" })) },
        n("sups", "Supports", "supports"), n("loads", "Loads", "loads"),
        { id: "amps", label: "Amplitudes", els: card("amps"), count: () => ((FA.doc || {}).amplitudes || []).length, items: () => treeItems("amplitudes") },
        { id: "ivel", label: "Initial velocities", els: card("ivel"), count: () => ((FA.doc || {}).initial_velocities || []).length, items: () => treeItems("initial_velocities") },
        { id: "hist", label: "History output", els: card("hist"), count: () => ((FA.doc || {}).history || []).length, items: () => treeItems("history") }] },
      { id: "results", label: "Results", els: card("results") }] } });
}

/** Material drop-downs: model materials with their library entry or law and values, library entries (choosing one
 *  adds a model material, addLibraryMaterial). */
function matOptions(cur) {
  loadMatlib();
  return MS.matOptions(FA.doc, cur || "", (FA.matlib || []).map(x => x.name));
}
function loadMatlib() {
  if (FA.matlib) return;
  FA.matlib = [];
  api("/api/analysis/material_library").then(r => r.json()).then(j => { FA.matlib = j; if (FA.doc) renderAll(); }).catch(() => {});
}
function addLibraryMaterial(entry) {
  const lib = (FA.matlib || []).find(x => x.name === entry);
  if (!lib) return null;
  const n = MS.nameForLibrary(FA.doc, entry);
  const m = { library: lib.name, E: lib.E, nu: lib.nu, rho: Math.round(lib.rho * 1000) / 1000 };
  if (lib.plastic.length) { m.plastic = lib.plastic.map(r => r.slice()); m.law = "plastic"; m.hardening = "isotropic"; }
  FA.doc.materials = FA.doc.materials || {};
  FA.doc.materials[n] = m;
  return n;
}

const MESH_STRATEGIES = [["tet", "Tetrahedra (free)"], ["hex", "Hexahedra, structured (block cells)"], ["hexsub", "Hexahedra by subdivision"]];
const TET_TYPES = [["C3D10", "C3D10 (second order)"], ["C3D4", "C3D4 (first order)"]];
const HEX_TYPES = [["C3D8I", "C3D8I (incompatible modes)"], ["C3D8", "C3D8 (full integration)"], ["C3D8R", "C3D8R (reduced integration)"],
                   ["C3D20", "C3D20 (second order)"], ["C3D20R", "C3D20R (second order, reduced)"]];
const ALGOS = [["delaunay", "Delaunay"], ["frontal", "Frontal"], ["hxt", "HXT (parallel Delaunay)"]];
const SHELL_TYPES = [["S4", "S4 (incompatible modes)"], ["S8R", "S8R (second order)"], ["S3", "S3 (triangles)"]];
const SHELL_ALGOS = [["quasi", "Quasi-structured quadrangles"], ["frontal", "Frontal-Delaunay for quadrangles"], ["delaunay", "Delaunay, recombined"], ["tri", "Triangles only"]];
const SHELL_POS = [["mid", "mid"], ["positive", "positive"], ["negative", "negative"]];
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
    `<label class="check" title="Structured quadrangles on axis-aligned rectangles of the shells (step2shell): the break coordinates of all curve ends form an interval grid; each interval gets ceil(interval / size) divisions"><input type="checkbox" id="fs-shstruct"${m.shell_structured === false ? "" : " checked"}> Structured quadrangles on axis-aligned rectangles</label>` +
    `<div class="grid2"><label title="Lowest number of elements between two break coordinates of the structured mesh">Min divisions per interval<input type="text" class="numf" id="fs-shmindiv" value="${m.shell_min_div || ""}" placeholder="1"></label>` +
    `<label title="local: a curve takes the smallest size of the shells and sections of its faces (a face next to a finer one on one side only is meshed free). along the grid: every interval takes the smallest size of the curves spanning it, so all rectangles stay structured">Section sizes<select id="fs-shsizemode">${optList([["local", "local, free transition"], ["grid", "along the grid, all structured"]], m.shell_size_mode || "local")}</select></label></div>` +
    `<label title="Tolerance of the general fuse of the shells (mm): faces and edges closer than this are joined. 0: exact">Fuzzy (mm)<input type="text" class="numf" id="fs-fuzzy" value="${m.fuzzy || ""}" placeholder="0"></label>` +
    `<div class="grid2"><label title="Element type of the shells (surface bodies). S4: CalculiX expands it to C3D8I elements. Triangles left by the quadrangle mesh are S3 (S6 with S8R)">Shell elements<select id="fs-shtype">${optList(SHELL_TYPES, m.shell_type || "S4")}</select></label>` +
    `<label title="gmsh surface algorithm of the shells">Shell mesh<select id="fs-shalgo">${optList(SHELL_ALGOS, m.shell_algorithm || "quasi")}</select></label></div>` +
    `<p class="hint">Structured hexahedra need bodies whose cells are blocks (6 faces with 4 edges each) or prisms (Part tab, Partition). Bodies of different strategies, and plates, are tied where they touch.</p>` + `<div id="fs-refine"></div>`;
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
  if ($("#fs-shtype")) $("#fs-shtype").onchange = () => { m().shell_type = $("#fs-shtype").value; changed(); renderBodies(); renderSections(); };
  if ($("#fs-shalgo")) $("#fs-shalgo").onchange = () => { m().shell_algorithm = $("#fs-shalgo").value; changed(); };
  if ($("#fs-shstruct")) $("#fs-shstruct").onchange = () => { if ($("#fs-shstruct").checked) delete m().shell_structured; else m().shell_structured = false; changed(); };
  if ($("#fs-shsizemode")) $("#fs-shsizemode").onchange = () => { m().shell_size_mode = $("#fs-shsizemode").value; changed(); };
  if ($("#fs-shmindiv")) $("#fs-shmindiv").onchange = () => { const v = Math.round(fnum($("#fs-shmindiv").value)); if (v >= 1) m().shell_min_div = v; else delete m().shell_min_div; changed(); };
  if ($("#fs-fuzzy")) $("#fs-fuzzy").onchange = () => { const v = fnum($("#fs-fuzzy").value); if (v > 0) m().fuzzy = v; else delete m().fuzzy; changed(); };
  if ($("#fs-refine")) SM.renderRefine(SH, $("#fs-refine"));
}

/** Width of the analysis panel: drag of the bar between the view and the panel, kept in the browser (localStorage). */
function bindPanelSplit() {
  TP.bindSplit($("#fa-split"), $("#fa-panel"), $("#fa-panel").parentElement, "fa_panel_w");
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
    `<label class="check" title="Touching solid bodies share their nodes; plates are tied to the faces they touch. Bodies of a contact pair are meshed apart"><input type="checkbox" id="fs-bonded"${d.bonded !== false ? " checked" : ""}> Bonded contact between touching bodies</label>` +
    nonlinearHtml(d);
  $("#fs-ccx").onchange = async () => {
    try { FA.solver = await (await api("/api/analysis/solver", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: $("#fs-ccx").value }) })).json(); } catch (e) { showErr(e); }
    renderSettings();
  };
  bindMeshSettings(d);
  $("#fs-defmat").onchange = () => { d.default_material = $("#fs-defmat").value; changed(); renderAll(); };
  $("#fs-bonded").onchange = () => { d.bonded = $("#fs-bonded").checked; changed(); };
  bindNonlinear(d);
  $("#fs-atype").onchange = () => { d.analysis_type = $("#fs-atype").value; changed(); renderSettings(); };
  $("#fs-modes").onchange = () => { const v = Math.round(fnum($("#fs-modes").value)); if (isFinite(v) && v >= 1 && v <= 100) { d.modes = v; changed(); } else { status("Number of modes: 1 to 100"); renderSettings(); } };
}

const LAWS = [["elastic", "linear elastic"], ["plastic:isotropic", "plastic, isotropic hardening"], ["plastic:kinematic", "plastic, kinematic hardening"],
              ["hyper:neohooke", "hyperelastic Neo-Hooke"], ["hyper:mooney", "hyperelastic Mooney-Rivlin"]];
const lawOf = m => (m.law || "elastic") === "plastic" ? "plastic:" + (m.hardening || "isotropic") : (m.law || "elastic") === "hyper" ? "hyper:" + (m.hyper || "neohooke") : "elastic";
/** Materials: name, E, nu, rho, law (elastic, plastic with isotropic or kinematic hardening, hyperelastic), the
 *  library material; per plastic material the hardening table, per hyperelastic material its constants. */
/** Nonlinear step settings (doc.nonlinear): large deformation, increments, output frequency. */
function nlActive(d) {
  const nl = d.nonlinear || {};
  return !!(nl.nlgeom || (d.contacts || []).some(c => (c.type || "surface") !== "tied") || Object.values(d.materials || {}).some(m => (m.law || "elastic") !== "elastic"));
}
function nonlinearHtml(d) {
  const nl = d.nonlinear || {};
  const v = k => nl[k] === undefined || nl[k] === null ? "" : nl[k];
  return `<p class="hint" style="margin:8px 0 2px"><strong>Nonlinear step</strong> ${nlActive(d) ? "(used: contact, plastic or hyperelastic material, or large deformation)" : "(not used: linear static)"}</p>` +
    `<label class="check" title="NLGEOM: equilibrium in the deformed geometry (always on with a hyperelastic material)"><input type="checkbox" id="fs-nlgeom"${nl.nlgeom ? " checked" : ""}> Large deformation (NLGEOM)</label>` +
    `<div class="grid2"><label title="First increment as a fraction of the step (step time 1)">Initial increment<input type="text" class="numf" data-nl="inc0" value="${v("inc0")}" placeholder="0.1"></label>` +
    `<label title="Largest increment (fraction of the step)">Max increment<input type="text" class="numf" data-nl="incmax" value="${v("incmax")}" placeholder="0.25"></label></div>` +
    `<div class="grid2"><label title="Smallest increment before the solve stops">Min increment<input type="text" class="numf" data-nl="incmin" value="${v("incmin")}" placeholder="1e-5"></label>` +
    `<label title="Largest number of increments of the step">Max increments<input type="text" class="numf" data-nl="maxinc" value="${v("maxinc")}" placeholder="100"></label></div>` +
    `<label title="Results written every n increments (each written increment is a result state)">Output every n increments<input type="text" class="numf" data-nl="every" value="${v("every")}" placeholder="1"></label>` +
    `<p class="hint">Loads and prescribed displacements are ramped linearly over the step. Beams and fasteners (U1 elements) are linear only.</p>`;
}
function bindNonlinear(d) {
  const nl = () => (d.nonlinear = d.nonlinear || {});
  $("#fs-nlgeom").onchange = () => { nl().nlgeom = $("#fs-nlgeom").checked; changed(); renderSettings(); };
  document.querySelectorAll("#fa-settings [data-nl]").forEach(el => el.onchange = () => {
    const k = el.dataset.nl, raw = el.value.trim(), v = fnum(raw);
    if (raw === "") delete nl()[k]; else if (v > 0) nl()[k] = (k === "maxinc" || k === "every") ? Math.round(v) : v; else { status("A positive number", true); el.value = nl()[k] ?? ""; return; }
    changed();
  });
}

function renderMats() {
  const d = FA.doc;
  loadMatlib();
  const libOpts = cur => `<option value="">(none)</option>` + FA.matlib.map(x => `<option value="${fesc(x.name)}"${x.name === cur ? " selected" : ""}>${fesc(x.name)}</option>`).join("");
  const rows = Object.entries(d.materials).map(([n, m]) => {
    const lib = !!m.library;
    return `<tr data-n="${fesc(n)}"><td><input type="text" data-k="name" value="${fesc(n)}"></td>` +
      `<td><input type="text" class="numf" data-k="E" value="${m.E}"${lib ? " disabled" : ""}></td><td><input type="text" class="numf" data-k="nu" value="${m.nu}"${lib ? " disabled" : ""}></td>` +
      `<td><input type="text" class="numf" data-k="rho" value="${m.rho || ""}"${lib ? " disabled" : ""}></td>` +
      `<td><select data-k="law">${optList(LAWS, lawOf(m))}</select></td>` +
      `<td><select data-k="library" title="Material library: E, nu, rho and the hardening curve">${libOpts(m.library || "")}</select></td>` +
      `<td><button type="button" class="small" data-k="del" title="Delete">&#10005;</button></td></tr>`;
  }).join("");
  let h = `<div class="fa-wide"><table class="pc-table"><tr><th>Name</th><th>E (MPa)</th><th>nu</th><th>rho (kg/m^3)</th><th>Law</th><th>Library</th><th></th></tr>${rows}</table></div>` +
    `<button type="button" class="small" id="fm-add">Add material</button>`;
  for (const [n, m] of Object.entries(d.materials)) {
    const law = m.law || "elastic";
    if (law === "plastic") {
      const tbl = (m.plastic || []).map(r => `${r[0]}, ${r[1]}`).join("\n");
      h += `<div class="fa-props" data-mn="${fesc(n)}"><p class="hint" style="margin:6px 0 2px"><strong>${fesc(n)}</strong>: hardening table, one row per line: yield stress (MPa), plastic strain; the first row at plastic strain 0` +
        (m.library ? " (from the library)" : "") + `</p><textarea data-mk="plastic" rows="${Math.min(10, Math.max(3, (m.plastic || []).length + 1))}"${m.library ? " disabled" : ""}>${fesc(tbl)}</textarea></div>`;
    } else if (law === "hyper") {
      const moon = (m.hyper || "neohooke") === "mooney";
      h += `<div class="fa-props" data-mn="${fesc(n)}"><p class="hint" style="margin:6px 0 2px"><strong>${fesc(n)}</strong>: ${moon ? "Mooney-Rivlin" : "Neo-Hooke"} constants (large deformation is used)</p>` +
        `<div class="grid2"><label>C10 (MPa)<input type="text" class="numf" data-mk="C10" value="${m.C10 ?? ""}"></label>` +
        (moon ? `<label>C01 (MPa)<input type="text" class="numf" data-mk="C01" value="${m.C01 ?? ""}"></label>` : "") +
        `<label title="Compressibility: bulk modulus K = 2 / D1">D1 (1/MPa)<input type="text" class="numf" data-mk="D1" value="${m.D1 ?? ""}"></label></div></div>`;
    }
  }
  h += `<h3 class="xp-h">Curve</h3><div id="fa-matcurve"></div>`;
  $("#fa-mats").innerHTML = h;
  FA.matPlot = FA.matPlot || {};
  CV.renderMaterials($("#fa-matcurve"), Object.entries(d.materials).map(([n, m]) => CV.materialEntry(n, m, m.library)), FA.matPlot,
    { empty: "No plastic or hyperelastic material (Law)." });
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
        for (const b of Object.values(d.shells || {})) if (b.material === n) b.material = nn;
        for (const b of d.sections || []) if (b.material === n) b.material = nn;
      } else m[k] = fnum(inp.value) || 0;
      changed(); renderAll();
    });
    tr.querySelector("[data-k=law]").onchange = e => {
      const m = d.materials[n], [law, sub] = e.target.value.split(":");
      m.law = law;
      if (law === "plastic") { m.hardening = sub; if (!(m.plastic || []).length) m.plastic = [[250, 0], [300, 0.1]]; }
      if (law === "hyper") { m.hyper = sub; if (m.C10 === undefined) { m.C10 = 0.5; m.D1 = 0.1; } }
      if (law === "elastic") { delete m.hardening; delete m.hyper; }
      changed(); renderMats(); renderSettings();
    };
    tr.querySelector("[data-k=library]").onchange = e => {
      const m = d.materials[n], lib = FA.matlib.find(x => x.name === e.target.value);
      if (!lib) delete m.library;
      else {
        m.library = lib.name; m.E = lib.E; m.nu = lib.nu; m.rho = Math.round(lib.rho * 1000) / 1000;
        if (lib.plastic.length) { m.plastic = lib.plastic.map(r => r.slice()); if ((m.law || "elastic") === "elastic") { m.law = "plastic"; m.hardening = "isotropic"; } }
      }
      changed(); renderMats(); renderSettings();
    };
    tr.querySelector("[data-k=del]").onclick = () => {
      if (Object.keys(d.materials).length < 2) return;
      delete d.materials[n];
      if (d.default_material === n) d.default_material = Object.keys(d.materials)[0];
      changed(); renderAll();
    };
  });
  $("#fa-mats").querySelectorAll("[data-mn]").forEach(div => {
    const m = d.materials[div.dataset.mn];
    div.querySelectorAll("[data-mk]").forEach(el => el.onchange = () => {
      const k = el.dataset.mk;
      if (k === "plastic") {
        const rows = el.value.split(/\n/).map(l => l.trim()).filter(Boolean).map(l => l.split(/[,;\s]+/).map(fnum));
        if (rows.some(r => r.length < 2 || !isFinite(r[0]) || !isFinite(r[1]))) { status("Hardening table: two numbers per line (stress, plastic strain)", true); return; }
        rows.sort((a, b) => a[1] - b[1]);
        if (rows[0][1] !== 0) { status("Hardening table: the first row is at plastic strain 0 (the yield stress)", true); return; }
        m.plastic = rows.map(r => [r[0], r[1]]);
      } else { const v = fnum(el.value); if (isFinite(v)) m[k] = v; else delete m[k]; }
      changed(); status("Material " + div.dataset.mn + " changed"); renderMats();
    });
  });
  $("#fm-add").onclick = () => { let k = 1; while (d.materials["Material " + k]) k++; d.materials["Material " + k] = { E: 210000, nu: 0.3, rho: 7850 }; changed(); renderAll(); };
}

const LAYERS_TIP = "S8R shell elements: *SHELL SECTION, COMPOSITE with this number of layers of t / n of the material (integration points through the thickness per layer). Empty: 1 layer";
const s8r = () => ((FA.doc.mesh || {}).shell_type || "S4") === "S8R";
function renderBodies() {
  const d = FA.doc;
  const all = (FA.asm && FA.asm.components) || [];
  if (!all.length) { $("#fa-bodies").innerHTML = '<p class="hint">No bodies: Geometry is (none).</p>'; return; }
  const comps = all.filter(c => !sketchOnly(c.id));
  if (!comps.length) { $("#fa-bodies").innerHTML = `<p class="hint">No bodies: ${all.map(c => fesc(c.name)).join(", ")} has sketches only (members and plates snap to the sketch points).</p>`; return; }
  const defStrat = ((d.mesh || {}).strategy) || "tet";
  const stratShort = { tet: "tet", hex: "hex", hexsub: "hex sub" };
  const hasSolid = c => { const g = compOf(c.id); const m = g && g.mesh; return !m || (m.triangles.length > 0 && (!m.face_body || m.face_body.some(v => v === null || v === undefined))); };
  const solids = comps.filter(hasSolid);
  const shells = [];
  for (const c of comps) { const g = compOf(c.id); for (const sf of (g && g.surfaces) || []) shells.push([c, sf]); }
  $("#fa-bodies").innerHTML = (solids.length ? `<table class="pc-table"><tr><th>Body</th><th>Model</th><th>Mesh</th><th>Material</th><th>Size (mm)</th></tr>` + solids.map(c => {
    const b = d.bodies[c.id] || {};
    const strat = `<select data-k="strategy"${b.mode === "plate" || b.mode === "off" ? " disabled" : ""}><option value="">(${stratShort[defStrat]})</option>` +
      ["tet", "hex", "hexsub"].map(k => `<option value="${k}"${b.strategy === k ? " selected" : ""}>${stratShort[k]}</option>`).join("") + `</select>`;
    return `<tr data-id="${fesc(c.id)}"><td>${fesc(c.name)}</td><td><select data-k="mode">${["solid", "plate", "off"].map(m => `<option${(b.mode || "solid") === m ? " selected" : ""}>${m}</option>`).join("")}</select></td>` +
      `<td>${strat}</td><td><select data-k="material">${matOptions(b.material)}</select></td><td><input type="text" class="numf" data-k="size" value="${b.size || ""}" placeholder="auto"></td></tr>`;
  }).join("") + `</table><p class="hint">solid: meshed with the strategy in Mesh (tet: tetrahedra; hex: structured hexahedra; hex sub: hexahedra by subdivision; in brackets: the default of Settings); plate: prismatic part meshed through the thickness (C3D8I); off: left out.</p>` : "") +
    (shells.length ? `<p class="hint">Shells: ${shells.length} surface body(ies), meshed with shell elements (Shell elements in Settings). Model, thickness, position, material, element size and layers are set in Sections; touching shells share their nodes (bonded), shells on solid faces are tied to them.</p>` : "");
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
  const st = SM.surfaceText(SH, tg);
  if (st) return st;
  const mt = VS.multiText(tg);
  if (mt) return mt + ((tg.faces || []).some(shellFace) ? " (shell)" : "");
  if (tg.point !== undefined) { const p = (FA.doc.points || []).find(x => x.id === tg.point); return "reference point " + (p ? p.name : tg.point); }
  if (tg.member !== undefined) { const m = FA.doc.members.find(x => x.id === tg.member); return (m ? m.name : tg.member) + (tg.end ? " end " + tg.end.toUpperCase() : ""); }
  if (tg.nset !== undefined) { const ns = (FA.doc.nsets || []).find(x => x.id === tg.nset); return "node set " + (ns ? ns.name + " (" + SM.nsetText(SH, ns) + ")" : tg.nset); }
  if (tg.edge !== undefined) {
    const comp = (FA.asm && FA.asm.components || []).find(x => x.id === tg.comp), c = compOf(tg.comp);
    return (comp ? comp.name : tg.comp) + " : " + edgeLabel(c && c.erefs, tg.edge, v => ffmt(v, 4));
  }
  return faceText(tg) + (shellFace(tg) ? " (shell)" : "");
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
  let h = d.supports.map(s => itemRow("support", s, `${s.name}: ${s.type}`, targetText(s.target))).join("") || '<p class="hint">Supports on faces and edges of the bodies and shells, node sets, member ends and reference points.</p>';
  const s = FA.sel && FA.sel.kind === "support" && findItem("support", FA.sel.id);
  for (const x of d.supports) if (!x.type) x.type = x.dofs ? "dofs" : "fixed";     // supports made in the explicit pane
  if (s) {
    const onMember = s.target && (s.target.member !== undefined || s.target.point !== undefined);
    const onPoint = s.target && s.target.point !== undefined;
    const onEdge = s.target && (s.target.edge !== undefined || s.target.nset !== undefined || s.target.surface !== undefined || !!VS.multiText(s.target));
    const onShell = onEdge || shellFace(s.target);
    const types = onMember ? [["fixed", "fixed (all 6)"], ["pinned", "pinned (ux uy uz)"], ["dofs", "chosen components"], ["displacement", "prescribed displacement"]]
                : onShell ? [["fixed", "fixed (all 6)"], ["pinned", "pinned (ux uy uz)"], ...SYMM_TYPES, ...(onEdge ? [] : [["normal", "normal to the face (planar)"]]),
                             ["dofs", "chosen components"], ["displacement", "prescribed displacement"]]
                           : [["fixed", "fixed (ux uy uz)"], ["normal", "normal to the face (planar)"], ["dofs", "chosen components"], ["displacement", "prescribed displacement"]];
    const dofs = s.dofs || [1, 1, 1, 0, 0, 0];
    const val = Array.isArray(s.value) ? s.value : [0, 0, 0, 0, 0, 0];
    const ndof = 6;
    h += `<div class="fa-props"><div class="grid2"><label>Name<input type="text" id="fsp-name" value="${fesc(s.name)}"></label>` +
      `<label>Type<select id="fsp-type">${types.map(([v, t]) => `<option value="${v}"${s.type === v ? " selected" : ""}>${t}</option>`).join("")}</select></label></div>` +
      `<p class="hint">Target: ${fesc(targetText(s.target))} <button type="button" class="small" id="fsp-pick" title="The selected faces, edges, bodies or reference point, or select them (or click a member end), then Done">Pick</button><button type="button" class="small" id="fsp-show" title="Select the target in the view">Show</button></p>` +
      (d.members.length ? `<label>or member end${memberEndSelect("fsp-mem", s.target, false)}</label>` : "") +
      (s.type === "dofs" ? `<div class="fa-dofs">${DOF_NAMES.slice(0, ndof).map((n, i) => `<label><input type="checkbox" data-dof="${i}"${dofs[i] ? " checked" : ""}>${n}</label>`).join("")}</div>` : "") +
      (!onMember && !onShell && (s.type === "dofs" || s.type === "displacement") ? `<p class="hint">rx, ry, rz on a face: the face is rigidly coupled (kinematic coupling) to a node at its centre, which carries the support.</p>` : "") +
      (onShell ? `<p class="hint">Edges and shell faces: the translations of all their nodes are held; the rotations act on the shell nodes only (nodes of solid elements have no rotations).</p>` : "") +
      ((d.surfaces || []).length ? `<label>or surface<select id="fsp-surf"><option value="">(choose)</option>${SM.surfaceOptions(SH, s.target && s.target.surface)}</select></label>` : "") +
      ((d.nsets || []).length ? `<label>or node set<select id="fsp-ns"><option value="">(choose)</option>${d.nsets.map(n => `<option value="${fesc(n.id)}"${s.target && s.target.nset === n.id ? " selected" : ""}>${fesc(n.name)}</option>`).join("")}</select></label>` : "") +
      ((d.points || []).length ? `<label>or reference point<select id="fsp-rp"><option value="">(choose)</option>${d.points.map(p => `<option value="${fesc(p.id)}"${onPoint && s.target.point === p.id ? " selected" : ""}>${fesc(p.name)}</option>`).join("")}</select></label>` : "") +
      (s.type === "displacement" ? `<p class="hint">Checked components are prescribed (mm; rotations in rad); unchecked components are free.</p><table class="pc-table fa-disp">` +
        DOF_NAMES.slice(0, ndof).map((n, i) => `<tr><td><label><input type="checkbox" data-dof="${i}"${dofs[i] ? " checked" : ""}>${n}</label></td><td><input type="text" class="numf" data-dval="${i}" value="${val[i] || 0}"${dofs[i] ? "" : " disabled"}></td></tr>`).join("") + `</table>` : "") +
      (s.type === "normal" ? `<label title="Displacement along the outward normal of the face (mm); 0: held">Normal displacement (mm, along the outward normal)<input type="text" class="numf" id="fsp-nval" value="${typeof s.value === "number" ? s.value : 0}"></label>` : "") +
      stepFactorsHtml(s, "support") + pickHint() + `</div>`;
  }
  box.innerHTML = h;
  if (s) bindStepFactors(box, s, renderSups);
  bindRows(box, "support", "supports");
  if (!s) return;
  $("#fsp-name").onchange = () => { s.name = $("#fsp-name").value.trim() || s.name; changed(); renderSups(); };
  $("#fsp-type").onchange = () => {
    s.type = $("#fsp-type").value;
    if (s.type === "displacement" && !Array.isArray(s.value)) { s.value = [0, 0, 0, 0, 0, 0]; if (!s.dofs) s.dofs = [1, 1, 1, 0, 0, 0]; }
    else if (s.type === "normal" && typeof s.value !== "number") s.value = 0;
    else if (s.type !== "displacement" && s.type !== "normal") delete s.value;
    changed(); renderSups(); draw(); };
  $("#fsp-pick").onclick = () => pickSupport(s);
  $("#fsp-show").onclick = () => VS.show(SH, s.target);
  if ($("#fsp-surf")) $("#fsp-surf").onchange = () => { const v = $("#fsp-surf").value; if (v) { s.target = { surface: v.slice(5) }; if (s.type === "normal") s.type = "fixed"; } changed(); renderSups(); draw(); };
  if ($("#fsp-ns")) $("#fsp-ns").onchange = () => { if ($("#fsp-ns").value) { s.target = { nset: $("#fsp-ns").value }; if (s.type === "normal") s.type = "fixed"; } changed(); renderSups(); draw(); };
  if ($("#fsp-rp")) $("#fsp-rp").onchange = () => { if ($("#fsp-rp").value) { s.target = { point: $("#fsp-rp").value }; if (s.type === "normal") s.type = "fixed"; } changed(); renderSups(); draw(); };
  if ($("#fsp-mem")) $("#fsp-mem").onchange = () => { const [mid, end] = $("#fsp-mem").value.split(":"); if (mid) { s.target = { member: mid, end }; if (s.type === "normal") s.type = "fixed"; } changed(); renderSups(); draw(); };
  box.querySelectorAll("[data-dof]").forEach(cb => cb.onchange = () => { const v = (s.dofs || [1, 1, 1, 0, 0, 0]).slice(); v[+cb.dataset.dof] = cb.checked ? 1 : 0; s.dofs = v; changed(); if (s.type === "displacement") renderSups(); });
  box.querySelectorAll("[data-dval]").forEach(inp => inp.onchange = () => { const v = (Array.isArray(s.value) ? s.value : [0, 0, 0, 0, 0, 0]).slice(); v[+inp.dataset.dval] = fnum(inp.value) || 0; s.value = v; changed(); });
  if ($("#fsp-nval")) $("#fsp-nval").onchange = () => { s.value = fnum($("#fsp-nval").value) || 0; changed(); };
}
/** Contact pairs (doc.contacts): master and slave faces from the face selection (Select faces), or found by Search;
 *  type, friction, penalty stiffness, adjust, tied tolerance; a node set as the slave of node-to-surface and tied pairs. */
const CONTACT_TYPES = [["surface", "surface-to-surface (penalty)"], ["node", "node-to-surface (penalty)"], ["tied", "tied (bonded)"]];
const fkeyOf = r => r.comp + ":" + r.face;
/** Faces of a contact side: of its surface (master_surface / slave_surface), else the picked faces. */
function contactFaces(c, side) {
  const sid = c[side + "_surface"];
  if (sid) { const f = (FA.doc.surfaces || []).find(x => x.id === sid); return f ? f.faces || [] : []; }
  return c[side] || [];
}
function sideText(c, side) {
  const sid = c[side + "_surface"];
  if (sid) { const f = (FA.doc.surfaces || []).find(x => x.id === sid); return f ? `surface ${f.name} (${(f.faces || []).length} face(s))` : "surface (deleted)"; }
  return (c[side] || []).length + " face(s)";
}
function contactSub(c) {
  return `master ${sideText(c, "master")}, slave ${c.slave_nset ? "node set " + ((FA.doc.nsets || []).find(n => n.id === c.slave_nset) || {}).name : sideText(c, "slave")}`;
}
function renderContacts() {
  const d = FA.doc, box = $("#fa-contacts");
  if (!box) return;
  d.contacts = d.contacts || [];
  const S = SM.selState(SH);
  let h = `<div class="row wrap"><button type="button" class="small" id="fc-add" title="New contact pair from the selected faces (first component: master)">Add contact</button>` +
    `<button type="button" class="small${S.types.has("faces") ? " on" : ""}" id="fc-sel" title="Click faces in the view to select or deselect them (Esc ends)">Select faces</button>` +
    `<span class="hint">${S.faces.size} face(s) selected</span></div>` +
    `<div class="row wrap"><label class="inline" title="Faces of different bodies closer than the gap (mm), facing each other">Gap (mm)<input type="text" class="numf" id="fc-gap" style="width:56px" value="${FA.contactGap || 0.1}"></label>` +
    `<button type="button" class="small" id="fc-search" title="Contact pairs of the faces of different bodies within the gap (master: the larger area)">Search</button></div>`;
  h += d.contacts.map(c => itemRow("contact", c, `${c.name}: ${(CONTACT_TYPES.find(t => t[0] === (c.type || "surface")) || [])[1]}`, contactSub(c))).join("") ||
    '<p class="hint">Contact pairs between faces of bodies and shells: penalty contact (surface-to-surface or node-to-surface) with friction, or tied faces. The bodies of a pair are meshed apart; the solve is nonlinear.</p>';
  const c = FA.sel && FA.sel.kind === "contact" && findItem("contact", FA.sel.id);
  if (c) {
    const typ = c.type || "surface";
    h += `<div class="fa-props"><div class="grid2"><label>Name<input type="text" id="fc-name" value="${fesc(c.name)}"></label>` +
      `<label>Type<select id="fc-type">${optList(CONTACT_TYPES, typ)}</select></label></div>` +
      `<p class="hint"><span style="color:#0c8599">Master</span>: ${fesc(sideText(c, "master"))} <button type="button" class="small" data-fcs="master">Set from selection</button><button type="button" class="small" data-fcx="master">Clear</button>${(d.surfaces || []).length ? `<select data-fcsurf="master" title="A surface as the master side"><option value="">or surface…</option>${SM.surfaceOptions(SH, c.master_surface)}</select>` : ""}</p>` +
      `<p class="hint"><span style="color:#d6336c">Slave</span>: ${fesc(sideText(c, "slave"))} <button type="button" class="small" data-fcs="slave">Set from selection</button><button type="button" class="small" data-fcx="slave">Clear</button>${(d.surfaces || []).length ? `<select data-fcsurf="slave" title="A surface as the slave side"><option value="">or surface…</option>${SM.surfaceOptions(SH, c.slave_surface)}</select>` : ""}` +
      `<button type="button" class="small" id="fc-swap" title="Swap master and slave">Swap</button><button type="button" class="small" id="fc-show" title="Select the faces of the pair">Select</button></p>` +
      (typ !== "surface" && (d.nsets || []).length ? `<label title="Slave nodes: a node set in place of the slave faces">Slave node set<select id="fc-ns"><option value="">(slave faces)</option>${d.nsets.map(n => `<option value="${fesc(n.id)}"${c.slave_nset === n.id ? " selected" : ""}>${fesc(n.name)}</option>`).join("")}</select></label>` : "") +
      (typ !== "tied" ? `<div class="grid2"><label title="Coulomb friction coefficient (0: frictionless)">Friction<input type="text" class="numf" id="fc-mu" value="${c.friction ?? ""}" placeholder="0"></label>` +
        `<label title="Slope of the pressure-overclosure line (N/mm^3). Empty: 10 x the largest E per mm">Stiffness (N/mm^3)<input type="text" class="numf" id="fc-k" value="${c.stiffness ?? ""}" placeholder="auto"></label></div>` +
        `<label title="Slave nodes within this distance of the master are moved onto it at the start (closes small gaps; empty: none)">Adjust (mm)<input type="text" class="numf" id="fc-adj" value="${c.adjust ?? ""}" placeholder="none"></label>`
        : `<label title="Slave nodes within this distance of the master are tied (empty: 1 % of the model size)">Position tolerance (mm)<input type="text" class="numf" id="fc-tol" value="${c.tol ?? ""}" placeholder="auto"></label>`) +
      `<p class="hint">Master: the stiffer or coarser side. Surface-to-surface: element faces on both sides; node-to-surface and tied: the slave nodes against the master faces.</p></div>`;
  }
  box.innerHTML = h;
  bindRows(box, "contact", "contacts");
  $("#fc-sel").onclick = () => { const t = new Set(S.types); if (t.has("faces")) t.delete("faces"); else t.add("faces"); VS.setTypes(SH, [...t]); };
  const selRefs = () => VS.items(SH, ["faces", "bodies"], true).faces;
  $("#fc-add").onclick = () => {
    if (!selRefs().length) {                                   // nothing selected: select, then Done
      VS.collect(SH, { text: "New contact pair: faces (first component: master)", types: ["faces", "bodies"], expand: true, cb: it => {
        if (!it.faces.length) return "select faces";
        const first = it.faces[0].comp;
        const x = { id: nid("ct"), name: "Contact " + (d.contacts.length + 1), type: "surface", master: it.faces.filter(r => r.comp === first), slave: it.faces.filter(r => r.comp !== first), friction: 0 };
        d.contacts.push(x); FA.sel = { kind: "contact", id: x.id };
        changed(); renderAll(); draw();
      } });
      return;
    }
    const refs = selRefs();
    const first = refs.length ? refs[0].comp : null;
    const x = { id: nid("ct"), name: "Contact " + (d.contacts.length + 1), type: "surface", master: refs.filter(r => r.comp === first), slave: refs.filter(r => r.comp !== first), friction: 0 };
    d.contacts.push(x); FA.sel = { kind: "contact", id: x.id };
    changed(); renderAll(); draw();
  };
  $("#fc-gap").onchange = () => { const v = fnum($("#fc-gap").value); if (v > 0) FA.contactGap = v; };
  $("#fc-search").onclick = async () => {
    try {
      status("Searching for contact faces...");
      const j = await (await postJSON("/api/analysis/contact_search", { analysis: d, gap: FA.contactGap || 0.1 })).json();
      const have = new Set(d.contacts.map(x => (x.master || []).map(fkeyOf).sort().join(",") + "|" + (x.slave || []).map(fkeyOf).sort().join(",")));
      let n = 0;
      for (const p of j.pairs) {
        const key = p.master.map(fkeyOf).sort().join(",") + "|" + p.slave.map(fkeyOf).sort().join(",");
        if (have.has(key)) continue;
        d.contacts.push({ id: nid("ct"), name: `${p.names[0]} / ${p.names[1]}`, type: "surface", master: p.master, slave: p.slave, friction: 0 });
        n++;
      }
      status(`${j.pairs.length} pair(s) found, ${n} added`);
      if (n) changed();
      renderAll(); draw();
    } catch (e) { showErr(e); }
  };
  if (!c) return;
  const num = (id, k) => { $(id).onchange = () => { const raw = $(id).value.trim(), v = fnum(raw); if (raw === "") delete c[k]; else if (v >= 0) c[k] = v; else { status("Not a number", true); return; } changed(); renderContacts(); }; };
  $("#fc-name").onchange = () => { c.name = $("#fc-name").value.trim() || c.name; changed(); renderContacts(); };
  $("#fc-type").onchange = () => { c.type = $("#fc-type").value; if (c.type === "surface") delete c.slave_nset; changed(); renderAll(); };
  box.querySelectorAll("[data-fcs]").forEach(b => b.onclick = () => {
    const side = b.dataset.fcs;
    const take = refs => { c[side] = refs; delete c[side + "_surface"]; if (side === "slave") delete c.slave_nset; changed(); renderAll(); draw(); };
    const refs = selRefs();
    if (refs.length) { take(refs); return; }
    VS.collect(SH, { text: `${c.name}: ${side} faces`, types: ["faces", "bodies"], expand: true, cb: it => { if (!it.faces.length) return "select faces"; take(it.faces); } });
  });
  box.querySelectorAll("[data-fcsurf]").forEach(sel => sel.onchange = () => {
    const side = sel.dataset.fcsurf, v = sel.value;
    if (v) { c[side + "_surface"] = v.slice(5); c[side] = []; if (side === "slave") delete c.slave_nset; } else delete c[side + "_surface"];
    changed(); renderAll(); draw();
  });
  box.querySelectorAll("[data-fcx]").forEach(b => b.onclick = () => { c[b.dataset.fcx] = []; delete c[b.dataset.fcx + "_surface"]; changed(); renderAll(); draw(); });
  $("#fc-swap").onclick = () => {
    [c.master, c.slave] = [c.slave || [], c.master || []];
    const ms = c.master_surface, ss = c.slave_surface;
    delete c.master_surface; delete c.slave_surface;
    if (ss) c.master_surface = ss;
    if (ms) c.slave_surface = ms;
    changed(); renderAll(); draw();
  };
  $("#fc-show").onclick = () => { S.faces = new Set([...contactFaces(c, "master"), ...contactFaces(c, "slave")].map(fkeyOf)); renderAll(); draw(); };
  if ($("#fc-ns")) $("#fc-ns").onchange = () => { if ($("#fc-ns").value) c.slave_nset = $("#fc-ns").value; else delete c.slave_nset; changed(); renderAll(); };
  if ($("#fc-mu")) num("#fc-mu", "friction");
  if ($("#fc-k")) num("#fc-k", "stiffness");
  if ($("#fc-adj")) num("#fc-adj", "adjust");
  if ($("#fc-tol")) num("#fc-tol", "tol");
}
const SYMM_TYPES = [["xsymm", "symmetry X (ux, ry, rz held)"], ["ysymm", "symmetry Y (uy, rx, rz held)"], ["zsymm", "symmetry Z (uz, rx, ry held)"]];
/** Target of a support from the selection (viewsel.js) or a member end clicked during it. */
function pickSupport(s) {
  VS.collect(SH, { text: s.name + ": faces, edges, vertices, bodies, mesh nodes or elements, a reference point or a member end", types: ["faces", "edges", "vertices", "bodies", "points", "nodes", "elements"],
    cb: it => {
      const r = VS.targetOf(it);
      if (r.error) return r.error;
      const t = r.target;
      if (t.point !== undefined) supportHit(s, { point: t.point });
      else if (t.face !== undefined) supportHit(s, { face: t });
      else if (t.edge !== undefined) supportHit(s, { edge: t });
      else { s.target = t; if (s.type === "normal") s.type = "fixed"; status(s.name + ": " + targetText(t)); }
      changed(); renderAll(); draw();
    },
    extra: e => endAt(e), cbExtra: h => { supportHit(s, { member: h.member, end: h.end }); changed(); renderAll(); draw(); } });
}
/** Target of a load from the selection (viewsel.js) or a member end or member clicked during it. */
function pickLoad(l) {
  const ut = uiType(l);
  const types = ut === "pressure" ? ["faces", "bodies"] : ut === "eline" ? ["edges"] : ["faces", "edges", "vertices", "bodies", "points", "nodes", "elements"];
  VS.collect(SH, { text: l.name + ": " + (ut === "pressure" ? "faces or bodies" : ut === "eline" ? "edges" : "faces, edges (line load), a reference point, a member end or a member"),
    types, expand: true,
    cb: it => {
      const r = VS.targetOf(it);
      if (r.error) return r.error;
      const t = r.target;
      if (t.point !== undefined) loadHit(l, { point: t.point });
      else if (t.face !== undefined) loadHit(l, { face: t });
      else if (t.edge !== undefined) loadHit(l, { edge: t });
      else if (t.faces && t.edges) return "a load takes faces or edges";
      else if ((t.vertices || t.nodes || t.elements) && (t.faces || t.edges || t.bodies)) return "vertices, mesh nodes and elements take a load of their own (not with faces, edges or bodies)";
      else if (t.vertices || t.nodes || t.elements) { if (!Array.isArray(l.value)) l.value = [0, 0, -1000]; l.type = "force"; l._ui = "force"; l.target = t; }
      else if (t.edges) { if (l.type !== "line") l.value = [0, 0, -1]; l.target = t; l.type = "line"; l._ui = "eline"; }
      else {
        if (l.type === "line" || (l.type !== "pressure" && !Array.isArray(l.value))) { l.type = "force"; l.value = [0, 0, -1000]; }
        l.target = t; l._ui = l.type === "moment" ? "moment" : l.type === "pressure" ? "pressure" : "force";
      }
      status(l.name + ": " + targetText(l.target));
      changed(); renderAll(); draw();
    },
    extra: e => {
      const h = endAt(e);
      if (h) return { member: h.member, end: h.end };
      if (ut === "pressure" || ut === "eline") return null;
      const m = rayAt(e).intersectObjects(FA.three.pickables, false).find(x => x.object.userData && x.object.userData.kind === "member" && x.object.userData.end === undefined);
      return m ? { member: m.object.userData.id } : null;
    },
    cbExtra: h => { loadHit(l, h); changed(); renderAll(); draw(); } });
}
function supportHit(s, hit) {
  const symm = SYMM_TYPES.some(([v]) => v === s.type);
  if (hit.point !== undefined && !hit.face) { s.target = { point: hit.point }; if (s.type === "normal" || symm) s.type = "fixed"; status(s.name + ": " + targetText(s.target)); return; }
  if (hit.edge) { s.target = hit.edge; if (s.type === "normal") s.type = "fixed"; }
  else if (hit.end) { s.target = { member: hit.member, end: hit.end }; if (s.type === "normal" || symm) s.type = "fixed"; }
  else { s.target = hit.face; if ((s.type === "pinned" || symm) && !shellFace(hit.face)) s.type = "fixed"; }
  status(s.name + ": " + targetText(s.target));
}
/** Reference points: name, coordinates (typed or picked), faces rigidly connected (*RIGID BODY). */
function renderRps() { if ($("#fa-rps")) RP.renderPoints(RH, $("#fa-rps")); }
/** Ref. point (toolbar): a new reference point placed at a clicked point (Esc: typed coordinates). */
function addRp() {
  renderRps();
  const b = document.querySelector('#fa-rps [data-rpa="add"]');
  if (b) b.click();
}

function addSupport() {
  const at = selEnd();
  const s = { id: nid("s"), name: "Support " + (FA.doc.supports.length + 1), type: "fixed", target: at };
  FA.doc.supports.push(s);
  FA.sel = { kind: "support", id: s.id };
  changed();
  if (at) { renderAll(); draw(); status(s.name + ": " + targetText(at)); return; }
  renderAll();
  pickSupport(s);
}

function renderLoads() {
  const d = FA.doc, box = $("#fa-loads");
  const UNITS = { force: "N", mforce: "N", moment: "N mm", mmoment: "N mm", line: "N/mm", eline: "N/mm", gravity: "mm/s^2", pressure: "MPa" };
  const valText = l => (Array.isArray(l.value) ? "(" + l.value.map(v => ffmt(v, 5)).join(", ") + ")" : ffmt(l.value, 5)) + " " + (UNITS[uiType(l)] || "");
  let h = d.loads.map(l => itemRow("load", l, `${l.name}: ${LOAD_TYPES[uiType(l)] || l.type}`, (l.type === "gravity" ? "" : targetText(l.target) + " ") + valText(l))).join("") ||
    '<p class="hint">Forces, moments and pressures on faces, line loads on edges and members, loads at member ends, gravity.</p>';
  const l = FA.sel && FA.sel.kind === "load" && findItem("load", FA.sel.id);
  if (l) {
    const ut = uiType(l);
    const unit = { force: "N", mforce: "N", moment: "N mm", mmoment: "N mm", line: "N/mm", eline: "N/mm", gravity: "mm/s^2" }[ut];
    h += `<div class="fa-props"><div class="grid2"><label>Name<input type="text" id="fld-name" value="${fesc(l.name)}"></label>` +
      `<label>Type<select id="fld-type">${Object.entries(LOAD_TYPES).map(([k, t]) => `<option value="${k}"${k === ut ? " selected" : ""}>${t}</option>`).join("")}</select></label></div>` +
      (ut === "pressure" ? `<label>Pressure (MPa, positive into the face)<input type="text" class="numf" id="fld-p" value="${ffmt(Number(l.value) || 0, 8)}"></label>`
                         : `<p class="hint" style="margin:6px 0 2px">${ut === "force" ? "Total force" : ut === "moment" ? "Moment about the face centre" : ut === "gravity" ? "Acceleration (-9810 in z: gravity down)" : ut === "eline" ? "Load per length of the edge" : "Value"} (${unit}, global x y z)</p>${v3("fld-v", l.value)}`) +
      (ut !== "gravity" ? `<p class="hint">Target: ${fesc(targetText(l.target))} <button type="button" class="small" id="fld-pick" title="${ut === "pressure" ? "Click a face" : ut === "eline" ? "Click an edge" : "Click a face, an edge (line load), a member end or a member (line load)"} in the view">Pick</button><button type="button" class="small" id="fld-show" title="Select the target in the view">Show</button></p>` : "") +
      (["mforce", "mmoment"].includes(ut) ? `<label>Member end${memberEndSelect("fld-mem", l.target, false)}</label>` +
        ((d.points || []).length ? `<label>or reference point<select id="fld-rp"><option value="">(choose)</option>${d.points.map(p => `<option value="${fesc(p.id)}"${l.target && l.target.point === p.id ? " selected" : ""}>${fesc(p.name)}</option>`).join("")}</select></label>` : "") : "") +
      (ut === "line" ? `<label>Member${memberEndSelect("fld-mem", l.target, true)}</label>` : "") +
      (["force", "pressure", "moment"].includes(ut) && (d.surfaces || []).length ? `<label>or surface<select id="fld-surf"><option value="">(choose)</option>${SM.surfaceOptions(SH, l.target && l.target.surface)}</select></label>` : "") +
      ((d.amplitudes || []).length ? `<label>Amplitude<select id="fld-amp"><option value="">(none: ramp in static steps, at once in dynamic steps)</option>${d.amplitudes.map(a => `<option value="${fesc(a.id)}"${l.amplitude === a.id ? " selected" : ""}>${fesc(a.name)}</option>`).join("")}</select></label>` : "") +
      stepFactorsHtml(l, "load") + pickHint() + `</div>`;
  }
  box.innerHTML = h;
  bindRows(box, "load", "loads");
  if (!l) return;
  bindStepFactors(box, l, renderLoads);
  if ($("#fld-amp")) $("#fld-amp").onchange = () => { if ($("#fld-amp").value) l.amplitude = $("#fld-amp").value; else delete l.amplitude; changed(); renderLoads(); };
  const upd = () => { changed(); renderLoads(); draw(); };
  $("#fld-name").onchange = () => { l.name = $("#fld-name").value.trim() || l.name; upd(); };
  $("#fld-type").onchange = () => {
    const nt = $("#fld-type").value;
    l.type = { mforce: "force", mmoment: "moment", eline: "line" }[nt] || nt;
    if (nt === "pressure") l.value = 0.1; else if (!Array.isArray(l.value)) l.value = nt === "gravity" ? [0, 0, -9810] : nt === "eline" ? [0, 0, -1] : [0, 0, -1000];
    if (nt === "gravity") l.target = null;
    if ((nt === "eline") !== !!(l.target && l.target.edge !== undefined)) l.target = null;
    if (["mforce", "mmoment", "line"].includes(nt) && !(l.target && (l.target.member !== undefined || (l.target.point !== undefined && nt !== "line")))) l.target = FA.doc.members.length ? { member: FA.doc.members[0].id, end: nt === "line" ? undefined : "b" } : null;
    if (["force", "pressure", "moment"].includes(nt) && l.target && (l.target.member !== undefined || l.target.point !== undefined)) l.target = null;
    l._ui = nt;
    upd();
  };
  if ($("#fld-p")) $("#fld-p").onchange = () => { l.value = fnum($("#fld-p").value) || 0; upd(); };
  if ($("#fld-v0")) [0, 1, 2].forEach(i => $("#fld-v" + i).onchange = () => { l.value = read3("fld-v"); upd(); });
  if ($("#fld-pick")) $("#fld-pick").onclick = () => pickLoad(l);
  if ($("#fld-show")) $("#fld-show").onclick = () => VS.show(SH, l.target);
  if ($("#fld-surf")) $("#fld-surf").onchange = () => { const v = $("#fld-surf").value; if (v) l.target = { surface: v.slice(5) }; upd(); };
  if ($("#fld-rp")) $("#fld-rp").onchange = () => { if ($("#fld-rp").value) l.target = { point: $("#fld-rp").value }; upd(); };
  if ($("#fld-mem")) $("#fld-mem").onchange = () => { const [mid, end] = $("#fld-mem").value.split(":"); l.target = mid ? (end ? { member: mid, end } : { member: mid }) : null; upd(); };
}
// ------------------------------------------------------------------ steps, amplitudes, initial velocities

const STEP_KINDS = [["static", "static"], ["dynamic", "dynamic (implicit)"], ["explicit", "dynamic (explicit)"]];
/** Steps of the document, or the one default static step. */
function stepList() {
  const d = FA.doc || {};
  return (d.steps || []).length ? d.steps : [{ id: "1", name: "Step 1", kind: "static", _default: true }];
}
function renderSteps() {
  const d = FA.doc, box = $("#fa-steps");
  if (!box) return;
  $("#fa-steps-card").hidden = !!(d.analysis_type && d.analysis_type !== "static");
  const steps = stepList(), def = !(d.steps || []).length;
  const num = (st, k, ph) => `<input type="text" class="numf" data-stk="${k}" value="${st[k] === undefined ? "" : fesc(st[k])}" placeholder="${ph}" style="width:52px">`;
  let h = `<table class="fa-tbl fa-steps"><tr><th>Step</th><th>Kind</th><th title="Step time (s)">Time (s)</th><th title="First increment, fraction of the step time">1st inc.</th><th title="Largest increment, fraction of the step time">Max inc.</th><th title="Largest number of increments">Incs</th><th title="Results every n increments">Every</th><th></th></tr>` +
    steps.map((st, i) => `<tr data-st="${fesc(st.id)}"><td><input type="text" data-stk="name" value="${fesc(st.name)}" style="width:80px"${def ? " disabled" : ""}></td>` +
      `<td><select data-stk="kind"${def ? " disabled" : ""}>${STEP_KINDS.map(([v, t]) => `<option value="${v}"${(st.kind || "static") === v ? " selected" : ""}>${t}</option>`).join("")}</select></td>` +
      (def ? `<td colspan="5" class="hint">increments: Settings, Nonlinear step</td><td></td>` :
        `<td>${num(st, "time", st.kind === "static" ? "1" : "0.01")}</td><td>${num(st, "inc0", st.kind === "static" ? "0.1" : "0.01")}</td><td>${num(st, "incmax", st.kind === "static" ? "0.25" : "0.05")}</td>` +
        `<td>${num(st, "maxinc", st.kind === "static" ? "100" : "10000")}</td><td>${num(st, "every", "1")}</td>` +
        `<td><button type="button" class="small" data-sta="up" title="Move up"${i ? "" : " disabled"}>▲</button><button type="button" class="small" data-sta="del" title="Delete the step">×</button></td>`) + `</tr>`).join("") + `</table>` +
    `<div class="row"><button type="button" class="small" id="fst-add">Add step</button></div>` +
    `<p class="hint">Steps run in sequence. Static: the loads ramp from the values of the step before. Dynamic (implicit, *DYNAMIC) and explicit (*DYNAMIC, EXPLICIT): the loads act at once, densities needed; Initial velocities apply at the start. Each support and load has a factor per step (Supports, Loads: Steps).</p>`;
  box.innerHTML = h;
  $("#fst-add").onclick = () => {
    if (!(d.steps || []).length) d.steps = [{ id: "1", name: "Step 1", kind: "static" }];
    let k = d.steps.length + 1;
    while (d.steps.some(x => x.id === String(k))) k++;
    d.steps.push({ id: String(k), name: "Step " + k, kind: "static" });
    changed(); renderAll();
  };
  box.querySelectorAll("tr[data-st]").forEach(tr => {
    const st = (d.steps || []).find(x => x.id === tr.dataset.st);
    if (!st) return;
    tr.querySelectorAll("[data-stk]").forEach(el => el.onchange = () => {
      const k = el.dataset.stk;
      if (k === "name") st.name = el.value.trim() || st.name;
      else if (k === "kind") st.kind = el.value;
      else { const v = fnum(el.value); if (el.value.trim() === "") delete st[k]; else if (v > 0) st[k] = k === "maxinc" || k === "every" ? Math.round(v) : v; else el.value = st[k] === undefined ? "" : st[k]; }
      changed(); renderAll();
    });
    tr.querySelectorAll("[data-sta]").forEach(b => b.onclick = () => {
      const i = d.steps.indexOf(st);
      if (b.dataset.sta === "up" && i > 0) { d.steps.splice(i, 1); d.steps.splice(i - 1, 0, st); }
      if (b.dataset.sta === "del") {
        d.steps.splice(i, 1);
        for (const x of [...(d.supports || []), ...(d.loads || [])]) if (x.steps) delete x.steps[st.id];
        if (d.steps.length === 1 && !d.steps[0].time && d.steps[0].kind === "static") d.steps = [];
      }
      changed(); renderAll();
    });
  });
}
/** Factors of a support or load per step (empty: 1 in every step until one is set). */
function stepFactorsHtml(x, what) {
  const steps = stepList();
  if (steps.length < 2 && !x.steps) return "";
  return `<p class="hint" style="margin:6px 0 2px">Steps: factor of the ${what} (0: ${what === "support" ? "released" : "removed"})</p><div class="row wrap fa-stepf">` +
    steps.map(st => `<label class="inline">${fesc(st.name)}<input type="text" class="numf" data-stf="${fesc(st.id)}" value="${x.steps ? (x.steps[st.id] === undefined ? 0 : x.steps[st.id]) : 1}" style="width:44px"></label>`).join("") + `</div>`;
}
function bindStepFactors(box, x, rerender) {
  box.querySelectorAll("[data-stf]").forEach(el => el.onchange = () => {
    const v = fnum(el.value);
    if (!isFinite(v)) { el.value = x.steps ? (x.steps[el.dataset.stf] || 0) : 1; return; }
    if (!x.steps) { x.steps = {}; for (const st of stepList()) x.steps[st.id] = 1; }
    x.steps[el.dataset.stf] = v;
    if (stepList().every(st => x.steps[st.id] === 1)) delete x.steps;
    changed(); rerender();
  });
}
function renderAmps() {
  const d = FA.doc, box = $("#fa-amps");
  if (!box) return;
  CV.renderAmplitudes(box, d, { changed, rerender: renderAll, status, nid, xlabel: "step time (s)", addId: "famp-add",
    hint: "Tabular amplitudes: time (s, from the start of the step), factor; linear between the points, constant outside. A load with an amplitude is its value times the factor." });
}
function renderIvel() {
  const d = FA.doc, box = $("#fa-ivel");
  if (!box) return;
  d.initial_velocities = d.initial_velocities || [];
  box.innerHTML = d.initial_velocities.map(v => `<div class="fa-ivel" data-iv="${fesc(v.id)}"><div class="row"><input type="text" data-ivk="name" value="${fesc(v.name)}" style="width:110px">` +
      `<span class="hint">${fesc(v.target ? (v.target.nset ? "node set " + ((d.nsets || []).find(n => n.id === v.target.nset) || {}).name : VS.multiText(v.target) || "(none)") : "(no target)")}</span>` +
      `<button type="button" class="small" data-ivk="pick" title="The selection (bodies, faces, edges, vertices, mesh nodes, elements) or select, then Done">Pick</button>` +
      `<button type="button" class="small" data-ivk="del" title="Delete">×</button></div>${v3("fiv-" + v.id, v.v || [0, 0, 0])}</div>`).join("") +
    `<div class="row"><button type="button" class="small" id="fiv-add">Add initial velocity</button></div>` +
    `<p class="hint">Velocity (mm/s, global x y z) of the nodes of the target at the start (*INITIAL CONDITIONS, TYPE=VELOCITY); used by dynamic steps.</p>`;
  const pick = v => VS.collect(SH, { text: v.name + ": bodies, faces, edges, vertices, mesh nodes or elements", types: ["bodies", "faces", "edges", "vertices", "nodes", "elements"], cb: it => {
    const r = VS.targetOf(it);
    if (r.error) return r.error;
    const t = r.target;
    v.target = t.face !== undefined ? { faces: [t] } : t.edge !== undefined ? { edges: [t] } : t;
    changed(); renderAll(); draw();
  } });
  $("#fiv-add").onclick = () => { const v = { id: nid("iv"), name: "Velocity " + (d.initial_velocities.length + 1), v: [0, 0, -1000], target: null }; d.initial_velocities.push(v); changed(); renderAll(); pick(v); };
  box.querySelectorAll("[data-iv]").forEach(div => {
    const v = d.initial_velocities.find(x => x.id === div.dataset.iv);
    div.querySelectorAll("[data-ivk]").forEach(el => {
      const k = el.dataset.ivk;
      if (k === "del") el.onclick = () => { d.initial_velocities = d.initial_velocities.filter(x => x !== v); changed(); renderAll(); };
      else if (k === "pick") el.onclick = () => pick(v);
      else el.onchange = () => { v.name = el.value.trim() || v.name; changed(); renderAll(); };
    });
    [0, 1, 2].forEach(i => { const el = $("#fiv-" + v.id + i); if (el) el.onchange = () => { v.v = read3("fiv-" + v.id); changed(); }; });
  });
}

function uiType(l) {
  if (l._ui) return l._ui;
  if (l.target && l.target.edge !== undefined) return "eline";
  if (l.target && (l.target.member !== undefined || l.target.point !== undefined)) return l.type === "line" ? "line" : l.type === "moment" ? "mmoment" : "mforce";
  return l.type;
}
/** Target of a load from a pick: a member end (force or moment at the end), a member (line load), or a face. */
function loadHit(l, hit) {
  const moment = l.type === "moment";
  if (l.type === "pressure" && hit.face && !hit.edge && hit.end === undefined && hit.member === undefined) {
    if (Array.isArray(l.value) || !isFinite(Number(l.value))) l.value = 0.1;
  } else if (!Array.isArray(l.value)) l.value = [0, 0, -1000];
  if (hit.point !== undefined && !hit.face) { l.target = { point: hit.point }; if (l.type !== "moment") l.type = "force"; l._ui = l.type === "moment" ? "mmoment" : "mforce"; }
  else if (hit.end) { l.target = { member: hit.member, end: hit.end }; l.type = moment ? "moment" : "force"; l._ui = moment ? "mmoment" : "mforce"; }
  else if (hit.member !== undefined) { if (l.type !== "line") l.value = [0, 0, -1]; l.target = { member: hit.member }; l.type = "line"; l._ui = "line"; }
  else if (hit.edge) { if (l.type !== "line") l.value = [0, 0, -1]; l.target = hit.edge; l.type = "line"; l._ui = "eline"; }
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
  renderAll();
  pickLoad(l);
}

// ------------------------------------------------------------------ results panel

/** Mesh report of the shells: faces structured and free, element quality (gamma) and edge lengths. */
function shellReport(r) {
  if (!r) return "";
  return `<p class="hint fa-shellrep">Shells: ${r.structured} of ${r.faces} face(s) structured, ${r.free} free; element quality (gamma) min ${ffmt(r.min_quality, 3)}, mean ${ffmt(r.mean_quality, 3)}, ` +
    `below 0.3: ${r.below_03}; element edges ${ffmt(r.min_edge, 4)} mm to ${ffmt(r.max_edge, 4)} mm</p>`;
}

/** Result bodies of the selection: selected bodies, the bodies or sections of selected faces (a surface body meshed
 *  in sections: those sections). */
function resultBodiesOfSelection(have) {
  const it = VS.items(SH, ["faces", "bodies"]), hv = new Set(have), out = new Set();
  for (const [kind, id] of VS.suppressTargets(SH, it)) {
    const rid = kind === "section" ? "sec:" + id : id;
    if (hv.has(rid)) { out.add(rid); continue; }
    if (kind === "shell") for (const r of VS.facesOfBody(SH, id)) {
      const sec = (FA.doc.sections || []).find(x => (x.faces || []).some(q => q.comp === r.comp && q.face === r.face));
      if (sec && hv.has("sec:" + sec.id)) out.add("sec:" + sec.id);
    }
  }
  return out;
}
function renderResults() {
  const box = $("#fa-results");
  const r = FA.res;
  if (!r || !r.tables) {
    const s = FA.mesh && FA.mesh._summary;
    if (FA.live && (FA.job || FA.liveFailed)) { renderLive(box, FA.liveFailed); return; }
    box.innerHTML = s ? `<p class="hint">Mesh: ${s.nodes} nodes, ${s.elements} elements${s.ties ? ", " + s.ties + " tie(s)" : ""}. ${s.bodies.map(b => fesc(b.name) + " " + b.elements + " " + b.types.join("+")).join(", ")}</p>` + shellReport(s.shell) +
      ((s.warnings || []).length ? `<p class="hint">${s.warnings.map(fesc).join("<br>")}</p>` : "") : '<p class="hint">Solve to see the results.</p>';
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
  const hasPe = t.bodies.some(b => b.pemax !== null && b.pemax !== undefined);
  const hide = FA.bodyHide || new Set();
  h += `<div class="row wrap"><button type="button" class="small" id="fr-ball" title="Show all bodies">Show all</button>` +
    `<button type="button" class="small" id="fr-bsel" title="Show only the bodies selected in the view (Bodies; selected faces give their body or section)">Show selected</button>` +
    `<span class="hint">${hide.size ? hide.size + " body(ies) hidden" : ""}</span></div>` +
    `<div class="fa-wide"><table class="fa-tbl fr-bodies"><tr><th>Show</th><th>Body</th><th>max |u| (mm)</th><th>ux (mm)</th><th>uy (mm)</th><th>uz (mm)</th><th>max von Mises (MPa)</th>${hasPe ? "<th>max PEEQ</th>" : ""}</tr>` +
    t.bodies.map(b => `<tr><td><input type="checkbox" data-bshow="${fesc(b.id)}"${hide.has(b.id) ? "" : " checked"}></td>` +
      [fesc(b.name), ffmt(b.umax)].concat((b.ucomp || [null, null, null]).map(v => ffmt(v)), [ffmt(b.smax)], hasPe ? [ffmt(b.pemax || 0, 4)] : []).map(c => `<td>${c}</td>`).join("") + `</tr>`).join("") +
    `</table></div><p class="hint">ux, uy, uz: the component of largest magnitude over the nodes of the body. Show: the bodies drawn in Show Mesh and Results; the colour range is taken from the bodies shown.</p>`;
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
  if (r.history && r.history.rows.length) h += `<p class="hint" style="margin:8px 0 2px">Load history (one point per output increment; a click shows the increment)</p>` +
    `<div class="row wrap"><label class="inline">x<select id="fr-hx">${optList(historySeries(r.history).map(q => [q.key, q.name]), FA.histX || "time")}</select></label>` +
    `<label class="inline">y<select id="fr-hy">${optList(historySeries(r.history).map(q => [q.key, q.name]), FA.histY || historySeries(r.history)[1].key)}</select></label></div><div id="fr-hplot"></div>`;
  if ((r.time_history || []).length) {
    const q = r.time_history.find(x => x.id === FA.thReq) || r.time_history[0];
    const on = FA.thOn && FA.thOn[q.id] ? FA.thOn[q.id] : q.series.slice(0, 1).map(x => x.name);
    h += `<h3 class="xp-h">Time history</h3><div class="row wrap"><label class="inline">Request<select id="fr-threq">${r.time_history.map(x => `<option value="${fesc(x.id)}"${x === q ? " selected" : ""}>${fesc(x.name)}</option>`).join("")}</select></label>` +
      `<button type="button" class="small" id="fr-thcsv" title="The curves of the request as CSV">CSV</button></div>` +
      `<div class="row wrap fa-thser">${q.series.map(x => `<label class="check inline"><input type="checkbox" data-ths="${fesc(x.name)}"${on.includes(x.name) ? " checked" : ""}> ${fesc(x.name)}</label>`).join("") || '<span class="hint">no values (see the solver log)</span>'}</div><div id="fr-thplot"></div>`;
  }
  if (r.run) {
    const R = r.run;
    h += `<h3 class="xp-h">Run</h3><p class="hint">${fesc(liveProcText(R, true))}${R.n ? `; ${R.n} increment(s)` : ""}${R.cvg ? `, ${R.cvg.series[0].t.length} iteration(s)` : ""}. ${fesc(liveStagesText(R))}</p>` +
      `<div id="fr-runcvg"></div><details class="fr-rundet"><summary class="hint">Solver output</summary><div id="fr-runlog"></div></details>`;
  }
  h += probeHtml(r);
  h += `<div class="row" style="margin-top:8px"><button type="button" id="fr-report">Report</button><button type="button" id="fr-download">Download report</button><button type="button" id="fr-folder">Open run folder</button></div>`;
  box.innerHTML = h;
  if ($("#fr-thplot")) bindTimeHistory(r);
  if (r.run) { renderCvg($("#fr-runcvg"), r.run.cvg); renderLog($("#fr-runlog"), r.run.log, r.name); }
  bindProbe(r);
  box.querySelectorAll("[data-bshow]").forEach(cb => cb.onchange = () => {
    FA.bodyHide = FA.bodyHide || new Set();
    if (cb.checked) FA.bodyHide.delete(cb.dataset.bshow); else FA.bodyHide.add(cb.dataset.bshow);
    draw(); renderResults();
  });
  $("#fr-ball").onclick = () => { FA.bodyHide = new Set(); draw(); renderResults(); };
  $("#fr-bsel").onclick = () => {
    const ids = resultBodiesOfSelection(t.bodies.map(b => b.id));
    if (!ids.size) { status("Select bodies (Bodies) or faces in Show Model first", true); return; }
    FA.bodyHide = new Set(t.bodies.map(b => b.id).filter(id => !ids.has(id)));
    draw(); renderResults();
  };
  if ($("#fr-hplot")) {
    $("#fr-hx").onchange = () => { FA.histX = $("#fr-hx").value; plotHistory(); };
    $("#fr-hy").onchange = () => { FA.histY = $("#fr-hy").value; plotHistory(); };
    plotHistory();
  }
  const name = encodeURIComponent(r.name);
  $("#fr-report").onclick = () => window.open("/api/analysis/report/" + name, "_blank");
  $("#fr-download").onclick = () => { const a = document.createElement("a"); a.href = "/api/analysis/report/" + name + "?download=1"; document.body.appendChild(a); a.click(); a.remove(); };
  $("#fr-folder").onclick = () => postJSON("/api/analysis/open_folder", { name: r.name }).catch(showErr);
}

// ------------------------------------------------------------------ probe and path (Results)

const FIELD_UNIT = { vm: ["von Mises", "MPa"], u: ["|u|", "mm"], ux: ["ux", "mm"], uy: ["uy", "mm"], uz: ["uz", "mm"], peeq: ["PEEQ", "-"] };
/** Value of a field at view node i of a state. */
function fieldAt(st, field, i) {
  const p = FA.res.payload;
  if (!p.states[st]) return NaN;
  const s = stateData(p, st);
  const ux = s.U[3 * i], uy = s.U[3 * i + 1], uz = s.U[3 * i + 2];
  return field === "vm" ? s.vm[i] : field === "peeq" ? (s.pe ? s.pe[i] : NaN) : field === "u" ? Math.hypot(ux, uy, uz) : field === "ux" ? ux : field === "uy" ? uy : uz;
}
/** States of the probe curves in time order: the increments, else the steps (time: step number), else the state. */
function probeStates() {
  const r = FA.res;
  if ((r.increments || []).length) return r.increments.map(x => ({ st: x.state, t: x.time }));
  const ss = (r.states || []).filter(s => /^s\d+$/.test(s));
  if (ss.length) return ss.map(s => ({ st: s, t: +s.slice(1) }));
  return [{ st: $("#fa-state").value, t: 0 }];
}
/** A click on the result: the view node nearest the hit (probe: added to the probes; path: an end of the path). */
function probeClick(e) {
  const h = rayAt(e).intersectObjects(FA.three.group.children.filter(o => o.userData && o.userData.kind === "mesh"), false)[0];
  if (!h || !h.face) { status("Probe: click a face of the result", true); return; }
  const P = h.object.geometry.attributes.position.array;
  let best = null, bd = Infinity;
  for (const v of [h.face.a, h.face.b, h.face.c]) {
    const dd = Math.hypot(P[3 * v] - h.point.x, P[3 * v + 1] - h.point.y, P[3 * v + 2] - h.point.z);
    if (dd < bd) { bd = dd; best = v; }
  }
  const vs = h.object.userData.vsrc, i = vs ? vs[best] : best;
  const ids = decoded(FA.res.payload).ids;
  const node = { i, id: ids ? ids[i] : i };
  if (FA.probeMode === "probe") {
    FA.probes = (FA.probes || []).filter(x => x.i !== i).concat([node]).slice(-8);
    status(`Probe: node ${node.id}`);
  } else {
    FA.path = (FA.path && FA.path.length === 1) ? [FA.path[0], node] : [node];
    status(FA.path.length === 1 ? `Path: node ${node.id}; click the end of the path` : `Path: node ${FA.path[0].id} to node ${node.id}`);
    if (FA.path.length === 2) FA.probeMode = null;
  }
  renderResults(); draw();
}
/** Markers of the probes and the path on the result (deformed positions pos). */
function drawProbes(t, pos) {
  const r = (FA.size || 100) / 300;
  const at = i => new THREE.Vector3(pos[3 * i], pos[3 * i + 1], pos[3 * i + 2]);
  (FA.probes || []).forEach((q, k) => {
    const b = new THREE.Mesh(track(new THREE.SphereGeometry(r * 2.4, 12, 8)), new THREE.MeshBasicMaterial({ color: TH.COLORS[k % TH.COLORS.length], depthTest: false }));
    b.position.copy(at(q.i)); b.renderOrder = 12; b.userData = { kind: "probe" };
    t.group.add(b);
  });
  if (FA.path && FA.path.length) {
    const g = track(new THREE.BufferGeometry().setFromPoints(FA.path.map(q => at(q.i))));
    const ln = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0x111111, depthTest: false }));
    ln.renderOrder = 12; ln.userData = { kind: "probe" };
    t.group.add(ln);
    for (const q of FA.path) {
      const b = new THREE.Mesh(track(new THREE.SphereGeometry(r * 2, 12, 8)), new THREE.MeshBasicMaterial({ color: 0x111111, depthTest: false }));
      b.position.copy(at(q.i)); b.renderOrder = 12; b.userData = { kind: "probe" };
      t.group.add(b);
    }
  }
}
/** Probe curves: the field at each probed node over the states. */
function probeSeries(field) {
  const sts = probeStates();
  const [fn, unit] = FIELD_UNIT[field] || [field, ""];
  return (FA.probes || []).map(q => ({ name: `node ${q.id} ${fn}`, unit, t: sts.map(x => x.t), v: sts.map(x => fieldAt(x.st, field, q.i)) }));
}
/** Path curve: the field along the straight line between the path ends (60 samples), on the surface of the bodies
 *  (nearest point of the undeformed surface triangles, linear on the triangle). */
function pathSeries(field, st) {
  if (!FA.path || FA.path.length < 2) return [];
  const d = decoded(FA.res.payload), P = d.pos, T = d.tri;
  const A = new THREE.Vector3().fromArray(P, 3 * FA.path[0].i), B = new THREE.Vector3().fromArray(P, 3 * FA.path[1].i);
  const L = A.distanceTo(B), N = 60;
  const tri = new THREE.Triangle(), q = new THREE.Vector3(), c = new THREE.Vector3(), bary = new THREE.Vector3();
  const va = new THREE.Vector3(), vb = new THREE.Vector3(), vc = new THREE.Vector3();
  const xs = [], vs = [];
  for (let k = 0; k <= N; k++) {
    const x = new THREE.Vector3().lerpVectors(A, B, k / N);
    let bd = Infinity, bt = -1;
    for (let j = 0; j < T.length; j += 3) {
      va.fromArray(P, 3 * T[j]); vb.fromArray(P, 3 * T[j + 1]); vc.fromArray(P, 3 * T[j + 2]);
      tri.set(va, vb, vc); tri.closestPointToPoint(x, q);
      const dd = q.distanceToSquared(x);
      if (dd < bd) { bd = dd; bt = j; c.copy(q); }
    }
    if (bt < 0) continue;
    va.fromArray(P, 3 * T[bt]); vb.fromArray(P, 3 * T[bt + 1]); vc.fromArray(P, 3 * T[bt + 2]);
    THREE.Triangle.getBarycoord(c, va, vb, vc, bary);
    xs.push(L * k / N);
    vs.push(bary.x * fieldAt(st, field, T[bt]) + bary.y * fieldAt(st, field, T[bt + 1]) + bary.z * fieldAt(st, field, T[bt + 2]));
  }
  const [fn, unit] = FIELD_UNIT[field] || [field, ""];
  return [{ name: `${fn} node ${FA.path[0].id} to ${FA.path[1].id}`, unit, t: xs, v: vs }];
}
function probeHtml(r) {
  if (r.atype !== "static") return "";
  const mode = FA.probeMode;
  const fname = (FIELD_UNIT[$("#fa-field").value] || [""])[0];
  let h = `<h3 class="xp-h">Probe and path</h3><div class="row wrap">` +
    `<button type="button" class="small${mode === "probe" ? " primary" : ""}" id="fr-probe" title="Click points of the result: the Result field at the nearest node over the increments (or steps)">Probe</button>` +
    `<button type="button" class="small${mode === "path" ? " primary" : ""}" id="fr-path" title="Click the two ends of a path on the result: the Result field along the straight line on the surface">Path</button>` +
    `<button type="button" class="small" id="fr-pclear">Clear</button><button type="button" class="small" id="fr-pcsv" title="The probe and path curves as CSV">CSV</button>` +
    (mode ? `<span class="hint">${mode === "probe" ? "click points of the result (Probe again: end)" : "click the two ends of the path"}</span>` : "") + `</div>`;
  if ((FA.probes || []).length) h += `<p class="hint">Probe: ${fname} at ${FA.probes.map(q => "node " + q.id).join(", ")} against ${(r.increments || []).length ? "the total time (s)" : "the step"}</p><div id="fr-probeplot"></div>`;
  if (FA.path && FA.path.length === 2) h += `<p class="hint">Path: ${fname} of ${fesc(stateName($("#fa-state").value))} against the distance from node ${FA.path[0].id} (mm)</p><div id="fr-pathplot"></div>`;
  return h;
}
function bindProbe(r) {
  if (!$("#fr-probe")) return;
  const field = $("#fa-field").value;
  const sts = probeStates();
  if ($("#fr-probeplot")) TH.plot($("#fr-probeplot"), probeSeries(field), { xlabel: (r.increments || []).length ? "time (s)" : "step",
    mark: (sts.find(x => x.st === $("#fa-state").value) || {}).t,
    onPick: t => { let b = sts[0]; for (const x of sts) if (Math.abs(x.t - t) < Math.abs(b.t - t)) b = x; $("#fa-state").value = b.st; draw(); renderResults(); } });
  if ($("#fr-pathplot")) TH.plot($("#fr-pathplot"), pathSeries(field, $("#fa-state").value), { xlabel: "distance (mm)" });
  const toggle = m => { FA.probeMode = FA.probeMode === m ? null : m; if (m === "path" && FA.probeMode) FA.path = []; if (FA.probeMode) { $("#fa-show").value = "results"; draw(); } renderResults(); };
  $("#fr-probe").onclick = () => toggle("probe");
  $("#fr-path").onclick = () => toggle("path");
  $("#fr-pclear").onclick = () => { FA.probes = []; FA.path = null; FA.probeMode = null; renderResults(); draw(); };
  $("#fr-pcsv").onclick = () => {
    const S = probeSeries(field).concat(pathSeries(field, $("#fa-state").value));
    if (!S.length) { status("Probe: no curves", true); return; }
    TH.download(`${r.name}_probe.csv`.replace(/[^A-Za-z0-9_.\-]+/g, "_"), TH.csv(S));
  };
}

/** Input file page (inpinfo.js): the contents of the .inp or .rad file of a mesh file geometry. */
function renderInpFile() {
  const s = (FA.doc && FA.doc.source) || {}, card = $("#fa-inpfile-card"), box = $("#fa-inpfile");
  if (!card) return;
  const path = s.type === "inp" ? s.path || "" : "";
  card.hidden = !path;
  if (!path) { FA.inpFileShown = null; return; }
  if (FA.inpFileShown === path && box.innerHTML) return;
  FA.inpFileShown = path;
  IF.render(box, path, { mark: m => { FA.queryMarks = m; draw(); },
    pick: cb => startPick("Click a point of the model", { snap: true }, hit => { if (hit && hit.xyz) cb(hit.xyz); }),
    pickAt: (cb, cancel) => startPick("Click a node or element of the model", { snap: true, raw: true, onCancel: cancel }, hit => { if (hit && hit.xyz) cb(hit); }),
    endPick: () => { if (FA.pick && FA.pick.raw) { FA.pick.onCancel = null; endPick(); } } });
}

/** Text of the solver state of a run monitor record: the iteration of a step with increments and the stage of the
 *  solver. */
function liveStageText(L) {
  const a = L.sta;
  let h = L.increment ? `${L.increment[0].toUpperCase()}${L.increment.slice(1)}: ${L.stage.toLowerCase()}` : L.stage;
  if (a) h += `. Last increment: step ${a.step}, increment ${a.inc}${a.att > 1 ? ", attempt " + a.att : ""}${a.cut ? " (cutback)" : ""}, ${a.itrs} iterations, step time ${ffmt(a.time, 4)} s, total time ${ffmt(a.tot, 4)} s, increment ${ffmt(a.dt, 3)} s (${L.n} increments)`;
  return h;
}

/** Text of the process of a run monitor record: elapsed time, CPU use, memory and the estimate of the remaining
 *  time. */
function liveProcText(L, done) {
  const parts = [`${done ? "solver" : "elapsed"} ${ffmt(L.elapsed, 4)} s`];
  if (L.threads) parts.push(`${L.threads} thread(s)`);
  if (!done && L.cpu_pct !== null && L.cpu_pct !== undefined) parts.push(`CPU ${L.cpu_pct} %`);
  if (!done && L.mem_mb !== null && L.mem_mb !== undefined) parts.push(`memory ${L.mem_mb} MB`);
  const e = L.estimate;
  if (!done && e) parts.push(`${Math.round(100 * e.done)} % of the analysis time of ${ffmt(e.total, 4)} s, about ${e.remaining} s remaining`);
  return parts.join(", ");
}

/** Text of the stages of a run: name and duration (the stages before the increments, Increments, Finished). */
function liveStagesText(L) {
  const st = L.stages || [];
  if (!st.length) return "";
  const end = ["Finished", "Stopped"];
  return "Stages: " + st.map((x, i) => end.includes(x.name) ? x.name : `${x.name} ${ffmt((i + 1 < st.length ? st[i + 1].t0 : L.elapsed) - x.t0, 3)} s`).join(", ");
}

/** Convergence plot of a run (the iterations of job.cvg) into box (built once; the curves chosen are kept in
 *  FA.cvgOn). */
function renderCvg(box, cvg) {
  if (!box) return;
  if (!cvg) { box.innerHTML = ""; return; }
  const on = FA.cvgOn || cvg.series.slice(0, 2).map(x => x.name);
  if (!box.querySelector(".fr-cvgplot")) {
    box.innerHTML = `<h3 class="xp-h">Convergence</h3><div class="row wrap">${cvg.series.map(x => `<label class="check inline"><input type="checkbox" data-cvs="${fesc(x.name)}"${on.includes(x.name) ? " checked" : ""}> ${fesc(x.name)}</label>`).join("")}` +
      `<span class="hint fr-cvgn"></span></div><div class="fr-cvgplot"></div>`;
    box.querySelectorAll("[data-cvs]").forEach(el => el.onchange = () => {
      FA.cvgOn = [...box.querySelectorAll("[data-cvs]:checked")].map(x => x.dataset.cvs);
      renderCvg(box, box._cvg);
    });
  }
  box._cvg = cvg;
  const n = cvg.series[0].t.length;
  box.querySelector(".fr-cvgn").textContent = `${n} iteration(s), ${cvg.incs.length} increment attempt(s); residual force and displacement correction in % of the convergence limit, dashed lines at the start of each attempt`;
  TH.plot(box.querySelector(".fr-cvgplot"), cvg.series.filter(x => on.includes(x.name)),
    { xlabel: "iteration", xname: "iteration", ylog: true, xint: true, marks: cvg.incs.map(m => ({ t: m[0], title: `step ${m[1]}, increment ${m[2]}, attempt ${m[3]}` })) });
}

/** Solver output into box (built once): the text of solver.log with Follow (scrolled to the end at each update)
 *  and the link to the whole file. */
function renderLog(box, text, name, title) {
  if (!box) return;
  if (!box.querySelector(".fr-log")) {
    box.innerHTML = (title ? `<h3 class="xp-h">Solver output</h3>` : "") + `<div class="row wrap"><label class="check inline"><input type="checkbox" class="fr-logfollow" checked> Follow</label>` +
      `<button type="button" class="small fr-logopen" title="The whole solver.log in a new tab">Open solver.log</button><span class="hint fr-lognote"></span></div><pre class="xp-log fr-log"></pre>`;
    box.querySelector(".fr-logopen").onclick = () => window.open("/api/analysis/log/" + encodeURIComponent(name), "_blank");
  }
  const pre = box.querySelector(".fr-log");
  if (pre.textContent !== text) {
    pre.textContent = text || "";
    if (box.querySelector(".fr-logfollow").checked) pre.scrollTop = pre.scrollHeight;
  }
  box.querySelector(".fr-lognote").textContent = text && text.length >= 24000 ? "last 24 kB; the messages of the input reading are written when the solver exits" : "the messages of the input reading are written when the solver exits";
}

/** Run monitor of a running solve (FA.live, read every 1.5 s on the server): the stage of the solver and the last
 *  increment of job.sta; elapsed time, CPU use, memory and the estimate of the remaining time; the stages of the run;
 *  the convergence of the iterations (job.cvg); the curves of the history requests and of the increments; the solver
 *  output. The box is built once and updated at each poll; failed: the solver stopped with an error. */
function renderLive(box, failed) {
  const L = FA.live;
  if (!box || !L) return;
  if (!box.querySelector("#fr-live")) {
    box.innerHTML = `<div id="fr-live"><h3 class="xp-h" id="fr-lvhead">Run monitor</h3><p class="hint" id="fr-lvstage"></p><p class="hint" id="fr-lvproc"></p>` +
      `<p class="hint" id="fr-lvstages"></p><div id="fr-lvcvg"></div><div id="fr-lvth"></div><div id="fr-lvlog"></div></div>`;
  }
  $("#fr-lvhead").textContent = failed ? "Run monitor: the solver stopped with an error" : L.final ? "Run monitor: finished" : "Run monitor";
  $("#fr-lvstage").textContent = liveStageText(L);
  $("#fr-lvproc").textContent = liveProcText(L, !!L.final);
  $("#fr-lvstages").textContent = liveStagesText(L);
  renderCvg($("#fr-lvcvg"), L.cvg);
  const th = L.time_history || [];
  const tb = $("#fr-lvth");
  if (th.length) {
    const q = th.find(x => x.id === FA.thReq) || th[0];
    const on = (FA.thOn || {})[q.id] || q.series.slice(0, 1).map(x => x.name);
    const key = th.map(x => x.id).join("|") + "|" + q.id + "|" + q.series.map(x => x.name).join("|");
    if (tb._key !== key) {
      tb._key = key;
      tb.innerHTML = `<h3 class="xp-h">Time history</h3><div class="row wrap"><label class="inline">Request<select id="fr-lvreq">${th.map(x => `<option value="${fesc(x.id)}"${x === q ? " selected" : ""}>${fesc(x.name)}</option>`).join("")}</select></label></div>` +
        `<div class="row wrap">${q.series.map(x => `<label class="check inline"><input type="checkbox" data-lvs="${fesc(x.name)}"${on.includes(x.name) ? " checked" : ""}> ${fesc(x.name)}</label>`).join("")}</div><div id="fr-lvplot"></div>`;
      $("#fr-lvreq").onchange = () => { FA.thReq = $("#fr-lvreq").value; tb._key = null; renderLive(box, failed); };
      tb.querySelectorAll("[data-lvs]").forEach(el => el.onchange = () => {
        FA.thOn = FA.thOn || {};
        FA.thOn[q.id] = [...tb.querySelectorAll("[data-lvs]:checked")].map(x => x.dataset.lvs);
        renderLive(box, failed);
      });
    }
    TH.plot($("#fr-lvplot"), q.series.filter(x => on.includes(x.name)));
  } else tb.innerHTML = "";
  renderLog($("#fr-lvlog"), L.log, FA.jobName || "", true);
}

/** Time history of the result (history requests): the chosen request, its curves, a click picks the nearest
 *  increment state. */
function bindTimeHistory(r) {
  const q = r.time_history.find(x => x.id === FA.thReq) || r.time_history[0];
  FA.thOn = FA.thOn || {};
  const on = () => FA.thOn[q.id] || q.series.slice(0, 1).map(x => x.name);
  const incs = r.increments || [];
  const cur = incs.find(x => x.state === $("#fa-state").value);
  const draw1 = () => TH.plot($("#fr-thplot"), q.series.filter(x => on().includes(x.name)), {
    mark: cur ? cur.time : null,
    onPick: t => {
      if (!incs.length) return;
      let best = incs[0];
      for (const x of incs) if (Math.abs(x.time - t) < Math.abs(best.time - t)) best = x;
      $("#fa-state").value = best.state; draw(); renderResults();
    } });
  draw1();
  $("#fr-threq").onchange = () => { FA.thReq = $("#fr-threq").value; renderResults(); };
  document.querySelectorAll("#fa-results [data-ths]").forEach(el => el.onchange = () => {
    FA.thOn[q.id] = [...document.querySelectorAll("#fa-results [data-ths]:checked")].map(x => x.dataset.ths);
    draw1();
  });
  $("#fr-thcsv").onclick = () => TH.download(`${r.name}_${q.name}.csv`.replace(/[^A-Za-z0-9_.\-]+/g, "_"), TH.csv(q.series.filter(x => on().includes(x.name))));
}

// ------------------------------------------------------------------ history requests

function renderHist() {
  HR.render({ doc: () => FA.doc, solver: "calculix", sel: SH, nid, num: fnum, changed, rerender: () => { renderAll(); draw(); }, targetText }, $("#fa-hist"));
}

/** Series of the load history: [{key, name, v: [value per increment]}]. */
function historySeries(hs) {
  const R = hs.rows, out = [{ key: "time", name: "step time", v: R.map(x => x.time) }, { key: "umax", name: "max |u| (mm)", v: R.map(x => x.umax) }];
  hs.supports.forEach((n, i) => {
    ["Fx", "Fy", "Fz"].forEach((c, d) => out.push({ key: `r${i}_${d}`, name: `${n} ${c} (N)`, v: R.map(x => x.reactions[i][d]) }));
    out.push({ key: `r${i}_m`, name: `${n} |F| (N)`, v: R.map(x => Math.hypot(...x.reactions[i])) });
  });
  hs.points.forEach((n, i) => {
    ["ux", "uy", "uz"].forEach((c, d) => out.push({ key: `p${i}_${d}`, name: `${n} ${c} (mm)`, v: R.map(x => x.points[i][d]) }));
    out.push({ key: `p${i}_m`, name: `${n} |u| (mm)`, v: R.map(x => Math.hypot(...x.points[i])) });
  });
  out.push({ key: "vmmax", name: "max von Mises (MPa)", v: R.map(x => x.vmmax) });
  if (R.some(x => x.pemax > 0)) out.push({ key: "pemax", name: "max PEEQ", v: R.map(x => x.pemax) });
  return out;
}
function plotHistory() {
  const box = $("#fr-hplot"), hs = FA.res && FA.res.history;
  if (!box || !hs) return;
  const ser = historySeries(hs);
  const X = ser.find(q => q.key === (FA.histX || "time")) || ser[0], Y = ser.find(q => q.key === (FA.histY || ser[1].key)) || ser[1];
  const W = Math.max(280, box.clientWidth || 420), H = 220, L = 62, Rm = 10, T = 10, B = 30;
  const lo = a => Math.min(0, ...a), hi = a => { const m = Math.max(0, ...a), n = lo(a); return m > n ? m : n + 1; };
  const x0 = lo(X.v), x1 = hi(X.v), y0 = lo(Y.v), y1 = hi(Y.v);
  const px = v => L + (v - x0) / (x1 - x0) * (W - L - Rm), py = v => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  const st = $("#fa-state").value;
  let g = `<svg width="${W}" height="${H}" class="fa-hsvg">`;
  for (let k = 0; k <= 4; k++) {
    const xv = x0 + (x1 - x0) * k / 4, yv = y0 + (y1 - y0) * k / 4;
    g += `<line x1="${L}" x2="${W - Rm}" y1="${py(yv)}" y2="${py(yv)}" stroke="#e9ecef"/><text x="${L - 4}" y="${py(yv) + 4}" text-anchor="end">${ffmt(yv, 3)}</text>`;
    g += `<line y1="${T}" y2="${H - B}" x1="${px(xv)}" x2="${px(xv)}" stroke="#e9ecef"/><text x="${px(xv)}" y="${H - B + 14}" text-anchor="middle">${ffmt(xv, 3)}</text>`;
  }
  g += `<polyline fill="none" stroke="#1f5fae" stroke-width="1.6" points="${X.v.map((v, i) => px(v).toFixed(1) + "," + py(Y.v[i]).toFixed(1)).join(" ")}"/>`;
  hs.rows.forEach((r, i) => { g += `<circle data-hst="${r.state}" cx="${px(X.v[i])}" cy="${py(Y.v[i])}" r="${r.state === st ? 5 : 3.5}" fill="${r.state === st ? "#f08c00" : "#1f5fae"}" style="cursor:pointer"><title>${fesc(stateName(r.state))}</title></circle>`; });
  g += `<text x="${W - Rm}" y="${H - 3}" text-anchor="end">${fesc(X.name)}</text><text x="4" y="${T + 2}">${fesc(Y.name)}</text></svg>`;
  box.innerHTML = g;
  box.querySelectorAll("[data-hst]").forEach(c => c.onclick = () => { $("#fa-state").value = c.dataset.hst; draw(); renderResults(); });
}

function setStates() {
  const sel = $("#fa-state");
  const sts = !FA.res || !FA.res.states ? [] : modeResult() ? FA.res.states : ["total", "preload", "loads"].filter(s => FA.res.states.includes(s))
    .concat(FA.res.states.filter(s => /^s\d+$/.test(s))).concat((FA.res.increments || []).map(x => x.state));
  sel.innerHTML = sts.map(s => `<option value="${s}">${fesc(stateName(s))}</option>`).join("");
  sel.disabled = sts.length < 2;
}

// ------------------------------------------------------------------ run

/** Mesh view data ({payload, summary}) of a solve run: shown (Show Mesh) while the solver runs or after an error. */
function showMesh(m) {
  FA.res = null; setStates();
  FA.mesh = m.payload;
  FA.mesh._summary = m.summary;
  $("#fa-show").value = "mesh";
  renderResults(); draw();
}
async function runJob(meshOnly) {
  if (FA.job) return;
  const name = (FA.doc.name || "analysis").replace(/[^A-Za-z0-9_\-.]+/g, "_");
  try {
    const j = await (await postJSON("/api/analysis/run", { name, analysis: FA.doc, mesh_only: !!meshOnly })).json();
    FA.job = j.job;
    FA.jobName = name;
    FA.live = null; FA.liveFailed = false;
  } catch (e) { showErr(e); return; }
  $("#fa-cancel").disabled = false;
  $("#fa-solve").disabled = $("#fa-mesh").disabled = true;
  status(meshOnly ? "Meshing" : "Solving");
  const keys = {};
  for (const x of FA.doc.supports.concat(FA.doc.loads)) keys[x.id] = itemKey(x);
  const t0 = Date.now();
  const poll = async () => {
    let s;
    try { s = await (await api("/api/analysis/job/" + FA.job)).json(); } catch (e) { s = { state: "error", error: e.message }; }
    if (s.mesh) { FA.meshKeys = keys; showMesh(s.mesh); }
    if (s.state === "running") {
      $("#fa-info").textContent = `${s.message || s.stage} … ${Math.round((Date.now() - t0) / 1000)} s`;
      if (s.live) { FA.live = s.live; renderLive($("#fa-results")); }
      setTimeout(poll, 700);
      return;
    }
    FA.job = null;
    $("#fa-cancel").disabled = true;
    $("#fa-solve").disabled = $("#fa-mesh").disabled = false;
    if (s.state === "error") {
      $("#fa-info").textContent = "";
      status(s.error, true);
      if (s.live) { FA.live = s.live; FA.liveFailed = true; renderLive($("#fa-results"), true); } else FA.live = null;
      return;
    }
    FA.live = null;
    const r = s.result;
    FA.res = null;
    FA.meshKeys = keys;
    FA.mesh = r.payload;
    FA.mesh._summary = r.summary;
    if (r.mesh_only) {
      setStates();
      $("#fa-show").value = "mesh";
      status(`Mesh: ${r.summary.nodes} nodes, ${r.summary.elements} elements (${r.summary.bodies.map(b => b.types.join(" + ")).filter(Boolean).join(", ") || "members"}); input file ${r.files.inp}`);
    } else {
      FA.res = r;
      FA.probes = []; FA.path = null; FA.probeMode = null;
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
  const cur = s.type === "inp" ? "inp:" + (s.path || "") : s.name ? s.type + ":" + s.name : "";
  $("#fa-source").innerHTML = `<option value="">(none: members and plates)</option>` +
    (asms.length ? `<optgroup label="Assemblies">${asms.map(n => `<option value="assembly:${fesc(n)}">${fesc(n)}</option>`).join("")}</optgroup>` : "") +
    (parts.length ? `<optgroup label="Parts">${parts.map(n => `<option value="part:${fesc(n)}">${fesc(n)}</option>`).join("")}</optgroup>` : "") +
    `<optgroup label="Mesh file">${s.type === "inp" ? `<option value="${fesc(cur)}" title="${fesc(s.path || "")}">${fesc(s.name || s.path)}</option>` : ""}` +
    `<option value="inp:">Import CalculiX .inp or Radioss .rad…</option></optgroup>`;
  if (cur && ![...$("#fa-source").options].some(o => o.value === cur)) $("#fa-source").insertAdjacentHTML("beforeend", `<option value="${fesc(cur)}">${fesc(s.name)} (missing)</option>`);
  $("#fa-source").value = cur;
}

async function loadDoc(d, saved) {
  const b = blankDoc(d.name);
  for (const k of Object.keys(b)) if (d[k] === undefined) d[k] = b[k];
  FA.doc = d;
  if ($("#fa-solver")) $("#fa-solver").value = d.solver === "explicit" ? "explicit" : "calculix";
  if (d.solver === "explicit" && window.__xpAttach) {
    // solver OpenCourant: the document in the explicit pane of the tab
    FA.dirty = false;
    await window.__xpAttach(d, saved);
    if (!$("#tab-fea").hidden) showTab("xp");
    return;
  }
  FA.sel = null; FA.pick = null; FA.mesh = null; FA.res = null; FA.probes = []; FA.path = null; FA.probeMode = null; FA.bodyHide = new Set(); VS.clear(SH); SM.selState(SH).collect = null; VS.renderBar(SH);
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
  if (FA.doc && FA.doc.solver === "explicit" && window.__xpAttach) { showTab("xp"); return; }   // solver OpenCourant: the explicit pane
  if (!FA.three) initThree();
  MS.installLibraryPick($("#tab-fea"), addLibraryMaterial);
  if (!FA.solver) { try { FA.solver = await (await api("/api/analysis/solver")).json(); } catch (e) { FA.solver = {}; } }
  if (!FA.doc) await loadDoc(blankDoc("analysis"));
  refreshList();
  renderAll();
  checkGeometry();
  setTimeout(resize3, 0);
};

(function bindFea() {
  VS.renderBar(SH, $("#fa-selbar"));
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && FA.pick && !$("#tab-fea").hidden) { endPick(); status("Pick cancelled"); }
    else if ((e.key === "Escape" || (e.key === "Enter" && !e.target.closest("input, textarea, select"))) && !$("#tab-fea").hidden && VS.key(SH, e)) e.preventDefault();
  });
  $("#fa-source").onchange = () => {
    const v = $("#fa-source").value;
    if (v === "inp:") { chooseInp(); return; }
    if (v.startsWith("inp:")) return;
    const i = v.indexOf(":");
    FA.doc.source = v ? { type: v.slice(0, i), name: v.slice(i + 1) } : { type: "assembly", name: "" };
    FA.mesh = null; FA.res = null; setStates();
    $("#fa-show").value = "model";
    changed(); loadGeometry();
  };
  $("#fa-update").onclick = updateGeometry;
  $("#fa-solver").onchange = async () => {
    if ($("#fa-solver").value !== "explicit") return;
    FA.doc.solver = "explicit";
    changed();
    const saved = FM && FM.isSaved();
    await window.__xpAttach(FA.doc, saved);
    if (saved) window.__feaDirty();
    showTab("xp");
    HO.handover(window.__feaPane, window.__xpPane);          // the view of this pane in the explicit pane
  };
  window.addEventListener("focus", checkGeometry);
  setInterval(checkGeometry, 4000);
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
  for (const id of ["#fa-show", "#fa-field", "#fa-scale", "#fa-undef", "#fa-edges", "#fa-thick", "#fa-axes", "#fa-bcs"]) $(id).onchange = () => {
    if ($("#fa-show").value !== "model" && !FA.mesh) { $("#fa-show").value = "model"; status("Mesh or solve first", true); }
    if ($("#fa-show").value === "results" && !FA.res) { $("#fa-show").value = FA.mesh ? "mesh" : "model"; status("Solve first", true); }
    draw();
    if (id === "#fa-field" && FA.res && ((FA.probes || []).length || (FA.path || []).length === 2)) renderResults();      // probe and path curves of the field
  };
  $("#fa-state").onchange = () => { draw(); renderResults(); };
  FM = docFileMenu({ pre: "fa", type: "analysis", label: "analysis", pane: "#tab-fea", listUrl: "/api/analysis/list",
    cur: () => (FA.doc ? { name: FA.doc.name, dirty: !!FA.dirty } : null),
    load: async name => loadDoc(await (await api("/api/analysis/file/" + encodeURIComponent(name))).json()),
    save: saveDoc, blank: () => loadDoc(blankDoc("analysis")), setName: name => { FA.doc.name = name; } });
  window.addEventListener("beforeunload", e => { if (FA.dirty) { e.preventDefault(); e.returnValue = ""; } });
})();

window.__fea = { FA, SH, renderResults, select: (k, id) => { FA.sel = k ? { kind: k, id } : null; renderAll(); draw(); } };
window.__feaLoadNamed = async function (name) {
  const d = await (await api("/api/analysis/file/" + encodeURIComponent(name))).json();
  if (FM) FM.markSaved(name);
  await loadDoc(d, true);
};
// one document with the explicit pane (solver OpenCourant, explicit.js)
window.__feaDirty = () => { FA.dirty = true; if (FM) FM.render(); };
window.__feaIsDirty = () => !!FA.dirty;
window.__feaSaveDoc = async name => { await saveDoc(name); if (FM) FM.markSaved(name); };
window.__feaNewDoc = async solver => { const d = blankDoc("analysis"); if (solver) d.solver = solver; if (FM) FM.markUnsaved(); await loadDoc(d); };
/** A document from the explicit pane (solver CalculiX): shown in this pane. */
/** View handover between the CalculiX and the OpenCourant pane (handoff.js). */
window.__feaPane = {
  ready: () => !!(FA.three && FA.geo && !$("#tab-fea").hidden),
  state: () => HO.state(FA.three, SM.selState(SH), FA.tree, $("#fa-panel")),
  apply: st => HO.apply(st, FA.three, SM.selState(SH), FA.tree, $("#fa-panel"), () => { resize3(); VS.renderBar(SH); draw(); }),
};
window.__feaAdopt = async (d, saved) => { if (FM) { if (saved) FM.markSaved(d.name); else FM.markUnsaved(); } await loadDoc(d, saved); if (!saved) FA.dirty = true; if (FM) FM.render(); };
window.__feaSetName = name => { if (FA.doc) { FA.doc.name = name; if (FM) FM.markSaved(name); } };
window.__feaRefresh = refreshList;
window.__feaCurrent = () => (FA.doc ? { name: FA.doc.name, dirty: !!FA.dirty } : null);
