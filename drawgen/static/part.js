// Part tab: feature tree (reference planes, bodies, sketches, planes, features), 3D view with element
// hover / selection (three.js), step-based command bar for every feature, live rebuild.
import * as THREE from "three";
import { TumbleControls } from "/static/vendor/TumbleControls.js";
import { updateAxes } from "/static/axes.js";
import { createNavCube } from "/static/navcube.js";

const PT = {
  part: null, sel: null, status: {}, mesh: null, surfaces: {}, solids: [], dirty: false,
  three: null, buildSeq: 0, buildTimer: null,
  cmd: null,             // active command: {id: feature id, step: index, isNew, pick: {prop, kinds, single} | null, regions}
  hover: null,           // element under the cursor
  hidden: {},            // element id -> true (bodies "solid:i", surface feature ids, sketch ids, plane ids)
  faceObjs: [], edgeLines: [], surfObjs: [], sketchObjs: [], planeObjs: [], pointObjs: [], axisObjs: [], regionObjs: [],
  cells: 0,
};
const TYPE_NAMES = { sketch: "Sketch", plane: "Plane", point: "Point", axis: "Axis", extrude: "Extrude", cut: "Cut", revolve: "Revolve", fillet: "Fillet", chamfer: "Chamfer",
                     shell: "Shell", pattern: "Pattern", mirror: "Mirror", boolean: "Boolean", hole: "Hole", thread: "Thread", sweep: "Sweep",
                     import: "Import STEP", place: "Place", split: "Partition", unify: "Merge faces", heal: "Heal", defeature: "Remove faces", offset_faces: "Offset faces", move_faces: "Move faces", combine: "Combine faces", hole_mesh: "Hole mesh", smooth: "Smooth surfaces", replace: "Replace faces",
                     surf_extract: "Extract surface", surf_fit: "Fit surface", surf_sketch: "Extruded surface", surf_loft: "Loft surface",
                     surf_fill: "Fill surface", surf_offset: "Offset surface", surf_sew: "Sew surfaces", surf_import: "Import surface", thicken: "Thicken", surf_cut: "Cut with surface",
                     curve_extract: "Extract curve", curve_section: "Intersection curve", surf_from_curve: "Surface from curve", surf_trim: "Trim surface", surf_extend: "Extend surface", surf_bridge: "Bridge surface" };
const SURFACE_TYPES = new Set(["surf_extract", "surf_fit", "surf_sketch", "surf_loft", "surf_fill", "surf_offset", "surf_sew", "surf_import", "curve_extract", "curve_section", "surf_from_curve", "surf_trim", "surf_extend", "surf_bridge"]);
const CURVE_TYPES = new Set(["curve_extract", "curve_section"]);
const SOLID_TYPES = new Set(["extrude", "cut", "revolve", "hole", "sweep", "fillet", "chamfer", "shell", "pattern", "mirror", "boolean", "import", "place", "split", "unify", "heal", "defeature", "smooth", "replace", "thicken", "surf_cut", "hole_mesh", "offset_faces", "move_faces"]);
const SPLIT_METHODS = { principal: "Principal plane + offset", datum: "Plane feature + offset", face: "Extend a face (planar or curved)", sketch: "Sketch extruded through the part",
                        edge: "Normal to an edge or curve", surface: "Surface body", point_normal: "Point and normal", three_points: "Three points", ogrid: "Around a hole (4 planes through the axis)" };
const POINT_METHODS = { coords: "Coordinates", edge: "On an edge or curve", face: "Centre of a face", offset: "Offset from a point", axis: "On an axis at a distance", axis_plane: "Axis and plane intersection", midpoint: "Midpoint of two points" };
const AXIS_METHODS = { point_dir: "Point and direction", two_points: "Two points", edge: "Straight edge or curve", cylinder: "Axis of a cylindrical face", planes: "Intersection of two planes", normal: "Normal to a plane", parallel: "Parallel to an axis through a point" };
const PLANE_METHODS = { principal: "Principal plane + offset", datum: "Parallel to a plane feature + offset", face: "Parallel to a planar face + offset",
                        midplane: "Midplane between two parallel faces", edge: "Normal to an edge or curve", angle: "Through an edge, at an angle to a face",
                        point_normal: "Point and normal (point and axis features, or values)", axis_point: "Through an axis and a point", normal_axis: "Normal to an axis at a point", three_points: "Three points" };
const SKETCH_TYPES = new Set(["extrude", "cut", "revolve", "hole", "sweep"]);
const BASE_PLANES = { XY: "Top (XY)", XZ: "Front (XZ)", YZ: "Right (YZ)" };
const PLANE_TXT = { XY: "Top (XY), normal +Z", XZ: "Front (XZ), normal -Y", YZ: "Right (YZ), normal +X", normal: "Normal to an edge or curve" };
const COL = { hover: 0x7ad17a, sel: 0x2bb24c, surf: 0x5b7fb5, curve: 0x6a1b9a, solid: 0xb8c2cf, edge: 0x1d2125, sketch: 0x7a4a9a, plane: 0x6c7a89, region: 0x3aa6d8, datum: 0x6a3fa0 };

function msgPart(text, isError) { status(text, isError); }
const pesc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const pfmt = (v, d = 3) => { let s = Number(v).toFixed(d).replace(/\.?0+$/, ""); return s === "-0" || s === "" ? "0" : s; };
const keyOfFace = k => k.c.join(",");
const keyOfEdge = k => k.mid.join(",");

const newUid = () => Array.from(crypto.getRandomValues(new Uint8Array(6)), b => b.toString(16).padStart(2, "0")).join("");
function blankPart(name) { return { name: name || "part", version: 2, features: [], next: 1, uid: newUid() }; }
function emptySketch() {
  return {
    name: "feature sketch", source: "", units: "mm", insunits: 4, scale: 1,
    layers: [{ name: "0", aci: 7, color: "#000000", linetype: "Continuous", lineweight: -1, on: true }],
    linetypes: [], current_layer: "0", entities: [], constraints: [], dims: [], next_id: 1,
    sheet: { page: "extents", title_block: false, origin: [0, 0] },
  };
}
function feat(id) { return PT.part.features.find(f => f.id === id); }
function featIndex(id) { return PT.part.features.findIndex(f => f.id === id); }
function newId() { return "f" + (PT.part.next++); }
function nextName(type) { return TYPE_NAMES[type] + " " + (PT.part.features.filter(f => f.type === type).length + 1); }
/** Items of a type above index i (candidates for references). */
function itemsAbove(i, pred) { return PT.part.features.filter((x, k) => k < i && !x.suppressed && pred(x)); }
function sketchItems(i) { return itemsAbove(i, x => x.type === "sketch"); }
function planeItems(i) { return itemsAbove(i, x => x.type === "plane"); }
function pointItems(i) { return itemsAbove(i, x => x.type === "point"); }
function axisItems(i) { return itemsAbove(i, x => x.type === "axis"); }
const refSelect = (id, label, items, cur, none) => select(id, label, [["", none || "(none)"]].concat(items.map(p => [p.id, p.name])), cur || "");
function surfaceItems(i, curves) { return itemsAbove(i, x => SURFACE_TYPES.has(x.type) && (curves === undefined || CURVE_TYPES.has(x.type) === curves)); }
/** Display name of a plane reference (XY / XZ / YZ or a plane feature id). */
function planeName(ref) { if (!ref) return "?"; if (BASE_PLANES[ref]) return BASE_PLANES[ref]; const f = feat(ref); return f ? f.name : ref; }
/** A vertex of the part used as a point reference is stored as its coordinates [x, y, z] (mm). */
const isVertexRef = v => Array.isArray(v) && v.length === 3 && v.every(x => typeof x === "number" && isFinite(x));
function itemName(id) { if (isVertexRef(id)) return "vertex (" + id.map(v => pfmt(v, 2)).join(", ") + ")"; if (BASE_PLANES[id]) return BASE_PLANES[id]; if (String(id).startsWith("solid:")) return "Solid " + (+id.slice(6) + 1); const f = feat(id); return f ? f.name : id; }

// ------------------------------------------------------------------ 3D view

function initThree() {
  const box = $("#pt-view");
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
  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.75);
  camera.add(d1);
  d1.position.set(1, 1, 2);
  scene.add(camera);
  const group = new THREE.Group();      // model: faces, edges, surfaces, sketches, planes
  scene.add(group);
  const overlay = new THREE.Group();    // highlights
  scene.add(overlay);
  updateAxes(scene, null, true);
  const tip = document.createElement("div");
  tip.className = "pt-tip";
  tip.hidden = true;
  box.appendChild(tip);
  PT.three = { renderer, scene, camera, controls, group, overlay, box, tip, zoomed: false };
  controls.addEventListener("change", render3);
  camera.userData.target = controls.target;
  PT.three.cube = createNavCube(box, camera, viewDir);
  let down = null;
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.abs(e.clientX - down[0]) + Math.abs(e.clientY - down[1]) > 4 || (e.button !== 0 && e.button !== 1)) { down = null; return; }
    down = null;
    if (e.button === 1) { setPivot(e); return; }
    clickView(e);
  });
  renderer.domElement.addEventListener("dblclick", e => { if (e.button === 0) dblclickView(e); });
  let clicks = [];
  renderer.domElement.addEventListener("pointerup", e => {
    if (e.button !== 0) return;
    const now = e.timeStamp;
    clicks = clicks.filter(t => now - t < 600); clicks.push(now);
    if (clicks.length >= 3) { clicks = []; if (PT.cmd && canFinish(feat(PT.cmd.id))) finishCommand(true); }
  });
  let moveReq = null;
  renderer.domElement.addEventListener("pointermove", e => {
    if (moveReq) return;
    moveReq = requestAnimationFrame(() => { moveReq = null; hoverView(e); });
  });
  renderer.domElement.addEventListener("pointerleave", () => { setHover(null); });
  new ResizeObserver(resize3).observe(box);
  resize3();
}

function resize3() {
  const t = PT.three;
  if (!t) return;
  const w = t.box.clientWidth || 1, h = t.box.clientHeight || 1;
  t.renderer.setSize(w, h);
  const c = t.camera, half = (c.top - c.bottom) / 2 || 100;
  c.left = -half * w / h; c.right = half * w / h;
  c.updateProjectionMatrix();
  render3();
}
function render3() { const t = PT.three; if (!t) return; t.renderer.render(t.scene, t.camera); if (t.cube) t.cube.render(); }

/** Turns the camera to look along -dir (dir: from the target to the camera) with the given up vector; the target, the
 *  distance and the zoom are kept. Used by the navigation cube. */
/** View along dir (direction from the target to the camera). The up vector is the axis direction perpendicular
 *  to dir that is nearest to the current screen up, so a view that is nearly square is only squared up. */
function viewDir(dir, up) {
  const t = PT.three;
  if (!t) return;
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
  t.camera.position.copy(t.controls.target.clone().add(dir.clone().normalize().multiplyScalar(dist)));
  t.controls.update();
  render3();
}

/** A mesh of the given face indices of a mesh record. */
function facesGeometry(m, faceSet) {
  const tri = [];
  m.triangles.forEach((tr, i) => { if (faceSet.has(m.face_of_tri[i])) tri.push(...tr); });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(m.vertices.flat(), 3));
  g.setIndex(tri);
  g.computeVertexNormals();
  return g;
}

/** Rebuilds the scene from the current mesh, surfaces, sketches and planes. */
function setMesh(m) {
  const t = PT.three;
  t.group.clear();
  PT.mesh = m;
  PT.faceObjs = []; PT.edgeLines = []; PT.surfObjs = []; PT.sketchObjs = []; PT.planeObjs = []; PT.pointObjs = []; PT.axisObjs = [];
  updateAxes(t.scene, m && m.bbox, $("#pt-axes").checked);
  if (PT.meshPreview) { t.scene.remove(PT.meshPreview); PT.meshPreview = null; if ($("#pt-meshinfo")) $("#pt-meshinfo").hidden = true; }
  if (m && m.vertices.length) {
    // one mesh per solid cell (hidden cells are skipped)
    const nSolids = Math.max(0, ...m.face_solid) + 1;
    for (let si = 0; si < nSolids; si++) {
      if (PT.hidden["solid:" + si]) continue;
      const faces = new Set();
      m.face_solid.forEach((s, fi) => { if (s === si) faces.add(fi); });
      const g = facesGeometry(m, faces);
      const seeThrough = !!(PT.cmd && PT.cmd.regions);
      const mat = new THREE.MeshStandardMaterial({ color: COL.solid, metalness: 0.15, roughness: 0.6, side: THREE.DoubleSide, transparent: seeThrough, opacity: seeThrough ? 0.3 : 1, depthWrite: !seeThrough,
                                                   polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
      const mesh = new THREE.Mesh(g, mat);
      mesh.userData = { kind: "solid", solid: si, faces };
      t.group.add(mesh);
      PT.faceObjs.push(mesh);
    }
    if ($("#pt-edges").checked) {
      m.edges.forEach((pl, i) => {
        // edges of hidden solids are hidden (an edge shared with a visible solid stays)
        const owners = (m.edge_solids || [])[i] || [];
        if (owners.length && owners.every(si => PT.hidden["solid:" + si])) return;
        const eg = new THREE.BufferGeometry();
        eg.setAttribute("position", new THREE.Float32BufferAttribute(pl.flat(), 3));
        const line = new THREE.Line(eg, new THREE.LineBasicMaterial({ color: COL.edge }));
        line.userData = { kind: "edge", index: i, key: m.edge_keys[i] };
        t.group.add(line);
        PT.edgeLines.push(line);
      });
    }
  }
  drawSurfaces();
  drawSketches();
  drawPlanes(); drawDatums();
  drawRegions();
  applyClipping();
  if (PT.section) refreshSectionCap();
  drawSelection();
  // first display of a part: fit the view (an empty part: the reference planes)
  if (!t.zoomed) { view("iso"); t.zoomed = true; } else render3();
}

/** Surface and curve bodies. */
function drawSurfaces() {
  const t = PT.three;
  const trimming = PT.cmd && PT.cmd.regions && feat(PT.cmd.id);
  for (const [id, sm] of Object.entries(PT.surfaces || {})) {
    if (PT.hidden[id]) continue;
    const f = feat(id);
    if (!f || f.suppressed) continue;
    if (trimming && trimming.source === id) continue;
    const isCurve = !sm.triangles.length;
    if (!isCurve) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(sm.vertices.flat(), 3));
      g.setIndex(sm.triangles.flat());
      g.computeVertexNormals();
      const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: COL.surf, transparent: true, opacity: 0.45, side: THREE.DoubleSide, depthWrite: false,
                                                                     polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }));
      mesh.renderOrder = 2;
      mesh.userData = { kind: "surface", id };
      t.group.add(mesh);
      PT.surfObjs.push(mesh);
    }
    if (isCurve) {
      const pos = [];
      for (const pl of sm.edges) for (let k = 0; k + 1 < pl.length; k++) pos.push(...pl[k], ...pl[k + 1]);
      if (pos.length) {
        const eg = new THREE.BufferGeometry();
        eg.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
        const line = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: COL.curve, depthTest: false }));
        line.renderOrder = 6; line.userData = { kind: "curve", id }; PT.surfObjs.push(line);
        t.group.add(line);
      }
    } else {
      // one pickable line per edge of the surface body
      sm.edges.forEach((pl, i) => {
        const eg = new THREE.BufferGeometry();
        eg.setAttribute("position", new THREE.Float32BufferAttribute(pl.flat(), 3));
        const line = new THREE.Line(eg, new THREE.LineBasicMaterial({ color: 0x3a5a8a }));
        line.userData = { kind: "edge", key: (sm.edge_keys || [])[i], surface: id, polyline: pl };
        t.group.add(line);
        PT.edgeLines.push(line);
      });
    }
  }
}

// sketch plane (u, v) -> 3D for a sketch item (frame from the build; offset along the normal)
function frameOf(item) {
  const fr = (PT.status[item.id] || {}).frame;
  if (fr) return fr;
  const base = { XY: { o: [0, 0, 0], x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] }, XZ: { o: [0, 0, 0], x: [1, 0, 0], y: [0, 0, 1], z: [0, -1, 0] }, YZ: { o: [0, 0, 0], x: [0, 1, 0], y: [0, 0, 1], z: [1, 0, 0] } };
  return base[item.plane] || null;
}
function to3(item, u, v) {
  const fr = frameOf(item);
  if (!fr) return [0, 0, 0];
  const off = item.type === "sketch" ? (+item.offset || 0) : 0;
  return [0, 1, 2].map(k => fr.o[k] + fr.x[k] * u + fr.y[k] * v + fr.z[k] * off);
}

function sketchPolylines(sk) {
  const out = [];
  for (const e of (sk && sk.entities) || []) {
    if (e.t === "line") out.push([[e.x1, e.y1], [e.x2, e.y2]]);
    else if (e.t === "circle" || e.t === "arc") {
      const a0 = e.t === "circle" ? 0 : e.a0;
      let span = e.t === "circle" ? 360 : ((e.a1 - e.a0) % 360 + 360) % 360 || 360;
      const n = Math.max(12, Math.ceil(span / 6)), pl = [];
      for (let i = 0; i <= n; i++) { const a = (a0 + span * i / n) * Math.PI / 180; pl.push([e.cx + e.r * Math.cos(a), e.cy + e.r * Math.sin(a)]); }
      out.push(pl);
    } else if (e.t === "poly") out.push(e.closed ? e.pts.concat([e.pts[0]]) : e.pts);
    else if (e.t === "ellipse") {
      const a0 = e.a0 || 0, a1 = e.a1 === undefined ? 0 : e.a1;
      let span = ((a1 - a0) % 360 + 360) % 360; if (span < 1e-9) span = 360;
      const rot = (e.rot || 0) * Math.PI / 180, n = Math.max(24, Math.ceil(span / 4)), pl = [];
      for (let i = 0; i <= n; i++) {
        const tt = (a0 + span * i / n) * Math.PI / 180, x = e.rx * Math.cos(tt), y = e.ry * Math.sin(tt);
        pl.push([e.cx + x * Math.cos(rot) - y * Math.sin(rot), e.cy + x * Math.sin(rot) + y * Math.cos(rot)]);
      }
      out.push(pl);
    } else if (e.t === "spline" && window.splinePolyE) out.push(window.splinePolyE(e, 12));
    else if (e.t === "conic" && window.conicPolyE) out.push(window.conicPolyE(e, 32));
    else if (e.t === "point") out.push([[e.x - 1, e.y], [e.x + 1, e.y]], [[e.x, e.y - 1], [e.x, e.y + 1]]);
  }
  return out;
}

/** Sketch items as curves in the view (construction geometry dashed blue). */
function drawSketches() {
  const t = PT.three;
  if (!$("#pt-showsketch").checked) return;
  for (const item of PT.part.features) {
    if (item.type !== "sketch" || item.suppressed || PT.hidden[item.id]) continue;
    const sk = item.sketch || {};
    const pos = [], cpos = [];
    for (const e of sk.entities || []) {
      if (e.axis) continue;
      const pls = sketchPolylines({ entities: [e] });
      for (const pl of pls) for (let i = 0; i + 1 < pl.length; i++) (e.constr ? cpos : pos).push(...to3(item, ...pl[i]), ...to3(item, ...pl[i + 1]));
    }
    const add = (arr, color, dashed) => {
      if (!arr.length) return null;
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(arr, 3));
      const mat = dashed ? new THREE.LineDashedMaterial({ color, dashSize: 2, gapSize: 1.5, depthTest: false }) : new THREE.LineBasicMaterial({ color, depthTest: false });
      const l = new THREE.LineSegments(g, mat);
      if (dashed) l.computeLineDistances();
      l.renderOrder = 8;
      l.userData = { kind: "sketch", id: item.id };
      t.group.add(l);
      return l;
    };
    const a = add(pos, COL.sketch, false);
    if (a) PT.sketchObjs.push(a);
    add(cpos, 0x2f74d0, true);
  }
}

function planeLabel(text, color) {
  const c = document.createElement("canvas");
  c.width = 256; c.height = 64;
  const g = c.getContext("2d");
  g.font = "bold 34px sans-serif"; g.textAlign = "right"; g.textBaseline = "middle"; g.fillStyle = color;
  g.fillText(text, 250, 32);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false, depthWrite: false, transparent: true }));
  sp.renderOrder = 1002;
  return sp;
}

/** Point features (markers) and axis features (dash-dot lines) in the view. */
function drawDatums() {
  const t = PT.three;
  if (!$("#pt-planes").checked) return;
  const s = planeSize();
  for (const f of PT.part.features) {
    if ((f.type !== "point" && f.type !== "axis") || f.suppressed || PT.hidden[f.id]) continue;
    const st = PT.status[f.id] || {};
    if (f.type === "point" && st.point) {
      const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...st.point)]);
      const p = new THREE.Points(g, new THREE.PointsMaterial({ color: COL.datum, size: 9, sizeAttenuation: false, depthTest: false }));
      p.userData = { kind: "point", id: f.id, point: st.point };
      p.renderOrder = 8;
      t.group.add(p); PT.pointObjs.push(p);
      // cross marker
      const L = s * 0.06, q = st.point, pos = [];
      for (const d of [[1, 0, 0], [0, 1, 0], [0, 0, 1]]) pos.push(q[0] - d[0] * L, q[1] - d[1] * L, q[2] - d[2] * L, q[0] + d[0] * L, q[1] + d[1] * L, q[2] + d[2] * L);
      const cg = new THREE.BufferGeometry(); cg.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      const cl = new THREE.LineSegments(cg, new THREE.LineBasicMaterial({ color: COL.datum, depthTest: false }));
      cl.renderOrder = 8; t.group.add(cl);
      const sp = planeLabel(f.name, "#6a3fa0"); sp.position.set(q[0] + L * 1.2, q[1], q[2] + L * 1.2); sp.scale.set(s * 0.6, s * 0.15, 1); sp.center.set(0, 0.5); t.group.add(sp);
    } else if (f.type === "axis" && st.axis) {
      const { o, d } = st.axis, L = s * 1.6;
      const a = [o[0] - d[0] * L, o[1] - d[1] * L, o[2] - d[2] * L], b = [o[0] + d[0] * L, o[1] + d[1] * L, o[2] + d[2] * L];
      const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...a), new THREE.Vector3(...b)]);
      const ln = new THREE.Line(g, new THREE.LineDashedMaterial({ color: COL.datum, dashSize: s * 0.12, gapSize: s * 0.05, depthTest: false }));
      ln.computeLineDistances();
      ln.userData = { kind: "axis", id: f.id, polyline: [a, b] };
      ln.renderOrder = 8;
      t.group.add(ln); PT.axisObjs.push(ln);
      const sp = planeLabel(f.name, "#6a3fa0"); sp.position.set(...b); sp.scale.set(s * 0.6, s * 0.15, 1); sp.center.set(0, 0.5); t.group.add(sp);
    }
  }
}

function planeSize() {
  const bb = PT.mesh && PT.mesh.bbox;
  return bb ? Math.max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]) * 0.45 + 5 : 40;
}

/** Reference planes (XY, XZ, YZ when visible) and plane features as translucent squares. */
function drawPlanes() {
  const t = PT.three;
  if (!$("#pt-planes").checked) return;
  const s = planeSize();
  const items = [];
  for (const k of Object.keys(BASE_PLANES)) if (!PT.hidden[k]) items.push({ id: k, name: BASE_PLANES[k], fr: frameOf({ plane: k }), base: true });
  for (const f of PT.part.features) {
    if (f.type !== "plane" || f.suppressed || PT.hidden[f.id]) continue;
    const fr = (PT.status[f.id] || {}).frame;
    if (fr) items.push({ id: f.id, name: f.name, fr });
  }
  for (const it of items) {
    const fr = it.fr;
    const P = (u, v) => [0, 1, 2].map(k => fr.o[k] + fr.x[k] * u + fr.y[k] * v);
    const q = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => P(a * s, b * s));
    const pg = new THREE.BufferGeometry();
    pg.setAttribute("position", new THREE.Float32BufferAttribute([...q[0], ...q[1], ...q[2], ...q[0], ...q[2], ...q[3]], 3));
    const mesh = new THREE.Mesh(pg, new THREE.MeshBasicMaterial({ color: COL.plane, transparent: true, opacity: it.base ? 0.03 : 0.07, side: THREE.DoubleSide, depthWrite: false }));
    mesh.userData = { kind: "plane", id: it.id, corners: q };
    t.group.add(mesh);
    PT.planeObjs.push(mesh);
    const lg = new THREE.BufferGeometry().setFromPoints([...q, q[0]].map(p => new THREE.Vector3(...p)));
    const ln = new THREE.Line(lg, new THREE.LineBasicMaterial({ color: COL.plane, transparent: true, opacity: it.base ? 0.35 : 0.6, depthTest: false }));
    ln.renderOrder = 7;
    t.group.add(ln);
    const sp = planeLabel(it.name, it.base ? "#8a94a3" : "#4a5563");
    sp.position.set(...P(s * 0.97, s * 0.9));
    sp.scale.set(s * 0.9, s * 0.22, 1);
    sp.center.set(1, 0.5);
    t.group.add(sp);
  }
}

/** Trim regions (pieces) during the Regions step of a trim command. */
function drawRegions() {
  const t = PT.three;
  for (const o of PT.regionObjs) t.group.remove(o);
  PT.regionObjs = [];
  const c = PT.cmd;
  if (!c || !c.regions) return;
  const f = feat(c.id);
  const removed = new Set((f.remove || []).map(p => p.join(",")));
  const selectMode = c.regionMode === "select";
  const selected = new Set((f.regions || []).map(p => p.join(",")));
  c.regions.forEach((rg, i) => {
    if (!rg.mesh.triangles.length) return;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(rg.mesh.vertices.flat(), 3));
    g.setIndex(rg.mesh.triangles.flat());
    g.computeVertexNormals();
    // trim: kept green, removed red; profile regions: picked green, the others grey (none picked: all grey-green)
    let color, opacity;
    if (selectMode) { const on = selected.has((rg.uv || []).join(",")); color = on ? COL.region : 0x9aa5b1; opacity = on ? 0.7 : (selected.size ? 0.25 : 0.4); }
    else { const isRemoved = removed.has(rg.point.join(",")); color = isRemoved ? 0xd9534f : COL.region; opacity = isRemoved ? 0.25 : 0.7; }
    const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide,
                                                                   polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
    mesh.renderOrder = 4;
    mesh.userData = { kind: "region", index: i, point: rg.point, uv: rg.uv, area: rg.area };
    t.group.add(mesh);
    PT.regionObjs.push(mesh);
  });
}

