// Time history plots of the Analysis tab (CalculiX history output) and of the explicit pane (OpenCourant time
// history): curves against time in one SVG with axes, a legend, the value at the cursor and a click that picks a
// time; CSV of the curves.

const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
export const COLORS = ["#1f5fae", "#e8590c", "#2f9e44", "#c2255c", "#7048e8", "#0c8599", "#e67700", "#495057"];
const fmt = v => { if (!isFinite(v)) return "-"; const a = Math.abs(v); return a !== 0 && (a < 1e-3 || a >= 1e5) ? v.toExponential(3) : (+v.toPrecision(4)).toString(); };

/** Curves into box: series [{name, unit, t: [s], v: []}]; opts {xlabel, xname (of the value at the cursor, default t),
 *  mark (time of a marker), marks ([{t, title}]: thin vertical lines), ylog (logarithmic value axis; values <= 0 are
 *  drawn at the bottom), xint (integer ticks on the x axis), onPick(t)}. */
export function plot(box, series, opts) {
  opts = opts || {};
  if (!box) return;
  const S = series.filter(s => s.t && s.t.length);
  if (!S.length) { box.innerHTML = `<p class="hint">No values.</p>`; return; }
  const W = Math.max(280, box.clientWidth || 420), H = 240, L = 64, R = 10, T = 10, B = 46 + 14 * Math.ceil(S.length / 2);
  const ts = S.flatMap(s => s.t), vs = S.flatMap(s => s.v).filter(isFinite);
  let x0 = Math.min(...ts), x1 = Math.max(...ts), y0 = Math.min(0, ...vs), y1 = Math.max(0, ...vs);
  if (x1 <= x0) x1 = x0 + 1;
  const ph = H - B;
  const px = v => L + (v - x0) / (x1 - x0) * (W - L - R);
  let py, yticks;
  if (opts.ylog) {
    const pos = vs.filter(v => v > 0);
    const floor = pos.length ? Math.min(...pos) / 10 : 1e-6;
    const lg = v => Math.log10(Math.max(v, floor));
    let l0 = Math.floor(lg(floor)), l1 = Math.ceil(pos.length ? Math.log10(Math.max(...pos)) : 1);
    if (l1 <= l0) l1 = l0 + 1;
    py = v => T + (1 - (lg(v) - l0) / (l1 - l0)) * (ph - T);
    const step = Math.max(1, Math.ceil((l1 - l0) / 6));
    yticks = [];
    for (let e = l0; e <= l1; e += step) yticks.push(Math.pow(10, e));
  } else {
    if (y1 <= y0) y1 = y0 + 1;
    py = v => T + (1 - (v - y0) / (y1 - y0)) * (ph - T);
    yticks = [0, 1, 2, 3, 4].map(k => y0 + (y1 - y0) * k / 4);
  }
  let g = `<svg width="${W}" height="${H}" class="fa-hsvg th-svg">`;
  for (const yv of yticks) g += `<line x1="${L}" x2="${W - R}" y1="${py(yv)}" y2="${py(yv)}" stroke="#e9ecef"/><text x="${L - 4}" y="${py(yv) + 4}" text-anchor="end">${fmt(yv)}</text>`;
  const xticks = [0, 1, 2, 3, 4].map(k => x0 + (x1 - x0) * k / 4);
  for (const xv of opts.xint ? [...new Set(xticks.map(Math.round))] : xticks) {
    g += `<line y1="${T}" y2="${ph}" x1="${px(xv)}" x2="${px(xv)}" stroke="#e9ecef"/><text x="${px(xv)}" y="${ph + 14}" text-anchor="middle">${fmt(xv)}</text>`;
  }
  if (!opts.ylog && y0 < 0 && y1 > 0) g += `<line x1="${L}" x2="${W - R}" y1="${py(0)}" y2="${py(0)}" stroke="#adb5bd"/>`;
  for (const m of opts.marks || []) if (isFinite(m.t)) g += `<line y1="${T}" y2="${ph}" x1="${px(m.t)}" x2="${px(m.t)}" stroke="#ced4da" stroke-dasharray="3 3"><title>${esc(m.title || "")}</title></line>`;
  if (opts.mark !== undefined && opts.mark !== null && isFinite(opts.mark)) g += `<line class="th-mark" y1="${T}" y2="${ph}" x1="${px(opts.mark)}" x2="${px(opts.mark)}" stroke="#f08c00" stroke-width="1.5"/>`;
  S.forEach((s, i) => {
    const c = COLORS[i % COLORS.length];
    g += `<polyline fill="none" stroke="${c}" stroke-width="1.6" points="${s.t.map((t, k) => px(t).toFixed(1) + "," + py(isFinite(s.v[k]) ? s.v[k] : 0).toFixed(1)).join(" ")}"/>`;
    if (s.t.length < 60) s.t.forEach((t, k) => { g += `<circle cx="${px(t).toFixed(1)}" cy="${py(s.v[k]).toFixed(1)}" r="2.2" fill="${c}"/>`; });
    const lx = L + (i % 2) * (W - L) / 2, ly = ph + 42 + 14 * Math.floor(i / 2);       // the legend below the axis label
    g += `<rect x="${lx}" y="${ly - 8}" width="10" height="3" fill="${c}"/><text x="${lx + 14}" y="${ly - 4}">${esc(s.name)}${s.unit ? " (" + esc(s.unit) + ")" : ""}</text>`;
  });
  g += `<text x="${W - R}" y="${ph + 26}" text-anchor="end">${esc(opts.xlabel || "time (s)")}</text>`;
  g += `<rect class="th-hit" x="${L}" y="${T}" width="${W - L - R}" height="${ph - T}" fill="transparent" style="cursor:crosshair"/>`;
  g += `<text class="th-read" x="${L + 4}" y="${T + 12}" pointer-events="none"></text></svg>`;
  box.innerHTML = g;
  const hit = box.querySelector(".th-hit"), read = box.querySelector(".th-read");
  const tAt = e => { const r = hit.getBoundingClientRect(); return x0 + (e.clientX - r.left) / r.width * (x1 - x0); };
  const valAt = (s, t) => {                       // linear between the points
    if (t <= s.t[0]) return s.v[0];
    for (let k = 1; k < s.t.length; k++) if (t <= s.t[k]) { const a = s.t[k - 1], b = s.t[k]; return b > a ? s.v[k - 1] + (s.v[k] - s.v[k - 1]) * (t - a) / (b - a) : s.v[k]; }
    return s.v[s.v.length - 1];
  };
  hit.onmousemove = e => { const t = tAt(e); read.textContent = `${opts.xname || "t"} ${fmt(t)}: ` + S.map(s => fmt(valAt(s, t))).join(", "); };
  hit.onmouseleave = () => { read.textContent = ""; };
  if (opts.onPick) hit.onclick = e => opts.onPick(tAt(e));
}

/** CSV text of curves: a time column per curve (the curves may have different times); xhead: the heading of the
 *  first column of a curve (default time (s)). */
export function csv(series, xhead) {
  const S = series.filter(s => s.t && s.t.length);
  const head = S.flatMap(s => [xhead || "time (s)", `${s.name}${s.unit ? " (" + s.unit + ")" : ""}`].map(h => `"${h.replace(/"/g, "'")}"`)).join(",");
  const n = Math.max(0, ...S.map(s => s.t.length));
  const rows = [];
  for (let k = 0; k < n; k++) rows.push(S.flatMap(s => k < s.t.length ? [s.t[k], s.v[k]] : ["", ""]).join(","));
  return head + "\n" + rows.join("\n") + "\n";
}
/** Downloads text as a file. */
export function download(name, text) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
