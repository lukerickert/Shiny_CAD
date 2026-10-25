# -*- coding: utf-8 -*-
"""Server tests with the Flask test client: projects, parts, STEP export, drawings (PDF, DXF, SVG), sketches,
assemblies (build, view cache, solve, interference, STEP export). Everything is written to the
temporary project "tests" (conftest.py)."""
import io
import json
import math
import os

import pytest

from conftest import plate, rect, sketch_part

BOX = 100.0 * 50.0 * 20.0
PLATE_VOL = BOX - math.pi * 100 * 20


def ok(r):
    assert r.status_code == 200, r.get_data(as_text=True)[:500]
    return r.get_json()


def save_part(client, p):
    return ok(client.put("/api/part/file/" + p["name"], json=p))


def project_dir(web):
    return web.PROJECTS.project_dir(web.PROJECTS.current_name())


# --------------------------------------------------------------------------- projects and documents

def test_project_open(client):
    j = ok(client.get("/api/projects"))
    assert j["current"] == "tests"
    assert j["dirs"]["step"].endswith("step") and j["dirs"]["work"].endswith("work")


def test_part_save_list_load(client):
    save_part(client, plate("plate_a"))
    assert "plate_a" in ok(client.get("/api/part/list"))
    p = ok(client.get("/api/part/file/plate_a"))
    assert p["name"] == "plate_a" and any(f["type"] == "extrude" for f in p["features"])


def test_document_rename_copy_version_delete(client):
    save_part(client, plate("doc_a"))
    ok(client.post("/api/project/doc", json={"op": "rename", "type": "part", "name": "doc_a", "new": "doc b"}))
    names = ok(client.get("/api/part/list"))
    assert "doc_b" in names and "doc_a" not in names              # names follow the file name rule
    ok(client.post("/api/project/doc", json={"op": "copy", "type": "part", "name": "doc_b", "new": "doc_c"}))
    v = ok(client.post("/api/project/doc", json={"op": "snapshot", "type": "part", "name": "doc_b", "note": "first"}))
    assert v["version"] == 1
    vs = ok(client.post("/api/project/doc", json={"op": "versions", "type": "part", "name": "doc_b"}))
    assert vs and vs[0]["note"] == "first"
    ok(client.post("/api/project/doc", json={"op": "delete", "type": "part", "name": "doc_c"}))
    assert "doc_c" not in ok(client.get("/api/part/list"))
    docs = ok(client.get("/api/project/docs"))
    assert any(d["name"] == "doc_b" and d["type"] == "part" for d in docs["docs"])


def test_project_state_roundtrip(client):
    st = {"tab": "part", "part": "plate_a", "settings": {"sheet": "A3"}}
    r = client.put("/api/project/state/s1", data=json.dumps(st), content_type="application/json")
    ok(r)
    assert ok(client.get("/api/project/state/s1"))["part"] == "plate_a"
    assert any(s["name"] == "s1" for s in ok(client.get("/api/project/states")))


# --------------------------------------------------------------------------- part build and STEP

def test_part_build(client):
    j = ok(client.post("/api/part/build", json={"part": plate()}))
    assert not [s for s in j["status"] if s.get("error")]
    assert len(j["mesh"]["face_keys"]) == 7


def test_step_export_and_reimport(client, web):
    p = plate("plate_step")
    j = ok(client.post("/api/part/export", json={"part": p, "folder": "", "overwrite": True}))
    path = j["written"][0]
    assert path.startswith(os.path.join(project_dir(web), "step"))
    from drawgen import model
    parts = model.load_step(path)
    assert len(parts) == 1 and parts[0].volume == pytest.approx(PLATE_VOL, rel=1e-6)


# --------------------------------------------------------------------------- drawings

@pytest.fixture(scope="module")
def drawing_sel(client):
    j = ok(client.post("/api/part/to_drawings", json={"part": plate("plate_dwg")}))
    f = j["files"][0]
    return [{"file_id": f["file_id"], "part_ids": [p["id"] for p in f["parts"]]}]


