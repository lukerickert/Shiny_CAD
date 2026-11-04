// Shell model panels of the Analysis and Explicit tabs (from step2shell): sections (faces of the surface bodies of any
// components with one thickness, position, material and element size), face and edge selection in the 3D view, and
// node sets (plane, free edges or outline of a section or shell, selected edges, selected faces).
//
// A host object H connects a tab:
//   H.doc()            the analysis or explicit document (doc.sections, doc.nsets, doc.shells)
//   H.comps()          the geometry components with view data (id, mesh with face_body, surfaces, erefs)
//   H.compName(id)     the name of a component
//   H.matOptions(cur)  <option> list of the materials
//   H.layers()         optional: {enabled, title} of the Layers column of the sections (Analysis: S8R composite shells)
//   H.modes            [[value, text]] of the section Model / Role column
//   H.nid(prefix)      new id
//   H.changed(), H.draw(), H.render(), H.status(text, isError), H.postJSON(url, body)
//   H.fmt(v), H.esc(s)
// The selection lives in H.sel (viewsel.js): faces Set("<comp>:<face>"), edges Set("<comp>:<edge>"), bodies, points,
// types (the types clicks and boxes take), box, collect.

export const SECTION_COLORS = ["#8c8c8c", "#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2", "#edc948", "#b07aa1",
                               "#ff9da7", "#9c755f"];
const POS = [["mid", "mid"], ["positive", "positive"], ["negative", "negative"]];
const KINDS = { plane: "nodes on a plane", section_edges: "edges of a section or shell", edges: "selected edges", faces: "selected faces", body: "all nodes of bodies" };

export function selState(H) {
  if (!H.sel) H.sel = { faces: new Set(), edges: new Set(), bodies: new Set(), points: new Set(), types: new Set(), box: false, collect: null };
  return H.sel;
}
const fkey = r => r.comp + ":" + r.face;
const ekey = r => r.comp + ":" + r.edge;
const fref = k => { const i = k.lastIndexOf(":"); return { comp: k.slice(0, i), face: +k.slice(i + 1) }; };
const eref = k => { const i = k.lastIndexOf(":"); return { comp: k.slice(0, i), edge: +k.slice(i + 1) }; };

/** Faces of the surface bodies of the components: [{comp, face, body (surface index)}]. */
export function shellFaces(H) {
  const out = [];
  for (const c of H.comps()) {
    const fb = (c.mesh && c.mesh.face_body) || [];
    fb.forEach((b, fi) => { if (b !== null && b !== undefined) out.push({ comp: c.id, face: fi, body: b }); });
  }
  return out;
}
/** Section of a face (the first section listing it), or null. */
export function sectionOf(H, ref) {
  const k = fkey(ref);
  return (H.doc().sections || []).find(s => (s.faces || []).some(r => fkey(r) === k)) || null;
}

/** Overlays of a component for the 3D view: [{face | edge, color, opacity}] (section colours, the selection). */
export function overlays(H, cid) {
  const S = selState(H), out = [];
  for (const s of H.doc().sections || []) for (const r of s.faces || []) if (r.comp === cid && !S.faces.has(fkey(r))) out.push({ face: r.face, color: s.color || "#8c8c8c", opacity: 0.55 });
  for (const k of S.faces) { const r = fref(k); if (r.comp === cid) out.push({ face: r.face, color: "#f08c00", opacity: 0.8 }); }
  if (S.bodies.size) {                                       // faces of the selected bodies
    const c = H.comps().find(x => x.id === cid), fb = (c && c.mesh && c.mesh.face_body) || [], fot = (c && c.mesh && c.mesh.face_of_tri) || [];
    let n = fb.length;
    for (const fi of fot) if (fi + 1 > n) n = fi + 1;
    for (let fi = 0; fi < n; fi++) {
      const b = fb[fi], sf = b === null || b === undefined ? null : (c.surfaces || [])[b];
      const bid = sf ? cid + ":" + sf.id : cid;
      if (S.bodies.has(bid) && !S.faces.has(cid + ":" + fi)) out.push({ face: fi, color: "#f59f00", opacity: 0.6 });
    }
  }
  for (const k of S.edges) { const r = eref(k); if (r.comp === cid) out.push({ edge: r.edge, color: "#e03131" }); }
  return out;
}

