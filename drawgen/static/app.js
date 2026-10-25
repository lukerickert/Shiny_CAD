"use strict";

window.addEventListener("error", (e) => {
  const st = document.getElementById("status-text");
  if (st) { st.textContent = "Script error: " + e.message + " (" + (e.filename || "").split("/").pop() + ":" + e.lineno + ")"; }
});
window.addEventListener("unhandledrejection", (e) => {
  const st = document.getElementById("status-text");
  const r = e.reason || {};
  if (st) { st.textContent = "Script error: " + (r.message || r) + " | " + ((r.stack || "").split("\n").slice(0, 3).join(" | ")); }
});

const $ = (s) => document.querySelector(s);
const state = { cfg: null, files: [], busy: 0 };
const VIEW_KEYS = ["orthographic", "section", "isometric", "hidden_lines", "smooth_lines"];
const AUTO_FIELDS = { Title: "auto: part name", DrawingNumber: "auto: from title", Date: "auto: today",
                      Scale: "auto", Mass: "auto with density" };
const FIELD_LABELS = {};

// ------------------------------------------------------------------ status

function busy(on, text) {
  state.busy += on ? 1 : -1;
  $("#spinner").hidden = state.busy <= 0;
  document.querySelectorAll("#btn-preview, #btn-export").forEach(b => b.disabled = state.busy > 0);
  if (text) status(text);
}
function showErr(e) {
  console.error(e);
  const where = (e && e.stack || "").split("\n").slice(1, 3).map(x => x.trim().replace(/https?:\/\/[^/]+\/static\//, "")).join(" | ");
  status((e && e.message || String(e)) + (where ? "  [" + where + "]" : ""), true);
}
// The browser menu is not shown on the 3D views, the sketch and drawing areas and the program's own menus. On
// Windows the contextmenu event comes after the button is released, when a program menu may already be open under
// the cursor.
document.addEventListener("contextmenu", e => {
  if (e.target.closest && e.target.closest("canvas, svg, .sk-menu, #as-view, #pt-view, #fa-view, #xp-view, .as-comp")) e.preventDefault();
}, true);

/** Measure panel content: the picked items and the rows of a measurement (measure.py). */
function measureHtml(res, hint) {
  const e = x => String(x).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  if (!res) return `<p class="hint">${e(hint || "")}</p>`;
  return `<p class="hint">${(res.items || []).map((n, i) => (i ? "B: " : "A: ") + e(n)).join("<br>")}</p>` +
    `<table class="meas-tbl">${res.rows.map(([k, v]) => `<tr><td>${e(k)}</td><td>${e(v)}</td></tr>`).join("")}</table>` +
    (hint ? `<p class="hint">${e(hint)}</p>` : "");
}

function status(text, isError) {
  $("#status-text").textContent = text;
  $("#status-text").title = text;                    // one line; the full text as tooltip
  $("#status").classList.toggle("error", !!isError);
}
async function api(url, opts) {
  const r = await fetch(url, opts);
  const ct = r.headers.get("content-type") || "";
  if (!r.ok) {
    const msg = ct.includes("json") ? (await r.json()).error : await r.text();
    throw new Error(msg || r.statusText);
  }
  return r;
}
function postJSON(url, body) {
  return api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

// ------------------------------------------------------------------ config -> form

function scaleText(s) {
  return s >= 1 ? `${+s.toFixed(6)}:1` : `1:${+(1 / s).toFixed(6)}`;
}

function fillForm(cfg) {
  const sheet = $("#sheet");
  sheet.innerHTML = "";
  [...Object.keys(cfg.sheet_sizes_mm), "auto"].forEach(k => {
    const o = new Option(k === "auto" ? "Auto" : k, k);
    sheet.add(o);
  });
  sheet.value = cfg.sheet || "A3";
  const scale = $("#scale");
  scale.innerHTML = "";
  scale.add(new Option("Auto", "auto"));
  cfg.standard_scales.forEach(s => scale.add(new Option(scaleText(s), scaleText(s))));
  scale.value = cfg.scale || "auto";
  $("#mode").value = cfg.mode || "per_part";
  VIEW_KEYS.forEach(k => $("#v-" + k).checked = !!cfg.views[k]);
  $("#v-section_axis").value = cfg.views.section_axis || "X";
  $("#v-section_offset_mm").value = cfg.views.section_offset_mm || 0;
  $("#v-section_flip").checked = !!cfg.views.section_flip;
  $("#v-isometric_scale_factor").value = cfg.views.isometric_scale_factor ?? 1;
  $("#density").value = cfg.density_kg_per_m3 || 0;
  ["pdf", "dxf", "svg", "fcstd"].forEach(f => $("#f-" + f).checked = (cfg.outputs || []).includes(f));
  $("#out-dir").value = cfg.output_dir || "";

  cfg.title_block.cells.forEach(c => FIELD_LABELS[c.key] = c.label);
  const box = $("#fields");
  box.innerHTML = "";
  Object.entries(cfg.fields).forEach(([k, v]) => {
    const lab = document.createElement("label");
    lab.textContent = FIELD_LABELS[k] || k;
    const inp = document.createElement("input");
    inp.type = "text";
    inp.dataset.key = k;
    inp.value = v;
    if (AUTO_FIELDS[k]) inp.placeholder = AUTO_FIELDS[k];
    if (k === "Scale") { inp.disabled = true; inp.value = ""; }
    lab.appendChild(inp);
    if (k === "SurfaceFinish") {                     // achievable Ra by process (reference.js, Surface roughness)
      const b = document.createElement("button");
      b.type = "button"; b.className = "small"; b.id = "ra-guide"; b.textContent = "Guide";
      b.title = "Achievable roughness Ra by process; a click on a value sets the field";
      b.onclick = e => { e.preventDefault(); if (window.openReference) window.openReference("rough", inp); };
      lab.appendChild(b);
    }
    box.appendChild(lab);
  });
  fillEditor(cfg);
}

/** Writes drawing settings (the shape of readSettings()) into the form. */
window.applySettings = function (st) {
  if (!st) return;
  if (st.sheet) $("#sheet").value = st.sheet;
  if (st.scale) $("#scale").value = st.scale;
  if (st.mode) $("#mode").value = st.mode;
  const v = st.views || {};
  VIEW_KEYS.forEach(k => { if (k in v) $("#v-" + k).checked = !!v[k]; });
  if (v.section_axis) $("#v-section_axis").value = v.section_axis;
  if ("section_offset_mm" in v) $("#v-section_offset_mm").value = v.section_offset_mm;
  if ("section_flip" in v) $("#v-section_flip").checked = !!v.section_flip;
  if ("isometric_scale_factor" in v) $("#v-isometric_scale_factor").value = v.isometric_scale_factor;
  if ("density_kg_per_m3" in st) $("#density").value = st.density_kg_per_m3;
};

function readSettings() {
  const views = {};
  VIEW_KEYS.forEach(k => views[k] = $("#v-" + k).checked);
  views.section_axis = $("#v-section_axis").value;
  views.section_offset_mm = parseFloat($("#v-section_offset_mm").value) || 0;
  views.section_flip = $("#v-section_flip").checked;
  views.isometric_scale_factor = parseFloat($("#v-isometric_scale_factor").value) || 1;
  return { sheet: $("#sheet").value, scale: $("#scale").value, mode: $("#mode").value, views,
           density_kg_per_m3: parseFloat($("#density").value) || 0 };
}
function readFields() {
  const f = {};
  document.querySelectorAll("#fields input").forEach(i => { if (i.dataset.key !== "Scale") f[i.dataset.key] = i.value; });
  return f;
}
function readFormats() {
  return ["pdf", "dxf", "svg", "fcstd"].filter(f => $("#f-" + f).checked);
}
function selection() {
  return state.files.map(f => ({
    file_id: f.file_id,
    part_ids: f.parts.filter(p => p.checked).map(p => p.id),
  })).filter(s => s.part_ids.length);
}

// ------------------------------------------------------------------ files

function renderFiles() {
  const box = $("#files");
  box.innerHTML = "";
  state.files.forEach(f => {
    const el = document.createElement("div");
    el.className = "file";
    const head = document.createElement("div");
    head.className = "file-head";
    const name = document.createElement("strong");
    name.textContent = f.name;
    name.title = f.source || f.name;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.textContent = "×";
    rm.title = "Remove";
    rm.onclick = async () => {
      await api("/api/files/" + f.file_id, { method: "DELETE" });
      state.files = state.files.filter(x => x !== f);
      renderFiles();
    };
    if (f.refresh) {
      const up = document.createElement("button");
      up.type = "button";
      up.textContent = "\u21bb";
      up.title = "Update: rebuild the model from the part, the assembly or the STEP file and redraw";
      up.onclick = () => refreshFile(f);
      head.append(name, up, rm);
    } else head.append(name, rm);
    el.appendChild(head);
    f.parts.forEach(p => {
      const row = document.createElement("label");
      row.className = "part check";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = p.checked;
      cb.onchange = () => { p.checked = cb.checked; schedulePreview(); };
      const t = document.createElement("span");
      t.textContent = p.name;
      const dim = document.createElement("span");
      dim.className = "dim";
      dim.textContent = p.size_mm.map(v => +v.toFixed(1)).join(" x ") + " mm";
      row.append(cb, t, dim);
      el.appendChild(row);
    });
    box.appendChild(el);
  });
}

// ------------------------------------------------------------------ options (drawing units, keyboard shortcuts)
// config.json "options" (units.py): units "mm" | "inch" for the drawing text; keys "default" | "left".
window.OPT = { units: "mm", keys: "default" };
const MM_PER_IN = 25.4;
window.isInch = () => OPT.units === "inch";
window.leftKeys = () => OPT.keys === "left";
/** Inch text of a length in mm, leading zero omitted (ASME Y14.5); sign: + also on positive values. */
window.inchText = function (vmm, d, sign) {
  const v = vmm / MM_PER_IN;
  let s = Math.abs(v).toFixed(d);
  if (s.startsWith("0.")) s = s.slice(1);
  const neg = v < 0 && +s !== 0;
  return (neg ? "-" : sign ? "+" : "") + s;
};
/** Deviation text on the drawing (mm in): µm (+27, -40, 0) or inch (+.0011, -.0000); mirrors units.dev_text. */
window.devText = function (v, lower) {
  if (isInch()) return Math.abs(v) < 0.5e-4 * MM_PER_IN ? (lower ? "-" : "+") + ".0000" : inchText(v, 4, true);
  const um = Math.round(v * 10000) / 10;
  if (Math.abs(um) < 0.05) return "0";
  return (um > 0 ? "+" : "-") + String(+Math.abs(um).toFixed(1));
};
/** Value after ± of a symmetric tolerance (mm in). */
window.symText = v => isInch() ? inchText(Math.abs(v), 4) : devText(Math.abs(v)).replace("+", "");
/** Length text of a dimension on the drawing; fmtMm formats the mm value. */
window.dimLenText = (v, fmtMm) => isInch() ? inchText(v, 3) : fmtMm(v);
/** Deviation fields of the dimension properties: µm, or inch with the inch option. */
window.devUnit = () => isInch() ? "in" : "\u00b5m";
window.devToField = v => v === undefined || v === null || v === "" ? "" : isInch() ? String(+(v / MM_PER_IN).toFixed(5)) : String(+(v * 1000).toFixed(3));
window.devFromField = s => { const v = numv(s); return isFinite(v) ? (isInch() ? v * MM_PER_IN : v / 1000) : 0; };

/** Label of a physical key (KeyboardEvent.code) on this keyboard layout. */
let KEY_LAYOUT = null;
window.codeLabel = function (code) {
  if (code === "Space") return "Space";
  const l = KEY_LAYOUT && KEY_LAYOUT.get(code);
  if (l) return l.toUpperCase();
  return ({ Semicolon: ";", Slash: "/", Period: ".", Comma: ",", Quote: "'", Minus: "-", Equal: "=", BracketLeft: "[", BracketRight: "]" })[code]
    || code.replace(/^Key|^Digit/, "");
};
/** Keyboard shortcut lists of the tabs for the Options dialog: {tab, rows: () => [[key, action], ...]}. */
window.SHORTCUTS = [];
/** Replaces "(K)" after the name in a tooltip by the current key (none: removed). */
window.setKeyTitle = function (el, key) {
  if (!el) return;
  const t = (el.title || "").replace(/ \([^)]*\)(?=[:.]|$)/, "");
  const m = t.match(/^[^:.]*/);
  el.title = key ? m[0] + " (" + key + ")" + t.slice(m[0].length) : t;
};
function optionsChanged() { window.dispatchEvent(new Event("optionschanged")); }
function renderKeyList() {
  const box = $("#opt-keylist");
  if (!box) return;
  box.innerHTML = SHORTCUTS.map(g => `<h3 class="ref-h">${g.tab}</h3><table class="opt-keys">` +
    g.rows().map(([k, a]) => `<tr><td><kbd>${k}</kbd></td><td>${a}</td></tr>`).join("") + "</table>").join("");
}
async function setOption(key, value) {
  try {
    const r = await api("/api/options", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ [key]: value }) });
    Object.assign(OPT, await r.json());
    if (state.cfg) state.cfg.options = Object.assign({}, OPT);
    optionsChanged();
    renderKeyList();
    if (key === "units" && (state.drawings || []).length) preview(false, true);
    status(key === "units" ? "Drawing units: " + (isInch() ? "inch" : "mm") : key === "keys" ? "Keyboard shortcuts: " + (leftKeys() ? "left-handed" : "default")
      : "Browser: " + (OPT.browser || "system default") + " (used at the next start)");
  } catch (e) { showErr(e); }
}
function openOptions() {
  $("#opt-units").value = OPT.units;
  $("#opt-keys").value = OPT.keys;
  $("#opt-browser").value = OPT.browser || "";
  renderKeyList();
  $("#opt-dialog").hidden = false;
}
async function loadOptions() {
  try { Object.assign(OPT, await (await api("/api/options")).json()); } catch (e) { /* defaults */ }
  if (navigator.keyboard && navigator.keyboard.getLayoutMap) {
    try { KEY_LAYOUT = await navigator.keyboard.getLayoutMap(); } catch (e) { KEY_LAYOUT = null; }
  }
  optionsChanged();
}