/** Highlights: the selected tree item (green) and the references of the active command step (orange). */
function drawSelection() {
  const t = PT.three;
  t.overlay.clear();
  const m = PT.mesh;
  const selFaces = new Set();
  const selEdges = new Set();
  const paint = (faces, color, opacity, order) => {
    if (!m || !faces.size) return;
    const mesh = new THREE.Mesh(facesGeometry(m, faces), new THREE.MeshBasicMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false,
                                                                                       polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }));
    mesh.renderOrder = order || 3;
    t.overlay.add(mesh);
  };
  const paintEdges = (keys, color) => {
    const pos = [];
    for (const ln of PT.edgeLines) {
      const k = ln.userData.key;
      if (!k || !keys.has(keyOfEdge(k))) continue;
      const pl = ln.userData.polyline || (m && m.edges[ln.userData.index]);
      if (pl) for (let j = 0; j + 1 < pl.length; j++) pos.push(...pl[j], ...pl[j + 1]);
    }
    if (!pos.length) return;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    const l = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color, depthTest: false, linewidth: 2 }));
    l.renderOrder = 9;
    t.overlay.add(l);
  };
  // the selected tree item
  const id = PT.sel;
  if (id && m) {
    if (String(id).startsWith("solid:")) { const si = +id.slice(6); m.face_solid.forEach((s, fi) => { if (s === si) selFaces.add(fi); }); }
    else (m.face_owner || []).forEach((o, fi) => { if (o === id) selFaces.add(fi); });
  }
  paint(selFaces, COL.sel, 0.45);
  drawMeasure(paint);
  if (id && PT.surfaces[id] && !PT.hidden[id]) paintSurface(id, COL.sel, 0.6);
  if (id && (BASE_PLANES[id] || (feat(id) && feat(id).type === "plane"))) paintPlane(id, COL.sel);
  if (id && feat(id) && feat(id).type === "sketch") paintSketch(id, COL.sel);
  if (id && feat(id) && (feat(id).type === "point" || feat(id).type === "axis")) paintDatum(id, COL.sel);
  // references of the active command step
  const c = PT.cmd && feat(PT.cmd.id);
  if (c) {
    const refs = commandRefs(c);
    const faces = new Set();
    for (const r of refs.faces) {
      const fi = m ? m.face_keys.findIndex(k => k && keyOfFace(k) === keyOfFace(r)) : -1;
      if (fi >= 0) { faces.add(fi); continue; }
      // a face of a surface body
      for (const [sid, sm] of Object.entries(PT.surfaces || {})) { const si = (sm.face_keys || []).findIndex(k => k && keyOfFace(k) === keyOfFace(r)); if (si >= 0) { paintSurface(sid, 0xe8590c, 0.5, si); break; } }
    }
    paint(faces, 0xe8590c, 0.55, 4);
    paintEdges(new Set(refs.edges.map(keyOfEdge)), 0xe8590c);
    const bad = (PT.status[c.id] || {}).bad_edges;                 // edges where a fillet or chamfer fails
    if (bad && bad.length) paintEdges(new Set(bad.map(keyOfEdge)), 0xd0021b);
    for (const sid of refs.surfaces) if (PT.surfaces[sid]) paintSurface(sid, 0xe8590c, 0.5);
    for (const pid of refs.planes) paintPlane(pid, 0xe8590c);
    for (const sid of refs.sketches) paintSketch(sid, 0xe8590c);
    for (const did of refs.datums || []) paintDatum(did, 0xe8590c);
    for (const q of refs.points || []) { const sg = new THREE.SphereGeometry(planeSize() * 0.02, 12, 12); const sp = new THREE.Mesh(sg, new THREE.MeshBasicMaterial({ color: 0xe8590c, depthTest: false })); sp.position.set(...q); sp.renderOrder = 11; t.overlay.add(sp); }
  }
  // inspection results: the active issue red, the others orange
  if (PT.inspect && PT.inspect.issues) {
    const seg = (pts, color, width, order) => {
      const pos = [];
      for (let j = 0; j + 1 < pts.length; j++) pos.push(...pts[j], ...pts[j + 1]);
      if (!pos.length) return;
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      const l = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color, depthTest: false, linewidth: width }));
      l.renderOrder = order;
      t.overlay.add(l);
    };
    PT.inspect.issues.forEach((x, i) => {
      const active = i === PT.inspect.active;
      if (!active && !PT.inspect.showAll) return;
      const color = active ? 0xd0021b : x.kind === "free" ? 0xe8a04c : 0xe8590c;
      seg(x.pts || [], color, active ? 3 : 1, active ? 13 : 12);
      if (active || x.kind === "pointgap" || x.kind === "smalledge" || x.kind === "smallface") {
        const sg = new THREE.SphereGeometry(planeSize() * (active ? 0.015 : 0.01), 10, 10);
        const sp = new THREE.Mesh(sg, new THREE.MeshBasicMaterial({ color, depthTest: false })); sp.position.set(...x.p); sp.renderOrder = 13; t.overlay.add(sp);
      }
    });
  }
  if (PT.section) t.overlay.traverse(o => { if (o.material && !o.userData.noclip) o.material.clippingPlanes = [PT.section.plane]; });
  // centre of rotation
  if (PT.pivot) { const sg = new THREE.SphereGeometry(planeSize() * 0.012, 10, 10); const sp = new THREE.Mesh(sg, new THREE.MeshBasicMaterial({ color: 0x2f74d0, depthTest: false })); sp.position.set(...PT.pivot); sp.renderOrder = 12; t.overlay.add(sp); }
  // hover
  if (PT.hover) {
    const h = PT.hover;
    if (h.kind === "face" && h.surface) paintSurface(h.surface, COL.hover, 0.6, h.fi);
    else if (h.kind === "face") paint(new Set([h.fi]), COL.hover, 0.5, 5);
    else if (h.kind === "body") paint(new Set([...h.faces]), COL.hover, 0.35, 5);
    else if (h.kind === "edge") paintEdges(new Set([keyOfEdge(h.key)]), COL.hover);
    else if (h.kind === "surface" || h.kind === "curve") paintSurface(h.id, COL.hover, 0.6);
    else if (h.kind === "plane") paintPlane(h.id, COL.hover);
    else if (h.kind === "sketch") paintSketch(h.id, COL.hover);
    else if (h.kind === "point" && h.vertex) { const sg = new THREE.SphereGeometry(planeSize() * 0.015, 10, 10); const sp = new THREE.Mesh(sg, new THREE.MeshBasicMaterial({ color: COL.hover, depthTest: false })); sp.position.set(...h.point); sp.renderOrder = 12; t.overlay.add(sp); }
    else if (h.kind === "point" || h.kind === "axis") paintDatum(h.id, COL.hover);
    else if (h.kind === "region") { const o = PT.regionObjs[h.index]; if (o) { const mm = o.clone(); mm.material = new THREE.MeshBasicMaterial({ color: COL.hover, transparent: true, opacity: 0.7, side: THREE.DoubleSide, depthWrite: false }); mm.renderOrder = 6; t.overlay.add(mm); } }
  }
  render3();
}
function paintSurface(id, color, opacity, faceIndex) {
  const t = PT.three, sm = PT.surfaces[id];
  if (!sm) return;
  if (sm.triangles.length) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(sm.vertices.flat(), 3));
    const tris = faceIndex === undefined || !sm.face_of_tri ? sm.triangles : sm.triangles.filter((tr, i) => sm.face_of_tri[i] === faceIndex);
    g.setIndex(tris.flat());
    const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }));
    mesh.renderOrder = 5;
    t.overlay.add(mesh);
  } else {
    const pos = [];
    for (const pl of sm.edges) for (let k = 0; k + 1 < pl.length; k++) pos.push(...pl[k], ...pl[k + 1]);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    const l = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color, depthTest: false }));
    l.renderOrder = 9;
    t.overlay.add(l);
  }
}
function paintPlane(id, color) {
  const t = PT.three;
  const o = PT.planeObjs.find(p => p.userData.id === id);
  if (!o) return;
  const q = o.userData.corners;
  const pg = new THREE.BufferGeometry();
  pg.setAttribute("position", new THREE.Float32BufferAttribute([...q[0], ...q[1], ...q[2], ...q[0], ...q[2], ...q[3]], 3));
  const mesh = new THREE.Mesh(pg, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.18, side: THREE.DoubleSide, depthWrite: false }));
  mesh.renderOrder = 3;
  t.overlay.add(mesh);
  const lg = new THREE.BufferGeometry().setFromPoints([...q, q[0]].map(p => new THREE.Vector3(...p)));
  const ln = new THREE.Line(lg, new THREE.LineBasicMaterial({ color, depthTest: false }));
  ln.renderOrder = 9;
  t.overlay.add(ln);
}
function paintDatum(id, color) {
  const t = PT.three;
  const p = PT.pointObjs.find(o => o.userData.id === id);
  if (p) { const sg = new THREE.SphereGeometry(planeSize() * 0.03, 12, 12); const sp = new THREE.Mesh(sg, new THREE.MeshBasicMaterial({ color, depthTest: false })); sp.position.set(...p.userData.point); sp.renderOrder = 11; t.overlay.add(sp); }
  const a = PT.axisObjs.find(o => o.userData.id === id);
  if (a) { const l = new THREE.Line(a.geometry, new THREE.LineBasicMaterial({ color, depthTest: false })); l.renderOrder = 10; t.overlay.add(l); }
}
function paintSketch(id, color) {
  const t = PT.three;
  const o = PT.sketchObjs.find(p => p.userData.id === id);
  if (!o) return;
  const l = new THREE.LineSegments(o.geometry, new THREE.LineBasicMaterial({ color, depthTest: false, linewidth: 2 }));
  l.renderOrder = 10;
  t.overlay.add(l);
}

// ------------------------------------------------------------------ hover and click in the view

/** Element under the cursor, filtered by kinds (array of kinds or null for all). */
/** Vertices of the solid (ends of the edge polylines), cached per mesh. */
function meshVertices() {
  const m = PT.mesh;
  if (!m) return [];
  if (PT.vtxCache && PT.vtxCache.mesh === m) return PT.vtxCache.list;
  const seen = new Set(), list = [];
  for (const pl of m.edges || []) {
    if (!pl || !pl.length) continue;
    for (const q of [pl[0], pl[pl.length - 1]]) {
      const k = q.map(x => x.toFixed(4)).join(",");
      if (!seen.has(k)) { seen.add(k); list.push(q.slice()); }
    }
  }
  PT.vtxCache = { mesh: m, list };
  return list;
}
function vertexAt(e, r, rc, px) {
  const t = PT.three, mx = e.clientX - r.left, my = e.clientY - r.top;
  let best = null, bd = 8;
  const p = new THREE.Vector3();
  for (const q of meshVertices()) {
    p.set(q[0], q[1], q[2]).project(t.camera);
    const d = Math.hypot((p.x + 1) / 2 * r.width - mx, (1 - p.y) / 2 * r.height - my);
    if (d < bd) { bd = d; best = q; }
  }
  if (!best) return null;
  const along = new THREE.Vector3(...best).sub(rc.ray.origin).dot(rc.ray.direction);
  const hits = rc.intersectObjects(PT.faceObjs, false);
  if (hits.length && hits[0].distance < along - px * 4) return null;
  return { kind: "point", vertex: true, point: best.slice(), dist: along };
}

function pickAt(e, kinds) {
  const t = PT.three;
  const r = t.renderer.domElement.getBoundingClientRect();
  const nd = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster();
  rc.setFromCamera(nd, t.camera);
  const px = (t.camera.right - t.camera.left) / t.camera.zoom / r.width;   // world units per pixel
  rc.params.Line.threshold = px * 6;
  const allow = k => !kinds || kinds.includes(k);
  const m = PT.mesh;
  // lines first (edges, sketches, curves): nearest to the ray in screen terms
  const lineObjs = [];
  if (allow("edge")) lineObjs.push(...PT.edgeLines.filter(l => !l.userData.surface));
  if (allow("sedge")) lineObjs.push(...PT.edgeLines.filter(l => l.userData.surface));
  if (allow("sketch")) lineObjs.push(...PT.sketchObjs);
  if (allow("curve")) lineObjs.push(...PT.surfObjs.filter(o => o.userData.kind === "curve"));
  if (allow("axis")) lineObjs.push(...PT.axisObjs);
  let best = null;
  // point features: picked within 8 px before anything else
  if (allow("point") && PT.pointObjs.length) {
    rc.params.Points.threshold = px * 8;
    const ph = rc.intersectObjects(PT.pointObjs, false);
    if (ph.length) { const u = ph[0].object.userData; return { kind: "point", id: u.id, point: u.point, dist: ph[0].distance }; }
  }
  // vertices of the solid: picked within 8 px where a step takes points, unless a face is in front of them
  if (allow("point") && m) {
    const v = vertexAt(e, r, rc, px);
    if (v) return v;
  }
  if (lineObjs.length) {
    const hits = rc.intersectObjects(lineObjs, false);
    for (const h of hits) h.dr = rc.ray.distanceToPoint(h.point);
    hits.sort((a, b) => (Math.abs(a.dr - b.dr) > px * 1.5 ? a.dr - b.dr : a.distance - b.distance));
    if (hits.length) {
      const u = hits[0].object.userData;
      const pt = [hits[0].point.x, hits[0].point.y, hits[0].point.z];
      if (u.kind === "edge") best = { kind: "edge", key: u.key, index: u.index, surface: u.surface, polyline: u.polyline, dist: hits[0].distance, line: true, point: pt };
      else best = { kind: u.kind, id: u.id, dist: hits[0].distance, line: true, point: pt };
    }
  }
  // surfaces (faces, bodies, surface bodies, regions, planes)
  const faceObjs = [];
  if (allow("face") || allow("body")) faceObjs.push(...PT.faceObjs);
  if (allow("surface") || allow("sface")) faceObjs.push(...PT.surfObjs.filter(o => o.userData.kind === "surface"));
  if (allow("region")) faceObjs.push(...PT.regionObjs);
  if (allow("plane")) faceObjs.push(...PT.planeObjs);
  if (faceObjs.length) {
    const hits = rc.intersectObjects(faceObjs, false);
    // coincident surfaces: the later feature is picked
    hits.sort((a, b) => Math.abs(a.distance - b.distance) > px * 0.5 ? a.distance - b.distance : (featIndex(b.object.userData.id) || 0) - (featIndex(a.object.userData.id) || 0));
    // planes are picked only when nothing else is under the cursor
    const solidHit = hits.find(h => h.object.userData.kind !== "plane");
    const hit = solidHit || hits[0];
    if (hit && (!best || hit.distance < best.dist - px * 3 || hit.object.userData.kind === "region")) {
      const u = hit.object.userData;
      if (u.kind === "solid") {
        const fi = m.face_of_tri[hit.faceIndex];
        const kind = allow("face") ? "face" : "body";
        const pt = [hit.point.x, hit.point.y, hit.point.z];
        best = kind === "face" ? { kind, fi, key: m.face_keys[fi], solid: u.solid, owner: (m.face_owner || [])[fi], dist: hit.distance, point: pt }
          : { kind: "body", solid: u.solid, faces: u.faces, dist: hit.distance, point: pt };
      } else if (u.kind === "surface") {
        const sm = (PT.surfaces || {})[u.id], fi = sm && sm.face_of_tri ? sm.face_of_tri[hit.faceIndex] : -1;
        const key = sm && fi >= 0 ? (sm.face_keys || [])[fi] : null;
        // a face of a surface body when the step takes faces (sface) and not whole surface bodies
        if (allow("sface") && !allow("surface") && key) best = { kind: "face", fi, key, surface: u.id, dist: hit.distance, point: [hit.point.x, hit.point.y, hit.point.z] };
        else best = { kind: "surface", id: u.id, fi, key, dist: hit.distance };
      }
      else if (u.kind === "region") best = { kind: "region", index: u.index, point: u.point, uv: u.uv, area: u.area, dist: hit.distance };
      else if (u.kind === "plane" && !best) best = { kind: "plane", id: u.id, dist: hit.distance };
    }
  }
  return best;
}

/** Default pick of a parameter panel (Remove faces, Hole mesh, ...): the first pick of the panel. */
function legacyPick(c) {
  const defs = c && c.legacyDefs;
  if (!defs) return null;
  const fc = feat(c.id);
  // Place: the next empty face
  const k = (fc && fc.type === "place" && Object.keys(defs).find(x => !fc[x])) || Object.keys(defs)[0];
  if (!k) return null;
  const d = defs[k];
  return { prop: k, kinds: d.kinds || [d.kind], single: !!d.single, expand: d.kind === "edge" && !d.single ? true : undefined };
}

/** Kinds accepted by the active command step (null: any element, for tree selection). */
function activeKinds() {
  if (PT.measure && !PT.cmd) return ["face", "plane", "axis"];
  const c = PT.cmd;
  if (!c) return null;
  if (c.pick) return c.pick.kinds;
  const lp = legacyPick(c);
  if (lp) return lp.kinds;
  const st = commandSteps(feat(c.id))[c.step];
  return st && st.kinds ? st.kinds : null;
}

function hoverView(e) {
  if (!PT.three || !PT.part) return;
  setHover(pickAt(e, activeKinds()), e);
}

function setHover(h, e) {
  const t = PT.three;
  const same = JSON.stringify(h && { k: h.kind, a: h.fi, b: h.id, c: h.index, d: h.solid }) === JSON.stringify(PT.hover && { k: PT.hover.kind, a: PT.hover.fi, b: PT.hover.id, c: PT.hover.index, d: PT.hover.solid });
  PT.hover = h;
  if (!h) { t.tip.hidden = true; if (!same) drawSelection(); return; }
  t.tip.hidden = false;
  t.tip.textContent = hoverText(h);
  if (e) {
    const r = t.box.getBoundingClientRect();
    t.tip.style.left = (e.clientX - r.left + 14) + "px";
    t.tip.style.top = (e.clientY - r.top + 14) + "px";
  }
  t.renderer.domElement.style.cursor = "pointer";
  if (!same) drawSelection();
}

function hoverText(h) {
  const owner = id => { const f = id && feat(id); return f ? " (" + f.name + ")" : ""; };
  // circular edge or cylindrical face: Ø for a span of 180 deg or more, R below
  const round = k => { const q = k && k.round; return !q ? "" : q.span >= 179.9 ? ", Ø" + pfmt(2 * q.r, 3) + " mm" : ", R" + pfmt(q.r, 3) + " mm"; };
  if (h.kind === "face" && h.surface) return "Face of " + (feat(h.surface) || {}).name + round(h.key);
  if (h.kind === "face") return "Face" + owner(h.owner) + (PT.cells > 1 ? ", Solid " + (h.solid + 1) : "") + round(h.key);
  if (h.kind === "body") return "Solid " + (h.solid + 1);
  if (h.kind === "edge") {
    const q = h.key && h.key.round;
    const txt = !q ? pfmt(h.key.len, 2) + " mm" : q.span >= 359.9 ? "Ø" + pfmt(2 * q.r, 3) + " mm"
      : (q.span >= 179.9 ? "Ø" + pfmt(2 * q.r, 3) : "R" + pfmt(q.r, 3)) + " mm, arc " + pfmt(q.span, 1) + "°, length " + pfmt(h.key.len, 2) + " mm";
    return "Edge, " + txt + (h.surface ? owner(h.surface) : "");
  }
  if (h.kind === "surface") return "Surface" + owner(h.id);
  if (h.kind === "curve") return "Curve" + owner(h.id);
  if (h.kind === "sketch") return itemName(h.id);
  if (h.kind === "point") { const q = h.point || []; return (h.vertex ? "Vertex" : itemName(h.id)) + " (" + q.map(v => pfmt(v, 2)).join(", ") + ") mm"; }
  if (h.kind === "axis") return itemName(h.id);
  if (h.kind === "plane") return BASE_PLANES[h.id] ? "Reference plane " + BASE_PLANES[h.id] : itemName(h.id);
  if (h.kind === "region") return "Region " + (h.index + 1) + ", " + pfmt(h.area, 1) + " mm^2";
  return "";
}

/** Click in the view: feeds the active command step, or selects the owner of the element in the tree. */
function clickView(e) {
  const kinds = activeKinds();
  const h = pickAt(e, kinds);
  if (PT.measure && !PT.cmd) { if (h) measureClick(h); return; }
  const c = PT.cmd;
  if (c && (c.pick || kinds)) {
    if (!h) return;
    feedCommand(h);
    return;
  }
  if (!h) { selectItem(null); return; }
  if (h.kind === "face") selectItem(h.owner || "solid:" + h.solid);
  else if (h.kind === "body") selectItem("solid:" + h.solid);
  else if (h.kind === "edge") selectItem(null);
  else selectItem(h.id);
}

/** Feeds a hit to the active command step. Returns true when the step took it. */
function feedCommand(h) {
  const c = PT.cmd;
  if (!c) return false;
  const kinds = activeKinds();
  if (!kinds || !kinds.includes(h.kind)) return false;
  const f = feat(c.id);
  if (!c.pick && legacyPick(c)) { c.pick = legacyPick(c); applyPick(f, c.pick, h); renderCommand(); return true; }
  if (c.pick) { applyPick(f, c.pick, h); return true; }
  const st = commandSteps(f)[c.step];
  if (st && st.accept) { st.accept(f, h); PT.dirty = true; renderCommand(); drawSelection(); scheduleBuild(); }
  else if (st && st.prop) applyPick(f, { prop: st.prop, kinds: st.kinds, single: st.single, expand: st.expand }, h);
  afterStepChange(f, st);
  return true;
}

/** Step picking one point or axis feature (or a plane feature) into f[prop]. */
/** Step "Edge or curve" of the Plane and Point features: an edge of the solid, a curve body, or a curve of a sketch
 *  (sketch_curve: the connected chain of sketch curves at the click; without a position the plane or point goes to
 *  the chain end nearer the click). withT adds the position field. */
function curveRefStep(withT) {
  const tEmpty = f => f.t === undefined || f.t === null;
  return { key: "edge", label: "Edge or curve", kinds: ["edge", "curve", "sketch"], single: true,
    hint: "Click an edge of the solid, a curve body or a curve of a sketch (a sketch curve: click near the end where the plane or point goes).",
    accept: (f, h) => {
      f.edge = null; f.curve = null; f.sketch_curve = null;
      if (h.kind === "edge") f.edge = refOf(h);
      else if (h.kind === "sketch") { f.sketch_curve = { sketch: h.id, pick: (h.point || [0, 0, 0]).map(v => +(+v).toFixed(6)) }; f.t = null; }
      else f.curve = h.id;
      PT.dirty = true; },
    html: f => sourceSelect("pf-curve", f, "curve", false, true).replace("Curve<", "Or a curve body<") +
      (withT ? `<div class="grid2">` + num("pf-st", f.sketch_curve ? "Position along the curve (0 to 1; empty: the end nearer the click)" : "Position along the edge (0 to 1)",
        tEmpty(f) ? (f.sketch_curve ? "" : 0.5) : f.t) + `<span></span></div>` : ""),
    bind: (f, box) => bindAll(box, { "#pf-curve": el => { f.curve = el.value || null; if (el.value) { f.edge = null; f.sketch_curve = null; } },
      "#pf-st": el => { const t = el.value.trim() === "" ? NaN : numv(el.value); f.t = t >= 0 && t <= 1 ? t : (f.sketch_curve ? null : 0.5); } }),
    done: f => !!(f.edge || f.curve || f.sketch_curve),
    summary: f => f.sketch_curve ? itemName(f.sketch_curve.sketch) + " curve" + (tEmpty(f) ? ", nearer end" : ", " + pfmt(f.t)) : f.curve ? itemName(f.curve) : f.edge ? "edge" : "none" };
}

function datumStep(kind, label, prop, hint, optional) {
  const items = i => kind === "point" ? pointItems(i) : kind === "axis" ? axisItems(i) : planeItems(i);
  return { key: prop, label, kinds: [kind], prop, single: true, optional: !!optional, before: false,
    hint: hint || ("Click a " + kind + " feature" + (kind === "point" ? " or a vertex of the part" : "") + " in the view or the tree."),
    html: f => (isVertexRef(f[prop]) ? `<p class="hint">${itemName(f[prop])}</p>` : "") + refSelect("pf-" + prop, TYPE_NAMES[kind] + " feature", items(featIndex(f.id)), isVertexRef(f[prop]) ? "" : f[prop]),
    bind: (f, box) => bindAll(box, { ["#pf-" + prop]: el => { f[prop] = el.value || null; } }),
    done: f => optional || !!f[prop], summary: f => f[prop] ? itemName(f[prop]) : "none" };
}

/** Hit record for a tree row: a reference plane, a plane feature or a sketch. */
function treeHit(id) {
  if (BASE_PLANES[id]) return { kind: "plane", id };
  const f = feat(id);
  if (!f) return null;
  if (f.type === "plane") return { kind: "plane", id };
  if (f.type === "sketch") return { kind: "sketch", id };
  if (f.type === "point") return { kind: "point", id, point: (PT.status[id] || {}).point };
  if (f.type === "axis") return { kind: "axis", id };
  return null;
}

/** True while the Plane step of the Sketch command is active. */
function isPlaneStep() {
  const c = PT.cmd;
  if (!c) return false;
  const f = feat(c.id);
  if (!f || f.type !== "sketch") return false;
  const st = commandSteps(f)[c.step];
  return !!st && st.key === "plane";
}

/** Sketch on the hit element and open the sketch editor. In the Plane step of the Sketch command the hit sets
 *  the plane of that sketch; otherwise a new Sketch command is started. */
function sketchOnPlane(h) {
  if (!isPlaneStep()) {
    if (PT.cmd) return;
    startCommand("sketch");
    if (!PT.cmd) return;
  }
  const f = feat(PT.cmd.id);
  acceptPlanePick(f, h);
  if (canFinish(f)) finishCommand(true);
}

/** Double click in the view: sketch on the reference plane, plane feature, planar face or edge under the cursor. */
/** Centre of rotation at the clicked point of the model (middle click); the view does not move. */
function setPivot(e) {
  const t = PT.three;
  const h = pickAt(e, ["face", "edge", "sedge", "surface", "sketch", "curve", "point"]);
  let q = h && h.point;
  if (!q && h && h.kind === "surface") {
    // surfaces carry no point: intersect the surface mesh again
    const r = t.renderer.domElement.getBoundingClientRect();
    const nd = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    const rc = new THREE.Raycaster(); rc.setFromCamera(nd, t.camera);
    const hs = rc.intersectObjects(PT.surfObjs.filter(o => o.userData.id === h.id), false);
    if (hs.length) q = [hs[0].point.x, hs[0].point.y, hs[0].point.z];
  }
  if (!q) { msgPart("Centre of rotation: middle-click a point of the model"); return; }
  t.controls.setTarget(new THREE.Vector3(...q), true);
  PT.pivot = q;
  drawSelection();
  msgPart(`Centre of rotation (${pfmt(q[0], 2)}, ${pfmt(q[1], 2)}, ${pfmt(q[2], 2)}) mm`);
}

function dblclickView(e) {
  if (PT.cmd && !isPlaneStep()) return;
  const h = pickAt(e, ["plane", "face", "edge", "curve"]);
  if (h) sketchOnPlane(h);
}

/** Reference record of a picked element for a feature property. */
/** Three points method (Plane, Partition): a picked vertex or point feature fills point 1, 2 and 3 in turn. */
function fillThreePoints(f, h) {
  if (!h.point) return;
  f.points = (f.points || [[0, 0, 0], [1, 0, 0], [0, 1, 0]]).slice(0, 3);
  const c = PT.cmd, i = (c.pointIndex || 0) % 3;
  f.points[i] = h.point.map(v => +(+v).toFixed(6));
  c.pointIndex = i + 1;
  msgPart("Point " + (i + 1) + " set to (" + f.points[i].map(v => pfmt(v, 2)).join(", ") + ") mm");
}

function refOf(h) {
  if (h.kind === "face") return { c: h.key.c, n: h.key.n, area: h.key.area };
  if (h.kind === "edge") return { mid: h.key.mid, len: h.key.len };
  if (h.kind === "body") return { solid: h.solid };
  return h.id !== undefined ? h.id : h.point;
}
const sameRef = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** Writes a picked element into f[prop]: single replaces, multi toggles; "expand" modes ask the server
 *  for a tangent chain or the edges of a face. */
function applyPick(f, pick, h) {
  const ref = refOf(h);
  if (pick.expand && h.kind === "face" && pick.kinds.includes("edge")) { expandEdges(f, pick.prop, "faces", [ref]); return; }
  if (pick.expand === "tangent" && h.kind === "edge") { expandEdges(f, pick.prop, "tangent", [ref]); return; }
  if (pick.single) { f[pick.prop] = ref; if (pick.after) pick.after(f, h); }
  else {
    f[pick.prop] = f[pick.prop] || [];
    const i = f[pick.prop].findIndex(x => sameRef(x, ref));
    if (i >= 0) f[pick.prop].splice(i, 1); else f[pick.prop].push(ref);
  }
  PT.dirty = true;
  if (PT.cmd && PT.cmd.pick && pick.single) PT.cmd.pick = null;
  renderCommand();
  drawSelection();
  scheduleBuild();
}

async function expandEdges(f, prop, mode, refs) {
  try {
    const r = await postJSON("/api/part/expand", { part: PT.part, index: featIndex(f.id), mode, refs });
    const keys = await r.json();
    f[prop] = f[prop] || [];
    const have = new Set(f[prop].map(keyOfEdge));
    let n = 0;
    for (const k of keys) if (!have.has(keyOfEdge(k))) { f[prop].push({ mid: k.mid, len: k.len }); have.add(keyOfEdge(k)); n++; }
    PT.dirty = true;
    renderCommand(); drawSelection(); scheduleBuild();
    msgPart(n + " edge(s) added, " + f[prop].length + " selected");
  } catch (e) { showErr(e); }
}

function togglePanel(sel) {
  const el = document.querySelector(sel);
  if (!el) return;
  el.classList.toggle("collapsed");
  window.dispatchEvent(new Event("resize"));
}

/** Space: hides or shows the element under the cursor (its solid, plane, sketch, surface or curve), else the
 *  selected tree item, else all reference planes and plane features (the Planes check box). */
function toggleVisible() {
  const h = PT.hover;
  let id = null;
  if (h) {
    if (h.kind === "face" || h.kind === "body") id = "solid:" + h.solid;
    else if (h.kind === "edge") id = h.surface || null;
    else if (["plane", "sketch", "surface", "curve", "point", "axis"].includes(h.kind)) id = h.id;
  }
  if (!id && PT.sel && (BASE_PLANES[PT.sel] || PT.sel.startsWith("solid:") || (feat(PT.sel) && ["sketch", "plane", "point", "axis"].concat([...SURFACE_TYPES]).includes(feat(PT.sel).type)))) id = PT.sel;
  if (!id) {
    if (PT.sel && feat(PT.sel) && !SURFACE_TYPES.has(feat(PT.sel).type)) { const si = PT.solids.length ? "solid:0" : null; if (si) { PT.hidden[si] = !PT.hidden[si]; renderTree(); setMesh(PT.mesh); msgPart((PT.hidden[si] ? "Hidden: " : "Shown: ") + "Solid 1 (Space toggles)"); return; } }
    const cb = $("#pt-planes"); cb.checked = !cb.checked; setMesh(PT.mesh); msgPart(cb.checked ? "Planes, points and axes shown" : "Planes, points and axes hidden"); return;
  }
  PT.hidden[id] = !PT.hidden[id];
  setHover(null);
  renderTree(); setMesh(PT.mesh);
  msgPart((PT.hidden[id] ? "Hidden: " : "Shown: ") + (BASE_PLANES[id] ? BASE_PLANES[id] : id.startsWith("solid:") ? "Solid " + (+id.slice(6) + 1) : itemName(id)) + " (Space toggles)");
}

function selectItem(id) {
  PT.sel = id;
  renderTree();
  if (!PT.cmd) renderProps();
  drawSelection();
}

// ------------------------------------------------------------------ view