function startSelect(H, mode) {
  const S = selState(H);
  const t = new Set(S.types);
  if (t.has(mode)) t.delete(mode); else t.add(mode);
  if (H.setTypes) H.setTypes([...t]); else { S.types = t; H.render(); H.draw(); }
}
/** The selected faces with the faces of the selected bodies: keys "<comp>:<face>". */
function selFaceKeys(H) {
  const S = selState(H), keys = new Set(S.faces);
  if (S.bodies.size) for (const c of H.comps()) {
    const fb = (c.mesh && c.mesh.face_body) || [];
    fb.forEach((b, fi) => { const sf = b === null || b === undefined ? null : (c.surfaces || [])[b]; if (S.bodies.has(sf ? c.id + ":" + sf.id : c.id)) keys.add(c.id + ":" + fi); });
  }
  return [...keys];
}

function newSectionName(H, base) {
  const used = new Set((H.doc().sections || []).map(s => s.name));
  let n = base, k = 2;
  while (used.has(n)) n = base + "_" + k++;
  return n;
}
const safeName = s => String(s || "").toUpperCase().replace(/[^A-Z0-9_]+/g, "_").replace(/^_+|_+$/g, "") || "SECTION";

/** The selected faces that belong to surface bodies (sections take faces of shells only). */
function shellSel(H) {
  const ok = new Set(shellFaces(H).map(fkey)), all = selFaceKeys(H);
  const keys = all.filter(k => ok.has(k));
  if (keys.length < all.length) H.status(`${all.length - keys.length} selected face(s) of solids left out: sections take faces of shells`, true);
  return keys;
}
/** New sections replace the existing ones (after confirmation); thickness, position, material, size and mode of a
 *  section with the same name are kept. */
function replaceSections(H, list) {
  const d = H.doc();
  const old = new Map((d.sections || []).map(s => [s.name, s]));
  if ((d.sections || []).length && !confirm(`Replace the ${d.sections.length} section(s)?`)) return;
  d.sections = list.map((x, i) => {
    const o = old.get(x.name) || {};
    const s = { id: H.nid("sec"), name: x.name, faces: x.faces, color: o.color || SECTION_COLORS[i % SECTION_COLORS.length] };
    for (const k of ["t", "offset", "material", "size", "mode", "layers"]) if (o[k] !== undefined) s[k] = o[k]; else if (x[k] !== undefined) s[k] = x[k];
    return s;
  });
  H.changed(); H.render(); H.draw();
  H.status(`${d.sections.length} section(s)`);
}
function fromBodies(H) {
  const d = H.doc(), list = [];
  for (const c of H.comps()) {
    const fb = (c.mesh && c.mesh.face_body) || [];
    (c.surfaces || []).forEach((sf, k) => {
      const faces = []; fb.forEach((b, fi) => { if (b === k) faces.push({ comp: c.id, face: fi }); });
      if (!faces.length) return;
      const sh = (d.shells || {})[c.id + ":" + sf.id] || {};
      const x = { name: safeName(H.compName(c.id) + "_" + sf.name), faces };
      for (const key of ["t", "offset", "material", "size", "layers"]) if (sh[key] !== undefined) x[key] = sh[key];
      if (sh.mode === "rigid") x.mode = "rigid";
      list.push(x);
    });
  }
  if (!list.length) { H.status("No surface bodies in the geometry", true); return; }
  const seen = new Set();
  for (const x of list) { let n = x.name, k = 2; while (seen.has(n)) n = x.name + "_" + k++; x.name = n; seen.add(n); }
  replaceSections(H, list);
}
async function byGeometry(H, angle) {
  try {
    const r = await H.postJSON("/api/analysis/shell_groups", { source: H.doc().source, angle });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    if (!j.groups.length) { H.status("No surface bodies in the geometry", true); return; }
    replaceSections(H, j.groups.map(g => ({ name: g.name, faces: g.faces })));
  } catch (e) { H.status("By geometry: " + e.message, true); }
}

