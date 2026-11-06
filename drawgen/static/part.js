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
                     import: "Import geometry", body_delete: "Delete body", body_copy: "Copy body", body_scale: "Scale body", place: "Place", split: "Partition", unify: "Merge faces", heal: "Heal", defeature: "Remove faces", offset_faces: "Offset faces", move_faces: "Move faces", combine: "Combine faces", hole_mesh: "Hole mesh", smooth: "Smooth surfaces", replace: "Replace faces", merge_tangent: "Merge tangent faces",
                     surf_extract: "Extract surface", surf_fit: "Fit surface", surf_sketch: "Extruded surface", surf_loft: "Loft surface",
                     surf_fill: "Fill surface", surf_offset: "Offset surface", surf_sew: "Sew surfaces", surf_import: "Import surface", thicken: "Thicken", surf_cut: "Cut with surface",
                     curve_extract: "Extract curve", curve_section: "Intersection curve", surf_from_curve: "Surface from curve", surf_trim: "Trim surface", surf_extend: "Extend surface", surf_bridge: "Bridge surface", surf_fillet: "Surface fillet", surf_gaps: "Close gaps", surf_sweep: "Sweep surface", curve_project: "Project curve", curve_blend: "Blend curve", curve_points: "Curve through points", surf_connect: "Connect surfaces", surf_clean: "Clean edges", surf_separate: "Separate faces" };
const SURFACE_TYPES = new Set(["surf_extract", "surf_fit", "surf_sketch", "surf_loft", "surf_fill", "surf_offset", "surf_sew", "surf_import", "curve_extract", "curve_section", "surf_from_curve", "surf_trim", "surf_extend", "surf_bridge", "surf_fillet", "surf_gaps", "surf_sweep", "curve_project", "curve_blend", "curve_points", "surf_connect", "surf_clean", "surf_separate"]);
const CURVE_TYPES = new Set(["curve_extract", "curve_section", "curve_project", "curve_blend", "curve_points"]);
const SOLID_TYPES = new Set(["extrude", "cut", "revolve", "hole", "sweep", "fillet", "chamfer", "shell", "pattern", "mirror", "boolean", "import", "place", "split", "unify", "heal", "defeature", "smooth", "replace", "merge_tangent", "thicken", "surf_cut", "hole_mesh", "offset_faces", "move_faces"]);
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
const COL = { mesh: 0xc9b48a, hover: 0x7ad17a, sel: 0x2bb24c, surf: 0x5b7fb5, curve: 0x6a1b9a, solid: 0xb8c2cf, edge: 0x1d2125, sketch: 0x7a4a9a, plane: 0x6c7a89, region: 0x3aa6d8, datum: 0x6a3fa0,
              ref: 0xe8590c, refEdge: 0xff00e6 };   // references of the active command: faces and bodies orange, edges and curves magenta

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
/** Coordinates of a point reference: a vertex [x, y, z] as it is, a point feature from its drawn object. */
function pointOf(ref) { if (isVertexRef(ref)) return ref; const o = (PT.pointObjs || []).find(x => x.userData.id === ref); return o ? o.userData.point : null; }
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
  controls.addEventListener("change", () => { rescaleMarkers(); render3(); });
  camera.userData.target = controls.target;
  PT.three.cube = createNavCube(box, camera, viewDir);
  let down = null;
  // Ctrl + left drag: box selection (the view does not rotate)
  box.addEventListener("pointerdown", e => { if (e.target === renderer.domElement && e.button === 0 && (e.ctrlKey || e.metaKey)) boxStart(e); }, true);
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
  let moveReq = null, lastMove = null;
  renderer.domElement.addEventListener("pointermove", e => {
    lastMove = e;                      // the hover of the last position of the frame
    if (moveReq) return;
    moveReq = requestAnimationFrame(() => { moveReq = null; hoverView(lastMove); });
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

/** Buffers shared by every geometry made from a mesh record, built once per record: the vertex positions, the
 *  vertex normals (each vertex belongs to one face, so the normals are those of its own face) and the triangle
 *  indices of each face. */
function meshBuffers(m) {
  if (m._buf) return m._buf;
  const V = m.vertices, T = m.triangles, nv = V.length;
  const pos = new Float32Array(nv * 3), nrm = new Float32Array(nv * 3);
  for (let i = 0, k = 0; i < nv; i++) { const v = V[i]; pos[k++] = v[0]; pos[k++] = v[1]; pos[k++] = v[2]; }
  const nf = m.face_solid ? m.face_solid.length : 0;
  const faceTris = Array.from({ length: nf }, () => []);
  for (let i = 0; i < T.length; i++) {
    const tr = T[i], a = tr[0] * 3, b = tr[1] * 3, c = tr[2] * 3;
    const fi = m.face_of_tri[i];
    if (fi >= 0 && fi < nf) faceTris[fi].push(i);
    const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
    const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    nrm[a] += nx; nrm[a + 1] += ny; nrm[a + 2] += nz; nrm[b] += nx; nrm[b + 1] += ny; nrm[b + 2] += nz; nrm[c] += nx; nrm[c + 1] += ny; nrm[c + 2] += nz;
  }
  for (let k = 0; k < nrm.length; k += 3) { const l = Math.hypot(nrm[k], nrm[k + 1], nrm[k + 2]) || 1; nrm[k] /= l; nrm[k + 1] /= l; nrm[k + 2] /= l; }
  m._buf = { pos: new THREE.BufferAttribute(pos, 3), nrm: new THREE.BufferAttribute(nrm, 3), faceTris };
  return m._buf;
}

/** Geometry of the triangles of the given faces (a Set of face indices) of a mesh record: the shared buffers with
 *  an index of its own. userData.tri[k] is the triangle index of the k-th triangle of the geometry. */
function facesGeometry(m, faceSet) {
  const b = meshBuffers(m), T = m.triangles, tri = [], gi = [];
  for (const fi of faceSet) {
    const ts = b.faceTris[fi];
    if (!ts) continue;
    for (const i of ts) { const tr = T[i]; tri.push(tr[0], tr[1], tr[2]); gi.push(i); }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", b.pos);
  g.setAttribute("normal", b.nrm);
  g.setIndex(tri);
  g.userData.tri = gi;
  return g;
}

/** Colour of a body ("solid:<i>" or a surface body id) set in Properties (part "body_colors"), else dflt. */
function bodyColor(id, dflt) {
  const c = (PT.part && PT.part.body_colors || {})[id];
  return c ? new THREE.Color(c) : dflt;
}
function colorRow(id, dflt) {
  const c = (PT.part.body_colors || {})[id] || "#" + new THREE.Color(dflt).getHexString();
  return `<div class="row pt-color"><label class="inline">Colour <input type="color" id="pp-color" value="${c}"></label>` +
    `<button type="button" id="pp-colordef" class="small"${(PT.part.body_colors || {})[id] ? "" : " disabled"}>Default</button></div>`;
}
function bindColor(id) {
  const inp = $("#pp-color"), def = $("#pp-colordef");
  if (!inp) return;
  inp.oninput = () => { PT.part.body_colors = Object.assign({}, PT.part.body_colors || {}, { [id]: inp.value }); PT.dirty = true; def.disabled = false; setMesh(PT.mesh); renderTree(); };
  inp.onchange = () => renderProps();
  def.onclick = () => { const bc = Object.assign({}, PT.part.body_colors || {}); delete bc[id]; PT.part.body_colors = bc; PT.dirty = true; setMesh(PT.mesh); renderTree(); renderProps(); };
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
    let nSolids = 0;
    for (const s of m.face_solid) if (s + 1 > nSolids) nSolids = s + 1;
    const solidFaces = Array.from({ length: nSolids }, () => new Set());
    m.face_solid.forEach((s, fi) => { if (s >= 0) solidFaces[s].add(fi); });
    for (let si = 0; si < nSolids; si++) {
      if (PT.hidden["solid:" + si]) continue;
      const faces = solidFaces[si];
      const g = facesGeometry(m, faces);
      const seeThrough = !!(PT.cmd && PT.cmd.regions);
      const mat = new THREE.MeshStandardMaterial({ color: bodyColor("solid:" + si, COL.solid), metalness: 0.15, roughness: 0.6, side: THREE.DoubleSide, transparent: seeThrough, opacity: seeThrough ? 0.3 : 1, depthWrite: !seeThrough,
                                                   polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
      const mesh = new THREE.Mesh(g, mat);
      mesh.userData = { kind: "solid", solid: si, faces };
      t.group.add(mesh);
      PT.faceObjs.push(mesh);
    }
    if ($("#pt-edges").checked) {
      const edgeMat = new THREE.LineBasicMaterial({ color: COL.edge });     // one material for all the edges
      m.edges.forEach((pl, i) => {
        // edges of hidden solids are hidden (an edge shared with a visible solid stays)
        const owners = (m.edge_solids || [])[i] || [];
        if (owners.length && owners.every(si => PT.hidden["solid:" + si])) return;
        const eg = new THREE.BufferGeometry();
        eg.setAttribute("position", new THREE.Float32BufferAttribute(pl.flat(), 3));
        const line = new THREE.Line(eg, edgeMat);
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
  // a command reopened on the part before its feature: the bodies it uses are shown (hidden since the feature was
  // made) so that their edges and faces can be picked
  const cf = PT.cmd && buildUpto() !== null && feat(PT.cmd.id);
  const used = new Set(cf ? consumedSources(cf) : []);
  for (const [id, sm] of Object.entries(PT.surfaces || {})) {
    if (PT.hidden[id] && !used.has(id)) continue;
    const f = feat(id);
    if (!f || f.suppressed) continue;
    if (trimming && (trimming.source === id || (trimming.mutual && trimming.tool === id && (trimming.with || "surface") === "surface"))) continue;
    const isCurve = !sm.triangles.length;
    const isMesh = !!(PT.status[id] && PT.status[id].mesh);
    if (!isCurve) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(sm.vertices.flat(), 3));
      g.setIndex(sm.triangles.flat());
      g.computeVertexNormals();
      // a rough mesh body (STL) is drawn opaque like a solid, the other surface bodies translucent
      const op = isMesh ? 1 : surfOpacity();
      const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: bodyColor(id, isMesh ? COL.mesh : COL.surf), transparent: op < 1, opacity: op,
                                                                     side: THREE.DoubleSide, depthWrite: op >= 1, flatShading: isMesh, metalness: isMesh ? 0.1 : 0, roughness: isMesh ? 0.7 : 1,
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
    } else if (isMesh) {
      // a mesh body: no triangle edges (they would hide the shading)
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
    const c = add(cpos, 0x2f74d0, true);                 // construction lines: picked like the other lines
    if (c) { c.userData.constr = true; PT.sketchObjs.push(c); }
    for (const m of sk.images || []) if (m.show3d && m.show !== false) drawSketchImage(item, m);
  }
}

/** Reference image of a sketch (images[].show3d) on the sketch plane: the shown file (corrected file, else the
 * image file) placed by its affine map A (shown pixel -> sketch point). */
function drawSketchImage(item, m) {
  const [w, h] = m.cfile && m.out ? m.out : [m.w, m.h];
  const A = m.A;
  if (!A || !(w > 0 && h > 0)) return;
  const sp = (u, v) => to3(item, A[0] * u + A[2] * v + A[4], A[1] * u + A[3] * v + A[5]);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute([...sp(0, 0), ...sp(w, 0), ...sp(w, h), ...sp(0, h)], 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute([0, 1, 1, 1, 1, 0, 0, 0], 2));
  g.setIndex([0, 1, 2, 0, 2, 3]);
  const url = "/api/sketch/image/file/" + encodeURIComponent(m.cfile || m.file);
  PT.imgTex = PT.imgTex || {};
  let tex = PT.imgTex[url];
  if (!tex) {
    tex = PT.imgTex[url] = new THREE.TextureLoader().load(url, () => render3(), undefined, () => { delete PT.imgTex[url]; });
    tex.colorSpace = THREE.SRGBColorSpace;
  }
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: m.opacity === undefined ? 0.6 : m.opacity,
                                            side: THREE.DoubleSide, depthWrite: false });
  const mesh = new THREE.Mesh(g, mat);
  mesh.renderOrder = 1;
  mesh.userData = { kind: "sketchimage", id: item.id };
  PT.three.group.add(mesh);
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
/** World units per screen pixel of the 3D view (orthographic camera). */
function worldPerPixel() {
  const t = PT.three;
  if (!t) return 0.1;
  const w = t.renderer.domElement.clientWidth || 1;
  return (t.camera.right - t.camera.left) / (t.camera.zoom || 1) / w;
}
/** A point marker of a fixed size on screen (px: radius in pixels) in the overlay; the markers are rescaled when
 *  the view zooms (see initThree). */
function addMarker(point, color, px, order, segments) {
  const t = PT.three;
  const sp = new THREE.Mesh(new THREE.SphereGeometry(1, segments || 12, segments || 12), new THREE.MeshBasicMaterial({ color, depthTest: false }));
  sp.position.set(point[0], point[1], point[2]);
  sp.scale.setScalar(worldPerPixel() * px);
  sp.renderOrder = order || 12;
  sp.userData.markerPx = px;
  t.overlay.add(sp);
  return sp;
}
/** Markers of the overlay rescaled to their pixel size after a zoom. */
function rescaleMarkers() {
  const t = PT.three;
  if (!t) return;
  const k = worldPerPixel();
  t.overlay.traverse(o => { if (o.userData && o.userData.markerPx) o.scale.setScalar(k * o.userData.markerPx); });
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
    // trim: kept green (translucent), removed strong red; profile regions: picked green, the others grey (none picked: all grey-green)
    let color, opacity;
    if (selectMode) { const on = selected.has((rg.uv || []).join(",")); color = on ? COL.region : 0x9aa5b1; opacity = on ? 0.7 : (selected.size ? 0.25 : 0.4); }
    else { const isRemoved = removed.has(rg.point.join(",")); color = isRemoved ? 0xff2020 : COL.region; opacity = isRemoved ? 0.75 : 0.55; }
    const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide,
                                                                   polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
    mesh.renderOrder = 4;
    mesh.userData = { kind: "region", index: i, point: rg.point, uv: rg.uv, area: rg.area };
    t.group.add(mesh);
    PT.regionObjs.push(mesh);
  });
}

/** Highlights: the selected tree item (green) and the references of the active command step (faces, bodies, planes and sketches orange; edges and curve bodies magenta). */
function drawSelection() {
  if (PT.quiet) return;
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
      const fi = m && m.face_keys ? m.face_keys.findIndex(k => k && keyOfFace(k) === keyOfFace(r)) : -1;      // no solid: no face keys
      if (fi >= 0) { faces.add(fi); continue; }
      // a face of a surface body
      for (const [sid, sm] of Object.entries(PT.surfaces || {})) { const si = (sm.face_keys || []).findIndex(k => k && keyOfFace(k) === keyOfFace(r)); if (si >= 0) { paintSurface(sid, 0xe8590c, 0.5, si); break; } }
    }
    paint(faces, 0xe8590c, 0.55, 4);
    paintEdges(new Set(refs.edges.map(keyOfEdge)), COL.refEdge);
    const bad = (PT.status[c.id] || {}).bad_edges;                 // edges where a fillet or chamfer fails
    if (bad && bad.length) paintEdges(new Set(bad.map(keyOfEdge)), 0xd0021b);
    for (const sid of refs.surfaces) if (PT.surfaces[sid]) paintSurface(sid, PT.surfaces[sid].triangles.length ? COL.ref : COL.refEdge, 0.5);
    for (const pid of refs.planes) paintPlane(pid, 0xe8590c);
    for (const sid of refs.sketches) paintSketch(sid, 0xe8590c);
    for (const did of refs.datums || []) paintDatum(did, 0xe8590c);
    if (c.type === "sweep" || c.type === "revolve") { const ln = axisLine3(c); if (ln) paintLine3(ln[0], ln[1], 0xe8590c); }
    // the solids the command acts on (Bodies section): tinted in the view
    const bsel = new Set((c.bodies || []).map(b => (typeof b === "object" ? b.solid : b)).concat(c.type === "split" ? (c.cells || []).filter(r => r && r.solid !== undefined).map(r => r.solid) : []));
    if (bsel.size && m && m.face_solid) { const bf = new Set(); m.face_solid.forEach((s, fi) => { if (bsel.has(s)) bf.add(fi); }); paint(bf, 0xe8590c, 0.3, 4); }
    for (const q of refs.points || []) addMarker(q, COL.ref, 7, 11);
    // the face or edge under the mouse in the selection chips of the command window
    // (hover, and the chip clicked to stay highlighted)
    for (const hv of [PT.chipPin, PT.chipHover]) {
      if (!hv) continue;
      if (hv.mid) { paintEdges(new Set([keyOfEdge(hv)]), 0x0a84ff); continue; }
      if (hv.point) { addMarker(hv.point, 0x0a84ff, 7, 12); continue; }
      if (!hv.c) continue;
      const fi = m && m.face_keys ? m.face_keys.findIndex(k => k && keyOfFace(k) === keyOfFace(hv)) : -1;
      if (fi >= 0) { paint(new Set([fi]), 0x0a84ff, 0.7, 5); continue; }
      for (const [sid, sm] of Object.entries(PT.surfaces || {})) { const si = (sm.face_keys || []).findIndex(k => k && keyOfFace(k) === keyOfFace(hv)); if (si >= 0) { paintSurface(sid, 0x0a84ff, 0.7, si); break; } }
    }
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
        addMarker(x.p, color, active ? 6 : 4, 13, 10);
      }
    });
  }
  if (PT.section) t.overlay.traverse(o => { if (o.material && !o.userData.noclip) o.material.clippingPlanes = [PT.section.plane]; });
  // centre of rotation
  if (PT.pivot) addMarker(PT.pivot, 0x2f74d0, 5, 12, 10);
  // hover
  if (PT.hover) {
    const h = PT.hover;
    if (h.kind === "face" && h.surface) paintSurface(h.surface, COL.hover, 0.6, h.fi);
    else if (h.kind === "face") paint(new Set([h.fi]), COL.hover, 0.5, 5);
    else if (h.kind === "body") paint(new Set([...h.faces]), COL.hover, 0.35, 5);
    else if (h.kind === "edge") paintEdges(new Set([keyOfEdge(h.key)]), COL.hover);
    else if (h.kind === "surface" || h.kind === "curve") paintSurface(h.id, COL.hover, 0.6);
    else if (h.kind === "plane") paintPlane(h.id, COL.hover);
    else if (h.kind === "sketch") {
      const ax = activeAxisStep();
      const near = ax && h.id === ax.f.sketch_ref && h.point ? nearestSketchLine(feat(h.id), axisLines(ax.f, ax.constrOnly), h.point) : null;
      if (near && near.dist <= planeSize() * 0.02) paintLine3(near.a, near.b, COL.hover); else paintSketch(h.id, COL.hover);
    }
    else if (h.kind === "point" && h.vertex) addMarker(h.point, COL.hover, 6, 12, 10);
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
  if (p) addMarker(p.userData.point, color, 8, 11);
  const a = PT.axisObjs.find(o => o.userData.id === id);
  if (a) { const l = new THREE.Line(a.geometry, new THREE.LineBasicMaterial({ color, depthTest: false })); l.renderOrder = 10; t.overlay.add(l); }
}
function paintSketch(id, color) {
  const t = PT.three;
  for (const o of PT.sketchObjs.filter(p => p.userData.id === id)) {
    const l = new THREE.LineSegments(o.geometry, new THREE.LineBasicMaterial({ color, depthTest: false, linewidth: 2 }));
    l.renderOrder = 10;
    t.overlay.add(l);
  }
}

/** A line between two 3D points in the overlay (an axis chosen or under the cursor). */
function paintLine3(a, b, color) {
  const t = PT.three;
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute([...a, ...b], 3));
  const l = new THREE.Line(g, new THREE.LineBasicMaterial({ color, depthTest: false }));
  l.renderOrder = 12;
  t.overlay.add(l);
  for (const q of [a, b]) addMarker(q, color, 4, 12, 8);
}

/** Lines of the profile sketch of f that can be its axis (constrOnly: construction lines only, as Revolve lists). */
function axisLines(f, constrOnly) {
  const sk = f.sketch_ref && feat(f.sketch_ref);
  return (((sk || {}).sketch || {}).entities || []).filter(e => e.t === "line" && !e.axis && (!constrOnly || e.constr));
}

/** The line of lines (entities of the sketch item sk) nearest to the 3D point q: {e, a, b, dist} or null. */
function nearestSketchLine(sk, lines, q) {
  let best = null;
  for (const e of lines) {
    const a = to3(sk, e.x1, e.y1), b = to3(sk, e.x2, e.y2);
    const d = [0, 1, 2].map(k => b[k] - a[k]), L2 = d.reduce((t, v) => t + v * v, 0) || 1;
    const t = Math.max(0, Math.min(1, [0, 1, 2].reduce((s2, k) => s2 + (q[k] - a[k]) * d[k], 0) / L2));
    const dist = Math.hypot(...[0, 1, 2].map(k => q[k] - (a[k] + t * d[k])));
    if (!best || dist < best.dist) best = { e, a, b, dist };
  }
  return best;
}

/** The step of the active command that takes a line of the profile sketch as the axis (Sweep tool axis, Revolve
 *  axis), when it is the active step: {f, constrOnly} or null. */
function activeAxisStep() {
  const c = PT.cmd, f = c && feat(c.id);
  if (!f || c.pick) return null;
  const st = commandSteps(f)[c.step];
  if (!st || !st.axisPick) return null;
  return { f, constrOnly: st.axisPick === "constr" };
}

/** Name of a sketch line for the hover text and the command window. */
function lineLabel(e) { return (e.constr ? "Construction line " : "Line ") + e.id + " (" + pfmt(e.x1, 2) + ", " + pfmt(e.y1, 2) + ") - (" + pfmt(e.x2, 2) + ", " + pfmt(e.y2, 2) + ")"; }

/** A click on a line of the profile sketch or on an axis feature as the axis of f (f.axis: line id, or f.axis_ref:
 *  the axis feature). constrOnly: construction lines only. */
function acceptAxisPick(f, h, constrOnly) {
  if (h.kind === "axis") { f.axis_ref = h.id; PT.dirty = true; return; }
  if (h.id !== f.sketch_ref) { msgPart("Click a line of the profile sketch (" + itemName(f.sketch_ref) + ")", true); return; }
  const sk = feat(f.sketch_ref);
  if (!h.point) return;
  const best = nearestSketchLine(sk, axisLines(f, constrOnly), h.point);
  if (!best) { msgPart(constrOnly ? "The profile sketch has no construction line" : "The profile sketch has no line", true); return; }
  if (best.dist > planeSize() * 0.02) { msgPart("Click a " + (constrOnly ? "construction line" : "line") + " of the profile sketch (the line under the cursor is highlighted)", true); return; }
  f.axis = best.e.id; f.axis_ref = null; PT.dirty = true;
  msgPart(lineLabel(best.e) + " is the axis");
}

/** The axis line of a Sweep or Revolve feature in the view: [a, b] (3D ends of the sketch line) or null. */
function axisLine3(f) {
  if (!f || f.axis_ref || !f.sketch_ref) return null;
  const sk = feat(f.sketch_ref);
  if (!sk) return null;
  const e = axisLines(f, false).find(x => String(x.id) === String(f.axis));
  if (e) return [to3(sk, e.x1, e.y1), to3(sk, e.x2, e.y2)];
  if (f.axis === "u" || f.axis === "v") {
    // the sketch axis across the extent of the sketch
    let lo = -10, hi = 10;
    for (const x of (sk.sketch || {}).entities || []) for (const [u, v] of sketchPolylines({ entities: [x] }).flat()) { const w = f.axis === "u" ? u : v; lo = Math.min(lo, w); hi = Math.max(hi, w); }
    lo -= 2; hi += 2;
    return f.axis === "u" ? [to3(sk, lo, 0), to3(sk, hi, 0)] : [to3(sk, 0, lo), to3(sk, 0, hi)];
  }
  return null;
}

// ------------------------------------------------------------------ hover and click in the view

/** Element under the cursor, filtered by kinds (array of kinds or null for all). */
/** Vertices of the solid and of the shown surface and curve bodies (ends of the edge polylines), cached per mesh
 *  and set of shown bodies. */
function meshVertices() {
  const m = PT.mesh;
  const shown = Object.keys(PT.surfaces || {}).filter(id => !PT.hidden[id] && feat(id) && !feat(id).suppressed).join(",");
  if (PT.vtxCache && PT.vtxCache.mesh === m && PT.vtxCache.surfaces === PT.surfaces && PT.vtxCache.shown === shown) return PT.vtxCache.list;
  const seen = new Set(), list = [];
  const add = pl => {
    if (!pl || !pl.length) return;
    for (const q of [pl[0], pl[pl.length - 1]]) {
      const k = q.map(x => x.toFixed(4)).join(",");
      if (!seen.has(k)) { seen.add(k); list.push(q.slice()); }
    }
  };
  for (const pl of (m && m.edges) || []) add(pl);
  for (const id of shown ? shown.split(",") : []) for (const pl of (PT.surfaces[id] || {}).edges || []) add(pl);
  PT.vtxCache = { mesh: m, surfaces: PT.surfaces, shown, list };
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
        const ti = hit.object.geometry.userData.tri;
        const fi = m.face_of_tri[ti ? ti[hit.faceIndex] : hit.faceIndex];
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
  if (PT.measure && !PT.cmd) return ["face", "sface", "plane", "axis"];
  const c = PT.cmd;
  if (!c) return null;
  if (c.pick) return c.pick.kinds;
  const lp = legacyPick(c);
  if (lp) return lp.kinds;
  const steps = commandSteps(feat(c.id)), st = steps[c.step];
  if (st && st.kinds) return st.kinds;
  // a value section is active: the clicks go to the element sections (feedCommand picks the section)
  const all = [...new Set(steps.filter(isPickStep).flatMap(x => x.kinds))];
  return all.length ? all : null;
}

// ------------------------------------------------------------------ 3D sketch (Curve through points with "space")
// Points picked in space: vertices, points of the curve, edge midpoints, centres of circular edges, centre lines
// (axes of circular edges and cylindrical faces), points on edges, the 3D snap grid (a plane through the anchor
// point: the last point of the curve, else the origin) and, with Shift, the line along the grid normal through the
// anchor. X, Y, Z: grid normal; Backspace: removes the last point.

