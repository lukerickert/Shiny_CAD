// Supports and loads at the mesh nodes (Analysis tab, Show Mesh and Results; node set supports in Show Model).
//
// payload.bcs:   [{id, name, nodes: [node index], dofs: [1..3 held translations], rnodes: [node index], rdofs: [1..3 held
//                  rotations], prescribed: bool, normal: bool}]
// payload.loads: [{id, name, type, value (gravity), f: [[node index, fx, fy, fz]], m: [[node index, mx, my, mz]]}]
//
// Held translation: a cone along the axis with its tip at the node (one per held component); held rotations: a cube
// at the node. Support colour blue, prescribed displacement green. Nodal force: an arrow ending at the node, length
// scaled by the largest nodal force of the load (35 % to 100 %); nodal moment: an arrow with two heads (violet).
// Gravity: one arrow above the model. The selected support or load is orange.
import * as THREE from "three";

export const BC_COLORS = { support: 0x1c7ed6, prescribed: 0x2f9e44, load: 0xe03131, moment: 0x9c36b5, sel: 0xf08c00 };
const MAX_GLYPHS = 4000;            // glyphs per support or load; more nodes: every k-th node

const AXES = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)];
const UP = new THREE.Vector3(0, 1, 0);

function stride(n) { return Math.max(1, Math.ceil(n / MAX_GLYPHS)); }

/** Instanced mesh of geometry geo with one matrix per entry of mats. */
function instanced(track, geo, mats, color, ud) {
  if (!mats.length) return null;
  const m = new THREE.InstancedMesh(track(geo), new THREE.MeshLambertMaterial({ color }), mats.length);
  mats.forEach((M, i) => m.setMatrixAt(i, M));
  m.instanceMatrix.needsUpdate = true;
  m.userData = ud;
  m.renderOrder = 6;
  return m;
}

/** Matrix of a glyph whose local +y axis points along dir, translated to p. */
function along(dir, p, sx = 1, sy = 1) {
  const q = new THREE.Quaternion().setFromUnitVectors(UP, dir.clone().normalize());
  return new THREE.Matrix4().compose(p, q, new THREE.Vector3(sx, sy, sx));
}

/**
 * Adds the glyphs to group.
 * pos: Float32Array of the node positions (deformed in Show Results); size: model size (mm);
 * opts: {sel: {kind, id}, only: Set of support ids to draw (null: all), onlyLoads: Set of load ids (null: all),
 *        loads: false (no loads), box: THREE.Box3 of the model (gravity arrow; default: the box of pos)}.
 */
