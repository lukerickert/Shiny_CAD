// History output panel of the Analysis tab and of the explicit pane: the time history requests of the document
// ("history": [{id, name, kind: "node" | "element", target, quantities, every}]).

import * as VS from "/static/viewsel.js";

const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** Quantities per solver: [key, label]. */
export const Q = {
  calculix: { node: [["U", "displacement"], ["V", "velocity (dynamic steps)"], ["RF", "reaction force (total)"]],
              element: [["S", "stress (von Mises)"], ["E", "strain"], ["PEEQ", "PEEQ"], ["ENER", "internal energy"], ["EKIN", "kinetic energy (dynamic steps)"]],
              contact: [["CF", "contact force"]], section: [["SOF", "section force and moment"]] },
  explicit: { node: [["U", "displacement"], ["V", "velocity"], ["A", "acceleration"], ["RF", "reaction force (total)"]],
              element: [["ENER", "internal energy"], ["EKIN", "kinetic energy"]],
              contact: [["CF", "contact force (general contact)"]], section: [["SOF", "section force and moment"]] },
};
const KINDS = [["node", "nodes"], ["element", "elements"], ["contact", "contact"], ["section", "section"]];
const HINT = {
  calculix: "Values at every output increment of the steps (*NODE PRINT, *EL PRINT, *CONTACT PRINT, *SECTION PRINT): nodes: mean displacement and velocity components, largest |u| and |v|, total reaction force; elements: largest and mean von Mises stress, largest equivalent strain and PEEQ, total internal and kinetic energy; contact: force on the slave surface of a contact pair; section: force and moment on faces of solid bodies (element faces). Results: Time history.",
  explicit: "Values at every time history output (/TFILE) of the run (/TH/NODE, /TH/PART, /TH/INTER, /TH/SECTIO): nodes: mean displacement, velocity and acceleration components, largest |u|, |v| and |a|, total reaction force; elements: internal and kinetic energy of the parts of the bodies; contact: force of the general contact interface of the build; section: force and moment on faces of solid bodies (/SECT). Results: Time history.",
};

/** Text of the target of a request. */
export function targetText(doc, h, fallback) {
  const t = h.target;
  if ((h.kind || "node") === "contact") return t && t.contact ? "contact " + (((doc.contacts || []).find(c => c.id === t.contact)) || {}).name : "(contact pair)";
  if (!t) return "(no target)";
  if (t.nset) return "node set " + (((doc.nsets || []).find(n => n.id === t.nset)) || {}).name;
  if (t.point) return "reference point " + (((doc.points || []).find(p => p.id === t.point)) || {}).name;
  if (t.surface) return "surface " + (((doc.surfaces || []).find(x => x.id === t.surface)) || {}).name;
  return VS.multiText(t) || (fallback ? fallback(t) : "");
}

/**
 * Renders the requests into box. H: {doc(), solver ("calculix" | "explicit"), sel (selection host of VS.collect),
 * nid(prefix), num(text), changed(), rerender(), targetText(t) (single face / edge targets)}.
 */
