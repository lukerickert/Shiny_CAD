# -*- coding: utf-8 -*-
"""Browser tests (Playwright, headless Chromium): the main workflows of the interface. Any JavaScript error on
the page fails the test. Skipped when Playwright or its browser is not installed
(py -m pip install playwright, then py -m playwright install chromium)."""
import logging
import math
import os
import time

import pytest

from conftest import plate, sketch_part

pw = pytest.importorskip("playwright.sync_api")
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@pytest.fixture(scope="module")
def ui_browser():
    with pw.sync_playwright() as p:
        exe = os.environ.get("DRAWGEN_CHROMIUM") or None
        try:
            b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as e:
            pytest.skip("Chromium for Playwright not installed: %s" % str(e).splitlines()[0])
        yield b
        b.close()


@pytest.fixture
def page(ui_browser, server_url, client):
    pg = ui_browser.new_page(viewport={"width": 1600, "height": 950})
    errors = []
    pg.on("pageerror", lambda e: errors.append("page error: %s" % e))
    pg.on("console", lambda m: errors.append("console: %s (%s)" % (m.text, m.location.get("url", "")))
          if m.type == "error" and "favicon" not in m.location.get("url", "") else None)
    pg.on("dialog", lambda d: d.accept(pg.__dict__.get("_answer", "")) if d.type == "prompt" else d.accept())
    pg.goto(server_url + "/")
    pg.wait_for_load_state("networkidle")
    pg.wait_for_function("window.__part && window.__asm && window.projectInfo && window.projectInfo()")
    yield pg
    pg.close()
    assert not errors, "\n".join(errors)


def tab(pg, name):
    if name == "sketch":            # the Sketches pane of the Drawings tab
        pg.click(".tab[data-tab=annotate]")
        pg.click("#tab-annotate .dmode button[data-dmode=sketch]")
    else:
        pg.click(".tab[data-tab=%s]" % name)
    time.sleep(0.3)


def wait_text(pg, sel, text, timeout=60000):
    pg.wait_for_function("([s, t]) => (document.querySelector(s) || {}).textContent && document.querySelector(s).textContent.includes(t)",
                         arg=[sel, text], timeout=timeout)


def file_menu(pg, pane):
    """Opens the File menu of the tab (a click on the button toggles it)."""
    if not pg.is_visible("%s .dd > .dd-menu.file-menu" % pane):
        pg.click("%s .dd > .dd-btn" % pane)


# --------------------------------------------------------------------------- tests

def test_all_tabs_open(page):
    for t in ("project", "annotate", "sketch", "part", "asm"):
        tab(page, t)
        assert page.is_visible("#tab-" + t)
    assert page.locator(".tab[data-tab=drawings]").count() == 0 and page.locator(".tab[data-tab=editor]").count() == 0


def test_title_block_editor_window(page, client):
    """Title block editor window: opened from the Drawings toolbar and from the Title block section of the drawing
    settings panel, filled from the saved configuration, preview, save, Close and Escape."""
    tab(page, "annotate")
    assert page.is_hidden("#tb-dialog")
    page.click("#tb-open")
    assert page.is_visible("#tb-dialog")
    w0 = client.get("/api/config").get_json()["title_block"]["width_mm"]
    assert float(page.input_value("#tb-width_mm")) == w0
    page.wait_for_selector("#tb-sheet svg", state="attached")
    page.fill("#tb-width_mm", str(w0 + 10))
    page.click("#tb-preview")
    page.click("#tb-close")
    assert page.is_hidden("#tb-dialog")
    # reopened: the unsaved width is discarded
    page.click("#tb-open2")
    assert float(page.input_value("#tb-width_mm")) == w0
    page.fill("#tb-width_mm", str(w0 + 10))
    page.click("#tb-save")
    wait_text(page, "#status", "Title block, line widths and text heights saved")
    assert client.get("/api/config").get_json()["title_block"]["width_mm"] == w0 + 10
    page.keyboard.press("Escape")
    assert page.is_hidden("#tb-dialog")
    page.click("#tb-open")
    page.fill("#tb-width_mm", str(w0))
    page.click("#tb-save")
    wait_text(page, "#status", "saved")
    page.click("#tb-close")
    assert client.get("/api/config").get_json()["title_block"]["width_mm"] == w0


def test_project_tab_shows_open_project(page):
    tab(page, "project")
    wait_text(page, "#pj-title", "tests")


def test_part_sketch_extrude_save(page, client):
    tab(page, "part")
    page.click("#tab-part [data-add=sketch]")
    page.get_by_role("button", name="Draw", exact=True).click()
    page.wait_for_selector("#tab-sketch:not([hidden])")
    page.keyboard.press("w")
    page.keyboard.type("0,0")
    page.keyboard.press("Enter")
    page.keyboard.type("100,50")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    page.keyboard.press("Control+e")
    page.wait_for_selector("#tab-part:not([hidden])")
    wait_text(page, "#pt-props", "Extrude")                         # Next: Extrude (1)
    page.keyboard.press("1")
    page.wait_for_selector("#pf-depth")
    page.fill("#pf-depth", "20")
    page.dispatch_event("#pf-depth", "change")
    page.click("#pt-cmdfinish")
    wait_text(page, "#pt-info", "Volume 100 cm^3")
    page.__dict__["_answer"] = "ui_box"
    page.keyboard.press("Control+s")                                # not saved yet: asks for the name
    for _ in range(50):
        if "ui_box" in client.get("/api/part/list").get_json():
            break
        time.sleep(0.2)
    assert "ui_box" in client.get("/api/part/list").get_json()
    file_menu(page, "#tab-part")
    assert page.input_value("#pt-list") == "ui_box"


def test_part_file_menu_load_and_make_drawing(page, client):
    client.put("/api/part/file/ui_plate", json=plate("ui_plate"))
    tab(page, "part")
    file_menu(page, "#tab-part")
    page.select_option("#pt-list", "ui_plate")
    wait_text(page, "#pt-info", "Volume 93.717 cm^3")
    file_menu(page, "#tab-part")
    page.click("#pt-draw")
    page.wait_for_selector("#tab-annotate:not([hidden])")
    page.wait_for_selector("#ann-canvas svg", timeout=120000)
    assert page.is_visible("#layout > aside")
    if os.environ.get("DRAWGEN_SHOTS"):
        page.wait_for_timeout(1000)
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "make_drawing.png"))


def add_part(pg, name):
    pg.click("#as-add-part")
    pg.wait_for_selector("#value-dialog:not([hidden])")
    pg.select_option("#value-dialog-select", name)
    pg.click("#value-dialog-ok")


def asm_state(pg, expr):
    return pg.evaluate("() => { const AS = window.__asm.AS; return %s; }" % expr)


def test_assembly_menu_drag_fix_and_mate(page, client):
    client.put("/api/part/file/ui_plate", json=plate("ui_plate"))
    tab(page, "asm")
    add_part(page, "ui_plate")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length === 1 && window.__asm.AS.bbox")
    add_part(page, "ui_plate")                                      # placed beside the first one
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length === 2")
    assert asm_state(page, "AS.asm.components.length") == 2
    # drag the second (unfixed) component
    page.keyboard.press("d")
    pos0 = asm_state(page, "AS.asm.components[1].pos.slice()")
    xy = page.evaluate("""() => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const c = AS.asm.components[1], m = t.pickables.find(o => o.userData.id === c.id);
        const b = new T.Box3().setFromObject(m), p = b.getCenter(new T.Vector3()).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""")
    page.mouse.move(*xy)
    page.mouse.down()
    page.mouse.move(xy[0] + 60, xy[1] - 40, steps=5)
    page.mouse.up()
    page.keyboard.press("d")
    pos1 = asm_state(page, "AS.asm.components[1].pos.slice()")
    assert pos1 != pos0
    # context menu of the list row: Fix in space
    page.click("#as-comps .as-comp[data-id='%s']" % asm_state(page, "AS.asm.components[1].id"), button="right")
    page.click("#as-menu button:has-text('Fix in space')")
    assert asm_state(page, "AS.asm.components[1].fixed") is True
    page.click("#as-comps .as-comp[data-id='%s']" % asm_state(page, "AS.asm.components[1].id"), button="right")
    page.click("#as-menu button:has-text('Unfix')")
    # mate the XY planes of both components through the plane and axis lists
    page.click("#as-tb-mates button[data-mate=coincident]")
    page.keyboard.press("Escape")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    for side, cid in (("a", ids[1]), ("b", ids[0])):
        page.select_option("#am-c" + side, cid)
        page.select_option("#am-d" + side, "plane:XY")
    page.wait_for_function("window.__asm.AS.asm.mates[0].a && window.__asm.AS.asm.mates[0].b")
    wait_text(page, "#status-text", "Mates solved")
    z = asm_state(page, "AS.asm.components[1].pos[2]")
    assert abs(z) < 1e-6


def test_sketch_tab_rectangle_dof(page):
    tab(page, "sketch")
    page.keyboard.press("w")
    page.keyboard.type("0,0")
    page.keyboard.press("Enter")
    page.keyboard.type("40,20")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    wait_text(page, "#tab-sketch", "DOF 4")
    # every constraint button has an icon; the dimension tools are in the constraint group
    assert page.locator("#sk-tools-con button[data-con] svg.tb-ico").count() == 12
    assert page.locator("#sk-tools-con button[data-tool=dim]").count() == 1
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "sketch_toolbar.png"), clip={"x": 0, "y": 180, "width": 820, "height": 100})


def test_part_hole_mesh_command(page, client):
    from drawgen import part
    p = plate("ui_hm")
    client.put("/api/part/file/ui_hm", json=p)
    base, _ = part.build(p)
    keys = [part.face_key(f) for f in base.faces() if f.geom_type.name == "CYLINDER"]
    tab(page, "part")
    file_menu(page, "#tab-part")
    page.select_option("#pt-list", "ui_hm")
    wait_text(page, "#pt-info", "Volume 93.717 cm^3")
    page.click("#tab-part .dd-btn:has-text('Faces')")
    page.click("#tab-part [data-add=hole_mesh]")
    page.wait_for_selector("#pf-hmcirc")
    page.evaluate("(keys) => { const P = window.__part, f = P.feat(P.PT.cmd.id); f.faces = keys; P.changedPart(); }", keys)
    page.click("#pt-cmdfinish")
    wait_text(page, "#pt-props", "20 blocks")


def test_analysis_tab_solve_and_results(page, client):
    from test_analysis import CCX, _two_plate_doc
    if CCX is None:
        pytest.skip("CalculiX (ccx) not found")
    doc = _two_plate_doc(client, "fea_ui")
    client.put("/api/analysis/file/fea_ui", json=doc)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("window.__feaLoadNamed('fea_ui')")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    assert page.input_value("#fa-source") == "assembly:fea_asm"
    assert page.locator("#fa-sups .fa-item").count() == 1 and page.locator("#fa-fasts .fa-item").count() == 1
    # add a beam by coordinates: a post on the top face of the upper plate
    page.click("#fa-add-beam")
    page.keyboard.press("Escape")
    for k, xyz in (("a", (20, 25, 20)), ("b", (20, 25, 120))):
        for i, v in enumerate(xyz):
            page.fill("#fmb-%s%d" % (k, i), str(v))
            page.dispatch_event("#fmb-%s%d" % (k, i), "change")
    page.wait_for_function("window.__fea.FA.doc.members[0].b && window.__fea.FA.doc.members[0].b.xyz[2] === 120")
    # connect end A to the top face of the upper plate by picking it in the view
    page.click("#fa-members [data-pickc=a]")
    xy = page.evaluate("""() => { const FA = window.__fea.FA, t = FA.three;
        const m = t.pickables.find(o => o.userData.comp === 'c2'); const T = m.geometry.boundingBox;
        const p = new (Object.getPrototypeOf(T.max).constructor)(10, 10, 10).applyMatrix4(m.matrixWorld).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""")
    page.mouse.click(*xy)
    page.wait_for_function("window.__fea.FA.doc.members[0].a.face")
    page.evaluate("""() => { const FA = window.__fea.FA; FA.doc.members[0].a = {xyz: [20, 25, 20], face: FA.doc.members[0].a.face};
        FA.doc.loads.push({id: 'lx', name: 'tip', type: 'force', target: {member: FA.doc.members[0].id, end: 'b'}, value: [0, 100, 0]}); }""")
    page.click("#fa-solve")
    page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.tables", timeout=300000)
    wait_text(page, "#fa-results", "Fasteners")
    assert page.is_visible("#fa-legend")
    assert page.input_value("#fa-show") == "results"
    page.select_option("#fa-state", "preload")
    wait_text(page, "#fa-legend", "Step 1")
    page.select_option("#fa-field", "u")
    wait_text(page, "#fa-legend", "|u|")
    page.select_option("#fa-show", "model")
    assert not page.is_visible("#fa-legend")


