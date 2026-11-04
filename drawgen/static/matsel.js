// Material drop-downs of the Analysis and Explicit tabs: the model materials with the library entry or the elastic
// values in the label, "(default: ...)" with the default material, and the library entries not yet in the model
// (value "lib:<entry>"; choosing one adds a model material for the entry, installLibraryPick).

const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = v => (typeof v === "number" && isFinite(v)) ? String(+v.toPrecision(6)) : String(v === undefined || v === null ? "" : v);

/** Label of a model material: "name - library entry" or "name - law, E MPa, nu, rho kg/m^3". */
export function matLabel(name, m) {
  if (!m) return name + " (not defined)";
  if (m.library) return `${name} - ${m.library}` + (m.law && m.law !== "elastic" && m.law !== "plastic" ? `, ${m.law}` : "");
  return `${name} - ${m.law && m.law !== "elastic" ? m.law + ", " : ""}E ${num(m.E)} MPa, nu ${num(m.nu)}, rho ${num(m.rho)} kg/m^3`;
}

/** <option>s: default (when withDefault), the model materials, the library entries not used by a model material. */
export function matOptions(doc, cur, library, withDefault = true) {
  const mats = (doc && doc.materials) || {};
  const def = doc && doc.default_material;
  let h = withDefault ? `<option value="">(default: ${esc(def ? matLabel(def, mats[def]) : "none")})</option>` : "";
  const names = Object.keys(mats);
  h += `<optgroup label="Model materials">` + names.map(n => `<option value="${esc(n)}"${n === cur ? " selected" : ""}>${esc(matLabel(n, mats[n]))}</option>`).join("") + `</optgroup>`;
  const used = new Set(Object.values(mats).map(m => m && m.library).filter(Boolean));
  const libs = (library || []).filter(k => !used.has(k));
  if (libs.length) h += `<optgroup label="Library (adds a model material)">` + libs.map(k => `<option value="lib:${esc(k)}">${esc(k)}</option>`).join("") + `</optgroup>`;
  return h;
}

/** Model material name for a library entry: the entry without the parenthesised part, letters, digits, _ and -. */
export function nameForLibrary(doc, entry) {
  const base = String(entry).replace(/\([^)]*\)/g, " ").trim().replace(/[^A-Za-z0-9_\-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "Material";
  const mats = (doc && doc.materials) || {};
  let n = base, k = 2;
  while (mats[n]) n = `${base}_${k++}`;
  return n;
}

/** A choice "lib:<entry>" in a material drop-down under root adds the model material (add(entry) returns its name)
 *  before the drop-down's own change handler runs, which then reads the new name. */
export function installLibraryPick(root, add) {
  if (!root || root._libPick) return;
  root._libPick = true;
  root.addEventListener("change", ev => {
    const el = ev.target;
    if (!el || el.tagName !== "SELECT" || !String(el.value).startsWith("lib:")) return;
    const name = add(el.value.slice(4));
    if (!name) { el.value = ""; return; }
    const o = document.createElement("option");
    o.value = name; o.textContent = name;
    el.appendChild(o);
    el.value = name;
  }, true);
}