def test_preview(client, drawing_sel):
    j = ok(client.post("/api/preview", json={"selection": drawing_sel, "settings": {"sheet": "A3", "scale": "auto"}}))
    d = j["drawings"][0]
    assert d["sheet"] == "A3" and d["svg"].startswith("<svg")
    assert {"front", "top", "right"} <= set(d["all_views"])


def test_export_pdf_dxf_svg(client, drawing_sel, web):
    j = ok(client.post("/api/export", json={"selection": drawing_sel, "settings": {"sheet": "A3"},
                                            "formats": ["pdf", "dxf", "svg"], "out_dir": ""}))
    files = {os.path.splitext(p)[1]: p for p in j["written"]}
    assert set(files) == {".pdf", ".dxf", ".svg"}
    assert all(p.startswith(os.path.join(project_dir(web), "drawings")) for p in files.values())
    with open(files[".pdf"], "rb") as f:
        pdf = f.read()
    assert pdf.startswith(b"%PDF") and (b"1190.55" in pdf or b"1191" in pdf)          # A3 landscape, 420 mm
    import ezdxf
    doc = ezdxf.readfile(files[".dxf"])
    layers = {l.dxf.name for l in doc.layers}
    assert {"VISIBLE", "FRAME", "TITLE"} <= layers
    msp = doc.modelspace()
    assert len(msp.query('*[layer=="VISIBLE"]')) > 10
    assert any(c.dxf.radius > 0 for c in msp.query("CIRCLE"))                       # the hole in the top view


def test_annotations_roundtrip(client, drawing_sel):
    j = ok(client.post("/api/preview", json={"selection": drawing_sel}))
    name = j["drawings"][0]["ann_name"]
    anns = [{"id": "a1", "type": "note", "view": "front", "p": [0, 0], "text": "TEST NOTE"}]
    ok(client.put("/api/annotations/" + name, json=anns))
    assert ok(client.get("/api/annotations/" + name))[0]["text"] == "TEST NOTE"


def test_options_inch_drawing(client, drawing_sel):
    """Options: inch drawing units change the dimension text and the title block Units field; invalid values fail."""
    assert ok(client.get("/api/options")) == {"units": "mm", "keys": "default", "browser": ""}
    assert ok(client.put("/api/options", json={"browser": "msedge --app={url}"}))["browser"] == "msedge --app={url}"
    assert ok(client.put("/api/options", json={"browser": ""}))["browser"] == ""
    assert client.put("/api/options", json={"units": "yard"}).status_code == 400
    j = ok(client.post("/api/preview", json={"selection": drawing_sel}))
    name = j["drawings"][0]["ann_name"]
    anns = [{"id": "d1", "type": "linear", "view": "front", "p1": [0, 0], "p2": [25.4, 0], "orient": "h", "pos": [12.7, 30],
             "tol": {"mode": "dev", "plus": 0.0254, "minus": 0}}]
    ok(client.put("/api/annotations/" + name, json=anns))
    try:
        svg = ok(client.post("/api/preview", json={"selection": drawing_sel}))["drawings"][0]["svg"]
        assert ">25.4<" in svg and ">+25.4<" in svg
        assert ok(client.put("/api/options", json={"units": "inch", "keys": "left"})) == {"units": "inch", "keys": "left", "browser": ""}
        svg = ok(client.post("/api/preview", json={"selection": drawing_sel}))["drawings"][0]["svg"]
        assert ">1.000<" in svg and ">+.0010<" in svg and ">-.0000<" in svg and ">in<" in svg
    finally:
        ok(client.put("/api/options", json={"units": "mm", "keys": "default"}))
        ok(client.put("/api/annotations/" + name, json=[]))


