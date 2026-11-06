// Input file page of the Analysis tab and the explicit pane: the contents of a .inp or .rad mesh file in detail
// (server: drawgen/inpinfo.py, POST /api/inp/info) and the search of its nodes and elements (drawgen/inpquery.py,
// POST /api/inp/query); the results are drawn in the view of the pane (host.mark). Select in view picks nodes or
// elements in the view (host.pickAt), restricted to the set or type of the filter; Shift+click adds to the list.

import * as THREE from "three";
import * as CV from "/static/curves.js";

const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const g = (v, d = 4) => {
  if (v === null || v === undefined || v === "") return "-";
  if (typeof v !== "number") return esc(v);
  if (v === 0) return "0";
  const a = Math.abs(v);
  return a < 1e-3 || a >= 1e7 ? v.toExponential(d - 1) : String(+v.toPrecision(d));
};
const CACHE = {};
const OPEN = {};               // open sections (kept while the page is redrawn)
const QS = {};                 // search of each file: {q, res, sel}

const BY = { nodes: [["number", "number"], ["box", "box (x, y, z range)"], ["near", "near a point"], ["set", "node set"], ["type", "of an element type"],
                     ["attached", "of elements"], ["quality", "coincident"]],
             elements: [["number", "number"], ["box", "centroid in a box"], ["near", "centroid near a point"], ["set", "element set"], ["type", "type"],
                        ["attached", "on nodes"], ["quality", "quality"]] };
const CRIT = [["inverted", "inverted (volume <= 0)"], ["aspect", "aspect ratio above"], ["warp", "warping above (deg)"], ["angle", "corner angle below (deg)"],
              ["edge", "shortest edge below (mm)"], ["volume", "volume / area below"]];

/** Points and lines of search results ({points: [[x, y, z]], lines: [[x, y, z, x, y, z]]}) as a group of the view. */
export function marksGroup(m, track) {
  const grp = new THREE.Group();
  const tr = g0 => (track ? track(g0) : g0);
  if ((m.lines || []).length) {
    const g0 = tr(new THREE.BufferGeometry());
    g0.setAttribute("position", new THREE.Float32BufferAttribute(m.lines.flat(), 3));
    const ls = new THREE.LineSegments(g0, new THREE.LineBasicMaterial({ color: 0xff6a00, depthTest: false }));
    ls.renderOrder = 20;
    grp.add(ls);
  }
  if ((m.points || []).length) {
    const g0 = tr(new THREE.BufferGeometry());
    g0.setAttribute("position", new THREE.Float32BufferAttribute(m.points.flat(), 3));
    const pts = new THREE.Points(g0, new THREE.PointsMaterial({ color: 0xff2d00, size: 8, sizeAttenuation: false, depthTest: false }));
    pts.renderOrder = 21;
    grp.add(pts);
  }
  if ((m.focusTris || []).length) {
    const g0 = tr(new THREE.BufferGeometry());
    g0.setAttribute("position", new THREE.Float32BufferAttribute(m.focusTris, 3));
    const fm = new THREE.Mesh(g0, new THREE.MeshBasicMaterial({ color: 0x0055ff, transparent: true, opacity: 0.45, side: THREE.DoubleSide, depthTest: false }));
    fm.renderOrder = 22;
    grp.add(fm);
  }
  if ((m.focusLines || []).length) {
    const g0 = tr(new THREE.BufferGeometry());
    g0.setAttribute("position", new THREE.Float32BufferAttribute(m.focusLines.flat(), 3));
    const ls = new THREE.LineSegments(g0, new THREE.LineBasicMaterial({ color: 0x0033cc, depthTest: false }));
    ls.renderOrder = 23;
    grp.add(ls);
  }
  if (m.focus) {
    const g0 = tr(new THREE.BufferGeometry());
    g0.setAttribute("position", new THREE.Float32BufferAttribute(m.focus, 3));
    const f = new THREE.Points(g0, new THREE.PointsMaterial({ color: 0x0055ff, size: 14, sizeAttenuation: false, depthTest: false }));
    f.renderOrder = 24;
    grp.add(f);
  }
  grp.userData = { kind: "query" };
  return grp;
}

const fileBtn = i => `<button type="button" class="small" data-qline="${i}" title="Show the line of the item in File text">line</button>`;

// ------------------------------------------------------------------ File text: the lines of the file, loaded in
// blocks of 200 lines while scrolled (at most 2000 lines held), Line / Go, Find (text, node or element number) ▲ ▼

