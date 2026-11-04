// Optional panels of the Analysis and Explicit tabs: a row of check boxes (Panels) that shows or hides them. The hidden
// panels are stored in the document (doc.panels_hidden: [key]). A hidden panel with items shows their number.

const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export function isHidden(doc, key) { return ((doc && doc.panels_hidden) || []).includes(key); }

/** list: [{key, label, count}]; onChange(): called after a change of doc.panels_hidden. */
export function renderToggles(box, doc, list, onChange) {
  if (!box || !doc) return;
  box.innerHTML = `<div class="row wrap panel-toggles"><span class="hint">Panels</span>` + list.map(p => {
    const hid = isHidden(doc, p.key);
    return `<label class="check inline" title="Show or hide the ${esc(p.label)} panel"><input type="checkbox" data-ptog="${esc(p.key)}"${hid ? "" : " checked"}> ${esc(p.label)}${hid && p.count ? ` (${p.count})` : ""}</label>`;
  }).join("") + `</div>`;
  box.querySelectorAll("[data-ptog]").forEach(el => el.onchange = () => {
    const k = el.dataset.ptog;
    const h = new Set(doc.panels_hidden || []);
    if (el.checked) h.delete(k); else h.add(k);
    doc.panels_hidden = [...h];
    if (!doc.panels_hidden.length) delete doc.panels_hidden;
    onChange();
  });
}