def test_sketch_on_drawing(client, drawing_sel):
    """A sketch on a view and one on the sheet: stored with the drawing, drawn on it (view sketch through the view
    map, chain line on layer CHAIN), left out of the editing background, removed when empty."""
    j = ok(client.post("/api/preview", json={"selection": drawing_sel}))
    d = j["drawings"][0]
    name, mp = d["ann_name"], d["maps"]["front"]
    base = ok(client.post("/api/drawing/sketch_base", json={"selection": drawing_sel, "name": d["name"], "target": "front"}))
    assert base["map"][:5] == mp[:5] and base["doc"] is None and base["ann_name"] == name
    assert any(r["t"] == "line" and r["kind"] == "proj" for r in base["refs"])
    assert ok(client.post("/api/drawing/sketch_base", json={"selection": drawing_sel, "name": d["name"], "target": "sheet"}))["map"] is None
    line = {"id": "e1", "t": "line", "layer": "CENTRE", "x1": 0.0, "y1": -33.0, "x2": 10.0, "y2": -33.0}
    doc = {"name": "s", "layers": [{"name": "CENTRE", "linetype": "CENTER", "on": True}], "entities": [line], "dims": [], "constraints": []}
    anns = [{"id": "d1", "type": "linear", "p1": [0, 0], "p2": [10, 0], "orient": "h", "pos": [5, 4]}]
    assert ok(client.put("/api/drawing/sketch/%s/front" % name, json={"doc": doc, "anns": anns}))["targets"] == ["front"]
    sheet_doc = dict(doc, entities=[dict(line, id="e2", layer="0", x1=20.0, y1=20.0, x2=40.0, y2=20.0)])
    ok(client.put("/api/drawing/sketch/%s/sheet" % name, json={"doc": sheet_doc, "anns": []}))
    assert client.put("/api/drawing/sketch/%s/bogus" % name, json={"doc": doc}).status_code == 400
    try:
        d2 = ok(client.post("/api/preview", json={"selection": drawing_sel}))["drawings"][0]
        assert d2["sketches"] == ["front", "sheet"]
        # the sketch line ends and mid point snap in the front view (dimensions to sketch corners)
        sp = {(round(p[0], 4), round(p[1], 4)) for p in d2["snaps"]["front"]["points"]}
        assert {(0.0, -33.0), (10.0, -33.0), (5.0, -33.0)} <= sp
        assert [0.0, -33.0, 10.0, -33.0] in d2["snaps"]["front"]["lines"]
        cx, cy, f, bx, by = mp[:5]
        x1, x2, y = cx + f * (0 - bx), cx + f * (10 - bx), cy + f * (-33 - by)
        H = d2["size"][1]
        el = '<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f"' % (x1, H - y, x2, H - y)
        assert el in d2["svg"]
        assert ('y1="%.3f"' % (H - 20.0)) in d2["svg"] and ">10<" in d2["svg"]
        base = ok(client.post("/api/drawing/sketch_base", json={"selection": drawing_sel, "name": d["name"], "target": "front"}))
        assert base["doc"]["entities"][0]["id"] == "e1" and el not in base["svg"]
        from drawgen import sketch
        prims = sketch.drawing_prims({"doc": doc, "anns": []}, mp, {"line_widths_mm": {"visible": 0.5, "hidden": 0.25}})
        assert prims[0][0] == "line" and prims[0][5] == "chain"
    finally:
        ok(client.put("/api/drawing/sketch/%s/front" % name, json={"doc": {}}))
        assert ok(client.put("/api/drawing/sketch/%s/sheet" % name, json={"doc": {}}))["targets"] == []
    assert ok(client.post("/api/preview", json={"selection": drawing_sel}))["drawings"][0]["sketches"] == []


# --------------------------------------------------------------------------- sketches