/** Sections panel (HTML and bindings) into box. */
export function renderSections(H, box) {
  const d = H.doc(), S = selState(H);
  d.sections = d.sections || [];
  const nf = shellFaces(H), inSec = nf.filter(r => sectionOf(H, r)).length;
  let h = `<div class="buttons sm-tools"><button type="button" class="small" data-sm="bodies" title="One section per surface body of the components (the thickness and material of its Shells row)">From surface bodies</button>` +
    `<button type="button" class="small" data-sm="geom" title="Connected faces on the same plane (within the angle) or the same cylinder form one section: PLATE_Z0, WEB_X1500, CYL_R800, PLANE, SURF">By geometry</button>` +
    `<label class="inline" title="Angle tolerance of By geometry (deg)">angle<input type="text" class="numf" data-sm-angle value="${H.esc(H.angle || 1)}" style="width:36px"></label>` +
    `<button type="button" class="small" data-sm="new" title="New section of the selected faces (they leave other sections)">New from selection</button>` +
    `<button type="button" class="small" data-sm="clear" title="Remove all sections (their faces take the Shells rows again)">Remove all</button></div>` +
    `<div class="buttons sm-tools"><button type="button" class="small${S.types.has("faces") ? " active" : ""}" data-sm="selfaces" title="Click faces in the view to select or deselect them (Esc ends); sections take the faces of shells">Select faces</button>` +
    `<button type="button" class="small" data-sm="unassigned" title="Select the faces of the shells in no section">Select unassigned</button>` +
    `<button type="button" class="small" data-sm="allfaces">Select all</button><button type="button" class="small" data-sm="invert">Invert</button>` +
    `<button type="button" class="small" data-sm="unsel">Clear selection</button><span class="hint">${S.faces.size} face(s) selected; ${inSec} of ${nf.length} shell face(s) in sections</span></div>`;
  if (d.sections.length) {
    const lay = H.layers ? H.layers() : null;                  // Analysis: layers of S8R composite shells
    // two lines per section: name, faces and model; thickness, position, material, size (and layers)
    h += `<table class="sm-sections">` + d.sections.map((s, i) => `<tr data-sec="${H.esc(s.id)}" class="${i % 2 ? "sm-odd" : ""}${s.mode === "off" ? " sm-off" : ""}"><td>` +
      `<div class="sm-l1"><input type="color" data-sk="color" value="${H.esc(s.color || "#8c8c8c")}" class="sm-col">` +
      `<input type="text" data-sk="name" value="${H.esc(s.name)}" class="sm-name" title="${H.esc(s.name)}">` +
      `<span class="sm-faces" title="Faces of the section">${(s.faces || []).length} face(s)</span>` +
      `<button type="button" class="small" data-sk="sel" title="Select the faces of the section">Sel</button><button type="button" class="small" data-sk="add" title="Add the selected faces (they leave other sections)">+</button>` +
      `<button type="button" class="small" data-sk="del" title="Remove the section (its faces take their Shells row again)">&#10005;</button></div>` +
      `<div class="sm-l2"><label>Model<select data-sk="mode">${H.modes.map(([v, t]) => `<option value="${v}"${(s.mode || "shell") === v ? " selected" : ""}>${t}</option>`).join("")}</select></label>` +
      `<label>t (mm)<input type="text" class="numf" data-sk="t" value="${H.esc(s.t || "")}" placeholder="10"></label>` +
      `<label>Position<select data-sk="offset">${POS.map(([v, t]) => `<option value="${v}"${(s.offset || "mid") === v ? " selected" : ""}>${t}</option>`).join("")}</select></label>` +
      `<label class="sm-mat">Material<select data-sk="material">${H.matOptions(s.material)}</select></label>` +
      `<label>Size (mm)<input type="text" class="numf" data-sk="size" value="${H.esc(s.size || "")}" placeholder="auto"></label>` +
      (lay ? `<label title="${H.esc(lay.title)}">Layers<input type="text" class="numf" data-sk="layers" value="${H.esc(s.layers || "")}" placeholder="1"${lay.enabled ? "" : " disabled"}></label>` : "") +
      `</div></td></tr>`).join("") + `</table>`;
  }
  h += `<p class="hint">A section gives its faces (of any surface bodies and components) one ELSET with thickness t (empty: 10 mm), position, material and element size; the faces of no section take the row of their surface body in Shells. Face colours in the view: the section colour; selected faces orange.</p>`;
  box.innerHTML = h;
  const ang = box.querySelector("[data-sm-angle]");
  ang.onchange = () => { const v = parseFloat(ang.value); H.angle = isFinite(v) && v > 0 ? v : 1; };
  const sel = list => { S.faces = new Set(list.map(fkey)); H.render(); H.draw(); H.status(`${S.faces.size} face(s) selected`); };
  box.querySelectorAll("[data-sm]").forEach(b => b.onclick = () => {
    const k = b.dataset.sm;
    if (k === "bodies") fromBodies(H);
    else if (k === "geom") byGeometry(H, H.angle || 1);
    else if (k === "new") {
      const keys = shellSel(H);
      if (!keys.length) { H.status("Select faces of shells first (Select faces)", true); return; }
      const faces = keys.map(fref), ks = new Set(keys);
      for (const s of d.sections) s.faces = (s.faces || []).filter(r => !ks.has(fkey(r)));
      d.sections.push({ id: H.nid("sec"), name: newSectionName(H, "SECTION_" + (d.sections.length + 1)), faces, color: SECTION_COLORS[d.sections.length % SECTION_COLORS.length] });
      S.faces = new Set(); S.bodies = new Set(); H.changed(); H.render(); H.draw();
    } else if (k === "clear") { if (d.sections.length && confirm(`Remove the ${d.sections.length} section(s)?`)) { d.sections = []; H.changed(); H.render(); H.draw(); } }
    else if (k === "selfaces") startSelect(H, "faces");
    else if (k === "unassigned") sel(nf.filter(r => !sectionOf(H, r)));
    else if (k === "allfaces") sel(nf);
    else if (k === "invert") sel(nf.filter(r => !S.faces.has(fkey(r))));
    else if (k === "unsel") sel([]);
  });
  box.querySelectorAll("tr[data-sec]").forEach(tr => {
    const s = d.sections.find(x => x.id === tr.dataset.sec);
    tr.querySelectorAll("[data-sk]").forEach(el => {
      const k = el.dataset.sk;
      if (el.tagName === "BUTTON") el.onclick = () => {
        if (k === "sel") sel(s.faces || []);
        else if (k === "add") {
          const keys = shellSel(H), ks = new Set(keys);
          if (!keys.length) { H.status("Select faces of shells first (Select faces)", true); return; }
          for (const o of d.sections) o.faces = (o.faces || []).filter(r => !ks.has(fkey(r)));
          s.faces = s.faces.concat(keys.map(fref));
          S.faces = new Set(); S.bodies = new Set(); H.changed(); H.render(); H.draw();
        } else if (k === "del") { d.sections = d.sections.filter(x => x !== s); H.changed(); H.render(); H.draw(); }
      };
      else el.onchange = () => {
        if (k === "name") { const n = safeName(el.value); if (d.sections.some(x => x !== s && x.name === n)) { el.value = s.name; return; } s.name = n; }
        else if (k === "t" || k === "size") { const v = parseFloat(String(el.value).replace(",", ".")); if (v > 0) s[k] = v; else delete s[k]; }
        else if (k === "layers") { const v = Math.round(parseFloat(String(el.value).replace(",", "."))); if (v > 1 && v <= 20) s.layers = v; else delete s.layers; }
        else if (k === "mode" && el.value === "shell") delete s.mode;
        else if (k === "offset" && el.value === "mid") delete s.offset;
        else if (el.value) s[k] = el.value; else delete s[k];
        H.changed(); H.render(); H.draw();
      };
    });
  });
}

