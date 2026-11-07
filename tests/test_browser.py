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
    client.put("/api/part/last", json={"clear": True})     # Part command settings of earlier tests not kept
    pg.goto(server_url + "/")
    pg.wait_for_load_state("networkidle")
    pg.wait_for_function("window.__part && window.__asm && window.projectInfo && window.projectInfo()")
    yield pg
    pg.close()
    assert not errors, "\n".join(errors)


def tab(pg, name):
    if name == "xp":                # the explicit pane of the Analysis tab (solver OpenCourant), with its own document
        pg.evaluate("showTab('xp')")
        time.sleep(0.3)
        return
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
    page.click("#cmd-finish")
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
    page.click("#cmd-finish")
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


def test_analysis_run_monitor(page, client):
    """Run monitor of a nonlinear solve (block pressed onto a block, contact and plastic material): while the solver
    runs, Results shows the stage, the process, the convergence plot of job.cvg and the solver output; after the
    solve the Run block gives the convergence plot and the folded solver output ending with Job finished. A solve
    that fails (no support: singular matrix) keeps the run monitor with the solver output."""
    from test_analysis import CCX, _stack
    if CCX is None:
        pytest.skip("CalculiX (ccx) not found")
    from drawgen import web
    asm, F = _stack(client, web, "mon")
    client.put("/api/assembly/file/mon_asm", json=asm)
    mats = {"Soft": {"E": 210000.0, "nu": 0.3, "rho": 7850.0, "law": "plastic", "plastic": [[100.0, 0.0], [200.0, 0.1]]}}
    doc = {"name": "fea_mon", "source": {"type": "assembly", "name": "mon_asm"}, "materials": mats, "default_material": "Soft",
           "mesh": {"size": 4}, "bonded": True, "bodies": {}, "members": [], "plates": [], "fasteners": [], "loads": [],
           "supports": [{"id": "s1", "name": "base", "target": F["lo_bot"], "type": "fixed"},
                        {"id": "s2", "name": "press", "target": F["hi_top"], "type": "displacement", "dofs": [1, 1, 1, 0, 0, 0], "value": [0, 0, -0.05, 0, 0, 0]}],
           "contacts": [{"id": "c1", "name": "seat", "type": "surface", "master": [F["lo_top"]], "slave": [F["hi_bot"]], "friction": 0.2}],
           "nonlinear": {"inc0": 0.25, "incmax": 0.25}}
    client.put("/api/analysis/file/fea_mon", json=doc)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("window.__feaLoadNamed('fea_mon')")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    page.click("#fa-solve")
    page.wait_for_selector("#fr-live", timeout=300000)
    page.wait_for_selector("#fr-lvcvg .fr-cvgplot svg", timeout=300000)
    assert "Run monitor" in page.text_content("#fr-lvhead") and "elapsed" in page.text_content("#fr-lvproc")
    assert "increment" in page.text_content("#fr-lvstage")
    assert page.locator("#fr-lvlog .fr-log").count() == 1 and page.is_checked("#fr-lvlog .fr-logfollow")
    page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.tables", timeout=300000)
    wait_text(page, "#fa-results", "Run")
    assert page.locator("#fr-runcvg .fr-cvgplot svg").count() == 1
    assert "Job finished" in page.text_content("#fr-runlog .fr-log") and "thread(s)" in page.text_content("#fa-results")
    assert page.evaluate("window.__fea.FA.res.run.stages.at(-1).name") == "Finished"
    # the convergence curves chosen
    page.uncheck("#fr-runcvg [data-cvs='displacement correction']")
    assert page.evaluate("window.__fea.FA.cvgOn") == ["residual force"]
    # a failed solve keeps the monitor with the output (a stand-in ccx that writes an error and exits)
    import sys
    import tempfile
    d = tempfile.mkdtemp(prefix="fake_ccx_")
    if os.name == "nt":
        exe = os.path.join(d, "ccx.cmd")
        open(exe, "w").write('@echo  Decascading the MPC\'s\r\n@echo  *ERROR in test: the solver stopped\r\n@exit /b 1\r\n')
    else:
        exe = os.path.join(d, "ccx")
        open(exe, "w").write("#!/bin/sh\necho \" Decascading the MPC's\"\necho \" *ERROR in test: the solver stopped\"\nexit 1\n")
        os.chmod(exe, 0o755)
    client.put("/api/analysis/solver", json={"path": exe})
    try:
        page.click("#fa-solve")
        page.wait_for_function("window.__fea.FA.liveFailed === true", timeout=300000)
        assert "stopped with an error" in page.text_content("#fr-lvhead")
        assert "*ERROR in test" in page.text_content("#fr-lvlog .fr-log") and page.evaluate("window.__fea.FA.live.stage") == "Stopped"
        assert page.evaluate("window.__fea.FA.live.stages.at(-1).name") == "Stopped"
    finally:
        client.put("/api/analysis/solver", json={"path": ""})


def test_analysis_inp_source(page, client, tmp_path):
    """Geometry = Import CalculiX .inp: a component per element set, the materials, the shell section (t 2 mm) and the
    *NSET node sets of the file in the document; the node set rows name the *NSET. With CalculiX: supports on the
    node sets and a force on the end face of the bar solve. The Input file page: the contents of the file (element
    types, quality, element sets, materials, keywords), a section opened, the report downloaded; the search of nodes by
    number and elements of a set with the marks in the view, a row highlighted; elements selected in the view
    (restricted to the set of the filter, Shift+click adds)."""
    from test_analysis import CCX, write_test_inp
    p = write_test_inp(str(tmp_path / "ui.inp"))
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#fa-source", "inp:")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    d = page.evaluate("window.__fea.FA.doc")
    assert d["source"]["type"] == "inp" and d["source"]["name"] == "ui.inp" and d["materials"]["STEEL"]["E"] == 210000
    assert sorted(n["set"] for n in d["nsets"] if n["kind"] == "inp") == ["FIX", "PFIX"]
    sec = [x for x in d["sections"] if any(r["comp"] == "PLATE" for r in x["faces"])]
    assert len(sec) == 1 and float(sec[0]["t"]) == 2.0
    assert page.input_value("#fa-source") == "inp:" + p
    wait_text(page, "#fa-info", "132 nodes, 60 elements")
    wait_text(page, "#fa-nsets", "*NSET FIX of the .inp")
    # Input file page: the contents of the file
    page.click("#fa-tree [data-tp=inpfile]")
    wait_text(page, "#fa-inpfile", "Element types (2)")
    for t in ("C3D8", "linear hexahedron solid, 8 nodes", "Mesh quality", "BEAM", "STEEL", "*SHELL SECTION"):
        assert t in page.text_content("#fa-inpfile"), t
    page.click("#fa-inpfile [data-ii=kws] summary")
    assert page.evaluate("document.querySelector('#fa-inpfile [data-ii=kws]').open")
    with page.expect_download() as dl:
        page.click("#fa-inpfile [data-iiop=download]")
    assert "INPUT FILE: ui.inp" in open(dl.value.path()).read()
    # search: node 1 (row, mark in the view), elements of set PLATE (rows, element edges marked), a row marks one element
    page.fill("#fa-inpfile [data-qk=numbers]", "1, 99")
    page.click("#fa-inpfile [data-qop=go]")
    wait_text(page, "#fa-inpfile .ii-res", "FIX")
    assert page.locator("#fa-inpfile .ii-res tr[data-qrow]").count() == 2
    assert page.evaluate("window.__fea.FA.queryMarks.points.length") == 2
    assert page.evaluate("window.__fea.FA.three.group.children.some(o => o.userData && o.userData.kind === 'query')")
    page.select_option("#fa-inpfile [data-qk=what]", "elements")
    page.select_option("#fa-inpfile [data-qk=by]", "set")
    page.select_option("#fa-inpfile [data-qk=set]", "PLATE")
    page.click("#fa-inpfile [data-qop=go]")
    wait_text(page, "#fa-inpfile .ii-query", "20 element(s) found")
    assert page.evaluate("window.__fea.FA.queryMarks.lines.length") == 80
    page.click("#fa-inpfile .ii-res tr[data-qrow='3']")
    qm = page.evaluate("window.__fea.FA.queryMarks")
    assert len(qm["lines"]) == 80 and len(qm["focusLines"]) == 4 and len(qm["focusTris"]) == 18 and qm["focus"]
    assert page.locator("#fa-inpfile .ii-res tr.sel").count() == 1
    page.click("#fa-inpfile .ii-res tr[data-qrow='3']")                     # a second click removes the highlight
    assert not page.evaluate("window.__fea.FA.queryMarks.focus") and page.locator("#fa-inpfile .ii-res tr.sel").count() == 0
    # Select in view (elements of set PLATE): a click on the strip, Shift+click adds a second element, Esc stops
    scr = ("(p) => { const T = window.__fea.FA.three, r = T.renderer.domElement.getBoundingClientRect();"
           " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")
    page.click("#fa-inpfile [data-qop=sel]")
    wait_text(page, "#fa-inpfile .ii-query", "Click an element in the view (set PLATE)")
    page.mouse.click(*page.evaluate(scr, [52, 3, 20]))
    wait_text(page, "#fa-inpfile .ii-query", "1 element(s) found")
    r0 = page.evaluate("window.__fea.FA.doc && document.querySelector('#fa-inpfile .ii-res tr[data-qrow]').cells[1].textContent")
    assert r0 == "S4" and page.evaluate("window.__fea.FA.queryMarks.focusTris.length") == 18
    page.keyboard.down("Shift")
    page.mouse.click(*page.evaluate(scr, [77, 7, 20]))
    page.keyboard.up("Shift")
    wait_text(page, "#fa-inpfile .ii-query", "2 element(s) found")
    assert page.locator("#fa-inpfile .ii-res tr.sel").count() == 1 and page.evaluate("window.__fea.FA.queryMarks.lines.length") == 8
    page.keyboard.press("Escape")
    wait_text(page, "#fa-inpfile .ii-query", "Select in view")
    page.click("#fa-inpfile [data-qop=clear]")
    assert page.evaluate("window.__fea.FA.queryMarks") is None
    # near a point picked in the view: the corner (100, 10, 10) of the bar
    page.select_option("#fa-inpfile [data-qk=what]", "nodes")
    page.select_option("#fa-inpfile [data-qk=by]", "near")
    page.click("#fa-inpfile [data-qop=pick]")
    xy = page.evaluate("(p) => { const T = window.__fea.FA.three, r = T.renderer.domElement.getBoundingClientRect();"
                       " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
                       " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }", [100, 10, 10])
    page.mouse.click(*xy)
    page.wait_for_function("+document.querySelector('#fa-inpfile [data-qk=px]').value === 100")
    page.click("#fa-inpfile [data-qop=go]")
    wait_text(page, "#fa-inpfile .ii-query", "1 node(s) found")
    assert page.locator("#fa-inpfile .ii-res td").first.inner_text() == "99"
    page.click("#fa-tree [data-tp=all]")
    if CCX is None:
        return
    page.evaluate("""() => { const FA = window.__fea.FA, d = FA.doc, c = FA.geo.components.find(x => x.id === 'BEAM');
        const end = c.refs.findIndex(r => Math.abs(r.c[0] - 100) < 1e-6);
        d.supports = d.nsets.filter(n => n.kind === 'inp').map((n, i) => ({id: 'si' + i, name: n.name, target: {nset: n.id}, type: 'fixed'}));
        d.loads = [{id: 'l1', name: 'tip', type: 'force', target: {comp: 'BEAM', face: end}, value: [0, 0, -100]}]; }""")
    page.click("#fa-solve")
    page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.tables", timeout=300000)
    assert page.evaluate("window.__fea.FA.res.tables.total.applied[2]") == pytest.approx(-100, abs=1e-6)


def test_inp_file_curves(page, client, tmp_path):
    """Input file page of an .inp with a *PLASTIC table and an *AMPLITUDE: the section of the curves plots the
    hardening curve (true stress against true plastic strain) and the amplitude (factor against step time); File text
    (lines loaded while scrolled, Find, a keyword of Keywords, the line of an element of the search)."""
    from test_analysis import write_test_inp
    p = write_test_inp(str(tmp_path / "cv.inp"))
    text = open(p).read().replace("*DENSITY", "*PLASTIC\n250, 0\n300, 0.1\n*DENSITY", 1).replace("*STEP", "*AMPLITUDE, NAME=RAMP\n0, 0, 1, 1\n*STEP", 1)
    open(p, "w").write(text)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#fa-source", "inp:")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    page.click("#fa-tree [data-tp=inpfile]")
    wait_text(page, "#fa-inpfile", "Material curves, amplitudes, functions (2)")
    page.click("#fa-inpfile [data-ii=curves] summary")
    page.wait_for_selector("#fa-inpfile .ii-mc svg polyline")
    assert "STEEL" in page.text_content("#fa-inpfile .ii-mc") and "true plastic strain" in page.text_content("#fa-inpfile .ii-mc")
    assert page.locator("#fa-inpfile .ii-ac svg polyline").count() == 1 and "step time (s)" in page.text_content("#fa-inpfile .ii-ac")
    # File text: the first 300 lines, more loaded when scrolled to the end; Find; a keyword of Keywords; the line of a
    # search row
    n = len(text.splitlines())
    page.click("#fa-inpfile [data-ii=text] summary")
    page.wait_for_selector("#fa-inpfile .ii-src tr[data-ln='1']")
    assert page.locator("#fa-inpfile .ii-src tr").count() == min(300, n) and page.text_content("#fa-inpfile .ii-src tr[data-ln='1']") == "1*HEADING"
    page.evaluate("() => { const s = document.querySelector('#fa-inpfile .ii-src'); s.scrollTop = s.scrollHeight; s.dispatchEvent(new Event('scroll')); }")
    page.wait_for_function("document.querySelectorAll('#fa-inpfile .ii-src tr').length === %d" % min(500, n))
    page.fill("#fa-inpfile [data-tx=find]", "*SHELL SECTION")
    page.click("#fa-inpfile [data-tx=next]")
    page.wait_for_selector("#fa-inpfile .ii-src tr.hl")
    hl = page.text_content("#fa-inpfile .ii-src tr.hl")
    assert "*SHELL SECTION, ELSET=PLATE" in hl and page.input_value("#fa-inpfile [data-tx=line]") == hl.split("*")[0]
    page.click("#fa-inpfile [data-ii=kws] summary")
    page.click("#fa-inpfile a.ii-kw[data-kw='*MATERIAL']")
    page.wait_for_function("(document.querySelector('#fa-inpfile .ii-src tr.hl') || {}).textContent?.includes('*MATERIAL, NAME=STEEL')")
    page.select_option("#fa-inpfile [data-qk=what]", "elements")
    page.fill("#fa-inpfile [data-qk=numbers]", "41")
    page.click("#fa-inpfile [data-qop=go]")
    wait_text(page, "#fa-inpfile .ii-query", "1 element(s) found")
    page.click("#fa-inpfile [data-qline='0']")
    page.wait_for_function("(document.querySelector('#fa-inpfile .ii-src tr.hl td:last-child') || {}).textContent?.startsWith('41, 1001,')")


def test_inp_import_steps_ui(page, client, tmp_path):
    """Import of an .inp with a step: the *BOUNDARY as a support on the node set of the file, the *CLOAD as a force
    (value x nodes), NLGEOM, the increments and the *CONTROLS in Settings; the note of what was read on the Input file
    page; the load arrow at the centre of the node set."""
    from test_analysis import write_test_inp
    p = write_test_inp(str(tmp_path / "stp.inp"))
    text = open(p).read().replace("*STEP\n*STATIC\n*BOUNDARY\nFIX, 1, 3\n*END STEP\n",
        "*STEP, NLGEOM, INC=40\n*STATIC\n0.25, 1, 1e-5, 1\n*CONTROLS, PARAMETERS=TIME INCREMENTATION\n, , , 30\n"
        "** Name: Root\n*BOUNDARY\nFIX, 1, 3\n** Name: Push\n*CLOAD\nPFIX, 3, -2\n*NODE PRINT, NSET=FIX\nRF\n*END STEP\n")
    open(p, "w").write(text)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#fa-source", "inp:")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2 && window.__fea.FA.doc.supports.length")
    d = page.evaluate("window.__fea.FA.doc")
    ns = {n["id"]: n["set"] for n in d["nsets"]}
    assert [(s["name"], ns[s["target"]["nset"]], s["type"], s["dofs"]) for s in d["supports"]] == [("Root", "FIX", "dofs", [1, 1, 1, 0, 0, 0])]
    assert [(l["name"], ns[l["target"]["nset"]], l["value"]) for l in d["loads"]] == [("Push", "PFIX", [0, 0, -6])]
    nl = d["nonlinear"]
    assert nl["nlgeom"] and nl["maxinc"] == 40 and nl["inc0"] == 0.25 and nl["controls"] == "*CONTROLS, PARAMETERS=TIME INCREMENTATION\n, , , 30"
    page.click("#fa-tree [data-tp=settings]")
    assert page.input_value("#fs-controls").startswith("*CONTROLS, PARAMETERS=TIME INCREMENTATION")
    page.click("#fa-tree [data-tp=inpfile]")
    wait_text(page, "#fa-inpimport", "Read from the file: 1 support(s), 1 load(s), one static step with NLGEOM")
    assert "*NODE PRINT" in page.text_content("#fa-inpimport")
    arrows = "(() => { let n = 0; window.__fea.FA.three.group.traverse(o => { if (o.type === 'ArrowHelper' && o.userData.kind === 'load') n++; }); return n; })()"
    page.wait_for_function(arrows + " > 0")
    page.click("#fa-tree [data-tp=settings]")
    page.fill("#fs-controls", "*BOUNDARY\n1, 1")
    page.dispatch_event("#fs-controls", "change")
    assert page.evaluate("window.__fea.FA.doc.nonlinear.controls").startswith("*CONTROLS")


def test_explicit_inp_source(page, client, tmp_path):
    """Explicit Geometry = Import CalculiX .inp: the bodies, materials, shell section and *NSET node sets of the file
    in the document; Mesh writes the model .inp from the elements of the file; a node selected in the view on the
    Input file page."""
    from test_analysis import write_test_inp
    p = write_test_inp(str(tmp_path / "xui.inp"))
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#xp-source", "inp:")
    page.wait_for_function("window.__xp.XP.geo && window.__xp.XP.geo.components.length === 2")
    d = page.evaluate("window.__xp.XP.doc")
    assert d["source"]["type"] == "inp" and d["source"]["kind"] == "shinycad" and d["materials"]["STEEL"]["rho"] == 7850
    assert d["bodies"]["BEAM"]["role"] == "deformable" and sorted(n["set"] for n in d["nsets"] if n["kind"] == "inp") == ["FIX", "PFIX"]
    assert page.input_value("#xp-source") == "inp:" + p
    wait_text(page, "#xp-nsets", "*NSET PFIX of the .inp")
    page.click("#xp-tree [data-tp=inpfile]")
    wait_text(page, "#xp-inpfile", "Element types (2)")
    # Select in view: the node nearest to a click on the end of the bar
    page.click("#xp-inpfile [data-qop=sel]")
    xy = page.evaluate("(p) => { const T = window.__xp.XP.three, r = T.renderer.domElement.getBoundingClientRect();"
                       " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
                       " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }", [99.5, 9.5, 10])
    page.mouse.click(*xy)
    wait_text(page, "#xp-inpfile .ii-query", "1 node(s) found")
    assert page.locator("#xp-inpfile .ii-res td").first.inner_text() == "99" and page.evaluate("!!window.__xp.XP.queryMarks.focus")
    page.click("#xp-inpfile [data-qop=sel]")
    assert page.evaluate("window.__xp.XP.pick") is None
    page.click("#xp-tree [data-tp=all]")
    # the element edges of the file drawn on the bodies (Edges on)
    wire = "(() => { let n = 0; window.__xp.XP.three.group.traverse(o => { if (o.isLineSegments && o.geometry.index) n += o.geometry.index.count / 2; }); return n; })()"
    page.wait_for_function(wire + " > 0")
    assert page.evaluate(wire) == 176 + 52
    page.click("#xp-model-btn")
    page.wait_for_function("window.__xp.XP.meshSummary && window.__xp.XP.meshSummary.nodes >= 132", timeout=120000)
    # mesh selection data of the model .inp: node and element ids
    page.wait_for_function("window.__xp.XP.meshSel && window.__xp.XP.meshSel.ids.length === 132 && window.__xp.XP.meshSel.triElem.length > 0")


def test_explicit_external_rad(page, client, tmp_path):
    """Explicit Source = External .inp or Radioss .rad with a starter deck: the mesh is read and shown when the path is
    set (its parts); the deck is the Target .rad of Solve; Build does not run inp2rad."""
    from test_analysis import write_test_rad
    p = write_test_rad(str(tmp_path / "ext_0000.rad"))
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-kind", "inp")
    page.wait_for_selector("#xp-inp")
    page.fill("#xp-inp", p)
    page.dispatch_event("#xp-inp", "change")                 # the mesh is read when the path is set
    page.wait_for_function("window.__xp.XP.meshSummary && window.__xp.XP.meshSummary.elements === 25", timeout=60000)
    assert page.input_value("#xp-show") == "mesh"
    assert page.evaluate("window.__xp.XP.meshSummary.parts.map(x => x.elset)") == ["STRIP", "TRI", "BAR", "PART_4"]
    assert page.evaluate("window.__xp.XP.doc.settings.rad_target") == p.replace("\\", "/")
    page.click("#xp-build")
    wait_text(page, "#status", "no build")


def test_panel_model_tree(page, client, tmp_path, server_url):
    """Model tree of the Analysis and Explicit panels: the top node shows all pages; a node shows its page (Analysis:
    the card; Explicit: the part of Model or the section) and the pages below it; counts; a support selected in the
    list shows its page; Explicit Console opened by an action; ⇄ moves the panel to the left and back, kept after a
    reload; the width drag follows the side."""
    from test_analysis import write_test_inp
    p = write_test_inp(str(tmp_path / "tree.inp"))
    vis = "s => { const e = document.querySelector(s); return !!e && e.offsetParent !== null; }"
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    assert page.evaluate("document.querySelector('#fa-tree .tp-row.sel').dataset.tp") == "all"
    assert page.evaluate(vis, "#fa-sups-card") and page.evaluate(vis, "#fa-mats-card")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#fa-source", "inp:")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    # Bodies: the solid and the shell of the file as leaves; a leaf selects the body in the view
    assert page.inner_text("#fa-tree [data-tp=bodies] .tp-count") == "2"
    leaves = page.evaluate("[...document.querySelectorAll('#fa-tree .tp-leaf[data-tp=bodies]')].map(r => r.dataset.tpi)")
    assert leaves == ["BEAM", "PLATE:shell"]
    page.click("#fa-tree .tp-leaf[data-tp=bodies][data-tpi=BEAM]")
    assert page.evaluate("[...window.__fea.SH.sel.bodies]") == ["BEAM"] and page.evaluate(vis, "#fa-bodies-card") and not page.evaluate(vis, "#fa-mats-card")
    assert page.evaluate("document.querySelector('#fa-tree .tp-row.sel').dataset.tpi") == "BEAM"
    page.click("#fa-tree [data-tp=nsets]")
    assert page.evaluate(vis, "#fa-nsets-card") and not page.evaluate(vis, "#fa-mats-card") and not page.evaluate(vis, "#fa-sups-card")
    assert page.evaluate("[...document.querySelectorAll('#fa-tree .tp-leaf[data-tp=nsets]')].map(r => r.textContent)") == ["FIX", "PFIX"]
    assert page.inner_text("#fa-tree [data-tp=nsets] .tp-count") == "2"
    page.click("#fa-tree [data-tp=step]")                     # a node with children: its pages
    assert page.evaluate(vis, "#fa-sups-card") and page.evaluate(vis, "#fa-loads-card") and not page.evaluate(vis, "#fa-nsets-card")
    page.click("#fa-tree [data-tp=nsets]")
    page.click("#fa-nsets [data-nk=sup]")                     # a support on the node set: the Supports page
    page.wait_for_function("document.querySelector('#fa-tree .tp-row.sel').dataset.tp === 'sups'")
    # the support read from the *BOUNDARY of the file and the new one
    assert page.evaluate(vis, "#fa-sups-card") and page.inner_text("#fa-tree [data-tp=sups] .tp-count") == "2"
    page.evaluate("window.__fea.FA.sel = null")
    page.click("#fa-tree .tp-leaf[data-tp=sups] >> nth=0")    # a support leaf: the support selected
    assert page.evaluate("window.__fea.FA.sel.kind") == "support"
    # the panel on the left: the view to the right of it; the width drag follows the side
    page.click("#fa-tp-side")
    assert page.evaluate("document.querySelector('#fa-panel').getBoundingClientRect().right <= document.querySelector('#fa-view').getBoundingClientRect().left + 1")
    w0 = page.evaluate("document.querySelector('#fa-panel').getBoundingClientRect().width")
    b = page.locator("#fa-split").bounding_box()
    page.mouse.move(b["x"] + 3, b["y"] + 100); page.mouse.down(); page.mouse.move(b["x"] + 63, b["y"] + 100); page.mouse.up()
    assert abs(page.evaluate("document.querySelector('#fa-panel').getBoundingClientRect().width") - (w0 + 60)) < 3
    page.reload()
    page.wait_for_load_state("networkidle")
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc && document.querySelector('#fa-tree .tp-row.sel')")
    assert page.evaluate("document.querySelector('#fa-panel').parentElement.classList.contains('tp-left')")
    assert page.evaluate("document.querySelector('#fa-tree .tp-row.sel').dataset.tp") == "sups"
    page.click("#fa-tp-side")
    assert page.evaluate("document.querySelector('#fa-panel').getBoundingClientRect().left >= document.querySelector('#fa-view').getBoundingClientRect().right - 1")
    # Explicit: a part of Model, a section, Console opened by List parts
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#xp-source", "inp:")
    page.wait_for_function("window.__xp.XP.geo && window.__xp.XP.geo.components.length === 2")
    assert page.evaluate("[...document.querySelectorAll('#xp-tree .tp-leaf[data-tp=bodies]')].map(r => r.dataset.tpi)") == ["BEAM", "PLATE:shell"]
    page.click("#xp-tree .tp-leaf[data-tp=bodies][data-tpi=PLATE\\:shell]")
    assert page.evaluate("[...window.__xp.SH.sel.bodies]") == ["PLATE:shell"] and page.evaluate(vis, "#xp-model [data-page=bodies]")
    page.click("#xp-tree [data-tp=mats]")
    assert page.evaluate(vis, "#xp-model [data-page=mats]") and not page.evaluate(vis, "#xp-model [data-page=bodies]")
    # the curves of a library entry (static and Cowper-Symonds rates); an elastic material has none
    names = lambda: page.evaluate("[...document.querySelectorAll('#xp-matcurve [data-mc=mat] option')].map(o => o.value)")
    assert not any(n.startswith("STEEL") for n in names())
    page.select_option("#xp-model tr[data-m=STEEL] [data-mk=library]", "Steel S355 (DNVGL 19-pt + Cowper-Symonds rate)")
    page.select_option("#xp-matcurve [data-mc=mat]", "STEEL (Steel S355 (DNVGL 19-pt + Cowper-Symonds rate))")
    page.wait_for_function("document.querySelectorAll('#xp-matcurve svg polyline').length === 5")
    assert "1000 1/s" in page.text_content("#xp-matcurve")
    assert not page.evaluate(vis, "#xp-kind") and not page.evaluate(vis, "#xp-sec-runs")
    page.click("#xp-tree [data-tp=model]")
    assert page.evaluate(vis, "#xp-kind") and page.evaluate(vis, "#xp-model [data-page=bodies]") and not page.evaluate(vis, "#xp-sec-build")
    page.click("#xp-tree [data-tp=tools]")
    assert page.evaluate(vis, "#xp-tools") and not page.evaluate(vis, "#xp-sec-model")
    page.evaluate("window.__xp.openSection('xp-sec-console')")
    assert page.evaluate("document.querySelector('#xp-tree .tp-row.sel').dataset.tp") == "console" and page.evaluate(vis, "#xp-console")
    page.click("#xp-tree [data-tp=all]")
    assert page.evaluate(vis, "#xp-sec-model") and page.evaluate(vis, "#xp-sec-console")


def test_selection_propagation_vertices_mesh(page, client, tmp_path):
    """Selection tools: on a box with a rounded vertical edge, Tangent (10 deg) from a side face takes the side, the
    round and the other side (3 faces), Connected and Whole body all 7 faces, an edge chain through the tangent
    round edges; the vertices of the component; a selected vertex as an item with its coordinates. On Show Mesh of an
    .inp geometry: a box takes the mesh nodes on the surface, Elements the elements; a node set of the selection."""
    from conftest import part_rec, rect
    from test_analysis import write_test_inp
    p = part_rec("ui_tf", [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": rect(20, 10)}, "depth": 5},
                           {"id": "fl", "name": "Fillet 1", "type": "fillet", "value": 3, "edges": [{"mid": [20, 10, 2.5], "len": 5}]}])
    client.put("/api/part/file/ui_tf", json=p)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("() => { const s = document.getElementById('fa-source'); s.insertAdjacentHTML('beforeend', '<option value=\"part:ui_tf\">ui_tf</option>'); s.value = 'part:ui_tf'; s.dispatchEvent(new Event('change')); }")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 1 && window.__fea.FA.geo.components[0].mesh")
    r = page.evaluate("""async () => { const VS = await import('/static/viewsel.js'); const c = window.__fea.FA.geo.components[0];
        const side = c.refs.findIndex(q => q && q.kind === 'plane' && Math.abs(q.c[0] - 20) < 1e-6);
        const top = c.refs.findIndex(q => q && q.kind === 'plane' && Math.abs(q.c[2] - 5) < 1e-6);
        const curved = c.mesh.edges.findIndex(pl => pl.length > 2 && Math.abs(pl[0][2] - 5) < 1e-6);
        return { tan: VS.propagateFaces(c, side, 'angle', 10).length, top: VS.propagateFaces(c, top, 'angle', 10).length,
                 con: VS.propagateFaces(c, side, 'connected', 10).length, body: VS.propagateFaces(c, side, 'body', 10).length,
                 chain: VS.propagateEdges(c, curved, 'angle', 10).length, verts: VS.compVertices(c.mesh).length }; }""")
    assert r == {"tan": 3, "top": 1, "con": 7, "body": 7, "chain": 3, "verts": 10}
    page.select_option("#fa-selbar [data-vsp=prop]", "angle")
    page.wait_for_selector("#fa-selbar [data-vsp=angle]")
    page.fill("#fa-selbar [data-vsp=angle]", "5")
    page.dispatch_event("#fa-selbar [data-vsp=angle]", "change")
    assert page.evaluate("window.__fea.SH.sel.prop") == "angle" and page.evaluate("window.__fea.SH.sel.angle") == 5
    page.evaluate("() => window.__fea.SH.sel.vertices.add('1:0')")
    it = page.evaluate("async () => (await import('/static/viewsel.js')).items(window.__fea.SH, ['vertices']).vertices")
    assert len(it) == 1 and it[0]["comp"] == "1" and len(it[0]["xyz"]) == 3
    page.click("#fa-selbar [data-vs=clear]")
    # mesh nodes and elements of an .inp geometry
    path = write_test_inp(str(tmp_path / "sel.inp"))
    page.evaluate("p => { window.browse = async () => p; }", path)
    page.select_option("#fa-source", "inp:")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    page.click("#fa-mesh")
    page.wait_for_function("window.__fea.FA.mesh && window.__fea.FA.meshSel", timeout=120000)
    page.click("#fa-selbar [data-vs=nodes]")
    page.click("#fa-selbar [data-vs=box]")
    b = page.locator("#fa-view canvas:not(.navcube)").bounding_box()
    page.mouse.move(b["x"] + 5, b["y"] + 5); page.mouse.down(); page.mouse.move(b["x"] + b["width"] - 5, b["y"] + b["height"] - 5, steps=4); page.mouse.up()
    assert page.evaluate("window.__fea.SH.sel.nodes.size") == 123          # the nodes on the surface: 132 less 9 inside the bar
    page.click("#fa-selbar [data-vs=nodes]")
    page.click("#fa-selbar [data-vs=elements]")
    page.mouse.move(b["x"] + 5, b["y"] + 5); page.mouse.down(); page.mouse.move(b["x"] + b["width"] - 5, b["y"] + b["height"] - 5, steps=4); page.mouse.up()
    assert page.evaluate("window.__fea.SH.sel.elements.size") == 60
    page.click("#fa-tree [data-tp=nsets]")
    page.click("#fa-nsets [data-na=selection]")
    page.wait_for_function("window.__fea.FA.doc.nsets.some(n => n.kind === 'selection')")
    ns = page.evaluate("window.__fea.FA.doc.nsets.find(n => n.kind === 'selection')")
    assert len(ns["nodes"]) == 123 and len(ns["elements"]) == 60
    wait_text(page, "#fa-nsets", "123 mesh node(s), 60 element(s)")