/** Number from a text field: a plain number, or an arithmetic expression with + - * / ^ ( ), sqrt() and pi
 *  ("450/2", "(120-2*8)/3", "sqrt(2)*10"). Decimal commas are accepted; a trailing mm or deg is ignored.
 *  NaN when the text is not a number or an expression. */
window.numv = function (s) {
  if (typeof s === "number") return s;
  if (s === null || s === undefined) return NaN;
  const t = String(s).trim().replace(/,/g, ".").replace(/\s*(mm|deg|\u00b0)\s*$/i, "");
  if (/^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(t)) return parseFloat(t);
  if (!/^(?:\d+\.?\d*|\.\d+|sqrt|pi|[-+*/^()\s])+$/i.test(t) || !/\d/.test(t)) return parseFloat(t);
  try {
    const expr = t.replace(/\^/g, "**").replace(/sqrt/gi, "Math.sqrt").replace(/pi/gi, "Math.PI");
    const v = Function('"use strict"; return (' + expr + ");")();
    return typeof v === "number" && isFinite(v) ? v : NaN;
  } catch (e) { return NaN; }
};

// dropdown menus (.dd > .dd-btn + .dd-menu): one open at a time; a click on a button in the menu or outside closes it
document.addEventListener("click", e => {
  const btn = e.target.closest(".dd-btn");
  if (btn) {
    const dd = btn.parentElement, open = dd.classList.contains("open");
    document.querySelectorAll(".dd.open").forEach(d => d.classList.remove("open"));
    if (!open) dd.classList.add("open");
    return;
  }
  const inMenu = e.target.closest(".dd-menu");
  if (!inMenu || e.target.closest("button:not(.browse)")) document.querySelectorAll(".dd.open").forEach(d => d.classList.remove("open"));
});
document.addEventListener("keydown", e => { if (e.key === "Escape") document.querySelectorAll(".dd.open").forEach(d => d.classList.remove("open")); });