const GRID_PLANES = { z: "XY", y: "XZ", x: "YZ" };
const AXV = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] };
/** The 3D sketch whose Points step is active, or null. */
function spaceFeat() {
  const c = PT.cmd;
  if (!c) return null;
  const f = feat(c.id);
  if (!f || f.type !== "curve_points" || !f.space) return null;
  const st = commandSteps(f)[c.step];
  return st && st.key === "points" ? f : null;
}
function niceStep(v) {
  const e = Math.pow(10, Math.floor(Math.log10(v)));
  return [1, 2, 5, 10].map(k => k * e).find(x => x >= v) || 10 * e;
}
/** Grid of a 3D sketch: {axis, step (mm), anchor}. */
function spaceGrid(f) {
  const g = f.grid || {};
  const bb = PT.mesh && PT.mesh.bbox;
  const size = bb ? Math.hypot(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]) : 100;
  const pts = (f.points || []).map(pointOf).filter(Boolean);
  return { axis: g.axis || "z", step: +g.step > 0 ? +g.step : niceStep(Math.max(size, 1) / 40), anchor: pts.length ? pts[pts.length - 1] : [0, 0, 0], pts };
}
const vec3 = a => new THREE.Vector3(a[0], a[1], a[2]);
/** Closest points of the ray and the line p + s d: s on the line. */
function rayLineS(ray, p, d) {
  const w0 = ray.origin.clone().sub(p), a = ray.direction.dot(ray.direction), b = ray.direction.dot(d), c = d.dot(d);
  const dd = ray.direction.dot(w0), e = d.dot(w0), den = a * c - b * b;
  return Math.abs(den) < 1e-12 ? 0 : (a * e - b * dd) / den;
}
/** Snap of the cursor in a 3D sketch: a hit {kind: "point", vertex: true, point, snap}. */
function snap3d(e, f) {
  const t = PT.three, r = t.renderer.domElement.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  const nd = new THREE.Vector2((mx / r.width) * 2 - 1, -(my / r.height) * 2 + 1);
  const rc = new THREE.Raycaster();
  rc.setFromCamera(nd, t.camera);
  const scr = q => { const v = vec3(q).project(t.camera); return Math.hypot((v.x + 1) / 2 * r.width - mx, (1 - v.y) / 2 * r.height - my); };
  const G = spaceGrid(f), n = vec3(AXV[G.axis]), A = vec3(G.anchor);
  const hit = (point, snap) => ({ kind: "point", vertex: true, point: point.map(v => Math.round(v * 1e6) / 1e6), snap });
  const roundS = s => Math.round(s / G.step) * G.step;
  // Shift: along the grid normal through the anchor
  if (e.shiftKey) {
    const sN = roundS(rayLineS(rc.ray, A, n));
    return Object.assign(hit(A.clone().addScaledVector(n, sN).toArray(), "along " + G.axis.toUpperCase()), { line: [G.anchor, A.clone().addScaledVector(n, sN).toArray()] });
  }
  // vertices and point features (not behind a face), the points of the curve
  const v = pickAt(e, ["point"]);
  if (v) return Object.assign(v, { snap: v.vertex ? "vertex" : "point feature" });
  for (const q of G.pts) if (scr(q) < 8) return hit(q, "point of the curve");
  // edge midpoints, centres of circular edges (8 px)
  let best = null, bd = 8;
  const keys = (PT.mesh && PT.mesh.edge_keys) || [];
  for (const k of keys) {
    if (!k) continue;
    if (k.mid && !k.round) { const d = scr(k.mid); if (d < bd) { bd = d; best = hit(k.mid, "midpoint"); } }
    if (k.round && k.round.c) { const d = scr(k.round.c); if (d < bd) { bd = d; best = hit(k.round.c, "centre"); } }
  }
  if (best) return best;
  // centre lines: the axes of circular edges and cylindrical faces (6 px of the line)
  const axes = [];
  for (const k of keys.concat((PT.mesh && PT.mesh.face_keys) || [])) if (k && k.round && k.round.c && k.round.ax) axes.push(k.round);
  for (const q of axes) {
    const c = vec3(q.c), d = vec3(q.ax).normalize();
    const sA = rayLineS(rc.ray, c, d), pt = c.clone().addScaledVector(d, roundS(sA)), raw = c.clone().addScaledVector(d, sA);
    const dd = scr(raw.toArray());
    if (dd < 6 && dd < bd) { bd = dd; best = Object.assign(hit(pt.toArray(), "centre line"), { line: [c.clone().addScaledVector(d, -G.step * 20).toArray(), c.clone().addScaledVector(d, G.step * 20).toArray()] }); }
  }
  if (best) return best;
  // a point on an edge or a curve body
  const eh = pickAt(e, ["edge", "sedge", "curve"]);
  if (eh && eh.line && eh.point) return hit(eh.point, "on edge");
  // the grid: the ray on the plane through the anchor
  const den = rc.ray.direction.dot(n);
  if (Math.abs(den) < 1e-9) return null;
  const s0 = A.clone().sub(rc.ray.origin).dot(n) / den;
  const P = rc.ray.origin.clone().addScaledVector(rc.ray.direction, s0).sub(A);
  const u = G.axis === "x" ? [1, 2] : G.axis === "y" ? [0, 2] : [0, 1];
  const q = P.toArray();
  for (const i of u) q[i] = roundS(q[i]);
  return hit(A.clone().add(vec3(q)).toArray(), "grid " + GRID_PLANES[G.axis]);
}
/** Grid, cursor point, rubber band from the last point and snap line of the 3D sketch (overlay of the view). */
function drawSpace(f, h) {
  const t = PT.three;
  if (!t) return;
  if (!t.space) { t.space = new THREE.Group(); t.space.renderOrder = 30; t.scene.add(t.space); }
  const grp = t.space;
  for (const o of [...grp.children]) { grp.remove(o); if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); }
  if (!f) { render3(); return; }
  const G = spaceGrid(f), N = 10, u = G.axis === "x" ? [1, 2] : G.axis === "y" ? [0, 2] : [0, 1];
  const pos = [], axisPos = [];
  for (let k = -N; k <= N; k++) {
    for (const [i, j] of [[u[0], u[1]], [u[1], u[0]]]) {
      const a = G.anchor.slice(), b = G.anchor.slice();
      a[i] += k * G.step; b[i] += k * G.step; a[j] -= N * G.step; b[j] += N * G.step;
      (k === 0 ? axisPos : pos).push(...a, ...b);
    }
  }
  const lines = (arr, color, opacity, dashed) => {
    if (!arr.length) return;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(arr, 3));
    const m = dashed ? new THREE.LineDashedMaterial({ color, dashSize: G.step / 2, gapSize: G.step / 3, depthTest: false, transparent: true, opacity })
      : new THREE.LineBasicMaterial({ color, depthTest: false, transparent: true, opacity });
    const l = new THREE.LineSegments(g, m);
    if (dashed) l.computeLineDistances();
    l.renderOrder = 30;
    grp.add(l);
  };
  lines(pos, 0x868e96, 0.35);
  lines(axisPos, 0x1f5fae, 0.6);
  // the curve so far and the rubber band
  const pts = G.pts, poly = [];
  for (let k = 0; k + 1 < pts.length; k++) poly.push(...pts[k], ...pts[k + 1]);
  lines(poly, 0x6a1b9a, 1);
  if (h && h.point) {
    if (pts.length) lines([...pts[pts.length - 1], ...h.point], 0xe8590c, 1, true);
    if (h.line) lines([...h.line[0], ...h.line[1]], 0x0b7a75, 0.9, true);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(h.point, 3));
    const pm = new THREE.Points(g, new THREE.PointsMaterial({ color: 0xe8590c, size: 10, sizeAttenuation: false, depthTest: false }));
    pm.renderOrder = 31;
    grp.add(pm);
  }
  render3();
}

/** Grid and typed point controls of the Points step of a 3D sketch. */
function spaceHtml(f) {
  const G = spaceGrid(f);
  return `<div class="grid2">` + select("pf-sgax", "Grid plane", [["z", "XY (normal Z, key Z)"], ["y", "XZ (normal Y, key Y)"], ["x", "YZ (normal X, key X)"]], G.axis) +
    num("pf-sgstep", "Grid step (mm; empty: automatic " + pfmt(spaceGrid(Object.assign({}, f, { grid: { axis: G.axis } })).step) + ")", (f.grid || {}).step || "") + `</div>` +
    `<p class="hint">Grid through (${G.anchor.map(v => pfmt(v, 3)).join(", ")}) mm. Point x y z (mm)${G.pts.length ? "; Relative: from the last point" : ""}:</p>` +
    `<div class="row wrap"><input type="text" id="pf-sxyz" placeholder="x, y, z" style="width:140px">` + (G.pts.length ? `<label class="check inline"><input type="checkbox" id="pf-srel"${PT.spaceRel ? " checked" : ""}> Relative</label>` : "") +
    `<button type="button" id="pf-sadd">Add point</button></div>`;
}
function bindSpace(f, box) {
  const ax = box.querySelector("#pf-sgax"), st = box.querySelector("#pf-sgstep"), xyz = box.querySelector("#pf-sxyz"), rel = box.querySelector("#pf-srel");
  if (ax) ax.onchange = () => { f.grid = Object.assign({}, f.grid, { axis: ax.value }); renderCommand(); drawSpace(f, null); };
  if (st) st.onchange = () => { const v = numv(st.value); f.grid = Object.assign({}, f.grid); if (v > 0) f.grid.step = v; else delete f.grid.step; renderCommand(); drawSpace(f, null); };
  if (rel) rel.onchange = () => { PT.spaceRel = rel.checked; };
  const add = () => {
    const v = xyz.value.split(/[,;\s]+/).filter(Boolean).map(numv);
    if (v.length !== 3 || !v.every(isFinite)) { msgPart("Point: three numbers x, y, z (mm)", true); return; }
    const G = spaceGrid(f), q = PT.spaceRel && G.pts.length ? v.map((c, i) => G.anchor[i] + c) : v;
    f.points = (f.points || []).concat([q.map(c => Math.round(c * 1e6) / 1e6)]);
    PT.dirty = true; changedPart(); renderCommand(); drawSpace(f, null);
  };
  box.querySelector("#pf-sadd").onclick = add;
  xyz.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); add(); } };
}

function hoverView(e) {
  if (!PT.three || !PT.part) return;
  const sf = spaceFeat();
  if (sf) { const h = snap3d(e, sf); PT.spaceHover = h; setHover(h, e); drawSpace(sf, h); return; }
  if (PT.three.space && PT.three.space.children.length) drawSpace(null);
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
  if (h.kind === "sketch") {
    const ax = activeAxisStep();
    const near = ax && h.id === ax.f.sketch_ref && h.point ? nearestSketchLine(feat(h.id), axisLines(ax.f, ax.constrOnly), h.point) : null;
    return near && near.dist <= planeSize() * 0.02 ? lineLabel(near.e) + " of " + itemName(h.id) : itemName(h.id);
  }
  if (h.kind === "point" && h.snap) { const q = h.point || []; return h.snap[0].toUpperCase() + h.snap.slice(1) + " (" + q.map(v => pfmt(v, 3)).join(", ") + ") mm"; }
  if (h.kind === "point") { const q = h.point || []; return (h.vertex ? "Vertex" : itemName(h.id)) + " (" + q.map(v => pfmt(v, 2)).join(", ") + ") mm"; }
  if (h.kind === "axis") return itemName(h.id);
  if (h.kind === "plane") return BASE_PLANES[h.id] ? "Reference plane " + BASE_PLANES[h.id] : itemName(h.id);
  if (h.kind === "region") return "Region " + (h.index + 1) + ", " + pfmt(h.area, 1) + " mm^2";
  return "";
}

/** Click in the view: feeds the active command step, or selects the owner of the element in the tree. */
function clickView(e) {
  const kinds = activeKinds();
  const sf = spaceFeat();
  const h = sf ? snap3d(e, sf) : pickAt(e, kinds);
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
  // a click in the view ends the typing in a field of the command window (the window is then redrawn)
  const ae = document.activeElement, cw = $("#pt-cmdbody");
  if (ae && cw && cw.contains(ae) && ae.matches("input, select, textarea")) ae.blur();
  const kinds = activeKinds();
  if (!kinds || !kinds.includes(h.kind)) return false;
  const f = feat(c.id);
  if (!c.pick && !legacyPick(c)) {
    // the active section does not take this element: the element section that does (the nearest one above the
    // active section, else the first one) becomes active
    const steps = commandSteps(f), cur = steps[c.step];
    if (!(cur && cur.kinds && cur.kinds.includes(h.kind))) {
      const idx = steps.map((x, i) => i).filter(i => steps[i].kinds && steps[i].kinds.includes(h.kind));
      const before = idx.filter(i => i < c.step);
      const j = before.length ? before[before.length - 1] : idx[0];
      if (j === undefined) return false;
      c.step = j;
      if (steps[j].enter) steps[j].enter(f);
    }
  }
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
  const h = pickAt(e, ["plane", "face", "sface", "edge", "curve", "sketch"]);
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

/** Cell of a picked edge of the solid when the part has several cells: the first shown solid that holds the edge
 *  (an edge where cells touch, or edges of two solids at one place, are one edge in the view). */
function edgeCell(h) {
  const m = PT.mesh;
  if (h.surface || h.index === undefined || !m || !m.face_solid || !(Math.max(0, ...m.face_solid) >= 1)) return undefined;
  const owners = (m.edge_solids || [])[h.index] || [];
  if (!owners.length) return undefined;
  const shown = owners.find(si => !PT.hidden["solid:" + si]);
  return shown !== undefined ? shown : owners[0];
}

function refOf(h) {
  // cell: the solid the face was picked on (a face between two cells belongs to both)
  if (h.kind === "face") return PT.cells > 1 && h.solid !== undefined ? { c: h.key.c, n: h.key.n, area: h.key.area, cell: h.solid } : { c: h.key.c, n: h.key.n, area: h.key.area };
  if (h.kind === "edge") { const c = edgeCell(h); return c !== undefined ? { mid: h.key.mid, len: h.key.len, cell: c } : { mid: h.key.mid, len: h.key.len }; }
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
  if (h.kind === "face" && h.key && !pick.single && !(pick.kinds || []).includes("edge") && faceMode() !== "face") { pickFaces(f, pick.prop, h, faceMode()); return; }
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
    // the edges grown from a face or an edge picked on a cell belong to that cell
    const cell = refs.length && refs[0] && Number.isInteger(refs[0].cell) ? refs[0].cell : undefined;
    if (cell !== undefined) for (const k of keys) k.cell = cell;
    f[prop] = f[prop] || [];
    const have = new Set(f[prop].map(keyOfEdge));
    let n = 0;
    for (const k of keys) if (!have.has(keyOfEdge(k))) { f[prop].push(k.cell !== undefined ? { mid: k.mid, len: k.len, cell: k.cell } : { mid: k.mid, len: k.len }); have.add(keyOfEdge(k)); n++; }
    PT.dirty = true;
    renderCommand(); drawSelection(); scheduleBuild();
    msgPart(n + " edge(s) added, " + f[prop].length + " selected");
  } catch (e) { showErr(e); }
}

/** Face click mode of the steps that take several faces: Face, Tangent faces (joined through tangent edges) or
 *  Connected faces (all faces joined through edges, within the solid or surface body of the clicked face). */
const faceModeHtml = () => `<div class="cw-modes" title="What a click on a face adds">` +
  [["face", "Face"], ["tangent", "Tangent faces"], ["connected", "Connected faces"]].map(([v, l]) =>
    `<label class="check inline"><input type="radio" name="pf-fmode" value="${v}"${((PT.cmd && PT.cmd.fmode) || "face") === v ? " checked" : ""}> ${l}</label>`).join("") + `</div>`;
const bindFaceMode = box => { box.querySelectorAll("input[name=pf-fmode]").forEach(r => r.onchange = () => { if (PT.cmd) PT.cmd.fmode = r.value; }); bindBoxTools(box); };
const faceMode = () => (PT.cmd && PT.cmd.fmode) || "face";
/** Multi-face step of the command bar (takes faces into an array): the face click mode is shown. */
const isMultiFaceStep = st => !!st && (st.multiFace || (!!st.prop && !st.single && !st.accept && Array.isArray(st.kinds) && (st.kinds.includes("face") || st.kinds.includes("sface"))));

/** Adds the faces grown from the clicked face (mode tangent or connected) to f[prop]; when the clicked face is
 *  already selected, removes them. */
async function pickFaces(f, prop, h, mode) {
  try {
    const r = await postJSON("/api/part/expand_faces", { part: PT.part, index: featIndex(f.id), mode, ref: Object.assign({ c: h.key.c, n: h.key.n, area: h.key.area }, PT.cells > 1 && h.solid !== undefined && !h.surface ? { cell: h.solid } : {}), surface: h.surface || null });
    const keys = await r.json();
    f[prop] = f[prop] || [];
    const at = k => f[prop].findIndex(x => x && x.c && keyOfFace(x) === keyOfFace(k));
    const had = at(h.key) >= 0;
    let n = 0;
    for (const k of keys) {
      const i = at(k);
      if (had && i >= 0) { f[prop].splice(i, 1); n++; }
      else if (!had && i < 0) { f[prop].push(PT.cells > 1 && h.solid !== undefined && !h.surface ? { c: k.c, n: k.n, area: k.area, cell: h.solid } : { c: k.c, n: k.n, area: k.area }); n++; }
    }
    PT.dirty = true;
    renderCommand(); drawSelection(); scheduleBuild();
    msgPart(n + " face(s) " + (had ? "removed" : "added") + ", " + f[prop].length + " selected");
  } catch (e) { showErr(e); }
}

// ------------------------------------------------------------------ box selection and Select shown
/** The active pick of the command: { kinds, multi } (multi: the step takes several elements). */
function activePick() {
  const c = PT.cmd;
  if (!c) return null;
  const p = c.pick || legacyPick(c);
  if (p) return { kinds: p.kinds || [], multi: !p.single };
  const f = feat(c.id), steps = f ? commandSteps(f) : [], st = steps[c.step];
  const multi = x => !!(x.multi || x.multiFace || (x.prop && !x.single));
  if (st && st.kinds) return { kinds: st.kinds, multi: multi(st) };
  // a value section is active: the element sections (feedCommand gives each element to the section that takes it)
  const picks = steps.filter(isPickStep);
  if (!picks.length) return null;
  return { kinds: [...new Set(picks.flatMap(x => x.kinds))], multi: picks.some(multi) };
}
/** Kinds taken by a box or Select shown: the edges when the step takes edges (a face would add all its edges),
 *  otherwise the kinds of the step without reference planes and axes. */
function boxKinds(kinds) {
  if (kinds.includes("edge") || kinds.includes("sedge")) return kinds.filter(k => k === "edge" || k === "sedge");
  return kinds.filter(k => k !== "plane" && k !== "axis");
}
const boxToolsHtml = (extra) => `<div class="buttons"><button type="button" id="pf-shown" title="Adds every element of this step that is visible in the view (in the view area and not hidden behind a solid)">Select shown</button>${extra || ""}` +
  `<label class="check inline" title="Box selection: Ctrl + left drag. Left to right: the elements entirely inside the box; right to left: the elements the box touches"><input type="checkbox" id="pf-boxshown"${PT.boxShown ? " checked" : ""}> Box: shown only</label></div>`;
function bindBoxTools(box) {
  const b = box.querySelector("#pf-shown");
  if (b) b.onclick = () => selectShown();
  const k = box.querySelector("#pf-boxshown");
  if (k) k.onchange = () => { PT.boxShown = k.checked; };
}

/** Elements of the given kinds in the view: [{ h, pts (world points of the element), probes (points on it for
 *  the visibility test) }]. h is the hit a click on the element gives. */