function view(name) {
  const t = PT.three;
  if (!t) return;
  const ps = planeSize();
  let bb = PT.mesh && PT.mesh.bbox ? PT.mesh.bbox : null;
  if (!bb && (PT.surfObjs || []).length) {
    // no solid: the surface bodies
    const b3 = new THREE.Box3();
    for (const o of PT.surfObjs) b3.expandByObject(o);
    if (!b3.isEmpty()) bb = [b3.min.x, b3.min.y, b3.min.z, b3.max.x, b3.max.y, b3.max.z];
  }
  bb = bb || [-ps, -ps, -ps, ps, ps, ps];
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
  PT.pivot = null;
  const w = t.box.clientWidth || 1, h = t.box.clientHeight || 1;
  const half = size * 0.75;
  t.camera.top = half; t.camera.bottom = -half; t.camera.left = -half * w / h; t.camera.right = half * w / h;
  t.camera.zoom = 1;
  t.camera.updateProjectionMatrix();
  t.controls.update();
  render3();
}

// ------------------------------------------------------------------ hole presets (fasteners.py)

let REF = null;
async function loadReference() {
  if (REF) return REF;
  try { const r = await fetch("/api/reference"); REF = await r.json(); } catch (e) { REF = { presets: [] }; }
  return REF;
}
loadReference();

/** Select of the standard holes for metric screws: tapped (tap drill), clearance (ISO 273), counterbore for
 *  ISO 4762 / DIN 7984 (DIN 974-1), countersink for ISO 10642 (DIN 74 F) and ISO 7721 heads (ISO 15065). */
function holePresetHtml(f) {
  const presets = (REF && REF.presets) || [];
  const groups = [];
  for (const p of presets) { let g = groups.find(x => x.name === p.group); if (!g) { g = { name: p.group, items: [] }; groups.push(g); } g.items.push(p); }
  const opts = groups.map(g => `<optgroup label="${pesc(g.name)}">` + g.items.map(p => `<option value="${p.id}"${f.preset === p.id ? " selected" : ""}>${pesc(p.label)}</option>`).join("") + `</optgroup>`).join("");
  return `<label>Standard hole for a metric screw<select id="pf-preset"><option value="">(values below)</option>${opts}</select></label>`;
}

/** Thread type (metric coarse, metric fine, trapezoidal, custom) and the designations of that type. */
const THREAD_TYPES = [["coarse", "Metric coarse (ISO 261)"], ["fine", "Metric fine (ISO 262)"], ["bearing", "Bearing lock nut (KM, DIN 981)"], ["trapezoidal", "Trapezoidal Tr (ISO 2904)"],
                      ["unc", "Unified coarse UNC (ASME B1.1)"], ["unf", "Unified fine UNF (ASME B1.1)"], ["bspp", "Pipe thread G (ISO 228-1)"], ["custom", "Custom designation"]];
const THREAD_CLASS = { coarse: "6g", fine: "6g", bearing: "6g", trapezoidal: "7e", unc: "2A", unf: "2A", bspp: "A" };
function threadNames(type) { return (((REF || {})[type]) || []).map(r => r.name); }
function threadSelectHtml(f) {
  const cur = f.thread || "";
  let type = f.thread_type;
  if (!type) type = THREAD_TYPES.map(t => t[0]).find(t => threadNames(t).includes(cur)) || "custom";
  const names = threadNames(type);
  const opts = names.map(n => `<option value="${n}"${n === cur ? " selected" : ""}>${n}</option>`).join("");
  const types = THREAD_TYPES.map(([v, t]) => `<option value="${v}"${v === type ? " selected" : ""}>${t}</option>`).join("");
  return `<div class="grid2"><label>Type<select id="pf-ttype">${types}</select></label>` +
    (type === "custom" ? `<label>Designation (M10x1.25, Tr20x4, 1/4-20 UNC, G1/2)<input type="text" id="pf-tcustom" value="${pesc(cur)}"></label>`
      : `<label>Designation<select id="pf-tsel">${opts}</select></label>`) + `</div>`;
}

function applyHolePreset(f, id) {
  const p = ((REF && REF.presets) || []).find(x => x.id === id);
  f.preset = id || null;
  if (!p) return;
  f.dia = p.dia;
  f.cbore_dia = p.cbore_dia || null; f.cbore_depth = p.cbore_depth || null;
  f.csink_dia = p.csink_dia || null; f.csink_angle = p.csink_angle || 90;
  f.thread = p.thread || ""; f.tol = p.tol || "";
  // the fields are re-rendered when the select loses the focus
  setTimeout(() => { const el = document.activeElement; if (el && el.id === "pf-preset") el.blur(); }, 0);
}

// ------------------------------------------------------------------ build

function scheduleBuild() {
  clearTimeout(PT.buildTimer);
  PT.buildTimer = setTimeout(build, 150);
}

/** The build stops before the command's feature while one of its element selection steps is active. */
function buildUpto() {
  const c = PT.cmd;
  if (!c) return null;
  const f = feat(c.id);
  if (!f) return null;
  if (c.pick || f.type === "place") return featIndex(f.id);     // Place: faces are picked on the part before it
  const st = commandSteps(f)[c.step];
  if (st && st.kinds && st.before !== false && (st.kinds.includes("face") || st.kinds.includes("edge") || st.kinds.includes("sedge") || st.kinds.includes("body") || st.kinds.includes("region"))) return featIndex(f.id);
  return null;
}

async function build() {
  const seq = ++PT.buildSeq;
  $("#pt-info").textContent = "Building...";
  try {
    const upto = buildUpto();
    const uptoName = upto !== null && PT.cmd && feat(PT.cmd.id) ? feat(PT.cmd.id).name : "";
    const r = await postJSON("/api/part/build", { part: PT.part, upto });
    const j = await r.json();
    if (seq !== PT.buildSeq) return;
    PT.status = {};
    for (const s of j.status) PT.status[s.id] = s;
    // a cut that removed nothing in its direction was made in the opposite direction: the feature records it
    for (const s of j.status) if (s.flipped) { const f = feat(s.id); if (f) { f.reverse = !f.reverse; PT.dirty = true; } }
    PT.surfaces = j.surfaces || {};
    PT.solids = j.solids || [];
    PT.cells = j.cells || 0;
    setMesh(j.mesh);
    const rho = numv($("#density").value) || 0;
    const bb = j.mesh.bbox;
    const errs = j.status.filter(s => s.error).length;
    $("#pt-info").textContent = (upto !== null ? "Part before " + uptoName + ". " : "") + (bb ? `Volume ${pfmt(j.volume_mm3 / 1000, 3)} cm^3` + (rho > 0 ? `, mass ${pfmt(j.volume_mm3 * 1e-9 * rho, 3)} kg` : "") +
      `, size ${pfmt(bb[3] - bb[0], 2)} x ${pfmt(bb[4] - bb[1], 2)} x ${pfmt(bb[5] - bb[2], 2)} mm` + (j.cells > 1 ? `, ${j.cells} cells` : "") + (errs ? `, ${errs} feature(s) failed` : "")
      : (errs ? `${errs} feature(s) failed` : "No solid"));
    renderTree();
    if (PT.cmd) renderCommand(); else renderProps();
  } catch (e) { if (seq === PT.buildSeq) { $("#pt-info").textContent = ""; showErr(e); } }
}

function changedPart(rebuild) {
  PT.dirty = true;
  if (PT.rendering) { if (rebuild !== false) scheduleBuild(); return; }
  PT.rendering = true;
  try {
    renderTree();
    if (PT.cmd) renderCommand(true); else renderProps();
    renderConfigs();
  } finally { PT.rendering = false; }
  if (rebuild !== false) scheduleBuild();
  else drawSelection();
}

// ------------------------------------------------------------------ tree

const EYE = '<svg viewBox="0 0 16 16" width="13" height="13"><path d="M1 8s2.5-4.5 7-4.5S15 8 15 8s-2.5 4.5-7 4.5S1 8 1 8z" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>';
const ICON = { sketch: "✎", plane: "▱", point: "⊕", axis: "⟋", solid: "◆", surface: "◈", curve: "∿", feature: "●" };

function renderTree() {
  const box = $("#pt-features");
  const fs = PT.part.features;
  const row = (id, icon, name, opts) => {
    const o = opts || {};
    const st = PT.status[id] || {};
    return `<div class="pt-feat${id === PT.sel ? " sel" : ""}${o.suppressed ? " supp" : ""}${o.cmd ? " editing" : ""}" data-id="${pesc(id)}">` +
      (o.toggle ? `<input type="checkbox" data-k="on" title="Active"${o.suppressed ? "" : " checked"}>` : `<span class="ico">${icon}</span>`) +
      `<span class="nm">${o.toggle ? `<span class="ico">${icon}</span> ` : ""}${pesc(name)}</span>` +
      `<span class="ops">` + (o.eye ? `<button type="button" data-k="eye" class="${PT.hidden[id] ? "off" : ""}" title="Show / hide">${EYE}</button>` : "") +
      (o.ops ? `<button type="button" data-k="up" title="Move up">&#9650;</button><button type="button" data-k="down" title="Move down">&#9660;</button><button type="button" data-k="del" title="Delete">&#10005;</button>` : "") + `</span>` +
      (st.error && o.ops ? `<span class="err">${pesc(st.error)}</span>` : "") + "</div>";
  };
  let h = `<div class="pt-sec">Reference planes</div>` + Object.entries(BASE_PLANES).map(([k, n]) => row(k, ICON.plane, n, { eye: true })).join("");
  h += `<div class="pt-sec">Bodies</div>`;
  const nSolids = PT.solids.length;
  if (nSolids > 6 && !PT.showCells) h += `<div class="pt-feat" data-id="cells"><span class="ico">${ICON.solid}</span><span class="nm">${nSolids} solid cells</span><span class="ops"><button type="button" data-k="cells" title="List the cells">…</button></span></div>`;
  else for (let i = 0; i < nSolids; i++) h += row("solid:" + i, ICON.solid, "Solid " + (i + 1) + (nSolids > 1 ? ` (${pfmt(PT.solids[i].volume_mm3 / 1000, 2)} cm^3)` : ""), { eye: true });
  for (const f of fs) if (SURFACE_TYPES.has(f.type) && !f.suppressed && PT.surfaces[f.id]) h += row(f.id, CURVE_TYPES.has(f.type) ? ICON.curve : ICON.surface, f.name, { eye: true });
  if (!nSolids && !fs.some(f => SURFACE_TYPES.has(f.type) && PT.surfaces[f.id])) h += `<p class="hint">No body yet.</p>`;
  h += `<div class="pt-sec">Features</div>`;
  if (!fs.length) h += '<p class="hint">Sketch on a reference plane, then Extrude.</p>';
  for (const f of fs) {
    const icon = f.type === "sketch" ? ICON.sketch : f.type === "plane" ? ICON.plane : f.type === "point" ? ICON.point : f.type === "axis" ? ICON.axis : SURFACE_TYPES.has(f.type) ? (CURVE_TYPES.has(f.type) ? ICON.curve : ICON.surface) : ICON.feature;
    h += row(f.id, icon, f.name, { toggle: true, ops: true, suppressed: f.suppressed, eye: ["sketch", "plane", "point", "axis"].includes(f.type) || (SURFACE_TYPES.has(f.type) && !!PT.surfaces[f.id]), cmd: PT.cmd && PT.cmd.id === f.id });
  }
  box.innerHTML = h;
  box.querySelectorAll(".pt-feat").forEach(el => {
    const id = el.dataset.id;
    el.onclick = e => {
      const k = e.target.closest("[data-k]") && e.target.closest("[data-k]").dataset.k;
      const f = feat(id);
      const i = featIndex(id);
      if (k === "eye") { PT.hidden[id] = !PT.hidden[id]; renderTree(); setMesh(PT.mesh); return; }
      if (id === "cells") { PT.showCells = !PT.showCells; renderTree(); return; }
      if (!k && PT.cmd) { const th = treeHit(id); if (th && feedCommand(th)) return; }
      if (!f) { selectItem(id); return; }
      if (k === "on") { f.suppressed = !e.target.checked; changedPart(); return; }
      if (k === "up" && i > 0) { checkpointPart(); [fs[i - 1], fs[i]] = [fs[i], fs[i - 1]]; changedPart(); return; }
      if (k === "down" && i < fs.length - 1) { checkpointPart(); [fs[i + 1], fs[i]] = [fs[i], fs[i + 1]]; changedPart(); return; }
      if (k === "del") { deleteFeature(id); return; }
      selectItem(id);
    };
    el.ondblclick = e => {
      if (e.target.closest("[data-k]")) return;
      const th = treeHit(id);
      if (th && th.kind === "plane" && (!PT.cmd || isPlaneStep())) { sketchOnPlane(th); return; }
      const f = feat(id); if (f) { if (f.type === "sketch") editSketch(id); else editDefinition(id); }
    };
    el.onmouseenter = () => { const f = feat(id); if (f || BASE_PLANES[id] || id.startsWith("solid:")) drawTreeHover(id); };
    el.onmouseleave = () => drawSelection();
  });
}

/** Hover on a tree row highlights its geometry. */
function drawTreeHover(id) {
  const m = PT.mesh;
  if (!m) return;
  drawSelection();
  const t = PT.three;
  const faces = new Set();
  if (id.startsWith("solid:")) { const si = +id.slice(6); m.face_solid.forEach((s, fi) => { if (s === si) faces.add(fi); }); }
  else (m.face_owner || []).forEach((o, fi) => { if (o === id) faces.add(fi); });
  if (faces.size) {
    const mesh = new THREE.Mesh(facesGeometry(m, faces), new THREE.MeshBasicMaterial({ color: COL.hover, transparent: true, opacity: 0.45, side: THREE.DoubleSide, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }));
    mesh.renderOrder = 5;
    t.overlay.add(mesh);
  }
  if (PT.surfaces[id]) paintSurface(id, COL.hover, 0.6);
  if (BASE_PLANES[id] || (feat(id) && feat(id).type === "plane")) paintPlane(id, COL.hover);
  if (feat(id) && feat(id).type === "sketch") paintSketch(id, COL.hover);
  render3();
}

/** Undo stack of the part tree (deletions and reordering). Ctrl+Z restores, Ctrl+Y repeats. */
function checkpointPart() {
  PT.undo = PT.undo || []; PT.redo = [];
  PT.undo.push(JSON.stringify({ features: PT.part.features, sel: PT.sel }));
  if (PT.undo.length > 50) PT.undo.shift();
}
function undoPart() {
  if (!PT.undo || !PT.undo.length) { msgPart("Nothing to undo"); return; }
  if (PT.cmd) cancelCommand();
  PT.redo = PT.redo || []; PT.redo.push(JSON.stringify({ features: PT.part.features, sel: PT.sel }));
  const st = JSON.parse(PT.undo.pop());
  PT.part.features = st.features; PT.sel = st.sel && (feat(st.sel) || BASE_PLANES[st.sel]) ? st.sel : null;
  changedPart();
  msgPart("Undone");
}
function redoPart() {
  if (!PT.redo || !PT.redo.length) { msgPart("Nothing to redo"); return; }
  if (PT.cmd) cancelCommand();
  PT.undo = PT.undo || []; PT.undo.push(JSON.stringify({ features: PT.part.features, sel: PT.sel }));
  const st = JSON.parse(PT.redo.pop());
  PT.part.features = st.features; PT.sel = st.sel && feat(st.sel) ? st.sel : null;
  changedPart();
  msgPart("Redone");
}

function deleteFeature(id) {
  const f = feat(id);
  if (!f) return;
  const users = PT.part.features.filter(x => x.sketch_ref === id || x.path_ref === id || x.plane_ref === id || x.source === id || x.tool === id || (x.sources || []).includes(id) || (x.curves || []).includes(id) || (x.features || []).includes(id) || x.point_ref === id || x.axis_ref === id || x.plane_axis === id || x.plane_point === id || x.plane_origin_ref === id || x.plane_xdir_ref === id || (x.points_ref || []).includes(id) || (x.planes_ref || []).includes(id) || (x.sketch_refs || []).includes(id));
  checkpointPart();
  if (PT.cmd && PT.cmd.id === id) PT.cmd = null;
  PT.part.features.splice(featIndex(id), 1);
  if (PT.sel === id) PT.sel = null;
  changedPart();
  msgPart("Deleted " + f.name + (users.length ? "; used by " + users.map(u => u.name).join(", ") : "") + " (Ctrl+Z undoes)", users.length > 0);
}

// ------------------------------------------------------------------ properties (no active command)

function num(id, label, v, step) {
  const val = v === "" || v === null || v === undefined ? "" : pfmt(v, 6);
  return `<label>${label}<input type="text" inputmode="decimal" class="numf" id="${id}" value="${val}"></label>`;
}

/** Suggested next commands for the selection: [type, label, init]. Keys 1, 2, 3 start them. */
function nextCommands() {
  const out = [];
  const A = (type, label, init) => { if (out.length < 3 && !out.some(x => x[0] === type && x[1] === label)) out.push([type, label, init]); };
  const id = PT.sel;
  const solid = PT.solids.length > 0;
  const f = id && feat(id);
  if (!id || id.startsWith("solid:")) {
    if (!PT.part.features.length) { A("sketch", "Sketch"); return out; }
    if (solid) { A("sketch", "Sketch on a face"); A("fillet", "Round"); A("hole", "Hole"); } else A("sketch", "Sketch");
    return out;
  }
  if (BASE_PLANES[id]) { A("sketch", "Sketch on " + BASE_PLANES[id], { plane: id }); A("plane", "Parallel plane", { method: "principal", plane: id }); return out; }
  if (!f) return out;
  if (f.type === "sketch") {
    const st = PT.status[id] || {};
    const closed = st.profiles === undefined || st.profiles > 0;
    if (closed) { A("extrude", solid ? "Extrude (add)" : "Extrude"); if (solid) A("cut", "Cut"); A("revolve", "Revolve"); }
    else { A("surf_sketch", "Extruded surface"); A("surf_sketch", "Revolved surface", { kind: "revolve" }); A("sweep", "Sweep path"); }
    if (!solid) A("surf_sketch", "Extruded surface");
    return out;
  }
  if (f.type === "plane") { A("sketch", "Sketch on " + f.name, { plane: "datum", plane_ref: id }); A("split", "Partition", { method: "datum", plane_ref: id }); A("axis", "Axis normal to " + f.name, { method: "normal", plane_ref: id }); return out; }
  if (f.type === "axis") { A("sketch", "Sketch normal to " + f.name, { plane: "normal", plane_axis: id }); A("plane", "Plane normal to " + f.name, { method: "normal_axis", axis_ref: id }); A("point", "Point on " + f.name, { method: "axis", axis_ref: id }); return out; }
  if (f.type === "point") { A("axis", "Axis through " + f.name, { method: "point_dir", point_ref: id }); A("plane", "Plane through " + f.name, { method: "point_normal", point_ref: id }); A("point", "Point offset from " + f.name, { method: "offset", point_ref: id }); return out; }
  if (SURFACE_TYPES.has(f.type)) {
    if (CURVE_TYPES.has(f.type)) { A("sweep", "Sweep along the curve"); A("plane", "Plane normal to the curve", { method: "edge", curve: id }); }
    else { A("thicken", "Thicken"); A("surf_trim", "Trim surface"); A("surf_extend", "Extend surface"); }
    return out;
  }
  A("sketch", "Sketch on a face"); A("fillet", "Round"); A("chamfer", "Chamfer");
  return out;
}
// keys of the Next commands: 1 2 3 (default, also the numeric keypad), 7 8 9 (left-handed option)
const NEXT_CODES_LEFT = ["Digit7", "Digit8", "Digit9"];
function nextKeyLabel(i) { return leftKeys() ? codeLabel(NEXT_CODES_LEFT[i]) : String(i + 1); }
function nextIndexOf(e) {
  if (leftKeys()) return NEXT_CODES_LEFT.indexOf(e.code);
  return /^[1-3]$/.test(e.key) ? +e.key - 1 : -1;
}
window.SHORTCUTS.push({ tab: "Part", rows: () => [[[0, 1, 2].map(nextKeyLabel).join(" "), "Next commands"], ["Space", "Hide / show the element under the cursor"],
  ["Enter / Ctrl+E", "Finish the command"], ["Esc", "Cancel the command"], ["Ctrl+Z / Ctrl+Y", "Undo / Redo"], ["Delete", "Delete the selected feature"]] });
window.addEventListener("optionschanged", () => { if (PT.part && !PT.cmd) renderProps(); });
function nextHtml() {
  const items = nextCommands();
  if (!items.length) return "";
  return `<div class="pt-next"><span class="lbl">Next:</span>` + items.map(([t, label], i) => `<button type="button" data-next="${i}">${pesc(label)}<kbd>${nextKeyLabel(i)}</kbd></button>`).join("") + `</div>`;
}
function bindNext(box) {
  const items = nextCommands();
  box.querySelectorAll("button[data-next]").forEach(b => { b.onclick = () => runNext(items[+b.dataset.next]); });
}
function runNext(item) {
  if (!item) return;
  const [type, , init] = item;
  const sel = PT.sel && feat(PT.sel);
  startCommand(type, init || null);
  if (!PT.cmd) return;
  const f = feat(PT.cmd.id);
  if (init) Object.assign(f, init);
  if (type === "sweep" && sel) {
    if (sel.type === "sketch") { f.path_ref = sel.id; if (f.sketch_ref === sel.id) f.sketch_ref = null; }
    else if (CURVE_TYPES.has(sel.type)) { f.path_source = sel.id; f.path_ref = null; }
  }
  PT.dirty = true;
  renderCommand(); scheduleBuild();
}

// ------------------------------------------------------------------ body inspection (free edges, gaps, small faces)

const INSPECT = { gap_tol: 0.1, min_area: 0.01, min_edge: 0.01, showAll: true };

async function inspectBody(id) {
  const body = id && PT.surfaces[id] ? id : null;
  const name = body ? (feat(body) ? feat(body).name : body) : "Solid";
  status("Inspecting " + name + "...");
  try {
    const r = await postJSON("/api/part/inspect", { part: PT.part, body, gap_tol: INSPECT.gap_tol, min_area: INSPECT.min_area, min_edge: INSPECT.min_edge });
    const rep = await r.json();
    PT.inspect = { body, name, summary: rep.summary, issues: rep.issues, active: -1, showAll: INSPECT.showAll };
    status("Ready");
    renderInspect();
    drawSelection();
  } catch (e) { showErr(e); }
}

function renderInspect() {
  const box = $("#pt-props"), I = PT.inspect;
  if (!I) return;
  $("#pt-cmdbar").hidden = true;
  const S = I.summary || {};
  const kinds = { gap: "Gaps", pointgap: "Vertex gaps", nonmanifold: "Non-manifold edges", free: "Free edges", smallface: "Small faces", smalledge: "Short edges" };
  const counts = {};
  for (const x of I.issues) counts[x.kind] = (counts[x.kind] || 0) + 1;
  let h = `<p><strong>Inspection: ${pesc(I.name)}</strong></p>` +
    `<p class="hint">${S.faces} faces, ${S.edges} edges, ${S.vertices} vertices, area ${pfmt(S.area, 1)} mm^2. ${S.free_edges} free edge(s), free length ${pfmt(S.free_length, 2)} mm. ` +
    `${S.shells} shell(s), ${S.closed_shells} closed. ${S.valid === null ? "" : S.valid ? "Topology valid." : "Topology invalid (BRepCheck)."}</p>` +
    `<p class="hint">${Object.entries(kinds).filter(([k]) => counts[k]).map(([k, n]) => n + " " + counts[k]).join(", ") || "No free edges, gaps, non-manifold edges, small faces or short edges."}</p>` +
    `<div class="grid2"><label>Gap tolerance (mm)<input type="text" inputmode="decimal" class="numf" id="pi-gap" value="${INSPECT.gap_tol}"></label><label>Small face below (mm^2)<input type="text" inputmode="decimal" class="numf" id="pi-area" value="${INSPECT.min_area}"></label>` +
    `<label>Short edge below (mm)<input type="text" inputmode="decimal" class="numf" id="pi-edge" value="${INSPECT.min_edge}"></label><label class="check"><input type="checkbox" id="pi-all"${I.showAll ? " checked" : ""}> Show all in the view</label></div>` +
    `<div class="buttons"><button type="button" id="pi-run">Run again</button><button type="button" id="pi-close">Close</button></div>` +
    (I.issues.length ? `<ul class="check-list">${I.issues.map((x, i) => `<li><a href="#" data-ii="${i}"${i === I.active ? ' class="active"' : ""}>${pesc(x.text)}</a></li>`).join("")}</ul>` : "");
  box.innerHTML = h;
  const num = (id, k) => { const el = $(id); el.onchange = () => { const v = window.numv ? numv(el.value) : parseFloat(el.value); if (v > 0) INSPECT[k] = v; }; };
  num("#pi-gap", "gap_tol"); num("#pi-area", "min_area"); num("#pi-edge", "min_edge");
  $("#pi-all").onchange = () => { INSPECT.showAll = I.showAll = $("#pi-all").checked; drawSelection(); };
  $("#pi-run").onclick = () => inspectBody(I.body);
  $("#pi-close").onclick = () => { PT.inspect = null; renderProps(); drawSelection(); };
  box.querySelectorAll("a[data-ii]").forEach(a => a.onclick = ev => {
    ev.preventDefault();
    I.active = +a.dataset.ii;
    const x = I.issues[I.active];
    // centre the view on the issue
    const t = PT.three, q = new THREE.Vector3(...x.p), d = q.clone().sub(t.controls.target);
    t.camera.position.add(d); t.controls.target.copy(q); t.controls.update();
    box.querySelectorAll("a[data-ii]").forEach(b => b.classList.toggle("active", b === a));
    drawSelection();
  });
}

// ------------------------------------------------------------------ section view (clipping plane with cap)

/** Clipping planes on the model objects (faces, edges, surfaces, sketches): the section plane or none. */
function applyClipping() {
  const t = PT.three;
  if (!t) return;
  const planes = PT.section ? [PT.section.plane] : [];
  t.renderer.localClippingEnabled = !!PT.section;
  t.group.traverse(o => { if (o.material && !o.userData.noclip) o.material.clippingPlanes = planes; });
}

/** Frame of the section plane: base plane or datum plane id -> {o, z}. */
function sectionFrame(id) {
  if (BASE_PLANES[id]) return frameOf({ plane: id });
  const fr = (PT.status[id] || {}).frame;
  return fr || frameOf({ plane: "XY" });
}

/** Range of the offset along the plane normal over the model bounding box: [lo, hi]. */
function sectionRange(fr) {
  const bb = PT.mesh && PT.mesh.bbox;
  if (!bb) return [-50, 50];
  const n = fr.z, o = fr.o;
  let lo = Infinity, hi = -Infinity;
  for (const x of [bb[0], bb[3]]) for (const y of [bb[1], bb[4]]) for (const z of [bb[2], bb[5]]) { const d = (x - o[0]) * n[0] + (y - o[1]) * n[1] + (z - o[2]) * n[2]; lo = Math.min(lo, d); hi = Math.max(hi, d); }
  return [lo, hi];
}

function setSection(on) {
  const t = PT.three;
  if (!on) {
    if (PT.section && PT.section.capObj) t.scene.remove(PT.section.capObj);
    PT.section = null;
    $("#pt-section").hidden = true;
    applyClipping(); drawSelection();
    return;
  }
  if (!PT.section) {
    const fr = sectionFrame("XZ"), [lo, hi] = sectionRange(fr);
    PT.section = { planeId: "XZ", offset: (lo + hi) / 2, flip: false, cap: true, plane: new THREE.Plane(), capObj: null };
  }
  $("#pt-section").hidden = false;
  updateSectionPlane();
  renderSectionPanel();
  refreshSectionCap();
}

function updateSectionPlane() {
  const S = PT.section;
  if (!S) return;
  const fr = sectionFrame(S.planeId);
  const n = new THREE.Vector3(...fr.z).normalize().multiplyScalar(S.flip ? 1 : -1);
  const o = new THREE.Vector3(...fr.o).add(new THREE.Vector3(...fr.z).normalize().multiplyScalar(S.offset));
  // the half space kept is where n . (p - o) >= 0 (three.js keeps the positive side of the plane)
  S.plane.setFromNormalAndCoplanarPoint(n, o);
  S.origin = o.toArray(); S.normal = fr.z.slice();
  applyClipping(); drawSelection();
}

let sectionCapSeq = 0;
async function refreshSectionCap() {
  const S = PT.section, t = PT.three;
  if (!S) return;
  if (S.capObj) { t.scene.remove(S.capObj); S.capObj = null; }
  if (!S.cap || !PT.mesh || !PT.mesh.vertices.length) { render3(); return; }
  const seq = ++sectionCapSeq;
  try {
    const r = await postJSON("/api/part/section", { part: PT.part, origin: S.origin, normal: S.normal });
    const m = await r.json();
    if (seq !== sectionCapSeq || !PT.section) return;
    if (!m.vertices.length) { render3(); return; }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(m.vertices.flat(), 3));
    g.setIndex(m.triangles.flat());
    g.computeVertexNormals();
    const cap = new THREE.Group();
    const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: 0x9aa3ad, metalness: 0.1, roughness: 0.7, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
    mesh.userData.noclip = true;
    cap.add(mesh);
    const pos = [];
    for (const pl of m.edges) for (let k = 0; k + 1 < pl.length; k++) pos.push(...pl[k], ...pl[k + 1]);
    if (pos.length) { const eg = new THREE.BufferGeometry(); eg.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); const l = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0x222222 })); l.userData.noclip = true; cap.add(l); }
    S.capObj = cap;
    t.scene.add(cap);
    render3();
  } catch (e) { showErr(e); }
}