def test_analysis_steps_ui(page, client, tmp_path):
    """Steps: Add step twice (Step 1 and Step 2 made), kind and time of a step, the support factors (0 in step 2:
    released), an amplitude and the load amplitude, an initial velocity picked from a selected body; with CalculiX the
    solve gives the states of both steps."""
    from test_analysis import CCX, write_test_inp
    p = write_test_inp(str(tmp_path / "st.inp"))
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#fa-source", "inp:")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    page.click("#fa-tree [data-tp=steps]")
    assert page.inner_text("#fa-tree [data-tp=steps] .tp-count") == "1"
    page.click("#fst-add")
    page.wait_for_function("(window.__fea.FA.doc.steps || []).length === 2")
    page.select_option("#fa-steps tr[data-st='2'] [data-stk=kind]", "dynamic")
    page.fill("#fa-steps tr[data-st='2'] [data-stk=time]", "0.002")
    page.dispatch_event("#fa-steps tr[data-st='2'] [data-stk=time]", "change")
    st = page.evaluate("window.__fea.FA.doc.steps[1]")
    assert st["kind"] == "dynamic" and st["time"] == 0.002
    # a support on the node set FIX (in place of the one read from the file), released in step 2 of a second support
    assert page.evaluate("window.__fea.FA.doc.supports.map(s => s.dofs)") == [[1, 1, 1, 0, 0, 0]]
    page.evaluate("""() => { const d = window.__fea.FA.doc, ns = d.nsets.find(n => n.set === 'FIX'), ps = d.nsets.find(n => n.set === 'PFIX');
        d.supports = [];
        d.supports.push({id: 's1', name: 'root', type: 'fixed', target: {nset: ns.id}}, {id: 's2', name: 'proot', type: 'pinned', target: {nset: ps.id}});
        window.__fea.FA.sel = {kind: 'support', id: 's2'}; window.__fea.SH.render(); }""")
    page.evaluate("window.__fea.select('support', 's2')")
    page.wait_for_selector("#fa-sups [data-stf='2']")
    page.fill("#fa-sups [data-stf='2']", "0")
    page.dispatch_event("#fa-sups [data-stf='2']", "change")
    assert page.evaluate("window.__fea.FA.doc.supports[1].steps") == {"1": 1, "2": 0}
    page.click("#fa-tree [data-tp=amps]")
    page.click("#famp-add")
    page.wait_for_function("(window.__fea.FA.doc.amplitudes || []).length === 1")
    page.fill("#fa-amps textarea", "0, 0\n0.001, 1\n0.002, 0")
    page.dispatch_event("#fa-amps textarea", "change")
    assert page.evaluate("window.__fea.FA.doc.amplitudes[0].points") == [[0, 0], [0.001, 1], [0.002, 0]]
    assert page.locator("#fa-amps .ac-plot svg polyline").count() == 1 and "step time (s)" in page.text_content("#fa-amps .ac-plot")
    page.evaluate("""() => { const d = window.__fea.FA.doc, c = window.__fea.FA.geo.components.find(x => x.id === 'BEAM');
        const end = c.refs.findIndex(r => Math.abs(r.c[0] - 100) < 1e-6);
        d.loads.push({id: 'l1', name: 'tip', type: 'force', target: {comp: 'BEAM', face: end}, value: [0, 0, -100]}); }""")
    page.evaluate("window.__fea.select('load', 'l1')")
    page.wait_for_selector("#fld-amp")
    page.select_option("#fld-amp", page.evaluate("window.__fea.FA.doc.amplitudes[0].id"))
    assert page.evaluate("window.__fea.FA.doc.loads[0].amplitude") == page.evaluate("window.__fea.FA.doc.amplitudes[0].id")
    page.fill("#fa-loads [data-stf='1']", "0")
    page.dispatch_event("#fa-loads [data-stf='1']", "change")
    assert page.evaluate("window.__fea.FA.doc.loads[0].steps") == {"1": 0, "2": 1}
    page.evaluate("() => window.__fea.SH.sel.bodies.add('BEAM')")
    page.click("#fa-tree [data-tp=ivel]")
    page.click("#fiv-add")
    page.wait_for_function("(window.__fea.FA.doc.initial_velocities || []).length === 1 && window.__fea.FA.doc.initial_velocities[0].target")
    assert page.evaluate("window.__fea.FA.doc.initial_velocities[0].target") == {"bodies": ["BEAM"]}
    if CCX is None:
        return
    page.click("#fa-solve")
    page.wait_for_function("(window.__fea.FA.res && window.__fea.FA.res.tables) || /failed|error|not /i.test(document.getElementById('status-text').textContent)", timeout=300000)
    assert page.evaluate("!!(window.__fea.FA.res && window.__fea.FA.res.tables)"), page.inner_text("#status-text")
    opts = page.evaluate("[...document.querySelectorAll('#fa-state option')].map(o => o.textContent)")
    assert "End of step 1: Step 1" in opts and "End of step 2: Step 2" in opts and opts[0] == "End of the last step"


def test_one_analysis_document_both_solvers(page, client, tmp_path):
    """Analysis tab, Solver OpenCourant: the explicit pane opens on the same document (geometry, materials, node sets
    of the .inp source shared), the tab button stays Analysis; a support added there is a support of type dofs of the
    document; Solver CalculiX shows the Analysis pane with it; the explicit mesh settings are kept as xp_mesh; the
    document saved with solver OpenCourant opens in the explicit pane (File list of the analyses); an explicit document
    of the former kind is converted by Solver CalculiX."""
    from test_analysis import write_test_inp
    p = write_test_inp(str(tmp_path / "one.inp"))
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#fa-source", "inp:")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    page.select_option("#fa-solver", "explicit")
    page.wait_for_function("!document.getElementById('tab-xp').hidden && window.__xp.XP.shared && window.__xp.XP.geo && window.__xp.XP.geo.components.length === 2")
    assert page.evaluate("document.querySelector('.tab.active').dataset.tab") == "fea"
    assert page.evaluate("window.__xp.XP.shared === window.__fea.FA.doc")
    assert page.evaluate("window.__xp.XP.doc.materials.STEEL.E") == 210000
    page.evaluate("""() => { const X = window.__xp.XP, ns = X.doc.nsets.find(n => n.set === 'FIX');
        X.doc.supports.push({id: 'sx', name: 'root', type: 'dofs', target: {nset: ns.id}, dofs: [1, 1, 1, 0, 0, 0]});
        X.doc.mesh = Object.assign({}, X.doc.mesh, {size: 7}); }""")
    d = page.evaluate("window.__fea.FA.doc")
    assert d["xp_mesh"]["size"] == 7 and d["xp_mesh"]["tet_type"] == "C3D4" and d["mesh"].get("size") != 7
    assert d["supports"][-1]["type"] == "dofs" and d["solver"] == "explicit"
    page.select_option("#xp-solver", "calculix")
    page.wait_for_function("!document.getElementById('tab-fea').hidden && window.__fea.FA.doc.solver === 'calculix'")
    page.click("#fa-tree [data-tp=sups]")
    wait_text(page, "#fa-sups", "root")
    # saved with solver OpenCourant: opens in the explicit pane
    page.evaluate("window.__fea.FA.doc.solver = 'explicit'; window.__fea.FA.doc.name = 'one_doc'")
    ok = client.put("/api/analysis/file/one_doc", json=page.evaluate("window.__fea.FA.doc"))
    assert ok.status_code == 200
    page.evaluate("window.__feaNewDoc()")
    page.evaluate("window.__feaLoadNamed('one_doc')")
    page.wait_for_function("!document.getElementById('tab-xp').hidden && window.__xp.XP.shared && window.__xp.XP.shared.name === 'one_doc'")
    assert page.evaluate("document.getElementById('xp-solver').value") == "explicit"
    assert page.evaluate("window.__xp.XP.doc.mesh.size") == 7
    # an explicit document of the former kind: converted by Solver CalculiX
    client.put("/api/explicit/file/old_x", json={"name": "old_x", "source": {"kind": "shinycad", "type": "assembly", "name": ""},
                                                 "materials": {"S355": {"library": "", "E": 210000, "nu": 0.3, "rho": 7850}}, "default_material": "S355",
                                                 "mesh": {"size": 5, "tet_type": "C3D4"}, "bodies": {}, "supports": [{"id": "s1", "name": "a", "target": {"nset": "n1"}, "dofs": [1, 0, 0]}],
                                                 "settings": {}, "next": 2})
    page.evaluate("window.__xpLoadNamed('old_x')")
    page.wait_for_function("window.__xp.XP.doc.name === 'old_x' && !window.__xp.XP.shared")
    page.select_option("#xp-solver", "calculix")
    page.wait_for_function("!document.getElementById('tab-fea').hidden && window.__fea.FA.doc.name === 'old_x'")
    d = page.evaluate("window.__fea.FA.doc")
    assert d["xp_mesh"]["size"] == 5 and d["supports"][0]["type"] == "dofs" and d["solver"] == "calculix"


def test_solver_switch_hands_over_the_view(page, client, tmp_path):
    """Solver OpenCourant and back: the explicit pane takes the camera (position, zoom, target), the selected body
    and face, the selected node of the model tree and the panel width of the CalculiX pane, and the CalculiX pane
    takes them back."""
    from test_analysis import write_test_inp
    p = write_test_inp(str(tmp_path / "ho.inp"))
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#fa-source", "inp:")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2 && window.__fea.FA.three.zoomed")
    page.evaluate("""() => { const T = window.__fea.FA.three; T.camera.position.set(300, 50, 80); T.camera.zoom = 2.5; T.controls.target.set(10, 5, 0);
        T.camera.lookAt(T.controls.target); T.camera.updateProjectionMatrix();
        const S = window.__fea.SH.sel; S.bodies.add('BEAM'); S.faces.add('PLATE:0');
        document.getElementById('fa-panel').style.width = '420px'; }""")
    page.click("#fa-tree [data-tp=sups]")
    page.select_option("#fa-solver", "explicit")
    page.wait_for_function("!document.getElementById('tab-xp').hidden && window.__xp.XP.three && window.__xp.XP.three.camera.zoom === 2.5", timeout=15000)
    c = page.evaluate("(() => { const T = window.__xp.XP.three; return [T.camera.position.toArray(), T.controls.target.toArray()]; })()")
    assert c[0] == pytest.approx([300, 50, 80]) and c[1] == pytest.approx([10, 5, 0])
    assert page.evaluate("[...window.__xp.SH.sel.bodies]") == ["BEAM"] and page.evaluate("[...window.__xp.SH.sel.faces]") == ["PLATE:0"]
    assert page.evaluate("window.__xp.XP.tree.selected()") == "sups"
    assert page.evaluate("document.getElementById('xp-panel').style.width") == "420px"
    page.evaluate("() => { const T = window.__xp.XP.three; T.camera.zoom = 1.5; T.camera.updateProjectionMatrix(); window.__xp.SH.sel.bodies.clear(); }")
    page.click("#xp-tree [data-tp=mats]")
    page.select_option("#xp-solver", "calculix")
    page.wait_for_function("!document.getElementById('tab-fea').hidden && window.__fea.FA.three.camera.zoom === 1.5", timeout=15000)
    assert page.evaluate("[...window.__fea.SH.sel.bodies]") == [] and page.evaluate("window.__fea.FA.tree.selected()") == "mats"


def test_analysis_time_history_ui(page, client, tmp_path):
    """History output: Add request with a selected body (nodes of the body), quantities, a second request on node set
    FIX with the reaction force; with CalculiX the Results Time history: the request list, the curves checked, the
    plot and the CSV; a click on the plot picks an increment state."""
    from test_analysis import CCX, write_test_inp
    p = write_test_inp(str(tmp_path / "th.inp"))
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#fa-source", "inp:")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    page.evaluate("() => window.__fea.SH.sel.bodies.add('BEAM')")
    page.click("#fa-tree [data-tp=hist]")
    page.click("#fa-hist [data-hadd]")
    page.wait_for_function("(window.__fea.FA.doc.history || []).length === 1 && window.__fea.FA.doc.history[0].target")
    assert page.evaluate("window.__fea.FA.doc.history[0].target") == {"bodies": ["BEAM"]}
    page.click("#fa-hist [data-hq=RF]")
    assert page.evaluate("window.__fea.FA.doc.history[0].quantities") == ["U", "RF"]
    # a contact request: the contact pairs of the document (not tied)
    page.evaluate("""() => { const d = window.__fea.FA.doc; d.contacts = [{id: 'c1', name: 'seat', type: 'surface', master: [], slave: []}, {id: 'c2', name: 'glue', type: 'tied', master: [], slave: []}];
        d.history.push({id: 'hct', name: 'ct', kind: 'contact', target: null, quantities: ['CF']}); window.__fea.select(null); }""")
    page.select_option("#fa-hist [data-hr=hct] [data-hk=contact]", "c1")
    assert page.evaluate("window.__fea.FA.doc.history[1].target") == {"contact": "c1"}
    assert page.locator("#fa-hist [data-hr=hct] [data-hk=contact] option").count() == 2
    page.evaluate("() => { const d = window.__fea.FA.doc; d.history.pop(); d.contacts = []; window.__fea.select(null); }")
    page.press("body", "Escape")
    page.evaluate("""() => { const d = window.__fea.FA.doc, ns = d.nsets.find(n => n.set === 'FIX'), c = window.__fea.FA.geo.components.find(x => x.id === 'BEAM');
        const end = c.refs.findIndex(r => Math.abs(r.c[0] - 100) < 1e-6);
        d.history.push({id: 'h9', name: 'root', kind: 'node', target: {nset: ns.id}, quantities: ['RF']});
        d.supports.push({id: 's1', name: 'root', type: 'fixed', target: {nset: ns.id}}, {id: 's2', name: 'p', type: 'pinned', target: {nset: d.nsets.find(n => n.set === 'PFIX').id}});
        d.loads.push({id: 'l1', name: 'tip', type: 'force', target: {comp: 'BEAM', face: end}, value: [0, 0, -100]});
        d.nonlinear = {nlgeom: true, inc0: 0.25, incmax: 0.25}; window.__fea.SH.render(); }""")
    # run monitor (data of a job poll): the last increment and the curves so far
    page.evaluate("""() => { const F = window.__fea.FA; F.job = 'x'; F.res = null; F.live = {n: 3, sta: {step: 1, inc: 3, att: 2, cut: true, itrs: 7, tot: 0.6, time: 0.6, dt: 0.1},
        time_history: [{id: '_sta', name: 'Increments (job.sta)', kind: 'solver', series: [{name: 'increment size', unit: 's', t: [0.25, 0.5, 0.6], v: [0.25, 0.25, 0.1]}]}]};
        window.__fea.renderResults(); }""")
    page.click("#fa-tree [data-tp=results]")
    wait_text(page, "#fa-results", "attempt 2 (cutback)")
    assert page.locator("#fr-lvplot polyline").count() == 1
    page.evaluate("() => { const F = window.__fea.FA; F.job = null; F.live = null; window.__fea.renderResults(); }")
    if CCX is None:
        return
    page.click("#fa-solve")
    page.wait_for_function("(window.__fea.FA.res && window.__fea.FA.res.tables) || /failed|error/i.test(document.getElementById('status-text').textContent)", timeout=300000)
    assert page.evaluate("!!(window.__fea.FA.res && window.__fea.FA.res.time_history)"), page.inner_text("#status-text")
    page.click("#fa-tree [data-tp=results]")
    page.wait_for_selector("#fr-thplot svg")
    page.select_option("#fr-threq", "h9")
    page.wait_for_selector("#fa-results [data-ths='RFz total']")
    page.check("#fa-results [data-ths='RFz total']")
    assert page.locator("#fr-thplot polyline").count() == 2
    b = page.locator("#fr-thplot .th-hit").bounding_box()
    page.mouse.click(b["x"] + b["width"] * 0.3, b["y"] + 10)
    assert page.evaluate("document.getElementById('fa-state').value").startswith("i")
    with page.expect_download() as dl:
        page.click("#fr-thcsv")
    assert "RFz total" in open(dl.value.path()).read()
    # probe and path: clicks on vertices of the result
    scr = ("(k) => { const T = window.__fea.FA.three, r = T.renderer.domElement.getBoundingClientRect();"
           " const m = T.group.children.find(o => o.userData && o.userData.kind === 'mesh'), P = m.geometry.attributes.position.array;"
           " let best = 0, bx = -Infinity; for (let i = 0; i < P.length / 3; i++) { const s = k * P[3 * i] + P[3 * i + 2] * 1e-3; if (s > bx) { bx = s; best = i; } }"
           " const V = Object.getPrototypeOf(T.camera.position).constructor, I = m.geometry.index.array; let f = 0; while (I[f] !== best) f++; f -= f % 3;"
           " const c = new V(); for (const q of [I[f], I[f + 1], I[f + 2]]) c.add(new V(P[3 * q], P[3 * q + 1], P[3 * q + 2])); c.multiplyScalar(1 / 3);"
           " const v = new V(P[3 * best], P[3 * best + 1], P[3 * best + 2]).lerp(c, 0.5).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")
    page.click("#fr-probe")
    page.evaluate("() => { const T = window.__fea.FA.three; T.controls.reset && T.controls.reset(); }")
    page.mouse.click(*page.evaluate(scr, 1))
    page.wait_for_function("(window.__fea.FA.probes || []).length === 1")
    page.wait_for_selector("#fr-probeplot polyline")
    n = page.evaluate("window.__fea.FA.res.increments.length")
    assert page.evaluate("document.querySelectorAll('#fr-probeplot circle').length") == n
    page.click("#fr-probe")
    page.click("#fr-path")
    xy = page.evaluate(scr, -1)
    page.mouse.click(*xy)
    time.sleep(0.5)
    page.wait_for_function("window.__fea.FA.path && window.__fea.FA.path.length === 1")
    time.sleep(0.6)
    page.mouse.click(*page.evaluate(scr, 1))
    time.sleep(0.5)
    page.wait_for_function("window.__fea.FA.path && window.__fea.FA.path.length === 2")
    page.wait_for_selector("#fr-pathplot polyline")
    with page.expect_download() as dl:
        page.click("#fr-pcsv")
    t = open(dl.value.path()).read()
    assert "von Mises" in t.splitlines()[0] or "|u|" in t.splitlines()[0]


def test_explicit_time_history_ui(page, client, tmp_path):
    """Solver OpenCourant: History output in the model tree of the explicit pane; Add request with a selected body
    (nodes of the body) and the quantities of the explicit solver (acceleration); an element request keeps a CalculiX
    quantity (shown as kept); the Results Time history of a job with time history curves: the plot, a second curve
    checked, the CSV."""
    from test_analysis import write_test_inp
    p = write_test_inp(str(tmp_path / "xth.inp"))
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("p => { window.browse = async () => p; }", p)
    page.select_option("#fa-source", "inp:")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2")
    page.evaluate("() => window.__fea.SH.sel.bodies.add('BEAM')")         # taken by the explicit pane (view handover)
    page.select_option("#fa-solver", "explicit")
    page.wait_for_function("!document.getElementById('tab-xp').hidden && window.__xp.XP.geo && window.__xp.XP.geo.components.length === 2 && window.__xp.SH.sel.bodies.has('BEAM')")
    page.click("#xp-tree [data-tp=hist]")
    page.click("#xp-hist [data-hadd]")
    page.wait_for_function("(window.__xp.XP.doc.history || []).length === 1 && window.__xp.XP.doc.history[0].target")
    assert page.evaluate("window.__fea.FA.doc.history[0].target") == {"bodies": ["BEAM"]}
    page.click("#xp-hist [data-hq=A]")
    assert page.evaluate("window.__fea.FA.doc.history[0].quantities") == ["U", "A"]
    page.press("body", "Escape")
    page.evaluate("""() => { const X = window.__xp.XP; X.doc.history.push({id: 'h7', name: 'parts', kind: 'element', target: {bodies: ['BEAM']}, quantities: ['S', 'ENER']}); window.__xp.renderModel(); }""")
    wait_text(page, "#xp-hist", "+ stress (von Mises)")
    page.evaluate("""() => { const X = window.__xp.XP; X.doc.history.push({id: 'h8', name: 'ct', kind: 'contact', target: null, quantities: ['CF']}); window.__xp.renderModel(); }""")
    wait_text(page, "#xp-hist", "general contact of the build")
    page.evaluate("() => { const X = window.__xp.XP; X.doc.history.pop(); window.__xp.renderModel(); }")
    page.click("#xp-hist [data-hr=h7] [data-hq=EKIN]")
    assert page.evaluate("window.__fea.FA.doc.history[1].quantities") == ["S", "ENER", "EKIN"]
    page.evaluate("""() => { const X = window.__xp.XP; X.res = {folder: '/x', job: 'j1', data: {job: 'j1', frames: [{time: 0}, {time: 0.001}], outs: {}, files: [],
        time_history: [{id: 'h1', name: 'beam', kind: 'node', series: [{name: 'uz mean', unit: 'mm', t: [0, 0.001], v: [0, -1]}, {name: 'RFz total', unit: 'N', t: [0, 0.001], v: [0, 30]}]}]},
        geo: null, frame: null, k: 0}; window.__xp.renderResults(); }""")
    page.click("#xp-tree [data-tp=results]")
    page.wait_for_selector("#xp-thplot svg")
    assert page.locator("#xp-thplot polyline").count() == 1
    page.check("#xp-results [data-ths='RFz total']")
    assert page.locator("#xp-thplot polyline").count() == 2
    with page.expect_download() as dl:
        page.click("#xp-thcsv")
    assert "RFz total" in open(dl.value.path()).read()
    # run monitor of the Solve section: the cycle lines of a job (status rows and /api/explicit/monitor stubbed)
    page.route("**/api/explicit/monitor?job=j2", lambda route: route.fulfill(content_type="application/json", body=json.dumps(
        {"job": "j2", "status": "Running", "t": [0, 0.001, 0.002], "dt": [1e-7, 1e-7, 1e-7], "err": [0, -0.1, -0.3], "dmm": [0, 1e-4, 2e-4], "nc": [100, 200, 300]})))
    page.evaluate("""() => { const X = window.__xp.XP; X.status = Object.assign({}, X.status, {rows: [{id: 's::j2', job: 'j2', status: 'Running', tag: 'running', folder: '/x'}]}); X.boardSel = 's::j2'; X.mon = null; return window.__xp.monitor(true); }""")
    page.click("#xp-tree [data-tp=solve]")
    wait_text(page, "#xp-monitor", "Run monitor: j2")
    page.check("#xp-monitor [data-mon=dmm]")
    page.wait_for_function("document.querySelectorAll('#xp-monplot polyline').length === 2")


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


def test_surface_bodies_in_analysis_explicit_and_assembly_views(page, client):
    """A part with a solid and a surface body, and a part with surface bodies only: the surface bodies are drawn
    translucent in the Analysis, Explicit and Assembly views (hidden surface bodies are not) and are pickable; the
    Shells tables; a support picked on an edge (symmetry types offered) and, with CalculiX, solved; the Explicit
    Mesh button and a support on an edge; Move 2 pts in the Assembly tab (vertex to vertex)."""
    def surf(fid, name, plane, w, h):
        from conftest import rect
        return {"id": fid, "name": name, "type": "surf_sketch", "kind": "planar", "plane": plane, "offset": 0,
                "sketch": {"entities": rect(w, h)}}
    p = plate("ui_surf", 100.0, 50.0, 10.0, 0.0)
    p["features"] += [surf("s1", "Wall", "XZ", 100, 60), surf("s2", "Hidden", "YZ", 50, 60)]
    p["hidden"] = ["s2"]
    client.put("/api/part/file/ui_surf", json=p)
    client.put("/api/part/file/ui_surf_only", json={"name": "ui_surf_only", "version": 2, "next": 2,
                                                      "features": [surf("s1", "Sheet", "XY", 40, 20)]})
    client.put("/api/assembly/file/ui_surf_asm", json={"name": "ui_surf_asm", "next": 3, "components": [
        {"id": "1", "name": "body", "source": {"type": "part", "name": "ui_surf"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "sheet", "source": {"type": "part", "name": "ui_surf_only"}, "pos": [0, 0, 30], "rot": [0, 0, 0]}]})
    # translucent materials of the component meshes (surface bodies: one material per body in the mesh groups)
    count = ("(g) => { let n = 0; g.traverse(o => { if (!o.isMesh) return; for (const m of [].concat(o.material)) "
             "if (m.transparent && m.opacity < 1 && m.opacity > 0.1) n++; }); return n; }")
    translucent = lambda group: page.evaluate("(%s)(%s)" % (count, group))
    # screen point of a global point in a view (FA, XP or AS)
    scr = ("([T, p]) => { const r = T.renderer.domElement.getBoundingClientRect();"
           " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("() => { const s = document.getElementById('fa-source'); s.insertAdjacentHTML('beforeend', '<option value=\"assembly:ui_surf_asm\">ui_surf_asm</option>'); s.value = 'assembly:ui_surf_asm'; s.dispatchEvent(new Event('change')); }")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2 && window.__fea.FA.three.group.children.length")
    wait_text(page, "#fa-info", "2 component(s)")
    geo = page.evaluate("window.__fea.FA.geo.components.map(c => [c.id, c.error, c.mesh.vertices.length > 0, c.surfaces.map(s => s.name)])")
    assert geo == [["1", None, True, ["Wall"]], ["2", None, True, ["Sheet"]]]
    assert translucent("window.__fea.FA.three.group") == 4          # 2 surface bodies + their section overlays
    assert page.evaluate("window.__fea.FA.three.pickables.filter(o => o.userData.comp === '2').length") == 1
    # shells: one section per surface body (thickness and the other shell inputs in Sections only)
    assert page.locator("#fa-bodies tr[data-shell]").count() == 0 and page.locator("#fa-bodies tr[data-id]").count() == 1
    assert page.evaluate("window.__fea.FA.doc.sections.map(s => [s.name, s.faces.map(f => f.comp)])") == [["BODY_WALL", ["1"]], ["SHEET_SHEET", ["2"]]]
    page.fill("#fa-sections tr[data-sec] >> nth=1 >> [data-sk=t]", "3")
    page.dispatch_event("#fa-sections tr[data-sec] >> nth=1 >> [data-sk=t]", "change")
    assert page.evaluate("window.__fea.FA.doc.sections[1].t") == 3
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "fea_surfaces.png"))
    # support on the edge x = 0 of the sheet (local midpoint (0, 10, 0), global z 30)
    page.click("#fa-add-sup")
    xy = page.evaluate("(a) => (%s)([window.__fea.FA.three, a])" % scr, [0, 10, 30])
    page.mouse.move(xy[0] + 3, xy[1] + 2)
    assert page.evaluate("!!window.__fea.FA.three.hover")
    page.mouse.click(xy[0] + 3, xy[1] + 2)
    page.keyboard.press("Enter")
    page.wait_for_function("(() => { const s = window.__fea.FA.doc.supports[0]; return s && s.target && s.target.edge !== undefined; })()")
    sup = page.evaluate("window.__fea.FA.doc.supports[0].target")
    er = page.evaluate("window.__fea.FA.geo.components[1].erefs[%d]" % sup["edge"])
    assert sup["comp"] == "2" and er["kind"] == "line" and abs(er["c"][0]) < 1e-6
    assert "line edge" in page.inner_text("#fa-sups") and page.locator("#fsp-type option[value=xsymm]").count() == 1
    from test_analysis import CCX
    if CCX is not None:
        page.evaluate("""() => { const d = window.__fea.FA.doc; d.bodies = { "1": { mode: "off" } }; d.sections[0].mode = "off";
            d.loads.push({ id: "lg", name: "g", type: "gravity", value: [0, 0, -9810] }); }""")
        page.click("#fa-solve")
        page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.tables", timeout=180000)
        b = page.evaluate("window.__fea.FA.res.tables.total.bodies")
        assert [x["name"] for x in b] == ["SHEET_SHEET"] and b[0]["umax"] > 0
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-source", "assembly:ui_surf_asm")
    page.wait_for_function("window.__xp.XP.geo && window.__xp.XP.geo.components.length === 2 && window.__xp.XP.three.group.children.length")
    assert page.evaluate("window.__xp.XP.geo.components.map(c => c.surfaces.length)") == [1, 1]
    assert translucent("window.__xp.XP.three.group") == 4
    assert page.locator(".xp-shells tr[data-shell]").count() == 0 and page.locator("#xp-sections tr[data-sec]").count() == 2
    assert page.inner_text("#xp-model-btn").strip() == "Mesh"
    page.click("#xp-supbtn")
    xy = page.evaluate("(a) => (%s)([window.__xp.XP.three, a])" % scr, [40, 10, 30])
    page.mouse.click(xy[0] + 2, xy[1] + 3)
    page.keyboard.press("Enter")
    page.wait_for_function("window.__xp.XP.doc.supports.length === 1 && window.__xp.XP.doc.supports[0].target.edge !== undefined")
    page.select_option(".xp-sups [data-spre]", "xsymm")
    assert page.evaluate("window.__xp.XP.doc.supports[0].dofs") == [1, 0, 0, 0, 1, 1]
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "xp_surfaces.png"))
    tab(page, "asm")
    page.evaluate("window.__asmLoadNamed('ui_surf_asm')")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.result.components.length === 2 && window.__asm.AS.three.group.children.length === 2")
    assert translucent("window.__asm.AS.three.group") == 2
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "asm_surfaces.png"))
    # Move 2 pts: the corner (0, 0, 30) of the sheet to the top corner (100, 0, 10) of the body
    page.click("#as-move2")
    for p_ in ([0, 0, 30], [100, 0, 10]):
        xy = page.evaluate("(a) => (%s)([window.__asm.AS.three, a])" % scr, p_)
        page.mouse.move(xy[0] + 4, xy[1] + 3)
        page.mouse.click(xy[0] + 4, xy[1] + 3)
        time.sleep(0.2)
    page.wait_for_function("(() => { const c = window.__asm.comp('2'); return c && c.pos[0] === 100; })()")
    assert page.evaluate("window.__asm.comp('2').pos") == [100, 0, 10]
    page.keyboard.press("Escape")
    assert page.evaluate("window.__asm.AS.move2") is None


def test_sections_and_node_sets_panels(page, client):
    """Girder of surface parts in the Analysis tab: By geometry makes PLATE_Z0 and WEB_Y50; Select faces and New from
    selection move a deck face to a new section; a node set by plane with a support on it; Select edges and a node
    set of the selected edge; Mesh shows the shell report; with CalculiX the solve gives one body per section. The
    Explicit tab shows the same panels."""
    def surf(fid, name, plane, w, h):
        from conftest import rect
        return {"id": fid, "name": name, "type": "surf_sketch", "kind": "planar", "plane": plane, "offset": 0,
                "sketch": {"entities": rect(w, h)}}
    client.put("/api/part/file/ui_gd_deck", json={"name": "ui_gd_deck", "version": 2, "next": 2, "features": [surf("s1", "Deck", "XY", 200, 100)]})
    client.put("/api/part/file/ui_gd_web", json={"name": "ui_gd_web", "version": 2, "next": 2, "features": [surf("w", "Web", "XZ", 400, 40)]})
    client.put("/api/assembly/file/ui_gd", json={"name": "ui_gd", "next": 4, "components": [
        {"id": "1", "name": "deck", "source": {"type": "part", "name": "ui_gd_deck"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "3", "name": "deck2", "source": {"type": "part", "name": "ui_gd_deck"}, "pos": [200, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "web", "source": {"type": "part", "name": "ui_gd_web"}, "pos": [0, 50, 0], "rot": [180, 0, 0]}]})
    scr = ("([T, p]) => { const r = T.renderer.domElement.getBoundingClientRect();"
           " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("() => { const s = document.getElementById('fa-source'); s.insertAdjacentHTML('beforeend', '<option value=\"assembly:ui_gd\">ui_gd</option>'); s.value = 'assembly:ui_gd'; s.dispatchEvent(new Event('change')); }")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 3 && window.__fea.FA.three.group.children.length")
    wait_text(page, "#fa-sections", "3 of 3 shell face(s) in sections")
    assert page.evaluate("window.__fea.FA.doc.sections.map(s => s.name)") == ["DECK_DECK", "DECK2_DECK", "WEB_WEB"]
    page.click("#fa-sections [data-sm=geom]")
    page.wait_for_function("window.__fea.FA.doc.sections.length === 2")
    assert page.evaluate("window.__fea.FA.doc.sections.map(s => [s.name, s.faces.length])") == [["PLATE_Z0", 2], ["WEB_Y50", 1]]
    assert page.locator("#fa-sections tr[data-sec]").count() == 2
    page.fill("#fa-sections tr[data-sec] >> nth=0 >> [data-sk=t]", "8")
    page.dispatch_event("#fa-sections tr[data-sec] >> nth=0 >> [data-sk=t]", "change")
    fsel = "#fa-sections tr[data-sec] >> nth=1 >> [data-sk=material]"
    page.wait_for_function("document.querySelector('#fa-sections [data-sk=material] option[value^=\"lib:\"]')")
    flabels = page.eval_on_selector(fsel, "e => [...e.options].map(o => [o.value, o.textContent])")
    assert flabels[0][1].startswith("(default: ") and " - " in flabels[1][1]
    flib = next(v for v, t in flabels if v.startswith("lib:"))
    page.select_option(fsel, flib)
    fd = page.evaluate("window.__fea.FA.doc")
    fm = fd["sections"][1]["material"]
    assert fd["materials"][fm]["library"] == flib[4:] and fd["materials"][fm]["law"] == "plastic"
    page.select_option(fsel, "")
    # Layers (S8R composite shells): disabled with S4, set on a section with S8R
    lsel = "#fa-sections tr[data-sec] >> nth=0 >> [data-sk=layers]"
    assert page.is_disabled(lsel)
    page.select_option("#fs-shtype", "S8R")
    assert page.is_enabled(lsel)
    page.fill(lsel, "3")
    page.dispatch_event(lsel, "change")
    assert page.evaluate("window.__fea.FA.doc.sections[0].layers") == 3
    page.select_option("#fs-shtype", "S4")
    assert page.evaluate("window.__fea.FA.doc.sections[0].t") == 8
    # Select faces: the deck of component 3, then New from selection
    page.click("#fa-sections [data-sm=selfaces]")
    assert page.evaluate("[...window.__fea.SH.sel.types]") == ["faces"]
    xy = page.evaluate("(a) => (%s)([window.__fea.FA.three, a])" % scr, [300, 20, 0])
    page.mouse.move(xy[0], xy[1])
    page.mouse.click(xy[0], xy[1])
    page.wait_for_function("window.__fea.SH.sel.faces.size === 1")
    assert page.evaluate("[...window.__fea.SH.sel.faces]") == ["3:0"]
    page.keyboard.press("Escape")
    assert page.evaluate("[...window.__fea.SH.sel.types]") == []
    page.click("#fa-sections [data-sm=new]")
    assert page.evaluate("window.__fea.FA.doc.sections.map(s => [s.name, s.faces.map(f => f.comp + ':' + f.face)])") == [
        ["PLATE_Z0", ["1:0"]], ["WEB_Y50", ["2:0"]], ["SECTION_3", ["3:0"]]]
    # node set by plane x = 0 and a support on it
    page.click("#fa-nsets [data-na=plane]")
    assert page.evaluate("window.__fea.FA.doc.nsets[0]")["kind"] == "plane"
    page.click("#fa-nsets tr[data-ns] >> nth=0 >> [data-nk=sup]")
    ns_id = page.evaluate("window.__fea.FA.doc.nsets[0].id")
    assert page.evaluate("window.__fea.FA.doc.supports[0].target") == {"nset": ns_id}
    assert "node set" in page.inner_text("#fa-sups")
    # Select edges: the edge x = 400 of the deck of component 3 and a node set of it
    page.click("#fa-nsets [data-na=seledges]")
    xy = page.evaluate("(a) => (%s)([window.__fea.FA.three, a])" % scr, [400, 20, 0])
    page.mouse.move(xy[0] + 2, xy[1] + 1)
    page.mouse.click(xy[0] + 2, xy[1] + 1)
    page.wait_for_function("window.__fea.SH.sel.edges.size === 1")
    page.keyboard.press("Escape")
    page.click("#fa-nsets [data-na=edges]")
    e = page.evaluate("window.__fea.FA.doc.nsets[1]")
    assert e["kind"] == "edges" and len(e["edges"]) == 1 and e["edges"][0]["comp"] == "3"
    er = page.evaluate("window.__fea.FA.geo.components.find(c => c.id === '3').erefs[%d]" % e["edges"][0]["edge"])
    assert er["kind"] == "line" and abs(er["c"][0] - 200) < 1e-6
    # a pressure load picked again on a face keeps one value (MPa)
    page.click("#fa-add-load")
    xy = page.evaluate("(a) => (%s)([window.__fea.FA.three, a])" % scr, [100, 20, 0])
    page.mouse.move(xy[0], xy[1])
    page.mouse.click(xy[0], xy[1])
    page.keyboard.press("Enter")
    page.wait_for_function("window.__fea.FA.doc.loads.length === 1 && window.__fea.FA.doc.loads[0].target && window.__fea.FA.doc.loads[0].target.face !== undefined")
    page.select_option("#fld-type", "pressure")
    page.click("#fld-pick")
    page.mouse.move(xy[0] + 1, xy[1])
    page.mouse.click(xy[0] + 1, xy[1])
    page.keyboard.press("Enter")
    time.sleep(0.3)
    ld = page.evaluate("window.__fea.FA.doc.loads[0]")
    assert ld["type"] == "pressure" and ld["value"] == 0.1 and ld["target"]["face"] is not None
    page.evaluate("() => { window.__fea.FA.doc.loads = []; }")
    # Mesh with Section sizes Grid: the shell report
    page.evaluate("() => { window.__fea.FA.doc.mesh = { size: 10, shell_size_mode: 'grid' }; }")
    page.click("#fa-mesh")
    wait_text(page, "#fa-results", "face(s) structured, 0 free", timeout=180000)
    assert "element quality (gamma) min 1" in page.inner_text("#fa-results")
    # Show Mesh after Mesh, with the support on the node set at its nodes (cones along ux uy uz, cubes for rotations)
    assert page.evaluate("document.getElementById('fa-show').value") == "mesh"
    glyphs = ("() => { const out = {}; window.__fea.FA.three.group.traverse(o => { if (o.isInstancedMesh && o.userData.kind) "
              "out[o.userData.kind + ':' + o.userData.id] = (out[o.userData.kind + ':' + o.userData.id] || 0) + o.count; }); return out; }")
    g = page.evaluate(glyphs)
    sid = page.evaluate("window.__fea.FA.doc.supports[0].id")
    assert g.get("support:" + sid, 0) >= 11 * 3, g
    page.uncheck("#fa-bcs")
    assert page.evaluate(glyphs) == {}
    page.check("#fa-bcs")
    page.select_option("#fa-show", "model")
    assert ("support:" + sid) in page.evaluate(glyphs)
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "fea_sections.png"))
    from test_analysis import CCX
    if CCX is not None:
        page.evaluate("() => window.__fea.FA.doc.loads.push({ id: 'lg', name: 'g', type: 'gravity', value: [0, 0, -9810] })")
        page.click("#fa-solve")
        page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.tables", timeout=180000)
        assert [b["name"] for b in page.evaluate("window.__fea.FA.res.tables.total.bodies")] == ["PLATE_Z0", "WEB_Y50", "SECTION_3"]
        # results of chosen bodies: ux uy uz of each body, a body not shown is not drawn; Show selected
        b0 = page.evaluate("window.__fea.FA.res.tables.total.bodies[0]")
        assert len(b0["ucomp"]) == 3 and abs(b0["ucomp"][2]) == pytest.approx(b0["umax"], rel=0.2)
        tris = "(() => { let n = 0; window.__fea.FA.three.group.traverse(o => { if (o.isMesh && o.userData.kind === 'mesh') n += o.geometry.index.count; }); return n; })()"
        n_all = page.evaluate(tris)
        page.uncheck("#fa-results [data-bshow='%s']" % b0["id"])
        assert 0 < page.evaluate(tris) < n_all and "1 body(ies) hidden" in page.inner_text("#fa-results")
        page.evaluate("() => { const S = window.__fea.SH.sel; S.faces.clear(); S.bodies.clear(); S.faces.add('3:0'); }")
        page.click("#fr-bsel")
        assert sorted(page.evaluate("[...window.__fea.FA.bodyHide]")) == sorted(b["id"] for b in page.evaluate("window.__fea.FA.res.tables.total.bodies") if b["name"] != "SECTION_3")
        page.click("#fr-ball")
        assert page.evaluate(tris) == n_all
    # Explicit tab: the panels with the shells
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-source", "assembly:ui_gd")
    page.wait_for_function("window.__xp.XP.geo && window.__xp.XP.geo.components.length === 3 && document.querySelector('#xp-sections [data-sm=geom]')")
    page.click("#xp-sections [data-sm=geom]")
    page.wait_for_function("(window.__xp.XP.doc.sections || []).length === 2")
    mats = page.evaluate("Object.keys(window.__xp.XP.doc.materials)")
    page.select_option("#xp-sections tr[data-sec] [data-sk=material]", mats[-1])
    assert page.evaluate("window.__xp.XP.doc.sections[0].material") == mats[-1]
    assert page.input_value("#xp-sections tr[data-sec] [data-sk=material]") == mats[-1]
    # labels: model name with the library entry or the values; a library entry adds a model material
    sel = "#xp-sections tr[data-sec] [data-sk=material]"
    labels = page.eval_on_selector(sel, "e => [...e.options].map(o => [o.value, o.textContent])")
    assert labels[0][0] == "" and labels[0][1].startswith("(default: ")
    assert any(v == mats[-1] and t.startswith(mats[-1] + " - ") for v, t in labels)
    lib = next(v for v, t in labels if v.startswith("lib:"))
    page.select_option(sel, lib)
    d = page.evaluate("window.__xp.XP.doc")
    new = d["sections"][0]["material"]
    assert new not in mats and d["materials"][new]["library"] == lib[4:] and d["materials"][new]["rho"] > 1000
    assert page.input_value(sel) == new and lib[4:] in page.eval_on_selector(sel, "e => e.options[e.selectedIndex].textContent")
    page.click("#xp-nsets [data-na=section_edges]")
    assert page.evaluate("window.__xp.XP.doc.nsets[0]")["body"] == "sec:" + page.evaluate("window.__xp.XP.doc.sections[0].id")


