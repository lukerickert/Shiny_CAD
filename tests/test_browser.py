# -*- coding: utf-8 -*-
"""Browser tests (Playwright, headless Chromium): the main workflows of the interface. Any JavaScript error on
the page fails the test. Skipped when Playwright or its browser is not installed
(py -m pip install playwright, then py -m playwright install chromium)."""
import logging
import math
import json
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
    # the closed profile is known once the build status of the sketch has arrived
    page.wait_for_function("(() => { const s = window.__part.PT.status; return Object.values(s).some(x => x.sketch && x.profiles === 1); })()")
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
    # the view can still change after the part is shown (fit): the position is taken again when a click misses
    done = "([q]) => { const P = window.__part, f = P.feat(P.PT.cmd.id); return f.point && Math.abs(f.point[0] - q[0]) + Math.abs(f.point[1] - q[1]) + Math.abs(f.point[2] - q[2]) < 1e-6; }"
    for k in range(4):
        x, y, q = page.evaluate(js)
        page.mouse.move(x, y)
        page.mouse.click(x, y)
        try:
            page.wait_for_function(done, arg=[q], timeout=3000 if k < 3 else 30000)
            break
        except Exception:
            if k == 3:
                raise
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


def test_part_surface_fillet_command(page, client):
    """Surface fillet: surface A and surface B chosen, radius 3, Finish: one sewn surface body of three faces; the
    sources are hidden."""
    from conftest import part_rec, rect
    p = part_rec("ui_sf", [{"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 0)}},
                           {"id": "b", "name": "B", "type": "surf_sketch", "kind": "planar", "plane": "XZ", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 0)}}])
    client.put("/api/part/file/ui_sf", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_sf')")
    page.wait_for_function("window.__part.PT.surfaces && Object.keys(window.__part.PT.surfaces).length === 2")
    page.evaluate("window.__part.startCommand('surf_fillet')")
    page.wait_for_function("window.__part.PT.cmd && window.__part.feat(window.__part.PT.cmd.id).type === 'surf_fillet'")
    page.select_option("#pf-source_a", "a")
    page.evaluate("window.__part.gotoStep(1)")
    page.wait_for_selector("#pf-source_b")
    page.select_option("#pf-source_b", "b")
    page.evaluate("window.__part.gotoStep(2)")
    page.wait_for_selector("#pf-sfr")
    page.fill("#pf-sfr", "3")
    page.dispatch_event("#pf-sfr", "change")
    page.evaluate("window.__part.finishCommand()")
    page.wait_for_function("!window.__part.PT.cmd")
    page.wait_for_function("""(() => { const PT = window.__part.PT; const f = PT.part.features.find(x => x.type === 'surf_fillet');
        const st = f && PT.status[f.id]; return st && !st.error && st.faces === 3; })()""", timeout=60000)
    assert page.evaluate("window.__part.PT.hidden.a && window.__part.PT.hidden.b")
    area = page.evaluate("window.__part.PT.status[window.__part.PT.part.features.find(x => x.type === 'surf_fillet').id].area")
    assert abs(area - (2 * 40 * 17 + math.pi / 2 * 3 * 40)) < 0.01


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


# --------------------------------------------------------------------------- reference images of sketches

def _photo(path, H, k1=0.0, size=(1600, 1200)):
    """Synthetic photo: a 200 mm x 100 mm rectangle and its diagonals on a grey background, seen through the
    homography H (object mm -> undistorted pixels) and a lens with the radial coefficient k1 (sketchimage model).
    Returns the image pixels of the corners."""
    import numpy as np
    from PIL import Image, ImageDraw
    from drawgen import sketchimage as si
    w, h = size
    im = Image.new("RGB", size, (150, 150, 150))
    dr = ImageDraw.Draw(im)

    def img(pts):
        q, _ = si.apply_h(H, pts)
        return si.distort(q, k1, w, h)
    c = [(0, 0), (200, 0), (200, 100), (0, 100)]
    for a, b in list(zip(c, c[1:] + c[:1])) + [(c[0], c[2]), (c[1], c[3])]:
        t = np.linspace(0, 1, 60)[:, None]
        p = img(np.array(a) * (1 - t) + np.array(b) * t)
        dr.line([tuple(x) for x in p], fill=(0, 0, 0), width=3)
    im.save(path)
    return img(c)


def _click_px(pg, px):
    """Clicks the image pixel px (of the stored file) of the selected image in the sketch editor."""
    s = pg.evaluate("([u, v]) => { const sk = window.__sk, m = sk.SK.doc.images.find(x => x.id === sk.SK.imgSel); return sk.S(sk.affApply(m.A, sk.imgShownPx(m, [u, v]))); }", [float(px[0]), float(px[1])])
    box = pg.locator("#sk-canvas svg").bounding_box()
    pg.mouse.click(box["x"] + s[0], box["y"] + s[1])


def _model_of(pg, p):
    """Sketch point of the image pixel p of the stored file, with the current corrections."""
    return pg.evaluate("([u, v]) => { const sk = window.__sk, m = sk.SK.doc.images.find(x => x.id === sk.SK.imgSel); return sk.affApply(m.A, sk.imgShownPx(m, [u, v])); }", [float(p[0]), float(p[1])])


def test_sketch_image_scale_perspective_lens(page, tmp_path):
    import numpy as np
    tab(page, "sketch")
    page.click("#sk-new")
    H = np.array([[4.2, 1.1, 300.0], [0.3, 3.0, 420.0], [0.0006, 0.0018, 1.0]])
    path = str(tmp_path / "photo.png")
    corners = _photo(path, H)
    page.set_input_files("#sk-img-file", path)
    page.wait_for_function("window.__sk.SK.doc.images.length === 1 && window.__sk.SK.imgSel")
    wait_text(page, "#sk-props", "Scale from distance")
    assert page.locator("#sk-images .sk-image").count() == 1
    assert page.locator("#sk-img image").count() == 1
    # scale from distance: corner 1 to corner 2 is 200 mm (in the perspective image this is approximate)
    page.click("#sk-props button[data-ia=imgscale]")
    page._answer = ""
    _click_px(page, corners[0])
    _click_px(page, corners[1])
    page.fill("#value-dialog-input", "200")
    page.press("#value-dialog-input", "Enter")
    page.wait_for_function("window.__sk.SK.tool === 'select'")
    a, b = _model_of(page, corners[0]), _model_of(page, corners[1])
    assert abs(math.hypot(b[0] - a[0], b[1] - a[1]) - 200) < 1.0
    # perspective: the four corners of the 200 x 100 mm rectangle
    page.click("#sk-props button[data-ia=persp]")
    page.fill("#skp-pw", "200")
    page.fill("#skp-ph", "100")
    page.click("#skp-ppick")
    page.wait_for_function("window.__sk.SK.tool === 'imgpersp'")
    for c in corners:
        _click_px(page, c)
    page.wait_for_function("window.__sk.SK.tool === 'select' && window.__sk.SK.doc.images[0].cfile", timeout=60000)
    m = [_model_of(page, c) for c in corners]
    d = [m[1][0] - m[0][0], m[1][1] - m[0][1]]
    assert abs(d[0] - 200) < 1.5 and abs(d[1]) < 1.0, m
    assert abs(math.hypot(m[2][0] - m[1][0], m[2][1] - m[1][1]) - 100) < 1.5, m
    assert abs(math.hypot(m[3][0] - m[0][0], m[3][1] - m[0][1]) - 100) < 1.5, m
    # the image is drawn from the corrected file
    page.wait_for_function("document.querySelector('#sk-img image').getAttribute('href').includes('_c')")
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "sketch_image_perspective.png"))
    # undo returns to the image before the perspective correction
    page.keyboard.press("Control+z")
    page.wait_for_function("!window.__sk.SK.doc.images[0].cfile")
    # 3 control points: affine placement without a corrected file
    page.click("#sk-images .sk-image span")
    page.click("#sk-images .sk-image span")
    page.click("#sk-props button[data-ia=imgctrl]")
    page.wait_for_function("window.__sk.SK.tool === 'imgctrl'")
    for p, xy in zip(corners[:3], ("10,10", "210,10", "210,-90")):
        _click_px(page, p)
        page.keyboard.type(xy)
        page.keyboard.press("Enter")
    wait_text(page, "#sk-props", "Pairs: 3")
    page.focus("#sk-canvas")
    page.keyboard.press("Enter")
    page.wait_for_function("window.__sk.SK.tool === 'select'")
    for p, xy in zip(corners[:3], ((10, 10), (210, 10), (210, -90))):
        m = _model_of(page, p)
        assert math.hypot(m[0] - xy[0], m[1] - xy[1]) < 1.0, (m, xy)
    assert not page.evaluate("window.__sk.SK.doc.images[0].cfile")


def test_sketch_image_lens_and_control_points(page, tmp_path):
    import numpy as np
    tab(page, "sketch")
    page.click("#sk-new")
    k1 = 0.08
    H = np.array([[5.0, 0.0, 300.0], [0.0, 5.0, 350.0], [0.0, 0.0, 1.0]])
    path = str(tmp_path / "lens.png")
    _photo(path, H, k1)
    page.set_input_files("#sk-img-file", path)
    page.wait_for_function("window.__sk.SK.doc.images.length === 1 && window.__sk.SK.imgSel")
    from drawgen import sketchimage as si
    page.click("#sk-props button[data-ia=imglens]")
    page.wait_for_function("window.__sk.SK.tool === 'imglens'")
    # points along the long edges and the left edge of the rectangle (straight on the object), typed as sketch
    # coordinates (a click is placed to the screen pixel)
    A = page.evaluate("window.__sk.SK.doc.images[0].A")
    for a, b in (((0, 0), (200, 0)), ((0, 100), (200, 100)), ((0, 0), (0, 100))):
        for t in np.linspace(0, 1, 6):
            q, _ = si.apply_h(H, [np.array(a) * (1 - t) + np.array(b) * t])
            u, v = si.distort(q, k1, 1600, 1200)[0]
            page.focus("#sk-canvas")
            page.keyboard.type("%.6f,%.6f" % (A[0] * u + A[2] * v + A[4], A[1] * u + A[3] * v + A[5]))
            page.keyboard.press("Enter")
        page.click("#skp-lend")
    wait_text(page, "#sk-props", "Lines: 3 (18 points)")
    page.click("#skp-lapply")
    page.wait_for_function("window.__sk.SK.tool === 'select' && window.__sk.SK.doc.images[0].cfile", timeout=60000)
    got = page.evaluate("window.__sk.SK.doc.images[0].k1")
    assert abs(got - k1) < 0.002, got
    wait_text(page, "#sk-props", "lens k1")
    # control points: 4 corners to typed sketch points (the rectangle 200 x 100 at the origin)
    page.click("#sk-props button[data-ia=imgctrl]")
    page.wait_for_function("window.__sk.SK.tool === 'imgctrl'")
    cq, _ = si.apply_h(H, [(0, 0), (200, 0), (200, 100), (0, 100)])
    cp = si.distort(cq, k1, 1600, 1200)
    for p, xy in zip(cp, ("0,0", "200,0", "200,-100", "0,-100")):
        _click_px(page, p)
        page.keyboard.type(xy)
        page.keyboard.press("Enter")
    wait_text(page, "#sk-props", "Pairs: 4")
    page.click("#skp-capply")
    page.wait_for_function("window.__sk.SK.tool === 'select' && window.__sk.SK.doc.images[0].ctrl", timeout=60000)
    for p, xy in zip(cp, ((0, 0), (200, 0), (200, -100), (0, -100))):
        m = _model_of(page, p)
        assert math.hypot(m[0] - xy[0], m[1] - xy[1]) < 1.5, (m, xy)
    # saved with the sketch; the image file is in the images folder of the project
    page.fill("#sk-name", "imgtest")
    page.click("#sk-save")
    wait_text(page, "#sk-msg, #status", "Saved")


