// Assembly tab: placed components (saved parts or STEP files), 3D view, mass, interference, STEP and drawing.
import * as THREE from "three";
import { TumbleControls } from "/static/vendor/TumbleControls.js";
import { updateAxes } from "/static/axes.js";
import { createNavCube } from "/static/navcube.js";

const AS = { asm: null, sel: null, dirty: false, three: null, seq: 0, timer: null, result: null, bbox: null,
             matePick: null,   // {mateId, side: "a" | "b"} while a face is being picked for a mate
             selMate: null,
             dragMode: false,  // Drag: left drag moves unmated, unfixed components
             drag: null };     // {cid, plane, start, delta, objs} during a drag
const MATE_TYPES = { coincident: "Coincident (faces)", distance: "Distance (faces)", parallel: "Parallel (faces)",
                     angle: "Angle (faces)", concentric: "Concentric (cylinders)", point: "Point (face centres)",
                     tangent: "Tangent (plane, cylinders)", gear: "Gear (rotation ratio)" };
const aesc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const afmt = (v, d = 3) => { let s = Number(v).toFixed(d).replace(/\.?0+$/, ""); return s === "-0" || s === "" ? "0" : s; };
const PALETTE = ["#9aa7b5", "#c98a4a", "#5b8fc9", "#7bb06a", "#b86a9a", "#c9b24a", "#6ab0b0", "#a07a5a"];

const newUidA = () => Array.from(crypto.getRandomValues(new Uint8Array(6)), b => b.toString(16).padStart(2, "0")).join("");
function blankAsm(name) { return { name: name || "assembly", components: [], next: 1, uid: newUidA() }; }
function comp(id) { return AS.asm.components.find(c => c.id === id); }

// ------------------------------------------------------------------ 3D view (same conventions as the Part tab)

function initThree() {
  const box = $("#as-view");
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.localClippingEnabled = true;               // section plane
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
  const group = new THREE.Group();
  scene.add(group);
  updateAxes(scene, null, true);
  AS.three = { renderer, scene, camera, controls, group, box, zoomed: false, pickables: [] };
  controls.addEventListener("change", render3);
  camera.userData.target = controls.target;
  AS.three.cube = createNavCube(box, camera, viewDir);
  let down = null;
  // drag mode: capture phase on the box, so the controls do not start a rotation when a component is grabbed
  box.addEventListener("pointerdown", e => { if (e.target === renderer.domElement) { if (!boxStart(e)) dragStart(e); } }, true);
  renderer.domElement.addEventListener("pointermove", dragHover);
  renderer.domElement.addEventListener("pointerleave", () => { AS.mouse = null; });
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; closeCompMenu(); });
  renderer.domElement.addEventListener("contextmenu", e => e.preventDefault());
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.abs(e.clientX - down[0]) + Math.abs(e.clientY - down[1]) > 4) { down = null; return; }
    down = null;
    if (e.button === 1) { setPivotAs(e); return; }
    if (e.button === 2) { if (!AS.matePick) { const cid = compAt(e); if (cid) showCompMenu(cid, e.clientX, e.clientY); } return; }
    if (e.button === 0) pickComponent(e);
  });
  new ResizeObserver(resize3).observe(box);
  resize3();
}
function resize3() {
  const t = AS.three;
  if (!t) return;
  const w = t.box.clientWidth || 1, h = t.box.clientHeight || 1;
  t.renderer.setSize(w, h);
  const c = t.camera, half = (c.top - c.bottom) / 2 || 100;
  c.left = -half * w / h; c.right = half * w / h;
  c.updateProjectionMatrix();
  render3();
}
function render3() { const t = AS.three; if (!t) return; t.renderer.render(t.scene, t.camera); if (t.cube) t.cube.render(); }

/** Turns the camera to look along -dir (dir: from the target to the camera) with the given up vector; the target, the
 *  distance and the zoom are kept. Used by the navigation cube. */
/** View along dir (direction from the target to the camera). The up vector is the axis direction perpendicular
 *  to dir that is nearest to the current screen up, so a view that is nearly square is only squared up. */
function viewDir(dir, up) {
  const t = AS.three;
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

/** Centre of rotation at the clicked point of a component (middle click); the view does not move. */
function setPivotAs(e) {
  const t = AS.three;
  const r = t.renderer.domElement.getBoundingClientRect();
  const nd = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster();
  rc.setFromCamera(nd, t.camera);
  const hits = pickHits(rc);
  if (!hits.length) return;
  t.controls.setTarget(hits[0].point.clone(), true);
  render3();
}

// ------------------------------------------------------------------ drag mode

/** Component that drag mode may move: not fixed. Returns null, or the reason it may not. */
/** The selected components: the box or Ctrl selection when it holds the current component, else the current one. */
function selIds() { return AS.sel && AS.multi && AS.multi.has(AS.sel) ? AS.multi : new Set(AS.sel ? [AS.sel] : []); }
function setSelection(ids) {
  const arr = [...ids].filter(id => comp(id));
  AS.multi = arr.length > 1 ? new Set(arr) : null;
  AS.sel = arr.length ? (arr.includes(AS.sel) ? AS.sel : arr[0]) : null;
  renderComps(); renderProps(); setMeshes(AS.result);
}
function toggleSelect(id) {
  const s = new Set(selIds());
  if (s.has(id)) s.delete(id); else s.add(id);
  setSelection(s);
  status(s.size + " component(s) selected");
}

/** Box selection: Ctrl + left drag, or a left drag with Box select on. Left to right: the components entirely
 *  inside the box; right to left: the components the box touches. With Ctrl the box adds to the selection.
 *  Returns true when the press starts a box (the view does not rotate). */
function boxStart(e) {
  if (e.button !== 0 || !(e.ctrlKey || e.metaKey || AS.boxMode) || AS.dragMode || AS.measure || pickSide() || !AS.three) return false;
  e.stopPropagation();
  e.preventDefault();
  const t = AS.three, r = t.box.getBoundingClientRect();
  const x0 = e.clientX, y0 = e.clientY, add = e.ctrlKey || e.metaKey;
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
    if (Math.abs(x1 - x0) + Math.abs(y1 - y0) < 4) {        // a click: Ctrl toggles the component under the cursor
      const cid = compAt(ev);
      if (cid) toggleSelect(cid);
      return;
    }
    const ids = boxComps(Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1), x1 < x0);
    const sel = add ? new Set([...selIds(), ...ids]) : new Set(ids);
    setSelection(sel);
    status(sel.size + " component(s) selected (" + (x1 < x0 ? "touched by the box" : "inside the box") + "). Space hides them; right click for more");
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  return true;
}

/** Components in a screen rectangle (client px): all sampled vertices inside (window), or any inside (crossing). */
function boxComps(xa, ya, xb, yb, crossing) {
  const t = AS.three, r = t.renderer.domElement.getBoundingClientRect();
  const out = [], v = new THREE.Vector3();
  for (const m of t.pickables) {
    const id = m.userData.id;
    if (!id || out.includes(id)) continue;
    const pos = m.geometry.attributes.position, n = pos.count;
    const step = Math.max(1, Math.ceil(n / 4000));
    let all = true, any = false;
    for (let i = 0; i < n; i += step) {
      v.fromBufferAttribute(pos, i).applyMatrix4(m.matrixWorld).project(t.camera);
      const x = r.left + (v.x + 1) / 2 * r.width, y = r.top + (1 - v.y) / 2 * r.height;
      const inside = x >= xa && x <= xb && y >= ya && y <= yb;
      if (inside) any = true; else all = false;
      if (crossing ? any : !all) break;
    }
    if (crossing ? any : all) out.push(id);
  }
  return out;
}

function dragBlock(c) {
  return c.fixed ? "fixed" : null;
}

/** Local reference of a mate side: a face, a reference plane or axis, an edge or a vertex of the component. */
function sideRef(sd, rc) {
  if (!sd || !rc) return null;
  if (sd.datum) return (rc.datums || {})[sd.datum];
  if (sd.edge !== undefined && sd.edge !== null) return (rc.erefs || [])[sd.edge];
  if (sd.vertex !== undefined && sd.vertex !== null) return (rc.vrefs || [])[sd.vertex];
  return (rc.refs || [])[sd.face];
}
function sideOf(h) {
  return h.datum ? { comp: h.comp, datum: h.datum } : h.edge !== undefined ? { comp: h.comp, edge: h.edge }
    : h.vertex !== undefined ? { comp: h.comp, vertex: h.vertex } : { comp: h.comp, face: h.face };
}
/** Reference of a mate side in world coordinates: {kind, c, p, n} (THREE vectors), or null. */
function worldRef(sd) {
  const live = comp(sd.comp), rc = AS.result && AS.result.components.find(x => x.id === sd.comp);
  if (!live || !rc) return null;
  const r = sideRef(sd, rc);
  if (!r || !r.c) return null;
  const M = compMatrix(live);
  const pt = q => new THREE.Vector3(...q).applyMatrix4(M);
  const kind = r.kind === "line" ? "axis" : r.kind === "circle" ? "cylinder" : r.kind;
  return { kind, r: r.r, c: pt(r.c), p: pt(r.p || r.c), n: r.n ? new THREE.Vector3(...r.n).transformDirection(M) : null };
}

/** Components connected to cid by active mates (cid included) and whether one of them is fixed. A group without a
 *  fixed component is not held in space: a drag moves the whole group in the directions its mates hold cid. */
function mateGroup(cid) {
  const ids = new Set([cid]), todo = [cid];
  while (todo.length) {
    const x = todo.pop();
    for (const m of AS.asm.mates || []) {
      if (m.suppressed || !m.a || !m.b) continue;
      const o = m.a.comp === x ? m.b.comp : m.b.comp === x ? m.a.comp : null;
      if (o && !ids.has(o) && comp(o)) { ids.add(o); todo.push(o); }
    }
  }
  return { ids, grounded: [...ids].some(id => (comp(id) || {}).fixed) };
}

/** Two unit vectors normal to n. */
function perp2(n) {
  const t = Math.abs(n.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
  const u = new THREE.Vector3().crossVectors(n, t).normalize();
  return [u, new THREE.Vector3().crossVectors(n, u).normalize()];
}

/** Directions in which the active mates of a component hold its position (orthonormal, world): the drag moves the
 *  component only normal to them. Mirrors the position conditions of the solver (assembly._residuals): coincident and
 *  distance of planes along the normal of A (an axis with a plane: along the plane normal; two axes: across the axis,
 *  distance: along the offset), concentric across the axis, point in all directions; parallel and angle none. */
function lockedDirs(cid) {
  const dirs = [];
  const line = k => k === "axis" || k === "cylinder";
  for (const m of AS.asm.mates || []) {
    if (m.suppressed || !m.a || !m.b || (m.a.comp !== cid && m.b.comp !== cid) || m.a.comp === m.b.comp) continue;
    const A = worldRef(m.a), B = worldRef(m.b), t = m.type;
    if (!A || !B) continue;
    if (t === "gear" || !A.n || !B.n) { if (t === "point") dirs.push(new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)); continue; }
    if (t === "tangent") {
      if (A.kind === "plane" || B.kind === "plane") dirs.push((A.kind === "plane" ? A : B).n.clone());
      else { const d = B.p.clone().sub(A.p); d.addScaledVector(B.n, -d.dot(B.n)); if (d.length() > 1e-9) dirs.push(d.normalize()); }
      continue;
    }
    if (t === "point") dirs.push(new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1));
    else if (t === "concentric") { if (B.n) dirs.push(...perp2(B.n)); }
    else if ((A.kind === "axis" || B.kind === "axis") && (t === "coincident" || t === "distance")) {
      if (line(A.kind) && line(B.kind)) {
        if (t === "coincident") dirs.push(...perp2(B.n));
        else { const d = B.p.clone().sub(A.p); d.addScaledVector(B.n, -d.dot(B.n)); if (d.length() > 1e-9) dirs.push(d.normalize()); }
      } else { const pl = A.kind === "plane" ? A : B; if (pl.n) dirs.push(pl.n.clone()); }
    } else if ((t === "coincident" || t === "distance") && A.n) dirs.push(A.n.clone());
  }
  return orthoBasis(dirs);
}

/** Orthonormal basis of held directions. A direction within about 3 deg of the span of the earlier ones adds no
 *  restraint (redundant mates, solver residuals), so near-parallel conditions do not lock the component. */
function orthoBasis(dirs, tol = 0.05) {
  const out = [];
  for (const d of dirs) {
    const v = d.clone().normalize();
    for (const e of out) v.addScaledVector(e, -v.dot(e));
    if (v.length() > tol) out.push(v.normalize());
  }
  return out;
}

/** Drag mode: on = "move" (Drag) or "rotate" (Rotate), false: off. */
function setDragMode(on) {
  AS.dragMode = on === true ? "move" : on;
  $("#as-drag").classList.toggle("active", AS.dragMode === "move");
  $("#as-rotate").classList.toggle("active", AS.dragMode === "rotate");
  if (on) AS.matePick = null;
  if (on && AS.measure) setMeasure(false);
  if (AS.three) AS.three.renderer.domElement.style.cursor = "";
  status(AS.dragMode === "move" ? "Drag: left drag moves a component that is not fixed, only in the directions its mates leave free (Shift: along X, Y or Z). D or Esc ends"
    : AS.dragMode === "rotate" ? "Rotate: left drag sideways rotates a component that is not fixed, about the axis its mates leave free, else about the view direction (Shift: 15 deg steps). R or Esc ends"
    : "Drag mode off");
}