export function drawBcLoads(group, track, pos, payload, size, opts = {}) {
  const sel = opts.sel || {};
  const P = i => new THREE.Vector3(pos[3 * i], pos[3 * i + 1], pos[3 * i + 2]);
  const h = size * 0.025, r = size * 0.008;
  // supports
  const cone = () => new THREE.ConeGeometry(r, h, 10).translate(0, -h / 2, 0);   // tip at the origin, body along -y
  for (const b of payload.bcs || []) {
    if (opts.only && !opts.only.has(b.id)) continue;
    const strong = sel.kind === "support" && sel.id === b.id;
    const color = strong ? BC_COLORS.sel : b.prescribed ? BC_COLORS.prescribed : BC_COLORS.support;
    const ud = { kind: "support", id: b.id };
    const mats = [], k = stride(b.nodes.length);
    for (let j = 0; j < b.nodes.length; j += k) {
      const p = P(b.nodes[j]);
      for (const d of b.dofs) if (d >= 1 && d <= 3) mats.push(along(AXES[d - 1], p));
    }
    const cm = instanced(track, cone(), mats, color, ud);
    if (cm) group.add(cm);
    if ((b.rdofs || []).length && (b.rnodes || []).length) {
      const bm = [], kr = stride(b.rnodes.length);
      for (let j = 0; j < b.rnodes.length; j += kr) bm.push(new THREE.Matrix4().makeTranslation(P(b.rnodes[j])));
      const s = r * 1.6;
      const im = instanced(track, new THREE.BoxGeometry(s, s, s), bm, strong ? BC_COLORS.sel : 0x0b4f9c, ud);
      if (im) group.add(im);
    }
  }
  if (opts.loads === false) return;
  // loads
  const L = size * 0.06;
  for (const l of payload.loads || []) {
    if (opts.onlyLoads && !opts.onlyLoads.has(l.id)) continue;
    const strong = sel.kind === "load" && sel.id === l.id;
    const ud = { kind: "load", id: l.id };
    if (l.type === "gravity") {
      const g = new THREE.Vector3(...(l.value || [0, 0, -9810]));
      if (g.lengthSq() < 1e-20) continue;
      const bb = opts.box && !opts.box.isEmpty() ? opts.box : new THREE.Box3().setFromArray(pos);
      const c = bb.getCenter(new THREE.Vector3());
      const dir = g.clone().normalize();
      const len = size * 0.15;
      const start = c.clone().addScaledVector(dir, -(size * 0.6 + len));
      const a = new THREE.ArrowHelper(dir, start, len, strong ? BC_COLORS.sel : BC_COLORS.load, len * 0.25, len * 0.12);
      a.traverse(o => { o.userData = ud; });
      group.add(a);
      continue;
    }
    for (const [rows, color, heads] of [[l.f || [], BC_COLORS.load, 1], [l.m || [], BC_COLORS.moment, 2]]) {
      if (!rows.length) continue;
      let fmax = 0;
      for (const q of rows) fmax = Math.max(fmax, Math.hypot(q[1], q[2], q[3]));
      if (!(fmax > 0)) continue;
      const shaft = [], tips = [], k = stride(rows.length);
      for (let j = 0; j < rows.length; j += k) {
        const q = rows[j];
        const v = new THREE.Vector3(q[1], q[2], q[3]);
        const len = L * (0.35 + 0.65 * v.length() / fmax);
        const dir = v.normalize();
        const p = P(q[0]);
        // head: tip at the node; shaft: from the start of the arrow to the base of the head
        const hh = Math.min(h, len * 0.45);
        tips.push(along(dir, p, 1, hh / h));
        if (heads === 2) tips.push(along(dir, p.clone().addScaledVector(dir, -hh * 0.9), 1, hh / h));
        const sl = len - hh;
        shaft.push(along(dir, p.clone().addScaledVector(dir, -hh - sl / 2), 1, sl));
      }
      const col = strong ? BC_COLORS.sel : color;
      const hm = instanced(track, cone(), tips, col, ud);
      if (hm) group.add(hm);
      const sm = instanced(track, new THREE.CylinderGeometry(r * 0.3, r * 0.3, 1, 6), shaft, col, ud);
      if (sm) group.add(sm);
    }
  }
}

/** True when the load has glyphs at the nodes (member line loads have none: they are element loads). */
export function hasNodeGlyphs(payload, id) {
  const l = (payload.loads || []).find(x => x.id === id);
  return !!l && (l.type === "gravity" || (l.f || []).length > 0 || (l.m || []).length > 0);
}

/** Held components of a support of the document: [translations 1..3, rotations 1..3]. */
export function supportDofs(s) {
  const t = s.type || "fixed";
  if (t === "fixed") return [[1, 2, 3], [1, 2, 3]];
  if (t === "pinned") return [[1, 2, 3], []];
  if (t === "xsymm") return [[1], [2, 3]];
  if (t === "ysymm") return [[2], [1, 3]];
  if (t === "zsymm") return [[3], [1, 2]];
  if (t === "dofs" || t === "displacement") {
    const f = (s.dofs || []).map(Number);
    return [[1, 2, 3].filter(d => f[d - 1]), [1, 2, 3].filter(d => f[d + 2])];
  }
  return [[], []];
}