const safeName = s => (s || "").replace(/[^A-Za-z0-9_\-.]+/g, "_").replace(/^_+|_+$/g, "") || "drawing";

/** Rebuilds the model of a Models entry: a part from the Part tab when it holds that part (saved or not), else
 *  from the saved part file; an assembly from the Assembly tab or the saved assembly file; a STEP file from its
 *  path. The checked parts and the drawing annotations are kept. */
async function refreshFile(f) {
  busy(true, "Updating " + f.name + " ...");
  try {
    const body = {};
    const P = window.__part && window.__part.PT && window.__part.PT.part;
    if (P && f.file_id === "part_" + safeName(P.name)) body.part = P;
    const A = window.__asm && window.__asm.AS && window.__asm.AS.asm;
    if (A && f.file_id === "asm_" + safeName(A.name)) body.assembly = A;
    const r = await postJSON("/api/files/" + f.file_id + "/refresh", body);
    const res = await r.json();
    const nf = res.files[0];
    nf.parts.forEach((p, i) => { p.checked = f.parts[i] ? f.parts[i].checked : true; });
    const i = state.files.indexOf(f);
    if (i >= 0) state.files[i] = nf; else state.files.push(nf);
    renderFiles();
    status("Updated " + nf.name);
  } catch (e) { showErr(e); busy(false); return; }
  busy(false);
  preview(false);
}