const TX = {};                 // per path: {start, lines, total, hl, find, kind}
const BLOCK = 200, HOLD = 2000;
async function textLines(path, start, count) {
  return (await window.postJSON("/api/inp/text", { path, start, count })).json();
}
function lineHtml(n, t, hl, rad) {
  const s = t.trimStart();
  const cls = (rad ? s.startsWith("#") : s.startsWith("**")) ? "cm" : (rad ? s.startsWith("/") : s.startsWith("*")) ? "kw" : "";
  return `<tr data-ln="${n}"${n === hl ? ' class="hl"' : ""}><td class="ln">${n}</td><td class="${cls}">${esc(t) || " "}</td></tr>`;
}
function textHtml(path) {
  const T = TX[path];
  const rad = /\.rad$/i.test(path);
  return `<div class="row wrap ii-bar"><label class="inline">Line<input type="text" data-tx="line" value="${T.hl || ""}" style="width:70px"></label>` +
    `<button type="button" class="small" data-tx="go">Go</button>` +
    `<label class="inline">Find<input type="text" data-tx="find" value="${esc(T.find || "")}" style="width:120px"></label>` +
    `<select data-tx="kind">${[["text", "text"], ["node", "node number"], ["element", "element number"]].map(([v, t]) => `<option value="${v}"${(T.kind || "text") === v ? " selected" : ""}>${t}</option>`).join("")}</select>` +
    `<button type="button" class="small" data-tx="prev" title="Previous line with the text">▲</button><button type="button" class="small" data-tx="next" title="Next line with the text (node or element number: its data line)">▼</button>` +
    `<span class="hint" data-tx="info">lines ${T.start} to ${T.start + T.lines.length - 1} of ${T.total}</span></div>` +
    `<div class="ii-src"><table>${T.lines.map((t, k) => lineHtml(T.start + k, t, T.hl, rad)).join("")}</table></div>`;
}
/** Shows File text of the file at line n (highlighted), opening the section. */
async function gotoLine(box, path, n) {
  const det = box.querySelector('details.ii-sec[data-ii="text"]');
  if (!det) return;
  OPEN.text = true;
  const T = TX[path] = TX[path] || { start: 1, lines: [], total: 0 };
  T.hl = n;
  const j = await textLines(path, Math.max(1, n - 60), 300);
  Object.assign(T, { start: j.start, lines: j.lines, total: j.total });
  if (!det.open) det.open = true;
  drawText(box, path);
  const src = det.querySelector(".ii-src"), tr = det.querySelector(`tr[data-ln="${n}"]`);
  if (src && tr) src.scrollTop = tr.offsetTop - src.clientHeight / 3;
}
function drawText(box, path) {
  const el = box.querySelector(".ii-text");
  if (!el || !TX[path]) return;
  el.innerHTML = textHtml(path);
  bindText(box, path);
}
function bindText(box, path) {
  const el = box.querySelector(".ii-text"), T = TX[path], src = el.querySelector(".ii-src");
  const rad = /\.rad$/i.test(path);
  const info = () => { el.querySelector("[data-tx=info]").textContent = `lines ${T.start} to ${T.start + T.lines.length - 1} of ${T.total}`; };
  let busy = false;
  src.onscroll = async () => {
    if (busy) return;
    const tb = src.querySelector("table");
    if (src.scrollTop < 60 && T.start > 1) {
      busy = true;
      const s0 = Math.max(1, T.start - BLOCK), j = await textLines(path, s0, T.start - s0);
      const h0 = src.scrollHeight;
      tb.insertAdjacentHTML("afterbegin", j.lines.map((t, k) => lineHtml(s0 + k, t, T.hl, rad)).join(""));
      T.lines = j.lines.concat(T.lines); T.start = s0;
      src.scrollTop += src.scrollHeight - h0;
      while (T.lines.length > HOLD) { T.lines.pop(); tb.lastElementChild.remove(); }
      info(); busy = false;
    } else if (src.scrollTop + src.clientHeight > src.scrollHeight - 60 && T.start + T.lines.length - 1 < T.total) {
      busy = true;
      const s0 = T.start + T.lines.length, j = await textLines(path, s0, BLOCK);
      tb.insertAdjacentHTML("beforeend", j.lines.map((t, k) => lineHtml(s0 + k, t, T.hl, rad)).join(""));
      T.lines = T.lines.concat(j.lines);
      while (T.lines.length > HOLD) { const h0 = tb.firstElementChild.offsetHeight; T.lines.shift(); T.start++; tb.firstElementChild.remove(); src.scrollTop -= h0; }
      info(); busy = false;
    }
  };
  const val = k => el.querySelector(`[data-tx=${k}]`).value.trim();
  el.querySelector("[data-tx=go]").onclick = () => { const n = parseInt(val("line"), 10); if (n > 0) gotoLine(box, path, Math.min(n, T.total || n)); };
  el.querySelector("[data-tx=line]").onkeydown = e => { if (e.key === "Enter") el.querySelector("[data-tx=go]").click(); };
  const find = async back => {
    T.find = val("find"); T.kind = el.querySelector("[data-tx=kind]").value;
    if (!T.find) return;
    const from = T.kind === "text" ? (T.hl || (back ? T.total + 1 : 0)) : 0;
    try {
      const j = await (await window.postJSON("/api/inp/text", { path, find: { text: T.find, kind: T.kind, from, back } })).json();
      if (j.line) gotoLine(box, path, j.line);
      else if (window.status) window.status(`File text: ${T.find} not found${T.kind === "text" ? (back ? " above" : " below") + " line " + (T.hl || 1) : ""}`, true);
    } catch (e) { if (window.showErr) window.showErr(e); }
  };
  el.querySelector("[data-tx=next]").onclick = () => find(false);
  el.querySelector("[data-tx=prev]").onclick = () => find(true);
  el.querySelector("[data-tx=find]").onkeydown = e => { if (e.key === "Enter") find(e.shiftKey); };
  src.onclick = e => {
    const tr = e.target.closest("tr[data-ln]");
    if (!tr) return;
    T.hl = +tr.dataset.ln;
    src.querySelectorAll("tr.hl").forEach(x => x.classList.remove("hl"));
    tr.classList.add("hl");
    el.querySelector("[data-tx=line]").value = T.hl;
  };
}
/** File text opened: the first lines (or the lines held before). */
async function openText(box, path) {
  if (!TX[path]) {
    const j = await textLines(path, 1, 300);
    TX[path] = { start: j.start, lines: j.lines, total: j.total, hl: null };
  }
  drawText(box, path);
}