def test_analysis_modal_ui(page, client):
    """Modal analysis of a cantilever plate item (500 x 100 x 10 mm): analysis type and number of modes in the
    settings, mode list in the state selector and in the results, mode shape with a normalised legend."""
    from test_analysis import CCX, STEEL
    if CCX is None:
        pytest.skip("CalculiX (ccx) not found")
    doc = {"name": "fea_modal", "source": {"type": "assembly", "name": ""}, "materials": STEEL, "default_material": "Steel",
           "mesh": {"size": 20}, "bonded": True, "bodies": {}, "fasteners": [], "members": [], "loads": [],
           "plates": [{"id": "p1", "name": "P1", "t": 10, "position": "mid",
                       "points": [[0, 0, 0], [500, 0, 0], [500, 100, 0], [0, 100, 0]]}]}
    pv = client.post("/api/analysis/plates", json={"analysis": doc}).get_json()["plates"]
    root = next(i for i, r in enumerate(pv[0]["refs"]) if r["kind"] == "plane" and abs(r["c"][0]) < 1e-6)
    doc["supports"] = [{"id": "s1", "name": "root", "target": {"comp": "plate_p1", "face": root}, "type": "fixed"}]
    client.put("/api/analysis/file/fea_modal", json=doc)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("window.__feaLoadNamed('fea_modal')")
    page.wait_for_function("window.__fea.FA.doc.name === 'fea_modal'")
    page.select_option("#fs-atype", "modal")
    page.fill("#fs-modes", "3")
    page.dispatch_event("#fs-modes", "change")
    assert page.evaluate("window.__fea.FA.doc.analysis_type") == "modal" and page.evaluate("window.__fea.FA.doc.modes") == 3
    page.click("#fa-solve")
    page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.modes", timeout=300000)
    assert page.locator("#fa-state option").count() == 3
    wait_text(page, "#fa-results", "f (Hz)")
    f1 = page.evaluate("window.__fea.FA.res.modes[0].value")
    E, rho, A, L, I = 210000.0, 7.85e-9, 1000.0, 500.0, 100 * 10 ** 3 / 12
    ref = 1.875 ** 2 / (2 * math.pi) * math.sqrt(E * I / (rho * A * L ** 4))
    assert abs(f1 / ref - 1) < 0.05, (f1, ref)
    wait_text(page, "#fa-legend", "Mode 1")
    wait_text(page, "#fa-legend", "normalised")
    page.click("#fa-results tr[data-mode='2']")
    assert page.input_value("#fa-state") == "m2"
    wait_text(page, "#fa-legend", "Mode 2")
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "analysis_modal.png"))


def test_mate_vertex_edge_tangent_gear(page, client):
    """Edges and vertices: a vertex of one plate picked for A of a Coincident mate (on a face of the other plate), the
    circular edge of the hole for A of a Concentric mate; Tangent and Gear mates in the toolbar with their fields."""
    client.put("/api/part/file/ui_ev", json=plate("ui_ev"))
    tab(page, "asm")
    add_part(page, "ui_ev")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 1 && window.__asm.AS.bbox")
    add_part(page, "ui_ev")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length >= 2 && window.__asm.AS.result.components.every(c => c.vrefs)")
    n = asm_state(page, "AS.asm.components.length")
    screen = """([i, kind, pred]) => { const A = window.__asm, AS = A.AS, T = A.THREE, t = AS.three;
        const c = AS.result.components.find(x => x.id === AS.asm.components[i].id), M = A.compMatrix(A.comp(c.id));
        const r = t.renderer.domElement.getBoundingClientRect();
        const list = kind === 'vertex' ? c.vrefs.map((v, k) => [k, v.c]) : c.erefs.map((e, k) => [k, e && e.m]).filter(x => x[1]);
        for (const [k, q] of list) {
          if (kind === 'edge' && c.erefs[k].kind !== 'circle') continue;
          const p = new T.Vector3(...q).applyMatrix4(M).project(t.camera);
          const x = r.left + (p.x + 1) / 2 * r.width, y = r.top + (1 - p.y) / 2 * r.height;
          const h = A.mateHitAt({ clientX: x, clientY: y }, true);
          if (h && h.comp === c.id && (kind === 'vertex' ? h.vertex === k : h.edge === k)) return [x, y];
        }
        return null; }"""
    centre = """(i) => { const AS = window.__asm.AS, T = window.__asm.THREE, t = AS.three;
        const c = AS.asm.components[i], m = t.pickables.find(o => o.userData.id === c.id);
        const b = new T.Box3().setFromObject(m), p = new T.Vector3(b.min.x + 0.1 * (b.max.x - b.min.x), b.min.y + 0.1 * (b.max.y - b.min.y), b.max.z).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }"""
    page.click("#as-tb-mates button[data-mate=coincident]")
    page.check("#as-edgepick")
    xy = page.evaluate(screen, [n - 1, "vertex", None])
    assert xy
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const m = window.__asm.AS.asm.mates.slice(-1)[0]; return m.a && m.a.vertex !== undefined && !m.b; })()")
    page.uncheck("#as-edgepick")
    page.mouse.click(*page.evaluate(centre, n - 2))
    page.wait_for_function("(() => { const m = window.__asm.AS.asm.mates.slice(-1)[0]; return m.b && m.b.face !== undefined; })()")
    wait_text(page, "#as-mates", "vertex (")
    page.wait_for_function("window.__asm.AS.unsat && Object.keys(window.__asm.AS.unsat).length === 0", timeout=60000)
    # the circular edge of the hole for a Concentric mate
    page.click("#as-tb-mates button[data-mate=concentric]")
    page.check("#as-edgepick")
    xy = page.evaluate(screen, [n - 1, "edge", None])
    assert xy
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const m = window.__asm.AS.asm.mates.slice(-1)[0]; return m.a && m.a.edge !== undefined; })()")
    wait_text(page, "#as-mates", "edge, circle Ø20")
    # Tangent and Gear: mate types, labels and the gear ratio field
    page.click("#as-tb-mates button[data-mate=gear]")
    wait_text(page, "#as-mates", "Ratio (turns of B per turn of A)")
    assert page.input_value("#am-ratio") == "1"
    page.select_option("#am-type", "tangent")
    wait_text(page, "#as-mates", "cylinder on the other side")
    assert page.locator("#as-tb-mates button[data-mate=tangent] svg.tb-ico").count() == 1


def test_sketch_image_scale_from_circle(page, tmp_path):
    """Scale from circle: 3 points on a circle of 300 px radius and a diameter of 50 mm give 50 / 600 mm/px."""
    from PIL import Image, ImageDraw
    path = str(tmp_path / "circle.png")
    im = Image.new("RGB", (1200, 900), (255, 255, 255))
    ImageDraw.Draw(im).ellipse([300, 150, 900, 750], outline=(0, 0, 0), width=3)
    im.save(path)
    tab(page, "sketch")
    page.click("#sk-new")
    page.set_input_files("#sk-img-file", path)
    page.wait_for_function("window.__sk.SK.doc.images.length === 1 && window.__sk.SK.imgSel")
    page.click("#sk-props button[data-ia=imgcircle]")
    page.wait_for_function("window.__sk.SK.tool === 'imgcircle'")
    for a in (20, 140, 260):
        _click_px(page, (600 + 300 * math.cos(math.radians(a)), 450 + 300 * math.sin(math.radians(a))))
    page.fill("#value-dialog-input", "50")
    page.press("#value-dialog-input", "Enter")
    page.wait_for_function("window.__sk.SK.tool === 'select'")
    a, b = _model_of(page, (300, 450)), _model_of(page, (900, 450))
    assert abs(math.hypot(b[0] - a[0], b[1] - a[1]) - 50) < 0.5