def test_sketch_save_and_dxf_export(client):
    sk = {"name": "sk1", "units": "mm", "entities": rect(40, 20), "constraints": [], "dims": [], "next_id": 5}
    ok(client.put("/api/sketch/file/sk1", json=sk))
    assert "sk1" in ok(client.get("/api/sketch/list"))
    r = client.post("/api/sketch/export", json={"sketch": sk, "format": "dxf", "folder": "", "overwrite": True})
    j = ok(r)
    import ezdxf
    doc = ezdxf.readfile(j["written"][0] if "written" in j else j["path"])
    assert len(doc.modelspace().query("LINE")) == 4


# --------------------------------------------------------------------------- assemblies

def asm(comps, mates=()):
    return {"name": "asm1", "components": comps, "mates": list(mates), "next": 20}


def comp(cid, name, pos=(0, 0, 0), **kw):
    c = {"id": cid, "name": name, "source": {"type": "part", "name": "plate_a"}, "pos": list(pos), "rot": [0, 0, 0],
         "visible": True}
    c.update(kw)
    return c


def test_assembly_build_mass_and_view_cache(client):
    a = asm([comp("c1", "A", fixed=True), comp("c2", "B", (0, 0, 40))])
    j = ok(client.post("/api/assembly/build", json={"assembly": a, "have": [], "density": 7850}))
    cs = j["components"]
    assert all(c.get("mesh") and c.get("mkey") for c in cs)
    assert cs[0]["mkey"] == cs[1]["mkey"]                                              # same source, one mesh
    assert cs[1]["matrix"][11] == pytest.approx(40)
    assert j["mass"]["total"]["volume_mm3"] == pytest.approx(2 * PLATE_VOL, rel=1e-6)
    j2 = ok(client.post("/api/assembly/build", json={"assembly": a, "have": [cs[0]["mkey"]]}))
    assert all("mesh" not in c for c in j2["components"])                              # client holds the mesh


def test_assembly_solve_datums_and_interference(client):
    a = asm([comp("c1", "A", fixed=True), comp("c2", "B", (13, 7, 55))],
            [{"id": "m1", "type": "coincident", "a": {"comp": "c2", "datum": "plane:XY"}, "b": {"comp": "c1", "datum": "plane:XY"},
              "flip": True},
             {"id": "m2", "type": "coincident", "a": {"comp": "c2", "datum": "axis:Z"}, "b": {"comp": "c1", "datum": "axis:Z"},
              "flip": True},
             {"id": "m3", "type": "parallel", "a": {"comp": "c2", "datum": "axis:X"}, "b": {"comp": "c1", "datum": "axis:X"},
              "flip": True}])
    j = ok(client.post("/api/assembly/solve", json={"assembly": a}))
    assert j["residual"] < 1e-6, j["messages"]
    assert j["placements"]["c2"]["pos"] == pytest.approx([0, 0, 0], abs=1e-6)
    a["components"][1].update(j["placements"]["c2"])
    j = ok(client.post("/api/assembly/build", json={"assembly": a, "interference": True}))
    assert len(j["interference"]) == 1 and j["interference"][0]["volume_mm3"] == pytest.approx(PLATE_VOL, rel=1e-4)


def test_assembly_step_export(client, web):
    a = asm([comp("c1", "A"), comp("c2", "B", (0, 0, 40))])
    j = ok(client.post("/api/assembly/export", json={"assembly": a, "folder": "", "overwrite": True}))
    from drawgen import model
    parts = model.load_step(j["written"][0])
    assert len(parts) == 2 and [p.name for p in parts] == ["A", "B"]