/** Axis and pivot of a rotation of a component that its active mates allow: {axis, pivot} (world), {locked} when the
 *  mates hold two different directions, {axis: null} when they hold none (the view direction is used). A plane mate
 *  keeps the plane normal (rotation about it), a concentric or axis mate the axis (rotation about it, the pivot on
 *  the axis), an angle mate the other normal; a point mate fixes the pivot. */
function rotAxis(cid) {
  const line = k => k === "axis" || k === "cylinder";
  let dir = null, pivotLine = null, pivotPoint = null, locked = false;
  const use = d => { if (!d) return; d = d.clone().normalize(); if (!dir) dir = d; else if (Math.abs(d.dot(dir)) < Math.cos(3 * Math.PI / 180)) locked = true; };
  for (const m of AS.asm.mates || []) {
    if (m.suppressed || !m.a || !m.b || (m.a.comp !== cid && m.b.comp !== cid) || m.a.comp === m.b.comp) continue;
    const own = worldRef(m.a.comp === cid ? m.a : m.b), other = worldRef(m.a.comp === cid ? m.b : m.a), t = m.type;
    if (!own || !other || t === "gear") continue;
    if (t === "point") { pivotPoint = other.c; continue; }
    if (!own.n || !other.n) continue;
    if (t === "tangent") { use(own.kind === "plane" ? own.n : other.kind === "plane" ? other.n : other.n); continue; }
    if (t === "concentric" || (line(own.kind) && line(other.kind) && (own.kind === "axis" || other.kind === "axis"))) {
      use(other.n);
      if (t === "concentric" || t === "coincident") pivotLine = { p: other.p, d: other.n.clone().normalize() };
    } else if ((own.kind === "axis" || other.kind === "axis") && ["coincident", "distance", "parallel"].includes(t)) {
      use(own.kind === "plane" ? own.n : other.n);
    } else if (["coincident", "distance", "parallel", "angle"].includes(t)) use(other.n);
  }
  if (locked) return { locked: true };
  return { axis: dir, pivotLine, pivotPoint };
}

/** Hits on the components; with the section on, only on the kept side of the section plane. */
function pickHits(rc) {
  const t = AS.three;
  const hits = rc.intersectObjects(t.pickables, false);
  const pl = sectionOn() && t.clipPlane;
  return pl ? hits.filter(h => pl.distanceToPoint(h.point) >= -1e-6) : hits;
}

function rayAt(e) {
  const t = AS.three;
  const r = t.renderer.domElement.getBoundingClientRect();
  const nd = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster();
  rc.setFromCamera(nd, t.camera);
  return rc;
}

function dragHover(e) {
  AS.mouse = { clientX: e.clientX, clientY: e.clientY };
  if (!AS.drag && !e.buttons && AS.measure && AS.result) {
    const cid = compAt(e);
    if (cid) showPlanesOf(cid);
    const h = mateHitAt(e);
    AS.three.renderer.domElement.style.cursor = h ? "crosshair" : "";
    if (h) status("Measure " + (AS.measure.items.length === 1 ? "B" : "A") + ": " + mateHitText(h));
    return;
  }
  if (!AS.drag && !e.buttons && pickSide() && AS.result) {
    const cid = compAt(e);
    if (cid) showPlanesOf(cid);
    const h = mateHitAt(e, true), ps = pickSide();
    const txt = mateHitText(h);
    AS.three.renderer.domElement.style.cursor = h ? (h.ref && h.ref.kind === "other" ? "not-allowed" : "crosshair") : "";
    if (txt) status(ps.side.toUpperCase() + ": " + txt + (h.ref && h.ref.kind === "other" ? "" : " (click to use)"));
    return;
  }
  if (AS.drag || e.buttons) return;
  if (!AS.dragMode) { if (AS.three) AS.three.renderer.domElement.style.cursor = ""; return; }
  const cid = compAt(e), c = cid && comp(cid);
  AS.three.renderer.domElement.style.cursor = c ? (dragBlock(c) ? "not-allowed" : "move") : "";
}

function dragStart(e) {
  if (!AS.dragMode || e.button !== 0 || pickSide()) return;
  const t = AS.three;
  const hits = pickHits(rayAt(e));
  if (!hits.length) return;
  const cid = hits[0].object.userData.id, c = comp(cid);
  if (!c) return;
  e.stopPropagation();                               // a drag on a component never rotates the view, moved or not
  const why = dragBlock(c);
  if (why) { status(`${c.name} is not moved by dragging (${why}). Unfix it, or edit Position`, true); return; }
  const grp = mateGroup(cid);
  const carry = grp.grounded ? [] : [...grp.ids].filter(id => id !== cid);   // moved with cid in its held directions
  if (AS.dragMode === "rotate") { rotStart(e, cid, c, carry); return; }
  let locked = lockedDirs(cid);
  // held against the mated components in all directions: the preview follows the cursor, the release pulls the
  // chain of mated components (solver) as far as the fixed components and the mates allow
  if (locked.length >= 3 && !carry.length) locked = [];
  const normal = new THREE.Vector3(0, 0, -1).applyQuaternion(t.camera.quaternion);
  AS.drag = { cid, plane: new THREE.Plane().setFromNormalAndCoplanarPoint(normal, hits[0].point), start: hits[0].point.clone(),
              delta: new THREE.Vector3(), objs: t.group.children.filter(o => o.userData.cid === cid), locked,
              carry, carryObjs: t.group.children.filter(o => carry.includes(o.userData.cid)), carryDelta: new THREE.Vector3(),
              live: hasMates(cid) };
  AS.sel = cid; renderComps(); renderProps();
  window.addEventListener("pointermove", dragMove);
  window.addEventListener("pointerup", dragEnd, { once: true });
}

/** Placement matrix of a component without the explode offset. */
function placeMatrix(c) {
  const r = (c.rot || [0, 0, 0]).map(a => (Number(a) || 0) * Math.PI / 180);
  const m = new THREE.Matrix4().makeRotationX(r[0]);
  m.premultiply(new THREE.Matrix4().makeRotationY(r[1]));
  m.premultiply(new THREE.Matrix4().makeRotationZ(r[2]));
  const p = (c.pos || [0, 0, 0]).map(Number);
  m.setPosition(p[0] || 0, p[1] || 0, p[2] || 0);
  return m;
}

function rotStart(e, cid, c, carry = []) {
  const t = AS.three;
  const ra = rotAxis(cid);
  // a group not held in space turns as a whole about the view direction when the mates hold cid against rotation,
  // when cid has no mate axis, or with Ctrl
  const whole = carry.length > 0 && (ra.locked || !ra.axis || e.ctrlKey);
  // held against rotation by its own mates: the solver turns it with the chain it is mated in, as far as the
  // fixed components allow (target: the rotation about the view direction)
  const chain = ra.locked && !whole && hasMates(cid);
  if (ra.locked && !whole && !chain) { status(`${c.name} is held against rotation by its mates (two different axes). Suppress a mate to rotate it`, true); return; }
  const ids = whole ? [cid, ...carry] : [cid];
  const box = new THREE.Box3();
  for (const o of t.pickables) if (ids.includes(o.userData.id)) box.expandByObject(o);
  const centre = box.isEmpty() ? new THREE.Vector3() : box.getCenter(new THREE.Vector3());
  const axis = !whole && ra.axis ? ra.axis : new THREE.Vector3(0, 0, -1).applyQuaternion(t.camera.quaternion).normalize();
  let pivot = centre;
  if (!whole && ra.pivotPoint) pivot = ra.pivotPoint.clone();
  else if (!whole && ra.pivotLine) { const L = ra.pivotLine; pivot = L.p.clone().addScaledVector(L.d, centre.clone().sub(L.p).dot(L.d)); }
  AS.drag = { cid, rotate: true, x0: e.clientX, axis, pivot, angle: 0, quat: new THREE.Quaternion(), ids,
              objs: t.group.children.filter(o => ids.includes(o.userData.cid)),
              about: whole ? "the view direction (with its mated components)" : chain ? "the view direction (the mated components follow)" : ra.axis ? "its mate axis" : "the view direction",
              live: chain };
  AS.sel = cid; renderComps(); renderProps();
  window.addEventListener("pointermove", dragMove);
  window.addEventListener("pointerup", dragEnd, { once: true });
}

function dragMove(e) {
  const d = AS.drag;
  if (!d) return;
  if (d.rotate) {
    let a = (e.clientX - d.x0) * 0.5;                // deg: half a degree per pixel
    if (e.shiftKey) a = Math.round(a / 15) * 15;
    d.angle = a;
    d.quat.setFromAxisAngle(d.axis, a * Math.PI / 180);
    const off = d.pivot.clone().sub(d.pivot.clone().applyQuaternion(d.quat));
    if (d.live) liveSolve(d);
    if (!d.liveSeen) for (const o of d.objs) { o.quaternion.copy(d.quat); o.position.copy(off); }
    status(`${comp(d.cid).name}: ${afmt(a, 1)} deg about ${d.about}`);
    render3();
    return;
  }
  const p = new THREE.Vector3();
  if (!rayAt(e).ray.intersectPlane(d.plane, p)) return;
  const v = p.sub(d.start);
  if (e.shiftKey) {                                  // along the global axis with the largest component
    const a = [Math.abs(v.x), Math.abs(v.y), Math.abs(v.z)], k = a.indexOf(Math.max(...a));
    v.set(k === 0 ? v.x : 0, k === 1 ? v.y : 0, k === 2 ? v.z : 0);
  }
  const raw = v.clone();
  if (d.locked.length >= 3) v.set(0, 0, 0);
  else if (d.locked.length === 2) {                  // free along one line: the cursor's position along it
    const f = new THREE.Vector3().crossVectors(d.locked[0], d.locked[1]).normalize();
    v.copy(f.multiplyScalar(v.dot(f)));
  } else for (const e of d.locked) v.addScaledVector(e, -v.dot(e));   // the held directions removed
  d.raw = raw.clone();
  if (d.carry.length) {                              // group not held in space: the held part moves the whole group
    d.carryDelta.copy(raw).sub(v);
    v.copy(raw);
    if (!d.liveSeen) for (const o of d.carryObjs) o.position.copy(d.carryDelta);
  }
  d.delta.copy(v);
  if (d.live) liveSolve(d);
  if (!d.liveSeen) for (const o of d.objs) o.position.copy(v);
  const c = comp(d.cid);
  status(`${c.name}: dx ${afmt(v.x, 2)}, dy ${afmt(v.y, 2)}, dz ${afmt(v.z, 2)} mm`);
  render3();
}

/** Solver pull of a drag: the grabbed point follows the cursor movement (rotation drag: the target placement). */
function dragReq(d, limit) {
  const skip = Object.keys(AS.conflicts || {});             // left out by the last solve: not solved again on each move
  if (d.rotate) { const tp = rotTarget(d); return { comp: d.cid, pos: tp.pos, rot: tp.rot, limit, skip }; }
  return { comp: d.cid, delta: (d.raw || d.delta).toArray(), grab: d.start.toArray(), limit, skip };
}

/** Placement of the dragged component after the rotation of a rotation drag: {pos, rot}. */
function rotTarget(d) {
  const c = comp(d.cid);
  const T = new THREE.Matrix4().makeTranslation(d.pivot.x, d.pivot.y, d.pivot.z)
    .multiply(new THREE.Matrix4().makeRotationFromQuaternion(d.quat))
    .multiply(new THREE.Matrix4().makeTranslation(-d.pivot.x, -d.pivot.y, -d.pivot.z));
  const M = T.multiply(placeMatrix(c));
  const eu = new THREE.Euler().setFromRotationMatrix(M, "ZYX");
  const p = new THREE.Vector3().setFromMatrixPosition(M);
  return { pos: [p.x, p.y, p.z].map(x => Math.round(x * 1e4) / 1e4), rot: [eu.x, eu.y, eu.z].map(x => Math.round(x * 180 / Math.PI * 1e4) / 1e4) };
}

/** Live drag of a component with mates: the solver pull at the current cursor movement, one request at a time; the
 *  components are drawn at the returned placements (outer group transform = new placement x old placement^-1). */
async function liveSolve(d) {
  if (d.busy) { d.pending = true; return; }
  d.busy = true;
  const ms = (AS.asm.mates || []).filter(m => !m.suppressed && m.a && m.b);
  try {
    const r = await postJSON("/api/assembly/solve", { assembly: Object.assign({}, AS.asm, { mates: ms }), drag: dragReq(d, 0.3) });
    const j = await r.json();
    if (AS.drag !== d) return;
    const t = AS.three;
    let n = 0;
    for (const o of t.group.children) {
      const pl = j.placements[o.userData.cid], live = comp(o.userData.cid);
      if (!pl || !live) continue;
      const M = compMatrix(Object.assign({}, live, { pos: pl.pos, rot: pl.rot })).multiply(compMatrix(live).invert());
      M.decompose(o.position, o.quaternion, o.scale);
      n++;
    }
    d.liveSeen = true;
    const cnt = new Set(Object.keys(j.placements)).size;
    status(`${comp(d.cid).name}: ${cnt > 1 ? cnt - 1 + " mated component(s) follow" : "moving"}`);
    render3();
  } catch (e) { /* the release solves again */ }
  finally {
    d.busy = false;
    if (d.pending && AS.drag === d) { d.pending = false; liveSolve(d); }
  }
}