function renderSectionPanel() {
  const S = PT.section, box = $("#pt-section");
  if (!S) return;
  const planes = Object.entries(BASE_PLANES).map(([k, v]) => [k, v]).concat(PT.part.features.filter(f => f.type === "plane" && !f.suppressed).map(f => [f.id, f.name]));
  const fr = sectionFrame(S.planeId), [lo, hi] = sectionRange(fr);
  box.innerHTML = `<strong>Section</strong> <button type="button" id="ps-off">Off</button><br>` +
    `<label>Plane <select id="ps-plane">${planes.map(([k, v]) => `<option value="${k}"${k === S.planeId ? " selected" : ""}>${pesc(v)}</option>`).join("")}</select></label>` +
    `<label>Offset (mm) <input type="range" id="ps-range" min="${lo.toFixed(2)}" max="${hi.toFixed(2)}" step="${((hi - lo) / 400 || 0.01).toFixed(4)}" value="${S.offset}"> <input type="text" class="numf" id="ps-off-v" value="${pfmt(S.offset, 3)}" style="width:70px"></label>` +
    `<label class="check inline"><input type="checkbox" id="ps-flip"${S.flip ? " checked" : ""}> Flip</label> <label class="check inline"><input type="checkbox" id="ps-cap"${S.cap ? " checked" : ""}> Cap</label>`;
  $("#ps-off").onclick = () => { setSection(false); $("#pt-sectionchk").checked = false; };
  $("#ps-plane").onchange = () => { S.planeId = $("#ps-plane").value; const [a, b] = sectionRange(sectionFrame(S.planeId)); S.offset = (a + b) / 2; updateSectionPlane(); renderSectionPanel(); refreshSectionCap(); };
  $("#ps-range").oninput = () => { S.offset = parseFloat($("#ps-range").value); $("#ps-off-v").value = pfmt(S.offset, 3); updateSectionPlane(); };
  $("#ps-range").onchange = () => refreshSectionCap();
  $("#ps-off-v").onchange = () => { const v = window.numv ? numv($("#ps-off-v").value) : parseFloat($("#ps-off-v").value); if (isFinite(v)) { S.offset = v; $("#ps-range").value = v; updateSectionPlane(); refreshSectionCap(); } };
  $("#ps-flip").onchange = () => { S.flip = $("#ps-flip").checked; updateSectionPlane(); };
  $("#ps-cap").onchange = () => { S.cap = $("#ps-cap").checked; refreshSectionCap(); };
}

function renderProps() {
  const box = $("#pt-props");
  if (PT.inspect && !PT.cmd) { renderInspect(); return; }
  $("#pt-cmdbar").hidden = true;
  const id = PT.sel;
  if (!id) { box.innerHTML = '<p class="hint">Click an element in the view or an item in the tree. Double-click a feature to edit its definition.</p>' + nextHtml(); bindNext(box); return; }
  if (BASE_PLANES[id]) { box.innerHTML = `<p><strong>${BASE_PLANES[id]}</strong></p><p class="hint">Reference plane through the origin. Sketches and planes can be placed on it.</p>` + nextHtml(); bindNext(box); return; }
  if (id.startsWith("solid:")) { const s = PT.solids[+id.slice(6)]; box.innerHTML = `<p><strong>Solid ${+id.slice(6) + 1}</strong></p>` + (s ? `<p class="hint">Volume ${pfmt(s.volume_mm3 / 1000, 3)} cm^3, size ${pfmt(s.bbox[3] - s.bbox[0], 2)} x ${pfmt(s.bbox[4] - s.bbox[1], 2)} x ${pfmt(s.bbox[5] - s.bbox[2], 2)} mm</p>` : "") + `<div class="buttons"><button type="button" id="pp-inspect">Inspect</button></div>` + nextHtml(); $("#pp-inspect").onclick = () => inspectBody(null); bindNext(box); return; }
  const f = feat(id);
  if (!f) { box.innerHTML = ""; return; }
  const st = PT.status[id] || {};
  const steps = commandSteps(f);
  let h = `<p><strong>${pesc(f.name)}</strong> <span class="hint">${TYPE_NAMES[f.type]}</span></p>`;
  h += steps.map(s => `<div class="pt-sum"><span class="lbl">${s.label}</span><span>${pesc(s.summary ? s.summary(f) : "")}</span></div>`).join("");
  if (st.error) h += `<p class="hint err">${pesc(st.error)}</p>`;
  else if (st.extent) h += `<p class="hint">${st.profiles} profile(s), extent x ${pfmt(st.extent[0], 2)} to ${pfmt(st.extent[3], 2)}, y ${pfmt(st.extent[1], 2)} to ${pfmt(st.extent[4], 2)}, z ${pfmt(st.extent[2], 2)} to ${pfmt(st.extent[5], 2)} mm${st.note ? ". " + pesc(st.note) : ""}</p>`;
  else if (st.frame) h += `<p class="hint">Origin (${st.frame.o.map(v => pfmt(v, 2)).join(", ")}) mm, normal (${st.frame.z.map(v => pfmt(v, 3)).join(", ")})</p>`;
  else if (st.faces !== undefined && st.faces_before !== undefined) h += `<p class="hint">${st.faces_before} → ${st.faces} faces, ${st.edges_before} → ${st.edges} edges${st.note ? ". " + pesc(st.note) : ""}</p>`;
  else if (st.surface) h += `<p class="hint">${st.curve ? "Curve, length " + pfmt(st.length, 2) + " mm" : "Surface, " + st.faces + " face(s), " + pfmt(st.area, 1) + " mm^2"}${st.note ? ". " + pesc(st.note) : ""}</p>`;
  h += `<div class="buttons"><button type="button" id="pp-edit" class="primary">Edit definition</button>` +
    (f.type === "sketch" ? `<button type="button" id="pp-sketch">Edit sketch</button>` : "") +
    (PT.surfaces[id] && !(st.curve) ? `<button type="button" id="pp-inspect" title="Free edges, gaps, non-manifold edges, small faces and short edges of the surface body">Inspect</button>` : "") + `</div>`;
  box.innerHTML = h + nextHtml();
  $("#pp-edit").onclick = () => editDefinition(id);
  if ($("#pp-inspect")) $("#pp-inspect").onclick = () => inspectBody(id);
  if ($("#pp-sketch")) $("#pp-sketch").onclick = () => editSketch(id);
  bindNext(box);
}

function editDefinition(id) {
  const f = feat(id);
  if (!f) return;
  startCommand(f.type, null, id);
}

// ------------------------------------------------------------------ commands (step-based command bar)
// A command defines a feature through ordered steps. A step with "kinds" takes elements clicked in the view
// (or in the tree) into f[prop]; a step without kinds carries parameter fields. The feature exists in the
// tree while it is defined and the part rebuilds live; Cancel removes a new feature or restores an edited one.

const hasValue = v => Array.isArray(v) ? v.length > 0 : v !== null && v !== undefined && v !== "";
const bindAll = (box, map) => { for (const [sel, fn] of Object.entries(map)) { const el = box.querySelector(sel); if (el) el.onchange = () => { fn(el); changedPart(); }; } };
const check = (id, label, on) => `<label class="check"><input type="checkbox" id="${id}"${on ? " checked" : ""}> ${label}</label>`;
const select = (id, label, opts, cur) => `<label>${label}<select id="${id}">${opts.map(([v, t]) => `<option value="${pesc(v)}"${String(v) === String(cur) ? " selected" : ""}>${pesc(t)}</option>`).join("")}</select></label>`;
const v3 = (id, lab, a) => `<p class="hint" style="margin-bottom:2px">${lab}</p><div class="grid3">` + num(id + "x", "x", a[0]) + num(id + "y", "y", a[1]) + num(id + "z", "z", a[2]) + `</div>`;
const bind3 = (box, id, fn) => ["x", "y", "z"].forEach(k => { const el = box.querySelector("#" + id + k); if (el) el.onchange = () => { fn(["x", "y", "z"].map(q => numv(box.querySelector("#" + id + q).value) || 0)); changedPart(); }; });

function sketchField(f, prop, label) {
  const sks = sketchItems(featIndex(f.id));
  return `<label>${label || "Sketch"}<select id="pf-${prop}"><option value="">(none)</option>${sks.map(s => `<option value="${pesc(s.id)}"${s.id === f[prop] ? " selected" : ""}>${pesc(s.name)}</option>`).join("")}</select></label>` +
    `<div class="buttons"><button type="button" data-newsketch="${prop}">New sketch</button>` + (f[prop] ? `<button type="button" data-editsketch="${prop}">Edit sketch</button>` : "") + `<span class="hint">or click a sketch in the view</span></div>`;
}
function bindSketchField(box, f, prop) {
  const sel = box.querySelector("#pf-" + prop);
  if (sel) sel.onchange = () => { f[prop] = sel.value || null; changedPart(); };
  box.querySelectorAll("button[data-newsketch]").forEach(b => b.onclick = () => newSketchFor(f, b.dataset.newsketch));
  box.querySelectorAll("button[data-editsketch]").forEach(b => b.onclick = () => { if (f[b.dataset.editsketch]) editSketch(f[b.dataset.editsketch]); });
}
function sourceSelect(id, f, prop, multi, curves) {
  const srcs = surfaceItems(featIndex(f.id), curves);
  const cur = multi ? new Set(f[prop] || []) : f[prop];
  if (multi) return srcs.map(x => `<label class="check"><input type="checkbox" data-src="${pesc(x.id)}"${cur.has(x.id) ? " checked" : ""}> ${pesc(x.name)}</label>`).join("") || `<p class="hint">No ${curves ? "curve" : "surface"} above this feature.</p>`;
  return `<label>${curves ? "Curve" : "Surface"}<select id="${id}"><option value="">(none)</option>${srcs.map(x => `<option value="${pesc(x.id)}"${x.id === cur ? " selected" : ""}>${pesc(x.name)}</option>`).join("")}</select></label>`;
}
function planeSelectField(item) {
  const i = featIndex(item.id);
  const opts = Object.entries(BASE_PLANES).map(([k, n]) => [k, n]).concat(planeItems(i).map(p => ["datum:" + p.id, p.name]));
  opts.push(["normal", "Normal to an edge or curve"]);
  if (item.plane === "face") opts.push(["face", "A planar face"]);
  const cur = item.plane === "datum" ? "datum:" + item.plane_ref : item.plane;
  let h = `<div class="grid2">` + select("pf-plane", "Plane", opts, cur) + num("pf-offset", "Offset (mm)", item.offset || 0) + `</div>`;
  if (item.plane === "normal") h += `<div class="grid2">` + num("pf-pt", "Position along the edge (0 to 1)", item.plane_t === undefined ? 0.5 : item.plane_t) + `<label class="check bottom"><input type="checkbox" id="pf-pflip"${item.plane_flip ? " checked" : ""}> Flip the normal</label></div>` +
    `<p class="hint">${item.plane_edge ? "Edge of the solid picked." : item.plane_curve ? "Curve body " + itemName(item.plane_curve) + "." : "Click an edge or a curve in the view."}</p>`;
  return h;
}
function bindPlaneSelect(box, item) {
  bindAll(box, {
    "#pf-plane": el => { const v = el.value; if (v.startsWith("datum:")) { item.plane = "datum"; item.plane_ref = v.slice(6); } else { item.plane = v; if (v === "normal" && item.plane_t === undefined) item.plane_t = 0.5; } },
    "#pf-offset": el => { item.offset = numv(el.value) || 0; },
    "#pf-pt": el => { const t = numv(el.value); item.plane_t = t >= 0 && t <= 1 ? t : 0.5; },
    "#pf-pflip": el => { item.plane_flip = el.checked; },
  });
}
/** A plane / face / edge / curve clicked in the view sets the plane of a sketch item or a datum reference. */
/** Sketch x direction for a plane of normal n from the 3D view: the principal axis (+-X, +-Y, +-Z, projected into
 *  the plane) nearest the screen right direction, or the screen right direction itself when no principal axis is
 *  within 45 deg of it. */
function viewXdir(n) {
  const t = PT.three;
  if (!t || !t.camera) return null;
  const N = new THREE.Vector3(...n).normalize();
  const proj = v => v.clone().addScaledVector(N, -v.dot(N));
  const r = proj(new THREE.Vector3(1, 0, 0).applyQuaternion(t.camera.quaternion));
  if (r.length() < 1e-6) return null;
  r.normalize();
  let best = r, bd = 0.7071;
  for (const a of [[1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, 0, 0], [0, -1, 0], [0, 0, -1]]) {
    const v = proj(new THREE.Vector3(...a));
    if (v.length() < 1e-6) continue;
    v.normalize();
    if (v.dot(r) > bd) { bd = v.dot(r); best = v; }
  }
  return best.toArray().map(x => Math.abs(x) < 1e-12 ? 0 : +x.toFixed(12));
}

function acceptPlanePick(item, h) {
  if (h.kind === "plane") { if (BASE_PLANES[h.id]) item.plane = h.id; else { item.plane = "datum"; item.plane_ref = h.id; } item.offset = 0; }
  else if (h.kind === "face") {
    item.plane = "face"; item.plane_face = refOf(h); item.offset = 0;
    // sketch x axis from the view: the principal direction nearest the screen right (the sketch opens as the face
    // is seen in the view); an x axis feature of the sketch is kept
    const k = PT.mesh && PT.mesh.face_keys && PT.mesh.face_keys[h.fi];
    if (!item.plane_xdir_ref && k && k.n) { const xd = viewXdir(k.n); if (xd) item.plane_xdir = xd; }
  }
  else if (h.kind === "edge") { item.plane = "normal"; item.plane_edge = refOf(h); item.plane_curve = null; item.plane_axis = null; if (item.plane_t === undefined) item.plane_t = 0.5; }
  else if (h.kind === "curve") { item.plane = "normal"; item.plane_curve = h.id; item.plane_edge = null; item.plane_axis = null; if (item.plane_t === undefined) item.plane_t = 0.5; }
  else if (h.kind === "axis") { item.plane = "normal"; item.plane_axis = h.id; item.plane_edge = null; item.plane_curve = null; }
  PT.dirty = true;
}
function planeSummary(item) {
  if (item.plane === "normal" && item.plane_axis) return "Normal to " + itemName(item.plane_axis) + (item.plane_point ? " at " + itemName(item.plane_point) : "");
  if (item.plane === "normal") return "Normal to " + (item.plane_curve ? itemName(item.plane_curve) : "an edge") + " at " + pfmt(item.plane_t === undefined ? 0.5 : item.plane_t, 2);
  if (item.plane === "face") return "A planar face" + (item.offset ? ", offset " + pfmt(item.offset) + " mm" : "");
  return planeName(item.plane === "datum" ? item.plane_ref : item.plane) + (item.offset ? ", offset " + pfmt(item.offset) + " mm" : "");
}

const edgeModeHtml = f => `<p class="hint" style="margin-bottom:2px">Click mode</p><label class="check inline"><input type="radio" name="pf-emode" value="edge"${(PT.cmd.emode || "edge") === "edge" ? " checked" : ""}> Edge</label>` +
  `<label class="check inline"><input type="radio" name="pf-emode" value="tangent"${PT.cmd.emode === "tangent" ? " checked" : ""}> Tangent chain</label>` +
  `<label class="check inline"><input type="radio" name="pf-emode" value="face"${PT.cmd.emode === "face" ? " checked" : ""}> All edges of a face</label>`;
const bindEdgeMode = box => box.querySelectorAll("input[name=pf-emode]").forEach(r => r.onchange = () => { PT.cmd.emode = r.value; });
/** Edge selection step: single edges, tangent chains or all edges of a clicked face, toggled. */
function edgesStep(label, prop, hint) {
  return { key: prop, label, kinds: ["edge", "face"], prop, hint: hint || "Click the edges (click again to deselect).",
    accept(f, h) {
      const mode = PT.cmd.emode || "edge";
      if (h.surface && f.type !== "surf_fill" && f.type !== "curve_extract") { msgPart("Click an edge of the solid", true); return; }
      if (h.surface && h.kind === "edge") { applyPick(f, { prop, kinds: ["edge"], single: false }, h); return; }
      if (h.kind === "face") { expandEdges(f, prop, "faces", [refOf(h)]); return; }
      if (mode === "tangent") { expandEdges(f, prop, "tangent", [refOf(h)]); return; }
      applyPick(f, { prop, kinds: ["edge"], single: false }, h);
    },
    html: f => edgeModeHtml(f) + `<p class="hint">${(f[prop] || []).length} edge(s) selected.</p><div class="buttons"><button type="button" data-clear="${prop}">Clear</button></div>`,
    bind: (f, box) => { bindEdgeMode(box); box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f[b.dataset.clear] = []; changedPart(); }); },
    summary: f => (f[prop] || []).length + " edge(s)" };
}
function facesStep(label, prop, hint, single, sfaces) {
  return { key: prop, label, kinds: sfaces ? ["face", "sface"] : ["face"], prop, single: !!single, hint: hint || (single ? "Click the face." : "Click the faces (click again to deselect)."),
    html: f => `<p class="hint">${single ? (f[prop] ? "1 face" : "no face") : (f[prop] || []).length + " face(s)"} selected.</p>` + (single ? "" : `<div class="buttons"><button type="button" data-clear="${prop}">Clear</button></div>`),
    bind: (f, box) => box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f[b.dataset.clear] = []; changedPart(); }),
    summary: f => single ? (f[prop] ? "1 face" : "none") : (f[prop] || []).length + " face(s)" };
}
function sourceStep(label, prop, curves, hint) {
  return { key: prop, label, kinds: [curves === true ? "curve" : "surface"].concat(curves === undefined ? ["curve"] : []), prop, single: true,
    hint: hint || "Click a " + (curves === true ? "curve" : "surface") + " body in the view, or choose it.",
    html: f => sourceSelect("pf-" + prop, f, prop, false, curves === undefined ? undefined : curves),
    bind: (f, box) => bindAll(box, { ["#pf-" + prop]: el => { f[prop] = el.value || null; } }),
    summary: f => f[prop] ? itemName(f[prop]) : "none" };
}
/** Source step taking a surface body or faces of the solid (sewn into one surface). */
function surfaceOrFacesStep(label, hint, before) {
  return { key: "source", label: label || "Surface", get kinds() { return PT.cmd && PT.cmd.sface ? ["sface", "face"] : ["surface", "face"]; }, before: before === undefined ? false : before,
    hint: hint || "Click a surface body, or faces of the solid (click again to deselect a face); or choose a surface body. Single faces of surface bodies: tick the option.",
    accept: (f, h) => {
      if (h.kind === "surface") { f.source = h.id; f.faces = []; }
      else { f.source = null; f.faces = f.faces || []; const ref = refOf(h); const i = f.faces.findIndex(x => sameRef(x, ref)); if (i >= 0) f.faces.splice(i, 1); else f.faces.push(ref); }
      PT.dirty = true;
    },
    html: f => sourceSelect("pf-source", f, "source", false, false) + check("pf-sface", "Pick single faces of surface bodies (a portion of a surface)", PT.cmd && PT.cmd.sface) +
      `<p class="hint">${(f.faces || []).length ? (f.faces || []).length + " face(s) selected." : f.source ? itemName(f.source) + "." : "Nothing selected."}</p>` +
      ((f.faces || []).length ? `<div class="buttons"><button type="button" data-clear="faces">Clear faces</button></div>` : ""),
    bind: (f, box) => { bindAll(box, { "#pf-source": el => { f.source = el.value || null; if (el.value) f.faces = []; } }); const sf = box.querySelector("#pf-sface"); if (sf) sf.onchange = () => { PT.cmd.sface = sf.checked; }; box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.faces = []; changedPart(); }); },
    done: f => !!f.source || (f.faces || []).length > 0,
    summary: f => (f.faces || []).length ? (f.faces || []).length + " face(s)" : f.source ? itemName(f.source) : "none" };
}

function profileStep(prop, label) {
  return { key: prop || "sketch_ref", label: label || "Profile", kinds: ["sketch"], prop: prop || "sketch_ref", single: true, before: false,
    hint: "Click a sketch in the view, choose it, or draw a new one.",
    html: f => sketchField(f, prop || "sketch_ref", "Sketch"),
    bind: (f, box) => bindSketchField(box, f, prop || "sketch_ref"),
    summary: f => f[prop || "sketch_ref"] ? itemName(f[prop || "sketch_ref"]) : "none" };
}
const nameField = f => `<label>Name<input type="text" id="pf-name" value="${pesc(f.name)}"></label>`;
const resultLine = f => { const st = PT.status[f.id] || {}; if (st.error) return `<p class="hint err">${pesc(st.error)}</p>`; if (st.faces !== undefined && st.faces_before !== undefined) return `<p class="hint">Result: ${st.faces_before} → ${st.faces} faces, ${st.edges_before} → ${st.edges} edges${st.note ? ". " + pesc(st.note) : ""}</p>`; if (st.note) return `<p class="hint">${pesc(st.note)}</p>`; return ""; };