def test_reference_points_springs_joints_and_equations(page, client):
    """Analysis tab, shell plate 100 x 20 mm: a reference point picked at a vertex, then between two picked vertices,
    coupled rigidly to the picked edge; a point offset from it; a point at the centre of the circle through three
    typed points (deleted again); a spring, a ball joint and an equation; solve with the clamped edge x = 0 and a
    force on the first point. Explicit tab: Mesh, a reference point picked at a mesh node in Show Mesh, a support
    on it."""
    from conftest import rect
    client.put("/api/part/file/ui_rp_plate", json={"name": "ui_rp_plate", "version": 2, "next": 2, "features": [
        {"id": "s1", "name": "Plate", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(100, 20)}}]})
    client.put("/api/assembly/file/ui_rp", json={"name": "ui_rp", "next": 2, "components": [
        {"id": "1", "name": "plate", "source": {"type": "part", "name": "ui_rp_plate"}, "pos": [0, 0, 0], "rot": [0, 0, 0]}]})
    scr = ("([T, p]) => { const r = T.renderer.domElement.getBoundingClientRect();"
           " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")

    def click3(T, pt, dx=0, dy=0):
        xy = page.evaluate("(a) => (%s)([%s, a])" % (scr, T), pt)
        page.mouse.move(xy[0] + dx, xy[1] + dy)
        time.sleep(0.05)
        page.mouse.click(xy[0] + dx, xy[1] + dy)
        time.sleep(0.2)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("() => { const s = document.getElementById('fa-source'); s.insertAdjacentHTML('beforeend', '<option value=\"assembly:ui_rp\">ui_rp</option>'); s.value = 'assembly:ui_rp'; s.dispatchEvent(new Event('change')); }")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 1 && window.__fea.FA.three.group.children.length")
    page.click("[data-faview=iso]")
    T = "window.__fea.FA.three"
    pts = lambda: page.evaluate("window.__fea.FA.doc.points")
    page.click("#fa-rps [data-rpa=add]")
    click3(T, [100, 0, 0], 3, 2)
    assert pts()[0]["xyz"] == [100, 0, 0]
    page.select_option("#fa-rps [data-rp=m]", "between")
    page.click("#fa-rps [data-pickpt='1']")
    click3(T, [100, 20, 0], 2, 2)
    assert pts()[0]["xyz"] == [100, 10, 0] and pts()[0]["place"]["m"] == "between"
    page.select_option("#fa-rps [data-rp=coupling]", "rigid")
    page.click("#fa-rps [data-rpa=edges]")
    click3(T, [100, 5, 0], 2, 0)
    page.keyboard.press("Enter")
    e = pts()[0]["edges"]
    er = page.evaluate("window.__fea.FA.geo.components[0].erefs[%d]" % e[0]["edge"])
    assert len(e) == 1 and er["kind"] == "line" and abs(er["c"][0] - 100) < 1e-6
    # second point: offset dz 30 from the first
    page.click("#fa-rps [data-rpa=add]")
    page.keyboard.press("Escape")
    page.select_option("#fa-rps [data-slot='0']", pts()[0]["id"])
    page.fill("#fa-rps [data-v3=d][data-i='2']", "30")
    page.dispatch_event("#fa-rps [data-v3=d][data-i='2']", "change")
    assert pts()[1]["xyz"] == [100, 10, 30]
    # third point: circle through three typed points, then deleted
    page.click("#fa-rps [data-rpa=add]")
    page.keyboard.press("Escape")
    page.select_option("#fa-rps [data-rp=m]", "circle3")
    for i, q in enumerate([[0, 0, 0], [20, 0, 0], [10, 10, 0]]):
        for k in range(3):
            page.fill("#fa-rps [data-v3=pt%d][data-i='%d']" % (i, k), str(q[k]))
            page.dispatch_event("#fa-rps [data-v3=pt%d][data-i='%d']" % (i, k), "change")
    assert pts()[2]["xyz"] == [10, 0, 0]
    page.click("#fa-rps [data-del=rp][data-id='%s']" % pts()[2]["id"])
    assert len(pts()) == 2
    # moving the first point moves the second (offset from it)
    page.click("#fa-rps [data-pick=rp][data-id='%s']" % pts()[0]["id"])
    page.fill("#fa-rps [data-rp=t]", "0.25")
    page.dispatch_event("#fa-rps [data-rp=t]", "change")
    assert pts()[0]["xyz"] == [100, 5, 0] and pts()[1]["xyz"] == [100, 5, 30]
    page.click("#fa-springs [data-sa=add]")
    page.click("#fa-joints [data-ja=add]")
    page.click("#fa-eqs [data-qa=add]")
    d = page.evaluate("window.__fea.FA.doc")
    p1, p2 = d["points"][0]["id"], d["points"][1]["id"]
    assert d["springs"][0]["a"] == {"point": p1} and d["springs"][0]["b"] is None
    assert d["joints"][0]["a"] == {"point": p1} and d["joints"][0]["b"] == {"point": p2}
    assert [t["end"] for t in d["equations"][0]["terms"]] == [{"point": p1}, {"point": p2}]
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "fea_refpoints.png"))
    from test_analysis import CCX
    if CCX is not None:
        e0 = page.evaluate("window.__fea.FA.geo.components[0].erefs.findIndex(r => r && r.kind === 'line' && Math.abs(r.c[0]) < 1e-6)")
        page.evaluate("""([p1, p2, e0]) => { const d = window.__fea.FA.doc;
            d.equations = []; d.joints[0].type = 'weld';
            d.supports.push({ id: 'sx', name: 'root', type: 'fixed', target: { comp: '1', edge: e0 } });
            d.loads.push({ id: 'lx', name: 'F', type: 'force', target: { point: p1 }, value: [0, 0, -10] });
            d.springs[0].a = { point: p2 }; d.springs[0].k = [0, 0, 1, 0, 0, 0]; }""", [p1, p2, e0])
        page.click("#fa-solve")
        page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.tables", timeout=180000)
        P = page.evaluate("window.__fea.FA.res.tables.total.points")
        assert [x["name"] for x in P] == ["RP 1", "RP 2"] and P[0]["u"][2] < 0
    # Explicit: a point at a mesh node, a support on it
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-source", "assembly:ui_rp")
    page.wait_for_function("window.__xp.XP.geo && window.__xp.XP.geo.components.length === 1 && window.__xp.XP.three.group.children.length")
    page.evaluate("() => { window.__xp.XP.doc.mesh = { size: 10, shell_size_mode: 'grid' }; }")
    page.click("#xp-model-btn")
    page.wait_for_function("window.__xp.XP.mesh && document.getElementById('xp-show').value === 'mesh'", timeout=120000)
    page.click("#xp-rps [data-rpa=add]")
    click3("window.__xp.XP.three", [50, 10, 0], 3, 3)
    xp = page.evaluate("window.__xp.XP.doc.points[0]")
    assert xp["xyz"] == [50, 10, 0] and page.evaluate("document.getElementById('xp-show').value") == "mesh"
    page.click("#xp-supbtn")
    click3("window.__xp.XP.three", [50, 10, 0])
    page.keyboard.press("Enter")
    page.wait_for_function("window.__xp.XP.doc.supports.length === 1")
    assert page.evaluate("window.__xp.XP.doc.supports[0].target") == {"point": xp["id"]}
    assert "reference point RP 1" in page.inner_text(".xp-sups")


def test_view_selection_types_box_and_targets(page, client):
    """Selection toolbar of the 3D views (viewsel.js): a click toggles a face (Faces) or a surface body (Bodies); a box
    dragged to the right takes the items fully inside, to the left the items inside or crossing; Ctrl deselects;
    reference points by box; Support with two faces selected takes both ({"faces"}); Pick with nothing selected waits
    for Done; Analysis: a force on two selected faces."""
    def surf(fid, name, plane, w, h):
        from conftest import rect
        return {"id": fid, "name": name, "type": "surf_sketch", "kind": "planar", "plane": plane, "offset": 0,
                "sketch": {"entities": rect(w, h)}}
    client.put("/api/part/file/ui_vs_deck", json={"name": "ui_vs_deck", "version": 2, "next": 2, "features": [surf("s1", "Deck", "XY", 200, 100)]})
    client.put("/api/part/file/ui_vs_web", json={"name": "ui_vs_web", "version": 2, "next": 2, "features": [surf("w", "Web", "XZ", 200, 40)]})
    client.put("/api/assembly/file/ui_vs", json={"name": "ui_vs", "next": 3, "components": [
        {"id": "1", "name": "deck", "source": {"type": "part", "name": "ui_vs_deck"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "web", "source": {"type": "part", "name": "ui_vs_web"}, "pos": [0, 50, 0], "rot": [180, 0, 0]}]})
    scr = ("([T, p]) => { const r = T.renderer.domElement.getBoundingClientRect();"
           " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-source", "assembly:ui_vs")
    page.wait_for_function("window.__xp.XP.geo && window.__xp.XP.geo.components.length === 2 && window.__xp.XP.three.group.children.length")
    page.click("[data-xpview=top]")
    T = "window.__xp.XP.three"
    at = lambda p_: page.evaluate("(a) => (%s)([%s, a])" % (scr, T), p_)
    sel = lambda: page.evaluate("(() => { const S = window.__xp.SH.sel; return {faces: [...S.faces].sort(), edges: [...S.edges], bodies: [...S.bodies], points: [...S.points]}; })()")

    def drag(a, b, ctrl=False, shot=None):
        page.mouse.move(a[0], a[1])
        if ctrl:
            page.keyboard.down("Control")
        page.mouse.down()
        page.mouse.move((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, steps=3)
        page.mouse.move(b[0], b[1], steps=3)
        if shot and os.environ.get("DRAWGEN_SHOTS"):
            page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], shot))
        page.mouse.up()
        if ctrl:
            page.keyboard.up("Control")
    # Faces: a click selects, a second click deselects
    page.click("#xp-selbar [data-vs=faces]")
    assert page.evaluate("[...window.__xp.SH.sel.types]") == ["faces"]
    xy = at([50, 20, 0])
    page.mouse.click(xy[0], xy[1])
    assert sel()["faces"] == ["1:0"] and "1 face(s)" in page.inner_text("#xp-selbar")
    page.mouse.click(xy[0], xy[1])
    assert sel()["faces"] == []
    # Box: to the right around the whole model takes both faces; with Ctrl they leave the selection
    page.click("#xp-selbar [data-vs=box]")
    lo, hi = at([-20, 120, 0]), at([220, -20, 0])
    drag(lo, hi)
    assert sel()["faces"] == ["1:0", "2:0"]
    drag(lo, hi, ctrl=True)
    assert sel()["faces"] == []
    # a small box inside the deck: to the right (inside) nothing, to the left (crossing) the deck face
    a, b = at([20, 30, 0]), at([40, 10, 0])
    drag(a, b)
    assert sel()["faces"] == []
    drag(b, a, shot="xp_box_crossing.png")
    assert sel()["faces"] == ["1:0"]
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "xp_box_selected.png"))
    page.click("#xp-selbar [data-vs=clear]")
    # Bodies: a click selects the surface body of the face
    page.click("#xp-selbar [data-vs=faces]")
    page.click("#xp-selbar [data-vs=bodies]")
    page.mouse.click(xy[0], xy[1])
    assert sel()["bodies"] == ["1:s1"] and sel()["faces"] == []
    # Suppress and Unsuppress the selected body
    page.click("#xp-selbar [data-vs=sup]")
    sec = page.evaluate("window.__xp.XP.doc.sections.find(x => x.faces.some(f => f.comp === '1'))")
    assert sec["mode"] == "off" and sec["prev_off"] == "shell"
    page.click("#xp-selbar [data-vs=unsup]")
    assert page.evaluate("window.__xp.XP.doc.sections.find(x => x.faces.some(f => f.comp === '1')).mode") == "shell"
    # reference points by box
    page.evaluate("window.__xp.XP.doc.points = [{id: 'p1', name: 'P1', xyz: [150, 80, 0], coupling: 'none'}]; window.__xp.renderModel(); window.__xp.draw();")
    page.click("#xp-selbar [data-vs=bodies]")
    page.click("#xp-selbar [data-vs=points]")
    drag(at([140, 90, 0]), at([160, 70, 0]))
    assert sel()["points"] == ["p1"]
    page.click("#xp-selbar [data-vs=clear]")
    # Support from a selection of two faces: one support on both
    page.click("#xp-selbar [data-vs=points]")
    page.click("#xp-selbar [data-vs=faces]")
    drag(lo, hi)
    page.click("#xp-supbtn")
    t = page.evaluate("window.__xp.XP.doc.supports[0].target")
    assert sorted(f["comp"] + ":" + str(f["face"]) for f in t["faces"]) == ["1:0", "2:0"] and "2 face(s)" in page.inner_text(".xp-sups")
    assert sel()["faces"] == []
    # Pick with nothing selected: clicks select until Done
    page.click(".xp-sups [data-spick]")
    assert "Done" in page.inner_text("#xp-selbar")
    page.click("#xp-selbar [data-vs=box]")
    page.mouse.click(xy[0], xy[1])
    page.click("#xp-selbar [data-vs=done]")
    assert page.evaluate("window.__xp.XP.doc.supports[0].target") == {"comp": "1", "face": 0}
    assert not page.evaluate("window.__xp.SH.sel.collect")
    # Mesh refinement region from the selection
    page.evaluate("() => { const S = window.__xp.SH.sel; S.faces.add('2:0'); }")
    page.click("#xp-model .xp-refine [data-rf=add]")
    rf = page.evaluate("window.__xp.XP.doc.refine")
    assert len(rf) == 1 and rf[0]["faces"] == [{"comp": "2", "face": 0}] and rf[0]["size"] == 10
    page.fill("#xp-model .xp-refine tr[data-rf] [data-rk=size]", "4")
    page.dispatch_event("#xp-model .xp-refine tr[data-rf] [data-rk=size]", "change")
    assert page.evaluate("window.__xp.XP.doc.refine[0].size") == 4
    # Surfaces: New from selection with nothing selected waits for Done; a support on the surface
    page.click("#xp-selbar [data-vs=clear]")
    page.click("#xp-surfaces [data-sf=new]")
    assert page.evaluate("!!window.__xp.SH.sel.collect")
    page.click("#xp-selbar [data-vs=box]")
    page.mouse.click(xy[0], xy[1])
    page.click("#xp-selbar [data-vs=done]")
    sf = page.evaluate("window.__xp.XP.doc.surfaces")
    assert len(sf) == 1 and sf[0]["faces"] == [{"comp": "1", "face": 0}] and sf[0]["name"] == "SURFACE_1"
    page.select_option(".xp-sups [data-ssurf]", "surf:" + sf[0]["id"])
    assert page.evaluate("window.__xp.XP.doc.supports[0].target") == {"surface": sf[0]["id"]}
    assert "surface SURFACE_1 (1 face(s))" in page.inner_text(".xp-sups")
    # Analysis: a force on two selected faces
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("() => { const s = document.getElementById('fa-source'); s.insertAdjacentHTML('beforeend', '<option value=\"assembly:ui_vs\">ui_vs</option>'); s.value = 'assembly:ui_vs'; s.dispatchEvent(new Event('change')); }")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2 && window.__fea.FA.three.group.children.length")
    page.evaluate("() => { const S = window.__fea.SH.sel; S.faces.add('1:0'); S.faces.add('2:0'); }")
    page.click("#fa-add-load")
    ld = page.evaluate("window.__fea.FA.doc.loads[0]")
    assert ld["type"] == "force" and len(ld["target"]["faces"]) == 2 and "2 face(s)" in page.inner_text("#fa-loads")
    # contact: Add contact with nothing selected waits for Done; a surface as the master side
    page.click("#fc-add")
    assert page.evaluate("!!window.__fea.SH.sel.collect")
    page.evaluate("() => { const S = window.__fea.SH.sel; S.faces.add('1:0'); S.faces.add('2:0'); }")
    page.keyboard.press("Enter")
    ct = page.evaluate("window.__fea.FA.doc.contacts[0]")
    assert ct["master"] == [{"comp": "1", "face": 0}] and ct["slave"] == [{"comp": "2", "face": 0}]
    page.evaluate("() => { const d = window.__fea.FA.doc; d.surfaces = [{ id: 'sfa', name: 'TOP', faces: [{ comp: '1', face: 0 }] }]; window.__fea.SH.render(); }")
    page.select_option("#fa-contacts [data-fcsurf=master]", "surf:sfa")
    ct = page.evaluate("window.__fea.FA.doc.contacts[0]")
    assert ct["master_surface"] == "sfa" and ct["master"] == [] and "surface TOP (1 face(s))" in page.inner_text("#fa-contacts")
    # a plain click (no type on) selects the face under the cursor
    page.evaluate("() => { const S = window.__fea.SH.sel; S.faces.clear(); S.types.clear(); S.box = false; }")
    xa = page.evaluate("(a) => (%s)([window.__fea.FA.three, a])" % scr, [60, 20, 0])
    page.mouse.click(xa[0], xa[1])
    assert page.evaluate("[...window.__fea.SH.sel.faces]") == ["1:0"]