def test_sketch_image_round_part(page, tmp_path):
    """Round part: a face with circles of 80 mm and 30 mm diameter in perspective; 8 points on each circle give the
    perspective correction (concentric circles), 8 points on circle 1 and the centre the same."""
    import numpy as np
    from PIL import Image, ImageDraw
    from drawgen import sketchimage as si
    Hm = np.array([[6.0, 1.5, 700.0], [0.4, 4.0, 520.0], [0.0009, 0.0035, 1.0]])
    path = str(tmp_path / "round.png")
    im = Image.new("RGB", (1600, 1200), (150, 150, 150))
    dr = ImageDraw.Draw(im)
    for r in (40, 15):
        a = np.linspace(0, 2 * math.pi, 200)
        q, _ = si.apply_h(Hm, np.c_[r * np.cos(a), r * np.sin(a)])
        dr.line([tuple(x) for x in q], fill=(0, 0, 0), width=3)
    im.save(path)
    rim = lambda r: si.apply_h(Hm, [[r * math.cos(t), r * math.sin(t)] for t in np.linspace(0.3, 5.8, 8)])[0]
    tab(page, "sketch")
    page.click("#sk-new")
    page.set_input_files("#sk-img-file", path)
    page.wait_for_function("window.__sk.SK.doc.images.length === 1 && window.__sk.SK.imgSel")
    probe = [(-40, 0), (40, 0), (0, -40), (0, 40), (0, 0)]
    probe_px = si.apply_h(Hm, probe)[0]

    def check(tol):
        m = [_model_of(page, p) for p in probe_px]
        for (i, j) in ((0, 1), (2, 3)):
            assert abs(math.hypot(m[j][0] - m[i][0], m[j][1] - m[i][1]) - 80) < tol, m
        assert abs(math.hypot(m[4][0] - m[0][0], m[4][1] - m[0][1]) - 40) < tol, m
    for mode in ("concentric", "centre"):
        page.click("#sk-props button[data-ia=round]")
        page.wait_for_function("window.__sk.SK.tool === 'imground'")
        page.fill("#skp-rd", "80")
        page.dispatch_event("#skp-rd", "change")
        for p in rim(40):
            _click_px(page, p)
        wait_text(page, "#sk-props", "Circle 1 (8 points)")
        wait_text(page, "#sk-props", "affine from 1 circle")
        if mode == "concentric":
            page.check("input[name=skp-ract][value='1']")
            for p in rim(15):
                _click_px(page, p)
            wait_text(page, "#sk-props", "2 concentric circles")
            if os.environ.get("DRAWGEN_SHOTS"):
                page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "sketch_image_round_pick.png"))
        else:
            page.check("input[name=skp-ract][value=c]")
            _click_px(page, si.apply_h(Hm, [[70, 0]])[0][0])         # outside circle 1: refused
            wait_text(page, "#sk-msg", "outside circle 1")
            wait_text(page, "#sk-props", "Centre (not picked)")
            _click_px(page, probe_px[4])
            wait_text(page, "#sk-props", "circle and centre")
        page.click("#skp-rapply")
        page.wait_for_function("window.__sk.SK.tool === 'select' && window.__sk.SK.doc.images[0].cfile", timeout=60000)
        assert page.evaluate("window.__sk.SK.doc.images[0].round.mode") == mode
        check(1.5)
        wait_text(page, "#sk-props", "round part")
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "sketch_image_round.png"))


def test_sketch_pan_release_missed(page):
    """A pan whose button release does not reach the page (released outside the window) ends at the next mouse move
    without the button; a release outside the canvas ends it as well."""
    tab(page, "sketch")
    page.click("#sk-new")
    box = page.locator("#sk-canvas svg").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    ev = """([type, x, y, button, buttons]) => { const svg = document.querySelector('#sk-canvas svg');
        svg.dispatchEvent(new MouseEvent(type, {bubbles: true, clientX: x, clientY: y, button, buttons})); }"""
    page.evaluate(ev, ["mousedown", cx, cy, 1, 4])
    page.evaluate(ev, ["mousemove", cx + 80, cy + 40, 1, 4])
    v0 = page.evaluate("JSON.stringify(window.__sk.SK.view)")
    page.evaluate(ev, ["mousemove", cx + 200, cy + 100, 0, 0])          # button up, no mouseup event
    assert page.evaluate("window.__sk.SK.pan") is None
    assert page.evaluate("JSON.stringify(window.__sk.SK.view)") == v0
    # middle button released over the side panel
    page.mouse.move(cx, cy)
    page.mouse.down(button="middle")
    page.mouse.move(box["x"] + box["width"] + 60, cy, steps=4)
    page.mouse.up(button="middle")
    assert page.evaluate("window.__sk.SK.pan") is None
    # the Line tool takes clicks after the pans
    page.keyboard.press("q")
    page.mouse.click(cx - 100, cy)
    page.mouse.click(cx + 100, cy)
    page.keyboard.press("Escape")
    assert page.evaluate("window.__sk.SK.doc.entities.filter(e => e.t === 'line' && !e.axis).length") == 1


def test_part_sketch_image_shown_closed(page, tmp_path):
    """Show when the sketch is closed: the image of a feature sketch is drawn on its plane in the Part view."""
    from PIL import Image
    path = str(tmp_path / "ref.png")
    Image.new("RGB", (400, 300), (200, 120, 40)).save(path)
    tab(page, "part")
    page.click("#tab-part [data-add=sketch]")
    page.get_by_role("button", name="Draw", exact=True).click()
    page.wait_for_selector("#tab-sketch:not([hidden])")
    page.set_input_files("#sk-img-file", path)
    page.wait_for_function("window.__sk.SK.doc.images.length === 1 && window.__sk.SK.imgSel")
    page.check("#skp-i3d")
    assert page.evaluate("window.__sk.SK.doc.images[0].show3d") is True
    corners = page.evaluate("(() => { const m = window.__sk.SK.doc.images[0]; return [[0, 0], [400, 300]].map(p => window.__sk.affApply(m.A, p)); })()")
    page.click("#sk-canvas")
    page.keyboard.press("Control+e")
    page.wait_for_selector("#tab-part:not([hidden])")
    count = "window.__part.PT.three.group.children.filter(o => o.userData.kind === 'sketchimage').length"
    page.wait_for_function(count + " === 1")
    # the quad lies on the XY plane at the corners of the image in the sketch
    pos = page.evaluate("Array.from(window.__part.PT.three.group.children.find(o => o.userData.kind === 'sketchimage').geometry.attributes.position.array)")
    assert abs(pos[0] - corners[0][0]) < 1e-3 and abs(pos[1] - corners[0][1]) < 1e-3 and abs(pos[2]) < 1e-9
    assert abs(pos[6] - corners[1][0]) < 1e-3 and abs(pos[7] - corners[1][1]) < 1e-3
    # Sketches unchecked: no image
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "part_sketch_image.png"))
    page.evaluate("(() => { const c = document.querySelector('#pt-showsketch'); c.checked = false; c.dispatchEvent(new Event('change')); })()")
    page.wait_for_function(count + " === 0")


def _click_model(pg, x, y):
    s = pg.evaluate("([x, y]) => window.__sk.S([x, y])", [x, y])
    box = pg.locator("#sk-canvas svg").bounding_box()
    pg.mouse.click(box["x"] + s[0], box["y"] + s[1])


def _typed(pg, *pts):
    for t in pts:
        pg.keyboard.type(t)
        pg.keyboard.press("Enter")


def test_sketch_centre_rectangle_slot_tangent_arc(page):
    tab(page, "sketch")
    page.click("#sk-new")
    ents = "window.__sk.SK.doc.entities.filter(e => !e.axis)"
    # centre rectangle: centre (10, 5), corner (30, 15); construction diagonals and centre point; DOF 4
    page.click("#sk-tools-draw button[data-tool=rectc]")
    _typed(page, "10,5", "30,15")
    page.keyboard.press("Escape")
    wait_text(page, "#tab-sketch", "DOF 4")
    r = page.evaluate(ents + ".map(e => [e.t, !!e.constr])")
    assert sorted(r) == sorted([["line", False]] * 4 + [["line", True]] * 2 + [["point", True]])
    xs = page.evaluate(ents + ".filter(e => e.t === 'line' && !e.constr).flatMap(e => [e.x1, e.x2])")
    assert abs(min(xs) + 10) < 1e-6 and abs(max(xs) - 30) < 1e-6
    page.keyboard.press("Control+z")
    page.wait_for_function(ents + ".length === 0")
    # slot: centres (0, 0) and (40, 0), typed width 10; horizontal centre line; DOF 4
    page.click("#sk-tools-draw button[data-tool=slot]")
    _typed(page, "0,0", "40,0", "10")
    page.keyboard.press("Escape")
    wait_text(page, "#tab-sketch", "DOF 4")
    arcs = page.evaluate(ents + ".filter(e => e.t === 'arc').map(e => [e.cx, e.cy, e.r])")
    assert sorted(arcs) == [[0, 0, 5], [40, 0, 5]]
    ys = page.evaluate(ents + ".filter(e => e.t === 'line' && !e.constr).map(e => [e.y1, e.y2])")
    assert sorted(ys) == [[-5, -5], [5, 5]]
    n_t = page.evaluate("window.__sk.SK.doc.constraints.filter(c => c.t === 'tangent').length")
    assert n_t == 4
    page.keyboard.press("Control+z")
    page.wait_for_function(ents + ".length === 0")
    # slot by its tips (0, 0) and (40, 0), width 10: arc centres (5, 0) and (35, 0)
    page.click("#sk-tools-draw button[data-tool=slot]")
    page.check("#skp-stips")
    page.focus("#sk-canvas")
    _typed(page, "0,0", "40,0", "10")
    page.keyboard.press("Escape")
    arcs = page.evaluate(ents + ".filter(e => e.t === 'arc').map(e => [e.cx, e.cy, e.r])")
    assert sorted(arcs) == [[5, 0, 5], [35, 0, 5]], arcs
    page.click("#sk-tools-draw button[data-tool=slot]")
    page.uncheck("#skp-stips")
    page.focus("#sk-canvas")
    page.keyboard.press("Escape")
    page.keyboard.press("Control+z")
    page.wait_for_function(ents + ".length === 0")
    # tangent arc: line (0, 0) - (20, 0), arc from its end to (30, 10), then a second arc to (40, 20)
    page.click("#sk-tools-draw button[data-tool=line]")
    _typed(page, "0,0", "20,0")
    page.keyboard.press("Escape")
    page.click("#sk-tools-draw button[data-tool=tarc]")
    _click_model(page, 20, 0)
    _typed(page, "30,10", "40,20")
    page.keyboard.press("Escape")
    arcs = page.evaluate(ents + ".filter(e => e.t === 'arc').map(e => [e.cx, e.cy, e.r])")
    assert len(arcs) == 2
    assert all(abs(a - b) < 1e-6 for a, b in zip(arcs[0], [20, 10, 10])), arcs
    assert all(abs(a - b) < 1e-6 for a, b in zip(arcs[1], [40, 10, 10])), arcs
    assert page.evaluate("window.__sk.SK.doc.constraints.filter(c => c.t === 'tangent').length") == 2
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "sketch_tangent_arc.png"))


