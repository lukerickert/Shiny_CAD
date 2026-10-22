// Thread and fastener reference tables (dialog #ref-dialog, data from /api/reference, drawgen/fasteners.py).
(function () {
  const $ = s => document.querySelector(s);
  let DATA = null, tab = "coarse", target = null;     // target: input set by a click in the roughness table
  const f3 = v => v === null || v === undefined ? "–" : (+v).toFixed(3).replace(/\.?0+$/, "");
  const f2 = v => v === null || v === undefined ? "–" : (+v).toFixed(2).replace(/\.?0+$/, "");

  async function load() {
    if (DATA) return DATA;
    const r = await fetch("/api/reference");
    DATA = await r.json();
    return DATA;
  }

  function metricTable(rows, nut) {
    const h = `<tr><th>Thread</th>${nut ? "<th>Nut</th>" : ""}<th>P</th><th>d2 = D2</th><th>d3</th><th>D1</th><th>Tap drill</th><th>h3 ext.</th><th>H1 int.</th><th>R root</th><th>R min ext.</th><th>As mm^2</th><th>6H: D2 min–max</th><th>6H: D1 min–max</th><th>6g: d max–min</th><th>6g: d2 max–min</th><th>6g: d3 max–min</th></tr>`;
    return `<table class="ref-table">${h}` + rows.map(r => {
      const i = r.t6H, e = r.t6g;
      return `<tr><td><b>${r.name}</b></td>${nut ? `<td>${r.nut || ""}</td>` : ""}<td>${f2(r.P)}</td><td>${f3(r.d2)}</td><td>${f3(r.d3)}</td><td>${f3(r.D1)}</td><td>${f2(r.drill)}</td><td>${f3(r.h3)}</td><td>${f3(r.H1)}</td><td>${f3(r.R)}</td><td>${f3(r.Rmin)}</td><td>${r.As}</td>` +
        `<td>${i ? f3(i.D2_min) + " – " + f3(i.D2_max) : "–"}</td><td>${i ? f3(i.D1_min) + " – " + f3(i.D1_max) : "–"}</td>` +
        `<td>${e ? f3(e.d_max) + " – " + f3(e.d_min) : "–"}</td><td>${e ? f3(e.d2_max) + " – " + f3(e.d2_min) : "–"}</td><td>${e ? f3(e.d3_max) + " – " + f3(e.d3_min) : "–"}</td></tr>`;
    }).join("") + `</table>` +
      `<p class="hint">ISO 68-1 profile: H = 0.866 P; d2 = d − 0.6495 P; d3 = d − 1.2269 P; D1 = d − 1.0825 P; external thread depth h3 = 0.6134 P; internal thread depth H1 = 0.5413 P; root radius R = H/6 = 0.1443 P; minimum root radius of the external thread 0.125 P (ISO 965-1). Tap drill per DIN 336 (coarse) or d − P (fine). Limits per ISO 965-1, tolerance classes 6H and 6g; d3 min as in DIN 13-20.</p>`;
  }

  function unTable(rows) {
    const h = `<tr><th>Thread</th><th>TPI</th><th>P mm</th><th>d</th><th>d2 = D2</th><th>d3</th><th>D1</th><th>Tap drill ≈</th><th>h3 ext.</th><th>H1 int.</th><th>R root</th><th>As mm^2</th></tr>`;
    return `<table class="ref-table">${h}` + rows.map(r => `<tr><td><b>${r.name}</b></td><td>${r.tpi}</td><td>${f3(r.P)}</td><td>${f3(r.d)}</td><td>${f3(r.d2)}</td><td>${f3(r.d3)}</td><td>${f3(r.D1)}</td><td>${f2(r.drill)}</td><td>${f3(r.h3)}</td><td>${f3(r.H1)}</td><td>${f3(r.R)}</td><td>${r.As}</td></tr>`).join("") + `</table>` +
      `<p class="hint">ASME B1.1 unified threads, 60° profile as ISO 68-1 (P = 25.4 mm / TPI). Tap drill d − P rounded to 0.1 mm (approximate; the standard numbered and letter drills differ by up to 0.1 mm). Classes 2A/2B (external/internal) are the usual ones; their limits are not tabulated here.</p>`;
  }

  function gTable(rows) {
    const h = `<tr><th>Thread</th><th>TPI</th><th>P mm</th><th>Major d</th><th>Pitch d2</th><th>Minor d1</th><th>Depth h</th><th>Radius r</th><th>Tap drill ≈</th></tr>`;
    return `<table class="ref-table">${h}` + rows.map(r => `<tr><td><b>${r.name}</b></td><td>${r.tpi}</td><td>${f3(r.P)}</td><td>${f3(r.d)}</td><td>${f3(r.d2)}</td><td>${f3(r.d1)}</td><td>${f3(r.h)}</td><td>${f3(r.r)}</td><td>${f2(r.drill)}</td></tr>`).join("") + `</table>` +
      `<p class="hint">ISO 228-1 pipe threads where pressure-tight joints are not made on the threads (G, BSPP), Whitworth form: flank angle 55°, thread depth h = 0.6403 P, crest and root radius r = 0.1373 P. External thread classes A and B, internal thread one class. For a G thread in a Hole feature the tap drill is the minor diameter d1.</p>`;
  }

  function trapTable(rows) {
    const h = `<tr><th>Thread</th><th>P</th><th>ac</th><th>d2 = D2</th><th>d3 ext. minor</th><th>D1 int. minor</th><th>D4 int. major</th><th>h3 = H4 depth</th><th>H1 overlap</th><th>b root width</th><th>R1 max</th><th>R2 max</th></tr>`;
    return `<table class="ref-table">${h}` + rows.map(r => `<tr><td><b>${r.name}</b></td><td>${f2(r.P)}</td><td>${f3(r.ac)}</td><td>${f3(r.d2)}</td><td>${f3(r.d3)}</td><td>${f3(r.D1)}</td><td>${f3(r.D4)}</td><td>${f3(r.h3)}</td><td>${f3(r.H1)}</td><td>${f3(r.b)}</td><td>${f3(r.R1max)}</td><td>${f3(r.R2max)}</td></tr>`).join("") + `</table>` +
      `<p class="hint">ISO 2904 / DIN 103-1, flank angle 30°: d2 = D2 = d − 0.5 P; d3 = d − 2 h3; h3 = H4 = 0.5 P + ac; D1 = d − P; D4 = d + 2 ac; H1 = 0.5 P; root width b = 0.366 P − 0.54 ac; crest clearance ac = 0.15 (P 1.5), 0.25 (P 2–5), 0.5 (P 6–12), 1 (P 14–44); R1 max = 0.5 ac at the crest of the external thread, R2 max = ac at the roots. Tolerances per ISO 2903 (7H/7e, 8H/8e) are not tabulated here.</p>`;
  }

  function holesTable(rows) {
    const h = `<tr><th>Screw</th><th>Tap drill (coarse)</th><th>Clearance fine H12</th><th>medium H13</th><th>coarse H14</th><th>Counterbore ⌀ (DIN 974-1 row 1)</th><th>depth, ISO 4762</th><th>depth, DIN 7984</th><th>Countersink ⌀ × 90°, ISO 10642 (DIN 74 F)</th><th>depth</th><th>Countersink ⌀ × 90°, ISO 7721 head (ISO 15065)</th><th>depth</th></tr>`;
    return `<table class="ref-table">${h}` + rows.map(r => `<tr><td><b>${r.name}</b></td><td>${f2(r.drill)}</td><td>${f2(r.fine)}</td><td>${f2(r.medium)}</td><td>${f2(r.coarse)}</td><td>${f2(r.cb_dia)}</td><td>${f2(r.cb_depth)}</td><td>${f2(r.cb_depth_low)}</td><td>${f2(r.cs_dia)}</td><td>${f2(r.cs_depth)}</td><td>${f2(r.cs15065_dia)}</td><td>${f2(r.cs15065_depth)}</td></tr>`).join("") + `</table>` +
      `<p class="hint">Clearance holes ISO 273. Counterbores DIN 974-1 row 1 (screws without washers), through hole medium; the depth is the head height plus clearance. Countersinks DIN 74 form F (countersunk socket head screws ISO 10642) and ISO 15065 (slotted and cross recess countersunk screws); through hole medium. The same values are the presets of the **Hole** feature in the Part tab.</p>`;
  }

  function tolBox() {
    const d = DATA;
    const sizes = d.coarse.concat(d.fine, d.bearing);
    const opts = sizes.map((r, i) => `<option value="${i}"${r.name === "M6" ? " selected" : ""}>${r.name}</option>`).join("");
    const cls = d.classes.internal.concat(d.classes.external).map(c => `<option>${c}</option>`).join("");
    return `<div class="ref-tol"><label>Thread<select id="ref-size">${opts}</select></label><label>Tolerance class<select id="ref-class">${cls}</select></label><button type="button" id="ref-calc">Limits</button></div><div id="ref-tolout"></div>` +
      `<p class="hint">ISO 965-1. Grade 6 from the tables of the standard; grades 4, 5, 7 and 8 are the grade 6 values multiplied by 0.63, 0.8, 1.25 and 1.6 (the standard rounds its tabulated values). Positions: H, h: no deviation; G: +(15 + 11 P) µm; g: −(15 + 11 P) µm; e: −(50 + 11 P) µm; f: −(30 + 11 P) µm. Pitches below 0.5 mm are not covered.</p>`;
  }

  async function calcTol() {
    const sizes = DATA.coarse.concat(DATA.fine, DATA.bearing);
    const r = sizes[+$("#ref-size").value], cls = $("#ref-class").value;
    const q = await fetch(`/api/reference/tolerance?d=${r.d}&P=${r.P}&cls=${encodeURIComponent(cls)}`);
    const t = await q.json();
    const out = $("#ref-tolout");
    if (!t || t.error) { out.innerHTML = `<p class="hint">${(t && t.error) || "not available"}</p>`; return; }
    if (t.internal) {
      out.innerHTML = `<table class="ref-table"><tr><th>${r.name} – ${cls} (internal)</th><th>min</th><th>max</th></tr>` +
        `<tr><td>Major diameter D</td><td>${f3(t.D_min)}</td><td>–</td></tr><tr><td>Pitch diameter D2</td><td>${f3(t.D2_min)}</td><td>${f3(t.D2_max)}</td></tr><tr><td>Minor diameter D1 (bore before threading: tap drill ${f2(r.drill)})</td><td>${f3(t.D1_min)}</td><td>${f3(t.D1_max)}</td></tr></table>` +
        `<p class="hint">Thread depth H1 = ${f3(r.H1)} mm from D1 to D; pitch ${f2(r.P)} mm.</p>`;
    } else {
      out.innerHTML = `<table class="ref-table"><tr><th>${r.name} – ${cls} (external)</th><th>max</th><th>min</th></tr>` +
        `<tr><td>Major diameter d (turn to)</td><td>${f3(t.d_max)}</td><td>${f3(t.d_min)}</td></tr><tr><td>Pitch diameter d2</td><td>${f3(t.d2_max)}</td><td>${f3(t.d2_min)}</td></tr><tr><td>Minor diameter d3 (root)</td><td>${f3(t.d3_max)}</td><td>${f3(t.d3_min)}</td></tr></table>` +
        `<p class="hint">Thread depth h3 = ${f3(r.h3)} mm; root radius ${f3(r.R)} mm nominal, ${f3(r.Rmin)} mm minimum; pitch ${f2(r.P)} mm.</p>`;
    }
  }

  /** Surface roughness Ra by process: one cell per Ra value of ISO 1302, coloured by the fine, usual or rough
   *  range of the process. With a target field (Guide button of Surface finish) a click on a value sets it. */
  function roughTable() {
    const R = DATA.roughness;
    const vals = R.series.map(s => s[0]);
    const cur = target ? parseRa(target.value) : null;
    const fmt = v => String(+v);
    const inR = (rg, v) => rg && v >= rg[0] - 1e-9 && v <= rg[1] + 1e-9;
    const band = (p, v) => inR(p.usual, v) ? "usual" : inR(p.fine, v) ? "fine" : inR(p.rough, v) ? "rough" : "";
    const sel = v => cur !== null && Math.abs(v - cur) < 1e-9 ? " ra-cur" : "";
    let group = null;
    const rows = R.processes.map(p => {
      const g = p.group !== group ? `<tr class="ra-group"><td colspan="${vals.length + 1}">${p.group}</td></tr>` : "";
      group = p.group;
      return g + `<tr><td>${p.name}</td>` + vals.map(v => { const b = band(p, v); return `<td class="ra-cell${b ? " ra-" + b : ""}${sel(v)}" data-ra="${v}" title="${p.name}: Ra ${fmt(v)} µm${b ? ", " + b : ""}"></td>`; }).join("") + `</tr>`;
    }).join("");
    return (target ? `<p class="hint">Click an Ra value (column) to set <b>Surface finish</b>${cur !== null ? "; current Ra " + fmt(cur) + " µm" : ""}.</p>` : "") +
      `<table class="ref-table ra-table"><tr><th>Process</th>${vals.map(v => `<th class="ra-head${sel(v)}" data-ra="${v}">${fmt(v)}</th>`).join("")}</tr>` +
      `<tr><th>Grade</th>${R.series.map(s => `<th class="ra-head${sel(s[0])}" data-ra="${s[0]}">${s[1]}</th>`).join("")}</tr>${rows}</table>` +
      `<p class="ra-legend"><span class="ra-key ra-fine"></span> fine (careful production) <span class="ra-key ra-usual"></span> usual <span class="ra-key ra-rough"></span> rough</p>` +
      `<p class="hint">Ra in µm; grade numbers N1 to N12 of ISO 1302. ${R.note}</p>`;
  }
  function parseRa(s) { const m = String(s || "").replace(",", ".").match(/(\d+(?:\.\d+)?)/); return m ? +m[1] : null; }
  function bindRough() {
    if (!target) return;
    document.querySelectorAll("#ref-body [data-ra]").forEach(el => {
      el.style.cursor = "pointer";
      el.onclick = () => {
        target.value = "Ra " + String(+el.dataset.ra);
        target.dispatchEvent(new Event("input", { bubbles: true }));
        target.dispatchEvent(new Event("change", { bubbles: true }));
        $("#ref-dialog").hidden = true;
        target = null;
      };
    });
  }

  // ------------------------------------------------------------------ ISO 286 fits
  let FITS = null, fitOpts = null;           // fitOpts: {size, cls, apply(cls)} when opened from a dimension
  const FIT = { size: 25, hole: "H7", shaft: "g6" };
  const um = v => (v > 0 ? "+" : "") + (Math.round(v * 1e4) / 10).toString();
  const mm3 = v => (Math.round(v * 1e4) / 1e4).toFixed(4);

  function fitsHtml() {
    const F = FITS;
    const pref = F.preferred.map((p, i) => `<button type="button" class="small" data-pf="${i}" title="${p.text}">${p.hole}/${p.shaft}</button>`).join("");
    const itHead = Object.keys(F.it).map(g => `<th>IT${g}</th>`).join("");
    let prev = 0;
    const itRows = F.ranges.map((r, i) => {
      const row = `<tr><td>${prev} … ${r}</td>` + Object.keys(F.it).map(g => { const v = F.it[g][i]; return `<td>${+g >= 12 ? +(v / 1000).toFixed(3) : v}</td>`; }).join("") + `</tr>`;
      prev = r;
      return row;
    }).join("");
    return `<div class="fit-calc"><div class="fit-in">` +
      `<label>Nominal size (mm)<input type="text" id="fit-size" class="numf" value="${FIT.size}"></label>` +
      `<label>Hole<input type="text" id="fit-hole" list="fit-holes" value="${FIT.hole}"></label>` +
      `<label>Shaft<input type="text" id="fit-shaft" list="fit-shafts" value="${FIT.shaft}"></label>` +
      `<datalist id="fit-holes">${F.holes.map(c => `<option value="${c}">`).join("")}</datalist><datalist id="fit-shafts">${F.shafts.map(c => `<option value="${c}">`).join("")}</datalist>` +
      `<p class="hint" style="margin:6px 0 2px">Preferred fits (hole basis, shaft basis)</p><div class="fit-pref">${pref}</div>` +
      (fitOpts && fitOpts.apply ? `<div class="buttons" style="margin-top:8px"><button type="button" id="fit-usehole">Use hole class for the dimension</button><button type="button" id="fit-useshaft">Use shaft class for the dimension</button></div>` : "") +
      `</div><div id="fit-out"></div></div>` +
      `<p class="hint" style="margin-top:10px">Hole letters A to U, shaft letters a to u (${F.letters.join(", ")}) for nominal sizes up to 500 mm; H, h, JS and js up to 3150 mm; grades IT1 to IT18. Clearance = hole size − shaft size; a negative clearance is an interference. Hole basis: all holes H (EI = 0), the shaft letter sets the fit; shaft basis: all shafts h (es = 0), the hole letter sets the fit.</p>` +
      `<h3 class="ref-h">Standard tolerance grades (ISO 286-1), IT1 to IT11 in µm, IT12 to IT18 in mm</h3>` +
      `<div class="fa-wide"><table class="ref-table"><tr><th>Nominal size over … to (mm)</th>${itHead}</tr>${itRows}</table></div>` +
      `<p class="hint">Limit deviations from the grades for h, js, H and JS: h: es = 0, ei = −IT; js: es = +IT/2, ei = −IT/2; H: ES = +IT, EI = 0; JS: ES = +IT/2, EI = −IT/2.</p>`;
  }

  function fitDiagram(f) {
    // tolerance zones of hole (blue) and shaft (orange) about the zero line (nominal size), deviations in um
    const vals = [f.hole_upper, f.hole_lower, f.shaft_upper, f.shaft_lower, 0].map(v => v * 1000);
    let hi = Math.max(...vals), lo = Math.min(...vals);
    const pad = Math.max(5, (hi - lo) * 0.15);
    hi += pad; lo -= pad;
    const H = 260, W = 340, y = v => 20 + (hi - v) / (hi - lo) * (H - 40);
    const step = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000].find(s => (hi - lo) / s <= 10) || 5000;
    let ticks = "";
    for (let t = Math.ceil(lo / step) * step; t <= hi; t += step)
      ticks += `<line x1="46" x2="52" y1="${y(t)}" y2="${y(t)}" stroke="#555"/><text x="42" y="${y(t) + 4}" text-anchor="end" font-size="11">${t > 0 ? "+" + t : t}</text>`;
    const box = (x, u, l, col, lab) => `<rect x="${x}" y="${y(u * 1000)}" width="90" height="${Math.max(1, y(l * 1000) - y(u * 1000))}" fill="${col}" stroke="#333"/>` +
      `<text x="${x + 45}" y="${(y(u * 1000) + y(l * 1000)) / 2 + 4}" text-anchor="middle" font-size="12" font-weight="600">${lab}</text>` +
      `<text x="${x + 96}" y="${y(u * 1000) + 4}" font-size="11">${um(u)}</text><text x="${x + 96}" y="${y(l * 1000) + 4}" font-size="11">${um(l)}</text>`;
    return `<svg width="${W}" height="${H}" class="fit-svg"><line x1="52" x2="52" y1="14" y2="${H - 14}" stroke="#555"/>${ticks}` +
      `<line x1="52" x2="${W - 6}" y1="${y(0)}" y2="${y(0)}" stroke="#111" stroke-width="1.5"/><text x="${W - 8}" y="${y(0) - 4}" text-anchor="end" font-size="11">0 (${f.size} mm)</text>` +
      box(70, f.hole_upper, f.hole_lower, "#5b8fd9", f.size + f.hole) + box(205, f.shaft_upper, f.shaft_lower, "#f0a848", f.size + f.shaft) +
      `<text x="6" y="12" font-size="11">µm</text></svg>`;
  }

  async function calcFit() {
    FIT.size = numv($("#fit-size").value) || FIT.size;
    FIT.hole = $("#fit-hole").value.trim();
    FIT.shaft = $("#fit-shaft").value.trim();
    const out = $("#fit-out");
    try {
      const r = await fetch("/api/fits/calc", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(FIT) });
      const f = await r.json();
      if (!r.ok || f.error) { out.innerHTML = `<p class="as-bad">${f.error || r.statusText}</p>`; return; }
      const kind = { clearance: "Clearance fit", transition: "Transition fit", interference: "Interference fit" }[f.kind];
      const cl = (v, a, b) => v >= 0 ? `${a} ${mm3(v)} mm` : `${b} ${mm3(-v)} mm`;
      out.innerHTML = `<div class="fit-res">${fitDiagram(f)}<div><p><b>${f.size} ${f.hole}/${f.shaft}: ${kind}</b></p>` +
        `<table class="ref-table"><tr><th></th><th>Upper deviation</th><th>Lower deviation</th><th>Maximum size</th><th>Minimum size</th><th>Tolerance</th></tr>` +
        `<tr><td>Hole ${f.hole}</td><td>${um(f.hole_upper)} µm</td><td>${um(f.hole_lower)} µm</td><td>${mm3(f.hole_max)}</td><td>${mm3(f.hole_min)}</td><td>${um(f.hole_it).replace("+", "")} µm</td></tr>` +
        `<tr><td>Shaft ${f.shaft}</td><td>${um(f.shaft_upper)} µm</td><td>${um(f.shaft_lower)} µm</td><td>${mm3(f.shaft_max)}</td><td>${mm3(f.shaft_min)}</td><td>${um(f.shaft_it).replace("+", "")} µm</td></tr></table>` +
        `<p>${cl(f.clearance_max, "Maximum clearance", "Minimum interference")}<br>${cl(f.clearance_min, "Minimum clearance", "Maximum interference")}</p></div></div>`;
    } catch (e) { out.innerHTML = `<p class="as-bad">${e.message}</p>`; }
  }

  function bindFits() {
    ["#fit-size", "#fit-hole", "#fit-shaft"].forEach(id => $(id).addEventListener("change", calcFit));
    document.querySelectorAll("#ref-body [data-pf]").forEach(b => b.onclick = () => {
      const p = FITS.preferred[+b.dataset.pf];
      $("#fit-hole").value = p.hole; $("#fit-shaft").value = p.shaft; calcFit();
    });
    const use = cls => { if (fitOpts && fitOpts.apply) { fitOpts.apply(cls); $("#ref-dialog").hidden = true; fitOpts = null; } };
    if ($("#fit-usehole")) $("#fit-usehole").onclick = () => use($("#fit-hole").value.trim());
    if ($("#fit-useshaft")) $("#fit-useshaft").onclick = () => use($("#fit-shaft").value.trim());
    calcFit();
  }

  function render() {
    const box = $("#ref-body");
    document.querySelectorAll("#ref-tabs button").forEach(b => b.classList.toggle("active", b.dataset.ref === tab));
    const dg = window.refDiagrams || {};
    if (tab === "coarse") box.innerHTML = (dg.metric ? dg.metric() : "") + metricTable(DATA.coarse);
    else if (tab === "fine") box.innerHTML = (dg.metric ? dg.metric() : "") + metricTable(DATA.fine);
    else if (tab === "bearing") box.innerHTML = (dg.metric ? dg.metric() : "") + metricTable(DATA.bearing, true);
    else if (tab === "trap") box.innerHTML = (dg.trapezoidal ? dg.trapezoidal() : "") + trapTable(DATA.trapezoidal);
    else if (tab === "unc") box.innerHTML = (dg.metric ? dg.metric() : "") + unTable(DATA.unc);
    else if (tab === "unf") box.innerHTML = (dg.metric ? dg.metric() : "") + unTable(DATA.unf);
    else if (tab === "bspp") box.innerHTML = gTable(DATA.bspp);
    else if (tab === "holes") box.innerHTML = (dg.holes ? dg.holes() : "") + holesTable(DATA.holes);
    else if (tab === "rough") { box.innerHTML = roughTable(); bindRough(); }
    else if (tab === "fits") { box.innerHTML = fitsHtml(); bindFits(); }
    else { box.innerHTML = tolBox() + (dg.metric ? dg.metric() : ""); $("#ref-calc").onclick = calcTol; calcTol(); }
  }

  /** Opens the reference tables; name: tab to show; field: input set by a click in the roughness table. */
  async function open(name, field, opts) {
    await load();
    if (!FITS) FITS = await (await fetch("/api/fits")).json();
    if (typeof name === "string") tab = name;
    target = field || null;
    fitOpts = opts || null;
    if (fitOpts) {
      if (fitOpts.size > 0) FIT.size = +(+fitOpts.size).toFixed(3);
      const c = (fitOpts.cls || "").trim();
      if (c) { if (/^[A-Z]/.test(c)) FIT.hole = c; else FIT.shaft = c; }
    }
    $("#ref-dialog").hidden = false;
    render();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const btn = $("#ann-reference");
    if (btn) btn.onclick = () => open();
    document.querySelectorAll("#ref-tabs button").forEach(b => b.onclick = () => { if (b.dataset.ref !== "rough") target = null; if (b.dataset.ref !== "fits") fitOpts = null; tab = b.dataset.ref; render(); });
    $("#ref-close").onclick = () => { $("#ref-dialog").hidden = true; target = null; };
    $("#ref-dialog").addEventListener("click", e => { if (e.target.id === "ref-dialog") $("#ref-dialog").hidden = true; });
    document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#ref-dialog").hidden) $("#ref-dialog").hidden = true; });
  });
  window.openReference = open;
})();