def test_analysis_sketch_geometry(page, client):
    """Geometry = a part with a sketch only: the sketch is drawn, the part is not a body, Sketch beams puts a beam
    on each line, Beam snaps its ends to the sketch corners; the toolbar buttons have icons. With CalculiX: the
    frame solves (supports at two corners, load at a third)."""
    client.put("/api/part/file/ui_skf", json=sketch_part("ui_skf", 200, 80))
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("() => { const s = document.getElementById('fa-source'); s.insertAdjacentHTML('beforeend', '<option value=\"part:ui_skf\">ui_skf</option>'); s.value = 'part:ui_skf'; s.dispatchEvent(new Event('change')); }")
    page.wait_for_function("window.__fea.FA.sketches && window.__fea.FA.sketches.length === 1")
    wait_text(page, "#fa-bodies", "sketches only")
    wait_text(page, "#fa-info", "1 sketch")
    assert page.locator("#tab-fea .toolbar button.ico-btn svg.tb-ico").count() >= 11
    page.click("#fa-add-beam")
    for corner in ((0, 0, 0), (200, 80, 0)):
        xy = page.evaluate("(p) => { const FA = window.__fea.FA, T = FA.three, r = T.renderer.domElement.getBoundingClientRect();"
                           " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
                           " return [r.left + (v.x + 1) / 2 * r.width + 4, r.top + (1 - v.y) / 2 * r.height + 3]; }", list(corner))
        page.mouse.click(*xy)
        time.sleep(0.2)
    m = page.evaluate("window.__fea.FA.doc.members[0]")
    assert m["a"]["xyz"] == [0, 0, 0] and m["b"]["xyz"] == [200, 80, 0]
    page.click("#fa-add-skm")
    page.wait_for_function("window.__fea.FA.doc.members.length === 5")
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "fea_sketch.png"))
    page.click("#fa-add-skm")
    wait_text(page, "#status-text", "0 beam(s)")
    assert page.evaluate("window.__fea.FA.doc.members.length") == 5
    # a click on a corner selects the member end (large orange ball); Support then applies to it without a pick
    scr = ("(p) => { const FA = window.__fea.FA, T = FA.three, r = T.renderer.domElement.getBoundingClientRect();"
           " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width + 4, r.top + (1 - v.y) / 2 * r.height + 3]; }")
    xy = page.evaluate(scr, [200, 0, 0])
    page.mouse.move(xy[0] + 30, xy[1] + 30)
    page.mouse.move(*xy)
    assert page.evaluate("!!window.__fea.FA.three.hover && window.__fea.FA.three.renderer.domElement.style.cursor === 'pointer'")
    page.mouse.click(*xy)
    page.wait_for_function("window.__fea.FA.sel && window.__fea.FA.sel.end")
    wait_text(page, "#fa-members", "selected (200, 0, 0)")
    assert page.evaluate("""() => window.__fea.FA.three.pickables.some(o => o.userData.end && o.geometry.parameters.radius > (window.__fea.FA.size / 300) * 3)""")
    page.click("#fa-add-sup")
    page.wait_for_function("(() => { const s = window.__fea.FA.doc.supports[0]; return s && s.target && s.target.end; })()")
    assert page.evaluate("window.__fea.FA.pick") is None
    # Support with nothing selected: a pick that takes a member end
    page.evaluate("() => { const FA = window.__fea.FA; FA.sel = null; }")
    page.click("#fa-add-sup")
    xy = page.evaluate(scr, [0, 80, 0])
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const s = window.__fea.FA.doc.supports[1]; return s && s.target && s.target.end; })()")
    # Load: a click on the middle of a member gives a line load
    page.evaluate("() => { window.__fea.FA.sel = null; }")
    page.click("#fa-add-load")
    xy = page.evaluate(scr, [100, 80, 0])
    page.mouse.click(xy[0] - 4, xy[1] - 3)
    page.wait_for_function("(() => { const l = window.__fea.FA.doc.loads[0]; return l && l.type === 'line' && l.target && l.target.member; })()")
    assert page.evaluate("window.__fea.FA.doc.loads[0].value") == [0, 0, -1]
    from test_analysis import CCX
    if CCX is None:
        return
    page.click("#fa-solve")
    page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.tables", timeout=300000)


