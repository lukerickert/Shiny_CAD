// Project tab: projects folder, project list, documents of the open project (rename, copy, versions, delete),
// exports, saved project states. Server: /api/projects, /api/project/* (drawgen/projects.py).
(function () {
  const $ = s => document.querySelector(s);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const PJ = { info: null, docs: null, states: [], sort: { key: "name", dir: 1 }, allSort: { key: "opened", dir: -1 } };
  try { const as = JSON.parse(localStorage.getItem("pj-allsort") || "null"); if (as && as.key && (as.dir === 1 || as.dir === -1)) PJ.allSort = as; } catch (e) { /* default order */ }
  try { const ps = JSON.parse(localStorage.getItem("pj-sort") || "null"); if (ps && ps.key && (ps.dir === 1 || ps.dir === -1)) PJ.sort = ps; } catch (e) { /* default order */ }
  const TYPE_LABEL = { part: "Part", sketch: "Sketch", assembly: "Assembly", analysis: "Analysis", explicit: "Explicit" };
  const TAB_OF = { part: "part", sketch: "sketch", assembly: "asm", analysis: "fea", explicit: "xp" };
  const kb = n => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : n > 1024 ? (n / 1024).toFixed(0) + " kB" : n + " B";

  async function refreshProjects() {
    try {
      const r = await api("/api/projects");
      PJ.info = await r.json();
    } catch (e) { showErr(e); return; }
    const i = PJ.info;
    $("#pj-root").value = i.root || "";
    const rr = i.recent_roots || [];
    $("#pj-recent").innerHTML = `<option value="">Recent folders (${rr.length})</option>` + rr.map((r, k) => `<option value="${k}"${r.exists ? "" : " disabled"}>${esc(r.path)} (${r.projects} project${r.projects === 1 ? "" : "s"}${r.project ? ", last: " + esc(r.project) : ""})${r.exists ? "" : " (not found)"}</option>`).join("");
    const sel = $("#pj-list");
    sel.innerHTML = i.projects.length ? i.projects.map(p => `<option value="${esc(p.name)}"${p.name === i.current ? " selected" : ""}>${esc(p.name)} (${p.docs} docs, ${esc(p.modified)})</option>`).join("") : '<option value="">(no projects)</option>';
    $("#pj-current").textContent = i.current ? "Open: " + i.current : (i.root ? "No project open: the documents are read from the program folder" : "Set the projects folder");
    $("#pj-title").textContent = i.current || "No project open";
    const cur = i.projects.find(p => p.name === i.current);
    $("#pj-desc").value = cur ? cur.description || "" : "";
    $("#pj-desc").disabled = !cur;
    $("#pj-rename").disabled = !cur;
    $("#pj-folder").disabled = !cur;
    $("#pj-paths").textContent = cur ? `${i.root}\\${cur.name}\\  work (documents), drawings (PDF, DXF, SVG, FCStd), step (STEP and mesh exports), step_import (copies of imported STEP files), analysis (solver files and reports), explicit (OpenCourant model and run folders), versions, states` : "";
    $("#pj-adopt").hidden = !(i.root && !i.projects.length);
    renderAll();
    if (i.current) { await refreshDocs(); await refreshStates(); }
    else { $("#pj-docs").innerHTML = ""; $("#pj-exports").innerHTML = ""; $("#pj-states").innerHTML = ""; }
    // the saved lists of the tabs follow the project
    for (const fn of ["__partRefresh", "__asmRefresh", "__sketchRefresh", "__feaRefresh", "__xpRefresh"]) { try { if (window[fn]) window[fn](); } catch (e) { /* tab not initialised */ } }
  }

  /** All known projects of this PC (any folder): open, sort, filter, find in a folder, remove from the list. */
  function renderAll() {
    const box = $("#pj-all");
    const list = (PJ.info && PJ.info.known) || [];
    const filt = ($("#pj-allfilter").value || "").toLowerCase();
    let rows = list.filter(x => !filt || [x.name, x.folder, x.description].join(" ").toLowerCase().includes(filt));
    const S = PJ.allSort;
    rows = rows.slice().sort((a, b) => {
      const va = a[S.key], vb = b[S.key];
      const c = typeof va === "number" ? va - vb : String(va || "").localeCompare(String(vb || ""), undefined, { numeric: true, sensitivity: "base" });
      return (c || a.name.localeCompare(b.name)) * S.dir;
    });
    const limit = $("#pj-allshow").checked || filt ? rows.length : 8;
    if (!list.length) { box.innerHTML = '<p class="hint">No projects known yet. Use Find projects with the folder that holds your projects (for example the folder above the project folders).</p>'; return; }
    const th = (key, label) => `<th class="pj-sort${S.key === key ? " on" : ""}" data-asort="${key}">${label}${S.key === key ? (S.dir > 0 ? " ▲" : " ▼") : ""}</th>`;
    box.innerHTML = `<table class="pj-table"><tr>${th("name", "Project")}${th("folder", "Folder")}${th("description", "Description")}${th("docs", "Documents")}${th("modified", "Last change")}${th("opened", "Last opened")}<th></th></tr>` +
      rows.slice(0, limit).map((x, k) => `<tr class="${x.current ? "pj-cur" : ""}${x.exists ? "" : " pj-missing"}" data-k="${list.indexOf(x)}"><td><b>${esc(x.name)}</b>${x.current ? " (open)" : ""}</td><td title="${esc(x.path)}">${esc(x.folder)}</td><td>${esc(x.description || "")}</td><td>${x.exists ? x.docs : "not found"}</td><td>${esc(x.modified)}</td><td>${esc((x.opened || "").slice(0, 16))}</td>` +
        `<td class="pj-actions">${x.exists && !x.current ? '<button type="button" data-aop="open">Open</button>' : ""}<button type="button" data-aop="forget" title="Remove from this list (the folder is not changed)">×</button></td></tr>`).join("") + `</table>` +
      (rows.length > limit ? `<p class="hint">${rows.length - limit} more: filter, or check Show all.</p>` : "");
    box.querySelectorAll("th[data-asort]").forEach(h => h.onclick = () => {
      const k = h.dataset.asort;
      PJ.allSort = PJ.allSort.key === k ? { key: k, dir: -PJ.allSort.dir } : { key: k, dir: (k === "modified" || k === "opened" || k === "docs") ? -1 : 1 };
      try { localStorage.setItem("pj-allsort", JSON.stringify(PJ.allSort)); } catch (e) { /* order kept for this session */ }
      renderAll();
    });
    box.querySelectorAll("button[data-aop]").forEach(b => b.onclick = async () => {
      const x = list[+b.closest("tr").dataset.k];
      try {
        if (b.dataset.aop === "open") {
          await postJSON("/api/projects/open", { path: x.path });
          state.files = []; renderFiles();
          await refreshProjects();
          status("Project " + x.name + " opened (" + x.folder + ")");
        } else {
          await postJSON("/api/projects/forget", { path: x.path });
          await refreshProjects();
        }
      } catch (e) { showErr(e); }
    });
  }
  async function scanProjects() {
    const folder = $("#pj-scanpath").value.trim();
    if (!folder) { showErr(new Error("Enter or choose the folder to search")); return; }
    try {
      busy(true);
      const r = await (await postJSON("/api/projects/scan", { folder })).json();
      PJ.info = r;
      await refreshProjects();
      status(`${r.found.length} project(s) found in ${folder}`);
    } catch (e) { showErr(e); } finally { busy(false); }
  }

  async function refreshDocs() {
    try { PJ.docs = await (await api("/api/project/docs")).json(); } catch (e) { showErr(e); return; }
    renderDocs();
    renderExports();
  }

  function renderDocs() {
    const box = $("#pj-docs");
    const d = PJ.docs;
    if (!d) { box.innerHTML = ""; return; }
    const filt = ($("#pj-filter").value || "").toLowerCase();
    const links = $("#pj-showlinks").checked;
    const rows = d.docs.filter(x => !filt || x.name.toLowerCase().includes(filt) || x.type.includes(filt));
    if (!rows.length) { box.innerHTML = '<p class="hint">No documents. Save a part, sketch, assembly or analysis in its tab.</p>'; return; }
    // sort by the clicked column (a second click reverses); ties by name
    const S = PJ.sort;
    const val = x => S.key === "type" ? TYPE_LABEL[x.type] : x[S.key];
    rows.sort((a, b) => {
      const va = val(a), vb = val(b);
      const c = typeof va === "number" && typeof vb === "number" ? va - vb : String(va || "").localeCompare(String(vb || ""), undefined, { numeric: true, sensitivity: "base" });
      return (c || a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" })) * S.dir;
    });
    const th = (key, label) => `<th class="pj-sort${S.key === key ? " on" : ""}" data-sort="${key}" title="Sort by ${label.toLowerCase()} (click again to reverse)">${label}${S.key === key ? (S.dir > 0 ? " ▲" : " ▼") : ""}</th>`;
    box.innerHTML = `<table class="pj-table"><tr>${th("name", "Name")}${th("type", "Type")}${th("version", "Version")}${th("note", "Note")}${th("modified", "Modified")}${th("size", "Size")}<th title="Document file in the project folder; ↔ a linked file outside the project (written at each save)">File</th>${links ? "<th>Uses</th><th>Used by</th><th>Exports</th>" : ""}<th></th></tr>` +
      rows.map(x => `<tr data-type="${x.type}" data-name="${esc(x.name)}"><td><b>${esc(x.name)}</b></td><td>${TYPE_LABEL[x.type]}</td><td>${x.version ? "v" + x.version : "–"}</td><td>${esc(x.note)}</td><td>${esc(x.modified)}</td><td>${kb(x.size)}</td>` +
        `<td><span title="${esc(x.package_path || "")}">${esc(x.package || "")}</span>${x.linked ? `<br><span class="pj-linked" title="${esc(x.linked)}">↔ ${esc(x.linked)}</span> <button type="button" class="small" data-op="unlink" title="End the link (the file is not changed)">×</button>` : ""}</td>` +
        (links ? `<td>${usesHtml(x.links)}</td>` +
          `<td>${x.used_by.map(l => `<span class="pj-link" data-goto="${l.type}:${esc(l.name)}">${esc(l.name)}</span>`).join(", ")}</td><td>${x.exports.map(esc).join(", ")}</td>` : "") +
        `<td class="pj-actions"><button type="button" data-op="open" title="Open in its tab">Open</button><button type="button" data-op="rename">Rename</button><button type="button" data-op="copy">Copy</button><button type="button" data-op="snapshot" title="Store a numbered version with a note">Version</button><button type="button" data-op="versions" title="List, restore">Versions…</button><button type="button" data-op="move" title="Move or copy to another project">Move…</button><button type="button" data-op="savefile" title="Save as a document file in any folder">File…</button><button type="button" data-op="delete" title="Move to the project trash folder">×</button></td></tr>`).join("") + `</table>`;
    box.querySelectorAll("th[data-sort]").forEach(h => h.onclick = () => {
      const k = h.dataset.sort;
      // a new column: names A to Z, dates and sizes newest / largest first
      PJ.sort = PJ.sort.key === k ? { key: k, dir: -PJ.sort.dir } : { key: k, dir: (k === "modified" || k === "size" || k === "version") ? -1 : 1 };
      try { localStorage.setItem("pj-sort", JSON.stringify(PJ.sort)); } catch (e) { /* the order is kept for this session only */ }
      renderDocs();
    });
    box.querySelectorAll("button[data-op]").forEach(b => b.onclick = () => docOp(b.dataset.op, b.closest("tr").dataset.type, b.closest("tr").dataset.name));
    box.querySelectorAll(".pj-link").forEach(s => s.onclick = () => { const [t, n] = s.dataset.goto.split(":"); openDoc(t, n); });
  }

  /** Uses column: parts and assemblies as links; the solids of a STEP file after the file name; counts as x N. */
  function usesHtml(links) {
    const n = l => (l.count > 1 ? ` ×${l.count}` : "");
    const out = [];
    for (const l of links) if (l.type === "part" || l.type === "assembly") out.push(`<span class="pj-link" data-goto="${l.type}:${esc(l.name)}">${esc(l.name)}</span>${n(l)}`);
    const files = new Map();
    for (const l of links) if (l.type === "step") { if (!files.has(l.name)) files.set(l.name, []); files.get(l.name).push(l); }
    for (const [f, ls] of files) {
      const solids = ls.filter(l => l.solid);
      const whole = ls.filter(l => !l.solid).reduce((a, l) => a + (l.count || 1), 0);
      const items = solids.map(l => esc(l.solid) + n(l)).concat(whole && solids.length ? ["whole file" + (whole > 1 ? " ×" + whole : "")] : []);
      out.push(`<span title="${esc(ls[0].path || "")}">${esc(f)}</span>` + (items.length ? ": " + items.join(", ") : (whole > 1 ? " ×" + whole : "")));
    }
    for (const l of links) if (l.type === "inp") out.push(`<span title="${esc(l.path || "")}">${esc(l.name)}</span>`);
    return out.join("<br>");
  }

  function renderExports() {
    const e = PJ.docs && PJ.docs.exports;
    const box = $("#pj-exports");
    if (!e) { box.innerHTML = ""; return; }
    const list = (title, arr) => `<div class="pj-exp"><strong>${title}</strong>${arr.length ? `<table class="pj-table small">${arr.map(f => `<tr><td>${esc(f.name)}</td><td>${esc(f.modified)}</td><td>${kb(f.size)}</td></tr>`).join("")}</table>` : '<p class="hint">none</p>'}</div>`;
    box.innerHTML = list("drawings/", e.drawings) + list("step/", e.step) + list("step_import/", e.step_import);
  }

  async function openDoc(type, name, noConfirm) {
    const loaders = { part: window.__partLoadNamed, assembly: window.__asmLoadNamed, sketch: window.__sketchLoadNamed, analysis: window.__feaLoadNamed, explicit: window.__xpLoadNamed };
    const cur = { part: window.__partCurrent, assembly: window.__asmCurrent, analysis: window.__feaCurrent, explicit: window.__xpCurrent }[type];
    const c = cur && cur();
    if (c && c.dirty && !noConfirm && !confirm(`Discard the changes to the current ${type}?`)) return;
    showTab(TAB_OF[type]);
    try { await loaders[type](name); status(`Loaded ${type} ${name}`); } catch (e) { showErr(e); }
  }

  async function docOp(op, type, name) {
    try {
      if (op === "open") return openDoc(type, name);
      if (op === "rename") {
        const nn = prompt(`New name for ${type} ${name}`, name);
        if (!nn || nn === name) return;
        const r = await (await postJSON("/api/project/doc", { op: "rename", type, name, new: nn })).json();
        const cur = { part: [window.__partCurrent, window.__partSetName], assembly: [window.__asmCurrent, window.__asmSetName], analysis: [window.__feaCurrent, window.__feaSetName], explicit: [window.__xpCurrent, window.__xpSetName] }[type];
        if (cur && cur[0] && cur[1] && (cur[0]() || {}).name === name) cur[1](r.name);
      } else if (op === "copy") {
        const nn = prompt(`Name of the copy of ${type} ${name}`, name + " copy");
        if (!nn) return;
        await postJSON("/api/project/doc", { op: "copy", type, name, new: nn });
      } else if (op === "snapshot") {
        const note = prompt(`Version note for ${type} ${name}`, "");
        if (note === null) return;
        const r = await (await postJSON("/api/project/doc", { op: "snapshot", type, name, note })).json();
        status(`${name}: version ${r.version} stored`);
      } else if (op === "versions") {
        return showVersions(type, name);
      } else if (op === "move") {
        return showMove(type, name);
      } else if (op === "savefile") {
        return window.saveDocFile(type, name);
      } else if (op === "unlink") {
        await postJSON("/api/file/unlink", { type, name });
      } else if (op === "delete") {
        if (!confirm(`Move ${type} ${name} to the project trash folder?`)) return;
        await postJSON("/api/project/doc", { op: "delete", type, name });
      }
      await refreshDocs();
      for (const fn of ["__partRefresh", "__asmRefresh", "__sketchRefresh", "__feaRefresh", "__xpRefresh"]) { try { if (window[fn]) window[fn](); } catch (e) { /* ignore */ } }
    } catch (e) { showErr(e); }
  }

  /** Move or copy a document to another project, with its versions, drawing annotations, sketch images and analysis
   *  folders; optionally with the documents it uses. */
  function showMove(type, name) {
    const others = ((PJ.info && PJ.info.projects) || []).filter(p => p.name !== PJ.info.current);
    if (!others.length) { showErr(new Error("No other project. Create one in the project list first.")); return; }
    const doc = ((PJ.docs && PJ.docs.docs) || []).find(d => d.type === type && d.name === name) || { links: [], used_by: [] };
    const uses = doc.links.filter(l => l.type === "part" || l.type === "assembly");
    const dlg = $("#pj-mdialog");
    $("#pj-mtitle").textContent = `${TYPE_LABEL[type]} ${name}: move or copy to another project`;
    $("#pj-mtarget").innerHTML = others.map(p => `<option value="${esc(p.name)}">${esc(p.name)}</option>`).join("");
    $("#pj-museslbl").hidden = !uses.length;
    $("#pj-muses").checked = true;
    $("#pj-musestext").textContent = "With the documents it uses: " + uses.map(l => l.name).join(", ") + " (moved only when no other document here uses them, else copied)";
    const note = () => {
      const mv = dlg.querySelector("input[name=pj-mmode]:checked").value === "move";
      $("#pj-mgo").textContent = mv ? "Move" : "Copy";
      $("#pj-mnote").textContent = (mv && doc.used_by.length ? `Used here by ${doc.used_by.map(u => u.name).join(", ")}: after the move these references are missing (Copy keeps them). ` : "") +
        "Versions, drawing annotations and layouts, sketch images and analysis folders go along. Documents open in their tabs keep their current state; save them only in the project they belong to.";
    };
    dlg.querySelectorAll("input[name=pj-mmode]").forEach(r => r.onchange = note);
    note();
    dlg.hidden = false;
    $("#pj-mclose").onclick = () => { dlg.hidden = true; };
    $("#pj-mgo").onclick = async () => {
      const mode = dlg.querySelector("input[name=pj-mmode]:checked").value, target = $("#pj-mtarget").value;
      try {
        const r = await (await postJSON("/api/project/doc", { op: mode === "move" ? "move" : "copy_to", type, name, project: target, with_uses: uses.length > 0 && $("#pj-muses").checked })).json();
        dlg.hidden = true;
        status(r.done.map(d => `${TYPE_LABEL[d.type]} ${d.name} ${d.mode === "move" ? "moved" : "copied"}`).join(", ") + " to project " + target);
        await refreshProjects();
      } catch (e) { showErr(e); }
    };
  }

  async function showVersions(type, name) {
    let vs;
    try { vs = await (await postJSON("/api/project/doc", { op: "versions", type, name })).json(); } catch (e) { showErr(e); return; }
    const dlg = $("#pj-vdialog");
    $("#pj-vtitle").textContent = `${TYPE_LABEL[type]} ${name}: versions`;
    $("#pj-vlist").innerHTML = vs.length ? `<table class="pj-table">${vs.map(v => `<tr><td>v${v.version}</td><td>${esc(v.date)}</td><td>${esc(v.note)}</td><td><button type="button" data-restore="${v.version}">Restore</button><button type="button" data-ascopy="${v.version}">Restore as copy…</button></td></tr>`).join("")}</table>` : '<p class="hint">No versions. Use Version in the document list to store one.</p>';
    dlg.hidden = false;
    $("#pj-vclose").onclick = () => { dlg.hidden = true; };
    $("#pj-vlist").querySelectorAll("button[data-restore]").forEach(b => b.onclick = async () => {
      if (!confirm(`Replace the working file of ${name} with version ${b.dataset.restore}? (store a version of the current state first if needed)`)) return;
      try { await postJSON("/api/project/doc", { op: "restore", type, name, version: +b.dataset.restore }); dlg.hidden = true; status(`${name}: version ${b.dataset.restore} restored`); refreshDocs(); } catch (e) { showErr(e); }
    });
    $("#pj-vlist").querySelectorAll("button[data-ascopy]").forEach(b => b.onclick = async () => {
      const nn = prompt("Name of the copy", `${name} v${b.dataset.ascopy}`);
      if (!nn) return;
      try { await postJSON("/api/project/doc", { op: "restore", type, name, version: +b.dataset.ascopy, as_copy: nn }); dlg.hidden = true; refreshDocs(); } catch (e) { showErr(e); }
    });
  }

  // ------------------------------------------------------------------ states
  async function refreshStates() {
    try { PJ.states = await (await api("/api/project/states")).json(); } catch (e) { PJ.states = []; }
    const box = $("#pj-states");
    box.innerHTML = PJ.states.length ? `<table class="pj-table">${PJ.states.map(s => `<tr><td><b>${esc(s.name)}</b></td><td>${esc(s.modified)}</td><td><button type="button" data-load="${esc(s.name)}">Load</button><button type="button" data-del="${esc(s.name)}">×</button></td></tr>`).join("")}</table>` : '<p class="hint">No saved states.</p>';
    box.querySelectorAll("button[data-load]").forEach(b => b.onclick = () => loadState(b.dataset.load));
    box.querySelectorAll("button[data-del]").forEach(b => b.onclick = async () => { if (!confirm(`Delete state ${b.dataset.del}?`)) return; await api("/api/project/state/" + encodeURIComponent(b.dataset.del), { method: "DELETE" }); refreshStates(); });
  }

  function currentState() {
    const tab = (document.querySelector(".tab.active") || {}).dataset ? document.querySelector(".tab.active").dataset.tab : "project";
    const cur = fn => { try { return window[fn] ? window[fn]() : null; } catch (e) { return null; } };
    return {
      saved: new Date().toISOString(), tab,
      part: (cur("__partCurrent") || {}).name || null,
      assembly: (cur("__asmCurrent") || {}).name || null,
      sketch: (cur("__sketchCurrent") || {}).name || null,
      analysis: (cur("__feaCurrent") || {}).name || null,
      explicit: (cur("__xpCurrent") || {}).name || null,
      models: (state.files || []).map(f => ({ file_id: f.file_id, name: f.name, source: f.source || "", checked: f.parts.filter(p => p.checked).map(p => p.id) })),
      settings: readSettings(),
      drawing: $("#ann-drawing") ? $("#ann-drawing").value : null,
    };
  }

  async function saveState() {
    const name = ($("#pj-statename").value || "").trim() || new Date().toISOString().slice(0, 16).replace("T", " ").replace(":", "-");
    try {
      await api("/api/project/state/" + encodeURIComponent(name), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentState()) });
      status("State " + name + " saved");
      refreshStates();
    } catch (e) { showErr(e); }
  }

  async function loadState(name) {
    let st;
    try { st = await (await api("/api/project/state/" + encodeURIComponent(name))).json(); } catch (e) { showErr(e); return; }
    busy(true, "Loading state " + name + " ...");
    try {
      if (st.part && window.__partLoadNamed) { try { await window.__partLoadNamed(st.part); } catch (e) { status("Part " + st.part + ": " + e.message, true); } }
      if (st.assembly && window.__asmLoadNamed) { try { await window.__asmLoadNamed(st.assembly); } catch (e) { status("Assembly " + st.assembly + ": " + e.message, true); } }
      if (st.sketch && window.__sketchLoadNamed) { try { await window.__sketchLoadNamed(st.sketch); } catch (e) { /* unsaved sketch */ } }
      if (st.analysis && window.__feaLoadNamed) { try { await window.__feaLoadNamed(st.analysis); } catch (e) { /* unsaved analysis */ } }
      if (st.explicit && window.__xpLoadNamed) { try { await window.__xpLoadNamed(st.explicit); } catch (e) { /* unsaved explicit analysis */ } }
      if (st.settings) applySettings(st.settings);
      // Models: parts and assemblies are rebuilt from their saved files, STEP files reopened by path
      state.files = [];
      for (const m of st.models || []) {
        try {
          let res = null;
          if (m.file_id.startsWith("part_")) {
            const p = await (await api("/api/part/file/" + encodeURIComponent(m.name.replace(/\.part$/, "")))).json();
            res = await (await postJSON("/api/part/to_drawings", { part: p })).json();
          } else if (m.file_id.startsWith("asm_")) {
            const a = await (await api("/api/assembly/file/" + encodeURIComponent(m.name.replace(/\.asm$/, "")))).json();
            res = await (await postJSON("/api/assembly/to_drawings", { assembly: a })).json();
          } else if (m.source) {
            res = await (await postJSON("/api/open_path", { path: m.source })).json();
          }
          if (res) res.files.forEach(f => { f.parts.forEach(p => p.checked = !m.checked || m.checked.includes(p.id)); state.files.push(f); });
        } catch (e) { status("Model " + m.name + ": " + e.message, true); }
      }
      renderFiles();
      if (state.files.length) await preview(false);
      if (st.tab && st.tab !== "project") showTab(st.tab);
      status("State " + name + " loaded");
    } finally { busy(false); }
  }

  // ------------------------------------------------------------------ project actions
  async function setRoot() {
    const path = $("#pj-root").value.trim();
    if (!path) return;
    try { await api("/api/projects/root", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) }); await refreshProjects(); } catch (e) { showErr(e); }
  }
  /** A recently used projects folder: set as the projects folder, then the project last opened there is opened. */
  async function openRecentRoot() {
    const sel = $("#pj-recent"), r = ((PJ.info && PJ.info.recent_roots) || [])[+sel.value];
    sel.value = "";
    if (!r) return;
    try {
      await api("/api/projects/root", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: r.path }) });
      if (r.project) { await postJSON("/api/projects/open", { name: r.project }); state.files = []; renderFiles(); }
      await refreshProjects();
      status("Projects folder " + r.path + (r.project ? ", project " + r.project + " opened" : ""));
    } catch (e) { showErr(e); }
  }
  async function newProject() {
    const name = prompt("Name of the new project");
    if (!name) return;
    const description = prompt("Description (optional)", "") || "";
    try { await postJSON("/api/projects", { name, description, open: true }); await refreshProjects(); } catch (e) { showErr(e); }
  }
  async function openProject() {
    const name = $("#pj-list").value;
    if (!name) return;
    try { await postJSON("/api/projects/open", { name }); await refreshProjects(); state.files = []; renderFiles(); status("Project " + name + " opened"); } catch (e) { showErr(e); }
  }
  async function adopt() {
    const name = prompt("Name of the project that takes over the existing parts, sketches and assemblies (the files are moved from the program folder)", "legacy");
    if (!name) return;
    try { const r = await (await postJSON("/api/projects/adopt", { name, move: true })).json(); await refreshProjects(); status(`${r.moved} file(s) moved into project ${name}`); } catch (e) { showErr(e); }
  }
  async function renameProject() {
    const cur = PJ.info && PJ.info.current;
    if (!cur) return;
    const nn = prompt("New project name", cur);
    if (!nn || nn === cur) return;
    try { await api("/api/projects/" + encodeURIComponent(cur), { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rename: nn }) }); await refreshProjects(); } catch (e) { showErr(e); }
  }
  async function saveDesc() {
    const cur = PJ.info && PJ.info.current;
    if (!cur) return;
    try { await api("/api/projects/" + encodeURIComponent(cur), { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ description: $("#pj-desc").value }) }); } catch (e) { showErr(e); }
  }
  async function openFolder(sub) {
    try { await postJSON("/api/project/open_folder", { sub: sub || "" }); } catch (e) { showErr(e); }
  }

  window.projectShown = function () { refreshProjects(); };
  window.projectInfo = () => PJ.info;
  window.projectRefreshDocs = refreshDocs;
  window.projectRefresh = refreshProjects;
  window.projectOpenDoc = openDoc;

  document.addEventListener("DOMContentLoaded", () => {
    $("#pj-setroot").onclick = setRoot;
    $("#pj-recent").onchange = openRecentRoot;
    $("#pj-scan").onclick = scanProjects;
    $("#pj-allfilter").oninput = renderAll;
    $("#pj-allshow").onchange = renderAll;
    $("#pj-new").onclick = newProject;
    $("#pj-open").onclick = openProject;
    $("#pj-adopt").onclick = adopt;
    $("#pj-rename").onclick = renameProject;
    $("#pj-desc").onchange = saveDesc;
    $("#pj-folder").onclick = () => openFolder("");
    document.querySelectorAll("button[data-pjfolder]").forEach(b => b.onclick = () => openFolder(b.dataset.pjfolder));
    $("#pj-refresh").onclick = refreshDocs;
    $("#pj-filter").oninput = renderDocs;
    $("#pj-showlinks").onchange = renderDocs;
    $("#pj-savestate").onclick = saveState;
    $("#pj-openfile").onclick = () => window.openDocFile();
    // run.py --open <file> (double-click in Explorer): /?open=<path>
    const toOpen = new URLSearchParams(location.search).get("open");
    if (toOpen) history.replaceState(null, "", location.pathname);
    refreshProjects().then(() => { if (toOpen) window.openDocFile(toOpen); });
  });
})();
