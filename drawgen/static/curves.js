// Material curve and amplitude plots of the Analysis tab (CalculiX and OpenCourant panes, Input file page).
// Material curves: true stress (MPa) against true plastic strain or true total strain (plastic strain + stress / E);
// hyperelastic materials: uniaxial nominal stress against nominal strain (incompressible). Amplitudes: factor
// against time.

import * as TH from "/static/thplot.js";

const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const AMP_ST = {};
const safe = s => String(s || "curve").replace(/[^A-Za-z0-9_\-]+/g, "_");

/** Uniaxial curve of a Neo-Hooke or Mooney-Rivlin material (C10, C01 in MPa): nominal stress against nominal strain
 *  -0.3 to 1, 2 (lambda - lambda^-2) (C10 + C01 / lambda). */
export function hyperCurve(m) {
  const c10 = +m.C10 || 0, c01 = (m.hyper || "neohooke") === "mooney" ? +m.C01 || 0 : 0;
  const ep = [], s = [];
  for (let k = 0; k <= 26; k++) {
    const e = -0.3 + 1.3 * k / 26, l = 1 + e;
    ep.push(e); s.push(2 * (l - 1 / (l * l)) * (c10 + c01 / l));
  }
  return [{ name: "nominal stress", ep, s }];
}

/** Curves of a CalculiX material record (with the library entry lib {curves} when set). */
export function materialEntry(name, m, lib) {
  const law = m.law || "elastic";
  if (law === "hyper") return { name, hyper: true, curves: hyperCurve(m) };
  if (law !== "plastic") return { name, E: +m.E, curves: [] };
  const rows = (m.plastic || []).slice().sort((a, b) => a[1] - b[1]);
  return { name, E: +m.E, curves: rows.length ? [{ name: lib ? "static (library)" : "true stress", ep: rows.map(r => r[1]), s: rows.map(r => r[0]) }] : [] };
}

/** Plot series of an entry: x "plastic" or "total". */
export function series(e, x) {
  if (e.hyper) return e.curves.map(c => ({ name: c.name, unit: "MPa", t: c.ep, v: c.s }));
  return e.curves.map(c => x === "total" && e.E > 0
    ? { name: c.name, unit: "MPa", t: [0, ...c.ep.map((p, k) => p + c.s[k] / e.E)], v: [0, ...c.s] }
    : { name: c.name, unit: "MPa", t: c.ep, v: c.s });
}

/** Material curves into box: entries [{name, E (MPa), hyper, curves: [{name, ep, s}]}]; st {mat, x} is kept by the
 *  caller; opts {empty}. */
export function renderMaterials(box, entries, st, opts) {
  opts = opts || {};
  if (!box) return;
  const E = entries.filter(e => e.curves && e.curves.length);
  if (!E.length) { box.innerHTML = `<p class="hint">${esc(opts.empty || "No material with a plastic or hyperelastic curve.")}</p>`; return; }
  if (!E.some(e => e.name === st.mat)) st.mat = E[0].name;
  st.x = st.x || "plastic";
  const e = E.find(q => q.name === st.mat);
  const xl = e.hyper ? "nominal strain" : st.x === "total" ? "true total strain" : "true plastic strain";
  box.innerHTML = `<div class="row wrap mc-bar"><label class="inline">Curve<select data-mc="mat">${E.map(q => `<option value="${esc(q.name)}"${q.name === e.name ? " selected" : ""}>${esc(q.name)}</option>`).join("")}</select></label>` +
    (e.hyper ? `<span class="hint">uniaxial, incompressible</span>` : `<label class="inline">Strain<select data-mc="x"><option value="plastic"${st.x === "plastic" ? " selected" : ""}>true plastic strain</option>` +
      `<option value="total"${st.x === "total" ? " selected" : ""}>true total strain</option></select></label>`) +
    `<button type="button" class="small" data-mc="csv" title="The curves as CSV">CSV</button></div><div class="mc-plot"></div>`;
  const S = series(e, st.x);
  TH.plot(box.querySelector(".mc-plot"), S, { xlabel: xl, xname: "strain" });
  box.querySelector("[data-mc=mat]").onchange = ev => { st.mat = ev.target.value; renderMaterials(box, entries, st, opts); };
  if (box.querySelector("[data-mc=x]")) box.querySelector("[data-mc=x]").onchange = ev => { st.x = ev.target.value; renderMaterials(box, entries, st, opts); };
  box.querySelector("[data-mc=csv]").onclick = () => TH.download(safe(e.name) + "_curve.csv", TH.csv(S, xl));
}

/** Amplitude curves into box: amps [{name, t: [], v: []}]; opts {xlabel, ylabel (default factor), st: {pick} kept by the
 *  caller (a choice of one curve or all; all by default up to 8 curves)}. */