def test_explicit_velocities_and_node_sets_of_bodies_and_faces(page, client):
    """Explicit tab, a solid block and a rigid shell impactor: a node set of the block body (Bodies), a node set of a
    solid face picked with Select faces, an initial and an imposed velocity on the rigid impactor (arrow in the view);
    Mesh lists the node sets and the velocities."""
    from conftest import part_rec, rect
    client.put("/api/part/file/ui_v_blk", json=part_rec("ui_v_blk", [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                                                                       "sketch": {"entities": rect(40, 40)}, "depth": 20}]))
    client.put("/api/part/file/ui_v_tup", json={"name": "ui_v_tup", "version": 2, "next": 2, "features": [
        {"id": "s1", "name": "Tup", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(20, 20)}}]})
    client.put("/api/assembly/file/ui_v", json={"name": "ui_v", "next": 3, "components": [
        {"id": "1", "name": "block", "source": {"type": "part", "name": "ui_v_blk"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "tup", "source": {"type": "part", "name": "ui_v_tup"}, "pos": [10, 10, 30], "rot": [0, 0, 0]}]})
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-source", "assembly:ui_v")
    page.wait_for_function("window.__xp.XP.geo && window.__xp.XP.geo.components.length === 2 && window.__xp.XP.three.group.children.length")
    page.select_option("#xp-sections tr[data-sec] [data-sk=mode]", "rigid")
    page.click("#xp-nsets [data-na=body]")
    assert page.evaluate("window.__xp.XP.doc.nsets[0]")["bodies"] == ["1"]
    assert page.locator("#xp-nsets [data-nb]").count() == 3
    page.click("#xp-nsets [data-na=selfaces]")
    scr = ("([T, p]) => { const r = T.renderer.domElement.getBoundingClientRect();"
           " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")
    xy = page.evaluate("(a) => (%s)([window.__xp.XP.three, a])" % scr, [2, 2, 20])
    page.mouse.move(xy[0], xy[1])
    page.mouse.click(xy[0], xy[1])
    page.wait_for_function("window.__xp.SH.sel.faces.size === 1")
    page.keyboard.press("Escape")
    page.click("#xp-nsets [data-na=faces]")
    f = page.evaluate("window.__xp.XP.doc.nsets[1]")["faces"]
    r = page.evaluate("window.__xp.XP.geo.components[0].refs[%d]" % f[0]["face"])
    assert f[0]["comp"] == "1" and r["kind"] == "plane" and abs(r["c"][2] - 20) < 1e-6
    page.click("#xp-vels [data-va=initial]")
    page.click("#xp-vels [data-va=imposed]")
    v = page.evaluate("window.__xp.XP.doc.velocities")
    assert [(x["kind"], x["target"]) for x in v] == [("initial", {"body": "2:s1"}), ("imposed", {"body": "2:s1"})]
    # an amplitude (Loading, Amplitudes) on the imposed velocity in place of the ramp
    page.click("#xp-tree [data-tp=amps]")
    page.click("#xp-amps [data-ak=add]")
    page.wait_for_function("(window.__xp.XP.doc.amplitudes || []).length === 1")
    page.fill("#xp-amps textarea", "0, 0\n0.002, 1")
    page.dispatch_event("#xp-amps textarea", "change")
    assert page.evaluate("window.__xp.XP.doc.amplitudes[0].points") == [[0, 0], [0.002, 1]] and page.locator("#xp-amps .ac-plot svg polyline").count() == 1
    page.click("#xp-tree [data-tp=vels]")
    page.select_option("#xp-vels [data-vk=amplitude]", page.evaluate("String(window.__xp.XP.doc.amplitudes[0].id)"))
    assert page.evaluate("window.__xp.XP.doc.velocities[1].amplitude") == page.evaluate("String(window.__xp.XP.doc.amplitudes[0].id)")
    assert page.locator("#xp-vels [data-vk=ramp]").count() == 0
    page.click("#xp-tree [data-tp=model]")
    assert page.evaluate("(() => { let n = 0; window.__xp.XP.three.group.traverse(o => { if (o.type === 'ArrowHelper') n++; }); return n; })()") == 2
    page.click("#xp-model-btn")
    page.wait_for_function("window.__xp.XP.meshSummary && window.__xp.XP.meshSummary.velocities", timeout=120000)
    s = page.evaluate("window.__xp.XP.meshSummary")
    assert [n["name"] for n in s["nsets"]] == ["BODY_1", "NSET_2"] and len(s["velocities"]) == 2
    assert "Velocities: Initial" in page.inner_text("#xp-model")


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


def test_assembly_refresh_changed_part(page, client):
    """Refresh of the Assembly tab: a part saved after the build marks Refresh orange; Refresh builds the components
    again from the saved part (the new size) and clears the mark."""
    client.put("/api/part/file/ui_rf", json=plate("ui_rf", 40.0, 20.0, 5.0, 0.0))
    tab(page, "asm")
    add_part(page, "ui_rf")
    page.wait_for_function("window.__asm.AS.result && window.__asm.AS.bbox && Math.abs(window.__asm.AS.bbox[3] - window.__asm.AS.bbox[0] - 40) < 0.5")
    assert "cm-stale" not in (page.get_attribute("#as-refresh", "class") or "")
    client.put("/api/part/file/ui_rf", json=plate("ui_rf", 60.0, 20.0, 5.0, 0.0))
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    page.wait_for_function("document.getElementById('as-refresh').classList.contains('cm-stale')")
    page.click("#as-refresh")
    page.wait_for_function("Math.abs(window.__asm.AS.bbox[3] - window.__asm.AS.bbox[0] - 60) < 0.5")
    page.wait_for_function("!document.getElementById('as-refresh').classList.contains('cm-stale')")


def test_reference_point_pick_not_through_faces(page, client):
    """A point picked on a face is not snapped to the edge of a plate hidden behind the face."""
    def surf(fid, name, plane, w, h):
        from conftest import rect
        return {"id": fid, "name": name, "type": "surf_sketch", "kind": "planar", "plane": plane, "offset": 0,
                "sketch": {"entities": rect(w, h)}}
    client.put("/api/part/file/ui_hp_top", json={"name": "ui_hp_top", "version": 2, "next": 2, "features": [surf("s1", "Top", "XY", 200, 100)]})
    client.put("/api/part/file/ui_hp_low", json={"name": "ui_hp_low", "version": 2, "next": 2, "features": [surf("s1", "Low", "XY", 40, 20)]})
    client.put("/api/assembly/file/ui_hp", json={"name": "ui_hp", "next": 3, "components": [
        {"id": "1", "name": "top", "source": {"type": "part", "name": "ui_hp_top"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "low", "source": {"type": "part", "name": "ui_hp_low"}, "pos": [100, 10, -50], "rot": [0, 0, 0]}]})
    scr = ("([T, p]) => { const r = T.renderer.domElement.getBoundingClientRect();"
           " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-source", "assembly:ui_hp")
    page.wait_for_function("window.__xp.XP.geo && window.__xp.XP.geo.components.length === 2 && window.__xp.XP.three.group.children.length")
    page.click("[data-xpview=top]")
    page.click("#xp-rps [data-rpa=add]")
    xy = page.evaluate("(a) => (%s)([window.__xp.XP.three, a])" % scr, [100, 20, 0])
    page.mouse.move(xy[0] + 2, xy[1])
    page.mouse.click(xy[0] + 2, xy[1])
    p = page.evaluate("window.__xp.XP.doc.points[0].xyz")
    assert abs(p[2]) < 1e-6, p


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
    page.click("#cmd-finish")
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
    page.wait_for_selector("#pt-cmdbody .cw-sec[data-step='1'] .cw-sec-head")
    page.click("#pt-cmdbody .cw-sec[data-step='1'] .cw-sec-head")
    page.wait_for_function("document.querySelector('#pt-cmdbody .cw-sec.active .lbl').textContent.startsWith('Edge or curve')")
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
    """Ref. point: the picked point sets the point; Coupling rigid and Add faces connect the picked face; Esc ends
    the face picking. Support and Load with the reference point selected act on it; the support shows six
    components; the results list the reference point."""
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
    page.evaluate("(t) => window.__fea.FA.pick.cb({xyz: t.c})", top_face)
    page.select_option("#fa-rps [data-rp=coupling]", "rigid")
    page.click("#fa-rps [data-rpa=faces]")
    page.wait_for_function("window.__fea.SH.sel.collect")
    page.evaluate("(t) => window.__fea.SH.sel.faces.add(t.comp + ':' + t.face)", top_face)
    page.keyboard.press("Enter")
    rp = page.evaluate("window.__fea.FA.doc.points[0]")
    assert rp["xyz"] == top_face["c"] and len(rp["faces"]) == 1
    page.click("#fa-add-load")
    page.wait_for_function("window.__fea.FA.doc.loads.length === 1")
    assert page.evaluate("window.__fea.FA.doc.loads[0].target") == {"point": rp["id"]}
    page.evaluate("() => { const l = window.__fea.FA.doc.loads[0]; l.type = 'moment'; l.value = [0, 0, 10000]; }")
    page.click("#fa-rps .rp-item")
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
    import fake_opencourant
    from conftest import part_rec, rect

    def block(name, w, h, t, x=0.0, y=0.0):
        return part_rec(name, [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                                "sketch": {"entities": rect(w, h, x, y)}, "depth": t}])
    assert client.put("/api/part/file/xpb_target", json=block("xpb_target", 200, 200, 10, -100, -100)).status_code == 200
    assert client.put("/api/part/file/xpb_imp", json=block("xpb_imp", 40, 40, 40, -20, -20)).status_code == 200
    assert client.put("/api/assembly/file/xpb_drop", json={"name": "xpb_drop", "next": 3, "components": [
        {"id": "1", "name": "target", "source": {"type": "part", "name": "xpb_target"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "impactor", "source": {"type": "part", "name": "xpb_imp"}, "pos": [0, 0, 15], "rot": [0, 0, 0]}]}).status_code == 200
    exe = fake_opencourant.install(str(tmp_path / "exec"))
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
    page.keyboard.press("Enter")
    page.wait_for_function("window.__xp.XP.doc.supports.length === 1")
    assert "target" in page.inner_text(".xp-sups .xp-face")
    page.click("#xp-model-btn")
    page.wait_for_function("document.querySelector('#xp-show').value === 'mesh'", timeout=120000)
    assert page.evaluate("window.__xp.XP.meshSummary.supports") >= 1
    # supports at the mesh nodes (cones), Supports off and on
    cones = ("() => { let n = 0; window.__xp.XP.three.group.traverse(o => { if (o.isInstancedMesh && o.userData.kind === 'support') n += o.count; }); return n; }")
    nb = len(page.evaluate("window.__xp.XP.mesh.bcs[0].nodes"))
    assert nb > 0 and page.evaluate(cones) >= nb
    page.uncheck("#xp-bcs")
    assert page.evaluate(cones) == 0
    page.check("#xp-bcs")
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
    # parts of the results: max |d| of the frame; a part not shown is not drawn
    assert page.locator("#xp-parts [data-pshow]").count() == 1 and "1 part" in page.inner_text("#xp-parts")
    assert page.evaluate("window.__xp.XP.res.frame.parts[0].umax") > 0
    page.uncheck("#xp-parts [data-pshow='0']")
    tris = "(() => { let n = 0; window.__xp.XP.three.group.traverse(o => { if (o.isMesh && o.userData.kind === 'mesh') n += o.geometry.attributes.position.count; }); return n; })()"
    assert page.evaluate(tris) == 0 and "1 part(s) hidden" in page.inner_text("#xp-parts")
    page.click("#xp-pall")
    assert page.evaluate(tris) == n4
    # probe and path on the result
    scr = ("(k) => { const T = window.__xp.XP.three, r = T.renderer.domElement.getBoundingClientRect();"
           " const m = T.group.children.find(o => o.userData && o.userData.kind === 'mesh'), P = m.geometry.attributes.position.array;"
           " const V = Object.getPrototypeOf(T.camera.position).constructor; let best = 0, bx = -Infinity;"
           " for (let i = 0; i < P.length / 3; i++) { const s = k * P[3 * i] + P[3 * i + 2] * 1e-3; if (s > bx) { bx = s; best = i; } }"
           " const f = best - best % 3, c = new V(P[3 * f] + P[3 * f + 3] + P[3 * f + 6], P[3 * f + 1] + P[3 * f + 4] + P[3 * f + 7], P[3 * f + 2] + P[3 * f + 5] + P[3 * f + 8]).multiplyScalar(1 / 3);"
           " const v = new V(P[3 * best], P[3 * best + 1], P[3 * best + 2]).lerp(c, 0.5).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")
    page.click("#xp-tree [data-tp=results]")
    page.click("#xp-probe")
    page.mouse.click(*page.evaluate(scr, 1))
    page.wait_for_function("(window.__xp.XP.probes || []).length === 1")
    page.wait_for_selector("#xp-probeplot polyline")
    assert page.evaluate("window.__xp.XP.probeData.time.length") == 5 and page.evaluate("window.__xp.XP.probes[0].label").startswith("node ")
    page.click("#xp-probe")
    page.click("#xp-path")
    page.mouse.click(*page.evaluate(scr, -1))
    page.wait_for_function("window.__xp.XP.path && window.__xp.XP.path.length === 1")
    page.mouse.click(*page.evaluate(scr, 1))
    page.wait_for_function("window.__xp.XP.path && window.__xp.XP.path.length === 2")
    page.wait_for_selector("#xp-pathplot polyline")
    with page.expect_download() as dl:
        page.click("#xp-pcsv")
    assert "node " in open(dl.value.path()).read().splitlines()[0]
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
    """Import geometry: clean-up options (rebuild and fix on for a new import); a minimum volume removes the small solid
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
    wait_text(page, "#pt-cmdbody", "1 solid(s) below the minimum volume removed")
    wait_text(page, "#pt-info", "Volume 1 cm^3")
    assert page.evaluate("window.__part.PT.part.features[0].clean.min_volume") == 10


def test_part_import_surface_step(page, tmp_path):
    """Import geometry of a STEP file without solids (two labelled faces): the feature is replaced by one Import
    surface feature per component (LOWER, UPPER), each a surface body; the Component field lists the components."""
    from build123d import Compound, Face, Pos, export_step
    f1, f2 = Face.make_rect(100, 50), Pos(0, 0, 30) * Face.make_rect(100, 50)
    f1.label, f2.label = "LOWER", "UPPER"
    comp = Compound(children=[f1, f2])
    comp.label = "PANELS"
    path = str(tmp_path / "panels.step")
    export_step(comp, path)
    tab(page, "part")
    page.click("#tab-part [data-add=import]")
    page.wait_for_selector("#pf-path")
    page.fill("#pf-path", path)
    page.dispatch_event("#pf-path", "change")
    page.wait_for_function("window.__part.PT.part.features.length === 2 && window.__part.PT.part.features.every(f => f.type === 'surf_import')")
    feats = page.evaluate("window.__part.PT.part.features.map(f => [f.name, f.label])")
    assert feats == [["LOWER", "LOWER"], ["UPPER", "UPPER"]]
    page.wait_for_function("Object.values(window.__part.PT.status).filter(s => s.surface && s.faces === 1 && !s.error).length === 2")
    wait_text(page, "#status", "has no solids: 2 Import surface feature(s)")


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
    wait_text(page, "#pt-cmdbody", "7 planar, 2 cylindrical, 2 conical")
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


def test_sketch_dimension_circle_outline_gives_centre(page):
    """Dimension tool: a circle clicked on its outline, then a line: the distance from the circle centre to the line;
    a line, then a circle: the same; two circles: centre to centre; a circle, then empty space: its diameter."""
    tab(page, "sketch")
    page.click("#sk-new")
    page.keyboard.press("w")
    page.keyboard.type("0,0")
    page.keyboard.press("Enter")
    page.keyboard.type("100,60")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    page.keyboard.press("e")
    page.keyboard.type("30,30")
    page.keyboard.press("Enter")
    page.keyboard.type("12")
    page.keyboard.press("Enter")
    page.keyboard.type("70,30")
    page.keyboard.press("Enter")
    page.keyboard.type("10")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    page.wait_for_function("window.__sk.SK.doc.entities.filter(e => e.t === 'circle').length === 2")
    page.uncheck("#sk-driving")

    def click(xy):
        s = page.evaluate("(p) => window.__sk.S(p)", list(xy))
        box = page.locator("#sk-canvas svg").bounding_box()
        page.mouse.click(box["x"] + s[0], box["y"] + s[1])
    dims = lambda: page.evaluate("window.__sk.SK.doc.dims")
    c1, c2 = page.evaluate("window.__sk.SK.doc.entities.filter(e => e.t === 'circle').map(e => e.id)")
    bottom = page.evaluate("window.__sk.SK.doc.entities.find(e => e.t === 'line' && Math.abs(e.y1) < 1e-9 && Math.abs(e.y2) < 1e-9).id")
    page.click("#tab-sketch [data-tool=dim]")
    # circle 1 (R12) on its outline (away from the grips at 0, 90, 180, 270 deg and, at the small zoom of the test
    # window, from the centre grip), then the bottom line, then the position
    click((30 + 12 * math.cos(math.radians(-50)), 30 + 12 * math.sin(math.radians(-50))))
    wait_text(page, "#sk-hint", "distance from the centre")
    click((50, 0))
    click((45, -10))
    page.wait_for_function("window.__sk.SK.doc.dims.length === 1")
    d = dims()[0]
    assert d["type"] == "linear" and d["r1"] == {"e": c1, "k": "c"} and d["l2"] == bottom, d
    # the bottom line, then circle 2 on its outline
    click((80, 0))
    click((70 + 10 * math.cos(math.radians(40)), 30 + 10 * math.sin(math.radians(40))))
    click((85, -10))
    page.wait_for_function("window.__sk.SK.doc.dims.length === 2")
    d = dims()[1]
    assert d["type"] == "linear" and d["r1"] == {"e": c2, "k": "c"} and d["l2"] == bottom, d
    # circle 1, then circle 2: centre to centre
    click((30 + 12 * math.cos(math.radians(130)), 30 + 12 * math.sin(math.radians(130))))
    click((70 + 10 * math.cos(math.radians(50)), 30 + 10 * math.sin(math.radians(50))))
    click((50, 50))
    page.wait_for_function("window.__sk.SK.doc.dims.length === 3")
    d = dims()[2]
    assert d["type"] == "linear" and d["r1"] == {"e": c1, "k": "c"} and d["r2"] == {"e": c2, "k": "c"}, d
    # circle 2, then empty space: diameter
    click((70 + 10 * math.cos(math.radians(-40)), 30 + 10 * math.sin(math.radians(-40))))
    click((92, 12))
    page.wait_for_function("window.__sk.SK.doc.dims.length === 4")
    d = dims()[3]
    assert d["type"] == "diameter" and d["ent"] == c2, d


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
    page.click("#cmd-finish")
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
    page.click("#cmd-finish")
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
        # column width: the grip of the Name header dragged 60 px to the right widens the column; the width is kept
        # over a redraw (localStorage); a double-click on the grip restores the automatic widths
        w0 = page.evaluate("document.querySelector('#pj-docs th[data-sort=name]').offsetWidth")
        g = page.locator("#pj-docs th[data-sort=name] .pj-grip").bounding_box()
        page.mouse.move(g["x"] + g["width"] / 2, g["y"] + g["height"] / 2)
        page.mouse.down()
        page.mouse.move(g["x"] + g["width"] / 2 + 60, g["y"] + g["height"] / 2, steps=4)
        page.mouse.up()
        w1 = page.evaluate("document.querySelector('#pj-docs th[data-sort=name]').offsetWidth")
        assert abs(w1 - (w0 + 60)) <= 2, (w0, w1)
        assert names == page.evaluate("() => [...document.querySelectorAll('#pj-docs tr[data-name]')].map(r => r.dataset.name)")   # no sort by the drag
        page.click("#pj-refresh")
        page.wait_for_function("document.querySelector('#pj-docs th[data-sort=name]').offsetWidth === %d" % w1)
        page.dblclick("#pj-docs th[data-sort=name] .pj-grip")
        page.wait_for_function("document.querySelector('#pj-docs table').style.tableLayout === ''")
        assert page.evaluate("localStorage.getItem('pj-colw-docs-links')") is None
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
    """Ctrl+K opens the command search; "stl" lists Import geometry of the Part tab first; Enter starts it in the Part
    tab; Esc closes the window."""
    tab(page, "project")
    page.keyboard.press("Control+k")
    page.wait_for_selector("#cmd-search:not([hidden])")
    assert page.evaluate("document.activeElement.id") == "cs-input"
    page.keyboard.type("stl")
    first = page.locator("#cs-list .cs-item").first
    assert first.locator("b").inner_text() == "Import geometry" and "Part" in first.inner_text()
    page.keyboard.press("Enter")
    assert page.is_hidden("#cmd-search")
    assert not page.is_hidden("#tab-part")
    page.wait_for_function("(() => { const P = window.__part; return P.PT.cmd && P.feat(P.PT.cmd.id).type === 'import'; })()")
    page.evaluate("window.__part.cancelCommand()")
    page.click("#cs-input")
    page.keyboard.type("fillet")
    assert page.locator("#cs-list .cs-item").count() >= 1
    page.keyboard.press("Escape")
    assert page.is_hidden("#cmd-search")


def test_part_sketch_on_sketch_curve_end_and_tool_sweep(page, client):
    """A click on a sketch curve in the Plane section of Sketch sets the plane normal to the curve at the end
    nearer the click; Sweep with Moving tool shows the tool axis and removes the V groove."""
    from test_models import _sweep_part
    pp = _sweep_part()
    pp["name"] = "ui_sw"
    client.put("/api/part/file/ui_sw", json=pp)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_sw')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length > 0 && window.__part.PT.status.sw", timeout=60000)
    assert page.evaluate("window.__part.PT.status.sw.error") is None
    page.evaluate("window.__part.selectItem('sw')")
    page.evaluate("window.__part.startCommand('sweep', null, 'sw')")
    page.wait_for_selector("#pf-saxis")
    assert page.input_value("#pf-skind") == "tool" and page.input_value("#pf-saxis") == "auto"
    assert page.input_value("#pf-stoolat") == "path"
    # a click on the line x = 3 of the profile (the right side of the V, on XZ) makes it the tool axis
    i = page.evaluate("window.__part.commandSteps(window.__part.feat('sw')).findIndex(s => s.key === 'tool_axis')")
    page.evaluate("window.__part.gotoStep(%d)" % i)
    page.evaluate("window.__part.addHits([{kind: 'sketch', id: 'sq', point: [1.5, 0, 2]}])")
    assert page.evaluate("window.__part.feat('sw').axis") == 12
    page.wait_for_selector("#pf-stoolat")
    assert page.input_value("#pf-stoolat") == "drawn"
    # a construction line of the profile sketch (x = 0, z from -1 to 6, drawn dashed) clicked in the view at
    # (0, 0, 5): it becomes the tool axis; the hover text names the line under the cursor
    page.evaluate("""(() => { const P = window.__part, sq = P.feat('sq');
        sq.sketch.entities.push({ id: 14, t: 'line', x1: 0, y1: -1, x2: 0, y2: 6, constr: true, layer: '0' }); P.changedPart(); })()""")
    page.wait_for_function("window.__part.PT.sketchObjs.some(o => o.userData.id === 'sq' && o.userData.constr)")
    i = page.evaluate("window.__part.commandSteps(window.__part.feat('sw')).findIndex(s => s.key === 'tool_axis')")
    page.evaluate("window.__part.gotoStep(%d)" % i)
    page.wait_for_selector("#pf-saxis")
    xy = page.evaluate("""() => { const P = window.__part, t = P.PT.three, r = t.renderer.domElement.getBoundingClientRect();
        const v = new P.THREE.Vector3(0, 0, 5).project(t.camera);
        return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }""")
    page.mouse.move(*xy)
    h = page.evaluate("window.__part.PT.hover")
    assert h and h["kind"] == "sketch" and h["id"] == "sq", h
    assert page.evaluate("window.__part.hoverText(window.__part.PT.hover)").startswith("Construction line 14 (0, -1) - (0, 6) of Profile")
    page.mouse.click(*xy)
    page.wait_for_function("window.__part.feat('sw').axis === 14")
    assert page.input_value("#pf-saxis") == "14"
    page.select_option("#pf-skind", "profile")
    page.wait_for_selector("#pf-saxis", state="detached")
    page.evaluate("window.__part.cancelCommand()")
    page.click("#tab-part [data-add=sketch]")
    page.wait_for_selector("#pf-plane")
    page.evaluate("window.__part.addHits([{kind: 'sketch', id: 'sp', point: [11, 9.8, 2]}])")
    f = page.evaluate("window.__part.feat(window.__part.PT.cmd.id)")
    assert f["plane"] == "normal" and f["plane_sketch_curve"]["sketch"] == "sp" and f["plane_t"] is None
    assert "Normal to Path at the nearer end" in page.inner_text("#pt-cmdbody")
    page.evaluate("window.__part.cancelCommand()")
    # Origin step of a new sketch on XY: a click on the path curve near its end (11, 10, 2) puts the origin there
    page.click("#tab-part [data-add=sketch]")
    page.wait_for_selector("#pf-plane")
    i = page.evaluate("window.__part.commandSteps(window.__part.feat(window.__part.PT.cmd.id)).findIndex(s => s.key === 'origin')")
    page.evaluate("window.__part.gotoStep(%d)" % i)
    page.evaluate("window.__part.addHits([{kind: 'sketch', id: 'sp', point: [11, 8, 2]}])")
    f = page.evaluate("window.__part.feat(window.__part.PT.cmd.id)")
    assert f["plane_origin"] == pytest.approx([11, 10, 2], abs=1e-6), f
    page.evaluate("window.__part.cancelCommand()")


def test_part_command_window(page, client):
    """Command window over the view: all sections of Fillet at once (Edges and Radius); a field of Radius makes it
    the active section; Select shown with Radius active adds the edges to Edges; the edges are listed as chips and
    × removes one; the title bar moves the window and the place is kept for the next command; Esc closes it. The
    body list shows colour marks and no volumes; Configurations is folded by default."""
    pp = plate("ui_cw")
    pp["body_colors"] = {"solid:0": "#ff0000"}
    client.put("/api/part/file/ui_cw", json=pp)
    tab(page, "part")
    page.evaluate("try { localStorage.removeItem('pt-cmdwin-pos'); localStorage.removeItem('pt-cfg-open'); } catch (e) {}")
    page.evaluate("window.__partLoadNamed('ui_cw')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length > 0", timeout=60000)
    tree = page.inner_text("#pt-features")
    assert "cm^3" not in tree
    assert page.evaluate("getComputedStyle(document.querySelector(\"#pt-features .pt-feat[data-id='solid:0'] .swatch\")).backgroundColor") == "rgb(255, 0, 0)"
    assert page.is_hidden("#pt-configs")
    page.click("#pt-cfg-toggle")
    assert page.is_visible("#pt-configs")
    page.click("#pt-cfg-toggle")
    page.click("#tab-part [data-add=fillet]")
    page.wait_for_selector("#pt-cmdwin:not([hidden])")
    assert page.inner_text("#pt-cmdwin-title") == "Fillet"
    assert page.locator("#pt-cmdbody .cw-sec").count() == 2
    assert page.is_visible("#pf-value")
    assert "Fillet 1 is open in the command window" in page.inner_text("#pt-props")
    page.focus("#pf-value")
    page.wait_for_function("window.__part.PT.cmd.step === 1")
    assert page.locator("#pt-cmdbody .cw-sec.active[data-step='1']").count() == 1
    page.evaluate("document.activeElement.blur()")                  # a click in the view takes the focus
    n = page.evaluate("window.__part.selectShown()")
    assert n > 0
    page.wait_for_function("window.__part.PT.cmd.step === 0")
    ne = page.evaluate("window.__part.feat(window.__part.PT.cmd.id).edges.length")
    assert ne == n and page.locator("#pt-cmdbody .cw-chip").count() == min(ne, 40)
    page.click("#pt-cmdbody .cw-chip [data-cwdel='0']")
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).edges.length === %d" % (ne - 1))
    box = page.locator("#pt-cmdwin-head").bounding_box()
    x0 = page.evaluate("document.querySelector('#pt-cmdwin').offsetLeft")
    page.mouse.move(box["x"] + 40, box["y"] + 10)
    page.mouse.down()
    page.mouse.move(box["x"] + 240, box["y"] + 90, steps=5)
    page.mouse.up()
    x1 = page.evaluate("document.querySelector('#pt-cmdwin').offsetLeft")
    assert x1 - x0 > 150
    page.keyboard.press("Escape")
    page.wait_for_selector("#pt-cmdwin", state="hidden")
    page.click("#tab-part [data-add=chamfer]")
    page.wait_for_selector("#pt-cmdwin:not([hidden])")
    assert abs(page.evaluate("document.querySelector('#pt-cmdwin').offsetLeft") - x1) < 2
    page.evaluate("window.__part.cancelCommand()")


def test_part_settings_kept_for_next_use(page, client):
    """A finished Fillet keeps its radius and a finished Boolean its sliver thickness for the next new feature of the
    same type, also after a reload (config.local.json "part_last"); picks are not kept; a cancelled command keeps
    nothing."""
    client.put("/api/part/file/ui_last", json=plate("ui_last"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_last')")
    page.wait_for_function("window.__part.PT.solids.length === 1", timeout=60000)
    page.evaluate("() => { const P = window.__part; P.startCommand('fillet'); const f = P.PT.part.features.slice(-1)[0]; f.value = 0.75; f.edges = [{mid: [0, 0, 0], len: 1}]; P.finishCommand(); }")
    assert page.evaluate("window.__part.PT.lastSave") is True
    assert client.get("/api/part/last").get_json()["fillet"] == {"value": 0.75}
    page.evaluate("() => { const P = window.__part; P.startCommand('boolean'); const f = P.PT.part.features.slice(-1)[0]; f.min_thickness = 0.05; P.cancelCommand(); }")
    assert "boolean" not in client.get("/api/part/last").get_json()
    page.reload()
    page.wait_for_function("window.__part && window.__part.PT.last && window.__part.PT.last.fillet")
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_last')")
    page.wait_for_function("window.__part.PT.solids.length >= 0 && window.__part.PT.part && window.__part.PT.part.name === 'ui_last'", timeout=60000)
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length > 0", timeout=60000)
    f = page.evaluate("() => { const P = window.__part; P.startCommand('fillet'); return P.PT.part.features.slice(-1)[0]; }")
    assert f["value"] == 0.75 and f["edges"] == []
    page.evaluate("window.__part.cancelCommand()")
    page.evaluate("() => { const P = window.__part; P.startCommand('boolean'); const f = P.PT.part.features.slice(-1)[0]; f.min_thickness = 0.05; f.targets = [0]; f.tools = [0]; P.finishCommand(); }")
    assert page.evaluate("window.__part.PT.lastSave") is True
    assert client.get("/api/part/last").get_json()["boolean"]["min_thickness"] == 0.05
    f = page.evaluate("() => { const P = window.__part; P.startCommand('boolean'); return P.PT.part.features.slice(-1)[0]; }")
    assert f["min_thickness"] == 0.05 and f["targets"] == []
    page.evaluate("window.__part.cancelCommand()")


def test_part_body_show_only(page, client):
    """Show only of a body in the tree hides the other solids and surface bodies; Show all in the Bodies header and
    in Properties shows them again."""
    pp = plate("ui_only")
    pp["features"].append({"id": "c1", "name": "Copy body 1", "type": "body_copy", "bodies": [0], "surfaces": [], "move": [0, 0, 40]})
    client.put("/api/part/file/ui_only", json=pp)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_only')")
    page.wait_for_function("window.__part.PT.solids.length === 2", timeout=60000)
    page.click("#pt-features .pt-feat[data-id='solid:1'] button[data-k=only]")
    assert page.evaluate("[!!window.__part.PT.hidden['solid:0'], !!window.__part.PT.hidden['solid:1']]") == [True, False]
    assert page.evaluate("window.__part.PT.faceObjs.filter(o => o.userData.solid === 0).every(o => !o.visible)")
    page.click("#pt-showall")
    assert page.evaluate("Object.values(window.__part.PT.hidden).filter(Boolean).length") == 0
    page.click("#pt-features .pt-feat[data-id='solid:0'] .nm")
    page.click("#pp-only")
    assert page.evaluate("[!!window.__part.PT.hidden['solid:0'], !!window.__part.PT.hidden['solid:1']]") == [False, True]
    page.click("#pp-showall")
    assert page.evaluate("Object.values(window.__part.PT.hidden).filter(Boolean).length") == 0


def test_part_body_groups(page, client):
    """The tree lists solids, surface bodies and curve bodies in their own sections; the eye of a section header
    hides every body of the section and, when all are hidden, shows them again."""
    from drawgen import part
    pp = plate("ui_grp")
    base, _ = part.build(pp)
    top = [f for f in base.faces() if abs(f.center().Z - 20) < 1e-6][0]
    pp["features"].append({"id": "x1", "name": "Extract surface 1", "type": "surf_extract", "faces": [part.face_key(top)], "offset": 0})
    client.put("/api/part/file/ui_grp", json=pp)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_grp')")
    page.wait_for_function("window.__part.PT.solids.length === 1 && !!window.__part.PT.surfaces['x1']", timeout=60000)
    heads = page.evaluate("[...document.querySelectorAll('#pt-features .pt-sub')].map(e => e.textContent.trim())")
    assert heads == ["Solids", "Surfaces"], heads
    assert page.evaluate("window.__part.bodyGroupIds('solid')") == ["solid:0"]
    assert page.evaluate("window.__part.bodyGroupIds('surface')") == ["x1"]
    page.click("#pt-features [data-grp=surface]")
    assert page.evaluate("[!!window.__part.PT.hidden['solid:0'], !!window.__part.PT.hidden['x1']]") == [False, True]
    assert page.evaluate("document.querySelector('#pt-features [data-grp=surface]').classList.contains('off')")
    page.click("#pt-features [data-grp=solid]")
    assert page.evaluate("[!!window.__part.PT.hidden['solid:0'], !!window.__part.PT.hidden['x1']]") == [True, True]
    assert page.evaluate("window.__part.PT.faceObjs.filter(o => o.userData.solid === 0).every(o => !o.visible)")
    page.click("#pt-features [data-grp=solid]")
    assert page.evaluate("[!!window.__part.PT.hidden['solid:0'], !!window.__part.PT.hidden['x1']]") == [False, True]
    page.click("#pt-showall")
    assert page.evaluate("Object.values(window.__part.PT.hidden).filter(Boolean).length") == 0
    # Show menu: Hide all, Invert, Solids only, Surfaces only, Show all
    hidden = lambda: page.evaluate("[!!window.__part.PT.hidden['solid:0'], !!window.__part.PT.hidden['x1']]")
    for btn, want in (("#pt-hide-all", [True, True]), ("#pt-show-invert", [False, False]), ("#pt-show-solids", [False, True]), ("#pt-show-surfaces", [True, False]), ("#pt-show-all", [False, False])):
        page.click("#tab-part .dd-btn:has-text('Show')")
        page.click(btn)
        assert hidden() == want, (btn, hidden())


def test_part_pick_panel_chips(page, client):
    """A parameter panel with a Pick faces button (Offset faces) lists the picked faces as chips: a click on a chip
    keeps its face highlighted (PT.chipPin), a second click releases it, × removes the face, Clear removes all."""
    client.put("/api/part/file/ui_chips", json=plate("ui_chips"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_chips')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.face_keys && window.__part.PT.mesh.face_keys.length > 0", timeout=60000)
    page.evaluate("window.__part.startCommand('offset_faces')")
    page.wait_for_selector("#pt-cmdbody button[data-pick=faces]")
    n = page.evaluate("window.__part.selectShown()")
    assert n > 0
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).faces.length === %d" % n)
    assert page.locator("#pt-cmdbody .cw-chips[data-prop=faces] .cw-chip").count() == min(n, 40)
    page.click("#pt-cmdbody .cw-chip[data-i='0']")
    assert page.evaluate("!!window.__part.PT.chipPin") and page.locator("#pt-cmdbody .cw-chip.on").count() == 1
    page.click("#pt-cmdbody .cw-chip[data-i='0']")
    assert page.evaluate("window.__part.PT.chipPin === null") and page.locator("#pt-cmdbody .cw-chip.on").count() == 0
    page.click("#pt-cmdbody .cw-chip [data-cwdel='0']")
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).faces.length === %d" % (n - 1))
    page.click("#pt-cmdbody button[data-clear=faces]")
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).faces.length === 0")
    assert page.locator("#pt-cmdbody .cw-chip").count() == 0
    page.evaluate("window.__part.cancelCommand()")


def test_part_body_scale(page, client):
    """Scale body from the tree: the command opens at the factor; a factor of 2 about the bounding box centre gives
    8 times the volume; non-uniform factors show X, Y, Z fields; the Point reference adds the Point step."""
    client.put("/api/part/file/ui_scale", json=plate("ui_scale"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_scale')")
    page.wait_for_function("window.__part.PT.solids.length === 1", timeout=60000)
    v0 = page.evaluate("window.__part.PT.solids[0].volume_mm3")
    page.click("#pt-features .pt-feat[data-id='solid:0'] button[data-k=bscale]")
    page.wait_for_selector("#pf-sfac")
    page.select_option("#pf-sabout", "bbox")
    page.wait_for_selector("#pf-sfac")
    page.fill("#pf-sfac", "2")
    page.dispatch_event("#pf-sfac", "change")
    page.click("#cmd-finish")
    page.wait_for_function("window.__part.PT.solids.length === 1 && Math.abs(window.__part.PT.solids[0].volume_mm3 - 8 * %r) < 1e-3 * 8 * %r" % (v0, v0), timeout=60000)
    f = page.evaluate("window.__part.PT.part.features.slice(-1)[0]")
    assert f["type"] == "body_scale" and f["bodies"] == [0] and f["about"] == "bbox" and f["factor"] == 2
    assert page.evaluate("window.__part.PT.status[window.__part.PT.part.features.slice(-1)[0].id].error") is None
    page.evaluate("window.__part.startCommand('body_scale', {bodies: [0], surfaces: []})")
    page.wait_for_selector("#pf-suni")
    page.uncheck("#pf-suni")
    page.wait_for_selector("#pf-sfacsx")
    page.select_option("#pf-sabout", "point")
    page.wait_for_selector("#pf-sptx")
    labels = page.evaluate("window.__part.commandSteps(window.__part.PT.part.features.slice(-1)[0]).map(s => s.label)")
    assert labels == ["Bodies to scale", "Scale", "Point"], labels


def test_part_body_delete_copy_colour_and_rough_mesh(page, client, tmp_path):
    """Bodies in the tree: copy (Copy body opens at the move vector), delete (Delete body feature added), colour in
    Properties; a rough STL import is an opaque mesh body, and Measure picks points on it."""
    from build123d import Box, export_stl
    stl = str(tmp_path / "rough.stl")
    export_stl(Box(10, 10, 10), stl)
    pp = plate("ui_bodies")
    pp["features"].append({"id": "r1", "name": "Import geometry 2", "type": "import", "path": stl, "part": None,
                           "stl": {"mode": "rough"}, "clean": {}})
    client.put("/api/part/file/ui_bodies", json=pp)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_bodies')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.r1 && window.__part.PT.solids.length === 1", timeout=60000)
    assert page.evaluate("window.__part.PT.status.r1.mesh") is True
    # copy the solid: the command opens at the move vector
    page.click("#pt-features .pt-feat[data-id='solid:0'] button[data-k=bcopy]")
    page.wait_for_selector("#pf-bmovez")
    page.fill("#pf-bmovez", "40")
    page.dispatch_event("#pf-bmovez", "change")
    page.click("#cmd-finish")
    page.wait_for_function("window.__part.PT.solids.length === 2", timeout=60000)
    # delete the mesh body: a Delete body feature, applied at once
    page.click("#pt-features .pt-feat[data-id='r1'] button[data-k=bdel]")
    page.wait_for_function("!window.__part.PT.surfaces.r1", timeout=60000)
    types = page.evaluate("window.__part.PT.part.features.map(f => f.type)")
    assert types[-2:] == ["body_copy", "body_delete"]
    assert page.evaluate("window.__part.PT.part.features.slice(-1)[0].surfaces") == ["r1"]
    # colour of solid 2
    page.click("#pt-features .pt-feat[data-id='solid:1'] .nm")
    page.wait_for_selector("#pp-color")
    page.evaluate("() => { const c = document.querySelector('#pp-color'); c.value = '#ff0000'; c.dispatchEvent(new Event('input')); }")
    assert page.evaluate("window.__part.PT.part.body_colors['solid:1']") == "#ff0000"
    assert page.evaluate("window.__part.PT.faceObjs.find(o => o.userData.solid === 1).material.color.getHexString()") == "ff0000"
    page.click("#pp-colordef")
    assert page.evaluate("Object.keys(window.__part.PT.part.body_colors || {}).length") == 0
    # measure: points on a mesh body (undo the delete first)
    page.evaluate("() => { const P = window.__part.PT; P.part.features.pop(); }")
    page.evaluate("window.__part.changedPart()")
    page.wait_for_function("window.__part.PT.surfaces.r1", timeout=60000)
    page.evaluate("window.__part.setMeasure(true)")
    page.evaluate("window.__part.measureClick({kind: 'face', surface: 'r1', fi: 0, point: [0, 0, 5]})")
    page.evaluate("window.__part.measureClick({kind: 'face', surface: 'r1', fi: 1, point: [3, 4, 5]})")
    page.wait_for_function("window.__part.PT.measure && window.__part.PT.measure.res", timeout=30000)
    rows = page.evaluate("window.__part.PT.measure.res.rows")
    assert any(r[0] == "Minimum distance" and r[1].startswith("5.0000") for r in rows), rows
    page.evaluate("window.__part.setMeasure(false)")


def test_sketch_earlier_sketches_toggle(page, client):
    """Sketch bar: Earlier sketches hides and shows the curves of the earlier sketches; Model edges stays separate."""
    from conftest import rect
    pp = {"name": "ui_esr", "version": 2, "features": [
        {"id": "s1", "name": "Sketch 1", "type": "sketch", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20), "layers": [{"name": "0", "on": True}]}},
        {"id": "s2", "name": "Sketch 2", "type": "sketch", "plane": "XY", "offset": 0, "sketch": {"entities": [], "layers": [{"name": "0", "on": True}]}}]}
    client.put("/api/part/file/ui_esr", json=pp)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_esr')")
    page.wait_for_selector("#pt-features .pt-feat[data-id=s2]")
    page.dblclick("#pt-features .pt-feat[data-id=s2] .nm")
    page.wait_for_function("window.__sk.SK.refs && window.__sk.SK.refs.some(e => e.src === 'sketch')", timeout=30000)
    assert page.is_visible("#sk-sketchrefs")
    count = lambda: page.evaluate("document.querySelectorAll('#sk-canvas [stroke=\"#9aa3b0\"]').length")
    n0 = count()
    assert n0 >= 1
    page.uncheck("#sk-sketchrefs")
    assert count() < n0
    page.check("#sk-sketchrefs")
    assert count() == n0


def test_sketch_hidden_lines_cut_and_shaded(page, client):
    """Sketch bar of a feature sketch through a plate with a hole (XZ through the hole centre): Hidden lines hides
    the dotted edges; Cut at plane reads the reference geometry of the model cut at the plane (the hole no longer
    hidden lines) and Flip the other half; the shaded model is a canvas under the sketch that follows the view and
    is hidden by Shaded; the canvas is removed when the sketch is closed. The settings are kept for the next sketch."""
    pp = plate("ui_cut")
    pp["features"].append({"id": "s9", "name": "Sketch 9", "type": "sketch", "plane": "XZ", "offset": -25, "sketch": {"entities": [], "layers": [{"name": "0", "on": True}]}})
    client.put("/api/part/file/ui_cut", json=pp)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_cut')")
    page.wait_for_selector("#pt-features .pt-feat[data-id=s9]")
    page.dblclick("#pt-features .pt-feat[data-id=s9] .nm")
    page.wait_for_function("window.__sk.SK.refs && window.__sk.SK.refs.some(e => e.kind === 'hidden')", timeout=30000)
    hidden = lambda: page.evaluate("document.querySelectorAll('#sk-canvas [stroke=\"#b8bfc9\"]').length")
    assert hidden() == 4
    assert page.is_visible("#sk-hidden") and page.is_visible("#sk-cut") and page.is_visible("#sk-cutflip") and page.is_visible("#sk-shaded")
    page.uncheck("#sk-hidden")
    assert hidden() == 0
    page.check("#sk-hidden")
    assert hidden() == 4
    # the shaded model: a canvas under the SVG, sized like the sketch box, hidden by Shaded
    assert page.evaluate("document.querySelector('#sk-canvas').firstElementChild.classList.contains('sk-underlay')")
    assert page.evaluate("Math.abs(document.querySelector('#sk-canvas canvas.sk-underlay').clientWidth - document.querySelector('#sk-canvas').clientWidth) <= 1")
    page.uncheck("#sk-shaded")
    assert page.evaluate("document.querySelector('#sk-canvas canvas.sk-underlay').hidden")
    page.check("#sk-shaded")
    assert not page.evaluate("document.querySelector('#sk-canvas canvas.sk-underlay').hidden")
    # cut at the plane: the hole's four hidden lines become visible edges of the kept half (two) and the frame's
    # section is unchanged; Flip keeps the other half
    assert page.is_disabled("#sk-cutflip")
    page.check("#sk-cut")
    page.wait_for_function("window.__sk.SK.cutMode === 'front' && window.__sk.SK.refs.filter(e => e.kind === 'hidden').length < 4", timeout=30000)
    assert not page.is_disabled("#sk-cutflip")
    proj = "JSON.stringify(window.__sk.SK.refs.filter(e => e.kind === 'proj').map(e => [e.x1, e.y1, e.x2, e.y2].map(v => Math.round(v))).sort())"
    p_front = page.evaluate(proj)
    page.check("#sk-cutflip")
    page.wait_for_function("window.__sk.SK.cutMode === 'back'")
    page.wait_for_function("([s, p]) => eval(s) !== p", arg=[proj, p_front], timeout=30000)
    assert page.evaluate("window.__sk.SK.refs.filter(e => e.kind === 'section').length") == 8
    page.uncheck("#sk-cut")
    page.wait_for_function("window.__sk.SK.cutMode === null && window.__sk.SK.refs.filter(e => e.kind === 'hidden').length === 4", timeout=30000)
    page.uncheck("#sk-hidden")
    page.click("#sk-partcancel")
    page.wait_for_selector("#sk-partbar", state="hidden")
    assert page.evaluate("!document.querySelector('#sk-canvas canvas.sk-underlay')")
    # the next sketch keeps the setting
    page.dblclick("#pt-features .pt-feat[data-id=s9] .nm")
    page.wait_for_function("window.__sk.SK.refs && window.__sk.SK.refs.some(e => e.kind === 'hidden')", timeout=30000)
    assert not page.is_checked("#sk-hidden") and hidden() == 0
    page.check("#sk-hidden")
    page.click("#sk-partcancel")
    page.wait_for_selector("#sk-partbar", state="hidden")


def test_sketch_behind_plane_hover_snap_isolate(page, client):
    """Feature sketch 10 mm above a plate: the model edges behind the plane are drawn at 10 % opacity and the shaded
    model behind it is a 10 % copy (Behind plane dim); hide removes them, show draws them as before. Isolate (key I)
    hides the model edges and clips the shaded model to the plane, I again restores. Hover to snap: a corner of an
    earlier sketch snaps only after the cursor rested on its edge."""
    from conftest import rect
    pp = plate("ui_bh")
    pp["features"].append({"id": "s9", "name": "Sketch 9", "type": "sketch", "plane": "XY", "offset": 30, "sketch": {"entities": [], "layers": [{"name": "0", "on": True}]}})
    client.put("/api/part/file/ui_bh", json=pp)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_bh')")
    page.wait_for_selector("#pt-features .pt-feat[data-id=s9]")
    page.dblclick("#pt-features .pt-feat[data-id=s9] .nm")
    page.wait_for_function("window.__sk.SK.refs && window.__sk.SK.refs.some(e => e.kind === 'proj')", timeout=30000)
    assert page.evaluate("window.__sk.SK.refs.filter(e => e.kind === 'proj').every(e => e.behind)")
    proj = lambda: page.evaluate("document.querySelectorAll('#sk-canvas [stroke=\"#9aa3b0\"]').length")
    dim = lambda: page.evaluate("document.querySelectorAll('#sk-canvas [stroke=\"#9aa3b0\"][stroke-opacity=\"0.1\"]').length")
    ul = lambda: page.evaluate("window.__sk.SK.partEdit.underlay.state()")
    n = proj()
    assert n > 0 and dim() == n and page.input_value("#sk-behind") == "dim" and ul()["backVisible"]
    page.select_option("#sk-behind", "hide")
    assert proj() == 0 and not ul()["backVisible"]
    page.select_option("#sk-behind", "show")
    assert proj() == n and dim() == 0 and not ul()["backVisible"] and ul()["front"] == [0]
    page.select_option("#sk-behind", "dim")
    page.click("#sk-canvas")
    page.keyboard.press("i")
    assert page.evaluate("window.__sk.SK.isolate") and page.is_checked("#sk-isolate") and proj() == 0
    assert ul()["isolate"] and ul()["front"] == [2]
    page.keyboard.press("i")
    assert not page.evaluate("window.__sk.SK.isolate") and dim() == n
    page.click("#sk-partcancel")
    page.wait_for_selector("#sk-partbar", state="hidden")
    # hover to snap: an earlier sketch (40 x 20 rectangle) in front of the sketch plane
    sp = {"name": "ui_hs", "version": 2, "features": [
        {"id": "s1", "name": "Sketch 1", "type": "sketch", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20, 30, 30), "layers": [{"name": "0", "on": True}]}},
        {"id": "s2", "name": "Sketch 2", "type": "sketch", "plane": "XY", "offset": -5, "sketch": {"entities": [], "layers": [{"name": "0", "on": True}]}}]}
    client.put("/api/part/file/ui_hs", json=sp)
    page.evaluate("window.__partLoadNamed('ui_hs')")
    page.wait_for_selector("#pt-features .pt-feat[data-id=s2]")
    page.dblclick("#pt-features .pt-feat[data-id=s2] .nm")
    page.wait_for_function("window.__sk.SK.refs && window.__sk.SK.refs.some(e => e.src === 'sketch')", timeout=30000)
    page.click("#sk-canvas")
    page.keyboard.press("q")
    scr = lambda x, y: page.evaluate("([x, y]) => { const r = document.querySelector('#sk-canvas svg').getBoundingClientRect(), S = window.__sk.S([x, y]); return [r.left + S[0], r.top + S[1]]; }", [x, y])
    page.mouse.move(*scr(70, 49.5))
    assert not page.evaluate("window.__sk.SK.snap && window.__sk.SK.snap.kind")
    page.wait_for_function("window.__sk.SK.awake.size === 1", timeout=5000)
    page.mouse.move(*scr(70.2, 49.8))
    assert page.evaluate("window.__sk.SK.snap.kind") == "end" and page.evaluate("window.__sk.SK.snap.p") == [70, 50]
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    assert page.evaluate("window.__sk.SK.awake.size") == 0
    page.click("#sk-partcancel")
    page.wait_for_selector("#sk-partbar", state="hidden")


def test_part_3d_sketch(page, client):
    """3D sketch (Curve through points in space) on a plate with a hole: a vertex, the centre of the hole edge and a
    grid point of the XY grid through the last point picked in the view; Shift: along the grid normal; key Y: the XZ
    grid; a typed point relative to the last one; Backspace removes it; the curve body is built."""
    pp = plate("ui_3ds")
    client.put("/api/part/file/ui_3ds", json=pp)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_3ds')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    page.evaluate("window.__part.startCommand('curve_points', {space: true})")
    page.wait_for_selector("#pf-sgax")
    cid = page.evaluate("window.__part.PT.cmd.id")
    assert page.evaluate("id => window.__part.feat(id).name", cid) == "3D sketch 1"
    scr = ("(p) => { const T = window.__part.PT.three, r = T.renderer.domElement.getBoundingClientRect();"
           " const v = new window.__part.THREE.Vector3(...p).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")
    def at(q):                         # after the layout of the command window has settled (two frames)
        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        return page.evaluate(scr, q)
    snap = lambda: page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(window.__part.PT.spaceHover && [window.__part.PT.spaceHover.snap, window.__part.PT.spaceHover.point]))))")
    pts = lambda: page.evaluate("id => window.__part.feat(id).points", cid)
    page.mouse.move(*at([100, 0, 20]))
    assert snap() == ["vertex", [100, 0, 20]]
    page.mouse.click(*at([100, 0, 20]))
    page.wait_for_function("id => window.__part.feat(id).points.length === 1", arg=cid)
    page.mouse.move(*at([50, 25, 20]))
    assert snap() == ["centre", [50, 25, 20]]
    page.mouse.click(*at([50, 25, 20]))
    page.wait_for_function("id => window.__part.feat(id).points.length === 2", arg=cid)
    g = page.evaluate("id => window.__part.spaceGrid(window.__part.feat(id))", cid)
    assert g["axis"] == "z" and g["anchor"] == [50, 25, 20] and g["step"] == 5
    page.mouse.move(*at([70.8, 41.3, 20]))
    s0 = snap()
    assert s0[0] == "grid XY" and s0[1] == [70, 40, 20], s0
    page.mouse.click(*at([70.8, 41.3, 20]))
    page.wait_for_function("id => window.__part.feat(id).points.length === 3", arg=cid)
    page.keyboard.down("Shift")
    page.mouse.move(*at([70, 40, 41]))
    s1 = snap()
    page.keyboard.up("Shift")
    assert s1[0] == "along Z" and s1[1][:2] == [70, 40] and s1[1][2] % 5 == 0 and s1[1][2] > 20, s1
    page.keyboard.press("y")
    assert page.evaluate("id => window.__part.feat(id).grid.axis", cid) == "y" and page.input_value("#pf-sgax") == "y"
    page.check("#pf-srel")
    page.fill("#pf-sxyz", "0, 0, 15")
    page.click("#pf-sadd")
    page.wait_for_function("id => window.__part.feat(id).points.length === 4", arg=cid)
    assert pts()[3] == [70, 40, 35]
    page.mouse.move(*at([20, 20, 60]))
    page.keyboard.press("Backspace")
    page.wait_for_function("id => window.__part.feat(id).points.length === 3", arg=cid)
    page.wait_for_function("id => window.__part.PT.status[id] && !window.__part.PT.status[id].pending && window.__part.PT.surfaces[id]", arg=cid, timeout=60000)
    page.click("#cmd-finish")
    page.wait_for_function("!window.__part.PT.cmd")
    assert page.evaluate("id => window.__part.feat(id).points", cid) == [[100, 0, 20], [50, 25, 20], [70, 40, 20]]
    assert page.evaluate("window.__part.PT.three.space.children.length") == 0


def test_part_delete_or_suppress_shows_consumed_bodies(page, client):
    """The bodies a feature consumed (hidden when it was made) are shown when the feature is suppressed or deleted,
    and hidden again when it is unsuppressed."""
    from conftest import part_rec, rect
    p = part_rec("ui_cons", [
        {"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 1)}},
        {"id": "b", "name": "B", "type": "surf_sketch", "kind": "planar", "plane": "XZ", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 1)}},
        {"id": "s", "name": "Sew 1", "type": "surf_sew", "sources": ["a", "b"], "tolerance": 0.001}])
    client.put("/api/part/file/ui_cons", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_cons')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.s")
    hidden = lambda: page.evaluate("[!!window.__part.PT.hidden.a, !!window.__part.PT.hidden.b, !!window.__part.PT.hidden.s]")
    assert hidden() == [True, True, False]
    page.uncheck("#pt-features .pt-feat[data-id=s] input[data-k=on]")
    page.wait_for_function("window.__part.feat('s').suppressed")
    assert hidden() == [False, False, False]
    page.check("#pt-features .pt-feat[data-id=s] input[data-k=on]")
    page.wait_for_function("!window.__part.feat('s').suppressed")
    assert hidden() == [True, True, False]
    page.click("#pt-features .pt-feat[data-id=s] button[data-k=del]")
    page.wait_for_function("!window.__part.feat('s')")
    assert hidden()[:2] == [False, False]


def test_part_blend_curve_and_curve_through_points(page, client):
    """Blend curve: the ends fed as an edge end of the solid and a vertex; the continuity select and the result note.
    Curve through points: vertices as chips, a chip removed, the method changed to spline; the bodies appear under
    Curves in the tree. Partition with a surface has the Extend field."""
    client.put("/api/part/file/ui_blend", json=plate("ui_blend"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_blend')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.edge_keys && window.__part.PT.mesh.edge_keys.length > 0", timeout=60000)
    page.evaluate("window.__part.startCommand('curve_blend')")
    page.wait_for_selector("#pt-cmdwin:not([hidden])")
    assert page.inner_text("#pt-cmdwin-title") == "Blend curve"
    # end A: the top edge along x at y = 0 (mid (50, 0, 20)), near its end at x = 100
    page.evaluate("""() => { const P = window.__part, m = P.PT.mesh; const i = m.edge_keys.findIndex(k => k && Math.abs(k.mid[0] - 50) < 1e-6 && Math.abs(k.mid[1]) < 1e-6 && Math.abs(k.mid[2] - 20) < 1e-6);
        P.feedCommand({ kind: "edge", key: m.edge_keys[i], index: i, point: [100, 0, 20] }); }""")
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.ends[0] && f.ends[0].kind === 'edge' && f.ends[0].at[0] === 100; })()")
    page.wait_for_selector("#pf-bcont0")
    page.select_option("#pf-bcont0", "curvature")
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).ends[0].cont === 'curvature'")
    page.evaluate("window.__part.gotoStep(1)")
    page.evaluate("window.__part.feedCommand({ kind: 'point', vertex: true, point: [140, 30, 20] })")
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.ends[1] && f.ends[1].kind === 'point'; })()")
    cid = page.evaluate("window.__part.PT.cmd.id")
    page.wait_for_function("id => window.__part.PT.status[id] && !window.__part.PT.status[id].pending && window.__part.PT.surfaces[id]", arg=cid, timeout=60000)
    assert "blend curvature / position" in page.evaluate("id => window.__part.PT.status[id].note || ''", cid)
    page.click("#cmd-finish")
    page.wait_for_function("!window.__part.PT.cmd")
    assert page.evaluate("[...document.querySelectorAll('#pt-features .pt-sub')].map(e => e.textContent.trim())") == ["Solids", "Curves"]
    # curve through points
    page.evaluate("window.__part.startCommand('curve_points')")
    page.wait_for_selector("#pt-cmdwin:not([hidden])")
    for q in ([0, 0, 20], [50, 10, 25], [100, 0, 20]):
        page.evaluate("q => window.__part.feedCommand({ kind: 'point', vertex: true, point: q })", q)
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).points.length === 3")
    assert page.locator("#pt-cmdbody .cw-chips[data-prop=points] .cw-chip").count() == 3
    page.click("#pt-cmdbody .cw-chip [data-cwdel='1']")
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).points.length === 2")
    page.evaluate("q => window.__part.feedCommand({ kind: 'point', vertex: true, point: q })", [50, 10, 25])
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).points.length === 3")
    page.evaluate("window.__part.gotoStep(1)")
    page.wait_for_selector("#pf-cpm")
    page.select_option("#pf-cpm", "spline")
    cid = page.evaluate("window.__part.PT.cmd.id")
    page.wait_for_function("id => window.__part.PT.status[id] && !window.__part.PT.status[id].pending && (window.__part.PT.status[id].note || '').includes('spline')", arg=cid, timeout=60000)
    page.click("#cmd-finish")
    page.wait_for_function("!window.__part.PT.cmd")
    assert page.evaluate("window.__part.bodyGroupIds('curve').length") == 2
    # partition with a surface: the Extend field
    page.evaluate("window.__part.startCommand('split')")
    page.wait_for_selector("#pf-method")
    page.select_option("#pf-method", "surface")
    page.wait_for_selector("#pf-sext")
    assert page.input_value("#pf-sext") == "1"
    page.evaluate("window.__part.cancelCommand()")


def test_part_connect_surfaces_command(page, client):
    """Connect surfaces: edges of two surface bodies fed to side A and side B (a side switches body on an edge of
    another body), the feature builds one shell, the two bodies are hidden."""
    from conftest import part_rec, rect
    p = part_rec("ui_conn", [
        {"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20)}},
        {"id": "b", "name": "B", "type": "surf_sketch", "kind": "planar", "plane": "XZ", "offset": -23, "sketch": {"entities": rect(40, 20, 0, 2)}}])
    client.put("/api/part/file/ui_conn", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_conn')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.a && window.__part.PT.surfaces.b")
    page.evaluate("window.__part.startCommand('surf_connect')")
    page.wait_for_selector("#pt-cmdwin:not([hidden])")
    assert page.inner_text("#pt-cmdwin-title") == "Connect surfaces"
    feed = "([sid, mid, len]) => { const sm = window.__part.PT.surfaces[sid]; const i = sm.edge_keys.findIndex(k => k && Math.abs(k.mid[0] - mid[0]) < 1e-4 && Math.abs(k.mid[1] - mid[1]) < 1e-4 && Math.abs(k.mid[2] - mid[2]) < 1e-4); window.__part.feedCommand({ kind: 'edge', key: sm.edge_keys[i], surface: sid, point: mid }); }"
    page.evaluate(feed, ["a", [20, 20, 0], 40])
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.source_a === 'a' && f.edges_a.length === 1; })()")
    page.evaluate("window.__part.gotoStep(1)")
    page.evaluate(feed, ["b", [20, 23, 2], 40])
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.source_b === 'b' && f.edges_b.length === 1; })()")
    cid = page.evaluate("window.__part.PT.cmd.id")
    page.wait_for_function("id => window.__part.PT.status[id] && !window.__part.PT.status[id].pending && window.__part.PT.surfaces[id]", arg=cid, timeout=60000)
    assert "1 shell" in page.evaluate("id => window.__part.PT.status[id].note || ''", cid)
    page.click("#cmd-finish")
    page.wait_for_function("!window.__part.PT.cmd")
    assert page.evaluate("[!!window.__part.PT.hidden.a, !!window.__part.PT.hidden.b]") == [True, True]


def test_part_extract_surface_separate_bodies(page, client):
    """Extract surface with Separate bodies: the top and the bottom face of a plate (not connected) give two
    Extract surface features, one face each; two surface bodies in the tree."""
    client.put("/api/part/file/ui_sep", json=plate("ui_sep", hole_r=0))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_sep')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.face_keys && window.__part.PT.mesh.face_keys.length > 0", timeout=60000)
    page.evaluate("window.__part.startCommand('surf_extract')")
    page.wait_for_selector("#pt-cmdwin:not([hidden])")
    for z in (20, 0):
        page.evaluate("z => { const m = window.__part.PT.mesh; const i = m.face_keys.findIndex(k => k && Math.abs(k.c[2] - z) < 1e-6 && Math.abs(Math.abs(k.n[2]) - 1) < 1e-6); window.__part.feedCommand({ kind: 'face', fi: i, key: m.face_keys[i], solid: 0, point: m.face_keys[i].c }); }", z)
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).faces.length === 2")
    page.evaluate("window.__part.gotoStep(1)")
    page.wait_for_selector("#pf-xsep")
    page.check("#pf-xsep")
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).separate === true")
    page.click("#cmd-finish")
    page.wait_for_function("!window.__part.PT.cmd && window.__part.PT.part.features.filter(f => f.type === 'surf_extract').length === 2", timeout=60000)
    assert page.evaluate("window.__part.PT.part.features.filter(f => f.type === 'surf_extract').map(f => f.faces.length)") == [1, 1]
    page.wait_for_function("window.__part.bodyGroupIds('surface').length === 2", timeout=60000)


def test_part_surface_fillet_faces_of_one_body_by_click(page, client):
    """Surface fillet with Pick single faces: a click on a face of a surface body sets the side (A, then B, both faces
    of one sewn body); Finish gives the fillet."""
    from conftest import part_rec, rect
    p = part_rec("ui_sf1", [
        {"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 1)}},
        {"id": "b", "name": "B", "type": "surf_sketch", "kind": "planar", "plane": "XZ", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 1)}},
        {"id": "s", "name": "Sew 1", "type": "surf_sew", "sources": ["a", "b"], "tolerance": 0.001}])
    p["hidden"] = ["a", "b"]
    client.put("/api/part/file/ui_sf1", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_sf1')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.s")
    page.evaluate("() => { window.__part.PT.hidden.a = true; window.__part.PT.hidden.b = true; window.__part.setMesh(window.__part.PT.mesh); }")
    page.evaluate("window.__part.startCommand('surf_fillet')")
    page.wait_for_selector("#pf-sfacea")
    page.check("#pf-sfacea")
    find = """([cx, cy, cz]) => { const P = window.__part, t = P.PT.three, r = t.renderer.domElement.getBoundingClientRect();
        for (let i = 2; i < 60; i++) for (let j = 2; j < 60; j++) {
          const x = r.left + r.width * i / 61, y = r.top + r.height * j / 61;
          const h = P.pickAt({ clientX: x, clientY: y }, ['sface', 'face']);
          if (h && h.kind === 'face' && h.surface === 's' && Math.abs(h.key.c[0] - cx) + Math.abs(h.key.c[1] - cy) + Math.abs(h.key.c[2] - cz) < 0.5) return [x, y];
        }
        return null; }"""
    xy = page.evaluate(find, [0, 11, 0])
    assert xy, "face A not found on screen"
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.source_a === 's' && (f.faces_a || []).length === 1; })()")
    page.evaluate("window.__part.gotoStep(1)")
    page.wait_for_selector("#pf-sfaceb")
    xy = page.evaluate(find, [0, 0, 11])
    assert xy, "face B not found on screen"
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.source_b === 's' && (f.faces_b || []).length === 1; })()")
    page.evaluate("window.__part.gotoStep(2)")
    page.wait_for_selector("#pf-sfr")
    page.fill("#pf-sfr", "3")
    page.dispatch_event("#pf-sfr", "change")
    page.evaluate("window.__part.finishCommand()")
    page.wait_for_function("""(() => { const PT = window.__part.PT; const f = PT.part.features.find(x => x.type === 'surf_fillet');
        const st = f && PT.status[f.id]; return st && !st.pending && st.error === null && st.faces === 3; })()""", timeout=60000)


def test_part_inspect_join_cells(page, client):
    """Inspect of a part of cells: Edges where cells meet, Join cells adds Boolean union and Merge faces, one solid."""
    pp = plate("ui_cells", 100.0, 50.0, 20.0, 0)
    pp["features"] += [{"id": "s1", "name": "Partition 1", "type": "split", "method": "principal", "plane": "YZ", "offset": 50}]
    client.put("/api/part/file/ui_cells", json=pp)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_cells')")
    page.wait_for_function("window.__part.PT.solids && window.__part.PT.solids.length === 2", timeout=60000)
    page.click("#pt-features .pt-feat[data-id='solid:0'] .nm")
    page.click("#pp-inspect")
    wait_text(page, "#pt-props", "Edges where cells meet")
    page.click("#pi-join")
    page.wait_for_function("window.__part.PT.solids.length === 1 && !Object.values(window.__part.PT.status).some(s => s.pending)", timeout=60000)
    assert page.evaluate("window.__part.PT.part.features.slice(-2).map(f => f.type)") == ["boolean", "unify"]


def test_part_extend_surface_face_of_body_edge_click(page, client):
    """Extend surface by an edge click alone: the command opens on the Edges step, a click on the outer edge of
    face A of a sewn surface body picks the body and the edge; A is extended by 5 mm across that edge and the strip
    is part of A (two faces as before)."""
    from conftest import part_rec, rect
    p = part_rec("ui_ext1", [
        {"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 1)}},
        {"id": "b", "name": "B", "type": "surf_sketch", "kind": "planar", "plane": "XZ", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 1)}},
        {"id": "s", "name": "Sew 1", "type": "surf_sew", "sources": ["a", "b"], "tolerance": 0.001}])
    client.put("/api/part/file/ui_ext1", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_ext1')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.s")
    page.evaluate("() => { window.__part.PT.hidden.a = true; window.__part.PT.hidden.b = true; window.__part.setMesh(window.__part.PT.mesh); }")
    page.evaluate("window.__part.startCommand('surf_extend')")
    find = """([kinds, test]) => { const P = window.__part, t = P.PT.three, r = t.renderer.domElement.getBoundingClientRect();
        const ok = new Function('h', 'return ' + test);
        for (let i = 2; i < 120; i++) for (let j = 2; j < 120; j++) {
          const x = r.left + r.width * i / 121, y = r.top + r.height * j / 121;
          const h = P.pickAt({ clientX: x, clientY: y }, kinds);
          if (h && ok(h)) return [x, y];
        }
        return null; }"""
    xy = page.evaluate(find, [["sedge", "edge"], "h.kind === 'edge' && h.surface === 's' && Math.abs(h.key.mid[1] - 21) < 0.5 && Math.abs(h.key.mid[2]) < 0.5"])
    assert xy, "outer edge of A not found"
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.source === 's' && (f.edges || []).length === 1; })()")
    page.evaluate("window.__part.finishCommand()")
    page.wait_for_function("""(() => { const PT = window.__part.PT; const f = PT.part.features.find(x => x.type === 'surf_extend');
        const st = f && PT.status[f.id]; return st && !st.pending && st.error === null && Math.abs(st.area - (1600 + 200)) < 0.01 && st.faces === 2; })()""", timeout=60000)


def test_part_surface_fillet_edge_click(page, client):
    """Surface fillet, Edges of a surface body: with the Radius section active and no surface chosen, a click on the
    edge where the two faces of a sewn body meet picks the body and the edge; R3 rounds it (3 faces)."""
    from conftest import part_rec, rect
    p = part_rec("ui_sfe1", [
        {"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 0)}},
        {"id": "b", "name": "B", "type": "surf_sketch", "kind": "planar", "plane": "XZ", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 0)}},
        {"id": "s", "name": "Sew 1", "type": "surf_sew", "sources": ["a", "b"], "tolerance": 0.001}])
    client.put("/api/part/file/ui_sfe1", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_sfe1')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.s")
    page.evaluate("() => { window.__part.PT.hidden.a = true; window.__part.PT.hidden.b = true; window.__part.setMesh(window.__part.PT.mesh); }")
    page.evaluate("window.__part.startCommand('surf_fillet')")
    page.wait_for_selector("#pf-sfmode")
    page.select_option("#pf-sfmode", "edges")
    page.wait_for_selector("#pf-sfr")
    page.fill("#pf-sfr", "3")
    page.dispatch_event("#pf-sfr", "change")
    find = """([kinds, test]) => { const P = window.__part, t = P.PT.three, r = t.renderer.domElement.getBoundingClientRect();
        const ok = new Function('h', 'return ' + test);
        for (let i = 2; i < 120; i++) for (let j = 2; j < 120; j++) {
          const x = r.left + r.width * i / 121, y = r.top + r.height * j / 121;
          const h = P.pickAt({ clientX: x, clientY: y }, kinds);
          if (h && ok(h)) return [x, y];
        }
        return null; }"""
    xy = page.evaluate(find, [["sedge", "surface"], "h.kind === 'edge' && h.surface === 's' && Math.abs(h.key.mid[1]) < 0.5 && Math.abs(h.key.mid[2]) < 0.5"])
    assert xy, "shared edge not found"
    page.mouse.click(*xy)
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.source === 's' && (f.edges || []).length === 1; })()")
    page.evaluate("window.__part.finishCommand()")
    page.wait_for_function("""(() => { const PT = window.__part.PT; const f = PT.part.features.find(x => x.type === 'surf_fillet');
        const st = f && PT.status[f.id]; return st && !st.pending && st.error === null && st.faces === 3; })()""", timeout=60000)


def test_part_face_click_tangent_and_connected(page, client):
    """Face click mode of a multi-face step (Extract surface): Tangent faces adds the top of a filleted plate with
    its fillets and the sides joined through them (9 faces); Connected faces adds the rest (10); a Connected click on
    a selected face removes them all."""
    import copy
    from drawgen import part as dpart
    p = plate("ui_fmode", 40.0, 20.0, 10.0, 0)
    sh, st = dpart.build(copy.deepcopy(p))
    top = [f for f in sh.faces() if abs(f.center().Z - 10) < 1e-6][0]
    p["features"].append({"id": "f9", "name": "Fillet 1", "type": "fillet", "edges": [dpart.edge_key(e) for e in top.edges()], "value": 2})
    client.put("/api/part/file/ui_fmode", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_fmode')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.face_keys && window.__part.PT.mesh.face_keys.length === 10", timeout=60000)
    page.evaluate("window.__part.startCommand('surf_extract')")
    page.wait_for_selector("input[name=pf-fmode][value=tangent]")
    page.check("input[name=pf-fmode][value=tangent]")
    find = """(z) => { const P = window.__part, t = P.PT.three, r = t.renderer.domElement.getBoundingClientRect();
        for (let i = 2; i < 100; i++) for (let j = 2; j < 100; j++) {
          const x = r.left + r.width * i / 101, y = r.top + r.height * j / 101;
          const h = P.pickAt({ clientX: x, clientY: y }, ['face', 'sface']);
          if (h && h.kind === 'face' && !h.surface && Math.abs(h.key.c[2] - z) < 0.01 && h.key.area > 300) return [x, y];
        }
        return null; }"""
    nfaces = "(window.__part.feat(window.__part.PT.cmd.id).faces || []).length"
    xy = page.evaluate(find, 10)
    assert xy, "top face not found"
    page.mouse.click(*xy)
    page.wait_for_function(nfaces + " === 9", timeout=30000)
    page.check("input[name=pf-fmode][value=connected]")
    page.mouse.click(*xy)          # the top face is selected: Connected removes every face joined to it
    page.wait_for_function(nfaces + " === 0", timeout=30000)
    page.mouse.click(*xy)
    page.wait_for_function(nfaces + " === 10", timeout=30000)
    page.evaluate("window.__part.cancelCommand()")


def test_sketch_command_closed_before_slow_refs(page, client):
    """Draw while the reference geometry is still read (a part with many bodies): the command bar is closed at once
    and a late Next does nothing (was: Cannot read properties of null)."""
    client.put("/api/part/file/ui_rp", json=plate("ui_rp"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_rp')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    page.route("**/api/part/refs", lambda r: (time.sleep(2), r.continue_()))
    page.click("#tab-part [data-add=sketch]")
    page.wait_for_selector("#pf-plane")
    assert page.locator("#pt-cmdwin:not([hidden]) #cmd-finish").count() == 1
    page.get_by_role("button", name="Draw", exact=True).click()
    page.wait_for_timeout(200)
    assert page.locator("#pt-cmdwin:not([hidden])").count() == 0
    page.evaluate("window.__part.nextStep()")
    page.wait_for_selector("#tab-sketch:not([hidden])")


def _bx_load(page, client):
    client.put("/api/part/file/ui_bx", json=plate("ui_bx"))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_bx')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")

def _view_rect(page):
    return page.evaluate("(() => { const r = window.__part.PT.three.renderer.domElement.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")

def test_part_box_selection_and_select_shown(page, client):
    _bx_load(page, client)
    page.evaluate("window.__part.startCommand('fillet')")
    page.wait_for_selector("#pf-shown")
    ne = page.evaluate("window.__part.PT.mesh.edges.length")
    page.click("#pf-shown")
    page.wait_for_function("(window.__part.feat(window.__part.PT.cmd.id).edges || []).length > 0")
    shown = page.evaluate("window.__part.feat(window.__part.PT.cmd.id).edges.length")
    assert 0 < shown < ne, (shown, ne)
    # Ctrl + drag right to left over the whole view: every edge (the box adds to the selection)
    x, y, w, h = _view_rect(page)
    page.keyboard.down("Control")
    page.mouse.move(x + w - 5, y + h - 5)
    page.mouse.down()
    page.mouse.move(x + w / 2, y + h / 2, steps=4)
    page.mouse.move(x + 5, y + 5, steps=4)
    page.mouse.up()
    page.keyboard.up("Control")
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).edges.length === %d" % ne)
    # the view did not rotate: Select shown again adds nothing and removes nothing
    page.click("#pf-shown")
    assert page.evaluate("window.__part.feat(window.__part.PT.cmd.id).edges.length") == ne

def test_part_box_window_faces_shown_only(page, client):
    _bx_load(page, client)
    page.click("#tab-part .dd-btn:has-text('Faces')")
    page.click("#tab-part [data-add=defeature]")
    page.wait_for_function("window.__part.PT.cmd && window.__part.PT.cmd.legacyDefs")
    page.wait_for_selector("#pf-boxshown")
    nf = page.evaluate("window.__part.PT.mesh.face_keys.length")
    x, y, w, h = _view_rect(page)
    hits = page.evaluate("window.__part.boxHits(%f, %f, %f, %f, false, false).length" % (x, y, x + w, y + h))
    shown = page.evaluate("window.__part.boxHits(%f, %f, %f, %f, false, true).length" % (x, y, x + w, y + h))
    assert hits == nf and 0 < shown < nf, (hits, shown, nf)
    page.check("#pf-boxshown")
    page.keyboard.down("Control")
    page.mouse.move(x + 3, y + 3); page.mouse.down(); page.mouse.move(x + w - 3, y + h - 3, steps=6); page.mouse.up()
    page.keyboard.up("Control")
    page.wait_for_function("(window.__part.feat(window.__part.PT.cmd.id).faces || []).length === %d" % shown)


def test_part_edge_pick_records_shown_cell(page, client):
    """Two solids side by side, solid 1 hidden: a click on the edge where both solids have an edge stores the shown
    solid as the cell of the edge reference (the fillet acts on that solid only)."""
    from conftest import part_rec, rect
    ext = lambda i, x, nb: {"id": "e%d" % i, "name": "Extrude %d" % i, "type": "extrude", "plane": "XY", "offset": 0,
                            "depth": 10, "direction": "normal", "new_body": nb, "sketch": {"entities": rect(10, 10, x, 0)}}
    client.put("/api/part/file/ui_cells", json=part_rec("ui_cells", [ext(1, 0, False), ext(2, 10, True)]))
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_cells')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.cells === 2")
    page.evaluate("(() => { const P = window.__part; P.PT.hidden['solid:0'] = true; P.setMesh(P.PT.mesh); P.startCommand('fillet'); })()")
    page.wait_for_selector("#pf-shown")
    xy = page.evaluate("""() => { const P = window.__part, t = P.PT.three, r = t.renderer.domElement.getBoundingClientRect();
        const v = new P.THREE.Vector3(10, 0, 5).project(t.camera);
        return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }""")
    page.mouse.click(*xy)
    page.wait_for_function("(window.__part.feat(window.__part.PT.cmd.id).edges || []).length === 1")
    e = page.evaluate("window.__part.feat(window.__part.PT.cmd.id).edges[0]")
    assert e.get("cell") == 1 and abs(e["mid"][0] - 10) < 1e-6 and abs(e["mid"][1]) < 1e-6, e


def cam_add(page, kind):
    """Adds an operation (its dropdown opened first); the command window opens for it."""
    btn = page.locator("#tab-cam [data-addop=%s]" % kind)
    if not btn.is_visible():
        btn.evaluate("b => b.closest('.dd').querySelector('.dd-btn').click()")
    btn.click()
    page.wait_for_function("window.__cam.CM.cmd && window.__cam.CM.doc.operations[window.__cam.CM.doc.operations.length - 1].type === '%s'" % kind)


def cam_click_at(page, x, y, z):
    xy = page.evaluate("""([x, y, z]) => { const CM = window.__cam.CM, t = CM.three; const T = t.controls.target, V = Object.getPrototypeOf(T).constructor;
        t.camera.updateMatrixWorld(true); const p = new V(x, y, z).project(t.camera); const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""", [x, y, z])
    page.mouse.click(*xy)


def cam_click_undercut(page):
    """The undercut face is seen from the +Y side: the view turned there, then the face centre clicked."""
    xy = page.evaluate("""() => { const CM = window.__cam.CM, t = CM.three;
        const fi = CM.geo.undercuts[0], m = CM.geo, c = [0, 0, 0]; let n = 0;
        m.triangles.forEach((tr, k) => { if (m.face_of_tri[k] === fi) for (const v of tr) { c[0] += m.vertices[v][0]; c[1] += m.vertices[v][1]; c[2] += m.vertices[v][2]; n++; } });
        const T = t.controls.target, V = Object.getPrototypeOf(T).constructor;
        const dist = t.camera.position.distanceTo(T);
        t.camera.position.copy(T.clone().add(new V(-0.3, 1, 0.1).normalize().multiplyScalar(dist)));
        t.camera.up.set(0, 0, 1); t.controls.update(); t.camera.updateMatrixWorld(true);
        const p = new V(c[0] / n, c[1] / n, c[2] / n).project(t.camera);
        const r = t.renderer.domElement.getBoundingClientRect();
        return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""")
    page.mouse.click(*xy)


def test_cam_tab_tree_and_placement(page, client):
    """CAM tab: the operation buttons with icons in the toolbar (no dropdown), the tree in the FreeCAD order (Job,
    Operations with the operations and dressups, Model with the part, Stock, SetupSheet, Tools folded), folding and
    the eyes; Placement: a Coincident constraint of the plate top added by a click (the part stays where it is),
    Flip turns the part over (the picked pocket face follows), the constraint row in the tree, Position fields and
    Z +90, Cancel restores the placement and the picks; Zero: the machine zero at a clicked vertex, moved with the part."""
    from test_cam import job_part, BITS
    client.put("/api/part/file/ui_place", json=job_part("ui_place"))
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    page.select_option("#cm-source", "ui_place")
    page.wait_for_function("window.__cam.CM.geo && window.__cam.CM.setup")
    for k in ("face", "profile", "pocket", "drilling", "undercut", "pocket3d"):
        assert page.is_visible("#tab-cam [data-addop=%s]" % k) and page.locator("#tab-cam [data-addop=%s] svg.tb-ico" % k).count() == 1
    assert page.locator("#tab-cam [data-addop=pocket]").evaluate("b => !b.closest('.dd-menu')")
    page.click("#tab-cam [data-addop=face]")
    page.click("#cm-cmd-ok")
    page.click("#tab-cam [data-addop=pocket]")
    cam_click_at(page, 50, 40, 10)
    page.wait_for_function("window.__cam.CM.doc.operations[1].faces.length === 1")
    page.click("#cm-cmd-ok")
    ids = page.evaluate("[...document.querySelectorAll('#cm-tree .pt-feat')].map(e => e.dataset.id)")
    o1, o2 = page.evaluate("window.__cam.CM.doc.operations.map(o => o.id)")
    assert ids[:4] == ["job", "ops", o1, o2] and ids[4:] == ["model", "part", "stock", "setup", "machine", "tools"], ids
    page.click("#cm-tree .pt-feat[data-id=tools] [data-k=fold]")
    page.wait_for_function("document.querySelector('#cm-tree .pt-feat[data-id^=\"tc:\"]')")
    page.click("#cm-tree .pt-feat[data-id=ops] [data-k=fold]")
    page.wait_for_function("!document.querySelector('#cm-tree .pt-feat[data-id=%s]')" % o1)
    page.click("#cm-tree .pt-feat[data-id=ops] [data-k=fold]")
    page.click("#cm-tree .pt-feat[data-id=ops] [data-k=eye]")
    page.wait_for_function("window.__cam.CM.hidden.ops && document.querySelector('#cm-tree .pt-feat[data-id=%s]').classList.contains('hid')" % o1)
    page.click("#cm-tree .pt-feat[data-id=ops] [data-k=eye]")
    page.click("#cm-tree .pt-feat[data-id=job]")
    page.wait_for_selector("#cm-props select[data-k=post]")
    # placement: the plate top in the XY plane, Flip kept from the current direction: the part does not move
    face0 = page.evaluate("JSON.stringify(window.__cam.CM.doc.operations[1].faces[0])")
    runs = []
    page.on("request", lambda rq: runs.append(rq.url) if rq.url.endswith("/api/cam/run") else None)
    page.click("#cm-place")
    page.wait_for_function("window.__cam.CM.cmd && window.__cam.CM.cmd.place")
    assert "Model placement" in page.text_content("#cm-cmdwin-title")
    page.click("#cm-cmdbody [data-pctype=coincident]")
    cam_click_at(page, 50, 40, 10)
    page.wait_for_function("window.__cam.CM.doc.placement.constraints.length === 1 && window.__cam.CM.placeRes")
    pl = page.evaluate("window.__cam.CM.doc.placement")
    assert pl["constraints"][0]["datum"] == "XY" and pl["constraints"][0]["flip"] is True
    assert pl["pos"] == [0, 0, -10] and pl["rot"] == [0, 0, 0], pl
    page.wait_for_function("window.__cam.CM.geo && Math.abs(window.__cam.CM.geo.bbox[5] - 6) < 1e-3")
    assert page.locator("#cm-tree .pt-feat[data-id^='pc:']").count() == 1
    assert abs(page.evaluate("window.__cam.CM.doc.operations[1].faces[0].c[2]")) < 1e-6
    # Flip off: the plate top faces down, the part above the table
    page.uncheck("#cm-cmdbody [data-pcf]")
    page.wait_for_function("window.__cam.CM.geo && Math.abs(window.__cam.CM.geo.bbox[2] + 6) < 1e-3 && Math.abs(window.__cam.CM.geo.bbox[5] - 10) < 1e-3", timeout=60000)
    assert page.evaluate("window.__cam.CM.doc.operations[1].faces[0].n[2]") < -0.99
    # Z +90 with the constraint kept: a turn about Z, the top still on the table
    page.click("#cm-cmdbody [data-pturn='2']")
    page.wait_for_function("window.__cam.CM.geo && Math.abs((window.__cam.CM.geo.bbox[4] - window.__cam.CM.geo.bbox[1]) - 100) < 1e-3", timeout=60000)
    # no toolpath run while the Placement window is open; the toolpaths of the old placement are dropped
    page.wait_for_timeout(800)
    assert runs == [] and page.evaluate("window.__cam.CM.res") is None
    # Cancel: placement and picks as before
    page.click("#cm-cmd-cancel")
    page.wait_for_function("!window.__cam.CM.cmd && window.__cam.CM.doc.placement.constraints.length === 0")
    page.wait_for_function("window.__cam.CM.geo && Math.abs(window.__cam.CM.geo.bbox[5] - 16) < 1e-3")
    assert page.evaluate("JSON.stringify(window.__cam.CM.doc.operations[1].faces[0])") == face0
    page.wait_for_function("window.__cam.CM.res && window.__cam.CM.res.operations.length === 2", timeout=60000)
    # the position typed without constraints moves the part
    page.dblclick("#cm-tree .pt-feat[data-id=model]")
    page.wait_for_function("window.__cam.CM.cmd && window.__cam.CM.cmd.place")
    page.fill("#cm-cmdbody input[data-ppos='0']", "10")
    page.dispatch_event("#cm-cmdbody input[data-ppos='0']", "change")
    page.wait_for_function("window.__cam.CM.geo && Math.abs(window.__cam.CM.geo.bbox[0] - 10) < 1e-3")
    page.click("#cm-cmd-ok")
    page.wait_for_function("!window.__cam.CM.cmd")
    assert page.evaluate("window.__cam.CM.doc.placement.pos") == [10, 0, 0]
    wait_text(page, "#cm-tree", "at 10, 0, 0 mm")
    # the machine zero at a vertex clicked in the view (Zero in the toolbar)
    page.click("#cm-zero")
    page.wait_for_function("window.__cam.CM.zeroPick")
    cam_click_at(page, 110, 60, 10)
    page.wait_for_function("!window.__cam.CM.zeroPick && window.__cam.CM.doc.origin.xy === 'point' && window.__cam.CM.doc.origin.z === 'point'")
    assert page.evaluate("window.__cam.CM.doc.origin.point") == [110, 60, 10]
    page.wait_for_function("window.__cam.CM.setup && window.__cam.CM.setup.origin[0] === 110 && window.__cam.CM.setup.origin[1] === 60 && window.__cam.CM.setup.origin[2] === 10")
    wait_text(page, "#cm-props", "Picked vertex X 110 Y 60 Z 10 mm")
    # the vertex follows the part when the placement changes
    page.click("#cm-place")
    page.wait_for_function("window.__cam.CM.cmd && window.__cam.CM.cmd.place")
    page.fill("#cm-cmdbody input[data-ppos='0']", "0")
    page.dispatch_event("#cm-cmdbody input[data-ppos='0']", "change")
    page.wait_for_function("window.__cam.CM.doc.origin.point[0] === 100")
    page.click("#cm-cmd-ok")


def test_cam_tab_feeds_and_speeds(page, client):
    """CAM tab feeds and speeds: the machine fields of the SetupSheet, the material of the Stock, the calculation in
    the properties of a tool controller (no material: a message; ae typed; Apply sets rpm, feed and plunge), the
    Calculate button of an Adaptive operation (ae from the step over), Feeds and speeds for all, the tool material
    column of the bit library."""
    from test_cam import job_part, BITS
    client.put("/api/part/file/ui_fs", json=job_part("ui_fs"))
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    page.select_option("#cm-source", "ui_fs")
    page.wait_for_function("window.__cam.CM.geo && window.__cam.CM.setup")
    page.click("#cm-tree .pt-feat[data-id=setup]")
    page.fill("#cm-props input[data-k=rpm_max]", "18000")
    page.dispatch_event("#cm-props input[data-k=rpm_max]", "change")
    page.wait_for_function("window.__cam.CM.doc.setup.rpm_max === 18000")
    page.click("#tab-cam [data-addop=adaptive]")
    page.wait_for_function("window.__cam.CM.cmd")
    page.click("#cm-cmd-ok")
    tc = page.evaluate("window.__cam.CM.doc.operations[0].tc")
    page.click("#cm-tree .pt-feat[data-id=tools] [data-k=fold]")
    page.click("#cm-tree .pt-feat[data-id='tc:%s']" % tc)
    wait_text(page, "#cm-props", "No workpiece material")
    page.click("#cm-tree .pt-feat[data-id=stock]")
    page.select_option("#cm-props select[data-k=material]", "al_wrought")
    page.wait_for_function("window.__cam.CM.doc.stock.material === 'al_wrought'")
    wait_text(page, "#cm-tree", "Aluminium wrought")
    page.click("#cm-tree .pt-feat[data-id='tc:%s']" % tc)
    wait_text(page, "#cm-fs-res", "Chip load")
    page.fill("#cm-props input[data-fs=ae]", "3")
    page.dispatch_event("#cm-props input[data-fs=ae]", "change")
    page.wait_for_function("window.__cam.CM.doc.tools[0].fs && window.__cam.CM.doc.tools[0].fs.ae === 3")
    page.click("#cm-fs-apply")
    page.wait_for_function("window.__cam.CM.doc.tools[0].rpm === 15915")             # 300 m/min at D 6 mm
    assert page.evaluate("window.__cam.CM.doc.tools[0].hfeed") > 800
    # Calculate in the Feeds section of the Adaptive operation: ae from the step over 20 %
    page.dblclick("#cm-tree .pt-feat[data-id=%s]" % page.evaluate("window.__cam.CM.doc.operations[0].id"))
    page.wait_for_function("window.__cam.CM.cmd")
    page.click("#cm-cmdbody .cw-sec[data-step='3'] .cw-sec-head")
    page.click("#cm-fs-op")
    page.wait_for_function("window.__cam.CM.doc.operations[0].feed > 0 && window.__cam.CM.doc.operations[0].rpm === 15915")
    assert page.evaluate("window.__cam.CM.fsOp.r.ae") == pytest.approx(1.2)
    wait_text(page, "#cm-cmdbody", "ae 1.2 mm")
    page.click("#cm-cmd-ok")
    # Feeds and speeds for all; the spindle maximum caps the V bit
    page.evaluate("window.__cam.CM.doc.tools.push({id: 'TC9', name: 'V', bit: 'T5', number: 9, hfeed: 1, vfeed: 1, rpm: 1, dir: 'CW'})")
    page.click("#cm-tree .pt-feat[data-id=tools]")
    page.click("#cm-fs-all")
    page.wait_for_function("window.__cam.CM.doc.tools[1].rpm === 18000 && window.__cam.CM.doc.tools[1].hfeed > 1")
    # the tool material column of the bit library
    if not page.is_visible("#cm-tools"):
        page.click("#cm-tools-toggle")
    page.select_option("#cm-bited select[data-k=tool_material]", "hss")
    assert page.evaluate("window.__cam.CM.bits[0].tool_material") == "hss"


def test_cam_tab_library_machine_refresh_placement(page, client, tmp_path):
    """CAM tab: the standard tool library (Library…, a group, Select all, Add selected), Thread / Hop / Probe / Axis
    map buttons and the STEP stock (shown before a run, turned and moved by the stock offsets), the playback bar and the machine (Show ▾ Machine, the Machine tree item
    with the travel check), the part change marked on Refresh and the reload, placement by an edge (Edges, Parallel,
    an edge click) and a drag of the part in Drag mode."""
    from test_cam import job_part, BITS
    client.put("/api/part/file/ui_lib", json=job_part("ui_lib"))
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    page.select_option("#cm-source", "ui_lib")
    page.wait_for_function("window.__cam.CM.geo && window.__cam.CM.setup")
    for sel in ("#tab-cam [data-addop=thread]",):
        assert page.is_visible(sel)
    assert page.locator("#tab-cam [data-addop=hop]").count() == 1 and page.locator("#tab-cam [data-addop=probe]").count() == 1 and page.locator("#tab-cam [data-adddr=axismap]").count() == 1
    # the library
    if not page.is_visible("#cm-tools"):
        page.click("#cm-tools-toggle")
    n0 = page.evaluate("window.__cam.CM.bits.length")
    page.click("#cm-lib-toggle")
    page.wait_for_selector("#cm-lib-group")
    page.select_option("#cm-lib-group", "Tapered ball nose")
    page.click("#cm-lib-all")
    page.click("#cm-lib-add")
    page.wait_for_function("n => window.__cam.CM.bits.length === n + 12", arg=n0)
    assert page.evaluate("window.__cam.CM.bits.some(b => b.id === 'TB-R0.5-3' && b.shape === 'tapered')")
    # the STEP stock option
    page.click("#cm-tree .pt-feat[data-id=stock]")
    assert page.locator("#cm-props select[data-k=kind] option[value=step]").count() == 1
    from build123d import Box, Location, Vector, export_step
    stp = str(tmp_path / "ui_blank.step")
    export_step(Box(110, 70, 20).moved(Location(Vector(50, 30, 10))), stp)
    page.select_option("#cm-props select[data-k=kind]", "step")
    page.fill("#cm-props input[data-k=path]", stp)
    page.press("#cm-props input[data-k=path]", "Tab")
    page.wait_for_function("window.__cam.CM.setup && window.__cam.CM.setup.stock_mesh && Math.abs(window.__cam.CM.setup.stock_bbox[0] + 5) < 1e-3", timeout=60000)
    page.fill("#cm-props input[data-k=rz]", "90")
    page.press("#cm-props input[data-k=rz]", "Tab")
    page.fill("#cm-props input[data-k=dx]", "70")
    page.press("#cm-props input[data-k=dx]", "Tab")
    page.wait_for_function("Math.abs(window.__cam.CM.setup.stock_bbox[0] - 5) < 1e-3 && Math.abs(window.__cam.CM.setup.stock_bbox[4] - 105) < 1e-3", timeout=60000)
    page.select_option("#cm-props select[data-k=kind]", "offsets")
    page.wait_for_function("!window.__cam.CM.setup.stock_mesh", timeout=60000)
    # a run, the playback and the machine
    page.click("#tab-cam [data-addop=face]")
    page.wait_for_function("window.__cam.CM.cmd")
    page.click("#cm-cmd-ok")
    page.click("#cm-run")
    page.wait_for_function("window.__cam.CM.res && window.__cam.CM.res.operations[0].ok && window.__cam.CM.play", timeout=120000)
    assert page.is_visible("#cm-play")
    page.click("#tab-cam .dd-btn:has-text('Show')")
    page.check("#cm-showmachine")
    page.click("#tab-cam .dd-btn:has-text('Show')")
    page.wait_for_function("window.__cam.CM.mach && window.__cam.CM.mach.gantry")
    page.evaluate("window.__cam.playAt(0.5)")
    wait_text(page, "#cm-play-info", "Face")
    y = page.evaluate("window.__cam.CM.mach.gantry.position.y")
    d = page.evaluate("window.__cam.machineOffset()")
    assert abs(y - (page.evaluate("window.__cam.CM.play.pos[1]") + d[1])) < 1e-6
    page.click("#cm-tree .pt-feat[data-id=machine]")
    wait_text(page, "#cm-props", "All moves inside the travel")
    # a change of the part marks Refresh; Refresh loads it again
    rec = job_part("ui_lib")
    rec["features"][0]["depth"] = 12
    client.put("/api/part/file/ui_lib", json=rec)
    page.evaluate("window.__cam.checkPart()")
    page.wait_for_function("document.querySelector('#cm-refresh').classList.contains('cm-stale')")
    page.click("#cm-refresh")
    page.wait_for_function("!window.__cam.CM.partStale && window.__cam.CM.geo && Math.abs(window.__cam.CM.geo.bbox[2] - 0) < 1e-3 && !document.querySelector('#cm-refresh').classList.contains('cm-stale')")
    # placement by an edge: the front bottom edge parallel to the X axis
    page.click("#cm-place")
    page.wait_for_function("window.__cam.CM.cmd && window.__cam.CM.cmd.place")
    page.check("#cm-cmdbody input[name=cm-pkind][value=edges]")
    page.click("#cm-cmdbody [data-pctype=parallel]")
    cam_click_at(page, 50, 0, 0)
    page.wait_for_function("window.__cam.CM.doc.placement.constraints.length === 1 && window.__cam.CM.doc.placement.constraints[0].edge != null")
    c = page.evaluate("window.__cam.CM.doc.placement.constraints[0]")
    assert c["datum"] == "X" and abs(c["ec"][1]) < 1e-6 and abs(c["ec"][2]) < 1e-6
    # drag: the part moved in X and Y with the constraint kept
    page.click("#cm-pdrag")
    page.wait_for_function("window.__cam.CM.cmd.drag")
    a = page.evaluate("""() => { const CM = window.__cam.CM, t = CM.three; const T = t.controls.target, V = Object.getPrototypeOf(T).constructor;
        t.camera.updateMatrixWorld(true); const r = t.renderer.domElement.getBoundingClientRect();
        const pr = p => { const q = new V(...p).project(t.camera); return [r.left + (q.x + 1) / 2 * r.width, r.top + (1 - q.y) / 2 * r.height]; };
        return [pr([50, 30, 10]), pr([70, 30, 10])]; }""")
    page.mouse.move(*a[0])
    page.mouse.down()
    page.mouse.move((a[0][0] + a[1][0]) / 2, (a[0][1] + a[1][1]) / 2)
    page.mouse.move(*a[1])
    page.mouse.up()
    page.wait_for_function("Math.abs(window.__cam.CM.doc.placement.pos[0] - 20) < 0.5", timeout=60000)
    page.click("#cm-cmd-ok")


def test_cam_tab_finish_section(page, client):
    """CAM tab: the Finish section of a Pocket (After the roughing, a second tool controller, finish feed and step
    down, spring pass), the run gives the roughing and the finish records, the tree names the finish controller, the
    properties show both results; Off leaves one record."""
    from test_cam import job_part, BITS
    client.put("/api/part/file/ui_fin", json=job_part("ui_fin"))
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    page.select_option("#cm-source", "ui_fin")
    page.wait_for_function("window.__cam.CM.geo && window.__cam.CM.setup")
    page.evaluate("() => { const CM = window.__cam.CM; CM.doc.tools = [{id: 'TC1', name: 'E6', bit: 'T1', number: 1, hfeed: 800, vfeed: 200, rpm: 12000, dir: 'CW'}, {id: 'TC6', name: 'E3', bit: 'T6', number: 6, hfeed: 600, vfeed: 150, rpm: 15000, dir: 'CW'}]; }")
    page.click("#tab-cam [data-addop=face]")
    page.wait_for_function("window.__cam.CM.cmd")
    page.click("#cm-cmd-ok")
    page.click("#tab-cam [data-addop=pocket]")
    cam_click_at(page, 65, 38, 6)
    page.wait_for_function("window.__cam.CM.doc.operations[1].faces.length === 1")
    assert page.evaluate("window.__cam.CM.doc.operations[1].finish_mode") == "level"
    page.click("#cm-cmdbody .cw-sec[data-step='3'] .cw-sec-head")
    page.fill("#cm-cmdbody input[data-k=extra_offset]", "0.3")
    page.dispatch_event("#cm-cmdbody input[data-k=extra_offset]", "change")
    page.click("#cm-cmdbody .cw-sec[data-step='4'] .cw-sec-head")
    page.select_option("#cm-cmdbody select[data-k=finish_mode]", "separate")
    page.wait_for_selector("#cm-cmdbody select[data-k=finish_tc]")
    page.select_option("#cm-cmdbody select[data-k=finish_tc]", "TC6")
    for k, v in (("finish_feed", "450"), ("finish_step", "4")):
        page.fill("#cm-cmdbody input[data-k=%s]" % k, v)
        page.dispatch_event("#cm-cmdbody input[data-k=%s]" % k, "change")
    page.check("#cm-cmdbody input[data-k=finish_spring]")
    page.wait_for_function("() => { const o = window.__cam.CM.doc.operations[1]; return o.finish_tc === 'TC6' && o.finish_feed === 450 && o.finish_step === 4 && o.finish_spring; }")
    page.click("#cm-cmd-ok")
    page.click("#cm-run")
    page.wait_for_function("window.__cam.CM.res && window.__cam.CM.res.operations.length === 3 && window.__cam.CM.resUpto === null", timeout=120000)
    recs = page.evaluate("window.__cam.CM.res.operations.map(o => [o.id, o.ok, o.tool])")
    oid = page.evaluate("window.__cam.CM.doc.operations[1].id")
    assert recs[1] == [oid, True, "TC1"] and recs[2] == [oid + ":finish", True, "TC6"], recs
    wait_text(page, "#cm-tree", "finish TC6")
    page.click("#cm-tree .pt-feat[data-id=%s]" % oid)
    wait_text(page, "#cm-props", "Roughing")
    wait_text(page, "#cm-props", "Finish (TC6)")
    page.evaluate("id => { const o = window.__cam.CM.doc.operations[1]; o.finish_mode = 'off'; }", oid)
    page.click("#cm-run")
    page.wait_for_function("window.__cam.CM.res && window.__cam.CM.res.operations.length === 2", timeout=120000)


def test_cam_tab_undercut_pick_run_gcode(page, client):
    """CAM tab: the part chosen, the stock set in the properties of the Stock tree item, Undercut added (the
    command window opens, the tool controller made from the library), the undercut face picked by a click in the
    view (a chip appears), the preview runs, OK closes the window, Simulate cuts the stock (nothing left, no gouge),
    the G-code file written to the cam folder of the project, Inspect shows the G-code of the operation."""
    from test_cam import rail_part, BITS
    client.put("/api/part/file/ui_rail", json=rail_part("ui_rail"))
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    page.select_option("#cm-source", "ui_rail")
    page.wait_for_function("window.__cam.CM.geo && window.__cam.CM.geo.undercuts.length === 1")
    page.click("#cm-tree .pt-feat[data-id=stock]")
    page.select_option("#cm-props select[data-k=kind]", "part_filled")
    page.wait_for_function("window.__cam.CM.doc.stock.kind === 'part_filled' && window.__cam.CM.setup && Math.abs(window.__cam.CM.setup.stock_bbox[5] - 16) < 1e-3")
    cam_add(page, "undercut")
    assert page.evaluate("window.__cam.CM.doc.tools.length") == 1 and page.evaluate("window.__cam.CM.doc.tools[0].bit") == "T2"
    assert page.is_visible("#cm-cmdwin") and "Undercut" in page.text_content("#cm-cmdwin-title")
    assert page.evaluate("window.__cam.CM.cmd.step") == 0                     # the Base geometry section is active
    cam_click_undercut(page)
    page.wait_for_function("window.__cam.CM.doc.operations[0].faces.length === 1")
    assert page.locator("#cm-cmdbody .cw-chip").count() == 1
    page.wait_for_function("window.__cam.CM.res && window.__cam.CM.res.operations.length === 1 && window.__cam.CM.res.operations[0].ok", timeout=120000)
    wait_text(page, "#cm-cmdbody", "undercut depth")
    page.click("#cm-cmd-ok")
    page.wait_for_function("!window.__cam.CM.cmd")
    assert not page.is_visible("#cm-cmdwin")
    page.click("#cm-run")
    page.wait_for_function("window.__cam.CM.res && window.__cam.CM.res.operations.length === 1", timeout=120000)
    assert page.evaluate("window.__cam.CM.res.operations[0].ok") is True
    assert page.evaluate("window.__cam.CM.res.left_mm3") < 1e-3
    assert page.locator("#cm-tree .cm-ok").count() == 1
    # the properties of the operation show its results
    page.click("#cm-tree .pt-feat[data-id=%s]" % page.evaluate("window.__cam.CM.doc.operations[0].id"))
    wait_text(page, "#cm-props", "removed")
    file_menu(page, "#tab-cam")
    page.click("#cm-inspect")
    wait_text(page, "#cm-gcodebody", "M06 T1")
    page.click("#cm-gcodewin-x")
    file_menu(page, "#tab-cam")
    page.click("#cm-gcode")
    page.wait_for_function("document.querySelector('#status-text').textContent.includes('Written')", timeout=120000)
    path = page.text_content("#status-text").split("Written ")[1].split(" (")[0].strip()
    assert os.path.isfile(path) and path.endswith(".nc")


def test_cam_tab_job(page, client):
    """CAM tab: a whole job on the pocketed rail plate: stock offsets typed, Face, Pocket Shape (plate top picked by a
    click), Pocket Shape (the pocket floor), Drilling, Undercut, Profile with a Tag dressup from the Dressup menu;
    Cancel restores an operation; the tree shows the dressup; Simulate; results; the document saved and loaded
    again; the sanity check."""
    from test_cam import job_part, BITS
    client.put("/api/part/file/ui_job", json=job_part("ui_job"))
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    file_menu(page, "#tab-cam")
    page.click("#cm-new")
    page.wait_for_function("window.__cam.CM.doc.operations.length === 0")
    page.select_option("#cm-source", "ui_job")
    page.wait_for_function("window.__cam.CM.geo && window.__cam.CM.setup")
    assert page.evaluate("window.__cam.CM.geo.face_kind.filter(k => k === 'floor').length") == 4
    page.click("#cm-tree .pt-feat[data-id=stock]")
    for k in ("xneg", "xpos", "yneg", "ypos", "zpos"):
        page.fill("#cm-props input[data-k=%s]" % k, "2")
        page.dispatch_event("#cm-props input[data-k=%s]" % k, "change")
        page.wait_for_function("k => window.__cam.CM.doc.stock[k] === 2", arg=k)
    page.wait_for_function("window.__cam.CM.setup && Math.abs(window.__cam.CM.setup.stock_bbox[3] - 102) < 1e-3")
    wait_text(page, "#cm-setup-hint", "Stock 104 x 64 x 18 mm; machine zero at part X -2 Y -2 Z 18")
    cam_add(page, "face")
    page.click("#cm-cmd-ok")
    cam_add(page, "pocket")
    cam_click_at(page, 50, 40, 10)                                    # the plate top
    page.wait_for_function("window.__cam.CM.doc.operations[1].faces.length === 1")
    page.click("#cm-cmd-ok")
    cam_add(page, "pocket")
    cam_click_at(page, 65, 38, 6)                                     # the pocket floor beside the island
    page.wait_for_function("window.__cam.CM.doc.operations[2].faces.length === 1")
    # Cancel on a new operation removes it; on an opened one restores it
    page.click("#cm-cmd-cancel")
    page.wait_for_function("!window.__cam.CM.cmd && window.__cam.CM.doc.operations.length === 2")
    cam_add(page, "pocket")
    cam_click_at(page, 65, 38, 6)
    page.wait_for_function("window.__cam.CM.doc.operations[2].faces.length === 1")
    page.click("#cm-cmd-ok")
    page.wait_for_function("!window.__cam.CM.cmd")
    page.dblclick("#cm-tree .pt-feat[data-id=%s]" % page.evaluate("window.__cam.CM.doc.operations[2].id"))
    page.wait_for_function("window.__cam.CM.cmd && window.__cam.CM.cmd.id === window.__cam.CM.doc.operations[2].id")
    page.click("#cm-cmdbody .cw-sec[data-step='3'] .cw-sec-head")
    page.select_option("#cm-cmdbody select[data-k=pattern]", "zigzag")
    page.wait_for_function("window.__cam.CM.doc.operations[2].pattern === 'zigzag'")
    page.click("#cm-cmd-cancel")
    page.wait_for_function("!window.__cam.CM.cmd && window.__cam.CM.doc.operations[2].pattern === 'offset'")
    assert page.evaluate("window.__cam.CM.doc.operations[2].faces.length") == 1
    cam_add(page, "drilling")
    page.evaluate("""() => { const CM = window.__cam.CM; const i = CM.geo.face_kind.indexOf("hole"); const k = CM.geo.face_keys[i];
        CM.doc.operations[3].faces = [{c: k.c, n: k.n, area: k.area}]; }""")
    page.click("#cm-cmd-ok")
    cam_add(page, "undercut")
    cam_click_undercut(page)
    page.wait_for_function("window.__cam.CM.doc.operations[4].faces.length === 1")
    page.click("#cm-cmd-ok")
    cam_add(page, "profile")
    page.click("#cm-cmd-ok")
    page.wait_for_function("!window.__cam.CM.cmd")
    # the Tag dressup of the selected profile from the Dressup menu
    page.click("#tab-cam .dd-btn:has-text('Dressup')")
    page.click("#tab-cam [data-adddr=tag]")
    page.wait_for_function("window.__cam.CM.cmd && window.__cam.CM.cmd.dr === 0 && window.__cam.CM.doc.operations[5].dressups.length === 1")
    page.fill("#cm-cmdbody input[data-k=count]", "3")
    page.dispatch_event("#cm-cmdbody input[data-k=count]", "change")
    page.fill("#cm-cmdbody input[data-k=height]", "1")
    page.dispatch_event("#cm-cmdbody input[data-k=height]", "change")
    page.wait_for_function("window.__cam.CM.doc.operations[5].dressups[0].count === 3 && window.__cam.CM.doc.operations[5].dressups[0].height === 1")
    page.click("#cm-cmd-ok")
    assert page.locator("#cm-tree .pt-feat.cm-child").count() >= 1 + len(page.evaluate("window.__cam.CM.doc.tools"))
    page.click("#cm-run")
    page.wait_for_function("window.__cam.CM.res && window.__cam.CM.res.operations.length === 6 && window.__cam.CM.resUpto === null", timeout=300000)
    assert page.evaluate("window.__cam.CM.res.operations.every(o => o.ok)"), page.evaluate("window.__cam.CM.res.operations.map(o => o.errors)")
    assert page.evaluate("window.__cam.CM.res.gone_mm3") < 0.05 and page.evaluate("window.__cam.CM.res.left_mm3") < 400
    assert page.locator("#cm-tree .cm-ok").count() == 6
    page.click("#cm-tree .pt-feat[data-id=%s]" % page.evaluate("window.__cam.CM.doc.operations[5].id"))
    wait_text(page, "#cm-props", "3 tag(s)")
    # the sanity check in the properties panel
    page.click("#cm-sanity")
    wait_text(page, "#cm-props", "Sanity check")
    # saved and loaded again with the operations and their faces
    page.__dict__["_answer"] = "ui_jobcam"
    file_menu(page, "#tab-cam")
    page.click("#cm-saveas")
    page.wait_for_function("!window.__cam.CM.dirty")
    assert "ui_jobcam" in client.get("/api/cam/list").get_json()
    page.evaluate("window.__camLoadNamed('ui_jobcam')")
    page.wait_for_function("window.__cam.CM.doc.name === 'ui_jobcam' && window.__cam.CM.geo")
    assert page.evaluate("window.__cam.CM.doc.operations.map(o => (o.faces || []).length)") == [0, 1, 1, 1, 1, 0]
    assert page.evaluate("window.__cam.CM.doc.operations[5].dressups[0].type") == "tag"


def test_cam_tab_measure(page, client):
    """CAM tab: Measure (toolbar button, window): a click on the plate top face, a second click on the pocket floor
    (distance between the planes, the minimum distance line), Machine zero and Stock top from the window buttons, a
    vertex click with machine coordinates, Esc ends it."""
    from test_cam import job_part, BITS
    client.put("/api/part/file/ui_meas", json=job_part("ui_meas"))
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    page.select_option("#cm-source", "ui_meas")
    page.wait_for_function("window.__cam.CM.geo && window.__cam.CM.setup")
    page.click("#cm-measure-btn")
    assert page.is_visible("#cm-measure") and page.evaluate("!!window.__cam.CM.measure")
    cam_click_at(page, 20, 30, 10)
    page.wait_for_function("window.__cam.CM.measure.res && window.__cam.CM.measure.items.length === 1")
    assert page.evaluate("window.__cam.CM.measure.items[0].face !== undefined")
    cam_click_at(page, 65, 44, 6)
    page.wait_for_function("window.__cam.CM.measure.res && window.__cam.CM.measure.items.length === 2")
    wait_text(page, "#cm-measure-body", "Distance between the planes")
    assert "4.0000 mm" in page.text_content("#cm-measure-body")
    page.click("#cm-measure [data-mref=zero]")
    page.wait_for_function("window.__cam.CM.measure.items.length === 1 && window.__cam.CM.measure.res")
    page.click("#cm-measure [data-mref=stock_top]")
    page.wait_for_function("window.__cam.CM.measure.items.length === 2 && window.__cam.CM.measure.res")
    wait_text(page, "#cm-measure-body", "Stock top")
    page.click("#cm-measure [data-mref=zero]")
    cam_click_at(page, 100, 60, 10)
    page.wait_for_function("window.__cam.CM.measure.items.length === 2 && window.__cam.CM.measure.res")
    assert page.evaluate("JSON.stringify(window.__cam.CM.measure.items[1].vertex)") == "[100,60,10]"
    page.click("#cm-measure [data-mref=zero]")
    page.wait_for_function("window.__cam.CM.measure.items.length === 1 && window.__cam.CM.measure.res")
    page.keyboard.press("Escape")
    page.wait_for_function("!window.__cam.CM.measure")
    assert not page.is_visible("#cm-measure")


def test_cam_tab_new_controller_from_op(page, client):
    """CAM tab: the Tool controller select of an operation lists the bits of the library as new controllers; picking
    one adds a controller to the job and sets it on the operation (and on Finish tool controller)."""
    from test_cam import job_part, BITS
    client.put("/api/part/file/ui_tc", json=job_part("ui_tc"))
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    page.select_option("#cm-source", "ui_tc")
    page.wait_for_function("window.__cam.CM.geo && window.__cam.CM.setup")
    page.click("#tab-cam [data-addop=pocket]")
    page.wait_for_selector("#cm-cmdbody select[data-k=tc]")
    n0 = page.evaluate("window.__cam.CM.doc.tools.length")
    assert page.locator("#cm-cmdbody select[data-k=tc] option[value='bit:T4']").count() == 1
    page.select_option("#cm-cmdbody select[data-k=tc]", "bit:T4")
    page.wait_for_function("n => window.__cam.CM.doc.tools.length === n + 1", arg=n0)
    tc = page.evaluate("window.__cam.CM.doc.operations[0].tc")
    assert page.evaluate("t => window.__cam.CM.doc.tools.find(x => x.id === t).bit", tc) == "T4"
    page.wait_for_function("t => document.querySelector('#cm-cmdbody select[data-k=tc]').value === t", arg=tc)
    page.select_option("#cm-cmdbody select[data-k=finish_mode]", "separate")
    page.wait_for_selector("#cm-cmdbody select[data-k=finish_tc]")
    page.select_option("#cm-cmdbody select[data-k=finish_tc]", "bit:T6")
    page.wait_for_function("n => window.__cam.CM.doc.tools.length === n + 2", arg=n0)
    assert page.evaluate("window.__cam.CM.doc.tools.find(x => x.id === window.__cam.CM.doc.operations[0].finish_tc).bit") == "T6"


def test_cam_tab_gouge_places(page, client):
    """CAM tab: a Face operation cut into the part top: the Gouges table in the operation properties (volume, centre,
    move), the Gouge column of the levels, the gouge drawn in the view, a click on a row centres the view."""
    from test_cam import job_part, BITS
    client.put("/api/part/file/ui_gouge", json=job_part("ui_gouge"))
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    page.select_option("#cm-source", "ui_gouge")
    page.wait_for_function("window.__cam.CM.geo && window.__cam.CM.setup")
    page.click("#tab-cam [data-addop=face]")
    page.wait_for_selector("#cm-cmdbody input[data-k=final_depth]")
    page.fill("#cm-cmdbody input[data-k=final_depth]", "15.5")
    page.press("#cm-cmdbody input[data-k=final_depth]", "Tab")
    page.click("#cm-cmd-ok")
    page.wait_for_function("window.__cam.CM.res && window.__cam.CM.res.operations[0].gouges && window.__cam.CM.res.operations[0].gouges.length", timeout=60000)
    page.click("#cm-tree .pt-feat[data-id=%s]" % page.evaluate("window.__cam.CM.doc.operations[0].id"))
    page.wait_for_selector("#cm-props .cm-gouges tr[data-gouge]")
    assert "Gouge (mm^3)" in page.text_content("#cm-props")
    assert page.evaluate("window.__cam.CM.three.group.children.some(o => o.material && o.material.color && o.material.color.getHex() === 0xe64980)")
    c = page.evaluate("window.__cam.CM.res.operations[0].gouges[0].c")
    page.click("#cm-props .cm-gouges tr[data-gouge]")
    t = page.evaluate("window.__cam.CM.three.controls.target.toArray()")
    assert all(abs(t[i] - c[i]) < 1e-3 for i in range(3)), (t, c)


def test_cam_tab_bit_editor(page, client):
    """CAM tab: the bit list and the bit editor: New bit, Shape T-slot cutter with its fields (Disc diameter, Disc
    thickness, Neck diameter), the profile drawing and its line, a neck as large as the disc refused in the drawing
    line, Copy, a Custom profile with a point added (D from the points), Save bits (the server sets D)."""
    from test_cam import BITS
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    if not page.is_visible("#cm-tools"):
        page.click("#cm-tools-toggle")
    n0 = page.evaluate("window.__cam.CM.bits.length")
    page.click("#cm-tool-add")
    page.wait_for_function("n => window.__cam.CM.bits.length === n + 1", arg=n0)
    page.select_option("#cm-bited select[data-k=shape]", "tslot")
    page.wait_for_selector("#cm-bited input[data-k=height]")
    assert "Disc diameter D (mm)" in page.text_content("#cm-bited") and "Disc thickness (mm)" in page.text_content("#cm-bited")
    for k, v in (("d", "16"), ("height", "6"), ("neck", "7"), ("neck_length", "10")):
        page.fill("#cm-bited input[data-k=%s]" % k, v)
        page.press("#cm-bited input[data-k=%s]" % k, "Tab")
    wait_text(page, "#cm-bit-info", "D 16 mm, cutting height 6 mm")
    assert page.locator("#cm-bit-svg polygon").count() == 2
    page.fill("#cm-bited input[data-k=neck]", "16")
    page.press("#cm-bited input[data-k=neck]", "Tab")
    wait_text(page, "#cm-bit-info", "must be smaller than the disc diameter")
    page.fill("#cm-bited input[data-k=neck]", "7")
    page.press("#cm-bited input[data-k=neck]", "Tab")
    wait_text(page, "#cm-bit-info", "cutting height 6 mm")
    page.click("#cm-tools tr[data-bi='%d'] [data-tdup]" % n0)
    page.wait_for_function("n => window.__cam.CM.bits.length === n + 2 && window.__cam.CM.bits[n + 1].shape === 'tslot'", arg=n0)
    page.select_option("#cm-bited select[data-k=shape]", "custom")
    page.wait_for_selector("#cm-bited #cm-padd")
    page.click("#cm-bited #cm-padd")
    page.wait_for_function("n => window.__cam.CM.bits[n + 1].profile.length === 4", arg=n0)
    page.fill("#cm-bited input[data-pr='1'][data-pc='0']", "5")
    page.press("#cm-bited input[data-pr='1'][data-pc='0']", "Tab")
    page.wait_for_function("n => window.__cam.CM.bits[n + 1].d === 10", arg=n0)
    page.click("#cm-tool-save")
    page.wait_for_function("n => window.__cam.CM.bits.length === n + 2 && window.__cam.CM.bits[n + 1].height === 12", arg=n0)
    saved = client.get("/api/cam/tools").get_json()
    assert saved[n0]["shape"] == "tslot" and saved[n0 + 1]["shape"] == "custom" and saved[n0 + 1]["d"] == 10


def test_cam_tab_setups(page, client):
    """CAM tab: Add setup from the Job properties: the setup rows in the tree (the active one with its Operations,
    Model and Stock), the second setup starts with the placement of the first and no operations, its stock from
    Setup 1 (setup line), operations kept per setup when switching, rename, move, delete."""
    from test_cam import job_part, BITS
    client.put("/api/part/file/ui_su", json=job_part("ui_su"))
    client.put("/api/cam/tools", json=BITS)
    tab(page, "cam")
    page.wait_for_function("window.__cam && window.__cam.CM.doc && window.__cam.CM.bits.length")
    page.select_option("#cm-source", "ui_su")
    page.wait_for_function("window.__cam.CM.geo && window.__cam.CM.setup")
    page.click("#tab-cam [data-addop=face]")
    page.click("#cm-cmd-ok")
    o1 = page.evaluate("window.__cam.CM.doc.operations[0].id")
    assert page.locator("#cm-tree .pt-feat[data-id^='su:']").count() == 0
    page.click("#cm-tree .pt-feat[data-id=job]")
    page.click("#cm-su-add2")
    page.wait_for_function("window.__cam.CM.doc.setups.length === 2 && window.__cam.CM.doc.active === 1")
    assert page.evaluate("window.__cam.CM.doc.operations.length") == 0
    ids = page.evaluate("[...document.querySelectorAll('#cm-tree .pt-feat')].map(e => e.dataset.id)")
    assert ids[:6] == ["job", "su:S1", "su:S2", "ops", "model", "part"], ids
    assert "from Setup 1" in page.text_content("#cm-tree .pt-feat[data-id=stock]")
    page.wait_for_function("window.__cam.CM.setup && window.__cam.CM.setup.setup && window.__cam.CM.setup.setup.index === 1 && window.__cam.CM.setup.stock_mesh", timeout=60000)
    page.click("#tab-cam [data-addop=face]")
    page.click("#cm-cmd-ok")
    o2 = page.evaluate("window.__cam.CM.doc.operations[0].id")
    assert o2 != o1
    page.click("#cm-tree .pt-feat[data-id='su:S1']")
    page.wait_for_function("o => window.__cam.CM.doc.active === 0 && window.__cam.CM.doc.operations[0].id === o", arg=o1)
    assert page.evaluate("window.__cam.CM.doc.setups[1].operations[0].id") == o2
    page.click("#cm-tree .pt-feat[data-id='su:S1']")
    page.wait_for_selector("#cm-props input[data-k=name]")
    page.fill("#cm-props input[data-k=name]", "Top")
    page.press("#cm-props input[data-k=name]", "Tab")
    page.wait_for_function("window.__cam.CM.doc.setups[0].name === 'Top'")
    page.click("#cm-tree .pt-feat[data-id='su:S2'] [data-k=up]")
    page.wait_for_function("window.__cam.CM.doc.setups[0].id === 'S2' && window.__cam.CM.doc.active === 1")
    page.on("dialog", lambda dlg: dlg.accept())
    page.click("#cm-tree .pt-feat[data-id='su:S2'] [data-k=del]")
    page.wait_for_function("window.__cam.CM.doc.setups.length === 1 && window.__cam.CM.doc.setups[0].name === 'Top' && window.__cam.CM.doc.active === 0")
    assert page.locator("#cm-tree .pt-feat[data-id^='su:']").count() == 0


def test_part_merge_tangent_faces_command(page, client):
    """Faces ▾ Merge tangent faces on a box with a rounded vertical edge: the panel, Spline faces only off, Max
    deviation 0.2 mm, finish;
    the two side faces and the round become one face (the result line)."""
    from conftest import part_rec, rect
    p = part_rec("ui_mt", [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": rect(20, 10)}, "depth": 5},
                           {"id": "fl", "name": "Fillet 1", "type": "fillet", "value": 3, "edges": [{"mid": [20, 10, 2.5], "len": 5}]}])
    client.put("/api/part/file/ui_mt", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_mt')")
    page.wait_for_function("window.__part.PT.mesh && window.__part.PT.mesh.vertices.length")
    page.click("#tab-part .dd-btn:has-text('Faces')")
    page.click("#tab-part [data-add=merge_tangent]")
    page.wait_for_function("window.__part.PT.cmd && window.__part.PT.cmd.legacyDefs")
    page.uncheck("#pf-mtspl")
    page.fill("#pf-mtdev", "0.2")
    page.press("#pf-mtdev", "Tab")
    page.evaluate("window.__part.finishCommand()")
    page.wait_for_function("""(() => { const PT = window.__part.PT; const f = PT.part.features.find(x => x.type === 'merge_tangent');
        const st = f && PT.status[f.id]; return st && !st.pending && st.error === null && st.faces === 5 && /1 group/.test(st.note || ''); })()""", timeout=60000)


def test_part_trim_surface_plane(page, client):
    """Trim surface with a plane feature: the plane at x = 5 mm cuts the extruded rectangle (4 faces) into 2 regions; the plane
    at x = 50 mm misses it and the Regions section shows the reason."""
    from conftest import part_rec, rect
    p = part_rec("ui_trp", [
        {"id": "a", "name": "A", "type": "surf_sketch", "kind": "extrude", "depth": 10, "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 0)}},
        {"id": "pl1", "name": "Plane 1", "type": "plane", "method": "principal", "plane": "YZ", "offset": 5},
        {"id": "pl2", "name": "Plane 2", "type": "plane", "method": "principal", "plane": "YZ", "offset": 50}])
    client.put("/api/part/file/ui_trp", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_trp')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.a")
    page.evaluate("window.__part.startCommand('surf_trim')")
    page.wait_for_selector("#pf-source")
    page.select_option("#pf-source", "a")
    page.evaluate("window.__part.gotoStep(1)")
    page.evaluate("window.__part.feedCommand({ kind: 'plane', id: 'pl1' })")
    page.wait_for_function("window.__part.PT.cmd.step === 2 && (window.__part.PT.cmd.regions || []).length === 2")
    page.evaluate("window.__part.gotoStep(1)")
    page.evaluate("window.__part.feedCommand({ kind: 'plane', id: 'pl2' })")
    page.wait_for_function("window.__part.PT.cmd.step === 2 && /does not cut/.test(document.querySelector('#pt-cmdbody').innerText)")


def test_part_close_gaps_command(page, client):
    """Close gaps from the Surfaces menu: a sewn body of two planar faces with a V-shaped split (0.3 mm wide at its
    open end) gives one shell of area 200 mm^2 with the note "1 gap(s) closed"; the source body is hidden."""
    from conftest import part_rec, rect
    p4 = [(10, 0), (20, 0), (20, 10), (10.3, 10)]
    poly = [{"id": 11 + i, "t": "line", "x1": p4[i][0], "y1": p4[i][1], "x2": p4[(i + 1) % 4][0], "y2": p4[(i + 1) % 4][1], "layer": "0"} for i in range(4)]
    p = part_rec("ui_gaps", [
        {"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(10, 10)}},
        {"id": "b", "name": "B", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": poly}},
        {"id": "s", "name": "Sew 1", "type": "surf_sew", "sources": ["a", "b"], "tolerance": 0.001}])
    p["hidden"] = ["a", "b"]
    client.put("/api/part/file/ui_gaps", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_gaps')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.s")
    page.evaluate("document.querySelector('[data-add=surf_gaps]').click()")
    page.wait_for_selector("#pf-source")
    page.select_option("#pf-source", "s")
    page.evaluate("window.__part.finishCommand()")
    page.wait_for_function("""(() => { const PT = window.__part.PT; const f = PT.part.features.find(x => x.type === 'surf_gaps');
        const st = f && PT.status[f.id]; return st && !st.pending && st.error === null && Math.abs(st.area - 200) < 1e-6 && st.faces === 2; })()""", timeout=60000)
    assert page.evaluate("window.__part.PT.hidden.s === true")
    assert "1 gap(s) closed" in page.evaluate("(() => { const PT = window.__part.PT; return PT.status[PT.part.features.find(x => x.type === 'surf_gaps').id].note; })()")


def test_part_sweep_surface_command(page, client):
    """Sweep surface from the Surfaces menu: profile Sketch 1 (6 mm line), path Sketch 2 (20 mm line) chosen in the
    lists; the result is a surface of 120 mm^2."""
    from conftest import part_rec
    line = lambda i, a, b: {"id": i, "t": "line", "layer": "0", "x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1]}
    p = part_rec("ui_sweep", [
        {"id": "s1", "name": "Sketch 1", "type": "sketch", "plane": "XY", "offset": 0, "sketch": {"entities": [line(1, (-3, 0), (3, 0))]}},
        {"id": "s2", "name": "Sketch 2", "type": "sketch", "plane": "XZ", "offset": 0, "sketch": {"entities": [line(1, (0, 0), (0, 20))]}}])
    client.put("/api/part/file/ui_sweep", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_sweep')")
    page.wait_for_function("window.__part.PT.part && window.__part.PT.part.features.length === 2")
    page.evaluate("document.querySelector('[data-add=surf_sweep]').click()")
    page.wait_for_selector("#pf-swprofile")
    page.select_option("#pf-swprofile", "s1")
    page.evaluate("window.__part.gotoStep(1)")
    page.wait_for_selector("#pf-swpath")
    page.select_option("#pf-swpath", "s2")
    page.evaluate("window.__part.finishCommand()")
    page.wait_for_function("""(() => { const PT = window.__part.PT; const f = PT.part.features.find(x => x.type === 'surf_sweep');
        const st = f && PT.status[f.id]; return st && !st.pending && st.error === null && Math.abs(st.area - 120) < 1e-3; })()""", timeout=60000)


def test_part_project_curve_command(page, client):
    """Project curve from the Surfaces menu: Sketch 1 (circle R5 at z = 10 mm) chosen in the list, surface A
    (planar 40 x 20 mm at z = 0) chosen as Onto; the result is a curve of length 2 pi 5 mm."""
    from conftest import part_rec, rect
    p = part_rec("ui_proj", [
        {"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20, -20, -10)}},
        {"id": "s1", "name": "Sketch 1", "type": "sketch", "plane": "XY", "offset": 10, "sketch": {"entities": [{"id": 1, "t": "circle", "layer": "0", "cx": 0, "cy": 0, "r": 5}]}}])
    client.put("/api/part/file/ui_proj", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_proj')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.a")
    page.evaluate("document.querySelector('[data-add=curve_project]').click()")
    page.wait_for_selector("#pf-pjsrc")
    page.select_option("#pf-pjsrc", "s1")
    page.wait_for_selector("#pf-pjtgt")
    page.select_option("#pf-pjtgt", "a")
    page.evaluate("window.__part.finishCommand()")
    page.wait_for_function("""(() => { const PT = window.__part.PT; const f = PT.part.features.find(x => x.type === 'curve_project');
        const st = f && PT.status[f.id]; return st && !st.pending && st.error === null && st.curve && Math.abs(st.length - 2 * Math.PI * 5) < 1e-3; })()""", timeout=60000)


def test_part_extend_surface_reopen_edges_pickable(page, client):
    """Extend surface reopened for editing: its source body (hidden since the feature was made) is drawn on the part
    before the feature with pickable edges; a click on the outer edge of A deselects it (0 edges), a second click
    selects it again."""
    from conftest import part_rec, rect
    from drawgen import part as dpart, surfaces as sfm
    import copy
    feats = [{"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 1)}}]
    p = part_rec("ui_ext_re", feats)
    bodies = {}
    dpart.build(copy.deepcopy(p), surfaces=bodies)
    e = [x for x in bodies["a"].edges() if abs(x.center().Y - 21) < 1e-6][0]
    p["features"].append({"id": "x", "name": "Extend surface 1", "type": "surf_extend", "source": "a", "edges": [dpart.edge_key(e)], "mode": "edges", "distance": 5, "sides": "all", "tolerance": 0.01, "target": None})
    p["hidden"] = ["a"]
    client.put("/api/part/file/ui_ext_re", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_ext_re')")
    page.wait_for_function("window.__part.PT.status && window.__part.PT.status.x && window.__part.PT.status.x.error === null")
    page.evaluate("window.__part.startCommand('surf_extend', null, 'x')")
    page.evaluate("window.__part.gotoStep(0)")
    find = """() => { const P = window.__part, t = P.PT.three, r = t.renderer.domElement.getBoundingClientRect();
        for (let i = 2; i < 120; i++) for (let j = 2; j < 120; j++) {
          const x = r.left + r.width * i / 121, y = r.top + r.height * j / 121;
          const h = P.pickAt({ clientX: x, clientY: y }, ['sedge', 'edge']);
          if (h && h.kind === 'edge' && h.surface === 'a' && Math.abs(h.key.mid[1] - 21) < 0.5) return [x, y];
        }
        return null; }"""
    page.wait_for_function("window.__part.PT.edgeLines.some(l => l.userData.surface === 'a')", timeout=30000)
    xy = page.evaluate(find)
    assert xy, "edge of the source body not pickable"
    page.mouse.click(*xy)
    page.wait_for_function("(window.__part.feat('x').edges || []).length === 0")
    page.wait_for_timeout(800)
    xy = page.evaluate(find)
    assert xy, "edge not pickable after the deselection"
    page.mouse.click(*xy)
    page.wait_for_function("(window.__part.feat('x').edges || []).length === 1")


def test_part_clean_edges_command(page, client):
    """Clean edges: a planar surface body whose bottom edge is two collinear lines, chosen as the source of the
    command; the feature builds a face with 4 edges, the note says so, the source body is hidden."""
    from conftest import part_rec
    def line(i, a, b):
        return {"id": i, "t": "line", "x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1], "layer": "0"}
    ents = [line(1, (0, 0), (50, 0)), line(2, (50, 0), (100, 0)), line(3, (100, 0), (100, 50)), line(4, (100, 50), (0, 50)), line(5, (0, 50), (0, 0))]
    p = part_rec("ui_clean", [{"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": ents}}])
    client.put("/api/part/file/ui_clean", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_clean')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.a")
    assert page.evaluate("window.__part.PT.surfaces.a.edge_keys.filter(Boolean).length") == 5
    page.evaluate("window.__part.startCommand('surf_clean')")
    page.wait_for_selector("#pt-cmdwin:not([hidden])")
    assert page.inner_text("#pt-cmdwin-title") == "Clean edges"
    page.select_option("#pf-source", "a")
    page.wait_for_function("window.__part.feat(window.__part.PT.cmd.id).source === 'a'")
    page.evaluate("window.__part.gotoStep(1)")
    page.wait_for_selector("#pf-clm")
    assert page.input_value("#pf-cltol") == "0.05" and page.input_value("#pf-clang") == "15"
    cid = page.evaluate("window.__part.PT.cmd.id")
    page.wait_for_function("id => window.__part.PT.status[id] && !window.__part.PT.status[id].pending && window.__part.PT.surfaces[id]", arg=cid, timeout=60000)
    assert "5 edge(s) joined into 4" in page.evaluate("id => window.__part.PT.status[id].note || ''", cid)
    assert page.evaluate("id => window.__part.PT.surfaces[id].edge_keys.filter(Boolean).length", cid) == 4
    page.click("#cmd-finish")
    page.wait_for_function("!window.__part.PT.cmd")
    assert page.evaluate("!!window.__part.PT.hidden.a") is True


def test_part_surface_opacity_slider(page, client):
    """Show menu, Surface opacity: the slider sets the opacity of the surface bodies (material opacity, opaque at
    100 %), the value is kept in localStorage and applied to a reloaded part."""
    from conftest import part_rec, rect
    p = part_rec("ui_op", [{"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20)}}])
    client.put("/api/part/file/ui_op", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_op')")
    page.wait_for_function("window.__part.PT.surfObjs && window.__part.PT.surfObjs.length > 0")
    assert abs(page.evaluate("window.__part.PT.surfObjs[0].material.opacity") - 0.45) < 1e-6
    assert page.input_value("#pt-surfop") == "45"
    page.evaluate("const s = document.querySelector('#pt-surfop'); s.value = '80'; s.dispatchEvent(new Event('input'))")
    assert abs(page.evaluate("window.__part.PT.surfObjs[0].material.opacity") - 0.8) < 1e-6
    assert page.evaluate("window.__part.PT.surfObjs[0].material.transparent") is True
    assert page.inner_text("#pt-surfop-val") == "80 %"
    page.evaluate("window.__part.setSurfOpacity(1)")
    assert page.evaluate("[window.__part.PT.surfObjs[0].material.transparent, window.__part.PT.surfObjs[0].material.depthWrite]") == [False, True]
    assert page.evaluate("localStorage.getItem('pt-surf-opacity')") == "1"
    page.evaluate("window.__part.setSurfOpacity(0.3)")
    page.evaluate("window.__partLoadNamed('ui_op')")
    page.wait_for_function("window.__part.PT.surfObjs && window.__part.PT.surfObjs.length > 0 && Math.abs(window.__part.PT.surfObjs[0].material.opacity - 0.3) < 1e-6")
    page.evaluate("window.__part.setSurfOpacity(0.45)")


def test_part_trim_surface_tool_faces(page, client):
    """Trim surface with faces of the tool: the tool body has two vertical faces across a 100 x 50 target; with
    Pick single faces ticked, one face of the tool fed as the tool gives 2 regions (the whole tool 3); the tool body
    stays shown (not consumed) and the chip summary names the face count."""
    from conftest import part_rec, rect
    def line(i, a, b):
        return {"id": i, "t": "line", "x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1], "layer": "0"}
    p = part_rec("ui_trf", [
        {"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(100, 50)}},
        {"id": "b", "name": "B", "type": "surf_sketch", "kind": "extrude", "depth": 20, "symmetric": True, "plane": "XY", "offset": 0,
         "sketch": {"entities": [line(1, (40, -5), (40, 55)), line(2, (70, -5), (70, 55))]}}])
    client.put("/api/part/file/ui_trf", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_trf')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.a && window.__part.PT.surfaces.b")
    page.evaluate("window.__part.startCommand('surf_trim')")
    page.wait_for_selector("#pf-source")
    page.select_option("#pf-source", "a")
    page.evaluate("window.__part.gotoStep(1)")
    page.evaluate("window.__part.feedCommand({ kind: 'surface', id: 'b' })")
    page.wait_for_function("window.__part.PT.cmd.step === 2 && (window.__part.PT.cmd.regions || []).length === 3")
    # one face of the tool: the pick of a surface body face comes as kind "face" with .surface
    page.evaluate("window.__part.gotoStep(1)")
    page.evaluate("window.__part.PT.cmd.sface = true")
    page.evaluate("() => { const sm = window.__part.PT.surfaces.b; const i = sm.face_keys.findIndex(k => k && Math.abs(k.c[0] - 40) < 1e-6); window.__part.feedCommand({ kind: 'face', fi: i, key: sm.face_keys[i], surface: 'b', point: sm.face_keys[i].c }); }")
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.tool === 'b' && (f.tool_faces || []).length === 1; })()")
    page.wait_for_function("window.__part.PT.cmd.step === 2 && (window.__part.PT.cmd.regions || []).length === 2")
    page.evaluate("window.__part.feedCommand({ kind: 'region', point: window.__part.PT.cmd.regions.find(r => r.point[0] > 40).point })")
    cid = page.evaluate("window.__part.PT.cmd.id")
    page.click("#cmd-finish")
    page.wait_for_function("!window.__part.PT.cmd")
    page.wait_for_function("id => window.__part.PT.status[id] && !window.__part.PT.status[id].pending && !window.__part.PT.status[id].error && window.__part.PT.surfaces[id]", arg=cid, timeout=60000)
    assert page.evaluate("[!!window.__part.PT.hidden.a, !!window.__part.PT.hidden.b]") == [True, False]
    assert page.evaluate("id => window.__part.PT.surfaces[id].face_keys.filter(Boolean).length", cid) == 1
    assert page.evaluate("id => window.__part.feat(id).remove.length", cid) == 1


def test_part_separate_faces_command(page, client):
    """Separate faces from the Surfaces menu: a face of a 4-face surface body fed to the command; OK creates the
    feature with the picked face and a second feature with the remaining faces; the source body is hidden and
    both new bodies exist (1 and 3 faces)."""
    from conftest import part_rec, rect
    p = part_rec("ui_sepf", [{"id": "a", "name": "A", "type": "surf_sketch", "kind": "extrude", "depth": 10, "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20)}}])
    client.put("/api/part/file/ui_sepf", json=p)
    tab(page, "part")
    page.evaluate("window.__partLoadNamed('ui_sepf')")
    page.wait_for_function("window.__part.PT.surfaces && window.__part.PT.surfaces.a && window.__part.PT.surfaces.a.face_keys")
    page.evaluate("document.querySelector('[data-add=surf_separate]').click()")
    page.wait_for_selector("#pt-cmdwin:not([hidden])")
    assert page.inner_text("#pt-cmdwin-title") == "Separate faces"
    page.evaluate("() => { const sm = window.__part.PT.surfaces.a; const i = sm.face_keys.findIndex(k => k && Math.abs(k.c[0] - 40) < 1e-6); window.__part.feedCommand({ kind: 'face', fi: i, key: sm.face_keys[i], surface: 'a', point: sm.face_keys[i].c }); }")
    page.wait_for_function("(() => { const f = window.__part.feat(window.__part.PT.cmd.id); return f.source === 'a' && (f.faces || []).length === 1; })()")
    cid = page.evaluate("window.__part.PT.cmd.id")
    page.evaluate("window.__part.gotoStep(1)")
    page.wait_for_selector("#pf-sprest")
    assert page.is_checked("#pf-sprest")
    page.click("#cmd-finish")
    page.wait_for_function("!window.__part.PT.cmd")
    ids = page.evaluate("window.__part.PT.part.features.filter(x => x.type === 'surf_separate').map(x => [x.id, x.keep, x.faces.length])")
    assert len(ids) == 2 and ids[0][0] == cid and ids[0][1] == "picked" and ids[1][1] == "rest" and ids[1][2] == 1
    rid = ids[1][0]
    page.wait_for_function("([a, b]) => window.__part.PT.surfaces[a] && window.__part.PT.surfaces[b] && !window.__part.PT.status[a].pending && !window.__part.PT.status[b].pending", arg=[cid, rid], timeout=60000)
    assert page.evaluate("([a, b]) => [window.__part.PT.surfaces[a].face_keys.filter(Boolean).length, window.__part.PT.surfaces[b].face_keys.filter(Boolean).length]", [cid, rid]) == [1, 3]
    assert page.evaluate("!!window.__part.PT.hidden.a") is True


def test_dimension_horizontal_text_drag_and_clear(page, client):
    """Drawings: a vertical dimension's text turns horizontal with the Horizontal text checkbox (the text element
    loses its rotation) and back with key T; dragging a note moves it by the drag distance (the group follows the
    mouse during the drag); Clear annotations removes every annotation and Ctrl+Z brings them back."""
    client.put("/api/part/file/ui_htx", json=plate("ui_htx"))
    tab(page, "part")
    file_menu(page, "#tab-part")
    page.select_option("#pt-list", "ui_htx")
    wait_text(page, "#pt-info", "Volume")
    file_menu(page, "#tab-part")
    page.click("#pt-draw")
    page.wait_for_selector("#ann-canvas svg", timeout=120000)
    page.wait_for_function("typeof ED !== 'undefined' && ED.d && ED.d.maps && ED.snapPts.length")
    page.evaluate("""() => { setTool('v'); const P = ED.snapPts.filter(p => p.view === 'front');
        const a = P[0], b = P.find(p => Math.abs(p.X - a.X) < 1e-6 && Math.abs(p.Y - a.Y) > 5);
        toolClick(a.X, a.Y); toolClick(b.X, b.Y); toolClick(a.X - 15, (a.Y + b.Y) / 2); setTool('select'); }""")
    page.wait_for_function("ED.anns.length === 1 && document.querySelector('g.ann')")
    page.evaluate("select(ED.anns[0].id)")
    assert page.is_visible("#ann-horiz-row")
    rotated = page.evaluate("[...document.querySelectorAll('g.ann text')].some(t => /rotate\\(\\s*-?90/.test(t.getAttribute('transform') || ''))")
    assert rotated
    page.check("#ann-horiz")
    page.dispatch_event("#ann-horiz", "change")
    page.wait_for_function("ED.anns[0].text_horizontal === true")
    page.wait_for_function("![...document.querySelectorAll('g.ann text')].some(t => /rotate\\(\\s*-?90/.test(t.getAttribute('transform') || ''))")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("t")
    page.wait_for_function("ED.anns[0].text_horizontal === false")
    # a note, dragged 20 mm to the right on the sheet
    page.evaluate("() => { setTool('note'); toolClick(60, 60); }")
    page.wait_for_selector("#text-dialog:not([hidden]) textarea")
    page.fill("#text-dialog textarea", "NOTE")
    page.click("#text-dialog-ok")
    page.wait_for_function("ED.anns.length === 2 && ED.anns[1].type === 'note' && document.querySelector('g.ann[data-ann=\"' + ED.anns[1].id + '\"]')")
    page.evaluate("setTool('select')")
    box = page.evaluate("""() => { const g = document.querySelector('g.ann[data-ann="' + ED.anns[1].id + '"]'); const r = g.getBoundingClientRect();
        const svg = document.querySelector('#ann-canvas svg'); const k = ED.vb[2] / svg.clientWidth; return [r.x + r.width / 2, r.y + r.height / 2, k]; }""")
    x0, y0, k = box
    px = 20 / k                                   # 20 mm on the sheet in screen pixels
    page.mouse.move(x0, y0)
    page.mouse.down()
    page.mouse.move(x0 + px / 2, y0, steps=4)
    page.mouse.move(x0 + px, y0, steps=4)
    assert page.evaluate("!!ED.drag && ED.drag.moved")
    tr = page.evaluate("document.querySelector('g.ann[data-ann=\"' + ED.anns[1].id + '\"]').getAttribute('transform') || ''")
    assert "translate(" in tr
    before = page.evaluate("ED.anns[1].pos[0]")
    page.mouse.up()
    page.wait_for_function("x0 => Math.abs(ED.anns[1].pos[0] - x0 - 20) < 1", arg=before)
    page.click("#ann-clearall")
    page.wait_for_function("ED.anns.length === 0")
    page.keyboard.press("Control+z")
    page.wait_for_function("ED.anns.length === 2")
    # Decimals of the dimension: the select writes the dimension's decimals and the text shows them
    page.evaluate("select(ED.anns[0].id)")
    set_dec = "v => { const s = document.querySelector('#ann-decimals'); s.value = v; s.dispatchEvent(new Event('change')); }"
    page.evaluate(set_dec, "2")
    page.wait_for_function("ED.anns[0].decimals === 2")
    page.wait_for_function("[...document.querySelectorAll('g.ann text')].some(t => /^\\d+\\.\\d\\d$/.test(t.textContent.trim()))")
    page.evaluate(set_dec, "")
    page.wait_for_function("ED.anns[0].decimals === undefined")
    # the tolerance text option: deviations with the µm unit in the drawing and the mm unit in the fields
    page.evaluate("setOption('tol_unit', 'mm')")
    page.wait_for_function("OPT.tol_unit === 'mm' && document.querySelector('.dev-unit').textContent === 'mm'")
    page.evaluate("setOption('tol_unit', 'um')")
    page.wait_for_function("OPT.tol_unit === 'um' && document.querySelector('.dev-unit').textContent === '\u00b5m'")


def test_drawing_right_click_returns_to_select(page, client):
    """Drawings: a right click on the sheet while a dimension tool is active returns to the Select tool and drops
    the picks of the tool."""
    client.put("/api/part/file/ui_rc", json=plate("ui_rc"))
    tab(page, "part")
    file_menu(page, "#tab-part")
    page.select_option("#pt-list", "ui_rc")
    wait_text(page, "#pt-info", "Volume")
    file_menu(page, "#tab-part")
    page.click("#pt-draw")
    page.wait_for_selector("#ann-canvas svg", timeout=120000)
    page.wait_for_function("typeof ED !== 'undefined' && ED.d && ED.d.maps && ED.snapPts.length")
    page.evaluate("() => { setTool('h'); const a = ED.snapPts.filter(p => p.view === 'front')[0]; toolClick(a.X, a.Y); }")
    assert page.evaluate("ED.tool === 'h' && ED.pick.length === 1")
    box = page.evaluate("() => { const r = document.querySelector('#ann-canvas svg').getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }")
    page.mouse.click(box[0], box[1], button="right")
    page.wait_for_function("ED.tool === 'select' && ED.pick.length === 0")
    assert page.evaluate("document.querySelector('#ann-tools button[data-tool=select]').classList.contains('active')")


def test_drawing_manual_centre_mark_and_line(page, client):
    """Drawings: the Centre tool (key C) makes a centre mark from a click on a circle (two chain lines crossing at
    the centre) and a centre line from two point picks; a drag moves the mark; the properties show no dimension
    fields for it."""
    client.put("/api/part/file/ui_cm", json=plate("ui_cm"))
    tab(page, "part")
    file_menu(page, "#tab-part")
    page.select_option("#pt-list", "ui_cm")
    wait_text(page, "#pt-info", "Volume")
    file_menu(page, "#tab-part")
    page.click("#pt-draw")
    page.wait_for_selector("#ann-canvas svg", timeout=120000)
    page.wait_for_function("typeof ED !== 'undefined' && ED.d && ED.d.maps && ED.circles.length")
    assert page.is_visible("#ann-tools button[data-tool=centre]")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.keyboard.press("c")
    page.wait_for_function("ED.tool === 'centre'")
    # the hole in the top view: a click on its circle
    page.evaluate("() => { const c = ED.circles.find(x => x.view === 'top' && x.kind !== 'hidden') || ED.circles[0]; toolClick(c.X + c.R, c.Y); }")
    page.wait_for_function("ED.anns.length === 1 && ED.anns[0].type === 'centre' && ED.anns[0].c && ED.anns[0].r === 10")
    page.wait_for_function("document.querySelectorAll('g.ann[data-ann=\"' + ED.anns[0].id + '\"] line').length === 4")  # 2 lines + 2 hit lines
    # a centre line between two snap points of the front view
    page.evaluate("""() => { const P = ED.snapPts.filter(p => p.view === 'front'); const a = P[0], b = P.find(p => Math.hypot(p.X - a.X, p.Y - a.Y) > 5);
        toolClick(a.X, a.Y); toolClick(b.X, b.Y); }""")
    page.wait_for_function("ED.anns.length === 2 && ED.anns[1].p1 && ED.anns[1].p2 && ED.anns[1].view === 'front'")
    page.evaluate("setTool('select'); select(ED.anns[0].id)")
    assert page.is_hidden("#ann-dim-fields") and page.is_hidden("#ann-note-fields")
    assert page.evaluate("document.querySelector('#ann-kind').textContent") == "Centre mark"
    assert page.is_visible("#ann-centre-ext")
    page.evaluate("() => { const f = document.querySelector('#ann-centre-ext'); f.value = '6'; f.dispatchEvent(new Event('change')); }")
    page.wait_for_function("ED.anns[0].ext === 6")
    page.wait_for_function("""() => { const l = document.querySelector('g.ann[data-ann="' + ED.anns[0].id + '"] line:not([stroke=transparent])');
        return l && Math.abs(Math.abs(+l.getAttribute('x2') - +l.getAttribute('x1')) - 2 * (10 * ED.d.maps.top[2] + 6)) < 1e-3; }""")
    c0 = page.evaluate("ED.anns[0].c.slice()")
    g = page.evaluate("""() => { const g = document.querySelector('g.ann[data-ann="' + ED.anns[0].id + '"]'); const r = g.getBoundingClientRect();
        const svg = document.querySelector('#ann-canvas svg'); return [r.x + r.width / 2, r.y + 2, ED.vb[2] / svg.clientWidth]; }""")
    px = 10 / g[2]
    page.mouse.move(g[0], g[1])
    page.mouse.down()
    page.mouse.move(g[0] + px / 2, g[1], steps=4)
    page.mouse.move(g[0] + px, g[1], steps=4)
    page.mouse.up()
    f = page.evaluate("ED.d.maps.top[2]")
    page.wait_for_function("([c0, f]) => Math.abs(ED.anns[0].c[0] - c0[0] - 10 / f) < 0.5 && Math.abs(ED.anns[0].c[1] - c0[1]) < 0.5", arg=[c0, f])


def test_explicit_mk2_functions(page, client, tmp_path):
    """Explicit tab, functions: analysis types (Rivet section), Downgrade, Output Dir, travel table, "?"
    pop-ups, Tie dist in Scoped, concentrated mass summary, Tools section, Rivet gauge rings and F-d curve, results
    CSV, overlay, zoom, Save PNG, run history Load Selected."""
    import math
    from drawgen import web
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta && window.__xp.XP.tools")
    dialog = {"path": ""}
    page.route("**/api/dialog", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"path": dialog["path"]})))
    assert page.evaluate("document.querySelector('[data-s=analysis_mode]').value") == "Advanced (all features)"
    assert page.is_visible("#xp-sec-rivet") and page.is_visible("[data-s=downgrade_quad]") and page.is_visible("[data-s=out_dir]")
    page.select_option("[data-s=analysis_mode]", "Impact / drop test")
    assert page.is_hidden("#xp-sec-rivet") and page.is_visible("[data-s=downgrade_quad]")
    page.select_option("[data-s=analysis_mode]", "Rivet coupon calibration")
    assert page.is_visible("#xp-sec-rivet") and page.locator("[data-s=point_mass_json]").count() == 0
    page.select_option("[data-s=analysis_mode]", "Advanced (all features)")
    # travel table of the Explicit driver
    page.select_option("[data-s=rigid_vel_mode]", "Explicit (Vx Vy Vz below)")
    page.fill("[data-s=rigid_vel]", "0 0 -5000")
    page.fill("[data-s=tstop]", "0.01")
    page.dispatch_event("[data-s=tstop]", "input")
    t = page.inner_text("#xp-travel")
    assert "|V| = 5000 mm/s" in t and "100 mm: 0.02 s (NOT reached)" in t and "covers 50 mm" in t
    # "?" pop-up of the tie modes, the selected mode first
    page.click("#xp-buildp [data-help='Tie modes (bonded connections)']")
    assert page.is_visible("#xp-help") and "(selected)" in page.inner_text("#xp-help-b h3")
    assert "Auto (*TIE from INP)" in page.inner_text("#xp-help-b h3")
    page.click("#xp-help-close")
    assert page.is_hidden("#xp-help")
    page.select_option("[data-s=tie_mode]", "Scoped pairs (box below)")
    assert page.is_disabled("[data-s=tie_dist]")
    page.select_option("[data-s=tie_mode]", "Single global tie")
    assert page.is_enabled("[data-s=tie_dist]")
    # concentrated mass (External .inp source): Browse (file dialog) and the summary
    page.select_option("#xp-kind", "inp")
    page.wait_for_selector("#xp-buildp [data-browse-s=point_mass_json]")
    pj = tmp_path / "imp.json"
    pj.write_text(json.dumps({"mass": 0.5, "cx": 0, "cy": 0, "cz": 0, "Jxx": 10, "Jyy": 20, "Jzz": 30, "Jxy": 0, "Jyz": 0, "Jxz": 0}))
    dialog["path"] = str(pj)
    page.click("#xp-buildp [data-browse-s=point_mass_json]")
    wait_text(page, "#xp-inertia", "STATUS : READY")
    page.select_option("#xp-kind", "shinycad")
    page.wait_for_function("!document.querySelector('#xp-buildp [data-browse-s=point_mass_json]')")
    # Output Dir: Browse (folder)
    dialog["path"] = str(tmp_path)
    page.click("#xp-buildp [data-browse-s=out_dir]")
    page.wait_for_function("arg => window.__xp.XP.doc.settings.out_dir === arg", arg=str(tmp_path).replace("\\", "/"))
    # Tools section
    page.click("#xp-sec-tools > summary")
    assert page.locator("#xp-tools [data-tlaunch]").count() >= 16
    assert "Inertia builder" in page.inner_text("#xp-tools")
    page.click("#xp-tools [data-tremove='inp2unv']")
    page.wait_for_function("window.__xp.XP.tools.hidden.includes('inp2unv')")
    assert page.locator("#xp-tools [data-tlaunch='inp2unv']").count() == 0
    page.check("#xp-tl-hidden")
    page.click("#xp-tools [data-trestore='inp2unv']")
    page.wait_for_function("!window.__xp.XP.tools.hidden.includes('inp2unv')")
    page.click("#xp-tools [data-help='Job audit  (CLI)']")
    assert "Audits every job" in page.inner_text("#xp-help-b")
    page.click("#xp-help-close")
    # Rivet: gauge rings on a deck, then the F-d curve
    L = ["#RADIOSS STARTER", "/BEGIN", "rivet", "/NODE"]
    nid = 0
    for z in (1.0, -1.0):
        for k in range(12):
            nid += 1
            a = math.radians(30 * k)
            L.append("%10d%20.6f%20.6f%20.6f" % (nid, 6 * math.cos(a), 6 * math.sin(a), z))
    deck = tmp_path / "cp_0000.rad"
    deck.write_text("\n".join(L + ["/END"]) + "\n")
    rows = ['"time","INTERNAL ENERGY","KINETIC ENERGY","P1 DX","P1 DY","P1 DZ","P2 DX","P2 DY","P2 DZ","RBODY 12 FX"']
    for k in range(11):
        rows.append("%g,%g,%g,%g,0,0,0,0,0,%g" % (k * 1e-4, 5.0 * k, 100.0 - 5.0 * k, 0.1 * k, max(100.0 * k if k <= 6 else 600.0 - 290.0 * (k - 6), 0.0)))
    (tmp_path / "cp_Results.csv").write_text("\n".join(rows) + "\n")
    page.fill("#xp-solvep [data-s=rad_target]", str(deck))
    page.dispatch_event("#xp-solvep [data-s=rad_target]", "change")
    page.click("#xp-sec-rivet > summary")
    page.fill("[data-s=rv_maxnodes]", "4")
    page.dispatch_event("[data-s=rv_maxnodes]", "change")
    page.click("#xp-rv-rings")
    page.wait_for_function("() => document.querySelector('#status-text').textContent.includes('Gauge rings: P1 4 nodes')")
    assert (tmp_path / "gauge_rings.json").exists()
    page.click("#xp-rv-cols-b")
    page.wait_for_function("() => document.querySelectorAll('#xp-rv-cols option').length === 10")
    page.fill("[data-s=rv_force_col]", "RBODY 12 FX")
    page.dispatch_event("[data-s=rv_force_col]", "change")
    page.select_option("[data-s=rv_component]", "x")
    page.click("#xp-rv-extract")
    wait_text(page, ".xp-rvsum", "Peak force        600")
    assert page.locator("#xp-rvplot polyline").count() == 1 and page.locator("#xp-rvplot circle").count() == 1
    dialog["path"] = str(tmp_path / "rv.png")
    page.click("#xp-rv-png")
    page.wait_for_function("() => document.querySelector('#status-text').textContent.includes('rv.png')")
    assert (tmp_path / "rv.png").read_bytes().startswith(b"\x89PNG")
    # Results: Load CSV of two jobs, overlay, zoom, Save PNG
    other = tmp_path / "jo_Results.csv"
    other.write_text('"time","INTERNAL ENERGY","KINETIC ENERGY"\n0,0,50\n0.001,10,40\n')
    for p in (tmp_path / "cp_Results.csv", other):
        dialog["path"] = str(p)
        page.click("#xp-csvload")
        page.wait_for_function("arg => window.__xp.XP.curveSel === arg", arg=p.name.replace("_Results.csv", ""))
    assert page.locator("#xp-plot polyline").count() == 1
    page.check("[data-pv=overlay]")
    assert page.locator("#xp-plot polyline").count() == 2 and "2 jobs overlaid" in page.inner_text("#xp-plot")
    bb = page.locator("#xp-plot svg").bounding_box()
    page.mouse.move(bb["x"] + 100, bb["y"] + 40)
    page.mouse.down()
    page.mouse.move(bb["x"] + 200, bb["y"] + 120, steps=4)
    page.mouse.up()
    assert page.evaluate("!!window.__xp.XP.zoom.energy")
    page.dblclick("#xp-plot svg")
    assert page.evaluate("!window.__xp.XP.zoom.energy")
    dialog["path"] = str(tmp_path / "ke")
    page.click("#xp-pngsave")
    page.wait_for_function("() => document.querySelector('#status-text').textContent.includes('ke.png')")
    assert (tmp_path / "ke.png").read_bytes().startswith(b"\x89PNG")
    # run history: Load Selected sets Target .rad and Output Dir
    run = tmp_path / "hist"
    run.mkdir()
    (run / "hj_0000.rad").write_text("/BEGIN\n/END\n")
    client.post("/api/explicit/history", json={"op": "clear"})
    web.EXPLICIT._history_add("hj", "Done", str(run), "Local (Windows)")
    page.evaluate("document.querySelector('#xp-solvep .xp-hist').open = true")
    page.wait_for_selector("#xp-history tr[data-hj='hj']")
    page.click("#xp-history tr[data-hj='hj']")
    page.click("[data-hop=load]")
    page.wait_for_function("arg => window.__xp.XP.doc.settings.rad_target === arg", arg=str(run / "hj_0000.rad").replace("\\", "/"))
    assert page.evaluate("window.__xp.XP.doc.settings.out_dir") == str(run).replace("\\", "/")
    client.post("/api/explicit/history", json={"op": "clear"})


def test_shell_thickness_view(page, client):
    """Analysis tab, Show Mesh with Shell thickness: the plate section (t 8 mm) drawn as a slab 8 mm thick, centred on
    the mid-surface (offset mid) or on one side (offset positive); off: the mid-surface."""
    from conftest import rect
    client.put("/api/part/file/ui_th_plate", json={"name": "ui_th_plate", "version": 2, "next": 2, "features": [
        {"id": "s1", "name": "Plate", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(100, 50)}}]})
    client.put("/api/assembly/file/ui_th", json={"name": "ui_th", "next": 2, "components": [
        {"id": "1", "name": "plate", "source": {"type": "part", "name": "ui_th_plate"}, "pos": [0, 0, 0], "rot": [0, 0, 0]}]})
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("() => { const s = document.getElementById('fa-source'); s.insertAdjacentHTML('beforeend', '<option value=\"assembly:ui_th\">ui_th</option>'); s.value = 'assembly:ui_th'; s.dispatchEvent(new Event('change')); }")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 1")
    page.evaluate("() => { const FA = window.__fea.FA; FA.doc.sections = [{ id: '1', name: 'PLATE', faces: [{ comp: '1', face: 0 }], t: 8, offset: 'mid' }]; FA.doc.mesh = { size: 10 }; }")
    zr = ("() => { let lo = 1e9, hi = -1e9, n = 0; window.__fea.FA.three.group.traverse(o => { if (o.isMesh && o.userData.kind === 'mesh') {"
          " const p = o.geometry.attributes.position; n += p.count; for (let i = 0; i < p.count; i++) { lo = Math.min(lo, p.getZ(i)); hi = Math.max(hi, p.getZ(i)); } } }); return [lo, hi, n]; }")
    page.click("#fa-mesh")
    page.wait_for_function("document.getElementById('fa-show').value === 'mesh' && window.__fea.FA.mesh", timeout=180000)
    lo, hi, n = page.evaluate(zr)
    assert abs(lo) < 1e-6 and abs(hi) < 1e-6
    assert page.evaluate("window.__fea.FA.mesh.bodies.map(b => [b.t, b.offset])") == [[8, 0]]
    page.check("#fa-thick")
    lo, hi, n2 = page.evaluate(zr)
    assert abs(hi - lo - 8) < 1e-4 and abs(hi + lo) < 1e-4 and n2 > 2 * n - 1
    page.evaluate("() => { window.__fea.FA.doc.sections[0].offset = 'positive'; }")
    page.click("#fa-mesh")
    page.wait_for_function("window.__fea.FA.mesh && window.__fea.FA.mesh.bodies[0].offset === 0.5", timeout=180000)
    lo, hi, _n = page.evaluate(zr)
    assert abs(hi - lo - 8) < 1e-4 and (abs(lo) < 1e-4 or abs(hi) < 1e-4)
    page.uncheck("#fa-thick")
    lo, hi, _n = page.evaluate(zr)
    assert abs(lo) < 1e-6 and abs(hi) < 1e-6


def test_update_geometry_after_assembly_change(page, client):
    """Analysis and Explicit tabs: a change of the assembly (a component moved) and of a part (a new size) marks
    Update; Update loads the geometry again and clears the mark and the mesh."""
    from conftest import rect

    def put_part(w):
        client.put("/api/part/file/ui_up_plate", json={"name": "ui_up_plate", "version": 2, "next": 2, "features": [
            {"id": "s1", "name": "Plate", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(w, 50)}}]})

    def put_asm(x):
        client.put("/api/assembly/file/ui_up", json={"name": "ui_up", "next": 2, "components": [
            {"id": "1", "name": "plate", "source": {"type": "part", "name": "ui_up_plate"}, "pos": [x, 0, 0], "rot": [0, 0, 0]}]})
    put_part(100)
    put_asm(0)
    for pre, ns in (("fa", "__fea.FA"), ("xp", "__xp.XP")):
        k0 = client.post("/api/geometry/state", json={"source": {"type": "assembly", "name": "ui_up"}}).get_json()["key"]
        tab(page, "fea" if pre == "fa" else "xp")
        page.wait_for_function("window.%s && window.%s.doc" % (ns.split(".")[0], ns))
        page.evaluate("() => { const s = document.getElementById('%s-source'); s.insertAdjacentHTML('beforeend', '<option value=\"assembly:ui_up\">ui_up</option>'); s.value = 'assembly:ui_up'; s.dispatchEvent(new Event('change')); }" % pre)
        page.wait_for_function("window.%s.geo && window.%s.geo.components.length === 1 && window.%s.geoKey" % (ns, ns, ns))
        assert page.evaluate("window.%s.geoKey" % ns) == k0
        assert not page.evaluate("document.getElementById('%s-update').classList.contains('cm-stale')" % pre)
        put_asm(30 if pre == "fa" else 60)
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        page.wait_for_function("document.getElementById('%s-update').classList.contains('cm-stale')" % pre, timeout=15000)
        page.click("#%s-update" % pre)
        page.wait_for_function("!document.getElementById('%s-update').classList.contains('cm-stale')" % pre, timeout=60000)
        assert page.evaluate("window.%s.asm.components[0].pos[0]" % ns) == (30 if pre == "fa" else 60)
        assert page.evaluate("window.%s.mesh" % ns) is None
        put_part(120 if pre == "fa" else 140)                   # a part change also marks Update
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        page.wait_for_function("document.getElementById('%s-update').classList.contains('cm-stale')" % pre, timeout=15000)
        page.click("#%s-update" % pre)
        page.wait_for_function("!document.getElementById('%s-update').classList.contains('cm-stale')" % pre, timeout=60000)


def test_analysis_contact_and_plastic_material(page, client, web):
    """Analysis tab: a block on a block; Search finds the contact pair (master: the larger face), friction typed;
    material law plastic from the material library (hardening table), Nonlinear step settings; Solve: increments in
    State, PEEQ field, load history plot and a click on a point shows that increment."""
    from test_analysis import CCX, _stack
    if CCX is None:
        pytest.skip("CalculiX (ccx) not found")
    asm, F = _stack(client, web, "ui_ct")
    client.put("/api/assembly/file/ui_ct", json=dict(asm, name="ui_ct", next=3))
    doc = {"name": "ui_ct", "source": {"type": "assembly", "name": "ui_ct"}, "materials": {"Steel": {"E": 210000, "nu": 0.3, "rho": 7850}},
           "default_material": "Steel", "mesh": {"size": 5}, "bonded": True, "bodies": {}, "members": [], "plates": [], "fasteners": [], "loads": [],
           "supports": [{"id": "s1", "name": "base", "target": F["lo_bot"], "type": "fixed"},
                        {"id": "s2", "name": "press", "target": F["hi_top"], "type": "displacement", "dofs": [1, 1, 1, 0, 0, 0], "value": [0, 0, -0.03, 0, 0, 0]}],
           "next": 10}
    client.put("/api/analysis/file/ui_ct", json=doc)
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.evaluate("window.__feaLoadNamed('ui_ct')")
    page.wait_for_function("window.__fea.FA.geo && window.__fea.FA.geo.components.length === 2 && window.__fea.FA.matlib && window.__fea.FA.matlib.length")
    # contact: Search
    page.fill("#fc-gap", "0.2")
    page.dispatch_event("#fc-gap", "change")
    page.click("#fc-search")
    page.wait_for_function("(window.__fea.FA.doc.contacts || []).length === 1")
    c = page.evaluate("window.__fea.FA.doc.contacts[0]")
    assert c["master"] == [F["lo_top"]] and c["slave"] == [F["hi_bot"]] and c["type"] == "surface"
    page.click("#fa-contacts .fa-item")
    page.fill("#fc-mu", "0.2")
    page.dispatch_event("#fc-mu", "change")
    assert page.evaluate("window.__fea.FA.doc.contacts[0].friction") == 0.2
    page.click("#fc-search")                                   # the same pair is not added twice
    page.wait_for_function("document.querySelector('#status-text').textContent.includes('0 added')")
    # material: library S355 sets plastic with its table
    page.select_option("#fa-mats tr[data-n='Steel'] [data-k=library]", "Steel S355 (DNVGL 19-Point Standard)")
    m = page.evaluate("window.__fea.FA.doc.materials.Steel")
    assert m["law"] == "plastic" and m["plastic"][0] == [355, 0] and len(m["plastic"]) == 19
    assert page.is_visible("#fa-mats textarea[data-mk=plastic]")
    # the hardening curve plotted against the plastic strain, then the total strain (from 0, plastic strain + stress / E)
    assert page.locator("#fa-matcurve svg polyline").count() == 1 and "true plastic strain" in page.text_content("#fa-matcurve")
    page.select_option("#fa-matcurve [data-mc=x]", "total")
    assert "true total strain" in page.text_content("#fa-matcurve") and page.evaluate("window.__fea.FA.matPlot.x") == "total"
    with page.expect_download() as dl:
        page.click("#fa-matcurve [data-mc=csv]")
    rows = open(dl.value.path()).read().splitlines()
    assert rows[0].startswith('"true total strain"') and rows[1] == "0,0" and float(rows[2].split(",")[0]) == pytest.approx(355 / 210000)
    page.select_option("#fa-mats tr[data-n='Steel'] [data-k=law]", "plastic:kinematic")
    assert page.evaluate("window.__fea.FA.doc.materials.Steel.hardening") == "kinematic"
    page.select_option("#fa-mats tr[data-n='Steel'] [data-k=law]", "plastic:isotropic")
    assert "(used:" in page.inner_text("#fa-settings")
    page.fill("#fa-settings [data-nl=incmax]", "0.25")
    page.dispatch_event("#fa-settings [data-nl=incmax]", "change")
    assert page.evaluate("window.__fea.FA.doc.nonlinear.incmax") == 0.25
    page.click("#fa-solve")
    page.wait_for_function("window.__fea.FA.res && window.__fea.FA.res.tables && window.__fea.FA.res.history", timeout=300000)
    opts = page.evaluate("[...document.querySelectorAll('#fa-state option')].map(o => o.value)")
    assert opts[0] == "total" and opts[1] == "i1" and len(opts) >= 5
    assert "End of the step" in page.inner_text("#fa-state")
    assert page.locator("#fr-hplot circle").count() == len(opts) - 1
    page.select_option("#fr-hy", "r1_2")
    page.locator("#fr-hplot circle").nth(1).click()
    assert page.evaluate("document.querySelector('#fa-state').value") == "i2"
    page.select_option("#fa-field", "peeq")
    assert "PEEQ" in page.inner_text("#fa-legend")
    if os.environ.get("DRAWGEN_SHOTS"):
        page.evaluate("document.getElementById('fa-results-card').scrollIntoView()")
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "fea_nonlinear.png"))
        page.click("#fa-contacts .fa-item")
        page.evaluate("document.getElementById('fa-mats-card').scrollIntoView()")
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "fea_mats.png"))
        page.evaluate("document.getElementById('fa-contacts-card').scrollIntoView()")
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "fea_contacts.png"))


def test_explicit_status_bar_popups_masses_and_panels(page, client):
    """Explicit tab: status bar items (geometry, materials, bodies, mesh, supports, loading, masses, deck); the Materials
    pop-up changes the Materials table of the Model panel and the reverse; Bodies pop-up; point and distributed mass
    (face picked) in the Masses pop-up, the sphere and face in the view; Panels row hides Springs and Masses (status
    item opens the pop-up); Analysis tab Panels row hides the Joints card."""
    from conftest import part_rec, rect
    client.put("/api/part/file/ui_m_blk", json=part_rec("ui_m_blk", [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                                                                       "sketch": {"entities": rect(40, 40)}, "depth": 20}]))
    client.put("/api/assembly/file/ui_m", json={"name": "ui_m", "next": 2, "components": [
        {"id": "1", "name": "block", "source": {"type": "part", "name": "ui_m_blk"}, "pos": [0, 0, 0], "rot": [0, 0, 0]}]})
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-source", "assembly:ui_m")
    page.wait_for_function("window.__xp.XP.geo && window.__xp.XP.geo.components.length === 1 && window.__xp.XP.three.group.children.length")
    st = lambda k: page.get_attribute("#xp-statusbar [data-st=%s]" % k, "class")
    assert "ok" in st("geo") and "ok" in st("bodies") and "bad" in st("mesh") and "warn" in st("sups")
    assert page.locator("#xp-statusbar [data-st]").count() >= 8
    # Materials pop-up <-> panel
    page.click("#xp-statusbar [data-st=mats]")
    page.wait_for_selector("#xp-pop:not([hidden]) .xp-mats")
    page.select_option("#xp-pop tr[data-m] [data-mk=library]", "")
    assert page.input_value("#xp-model tr[data-m] [data-mk=library]") == ""
    page.fill("#xp-pop tr[data-m] [data-mk=E]", "70000")
    page.dispatch_event("#xp-pop tr[data-m] [data-mk=E]", "change")
    assert page.input_value("#xp-model tr[data-m] [data-mk=E]") == "70000"
    page.fill("#xp-model tr[data-m] [data-mk=nu]", "0.33")
    page.dispatch_event("#xp-model tr[data-m] [data-mk=nu]", "change")
    assert page.input_value("#xp-pop tr[data-m] [data-mk=nu]") == "0.33"
    page.fill("#xp-pop tr[data-m] [data-mk=rho]", "0")
    page.dispatch_event("#xp-pop tr[data-m] [data-mk=rho]", "change")
    assert "bad" in st("mats")
    page.fill("#xp-pop tr[data-m] [data-mk=rho]", "2700")
    page.dispatch_event("#xp-pop tr[data-m] [data-mk=rho]", "change")
    assert "ok" in st("mats")
    nm = page.locator("#xp-model tr[data-m]").count()
    page.click("#xp-pop [data-xpmat=add]")
    assert page.locator("#xp-model tr[data-m]").count() == nm + 1 and page.locator("#xp-pop tr[data-m]").count() == nm + 1
    # Bodies pop-up
    page.click("#xp-statusbar [data-st=bodies]")
    page.select_option("#xp-pop tr[data-b] [data-bk=role]", "off")
    assert "bad" in st("bodies") and page.input_value("#xp-model tr[data-b] [data-bk=role]") == "off"
    page.select_option("#xp-pop tr[data-b] [data-bk=role]", "deformable")
    # masses: a reference point, a point mass on it, a distributed mass on a picked face
    page.evaluate("window.__xp.XP.doc.points = [{id: 'p1', name: 'P1', xyz: [20, 20, 30], coupling: 'none'}]; window.__xp.renderModel(); window.__xp.draw();")
    page.click("#xp-statusbar [data-st=masses]")
    page.wait_for_selector("#xp-pop:not([hidden]) [data-ma=point]")
    page.click("#xp-pop [data-ma=point]")
    page.click("#xp-pop [data-ma=distributed]")
    ms = page.evaluate("window.__xp.XP.doc.masses")
    assert ms[0]["target"] == {"point": "p1"} and ms[1]["target"] == {"faces": []}
    page.click("#xp-pop [data-mface]")
    scr = ("([T, p]) => { const r = T.renderer.domElement.getBoundingClientRect();"
           " const v = new (Object.getPrototypeOf(T.camera.position).constructor)(...p).project(T.camera);"
           " return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; }")
    xy = page.evaluate("(a) => (%s)([window.__xp.XP.three, a])" % scr, [12, 14, 20])
    page.mouse.click(xy[0], xy[1])
    page.keyboard.press("Enter")
    page.wait_for_function("window.__xp.XP.doc.masses[1].target.faces.length === 1")
    assert page.locator("#xp-model .xp-mass").count() == 2 and "warn" in st("masses")
    assert "Mesh to check" in page.inner_text("#xp-statusbar [data-st=masses]")
    page.select_option("#xp-pop [data-mass=%s] [data-mk2=mode]" % ms[1]["id"], "area")
    if os.environ.get("DRAWGEN_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["DRAWGEN_SHOTS"], "xp_status_masses.png"))
    assert "kg/m^2" in page.inner_text("#xp-pop [data-mass=%s]" % ms[1]["id"])
    assert page.evaluate("(() => { let n = 0; window.__xp.XP.three.group.traverse(o => { if (o.geometry && o.geometry.type === 'SphereGeometry') n++; }); return n; })()") == 1
    page.click("#xp-model-btn")
    page.wait_for_function("window.__xp.XP.meshSummary && window.__xp.XP.meshSummary.total_kg > 0", timeout=120000)
    t = page.inner_text("#xp-statusbar [data-st=masses]")
    assert "ok" in st("masses") and "model" in t and "kg" in t and "Mass: model" in page.inner_text("#xp-model")
    assert "ok" in st("mesh")
    page.fill("#xp-pop [data-mass=%s] [data-mk2=m]" % ms[0]["id"], "160")
    page.dispatch_event("#xp-pop [data-mass=%s] [data-mk2=m]" % ms[0]["id"], "change")
    assert "warn" in st("mesh") and "changed since Mesh" in page.inner_text("#xp-statusbar [data-st=mesh]") and "Mesh to check" in page.inner_text("#xp-statusbar [data-st=masses]")
    page.fill("#xp-pop [data-mass=%s] [data-mk2=m]" % ms[0]["id"], "1")
    page.dispatch_event("#xp-pop [data-mass=%s] [data-mk2=m]" % ms[0]["id"], "change")
    assert "ok" in st("mesh")
    # Panels row
    page.keyboard.press("Escape")
    assert page.is_hidden("#xp-pop")
    page.uncheck("#xp-panels [data-ptog=springs]")
    page.uncheck("#xp-panels [data-ptog=masses]")
    assert page.locator("#xp-springs").count() == 0 and page.locator("#xp-masses").count() == 0
    assert "Masses (2)" in page.inner_text("#xp-panels") and sorted(page.evaluate("window.__xp.XP.doc.panels_hidden")) == ["masses", "springs"]
    page.click("#xp-statusbar [data-st=masses]")
    page.wait_for_selector("#xp-pop:not([hidden]) .xp-mass")
    page.keyboard.press("Escape")
    assert page.is_hidden("#xp-pop")
    # rigid parts and concentrated mass of the Build panel: not for a ShinyCAD model
    assert page.locator("#xp-buildp [data-s=rigid_part]").count() == 0 and page.locator("#xp-buildp [data-s=point_mass_json]").count() == 0
    # Analysis tab
    tab(page, "fea")
    page.wait_for_function("window.__fea && window.__fea.FA.doc")
    page.wait_for_selector("#fa-panels [data-ptog=joints]")
    page.uncheck("#fa-panels [data-ptog=joints]")
    assert page.is_hidden("#fa-joints-card") and page.evaluate("window.__fea.FA.doc.panels_hidden") == ["joints"]
    page.check("#fa-panels [data-ptog=joints]")
    assert page.is_visible("#fa-joints-card")


def test_explicit_initial_state_panel(page, client):
    """Explicit tab, Initial state (static): an Analysis document chosen, Solve static (Mesh first, CalculiX on the
    Explicit mesh), the result line, Use in Build and the status bar item; the pop-up of the item."""
    from conftest import part_rec, rect
    from drawgen import analysis
    if not analysis.find_ccx(os.environ.get("DRAWGEN_CCX", "")):
        pytest.skip("CalculiX (ccx) not found")
    client.put("/api/part/file/ui_is_blk", json=part_rec("ui_is_blk", [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                                                                         "sketch": {"entities": rect(40, 40)}, "depth": 20}]))
    client.put("/api/assembly/file/ui_is", json={"name": "ui_is", "next": 2, "components": [
        {"id": "1", "name": "block", "source": {"type": "part", "name": "ui_is_blk"}, "pos": [0, 0, 0], "rot": [0, 0, 0]}]})
    c = client.post("/api/assembly/build", json={"assembly": client.get("/api/assembly/file/ui_is").get_json()}).get_json()["components"][0]
    face = lambda ax, v: next(i for i, r in enumerate(c["refs"]) if r and r["kind"] == "plane" and abs(r["c"][ax] - v) < 1e-6 and abs(abs(r["n"][ax]) - 1) < 1e-6)
    client.put("/api/analysis/file/ui_is_pre", json={"name": "ui_is_pre", "source": {"type": "assembly", "name": "ui_is"},
                                                     "supports": [{"id": "a", "name": "base", "target": {"comp": "1", "face": face(2, 0)}, "type": "fixed"}],
                                                     "loads": [{"id": "p", "name": "p", "type": "pressure", "target": {"comp": "1", "face": face(2, 20)}, "value": 5.0}]})
    tab(page, "xp")
    page.wait_for_function("window.__xp && window.__xp.XP.doc && window.__xp.XP.meta")
    page.select_option("#xp-source", "assembly:ui_is")
    page.wait_for_function("window.__xp.XP.geo && window.__xp.XP.geo.components.length === 1")
    page.wait_for_function("document.querySelector('#xp-init [data-ik=analysis] option[value=ui_is_pre]')")
    page.select_option("#xp-init [data-ik=analysis]", "ui_is_pre")
    assert page.evaluate("window.__xp.XP.doc.initial_state.analysis") == "ui_is_pre"
    page.click("#xp-init [data-isolve]")
    page.wait_for_function("document.querySelector('#xp-init .xp-init-st').textContent.includes('max displacement')", timeout=180000)
    assert "ui_is_pre" in page.inner_text("#xp-init .xp-init-st")
    page.check("#xp-init [data-s=init_state]")
    assert "ok" in page.get_attribute("#xp-statusbar [data-st=init]", "class")
    page.click("#xp-statusbar [data-st=init]")
    page.wait_for_selector("#xp-pop:not([hidden]) [data-isolve]")
    assert "max displacement" in page.inner_text("#xp-pop")
    page.keyboard.press("Escape")