function addFiles(res) {
  res.files.forEach(f => { f.parts.forEach(p => p.checked = true); state.files.push(f); });
  renderFiles();
  const n = res.files.reduce((a, f) => a + f.parts.length, 0);
  if (res.errors && res.errors.length) status(res.errors.join("; "), true);
  else status(`Loaded ${res.files.length} file(s), ${n} part(s)`);
  schedulePreview();
}

async function uploadFiles(list) {
  const files = [...list].filter(f => /\.(step|stp)$/i.test(f.name));
  if (!files.length) return status("No STEP files selected", true);
  const fd = new FormData();
  files.forEach(f => fd.append("files", f));
  busy(true, `Reading ${files.length} file(s)...`);
  try {
    const r = await api("/api/upload", { method: "POST", body: fd });
    addFiles(await r.json());
  } catch (e) { showErr(e); }
  finally { busy(false); }
}

async function openPath() {
  const path = $("#path-input").value.trim();
  if (!path) return;
  busy(true, "Reading " + path + " ...");
  try {
    const r = await postJSON("/api/open_path", { path });
    addFiles(await r.json());
  } catch (e) { showErr(e); }
  finally { busy(false); }
}

// ------------------------------------------------------------------ preview / export

function request() {
  return { selection: selection(), settings: readSettings(), fields: readFields() };
}

// auto preview: preview again after a change, debounced; one request at a time, a change during a
// request queues one more
let autoTimer = null, previewRunning = false, previewAgain = false;
function autoPreviewOn() { const cb = $("#auto-preview"); return !!(cb && cb.checked); }
function schedulePreview() {
  if (!autoPreviewOn() || !state.files.length) return;
  clearTimeout(autoTimer);
  autoTimer = setTimeout(() => { if (previewRunning) previewAgain = true; else preview(true); }, 400);
}

async function preview(auto, keepTab) {
  const req = request();
  if (!req.selection.length) { if (!auto) status("No parts selected", true); return; }
  if (previewRunning) { previewAgain = true; return; }
  previewRunning = true;
  try { await previewNow(req, keepTab); }
  finally {
    previewRunning = false;
    if (previewAgain) { previewAgain = false; if (autoPreviewOn()) preview(true); }
  }
}

async function previewNow(req, keepTab) {
  busy(true, "Projecting views...");
  const t0 = performance.now();
  try {
    const r = await postJSON("/api/preview", req);
    const data = await r.json();
    state.drawings = data.drawings;
    if (!keepTab) showTab("annotate");
    status(`${data.drawings.length} drawing(s) in ${((performance.now() - t0) / 1000).toFixed(1)} s`);
    try {
      if (window.annotatorDrawingsChanged) annotatorDrawingsChanged();
    } catch (e) {
      console.error(e);
      status("Dimensions editor: " + e.message + " | " + (e.stack || "").split("\n").slice(0, 3).join(" | "), true);
    }
  } catch (e) { console.error(e); status(e.message + " | " + (e.stack || "").split("\n").slice(0, 3).join(" | "), true); }
  finally { busy(false); }
}

async function exportFiles() {
  const req = request();
  if (!req.selection.length) return status("No parts selected", true);
  req.formats = readFormats();
  if (!req.formats.length) return status("No output format selected", true);
  req.out_dir = $("#out-dir").value.trim();
  req.next_to_source = $("#next-to-source").checked;
  busy(true, "Exporting...");
  try {
    const r = await postJSON("/api/export", req);
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("json")) {
      const data = await r.json();
      status(`Wrote ${data.written.length} file(s): ${data.written.join(", ")}`);
    } else {
      const blob = await r.blob();
      const cd = r.headers.get("content-disposition") || "";
      const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = m ? decodeURIComponent(m[1]) : "drawings.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      status("Downloaded " + a.download);
    }
  } catch (e) { showErr(e); }
  finally { busy(false); }
}

async function saveDefaults() {
  const cfg = structuredClone(state.cfg);
  const st = readSettings();
  cfg.sheet = st.sheet; cfg.scale = st.scale; cfg.mode = st.mode;
  Object.assign(cfg.views, st.views);
  cfg.density_kg_per_m3 = st.density_kg_per_m3;
  cfg.outputs = readFormats();
  cfg.output_dir = $("#out-dir").value.trim();
  const f = readFields();
  ["Title", "SupplementaryTitle", "DrawingNumber", "Date", "Mass", "Material"].forEach(k => { if (k in f) f[k] = ""; });
  Object.assign(cfg.fields, f);
  try {
    await postJSON("/api/config", cfg);
    state.cfg = cfg;
    status("Defaults saved");
  } catch (e) { showErr(e); }
}

// ------------------------------------------------------------------ title block editor

function fillEditor(cfg) {
  const tb = cfg.title_block;
  ["width_mm", "height_mm", "label_size_mm", "font"].forEach(k => $("#tb-" + k).value = tb[k]);
  $("#tb-logo_cell").value = tb.logo_cell.join(", ");
  $("#tb-projection_cell").value = tb.projection_cell.join(", ");
  $("#b-left_mm").value = cfg.border.left_mm;
  $("#b-other_mm").value = cfg.border.other_mm;
  $("#logo-name").textContent = tb.logo_file || "No logo";
  const lw = cfg.line_widths_mm || {};
  ["visible", "hidden", "chain", "hatch", "dim", "frame", "title", "text"].forEach(k => { $("#lw-" + k).value = lw[k] !== undefined ? lw[k] : (k === "dim" ? 0.25 : 0.5); });
  $("#th-text").value = cfg.text_height_mm !== undefined ? cfg.text_height_mm : 5;
  $("#th-dim").value = cfg.dim_text_height_mm !== undefined ? cfg.dim_text_height_mm : 3.5;
  const body = $("#cells tbody");
  body.innerHTML = "";
  tb.cells.forEach(c => addCellRow(c));
  tbPreview();
}