def test_part_remove_faces_click_picks_face(page, client):
    """In a parameter panel (Remove faces) a click on a face picks it without pressing Pick faces first."""
    client.put("/api/part/file/ui_rf", json=plate("ui_rf"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_rf')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    page.click("#tab-part .dd-btn:has-text('Faces')")
    page.click("#tab-part [data-add=defeature]")
    page.wait_for_function("window.__part.PT.cmd && window.__part.PT.cmd.legacyDefs")
    xy = page.evaluate("""() => { const PT = window.__part.PT, t = PT.three;
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + r.width / 2, r.top + r.height / 2]; }""")
    page.mouse.click(*xy)
    page.wait_for_function("(window.__part.feat(window.__part.PT.cmd.id).faces || []).length === 1")


def test_part_hover_round_edges_and_faces(page, client):
    """Hover text: Ø for a circular edge and a cylindrical face, the length for a straight edge."""
    client.put("/api/part/file/ui_hov", json=plate("ui_hov"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_hov')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    t = page.evaluate("""() => { const P = window.__part, m = P.PT.mesh;
        const ce = m.edge_keys.find(k => k.round), le = m.edge_keys.find(k => !k.round), cf = m.face_keys.find(k => k && k.round);
        return [P.hoverText({ kind: "edge", key: ce }), P.hoverText({ kind: "edge", key: le }), P.hoverText({ kind: "face", key: cf, solid: 0 })]; }""")
    assert t[0] == "Edge, Ø20 mm"
    assert t[1].startswith("Edge, ") and "Ø" not in t[1] and t[1].endswith(" mm")
    assert t[2].endswith(", Ø20 mm")


def test_analysis_plate_by_points(page, client):
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.click("#fa-add-ppts")
    page.keyboard.press("Escape")
    for i in range(4):
        page.click("#fpl-row")
    pts = [[0, 0, 0], [400, 0, 0], [400, 300, 0], [0, 300, 0]]
    for i, q in enumerate(pts):
        for j, v in enumerate(q):
            sel = "#fa-plates tr[data-i='%d'] input[data-j='%d']" % (i, j)
            page.fill(sel, str(v))
            page.dispatch_event(sel, "change")
    page.wait_for_function("window.__fea.FA.geo.components.some(c => c.plate && c.mesh)", timeout=30000)
    assert page.evaluate("window.__fea.FA.doc.plates[0].points.length") == 4


def test_dimension_tolerance_fields(page, client):
    """A selected dimension shows its properties; an ISO 286 class and a deviation are applied."""
    client.put("/api/part/file/ui_tol", json=plate("ui_tol"))
    tab(page, "part")
    file_menu(page, "#tab-part")
    page.select_option("#pt-list", "ui_tol")
    wait_text(page, "#pt-info", "Volume")
    file_menu(page, "#tab-part")
    page.click("#pt-draw")
    page.wait_for_selector("#ann-canvas svg", timeout=120000)
    page.wait_for_function("typeof ED !== 'undefined' && ED.d && ED.d.maps && ED.snapPts.length")
    page.evaluate("""() => { setTool('h'); const P = ED.snapPts.filter(p => p.view === 'front');
        const a = P[0], b = P.find(p => Math.abs(p.Y - a.Y) < 1e-6 && Math.abs(p.X - a.X) > 5);
        toolClick(a.X, a.Y); toolClick(b.X, b.Y); toolClick((a.X + b.X) / 2, a.Y + 15); setTool('select'); }""")
    page.wait_for_function("ED.anns.length === 1 && document.querySelector('g.ann')")
    page.evaluate("select(ED.anns[0].id)")
    assert page.is_visible("#ann-form") and page.is_visible("#ann-tolmode")
    page.select_option("#ann-tolmode", "fit")
    page.fill("#ann-fit", "h7")
    page.dispatch_event("#ann-fit", "change")
    page.wait_for_function("ED.anns[0].tol && ED.anns[0].tol.fit === 'h7'")
    wait_text(page, "#ann-fit-result", "µm")
    page.select_option("#ann-tolmode", "dev")
    page.fill("#ann-plus", "0")
    page.fill("#ann-minus", "-40,5")
    page.dispatch_event("#ann-minus", "change")
    page.wait_for_function("ED.anns[0].tol.mode === 'dev' && Math.abs(ED.anns[0].tol.minus + 0.0405) < 1e-12")
    page.evaluate("annShowProps()")
    assert page.input_value("#ann-minus") == "-40.5" and page.input_value("#ann-plus") == "0"


def test_surface_roughness_guide_sets_field(page):
    tab(page, "annotate")
    page.wait_for_selector("#ra-guide")
    page.click("#ra-guide")
    page.wait_for_selector("#ref-dialog:not([hidden]) .ra-table")
    assert page.locator(".ra-table td.ra-usual").count() > 30
    page.screenshot(path=os.path.join(os.environ.get("DRAWGEN_SHOTS", ""), "ra.png") if os.environ.get("DRAWGEN_SHOTS") else None)
    page.click(".ra-table th.ra-head[data-ra='0.8'] >> nth=0")
    assert page.is_hidden("#ref-dialog")
    assert page.input_value("#fields input[data-key=SurfaceFinish]") == "Ra 0.8"


def test_fit_calculator(page, client):
    tab(page, "annotate")
    page.click("#ann-reference")
    page.click("#ref-tabs button[data-ref=fits]")
    page.wait_for_selector("#fit-size")
    page.fill("#fit-size", "25")
    page.fill("#fit-hole", "H7")
    page.fill("#fit-shaft", "u6")
    page.dispatch_event("#fit-shaft", "change")
    wait_text(page, "#fit-out", "Interference fit")
    wait_text(page, "#fit-out", "Maximum interference 0.0610 mm")
    page.click("#ref-body [data-pf] >> text=H7/g6")
    wait_text(page, "#fit-out", "Clearance fit")
    page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "fits.png")) if os.environ.get("DRAWGEN_SHOTS") else None
    page.click("#ref-body [data-pf] >> text=H7/k6")
    wait_text(page, "#fit-out", "Transition fit")
    assert page.locator("#ref-body .ref-table").count() >= 2


def test_options_units_and_left_handed_keys(page, client):
    """Options dialog: inch units relabel the deviation fields; left-handed keys relabel the tooltips and work."""
    tab(page, "annotate")
    page.click("#opt-open")
    page.wait_for_selector("#opt-dialog:not([hidden])")
    try:
        page.select_option("#opt-keys", "left")
        page.wait_for_function("OPT.keys === 'left'")
        assert "(J)" in page.get_attribute("#ann-tools button[data-tool=select]", "title")
        assert "(P)" in page.get_attribute("#tab-sketch button[data-tool=line]", "title")
        assert page.locator("#opt-keylist kbd").count() > 40
        page.select_option("#opt-units", "inch")
        page.wait_for_function("OPT.units === 'inch'")
        assert page.inner_text(".dev-unit >> nth=0") == "in"
        assert page.evaluate("devFromField('0.001')") == 0.0254
        if os.environ.get("DRAWGEN_SHOTS"):
            page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "options.png"))
        page.click("#opt-close")
        page.keyboard.press("h")
        page.wait_for_function("ED.tool === 'h'")
        page.keyboard.press("j")
        page.wait_for_function("ED.tool === 'select'")
    finally:
        client.put("/api/options", json={"units": "mm", "keys": "default"})
        page.evaluate("Object.assign(OPT, {units: 'mm', keys: 'default'}); window.dispatchEvent(new Event('optionschanged'))")
    assert "(S)" in page.get_attribute("#ann-tools button[data-tool=select]", "title")


def test_sketch_on_drawing_view(page, client):
    """Drawings tab, Sketch tool: a click on the front view opens the sketch editor on that view with the drawing as
    the sheet; a line typed in view coordinates is stored with the drawing after Finish sketch."""
    client.put("/api/part/file/ui_dsk", json=plate("ui_dsk"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_dsk')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    file_menu(page, "#tab-part")
    page.click("#pt-draw")
    page.wait_for_function("typeof ED !== 'undefined' && ED.d && ED.d.maps && ED.d.maps.front && ED.d.name.includes('ui_dsk')", timeout=120000)
    page.evaluate("setTool('sketch'); toolClick(ED.d.maps.front[0], ED.d.maps.front[1])")
    page.wait_for_selector("#sk-partbar:not([hidden])", timeout=60000)
    assert page.is_visible("#tab-sketch") and page.is_hidden("#tab-annotate")
    wait_text(page, "#sk-parttitle", "Front")
    assert page.locator("#sk-sheet line").count() > 4
    assert page.evaluate("document.querySelector('.tab.active').dataset.tab") == "annotate"
    page.click("#sk-canvas")
    page.keyboard.press("q")
    page.keyboard.type("0,-33")
    page.keyboard.press("Enter")
    page.keyboard.type("10,-33")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    # a zoomed view is kept after a geometry change (fitIfNeeded): geometry inside the window, no change; outside,
    # the view is moved, the zoom kept
    v0 = page.evaluate("""() => { const K = window.__sk.SK; K.view.s *= 4; const W = document.getElementById('sk-canvas').clientWidth, H = document.getElementById('sk-canvas').clientHeight;
        K.view.ox = W / 2 - 5 * K.view.s; K.view.oy = H / 2 - 33 * K.view.s; window.__sk.fitIfNeeded(); return [K.view.s, K.view.ox, K.view.oy]; }""")
    assert page.evaluate("[window.__sk.SK.view.s, window.__sk.SK.view.ox, window.__sk.SK.view.oy]") == v0
    page.evaluate("() => { const K = window.__sk.SK; K.view.ox += 5000; window.__sk.fitIfNeeded(); }")
    assert page.evaluate("window.__sk.SK.view.s") == v0[0]
    assert abs(page.evaluate("window.__sk.SK.view.ox") - v0[1]) < 1
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "sketch_on_view.png"))
    page.click("#sk-partfinish")
    page.wait_for_function("ED.d && (ED.d.sketches || []).includes('front')", timeout=60000)
    assert page.is_visible("#tab-annotate") and page.is_visible("#ann-sketches")
    if os.environ.get("DRAWGEN_SHOTS"):
        page.wait_for_timeout(500)
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "sketch_on_view_done.png"))
    client.put("/api/drawing/sketch/%s/front" % page.evaluate("ED.d.ann_name"), json={"doc": {}})


def test_partition_method_step_face_click(page, client):
    """Partition: a click on a face in the Method step sets the method to an extended face and goes to its step."""
    client.put("/api/part/file/ui_pt", json=plate("ui_pt"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_pt')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    page.evaluate("window.__part.startCommand('split')")
    page.wait_for_function("window.__part.PT.cmd && window.__part.PT.cmd.step === 0")
    xy = page.evaluate("""() => { const r = window.__part.PT.three.renderer.domElement.getBoundingClientRect();
        return [r.left + r.width / 2, r.top + r.height / 2]; }""")
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const P = window.__part, f = P.feat(P.PT.cmd.id); return f.method === 'face' && f.face && P.PT.cmd.step === 1; })()")


def test_point_from_vertex_click(page, client):
    """Point feature, Coordinates: a click near a visible vertex of the part copies its coordinates."""
    client.put("/api/part/file/ui_vx", json=plate("ui_vx"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_vx')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    page.evaluate("window.__part.startCommand('point')")
    page.wait_for_function("window.__part.PT.cmd && window.__part.PT.cmd.step === 0")
    js = """() => { const P = window.__part, t = P.PT.three, r = t.renderer.domElement.getBoundingClientRect();
        const ray = new P.THREE.Raycaster(); let best = null;
        for (const pl of P.PT.mesh.edges) for (const q of [pl[0], pl[pl.length - 1]]) {
          const v = new P.THREE.Vector3(...q).project(t.camera);
          const x = r.left + (v.x + 1) / 2 * r.width, y = r.top + (1 - v.y) / 2 * r.height;
          const h = P.pickAt({ clientX: x, clientY: y }, ['point']);
          if (h && h.vertex && Math.abs(h.point[0] - q[0]) + Math.abs(h.point[1] - q[1]) + Math.abs(h.point[2] - q[2]) < 1e-6) { best = [x, y, q]; break; }
        }
        return best; }"""
    x, y, q = page.evaluate(js)
    page.mouse.move(x, y)
    page.mouse.click(x, y)
    page.wait_for_function("([q]) => { const P = window.__part, f = P.feat(P.PT.cmd.id); return f.point && Math.abs(f.point[0] - q[0]) + Math.abs(f.point[1] - q[1]) + Math.abs(f.point[2] - q[2]) < 1e-6; }", arg=[q])
    assert page.evaluate("window.__part.hoverText({kind: 'point', vertex: true, point: [1, 2, 3]})") == "Vertex (1, 2, 3) mm"


def test_mate_sides_by_click(page, client):
    """Coincident, then a click on a face of each component fills A and B without choosing the component in the
    lists; no reference planes or axes are drawn; with Datums checked, a click on a reference axis gives a datum side."""
    client.put("/api/part/file/ui_mc", json=plate("ui_mc"))
    tab(page, "asm")
    add_part(page, "ui_mc")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_mc")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    centre = """(i) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const c = AS.asm.components[i], m = t.pickables.find(o => o.userData.id === c.id);
        const b = new T.Box3().setFromObject(m), p = b.getCenter(new T.Vector3()).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }"""
    n = asm_state(page, "AS.asm.components.length")
    page.click("#as-tb-mates button[data-mate=coincident]")
    page.wait_for_function("window.__asm.AS.selMate && window.__asm.AS.three.datumPickables.length === 0")
    if os.environ.get("DRAWGEN_SHOTS"):
        page.mouse.move(*page.evaluate(centre, n - 1))
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "mate_pick.png"))
    page.mouse.click(*page.evaluate(centre, n - 1))
    page.wait_for_function("(() => { const m = window.__asm.AS.asm.mates.slice(-1)[0]; return m.a && m.a.face !== undefined && !m.b; })()")
    page.mouse.click(*page.evaluate(centre, n - 2))
    page.wait_for_function("(() => { const m = window.__asm.AS.asm.mates.slice(-1)[0]; return m.a && m.b && m.b.face !== undefined; })()")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    m = asm_state(page, "AS.asm.mates.slice(-1)[0]")
    assert m["a"]["comp"] == ids[n - 1] and m["b"]["comp"] == ids[n - 2]
    # with Datums checked, a reference axis picked by a click on its line outside the parts
    page.click("#as-tb-mates button[data-mate=coincident]")
    page.check("#as-datums")
    page.wait_for_function("window.__asm.AS.three.datumPickables.some(o => o.isLine)")
    xy = page.evaluate("""() => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const r = t.renderer.domElement.getBoundingClientRect();
        for (const ln of t.datumPickables.filter(o => o.isLine)) {
          const a = ln.geometry.attributes.position;
          for (const f of [0.97, 0.03, 0.9, 0.1]) {
            const p = new T.Vector3(a.getX(0) + (a.getX(1) - a.getX(0)) * f, a.getY(0) + (a.getY(1) - a.getY(0)) * f, a.getZ(0) + (a.getZ(1) - a.getZ(0)) * f).applyMatrix4(ln.matrixWorld).project(t.camera);
            const x = r.left + (p.x + 1) / 2 * r.width, y = r.top + (1 - p.y) / 2 * r.height;
            if (x < r.left || x > r.right || y < r.top || y > r.bottom) continue;
            const h = window.__asm.mateHitAt({ clientX: x, clientY: y });
            if (h && h.datum) return [x, y];
          }
        }
        return null; }""")
    assert xy
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const m = window.__asm.AS.asm.mates.slice(-1)[0]; return m.a && m.a.datum; })()")
    page.uncheck("#as-datums")


def test_mate_pick_cursor_in_drag_mode(page, client):
    """While a mate side is picked, the cursor over a fixed component is a crosshair also in Drag mode, and the click
    fills the side; Pick ends drag mode."""
    client.put("/api/part/file/ui_mcur", json=plate("ui_mcur"))
    tab(page, "asm")
    add_part(page, "ui_mcur")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_mcur")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    n = asm_state(page, "AS.asm.components.length")
    page.evaluate("(i) => { window.__asm.AS.asm.components[i].fixed = true; }", n - 2)
    page.click("#as-tb-mates button[data-mate=coincident]")
    page.wait_for_function("window.__asm.AS.selMate")
    page.mouse.move(5, 5)
    page.keyboard.press("d")
    assert asm_state(page, "AS.dragMode") == "move"
    xy = page.evaluate("""(i) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const c = AS.asm.components[i], m = t.pickables.find(o => o.userData.id === c.id);
        const b = new T.Box3().setFromObject(m), p = b.getCenter(new T.Vector3()).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""", n - 2)
    page.mouse.move(xy[0] + 1, xy[1] + 1)
    page.mouse.move(*xy)
    assert page.evaluate("() => window.__asm.AS.three.renderer.domElement.style.cursor") == "crosshair"
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const m = window.__asm.AS.asm.mates.slice(-1)[0]; return m.a && m.a.face !== undefined; })()")
    page.click("#am-pb")
    assert asm_state(page, "AS.dragMode") in (False, None, "")


def test_unsatisfied_mate_marked_status_one_line(page, client):
    """Two conflicting mates (the second is left out): the status line stays one line high with the full text as tooltip, and the mates
    are marked in the mates list."""
    client.put("/api/part/file/ui_us", json=plate("ui_us"))
    tab(page, "asm")
    add_part(page, "ui_us")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_us")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    n = asm_state(page, "AS.asm.components.length")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    for plane in ("plane:XY", "plane:YZ"):
        page.click("#as-tb-mates button[data-mate=coincident]")
        page.keyboard.press("Escape")
        page.select_option("#am-type", "parallel" if plane == "plane:YZ" else "coincident")
        page.select_option("#am-ca", ids[n - 1]); page.select_option("#am-da", "plane:XY")
        page.select_option("#am-cb", ids[n - 2]); page.select_option("#am-db", plane)
    page.wait_for_function("Object.keys(window.__asm.AS.unsat || {}).length >= 1", timeout=60000)
    wait_text(page, "#status-text", "left out")
    h = page.evaluate("() => document.getElementById('status-text').getBoundingClientRect().height")
    assert h < 24
    assert "left out" in page.get_attribute("#status-text", "title")
    assert page.locator("#as-mates .as-comp.bad").count() >= 1


def test_drag_unfixed_mated_pair_and_display(page, client):
    """Coincident XY and concentric Z between two components, none fixed: a drag moves the pair together (it is
    not held in space). Display: Transparent, Hidden lines removed and Wireframe change the materials."""
    client.put("/api/part/file/ui_pair", json=plate("ui_pair"))
    tab(page, "asm")
    add_part(page, "ui_pair")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_pair")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    page.evaluate("() => { const A = window.__asm.AS.asm; A.components.forEach(c => { c.fixed = false; }); A.mates = []; }")
    n = asm_state(page, "AS.asm.components.length")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    for typ, d in (("coincident", "plane:XY"), ("concentric", "axis:Z")):
        page.click("#as-tb-mates button[data-mate=%s]" % typ)
        page.keyboard.press("Escape")
        page.select_option("#am-ca", ids[n - 1]); page.select_option("#am-da", d)
        page.select_option("#am-cb", ids[n - 2]); page.select_option("#am-db", d)
        page.wait_for_function("(() => { const m = window.__asm.AS.asm.mates.slice(-1)[0]; return m.a && m.b; })()")
    wait_text(page, "#status-text", "Mates solved")
    time.sleep(0.5)
    pos = lambda i: asm_state(page, "AS.asm.components.find(c => c.id === '%s').pos.slice()" % ids[i])
    a0, b0 = pos(n - 1), pos(n - 2)
    page.keyboard.press("d")
    xy = page.evaluate("""([cid]) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const m = t.pickables.find(o => o.userData.id === cid);
        const b = new T.Box3().setFromObject(m), p = b.getCenter(new T.Vector3()).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""", [ids[n - 1]])
    page.mouse.move(*xy)
    page.mouse.down()
    page.mouse.move(xy[0] + 60, xy[1] - 40, steps=5)
    page.mouse.up()
    wait_text(page, "#status-text", " moved ")
    page.keyboard.press("d")
    a1, b1 = pos(n - 1), pos(n - 2)
    da = [a1[k] - a0[k] for k in range(3)]
    db = [b1[k] - b0[k] for k in range(3)]
    assert max(abs(v) for v in da) > 1 and all(abs(da[k] - db[k]) < 1e-3 for k in range(3))
    for mode, check in (("transparent", "m.transparent && m.opacity < 1"), ("hidden", "!m.colorWrite && m.depthWrite"), ("wire", "!m.colorWrite && !m.depthWrite")):
        page.select_option("#as-display", mode)
        assert page.evaluate("() => window.__asm.AS.three.pickables.every(o => { const m = o.material; return %s; })" % check)
        if os.environ.get("DRAWGEN_SHOTS"):
            page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "asm_%s.png" % mode))
    page.select_option("#as-display", "shaded")


def test_drag_pulls_mated_chain(page, client):
    """BASE fixed, SLIDE coincident on BASE (free in the plane), CAM held to SLIDE (distance 60 mm and concentric): a
    drag of CAM moves SLIDE with it in the plane, live while dragging and on release; BASE stays."""
    client.put("/api/part/file/ui_ch", json=plate("ui_ch"))
    tab(page, "asm")
    for _ in range(3):
        add_part(page, "ui_ch")
        time.sleep(0.3)
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 3 && window.__asm.AS.bbox")
    n = asm_state(page, "AS.asm.components.length")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    base, slide, cam = ids[n - 3], ids[n - 2], ids[n - 1]
    page.evaluate("""([b, s, c]) => { const A = window.__asm.AS.asm; A.components.forEach(x => { x.fixed = x.id === b; });
        A.mates = [{id: 'k1', type: 'coincident', a: {comp: s, datum: 'plane:XY'}, b: {comp: b, datum: 'plane:XY'}, value: 0},
                   {id: 'k2', type: 'distance', a: {comp: c, datum: 'plane:XY'}, b: {comp: s, datum: 'plane:XY'}, value: 60},
                   {id: 'k3', type: 'concentric', a: {comp: c, datum: 'caxis:Z'}, b: {comp: s, datum: 'caxis:Z'}, value: 0}]; }""", [base, slide, cam])
    page.click("#as-solve")
    wait_text(page, "#status-text", "Mates solved")
    pos = lambda i: asm_state(page, "AS.asm.components.find(c => c.id === '%s').pos.slice()" % i)
    b0, s0, c0 = pos(base), pos(slide), pos(cam)
    page.keyboard.press("d")
    xy = page.evaluate("""([cid]) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const m = t.pickables.find(o => o.userData.id === cid), b = new T.Box3().setFromObject(m);
        const r = t.renderer.domElement.getBoundingClientRect();
        for (let i = 0; i < 400; i++) {                 // a point of the box whose first hit is the component
          const q = new T.Vector3(b.min.x + (b.max.x - b.min.x) * ((i % 20) + 0.5) / 20, b.min.y + (b.max.y - b.min.y) * (Math.floor(i / 20) + 0.5) / 20, b.max.z).project(t.camera);
          const nd = new T.Vector2(q.x, q.y), rc = new T.Raycaster(); rc.setFromCamera(nd, t.camera);
          const h = rc.intersectObjects(t.pickables, false);
          const sx = r.left + (q.x + 1) / 2 * r.width, sy = r.top + (1 - q.y) / 2 * r.height;
          if (h.length && h[0].object.userData.id === cid && document.elementFromPoint(sx, sy) === t.renderer.domElement) return [sx, sy];
        }
        return null; }""", [cam])
    assert xy
    page.mouse.move(*xy)
    page.mouse.down()
    page.mouse.move(xy[0] + 60, xy[1] - 40, steps=5)
    # live drag: the solver result moves SLIDE while the button is down
    page.wait_for_function("(s) => window.__asm.AS.three.group.children.some(o => o.userData.cid === s && o.position.length() > 1)", arg=slide)
    page.mouse.up()
    wait_text(page, "#status-text", "with 1 mated component")
    page.keyboard.press("d")
    b1, s1, c1 = pos(base), pos(slide), pos(cam)
    assert b1 == b0
    ds = [s1[k] - s0[k] for k in range(3)]
    dc = [c1[k] - c0[k] for k in range(3)]
    # SLIDE moved in the plane of BASE (the CAM may also turn about its axis: the grabbed point follows the cursor)
    assert max(abs(v) for v in ds[:2]) > 1 and abs(ds[2]) < 1e-3 and abs(dc[2]) < 1e-3
    assert "not satisfied" not in page.text_content("#status-text")


def test_mate_conflict_check_and_undo(page, client):
    """A coincident and a conflicting distance mate on the same planes: the solve leaves the second out (tag), the
    first is satisfied. Check: summary, tags, free motions of the component; Suppress conflicting; Ctrl+Z undoes."""
    client.put("/api/part/file/ui_cf", json=plate("ui_cf"))
    tab(page, "asm")
    add_part(page, "ui_cf")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_cf")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    n = asm_state(page, "AS.asm.components.length")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    base, mov = ids[n - 2], ids[n - 1]
    page.evaluate("""([b, m]) => { const A = window.__asm.AS.asm; A.components.forEach(x => { x.fixed = x.id === b; });
        A.mates = [{id: 'q1', type: 'coincident', a: {comp: m, datum: 'plane:XY'}, b: {comp: b, datum: 'plane:XY'}, value: 0},
                   {id: 'q2', type: 'distance', a: {comp: m, datum: 'plane:XY'}, b: {comp: b, datum: 'plane:XY'}, value: 30}]; }""", [base, mov])
    page.click("#as-solve")
    wait_text(page, "#status-text", "left out")
    page.wait_for_selector("#as-mates .as-comp[data-mid=q2] .mtag-conflict", state="attached")
    page.click("#as-check")
    wait_text(page, "#as-mates", "1 conflict")
    assert page.locator("#as-mates .as-comp[data-mid=q2] .mtag-conflict").count() == 1
    wait_text(page, "#as-comps", "free: 2 translations, 1 rotation")
    wait_text(page, "#as-comps", "fixed")
    page.click("#am-supconf")
    page.wait_for_function("window.__asm.AS.asm.mates.find(m => m.id === 'q2').suppressed === true")
    wait_text(page, "#as-mates", "0 conflicts")
    page.mouse.click(5, 300)
    page.keyboard.press("Control+z")
    page.wait_for_function("!window.__asm.AS.asm.mates.find(m => m.id === 'q2').suppressed")
    page.keyboard.press("Control+y")
    page.wait_for_function("window.__asm.AS.asm.mates.find(m => m.id === 'q2').suppressed === true")
    if os.environ.get("DRAWGEN_SHOTS"):
        page.click("#as-check")
        wait_text(page, "#as-mates", "0 conflicts")
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "asm_check.png"))


def test_rotate_held_component_turns_chain(page, client):
    """HANDLE held to SPINDLE (concentric, two coincident centre planes), SPINDLE concentric with BASE (fixed): Rotate
    on HANDLE turns SPINDLE with it about Z."""
    client.put("/api/part/file/ui_rc", json=plate("ui_rc"))
    tab(page, "asm")
    for _ in range(3):
        add_part(page, "ui_rc")
        time.sleep(0.3)
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 3 && window.__asm.AS.bbox")
    n = asm_state(page, "AS.asm.components.length")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    base, spin, hand = ids[n - 3], ids[n - 2], ids[n - 1]
    page.evaluate("""([b, s, h]) => { const A = window.__asm.AS.asm; A.components.forEach(x => { x.fixed = x.id === b; });
        A.mates = [{id: 'r1', type: 'concentric', a: {comp: s, datum: 'caxis:Z'}, b: {comp: b, datum: 'caxis:Z'}, value: 0},
                   {id: 'r2', type: 'distance', a: {comp: s, datum: 'plane:XY'}, b: {comp: b, datum: 'plane:XY'}, value: 60},
                   {id: 'r3', type: 'concentric', a: {comp: h, datum: 'caxis:Z'}, b: {comp: s, datum: 'caxis:Z'}, value: 0},
                   {id: 'r4', type: 'distance', a: {comp: h, datum: 'plane:XY'}, b: {comp: s, datum: 'plane:XY'}, value: 30},
                   {id: 'r5', type: 'parallel', a: {comp: h, datum: 'plane:YZ'}, b: {comp: s, datum: 'plane:YZ'}, value: 0}]; }""", [base, spin, hand])
    page.click("#as-solve")
    wait_text(page, "#status-text", "Mates solved")
    page.click("#as-check")
    wait_text(page, "#as-mates", "1 degree of freedom in all")
    time.sleep(1.5)                                   # the build after the check
    rot = lambda i: asm_state(page, "AS.asm.components.find(c => c.id === '%s').rot.slice()" % i)
    s0 = rot(spin)
    page.click("#as-rotate")
    xy = page.evaluate("""([cid]) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const m = t.pickables.find(o => o.userData.id === cid), b = new T.Box3().setFromObject(m);
        const r = t.renderer.domElement.getBoundingClientRect();
        for (let i = 0; i < 1200; i++) {
          const z = [b.max.z, b.min.z, (b.min.z + b.max.z) / 2][Math.floor(i / 400)];
          const q = new T.Vector3(b.min.x + (b.max.x - b.min.x) * ((i % 20) + 0.5) / 20, b.min.y + (b.max.y - b.min.y) * (Math.floor((i % 400) / 20) + 0.5) / 20, z).project(t.camera);
          const rc = new T.Raycaster(); rc.setFromCamera(new T.Vector2(q.x, q.y), t.camera);
          const h = rc.intersectObjects(t.pickables, false);
          const sx = r.left + (q.x + 1) / 2 * r.width, sy = r.top + (1 - q.y) / 2 * r.height;
          if (h.length && h[0].object.userData.id === cid && document.elementFromPoint(sx, sy) === t.renderer.domElement) return [sx, sy];
        }
        return null; }""", [hand])
    assert xy
    page.mouse.move(*xy)
    page.mouse.down()
    page.mouse.move(xy[0] + 80, xy[1], steps=6)
    page.mouse.up()
    wait_text(page, "#status-text", "with 1 mated component")
    page.click("#as-rotate")
    s1 = rot(spin)
    from drawgen import assembly as A
    R0, R1 = A._rot_matrix(s0), A._rot_matrix(s1)
    # SPINDLE turned about Z only: the Z column is unchanged, the X column turned by more than 1 deg
    assert all(abs(R1[i][2] - R0[i][2]) < 1e-4 for i in range(3))
    assert sum(R1[i][0] * R0[i][0] for i in range(3)) < math.cos(math.radians(1))
    # Isolate: with mate r1 selected only BASE and SPINDLE are pickable
    page.click("#as-mates-btn") if not page.is_visible("#as-matewin") else None
    page.click("#as-mates .as-comp[data-mid=r1]")
    page.check("#as-isolate")
    page.wait_for_function("(ids) => { const p = window.__asm.AS.three.pickables.map(o => o.userData.id); return p.length === 2 && ids.every(i => p.includes(i)); }", arg=[base, spin])
    page.uncheck("#as-isolate")


def test_drag_mated_component_keeps_mates(page, client):
    """A component mated plane to plane (XY on XY) is dragged only in the plane: z stays, x or y change; the first
    component of the group keeps its place when the mate is solved."""
    client.put("/api/part/file/ui_dm", json=plate("ui_dm"))
    tab(page, "asm")
    add_part(page, "ui_dm")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_dm")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    n = asm_state(page, "AS.asm.components.length")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    page.evaluate("([a]) => { const c = window.__asm.AS.asm.components.find(x => x.id === a); c.pos = [c.pos[0], c.pos[1], 15]; }", [ids[n - 1]])
    first = asm_state(page, "AS.asm.components.find(c => c.id === '%s').pos.slice()" % ids[n - 2])
    page.click("#as-tb-mates button[data-mate=coincident]")
    page.keyboard.press("Escape")
    for side, cid in (("a", ids[n - 1]), ("b", ids[n - 2])):
        page.select_option("#am-c" + side, cid)
        page.select_option("#am-d" + side, "plane:XY")
    page.wait_for_function("(() => { const m = window.__asm.AS.asm.mates.slice(-1)[0]; return m.a && m.b; })()")
    wait_text(page, "#status-text", "Mates solved")
    assert asm_state(page, "AS.asm.components.find(c => c.id === '%s').pos.slice()" % ids[n - 2]) == first
    z0 = asm_state(page, "AS.asm.components.find(c => c.id === '%s').pos.slice()" % ids[n - 1])
    page.keyboard.press("d")
    xy = page.evaluate("""([cid]) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const m = t.pickables.find(o => o.userData.id === cid);
        const b = new T.Box3().setFromObject(m), p = b.getCenter(new T.Vector3()).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""", [ids[n - 1]])
    page.mouse.move(*xy)
    page.mouse.down()
    page.mouse.move(xy[0] + 60, xy[1] - 40, steps=5)
    page.mouse.up()
    wait_text(page, "#status-text", " moved ")
    page.keyboard.press("d")
    z1 = asm_state(page, "AS.asm.components.find(c => c.id === '%s').pos.slice()" % ids[n - 1])
    f1 = asm_state(page, "AS.asm.components.find(c => c.id === '%s').pos.slice()" % ids[n - 2])
    # no fixed component: the in-plane movement moves the component alone, the movement normal to the mated planes
    # moves both (the mate stays satisfied and the pair is not held in space)
    assert z1[:2] != z0[:2]
    assert abs((z1[2] - f1[2]) - (z0[2] - first[2])) < 1e-4 and all(abs(f1[k] - first[k]) < 1e-4 for k in range(2))
    # with the first component fixed, the dragged component stays in its plane
    page.evaluate("(id) => { window.__asm.AS.asm.components.find(c => c.id === id).fixed = true; }", ids[n - 2])
    page.keyboard.press("d")
    page.mouse.move(*xy)
    page.mouse.down()
    page.mouse.move(xy[0] - 50, xy[1] + 30, steps=5)
    page.mouse.up()
    wait_text(page, "#status-text", " moved ")
    page.keyboard.press("d")
    z2 = asm_state(page, "AS.asm.components.find(c => c.id === '%s').pos.slice()" % ids[n - 1])
    assert z2[:2] != z1[:2] and abs(z2[2] - z1[2]) < 1e-4
    assert asm_state(page, "AS.asm.components.find(c => c.id === '%s').pos.slice()" % ids[n - 2]) == f1


def test_assembly_space_hides_component(page, client):
    """Space over a component hides it; Shift+Space shows all components again."""
    client.put("/api/part/file/ui_sp", json=plate("ui_sp"))
    tab(page, "asm")
    add_part(page, "ui_sp")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    cid = asm_state(page, "AS.asm.components.slice(-1)[0].id")
    page.wait_for_function("([cid]) => window.__asm.AS.three.pickables.some(o => o.userData.id === cid)", arg=[cid])
    xy = page.evaluate("""([cid]) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const m = t.pickables.find(o => o.userData.id === cid);
        const b = new T.Box3().setFromObject(m), p = b.getCenter(new T.Vector3()).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""", [cid])
    page.mouse.move(*xy)
    page.mouse.move(xy[0] + 1, xy[1] + 1)
    page.keyboard.press("Space")
    assert asm_state(page, "AS.asm.components.find(c => c.id === '%s').visible" % cid) is False
    page.keyboard.press("Shift+Space")
    assert asm_state(page, "AS.asm.components.every(c => c.visible !== false)") is True


def test_drag_on_held_component_keeps_view(page, client):
    """Drag mode: a drag on a fixed component does not move it and does not rotate the view."""
    client.put("/api/part/file/ui_hv", json=plate("ui_hv"))
    tab(page, "asm")
    add_part(page, "ui_hv")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    cid = asm_state(page, "AS.asm.components.slice(-1)[0].id")
    page.evaluate("([cid]) => { window.__asm.AS.asm.components.find(c => c.id === cid).fixed = true; }", [cid])
    page.wait_for_function("([cid]) => window.__asm.AS.three.pickables.some(o => o.userData.id === cid)", arg=[cid])
    cam = "() => { const t = window.__asm.AS.three; return [t.camera.position.toArray(), t.camera.quaternion.toArray()]; }"
    page.keyboard.press("d")
    c0, p0 = page.evaluate(cam), asm_state(page, "AS.asm.components.slice(-1)[0].pos.slice()")
    xy = page.evaluate("""([cid]) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const m = t.pickables.find(o => o.userData.id === cid);
        const b = new T.Box3().setFromObject(m), p = b.getCenter(new T.Vector3()).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""", [cid])
    page.mouse.move(*xy)
    page.mouse.down()
    page.mouse.move(xy[0] + 60, xy[1] - 40, steps=5)
    page.mouse.up()
    page.keyboard.press("d")
    page.wait_for_timeout(500)
    assert page.evaluate(cam) == c0
    assert asm_state(page, "AS.asm.components.slice(-1)[0].pos.slice()") == p0


def test_drag_held_directions_tolerance(page):
    """Held directions within about 3 deg count once: two plane mates with normals 1 deg apart leave the plane free."""
    tab(page, "asm")
    n = page.evaluate("""() => { const T = window.__asm.THREE, a = 1 * Math.PI / 180;
        return [window.__asm.orthoBasis([new T.Vector3(0, 0, 1), new T.Vector3(Math.sin(a), 0, Math.cos(a))]).length,
                window.__asm.orthoBasis([new T.Vector3(0, 0, 1), new T.Vector3(1, 0, 0)]).length]; }""")
    assert n == [1, 2]


def test_add_mate_with_long_list(page, client):
    """A mate type button in an assembly with incomplete mates: the new mate is selected, picking starts, its sides are in view
    and the status bar says what to click."""
    client.put("/api/part/file/ui_am", json=plate("ui_am"))
    comps = [{"id": "c%d" % i, "name": "P%d" % i, "source": {"type": "part", "name": "ui_am"}, "pos": [120 * i, 0, 0], "rot": [0, 0, 0],
              "visible": True, "fixed": i == 0, "explode": [0, 0, 0]} for i in range(3)]
    mates = [{"id": "m%d" % k, "type": "coincident", "a": {"comp": "c1", "datum": "plane:XY"}, "b": {"comp": "c0", "datum": "plane:XY"}} for k in range(20)]
    mates += [{"id": "m40", "type": "coincident", "a": None, "b": None}, {"id": "m41", "type": "coincident", "a": {"comp": "c2", "datum": "plane:XY"}, "b": None}]
    client.put("/api/assembly/file/ui_amasm", json={"name": "ui_amasm", "components": comps, "mates": mates, "next": 97})
    tab(page, "asm")
    page.evaluate("window.__asmLoadNamed('ui_amasm')")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length === 3")
    page.click("#as-tb-mates button[data-mate=coincident]")
    page.wait_for_function("window.__asm.AS.selMate === 'm97' && window.__asm.AS.matePick && window.__asm.AS.matePick.side === 'a'")
    wait_text(page, "#status-text", "click a face of the first component")
    assert page.evaluate("""() => { const el = document.querySelector('#as-mates .as-mateprops'), r = el.getBoundingClientRect();
        return r.top < window.innerHeight && r.bottom > 0; }""")
    page.keyboard.press("Escape")
    page.click("#as-tb-mates button[data-mate=concentric]")
    page.wait_for_function("window.__asm.AS.selMate === 'm98' && window.__asm.AS.asm.mates.slice(-1)[0].type === 'concentric'")
    wait_text(page, "#status-text", "Concentric mate")
    assert page.input_value("#am-type") == "concentric"
    assert page.locator("#tab-asm .toolbar button.ico-btn svg.tb-ico").count() >= 14


def test_assembly_rotate_section_mates_window(page, client):
    """Rotate mode: a component mated XY to XY turns about Z only. Section: all materials clipped by one plane that
    follows the slider. The mates window opens with a mate type button and closes with ×; the mass section is collapsed."""
    client.put("/api/part/file/ui_rot", json=plate("ui_rot"))
    tab(page, "asm")
    add_part(page, "ui_rot")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_rot")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    n = asm_state(page, "AS.asm.components.length")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    assert page.is_hidden("#as-mass") and page.is_hidden("#as-matewin")
    page.click("#as-tb-mates button[data-mate=coincident]")
    assert page.is_visible("#as-matewin")
    page.keyboard.press("Escape")
    for side, cid in (("a", ids[n - 1]), ("b", ids[n - 2])):
        page.select_option("#am-c" + side, cid)
        page.select_option("#am-d" + side, "plane:XY")
    wait_text(page, "#status-text", "Mates solved")
    page.click("#as-matewin-close")
    assert page.is_hidden("#as-matewin")
    page.keyboard.press("r")
    page.wait_for_function("window.__asm.AS.dragMode === 'rotate'")
    z0 = asm_state(page, "AS.asm.components[%d].pos[2]" % (n - 1))
    rot0 = asm_state(page, "AS.asm.components[%d].rot.slice()" % (n - 1))
    xy = page.evaluate("""([cid]) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const m = t.pickables.find(o => o.userData.id === cid);
        const b = new T.Box3().setFromObject(m), p = b.getCenter(new T.Vector3()).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""", [ids[n - 1]])
    page.mouse.move(*xy)
    page.mouse.down()
    page.mouse.move(xy[0] + 90, xy[1], steps=6)
    page.mouse.up()
    page.keyboard.press("r")
    rot = asm_state(page, "AS.asm.components[%d].rot.slice()" % (n - 1))
    import numpy as np

    def R(r):                                   # rotations about the fixed X, then Y, then Z axis (deg)
        a, b, c = np.radians(r)
        rx = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
        ry = np.array([[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]])
        rz = np.array([[np.cos(c), -np.sin(c), 0], [np.sin(c), np.cos(c), 0], [0, 0, 1]])
        return rz @ ry @ rx
    d = R(rot) @ R(rot0).T                      # the rotation made by the drag: about Z by 45 deg
    assert abs(d[2, 2] - 1) < 1e-6 and abs(abs(np.degrees(np.arctan2(d[1, 0], d[0, 0]))) - 45) < 1e-3
    assert abs(asm_state(page, "AS.asm.components[%d].pos[2]" % (n - 1)) - z0) < 1e-6
    # section
    page.check("#as-sec")
    page.wait_for_function("window.__asm.AS.three.clipMats.length > 0 && window.__asm.AS.three.clipMats.every(m => (m.clippingPlanes || []).length === 1)")
    c0 = page.evaluate("window.__asm.AS.three.clipPlane.constant")
    page.fill("#as-sec-pos", "200")
    page.dispatch_event("#as-sec-pos", "input")
    assert page.evaluate("window.__asm.AS.three.clipPlane.constant") != c0
    if os.environ.get("DRAWGEN_SHOTS"):
        page.click("#as-mates-btn")
        page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "asm_section.png"))
        page.click("#as-mates-btn")
    page.uncheck("#as-sec")
    page.wait_for_function("window.__asm.AS.three.clipMats.every(m => !(m.clippingPlanes || []).length)")


def test_context_menu_suppressed(page, client):
    """The browser menu is not opened on the 3D views or on the program's own menus (on Windows the contextmenu event
    arrives after the program menu is open under the cursor)."""
    tab(page, "asm")
    res = page.evaluate("""() => {
        const m = document.createElement('div'); m.className = 'sk-menu'; document.body.appendChild(m);
        const out = [];
        for (const el of [m, document.querySelector('#as-view canvas'), document.querySelector('#tab-asm .toolbar button')]) {
          const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true }); el.dispatchEvent(ev); out.push(ev.defaultPrevented);
        }
        m.remove(); return out; }""")
    assert res == [True, True, False]


def test_mate_default_direction(page, client):
    """A concentric mate on reference axes takes the direction the components have: SECOND turned 180 deg about X
    (axis Z reversed) gives Flip off (facing); turned back, Flip on. Planar faces keep facing."""
    client.put("/api/part/file/ui_dir", json=plate("ui_dir"))
    tab(page, "asm")
    add_part(page, "ui_dir")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_dir")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    n = asm_state(page, "AS.asm.components.length")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    a, b = ids[n - 1], ids[n - 2]
    for rx, flip in ((180, False), (0, True)):
        page.evaluate("([a, b, rx]) => { const A = window.__asm.AS.asm; A.mates = []; A.components.forEach(c => { c.fixed = c.id === b; });"
                      " A.components.find(c => c.id === a).rot = [rx, 0, 0]; A.components.find(c => c.id === b).rot = [0, 0, 0]; }", [a, b, rx])
        page.click("#as-tb-mates button[data-mate=concentric]")
        page.keyboard.press("Escape")
        page.select_option("#am-ca", a); page.select_option("#am-da", "caxis:Z")
        page.select_option("#am-cb", b); page.select_option("#am-db", "caxis:Z")
        page.wait_for_function("(() => { const m = window.__asm.AS.asm.mates.slice(-1)[0]; return m.a && m.b; })()")
        assert asm_state(page, "AS.asm.mates.slice(-1)[0].flip") is flip
        wait_text(page, "#status-text", "Mates solved")


def test_assembly_measure(page, client):
    """Measure: two faces picked in the 3D view give the rows (minimum distance first) and the line between the
    closest points; Esc ends."""
    client.put("/api/part/file/ui_ms", json=plate("ui_ms"))
    tab(page, "asm")
    add_part(page, "ui_ms")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_ms")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    n = asm_state(page, "AS.asm.components.length")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    page.evaluate("([a, b]) => { const A = window.__asm.AS.asm; A.mates = []; A.components.forEach(c => { c.rot = [0, 0, 0]; });"
                  " A.components.find(c => c.id === a).pos = [0, 0, 0]; A.components.find(c => c.id === b).pos = [150, 0, 0]; }", [ids[n - 2], ids[n - 1]])
    page.evaluate("() => { const AS = window.__asm.AS; window.__asm.setMeshes(AS.result); }")
    page.click("#as-measure-btn")
    assert page.is_visible("#as-measure")
    for cid in (ids[n - 2], ids[n - 1]):
        xy = page.evaluate("""([cid]) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
            const m = t.pickables.find(o => o.userData.id === cid), b = new T.Box3().setFromObject(m);
            const r = t.renderer.domElement.getBoundingClientRect();
            for (let i = 0; i < 400; i++) {
              const q = new T.Vector3(b.min.x + (b.max.x - b.min.x) * ((i % 20) + 0.5) / 20, b.min.y + (b.max.y - b.min.y) * (Math.floor(i / 20) + 0.5) / 20, b.max.z).project(t.camera);
              const rc = new T.Raycaster(); rc.setFromCamera(new T.Vector2(q.x, q.y), t.camera);
              const h = rc.intersectObjects(t.pickables, false);
              const sx = r.left + (q.x + 1) / 2 * r.width, sy = r.top + (1 - q.y) / 2 * r.height;
              if (h.length && h[0].object.userData.id === cid && document.elementFromPoint(sx, sy) === t.renderer.domElement) return [sx, sy];
            }
            return null; }""", [cid])
        assert xy
        page.mouse.click(*xy)
        page.wait_for_function("(k) => window.__asm.AS.measure.res && window.__asm.AS.measure.items.length === k", arg=1 if cid == ids[n - 2] else 2)
    wait_text(page, "#as-measure-body", "Minimum distance")
    assert page.evaluate("window.__asm.AS.measure.res.points.length") == 2
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "asm_measure.png"))
    page.mouse.move(5, 300)
    page.keyboard.press("Escape")
    assert not page.is_visible("#as-measure")


def test_part_measure(page, client):
    """Part Measure: a face clicked in the view, then the reference plane XY: distance and minimum distance; Esc
    ends."""
    client.put("/api/part/file/ui_pm", json=plate("ui_pm"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_pm')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    page.click("#pt-measure-btn")
    assert page.is_visible("#pt-measure")
    page.click("#tab-part [data-view=top]")
    time.sleep(0.3)
    xy = page.evaluate("""() => { const PT = window.__part.PT, t = PT.three;
        const r = t.renderer.domElement.getBoundingClientRect();
        for (let i = 0; i < 400; i++) {
          const sx = r.left + r.width * (0.1 + 0.8 * (i % 20) / 20), sy = r.top + r.height * (0.1 + 0.8 * Math.floor(i / 20) / 20);
          const h = window.__part.pickAt({ clientX: sx, clientY: sy }, ["face"]);
          if (h && h.kind === "face" && PT.mesh.face_keys[h.fi] && document.elementFromPoint(sx, sy) === t.renderer.domElement) {
            const n = window.__part.PT.mesh; return [sx, sy];
          }
        }
        return null; }""")
    assert xy
    page.mouse.click(*xy)
    page.wait_for_function("window.__part.PT.measure.res && window.__part.PT.measure.items.length === 1")
    page.evaluate("window.__part.measureClick({ kind: 'plane', id: 'XY' })")
    page.wait_for_function("window.__part.PT.measure.res && window.__part.PT.measure.items.length === 2")
    wait_text(page, "#pt-measure-body", "Distance between the planes")
    wait_text(page, "#pt-measure-body", "20.0000 mm")
    page.mouse.move(5, 300)
    page.keyboard.press("Escape")
    assert not page.is_visible("#pt-measure")


def test_assembly_show_all_and_invert(page, client):
    """Invert shows the hidden components and hides the shown ones (button and Ctrl+Space); Show all shows all."""
    client.put("/api/part/file/ui_inv", json=plate("ui_inv"))
    tab(page, "asm")
    add_part(page, "ui_inv")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_inv")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    page.evaluate("(id) => { window.__asm.AS.asm.components.forEach(c => { c.visible = c.id !== id; }); }", ids[-1])
    vis = lambda: asm_state(page, "AS.asm.components.map(c => c.visible !== false)")
    page.click("#as-invert")
    assert vis() == [False] * (len(ids) - 1) + [True]
    page.mouse.move(5, 300)
    page.keyboard.press("Control+Space")
    assert vis() == [True] * (len(ids) - 1) + [False]
    page.click("#as-showall")
    assert vis() == [True] * len(ids)


def test_assembly_menu_isolate_connected(page, client):
    """Component menu: show only the component and its mated components, or the connected chain (not continued
    through the fixed component)."""
    client.put("/api/part/file/ui_iso", json=plate("ui_iso"))
    tab(page, "asm")
    for _ in range(4):
        add_part(page, "ui_iso")
        time.sleep(0.3)
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 4")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    f, a, b, x = ids[-4], ids[-3], ids[-2], ids[-1]
    # F fixed; A-F, A-B mated; X mated to F only
    page.evaluate("""([f, a, b, x]) => { const A = window.__asm.AS.asm; A.components.forEach(c => { c.fixed = c.id === f; c.visible = true; });
        const mt = (id, p, q) => ({ id, type: 'parallel', a: { comp: p, datum: 'plane:XY' }, b: { comp: q, datum: 'plane:XY' }, value: 0 });
        A.mates = [mt('i1', a, f), mt('i2', b, a), mt('i3', x, f)]; }""", [f, a, b, x])
    shown = lambda: sorted(asm_state(page, "AS.asm.components.filter(c => c.visible !== false).map(c => c.id)"))
    page.evaluate("(id) => window.__asm.isolateComps(id, false)", b)
    assert shown() == sorted([a, b])
    page.evaluate("(id) => window.__asm.isolateComps(id, true)", b)
    assert shown() == sorted([f, a, b])
    page.click("#as-showall")
    assert len(shown()) == len(ids)


def test_assembly_box_select(page, client):
    """Box select: left to right selects the components entirely inside, right to left those touched; Ctrl+click
    adds one; Space hides the selection; the component menu offers the selection actions."""
    client.put("/api/part/file/ui_box", json=plate("ui_box"))
    tab(page, "asm")
    for _ in range(3):
        add_part(page, "ui_box")
        time.sleep(0.3)
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 3")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    a, b, c = ids[-3], ids[-2], ids[-1]
    page.evaluate("""([a, b, c]) => { const AS = window.__asm.AS; AS.asm.mates = [];
        AS.asm.components.forEach(x => { x.visible = [a, b, c].includes(x.id); x.rot = [0, 0, 0]; });
        AS.asm.components.find(x => x.id === a).pos = [0, 0, 0]; AS.asm.components.find(x => x.id === b).pos = [150, 0, 0];
        AS.asm.components.find(x => x.id === c).pos = [300, 0, 0]; window.__asm.setMeshes(AS.result); }""", [a, b, c])
    page.click("#tab-asm [data-asview=top]")
    page.click("#tab-asm [data-asview=fit]")
    time.sleep(0.5)
    rect = lambda cid: page.evaluate("""(cid) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const m = t.pickables.find(o => o.userData.id === cid), b = new T.Box3().setFromObject(m), r = t.renderer.domElement.getBoundingClientRect();
        const ps = [[b.min.x, b.min.y, b.max.z], [b.max.x, b.max.y, b.max.z]].map(p => new T.Vector3(...p).project(t.camera)).map(v => [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]);
        return [Math.min(ps[0][0], ps[1][0]), Math.min(ps[0][1], ps[1][1]), Math.max(ps[0][0], ps[1][0]), Math.max(ps[0][1], ps[1][1])]; }""", cid)
    ra, rb = rect(a), rect(b)
    sel = lambda: sorted(asm_state(page, "[...(AS.multi || new Set(AS.sel ? [AS.sel] : []))]"))
    # left to right around A and B (entirely inside): A and B
    page.click("#as-box")
    page.mouse.move(ra[0] - 10, min(ra[1], rb[1]) - 10)
    page.mouse.down()
    page.mouse.move(rb[2] + 10, max(ra[3], rb[3]) + 10, steps=6)
    page.mouse.up()
    assert sel() == sorted([a, b])
    # right to left over half of B only: B (touched)
    page.mouse.move((rb[0] + rb[2]) / 2, rb[1] - 10)
    page.mouse.down()
    page.mouse.move(rb[0] - 5, rb[3] + 10, steps=6)
    page.mouse.up()
    assert sel() == [b]
    page.click("#as-box")
    # Ctrl+click adds C
    rc = rect(c)
    page.keyboard.down("Control")
    page.mouse.click((rc[0] + rc[2]) / 2 + 30, (rc[1] + rc[3]) / 2)
    page.keyboard.up("Control")
    assert sel() == sorted([b, c])
    page.mouse.move(5, 300)
    page.keyboard.press("Space")
    vis = asm_state(page, "AS.asm.components.filter(c => c.visible !== false).map(c => c.id)")
    assert vis == [a]


def test_drawing_angle_dimension(page, client):
    """Angle tool: a horizontal and a vertical edge of the front view give a 90 deg angle dimension."""
    client.put("/api/part/file/ui_ang", json=plate("ui_ang"))
    tab(page, "part")
    file_menu(page, "#tab-part")
    page.select_option("#pt-list", "ui_ang")
    wait_text(page, "#pt-info", "Volume")
    file_menu(page, "#tab-part")
    page.click("#pt-draw")
    page.wait_for_selector("#ann-canvas svg", timeout=120000)
    page.wait_for_function("typeof ED !== 'undefined' && ED.d && ED.d.maps && ED.lines.length")
    assert page.is_visible("#ann-tools button[data-tool=angle]")
    n0 = page.evaluate("ED.anns.length")
    page.evaluate("""() => { setTool('angle'); const L = ED.lines.filter(l => l.view === 'front');
        const h = L.find(l => Math.abs(l.A[1] - l.B[1]) < 1e-6), v = L.find(l => Math.abs(l.A[0] - l.B[0]) < 1e-6);
        const mid = l => [(l.A[0] + l.B[0]) / 2, (l.A[1] + l.B[1]) / 2];
        toolClick(...mid(h)); toolClick(...mid(v));
        const an = angleFromLines(h, v), C = toSheet('front', an.c[0], an.c[1]);
        const m = [(mid(h)[0] + mid(v)[0]) / 2, (mid(h)[1] + mid(v)[1]) / 2];
        toolClick(C[0] + (m[0] - C[0]) * 0.5, C[1] + (m[1] - C[1]) * 0.5); setTool('select'); }""")
    page.wait_for_function("(n) => ED.anns.length === n + 1 && ED.anns[n].type === 'angle'", arg=n0)
    assert abs(page.evaluate("measured(ED.anns[ED.anns.length - 1])") - 90) < 1e-6
    page.wait_for_function("[...document.querySelectorAll('g.ann')].some(g => g.textContent.includes('90°'))", timeout=60000)


def test_assembly_colour_updates(page, client):
    """The colour field changes the material at once (input) and the list swatch; with two components selected both
    get the colour; a selected component keeps its own colour."""
    client.put("/api/part/file/ui_col", json=plate("ui_col"))
    tab(page, "asm")
    add_part(page, "ui_col")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_col")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2")
    ids = asm_state(page, "AS.asm.components.map(c => c.id)")
    a, b = ids[-2], ids[-1]
    page.click("#as-comps .as-comp[data-id='%s'] .nm" % a)
    mat = lambda cid: page.evaluate("(cid) => '#' + window.__asm.AS.three.pickables.find(o => o.userData.id === cid).material.color.getHexString()", cid)
    page.evaluate("() => { const el = document.getElementById('ac-color'); el.value = '#12ab34'; el.dispatchEvent(new Event('input')); }")
    assert mat(a) == "#12ab34"
    assert "18, 171, 52" in page.get_attribute("#as-comps .as-comp[data-id='%s'] .sw" % a, "style")
    page.evaluate("() => { const el = document.getElementById('ac-color'); el.dispatchEvent(new Event('change')); }")
    assert asm_state(page, "AS.asm.components.find(c => c.id === '%s').color" % a) == "#12ab34"
    page.keyboard.down("Control")
    page.click("#as-comps .as-comp[data-id='%s'] .nm" % b)
    page.keyboard.up("Control")
    page.evaluate("() => { const el = document.getElementById('ac-color'); el.value = '#aa2200'; el.dispatchEvent(new Event('input')); el.dispatchEvent(new Event('change')); }")
    assert mat(a) == "#aa2200" and mat(b) == "#aa2200"


def test_part_place_command(page, client):
    """Place: the clicks pick face 1, then face 2 (the part before Place is shown); Finish moves the part so that the
    picked faces lie on XY and XZ."""
    client.put("/api/part/file/ui_place", json=plate("ui_place"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_place')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    page.click("#tab-part [data-add=place]")
    page.wait_for_function("window.__part.PT.cmd && window.__part.PT.cmd.legacyDefs")
    page.click("#tab-part [data-view=iso]")
    time.sleep(0.4)
    # click the top face (normal +Z), then a side face
    def click_face(nz, ny):
        xy = page.evaluate("""([nz, ny]) => { const P = window.__part, PT = P.PT, t = PT.three, r = t.renderer.domElement.getBoundingClientRect();
            for (let i = 0; i < 1600; i++) {
              const sx = r.left + r.width * (0.05 + 0.9 * (i % 40) / 40), sy = r.top + r.height * (0.05 + 0.9 * Math.floor(i / 40) / 40);
              const h = P.pickAt({ clientX: sx, clientY: sy }, ["face"]);
              if (!h || h.kind !== 'face') continue;
              const k = PT.mesh.face_keys[h.fi]; if (!k || !k.n) continue;
              if (Math.abs(k.n[2] - nz) < 1e-6 && Math.abs(k.n[1] - ny) < 1e-6 && document.elementFromPoint(sx, sy) === t.renderer.domElement) return [sx, sy];
            }
            return null; }""", [nz, ny])
        assert xy, (nz, ny)
        page.mouse.click(*xy)
    click_face(1, 0)
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).face1")
    time.sleep(0.5)
    click_face(0, -1)
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).face2")
    page.click("#pt-cmdfinish")
    page.wait_for_function("window.__part.PT.mesh && !window.__part.PT.cmd")
    page.wait_for_function("(() => { const b = window.__part.PT.mesh.bbox; return Math.abs(b[2]) < 1e-6 && Math.abs(b[1]) < 1e-6; })()", timeout=60000)


def test_part_plane_normal_to_sketch_curve(page, client):
    """Plane, method Normal to an edge or curve: a click near the end of a sketched curve puts the plane at that
    end of the chain of sketch curves, normal to the curve."""
    p = plate("ui_skc")
    p["features"].append({"id": "skc", "name": "Path", "type": "sketch", "plane": "XY", "offset": 30, "sketch": {"layers": [{"name": "0", "on": True}],
        "entities": [{"id": 1, "t": "line", "x1": 0, "y1": 0, "x2": 60, "y2": 0, "layer": "0"},
                     {"id": 2, "t": "line", "x1": 60, "y1": 0, "x2": 60, "y2": 40, "layer": "0"}]}})
    client.put("/api/part/file/ui_skc", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_skc')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length && window.__part.PT.sketchObjs.length")
    page.click("#tab-part [data-view=iso]")
    page.click("#tab-part [data-add=plane]")
    page.wait_for_function("window.__part.PT.cmd")
    page.evaluate("window.__part.gotoStep(0)")                     # the command opens at Offset (Method has a default)
    page.select_option("#pf-method", "edge")
    page.wait_for_selector("#cmd-next")
    page.click("#cmd-next")
    page.wait_for_function("document.querySelector('#pt-props .cmd-step.active .lbl').textContent === 'Edge or curve'")
    time.sleep(0.4)
    xy = page.evaluate("""() => { const P = window.__part, PT = P.PT, t = PT.three, T = window.__part.THREE || Object.getPrototypeOf(t.camera.position).constructor;
        const r = t.renderer.domElement.getBoundingClientRect();
        const v = t.camera.position.clone().set(60, 37, 30).project(t.camera);
        const sx = r.left + (v.x + 1) / 2 * r.width, sy = r.top + (1 - v.y) / 2 * r.height;
        const h = P.pickAt({ clientX: sx, clientY: sy }, ["edge", "curve", "sketch"]);
        return h && h.kind === 'sketch' ? [sx, sy] : null; }""")
    assert xy
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.sketch_curve && f.sketch_curve.sketch === 'skc'; })()")
    page.click("#cmd-finish")
    page.wait_for_function("!window.__part.PT.cmd")
    page.wait_for_function("""(() => { const PT = window.__part.PT; const f = PT.part.features.find(x => x.type === 'plane');
        const st = f && PT.status[f.id]; return st && st.frame && Math.abs(st.frame.o[0] - 60) < 1e-6 && Math.abs(st.frame.o[1] - 40) < 1e-6
          && Math.abs(st.frame.o[2] - 30) < 1e-6 && Math.abs(Math.abs(st.frame.z[1]) - 1) < 1e-6; })()""", timeout=60000)


def test_analysis_mesh_settings_and_displacement_support(page, client):
    """Analysis Settings: mesh strategy hexahedra by subdivision with C3D8I; Mesh gives hexahedra. A support set to
    prescribed displacement shows the component fields and stores the value."""
    from test_analysis import _two_plate_doc
    doc = _two_plate_doc(client, "fea_mesh_ui")
    doc["mesh"] = {"size": 10}
    client.put("/api/analysis/file/fea_mesh_ui", json=doc)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("window.__feaLoadNamed('fea_mesh_ui')")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    page.select_option("#fs-strategy", "hexsub")
    page.select_option("#fs-hextype", "C3D8I")
    assert page.evaluate("window.__fea.FA.doc.mesh.strategy") == "hexsub"
    page.click("#fa-mesh")
    page.wait_for_function("window.__fea.FA.mesh && window.__fea.FA.mesh._summary", timeout=300000)
    types = page.evaluate("window.__fea.FA.mesh._summary.bodies.map(b => b.types)")
    assert all(t == ["C3D8I"] for t in types), types
    wait_text(page, "#status-text", "C3D8I")
    page.click("#fa-sups .fa-item")
    page.select_option("#fsp-type", "displacement")
    page.wait_for_selector("#fa-sups [data-dval='2']")
    page.fill("#fa-sups [data-dval='2']", "0.05")
    page.dispatch_event("#fa-sups [data-dval='2']", "change")
    s = page.evaluate("window.__fea.FA.doc.supports[0]")
    assert s["type"] == "displacement" and s["value"][2] == 0.05 and s["dofs"][:3] == [1, 1, 1]


def test_analysis_members_table_groups_and_beam_results(page, client):
    """Members table with group selects; Add group from the selected member; a group section change goes to its
    members; the results colour the members (tubes with the von Mises colours); the panel bar changes the panel
    width."""
    from test_analysis import CCX, STEEL
    if CCX is None:
        pytest.skip("CalculiX (ccx) not found")
    doc = {"name": "fea_grp", "source": {"type": "assembly", "name": ""}, "materials": STEEL, "default_material": "Steel",
           "members": [{"id": "m1", "name": "B1", "kind": "beam", "a": {"xyz": [0, 0, 0]}, "b": {"xyz": [500, 0, 0]},
                        "section": {"shape": "ROUND", "d": 20}, "up": [0, 0, 1]},
                       {"id": "m2", "name": "B2", "kind": "beam", "a": {"xyz": [500, 0, 0]}, "b": {"xyz": [500, 300, 0]},
                        "section": {"shape": "ROUND", "d": 20}, "up": [0, 0, 1]}],
           "supports": [{"id": "s1", "name": "root", "target": {"member": "m1", "end": "a"}, "type": "fixed"}],
           "loads": [{"id": "l1", "name": "P", "type": "force", "target": {"member": "m2", "end": "b"}, "value": [0, 0, -100]}],
           "plates": [], "fasteners": [], "bodies": {}}
    client.put("/api/analysis/file/fea_grp", json=doc)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("window.__feaLoadNamed('fea_grp')")
    page.wait_for_selector("#fa-mgrid td[data-r]")
    assert page.locator("#fa-mgrid tr").count() == 3
    page.click("#fa-mgrid td[data-r='0'][data-c='1']")
    page.click("#fgr-add")
    page.wait_for_selector("#fa-members .fa-gtable tr.fa-grow")
    gname = page.evaluate("window.__fea.FA.doc.groups[0].name")
    page.click("#fa-mgrid td[data-r='1'][data-c='1']")
    page.keyboard.type(gname)
    page.keyboard.press("Enter")
    page.wait_for_function("window.__fea.FA.doc.members[1].group === window.__fea.FA.doc.groups[0].id")
    page.fill("#fa-members [data-gdim=d]", "30")
    page.dispatch_event("#fa-members [data-gdim=d]", "change")
    assert page.evaluate("window.__fea.FA.doc.members.map(m => m.section.d)") == [30, 30]
    w0 = page.evaluate("document.querySelector('#fa-panel').getBoundingClientRect().width")
    b = page.locator("#fa-split").bounding_box()
    page.mouse.move(b["x"] + 3, b["y"] + 100); page.mouse.down(); page.mouse.move(b["x"] - 97, b["y"] + 100); page.mouse.up()
    assert abs(page.evaluate("document.querySelector('#fa-panel').getBoundingClientRect().width") - (w0 + 100)) < 3
    page.click("#fa-solve")
    page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.tables", timeout=300000)
    page.select_option("#fa-field", "vm")
    cols = page.evaluate("""() => { const o = window.__fea.FA.three.group.children.find(c => c.userData && c.userData.kind === 'members');
        if (!o) return null; const c = o.geometry.getAttribute('color').array; let red = 0; for (let i = 0; i < c.length; i += 3) if (c[i] > 0.8 && c[i + 2] < 0.3) red++; return red; }""")
    assert cols and cols > 0


def test_analysis_beam_drawing_repeats_properties(page, client):
    """Beam: after end B the next beam starts with the section, group and up vector of the previous one; Esc ends
    the drawing and removes the beam started without ends."""
    doc = {"name": "fea_rep", "source": {"type": "assembly", "name": ""}, "materials": {"Steel": {"E": 210000, "nu": 0.3, "rho": 7850}},
           "default_material": "Steel", "members": [], "supports": [], "loads": [], "plates": [], "fasteners": [], "bodies": {},
           "groups": [{"id": "g1", "name": "Posts", "kind": "beam", "section": {"shape": "BOX", "b": 40, "h": 40, "t": 3}}]}
    client.put("/api/analysis/file/fea_rep", json=doc)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("window.__feaLoadNamed('fea_rep')")
    page.wait_for_function("window.__fea.FA.doc.name === 'fea_rep'")
    page.click("#fa-add-beam")
    page.evaluate("""() => { const F = window.__fea.FA, m = F.doc.members[0]; m.group = 'g1'; m.section = {shape: 'BOX', b: 40, h: 40, t: 3}; m.up = [1, 0, 0];
        F.pick.cb({xyz: [0, 0, 0]}); }""")
    page.wait_for_function("window.__fea.FA.pick && /end B/.test(window.__fea.FA.pick.text)")
    page.evaluate("window.__fea.FA.pick.cb({xyz: [0, 0, 1000]})")
    page.wait_for_function("window.__fea.FA.doc.members.length === 2 && window.__fea.FA.pick")
    m2 = page.evaluate("window.__fea.FA.doc.members[1]")
    assert m2["group"] == "g1" and m2["section"]["shape"] == "BOX" and m2["up"] == [1, 0, 0] and m2["a"] is None
    page.keyboard.press("Escape")
    page.wait_for_function("window.__fea.FA.doc.members.length === 1 && !window.__fea.FA.pick")


def test_analysis_reference_point(page, client):
    """Ref. point: the first picked face sets the point (face centre) and is connected; Esc ends the face picking.
    Support and Load with the reference point selected act on it; the support shows six components; the results
    list the reference point."""
    from test_analysis import CCX, _two_plate_doc
    if CCX is None:
        pytest.skip("CalculiX (ccx) not found")
    doc = _two_plate_doc(client, "fea_rp")
    doc["loads"] = []
    client.put("/api/analysis/file/fea_rp", json=doc)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("window.__feaLoadNamed('fea_rp')")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    page.click("#fa-add-rp")
    page.wait_for_function("window.__fea.FA.pick")
    top_face = page.evaluate("""() => { const F = window.__fea.FA; const c = F.geo.components.find(x => x.id === 'c2');
        let i = -1; c.refs.forEach((r, k) => { if (r && r.kind === 'plane' && r.n[2] > 0.9 && (i < 0 || r.c[2] > c.refs[i].c[2])) i = k; });
        return {comp: 'c2', face: i, c: c.refs[i].c}; }""")
    page.evaluate("(t) => window.__fea.FA.pick.cb({face: {comp: t.comp, face: t.face}, xyz: t.c, centre: t.c})", top_face)
    page.wait_for_function("window.__fea.FA.pick")
    page.keyboard.press("Escape")
    rp = page.evaluate("window.__fea.FA.doc.points[0]")
    assert rp["xyz"] == top_face["c"] and len(rp["faces"]) == 1
    page.click("#fa-add-load")
    page.wait_for_function("window.__fea.FA.doc.loads.length === 1")
    assert page.evaluate("window.__fea.FA.doc.loads[0].target") == {"point": rp["id"]}
    page.evaluate("() => { const l = window.__fea.FA.doc.loads[0]; l.type = 'moment'; l.value = [0, 0, 10000]; }")
    page.click("#fa-rps .fa-item")
    page.click("#fa-add-sup")
    page.wait_for_function("window.__fea.FA.doc.supports.length === 2")
    page.select_option("#fsp-type", "dofs")
    assert page.locator("#fa-sups .fa-dofs input").count() == 6
    page.evaluate("() => { const s = window.__fea.FA.doc.supports[1]; s.dofs = [0, 0, 0, 0, 0, 0]; s.type = 'dofs'; s.dofs[2] = 1; }")
    page.click("#fa-solve")
    page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.tables", timeout=300000)
    wait_text(page, "#fa-results", "Reference points")



def test_analysis_member_grid_fill_copy_paste(page, client):
    """Member grid: typing a new group name makes the group; the corner square drags the selected cells down
    (group to the rows below); paste of tab-separated text fills cells; a value not allowed is refused with a
    message; Delete clears the group."""
    from test_analysis import STEEL
    mem = lambda i: {"id": "m%d" % i, "name": "B%d" % i, "kind": "beam", "a": {"xyz": [0, 0, 100 * i]}, "b": {"xyz": [500, 0, 100 * i]},
                     "section": {"shape": "ROUND", "d": 20}, "up": [0, 0, 1]}
    doc = {"name": "fea_grid", "source": {"type": "assembly", "name": ""}, "materials": STEEL, "default_material": "Steel",
           "members": [mem(i) for i in range(1, 5)], "supports": [], "loads": [], "plates": [], "fasteners": [], "bodies": {}}
    client.put("/api/analysis/file/fea_grid", json=doc)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("window.__feaLoadNamed('fea_grid')")
    page.wait_for_selector("#fa-mgrid td[data-r='3']")
    # group "1" typed in row 1, then the fill square dragged to row 3
    page.click("#fa-mgrid td[data-r='0'][data-c='1']")
    page.keyboard.type("1")
    page.keyboard.press("Enter")
    page.wait_for_function("window.__fea.FA.doc.groups && window.__fea.FA.doc.groups.length === 1")
    page.click("#fa-mgrid td[data-r='0'][data-c='1']")
    h = page.locator("#fa-mgrid td[data-r='0'][data-c='1'] .fill").bounding_box()
    t = page.locator("#fa-mgrid td[data-r='2'][data-c='1']").bounding_box()
    page.mouse.move(h["x"] + 3, h["y"] + 3); page.mouse.down()
    page.mouse.move(t["x"] + 10, t["y"] + t["height"] / 2, steps=5); page.mouse.up()
    page.wait_for_function("window.__fea.FA.doc.members.filter(m => m.group).length === 3")
    assert page.evaluate("window.__fea.FA.doc.members[3].group") is None
    # paste: section and dimensions into row 4 (two cells), Delete clears the group of row 2
    page.click("#fa-mgrid td[data-r='3'][data-c='3']")
    page.evaluate("""() => { const dt = new DataTransfer(); dt.setData('text/plain', 'PIPE\t48.3 x 3.2');
        document.querySelector('#fa-mgrid').dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true})); }""")
    page.wait_for_function("window.__fea.FA.doc.members[3].section.shape === 'PIPE' && window.__fea.FA.doc.members[3].section.t === 3.2")
    page.click("#fa-mgrid td[data-r='3'][data-c='2']")
    page.keyboard.type("bar")
    page.keyboard.press("Enter")
    wait_text(page, "#status-text", "kind: beam or rod")
    page.click("#fa-mgrid td[data-r='1'][data-c='1']")
    page.keyboard.press("Delete")
    page.wait_for_function("!window.__fea.FA.doc.members[1].group")


def test_analysis_plate_grid_and_groups(page, client):
    """Plate grid: a group typed in the Group cell is made from the plate; the fill square copies it to the next
    plate; a group thickness change goes to both plates."""
    from test_analysis import STEEL
    pl = lambda i: {"id": "p%d" % i, "name": "Plate %d" % i, "t": 2, "position": "mid",
                    "points": [[0, 0, 100 * i], [100, 0, 100 * i], [100, 100, 100 * i]]}
    doc = {"name": "fea_pg", "source": {"type": "assembly", "name": ""}, "materials": STEEL, "default_material": "Steel",
           "members": [], "plates": [pl(1), pl(2)], "supports": [], "loads": [], "fasteners": [], "bodies": {}, "next": 10}
    client.put("/api/analysis/file/fea_pg", json=doc)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("window.__feaLoadNamed('fea_pg')")
    page.wait_for_selector("#fa-pgrid td[data-r='1']")
    page.click("#fa-pgrid td[data-r='0'][data-c='1']")
    page.keyboard.type("skin")
    page.keyboard.press("Enter")
    page.wait_for_function("(window.__fea.FA.doc.plate_groups || []).length === 1")
    page.click("#fa-pgrid td[data-r='0'][data-c='1']")
    h = page.locator("#fa-pgrid td[data-r='0'][data-c='1'] .fill").bounding_box()
    t = page.locator("#fa-pgrid td[data-r='1'][data-c='1']").bounding_box()
    page.mouse.move(h["x"] + 3, h["y"] + 3); page.mouse.down()
    page.mouse.move(t["x"] + 10, t["y"] + t["height"] / 2, steps=5); page.mouse.up()
    page.wait_for_function("window.__fea.FA.doc.plates.every(p => p.group)")
    page.click("#fa-plates tr.fa-pgrow")
    page.fill("#fpg-t", "6")
    page.dispatch_event("#fpg-t", "change")
    assert page.evaluate("window.__fea.FA.doc.plates.map(p => p.t)") == [6, 6]
    assert "ro" in page.get_attribute("#fa-pgrid td[data-r='1'][data-c='2']", "class")


def test_part_sketch_on_face_x_axis_from_view(page, client):
    """Sketch on a face: the sketch x axis is the principal axis nearest the screen right direction of the view,
    so the sketch opens as the face is seen."""
    client.put("/api/part/file/ui_skx", json=plate("ui_skx"))
    tab(page, "part")
    page.evaluate("window.__part.PT.mesh = null; window.__partLoadNamed('ui_skx')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    for view, n in (("front", [0, -1, 0]), ("right", [1, 0, 0]), ("top", [0, 0, 1]), ("iso", [1, 0, 0])):
        page.click("#tab-part [data-view=%s]" % view)
        time.sleep(0.3)
        r = page.evaluate("""(n) => { const P = window.__part, x = P.viewXdir(n);
            const right = new P.THREE.Vector3(1, 0, 0).applyQuaternion(P.PT.three.camera.quaternion);
            return {x, dot: right.x * x[0] + right.y * x[1] + right.z * x[2]}; }""", n)
        x = r["x"]
        assert sorted(abs(v) for v in x) == [0, 0, 1] and abs(sum(a * b for a, b in zip(x, n))) < 1e-9 and r["dot"] > 0.7, (view, r)


def test_part_bridge_surface_command(page, client):
    """Bridge surface: side A and side B edges picked on two surface bodies, Finish: a surface body of 3000 mm^2
    between the plates (status without error)."""
    from conftest import part_rec, rect
    p = part_rec("ui_br", [{"id": "s1", "name": "P1", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(100, 50)}},
                           {"id": "s2", "name": "P2", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(100, 50, 0, 80)}}])
    client.put("/api/part/file/ui_br", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_br')")
    page.wait_for_function("window.__part.PT.surfaces && Object.keys(window.__part.PT.surfaces).length === 2")
    page.click("#tab-part [data-add=surf_bridge]") if page.is_visible("#tab-part [data-add=surf_bridge]") else page.evaluate("window.__part.startCommand('surf_bridge')")
    page.wait_for_function("window.__part.PT.cmd && window.__part.feat(window.__part.PT.cmd.id).type === 'surf_bridge'")
    r = page.evaluate("""() => { const P = window.__part, PT = P.PT, f = P.feat(PT.cmd.id), steps = P.commandSteps(f);
        const keyAt = y => { for (const [sid, sm] of Object.entries(PT.surfaces)) { const k = (sm.edge_keys || []).find(k => k && Math.abs(k.mid[1] - y) < 1e-6 && Math.abs(k.len - 100) < 1e-6); if (k) return [sid, k]; } return null; };
        const a = keyAt(50), b = keyAt(80);
        if (!a || !b) return 'no edges';
        steps[0].accept(f, { kind: 'edge', key: a[1], surface: a[0] });
        steps[1].accept(f, { kind: 'edge', key: b[1], surface: b[0] });
        return [f.edges_a.length, f.edges_b.length]; }""")
    assert r == [1, 1], r
    page.evaluate("window.__part.finishCommand()")
    page.wait_for_function("!window.__part.PT.cmd")
    page.wait_for_function("""(() => { const PT = window.__part.PT; const f = PT.part.features.find(x => x.type === 'surf_bridge');
        const st = f && PT.status[f.id]; return st && !st.error && PT.surfaces[f.id]; })()""", timeout=60000)


def test_explicit_tab_model_build_run_results(page, client, tmp_path):
    """Explicit tab: geometry, rigid impactor, support on a face, Write .inp, New run, Build, Run with the stand-in
    OpenCourant executables, status board, results on the 3D view and the energy curve."""
    import fake_openradioss
    from conftest import part_rec, rect

    def block(name, w, h, t, x=0.0, y=0.0):
        return part_rec(name, [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                                "sketch": {"entities": rect(w, h, x, y)}, "depth": t}])
    assert client.put("/api/part/file/xpb_target", json=block("xpb_target", 200, 200, 10, -100, -100)).status_code == 200
    assert client.put("/api/part/file/xpb_imp", json=block("xpb_imp", 40, 40, 40, -20, -20)).status_code == 200
    assert client.put("/api/assembly/file/xpb_drop", json={"name": "xpb_drop", "next": 3, "components": [
        {"id": "1", "name": "target", "source": {"type": "part", "name": "xpb_target"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "impactor", "source": {"type": "part", "name": "xpb_imp"}, "pos": [0, 0, 15], "rot": [0, 0, 0]}]}).status_code == 200
    exe = fake_openradioss.install(str(tmp_path / "exec"))
    assert client.put("/api/explicit/env", json={"or_exec": exe, "run_target": "Local (Windows)", "ssh_threads": "2"}).status_code == 200
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-source", "assembly:xpb_drop")
    page.wait_for_selector("tr[data-b='2'] [data-bk=role]")
    page.select_option("tr[data-b='2'] [data-bk=role]", "rigid")
    page.select_option("tr[data-b='2'] [data-bk=material]", "Rigid")
    page.fill("[data-mesh=size]", "20")
    page.dispatch_event("[data-mesh=size]", "change")
    # support: a face of the plate near a corner, top view
    page.click("[data-xpview=top]")
    page.click("#xp-supbtn")
    box = page.locator("#xp-view > canvas").first.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2 - box["height"] * 0.3, box["y"] + box["height"] * 0.5 - box["height"] * 0.3)
    page.wait_for_function("window.__xp.XP.doc.supports.length === 1")
    assert "target" in page.inner_text(".xp-sups .xp-face")
    page.click("#xp-model-btn")
    page.wait_for_function("document.querySelector('#xp-show').value === 'mesh'", timeout=120000)
    assert page.evaluate("window.__xp.XP.meshSummary.supports") >= 1
    page.fill("#xp-run-desc", "browser drop")
    page.click("#xp-run-new")
    page.wait_for_function("(window.__xp.XP.doc.settings.out_dir || '').includes('_r001_browser-drop')")
    page.select_option("[data-s=rigid_vel_mode]", "Explicit (Vx Vy Vz below)")
    page.fill("[data-s=rigid_vel]", "0 0 -5000")
    page.dispatch_event("[data-s=rigid_vel]", "change")
    page.fill("[data-s=tstop]", "0.01")
    page.dispatch_event("[data-s=tstop]", "change")
    page.click("#xp-build")
    page.wait_for_function("(window.__xp.XP.doc.settings.rad_target || '').endsWith('_b01_0000.rad')", timeout=120000)
    page.click("#xp-run")
    page.wait_for_function("document.querySelector('#xp-show').value === 'results'", timeout=120000)
    wait_text(page, "#xp-board", "Done")
    assert page.is_visible("#xp-legend")
    assert page.evaluate("document.querySelector('#xp-field').value") == "cell|3DELEM_Strain|eps1"
    assert page.locator("#xp-plot polyline").count() == 1
    wait_text(page, "#xp-log", "Local Task Complete")
    # frame slider: the first frame, then the eroded element of the last frame is hidden
    page.evaluate("document.querySelector('#xp-frame').value = 0; document.querySelector('#xp-frame').dispatchEvent(new Event('change'))")
    page.wait_for_function("window.__xp.XP.res.frame.index === 0")
    n0 = page.evaluate("(() => { let n = 0; window.__xp.XP.three.group.traverse(o => { if (o.isMesh && o.userData.kind === 'mesh') n += o.geometry.attributes.position.count; }); return n; })()")
    page.evaluate("document.querySelector('#xp-frame').value = 4; document.querySelector('#xp-frame').dispatchEvent(new Event('change'))")
    page.wait_for_function("window.__xp.XP.res.frame.index === 4")
    n4 = page.evaluate("(() => { let n = 0; window.__xp.XP.three.group.traverse(o => { if (o.isMesh && o.userData.kind === 'mesh') n += o.geometry.attributes.position.count; }); return n; })()")
    assert n0 - n4 == 12                         # top and bottom face of the eroded hexahedron: 4 triangles
    # save, list in the File menu
    page.__dict__["_answer"] = "xpb_doc"
    file_menu(page, "#tab-xp")
    page.click("#xp-saveas")
    page.wait_for_function("window.__xp.XP.doc.name === 'xpb_doc' && !window.__xp.XP.dirty")
    assert "xpb_doc" in client.get("/api/explicit/list").get_json()


def test_explicit_tab_deck_generator(page, client):
    """Explicit tab, deck generator source: beam table with sums and the coincidence check, Pattern, plan and section
    diagrams, plates on the 3D view, Write .inp, Generate STEP and the part with the surface bodies."""
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-kind", "deck")
    page.wait_for_selector("#xp-dk-plan line", state="attached")
    page.wait_for_function("window.__xp.XP.deckCheck && window.__xp.XP.deckCheck.parts.length === 8")
    assert page.is_disabled("#xp-source") and page.is_disabled("#xp-supbtn")
    n0 = page.evaluate("window.__xp.XP.doc.deck.beams.length")
    assert page.locator("tr[data-bi]").count() == n0 == 9
    # a sum in a field; a position on top of another beam of the same axis is refused
    page.fill("tr[data-bi='0'] [data-bk=h]", "400+100")
    page.dispatch_event("tr[data-bi='0'] [data-bk=h]", "change")
    assert page.input_value("tr[data-bi='0'] [data-bk=h]") == "500"
    page.fill("tr[data-bi='3'] [data-bk=pos]", "1000.2")
    page.dispatch_event("tr[data-bi='3'] [data-bk=pos]", "change")
    assert page.evaluate("window.__xp.XP.doc.deck.beams[3].pos") == 2000
    wait_text(page, "#status", "two beams on one line")
    # pattern of STIFF (row 5, x = 500): 3 at 250 -> 500 skipped, 750 and 1000 (BEAM there: skipped)
    page.click("tr[data-bi='5'] td:nth-child(1) input")
    page.click("#xp-dk-pat")
    page.fill("[data-pt=n]", "3")
    page.dispatch_event("[data-pt=n]", "input")
    page.fill("[data-pt=sp]", "250")
    page.dispatch_event("[data-pt=sp]", "input")
    wait_text(page, "#xp-pt-prev", "1 new")
    page.click("#xp-pt-ok")
    page.wait_for_function("window.__xp.XP.doc.deck.beams.length === 10")
    assert page.evaluate("window.__xp.XP.doc.deck.beams[9]") == {"name": "STIFF", "axis": "x", "pos": 750, "h": 150, "bf_top": 0, "bf_bot": 0, "t_web": 6, "t_flange": 0}
    assert page.locator("#xp-dk-sec line").count() >= 2
    page.wait_for_function("window.__xp.XP.deckCheck.parts.find(p => p.name === 'STIFF_WEB').polys.length === 15")
    nmesh = page.evaluate("(() => { let n = 0; window.__xp.XP.three.group.traverse(o => { if (o.isMesh && o.userData.deckPart) n++; }); return n; })()")
    assert nmesh == 8
    # edge supports, Write .inp
    page.select_option("[data-edge=x0]", "clamped")
    page.fill("[data-dk=size]", "200")
    page.dispatch_event("[data-dk=size]", "change")
    page.click("#xp-model-btn")
    page.wait_for_function("document.querySelector('#xp-show').value === 'mesh'", timeout=120000)
    s = page.evaluate("window.__xp.XP.meshSummary")
    assert s["supports"] == 1 and len(s["sets"]) == 8 and s["longest_edge"] <= 200.001
    wait_text(page, "#xp-model", "Mesh written")
    # Generate STEP: the part with one surface body per component
    page.__dict__["_answer"] = "xpb_deck"
    file_menu(page, "#tab-xp")
    page.click("#xp-saveas")
    page.wait_for_function("window.__xp.XP.doc.name === 'xpb_deck' && !window.__xp.XP.dirty")
    page.click("#xp-dk-step")
    page.wait_for_function("window.__xp.XP.deckStep && window.__xp.XP.deckStep.part === 'xpb_deck_deck'", timeout=120000)
    assert len(client.get("/api/part/file/xpb_deck_deck").get_json()["features"]) == 8
    page.click("#xp-dk-openpart")
    page.wait_for_function("window.__part.PT.part && window.__part.PT.part.name === 'xpb_deck_deck' && Object.keys(window.__part.PT.status || {}).length === 8", timeout=120000)
    assert page.evaluate("Object.values(window.__part.PT.status).every(s => !s.error && s.surface)")