function dragEnd() {
  window.removeEventListener("pointermove", dragMove);
  const d = AS.drag;
  AS.drag = null;
  if (!d) return;
  const c = comp(d.cid);
  if (d.rotate) {
    if (!c || Math.abs(d.angle) < 1e-9) return;
    if (d.live) { solveMates(false, dragReq(d, 1.5)); return; }
    const T = new THREE.Matrix4().makeTranslation(d.pivot.x, d.pivot.y, d.pivot.z)
      .multiply(new THREE.Matrix4().makeRotationFromQuaternion(d.quat))
      .multiply(new THREE.Matrix4().makeTranslation(-d.pivot.x, -d.pivot.y, -d.pivot.z));
    for (const id of d.ids) {
      const x = comp(id);
      if (!x) continue;
      const M = T.clone().multiply(placeMatrix(x));
      const eu = new THREE.Euler().setFromRotationMatrix(M, "ZYX");
      const p = new THREE.Vector3().setFromMatrixPosition(M);
      x.pos = [p.x, p.y, p.z].map(v => Math.round(v * 1e4) / 1e4);
      x.rot = [eu.x, eu.y, eu.z].map(v => Math.round(v * 180 / Math.PI * 1e4) / 1e4);
    }
    status(`${c.name}${d.ids.length > 1 ? " and " + (d.ids.length - 1) + " mated component(s)" : ""} rotated ${afmt(d.angle, 1)} deg`);
    changedAsm();
    return;
  }
  if (!c || d.delta.lengthSq() < 1e-12) return;
  if (hasMates(d.cid)) {                             // the solver moves the component and the chain it is mated in
    solveMates(false, dragReq(d, 1.5));
    return;
  }
  const add = (x, v) => { const p = x.pos || [0, 0, 0]; x.pos = [p[0] + v.x, p[1] + v.y, p[2] + v.z].map(q => Math.round(q * 1e4) / 1e4); };
  add(c, d.delta);
  if (d.carry.length && d.carryDelta.lengthSq() > 1e-12) for (const id of d.carry) if (comp(id)) add(comp(id), d.carryDelta);
  status(`${c.name} moved to ${c.pos.map(x => afmt(x, 3)).join(", ")} mm` + (d.carry.length && d.carryDelta.lengthSq() > 1e-12 ? `, with ${d.carry.length} mated component(s)` : ""));
  changedAsm();
}

/** Id of the component under the cursor, or null. */
function compAt(e) {
  const t = AS.three;
  const r = t.renderer.domElement.getBoundingClientRect();
  const nd = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster();
  rc.setFromCamera(nd, t.camera);
  const hits = pickHits(rc);
  return hits.length ? hits[0].object.userData.id : null;
}

/** What a click would pick for a mate side: {comp, face, ref} for a planar or cylindrical face, {comp, datum, name}
 *  for a reference plane or axis of a component (axes within 6 px first, planes only off the parts), or null. */
function mateHitAt(e, geo) {
  const t = AS.three;
  const rc = rayAt(e);
  const r = t.renderer.domElement.getBoundingClientRect();
  const px = (t.camera.right - t.camera.left) / t.camera.zoom / r.width;
  if (geo && $("#as-edgepick") && $("#as-edgepick").checked) { const g = geoHitAt(e, rc); if (g) return g; }
  rc.params.Line.threshold = px * 6;
  const dh = rc.intersectObjects((t.datumPickables || []).filter(o => o.visible), false);
  const axis = dh.find(h => h.object.isLine);
  if (axis) return { comp: axis.object.userData.cid, datum: axis.object.userData.datum, name: axis.object.userData.name };
  const hits = pickHits(rc);
  if (hits.length) {
    const h = hits[0], cid = h.object.userData.id;
    const c = AS.result.components.find(x => x.id === cid);
    const fi = c && c.mesh ? c.mesh.face_of_tri[h.faceIndex] : null;
    const ref = c && c.refs ? c.refs[fi] : null;
    if (fi === null || fi === undefined || !ref) return null;
    return { comp: cid, face: fi, ref };
  }
  const plane = dh.find(h => !h.object.isLine);
  return plane ? { comp: plane.object.userData.cid, datum: plane.object.userData.datum, name: plane.object.userData.name } : null;
}

/** Vertex within 8 px or edge within 5 px of the cursor on the visible side of the components (Edges and vertices
 *  checked): {comp, vertex, ref} or {comp, edge, ref}. */
function geoHitAt(e, rc) {
  const t = AS.three, r = t.renderer.domElement.getBoundingClientRect();
  const sx = e.clientX - r.left, sy = e.clientY - r.top;
  const scr = v => { const q = v.clone().project(t.camera); return [(q.x + 1) / 2 * r.width, (1 - q.y) / 2 * r.height, q.z]; };
  const front = pickHits(rc);
  const depth = front.length ? front[0].distance : Infinity;
  const visible = w => rc.ray.origin.distanceTo(w) <= depth + 1e-3 * Math.max(1, depth) || !isFinite(depth) ||
    Math.abs(new THREE.Vector3().subVectors(w, rc.ray.origin).dot(rc.ray.direction) - depth) < (AS.bbox ? 1e-3 * Math.hypot(AS.bbox[3] - AS.bbox[0], AS.bbox[4] - AS.bbox[1], AS.bbox[5] - AS.bbox[2]) : 0.01);
  let best = null, bd = 8;
  for (const c of (AS.result && AS.result.components) || []) {
    const live = comp(c.id);
    if (!live || live.visible === false || !c.mesh) continue;
    const M = compMatrix(live);
    (c.vrefs || []).forEach((v, i) => {
      const w = new THREE.Vector3(...v.c).applyMatrix4(M), s = scr(w);
      const d = Math.hypot(s[0] - sx, s[1] - sy);
      if (d < bd && visible(w)) { bd = d; best = { comp: c.id, vertex: i, ref: v }; }
    });
  }
  if (best) return best;
  bd = 5;
  for (const c of (AS.result && AS.result.components) || []) {
    const live = comp(c.id);
    if (!live || live.visible === false || !c.mesh || !c.mesh.edge_ids) continue;
    const M = compMatrix(live);
    c.mesh.edges.forEach((pl, k) => {
      const ei = c.mesh.edge_ids[k];
      for (let j = 0; j + 1 < pl.length; j++) {
        const a = new THREE.Vector3(...pl[j]).applyMatrix4(M), b = new THREE.Vector3(...pl[j + 1]).applyMatrix4(M);
        const sa = scr(a), sb = scr(b);
        const dx = sb[0] - sa[0], dy = sb[1] - sa[1], L2 = dx * dx + dy * dy;
        const u = L2 > 0 ? Math.max(0, Math.min(1, ((sx - sa[0]) * dx + (sy - sa[1]) * dy) / L2)) : 0;
        const d = Math.hypot(sa[0] + u * dx - sx, sa[1] + u * dy - sy);
        if (d < bd && visible(a.clone().lerp(b, u))) { bd = d; best = { comp: c.id, edge: ei, ref: (c.erefs || [])[ei] }; }
      }
    });
  }
  return best && best.ref ? best : null;
}

function refText(r) {
  if (!r) return "?";
  if (r.kind === "point") return "vertex (" + r.c.map(v => afmt(v, 2)).join(", ") + ")";
  if (r.kind === "line") return "edge, line " + afmt(r.len, 2) + " mm";
  if (r.kind === "circle") return "edge, circle Ø" + afmt(2 * r.r, 2);
  if (r.kind === "edge") return "edge, curve " + afmt(r.len, 2) + " mm (Point mate only)";
  return r.kind + (r.r ? " Ø" + afmt(2 * r.r, 2) : "");
}

function mateHitText(h) {
  if (!h) return "";
  if (h.datum) return compName(h.comp) + " : " + h.name;
  if (h.edge !== undefined || h.vertex !== undefined) return compName(h.comp) + " : " + refText(h.ref);
  return compName(h.comp) + " : " + (h.ref.kind === "other" ? "face (not planar or cylindrical)" : h.ref.kind + (h.ref.r ? " Ø" + afmt(2 * h.ref.r, 2) : ""));
}

/** The side a click fills: the side being picked, or the empty side of the selected mate. */
function pickSide() {
  if (AS.matePick) return AS.matePick;
  const m = AS.selMate && mate(AS.selMate);
  if (m && !m.suppressed && AS.noAutoPick !== m.id && (!m.a || !m.b)) return { mateId: m.id, side: m.a ? "b" : "a" };
  return null;
}

function pickComponent(e) {
  const t = AS.three;
  if (AS.measure) { measureClick(e); return; }
  const ps = pickSide();
  if (ps) {
    const h = mateHitAt(e, true);
    if (!h) return;
    if (h.ref && h.ref.kind === "other") return msg("This face is not planar or cylindrical", true);
    const m = mate(ps.mateId);
    if (!m) { AS.matePick = null; return; }
    m[ps.side] = sideOf(h);
    if (m.type === "gear" && m.a && m.b) setGearRef(m);
    if (ps.side === "a" && !m.b) AS.matePick = { mateId: m.id, side: "b" };
    else AS.matePick = null;
    AS.dirty = true;
    msg(ps.side.toUpperCase() + ": " + mateHitText(h));
    if (!pickSide()) t.renderer.domElement.style.cursor = "";
    autoFlip(m);
    renderMates(); setMeshes(AS.result);
    if (!AS.matePick && m.a && m.b) solveMates();
    return;
  }
  const hits = pickHits(rayAt(e));
  if (!hits.length) { if (AS.multi) { AS.multi = null; renderComps(); setMeshes(AS.result); } return; }
  const cid = hits[0].object.userData.id;
  AS.multi = null;
  AS.sel = cid;
  renderComps(); renderProps(); setMeshes(AS.result);
}
function msg(text, isError) { status(text, isError); }
function mate(id) { return (AS.asm.mates || []).find(m => m.id === id); }

/** Local meshes of the component sources, kept between builds by mkey: {mesh, refs, geo, edgeGeo}. The server sends a
 *  mesh only for an mkey the client does not hold; components are placed by their matrix. */
const MESHES = new Map();