export function renderAmplitudeCurves(box, amps, opts) {
  opts = opts || {};
  if (!box) return;
  const A = amps.filter(a => a.t && a.t.length);
  if (!A.length) { box.innerHTML = ""; return; }
  const st = opts.st || {}, xl = opts.xlabel || "time (s)";
  if (st.pick === undefined || (st.pick !== "" && !A.some(a => a.name === st.pick))) st.pick = A.length > 8 ? A[0].name : "";
  const S = A.filter(a => !st.pick || a.name === st.pick).map(a => ({ name: a.name, unit: "", t: a.t, v: a.v }));
  box.innerHTML = `<div class="row wrap mc-bar">` + (A.length > 1 ? `<label class="inline">Curve<select data-mc="pick"><option value="">(all)</option>` +
      A.map(a => `<option value="${esc(a.name)}"${a.name === st.pick ? " selected" : ""}>${esc(a.name)}</option>`).join("") + `</select></label>` : "") +
    `<span class="hint">${esc(opts.ylabel || "factor")} against ${esc(xl)}</span><button type="button" class="small" data-mc="csv" title="The curves as CSV">CSV</button></div><div class="mc-plot"></div>`;
  TH.plot(box.querySelector(".mc-plot"), S, { xlabel: xl, xname: opts.xname || "t" });
  if (box.querySelector("[data-mc=pick]")) box.querySelector("[data-mc=pick]").onchange = ev => { st.pick = ev.target.value; renderAmplitudeCurves(box, amps, Object.assign({}, opts, { st })); };
  box.querySelector("[data-mc=csv]").onclick = () => TH.download((opts.csvName || "amplitudes") + ".csv", TH.csv(S, xl));
}

/** Amplitudes of a document (doc.amplitudes [{id, name, points: [[t, factor]]}]) into box: name, points, plot.
 *  host {changed(), rerender(), status(text, err), nid(prefix), hint, xlabel, addId (id of the Add button)}. A deleted amplitude is removed from
 *  the loads and the velocities. */
export function renderAmplitudes(box, doc, host) {
  if (!box) return;
  doc.amplitudes = doc.amplitudes || [];
  const txt = a => (a.points || []).map(p => p.join(", ")).join("\n");
  box.innerHTML = doc.amplitudes.map(a => `<div class="fa-amp" data-amp="${esc(a.id)}"><div class="row"><input type="text" data-ak="name" value="${esc(a.name)}" style="width:110px">` +
      `<button type="button" class="small" data-ak="del" title="Delete">×</button></div>` +
      `<textarea data-ak="points" rows="${Math.min(8, Math.max(3, (a.points || []).length + 1))}" title="One point per line: time (s), factor">${esc(txt(a))}</textarea></div>`).join("") +
    `<div class="row"><button type="button" class="small" data-ak="add"${host.addId ? ` id="${esc(host.addId)}"` : ""}>Add amplitude</button></div>` +
    `<p class="hint">${esc(host.hint || "")}</p><div class="ac-plot"></div>`;
  box.querySelector("[data-ak=add]").onclick = () => {
    doc.amplitudes.push({ id: host.nid("a"), name: "Amplitude " + (doc.amplitudes.length + 1), points: [[0, 0], [1, 1]] });
    host.changed(); host.rerender();
  };
  box.querySelectorAll("[data-amp]").forEach(div => {
    const a = doc.amplitudes.find(x => String(x.id) === div.dataset.amp);
    div.querySelectorAll("[data-ak]").forEach(el => {
      const k = el.dataset.ak;
      if (k === "del") el.onclick = () => {
        doc.amplitudes = doc.amplitudes.filter(x => x !== a);
        for (const l of [...(doc.loads || []), ...(doc.velocities || [])]) if (l.amplitude === a.id) delete l.amplitude;
        host.changed(); host.rerender();
      };
      else el.onchange = () => {
        if (k === "name") a.name = el.value.trim() || a.name;
        else {
          const rows = el.value.split(/\n/).map(r => r.trim()).filter(Boolean).map(r => r.split(/[,;\s]+/).map(Number));
          if (rows.length && rows.every(r => r.length >= 2 && isFinite(r[0]) && isFinite(r[1]))) a.points = rows.map(r => [r[0], r[1]]).sort((p, q) => p[0] - q[0]);
          else { host.status("Amplitude: one point per line, time and factor", true); el.value = txt(a); return; }
        }
        host.changed(); host.rerender();
      };
    });
  });
  renderAmplitudeCurves(box.querySelector(".ac-plot"), doc.amplitudes.map(a => ({ name: a.name, t: (a.points || []).map(p => p[0]), v: (a.points || []).map(p => p[1]) })),
    { xlabel: host.xlabel, st: AMP_ST });
}