/** Text of a node set. */
export function nsetText(H, ns) {
  if (ns.kind === "plane") return `${(ns.axis || "z")} = ${H.fmt(ns.value || 0)} mm (± ${H.fmt(ns.tol === undefined ? 0.01 : ns.tol)} mm)`;
  if (ns.kind === "section_edges") return `${ns.which === "outline" ? "outline" : "free edges"} of ${bodyName(H, ns.body)}`;
  if (ns.kind === "edges") return `${(ns.edges || []).length} edge(s)`;
  if (ns.kind === "body") return (ns.bodies || []).map(b => bodyName(H, b)).join(", ") || "(choose)";
  return `${(ns.faces || []).length} face(s)`;
}
/** Meshed bodies of the geometry: [[id, text]]: solids (component id), shells ("<component>:<surface>"), sections. */
export function bodyList(H) {
  const out = [], inSec = new Map();
  for (const s of H.doc().sections || []) if (s.mode !== "off") for (const r of s.faces || []) inSec.set(r.comp + ":" + r.face, s.name);
  for (const c of H.comps()) {
    const fb = (c.mesh && c.mesh.face_body) || [];
    if (!fb.length || fb.some(v => v === null || v === undefined)) out.push([c.id, "solid " + (H.compName(c.id) || c.id)]);
    (c.surfaces || []).forEach((sf, k) => {
      // faces of the surface body meshed in sections: the section names
      const secs = [...new Set(fb.map((v, i) => v === k ? inSec.get(c.id + ":" + i) : undefined).filter(v => v !== undefined))];
      out.push([c.id + ":" + sf.id, "shell " + (H.compName(c.id) || c.id) + " / " + sf.name + (secs.length ? " (in section " + secs.join(", ") + ")" : "")]);
    });
  }
  for (const s of H.doc().sections || []) out.push(["sec:" + s.id, "section " + s.name]);
  return out;
}
function bodyName(H, bid) {
  if (!bid) return "(choose)";
  if (!bid.includes(":")) return H.compName(bid) || bid;
  if (bid.startsWith("sec:")) { const s = (H.doc().sections || []).find(x => "sec:" + x.id === bid); return s ? s.name : bid; }
  const [cid, sid] = [bid.slice(0, bid.lastIndexOf(":")), bid.slice(bid.lastIndexOf(":") + 1)];
  const c = H.comps().find(x => x.id === cid), sf = c && (c.surfaces || []).find(x => String(x.id) === sid);
  return (H.compName(cid) || cid) + " / " + (sf ? sf.name : sid);
}
function bodyOptions(H, cur) {
  const opts = (H.doc().sections || []).map(s => ["sec:" + s.id, "section " + s.name]);
  for (const c of H.comps()) for (const sf of c.surfaces || []) opts.push([c.id + ":" + sf.id, "shell " + H.compName(c.id) + " / " + sf.name]);
  return `<option value="">(choose)</option>` + opts.map(([v, t]) => `<option value="${H.esc(v)}"${v === cur ? " selected" : ""}>${H.esc(t)}</option>`).join("");
}

