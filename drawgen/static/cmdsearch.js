// Command search (Ctrl+K or the Search button of the tab bar): finds the buttons of all tabs by their text, tooltip,
// tab, menu and a few other names, and runs the chosen one in its tab.
(function () {
  const $ = s => document.querySelector(s);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const PANES = { "tab-project": ["project", "Project"], "tab-annotate": ["annotate", "Drawings"], "tab-sketch": ["sketch", "Sketch"],
    "tab-part": ["part", "Part"], "tab-asm": ["asm", "Assembly"], "tab-fea": ["fea", "Analysis"], "tab-xp": ["xp", "Explicit"] };
  // other names of commands (matched as words of the text or tooltip)
  const ALIAS = {
    "import geometry": "step stp stl iges brep open load model mesh", "extrude": "pad boss", "cut": "pocket remove", "revolve": "lathe turn",
    "fillet": "round radius", "chamfer": "bevel", "pattern": "array copy repeat", "mirror": "symmetry", "shell": "hollow",
    "hole": "drill thread", "sweep": "path", "loft": "blend", "measure": "distance", "trim": "cut extend",
    "export step": "save stp", "export mesh": "fem msh", "make drawing": "sheet 2d", "coincident": "join connect",
    "dimension": "size length", "spline": "curve", "check": "clean fix", "section": "cut plane clip",
  };
  const CS = { items: [], shown: [], sel: 0 };

  function label(b) {
    const t = (b.textContent || "").replace(/\s+/g, " ").replace(/[▾…]/g, "").trim();
    return t || (b.getAttribute("aria-label") || b.title || "").split(/[:(]/)[0].trim();
  }

  /** All commands: the buttons of the tab panes (not in tables, dialogs or file choosers) and the tabs. */
  function collect() {
    const out = [], seen = new Set();
    document.querySelectorAll(".tabs .tab").forEach(b => out.push({ el: b, label: "Go to " + b.textContent.trim(), title: "Tab", where: "Tabs", tab: null }));
    for (const id of Object.keys(PANES)) {
      const pane = document.getElementById(id);
      if (!pane) continue;
      pane.querySelectorAll("button").forEach(b => {
        if (b.closest("table, .modal, dialog, .dlg, [id$=dialog], .cmd-search") || b.classList.contains("browse") || b.classList.contains("dd-btn")) return;
        const l = label(b);
        if (!l || l.length < 2 || /^[×✕+\-<>▲▼←→]+$/.test(l)) return;
        const dd = b.closest(".dd");
        const menu = dd ? label(dd.querySelector(".dd-btn") || dd) : "";
        const where = PANES[id][1] + (menu ? " › " + menu : "");
        const key = where + "|" + l + "|" + (b.title || "");
        if (seen.has(key)) return;
        seen.add(key);
        const a = ALIAS[l.toLowerCase()] || "";
        out.push({ el: b, label: l, title: b.title || "", where, tab: PANES[id][0], alias: a });
      });
    }
    return out;
  }

  function score(it, words) {
    const L = it.label.toLowerCase(), hay = (it.label + " " + it.title + " " + it.where + " " + (it.alias || "")).toLowerCase();
    let s = 0;
    for (const w of words) {
      if (!hay.includes(w)) return -1;
      s += L.startsWith(w) ? 30 : L.includes(w) ? 20 : (it.alias || "").includes(w) ? 12 : it.title.toLowerCase().includes(w) ? 8 : 2;
    }
    if (it.el.disabled) s -= 5;
    return s;
  }

  function render() {
    const q = $("#cs-input").value.trim().toLowerCase();
    const words = q.split(/\s+/).filter(Boolean);
    CS.shown = !words.length ? [] : CS.items.map(it => [score(it, words), it]).filter(x => x[0] >= 0)
      .sort((a, b) => b[0] - a[0] || a[1].label.localeCompare(b[1].label)).slice(0, 40).map(x => x[1]);
    CS.sel = Math.min(CS.sel, Math.max(0, CS.shown.length - 1));
    $("#cs-list").innerHTML = !words.length ? '<p class="hint">Type a command name or a word of its tooltip, for example stl, fillet, export.</p>'
      : !CS.shown.length ? '<p class="hint">No command found.</p>'
      : CS.shown.map((it, k) => `<div class="cs-item${k === CS.sel ? " on" : ""}${it.el.disabled ? " off" : ""}" data-k="${k}"><b>${esc(it.label)}</b> <span class="cs-where">${esc(it.where)}</span>${it.title ? `<div class="cs-title">${esc(it.title)}</div>` : ""}</div>`).join("");
    $("#cs-list").querySelectorAll(".cs-item").forEach(d => {
      d.onmousemove = () => { if (CS.sel !== +d.dataset.k) { CS.sel = +d.dataset.k; mark(); } };
      d.onclick = () => run(CS.shown[+d.dataset.k]);
    });
  }
  function mark() {
    $("#cs-list").querySelectorAll(".cs-item").forEach(d => d.classList.toggle("on", +d.dataset.k === CS.sel));
    const on = $("#cs-list .cs-item.on");
    if (on) on.scrollIntoView({ block: "nearest" });
  }

  /** The result list drops down below the search field of the tab bar. */
  function place() {
    const r = $("#cs-input").getBoundingClientRect(), box = $("#cmd-search");
    box.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 560)) + "px";
    box.style.top = (r.bottom + 4) + "px";
  }
  function open() {
    if ($("#cmd-search").hidden) { CS.items = collect(); CS.sel = 0; }
    $("#cmd-search").hidden = false;
    place();
    render();
  }
  function close() {
    $("#cmd-search").hidden = true;
    $("#cs-input").value = "";
    $("#cs-input").blur();
  }

  function run(it) {
    if (!it) return;
    if (it.el.disabled) { status(`${it.label} is not available now (${it.where})`); return; }
    close();
    if (it.tab && document.getElementById("tab-" + it.tab).hidden) {
      if (it.tab === "sketch") showTab("sketch");
      else { const t = document.querySelector(`.tabs .tab[data-tab=${it.tab}]`); if (t) t.click(); else showTab(it.tab); }
    }
    // a command in a drop-down menu: the menu is opened so that its fields can be seen
    const dd = it.el.closest(".dd");
    if (dd && !dd.classList.contains("open") && it.el.closest(".dd-menu")) dd.classList.add("open");
    it.el.click();
    status(`${it.label} (${it.where})`);
  }

  window.commandSearch = { open, close, collect, run: q => { $("#cs-input").value = q; open(); run(CS.shown[0]); } };

  document.addEventListener("DOMContentLoaded", () => {
    document.body.insertAdjacentHTML("beforeend", '<div id="cmd-search" class="cmd-search" hidden><div id="cs-list"></div></div>');
    const nav = $(".tabs");
    if (nav) nav.insertAdjacentHTML("beforeend", '<span class="cs-field" title="Search the commands of all tabs (Ctrl+K)"><span class="cs-glass">⌕</span>' +
      '<input type="search" id="cs-input" placeholder="Search commands (Ctrl+K)" autocomplete="off" spellcheck="false"></span>');
    const inp = $("#cs-input");
    inp.onfocus = open;
    inp.oninput = () => { CS.sel = 0; open(); };
    inp.onkeydown = e => {
      if (e.key === "ArrowDown") { e.preventDefault(); CS.sel = Math.min(CS.sel + 1, CS.shown.length - 1); mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); CS.sel = Math.max(CS.sel - 1, 0); mark(); }
      else if (e.key === "Enter") { e.preventDefault(); run(CS.shown[CS.sel]); }
      else if (e.key === "Escape") { e.preventDefault(); close(); }
      e.stopPropagation();
    };
    // a click outside the field and the list closes the list
    document.addEventListener("mousedown", e => {
      if (!$("#cmd-search").hidden && !e.target.closest("#cmd-search, .cs-field")) close();
    }, true);
    window.addEventListener("resize", () => { if (!$("#cmd-search").hidden) place(); });
    document.addEventListener("keydown", e => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); inp.focus(); open(); }
    }, true);
  });
})();