function meshEntry(mkey) {
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

/** Stores the meshes of a build result, fills c.mesh and c.refs from the store and drops meshes no longer used. */
function takeMeshes(res) {
  for (const c of res.components) if (c.mesh && !c.mkey) { c.mkey = "w" + AS.seq + "_" + c.id; c.placed = true; }  // placed mesh (server before the cache)
  for (const c of res.components) if (c.mkey && c.mesh) {
    const old = MESHES.get(c.mkey);
    if (old && old.geo) { old.geo.dispose(); old.edgeGeo.dispose(); }
    MESHES.set(c.mkey, { mesh: c.mesh, refs: c.refs || [], datums: c.datums || {}, erefs: c.erefs || [], vrefs: c.vrefs || [] });
  }
  const used = new Set();
  let missing = false;
  for (const c of res.components) if (c.mkey) {
    const e = MESHES.get(c.mkey);
    if (e) { c.mesh = e.mesh; c.refs = e.refs; c.datums = e.datums; c.erefs = e.erefs; c.vrefs = e.vrefs; used.add(c.mkey); }
    else { c.error = c.error || "mesh missing"; missing = true; }
  }
  if (missing) scheduleBuild();                       // a mesh was dropped while the request was under way
  for (const [k, e] of MESHES) if (!used.has(k)) { if (e.geo) { e.geo.dispose(); e.edgeGeo.dispose(); } MESHES.delete(k); }
}

/** Placement of a component from its current pos, rot and explode offset (assembly.trsf_of: rotations about the
 *  fixed X, then Y, then Z axis, then the translation). */
function compMatrix(c) {
  const r = (c.rot || [0, 0, 0]).map(a => (Number(a) || 0) * Math.PI / 180);
  const m = new THREE.Matrix4().makeRotationX(r[0]);
  m.premultiply(new THREE.Matrix4().makeRotationY(r[1]));
  m.premultiply(new THREE.Matrix4().makeRotationZ(r[2]));
  const p = (c.pos || [0, 0, 0]).map(Number);
  if ($("#as-explode").checked) (c.explode || [0, 0, 0]).forEach((e, k) => { p[k] += Number(e) || 0; });
  m.setPosition(p[0] || 0, p[1] || 0, p[2] || 0);
  return m;
}

/** Draws the meshes of the last build result at the current placement of each component (a moved, dragged or
 *  solved component is drawn at its new place before the next build returns). */
function setMeshes(res) {
  const t = AS.three;
  if (!t) return;
  for (const g of t.tempGeo || []) g.dispose();
  t.tempGeo = [];
  t.group.clear();
  t.pickables = [];
  t.datumPickables = [];
  t.datumPlanes = [];
  t.clipMats = [];
  AS.result = res;
  const box = new THREE.Box3();
  const sec = sectionOn();
  const selM = AS.selMate && mate(AS.selMate);
  const focusSet = isolateSet();
  if (res) for (const [i, c] of res.components.entries()) {
    const m = c.mesh;
    const e = c.mkey && meshEntry(c.mkey);
    const live = comp(c.id);
    if (!live || !m || !e || !m.vertices.length || live.visible === false) continue;
    const outer = new THREE.Group();                  // moved by Drag
    outer.userData.cid = c.id;
    const inner = new THREE.Group();                  // component placement
    inner.matrixAutoUpdate = false;
    if (!c.placed) inner.matrix.copy(compMatrix(live));
    outer.add(inner);
    t.group.add(outer);
    const col = new THREE.Color(live.color || PALETTE[AS.asm.components.indexOf(live) % PALETTE.length]);
    const sel = selIds().has(c.id);
    const disp = displayMode(), lines = disp === "hidden" || disp === "wire";
    const ghost = focusSet && !focusSet.has(c.id);         // Isolate: the other components faint, not pickable
    // selected: the own colour with a faint orange glow and orange edges (the colour stays recognisable)
    const mat = new THREE.MeshStandardMaterial({ color: col, emissive: sel ? 0x5a2200 : 0x000000, metalness: 0.15, roughness: 0.6, side: sec ? THREE.FrontSide : THREE.DoubleSide,
                                                 polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    if (disp === "transparent") { mat.transparent = true; mat.opacity = sel ? 0.5 : 0.25; mat.depthWrite = false; mat.side = THREE.DoubleSide; }
    if (lines) { mat.colorWrite = false; mat.depthWrite = disp === "hidden"; }   // pickable; hidden lines: depth only
    if (ghost) { mat.transparent = true; mat.opacity = 0.07; mat.depthWrite = false; mat.colorWrite = true; }
    const mesh = new THREE.Mesh(e.geo, mat);
    mesh.userData = { id: c.id };
    inner.add(mesh);
    if (!ghost) t.pickables.push(mesh);
    t.clipMats.push(mat);
    if (sec && !lines && disp !== "transparent" && !ghost) {     // section: the inside faces in a darker flat colour (cut surface)
      const cap = new THREE.MeshBasicMaterial({ color: col.clone().multiplyScalar(0.55), side: THREE.BackSide });
      inner.add(new THREE.Mesh(e.geo, cap));
      t.clipMats.push(cap);
    }
    // faces of the selected mate (orange), of the linked mates (blue)
    const hl = [];
    if (selM) for (const side of ["a", "b"]) if (selM[side] && selM[side].comp === c.id) hl.push([selM[side].face, 0xe8590c]);
    if (AS.measure) for (const it of AS.measure.items) if (it.comp === c.id && it.face !== undefined) hl.push([it.face, MEAS_COL]);
    if (!selM && AS.mateFilter) for (const lm of matesOf(AS.mateFilter)) for (const side of ["a", "b"]) if (lm[side] && lm[side].comp === c.id) hl.push([lm[side].face, 0x1c7ed6]);
    for (const [fi, color] of hl) {
      const pos = [];                                  // own vertices: disposing it leaves the shared mesh buffers alone
      m.triangles.forEach((tr, k) => { if (m.face_of_tri[k] === fi) for (const v of tr) pos.push(...m.vertices[v]); });
      if (!pos.length) continue;
      const sg = new THREE.BufferGeometry();
      sg.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      t.tempGeo.push(sg);
      inner.add(new THREE.Mesh(sg, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })));
    }
    if (!ghost && ($("#as-edges").checked || disp !== "shaded" || sel)) {
      const lc = sel ? 0xe8590c : disp === "shaded" ? 0x1d2125 : disp === "transparent" ? col.clone().multiplyScalar(0.5) : 0x1d2125;
      const lm = new THREE.LineBasicMaterial({ color: lc, transparent: disp === "transparent", opacity: disp === "transparent" ? 0.7 : 1 });
      inner.add(new THREE.LineSegments(e.edgeGeo, lm));
      t.clipMats.push(lm);
    }
    // edges and vertices of the selected mate (orange)
    if (selM) for (const side of ["a", "b"]) {
      const sd = selM[side];
      if (!sd || sd.comp !== c.id) continue;
      if (sd.edge !== undefined && sd.edge !== null && m.edge_ids) {
        const pos = [];
        m.edges.forEach((pl, k) => { if (m.edge_ids[k] === sd.edge) for (let j = 0; j + 1 < pl.length; j++) pos.push(...pl[j], ...pl[j + 1]); });
        if (pos.length) {
          const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); t.tempGeo.push(g);
          const lm = new THREE.LineBasicMaterial({ color: 0xe8590c, depthTest: false }); const ls = new THREE.LineSegments(g, lm); ls.renderOrder = 5; inner.add(ls);
        }
      }
      if (sd.vertex !== undefined && sd.vertex !== null && (c.vrefs || [])[sd.vertex]) {
        const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(c.vrefs[sd.vertex].c, 3)); t.tempGeo.push(g);
        const pm = new THREE.Points(g, new THREE.PointsMaterial({ color: 0xe8590c, size: 9, sizeAttenuation: false, depthTest: false })); pm.renderOrder = 5; inner.add(pm);
      }
    }
    // reference planes and axes: of the selected mate (orange), of the selected component with Datums (purple)
    const ds = c.datums || {};
    if (selM) for (const side of ["a", "b"]) { const sd = selM[side]; if (sd && sd.comp === c.id && sd.datum && ds[sd.datum]) addDatum(inner, ds[sd.datum], 0xe8590c, 0.18); }
    // with Datums checked while a mate side is picked: the reference axes of every component and the reference
    // planes of the last component under the cursor, pickable
    if ((pickSide() || AS.measure) && $("#as-datums") && $("#as-datums").checked) for (const [k, d] of Object.entries(ds)) addDatum(inner, d, 0x7048e8, 0.04, { cid: c.id, datum: k, name: d.name });
    if (AS.measure) for (const it of AS.measure.items) if (it.comp === c.id && it.datum && ds[it.datum]) addDatum(inner, ds[it.datum], MEAS_COL, 0.18);
    else if ($("#as-datums") && $("#as-datums").checked && c.id === AS.sel) for (const d of Object.values(ds)) addDatum(inner, d, 0x7048e8, 0.06);
    box.union(e.geo.boundingBox.clone().applyMatrix4(inner.matrix));
  }
  drawMeasureLine();
  t.group.updateMatrixWorld(true);
  const bb = box.isEmpty() ? null : [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z];
  AS.bbox = bb;
  updateSection();
  updateAxes(t.scene, bb, $("#as-axes").checked);
  if (!t.zoomed && bb) { view("iso"); t.zoomed = true; } else render3();
}

/** Display of the components: "shaded", "transparent", "hidden" (hidden lines removed) or "wire". */
function displayMode() { const el = $("#as-display"); return el ? el.value : "shaded"; }

/** Isolate (mates window): the components of the selected mate, or the component of the mate filter and the
 *  components mated to it; null when Isolate is off or nothing is selected. */
function isolateSet() {
  if (!$("#as-isolate") || !$("#as-isolate").checked) return null;
  const set = new Set();
  const m = AS.selMate && mate(AS.selMate);
  if (m) { for (const sd of [m.a, m.b]) if (sd && sd.comp) set.add(sd.comp); }
  else if (AS.mateFilter) { set.add(AS.mateFilter); for (const x of matesOf(AS.mateFilter)) for (const sd of [x.a, x.b]) if (sd && sd.comp) set.add(sd.comp); }
  return set.size ? set : null;
}

const MEAS_COL = 0x0ca678;

/** Measure mode: on / off. */
function setMeasure(on) {
  AS.measure = on ? { items: [], res: null } : null;
  if (on) { if (AS.dragMode) setDragMode(false); AS.matePick = null; AS.noAutoPick = AS.selMate; }
  $("#as-measure-btn").classList.toggle("active", !!on);
  $("#as-measure").hidden = !on;
  renderMeasure();
  if (AS.three) AS.three.renderer.domElement.style.cursor = "";
  setMeshes(AS.result);
  status(on ? "Measure: click a face (with Datums: also a reference plane or axis), then a second one. Esc ends" : "Measuring ended");
}
function renderMeasure() {
  const m = AS.measure;
  if (!m) return;
  $("#as-measure-body").innerHTML = measureHtml(m.res, m.res ? (m.items.length < 2 ? "Click a second item to measure between them." : "A click starts a new measurement.") : "Click a face, or with Datums a reference plane or axis.");
}
async function measureClick(e) {
  const h = mateHitAt(e);
  if (!h) return;
  const m = AS.measure;
  if (m.items.length >= 2) m.items = [];
  m.items.push(h.datum ? { comp: h.comp, datum: h.datum } : { comp: h.comp, face: h.face });
  m.res = null;
  setMeshes(AS.result);
  try {
    const r = await postJSON("/api/assembly/measure", { assembly: AS.asm, items: m.items });
    const j = await r.json();
    if (AS.measure !== m) return;
    m.res = j;
    renderMeasure();
    setMeshes(AS.result);
    const md = (j.rows.find(x => x[0] === "Minimum distance") || [])[1];
    status(md ? "Minimum distance " + md : j.rows.length ? j.rows[0][0] + ": " + j.rows[0][1] : "");
  } catch (err) { showErr(err); }
}
/** The minimum distance of the measurement as a line between the closest points (drawn over the parts). */
function drawMeasureLine() {
  const m = AS.measure, t = AS.three;
  if (!m || !m.res || !m.res.points || m.items.length < 2) return;
  const [a, b] = m.res.points;
  const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...a), new THREE.Vector3(...b)]);
  t.tempGeo.push(g);
  const ln = new THREE.Line(g, new THREE.LineBasicMaterial({ color: MEAS_COL, depthTest: false }));
  ln.renderOrder = 12;
  t.group.add(ln);
  const r = Math.max(((AS.bbox && Math.max(AS.bbox[3] - AS.bbox[0], AS.bbox[4] - AS.bbox[1], AS.bbox[5] - AS.bbox[2])) || 100) / 250, 0.2);
  for (const p of [a, b]) {
    const sg = new THREE.SphereGeometry(r, 12, 8);
    t.tempGeo.push(sg);
    const s = new THREE.Mesh(sg, new THREE.MeshBasicMaterial({ color: MEAS_COL, depthTest: false }));
    s.position.set(...p);
    s.renderOrder = 12;
    t.group.add(s);
  }
}

function sectionOn() { const el = $("#as-sec"); return !!(el && el.checked); }

/** Section plane: normal to X, Y or Z at the slider position within the assembly extents; the side below the plane
 *  is kept (Reverse: above). One plane shared by all component materials. */
function updateSection() {
  const t = AS.three;
  if (!t) return;
  const on = sectionOn() && AS.bbox;
  if (!t.clipPlane) t.clipPlane = new THREE.Plane();
  if (on) {
    const k = { x: 0, y: 1, z: 2 }[$("#as-sec-axis").value] || 0, b = AS.bbox;
    const lo = b[k], hi = b[k + 3], f = (+$("#as-sec-pos").value || 0) / 1000;
    const at = lo + (hi - lo) * f, n = new THREE.Vector3(k === 0 ? 1 : 0, k === 1 ? 1 : 0, k === 2 ? 1 : 0);
    const flip = $("#as-sec-flip").checked;
    t.clipPlane.normal.copy(flip ? n : n.negate());
    t.clipPlane.constant = flip ? -at : at;
    $("#as-sec-pos").title = "Section at " + "XYZ"[k] + " = " + afmt(at, 2) + " mm";
  }
  for (const m of t.clipMats || []) {
    const want = on ? 1 : 0;
    if ((m.clippingPlanes || []).length !== want) { m.clippingPlanes = on ? [t.clipPlane] : []; m.needsUpdate = true; }
  }
}

