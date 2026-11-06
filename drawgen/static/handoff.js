// The Analysis tab has two panes on one document: CalculiX (analysis.js) and OpenCourant (explicit.js). Switching
// the Solver hands the view over: camera, selected faces / edges / vertices / bodies / reference points, selection
// mode, selected node of the model tree, panel width and side.

const SEL = ["faces", "edges", "vertices", "bodies", "points"];

/** State of a pane: three {camera, controls}, sel (shellmodel selState), tree (paneltree), panel (element). */
export function state(three, sel, tree, panel) {
  const st = {};
  if (three) {
    const c = three.camera;
    st.camera = { pos: c.position.toArray(), quat: c.quaternion.toArray(), up: c.up.toArray(), zoom: c.zoom,
                  top: c.top, bottom: c.bottom, target: three.controls.target.toArray() };
  }
  if (sel) {
    st.sel = {};
    for (const k of SEL) st.sel[k] = [...(sel[k] || [])];
    st.sel.types = [...(sel.types || [])].filter(t => SEL.includes(t));
    st.sel.prop = sel.prop; st.sel.angle = sel.angle;
  }
  if (tree) st.tree = tree.selected();
  if (panel) st.width = panel.style.width || "";
  if (panel) st.left = panel.parentElement.classList.contains("tp-left");
  return st;
}

/** Applies a state to a pane: three, sel, tree, panel as for state(); after() redraws. */
export function apply(st, three, sel, tree, panel, after) {
  if (!st) return;
  if (three && st.camera) {
    const c = three.camera, s = st.camera;
    c.position.fromArray(s.pos); c.up.fromArray(s.up); c.quaternion.fromArray(s.quat); c.zoom = s.zoom;
    const half = (s.top - s.bottom) / 2 || 100, w = three.box.clientWidth || 1, h = three.box.clientHeight || 1;
    c.top = half; c.bottom = -half; c.left = -half * w / h; c.right = half * w / h;
    three.controls.target.fromArray(s.target);
    c.updateProjectionMatrix();
    three.zoomed = true;
  }
  if (sel && st.sel) {
    for (const k of SEL) sel[k] = new Set(st.sel[k] || []);
    if (st.sel.types && st.sel.types.length) sel.types = new Set(st.sel.types);
    if (st.sel.prop) sel.prop = st.sel.prop;
    if (st.sel.angle) sel.angle = st.sel.angle;
  }
  if (panel && st.width) panel.style.width = st.width;
  if (tree && st.left !== undefined && tree.side) tree.side(st.left);
  if (tree && st.tree) tree.select(st.tree);
  if (after) after();
}

/** Hands the view from one pane ({ready(), state(), apply(st)}) to the other once it is ready (5 s at most). */
export async function handover(from, to) {
  if (!from || !to) return;
  const st = from.state();
  for (let i = 0; i < 50; i++) {
    if (to.ready()) { to.apply(st); return; }
    await new Promise(r => setTimeout(r, 100));
  }
}
