"use strict";
// Scoped: the sketch editor shares function names (setTool, undo, showProps, updateHint) with annotate.js.
(function () {
// 2D sketch editor: drafting, modify tools, geometric constraints, driving dimensions,
// DXF import/export and PDF export. Model coordinates in drawing units, y up.

const SK = {
  doc: null,
  view: { s: 2, ox: 100, oy: 400 },      // screen = (ox + s*x, oy - s*y)
  tool: "select",
  pick: [],                             // picks of the current tool
  sel: new Set(),                       // "e:id" entity, "p:id:k" point, "d:id" dimension, "c:id" constraint
  hover: null,
  mouse: null,                          // {x, y, sx, sy} model and screen
  snap: null,                           // {x, y, kind, ref}
  undo: [], redo: [],
  drag: null,
  pan: null,
  win: null,                            // window selection {x0, y0}
  fitCache: {},
  glyphs: [], dimHits: [],
  dirty: false,
  dof: null,
};
const SNAP_PX = 10, HIT_PX = 6;
const TOL = 1e-10;

// ------------------------------------------------------------------ small helpers

// message in the status bar and in the sketch command bar
function msg(text, isError) {
  status(text, isError);
  const el = document.getElementById("sk-msg");
  if (el) { el.textContent = text; el.title = text; el.classList.toggle("err", !!isError); }
}

const d2r = a => a * Math.PI / 180, r2d = a => a * 180 / Math.PI;
const n360 = a => { a %= 360; return a < 0 ? a + 360 : a; };
const hyp = Math.hypot;
const fmtN = (v, d = 3) => { let s = Number(v).toFixed(d).replace(/\.?0+$/, ""); return s === "-0" || s === "" ? "0" : s; };
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const mul = (a, k) => [a[0] * k, a[1] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
const crs = (a, b) => a[0] * b[1] - a[1] * b[0];
const len = a => hyp(a[0], a[1]);
const unit = a => { const l = len(a); return l > 1e-12 ? [a[0] / l, a[1] / l] : [1, 0]; };
const dist = (a, b) => hyp(a[0] - b[0], a[1] - b[1]);
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function arcSpan(e) { const s = n360(e.a1 - e.a0); return s < 1e-9 ? 360 : s; }
function angOnArc(e, ang) { return n360(ang - e.a0) <= arcSpan(e) + 1e-7; }
/** Ellipse (cx, cy, rx, ry, rot deg; a0, a1 parameter angles in deg, equal or missing: closed). */
function ellPt(e, t) {
  const r = d2r(e.rot || 0), tt = d2r(t), x = e.rx * Math.cos(tt), y = e.ry * Math.sin(tt);
  return [e.cx + x * Math.cos(r) - y * Math.sin(r), e.cy + x * Math.sin(r) + y * Math.cos(r)];
}
function ellClosed(e) { return e.a0 === undefined || e.a1 === undefined || Math.abs(n360(e.a1 - e.a0)) < 1e-9; }
function ellSpan(e) { return ellClosed(e) ? 360 : n360(e.a1 - e.a0); }
function ellPoly(e, n) {
  n = n || 64;
  const a0 = e.a0 || 0, sp = ellSpan(e), out = [];
  for (let i = 0; i <= n; i++) out.push(ellPt(e, a0 + sp * i / n));
  return out;
}
/** Cubic spline through the fit points (chord-length parameters, natural ends; periodic when closed).
 *  Parameter t: span index plus fraction, 0..m (m spans; closed: periodic in m). */
function splineSolve(pts, closed) {
  const n = pts.length;
  const P = closed ? pts.concat([pts[0]]) : pts.slice();
  const m = P.length - 1;
  const h = [];
  for (let i = 0; i < m; i++) h.push(Math.max(1e-9, dist(P[i], P[i + 1])));
  const solve = (cIdx) => {
    if (m < 1) return [0, 0];
    if (m === 1 && !closed) return [0, 0];
    const y = P.map(p => p[cIdx]);
    const N = closed ? m : m + 1, np = closed ? m : m + 1;
    const A = Array.from({ length: N }, () => new Array(N).fill(0)), b = new Array(N).fill(0);
    if (!closed) { A[0][0] = 1; A[N - 1][N - 1] = 1; }
    for (let i = closed ? 0 : 1; i < m; i++) {
      const hp = h[(i - 1 + m) % m], hc = h[i % m], r = i % N;
      A[r][(i - 1 + N) % N] += hp; A[r][r] += 2 * (hp + hc); A[r][(i + 1) % N] += hc;
      b[r] = 6 * ((y[(i + 1) % np] - y[i]) / hc - (y[i] - y[(i - 1 + np) % np]) / hp);
    }
    for (let c = 0; c < N; c++) {
      let piv = c; for (let r = c + 1; r < N; r++) if (Math.abs(A[r][c]) > Math.abs(A[piv][c])) piv = r;
      [A[c], A[piv]] = [A[piv], A[c]]; [b[c], b[piv]] = [b[piv], b[c]];
      if (Math.abs(A[c][c]) < 1e-14) continue;
      for (let r = c + 1; r < N; r++) { const f = A[r][c] / A[c][c]; if (!f) continue; for (let j = c; j < N; j++) A[r][j] -= f * A[c][j]; b[r] -= f * b[c]; }
    }
    const M = new Array(N).fill(0);
    for (let r = N - 1; r >= 0; r--) { let sm = b[r]; for (let j = r + 1; j < N; j++) sm -= A[r][j] * M[j]; M[r] = Math.abs(A[r][r]) < 1e-14 ? 0 : sm / A[r][r]; }
    return closed ? M.concat([M[0]]) : M;
  };
  return { P, h, m, closed, Mx: solve(0), My: solve(1) };
}
function splineAt(S, t) {
  const m = S.m;
  if (m < 1) return S.P[0].slice();
  if (S.closed) t = ((t % m) + m) % m;
  let i = Math.min(m - 1, Math.max(0, Math.floor(t))), u = t - i;
  if (!S.closed) { if (t <= 0) { i = 0; u = t; } else if (t >= m) { i = m - 1; u = t - i; } }
  const hi = S.h[i], a = 1 - u;
  const f = (y0, y1, M0, M1) => a * y0 + u * y1 + ((a * a * a - a) * M0 + (u * u * u - u) * M1) * hi * hi / 6;
  return [f(S.P[i][0], S.P[i + 1][0], S.Mx[i], S.Mx[i + 1]), f(S.P[i][1], S.P[i + 1][1], S.My[i], S.My[i + 1])];
}
/** Tangent direction (unit) at t. */
function splineTan(S, t) {
  const m = S.m;
  if (m < 1) return [1, 0];
  if (S.closed) t = ((t % m) + m) % m;
  const i = Math.min(m - 1, Math.max(0, Math.floor(t))), u = Math.min(1, Math.max(0, t - i)), hi = S.h[i], a = 1 - u;
  const d = (y0, y1, M0, M1) => (y1 - y0) + ((-(3 * a * a - 1)) * M0 + (3 * u * u - 1) * M1) * hi * hi / 6;
  return unit([d(S.P[i][0], S.P[i + 1][0], S.Mx[i], S.Mx[i + 1]), d(S.P[i][1], S.P[i + 1][1], S.My[i], S.My[i + 1])]);
}
/** Parameter range of a spline entity: [t0, t1] (default the whole curve). */
function splineRange(e) {
  const m = e.closed ? e.pts.length : e.pts.length - 1;
  const t0 = e.t0 === undefined || e.t0 === null ? 0 : e.t0, t1 = e.t1 === undefined || e.t1 === null ? m : e.t1;
  return [t0, t1];
}
/** Sample points of the spline (k per span) between t0 and t1, with the parameter of each: [{p, t}]. */
function splineSamples(pts, closed, k, t0, t1) {
  const S = splineSolve(pts, closed);
  k = k || 12;
  if (t0 === undefined) t0 = 0;
  if (t1 === undefined) t1 = S.m;
  const out = [{ p: splineAt(S, t0), t: t0 }];
  if (S.m >= 1 && (pts.length > 2 || closed)) {
    for (let i = Math.floor(t0 * k) + 1; i < t1 * k - 1e-9; i++) { const t = i / k; if (t > t0 + 1e-9) out.push({ p: splineAt(S, t), t }); }
  }
  out.push({ p: splineAt(S, t1), t: t1 });
  return out;
}
function splinePoly(pts, closed, k, t0, t1) {
  if (pts.length < 2) return pts.slice();
  return splineSamples(pts, closed, k, t0, t1).map(q => q.p);
}
function splinePolyE(e, k) { const [t0, t1] = splineRange(e); return splinePoly(e.pts, e.closed, k, t0, t1); }
/** Parameter of the spline point nearest to q (within the range of e). */
function splineParam(e, q, k) {
  const sm = splineSamples(e.pts, e.closed, k || 24, ...splineRange(e));
  let best = 0, bd = Infinity;
  for (let i = 0; i + 1 < sm.length; i++) {
    const a = sm[i].p, b = sm[i + 1].p, d = sub(b, a), L2 = dot(d, d) || 1, u = Math.max(0, Math.min(1, dot(sub(q, a), d) / L2));
    const dd = dist(q, add(a, mul(d, u)));
    if (dd < bd) { bd = dd; best = sm[i].t + (sm[i + 1].t - sm[i].t) * u; }
  }
  return best;
}
/** Parametric curve adapter for splines (parameter: span index + fraction) and ellipses (parameter angle, deg):
 *  range, at(t), tan(t), param(q), samples(k) -> [{p, t}], trim(lo, hi) keeps the range lo..hi, whole: a closed
 *  curve that has not been trimmed. */
function cvAdapter(e) {
  if (e.t === "spline") {
    const S = splineSolve(e.pts, e.closed), [t0, t1] = splineRange(e);
    return { range: [t0, t1], period: e.closed ? S.m : null, whole: !!e.closed && e.t0 === undefined && e.t1 === undefined,
      at: t => splineAt(S, t), tan: t => splineTan(S, t), param: q => splineParam(e, q),
      samples: k => splineSamples(e.pts, e.closed, k, t0, t1), trim: (lo, hi) => { e.t0 = lo; e.t1 = hi; } };
  }
  if (e.t === "ellipse") {
    const closed = ellClosed(e), a0 = e.a0 || 0, span = closed ? 360 : ellSpan(e), a1 = a0 + span;
    return { range: [a0, a1], period: 360, whole: closed,
      at: t => ellPt(e, t),
      tan: t => { const r = d2r(e.rot || 0), tt = d2r(t), x = -e.rx * Math.sin(tt), y = e.ry * Math.cos(tt); return unit([x * Math.cos(r) - y * Math.sin(r), x * Math.sin(r) + y * Math.cos(r)]); },
      param: q => { let t = a0 + n360(ellParam(e, q) - a0); if (t > a1 + 1e-9) t = (t - a1 < a0 + 360 - t) ? a1 : a0; return t; },
      samples: k => { const n = Math.max(24, Math.ceil(span / 360 * (k || 96))), out = []; for (let i = 0; i <= n; i++) { const t = a0 + span * i / n; out.push({ p: ellPt(e, t), t }); } return out; },
      trim: (lo, hi) => { e.a0 = n360(lo); e.a1 = n360(hi); if (Math.abs(n360(e.a1 - e.a0)) < 1e-9) e.a1 = e.a0 + 1e-6; } };
  }
  if (e.t === "conic") {
    const [t0, t1] = conicRange(e);
    return { range: [t0, t1], period: null, whole: false,
      at: t => conicPt(e, t), tan: t => conicTan(e, t), param: q => conicParam(e, q),
      samples: k => conicSamples(e, k), trim: (lo, hi) => { e.t0 = lo; e.t1 = hi; } };
  }
  return null;
}
/** Fix constraints of other entities whose point sits on an end of the spline or ellipse e: [{c, i}] (i: 0 start, 1 end). */
function curveAttachments(e) {
  const A = cvAdapter(e);
  if (!A || A.whole) return [];
  const out = [];
  A.range.forEach((t, i) => {
    const q = A.at(t), tol = 1e-3 * Math.max(1, Math.abs(q[0]), Math.abs(q[1]));
    for (const c of SK.doc.constraints) if (c.t === "fix" && c.a && c.a.e !== e.id && c.v && dist(c.v, q) < tol) out.push({ c, i });
  });
  return out;
}
/** After a change of the curve e: the attached fixed points move to the new end positions. */
function followAttached(e, att) {
  const A = cvAdapter(e);
  if (!A || !att || !att.length) return;
  for (const { c, i } of att) { const q = A.at(A.range[Math.min(i, A.range.length - 1)]); c.v = q.slice(); setPt(c.a, q); }
}
/** Transforms the entities ids with f (xformEnt) and carries the points fixed to the ends of splines and ellipses. */
function xformEnts(ids, f, opts) {
  const atts = ids.map(id => [entById(id), curveAttachments(entById(id))]);
  for (const [e] of atts) xformEnt(e, f, opts);
  const extra = new Set();
  for (const [e, att] of atts) { followAttached(e, att); att.forEach(x => extra.add(x.c.a.e)); }
  return [...extra];
}
/** Parameter angle (deg) of the ellipse point nearest in direction to p (for grips and arc ends). */
function ellParam(e, p) {
  const r = d2r(e.rot || 0), dx = p[0] - e.cx, dy = p[1] - e.cy;
  const x = dx * Math.cos(r) + dy * Math.sin(r), y = -dx * Math.sin(r) + dy * Math.cos(r);
  return n360(r2d(Math.atan2(y / (e.ry || 1), x / (e.rx || 1))));
}

/** Conic (rational quadratic Bezier): start (x0, y0), end (x1, y1), tangent intersection (xt, yt), rho (0..1:
 *  below 0.5 ellipse, 0.5 parabola, above 0.5 hyperbola). Parameter t 0..1; t0, t1: kept range after a trim. */
function conicW(e) { const r = Math.min(0.999, Math.max(0.001, e.rho === undefined ? 0.5 : e.rho)); return r / (1 - r); }
function conicPt(e, t) {
  const w = conicW(e), a = (1 - t) * (1 - t), b = 2 * w * t * (1 - t), c = t * t, den = a + b + c;
  return [(a * e.x0 + b * e.xt + c * e.x1) / den, (a * e.y0 + b * e.yt + c * e.y1) / den];
}
function conicTan(e, t) {
  const w = conicW(e), a = (1 - t) * (1 - t), b = 2 * w * t * (1 - t), c = t * t, den = a + b + c;
  const da = -2 * (1 - t), db = 2 * w * (1 - 2 * t), dc = 2 * t, dden = da + db + dc;
  const nx = a * e.x0 + b * e.xt + c * e.x1, ny = a * e.y0 + b * e.yt + c * e.y1;
  const dnx = da * e.x0 + db * e.xt + dc * e.x1, dny = da * e.y0 + db * e.yt + dc * e.y1;
  return unit([(dnx * den - nx * dden) / (den * den), (dny * den - ny * dden) / (den * den)]);
}
function conicRange(e) { return [e.t0 === undefined || e.t0 === null ? 0 : e.t0, e.t1 === undefined || e.t1 === null ? 1 : e.t1]; }
/** Shoulder point: the curve point at t = 0.5, on the line from the chord midpoint to the tangent intersection. */
function conicShoulder(e) { return conicPt(e, 0.5); }
function conicSamples(e, k) {
  const [t0, t1] = conicRange(e), n = Math.max(8, Math.ceil((k || 32) * (t1 - t0))), out = [];
  for (let i = 0; i <= n; i++) { const t = t0 + (t1 - t0) * i / n; out.push({ p: conicPt(e, t), t }); }
  return out;
}
function conicPolyE(e, k) { return conicSamples(e, k).map(q => q.p); }
window.conicPolyE = conicPolyE;
/** Parameter of the conic point nearest to q (within the range). */
function conicParam(e, q) {
  const sm = conicSamples(e, 64);
  let best = sm[0].t, bd = Infinity;
  for (let i = 0; i + 1 < sm.length; i++) {
    const a = sm[i].p, b = sm[i + 1].p, d = sub(b, a), L2 = dot(d, d) || 1, u = Math.max(0, Math.min(1, dot(sub(q, a), d) / L2));
    const dd = dist(q, add(a, mul(d, u)));
    if (dd < bd) { bd = dd; best = sm[i].t + (sm[i + 1].t - sm[i].t) * u; }
  }
  return best;
}
/** Rho of the conic whose shoulder point lies at p (projected on the line from the chord midpoint to the tangent intersection). */
function conicRhoAt(e, p) {
  const m = [(e.x0 + e.x1) / 2, (e.y0 + e.y1) / 2], d = sub([e.xt, e.yt], m), L2 = dot(d, d);
  if (L2 < 1e-18) return 0.5;
  return Math.min(0.98, Math.max(0.02, dot(sub(p, m), d) / L2));
}

function arcPt(e, a) { return [e.cx + e.r * Math.cos(d2r(a)), e.cy + e.r * Math.sin(d2r(a))]; }
function angOf(c, p) { return n360(r2d(Math.atan2(p[1] - c[1], p[0] - c[0]))); }

function ents() { return SK.doc ? SK.doc.entities : []; }
function entById(id) { return SK.idx ? SK.idx.get(id) : ents().find(e => e.id === id); }
function reindex() { SK.idx = new Map(ents().map(e => [e.id, e])); }
function newId(p) { const n = SK.doc.next_id++; return (p || "e") + n; }
function layerOf(e) { return SK.doc.layers.find(l => l.name === e.layer); }
function layerOn(e) { const l = layerOf(e); return !l || l.on !== false; }
const SOLVER_T = new Set(["line", "circle", "arc", "point"]);

// ------------------------------------------------------------------ point references {e, k}

function getPt(ref) {
  const e = entById(ref.e);
  if (!e) return null;
  const k = ref.k;
  switch (e.t) {
    case "line":
      if (k === "p1") return [e.x1, e.y1];
      if (k === "p2") return [e.x2, e.y2];
      if (k === "m") return [(e.x1 + e.x2) / 2, (e.y1 + e.y2) / 2];
      break;
    case "circle":
      if (k === "c") return [e.cx, e.cy];
      break;
    case "arc":
      if (k === "c") return [e.cx, e.cy];
      if (k === "s") return arcPt(e, e.a0);
      if (k === "e") return arcPt(e, e.a1);
      if (k === "m") return arcPt(e, e.a0 + arcSpan(e) / 2);
      break;
    case "point":
      if (k === "p") return [e.x, e.y];
      break;
    case "ellipse":
      if (k === "c") return [e.cx, e.cy];
      if (k === "ma") return ellPt(e, 0);
      if (k === "mb") return ellPt(e, 180);
      if (k === "na") return ellPt(e, 90);
      if (k === "nb") return ellPt(e, 270);
      if (k === "s") return ellPt(e, e.a0 || 0);
      if (k === "e") return ellPt(e, (e.a0 || 0) + ellSpan(e));
      break;
    case "conic":
      if (k === "s") return [e.x0, e.y0];
      if (k === "e") return [e.x1, e.y1];
      if (k === "t") return [e.xt, e.yt];
      if (k === "m") return conicShoulder(e);
      break;
    case "poly": case "spline": {
      if (k === "c" && e.pprof) return [e.pprof.cx, e.pprof.cy];
      const m = /^v(\d+)$/.exec(k);
      if (m && e.pts[+m[1]]) return e.pts[+m[1]].slice();
      if (e.t === "spline" && (k === "s" || k === "e")) { const A = cvAdapter(e); if (!A.whole) return A.at(A.range[k === "s" ? 0 : 1]); }
      break;
    }
    case "text":
      if (k === "p") return [e.x, e.y];
  }
  return null;
}

function setPt(ref, p) {
  const e = entById(ref.e);
  if (!e) return;
  const k = ref.k;
  if (e.t === "line") {
    if (k === "p1") { e.x1 = p[0]; e.y1 = p[1]; }
    else if (k === "p2") { e.x2 = p[0]; e.y2 = p[1]; }
  } else if (e.t === "circle" || (e.t === "arc" && k === "c")) {
    if (k === "c") { e.cx = p[0]; e.cy = p[1]; }
  } else if (e.t === "arc") {
    const a = angOf([e.cx, e.cy], p);
    e.r = dist([e.cx, e.cy], p) || e.r;
    if (k === "s") e.a0 = a; else if (k === "e") e.a1 = a;
  } else if (e.t === "point" || e.t === "text") {
    e.x = p[0]; e.y = p[1];
  } else if (e.t === "ellipse") {
    if (k === "c") { e.cx = p[0]; e.cy = p[1]; }
    else if (k === "ma" || k === "mb") { const d = sub(p, [e.cx, e.cy]); e.rx = Math.hypot(d[0], d[1]) || e.rx; e.rot = n360(r2d(Math.atan2(d[1], d[0])) + (k === "mb" ? 180 : 0)); }
    else if (k === "na" || k === "nb") { e.ry = dist(p, [e.cx, e.cy]) || e.ry; }
    else if (k === "s") e.a0 = ellParam(e, p);
    else if (k === "e") e.a1 = ellParam(e, p);
  } else if (e.t === "conic") {
    if (k === "s") { e.x0 = p[0]; e.y0 = p[1]; }
    else if (k === "e") { e.x1 = p[0]; e.y1 = p[1]; }
    else if (k === "t") { e.xt = p[0]; e.yt = p[1]; }
    else if (k === "m") e.rho = conicRhoAt(e, p);
  } else if (e.t === "poly" || e.t === "spline") {
    if (k === "c" && e.pprof) { const d = sub(p, [e.pprof.cx, e.pprof.cy]); e.pprof.cx = p[0]; e.pprof.cy = p[1]; e.pts = e.pts.map(q => [q[0] + d[0], q[1] + d[1]]); return; }
    const m = /^v(\d+)$/.exec(k);
    if (m) e.pts[+m[1]] = [p[0], p[1]];
    else if (e.t === "spline" && !e.closed && e.t0 === undefined && e.t1 === undefined && (k === "s" || k === "e")) e.pts[k === "s" ? 0 : e.pts.length - 1] = [p[0], p[1]];
  }
}

function grips(e) {
  switch (e.t) {
    case "line": return [["p1", [e.x1, e.y1]], ["p2", [e.x2, e.y2]]];
    case "circle": return [["c", [e.cx, e.cy]]];
    case "arc": return [["c", [e.cx, e.cy]], ["s", arcPt(e, e.a0)], ["e", arcPt(e, e.a1)]];
    case "point": return [["p", [e.x, e.y]]];
    case "ellipse": return [["c", [e.cx, e.cy]], ["ma", ellPt(e, 0)], ["mb", ellPt(e, 180)], ["na", ellPt(e, 90)], ["nb", ellPt(e, 270)]].concat(ellClosed(e) ? [] : [["s", ellPt(e, e.a0)], ["e", ellPt(e, e.a0 + ellSpan(e))]]);
    case "poly": return e.pprof ? [["c", [e.pprof.cx, e.pprof.cy]]] : e.pts.map((p, i) => ["v" + i, p]);
    case "spline": return e.pts.map((p, i) => ["v" + i, p]);
    case "conic": return [["s", [e.x0, e.y0]], ["e", [e.x1, e.y1]], ["t", [e.xt, e.yt]], ["m", conicShoulder(e)]];
    case "text": return [["p", [e.x, e.y]]];
  }
  return [];
}
function refKey(r) { return "p:" + r.e + ":" + r.k; }
function parseSel(s) {
  const a = s.split(":");
  return { kind: a[0], id: a[1], k: a[2] };
}

// ------------------------------------------------------------------ curves and geometry

// curve pieces: {s: "seg", a, b} or {s: "circ", c, r, a0, span} (full circle: span 360)
function curves(e) {
  switch (e.t) {
    case "line": return [{ s: "seg", a: [e.x1, e.y1], b: [e.x2, e.y2] }];
    case "circle": return [{ s: "circ", c: [e.cx, e.cy], r: e.r, a0: 0, span: 360 }];
    case "arc": return [{ s: "circ", c: [e.cx, e.cy], r: e.r, a0: e.a0, span: arcSpan(e) }];
    case "poly": {
      const out = [];
      for (let i = 0; i + 1 < e.pts.length; i++) out.push({ s: "seg", a: e.pts[i], b: e.pts[i + 1] });
      if (e.closed && e.pts.length > 2) out.push({ s: "seg", a: e.pts[e.pts.length - 1], b: e.pts[0] });
      return out;
    }
    case "ellipse": case "spline": case "conic": {
      const pts = e.t === "spline" ? splinePolyE(e, 16) : e.t === "conic" ? conicPolyE(e, 48) : ellPoly(e, 96), out = [];
      for (let i = 0; i + 1 < pts.length; i++) out.push({ s: "seg", a: pts[i], b: pts[i + 1] });
      return out;
    }
  }
  return [];
}

function textBox(e) {
  const lines = String(e.text || "").split("\n");
  const w = Math.max(...lines.map(t => textW(t, e.h)), e.h);
  const r = d2r(e.rot || 0), u = [Math.cos(r), Math.sin(r)], v = [-Math.sin(r), Math.cos(r)];
  const off = e.anchor === "middle" ? -w / 2 : e.anchor === "end" ? -w : 0;
  const pts = [];
  for (const s of [off, off + w]) for (const t of [e.h, -(lines.length - 1) * 1.6 * e.h]) {
    pts.push([e.x + u[0] * s + v[0] * t, e.y + u[1] * s + v[1] * t]);
  }
  return pts;
}

function bbox(e) {
  let pts;
  switch (e.t) {
    case "line": pts = [[e.x1, e.y1], [e.x2, e.y2]]; break;
    case "circle": pts = [[e.cx - e.r, e.cy - e.r], [e.cx + e.r, e.cy + e.r]]; break;
    case "arc": {
      pts = [arcPt(e, e.a0), arcPt(e, e.a1)];
      for (const q of [0, 90, 180, 270]) if (angOnArc(e, q)) pts.push(arcPt(e, q));
      break;
    }
    case "point": pts = [[e.x, e.y]]; break;
    case "poly": pts = e.pts; break;
    case "spline": pts = splinePolyE(e, 8); break;
    case "conic": pts = conicPolyE(e, 16); break;
    case "ellipse": pts = ellPoly(e, 48); break;
    case "text": pts = textBox(e); break;
    default: pts = [];
  }
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of pts) { x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]); }
  return [x0, y0, x1, y1];
}

function segDist(p, a, b) {
  const d = sub(b, a), L2 = dot(d, d);
  const t = L2 > 0 ? Math.max(0, Math.min(1, dot(sub(p, a), d) / L2)) : 0;
  return dist(p, add(a, mul(d, t)));
}

function entDist(e, p) {
  switch (e.t) {
    case "line": return segDist(p, [e.x1, e.y1], [e.x2, e.y2]);
    case "circle": return Math.abs(dist(p, [e.cx, e.cy]) - e.r);
    case "arc": {
      const a = angOf([e.cx, e.cy], p);
      if (angOnArc(e, a)) return Math.abs(dist(p, [e.cx, e.cy]) - e.r);
      return Math.min(dist(p, arcPt(e, e.a0)), dist(p, arcPt(e, e.a1)));
    }
    case "point": return dist(p, [e.x, e.y]);
    case "ellipse": case "spline": case "conic": { let m = Infinity; for (const c of curves(e)) m = Math.min(m, segDist(p, c.a, c.b)); return m; }
    case "poly": {
      let m = Infinity;
      for (const c of curves(e)) m = Math.min(m, segDist(p, c.a, c.b));
      if (e.fill && pointInPoly(p, e.pts)) m = 0;
      return m;
    }
    case "text": return pointInPoly(p, [textBox(e)[0], textBox(e)[2], textBox(e)[3], textBox(e)[1]]) ? 0 : Infinity;
  }
  return Infinity;
}

function pointInPoly(p, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const a = pts[i], b = pts[j];
    if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}

function nearestOn(e, p) {
  switch (e.t) {
    case "line": {
      const a = [e.x1, e.y1], d = sub([e.x2, e.y2], a), L2 = dot(d, d);
      const t = L2 > 0 ? Math.max(0, Math.min(1, dot(sub(p, a), d) / L2)) : 0;
      return add(a, mul(d, t));
    }
    case "circle": case "arc": {
      const c = [e.cx, e.cy];
      const q = add(c, mul(unit(sub(p, c)), e.r));
      if (e.t === "arc" && !angOnArc(e, angOf(c, q))) return null;
      return q;
    }
  }
  return null;
}

// intersections; inf: treat segments as infinite lines, circles ignore the arc span
function intersect(c1, c2, inf1, inf2) {
  const out = [];
  const onSeg = (c, p, inf) => {
    if (inf) return true;
    const d = sub(c.b, c.a), L2 = dot(d, d);
    const t = dot(sub(p, c.a), d) / L2;
    return t >= -1e-9 && t <= 1 + 1e-9;
  };
  const onCirc = (c, p, inf) => inf || c.span >= 360 || n360(angOf(c.c, p) - c.a0) <= c.span + 1e-7;
  const on = (c, p, inf) => c.s === "seg" ? onSeg(c, p, inf) : onCirc(c, p, inf);
  let pts = [];
  if (c1.s === "seg" && c2.s === "seg") {
    const d1 = sub(c1.b, c1.a), d2 = sub(c2.b, c2.a), den = crs(d1, d2);
    if (Math.abs(den) < 1e-12 * len(d1) * len(d2)) return out;
    const t = crs(sub(c2.a, c1.a), d2) / den;
    pts = [add(c1.a, mul(d1, t))];
  } else if (c1.s === "circ" && c2.s === "circ") {
    const d = dist(c1.c, c2.c);
    if (d < 1e-12 || d > c1.r + c2.r + 1e-9 || d < Math.abs(c1.r - c2.r) - 1e-9) return out;
    const a = (c1.r * c1.r - c2.r * c2.r + d * d) / (2 * d);
    const h = Math.sqrt(Math.max(0, c1.r * c1.r - a * a));
    const u = unit(sub(c2.c, c1.c)), m = add(c1.c, mul(u, a));
    pts = h < 1e-12 ? [m] : [add(m, mul([-u[1], u[0]], h)), add(m, mul([u[1], -u[0]], h))];
  } else {
    const [sg, ci, infS, infC] = c1.s === "seg" ? [c1, c2, inf1, inf2] : [c2, c1, inf2, inf1];
    const d = sub(sg.b, sg.a), f = sub(sg.a, ci.c);
    const A = dot(d, d), B = 2 * dot(f, d), C = dot(f, f) - ci.r * ci.r;
    const disc = B * B - 4 * A * C;
    if (disc < -1e-12 * A * ci.r * ci.r) return out;
    const sq = Math.sqrt(Math.max(0, disc));
    pts = sq < 1e-12 ? [add(sg.a, mul(d, -B / (2 * A)))]
      : [add(sg.a, mul(d, (-B - sq) / (2 * A))), add(sg.a, mul(d, (-B + sq) / (2 * A)))];
    return pts.filter(p => on(sg, p, infS) && on(ci, p, infC));
  }
  return pts.filter(p => on(c1, p, inf1) && on(c2, p, inf2));
}

function bboxOverlap(a, b, m) {
  return !(a[2] + m < b[0] || b[2] + m < a[0] || a[3] + m < b[1] || b[3] + m < a[1]);
}

// ------------------------------------------------------------------ text width (Arial metrics)

const _tw = document.createElement("canvas").getContext("2d");
function textW(t, h) {
  _tw.font = "100px Arial, Helvetica, sans-serif";
  return _tw.measureText(t || "").width / 100 * h / 0.72;
}

// ------------------------------------------------------------------ constraint solver
// Parameters: line x1 y1 x2 y2; circle cx cy r; arc cx cy r a0 a1 (radians); point x y.
// Gauss-Newton with minimum-norm steps (J^T (J J^T + mu I)^-1 r), finite-difference Jacobian.

const PARAMS = { line: ["x1", "y1", "x2", "y2"], circle: ["cx", "cy", "r"], arc: ["cx", "cy", "r", "a0", "a1"], point: ["x", "y"] };
/** Curve types that are solver geometry through their defining points: conic (start, end, tangent intersection,
 *  rho), ellipse (centre, half axes, rotation, start and end angle when open), spline (fit points). */
const CURVE_T = new Set(["conic", "ellipse", "spline"]);
function isSolver(e) { return !!e && (SOLVER_T.has(e.t) || CURVE_T.has(e.t)); }
/** Solver parameter values of an entity (angles in radians). */
function entVals(e) {
  switch (e.t) {
    case "conic": return [e.x0, e.y0, e.x1, e.y1, e.xt, e.yt, e.rho === undefined ? 0.5 : e.rho];
    case "ellipse": { const v = [e.cx, e.cy, e.rx, e.ry, d2r(e.rot || 0)]; if (!ellClosed(e)) v.push(d2r(e.a0), d2r(e.a1)); return v; }
    case "spline": return e.pts.flat();
    default: return PARAMS[e.t].map(q => e.t === "arc" && (q === "a0" || q === "a1") ? d2r(e[q]) : e[q]);
  }
}
/** Writes solver parameter values back to the entity. */
function setEntVals(e, v) {
  switch (e.t) {
    case "conic": [e.x0, e.y0, e.x1, e.y1, e.xt, e.yt] = v.slice(0, 6); e.rho = Math.min(0.99, Math.max(0.01, v[6])); return;
    case "ellipse":
      e.cx = v[0]; e.cy = v[1]; e.rx = Math.abs(v[2]); e.ry = Math.abs(v[3]); e.rot = n360(r2d(v[4]));
      if (v.length > 6) { e.a0 = n360(r2d(v[5])); e.a1 = n360(r2d(v[6])); if (Math.abs(n360(e.a1 - e.a0)) < 1e-9) e.a1 = e.a0 + 1e-6; }
      return;
    case "spline": { const pts = []; for (let i = 0; i + 1 < v.length; i += 2) pts.push([v[i], v[i + 1]]); e.pts = pts; return; }
    default:
      PARAMS[e.t].forEach((q, i) => { let val = v[i]; if (e.t === "arc" && (q === "a0" || q === "a1")) val = n360(r2d(val)); e[q] = val; });
      if (e.r !== undefined && e.r < 0) e.r = -e.r;
  }
}
/** A copy of the entity with the solver values taken from x at base b (for residuals of curves). */
function entFromX(e, x, b, n) { const c = Object.assign({}, e); setEntVals(c, x.slice(b, b + n)); return c; }
/** Ends of an open curve as point refs: [["s", p], ["e", p]]; [] for a closed curve or other types. */
function curveEnds(e) {
  const A = cvAdapter(e);
  if (!A || A.whole) return [];
  return [["s", A.at(A.range[0])], ["e", A.at(A.range[1])]];
}
/** Whether the tangent constraint record needs an end key for this entity (arc or curve). */
function needsEndKey(e) { return !!e && (e.t === "arc" || CURVE_T.has(e.t)); }
const DRAG_WEIGHT = 0.02;

class System {
  constructor() { this.x = []; this.base = new Map(); this.count = new Map(); this.res = []; this.bad = false; this.naux = 0; }
  ensure(id) {
    if (this.base.has(id)) return this.base.get(id);
    const e = entById(id);
    if (!isSolver(e)) { this.bad = true; return null; }
    const b = this.x.length;
    const vals = entVals(e);
    this.base.set(id, b);
    this.count.set(id, vals.length);
    for (const v of vals) this.x.push(v);
    return b;
  }
  /** An auxiliary unknown (a curve parameter of a point-on-curve or tangent constraint). Returns its index. */
  aux(v) { this.x.push(v); this.naux++; return this.x.length - 1; }
  /** Curve accessor: {deps, ent(x) -> entity with the values of x, A(x) -> cvAdapter of it}. */
  K(id) {
    const e = entById(id);
    if (!e || !CURVE_T.has(e.t)) { this.bad = true; return null; }
    const b = this.ensure(id), n = this.count.get(id);
    const deps = []; for (let i = 0; i < n; i++) deps.push(b + i);
    const ent = x => entFromX(e, x, b, n);
    return { deps, b, n, e, ent, A: x => cvAdapter(ent(x)) };
  }
  /** Unit tangent direction at an end: line (k ignored), arc end k ("s"/"e"), curve end k ("s"/"e"). */
  T(id, k) {
    const e = entById(id);
    if (!e) { this.bad = true; return null; }
    if (e.t === "line") { const L = this.L(id); return L && { deps: L.deps, f: x => { const v = L.f(x); return unit([v[2] - v[0], v[3] - v[1]]); } }; }
    if (e.t === "arc" || e.t === "circle") {
      const b = this.ensure(id); if (b === null) return null;
      const j = k === "e" ? b + 4 : b + 3;
      return { deps: [j], f: x => [-Math.sin(x[j]), Math.cos(x[j])] };
    }
    if (CURVE_T.has(e.t)) {
      const K = this.K(id); if (!K) return null;
      if (cvAdapter(e).whole) { this.bad = true; return null; }
      return { deps: K.deps, f: x => { const A = K.A(x); return A.tan(A.range[k === "e" ? 1 : 0]); } };
    }
    this.bad = true;
    return null;
  }
  P(ref) {          // point: {deps, f(x) -> [x, y]}
    const e = entById(ref.e);
    const b = this.ensure(ref.e);
    if (b === null) return null;
    const k = ref.k;
    if (CURVE_T.has(e.t)) {
      const K = this.K(ref.e);
      const trimmed = e.t0 !== undefined || e.t1 !== undefined;
      if (e.t === "conic" && !trimmed) {
        if (k === "s") return { deps: [b, b + 1], f: x => [x[b], x[b + 1]] };
        if (k === "e") return { deps: [b + 2, b + 3], f: x => [x[b + 2], x[b + 3]] };
      }
      if (e.t === "conic" && k === "t") return { deps: [b + 4, b + 5], f: x => [x[b + 4], x[b + 5]] };
      if (e.t === "conic" && k === "m") return { deps: K.deps, f: x => conicShoulder(K.ent(x)) };
      if (e.t === "spline") {
        const m = /^v(\d+)$/.exec(k);
        if (m && +m[1] < e.pts.length) { const i = b + 2 * (+m[1]); return { deps: [i, i + 1], f: x => [x[i], x[i + 1]] }; }
        if (!trimmed && !e.closed && (k === "s" || k === "e")) { const i = k === "s" ? b : b + 2 * (e.pts.length - 1); return { deps: [i, i + 1], f: x => [x[i], x[i + 1]] }; }
      }
      if (e.t === "ellipse") {
        if (k === "c") return { deps: [b, b + 1], f: x => [x[b], x[b + 1]] };
        const ang = { ma: 0, mb: 180, na: 90, nb: 270 }[k];
        if (ang !== undefined) return { deps: K.deps, f: x => ellPt(K.ent(x), ang) };
      }
      if ((k === "s" || k === "e") && !cvAdapter(e).whole) return { deps: K.deps, f: x => { const A = K.A(x); return A.at(A.range[k === "e" ? 1 : 0]); } };
      this.bad = true;
      return null;
    }
    if (e.t === "line") {
      if (k === "p1") return { deps: [b, b + 1], f: x => [x[b], x[b + 1]] };
      if (k === "p2") return { deps: [b + 2, b + 3], f: x => [x[b + 2], x[b + 3]] };
      if (k === "m") return { deps: [b, b + 1, b + 2, b + 3], f: x => [(x[b] + x[b + 2]) / 2, (x[b + 1] + x[b + 3]) / 2] };
    } else if (e.t === "circle" || e.t === "arc") {
      if (k === "c") return { deps: [b, b + 1], f: x => [x[b], x[b + 1]] };
      if (e.t === "arc" && (k === "s" || k === "e")) {
        const j = k === "s" ? b + 3 : b + 4;
        return { deps: [b, b + 1, b + 2, j], f: x => [x[b] + x[b + 2] * Math.cos(x[j]), x[b + 1] + x[b + 2] * Math.sin(x[j])] };
      }
    } else if (e.t === "point" && k === "p") {
      return { deps: [b, b + 1], f: x => [x[b], x[b + 1]] };
    }
    this.bad = true;
    return null;
  }
  L(id) {           // line: [ax, ay, bx, by]
    const e = entById(id);
    if (!e || e.t !== "line") { this.bad = true; return null; }
    const b = this.ensure(id);
    return { deps: [b, b + 1, b + 2, b + 3], f: x => [x[b], x[b + 1], x[b + 2], x[b + 3]] };
  }
  C(id) {           // circle/arc: [cx, cy, r]
    const e = entById(id);
    if (!e || (e.t !== "circle" && e.t !== "arc")) { this.bad = true; return null; }
    const b = this.ensure(id);
    return { deps: [b, b + 1, b + 2], f: x => [x[b], x[b + 1], x[b + 2]] };
  }
  add(deps, f, tag) {
    // a drag is a weak residual: when it conflicts with the constraints, the constraints win and the geometry
    // stays in place instead of moving to a compromise that snaps back on release
    if (tag === "drag") { const g = f; f = x => DRAG_WEIGHT * g(x); }
    this.res.push({ deps: [...new Set(deps)], f, tag });
  }

  // residuals of one constraint record
  addCon(c, tag) {
    const S = this;
    const t = c.t;
    const lineDir = (L, x) => { const v = L.f(x); return [v[2] - v[0], v[3] - v[1]]; };
    if (t === "coincident" || t === "concentric") {
      const A = t === "coincident" ? S.P(c.a) : S.P({ e: c.e1, k: "c" });
      const B = t === "coincident" ? S.P(c.b) : S.P({ e: c.e2, k: "c" });
      if (!A || !B) return;
      S.add([...A.deps, ...B.deps], x => A.f(x)[0] - B.f(x)[0], tag);
      S.add([...A.deps, ...B.deps], x => A.f(x)[1] - B.f(x)[1], tag);
    } else if (t === "horizontal" || t === "vertical") {
      const i = t === "horizontal" ? 1 : 0;
      if (c.l) {
        const L = S.L(c.l); if (!L) return;
        S.add(L.deps, x => { const v = L.f(x); return v[2 + i] - v[i]; }, tag);
      } else {
        const A = S.P(c.a), B = S.P(c.b); if (!A || !B) return;
        S.add([...A.deps, ...B.deps], x => B.f(x)[i] - A.f(x)[i], tag);
      }
    } else if (t === "parallel" || t === "perpendicular") {
      const A = S.L(c.l1), B = S.L(c.l2); if (!A || !B) return;
      S.add([...A.deps, ...B.deps], x => {
        const u = lineDir(A, x), v = lineDir(B, x), n = (len(u) * len(v)) || 1;
        return (t === "parallel" ? crs(u, v) : dot(u, v)) / n;
      }, tag);
    } else if (t === "tangent") {
      const e1 = entById(c.e1), e2 = entById(c.e2);
      if (!e1 || !e2) { S.bad = true; return; }
      if (CURVE_T.has(e1.t) || CURVE_T.has(e2.t)) {
        if (c.ak1 || c.ak2) {
          // tangent at a shared end: parallel tangent directions there
          const T1 = S.T(c.e1, c.ak1), T2 = S.T(c.e2, c.ak2); if (!T1 || !T2) return;
          S.add([...T1.deps, ...T2.deps], x => crs(T1.f(x), T2.f(x)), tag);
          return;
        }
        // tangent contact away from the ends: the curve point at an auxiliary parameter lies on the other entity
        // with parallel tangents there
        const [ci, oi] = CURVE_T.has(e1.t) ? [c.e1, c.e2] : [c.e2, c.e1];
        const K = S.K(ci), o = entById(oi); if (!K || !o) return;
        if (CURVE_T.has(o.t)) { S.bad = true; return; }
        const A0 = cvAdapter(K.e);
        const guess = o.t === "line" ? A0.param([(o.x1 + o.x2) / 2, (o.y1 + o.y2) / 2]) : A0.param(add([o.cx, o.cy], mul(unit(sub(A0.at((A0.range[0] + A0.range[1]) / 2), [o.cx, o.cy])), o.r)));
        const j = S.aux(c.u !== undefined ? c.u : guess);
        if (o.t === "line") {
          const L = S.L(oi); if (!L) return;
          S.add([...K.deps, ...L.deps, j], x => { const A = K.A(x), v = L.f(x), d = [v[2] - v[0], v[3] - v[1]]; return crs(sub(A.at(x[j]), [v[0], v[1]]), d) / (len(d) || 1); }, tag);
          S.add([...K.deps, ...L.deps, j], x => { const A = K.A(x), v = L.f(x); return crs(A.tan(x[j]), unit([v[2] - v[0], v[3] - v[1]])); }, tag);
        } else {
          const C = S.C(oi); if (!C) return;
          S.add([...K.deps, ...C.deps, j], x => { const A = K.A(x), q = C.f(x), p = A.at(x[j]); return hyp(p[0] - q[0], p[1] - q[1]) - q[2]; }, tag);
          S.add([...K.deps, ...C.deps, j], x => { const A = K.A(x), q = C.f(x), p = A.at(x[j]); return dot(A.tan(x[j]), unit(sub(p, [q[0], q[1]]))); }, tag);
        }
        return;
      }
      if (c.ak1 || c.ak2) {
        // tangent at a shared end point: the radius at the arc end is normal to the line (or to the other radius)
        const angIdx = (id, k) => { const b = S.ensure(id); return b === null ? null : b + (k === "s" ? 3 : 4); };
        if (e1.t === "line" || e2.t === "line") {
          const [li, ai, ak] = e1.t === "line" ? [c.e1, c.e2, c.ak2] : [c.e2, c.e1, c.ak1];
          const L = S.L(li), j = angIdx(ai, ak); if (!L || j === null) return;
          S.add([...L.deps, j], x => { const v = L.f(x), d = [v[2] - v[0], v[3] - v[1]]; return dot(d, [Math.cos(x[j]), Math.sin(x[j])]) / (len(d) || 1); }, tag);
        } else {
          const i = angIdx(c.e1, c.ak1), j = angIdx(c.e2, c.ak2); if (i === null || j === null) return;
          S.add([i, j], x => Math.sin(x[i] - x[j]), tag);
        }
        return;
      }
      if (e1.t === "line" || e2.t === "line") {
        const [li, ci] = e1.t === "line" ? [c.e1, c.e2] : [c.e2, c.e1];
        const L = S.L(li), C = S.C(ci); if (!L || !C) return;
        // the side of the line the centre is on now is kept (a signed distance has a gradient at distance 0)
        const side = (x => { const v = L.f(x), q = C.f(x); return Math.sign(crs(sub([q[0], q[1]], [v[0], v[1]]), [v[2] - v[0], v[3] - v[1]])) || 1; })(S.x);
        S.add([...L.deps, ...C.deps], x => {
          const v = L.f(x), q = C.f(x), d = [v[2] - v[0], v[3] - v[1]];
          return side * crs(sub([q[0], q[1]], [v[0], v[1]]), d) / (len(d) || 1) - q[2];
        }, tag);
      } else {
        const A = S.C(c.e1), B = S.C(c.e2); if (!A || !B) return;
        S.add([...A.deps, ...B.deps], x => {
          const a = A.f(x), b = B.f(x), d = hyp(a[0] - b[0], a[1] - b[1]);
          return c.mode === "int" ? d - Math.abs(a[2] - b[2]) : d - (a[2] + b[2]);
        }, tag);
      }
    } else if (t === "equal") {
      const e1 = entById(c.e1);
      if (!e1) { S.bad = true; return; }
      if (e1.t === "line") {
        const A = S.L(c.e1), B = S.L(c.e2); if (!A || !B) return;
        S.add([...A.deps, ...B.deps], x => len(lineDir(A, x)) - len(lineDir(B, x)), tag);
      } else {
        const A = S.C(c.e1), B = S.C(c.e2); if (!A || !B) return;
        S.add([...A.deps, ...B.deps], x => A.f(x)[2] - B.f(x)[2], tag);
      }
    } else if (t === "pointon") {
      const A = S.P(c.a); const e = entById(c.e2);
      if (!A || !e) { S.bad = true; return; }
      if (CURVE_T.has(e.t)) {
        // point on a curve: the curve parameter is an auxiliary unknown
        const K = S.K(c.e2); if (!K) return;
        const p0 = getPt(c.a), A0 = cvAdapter(e);
        const j = S.aux(p0 ? A0.param(p0) : (A0.range[0] + A0.range[1]) / 2);
        S.add([...A.deps, ...K.deps, j], x => A.f(x)[0] - K.A(x).at(x[j])[0], tag);
        S.add([...A.deps, ...K.deps, j], x => A.f(x)[1] - K.A(x).at(x[j])[1], tag);
        return;
      }
      if (e.t === "line") {
        const L = S.L(c.e2); if (!L) return;
        S.add([...A.deps, ...L.deps], x => {
          const v = L.f(x), p = A.f(x), d = [v[2] - v[0], v[3] - v[1]];
          return crs(sub(p, [v[0], v[1]]), d) / (len(d) || 1);
        }, tag);
      } else {
        const C = S.C(c.e2); if (!C) return;
        S.add([...A.deps, ...C.deps], x => { const q = C.f(x), p = A.f(x); return hyp(p[0] - q[0], p[1] - q[1]) - q[2]; }, tag);
      }
    } else if (t === "midpoint") {
      const A = S.P(c.a), L = S.L(c.l); if (!A || !L) return;
      S.add([...A.deps, ...L.deps], x => { const v = L.f(x); return A.f(x)[0] - (v[0] + v[2]) / 2; }, tag);
      S.add([...A.deps, ...L.deps], x => { const v = L.f(x); return A.f(x)[1] - (v[1] + v[3]) / 2; }, tag);
    } else if (t === "symmetric") {
      const A = S.P(c.a), B = S.P(c.b), L = S.L(c.l); if (!A || !B || !L) return;
      const deps = [...A.deps, ...B.deps, ...L.deps];
      S.add(deps, x => {
        const v = L.f(x), p = A.f(x), q = B.f(x), d = [v[2] - v[0], v[3] - v[1]];
        const m = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
        return crs(sub(m, [v[0], v[1]]), d) / (len(d) || 1);
      }, tag);
      S.add(deps, x => {
        const v = L.f(x), p = A.f(x), q = B.f(x), d = [v[2] - v[0], v[3] - v[1]];
        return dot(sub(q, p), d) / (len(d) || 1);
      }, tag);
    } else if (t === "fix") {
      if (c.a) {
        const A = S.P(c.a); if (!A) return;
        S.add(A.deps, x => A.f(x)[0] - c.v[0], tag);
        S.add(A.deps, x => A.f(x)[1] - c.v[1], tag);
      } else if (c.param !== undefined) {
        // one parameter held (the radius of a circle made tangent)
        const b = S.ensure(c.e); if (b === null) return;
        S.add([b + c.param], x => x[b + c.param] - c.v, tag);
      } else {
        const b = S.ensure(c.e); if (b === null) return;
        const n = S.count.get(c.e);
        c.vals.forEach((v, i) => { if (i < n) S.add([b + i], x => x[b + i] - v, tag); });
      }
    } else if (t === "drag") {              // temporary: point to target
      const A = S.P(c.a); if (!A) return;
      S.add(A.deps, x => A.f(x)[0] - c.v[0], tag);
      S.add(A.deps, x => A.f(x)[1] - c.v[1], tag);
    } else if (t === "dragr") {
      const C = S.C(c.e); if (!C) return;
      S.add(C.deps, x => C.f(x)[2] - c.v, tag);
    } else if (t === "dist") {             // |AB| = v, or |B - A| along x / y
      const A = S.P(c.a), B = S.P(c.b); if (!A || !B) return;
      S.add([...A.deps, ...B.deps], x => {
        const p = A.f(x), q = B.f(x);
        if (c.o === "h") return Math.abs(q[0] - p[0]) - c.v;
        if (c.o === "v") return Math.abs(q[1] - p[1]) - c.v;
        return hyp(q[0] - p[0], q[1] - p[1]) - c.v;
      }, tag);
    } else if (t === "pldist") {           // point to line distance
      const A = S.P(c.a), L = S.L(c.l); if (!A || !L) return;
      S.add([...A.deps, ...L.deps], x => {
        const v = L.f(x), p = A.f(x), d = [v[2] - v[0], v[3] - v[1]];
        return Math.abs(crs(sub(p, [v[0], v[1]]), d)) / (len(d) || 1) - c.v;
      }, tag);
    } else if (t === "radius") {
      const C = S.C(c.e); if (!C) return;
      S.add(C.deps, x => C.f(x)[2] * (c.dia ? 2 : 1) - c.v, tag);
    } else if (t === "angle") {
      const A = S.L(c.l1), B = S.L(c.l2); if (!A || !B) return;
      const v = d2r(c.v);
      S.add([...A.deps, ...B.deps], x => {
        const u = mul(lineDir(A, x), c.s1), w = mul(lineDir(B, x), c.s2);
        let a = Math.atan2(crs(u, w), dot(u, w)) - v;
        while (a > Math.PI) a -= 2 * Math.PI;
        while (a < -Math.PI) a += 2 * Math.PI;
        return a;
      }, tag);
    }
  }

  r(x) { return this.res.map(q => q.f(x)); }
  jac(x) {
    const rows = [];
    for (const q of this.res) {
      const row = new Map();
      for (const j of q.deps) {
        const v = x[j], h = 1e-7 * Math.max(1, Math.abs(v));
        x[j] = v + h; const fp = q.f(x);
        x[j] = v - h; const fm = q.f(x);
        x[j] = v;
        const g = (fp - fm) / (2 * h);
        if (g !== 0) row.set(j, g);
      }
      rows.push(row);
    }
    return rows;
  }
  solve(maxIt = 60) {
    const x = this.x.slice();
    const m = this.res.length;
    if (!m) return { ok: true, x };
    let r = this.r(x), nr = Math.max(...r.map(Math.abs));
    let mu = 1e-9;
    for (let it = 0; it < maxIt && nr > TOL; it++) {
      const J = this.jac(x);
      const A = [];
      for (let i = 0; i < m; i++) {
        A.push(new Float64Array(m));
        for (let k = 0; k <= i; k++) {
          let s = 0;
          const [a, b] = J[i].size < J[k].size ? [J[i], J[k]] : [J[k], J[i]];
          for (const [j, v] of a) { const w = b.get(j); if (w !== undefined) s += v * w; }
          A[i][k] = s;
          if (k < i) A[k][i] = s;
        }
      }
      let improved = false;
      for (let tries = 0; tries < 10; tries++) {
        const M = A.map((row, i) => { const c = Float64Array.from(row); c[i] += mu * (1 + row[i]); return c; });
        const y = gaussSolve(M, r.map(v => -v));
        if (!y) { mu *= 10; continue; }
        const dx = new Float64Array(x.length);
        J.forEach((row, i) => { for (const [j, v] of row) dx[j] += v * y[i]; });
        // the full step, then shorter steps along it (the residuals are nonlinear in the arc angles)
        for (const alpha of [1, 0.5, 0.25, 0.125]) {
          const xn = x.slice();
          for (let j = 0; j < x.length; j++) xn[j] += alpha * dx[j];
          const rn = this.r(xn), nn = Math.max(...rn.map(Math.abs));
          if (isFinite(nn) && nn < nr) {
            for (let j = 0; j < x.length; j++) x[j] = xn[j];
            r = rn; nr = nn; mu = Math.max(mu / 10, 1e-12); improved = true;
            break;
          }
        }
        if (improved) break;
        mu *= 10;
      }
      if (!improved) break;
    }
    return { ok: nr <= 1e-6, x, norm: nr };
  }
  rank() {
    const x = this.x;
    const J = this.jac(x.slice());
    const n = x.length;
    const rows = J.map(row => { const a = new Float64Array(n); for (const [j, v] of row) a[j] = v; return a; });
    return matRank(rows, n);
  }
  write(x) {
    for (const [id, b] of this.base) {
      const e = entById(id);
      setEntVals(e, x.slice(b, b + this.count.get(id)));
    }
  }
}

function gaussSolve(A, b) {
  const n = b.length;
  const M = A.map((row, i) => { const r = Array.from(row); r.push(b[i]); return r; });
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let i = c + 1; i < n; i++) if (Math.abs(M[i][c]) > Math.abs(M[p][c])) p = i;
    if (Math.abs(M[p][c]) < 1e-300) return null;
    [M[c], M[p]] = [M[p], M[c]];
    for (let i = c + 1; i < n; i++) {
      const f = M[i][c] / M[c][c];
      if (f === 0) continue;
      for (let k = c; k <= n; k++) M[i][k] -= f * M[c][k];
    }
  }
  const y = new Array(n).fill(0);
  for (let i = n - 1; i >= 0; i--) {
    let s = M[i][n];
    for (let k = i + 1; k < n; k++) s -= M[i][k] * y[k];
    y[i] = s / M[i][i];
  }
  return y.every(isFinite) ? y : null;
}

function matRank(rows, n) {
  const R = rows.map(r => Float64Array.from(r));
  let rank = 0;
  let mx = 0;
  R.forEach(r => r.forEach(v => { mx = Math.max(mx, Math.abs(v)); }));
  const tol = 1e-8 * Math.max(1, mx);
  const used = new Array(R.length).fill(false);
  for (let c = 0; c < n; c++) {
    let p = -1, best = tol;
    for (let i = 0; i < R.length; i++) if (!used[i] && Math.abs(R[i][c]) > best) { best = Math.abs(R[i][c]); p = i; }
    if (p < 0) continue;
    used[p] = true; rank++;
    for (let i = 0; i < R.length; i++) {
      if (i === p || used[i]) continue;
      const f = R[i][c] / R[p][c];
      if (f === 0) continue;
      for (let k = c; k < n; k++) R[i][k] -= f * R[p][k];
    }
  }
  return rank;
}

// constraint records from driving dimensions
function dimCon(d) {
  if (!d.driving) return null;
  const v = +d.value;
  if (d.type === "linear") {
    if (d.line) return { t: "dist", a: { e: d.line, k: "p1" }, b: { e: d.line, k: "p2" }, o: d.orient, v };
    if (d.r1 && d.r2) return { t: "dist", a: d.r1, b: d.r2, o: d.orient, v };
    if (d.r1 && d.l2) return { t: "pldist", a: d.r1, l: d.l2, v };
  } else if (d.type === "diameter" || d.type === "radius") {
    return { t: "radius", e: d.ent, dia: d.type === "diameter", v };
  } else if (d.type === "angle") {
    return { t: "angle", l1: d.l1, l2: d.l2, s1: d.s1, s2: d.s2, v };
  }
  return null;
}

function buildSystem(extra) {
  const S = new System();
  for (const c of SK.doc.constraints) S.addCon(c, c.id);
  for (const d of SK.doc.dims) { const c = dimCon(d); if (c) S.addCon(c, "d:" + d.id); }
  for (const c of extra || []) S.addCon(c, c.tag || "extra");
  return S;
}

// solve and write back; returns true when all constraints are satisfied
function solveAll(extra) {
  const S = buildSystem(extra);
  if (!S.res.length) return true;
  const res = S.solve();
  if (res.ok || extra) S.write(res.x);
  return res.ok;
}

function updateDof() {
  let total = 0;
  for (const e of ents()) if (isSolver(e)) total += entVals(e).length;
  const S = buildSystem();
  const rank = S.res.length ? S.rank() : 0;
  SK.dof = total + S.naux - rank;
  const n = SK.doc.constraints.length + SK.doc.dims.filter(d => d.driving).length;
  $("#sk-dof").textContent = n ? (SK.dof === 0 ? "Fully constrained" : "DOF " + SK.dof) : "";
}

// ------------------------------------------------------------------ dimensions and notes

function lineInter(l1, l2) {
  const a = entById(l1), b = entById(l2);
  if (!a || !b || a.t !== "line" || b.t !== "line") return null;
  const p = intersect({ s: "seg", a: [a.x1, a.y1], b: [a.x2, a.y2] }, { s: "seg", a: [b.x1, b.y1], b: [b.x2, b.y2] }, true, true);
  return p.length ? p[0] : null;
}
function lineVec(id) { const e = entById(id); return e && e.t === "line" ? [e.x2 - e.x1, e.y2 - e.y1] : null; }
function farEnd(id, c, u) {
  const e = entById(id);
  const a = [e.x1, e.y1], b = [e.x2, e.y2];
  return dot(sub(a, c), u) > dot(sub(b, c), u) ? a : b;
}

// dimension record -> annotation in the annotate.py schema (model coordinates), or null
function resolveDim(d) {
  const base = { id: d.id, type: d.type, text: d.text || "", prefix: d.prefix || "", tol: d.tol || null };
  if (d.type === "note") {
    return Object.assign(base, { pos: d.pos, anchor: d.anchor || null });
  }
  if (d.type === "linear") {
    let p1, p2;
    if (d.line) { p1 = getPt({ e: d.line, k: "p1" }); p2 = getPt({ e: d.line, k: "p2" }); }
    else if (d.r1 && d.r2) { p1 = getPt(d.r1); p2 = getPt(d.r2); }
    else if (d.r1 && d.l2) {
      p1 = getPt(d.r1);
      const l = entById(d.l2);
      if (!p1 || !l) return null;
      const a = [l.x1, l.y1], u = unit([l.x2 - l.x1, l.y2 - l.y1]);
      p2 = add(a, mul(u, dot(sub(p1, a), u)));
    }
    if (!p1 || !p2) return null;
    const m = mul(add(p1, p2), 0.5);
    return Object.assign(base, { p1, p2, orient: d.orient || "a", pos: add(m, d.off || [0, 0]),
                                  text_free: !!d.text_free, dia: !!d.dia });
  }
  if (d.type === "diameter" || d.type === "radius") {
    const e = entById(d.ent);
    if (!e || (e.t !== "circle" && e.t !== "arc")) return null;
    return Object.assign(base, { c: [e.cx, e.cy], r: e.r, pos: add([e.cx, e.cy], d.off || [e.r, e.r]) });
  }
  if (d.type === "angle") {
    const c = lineInter(d.l1, d.l2);
    const v1 = lineVec(d.l1), v2 = lineVec(d.l2);
    if (!c || !v1 || !v2) return null;
    const u1 = unit(mul(v1, d.s1)), u2 = unit(mul(v2, d.s2));
    const bis = unit(add(u1, u2));
    const b = len(add(u1, u2)) < 1e-9 ? [-u1[1], u1[0]] : bis;
    return Object.assign(base, { c, p1: farEnd(d.l1, c, u1), p2: farEnd(d.l2, c, u2), pos: add(c, mul(b, d.rad || 10)) });
  }
  return null;
}

function measure(a) {
  if (!a) return null;
  if (a.type === "linear") {
    const o = a.orient;
    if (o === "h") return Math.abs(a.p2[0] - a.p1[0]);
    if (o === "v") return Math.abs(a.p2[1] - a.p1[1]);
    return dist(a.p1, a.p2);
  }
  if (a.type === "diameter") return 2 * a.r;
  if (a.type === "radius") return a.r;
  if (a.type === "angle") return r2d(angleSector(a.c, a.p1, a.p2, a.pos)[1]);
  return null;
}

function angleSector(c, p1, p2, q) {
  const t1 = Math.atan2(p1[1] - c[1], p1[0] - c[0]), t2 = Math.atan2(p2[1] - c[1], p2[0] - c[0]);
  const tq = Math.atan2(q[1] - c[1], q[0] - c[0]);
  const tw = 2 * Math.PI, md = (v) => ((v % tw) + tw) % tw;
  let best = null;
  for (const a of [t1, t1 + Math.PI]) for (const b of [t2, t2 + Math.PI]) for (const [s0, s1] of [[a, b], [b, a]]) {
    const span = md(s1 - s0);
    if (span < 1e-9 || span > Math.PI + 1e-9) continue;
    if (md(tq - s0) <= span + 1e-9 && (!best || span < best[1])) best = [md(s0), span];
  }
  return best || [md(t1), md(t2 - t1)];
}

function fitDev(size, cls) {
  const key = fmtN(size, 4) + "|" + cls;
  if (key in SK.fitCache) return SK.fitCache[key];
  SK.fitCache[key] = null;
  postJSON("/api/fit", { size, cls }).then(r => r.json())
    .then(j => { SK.fitCache[key] = [j.upper, j.lower]; redraw(); })
    .catch(() => { SK.fitCache[key] = ["?", "?"]; redraw(); });
  return null;
}
// deviation text on the drawing from a deviation in mm (µm, or inch with the inch option); app.js devText
function fmtDev(v, lower) { return typeof v === "number" ? devText(v, lower) : v; }

// [main text, upper, lower]; mirrors annotate.label
function dimLabel(a) {
  const v = measure(a);
  if (a.type === "note") return [a.text || "", null, null];
  let main;
  if (a.type === "angle") main = a.text || ((a.prefix || "") + fmtN(v, 2) + "°");
  else {
    const sym = a.type === "diameter" || a.dia ? "Ø" : a.type === "radius" ? "R" : "";
    main = a.text || ((a.prefix || "") + sym + dimLenText(v, x => fmtN(x)));
  }
  const tol = a.tol || {};
  let up = null, lo = null;
  if (tol.mode === "fit" && tol.fit) {
    main += " " + tol.fit;
    if (tol.show_dev !== false) { const f = fitDev(v, tol.fit); if (f) { up = fmtDev(f[0]); lo = fmtDev(f[1], true); } }
  } else if (tol.mode === "sym") {
    main += " ±" + symText(+tol.plus || 0);
  } else if (tol.mode === "dev") {
    up = fmtDev(+tol.plus || 0); lo = fmtDev(+tol.minus || 0, true);
  }
  return [main, up, lo];
}

// dimension graphics in paper mm (model * scale); port of annotate.py
const ARROW_L = 3.0, ARROW_W = 0.5, EXT_GAP = 1.0, EXT_OVER = 2.0, TEXT_GAP = 1.0;

function readingAngle(u) {
  let a = r2d(Math.atan2(u[1], u[0]));
  while (a <= -90 + 1e-9) a += 180;
  while (a > 90 + 1e-9) a -= 180;
  return a;
}
function arrow(tip, d) {
  const b = [tip[0] - d[0] * ARROW_L, tip[1] - d[1] * ARROW_L], p = [-d[1] * ARROW_W, d[0] * ARROW_W];
  return { t: "solid", pts: [tip, add(b, p), sub(b, p)] };
}
function textBlock(base, ang, h, main, up, lo, anchor) {
  const a = d2r(ang), u = [Math.cos(a), Math.sin(a)], n = [-u[1], u[0]];
  if (up === null || up === undefined) return [{ t: "text", p: base, h, s: main, anchor, ang }];
  const wm = textW(main, h), hd = h * 0.7, wd = Math.max(textW(up, hd), textW(lo, hd));
  const total = wm + 0.8 + wd;
  const s0 = anchor === "middle" ? -total / 2 : anchor === "end" ? -total : 0;
  const p = add(base, mul(u, s0)), q = add(p, mul(u, wm + 0.8));
  return [{ t: "text", p, h, s: main, anchor: "start", ang },
          { t: "text", p: add(q, mul(n, hd * 1.4)), h: hd, s: up, anchor: "start", ang },     // ISO 129-1: lower deviation
          { t: "text", p: q, h: hd, s: lo, anchor: "start", ang }];                            // on the baseline
}

function dimGraphics(a, k, h) {          // k: model -> paper factor
  const M = p => [p[0] * k, p[1] * k];
  const out = [];
  const L = (p, q) => out.push({ t: "line", a: p, b: q });
  const [main, up, lo] = dimLabel(a);
  if (a.type === "linear") {
    const P1 = M(a.p1), P2 = M(a.p2), Q = M(a.pos);
    const u = a.orient === "h" ? [1, 0] : a.orient === "v" ? [0, 1] : unit(sub(P2, P1));
    const n = [-u[1], u[0]];
    const foot = P => { const d = dot(sub(Q, P), n); return [add(P, mul(n, d)), d]; };
    const [A, dA] = foot(P1), [B, dB] = foot(P2);
    for (const [P, F, d] of [[P1, A, dA], [P2, B, dB]]) {
      if (Math.abs(d) > EXT_GAP) { const sg = d > 0 ? 1 : -1; L(add(P, mul(n, sg * EXT_GAP)), add(F, mul(n, sg * EXT_OVER))); }
    }
    const Ld = dist(A, B), dab = unit(sub(B, A));
    const tw = textW(main, h) + (up ? 0.8 + Math.max(textW(up, h * 0.7), textW(lo, h * 0.7)) : 0);
    let t = a.text_free ? dot(sub(Q, A), dab) : Ld / 2;
    if (Ld >= 2 * ARROW_L + 1) { L(A, B); out.push(arrow(A, mul(dab, -1)), arrow(B, dab)); }
    else { const e = ARROW_L + 3; L(sub(A, mul(dab, e)), add(B, mul(dab, e))); out.push(arrow(A, dab), arrow(B, mul(dab, -1))); }
    if (t > Ld) L(B, add(A, mul(dab, t + tw / 2 + 1)));
    else if (t < 0) L(A, add(A, mul(dab, t - tw / 2 - 1)));
    const ang = readingAngle(u), ar = d2r(ang), upd = [-Math.sin(ar), Math.cos(ar)];
    const base = add(add(A, mul(dab, t)), mul(upd, TEXT_GAP));
    out.push(...textBlock(base, ang, h, main, up, lo, "middle"));
  } else if (a.type === "diameter" || a.type === "radius") {
    const C = M(a.c), r = a.r * k, Q = M(a.pos);
    const d = unit(sub(Q, C)), N = add(C, mul(d, r)), F = sub(C, mul(d, r));
    let outside = dist(Q, C) > r + 0.5;
    if (a.type === "diameter") {
      if (2 * r >= 2 * ARROW_L + 2) { L(F, outside ? Q : N); out.push(arrow(F, mul(d, -1)), arrow(N, d)); }
      else { L(N, Q); out.push(arrow(N, mul(d, -1))); L(F, sub(F, mul(d, ARROW_L + 3))); out.push(arrow(F, d)); outside = true; }
    } else { L(C, outside ? Q : N); out.push(arrow(N, d)); }
    if (outside) {
      const sg = d[0] >= 0 ? 1 : -1;
      const w = textW(main, h) + (up ? 0.8 + textW(up, h * 0.7) : 0) + 1;
      const S = [Q[0] + sg * w, Q[1]];
      L(Q, S);
      out.push(...textBlock([Math.min(Q[0], S[0]) + 0.5, Q[1] + TEXT_GAP], 0, h, main, up, lo, "start"));
    } else out.push(...textBlock([Q[0], Q[1] + TEXT_GAP], 0, h, main, up, lo, "middle"));
  } else if (a.type === "angle") {
    const C = M(a.c), P1 = M(a.p1), P2 = M(a.p2), Q = M(a.pos);
    const [s0, span] = angleSector(C, P1, P2, Q);
    const R = dist(Q, C), ends = [s0, s0 + span];
    for (const P of [P1, P2]) {
      const tp = Math.atan2(P[1] - C[1], P[0] - C[0]), dp = dist(P, C);
      for (const e of ends) {
        let df = (tp - e) % (2 * Math.PI); if (df > Math.PI) df -= 2 * Math.PI; if (df < -Math.PI) df += 2 * Math.PI;
        if (Math.abs(df) < 1e-6 && R > dp + EXT_GAP) {
          const u = [Math.cos(e), Math.sin(e)];
          L(add(C, mul(u, dp + EXT_GAP)), add(C, mul(u, R + EXT_OVER)));
        }
      }
    }
    out.push({ t: "arc", c: C, r: R, a0: r2d(s0), a1: r2d(s0 + span) });
    for (const [e, sg] of [[ends[0], -1], [ends[1], 1]]) {
      let tg = [-Math.sin(e) * sg, Math.cos(e) * sg];
      if (R * span < 2 * ARROW_L + 1) tg = mul(tg, -1);
      out.push(arrow([C[0] + R * Math.cos(e), C[1] + R * Math.sin(e)], tg));
    }
    const mid = s0 + span / 2, u = [-Math.sin(mid), Math.cos(mid)];
    const ang = readingAngle(u), ar = d2r(ang), upd = [-Math.sin(ar), Math.cos(ar)];
    const rp = [C[0] + R * Math.cos(mid), C[1] + R * Math.sin(mid)];
    let base = add(rp, mul(upd, TEXT_GAP));
    if (upd[0] * Math.cos(mid) + upd[1] * Math.sin(mid) < 0) base = sub(rp, mul(upd, TEXT_GAP + h));
    out.push(...textBlock(base, ang, h, main, up, lo, "middle"));
  } else if (a.type === "note") {
    const raw = String(a.text || "").replace(/\r\n/g, "\n").replace(/\\n/g, "\n").replace(/ \/n /g, "\n").replace(/ \/n/g, "\n").replace(/\/n /g, "\n");
    const lines = raw.split("\n"), P = M(a.pos);
    lines.forEach((s, i) => { if (s) out.push({ t: "text", p: [P[0], P[1] - i * h * 1.6], h, s, anchor: "start", ang: 0 }); });
    if (a.anchor) {
      const A = M(a.anchor), w = Math.max(...lines.map(s => textW(s, h)), h);
      const left = A[0] <= P[0] + w / 2;
      const S = left ? [P[0] - 1, P[1] + h * 0.4] : [P[0] + w + 1, P[1] + h * 0.4];
      L(A, S); out.push(arrow(A, unit(sub(A, S))));
    }
  }
  return out;
}

// ------------------------------------------------------------------ view and rendering

function S(p) { return [SK.view.ox + SK.view.s * p[0], SK.view.oy - SK.view.s * p[1]]; }
function Minv(sx, sy) { return [(sx - SK.view.ox) / SK.view.s, (SK.view.oy - sy) / SK.view.s]; }
function sketchScale() { return SK.doc ? (+SK.doc.scale || 1) : 1; }
function dimH() { return (state.cfg && state.cfg.dim_text_height_mm) || 3.5; }
/** Model-to-paper factor for the dimensions: the sketch scale on a sheet; without a sheet (feature sketches,
 *  extents) the factor keeps the dimension text at DIM_PX pixels on screen whatever the zoom and the part size. */
const DIM_PX = 12;
function dimK() {
  if (sheetOn()) return sketchScale();
  return dimH() * SK.view.s / DIM_PX;
}
const N = v => v.toFixed(2);

function dispColor(c) {
  if (!c || !/^#[0-9a-f]{6}$/i.test(c)) return "#000000";
  const r = parseInt(c.slice(1, 3), 16), g = parseInt(c.slice(3, 5), 16), b = parseInt(c.slice(5, 7), 16);
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  if (lum < 0.75) return c;
  const f = 0.55;
  return "#" + [r, g, b].map(v => Math.round(v * f).toString(16).padStart(2, "0")).join("");
}

function ltClass(name) {
  const n = String(name || "").toUpperCase();
  if (!n || n === "CONTINUOUS" || n === "BYLAYER" || n === "BYBLOCK") return "continuous";
  const lt = (SK.doc.linetypes || []).find(l => l.name.toUpperCase() === n);
  if (lt && lt.cls) return lt.cls;
  if (/CENTER|CHAIN|DASHDOT|PHANTOM|DIVIDE|BORDER/.test(n)) return "chain";
  if (/DOT/.test(n)) return "dot";
  if (/HIDDEN|DASH/.test(n)) return "hidden";
  return "continuous";
}
function entStyle(e) {
  const lay = layerOf(e) || {};
  let lt = e.linetype || lay.linetype || "Continuous";
  if (/^bylayer$/i.test(lt)) lt = lay.linetype || "Continuous";
  const cls = ltClass(lt);
  const lw = (lay.lineweight > 0 ? lay.lineweight : (cls === "continuous" ? 0.5 : 0.25));
  const dash = { continuous: "", hidden: "6 3", chain: "14 3 2 3", dot: "1.5 3" }[cls];
  return { color: dispColor(e.color || lay.color), w: lw >= 0.4 ? 1.7 : 1.0, dash };
}

function entSvg(e, stroke, w, dash, extra) {
  const st = `stroke="${stroke}" stroke-width="${w}"${dash ? ` stroke-dasharray="${dash}"` : ""}${extra || ""}`;
  switch (e.t) {
    case "line": { const a = S([e.x1, e.y1]), b = S([e.x2, e.y2]); return `<line x1="${N(a[0])}" y1="${N(a[1])}" x2="${N(b[0])}" y2="${N(b[1])}" ${st}/>`; }
    case "circle": { const c = S([e.cx, e.cy]); return `<circle cx="${N(c[0])}" cy="${N(c[1])}" r="${N(e.r * SK.view.s)}" fill="none" ${st}/>`; }
    case "arc": {
      const a = S(arcPt(e, e.a0)), b = S(arcPt(e, e.a1)), sp = arcSpan(e), r = e.r * SK.view.s;
      if (sp >= 359.999) { const c = S([e.cx, e.cy]); return `<circle cx="${N(c[0])}" cy="${N(c[1])}" r="${N(r)}" fill="none" ${st}/>`; }
      return `<path d="M${N(a[0])} ${N(a[1])}A${N(r)} ${N(r)} 0 ${sp > 180 ? 1 : 0} 0 ${N(b[0])} ${N(b[1])}" fill="none" ${st}/>`;
    }
    case "point": { const p = S([e.x, e.y]); return `<path d="M${N(p[0] - 4)} ${N(p[1])}h8M${N(p[0])} ${N(p[1] - 4)}v8" ${st}/>`; }
    case "ellipse": {
      const c = S([e.cx, e.cy]), rx = e.rx * SK.view.s, ry = e.ry * SK.view.s, rot = -(e.rot || 0);
      if (ellClosed(e)) return `<ellipse cx="${N(c[0])}" cy="${N(c[1])}" rx="${N(rx)}" ry="${N(ry)}" transform="rotate(${N(rot)} ${N(c[0])} ${N(c[1])})" fill="none" ${st}/>`;
      const a = S(ellPt(e, e.a0)), b = S(ellPt(e, e.a0 + ellSpan(e))), sp = ellSpan(e);
      return `<path d="M${N(a[0])} ${N(a[1])}A${N(rx)} ${N(ry)} ${N(rot)} ${sp > 180 ? 1 : 0} 0 ${N(b[0])} ${N(b[1])}" fill="none" ${st}/>`;
    }
    case "spline": {
      const pts = splinePolyE(e, 16).map(p => S(p).map(N).join(",")).join(" ");
      return `<polyline points="${pts}" fill="none" ${st}/>`;
    }
    case "conic": {
      const pts = conicPolyE(e, 64).map(p => S(p).map(N).join(",")).join(" ");
      return `<polyline points="${pts}" fill="none" ${st}/>`;
    }
    case "poly": {
      const pts = e.pts.map(p => S(p).map(N).join(",")).join(" ");
      if (e.fill) return `<polygon points="${pts}" fill="${stroke}" ${st}/>`;
      return `<${e.closed ? "polygon" : "polyline"} points="${pts}" fill="none" ${st}/>`;
    }
    case "text": {
      const p = S([e.x, e.y]), fs = e.h * SK.view.s / 0.72;
      const lines = String(e.text).split("\n");
      const anc = e.anchor || "start";
      const rot = e.rot ? ` transform="rotate(${N(-e.rot)} ${N(p[0])} ${N(p[1])})"` : "";
      const tsp = lines.map((s, i) => `<tspan x="${N(p[0])}" y="${N(p[1] + i * 1.6 * e.h * SK.view.s)}">${esc(s)}</tspan>`).join("");
      return `<text font-size="${N(fs)}" text-anchor="${anc}" fill="${stroke}" stroke="none"${rot}>${tsp}</text>`;
    }
  }
  return "";
}

function primSvg(g, color, k) {        // dimension primitive (paper mm) -> svg
  const P = p => S([p[0] / k, p[1] / k]);
  const sc = SK.view.s / k;
  if (g.t === "line") { const a = P(g.a), b = P(g.b); return `<line x1="${N(a[0])}" y1="${N(a[1])}" x2="${N(b[0])}" y2="${N(b[1])}" stroke="${color}" stroke-width="1"/>`; }
  if (g.t === "solid") return `<polygon points="${g.pts.map(p => P(p).map(N).join(",")).join(" ")}" fill="${color}"/>`;
  if (g.t === "arc") {
    const a = P([g.c[0] + g.r * Math.cos(d2r(g.a0)), g.c[1] + g.r * Math.sin(d2r(g.a0))]);
    const b = P([g.c[0] + g.r * Math.cos(d2r(g.a1)), g.c[1] + g.r * Math.sin(d2r(g.a1))]);
    const r = g.r * sc, sp = n360(g.a1 - g.a0);
    return `<path d="M${N(a[0])} ${N(a[1])}A${N(r)} ${N(r)} 0 ${sp > 180 ? 1 : 0} 0 ${N(b[0])} ${N(b[1])}" fill="none" stroke="${color}" stroke-width="1"/>`;
  }
  if (g.t === "text") {
    const p = P(g.p), fs = g.h * sc / 0.72;
    const rot = g.ang ? ` transform="rotate(${N(-g.ang)} ${N(p[0])} ${N(p[1])})"` : "";
    return `<text x="${N(p[0])}" y="${N(p[1])}" font-size="${N(fs)}" text-anchor="${g.anchor}" fill="${color}"${rot}>${esc(g.s)}</text>`;
  }
  return "";
}

const GLYPH = { horizontal: "H", vertical: "V", parallel: "∥", perpendicular: "⊥", tangent: "T", equal: "=",
                pointon: "On", midpoint: "M", concentric: "◎", symmetric: "S", fix: "F" };

function entMid(id) {
  const e = entById(id);
  if (!e) return null;
  if (e.t === "line") return [(e.x1 + e.x2) / 2, (e.y1 + e.y2) / 2];
  if (e.t === "circle") return [e.cx, e.cy + e.r];
  if (e.t === "arc") return arcPt(e, e.a0 + arcSpan(e) / 2);
  if (e.t === "point") return [e.x, e.y];
  return null;
}
function conAnchors(c) {
  switch (c.t) {
    case "coincident": return [getPt(c.a)];
    case "horizontal": case "vertical": return [c.l ? entMid(c.l) : (getPt(c.a) && getPt(c.b) ? mul(add(getPt(c.a), getPt(c.b)), 0.5) : null)];
    case "parallel": case "perpendicular": return [entMid(c.l1), entMid(c.l2)];
    case "tangent": case "equal": return [entMid(c.e1), entMid(c.e2)];
    case "pointon": case "midpoint": return [getPt(c.a)];
    case "concentric": return [getPt({ e: c.e1, k: "c" })];
    case "symmetric": return [getPt(c.a) && getPt(c.b) ? mul(add(getPt(c.a), getPt(c.b)), 0.5) : null];
    case "fix": return [c.a ? getPt(c.a) : entMid(c.e)];
  }
  return [];
}

// ------------------------------------------------------------------ sheet (frame and title block)
// doc.sheet = {page: "extents" | "A4".."A0", title_block, origin: [x, y]}; paper mm = (model - origin) * scale

function sheetOn() { return SK.doc && SK.doc.sheet && SK.doc.sheet.page !== "extents"; }

function sheetKey() {
  const sh = SK.doc.sheet;
  let f = "";
  try { f = JSON.stringify(readFields()); } catch (e) { f = ""; }
  return [sh.page, sh.title_block, sketchScale(), SK.doc.name, f].join("|");
}

let sheetBusy = null;
function ensureSheet() {
  const g = $("#sk-sheet");
  $("#sk-canvas").classList.toggle("paper", !!sheetOn());
  if (!sheetOn()) { if (g) g.innerHTML = ""; SK.sheetData = null; return; }
  if (SK.hostSheet) {                       // sketch on a drawing: the drawing is the sheet
    if (!SK.sheetData || SK.sheetData.key !== "host") {
      SK.sheetData = Object.assign({ key: "host" }, SK.hostSheet);
      $("#sk-sheet").innerHTML = '<g id="sk-sheet-t">' + SK.hostSheet.inner + "</g>";
    }
    placeSheet();
    return;
  }
  const key = sheetKey();
  if (SK.sheetData && SK.sheetData.key === key) { placeSheet(); return; }
  if (sheetBusy === key) return;
  sheetBusy = key;
  postJSON("/api/sketch/sheet", { sketch: { name: SK.doc.name, scale: sketchScale() }, sheet: SK.doc.sheet.page,
                                  title_block: SK.doc.sheet.title_block, fields: readFields() })
    .then(r => r.json())
    .then(j => {
      sheetBusy = null;
      const inner = j.svg.replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "");
      SK.sheetData = { key, size: j.size, area: j.area, inner };
      $("#sk-sheet").innerHTML = '<g id="sk-sheet-t">' + inner + "</g>";
      const first = !SK.sheetFitted;
      if (!SK.doc.sheet.origin) centreOnSheet(true);
      placeSheet();
      if (first) { SK.sheetFitted = true; fit(); } else redraw();
    })
    .catch(e => { sheetBusy = null; msg("Sheet: " + e.message, true); });
}

function placeSheet() {
  const t = document.getElementById("sk-sheet-t");
  if (!t || !SK.sheetData) return;
  const k = SK.view.s / sketchScale(), H = SK.sheetData.size[1], o = SK.doc.sheet.origin || [0, 0];
  t.setAttribute("transform", `matrix(${k} 0 0 ${k} ${SK.view.ox + SK.view.s * o[0]} ${SK.view.oy - SK.view.s * o[1] - k * H})`);
}

// origin so that the drawing extents are centred in the drawing area of the sheet
function centreOnSheet(silent) {
  if (!SK.sheetData) return;
  const b = extents(false);
  const a = SK.sheetData.area, sc = sketchScale();
  const cx = b ? (b[0] + b[2]) / 2 : 0, cy = b ? (b[1] + b[3]) / 2 : 0;
  if (!b) { SK.doc.sheet.origin = [0, 0]; }
  else SK.doc.sheet.origin = [cx - (a[0] + a[2]) / 2 / sc, cy - (a[1] + a[3]) / 2 / sc];
  if (!silent) { SK.dirty = true; placeSheet(); fit(); msg("Drawing centred on the sheet"); }
}

function extents(withDims) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const e of visibleEnts()) {
    if (e.axis) continue;
    const b = bbox(e);
    if (!isFinite(b[0])) continue;
    x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]); x1 = Math.max(x1, b[2]); y1 = Math.max(y1, b[3]);
  }
  if (withDims !== false) for (const d of SK.doc.dims) { const a = resolveDim(d); if (a) { x0 = Math.min(x0, a.pos[0]); x1 = Math.max(x1, a.pos[0]); y0 = Math.min(y0, a.pos[1]); y1 = Math.max(y1, a.pos[1]); } }
  return isFinite(x0) ? [x0, y0, x1, y1] : null;
}

function ensureSvg() {
  const box = $("#sk-canvas");
  let svg = box.querySelector("svg");
  if (!svg) {
    box.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg"><g id="sk-sheet"></g><g id="sk-geo" stroke-linecap="round" font-family="Arial, Helvetica, sans-serif"></g><g id="sk-ov" font-family="Arial, Helvetica, sans-serif"></g></svg>';
    svg = box.querySelector("svg");
    bindCanvas(svg);
  }
  return svg;
}

function redraw() {
  if (!SK.doc) return;
  ensureSvg();
  reindex();
  const W = $("#sk-canvas").clientWidth, H = $("#sk-canvas").clientHeight;
  const vx0 = Minv(0, H), vx1 = Minv(W, 0);
  const vb = [vx0[0], vx0[1], vx1[0], vx1[1]];
  const out = [];
  const selE = new Set(), selP = new Set();
  for (const s of SK.sel) { const q = parseSel(s); if (q.kind === "e") selE.add(q.id); if (q.kind === "p") selP.add(q.id + ":" + q.k); }
  // coordinate systems of a feature sketch: the sketch axes at the sketch origin, the base (part) coordinate
  // system projected onto the sketch plane when it differs
  const hasAxes = axisEnts().length > 0;
  if ($("#sk-axes")) $("#sk-axes").classList.toggle("active", hasAxes);
  if (SK.partEdit && !SK.partEdit.drawing) {
    const L = 36 / SK.view.s;
    const o = S([0, 0]), px = S([L, 0]), py = S([0, L]);
    if (!hasAxes) {
      out.push(`<line x1="${N(o[0])}" y1="${N(o[1])}" x2="${N(px[0])}" y2="${N(px[1])}" stroke="#d32f2f" stroke-width="1.5"/><text x="${N(px[0] + 4)}" y="${N(px[1] + 4)}" font-size="11" fill="#d32f2f">x</text>`);
      out.push(`<line x1="${N(o[0])}" y1="${N(o[1])}" x2="${N(py[0])}" y2="${N(py[1])}" stroke="#2e7d32" stroke-width="1.5"/><text x="${N(py[0] + 4)}" y="${N(py[1] - 4)}" font-size="11" fill="#2e7d32">y</text>`);
      out.push(`<circle cx="${N(o[0])}" cy="${N(o[1])}" r="3" fill="#fff" stroke="#1d2125"/>`);
    }
    const g = SK.frameRef;
    if (g) {
      const go = S(g.o);
      const cols = { x: "#d32f2f", y: "#2e7d32", z: "#1565c0" };
      for (const k of ["x", "y", "z"]) {
        const d = g[k];
        const ln = Math.hypot(d[0], d[1]);
        if (ln < 1e-6) continue;
        const e = S([g.o[0] + d[0] / ln * L * 1.8, g.o[1] + d[1] / ln * L * 1.8]);
        out.push(`<line x1="${N(go[0])}" y1="${N(go[1])}" x2="${N(e[0])}" y2="${N(e[1])}" stroke="${cols[k]}" stroke-width="1" stroke-dasharray="4 3" stroke-opacity="0.8"/><text x="${N(e[0] + 3)}" y="${N(e[1] - 3)}" font-size="11" fill="${cols[k]}" fill-opacity="0.9">${k.toUpperCase()}</text>`);
      }
      out.push(`<rect x="${N(go[0] - 3)}" y="${N(go[1] - 3)}" width="6" height="6" fill="none" stroke="#1d2125" stroke-dasharray="2 1"/>`);
    }
  }
  // reference geometry (section of the part with the sketch plane)
  for (const e of SK.refs || []) {
    if (!SK.showProj && (e.kind === "proj" || e.kind === "hidden")) continue;
    if (e.kind === "proj") out.push(entSvg(e, "#9aa3b0", 1.0, ""));
    else if (e.kind === "hidden") out.push(entSvg(e, "#b8bfc9", 0.9, "1 2.5"));
    else if (e.kind === "axis") out.push(entSvg(e, "#6a3fa0", 1.0, "10 3 2 3"));
    else if (e.kind === "datum") { const q = S([e.x, e.y]); out.push(`<circle cx="${N(q[0])}" cy="${N(q[1])}" r="3.5" fill="none" stroke="#6a3fa0" stroke-width="1.4"/><path d="M${N(q[0] - 6)} ${N(q[1])} H${N(q[0] + 6)} M${N(q[0])} ${N(q[1] - 6)} V${N(q[1] + 6)}" stroke="#6a3fa0" stroke-width="1"/>`); }
    else out.push(entSvg(e, "#6b7480", 1.2, "2 3"));
  }
  // geometry
  for (const e of ents()) {
    if (!layerOn(e)) continue;
    if (e.axis) { out.push(axisSvg(e, vb, selE.has(e.id))); continue; }
    const bb = bbox(e);
    if (!bboxOverlap(bb, vb, 0)) continue;
    const st = entStyle(e);
    if (e.included && e.constr) out.push(entSvg(e, "#0b7a75", 1.2, "6 3"));
    else if (e.constr) out.push(entSvg(e, "#2f74d0", 1, "5 4"));
    else if (e.included) out.push(entSvg(e, "#0b7a75", 1.6, ""));
    else out.push(entSvg(e, st.color, st.w, st.dash));
    if (selE.has(e.id)) out.push(entSvg(e, "#e8590c", 3, "", ' stroke-opacity="0.85"'));
  }
  // grips of selected entities and selected points
  for (const e of ents()) {
    if (!selE.has(e.id) || e.t === "text") continue;
    for (const [k, p] of grips(e)) { const q = S(p); out.push(`<rect x="${N(q[0] - 3)}" y="${N(q[1] - 3)}" width="6" height="6" fill="#fff" stroke="#e8590c"/>`); }
  }
  for (const key of selP) {
    const [id, k] = key.split(":");
    const p = getPt({ e: id, k });
    if (p) { const q = S(p); out.push(`<rect x="${N(q[0] - 4)}" y="${N(q[1] - 4)}" width="8" height="8" fill="#e8590c"/>`); }
  }
  // dimensions
  SK.dimHits = [];
  const k = dimK(), h = dimH();
  for (const d of SK.doc.dims) {
    const a = resolveDim(d);
    if (!a) continue;
    const sel = SK.sel.has("d:" + d.id);
    const color = sel ? "#e8590c" : d.driving ? "#0b7a3b" : "#1d2125";
    const gs = dimGraphics(a, k, h);
    out.push(`<g data-dim="${esc(d.id)}">` + gs.map(g => primSvg(g, color, k)).join("") + "</g>");
    SK.dimHits.push({ id: d.id, gs, k });
  }
  // constraint glyphs
  SK.glyphs = [];
  if ($("#sk-showcon").checked) {
    const stack = new Map();
    for (const c of SK.doc.constraints) {
      if (c.t === "fix" && entById(c.e) && entById(c.e).axis) continue;
      for (const p of conAnchors(c)) {
        if (!p) continue;
        const q = S(p);
        const key = Math.round(q[0]) + "," + Math.round(q[1]);
        const n = stack.get(key) || 0; stack.set(key, n + 1);
        const sel = SK.sel.has("c:" + c.id);
        if (c.t === "coincident") {
          out.push(`<circle cx="${N(q[0])}" cy="${N(q[1])}" r="3.2" fill="${sel ? "#e8590c" : "#0b7a3b"}"/>`);
          SK.glyphs.push({ id: c.id, x: q[0] - 4, y: q[1] - 4, w: 8, h: 8 });
          continue;
        }
        const gx = q[0] + 6 + n * 15, gy = q[1] - 18;
        out.push(`<rect x="${N(gx)}" y="${N(gy)}" width="14" height="13" rx="2" fill="${sel ? "#e8590c" : "#e6f2ea"}" stroke="#0b7a3b" stroke-width="0.8"/>` +
                 `<text x="${N(gx + 7)}" y="${N(gy + 10)}" font-size="${GLYPH[c.t].length > 1 ? 7.5 : 10}" text-anchor="middle" fill="${sel ? "#fff" : "#0b7a3b"}">${GLYPH[c.t]}</text>`);
        SK.glyphs.push({ id: c.id, x: gx, y: gy, w: 14, h: 13 });
      }
    }
  }
  $("#sk-geo").innerHTML = out.join("");
  ensureSheet();
  overlay();
}

// ------------------------------------------------------------------ picking and snapping

function visibleEnts() { return ents().filter(layerOn); }

function entityAt(p, filter) {
  // the sketch axes are picked only when no other entity is within the tolerance
  const tol = HIT_PX / SK.view.s;
  let best = null, bd = tol, bestAxis = null, bdAxis = tol;
  for (const e of visibleEnts()) {
    if (filter && !filter(e)) continue;
    const d = entDist(e, p);
    if (e.axis) { if (d <= bdAxis) { bdAxis = d; bestAxis = e; } continue; }
    if (d <= bd) { bd = d; best = e; }
  }
  return best || bestAxis;
}

function gripAt(p, filter) {
  const tol = SNAP_PX / SK.view.s;
  let best = null, bd = tol;
  for (const e of visibleEnts()) {
    if (filter && !filter(e)) continue;
    if (e.t === "text") continue;
    for (const [k, q] of grips(e)) {
      const d = dist(p, q);
      if (d < bd - 1e-12) { bd = d; best = { e: e.id, k, p: q }; }
    }
  }
  return best;
}

function dimAt(sx, sy) {
  for (const h of SK.dimHits) {
    for (const g of h.gs) {
      if (g.t === "line") {
        const a = S([g.a[0] / h.k, g.a[1] / h.k]), b = S([g.b[0] / h.k, g.b[1] / h.k]);
        if (segDist([sx, sy], a, b) < 4) return h.id;
      } else if (g.t === "text") {
        const p = S([g.p[0] / h.k, g.p[1] / h.k]), w = textW(g.s, g.h) * SK.view.s / h.k, hh = g.h * SK.view.s / h.k;
        const x0 = g.anchor === "middle" ? p[0] - w / 2 : g.anchor === "end" ? p[0] - w : p[0];
        const r = d2r(g.ang || 0), dx = sx - p[0], dy = sy - p[1];
        const lx = p[0] + dx * Math.cos(r) - dy * Math.sin(r), ly = p[1] + dx * Math.sin(r) + dy * Math.cos(r);
        if (lx >= x0 - 2 && lx <= x0 + w + 2 && ly <= p[1] + 3 && ly >= p[1] - hh - 3) return h.id;
      } else if (g.t === "arc") {
        const c = S([g.c[0] / h.k, g.c[1] / h.k]);
        if (Math.abs(dist([sx, sy], c) - g.r * SK.view.s / h.k) < 4) return h.id;
      }
    }
  }
  return null;
}

function glyphAt(sx, sy) {
  for (const g of SK.glyphs) if (sx >= g.x && sx <= g.x + g.w && sy >= g.y && sy <= g.y + g.h) return g.id;
  return null;
}

function snapAt(p, opts) {
  opts = opts || {};
  if (!$("#sk-snap").checked || opts.nosnap) return { p, kind: null, ref: null };
  const tol = SNAP_PX / SK.view.s;
  const near = [];
  for (const e of visibleEnts().concat(SK.refs || [])) {
    if (e.t === "text" || (opts.exclude && opts.exclude.has(e.id))) continue;
    const d = entDist(e, p);
    if (d < tol * 1.5) near.push([d, e]);
  }
  near.sort((a, b) => a[0] - b[0]);
  let best = null, bd = tol;
  let curRef = false;
  const consider = (q, kind, ref) => { const d = dist(p, q); if (d < bd) { bd = d; best = { p: q, kind, ref: curRef ? null : ref }; } };
  for (const [, e] of near) {
    curRef = !!e.isRef;
    for (const [k, q] of grips(e)) consider(q, k === "c" ? "cen" : "end", { e: e.id, k });
    if (e.t === "line") consider([(e.x1 + e.x2) / 2, (e.y1 + e.y2) / 2], "mid", { e: e.id, k: "m" });
    if (e.t === "arc") consider(arcPt(e, e.a0 + arcSpan(e) / 2), "mid", { e: e.id, k: "m" });
    if (e.t === "circle" || e.t === "arc") {
      for (const a of [0, 90, 180, 270]) if (e.t === "circle" || angOnArc(e, a)) consider(arcPt(e, a), "quad", null);
    }
  }
  curRef = false;
  const few = near.slice(0, 6).map(x => x[1]);
  for (let i = 0; i < few.length; i++) for (let j = i + 1; j < few.length; j++) {
    for (const c1 of curves(few[i])) for (const c2 of curves(few[j])) for (const q of intersect(c1, c2)) consider(q, "int", null);
  }
  if (best) return best;
  if (near.length && near[0][0] < tol) {
    const e = near[0][1];
    const q = nearestOn(e, p);
    if (q) return { p: q, kind: "on", ref: isSolver(e) && e.t !== "point" && !e.isRef ? { on: e.id } : null };
  }
  return { p, kind: null, ref: null };
}

// ortho (Shift): horizontal or vertical from the base point
function ortho(base, p, ev) {
  if (!base || !ev || !ev.shiftKey) return p;
  const d = sub(p, base);
  return Math.abs(d[0]) >= Math.abs(d[1]) ? [p[0], base[1]] : [base[0], p[1]];
}

// ------------------------------------------------------------------ overlay

function overlay() {
  const ov = $("#sk-ov");
  if (!ov) return;
  const out = [];
  const blue = "#1f77d0";
  if (SK.hover && SK.hover.kind === "e") {
    const e = entById(SK.hover.id);
    if (e) out.push(entSvg(e, blue, 2.6, "", ' stroke-opacity="0.7"'));
  }
  for (const pk of SK.pick) {
    const e = pk && pk.e && !pk.k ? entById(pk.e) : null;
    if (e) out.push(entSvg(e, "#e8590c", 3, "", ' stroke-opacity="0.8"'));
  }
  if (SK.hover && SK.hover.kind === "p") {
    const q = S(SK.hover.p);
    out.push(`<rect x="${N(q[0] - 4)}" y="${N(q[1] - 4)}" width="8" height="8" fill="none" stroke="${blue}" stroke-width="1.5"/>`);
  }
  if (SK.win && SK.mouse) {
    const a = [SK.win.sx, SK.win.sy], b = [SK.mouse.sx, SK.mouse.sy];
    const cross = b[0] < a[0];
    out.push(`<rect x="${N(Math.min(a[0], b[0]))}" y="${N(Math.min(a[1], b[1]))}" width="${N(Math.abs(b[0] - a[0]))}" height="${N(Math.abs(b[1] - a[1]))}" ` +
             `fill="${cross ? "rgba(40,160,80,0.08)" : "rgba(31,119,208,0.08)"}" stroke="${cross ? "#28a050" : blue}"${cross ? ' stroke-dasharray="5 3"' : ""}/>`);
  }
  for (const e of previewEnts()) out.push(entSvg(e, blue, 1.2, "6 3"));
  const pd = previewDim();
  if (pd) for (const g of dimGraphics(pd, dimK(), dimH())) out.push(primSvg(g, blue, dimK()));
  if (SK.snap && SK.snap.kind && SK.mouse) {
    const q = S(SK.snap.p), c = "#d0451b";
    const m = {
      end: `<rect x="${N(q[0] - 5)}" y="${N(q[1] - 5)}" width="10" height="10" fill="none" stroke="${c}" stroke-width="1.5"/>`,
      mid: `<path d="M${N(q[0])} ${N(q[1] - 6)}L${N(q[0] + 6)} ${N(q[1] + 5)}L${N(q[0] - 6)} ${N(q[1] + 5)}Z" fill="none" stroke="${c}" stroke-width="1.5"/>`,
      cen: `<circle cx="${N(q[0])}" cy="${N(q[1])}" r="6" fill="none" stroke="${c}" stroke-width="1.5"/>`,
      quad: `<path d="M${N(q[0])} ${N(q[1] - 6)}L${N(q[0] + 6)} ${N(q[1])}L${N(q[0])} ${N(q[1] + 6)}L${N(q[0] - 6)} ${N(q[1])}Z" fill="none" stroke="${c}" stroke-width="1.5"/>`,
      int: `<path d="M${N(q[0] - 5)} ${N(q[1] - 5)}L${N(q[0] + 5)} ${N(q[1] + 5)}M${N(q[0] + 5)} ${N(q[1] - 5)}L${N(q[0] - 5)} ${N(q[1] + 5)}" stroke="${c}" stroke-width="1.8"/>`,
      on: `<path d="M${N(q[0] - 5)} ${N(q[1] - 5)}L${N(q[0] + 5)} ${N(q[1] - 5)}L${N(q[0] - 5)} ${N(q[1] + 5)}L${N(q[0] + 5)} ${N(q[1] + 5)}Z" fill="none" stroke="${c}" stroke-width="1.3"/>`,
    }[SK.snap.kind];
    if (m) out.push(m);
  }
  ov.innerHTML = out.join("");
}

// ------------------------------------------------------------------ document changes

function checkpoint() {
  SK.undo.push(JSON.stringify(SK.doc));
  if (SK.undo.length > 100) SK.undo.shift();
  SK.redo = [];
}
function changed(keepSel) {
  SK.dirty = true;
  reindex();
  if (!keepSel) {
    for (const s of [...SK.sel]) {
      const q = parseSel(s);
      if ((q.kind === "e" || q.kind === "p") && !entById(q.id)) SK.sel.delete(s);
      if (q.kind === "d" && !SK.doc.dims.find(d => d.id === q.id)) SK.sel.delete(s);
      if (q.kind === "c" && !SK.doc.constraints.find(c => c.id === q.id)) SK.sel.delete(s);
    }
  }
  updateDof();
  redraw();
  showProps();
  // the first geometry drawn in an empty sketch sets the view scale
  if (SK.firstFit && ents().some(e => !e.axis && e.t !== "text")) { SK.firstFit = false; fitIfNeeded(); }
}
function undo() {
  if (!SK.undo.length) return;
  SK.redo.push(JSON.stringify(SK.doc));
  SK.doc = JSON.parse(SK.undo.pop());
  SK.sel.clear(); resetTool(); renderLayers(); changed();
}
function redoOp() {
  if (!SK.redo.length) return;
  SK.undo.push(JSON.stringify(SK.doc));
  SK.doc = JSON.parse(SK.redo.pop());
  SK.sel.clear(); resetTool(); renderLayers(); changed();
}

function conEnts(c) {
  const ids = [];
  for (const k of ["l", "l1", "l2", "e1", "e2", "e", "line", "ent"]) if (c[k]) ids.push(c[k]);
  for (const k of ["a", "b", "r1", "r2"]) if (c[k] && c[k].e) ids.push(c[k].e);
  return ids;
}
function conPts(c) { return ["a", "b", "r1", "r2"].filter(k => c[k] && c[k].e).map(k => c[k]); }
function removeRefs(ids) {
  const s = new Set(ids);
  SK.doc.constraints = SK.doc.constraints.filter(c => !conEnts(c).some(id => s.has(id)));
  SK.doc.dims = SK.doc.dims.filter(d => d.type === "note" || !conEnts(d).some(id => s.has(id)));
}
function removePointRefs(ref) {
  const same = r => r && r.e === ref.e && r.k === ref.k;
  SK.doc.constraints = SK.doc.constraints.filter(c => !conPts(c).some(same));
  SK.doc.dims = SK.doc.dims.filter(d => !conPts(d).some(same));
}

function moveRefs(from, to) {
  for (const c of SK.doc.constraints.concat(SK.doc.dims)) {
    for (const k of ["a", "b", "r1", "r2"]) if (c[k] && c[k].e === from.e && c[k].k === from.k) c[k] = Object.assign({}, to);
  }
}

function newEnt(t, props) {
  const e = Object.assign({ id: newId("e"), t, layer: SK.doc.current_layer || "0" }, props);
  if (SK.constrMode) e.constr = true;
  SK.doc.entities.push(e);
  SK.idx && SK.idx.set(e.id, e);
  return e;
}

// add a constraint: solves; rejects conflicting and redundant constraints. Returns true when kept.
// entities held when a constraint is added (the reference); the other entity is moved
function holdOf(c) {
  const moving = new Set();
  let ref = [];
  switch (c.t) {
    case "coincident": ref = [c.b.e]; moving.add(c.a.e); break;
    case "pointon": ref = [c.e2]; moving.add(c.a.e); break;
    case "midpoint": case "symmetric": ref = [c.l]; if (c.a) moving.add(c.a.e); if (c.b) moving.add(c.b.e); break;
    case "parallel": case "perpendicular": ref = [c.l1]; moving.add(c.l2); break;
    case "tangent": case "equal": case "concentric": ref = [c.e1]; moving.add(c.e2); break;
    case "horizontal": case "vertical": if (c.a && c.b) { ref = [c.a.e]; moving.add(c.b.e); } break;
  }
  return ref.filter(id => id && !moving.has(id));
}

function addConstraint(c, silent) {
  c.id = c.id || newId("c");
  const before = JSON.stringify({ e: SK.doc.entities });
  const r0 = buildSystem().rank();
  SK.doc.constraints.push(c);
  const S1 = buildSystem();
  if (S1.bad) { SK.doc.constraints.pop(); if (!silent) msg("Constraint not applicable to this geometry", true); return false; }
  // the reference entity is held where possible, so the other entity moves to it
  let res = null, Sx = null;
  const holds = holdOf(c).map(id => entById(id)).filter(e => isSolver(e))
    .map(e => ({ t: "fix", e: e.id, vals: entVals(e), tag: "hold" }));
  // a circle or arc made tangent keeps its radius where possible
  const radii = c.t === "tangent" && !c.ak1 && !c.ak2
    ? [c.e2, c.e1].map(id => entById(id)).filter(e => e && (e.t === "circle" || e.t === "arc") && !holds.some(h => h.e === e.id))
        .map(e => ({ t: "fix", e: e.id, param: 2, v: e.r, tag: "hold" }))
    : [];
  if (radii.length) { Sx = buildSystem(holds.concat(radii)); res = Sx.solve(); if (!res.ok) res = null; }
  if (!res && holds.length) { Sx = buildSystem(holds); res = Sx.solve(); if (!res.ok) res = null; }
  if (!res) { Sx = S1; res = S1.solve(); }
  if (!res.ok) {
    SK.doc.constraints.pop();
    if (!silent) msg("Conflicting constraint (not added)", true);
    return false;
  }
  Sx.write(res.x);
  const r1 = buildSystem().rank();
  if (r1 <= r0) {
    SK.doc.constraints.pop();
    SK.doc.entities = JSON.parse(before).e; reindex();
    if (!silent) msg("Redundant constraint (not added)", true);
    return false;
  }
  return true;
}

// a driving dimension: kept driving when it is independent of the other constraints
function tryDriving(d) {
  d.driving = true;
  d.value = measure(resolveDim(d));
  const r0 = (() => { d.driving = false; const r = buildSystem().rank(); d.driving = true; return r; })();
  const S = buildSystem();
  if (S.bad) { d.driving = false; return false; }
  const r1 = S.rank();
  if (r1 <= r0) { d.driving = false; return false; }
  return true;
}

function selected() {
  const pts = [], es = [], dims = [], cons = [];
  for (const s of SK.sel) {
    const q = parseSel(s);
    if (q.kind === "p") pts.push({ e: q.id, k: q.k });
    else if (q.kind === "e") { const e = entById(q.id); if (e) { if (e.t === "point") pts.push({ e: e.id, k: "p" }); else es.push(e); } }
    else if (q.kind === "d") dims.push(q.id);
    else if (q.kind === "c") cons.push(q.id);
  }
  return { pts, es, dims, cons };
}

function applyConstraint(t, quiet) {
  const { pts, es } = selected();
  const lines = es.filter(e => e.t === "line"), circs = es.filter(e => e.t === "circle" || e.t === "arc");
  const list = [];
  const need = (ok, msg) => { if (!ok) throw new Error(msg); };
  try {
    switch (t) {
      case "coincident":
        if (pts.length >= 1 && es.length === 1 && (lines.length || circs.length || CURVE_T.has(es[0].t))) {
          // point(s) and one line, circle or arc: point on object
          pts.filter(p => p.e !== es[0].id).forEach(p => list.push({ t: "pointon", a: p, e2: es[0].id }));
          need(list.length, "Coincident: the point belongs to this entity");
          break;
        }
        need(pts.length >= 2, "Coincident: select two or more points, or points and one line, circle or arc");
        for (let i = 1; i < pts.length; i++) list.push({ t, a: pts[0], b: pts[i] });
        break;
      case "horizontal": case "vertical":
        if (lines.length) lines.forEach(l => list.push({ t, l: l.id }));
        else { need(pts.length === 2, `${t}: select lines or two points`); list.push({ t, a: pts[0], b: pts[1] }); }
        break;
      case "parallel":
        need(lines.length >= 2, "Parallel: select two or more lines");
        for (let i = 1; i < lines.length; i++) list.push({ t, l1: lines[0].id, l2: lines[i].id });
        break;
      case "perpendicular":
        need(lines.length === 2, "Perpendicular: select two lines");
        list.push({ t, l1: lines[0].id, l2: lines[1].id });
        break;
      case "tangent":
        {
          const curves = es.filter(e => CURVE_T.has(e.t));
          if (curves.length && es.length === 2) {
            // a curve with a line, arc, circle or curve: at a shared end, or in contact elsewhere (line, arc, circle)
            const [x1, x2] = es;
            const sh = sharedEnd(x1, x2);
            if (sh) list.push({ t, e1: x1.id, e2: x2.id, ak1: needsEndKey(x1) ? sh[0] : undefined, ak2: needsEndKey(x2) ? sh[1] : undefined });
            else { need(curves.length === 1, "Tangent: two curves must share an end point"); list.push({ t, e1: x1.id, e2: x2.id }); }
            break;
          }
        }
        need(es.length === 2 && circs.length >= 1, "Tangent: select a line and a circle/arc, or two circles/arcs");
        {
          const [x1, x2] = circs.length === 2 ? circs : [lines[0], circs[0]];
          const sh = sharedEnd(x1, x2);
          if (sh) list.push({ t, e1: x1.id, e2: x2.id, ak1: x1.t === "arc" ? sh[0] : undefined, ak2: x2.t === "arc" ? sh[1] : undefined });
          else if (circs.length === 2) {
            const [a, b] = circs, d = dist([a.cx, a.cy], [b.cx, b.cy]);
            list.push({ t, e1: a.id, e2: b.id, mode: Math.abs(d - Math.abs(a.r - b.r)) < Math.abs(d - (a.r + b.r)) ? "int" : "ext" });
          } else list.push({ t, e1: lines[0].id, e2: circs[0].id });
        }
        break;
      case "equal": {
        const g = lines.length >= 2 ? lines : circs;
        need(g.length >= 2, "Equal: select two or more lines, or two or more circles/arcs");
        for (let i = 1; i < g.length; i++) list.push({ t, e1: g[0].id, e2: g[i].id });
        break;
      }
      case "pointon":
        need(pts.length >= 1 && es.length === 1 && (lines.length || circs.length || CURVE_T.has(es[0].t)), "Point on object: select points and one line, circle, arc or curve");
        pts.forEach(p => list.push({ t, a: p, e2: es[0].id }));
        break;
      case "midpoint":
        need(pts.length === 1 && lines.length === 1, "Midpoint: select a point and a line");
        list.push({ t, a: pts[0], l: lines[0].id });
        break;
      case "concentric":
        if (circs.length === 1 && pts.length >= 1 && es.length === 1) {
          // circle/arc and point(s): the centre coincides with the point
          pts.filter(p => !(p.e === circs[0].id && p.k === "c")).forEach(p => list.push({ t: "coincident", a: { e: circs[0].id, k: "c" }, b: p }));
          need(list.length, "Concentric: the point is the centre of this circle");
          break;
        }
        if (circs.length === 1 && lines.length >= 1 && !pts.length) {
          // circle/arc and line(s): the centre lies on the line
          lines.forEach(l => list.push({ t: "pointon", a: { e: circs[0].id, k: "c" }, e2: l.id }));
          break;
        }
        need(circs.length >= 2, "Concentric: select two or more circles/arcs, or a circle/arc and a point (centre at the point) or a line (centre on the line)");
        for (let i = 1; i < circs.length; i++) list.push({ t, e1: circs[0].id, e2: circs[i].id });
        break;
      case "symmetric":
        need(pts.length === 2 && lines.length === 1, "Symmetric: select two points and a line");
        list.push({ t, a: pts[0], b: pts[1], l: lines[0].id });
        break;
      case "fix":
        need(pts.length || es.length, "Fix: select points or entities");
        pts.forEach(p => list.push({ t, a: p, v: getPt(p) }));
        es.filter(e => isSolver(e)).forEach(e => list.push({ t, e: e.id, vals: entVals(e) }));
        break;
    }
  } catch (err) { if (!quiet) msg(err.message, true); return "need"; }
  if (!list.length) return "none";
  checkpoint();
  let kept = 0;
  for (const c of list) if (addConstraint(c, list.length > 1)) kept++;
  if (!kept) { SK.undo.pop(); if (list.length > 1) msg("Constraints not added (redundant or conflicting)", true); changed(); return "fail"; }
  msg(kept + " constraint(s) added" + (kept < list.length ? ", " + (list.length - kept) + " redundant or conflicting" : ""));
  changed();
  return "ok";
}

/** Constraint pick mode: a constraint button pressed with nothing selected; the points and entities clicked next
 *  are collected and the constraint is applied as soon as the selection fits it. Esc or a drawing tool ends it. */
function setConPick(t) {
  SK.conPick = t || null;
  document.querySelectorAll("#tab-sketch [data-con]").forEach(b => b.classList.toggle("active", b.dataset.con === SK.conPick));
  if (SK.conPick) { SK.sel.clear(); redraw(); showProps(); }
  updateHint();
}
const CON_PICK_HINT = { coincident: "two or more points, or points and one line, circle or arc", horizontal: "a line, or two points", vertical: "a line, or two points",
  parallel: "two lines", perpendicular: "two lines", tangent: "a line and a circle/arc, two circles/arcs, or a conic and the entity at its end", equal: "two lines, or two circles/arcs",
  pointon: "a point and a line, circle or arc", midpoint: "a point and a line", concentric: "two circles/arcs, or a circle/arc and a point", symmetric: "two points and the mirror line", fix: "points or entities" };
function conPickClick() {
  const r = applyConstraint(SK.conPick, true);
  if (r === "ok" || r === "fail") { SK.sel.clear(); redraw(); showProps(); }
}

// end points of two entities that coincide (arc ends s/e, line ends p1/p2), or null
function sharedEnd(a, b) {
  const ends = e => e.t === "arc" ? [["s", arcPt(e, e.a0)], ["e", arcPt(e, e.a1)]] : e.t === "line" ? [["p1", [e.x1, e.y1]], ["p2", [e.x2, e.y2]]] : CURVE_T.has(e.t) ? curveEnds(e) : [];
  const tol = 1e-4 * Math.max(1, ...ends(a).concat(ends(b)).map(([, q]) => Math.max(Math.abs(q[0]), Math.abs(q[1]))));
  for (const [ka, pa] of ends(a)) for (const [kb, pb] of ends(b)) if (dist(pa, pb) < tol) return [ka, kb];
  return null;
}

function deleteSelection() {
  const { pts, es, dims, cons } = selected();
  if (!pts.length && !es.length && !dims.length && !cons.length) return;
  checkpoint();
  const ids = new Set(es.filter(e => !e.axis).map(e => e.id));
  for (const s of SK.sel) { const q = parseSel(s); if (q.kind === "e" && entById(q.id) && !entById(q.id).axis) ids.add(q.id); }
  if (es.some(e => e.axis)) msg("The sketch axes are removed with the Axes button");
  SK.doc.entities = SK.doc.entities.filter(e => !ids.has(e.id));
  removeRefs([...ids]);
  for (const p of pts) if (!ids.has(p.e) && entById(p.e) && entById(p.e).t !== "point") removePointRefs(p);
  SK.doc.dims = SK.doc.dims.filter(d => !dims.includes(d.id));
  SK.doc.constraints = SK.doc.constraints.filter(c => !cons.includes(c.id));
  SK.sel.clear();
  changed();
}

function toggleConstruction() {
  const { es, pts } = selected();
  const list = es.concat(pts.map(p => entById(p.e)).filter(e => e && e.t === "point"));
  if (!list.length) { SK.constrMode = !SK.constrMode; $("#sk-construction").classList.toggle("active", SK.constrMode); msg(SK.constrMode ? "New geometry: construction" : "New geometry: normal"); return; }
  checkpoint();
  const on = !list.every(e => e.constr);
  list.forEach(e => { if (on) e.constr = true; else delete e.constr; });
  changed(true);
}

// ------------------------------------------------------------------ geometry operations

function solverRef(r) {
  if (!r || !r.e) return null;
  const e = entById(r.e);
  return isSolver(e) && r.k !== "m" ? r : (e && e.t === "line" && r.k === "m" ? r : null);
}

// auto constraints at a new point ref `mine` that was placed on snap `sn`
function autoAt(mine, sn) {
  if (!$("#sk-auto").checked || !sn || !sn.ref) return;
  if (sn.ref.on) { addConstraint({ t: "pointon", a: mine, e2: sn.ref.on }, true); return; }
  const r = sn.ref;
  if (r.k === "m") {
    const e = entById(r.e);
    if (e && e.t === "line") addConstraint({ t: "midpoint", a: mine, l: r.e }, true);
    return;
  }
  if (solverRef(r)) addConstraint({ t: "coincident", a: mine, b: r }, true);
}

function autoHV(lineId) {
  if (!$("#sk-auto").checked) return;
  const e = entById(lineId);
  const a = Math.abs(r2d(Math.atan2(e.y2 - e.y1, e.x2 - e.x1)));
  if (Math.min(a, 180 - a) < 1e-6) addConstraint({ t: "horizontal", l: lineId }, true);
  else if (Math.abs(a - 90) < 1e-6) addConstraint({ t: "vertical", l: lineId }, true);
}

// snap the second point of a line to horizontal/vertical when within 1.5 deg and not snapped to geometry
function hvSnap(base, sn) {
  if (!$("#sk-auto").checked || (sn.kind && sn.kind !== "on")) return sn;
  const d = sub(sn.p, base);
  const a = Math.abs(r2d(Math.atan2(d[1], d[0])));
  if (Math.min(a, 180 - a) < 1.5) return { p: [sn.p[0], base[1]], kind: null, ref: null };
  if (Math.abs(a - 90) < 1.5) return { p: [base[0], sn.p[1]], kind: null, ref: null };
  return sn;
}

function xformEnt(e, f, opts) {
  opts = opts || {};
  const P = (x, y) => f([x, y]);
  if (e.t === "line") { const a = P(e.x1, e.y1), b = P(e.x2, e.y2); [e.x1, e.y1, e.x2, e.y2] = [a[0], a[1], b[0], b[1]]; }
  else if (e.t === "circle") { const c = P(e.cx, e.cy); [e.cx, e.cy] = c; }
  else if (e.t === "arc") {
    const c = P(e.cx, e.cy); [e.cx, e.cy] = c;
    if (opts.rot) { e.a0 = n360(e.a0 + opts.rot); e.a1 = n360(e.a1 + opts.rot); }
    if (opts.mirror !== undefined) { const a0 = n360(2 * opts.mirror - e.a1), a1 = n360(2 * opts.mirror - e.a0); e.a0 = a0; e.a1 = a1; }
  }
  else if (e.t === "point" || e.t === "text") {
    const p = P(e.x, e.y); [e.x, e.y] = p;
    if (e.t === "text" && opts.rot) e.rot = n360((e.rot || 0) + opts.rot);
  }
  else if (e.t === "poly" || e.t === "spline") {
    e.pts = e.pts.map(p => f(p));
    if (e.pprof) {
      const c = P(e.pprof.cx, e.pprof.cy); [e.pprof.cx, e.pprof.cy] = c;
      if (opts.rot) e.pprof.rot = n360((e.pprof.rot || 0) + opts.rot);
      if (opts.mirror !== undefined) e.pprof.rot = n360(2 * opts.mirror - (e.pprof.rot || 0));
    }
  }
  else if (e.t === "conic") {
    const a = P(e.x0, e.y0), b = P(e.x1, e.y1), t = P(e.xt, e.yt);
    [e.x0, e.y0, e.x1, e.y1, e.xt, e.yt] = [a[0], a[1], b[0], b[1], t[0], t[1]];
  }
  else if (e.t === "ellipse") {
    const c = P(e.cx, e.cy), ma = f(ellPt(e, 0)), na = f(ellPt(e, 90));
    const s0 = ellClosed(e) ? null : f(ellPt(e, e.a0)), e0 = ellClosed(e) ? null : f(ellPt(e, e.a0 + ellSpan(e)));
    [e.cx, e.cy] = c;
    const d = sub(ma, c); e.rx = Math.hypot(d[0], d[1]); e.rot = n360(r2d(Math.atan2(d[1], d[0]))); e.ry = dist(na, c);
    if (s0) { const a0 = ellParam(e, s0), a1 = ellParam(e, e0); if (opts.mirror !== undefined) { e.a0 = a1; e.a1 = a0; } else { e.a0 = a0; e.a1 = a1; } }
  }
}

// after a move/rotate/mirror/trim etc.: fix values follow, driving values follow, violated constraints are removed
function postModify(movedIds) {
  const moved = new Set(movedIds || []);
  for (const c of SK.doc.constraints) {
    if (c.t !== "fix") continue;
    if (c.a && moved.has(c.a.e)) c.v = getPt(c.a);
    if (c.e && moved.has(c.e) && c.vals) { const e = entById(c.e); c.vals = entVals(e); }
  }
  for (const d of SK.doc.dims) if (d.driving) { const a = resolveDim(d); if (a) d.value = measure(a); }
  const S = buildSystem();
  const bad = new Set();
  S.res.forEach(q => { if (Math.abs(q.f(S.x)) > 1e-6) bad.add(q.tag); });
  const n0 = SK.doc.constraints.length;
  SK.doc.constraints = SK.doc.constraints.filter(c => !bad.has(c.id));
  SK.doc.dims.forEach(d => { if (bad.has("d:" + d.id)) d.driving = false; });
  const removed = n0 - SK.doc.constraints.length;
  if (removed) msg(removed + " constraint(s) removed (not satisfied after the change)");
}

function selectedEntityIds() {
  const ids = new Set();
  for (const s of SK.sel) { const q = parseSel(s); if (q.kind === "e" || q.kind === "p") ids.add(q.id); }
  return [...ids].filter(id => entById(id));
}

function cloneEnt(e) { const c = JSON.parse(JSON.stringify(e)); c.id = newId("e"); delete c.axis; return c; }

// ---- polylines from imported or included geometry

/** Circle through the polyline points when all lie on one circle: {cx, cy, r, a0, a1, closed} or null. */
function polyCircle(pts, closed) {
  if (pts.length < 4) return null;
  const a = pts[0], m = pts[Math.floor(pts.length / 2)], b = closed ? pts[Math.floor(2 * pts.length / 3)] : pts[pts.length - 1];
  const mm = closed ? pts[Math.floor(pts.length / 3)] : m;
  const [ax, ay] = a, [bx, by] = mm, [cx, cy] = b;
  const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
  if (Math.abs(d) < 1e-12) return null;
  const ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d;
  const uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d;
  const r = Math.hypot(ax - ux, ay - uy);
  const tol = Math.max(0.005, 2e-4 * r);
  if (r < tol || pts.some(p => Math.abs(Math.hypot(p[0] - ux, p[1] - uy) - r) > tol)) return null;
  const ang = p => n360(r2d(Math.atan2(p[1] - uy, p[0] - ux)));
  let a0 = ang(pts[0]), a1 = ang(pts[pts.length - 1]);
  if (n360(ang(pts[1]) - a0) > n360(a1 - a0)) [a0, a1] = [a1, a0];
  return { cx: ux, cy: uy, r, a0, a1, closed };
}

/** Replaces a polyline by solver or curve geometry: an arc or circle when the vertices lie on a circle, a spline
 *  through the vertices when the polyline is a sampled curve (5 or more vertices, smooth), else lines. Returns the
 *  new entities. */
function convertPoly(e, mode) {
  const pts = e.pts.map(p => p.slice());
  const closed = !!e.closed || (pts.length > 2 && dist(pts[0], pts[pts.length - 1]) < 1e-6);
  if (closed && dist(pts[0], pts[pts.length - 1]) < 1e-6) pts.pop();
  const base = { layer: e.layer, linetype: e.linetype, color: e.color, aci: e.aci, constr: e.constr };
  const out = [];
  const c = mode !== "lines" && mode !== "spline" ? polyCircle(pts, closed) : null;
  let smooth = pts.length >= 5;
  if (smooth) {
    for (let i = 1; i + 1 < pts.length && smooth; i++) {
      const u = unit(sub(pts[i], pts[i - 1])), v = unit(sub(pts[i + 1], pts[i]));
      if (dot(u, v) < Math.cos(d2r(30))) smooth = false;
    }
  }
  if (c) {
    out.push(c.closed ? newEnt("circle", Object.assign({ cx: c.cx, cy: c.cy, r: c.r }, base)) : newEnt("arc", Object.assign({ cx: c.cx, cy: c.cy, r: c.r, a0: c.a0, a1: c.a1 }, base)));
  } else if (mode === "spline" || (mode !== "lines" && smooth)) {
    out.push(newEnt("spline", Object.assign({ pts, closed }, base)));
  } else {
    const n = closed ? pts.length : pts.length - 1;
    for (let i = 0; i < n; i++) { const a = pts[i], b = pts[(i + 1) % pts.length]; if (dist(a, b) > 1e-9) out.push(newEnt("line", Object.assign({ x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, base))); }
  }
  // constraints and dimensions on the polyline are dropped with it
  SK.doc.entities = SK.doc.entities.filter(x => x.id !== e.id);
  removeRefs([e.id]);
  for (const s of [...SK.sel]) { const q = parseSel(s); if (q.id === e.id) SK.sel.delete(s); }
  reindex();
  return out;
}

/** True when the polyline is a sampled curve: 5 or more vertices and every turn below 30 deg. */
function polySmooth(pts) {
  if (pts.length < 5) return false;
  for (let i = 1; i + 1 < pts.length; i++) {
    const u = unit(sub(pts[i], pts[i - 1])), v = unit(sub(pts[i + 1], pts[i]));
    if (dot(u, v) < Math.cos(d2r(30))) return false;
  }
  return true;
}

/** Conic through the first and last point of an open point sequence with the end tangents of the sequence; rho
 *  chosen for the least maximum deviation from the points. Returns {props, dev} (dev: maximum deviation, mm) or
 *  null when the end tangents do not meet on the convex side. */
function fitConic(pts) {
  if (pts.length < 3) return null;
  const n = pts.length, p0 = pts[0], p1 = pts[n - 1];
  if (dist(p0, p1) < 1e-9) return null;
  // end tangents from the quadratic through the three end points (chord-length parameters)
  const endTan = (a, b, c) => {
    const t1 = dist(a, b), t2 = t1 + dist(b, c);
    if (t1 < 1e-12 || t2 - t1 < 1e-12) return unit(sub(b, a));
    return unit(add(add(mul(a, -(t1 + t2) / (t1 * t2)), mul(b, t2 / (t1 * (t2 - t1)))), mul(c, -t1 / (t2 * (t2 - t1)))));
  };
  const u0 = endTan(pts[0], pts[1], pts[2]), u1 = endTan(pts[n - 1], pts[n - 2], pts[n - 3]);
  // tangent intersection of the end tangents at the angles a0, a1 (rad): null when they do not meet on the convex side
  const apex = (a0, a1) => {
    const v0 = [Math.cos(a0), Math.sin(a0)], v1 = [Math.cos(a1), Math.sin(a1)], den = crs(v0, v1);
    if (Math.abs(den) < 1e-9) return null;
    const d = sub(p1, p0), a = crs(d, v1) / den, b = crs(d, v0) / den;
    if (a <= 0 || b <= 0) return null;
    return add(p0, mul(v0, a));
  };
  const propsOf = (a0, a1, rho) => { const pt = apex(a0, a1); return pt ? { x0: p0[0], y0: p0[1], x1: p1[0], y1: p1[1], xt: pt[0], yt: pt[1], rho } : null; };
  const devOf = props => {
    if (!props) return Infinity;
    const sm = conicPolyE(Object.assign({ t: "conic" }, props), 128);
    let worst = 0;
    for (const q of pts) { let m = Infinity; for (let i = 0; i + 1 < sm.length; i++) m = Math.min(m, segDist(q, sm[i], sm[i + 1])); worst = Math.max(worst, m); }
    return worst;
  };
  let x = [Math.atan2(u0[1], u0[0]), Math.atan2(u1[1], u1[0]), 0.5];
  if (!apex(x[0], x[1])) return null;
  let bd = devOf(propsOf(...x));
  for (let r = 0.05; r < 0.951; r += 0.05) { const v = devOf(propsOf(x[0], x[1], r)); if (v < bd) { bd = v; x[2] = r; } }
  // Nelder-Mead on the two tangent angles and rho
  const F = y => (y[2] <= 0.01 || y[2] >= 0.99) ? Infinity : devOf(propsOf(...y));
  let simplex = [x, [x[0] + d2r(1), x[1], x[2]], [x[0], x[1] + d2r(1), x[2]], [x[0], x[1], x[2] + 0.02]].map(y => ({ y, f: F(y) }));
  for (let it = 0; it < 150; it++) {
    simplex.sort((a, b) => a.f - b.f);
    if (simplex[3].f - simplex[0].f < 1e-6) break;
    const c = [0, 1, 2].map(k => (simplex[0].y[k] + simplex[1].y[k] + simplex[2].y[k]) / 3), w = simplex[3];
    const pt = (k) => c.map((v, i) => v + k * (v - w.y[i]));
    const r = pt(1), fr = F(r);
    if (fr < simplex[0].f) { const ex = pt(2), fe = F(ex); simplex[3] = fe < fr ? { y: ex, f: fe } : { y: r, f: fr }; }
    else if (fr < simplex[2].f) simplex[3] = { y: r, f: fr };
    else {
      const ct = pt(fr < w.f ? 0.5 : -0.5), fc = F(ct);
      if (fc < Math.min(fr, w.f)) simplex[3] = { y: ct, f: fc };
      else for (let k = 1; k < 4; k++) { const y = simplex[k].y.map((v, i) => (v + simplex[0].y[i]) / 2); simplex[k] = { y, f: F(y) }; }
    }
  }
  simplex.sort((a, b) => a.f - b.f);
  if (simplex[0].f < bd) { bd = simplex[0].f; x = simplex[0].y; }
  const props = propsOf(...x);
  props.rho = +props.rho.toFixed(4);
  return { props, dev: bd };
}

/** Replaces a polyline or a spline by the fitted conic. Returns the new entity or null. */
function convertToConic(e) {
  const pts = e.t === "spline" ? splinePolyE(e, 8) : e.pts.map(p => p.slice());
  if (e.closed && e.t !== "spline") return null;
  const fit = fitConic(pts);
  if (!fit) return null;
  const base = { layer: e.layer, linetype: e.linetype, color: e.color, aci: e.aci, constr: e.constr };
  const c = newEnt("conic", Object.assign(fit.props, base));
  SK.doc.entities = SK.doc.entities.filter(x => x.id !== e.id);
  removeRefs([e.id]);
  for (const s of [...SK.sel]) { const q = parseSel(s); if (q.id === e.id) SK.sel.delete(s); }
  reindex();
  return c;
}

/** Converts every polyline of the sketch (except polygon profiles). Returns the count. */
function convertAllPolys(mode) {
  const list = SK.doc.entities.filter(x => x.t === "poly" && !x.pprof && !x.fill);
  for (const e of list) convertPoly(e, mode);
  return list.length;
}

/** For a tool that needs a line, arc or curve: a polyline under the cursor is converted and the new entity at the
 *  click point is returned. */
function solidHit(hit, p) {
  if (!hit || hit.t !== "poly" || hit.pprof) return hit;
  checkpoint();
  const made = convertPoly(hit);
  let best = null, bd = Infinity;
  for (const e of made) { const d = entDist(e, p); if (d < bd) { bd = d; best = e; } }
  changed(true);
  return best;
}

// ---- trim / extend

function cutParams(e, others) {
  // intersections along e: {v, o, p}; v: line t in [0,1], circle/arc angle offset from a0 (deg); o: the
  // cutting entity; p: the point
  const ce = curves(e)[0];
  const bb = bbox(e);
  const res = [];
  for (const o of others) {
    if (o.id === e.id || o.t === "text" || o.t === "point" || o.axis || !layerOn(o)) continue;
    if (!bboxOverlap(bb, bbox(o), 1e-6)) continue;
    const pts = [];
    const A = cvAdapter(o);
    if (A) {
      // sampled curve (ellipse, spline): crossings refined on the true curve by bisection between the chord's parameters
      const f = e.t === "line" ? (q => { const a = [e.x1, e.y1], v = unit([e.x2 - e.x1, e.y2 - e.y1]); return crs(v, sub(q, a)); }) : (q => dist(q, [e.cx, e.cy]) - e.r);
      const sm = A.samples(24);
      for (let i = 0; i + 1 < sm.length; i++) {
        const sg = { s: "seg", a: sm[i].p, b: sm[i + 1].p };
        for (const q of intersect(ce, sg)) {
          let a = sm[i].t, b = sm[i + 1].t, fa = f(A.at(a)), fb = f(A.at(b));
          if (fa * fb < 0) { for (let it = 0; it < 50; it++) { const c = (a + b) / 2, fc = f(A.at(c)); if (fa * fc <= 0) { b = c; fb = fc; } else { a = c; fa = fc; } } pts.push(A.at((a + b) / 2)); }
          else pts.push(q);
        }
      }
      // an end of the curve lying on e: a cut at that point
      if (!A.whole) for (const t of A.range) { const q = A.at(t); if (entDist(e, q) < 1e-4 * Math.max(1, Math.abs(q[0]), Math.abs(q[1]))) pts.push(q); }
    } else for (const co of curves(o)) pts.push(...intersect(ce, co));
    for (const p of pts) {
      if (e.t === "line") {
        const d = [e.x2 - e.x1, e.y2 - e.y1];
        res.push({ v: dot(sub(p, [e.x1, e.y1]), d) / dot(d, d), o, p });
      } else {
        res.push({ v: n360(angOf([e.cx, e.cy], p) - (e.t === "arc" ? e.a0 : 0)), o, p });
      }
    }
  }
  return res;
}

/** The cut record nearest to parameter v. */
function cutAt(cuts, v) {
  let best = null;
  for (const c of cuts) if (!best || Math.abs(c.v - v) < Math.abs(best.v - v)) best = c;
  return best;
}

/** Constraint of a trimmed end (ref) that lies on the cutting entity: coincident when the point is an end of
 *  the cutter, tangent when the curves touch there, else point on object. Auto constraints only. */
function trimConstraint(ref, cut) {
  if (!$("#sk-auto").checked || !cut || !cut.o || cut.o.t === "point") return;
  if (!isSolver(cut.o)) return;
  const o = cut.o, p = cut.p;
  const tol = 1e-4 * Math.max(1, Math.abs(p[0]), Math.abs(p[1]));
  const ends = o.t === "line" ? [["p1", [o.x1, o.y1]], ["p2", [o.x2, o.y2]]] : o.t === "arc" ? [["s", arcPt(o, o.a0)], ["e", arcPt(o, o.a1)]] : CURVE_T.has(o.t) ? curveEnds(o) : [];
  const end = ends.find(([, q]) => dist(q, p) < tol);
  const e = entById(ref.e);
  const tan = (x, q) => x.t === "line" ? unit([x.x2 - x.x1, x.y2 - x.y1]) : CURVE_T.has(x.t) ? (A => A.tan(A.param(q)))(cvAdapter(x)) : unit([-(q[1] - x.cy), q[0] - x.cx]);
  const tangentAt = q => !!e && (e.t !== "line" || o.t !== "line") && !(CURVE_T.has(e.t) && CURVE_T.has(o.t) && !end) && Math.abs(crs(tan(e, q), tan(o, q))) < 1e-4;
  if (end) {
    // the trimmed end meets an end of the cutter: one coincident constraint replaces a point-on-object
    // constraint of the cutter end on this entity (from an earlier trim of the cutter)
    const b = { e: o.id, k: end[0] };
    SK.doc.constraints = SK.doc.constraints.filter(c => !(c.t === "pointon" && c.a && c.a.e === b.e && c.a.k === b.k && c.e2 === ref.e));
    setPt(ref, end[1]);
    addConstraint({ t: "coincident", a: ref, b }, true);
    if (tangentAt(end[1])) {
      // one tangent constraint anchored at the shared end replaces an unanchored one between the two entities
      const pair = c => c.t === "tangent" && ((c.e1 === o.id && c.e2 === e.id) || (c.e1 === e.id && c.e2 === o.id));
      SK.doc.constraints = SK.doc.constraints.filter(c => !pair(c));
      const c = { t: "tangent", e1: o.id, e2: e.id }; if (needsEndKey(o)) c.ak1 = end[0]; if (needsEndKey(e)) c.ak2 = ref.k;
      addConstraint(c, true);
    }
    return;
  }
  // tangent contact: the two curves have parallel tangents at the point
  if (tangentAt(p)) {
    const c = { t: "tangent", e1: o.id, e2: e.id };
    if (needsEndKey(e) && !CURVE_T.has(o.t)) c.ak2 = ref.k;
    addConstraint(c, true);
  }
  addConstraint({ t: "pointon", a: ref, e2: o.id }, true);
}

/** Trims e at the click p between its intersections. Returns "delete", "unsupported", or a list of the new
 *  ends [{ref: {e, k}, cut}] (the trimmed end points lying on the cutting entities). */
function trimAt(e, p) {
  if (e.t === "spline" || e.t === "ellipse" || e.t === "conic") return trimParamAt(e, p);
  const cuts = cutParams(e, ents());
  const vals = cuts.map(c => c.v);
  if (e.t === "line") {
    const d = [e.x2 - e.x1, e.y2 - e.y1], t = dot(sub(p, [e.x1, e.y1]), d) / dot(d, d);
    const inner = vals.filter(v => v > 1e-9 && v < 1 - 1e-9).sort((a, b) => a - b);
    const lo = Math.max(0, ...inner.filter(v => v < t)), hi = Math.min(1, ...inner.filter(v => v > t));
    const P = v => [e.x1 + d[0] * v, e.y1 + d[1] * v];
    if (lo <= 0 && hi >= 1) return "delete";
    if (lo <= 0) { const q = P(hi); removePointRefs({ e: e.id, k: "p1" }); e.x1 = q[0]; e.y1 = q[1]; return [{ ref: { e: e.id, k: "p1" }, cut: cutAt(cuts, hi) }]; }
    if (hi >= 1) { const q = P(lo); removePointRefs({ e: e.id, k: "p2" }); e.x2 = q[0]; e.y2 = q[1]; return [{ ref: { e: e.id, k: "p2" }, cut: cutAt(cuts, lo) }]; }
    const n = cloneEnt(e), a = P(lo), b = P(hi);
    moveRefs({ e: e.id, k: "p2" }, { e: n.id, k: "p2" });
    e.x2 = a[0]; e.y2 = a[1];
    n.x1 = b[0]; n.y1 = b[1];
    SK.doc.entities.push(n);
    reindex();
    return [{ ref: { e: e.id, k: "p2" }, cut: cutAt(cuts, lo) }, { ref: { e: n.id, k: "p1" }, cut: cutAt(cuts, hi) }];
  }
  if (e.t === "circle") {
    const angs = [...new Set(vals.map(a => +a.toFixed(9)))].sort((a, b) => a - b);
    if (angs.length < 2) return "delete";
    const ta = angOf([e.cx, e.cy], p);
    let lo = angs.filter(a => a <= ta).pop(), hi = angs.find(a => a > ta);
    if (lo === undefined) lo = angs[angs.length - 1];
    if (hi === undefined) hi = angs[0];
    // keep the complement of (lo, hi)
    e.t = "arc"; e.a0 = n360(hi); e.a1 = n360(lo);
    return [{ ref: { e: e.id, k: "s" }, cut: cutAt(cuts, hi) }, { ref: { e: e.id, k: "e" }, cut: cutAt(cuts, lo) }];
  }
  if (e.t === "arc") {
    const sp = arcSpan(e), ta = n360(angOf([e.cx, e.cy], p) - e.a0);
    const inner = vals.filter(v => v > 1e-7 && v < sp - 1e-7).sort((a, b) => a - b);
    const lo = Math.max(0, ...inner.filter(v => v < ta)), hi = Math.min(sp, ...inner.filter(v => v > ta));
    if (lo <= 0 && hi >= sp) return "delete";
    const a0 = e.a0;
    if (lo <= 0) { removePointRefs({ e: e.id, k: "s" }); e.a0 = n360(a0 + hi); return [{ ref: { e: e.id, k: "s" }, cut: cutAt(cuts, hi) }]; }
    if (hi >= sp) { removePointRefs({ e: e.id, k: "e" }); e.a1 = n360(a0 + lo); return [{ ref: { e: e.id, k: "e" }, cut: cutAt(cuts, lo) }]; }
    const n = cloneEnt(e);
    moveRefs({ e: e.id, k: "e" }, { e: n.id, k: "e" });
    e.a1 = n360(a0 + lo); n.a0 = n360(a0 + hi);
    SK.doc.entities.push(n);
    reindex();
    return [{ ref: { e: e.id, k: "e" }, cut: cutAt(cuts, lo) }, { ref: { e: n.id, k: "s" }, cut: cutAt(cuts, hi) }];
  }
  if (e.t === "poly") return trimPolyAt(e, p);
  return "unsupported";
}

/** Trim of a polyline (or an ellipse, converted to a polyline) between its intersections with the other
 *  entities. The parameter along the polyline is segment index + fraction. */
/** Crossing of two sampled curves (cvAdapter A, B) from the parameter estimates t, s: Newton iteration on
 *  A(t) - B(s) = 0 with finite-difference derivatives. Returns [t, s] or null when it does not converge. */
function curveCross(A, t, B, s) {
  const h = 1e-4, t00 = t, s00 = s;
  const der = (C, u) => mul(sub(C.at(u + h), C.at(u - h)), 1 / (2 * h));
  const span = C => { const w = C.range[1] - C.range[0]; return Math.max(w / 24, 1e-6); };
  for (let it = 0; it < 40; it++) {
    const r = sub(A.at(t), B.at(s));
    if (Math.hypot(r[0], r[1]) < 1e-10) break;
    const da = der(A, t), db = der(B, s);
    const det = -da[0] * db[1] + db[0] * da[1];
    if (Math.abs(det) < 1e-14) return null;
    const dt = (r[0] * db[1] - db[0] * r[1]) / det, ds = (-da[0] * r[1] + r[0] * da[1]) / det;
    t += dt; s += ds;
    if (Math.abs(t - t00) > 2 * span(A) || Math.abs(s - s00) > 2 * span(B)) return null;
  }
  const r = sub(A.at(t), B.at(s));
  if (Math.hypot(r[0], r[1]) > 1e-7) return null;
  if (A.whole && A.period) t = A.range[0] + ((t - A.range[0]) % A.period + A.period) % A.period;
  if (B.whole && B.period) s = B.range[0] + ((s - B.range[0]) % B.period + B.period) % B.period;
  return [t, s];
}

/** Trim a spline or an ellipse at the click: the piece between the nearest intersections is removed by narrowing
 *  the parameter range; the curve itself is unchanged. */
function trimParamAt(e, p) {
  const A = cvAdapter(e), [t0, t1] = A.range;
  const sm = A.samples(24);
  const segs = [];
  for (let i = 0; i + 1 < sm.length; i++) segs.push({ s: "seg", a: sm[i].p, b: sm[i + 1].p, ta: sm[i].t, tb: sm[i + 1].t });
  const tOf = (sg, q) => { const d = sub(sg.b, sg.a), L2 = dot(d, d) || 1; return sg.ta + (sg.tb - sg.ta) * Math.max(0, Math.min(1, dot(sub(q, sg.a), d) / L2)); };
  // nearest parameter on the true curve for a point near it (sample-based estimate refined by a local search)
  const nearT = q => {
    let t = A.param(q), step = (sm[1] ? sm[1].t - sm[0].t : 1) / 2;
    for (let it = 0; it < 40; it++) {
      const d0 = dist(q, A.at(t)), dm = dist(q, A.at(Math.max(t0, t - step))), dp = dist(q, A.at(Math.min(t1, t + step)));
      if (dm < d0 && dm <= dp) t = Math.max(t0, t - step); else if (dp < d0) t = Math.min(t1, t + step); else step /= 2;
    }
    return t;
  };
  let cuts = [];
  const endCuts = [];
  for (const o of ents()) {
    if (o.id === e.id || o.t === "text" || o.t === "point" || o.axis || !layerOn(o)) continue;
    const B = cvAdapter(o);
    if (B) {
      // crossing with another spline or ellipse: the chord crossing refined on both true curves
      const smB = B.samples(24);
      for (let j = 0; j + 1 < smB.length; j++) {
        const sgB = { s: "seg", a: smB[j].p, b: smB[j + 1].p, ta: smB[j].t, tb: smB[j + 1].t };
        for (const sg of segs) for (const q of intersect(sg, sgB)) {
          const r = curveCross(A, tOf(sg, q), B, tOf(sgB, q));
          cuts.push({ v: r ? r[0] : tOf(sg, q), o });
        }
      }
    } else {
      const oc = curves(o);
      // crossing with a line, arc or circle: refined on the true curve by bisection between the chord's sample parameters
      const f = o.t === "line" ? (q => { const a = [o.x1, o.y1], v = unit([o.x2 - o.x1, o.y2 - o.y1]); return crs(v, sub(q, a)); })
        : (o.t === "arc" || o.t === "circle") ? (q => dist(q, [o.cx, o.cy]) - o.r) : null;
      for (const sg of segs) for (const co of oc) for (const q of intersect(sg, co)) {
        let t = tOf(sg, q);
        if (f) {
          let a = sg.ta, b = sg.tb, fa = f(A.at(a)), fb = f(A.at(b));
          if (fa * fb < 0) { for (let it = 0; it < 50; it++) { const c = (a + b) / 2, fc = f(A.at(c)); if (fa * fc <= 0) { b = c; fb = fc; } else { a = c; fa = fc; } } t = (a + b) / 2; }
        }
        cuts.push({ v: t, o });
      }
    }
    // an end of the other entity lying on this curve (exact; a tangent arc crosses the sampled chain nearby)
    const ends = o.t === "line" ? [[o.x1, o.y1], [o.x2, o.y2]] : o.t === "arc" ? [arcPt(o, o.a0), arcPt(o, o.a1)] : cvAdapter(o) && !cvAdapter(o).whole ? cvAdapter(o).range.map(t => cvAdapter(o).at(t)) : [];
    for (const q of ends) { const t = nearT(q); if (dist(q, A.at(t)) < 1e-4 * Math.max(1, Math.abs(q[0]), Math.abs(q[1]))) endCuts.push({ v: t, o }); }
  }
  const spacing = sm[1] ? (sm[1].t - sm[0].t) * 2 : 0;
  cuts = cuts.filter(c => !endCuts.some(x => Math.abs(c.v - x.v) <= spacing)).concat(endCuts);
  const vc = A.param(p);
  const byV = new Map();
  for (const c of cuts) { const k = +c.v.toFixed(9); if (!byV.has(k) && Math.abs(k - vc) > 1e-6) byV.set(k, c.o); }
  const vals = [...byV.keys()].sort((a, b) => a - b);
  // the cut record for a trimmed end: the cutter and the end point (for the auto constraints)
  const cutAtV = (v, ent) => { const o = byV.get(+v.toFixed(9)); return o ? { o, p: cvAdapter(ent).at(v) } : null; };
  const refsOf = (ent, loV, hiV) => {
    const out = [];
    if (loV !== null) { const c = cutAtV(loV, ent); if (c) out.push({ ref: { e: ent.id, k: "e" }, cut: c }); }
    if (hiV !== null) { const c = cutAtV(hiV, ent); if (c) out.push({ ref: { e: ent.id, k: "s" }, cut: c }); }
    return out;
  };
  if (A.whole) {
    if (vals.length < 2) return "delete";
    let lo = vals.filter(v => v < vc).pop(), hi = vals.find(v => v > vc);
    if (lo === undefined) lo = vals[vals.length - 1];
    if (hi === undefined) hi = vals[0];
    A.trim(hi, lo > hi ? lo : lo + A.period);
    return refsOf(e, lo, hi);
  }
  const lo = Math.max(t0, ...vals.filter(v => v < vc)), hi = Math.min(t1, ...vals.filter(v => v > vc));
  if (lo <= t0 + 1e-9 && hi >= t1 - 1e-9) return "delete";
  if (lo > t0 + 1e-9 && hi < t1 - 1e-9) { const nn = cloneEnt(e); SK.doc.entities.push(nn); cvAdapter(nn).trim(hi, t1); A.trim(t0, lo); reindex(); return refsOf(e, lo, null).concat(refsOf(nn, null, hi)); }
  if (lo > t0 + 1e-9) { A.trim(t0, lo); return refsOf(e, lo, null); }
  A.trim(hi, t1);
  return refsOf(e, null, hi);
}

function trimPolyAt(e, p) {
  const cs = curves(e);
  if (!cs.length) return "unsupported";
  const cuts = [];
  for (const o of ents()) {
    if (o.id === e.id || o.t === "text" || o.t === "point" || o.axis || !layerOn(o)) continue;
    const oc = curves(o);
    cs.forEach((c, ci) => {
      const d = sub(c.b, c.a), L2 = dot(d, d) || 1;
      for (const co of oc) for (const q of intersect(c, co)) cuts.push(ci + Math.max(0, Math.min(1, dot(sub(q, c.a), d) / L2)));
    });
  }
  // click parameter
  let bi = 0, bt = 0, bd = Infinity;
  cs.forEach((c, ci) => { const d = sub(c.b, c.a), L2 = dot(d, d) || 1, t = Math.max(0, Math.min(1, dot(sub(p, c.a), d) / L2)); const q = add(c.a, mul(d, t)), dd = dist(p, q); if (dd < bd) { bd = dd; bi = ci; bt = t; } });
  const vc = bi + bt, n = cs.length;
  const P = v => { const i = Math.min(n - 1, Math.floor(v)), t = v - i, c = cs[i]; return add(c.a, mul(sub(c.b, c.a), t)); };
  const vals = [...new Set(cuts.map(v => +v.toFixed(9)))].sort((a, b) => a - b).filter(v => Math.abs(v - vc) > 1e-9);
  const verts = v0 => { const out = []; for (let i = Math.ceil(v0); i < n; i++) out.push(cs[i].a.slice()); return out; }; // vertices strictly after v0 (start of segment i = vertex i)
  if (e.closed) {
    if (vals.length < 2) return "delete";
    let lo = vals.filter(v => v < vc).pop(), hi = vals.find(v => v > vc);
    if (lo === undefined) lo = vals[vals.length - 1];
    if (hi === undefined) hi = vals[0];
    // keep from hi forward (wrapping) to lo
    const pts = [P(hi)];
    let vpos = Math.floor(hi) + 1;
    const loU = lo > hi ? lo : lo + n;
    while (vpos < loU - 1e-9) { pts.push(cs[vpos % n].a.slice()); vpos++; }
    pts.push(P(lo));
    e.pts = pts.filter((q, i) => i === 0 || dist(q, pts[i - 1]) > 1e-9); e.closed = false;
    return [];
  }
  const lo = Math.max(0, ...vals.filter(v => v < vc)), hi = Math.min(n, ...vals.filter(v => v > vc));
  if (lo <= 0 && hi >= n) return "delete";
  const before = [], after = [];
  if (lo > 0) { before.push(cs[0].a.slice()); for (let i = 1; i <= Math.floor(lo) && i < n; i++) before.push(cs[i].a.slice()); if (Math.abs(lo - Math.round(lo)) > 1e-9 || lo >= n) before.push(P(lo)); else if (before.length && dist(before[before.length - 1], P(lo)) > 1e-9) before.push(P(lo)); }
  if (hi < n) { after.push(P(hi)); for (let i = Math.floor(hi) + 1; i < n; i++) after.push(cs[i].a.slice()); after.push(cs[n - 1].b.slice()); }
  const dedupe = a => a.filter((q, i) => i === 0 || dist(q, a[i - 1]) > 1e-9);
  const b1 = dedupe(before), a1 = dedupe(after);
  if (b1.length >= 2 && a1.length >= 2) { e.pts = b1; const nn = cloneEnt(e); nn.pts = a1; SK.doc.entities.push(nn); reindex(); return []; }
  if (b1.length >= 2) { e.pts = b1; return []; }
  if (a1.length >= 2) { e.pts = a1; return []; }
  return "delete";
}

function extendAt(e, p) {
  if (e.t === "line") {
    const a = [e.x1, e.y1], b = [e.x2, e.y2];
    const atEnd = dist(p, b) < dist(p, a);
    const from = atEnd ? b : a, dir = unit(atEnd ? sub(b, a) : sub(a, b));
    const ray = { s: "seg", a: from, b: add(from, dir) };
    let best = Infinity, bp = null;
    for (const o of ents()) {
      if (o.id === e.id || o.t === "text" || o.t === "point" || o.axis || !layerOn(o)) continue;
      for (const co of curves(o)) for (const q of intersect(ray, co, true, false)) {
        const t = dot(sub(q, from), dir);
        if (t > 1e-7 && t < best) { best = t; bp = q; }
      }
    }
    if (!bp) return false;
    if (atEnd) { e.x2 = bp[0]; e.y2 = bp[1]; } else { e.x1 = bp[0]; e.y1 = bp[1]; }
    return true;
  }
  if (e.t === "arc") {
    const atEnd = dist(p, arcPt(e, e.a1)) < dist(p, arcPt(e, e.a0));
    const circ = { s: "circ", c: [e.cx, e.cy], r: e.r, a0: 0, span: 360 };
    let best = Infinity, ba = null;
    for (const o of ents()) {
      if (o.id === e.id || o.t === "text" || o.t === "point" || o.axis || !layerOn(o)) continue;
      for (const co of curves(o)) for (const q of intersect(circ, co, true, false)) {
        const a = angOf([e.cx, e.cy], q);
        const off = atEnd ? n360(a - e.a1) : n360(e.a0 - a);
        if (off > 1e-7 && off < best && off < 360 - arcSpan(e)) { best = off; ba = a; }
      }
    }
    if (ba === null) return false;
    if (atEnd) e.a1 = ba; else e.a0 = ba;
    return true;
  }
  return false;
}

// ---- fillet / chamfer between two lines; p1, p2: click points (kept sides)

function corner(l1, p1, l2, p2) {
  const X = lineInter(l1.id, l2.id);
  if (!X) return null;
  const side = (l, p) => {
    const a = [l.x1, l.y1], b = [l.x2, l.y2], d = unit(sub(b, a));
    const s = dot(sub(p, X), d) >= 0 ? 1 : -1;
    return mul(d, s);
  };
  return { X, u1: side(l1, p1), u2: side(l2, p2) };
}
function setNearEnd(l, X, u, q) {
  // the end of l on the corner side (smaller projection on u) moves to q
  const a = [l.x1, l.y1], b = [l.x2, l.y2];
  if (dot(sub(a, X), u) < dot(sub(b, X), u)) { removePointRefs({ e: l.id, k: "p1" }); l.x1 = q[0]; l.y1 = q[1]; return "p1"; }
  removePointRefs({ e: l.id, k: "p2" }); l.x2 = q[0]; l.y2 = q[1]; return "p2";
}

// an existing fillet arc or chamfer line between the near ends of l1 and l2, and the corner
// construction lines from those ends to X, are removed before a new fillet or chamfer is made
function clearCorner(l1, u1, l2, u2, X) {
  const near = (l, u) => { const a = [l.x1, l.y1], b = [l.x2, l.y2]; return dot(sub(a, X), u) < dot(sub(b, X), u) ? a : b; };
  const n1 = near(l1, u1), n2 = near(l2, u2);
  const tol = 1e-6 * Math.max(1, dist(n1, X), dist(n2, X)) + 1e-9;
  const endsOf = e => e.t === "line" ? [[e.x1, e.y1], [e.x2, e.y2]] : e.t === "arc" ? [arcPt(e, e.a0), arcPt(e, e.a1)] : [];
  const touches = (E, q) => E.some(x => dist(x, q) < tol);
  const gone = [];
  for (const e of ents()) {
    if (e.id === l1.id || e.id === l2.id) continue;
    const E = endsOf(e);
    if (E.length !== 2) continue;
    const corner = touches(E, n1) && touches(E, n2);
    const stub = e.constr && touches(E, X) && (touches(E, n1) || touches(E, n2));
    if (corner || stub) gone.push(e.id);
  }
  if (gone.length) {
    const g = new Set(gone);
    SK.doc.entities = SK.doc.entities.filter(e => !g.has(e.id));
    removeRefs(gone);
    reindex();
  }
  return gone.length;
}

// length of line l from the corner X in direction u (the kept part)
function keptLen(l, X, u) {
  return Math.max(dot(sub([l.x1, l.y1], X), u), dot(sub([l.x2, l.y2], X), u));
}

// construction lines from the trimmed ends to the original corner X, constrained collinear with the lines
// and meeting at the corner; equal: equal lengths (equal-distance chamfer)
function cornerLines(l1, k1, T1, l2, k2, T2, X, equal) {
  if (!$("#sk-cornerlines").checked) return;
  const c1 = newEnt("line", { x1: T1[0], y1: T1[1], x2: X[0], y2: X[1], layer: l1.layer, constr: true });
  const c2 = newEnt("line", { x1: T2[0], y1: T2[1], x2: X[0], y2: X[1], layer: l2.layer, constr: true });
  reindex();
  if (!$("#sk-auto").checked) return;
  addConstraint({ t: "coincident", a: { e: l1.id, k: k1 }, b: { e: c1.id, k: "p1" } }, true);
  addConstraint({ t: "coincident", a: { e: l2.id, k: k2 }, b: { e: c2.id, k: "p1" } }, true);
  addConstraint({ t: "coincident", a: { e: c1.id, k: "p2" }, b: { e: c2.id, k: "p2" } }, true);
  addConstraint({ t: "parallel", l1: l1.id, l2: c1.id }, true);
  addConstraint({ t: "parallel", l1: l2.id, l2: c2.id }, true);
  if (equal) addConstraint({ t: "equal", e1: c1.id, e2: c2.id }, true);
}

function fillet(l1, p1, l2, p2, r) {
  const c = corner(l1, p1, l2, p2);
  if (!c) return "Fillet: lines are parallel";
  const th = Math.acos(Math.max(-1, Math.min(1, dot(c.u1, c.u2)))) / 2;
  if (th < 1e-6 || th > Math.PI / 2 - 1e-6) return "Fillet: lines are collinear";
  clearCorner(l1, c.u1, l2, c.u2, c.X);
  if (r <= 0) {
    const k1 = setNearEnd(l1, c.X, c.u1, c.X), k2 = setNearEnd(l2, c.X, c.u2, c.X);
    if ($("#sk-auto").checked) addConstraint({ t: "coincident", a: { e: l1.id, k: k1 }, b: { e: l2.id, k: k2 } }, true);
    return null;
  }
  const t = r / Math.tan(th);
  const room = Math.min(keptLen(l1, c.X, c.u1), keptLen(l2, c.X, c.u2));
  if (t >= room - 1e-9) return "Fillet: radius " + fmtN(r) + " too large for these lines (max " + fmtN(room * Math.tan(th), 3) + ")";
  const T1 = add(c.X, mul(c.u1, t)), T2 = add(c.X, mul(c.u2, t));
  const C = add(c.X, mul(unit(add(c.u1, c.u2)), r / Math.sin(th)));
  const k1 = setNearEnd(l1, c.X, c.u1, T1), k2 = setNearEnd(l2, c.X, c.u2, T2);
  let a1 = angOf(C, T1), a2 = angOf(C, T2);
  let s1 = "s", s2 = "e";
  if (n360(a2 - a1) > 180) { [a1, a2] = [a2, a1]; s1 = "e"; s2 = "s"; }
  const arc = newEnt("arc", { cx: C[0], cy: C[1], r, a0: a1, a1: a2, layer: l1.layer });
  reindex();
  if ($("#sk-auto").checked) {
    addConstraint({ t: "coincident", a: { e: l1.id, k: k1 }, b: { e: arc.id, k: s1 } }, true);
    addConstraint({ t: "coincident", a: { e: l2.id, k: k2 }, b: { e: arc.id, k: s2 } }, true);
    addConstraint({ t: "tangent", e1: l1.id, e2: arc.id, ak2: s1 }, true);
    addConstraint({ t: "tangent", e1: l2.id, e2: arc.id, ak2: s2 }, true);
  }
  cornerLines(l1, k1, T1, l2, k2, T2, c.X, false);
  return null;
}

// ---- fillet between a line and an arc, or two arcs. k1, k2: click points on the kept parts

function fcOffsets(e, r) {
  if (e.t === "line") {
    const a = [e.x1, e.y1], b = [e.x2, e.y2], u = unit(sub(b, a)), n = [-u[1], u[0]];
    return [1, -1].map(sg => ({ s: "seg", a: add(a, mul(n, sg * r)), b: add(b, mul(n, sg * r)) }));
  }
  const out = [{ s: "circ", c: [e.cx, e.cy], r: e.r + r, a0: 0, span: 360 }];
  if (e.r - r > 1e-9) out.push({ s: "circ", c: [e.cx, e.cy], r: e.r - r, a0: 0, span: 360 });
  if (r - e.r > 1e-9) out.push({ s: "circ", c: [e.cx, e.cy], r: r - e.r, a0: 0, span: 360 });
  return out;
}
function fcFoot(e, P) {
  if (e.t === "line") { const a = [e.x1, e.y1], u = unit([e.x2 - e.x1, e.y2 - e.y1]); return add(a, mul(u, dot(sub(P, a), u))); }
  return add([e.cx, e.cy], mul(unit(sub(P, [e.cx, e.cy])), e.r));
}
// position along the entity: line distance from p1, arc angle from a0 (deg)
function fcParam(e, Q) {
  if (e.t === "line") { const a = [e.x1, e.y1], u = unit([e.x2 - e.x1, e.y2 - e.y1]); return dot(sub(Q, a), u); }
  return n360(angOf([e.cx, e.cy], Q) - e.a0);
}
function fcLen(e) { return e.t === "line" ? dist([e.x1, e.y1], [e.x2, e.y2]) : arcSpan(e); }
// T lies on the entity, on the same side of X as K
function fcSideOK(e, X, K, T) {
  let pX = fcParam(e, X), pK = fcParam(e, K), pT = fcParam(e, T);
  const L = fcLen(e), tol = e.t === "line" ? 1e-7 : 1e-6;
  if (e.t === "arc") {
    // X at an arc end can read as 0 or the full span
    if (Math.abs(pX - 360) < 1e-6 || (pX > L + 1e-6 && n360(pX) > 360 - 1e-6)) pX = 0;
    if (pX > L + 1e-6) pX = (n360(pX - L) < n360(360 - pX)) ? L : 0;
  }
  if (pT < -tol || pT > L + tol) return false;
  return (pT - pX) * (pK - pX) > 1e-12;
}
// shorten the entity so that it ends at T: the end on the corner side (X; else the side away from the click K) is
// moved to T; returns the moved end key
function fcTrim(e, K, T, X) {
  const tT = fcParam(e, T), tK = fcParam(e, K);
  // the end to move: with X, the end nearer to the corner; else the end on the far side of T from K
  let first;
  if (X) {
    let pX = fcParam(e, X);
    const L = fcLen(e);
    if (e.t === "arc" && pX > L + 1e-6) pX = (n360(pX - L) < n360(360 - pX)) ? L : 0;
    first = Math.abs(pX) < Math.abs(pX - L);
  } else first = tK > tT;
  if (e.t === "line") {
    if (first) { removePointRefs({ e: e.id, k: "p1" }); e.x1 = T[0]; e.y1 = T[1]; return "p1"; }
    removePointRefs({ e: e.id, k: "p2" }); e.x2 = T[0]; e.y2 = T[1]; return "p2";
  }
  const aT = angOf([e.cx, e.cy], T);
  if (first) { removePointRefs({ e: e.id, k: "s" }); e.a0 = aT; return "s"; }
  removePointRefs({ e: e.id, k: "e" }); e.a1 = aT; return "e";
}

function filletCurve(e1, k1, e2, k2, r) {
  if (e1.t === "circle" || e2.t === "circle") return "Fillet: trim the circle to an arc first";
  if (r <= 0) return "Fillet: radius must be > 0 for arcs";
  // corner: intersection of the two entities nearest the click points
  const mid = mul(add(k1, k2), 0.5);
  let Xs = [];
  for (const c1 of curves(e1)) for (const c2 of curves(e2)) Xs = Xs.concat(intersect(c1, c2));
  if (!Xs.length) for (const c1 of curves(e1)) for (const c2 of curves(e2)) Xs = Xs.concat(intersect(c1, c2, true, true));
  if (!Xs.length) return "Fillet: the line and arc do not meet";
  Xs.sort((a, b) => dist(a, mid) - dist(b, mid));
  const X = Xs[0];
  let best = null;
  for (const o1 of fcOffsets(e1, r)) for (const o2 of fcOffsets(e2, r)) for (const P of intersect(o1, o2, true, true)) {
    const T1 = fcFoot(e1, P), T2 = fcFoot(e2, P);
    if (dist(T1, T2) < 1e-9) continue;
    if (!fcSideOK(e1, X, k1, T1) || !fcSideOK(e2, X, k2, T2)) continue;
    const d = dist(P, X);
    if (!best || d < best.d) best = { P, T1, T2, d };
  }
  if (!best) return "Fillet: radius " + fmtN(r) + " does not fit between these entities";
  const { P, T1, T2 } = best;
  const q1 = fcTrim(e1, k1, T1, X), q2 = fcTrim(e2, k2, T2, X);
  let a1 = angOf(P, T1), a2 = angOf(P, T2), s1 = "s", s2 = "e";
  if (n360(a2 - a1) > 180) { [a1, a2] = [a2, a1]; s1 = "e"; s2 = "s"; }
  const arc = newEnt("arc", { cx: P[0], cy: P[1], r, a0: a1, a1: a2, layer: e1.layer });
  reindex();
  if ($("#sk-auto").checked) {
    addConstraint({ t: "coincident", a: { e: e1.id, k: q1 }, b: { e: arc.id, k: s1 } }, true);
    addConstraint({ t: "coincident", a: { e: e2.id, k: q2 }, b: { e: arc.id, k: s2 } }, true);
    for (const [e, q, s] of [[e1, q1, s1], [e2, q2, s2]]) {
      if (e.t === "line") addConstraint({ t: "tangent", e1: e.id, e2: arc.id, ak2: s }, true);
      else addConstraint({ t: "tangent", e1: e.id, e2: arc.id, ak1: q, ak2: s }, true);
    }
  }
  return null;
}

/** Fillet between a spline or ellipse and a line or arc: the arc centre is found numerically along the curve
 *  (circle of radius r tangent to both), the curve is trimmed by its parameter range, the other entity by its end. */
function filletParam(e1, k1, e2, k2, r) {
  const sp = cvAdapter(e1) ? e1 : e2, ot = sp === e1 ? e2 : e1, kS = sp === e1 ? k1 : k2, kO = sp === e1 ? k2 : k1;
  if (cvAdapter(ot)) return filletCurves(sp, kS, ot, kO, r);
  if (ot.t === "circle") return "Fillet: trim the circle to an arc first";
  if (r <= 0) return "Fillet: radius must be > 0";
  const A = cvAdapter(sp), [t0, t1] = A.range;
  const mid = mul(add(kS, kO), 0.5);
  let Xs = [];
  for (const c1 of curves(sp)) for (const c2 of curves(ot)) Xs = Xs.concat(intersect(c1, c2));
  // an end of one entity lying on the other (the usual corner after a trim) counts as the meeting point
  const tolX = q => 1e-3 * Math.max(1, Math.abs(q[0]), Math.abs(q[1]));
  for (const q of A.range.map(t => A.at(t))) if (entDist(ot, q) < tolX(q)) Xs.push(q);
  for (const q of (ot.t === "line" ? [[ot.x1, ot.y1], [ot.x2, ot.y2]] : [arcPt(ot, ot.a0), arcPt(ot, ot.a1)])) if (entDist(sp, q) < tolX(q)) Xs.push(q);
  if (!Xs.length) for (const c1 of curves(sp)) for (const c2 of curves(ot)) Xs = Xs.concat(intersect(c1, c2, true, true));
  if (!Xs.length) return "Fillet: the " + sp.t + " and the " + ot.t + " do not meet";
  Xs.sort((a, b) => dist(a, mid) - dist(b, mid));
  const X = Xs[0];
  const tX = A.param(X), tK = A.param(kS);
  const centre = (t, sg) => { const q = A.at(t), u = A.tan(t); return add(q, mul([-u[1], u[0]], sg * r)); };
  const gs = ot.t === "line"
    ? [C => { const a = [ot.x1, ot.y1], v = unit([ot.x2 - ot.x1, ot.y2 - ot.y1]); return Math.abs(crs(v, sub(C, a))) - r; }]
    : [C => dist(C, [ot.cx, ot.cy]) - (ot.r + r), C => dist(C, [ot.cx, ot.cy]) - Math.abs(ot.r - r)];
  const N = Math.max(128, A.samples(64).length * 2);
  let best = null;
  for (const sg of [1, -1]) for (const g of gs) {
    let tp = t0, gp = g(centre(tp, sg));
    for (let i = 1; i <= N; i++) {
      const t = t0 + (t1 - t0) * i / N, gv = g(centre(t, sg));
      if (gp === 0 || gp * gv < 0) {
        let a = tp, b = t, ga = gp;
        for (let it = 0; it < 50; it++) { const c = (a + b) / 2, gc = g(centre(c, sg)); if (ga * gc <= 0) b = c; else { a = c; ga = gc; } }
        const ts = (a + b) / 2, C = centre(ts, sg), T2 = A.at(ts), T1 = fcFoot(ot, C);
        if (dist(T1, T2) > 1e-9 && fcSideOK(ot, X, kO, T1) && (ts - tX) * (tK - tX) > 1e-12) {
          const d = dist(C, X);
          if (!best || d < best.d) best = { C, T1, T2, ts, d };
        }
      }
      tp = t; gp = gv;
    }
  }
  if (!best) return "Fillet: radius " + fmtN(r) + " does not fit between the " + sp.t + " and the " + ot.t;
  const { C, T1, T2, ts } = best;
  const qO = fcTrim(ot, kO, T1, X);
  if (tX > ts) A.trim(t0, ts); else A.trim(ts, t1);
  let a1 = angOf(C, T1), a2 = angOf(C, T2), s1 = "s", s2 = "e";
  if (n360(a2 - a1) > 180) { [a1, a2] = [a2, a1]; s1 = "e"; s2 = "s"; }
  const arc = newEnt("arc", { cx: C[0], cy: C[1], r, a0: a1, a1: a2, layer: ot.layer });
  reindex();
  if ($("#sk-auto").checked) {
    addConstraint({ t: "coincident", a: { e: ot.id, k: qO }, b: { e: arc.id, k: s1 } }, true);
    if (ot.t === "line") addConstraint({ t: "tangent", e1: ot.id, e2: arc.id, ak2: s1 }, true);
    else addConstraint({ t: "tangent", e1: ot.id, e2: arc.id, ak1: qO, ak2: s1 }, true);
    // the curve end meets the arc: coincident and tangent at that end
    const kS2 = tX > ts ? "e" : "s";
    addConstraint({ t: "coincident", a: { e: arc.id, k: s2 }, b: { e: sp.id, k: kS2 } }, true);
    addConstraint({ t: "tangent", e1: sp.id, e2: arc.id, ak1: kS2, ak2: s2 }, true);
  }
  return null;
}

/** Parameter of the curve A nearest to q: the sample-based estimate refined by a local search. */
function curveNearT(A, q) {
  const [t0, t1] = A.range;
  let t = A.param(q), step = (t1 - t0) / 48;
  for (let it = 0; it < 40; it++) {
    const d0 = dist(q, A.at(t)), tm = Math.max(t0, t - step), tp = Math.min(t1, t + step), dm = dist(q, A.at(tm)), dp = dist(q, A.at(tp));
    if (dm < d0 && dm <= dp) t = tm; else if (dp < d0) t = tp; else step /= 2;
  }
  return t;
}

/** Fillet between two parametric curves (spline, ellipse, conic): the arc centre is found along the first curve
 *  (offset by r) where its distance to the second curve equals r; both curves are trimmed by their parameter range. */
function filletCurves(e1, k1, e2, k2, r) {
  if (r <= 0) return "Fillet: radius must be > 0";
  const A = cvAdapter(e1), B = cvAdapter(e2), [a0, a1] = A.range, [b0, b1] = B.range;
  if (A.whole || B.whole) return "Fillet: trim the closed curve first";
  const mid = mul(add(k1, k2), 0.5);
  let Xs = [];
  for (const c1 of curves(e1)) for (const c2 of curves(e2)) Xs = Xs.concat(intersect(c1, c2));
  const tolX = q => 1e-3 * Math.max(1, Math.abs(q[0]), Math.abs(q[1]));
  for (const q of A.range.map(t => A.at(t))) if (entDist(e2, q) < tolX(q)) Xs.push(q);
  for (const q of B.range.map(t => B.at(t))) if (entDist(e1, q) < tolX(q)) Xs.push(q);
  if (!Xs.length) {
    // no crossing: the nearest pair of ends counts as the meeting point when the gap is small
    let bestE = null;
    for (const p of A.range.map(t => A.at(t))) for (const q of B.range.map(t => B.at(t))) { const d = dist(p, q); if (!bestE || d < bestE.d) bestE = { d, p: mul(add(p, q), 0.5) }; }
    if (bestE && bestE.d < CHECK.gap) Xs.push(bestE.p);
  }
  if (!Xs.length) return "Fillet: the " + e1.t + " and the " + e2.t + " do not meet";
  Xs.sort((a, b) => dist(a, mid) - dist(b, mid));
  const X = Xs[0];
  const tXA = curveNearT(A, X), tKA = A.param(k1), tXB = curveNearT(B, X), tKB = B.param(k2);
  const centre = (t, sg) => { const q = A.at(t), u = A.tan(t); return add(q, mul([-u[1], u[0]], sg * r)); };
  const g = C => { const tb = curveNearT(B, C); return { v: dist(C, B.at(tb)) - r, tb }; };
  // scan from the meeting point towards the kept side of the first curve
  const dirA = Math.sign(tKA - tXA) || 1, tEnd = dirA > 0 ? a1 : a0;
  const N = 160;
  let best = null;
  for (const sg of [1, -1]) {
    let tp = tXA, gp = g(centre(tp, sg)).v;
    for (let i = 1; i <= N; i++) {
      const t = tXA + (tEnd - tXA) * i / N, gv = g(centre(t, sg)).v;
      if (gp * gv < 0) {
        let lo = tp, hi = t, glo = gp;
        for (let it = 0; it < 40; it++) { const c = (lo + hi) / 2, gc = g(centre(c, sg)).v; if (glo * gc <= 0) hi = c; else { lo = c; glo = gc; } }
        const ts = (lo + hi) / 2, C = centre(ts, sg), tb = g(C).tb, T1 = A.at(ts), T2 = B.at(tb);
        if (dist(T1, T2) > 1e-9 && (tb - tXB) * (tKB - tXB) > 1e-12 && Math.abs(dist(C, T2) - r) < 1e-4 * Math.max(1, r)) {
          const d = dist(C, X);
          if (!best || d < best.d) best = { C, T1, T2, ts, tb, d };
        }
      }
      tp = t; gp = gv;
    }
  }
  if (!best) return "Fillet: radius " + fmtN(r) + " does not fit between the " + e1.t + " and the " + e2.t;
  const { C, T1, T2, ts, tb } = best;
  if (tXA > ts) A.trim(a0, ts); else A.trim(ts, a1);
  if (tXB > tb) B.trim(b0, tb); else B.trim(tb, b1);
  let q1 = angOf(C, T1), q2 = angOf(C, T2), s1 = "s", s2 = "e";
  if (n360(q2 - q1) > 180) { [q1, q2] = [q2, q1]; s1 = "e"; s2 = "s"; }
  const arc = newEnt("arc", { cx: C[0], cy: C[1], r, a0: q1, a1: q2, layer: e1.layer });
  reindex();
  if ($("#sk-auto").checked) {
    const k1 = tXA > ts ? "e" : "s", k2 = tXB > tb ? "e" : "s";
    addConstraint({ t: "coincident", a: { e: arc.id, k: s1 }, b: { e: e1.id, k: k1 } }, true);
    addConstraint({ t: "tangent", e1: e1.id, e2: arc.id, ak1: k1, ak2: s1 }, true);
    addConstraint({ t: "coincident", a: { e: arc.id, k: s2 }, b: { e: e2.id, k: k2 } }, true);
    addConstraint({ t: "tangent", e1: e2.id, e2: arc.id, ak1: k2, ak2: s2 }, true);
  }
  return null;
}

function chamfer(l1, p1, l2, p2, d) {
  const c = corner(l1, p1, l2, p2);
  if (!c) return "Chamfer: lines are parallel";
  clearCorner(l1, c.u1, l2, c.u2, c.X);
  const room = Math.min(keptLen(l1, c.X, c.u1), keptLen(l2, c.X, c.u2));
  if (d >= room - 1e-9) return "Chamfer: distance " + fmtN(d) + " too large for these lines (max " + fmtN(room, 3) + ")";
  const T1 = add(c.X, mul(c.u1, d)), T2 = add(c.X, mul(c.u2, d));
  const k1 = setNearEnd(l1, c.X, c.u1, T1), k2 = setNearEnd(l2, c.X, c.u2, T2);
  const ln = newEnt("line", { x1: T1[0], y1: T1[1], x2: T2[0], y2: T2[1], layer: l1.layer });
  reindex();
  if ($("#sk-auto").checked) {
    addConstraint({ t: "coincident", a: { e: l1.id, k: k1 }, b: { e: ln.id, k: "p1" } }, true);
    addConstraint({ t: "coincident", a: { e: l2.id, k: k2 }, b: { e: ln.id, k: "p2" } }, true);
  }
  cornerLines(l1, k1, T1, l2, k2, T2, c.X, true);
  return null;
}

// ---- sketch check: gaps, open ends, near tangents

const CHECK = { gap: 0.5, angle: 2 };     // mm, deg

/** Ends of an entity with the outward tangent direction at each end: [{ref, p, t}]; t null when unknown. */
function endsWithTangents(e) {
  const out = [];
  if (e.t === "line") {
    const u = unit([e.x2 - e.x1, e.y2 - e.y1]);
    out.push({ ref: { e: e.id, k: "p1" }, p: [e.x1, e.y1], t: mul(u, -1) }, { ref: { e: e.id, k: "p2" }, p: [e.x2, e.y2], t: u });
  } else if (e.t === "arc") {
    const tanAt = (a, sg) => { const q = arcPt(e, a); return mul(unit([-(q[1] - e.cy), q[0] - e.cx]), sg); };
    out.push({ ref: { e: e.id, k: "s" }, p: arcPt(e, e.a0), t: tanAt(e.a0, -1) }, { ref: { e: e.id, k: "e" }, p: arcPt(e, e.a1), t: tanAt(e.a1, 1) });
  } else if (cvAdapter(e)) {
    const A = cvAdapter(e);
    if (!A.whole) { const [t0, t1] = A.range; out.push({ ref: { e: e.id, k: "s" }, p: A.at(t0), t: mul(A.tan(t0), -1), curve: true }, { ref: { e: e.id, k: "e" }, p: A.at(t1), t: A.tan(t1), curve: true }); }
  }
  return out;
}

/** Issues of the sketch: gaps (two ends within CHECK.gap mm, not coincident), open ends (no other end nearby),
 *  near tangents (shared end, tangents within CHECK.angle deg but not equal, or equal without a tangent constraint). */
function sketchCheck() {
  const es = ents().filter(e => !e.axis && !e.constr && layerOn(e) && e.t !== "text" && e.t !== "point" && e.t !== "poly" && e.t !== "circle");
  const ends = [];
  for (const e of es) for (const x of endsWithTangents(e)) ends.push(Object.assign(x, { ent: e }));
  const issues = [];
  const seen = new Set();
  const hasTangent = (a, b) => SK.doc.constraints.some(c => c.t === "tangent" && ((c.e1 === a && c.e2 === b) || (c.e1 === b && c.e2 === a)));
  const hasCoincident = (ra, rb) => SK.doc.constraints.some(c => c.t === "coincident" && ((c.a.e === ra.e && c.a.k === ra.k && c.b.e === rb.e && c.b.k === rb.k) || (c.a.e === rb.e && c.a.k === rb.k && c.b.e === ra.e && c.b.k === ra.k)));
  for (let i = 0; i < ends.length; i++) {
    const a = ends[i];
    let best = null, bd = Infinity;
    for (let j = 0; j < ends.length; j++) {
      if (i === j || ends[j].ent.id === a.ent.id) continue;
      const d = dist(a.p, ends[j].p);
      if (d < bd) { bd = d; best = ends[j]; }
    }
    // an end on the interior of another entity (T junction) is not open
    const onOther = () => es.some(o => o.id !== a.ent.id && entDist(o, a.p) < 1e-4 * Math.max(1, Math.abs(a.p[0]), Math.abs(a.p[1])));
    const key = best ? [a.ref.e + ":" + a.ref.k, best.ref.e + ":" + best.ref.k].sort().join("|") : null;
    const tol = 1e-4 * Math.max(1, Math.abs(a.p[0]), Math.abs(a.p[1]));
    if (!best || bd > CHECK.gap) { if (!onOther()) issues.push({ kind: "open", p: a.p, refs: [a.ref], text: `Open end of ${TYPE_NAMES[a.ent.t] || a.ent.t} ${a.ent.id}` }); continue; }
    if (seen.has(key)) continue;
    seen.add(key);
    if (bd > tol) { issues.push({ kind: "gap", p: a.p, refs: [a.ref, best.ref], d: bd, a, b: best, text: `Gap ${fmtN(bd, 4)} mm between ${a.ent.id} and ${best.ent.id}` }); continue; }
    if (a.t && best.t) {
      // tangents point away from the shared end: tangent continuity when they are opposite
      const ang = r2d(Math.acos(Math.max(-1, Math.min(1, -dot(a.t, best.t)))));
      const solver = isSolver(a.ent) && isSolver(best.ent);
      if (ang > 1e-4 && ang < CHECK.angle) issues.push({ kind: "neartangent", p: a.p, refs: [a.ref, best.ref], ang, a, b: best, solver, text: `Nearly tangent (${fmtN(ang, 3)} deg) at ${a.ent.id} / ${best.ent.id}` });
      else if (ang <= 1e-4 && solver && !hasTangent(a.ent.id, best.ent.id)) issues.push({ kind: "notangent", p: a.p, refs: [a.ref, best.ref], a, b: best, solver, text: `Tangent without constraint at ${a.ent.id} / ${best.ent.id}` });
      if (solver && !hasCoincident(a.ref, best.ref)) issues.push({ kind: "nocoincident", p: a.p, refs: [a.ref, best.ref], a, b: best, text: `Touching without coincident constraint at ${a.ent.id} / ${best.ent.id}` });
    }
  }
  issues.push(...overlapIssues());
  return issues;
}

/** Overlapping geometry: collinear lines whose segments overlap, arcs and circles with the same centre and radius
 *  whose spans overlap, and identical curves (ellipse, spline, conic, polyline). */
function overlapIssues() {
  const all = ents().filter(e => !e.axis && !e.constr && layerOn(e) && e.t !== "text" && e.t !== "point");
  const out = [];
  const tolOf = p => 1e-4 * Math.max(1, Math.abs(p[0]), Math.abs(p[1]));
  for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
    const a = all[i], b = all[j];
    if (a.t === "line" && b.t === "line") {
      const A = [a.x1, a.y1], u = sub([a.x2, a.y2], A), L = len(u);
      if (L < 1e-9) continue;
      const d = mul(u, 1 / L), tol = tolOf(A);
      const off = q => Math.abs(crs(d, sub(q, A)));
      if (off([b.x1, b.y1]) > tol || off([b.x2, b.y2]) > tol) continue;
      const s1 = dot(sub([b.x1, b.y1], A), d), s2 = dot(sub([b.x2, b.y2], A), d);
      const lo = Math.max(0, Math.min(s1, s2)), hi = Math.min(L, Math.max(s1, s2));
      if (hi - lo <= tol) continue;
      const m = add(A, mul(d, (lo + hi) / 2));
      out.push({ kind: "overlap", p: m, refs: [{ e: a.id, k: "p1" }, { e: b.id, k: "p1" }], a, b, len: hi - lo, union: [Math.min(0, s1, s2), Math.max(L, s1, s2)], text: `Overlapping lines ${a.id} / ${b.id} (${fmtN(hi - lo, 3)} mm)` });
    } else if ((a.t === "arc" || a.t === "circle") && (b.t === "arc" || b.t === "circle")) {
      const tol = tolOf([a.cx, a.cy]);
      if (dist([a.cx, a.cy], [b.cx, b.cy]) > tol || Math.abs(a.r - b.r) > tol) continue;
      let over = null;
      if (a.t === "circle" || b.t === "circle") over = a.t === "circle" && b.t === "circle" ? 360 : arcSpan(a.t === "arc" ? a : b);
      else {
        // angular overlap of the two spans
        const a0 = a.a0, sa = arcSpan(a), b0 = n360(b.a0 - a0), sb = arcSpan(b);
        const o1 = Math.max(0, Math.min(sa, b0 + sb) - b0), o2 = b0 + sb > 360 ? Math.min(sa, b0 + sb - 360) : 0;
        over = Math.max(o1, o2);
        if (over <= 1e-6) continue;
      }
      const mid = a.t === "arc" ? arcPt(a, a.a0 + arcSpan(a) / 2) : b.t === "arc" ? arcPt(b, b.a0 + arcSpan(b) / 2) : [a.cx + a.r, a.cy];
      out.push({ kind: "overlap", p: mid, refs: [{ e: a.id, k: "c" }, { e: b.id, k: "c" }], a, b, text: `Overlapping ${a.t === "circle" && b.t === "circle" ? "circles" : "arcs"} ${a.id} / ${b.id} (${fmtN(over, 2)} deg)` });
    } else if (a.t === b.t && ["ellipse", "spline", "conic", "poly"].includes(a.t)) {
      const strip = e => { const c = Object.assign({}, e); delete c.id; delete c.layer; delete c.linetype; delete c.color; delete c.aci; delete c.included; return JSON.stringify(c); };
      if (strip(a) !== strip(b)) continue;
      const bb = bbox(a);
      out.push({ kind: "overlap", p: [(bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2], refs: [{ e: a.id, k: "s" }, { e: b.id, k: "s" }], a, b, text: `Duplicate ${(TYPE_NAMES[a.t] || a.t).toLowerCase()} ${a.id} / ${b.id}` });
    }
  }
  return out;
}

function showCheck(issues) {
  const box = $("#sk-props");
  const fixable = issues.filter(x => x.kind !== "open");
  box.innerHTML = `<p><strong>Sketch check</strong></p><p class="hint">Gap tolerance ${fmtN(CHECK.gap, 3)} mm, tangent tolerance ${fmtN(CHECK.angle, 2)} deg.</p>` +
    (issues.length ? `<ul class="check-list">${issues.map((x, i) => `<li><a href="#" data-ci="${i}">${esc(x.text)}</a></li>`).join("")}</ul>` : `<p class="hint">No gaps, open ends, near tangents or overlaps.</p>`) +
    (fixable.length ? `<div class="buttons"><button type="button" id="skp-fixall">Fix ${fixable.length} issue(s)</button></div>` : "") +
    (SK.doc.entities.some(x => x.t === "poly" && !x.pprof && !x.fill) ? `<div class="buttons"><button type="button" id="skp-convpoly" title="Polylines become arcs, circles, splines or lines (solver geometry for constraints, trim, fillet and profiles)">Convert ${SK.doc.entities.filter(x => x.t === "poly" && !x.pprof && !x.fill).length} polyline(s)</button></div>` : "") +
    `<div class="grid2"><label>Gap tolerance (mm)<input type="text" inputmode="decimal" class="numf" id="skp-ckgap" value="${CHECK.gap}"></label><label>Tangent tolerance (deg)<input type="text" inputmode="decimal" class="numf" id="skp-ckang" value="${CHECK.angle}"></label></div>`;
  if ($("#skp-convpoly")) $("#skp-convpoly").onclick = () => { checkpoint(); const n = convertAllPolys(); changed(); msg(n + " polyline(s) converted"); showCheck(sketchCheck()); };
  box.querySelectorAll("a[data-ci]").forEach(a => a.onclick = ev => {
    ev.preventDefault();
    const x = issues[+a.dataset.ci];
    SK.sel.clear(); x.refs.forEach(r => SK.sel.add("e:" + r.e));
    // centre the view on the issue
    const svg = $("#sk-canvas svg"), r = svg.getBoundingClientRect();
    SK.view.ox = r.width / 2 - SK.view.s * x.p[0]; SK.view.oy = r.height / 2 + SK.view.s * x.p[1];
    redraw();
    msg(x.text);
  });
  const fa = $("#skp-fixall"); if (fa) fa.onclick = () => { checkpoint(); const n = fixIssues(fixable); changed(true); const rest = sketchCheck(); showCheck(rest); msg(`${n} issue(s) fixed, ${rest.length} remaining`); };
  $("#skp-ckgap").onchange = () => { const v = numv($("#skp-ckgap").value); if (v > 0) { CHECK.gap = v; showCheck(sketchCheck()); } };
  $("#skp-ckang").onchange = () => { const v = numv($("#skp-ckang").value); if (v > 0) { CHECK.angle = v; showCheck(sketchCheck()); } };
}

/** Fixes: a gap closes at the midpoint (at the curve end when one side is a spline or ellipse) with a coincident
 *  constraint (a fix constraint on the curve side); near tangents and tangents without constraint get a tangent
 *  constraint; touching ends get a coincident constraint. Each fix is kept only when the solver accepts it. */
function fixIssues(list) {
  let n = 0;
  const tryFix = (apply) => {
    const before = JSON.stringify(SK.doc);
    try { apply(); } catch (err) { SK.doc = JSON.parse(before); reindex(); return false; }
    if (solveAll()) { n++; return true; }
    SK.doc = JSON.parse(before); reindex();
    return false;
  };
  for (const x of list) {
    if (x.kind === "gap") {
      tryFix(() => {
        // a spline fit point or a curve end can be moved directly; a trimmed curve end is moved by the solver
        const movable = r => { const e = entById(r.e); return !CURVE_T.has(e.t) || e.t === "spline" && (e.t0 === undefined && e.t1 === undefined) || (e.t === "conic" && e.t0 === undefined && e.t1 === undefined); };
        const m = mul(add(x.a.p, x.b.p), 0.5);
        if (movable(x.a.ref)) setPt(x.a.ref, movable(x.b.ref) ? m : x.b.p);
        if (movable(x.b.ref)) setPt(x.b.ref, movable(x.a.ref) ? m : x.a.p);
        addConstraint({ t: "coincident", a: x.a.ref, b: x.b.ref }, true);
      });
    } else if ((x.kind === "neartangent" || x.kind === "notangent") && x.solver) {
      tryFix(() => {
        const c = { t: "tangent", e1: x.a.ent.id, e2: x.b.ent.id };
        if (needsEndKey(x.a.ent)) c.ak1 = x.a.ref.k;
        if (needsEndKey(x.b.ent)) c.ak2 = x.b.ref.k;
        if (!SK.doc.constraints.some(q => q.t === "coincident" && ((q.a.e === x.a.ref.e && q.a.k === x.a.ref.k && q.b.e === x.b.ref.e && q.b.k === x.b.ref.k) || (q.b.e === x.a.ref.e && q.b.k === x.a.ref.k && q.a.e === x.b.ref.e && q.a.k === x.b.ref.k))))
          addConstraint({ t: "coincident", a: x.a.ref, b: x.b.ref }, true);
        addConstraint(c, true);
      });
    } else if (x.kind === "nocoincident") {
      tryFix(() => addConstraint({ t: "coincident", a: x.a.ref, b: x.b.ref }, true));
    } else if (x.kind === "overlap") {
      // the entity with fewer constraints is removed; two lines or two arcs are merged into the kept one
      const ca = SK.doc.constraints.filter(c => conEnts(c).includes(x.a.id)).length, cb = SK.doc.constraints.filter(c => conEnts(c).includes(x.b.id)).length;
      const keep = cb > ca ? x.b : x.a, drop = keep === x.a ? x.b : x.a;
      tryFix(() => {
        const k = entById(keep.id), d = entById(drop.id);
        if (!k || !d) throw new Error("gone");
        if (k.t === "line" && d.t === "line") {
          const A = [k.x1, k.y1], u = unit(sub([k.x2, k.y2], A));
          const ss = [0, dot(sub([k.x2, k.y2], A), u), dot(sub([d.x1, d.y1], A), u), dot(sub([d.x2, d.y2], A), u)];
          const p1 = add(A, mul(u, Math.min(...ss))), p2 = add(A, mul(u, Math.max(...ss)));
          k.x1 = p1[0]; k.y1 = p1[1]; k.x2 = p2[0]; k.y2 = p2[1];
        } else if (k.t === "arc" && d.t === "arc") {
          const b0 = n360(d.a0 - k.a0), sk = arcSpan(k), sd = arcSpan(d);
          let start = k.a0, span;
          if (b0 <= sk + 1e-6) span = Math.max(sk, b0 + sd);
          else { start = d.a0; span = Math.max(sd, 360 - b0 + sk); }
          if (span >= 360 - 1e-6) { k.t = "circle"; delete k.a0; delete k.a1; }
          else { k.a0 = n360(start); k.a1 = n360(start + span); }
        } else if (k.t === "arc" && d.t === "circle") { k.t = "circle"; delete k.a0; delete k.a1; }
        SK.doc.entities = SK.doc.entities.filter(e => e.id !== d.id);
        removeRefs([d.id]);
        reindex();
      });
    }
  }
  return n;
}

/** Extends the selection to the tangent (or connected) chains through the selected lines and arcs. */
function selectChain(tangent) {
  const { es } = selected();
  const seeds = es.filter(e => e.t === "line" || e.t === "arc");
  if (!seeds.length) return msg("Select a line or an arc first", true);
  let n = 0;
  for (const e of seeds) for (const x of chainOf(e, tangent ? { tangent: true } : {})) { if (!SK.sel.has("e:" + x.id)) n++; SK.sel.add("e:" + x.id); }
  redraw(); showProps();
  msg(`${tangent ? "Tangent" : "Connected"} chain: ${n} entit${n === 1 ? "y" : "ies"} added`);
}

/** Ends of a line or arc: [[key, point], ...]. */
function entEnds(e) {
  if (e.t === "line") return [["p1", [e.x1, e.y1]], ["p2", [e.x2, e.y2]]];
  if (e.t === "arc") return [["s", arcPt(e, e.a0)], ["e", arcPt(e, e.a1)]];
  return [];
}
/** The chain of lines and arcs connected end to end through e (ends within tolerance), in order.
 *  opts.tangent: only junctions with tangent continuity (within CHECK.angle deg); opts.within: a Set of entity
 *  ids the chain may use. */
function chainOf(e, opts) {
  opts = opts || {};
  const cands = ents().filter(x => (x.t === "line" || x.t === "arc") && !x.axis && layerOn(x) && !!x.constr === !!e.constr && (!opts.within || opts.within.has(x.id)));
  const tol = q => 1e-4 * Math.max(1, Math.abs(q[0]), Math.abs(q[1]));
  const near = (a, b) => dist(a, b) < tol(a);
  // tangent continuity at a shared end: the outward tangents are opposite
  const tangentAt = (x, y, q) => {
    const tx = endsWithTangents(x).find(z => near(z.p, q)), ty = endsWithTangents(y).find(z => near(z.p, q));
    if (!tx || !ty || !tx.t || !ty.t) return false;
    return r2d(Math.acos(Math.max(-1, Math.min(1, -dot(tx.t, ty.t))))) < CHECK.angle;
  };
  const chain = [e];
  const used = new Set([e.id]);
  // extend at the end of the chain, then at the start
  const grow = (fromEnd) => {
    for (;;) {
      const last = fromEnd ? chain[chain.length - 1] : chain[0];
      const other = fromEnd ? (chain.length > 1 ? chain[chain.length - 2] : null) : (chain.length > 1 ? chain[1] : null);
      // the free end of last: the end not shared with other
      const ends = entEnds(last).map(x => x[1]);
      let free = ends;
      if (other) free = ends.filter(q => !entEnds(other).some(([, r]) => near(q, r)));
      if (chain.length === 1) free = fromEnd ? [ends[1]] : [ends[0]];
      if (!free.length) return;
      const q = free[0];
      let nxt = cands.filter(x => !used.has(x.id) && entEnds(x).some(([, r]) => near(q, r)));
      if (opts.tangent) nxt = nxt.filter(x => tangentAt(last, x, q));
      if (nxt.length !== 1) return;          // open end, or a branch
      used.add(nxt[0].id);
      if (fromEnd) chain.push(nxt[0]); else chain.unshift(nxt[0]);
      if (chain.length > 2 && chain[0] === chain[chain.length - 1]) return;
    }
  };
  grow(true); grow(false);
  return chain;
}
/** Offset of a connected chain of lines and arcs: each entity is offset by d to the side of p (judged on the
 *  clicked entity), adjacent offsets are joined at their intersection, and the joints get coincident constraints. */
function offsetChain(chain, d, p) {
  // side: offset of the clicked entity (the one nearest p) decides the side for the chain
  const e0 = chain.reduce((b, e) => entDist(e, p) < entDist(b, p) ? e : b, chain[0]);
  const ends = chain.map(entEnds);
  // the chain is closed when the last end meets the first start
  const tol = q => 1e-4 * Math.max(1, Math.abs(q[0]), Math.abs(q[1]));
  const closed = chain.length > 2 && entEnds(chain[0]).some(([, a]) => entEnds(chain[chain.length - 1]).some(([, b]) => dist(a, b) < tol(a)));
  // offset side for each entity: a point on the offset side of e0 propagated along the chain (left/right of the travel direction)
  const dir0 = chainDirs(chain);
  const u0 = dir0[chain.indexOf(e0)];
  const mid0 = e0.t === "line" ? mul(add([e0.x1, e0.y1], [e0.x2, e0.y2]), 0.5) : arcPt(e0, e0.a0 + arcSpan(e0) / 2);
  const leftOf = crs(u0.t, sub(p, mid0)) > 0;
  const out = [];
  for (let i = 0; i < chain.length; i++) {
    const e = chain[i], u = dir0[i];
    const m = e.t === "line" ? mul(add([e.x1, e.y1], [e.x2, e.y2]), 0.5) : arcPt(e, e.a0 + arcSpan(e) / 2);
    const nrm = [-u.t[1], u.t[0]];
    const side = add(m, mul(nrm, leftOf ? d : -d));
    const n = offsetEnt(e, d, side);
    if (!n) { out.forEach(x => { SK.doc.entities = SK.doc.entities.filter(y => y.id !== x.id); }); return null; }
    out.push(n);
  }
  reindex();
  // join adjacent offsets at the corner nearest the original corner
  const joints = [];
  for (let i = 0; i + 1 < chain.length + (closed ? 1 : 0); i++) {
    const j = (i + 1) % chain.length;
    const a = out[i], b = out[j];
    const ca = ends[i].map(x => x[1]), cb = ends[j].map(x => x[1]);
    let corner = null;
    for (const qa of ca) for (const qb of cb) if (dist(qa, qb) < tol(qa)) corner = qa;
    if (!corner) continue;
    let X = [];
    for (const c1 of curves(a)) for (const c2 of curves(b)) X = X.concat(intersect(c1, c2, true, true));
    if (!X.length) continue;
    X.sort((q1, q2) => dist(q1, corner) - dist(q2, corner));
    const q = X[0];
    const ka = nearestEndKey(a, corner), kb = nearestEndKey(b, corner);
    setPt({ e: a.id, k: ka }, q); setPt({ e: b.id, k: kb }, q);
    joints.push([{ e: a.id, k: ka }, { e: b.id, k: kb }]);
  }
  if ($("#sk-auto").checked) for (const [ra, rb] of joints) addConstraint({ t: "coincident", a: ra, b: rb }, true);
  return out[0];
}
/** Travel direction of each entity along the chain: {t: unit tangent at the middle (oriented along the chain)}. */
function chainDirs(chain) {
  const tol = q => 1e-4 * Math.max(1, Math.abs(q[0]), Math.abs(q[1]));
  const res = [];
  for (let i = 0; i < chain.length; i++) {
    const e = chain[i];
    const [s, f] = entEnds(e).map(x => x[1]);
    // forward when the start meets the previous entity (or the end meets the next one)
    let forward = true;
    const prev = chain[i - 1], next = chain[i + 1];
    if (prev) forward = entEnds(prev).some(([, r]) => dist(r, s) < tol(s));
    else if (next) forward = entEnds(next).some(([, r]) => dist(r, f) < tol(f));
    let t;
    if (e.t === "line") t = unit(sub(f, s));
    else { const am = e.a0 + arcSpan(e) / 2, q = arcPt(e, am); t = unit([-(q[1] - e.cy), q[0] - e.cx]); }
    if (!forward) t = mul(t, -1);
    res.push({ t, forward });
  }
  return res;
}
function nearestEndKey(e, q) {
  const ends = entEnds(e);
  return ends.reduce((b, x) => dist(x[1], q) < dist(b[1], q) ? x : b, ends[0])[0];
}

function offsetEnt(e, d, p) {
  if (e.t === "line") {
    const a = [e.x1, e.y1], b = [e.x2, e.y2], u = unit(sub(b, a)), n = [-u[1], u[0]];
    const s = crs(sub(b, a), sub(p, a)) >= 0 ? 1 : -1;
    const o = mul(n, s * d);
    return newEnt("line", { x1: a[0] + o[0], y1: a[1] + o[1], x2: b[0] + o[0], y2: b[1] + o[1], layer: e.layer, linetype: e.linetype, color: e.color, aci: e.aci });
  }
  if (e.t === "circle" || e.t === "arc") {
    const inside = dist(p, [e.cx, e.cy]) < e.r;
    const r = inside ? e.r - d : e.r + d;
    if (r <= 1e-9) return null;
    const n = cloneEnt(e); n.r = r; delete n.constr;
    SK.doc.entities.push(n);
    return n;
  }
  if (e.t === "poly" && !e.fill) {
    // offset of each segment, corners joined at the intersection of the offset segments
    const pts = e.pts, nn = pts.length, closed = e.closed;
    const area = pts.reduce((s, q, i) => s + crs(q, pts[(i + 1) % nn]), 0);
    let best = null, bd = Infinity;
    for (let i = 0; i + 1 < nn || (closed && i < nn); i++) {
      const dd = segDist(p, pts[i], pts[(i + 1) % nn]);
      if (dd < bd) { bd = dd; best = i; }
    }
    const a = pts[best], b = pts[(best + 1) % nn];
    let s = crs(sub(b, a), sub(p, a)) >= 0 ? 1 : -1;
    const segs = [];
    const m = closed ? nn : nn - 1;
    for (let i = 0; i < m; i++) {
      const A = pts[i], B = pts[(i + 1) % nn], u = unit(sub(B, A)), n = mul([-u[1], u[0]], s * d);
      segs.push([add(A, n), add(B, n)]);
    }
    const out = [];
    for (let i = 0; i < m; i++) {
      if (i === 0 && !closed) { out.push(segs[0][0]); continue; }
      const prev = segs[(i - 1 + m) % m], cur = segs[i];
      const q = intersect({ s: "seg", a: prev[0], b: prev[1] }, { s: "seg", a: cur[0], b: cur[1] }, true, true);
      out.push(q.length ? q[0] : cur[0]);
    }
    if (!closed) out.push(segs[m - 1][1]);
    void area;
    return newEnt("poly", { pts: out, closed, layer: e.layer, linetype: e.linetype, color: e.color, aci: e.aci });
  }
  return null;
}

// ------------------------------------------------------------------ tools

const PARAM = { offset: 5, fillet: 5, chamfer: 2, polygon: 6, p3g: 14, p3g_e: 0.44, p3g_d1_last: 14 };

function lastPick() { return SK.pick.length ? SK.pick[SK.pick.length - 1] : null; }

const TOOLS = {
  select: { hint: () => "Click to select (Shift adds), drag a window (left to right: inside, right to left: crossing). Drag points, lines, circles and dimensions. Double-click a driving dimension to change its value." },
  line: {
    hint: n => n ? "Next point (Shift: horizontal/vertical), typed x,y  @dx,dy  @L<A  or length. Esc ends." : "First point",
    base: () => lastPick() && lastPick().p,
    move: sn => (SK.pick.length ? hvSnap(lastPick().p, sn) : sn),
    click(sn) {
      if (!SK.pick.length) { SK.pick.push(sn); return; }
      const a = lastPick();
      sn = hvSnap(a.p, sn);
      if (dist(a.p, sn.p) < 1e-9) return;
      checkpoint();
      const e = newEnt("line", { x1: a.p[0], y1: a.p[1], x2: sn.p[0], y2: sn.p[1] });
      reindex();
      if (a.chain) autoAt({ e: e.id, k: "p1" }, { ref: a.chain });
      else autoAt({ e: e.id, k: "p1" }, a);
      autoAt({ e: e.id, k: "p2" }, sn);
      autoHV(e.id);
      const end = getPt({ e: e.id, k: "p2" });
      SK.pick.push({ p: end, chain: { e: e.id, k: "p2" } });
      changed(true);
    },
    preview() {
      const a = lastPick(); if (!a || !SK.snap) return [];
      const b = SK.snap.p;
      return [{ t: "line", x1: a.p[0], y1: a.p[1], x2: b[0], y2: b[1] }];
    },
  },
  rect: {
    hint: n => n ? "Opposite corner (or @width,height)" : "First corner",
    base: () => lastPick() && lastPick().p,
    click(sn) {
      if (!SK.pick.length) { SK.pick.push(sn); return; }
      const a = lastPick().p, b = sn.p;
      if (Math.abs(a[0] - b[0]) < 1e-9 || Math.abs(a[1] - b[1]) < 1e-9) return;
      checkpoint();
      const P = [a, [b[0], a[1]], b, [a[0], b[1]]];
      const L = [0, 1, 2, 3].map(i => newEnt("line", { x1: P[i][0], y1: P[i][1], x2: P[(i + 1) % 4][0], y2: P[(i + 1) % 4][1] }));
      reindex();
      if ($("#sk-auto").checked) {
        for (let i = 0; i < 4; i++) addConstraint({ t: "coincident", a: { e: L[i].id, k: "p2" }, b: { e: L[(i + 1) % 4].id, k: "p1" } }, true);
        addConstraint({ t: "horizontal", l: L[0].id }, true); addConstraint({ t: "horizontal", l: L[2].id }, true);
        addConstraint({ t: "vertical", l: L[1].id }, true); addConstraint({ t: "vertical", l: L[3].id }, true);
        autoAt({ e: L[0].id, k: "p1" }, SK.pick[0]);
        autoAt({ e: L[1].id, k: "p2" }, sn);
      }
      SK.pick = [];
      changed(true);
    },
    preview() {
      const a = lastPick(); if (!a || !SK.snap) return [];
      const b = SK.snap.p, P = [a.p, [b[0], a.p[1]], b, [a.p[0], b[1]]];
      return [0, 1, 2, 3].map(i => ({ t: "line", x1: P[i][0], y1: P[i][1], x2: P[(i + 1) % 4][0], y2: P[(i + 1) % 4][1] }));
    },
  },
  polygon: {
    hint: n => n ? `Vertex of the ${PARAM.polygon}-gon (circumscribed circle), or type the distance across flats` : `Centre of the ${PARAM.polygon}-gon`,
    base: () => lastPick() && lastPick().p,
    value(v) { if (SK.pick.length && v > 0) { const n = PARAM.polygon; this.make(v / 2 / Math.cos(Math.PI / n), 0, null); } },
    click(sn) {
      if (!SK.pick.length) { SK.pick.push(sn); return; }
      const c = SK.pick[0].p, d = sub(sn.p, c), r = Math.hypot(d[0], d[1]);
      if (r > 1e-9) this.make(r, Math.atan2(d[1], d[0]), sn);
    },
    pts(c, r, a0) { const n = PARAM.polygon; return Array.from({ length: n }, (_, i) => [c[0] + r * Math.cos(a0 + 2 * Math.PI * i / n), c[1] + r * Math.sin(a0 + 2 * Math.PI * i / n)]); },
    make(r, a0, sn) {
      const c = SK.pick[0].p, n = PARAM.polygon, P = this.pts(c, r, a0);
      checkpoint();
      const L = P.map((p, i) => newEnt("line", { x1: p[0], y1: p[1], x2: P[(i + 1) % n][0], y2: P[(i + 1) % n][1] }));
      const circ = newEnt("circle", { cx: c[0], cy: c[1], r, constr: true });
      reindex();
      if ($("#sk-auto").checked) {
        for (let i = 0; i < n; i++) addConstraint({ t: "coincident", a: { e: L[i].id, k: "p2" }, b: { e: L[(i + 1) % n].id, k: "p1" } }, true);
        for (let i = 0; i < n; i++) addConstraint({ t: "pointon", a: { e: L[i].id, k: "p1" }, e2: circ.id }, true);
        for (let i = 1; i < n; i++) addConstraint({ t: "equal", e1: L[0].id, e2: L[i].id }, true);
        autoAt({ e: circ.id, k: "c" }, SK.pick[0]);
        if (sn) autoAt({ e: L[0].id, k: "p1" }, sn);
      }
      SK.pick = [];
      changed(true);
    },
    preview() {
      const a = lastPick(); if (!a || !SK.snap) return [];
      const d = sub(SK.snap.p, a.p), r = Math.hypot(d[0], d[1]); if (r < 1e-9) return [];
      const P = this.pts(a.p, r, Math.atan2(d[1], d[0])), n = PARAM.polygon;
      return P.map((p, i) => ({ t: "line", x1: p[0], y1: p[1], x2: P[(i + 1) % n][0], y2: P[(i + 1) % n][1] })).concat([{ t: "circle", cx: a.p[0], cy: a.p[1], r }]);
    },
  },
  p3g: {
    hint: n => n ? "Direction of a lobe (point), or type the angle (deg)" : `Centre of the polygon profile (${pprofSummary()}); parameters in Properties`,
    base: () => lastPick() && lastPick().p,
    value(v) { if (SK.pick.length) this.make(d2r(v)); },
    click(sn) {
      if (!SK.pick.length) { SK.pick.push(sn); return; }
      const d = sub(sn.p, SK.pick[0].p);
      this.make(Math.hypot(d[0], d[1]) > 1e-9 ? Math.atan2(d[1], d[0]) : 0);
    },
    pts(c, rot, P = PPROF) {
      // Filemon (1959) / DIN 32711: x = R cos a - e cos a cos na - k e sin na sin a, y = R sin a - e sin a cos na + k e sin na cos a
      // R = d1 / 2 mean radius, e eccentricity, n lobes (gear ratio), k lever ratio (k = n: DIN P3G, equidistant curve)
      const R = P.d1 / 2, e = P.e, n = P.n, k = P.k, N = Math.max(60, 60 * n), out = [];
      for (let i = 0; i < N; i++) {
        const a = 2 * Math.PI * i / N;
        const x = R * Math.cos(a) - e * Math.cos(a) * Math.cos(n * a) - k * e * Math.sin(n * a) * Math.sin(a);
        const y = R * Math.sin(a) - e * Math.sin(a) * Math.cos(n * a) + k * e * Math.sin(n * a) * Math.cos(a);
        out.push([c[0] + x * Math.cos(rot) - y * Math.sin(rot), c[1] + x * Math.sin(rot) + y * Math.cos(rot)]);
      }
      return out;
    },
    /** Six arcs of the two-arc K-profile about centre c, one corner in direction rot. */
    twoArcs(c, rot) {
      const Dm = PPROF.Dm, R2 = PPROF.R2, R1 = Dm - R2, side = R1 - R2, cr = side / Math.sqrt(3);
      const V = [0, 1, 2].map(i => [c[0] + cr * Math.cos(rot + 2 * Math.PI * i / 3), c[1] + cr * Math.sin(rot + 2 * Math.PI * i / 3)]);
      const arcs = [];
      for (let i = 0; i < 3; i++) {
        const j = (i + 1) % 3, k = (i + 2) % 3;
        // corner arc at V[i]: from the direction V[k]->V[i] to the direction V[j]->V[i] (outward), 60 deg
        const a0 = r2d(Math.atan2(V[i][1] - V[j][1], V[i][0] - V[j][0])), a1 = r2d(Math.atan2(V[i][1] - V[k][1], V[i][0] - V[k][0]));
        arcs.push({ t: "arc", cx: V[i][0], cy: V[i][1], r: R2, a0: n360(a0), a1: n360(a1), corner: i });
        // flank arc centred at V[i], opposite side: from direction V[i]->V[j] to V[i]->V[k], 60 deg
        const b0 = r2d(Math.atan2(V[j][1] - V[i][1], V[j][0] - V[i][0])), b1 = r2d(Math.atan2(V[k][1] - V[i][1], V[k][0] - V[i][0]));
        arcs.push({ t: "arc", cx: V[i][0], cy: V[i][1], r: R1, a0: n360(b0), a1: n360(b1), flank: i });
      }
      return arcs;
    },
    make(rot) {
      const c = SK.pick[0].p;
      checkpoint();
      if (PPROF.kind === "twoarc") {
        const arcs = this.twoArcs(c, rot).map(a => newEnt("arc", { cx: a.cx, cy: a.cy, r: a.r, a0: a.a0, a1: a.a1 }));
        newEnt("point", { x: c[0], y: c[1], constr: true });
        reindex();
        if ($("#sk-auto").checked) {
          // chain: corner i end -> flank (opposite of corner (i+2)) ... built from end point proximity
          const ends = e => [["s", arcPt(e, e.a0)], ["e", arcPt(e, e.a1)]];
          for (let i = 0; i < arcs.length; i++) for (let j = i + 1; j < arcs.length; j++) {
            for (const [ki, pi] of ends(arcs[i])) for (const [kj, pj] of ends(arcs[j])) {
              if (dist(pi, pj) < 1e-6) { addConstraint({ t: "coincident", a: { e: arcs[i].id, k: ki }, b: { e: arcs[j].id, k: kj } }, true); addConstraint({ t: "tangent", e1: arcs[i].id, e2: arcs[j].id, ak1: ki, ak2: kj }, true); }
            }
          }
        }
        SK.pick = [];
        changed(true);
        msg(`Schaublin K-profile ${pprofSummary()}: outer circle ${fmtN(2 * ((PPROF.Dm - 2 * PPROF.R2) / Math.sqrt(3) + PPROF.R2), 3)} mm, inner circle ${fmtN(2 * (PPROF.Dm - PPROF.R2 - (PPROF.Dm - 2 * PPROF.R2) / Math.sqrt(3)), 3)} mm`);
        return;
      }
      newEnt("poly", { pts: this.pts(c, rot), closed: true, pprof: { n: PPROF.n, k: PPROF.k, d1: PPROF.d1, e: PPROF.e, rot: r2d(rot), cx: c[0], cy: c[1], preset: PPROF.preset } });
      newEnt("point", { x: c[0], y: c[1], constr: true });
      reindex();
      SK.pick = [];
      changed(true);
      const rs = this.pts([0, 0], 0).map(q => Math.hypot(q[0], q[1]));
      msg(`Polygon profile ${pprofSummary()}: outer circle ${fmtN(2 * Math.max(...rs), 4)} mm, inner circle ${fmtN(2 * Math.min(...rs), 4)} mm`);
    },
    preview() {
      const a = lastPick(); if (!a || !SK.snap) return [];
      const d = sub(SK.snap.p, a.p), rot = Math.hypot(d[0], d[1]) > 1e-9 ? Math.atan2(d[1], d[0]) : 0;
      if (PPROF.kind === "twoarc") return this.twoArcs(a.p, rot);
      return [{ t: "poly", pts: this.pts(a.p, rot), closed: true }];
    },
  },
  spline: {
    hint: n => n ? `Next fit point (${n} so far); click the first point to close; Enter, Esc or double-click finishes` : "First fit point of the spline",
    base: () => lastPick() && lastPick().p,
    click(sn) {
      if (SK.pick.length >= 3 && dist(sn.p, SK.pick[0].p) * SK.view.s < SNAP_PX) { this.finish(true); return; }
      if (SK.pick.length && dist(sn.p, lastPick().p) * SK.view.s < 4) { this.finish(false); return; }
      SK.pick.push(sn);
    },
    finish(closed) {
      const P = SK.pick.map(q => q.p.slice()), picks = SK.pick.slice();
      SK.pick = [];
      if (P.length < 2) { updateHint(); overlay(); return; }
      checkpoint();
      const e = newEnt("spline", { pts: P, closed: !!closed });
      reindex();
      picks.forEach((pk, i) => autoAt({ e: e.id, k: "v" + i }, pk));
      SK.sel.clear(); SK.sel.add("e:" + e.id);
      changed(true);
      showProps();
    },
    preview() {
      const a = lastPick(); if (!a || !SK.snap) return [];
      const P = SK.pick.map(q => q.p).concat([SK.snap.p]);
      return [{ t: "spline", pts: P, closed: false }];
    },
  },
  ellipse: {
    hint: n => n === 0 ? "Centre" : n === 1 ? "End of the first axis (direction and half length), or type the half length" : "Half length of the second axis: a point, or type the value",
    base: () => lastPick() && lastPick().p,
    value(v) {
      if (!SK.pick.length || !(v > 0)) return;
      if (SK.pick.length === 1) { const c = SK.pick[0].p; SK.pick.push({ p: [c[0] + v, c[1]], kind: null, ref: null }); updateHint(); overlay(); return; }
      this.make(v);
    },
    click(sn) {
      if (SK.pick.length < 2) { if (SK.pick.length === 1 && dist(SK.pick[0].p, sn.p) < 1e-9) return; SK.pick.push(sn); return; }
      const c = SK.pick[0].p, a = SK.pick[1].p;
      const u = unit(sub(a, c)), d = sub(sn.p, c);
      const ry = Math.abs(crs(u, d));
      if (ry > 1e-9) this.make(ry);
    },
    make(ry) {
      const c = SK.pick[0].p, a = SK.pick[1].p;
      const d = sub(a, c), rx = Math.hypot(d[0], d[1]);
      checkpoint();
      const e = newEnt("ellipse", { cx: c[0], cy: c[1], rx, ry, rot: n360(r2d(Math.atan2(d[1], d[0]))) });
      reindex();
      const pk = SK.pick[0];
      SK.pick = [];
      autoAt({ e: e.id, k: "c" }, pk);
      changed(true);
    },
    preview() {
      const c = lastPick() && SK.pick[0]; if (!c || !SK.snap) return [];
      if (SK.pick.length === 1) return [{ t: "line", x1: c.p[0], y1: c.p[1], x2: SK.snap.p[0], y2: SK.snap.p[1] }];
      const a = SK.pick[1].p, d = sub(a, c.p), rx = Math.hypot(d[0], d[1]);
      const ry = Math.abs(crs(unit(d), sub(SK.snap.p, c.p))) || rx * 0.5;
      return [{ t: "ellipse", cx: c.p[0], cy: c.p[1], rx, ry, rot: n360(r2d(Math.atan2(d[1], d[0]))) }];
    },
  },
  conic: {
    hint: n => n === 0 ? "Start point of the conic" : n === 1 ? "End point" : n === 2 ? "Tangent intersection (the tangents at the start and end meet there)"
      : "Shoulder point on the curve, or type rho (0.5 parabola, below 0.5 ellipse, above 0.5 hyperbola); Enter: 0.5",
    base: () => lastPick() && lastPick().p,
    value(v) { if (SK.pick.length === 3 && v > 0 && v < 1) this.make(v); },
    ent() {
      const [a, b, t] = SK.pick.map(q => q.p);
      return { x0: a[0], y0: a[1], x1: b[0], y1: b[1], xt: t[0], yt: t[1], rho: 0.5 };
    },
    click(sn) {
      if (SK.pick.length < 3) {
        if (SK.pick.length && SK.pick.some(q => dist(q.p, sn.p) < 1e-9)) return;
        if (SK.pick.length === 2) { const a = SK.pick[0].p, b = SK.pick[1].p; if (Math.abs(crs(sub(b, a), sub(sn.p, a))) < 1e-9 * Math.max(1, dist(a, b))) return msg("Conic: the tangent intersection cannot lie on the chord", true); }
        SK.pick.push(sn);
        return;
      }
      this.make(conicRhoAt(this.ent(), sn.p));
    },
    make(rho) {
      const props = this.ent();
      props.rho = rho;
      checkpoint();
      const e = newEnt("conic", props);
      reindex();
      const picks = SK.pick.slice();
      SK.pick = [];
      autoAt({ e: e.id, k: "s" }, picks[0]); autoAt({ e: e.id, k: "e" }, picks[1]);
      SK.sel.clear(); SK.sel.add("e:" + e.id);
      changed(true);
      showProps();
    },
    preview() {
      const a = lastPick(); if (!a || !SK.snap) return [];
      if (SK.pick.length === 1) return [{ t: "line", x1: a.p[0], y1: a.p[1], x2: SK.snap.p[0], y2: SK.snap.p[1] }];
      const p0 = SK.pick[0].p, p1 = SK.pick[1].p;
      if (SK.pick.length === 2) return [{ t: "line", x1: p0[0], y1: p0[1], x2: SK.snap.p[0], y2: SK.snap.p[1] }, { t: "line", x1: p1[0], y1: p1[1], x2: SK.snap.p[0], y2: SK.snap.p[1] }];
      const c = this.ent();
      c.rho = conicRhoAt(c, SK.snap.p);
      return [Object.assign({ t: "conic" }, c), { t: "line", x1: p0[0], y1: p0[1], x2: c.xt, y2: c.yt }, { t: "line", x1: p1[0], y1: p1[1], x2: c.xt, y2: c.yt }];
    },
  },
  circle: {
    hint: n => n ? "Point on the circle, or type the radius" : "Centre",
    base: () => lastPick() && lastPick().p,
    value(v) { if (SK.pick.length && v > 0) this.make(v); },
    click(sn) {
      if (!SK.pick.length) { SK.pick.push(sn); return; }
      const r = dist(lastPick().p, sn.p);
      if (r > 1e-9) this.make(r, sn);
    },
    make(r, sn) {
      const c = SK.pick[0];
      checkpoint();
      const e = newEnt("circle", { cx: c.p[0], cy: c.p[1], r });
      reindex();
      autoAt({ e: e.id, k: "c" }, c);
      if (sn && sn.ref && sn.ref.e && solverRef(sn.ref) && $("#sk-auto").checked) addConstraint({ t: "pointon", a: sn.ref, e2: e.id }, true);
      SK.pick = [];
      changed(true);
    },
    preview() {
      const a = lastPick(); if (!a || !SK.snap) return [];
      return [{ t: "circle", cx: a.p[0], cy: a.p[1], r: dist(a.p, SK.snap.p) }];
    },
  },
  arc: {
    hint: n => ["Centre", "Start point (radius)", "End point (counter-clockwise)"][n],
    base: () => SK.pick[0] && SK.pick[0].p,
    click(sn) {
      if (SK.pick.length < 2) {
        if (SK.pick.length === 1 && dist(SK.pick[0].p, sn.p) < 1e-9) return;
        SK.pick.push(sn); return;
      }
      const c = SK.pick[0].p, s = SK.pick[1].p, r = dist(c, s);
      checkpoint();
      const e = newEnt("arc", { cx: c[0], cy: c[1], r, a0: angOf(c, s), a1: angOf(c, sn.p) });
      reindex();
      autoAt({ e: e.id, k: "c" }, SK.pick[0]);
      autoAt({ e: e.id, k: "s" }, SK.pick[1]);
      autoAt({ e: e.id, k: "e" }, sn);
      SK.pick = [];
      changed(true);
    },
    preview() {
      if (!SK.snap) return [];
      if (SK.pick.length === 1) { const c = SK.pick[0].p; return [{ t: "line", x1: c[0], y1: c[1], x2: SK.snap.p[0], y2: SK.snap.p[1] }]; }
      if (SK.pick.length === 2) {
        const c = SK.pick[0].p, s = SK.pick[1].p;
        return [{ t: "arc", cx: c[0], cy: c[1], r: dist(c, s), a0: angOf(c, s), a1: angOf(c, SK.snap.p) }];
      }
      return [];
    },
  },
  point: {
    hint: () => "Point position",
    click(sn) {
      checkpoint();
      const e = newEnt("point", { x: sn.p[0], y: sn.p[1] });
      reindex();
      autoAt({ e: e.id, k: "p" }, sn);
      changed(true);
    },
  },
  move: {
    needsSel: true,
    hint: n => n ? "Destination point (or @dx,dy)" : "Base point",
    base: () => lastPick() && lastPick().p,
    click(sn) {
      if (!SK.pick.length) { SK.pick.push(sn); return; }
      const d = sub(sn.p, lastPick().p), ids = selectedEntityIds();
      checkpoint();
      const extra = xformEnts(ids, p => add(p, d));
      postModify(ids.concat(extra));
      SK.pick = [];
      changed(true);
    },
    preview() {
      const a = lastPick(); if (!a || !SK.snap) return [];
      const d = sub(SK.snap.p, a.p);
      return selectedEntityIds().map(id => { const c = JSON.parse(JSON.stringify(entById(id))); xformEnt(c, p => add(p, d)); return c; });
    },
  },
  copy: {
    needsSel: true,
    hint: n => n ? "Destination point (or @dx,dy); Esc ends" : "Base point",
    base: () => SK.pick[0] && SK.pick[0].p,
    click(sn) {
      if (!SK.pick.length) { SK.pick.push(sn); return; }
      const d = sub(sn.p, SK.pick[0].p);
      checkpoint();
      for (const id of selectedEntityIds()) { const c = cloneEnt(entById(id)); xformEnt(c, p => add(p, d)); SK.doc.entities.push(c); }
      changed(true);
    },
    preview() { return TOOLS.move.preview.call(this, SK.pick[0]); },
  },
  rotate: {
    needsSel: true,
    hint: n => n ? "Angle (deg, typed) or a point giving the angle from the centre" : "Centre of rotation",
    base: () => lastPick() && lastPick().p,
    value(v) { if (SK.pick.length) this.apply(v); },
    click(sn) {
      if (!SK.pick.length) { SK.pick.push(sn); return; }
      this.apply(r2d(Math.atan2(sn.p[1] - SK.pick[0].p[1], sn.p[0] - SK.pick[0].p[0])));
    },
    rot(c, a) { const r = d2r(a), co = Math.cos(r), si = Math.sin(r); return p => [c[0] + (p[0] - c[0]) * co - (p[1] - c[1]) * si, c[1] + (p[0] - c[0]) * si + (p[1] - c[1]) * co]; },
    apply(a) {
      const c = SK.pick[0].p, ids = selectedEntityIds();
      checkpoint();
      const extra = xformEnts(ids, this.rot(c, a), { rot: a });
      postModify(ids.concat(extra));
      SK.pick = [];
      changed(true);
    },
    preview() {
      if (!SK.pick.length || !SK.snap) return [];
      const c = SK.pick[0].p, a = r2d(Math.atan2(SK.snap.p[1] - c[1], SK.snap.p[0] - c[0]));
      return selectedEntityIds().map(id => { const e = JSON.parse(JSON.stringify(entById(id))); xformEnt(e, this.rot(c, a), { rot: a }); return e; })
        .concat([{ t: "line", x1: c[0], y1: c[1], x2: SK.snap.p[0], y2: SK.snap.p[1] }]);
    },
  },
  mirror: {
    needsSel: true,
    hint: n => n ? "Second point of the mirror line (copies are made; delete the originals if required)" : "First point of the mirror line",
    base: () => lastPick() && lastPick().p,
    mir(a, b) {
      const u = unit(sub(b, a));
      return p => { const v = sub(p, a), t = dot(v, u), q = add(a, mul(u, t)); return sub(mul(q, 2), p); };
    },
    click(sn) {
      if (!SK.pick.length) { SK.pick.push(sn); return; }
      const a = SK.pick[0].p, b = sn.p;
      if (dist(a, b) < 1e-9) return;
      const th = r2d(Math.atan2(b[1] - a[1], b[0] - a[0]));
      checkpoint();
      for (const id of selectedEntityIds()) { const c = cloneEnt(entById(id)); xformEnt(c, this.mir(a, b), { mirror: th }); SK.doc.entities.push(c); }
      SK.pick = [];
      changed(true);
    },
    preview() {
      if (!SK.pick.length || !SK.snap || dist(SK.pick[0].p, SK.snap.p) < 1e-9) return [];
      const a = SK.pick[0].p, b = SK.snap.p, th = r2d(Math.atan2(b[1] - a[1], b[0] - a[0]));
      return selectedEntityIds().map(id => { const e = JSON.parse(JSON.stringify(entById(id))); xformEnt(e, this.mir(a, b), { mirror: th }); return e; })
        .concat([{ t: "line", x1: a[0], y1: a[1], x2: b[0], y2: b[1] }]);
    },
  },
  offset: {
    pickEnt: true,
    hint: n => n ? "Side to offset to" : `Entity to offset with its connected chain, or with the selected entities when it is selected (Shift: this entity only; distance ${fmtN(PARAM.offset)})`,
    value(v) { if (v > 0) { PARAM.offset = v; updateHint(); } },
    click(sn, ev, hit) {
      if (!SK.pick.length) {
        if (!hit || !["line", "circle", "arc", "poly"].includes(hit.t)) return msg("Offset: line, circle, arc or polyline", true);
        SK.pick.push({ e: hit.id, single: !!(ev && ev.shiftKey) }); return;
      }
      checkpoint();
      const e0 = entById(SK.pick[0].e);
      const selIds = new Set(selectedEntityIds());
      const chain = SK.pick[0].single || e0.t === "poly" || e0.t === "circle" ? [e0] : chainOf(e0, selIds.size > 1 && selIds.has(e0.id) ? { within: selIds } : {});
      const n = chain.length > 1 ? offsetChain(chain, PARAM.offset, sn.p) : offsetEnt(e0, PARAM.offset, sn.p);
      if (!n) { SK.undo.pop(); msg("Offset not possible", true); }
      else if (chain.length > 1) msg(`Offset of ${chain.length} connected entities`);
      SK.pick = [];
      changed(true);
    },
  },
  trim: {
    pickEnt: true,
    hint: () => "Part of a line, circle, arc, polyline, ellipse, spline or conic to remove (bounded by intersections)",
    click(sn, ev, hit) {
      if (!hit) return;
      checkpoint();
      const r = trimAt(hit, SK.mouse.p);
      if (r === "delete") { SK.doc.entities = SK.doc.entities.filter(e => e.id !== hit.id); removeRefs([hit.id]); }
      else if (r === "unsupported") { SK.undo.pop(); return msg("Trim: lines, circles, arcs, polylines, ellipses, splines and conics", true); }
      postModify([hit.id]);
      if (Array.isArray(r)) { reindex(); for (const x of r) trimConstraint(x.ref, x.cut); }
      changed();
    },
  },
  extend: {
    pickEnt: true,
    hint: () => "Line or arc, near the end to extend",
    click(sn, ev, hit) {
      if (!hit) return;
      checkpoint();
      if (!extendAt(hit, SK.mouse.p)) { SK.undo.pop(); return msg("Extend: no boundary found", true); }
      postModify([hit.id]);
      changed(true);
    },
  },
  fillet: {
    pickEnt: true,
    hint: n => n ? `Second line or arc, on the side to keep (radius ${fmtN(PARAM.fillet)})` : `First line or arc, on the side to keep (radius ${fmtN(PARAM.fillet)}; 0 gives a sharp corner between lines)`,
    value(v) { if (v >= 0) { PARAM.fillet = v; updateHint(); } },
    click(sn, ev, hit) {
      hit = solidHit(hit, SK.mouse.p);
      if (!hit || !["line", "arc", "circle", "spline", "ellipse", "conic"].includes(hit.t)) return msg("Fillet: click a line, an arc, a spline, an ellipse or a conic", true);
      if (!SK.pick.length) { SK.pick.push({ e: hit.id, p: SK.mouse.p }); return; }
      if (hit.id === SK.pick[0].e) return;
      checkpoint();
      const f0 = entById(SK.pick[0].e);
      const err = f0.t === "line" && hit.t === "line" ? fillet(f0, SK.pick[0].p, hit, SK.mouse.p, PARAM.fillet)
        : (cvAdapter(f0) || cvAdapter(hit)) ? filletParam(f0, SK.pick[0].p, hit, SK.mouse.p, PARAM.fillet)
        : filletCurve(f0, SK.pick[0].p, hit, SK.mouse.p, PARAM.fillet);
      if (err) { SK.doc = JSON.parse(SK.undo.pop()); reindex(); msg(err, true); } else { postModify([SK.pick[0].e, hit.id]); msg("Fillet R" + fmtN(PARAM.fillet)); }
      SK.pick = [];
      changed(true);
    },
  },
  chamfer: {
    pickEnt: true,
    hint: n => n ? `Second line (distance ${fmtN(PARAM.chamfer)})` : `First line, on the side to keep (distance ${fmtN(PARAM.chamfer)})`,
    value(v) { if (v > 0) { PARAM.chamfer = v; updateHint(); } },
    click(sn, ev, hit) {
      hit = solidHit(hit, SK.mouse.p);
      if (!hit || hit.t !== "line") return msg("Chamfer: click a line", true);
      if (!SK.pick.length) { SK.pick.push({ e: hit.id, p: SK.mouse.p }); return; }
      if (hit.id === SK.pick[0].e) return;
      checkpoint();
      const err = chamfer(entById(SK.pick[0].e), SK.pick[0].p, hit, SK.mouse.p, PARAM.chamfer);
      if (err) { SK.doc = JSON.parse(SK.undo.pop()); reindex(); msg(err, true); } else { postModify([SK.pick[0].e, hit.id]); msg("Chamfer " + fmtN(PARAM.chamfer)); }
      SK.pick = [];
      changed(true);
    },
  },
  note: {
    hint: () => "Text position",
    async click(sn) {
      const t = await askText("");
      if (!t) return;
      checkpoint();
      SK.doc.dims.push({ id: newId("d"), type: "note", pos: sn.p, anchor: null, text: t });
      changed(true);
    },
  },
  leader: {
    hint: n => n ? "Text position" : "Arrow point",
    base: () => lastPick() && lastPick().p,
    async click(sn) {
      if (!SK.pick.length) { SK.pick.push(sn); return; }
      const a = SK.pick[0].p;
      SK.pick = [];
      const t = await askText("");
      if (!t) return;
      checkpoint();
      SK.doc.dims.push({ id: newId("d"), type: "note", pos: sn.p, anchor: a, text: t });
      changed(true);
    },
  },
};

// dimension tools: picks are points (refs) or entities
function dimTool(orient) {
  return {
    dimPick: true,
    hint: n => {
      if (!n) return "Line, circle, arc, or first point" + (orient ? "" : " (two lines: angle)");
      const f = SK.pick[0];
      if (n === 1 && f.kind === "pt") return "Second point or a line";
      if (n === 1 && f.kind === "line" && !orient) return "Dimension position, or a second line (angle)";
      return "Dimension position";
    },
    pickWhat(sn, hit) {
      const g = gripAt(SK.mouse.p);
      if (g) return { kind: "pt", ref: { e: g.e, k: g.k }, p: g.p };
      if (hit && hit.t === "line") return { kind: "line", id: hit.id };
      if (hit && (hit.t === "circle" || hit.t === "arc")) return { kind: "radial", id: hit.id };
      return null;
    },
    click(sn, ev, hit) {
      const w = this.pickWhat(sn, hit);
      const P = SK.pick;
      if (!P.length) {
        if (!w) return;
        P.push(w); return;
      }
      const f = P[0];
      // second pick
      if (P.length === 1 && f.kind === "pt" && w && (w.kind === "pt" || w.kind === "line")) { P.push(w); return; }
      if (P.length === 1 && f.kind === "line" && !orient && w && w.kind === "line" && w.id !== f.id) { P.push(w); return; }
      if (P.length === 1 && f.kind === "pt") return;
      // position
      this.create(sn.p);
    },
    record(pos) {
      const P = SK.pick, f = P[0], s = P[1];
      const d = { id: "tmp", text: "", prefix: "", tol: null };
      if (f.kind === "radial") {
        const e = entById(f.id);
        Object.assign(d, { type: e.t === "circle" ? "diameter" : "radius", ent: f.id, off: sub(pos, [e.cx, e.cy]) });
      } else if (f.kind === "line" && !s) {
        Object.assign(d, { type: "linear", line: f.id, orient: orient || "a" });
      } else if (f.kind === "line" && s && s.kind === "line") {
        const c = lineInter(f.id, s.id);
        if (!c) return null;
        const v1 = lineVec(f.id), v2 = lineVec(s.id);
        const [s0, span] = angleSector(c, add(c, v1), add(c, v2), pos);
        const u0 = [Math.cos(s0), Math.sin(s0)], u1 = [Math.cos(s0 + span), Math.sin(s0 + span)];
        // directions bounding the sector, counter-clockwise from the first line
        let l1 = f.id, l2 = s.id, a = v1, b = v2;
        if (Math.abs(crs(unit(v1), u0)) > 1e-6) { l1 = s.id; l2 = f.id; a = v2; b = v1; }
        Object.assign(d, { type: "angle", l1, l2, s1: dot(a, u0) >= 0 ? 1 : -1, s2: dot(b, u1) >= 0 ? 1 : -1, rad: dist(c, pos) });
      } else if (f.kind === "pt" && s && s.kind === "pt") {
        Object.assign(d, { type: "linear", r1: f.ref, r2: s.ref, orient: orient || "a" });
      } else if (f.kind === "pt" && s && s.kind === "line") {
        Object.assign(d, { type: "linear", r1: f.ref, l2: s.id, orient: "a" });
      } else return null;
      if (d.type === "linear") {
        const a = resolveDim(Object.assign({}, d, { off: [0, 0] }));
        if (!a) return null;
        d.off = sub(pos, mul(add(a.p1, a.p2), 0.5));
        if (!orient && d.r1 && d.r2) {
          // two points: horizontal or vertical from the position, aligned otherwise
          const lo = [Math.min(a.p1[0], a.p2[0]), Math.min(a.p1[1], a.p2[1])], hi = [Math.max(a.p1[0], a.p2[0]), Math.max(a.p1[1], a.p2[1])];
          if (pos[0] > lo[0] && pos[0] < hi[0] && (pos[1] > hi[1] || pos[1] < lo[1])) d.orient = "h";
          else if (pos[1] > lo[1] && pos[1] < hi[1] && (pos[0] > hi[0] || pos[0] < lo[0])) d.orient = "v";
        }
      }
      return d;
    },
    async create(pos) {
      const d = this.record(pos);
      SK.pick = [];
      if (!d) { msg("Dimension not possible for this selection", true); updateHint(); return; }
      checkpoint();
      d.id = newId("d");
      SK.doc.dims.push(d);
      let driving = false;
      if ($("#sk-driving").checked) driving = tryDriving(d);
      changed(true);
      if (driving) await editDimValue(d);
      else if ($("#sk-driving").checked) msg("Reference dimension (the geometry is already constrained, or not solver geometry)");
    },
    preview() {
      if (!SK.pick.length || !SK.snap) return null;
      const f = SK.pick[0];
      if (f.kind === "pt" && SK.pick.length === 1) return null;
      const d = this.record(SK.snap.p);
      return d ? resolveDim(d) : null;
    },
  };
}
TOOLS.dim = dimTool(null);
TOOLS.dimh = dimTool("h");
TOOLS.dimv = dimTool("v");

/** After a dimension value changes the size of the geometry. On a sheet (a drawing or a sketch with a sheet) the
 *  zoom is kept; the view is only moved when the geometry left the visible area (centred on it). Without a sheet
 *  the view fits when the geometry leaves the visible area or fills less than a fifth of it. */
function fitIfNeeded() {
  const b = extents(false);
  if (!b) return;
  const W = $("#sk-canvas").clientWidth, H = $("#sk-canvas").clientHeight;
  const a = S([b[0], b[3]]), c = S([b[2], b[1]]);
  const inside = a[0] >= 0 && a[1] >= 0 && c[0] <= W && c[1] <= H;
  const frac = Math.max((c[0] - a[0]) / W, (c[1] - a[1]) / H);
  if (SK.hostSheet || sheetOn()) {
    if (inside) return;
    if (c[0] - a[0] > W || c[1] - a[1] > H) { fit(); return; }      // larger than the window: the whole sheet
    SK.view.ox += W / 2 - (a[0] + c[0]) / 2;
    SK.view.oy += H / 2 - (a[1] + c[1]) / 2;
    redraw();
    return;
  }
  if (!inside || frac < 0.2) { if (SK.partEdit && !SK.partEdit.drawing) fitAll(); else fit(); }
}

function setDimValue(d, v) {
  if (d.type === "angle" && (v <= 0 || v >= 180)) return msg("Angle must be between 0 and 180 deg", true);
  if (d.type !== "angle" && v <= 0) return msg("Value must be > 0", true);
  checkpoint();
  const old = d.value;
  d.value = v;
  // other radii, construction line lengths (fillet/chamfer corners) and the first point of the
  // dimension are held where possible; the holds are dropped in steps when they conflict
  const own = new Set(conEnts(d));
  const radii = [], lens = [], anchor = [];
  for (const e of ents()) {
    if (own.has(e.id)) continue;
    if (e.t === "circle" || e.t === "arc") radii.push({ t: "dragr", e: e.id, v: e.r, tag: "hold" });
    else if (e.t === "line" && e.constr) lens.push({ t: "dist", a: { e: e.id, k: "p1" }, b: { e: e.id, k: "p2" }, v: dist([e.x1, e.y1], [e.x2, e.y2]), tag: "hold" });
  }
  const ap = d.r1 ? d.r1 : d.line ? { e: d.line, k: "p1" } : d.ent ? { e: d.ent, k: "c" } : null;
  if (ap && getPt(ap)) anchor.push({ t: "drag", a: ap, v: getPt(ap), tag: "hold" });
  let ok = false;
  for (const extra of [radii.concat(lens, anchor), radii.concat(anchor), radii, []]) {
    const S0 = buildSystem(extra);
    const res = S0.solve();
    if (res.ok) { S0.write(res.x); ok = true; break; }
  }
  if (!ok) {
    SK.doc = JSON.parse(SK.undo.pop());
    reindex();
    msg("Value " + fmtN(v, 4) + " not possible with the other constraints (kept " + fmtN(old, 4) + ")", true);
  }
  changed(true);
  if (ok) fitIfNeeded();
}

function previewEnts() {
  const t = TOOLS[SK.tool];
  if (!t || !t.preview || t.dimPick) return [];
  try { return t.preview.call(t) || []; } catch (e) { return []; }
}
function previewDim() {
  const t = TOOLS[SK.tool];
  if (!t || !t.dimPick) return null;
  try { return t.preview.call(t); } catch (e) { return null; }
}

function updateHint() {
  const t = TOOLS[SK.tool];
  const h = SK.conPick && SK.tool === "select" ? `${CON_NAMES[SK.conPick]}: click ${CON_PICK_HINT[SK.conPick] || "the points or entities"}; Esc ends` : t ? t.hint(SK.pick.length) : "";
  $("#sk-hint").textContent = h;
  $("#sk-hint").title = h;
  renderNext();
}

/** Suggested next operations for the current selection and tool: [action, label, key]. */
function nextActions() {
  const out = nextActions0();
  if (SK.doc && SK.tool === "select" && !SK.pick.length && selected().es.some(e => !e.axis) && !out.some(x => x[0] === "pattern")) out.push(["pattern", "Pattern", ""]);
  return out;
}
function nextActions0() {
  const out = [];
  const A = (a, label, key) => { if (!out.some(x => x[0] === a)) out.push([a, label, key === undefined ? keyOf(a) : key]); };
  if (!SK.doc || SK.tool !== "select" || SK.pick.length || SK.includeMode) return out;
  const { pts, es, dims, cons } = selected();
  const lines = es.filter(e => e.t === "line"), circs = es.filter(e => e.t === "circle" || e.t === "arc");
  const nsel = pts.length + es.length + dims.length + cons.length;
  if (!nsel) {
    if (!SK.doc.entities.length) { A("tool:line", "Line"); A("tool:rect", "Rectangle"); A("tool:circle", "Circle"); return out; }
    if (SK.dof > 0 || !SK.doc.constraints.length) { A("tool:dim", "Dimension"); A("tool:dimh", "Horizontal dimension"); A("tool:dimv", "Vertical dimension"); }
    if (SK.partEdit) A("finish", "Finish sketch", "Ctrl+E");
    return out;
  }
  const sd = selectedDrivingDim();
  if (sd) { A("value", "Type a value", "0-9, Enter"); return out; }
  if (dims.length || cons.length) { A("delete", "Delete"); return out; }
  if (pts.length >= 2 && !es.length) { A("con:coincident", "Coincident"); if (pts.length === 2) { A("con:horizontal", "Horizontal"); A("con:vertical", "Vertical"); A("tool:dim", "Dimension"); } return out; }
  if (pts.length === 1 && es.length === 1) { A("con:coincident", "Coincident"); A("con:pointon", "Point on object"); A("con:midpoint", "Midpoint"); return out; }
  if (lines.length === 1 && es.length === 1) { A("con:horizontal", "Horizontal"); A("con:vertical", "Vertical"); A("tool:dim", "Dimension"); return out; }
  if (lines.length === 2 && es.length === 2) { A("con:parallel", "Parallel"); A("con:perpendicular", "Perpendicular"); A("con:equal", "Equal"); A("tool:dim", "Angle"); return out; }
  if (lines.length === 1 && circs.length === 1 && es.length === 2) { A("con:tangent", "Tangent"); A("con:pointon", "Point on object"); return out; }
  if (circs.length === 1 && es.length === 1) { A("tool:dim", circs[0].t === "circle" ? "Diameter" : "Radius"); return out; }
  if (circs.length >= 2 && es.length === circs.length) { A("con:concentric", "Concentric"); A("con:equal", "Equal"); A("con:tangent", "Tangent"); return out; }
  if (lines.length >= 3 && es.length === lines.length) { A("con:equal", "Equal"); A("con:parallel", "Parallel"); return out; }
  if (es.length > 1) { A("con:equal", "Equal"); A("construction", "Construction"); }
  return out;
}

function renderNext() {
  const box = $("#sk-next");
  if (!box) return;
  const items = nextActions();
  box.hidden = !items.length;
  if (!items.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<span class="lbl">Next:</span>` + items.map(([a, label, key]) => `<button type="button" data-a="${esc(a)}"${a === "value" ? " disabled" : ""}>${esc(label)}${key ? `<kbd>${esc(key)}</kbd>` : ""}</button>`).join("");
  box.querySelectorAll("button[data-a]").forEach(b => { b.onclick = () => { const a = b.dataset.a; if (a === "finish") endPartEdit(true); else if (a === "pattern") patternForm(); else runAction(a); }; });
}

const PARAM_TITLE = { offset: "Offset distance", fillet: "Fillet radius", chamfer: "Chamfer distance", polygon: "Number of sides" };

async function setTool(name) {
  const t = TOOLS[name];
  if (!t) return;
  if (name === "p3g") { SK.tool = name; SK.pick = []; document.querySelectorAll("#tab-sketch [data-tool]").forEach(b => b.classList.toggle("active", b.dataset.tool === name)); $("#sk-canvas").classList.remove("select"); pprofForm(); updateHint(); overlay(); return; }
  if (PARAM_TITLE[name]) {
    const lines = selected().es.filter(e => e.t === "line");
    const v = await askValue(PARAM_TITLE[name], fmtN(PARAM[name], 6));
    if (v === null) { if (SK.tool !== name) setTool("select"); return; }
    if (v < 0 || (v === 0 && name !== "fillet")) { msg(PARAM_TITLE[name] + " must be > 0", true); return; }
    if (name === "polygon") { if (v < 3) { msg("At least 3 sides", true); return; } PARAM.polygon = Math.round(v); }
    else PARAM[name] = v;

    if ((name === "fillet" || name === "chamfer") && lines.length === 2 && selectedEntityIds().length === 2) {
      applyCorner(name, lines[0], lines[1]);
      return;
    }
    const la = selected().es.filter(e => e.t === "line" || e.t === "arc");
    if (name === "fillet" && la.length === 2 && selectedEntityIds().length === 2) {
      applyCurveFillet(la[0], la[1]);
      return;
    }
  }
  if (t.needsSel && !selectedEntityIds().length) { msg("Select the objects first", true); return; }
  if (SK.conPick && name !== "select") setConPick(null);
  SK.tool = name;
  SK.pick = [];
  document.querySelectorAll("#tab-sketch [data-tool]").forEach(b => b.classList.toggle("active", b.dataset.tool === name));
  $("#sk-canvas").classList.toggle("select", name === "select");
  updateHint();
  overlay();
}
// fillet or chamfer of two selected lines; the longer part of each line from the corner is kept
function applyCorner(name, a, b) {
  const X = lineInter(a.id, b.id);
  if (!X) { msg(name === "fillet" ? "Fillet: lines are parallel" : "Chamfer: lines are parallel", true); return; }
  const far = l => dist([l.x1, l.y1], X) >= dist([l.x2, l.y2], X) ? [l.x1, l.y1] : [l.x2, l.y2];
  checkpoint();
  const err = (name === "fillet" ? fillet : chamfer)(a, far(a), b, far(b), PARAM[name]);
  if (err) { SK.doc = JSON.parse(SK.undo.pop()); reindex(); msg(err, true); }
  else { postModify([a.id, b.id]); msg(name === "fillet" ? "Fillet R" + fmtN(PARAM[name]) : "Chamfer " + fmtN(PARAM[name])); }
  SK.sel.clear();
  changed();
}

// fillet of a selected line and arc (or two arcs): the end of each entity farther from the corner is kept
function applyCurveFillet(a, b) {
  let Xs = [];
  for (const c1 of curves(a)) for (const c2 of curves(b)) Xs = Xs.concat(intersect(c1, c2));
  if (!Xs.length) { msg("Fillet: the entities do not meet", true); return; }
  const X = Xs[0];
  const ends = e => e.t === "line" ? [[e.x1, e.y1], [e.x2, e.y2]] : [arcPt(e, e.a0), arcPt(e, e.a1)];
  const far = e => ends(e).sort((p, q) => dist(q, X) - dist(p, X))[0];
  // a point just inside the kept part (an end point itself can coincide with the corner)
  const keep = e => { const f = far(e); return e.t === "line" ? add(mul(X, 0.1), mul(f, 0.9)) : arcPt(e, n360(angOf([e.cx, e.cy], f) + (dist(arcPt(e, e.a0), f) < dist(arcPt(e, e.a1), f) ? 1 : -1) * arcSpan(e) * 0.1)); };
  checkpoint();
  const err = filletCurve(a, keep(a), b, keep(b), PARAM.fillet);
  if (err) { SK.doc = JSON.parse(SK.undo.pop()); reindex(); msg(err, true); }
  else { postModify([a.id, b.id]); msg("Fillet R" + fmtN(PARAM.fillet)); }
  SK.sel.clear();
  changed();
}

function resetTool() { SK.pick = []; SK.drag = null; SK.win = null; updateHint(); }

// ------------------------------------------------------------------ mouse and keyboard

function involvedSet() {
  const s = new Set();
  for (const c of SK.doc.constraints) conEnts(c).forEach(id => s.add(id));
  for (const d of SK.doc.dims) if (d.driving) conEnts(d).forEach(id => s.add(id));
  return s;
}

function evScreen(ev, svg) {
  const r = svg.getBoundingClientRect();
  const sx = ev.clientX - r.left, sy = ev.clientY - r.top;
  return { sx, sy, p: Minv(sx, sy) };
}

function toolSnap(ev) {
  const t = TOOLS[SK.tool];
  let sn = snapAt(SK.mouse.p);
  const base = t && t.base ? t.base() : null;
  if (base && ev && ev.shiftKey) sn = { p: ortho(base, sn.p, ev), kind: null, ref: null };
  else if (t && t.move) sn = t.move(sn);
  return sn;
}

function bindCanvas(svg) {
  svg.addEventListener("contextmenu", e => e.preventDefault());
  svg.addEventListener("wheel", e => {
    e.preventDefault();
    const { sx, sy, p } = evScreen(e, svg);
    const f = Math.exp(-e.deltaY * 0.0015);
    SK.view.s = Math.min(1e5, Math.max(1e-5, SK.view.s * f));
    SK.view.ox = sx - p[0] * SK.view.s;
    SK.view.oy = sy + p[1] * SK.view.s;
    redraw();
  }, { passive: false });

  svg.addEventListener("mousedown", e => {
    closeMenu();
    $("#sk-canvas").focus();
    SK.mouse = evScreen(e, svg);
    if (e.button === 1 || e.button === 2) {
      SK.pan = { sx: SK.mouse.sx, sy: SK.mouse.sy, ox: SK.view.ox, oy: SK.view.oy, moved: false, button: e.button };
      e.preventDefault();
      return;
    }
    if (e.button !== 0) return;
    const p = SK.mouse.p;
    // triple click with the Select tool finishes a feature sketch
    SK.clicks = (SK.clicks || []).filter(t => e.timeStamp - t < 600); SK.clicks.push(e.timeStamp);
    if (SK.clicks.length >= 3 && SK.tool === "select" && SK.partEdit) { SK.clicks = []; SK.lastDown = null; e.preventDefault(); endPartEdit(true); return; }
    if (SK.includeMode) { includeAt(p); return; }
    // double click: detected here because the redraw after the first click replaces the svg elements
    const last = SK.lastDown;
    SK.lastDown = { t: e.timeStamp, sx: SK.mouse.sx, sy: SK.mouse.sy };
    const dbl = last && e.timeStamp - last.t < 400 && Math.abs(last.sx - SK.mouse.sx) + Math.abs(last.sy - SK.mouse.sy) < 6;
    if (dbl && SK.tool === "select") {
      SK.lastDown = null; SK.drag = null;
      e.preventDefault();
      doubleClick(e);
      return;
    }
    // double click with the Spline tool: the second click repeats the last point, which ends the spline (TOOLS.spline.click)
    if (SK.tool === "select") {
      const add = e.shiftKey || e.ctrlKey;
      const gp = gripAt(p);
      const g = gp ? null : glyphAt(SK.mouse.sx, SK.mouse.sy);
      if (g) { toggleSel("c:" + g, add); return; }
      const dId = dimAt(SK.mouse.sx, SK.mouse.sy);
      if (dId) { toggleSel("d:" + dId, add, true); SK.drag = { kind: "dim", id: dId, start: p, moved: false }; return; }
      const hit = entityAt(p);
      if (gp && (!hit || hit.id === gp.e || dist(p, gp.p) * SK.view.s < 6 || entById(gp.e).t === "point")) {
        const key = entById(gp.e).t === "point" ? "e:" + gp.e : refKey(gp);
        if (SK.conPick) { toggleSel(key, true); conPickClick(); return; }
        toggleSel(key, add, true);
        SK.drag = { kind: "pt", ref: { e: gp.e, k: gp.k }, start: p, moved: false };
        return;
      }
      if (hit) {
        if (SK.conPick) { toggleSel("e:" + hit.id, true); conPickClick(); return; }
        toggleSel("e:" + hit.id, add, true);
        SK.drag = { kind: "ent", id: hit.id, start: p, moved: false, orig: JSON.parse(JSON.stringify(hit)) };
        return;
      }
      if (!add) { SK.sel.clear(); showProps(); }
      SK.win = { sx: SK.mouse.sx, sy: SK.mouse.sy, p, add };
      redraw();
      return;
    }
    const t = TOOLS[SK.tool];
    const sn = toolSnap(e);
    const hit = (t.pickEnt || t.dimPick) ? entityAt(p) : null;
    Promise.resolve(t.click(sn, e, hit)).catch(showErr).finally(() => { updateHint(); overlay(); });
    updateHint();
    overlay();
  });

  svg.addEventListener("mousemove", e => {
    SK.mouse = evScreen(e, svg);
    const p = SK.mouse.p;
    $("#sk-coords").textContent = `x ${fmtN(p[0], 3)}  y ${fmtN(p[1], 3)}`;
    if (SK.pan) {
      SK.view.ox = SK.pan.ox + SK.mouse.sx - SK.pan.sx;
      SK.view.oy = SK.pan.oy + SK.mouse.sy - SK.pan.sy;
      if (Math.abs(SK.mouse.sx - SK.pan.sx) + Math.abs(SK.mouse.sy - SK.pan.sy) > 3) SK.pan.moved = true;
      redraw();
      return;
    }
    if (SK.drag) { doDrag(e); return; }
    if (SK.win) { overlay(); return; }
    if (SK.tool === "select") {
      SK.snap = null;
      const gp = gripAt(p);
      const g = gp ? null : (glyphAt(SK.mouse.sx, SK.mouse.sy) || dimAt(SK.mouse.sx, SK.mouse.sy));
      const hit = g || gp ? null : entityAt(p);
      SK.hover = gp ? { kind: "p", p: gp.p } : hit ? { kind: "e", id: hit.id } : null;
    } else {
      const t = TOOLS[SK.tool];
      SK.snap = toolSnap(e);
      SK.hover = null;
      if (t.dimPick) {
        const gp = gripAt(p);
        const hit = gp ? null : entityAt(p);
        SK.hover = gp ? { kind: "p", p: gp.p } : hit ? { kind: "e", id: hit.id } : null;
        SK.snap = { p: SK.snap.p, kind: null };
      } else if (t.pickEnt) {
        const hit = entityAt(p);
        SK.hover = hit ? { kind: "e", id: hit.id } : null;
        if (t.pickEnt && !(SK.tool === "offset" && SK.pick.length)) SK.snap = { p, kind: null };
      }
    }
    overlay();
  });

  const up = e => {
    if (SK.pan) {
      const p = SK.pan; SK.pan = null;
      if (!p.moved && p.button === 2) openMenu(e.clientX, e.clientY);
      return;
    }
    if (SK.drag) { endDrag(); return; }
    if (SK.win) {
      const w = SK.win; SK.win = null;
      const m = SK.mouse;
      if (Math.abs(m.sx - w.sx) + Math.abs(m.sy - w.sy) > 4) windowSelect(w, m);
      redraw(); showProps();
    }
  };
  svg.addEventListener("mouseup", up);
  svg.addEventListener("mouseleave", () => { SK.snap = null; SK.hover = null; overlay(); });

  svg.addEventListener("dblclick", e => e.preventDefault());
  async function doubleClick(e) {
    if (SK.tool !== "select") return;
    SK.mouse = evScreen(e, svg);
    const dId = dimAt(SK.mouse.sx, SK.mouse.sy);
    if (dId) {
      const d = SK.doc.dims.find(x => x.id === dId);
      if (d.type === "note") {
        const t = await askText(d.text);
        if (t !== null && t !== d.text) { checkpoint(); d.text = t; changed(true); }
      } else if (d.driving) await editDimValue(d);
      return;
    }
    const hit = entityAt(SK.mouse.p);
    if (hit && hit.t === "text") {
      const t = await askText(hit.text);
      if (t !== null && t !== hit.text) { checkpoint(); hit.text = t; changed(true); }
    }
  }
}

function toggleSel(key, add, keepIfSelected) {
  if (add) { if (SK.sel.has(key)) SK.sel.delete(key); else SK.sel.add(key); }
  else if (!(keepIfSelected && SK.sel.has(key))) { SK.sel.clear(); SK.sel.add(key); }
  redraw(); showProps();
}

function windowSelect(w, m) {
  const a = w.p, b = m.p;
  const r = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
  const crossing = m.sx < w.sx;
  const edges = [[[r[0], r[1]], [r[2], r[1]]], [[r[2], r[1]], [r[2], r[3]]], [[r[2], r[3]], [r[0], r[3]]], [[r[0], r[3]], [r[0], r[1]]]]
    .map(([p, q]) => ({ s: "seg", a: p, b: q }));
  for (const e of visibleEnts()) {
    if (e.axis) continue;
    const bb = bbox(e);
    const inside = bb[0] >= r[0] && bb[2] <= r[2] && bb[1] >= r[1] && bb[3] <= r[3];
    let take = inside;
    if (!take && crossing && bboxOverlap(bb, r, 0)) {
      if (e.t === "text" || e.t === "point") take = true;
      else take = curves(e).some(c => edges.some(ed => intersect(c, ed).length));
    }
    if (take) SK.sel.add("e:" + e.id);
  }
  for (const h of SK.dimHits) {
    const d = SK.doc.dims.find(x => x.id === h.id);
    const a2 = resolveDim(d);
    if (a2 && a2.pos[0] >= r[0] && a2.pos[0] <= r[2] && a2.pos[1] >= r[1] && a2.pos[1] <= r[3]) SK.sel.add("d:" + h.id);
  }
}

function doDrag(e) {
  const D = SK.drag, m = SK.mouse;
  if (!D.moved) {
    const s0 = S(D.start);
    if (Math.abs(m.sx - s0[0]) + Math.abs(m.sy - s0[1]) < 3) return;
    D.moved = true;
    checkpoint();
    D.inv = involvedSet();
    // a spline or ellipse: the points fixed to its ends follow it
    const de = D.kind === "pt" ? entById(D.ref.e) : D.kind === "ent" ? entById(D.id) : null;
    D.att = de && cvAdapter(de) ? curveAttachments(de) : null;
  }
  const p = m.p;
  if (D.kind === "dim") {
    const d = SK.doc.dims.find(x => x.id === D.id);
    const a = resolveDim(d);
    if (!a) return;
    if (d.type === "note") d.pos = add(d.pos, sub(p, D.start));
    else if (d.type === "linear") { d.off = sub(add(a.pos, sub(p, D.start)), mul(add(a.p1, a.p2), 0.5)); d.text_free = true; }
    else if (d.type === "diameter" || d.type === "radius") d.off = add(d.off || [0, 0], sub(p, D.start));
    else if (d.type === "angle") d.rad = Math.max(1e-6, dist(a.c, p));
    D.start = p;
    redraw();
    return;
  }
  if (D.kind === "pt") {
    const e = entById(D.ref.e);
    const sn = snapAt(p, { exclude: new Set([e.id]) });
    SK.snap = sn;
    if (D.inv.has(e.id) && isSolver(e)) solveDrag([{ t: "drag", a: D.ref, v: sn.p }]);
    else { setPt(D.ref, sn.p); if (D.att) followAttached(e, D.att); }
    D.lastSnap = sn;
    redraw();
    return;
  }
  if (D.kind === "ent") {
    const e = entById(D.id), o = D.orig, d = sub(p, D.start);
    if (e.t === "line") {
      if (D.inv.has(e.id)) solveDrag([{ t: "drag", a: { e: e.id, k: "p1" }, v: [o.x1 + d[0], o.y1 + d[1]] }, { t: "drag", a: { e: e.id, k: "p2" }, v: [o.x2 + d[0], o.y2 + d[1]] }]);
      else { e.x1 = o.x1 + d[0]; e.y1 = o.y1 + d[1]; e.x2 = o.x2 + d[0]; e.y2 = o.y2 + d[1]; }
    } else if (e.t === "circle" || e.t === "arc") {
      const r = dist([e.cx, e.cy], p);
      if (D.inv.has(e.id)) solveDrag([{ t: "dragr", e: e.id, v: r }]); else e.r = r;
    } else if (e.t === "point") {
      if (D.inv.has(e.id)) solveDrag([{ t: "drag", a: { e: e.id, k: "p" }, v: [o.x + d[0], o.y + d[1]] }]);
      else { e.x = o.x + d[0]; e.y = o.y + d[1]; }
    }
    else if (e.t === "spline" && D.inv.has(e.id)) solveDrag(o.pts.map((q, i) => ({ t: "drag", a: { e: e.id, k: "v" + i }, v: add(q, d) })));
    else if (e.t === "conic" && D.inv.has(e.id)) solveDrag([["s", [o.x0, o.y0]], ["e", [o.x1, o.y1]], ["t", [o.xt, o.yt]]].map(([k, q]) => ({ t: "drag", a: { e: e.id, k }, v: add(q, d) })));
    else if (e.t === "ellipse" && D.inv.has(e.id)) solveDrag([{ t: "drag", a: { e: e.id, k: "c" }, v: [o.cx + d[0], o.cy + d[1]] }]);
    else if (e.t === "poly" || e.t === "spline") { e.pts = o.pts.map(q => add(q, d)); if (e.pprof) { e.pprof.cx = o.pprof.cx + d[0]; e.pprof.cy = o.pprof.cy + d[1]; } if (D.att) followAttached(e, D.att); }
    else if (e.t === "text" || e.t === "ellipse") { const kx = e.t === "ellipse" ? "cx" : "x", ky = e.t === "ellipse" ? "cy" : "y"; e[kx] = o[kx] + d[0]; e[ky] = o[ky] + d[1]; if (D.att) followAttached(e, D.att); }
    else if (e.t === "conic") { for (const [kx, ky] of [["x0", "y0"], ["x1", "y1"], ["xt", "yt"]]) { e[kx] = o[kx] + d[0]; e[ky] = o[ky] + d[1]; } if (D.att) followAttached(e, D.att); }
    redraw();
  }
}

function solveDrag(extra) {
  extra.forEach(c => c.tag = "drag");
  const S = buildSystem(extra);
  const res = S.solve(30);
  S.write(res.x);
}

function endDrag() {
  const D = SK.drag;
  SK.drag = null;
  if (!D.moved) return;
  if (D.kind === "pt" && D.lastSnap && $("#sk-auto").checked) {
    const e = entById(D.ref.e);
    if (isSolver(e)) autoAt(D.ref, D.lastSnap);
  }
  if (D.kind !== "dim" && ((D.inv && D.inv.size) || (D.att && D.att.length))) {
    if (!solveAll()) msg("Constraints could not be fully satisfied", true);
  }
  SK.snap = null;
  changed(true);
}

function escape() {
  if (SK.includeMode) { setIncludeMode(false); return; }
  if (SK.conPick) { setConPick(null); SK.sel.clear(); redraw(); showProps(); return; }
  if (SK.tool === "spline" && SK.pick.length >= 2) { TOOLS.spline.finish(false); return; }
  if (SK.tool === "conic" && SK.pick.length === 3) { TOOLS.conic.make(0.5); return; }
  if (SK.pick.length) { SK.pick = []; updateHint(); overlay(); return; }
  if (SK.tool !== "select") { setTool("select"); return; }
  SK.sel.clear(); redraw(); showProps();
}

function parseCmd(txt) {
  const t = TOOLS[SK.tool];
  const s = txt.trim().replace(/\s+/g, "");
  if (!s) return;
  const base = t && t.base ? t.base() : null;
  // a number or an arithmetic expression without "," or "<" (those are coordinate and polar inputs)
  const num = !/[,<]/.test(s) && isFinite(numv(s)) ? numv(s) : null;
  if (num !== null && t && t.value && (SK.pick.length || ["offset", "fillet", "chamfer"].includes(SK.tool))) { t.value(num); return; }
  let p = null, m;
  if ((m = /^(@)?([-+]?[\d.]+(?:e[-+]?\d+)?)<([-+]?[\d.]+)$/i.exec(s))) {
    if (!base) return msg("Polar input needs a previous point", true);
    const L = +m[2], A = d2r(+m[3]);
    p = [base[0] + L * Math.cos(A), base[1] + L * Math.sin(A)];
  } else if ((m = /^(@)?([-+]?[\d.]+(?:e[-+]?\d+)?),([-+]?[\d.]+(?:e[-+]?\d+)?)$/i.exec(s))) {
    p = [+m[2], +m[3]];
    if (m[1]) { if (!base) return msg("Relative input needs a previous point", true); p = add(base, p); }
  } else if (num !== null && base) {
    const dir = SK.snap ? unit(sub(SK.snap.p, base)) : [1, 0];
    p = add(base, mul(dir, num));
  } else return msg("Input not recognised: " + txt, true);
  if (!t || SK.tool === "select") return msg("Select a drawing tool first", true);
  Promise.resolve(t.click({ p, kind: null, ref: null }, null, null)).catch(showErr).finally(() => { updateHint(); overlay(); });
}

// keyboard shortcuts: [code, shift] -> action. Default: keys on the left side of the keyboard (mouse in the right
// hand); left-handed option: the same keys mirrored to the right side (KEYS_LEFT)
const KEYS = [
  ["Space", false, "tool:select", "Select"],
  ["KeyQ", false, "tool:line", "Line"],
  ["KeyW", false, "tool:rect", "Rectangle"],
  ["KeyE", false, "tool:circle", "Circle"],
  ["KeyE", true, "tool:ellipse", "Ellipse"],
  ["KeyD", true, "tool:conic", "Conic"],
  ["KeyW", true, "tool:polygon", "Polygon"],
  ["KeyR", false, "tool:arc", "Arc"],
  ["KeyF", true, "tool:spline", "Spline"],
  ["KeyC", true, "seltangent", "Select tangent chain"],
  ["KeyQ", true, "tool:point", "Point"],
  ["KeyT", false, "tool:trim", "Trim"],
  ["KeyT", true, "tool:extend", "Extend"],
  ["KeyG", false, "tool:fillet", "Fillet"],
  ["KeyG", true, "tool:chamfer", "Chamfer"],
  ["KeyB", false, "tool:offset", "Offset"],
  ["KeyB", true, "tool:mirror", "Mirror"],
  ["KeyV", false, "tool:move", "Move"],
  ["KeyV", true, "tool:copy", "Copy"],
  ["KeyR", true, "tool:rotate", "Rotate"],
  ["KeyA", false, "tool:dim", "Dimension"],
  ["KeyS", false, "tool:dimh", "Horizontal dimension"],
  ["KeyD", false, "tool:dimv", "Vertical dimension"],
  ["KeyA", true, "tool:note", "Note"],
  ["KeyS", true, "tool:leader", "Leader note"],
  ["Digit1", false, "con:coincident", "Coincident"],
  ["Digit2", false, "con:horizontal", "Horizontal"],
  ["Digit3", false, "con:vertical", "Vertical"],
  ["Digit4", false, "con:parallel", "Parallel"],
  ["Digit5", false, "con:perpendicular", "Perpendicular"],
  ["Digit6", false, "con:tangent", "Tangent"],
  ["Digit1", true, "con:equal", "Equal"],
  ["Digit2", true, "con:pointon", "Point on object"],
  ["Digit3", true, "con:midpoint", "Midpoint"],
  ["Digit4", true, "con:concentric", "Concentric"],
  ["Digit5", true, "con:symmetric", "Symmetric"],
  ["Digit6", true, "con:fix", "Fix"],
  ["KeyC", false, "construction", "Construction"],
  ["KeyX", false, "delete", "Delete"],
  ["KeyZ", false, "undo", "Undo"],
  ["KeyZ", true, "redo", "Redo"],
  ["KeyF", false, "fit", "Fit"],
];
const KEY_MIRROR = { KeyQ: "KeyP", KeyW: "KeyO", KeyE: "KeyI", KeyR: "KeyU", KeyT: "KeyY", KeyA: "Semicolon", KeyS: "KeyL", KeyD: "KeyK",
                     KeyF: "KeyJ", KeyG: "KeyH", KeyZ: "Slash", KeyX: "Period", KeyC: "Comma", KeyV: "KeyM", KeyB: "KeyN",
                     Digit1: "Digit0", Digit2: "Digit9", Digit3: "Digit8", Digit4: "Digit7", Digit5: "Digit6", Digit6: "Digit5" };
const KEYS_LEFT = KEYS.map(k => [KEY_MIRROR[k[0]] || k[0], k[1], k[2], k[3]]);
function activeKeys() { return leftKeys() ? KEYS_LEFT : KEYS; }
function keyLabel(code, shift) {
  return (shift ? "Shift+" : "") + codeLabel(code);
}
function keyOf(action) {
  const k = activeKeys().find(x => x[2] === action);
  return k ? keyLabel(k[0], k[1]) : "";
}
function skKeyTitles() {
  document.querySelectorAll("#tab-sketch [data-tool]").forEach(b => setKeyTitle(b, keyOf("tool:" + b.dataset.tool)));
  document.querySelectorAll("#tab-sketch [data-con]").forEach(b => setKeyTitle(b, keyOf("con:" + b.dataset.con)));
  setKeyTitle($("#sk-fit"), keyOf("fit"));
}
window.SHORTCUTS.push({ tab: "Sketch", rows: () => activeKeys().map(k => [keyLabel(k[0], k[1]), k[3]])
  .concat([["Esc", "End / cancel, then Select"], ["Delete", "Delete"], ["Ctrl+Z / Ctrl+Y", "Undo / Redo"]]) });
function runAction(a) {
  if (a.startsWith("tool:")) return setTool(a.slice(5));
  if (a.startsWith("con:")) return applyConstraint(a.slice(4));
  switch (a) {
    case "construction": return toggleConstruction();
    case "delete": return deleteSelection();
    case "seltangent": return selectChain(true);
    case "selchain": return selectChain(false);
    case "undo": return undo();
    case "redo": return redoOp();
    case "fit": return fit();
    case "escape": return escape();
  }
}

function onKey(e) {
  if ($("#tab-sketch").hidden || !SK.doc) return;
  if (!$("#text-dialog").hidden || !$("#value-dialog").hidden) return;
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return;
  const k = e.key;
  if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "z") { e.preventDefault(); undo(); return; }
  if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "y") { e.preventDefault(); redoOp(); return; }
  if ((e.ctrlKey || e.metaKey) && (k === "Enter" || k.toLowerCase() === "e") && SK.partEdit) { e.preventDefault(); endPartEdit(true); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (k === "Escape") { closeMenu(); escape(); return; }
  if (k === "Enter" && SK.tool === "spline" && SK.pick.length >= 2) { e.preventDefault(); TOOLS.spline.finish(false); return; }
  if (k === "Enter" && SK.tool === "conic" && SK.pick.length === 3) { e.preventDefault(); TOOLS.conic.make(0.5); return; }
  if (k === "Delete" || k === "Backspace") { e.preventDefault(); deleteSelection(); return; }
  // a single selected driving dimension: digits start its value, Enter edits it
  const sd = selectedDrivingDim();
  if (sd && SK.tool === "select" && !SK.pick.length) {
    if (/^[0-9.,\-]$/.test(k) && !e.shiftKey) { e.preventDefault(); editDimValue(sd, k); return; }
    if (k === "Enter") { e.preventDefault(); editDimValue(sd); return; }
  }
  // with a drawing tool active, digits and coordinate characters start the command input
  if (/^[0-9@.\-+<,]$/.test(k) && !e.shiftKey && SK.tool !== "select") {
    e.preventDefault();
    const c = $("#sk-cmd"); c.focus(); c.value += k; return;
  }
  const hit = activeKeys().find(x => x[0] === e.code && x[1] === e.shiftKey);
  if (hit) { e.preventDefault(); closeMenu(); runAction(hit[2]); return; }
  if (leftKeys()) return;
  // right-hand aliases
  const alias = { l: "line", p: "point", m: "move", o: "offset", n: "note" }[k.toLowerCase()];
  if (alias && !e.shiftKey) setTool(alias);
}

// ------------------------------------------------------------------ context menu (right click)

function closeMenu() { const m = document.getElementById("sk-menu"); if (m) m.remove(); }

function menuItems() {
  const items = [];
  const t = SK.tool;
  const { pts, es } = selected();
  const lines = es.filter(e => e.t === "line"), circs = es.filter(e => e.t === "circle" || e.t === "arc");
  const nsel = pts.length + es.length;
  if (SK.pick.length || t !== "select") {
    items.push(["escape", SK.pick.length ? "End / cancel" : "Select tool", "Esc"]);
    items.push(null);
  }
  if (nsel) {
    const can = {
      coincident: pts.length >= 2 || (pts.length >= 1 && es.length === 1 && (lines.length + circs.length) === 1),
      horizontal: lines.length >= 1 || pts.length === 2,
      vertical: lines.length >= 1 || pts.length === 2,
      parallel: lines.length >= 2,
      perpendicular: lines.length === 2 && es.length === 2,
      tangent: es.length === 2 && circs.length >= 1,
      equal: lines.length >= 2 || circs.length >= 2,
      pointon: pts.length >= 1 && es.length === 1 && (lines.length + circs.length) === 1,
      midpoint: pts.length === 1 && lines.length === 1,
      concentric: circs.length >= 2 || (circs.length === 1 && es.length === 1 && pts.length >= 1) || (circs.length === 1 && lines.length >= 1 && !pts.length),
      symmetric: pts.length === 2 && lines.length === 1,
      fix: true,
    };
    const cons = Object.keys(can).filter(k => can[k]);
    cons.forEach(k => items.push(["con:" + k, CON_NAMES[k], keyOf("con:" + k)]));
    items.push(null);
    if (lines.length === 2 && es.length === 2) {
      items.push(["tool:fillet", "Fillet", keyOf("tool:fillet")]);
      items.push(["tool:chamfer", "Chamfer", keyOf("tool:chamfer")]);
    }
    if (es.some(e => e.t === "line" || e.t === "arc")) { items.push(["seltangent", "Select tangent chain", keyOf("seltangent")]); items.push(["selchain", "Select connected chain", keyOf("selchain")]); items.push(null); }
    for (const a of ["move", "copy", "rotate", "mirror"]) items.push(["tool:" + a, a[0].toUpperCase() + a.slice(1), keyOf("tool:" + a)]);
    items.push(["construction", "Construction on/off", keyOf("construction")]);
    items.push(["delete", "Delete", keyOf("delete")]);
    items.push(null);
  }
  for (const a of [["line", "Line"], ["rect", "Rectangle"], ["circle", "Circle"], ["arc", "Arc"], ["dim", "Dimension"], ["note", "Note"]]) {
    items.push(["tool:" + a[0], a[1], keyOf("tool:" + a[0])]);
  }
  if (!nsel) {
    for (const a of [["trim", "Trim"], ["extend", "Extend"], ["fillet", "Fillet"], ["chamfer", "Chamfer"], ["offset", "Offset"]]) {
      items.push(["tool:" + a[0], a[1], keyOf("tool:" + a[0])]);
    }
  }
  items.push(null);
  items.push(["undo", "Undo", keyOf("undo")]);
  items.push(["redo", "Redo", keyOf("redo")]);
  items.push(["fit", "Fit", keyOf("fit")]);
  return items;
}

function openMenu(clientX, clientY) {
  closeMenu();
  // right click on an object with nothing selected selects it
  if (!SK.sel.size && SK.tool === "select" && SK.mouse) {
    const gp = gripAt(SK.mouse.p);
    const hit = gp ? null : entityAt(SK.mouse.p);
    if (gp) SK.sel.add(entById(gp.e).t === "point" ? "e:" + gp.e : refKey(gp));
    else if (hit) SK.sel.add("e:" + hit.id);
    if (gp || hit) { redraw(); showProps(); }
  }
  const m = document.createElement("div");
  m.id = "sk-menu";
  m.className = "sk-menu";
  let prevSep = true;
  const html = [];
  for (const it of menuItems()) {
    if (!it) { if (!prevSep) html.push('<div class="sk-menu-sep"></div>'); prevSep = true; continue; }
    html.push(`<button type="button" data-a="${esc(it[0])}"><span>${esc(it[1])}</span><kbd>${esc(it[2] || "")}</kbd></button>`);
    prevSep = false;
  }
  if (prevSep && html.length) html.pop();
  m.innerHTML = html.join("");
  document.body.appendChild(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(clientX, window.innerWidth - r.width - 4) + "px";
  m.style.top = Math.min(clientY, window.innerHeight - r.height - 4) + "px";
  m.querySelectorAll("button").forEach(b => b.onclick = ev => { ev.stopPropagation(); closeMenu(); runAction(b.dataset.a); });
}

function showKeys() {
  const rows = activeKeys().map(k => `<tr><td><kbd>${keyLabel(k[0], k[1])}</kbd></td><td>${esc(k[3])}</td></tr>`).join("");
  closeMenu();
  const m = document.createElement("div");
  m.id = "sk-menu";
  m.className = "sk-menu sk-keys";
  m.innerHTML = `<table>${rows}<tr><td><kbd>Esc</kbd></td><td>End / cancel, then Select</td></tr>` +
    `<tr><td><kbd>Delete</kbd></td><td>Delete</td></tr><tr><td><kbd>Ctrl+Z</kbd> / <kbd>Ctrl+Y</kbd></td><td>Undo / Redo</td></tr></table>` +
    `<p class="hint">Constraint keys ${leftKeys() ? "0 to 5" : "1 to 6"} work with the Select tool. With a drawing tool active, digits${leftKeys() ? ", . and ," : ""} start the coordinate input.</p>`;
  document.body.appendChild(m);
  const b = $("#sk-keys").getBoundingClientRect();
  m.style.left = Math.max(4, Math.min(b.left, window.innerWidth - m.getBoundingClientRect().width - 4)) + "px";
  m.style.top = (b.bottom + 4) + "px";
}

function fit() {
  if (!SK.doc) return;
  if (SK.partEdit && !SK.partEdit.drawing) return fitAll();
  let b;
  if (sheetOn() && SK.sheetData) {
    const sc = sketchScale(), o = SK.doc.sheet.origin || [0, 0], sz = SK.sheetData.size;
    b = [o[0], o[1], o[0] + sz[0] / sc, o[1] + sz[1] / sc];
  } else b = extents(true) || [0, 0, 200, 140];
  const [x0, y0, x1, y1] = b;
  const W = $("#sk-canvas").clientWidth || 800, H = $("#sk-canvas").clientHeight || 500;
  const w = Math.max(x1 - x0, 1e-6), h = Math.max(y1 - y0, 1e-6);
  SK.view.s = Math.min((W - 60) / w, (H - 60) / h);
  SK.view.ox = W / 2 - (x0 + x1) / 2 * SK.view.s;
  SK.view.oy = H / 2 + (y0 + y1) / 2 * SK.view.s;
  redraw();
}

// ------------------------------------------------------------------ dialogs

function askValue(title, initial, text) {
  return new Promise(resolve => {
    const dlg = $("#value-dialog"), inp = $("#value-dialog-input");
    $("#value-dialog-title").textContent = title;
    inp.value = initial === undefined || initial === null ? "" : initial;
    dlg.hidden = false;
    setTimeout(() => { inp.focus(); inp.select(); }, 0);
    const done = v => {
      dlg.hidden = true;
      $("#value-dialog-ok").onclick = $("#value-dialog-cancel").onclick = inp.onkeydown = null;
      resolve(v);
    };
    const ok = () => {
      if (text) return done(inp.value.trim() || null);
      const v = numv(inp.value.replace(",", "."));
      done(isFinite(v) ? v : null);
    };
    $("#value-dialog-ok").onclick = ok;
    $("#value-dialog-cancel").onclick = () => done(null);
    inp.onkeydown = e => {
      if (e.key === "Enter") { e.preventDefault(); ok(); }
      if (e.key === "Escape") { e.preventDefault(); done(null); }
    };
  });
}

/** Screen position (svg coordinates) of the text of a dimension, or null. */
function dimTextScreen(dId) {
  const h = SK.dimHits.find(x => x.id === dId);
  if (!h) return null;
  const g = h.gs.find(x => x.t === "text");
  if (!g) return null;
  return S([g.p[0] / h.k, g.p[1] / h.k]);
}

/** Value input placed in the sketch view at a screen position. Enter applies, Escape or a click elsewhere cancels. */
function askValueAt(initial, sx, sy, selectAll) {
  const box = $("#sk-canvas");
  if (!box) return askValue("Dimension value", initial);
  const old = box.querySelector(".sk-inline");
  if (old) old.remove();
  return new Promise(resolve => {
    const inp = document.createElement("input");
    inp.type = "text"; inp.className = "sk-inline";
    inp.value = initial === undefined || initial === null ? "" : initial;
    const w = box.clientWidth, hh = box.clientHeight;
    inp.style.left = Math.max(4, Math.min(w - 96, sx - 44)) + "px";
    inp.style.top = Math.max(4, Math.min(hh - 30, sy - 22)) + "px";
    box.appendChild(inp);
    let closed = false;
    const done = v => { if (closed) return; closed = true; inp.remove(); box.focus({ preventScroll: true }); resolve(v); };
    inp.onkeydown = e => {
      e.stopPropagation();
      if (e.key === "Enter") { e.preventDefault(); const v = numv(inp.value.replace(",", ".")); done(isFinite(v) ? v : null); }
      if (e.key === "Escape") { e.preventDefault(); done(null); }
    };
    inp.onblur = () => setTimeout(() => done(null), 0);
    setTimeout(() => { inp.focus(); if (selectAll) inp.select(); else inp.setSelectionRange(inp.value.length, inp.value.length); }, 0);
  });
}

/** The selected driving dimension when it is the only selected item, else null. */
function selectedDrivingDim() {
  if (SK.sel.size !== 1) return null;
  const q = parseSel([...SK.sel][0]);
  if (q.kind !== "d") return null;
  const d = SK.doc.dims.find(x => x.id === q.id);
  return d && d.driving ? d : null;
}

/** Value of a driving dimension: input at the dimension text. `initial` undefined: the current value, selected. */
async function editDimValue(d, initial) {
  if (!d || !d.driving) return;
  const q = dimTextScreen(d.id);
  const v = q ? await askValueAt(initial === undefined ? fmtN(d.value, 4) : initial, q[0], q[1], initial === undefined) : await askValue("Dimension value", initial === undefined ? fmtN(d.value, 4) : initial);
  if (v !== null && Math.abs(v - d.value) > 1e-12) setDimValue(d, v);
}

// ------------------------------------------------------------------ properties panel

const TYPE_NAMES = { line: "Line", circle: "Circle", arc: "Arc", point: "Point", poly: "Polyline", text: "Text", ellipse: "Ellipse", spline: "Spline", conic: "Conic" };
const CON_NAMES = { coincident: "Coincident", horizontal: "Horizontal", vertical: "Vertical", parallel: "Parallel", perpendicular: "Perpendicular",
                    tangent: "Tangent", equal: "Equal", pointon: "Point on object", midpoint: "Midpoint", concentric: "Concentric",
                    symmetric: "Symmetric", fix: "Fix" };
const STD_LT = ["Continuous", "DASHED", "HIDDEN", "CENTER", "PHANTOM", "DASHDOT", "DOT"];

function ltOptions(cur, byLayer) {
  const names = [...new Set([...STD_LT, ...(SK.doc.linetypes || []).map(l => l.name)])];
  const opts = (byLayer ? ["ByLayer"] : []).concat(names);
  return opts.map(n => `<option${(cur || (byLayer ? "ByLayer" : "Continuous")).toUpperCase() === n.toUpperCase() ? " selected" : ""}>${esc(n)}</option>`).join("");
}
function layerOptions(cur) {
  return SK.doc.layers.map(l => `<option${l.name === cur ? " selected" : ""}>${esc(l.name)}</option>`).join("");
}
function numField(id, label, v, step) {
  return `<label>${label}<input type="text" inputmode="decimal" class="numf" id="${id}" value="${fmtN(v, 6)}"></label>`;
}

function showProps() {
  const box = $("#sk-props");
  renderNext();
  if (!SK.doc) { box.innerHTML = ""; return; }
  const sel = [...SK.sel].map(parseSel);
  const n = SK.doc.entities.length;
  if (!sel.length) {
    box.innerHTML = `<p class="hint">Nothing selected. ${n} entities, ${SK.doc.constraints.length} constraints, ${SK.doc.dims.length} dimensions and notes. Units: ${esc(SK.doc.units || "mm")}.</p>` +
      (SK.doc.skipped && Object.keys(SK.doc.skipped).length ? `<p class="hint">Not imported: ${Object.entries(SK.doc.skipped).map(([k, v]) => k + " " + v).join(", ")}</p>` : "");
    return;
  }
  if (sel.length === 1 && sel[0].kind === "d") return dimProps(SK.doc.dims.find(d => d.id === sel[0].id));
  if (sel.length === 1 && sel[0].kind === "c") return conProps(SK.doc.constraints.find(c => c.id === sel[0].id));
  if (sel.length === 1 && sel[0].kind === "e") return entProps(entById(sel[0].id));
  const ids = selectedEntityIds();
  const pts = sel.filter(q => q.kind === "p").length;
  // one entity with some of its own points: the entity's properties
  if (ids.length === 1 && sel.every(q => q.kind === "e" || (q.kind === "p" && q.id === ids[0]))) return entProps(entById(ids[0]));
  box.innerHTML = `<p><strong>${sel.length} selected</strong></p><p class="hint">${ids.length} entities, ${pts} points</p>` +
    (ids.length ? `<label>Layer<select id="skp-layer"><option value="">-</option>${layerOptions("")}</select></label>` : "") +
    `<p class="hint">Constraint buttons use the selected points and entities.</p>`;
  const ls = $("#skp-layer");
  if (ls) ls.onchange = () => { if (!ls.value) return; checkpoint(); ids.forEach(id => entById(id).layer = ls.value); changed(true); };
}

/** Sets solver values of a curve from the properties panel: the edited entity is held and the constrained
 *  geometry follows; the edit is kept when the constraints cannot be satisfied. */
function setCurveVals(e, apply) {
  checkpoint();
  const att = curveAttachments(e);
  apply();
  followAttached(e, att);
  if (involvedSet().has(e.id) && !solveAll([{ t: "fix", e: e.id, vals: entVals(e), tag: "hold" }])) { if (!solveAll()) msg("Constraints could not be fully satisfied", true); }
  changed(true);
}

function entProps(e) {
  if (!e) return;
  const box = $("#sk-props");
  let geo = "";
  if (e.t === "line") {
    const L = dist([e.x1, e.y1], [e.x2, e.y2]), A = r2d(Math.atan2(e.y2 - e.y1, e.x2 - e.x1));
    geo = `<div class="grid2">${numField("skp-x1", "x1", e.x1)}${numField("skp-y1", "y1", e.y1)}${numField("skp-x2", "x2", e.x2)}${numField("skp-y2", "y2", e.y2)}` +
          `${numField("skp-len", "Length", L)}${numField("skp-ang", "Angle (deg)", A)}</div>`;
  } else if (e.t === "circle") {
    geo = `<div class="grid2">${numField("skp-cx", "Centre x", e.cx)}${numField("skp-cy", "Centre y", e.cy)}${numField("skp-r", "Radius", e.r)}${numField("skp-dia", "Diameter", 2 * e.r)}</div>`;
  } else if (e.t === "arc") {
    geo = `<div class="grid2">${numField("skp-cx", "Centre x", e.cx)}${numField("skp-cy", "Centre y", e.cy)}${numField("skp-r", "Radius", e.r)}<span></span>` +
          `${numField("skp-a0", "Start angle (deg)", e.a0)}${numField("skp-a1", "End angle (deg)", e.a1)}</div>`;
  } else if (e.t === "point") {
    geo = `<div class="grid2">${numField("skp-x", "x", e.x)}${numField("skp-y", "y", e.y)}</div>`;
  } else if (e.t === "ellipse") {
    geo = `<div class="grid2">${numField("skp-cx", "Centre x", e.cx)}${numField("skp-cy", "Centre y", e.cy)}${numField("skp-rx", "Half axis 1", e.rx)}${numField("skp-ry", "Half axis 2", e.ry)}${numField("skp-rot", "Rotation (deg)", e.rot || 0)}<span></span>` +
          `${numField("skp-a0", "Start angle (deg)", e.a0 === undefined ? 0 : e.a0)}${numField("skp-a1", "End angle (deg)", e.a1 === undefined ? 0 : e.a1)}</div><p class="hint">Equal start and end angles: closed ellipse. Constraints and dimensions use the centre, the axis ends and the arc ends.</p>`;
  } else if (e.t === "conic") {
    const trimmed = e.t0 !== undefined || e.t1 !== undefined, rho = e.rho === undefined ? 0.5 : e.rho;
    const kind = Math.abs(rho - 0.5) < 1e-9 ? "parabola" : rho < 0.5 ? "ellipse" : "hyperbola";
    geo = `<p class="hint">Conic section (${kind})${trimmed ? ", trimmed to the parameter range " + fmtN(conicRange(e)[0], 3) + " to " + fmtN(conicRange(e)[1], 3) : ""}. Rho 0.5: parabola, below 0.5: ellipse, above 0.5: hyperbola. Constraints and dimensions use the start, the end and the tangent intersection; tangent constraints hold the end directions.</p>` + (trimmed ? `<button type="button" id="skp-untrim" class="small">Restore the whole conic</button>` : "") +
          `<div class="grid2">${numField("skp-x0", "Start x", e.x0)}${numField("skp-y0", "Start y", e.y0)}${numField("skp-x1", "End x", e.x1)}${numField("skp-y1", "End y", e.y1)}${numField("skp-xt", "Tangent intersection x", e.xt)}${numField("skp-yt", "Tangent intersection y", e.yt)}${numField("skp-rho", "Rho", rho)}</div>`;
  } else if (e.t === "text") {
    geo = `<label>Text<textarea id="skp-text" rows="3">${esc(e.text)}</textarea></label><div class="grid2">${numField("skp-x", "x", e.x)}${numField("skp-y", "y", e.y)}${numField("skp-h", "Height", e.h)}${numField("skp-rot", "Rotation (deg)", e.rot || 0)}</div>`;
  } else if (e.t === "poly" && e.pprof) {
    const P = e.pprof;
    if (P.cx === undefined) { P.cx = e.pts.reduce((s, p) => s + p[0], 0) / e.pts.length; P.cy = e.pts.reduce((s, p) => s + p[1], 0) / e.pts.length; }
    const f = (k, label, step) => `<label>${label}<input type="text" inputmode="decimal" class="numf" data-pp="${k}" value="${fmtN(P[k], 4)}"></label>`;
    geo = `<p class="hint">Polygon profile (trochoid), ${e.pts.length} vertices</p><div class="grid2">${f("cx", "Centre x")}${f("cy", "Centre y")}${f("d1", "Nominal diameter d1 (mm)")}${f("e", "Eccentricity e (mm)")}${f("n", "Lobes n", 1)}${f("k", "Lever ratio k")}${f("rot", "Rotation (deg)")}<span></span>` +
          `<label>Outer circle d2 (mm)<input type="text" inputmode="decimal" class="numf" id="skp-pd2" value="${fmtN(P.d1 + 2 * P.e, 4)}"></label><label>Inner circle d3 (mm)<input type="text" inputmode="decimal" class="numf" id="skp-pd3" value="${fmtN(P.d1 - 2 * P.e, 4)}"></label></div>` +
          `<p class="hint">Not solver geometry: no constraints or driving dimensions.</p><button type="button" id="skp-explode" class="small">Explode to lines</button>`;
  } else if (e.t === "spline") {
    const trimmed = e.t0 !== undefined || e.t1 !== undefined;
    let cf = null;
    geo = `<p class="hint">Cubic spline through ${e.pts.length} fit points${trimmed ? ", trimmed to the parameter range " + fmtN(splineRange(e)[0], 3) + " to " + fmtN(splineRange(e)[1], 3) : ""}. Drag a fit point to change the shape. Constraints and dimensions use the fit points; tangent constraints hold the end directions.</p>` + (trimmed ? `<button type="button" id="skp-untrim" class="small">Restore the whole spline</button>` : "") + `<label class="check"><input type="checkbox" id="skp-closed"${e.closed ? " checked" : ""}> Closed</label>` +
          `<div class="grid2">${e.pts.map((p, i) => numField("skp-sx" + i, "Point " + (i + 1) + " x", p[0]) + numField("skp-sy" + i, "Point " + (i + 1) + " y", p[1])).join("")}</div>` +
          `<div class="buttons">` + (!e.closed && (cf = fitConic(splinePolyE(e, 8))) ? `<button type="button" id="skp-toconic" class="small" title="Conic through the spline ends with the end tangents of the spline">Convert to conic (deviation ${fmtN(cf.dev, 3)} mm)</button>` : "") +
          `<button type="button" id="skp-explode" class="small" title="One line per sampled segment">Explode to lines</button></div>`;
  } else if (e.t === "poly") {
    const circ = polyCircle(e.pts, !!e.closed), smooth = polySmooth(e.pts), cfit = !e.closed && e.pts.length >= 3 ? fitConic(e.pts) : null;
    geo = `<p class="hint">${e.pts.length} vertices${e.fill ? ", filled" : ""}${smooth ? ", sampled curve" : ""}. Not solver geometry: convert it for constraints, trim, fillet and profiles.</p><label class="check"><input type="checkbox" id="skp-closed"${e.closed ? " checked" : ""}> Closed</label>` +
          `<div class="buttons">` +
          (circ ? `<button type="button" id="skp-toarc" class="small">Convert to ${circ.closed ? "circle" : "arc"} (R ${fmtN(circ.r, 3)})</button>` : "") +
          (e.pts.length >= 3 ? `<button type="button" id="skp-tospline" class="small">Convert to spline</button>` : "") +
          (cfit ? `<button type="button" id="skp-toconic" class="small" title="Conic through the end points with the end tangents of the polyline">Convert to conic (deviation ${fmtN(cfit.dev, 3)} mm)</button>` : "") +
          `<button type="button" id="skp-explode" class="small" title="One line per segment${smooth ? "; a sampled curve becomes many short lines" : ""}">Explode to lines (${e.closed ? e.pts.length : e.pts.length - 1})</button></div>`;
  }
  const cons = SK.doc.constraints.filter(c => conEnts(c).includes(e.id));
  box.innerHTML = `<p><strong>${TYPE_NAMES[e.t] || e.t}</strong> <span class="hint">${esc(e.id)}</span></p>` +
    `<label>Layer<select id="skp-layer">${layerOptions(e.layer)}</select></label>` +
    `<label>Line type<select id="skp-lt">${ltOptions(e.linetype, true)}</select></label>` +
    `<label class="check"><input type="checkbox" id="skp-constr"${e.constr ? " checked" : ""}> Construction (not exported)</label>` + geo +
    (cons.length ? `<p class="hint">Constraints: ${cons.map(c => `<a href="#" data-con="${esc(c.id)}">${CON_NAMES[c.t]}</a>`).join(", ")}</p>` : "");
  box.querySelectorAll("a[data-con]").forEach(a => a.onclick = ev => { ev.preventDefault(); SK.sel.clear(); SK.sel.add("c:" + a.dataset.con); redraw(); showProps(); });
  $("#skp-layer").onchange = () => { checkpoint(); e.layer = $("#skp-layer").value; changed(true); };
  $("#skp-lt").onchange = () => { checkpoint(); const v = $("#skp-lt").value; if (v === "ByLayer") delete e.linetype; else e.linetype = v; changed(true); };
  $("#skp-constr").onchange = () => { checkpoint(); if ($("#skp-constr").checked) e.constr = true; else delete e.constr; changed(true); };
  const val = id => numv($(id).value);
  const bind = (id, fn) => { const el = $(id); if (el) el.onchange = () => { const v = val(id); if (isFinite(v)) editGeom(e, fn, v); }; };
  if (e.t === "line") {
    bind("#skp-x1", (v) => [{ t: "drag", a: { e: e.id, k: "p1" }, v: [v, e.y1] }]);
    bind("#skp-y1", (v) => [{ t: "drag", a: { e: e.id, k: "p1" }, v: [e.x1, v] }]);
    bind("#skp-x2", (v) => [{ t: "drag", a: { e: e.id, k: "p2" }, v: [v, e.y2] }]);
    bind("#skp-y2", (v) => [{ t: "drag", a: { e: e.id, k: "p2" }, v: [e.x2, v] }]);
    bind("#skp-len", (v) => { const a = Math.atan2(e.y2 - e.y1, e.x2 - e.x1); return [{ t: "drag", a: { e: e.id, k: "p1" }, v: [e.x1, e.y1] }, { t: "drag", a: { e: e.id, k: "p2" }, v: [e.x1 + v * Math.cos(a), e.y1 + v * Math.sin(a)] }]; });
    bind("#skp-ang", (v) => { const L = dist([e.x1, e.y1], [e.x2, e.y2]), a = d2r(v); return [{ t: "drag", a: { e: e.id, k: "p1" }, v: [e.x1, e.y1] }, { t: "drag", a: { e: e.id, k: "p2" }, v: [e.x1 + L * Math.cos(a), e.y1 + L * Math.sin(a)] }]; });
  } else if (e.t === "circle" || e.t === "arc") {
    bind("#skp-cx", (v) => [{ t: "drag", a: { e: e.id, k: "c" }, v: [v, e.cy] }]);
    bind("#skp-cy", (v) => [{ t: "drag", a: { e: e.id, k: "c" }, v: [e.cx, v] }]);
    bind("#skp-r", (v) => v > 0 ? [{ t: "dragr", e: e.id, v }] : null);
    bind("#skp-dia", (v) => v > 0 ? [{ t: "dragr", e: e.id, v: v / 2 }] : null);
    bind("#skp-a0", (v) => [{ t: "drag", a: { e: e.id, k: "s" }, v: arcPt(e, v) }]);
    bind("#skp-a1", (v) => [{ t: "drag", a: { e: e.id, k: "e" }, v: arcPt(e, v) }]);
  } else if (e.t === "point") {
    bind("#skp-x", (v) => [{ t: "drag", a: { e: e.id, k: "p" }, v: [v, e.y] }]);
    bind("#skp-y", (v) => [{ t: "drag", a: { e: e.id, k: "p" }, v: [e.x, v] }]);
  } else if (e.t === "ellipse") {
    const set = (id, k, ok) => { const el = $(id); if (el) el.onchange = () => { const v = val(id); if (isFinite(v) && (!ok || ok(v))) setCurveVals(e, () => { e[k] = v; }); }; };
    set("#skp-cx", "cx"); set("#skp-cy", "cy"); set("#skp-rx", "rx", v => v > 0); set("#skp-ry", "ry", v => v > 0); set("#skp-rot", "rot"); set("#skp-a0", "a0"); set("#skp-a1", "a1");
  } else if (e.t === "conic") {
    const set = (id, k, ok) => { const el = $(id); if (el) el.onchange = () => { const v = val(id); if (isFinite(v) && (!ok || ok(v))) { setCurveVals(e, () => { e[k] = v; }); showProps(); } }; };
    set("#skp-x0", "x0"); set("#skp-y0", "y0"); set("#skp-x1", "x1"); set("#skp-y1", "y1"); set("#skp-xt", "xt"); set("#skp-yt", "yt"); set("#skp-rho", "rho", v => v > 0 && v < 1);
    const ut = $("#skp-untrim"); if (ut) ut.onclick = () => { checkpoint(); delete e.t0; delete e.t1; changed(true); showProps(); };
  } else if (e.t === "text") {
    const set = (id, k) => { $(id).onchange = () => { const v = val(id); if (isFinite(v)) { checkpoint(); e[k] = v; changed(true); } }; };
    set("#skp-x", "x"); set("#skp-y", "y"); set("#skp-h", "h"); set("#skp-rot", "rot");
    $("#skp-text").onchange = () => { checkpoint(); e.text = $("#skp-text").value; changed(true); };
  } else if (e.t === "spline") {
    $("#skp-closed").onchange = () => { checkpoint(); e.closed = $("#skp-closed").checked; delete e.t0; delete e.t1; changed(true); };
    const ut = $("#skp-untrim"); if (ut) ut.onclick = () => { checkpoint(); delete e.t0; delete e.t1; changed(true); showProps(); };
    e.pts.forEach((p, i) => {
      const set = (id, c) => { const el = $(id); if (el) el.onchange = () => { const v = val(id); if (isFinite(v)) setCurveVals(e, () => { p[c] = v; }); }; };
      set("#skp-sx" + i, 0); set("#skp-sy" + i, 1);
    });
    $("#skp-explode").onclick = () => {
      checkpoint();
      for (const c of curves(e)) newEnt("line", { x1: c.a[0], y1: c.a[1], x2: c.b[0], y2: c.b[1], layer: e.layer, linetype: e.linetype });
      SK.doc.entities = SK.doc.entities.filter(x => x.id !== e.id);
      SK.sel.clear();
      changed();
    };
    if ($("#skp-toconic")) $("#skp-toconic").onclick = () => { checkpoint(); const c = convertToConic(e); SK.sel.clear(); if (c) SK.sel.add("e:" + c.id); changed(); };
  } else if (e.t === "poly") {
    const cl = $("#skp-closed");
    if (cl) cl.onchange = () => { checkpoint(); e.closed = cl.checked; changed(true); };
    if (e.pprof) {
      const P = e.pprof;
      const regen = () => { checkpoint(); e.pts = TOOLS.p3g.pts([P.cx, P.cy], d2r(P.rot || 0), P); changed(true); showProps(); };
      box.querySelectorAll("input[data-pp]").forEach(inp => inp.onchange = () => {
        const v = numv(inp.value.replace(",", ".")); if (!isFinite(v)) return;
        const k = inp.dataset.pp;
        if (k === "n") { const same = P.k === P.n; P.n = Math.max(2, Math.round(v)); if (same) P.k = P.n; }
        else if ((k === "d1" || k === "e") && !(v > 0)) return;
        else P[k] = v;
        P.preset = "custom";
        regen();
      });
      const fromD23 = () => { const d2 = numv($("#skp-pd2").value), d3 = numv($("#skp-pd3").value); if (!(d2 > d3) || !(d3 > 0)) return; P.d1 = (d2 + d3) / 2; P.e = (d2 - d3) / 4; regen(); };
      $("#skp-pd2").onchange = fromD23; $("#skp-pd3").onchange = fromD23;
    }
    $("#skp-explode").onclick = () => {
      checkpoint();
      for (const c of curves(e)) newEnt("line", { x1: c.a[0], y1: c.a[1], x2: c.b[0], y2: c.b[1], layer: e.layer, linetype: e.linetype, color: e.color, aci: e.aci });
      SK.doc.entities = SK.doc.entities.filter(x => x.id !== e.id);
      SK.sel.clear();
      changed();
    };
    if ($("#skp-toarc")) $("#skp-toarc").onclick = () => { checkpoint(); const made = convertPoly(e, "arc"); SK.sel.clear(); made.forEach(x => SK.sel.add("e:" + x.id)); changed(); };
    if ($("#skp-tospline")) $("#skp-tospline").onclick = () => { checkpoint(); const made = convertPoly(e, "spline"); SK.sel.clear(); made.forEach(x => SK.sel.add("e:" + x.id)); changed(); };
    if ($("#skp-toconic")) $("#skp-toconic").onclick = () => { checkpoint(); const c = convertToConic(e); SK.sel.clear(); if (c) SK.sel.add("e:" + c.id); changed(); };
  }
}

// geometry edit from the properties panel: edited values held while the other constraints are solved
function editGeom(e, fn, v) {
  const extra = fn(v);
  if (!extra) return;
  checkpoint();
  if (!involvedSet().has(e.id)) {
    for (const c of extra) {
      if (c.t === "drag") setPt(c.a, c.v);
      else if (c.t === "dragr") entById(c.e).r = c.v;
    }
    changed(true);
    return;
  }
  extra.forEach(c => c.tag = "edit");
  const S = buildSystem(extra);
  const res = S.solve();
  if (!res.ok) {
    SK.doc = JSON.parse(SK.undo.pop()); reindex();
    msg("Value not possible with the constraints", true);
  } else S.write(res.x);
  changed(true);
}

function dimProps(d) {
  if (!d) return;
  const box = $("#sk-props");
  if (d.type === "note") {
    box.innerHTML = `<p><strong>${d.anchor ? "Leader note" : "Note"}</strong></p><label>Text<textarea id="skp-note" rows="6">${esc(d.text)}</textarea></label>` +
      `<p class="hint">Enter starts a new line. Applied when the field loses focus.</p>`;
    $("#skp-note").onchange = () => { checkpoint(); d.text = $("#skp-note").value; changed(true); };
    return;
  }
  const a = resolveDim(d);
  const v = a ? measure(a) : null;
  const tol = d.tol || {};
  const canDrive = (() => { const S = new System(); const c = Object.assign({}, dimCon(Object.assign({}, d, { driving: true, value: 1 }))); S.addCon(c); return !S.bad; })();
  const kind = { linear: "Linear dimension", diameter: "Diameter", radius: "Radius", angle: "Angle" }[d.type];
  box.innerHTML = `<p><strong>${kind}</strong> <span class="hint">${v === null ? "" : fmtN(v, 4) + (d.type === "angle" ? " deg" : "")}</span></p>` +
    (canDrive ? `<label class="check"><input type="checkbox" id="skp-driving"${d.driving ? " checked" : ""}> Driving (sets the geometry)</label>` : `<p class="hint">Reference dimension (geometry without constraint support).</p>`) +
    (d.driving ? `<label>Value<input type="text" inputmode="decimal" class="numf" id="skp-value" value="${fmtN(d.value, 6)}"></label>` : "") +
    (d.type === "linear" && !d.l2 ? `<label>Orientation<select id="skp-orient"><option value="a">Aligned</option><option value="h">Horizontal</option><option value="v">Vertical</option></select></label>` : "") +
    (d.type === "diameter" || d.type === "radius" ? `<label>Type<select id="skp-rtype"><option value="diameter">Diameter</option><option value="radius">Radius</option></select></label>` : "") +
    (d.type === "linear" ? `<label class="check"><input type="checkbox" id="skp-dia"${d.dia ? " checked" : ""}> Ø symbol</label>` : "") +
    `<label>Prefix<input type="text" id="skp-prefix" value="${esc(d.prefix || "")}" placeholder="e.g. 4x "></label>` +
    `<label>Text override<input type="text" id="skp-text" value="${esc(d.text || "")}" placeholder="measured value"></label>` +
    (d.type === "linear" ? `<label class="check"><input type="checkbox" id="skp-centred"${d.text_free ? "" : " checked"}> Text centred between extension lines</label>` : "") +
    `<label>Tolerance<select id="skp-tolmode"><option value="none">None (general tolerance)</option><option value="fit">ISO 286 fit</option><option value="sym">Symmetric ±</option><option value="dev">Upper / lower deviation</option></select></label>` +
    `<div id="skp-fitrow" class="grid2"><label>Class<input type="text" id="skp-fit" list="fit-classes" value="${esc(tol.fit || "")}" placeholder="H7"></label>` +
    `<label class="check bottom"><input type="checkbox" id="skp-showdev"${tol.show_dev !== false ? " checked" : ""}> Show deviations</label></div>` +
    `<div id="skp-devrow" class="grid2"><label>Upper (${devUnit()})<input type="text" inputmode="decimal" class="numf" id="skp-plus" value="${devUm(tol.plus)}"></label>` +
    `<label>Lower (${devUnit()})<input type="text" inputmode="decimal" class="numf" id="skp-minus" value="${devUm(tol.minus)}"></label></div>`;
  const tm = $("#skp-tolmode");
  tm.value = tol.mode || "none";
  const vis = () => { $("#skp-fitrow").hidden = tm.value !== "fit"; $("#skp-devrow").hidden = !(tm.value === "dev" || tm.value === "sym"); $("#skp-minus").disabled = tm.value === "sym"; };
  vis();
  if ($("#skp-orient")) $("#skp-orient").value = d.orient || "a";
  if ($("#skp-rtype")) $("#skp-rtype").value = d.type;
  const commit = fn => { checkpoint(); fn(); changed(true); };
  if ($("#skp-driving")) $("#skp-driving").onchange = () => {
    if ($("#skp-driving").checked) {
      checkpoint();
      if (!tryDriving(d)) { SK.undo.pop(); d.driving = false; msg("Not possible: the geometry is already constrained", true); }
      changed(true);
    } else commit(() => { d.driving = false; });
  };
  if ($("#skp-value")) $("#skp-value").onchange = () => { const x = numv($("#skp-value").value); if (isFinite(x)) setDimValue(d, x); };
  if ($("#skp-orient")) $("#skp-orient").onchange = () => commit(() => { d.orient = $("#skp-orient").value; if (d.driving) d.value = measure(resolveDim(d)); });
  if ($("#skp-rtype")) $("#skp-rtype").onchange = () => commit(() => {
    const was = d.type; d.type = $("#skp-rtype").value;
    if (d.driving) d.value = d.type === was ? d.value : (d.type === "diameter" ? d.value * 2 : d.value / 2);
  });
  if ($("#skp-dia")) $("#skp-dia").onchange = () => commit(() => { d.dia = $("#skp-dia").checked; });
  $("#skp-prefix").onchange = () => commit(() => { d.prefix = $("#skp-prefix").value; });
  $("#skp-text").onchange = () => commit(() => { d.text = $("#skp-text").value; });
  if ($("#skp-centred")) $("#skp-centred").onchange = () => commit(() => { d.text_free = !$("#skp-centred").checked; });
  const readTol = () => ({ mode: tm.value, fit: $("#skp-fit").value.trim(), show_dev: $("#skp-showdev").checked,
                           plus: devMm($("#skp-plus").value), minus: devMm($("#skp-minus").value) });
  tm.onchange = () => { vis(); commit(() => { d.tol = readTol(); }); };
  ["#skp-fit", "#skp-showdev", "#skp-plus", "#skp-minus"].forEach(id => $(id).onchange = () => commit(() => { d.tol = readTol(); }));
}

function conProps(c) {
  if (!c) return;
  const box = $("#sk-props");
  const names = conEnts(c).map(id => { const e = entById(id); return e ? (TYPE_NAMES[e.t] || e.t) + " " + id : id; });
  box.innerHTML = `<p><strong>${CON_NAMES[c.t] || c.t}</strong></p><p class="hint">${esc([...new Set(names)].join(", "))}</p>` +
    (c.t === "tangent" && c.mode ? `<label>Contact<select id="skp-mode"><option value="ext">External</option><option value="int">Internal</option></select></label>` : "") +
    `<div class="buttons"><button type="button" id="skp-delcon" class="danger">Delete constraint</button></div>`;
  if ($("#skp-mode")) { $("#skp-mode").value = c.mode; $("#skp-mode").onchange = () => { checkpoint(); c.mode = $("#skp-mode").value; if (!solveAll()) { SK.doc = JSON.parse(SK.undo.pop()); msg("Not possible", true); } changed(); }; }
  $("#skp-delcon").onclick = () => { checkpoint(); SK.doc.constraints = SK.doc.constraints.filter(x => x.id !== c.id); SK.sel.clear(); changed(); };
}

// ------------------------------------------------------------------ layers panel

function renderLayers() {
  const box = $("#sk-layers");
  if (!SK.doc) { box.innerHTML = ""; return; }
  box.innerHTML = SK.doc.layers.map((l, i) => {
    const cur = l.name === SK.doc.current_layer;
    const lw = l.lineweight > 0 ? l.lineweight : -1;
    return `<div class="sk-layer${cur ? " cur" : ""}">` +
      `<input type="checkbox" data-i="${i}" data-k="on" title="Visible"${l.on !== false ? " checked" : ""}>` +
      `<input type="radio" name="sk-cur" data-i="${i}" data-k="cur" title="Current layer"${cur ? " checked" : ""}>` +
      `<input type="color" data-i="${i}" data-k="color" value="${/^#[0-9a-f]{6}$/i.test(l.color) ? l.color : "#000000"}" title="Colour">` +
      `<span title="${esc(l.name)}">${esc(l.name)}</span></div>` +
      `<div class="sk-layer"><span></span><span></span><span></span><div class="row" style="margin:0 0 4px;flex-wrap:nowrap">` +
      `<select data-i="${i}" data-k="linetype" style="width:auto;padding:1px 3px;font-size:11px">${ltOptions(l.linetype, false)}</select>` +
      `<select data-i="${i}" data-k="lineweight" style="width:auto;padding:1px 3px;font-size:11px">` +
      [-1, 0.13, 0.18, 0.25, 0.35, 0.5, 0.7, 1.0].map(v => `<option value="${v}"${Math.abs(v - lw) < 1e-6 ? " selected" : ""}>${v < 0 ? "Default" : v + " mm"}</option>`).join("") +
      `</select></div></div>`;
  }).join("");
  box.querySelectorAll("[data-k]").forEach(el => el.onchange = () => {
    const l = SK.doc.layers[+el.dataset.i], k = el.dataset.k;
    if (k === "on") l.on = el.checked;
    else if (k === "cur") SK.doc.current_layer = l.name;
    else if (k === "color") { l.color = el.value; l.aci = null; }
    else if (k === "linetype") l.linetype = el.value;
    else if (k === "lineweight") l.lineweight = numv(el.value);
    SK.dirty = true;
    renderLayers();
    redraw();
  });
}

async function addLayer() {
  const name = await askValue("Layer name", "", true);
  if (!name) return;
  if (SK.doc.layers.some(l => l.name === name)) return msg("Layer exists: " + name, true);
  SK.doc.layers.push({ name, aci: 7, color: "#000000", linetype: "Continuous", lineweight: -1, on: true });
  SK.doc.current_layer = name;
  renderLayers();
}

// ------------------------------------------------------------------ files

function blankSketch(name) {
  return {
    name: name || "sketch", source: "", units: "mm", insunits: 4, scale: 1,
    layers: [
      { name: "0", aci: 7, color: "#000000", linetype: "Continuous", lineweight: -1, on: true },
      { name: "CENTRE", aci: 1, color: "#ff0000", linetype: "CENTER", lineweight: 0.25, on: true },
      { name: "HIDDEN", aci: 3, color: "#00ff00", linetype: "DASHED", lineweight: 0.25, on: true },
    ],
    linetypes: [], current_layer: "0", entities: [], constraints: [], dims: [], next_id: 1,
    sheet: { page: ["A4", "A3", "A2", "A1", "A0"].includes($("#sk-page").value) ? $("#sk-page").value : "A3", title_block: true, origin: [0, 0] },
  };
}

function loadDoc(doc) {
  SK.firstFit = !(doc.entities || []).some(e => !e.axis && e.t !== "text");
  doc.constraints = doc.constraints || [];
  doc.dims = doc.dims || [];
  doc.layers = doc.layers || [];
  doc.next_id = doc.next_id || 1;
  if (!doc.layers.length) doc.layers.push({ name: "0", aci: 7, color: "#000000", linetype: "Continuous", lineweight: -1, on: true });
  if (!doc.layers.some(l => l.name === doc.current_layer)) doc.current_layer = doc.layers[0].name;
  if (!doc.sheet) doc.sheet = { page: ["extents", "A4", "A3", "A2", "A1", "A0"].includes($("#sk-page").value) ? $("#sk-page").value : "A3", title_block: $("#sk-tb").checked, origin: null };
  SK.doc = doc;
  SK.sheetData = null; SK.sheetFitted = false;
  $("#sk-page").value = doc.sheet.page;
  $("#sk-tb").checked = doc.sheet.title_block !== false;
  SK.undo = []; SK.redo = []; SK.sel.clear(); SK.dirty = false;
  reindex();
  $("#sk-name").value = doc.name || "sketch";
  $("#sk-scale").value = scaleText(+doc.scale || 1);
  if (doc.source) $("#sk-folder").value = doc.source.replace(/[\\/][^\\/]*$/, "");
  renderLayers();
  setTool("select");
  updateDof();
  showProps();
  fit();
}

function confirmDiscard() { return !SK.dirty || confirm("Discard the changes to the current sketch?"); }

async function importDxfFile(file) {
  if (!confirmDiscard()) return;
  const fd = new FormData();
  fd.append("file", file);
  busy(true, "Reading " + file.name + "...");
  try {
    const r = await api("/api/sketch/import", { method: "POST", body: fd });
    const doc = await r.json();
    loadDoc(doc);
    msg(`Opened ${file.name}: ${doc.entities.length} entities` + (Object.keys(doc.skipped || {}).length ? ", not imported: " + Object.entries(doc.skipped).map(([k, v]) => k + " " + v).join(", ") : ""));
  } catch (e) { showErr(e); }
  finally { busy(false); }
}

async function importDxfPath() {
  const path = $("#sk-path").value.trim().replace(/^"|"$/g, "");
  if (!path) return;
  if (!confirmDiscard()) return;
  busy(true, "Reading " + path + "...");
  try {
    const r = await postJSON("/api/sketch/import", { path });
    const doc = await r.json();
    loadDoc(doc);
    msg(`Opened ${path}: ${doc.entities.length} entities` + (Object.keys(doc.skipped || {}).length ? ", not imported: " + Object.entries(doc.skipped).map(([k, v]) => k + " " + v).join(", ") : ""));
  } catch (e) { showErr(e); }
  finally { busy(false); }
}

async function refreshList() {
  try {
    const r = await api("/api/sketch/list");
    const names = await r.json();
    $("#sk-list").innerHTML = names.length ? names.map(n => `<option>${esc(n)}</option>`).join("") : '<option value="">(no saved sketches)</option>';
  } catch (e) { /* list is optional */ }
}

window.__sketchLoadNamed = async function (name) { const r = await api("/api/sketch/file/" + encodeURIComponent(name)); loadDoc(await r.json()); refreshList(); };
window.__sketchRefresh = () => refreshList();
window.__sketchCurrent = () => ({ name: (SK.doc && SK.doc.name) || "" });
window.__sk = { SK, fitIfNeeded, fit };

async function loadSaved() {
  const name = $("#sk-list").value;
  if (!name || !confirmDiscard()) return;
  try {
    const r = await api("/api/sketch/file/" + encodeURIComponent(name));
    loadDoc(await r.json());
    msg("Loaded sketch " + name);
  } catch (e) { showErr(e); }
}

async function saveSketch() {
  if (SK.partEdit) return msg("Finish sketch stores this sketch with its " + (SK.partEdit.drawing ? "drawing" : "part"), true);
  SK.doc.name = $("#sk-name").value.trim() || "sketch";
  try {
    const r = await api("/api/sketch/file/" + encodeURIComponent(SK.doc.name), {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(SK.doc) });
    const j = await r.json();
    SK.dirty = false;
    msg("Saved " + j.path);
    refreshList();
  } catch (e) { showErr(e); }
}

function parseScaleText(t) {
  const m = /^\s*([\d.]+)\s*:\s*([\d.]+)\s*$/.exec(t);
  if (m && +m[1] > 0 && +m[2] > 0) return +m[1] / +m[2];
  const v = numv(t);
  return v > 0 ? v : null;
}

async function exportSketch(fmt, overwrite) {
  SK.doc.name = $("#sk-name").value.trim() || "sketch";
  const anns = SK.doc.dims.map(resolveDim).filter(Boolean);
  const page = $("#sk-page").value;
  const req = {
    sketch: SK.doc, annotations: anns, format: fmt,
    pdf: { mode: page === "extents" ? "extents" : "sheet", sheet: page, title_block: $("#sk-tb").checked,
           origin: SK.doc.sheet && SK.doc.sheet.origin },
    fields: readFields(), folder: $("#sk-folder").value.trim(), file_name: SK.doc.name, overwrite: !!overwrite,
  };
  busy(true, "Exporting " + fmt.toUpperCase() + "...");
  try {
    const r = await fetch("/api/sketch/export", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
    if (r.status === 409) {
      const j = await r.json();
      busy(false);
      if (confirm("Overwrite " + j.exists + "?")) return exportSketch(fmt, true);
      busy(true);
      msg("Export cancelled");
      return;
    }
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || r.statusText); }
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("json")) { const j = await r.json(); msg("Wrote " + j.written.join(", ")); return; }
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = SK.doc.name.replace(/[^A-Za-z0-9_\-.]+/g, "_") + "." + fmt;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    msg("Downloaded " + a.download);
  } catch (e) { showErr(e); }
  finally { busy(false); }
}

// ------------------------------------------------------------------ sketch of a part feature

// open a feature sketch from the Part tab; onFinish(sketch) is called with the edited sketch
window.sketchEditForPart = function (sketch, refs, title, onFinish) {
  const saved = SK.doc ? { doc: JSON.stringify(SK.doc), dirty: SK.dirty } : null;
  SK.partEdit = { onFinish, saved };
  SK.hostSheet = null;
  const doc = JSON.parse(JSON.stringify(sketch || blankSketch("feature sketch")));
  doc.sheet = { page: "extents", title_block: false, origin: [0, 0] };
  SK.frameRef = (refs || []).find(e => e.t === "frame") || null;
  SK.refs = (refs || []).filter(e => e.t !== "frame").map((e, i) => Object.assign({ id: "ref" + i, isRef: true, layer: "" }, e));
  if (SK.showProj === undefined) SK.showProj = true;
  if ($("#sk-partproj")) { $("#sk-partproj").checked = SK.showProj; $("#sk-partproj").onchange = () => { SK.showProj = $("#sk-partproj").checked; redraw(); }; }
  showTab("sketch");
  loadDoc(doc);
  ensureAxes();
  reindex(); updateDof(); showProps();
  $("#sk-partbar").hidden = false;
  document.querySelector("#tab-sketch .sk-file").classList.add("collapsed");
  $("#sk-parttitle").textContent = title;
  fitAll();
};

function fitAll() {
  // fit including reference geometry
  // origin markers are excluded: an empty sketch is shown at sketch_view_width_mm (200 mm) centred on the origin
  const b = extents(true);
  let x0 = b ? b[0] : Infinity, y0 = b ? b[1] : Infinity, x1 = b ? b[2] : -Infinity, y1 = b ? b[3] : -Infinity;
  for (const e of SK.refs || []) { if (e.kind === "origin" || e.kind === "axis") continue; const q = bbox(e); x0 = Math.min(x0, q[0]); y0 = Math.min(y0, q[1]); x1 = Math.max(x1, q[2]); y1 = Math.max(y1, q[3]); }
  const minW = (state.cfg && +state.cfg.sketch_view_width_mm) || 200;
  if (!isFinite(x0) || (x1 - x0 < 1e-6 && y1 - y0 < 1e-6)) { const cx = isFinite(x0) ? x0 : 0, cy = isFinite(y0) ? y0 : 0; x0 = cx - minW / 2; x1 = cx + minW / 2; y0 = cy - minW / 2; y1 = cy + minW / 2; }
  const W = $("#sk-canvas").clientWidth || 800, H = $("#sk-canvas").clientHeight || 500;
  const w = Math.max(x1 - x0, 1), h = Math.max(y1 - y0, 1);
  SK.view.s = Math.min((W - 80) / w, (H - 80) / h);
  SK.view.ox = W / 2 - (x0 + x1) / 2 * SK.view.s;
  SK.view.oy = H / 2 + (y0 + y1) / 2 * SK.view.s;
  redraw();
}

// ------------------------------------------------------------------ pattern of the selection
// Copies of the selected entities on a grid: count 1 along direction 1 (dx1, dy1), count 2 along direction 2
// (dx2, dy2), every second row shifted by the row offset along direction 1. The copies carry no constraints.

// polygon profile parameters (P3G tool). Two profile kinds:
//  trochoid: Filemon (1959) / DIN 32711 curve with mean diameter d1, eccentricity e, lobes n, lever ratio k
//  twoarc:   Schaublin K-profile (change-gear bores of the SV13 dividing head, 125, 135): three corner arcs R2
//            centred on an equilateral triangle, three flank arcs R1 = Dm - R2 centred on the opposite corner;
//            constant width Dm. Schaublin: Dm 22 mm, R2 6 mm (R1 16 mm, triangle side 10 mm).
const PPROF = { preset: "p3g", kind: "trochoid", n: 3, k: 3, d1: 14, e: 0.44, Dm: 22, R2: 6 };
const PPROF_PRESETS = {
  p3g: { name: "DIN 32711 P3G (trochoid, k = n = 3)", kind: "trochoid", n: 3, k: 3, e: d1 => Math.round(d1 / 32 * 100) / 100 },
  p4: { name: "4 lobes (trochoid, k = n = 4)", kind: "trochoid", n: 4, k: 4, e: d1 => Math.round(d1 / 40 * 100) / 100 },
  schaublin: { name: "Schaublin K-profile Dm 22, R2 6 (SV13, 125, 135 change gears)", kind: "twoarc", Dm: 22, R2: 6 },
  twoarc: { name: "Two-arc K-profile, custom Dm and R2", kind: "twoarc" },
  custom: { name: "Trochoid, custom n and k", kind: "trochoid" },
};
function pprofSummary() {
  const P = PPROF;
  return P.kind === "twoarc" ? `K-profile Dm ${fmtN(P.Dm, 4)} mm, R2 ${fmtN(P.R2, 4)} mm, R1 ${fmtN(P.Dm - P.R2, 4)} mm` : `trochoid n ${P.n}, k ${fmtN(P.k, 4)}, d1 ${fmtN(P.d1, 4)} mm, e ${fmtN(P.e, 4)} mm`;
}
function pprofForm() {
  const box = $("#sk-props");
  const P = PPROF;
  const f = (k, label, step) => `<label>${label}<input type="text" inputmode="decimal" class="numf" data-pp="${k}" value="${P[k]}"></label>`;
  const tro = P.kind === "trochoid";
  box.innerHTML = `<p><strong>Polygon profile</strong></p>` +
    `<label>Preset<select id="skp-ppreset">${Object.entries(PPROF_PRESETS).map(([k, v]) => `<option value="${k}"${P.preset === k ? " selected" : ""}>${v.name}</option>`).join("")}</select></label>` +
    (tro ? `<div class="grid2">${f("d1", "Nominal diameter d1 (mm)")}${f("e", "Eccentricity e (mm)")}${f("n", "Lobes n", 1)}${f("k", "Lever ratio k")}</div>` +
      `<p class="hint" style="margin-bottom:2px">From a measured profile (k = n): outer circle d2 = d1 + 2e, inner circle d3 = d1 − 2e</p><div class="grid2"><label>Outer circle d2 (mm)<input type="text" inputmode="decimal" class="numf" id="skp-pd2" value="${fmtN(P.d1 + 2 * P.e, 4)}"></label><label>Inner circle d3 (mm)<input type="text" inputmode="decimal" class="numf" id="skp-pd3" value="${fmtN(P.d1 - 2 * P.e, 4)}"></label></div>` +
      `<p class="hint">x = R cos a − e cos a cos na − k e sin na sin a, y = R sin a − e sin a cos na + k e sin na cos a, R = d1/2. k = n gives the DIN P3G curve (equidistant, outer circle d1 + 2e, inner d1 − 2e). Closed polyline; features use it as one periodic spline. Click the centre in the sketch, then a lobe direction.</p>`
      : `<div class="grid2">${f("Dm", "Width Dm (mm, lobe to opposite flank)")}${f("R2", "Corner radius R2 (mm)")}</div>` +
      `<p class="hint">Three corner arcs R2 on an equilateral triangle of side R1 − R2, three flank arcs R1 = Dm − R2 = ${fmtN(P.Dm - P.R2, 4)} mm centred on the opposite corner; constant width Dm. Outer circle ${fmtN(2 * ((P.Dm - 2 * P.R2) / Math.sqrt(3) + P.R2), 3)} mm, inner circle ${fmtN(2 * (P.Dm - P.R2 - (P.Dm - 2 * P.R2) / Math.sqrt(3)), 3)} mm. Created as six arcs with coincident and tangent constraints. Click the centre in the sketch, then a lobe direction.</p>`);
  const refresh = () => { box.querySelectorAll("input[data-pp]").forEach(inp => inp.value = P[inp.dataset.pp]); updateHint(); };
  $("#skp-ppreset").onchange = () => {
    P.preset = $("#skp-ppreset").value; const pr = PPROF_PRESETS[P.preset];
    const kindChanged = pr.kind !== P.kind; P.kind = pr.kind;
    if (pr.n) { P.n = pr.n; P.k = pr.k; P.e = pr.e(P.d1); }
    if (pr.Dm) { P.Dm = pr.Dm; P.R2 = pr.R2; }
    if (kindChanged) pprofForm(); else refresh();
  };
  if (tro) {
    const fromD23 = () => { const d2 = numv($("#skp-pd2").value), d3 = numv($("#skp-pd3").value); if (!(d2 > d3) || !(d3 > 0)) return; P.d1 = (d2 + d3) / 2; P.e = (d2 - d3) / 4; refresh(); };
    $("#skp-pd2").onchange = fromD23; $("#skp-pd3").onchange = fromD23;
  }
  box.querySelectorAll("input[data-pp]").forEach(inp => inp.onchange = () => {
    const v = numv(inp.value.replace(",", ".")); if (!isFinite(v)) return;
    const k = inp.dataset.pp;
    if (k === "n") { const same = P.k === P.n; P.n = Math.max(2, Math.round(v)); if (same) P.k = P.n; }
    else P[k] = v;
    if (k === "d1" && PPROF_PRESETS[P.preset].e) P.e = PPROF_PRESETS[P.preset].e(v);
    if (tro && k !== "d1" && P.preset !== "custom") { P.preset = "custom"; $("#skp-ppreset").value = "custom"; }
    if (!tro && P.preset === "schaublin") { P.preset = "twoarc"; $("#skp-ppreset").value = "twoarc"; }
    if (!tro) pprofForm(); else refresh();
  });
}

const PATTERN = { n1: 3, dx1: 20, dy1: 0, n2: 1, dx2: 0, dy2: 20, row: 0 };
function patternForm() {
  const ids = selectedEntityIds().filter(id => { const e = entById(id); return e && !e.axis; });
  if (!ids.length) return msg("Select the entities to pattern first", true);
  const box = $("#sk-props");
  const P = PATTERN;
  const f = (k, label) => `<label>${label}<input type="text" inputmode="decimal" class="numf" data-pk="${k}" value="${P[k]}"></label>`;
  box.innerHTML = `<p><strong>Pattern</strong> <span class="hint">${ids.length} entities</span></p>` +
    `<div class="grid2">${f("n1", "Count, direction 1")}${f("row", "Row offset (mm, every second row along direction 1)")}</div>` +
    `<div class="grid2">${f("dx1", "Direction 1 dx (mm)")}${f("dy1", "Direction 1 dy (mm)")}</div>` +
    `<div class="grid2">${f("n2", "Count, direction 2")}<span></span></div>` +
    `<div class="grid2">${f("dx2", "Direction 2 dx (mm)")}${f("dy2", "Direction 2 dy (mm)")}</div>` +
    `<div class="buttons"><button type="button" id="skp-pattern" class="primary">Apply</button><button type="button" id="skp-pcancel">Cancel</button></div>` +
    `<p class="hint">Counts include the original. The copies have no constraints.</p>`;
  box.querySelectorAll("input[data-pk]").forEach(inp => inp.onchange = () => { const v = numv(inp.value.replace(",", ".")); if (isFinite(v)) P[inp.dataset.pk] = inp.dataset.pk.startsWith("n") ? Math.max(1, Math.round(v)) : v; });
  $("#skp-pattern").onclick = () => { applyPattern(ids); };
  $("#skp-pcancel").onclick = () => showProps();
  box.querySelector("input[data-pk=n1]").focus();
}
function applyPattern(ids) {
  const P = PATTERN;
  const l1 = Math.hypot(P.dx1, P.dy1) || 1, u1 = [P.dx1 / l1, P.dy1 / l1];
  if (P.n1 * P.n2 < 2) return msg("Count must be at least 2 in one direction", true);
  if (P.n1 > 1 && l1 < 1e-9) return msg("Direction 1 step is zero", true);
  checkpoint();
  let n = 0;
  for (let j = 0; j < P.n2; j++) for (let i = 0; i < P.n1; i++) {
    if (i === 0 && j === 0) continue;
    const sh = j % 2 === 1 ? P.row : 0;
    const d = [P.dx1 * i + P.dx2 * j + u1[0] * sh, P.dy1 * i + P.dy2 * j + u1[1] * sh];
    for (const id of ids) { const c = cloneEnt(entById(id)); xformEnt(c, p => add(p, d)); SK.doc.entities.push(c); n++; }
  }
  changed(true);
  msg(n + " entities created");
}

// ------------------------------------------------------------------ sketch axes as entities
// The x axis, the y axis (construction lines) and the origin (point) are fixed entities of the sketch. They are
// targets of constraints and dimensions and the revolve axis; they are not exported and do not form profiles.

const AXIS_LEN = 1e4;
function axisEnts() { return ents().filter(e => e.axis); }
function ensureAxes() {
  if (!SK.doc || SK.doc.axes === false || axisEnts().length) return false;
  const layer = SK.doc.current_layer || "0";
  const list = [{ id: "axis_x", t: "line", x1: -AXIS_LEN, y1: 0, x2: AXIS_LEN, y2: 0, axis: "x" },
                { id: "axis_y", t: "line", x1: 0, y1: -AXIS_LEN, x2: 0, y2: AXIS_LEN, axis: "y" },
                { id: "axis_o", t: "point", x: 0, y: 0, axis: "o" }];
  for (const e of list) {
    if (entById(e.id)) continue;
    SK.doc.entities.push(Object.assign(e, { layer, constr: true }));
  }
  reindex();
  for (const e of list) {
    if (SK.doc.constraints.some(c => c.t === "fix" && c.e === e.id)) continue;
    SK.doc.constraints.push({ id: "fix_" + e.id, t: "fix", e: e.id, vals: entVals(e) });
  }
  SK.doc.axes = true;
  return true;
}
function removeAxes() {
  const ids = axisEnts().map(e => e.id);
  if (!ids.length) return;
  SK.doc.entities = SK.doc.entities.filter(e => !e.axis);
  removeRefs(ids);
  for (const s of [...SK.sel]) { const q = parseSel(s); if ((q.kind === "e" || q.kind === "p") && ids.includes(q.id)) SK.sel.delete(s); }
}
function toggleAxes() {
  if (!SK.doc) return;
  checkpoint();
  if (axisEnts().length) { removeAxes(); SK.doc.axes = false; msg("Sketch axes removed (constraints and dimensions on them too)"); }
  else { SK.doc.axes = true; ensureAxes(); msg("Sketch axes added: x axis, y axis and origin are fixed construction entities"); }
  const b = $("#sk-axes"); if (b) b.classList.toggle("active", !!axisEnts().length);
  changed();
}
/** Axis entity drawn across the whole view: dash-dot, x red, y green, origin a circle. */
function axisSvg(e, vb, sel) {
  const col = sel ? "#e8590c" : e.axis === "x" ? "#d32f2f" : e.axis === "y" ? "#2e7d32" : "#1d2125";
  if (e.t === "point") { const q = S([e.x, e.y]); return `<circle cx="${N(q[0])}" cy="${N(q[1])}" r="3.5" fill="#fff" stroke="${col}" stroke-width="${sel ? 2 : 1.2}"/>`; }
  const a = e.axis === "x" ? S([vb[0], 0]) : S([0, vb[1]]), b = e.axis === "x" ? S([vb[2], 0]) : S([0, vb[3]]);
  const o = S([0, 0]);
  const lbl = e.axis === "x" ? `<text x="${N(o[0] + 40)}" y="${N(o[1] - 4)}" font-size="11" fill="${col}">x</text>` : `<text x="${N(o[0] + 4)}" y="${N(o[1] - 40)}" font-size="11" fill="${col}">y</text>`;
  return `<line x1="${N(a[0])}" y1="${N(a[1])}" x2="${N(b[0])}" y2="${N(b[1])}" stroke="${col}" stroke-width="${sel ? 2 : 1}" stroke-dasharray="12 4 2 4" stroke-opacity="${sel ? 1 : 0.75}"/>` + lbl;
}

// ------------------------------------------------------------------ include reference geometry
// Reference entities (section of the part, projected edges) are copied into the sketch as fixed entities, so they
// can be used in profiles and as targets of constraints and dimensions. The copies are not associative.

function setIncludeMode(on) {
  SK.includeMode = !!on;
  if (on && SK.tool !== "select") setTool("select");
  const b = $("#sk-include");
  if (b) b.classList.toggle("primary", !!on);
  const asConstr = !$("#sk-includeconstr") || $("#sk-includeconstr").checked;
  msg(on ? "Include: click reference geometry to copy it into the sketch as " + (asConstr ? "fixed construction geometry" : "sketch geometry") + " (Escape ends)" : "");
  redraw();
}

function includeRef(r) {
  const e = JSON.parse(JSON.stringify(r));
  delete e.isRef; delete e.kind;
  e.id = newId("e");
  e.layer = SK.doc.current_layer || "0";
  e.included = true;
  const asConstr = !$("#sk-includeconstr") || $("#sk-includeconstr").checked;
  if (asConstr) e.constr = true;
  SK.doc.entities.push(e);
  reindex();
  // a sampled curve comes as a polyline: an arc, a circle, a spline or lines instead
  const made = e.t === "poly" && !e.fill ? convertPoly(e) : [e];
  for (const x of made) {
    if (asConstr) x.constr = true;
    x.included = true;
    if (asConstr && isSolver(x)) addConstraint({ t: "fix", e: x.id, vals: entVals(x) }, true);
    else if (!asConstr) delete x.included;
  }
  SK.refs = SK.refs.filter(x => x !== r);
  SK.dirty = true;
}

function includeAt(p) {
  const tol = HIT_PX / SK.view.s;
  let best = null, bd = tol;
  for (const r of SK.refs || []) {
    if (!SK.showProj && (r.kind === "proj" || r.kind === "hidden")) continue;
    const d = entDist(r, p);
    if (d <= bd) { bd = d; best = r; }
  }
  if (!best) return;
  checkpoint();
  includeRef(best);
  changed(true);
  msg("Included; click more reference geometry or press Escape");
}

function includeAll(kinds) {
  const list = (SK.refs || []).filter(r => kinds.includes(r.kind));
  if (!list.length) return msg("Nothing to include", true);
  checkpoint();
  for (const r of list) includeRef(r);
  changed(true);
  msg(list.length + " reference entities included");
}

function endPartEdit(apply) {
  const pe = SK.partEdit;
  if (!pe) return;
  if (SK.includeMode) setIncludeMode(false);
  const sk = JSON.parse(JSON.stringify(SK.doc));
  const anns = pe.drawing ? SK.doc.dims.map(resolveDim).filter(Boolean) : null;
  SK.partEdit = null;
  SK.refs = [];
  SK.hostSheet = null;
  $("#sk-partbar").hidden = true;
  $("#sk-includesec").hidden = false;
  document.querySelector("#tab-sketch .sk-file").classList.remove("collapsed");
  if (pe.saved) { loadDoc(JSON.parse(pe.saved.doc)); SK.dirty = pe.saved.dirty; }
  else loadDoc(blankSketch("sketch"));
  showTab(pe.drawing ? "annotate" : "part");
  if (pe.drawing) {
    if (!apply) { pe.onFinish(false); return; }
    // sketch on a drawing: stored with the drawing (work/annotations/<drawing>.sketch.json)
    delete sk.sheet;
    api("/api/drawing/sketch/" + encodeURIComponent(pe.drawing.ann_name) + "/" + pe.drawing.target,
        { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ doc: sk, anns }) })
      .then(() => pe.onFinish(true)).catch(showErr);
    return;
  }
  pe.onFinish(apply ? sk : null);
}

/** Part tab during a feature sketch, else the Drawings tab: the tab button shown active for the Sketch pane. */
window.sketchHostTab = () => (SK.partEdit && !SK.partEdit.drawing ? "part" : "annotate");

/** Sketch on a drawing (Drawings tab, Sketch tool): target "sheet" (paper mm) or a view name (view coordinates,
 *  model mm, the sketch moves with the view). The drawing without this sketch is the sheet; its edges are reference
 *  geometry. onFinish(applied) after the sketch is stored or the edit is cancelled. */
window.sketchEditForDrawing = async function (d, target, label, onFinish) {
  if (SK.partEdit) return msg("Finish the current feature sketch first", true);
  busy(true, "Preparing the sketch...");
  let j;
  try {
    const r = await postJSON("/api/drawing/sketch_base", { selection: [d.selection], settings: readSettings(), fields: readFields(),
                                                           name: d.name, target });
    j = await r.json();
  } catch (e) { busy(false); showErr(e); return; }
  busy(false);
  const saved = SK.doc ? { doc: JSON.stringify(SK.doc), dirty: SK.dirty } : null;
  SK.partEdit = { onFinish, saved, drawing: { ann_name: j.ann_name, target } };
  const doc = JSON.parse(JSON.stringify(j.doc || blankSketch("sketch on " + label)));
  const mp = j.map, f = mp ? mp[2] : 1;
  // paper = (model - origin) * scale; on a view: paper = c + f (x - b)
  doc.scale = f;
  doc.sheet = { page: "host", title_block: false, origin: mp ? [mp[3] - mp[0] / f, mp[4] - mp[1] / f] : [0, 0] };
  doc.name = doc.name || ("sketch on " + label);
  SK.hostSheet = { size: j.size, area: [0, 0, j.size[0], j.size[1]],
                   inner: j.svg.replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "") };
  SK.frameRef = null;
  SK.refs = (j.refs || []).map((e, i) => Object.assign({ id: "ref" + i, isRef: true, layer: "" }, e));
  if (SK.showProj === undefined) SK.showProj = true;
  if ($("#sk-partproj")) { $("#sk-partproj").checked = SK.showProj; $("#sk-partproj").onchange = () => { SK.showProj = $("#sk-partproj").checked; redraw(); }; }
  showTab("sketch");
  SK.sheetData = null;
  loadDoc(doc);
  reindex(); updateDof(); showProps();
  $("#sk-partbar").hidden = false;
  $("#sk-includesec").hidden = true;
  document.querySelector("#tab-sketch .sk-file").classList.add("collapsed");
  $("#sk-parttitle").textContent = "Sketch on " + d.name + ": " + label + (mp ? " (view coordinates, mm)" : " (sheet, mm)");
  fit();
};

// ------------------------------------------------------------------ init

window.sketchShown = function () {
  if (!SK.doc) loadDoc(blankSketch("sketch"));
  else redraw();
  refreshList();
  updateHint();
};

(function bindSketch() {
  document.querySelectorAll("#tab-sketch [data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));
  document.querySelectorAll("#tab-sketch [data-con]").forEach(b => b.onclick = () => {
    if (SK.conPick === b.dataset.con) { setConPick(null); return; }
    if (!SK.sel.size) { if (SK.tool !== "select") setTool("select"); setConPick(b.dataset.con); return; }
    applyConstraint(b.dataset.con);
  });
  $("#sk-new").onclick = () => { if (confirmDiscard()) loadDoc(blankSketch("sketch")); };
  $("#sk-file").onchange = e => { if (e.target.files[0]) importDxfFile(e.target.files[0]); e.target.value = ""; };
  $("#sk-path-open").onclick = importDxfPath;
  $("#sk-path").addEventListener("keydown", e => { if (e.key === "Enter") importDxfPath(); });
  $("#sk-load").onclick = loadSaved;
  $("#sk-save").onclick = saveSketch;
  $("#sk-dxf").onclick = () => exportSketch("dxf");
  $("#sk-pdf").onclick = () => exportSketch("pdf");
  $("#sk-delete").onclick = deleteSelection;
  $("#sk-undo").onclick = undo;
  $("#sk-redo").onclick = redoOp;
  $("#sk-fit").onclick = fit;
  $("#sk-construction").onclick = toggleConstruction;
  $("#sk-layer-add").onclick = addLayer;
  $("#sk-showcon").onchange = redraw;
  $("#sk-page").onchange = () => {
    if (!SK.doc) return;
    SK.doc.sheet.page = $("#sk-page").value; SK.dirty = true; SK.sheetFitted = false;
    if (sheetOn() && !SK.doc.sheet.origin) SK.doc.sheet.origin = null;
    redraw(); if (!sheetOn()) fit();
  };
  $("#sk-tb").onchange = () => { if (!SK.doc) return; SK.doc.sheet.title_block = $("#sk-tb").checked; SK.dirty = true; redraw(); };
  $("#sk-centre").onclick = () => { if (!sheetOn()) return msg("Select a sheet size first", true); centreOnSheet(false); };
  document.getElementById("fields").addEventListener("change", () => { if (!$("#tab-sketch").hidden) redraw(); });
  $("#sk-name").onchange = () => { if (SK.doc) { SK.doc.name = $("#sk-name").value.trim() || "sketch"; SK.dirty = true; } };
  $("#sk-scale").onchange = () => {
    const v = parseScaleText($("#sk-scale").value);
    if (!v) { msg("Scale: e.g. 1:2 or 2:1", true); return; }
    const old = sketchScale();
    if (sheetOn() && SK.doc.sheet.origin && SK.sheetData) {
      // keep the drawing area centre at the same model point
      const a = SK.sheetData.area, o = SK.doc.sheet.origin;
      const c = [o[0] + (a[0] + a[2]) / 2 / old, o[1] + (a[1] + a[3]) / 2 / old];
      SK.doc.sheet.origin = [c[0] - (a[0] + a[2]) / 2 / v, c[1] - (a[1] + a[3]) / 2 / v];
    }
    SK.doc.scale = v; SK.dirty = true; $("#sk-scale").value = scaleText(v); SK.sheetFitted = false; redraw();
  };
  $("#sk-cmd").addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); const v = e.target.value; e.target.value = ""; parseCmd(v); $("#sk-canvas").focus(); }
    if (e.key === "Escape") { e.target.value = ""; $("#sk-canvas").focus(); escape(); }
  });
  document.addEventListener("keydown", onKey);
  window.addEventListener("optionschanged", () => { skKeyTitles(); if (SK.doc) redraw(); });
  $("#sk-axes").onclick = toggleAxes;
  $("#sk-check").onclick = () => showCheck(sketchCheck());
  $("#sk-filetoggle").onclick = () => document.querySelector("#tab-sketch .sk-file").classList.toggle("collapsed");
  $("#sk-pattern").onclick = patternForm;
  $("#sk-partfinish").onclick = () => endPartEdit(true);
  $("#sk-partcancel").onclick = () => endPartEdit(false);
  $("#sk-include").onclick = () => setIncludeMode(!SK.includeMode);
  $("#sk-includesec").onclick = () => includeAll(["section"]);
  $("#sk-includeproj").onclick = () => includeAll(["proj"]);
  document.addEventListener("mousedown", e => { const m = document.getElementById("sk-menu"); if (m && !m.contains(e.target) && e.target.id !== "sk-keys") closeMenu(); });
  $("#sk-keys").onclick = () => { if (document.getElementById("sk-menu")) closeMenu(); else showKeys(); };
  document.querySelectorAll("#tab-sketch [data-tool], #tab-sketch [data-con]").forEach(b => {
    const k = keyOf(b.dataset.tool ? "tool:" + b.dataset.tool : "con:" + b.dataset.con);
    if (k) b.title = (b.title || "") + " [" + k + "]";
  });
  [["#sk-construction", "construction"], ["#sk-delete", "delete"], ["#sk-undo", "undo"], ["#sk-redo", "redo"], ["#sk-fit", "fit"]]
    .forEach(([id, a]) => { const b = $(id); b.title = b.title.replace(/\s*\([^)]*\)\s*$/, "") + " [" + keyOf(a) + "]"; });
  window.addEventListener("resize", () => { if (!$("#tab-sketch").hidden) redraw(); });
  window.addEventListener("beforeunload", e => { if (SK.dirty) { e.preventDefault(); e.returnValue = ""; } });
})();

// solve a sketch record (not the one being edited) with driving dimension values {dimId: value};
// returns {sketch, ok, failed: [dimId]}
function applyDimValues(sketch, values) {
  const saved = SK.doc;
  SK.doc = JSON.parse(JSON.stringify(sketch));
  reindex();
  const failed = [];
  try {
    for (const d of SK.doc.dims) {
      if (d.driving && d.id in values && isFinite(+values[d.id])) d.value = +values[d.id];
    }
    const S0 = buildSystem();
    let res = S0.solve(120);
    if (!res.ok) {
      // retry from a perturbed start (symmetric configurations can stall)
      const x = S0.x.slice();
      for (let i = 0; i < x.length; i++) x[i] += (Math.random() - 0.5) * 1e-3 * Math.max(1, Math.abs(x[i]));
      S0.x = x;
      res = S0.solve(200);
    }
    S0.write(res.x);
    if (!res.ok) for (const d of SK.doc.dims) if (d.driving && d.id in values) failed.push(d.id);
    const out = SK.doc;
    return { sketch: out, ok: res.ok, failed };
  } finally {
    SK.doc = saved;
    reindex();
  }
}

// exposed for tests and for app.js / part.js
Object.assign(window, { SK, S, Minv, redraw, fit, newEnt, reindex, addConstraint, buildSystem, tryDriving, TOOLS,
                        resolveDim, measure, snapAt, updateDof, changed, selected, applyConstraint, askValue, askText, applyDimValues, cutParams, trimAt, trimConstraint, ents, dimAt, evScreen, ellPt, splinePoly, splinePolyE, PPROF, conicPt, conicTan, conicShoulder, fitConic, convertToConic, showProps, filletParam, cvAdapter, dist, arcPt, unit, solveAll, updateDof, entVals, isSolver, sharedEnd, sketchCheck, fixIssues });
})();