/** Restriction of a pick in the view by the filter: the chosen set or element type. */
const within = q => (q.by === "set" && q.set ? { set: q.set } : q.by === "type" && q.type ? { type: q.type } : null);

function queryHtml(path) {
  const st = QS[path] = QS[path] || { q: { what: "nodes", by: "number", numbers: "", limit: 500 } };
  const q = st.q, info = CACHE[path];
  const inp = (k, ph, w) => `<input type="text" data-qk="${k}" value="${esc(q[k] === undefined || q[k] === null ? "" : q[k])}" placeholder="${esc(ph)}" style="width:${w || 70}px">`;
  const sel = (k, opts) => `<select data-qk="${k}">${opts.map(([v, t]) => `<option value="${esc(v)}"${String(q[k]) === String(v) ? " selected" : ""}>${esc(t)}</option>`).join("")}</select>`;
  let f = "";
  if (q.by === "number" || q.by === "attached") f = inp("numbers", q.by === "attached" ? (q.what === "nodes" ? "element numbers: 5, 10-20" : "node numbers: 5, 10-20") : "numbers: 5, 10-20, 33", 200);
  else if (q.by === "box") f = ["x", "y", "z"].map((c, i) => `${c} ${inp("b" + i, "min", 56)} – ${inp("b" + (i + 3), "max", 56)}`).join(" ");
  else if (q.by === "near") f = `point ${inp("px", "x", 56)}${inp("py", "y", 56)}${inp("pz", "z", 56)} radius ${inp("radius", "mm", 50)} nearest ${inp("nearest", "n", 40)}` +
    `<button type="button" class="small" data-qop="pick" title="Click a point of the model in the view">Pick in view</button>`;
  else if (q.by === "set") f = sel("set", [["", "(choose)"], ...((q.what === "nodes" ? info.nsets : info.elsets).map(x => [x.name, `${x.name} (${q.what === "nodes" ? x.nodes : x.elements})`]))]);
  else if (q.by === "type") f = sel("type", [["", "(choose)"], ...info.element_types.map(t => [t.type, `${t.type} (${t.count})`])]);
  else if (q.by === "quality") f = q.what === "nodes" ? `tolerance ${inp("value", "mm (empty: 1e-6 x diagonal)", 150)}` : sel("criterion", CRIT) + (q.criterion && q.criterion !== "inverted" ? " " + inp("value", "value", 60) : "");
  let h = `<div class="ii-query"><div class="row wrap ii-bar"><b>Search</b>${sel("what", [["nodes", "nodes"], ["elements", "elements"]])}${sel("by", BY[q.what])}</div>` +
    `<div class="row wrap ii-bar">${f}</div><div class="row wrap ii-bar"><button type="button" class="small primary" data-qop="go">Search</button>` +
    `<button type="button" class="small${st.picking ? " active" : ""}" data-qop="sel" title="Click nodes or elements (Search: nodes or elements) in the view; the set or type of the filter restricts the pick; Shift+click adds to the list; Esc stops">${st.picking ? "Stop selecting" : "Select in view"}</button>` +
    `<label class="inline">rows ${inp("limit", "500", 50)}</label><button type="button" class="small" data-qop="clear" title="Remove the results and the marks in the view">Clear</button>` +
    (st.res ? `<button type="button" class="small" data-qop="csv">CSV</button><button type="button" class="small" data-qop="all" title="Mark all rows in the view without the highlight">Show all</button>` : "") + `</div>` +
    (st.picking ? `<p class="fa-pick">Click ${q.what === "nodes" ? "a node" : "an element"} in the view${within(q) ? ` (${within(q).set ? "set " + esc(within(q).set) : "type " + esc(within(q).type)})` : ""}; Shift+click adds to the list; Esc stops.</p>` : "");
  const r = st.res;
  if (r) {
    h += `<p class="hint">${r.count} ${r.what === "nodes" ? "node(s)" : "element(s)"} found${r.truncated ? `, the first ${r.rows.length} listed` : ""}${r.note ? "; " + esc(r.note) : ""}. A click on a row highlights it in the view.</p>`;
    const nodeCol = r.what === "nodes";
    const head = nodeCol ? ["Node", "x (mm)", "y (mm)", "z (mm)", ...(r.rows.some(x => x.dist !== null) ? ["Distance (mm)"] : []), "Sets", "Elements", "File"]
      : ["Element", "Type", "Nodes", "Sets", "Section", "Material", "Centroid x / y / z (mm)", ...(r.rows.some(x => x.dist !== null && x.dist !== undefined) ? ["Distance (mm)"] : []),
         "Volume / area", "Edge min / max (mm)", "Aspect", "Angle min / max (deg)", "Warp (deg)", "File"];
    const dcol = head.includes("Distance (mm)");
    h += `<div class="fa-wide ii-res"><table class="fa-tbl ii-tbl"><tr>${head.map(x => `<th>${esc(x)}</th>`).join("")}</tr>` +
      r.rows.map((x, i) => `<tr data-qrow="${i}" class="${st.sel === i ? "sel" : ""}">` + (nodeCol
        ? [x.id, g(x.xyz[0], 6), g(x.xyz[1], 6), g(x.xyz[2], 6), ...(dcol ? [g(x.dist, 5)] : []), esc(x.sets.join(", ")),
           `${x.elements}${x.elements ? ": " + x.elem_ids.join(", ") + (x.elements > x.elem_ids.length ? " …" : "") : ""}`, fileBtn(i)]
        : [x.id, esc(x.type), esc(x.nodes.join(", ")), esc(x.sets.join(", ")), esc(x.section || "-"), esc(x.material || "-"),
           x.centroid.map(v => g(v, 5)).join(" / "), ...(dcol ? [g(x.dist, 5)] : []),
           g(x.measure) + (x.inverted ? " (inverted)" : ""), `${g(x.edge_min)} / ${g(x.edge_max)}`, g(x.aspect),
           x.angle_min !== undefined ? `${g(x.angle_min)} / ${g(x.angle_max)}` : "-", g(x.warp), fileBtn(i)]).map(c => `<td>${c}</td>`).join("") + `</tr>`).join("") + `</table></div>`;
  }
  return h + `</div>`;
}