const COMMANDS = {
  sketch: {
    title: "Sketch", startStep: 0,
    defaults: init => ({ plane: (init && init.plane) || "XY", offset: 0, sketch: emptySketch() }),
    steps: f => [{ key: "plane", label: "Plane", kinds: ["plane", "face", "edge", "curve", "axis"], before: false, hint: "Click a reference plane, a plane feature, a planar face, an edge or an axis feature (plane normal to it). Double-click opens the sketch editor on it.",
      accept: acceptPlanePick, html: planeSelectField, bind: (f, box) => bindPlaneSelect(box, f), done: f => !!f.plane && (f.plane !== "normal" || f.plane_edge || f.plane_curve || f.plane_axis), summary: planeSummary },
      { key: "origin", label: "Origin and x axis", kinds: ["edge", "face", "point", "axis"], optional: true, before: false, hint: "Click an edge: the sketch origin goes to its nearer end and the sketch x axis along it. Click a face: the origin goes to its centre. Click a point feature: the origin. Click an axis feature: the sketch x axis. Nothing clicked: the plane origin.",
        accept: (f, h) => {
          if (h.kind === "point" && h.vertex) { f.plane_origin = h.point.slice(); delete f.plane_origin_ref; }
          else if (h.kind === "point") { f.plane_origin_ref = h.id; delete f.plane_origin; }
          else if (h.kind === "axis") { f.plane_xdir_ref = h.id; delete f.plane_xdir; }
          else if (h.kind === "edge") {
            const pl = h.polyline || PT.mesh.edges[h.index]; const a = pl[0], b = pl[pl.length - 1];
            const d = q => Math.hypot(q[0] - h.point[0], q[1] - h.point[1], q[2] - h.point[2]);
            const [o, e] = d(a) <= d(b) ? [a, b] : [b, a];
            f.plane_origin = o.slice(); f.plane_xdir = [e[0] - o[0], e[1] - o[1], e[2] - o[2]]; delete f.plane_origin_ref; delete f.plane_xdir_ref;
          } else if (h.kind === "face") { f.plane_origin = h.key.c.slice(); delete f.plane_origin_ref; }
          PT.dirty = true;
        },
        html: f => (f.plane_origin_ref ? `<p class="hint">Origin at ${pesc(itemName(f.plane_origin_ref))}.</p>` : v3("pf-po", "Origin (mm, projected onto the plane)", f.plane_origin || (PT.status[f.id] && PT.status[f.id].frame ? PT.status[f.id].frame.o : [0, 0, 0]))) +
          (f.plane_xdir_ref ? `<p class="hint">Sketch x along ${pesc(itemName(f.plane_xdir_ref))}.</p>` : f.plane_xdir ? `<p class="hint">Sketch x along (${f.plane_xdir.map(v => pfmt(v, 3)).join(", ")}).</p>` : "") +
          `<div class="buttons"><button type="button" id="pf-poreset">Plane origin and default x axis</button></div>` +
          (PT.status[f.id] && PT.status[f.id].frame ? `<p class="hint">Origin (${PT.status[f.id].frame.o.map(v => pfmt(v, 2)).join(", ")}) mm, sketch x (${PT.status[f.id].frame.x.map(v => pfmt(v, 3)).join(", ")}), normal (${PT.status[f.id].frame.z.map(v => pfmt(v, 3)).join(", ")})</p>` : ""),
        bind: (f, box) => { bind3(box, "pf-po", v => { f.plane_origin = v; }); const b = box.querySelector("#pf-poreset"); if (b) b.onclick = () => { delete f.plane_origin; delete f.plane_xdir; delete f.plane_origin_ref; delete f.plane_xdir_ref; changedPart(); }; },
        summary: f => (f.plane_origin_ref ? itemName(f.plane_origin_ref) : f.plane_origin ? "(" + f.plane_origin.map(v => pfmt(v, 2)).join(", ") + ")" : "plane origin") + (f.plane_xdir_ref ? ", x along " + itemName(f.plane_xdir_ref) : f.plane_xdir ? ", x along edge" : "") }],
    finishLabel: "Draw",
    finish: (f, isNew, resume) => { editSketch(f.id, isNew, undefined, resume); },
  },
  point: {
    title: "Point", startStep: 0,
    defaults: () => ({ method: "coords", point: [0, 0, 0], t: 0.5, distance: 0, offset_vec: [0, 0, 0] }),
    steps: f => {
      const m = f.method || "coords";
      const i0 = featIndex(f.id);
      const steps = [{ key: "method", label: "Method", html: f => select("pf-pmethod", "Method", Object.entries(POINT_METHODS), m) +
          (m === "coords" ? v3("pf-pxyz", "Coordinates (mm)", f.point || [0, 0, 0]) : "") +
          (m === "edge" ? `<div class="grid2">` + num("pf-pt", f.sketch_curve ? "Position along the curve (0 to 1; empty: the end nearer the click)" : "Position along the edge (0 to 1)", f.t === undefined || f.t === null ? (f.sketch_curve ? "" : 0.5) : f.t) + `<span></span></div>` : "") +
          (m === "axis" ? `<div class="grid2">` + num("pf-pdist", "Distance from the axis origin (mm)", f.distance || 0) + `<span></span></div>` : ""),
        bind: (f, box) => { bindAll(box, { "#pf-pmethod": el => { f.method = el.value; }, "#pf-pt": el => { const t = el.value.trim() === "" ? NaN : numv(el.value); f.t = t >= 0 && t <= 1 ? t : (f.sketch_curve ? null : 0.5); }, "#pf-pdist": el => { f.distance = numv(el.value) || 0; } }); bind3(box, "pf-pxyz", v => { f.point = v; }); },
        summary: f => POINT_METHODS[m] + (m === "coords" ? ": (" + (f.point || [0, 0, 0]).map(v => pfmt(v, 2)).join(", ") + ")" : ""),
        // Coordinates: a click on a vertex or a point feature copies its coordinates
        kinds: m === "coords" ? ["point"] : undefined, hint: m === "coords" ? "Type the coordinates, or click a vertex of the part or a point feature to copy its coordinates." : undefined,
        accept: (f, h) => { if (h.point) f.point = h.point.map(v => +(+v).toFixed(6)); } }];
      if (m === "edge") steps.push(curveRefStep(false));
      if (m === "face") steps.push(facesStep("Face", "face", "Click the face: the point is its centre.", true));
      if (m === "offset") steps.push(datumStep("point", "Point", "point_ref"));
      if (m === "axis" || m === "axis_plane") steps.push(datumStep("axis", "Axis", "axis_ref"));
      if (m === "axis_plane") steps.push(datumStep("plane", "Plane", "plane_ref", "Click a plane feature in the view or the tree."));
      if (m === "midpoint") steps.push({ key: "points_ref", label: "Two points", kinds: ["point"], prop: "points_ref", hint: "Click two point features or vertices of the part.",
        html: f => `<p class="hint">${(f.points_ref || []).length} point(s) selected.</p><div class="buttons"><button type="button" data-clear="points_ref">Clear</button></div>`,
        bind: (f, box) => box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.points_ref = []; changedPart(); }),
        done: f => (f.points_ref || []).length === 2, summary: f => (f.points_ref || []).map(itemName).join(", ") || "none" });
      steps.push({ key: "offset", label: "Offset", optional: true, html: f => v3("pf-poff", "Offset dx, dy, dz (mm)", f.offset_vec || [0, 0, 0]) + ((PT.status[f.id] || {}).point ? `<p class="hint">Point (${PT.status[f.id].point.map(v => pfmt(v, 3)).join(", ")}) mm</p>` : ""),
        bind: (f, box) => bind3(box, "pf-poff", v => { f.offset_vec = v; }),
        summary: f => (f.offset_vec || []).some(v => v) ? "(" + f.offset_vec.map(v => pfmt(v, 2)).join(", ") + ") mm" : "none" });
      return steps;
    },
  },
  axis: {
    title: "Axis", startStep: 0,
    defaults: () => ({ method: "point_dir", point: [0, 0, 0], direction: "Z", p1: [0, 0, 0], p2: [0, 0, 100], flip: false }),
    steps: f => {
      const m = f.method || "point_dir";
      const steps = [{ key: "method", label: "Method", html: f => select("pf-amethod", "Method", Object.entries(AXIS_METHODS), m) +
          (m === "point_dir" ? (f.point_ref ? "" : v3("pf-apt", "Point (mm, when no point feature is picked)", f.point || [0, 0, 0])) +
            select("pf-adir", "Direction", [["X", "X"], ["Y", "Y"], ["Z", "Z"], ["vec", "Vector"]], Array.isArray(f.direction) ? "vec" : (f.direction || "Z")) +
            (Array.isArray(f.direction) ? v3("pf-avec", "Direction vector", f.direction) : "") : "") +
          (m === "two_points" && (f.points_ref || []).length < 2 ? v3("pf-ap1", "Point 1 (mm, when no point features are picked)", f.p1 || [0, 0, 0]) + v3("pf-ap2", "Point 2 (mm)", f.p2 || [0, 0, 100]) : ""),
        bind: (f, box) => { bindAll(box, { "#pf-amethod": el => { f.method = el.value; }, "#pf-adir": el => { f.direction = el.value === "vec" ? [0, 0, 1] : el.value; } });
          bind3(box, "pf-apt", v => { f.point = v; }); bind3(box, "pf-avec", v => { f.direction = v; }); bind3(box, "pf-ap1", v => { f.p1 = v; }); bind3(box, "pf-ap2", v => { f.p2 = v; }); },
        summary: f => AXIS_METHODS[m] }];
      if (m === "two_points") steps.push({ key: "points_ref", label: "Two points", kinds: ["point"], prop: "points_ref", optional: true, hint: "Click two point features or vertices of the part (or type the coordinates in Method).",
        html: f => `<p class="hint">${(f.points_ref || []).length} point(s) selected.</p><div class="buttons"><button type="button" data-clear="points_ref">Clear</button></div>`,
        bind: (f, box) => box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.points_ref = []; changedPart(); }),
        done: f => true, summary: f => (f.points_ref || []).map(itemName).join(", ") || "coordinates" });
      if (m === "point_dir" || m === "normal" || m === "parallel") steps.push(datumStep("point", "Point", "point_ref", m === "point_dir" ? "Click a point feature or a vertex of the part (or type the coordinates in Method)." : "Click a point feature or a vertex the axis passes through (none: the reference origin).", true));
      if (m === "edge") steps.push({ key: "edge", label: "Edge or curve", kinds: ["edge", "curve"], single: true, hint: "Click a straight edge of the solid or a straight curve body.",
        accept: (f, h) => { if (h.kind === "edge") { f.edge = refOf(h); f.curve = null; } else { f.curve = h.id; f.edge = null; } PT.dirty = true; },
        html: f => sourceSelect("pf-curve", f, "curve", false, true).replace("Curve<", "Or a curve body<"),
        bind: (f, box) => bindAll(box, { "#pf-curve": el => { f.curve = el.value || null; if (el.value) f.edge = null; } }),
        done: f => !!(f.edge || f.curve), summary: f => f.curve ? itemName(f.curve) : f.edge ? "edge" : "none" });
      if (m === "cylinder") steps.push(facesStep("Cylindrical face", "face", "Click a cylindrical, conical or toroidal face.", true));
      if (m === "planes") steps.push({ key: "planes_ref", label: "Two planes", kinds: ["plane"], prop: "planes_ref", hint: "Click two plane features.",
        accept: (f, h) => { if (BASE_PLANES[h.id]) { msgPart("Reference planes cannot be used here; make a Plane feature on them first", true); return; } f.planes_ref = f.planes_ref || []; const i = f.planes_ref.indexOf(h.id); if (i >= 0) f.planes_ref.splice(i, 1); else f.planes_ref.push(h.id); PT.dirty = true; },
        html: f => `<p class="hint">${(f.planes_ref || []).length} plane(s) selected.</p><div class="buttons"><button type="button" data-clear="planes_ref">Clear</button></div>`,
        bind: (f, box) => box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.planes_ref = []; changedPart(); }),
        done: f => (f.planes_ref || []).length === 2, summary: f => (f.planes_ref || []).map(itemName).join(", ") || "none" });
      if (m === "normal") steps.push(datumStep("plane", "Plane", "plane_ref", "Click a plane feature in the view or the tree."));
      if (m === "parallel") steps.push(datumStep("axis", "Axis", "axis_ref"));
      steps.push({ key: "flip", label: "Direction", optional: true, html: f => check("pf-aflip", "Flip the direction", f.flip) + ((PT.status[f.id] || {}).axis ? `<p class="hint">Origin (${PT.status[f.id].axis.o.map(v => pfmt(v, 2)).join(", ")}) mm, direction (${PT.status[f.id].axis.d.map(v => pfmt(v, 3)).join(", ")})</p>` : ""),
        bind: (f, box) => bindAll(box, { "#pf-aflip": el => { f.flip = el.checked; } }), summary: f => f.flip ? "flipped" : "" });
      return steps;
    },
  },
  mirror: {
    title: "Mirror",
    defaults: () => ({ features: [], body: false, method: "principal", plane: "YZ", offset: 0 }),
    steps: f => {
      const i0 = featIndex(f.id);
      const cands = PT.part.features.filter((x, i) => i < i0 && SKETCH_TYPES.has(x.type));
      const m = f.method || "principal";
      return [
        { key: "features", label: "Features", kinds: ["face"], before: false, hint: "Click a face of each feature to mirror (click again to deselect), or check the features. Sketch features and holes only.",
          accept: (f, h) => { const id = h.owner; if (!id || !cands.some(x => x.id === id)) { msgPart("Only sketch features and holes above this feature can be mirrored", true); return; }
            f.features = f.features || []; const i = f.features.indexOf(id); if (i >= 0) f.features.splice(i, 1); else f.features.push(id); PT.dirty = true; },
          html: f => { const sel = new Set(f.features || []); return (cands.length ? cands.map(x => `<label class="check"><input type="checkbox" data-pf="${pesc(x.id)}"${sel.has(x.id) ? " checked" : ""}> ${pesc(x.name)}</label>`).join("") : '<p class="hint">No sketch features above this one.</p>') + check("pf-mbody", "Mirror the whole body (fused)", f.body); },
          bind: (f, box) => { box.querySelectorAll("input[data-pf]").forEach(cb => cb.onchange = () => { f.features = [...box.querySelectorAll("input[data-pf]:checked")].map(x => x.dataset.pf); changedPart(); }); bindAll(box, { "#pf-mbody": el => { f.body = el.checked; } }); },
          done: f => (f.features || []).length > 0 || !!f.body, summary: f => ((f.features || []).map(itemName).join(", ") || "") + (f.body ? (f.features && f.features.length ? ", " : "") + "whole body" : "") || "none" },
        { key: "plane", label: "Mirror plane", kinds: ["plane", "face"], before: false, hint: "Click a reference plane, a plane feature or a planar face of the solid.",
          accept: (f, h) => { if (h.kind === "plane") { if (BASE_PLANES[h.id]) { f.method = "principal"; f.plane = h.id; } else { f.method = "datum"; f.plane_ref = h.id; } } else { f.method = "face"; f.face = refOf(h); } PT.dirty = true; },
          html: f => select("pf-mmethod", "Plane", [["principal", "Principal plane + offset"], ["datum", "Plane feature + offset"], ["face", "Planar face of the solid"]], m) +
            (m === "principal" ? `<div class="grid2">` + select("pf-mplane", "Plane", Object.entries(BASE_PLANES), f.plane || "YZ") + num("pf-moff", "Offset (mm)", f.offset || 0) + `</div>` : "") +
            (m === "datum" ? `<div class="grid2">` + select("pf-mdatum", "Plane feature", [["", "(none)"]].concat(planeItems(i0).map(p => [p.id, p.name])), f.plane_ref || "") + num("pf-moff", "Offset (mm)", f.offset || 0) + `</div>` : "") +
            (m === "face" ? `<p class="hint">${f.face ? "1 face" : "no face"} selected.</p>` : ""),
          bind: (f, box) => bindAll(box, { "#pf-mmethod": el => { f.method = el.value; }, "#pf-mplane": el => { f.plane = el.value; }, "#pf-mdatum": el => { f.plane_ref = el.value || null; }, "#pf-moff": el => { f.offset = numv(el.value) || 0; } }),
          done: f => m === "principal" ? !!f.plane : m === "datum" ? !!f.plane_ref : !!f.face,
          summary: f => (m === "principal" ? planeName(f.plane) : m === "datum" ? planeName(f.plane_ref) : f.face ? "planar face" : "none") + (f.offset && m !== "face" ? ", offset " + pfmt(f.offset) + " mm" : "") },
      ];
    },
  },
  plane: {
    title: "Plane",
    defaults: () => ({ method: "principal", plane: "XY", offset: 0, flip: false }),
    steps: f => {
      const m = f.method || "principal";
      const method = { key: "method", label: "Method", html: f => select("pf-method", "Method", Object.entries(PLANE_METHODS), m) + (m === "principal" ? select("pf-splane", "Plane", Object.entries(BASE_PLANES), f.plane || "XY") : "") +
          (m === "datum" ? select("pf-sdatum", "Plane", [["", "(none)"]].concat(planeItems(featIndex(f.id)).map(p => [p.id, p.name])), f.plane_ref || "") : "") +
          (m === "point_normal" ? (f.point_ref ? "" : v3("pf-pp", "Point on the plane (mm, when no point feature is picked)", f.point || [0, 0, 0])) + (f.axis_ref ? "" : v3("pf-pn", "Normal (when no axis feature is picked)", f.normal || [0, 0, 1])) : "") +
          (m === "three_points" ? v3("pf-p1", "Point 1 (mm, origin)", (f.points || [[0, 0, 0]])[0]) + v3("pf-p2", "Point 2 (mm, sketch x)", (f.points || [0, [1, 0, 0]])[1] || [1, 0, 0]) + v3("pf-p3", "Point 3 (mm)", (f.points || [0, 0, [0, 1, 0]])[2] || [0, 1, 0]) : ""),
        bind: (f, box) => { bindAll(box, { "#pf-method": el => { f.method = el.value; }, "#pf-splane": el => { f.plane = el.value; }, "#pf-sdatum": el => { f.plane_ref = el.value || null; } });
          bind3(box, "pf-pp", v => { f.point = v; }); bind3(box, "pf-pn", v => { f.normal = v; });
          [1, 2, 3].forEach(i => bind3(box, "pf-p" + i, v => { f.points = f.points || [[0, 0, 0], [1, 0, 0], [0, 1, 0]]; f.points[i - 1] = v; })); },
        summary: f => PLANE_METHODS[m] + (m === "principal" ? ": " + planeName(f.plane) : m === "datum" ? ": " + planeName(f.plane_ref) : ""),
        kinds: m === "three_points" ? ["point"] : undefined, hint: m === "three_points" ? "Type the points, or click three vertices of the part or point features (point 1, 2, 3 in turn)." : undefined,
        accept: (f, h) => fillThreePoints(f, h) };
      const steps = [method];
      if (m === "datum") steps.push({ key: "plane_ref", label: "Reference plane", kinds: ["plane"], prop: "plane_ref", single: true, before: false, hint: "Click a plane feature in the view or the tree.",
        accept: (f, h) => { if (!BASE_PLANES[h.id]) f.plane_ref = h.id; else { f.method = "principal"; f.plane = h.id; } PT.dirty = true; }, done: f => !!f.plane_ref, summary: f => planeName(f.plane_ref) });
      if (m === "point_normal") { steps.push(datumStep("point", "Point", "point_ref", "Click a point feature or a vertex of the part (or type the point in Method).", true)); steps.push(datumStep("axis", "Normal axis", "axis_ref", "Click an axis feature for the normal (or type the normal in Method).", true)); }
      if (m === "axis_point") { steps.push(datumStep("axis", "Axis", "axis_ref")); steps.push(datumStep("point", "Point", "point_ref")); }
      if (m === "normal_axis") { steps.push(datumStep("axis", "Axis", "axis_ref")); steps.push(datumStep("point", "Point", "point_ref", "Click a point feature or a vertex on the plane (none: the axis origin).", true)); }
      if (m === "face" || m === "angle") steps.push(facesStep("Planar face", "face", "Click the planar face.", true));
      if (m === "midplane") steps.push(facesStep("Two parallel faces", "faces", "Click the two parallel planar faces.", false));
      if (m === "edge" || m === "angle") steps.push(curveRefStep(m === "edge"));
      steps.push({ key: "offset", label: "Offset", html: f => `<div class="grid2">` + num("pf-soff", "Offset along the normal (mm)", f.offset || 0) + (m === "angle" ? num("pf-sang", "Angle from the face (deg)", f.angle === undefined ? 45 : f.angle) : `<span></span>`) + `</div>` + check("pf-flip", "Flip the normal", f.flip) +
          ((PT.status[f.id] || {}).frame ? `<p class="hint">Origin (${PT.status[f.id].frame.o.map(v => pfmt(v, 2)).join(", ")}) mm, normal (${PT.status[f.id].frame.z.map(v => pfmt(v, 3)).join(", ")}), sketch x (${PT.status[f.id].frame.x.map(v => pfmt(v, 3)).join(", ")})</p>` : ""),
        bind: (f, box) => bindAll(box, { "#pf-soff": el => { f.offset = numv(el.value) || 0; }, "#pf-sang": el => { const a = numv(el.value); f.angle = isFinite(a) ? a : 0; }, "#pf-flip": el => { f.flip = el.checked; } }),
        summary: f => (f.offset ? pfmt(f.offset) + " mm" : "0 mm") + (m === "angle" ? ", " + pfmt(f.angle === undefined ? 45 : f.angle) + " deg" : "") + (f.flip ? ", flipped" : "") });
      return steps;
    },
  },
  extrude: {
    title: "Extrude", needsSolid: false,
    defaults: () => ({ sketch_ref: null, depth: 10, symmetric: false, reverse: false }),
    steps: f => [profileStep(), regionsStep(), { key: "extent", label: "Extent", html: f => `<div class="grid2">` + num("pf-depth", "Depth (mm)", f.depth) + select("pf-dir", "Direction", [["normal", "Along the normal"], ["reverse", "Against the normal"], ["symmetric", "Symmetric to the plane"]], f.symmetric ? "symmetric" : f.reverse ? "reverse" : "normal") + `</div>` + check("pf-newbody", "New body (not fused with the part; combine later with Boolean)", f.new_body),
      bind: (f, box) => bindAll(box, { "#pf-depth": el => { const v = numv(el.value); if (v > 0) f.depth = v; }, "#pf-dir": el => { f.symmetric = el.value === "symmetric"; f.reverse = el.value === "reverse"; }, "#pf-newbody": el => { f.new_body = el.checked; } }),
      summary: f => pfmt(f.depth) + " mm" + (f.symmetric ? ", symmetric" : f.reverse ? ", reversed" : "") + (f.new_body ? ", new body" : "") }],
  },
  cut: {
    title: "Cut", needsSolid: true,
    defaults: () => ({ sketch_ref: null, depth: 10, through: true, symmetric: false, reverse: false }),
    steps: f => [profileStep(), regionsStep(), { key: "extent", label: "Extent", html: f => select("pf-type", "Type", [["through", "Through all (both directions)"], ["finite", "Finite depth"]], f.through ? "through" : "finite") +
        (f.through ? "" : `<div class="grid2">` + num("pf-depth", "Depth (mm)", f.depth) + select("pf-dir", "Direction", [["normal", "Along the normal"], ["reverse", "Against the normal"], ["symmetric", "Symmetric to the plane"]], f.symmetric ? "symmetric" : f.reverse ? "reverse" : "normal") + `</div>`),
      bind: (f, box) => bindAll(box, { "#pf-type": el => { f.through = el.value === "through"; }, "#pf-depth": el => { const v = numv(el.value); if (v > 0) f.depth = v; }, "#pf-dir": el => { f.symmetric = el.value === "symmetric"; f.reverse = el.value === "reverse"; } }),
      summary: f => f.through ? "through all" : pfmt(f.depth) + " mm" + (f.symmetric ? ", symmetric" : f.reverse ? ", reversed" : "") }],
  },
  revolve: {
    title: "Revolve",
    defaults: () => ({ sketch_ref: null, angle: 360, axis: "v", mode: "add" }),
    steps: f => {
      const sk = f.sketch_ref && feat(f.sketch_ref);
      const axes = (((sk || {}).sketch || {}).entities || []).filter(e => e.t === "line" && e.constr && !e.axis);
      return [profileStep(), regionsStep(), { key: "axis", label: "Axis and extent", kinds: ["axis"], before: false, hint: "Choose the axis, or click an axis feature in the view or the tree.",
        accept: (f, h) => { f.axis_ref = h.id; PT.dirty = true; },
        html: f => select("pf-axis", "Axis", [["u", "Sketch x axis (u)"], ["v", "Sketch y axis (v)"]].concat(axes.map(e => [e.id, `Construction line ${e.id} (${pfmt(e.x1, 2)}, ${pfmt(e.y1, 2)}) - (${pfmt(e.x2, 2)}, ${pfmt(e.y2, 2)})`])).concat(axisItems(featIndex(f.id)).map(a => ["ref:" + a.id, "Axis feature " + a.name])), f.axis_ref ? "ref:" + f.axis_ref : (f.axis || "v")) +
          `<div class="grid2">` + num("pf-angle", "Angle (deg)", f.angle) + select("pf-mode", "Mode", [["add", "Add material"], ["cut", "Remove material"]], f.mode || "add") + `</div>` + check("pf-newbody", "New body (not fused with the part; combine later with Boolean)", f.new_body) + `<p class="hint">A construction line drawn in the sketch can be the axis.</p>`,
        bind: (f, box) => bindAll(box, { "#pf-axis": el => { if (el.value.startsWith("ref:")) f.axis_ref = el.value.slice(4); else { f.axis = el.value; f.axis_ref = null; } }, "#pf-angle": el => { const v = numv(el.value); if (v > 0 && v <= 360) f.angle = v; }, "#pf-mode": el => { f.mode = el.value; }, "#pf-newbody": el => { f.new_body = el.checked; } }),
        summary: f => pfmt(f.angle) + " deg about " + (f.axis === "u" ? "x" : f.axis === "v" ? "y" : f.axis) + (f.mode === "cut" ? ", remove" : "") }];
    },
  },
  hole: {
    title: "Hole", needsSolid: true,
    defaults: () => ({ sketch_ref: null, dia: 6, depth: null, cbore_dia: null, cbore_depth: null, csink_dia: null, csink_angle: 90, thread: "", tol: "", reverse: false }),
    steps: f => [profileStep("sketch_ref", "Positions"), { key: "hole", label: "Hole", html: f => holePresetHtml(f) + `<div class="grid2">` + num("pf-dia", "Diameter (mm)", f.dia) + num("pf-hdepth", "Depth (mm, empty: through)", f.depth === null || f.depth === undefined ? "" : f.depth) + `</div>` +
        `<div class="grid2">` + num("pf-cbd", "Counterbore dia (mm)", f.cbore_dia || "") + num("pf-cbh", "Counterbore depth (mm)", f.cbore_depth || "") + `</div>` +
        `<div class="grid2">` + num("pf-csd", "Countersink dia (mm)", f.csink_dia || "") + num("pf-csa", "Countersink angle (deg)", f.csink_angle || 90) + `</div>` +
        `<div class="grid2"><label>Thread<input type="text" id="pf-thread" value="${pesc(f.thread || "")}" placeholder="e.g. M8 or M10x1.25"></label><label>Tolerance class<input type="text" id="pf-tol" value="${pesc(f.tol || "")}" placeholder="H7, or 6H for a thread"></label></div>` +
        check("pf-hrev", "Reverse direction", f.reverse) + `<p class="hint">Hole positions: points (or circle centres) of the sketch. The holes go from the sketch plane into the part. Thread and tolerance class appear in the hole callout.</p>`,
      bind: (f, box) => bindAll(box, { "#pf-dia": el => { const v = numv(el.value); if (v > 0) f.dia = v; }, "#pf-hdepth": el => { const v = numv(el.value); f.depth = v > 0 ? v : null; },
        "#pf-cbd": el => { const v = numv(el.value); f.cbore_dia = v > 0 ? v : null; }, "#pf-cbh": el => { const v = numv(el.value); f.cbore_depth = v > 0 ? v : null; },
        "#pf-csd": el => { const v = numv(el.value); f.csink_dia = v > 0 ? v : null; }, "#pf-csa": el => { const v = numv(el.value); if (v > 0 && v < 180) f.csink_angle = v; },
        "#pf-thread": el => { f.thread = el.value.trim(); }, "#pf-tol": el => { f.tol = el.value.trim(); }, "#pf-hrev": el => { f.reverse = el.checked; },
        "#pf-preset": el => { applyHolePreset(f, el.value); } }),
      summary: f => (f.thread || "⌀" + pfmt(f.dia) + " mm") + (f.depth ? ", " + pfmt(f.depth) + " mm deep" : ", through") }],
  },
  thread: {
    title: "Thread", needsSolid: true,
    defaults: () => ({ face: null, thread: "M10", thread_type: "coarse", tol: "6g", length: null, reverse: false, cut_od: false }),
    steps: f => [facesStep("Face", "face", "Click the cylindrical face to thread.", true),
      { key: "thread", label: "Thread", html: f => threadSelectHtml(f) + `<div class="grid2"><label>Tolerance class<input type="text" id="pf-ttol" value="${pesc(f.tol || "6g")}" placeholder="6g"></label>` + num("pf-tlen", "Thread length (mm, empty: whole face)", f.length === null || f.length === undefined ? "" : f.length) + `</div>` +
        check("pf-trev", "Start at the other end of the face", f.reverse) + check("pf-tcut", "Turn the face down to d max of the class over the thread length", f.cut_od) +
        `<p class="hint">Cosmetic thread on the drawing (ISO 6410-1) and a thread callout with the outside diameter to turn, d3 and the thread depth (Hole callouts). Tolerance limits for metric classes only; trapezoidal threads get the nominal dimensions.</p>`,
        bind: (f, box) => bindAll(box, { "#pf-ttype": el => { f.thread_type = el.value; const names = threadNames(el.value); if (el.value !== "custom" && !names.includes(f.thread)) { f.thread = names[0] || ""; } if (Object.values(THREAD_CLASS).includes(f.tol) || !f.tol) f.tol = THREAD_CLASS[el.value] || f.tol; setTimeout(() => { if (document.activeElement && document.activeElement.id === "pf-ttype") document.activeElement.blur(); }, 0); },
          "#pf-tsel": el => { if (el.value) f.thread = el.value; }, "#pf-tcustom": el => { if (el.value.trim()) f.thread = el.value.trim(); }, "#pf-ttol": el => { f.tol = el.value.trim(); },
          "#pf-tlen": el => { const v = numv(el.value); f.length = v > 0 ? v : null; }, "#pf-trev": el => { f.reverse = el.checked; }, "#pf-tcut": el => { f.cut_od = el.checked; } }),
        done: f => !!f.thread, summary: f => (f.thread || "") + (f.tol ? "-" + f.tol : "") + (f.length ? " x " + pfmt(f.length) : "") }],
  },
  sweep: {
    title: "Sweep",
    defaults: () => ({ sketch_ref: null, path_ref: null, path_source: null, mode: "add" }),
    steps: f => [profileStep(), { key: "path", label: "Path", kinds: ["sketch", "curve"], single: true, before: false, hint: "Click the path sketch or a curve body.",
        accept: (f, h) => { if (h.kind === "sketch") { f.path_ref = h.id; f.path_source = null; } else { f.path_source = h.id; f.path_ref = null; } PT.dirty = true; },
        html: f => sketchField(f, "path_ref", "Path sketch") + sourceSelect("pf-path_source", f, "path_source", false, true).replace("Curve<", "Or a curve body<"),
        bind: (f, box) => { bindSketchField(box, f, "path_ref"); bindAll(box, { "#pf-path_source": el => { f.path_source = el.value || null; if (el.value) f.path_ref = null; } }); },
        done: f => !!(f.path_ref || f.path_source), summary: f => f.path_ref ? itemName(f.path_ref) : f.path_source ? itemName(f.path_source) : "none" },
      { key: "mode", label: "Mode", html: f => select("pf-mode", "Mode", [["add", "Add material"], ["cut", "Remove material"]], f.mode || "add") + check("pf-newbody", "New body (not fused with the part; combine later with Boolean)", f.new_body) + `<p class="hint">The profile is swept along the path (one open chain). The profile plane should be normal to the path at its start.</p>`,
        bind: (f, box) => bindAll(box, { "#pf-mode": el => { f.mode = el.value; }, "#pf-newbody": el => { f.new_body = el.checked; } }), summary: f => (f.mode === "cut" ? "remove material" : "add material") + (f.new_body ? ", new body" : "") }],
  },
  fillet: { title: "Fillet", needsSolid: true, defaults: () => ({ value: 2, edges: [] }),
    steps: f => [edgesStep("Edges", "edges"), { key: "value", label: "Radius", html: f => `<div class="grid2">` + num("pf-value", "Radius (mm)", f.value) + `<span></span></div>` + resultLine(f), bind: (f, box) => bindAll(box, { "#pf-value": el => { const v = numv(el.value); if (v > 0) f.value = v; } }), summary: f => pfmt(f.value) + " mm" }] },
  chamfer: { title: "Chamfer", needsSolid: true, defaults: () => ({ value: 1, edges: [] }),
    steps: f => [edgesStep("Edges", "edges"), { key: "value", label: "Distance", html: f => `<div class="grid2">` + num("pf-value", "Distance (mm, equal)", f.value) + `<span></span></div>` + resultLine(f), bind: (f, box) => bindAll(box, { "#pf-value": el => { const v = numv(el.value); if (v > 0) f.value = v; } }), summary: f => pfmt(f.value) + " mm" }] },
  shell: { title: "Shell", needsSolid: true, defaults: () => ({ thickness: 2, faces: [] }),
    steps: f => [Object.assign(facesStep("Open faces", "faces", "Click the faces to remove (openings); none: closed hollow part."), { optional: true }), { key: "thickness", label: "Thickness", html: f => `<div class="grid2">` + num("pf-thick", "Wall thickness (mm)", f.thickness) + `<span></span></div>` + resultLine(f), bind: (f, box) => bindAll(box, { "#pf-thick": el => { const v = numv(el.value); if (v > 0) f.thickness = v; } }), summary: f => pfmt(f.thickness) + " mm" }] },
  boolean: {
    title: "Boolean", needsSolid: true,
    defaults: () => ({ op: "subtract", targets: [], tools: [], keep_tools: false }),
    steps: f => {
      const solidStep = (key, label, hint) => ({ key, label, kinds: ["body"], before: true, hint,
        accept: (f, h) => { f[key] = f[key] || []; const i = f[key].indexOf(h.solid); if (i >= 0) f[key].splice(i, 1); else f[key].push(h.solid); PT.dirty = true; },
        html: f => { const sel = new Set(f[key] || []); return (PT.solids.length ? PT.solids.map((s, i) => `<label class="check"><input type="checkbox" data-ps="${i}"${sel.has(i) ? " checked" : ""}> Solid ${i + 1} (${pfmt(s.volume_mm3 / 1000, 2)} cm^3)</label>`).join("") : '<p class="hint">No solids.</p>') + `<p class="hint">Solids are numbered as in the tree before this feature.</p>`; },
        bind: (f, box) => box.querySelectorAll("input[data-ps]").forEach(cb => cb.onchange = () => { f[key] = [...box.querySelectorAll("input[data-ps]:checked")].map(x => +x.dataset.ps); changedPart(); }),
        done: f => (f[key] || []).length > 0, summary: f => (f[key] || []).length ? (f[key] || []).map(i => "Solid " + (i + 1)).join(", ") : "none" });
      const steps = [{ key: "op", label: "Operation", html: f => select("pf-bop", "Operation", [["union", "Union (fuse)"], ["subtract", "Subtract (target minus tools)"], ["intersect", "Intersect (common volume)"]], f.op || "subtract") + (f.op !== "union" ? check("pf-bkeep", "Keep the tool solids", f.keep_tools) : "") + `<p class="hint">Separate solids come from Extrude, Revolve or Sweep with New body, from Partition or from an imported STEP file.</p>`,
        bind: (f, box) => bindAll(box, { "#pf-bop": el => { f.op = el.value; }, "#pf-bkeep": el => { f.keep_tools = el.checked; } }),
        summary: f => ({ union: "union", subtract: "subtract", intersect: "intersect" })[f.op || "subtract"] + (f.keep_tools && f.op !== "union" ? ", tools kept" : "") },
        solidStep("targets", f.op === "union" ? "Solids" : "Target", f.op === "union" ? "Click each solid to fuse (click again to deselect), or check them." : "Click the target solid(s) (click again to deselect), or check them.")];
      if (f.op !== "union") steps.push(solidStep("tools", "Tools", "Click the tool solid(s), or check them."));
      else steps[1].done = f => (f.targets || []).length + (f.tools || []).length >= 2;
      return steps;
    },
  },
  split: {
    title: "Partition", needsSolid: true, startStep: 0,
    defaults: () => ({ method: "principal", plane: "XY", offset: 0, relative: false, point: [0, 0, 0], normal: [0, 0, 1], points: [[0, 0, 0], [1, 0, 0], [0, 1, 0]], face: null, edge: null, curve: null, t: 0.5, cells: [] }),
    steps: f => {
      const m = f.method || "principal";
      const steps = [{ key: "method", label: "Method", html: f => select("pf-method", "Method", Object.entries(SPLIT_METHODS), m) +
          (m === "principal" ? `<div class="grid2">` + select("pf-splane", "Plane", Object.entries(BASE_PLANES), f.plane || "XY") + num("pf-soff", "Offset (mm)", f.offset || 0) + `</div>` + check("pf-srel", "Offset from the minimum of the part (bounding box) instead of the origin", f.relative) : "") +
          (m === "point_normal" ? (f.point_ref ? "" : v3("pf-pp", "Point on the plane (mm, when no point feature is picked)", f.point || [0, 0, 0])) + (f.axis_ref ? "" : v3("pf-pn", "Normal (when no axis feature is picked)", f.normal || [0, 0, 1])) : "") +
          (m === "three_points" ? [1, 2, 3].map(i => v3("pf-p" + i, "Point " + i + " (mm)", (f.points || [[0, 0, 0], [1, 0, 0], [0, 1, 0]])[i - 1])).join("") : ""),
        bind: (f, box) => { bindAll(box, { "#pf-method": el => { f.method = el.value; }, "#pf-splane": el => { f.plane = el.value; }, "#pf-soff": el => { f.offset = numv(el.value) || 0; }, "#pf-srel": el => { f.relative = el.checked; } });
          bind3(box, "pf-pp", v => { f.point = v; }); bind3(box, "pf-pn", v => { f.normal = v; }); [1, 2, 3].forEach(i => bind3(box, "pf-p" + i, v => { f.points = f.points || [[0, 0, 0], [1, 0, 0], [0, 1, 0]]; f.points[i - 1] = v; })); },
        summary: f => SPLIT_METHODS[m],
        // a click picks the tool and sets the method: face (extended), plane, edge or curve (normal plane), sketch, surface
        kinds: ["face", "plane", "edge", "curve", "sketch", "surface", "point"], single: m !== "three_points", done: () => true,
        hint: m === "three_points" ? "Type the points, or click three vertices of the part or point features (point 1, 2, 3 in turn)."
          : "Choose the method, or click the tool: a face (its surface extended), a plane, an edge or curve (normal plane), a sketch, a surface body, or a vertex (plane through it, normal in Method).",
        accept: (f, h) => {
          if (h.kind === "point") { if (f.method === "three_points") fillThreePoints(f, h); else { f.method = "point_normal"; f.point = h.point.map(v => +(+v).toFixed(6)); } }
          else if (h.kind === "face") { if (f.method !== "ogrid") f.method = "face"; f.face = refOf(h); }
          else if (h.kind === "plane") { if (BASE_PLANES[h.id]) { f.method = "principal"; f.plane = h.id; } else { f.method = "datum"; f.plane_ref = h.id; } }
          else if (h.kind === "edge" || h.kind === "curve") { f.method = "edge"; if (h.kind === "edge") { f.edge = refOf(h); f.curve = null; } else { f.curve = h.id; f.edge = null; } }
          else if (h.kind === "sketch") { f.method = "sketch"; f.sketch_ref = h.id; }
          else if (h.kind === "surface") { f.method = "surface"; f.source = h.id; }
          PT.dirty = true;
        } }];
      if (m === "datum") steps.push({ key: "plane_ref", label: "Plane", kinds: ["plane"], prop: "plane_ref", single: true, before: false, hint: "Click a plane feature in the view or the tree.",
        accept: (f, h) => { if (BASE_PLANES[h.id]) { f.method = "principal"; f.plane = h.id; } else f.plane_ref = h.id; PT.dirty = true; },
        html: f => `<div class="grid2">` + select("pf-sdatum", "Plane", [["", "(none)"]].concat(planeItems(featIndex(f.id)).map(p => [p.id, p.name])), f.plane_ref || "") + num("pf-soff", "Offset (mm)", f.offset || 0) + `</div>`,
        bind: (f, box) => bindAll(box, { "#pf-sdatum": el => { f.plane_ref = el.value || null; }, "#pf-soff": el => { f.offset = numv(el.value) || 0; } }), done: f => !!f.plane_ref, summary: f => planeName(f.plane_ref) });
      if (m === "face") steps.push(Object.assign(facesStep("Face", "face", "Click the face: its surface (plane, cylinder, cone, ...) is extended through the cells.", true), { html: f => `<div class="grid2">` + num("pf-foff", "Offset from the face (mm, + outward)", f.face_offset || 0) + `<span></span></div>`, bind: (f, box) => bindAll(box, { "#pf-foff": el => { f.face_offset = numv(el.value) || 0; } }) }));
      if (m === "ogrid") steps.push(facesStep("Hole face", "face", "Click the cylindrical face of the hole: four planes through its axis partition the cells around it.", true));
      if (m === "sketch") steps.push(profileStep("sketch_ref", "Sketch"));
      if (m === "edge") steps.push({ key: "edge", label: "Edge or curve", kinds: ["edge", "curve"], single: true, hint: "Click an edge of the solid or a curve body; the plane is normal to it.",
        accept: (f, h) => { if (h.kind === "edge") { f.edge = refOf(h); f.curve = null; } else { f.curve = h.id; f.edge = null; } PT.dirty = true; },
        html: f => sourceSelect("pf-curve", f, "curve", false, true).replace("Curve<", "Or a curve body<") + `<div class="grid2">` + num("pf-st", "Position along the edge (0 to 1)", f.t === undefined ? 0.5 : f.t) + `<span></span></div>`,
        bind: (f, box) => bindAll(box, { "#pf-curve": el => { f.curve = el.value || null; if (el.value) f.edge = null; }, "#pf-st": el => { const t = numv(el.value); f.t = t >= 0 && t <= 1 ? t : 0.5; } }),
        done: f => !!(f.edge || f.curve), summary: f => f.curve ? itemName(f.curve) : f.edge ? "edge" : "none" });
      if (m === "surface") steps.push(sourceStep("Surface", "source", false, "Click the surface body that cuts the cells."));
      if (m !== "ogrid") steps.push(Object.assign(facesStep("Cells", "cells", "Click a face of each cell to partition; none: all cells."), { optional: true, summary: f => (f.cells || []).length ? (f.cells || []).length + " cell(s)" : "all cells" }));
      return steps;
    },
  },
  surf_sketch: {
    title: "Extruded surface",
    defaults: init => ({ sketch_ref: null, kind: (init && init.kind) || "extrude", depth: 20, symmetric: false, angle: 360, axis: "v" }),
    steps: f => {
      const sk = f.sketch_ref && feat(f.sketch_ref);
      const axes = (((sk || {}).sketch || {}).entities || []).filter(e => e.t === "line" && e.constr && !e.axis);
      return [profileStep(), { key: "extent", label: "Extent", html: f => select("pf-skind", "Type", [["extrude", "Curves extruded normal to the plane"], ["planar", "Planar face of the closed sketch"], ["revolve", "Curves revolved"]], f.kind || "extrude") +
          (f.kind === "extrude" || !f.kind ? `<div class="grid2">` + num("pf-sdepth", "Depth (mm, negative: against the normal)", f.depth || 20) + `<label class="check bottom"><input type="checkbox" id="pf-ssym"${f.symmetric ? " checked" : ""}> Symmetric to the plane</label></div>` : "") +
          (f.kind === "revolve" ? `<div class="grid2">` + num("pf-sang", "Angle (deg, negative: reversed)", f.angle || 360) + select("pf-saxis", "Axis", [["u", "Sketch x axis (u)"], ["v", "Sketch y axis (v)"]].concat(axes.map(e => [e.id, "Construction line " + e.id])), f.axis || "v") + `</div>` : "") + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-skind": el => { f.kind = el.value; }, "#pf-sdepth": el => { const v = numv(el.value); if (isFinite(v) && v !== 0) f.depth = v; }, "#pf-ssym": el => { f.symmetric = el.checked; }, "#pf-sang": el => { const v = numv(el.value); if (isFinite(v) && v !== 0 && Math.abs(v) <= 360) f.angle = v; }, "#pf-saxis": el => { f.axis = el.value; } }),
        summary: f => f.kind === "planar" ? "planar face" : f.kind === "revolve" ? pfmt(f.angle || 360) + " deg" : pfmt(f.depth || 20) + " mm" + (f.symmetric ? ", symmetric" : "") }];
    },
  },
  surf_trim: {
    title: "Trim surface",
    defaults: () => ({ source: null, with: "surface", tool: null, keep: "pick", remove: [] }),
    steps: f => [
      Object.assign(sourceStep("Target", "source", false, "Click the surface body to trim."), { kinds: ["surface"] }),
      { key: "tool", label: "Tool", kinds: ["surface", "curve", "sketch", "body", "plane"], single: true, before: false, hint: "Click the tool: a surface body, a curve body or a sketch (projected onto the target), the solid, or a plane.",
        accept: (f, h) => { if (h.id && h.id === f.source) { msgPart("The tool must differ from the target", true); return; }
          if (h.kind === "body") { f.with = "solid"; f.tool = null; } else if (h.kind === "plane") { f.with = "plane"; f.tool = h.id; } else { f.with = h.kind === "curve" ? "curve" : h.kind === "sketch" ? "sketch" : "surface"; f.tool = h.id; } f.remove = []; PT.cmd.regions = null; PT.dirty = true; },
        html: f => `<p class="hint">${f.with === "solid" ? "The solid." : f.with === "plane" ? "Plane " + planeName(f.tool) + "." : f.tool ? itemName(f.tool) + "." : "No tool yet."}</p>`,
        done: f => f.with === "solid" || !!f.tool, summary: f => f.with === "solid" ? "the solid" : f.with === "plane" ? planeName(f.tool) : f.tool ? itemName(f.tool) : "none" },
      { key: "regions", label: "Regions", kinds: ["region"], before: true, hint: "Click the regions to remove (click again to keep them). Invert swaps kept and removed.",
        enter: f => { if (f.source && (f.with === "solid" || f.tool)) loadRegions(f); },
        accept: (f, h) => { f.keep = "pick"; f.remove = f.remove || []; const i = f.remove.findIndex(p => p.join(",") === h.point.join(",")); if (i >= 0) f.remove.splice(i, 1); else f.remove.push(h.point); PT.dirty = true; drawRegions(); },
        html: f => { const n = (PT.cmd.regions || []).length; return `<p class="hint">${n ? n + " region(s), " + (f.remove || []).length + " removed." : "Computing the regions..."}</p><div class="buttons"><button type="button" id="pf-invert">Invert</button><button type="button" id="pf-keepall">Keep all</button></div>`; },
        bind: (f, box) => { const b = box.querySelector("#pf-invert"); if (b) b.onclick = () => { const all = (PT.cmd.regions || []).map(r => r.point); const rem = new Set((f.remove || []).map(p => p.join(","))); f.remove = all.filter(p => !rem.has(p.join(","))); f.keep = "pick"; changedPart(); };
          const k = box.querySelector("#pf-keepall"); if (k) k.onclick = () => { f.remove = []; changedPart(); }; },
        done: f => true, summary: f => (f.remove || []).length + " region(s) removed" },
    ],
  },
  surf_extend: {
    title: "Extend surface",
    defaults: () => ({ source: null, edges: [], mode: "edges", distance: 5, sides: "all", tolerance: 0.01 }),
    steps: f => {
      const steps = [surfaceOrFacesStep("Surface", "Click the surface body to extend, or a face of the solid.")];
      if (f.mode !== "all") steps.push({ key: "edges", label: "Edges", kinds: ["sedge", "edge"], prop: "edges", hint: "Click the boundary edges of the surface to extend (click again to deselect).",
        accept: (f, h) => { if ((f.faces || []).length ? !!h.surface : h.surface !== f.source) { msgPart("Click an edge of " + ((f.faces || []).length ? "the picked faces" : itemName(f.source)), true); return; } applyPick(f, { prop: "edges", kinds: ["edge"], single: false }, h); },
        html: f => `<p class="hint">${(f.edges || []).length} edge(s) selected.</p><div class="buttons"><button type="button" data-clear="edges">Clear</button></div>`,
        bind: (f, box) => box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.edges = []; changedPart(); }),
        summary: f => (f.edges || []).length + " edge(s)" });
      steps.push({ key: "extent", label: "Extent", html: f => { const sides = f.sides || "all"; const isList = Array.isArray(sides); const all = f.mode === "all";
        return `<div class="grid2">` + num("pf-edist", "Distance (mm)", f.distance || 5) + select("pf-emode", "Extend", [["edges", "Across the selected edges (trim kept)"], ["all", "Whole boundary: untrimmed patch"]], f.mode || "edges") + `</div>` +
          (all ? select("pf-esides", "Sides", [["all", "All four sides"], ["point", "The side nearest to a point"], ["list", "Chosen parameter sides"]], isList ? "list" : sides) +
            (sides === "point" ? v3("pf-ep", "Point (mm)", f.point || [0, 0, 0]) : "") + (isList ? ["umin", "umax", "vmin", "vmax"].map(k => `<label class="check inline"><input type="checkbox" data-side="${k}"${sides.includes(k) ? " checked" : ""}> ${k}</label>`).join("") : "") : "") +
          `<div class="grid2">` + num("pf-etol", "Fit tolerance (mm, splines)", f.tolerance || 0.01) + `<span></span></div>` + resultLine(f); },
        bind: (f, box) => { bindAll(box, { "#pf-edist": el => { const x = numv(el.value); if (x > 0) f.distance = x; }, "#pf-emode": el => { f.mode = el.value; }, "#pf-etol": el => { const x = numv(el.value); if (x > 0) f.tolerance = x; }, "#pf-esides": el => { f.sides = el.value === "list" ? ["umin", "umax", "vmin", "vmax"] : el.value; } });
          bind3(box, "pf-ep", v => { f.point = v; }); box.querySelectorAll("input[data-side]").forEach(cb => cb.onchange = () => { f.sides = [...box.querySelectorAll("input[data-side]:checked")].map(x => x.dataset.side); changedPart(); }); },
        summary: f => pfmt(f.distance || 5) + " mm" + (f.mode === "all" ? ", untrimmed patch" : "") });
      return steps;
    },
  },
  surf_offset: { title: "Offset surface", defaults: () => ({ source: null, faces: [], distance: 2 }),
    steps: f => [surfaceOrFacesStep("Surface", "Click a surface body or faces of the solid to offset."), { key: "distance", label: "Distance", html: f => `<div class="grid2">` + num("pf-odist", "Distance (mm, along the normals)", f.distance || 0) + `<span></span></div>` + resultLine(f), bind: (f, box) => bindAll(box, { "#pf-odist": el => { f.distance = numv(el.value) || 0; } }), summary: f => pfmt(f.distance || 0) + " mm" }] },
  thicken: { title: "Thicken", defaults: () => ({ source: null, faces: [], thickness: 1, side: "+", mode: "add" }),
    steps: f => [surfaceOrFacesStep("Surface", "Click a surface body or faces of the solid to thicken.", true), { key: "thickness", label: "Thickness", html: f => `<div class="grid2">` + num("pf-tth", "Thickness (mm)", f.thickness || 1) + select("pf-tside", "Side", [["+", "Along the normal"], ["-", "Against the normal"], ["both", "Both (half each)"]], f.side || "+") + `</div>` +
        select("pf-tmode", "Result", [["add", "Add to the part"], ["cut", "Remove from the part"], ["new", "New cell"]], f.mode || "add") + resultLine(f),
      bind: (f, box) => bindAll(box, { "#pf-tth": el => { const v = numv(el.value); if (v > 0) f.thickness = v; }, "#pf-tside": el => { f.side = el.value; }, "#pf-tmode": el => { f.mode = el.value; } }), summary: f => pfmt(f.thickness || 1) + " mm, " + (f.mode || "add") }] },
  curve_section: { title: "Intersection curve", defaults: () => ({ source: null, faces: [], other: null }),
    steps: f => [surfaceOrFacesStep("Surface", "Click a surface body or faces of the solid."), { key: "other", label: "With", kinds: ["surface", "body"], single: true, before: false, hint: "Click the second surface body, or the solid.",
      accept: (f, h) => { f.other = h.kind === "surface" ? h.id : null; PT.dirty = true; },
      html: f => sourceSelect("pf-other", f, "other", false, false).replace("Surface<", "With surface (none: the solid)<") + resultLine(f), bind: (f, box) => bindAll(box, { "#pf-other": el => { f.other = el.value || null; } }),
      done: f => true, summary: f => f.other ? itemName(f.other) : "the solid" }] },
  surf_extract: { title: "Extract surface", needsSolid: false, defaults: () => ({ faces: [], offset: 0 }),
    steps: f => [facesStep("Faces", "faces", "Click the faces to copy as a surface body: faces of the solid or of surface bodies.", false, true), { key: "offset", label: "Offset", html: f => `<div class="grid2">` + num("pf-xoff", "Offset along the normals (mm)", f.offset || 0) + `<span></span></div>` + resultLine(f), bind: (f, box) => bindAll(box, { "#pf-xoff": el => { f.offset = numv(el.value) || 0; } }), summary: f => pfmt(f.offset || 0) + " mm" }] },
  surf_bridge: { title: "Bridge surface", defaults: () => ({ edges_a: [], curves_a: [], edges_b: [], curves_b: [], flip: false }),
    steps: f => ["a", "b"].map(k => ({ key: "side_" + k, label: "Side " + k.toUpperCase(), kinds: ["edge", "sedge", "curve"], before: false,
        hint: `Click the edges of side ${k.toUpperCase()} (one connected chain): edges of the solid or of surface bodies, or curve bodies. Click again to deselect.`,
        accept(f, h) {
          if (h.kind === "curve") { const arr = f["curves_" + k] = f["curves_" + k] || []; const i = arr.indexOf(h.id); if (i >= 0) arr.splice(i, 1); else arr.push(h.id); PT.dirty = true; return; }
          if ((PT.cmd.emode || "edge") === "tangent" && !h.surface) { expandEdges(f, "edges_" + k, "tangent", [refOf(h)]); return; }
          applyPick(f, { prop: "edges_" + k, kinds: ["edge"], single: false }, h);
        },
        html: f => `<p class="hint">${(f["edges_" + k] || []).length} edge(s), ${(f["curves_" + k] || []).length} curve body(ies).</p><div class="buttons"><button type="button" data-clear="${k}">Clear</button></div>` +
          `<p class="hint" style="margin-bottom:2px">Curve bodies</p>` + sourceSelect("", f, "curves_" + k, true, true).replace(/data-src=/g, `data-src${k}=`),
        bind: (f, box) => {
          box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f["edges_" + k] = []; f["curves_" + k] = []; changedPart(); });
          box.querySelectorAll(`input[data-src${k}]`).forEach(cb => cb.onchange = () => { f["curves_" + k] = [...box.querySelectorAll(`input[data-src${k}]:checked`)].map(x => x.getAttribute("data-src" + k)); changedPart(); });
        },
        done: f => (f["edges_" + k] || []).length > 0 || (f["curves_" + k] || []).length > 0,
        summary: f => [(f["edges_" + k] || []).length ? (f["edges_" + k] || []).length + " edge(s)" : "", (f["curves_" + k] || []).length ? (f["curves_" + k] || []).length + " curve(s)" : ""].filter(Boolean).join(", ") || "none" }))
      .concat([{ key: "opts", label: "Options", html: f => check("pf-bflip", "Flip (join the ends of side A to the other ends of side B)", f.flip) +
          `<p class="hint">Straight lines join the ends of side A to the nearer ends of side B (corner to corner) and the points between; the result is a surface body. Sew surfaces joins it to the neighbouring surfaces.</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-bflip": el => { f.flip = el.checked; } }), summary: f => f.flip ? "flipped" : "corner to corner" }]) },
  surf_fill: { title: "Fill surface", defaults: () => ({ edges: [], tangent: true, curves: [], sketch_refs: [] }),
    steps: f => [{ key: "edges", label: "Boundary", kinds: ["edge", "sedge", "face", "sketch", "curve"], before: false,
        hint: "Click the edges of the closed loop: edges of the solid or of surface bodies, sketch curves (the whole sketch), curve bodies. Click again to deselect.",
        accept(f, h) {
          const toggle = (arr, id) => { const i = arr.indexOf(id); if (i >= 0) arr.splice(i, 1); else arr.push(id); };
          if (h.kind === "sketch") { f.sketch_refs = f.sketch_refs || []; toggle(f.sketch_refs, h.id); PT.dirty = true; return; }
          if (h.kind === "curve") { f.curves = f.curves || []; toggle(f.curves, h.id); PT.dirty = true; return; }
          if (h.kind === "face") { expandEdges(f, "edges", "faces", [refOf(h)]); return; }
          if ((PT.cmd.emode || "edge") === "tangent" && !h.surface) { expandEdges(f, "edges", "tangent", [refOf(h)]); return; }
          applyPick(f, { prop: "edges", kinds: ["edge"], single: false }, h);
        },
        html: f => edgeModeHtml(f) + `<p class="hint">${(f.edges || []).length} edge(s), ${(f.sketch_refs || []).length} sketch(es), ${(f.curves || []).length} curve body(ies) selected.</p><div class="buttons"><button type="button" data-clear="edges">Clear</button></div>` +
          `<p class="hint" style="margin-bottom:2px">Sketches</p>` + sketchItems(featIndex(f.id)).map(x => `<label class="check"><input type="checkbox" data-skr="${pesc(x.id)}"${(f.sketch_refs || []).includes(x.id) ? " checked" : ""}> ${pesc(x.name)}</label>`).join("") +
          `<p class="hint" style="margin-bottom:2px">Curve bodies</p>` + sourceSelect("", f, "curves", true, true),
        bind: (f, box) => { bindEdgeMode(box); box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.edges = []; f.sketch_refs = []; f.curves = []; changedPart(); });
          box.querySelectorAll("input[data-skr]").forEach(cb => cb.onchange = () => { f.sketch_refs = [...box.querySelectorAll("input[data-skr]:checked")].map(x => x.dataset.skr); changedPart(); });
          box.querySelectorAll("input[data-src]").forEach(cb => cb.onchange = () => { f.curves = [...box.querySelectorAll("input[data-src]:checked")].map(x => x.dataset.src); changedPart(); }); },
        done: f => (f.edges || []).length > 0 || (f.curves || []).length > 0 || (f.sketch_refs || []).length > 0,
        summary: f => [(f.edges || []).length ? (f.edges || []).length + " edge(s)" : "", (f.sketch_refs || []).length ? (f.sketch_refs || []).map(itemName).join(", ") : "", (f.curves || []).length ? (f.curves || []).length + " curve(s)" : ""].filter(Boolean).join(", ") || "none" },
      { key: "opts", label: "Options", html: f => check("pf-ftan", "Tangent to the adjacent faces", f.tangent !== false) + resultLine(f), bind: (f, box) => bindAll(box, { "#pf-ftan": el => { f.tangent = el.checked; } }), summary: f => f.tangent !== false ? "tangent" : "position only" }] },
  curve_extract: { title: "Extract curve", needsSolid: false, defaults: () => ({ edges: [], tangent_chain: false, clean: "none", tolerance: 0.05, project: "" }),
    steps: f => [Object.assign(edgesStep("Edges", "edges", "Click the edges of the curve: edges of the solid or of surface bodies."), { kinds: ["edge", "sedge", "face"] }), { key: "opts", label: "Clean", html: f => select("pf-cclean", "Clean", [["none", "None (edges as they are)"], ["smooth", "Join into one smooth spline within tolerance"], ["analytic", "Line or circular arc within tolerance, else smooth spline"]], f.clean || "none") +
        `<div class="grid2">` + num("pf-ctol", "Tolerance (mm)", f.tolerance || 0.05) + `<span></span></div>` + sourceSelect("pf-cproj", f, "project", false, false).replace("Surface<", "Project onto surface<") + resultLine(f),
      bind: (f, box) => bindAll(box, { "#pf-cclean": el => { f.clean = el.value; }, "#pf-ctol": el => { const v = numv(el.value); if (v > 0) f.tolerance = v; }, "#pf-cproj": el => { f.project = el.value; } }), summary: f => f.clean || "none" }] },
};

/** Legacy single-step commands: the parameter panel of the feature type (LEGACY_PANELS). */
function legacyCommand(type) {
  return { title: TYPE_NAMES[type], defaults: () => LEGACY_DEFAULTS[type] ? LEGACY_DEFAULTS[type]() : {},
    steps: f => [{ key: "params", label: "Parameters", html: f => `<div id="cmd-legacy"></div>`, bind: (f, box) => LEGACY_PANELS[type](f, box.querySelector("#cmd-legacy")), summary: f => "" }] };
}
function commandDef(type) { return COMMANDS[type] || legacyCommand(type); }
function commandSteps(f) { return commandDef(f.type).steps(f); }
function stepDone(f, st) { return st.done ? st.done(f) : (st.prop ? hasValue(f[st.prop]) : true); }
function canFinish(f) { return commandSteps(f).every(st => st.optional || stepDone(f, st)); }

/** References of all steps of a feature, for the highlight. */
function commandRefs(f) {
  const out = { faces: [], edges: [], surfaces: [], planes: [], sketches: [], datums: [], points: [] };
  const add = (v, kinds) => {
    if (v === null || v === undefined || v === "") return;
    if (isVertexRef(v)) { out.points.push(v); return; }
    if (Array.isArray(v)) { v.forEach(x => add(x, kinds)); return; }
    if (typeof v === "object") { if (v.c) out.faces.push(v); else if (v.mid) out.edges.push(v); return; }
    const t = feat(v);
    if (BASE_PLANES[v] || (t && t.type === "plane")) out.planes.push(v);
    else if (t && t.type === "sketch") out.sketches.push(v);
    else if (t && (t.type === "point" || t.type === "axis")) out.datums.push(v);
    else if (t && SURFACE_TYPES.has(t.type)) out.surfaces.push(v);
  };
  for (const st of commandSteps(f)) if (st.prop) add(f[st.prop]);
  if (f.type === "plane" || f.type === "split") { add(f.face); add(f.faces); add(f.edge); add(f.curve); add(f.plane_ref); add(f.sketch_ref); add(f.source); }
  if (f.type === "sweep") { add(f.path_ref); add(f.path_source); }
  if (f.type === "surf_trim") { add(f.source); if (f.with !== "solid") add(f.tool); }
  if (f.type === "sketch") { if (f.plane === "datum") add(f.plane_ref); else if (BASE_PLANES[f.plane]) add(f.plane); add(f.plane_edge); add(f.plane_curve); add(f.plane_face); add(f.plane_axis); add(f.plane_point); add(f.plane_origin_ref); add(f.plane_xdir_ref); }
  if (f.type === "point" || f.type === "axis" || f.type === "plane") { add(f.point_ref); add(f.axis_ref); add(f.points_ref); add(f.planes_ref); add(f.plane_ref); add(f.edge); add(f.curve); add(f.face); if (f.sketch_curve) add(f.sketch_curve.sketch); }
  if (f.type === "revolve" || f.type === "pattern") add(f.axis_ref);
  if (f.type === "sketch" && f.plane_origin) out.points.push(f.plane_origin);
  if (f.type === "place") { add(f.face1); add(f.face2); add(f.face3); }
  for (const k of ["faces", "edges", "source", "sources", "curves", "tool", "other", "project", "sketch_refs", "edges_a", "edges_b", "curves_a", "curves_b"]) if (!(f.type === "surf_trim" && k === "tool")) add(f[k]);
  return out;
}

// ------------------------------------------------------------------ measure

const MEAS_COL = 0x0ca678;
/** Measure mode on / off (Measure button, Esc). */
function setMeasure(on) {
  PT.measure = on ? { items: [], res: null } : null;
  $("#pt-measure-btn").classList.toggle("active", !!on);
  $("#pt-measure").hidden = !on;
  renderMeasure();
  drawSelection();
  msgPart(on ? "Measure: click a face, a reference plane, a plane feature or an axis feature, then a second one. Esc ends" : "Measuring ended");
}
function renderMeasure() {
  const m = PT.measure;
  if (!m) return;
  $("#pt-measure-body").innerHTML = measureHtml(m.res, m.res ? (m.items.length < 2 ? "Click a second item to measure between them." : "A click starts a new measurement.") : "Click a face, a reference plane, a plane feature or an axis feature.");
}
async function measureClick(h) {
  const m = PT.measure;
  let it = null;
  if (h.kind === "face" && !h.surface) it = { face: h.fi };
  else if (h.kind === "plane") it = BASE_PLANES[h.id] ? { base: h.id } : { plane: h.id };
  else if (h.kind === "axis") it = { axis: h.id };
  if (!it) { msgPart("Measure takes faces of the solid, planes and axes", true); return; }
  if (m.items.length >= 2) m.items = [];
  m.items.push(it);
  m.res = null;
  drawSelection();
  try {
    const r = await postJSON("/api/part/measure", { part: PT.part, items: m.items });
    const j = await r.json();
    if (PT.measure !== m) return;
    m.res = j;
    renderMeasure();
    drawSelection();
    const md = (j.rows.find(x => x[0] === "Minimum distance") || [])[1];
    msgPart(md ? "Minimum distance " + md : j.rows.length ? j.rows[0][0] + ": " + j.rows[0][1] : "");
  } catch (err) { showErr(err); }
}
/** Measured items (green) and the minimum distance line, in the selection overlay. */
function drawMeasure(paint) {
  const m = PT.measure, t = PT.three;
  if (!m) return;
  const faces = new Set(m.items.filter(x => x.face !== undefined).map(x => x.face));
  paint(faces, MEAS_COL, 0.55, 5);
  for (const x of m.items) { if (x.base) paintPlane(x.base, MEAS_COL); if (x.plane) paintPlane(x.plane, MEAS_COL); if (x.axis) paintDatum(x.axis, MEAS_COL); }
  if (m.res && m.res.points && m.items.length === 2) {
    const [a, b] = m.res.points;
    const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...a), new THREE.Vector3(...b)]);
    const ln = new THREE.Line(g, new THREE.LineBasicMaterial({ color: MEAS_COL, depthTest: false }));
    ln.renderOrder = 12;
    t.overlay.add(ln);
    for (const q of [a, b]) {
      const sp = new THREE.Mesh(new THREE.SphereGeometry(planeSize() * 0.015, 12, 8), new THREE.MeshBasicMaterial({ color: MEAS_COL, depthTest: false }));
      sp.position.set(...q);
      sp.renderOrder = 12;
      t.overlay.add(sp);
    }
  }
}

function startCommand(type, init, existingId) {
  if (PT.measure) setMeasure(false);
  if (PT.cmd) { if (canFinish(feat(PT.cmd.id))) finishCommand(true); else cancelCommand(); }
  const def = commandDef(type);
  let f;
  if (existingId) f = feat(existingId);
  else {
    if (def.needsSolid && !(PT.mesh && PT.mesh.vertices.length)) { msgPart(TYPE_NAMES[type] + ": the part has no solid yet", true); return; }
    f = Object.assign({ id: newId(), name: nextName(type), type, suppressed: false }, def.defaults(init));
    if (type === "surf_sketch" && f.kind === "revolve") f.name = "Revolved surface " + (PT.part.features.filter(x => x.type === "surf_sketch" && x.kind === "revolve").length + 1);
    if (type === "sketch" && !init) { const s = PT.sel && (BASE_PLANES[PT.sel] ? PT.sel : feat(PT.sel) && feat(PT.sel).type === "plane" ? PT.sel : null); if (s) { if (BASE_PLANES[s]) f.plane = s; else { f.plane = "datum"; f.plane_ref = s; } } }
    if (SKETCH_TYPES.has(type) || type === "surf_sketch") { const s = PT.sel && feat(PT.sel); if (s && s.type === "sketch") f.sketch_ref = s.id; }
    if (init && init.insertAt !== undefined) PT.part.features.splice(init.insertAt, 0, f); else PT.part.features.push(f);
  }
  PT.cmd = { id: f.id, step: 0, isNew: !existingId, snapshot: JSON.stringify(f), pick: null, regions: null, emode: "edge", resume: init && init.resume };
  // start at the first unfinished step
  const steps = commandSteps(f);
  let i = steps.findIndex(st => !st.optional && !stepDone(f, st));
  if (i < 0) i = def.startStep !== undefined ? def.startStep : existingId ? 0 : steps.length - 1;
  PT.cmd.step = i;
  if (steps[i].enter) steps[i].enter(f);
  PT.sel = f.id;
  PT.dirty = PT.dirty || !existingId;
  renderTree(); renderCommand(); renderConfigs();
  scheduleBuild();
}

function gotoStep(i) {
  const c = PT.cmd;
  if (!c) return;
  const f = feat(c.id);
  const steps = commandSteps(f);
  if (i < 0 || i >= steps.length) return;
  c.step = i; c.pick = null;
  if (steps[i].enter) steps[i].enter(f);
  renderCommand();
  scheduleBuild();
}
function nextStep() {
  const c = PT.cmd;
  const f = feat(c.id);
  const steps = commandSteps(f);
  if (c.step + 1 >= steps.length) { finishCommand(); return; }
  gotoStep(c.step + 1);
}
function afterStepChange(f, st) {
  if (st && st.single && stepDone(f, st)) nextStep();
}

function finishCommand(silent) {
  const c = PT.cmd;
  if (!c) return;
  const f = feat(c.id);
  if (!f) { PT.cmd = null; changedPart(); return; }
  if (!canFinish(f)) { if (!silent) msgPart("Complete the steps first", true); return; }
  const def = commandDef(f.type);
  const resume = c.resume, isNew = c.isNew;
  if (isNew) for (const sid of consumedSources(f)) PT.hidden[sid] = true;
  PT.cmd = null;
  PT.sel = f.id;
  if (def.finish) { def.finish(f, isNew, resume); return; }
  changedPart();
  if (resume) resumeCommand(resume);
}
function cancelCommand() {
  const c = PT.cmd;
  if (!c) return;
  const f = feat(c.id);
  if (f) {
    if (c.isNew) { PT.part.features.splice(featIndex(f.id), 1); PT.sel = null; }
    else Object.assign(f, JSON.parse(c.snapshot));
  }
  const resume = c.resume;
  PT.cmd = null;
  changedPart();
  if (resume) resumeCommand(resume);
}
function resumeCommand(r) {
  const f = feat(r.id);
  if (!f) return;
  startCommand(f.type, null, f.id);
  if (PT.cmd) { const steps = commandSteps(f); let i = steps.findIndex(st => !st.optional && !stepDone(f, st)); if (i < 0) i = Math.min(r.step + 1, steps.length - 1); gotoStep(i); }
}

/** A new sketch for a feature property: inserted before the feature, drawn, then the feature command resumes. */
function newSketchFor(f, prop) {
  const r = { id: f.id, step: PT.cmd ? PT.cmd.step : 0 };
  const item = Object.assign({ id: newId(), name: nextName("sketch"), type: "sketch", suppressed: false }, COMMANDS.sketch.defaults());
  PT.part.features.splice(featIndex(f.id), 0, item);
  f[prop] = item.id;
  PT.cmd = null;
  startCommand("sketch", { resume: r }, item.id);
  PT.cmd.isNew = true;
  renderTree(); renderCommand();
}

/** Regions of the profile sketch of a sketch feature, for picking which ones to extrude or cut. */
async function loadProfileRegions(f) {
  PT.cmd.regions = null; PT.cmd.regionMode = "select";
  try {
    const r = await postJSON("/api/part/profile_regions", { part: PT.part, index: featIndex(f.id) });
    const regs = await r.json();
    if (!PT.cmd || PT.cmd.id !== f.id) return;
    if (!r.ok) throw new Error(regs.error || "regions failed");
    PT.cmd.regions = regs;
    renderCommand();
    setMesh(PT.mesh);
  } catch (e) { msgPart("Regions: " + (e.message || e), true); }
}
/** Optional step: pick the regions of the sketch to use; none picked: every closed loop. */
function regionsStep() {
  return { key: "regions", label: "Regions", kinds: ["region"], before: true, optional: true,
    hint: "Click the regions of the sketch to use (click again to deselect). None picked: every closed loop.",
    enter: f => { if (f.sketch_ref) loadProfileRegions(f); },
    accept: (f, h) => { f.regions = f.regions || []; const k = (h.uv || []).join(","); const i = f.regions.findIndex(p => p.join(",") === k); if (i >= 0) f.regions.splice(i, 1); else f.regions.push(h.uv); PT.dirty = true; drawRegions(); },
    html: f => { const n = (PT.cmd.regions || []).length; return `<p class="hint">${PT.cmd.regions ? n + " region(s), " + (f.regions || []).length + " picked" + ((f.regions || []).length ? "." : ": every closed loop is used.") : "Computing the regions..."}</p><div class="buttons"><button type="button" id="pf-regall">All</button><button type="button" id="pf-regnone">None</button></div>`; },
    bind: (f, box) => { const a = box.querySelector("#pf-regall"); if (a) a.onclick = () => { f.regions = (PT.cmd.regions || []).map(r => r.uv); changedPart(); };
      const n = box.querySelector("#pf-regnone"); if (n) n.onclick = () => { f.regions = []; changedPart(); }; },
    done: f => true, summary: f => (f.regions || []).length ? (f.regions || []).length + " region(s)" : "all loops" };
}

async function loadRegions(f) {
  PT.cmd.regions = null; PT.cmd.regionMode = "remove";
  try {
    const r = await postJSON("/api/part/regions", { part: PT.part, index: featIndex(f.id) });
    const regs = await r.json();
    if (!PT.cmd || PT.cmd.id !== f.id) return;
    PT.cmd.regions = regs;
    if (!f.keep) f.keep = "pick";
    renderCommand();
    setMesh(PT.mesh);
  } catch (e) { msgPart("Regions: " + (e.message || e), true); }
}

/** The command bar in the properties panel. A render requested while a field of the bar has the focus (the
 *  user is typing) is deferred to the blur of that field; a nested render during the DOM replacement is skipped. */
function renderCommand(force) {
  const box = $("#pt-props");
  const c = PT.cmd;
  if (!c) { renderProps(); return; }
  if (PT.renderingCmd) return;
  const ae = document.activeElement;
  if (!force && ae && box.contains(ae) && ae.matches("input, select, textarea")) { PT.pendingRender = true; return; }
  PT.renderingCmd = true;
  try { renderCommandNow(box, c); } finally { PT.renderingCmd = false; }
}
function renderCommandNow(box, c) {
  const f = feat(c.id);
  if (!f) { PT.cmd = null; renderProps(); return; }
  const def = commandDef(f.type);
  const steps = commandSteps(f);
  if (c.step >= steps.length) c.step = steps.length - 1;
  const st = PT.status[f.id] || {};
  const title = f.type === "surf_sketch" && f.kind === "revolve" ? "Revolved surface" : def.title;
  let h = `<div class="cmd"><div class="cmd-head"><strong>${title}</strong>` + nameField(f) + `</div>`;
  steps.forEach((s, i) => {
    const done = stepDone(f, s);
    const active = i === c.step;
    h += `<div class="cmd-step${active ? " active" : ""}${done ? " done" : ""}" data-step="${i}"><span class="num">${done && !active ? "✓" : i + 1}</span><span class="lbl">${s.label}</span>` + (!active && s.summary ? `<span class="sum">${pesc(s.summary(f))}</span>` : "") + `</div>`;
    if (active) {
      h += `<div class="cmd-body">` + (s.hint ? `<p class="hint">${s.hint}</p>` : "") + (s.html ? s.html(f) : "") +
        `<div class="buttons">` + (i + 1 < steps.length ? `<button type="button" id="cmd-next" class="primary">Next</button>` : "") + `</div></div>`;
    }
  });
  if (st.error) h += `<p class="hint err">${pesc(st.error)}</p>`;
  else if (st.extent) h += `<p class="hint">${st.profiles} profile(s)${st.note ? "; " + pesc(st.note) : ""}</p>`;
  h += `<div class="cmd-foot"><button type="button" id="cmd-finish" class="primary"${canFinish(f) ? "" : " disabled"}>${def.finishLabel || "Finish"}</button><button type="button" id="cmd-cancel">Cancel</button></div></div>`;
  box.innerHTML = h;
  const nm = box.querySelector("#pf-name");
  if (nm) nm.onchange = () => { f.name = nm.value.trim() || f.name; PT.dirty = true; renderTree(); };
  box.querySelectorAll(".cmd-step").forEach(el => el.onclick = () => gotoStep(+el.dataset.step));
  const active = steps[c.step];
  if (active && active.bind) active.bind(f, box.querySelector(".cmd-body") || box);
  const nx = box.querySelector("#cmd-next"); if (nx) nx.onclick = nextStep;
  box.querySelector("#cmd-finish").onclick = () => finishCommand();
  box.querySelector("#cmd-cancel").onclick = cancelCommand;
  $("#pt-cmdbar").hidden = false;
  $("#pt-cmdtitle").textContent = title + ": " + f.name + " — " + (active ? active.label : "") + (active && active.hint ? ". " + active.hint : "");
}

// ------------------------------------------------------------------ legacy parameter panels (one-step commands)

function resultText(st) {
  if (st.error) return `<p class="hint err">${pesc(st.error)}</p>`;
  if (st.faces === undefined) return "";
  let t = `<p class="hint">Result: ${st.faces_before} → ${st.faces} faces, ${st.edges_before} → ${st.edges} edges`;
  if (st.note) t += `. ${pesc(st.note)}`;
  return t + "</p>";
}
/** Pick buttons of the legacy panels: a pick in the view into f[prop] with the given element kind. */
function pickButtons(f, kind, prop, single, title, label) {
  const active = PT.cmd && PT.cmd.pick && PT.cmd.pick.prop === prop;
  const n = single ? (f[prop] ? 1 : 0) : (f[prop] || []).length;
  return `<div class="buttons"><button type="button" data-pick="${prop}" class="${active ? "" : "primary"}">${active ? "Done picking" : label}</button>` +
    (single ? "" : `<button type="button" data-clear="${prop}">Clear</button>`) + `<span class="hint">${n} selected</span></div>`;
}
function bindPicks(f, box, defs) {
  // a click in the view feeds the first pick of the panel without pressing its pick button first
  if (PT.cmd && PT.cmd.id === f.id) PT.cmd.legacyDefs = defs;
  box.querySelectorAll("button[data-pick]").forEach(b => {
    const d = defs[b.dataset.pick];
    if (!d) return;
    b.onclick = () => {
      if (PT.cmd.pick && PT.cmd.pick.prop === b.dataset.pick) PT.cmd.pick = null;
      else PT.cmd.pick = { prop: b.dataset.pick, kinds: d.kinds || [d.kind], single: !!d.single, expand: d.kind === "edge" && !d.single ? true : undefined };
      renderCommand(); scheduleBuild();
    };
  });
  box.querySelectorAll("button[data-clear]").forEach(b => { if (defs[b.dataset.clear]) b.onclick = () => { f[b.dataset.clear] = []; changedPart(); }; });
}

const LEGACY_DEFAULTS = {
  pattern: () => ({ kind: "linear", features: [], count: 3, step: [20, 0, 0], count2: 1, step2: [0, 20, 0], row_offset: 0, axis: "Z", centre: [0, 0, 0], angle: 360 }),
  import: () => ({ path: "", part: null }),
  unify: () => ({ faces: true, edges: true, angle: 0 }),
  heal: () => ({ tolerance: 0, small_faces: 0 }),
  defeature: () => ({ faces: [], min_area: 0, all_small: false }),
  offset_faces: () => ({ faces: [], distance: 1, tangent: true }),
  move_faces: () => ({ faces: [], vector: [0, 0, 1], tangent: true }),
  place: () => ({ face1: null, plane1: "XY", flip1: false, face2: null, plane2: "XZ", flip2: false, face3: null, plane3: "YZ", flip3: false, rest: "keep", offset: [0, 0, 0] }),
  combine: () => ({ faces: [], min_area: 0 }),
  hole_mesh: () => ({ faces: [], factor: 2, n_circ: 3, n_rad: 4, bias: 2, n_thick: 4 }),
  smooth: () => ({ tolerance: 0.05, segments: 6, continuity: "C2" }),
  replace: () => ({ faces: [], method: "analytic", tolerance: 0.05, offset: 0, pad: 1, min_area: 0 }),
  surf_fit: () => ({ faces: [], method: "analytic", tolerance: 0.05, extend: 0.3, offset: 0 }),
  surf_loft: () => ({ sections: [{ plane: "XY", offset: 0, sketch: emptySketch() }, { plane: "XY", offset: 20, sketch: emptySketch() }], ruled: false, curves: [] }),
  surf_sew: () => ({ sources: [], tolerance: 0.001 }),
  surf_import: () => ({ path: "", label: "" }),
  surf_cut: () => ({ source: null, keep: "-" }),
  surf_from_curve: () => ({ source: null, kind: "extrude", direction: [0, 0, 1], depth: 10, symmetric: false, axis_point: [0, 0, 0], axis_dir: [0, 0, 1], angle: 360 }),
};

const LEGACY_PANELS = {
  pattern(f, box) {
    const i0 = featIndex(f.id);
    const cands = PT.part.features.filter((x, i) => i < i0 && SKETCH_TYPES.has(x.type));
    const selSet = new Set(f.features || []);
    box.innerHTML = select("pf-kind", "Kind", [["linear", "Linear"], ["circular", "Circular"]], f.kind || "linear") +
      `<p class="hint" style="margin-bottom:2px">Features to repeat</p>` +
      (cands.length ? cands.map(x => `<label class="check"><input type="checkbox" data-pf="${pesc(x.id)}"${selSet.has(x.id) ? " checked" : ""}> ${pesc(x.name)}</label>`).join("") : '<p class="hint">No sketch features above this one.</p>') +
      `<div class="grid2">` + num("pf-count", "Count", f.count || 2, 1) + `<span></span></div>` +
      (f.kind === "circular"
        ? `<div class="grid2">` + select("pf-pax", "Axis", [["X", "X"], ["Y", "Y"], ["Z", "Z"]].concat(axisItems(i0).map(a => ["ref:" + a.id, "Axis feature " + a.name])), f.axis_ref ? "ref:" + f.axis_ref : (f.axis || "Z")) + num("pf-pang", "Total angle (deg)", f.angle === undefined ? 360 : f.angle) + `</div>` + (f.axis_ref ? "" : v3("pf-c", "Axis point (mm)", f.centre || [0, 0, 0])) + `<p class="hint">360 deg spreads the instances evenly around the axis.</p>`
        : v3("pf-s", "Direction 1 step (mm)", f.step || [10, 0, 0]) + `<div class="grid2">` + num("pf-count2", "Count in direction 2", f.count2 || 1, 1) + num("pf-rowoff", "Row offset (mm, every second row along direction 1)", f.row_offset || 0) + `</div>` + ((f.count2 || 1) > 1 ? v3("pf-s2", "Direction 2 step (mm)", f.step2 || [0, 10, 0]) : ""));
    bindAll(box, { "#pf-kind": el => { f.kind = el.value; }, "#pf-count": el => { const c = parseInt(el.value); if (c >= 2) f.count = c; }, "#pf-pax": el => { if (el.value.startsWith("ref:")) f.axis_ref = el.value.slice(4); else { f.axis = el.value; f.axis_ref = null; } }, "#pf-pang": el => { const a = numv(el.value); if (a > 0 && a <= 360) f.angle = a; } });
    bind3(box, "pf-s", v => { f.step = v; }); bind3(box, "pf-s2", v => { f.step2 = v; }); bind3(box, "pf-c", v => { f.centre = v; });
    bindAll(box, { "#pf-count2": el => { const c = parseInt(el.value); if (c >= 1) f.count2 = c; }, "#pf-rowoff": el => { f.row_offset = numv(el.value) || 0; } });
    box.querySelectorAll("input[data-pf]").forEach(cb => cb.onchange = () => { f.features = [...box.querySelectorAll("input[data-pf]:checked")].map(x => x.dataset.pf); changedPart(); });
  },
  import(f, box) {
    box.innerHTML = `<label>STEP file path on this PC<span class="row"><input type="text" id="pf-path" value="${pesc(f.path || "")}" placeholder="C:\\...\\part.step"><button type="button" id="pf-browse" class="browse" title="Choose the file">…</button></span></label>` +
      `<label>Solid in the file<input type="text" id="pf-partidx" value="${f.part === null || f.part === undefined ? "" : pesc(f.part)}" placeholder="empty: all solids; or an index 0, 1, ..."></label>` + resultText(PT.status[f.id] || {}) +
      `<p class="hint">The imported solids are the base geometry; partitions, clean-up and the other features apply to them.</p>`;
    bindAll(box, { "#pf-path": el => { f.path = el.value.trim(); }, "#pf-partidx": el => { const v = el.value.trim(); f.part = v === "" ? null : v; } });
    box.querySelector("#pf-browse").onclick = async () => { try { const p = await window.browse("open", "step", "", "STEP file to import"); if (p) { f.path = p; changedPart(); } } catch (e) { showErr(e); } };
  },
  unify(f, box) {
    box.innerHTML = check("pf-uf", "Merge coplanar and co-cylindrical faces", f.faces !== false) + check("pf-ue", "Merge collinear and co-circular edges", f.edges !== false) +
      `<div class="grid2">` + num("pf-uang", "Angular tolerance (deg, 0: exact)", f.angle || 0) + `<span></span></div>` + resultText(PT.status[f.id] || {}) +
      `<p class="hint">Removes the face and edge splits left by imports and booleans (CAE: virtual topology, remove redundant entities).</p>`;
    bindAll(box, { "#pf-uf": el => { f.faces = el.checked; }, "#pf-ue": el => { f.edges = el.checked; }, "#pf-uang": el => { f.angle = numv(el.value) || 0; } });
  },
  heal(f, box) {
    box.innerHTML = `<div class="grid2">` + num("pf-htol", "Small edges below (mm, 0: off)", f.tolerance || 0) + num("pf-hsmall", "Small faces narrower than (mm, 0: off)", f.small_faces || 0) + `</div>` + resultText(PT.status[f.id] || {}) +
      `<p class="hint">Fixes the topology of imported geometry; drops edges shorter than the first value and removes spot and strip faces narrower than the second. A result that is invalid or changes the volume by more than 1 % is rejected.</p>`;
    bindAll(box, { "#pf-htol": el => { f.tolerance = numv(el.value) || 0; }, "#pf-hsmall": el => { f.small_faces = numv(el.value) || 0; } });
  },
  replace(f, box) {
    box.innerHTML = pickButtons(f, "face", "faces", false, "", "Pick faces") +
      select("pf-rmethod", "Clean surface", [["analytic", "Analytic (plane, cylinder, cone, sphere, torus) within tolerance, else smooth spline"], ["smooth", "Smooth spline within tolerance"], ["original", "Original surface (rebuild only)"], ["surface", "A surface body (one face)"]], f.method || "analytic") +
      (f.method === "surface" ? sourceSelect("pf-rsrc", f, "source", false, false) : "") +
      `<div class="grid2">` + num("pf-rtol", "Tolerance (mm)", f.tolerance || 0.05) + num("pf-roff", "Offset of the surface (mm, + outward)", f.offset || 0) + `</div>` +
      `<div class="grid2">` + num("pf-rpad", "Pad depth (mm)", f.pad || 1) + num("pf-rmin", "Also small faces below (mm^2)", f.min_area || "") + `</div>` + resultText(PT.status[f.id] || {}) +
      `<p class="hint">The surface of the largest picked face is cleaned (fitted) and offset. Within the footprint of the picked faces, material outside the clean surface is cut away and material up to the clean surface is added (CAE: replace faces).</p>`;
    bindAll(box, { "#pf-rmethod": el => { f.method = el.value; }, "#pf-rsrc": el => { f.source = el.value; }, "#pf-rtol": el => { const v = numv(el.value); if (v > 0) f.tolerance = v; }, "#pf-roff": el => { f.offset = numv(el.value) || 0; }, "#pf-rpad": el => { const v = numv(el.value); if (v > 0) f.pad = v; }, "#pf-rmin": el => { f.min_area = numv(el.value) || 0; } });
    bindPicks(f, box, { faces: { kind: "face", single: false } });
  },
  smooth(f, box) {
    box.innerHTML = `<div class="grid2">` + num("pf-stol", "Tolerance (mm)", f.tolerance || 0.05) + num("pf-sseg", "Max spline segments per surface", f.segments || 6) + `</div>` +
      select("pf-scont", "Continuity", [["C2", "C2 (smooth curvature)"], ["C1", "C1"]], f.continuity || "C2") + resultText(PT.status[f.id] || {}) +
      `<p class="hint">Re-approximates the B-spline surfaces and curves with degree-3 splines of few segments within the tolerance; analytic surfaces are kept. A result that is invalid or changes the volume by more than 1 % is rejected.</p>`;
    bindAll(box, { "#pf-stol": el => { const v = numv(el.value); if (v > 0) f.tolerance = v; }, "#pf-sseg": el => { const v = parseInt(el.value); if (v >= 1) f.segments = v; }, "#pf-scont": el => { f.continuity = el.value; } });
  },
  combine(f, box) {
    const st = PT.status[f.id] || {};
    box.innerHTML = pickButtons(f, "face", "faces", false, "", "Pick faces") + `<div class="grid2">` + num("pf-cminarea", "Combine every face below (mm^2) with its largest neighbour", f.min_area || "") + `<span></span></div>` +
      (st.combined ? `<p class="hint">${st.combined} picked face(s) found.</p>` : "") +
      `<p class="hint">Virtual topology for the mesh only: the picked faces are meshed as one surface. The geometry and the drawing are unchanged. Applies to free meshes; structured blocks need real faces.</p>`;
    bindAll(box, { "#pf-cminarea": el => { f.min_area = numv(el.value) || 0; } });
    bindPicks(f, box, { faces: { kind: "face", single: false } });
  },
  hole_mesh(f, box) {
    const st = PT.status[f.id] || {};
    box.innerHTML = pickButtons(f, "face", "faces", false, "", "Pick hole faces") +
      `<div class="grid2">` + num("pf-hmfac", "Square side / hole diameter", f.factor || 2) + num("pf-hmcirc", "Elements per 45 deg of the hole", f.n_circ || 3, 1) + `</div>` +
      `<div class="grid2">` + num("pf-hmrad", "Elements from the hole to the square", f.n_rad || 4, 1) + num("pf-hmbias", "Radial bias (largest / smallest element)", f.bias || 1) + `</div>` +
      `<div class="grid2">` + num("pf-hmthk", "Elements through the thickness", f.n_thick || 4, 1) + `<span></span></div>` + resultText(st) +
      `<p class="hint">One cylindrical face per hole; counterbores on the same axis are included. Hexahedra, structured in Export mesh uses the element counts above. Below a blind hole the cells are prisms (wedge elements on the axis).</p>`;
    const int1 = v => { const n = parseInt(v); return n >= 1 ? n : null; };
    bindAll(box, { "#pf-hmfac": el => { const v = numv(el.value); if (v > 1) f.factor = v; }, "#pf-hmcirc": el => { const n = int1(el.value); if (n) f.n_circ = n; },
      "#pf-hmrad": el => { const n = int1(el.value); if (n) f.n_rad = n; }, "#pf-hmbias": el => { const v = numv(el.value); if (v > 0) f.bias = v; },
      "#pf-hmthk": el => { const n = int1(el.value); if (n) f.n_thick = n; } });
    bindPicks(f, box, { faces: { kind: "face", single: false } });
  },
  offset_faces(f, box) {
    box.innerHTML = pickButtons(f, "face", "faces", false, "", "Pick faces") + `<div class="grid2">` + num("pf-odist", "Distance (mm, + adds material)", f.distance === undefined ? 1 : f.distance) + `<span></span></div>` +
      check("pf-otan", "Include faces connected through tangent edges", f.tangent !== false) + resultText(PT.status[f.id] || {}) +
      `<p class="hint">The picked faces move along their normals by the distance; the neighbouring faces are extended or trimmed to meet them (CAD: offset face, push/pull). A cylindrical hole face with a negative distance enlarges the hole. Where the offset algorithm fails, the material between each face and its offset is added or removed: neighbouring faces at a right angle are extended, others keep their position.</p>`;
    bindAll(box, { "#pf-odist": el => { f.distance = numv(el.value) || 0; }, "#pf-otan": el => { f.tangent = el.checked; } });
    bindPicks(f, box, { faces: { kind: "face", single: false } });
  },
  place(f, box) {
    const planes = [["XY", "XY (Top)"], ["XZ", "XZ (Front)"], ["YZ", "YZ (Right)"], ["X", "X axis (cylinder)"], ["Y", "Y axis (cylinder)"], ["Z", "Z axis (cylinder)"]];
    const row = i => `<p class="hint" style="margin:8px 0 2px"><b>Face ${i}</b>${i === 1 ? " (turned onto its plane)" : i === 2 ? " (turned about the first plane normal)" : " (moved only)"}</p>` +
      pickButtons(f, "face", "face" + i, true, "", "Pick face " + i) +
      `<div class="grid2">` + select("pf-pl" + i, "On plane / axis", planes, f["plane" + i] || planes[i - 1][0]) + `<span></span></div>` +
      check("pf-fl" + i, "Flip (plane: the part on the negative side; axis: axis direction reversed)", f["flip" + i]) +
      (f["face" + i] ? `<button type="button" class="small" data-clearface="${i}">Clear face ${i}</button>` : "");
    box.innerHTML = row(1) + row(2) + row(3) +
      select("pf-rest", "Directions without a face", [["keep", "Keep the position"], ["centre", "Bounding box centre to the plane"], ["min", "Bounding box minimum to the plane"]], f.rest || "keep") +
      v3("pf-poff", "Offset after placing (mm)", f.offset || [0, 0, 0]) + resultText(PT.status[f.id] || {}) +
      ((PT.status[f.id] || {}).note ? `<p class="hint">${pesc(PT.status[f.id].note)}</p>` : "") +
      `<p class="hint">Moves the whole part (solid and surface bodies) so that planar faces lie on the principal planes and cylindrical faces have their axis on a principal axis: face 1 is turned onto its target, face 2 is turned about the first target direction (plane normal or axis) onto its target, face 3 is only moved onto its target. A planar face lies on its plane with its outward normal against the plane normal, so the part is on the positive side (Flip: the negative side). A cylindrical face has its axis on the X, Y or Z axis, axis direction along the axis (Flip: reversed); a plane selected for a cylindrical face means the axis normal to that plane. A direction already set by an earlier face is not moved again (for example a hole on the X axis, then a face on XZ: the face gives the turn about X only). A click in the view picks the next empty face. While the command is open the view shows the part before Place; Finish shows the moved part. Features after Place use the moved part.</p>`;
    const b = {};
    for (const i of [1, 2, 3]) { b["#pf-pl" + i] = el => { f["plane" + i] = el.value; }; b["#pf-fl" + i] = el => { f["flip" + i] = el.checked; }; }
    b["#pf-rest"] = el => { f.rest = el.value; };
    bindAll(box, b);
    bind3(box, "pf-poff", v => { f.offset = v; });
    box.querySelectorAll("[data-clearface]").forEach(el => { el.onclick = () => { f["face" + el.dataset.clearface] = null; changedPart(); }; });
    bindPicks(f, box, { face1: { kind: "face", single: true }, face2: { kind: "face", single: true }, face3: { kind: "face", single: true } });
  },
  move_faces(f, box) {
    box.innerHTML = pickButtons(f, "face", "faces", false, "", "Pick faces") + v3("pf-mv", "Move vector (mm)", f.vector || [0, 0, 0]) +
      check("pf-mtan", "Include faces connected through tangent edges", f.tangent !== false) + resultText(PT.status[f.id] || {}) +
      `<p class="hint">Each face sweeps along the vector: the swept volume is added where the face points along the vector and removed where it points against it; faces parallel to the vector are extended or trimmed (push/pull). Faces moved across their own curvature (a hole moved sideways) are moved as a feature: pick all faces of the hole, boss or slot; the feature is removed (as Remove faces) and placed again at the moved position.</p>`;
    bind3(box, "pf-mv", v => { f.vector = v; });
    bindAll(box, { "#pf-mtan": el => { f.tangent = el.checked; } });
    bindPicks(f, box, { faces: { kind: "face", single: false } });
  },
  defeature(f, box) {
    box.innerHTML = pickButtons(f, "face", "faces", false, "", "Pick faces") + `<div class="grid2">` + num("pf-minarea", "Also small faces below (mm^2)", f.min_area || "") + `<span></span></div>` +
      check("pf-allsmall", "Every face below that area in the part (no pick needed)", f.all_small) + resultText(PT.status[f.id] || {}) +
      `<p class="hint">The picked faces are removed and the neighbouring faces are extended to close the gap; when they cannot be extended, the opening is closed with a smooth patch (CAE: remove faces, remove small faces).</p>`;
    bindAll(box, { "#pf-minarea": el => { f.min_area = numv(el.value) || 0; }, "#pf-allsmall": el => { f.all_small = el.checked; } });
    bindPicks(f, box, { faces: { kind: "face", single: false } });
  },
  surf_fit(f, box) {
    box.innerHTML = pickButtons(f, "face", "faces", false, "", "Pick faces") +
      select("pf-fmethod", "Surface type", [["analytic", "Analytic within tolerance, else smooth spline"], ["smooth", "Smooth spline"], ["original", "Original surface"]], f.method || "analytic") +
      `<div class="grid2">` + num("pf-ftol", "Tolerance (mm)", f.tolerance || 0.05) + num("pf-fext", "Extension beyond the face (fraction)", f.extend === undefined ? 0.3 : f.extend) + `</div>` +
      `<div class="grid2">` + num("pf-foff2", "Offset (mm, + outward)", f.offset || 0) + `<span></span></div>` + resultText(PT.status[f.id] || {}) +
      `<p class="hint">One clean surface fitted to the largest picked face and extended beyond it.</p>`;
    bindAll(box, { "#pf-fmethod": el => { f.method = el.value; }, "#pf-ftol": el => { const v = numv(el.value); if (v > 0) f.tolerance = v; }, "#pf-fext": el => { const v = numv(el.value); if (v >= 0) f.extend = v; }, "#pf-foff2": el => { f.offset = numv(el.value) || 0; } });
    bindPicks(f, box, { faces: { kind: "face", kinds: ["face", "sface"], single: false } });
  },
  surf_loft(f, box) {
    const secs = f.sections || [];
    box.innerHTML = secs.map((sc, i) => `<div class="grid2" data-sec="${i}">` + select("", "Section " + (i + 1) + " plane", Object.entries(BASE_PLANES), sc.plane || "XY").replace('id=""', 'data-k="plane"') +
        `<label>Offset (mm)<input type="text" inputmode="decimal" class="numf" data-k="offset" value="${sc.offset || 0}"></label>` +
        `<div class="buttons"><button type="button" data-edit="${i}">Edit sketch ${i + 1}</button><span class="hint">${((sc.sketch || {}).entities || []).filter(e => !e.constr).length} entities</span>` + (secs.length > 2 ? `<button type="button" data-del="${i}">×</button>` : "") + `</div></div>`).join("") +
      `<div class="buttons"><button type="button" id="pf-addsec">Add section</button></div>` + check("pf-ruled", "Ruled (straight between sections)", f.ruled) +
      `<div class="grid2"><label class="check bottom" title="Curves of a section that meet at less than the angle are joined into one smooth curve, so the loft is one smooth face instead of one face per segment"><input type="checkbox" id="pf-smooth"${f.smooth === false ? "" : " checked"}> Smooth sections</label>` +
      num("pf-smang", "Corner angle (deg)", f.smooth_angle || 15) + `</div>` +
      `<p class="hint" style="margin-bottom:2px">Or through curve bodies (in list order)</p>` + sourceSelect("", f, "curves", true, true) + resultText(PT.status[f.id] || {}) +
      `<p class="hint">One chain of curves per section; the sections are lofted in order. With curve bodies checked, the sketches are ignored.</p>`;
    bindAll(box, { "#pf-ruled": el => { f.ruled = el.checked; }, "#pf-smooth": el => { f.smooth = el.checked; },
                   "#pf-smang": el => { const v = numv(el.value); if (v > 0 && v < 180) f.smooth_angle = v; } });
    box.querySelectorAll("input[data-src]").forEach(cb => cb.onchange = () => { f.curves = [...box.querySelectorAll("input[data-src]:checked")].map(x => x.dataset.src); changedPart(); });
    box.querySelectorAll("[data-sec]").forEach(div => { const i = +div.dataset.sec; div.querySelectorAll("[data-k]").forEach(el => el.onchange = () => { secs[i][el.dataset.k] = el.dataset.k === "offset" ? (numv(el.value) || 0) : el.value; changedPart(); }); });
    box.querySelectorAll("button[data-edit]").forEach(b => b.onclick = () => editSketch(f.id, false, +b.dataset.edit));
    box.querySelectorAll("button[data-del]").forEach(b => b.onclick = () => { secs.splice(+b.dataset.del, 1); changedPart(); });
    box.querySelector("#pf-addsec").onclick = () => { const last = secs.at(-1); secs.push({ plane: last.plane, offset: (+last.offset || 0) + 20, sketch: emptySketch() }); changedPart(); };
  },
  surf_from_curve(f, box) {
    box.innerHTML = sourceSelect("pf-src", f, "source", false, true) + select("pf-fkind", "Kind", [["extrude", "Extruded along a direction"], ["revolve", "Revolved about an axis"]], f.kind || "extrude") +
      (f.kind === "revolve" ? v3("pf-ap", "Axis point (mm)", f.axis_point || [0, 0, 0]) + v3("pf-ad", "Axis direction", f.axis_dir || [0, 0, 1]) + `<div class="grid2">` + num("pf-fang", "Angle (deg)", f.angle || 360) + `<span></span></div>`
        : v3("pf-dd", "Direction", f.direction || [0, 0, 1]) + `<div class="grid2">` + num("pf-fdep", "Length (mm)", f.depth || 10) + `<label class="check bottom"><input type="checkbox" id="pf-fsym"${f.symmetric ? " checked" : ""}> Symmetric</label></div>`) + resultText(PT.status[f.id] || {});
    bindAll(box, { "#pf-src": el => { f.source = el.value; }, "#pf-fkind": el => { f.kind = el.value; }, "#pf-fdep": el => { const x = numv(el.value); if (x > 0) f.depth = x; }, "#pf-fsym": el => { f.symmetric = el.checked; }, "#pf-fang": el => { const x = numv(el.value); if (x > 0 && x <= 360) f.angle = x; } });
    bind3(box, "pf-dd", v => { f.direction = v; }); bind3(box, "pf-ap", v => { f.axis_point = v; }); bind3(box, "pf-ad", v => { f.axis_dir = v; });
  },
  surf_sew(f, box) {
    box.innerHTML = `<p class="hint" style="margin-bottom:2px">Surfaces</p>` + sourceSelect("", f, "sources", true, false) + `<div class="grid2">` + num("pf-stol2", "Tolerance (mm)", f.tolerance || 0.001) + `<span></span></div>` + resultText(PT.status[f.id] || {});
    bindAll(box, { "#pf-stol2": el => { f.tolerance = numv(el.value) || 0.001; } });
    box.querySelectorAll("input[data-src]").forEach(cb => cb.onchange = () => { f.sources = [...box.querySelectorAll("input[data-src]:checked")].map(x => x.dataset.src); changedPart(); });
  },
  surf_import(f, box) {
    box.innerHTML = `<label>STEP file path on this PC<span class="row"><input type="text" id="pf-spath" value="${pesc(f.path || "")}" placeholder="C:\\...\\deck.step"><button type="button" id="pf-sbrowse" class="browse" title="Choose the file">…</button></span></label>` +
      `<label>Component<input type="text" id="pf-slabel" value="${pesc(f.label || "")}" placeholder="empty: all faces of the file"></label>` + resultText(PT.status[f.id] || {}) +
      `<p class="hint">The faces of the component (STEP label) become one surface body.</p>`;
    bindAll(box, { "#pf-spath": el => { f.path = el.value.trim(); }, "#pf-slabel": el => { f.label = el.value.trim(); } });
    box.querySelector("#pf-sbrowse").onclick = async () => { try { const p = await window.browse("open", "step", "", "STEP file to import"); if (p) { f.path = p; changedPart(); } } catch (e) { showErr(e); } };
  },
  surf_cut(f, box) {
    box.innerHTML = sourceSelect("pf-src", f, "source", false, false) + select("pf-keep", "Keep", [["-", "The side against the surface normal"], ["+", "The side along the surface normal"]], f.keep || "-") + resultText(PT.status[f.id] || {}) +
      `<p class="hint">The solid is split by the surface and the cells on one side are kept. The surface must pass through the solid completely.</p>`;
    bindAll(box, { "#pf-src": el => { f.source = el.value; }, "#pf-keep": el => { f.keep = el.value; } });
  },
};

// ------------------------------------------------------------------ sketch editing

/** Opens the sketch editor for a sketch item (or a loft section). isNew: a new item, removed again when left empty. */
async function editSketch(id, isNew, section, resume) {
  const f = feat(id);
  if (!f) return;
  const sec = section !== undefined ? (f.sections || [])[section] : null;
  if (!sec && f.type !== "sketch") { if (f.sketch_ref) editSketch(f.sketch_ref); return; }
  let refs = [];
  try {
    const r = await postJSON("/api/part/refs", { part: PT.part, index: featIndex(id), path: false, section: section === undefined ? null : section });
    refs = await r.json();
  } catch (e) { /* reference geometry is optional */ }
  const title = sec ? `${f.name}: section ${section + 1} on ${planeName(sec.plane || "XY")}, offset ${pfmt(+sec.offset || 0)} mm` : `${f.name} on ${planeSummary(f)}`;
  if (PT.cmd && PT.cmd.id === id) { resume = resume || PT.cmd.resume; PT.cmd = null; }
  sketchEditForPart(sec ? sec.sketch : f.sketch, refs, title, sk => {
    if (sk) { if (sec) sec.sketch = sk; else f.sketch = sk; PT.dirty = true; }
    else if (isNew && !sec && !(f.sketch.entities || []).length) {
      PT.part.features.splice(featIndex(id), 1);
      for (const x of PT.part.features) { if (x.sketch_ref === id) x.sketch_ref = null; if (x.path_ref === id) x.path_ref = null; }
      if (PT.sel === id) PT.sel = null;
    }
    changedPart();
    if (resume) resumeCommand(resume);
    setTimeout(resize3, 0);
  });
}

// ------------------------------------------------------------------ configurations
// part.configs = {name: {"<item id>/<dim id>": value}}, part.active = name

function drivingDims() {
  const out = [];
  for (const f of PT.part.features) {
    if (f.type === "sketch") for (const d of (f.sketch || {}).dims || []) { if (d.driving) out.push({ key: f.id + "/" + d.id, f, which: "sketch", d }); }
    if (f.type === "extrude" || f.type === "cut") out.push({ key: f.id + "/depth", f, prop: "depth", label: "depth" });
    if (f.type === "revolve") out.push({ key: f.id + "/angle", f, prop: "angle", label: "angle" });
    if (f.type === "fillet" || f.type === "chamfer") out.push({ key: f.id + "/value", f, prop: "value", label: f.type === "fillet" ? "radius" : "distance" });
    if (f.type === "shell") out.push({ key: f.id + "/thickness", f, prop: "thickness", label: "thickness" });
    if (f.type === "hole") out.push({ key: f.id + "/dia", f, prop: "dia", label: "diameter" });
    if (f.type === "pattern") { out.push({ key: f.id + "/count", f, prop: "count", label: "count" }); if ((f.count2 || 1) > 1) out.push({ key: f.id + "/count2", f, prop: "count2", label: "count 2" }); if (f.row_offset) out.push({ key: f.id + "/row_offset", f, prop: "row_offset", label: "row offset" }); }
    if (f.type === "plane" || f.type === "sketch" || f.type === "mirror") { if (f.offset) out.push({ key: f.id + "/offset", f, prop: "offset", label: "offset" }); }
  }
  return out;
}
function dimName(row) {
  if (row.prop) return row.f.name + " " + row.label;
  const d = row.d;
  const t = { linear: "L", diameter: "Ø", radius: "R", angle: "∠" }[d.type] || d.type;
  return row.f.name + " " + (d.name || t + " " + d.id);
}
function currentValue(row) { return row.prop ? row.f[row.prop] : row.d.value; }

function renderConfigs() {
  const box = $("#pt-configs");
  if (!box) return;
  const p = PT.part;
  p.configs = p.configs || {};
  const names = Object.keys(p.configs);
  const rows = drivingDims();
  let h = `<div class="row"><select id="pc-sel" style="width:auto">${names.length ? names.map(n => `<option${n === p.active ? " selected" : ""}>${pesc(n)}</option>`).join("") : '<option value="">(none)</option>'}</select>` +
    `<button type="button" id="pc-add" class="small" style="margin-left:0">Add</button><button type="button" id="pc-ren" class="small" style="margin-left:0">Rename</button><button type="button" id="pc-del" class="small" style="margin-left:0">Delete</button></div>`;
  if (!rows.length) h += '<p class="hint">Driving dimensions and feature values appear here.</p>';
  else {
    h += `<table class="pc-table"><tr><th>Dimension</th><th>Name</th><th>Value</th></tr>` + rows.map(r =>
      `<tr><td title="${pesc(r.key)}">${pesc(dimName(r))}</td>` +
      `<td>${r.prop ? "" : `<input type="text" data-name="${pesc(r.key)}" value="${pesc(r.d.name || "")}" placeholder="name">`}</td>` +
      `<td><input type="text" inputmode="decimal" class="numf" data-val="${pesc(r.key)}" value="${pfmt(currentValue(r), 6)}"></td></tr>`).join("") + "</table>" +
      `<p class="hint">Values belong to the active configuration${p.active ? " <strong>" + pesc(p.active) + "</strong>" : ""}. Switching the configuration applies its values and rebuilds the part.</p>`;
  }
  box.innerHTML = h;
  $("#pc-sel").onchange = () => applyConfig($("#pc-sel").value);
  $("#pc-add").onclick = async () => {
    const name = await askValue("Configuration name", "", true);
    if (!name) return;
    p.configs[name] = {}; for (const r of rows) p.configs[name][r.key] = currentValue(r);
    p.active = name; PT.dirty = true; renderConfigs();
  };
  $("#pc-ren").onclick = async () => {
    if (!p.active) return;
    const name = await askValue("New name", p.active, true);
    if (!name || name === p.active) return;
    p.configs[name] = p.configs[p.active]; delete p.configs[p.active]; p.active = name; PT.dirty = true; renderConfigs();
  };
  $("#pc-del").onclick = () => {
    if (!p.active || !confirm("Delete configuration " + p.active + "?")) return;
    delete p.configs[p.active]; p.active = Object.keys(p.configs)[0] || null; PT.dirty = true; renderConfigs();
  };
  box.querySelectorAll("input[data-name]").forEach(inp => inp.onchange = () => { const r = rows.find(x => x.key === inp.dataset.name); if (r) { r.d.name = inp.value.trim(); PT.dirty = true; } });
  box.querySelectorAll("input[data-val]").forEach(inp => inp.onchange = () => {
    const v = numv(inp.value);
    if (!isFinite(v)) return;
    const r = rows.find(x => x.key === inp.dataset.val);
    if (!r) return;
    if (p.active) p.configs[p.active][r.key] = v;
    setDimValue(r, v);
  });
}
function setDimValue(r, v) {
  if (r.prop) {
    if (r.prop === "count") { if (v >= 2) r.f.count = Math.round(v); }
    else if (r.prop === "offset") r.f.offset = v;
    else if (v > 0) r.f[r.prop] = v;
    changedPart();
    return;
  }
  const res = applyDimValues(r.f.sketch, { [r.d.id]: v });
  if (!res.ok) msgPart(dimName(r) + " = " + pfmt(v, 4) + ": the sketch could not be solved; value kept but geometry unchanged", true);
  else r.f.sketch = res.sketch;
  changedPart();
}
function applyConfig(name) {
  const p = PT.part;
  if (!name || !p.configs[name]) return;
  p.active = name;
  const vals = p.configs[name];
  const fails = [];
  for (const f of p.features) {
    if (f.type === "sketch" && ((f.sketch || {}).dims || []).some(d => d.driving)) {
      const sub = {};
      for (const d of f.sketch.dims) if (d.driving && (f.id + "/" + d.id) in vals) sub[d.id] = vals[f.id + "/" + d.id];
      if (Object.keys(sub).length) { const res = applyDimValues(f.sketch, sub); f.sketch = res.sketch; if (!res.ok) fails.push(f.name); }
    }
    for (const prop of ["depth", "angle", "value", "thickness", "dia", "count", "offset"]) {
      const k = f.id + "/" + prop;
      if (k in vals && isFinite(+vals[k])) f[prop] = prop === "count" ? Math.round(+vals[k]) : +vals[k];
    }
  }
  if (fails.length) msgPart("Configuration " + name + ": sketch not solvable in " + fails.join(", "), true);
  else msgPart("Configuration " + name + " applied");
  changedPart();
}

// ------------------------------------------------------------------ files

let FM = null;                                              // File menu (docFileMenu in app.js)
function refreshList() { if (FM) return FM.refresh(); }

function loadPart(p) {
  if (!p.next) p.next = (p.features || []).reduce((m, f) => Math.max(m, parseInt(String(f.id).slice(1)) || 0), 0) + 1;
  p.version = 2;
  if (!p.uid) { p.uid = newUid(); p.legacy_ann = true; }      // uid identifies the part's drawing annotations; legacy_ann: annotations stored by name are taken over
  PT.part = p; PT.undo = []; PT.redo = [];
  PT.sel = null;
  PT.cmd = null;
  PT.status = {};
  PT.hidden = {};
  if (Array.isArray(p.hidden)) for (const id of p.hidden) PT.hidden[id] = true;
  else for (const f of p.features || []) for (const sid of consumedSources(f)) PT.hidden[sid] = true;
  PT.dirty = false;
  if (PT.three) PT.three.zoomed = false;
  if (FM) FM.render();
  $("#pt-cmdbar").hidden = true;
  renderTree();
  renderProps();
  renderConfigs();
  build();
}

/** Surface bodies a feature replaces (trim, extend, sew, offset, thicken): hidden when the feature is created. */
function consumedSources(f) {
  if (!f || f.suppressed) return [];
  if (f.type === "surf_trim" || f.type === "surf_extend" || f.type === "thicken") return f.source ? [f.source] : [];
  if (f.type === "surf_sew") return f.sources || [];
  return [];
}

/** Writes the part as <name>.part.json. asNew: a new document (Save as): new uid, so its drawing is separate. */
async function savePart(name, asNew) {
  if (asNew && PT.part.name !== name) { PT.part.uid = newUid(); delete PT.part.legacy_ann; }
  PT.part.name = name;
  PT.part.hidden = Object.keys(PT.hidden).filter(k => PT.hidden[k]);
  const r = await api("/api/part/file/" + encodeURIComponent(name), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(PT.part) });
  const j = await r.json();
  PT.dirty = false;
  status("Saved " + j.path);
}

async function exportStep(overwrite) {
  busy(true, "Exporting STEP...");
  try {
    const r = await fetch("/api/part/export", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ part: PT.part, folder: $("#pt-folder").value.trim(), overwrite: !!overwrite }) });
    if (r.status === 409) {
      const j = await r.json();
      busy(false);
      if (confirm("Overwrite " + j.exists + "?")) return exportStep(true);
      busy(true); status("Export cancelled"); return;
    }
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || r.statusText); }
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("json")) { const j = await r.json(); status("Wrote " + j.written.join(", ")); return; }
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = PT.part.name.replace(/[^A-Za-z0-9_\-.]+/g, "_") + ".step";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    status("Downloaded " + a.download);
  } catch (e) { showErr(e); }
  finally { busy(false); }
}

async function makeDrawing() {
  busy(true, "Adding the part to Models...");
  try {
    const r = await postJSON("/api/part/to_drawings", { part: PT.part });
    const res = await r.json();
    const fid = res.files[0].file_id;
    state.files = state.files.filter(f => f.file_id !== fid);
    addFiles(res);
    state.files.forEach(f => { if (f.file_id !== fid) f.parts.forEach(p => p.checked = false); });
    renderFiles();
  } catch (e) { showErr(e); busy(false); return; }
  busy(false);
  showTab("annotate");
  preview(false);
}

// ------------------------------------------------------------------ init

/** Project tab: load a saved part by name; refresh the saved list. */
window.__partLoadNamed = async function (name) {
  const r = await api("/api/part/file/" + encodeURIComponent(name));
  loadPart(await r.json());
  if (FM) FM.markSaved(name);
};
window.__partSetName = name => { if (PT.part) { PT.part.name = name; if (FM) FM.markSaved(name); } };
window.__partRefresh = refreshList;
/** Assembly tab: a new (unsaved) part whose base geometry is one solid of a STEP file (Import STEP feature). */
window.__partNewFromStep = function (name, path, index) {
  const p = blankPart(name);
  p.features.push({ id: "f" + (p.next++), name: "Import STEP 1", type: "import", suppressed: false, path, part: index === undefined ? null : index });
  loadPart(p);
  if (FM) FM.markUnsaved();
};
window.__partCurrent = () => (PT.part ? { name: PT.part.name, dirty: !!PT.dirty } : null);

window.partShown = function () {
  if (!PT.three) initThree();
  if (!PT.part) loadPart(blankPart("part"));
  refreshList();
  setTimeout(resize3, 0);
};

(function bindPart() {
  document.querySelectorAll("#tab-part [data-add]").forEach(b => b.onclick = () => startCommand(b.dataset.add, b.dataset.init ? JSON.parse(b.dataset.init) : null));
  document.querySelectorAll("#tab-part [data-view]").forEach(b => b.onclick = () => view(b.dataset.view));
  $("#pt-measure-btn").onclick = () => setMeasure(!PT.measure);
  $("#pt-measure-close").onclick = () => setMeasure(false);
  if ($("#pt-inspect")) $("#pt-inspect").onclick = () => inspectBody(PT.sel && PT.surfaces[PT.sel] ? PT.sel : null);
  $("#pt-edges").onchange = () => setMesh(PT.mesh);
  if ($("#pt-sectionchk")) $("#pt-sectionchk").onchange = () => setSection($("#pt-sectionchk").checked);
  $("#pt-planes").onchange = () => setMesh(PT.mesh);
  $("#pt-axes").onchange = () => setMesh(PT.mesh);
  $("#pt-showsketch").onchange = () => setMesh(PT.mesh);
  $("#pt-cmdfinish").onclick = () => finishCommand();
  $("#pt-props").addEventListener("focusout", () => setTimeout(() => { const box = $("#pt-props"); if (PT.pendingRender && !(document.activeElement && box.contains(document.activeElement))) { PT.pendingRender = false; if (PT.cmd) renderCommand(); } }, 0));
  $("#pt-cmdcancel").onclick = cancelCommand;
  FM = docFileMenu({ pre: "pt", type: "part", label: "part", pane: "#tab-part", listUrl: "/api/part/list",
    cur: () => (PT.part ? { name: PT.part.name, dirty: !!PT.dirty } : null),
    load: async name => loadPart(await (await api("/api/part/file/" + encodeURIComponent(name))).json()),
    save: savePart, blank: () => loadPart(blankPart("part")), setName: name => { PT.part.name = name; } });
  $("#pt-step").onclick = () => exportStep(false);
  $("#pt-mesh").onclick = () => { window.exportMesh(() => ({ part: PT.part }), $("#pt-folder").value.trim(), PT.part.name, window.partMeshPreview); };
  $("#pt-draw").onclick = makeDrawing;
  // side panel toggle (button and Ctrl+B) for every tab with a panel-toggle button
  document.querySelectorAll(".panel-toggle").forEach(b => b.onclick = () => togglePanel(b.dataset.panel));
  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b" && !e.target.matches("input, select, textarea")) {
      const pane = [...document.querySelectorAll(".tabpane")].find(t => !t.hidden);
      const props = pane && pane.querySelector(".ann-props");
      if (props) { e.preventDefault(); props.classList.toggle("collapsed"); window.dispatchEvent(new Event("resize")); }
    }
  });
  document.addEventListener("keydown", e => {
    if ($("#tab-part").hidden || !$("#tab-sketch").hidden || e.target.matches("input, select, textarea")) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "e") { e.preventDefault(); if (PT.cmd) finishCommand(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); undoPart(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") { e.preventDefault(); redoPart(); return; }
    if (e.key === "Delete" && !PT.cmd && PT.sel && feat(PT.sel)) { e.preventDefault(); deleteFeature(PT.sel); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === " " || e.code === "Space") { e.preventDefault(); toggleVisible(); return; }
    if (e.key === "Escape" && PT.measure && !PT.cmd) { setMeasure(false); return; }
    if (!PT.cmd) {
      const ni = nextIndexOf(e);
      if (ni >= 0 && PT.part) { const items = nextCommands(); const it = items[ni]; if (it) { e.preventDefault(); runNext(it); } }
      return;
    }
    if (e.key === "Escape") cancelCommand();
    if (e.key === "Enter") finishCommand();
  });
  window.addEventListener("beforeunload", e => { if (PT.dirty) { e.preventDefault(); e.returnValue = ""; } });
})();
// exposed for tests
window.__part = { PT, feat, THREE, viewXdir, setMeasure, measureClick, startCommand, finishCommand, cancelCommand, gotoStep, selectItem, pickAt, commandSteps, changedPart, viewDir, hoverText };

// ------------------------------------------------------------------ mesh preview

window.partMeshPreview = function (res) {
  const t = PT.three;
  if (!t) return;
  clearMeshPreview();
  if (!res || !res.preview || !res.preview.length) return;
  const pos = [];
  for (const [a, b] of res.preview) pos.push(...a, ...b);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  const lines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x0b5cad }));
  lines.name = "meshpreview";
  lines.renderOrder = 3;
  t.scene.add(lines);
  PT.meshPreview = lines;
  for (const o of PT.faceObjs) { o.material.opacity = 0.35; o.material.transparent = true; }
  render3();
  $("#pt-meshinfo").hidden = false;
  const q = res.quality || {};
  let cells = "";
  if ((res.cells || []).length > 8) {
    const by = {};
    for (const c of res.cells) by[c.technique] = (by[c.technique] || 0) + 1;
    cells = Object.entries(by).map(([k, v]) => `${v} cell(s) ${k}`).join(", ");
    const free = res.cells.filter(c => !c.technique.startsWith("structured") && !c.technique.startsWith("subdivision")).map(c => c.cell);
    if (free.length) cells += `; not structured: cells ${free.join(", ")}`;
  } else cells = (res.cells || []).map(c => `cell ${c.cell}: ${c.elements} elements, ${c.technique}`).join("<br>");
  $("#pt-meshinfo").innerHTML = `<strong>Mesh preview</strong> <button type="button" id="pt-meshclear">Hide</button><br>` +
    `${res.nodes} nodes, ${res.elements} elements: ${(res.types || []).join("; ")}<br>` +
    `Blocks (structured cells): ${res.blocks} of ${res.solids}` + (res.compounds || res.compounds_skipped ? `; combined face groups: ${res.compounds}` + (res.compounds_skipped ? ` (${res.compounds_skipped} skipped: an inner edge also bounds a face outside the group)` : "") : "") + `<br>` +
    (q.sicn_min !== undefined ? `Quality SICN min ${q.sicn_min}, mean ${q.sicn_mean}; ${q.sicn_below_0_2} element(s) below 0.2, ${q.inverted} inverted` + (q.gamma_min !== undefined ? `; gamma min ${q.gamma_min}, mean ${q.gamma_mean}` : "") + `<br>` : "") +
    `<span class="hint">${cells}</span>`;
  $("#pt-meshclear").onclick = clearMeshPreview;
};

function clearMeshPreview() {
  const t = PT.three;
  if (PT.meshPreview) { t.scene.remove(PT.meshPreview); PT.meshPreview = null; }
  for (const o of PT.faceObjs) { o.material.opacity = 1; o.material.transparent = false; }
  if ($("#pt-meshinfo")) $("#pt-meshinfo").hidden = true;
  if (t) render3();
}