function addCellRow(c) {
  c = c || { key: "NewField", label: "New field", x: 0, y: 0, w: 20, h: 8, size: 2.5 };
  const tr = document.createElement("tr");
  const cols = [["key", "text"], ["label", "text"], ["x", "number"], ["y", "number"], ["w", "number"], ["h", "number"], ["size", "number"]];
  cols.forEach(([k, type]) => {
    const td = document.createElement("td");
    if (type === "number") td.className = "num";
    const inp = document.createElement("input");
    inp.type = type;
    inp.step = "any";
    inp.dataset.k = k;
    inp.value = c[k];
    td.appendChild(inp);
    tr.appendChild(td);
  });
  const td = document.createElement("td");
  const del = document.createElement("button");
  del.type = "button";
  del.textContent = "×";
  del.onclick = () => tr.remove();
  td.appendChild(del);
  tr.appendChild(td);
  $("#cells tbody").appendChild(tr);
}

function nums(s) {
  const v = s.split(/[ ,;]+/).filter(Boolean).map(Number);
  if (v.length !== 4 || v.some(isNaN)) throw new Error("cell must be four numbers: " + s);
  return v;
}

function readEditor() {
  const cfg = structuredClone(state.cfg);
  const tb = cfg.title_block;
  tb.width_mm = parseFloat($("#tb-width_mm").value);
  tb.height_mm = parseFloat($("#tb-height_mm").value);
  tb.label_size_mm = parseFloat($("#tb-label_size_mm").value);
  tb.font = $("#tb-font").value;
  tb.logo_cell = nums($("#tb-logo_cell").value);
  tb.projection_cell = nums($("#tb-projection_cell").value);
  cfg.border.left_mm = parseFloat($("#b-left_mm").value);
  cfg.border.other_mm = parseFloat($("#b-other_mm").value);
  cfg.line_widths_mm = cfg.line_widths_mm || {};
  ["visible", "hidden", "chain", "hatch", "dim", "frame", "title", "text"].forEach(k => {
    const v = parseFloat($("#lw-" + k).value);
    if (v > 0) cfg.line_widths_mm[k] = v;
  });
  const th = parseFloat($("#th-text").value), thd = parseFloat($("#th-dim").value);
  if (th > 0) cfg.text_height_mm = th;
  if (thd > 0) cfg.dim_text_height_mm = thd;
  tb.cells = [...document.querySelectorAll("#cells tbody tr")].map(tr => {
    const c = {};
    tr.querySelectorAll("input").forEach(i => c[i.dataset.k] = i.type === "number" ? parseFloat(i.value) : i.value.trim());
    return c;
  }).filter(c => c.key);
  tb.cells.forEach(c => { if (!(c.key in cfg.fields)) cfg.fields[c.key] = ""; });
  return cfg;
}

async function tbPreview() {
  let cfg;
  try { cfg = readEditor(); } catch (e) { return showErr(e); }
  cfg._preview_sheet = $("#sheet").value === "auto" ? "A3" : $("#sheet").value;
  try {
    const r = await postJSON("/api/titleblock_preview", cfg);
    const svg = (await r.json()).svg;
    $("#tb-sheet").innerHTML = svg;
    $("#tb-zoom").innerHTML = svg;
    const [W, H] = cfg.sheet_sizes_mm[cfg._preview_sheet];
    const tb = cfg.title_block, other = cfg.border.other_mm;
    const x = W - other - tb.width_mm - 3, y = H - other - tb.height_mm - 3;
    const z = $("#tb-zoom svg");
    z.setAttribute("viewBox", `${x} ${y} ${tb.width_mm + 6} ${tb.height_mm + 6}`);
    z.removeAttribute("width"); z.removeAttribute("height");
    $("#tb-sheet svg").removeAttribute("width"); $("#tb-sheet svg").removeAttribute("height");
  } catch (e) { showErr(e); }
}

/** Title block editor window: filled from the saved configuration on every opening. */
function tbOpen() {
  try { fillEditor(state.cfg); } catch (e) { showErr(e); }
  $("#tb-dialog").hidden = false;
}
function tbClose() { $("#tb-dialog").hidden = true; }

async function tbSave() {
  let cfg;
  try { cfg = readEditor(); } catch (e) { return showErr(e); }
  try {
    await postJSON("/api/config", cfg);
    state.cfg = cfg;
    const vals = readFields();
    fillForm(cfg);
    document.querySelectorAll("#fields input").forEach(i => { if (i.dataset.key in vals && i.dataset.key !== "Scale") i.value = vals[i.dataset.key]; });
    status("Title block, line widths and text heights saved");
    schedulePreview();
  } catch (e) { showErr(e); }
}

async function uploadLogo(file) {
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("/api/logo", { method: "POST", body: fd });
    state.cfg.title_block.logo_file = (await r.json()).logo_file;
    $("#logo-name").textContent = state.cfg.title_block.logo_file + " (save the title block to keep it)";
    tbPreview();
  } catch (e) { showErr(e); }
}

// ------------------------------------------------------------------ tabs and events