export function render(H, box) {
  const d = H.doc();
  if (!box || !d) return;
  d.history = d.history || [];
  const QS = Q[H.solver] || Q.calculix;
  const other = QS === Q.calculix ? Q.explicit : Q.calculix;
  box.innerHTML = d.history.map(h => {
    const kind = h.kind || "node";
    const qs = QS[kind] || [];
    const extra = (h.quantities || []).filter(k => !qs.some(x => x[0] === k));        // of the other solver: kept
    return `<div class="fa-hreq" data-hr="${esc(h.id)}"><div class="row wrap"><input type="text" data-hk="name" value="${esc(h.name)}" style="width:96px">` +
      `<select data-hk="kind">${KINDS.map(([v, t]) => `<option value="${v}"${kind === v ? " selected" : ""}>${t}</option>`).join("")}</select>` +
      (kind === "contact" ? (H.solver === "explicit" ? `<span class="hint">general contact of the build</span>`
        : `<select data-hk="contact"><option value="">contact pair</option>${(d.contacts || []).filter(c => c.type !== "tied").map(c => `<option value="${esc(c.id)}"${h.target && h.target.contact === c.id ? " selected" : ""}>${esc(c.name || c.id)}</option>`).join("")}</select>`)
        : `<span class="hint">${esc(targetText(d, h, H.targetText))}</span><button type="button" class="small" data-hk="pick" title="${kind === "node" ? "The selected faces, edges, vertices, bodies, mesh nodes or elements" : kind === "section" ? "The selected faces of solid bodies" : H.solver === "explicit" ? "The selected bodies" : "The selected bodies or mesh elements"} (or select, then Done)">Pick</button>`) +
      (kind === "node" && (d.nsets || []).length ? `<select data-hk="nset"><option value="">or node set</option>${d.nsets.map(n => `<option value="${esc(n.id)}"${h.target && h.target.nset === n.id ? " selected" : ""}>${esc(n.name)}</option>`).join("")}</select>` : "") +
      (kind === "node" && (d.points || []).length ? `<select data-hk="point"><option value="">or reference point</option>${d.points.map(p => `<option value="${esc(p.id)}"${h.target && h.target.point === p.id ? " selected" : ""}>${esc(p.name)}</option>`).join("")}</select>` : "") +
      `<button type="button" class="small" data-hk="del" title="Delete">×</button></div><div class="row wrap">` +
      qs.map(([k, t]) => `<label class="check inline"><input type="checkbox" data-hq="${k}"${(h.quantities || []).includes(k) ? " checked" : ""}> ${t}</label>`).join("") +
      (H.solver !== "explicit" ? `<label class="inline" title="Output every n increments (empty: as the step)">every<input type="text" class="numf" data-hk="every" value="${h.every || ""}" style="width:34px"></label>` : "") +
      (extra.length ? `<span class="hint" title="Quantities of the other solver, kept in the request">+ ${esc(extra.map(k => ((other[kind] || []).find(x => x[0] === k) || [k, k])[1]).join(", "))}</span>` : "") +
      `</div></div>`;
  }).join("") + `<div class="row"><button type="button" class="small" data-hadd="1">Add request</button></div><p class="hint">${HINT[H.solver] || HINT.calculix}</p>`;
  const pick = h => {
    if (h.kind === "contact") return;
    const el = h.kind === "element";
    const types = el ? (H.solver === "explicit" ? ["bodies"] : ["bodies", "elements"]) : h.kind === "section" ? ["faces"] : ["faces", "edges", "vertices", "bodies", "nodes", "elements"];
    VS.collect(H.sel, { text: h.name + ": " + (el ? types.join(" or ").replace("elements", "mesh elements") : h.kind === "section" ? "faces of solid bodies" : "faces, edges, vertices, bodies, mesh nodes or elements"),
      types, cb: it => {
        const r = VS.targetOf(it);
        if (r.error) return r.error;
        const t = r.target;
        h.target = t.face !== undefined ? { faces: [t] } : t.edge !== undefined ? { edges: [t] } : t;
        H.changed(); H.rerender();
      } });
  };
  box.querySelector("[data-hadd]").onclick = () => {
    const h = { id: H.nid("h"), name: "History " + (d.history.length + 1), kind: "node", quantities: ["U"], target: null };
    d.history.push(h);
    H.changed(); H.rerender(); pick(h);
  };
  box.querySelectorAll("[data-hr]").forEach(div => {
    const h = d.history.find(x => x.id === div.dataset.hr);
    div.querySelectorAll("[data-hk]").forEach(el => {
      const k = el.dataset.hk;
      if (k === "del") el.onclick = () => { d.history = d.history.filter(x => x !== h); H.changed(); H.rerender(); };
      else if (k === "pick") el.onclick = () => pick(h);
      else el.onchange = () => {
        if (k === "name") h.name = el.value.trim() || h.name;
        else if (k === "kind") { h.kind = el.value; h.target = null; h.quantities = [QS[h.kind][0][0]]; if (h.kind === "section") pick(h); }
        else if (k === "nset" || k === "point" || k === "contact") { if (el.value) h.target = { [k]: el.value }; }
        else if (k === "every") { const v = Math.round(H.num(el.value)); if (v > 0) h.every = v; else delete h.every; }
        H.changed(); H.rerender();
      };
    });
    div.querySelectorAll("[data-hq]").forEach(el => el.onchange = () => {
      const keep = (h.quantities || []).filter(k => !(QS[h.kind || "node"] || []).some(x => x[0] === k));
      h.quantities = [...keep, ...[...div.querySelectorAll("[data-hq]:checked")].map(x => x.dataset.hq)];
      H.changed();
    });
  });
}