def test_step_component_split(client, tmp_path):
    """Components from a STEP file with two solids, one per solid."""
    from build123d import Box, Compound, Pos, export_step
    path = str(tmp_path / "two.step")
    a, b = Box(10, 10, 10), Pos(50, 0, 0) * Box(20, 10, 10)
    a.label, b.label = "SMALL", "LARGE"
    export_step(Compound(children=[a, b]), path)
    solids = ok(client.post("/api/assembly/step_solids", json={"path": path}))
    assert [s["name"] for s in solids] == ["SMALL", "LARGE"]
    comps = [{"id": "c%d" % s["index"], "name": s["name"], "source": {"type": "step", "path": path, "part": s["index"]},
              "pos": [0, 0, 0], "rot": [0, 0, 0]} for s in solids]
    j = ok(client.post("/api/assembly/build", json={"assembly": asm(comps), "density": 1000}))
    vols = [r["volume_mm3"] for r in j["mass"]["rows"]]
    assert vols == pytest.approx([1000, 2000])
    # Documents: the solids of the STEP file are listed with the number of components using each
    comps.append(dict(comps[0], id="c9", name="SMALL 2"))
    comps.append({"id": "c10", "name": "fea_plate", "source": {"type": "part", "name": "plate_a"}, "pos": [0, 0, 0], "rot": [0, 0, 0]})
    ok(client.put("/api/assembly/file/two_solids", json=asm(comps)))
    d = next(x for x in ok(client.get("/api/project/docs"))["docs"] if x["type"] == "assembly" and x["name"] == "two_solids")
    steps = sorted((l["solid"], l["count"]) for l in d["links"] if l["type"] == "step")
    assert steps == [("LARGE", 1), ("SMALL", 2)]
    assert {"type": "part", "name": "plate_a", "count": 1} in d["links"]


def test_assembly_sketches_of_parts(client):
    """A part with a sketch only: its four lines and corners, placed with the component; a sketch used by an extrude
    is not returned."""
    save_part(client, sketch_part("skonly"))
    save_part(client, plate("plate_a"))
    a = asm([dict(comp("c1", "S", (10, 0, 5)), source={"type": "part", "name": "skonly"}), comp("c2", "P")])
    j = ok(client.post("/api/assembly/sketches", json={"assembly": a}))
    assert [c["id"] for c in j["components"]] == ["c1"]
    sk = j["components"][0]["sketches"]
    assert len(sk) == 1 and len(sk[0]["lines"]) == 4 and len(sk[0]["points"]) == 4
    assert sorted(map(tuple, sk[0]["points"])) == [(10, 0, 5), (10, 80, 5), (210, 0, 5), (210, 80, 5)]


def test_assembly_centre_datums(client):
    """Centre planes and axes through the bounding box centre (plate 100 x 50 x 20 from the origin: centre
    (50, 25, 10)); two plates mated centre plane XY to centre plane XY end with their mid-planes at one height."""
    save_part(client, plate("plate_a"))
    a = asm([comp("c1", "A", fixed=True), comp("c2", "B", (0, 0, 40))])
    j = ok(client.post("/api/assembly/build", json={"assembly": a, "have": []}))
    ds = j["components"][0]["datums"]
    assert ds["cplane:XY"]["c"] == pytest.approx([50, 25, 10]) and ds["cplane:XY"]["name"] == "Centre plane XY"
    assert ds["caxis:Z"]["p"] == pytest.approx([50, 25, 10]) and ds["caxis:Z"]["n"] == [0, 0, 1]
    a["mates"] = [{"id": "m1", "type": "coincident", "flip": True, "a": {"comp": "c2", "datum": "cplane:XY"}, "b": {"comp": "c1", "datum": "cplane:XY"}}]
    j = ok(client.post("/api/assembly/solve", json={"assembly": a}))
    assert j["residual"] < 1e-6 and j["placements"]["c2"]["pos"][2] == pytest.approx(0, abs=1e-6)