function bindQuery(box, path, opts) {
  const st = QS[path], q = st.q;
  const redraw = () => { const d = box.querySelector(".ii-query"); if (d) { d.outerHTML = queryHtml(path); bindQuery(box, path, opts); } };
  // all rows marked (red points, orange element edges); the selected row st.sel highlighted (blue point, blue edges
  // and faces of the element)
  const marks = () => {
    if (!opts.mark) return;
    const r = st.res;
    if (!r) { opts.mark(null); return; }
    const m = { points: r.rows.map(x => (r.what === "nodes" ? x.xyz : x.centroid)), lines: r.what === "elements" ? r.rows.flatMap((x, i) => r.lineOf[i] || []) : [] };
    const x = st.sel !== null && st.sel !== undefined ? r.rows[st.sel] : null;
    if (x) {
      m.focus = r.what === "nodes" ? x.xyz : x.centroid;
      if (r.what === "elements") { m.focusLines = r.lineOf[st.sel] || []; m.focusTris = x.tris || []; }
    }
    opts.mark(m);
  };
  const splitLines = r => {                  // element edges per row (the marks of the server in row order)
    r.lineOf = [];
    if (r.what === "elements") {
      let k = 0;
      for (const x of r.rows) { const n = x.edges || 0; r.lineOf.push(r.marks.lines.slice(k, k + n)); k += n; }
    }
    return r;
  };
  const showRow = () => {
    const tr = box.querySelector(`.ii-query [data-qrow="${st.sel}"]`);
    if (tr) tr.scrollIntoView({ block: "nearest" });
  };
  const pickLoop = () => {
    if (!opts.pickAt || !st.picking) return;
    opts.pickAt(async hit => {
      if (!st.picking) return;
      try {
        const r = splitLines(await (await window.postJSON("/api/inp/query", { path, what: q.what, by: "at", point: hit.xyz, within: within(q) })).json());
        const x = r.rows[0];
        if (x) {
          if (hit.shift && st.res && st.res.what === r.what) {
            let i = st.res.rows.findIndex(y => y.id === x.id);
            if (i < 0) { st.res.rows.push(x); st.res.lineOf.push(r.lineOf[0] || []); st.res.count = st.res.rows.length; i = st.res.rows.length - 1; }
            st.sel = i;
          } else { r.note = "picked in the view"; st.res = r; st.sel = 0; }
        }
        marks(); redraw(); showRow();
      } catch (e) { if (window.showErr) window.showErr(e); }
      pickLoop();
    }, () => { st.picking = false; redraw(); });
  };
  box.querySelectorAll(".ii-query [data-qk]").forEach(el => el.onchange = () => {
    const k = el.dataset.qk;
    q[k] = el.value;
    if (k === "what") { q.by = "number"; delete q.set; delete q.type; }
    if (k === "what" || k === "by" || k === "criterion") redraw();
  });
  const num = v => (v === undefined || v === null || String(v).trim() === "" ? null : Number(window.numv ? window.numv(String(v)) : v));
  box.querySelectorAll(".ii-query [data-qop]").forEach(b => b.onclick = async () => {
    const op = b.dataset.qop;
    box.querySelectorAll(".ii-query [data-qk]").forEach(el => { q[el.dataset.qk] = el.value; });
    if (op === "sel") {
      st.picking = !st.picking;
      if (st.picking) pickLoop(); else if (opts.endPick) opts.endPick();
      redraw();
      return;
    }
    if (op === "pick") {
      if (!opts.pick) return;
      opts.pick(xyz => { q.px = +xyz[0].toFixed(6); q.py = +xyz[1].toFixed(6); q.pz = +xyz[2].toFixed(6); if (!q.nearest && !q.radius) q.nearest = 1; redraw(); });
      return;
    }
    if (op === "clear") { st.res = null; st.sel = null; marks(); redraw(); return; }
    if (op === "all") { st.sel = null; marks(); redraw(); return; }
    if (op === "csv") {
      const r = st.res, rows = r.what === "nodes" ? [["node", "x", "y", "z", "distance", "sets", "elements"], ...r.rows.map(x => [x.id, ...x.xyz, x.dist ?? "", x.sets.join(" "), x.elem_ids.join(" ")])]
        : [["element", "type", "nodes", "sets", "section", "material", "cx", "cy", "cz", "distance", "volume_or_area", "edge_min", "edge_max", "aspect", "angle_min", "angle_max", "warp"],
           ...r.rows.map(x => [x.id, x.type, x.nodes.join(" "), x.sets.join(" "), x.section || "", x.material || "", ...x.centroid, x.dist ?? "", x.measure ?? "", x.edge_min ?? "", x.edge_max ?? "", x.aspect ?? "", x.angle_min ?? "", x.angle_max ?? "", x.warp ?? ""])];
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([rows.map(rr => rr.map(c => (/[",]/.test(String(c)) ? `"${String(c).replace(/"/g, "'")}"` : c)).join(",")).join("\n") + "\n"], { type: "text/csv" }));
      a.download = "search_" + r.what + ".csv";
      document.body.appendChild(a); a.click(); a.remove();
      return;
    }
    const body = { path, what: q.what, by: q.by, numbers: q.numbers, set: q.set, type: q.type, criterion: q.criterion || "inverted", value: num(q.value),
                   limit: num(q.limit) || 500 };
    if (q.by === "box") body.box = [0, 1, 2, 3, 4, 5].map(i => num(q["b" + i]));
    if (q.by === "near") { body.point = [num(q.px), num(q.py), num(q.pz)]; body.radius = num(q.radius); body.nearest = num(q.nearest); }
    try {
      const r = splitLines(await (await window.postJSON("/api/inp/query", body)).json());
      st.res = r; st.sel = null;
      marks();
      redraw();
    } catch (e) { if (window.showErr) window.showErr(e); }
  });
  box.querySelectorAll(".ii-query [data-qline]").forEach(bt => bt.onclick = async ev => {
    ev.stopPropagation();
    const x = st.res.rows[+bt.dataset.qline];
    try {
      const j = await (await window.postJSON("/api/inp/text", { path, find: { text: String(x.id), kind: st.res.what === "nodes" ? "node" : "element" } })).json();
      if (j.line) { await gotoLine(box, path, j.line); box.querySelector('details.ii-sec[data-ii="text"]').scrollIntoView({ block: "start" }); }
      else if (window.status) window.status(`File text: ${st.res.what === "nodes" ? "node" : "element"} ${x.id} not found in the file (in an include file?)`, true);
    } catch (e) { if (window.showErr) window.showErr(e); }
  });
  box.querySelectorAll(".ii-query [data-qrow]").forEach(tr => tr.onclick = () => {
    const i = +tr.dataset.qrow;
    st.sel = st.sel === i ? null : i;
    marks();
    box.querySelectorAll(".ii-query [data-qrow]").forEach(t2 => t2.classList.toggle("sel", +t2.dataset.qrow === st.sel));
  });
}

function table(head, rows) {
  return `<div class="fa-wide"><table class="fa-tbl ii-tbl"><tr>${head.map(h => `<th>${esc(h)}</th>`).join("")}</tr>` +
    rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("") + `</table></div>`;
}
function section(key, title, body, open) {
  const o = OPEN[key] !== undefined ? OPEN[key] : !!open;
  return `<details class="ii-sec" data-ii="${key}"${o ? " open" : ""}><summary>${esc(title)}</summary>${body}</details>`;
}
const box3 = b => (b ? b.min.map((v, i) => `${g(v)} to ${g(b.max[i])}`).join(" / ") : "-");

/** HTML of the contents. */
export function html(info) {
  const f = info.file, n = info.nodes;
  let h = `<p class="hint">${esc(f.name)}: ${g(f.size_kb, 4)} kB, ${f.lines} lines${f.heading ? `, heading "${esc(f.heading)}"` : ""}; ` +
    `${n.count} nodes, ${info.elements.count} elements (${info.element_types.map(t => `${t.count} ${esc(t.type)}`).join(", ")})` +
    (info.mass.kg ? `; mass ${g(info.mass.kg, 5)} kg` : "") + `</p>`;
  if (info.checks.length) h += section("checks", `Checks (${info.checks.length})`, `<ul class="ii-checks">${info.checks.map(c => `<li>${esc(c)}</li>`).join("")}</ul>`, true);
  let fb = table(["Item", "Value"], [["Path", esc(f.path)], ["Size", `${g(f.size_kb, 4)} kB, ${f.lines} lines (with the include files)`],
    ["Heading", esc(f.heading || "-")], ...(f.includes || []).map(i => ["Include", `${esc(i.file)} (${i.found ? i.lines + " lines" : "not found"})`])]);
  h += section("file", "File", fb);
  h += section("text", `File text (${f.lines} lines)`, `<div class="ii-text"></div>`);
  h += section("nodes", `Nodes (${n.count})`, table(["Item", "Value"], [
    ["Numbers", `${n.first} to ${n.last}`], ["Extent x / y / z (mm)", box3(n.bbox)],
    ["Size x, y, z (mm)", n.bbox ? n.bbox.size.map(v => g(v)).join(" x ") : "-"], ["Diagonal (mm)", g(n.diagonal)],
    ["Coincident nodes", n.coincident], ["Nodes in no element", n.unused], ["Elements with missing nodes", n.elements_with_missing_nodes]]));
  const T = info.element_types;
  h += section("types", `Element types (${T.length})`, table(["Type", "Count", "Numbers", "Family", "Shape", "Order", "Nodes", "Integration", "Used"],
    T.map(t => [`<b>${esc(t.type)}</b>`, t.count, `${t.first} to ${t.last}`, esc(t.family), esc(t.shape || "-"), esc(t.order || "-"),
      (t.nodes_given || []).join(", "), esc(t.integration || "-"), t.read ? "yes" : "no"])) +
    `<p class="hint">${T.map(t => `${esc(t.type)}: ${esc(t.description)}`).join("<br>")}</p>`, true);
  const qr = T.filter(t => t.quality);
  if (qr.length) {
    const st = (s, d) => (s ? `${g(s.min, d)} / ${g(s.mean, d)} / ${g(s.max, d)}` : "-");
    h += section("quality", "Mesh quality", table(["Type", "Edge min / mean / max (mm)", "Aspect ratio min / mean / max", "Aspect > 10",
      "Volume (mm^3) or area (mm^2) min / mean / max", "Total", "Inverted", "Corner angle min / max (deg)", "Angle < 30", "Warping max (deg)"],
      qr.map(t => {
        const q = t.quality;
        return [esc(t.type), st(q.edge), st(q.aspect), q.aspect_above_10 ?? "-", st(q.volume || q.area),
          g(q.volume_total ?? q.area_total), q.inverted ?? "-", q.angle_min ? `${g(q.angle_min.min)} / ${g(q.angle_max.max)}` : "-",
          q.angle_below_30 ?? "-", q.warp ? g(q.warp.max) : "-"];
      })) + `<p class="hint">Corner nodes of each element; aspect ratio: longest / shortest edge; inverted: zero or negative volume; warping: largest angle between the two triangles of a quadrilateral.</p>`);
  }
  h += section("elsets", `Element sets (${info.elsets.length})`, table(["Name", "Elements", "Types", "Section", "Material", "Volume (mm^3)", "Area (mm^2)", "Mass (kg)", "Extent x / y / z (mm)"],
    info.elsets.map(e => [esc(e.name), e.elements + (e.missing ? ` (${e.missing} missing)` : ""), Object.entries(e.types).map(([k, v]) => `${esc(k)} ${v}`).join(", "),
      esc(e.section || "-"), esc(e.material || "-"), g(e.volume), g(e.area), g(e.mass_kg), box3(e.bbox)])) +
    (info.mass.kg ? `<p class="hint">Total mass of the element sets with a section and a density: ${g(info.mass.kg, 5)} kg; centre of mass (${info.mass.centre.map(v => g(v)).join(", ")}) mm</p>` : ""));
  h += section("nsets", `Node sets (${info.nsets.length})`, table(["Name", "Nodes", "Generated", "Extent x / y / z (mm)"],
    info.nsets.map(s => [esc(s.name), s.nodes + (s.missing ? ` (${s.missing} missing)` : ""), s.generated ? "yes" : "", box3(s.bbox)])));
  if ((info.surfaces || []).length) h += section("surfaces", `Surfaces (${info.surfaces.length})`, table(["Name", "Type", "Lines"], info.surfaces.map(s => [esc(s.name), esc(s.type), s.entries])));
  h += section("mats", `Materials (${info.materials.length})`, table(["Name", "Used", "E (MPa)", "nu", "Density (kg/m^3)", "Plastic", "Other", "Keywords"],
    info.materials.map(m => [esc(m.name), m.used ? "yes" : "no", g(m.E), g(m.nu), g(m.rho),
      m.plastic ? `${m.plastic.points} points, yield ${g(m.plastic.yield)} MPa, last ${g(m.plastic.last_stress)} MPa at ${g(m.plastic.last_strain)}` : "-",
      [m.alpha !== undefined ? `expansion ${g(m.alpha)} 1/K` : "", m.hyperelastic_constants ? `hyperelastic ${m.hyperelastic_constants.map(v => g(v)).join(", ")}` : "", m.damping ? "damping" : ""].filter(Boolean).join("; ") || "-",
      esc((m.keywords || []).join("; ") || "-")])));
  h += section("secs", `Sections (${info.sections.length})`, table(["Element set", "Kind", "Material", "Elements", "Thickness (mm)", "Parameters", "Data"],
    info.sections.map(s => [esc(s.elset) + (s.elset_found ? "" : " (not found)"), esc(s.kind), esc(s.material || "-") + (s.material_found ? "" : " (not found)"), s.elements,
      g(s.t), esc(Object.entries(s.params).map(([k, v]) => v === "" ? k : `${k}=${v}`).join(", ") || "-"), (s.data || []).map(v => g(v)).join(", ") || "-"])));
  if (info.constraints.length) h += section("cons", `Constraints, interactions, amplitudes, initial conditions (${info.constraints.length})`,
    table(["Keyword", "Name", "Content"], info.constraints.map(c => c.map(esc))));
  const C = info.curves || {}, nc = Object.keys(C.materials || {}).length + (C.amplitudes || []).length + (C.functions || []).length;
  if (nc) h += section("curves", `Material curves, amplitudes, functions (${nc})`,
    (Object.keys(C.materials || {}).length ? `<p class="hint">Materials: true stress against strain</p><div class="ii-mc"></div>` : "") +
    ((C.amplitudes || []).length ? `<p class="hint">*AMPLITUDE</p><div class="ii-ac"></div>` : "") +
    ((C.functions || []).length ? `<p class="hint">/FUNCT</p><div class="ii-fc"></div>` : ""));
  if (info.steps.length) h += section("steps", `Steps (${info.steps.length})`, info.steps.map((s, k) =>
    `<p class="ii-step"><b>${k + 1}. ${esc(s.name)}</b>: ${esc(s.procedure || "(no procedure)")} ${esc(Object.entries(s.proc_params).map(([a, b]) => b === "" ? a : `${a}=${b}`).join(", "))}` +
    (Object.keys(s.params).length ? ` [${esc(Object.entries(s.params).map(([a, b]) => b === "" ? a : `${a}=${b}`).join(", "))}]` : "") +
    (s.proc_data.length ? `; data ${s.proc_data.map(v => g(v)).join(", ")}` : "") + `</p>` +
    table(["Item", "Content"], [["*BOUNDARY", `${s.boundary} line(s) on ${esc(s.boundary_targets.join(", ") || "-")}`],
      ["*CLOAD", `${s.cload} line(s); total F (${s.cload_total.slice(0, 3).map(v => g(v)).join(", ")}) N, M (${s.cload_total.slice(3).map(v => g(v)).join(", ")}) N mm`],
      ["*DLOAD", esc(Object.entries(s.dload).map(([a, b]) => `${a} ${b}`).join(", ") || "0")], ["*DSLOAD", s.dsload],
      ["Amplitudes", esc(s.amplitudes.join(", ") || "-")],
      ...s.outputs.map(o => ["*" + esc(o.kw), esc(Object.entries(o.params).map(([a, b]) => b === "" ? a : `${a}=${b}`).join(", ")) + ": " + esc(o.vars.join(", "))]),
      ...(s.other.length ? [["Other", esc(s.other.join(", "))]] : [])])).join(""));
  h += section("kws", `Keywords (${info.keywords.length})`, table(["Keyword", "Count", "Used by the program"],
    info.keywords.map(k => [`<a href="#" class="ii-kw" data-kw="${esc(k.keyword)}" title="Show the first line of the keyword in File text">${esc(k.keyword)}</a>`, k.count, k.read ? "yes" : "no"])));
  return h;
}

const CST = { mat: {}, amp: {}, fn: {} };
/** Plots of the curves section: material curves, *AMPLITUDE (by the TIME parameter), /FUNCT. */
function curvesPlots(el, info) {
  const C = info.curves || {}, E = {};
  for (const m of info.materials || []) E[m.name] = m.E;
  if (el.querySelector(".ii-mc")) CV.renderMaterials(el.querySelector(".ii-mc"), Object.entries(C.materials).map(([n, cs]) => ({ name: n, E: +E[n] || 0, curves: cs })), CST.mat);
  if (el.querySelector(".ii-ac")) {
    const nt = C.amplitudes.filter(a => /TOTAL/i.test(a.time || "")).length;
    CV.renderAmplitudeCurves(el.querySelector(".ii-ac"), C.amplitudes, { xlabel: nt === C.amplitudes.length ? "total time (s)" : nt ? "time (s)" : "step time (s)", st: CST.amp });
  }
  if (el.querySelector(".ii-fc")) CV.renderAmplitudeCurves(el.querySelector(".ii-fc"), C.functions.map(f => ({ name: `${f.id} ${f.name}`, t: f.x, v: f.y })),
    { xlabel: "x", xname: "x", ylabel: "y", st: CST.fn, csvName: "functions" });
}

/** Renders the page of a file path into box (cached per path; refresh: read again). */
export async function render(box, path, opts) {
  opts = opts || {};
  if (!box) return;
  if (!path) { box.innerHTML = `<p class="hint">The geometry is not a mesh file (.inp or .rad).</p>`; return; }
  const bar = `<div class="row wrap ii-bar"><button type="button" class="small" data-iiop="report" title="The contents as a text report in a new window">Report</button>` +
    `<button type="button" class="small" data-iiop="download">Download report</button><button type="button" class="small" data-iiop="refresh" title="Read the file again">↻</button></div>`;
  const bind = () => {
    box.querySelectorAll("details.ii-sec").forEach(d => d.ontoggle = () => { OPEN[d.dataset.ii] = d.open; });
    box.querySelectorAll("[data-iiop]").forEach(b => b.onclick = async () => {
      const op = b.dataset.iiop;
      if (op === "refresh") { delete CACHE[path]; render(box, path, opts); return; }
      try {
        const j = await (await window.postJSON("/api/inp/info", { path, report: true })).json();
        if (op === "report") {
          const w = window.open("", "_blank");
          if (w) { w.document.title = j.name; w.document.body.innerHTML = `<pre style="font:12px Consolas,monospace">${esc(j.text)}</pre>`; }
        } else {
          const a = document.createElement("a");
          a.href = URL.createObjectURL(new Blob([j.text], { type: "text/plain" }));
          a.download = j.name.replace(/\.[^.]+$/, "") + "_contents.txt";
          document.body.appendChild(a); a.click(); a.remove();
        }
      } catch (e) { if (window.showErr) window.showErr(e); }
    });
  };
  if (!CACHE[path]) {
    box.innerHTML = bar + `<p class="hint">Reading ${esc(path)} …</p>`;
    try { CACHE[path] = await (await window.postJSON("/api/inp/info", { path })).json(); }
    catch (e) { box.innerHTML = bar + `<p class="hint">${esc(e.message || e)}</p>`; bind(); return; }
  }
  box.innerHTML = bar + queryHtml(path) + html(CACHE[path]);
  bind();
  const ts = box.querySelector('details.ii-sec[data-ii="text"]');
  if (ts) {
    const show = () => { if (ts.open && !ts.querySelector(".ii-src")) openText(box, path).catch(e => { if (window.showErr) window.showErr(e); }); };
    ts.addEventListener("toggle", show);
    show();
  }
  box.querySelectorAll("a.ii-kw").forEach(a => a.onclick = async ev => {
    ev.preventDefault();
    try {
      const j = await (await window.postJSON("/api/inp/text", { path, find: { text: a.dataset.kw, kind: "text", from: 0 } })).json();
      if (j.line) { await gotoLine(box, path, j.line); box.querySelector('details.ii-sec[data-ii="text"]').scrollIntoView({ block: "start" }); }
    } catch (e) { if (window.showErr) window.showErr(e); }
  });
  const cs = box.querySelector('details.ii-sec[data-ii="curves"]');
  if (cs) {
    const draw = () => { if (cs.open) curvesPlots(cs, CACHE[path]); };
    cs.addEventListener("toggle", draw);
    draw();
  }
  bindQuery(box, path, opts);
}