def test_part_pick_face_of_second_solid(page):
    """Faces are picked by their triangle in the whole mesh: with solid 1 hidden, a click on solid 2 gives a face of
    solid 2 (the triangle index of the solid's own mesh is mapped to the mesh triangle)."""
    tab(page, "part")
    mesh = {"vertices": [[-10, 0, 0], [0, 0, 0], [0, 10, 0], [-10, 10, 0], [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]],
            "triangles": [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]], "face_of_tri": [0, 0, 1, 1], "face_solid": [0, 1],
            "face_keys": [{"c": [-5, 5, 0], "n": [0, 0, 1], "area": 100}, {"c": [5, 5, 0], "n": [0, 0, 1], "area": 100}],
            "face_owner": [None, None], "edges": [], "edge_keys": [], "edge_solids": [], "bbox": [-10, 0, 0, 10, 10, 0]}
    hit = page.evaluate("""m => { const P = window.__part.PT, T = window.__part.THREE;
        P.hidden = {"solid:0": true}; window.__part.setMesh(m);
        const t = P.three, r = t.renderer.domElement.getBoundingClientRect(), q = new T.Vector3(5, 5, 0).project(t.camera);
        const h = window.__part.pickAt({ clientX: r.left + (q.x + 1) / 2 * r.width, clientY: r.top + (1 - q.y) / 2 * r.height }, ["face"]);
        return h && [h.fi, h.solid]; }""", mesh)
    assert hit == [1, 1]


def test_part_import_step_clean_up(page, tmp_path):
    """Import STEP: clean-up options (rebuild and fix on for a new import); a minimum volume removes the small solid
    and the result line reports it."""
    from build123d import Box, Compound, Location, export_step
    path = str(tmp_path / "two.step")
    export_step(Compound(children=[Box(20, 10, 5), Box(1, 1, 1).moved(Location((30, 0, 0)))]), path)
    tab(page, "part")
    page.click("#tab-part [data-add=import]")
    page.wait_for_selector("#pf-crebuild")
    assert page.is_checked("#pf-crebuild") and page.is_checked("#pf-cfix") and not page.is_checked("#pf-cunify")
    page.fill("#pf-path", path)
    page.dispatch_event("#pf-path", "change")
    wait_text(page, "#pt-info", "2 cells")
    page.fill("#pf-cminvol", "10")
    page.dispatch_event("#pf-cminvol", "change")
    wait_text(page, "#pt-props", "1 solid(s) below the minimum volume removed")
    wait_text(page, "#pt-info", "Volume 1 cm^3")
    assert page.evaluate("window.__part.PT.part.features[0].clean.min_volume") == 10


def test_sketch_fillet_fixed_radius_option(page):
    """Fillet properties: Radius 6 gives R6 fillets; the setting stays for the next use of the tool; Radius from the
    click positions returns to the automatic radius."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.keyboard.press("w")
    _typed(page, "0,0", "100,60")
    page.keyboard.press("Escape")
    page.click("#tab-sketch [data-tool=fillet]")
    page.wait_for_selector("#skp-frad")
    assert page.is_checked("input[name=skp-fmode][value=auto]") and page.is_disabled("#skp-frad")
    page.check("input[name=skp-fmode][value=fixed]")
    page.fill("#skp-frad", "6")
    page.dispatch_event("#skp-frad", "change")
    wait_text(page, "#sk-hint", "radius 6")
    _click_model(page, 92, 0)
    _click_model(page, 100, 12)
    page.wait_for_function("window.__sk.SK.doc.entities.some(e => e.t === 'arc')")
    assert page.evaluate("window.__sk.SK.doc.entities.find(e => e.t === 'arc').r") == pytest.approx(6)
    page.keyboard.press("Escape")
    page.click("#tab-sketch [data-tool=fillet]")
    page.wait_for_selector("#skp-frad")
    assert page.is_checked("input[name=skp-fmode][value=fixed]") and page.input_value("#skp-frad") == "6"
    page.check("input[name=skp-fmode][value=auto]")
    wait_text(page, "#sk-hint", "radius automatic")
    page.keyboard.press("Escape")


def test_part_import_stl(page, tmp_path):
    """Import of an STL file: the STL options appear for a .stl path; the plate with a hole and a countersink gives
    planar, cylindrical and conical faces."""
    from build123d import Box, Cylinder, Cone, Pos, export_stl
    path = str(tmp_path / "plate.stl")
    export_stl(Box(60, 40, 10) - Pos(-15, 0, 0) * Cylinder(5, 10) - Pos(15, 0, 3) * Cone(2, 6, 4), path,
               tolerance=0.01, angular_tolerance=0.2)
    tab(page, "part")
    page.click("#tab-part [data-add=import]")
    page.wait_for_selector("#pf-path")
    assert page.locator("#pf-sfit").count() == 0
    page.fill("#pf-path", path)
    page.dispatch_event("#pf-path", "change")
    page.wait_for_selector("#pf-sfit")
    assert page.is_checked("#pf-sfit")
    wait_text(page, "#pt-props", "7 planar, 2 cylindrical, 2 conical")
    wait_text(page, "#pt-info", "Volume 22.99")
    page.uncheck("#pf-sfit")
    page.wait_for_function("window.__part.PT.status && Object.values(window.__part.PT.status).some(s => s.stl && s.stl.fit === false)", timeout=60000)


def test_sketch_circle_three_points(page):
    """Circle 3P through the typed points (0, 0), (100, 0) and (50, 50): centre (50, 0), radius 50."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.click("#tab-sketch [data-tool=circle3]")
    for xy in ("0,0", "100,0", "50,50"):
        page.focus("#sk-canvas")
        page.keyboard.type(xy)
        page.keyboard.press("Enter")
    page.wait_for_function("window.__sk.SK.doc.entities.some(e => e.t === 'circle')")
    c = page.evaluate("window.__sk.SK.doc.entities.find(e => e.t === 'circle')")
    assert (c["cx"], c["cy"], c["r"]) == pytest.approx((50, 0, 50), abs=1e-9)
    assert page.locator("#tab-sketch [data-tool=circle3] svg.tb-ico").count() == 1