function view(name) {
  const t = AS.three;
  if (!t) return;
  const bb = AS.bbox || [-50, -50, -50, 50, 50, 50];
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

// ------------------------------------------------------------------ build

function scheduleBuild() { clearTimeout(AS.timer); AS.timer = setTimeout(build, 150); }

async function build() {
  const seq = ++AS.seq;
  $("#as-info").textContent = "Building...";
  try {
    const r = await postJSON("/api/assembly/build", { assembly: AS.asm, explode: $("#as-explode").checked, have: [...MESHES.keys()],
                                                       interference: $("#as-interf").checked, density: numv($("#density").value) || 0 });
    const j = await r.json();
    if (seq !== AS.seq) return;
    takeMeshes(j);
    AS.errors = {};
    for (const c of j.components) if (c.error) AS.errors[c.id] = c.error;
    setMeshes(j);
    const bb = AS.bbox;
    const n = j.components.filter(c => c.mesh).length;
    $("#as-info").textContent = (bb ? `${n} component(s), size ${afmt(bb[3] - bb[0], 2)} x ${afmt(bb[4] - bb[1], 2)} x ${afmt(bb[5] - bb[2], 2)} mm` : "No solids") +
      (j.interference ? `, ${j.interference.length} interference(s)` : "");
    renderMass(j.mass, j.interference);
    renderComps();
    renderMates();
  } catch (e) { if (seq === AS.seq) { $("#as-info").textContent = ""; showErr(e); } }
}

function renderMass(mass, interf) {
  const box = $("#as-mass");
  if (!mass || !mass.rows.length) { box.innerHTML = ""; $("#as-interf-out").innerHTML = ""; return; }
  const rho = numv($("#density").value) || 0;
  const rows = mass.rows.map(r => `<tr><td>${aesc(r.name)}</td><td>${afmt(r.volume_mm3 / 1000, 2)} cm^3</td><td>${r.density > 0 ? afmt(r.mass_kg, 4) + " kg" : "-"}</td></tr>`).join("");
  const t = mass.total;
  box.innerHTML = `<table class="as-mass">${rows}<tr><td><strong>Total</strong></td><td>${afmt(t.volume_mm3 / 1000, 2)} cm^3</td><td>${t.mass_kg > 0 ? afmt(t.mass_kg, 4) + " kg" : "-"}</td></tr></table>` +
    (t.cog ? `<p class="hint">Centre of mass x ${afmt(t.cog[0], 2)}, y ${afmt(t.cog[1], 2)}, z ${afmt(t.cog[2], 2)} mm</p>` : `<p class="hint">Mass needs a density: Views > Density, or per component.</p>`);
  const io = $("#as-interf-out");
  if (!interf) io.innerHTML = "";
  else if (!interf.length) io.innerHTML = '<p class="hint">No interference.</p>';
  else io.innerHTML = "<p class=\"as-bad\">Interference:</p>" + interf.map(x => `<p class="as-bad">${aesc(x.a_name)} / ${aesc(x.b_name)}: ${afmt(x.volume_mm3, 2)} mm^3</p>`).join("");
}

// ------------------------------------------------------------------ component list and properties

/** Undo history of the components and mates: a state is added when it differs from the current one. */
function snapAsm() {
  if (!AS.asm) return;
  const j = JSON.stringify({ components: AS.asm.components, mates: AS.asm.mates || [] });
  AS.hist = AS.hist || [];
  if (AS.hist[AS.hpos] === j) return;
  AS.hist = AS.hist.slice(0, (AS.hpos ?? -1) + 1);
  AS.hist.push(j);
  if (AS.hist.length > 60) AS.hist.shift();
  AS.hpos = AS.hist.length - 1;
  AS.check = null;                                   // the check is of the state before
}
function undoAsm(step) {
  snapAsm();
  const k = (AS.hpos ?? 0) + step;
  if (!AS.hist || k < 0 || k >= AS.hist.length) { status(step < 0 ? "Nothing to undo" : "Nothing to redo"); return; }
  AS.hpos = k;
  const st = JSON.parse(AS.hist[k]);
  AS.asm.components = st.components;
  AS.asm.mates = st.mates;
  AS.unsat = {}; AS.check = null; AS.dirty = true;
  if (AS.sel && !comp(AS.sel)) AS.sel = null;
  if (AS.selMate && !mate(AS.selMate)) AS.selMate = null;
  AS.matePick = null;
  renderComps(); renderProps(); renderMates();
  if (AS.result) setMeshes(AS.result);
  scheduleBuild();
  status(step < 0 ? "Undone (Ctrl+Y redoes)" : "Redone");
}

function changedAsm(rebuild) {
  AS.dirty = true;
  snapAsm();
  renderComps(); renderProps();
  if (AS.result) setMeshes(AS.result);               // current placements at once; the build follows
  if (rebuild !== false) scheduleBuild();
}

function srcText(c) {
  const s = c.source || {};
  if (s.type === "part") return "part " + s.name;
  const base = (s.path || "").split(/[\\/]/).pop();
  return base + (s.part !== undefined && s.part !== null && s.part !== "" ? " : " + s.part : "");
}

/** The colour swatches of the component list (without rebuilding the rows). */
function renderCompSwatches() {
  document.querySelectorAll("#as-comps .as-comp[data-id]").forEach(row => {
    const c = comp(row.dataset.id), sw = row.querySelector(".sw");
    if (c && sw) sw.style.background = c.color || PALETTE[AS.asm.components.indexOf(c) % PALETTE.length];
  });
}

function renderComps() {
  const box = $("#as-comps");
  const cs = AS.asm.components;
  if (!cs.length) { box.innerHTML = '<p class="hint">Add a saved part or a STEP file.</p>'; return; }
  box.innerHTML = cs.map((c, i) => {
    const err = (AS.errors || {})[c.id];
    return `<div class="as-comp${selIds().has(c.id) ? " sel" : ""}${c.visible === false ? " hid" : ""}" data-id="${aesc(c.id)}">` +
      `<input type="checkbox" data-k="vis" title="Visible"${c.visible === false ? "" : " checked"}>` +
      `<span class="sw" style="background:${aesc(c.color || PALETTE[i % PALETTE.length])}"></span>` +
      `<span class="nm" title="${aesc(srcText(c))}">${aesc(c.name)}</span>` +
      `<span class="ops"><button type="button" data-k="up" title="Move up">&#9650;</button><button type="button" data-k="down" title="Move down">&#9660;</button></span>` +
      (err ? `<span class="err">${aesc(err)}</span>` : "") +
      (AS.check && AS.check.components[c.id] ? `<span class="dof dof-${AS.check.components[c.id].status.replace(" ", "")}">${aesc(AS.check.components[c.id].text.replace(" (other components held)", ""))}</span>` : "") + "</div>";
  }).join("");
  box.querySelectorAll(".as-comp").forEach(row => {
    const id = row.dataset.id;
    row.onclick = e => {
      const k = e.target.dataset && e.target.dataset.k;
      const i = cs.findIndex(c => c.id === id);
      if (k === "vis") { comp(id).visible = e.target.checked; changedAsm(); return; }
      if (k === "up" && i > 0) { [cs[i - 1], cs[i]] = [cs[i], cs[i - 1]]; changedAsm(false); return; }
      if (k === "down" && i < cs.length - 1) { [cs[i + 1], cs[i]] = [cs[i], cs[i + 1]]; changedAsm(false); return; }
      if (e.ctrlKey || e.metaKey) { toggleSelect(id); return; }
      AS.multi = null; AS.sel = id; renderComps(); renderProps(); setMeshes(AS.result);
    };
    row.oncontextmenu = e => { e.preventDefault(); showCompMenu(id, e.clientX, e.clientY); };
  });
}

// ------------------------------------------------------------------ component menu (right click in the list or the view)

function closeCompMenu() { const m = document.getElementById("as-menu"); if (m) m.remove(); }
function matesOf(cid) { return (AS.asm.mates || []).filter(m => (m.a && m.a.comp === cid) || (m.b && m.b.comp === cid)); }
function mateText(m, cid) {
  const other = m.a && m.a.comp !== cid ? m.a.comp : m.b && m.b.comp !== cid ? m.b.comp : null;
  return (m.name || MATE_TYPES[m.type] || m.type) + (other ? " with " + compName(other) : " (one face picked)") + (m.suppressed ? " (suppressed)" : "");
}

function showCompMenu(cid, x, y) {
  closeCompMenu();
  const c = comp(cid);
  if (!c) return;
  const multi = selIds().size > 1 && selIds().has(cid) ? [...selIds()] : null;
  if (!multi) AS.multi = null;
  AS.sel = cid; renderComps(); renderProps(); setMeshes(AS.result);
  const ms = matesOf(cid);
  const src = c.source || {};
  const multiItems = multi ? [
    [`Hide the ${multi.length} selected components`, () => { multi.forEach(id => { comp(id).visible = false; }); AS.multi = null; renderComps(); changedAsm(); }],
    [`Show only the ${multi.length} selected components`, () => { AS.asm.components.forEach(x => { x.visible = multi.includes(x.id); }); renderComps(); changedAsm(); }],
    [`Fix the ${multi.length} selected components in space`, () => { multi.forEach(id => { comp(id).fixed = true; }); changedAsm(false); }],
    [`Unfix the ${multi.length} selected components`, () => { multi.forEach(id => { comp(id).fixed = false; }); changedAsm(false); }],
    null] : [];
  const items = multiItems.concat([
    [c.fixed ? "Unfix (moved by mates)" : "Fix in space", () => { c.fixed = !c.fixed; changedAsm(false); status(c.name + (c.fixed ? " fixed" : " not fixed")); }],
    [src.type === "part" ? "Open part " + src.name + " in the Part tab" : "Open in the Part tab (new part, Import STEP)", () => openInPart(c)],
    null,
    [`Show only ${c.name} and the components mated to it`, () => isolateComps(cid, false), !ms.length],
    ["Show only the connected components (also through other components; not continued through fixed ones)", () => isolateComps(cid, true), !ms.length],
    ["Show all components", () => toggleHidden(true), !AS.asm.components.some(x => x.visible === false)],
    null,
    [`Show linked mates (${ms.length})`, () => showLinkedMates(cid), !ms.length],
  ]).concat(ms.map(m => ["\u2003" + mateText(m, cid), () => { AS.mateFilter = cid; AS.selMate = m.id; AS.matePick = null; renderMates(); setMeshes(AS.result); scrollToMates(); }]));
  const menu = document.createElement("div");
  menu.id = "as-menu";
  menu.className = "sk-menu";
  menu.innerHTML = `<div class="hint" style="padding:2px 8px 4px;font-weight:600">${aesc(c.name)}</div>` +
    items.map((it, i) => it ? `<button type="button" data-i="${i}"${it[2] ? " disabled" : ""}>${aesc(it[0])}</button>` : '<div class="sk-menu-sep"></div>').join("");
  document.body.appendChild(menu);
  const w = menu.offsetWidth, h = menu.offsetHeight;
  menu.style.left = Math.max(0, Math.min(x, window.innerWidth - w - 4)) + "px";
  menu.style.top = Math.max(0, Math.min(y, window.innerHeight - h - 4)) + "px";
  menu.querySelectorAll("button[data-i]").forEach(b => b.onclick = () => { closeCompMenu(); items[+b.dataset.i][1](); });
}

/** The mates window over the 3D view: opened by Mates, the mate type buttons and the linked mates of a component. */
function showMatesWin(on) {
  const w = $("#as-matewin");
  if (!w) return;
  w.hidden = !on;
  $("#as-mates-btn").classList.toggle("active", !!on);
}
function scrollToMates() { showMatesWin(true); }

function showLinkedMates(cid) {
  AS.mateFilter = cid;
  AS.selMate = null; AS.matePick = null;
  renderMates(); setMeshes(AS.result); scrollToMates();
}

async function openInPart(c) {
  const src = c.source || {};
  const cur = window.__partCurrent && window.__partCurrent();
  if (cur && cur.dirty && !confirm(`Discard the changes to part ${cur.name}?`)) return;
  showTab("part");
  try {
    if (src.type === "part") { await window.__partLoadNamed(src.name); status("Loaded part " + src.name); }
    else {
      const name = (c.name || "part").replace(/[^A-Za-z0-9_\-.]+/g, "_").replace(/^_+|_+$/g, "") || "part";
      window.__partNewFromStep(name, src.path, src.part === "" ? null : src.part);
      status(`New part ${name} from ${srcText(c)} (not saved)`);
    }
  } catch (e) { showErr(e); }
}

function num(id, label, v, step) { return `<label>${label}<input type="text" inputmode="decimal" class="numf" id="${id}" value="${afmt(v || 0, 6)}"></label>`; }

function renderProps() {
  const box = $("#as-props");
  const c = AS.sel && comp(AS.sel);
  if (!c) { box.innerHTML = '<p class="hint">Select a component in the list or in the view.</p>'; return; }
  const pos = c.pos || [0, 0, 0], rot = c.rot || [0, 0, 0], ex = c.explode || [0, 0, 0];
  box.innerHTML = `<label>Name<input type="text" id="ac-name" value="${aesc(c.name)}"></label>` +
    `<p class="hint">Source: ${aesc(srcText(c))}</p>` +
    `<p class="hint" style="margin-bottom:2px">Position (mm)</p><div class="grid3">${num("ac-px", "x", pos[0])}${num("ac-py", "y", pos[1])}${num("ac-pz", "z", pos[2])}</div>` +
    `<p class="hint" style="margin-bottom:2px">Rotation (deg, about X, then Y, then Z)</p><div class="grid3">${num("ac-rx", "X", rot[0])}${num("ac-ry", "Y", rot[1])}${num("ac-rz", "Z", rot[2])}</div>` +
    `<p class="hint" style="margin-bottom:2px">Explode offset (mm)</p><div class="grid3">${num("ac-ex", "x", ex[0])}${num("ac-ey", "y", ex[1])}${num("ac-ez", "z", ex[2])}</div>` +
    `<div class="grid2"><label>Colour<input type="color" id="ac-color" value="${aesc(c.color || PALETTE[AS.asm.components.indexOf(c) % PALETTE.length])}"></label>` +
    `<label>Density (kg/m^3)<input type="text" inputmode="decimal" class="numf" id="ac-rho" value="${c.density || ""}" placeholder="from Views"></label></div>` +
    `<label>Material (parts list)<input type="text" id="ac-mat" value="${aesc(c.material || "")}" placeholder="e.g. S355"></label>` +
    `<label class="check"><input type="checkbox" id="ac-fixed"${c.fixed ? " checked" : ""}> Fixed (not moved by mates)</label>`;
  const bind = (id, fn) => { const el = $(id); if (el) el.onchange = () => { fn(el); changedAsm(); }; };
  bind("#ac-name", el => { c.name = el.value.trim() || c.name; });
  const v = id => numv($(id).value) || 0;
  ["#ac-px", "#ac-py", "#ac-pz"].forEach(id => bind(id, () => { c.pos = [v("#ac-px"), v("#ac-py"), v("#ac-pz")]; }));
  ["#ac-rx", "#ac-ry", "#ac-rz"].forEach(id => bind(id, () => { c.rot = [v("#ac-rx"), v("#ac-ry"), v("#ac-rz")]; }));
  ["#ac-ex", "#ac-ey", "#ac-ez"].forEach(id => bind(id, () => { c.explode = [v("#ac-ex"), v("#ac-ey"), v("#ac-ez")]; }));
  // colour: shown while the picker is open (input), stored with the change; with several components selected the
  // colour is given to all of them
  const colIds = () => (selIds().has(c.id) ? [...selIds()] : [c.id]);
  const setCol = val => { for (const id of colIds()) { const x = comp(id); if (x) x.color = val; } };
  $("#ac-color").oninput = e => { setCol(e.target.value); if (AS.result) setMeshes(AS.result); renderCompSwatches(); };
  $("#ac-color").onchange = e => { setCol(e.target.value); AS.dirty = true; snapAsm(); renderComps(); if (AS.result) setMeshes(AS.result); };
  bind("#ac-rho", el => { const d = numv(el.value); c.density = d > 0 ? d : null; });
  bind("#ac-mat", el => { c.material = el.value.trim(); });
  bind("#ac-fixed", el => { c.fixed = el.checked; });
}

/** opts.inPlace: keep the position of the solid in its file (no offset beside the assembly); opts.noBuild: no rebuild. */
function addComponent(source, name, opts) {
  opts = opts || {};
  const a = AS.asm;
  const id = "c" + (a.next++);
  const n = a.components.filter(c => (c.source || {}).type === source.type && JSON.stringify(c.source) === JSON.stringify(source)).length;
  const c = { id, name: name + (n ? " " + (n + 1) : ""), source, pos: [0, 0, 0], rot: [0, 0, 0], color: PALETTE[a.components.length % PALETTE.length], visible: true, density: null, explode: [0, 0, 0], fixed: a.components.length === 0 };
  // place new components beside the current extent
  if (AS.bbox && !opts.inPlace) c.pos = [AS.bbox[3] + 20, AS.bbox[1], AS.bbox[2]];
  a.components.push(c);
  AS.sel = id;
  if (AS.three) AS.three.zoomed = false;    // fit the view after the build
  if (!opts.noBuild) changedAsm();
}

async function addPart() {
  let names = [];
  try { names = await (await api("/api/part/list")).json(); } catch (e) { showErr(e); return; }
  if (!names.length) return status("No saved parts. Save a part in the Part tab first.", true);
  const pick = await chooseFrom("Saved part", names);
  if (!pick) return;
  addComponent({ type: "part", name: pick }, pick);
}

async function addStep() {
  let path = "";
  try { path = await window.browse("open", "step", "", "STEP file for the component"); } catch (e) { /* no dialog: type the path */ }
  if (!path) path = await askValue("STEP file path on this PC", "", true);
  if (!path) return;
  const p = path.replace(/^"|"$/g, "");
  let solids = [];
  try { solids = await (await postJSON("/api/assembly/step_solids", { path: p })).json(); } catch (e) { showErr(e); return; }
  const base = p.split(/[\\/]/).pop().replace(/\.(step|stp)$/i, "");
  if (solids.length <= 1) { addComponent({ type: "step", path: p, part: null }, base); return; }
  const ALL_SEP = `(all ${solids.length} solids as separate components)`, ALL_ONE = "(all solids as one component)";
  const pick = await chooseFrom("Solid in " + base, [ALL_SEP, ALL_ONE].concat(solids.map(s => s.name)));
  if (!pick) return;
  if (pick === ALL_SEP) {
    // positions as in the file; the first component is fixed only when the assembly was empty
    solids.forEach((s, i) => addComponent({ type: "step", path: p, part: s.index }, s.name, { inPlace: true, noBuild: i < solids.length - 1 }));
    status(`${solids.length} components added from ${base}`);
  }
  else if (pick === ALL_ONE) addComponent({ type: "step", path: p, part: null }, base);
  else { const s = solids.find(x => x.name === pick); addComponent({ type: "step", path: p, part: s.index }, s.name); }
}

// simple choice dialog using the value dialog with a datalist
function chooseFrom(title, options) {
  return new Promise(resolve => {
    const dlg = $("#value-dialog"), inp = $("#value-dialog-input"), sel = $("#value-dialog-select");
    $("#value-dialog-title").textContent = title;
    sel.innerHTML = options.map(o => `<option value="${aesc(o)}">${aesc(o)}</option>`).join("");
    sel.size = Math.min(Math.max(options.length, 2), 12);
    sel.value = options[0] || "";
    inp.hidden = true; sel.hidden = false;
    dlg.hidden = false;
    setTimeout(() => sel.focus(), 0);
    const done = v => { dlg.hidden = true; inp.hidden = false; sel.hidden = true; $("#value-dialog-ok").onclick = $("#value-dialog-cancel").onclick = sel.onkeydown = sel.ondblclick = null; resolve(v); };
    const ok = () => done(sel.value || null);
    $("#value-dialog-ok").onclick = ok;
    $("#value-dialog-cancel").onclick = () => done(null);
    sel.ondblclick = ok;
    sel.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); ok(); } if (e.key === "Escape") { e.preventDefault(); done(null); } };
  });
}