// the Drawings tab has two panes: the drawings of the models (annotate) and sketches (sketch); the sketch pane also
// edits feature sketches of the Part tab and sketches on drawings
let DRAW_MODE = "annotate";
function showTab(name) {
  if (name === "drawings" || name === "editor") name = "annotate";   // project states saved with the former Drawings and Title block editor tabs
  const btn = name === "sketch" ? (window.sketchHostTab ? sketchHostTab() : "annotate") : name;
  if (name === "annotate" || (name === "sketch" && btn === "annotate")) DRAW_MODE = name;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === btn));
  document.querySelectorAll(".dmode button").forEach(b => b.classList.toggle("active", b.dataset.dmode === name));
  $("#tab-project").hidden = name !== "project";
  $("#tab-annotate").hidden = name !== "annotate";
  $("#tab-sketch").hidden = name !== "sketch";
  $("#tab-part").hidden = name !== "part";
  $("#tab-asm").hidden = name !== "asm";
  $("#tab-fea").hidden = name !== "fea";
  $("#tab-xp").hidden = name !== "xp";
  // the drawing settings panel (models, sheet, views, title block) is for the Drawings tab
  const aside = document.querySelector("#layout > aside");
  if (aside) aside.hidden = name !== "annotate";
  window.dispatchEvent(new Event("resize"));
  if (name === "project" && window.projectShown) projectShown();
  if (name === "part" && window.partShown) partShown();
  if (name === "asm" && window.asmShown) asmShown();
  if (name === "fea" && window.feaShown) feaShown();
  if (name === "xp" && window.xpShown) xpShown();
  if (name === "annotate" && window.annotatorShown) annotatorShown();
  if (name === "sketch" && window.sketchShown) sketchShown();
}

/** Build stamp in the title (tooltip): the newest static file on the server and the version of this script. */
const APP_BUILD = "fix179";
async function showBuild() {
  try {
    const r = await fetch("/api/build"); const j = await r.json();
    const h = document.querySelector("header h1, h1");
    if (h) h.title = "Server files " + j.build + ", page script " + APP_BUILD;
  } catch (e) { /* no stamp */ }
}

function bind() {
  showBuild();
  document.querySelectorAll(".tab").forEach(t => t.onclick = () => showTab(t.dataset.tab === "annotate" ? DRAW_MODE : t.dataset.tab));
  document.querySelectorAll(".dmode button").forEach(b => b.onclick = () => showTab(b.dataset.dmode));
  $("#file-input").onchange = (e) => { uploadFiles(e.target.files); e.target.value = ""; };
  const drop = $("#drop");
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => uploadFiles(e.dataTransfer.files));
  $("#path-open").onclick = openPath;
  $("#path-input").addEventListener("keydown", e => { if (e.key === "Enter") openPath(); });
  $("#btn-preview").onclick = () => preview(false);
  try { $("#auto-preview").checked = localStorage.getItem("drawgen.autoPreview") === "1"; } catch (e) { /* storage optional */ }
  $("#auto-preview").onchange = () => { try { localStorage.setItem("drawgen.autoPreview", $("#auto-preview").checked ? "1" : "0"); } catch (e) { /* optional */ } if ($("#auto-preview").checked) schedulePreview(); };
  document.querySelector("aside").addEventListener("change", e => {
    const t = e.target;
    if (t.id === "auto-preview" || t.id === "file-input" || t.id === "out-dir" || t.id === "next-to-source" || /^f-/.test(t.id)) return;
    schedulePreview();
  });
  $("#btn-export").onclick = exportFiles;
  $("#btn-save").onclick = saveDefaults;
  $("#cell-add").onclick = () => addCellRow();
  $("#tb-preview").onclick = tbPreview;
  $("#tb-save").onclick = tbSave;
  $("#tb-open").onclick = tbOpen;
  $("#tb-open2").onclick = tbOpen;
  $("#tb-close").onclick = tbClose;
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#tb-dialog").hidden) tbClose(); });
  $("#logo-input").onchange = (e) => { if (e.target.files[0]) uploadLogo(e.target.files[0]); e.target.value = ""; };
  $("#logo-clear").onclick = () => { state.cfg.title_block.logo_file = ""; $("#logo-name").textContent = "No logo (save the title block to keep it)"; tbPreview(); };
}

(async function init() {
  bind();
  showTab("project");
  $("#opt-open").onclick = openOptions;
  $("#opt-close").onclick = () => { $("#opt-dialog").hidden = true; };
  $("#opt-units").onchange = e => setOption("units", e.target.value);
  $("#opt-keys").onchange = e => setOption("keys", e.target.value);
  $("#opt-browser").onchange = e => setOption("browser", e.target.value.trim());
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#opt-dialog").hidden) $("#opt-dialog").hidden = true; });
  loadOptions();
  try {
    const r = await api("/api/config");
    state.cfg = await r.json();
    fillForm(state.cfg);
  } catch (e) { status("Could not load configuration: " + e.message, true); }
})();

// ---------------------------------------------------------------- FEA mesh export (Part and Assembly tabs)
let FEA_FORMATS = null;
async function feaFormats() {
  if (FEA_FORMATS) return FEA_FORMATS;
  const r = await fetch("/api/fea/formats");
  FEA_FORMATS = await r.json();
  const sel = $("#fea-format");
  sel.innerHTML = Object.entries(FEA_FORMATS.formats).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  return FEA_FORMATS;
}