def test_sketch_offset_conic_and_ellipse(page):
    """Offset of a conic (parabola) and an ellipse: a spline whose fit points lie at the offset distance from the
    curve; an offset larger than the radius of curvature on the concave side is refused."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.evaluate("""() => { const sk = window.__sk, SK = sk.SK;
        SK.doc.entities.push({ id: "e" + SK.doc.next_id++, t: "conic", x0: 0, y0: 0, x1: 100, y1: 0, xt: 50, yt: 50, rho: 0.5, layer: "0" });
        SK.doc.entities.push({ id: "e" + SK.doc.next_id++, t: "ellipse", cx: 200, cy: 0, rx: 40, ry: 20, rot: 0, layer: "0" });
        sk.fit(); }""")
    def click(xy):
        s = page.evaluate("(p) => window.__sk.S(p)", list(xy))
        box = page.locator("#sk-canvas svg").bounding_box()
        page.mouse.click(box["x"] + s[0], box["y"] + s[1])
    def offset(d, on, side):
        page.click("#tab-sketch [data-tool=offset]")
        page.fill("#value-dialog-input", str(d))
        page.press("#value-dialog-input", "Enter")
        page.wait_for_function("window.__sk.SK.tool === 'offset'")
        click(on)
        click(side)
    n0 = page.evaluate("window.__sk.SK.doc.entities.length")
    offset(5, (50, 25), (50, 40))                  # the parabola point (50, 25), offset to the convex side
    page.wait_for_function("window.__sk.SK.doc.entities.length === %d" % (n0 + 1))
    sp = page.evaluate("window.__sk.SK.doc.entities.slice(-1)[0]")
    assert sp["t"] == "spline" and not sp["closed"]
    def conic(t):
        a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
        return ((b * 50 + c * 100) / (a + b + c), (b * 50) / (a + b + c))
    cs = [conic(i / 4000) for i in range(4001)]
    for p in sp["pts"]:
        d = min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in cs)
        assert abs(d - 5) < 1e-3, d
    assert sp["pts"][len(sp["pts"]) // 2][1] > 25
    # parabola y = x - x^2 / 100: radius of curvature 50 mm at the vertex (50, 25)
    offset(60, (50, 25), (50, 0))
    wait_text(page, "#sk-msg", "folds over")
    assert page.evaluate("window.__sk.SK.doc.entities.length") == n0 + 1
    # ellipse: closed spline at 3 mm outside
    page.keyboard.press("Escape")
    offset(3, (240, 0), (260, 0))
    page.wait_for_function("window.__sk.SK.doc.entities.length === %d" % (n0 + 2))
    sp = page.evaluate("window.__sk.SK.doc.entities.slice(-1)[0]")
    assert sp["t"] == "spline" and sp["closed"]
    es = [(200 + 40 * math.cos(a / 2000 * 2 * math.pi), 20 * math.sin(a / 2000 * 2 * math.pi)) for a in range(2000)]
    for p in sp["pts"]:
        d = min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in es)
        assert abs(d - 3) < 3e-3, d
    assert len(sp["pts"]) <= 64


def test_sketch_convert_all_to_conics(page):
    """Convert to conics: polylines and a spline sampled from conics become conics (deviation below the tolerance);
    an S-curve (inflection) is kept. With a selection, only the selected entities are converted."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.evaluate("""() => { const sk = window.__sk, SK = sk.SK;
        const par = (x0, y0, k, n) => { const out = []; for (let i = 0; i <= n; i++) { const x = 100 * i / n; out.push([x0 + x, y0 + x * (100 - x) / 100 * k]); } return out; };
        const add = (t, props) => SK.doc.entities.push(Object.assign({ id: "e" + SK.doc.next_id++, t, layer: "0" }, props));
        add("poly", { pts: par(0, 0, 1, 40), closed: false });
        add("poly", { pts: par(0, 50, 0.5, 30), closed: false });
        add("poly", { pts: par(0, 100, 0.3, 30), closed: false });
        add("spline", { pts: par(150, 0, 1, 20), closed: false });
        const s = []; for (let i = 0; i <= 40; i++) { const x = 100 * i / 40; s.push([150 + x, 100 + 20 * Math.sin(x / 100 * 2 * Math.PI)]); }
        add("poly", { pts: s, closed: false });
        sk.fit(); sk.SK.sel.clear(); }""")
    page.click("#sk-check")
    wait_text(page, "#sk-props", "Convert 5 to conics")
    page.click("#skp-convconic")
    page.wait_for_function("window.__sk.SK.doc.entities.filter(e => e.t === 'conic').length === 4", timeout=60000)
    wait_text(page, "#sk-msg", "4 converted to conics; 1 kept")
    ts = page.evaluate("window.__sk.SK.doc.entities.map(e => e.t)")
    assert ts.count("poly") == 1 and ts.count("spline") == 0
    # selection: one of two polylines
    page.evaluate("""() => { const sk = window.__sk, SK = sk.SK;
        const pts = []; for (let i = 0; i <= 20; i++) { const x = 100 * i / 20; pts.push([x, 200 + x * (100 - x) / 100]); }
        SK.doc.entities.push({ id: "e" + SK.doc.next_id++, t: "poly", layer: "0", pts, closed: false });
        SK.doc.entities.push({ id: "e" + SK.doc.next_id++, t: "poly", layer: "0", pts: pts.map(p => [p[0], p[1] + 50]), closed: false });
        const conic = SK.doc.entities.find(e => e.t === "conic");
        SK.sel.clear(); SK.sel.add("e:" + SK.doc.entities[SK.doc.entities.length - 1].id); SK.sel.add("e:" + conic.id); sk.fit(); }""")
    page.evaluate("window.__sk.showProps()")
    wait_text(page, "#sk-props", "Convert 1 to conics")
    page.click("#skp-convconic")
    page.wait_for_function("window.__sk.SK.doc.entities.filter(e => e.t === 'conic').length === 5", timeout=60000)
    assert page.evaluate("window.__sk.SK.doc.entities.filter(e => e.t === 'poly').length") == 2
    page.focus("#sk-canvas")
    page.keyboard.press("Control+z")
    page.wait_for_function("window.__sk.SK.doc.entities.filter(e => e.t === 'conic').length === 4")


def test_sketch_fillet_automatic_radius_drag_and_dimension(page):
    """Fillet without a radius: on a 100 x 60 rectangle, clicks at (92, 0) and (100, 12) give R8 (the fillet starts at
    the click nearer to the corner); the arc dragged to another radius stays tangent and the lines stay on their
    lines (the other lines of the rectangle do not move); a radius dimension then sets R5 with the lines in place and
    its leader scaled with the radius."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.keyboard.press("w")
    page.keyboard.type("0,0")
    page.keyboard.press("Enter")
    page.keyboard.type("100,60")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    def click(xy):
        s = page.evaluate("(p) => window.__sk.S(p)", list(xy))
        box = page.locator("#sk-canvas svg").bounding_box()
        page.mouse.click(box["x"] + s[0], box["y"] + s[1])
    # zoom in about the corner (100, 0)
    s = page.evaluate("(p) => window.__sk.S(p)", [100, 0])
    box = page.locator("#sk-canvas svg").bounding_box()
    page.mouse.move(box["x"] + s[0], box["y"] + s[1])
    for _ in range(12):
        page.mouse.wheel(0, -100)
    page.wait_for_function("window.__sk.SK.view.s > 8")
    page.wait_for_timeout(300)
    page.click("#tab-sketch [data-tool=fillet]")
    assert page.is_hidden("#value-dialog")
    wait_text(page, "#sk-hint", "radius automatic")
    click((92, 0))
    click((100, 12))
    page.wait_for_function("window.__sk.SK.doc.entities.some(e => e.t === 'arc')")
    wait_text(page, "#sk-msg", "Fillet R8 (automatic)")
    arc = lambda: page.evaluate("window.__sk.SK.doc.entities.find(e => e.t === 'arc')")
    lines = lambda: page.evaluate("window.__sk.SK.doc.entities.filter(e => e.t === 'line' && !e.constr).map(e => [e.x1, e.y1, e.x2, e.y2])")
    a = arc()
    assert a["r"] == pytest.approx(8) and (a["cx"], a["cy"]) == pytest.approx((92, 8))
    before = lines()
    # drag the arc: the radius changes; the bottom and right lines stay on their lines, the others do not move
    page.keyboard.press("Escape")
    m = (92 + 8 * math.cos(math.radians(-45)), 8 + 8 * math.sin(math.radians(-45)))
    s = page.evaluate("(p) => window.__sk.S(p)", list(m))
    t = page.evaluate("(p) => window.__sk.S(p)", [m[0] - 2, m[1] + 2])
    box = page.locator("#sk-canvas svg").bounding_box()
    page.mouse.move(box["x"] + s[0], box["y"] + s[1])
    page.mouse.down()
    page.mouse.move(box["x"] + t[0], box["y"] + t[1], steps=5)
    page.mouse.up()
    a = arc()
    # the arc passes through the release point (within a screen pixel)
    q = (m[0] - 2, m[1] + 2)
    assert math.hypot(a["cx"] - q[0], a["cy"] - q[1]) == pytest.approx(a["r"], abs=0.15)
    assert a["r"] > 12
    after = lines()
    for l0, l1 in zip(before, after):
        if abs(l0[1]) < 1e-9 and abs(l0[3]) < 1e-9:          # bottom line: on y = 0, its start in place
            assert l1[1] == pytest.approx(0, abs=1e-6) and l1[3] == pytest.approx(0, abs=1e-6) and l1[0] == pytest.approx(0, abs=1e-6)
        elif abs(l0[0] - 100) < 1e-9 and abs(l0[2] - 100) < 1e-9:   # right line: on x = 100, its top end in place
            assert l1[0] == pytest.approx(100, abs=1e-6) and l1[2] == pytest.approx(100, abs=1e-6) and l1[3] == pytest.approx(60, abs=1e-6)
        else:
            assert l1 == pytest.approx(l0, abs=1e-6)
    assert (a["cy"], 100 - a["cx"]) == pytest.approx((a["r"], a["r"]), abs=1e-6)
    # radius dimension on the arc: driving, value 5
    page.click("#tab-sketch [data-tool=dim]")
    click((a["cx"] + a["r"] * math.cos(math.radians(-25)), a["cy"] + a["r"] * math.sin(math.radians(-25))))   # off the mid point grip
    click((a["cx"] - 15, a["cy"] + 15))
    page.wait_for_selector("#sk-canvas .sk-inline")
    off0 = page.evaluate("window.__sk.SK.doc.dims[0].off")
    r0 = arc()["r"]
    page.fill("#sk-canvas .sk-inline", "5")
    page.press("#sk-canvas .sk-inline", "Enter")
    page.wait_for_function("Math.abs(window.__sk.SK.doc.entities.find(e => e.t === 'arc').r - 5) < 1e-6")
    a = arc()
    assert (a["cx"], a["cy"]) == pytest.approx((95, 5), abs=1e-6)       # the lines did not move
    # the dimension leader scaled with the radius (first value)
    off1 = page.evaluate("window.__sk.SK.doc.dims[0].off")
    assert off1 == pytest.approx([v * 5 / r0 for v in off0], abs=1e-6)