def test_measure_assembly_and_part(client):
    """Two plates 40 mm apart along Z: top face of A to bottom face of B 20 mm (min distance and plane distance),
    the hole cylinders: same axis, Ø 20; one face alone: area; a reference plane; the part: face and plane XY."""
    save_part(client, plate("plate_a"))
    a = asm([comp("c1", "A", fixed=True), comp("c2", "B", (0, 0, 40))])
    j = ok(client.post("/api/assembly/build", json={"assembly": a, "have": []}))
    refs = j["components"][0]["refs"]
    top = next(i for i, r in enumerate(refs) if r and r["kind"] == "plane" and r["n"][2] > 0.9)
    bot = next(i for i, r in enumerate(refs) if r and r["kind"] == "plane" and r["n"][2] < -0.9)
    cyl = next(i for i, r in enumerate(refs) if r and r["kind"] == "cylinder")
    rows = lambda r: dict((k, v) for k, v in r["rows"])
    r = ok(client.post("/api/assembly/measure", json={"assembly": a, "items": [{"comp": "c1", "face": top}, {"comp": "c2", "face": bot}]}))
    assert rows(r)["Minimum distance"] == "20.0000 mm" and rows(r)["Distance between the planes"] == "20.0000 mm"
    assert r["points"][0][2] == pytest.approx(20) and r["points"][1][2] == pytest.approx(40)
    r = ok(client.post("/api/assembly/measure", json={"assembly": a, "items": [{"comp": "c1", "face": cyl}, {"comp": "c2", "face": cyl}]}))
    assert rows(r)["Distance between the axes"] == "0.0000 mm" and rows(r)["Diameters"] == "Ø 20.0000 mm, Ø 20.0000 mm"
    r = ok(client.post("/api/assembly/measure", json={"assembly": a, "items": [{"comp": "c1", "face": top}]}))
    assert rows(r)["Area"] == "%.4f mm^2" % (100 * 50 - math.pi * 100)
    r = ok(client.post("/api/assembly/measure", json={"assembly": a, "items": [{"comp": "c2", "datum": "cplane:XY"}, {"comp": "c1", "face": top}]}))
    assert rows(r)["Distance between the planes"] == "30.0000 mm"
    r = ok(client.post("/api/part/measure", json={"part": plate("plate_a"), "items": [{"face": top}, {"base": "XY"}]}))
    assert rows(r)["Distance between the planes"] == "20.0000 mm" and rows(r)["Minimum distance"] == "20.0000 mm"


def test_assembly_drawing_parts_list_toggle(client):
    """The parts list of an assembly drawing follows the drawing layout ("parts_list"); default from Make drawing."""
    save_part(client, plate("plate_a"))
    a = dict(asm([comp("c1", "A", fixed=True), comp("c2", "B", (0, 0, 40))]), uid="pltest")
    j = ok(client.post("/api/assembly/to_drawings", json={"assembly": a, "parts_list": True}))
    f = j["files"][0]
    sel = [{"file_id": f["file_id"], "part_ids": [p["id"] for p in f["parts"]]}]
    req = {"selection": sel, "settings": {"sheet": "A3", "scale": "auto", "mode": "document"}}
    d = ok(client.post("/api/preview", json=req))["drawings"][0]
    assert d["has_parts_list"] and d["parts_list_shown"]
    ok(client.put("/api/layout/asm_pltest", json={"parts_list": False}))
    d2 = ok(client.post("/api/preview", json=req))["drawings"][0]
    assert d2["has_parts_list"] and not d2["parts_list_shown"]
    assert ok(client.get("/api/layout/asm_pltest"))["parts_list"] is False
    assert len(d2["svg"]) < len(d["svg"])


def test_parallel_saves_of_one_file(web):
    """Parallel PUTs of the same annotations, layout, part and assembly (the server answers requests in threads):
    every request succeeds and the file holds one of the written versions."""
    import threading
    errs = []

    def worker(k):
        c = web.app.test_client()
        for i in range(6):
            for url, body in (("/api/annotations/par_ann", [{"id": "n", "type": "note", "text": "T%d_%d" % (k, i)}]),
                              ("/api/part/file/par_part", {"name": "par_part", "version": 2, "features": []}),
                              ("/api/assembly/file/par_asm", {"name": "par_asm", "components": [], "next": 1})):
                r = c.put(url, json=body)
                if r.status_code != 200:
                    errs.append((url, r.status_code))
    ts = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errs, errs[:3]
    c = web.app.test_client()
    assert c.get("/api/annotations/par_ann").get_json()[0]["text"].startswith("T")


