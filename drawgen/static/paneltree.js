// Tree layout of the side panel of the Analysis and Explicit tabs: the model tree over a property pane. A tree node
// stands for one or more page elements of the panel; the property pane shows the pages of the selected node and of the
// nodes below it (the top node: all pages). ⇄ in the panel header moves the panel to the other side of the view.
// Selection, folded nodes, tree height and side are kept per PC (localStorage, keys tp_<what>_<key>).

const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const load = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* no storage */ } };

/**
 * cfg: {key ("fa" | "xp"), panel (element), body (the .ann-body of the view and the panel), title, root: node,
 *       onSide()}; node: {id, label (string or function), els: () => [elements], count: () => number | null,
 *       off: () => bool (hidden by Panels), children: [node], items: () => [{id, label}] (the items of the page as
 *       leaves of the node), pick: id => void (a click on a leaf: the item selected in the view or the panel)}.
 * Returns {apply(), select(id), reveal(id), selected(), render(), side(left)}.
 */
export function install(cfg) {
  const { key, panel, body } = cfg;
  const head = document.createElement("div");
  head.className = "tp-head";
  head.innerHTML = `<span class="tp-title">${esc(cfg.title || "Model tree")}</span>` +
    `<button type="button" class="small tp-side" id="${key}-tp-side" title="Move the panel to the other side of the view">⇄</button>`;
  const tree = document.createElement("div");
  tree.className = "tp-tree";
  tree.id = key + "-tree";
  const props = document.createElement("div");
  props.className = "tp-props";
  props.id = key + "-props";
  while (panel.firstChild) props.appendChild(panel.firstChild);
  panel.classList.add("tp-panel");
  panel.append(head, tree, props);
  const h0 = +load("tp_h_" + key, 0);
  if (h0 >= 60) tree.style.height = h0 + "px";
  new ResizeObserver(() => { const h = Math.round(tree.getBoundingClientRect().height); if (h >= 60) save("tp_h_" + key, h); }).observe(tree);

  const nodes = new Map();
  const parent = new Map();
  (function walk(n, p) { nodes.set(n.id, n); if (p) parent.set(n.id, p.id); (n.children || []).forEach(c => walk(c, n)); })(cfg.root, null);
  let sel = load("tp_sel_" + key, cfg.root.id);
  if (!nodes.has(sel)) sel = cfg.root.id;
  const folded = new Set(load("tp_fold_" + key, []));
  let selItem = null;                 // "<node id>|<item id>" of the clicked leaf

  const label = n => typeof n.label === "function" ? n.label() : n.label;
  const below = id => { const out = [id]; for (const c of nodes.get(id).children || []) out.push(...below(c.id)); return out; };
  function render() {
    const rows = [];
    (function walk(n, depth) {
      const kids = n.children || [];
      const items = n.items ? n.items() || [] : [];
      const off = n.off ? n.off() : false;
      const cnt = n.count ? n.count() : null;
      rows.push(`<div class="tp-row${n.id === sel && !selItem ? " sel" : ""}${off ? " off" : ""}" data-tp="${esc(n.id)}" style="padding-left:${4 + depth * 14}px"` +
        (off ? ` title="Hidden by Panels"` : "") + `><span class="tp-caret">${kids.length || items.length ? (folded.has(n.id) ? "▸" : "▾") : ""}</span>` +
        `<span class="tp-label">${esc(label(n))}</span>${cnt !== null && cnt !== undefined ? `<span class="tp-count">${cnt}</span>` : ""}</div>`);
      if (folded.has(n.id)) return;
      kids.forEach(c => walk(c, depth + 1));
      for (const it of items) {
        const k = n.id + "|" + it.id;
        rows.push(`<div class="tp-row tp-leaf${k === selItem && n.id === sel ? " sel" : ""}" data-tp="${esc(n.id)}" data-tpi="${esc(it.id)}" style="padding-left:${4 + (depth + 1) * 14}px"` +
          (it.title ? ` title="${esc(it.title)}"` : "") + `><span class="tp-caret"></span><span class="tp-label">${esc(it.label)}</span></div>`);
      }
    })(cfg.root, 0);
    tree.innerHTML = rows.join("");
    tree.querySelectorAll(".tp-row").forEach(r => r.onclick = e => {
      const id = r.dataset.tp;
      if (r.dataset.tpi !== undefined) {                 // a leaf: the page of its node, the item picked
        const n = nodes.get(id);
        selItem = id + "|" + r.dataset.tpi;
        if (sel !== id) select(id, true); else render();
        if (n.pick) n.pick(r.dataset.tpi);
        return;
      }
      if (e.target.classList.contains("tp-caret") && ((nodes.get(id).children || []).length || (nodes.get(id).items ? (nodes.get(id).items() || []).length : 0))) {
        if (folded.has(id)) folded.delete(id); else folded.add(id);
        save("tp_fold_" + key, [...folded]);
        render();
        return;
      }
      select(id);
    });
  }
  function apply() {
    const all = new Set(), vis = new Set();
    for (const n of nodes.values()) for (const el of n.els ? n.els() : []) if (el) all.add(el);
    for (const id of below(sel)) for (const el of nodes.get(id).els ? nodes.get(id).els() : []) if (el) vis.add(el);
    for (const el of all) {
      // a page holding a shown page (a section with sub pages) is shown
      const on = vis.has(el) || [...vis].some(v => v !== el && el.contains(v));
      el.classList.toggle("tp-off", !on);
      if (on && el.tagName === "DETAILS" && sel !== cfg.root.id && !el.open) el.open = true;
    }
    render();
  }
  function select(id, keepItem) {
    if (!nodes.has(id)) return;
    if (!keepItem) selItem = null;
    sel = id;
    save("tp_sel_" + key, id);
    for (let p = parent.get(id); p; p = parent.get(p)) folded.delete(p);
    apply();
    props.scrollTop = 0;
  }
  /** Shows the page of a node unless the selected node already shows it. */
  function reveal(id) {
    if (!nodes.has(id) || below(sel).includes(id)) return;
    select(id);
  }
  let pending = false;
  new MutationObserver(() => {
    if (pending) return;
    pending = true;
    queueMicrotask(() => { pending = false; apply(); });
  }).observe(props, { childList: true, subtree: true });

  const setSide = left => {
    body.classList.toggle("tp-left", left);
    save("tp_left_" + key, left);
    if (cfg.onSide) cfg.onSide(left);
    window.dispatchEvent(new Event("resize"));
  };
  head.querySelector(".tp-side").onclick = () => setSide(!body.classList.contains("tp-left"));
  if (load("tp_left_" + key, false)) setSide(true);
  apply();
  return { apply, select, reveal, render, selected: () => sel, side: setSide };
}

/** Width drag of the panel by its split bar, for the panel on either side (width kept in localStorage[wkey]). */
export function bindSplit(bar, panel, body, wkey, after) {
  if (!bar || bar.dataset.bound) return;
  bar.dataset.bound = "1";
  try { const w = +localStorage.getItem(wkey); if (w >= 300) panel.style.width = w + "px"; } catch (e) { /* no storage */ }
  bar.onmousedown = e => {
    e.preventDefault();
    const w0 = panel.getBoundingClientRect().width, x0 = e.clientX, sgn = body.classList.contains("tp-left") ? -1 : 1;
    bar.classList.add("drag");
    const move = ev => { panel.style.width = Math.max(300, Math.min(window.innerWidth * 0.75, w0 + sgn * (x0 - ev.clientX))) + "px"; };
    const up = () => {
      bar.classList.remove("drag");
      window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up);
      try { localStorage.setItem(wkey, parseInt(panel.style.width)); } catch (err) { /* no storage */ }
      if (after) after();
    };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  };
}