/** Opens the mesh dialog. payload(): {part} or {assembly}; folder: output folder text; name: base name for the download. */
window.exportMesh = async function (payload, folder, name, onPreview) {
  const info = await feaFormats();
  const dlg = $("#fea-dialog");
  if (!info.available) { status(`gmsh cannot be imported by ${info.python}: ${info.error}. Install it with  "${info.python}" -m pip install gmsh  and restart the server`, true); return; }
  dlg.hidden = false;
  $("#fea-preview").hidden = !onPreview;
  const hint = () => {
    const k = $("#fea-kind").value;
    const kindText = { hex: "Structured hexahedra: every cell must be a block (6 faces with 4 edges each); use Partition to cut the part into blocks. C3D8 / C3D20.",
                       hexmix: "Block cells get structured hexahedra, the other cells tetrahedra. The interfaces between them are not conforming (tie them in the solver).",
                       allhex: "A tetrahedral mesh is subdivided into hexahedra (4 per tetrahedron). All hexahedra, lower quality than a structured mesh. C3D8 / C3D20.",
                       solid: "Free tetrahedra, C3D4 / C3D10.", surface: "Triangles of the boundary, S3 / STRI65.", surfquad: "Quadrangles of the boundary (recombined), S4 / S8R." }[k] || "";
    $("#fea-hint").textContent = kindText + " " + ($("#fea-format").value === ".inp"
      ? "Abaqus .inp: one node set per face (F1..Fn), one element set per cell (S1..Sn). The folder field of the tab gives the output folder (empty: download)."
      : "One physical group per face (F1..Fn) and per cell (S1..Sn). The folder field of the tab gives the output folder (empty: download).");
  };
  $("#fea-format").onchange = hint;
  $("#fea-kind").onchange = hint;
  hint();
  const close = () => { dlg.hidden = true; };
  $("#fea-cancel").onclick = close;
  const readOpts = () => {
    let kind = $("#fea-kind").value;
    const opts = { kind: kind === "surfquad" ? "surface" : kind, recombine: kind === "surfquad", order: +$("#fea-order").value, algorithm: $("#fea-algo").value,
                   curvature: +$("#fea-curv").value || 0, corner_angle: +$("#fea-corner").value || 135, groups: $("#fea-groups").checked, optimize: $("#fea-opt").checked,
                   fix_tolerance: +$("#fea-fixtol").value || 0 };
    if ($("#fea-size").value) opts.size = +$("#fea-size").value;
    if ($("#fea-size-min").value) opts.size_min = +$("#fea-size-min").value;
    return opts;
  };
  $("#fea-preview").onclick = async () => {
    close();
    status("Meshing (preview)...");
    try {
      const r = await fetch("/api/fea/preview", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ opts: readOpts() }, payload())) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || r.statusText);
      onPreview(j);
      status(`Mesh preview: ${j.nodes} nodes, ${j.elements} elements (${(j.types || []).join("; ")})`);
    } catch (e) { showErr(e); }
  };
  $("#fea-ok").onclick = async () => {
    close();
    const opts = readOpts();
    const fmt = $("#fea-format").value;
    const run = async (overwrite) => {
      status("Meshing...");
      const r = await fetch("/api/fea/export", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ format: fmt, opts, folder, overwrite: !!overwrite }, payload())) });
      if (r.status === 409) {
        const j = await r.json();
        if (confirm("Overwrite " + j.exists + "?")) return run(true);
        status("Export cancelled"); return;
      }
      if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || r.statusText); }
      const ct = r.headers.get("content-type") || "";
      const summary = (m) => `${m.nodes} nodes, ${m.elements} elements (${(m.types || []).join("; ")}), size ${m.size} mm` + (m.quality && m.quality.sicn_min !== undefined ? `, SICN min ${m.quality.sicn_min}` : "");
      if (ct.includes("json")) { const j = await r.json(); status("Wrote " + j.written.join(", ") + ": " + summary(j)); return; }
      let m = {};
      try { m = JSON.parse(r.headers.get("X-Mesh-Info") || "{}"); } catch (e) { /* ignore */ }
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = (name || "mesh").replace(/[^A-Za-z0-9_\-.]+/g, "_") + fmt;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      status("Downloaded " + a.download + ": " + summary(m));
    };
    try { await run(false); } catch (e) { showErr(e); }
  };
};

// ---------------------------------------------------------------- native file / folder dialogs on this PC
/** Opens a native dialog on the PC running the server. kind: open | folder | save. Returns the path or "". */
window.browse = async function (kind, filter, initial, title, saveName) {
  const r = await fetch("/api/dialog", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, filter: filter || "", initial: initial || "", title: title || "", save_name: saveName || "" }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j.path || "";
};
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("button.browse").forEach(b => b.onclick = async () => {
    const inp = document.querySelector(b.dataset.target);
    try {
      const cur = inp.value.trim();
      const p = await window.browse(b.dataset.browse, b.dataset.filter, cur ? cur.replace(/[\\/][^\\/]*\.[A-Za-z0-9]+$/, "") : "");
      if (p) { inp.value = p; inp.dispatchEvent(new Event("change", { bubbles: true })); }
    } catch (e) { showErr(e); }
  });
});

// ------------------------------------------------------------------ document files (.scpart, .scasm, ...)
const DOC_EXT = { part: ".scpart", sketch: ".scsketch", assembly: ".scasm", analysis: ".scfea", explicit: ".scexp" };
/** Opens a document file from any folder (path empty: file dialog). In a project folder that project is opened;
 *  elsewhere the document is added to the open project and stays linked to the file. */
window.openDocFile = async function (path) {
  try {
    if (!path) path = await window.browse("open", "shinycad", "", "Open a ShinyCAD document");
    if (!path) return null;
    const r = await (await postJSON("/api/file/open", { path })).json();
    if (window.projectRefresh) await window.projectRefresh();
    if (window.projectOpenDoc) await window.projectOpenDoc(r.type, r.name, true);
    status(`Opened ${path}` + (r.linked ? ` (in project ${r.project}, saves write the file too)` : ` (project ${r.project})`));
    return r;
  } catch (e) { showErr(e); return null; }
};
/** Writes the document file of a saved document to a folder chosen in the file dialog (or to path). */
window.saveDocFile = async function (type, name, path) {
  try {
    if (!path) path = await window.browse("save", DOC_EXT[type].slice(1), "", "Save " + name + " as a document file", name + DOC_EXT[type]);
    if (!path) return null;
    const r = await (await postJSON("/api/file/saveas", { type, name, path })).json();
    status(`Saved ${r.path}` + (r.linked ? " (linked: later saves write this file too)" : ""));
    if (window.projectRefreshDocs) window.projectRefreshDocs();
    return r;
  } catch (e) { showErr(e); return null; }
};