// ------------------------------------------------------------------ mates

/** A or B of a mate: the face or reference text, Pick (a face in the view), the component and its reference
  *  planes and axes (Plane XY, XZ, YZ, Axis X, Y, Z of the component, the centre planes and axes through the centre
 *  of its bounding box, plane and axis features of a part). */
function sideHtml(m, side) {
  const sd = m[side];
  const cid = sd ? sd.comp : AS.sel;
  const ds = cid ? datumsOf(cid) : {};
  const U = side.toUpperCase();
  return `<p class="hint" style="margin:6px 0 2px">${U}: ${aesc(faceText(sd))} <button type="button" class="small" id="am-p${side}" style="margin-left:4px" title="Click a face in the 3D view">Pick</button></p>` +
    `<div class="grid2"><label>Component<select id="am-c${side}">${AS.asm.components.map(c => `<option value="${aesc(c.id)}"${c.id === cid ? " selected" : ""}>${aesc(c.name)}</option>`).join("")}</select></label>` +
    `<label>Plane or axis<select id="am-d${side}"><option value="">${sd && !sd.datum ? (sd.edge !== undefined && sd.edge !== null ? "(picked edge)" : sd.vertex !== undefined && sd.vertex !== null ? "(picked vertex)" : sd.face !== undefined && sd.face !== null ? "(picked face)" : "(face: Pick)") : "(face: Pick)"}</option>` +
    Object.entries(ds).map(([k, d]) => `<option value="${aesc(k)}"${sd && sd.datum === k ? " selected" : ""}>${aesc(d.name)}</option>`).join("") + `</select></label></div>`;
}

/** Flip of a mate when both sides are picked (unless Flip was set by hand): the direction the components already
 *  have, so the solve turns them the least. Planar faces of solids in a coincident or distance mate keep facing
 *  (outward normals opposite: the faces touch); a concentric mate and reference planes and axes take the current
 *  direction. */
function autoFlip(m) {
  if (!m || !m.a || !m.b || m.flipSet || !["coincident", "distance", "parallel", "concentric", "tangent"].includes(m.type)) return;
  const A = worldRef(m.a), B = worldRef(m.b);
  if (!A || !B || !A.n || !B.n) return;
  if (m.type === "tangent") {           // the cylinder stays on its side of the plane; a cylinder inside the other stays inside
    if (A.kind === "plane" && B.kind === "cylinder") m.flip = B.p.clone().sub(A.c).dot(A.n) < 0;
    else if (B.kind === "plane" && A.kind === "cylinder") m.flip = A.p.clone().sub(B.c).dot(B.n) < 0;
    else if (A.r && B.r) { const d = B.p.clone().sub(A.p); d.addScaledVector(A.n, -d.dot(A.n)); m.flip = d.length() < Math.max(A.r, B.r); }
    return;
  }
  const line = k => k === "axis" || k === "cylinder";
  if ((A.kind === "plane") !== (B.kind === "plane") && (line(A.kind) || line(B.kind)) && m.type !== "concentric") return;   // plane with axis: no direction
  const faces = !m.a.datum && !m.b.datum && A.kind === "plane" && B.kind === "plane";
  if (faces && m.type !== "parallel") { m.flip = false; return; }
  m.flip = A.n.dot(B.n) > 0;
}

/** Mates the solver had to flip (they could not be satisfied the other way): Flip changed on the client too. */
function applyFlipped(ids) {
  for (const id of ids || []) { const m = mate(id); if (m) m.flip = !m.flip; }
}

function bindSide(m, side) {
  const cs = $("#am-c" + side), dsel = $("#am-d" + side);
  const apply = () => { AS.dirty = true; AS.matePick = null; if (m.type === "gear" && m.a && m.b) setGearRef(m); autoFlip(m); renderMates(); setMeshes(AS.result); if (m.a && m.b) solveMates(); };
  cs.onchange = () => {
    const cid = cs.value, sd = m[side];
    if (sd && sd.datum && datumsOf(cid)[sd.datum]) m[side] = { comp: cid, datum: sd.datum };
    else m[side] = null;
    if (!m[side]) { AS.sel = cid; renderMates(); setMeshes(AS.result); return; }
    apply();
  };
  dsel.onchange = () => {
    if (!dsel.value) { if (AS.dragMode) setDragMode(false); AS.matePick = { mateId: m.id, side }; renderMates(); setMeshes(AS.result); return; }
    m[side] = { comp: cs.value, datum: dsel.value };
    apply();
  };
}

function compName(id) { const c = comp(id); return c ? c.name : id; }
/** Reference rotations of a gear mate: the current rotations of its two components. */
function setGearRef(m) {
  const a = comp(m.a.comp), b = comp(m.b.comp);
  if (a && b) m.ref = { a: (a.rot || [0, 0, 0]).map(Number), b: (b.rot || [0, 0, 0]).map(Number) };
}
/** Reference planes and axes of a component (local): {key: {kind, name, c, n, size}}. */
function datumsOf(cid) {
  const c = AS.result && AS.result.components.find(x => x.id === cid);
  return (c && c.datums) || {};
}

/** Draws a reference plane (square) or axis (line) in the local group of a component. */
function addDatum(group, d, color, opacity, pick) {
  const n = new THREE.Vector3(...d.n).normalize(), c = new THREE.Vector3(...d.c), L = (d.size || 100) * 0.6;
  if (d.kind === "axis") {
    const g = new THREE.BufferGeometry().setFromPoints([c.clone().addScaledVector(n, -L), c.clone().addScaledVector(n, L)]);
    const ln = new THREE.Line(g, new THREE.LineDashedMaterial({ color, dashSize: L / 12, gapSize: L / 24, depthTest: false }));
    ln.computeLineDistances();
    ln.renderOrder = 5;
    if (pick) { ln.userData = pick; AS.three.datumPickables.push(ln); }
    group.add(ln);
    AS.three.tempGeo.push(g);
    return;
  }
  const g = new THREE.PlaneGeometry(2 * L, 2 * L);
  const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false }));
  if (pick) { m.userData = pick; AS.three.datumPickables.push(m); }
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n);
  m.position.copy(c);
  group.add(m);
  const eg = new THREE.EdgesGeometry(g);
  const e = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color }));
  e.quaternion.copy(m.quaternion); e.position.copy(c);
  group.add(e);
  AS.three.tempGeo.push(g, eg);
  if (pick) {                       // pickable planes: shown for the last component under the cursor only
    AS.three.datumPlanes.push({ cid: pick.cid, objs: [m, e] });
    m.visible = e.visible = pick.cid === AS.hoverComp;
  }
}

/** Shows the pickable reference planes of one component (the last one under the cursor while a mate side is picked). */
function showPlanesOf(cid) {
  const t = AS.three;
  if (!t || AS.hoverComp === cid) return;
  AS.hoverComp = cid;
  for (const p of t.datumPlanes || []) for (const o of p.objs) o.visible = p.cid === cid;
  render3();
}

function faceText(side) {
  if (!side) return "(pick a face)";
  if (side.datum) { const d = datumsOf(side.comp)[side.datum]; return compName(side.comp) + " : " + (d ? d.name : side.datum + " (lost)"); }
  const c = AS.result && AS.result.components.find(x => x.id === side.comp);
  const r = sideRef(side, c);
  const geo = side.edge !== undefined && side.edge !== null ? "edge " + side.edge : side.vertex !== undefined && side.vertex !== null ? "vertex " + side.vertex : "face " + side.face;
  return compName(side.comp) + " : " + (r ? refText(r) : geo);
}