def test_config_split_local_settings(web, tmp_path, monkeypatch):
    """Settings of this PC (projects folder, open project, explicit, browser, ccx path) go to config.local.json; the
    other settings stay in config.json. An older config.json with them is split at start."""
    import json
    cp, lp = tmp_path / "config.json", tmp_path / "config.local.json"
    cp.write_text(json.dumps({"sheet": "A3", "projects_root": "C:\\\\P", "current_project": "X", "explicit": {"ssh_host": "h"}}))
    monkeypatch.setattr(web, "CONFIG_PATH", str(cp))
    monkeypatch.setattr(web, "LOCAL_PATH", str(lp))
    web._split_config()
    assert json.loads(cp.read_text()) == {"sheet": "A3"}
    assert json.loads(lp.read_text()) == {"projects_root": "C:\\\\P", "current_project": "X", "explicit": {"ssh_host": "h"}}
    cfg = web.load_config()
    assert cfg["sheet"] == "A3" and cfg["current_project"] == "X"
    cfg.update(browser="edge", sheet="A2")
    web.save_config(cfg)
    assert json.loads(cp.read_text()) == {"sheet": "A2"}
    assert json.loads(lp.read_text())["browser"] == "edge"


def test_part_refs_earlier_sketches(client):
    """Reference geometry of a sketch in a part with no solid: the curves of an earlier sketch on XY appear as
    projected lines (kind proj) in a sketch on XY and on XZ (projected along y; the edges along y are left out)."""
    rect = [{"id": "e%d" % i, "t": "line", "layer": "0", "x1": a, "y1": b, "x2": c, "y2": d}
            for i, (a, b, c, d) in enumerate([(0, 0, 40, 0), (40, 0, 40, 20), (40, 20, 0, 20), (0, 20, 0, 0)])]
    p = {"name": "t", "version": 2, "features": [
        {"id": "s1", "name": "Sketch 1", "type": "sketch", "plane": "XY", "offset": 0, "sketch": {"entities": rect}},
        {"id": "s2", "name": "Sketch 2", "type": "sketch", "plane": "XY", "offset": 5, "sketch": {"entities": []}},
        {"id": "s3", "name": "Sketch 3", "type": "sketch", "plane": "XZ", "offset": 0, "sketch": {"entities": []}}]}
    r = client.post("/api/part/refs", json={"part": p, "index": 1, "path": False, "section": None})
    lines = [x for x in r.get_json() if x.get("kind") == "proj" and x["t"] == "line"]
    ends = sorted((round(x["x1"], 6), round(x["y1"], 6)) for x in lines)
    assert ends == [(0, 0), (0, 20), (40, 0), (40, 20)], ends
    r = client.post("/api/part/refs", json={"part": p, "index": 2, "path": False, "section": None})
    lines = [x for x in r.get_json() if x.get("kind") == "proj" and x["t"] == "line"]
    assert len(lines) == 2 and all(abs(abs(x["x2"] - x["x1"]) - 40) < 1e-6 for x in lines), lines
    # a sketch used by an extrude is not listed (the solid is)
    p["features"].insert(1, {"id": "f1", "name": "Extrude 1", "type": "extrude", "sketch_ref": "s1", "depth": 3})
    r = client.post("/api/part/refs", json={"part": p, "index": 2, "path": False, "section": None})
    assert r.status_code == 200