def test_sketch_trim_by_sweep(page):
    """Trim with the button held: moving along y = 10 over three vertical lines removes their parts above the
    horizontal line y = 0; one undo restores them."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.evaluate("""() => { const sk = window.__sk, SK = sk.SK;
        const add = p => SK.doc.entities.push(Object.assign({ id: "e" + SK.doc.next_id++, t: "line", layer: "0" }, p));
        add({ x1: 0, y1: 0, x2: 100, y2: 0 });
        for (const x of [25, 50, 75]) add({ x1: x, y1: -20, x2: x, y2: 20 });
        sk.fit(); }""")
    page.click("#tab-sketch [data-tool=trim]")
    box = page.locator("#sk-canvas svg").bounding_box()
    sc = lambda p: page.evaluate("(p) => window.__sk.S(p)", list(p))
    s0 = sc((10, 10))
    page.mouse.move(box["x"] + s0[0], box["y"] + s0[1])
    page.mouse.down()
    for k in range(1, 41):
        q = sc((10 + 2 * k, 10))
        page.mouse.move(box["x"] + q[0], box["y"] + q[1])
    page.mouse.up()
    wait_text(page, "#sk-msg", "3 parts trimmed")
    v = page.evaluate("window.__sk.SK.doc.entities.filter(e => e.t === 'line' && Math.abs(e.x1 - e.x2) < 1e-9).map(e => Math.max(e.y1, e.y2))")
    assert sorted(v) == pytest.approx([0, 0, 0], abs=1e-9)
    page.focus("#sk-canvas")
    page.keyboard.press("Control+z")
    page.wait_for_function("window.__sk.SK.doc.entities.filter(e => e.t === 'line' && Math.abs(e.x1 - e.x2) < 1e-9 && Math.max(e.y1, e.y2) > 19).length === 3")


def test_sketch_spline_conic_end_conditions(page):
    """Spline and Conic tools: tangent (default) and G2 at a point on the end of a line or arc; end conditions in the
    properties of the curve; a conic with both ends tangent gets the tangent intersection of the two tangents."""
    tab(page, "sketch")
    page.click("#sk-new")
    sp = "window.__sk.SK.doc.entities.find(e => e.t === 'spline')"
    cons = "window.__sk.SK.doc.constraints"
    # line (0, 0) - (20, 0), spline from its end: tangent by default
    page.click("#sk-tools-draw button[data-tool=line]")
    _typed(page, "0,0", "20,0")
    page.keyboard.press("Escape")
    page.click("#sk-tools-draw button[data-tool=spline]")
    assert page.input_value("#skp-endc") == "tangent"
    page.focus("#sk-canvas")
    _click_model(page, 20, 0)
    _typed(page, "40,10", "60,0")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    r = page.evaluate("() => { const e = %s, A = cvAdapter(e); return [e.d0, A.tan(0), %s.filter(c => c.t === 'tangent' && c.e2 === e.id && c.ak2 === 's').length]; }" % (sp, cons))
    assert abs(r[0][1]) < 1e-9 and r[0][0] > 0, r
    assert abs(r[1][1]) < 1e-9 and r[2] == 1, r
    # G2 from the properties: zero curvature at the start (k0 0), the fit points unchanged
    page.evaluate("() => { const e = %s; SK.sel.clear(); SK.sel.add('e:' + e.id); showProps(); }" % sp)
    assert page.input_value("#sk-props select[data-endc=s]") == "tangent"
    page.select_option("#sk-props select[data-endc=s]", "g2")
    r = page.evaluate("""() => { const e = %s, A = cvAdapter(e), h = 1e-4;
        const p0 = A.at(h), p1 = A.at(2 * h), p2 = A.at(3 * h);
        const d1 = [(p2[0] - p0[0]) / (2 * h), (p2[1] - p0[1]) / (2 * h)], d2 = [(p0[0] - 2 * p1[0] + p2[0]) / (h * h), (p0[1] - 2 * p1[1] + p2[1]) / (h * h)];
        return [e.k0, (d1[0] * d2[1] - d1[1] * d2[0]) / Math.pow(Math.hypot(...d1), 3), e.pts, %s.filter(c => c.t === 'curvature').length]; }""" % (sp, cons))
    assert abs(r[0]) < 1e-9 and abs(r[1]) < 1e-4, r
    assert all(abs(a - b) < 1e-9 for p, q in zip(r[2], [[20, 0], [40, 10], [60, 0]]) for a, b in zip(p, q)) and r[3] == 1, r
    assert page.input_value("#sk-props select[data-endc=s]") == "g2"
    page.select_option("#sk-props select[data-endc=s]", "coincident")
    r = page.evaluate("() => { const e = %s; return [e.d0 === undefined, %s.filter(c => c.t === 'tangent' || c.t === 'curvature').length]; }" % (sp, cons))
    assert r == [True, 0], r
    # spline from the end of a tangent arc (centre (20, 10), R 10, end (30, 10)) with G2: curvature 0.1 1/mm
    page.keyboard.press("Escape")
    page.click("#sk-new")
    page.click("#sk-tools-draw button[data-tool=line]")
    _typed(page, "0,0", "20,0")
    page.keyboard.press("Escape")
    page.click("#sk-tools-draw button[data-tool=tarc]")
    _click_model(page, 20, 0)
    _typed(page, "30,10")
    page.keyboard.press("Escape")
    page.click("#sk-tools-draw button[data-tool=spline]")
    page.select_option("#skp-endc", "g2")
    page.focus("#sk-canvas")
    _click_model(page, 30, 10)
    _typed(page, "40,30", "50,30")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    r = page.evaluate("""() => { const e = %s, A = cvAdapter(e), h = 1e-4;
        const p0 = A.at(h), p1 = A.at(2 * h), p2 = A.at(3 * h);
        const d1 = [(p2[0] - p0[0]) / (2 * h), (p2[1] - p0[1]) / (2 * h)], d2 = [(p0[0] - 2 * p1[0] + p2[0]) / (h * h), (p0[1] - 2 * p1[1] + p2[1]) / (h * h)];
        return [e.k0, (d1[0] * d2[1] - d1[1] * d2[0]) / Math.pow(Math.hypot(...d1), 3), A.tan(0), %s.filter(c => c.t === 'curvature').length]; }""" % (sp, cons))
    assert abs(r[0] - 0.1) < 1e-6 and abs(r[1] - 0.1) < 1e-3, r
    assert abs(r[2][0]) < 1e-6 and r[3] == 1, r
    # conic between the ends of two lines, both tangent: tangent intersection (40, 0), then rho 0.4
    page.keyboard.press("Escape")
    page.click("#sk-new")
    page.click("#sk-tools-draw button[data-tool=line]")
    _typed(page, "0,0", "20,0")
    page.keyboard.press("Escape")
    page.click("#sk-tools-draw button[data-tool=line]")
    _typed(page, "40,20", "40,40")
    page.keyboard.press("Escape")
    page.click("#sk-tools-draw button[data-tool=conic]")
    page.select_option("#skp-endc", "tangent")
    page.focus("#sk-canvas")
    _click_model(page, 20, 0)
    _click_model(page, 40, 20)
    _typed(page, "0.4")
    page.keyboard.press("Escape")
    r = page.evaluate("() => { const e = window.__sk.SK.doc.entities.find(e => e.t === 'conic'); return [e.xt, e.yt, e.rho, %s.filter(c => c.t === 'tangent' && c.e2 === e.id).length]; }" % cons)
    assert abs(r[0] - 40) < 1e-6 and abs(r[1]) < 1e-6 and abs(r[2] - 0.4) < 1e-9 and r[3] == 2, r


def test_sketch_check_open_ends_tiny_merge_crossings(page):
    """Sketch check: open ends closed (two lines extended to meet, a line extended to another), crossings and
    T-junctions split, a tiny line removed with its neighbours joined, collinear lines and co-circular arcs merged."""
    tab(page, "sketch")
    page.click("#sk-new")
    kinds = "() => sketchCheck().map(x => x.kind)"
    # rectangle with 2 mm corner gaps and a line 3 mm short of the bottom and top edges
    page.evaluate("""() => {
        for (const [a, b, c, d] of [[0, 0, 18, 0], [20, 2, 20, 18], [18, 20, 2, 20], [0, 18, 0, 2], [10, 3, 10, 17]]) newEnt('line', { x1: a, y1: b, x2: c, y2: d });
        reindex(); changed(true); }""")
    page.click("#sk-check")
    k = page.evaluate(kinds)
    assert k.count("open") == 6, k
    assert page.locator("#sk-props button[data-fix=open]").inner_text() == "Close open ends (6)"
    page.click("#sk-props button[data-fix=open]")
    k = page.evaluate(kinds)
    assert "open" not in k and k.count("cross") == 2, k
    corners = page.evaluate("() => SK.doc.entities.filter(e => e.t === 'line').map(e => [e.x1, e.y1, e.x2, e.y2])")
    assert [0, 0, 20, 0] in corners and [20, 0, 20, 20] in corners and [20, 20, 0, 20] in corners and [0, 20, 0, 0] in corners, corners
    assert [10, 0, 10, 20] in corners, corners
    page.click("#sk-props button[data-fix=cross]")
    k = page.evaluate(kinds)
    assert k == [], k
    r = page.evaluate("() => [SK.doc.entities.filter(e => e.t === 'line').length, SK.doc.constraints.filter(c => c.t === 'coincident').length]")
    assert r[0] == 7 and r[1] >= 8, r
    # crossing of two lines: four lines joined at (10, 10)
    page.click("#sk-new")
    page.evaluate("() => { newEnt('line', { x1: 0, y1: 0, x2: 20, y2: 20 }); newEnt('line', { x1: 0, y1: 20, x2: 20, y2: 0 }); reindex(); changed(true); }")
    assert page.evaluate(kinds).count("cross") == 1
    page.evaluate("() => { fixIssues(sketchCheck().filter(x => x.kind === 'cross')); changed(true); }")
    r = page.evaluate("() => SK.doc.entities.filter(e => e.t === 'line').map(e => [e.x1, e.y1, e.x2, e.y2])")
    assert len(r) == 4 and all([10, 10] in ([a, b], [c, d]) for a, b, c, d in r), r
    # chain with a tiny line (0.05 mm) between two collinear lines: removed, then the two lines merged
    page.click("#sk-new")
    page.click("#sk-tools-draw button[data-tool=line]")
    _typed(page, "0,0", "10,0", "10.05,0", "20,0")
    page.keyboard.press("Escape")
    k = page.evaluate(kinds)
    assert k.count("tiny") == 1, k
    page.evaluate("() => { fixIssues(sketchCheck().filter(x => x.kind === 'tiny')); changed(true); }")
    k = page.evaluate(kinds)
    assert k.count("merge") == 1, k
    page.evaluate("() => { fixIssues(sketchCheck().filter(x => x.kind === 'merge')); changed(true); }")
    r = page.evaluate("() => SK.doc.entities.filter(e => e.t === 'line').map(e => [e.x1, e.y1, e.x2, e.y2])")
    assert len(r) == 1 and abs(r[0][0]) < 1e-9 and abs(r[0][2] - 20) < 1e-9, r
    # co-circular arcs 0-90 deg and 90-180 deg (R 10): one arc 0-180 deg
    page.click("#sk-new")
    page.evaluate("""() => { const a = newEnt('arc', { cx: 0, cy: 0, r: 10, a0: 0, a1: 90 }), b = newEnt('arc', { cx: 0, cy: 0, r: 10, a0: 90, a1: 180 });
        reindex(); addConstraint({ t: 'coincident', a: { e: a.id, k: 'e' }, b: { e: b.id, k: 's' } }, true); changed(true); }""")
    assert sorted(page.evaluate(kinds)) == ["merge", "open", "open"], page.evaluate(kinds)
    page.evaluate("() => { fixIssues(sketchCheck().filter(x => x.kind === 'merge')); changed(true); }")
    r = page.evaluate("() => SK.doc.entities.filter(e => e.t === 'arc').map(e => [e.a0, e.a1])")
    assert r == [[0, 180]], r


def test_sketch_three_point_rectangle_and_hv_capture(page):
    """3-pt rect.: inclined first side (DOF 5: perpendicular and two parallel constraints), horizontal first side
    (DOF 4); a line clicked 1.7 deg from horizontal gets a horizontal constraint."""
    tab(page, "sketch")
    page.click("#sk-new")
    lines = "() => SK.doc.entities.filter(e => e.t === 'line').map(e => [e.x1, e.y1, e.x2, e.y2])"
    page.click("#sk-tools-draw button[data-tool=rect3]")
    page.focus("#sk-canvas")
    _typed(page, "0,0", "30,10", "0,10")
    page.keyboard.press("Escape")
    wait_text(page, "#tab-sketch", "DOF 5")
    r = page.evaluate(lines)
    w = 10 * 30 / math.hypot(30, 10)
    assert len(r) == 4 and abs(math.hypot(r[1][2] - r[1][0], r[1][3] - r[1][1]) - w) < 1e-6, r
    ts = page.evaluate("() => SK.doc.constraints.map(c => c.t)")
    assert ts.count("perpendicular") == 1 and ts.count("parallel") == 2 and ts.count("coincident") == 4, ts
    page.click("#sk-new")
    page.click("#sk-tools-draw button[data-tool=rect3]")
    page.focus("#sk-canvas")
    _typed(page, "0,0", "40,0", "@0,15")
    page.keyboard.press("Escape")
    wait_text(page, "#tab-sketch", "DOF 4")
    r = page.evaluate(lines)
    assert [40, 0, 40, 15] in r, r
    # horizontal capture
    page.click("#sk-new")
    page.click("#sk-tools-draw button[data-tool=line]")
    _click_model(page, 0, 0)
    _click_model(page, 50, 1.5)
    page.keyboard.press("Escape")
    r = page.evaluate(lines)
    assert len(r) == 1 and abs(r[0][3] - r[0][1]) < 1e-9, r
    assert page.evaluate("() => SK.doc.constraints.filter(c => c.t === 'horizontal').length") == 1


def test_sketch_selection_filter_pick_list_and_constraint_pick(page):
    """Selection filter (Lines off: a click on a line selects nothing, a click on an end selects the point); the list
    of overlapping items after the cursor rests on two lines; Coincident with one point selected continues in the
    pick mode and the next click adds the second point without Shift."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.evaluate("""() => { for (const [a, b, c, d] of [[0, 0, 20, 0], [0, 0, 20, 0], [30, 0, 30, 10]]) newEnt('line', { x1: a, y1: b, x2: c, y2: d });
        reindex(); changed(true); fit(); }""")
    sel = "() => [...SK.sel]"
    page.click("#sk-filter-btn")
    page.uncheck("#sk-fln")
    page.click("#sk-filter-btn")
    _click_model(page, 10, 0)
    assert page.evaluate(sel) == []
    _click_model(page, 30, 10)
    assert page.evaluate(sel) == ["p:e3:p2"], page.evaluate(sel)
    page.click("#sk-filter-btn")
    page.check("#sk-fln")
    page.click("#sk-filter-btn")
    page.keyboard.press("Escape")
    # list of the two overlapping lines at (10, 0)
    s = page.evaluate("() => window.__sk.S([10, 0])")
    box = page.locator("#sk-canvas svg").bounding_box()
    page.mouse.move(box["x"] + s[0] + 1, box["y"] + s[1])
    page.mouse.move(box["x"] + s[0], box["y"] + s[1])
    page.wait_for_selector("#sk-picklist div[data-pl]")
    items = page.locator("#sk-picklist div[data-pl]").all_inner_texts()
    assert items == ["Line e1", "Line e2"] or items == ["Line e2", "Line e1"], items
    page.locator("#sk-picklist div[data-pl]").nth(1).dispatch_event("mousedown")
    assert page.evaluate(sel) == ["e:" + items[1].split()[-1]], page.evaluate(sel)
    assert page.locator("#sk-picklist").count() == 0
    # Coincident: one point selected, then the pick mode
    page.keyboard.press("Escape")
    _click_model(page, 30, 0)
    page.click("#tab-sketch [data-con=coincident]")
    assert page.evaluate("() => SK.conPick") == "coincident"
    _click_model(page, 20, 0)
    r = page.evaluate("() => [SK.doc.constraints.filter(c => c.t === 'coincident').length, SK.conPick, SK.doc.entities[2].x1, SK.doc.entities[2].y1]")
    assert r[0] == 1 and r[1] == "coincident" and abs(r[2] - 20) < 1e-6 and abs(r[3]) < 1e-6, r


def test_sketch_drag_keeps_driving_dimensions_and_collinear(page):
    """A drag of a fully constrained line (fixed start, horizontal, driving length 20 mm) leaves it in place while the
    mouse is down; Coincident on two lines makes them collinear."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.evaluate("""() => { const l = newEnt('line', { x1: 0, y1: 0, x2: 20, y2: 0 }); reindex();
        addConstraint({ t: 'fix', a: { e: l.id, k: 'p1' }, v: [0, 0] }, true); addConstraint({ t: 'horizontal', l: l.id }, true);
        SK.doc.dims.push({ id: 'd1', type: 'linear', line: l.id, orient: 'a', off: [0, 5], driving: true, value: 20 }); changed(true); fit(); }""")
    wait_text(page, "#tab-sketch", "Fully constrained")
    s = page.evaluate("() => window.__sk.S([20, 0])")
    t = page.evaluate("() => window.__sk.S([30, 6])")
    box = page.locator("#sk-canvas svg").bounding_box()
    page.mouse.move(box["x"] + s[0], box["y"] + s[1])
    page.mouse.down()
    for k in range(1, 6):
        page.mouse.move(box["x"] + s[0] + (t[0] - s[0]) * k / 5, box["y"] + s[1] + (t[1] - s[1]) * k / 5)
    r = page.evaluate("() => { const e = SK.doc.entities[0]; return [e.x2, e.y2]; }")
    page.mouse.up()
    assert abs(r[0] - 20) < 1e-6 and abs(r[1]) < 1e-6, r
    # collinear
    page.click("#sk-new")
    page.evaluate("() => { newEnt('line', { x1: 0, y1: 0, x2: 20, y2: 0 }); newEnt('line', { x1: 30, y1: 3, x2: 50, y2: 5 }); reindex(); changed(true); fit(); }")
    page.evaluate("() => { SK.sel.clear(); SK.sel.add('e:' + SK.doc.entities[0].id); SK.sel.add('e:' + SK.doc.entities[1].id); }")
    page.click("#tab-sketch [data-con=coincident]")
    r = page.evaluate("() => { const e = SK.doc.entities[1]; return [e.y1, e.y2, SK.doc.constraints.filter(c => c.t === 'pointon').length]; }")
    assert abs(r[0]) < 1e-6 and abs(r[1]) < 1e-6 and r[2] == 2, r


def test_sketch_constrained_colour_closed_profile_marks(page):
    """Under-constrained geometry blue, fully constrained geometry in its colour and the green Fully constrained
    badge; a closed triangle filled, the open ends of a line marked red; a dimension change keeps the view."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.evaluate("""() => { for (const [a, b, c, d] of [[0, 0, 40, 0], [40, 0, 40, 30], [40, 30, 0, 0], [60, 0, 90, 0]]) newEnt('line', { x1: a, y1: b, x2: c, y2: d });
        reindex(); const L = SK.doc.entities;
        for (let i = 0; i < 3; i++) addConstraint({ t: 'coincident', a: { e: L[i].id, k: 'p2' }, b: { e: L[(i + 1) % 3].id, k: 'p1' } }, true);
        changed(true); fit(); }""")
    page.wait_for_selector("#sk-geo path.sk-loops")
    assert page.locator("#sk-geo circle.sk-open").count() == 2
    assert page.evaluate("() => [...SK.under].length") == 4
    assert page.locator("#sk-dof.dof-under").count() == 1
    # fix the line (60, 0) - (90, 0): it is drawn in its layer colour, the triangle stays blue
    page.evaluate("() => { const l = SK.doc.entities[3]; addConstraint({ t: 'fix', e: l.id, vals: entVals(l) }, true); changed(true); }")
    assert page.evaluate("() => [...SK.under].sort()") == page.evaluate("() => SK.doc.entities.slice(0, 3).map(e => e.id).sort()")
    # fully constrained triangle: fixed start, horizontal base, vertical side, driving lengths
    page.evaluate("""() => { const L = SK.doc.entities;
        addConstraint({ t: 'fix', a: { e: L[0].id, k: 'p1' }, v: [0, 0] }, true); addConstraint({ t: 'horizontal', l: L[0].id }, true); addConstraint({ t: 'vertical', l: L[1].id }, true);
        SK.doc.dims.push({ id: 'd1', type: 'linear', line: L[0].id, orient: 'a', off: [0, -5], driving: true, value: 40 }, { id: 'd2', type: 'linear', line: L[1].id, orient: 'a', off: [5, 0], driving: true, value: 30 });
        changed(true); }""")
    wait_text(page, "#tab-sketch", "Fully constrained")
    assert page.locator("#sk-dof.dof-ok").count() == 1 and page.evaluate("() => SK.under.size") == 0
    # a dimension change keeps the view
    v0 = page.evaluate("() => [SK.view.s, SK.view.ox, SK.view.oy]")
    page.evaluate("() => window.__sk.setDimValue(SK.doc.dims[0], 4)")
    assert page.evaluate("() => [SK.view.s, SK.view.ox, SK.view.oy]") == v0
    assert abs(page.evaluate("() => SK.doc.entities[0].x2") - 4) < 1e-6


def test_part_pattern_bodies_pick(page, client):
    """Pattern: Pick bodies, a click on the solid adds it; the copies are new solids."""
    client.put("/api/part/file/ui_patb", json=plate("ui_patb"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_patb')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    page.evaluate("() => window.__part.startCommand('pattern')")
    page.wait_for_selector("#tab-part button[data-pick=bodies]")
    page.click("#tab-part button[data-pick=bodies]")
    time.sleep(0.5)
    xy = page.evaluate("""() => { const P = window.__part, t = P.PT.three, r = t.renderer.domElement.getBoundingClientRect();
        for (let i = 0; i < 900; i++) { const sx = r.left + r.width * (0.05 + 0.9 * (i % 30) / 30), sy = r.top + r.height * (0.05 + 0.9 * Math.floor(i / 30) / 30);
          const h = P.pickAt({ clientX: sx, clientY: sy }, ['body']); if (h && h.kind === 'body' && document.elementFromPoint(sx, sy) === t.renderer.domElement) return [sx, sy]; } return null; }""")
    assert xy
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const P = window.__part; return JSON.stringify(P.feat(P.PT.cmd.id).bodies) === '[{\"solid\":0}]'; })()")
    page.click("#pt-cmdfinish")
    page.wait_for_function("window.__part.PT.solids.length === 3", timeout=60000)


def test_part_cut_bodies_step(page, client):
    """Cut: the Bodies step lists the solids before the cut; a click on a solid adds it, and the cut changes only
    that solid."""
    def rect(x0, y0, x1, y1):
        return [{"id": "e%d" % i, "t": "line", "layer": "0", "x1": a, "y1": b, "x2": c, "y2": d}
                for i, (a, b, c, d) in enumerate([(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)])]
    p = {"name": "ui_cutb", "features": [
        {"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": rect(0, 0, 20, 10)}, "depth": 5},
        {"id": "f2", "name": "Extrude 2", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": rect(30, 0, 50, 10)}, "depth": 5, "new_body": True},
        {"id": "f3", "name": "Cut 1", "type": "cut", "plane": "XZ", "offset": 0, "sketch": {"entities": rect(-10, 3, 60, 7)}, "through": True}]}
    client.put("/api/part/file/ui_cutb", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_cutb')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.solids.length === 2")
    vols = page.evaluate("() => window.__part.PT.solids.map(s => Math.round(s.volume_mm3))")
    assert sorted(vols) == [600, 600], vols
    page.evaluate("""() => { const P = window.__part, f = P.PT.part.features.find(x => x.type === 'cut'); P.startCommand('cut', null, f.id);
        P.gotoStep(P.commandSteps(f).length - 1); }""")
    page.wait_for_selector("#tab-part input[data-pbs]")
    assert page.locator("#tab-part input[data-pbs]").count() == 2
    page.check("#tab-part input[data-pbs='1']")
    page.click("#pt-cmdfinish")
    page.wait_for_function("window.__part.PT.mesh && !window.__part.PT.cmd && window.__part.PT.solids.length === 2 && window.__part.PT.solids.some(s => Math.round(s.volume_mm3) === 1000)", timeout=60000)


def test_project_move_document_dialog(page, client, web):
    """Project tab: Move… on a part opens the dialog; Move puts the part in the other project."""
    import os
    client.post("/api/projects", json={"name": "ui_other", "description": "", "open": False})
    client.put("/api/part/file/ui_mv", json=plate("ui_mv"))
    tab(page, "project")
    page.wait_for_selector("#pj-docs tr[data-name='ui_mv'] button[data-op=move]", timeout=10000)
    page.click("#pj-docs tr[data-name='ui_mv'] button[data-op=move]")
    page.wait_for_selector("#pj-mdialog:not([hidden])")
    page.select_option("#pj-mtarget", "ui_other")
    page.click("#pj-mgo")
    page.wait_for_selector("#pj-mdialog[hidden]", state="attached")
    dst = web.PROJECTS.project_dir("ui_other")
    page.wait_for_function("() => !document.querySelector(\"#pj-docs tr[data-name='ui_mv']\")")
    assert os.path.isfile(os.path.join(dst, "work", "ui_mv.part.json"))


def test_sketch_check_fixed_geometry_and_speed(page):
    """Check on a sketch with 150 fixed lines joined end to end (as included edges) and two free touching lines:
    the fixed joints are not listed as missing constraints, the free joint is fixed, and the fix takes under 5 s."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.evaluate("""() => { for (let i = 0; i < 150; i++) { const l = newEnt('line', { x1: i * 2, y1: (i % 2) * 3, x2: (i + 1) * 2, y2: ((i + 1) % 2) * 3 });
          SK.doc.constraints.push({ id: 'cf' + i, t: 'fix', e: l.id, vals: entVals(l) }); }
        newEnt('line', { x1: 0, y1: 50, x2: 20, y2: 50 }); newEnt('line', { x1: 20, y1: 50, x2: 20, y2: 70 });
        reindex(); changed(true); fit(); }""")
    k = page.evaluate("() => sketchCheck().map(x => x.kind)")
    assert k.count("nocoincident") == 1 and "notangent" not in k, k
    t = page.evaluate("() => { const t0 = performance.now(); const n = fixIssues(sketchCheck().filter(x => x.kind === 'nocoincident')); changed(true); return [n, performance.now() - t0]; }")
    assert t[0] == 1 and t[1] < 5000, t
    assert "nocoincident" not in page.evaluate("() => sketchCheck().map(x => x.kind)")


def test_sketch_check_failed_fix_marked(page):
    """A tiny line between two fixed lines that are not collinear: the fix is not offered (neighbours fixed); a tiny
    line between free lines held by a conflicting dimension: the failed fix is marked and the button disappears."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.evaluate("""() => { const a = newEnt('line', { x1: 0, y1: 0, x2: 10, y2: 0 }), t = newEnt('line', { x1: 10, y1: 0, x2: 10.05, y2: 0.02 }), b = newEnt('line', { x1: 10.05, y1: 0.02, x2: 20, y2: 5 });
        reindex();
        for (const l of [a, b]) SK.doc.constraints.push({ id: 'f' + l.id, t: 'fix', e: l.id, vals: entVals(l) });
        changed(true); }""")
    x = page.evaluate("() => sketchCheck().filter(x => x.kind === 'tiny').map(x => [x.text, fixKind(x)])")
    assert len(x) == 1 and "(neighbours fixed)" in x[0][0] and x[0][1] is None, x
    # free neighbours, but each with a fixed start and a driving length: joining them is impossible
    page.click("#sk-new")
    page.evaluate("""() => { const a = newEnt('line', { x1: 0, y1: 0, x2: 10, y2: 0 }), t = newEnt('line', { x1: 10, y1: 0, x2: 10.05, y2: 0 }), b = newEnt('line', { x1: 10.05, y1: 0, x2: 20, y2: 0 });
        reindex();
        addConstraint({ t: 'fix', a: { e: a.id, k: 'p1' }, v: [0, 0] }, true); addConstraint({ t: 'fix', a: { e: b.id, k: 'p2' }, v: [20, 0] }, true);
        SK.doc.dims.push({ id: 'd1', type: 'linear', line: a.id, orient: 'a', off: [0, 3], driving: true, value: 10 }, { id: 'd2', type: 'linear', line: b.id, orient: 'a', off: [0, 3], driving: true, value: 9.95 });
        changed(true); }""")
    page.click("#sk-check")
    page.wait_for_selector("#sk-props button[data-fix=tiny]")
    page.click("#sk-props button[data-fix=tiny]")
    wait_text(page, "#sk-props", "fix not possible")
    assert page.locator("#sk-props button[data-fix=tiny]").count() == 0


def test_project_sort_columns_and_recent_folder(page, client, web, tmp_path):
    """Project tab: a click on Size sorts largest first, a second click reverses; choosing a recent projects folder
    sets it and opens the project last opened there."""
    root0, cur0 = web.PROJECTS.root(), web.PROJECTS.current_name()
    client.put("/api/part/file/ui_sort_small", json=plate("ui_sort_small"))
    big = plate("ui_sort_big")
    big["note_pad"] = "x" * 20000
    client.put("/api/part/file/ui_sort_big", json=big)
    other = str(tmp_path / "recent_root")
    try:
        client.put("/api/projects/root", json={"path": other})
        client.post("/api/projects", json={"name": "rec_pj", "description": "", "open": True})
        client.put("/api/projects/root", json={"path": root0})
        client.post("/api/projects/open", json={"name": cur0})
        tab(page, "project")
        page.wait_for_selector("#pj-docs th[data-sort=size]")
        page.click("#pj-docs th[data-sort=size]")
        names = page.evaluate("() => [...document.querySelectorAll('#pj-docs tr[data-name]')].map(r => r.dataset.name)")
        assert names.index("ui_sort_big") < names.index("ui_sort_small")
        page.click("#pj-docs th[data-sort=size]")
        names = page.evaluate("() => [...document.querySelectorAll('#pj-docs tr[data-name]')].map(r => r.dataset.name)")
        assert names.index("ui_sort_big") > names.index("ui_sort_small")
        assert "▲" in page.inner_text("#pj-docs th[data-sort=size]")
        # recent folder
        idx = page.evaluate("(p) => window.projectInfo().recent_roots.findIndex(r => r.path === p)", other)
        assert idx >= 0
        page.select_option("#pj-recent", str(idx))
        wait_text(page, "#pj-title", "rec_pj")
        assert web.PROJECTS.current_name() == "rec_pj"
    finally:
        web.PROJECTS.set_root(root0)
        web.PROJECTS.open(cur0)
        page.evaluate("() => window.projectShown && window.projectShown()")


def test_project_all_projects_find_and_open(page, client, web, tmp_path):
    """Project tab, All projects: Find projects lists the projects in the subfolders of a folder; Open opens one in
    another folder; × removes it from the list."""
    root0, cur0 = web.PROJECTS.root(), web.PROJECTS.current_name()
    base = tmp_path / "find_base"
    d = base / "x" / "found_pj"
    (d / "work").mkdir(parents=True)
    (d / "project.json").write_text(json.dumps({"name": "found_pj", "description": "old one"}), encoding="utf-8")
    try:
        tab(page, "project")
        page.fill("#pj-scanpath", str(base))
        page.click("#pj-scan")
        page.wait_for_selector("#pj-all tr:has-text('found_pj') button[data-aop=open]")
        page.click("#pj-all tr:has-text('found_pj') button[data-aop=open]")
        wait_text(page, "#pj-title", "found_pj")
        assert web.PROJECTS.current_name() == "found_pj"
        assert os.path.normcase(web.PROJECTS.root()) == os.path.normcase(str(base / "x"))
        page.fill("#pj-allfilter", "old one")
        assert page.locator("#pj-all tr.pj-cur").count() == 1
        web.PROJECTS.set_root(root0)
        web.PROJECTS.open(cur0)
        page.evaluate("() => window.projectShown && window.projectShown()")
        page.wait_for_selector("#pj-all tr:has-text('found_pj') button[data-aop=forget]")
        page.click("#pj-all tr:has-text('found_pj') button[data-aop=forget]")
        page.wait_for_function("() => !document.querySelector('#pj-all').textContent.includes('found_pj')")
    finally:
        page.fill("#pj-allfilter", "")
        web.PROJECTS.set_root(root0)
        web.PROJECTS.open(cur0)
        web.PROJECTS.forget(str(d))
        page.evaluate("() => window.projectShown && window.projectShown()")


def test_document_file_opened_from_url_and_file_column(page, client, web, server_url, tmp_path):
    """/?open=<file> (run.py --open, a double-click in Explorer) opens the document in its tab; the File menu has
    Open file… and Save as file…; the Documents list shows the linked file."""
    client.put("/api/part/file/ui_pkg", json=plate("ui_pkg"))
    f = str(tmp_path / "ui_loose.scpart")
    try:
        r = client.post("/api/file/saveas", json={"type": "part", "name": "ui_pkg", "path": f})
        assert r.status_code == 200, r.get_data(as_text=True)
        from urllib.parse import quote
        page.goto(server_url + "/?open=" + quote(f))
        page.wait_for_function("window.__partCurrent && (window.__partCurrent() || {}).name === 'ui_pkg'", timeout=30000)
        wait_text(page, "#status", "Opened")
        assert not page.is_hidden("#tab-part") and "open=" not in page.url
        file_menu(page, "#tab-part")
        assert page.is_visible("#pt-openfile") and page.is_visible("#pt-savefile")
        tab(page, "project")
        page.wait_for_selector("#pj-docs tr[data-name=ui_pkg] .pj-linked", state="attached")
        assert "ui_loose.scpart" in page.inner_text("#pj-docs tr[data-name=ui_pkg] .pj-linked")
    finally:
        client.post("/api/file/unlink", json={"type": "part", "name": "ui_pkg"})
        client.post("/api/project/doc", json={"op": "delete", "type": "part", "name": "ui_pkg"})


def test_command_search_finds_stl_import(page):
    """Ctrl+K opens the command search; "stl" lists Import STEP of the Part tab first; Enter starts it in the Part
    tab; Esc closes the window."""
    tab(page, "project")
    page.keyboard.press("Control+k")
    page.wait_for_selector("#cmd-search:not([hidden]) #cs-input")
    page.fill("#cs-input", "stl")
    first = page.locator("#cs-list .cs-item").first
    assert first.locator("b").inner_text() == "Import STEP" and "Part" in first.inner_text()
    page.keyboard.press("Enter")
    assert page.is_hidden("#cmd-search")
    assert not page.is_hidden("#tab-part")
    page.wait_for_function("(() => { const P = window.__part; return P.PT.cmd && P.feat(P.PT.cmd.id).type === 'import'; })()")
    page.evaluate("window.__part.cancelCommand()")
    page.click("#cs-open")
    page.fill("#cs-input", "fillet")
    assert page.locator("#cs-list .cs-item").count() >= 1
    page.keyboard.press("Escape")
    assert page.is_hidden("#cmd-search")