function renderMates() {
  const box = $("#as-mates");
  if (!box) return;
  if ($("#as-matewin-count")) $("#as-matewin-count").textContent = (AS.asm.mates || []).length ? "(" + (AS.asm.mates || []).length + ")" : "";
  if (AS.mateFilter && !comp(AS.mateFilter)) AS.mateFilter = null;
  const ms = AS.mateFilter ? matesOf(AS.mateFilter) : AS.asm.mates || [];
  let h = AS.mateFilter ? `<p class="hint">Mates of ${aesc(compName(AS.mateFilter))} (${ms.length}) <button type="button" class="small" id="am-all" style="margin-left:4px">Show all</button></p>` : "";
  snapAsm();
  const unsat = AS.unsat || {}, chk = AS.check;
  if (chk && !AS.mateFilter) {
    const nconf = Object.values(chk.mates).filter(x => x.status === "conflict").length;
    h += `<div class="as-check"><p>${aesc(chk.summary)}.</p>` +
      `<div class="row">${nconf ? `<button type="button" class="small" id="am-supconf" title="Suppress the mates left out of the solve">Suppress ${nconf} conflicting</button>` : ""}` +
      `<button type="button" class="small" id="am-chkclose" title="Hide the check results">Close check</button></div></div>`;
  }
  const tag = m => {
    const c = chk && chk.mates[m.id];
    if (c && c.status !== "ok" && c.status !== "suppressed") return `<span class="mtag mtag-${c.status.replace(" ", "")}" title="${aesc(c.text)}">${aesc(c.status)}</span>`;
    if (!chk && unsat[m.id] && !m.suppressed && unsat[m.id].startsWith("conflict")) return `<span class="mtag mtag-conflict" title="${aesc(unsat[m.id])}">left out</span>`;
    return "";
  };
  const tip = m => {
    const c = chk && chk.mates[m.id];
    if (c) return ` title="${aesc(c.text)}"`;
    return unsat[m.id] && !m.suppressed ? ` title="Not satisfied: ${aesc(unsat[m.id])}"` : "";
  };
  const isBad = m => !m.suppressed && (chk ? ["conflict", "not satisfied"].includes((chk.mates[m.id] || {}).status) : !!unsat[m.id]);
  h += ms.length ? ms.map(m => `<div class="as-comp${m.id === AS.selMate ? " sel" : ""}${isBad(m) ? " bad" : ""}" data-mid="${aesc(m.id)}"${tip(m)}>` +
      `<input type="checkbox" data-k="on" title="Active"${m.suppressed ? "" : " checked"}><span></span>` +
      `<span class="nm">${aesc(m.name || MATE_TYPES[m.type] || m.type)}${m.type === "distance" || m.type === "angle" ? " = " + afmt(m.value || 0, 3) : ""}${tag(m)}</span>` +
      `<span class="msub">${aesc(m.a && m.a.comp ? compName(m.a.comp) : "?")} / ${aesc(m.b && m.b.comp ? compName(m.b.comp) : "?")}</span>` +
      `<span class="ops"><button type="button" data-k="del" title="Delete">&#10005;</button></span></div>`).join("")
    : AS.mateFilter ? "" : '<p class="hint">No mates. Choose a mate type in the toolbar, then click a face, reference plane or axis on each of two components.</p>';
  const m = AS.selMate && mate(AS.selMate);
  if (m) {
    h += `<div class="as-mateprops"><label>Type<select id="am-type">${Object.keys(MATE_TYPES).map(k => `<option value="${k}"${k === m.type ? " selected" : ""}>${MATE_TYPES[k]}</option>`).join("")}</select></label>` +
      sideHtml(m, "a") + sideHtml(m, "b") +
      `<label class="check"><input type="checkbox" id="am-flip"${m.flip ? " checked" : ""}> ${m.type === "gear" ? "Flip (same direction of rotation)" : m.type === "tangent" ? "Flip (cylinder on the other side of the plane; one cylinder inside the other)" : "Flip (same direction instead of facing)"}</label>` +
      (m.type === "gear" ? `<label title="Rotation of B per rotation of A (number of teeth of A / number of teeth of B)">Ratio (turns of B per turn of A)<input type="text" inputmode="decimal" class="numf" id="am-ratio" value="${afmt(m.value || 1, 6)}"></label>` +
        `<p class="hint">Rotations are measured from the reference position (set when both sides are picked), within half a turn of it. <button type="button" class="small" id="am-gref" style="margin-left:4px">Set reference position</button></p>` : "") +
      (m.type === "distance" || m.type === "angle"
        ? `<div class="grid3"><label>${m.type === "distance" ? "Distance (mm)" : "Angle (deg)"}<input type="text" inputmode="decimal" class="numf" id="am-val" value="${afmt(m.value || 0, 6)}"></label>` +
          `<label>Min<input type="text" inputmode="decimal" class="numf" id="am-min" value="${m.min === undefined ? "" : m.min}"></label><label>Max<input type="text" inputmode="decimal" class="numf" id="am-max" value="${m.max === undefined ? "" : m.max}"></label></div>` +
          (m.min !== undefined && m.max !== undefined && m.max > m.min ? `<input type="range" id="am-slider" min="${m.min}" max="${m.max}" step="${(m.max - m.min) / 200}" value="${m.value || 0}" style="width:100%">` : `<p class="hint">Set Min and Max for a drive slider.</p>`)
        : "") +
      (pickSide() && pickSide().mateId === m.id ? `<p class="as-bad">Click a face of any component for ${pickSide().side.toUpperCase()} in the 3D view (reference planes and axes: check Datums, or use the lists).</p>` : "") + `</div>`;
  }
  box.innerHTML = h;
  if ($("#am-all")) $("#am-all").onclick = () => { AS.mateFilter = null; renderMates(); setMeshes(AS.result); };
  if ($("#am-chkclose")) $("#am-chkclose").onclick = () => { AS.check = null; renderMates(); renderComps(); };
  if ($("#am-supconf")) $("#am-supconf").onclick = () => {
    const ids = Object.entries(AS.check.mates).filter(([, x]) => x.status === "conflict").map(([k]) => k);
    for (const id of ids) { const x = mate(id); if (x) x.suppressed = true; }
    AS.dirty = true;
    status(ids.length + " conflicting mate(s) suppressed (Ctrl+Z undoes)");
    checkMates();
  };
  box.querySelectorAll(".as-comp[data-mid]").forEach(row => {
    const id = row.dataset.mid;
    row.onclick = e => {
      const k = e.target.dataset && e.target.dataset.k;
      if (k === "on") { mate(id).suppressed = !e.target.checked; AS.dirty = true; solveMates(); return; }
      if (k === "del") { AS.asm.mates = AS.asm.mates.filter(x => x.id !== id); if (AS.selMate === id) AS.selMate = null; AS.matePick = null; AS.dirty = true; renderMates(); setMeshes(AS.result); return; }
      AS.selMate = id; AS.matePick = null; AS.noAutoPick = null; renderMates(); setMeshes(AS.result);
    };
  });
  if (!m) return;
  $("#am-type").onchange = () => { m.type = $("#am-type").value; if (m.type === "gear") { if (!m.value) m.value = 1; if (m.a && m.b) setGearRef(m); } autoFlip(m); AS.dirty = true; renderMates(); solveMates(); };
  $("#am-pa").onclick = () => { if (AS.dragMode) setDragMode(false); AS.matePick = { mateId: m.id, side: "a" }; renderMates(); setMeshes(AS.result); };
  $("#am-pb").onclick = () => { if (AS.dragMode) setDragMode(false); AS.matePick = { mateId: m.id, side: "b" }; renderMates(); setMeshes(AS.result); };
  bindSide(m, "a"); bindSide(m, "b");
  $("#am-flip").onchange = () => { m.flip = $("#am-flip").checked; m.flipSet = true; AS.dirty = true; solveMates(); };
  if ($("#am-ratio")) $("#am-ratio").onchange = () => { const v = numv($("#am-ratio").value); if (isFinite(v) && v > 0) { m.value = v; AS.dirty = true; solveMates(); } else msg("Ratio must be > 0", true); };
  if ($("#am-gref")) $("#am-gref").onclick = () => { if (m.a && m.b) { setGearRef(m); AS.dirty = true; msg("Gear reference position set"); } };
  if ($("#am-val")) $("#am-val").onchange = () => { m.value = numv($("#am-val").value) || 0; AS.dirty = true; renderMates(); solveMates(); };
  if ($("#am-min")) $("#am-min").onchange = () => { const v = numv($("#am-min").value); if (isFinite(v)) m.min = v; else delete m.min; AS.dirty = true; renderMates(); };
  if ($("#am-max")) $("#am-max").onchange = () => { const v = numv($("#am-max").value); if (isFinite(v)) m.max = v; else delete m.max; AS.dirty = true; renderMates(); };
  if ($("#am-slider")) {
    let busyS = false;
    $("#am-slider").oninput = async () => {
      m.value = numv($("#am-slider").value);
      if ($("#am-val")) $("#am-val").value = afmt(m.value, 3);
      if (busyS) return;
      busyS = true;
      try { await solveMates(true); } finally { busyS = false; }
    };
  }
}

function addMate(type) {
  if (!AS.asm.components.length) return msg("Add components first", true);
  AS.asm.mates = AS.asm.mates || [];
  const id = "m" + (AS.asm.next++);
  type = MATE_TYPES[type] ? type : "coincident";
  if (AS.measure) setMeasure(false);
  const m = { id, type, a: null, b: null, value: type === "gear" ? 1 : 0, flip: false, suppressed: false };
  AS.asm.mates.push(m);
  AS.selMate = id;
  AS.matePick = { mateId: id, side: "a" };
  AS.mateFilter = null; AS.noAutoPick = null;
  if (AS.dragMode) setDragMode(false);
  AS.dirty = true;
  showMatesWin(true);
  renderMates();
  setMeshes(AS.result);
  // the new mate and its sides at the end of a long list: scrolled into view
  const row = document.querySelector(`#as-mates .as-comp[data-mid="${id}"]`), props = document.querySelector("#as-mates .as-mateprops");
  if (row) row.scrollIntoView({ block: "nearest" });
  if (props) props.scrollIntoView({ block: "nearest" });
  msg(MATE_TYPES[type].replace(/ \(.*/, "") + " mate " + AS.asm.mates.length + ": click a " + (type === "concentric" || type === "gear" ? "cylinder" : type === "tangent" ? "plane or cylinder" : "face") + " of the first component (A) in the 3D view, then of the second (B). Esc ends");
}

let solveSeq = 0;
/** Active mates with both sides on cid (another component). */
function hasMates(cid) {
  return (AS.asm.mates || []).some(m => !m.suppressed && m.a && m.b && m.a.comp !== m.b.comp && (m.a.comp === cid || m.b.comp === cid));
}

/** Solves the mates; drag {comp, delta}: the component is pulled by delta (mm) and the chain it is mated in follows. */
/** Mate check: solve (conflicting mates left out), state of each mate, free motions of each component. */
async function checkMates() {
  const ms = (AS.asm.mates || []);
  if (!ms.length) { status("No mates to check", true); return; }
  status("Checking the mates...");
  try {
    const r = await postJSON("/api/assembly/check", { assembly: AS.asm });
    const j = await r.json();
    for (const [cid, pl] of Object.entries(j.placements)) { const c = comp(cid); if (c) { c.pos = pl.pos; c.rot = pl.rot; } }
    applyFlipped(j.flipped);
    AS.unsat = j.unsatisfied || {};
    snapAsm();
    AS.check = j;
    showMatesWin(true);
    renderComps(); renderProps(); renderMates();
    if (AS.result) setMeshes(AS.result);
    status(j.summary, Object.values(j.mates).some(x => x.status === "conflict" || x.status === "not satisfied"));
    await build();
  } catch (e) { showErr(e); }
}

async function solveMates(quick, drag) {
  const ms = (AS.asm.mates || []).filter(m => !m.suppressed && m.a && m.b);
  if (!ms.length) { if (!quick) build(); return; }
  const seq = ++solveSeq;
  try {
    if (drag) status("Solving the drag...");
    const r = await postJSON("/api/assembly/solve", Object.assign({ assembly: Object.assign({}, AS.asm, { mates: ms }) }, drag ? { drag } : {}));   // complete mates only
    const j = await r.json();
    if (seq !== solveSeq) return;
    const before = {}, rbefore = {};
    for (const c of AS.asm.components) { before[c.id] = (c.pos || [0, 0, 0]).slice(); rbefore[c.id] = (c.rot || [0, 0, 0]).slice(); }
    for (const [cid, pl] of Object.entries(j.placements)) { const c = comp(cid); if (c) { c.pos = pl.pos; c.rot = pl.rot; } }
    applyFlipped(j.flipped);
    if ((j.flipped || []).length) AS.dirty = true;
    AS.unsat = j.unsatisfied || {};
    AS.conflicts = j.conflicts || {};
    if (drag) AS.dirty = true;
    let dragText = "";
    if (drag) {
      const c = comp(drag.comp), p0 = before[drag.comp] || [0, 0, 0], p1 = (c && c.pos) || p0;
      const dist = Math.hypot(p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]);
      const moved = Object.keys(j.placements).filter(id => id !== drag.comp && before[id] && Math.hypot(...j.placements[id].pos.map((v, i) => v - before[id][i])) > 1e-3).length;
      const r0 = rbefore[drag.comp] || [0, 0, 0], r1 = (c && c.rot) || r0;
      const turned = r0.some((v, i) => Math.abs((((Number(r1[i]) - Number(v)) % 360) + 540) % 360 - 180) > 1e-3);
      dragText = dist < 1e-3 && !turned ? `${c ? c.name : drag.comp} is held by its mates and the fixed components` :
        `${c ? c.name : drag.comp} ${dist >= 1e-3 ? `moved ${afmt(dist, 2)} mm` : "turned"}` + (moved ? `, with ${moved} mated component(s)` : "");
    }
    if (j.messages.length) msg((dragText ? dragText + ". " : "") + j.messages.join("; "), true);
    else if (dragText) msg(dragText, dragText.includes("held"));
    else if (!quick) msg("Mates solved");
    renderMates();
    renderProps();
    if (AS.result) setMeshes(AS.result);
    await build();
  } catch (e) { showErr(e); }
}

// ------------------------------------------------------------------ files

function loadAsm(a) {
  if (!a.uid) a.uid = newUidA();
  AS.hist = []; AS.hpos = -1; AS.check = null; AS.unsat = {};
  if (!a.next) a.next = (a.components || []).reduce((m, c) => Math.max(m, parseInt(String(c.id).slice(1)) || 0), 0) + 1;
  AS.asm = a;
  AS.sel = a.components.length ? a.components[0].id : null;
  AS.errors = {};
  AS.dirty = false;
  if (AS.three) AS.three.zoomed = false;
  if (FM) FM.render();
  AS.selMate = null; AS.matePick = null; AS.mateFilter = null;
  renderComps(); renderProps(); renderMates();
  build();
}

let FM = null;                                              // File menu (docFileMenu in app.js)
function refreshList() { if (FM) return FM.refresh(); }

/** Writes the assembly as <name>.asm.json. asNew: a new document (Save as): new uid. */
async function saveAsm(name, asNew) {
  if (asNew && AS.asm.name !== name) AS.asm.uid = newUidA();
  AS.asm.name = name;
  const r = await api("/api/assembly/file/" + encodeURIComponent(name), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(AS.asm) });
  const j = await r.json();
  AS.dirty = false;
  status("Saved " + j.path);
}

