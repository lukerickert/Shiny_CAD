// Shell elements drawn with their thickness (Analysis and Explicit views, Shell thickness).
//
// Each group of shell triangles (a shell body, section or part) with thickness t (mm) and offset o (fraction of t
// along the element normal: 0 mid-surface, 0.5 positive side, -0.5 negative side) becomes a slab: the triangles at
// the node positions + n t (o + 0.5) and + n t (o - 0.5), n the area-weighted normal of the node in the group, and
// side faces along the free edges of the group. Triangles of no group are kept.

/**
 * pos: Float32Array of the node positions (deformed or not); tri: Uint32Array of triangle node indices;
 * groups: [{tris: triangle indices, t, off}]; edges: element edge pairs (Uint32Array or array) or null.
 * Returns {pos: Float32Array, tri: Uint32Array, vsrc: node of each vertex, tsrc: source triangle of each triangle,
 * edges: element edges of the result (index pairs)}. The first pos.length / 3 vertices are the nodes.
 */
export function thicken(pos, tri, groups, edges) {
  const n0 = pos.length / 3, ntri = tri.length / 3;
  const P = Array.from(pos), vsrc = [], T = [], tsrc = [], E = [];
  for (let i = 0; i < n0; i++) vsrc.push(i);
  const done = new Uint8Array(ntri);
  const thickNodes = new Set();
  const groupMaps = [];
  for (const g of groups) {
    if (!(g.t > 0) || !g.tris || !g.tris.length) continue;
    const map = new Map(), N = [];
    const loc = v => { let i = map.get(v); if (i === undefined) { i = map.size; map.set(v, i); N.push(0, 0, 0); } return i; };
    const first = [];
    for (const k of g.tris) {
      done[k] = 1;
      const a = tri[3 * k], b = tri[3 * k + 1], c = tri[3 * k + 2];
      const ux = pos[3 * b] - pos[3 * a], uy = pos[3 * b + 1] - pos[3 * a + 1], uz = pos[3 * b + 2] - pos[3 * a + 2];
      const vx = pos[3 * c] - pos[3 * a], vy = pos[3 * c + 1] - pos[3 * a + 1], vz = pos[3 * c + 2] - pos[3 * a + 2];
      const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      for (const v of [a, b, c]) {
        const i = loc(v);
        N[3 * i] += nx; N[3 * i + 1] += ny; N[3 * i + 2] += nz;
        if (first[i] === undefined) first[i] = [nx, ny, nz];
      }
    }
    const nv = map.size, base = P.length / 3;
    const hi = g.t * ((g.off || 0) + 0.5), lo = g.t * ((g.off || 0) - 0.5);
    const unit = i => {
      let x = N[3 * i], y = N[3 * i + 1], z = N[3 * i + 2];
      let l = Math.hypot(x, y, z);
      if (l < 1e-12 && first[i]) { [x, y, z] = first[i]; l = Math.hypot(x, y, z); }   // opposite element normals
      return l > 0 ? [x / l, y / l, z / l] : [0, 0, 0];
    };
    const nodes = [...map.keys()];
    for (const f of [hi, lo]) for (const v of nodes) {
      const [x, y, z] = unit(map.get(v));
      P.push(pos[3 * v] + f * x, pos[3 * v + 1] + f * y, pos[3 * v + 2] + f * z);
      vsrc.push(v);
      thickNodes.add(v);
    }
    const top = v => base + map.get(v), bot = v => base + nv + map.get(v);
    const ecount = new Map();
    for (const k of g.tris) {
      const a = tri[3 * k], b = tri[3 * k + 1], c = tri[3 * k + 2];
      T.push(top(a), top(b), top(c), bot(a), bot(c), bot(b));
      tsrc.push(k, k);
      for (const [p, q] of [[a, b], [b, c], [c, a]]) {
        const key = p < q ? p + "," + q : q + "," + p;
        const e = ecount.get(key);
        if (e) e.n++; else ecount.set(key, { n: 1, p, q, k });
      }
    }
    for (const e of ecount.values()) {
      if (e.n !== 1) continue;                               // free edges of the group: side faces
      T.push(top(e.p), bot(e.p), bot(e.q), top(e.p), bot(e.q), top(e.q));
      tsrc.push(e.k, e.k);
      E.push(top(e.p), bot(e.p), top(e.q), bot(e.q));
    }
    groupMaps.push({ map, top, bot });
  }
  for (let k = 0; k < ntri; k++) if (!done[k]) { T.push(tri[3 * k], tri[3 * k + 1], tri[3 * k + 2]); tsrc.push(k); }
  if (edges) {
    for (let i = 0; i < edges.length; i += 2) {
      const a = edges[i], b = edges[i + 1];
      let inGroup = false;
      for (const gm of groupMaps) if (gm.map.has(a) && gm.map.has(b)) { E.push(gm.top(a), gm.top(b), gm.bot(a), gm.bot(b)); inGroup = true; }
      if (!inGroup) E.push(a, b);
    }
  }
  return { pos: new Float32Array(P), tri: new Uint32Array(T), vsrc: Uint32Array.from(vsrc), tsrc: Uint32Array.from(tsrc), edges: E, thickNodes };
}