// ------------------------------------------------------------------ document file menu (Part, Assembly)
/** File menu of a document tab, linked to the open project of the Project tab.
 *  o: { pre ("pt"), type ("part"), label ("part"), pane ("#tab-part"), listUrl, cur() -> {name, dirty},
 *       load(name), save(name, asNew), blank(), setName(name) }.
 *  The list holds the saved documents of the open project; the current document is selected in it
 *  ("(not saved)" when it has no file in the open project). Output folder empty: the project STEP folder. */
function docFileMenu(o) {
  const el = id => document.getElementById(o.pre + "-" + id);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const norm = s => String(s || "").trim().replace(/[^A-Za-z0-9_\-.]+/g, "_").replace(/^_+|_+$/g, "");
  const project = () => (window.projectInfo && window.projectInfo()) || {};
  let names = [];
  let saved = null;                                           // {name, project} of the file the current document is in
  const isSaved = c => !!(c && saved && saved.name === c.name && saved.project === (project().current || "") && names.includes(c.name));

  async function refresh() {
    try { names = await (await api(o.listUrl)).json(); } catch (e) { names = []; }
    render();
  }
  function render() {
    const c = o.cur() || {}, info = project(), d = info.dirs || {};
    const head = el("project");
    head.textContent = info.current ? "Project: " + info.current : "No project open: program folder";
    head.title = d.work || "";
    const ok = isSaved(c);
    const opts = names.map(n => `<option value="${esc(n)}"${ok && n === c.name ? " selected" : ""}>${esc(n)}${ok && n === c.name && c.dirty ? " *" : ""}</option>`);
    if (!ok) opts.unshift(`<option value="" selected>${esc(c.name || o.type)} (not saved)</option>`);
    el("list").innerHTML = opts.join("");
    el("rename").disabled = !ok || !info.current;
    el("openwork").disabled = !info.current;
    el("openstep").disabled = !info.current;
    el("folder").placeholder = d.step ? "empty: " + d.step : "empty: download";
  }
  function markSaved(name) { saved = { name, project: project().current || "" }; refresh(); }
  function markUnsaved() { saved = null; render(); }
  const discard = () => { const c = o.cur(); return !(c && c.dirty) || confirm(`Discard the changes to ${o.label} ${c.name}?`); };

  async function saveAs() {
    const c = o.cur() || {};
    const nn = norm(prompt(`Name of the ${o.label}`, c.name || o.type));
    if (!nn) return false;
    if (names.includes(nn) && !(isSaved(c) && nn === c.name) && !confirm(`${o.label} ${nn} exists in the ${project().current ? "project" : "program folder"}. Overwrite?`)) return false;
    try { await o.save(nn, !(isSaved(c) && nn === c.name)); markSaved(nn); return true; } catch (e) { showErr(e); return false; }
  }
  async function save() {
    const c = o.cur() || {};
    if (!isSaved(c)) return saveAs();
    try { await o.save(c.name, false); markSaved(c.name); return true; } catch (e) { showErr(e); return false; }
  }
  async function rename() {
    const c = o.cur() || {};
    if (!isSaved(c)) return;
    const nn = norm(prompt(`New name of ${o.label} ${c.name}`, c.name));
    if (!nn || nn === c.name) return;
    try {
      await postJSON("/api/project/doc", { op: "rename", type: o.type, name: c.name, new: nn });
      o.setName(nn);
      markSaved(nn);
      if (window.projectRefreshDocs) window.projectRefreshDocs();
      status(`Renamed ${o.label} ${c.name} to ${nn}`);
    } catch (e) { showErr(e); }
  }
  const openFolder = sub => postJSON("/api/project/open_folder", { sub }).catch(showErr);

  el("list").onchange = async () => {
    const name = el("list").value;
    if (!name) return;
    if (!discard()) { render(); return; }
    try { await o.load(name); markSaved(name); status(`Loaded ${o.label} ${name}`); } catch (e) { showErr(e); render(); }
  };
  el("rename").parentElement.insertAdjacentHTML("afterend", `<div class="row"><button type="button" id="${o.pre}-openfile" title="Open a ShinyCAD document file (${Object.values(DOC_EXT).join(" ")}) from any folder">Open file…</button><button type="button" id="${o.pre}-savefile" title="Save the ${o.label} as a document file (${DOC_EXT[o.type]}) in any folder">Save as file…</button></div>`);
  el("openfile").onclick = () => { if (discard()) window.openDocFile(); };
  el("savefile").onclick = async () => {
    const c = o.cur() || {};
    if (!project().current) { showErr(new Error("Open or create a project first")); return; }
    if (!isSaved(c) || c.dirty) { if (!(await save())) return; }
    window.saveDocFile(o.type, (o.cur() || {}).name);
  };
  el("new").onclick = () => { if (discard()) { o.blank(); markUnsaved(); } };
  el("save").onclick = save;
  el("saveas").onclick = saveAs;
  el("rename").onclick = rename;
  el("openwork").onclick = () => openFolder("work");
  el("openstep").onclick = () => openFolder("step");
  el("list").closest(".dd").querySelector(".dd-btn").addEventListener("click", () => refresh());
  document.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && !document.querySelector(o.pane).hidden) { e.preventDefault(); save(); }
  });
  return { refresh, render, markSaved, markUnsaved, isSaved: () => isSaved(o.cur()) };
}
