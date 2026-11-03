// View helpers for components with surface bodies (Assembly, Analysis, Explicit): the component mesh holds the faces
// of the solid first and then the faces of the surface bodies (mesh.face_body per face: null for the solid, else the
// index into the component's "surfaces"); edge picking on the edge polylines of the view mesh.
import * as THREE from "three";

export const SURF_COL = 0x5b7fb5;          // surface bodies (the Part tab colour)

/** Draw groups of a component geometry: one group per run of triangles of the same body; material index 0 for the
 *  solid, 1 + k for surface body k. Returns the number of groups (0: no surface bodies, one material). */
export function addBodyGroups(geo, m) {
  const fb = m.face_body || [], fot = m.face_of_tri || [];
  if (!fb.some(v => v !== null && v !== undefined)) return 0;
  geo.clearGroups();
  let cur = null, n = 0;
  for (let k = 0; k < m.triangles.length; k++) {
    const b = fb[fot[k]];
    const mi = b === null || b === undefined ? 0 : 1 + b;
    if (!cur || cur.mi !== mi) {
      if (cur) geo.addGroup(cur.start, cur.count, cur.mi);
      cur = { start: k * 3, count: 0, mi };
      n++;
    }
    cur.count += 3;
  }
  if (cur) geo.addGroup(cur.start, cur.count, cur.mi);
  return n;
}

/** Material of a surface body: translucent, double-sided, in its colour. */
export function surfaceMaterial(color, opacity, extra) {
  return new THREE.MeshStandardMaterial(Object.assign({ color: color ? new THREE.Color(color) : SURF_COL, transparent: opacity < 1, opacity,
    side: THREE.DoubleSide, depthWrite: opacity >= 1, metalness: 0, roughness: 1, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }, extra || {}));
}

/** Materials of a component mesh: [solid material, one per surface body]. surfOpts(k, surface) -> {color, opacity}. */
export function bodyMaterials(solidMat, surfaces, surfOpts) {
  return [solidMat, ...(surfaces || []).map((s, k) => { const o = surfOpts(k, s) || {}; return surfaceMaterial(o.color !== undefined ? o.color : s.color, o.opacity === undefined ? 0.45 : o.opacity, o.extra); })];
}

/** Edge of a component under the cursor: {comp, edge (index into the component's edges), d (px)} for the nearest edge
 *  polyline within px pixels, or null. comps: [{id, mesh, matrix: THREE.Matrix4}]. */
export function edgeAt(comps, camera, rect, x, y, px = 8) {
  let best = null;
  const v = new THREE.Vector3();
  for (const c of comps) {
    const m = c.mesh;
    if (!m || !m.edges || !m.edge_ids) continue;
    m.edges.forEach((pl, i) => {
      let prev = null;
      for (const q of pl) {
        v.set(q[0], q[1], q[2]).applyMatrix4(c.matrix).project(camera);
        const s = [(v.x + 1) / 2 * rect.width + rect.left, (1 - v.y) / 2 * rect.height + rect.top, v.z];
        if (prev) {
          const dx = s[0] - prev[0], dy = s[1] - prev[1], L2 = dx * dx + dy * dy;
          const t = L2 > 0 ? Math.max(0, Math.min(1, ((x - prev[0]) * dx + (y - prev[1]) * dy) / L2)) : 0;
          const d = Math.hypot(prev[0] + t * dx - x, prev[1] + t * dy - y);
          const z = prev[2] + t * (s[2] - prev[2]);
          if (d <= px && (!best || d < best.d - 0.5 || (Math.abs(d - best.d) <= 0.5 && z < best.z))) best = { comp: c.id, edge: m.edge_ids[i], d, z };
        }
        prev = s;
      }
    });
  }
  return best;
}

/** Positions (local, LineSegments pairs) of the polylines of an edge of a component mesh. */
export function edgeSegments(m, edge) {
  const pos = [];
  if (!m || !m.edges || !m.edge_ids) return pos;
  m.edges.forEach((pl, i) => { if (m.edge_ids[i] === edge) for (let k = 0; k + 1 < pl.length; k++) pos.push(...pl[k], ...pl[k + 1]); });
  return pos;
}

/** Text of an edge reference: "line edge 12, L 100 mm" (erefs: edge references of the component). */
export function edgeLabel(erefs, edge, fmt) {
  const r = (erefs || [])[edge];
  if (!r) return "edge " + edge;
  if (r.kind === "circle") return `circular edge ${edge}, Ø${fmt(2 * r.r)} mm`;
  return `${r.kind === "line" ? "line" : "curved"} edge ${edge}` + (r.len ? `, L ${fmt(r.len)} mm` : "");
}