/** Node sets panel (HTML and bindings) into box. H.onNsetSupport(ns), when set, adds a support on a node set. */
export function renderNsets(H, box) {
  const d = H.doc(), S = selState(H);
  d.nsets = d.nsets || [];
  let h = `<div class="buttons sm-tools"><button type="button" class="small" data-na="plane" title="All mesh nodes within the tolerance of a plane x, y or z = value">Plane</button>` +
    `<button type="button" class="small" data-na="section_edges" title="Free edges (bounding one shell element of the whole model) or outline (bounding one element of the section) of a section or shell">Section edges</button>` +
    `<button type="button" class="small" data-na="edges" title="The edges selected in the view (Select edges)">Selected edges</button>` +
    `<button type="button" class="small" data-na="faces" title="The faces selected in the view (Select faces)">Selected faces</button>` +
    `<button type="button" class="small" data-na="body" title="All nodes of the checked bodies (the selected bodies when there are any)">Bodies</button>` +
    `<button type="button" class="small${S.types.has("faces") ? " active" : ""}" data-na="selfaces" title="Click faces in the view to select or deselect them (Esc ends)">Select faces</button>` +
    `<button type="button" class="small${S.types.has("edges") ? " active" : ""}" data-na="seledges" title="Click edges in the view to select or deselect them (Esc ends)">Select edges</button>` +
    `<span class="hint">${S.faces.size} face(s), ${S.edges.size} edge(s) selected</span></div>`;
  if (d.nsets.length) {
    h += `<table class="pc-table sm-nsets"><tr><th>Node set</th><th>Definition</th><th></th></tr>` + d.nsets.map(ns => {
      let def = "";
      if (ns.kind === "plane") def = `<select data-nk="axis">${["x", "y", "z"].map(a => `<option${(ns.axis || "z") === a ? " selected" : ""}>${a}</option>`).join("")}</select> = ` +
        `<input type="text" class="numf" data-nk="value" value="${H.esc(ns.value === undefined ? 0 : ns.value)}" style="width:56px"> ± <input type="text" class="numf" data-nk="tol" value="${H.esc(ns.tol === undefined ? 0.01 : ns.tol)}" style="width:40px"> mm`;
      else if (ns.kind === "section_edges") def = `<select data-nk="which"><option value="free"${ns.which !== "outline" ? " selected" : ""}>free edges</option><option value="outline"${ns.which === "outline" ? " selected" : ""}>outline</option></select> of <select data-nk="body">${bodyOptions(H, ns.body)}</select>`;
      else if (ns.kind === "body") def = bodyList(H).map(([v, t]) => `<label class="check inline"><input type="checkbox" data-nb="${H.esc(v)}"${(ns.bodies || []).includes(v) ? " checked" : ""}> ${H.esc(t)}</label>`).join("") || "no bodies";
      else def = `${H.esc(nsetText(H, ns))} <button type="button" class="small" data-nk="set" title="Replace with the current selection">Set</button><button type="button" class="small" data-nk="show" title="Select them in the view">Show</button>`;
      return `<tr data-ns="${H.esc(ns.id)}"><td><input type="text" data-nk="name" value="${H.esc(ns.name)}" style="width:84px"></td><td><span class="sm-def">${def}</span></td>` +
        `<td>${H.onNsetSupport ? `<button type="button" class="small" data-nk="sup" title="Add a support on the node set">Support</button>` : ""}<button type="button" class="small" data-nk="del" title="Delete">&#10005;</button></td></tr>`;
    }).join("") + `</table>`;
  }
  h += `<p class="hint">Node sets: ${Object.values(KINDS).join(", ")}. A support takes a node set as its target; the explicit model .inp writes them as *NSET.</p>`;
  box.innerHTML = h;
  box.querySelectorAll("[data-na]").forEach(b => b.onclick = () => {
    const k = b.dataset.na;
    if (k === "seledges") { startSelect(H, "edges"); return; }
    if (k === "selfaces") { startSelect(H, "faces"); return; }
    const ns = { id: H.nid("ns"), name: "NSET_" + (d.nsets.length + 1), kind: k };
    if (k === "plane") Object.assign(ns, { name: "PLANE_" + (d.nsets.length + 1), axis: "x", value: 0, tol: 0.01 });
    else if (k === "section_edges") {
      const s0 = (d.sections || [])[0], c0 = H.comps().find(c => (c.surfaces || []).length);
      Object.assign(ns, { name: "FREE_" + (d.nsets.length + 1), which: "free", body: s0 ? "sec:" + s0.id : c0 ? c0.id + ":" + c0.surfaces[0].id : "" });
    }
    else if (k === "edges") { if (!S.edges.size) { H.status("Select edges first (Select edges)", true); return; } ns.edges = [...S.edges].map(eref); S.edges = new Set(); }
    else if (k === "faces") { const fk = selFaceKeys(H); if (!fk.length) { H.status("Select faces first (Select faces)", true); return; } ns.faces = fk.map(fref); S.faces = new Set(); S.bodies = new Set(); }
    else if (k === "body") { const b0 = bodyList(H)[0]; Object.assign(ns, { name: "BODY_" + (d.nsets.length + 1), bodies: S.bodies.size ? [...S.bodies] : b0 ? [b0[0]] : [] }); S.bodies = new Set(); }
    d.nsets.push(ns);
    H.changed(); H.render(); H.draw();
  });
  box.querySelectorAll("tr[data-ns]").forEach(tr => {
    const ns = d.nsets.find(x => x.id === tr.dataset.ns);
    tr.querySelectorAll("[data-nb]").forEach(el => el.onchange = () => {
      ns.bodies = (ns.bodies || []).filter(b => b !== el.dataset.nb);
      if (el.checked) ns.bodies.push(el.dataset.nb);
      H.changed();
    });
    tr.querySelectorAll("[data-nk]").forEach(el => {
      const k = el.dataset.nk;
      if (el.tagName === "BUTTON") el.onclick = () => {
        if (k === "del") d.nsets = d.nsets.filter(x => x !== ns);
        else if (k === "sup") { H.onNsetSupport(ns); return; }
        else if (k === "set") {
          if (ns.kind === "edges") { if (!S.edges.size) { H.status("Select edges first", true); return; } ns.edges = [...S.edges].map(eref); S.edges = new Set(); }
          else { const fk = selFaceKeys(H); if (!fk.length) { H.status("Select faces first", true); return; } ns.faces = fk.map(fref); S.faces = new Set(); S.bodies = new Set(); }
        } else if (k === "show") {
          if (ns.kind === "edges") S.edges = new Set((ns.edges || []).map(ekey)); else S.faces = new Set((ns.faces || []).map(fkey));
          H.render(); H.draw(); return;
        }
        H.changed(); H.render(); H.draw();
      };
      else el.onchange = () => {
        if (k === "value" || k === "tol") { const v = parseFloat(String(el.value).replace(",", ".")); if (isFinite(v) && (k === "value" || v >= 0)) ns[k] = v; else el.value = ns[k]; }
        else if (k === "name") ns.name = el.value.trim().toUpperCase().replace(/[^A-Z0-9_]+/g, "_") || ns.name;
        else ns[k] = el.value;
        H.changed(); H.render();
      };
    });
  });
}