def test_sketch_loops(client):
    """Closed profiles and open ends: a triangle, a circle and a single line (two open ends)."""
    sk = {"entities": [{"t": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0}, {"t": "line", "x1": 10, "y1": 0, "x2": 10, "y2": 5},
                       {"t": "line", "x1": 10, "y1": 5, "x2": 0, "y2": 0}, {"t": "line", "x1": 20, "y1": 0, "x2": 30, "y2": 0},
                       {"t": "circle", "cx": 50, "cy": 0, "r": 3}]}
    j = ok(client.post("/api/sketch/loops", json={"sketch": sk}))
    assert len(j["loops"]) == 1 and len(j["loops"][0]) == 3
    assert j["circles"] == [[50.0, 0.0, 3.0]] and sorted(j["open"]) == [[20.0, 0.0], [30.0, 0.0]]


def test_document_move_and_copy_to_project(client, web):
    """Move an assembly with the parts it uses to another project (versions, annotations and layout go along; a part
    still used by an assembly that stays is copied); copy a part; a name taken in the target project is refused."""
    ok(client.post("/api/projects", json={"name": "other_pj", "description": "", "open": False}))
    pp = plate("mv_part")
    pp["uid"] = "mvuid000001"
    save_part(client, pp)
    save_part(client, plate("mv_shared"))
    ok(client.post("/api/project/doc", json={"op": "snapshot", "type": "part", "name": "mv_part", "note": "v1"}))
    comp = lambda cid, part: {"id": cid, "name": cid, "source": {"type": "part", "name": part}, "pos": [0, 0, 0], "rot": [0, 0, 0]}
    ok(client.put("/api/assembly/file/mv_asm", json={"name": "mv_asm", "components": [comp("c1", "mv_part"), comp("c2", "mv_shared")], "next": 3}))
    ok(client.put("/api/assembly/file/stay_asm", json={"name": "stay_asm", "components": [comp("c1", "mv_shared")], "next": 2}))
    src = project_dir(web)
    uid = json.load(open(os.path.join(src, "work", "mv_part.part.json"))).get("uid") or "mvuid000001"
    with open(os.path.join(src, "work", "annotations", uid + ".json"), "w") as f:
        json.dump([{"type": "note", "text": "x"}], f)
    r = ok(client.post("/api/project/doc", json={"op": "move", "type": "assembly", "name": "mv_asm", "project": "other_pj", "with_uses": True}))
    assert sorted((d["type"], d["name"], d["mode"]) for d in r["done"]) == [("assembly", "mv_asm", "move"), ("part", "mv_part", "move"), ("part", "mv_shared", "copy")]
    dst = web.PROJECTS.project_dir("other_pj")
    for fn in ("mv_asm.asm.json", "mv_part.part.json", "mv_shared.part.json"):
        assert os.path.isfile(os.path.join(dst, "work", fn)), fn
    assert not os.path.exists(os.path.join(src, "work", "mv_asm.asm.json")) and not os.path.exists(os.path.join(src, "work", "mv_part.part.json"))
    assert os.path.isfile(os.path.join(src, "work", "mv_shared.part.json"))
    assert os.path.isfile(os.path.join(dst, "versions", "mv_part.part.v1.json"))
    assert os.path.isfile(os.path.join(dst, "work", "annotations", uid + ".json"))
    assert json.load(open(os.path.join(dst, "project.json")))["docs"]["part:mv_part"]["version"] == 1
    # copy: the source stays; a second copy is refused (name taken)
    r = ok(client.post("/api/project/doc", json={"op": "copy_to", "type": "assembly", "name": "stay_asm", "project": "other_pj"}))
    assert r["done"] == [{"type": "assembly", "name": "stay_asm", "mode": "copy"}]
    assert os.path.isfile(os.path.join(src, "work", "stay_asm.asm.json"))
    bad = client.post("/api/project/doc", json={"op": "copy_to", "type": "assembly", "name": "stay_asm", "project": "other_pj"})
    assert bad.status_code >= 400 and "exists in project other_pj" in bad.get_data(as_text=True)