async function exportStep(overwrite) {
  busy(true, "Exporting STEP...");
  try {
    const r = await fetch("/api/assembly/export", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assembly: AS.asm, folder: $("#as-folder").value.trim(), overwrite: !!overwrite, explode: $("#as-explode").checked }) });
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
    a.download = AS.asm.name.replace(/[^A-Za-z0-9_\-.]+/g, "_") + ".step";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    status("Downloaded " + a.download);
  } catch (e) { showErr(e); }
  finally { busy(false); }
}

async function makeDrawing() {
  busy(true, "Adding the assembly to Models...");
  try {
    const r = await postJSON("/api/assembly/to_drawings", { assembly: AS.asm, explode: $("#as-explode").checked,
                                                             density: numv($("#density").value) || 0, parts_list: $("#as-plist").checked });
    const res = await r.json();
    const fid = res.files[0].file_id;
    state.files = state.files.filter(f => f.file_id !== fid);
    addFiles(res);
    state.files.forEach(f => { if (f.file_id !== fid) f.parts.forEach(p => p.checked = false); });
    $("#mode").value = "document";
    renderFiles();
  } catch (e) { showErr(e); busy(false); return; }
  busy(false);
  showTab("annotate");
  preview(false);
}

// ------------------------------------------------------------------ init

// drag mode key: D (default), K (left-handed option)
const asDragKey = () => leftKeys() ? codeLabel("KeyK") : "D";
window.SHORTCUTS.push({ tab: "Assembly", rows: () => [[asDragKey(), "Drag mode on / off"], [leftKeys() ? codeLabel("KeyU") : "R", "Rotate mode on / off"], ["Space", "Hide the component under the cursor (else show / hide the selected one)"], ["Shift+Space", "Show all components"], ["Ctrl+Space", "Invert: show the hidden components, hide the shown ones"], ["Esc", "End drag mode"]] });

/** Space: hides the component under the cursor, or shows / hides the selected component when the cursor is over
 *  no component. Shift+Space shows all components. */
/** Components connected to cid by active mates, not continued through fixed components (a fixed component is
 *  included, the components mated to it only when cid is that component). */
function connectedComps(cid) {
  const ids = new Set([cid]), todo = [cid];
  while (todo.length) {
    const x = todo.pop();
    if (x !== cid && (comp(x) || {}).fixed) continue;
    for (const m of AS.asm.mates || []) {
      if (m.suppressed || !m.a || !m.b) continue;
      const o = m.a.comp === x ? m.b.comp : m.b.comp === x ? m.a.comp : null;
      if (o && !ids.has(o) && comp(o)) { ids.add(o); todo.push(o); }
    }
  }
  return ids;
}

/** Shows only the component and the components mated to it (chain: also those connected through other
 *  components that are not fixed); the others are hidden (Show all or Invert restores them). */
function isolateComps(cid, chain) {
  const keep = chain ? connectedComps(cid) : new Set([cid, ...matesOf(cid).filter(m => !m.suppressed).flatMap(m => [m.a && m.a.comp, m.b && m.b.comp]).filter(Boolean)]);
  AS.asm.components.forEach(c => { c.visible = keep.has(c.id); });
  status(`Shown: ${keep.size} component(s), hidden: ${AS.asm.components.length - keep.size} (Shift+Space shows all, Ctrl+Space inverts)`);
  renderComps(); changedAsm();
}

/** Invert the visibility: the hidden components are shown and the shown ones hidden. */
function invertHidden() {
  const cs = AS.asm.components;
  const hid = cs.filter(c => c.visible === false).length;
  if (!hid) return status("No component is hidden (Space hides the component under the cursor)", true);
  cs.forEach(c => { c.visible = c.visible === false; });
  status("Shown: " + hid + ", hidden: " + (cs.length - hid) + " component(s) (Ctrl+Space inverts again, Shift+Space shows all)");
  renderComps(); changedAsm();
}

function toggleHidden(all) {
  if (all) {
    const hid = AS.asm.components.filter(c => c.visible === false);
    if (!hid.length) return;
    hid.forEach(c => { c.visible = true; });
    status("Shown: " + hid.length + " component(s)");
    renderComps(); changedAsm();
    return;
  }
  const ss = selIds();
  if (ss.size > 1) {                                   // a box or Ctrl selection: hidden together
    ss.forEach(id => { const x = comp(id); if (x) x.visible = false; });
    AS.multi = null;
    status("Hidden: " + ss.size + " component(s) (Shift+Space shows all, Ctrl+Space inverts)");
    renderComps(); changedAsm();
    return;
  }
  const cid = (AS.mouse && AS.three && compAt(AS.mouse)) || AS.sel;
  const c = cid && comp(cid);
  if (!c) return status("Point at a component or select one in the list", true);
  c.visible = c.visible === false;
  status((c.visible ? "Shown: " : "Hidden: ") + c.name + " (Space toggles, Shift+Space shows all)");
  renderComps(); changedAsm();
}
window.addEventListener("optionschanged", () => setKeyTitle($("#as-drag"), asDragKey()));
setKeyTitle($("#as-drag"), asDragKey());

window.asmShown = function () {
  if (!AS.three) initThree();
  if (!AS.asm) loadAsm(blankAsm("assembly"));
  refreshList();
  setTimeout(resize3, 0);
};

(function bindAsm() {
  document.addEventListener("mousedown", e => { const m = document.getElementById("as-menu"); if (m && !m.contains(e.target)) closeCompMenu(); });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      closeCompMenu();
      if (AS.measure && !$("#tab-asm").hidden) setMeasure(false);
      else if (AS.multi && !$("#tab-asm").hidden && !AS.dragMode && !pickSide()) { AS.multi = null; renderComps(); setMeshes(AS.result); status("Selection cleared"); }
      else if (AS.dragMode && !$("#tab-asm").hidden) setDragMode(false);
      else if (pickSide() && !$("#tab-asm").hidden) { AS.matePick = null; AS.noAutoPick = AS.selMate; AS.three.renderer.domElement.style.cursor = ""; renderMates(); setMeshes(AS.result); status("Mate picking ended (Pick starts it again)"); }
    }
    if ((e.key === " " || e.code === "Space") && (e.ctrlKey || e.metaKey) && !e.altKey && !$("#tab-asm").hidden && !(e.target.matches && e.target.matches("input, select, textarea"))) {
      e.preventDefault();
      invertHidden();
      return;
    }
    if ((e.key === " " || e.code === "Space") && !e.ctrlKey && !e.metaKey && !e.altKey && !$("#tab-asm").hidden && !(e.target.matches && e.target.matches("input, select, textarea"))) {
      e.preventDefault();
      toggleHidden(e.shiftKey);
      return;
    }
    const dragKey = leftKeys() ? e.code === "KeyK" : e.key.toLowerCase() === "d";
    const rotKey = leftKeys() ? e.code === "KeyU" : e.key.toLowerCase() === "r";
    if ((e.ctrlKey || e.metaKey) && !$("#tab-asm").hidden && !(e.target.matches && e.target.matches("input, select, textarea"))) {
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) { e.preventDefault(); undoAsm(-1); return; }
      if (k === "y" || (k === "z" && e.shiftKey)) { e.preventDefault(); undoAsm(1); return; }
    }
    const free = !e.ctrlKey && !e.metaKey && !e.altKey && !$("#tab-asm").hidden && !(e.target.matches && e.target.matches("input, select, textarea"));
    if (dragKey && free) setDragMode(AS.dragMode === "move" ? false : "move");
    if (rotKey && free) setDragMode(AS.dragMode === "rotate" ? false : "rotate");
  });
  $("#as-drag").onclick = () => setDragMode(AS.dragMode === "move" ? false : "move");
  $("#as-rotate").onclick = () => setDragMode(AS.dragMode === "rotate" ? false : "rotate");
  $("#as-mates-btn").onclick = () => showMatesWin($("#as-matewin").hidden);
  $("#as-matewin-close").onclick = () => showMatesWin(false);
  $("#as-sec").onchange = () => setMeshes(AS.result);
  $("#as-sec-axis").onchange = () => { updateSection(); render3(); };
  $("#as-sec-flip").onchange = () => { updateSection(); render3(); };
  $("#as-sec-pos").oninput = () => { updateSection(); render3(); };
  $("#as-add-part").onclick = addPart;
  $("#as-add-step").onclick = addStep;
  document.querySelectorAll("#as-tb-mates button[data-mate]").forEach(b => { b.onclick = () => addMate(b.dataset.mate); });
  $("#as-solve").onclick = () => solveMates(false);
  $("#as-dup").onclick = () => {
    const c = AS.sel && comp(AS.sel); if (!c) return;
    const d = JSON.parse(JSON.stringify(c)); d.id = "c" + (AS.asm.next++); d.name = c.name + " copy"; d.pos = [c.pos[0] + 20, c.pos[1], c.pos[2]];
    AS.asm.components.push(d); AS.sel = d.id; changedAsm();
  };
  $("#as-del").onclick = () => {
    const ids = [...selIds()];
    if (!ids.length) return;
    if (!confirm(ids.length > 1 ? "Delete the " + ids.length + " selected components?" : "Delete " + comp(ids[0]).name + "?")) return;
    AS.asm.components = AS.asm.components.filter(x => !ids.includes(x.id)); AS.sel = null; AS.multi = null; changedAsm();
  };
  $("#as-box").onclick = () => { AS.boxMode = !AS.boxMode; $("#as-box").classList.toggle("active", AS.boxMode);
    status(AS.boxMode ? "Box select: left drag from left to right selects the components inside the box, from right to left the components it touches (Ctrl adds). Box select again ends" : "Box select off (Ctrl + left drag still draws a box)"); };
  document.querySelectorAll("#tab-asm [data-asview]").forEach(b => b.onclick = () => view(b.dataset.asview));
  $("#as-edges").onchange = () => setMeshes(AS.result);
  $("#as-display").onchange = () => setMeshes(AS.result);
  // Parts list: the default of a new drawing, and shown or hidden at once on the drawing of this assembly
  $("#as-plist").onchange = async () => {
    const on = $("#as-plist").checked;
    if (!AS.asm || !AS.asm.uid) return;
    const name = "asm_" + String(AS.asm.uid).replace(/[^A-Za-z0-9_\-.]+/g, "_");
    try {
      const lay = await (await api("/api/layout/" + encodeURIComponent(name))).json();
      lay.parts_list = on;
      await api("/api/layout/" + encodeURIComponent(name), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lay) });
      status("Parts list " + (on ? "shown" : "hidden") + " on the drawing of " + AS.asm.name);
      if (typeof preview === "function" && (state.files || []).some(f => f.file_id === "asm_" + String(AS.asm.name || "assembly").replace(/[^A-Za-z0-9_\-.]+/g, "_").replace(/^_+|_+$/g, ""))) preview(true, true);
    } catch (e) { showErr(e); }
  };
  $("#as-isolate").onchange = () => setMeshes(AS.result);
  $("#as-check").onclick = checkMates;
  $("#as-showall").onclick = () => { if (AS.asm.components.some(c => c.visible === false)) toggleHidden(true); else status("All components are shown"); };
  $("#as-invert").onclick = invertHidden;
  $("#as-measure-btn").onclick = () => setMeasure(!AS.measure);
  $("#as-measure-close").onclick = () => setMeasure(false);
  $("#as-undo").onclick = () => undoAsm(-1);
  $("#as-redo").onclick = () => undoAsm(1);
  $("#as-axes").onchange = () => setMeshes(AS.result);
  $("#as-datums").onchange = () => setMeshes(AS.result);
  $("#as-explode").onchange = () => { if (AS.result) setMeshes(AS.result); scheduleBuild(); };
  $("#as-interf").onchange = scheduleBuild;
  FM = docFileMenu({ pre: "as", type: "assembly", label: "assembly", pane: "#tab-asm", listUrl: "/api/assembly/list",
    cur: () => (AS.asm ? { name: AS.asm.name, dirty: !!AS.dirty } : null),
    load: async name => loadAsm(await (await api("/api/assembly/file/" + encodeURIComponent(name))).json()),
    save: saveAsm, blank: () => loadAsm(blankAsm("assembly")), setName: name => { AS.asm.name = name; } });
  $("#as-step").onclick = () => exportStep(false);
  $("#as-mesh").onclick = () => { if (!AS.asm) return; window.exportMesh(() => ({ assembly: AS.asm }), $("#as-folder").value.trim(), AS.asm.name); };
  $("#as-draw").onclick = makeDrawing;
  $("#density").addEventListener("change", () => { if (AS.asm && !$("#tab-asm").hidden) scheduleBuild(); });
  window.addEventListener("beforeunload", e => { if (AS.dirty) { e.preventDefault(); e.returnValue = ""; } });
})();

window.__asm = { AS, comp, THREE, mateHitAt, orthoBasis, setMeshes, isolateComps, compMatrix };
window.__asmLoadNamed = async function (name) { loadAsm(await (await api("/api/assembly/file/" + encodeURIComponent(name))).json()); if (FM) FM.markSaved(name); };
window.__asmSetName = name => { if (AS.asm) { AS.asm.name = name; if (FM) FM.markSaved(name); } };
window.__asmRefresh = refreshList;
window.__asmCurrent = () => (AS.asm ? { name: AS.asm.name, dirty: !!AS.dirty } : null);