function boxCandidates(kinds) {
  const allow = k => kinds.includes(k);
  const out = [], m = PT.mesh;
  const posOf = o => { const a = o.geometry.attributes.position, p = []; for (let i = 0; i < a.count; i++) p.push([a.getX(i), a.getY(i), a.getZ(i)]); return p; };
  const mid = pl => pl[Math.floor(pl.length / 2)] || pl[0];
  // faces of a triangle mesh: their vertices and the centres of up to 5 of their largest triangles
  const faceSets = (verts, tris, faceOfTri, skip) => {
    const by = new Map();
    tris.forEach((tr, i) => {
      const fi = faceOfTri[i];
      if (fi === undefined || fi < 0 || (skip && skip(fi))) return;
      let e = by.get(fi);
      if (!e) by.set(fi, e = { vi: new Set(), tris: [] });
      tr.forEach(v => e.vi.add(v));
      const [a, b, c] = tr.map(v => verts[v]);
      const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
      const ar = Math.hypot(uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx);
      e.tris.push([ar, [(a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, (a[2] + b[2] + c[2]) / 3]]);
    });
    for (const e of by.values()) { e.pts = [...e.vi].map(v => verts[v]); e.probes = e.tris.sort((x, y) => y[0] - x[0]).slice(0, 5).map(x => x[1]); }
    return by;
  };
  if (m && m.vertices.length && (allow("face") || allow("body"))) {
    const shownSolid = si => !PT.hidden["solid:" + si];
    const by = faceSets(m.vertices, m.triangles, m.face_of_tri, fi => !shownSolid(m.face_solid[fi]));
    if (allow("face")) {
      for (const [fi, e] of by) out.push({ h: { kind: "face", fi, key: m.face_keys[fi], solid: m.face_solid[fi], owner: (m.face_owner || [])[fi], point: e.probes[0] }, pts: e.pts, probes: e.probes, fi });
    } else {
      for (const o of PT.faceObjs) {
        const pts = [], probes = [];
        for (const fi of o.userData.faces) { const e = by.get(fi); if (e) { pts.push(...e.pts); probes.push(...e.probes.slice(0, 1)); } }
        if (pts.length) out.push({ h: { kind: "body", solid: o.userData.solid, faces: o.userData.faces, point: probes[0] }, pts, probes, solid: o.userData.solid });
      }
    }
  }
  if (allow("surface") || allow("sface")) {
    for (const o of PT.surfObjs.filter(o => o.userData.kind === "surface")) {
      const id = o.userData.id, sm = PT.surfaces[id];
      if (!sm) continue;
      if (allow("sface") && !allow("surface") && sm.face_of_tri) {
        for (const [fi, e] of faceSets(sm.vertices, sm.triangles, sm.face_of_tri)) {
          const key = (sm.face_keys || [])[fi];
          if (key) out.push({ h: { kind: "face", fi, key, surface: id, point: e.probes[0] }, pts: e.pts, probes: e.probes, surface: id, fi });
        }
      } else out.push({ h: { kind: "surface", id, fi: -1, key: null }, pts: sm.vertices, probes: sm.vertices.filter((v, i) => i % Math.max(1, Math.floor(sm.vertices.length / 8)) === 0), surface: id });
    }
  }
  for (const l of PT.edgeLines) {
    const u = l.userData;
    if (u.surface ? !allow("sedge") : !allow("edge")) continue;
    const pl = u.polyline || (m && m.edges[u.index]) || posOf(l);
    out.push({ h: { kind: "edge", key: u.key, index: u.index, surface: u.surface, polyline: pl, point: mid(pl), line: true }, pts: pl, probes: [mid(pl), pl[0], pl[pl.length - 1]], line: true });
  }
  if (allow("region")) for (const o of PT.regionObjs) { const u = o.userData, p = posOf(o); out.push({ h: { kind: "region", index: u.index, point: u.point, uv: u.uv, area: u.area }, pts: p, probes: [u.point], region: true }); }
  if (allow("point")) {
    for (const o of PT.pointObjs) { const u = o.userData; out.push({ h: { kind: "point", id: u.id, point: u.point }, pts: [u.point], probes: [u.point], line: true }); }
    for (const q of meshVertices()) out.push({ h: { kind: "point", vertex: true, point: q.slice() }, pts: [q], probes: [q], line: true });
  }
  if (allow("sketch")) for (const o of PT.sketchObjs) { const p = posOf(o); out.push({ h: { kind: "sketch", id: o.userData.id }, pts: p, probes: [p[0]], line: true, always: true }); }
  if (allow("curve")) for (const o of PT.surfObjs.filter(o => o.userData.kind === "curve")) { const p = posOf(o); out.push({ h: { kind: "curve", id: o.userData.id }, pts: p, probes: [p[0]], line: true, always: true }); }
  return out;
}

/** True when a point of the candidate is in the view area and not behind a solid face (or an opaque mesh body). */
function shownCandidate(cd) {
  const t = PT.three, r = t.renderer.domElement.getBoundingClientRect();
  const px = (t.camera.right - t.camera.left) / t.camera.zoom / r.width;
  const see = !!(PT.cmd && PT.cmd.regions);                      // the solid is drawn see-through while regions are shown
  const occl = see ? [] : PT.faceObjs.concat(PT.surfObjs.filter(o => o.userData.kind === "surface" && PT.status[o.userData.id] && PT.status[o.userData.id].mesh));
  const rc = new THREE.Raycaster(), v = new THREE.Vector3();
  for (const q of cd.probes) {
    v.set(q[0], q[1], q[2]).project(t.camera);
    if (Math.abs(v.x) > 1 || Math.abs(v.y) > 1) continue;
    if (cd.always || cd.region || !occl.length) return true;
    rc.setFromCamera(new THREE.Vector2(v.x, v.y), t.camera);
    const along = new THREE.Vector3(...q).sub(rc.ray.origin).dot(rc.ray.direction);
    const hits = rc.intersectObjects(occl, false);
    if (!hits.length || hits[0].distance >= along - px * 3) return true;
    // the first face hit is the face itself (a face of the solid)
    const hh = hits[0];
    if (cd.fi !== undefined && !cd.surface && hh.object.userData.kind === "solid") {
      const ti = hh.object.geometry.userData.tri;
      if (PT.mesh.face_of_tri[ti ? ti[hh.faceIndex] : hh.faceIndex] === cd.fi) return true;
    }
    if (cd.solid !== undefined && hh.object.userData.solid === cd.solid) return true;
  }
  return false;
}

/** Adds the hits to the active step (a hit that is already selected stays selected). */
function addHits(hits) {
  const c = PT.cmd;
  if (!c || !hits.length) return 0;
  const f = feat(c.id);
  const fm = c.fmode, em = c.emode;
  c.fmode = "face"; c.emode = "edge";
  PT.quiet = true;
  let n = 0;
  try {
    for (const h of hits) {
      const before = {};
      for (const [k, v] of Object.entries(f)) if (Array.isArray(v)) before[k] = v.slice();
      if (!feedCommand(h)) continue;
      // a click on a selected element deselects it: the arrays that got shorter are put back
      let off = false;
      for (const [k, v] of Object.entries(before)) if (Array.isArray(f[k]) && f[k].length < v.length) { f[k] = v; off = true; }
      if (!off) n++;
      if (PT.cmd !== c) break;
    }
  } finally {
    PT.quiet = false;
    c.fmode = fm; c.emode = em;
  }
  PT.dirty = true;
  renderCommand(); drawSelection(); scheduleBuild();
  return n;
}

function selectShown() {
  const ap = activePick();
  if (!ap || !ap.multi) { msgPart("Select shown: in a command step that takes several elements", true); return; }
  const kinds = boxKinds(ap.kinds);
  const hits = boxCandidates(kinds).filter(shownCandidate).map(cd => cd.h);
  const n = addHits(hits);
  msgPart("Select shown: " + hits.length + " element(s) shown, " + n + " added");
  return n;
}

/** Elements in a screen rectangle (client px): all points inside (window) or any inside (crossing). */
function boxHits(xa, ya, xb, yb, crossing, shownOnly) {
  const ap = activePick();
  const t = PT.three, r = t.renderer.domElement.getBoundingClientRect(), v = new THREE.Vector3();
  const out = [];
  for (const cd of boxCandidates(boxKinds(ap.kinds))) {
    const step = Math.max(1, Math.ceil(cd.pts.length / 2000));
    let all = true, any = false;
    for (let i = 0; i < cd.pts.length; i += step) {
      const q = cd.pts[i];
      v.set(q[0], q[1], q[2]).project(t.camera);
      const x = r.left + (v.x + 1) / 2 * r.width, y = r.top + (1 - v.y) / 2 * r.height;
      const inside = x >= xa && x <= xb && y >= ya && y <= yb;
      if (inside) any = true; else all = false;
      if (crossing ? any : !all) break;
    }
    if ((crossing ? any : all) && (!shownOnly || shownCandidate(cd))) out.push(cd.h);
  }
  return out;
}

/** Ctrl + left drag in the view: box selection for the active step. Left to right: the elements entirely
 *  inside the box; right to left: the elements the box touches. A Ctrl click without a drag is a click. */
function boxStart(e) {
  const t = PT.three;
  e.stopPropagation();
  e.preventDefault();
  const r = t.box.getBoundingClientRect();
  const x0 = e.clientX, y0 = e.clientY;
  const el = document.createElement("div");
  el.className = "sel-box";
  el.hidden = true;
  t.box.appendChild(el);
  const move = ev => {
    const x1 = ev.clientX, y1 = ev.clientY;
    el.hidden = Math.abs(x1 - x0) + Math.abs(y1 - y0) < 4;
    el.classList.toggle("cross", x1 < x0);
    Object.assign(el.style, { left: Math.min(x0, x1) - r.left + "px", top: Math.min(y0, y1) - r.top + "px", width: Math.abs(x1 - x0) + "px", height: Math.abs(y1 - y0) + "px" });
  };
  const up = ev => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    el.remove();
    const x1 = ev.clientX, y1 = ev.clientY;
    if (Math.abs(x1 - x0) + Math.abs(y1 - y0) < 4) { clickView(ev); return; }
    const ap = activePick();
    if (!ap || !ap.multi) { msgPart("Box selection: in a command step that takes several elements", true); return; }
    const hits = boxHits(Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1), x1 < x0, !!PT.boxShown);
    const n = addHits(hits);
    msgPart("Box selection: " + hits.length + " element(s) " + (x1 < x0 ? "touched by the box" : "inside the box") + (PT.boxShown ? " (shown only)" : "") + ", " + n + " added");
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
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
  if (PT.quiet) return;
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

/** One build request at a time: a build asked for while one runs is made when it returns (with the part as it
 *  is then), so that the server does not run a build for every click. */
async function build() {
  if (PT.building) { PT.buildAgain = true; return; }
  PT.building = true;
  try { await buildNow(); } finally {
    PT.building = false;
    if (PT.buildAgain) { PT.buildAgain = false; build(); }
  }
}
/** Cancel: ends the geometry process on the server; the running build (or region computation) answers with
 *  "build cancelled" and the next request starts a new process (its build cache is empty). */
async function cancelBuild() {
  PT.cancelled = true;
  $("#pt-cancel").disabled = true;
  try { await postJSON("/api/part/cancel", {}); } catch (e) { showErr(e); }
  finally { $("#pt-cancel").disabled = false; }
}
function showBuilding(on) {
  const b = $("#pt-cancel");
  if (!b) return;
  clearTimeout(PT.cancelTimer);
  if (on) PT.cancelTimer = setTimeout(() => { b.hidden = false; }, 1500);     // after 1.5 s of building
  else b.hidden = true;
}
async function buildNow() {
  const seq = ++PT.buildSeq;
  $("#pt-info").textContent = "Building...";
  PT.cancelled = false;
  showBuilding(true);
  try {
    const upto = buildUpto();
    const uptoName = upto !== null && PT.cmd && feat(PT.cmd.id) ? feat(PT.cmd.id).name : "";
    const r = await postJSON("/api/part/build", { part: PT.part, upto });
    const j = await r.json();
    if (seq !== PT.buildSeq) return;
    if (PT.buildAgain) return;                  // the part changed while this build ran: the next build follows
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
  } catch (e) {
    if (seq === PT.buildSeq) {
      $("#pt-info").textContent = PT.cancelled || /cancelled/.test(e.message || "") ? "Build cancelled" : "";
      if (PT.cancelled || /cancelled/.test(e.message || "")) { PT.buildAgain = false; msgPart("Build cancelled: change or suppress the feature, then the part is built again", true); }
      else showErr(e);
    }
  } finally { if (seq === PT.buildSeq) showBuilding(false); }
}

function changedPart(rebuild) {
  PT.dirty = true;
  // the result of the edited feature is out of date until the next build returns
  if (rebuild !== false && PT.cmd && PT.status[PT.cmd.id]) PT.status[PT.cmd.id] = Object.assign({}, PT.status[PT.cmd.id], { pending: true });
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

/** Volume texts of the solids of a list in one unit: cm^3 when the largest is 1 cm^3 or more, else mm^3. */
function volTexts(vols) {
  const big = vols.some(v => Math.abs(v) >= 1000);
  return vols.map(v => big ? pfmt(v / 1000, Math.abs(v) >= 1000 ? 2 : 3) + " cm^3" : pfmt(v, Math.abs(v) >= 1 ? 3 : 6) + " mm^3");
}
/** Label of a solid in the body lists of the commands: colour mark, number and volume (one unit for the list). */
function solidLabel(i, vt) { return swatch("solid:" + i, COL.solid) + " Solid " + (i + 1) + " (" + vt[i] + ")"; }
/** Colour mark of a body in the tree: its colour (Properties) or the default colour of its kind. */
function swatch(id, dflt, curve) {
  const c = (PT.part.body_colors || {})[id] || "#" + new THREE.Color(dflt).getHexString();
  return curve ? `<span class="swatch" style="background:${c};height:3px;border:none;vertical-align:3px" title="Curve"></span>` : `<span class="swatch" style="background:${c}"></span>`;
}
/** Tree keys of the bodies: "solid:<i>" and the surface body feature ids. */
function bodyIds() {
  return [...PT.solids.map((_, i) => "solid:" + i), ...PT.part.features.filter(f => !f.suppressed && PT.surfaces[f.id]).map(f => f.id)];
}
/** Show only: every other solid and surface body hidden, this one shown. */
function showOnlyBody(id) {
  for (const k of bodyIds()) { if (k === id) delete PT.hidden[k]; else PT.hidden[k] = true; }
  renderTree(); renderProps(); setMesh(PT.mesh);
}
function showAllBodies() {
  for (const k of bodyIds()) delete PT.hidden[k];
  renderTree(); renderProps(); setMesh(PT.mesh);
}
/** Show menu: "all" / "none" / "invert" (the hidden bodies shown, the shown ones hidden) / "solids" / "surfaces"
 *  (that group shown, the other hidden) over the solids, surface and curve bodies. */
/** Opacity of the surface bodies (0.1 to 1; localStorage "pt-surf-opacity", default 0.45). */
function surfOpacity() {
  if (PT.surfOpacity === undefined) { let v = NaN; try { v = parseFloat(localStorage.getItem("pt-surf-opacity")); } catch (e) { /* default */ } PT.surfOpacity = isFinite(v) && v >= 0.1 && v <= 1 ? v : 0.45; }
  return PT.surfOpacity;
}
/** Sets the opacity of the surface bodies and applies it to the drawn ones (mesh bodies stay opaque). */
function setSurfOpacity(v) {
  v = Math.min(1, Math.max(0.1, +v || 0.45));
  PT.surfOpacity = v;
  try { localStorage.setItem("pt-surf-opacity", String(v)); } catch (e) { /* kept for this session */ }
  for (const o of PT.surfObjs || []) {
    if (!o.material || !(o.material instanceof THREE.MeshStandardMaterial)) continue;
    if (PT.status[o.userData.id] && PT.status[o.userData.id].mesh) continue;
    o.material.opacity = v; o.material.transparent = v < 1; o.material.depthWrite = v >= 1; o.material.needsUpdate = true;
  }
  const lbl = $("#pt-surfop-val"); if (lbl) lbl.textContent = Math.round(v * 100) + " %";
  render3();
}
function showBodies(mode) {
  const ids = bodyIds(), solids = new Set(bodyGroupIds("solid"));
  for (const k of ids) {
    const show = mode === "all" ? true : mode === "none" ? false : mode === "invert" ? !!PT.hidden[k] : mode === "solids" ? solids.has(k) : !solids.has(k);
    if (show) delete PT.hidden[k]; else PT.hidden[k] = true;
  }
  renderTree(); renderProps(); setMesh(PT.mesh);
  msgPart({ all: "All bodies shown", none: "All bodies hidden", invert: "Shown and hidden bodies swapped", solids: "Solids shown, surfaces hidden", surfaces: "Surfaces shown, solids hidden" }[mode]);
}
/** Tree keys of one group of bodies: "solid" (solids), "surface" (surface bodies), "curve" (curve bodies). */
function bodyGroupIds(grp) {
  if (grp === "solid") return PT.solids.map((_, i) => "solid:" + i);
  return PT.part.features.filter(f => !f.suppressed && PT.surfaces[f.id] && CURVE_TYPES.has(f.type) === (grp === "curve")).map(f => f.id);
}
/** Eye of a group header: hides every body of the group when any is shown, else shows them all. */
function toggleBodyGroup(grp) {
  const ids = bodyGroupIds(grp);
  const anyShown = ids.some(k => !PT.hidden[k]);
  for (const k of ids) { if (anyShown) PT.hidden[k] = true; else delete PT.hidden[k]; }
  renderTree(); renderProps(); setMesh(PT.mesh);
}

function renderTree() {
  const box = $("#pt-features");
  const fs = PT.part.features;
  const row = (id, icon, name, opts) => {
    const o = opts || {};
    const st = PT.status[id] || {};
    return `<div class="pt-feat${id === PT.sel ? " sel" : ""}${o.suppressed ? " supp" : ""}${o.cmd ? " editing" : ""}" data-id="${pesc(id)}">` +
      (o.toggle ? `<input type="checkbox" data-k="on" title="Active"${o.suppressed ? "" : " checked"}>` : `<span class="ico">${icon}</span>`) +
      `<span class="nm">${o.toggle ? `<span class="ico">${icon}</span> ` : ""}${pesc(name)}</span>` +
      `<span class="ops">` + (o.body ? `<button type="button" data-k="bcopy" title="Copy body">&#10697;</button><button type="button" data-k="bscale" title="Scale body">&#10530;</button><button type="button" data-k="bdel" title="Delete body (adds a Delete body feature)">&#10006;</button><button type="button" data-k="only" title="Show only this body">&#9673;</button>` : "") +
      (o.eye ? `<button type="button" data-k="eye" class="${PT.hidden[id] ? "off" : ""}" title="Show / hide">${EYE}</button>` : "") +
      (o.ops ? `<button type="button" data-k="up" title="Move up">&#9650;</button><button type="button" data-k="down" title="Move down">&#9660;</button><button type="button" data-k="del" title="Delete">&#10005;</button>` : "") + `</span>` +
      (st.error && !st.pending && o.ops ? `<span class="err">${pesc(st.error)}</span>` : "") + "</div>";
  };
  let h = `<div class="pt-sec">Reference planes</div>` + Object.entries(BASE_PLANES).map(([k, n]) => row(k, ICON.plane, n, { eye: true })).join("");
  h += `<div class="pt-sec pt-sech">Bodies${bodyIds().some(k => PT.hidden[k]) ? `<button type="button" id="pt-showall" title="Show all bodies">Show all</button>` : ""}</div>`;
  const nSolids = PT.solids.length;
  const surfs = fs.filter(f => !f.suppressed && PT.surfaces[f.id] && !CURVE_TYPES.has(f.type));
  const curves = fs.filter(f => !f.suppressed && PT.surfaces[f.id] && CURVE_TYPES.has(f.type));
  // sub-section header with an eye for the whole group: off (dimmed) when every body of the group is hidden
  const grpHead = (grp, name) => {
    const ids = bodyGroupIds(grp), allHidden = ids.length > 0 && ids.every(k => PT.hidden[k]);
    return `<div class="pt-sec pt-sub pt-sech">${name}<button type="button" data-grp="${grp}" class="${allHidden ? "off" : ""}" title="${allHidden ? "Show all " : "Hide all "}${name.toLowerCase()}">${EYE}</button></div>`;
  };
  if (nSolids || !surfs.length && !curves.length) h += grpHead("solid", "Solids");
  if (nSolids > 6 && !PT.showCells) h += `<div class="pt-feat" data-id="cells"><span class="ico">${ICON.solid}</span><span class="nm">${nSolids} solid cells</span><span class="ops"><button type="button" data-k="cells" title="List the cells">…</button></span></div>`;
  else for (let i = 0; i < nSolids; i++) h += row("solid:" + i, swatch("solid:" + i, COL.solid), "Solid " + (i + 1), { eye: true, body: true });
  if (surfs.length) h += grpHead("surface", "Surfaces");
  for (const f of surfs) h += row(f.id, swatch(f.id, (PT.status[f.id] || {}).mesh ? COL.mesh : COL.surf), f.name, { eye: true, body: true });
  if (curves.length) h += grpHead("curve", "Curves");
  for (const f of curves) h += row(f.id, swatch(f.id, COL.curve, true), f.name, { eye: true, body: true });
  if (!nSolids && !surfs.length && !curves.length) h += `<p class="hint">No body yet.</p>`;
  h += `<div class="pt-sec">Features</div>`;
  if (!fs.length) h += '<p class="hint">Sketch on a reference plane, then Extrude.</p>';
  for (const f of fs) {
    const icon = f.type === "sketch" ? ICON.sketch : f.type === "plane" ? ICON.plane : f.type === "point" ? ICON.point : f.type === "axis" ? ICON.axis : SURFACE_TYPES.has(f.type) ? (CURVE_TYPES.has(f.type) ? ICON.curve : ICON.surface) : ICON.feature;
    h += row(f.id, icon, f.name, { toggle: true, ops: true, suppressed: f.suppressed, eye: ["sketch", "plane", "point", "axis"].includes(f.type) || !!PT.surfaces[f.id], cmd: PT.cmd && PT.cmd.id === f.id });
  }
  box.innerHTML = h;
  if ($("#pt-showall")) $("#pt-showall").onclick = showAllBodies;
  box.querySelectorAll("[data-grp]").forEach(b => b.onclick = () => toggleBodyGroup(b.dataset.grp));
  box.querySelectorAll(".pt-feat").forEach(el => {
    const id = el.dataset.id;
    el.onclick = e => {
      const k = e.target.closest("[data-k]") && e.target.closest("[data-k]").dataset.k;
      const f = feat(id);
      const i = featIndex(id);
      if (k === "eye") { PT.hidden[id] = !PT.hidden[id]; renderTree(); setMesh(PT.mesh); return; }
      if (k === "only") { showOnlyBody(id); return; }
      if (k === "bcopy" || k === "bdel" || k === "bscale") { bodyCommand(k === "bcopy" ? "body_copy" : k === "bscale" ? "body_scale" : "body_delete", id); return; }
      if (id === "cells") { PT.showCells = !PT.showCells; renderTree(); return; }
      if (!k && PT.cmd) { const th = treeHit(id); if (th && feedCommand(th)) return; }
      if (!f) { selectItem(id); return; }
      if (k === "on") {
        f.suppressed = !e.target.checked;
        // a suppressed feature shows the bodies it consumed; an active one hides them again
        for (const sid of sourcesOf(f)) { if (f.suppressed) { if (!consumedBy(sid).length) delete PT.hidden[sid]; } else PT.hidden[sid] = true; }
        changedPart(); return;
      }
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
  const users = PT.part.features.filter(x => usesFeature(x, id));
  checkpointPart();
  if (PT.cmd && PT.cmd.id === id) PT.cmd = null;
  PT.part.features.splice(featIndex(id), 1);
  if (PT.sel === id) PT.sel = null;
  // the bodies the feature consumed (hidden when it was made) are shown again
  for (const sid of sourcesOf(f)) if (!consumedBy(sid).length) delete PT.hidden[sid];
  changedPart();
  msgPart("Deleted " + f.name + (users.length ? "; used by " + users.map(u => u.name).join(", ") : "") + " (Ctrl+Z undoes)", users.length > 0);
}
/** Whether feature x references the feature id (sketch, plane, source bodies, curves, points, axes, ...). */
function usesFeature(x, id) {
  const one = ["sketch_ref", "path_ref", "plane_ref", "source", "tool", "point_ref", "axis_ref", "plane_axis", "plane_point", "plane_origin_ref", "plane_xdir_ref", "source_a", "source_b", "target", "other", "profile", "path", "project", "plane_face_body", "plane"];
  const many = ["sources", "curves", "features", "points_ref", "planes_ref", "sketch_refs", "curves_a", "curves_b", "surfaces"];
  return one.some(k => x[k] === id) || many.some(k => (x[k] || []).includes(id)) || !!(x.plane_sketch_curve && x.plane_sketch_curve.sketch === id) ||
    (x.ends || []).some(e => e && (e.body === id || e.point === id));
}
/** The active (not suppressed) features that consume the body sid (it is hidden while one exists). */
function consumedBy(sid) { return PT.part.features.filter(x => !x.suppressed && consumedSources(x).includes(sid)); }

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
  const S = I.summary || {};
  const kinds = { gap: "Gaps", pointgap: "Vertex gaps", nonmanifold: "Non-manifold edges", free: "Free edges", smallface: "Small faces", smalledge: "Short edges", celledge: "Edges where cells meet" };
  const counts = {};
  for (const x of I.issues) counts[x.kind] = (counts[x.kind] || 0) + 1;
  let h = `<p><strong>Inspection: ${pesc(I.name)}</strong></p>` +
    `<p class="hint">${S.faces} faces, ${S.edges} edges, ${S.vertices} vertices, area ${pfmt(S.area, 1)} mm^2. ${S.free_edges} free edge(s), free length ${pfmt(S.free_length, 2)} mm. ` +
    `${S.shells} shell(s), ${S.closed_shells} closed. ${S.valid === null ? "" : S.valid ? "Topology valid." : "Topology invalid (BRepCheck)."}</p>` +
    `<p class="hint">${Object.entries(kinds).filter(([k]) => counts[k]).map(([k, n]) => n + " " + counts[k]).join(", ") || "No free edges, gaps, non-manifold edges, small faces or short edges."}</p>` +
    (counts.celledge ? `<p class="hint">The part is ${S.cells} cells (solids sharing faces). An edge where cells meet has two faces in each cell. Boolean, Union of the cells, makes one solid; Partition and the hexahedral mesh use the cells.</p>` : "") +
    `<div class="grid2"><label>Gap tolerance (mm)<input type="text" inputmode="decimal" class="numf" id="pi-gap" value="${INSPECT.gap_tol}"></label><label>Small face below (mm^2)<input type="text" inputmode="decimal" class="numf" id="pi-area" value="${INSPECT.min_area}"></label>` +
    `<label>Short edge below (mm)<input type="text" inputmode="decimal" class="numf" id="pi-edge" value="${INSPECT.min_edge}"></label><label class="check"><input type="checkbox" id="pi-all"${I.showAll ? " checked" : ""}> Show all in the view</label></div>` +
    `<div class="buttons"><button type="button" id="pi-run">Run again</button><button type="button" id="pi-close">Close</button>` +
    (counts.celledge && !I.body ? `<button type="button" id="pi-join" title="Adds Boolean (Union of all solids) and Merge faces at the end of the feature list">Join cells</button>` : "") + `</div>` +
    (I.issues.length ? `<ul class="check-list">${I.issues.map((x, i) => `<li><a href="#" data-ii="${i}"${i === I.active ? ' class="active"' : ""}>${pesc(x.text)}</a></li>`).join("")}</ul>` : "");
  box.innerHTML = h;
  const num = (id, k) => { const el = $(id); el.onchange = () => { const v = window.numv ? numv(el.value) : parseFloat(el.value); if (v > 0) INSPECT[k] = v; }; };
  num("#pi-gap", "gap_tol"); num("#pi-area", "min_area"); num("#pi-edge", "min_edge");
  $("#pi-all").onchange = () => { INSPECT.showAll = I.showAll = $("#pi-all").checked; drawSelection(); };
  $("#pi-run").onclick = () => inspectBody(I.body);
  $("#pi-close").onclick = () => { PT.inspect = null; renderProps(); drawSelection(); };
  if ($("#pi-join")) $("#pi-join").onclick = () => {
    // one solid from the cells: Boolean union of all solids, then the faces and edges left between them merged
    checkpointPart();
    const n = PT.solids.length;
    PT.part.features.push({ id: newId(), name: nextName("boolean"), type: "boolean", suppressed: false, op: "union", targets: [...Array(n).keys()], tools: [], keep_tools: false });
    PT.part.features.push({ id: newId(), name: nextName("unify"), type: "unify", suppressed: false, faces: true, edges: true, angle: 0 });
    PT.inspect = null;
    changedPart();
    status(`Boolean union of ${n} solids and Merge faces added; Inspect again after the rebuild`);
  };
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

// ------------------------------------------------------------------ shaded model under a feature sketch

/** The shaded model (the part built up to the sketch feature) drawn under the sketch editor: an orthographic view
 *  along the sketch plane normal, in sketch coordinates, that follows the pan and zoom of the sketch. With a cut
 *  ("front" or "back") the half of the model on one side of the sketch plane is clipped and the section is capped.
 *  model: {mesh, surfaces} of /api/part/build; frame: {o3, x3, y3, z3} of the sketch plane (3D, offset included);
 *  upto: the feature index (the cap is of the model up to it). */
function createSketchUnderlay(model, frame, upto) {
  const m = model.mesh;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.localClippingEnabled = true;
  const el = renderer.domElement;
  el.className = "sk-underlay";
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-100, 100, 100, -100, -1e6, 1e6);
  const o = new THREE.Vector3(...frame.o3), x = new THREE.Vector3(...frame.x3).normalize(), y = new THREE.Vector3(...frame.y3).normalize(), z = new THREE.Vector3(...frame.z3).normalize();
  camera.up.copy(y);
  camera.position.copy(o.clone().add(z.clone().multiplyScalar(1e4)));
  camera.lookAt(o);
  camera.updateMatrixWorld();
  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.75);
  d1.position.set(1, 1, 2);
  camera.add(d1);
  scene.add(camera);
  const group = new THREE.Group();
  scene.add(group);
  const clip = new THREE.Plane();
  let cut = null, capObj = null, visible = true, W = 0, H = 0, capSeq = 0, behind = "dim", isolate = false;
  const mats = [], backMats = [];
  // behind the sketch plane (local z below -tol): a copy of each mesh drawn at 10 % opacity ("dim"), or not drawn
  // ("hide"); Isolate: only a slab of +-tol around the plane
  const add = (obj, mat) => {
    group.add(obj);
    const bm = mat.clone();
    bm.transparent = true; bm.opacity = 0.1; bm.depthWrite = false;
    backMats.push(bm);
    const copy = new obj.constructor(obj.geometry, bm);
    copy.renderOrder = 3;
    group.add(copy);
  };
  // the solids
  if (m && m.vertices && m.vertices.length) {
    let nSolids = 0;
    for (const s of m.face_solid) if (s + 1 > nSolids) nSolids = s + 1;
    const solidFaces = Array.from({ length: nSolids }, () => new Set());
    m.face_solid.forEach((s, fi) => { if (s >= 0) solidFaces[s].add(fi); });
    for (let si = 0; si < nSolids; si++) {
      const mat = new THREE.MeshStandardMaterial({ color: bodyColor("solid:" + si, COL.solid), metalness: 0.15, roughness: 0.6, side: THREE.DoubleSide });
      mats.push(mat);
      add(new THREE.Mesh(facesGeometry(m, solidFaces[si]), mat), mat);
    }
  }
  // the surface and curve bodies
  for (const [id, sm] of Object.entries(model.surfaces || {})) {
    const f = feat(id);
    if (f && f.suppressed) continue;
    if (sm.triangles && sm.triangles.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(sm.vertices.flat(), 3));
      g.setIndex(sm.triangles.flat());
      g.computeVertexNormals();
      const isMesh = !!(PT.status[id] && PT.status[id].mesh);
      const op = isMesh ? 1 : surfOpacity();
      const mat = new THREE.MeshStandardMaterial({ color: bodyColor(id, isMesh ? COL.mesh : COL.surf), transparent: op < 1, opacity: op, side: THREE.DoubleSide, depthWrite: op >= 1, flatShading: isMesh, metalness: 0, roughness: isMesh ? 0.7 : 1 });
      mats.push(mat);
      const mesh = new THREE.Mesh(g, mat);
      mesh.renderOrder = 2;
      add(mesh, mat);
    } else if (sm.edges && sm.edges.length) {
      const pos = [];
      for (const pl of sm.edges) for (let k = 0; k + 1 < pl.length; k++) pos.push(...pl[k], ...pl[k + 1]);
      if (pos.length) {
        const eg = new THREE.BufferGeometry();
        eg.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
        const mat = new THREE.LineBasicMaterial({ color: COL.curve });
        mats.push(mat);
        add(new THREE.LineSegments(eg, mat), mat);
      }
    }
  }
  const render = () => { if (visible && W && H) renderer.render(scene, camera); };
  const bb = new THREE.Box3();
  group.traverse(ob => { if (ob.geometry) { ob.geometry.computeBoundingBox(); bb.union(ob.geometry.boundingBox); } });
  const tolZ = 1e-3 * (bb.isEmpty() ? 100 : bb.getSize(new THREE.Vector3()).length() || 100);
  const keepFront = new THREE.Plane(z.clone(), -z.dot(o) + tolZ), keepBack = new THREE.Plane(z.clone().negate(), z.dot(o) - tolZ);
  const slabTop = new THREE.Plane(z.clone().negate(), z.dot(o) + tolZ);
  const applyClip = () => {
    const c = cut ? [clip] : [];
    const front = isolate ? [...c, keepFront, slabTop] : behind === "show" ? c : [...c, keepFront];
    for (const mat of mats) { mat.clippingPlanes = front; mat.needsUpdate = true; }
    for (const bm of backMats) { bm.clippingPlanes = [...c, keepBack]; bm.visible = !isolate && behind === "dim"; bm.needsUpdate = true; }
  };
  applyClip();
  async function refreshCap() {
    if (capObj) { scene.remove(capObj); capObj = null; }
    if (!cut || !m || !m.vertices || !m.vertices.length) { render(); return; }
    const seq = ++capSeq;
    try {
      const r = await postJSON("/api/part/section", { part: PT.part, origin: o.toArray(), normal: z.toArray(), upto });
      const cm = await r.json();
      if (seq !== capSeq || !cut || !cm.vertices.length) { render(); return; }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(cm.vertices.flat(), 3));
      g.setIndex(cm.triangles.flat());
      g.computeVertexNormals();
      capObj = new THREE.Group();
      capObj.add(new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: 0x9aa3ad, metalness: 0.1, roughness: 0.7, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
      scene.add(capObj);
      render();
    } catch (e) { console.error(e); }
  }
  return {
    el,
    /** The canvas under the sketch's SVG (first child of the sketch canvas box). */
    attach(box) { if (el.parentNode !== box) box.insertBefore(el, box.firstChild); },
    /** The view of the sketch (SK.view: ox, oy, s; screen = (ox + s u, oy - s v)) and the size of the sketch box. */
    update(view, w, h) {
      if (!el.isConnected && el.parentNode) el.parentNode.insertBefore(el, el.parentNode.firstChild);
      if (w !== W || h !== H) { W = w; H = h; renderer.setSize(w, h); }
      if (!w || !h || !view.s) return;
      camera.left = -view.ox / view.s; camera.right = (w - view.ox) / view.s;
      camera.top = view.oy / view.s; camera.bottom = (view.oy - h) / view.s;
      camera.updateProjectionMatrix();
      render();
    },
    /** null: the whole model; "front": the half toward the viewer (along the plane normal) clipped; "back": the
     *  other half clipped. The cap of the section is read from the server. */
    setCut(mode) {
      cut = mode === "front" || mode === "back" ? mode : null;
      if (cut) clip.setFromNormalAndCoplanarPoint(z.clone().multiplyScalar(cut === "front" ? -1 : 1), o);
      applyClip();
      refreshCap();
    },
    setVisible(on) { visible = !!on; el.hidden = !visible; if (visible) render(); },
    /** The model behind the sketch plane: "dim" (10 % opacity), "hide" or "show". */
    setBehind(mode) { behind = ["dim", "hide", "show"].includes(mode) ? mode : "dim"; applyClip(); render(); },
    /** Isolate: only the model within the sketch plane (+-0.1 % of the model size). */
    setIsolate(on) { isolate = !!on; applyClip(); render(); },
    /** State for the tests. */
    state() { return { behind, isolate, cut, backVisible: backMats.some(b => b.visible), front: mats.map(x => (x.clippingPlanes || []).length) }; },
    dispose() {
      ++capSeq;
      if (el.parentNode) el.parentNode.removeChild(el);
      group.traverse(ob => { if (ob.geometry) ob.geometry.dispose(); });
      for (const mat of mats.concat(backMats)) mat.dispose();
      renderer.dispose();
    },
  };
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
  if (!PT.cmd && $("#pt-cmdwin")) $("#pt-cmdwin").hidden = true;
  if (PT.inspect && !PT.cmd) { renderInspect(); return; }
  if (PT.cmd && feat(PT.cmd.id)) { box.innerHTML = `<p class="hint">${pesc(feat(PT.cmd.id).name)} is open in the command window.</p>`; return; }
  const id = PT.sel;
  if (!id) { box.innerHTML = '<p class="hint">Click an element in the view or an item in the tree. Double-click a feature to edit its definition.</p>' + nextHtml(); bindNext(box); return; }
  if (BASE_PLANES[id]) { box.innerHTML = `<p><strong>${BASE_PLANES[id]}</strong></p><p class="hint">Reference plane through the origin. Sketches and planes can be placed on it.</p>` + nextHtml(); bindNext(box); return; }
  if (id.startsWith("solid:")) {
    const s = PT.solids[+id.slice(6)];
    box.innerHTML = `<p><strong>Solid ${+id.slice(6) + 1}</strong></p>` + (s ? `<p class="hint">Volume ${pfmt(s.volume_mm3 / 1000, 3)} cm^3, size ${pfmt(s.bbox[3] - s.bbox[0], 2)} x ${pfmt(s.bbox[4] - s.bbox[1], 2)} x ${pfmt(s.bbox[5] - s.bbox[2], 2)} mm</p>` : "") +
      colorRow(id, COL.solid) + `<div class="buttons"><button type="button" id="pp-inspect">Inspect</button><button type="button" id="pp-bcopy" title="Copy body feature with this solid">Copy body…</button><button type="button" id="pp-bscale" title="Scale body feature with this solid">Scale body…</button><button type="button" id="pp-only" title="Hide the other solids and surface bodies">Show only</button><button type="button" id="pp-showall">Show all</button><button type="button" id="pp-bdel" title="Delete body feature with this solid">Delete body</button></div>` + nextHtml();
    $("#pp-inspect").onclick = () => inspectBody(null);
    $("#pp-bcopy").onclick = () => bodyCommand("body_copy", id);
    $("#pp-bscale").onclick = () => bodyCommand("body_scale", id);
    $("#pp-only").onclick = () => showOnlyBody(id); $("#pp-showall").onclick = showAllBodies;
    $("#pp-bdel").onclick = () => bodyCommand("body_delete", id);
    bindColor(id); bindNext(box); return;
  }
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
    (PT.surfaces[id] && !(st.curve) ? `<button type="button" id="pp-inspect" title="Free edges, gaps, non-manifold edges, small faces and short edges of the surface body">Inspect</button>` : "") +
    (PT.surfaces[id] ? `<button type="button" id="pp-bcopy" title="Copy body feature with this body">Copy body…</button><button type="button" id="pp-bscale" title="Scale body feature with this body">Scale body…</button><button type="button" id="pp-only" title="Hide the other solids and surface bodies">Show only</button><button type="button" id="pp-showall">Show all</button><button type="button" id="pp-bdel" title="Delete body feature with this body">Delete body</button>` : "") + `</div>`;
  if (PT.surfaces[id] && !st.curve) h += colorRow(id, st.mesh ? COL.mesh : COL.surf);
  box.innerHTML = h + nextHtml();
  if ($("#pp-bcopy")) { $("#pp-bcopy").onclick = () => bodyCommand("body_copy", id); $("#pp-bscale").onclick = () => bodyCommand("body_scale", id); $("#pp-only").onclick = () => showOnlyBody(id); $("#pp-showall").onclick = showAllBodies; $("#pp-bdel").onclick = () => bodyCommand("body_delete", id); }
  bindColor(id);
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
  if (item.plane === "normal") {
    const sc = item.plane_sketch_curve, tEmpty = item.plane_t === null || item.plane_t === undefined;
    h += `<div class="grid2">` + num("pf-pt", sc ? "Position along the curve (0 to 1; empty: the nearer end)" : "Position along the edge (0 to 1)", sc ? (tEmpty ? "" : item.plane_t) : (tEmpty ? 0.5 : item.plane_t)) + `<label class="check bottom"><input type="checkbox" id="pf-pflip"${item.plane_flip ? " checked" : ""}> Flip the normal</label></div>` +
      `<p class="hint">${sc ? "Curve of " + pesc(itemName(sc.sketch)) + (tEmpty ? ", at the end nearer the click." : ".") : item.plane_edge ? "Edge of the solid picked." : item.plane_curve ? "Curve body " + itemName(item.plane_curve) + "." : "Click an edge, a curve body or a sketch curve in the view."}</p>`;
  }
  return h;
}
function bindPlaneSelect(box, item) {
  bindAll(box, {
    "#pf-plane": el => { const v = el.value; if (v.startsWith("datum:")) { item.plane = "datum"; item.plane_ref = v.slice(6); } else { item.plane = v; if (v === "normal" && item.plane_t === undefined) item.plane_t = 0.5; } },
    "#pf-offset": el => { item.offset = numv(el.value) || 0; },
    "#pf-pt": el => { const t = el.value.trim() === "" ? NaN : numv(el.value); item.plane_t = t >= 0 && t <= 1 ? t : (item.plane_sketch_curve ? null : 0.5); },
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
    // a face of the solid, or (h.surface) of a surface body
    item.plane = "face"; item.plane_face = refOf(h); item.plane_face_body = h.surface || null; item.offset = 0;
    // sketch x axis from the view: the principal direction nearest the screen right (the sketch opens as the face
    // is seen in the view); an x axis feature of the sketch is kept
    const k = h.surface ? ((PT.surfaces[h.surface] || {}).face_keys || [])[h.fi] : PT.mesh && PT.mesh.face_keys && PT.mesh.face_keys[h.fi];
    if (!item.plane_xdir_ref && k && k.n) { const xd = viewXdir(k.n); if (xd) item.plane_xdir = xd; }
  }
  else if (h.kind === "edge") { item.plane = "normal"; item.plane_edge = refOf(h); item.plane_curve = null; item.plane_axis = null; item.plane_sketch_curve = null; if (item.plane_t === undefined || item.plane_t === null) item.plane_t = 0.5; }
  else if (h.kind === "curve") { item.plane = "normal"; item.plane_curve = h.id; item.plane_edge = null; item.plane_axis = null; item.plane_sketch_curve = null; if (item.plane_t === undefined || item.plane_t === null) item.plane_t = 0.5; }
  else if (h.kind === "axis") { item.plane = "normal"; item.plane_axis = h.id; item.plane_edge = null; item.plane_curve = null; item.plane_sketch_curve = null; }
  else if (h.kind === "sketch" && h.id !== item.id) {
    // normal to the clicked curve chain of a sketch, at the end of the chain nearer the click
    item.plane = "normal"; item.plane_sketch_curve = { sketch: h.id, pick: (h.point || [0, 0, 0]).map(v => +(+v).toFixed(6)) };
    item.plane_edge = null; item.plane_curve = null; item.plane_axis = null; item.plane_t = null; item.offset = 0;
  }
  PT.dirty = true;
}
function planeSummary(item) {
  if (item.plane === "normal" && item.plane_axis) return "Normal to " + itemName(item.plane_axis) + (item.plane_point ? " at " + itemName(item.plane_point) : "");
  if (item.plane === "normal" && item.plane_sketch_curve) return "Normal to " + itemName(item.plane_sketch_curve.sketch) + (item.plane_t === null || item.plane_t === undefined ? " at the nearer end" : " at " + pfmt(item.plane_t, 2));
  if (item.plane === "normal") return "Normal to " + (item.plane_curve ? itemName(item.plane_curve) : "an edge") + " at " + pfmt(item.plane_t === undefined ? 0.5 : item.plane_t, 2);
  if (item.plane === "face") return "A planar face" + (item.offset ? ", offset " + pfmt(item.offset) + " mm" : "");
  return planeName(item.plane === "datum" ? item.plane_ref : item.plane) + (item.offset ? ", offset " + pfmt(item.offset) + " mm" : "");
}

const edgeModeHtml = f => `<div class="cw-modes" title="What a click in the view adds"><label class="check inline"><input type="radio" name="pf-emode" value="edge"${(PT.cmd.emode || "edge") === "edge" ? " checked" : ""}> Edge</label>` +
  `<label class="check inline"><input type="radio" name="pf-emode" value="tangent"${PT.cmd.emode === "tangent" ? " checked" : ""}> Tangent chain</label>` +
  `<label class="check inline"><input type="radio" name="pf-emode" value="face"${PT.cmd.emode === "face" ? " checked" : ""}> All edges of a face</label></div>`;
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
    html: f => edgeModeHtml(f),
    bind: (f, box) => bindEdgeMode(box),
    summary: f => (f[prop] || []).length + " edge(s)" };
}
function facesStep(label, prop, hint, single, sfaces) {
  return { key: prop, label, kinds: sfaces ? ["face", "sface"] : ["face"], prop, single: !!single, hint: hint || (single ? "Click the face." : "Click the faces (click again to deselect)."),
    html: f => single ? `<p class="hint">${f[prop] ? "1 face" : "No face"} selected.</p>` : "",
    summary: f => single ? (f[prop] ? "1 face" : "none") : (f[prop] || []).length + " face(s)" };
}
function sourceStep(label, prop, curves, hint) {
  return { key: prop, label, kinds: [curves === true ? "curve" : "surface"].concat(curves === undefined ? ["curve"] : []), prop, single: true,
    hint: hint || "Click a " + (curves === true ? "curve" : "surface") + " body in the view, or choose it.",
    html: f => sourceSelect("pf-" + prop, f, prop, false, curves === undefined ? undefined : curves),
    bind: (f, box) => bindAll(box, { ["#pf-" + prop]: el => { f[prop] = el.value || null; } }),
    summary: f => f[prop] ? itemName(f[prop]) : "none" };
}
/** Side A or B of Surface fillet: a surface body, or with Pick single faces some faces of one surface body (both
 *  sides can be faces of the same body, for example two separate sections of one Extract surface or Offset surface). */
function filletSideStep(k) {
  const K = k.toUpperCase(), prop = "source_" + k, fprop = "faces_" + k;
  // single faces: the pick of a surface body face comes as kind "face" with .surface (faces of the solid are refused)
  return { key: prop, label: "Surface " + K, multiFace: true, get kinds() { return PT.cmd && PT.cmd.sface ? ["sface", "face"] : ["surface"]; }, before: false,
    hint: `Click surface body ${K}, or choose it. To use separate sections of one body for A and B, tick Pick single faces and click the faces of side ${K} (click again to deselect).`,
    accept: (f, h) => {
      if (h.kind === "surface") { f[prop] = h.id; f[fprop] = []; }
      else if (h.kind === "face" && !h.surface) { msgPart("Click a face of a surface body", true); return; }
      else if (h.surface) {
        if (f[prop] !== h.surface) f[fprop] = [];
        f[prop] = h.surface; f[fprop] = f[fprop] || [];
        if (faceMode() !== "face" && h.key) { pickFaces(f, fprop, h, faceMode()); return; }
        const ref = refOf(h), i = f[fprop].findIndex(x => sameRef(x, ref));
        if (i >= 0) f[fprop].splice(i, 1); else f[fprop].push(ref);
      }
      PT.dirty = true;
    },
    html: f => sourceSelect("pf-" + prop, f, prop, false, false) + check("pf-sface" + k, "Pick single faces of surface bodies (sections of one body for A and B)", PT.cmd && PT.cmd.sface) +
      ((f[fprop] || []).length ? `<p class="hint">${f[fprop].length} face(s) of ${pesc(itemName(f[prop]))}.</p><div class="buttons"><button type="button" data-clear="${fprop}">Whole body</button></div>` : ""),
    bind: (f, box) => {
      bindAll(box, { ["#pf-" + prop]: el => { f[prop] = el.value || null; f[fprop] = []; } });
      const sf = box.querySelector("#pf-sface" + k); if (sf) sf.onchange = () => { PT.cmd.sface = sf.checked; renderCommand(); };
      box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f[fprop] = []; changedPart(); });
    },
    done: f => !!f[prop],
    summary: f => f[prop] ? itemName(f[prop]) + ((f[fprop] || []).length ? `, ${f[fprop].length} face(s)` : "") : "none" };
}
/** Source step taking a surface body or faces of the solid (sewn into one surface). */
function surfaceOrFacesStep(label, hint, before) {
  return { key: "source", label: label || "Surface", multiFace: true, get kinds() { return PT.cmd && PT.cmd.sface ? ["sface", "face"] : ["surface", "face"]; }, before: before === undefined ? false : before,
    hint: hint || "Click a surface body, or faces of the solid (click again to deselect a face); or choose a surface body. Single faces of surface bodies: tick the option.",
    accept: (f, h) => {
      if (h.kind === "surface") { f.source = h.id; f.faces = []; }
      else if (faceMode() !== "face" && h.key) { f.source = null; pickFaces(f, "faces", h, faceMode()); return; }
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

/** Surface bodies (feature ids) present before the feature f. */
function surfaceBodiesBefore(f) {
  const i = featIndex(f.id);
  return PT.part.features.filter((g, k) => (i < 0 || k < i) && !g.suppressed && PT.surfaces[g.id] && !(PT.status[g.id] && PT.status[g.id].curve)).map(g => g.id);
}
/** Step of Delete body and Copy body: solids ("bodies": indices before the feature) and surface bodies ("surfaces"). */
function bodyPickStep(label) {
  const tog = (arr, v) => { const i = arr.indexOf(v); if (i >= 0) arr.splice(i, 1); else arr.push(v); };
  return { key: "bodies", label, multi: true, kinds: ["body", "surface"], before: true,
    hint: "Click the solids and surface bodies (click again to deselect), or check them.",
    accept: (f, h) => { f.bodies = f.bodies || []; f.surfaces = f.surfaces || []; if (h.kind === "surface") tog(f.surfaces, h.id); else if (h.solid !== undefined) tog(f.bodies, h.solid); PT.dirty = true; },
    html: f => {
      const sel = new Set(f.bodies || []), ss = new Set(f.surfaces || []), sb = surfaceBodiesBefore(f);
      return (PT.solids.length ? PT.solids.map((s, i, a) => `<label class="check"><input type="checkbox" data-pbd="${i}"${sel.has(i) ? " checked" : ""}> ${solidLabel(i, volTexts(a.map(x => x.volume_mm3)))}</label>`).join("") : "") +
        sb.map(sid => `<label class="check"><input type="checkbox" data-pbsf="${pesc(sid)}"${ss.has(sid) ? " checked" : ""}> ${pesc(itemName(sid))}</label>`).join("") +
        (!PT.solids.length && !sb.length ? '<p class="hint">No bodies.</p>' : "") + `<p class="hint">Solids are numbered as in the tree before this feature.</p>`;
    },
    bind: (f, box) => box.querySelectorAll("input[data-pbd], input[data-pbsf]").forEach(cb => cb.onchange = () => {
      f.bodies = [...box.querySelectorAll("input[data-pbd]:checked")].map(x => +x.dataset.pbd);
      f.surfaces = [...box.querySelectorAll("input[data-pbsf]:checked")].map(x => x.dataset.pbsf); changedPart(); }),
    done: f => (f.bodies || []).length + (f.surfaces || []).length > 0,
    summary: f => [...(f.bodies || []).map(i => "Solid " + (i + 1)), ...(f.surfaces || []).map(itemName)].join(", ") || "none" };
}
/** Delete body (applied at once), Copy body (opens at the move vector) or Scale body (opens at the factor) for a body of the tree ("solid:<i>" or a
 *  surface body id), added at the end of the feature list. */
function bodyCommand(type, id) {
  const init = id.startsWith("solid:") ? { bodies: [+id.slice(6)], surfaces: [] } : { bodies: [], surfaces: [id] };
  if (PT.cmd) { if (canFinish(feat(PT.cmd.id))) finishCommand(true); else cancelCommand(); }
  checkpointPart();
  startCommand(type, init);
  if (type === "body_delete") finishCommand();
}

/** Tool axis of a moving-tool Sweep: a line of the profile sketch (clicked in the view or chosen), an axis feature,
 *  or the line through the centre of the profile normal to the path plane; and where the tool starts. */
function toolAxisStep() {
  const lines = f => { const sk = f.sketch_ref && feat(f.sketch_ref); return (((sk || {}).sketch || {}).entities || []).filter(e => e.t === "line" && !e.axis); };
  const atPath = f => (f.tool_at || ((f.axis || "auto") === "auto" && !f.axis_ref ? "path" : "drawn")) === "path";
  return { key: "tool_axis", label: "Tool axis", kinds: ["sketch", "axis"], single: true, before: false, axisPick: "all",
    hint: "Click a line of the profile sketch (the line under the cursor is highlighted) or an axis feature in the view, or choose the axis.",
    accept: (f, h) => acceptAxisPick(f, h, false),
    html: f => select("pf-saxis", "Tool axis", [["auto", "Through the centre of the profile, normal to the path plane"], ["u", "Sketch x axis (u)"], ["v", "Sketch y axis (v)"]]
        .concat(lines(f).map(e => [e.id, lineLabel(e)]))
        .concat(axisItems(featIndex(f.id)).map(a => ["ref:" + a.id, "Axis feature " + a.name])), f.axis_ref ? "ref:" + f.axis_ref : (f.axis || "auto")) +
      select("pf-stoolat", "Tool position", [["drawn", "As drawn: moved with the path from its start"], ["path", "Axis through the start of the path"]], atPath(f) ? "path" : "drawn"),
    bind: (f, box) => bindAll(box, { "#pf-saxis": el => { if (el.value.startsWith("ref:")) f.axis_ref = el.value.slice(4); else { f.axis = el.value; f.axis_ref = null; } },
      "#pf-stoolat": el => { f.tool_at = el.value; } }),
    done: () => true,
    summary: f => (f.axis_ref ? itemName(f.axis_ref) : (f.axis || "auto") === "auto" ? "profile centre" : f.axis === "u" ? "sketch x axis" : f.axis === "v" ? "sketch y axis" : "line " + f.axis) + (atPath(f) ? ", on the path" : ", as drawn") };
}
/** Optional step of Extrude, Cut, Revolve and Sweep: the solids the feature acts on (none: all solids). */
function bodiesStep() {
  return { key: "bodies", label: "Bodies", multi: true, kinds: ["body"], before: true, optional: true,
    hint: "Click the solids the feature acts on (click again to deselect), or check them; none: all solids.",
    accept: (f, h) => { f.bodies = f.bodies || []; const i = f.bodies.indexOf(h.solid); if (i >= 0) f.bodies.splice(i, 1); else f.bodies.push(h.solid); PT.dirty = true; },
    html: f => { const sel = new Set(f.bodies || []); return (PT.solids.length ? PT.solids.map((s, i, a) => `<label class="check"><input type="checkbox" data-pbs="${i}"${sel.has(i) ? " checked" : ""}> ${solidLabel(i, volTexts(a.map(x => x.volume_mm3)))}</label>`).join("") : '<p class="hint">No solids.</p>') + `<p class="hint">Solids are numbered as in the tree before this feature. Add material: fused with the checked solids only. Remove material: cut from the checked solids only. The other solids are not changed.</p>`; },
    bind: (f, box) => box.querySelectorAll("input[data-pbs]").forEach(cb => cb.onchange = () => { f.bodies = [...box.querySelectorAll("input[data-pbs]:checked")].map(x => +x.dataset.pbs); changedPart(); }),
    done: f => (f.bodies || []).length > 0, summary: f => (f.bodies || []).length ? f.bodies.map(i => "Solid " + (i + 1)).join(", ") : "all solids" };
}
function profileStep(prop, label) {
  return { key: prop || "sketch_ref", label: label || "Profile", kinds: ["sketch"], prop: prop || "sketch_ref", single: true, before: false,
    hint: "Click a sketch in the view, choose it, or draw a new one.",
    html: f => sketchField(f, prop || "sketch_ref", "Sketch"),
    bind: (f, box) => bindSketchField(box, f, prop || "sketch_ref"),
    summary: f => f[prop || "sketch_ref"] ? itemName(f[prop || "sketch_ref"]) : "none" };
}
const nameField = f => `<label>Name<input type="text" id="pf-name" value="${pesc(f.name)}"></label>`;
const resultLine = f => { const st = PT.status[f.id] || {}; if (st.pending) return pendingText(st); if (st.error) return `<p class="hint err">${pesc(st.error)}</p>`; if (st.faces !== undefined && st.faces_before !== undefined) return `<p class="hint">Result: ${st.faces_before} → ${st.faces} faces, ${st.edges_before} → ${st.edges} edges${st.note ? ". " + pesc(st.note) : ""}</p>`; if (st.note) return `<p class="hint">${pesc(st.note)}</p>`; return ""; };

const COMMANDS = {
  body_delete: { title: "Delete body",
    defaults: init => ({ bodies: (init && init.bodies) || [], surfaces: (init && init.surfaces) || [] }),
    steps: f => { const b = bodyPickStep("Bodies to delete"); b.done = f => (f.bodies || []).length + (f.surfaces || []).length > 0 || f.min_volume > 0 || f.min_thickness > 0;
      return [b, { key: "small", label: "Small solids", optional: true, hint: "Solids below a volume or a mean thickness are deleted too.",
        html: f => `<div class="grid2">` + num("pf-dminv", "Volume below (mm^3)", f.min_volume || 0) + num("pf-dmint", "Mean thickness below (mm)", f.min_thickness || 0) + `</div>` +
          `<p class="hint">Mean thickness: 2 x volume / area. 0: not used.</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-dminv": el => { f.min_volume = Math.max(0, numv(el.value) || 0); }, "#pf-dmint": el => { f.min_thickness = Math.max(0, numv(el.value) || 0); } }),
        summary: f => (f.min_volume > 0 || f.min_thickness > 0) ? [f.min_volume > 0 ? "< " + pfmt(f.min_volume) + " mm^3" : "", f.min_thickness > 0 ? "thinner than " + pfmt(f.min_thickness) + " mm" : ""].filter(Boolean).join(", ") : "none" }]; } },
  body_copy: { title: "Copy body",
    defaults: init => ({ bodies: (init && init.bodies) || [], surfaces: (init && init.surfaces) || [], move: [0, 0, 0] }),
    steps: f => [bodyPickStep("Bodies to copy"),
      { key: "move", label: "Move", hint: "Move vector of the copies (mm).", html: f => v3("pf-bmove", "Move vector (mm)", f.move || [0, 0, 0]) + `<p class="hint">The copied solids are new solids; the copied surface bodies are one surface body of this feature.</p>`,
        bind: (f, box) => bind3(box, "pf-bmove", v => { f.move = v; }), summary: f => "(" + (f.move || [0, 0, 0]).map(v => pfmt(v, 2)).join(", ") + ") mm" }] },
  body_scale: { title: "Scale body",
    defaults: init => ({ bodies: (init && init.bodies) || [], surfaces: (init && init.surfaces) || [], uniform: true, factor: 1, factors: [1, 1, 1], about: "origin", point: [0, 0, 0], point_ref: null, copy: false }),
    steps: f => {
      const steps = [bodyPickStep("Bodies to scale"),
        { key: "factor", label: "Scale", hint: "Scale factor, or factors along X, Y and Z, and the reference point.",
          html: f => check("pf-suni", "Uniform", f.uniform !== false) +
            (f.uniform !== false ? num("pf-sfac", "Factor", f.factor != null ? f.factor : 1) : v3("pf-sfacs", "Factors along X, Y, Z", f.factors || [1, 1, 1]) + `<p class="hint">Different factors convert the faces to B-spline surfaces.</p>`) +
            select("pf-sabout", "Reference point", [["origin", "Origin"], ["centroid", "Centre of mass of the selection"], ["bbox", "Bounding box centre of the selection"], ["point", "Point"]], f.about || "origin") +
            (f.about === "point" && !f.point_ref ? v3("pf-spt", "Point (mm, when no point feature or vertex is picked)", f.point || [0, 0, 0]) : "") +
            check("pf-scopy", "Copy (keep the original bodies)", !!f.copy) +
            `<p class="hint">${f.copy ? "The scaled solids are new solids; the scaled surface bodies are one surface body of this feature." : "The scaled bodies take the place of the originals."}</p>` + resultLine(f),
          bind: (f, box) => { bindAll(box, { "#pf-suni": el => { f.uniform = el.checked; }, "#pf-sfac": el => { f.factor = numv(el.value); }, "#pf-sabout": el => { f.about = el.value; }, "#pf-scopy": el => { f.copy = el.checked; } });
            bind3(box, "pf-sfacs", v => { f.factors = v; }); bind3(box, "pf-spt", v => { f.point = v; }); },
          done: f => f.uniform !== false ? f.factor > 0 : (f.factors || []).every(v => v > 0),
          summary: f => (f.uniform !== false ? pfmt(f.factor != null ? f.factor : 1, 4) : "(" + (f.factors || [1, 1, 1]).map(v => pfmt(v, 4)).join(", ") + ")") + " about " +
            ({ origin: "origin", centroid: "centre of mass", bbox: "bounding box centre", point: f.point_ref ? itemName(f.point_ref) : "(" + (f.point || [0, 0, 0]).map(v => pfmt(v, 2)).join(", ") + ") mm" })[f.about || "origin"] + (f.copy ? ", copy" : "") }];
      if (f.about === "point") { const d = datumStep("point", "Point", "point_ref", "Click a point feature or a vertex of the part (none: the coordinates in Scale).", true); steps.push(d); }
      return steps;
    } },
  sketch: {
    title: "Sketch", startStep: 0,
    defaults: init => ({ plane: (init && init.plane) || "XY", offset: 0, sketch: emptySketch() }),
    steps: f => [{ key: "plane", label: "Plane", kinds: ["plane", "face", "sface", "edge", "curve", "axis", "sketch"], before: false, hint: "Click a reference plane, a plane feature, a planar face (of the solid or of a surface body), an edge, a curve or an axis feature (plane normal to it), or a curve of a sketch (plane normal to it at the end nearer the click). Double-click opens the sketch editor on it.",
      accept: acceptPlanePick, html: planeSelectField, bind: (f, box) => bindPlaneSelect(box, f), done: f => !!f.plane && (f.plane !== "normal" || f.plane_edge || f.plane_curve || f.plane_axis), summary: planeSummary },
      { key: "origin", label: "Origin and x axis", kinds: ["edge", "face", "point", "axis", "sketch"], optional: true, before: false, hint: "Click an edge: the sketch origin goes to its nearer end and the sketch x axis along it. Click a curve of an earlier sketch: the origin goes to its nearer end. Click a face: the origin goes to its centre. Click a point feature: the origin. Click an axis feature: the sketch x axis. Nothing clicked: the plane origin.",
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
          else if (h.kind === "sketch") {
            // the end of the clicked curve of an earlier sketch nearer the click (ends of its polylines in 3D)
            const item = feat(h.id);
            if (!item || item.type !== "sketch" || !h.point) return;
            const d = q => Math.hypot(q[0] - h.point[0], q[1] - h.point[1], q[2] - h.point[2]);
            let best = null;
            for (const e of (item.sketch || {}).entities || []) {
              if (e.axis || e.t === "point") continue;
              for (const pl of sketchPolylines({ entities: [e] })) for (const q of [pl[0], pl[pl.length - 1]]) { const p = to3(item, q[0], q[1]); if (!best || d(p) < d(best)) best = p; }
            }
            if (!best) { msgPart("The sketch has no curve", true); return; }
            f.plane_origin = best; delete f.plane_origin_ref;
          }
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
        { key: "features", label: "Features", multi: true, kinds: ["face"], before: false, hint: "Click a face of each feature to mirror (click again to deselect), or check the features. Sketch features and holes only.",
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
      summary: f => pfmt(f.depth) + " mm" + (f.symmetric ? ", symmetric" : f.reverse ? ", reversed" : "") + (f.new_body ? ", new body" : "") }].concat(f.new_body ? [] : [bodiesStep()]),
  },
  cut: {
    title: "Cut", needsSolid: true,
    defaults: () => ({ sketch_ref: null, depth: 10, through: true, symmetric: false, reverse: false }),
    steps: f => [profileStep(), regionsStep(), { key: "extent", label: "Extent", html: f => select("pf-type", "Type", [["through", "Through all (both directions)"], ["finite", "Finite depth"]], f.through ? "through" : "finite") +
        (f.through ? "" : `<div class="grid2">` + num("pf-depth", "Depth (mm)", f.depth) + select("pf-dir", "Direction", [["normal", "Along the normal"], ["reverse", "Against the normal"], ["symmetric", "Symmetric to the plane"]], f.symmetric ? "symmetric" : f.reverse ? "reverse" : "normal") + `</div>`),
      bind: (f, box) => bindAll(box, { "#pf-type": el => { f.through = el.value === "through"; }, "#pf-depth": el => { const v = numv(el.value); if (v > 0) f.depth = v; }, "#pf-dir": el => { f.symmetric = el.value === "symmetric"; f.reverse = el.value === "reverse"; } }),
      summary: f => f.through ? "through all" : pfmt(f.depth) + " mm" + (f.symmetric ? ", symmetric" : f.reverse ? ", reversed" : "") }, bodiesStep()],
  },
  revolve: {
    title: "Revolve",
    defaults: () => ({ sketch_ref: null, angle: 360, axis: "v", mode: "add" }),
    steps: f => {
      const sk = f.sketch_ref && feat(f.sketch_ref);
      const axes = (((sk || {}).sketch || {}).entities || []).filter(e => e.t === "line" && e.constr && !e.axis);
      return [profileStep(), regionsStep(), { key: "axis", label: "Axis and extent", kinds: ["sketch", "axis"], before: false, axisPick: "constr", hint: "Click a construction line of the profile sketch (the line under the cursor is highlighted) or an axis feature in the view, or choose the axis.",
        accept: (f, h) => acceptAxisPick(f, h, true),
        html: f => select("pf-axis", "Axis", [["u", "Sketch x axis (u)"], ["v", "Sketch y axis (v)"]].concat(axes.map(e => [e.id, lineLabel(e)])).concat(axisItems(featIndex(f.id)).map(a => ["ref:" + a.id, "Axis feature " + a.name])), f.axis_ref ? "ref:" + f.axis_ref : (f.axis || "v")) +
          `<div class="grid2">` + num("pf-angle", "Angle (deg)", f.angle) + select("pf-mode", "Mode", [["add", "Add material"], ["cut", "Remove material"]], f.mode || "add") + `</div>` + check("pf-newbody", "New body (not fused with the part; combine later with Boolean)", f.new_body) + `<p class="hint">A construction line drawn in the sketch can be the axis.</p>`,
        bind: (f, box) => bindAll(box, { "#pf-axis": el => { if (el.value.startsWith("ref:")) f.axis_ref = el.value.slice(4); else { f.axis = el.value; f.axis_ref = null; } }, "#pf-angle": el => { const v = numv(el.value); if (v > 0 && v <= 360) f.angle = v; }, "#pf-mode": el => { f.mode = el.value; }, "#pf-newbody": el => { f.new_body = el.checked; } }),
        summary: f => pfmt(f.angle) + " deg about " + (f.axis === "u" ? "x" : f.axis === "v" ? "y" : f.axis) + (f.mode === "cut" ? ", remove" : "") }].concat(f.new_body && f.mode !== "cut" ? [] : [bodiesStep()]);
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
    defaults: () => ({ sketch_ref: null, path_ref: null, path_source: null, mode: "add", kind: "profile" }),
    steps: f => [profileStep(), { key: "path", label: "Path", kinds: ["sketch", "curve"], single: true, before: false, hint: "Click the path sketch or a curve body.",
        accept: (f, h) => { if (h.kind === "sketch") { f.path_ref = h.id; f.path_source = null; } else { f.path_source = h.id; f.path_ref = null; } PT.dirty = true; },
        html: f => sketchField(f, "path_ref", "Path sketch") + sourceSelect("pf-path_source", f, "path_source", false, true).replace("Curve<", "Or a curve body<"),
        bind: (f, box) => { bindSketchField(box, f, "path_ref"); bindAll(box, { "#pf-path_source": el => { f.path_source = el.value || null; if (el.value) f.path_ref = null; } }); },
        done: f => !!(f.path_ref || f.path_source), summary: f => f.path_ref ? itemName(f.path_ref) : f.path_source ? itemName(f.path_source) : "none" },
      { key: "mode", label: "Mode", html: f => {
          const tool = f.kind === "tool";
          return select("pf-skind", "Sweep", [["profile", "Profile swept along the path"], ["tool", "Moving tool: the profile revolved about its axis"]], f.kind || "profile") +
            select("pf-mode", "Mode", [["add", "Add material"], ["cut", "Remove material"]], f.mode || "add") + check("pf-newbody", "New body (not fused with the part; combine later with Boolean)", f.new_body) +
            `<p class="hint">${tool ? "The profile revolved about the tool axis is a tool (for example a V-bit or an end mill) moved along the path without turning; the tool axis is normal to the path plane. Corners of the path tighter than the tool are filled as the tool would cut them." :
              "The profile is swept along the path (one connected chain); the profile plane should be normal to the path at its start. A profile wider than the radius of a path corner intersects itself there: use the moving tool."}</p>`;
        },
        bind: (f, box) => bindAll(box, { "#pf-skind": el => { f.kind = el.value; if (el.value === "tool" && !f.axis) f.axis = "auto"; },
          "#pf-mode": el => { f.mode = el.value; }, "#pf-newbody": el => { f.new_body = el.checked; } }),
        summary: f => (f.kind === "tool" ? "moving tool, " : "") + (f.mode === "cut" ? "remove material" : "add material") + (f.new_body ? ", new body" : "") }]
      .concat(f.kind === "tool" ? [toolAxisStep()] : [])
      .concat(f.new_body && f.mode !== "cut" ? [] : [bodiesStep()]),
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
        html: f => { const sel = new Set(f[key] || []); return (PT.solids.length ? PT.solids.map((s, i, a) => `<label class="check"><input type="checkbox" data-ps="${i}"${sel.has(i) ? " checked" : ""}> ${solidLabel(i, volTexts(a.map(x => x.volume_mm3)))}</label>`).join("") : '<p class="hint">No solids.</p>') + `<p class="hint">Solids are numbered as in the tree before this feature.</p>`; },
        bind: (f, box) => box.querySelectorAll("input[data-ps]").forEach(cb => cb.onchange = () => { f[key] = [...box.querySelectorAll("input[data-ps]:checked")].map(x => +x.dataset.ps); changedPart(); }),
        done: f => (f[key] || []).length > 0, summary: f => (f[key] || []).length ? (f[key] || []).map(i => "Solid " + (i + 1)).join(", ") : "none" });
      const steps = [{ key: "op", label: "Operation", html: f => select("pf-bop", "Operation", [["union", "Union (fuse)"], ["subtract", "Subtract (target minus tools)"], ["intersect", "Intersect (common volume)"]], f.op || "subtract") + (f.op !== "union" ? check("pf-bkeep", "Keep the tool solids", f.keep_tools) : "") +
          `<div class="grid2">` + num("pf-bfuzzy", "Fuzzy value (mm, 0: exact)", f.fuzzy || 0) + `<span></span></div>` +
          `<p class="hint">Faces, edges and vertices of the target and the tools closer than the fuzzy value are taken as coincident. A tool whose faces lie a hair inside or outside faces of the target leaves thin lips along those faces: a fuzzy value above that distance (0.05 to 0.2 mm) removes them.</p>` +
          `<div class="grid2">` + num("pf-bmint", "Sliver thickness (mm)", f.min_thickness != null ? f.min_thickness : 0.01) + num("pf-bminv", "Sliver volume (mm^3)", f.min_volume || 0) + `</div>` +
          check("pf-bkeeps", "Keep sliver solids", !!f.keep_slivers) +
          `<p class="hint">Result solids with a mean thickness (2 x volume / area) below the sliver thickness or a volume below the sliver volume are slivers: the Boolean is made again with a fuzzy value of the sliver thickness, and the slivers left are removed.</p>` +
          `<p class="hint">Separate solids come from Extrude, Revolve or Sweep with New body, from Partition or from an imported STEP file.</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-bop": el => { f.op = el.value; }, "#pf-bkeep": el => { f.keep_tools = el.checked; }, "#pf-bfuzzy": el => { f.fuzzy = Math.max(0, numv(el.value) || 0); }, "#pf-bmint": el => { f.min_thickness = Math.max(0, numv(el.value) || 0); }, "#pf-bminv": el => { f.min_volume = Math.max(0, numv(el.value) || 0); }, "#pf-bkeeps": el => { f.keep_slivers = el.checked; } }),
        summary: f => ({ union: "union", subtract: "subtract", intersect: "intersect" })[f.op || "subtract"] + (f.keep_tools && f.op !== "union" ? ", tools kept" : "") },
        solidStep("targets", f.op === "union" ? "Solids" : "Target", f.op === "union" ? "Click each solid to fuse (click again to deselect), or check them." : "Click the target solid(s) (click again to deselect), or check them.")];
      if (f.op !== "union") steps.push(solidStep("tools", "Tools", "Click the tool solid(s), or check them."));
      else steps[1].done = f => (f.targets || []).length + (f.tools || []).length >= 2;
      return steps;
    },
  },
  split: {
    title: "Partition", needsSolid: true, startStep: 0,
    defaults: () => ({ method: "principal", plane: "XY", offset: 0, relative: false, point: [0, 0, 0], normal: [0, 0, 1], points: [[0, 0, 0], [1, 0, 0], [0, 1, 0]], face: null, edge: null, curve: null, t: 0.5, cells: [], extend: 1 }),
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
      if (m === "surface") { const st = sourceStep("Surface", "source", false, "Click the surface body that cuts the cells.");
        const h0 = st.html; st.html = f => h0(f) + `<div class="grid2">` + num("pf-sext", "Extend the surface beyond its edges (mm, 0: as it is)", f.extend === undefined ? 1 : f.extend) + `<span></span></div>` +
          `<p class="hint">The faces of the surface body are extended across their free edges by this distance before the cut, so the surface need not reach the faces of the cell exactly.</p>`;
        const b0 = st.bind; st.bind = (f, box) => { b0(f, box); bindAll(box, { "#pf-sext": el => { const v = numv(el.value); f.extend = v >= 0 ? v : 0; } }); };
        steps.push(st); }
      if (m !== "ogrid") steps.push({ key: "cells", label: "Cells", kinds: ["body"], multi: true, before: true, optional: true,
        hint: "Click each cell (solid) to partition (click again to deselect), or check them; none: all cells.",
        accept: (f, h) => { f.cells = (f.cells || []).filter(r => r && "solid" in r); const i = f.cells.findIndex(r => r.solid === h.solid); if (i >= 0) f.cells.splice(i, 1); else f.cells.push({ solid: h.solid }); PT.dirty = true; },
        html: f => { const sel = new Set((f.cells || []).filter(r => r && "solid" in r).map(r => r.solid)); const old = (f.cells || []).filter(r => r && !("solid" in r)).length;
          return (PT.solids.length ? PT.solids.map((s, i, a) => `<label class="check"><input type="checkbox" data-pc="${i}"${sel.has(i) ? " checked" : ""}> ${solidLabel(i, volTexts(a.map(x => x.volume_mm3)))}</label>`).join("") : '<p class="hint">No solids.</p>') +
            (old ? `<p class="hint">${old} cell(s) picked by face (older part); a click here replaces them.</p>` : "") + `<p class="hint">Solids are numbered as in the tree before this feature.</p>`; },
        bind: (f, box) => box.querySelectorAll("input[data-pc]").forEach(cb => cb.onchange = () => { f.cells = [...box.querySelectorAll("input[data-pc]:checked")].map(x => ({ solid: +x.dataset.pc })); changedPart(); }),
        done: () => true, summary: f => (f.cells || []).length ? (f.cells || []).length + " cell(s)" : "all cells" });
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
    defaults: () => ({ source: null, faces: [], with: "surface", tool: null, tool_faces: [], keep: "pick", remove: [], extend: 3, extend_far: false, min_area: 0.5, grouping: "connected" }),
    steps: f => [
      { key: "source", label: "Target", multiFace: true, get kinds() { return PT.cmd && PT.cmd.sface ? ["sface", "face"] : ["surface"]; }, before: false,
        hint: "Click the surface body to trim, or choose it. To trim a part of a body, tick Pick single faces and click its faces (click again to deselect); faces of the solid are trimmed as a new surface.",
        accept: (f, h) => {
          if (h.kind === "surface") { f.source = h.id; f.faces = []; }
          else if (h.kind === "face" && h.surface) { if (f.source !== h.surface) f.faces = []; f.source = h.surface; f.faces = f.faces || []; const ref = refOf(h), i = f.faces.findIndex(x => sameRef(x, ref)); if (i >= 0) f.faces.splice(i, 1); else f.faces.push(ref); }
          else if (h.kind === "face") { if (f.source) f.faces = []; f.source = null; f.faces = f.faces || []; const ref = refOf(h), i = f.faces.findIndex(x => sameRef(x, ref)); if (i >= 0) f.faces.splice(i, 1); else f.faces.push(ref); }
          f.remove = []; PT.cmd.regions = null; PT.dirty = true;
        },
        html: f => sourceSelect("pf-source", f, "source", false, false) + check("pf-sface", "Pick single faces of surface bodies (a part of a body as target or tool)", PT.cmd && PT.cmd.sface) +
          ((f.faces || []).length ? `<p class="hint">${f.faces.length} face(s) of ${f.source ? pesc(itemName(f.source)) : "the solid"}.</p><div class="buttons"><button type="button" data-clear="faces">Whole body</button></div>` : ""),
        bind: (f, box) => { bindAll(box, { "#pf-source": el => { f.source = el.value || null; f.faces = []; f.remove = []; PT.cmd.regions = null; } }); const sf = box.querySelector("#pf-sface"); if (sf) sf.onchange = () => { PT.cmd.sface = sf.checked; renderCommand(); };
          box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.faces = []; f.remove = []; PT.cmd.regions = null; changedPart(); }); },
        done: f => !!f.source || (f.faces || []).length > 0,
        summary: f => (f.source ? itemName(f.source) : (f.faces || []).length ? "the solid" : "none") + ((f.faces || []).length ? `, ${f.faces.length} face(s)` : "") },
      { key: "tool", label: "Tool", get kinds() { return (PT.cmd && PT.cmd.sface ? ["sface", "face"] : ["surface"]).concat(["curve", "sketch", "body", "plane"]); }, single: true, before: false,
        hint: "Click the tool: a surface body, a curve body or a sketch (projected onto the target), the solid, or a plane. With Pick single faces ticked (Target step), click faces of a surface body to use only those as the tool.",
        accept: (f, h) => { if (h.id && h.id === f.source && !(h.kind === "face" && h.surface)) { msgPart("The tool must differ from the target", true); return; }
          if (h.kind === "face" && h.surface) { if (f.tool !== h.surface || f.with !== "surface") f.tool_faces = []; f.with = "surface"; f.tool = h.surface; f.tool_faces = f.tool_faces || []; const ref = refOf(h), i = f.tool_faces.findIndex(x => sameRef(x, ref)); if (i >= 0) f.tool_faces.splice(i, 1); else f.tool_faces.push(ref); }
          else if (h.kind === "face") { msgPart("Click a face of a surface body, or the solid as a whole", true); return; }
          else if (h.kind === "body") { f.with = "solid"; f.tool = null; f.tool_faces = []; } else if (h.kind === "plane") { f.with = "plane"; f.tool = h.id; f.tool_faces = []; } else { f.with = h.kind === "curve" ? "curve" : h.kind === "sketch" ? "sketch" : "surface"; f.tool = h.id; f.tool_faces = []; } f.remove = []; PT.cmd.regions = null; PT.dirty = true; },
        html: f => `<p class="hint">${f.with === "solid" ? "The solid." : f.with === "plane" ? "Plane " + planeName(f.tool) + "." : f.tool ? itemName(f.tool) + ((f.tool_faces || []).length ? `, ${f.tool_faces.length} face(s)` : "") + "." : "No tool yet."}</p>` +
          ((f.tool_faces || []).length ? `<div class="buttons"><button type="button" data-clear="tool_faces">Whole body</button></div>` : "") +
          (f.with === "surface" && f.tool && !CURVE_TYPES.has((feat(f.tool) || {}).type) ? check("pf-tmutual", "Mutual: the tool is trimmed by the target too; the kept pieces of both are sewn into one body", !!f.mutual) +
            `<div class="grid2">` + num("pf-text", "Extend the tool (mm, 0: off)", f.extend === undefined ? 3 : f.extend) + `<label class="check bottom"><input type="checkbox" id="pf-textfar"${f.extend_far ? " checked" : ""}> Extend across the whole target if that does not cut</label></div>` +
            `<p class="hint">A tool that does not reach across the target is extended beyond its edges by this distance before the cut.</p>` : ""),
        bind: (f, box) => { bindAll(box, { "#pf-tmutual": el => { f.mutual = el.checked; f.remove = []; PT.cmd.regions = null; }, "#pf-text": el => { const v = numv(el.value); if (v >= 0) { f.extend = v; f.remove = []; PT.cmd.regions = null; } }, "#pf-textfar": el => { f.extend_far = el.checked; f.remove = []; PT.cmd.regions = null; } });
          box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.tool_faces = []; f.remove = []; PT.cmd.regions = null; changedPart(); }); },
        done: f => f.with === "solid" || !!f.tool, summary: f => (f.with === "solid" ? "the solid" : f.with === "plane" ? planeName(f.tool) : f.tool ? itemName(f.tool) + ((f.tool_faces || []).length ? `, ${f.tool_faces.length} face(s)` : "") : "none") + (f.mutual && f.with === "surface" ? ", mutual" : "") },
      { key: "regions", label: "Regions", multi: true, kinds: ["region"], before: true, hint: "Click the regions to remove (click again to keep them). Invert swaps kept and removed.",
        enter: f => { if (f.source && (f.with === "solid" || f.tool)) loadRegions(f); },
        accept: (f, h) => { f.keep = "pick"; f.remove = f.remove || []; const i = f.remove.findIndex(p => p.join(",") === h.point.join(",")); if (i >= 0) f.remove.splice(i, 1); else f.remove.push(h.point); PT.dirty = true; drawRegions(); },
        html: f => { const n = (PT.cmd.regions || []).length; return `<p class="hint${PT.cmd.regionError ? " err" : ""}">${PT.cmd.regionError ? pesc(PT.cmd.regionError) : n ? n + " region(s), " + (f.remove || []).length + " removed." : "Computing the regions..."}</p><div class="buttons"><button type="button" id="pf-invert">Invert</button><button type="button" id="pf-keepall">Keep all</button></div>` +
          `<div class="grid2">` + select("pf-tregs", "Regions", [["connected", "Connected pieces (joined across edges off the cut)"], ["faces", "Faces: every piece of the cut on its own"]], f.grouping || "connected") +
          num("pf-tmina", "Drop pieces smaller than (mm^2)", f.min_area === undefined ? 0.5 : f.min_area) + `</div><p class="hint">Faces: a section of the body joined to its neighbour through an edge can be removed alone. Pieces below the area (whiskers and slivers at the ends of a cut) are removed and not offered as regions.</p>`; },
        bind: (f, box) => { const b = box.querySelector("#pf-invert"); if (b) b.onclick = () => { const all = (PT.cmd.regions || []).map(r => r.point); const rem = new Set((f.remove || []).map(p => p.join(","))); f.remove = all.filter(p => !rem.has(p.join(","))); f.keep = "pick"; changedPart(); };
          const k = box.querySelector("#pf-keepall"); if (k) k.onclick = () => { f.remove = []; changedPart(); };
          bindAll(box, { "#pf-tmina": el => { const v = numv(el.value); if (v >= 0) { f.min_area = v; PT.cmd.regions = null; } }, "#pf-tregs": el => { f.grouping = el.value; f.remove = []; PT.cmd.regions = null; } }); },
        done: f => true, summary: f => (f.remove || []).length + " region(s) removed" },
    ],
  },
  surf_extend: {
    title: "Extend surface",
    defaults: () => ({ source: null, edges: [], mode: "edges", distance: 5, sides: "all", tolerance: 0.01, target: null }),
    steps: f => {
      const steps = [];
      // older features with faces of the solid keep the surface step; otherwise a click on an edge picks the surface too
      if ((f.faces || []).length) steps.push(surfaceOrFacesStep("Surface", "Click the surface body to extend, or a face of the solid."));
      steps.push({ key: "edges", label: f.mode === "all" ? "Surface" : "Edges", kinds: ["sedge", "edge"], prop: "edges",
        hint: f.mode === "all" ? "Click an edge of the surface body to extend." : "Click the edges to extend (edges of one surface body; click again to deselect). A click on an edge of another surface body starts again with that body.",
        accept: (f, h) => {
          if (!(f.faces || []).length) {
            if (!h.surface) { msgPart("Click an edge of a surface body", true); return; }
            if (h.surface !== f.source) { f.source = h.surface; f.edges = []; }
            if (f.mode === "all") { PT.dirty = true; return; }
          }
          applyPick(f, { prop: "edges", kinds: ["edge"], single: false }, h);
        },
        html: f => `<p class="hint">${f.source ? itemName(f.source) + ": " : ""}${f.mode === "all" ? "the whole boundary." : (f.edges || []).length + " edge(s) selected."}</p>` + (f.mode === "all" ? "" : `<div class="buttons"><button type="button" data-clear="edges">Clear</button></div>`),
        bind: (f, box) => box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.edges = []; changedPart(); }),
        done: f => f.mode === "all" ? !!f.source || (f.faces || []).length > 0 : (f.edges || []).length > 0,
        summary: f => f.mode === "all" ? (f.source ? itemName(f.source) : "none") : (f.edges || []).length + " edge(s)" });
      if (f.mode === "upto") steps.push({ key: "target", label: "Up to", kinds: ["surface"], single: true, before: false, hint: "Click the surface body to extend up to.",
        accept: (f, h) => { if (h.id === f.source) { msgPart("Click another surface body", true); return; } f.target = h.id; PT.dirty = true; },
        html: f => `<p class="hint">${f.target ? itemName(f.target) + "." : "No surface yet."} The extension is cut where it meets this surface; a surface that does not quite reach is extended beyond its own edges for the cut.</p>`,
        done: f => !!f.target, summary: f => f.target ? itemName(f.target) : "none" });
      steps.push({ key: "extent", label: "Extent", html: f => { const sides = f.sides || "all"; const isList = Array.isArray(sides); const all = f.mode === "all";
        return `<div class="grid2">` + (f.mode === "upto" ? `<span></span>` : num("pf-edist", "Distance (mm)", f.distance || 5)) + select("pf-emode", "Extend", [["edges", "Across the selected edges by a distance"], ["upto", "Across the selected edges up to a surface"], ["all", "Whole boundary: untrimmed patch"]], f.mode || "edges") + `</div>` +
          (all ? select("pf-esides", "Sides", [["all", "All four sides"], ["point", "The side nearest to a point"], ["list", "Chosen parameter sides"]], isList ? "list" : sides) +
            (sides === "point" ? v3("pf-ep", "Point (mm)", f.point || [0, 0, 0]) : "") + (isList ? ["umin", "umax", "vmin", "vmax"].map(k => `<label class="check inline"><input type="checkbox" data-side="${k}"${sides.includes(k) ? " checked" : ""}> ${k}</label>`).join("") : "") : "") +
          `<div class="grid2">` + num("pf-etol", "Fit tolerance (mm, splines)", f.tolerance || 0.01) + `<span></span></div>` +
          `<p class="hint">The extension is part of the face it extends: one face with the surface continued smoothly (a spline surface lengthened with curvature continuity, a plane, cylinder, cone, sphere or torus on itself).</p>` + resultLine(f); },
        bind: (f, box) => { bindAll(box, { "#pf-edist": el => { const x = numv(el.value); if (x > 0) f.distance = x; }, "#pf-emode": el => { f.mode = el.value; }, "#pf-etol": el => { const x = numv(el.value); if (x > 0) f.tolerance = x; }, "#pf-esides": el => { f.sides = el.value === "list" ? ["umin", "umax", "vmin", "vmax"] : el.value; } });
          bind3(box, "pf-ep", v => { f.point = v; }); box.querySelectorAll("input[data-side]").forEach(cb => cb.onchange = () => { f.sides = [...box.querySelectorAll("input[data-side]:checked")].map(x => x.dataset.side); changedPart(); }); },
        summary: f => f.mode === "upto" ? "up to " + (f.target ? itemName(f.target) : "?") : pfmt(f.distance || 5) + " mm" + (f.mode === "all" ? ", untrimmed patch" : "") });
      return steps;
    },
  },
  surf_offset: { title: "Offset surface", defaults: () => ({ source: null, faces: [], distance: 2, join: "auto" }),
    steps: f => [surfaceOrFacesStep("Surface", "Click a surface body or faces of the solid to offset."), { key: "distance", label: "Distance", html: f => `<div class="grid2">` + num("pf-odist", "Distance (mm, along the normals)", f.distance || 0) +
          select("pf-ojoin", "Join at the edges", [["auto", "Automatic (intersection, then arcs, then face by face)"], ["intersection", "Intersection: faces extended or trimmed to meet"], ["arcs", "Arcs at the convex edges"], ["faces", "Face by face, cut at the sharp edges"], ["simple", "Each face on its own (no join)"]], f.join || "auto") + `</div>` +
          `<p class="hint">Automatic takes the first join that gives a valid body. A spike or an overshoot at a corner comes from an intersection join: choose Arcs or Face by face there.</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-odist": el => { f.distance = numv(el.value) || 0; }, "#pf-ojoin": el => { f.join = el.value; } }), summary: f => pfmt(f.distance || 0) + " mm" + (f.join && f.join !== "auto" ? ", " + f.join : "") }] },
  curve_project: { title: "Project curve", defaults: () => ({ source: null, target: null, method: "normal", direction: [0, 0, 0], keep: "nearest" }),
    steps: f => [{ key: "source", label: "Curve", kinds: ["curve", "sketch"], single: true, before: false, hint: "Click the curve to project: a curve body or a sketch.",
        accept: (f, h) => { f.source = h.id; PT.dirty = true; },
        html: f => refSelect("pf-pjsrc", "Curve", itemsAbove(featIndex(f.id), x => CURVE_TYPES.has(x.type) || x.type === "sketch"), f.source),
        bind: (f, box) => bindAll(box, { "#pf-pjsrc": el => { f.source = el.value || null; } }), done: f => !!f.source, summary: f => f.source ? itemName(f.source) : "none" },
      { key: "target", label: "Onto", kinds: ["surface", "body"], single: true, before: false, hint: "Click the surface body to project onto, or the solid.",
        accept: (f, h) => { f.target = h.kind === "surface" ? h.id : null; PT.dirty = true; },
        html: f => refSelect("pf-pjtgt", "Surface", surfaceItems(featIndex(f.id), false), f.target, "(the solid)"),
        bind: (f, box) => bindAll(box, { "#pf-pjtgt": el => { f.target = el.value || null; } }), done: f => true,
        summary: f => f.target ? itemName(f.target) : "the solid" },
      { key: "opts", label: "Options", html: f => select("pf-pjm", "Projection", [["normal", "Normal to the surface (nearest points)"], ["direction", "Along a direction"]], f.method || "normal") +
          (f.method === "direction" ? v3("pf-pjd", "Direction (0, 0, 0: normal of the sketch plane)", f.direction || [0, 0, 0]) +
            select("pf-pjk", "Keep", [["nearest", "The projection nearest to the curve"], ["all", "All projections (every side the direction meets)"]], f.keep || "nearest") : "") + resultLine(f),
        bind: (f, box) => { bindAll(box, { "#pf-pjm": el => { f.method = el.value; }, "#pf-pjk": el => { f.keep = el.value; } }); bind3(box, "pf-pjd", v => { f.direction = v; }); },
        summary: f => f.method === "direction" ? "along a direction" : "normal" }] },
  surf_sweep: { title: "Sweep surface", defaults: () => ({ profile: null, path: null, orient: "corrected", smooth: 0.02 }),
    steps: f => ["profile", "path"].map(k => ({ key: k, label: k === "profile" ? "Profile" : "Path", kinds: ["curve", "sketch"], single: true, before: false,
        hint: k === "profile" ? "Click the profile: a curve body or a sketch (each separate chain is swept)." : "Click the path: a curve body or a sketch (one connected chain).",
        accept: (f, h) => { if (h.id === (k === "profile" ? f.path : f.profile)) { msgPart("The profile and the path must differ", true); return; } f[k] = h.id; PT.dirty = true; },
        html: f => refSelect("pf-sw" + k, k === "profile" ? "Profile" : "Path", itemsAbove(featIndex(f.id), x => CURVE_TYPES.has(x.type) || x.type === "sketch"), f[k]),
        bind: (f, box) => bindAll(box, { ["#pf-sw" + k]: el => { f[k] = el.value || null; } }),
        done: f => !!f[k], summary: f => f[k] ? itemName(f[k]) : "none" }))
      .concat([{ key: "opts", label: "Options", html: f => select("pf-sworient", "Profile orientation", [["corrected", "Corrected Frenet (no twist)"], ["discrete", "Discrete frame (paths with tight bends)"], ["frenet", "Frenet (follows the path curvature)"], ["fixed", "Fixed (moved without turning)"]], f.orient || "corrected") +
          `<div class="grid2">` + num("pf-swsmooth", "Smooth the path within (mm, 0: off)", f.smooth === undefined ? 0.02 : f.smooth) + `<span></span></div>` +
          `<p class="hint">The profile is swept from where it lies along the path; the path corners are joined by extended and intersected sections. Open profiles give open surfaces; a closed profile gives a tube. Smooth: the path is replaced by one smooth spline within the tolerance (short edges, kinks and breaks up to 1 mm of an extracted curve removed).</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-sworient": el => { f.orient = el.value; }, "#pf-swsmooth": el => { const v = numv(el.value); if (v >= 0) f.smooth = v; } }),
        summary: f => ({ frenet: "Frenet", discrete: "discrete frame", fixed: "fixed" }[f.orient] || "corrected Frenet") + ((f.smooth === undefined ? 0.02 : f.smooth) ? ", smoothed" : "") }]) },
  surf_separate: { title: "Separate faces", needsSolid: false, defaults: () => ({ source: null, faces: [], keep: "picked", rest: true }),
    steps: f => [{ key: "faces", label: "Faces", multiFace: true, kinds: ["sface", "face"], before: false,
        hint: "Click the faces of a surface body to separate (click again to deselect; Tangent faces and Connected faces pick groups). All picked faces must belong to one body.",
        accept: (f, h) => {
          if (h.kind === "face" && !h.surface) { msgPart("Click a face of a surface body", true); return; }
          if (h.kind !== "face") return;
          if (f.source !== h.surface) f.faces = [];
          f.source = h.surface; f.faces = f.faces || [];
          if (faceMode() !== "face" && h.key) { pickFaces(f, "faces", h, faceMode()); return; }
          const ref = refOf(h), i = f.faces.findIndex(x => sameRef(x, ref)); if (i >= 0) f.faces.splice(i, 1); else f.faces.push(ref);
          PT.dirty = true;
        },
        html: f => `<p class="hint">${(f.faces || []).length ? (f.faces || []).length + " face(s) of " + pesc(itemName(f.source)) + "." : "Nothing selected."}</p>` +
          ((f.faces || []).length ? `<div class="buttons"><button type="button" data-clear="faces">Clear</button></div>` : ""),
        bind: (f, box) => { box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.faces = []; changedPart(); }); },
        done: f => !!f.source && (f.faces || []).length > 0,
        summary: f => (f.faces || []).length ? (f.faces || []).length + " face(s) of " + itemName(f.source) : "none" },
      { key: "opts", label: "Result", html: f => (f.keep === "rest" ? `<p class="hint">The faces of the body other than the picked ones.</p>` : check("pf-sprest", "Also a body of the remaining faces (a second Separate faces feature)", f.rest !== false)) +
          `<p class="hint">The picked faces become one surface body. The source body is hidden.</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-sprest": el => { f.rest = el.checked; } }),
        summary: f => f.keep === "rest" ? "the remaining faces" : "the picked faces" + (f.rest !== false ? " and the rest" : "") }],
    // on OK: a second feature with the remaining faces of the same body
    finish: async (f, isNew, resume) => {
      if (f.keep !== "rest" && f.rest !== false && f.source && (f.faces || []).length && isNew) {
        checkpointPart();
        const n = PT.part.features.filter(x => x.type === "surf_separate").length;
        PT.part.features.splice(featIndex(f.id) + 1, 0, { id: newId(), name: "Separate faces " + (n + 1) + " (rest)", type: "surf_separate", suppressed: false, source: f.source, faces: f.faces.map(x => Object.assign({}, x)), keep: "rest", rest: false });
      }
      changedPart();
      if (resume) resumeCommand(resume);
    } },
  surf_clean: { title: "Clean edges", defaults: () => ({ source: null, faces: [], clean: "analytic", tolerance: 0.05, angle: 15, min_edge: 0, min_face: 0 }),
    steps: f => [surfaceOrFacesStep("Surface", "Click the surface body whose edges to clean, or faces of the solid (extracted and cleaned in one step)."),
      { key: "opts", label: "Options", html: f => select("pf-clm", "Edges", [["analytic", "Lines and circular arcs within the tolerance, else smooth splines"], ["smooth", "Smooth splines"]], f.clean || "analytic") +
          `<div class="grid2">` + num("pf-cltol", "Tolerance (mm)", f.tolerance === undefined ? 0.05 : f.tolerance) + num("pf-clang", "Corner angle (deg)", f.angle === undefined ? 15 : f.angle) +
          num("pf-clmin", "Remove edges shorter than (mm, 0: off)", f.min_edge || 0) + num("pf-clface", "Remove faces smaller than (mm^2, 0: off)", f.min_face || 0) + `</div>` +
          `<p class="hint">On each face, every run of boundary edges that meet within the corner angle is replaced by one edge, and the face is rebuilt on its own surface. A run shorter than the given length in a corner (a notch, a small chamfer) is removed and the two edges beside it are extended to their corner. A face whose rebuild fails or changes its area is kept as it is. The source body is hidden.</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-clm": el => { f.clean = el.value; }, "#pf-cltol": el => { const v = numv(el.value); if (v > 0) f.tolerance = v; }, "#pf-clang": el => { const v = numv(el.value); if (v >= 0) f.angle = v; },
          "#pf-clmin": el => { const v = numv(el.value); if (v >= 0) f.min_edge = v; }, "#pf-clface": el => { const v = numv(el.value); if (v >= 0) f.min_face = v; } }),
        summary: f => (f.clean === "smooth" ? "smooth" : "analytic") + ", " + pfmt(f.tolerance === undefined ? 0.05 : f.tolerance) + " mm, " + pfmt(f.angle === undefined ? 15 : f.angle) + " deg" + (f.min_edge ? ", edges < " + pfmt(f.min_edge) + " mm removed" : "") + (f.min_face ? ", faces < " + pfmt(f.min_face) + " mm^2 removed" : "") }] },
  surf_gaps: { title: "Close gaps", defaults: () => ({ source: null, max_gap: 0.5 }),
    steps: f => [sourceStep("Surface", "source", false, "Click the surface body whose gaps to close, or choose it."),
      { key: "opts", label: "Gap", html: f => `<div class="grid2">` + num("pf-gmax", "Maximum gap (mm)", f.max_gap || 0.5) + `<span></span></div>` +
          `<p class="hint">A gap is a free edge of one face with free edges of another face beside it, at most the maximum gap apart over its whole length (a split between two faces). One of the two faces is extended to the edges of the other and the faces are sewn into one shell. The source body is hidden.</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-gmax": el => { const v = numv(el.value); if (v > 0) f.max_gap = v; } }), summary: f => "up to " + pfmt(f.max_gap || 0.5) + " mm" }] },
  thicken: { title: "Thicken", defaults: () => ({ source: null, faces: [], thickness: 1, side: "+", mode: "add" }),
    steps: f => [surfaceOrFacesStep("Surface", "Click a surface body or faces of the solid to thicken.", true), { key: "thickness", label: "Thickness", html: f => `<div class="grid2">` + num("pf-tth", "Thickness (mm)", f.thickness || 1) + select("pf-tside", "Side", [["+", "Along the normal"], ["-", "Against the normal"], ["both", "Both (half each)"]], f.side || "+") + `</div>` +
        select("pf-tmode", "Result", [["add", "Add to the part"], ["cut", "Remove from the part"], ["new", "New cell"]], f.mode || "add") + resultLine(f),
      bind: (f, box) => bindAll(box, { "#pf-tth": el => { const v = numv(el.value); if (v > 0) f.thickness = v; }, "#pf-tside": el => { f.side = el.value; }, "#pf-tmode": el => { f.mode = el.value; } }), summary: f => pfmt(f.thickness || 1) + " mm, " + (f.mode || "add") }] },
  curve_section: { title: "Intersection curve", defaults: () => ({ source: null, faces: [], other: null, with: "shape", plane: "XY", gap: 0.5 }),
    steps: f => [surfaceOrFacesStep("Surface", "Click a surface body or faces of the solid."), { key: "other", label: "With", kinds: ["surface", "body", "plane"], single: true, before: false, hint: "Click the second surface body, the solid, or a plane.",
      accept: (f, h) => { if (h.kind === "plane") { f.with = "plane"; f.plane = h.id; } else { f.with = "shape"; f.other = h.kind === "surface" ? h.id : null; } PT.dirty = true; },
      html: f => { const i = featIndex(f.id); const opts = [["", "(none: the solid)"]].concat(surfaceItems(i, false).filter(x => x.id !== f.source).map(x => [x.id, x.name]))
          .concat(Object.entries(BASE_PLANES).map(([k, n]) => ["plane:" + k, "Plane " + n])).concat(planeItems(i).map(p => ["plane:" + p.id, "Plane " + p.name]));
        return select("pf-other", "With", opts, f.with === "plane" ? "plane:" + (f.plane || "XY") : (f.other || "")) +
          `<div class="grid2">` + num("pf-isgap", "Bridge gaps up to (mm, 0: off)", f.gap === undefined ? 0.5 : f.gap) + `<span></span></div>` +
          `<p class="hint">Pieces of the intersection whose ends are at most this far apart are joined into one curve by straight lines.</p>` + resultLine(f); },
      bind: (f, box) => bindAll(box, { "#pf-other": el => { if (el.value.startsWith("plane:")) { f.with = "plane"; f.plane = el.value.slice(6); } else { f.with = "shape"; f.other = el.value || null; } }, "#pf-isgap": el => { const v = numv(el.value); if (v >= 0) f.gap = v; } }),
      done: f => true, summary: f => f.with === "plane" ? "plane " + planeName(f.plane) : f.other ? itemName(f.other) : "the solid" }] },
  surf_extract: { title: "Extract surface", needsSolid: false, defaults: () => ({ faces: [], offset: 0, separate: false }),
    steps: f => [facesStep("Faces", "faces", "Click the faces to copy as a surface body: faces of the solid or of surface bodies.", false, true), { key: "offset", label: "Offset", html: f => `<div class="grid2">` + num("pf-xoff", "Offset along the normals (mm)", f.offset || 0) + `<span></span></div>` +
          check("pf-xsep", "Separate bodies: one Extract surface feature per connected group of the picked faces", !!f.separate) + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-xoff": el => { f.offset = numv(el.value) || 0; }, "#pf-xsep": el => { f.separate = el.checked; } }), summary: f => pfmt(f.offset || 0) + " mm" + (f.separate ? ", separate bodies" : "") }],
    // Separate bodies: on OK the picked faces are grouped through their shared edges on the server and the feature is
    // split into one Extract surface per group (the first group stays in this feature)
    finish: async (f, isNew, resume) => {
      if (f.separate && (f.faces || []).length > 1) {
        try {
          const r = await postJSON("/api/part/face_groups", { part: PT.part, index: featIndex(f.id), faces: f.faces });
          const groups = await r.json();
          if (Array.isArray(groups) && groups.length > 1) {
            checkpointPart();
            f.faces = groups[0];
            let at = featIndex(f.id) + 1, n = PT.part.features.filter(x => x.type === "surf_extract").length;
            for (const g of groups.slice(1)) {
              PT.part.features.splice(at++, 0, { id: newId(), name: "Extract surface " + (++n), type: "surf_extract", suppressed: false, faces: g, offset: f.offset || 0, separate: true });
            }
            msgPart(groups.length + " connected groups of faces: " + groups.length + " surface bodies");
          } else if (Array.isArray(groups)) msgPart("The picked faces are one connected group: one surface body");
        } catch (e) { showErr(e); }
      }
      changedPart();
      if (resume) resumeCommand(resume);
    } },
  surf_fillet: { title: "Surface fillet", defaults: () => ({ mode: "bodies", source_a: null, source_b: null, source: null, edges: [], radius: 2, flip_a: false, flip_b: false, trim: true }),
    steps: f => {
      const modeSel = select("pf-sfmode", "Fillet", [["bodies", "Between two surface bodies"], ["edges", "Edges of a surface body"]], f.mode || "bodies");
      const opts = { key: "opts", label: "Radius",
        html: f => modeSel + `<div class="grid2">` + num("pf-sfr", "Radius (mm)", f.radius || 2) + `<span></span></div>` +
          (f.mode === "edges" ? `<p class="hint">The picked edges, where two faces of the surface body meet, are rounded with the radius. The result is a surface body; the source body is hidden.</p>`
            : check("pf-sffa", "Flip side on surface A", f.flip_a) + check("pf-sffb", "Flip side on surface B", f.flip_b) + check("pf-sftrim", "Trim the surfaces at the fillet and sew them into one body", f.trim !== false) +
              `<p class="hint">A ball of the radius rolls between the nearest faces of surface A and surface B, on the side of each face that faces the other surface (Flip: the other side; when those sides give no fillet the other combinations are tried). The fillet runs between the curves where the ball touches the faces. Trim: each surface is cut at its contact curve, the part towards the corner is removed and the rest is sewn with the fillet into one surface body (the sources are hidden); else the result is the fillet surface alone.</p>`) + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-sfmode": el => { f.mode = el.value; }, "#pf-sfr": el => { const v = numv(el.value); if (v > 0) f.radius = v; },
          "#pf-sffa": el => { f.flip_a = el.checked; }, "#pf-sffb": el => { f.flip_b = el.checked; }, "#pf-sftrim": el => { f.trim = el.checked; } }),
        summary: f => "R" + pfmt(f.radius || 2) + (f.mode === "edges" ? ", edges" : (f.flip_a || f.flip_b ? ", flipped" : "") + (f.trim === false ? ", fillet only" : ", trimmed")) };
      if (f.mode === "edges") return [sourceStep("Surface", "source", false, "Click the surface body whose edges to round, or choose it."),
        { key: "edges", label: "Edges", kinds: ["sedge", "edge"], prop: "edges", before: false, hint: "Click the edges to round (where two faces of a surface body meet); click again to deselect.",
          accept: (f, h) => {
            if (!h.surface) { msgPart("Click an edge of a surface body", true); return; }
            // an edge of another surface body: that body becomes the surface
            if (h.surface !== f.source) { f.source = h.surface; f.edges = []; }
            applyPick(f, { prop: "edges", kinds: ["edge"], single: false }, h);
          },
          html: f => `<p class="hint">${(f.edges || []).length} edge(s) selected.</p><div class="buttons"><button type="button" data-clear="edges">Clear</button></div>`,
          bind: (f, box) => box.querySelectorAll("button[data-clear]").forEach(b => b.onclick = () => { f.edges = []; changedPart(); }),
          done: f => (f.edges || []).length > 0, summary: f => (f.edges || []).length + " edge(s)" }, opts];
      return [filletSideStep("a"), filletSideStep("b"), opts];
    } },
  surf_bridge: { title: "Bridge surface", defaults: () => ({ edges_a: [], curves_a: [], edges_b: [], curves_b: [], flip: false }),
    steps: f => ["a", "b"].map(k => ({ key: "side_" + k, label: "Side " + k.toUpperCase(), multi: true, kinds: ["edge", "sedge", "curve"], before: false,
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
      .concat([{ key: "opts", label: "Options", html: f => select("pf-bcont", "Continuity", [["ruled", "Ruled (straight lines between the sides)"], ["tangent", "Tangent to the faces of both sides"]], f.continuity || "ruled") +
          (f.continuity === "tangent" ? `<div class="grid2">` + num("pf-bfac", "Tangent length (x the distance between the sides)", f.factor === undefined ? 1 : f.factor) + `<span></span></div>` : "") +
          check("pf-bflip", "Flip (join the ends of side A to the other ends of side B)", f.flip) +
          `<p class="hint">The ends of side A are joined to the nearer ends of side B (corner to corner) and the points between; the result is a surface body. Tangent: the surface leaves each side in the plane of the face that owns the side's edges (a side on a curve body: position only). Sew surfaces joins it to the neighbouring surfaces.</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-bcont": el => { f.continuity = el.value; }, "#pf-bfac": el => { const v = numv(el.value); if (v > 0) f.factor = v; }, "#pf-bflip": el => { f.flip = el.checked; } }),
        summary: f => (f.continuity === "tangent" ? "tangent" : "ruled") + (f.flip ? ", flipped" : "") }]) },
  surf_connect: { title: "Connect surfaces", needsSolid: false, defaults: () => ({ source_a: null, edges_a: [], source_b: null, edges_b: [], tolerance: 0.01 }),
    steps: f => ["a", "b"].map(k => ({ key: "side_" + k, label: "Side " + k.toUpperCase(), multi: true, kinds: ["sedge", "edge"], before: false,
        hint: `Click the edges of surface body ${k.toUpperCase()} at the corner (one body per side; click again to deselect). A click on an edge of another body starts the side again with that body.`,
        accept(f, h) {
          if (!h.surface) { msgPart("Click an edge of a surface body", true); return; }
          const other = k === "a" ? f.source_b : f.source_a;
          if (h.surface === other) { msgPart("Side " + k.toUpperCase() + " must be another surface body than side " + (k === "a" ? "B" : "A"), true); return; }
          if (h.surface !== f["source_" + k]) { f["source_" + k] = h.surface; f["edges_" + k] = []; }
          applyPick(f, { prop: "edges_" + k, kinds: ["edge"], single: false }, h);
        },
        html: f => `<p class="hint">${f["source_" + k] ? itemName(f["source_" + k]) + ": " : ""}${(f["edges_" + k] || []).length} edge(s).</p><div class="buttons"><button type="button" data-cclear="${k}">Clear</button></div>`,
        bind: (f, box) => box.querySelectorAll("button[data-cclear]").forEach(b => b.onclick = () => { f["source_" + k] = null; f["edges_" + k] = []; changedPart(); }),
        done: f => !!f["source_" + k] && (f["edges_" + k] || []).length > 0,
        summary: f => f["source_" + k] ? itemName(f["source_" + k]) + ", " + (f["edges_" + k] || []).length + " edge(s)" : "none" }))
      .concat([{ key: "opts", label: "Options", html: f => `<div class="grid2">` + num("pf-ctol", "Tolerance (mm)", f.tolerance || 0.01) + `<span></span></div>` +
          `<p class="hint">Side A is extended across its edges up to side B (B extended beyond its own edges when it is too short), then side B across its edges up to the extended A. Both end at their intersection and are sewn into one body; a gap or an overlap at the corner is closed. The two bodies are hidden.</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-ctol": el => { const v = numv(el.value); if (v > 0) f.tolerance = v; } }), summary: f => "" }]) },
  curve_blend: { title: "Blend curve", needsSolid: false, defaults: () => ({ ends: [null, null] }),
    steps: f => [0, 1].map(i => ({ key: "end_" + i, label: "End " + "AB"[i], kinds: ["edge", "sedge", "curve", "point"], before: false,
        hint: `Click the end of an edge (of the solid or of a surface body) or of a curve body near end ${"AB"[i]}, or a vertex or point feature. The curve continues the edge from the end nearer the click.`,
        accept(f, h) {
          f.ends = f.ends || [null, null];
          const prev = f.ends[i] || {};
          const at = (h.point || [0, 0, 0]).map(v => +(+v).toFixed(6));
          if (h.kind === "point") f.ends[i] = { kind: "point", point: refOf(h) };
          else if (h.kind === "curve") f.ends[i] = { kind: "curve", body: h.id, at, cont: prev.cont || "tangent", factor: prev.factor || 1 };
          else f.ends[i] = { kind: "edge", ref: refOf(h), body: h.surface || null, at, cont: prev.cont || "tangent", factor: prev.factor || 1 };
          PT.dirty = true;
        },
        html: f => { const e = (f.ends || [])[i]; if (!e) return `<p class="hint">Nothing picked.</p>`;
          if (e.kind === "point") return `<p class="hint">Point: ${pesc(itemName(e.point))}.</p><div class="buttons"><button type="button" data-eclear="${i}">Clear</button></div>`;
          return `<p class="hint">${e.kind === "curve" ? "End of " + pesc(itemName(e.body)) : "Edge end"} at (${e.at.map(v => pfmt(v, 2)).join(", ")}).</p>` +
            select("pf-bcont" + i, "Continuity", [["position", "Position"], ["tangent", "Tangent (continues the edge)"], ["curvature", "Curvature"]], e.cont || "tangent") +
            (e.cont !== "position" ? `<div class="grid2">` + num("pf-bfac" + i, "Tangent length (x the distance between the ends)", e.factor === undefined ? 1 : e.factor) + `<span></span></div>` : "") +
            `<div class="buttons"><button type="button" data-eclear="${i}">Clear</button></div>`; },
        bind: (f, box) => { bindAll(box, { ["#pf-bcont" + i]: el => { f.ends[i].cont = el.value; }, ["#pf-bfac" + i]: el => { const v = numv(el.value); if (v > 0) f.ends[i].factor = v; } });
          box.querySelectorAll("button[data-eclear]").forEach(b => b.onclick = () => { f.ends[i] = null; changedPart(); }); },
        done: f => !!(f.ends || [])[i],
        summary: f => { const e = (f.ends || [])[i]; return e ? (e.kind === "point" ? itemName(e.point) : (e.kind === "curve" ? itemName(e.body) : "edge") + ", " + (e.cont || "tangent")) : "none"; } }))
      .concat([{ key: "opts", label: "Result", html: f => `<p class="hint">A curve body: a cubic (tangent) or quintic (curvature) Bezier curve between the two ends. Fill surface, Loft surface, Bridge surface, Extend surface (up to) and Sweep surface take it.</p>` + resultLine(f), summary: f => "" }]) },
  curve_points: { title: "Curve through points", needsSolid: false, defaults: init => Object.assign({ points: [], method: "polyline", closed: false }, init && init.space ? { space: true, grid: { axis: "z" } } : {}),
    steps: f => [{ key: "points", label: "Points", kinds: ["point"], multi: true, before: false,
        hint: f.space ? "Click points in space: vertices, edge midpoints, centres of circular edges, centre lines, points on edges, else the 3D snap grid (a plane through the last point; X, Y, Z: its normal). Shift: along the grid normal through the last point. Backspace: removes the last point."
          : "Click vertices of the solid, of surface and curve bodies, or point features, in order. Click again to remove a point.",
        accept(f, h) {
          f.points = f.points || []; const ref = refOf(h);
          if (f.space) { const last = f.points[f.points.length - 1]; if (!(last && sameRef(last, ref))) f.points.push(ref); PT.dirty = true; return; }
          const k = f.points.findIndex(x => sameRef(x, ref)); if (k >= 0) f.points.splice(k, 1); else f.points.push(ref); PT.dirty = true; },
        // the chips (hover and click highlight the point, x removes it, Clear) are bound by bindChips
        html: f => (f.space ? spaceHtml(f) : "") + ((f.points || []).length ? `<div class="cw-chips" data-prop="points">` + (f.points || []).map((p, k) => `<span class="cw-chip" data-i="${k}" title="${pesc(itemName(p))}. Click: keep highlighted">${k + 1} · ${pesc(isVertexRef(p) ? "(" + p.map(v => pfmt(v, 2)).join(", ") + ")" : itemName(p))}<button type="button" data-cwdel="${k}" title="Remove">×</button></span>`).join("") + `</div>` +
          `<div class="buttons"><button type="button" data-cwclear="points">Clear</button></div>` : `<p class="hint">No point yet.</p>`),
        bind: (f, box) => { if (f.space) bindSpace(f, box); },
        done: f => (f.points || []).length >= 2, summary: f => (f.points || []).length + " point(s)" },
      { key: "opts", label: "Curve", html: f => select("pf-cpm", "Curve", [["polyline", "Polyline (straight segments)"], ["spline", "Smooth spline through the points"], ["line", "Best-fit straight line"], ["arc", "Circular arc through three points"]], f.method || "polyline") +
          (f.method === "polyline" || f.method === "spline" || !f.method ? check("pf-cpclosed", "Closed", !!f.closed) : "") + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-cpm": el => { f.method = el.value; }, "#pf-cpclosed": el => { f.closed = el.checked; } }),
        summary: f => (f.method || "polyline") + (f.closed && (f.method === "polyline" || f.method === "spline" || !f.method) ? ", closed" : "") }] },
  surf_fill: { title: "Fill surface", defaults: () => ({ edges: [], tangent: true, curves: [], sketch_refs: [], gap: 0.5 }),
    steps: f => [{ key: "edges", label: "Boundary", multi: true, kinds: ["edge", "sedge", "face", "sketch", "curve"], before: false,
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
      { key: "opts", label: "Options", html: f => check("pf-ftan", "Tangent to the adjacent faces", f.tangent !== false) + `<div class="grid2">` + num("pf-fgap", "Close gaps up to (mm, 0: off)", f.gap === undefined ? 0.5 : f.gap) + `<span></span></div>` +
          `<p class="hint">Edges whose ends are at most this far apart are joined by straight lines so the loop closes.</p>` + resultLine(f),
        bind: (f, box) => bindAll(box, { "#pf-ftan": el => { f.tangent = el.checked; }, "#pf-fgap": el => { const v = numv(el.value); if (v >= 0) f.gap = v; } }), summary: f => (f.tangent !== false ? "tangent" : "position only") + ((f.gap === undefined ? 0.5 : f.gap) ? ", gaps to " + pfmt(f.gap === undefined ? 0.5 : f.gap) + " mm" : "") }] },
  curve_extract: { title: "Extract curve", needsSolid: false, defaults: () => ({ edges: [], tangent_chain: false, clean: "none", tolerance: 0.05, gap: 0.5, project: "" }),
    steps: f => [Object.assign(edgesStep("Edges", "edges", "Click the edges of the curve: edges of the solid or of surface bodies."), { kinds: ["edge", "sedge", "face"] }), { key: "opts", label: "Clean", html: f => select("pf-cclean", "Clean", [["none", "None (edges as they are)"], ["smooth", "Join into one smooth spline within tolerance"], ["analytic", "Line or circular arc within tolerance, else smooth spline"]], f.clean || "none") +
        `<div class="grid2">` + num("pf-ctol", "Tolerance (mm)", f.tolerance || 0.05) + num("pf-cgap", "Bridge gaps up to (mm, 0: off)", f.gap || 0) + `</div>` +
        `<p class="hint">Breaks between the picked edges up to the gap are bridged with straight lines and the curve is one chain (with Clean the spline is fitted across them).</p>` + sourceSelect("pf-cproj", f, "project", false, false).replace("Surface<", "Project onto surface<") + resultLine(f),
      bind: (f, box) => bindAll(box, { "#pf-cclean": el => { f.clean = el.value; }, "#pf-ctol": el => { const v = numv(el.value); if (v > 0) f.tolerance = v; }, "#pf-cgap": el => { const v = numv(el.value); if (v >= 0) f.gap = v; }, "#pf-cproj": el => { f.project = el.value; } }), summary: f => (f.clean || "none") + (f.gap ? ", gaps up to " + pfmt(f.gap) + " mm" : "") }] },
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
  if (f.type === "surf_trim") { if (!(f.faces || []).length) add(f.source); if (f.with !== "solid") { if ((f.tool_faces || []).length) add(f.tool_faces); else add(f.tool); } }
  if (f.type === "sketch") { if (f.plane === "datum") add(f.plane_ref); else if (BASE_PLANES[f.plane]) add(f.plane); add(f.plane_edge); add(f.plane_curve); add(f.plane_face); add(f.plane_axis); add(f.plane_point); add(f.plane_origin_ref); add(f.plane_xdir_ref); if (f.plane_sketch_curve) add(f.plane_sketch_curve.sketch); }
  if (f.type === "point" || f.type === "axis" || f.type === "plane") { add(f.point_ref); add(f.axis_ref); add(f.points_ref); add(f.planes_ref); add(f.plane_ref); add(f.edge); add(f.curve); add(f.face); if (f.sketch_curve) add(f.sketch_curve.sketch); }
  if (f.type === "revolve" || f.type === "pattern") add(f.axis_ref);
  if (f.type === "sketch" && f.plane_origin) out.points.push(f.plane_origin);
  if (f.type === "place") { add(f.face1); add(f.face2); add(f.face3); }
  for (const k of ["faces", "edges", "source", "sources", "curves", "tool", "other", "project", "sketch_refs", "edges_a", "edges_b", "curves_a", "curves_b"]) if (!(f.type === "surf_trim" && (k === "tool" || k === "source"))) add(f[k]);
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
  else if (h.kind === "face" && h.surface && h.point) it = { point: h.point.slice(), surface: h.surface };
  else if (h.kind === "plane") it = BASE_PLANES[h.id] ? { base: h.id } : { plane: h.id };
  else if (h.kind === "axis") it = { axis: h.id };
  if (!it) { msgPart("Measure takes faces of the solid, points on surface bodies, planes and axes", true); return; }
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
      addMarker(q, MEAS_COL, 6, 12);
    }
  }
}

/** Settings of the commands kept for the next use (server: config.local.json "part_last"); picks are not kept. */
const STICKY = {
  extrude: ["depth", "symmetric"], cut: ["depth", "through", "symmetric"], revolve: ["angle"],
  hole: ["dia", "depth", "cbore_dia", "cbore_depth", "csink_dia", "csink_angle", "thread", "tol"],
  thread: ["thread", "thread_type", "tol", "cut_od"],
  fillet: ["value"], chamfer: ["value"], shell: ["thickness"],
  boolean: ["op", "keep_tools", "min_thickness", "min_volume", "keep_slivers"],
  pattern: ["kind", "count", "step", "count2", "step2", "row_offset", "axis", "angle"],
  body_delete: ["min_volume", "min_thickness"], body_scale: ["uniform", "factor", "factors", "about", "copy"],
  import: ["clean"], unify: ["faces", "edges", "angle"], heal: ["tolerance", "small_faces"], defeature: ["min_area"],
  offset_faces: ["distance", "tangent"], move_faces: ["vector", "tangent"], combine: ["min_area"],
  hole_mesh: ["factor", "n_circ", "n_rad", "bias", "n_thick"], smooth: ["tolerance", "segments", "continuity"],
  replace: ["method", "tolerance", "offset", "pad", "min_area"], surf_fit: ["method", "tolerance", "extend", "offset"],
  surf_sketch: ["depth", "symmetric", "angle"], surf_extend: ["distance", "sides", "tolerance"],
  surf_offset: ["distance"], thicken: ["thickness", "side", "mode"], surf_extract: ["offset"],
  surf_fillet: ["radius", "trim"], surf_trim: ["extend", "extend_far", "min_area", "grouping"], surf_fill: ["tangent", "gap"], surf_sew: ["tolerance"], surf_gaps: ["max_gap"], surf_sweep: ["orient", "smooth"], curve_project: ["method", "keep"],
  curve_extract: ["tangent_chain", "clean", "tolerance", "gap"], curve_section: ["gap"], surf_clean: ["clean", "tolerance", "angle", "min_edge", "min_face"], surf_from_curve: ["depth", "symmetric", "angle"], sweep: ["kind", "mode", "tool_at"],
};
async function loadLast() {
  try { const r = await fetch("/api/part/last"); if (r.ok) PT.last = await r.json(); } catch (e) { /* defaults */ }
}
/** Kept settings of a finished feature: sent to the server when they differ from the stored ones. */
function rememberLast(f) {
  const keys = STICKY[f.type];
  if (!keys) return;
  const vals = {};
  for (const k of keys) if (f[k] !== undefined) vals[k] = JSON.parse(JSON.stringify(f[k]));
  const cur = (PT.last || {})[f.type] || {};
  if (!Object.keys(vals).some(k => JSON.stringify(vals[k]) !== JSON.stringify(cur[k]))) return;
  PT.last = PT.last || {};
  PT.last[f.type] = Object.assign({}, cur, vals);
  PT.lastSave = api("/api/part/last", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type: f.type, values: vals }) })
    .then(() => true, () => false);     // on failure the settings are kept for this session
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
    const last = (PT.last || {})[type];
    if (last && STICKY[type]) for (const k of STICKY[type]) if (last[k] !== undefined && !(init && k in init)) f[k] = JSON.parse(JSON.stringify(last[k]));
    if (type === "surf_sketch" && f.kind === "revolve") f.name = "Revolved surface " + (PT.part.features.filter(x => x.type === "surf_sketch" && x.kind === "revolve").length + 1);
    if (type === "curve_points" && f.space) f.name = "3D sketch " + (PT.part.features.filter(x => x.type === "curve_points" && x.space).length + 1);
    if (type === "sketch" && !init) { const s = PT.sel && (BASE_PLANES[PT.sel] ? PT.sel : feat(PT.sel) && feat(PT.sel).type === "plane" ? PT.sel : null); if (s) { if (BASE_PLANES[s]) f.plane = s; else { f.plane = "datum"; f.plane_ref = s; } } }
    if (SKETCH_TYPES.has(type) || type === "surf_sketch") { const s = PT.sel && feat(PT.sel); if (s && s.type === "sketch") f.sketch_ref = s.id; }
    if (init && init.insertAt !== undefined) PT.part.features.splice(init.insertAt, 0, f); else PT.part.features.push(f);
  }
  PT.cmd = { id: f.id, step: 0, isNew: !existingId, snapshot: JSON.stringify(f), pick: null, regions: null, emode: "edge", fmode: "face", resume: init && init.resume };
  // start at the first unfinished step
  const steps = commandSteps(f);
  let i = steps.findIndex(st => !st.optional && !stepDone(f, st));
  // all done: the last step that is not optional (a new feature), or the first (an edited one)
  if (i < 0) { let last = steps.length - 1; while (last > 0 && steps[last].optional) last--; i = def.startStep !== undefined ? def.startStep : existingId ? 0 : last; }
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
  if (!f) return;
  const steps = commandSteps(f);
  if (i < 0 || i >= steps.length) return;
  c.step = i; c.pick = null;
  if (steps[i].enter) steps[i].enter(f);
  renderCommand();
  scheduleBuild();
}
function nextStep() {
  const c = PT.cmd;
  if (!c) return;
  const f = feat(c.id);
  if (!f) return;
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
  rememberLast(f);
  PT.cmd = null; PT.chipPin = null; PT.chipHover = null; PT.spaceHover = null;
  drawSpace(null);
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
  PT.cmd = null; PT.chipPin = null; PT.chipHover = null; PT.spaceHover = null;
  drawSpace(null);
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
  PT.cmd = null; PT.chipPin = null; PT.chipHover = null;
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
  return { key: "regions", label: "Regions", multi: true, kinds: ["region"], before: true, optional: true,
    hint: "Click the regions of the sketch to use (click again to deselect). None picked: every closed loop.",
    enter: f => { if (f.sketch_ref) loadProfileRegions(f); },
    accept: (f, h) => { f.regions = f.regions || []; const k = (h.uv || []).join(","); const i = f.regions.findIndex(p => p.join(",") === k); if (i >= 0) f.regions.splice(i, 1); else f.regions.push(h.uv); PT.dirty = true; drawRegions(); },
    html: f => { const n = (PT.cmd.regions || []).length; return `<p class="hint">${PT.cmd.regions ? n + " region(s), " + (f.regions || []).length + " picked" + ((f.regions || []).length ? "." : ": every closed loop is used.") : "Computing the regions..."}</p><div class="buttons"><button type="button" id="pf-regall">All</button><button type="button" id="pf-regnone">None</button></div>`; },
    bind: (f, box) => { const a = box.querySelector("#pf-regall"); if (a) a.onclick = () => { f.regions = (PT.cmd.regions || []).map(r => r.uv); changedPart(); };
      const n = box.querySelector("#pf-regnone"); if (n) n.onclick = () => { f.regions = []; changedPart(); }; },
    done: f => true, summary: f => (f.regions || []).length ? (f.regions || []).length + " region(s)" : "all loops" };
}

async function loadRegions(f) {
  PT.cmd.regions = null; PT.cmd.regionMode = "remove"; PT.cmd.regionError = null;
  try {
    const r = await postJSON("/api/part/regions", { part: PT.part, index: featIndex(f.id) });
    const regs = await r.json();
    if (!PT.cmd || PT.cmd.id !== f.id) return;
    if (regs && regs.error) { PT.cmd.regions = null; PT.cmd.regionError = "Regions: " + regs.error; renderCommand(); setMesh(PT.mesh); return; }
    PT.cmd.regions = regs;
    if (!f.keep) f.keep = "pick";
    renderCommand();
    setMesh(PT.mesh);
  } catch (e) {
    msgPart("Regions: " + (e.message || e), true);
    // the reason in the Regions section (in place of "Computing the regions...")
    if (PT.cmd && PT.cmd.id === f.id) { PT.cmd.regionError = "Regions: " + (e.message || e); renderCommand(); }
  }
}

/** The command bar in the properties panel. A render requested while a field of the bar has the focus (the
 *  user is typing) is deferred to the blur of that field; a nested render during the DOM replacement is skipped. */
function renderCommand(force) {
  if (PT.quiet) return;
  if (PT.three && PT.three.space && PT.three.space.children.length && !spaceFeat()) drawSpace(null);
  else if (spaceFeat()) drawSpace(spaceFeat(), PT.spaceHover);
  const box = $("#pt-cmdbody");
  const c = PT.cmd;
  if (!c) { $("#pt-cmdwin").hidden = true; renderProps(); return; }
  if (PT.renderingCmd) return;
  const ae = document.activeElement;
  if (!force && ae && box.contains(ae) && ae.matches("input, select, textarea")) { PT.pendingRender = true; return; }
  PT.renderingCmd = true;
  try { renderCommandNow(box, c); } finally { PT.renderingCmd = false; }
}
/** Steps whose clicks in the view a command takes: the steps with element kinds. */
const isPickStep = s => !!(s && s.kinds);
/** Command window: every step of the command as a section (element steps list their selection, value steps their
 *  fields); the active section takes the clicks in the view. */
function renderCommandNow(box, c) {
  const f = feat(c.id);
  if (!f) { PT.cmd = null; renderCommand(); return; }
  const def = commandDef(f.type);
  const steps = commandSteps(f);
  if (c.step >= steps.length) c.step = steps.length - 1;
  const st = PT.status[f.id] || {};
  const title = f.type === "surf_sketch" && f.kind === "revolve" ? "Revolved surface" : def.title;
  let h = `<div class="cmd cw"><div class="cw-name">` + nameField(f) + `</div>`;
  steps.forEach((s, i) => {
    const done = stepDone(f, s);
    const active = i === c.step;
    const pick = isPickStep(s);
    h += `<section class="cw-sec${active ? " active" : ""}${done ? " done" : ""}${pick ? " pick" : ""}" data-step="${i}">` +
      `<div class="cw-sec-head"><span class="cw-mark">${done ? "✓" : s.optional ? "○" : "●"}</span><span class="lbl">${s.label}${s.optional ? '<span class="opt">optional</span>' : ""}</span>` +
      (pick && s.summary ? `<span class="sum">${pesc(s.summary(f))}</span>` : "<span></span>") + `</div>` +
      `<div class="cw-sec-body">` + (active && s.hint ? `<p class="hint cw-hint">${s.hint}</p>` : "") + (s.html ? s.html(f) : "") +
      (active && isMultiFaceStep(s) ? faceModeHtml() : "") + selChips(f, s) +
      (active && s.kinds && (s.multi || s.multiFace || (s.prop && !s.single)) ? boxToolsHtml(clearBtn(f, s)) : clearBtn(f, s) ? `<div class="buttons">${clearBtn(f, s)}</div>` : "") + `</div></section>`;
  });
  h += `<div class="cw-result">`;
  if (st.pending) h += pendingText(st);
  else if (st.error && !h.includes(pesc(st.error))) h += `<p class="hint err">${pesc(st.error)}</p>`;
  else if (st.extent) h += `<p class="hint">${st.profiles} profile(s)${st.note ? "; " + pesc(st.note) : ""}</p>`;
  h += `</div><div class="cw-foot cmd-foot"><button type="button" id="cmd-finish" class="primary"${canFinish(f) ? "" : " disabled"}>${def.finishLabel || "OK"}</button><button type="button" id="cmd-cancel">Cancel</button></div></div>`;
  box.innerHTML = h;
  const nm = box.querySelector("#pf-name");
  if (nm) nm.onchange = () => { f.name = nm.value.trim() || f.name; PT.dirty = true; renderTree(); };
  box.querySelectorAll(".cw-sec").forEach(sec => {
    const i = +sec.dataset.step, s = steps[i];
    if (s.bind) s.bind(f, sec.querySelector(".cw-sec-body"));
    // a click on the head of another section makes it the active one (its clicks in the view, or the full preview
    // for a value section); a field of a value section activates it without redrawing the window
    sec.querySelector(".cw-sec-head").onclick = () => { if (i !== PT.cmd.step) gotoStep(i); };
    sec.addEventListener("focusin", () => { if (PT.cmd && i !== PT.cmd.step && !isPickStep(s)) activateStep(i, box); });
  });
  bindFaceMode(box.querySelector(".cw-sec.active") || box);
  bindChips(f, box);
  foldHelp(box);
  // the result line once: a section that shows the same error already
  const re = box.querySelector(".cw-result .err");
  if (re && [...box.querySelectorAll(".cw-sec-body .err")].some(x => x.textContent === re.textContent)) re.remove();
  box.querySelector("#cmd-finish").onclick = () => finishCommand();
  box.querySelector("#cmd-cancel").onclick = cancelCommand;
  $("#pt-cmdwin-title").textContent = title;
  $("#pt-cmdwin").hidden = false;
  placeCmdWin();
  if (!PT.inspect) $("#pt-props").innerHTML = `<p class="hint">${pesc(f.name)} is open in the command window.</p>`;
}
/** Selected faces and edges of an element section (f[prop] an array of face or edge references) as chips: × removes
 *  one, Clear all. */
function selChips(f, s) {
  const v = s.prop && f[s.prop];
  if (!Array.isArray(v) || !v.length || !v.every(x => x && typeof x === "object" && (x.c || x.mid))) return "";
  const max = 40;
  const pin = PT.chipPin;
  const same = x => pin && ((x.mid && pin.mid && keyOfEdge(x) === keyOfEdge(pin)) || (x.c && pin.c && keyOfFace(x) === keyOfFace(pin)));
  const chip = (x, i) => `<span class="cw-chip${same(x) ? " on" : ""}" data-i="${i}" title="${x.mid ? "Edge at (" + x.mid.map(q => pfmt(q, 2)).join(", ") + ")" : "Face at (" + x.c.map(q => pfmt(q, 2)).join(", ") + ")"}. Click: keep highlighted">` +
    (x.mid ? "Edge " + (i + 1) + " · " + pfmt(x.len, 2) + " mm" : "Face " + (i + 1) + " · " + pfmt(x.area, 2) + " mm^2") + `<button type="button" data-cwdel="${i}" title="Remove">×</button></span>`;
  return `<div class="cw-chips" data-prop="${pesc(s.prop)}">` + v.slice(0, max).map(chip).join("") + (v.length > max ? `<span class="hint">+${v.length - max} more</span>` : "") + `</div>`;
}
const clearBtn = (f, s) => s.prop && Array.isArray(f[s.prop]) && f[s.prop].length ? `<button type="button" data-cwclear="${pesc(s.prop)}">Clear</button>` : "";
function bindChips(f, box) {
  box.querySelectorAll(".cw-chips").forEach(el => {
    const prop = el.dataset.prop;
    el.querySelectorAll("[data-cwdel]").forEach(b => b.onclick = e => { e.stopPropagation(); PT.chipHover = null; PT.chipPin = null; checkpointPart(); f[prop].splice(+b.dataset.cwdel, 1); changedPart(); });
    // the highlight of a chip: a face or edge reference as it is, a point (vertex or point feature) as {point}
    const hoverOf = x => !x ? null : (x.c || x.mid) ? x : { point: pointOf(x) };
    el.querySelectorAll(".cw-chip").forEach(ch => {
      ch.onmouseenter = () => { PT.chipHover = hoverOf((f[prop] || [])[+ch.dataset.i]); drawSelection(); };
      ch.onmouseleave = () => { PT.chipHover = null; drawSelection(); };
      // a click keeps the element highlighted in the view until the chip is clicked again or another chip is clicked
      ch.onclick = e => { if (e.target.closest("[data-cwdel]")) return; const x = hoverOf((f[prop] || [])[+ch.dataset.i]); PT.chipPin = ch.classList.contains("on") ? null : x; el.querySelectorAll(".cw-chip").forEach(c => c.classList.toggle("on", c === ch && !!PT.chipPin)); drawSelection(); };
    });
  });
  box.querySelectorAll("[data-cwclear]").forEach(b => b.onclick = e => { e.stopPropagation(); checkpointPart(); f[b.dataset.cwclear] = []; changedPart(); });
}
/** Long explanations of the command window folded under "About" (kept open for the session once opened). */
function foldHelp(box) {
  box.querySelectorAll(".cw-sec-body p.hint").forEach(p => {
    if (p.classList.contains("cw-hint") || p.classList.contains("err") || p.textContent.length < 140) return;
    const d = document.createElement("details");
    d.className = "cw-help";
    d.open = !!PT.helpOpen;
    d.innerHTML = "<summary>About</summary>";
    p.replaceWith(d);
    d.appendChild(p);
    d.addEventListener("toggle", () => { PT.helpOpen = d.open; });
  });
}
/** Active step changed without redrawing the window (a field of a value section got the focus). */
function activateStep(i, box) {
  const c = PT.cmd, f = c && feat(c.id);
  if (!f) return;
  const steps = commandSteps(f);
  c.step = i; c.pick = null;
  if (steps[i].enter) steps[i].enter(f);
  box.querySelectorAll(".cw-sec").forEach(sec => sec.classList.toggle("active", +sec.dataset.step === i));
  box.querySelectorAll(".cw-hint").forEach(el => el.remove());
  scheduleBuild();
}
/** Command window inside the view at its stored place (localStorage "pt-cmdwin-pos"). */
function placeCmdWin() {
  const w = $("#pt-cmdwin"), v = $("#pt-view");
  if (!w || !v) return;
  let pos = PT.cmdPos;
  if (!pos) { try { pos = JSON.parse(localStorage.getItem("pt-cmdwin-pos") || "null"); } catch (e) { pos = null; } }
  pos = pos || { x: 12, y: 12 };
  const maxX = Math.max(0, v.clientWidth - w.offsetWidth - 4), maxY = Math.max(0, v.clientHeight - 60);
  pos = { x: Math.min(Math.max(0, pos.x), maxX), y: Math.min(Math.max(0, pos.y), maxY) };
  PT.cmdPos = pos;
  w.style.left = pos.x + "px"; w.style.top = pos.y + "px";
}
function bindCmdWin() {
  const head = $("#pt-cmdwin-head");
  if (!head) return;
  $("#pt-cmdwin-x").onclick = cancelCommand;
  head.addEventListener("mousedown", e => {
    if (e.button !== 0 || e.target.closest("button")) return;
    const w = $("#pt-cmdwin"), x0 = e.clientX, y0 = e.clientY, p0 = { x: w.offsetLeft, y: w.offsetTop };
    const move = ev => { PT.cmdPos = { x: p0.x + ev.clientX - x0, y: p0.y + ev.clientY - y0 }; placeCmdWin(); };
    const up = () => {
      window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up);
      try { localStorage.setItem("pt-cmdwin-pos", JSON.stringify(PT.cmdPos)); } catch (err) { /* kept for this session */ }
    };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
    e.preventDefault();
  });
}

// ------------------------------------------------------------------ legacy parameter panels (one-step commands)

function pendingText(st) {
  const f = PT.cmd && feat(PT.cmd.id), stl = f && f.type === "import" && /\.stl$/i.test(f.path || "");
  return st.pending ? `<p class="hint">Building…${stl ? " (an STL file with many triangles can take a minute or more)" : ""}</p>` : "";
}
function resultText(st) {
  if (st.pending) return pendingText(st);
  if (st.error) return `<p class="hint err">${pesc(st.error)}</p>`;
  if (st.faces === undefined) return st.note ? `<p class="hint">${pesc(st.note)}</p>` : "";
  let t = `<p class="hint">Result: ${st.faces_before} → ${st.faces} faces, ${st.edges_before} → ${st.edges} edges`;
  if (st.note) t += `. ${pesc(st.note)}`;
  return t + "</p>";
}
/** Pick buttons of the legacy panels: a pick in the view into f[prop] with the given element kind. */
function pickButtons(f, kind, prop, single, title, label) {
  if (kind === "face" && !single) return pickButtonsCore(f, kind, prop, single, title, label) + faceModeHtml() + boxToolsHtml();
  if (!single) return pickButtonsCore(f, kind, prop, single, title, label) + boxToolsHtml();
  return pickButtonsCore(f, kind, prop, single, title, label);
}
function pickButtonsCore(f, kind, prop, single, title, label) {
  const active = PT.cmd && PT.cmd.pick && PT.cmd.pick.prop === prop;
  const n = single ? (f[prop] ? 1 : 0) : (f[prop] || []).length;
  return `<div class="buttons"><button type="button" data-pick="${prop}" class="${active ? "" : "primary"}">${active ? "Done picking" : label}</button>` +
    (single ? "" : `<button type="button" data-clear="${prop}">Clear</button>`) + `<span class="hint">${n} selected</span></div>` +
    (single ? "" : selChips(f, { prop }));
}
function bindPicks(f, box, defs) {
  bindFaceMode(box);
  bindChips(f, box);
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

/** Check boxes of the solids a pattern can copy: the solids before the pattern (the copies follow them). */
function patternBodyChecks(f) {
  const st = PT.status[f.id] || {};
  const n = st.solids_before !== undefined ? st.solids_before : PT.solids.length;
  const sel = new Set((f.bodies || []).map(b => (typeof b === "object" ? b.solid : b)));
  if (!n) return '<p class="hint">No solids.</p>';
  return PT.solids.slice(0, n).map((s, i, a) => `<label class="check"><input type="checkbox" data-pb="${i}"${sel.has(i) ? " checked" : ""}> ${solidLabel(i, volTexts(a.map(x => x.volume_mm3)))}</label>`).join("") +
    (PT.solids.length < n ? Array.from({ length: n - PT.solids.length }, (_, k) => `<label class="check"><input type="checkbox" data-pb="${PT.solids.length + k}"${sel.has(PT.solids.length + k) ? " checked" : ""}> Solid ${PT.solids.length + k + 1}</label>`).join("") : "");
}
const LEGACY_DEFAULTS = {
  pattern: () => ({ kind: "linear", features: [], count: 3, step: [20, 0, 0], count2: 1, step2: [0, 20, 0], row_offset: 0, axis: "Z", centre: [0, 0, 0], angle: 360 }),
  import: () => ({ path: "", part: null, clean: { rebuild: true, fix: true, unify: false, min_volume: 0 } }),
  unify: () => ({ faces: true, edges: true, angle: 0 }),
  heal: () => ({ tolerance: 0, small_faces: 0 }),
  defeature: () => ({ faces: [], min_area: 0, all_small: false }),
  offset_faces: () => ({ faces: [], distance: 1, tangent: true }),
  move_faces: () => ({ faces: [], vector: [0, 0, 1], tangent: true }),
  place: () => ({ face1: null, plane1: "XY", flip1: false, face2: null, plane2: "XZ", flip2: false, face3: null, plane3: "YZ", flip3: false, rest: "keep", offset: [0, 0, 0] }),
  combine: () => ({ faces: [], min_area: 0 }),
  hole_mesh: () => ({ faces: [], factor: 2, n_circ: 3, n_rad: 4, bias: 2, n_thick: 4 }),
  smooth: () => ({ tolerance: 0.05, segments: 6, continuity: "C2" }),
  merge_tangent: () => ({ faces: [], angle: 1, splines_only: true, points: 8, max_dev: 0.1 }),
  replace: () => ({ faces: [], method: "analytic", tolerance: 0.05, offset: 0, pad: 1, min_area: 0 }),
  surf_fit: () => ({ faces: [], method: "analytic", tolerance: 0.05, extend: 0.3, offset: 0 }),
  surf_loft: () => ({ sections: [{ plane: "XY", offset: 0, sketch: emptySketch() }, { plane: "XY", offset: 20, sketch: emptySketch() }], ruled: false, curves: [] }),
  surf_sew: () => ({ sources: [], tolerance: 0.001 }),
  surf_import: () => ({ path: "", label: "" }),
  surf_cut: () => ({ source: null, with: "surface", plane: "XY", keep: "-" }),
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
      `<p class="hint" style="margin-bottom:2px">Bodies to repeat (copied as new solids)</p>` + pickButtons(f, "body", "bodies", false, "", "Pick bodies") +
      patternBodyChecks(f) +
      `<div class="grid2">` + num("pf-count", "Count", f.count || 2, 1) + `<span></span></div>` +
      (f.kind === "circular"
        ? `<div class="grid2">` + select("pf-pax", "Axis", [["X", "X"], ["Y", "Y"], ["Z", "Z"]].concat(axisItems(i0).map(a => ["ref:" + a.id, "Axis feature " + a.name])), f.axis_ref ? "ref:" + f.axis_ref : (f.axis || "Z")) + num("pf-pang", "Total angle (deg)", f.angle === undefined ? 360 : f.angle) + `</div>` + (f.axis_ref ? "" : v3("pf-c", "Axis point (mm)", f.centre || [0, 0, 0])) + `<p class="hint">360 deg spreads the instances evenly around the axis.</p>`
        : v3("pf-s", "Direction 1 step (mm)", f.step || [10, 0, 0]) + `<div class="grid2">` + num("pf-count2", "Count in direction 2", f.count2 || 1, 1) + num("pf-rowoff", "Row offset (mm, every second row along direction 1)", f.row_offset || 0) + `</div>` + ((f.count2 || 1) > 1 ? v3("pf-s2", "Direction 2 step (mm)", f.step2 || [0, 10, 0]) : ""));
    bindAll(box, { "#pf-kind": el => { f.kind = el.value; }, "#pf-count": el => { const c = parseInt(el.value); if (c >= 2) f.count = c; }, "#pf-pax": el => { if (el.value.startsWith("ref:")) f.axis_ref = el.value.slice(4); else { f.axis = el.value; f.axis_ref = null; } }, "#pf-pang": el => { const a = numv(el.value); if (a > 0 && a <= 360) f.angle = a; } });
    bind3(box, "pf-s", v => { f.step = v; }); bind3(box, "pf-s2", v => { f.step2 = v; }); bind3(box, "pf-c", v => { f.centre = v; });
    bindAll(box, { "#pf-count2": el => { const c = parseInt(el.value); if (c >= 1) f.count2 = c; }, "#pf-rowoff": el => { f.row_offset = numv(el.value) || 0; } });
    box.querySelectorAll("input[data-pf]").forEach(cb => cb.onchange = () => { f.features = [...box.querySelectorAll("input[data-pf]:checked")].map(x => x.dataset.pf); changedPart(); });
    box.querySelectorAll("input[data-pb]").forEach(cb => cb.onchange = () => { f.bodies = [...box.querySelectorAll("input[data-pb]:checked")].map(x => ({ solid: +x.dataset.pb })); changedPart(); });
    bindPicks(f, box, { bodies: { kind: "body" } });
  },
  import(f, box) {
    const cl = f.clean || {};
    const isStl = /\.stl$/i.test(f.path || ""), so = f.stl || {};
    box.innerHTML = `<label>STEP or STL file path on this PC<span class="row"><input type="text" id="pf-path" value="${pesc(f.path || "")}" placeholder="C:\\...\\part.step"><button type="button" id="pf-browse" class="browse" title="Choose the file">…</button></span></label>` +
      (isStl ? `<p class="hint" style="margin-bottom:2px">STL</p>` +
        select("pf-smode", "Import as", [["solid", "Solid (converted faces)"], ["rough", "Rough mesh (surface body for measuring and tracing, fast)"]], so.mode === "rough" ? "rough" : "solid") : "") +
      (isStl && so.mode === "rough" ? `<div class="grid2">` + num("pf-smax", "Max triangles (larger meshes are reduced)", so.max_triangles || 20000) + `<span></span></div>` +
        `<p class="hint">The triangles of the STL (reduced by merging the vertices in grid cells when there are more than the maximum) are planar faces of a surface body. It is shown opaque, can be measured (Measure: a click on it picks a point) and its section shows in sketches. No solid is made: Extrude, Cut and the other solid features do not use it.</p>` + resultText(PT.status[f.id] || {}) : "") +
      (isStl && so.mode !== "rough" ? check("pf-sfit", "Fit cylinders, cones and spheres to curved areas", so.fit !== false) +
        `<div class="grid2">` + num("pf-stol", "Tolerance (mm, 0: 1/1000 of the size)", so.tolerance || 0) + num("pf-sang", "Flat face: angle between triangles (deg)", so.angle || 0.5) + `</div>` +
        `<div class="grid2">` + num("pf-ssmooth", "Curved area: angle between neighbouring triangles (deg)", so.smooth || 30) + `<span></span></div>` +
        `<p class="hint">The closed mesh is converted to a solid: triangles in one plane within the tolerance form one planar face; with fitting, smooth curved areas that a cylinder, cone or sphere fits within the tolerance form one face (closed cylinders and cones in two halves); other curved areas stay as flat facets. The edges between the faces are the intersection curves of their surfaces.</p>` : "") +
      (isStl && so.mode === "rough" ? "" : (
      (isStl ? "" : `<label>Solid in the file<input type="text" id="pf-partidx" value="${f.part === null || f.part === undefined ? "" : pesc(f.part)}" placeholder="empty: all solids; or an index 0, 1, ..."></label>`) +
      `<p class="hint" style="margin-bottom:2px">Clean-up</p>` +
      check("pf-crebuild", "Rebuild faces on the wrong range of a periodic surface (torus, cylinder, cone, sphere)", !!cl.rebuild) +
      check("pf-cfix", "Fix topology, tolerances and edge curves on faces", !!cl.fix) +
      check("pf-cunify", "Merge coplanar faces and collinear edges", !!cl.unify) +
      check("pf-cana", "Spline faces to planes, cylinders, cones, spheres and tori (an exporter that writes every face as a spline)", !!cl.analytic) +
      `<div class="grid2">` + num("pf-cminvol", "Remove solids below (mm^3, 0: off)", cl.min_volume || 0) + num("pf-canatol", "Spline to surface tolerance (mm)", cl.analytic_tol || 0.001) + `</div>` + resultText(PT.status[f.id] || {}) +
      `<p class="hint">Each clean-up step is kept only when the solid stays one solid, its volume changes by less than 1 % (rebuilt faces: 5 %) and it does not make a valid solid invalid. The result line gives the invalid solids and faces before and after. The imported solids are the base geometry; partitions and the other features apply to them.</p>`));
    const setClean = (k, v) => { f.clean = Object.assign({}, f.clean || {}, { [k]: v }); };
    const setStl = (k, v) => { f.stl = Object.assign({ fit: true }, f.stl || {}, { [k]: v }); };
    bindAll(box, { "#pf-smode": el => setStl("mode", el.value), "#pf-smax": el => setStl("max_triangles", Math.max(100, Math.round(numv(el.value) || 20000))), "#pf-sfit": el => setStl("fit", el.checked), "#pf-stol": el => setStl("tolerance", Math.max(0, numv(el.value) || 0)),
                   "#pf-sang": el => { const v = numv(el.value); if (v > 0) setStl("angle", v); }, "#pf-ssmooth": el => { const v = numv(el.value); if (v > 0) setStl("smooth", v); } });
    bindAll(box, { "#pf-path": el => { f.path = el.value.trim(); if (/\.stl$/i.test(f.path) && !f.stl) f.stl = { fit: true }; }, "#pf-partidx": el => { const v = el.value.trim(); f.part = v === "" ? null : v; },
                   "#pf-crebuild": el => setClean("rebuild", el.checked), "#pf-cfix": el => setClean("fix", el.checked), "#pf-cunify": el => setClean("unify", el.checked), "#pf-cana": el => setClean("analytic", el.checked), "#pf-canatol": el => setClean("analytic_tol", Math.max(1e-6, numv(el.value) || 0.001)),
                   "#pf-cminvol": el => setClean("min_volume", Math.max(0, numv(el.value) || 0)) });
    box.querySelector("#pf-browse").onclick = async () => { try { const p = await window.browse("open", "model", "", "STEP or STL file to import"); if (p) { f.path = p; if (/\.stl$/i.test(p) && !f.stl) f.stl = { fit: true }; if (!(await importSurfaceStep(f))) changedPart(); } } catch (e) { showErr(e); } };
    const pin = box.querySelector("#pf-path"), pch = pin.onchange;
    pin.onchange = async ev => { if (pch) pch.call(pin, ev); try { await importSurfaceStep(f); } catch (e) { showErr(e); } };
    const err = (PT.status[f.id] || {}).error || "";
    if (/only surfaces/.test(err)) {
      box.insertAdjacentHTML("beforeend", `<button type="button" id="pf-assurf" title="Replace this feature with one Import surface feature per component of the file">Import as surfaces</button>`);
      box.querySelector("#pf-assurf").onclick = () => importSurfaceStep(f).catch(showErr);
    }
  },
  unify(f, box) {
    box.innerHTML = check("pf-uf", "Merge coplanar and co-cylindrical faces", f.faces !== false) + check("pf-ue", "Merge collinear and co-circular edges", f.edges !== false) +
      `<div class="grid2">` + num("pf-uang", "Angular tolerance (deg, 0: exact)", f.angle || 0) + `<span></span></div>` +
      check("pf-uana", "Spline faces to planes, cylinders, cones, spheres and tori first", !!f.analytic) +
      `<div class="grid2">` + num("pf-utol", "Spline to surface tolerance (mm)", f.tolerance || 0.001) + `<span></span></div>` + resultText(PT.status[f.id] || {}) +
      `<p class="hint">Removes the face and edge splits left by imports and booleans (CAE: virtual topology, remove redundant entities). Faces merge only when they lie on the same surface. An exporter that writes planes and cylinders as splines gives each face its own surface: with the first option those faces are rebuilt on a plane, cylinder, cone, sphere or torus when they lie on one within the tolerance, and then merge (the line above gives the count). Free-form faces stay as they are.</p>`;
    bindAll(box, { "#pf-uf": el => { f.faces = el.checked; }, "#pf-ue": el => { f.edges = el.checked; }, "#pf-uang": el => { f.angle = numv(el.value) || 0; },
                   "#pf-uana": el => { f.analytic = el.checked; }, "#pf-utol": el => { f.tolerance = Math.max(1e-6, numv(el.value) || 0.001); } });
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
  merge_tangent(f, box) {
    box.innerHTML = pickButtons(f, "face", "faces", false, "", "Pick faces (none: all)") +
      `<div class="grid2">` + num("pf-mtang", "Faces meeting at less than (deg)", f.angle || 1) + num("pf-mtdev", "Max deviation (mm)", f.max_dev || 0.1) + `</div>` +
      `<div class="grid2">` + num("pf-mtpts", "Points per face (n x n)", f.points || 8) + `<span></span></div>` +
      check("pf-mtspl", "Spline faces only (with no faces picked)", f.splines_only !== false) + resultText(PT.status[f.id] || {}) +
      `<p class="hint">Groups of faces that meet at less than the angle (the tangent patches an exporter writes for one smooth surface) are each replaced by one smooth face through the boundary edges of the group and points inside its faces. A group whose faces do not have one boundary loop, whose new face is farther than the deviation from the old faces, or that would make the solid invalid stays as it is. Smoothness comes before the exact shape: the volume can change a little (the line above gives it).</p>`;
    bindAll(box, { "#pf-mtang": el => { const v = numv(el.value); if (v > 0) f.angle = v; }, "#pf-mtdev": el => { const v = numv(el.value); if (v > 0) f.max_dev = v; },
                   "#pf-mtpts": el => { const v = parseInt(el.value); if (v >= 3) f.points = v; }, "#pf-mtspl": el => { f.splines_only = el.checked; } });
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
      `<label>Component<input type="text" id="pf-slabel" list="pf-slabels" value="${pesc(f.label || "")}" placeholder="empty: all faces of the file"></label><datalist id="pf-slabels"></datalist>` + resultText(PT.status[f.id] || {}) +
      `<p class="hint">The faces of the component (STEP label) become one surface body.</p>`;
    bindAll(box, { "#pf-spath": el => { f.path = el.value.trim(); }, "#pf-slabel": el => { f.label = el.value.trim(); } });
    box.querySelector("#pf-sbrowse").onclick = async () => { try { const p = await window.browse("open", "step", "", "STEP file to import"); if (p) { f.path = p; changedPart(); } } catch (e) { showErr(e); } };
    if (f.path) stepInfo(f.path).then(j => { const dl = box.querySelector("#pf-slabels"); if (dl && j) dl.innerHTML = (j.surfaces || []).map(n => `<option value="${pesc(n)}">`).join(""); }).catch(() => {});
  },
  surf_cut(f, box) {
    const i = featIndex(f.id);
    const opts = [["", "(none)"]].concat(surfaceItems(i, false).map(x => [x.id, x.name]))
      .concat(Object.entries(BASE_PLANES).map(([k, n]) => ["plane:" + k, "Plane " + n])).concat(planeItems(i).map(p => ["plane:" + p.id, "Plane " + p.name]));
    box.innerHTML = select("pf-src", "Surface or plane", opts, f.with === "plane" ? "plane:" + (f.plane || "XY") : (f.source || "")) +
      select("pf-keep", "Keep", [["-", "The side against the surface normal"], ["+", "The side along the surface normal"]], f.keep || "-") + resultText(PT.status[f.id] || {}) +
      `<p class="hint">The solid is split by the surface or plane and the cells on one side are kept. A surface must pass through the solid completely. The normal of a reference plane is its axis (Top: +Z, Front: -Y, Right: +X); of a plane feature, its normal.</p>`;
    bindAll(box, { "#pf-src": el => { if (el.value.startsWith("plane:")) { f.with = "plane"; f.plane = el.value.slice(6); f.source = null; } else { f.with = "surface"; f.source = el.value || null; } }, "#pf-keep": el => { f.keep = el.value; } });
  },
};

/** Components of a STEP file: {"solids", "surfaces": [names]} (server: model.step_solids, step_surfaces). */
async function stepInfo(path) {
  return await (await postJSON("/api/part/step_info", { path })).json();
}
/** Import geometry of a STEP file without solids: the feature is replaced by one Import surface feature per
 * component with faces (one surface body each, named by the component). Returns true when replaced. */
async function importSurfaceStep(f) {
  if (!f.path || /\.stl$/i.test(f.path)) return false;
  const j = await stepInfo(f.path);
  if (!j || j.solids !== 0 || !(j.surfaces || []).length || !feat(f.id)) return false;
  const names = [...new Set(j.surfaces)];
  const one = names.length === 1 || names.some(n => !n);
  const items = (one ? [""] : names).map(n => ({ id: newId(), name: n || nextName("surf_import"), type: "surf_import", suppressed: false, path: f.path, label: n }));
  PT.part.features.splice(featIndex(f.id), 1, ...items);
  PT.cmd = null; PT.chipPin = null; PT.chipHover = null;
  PT.sel = items[0].id;
  changedPart();
  msgPart(`${f.path.split(/[\\/]/).pop()} has no solids: ${items.length} Import surface feature(s), one surface body per component`);
  return true;
}

// ------------------------------------------------------------------ sketch editing

/** Opens the sketch editor for a sketch item (or a loft section). isNew: a new item, removed again when left empty. */
async function editSketch(id, isNew, section, resume) {
  const f = feat(id);
  if (!f) return;
  const sec = section !== undefined ? (f.sections || [])[section] : null;
  if (!sec && f.type !== "sketch") { if (f.sketch_ref) editSketch(f.sketch_ref); return; }
  // the command bar is closed before the reference geometry is read (a slow read with many bodies left the bar
  // of the finished command on screen)
  if (PT.cmd && PT.cmd.id === id) { resume = resume || PT.cmd.resume; PT.cmd = null; }
  if (!PT.cmd) { PT.sel = id; renderProps(); }
  msgPart("Sketch editor: reading the reference geometry");
  const index = featIndex(id);
  // the reference geometry (again on Cut at plane / Flip in the sketch bar) and the model up to the sketch for the
  // shaded view under the sketch
  const readRefs = async cut => { const r = await postJSON("/api/part/refs", { part: PT.part, index, path: false, section: section === undefined ? null : section, cut: cut || null }); return await r.json(); };
  const readModel = async () => { const r = await postJSON("/api/part/build", { part: PT.part, upto: index }); const j = await r.json(); return { mesh: j.mesh, surfaces: j.surfaces || {} }; };
  const cut = window.sketchRefOptions ? window.sketchRefOptions().cut : null;
  let refs = [], model = null;
  const [rr, rm] = await Promise.allSettled([readRefs(cut), readModel()]);
  if (rr.status === "fulfilled") refs = rr.value;            // reference geometry and the shaded view are optional
  if (rm.status === "fulfilled") model = rm.value;
  const title = sec ? `${f.name}: section ${section + 1} on ${planeName(sec.plane || "XY")}, offset ${pfmt(+sec.offset || 0)} mm` : `${f.name} on ${planeSummary(f)}`;
  const frame = (refs || []).find(e => e.t === "frame");
  let underlay = null;
  if (model && frame && frame.o3 && ((model.mesh && model.mesh.vertices.length) || Object.keys(model.surfaces).length)) {
    try { underlay = createSketchUnderlay(model, frame, index); } catch (e) { console.error(e); underlay = null; }
  }
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
  }, { reload: readRefs, underlay });
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

/** Configurations section of the side panel: folded by default (localStorage "pt-cfg-open"). */
function bindConfigFold() {
  const h = $("#pt-cfg-toggle"), box = $("#pt-configs");
  if (!h || !box) return;
  let open = false;
  try { open = localStorage.getItem("pt-cfg-open") === "1"; } catch (e) { /* folded */ }
  const show = () => { box.hidden = !open; h.querySelector(".fold").textContent = open ? "▾" : "▸"; };
  h.onclick = () => { open = !open; try { localStorage.setItem("pt-cfg-open", open ? "1" : "0"); } catch (e) { /* this session */ } show(); };
  show();
}
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
  PT.cmd = null; PT.chipPin = null; PT.chipHover = null;
  PT.status = {};
  PT.hidden = {};
  if (Array.isArray(p.hidden)) for (const id of p.hidden) PT.hidden[id] = true;
  else for (const f of p.features || []) if (!f.suppressed) for (const sid of consumedSources(f)) PT.hidden[sid] = true;
  PT.dirty = false;
  if (PT.three) PT.three.zoomed = false;
  if (FM) FM.render();
  renderTree();
  renderProps();
  renderConfigs();
  build();
}

/** Surface bodies a feature replaces (trim, extend, sew, offset, thicken): hidden when the feature is created. */
function consumedSources(f) {
  if (!f || f.suppressed) return [];
  return sourcesOf(f);
}
/** The bodies a feature of these types consumes, suppressed or not. */
function sourcesOf(f) {
  if (!f) return [];
  if (f.type === "surf_trim") return ((f.faces || []).length ? [] : [f.source]).concat(f.mutual && (f.with || "surface") === "surface" && f.tool && !(f.tool_faces || []).length ? [f.tool] : []).filter(Boolean);
  if (f.type === "surf_extend" || f.type === "thicken" || f.type === "surf_gaps" || f.type === "surf_clean" || f.type === "surf_separate") return f.source ? [f.source] : [];
  if (f.type === "surf_sew") return f.sources || [];
  if (f.type === "surf_fillet") return f.mode === "edges" ? (f.source ? [f.source] : []) : f.trim === false ? [] : [f.source_a, f.source_b].filter(Boolean);
  if (f.type === "surf_connect") return [f.source_a, f.source_b].filter(Boolean);
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
/** Assembly tab: a new (unsaved) part whose base geometry is one solid of a STEP file (Import geometry feature). */
window.__partNewFromStep = function (name, path, index) {
  const p = blankPart(name);
  p.features.push({ id: "f" + (p.next++), name: "Import geometry 1", type: "import", suppressed: false, path, part: index === undefined ? null : index, clean: { rebuild: true, fix: true, unify: false, min_volume: 0 } });
  loadPart(p);
  if (FM) FM.markUnsaved();
  importSurfaceStep(p.features[p.features.length - 1]).catch(() => {});          // a STEP file without solids
};
window.__partCurrent = () => (PT.part ? { name: PT.part.name, dirty: !!PT.dirty } : null);

window.partShown = function () {
  if (!PT.three) initThree();
  if (!PT.part) loadPart(blankPart("part"));
  refreshList();
  setTimeout(resize3, 0);
};

(function bindPart() {
  loadLast();
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
  for (const [id, mode] of [["#pt-show-all", "all"], ["#pt-hide-all", "none"], ["#pt-show-invert", "invert"], ["#pt-show-solids", "solids"], ["#pt-show-surfaces", "surfaces"]]) if ($(id)) $(id).onclick = () => showBodies(mode);
  if ($("#pt-cancel")) $("#pt-cancel").onclick = cancelBuild;
  if ($("#pt-surfop")) { $("#pt-surfop").value = String(Math.round(surfOpacity() * 100)); const lbl = $("#pt-surfop-val"); if (lbl) lbl.textContent = Math.round(surfOpacity() * 100) + " %"; $("#pt-surfop").oninput = () => setSurfOpacity(+$("#pt-surfop").value / 100); }
  $("#pt-cmdbody").addEventListener("focusout", () => setTimeout(() => { const box = $("#pt-cmdbody"); if (PT.pendingRender && !(document.activeElement && box.contains(document.activeElement))) { PT.pendingRender = false; if (PT.cmd) renderCommand(); } }, 0));
  bindCmdWin();
  bindConfigFold();
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
    const sf = spaceFeat();
    if (sf && ["x", "y", "z"].includes(e.key.toLowerCase())) { e.preventDefault(); sf.grid = Object.assign({}, sf.grid, { axis: e.key.toLowerCase() }); renderCommand(); drawSpace(sf, null); return; }
    if (sf && e.key === "Backspace") { e.preventDefault(); if ((sf.points || []).length) { sf.points.pop(); PT.dirty = true; changedPart(); renderCommand(); } return; }
    if (e.key === "Escape") cancelCommand();
    if (e.key === "Enter") finishCommand();
  });
  window.addEventListener("beforeunload", e => { if (PT.dirty) { e.preventDefault(); e.returnValue = ""; } });
})();
// exposed for tests
window.__part = { PT, feat, snap3d, spaceGrid, feedCommand, showOnlyBody, showAllBodies, showBodies, toggleBodyGroup, bodyGroupIds, surfOpacity, setSurfOpacity, cancelBuild, boxHits, selectShown, addHits, activePick, THREE, loadPart, setMesh, viewXdir, setMeasure, measureClick, startCommand, finishCommand, cancelCommand, gotoStep, nextStep, selectItem, pickAt, commandSteps, changedPart, viewDir, hoverText };

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
