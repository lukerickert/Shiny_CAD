# -*- coding: utf-8 -*-
"""CAM package (drawgen/cam): tool bits and swept solids, the job document (migration, heights, levels, moves),
the operations on a test part (face, pocket, drilling, undercut, profile with tag and ramp dressups, helix, slot,
engrave, vcarve, deburr, adaptive, 3D pocket, 3D surface, waterline, copy, array, supplemental), the stock cut
by the tool, the sanity check, the template, the G-code of both posts and the server routes."""
import copy
import math

import pytest

from conftest import part_rec, rect

H = 6.0                                  # undercut height mm
U = H / math.tan(math.radians(60))       # undercut depth mm of a 60 deg dovetail
FILL = 0.5 * U * H * 100.0               # volume mm^3 of the undercut of a 100 mm rail

TOOL = {"id": "T2", "name": "Dovetail 60", "shape": "dovetail", "d": 16.0, "angle": 60.0, "height": 6.5, "neck": 8.0,
        "neck_length": 10.0, "shank": 10.0, "shank_length": 30.0, "flutes": 6, "feed": 300, "plunge": 100, "rpm": 6000}
END_MILL = {"id": "T1", "name": "End mill 6", "shape": "endmill", "d": 6.0, "height": 18.0, "neck": 6.0, "neck_length": 0.0,
            "shank": 6.0, "shank_length": 30.0, "feed": 800, "plunge": 200, "rpm": 12000}
DRILL = {"id": "T3", "name": "Drill 6", "shape": "drill", "d": 6.0, "angle": 118.0, "height": 30.0, "neck": 6.0, "neck_length": 0.0,
         "shank": 6.0, "shank_length": 20.0, "feed": 150, "plunge": 150, "rpm": 3000}
BALL = {"id": "T4", "name": "Ball 6", "shape": "ballend", "d": 6.0, "height": 12.0, "neck": 6.0, "neck_length": 0.0,
        "shank": 6.0, "shank_length": 30.0, "feed": 600, "plunge": 200, "rpm": 12000}
VBIT = {"id": "T5", "name": "V bit 90", "shape": "vbit", "d": 6.0, "angle": 90.0, "tip": 0.2, "height": 3.0, "neck": 6.0,
        "neck_length": 0.0, "shank": 6.0, "shank_length": 30.0, "feed": 400, "plunge": 150, "rpm": 15000}
SMALL = {"id": "T6", "name": "End mill 3", "shape": "endmill", "d": 3.0, "height": 10.0, "neck": 3.0, "neck_length": 0.0,
         "shank": 6.0, "shank_length": 30.0, "feed": 600, "plunge": 150, "rpm": 15000}
BITS = [END_MILL, TOOL, DRILL, BALL, VBIT, SMALL]


def controllers():
    from drawgen.cam import job
    return [job.controller_defaults(b, i + 1) for i, b in enumerate(BITS)]


def rail_shape(length=100.0, wall=False):
    """Plate 100 x 60 x 10 mm with a rail 16 mm high along X at y = 0..12 whose inner face is a 60 deg undercut;
    wall: a block across the end at x = 100 (the undercut is closed there)."""
    from build123d import Box, Location, Vector, Face, Wire, Solid
    plate = Box(100, 60, 10).moved(Location(Vector(50, 30, 5)))
    tri = Face(Wire.make_polygon([Vector(0, 0, 10), Vector(0, 12, 10), Vector(0, 12 + U, 10 + H), Vector(0, 0, 10 + H)], close=True))
    sh = plate.fuse(Solid.extrude(tri, Vector(length, 0, 0)))
    if wall:
        sh = sh.fuse(Box(10, 60, 20).moved(Location(Vector(105, 30, 10))))
    return sh.clean()


def rail_part(name="rail"):
    """The same rail as a part record: the plate extruded on XY, the rail profile extruded on YZ."""
    prof = [(0, 10), (12, 10), (12 + U, 10 + H), (0, 10 + H)]
    lines = [{"id": 1 + i, "t": "line", "x1": prof[i][0], "y1": prof[i][1], "x2": prof[(i + 1) % 4][0], "y2": prof[(i + 1) % 4][1], "layer": "0"}
             for i in range(4)]
    return part_rec(name, [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": rect(100, 60)}, "depth": 10},
                           {"id": "f2", "name": "Extrude 2", "type": "extrude", "plane": "YZ", "offset": 0, "sketch": {"entities": lines}, "depth": 100}])


def job_shape():
    """The rail plate with a 30 x 20 x 4 mm pocket holding a 6 x 6 mm island and a 6 mm through hole."""
    from build123d import Box, Location, Vector, Cylinder
    sh = rail_shape()
    pocket = Box(30, 20, 4).moved(Location(Vector(75, 38, 8)))
    island = Box(6, 6, 4).moved(Location(Vector(75, 38, 8)))
    sh = sh.cut(pocket.cut(island))
    return sh.cut(Cylinder(3, 10).moved(Location(Vector(30, 45, 5)))).clean()


def job_part(name="job"):
    prof = [(0, 10), (12, 10), (12 + U, 10 + H), (0, 10 + H)]
    lines = [{"id": 1 + i, "t": "line", "x1": prof[i][0], "y1": prof[i][1], "x2": prof[(i + 1) % 4][0], "y2": prof[(i + 1) % 4][1], "layer": "0"}
             for i in range(4)]
    return part_rec(name, [
        {"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": rect(100, 60)}, "depth": 10},
        {"id": "f2", "name": "Extrude 2", "type": "extrude", "plane": "YZ", "offset": 0, "sketch": {"entities": lines}, "depth": 100},
        {"id": "f3", "name": "Cut 1", "type": "cut", "plane": "XY", "offset": 10, "depth": 4, "reverse": True,
         "sketch": {"entities": rect(30, 20, 60, 28, 1) + rect(6, 6, 72, 35, 11)}},
        {"id": "f4", "name": "Hole 1", "type": "hole", "plane": "XY", "offset": 10, "dia": 6, "depth": None,
         "sketch": {"entities": [{"id": 1, "t": "point", "x": 30, "y": 45, "layer": "0"}]}}])


def _kind(fc):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    return BRepAdaptor_Surface(fc.wrapped).GetType()


def face_key_where(shape, pred):
    from drawgen import part as P
    for fc in shape.faces():
        if pred(fc):
            return P.face_key(fc)
    raise AssertionError("no face")


def keys_of(shape):
    """Face keys of the test part: the plate top, the pocket floor, the hole and the undercut face."""
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from drawgen import cam, part as P
    return {"top": face_key_where(shape, lambda f: _kind(f) == GeomAbs_Plane and abs(f.center().Z - 10) < 1e-6 and f.area > 1000),
            "floor": face_key_where(shape, lambda f: _kind(f) == GeomAbs_Plane and abs(f.center().Z - 6) < 1e-6),
            "hole": face_key_where(shape, lambda f: _kind(f) == GeomAbs_Cylinder and abs(f.center().Y - 45) < 1.0 and abs(f.center().X - 30) < 4),
            "uc": P.face_key(cam.undercut_faces(shape)[0][0])}


def job_doc(shape, ops=None, **kw):
    """A job on the test part with the six operations of the basic workflow (or the given operations)."""
    k = keys_of(shape)
    doc = {"name": "job", "source": {"type": "part", "name": "job"}, "stock": {"kind": "offsets", "xneg": 2, "xpos": 2, "yneg": 2, "ypos": 2, "zneg": 0, "zpos": 2},
           "origin": {"xy": "stock_min", "z": "stock_top"}, "post": "estlcam", "tools": controllers(), "next": 20,
           "operations": ops if ops is not None else [
               {"id": "o1", "name": "Face", "type": "face", "tc": "TC1", "pattern": "zigzag", "stepover_pct": 60, "step_down": 1},
               {"id": "o2", "name": "Clear", "type": "pocket", "tc": "TC1", "faces": [k["top"]], "pattern": "offset", "stepover_pct": 40, "extra_offset": 0.2, "finish": True, "entry": "helix"},
               {"id": "o3", "name": "Pocket", "type": "pocket", "tc": "TC1", "faces": [k["floor"]], "pattern": "zigzag_offset", "angle": 30, "stepover_pct": 40, "extra_offset": 0.2, "finish": True},
               {"id": "o4", "name": "Drill", "type": "drilling", "tc": "TC3", "faces": [k["hole"]], "peck": 3, "dwell": 0.5},
               {"id": "o5", "name": "Undercut", "type": "undercut", "tc": "TC2", "faces": [k["uc"]], "stepover": 1.5, "allowance": 0.2, "runout": 2},
               {"id": "o6", "name": "Profile", "type": "profile", "tc": "TC1", "step_down": 3, "extra": 0.2,
                "dressups": [{"type": "ramp", "angle": 3, "method": "ramp1"}, {"type": "tag", "count": 3, "width": 6, "height": 1}]}]}
    doc.update(kw)
    return doc


def run_one(shape, op, **kw):
    from drawgen import cam
    doc = job_doc(shape, ops=[op], **kw)
    return cam.run(doc, shape, BITS)["operations"][0]


# --------------------------------------------------------------------------- tool bits

def test_tool_profile_and_solids():
    from drawgen import cam
    from drawgen.cam import tools as TB
    cut, body = cam.tool_profile(TOOL)
    assert cut[0] == (0.0, 0.0) and cut[1] == (8.0, 0.0)
    r_top = 8.0 - 6.5 / math.tan(math.radians(60))
    assert abs(cut[2][0] - r_top) < 1e-9 and cut[2][1] == 6.5
    assert body[-1][1] == 6.5 + 10 + 30
    frustum = math.pi * 6.5 / 3 * (8.0 ** 2 + 8.0 * r_top + r_top ** 2)
    assert abs(cam.tool_solid(TOOL, (0, 0, 0), "cut").volume - frustum) < 1e-3
    assert abs(cam.tool_solid(TOOL, (0, 0, 0), "body").volume - math.pi * (4.0 ** 2 * 10 + 5.0 ** 2 * 30)) < 1e-3
    with pytest.raises(ValueError):
        cam.check_tool(dict(TOOL, height=20))
    with pytest.raises(ValueError):
        cam.check_tool(dict(TOOL, angle=5))
    em = cam.tool_solid(END_MILL, (0, 0, 0), "cut")
    assert abs(em.volume - math.pi * 9 * 18) < 1e-3
    dr = cam.tool_solid(dict(DRILL, d=5, height=30), (0, 0, 0), "cut")
    tip = 2.5 / math.tan(math.radians(59))
    assert abs(dr.volume - math.pi * 2.5 ** 2 * (30 + tip / 3)) < 1e-3
    # the older "type" key of a bit is normalized to "shape"
    old = cam.normalize_tool({"id": "T9", "type": "ball", "d": 6, "height": 10})
    assert old["shape"] == "ballend" and "type" not in old
    assert TB.shape_of({"type": "endmill"}) == "endmill"
    # the bottom offset: a ball end mill, a V bit, a flat end mill
    assert abs(TB.bottom_offset(BALL, 0.0)) < 1e-9 and abs(TB.bottom_offset(BALL, 3.0) - 3.0) < 1e-9 and TB.bottom_offset(BALL, 3.5) is None
    assert abs(TB.bottom_offset(VBIT, 1.1) - 1.0) < 1e-9 and TB.bottom_offset(END_MILL, 2.9) == 0.0
    assert all(s in cam.SHAPE_NAMES for s in cam.SHAPES)


def test_swept_solids():
    from drawgen import cam
    cut, body = cam.tool_profile(TOOL)
    r_top = cut[2][0]
    frustum = math.pi * 6.5 / 3 * (8.0 ** 2 + 8.0 * r_top + r_top ** 2)
    sw = cam.sweep_line(TOOL, (0, 0, 0), (50, 0, 0), "cut")
    sect = (8.0 + r_top) * 6.5
    assert abs(sw.volume - (sect * 50 + frustum)) < 1e-2
    sw2 = cam.sweep_line(TOOL, (0, 0, 0), (0, 0, 10), "cut")
    assert abs(sw2.volume - (frustum + math.pi * 8.0 ** 2 * 10)) < 0.5


# --------------------------------------------------------------------------- document

def test_migrate_old_document():
    from drawgen import cam
    old = {"name": "x", "source": {"type": "part", "name": "p"}, "stock": {"kind": "box", "top": 2, "sides": 1, "bottom": 0}, "clearance": 7,
           "operations": [{"id": "o1", "name": "Drill 1", "type": "drill", "tool": "T3", "faces": [], "peck": 3, "suppressed": True},
                          {"id": "o2", "name": "Profile 1", "type": "profile", "tool": "T1", "tabs": 3, "tab_width": 6, "tab_height": 1, "ramp_angle": 3}]}
    d = cam.migrate(old)
    assert d["stock"] == {"kind": "offsets", "xneg": 1.0, "xpos": 1.0, "yneg": 1.0, "ypos": 1.0, "zneg": 0.0, "zpos": 2.0}
    assert d["setup"]["clearance_offset"] == 7.0 and d["setup"]["step_down"] == 2.0 and d["post"] == "estlcam"
    assert [t["bit"] for t in d["tools"]] == ["T3", "T1"] and d["tools"][0]["id"] == "TC1" and d["tools"][1]["number"] == 2
    o1, o2 = d["operations"]
    assert o1["type"] == "drilling" and o1["tc"] == "TC1" and o1["active"] is False and "suppressed" not in o1 and "tool" not in o1
    assert o2["tc"] == "TC2" and [x["type"] for x in o2["dressups"]] == ["tag", "ramp"] and o2["dressups"][0]["count"] == 3 and "tabs" not in o2
    assert all(k in o2 for k in ("clearance_height", "safe_height", "start_depth", "final_depth", "step_down", "finish_depth"))
    # migrating twice changes nothing
    assert cam.migrate(d) == d


def test_stock_origin_heights_levels_moves():
    from drawgen import cam
    from drawgen.cam import job as J
    sh = rail_shape()
    st = cam.stock_solid({"stock": {"kind": "part_filled"}}, sh)
    assert abs(st.volume - sh.volume - FILL) < 1e-3
    bx = cam.stock_solid({"stock": {"kind": "offsets", "xneg": 1, "xpos": 1, "yneg": 1, "ypos": 1, "zneg": 0, "zpos": 2}}, sh)
    assert abs(bx.volume - 102 * 62 * 18) < 1e-2
    bb = cam._bbox(bx)
    assert cam.origin_of({"origin": {"xy": "stock_min", "z": "stock_top"}}, bb) == [-1.0, -1.0, 18.0]
    assert cam.origin_of({"origin": {"xy": "stock_centre", "z": "stock_bottom"}}, bb) == [50.0, 30.0, 0.0]
    assert cam.origin_of({"origin": {"xy": "part", "z": "part"}}, bb) == [0.0, 0.0, 0.0]
    ex = cam.stock_solid({"stock": {"kind": "box", "xmin": -5, "ymin": -5, "zmin": 0, "xmax": 105, "ymax": 65, "zmax": 20}}, sh)
    assert abs(ex.volume - 110 * 70 * 20) < 1e-6
    with pytest.raises(ValueError):
        cam.stock_solid({"stock": {"kind": "box", "xmin": 10, "xmax": 5}}, sh)
    doc = cam.migrate({"setup": {"clearance_offset": 5, "safe_offset": 3, "step_down": 2, "finish_depth": 0.5}})
    h = cam.heights({"start_depth": None, "final_depth": None, "step_down": None, "finish_depth": None, "clearance_height": None, "safe_height": None}, doc, bb, cam._bbox(sh))
    assert h == {"clearance": 23.0, "safe": 21.0, "start": 18.0, "final": 0.0, "step": 2.0, "finish": 0.5}
    h2 = cam.heights({"start_depth": 10, "final_depth": 4, "step_down": 3, "finish_depth": 0, "clearance_height": 11, "safe_height": 12}, doc, bb, cam._bbox(sh))
    assert h2["clearance"] == 12.0 and h2["safe"] == 12.0 and h2["start"] == 10.0          # the clearance at least the safe height
    assert cam.levels({"start": 16, "final": 10, "step": 2, "finish": 0}) == [14, 12, 10]
    assert cam.levels({"start": 16, "final": 10, "step": 2, "finish": 0.5}) == [14, 12, 10.5, 10]
    assert cam.levels({"start": 10, "final": 10, "step": 2, "finish": 0}) == [] and cam.levels({"start": 10.5, "final": 10, "step": 2, "finish": 0}) == [10]
    lv = cam.levels({"start": 16.0000001, "final": 6, "step": 2, "finish": 0})
    assert len(lv) == 5 and lv[-1] == 6
    mv = J.Moves({"clearance": 20.0, "safe": 18.0, "start": 16.0, "final": 10.0, "step": 2.0, "finish": 0.0}, 800, 200)
    mv.rapid_to(0, 0)
    mv.to_safe()
    mv.plunge_to(10)
    mv.feed_to(10, 0, 10)
    mv.arc_to(10, 10, 10, 10, 5, False)
    mv.retract()
    ks = [m["k"] for m in mv.moves]
    assert ks == ["rapid", "rapid", "plunge", "feed", "arc", "rapid"]
    assert mv.moves[-1]["p"][2] == 20.0 and mv.moves[1]["p"][2] == 18.0 and mv.moves[2]["f"] == 200 and mv.moves[3]["f"] == 800
    cut, rapid = J.path_length(mv.moves)
    assert abs(cut - (8 + 10 + math.pi * 5)) < 0.1 and rapid > 0           # the plunge from the safe height counts as a cut
    assert J.cycle_time(mv.moves) > 0
    groups = J._level_groups(mv.moves)
    assert set(groups) == {10.0}
    from drawgen.cam import geom as G
    reg = G.level_region(groups[10.0], 3.0)
    assert abs(reg.area - (10 * 6 + math.pi * 9 + math.pi * 5 * 6)) < 3.0
    pts = G.arc_pts((10, 0, 0), (10, 10, 0), (10, 5), False, 4)
    assert len(pts) == 4 and abs(pts[-1][0] - 10) < 1e-9 and abs(pts[-1][1] - 10) < 1e-9 and abs(pts[1][0] - 15) < 1e-9


def test_geometry_helpers():
    from drawgen.cam import geom as G
    from OCP.GeomAbs import GeomAbs_Plane
    sh = job_shape()
    sec = G.section_polys(sh, 7.0)
    polys = G.polys(sec)
    assert len(polys) == 2 and abs(sec.area - (100 * 60 - 30 * 20 + 36 - math.pi * 9)) < 0.2
    top = [f for f in sh.faces() if _kind(f) == GeomAbs_Plane and abs(f.center().Z - 10) < 1e-6 and f.area > 1000][0]
    info = G.floor_info(sh, top)
    assert len(info["poly"].interiors) == 0 and abs(info["poly"].area - (100 * 48)) < 1e-6 and len(info["open"]) == 3
    floor = [f for f in sh.faces() if _kind(f) == GeomAbs_Plane and abs(f.center().Z - 6) < 1e-6][0]
    info = G.floor_info(sh, floor)
    assert len(info["poly"].interiors) == 1 and abs(info["poly"].area - (600 - 36)) < 1e-6 and info["open"] == []
    with pytest.raises(ValueError):
        G.floor_info(sh, [f for f in sh.faces() if abs(f.center().Z) < 1e-6][0])
    kinds = G.face_kinds(sh, [])
    assert kinds.count("floor") >= 2 and "hole" in kinds and "wall" in kinds
    assert abs(G.top_z_at(sh, 20, 30) - 10.0) < 1e-6 and abs(G.top_z_at(sh, 20, 5) - 16.0) < 1e-6 and G.top_z_at(sh, -50, -50) is None
    hm = G.HeightMap.of_shape(sh, 1.0, margin=1.0)
    assert abs(hm.at(20, 30) - 10.0) < 1e-6 and abs(hm.at(20, 5) - 16.0) < 1e-6 and abs(hm.at(75, 38) - 10.0) < 1e-6 and abs(hm.at(70, 38) - 6.0) < 1e-6
    tm = hm.tool_map(END_MILL)
    assert abs(tm.at(70, 38) - 10.0) < 1e-6                 # 3 mm from the island wall: the end mill stands on the island
    reg = tm.region(8.0)
    assert not reg.is_empty and reg.area < 100 * 60           # where the end mill may stand at Z 8: the plate top is above
    m = hm.mesh(bounds=(0, 0, 20, 20))
    assert m["vertices"] and m["triangles"]
    g, width = G.text_polygons("AB", 8.0, "", 10.0, 20.0)
    assert 8.0 < width < 20.0 and len(G.polys(g)) == 2 and g.bounds[0] >= 10.0 - 1e-6 and abs(g.bounds[1] - 20.0) < 0.5


# --------------------------------------------------------------------------- operations

def test_undercut_face_info_and_passes():
    from drawgen import cam
    sh = rail_shape()
    faces = cam.undercut_faces(sh)
    assert len(faces) == 1
    fc, info = faces[0]
    assert abs(info["angle"] - 60.0) < 1e-6 and abs(info["height"] - H) < 1e-9 and abs(info["depth"] - U) < 1e-9
    assert abs(cam.undercut_fill(info).volume - FILL) < 1e-6
    offs = cam.undercut_passes(cam.undercut_info(fc), TOOL, 1.5, 0.2)
    assert offs[-1] == 0.0 and abs(offs[-2] - 0.2 / math.sin(math.radians(60))) < 1e-9
    assert cam.undercut_passes(info, TOOL, 100.0, 0.0) == [0.0]
    assert cam.undercut_faces(cam.stock_solid({"stock": {"kind": "offsets"}}, sh)) == []


def test_undercut_operation():
    from drawgen import cam, part as P
    sh = rail_shape()
    uc = P.face_key(cam.undercut_faces(sh)[0][0])
    tcs = controllers()
    doc = {"name": "t", "stock": {"kind": "part_filled"}, "tools": tcs,
           "operations": [{"id": "o1", "name": "Undercut 1", "type": "undercut", "tc": "TC2", "faces": [uc], "stepover": 1.5, "allowance": 0.2, "runout": 2}]}
    res = cam.run(doc, sh, BITS)
    op = res["operations"][0]
    assert op["ok"], op["errors"]
    assert abs(op["removed_mm3"] - FILL) < 1e-3 and op["gouge_mm3"] < 1e-6 and op["remaining_mm3"] < 1e-6
    assert op["levels"] and all(m["k"] in ("rapid", "feed", "plunge") for m in op["moves"])
    left, gone, _ = cam.remaining(res["stock"], sh)
    assert left < 1e-3 and gone < 1e-3
    # an older document (tool bit ids) runs after migration
    old = {"name": "t", "stock": {"kind": "part_filled"}, "operations": [{"id": "o1", "name": "U", "type": "undercut", "tool": "T2", "faces": [uc], "stepover": 2}]}
    assert cam.run(old, sh, BITS)["operations"][0]["ok"]
    # refusals: an end mill, a closed undercut, a cutter whose flank is lower than the undercut
    bad = cam.run(dict(doc, operations=[dict(doc["operations"][0], tc="TC1")]), sh, BITS)["operations"][0]
    assert not bad["ok"] and "dovetail" in bad["errors"][0]
    shw = rail_shape(wall=True)
    ucw = P.face_key(cam.undercut_faces(shw)[0][0])
    bad = cam.run(dict(doc, operations=[dict(doc["operations"][0], faces=[ucw])]), shw, BITS)["operations"][0]
    assert not bad["ok"] and "not open" in bad["errors"][0]
    low = [dict(TOOL, height=4.0)] + [b for b in BITS if b["id"] != "T2"]
    bad = cam.run(doc, sh, low)["operations"][0]
    assert not bad["ok"] and "height" in bad["errors"][0]


def test_job_basic_workflow():
    """Face, clear, pocket, drilling, undercut and profile with tag and ramp dressups on the test part: nothing of
    the part cut, nothing left but the allowance films and the tags."""
    from drawgen import cam
    sh = job_shape()
    doc = job_doc(sh)
    res = cam.run(doc, sh, BITS)
    ops = {o["name"]: o for o in res["operations"]}
    for o in res["operations"]:
        assert o["ok"], (o["name"], o["errors"])
        assert o["gouge_mm3"] < 0.05, o["name"]
    assert res["origin"] == [-2.0, -2.0, 18.0] and res["clearance_z"] == 23.0
    assert abs(ops["Face"]["removed_mm3"] - 104 * 64 * 2) < 0.5 and len(ops["Face"]["levels"]) == 2
    assert ops["Face"]["heights"]["start"] == 18.0 and ops["Face"]["heights"]["final"] == 16.0
    assert len(ops["Clear"]["levels"]) == 3 and abs(ops["Clear"]["remaining_mm3"] - FILL) < 2.0     # the undercut stays for the dovetail
    assert ops["Clear"]["heights"]["start"] == 16.0 and any(m["k"] == "arc" for m in ops["Clear"]["moves"])
    assert len(ops["Pocket"]["levels"]) == 2 and ops["Pocket"]["heights"]["start"] == 10.0            # starts at the cleared plate
    assert ops["Pocket"]["remaining_mm3"] < 40 and "plunge(s) between separate loops" in ops["Pocket"]["messages"][0]
    assert ops["Drill"]["levels"] and ops["Drill"]["heights"]["final"] < -1.0 and any(m.get("k") == "dwell" for m in ops["Drill"]["moves"])
    assert abs(ops["Undercut"]["removed_mm3"] - FILL) < 10.0
    assert "3 tag(s) 6 x 1 mm" in " ".join(ops["Profile"]["messages"]) and "plunge(s) replaced" in " ".join(ops["Profile"]["messages"])
    assert ops["Profile"]["heights"]["final"] == -0.2 and len(ops["Profile"]["levels"]) >= 6
    assert all(o["time_s"] > 0 and o["cut_mm"] > 0 for o in res["operations"])
    left, gone, _ = cam.remaining(res["stock"], sh)
    assert gone < 0.05 and 10 < left < 80
    # the record fields of the interface
    for o in res["operations"]:
        for k in ("id", "type", "name", "ok", "errors", "messages", "moves", "levels", "removed_mm3", "gouge_mm3", "remaining_mm3", "heights", "feed", "plunge", "rpm", "cut_mm", "rapid_mm", "time_s", "tool"):
            assert k in o, k
    # the cache: a second run with one more operation computes only that one
    cam.cache_clear()
    cam.run(doc, sh, BITS, shape_key="k")
    doc2 = copy.deepcopy(doc)
    doc2["operations"].append({"id": "o7", "name": "Comment", "type": "comment", "text": "end"})
    res2 = cam.run(doc2, sh, BITS, shape_key="k")
    assert len(res2["operations"]) == 7 and res2["operations"][-1]["moves"] == [{"k": "comment", "text": "end"}]
    cam.cache_clear()
    # an inactive operation is skipped
    doc3 = copy.deepcopy(doc)
    doc3["operations"][4]["active"] = False
    r3 = cam.run(doc3, sh, BITS)
    assert r3["operations"][4]["ok"] and r3["operations"][4]["messages"] == ["inactive"] and not r3["operations"][4]["moves"]


def test_ops_refusals_and_messages():
    from drawgen import cam
    sh = job_shape()
    doc = job_doc(sh)
    ops = {o["id"]: o for o in doc["operations"]}
    run1 = lambda op, bits=BITS, **kw: cam.run(dict(doc, operations=[op], **kw), sh, bits)["operations"][0]
    assert "Dovetail; pocket needs end mill" in run1(dict(ops["o3"], tc="TC2"))["errors"][0]
    assert "Drill; profile needs" in run1(dict(ops["o6"], tc="TC3"))["errors"][0]
    assert "drilling needs drill or end mill" in run1(dict(ops["o4"], tc="TC2"))["errors"][0]
    short = [dict(END_MILL, height=3.0)] + BITS[1:]
    o = run1(dict(ops["o6"], step_down=5), short)
    assert not o["ok"] and "deeper than the cutting height" in o["errors"][0]
    assert "no floor face" in run1(dict(ops["o3"], faces=[]))["errors"][0]
    assert "no hole face" in run1(dict(ops["o4"], faces=[]))["errors"][0]
    o = run1(ops["o1"], stock={"kind": "offsets", "xneg": 2, "xpos": 2, "yneg": 2, "ypos": 2, "zneg": 0, "zpos": 0})
    assert o["ok"] and "nothing to cut" in o["messages"][0] and not o["moves"]
    o = run1(dict(ops["o4"]), [END_MILL, TOOL, dict(DRILL, d=5.0), BALL, VBIT, SMALL])
    assert o["ok"] and any("diameter 6.00 mm, tool 5.00 mm" in m for m in o["messages"])
    o = run1(dict(ops["o3"], entry="plunge", finish=False, extra_offset=0.3))
    assert o["ok"] and not any(m["k"] == "arc" for m in o["moves"]) and o["remaining_mm3"] > 40
    o = run1({"id": "x", "name": "X", "type": "nosuch", "tc": "TC1"})
    assert not o["ok"] and "unknown operation type" in o["errors"][0]
    o = run1(dict(ops["o3"], tc="TC9"))
    assert not o["ok"] and "tool controller" in o["errors"][0]
    # the explicit depths of an operation
    o = run1(dict(ops["o3"], start_depth=9.0, final_depth=7.0, step_down=1.0))
    assert o["ok"] and o["heights"]["start"] == 9.0 and o["heights"]["final"] == 7.0 and [l["z"] for l in o["levels"]] == [8.0, 7.0]


def test_helix_slot_engrave_deburr():
    from drawgen import cam, part as P
    sh = job_shape()
    k = keys_of(sh)
    base = job_doc(sh)
    pre = [base["operations"][0], base["operations"][1]]            # the plate top cleared
    # helix in the hole with the 3 mm end mill
    doc = job_doc(sh, ops=pre + [{"id": "h", "name": "Helix", "type": "helix", "tc": "TC6", "faces": [k["hole"]], "stepover_pct": 50}])
    res = cam.run(doc, sh, BITS)
    o = res["operations"][2]
    assert o["ok"], o["errors"]
    assert any(m["k"] == "arc" for m in o["moves"]) and o["gouge_mm3"] < 0.05 and o["removed_mm3"] > 0
    big = run_one(sh, {"id": "h", "name": "Helix", "type": "helix", "tc": "TC1", "faces": [k["hole"]]})
    assert big["ok"] and "larger than the hole" in big["messages"][0] and not big["moves"]
    # a straight slot from two points on the plate top, 2 mm deep
    doc = job_doc(sh, ops=pre + [{"id": "s", "name": "Slot", "type": "slot", "tc": "TC6", "points": [[20, 30], [50, 30]], "final_depth": 8.0, "step_down": 1.0, "extend_start": 1}])
    o = cam.run(doc, sh, BITS)["operations"][2]
    assert o["ok"], o["errors"]
    assert abs(o["removed_mm3"] - (31 * 3 + math.pi * 2.25) * 2) < 20 and o["gouge_mm3"] > 100          # a slot cut into the part
    assert len(o["levels"]) == 2
    # a slot from the edge of the pocket floor
    top_edges = [e for e in sh.edges() if abs(e.center().Z - 10) < 1e-6 and abs(e.center().Y - 60) < 1e-6]
    doc = job_doc(sh, ops=pre + [{"id": "s", "name": "Slot", "type": "slot", "tc": "TC6", "edges": [P.edge_key(top_edges[0])], "final_depth": 9.0}])
    o = cam.run(doc, sh, BITS)["operations"][2]
    assert o["ok"], o["errors"]
    # engrave a text on the plate top with the V bit: the surface under the text is the plate top (Z 10)
    doc = job_doc(sh, ops=pre + [{"id": "e", "name": "Engrave", "type": "engrave", "tc": "TC5", "text": {"text": "AB", "size": 8, "x": 15, "y": 20}, "depth": 0.3}])
    o = cam.run(doc, sh, BITS)["operations"][2]
    assert o["ok"], o["errors"]
    assert o["heights"]["start"] == 10.0 and o["heights"]["final"] == 9.7 and o["gouge_mm3"] == 0.0 and o.get("engraved_mm3", 0) > 1.0
    assert "cut from the part" in " ".join(o["messages"])
    # engrave picked edges: the top edges of the island
    isl = [e for e in sh.edges() if abs(e.center().Z - 10) < 1e-6 and 72 - 1e-6 <= e.center().X <= 78 + 1e-6 and 35 - 1e-6 <= e.center().Y <= 41 + 1e-6]
    assert len(isl) == 4
    doc = job_doc(sh, ops=pre + [{"id": "e", "name": "Engrave", "type": "engrave", "tc": "TC5", "edges": [P.edge_key(e) for e in isl], "depth": 0.2}])
    o = cam.run(doc, sh, BITS)["operations"][2]
    assert o["ok"], o["errors"]
    assert "4 path(s)" in o["messages"][0]
    # deburr the island edges with the V bit
    doc = job_doc(sh, ops=pre + [{"id": "d", "name": "Deburr", "type": "deburr", "tc": "TC5", "edges": [P.edge_key(e) for e in isl], "width": 0.5, "extra_depth": 0.3}])
    o = cam.run(doc, sh, BITS)["operations"][2]
    assert o["ok"], o["errors"]
    assert o["moves"] and o.get("engraved_mm3", 0) > 0
    # no geometry: an error
    o = run_one(sh, {"id": "e", "name": "Engrave", "type": "engrave", "tc": "TC5"})
    assert not o["ok"] and "no edges, sketch or text" in o["errors"][0]


def test_vcarve_and_adaptive():
    from drawgen import cam
    sh = job_shape()
    k = keys_of(sh)
    base = job_doc(sh)
    pre = [base["operations"][0], base["operations"][1]]
    doc = job_doc(sh, ops=pre + [{"id": "v", "name": "Vcarve", "type": "vcarve", "tc": "TC5", "text": {"text": "V", "size": 8, "x": 40, "y": 20}}])
    o = cam.run(doc, sh, BITS)["operations"][2]
    assert o["ok"], o["errors"]
    assert o["heights"]["start"] == 10.0 and "centre-line path(s)" in o["messages"][0] and o.get("hm") and o["hm"]["gouge_mm3"] > 1.0
    assert min(m["p"][2] for m in o["moves"] if m.get("k") == "feed") > 10.0 - 2.9 - 1e-6
    assert "cut by the height map surface" in " ".join(o["messages"])
    bad = run_one(sh, {"id": "v", "name": "Vcarve", "type": "vcarve", "tc": "TC1", "text": {"text": "V", "size": 8, "x": 40, "y": 20}})
    assert not bad["ok"] and "v bit" in bad["errors"][0].lower()
    # adaptive clearing of the pocket with stock to leave
    doc = job_doc(sh, ops=pre + [{"id": "a", "name": "Adaptive", "type": "adaptive", "tc": "TC1", "faces": [k["floor"]], "stepover_pct": 20, "stock_to_leave": 0.3}])
    res = cam.run(doc, sh, BITS)
    o = res["operations"][2]
    assert o["ok"], o["errors"]
    assert o["gouge_mm3"] < 0.05 and 1800 < o["removed_mm3"] < 2250 and "clearing, 2 level(s)" in o["messages"][-1]
    left, gone, _ = cam.remaining(res["stock"], sh)
    assert gone < 0.05
    # adaptive profiling around the island
    doc = job_doc(sh, ops=pre + [{"id": "a", "name": "Adaptive", "type": "adaptive", "tc": "TC1", "faces": [k["floor"]], "mode": "profiling", "passes": 1}])
    o = cam.run(doc, sh, BITS)["operations"][2]
    assert o["ok"], o["errors"]
    assert o["gouge_mm3"] < 0.05 and o["moves"]
    from drawgen.cam import adaptive as A
    from shapely.geometry import box
    paths = A.spiral_paths(box(0, 0, 20, 10), 2.0)
    assert paths and sum(len(p) for p in paths) > 20


def test_3d_operations():
    from drawgen import cam
    sh = job_shape()
    k = keys_of(sh)
    base = job_doc(sh)
    pre = [base["operations"][0], base["operations"][1]]
    doc = job_doc(sh, ops=pre + [
        {"id": "w", "name": "Waterline", "type": "waterline", "tc": "TC1", "sample": 0.5, "step_down": 3, "boundary": "stock"},
        {"id": "p", "name": "Pocket3D", "type": "pocket3d", "tc": "TC4", "faces": [k["floor"]], "sample": 0.5, "stepover_pct": 40},
        {"id": "s", "name": "Surface", "type": "surface", "tc": "TC4", "pattern": "zigzag", "stepover_pct": 30, "sample": 0.5, "boundary": "stock"}])
    res = cam.run(doc, sh, BITS)
    w, p, s = res["operations"][2:]
    for o in (w, p, s):
        assert o["ok"], (o["name"], o["errors"])
        assert o["hm"] and "height map simulation" in " ".join(o["messages"])
    assert w["gouge_mm3"] < 0.05 and w["removed_mm3"] > 500 and "waterline(s)" in w["messages"][-1]
    assert p["gouge_mm3"] < 0.05 and p["removed_mm3"] > 200 and p["levels"]          # the waterline took part of the pocket
    assert s["hm"]["gouge_mm3"] < 1.0 and s["hm"].get("mesh") and s["hm"]["mesh"]["triangles"] and "cut by the height map surface" in " ".join(s["messages"])
    # the surface operation cuts the solid stock (the stock after the pocket less the material under the surface)
    before = cam.run(job_doc(sh, ops=doc["operations"][:4]), sh, BITS)["stock"]
    assert cam._volume(before) - cam._volume(res["stock"]) > 50
    assert any(m["k"] == "feed" and m["p"][2] not in (w["heights"]["final"],) for m in s["moves"])
    left, gone, _ = cam.remaining(res["stock"], sh)
    assert gone < 1.0
    # the patterns of the surface operation
    for pat in ("line", "circular", "circular_zigzag", "offset", "spiral"):
        o = cam.run(job_doc(sh, ops=[{"id": "s", "name": "S", "type": "surface", "tc": "TC4", "pattern": pat, "stepover_pct": 50, "sample": 1.0, "faces": [k["floor"]], "boundary": "faces"}]), sh, BITS)["operations"][0]
        assert o["ok"], (pat, o["errors"])
        assert o["moves"]


def test_dressups_derived_and_supplemental():
    from drawgen import cam
    from drawgen.cam import dressup as D
    sh = job_shape()
    k = keys_of(sh)
    prof = {"id": "pr", "name": "Profile", "type": "profile", "tc": "TC1", "step_down": 4, "extra": 0.2}
    plain = run_one(sh, prof)
    assert plain["ok"]
    # lead in / out: arcs added at the start and the end of every level
    o = run_one(sh, dict(prof, dressups=[{"type": "leadinout", "style": "arc", "length": 4}]))
    assert o["ok"], o["errors"]
    assert sum(1 for m in o["moves"] if m["k"] == "arc") >= 2 * len(o["levels"]) and "lead" in " ".join(o["messages"]).lower()
    o = run_one(sh, dict(prof, dressups=[{"type": "leadinout", "style": "tangent", "length": 4, "lead_out": False}]))
    assert o["ok"] and o["moves"]
    # boundary: the path cut at a rectangle covering half the part
    o = run_one(sh, dict(prof, dressups=[{"type": "boundary", "xmin": -10, "xmax": 50, "ymin": -10, "ymax": 70, "inside": True}]))
    assert o["ok"], o["errors"]
    assert max(m["p"][0] for m in o["moves"] if m["k"] in ("feed", "arc")) < 50.5 and o["cut_mm"] < plain["cut_mm"]
    # dogbone on an inside pocket profile
    pk = {"id": "pk", "name": "Pocket profile", "type": "profile", "tc": "TC6", "faces": [k["floor"]], "side": "inside", "final_depth": 6.0, "step_down": 4, "extra": 0,
          "dressups": [{"type": "dogbone", "style": "dogbone", "side": "left", "incision": "adaptive"}]}
    base = job_doc(sh)
    o = cam.run(job_doc(sh, ops=base["operations"][:2] + [pk]), sh, BITS)["operations"][2]
    assert o["ok"], o["errors"]
    assert "dogbone" in " ".join(o["messages"]).lower()
    # ramp methods
    for method in ("ramp2", "zigzag", "helix"):
        o = run_one(sh, dict(prof, dressups=[{"type": "ramp", "method": method, "angle": 5}]))
        assert o["ok"], (method, o["errors"])
        assert "plunge(s) replaced" in " ".join(o["messages"])
    # the order of the dressups is fixed (dogbone, tag, lead in/out, ramp, boundary)
    assert D.ORDER["tag"] < D.ORDER["ramp"] and D.ORDER["dogbone"] == min(D.ORDER.values())
    # copy and array of the drilling, supplemental operations
    drill = {"id": "d", "name": "Drill", "type": "drilling", "tc": "TC3", "faces": [k["hole"]], "peck": 3}
    doc = job_doc(sh, ops=[drill, {"id": "c", "name": "Copy", "type": "copy", "of": "d"},
                           {"id": "a", "name": "Array", "type": "array", "of": "d", "kind": "linear", "count": 2, "dx": 20, "dy": 0},
                           {"id": "pa", "name": "Polar", "type": "array", "of": "d", "kind": "polar", "count": 3, "angle": 360, "cx": 50, "cy": 30},
                           {"id": "f", "name": "Fixture", "type": "fixture", "fixture": "G55", "shift": [1, 2, 0]},
                           {"id": "k", "name": "Comment", "type": "comment", "text": "hello (world)"},
                           {"id": "s", "name": "Stop", "type": "stop", "optional": True},
                           {"id": "u", "name": "Custom", "type": "custom", "gcode": "M08\nM09"}])
    res = cam.run(doc, sh, BITS)
    recs = {o["id"]: o for o in res["operations"]}
    for o in res["operations"]:
        assert o["ok"], (o["name"], o["errors"])
    assert recs["c"]["moves"] == recs["d"]["moves"] and recs["c"]["removed_mm3"] < 0.05 and recs["c"]["tool"] == "TC3"
    assert len(recs["a"]["moves"]) == 2 * len(recs["d"]["moves"]) and abs(recs["a"]["gouge_mm3"] - math.pi * 9 * 10) < 5.0     # the second hole is drilled into the plate
    assert len(recs["pa"]["moves"]) == 3 * len(recs["d"]["moves"])
    assert recs["f"]["moves"] == [{"k": "fixture", "g": "G55"}] and recs["k"]["moves"][0]["text"] == "hello (world)"
    assert recs["s"]["moves"] == [{"k": "stop", "optional": True}] and recs["u"]["moves"][0]["k"] == "custom"
    g = cam.gcode(doc, res, BITS)
    assert "(fixture G55: shift X1.000 Y2.000 Z0.000)" in g and "(hello [world])" in g and "M01" in g and "M08" in g and "M09" in g
    gg = cam.gcode(doc, res, BITS, post="generic")
    assert "G55" in gg.splitlines() and "M1" in gg.splitlines()
    bad = cam.run(job_doc(sh, ops=[{"id": "c", "name": "Copy", "type": "copy", "of": "zz"}]), sh, BITS)["operations"][0]
    assert not bad["ok"] and "not before" in bad["errors"][0]


def test_gcode_text():
    import re
    from drawgen import cam
    sh = job_shape()
    doc = job_doc(sh, origin={"xy": "part", "z": "part"})
    doc["operations"] = doc["operations"][:4]
    res = cam.run(doc, sh, BITS)
    assert all(o["ok"] for o in res["operations"])
    g = cam.gcode(doc, res, BITS, post="generic")
    lines = g.splitlines()
    assert lines[0] == "%" and lines[-1] == "%" and "M30" in lines and "G21 G90 G17 G40 G49 G54" in lines
    assert "T1 M6" in lines and "S12000 M3" in lines and "T3 M6" in lines and "G4 P0.5" in lines
    assert lines.index("T1 M6") < lines.index("T3 M6") and lines.count("T1 M6") == 1          # one tool change for the three end mill operations
    # the feed written when it changes only
    g1 = [l for l in lines if l.startswith("G1")]
    assert g1 and g1[0].endswith("F200") and sum(1 for l in g1 if " F" in l) < len(g1)
    e = cam.gcode(doc, res, BITS)
    el = e.splitlines()
    assert el[0].startswith("(") and "%" not in e and "M30" not in e and "G21" not in e and "G54" not in e and "G4" not in e and "(dwell 0.5 s)" in el
    assert "M06 T1" in el and "S12000" in el and "M03" in el and "M05" in el and el.index("M05") < el.index("M06 T3")
    for l in el:
        if l.startswith("("):
            continue
        assert len(re.findall(r"\bG\d+", l)) <= 1 and len(re.findall(r"\bM\d+", l)) <= 1, l
        assert not re.search(r"\bG\d+", l) or re.match(r"G0[0-3]\b", l), l
        assert not re.search(r"\bM\d+", l) or re.match(r"M0[0-9]\b", l), l
    assert all(" X" in l and " Y" in l and " Z" in l for l in el if l.startswith("G01"))
    arcs = [l for l in el if l.startswith("G02") or l.startswith("G03")]
    assert arcs and all(" I" in l and " J" in l for l in arcs)
    assert not any("," in l for l in el if not l.startswith("("))
    assert "(machine zero at job X0.000 Y0.000 Z0.000)" in e
    # one operation (Inspect)
    one = cam.gcode(doc, res, BITS, only=3)
    assert "(drilling: Drill" in one and "(face: Face" not in one
    with pytest.raises(ValueError):
        cam.gcode(dict(doc, post="haas"), res, BITS)
    # the machine zero at the stock corner: Z of the part top is negative
    doc0 = job_doc(sh)
    doc0["operations"] = doc0["operations"][:1]
    e0 = cam.gcode(doc0, cam.run(doc0, sh, BITS), BITS)
    assert "(machine zero at job X-2.000 Y-2.000 Z18.000)" in e0 and "Z-2.000" in e0
    assert next(l for l in e0.splitlines() if l.startswith("G00 Z")).endswith("Z5.000")


def test_sanity_and_template():
    from drawgen import cam
    sh = job_shape()
    doc = job_doc(sh)
    s = cam.sanity(doc, sh, BITS)
    assert all(x["level"] != "error" for x in s) and any("output file name" in x["text"] for x in s)
    bad = copy.deepcopy(doc)
    bad["operations"][2]["faces"] = []
    bad["operations"][3]["tc"] = "TC9"
    bad["tools"][0]["hfeed"] = 0
    bad["tools"][1]["number"] = 1
    bad["operations"].append({"id": "c", "name": "Copy", "type": "copy", "of": "zz"})
    bad["operations"][5]["start_depth"] = 5
    bad["operations"][5]["final_depth"] = 6
    txt = [x["text"] for x in cam.sanity(bad, sh, BITS)]
    assert any("no base geometry" in t for t in txt) and any("no tool controller" in t for t in txt) and any("feed or plunge feed is 0" in t for t in txt)
    assert any("same tool number" in t for t in txt) and any("copies is not in the job" in t for t in txt) and any("final depth is not below" in t for t in txt)
    small = dict(doc, stock={"kind": "box", "xmin": 10, "ymin": 0, "zmin": 0, "xmax": 90, "ymax": 60, "zmax": 18})
    assert any("does not cover the part" in x["text"] for x in cam.sanity(small, sh, BITS))
    assert any("no part is chosen" in x["text"] for x in cam.sanity(dict(doc, source={"type": "part", "name": ""}), None, BITS))
    res = cam.run(dict(doc, operations=doc["operations"][:1] + [{"id": "x", "name": "X", "type": "pocket", "tc": "TC1", "faces": []}]), sh, BITS)
    assert any(x["level"] == "error" and "no floor face" in x["text"] for x in cam.sanity(doc, sh, BITS, res))
    # the template: the operations without geometry; applied to a blank job with new ids
    tpl = cam.template(doc)
    assert tpl["format"] == "shinycad-cam-template" and len(tpl["operations"]) == 6 and "faces" not in tpl["operations"][1] and tpl["tools"] == cam.migrate(doc)["tools"]
    blank = cam.migrate({"name": "new", "source": {"type": "part", "name": "job"}, "next": 3})
    d = cam.apply_template(blank, tpl)
    assert d["name"] == "new" and [o["type"] for o in d["operations"]] == [o["type"] for o in doc["operations"]]
    assert d["operations"][1]["faces"] == [] and d["operations"][0]["id"] == "op3" and d["next"] == 9 and d["setup"] == tpl["setup"]
    assert d["operations"][5]["dressups"] == doc["operations"][5]["dressups"]


# --------------------------------------------------------------------------- server

def ok(r):
    assert r.status_code == 200, r.get_data(as_text=True)[:500]
    return r.get_json()


def test_cam_routes(client, web):
    import os
    ok(client.put("/api/part/file/job", json=job_part("job")))
    meta = ok(client.get("/api/cam/meta"))
    assert meta["op_names"]["pocket"] == "Pocket Shape" and "dovetail" in meta["shapes"] and meta["setup"]["step_down"] == 2.0 and [p["id"] for p in meta["posts"]] == ["estlcam", "generic", "grbl", "linuxcnc", "mach3"]
    bits = ok(client.get("/api/cam/tools"))
    assert bits and bits[0]["id"] and all("shape" in b for b in bits)
    saved = ok(client.put("/api/cam/tools", json=BITS))
    assert [t["id"] for t in saved] == [b["id"] for b in BITS]
    with open(web.CONFIG_PATH, "r", encoding="utf-8") as f:
        assert "cam_tools" in f.read()
    r = client.put("/api/cam/tools", json=[TOOL, dict(TOOL)])
    assert r.status_code == 400 and "twice" in r.get_json()["error"]
    r = client.put("/api/cam/tools", json=[dict(TOOL, height=20)])
    assert r.status_code == 400 and "cutting height" in r.get_json()["error"]
    # the geometry of the part: face and edge keys, face kinds, undercut faces
    doc = {"name": "jobcam", "source": {"type": "part", "name": "job"}, "stock": {"kind": "offsets", "xneg": 2, "xpos": 2, "yneg": 2, "ypos": 2, "zneg": 0, "zpos": 2},
           "tools": controllers(), "operations": [], "next": 1}
    g = ok(client.post("/api/cam/geometry", json={"cam": doc}))
    assert len(g["undercuts"]) == 1 and g["face_keys"][g["undercuts"][0]]["n"][2] < 0 and g["edge_keys"] and g["face_kind"].count("hole") >= 1
    floors = [i for i, k in enumerate(g["face_kind"]) if k == "floor" and abs(g["face_keys"][i]["c"][2] - 6) < 1e-6]
    assert len(floors) == 1
    su = ok(client.post("/api/cam/setup", json={"cam": doc}))
    assert su["stock_bbox"] == pytest.approx([-2.0, -2.0, 0.0, 102.0, 62.0, 18.0], abs=1e-5) and su["origin"] == pytest.approx([-2.0, -2.0, 18.0], abs=1e-5)
    assert su["clearance_z"] == pytest.approx(23.0, abs=1e-5) and su["part_bbox"][5] == pytest.approx(16.0, abs=1e-6)
    doc["operations"] = [{"id": "o1", "name": "Face", "type": "face", "tc": "TC1", "pattern": "zigzag", "stepover_pct": 60, "step_down": 1},
                         {"id": "o2", "name": "Pocket", "type": "pocket", "tc": "TC1", "faces": [g["face_keys"][floors[0]]], "pattern": "offset", "stepover_pct": 40},
                         {"id": "o3", "name": "Comment", "type": "comment", "text": "done"}]
    # a preview of the first operation, then the whole job (the first from the cache)
    j1 = ok(client.post("/api/cam/run", json={"cam": doc, "upto": 0}))
    assert len(j1["operations"]) == 1 and j1["operations"][0]["ok"] and j1["stock_mesh"]["triangles"] and "sanity" in j1
    j = ok(client.post("/api/cam/run", json={"cam": doc}))
    assert [o["ok"] for o in j["operations"]] == [True, True, True] and j["gone_mm3"] < 0.05 and j["left_mm3"] > 0 and j["left_mesh"]
    assert j["operations"][1]["heights"]["start"] == pytest.approx(16.0, abs=1e-5) and j["clearance_z"] == pytest.approx(23.0, abs=1e-5) and j["origin"] == pytest.approx([-2.0, -2.0, 18.0], abs=1e-5)
    s = ok(client.post("/api/cam/sanity", json={"cam": doc}))
    assert all(x["level"] != "error" for x in s)
    # saved and listed; the file is read back migrated
    ok(client.put("/api/cam/file/jobcam", json=doc))
    assert "jobcam" in ok(client.get("/api/cam/list"))
    back = ok(client.get("/api/cam/file/jobcam"))
    assert back["operations"][0]["id"] == "o1" and back["setup"]["clearance_offset"] == 5.0 and back["operations"][0]["active"] is True
    docs = ok(client.get("/api/project/docs"))
    d = next(x for x in docs["docs"] if x["type"] == "cam" and x["name"] == "jobcam")
    assert {"type": "part", "name": "job"} in d["links"]
    # the template
    tpl = ok(client.post("/api/cam/template", json={"cam": doc}))
    assert tpl["format"] == "shinycad-cam-template" and "faces" not in tpl["operations"][1]
    applied = ok(client.post("/api/cam/template", json={"cam": {"name": "n", "source": {"type": "part", "name": "job"}}, "apply": tpl}))
    assert [o["type"] for o in applied["operations"]] == ["face", "pocket", "comment"] and applied["operations"][1]["faces"] == []
    assert client.post("/api/cam/template", json={"cam": doc, "apply": {"format": "x"}}).status_code == 400
    # G-code: inspect one operation, write to the cam folder, download, the generic post, no overwrite
    ins = ok(client.post("/api/cam/gcode", json={"cam": doc, "inspect": 1}))
    assert "(pocket: Pocket" in ins["text"] and "(face: Face" not in ins["text"] and ins["lines"] > 10
    jw = ok(client.post("/api/cam/gcode", json={"cam": doc}))
    path = jw["written"][0]
    assert os.path.isfile(path) and os.path.basename(os.path.dirname(path)) == "cam" and path.endswith("jobcam.nc")
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    assert "M06 T1" in txt and "M03" in txt and "(done)" in txt and "M30" not in txt
    assert client.post("/api/cam/gcode", json={"cam": doc}).status_code == 409
    ok(client.post("/api/cam/gcode", json={"cam": doc, "overwrite": True}))
    named = ok(client.post("/api/cam/gcode", json={"cam": dict(doc, output={"folder": "", "name": "plate_top"})}))
    assert named["written"][0].endswith("plate_top.nc")
    r = client.post("/api/cam/gcode", json={"cam": dict(doc, post="generic"), "folder": "-"})
    assert r.status_code == 200 and "M30" in r.get_data(as_text=True)
    r = client.post("/api/cam/gcode", json={"cam": doc, "folder": "-"})
    assert r.status_code == 200 and r.get_data(as_text=True).startswith("(ShinyCAD CAM")
    # a failing operation gives no G-code
    bad = copy.deepcopy(doc)
    bad["operations"][1]["faces"] = []
    r = client.post("/api/cam/gcode", json={"cam": bad})
    assert r.status_code == 400 and "no floor face" in r.get_json()["error"]
    # an engrave operation with a saved sketch
    ok(client.put("/api/sketch/file/letters", json={"entities": rect(10, 5, 20, 2)}))       # on the rail top (Z 16)
    doc2 = dict(doc, operations=[doc["operations"][0], {"id": "e", "name": "Engrave", "type": "engrave", "tc": "TC5", "sketch": {"name": "letters"}, "depth": 0.2, "edges": []}])
    je = ok(client.post("/api/cam/run", json={"cam": doc2, "meshes": False}))
    assert je["operations"][1]["ok"], je["operations"][1]["errors"]
    assert "1 path(s)" in je["operations"][1]["messages"][0] and "stock_mesh" not in je
    # renaming the part follows into the CAM document
    ok(client.post("/api/project/doc", json={"op": "rename", "type": "part", "name": "job", "new": "job2"}))
    assert ok(client.get("/api/cam/file/jobcam"))["source"]["name"] == "job2"


def test_model_placement(client, web):
    """Model placement: constraints of faces to the datum planes solved (the rail turned over onto its top, an end face
    on YZ, a side face on XZ), a conflicting set flips one constraint, Distance and Parallel, the suggested datum and
    Flip keep the part in place, the face found again by its centre, the placed part in geometry, setup and run, the
    route and migration."""
    from drawgen.cam import placement as PL, geom, job
    sh = rail_shape()
    refs = PL.face_refs(sh)
    top = next(i for i, r in enumerate(refs) if r["kind"] == "plane" and r["n"][2] > 0.99 and abs(r["c"][2] - 16) < 1e-6)
    bottom = next(i for i, r in enumerate(refs) if r["kind"] == "plane" and r["n"][2] < -0.99)
    side = next(i for i, r in enumerate(refs) if r["kind"] == "plane" and r["n"][1] < -0.99)
    end = next(i for i, r in enumerate(refs) if r["kind"] == "plane" and r["n"][0] > 0.99)
    # the rail top on the table, the +X end face on YZ, the -Y side on XZ: the part turned about Y lies at x >= 0
    pl = {"constraints": [{"id": "c1", "type": "coincident", "face": top, "datum": "XY"},
                          {"id": "c2", "type": "coincident", "face": end, "datum": "YZ"},
                          {"id": "c3", "type": "coincident", "face": side, "datum": "XZ"}]}
    r = PL.solve(pl, sh)
    assert not r["unsatisfied"] and not r["flipped"], r
    bb = geom.bbox(PL.apply(sh, dict(pl, pos=r["pos"], rot=r["rot"])))
    assert bb == pytest.approx([0.0, 0.0, 0.0, 100.0, 60.0, 16.0], abs=1e-3)
    assert all(c.get("fc") for c in r["constraints"])
    # the -X end face on YZ facing as well: no rotation does both, one constraint is flipped
    pl2 = {"constraints": pl["constraints"][:2] + [{"id": "c4", "type": "coincident", "face": next(i for i, x in enumerate(refs) if x["kind"] == "plane" and x["n"][0] < -0.99), "datum": "YZ"}]}
    r2 = PL.solve(pl2, sh)
    assert r2["flipped"] or r2["unsatisfied"]
    assert all("Part / Datum" not in t for t in list(r2["unsatisfied"].values()) + r2["messages"])
    # bottom 5 mm above the table, the end face parallel to XZ: turned 90 deg about Z
    r3 = PL.solve({"constraints": [{"id": "d", "type": "distance", "face": bottom, "datum": "XY", "value": 5},
                                   {"id": "p", "type": "parallel", "face": end, "datum": "XZ"}]}, sh)
    bb3 = geom.bbox(PL.apply(sh, {"pos": r3["pos"], "rot": r3["rot"]}))
    assert bb3[2] == pytest.approx(5.0, abs=1e-3) and bb3[3] - bb3[0] == pytest.approx(60.0, abs=1e-3) and bb3[4] - bb3[1] == pytest.approx(100.0, abs=1e-3)
    # suggestions keep the part where it is
    sg = PL.suggest({}, sh, top, "distance")
    assert sg["datum"] == "XY" and sg["flip"] is True
    r4 = PL.solve({"constraints": [dict(sg, id="s", type="distance", face=top)]}, sh)
    assert r4["pos"] == pytest.approx([0, 0, 0], abs=1e-6) and r4["rot"] == pytest.approx([0, 0, 0], abs=1e-6)
    sg = PL.suggest({}, sh, bottom, "coincident")
    assert sg == {"datum": "XY", "flip": False, "value": 0.0, "kind": "plane"}
    # the face found by its centre when the index is wrong; a face that is gone is reported
    c = dict(r["constraints"][0], face=0)
    assert PL._face_of(c, refs) == top
    r5 = PL.solve({"constraints": [{"id": "x", "type": "coincident", "face": 99, "datum": "XY"}]}, sh)
    assert "x" in r5["unsatisfied"] and r5["pos"] == [0, 0, 0]
    # the machine zero at a picked vertex
    assert job.origin_of({"origin": {"xy": "point", "z": "point", "point": [5, 6, 7]}}, [0, 0, 0, 10, 10, 10]) == [5, 6, 7]
    assert job.origin_of({"origin": {"xy": "point", "z": "stock_top", "point": [5, 6, 7]}}, [0, 0, 0, 10, 10, 10]) == [5, 6, 10]
    # migration, identity, key
    d = job.migrate({"name": "n"})
    assert d["placement"]["pos"] == [0, 0, 0] and d["placement"]["constraints"] == [] and PL.key(d["placement"]) == ""
    assert PL.key({"pos": [1, 0, 0]}) and PL.apply(sh, {}) is sh
    # server: the solve route and the placed part in geometry, setup and run
    ok(client.put("/api/part/file/railpl", json=rail_part("railpl")))
    doc = {"name": "plc", "source": {"type": "part", "name": "railpl"}, "stock": {"kind": "offsets", "xneg": 0, "xpos": 0, "yneg": 0, "ypos": 0, "zneg": 0, "zpos": 1},
           "tools": controllers(), "operations": [], "placement": {"constraints": [dict(c, face=0) for c in r["constraints"]]}, "next": 1}
    rr = ok(client.post("/api/cam/placement", json={"cam": doc}))
    assert not rr["unsatisfied"]
    doc["placement"] = {"pos": rr["pos"], "rot": rr["rot"], "constraints": rr["constraints"]}
    g = ok(client.post("/api/cam/geometry", json={"cam": doc}))
    assert g["bbox"] == pytest.approx([0.0, 0.0, 0.0, 100.0, 60.0, 16.0], abs=1e-3) and g["undercuts"] == []
    su = ok(client.post("/api/cam/setup", json={"cam": doc}))
    assert su["stock_bbox"][5] == pytest.approx(17.0, abs=1e-3)
    ptop = next(c["face"] for c in rr["constraints"] if c["id"] == "c1")
    s2 = ok(client.post("/api/cam/placement", json={"cam": doc, "suggest": {"face": ptop, "type": "coincident"}}))
    assert s2["datum"] == "XY" and s2["flip"] is False
    doc["operations"] = [{"id": "o1", "name": "Face", "type": "face", "tc": "TC1", "pattern": "zigzag", "stepover_pct": 60}]
    j = ok(client.post("/api/cam/run", json={"cam": doc, "meshes": False}))
    assert j["operations"][0]["ok"] and j["operations"][0]["heights"]["final"] == pytest.approx(16.0, abs=1e-3)
    assert client.post("/api/cam/placement", json={"cam": doc, "suggest": {"face": 999, "type": "coincident"}}).status_code == 400
    # Angle of a face parallel to the datum: turned about its longest edge; with the lower back edge on the X axis the
    # part turns about that edge (negative value: the other direction); a straight edge at an angle to a plane
    from build123d import Box as _Box, Location as _Loc, Vector as _V
    from drawgen import assembly as _A
    bx = _Box(105, 20, 24).moved(_Loc(_V(52.5, 10, 12)))
    brefs = PL.face_refs(bx)
    bot = next(i for i, x in enumerate(brefs) if x["kind"] == "plane" and x["n"][2] < -0.99)
    sga = PL.suggest({}, bx, bot, "angle")
    assert sga["datum"] == "XY" and sga["flip"] is True and sga["value"] == 0.0
    er = _A.edge_refs(bx)
    ei = next(i for i, e in enumerate(er) if e and e["kind"] == "line" and abs(e["n"][0]) > 0.99 and abs(e["c"][1] - 20) < 1e-6 and abs(e["c"][2]) < 1e-6)
    for v, rx, zr in ((45, 45.0, [-14.1421, 16.9706]), (-45, -45.0, [0.0, 31.1127])):
        ra = PL.solve({"constraints": [dict(sga, id="a", type="angle", face=bot, value=v),
                                       {"id": "b", "type": "coincident", "edge": ei, "ec": er[ei]["c"], "datum": "X", "flip": True}]}, bx)
        assert not ra["unsatisfied"] and ra["rot"] == pytest.approx([rx, 0, 0], abs=1e-3), ra
        bb = geom.bbox(PL.apply(bx, {"pos": ra["pos"], "rot": ra["rot"]}))
        assert [bb[2], bb[5]] == pytest.approx(zr, abs=1e-3) and bb[0] == pytest.approx(0, abs=1e-3)
    sge = PL.suggest({}, bx, None, "angle", edge=er[ei]["c"])
    assert sge["datum"] == "XY" and sge["edge"] == ei
    re_ = PL.solve({"constraints": [dict(sge, id="e", type="angle", value=30)]}, bx)
    assert not re_["unsatisfied"] and abs(re_["rot"][1]) == pytest.approx(30, abs=1e-3)
    # a preview run stopped by a later preview (or the cancel route) of the same client; other runs are not stopped
    with pytest.raises(job.Cancelled):
        job.run(doc, sh, BITS, cancel=lambda: True)
    gen = web._CAM_PREVIEW.get("pg1", 0)
    ok(client.post("/api/cam/cancel", json={"preview": "pg1"}))
    assert web._CAM_PREVIEW["pg1"] == gen + 1
    j = ok(client.post("/api/cam/run", json={"cam": doc, "meshes": False, "preview": "pg1"}))
    assert j["operations"][0]["ok"]


def test_cam_measure(client, web):
    """Measure in a CAM job: two planar faces (distance between the planes), a straight edge (length), a vertex in
    machine coordinates, the machine zero and the stock top, a face index out of range; the placed part measured."""
    from drawgen import part as P
    ok(client.put("/api/part/file/meas", json=job_part("meas")))
    sh, _ = P.build(P.migrate(job_part("meas")))
    fs = sh.faces()
    top = next(i for i, f in enumerate(fs) if _kind(f) == _plane() and abs(f.center().Z - 10) < 1e-6 and f.area > 1000)
    floor = next(i for i, f in enumerate(fs) if _kind(f) == _plane() and abs(f.center().Z - 6) < 1e-6)
    edge = next(i for i, e in enumerate(sh.edges()) if e.geom_type.name == "LINE" and abs(e.length - 100) < 1e-6)
    doc = {"name": "m", "source": {"type": "part", "name": "meas"}, "stock": {"kind": "offsets", "xneg": 2, "xpos": 2, "yneg": 2, "ypos": 2, "zneg": 0, "zpos": 1},
           "origin": {"xy": "stock_min", "z": "stock_top"}, "tools": controllers(), "operations": []}
    r = ok(client.post("/api/cam/measure", json={"cam": doc, "items": [{"face": top}, {"face": floor}]}))
    rows = dict(r["rows"])
    assert rows["Distance between the planes"] == "4.0000 mm" and rows["Angle between the planes"] == "0.0000 deg"
    assert r["items"][0].endswith("planar face") and r["origin"] == pytest.approx([-2, -2, 17], abs=1e-6)
    r = ok(client.post("/api/cam/measure", json={"cam": doc, "items": [{"edge": edge}]}))
    assert dict(r["rows"])["Straight edge"] == "length 100.0000 mm" and "straight edge" in r["items"][0]
    r = ok(client.post("/api/cam/measure", json={"cam": doc, "items": [{"vertex": [0, 0, 0]}]}))
    assert dict(r["rows"])["Point, machine coordinates"] == "(2.0000, 2.0000, -17.0000)"
    r = ok(client.post("/api/cam/measure", json={"cam": doc, "items": [{"ref": "stock_top"}, {"face": top}]}))
    assert dict(r["rows"])["Distance between the planes"] == "7.0000 mm"
    r = ok(client.post("/api/cam/measure", json={"cam": doc, "items": [{"ref": "zero"}, {"vertex": [0, 0, 0]}]}))
    assert dict(r["rows"])["Minimum distance"] == "%.4f mm" % math.sqrt(2 * 2 + 2 * 2 + 17 * 17)
    # the placed part (the offsets stock moves with it)
    moved = dict(doc, placement={"pos": [0, 0, 5], "rot": [0, 0, 0]})
    r = ok(client.post("/api/cam/measure", json={"cam": moved, "items": [{"face": top}, {"ref": "stock_bottom"}]}))
    assert dict(r["rows"])["Distance between the planes"] == "10.0000 mm"
    r = ok(client.post("/api/cam/measure", json={"cam": moved, "items": [{"face": top}]}))
    assert dict(r["rows"])["Centre"].endswith(", 15.0000)")
    assert client.post("/api/cam/measure", json={"cam": doc, "items": [{"face": 999}]}).status_code == 400
    assert client.post("/api/cam/measure", json={"cam": doc, "items": []}).status_code == 400


def test_pocket_entry_beside_stock(tmp_path):
    """A V-groove jaw turned 45 deg about X (the groove walls vertical and horizontal) with the blank as STEP stock:
    Pocket Shape on the groove floor starts at the stock over the floor (a Start depth above it does not change the
    levels, one below it does), every level goes down beside the stock (open side) instead of a helix in the
    stock, and nothing of the part is cut; Line and ZigZag passes leave nothing on the wall parallel to them."""
    from build123d import Box, Location, Vector, Polyline, make_face, extrude, Axis, export_step
    from shapely.geometry import Point
    from drawgen import cam, part as P
    from drawgen.cam import geom as G
    blank = Box(105, 20, 24).moved(Location(Vector(52.5, 10, 12)))
    v = extrude(make_face(Polyline((0, 20, 6), (0, 20, 18), (0, 14, 12), close=True)), 105, dir=(1, 0, 0))
    part, stock = blank.cut(v).clean().rotate(Axis.X, 45), blank.rotate(Axis.X, 45)
    dz = -G.bbox(stock)[2]
    part, stock = part.moved(Location(Vector(0, 0, dz))), stock.moved(Location(Vector(0, 0, dz)))
    path = str(tmp_path / "jaw_blank.step")
    export_step(stock, path)
    floor = next(f for f in part.faces() if _kind(f) == _plane() and f.normal_at(f.center()).Z > 0.999)
    op = {"id": "o1", "name": "Pocket", "type": "pocket", "tc": "TC1", "faces": [P.face_key(floor)], "pattern": "offset", "stepover_pct": 40, "step_down": 1, "entry": "helix"}
    doc = {"name": "j", "source": {"type": "part", "name": "x"}, "stock": {"kind": "step", "path": path}, "tools": controllers(), "operations": [op]}
    r = cam.run(doc, part, BITS)["operations"][0]
    assert r["ok"] and r["gouge_mm3"] < 0.05, r
    top = r["heights"]["start"]
    assert top == pytest.approx(26.8701, abs=1e-3) and r["heights"]["final"] == pytest.approx(18.3848, abs=1e-3)
    assert not any(m.get("k") == "arc" for m in r["moves"])
    plunges = [m["p"] for m in r["moves"] if m.get("k") == "plunge"]
    assert len(plunges) >= 8
    for p in plunges:
        sec = G.section_polys(stock, p[2] + 0.01)
        assert sec.distance(Point(p[0], p[1])) >= 3.0 - 1e-6
    r28 = cam.run(dict(doc, operations=[dict(op, start_depth=28)]), part, BITS)["operations"][0]
    assert max(m["p"][2] for m in r28["moves"] if m.get("k") == "feed") == pytest.approx(top - 1, abs=1e-3)
    r25 = cam.run(dict(doc, operations=[dict(op, start_depth=25)]), part, BITS)["operations"][0]
    assert max(m["p"][2] for m in r25["moves"] if m.get("k") == "feed") == pytest.approx(24, abs=1e-3)
    # Line and ZigZag along the wall (the region bound at the wall a few micrometres above its corners): the first
    # pass runs the whole length, nothing left on the wall
    for pat in ("line", "zigzag"):
        res = cam.run(dict(doc, operations=[dict(op, pattern=pat, stepover_pct=25, entry="plunge", start_at="boundary", finish_mode="off")]), part, BITS)
        rp = res["operations"][0]
        assert rp["ok"] and rp["gouge_mm3"] < 0.05
        assert cam.remaining(res["stock"], part)[0] < 0.5, pat


def test_pocket_floor_with_notch(tmp_path):
    """The tilted V-groove jaw with a cross V-notch through the groove floor: the open edges of the floor are joined
    at the notch corners (no pinholes grown to the tool radius), so the ZigZag passes run through the notch and the
    tool stays down; no gouge."""
    from build123d import Box, Location, Vector, Polyline, make_face, extrude, Axis, export_step
    from shapely.geometry import LineString
    from drawgen import cam, part as P
    from drawgen.cam import geom as G, ops2d as O
    blank = Box(105, 20, 24).moved(Location(Vector(52.5, 10, 12)))
    v = extrude(make_face(Polyline((0, 20, 6), (0, 20, 18), (0, 14, 12), close=True)), 105, dir=(1, 0, 0))
    n = extrude(make_face(Polyline((47.5, 20, 0), (57.5, 20, 0), (52.5, 15, 0), close=True)), 24, dir=(0, 0, 1))
    part, stock = blank.cut(v).cut(n).clean().rotate(Axis.X, 45), blank.rotate(Axis.X, 45)
    dz = -G.bbox(stock)[2]
    part, stock = part.moved(Location(Vector(0, 0, dz))), stock.moved(Location(Vector(0, 0, dz)))
    path = str(tmp_path / "notch_blank.step")
    export_step(stock, path)
    floor = next(f for f in part.faces() if _kind(f) == _plane() and f.normal_at(f.center()).Z > 0.999)
    info = G.floor_info(part, floor)
    reg = O.pocket_region(part, info, 3.0, 0.0, 21.87, 22.87, True, False, 31.0)
    for y in (5, 7, 9):
        assert len(G.lines(reg.intersection(LineString([(-50, y), (200, y)])))) == 1, y
    op = {"id": "o1", "name": "Pocket", "type": "pocket", "tc": "TC1", "faces": [P.face_key(floor)], "pattern": "zigzag", "stepover_pct": 25, "step_down": 1, "entry": "plunge", "finish_mode": "off"}
    doc = {"name": "j", "source": {"type": "part", "name": "x"}, "stock": {"kind": "step", "path": path}, "tools": controllers(), "operations": [op]}
    r = cam.run(doc, part, BITS)["operations"][0]
    assert r["ok"] and r["gouge_mm3"] < 0.05
    assert sum(1 for m in r["moves"] if m.get("k") == "plunge") <= 4 * len(r["levels"])


def test_tslot_and_custom_bits():
    """T-slot cutter (disc profile, neck smaller than the disc), custom profile (points checked, D and the cutting
    height from them, bottom offset along the profile), feeds for both, and a custom profile equal to the 6 mm end
    mill gives the same Pocket Shape as the end mill."""
    from drawgen import cam
    from drawgen.cam import tools as T, feeds as F
    ts = T.normalize({"id": "TS", "shape": "tslot", "d": 16, "height": 6, "neck": 7, "neck_length": 10, "shank": 10, "flutes": 6})
    cut, body = T.tool_profile(ts)
    assert cut == [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (3.5, 6.0)] and body[1] == (3.5, 16.0)
    with pytest.raises(ValueError, match="smaller than the disc"):
        T.tool_profile(dict(ts, neck=16))
    cu = T.normalize({"id": "CU", "shape": "custom", "profile": [[0, 0], [4, 0], [6, 2], [6, 5], [3, 8]], "neck": 3})
    assert cu["d"] == 12 and cu["height"] == 8
    assert T.bottom_offset(cu, 2) == 0 and T.bottom_offset(cu, 5) == pytest.approx(1.0) and T.bottom_offset(cu, 7) is None
    for bad in ([[0, 0]], [[0, 1], [3, 2]], [[0, 0], [3, 2], [3, 1]], [[0, 0], [-1, 2]]):
        with pytest.raises(ValueError):
            T.tool_profile({"id": "B", "shape": "custom", "profile": bad})
    for b in (ts, cu):
        r = F.calc(b, "al_wrought", {}, 2.0, 1.0)
        assert r["rpm"] > 0 and r["feed"] > 0
    sh = job_shape()
    k = keys_of(sh)
    op = {"id": "o1", "name": "Pocket", "type": "pocket", "tc": "TC1", "faces": [k["floor"]], "pattern": "offset", "stepover_pct": 40}
    em = dict(END_MILL, id="T1")
    cus = {"id": "T1", "name": "Custom 6", "shape": "custom", "profile": [[0, 0], [3, 0], [3, 18]], "neck": 6, "shank": 6, "shank_length": 30,
           "feed": 800, "plunge": 200, "rpm": 12000}
    bits_em = [em] + [b for b in BITS if b["id"] != "T1"]
    bits_cu = [T.normalize(cus)] + [b for b in BITS if b["id"] != "T1"]
    r1 = cam.run(job_doc(sh, ops=[op]), sh, bits_em)["operations"][0]
    r2 = cam.run(job_doc(sh, ops=[op]), sh, bits_cu)["operations"][0]
    assert r1["ok"] and r2["ok"] and r2["removed_mm3"] == pytest.approx(r1["removed_mm3"], rel=1e-6) and r2["gouge_mm3"] < 0.05


def test_gouge_report():
    """A Face operation cut 0.5 mm into the plate top: the gouge volume, its place (volume, centre, bounding box),
    the first cutting move that reaches it, the level with the gouge, the gouge mesh; JSON-safe record; no gouge
    report without a gouge."""
    import json
    from drawgen import cam
    sh = job_shape()
    op = {"id": "o1", "name": "Face", "type": "face", "tc": "TC1", "pattern": "zigzag", "stepover_pct": 60, "step_down": 1, "final_depth": 15.5}
    r = cam.run(job_doc(sh, ops=[op]), sh, BITS)["operations"][0]
    assert r["ok"] and r["gouge_mm3"] > 700
    g = r["gouges"][0]
    assert g["volume"] == pytest.approx(r["gouge_mm3"], rel=1e-3) and g["bbox"][2] == pytest.approx(15.5, abs=1e-3) and g["bbox"][5] == pytest.approx(16, abs=1e-3)
    m = r["moves"][g["move"]]
    assert m["k"] != "rapid" and m["p"][2] == pytest.approx(15.5, abs=1e-6) and g["p"] == m["p"] and len(g["from"]) == 3
    assert [l.get("gouge_mm3") is not None for l in r["levels"]] == [False, False, True]
    assert r["gouge_mesh"]["triangles"]
    json.dumps(r)
    ok_rec = cam.run(job_doc(sh, ops=[dict(op, final_depth=None)]), sh, BITS)["operations"][0]
    assert ok_rec["gouge_mm3"] < 0.05 and "gouges" not in ok_rec and "gouge_mesh" not in ok_rec


def _plane():
    from OCP.GeomAbs import GeomAbs_Plane
    return GeomAbs_Plane


def test_feeds_and_speeds(client, web):
    """Feeds and speeds: rpm from the cutting speed, feed from the chip load and the flutes, radial chip thinning,
    ball end and V bit effective diameters, HSS, the spindle limits (rpm clamped, feed clamped, power below the rated
    speed lowers the feed), drills, rubbing warning, the route with the stock material, the sanity check of the
    spindle range, the materials in meta."""
    from drawgen.cam import feeds as FS, job
    mach = {"rpm_min": 6000, "rpm_max": 24000, "rpm_rated": 24000, "power_kw": 2.2, "feed_max": 10000}
    em = dict(END_MILL, flutes=3)
    r = FS.calc(em, "al_wrought", mach, 6, 1)
    n = 300 * 1000 / (math.pi * 6)
    fz = 0.08 * (0.6 ** 0.8)
    assert r["rpm"] == round(n) and r["fz"] == pytest.approx(fz, abs=1e-4) and r["rctf"] == 1.0
    assert r["feed"] == round(fz * 3 * n) and r["plunge"] == round(fz * 3 * n * 0.5) and not r["limited"]
    assert r["mrr"] == pytest.approx(6 * 1 * r["feed"] / 1000, rel=1e-3)
    # chip thinning at a 10 % step over
    r2 = FS.calc(em, "al_wrought", mach, 0.6, 1)
    assert r2["rctf"] == pytest.approx(1 / math.sqrt(1 - 0.8 ** 2), rel=1e-3) and r2["feed"] > r["feed"]
    assert FS.chip_thinning(0.01, 10) == FS.RCTF_MAX and FS.chip_thinning(5, 10) == 1.0
    # effective diameters
    assert FS.effective_diameter(BALL, 1) == pytest.approx(2 * math.sqrt(5), rel=1e-6) and FS.effective_diameter(BALL, 4) == 6
    assert FS.effective_diameter(VBIT, 1) == pytest.approx(0.2 + 2 * math.tan(math.radians(45)), rel=1e-6)
    rb = FS.calc(BALL, "al_wrought", mach, 3, 0.5)
    assert rb["deff"] < 6 and rb["rpm"] > r["rpm"]
    # HSS: lower cutting speed and chip load
    rh = FS.calc(dict(em, tool_material="hss"), "al_wrought", mach, 6, 1)
    assert rh["rpm"] < r["rpm"] and rh["fz"] == pytest.approx(0.8 * r["fz"], abs=2e-4) and rh["tool_material"] == "hss"
    # spindle maximum, feed maximum, minimum
    rv = FS.calc(VBIT, "al_wrought", mach, None, 0.2)
    assert rv["rpm"] == 24000 and "rpm_max" in rv["limited"]
    rw = FS.calc(em, "wd_mdf", dict(mach, feed_max=3000), 6, 3)
    assert rw["feed"] == 3000 and "feed_max" in rw["limited"]
    rs = FS.calc(TOOL, "st_struct", mach, 1, 6.5)
    assert rs["rpm"] == 6000 and any("below the spindle minimum" in w for w in rs["warnings"])
    # power: a 1 kW spindle rated at 24000 rpm gives a quarter at 6000 rpm; the feed is lowered to fit
    rp = FS.calc(em, "st_struct", dict(mach, power_kw=1.0), 6, 6)
    assert "power" in rp["limited"] and rp["power_kw"] == pytest.approx(rp["power_avail_kw"], rel=0.02)
    assert rp["power_avail_kw"] == pytest.approx(1.0 * rp["rpm"] / 24000, rel=1e-3)
    # drill: feed per revolution
    rd = FS.calc(DRILL, "al_wrought", dict(mach, rpm_rated=6000))
    assert rd["feed"] == rd["plunge"] and rd["feed"] == pytest.approx(0.025 * 6 * rd["rpm"], rel=0.01)
    # rubbing: a tiny chip load in steel
    rr = FS.calc(dict(END_MILL, d=1.0, flutes=2), "st_stainless", mach, 0.02, 0.1)
    assert any("rubs" in w for w in rr["warnings"])
    with pytest.raises(ValueError):
        FS.calc(em, "unobtainium", mach)
    assert {m["group"] for m in FS.materials()} == {"Aluminium", "Steel", "Brass and bronze", "Plastics", "Wood and boards"}
    # setup sheet keeps the machine fields; the sanity check of the spindle range and the feed
    d = job.migrate({"setup": {"rpm_max": 18000}})
    assert d["setup"]["rpm_max"] == 18000 and d["setup"]["power_kw"] == 2.2
    doc = {"name": "fs", "source": {"type": "part", "name": "x"}, "tools": [dict(controllers()[0], rpm=30000, hfeed=9000)], "operations": []}
    txt = [x["text"] for x in job.sanity(doc, None, BITS)]
    assert any("outside the spindle range" in t for t in txt) and any("above the machine maximum" in t for t in txt)
    # the route: the stock material, a bit, errors
    meta = ok(client.get("/api/cam/meta"))
    assert any(m["id"] == "cu_brass" for m in meta["materials"]) and meta["setup"]["rpm_rated"] == 24000 and meta["tool_materials"]["hss"] == "HSS"
    ok(client.put("/api/cam/tools", json=BITS))
    cdoc = {"name": "fs", "stock": {"kind": "offsets", "material": "pl_pom"}, "tools": controllers(), "operations": []}
    j = ok(client.post("/api/cam/feeds", json={"cam": cdoc, "tc": "TC1", "ae": 3, "ap": 2}))
    assert j["material"] == "pl_pom" and j["ae"] == 3 and j["rpm"] > 0
    assert ok(client.post("/api/cam/feeds", json={"cam": cdoc, "bit": "T5", "material": "wd_soft"}))["material"] == "wd_soft"
    assert client.post("/api/cam/feeds", json={"cam": dict(cdoc, stock={}), "tc": "TC1"}).status_code == 400
    assert client.post("/api/cam/feeds", json={"cam": cdoc, "tc": "TC9"}).status_code == 400


THREADMILL = {"id": "T7", "name": "Thread mill 4.7", "shape": "threadmill", "d": 4.7, "angle": 60.0, "height": 2.0, "neck": 3.0,
              "neck_length": 15.0, "shank": 6.0, "shank_length": 30.0, "flutes": 3, "feed": 300, "plunge": 100, "rpm": 15000}


def test_tool_library_tapered_threadmill():
    """The standard library (groups, ids unique, every bit valid, the spoilboard tool), the tapered ball nose
    (diameter from tip radius, taper and height; bottom offsets on the ball and the cone), the thread mill profile."""
    from drawgen.cam import tools as TB, feeds as FS
    lib = TB.library()
    groups = {t["group"] for t in lib}
    assert groups == {"Flat end mills", "Ball end mills", "Single flute end mills", "Chamfer mills", "Tapered ball nose", "Thread mills", "Spoilboard"}
    assert len({t["id"] for t in lib}) == len(lib) and all(TB.check(t) for t in lib)
    d_flat = sorted({t["d"] for t in lib if t["group"] == "Flat end mills"})
    assert d_flat == [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0]
    assert {t["flutes"] for t in lib if t["group"] == "Flat end mills"} == {2, 3}
    assert [t["angle"] for t in lib if t["group"] == "Chamfer mills"] == [90.0, 90.0, 60.0, 60.0]
    sb = next(t for t in lib if t["group"] == "Spoilboard")
    assert sb["d"] == 25.0 and sb["rpm"] > 0 and sb["feed"] > 0
    tb = TB.normalize({"id": "x", "shape": "tapered", "corner": 0.5, "angle": 3, "height": 20, "neck": 6, "shank": 6})
    a = math.radians(3)
    assert tb["d"] == pytest.approx(2 * (0.5 * math.cos(a) + (20 - (0.5 - 0.5 * math.sin(a))) * math.tan(a)), abs=1e-3)
    assert TB.bottom_offset(tb, 0.2) == pytest.approx(0.5 - math.sqrt(0.25 - 0.04), abs=1e-9)
    assert TB.bottom_offset(tb, 1.0) == pytest.approx(0.5 - 0.5 * math.sin(a) + (1.0 - 0.5 * math.cos(a)) / math.tan(a), abs=1e-9)
    assert TB.tool_solid(tb, (0, 0, 0)).volume > 0
    assert FS.effective_diameter(tb, 5.0) < tb["d"] and FS.effective_diameter(tb, 0.2) < 1.0
    cut, _ = TB.tool_profile(THREADMILL)
    assert max(r for r, _ in cut) == pytest.approx(2.35) and TB.tool_solid(TB.normalize(THREADMILL), (0, 0, 0)).volume > 0
    with pytest.raises(ValueError):
        TB.tool_profile(dict(THREADMILL, angle=150))


def test_feeds_coating_rigidity_ramp():
    from drawgen.cam import feeds as FS
    mach = {"rpm_min": 1000, "rpm_max": 60000, "rpm_rated": 1000, "power_kw": 50, "feed_max": 1e6}
    em = dict(END_MILL, flutes=3)
    r0 = FS.calc(em, "st_struct", mach, 6, 1)
    r1 = FS.calc(dict(em, coating="altin"), "st_struct", mach, 6, 1)
    assert r1["rpm"] == pytest.approx(r0["rpm"] * 1.4, rel=1e-3) and r1["coating"] == "altin"
    ra = FS.calc(dict(em, coating="altin"), "al_wrought", mach, 6, 1)
    assert ra["vc"] == pytest.approx(300 * 0.8, rel=1e-3)
    r2 = FS.calc(em, "st_struct", dict(mach, rigidity=50), 6, 1)
    assert r2["fz"] == pytest.approx(0.5 * r0["fz"], abs=2e-4) and r2["rigidity"] == 50
    assert r0["ramp"] == r0["feed"] * 1 or r0["ramp"] <= r0["feed"]
    r3 = FS.calc(em, "st_struct", dict(mach, ramp_angle=2), 6, 1)
    r4 = FS.calc(em, "st_struct", dict(mach, ramp_angle=20), 6, 1)
    assert r3["ramp"] == r3["feed"] and r4["ramp"] == r4["plunge"]


def test_step_stock_refresh_machine(client, web, tmp_path):
    """A STEP file as the stock (moved with the placement; relative paths in the STEP folder; a missing file), the
    part state key for the refresh, the machine record saved and refused."""
    import os
    from build123d import Box, Location, Vector, export_step
    from drawgen import cam
    ok(client.put("/api/part/file/stp", json=job_part("stp")))
    path = str(tmp_path / "blank.step")
    export_step(Box(110, 70, 20).moved(Location(Vector(50, 30, 10))), path)
    doc = {"name": "s", "source": {"type": "part", "name": "stp"}, "stock": {"kind": "step", "path": path}, "tools": controllers(), "operations": []}
    su = ok(client.post("/api/cam/setup", json={"cam": doc}))
    assert su["stock_bbox"] == pytest.approx([-5, -5, 0, 105, 65, 20], abs=1e-4) and su["origin"] == pytest.approx([-5, -5, 20], abs=1e-4)
    moved = dict(doc, placement={"pos": [10, 0, 0], "rot": [0, 0, 0]})
    assert ok(client.post("/api/cam/setup", json={"cam": moved}))["stock_bbox"][0] == pytest.approx(5, abs=1e-4)
    assert su["stock_mesh"]["triangles"]
    # stock offsets: turned 90 deg about the part Z axis, then moved by the offset; then the model placement
    off = dict(doc, stock=dict(doc["stock"], rz=90, dx=70, dy=0, dz=1))
    assert ok(client.post("/api/cam/setup", json={"cam": off}))["stock_bbox"] == pytest.approx([5, -5, 1, 75, 105, 21], abs=1e-4)
    offm = dict(off, placement={"pos": [10, 0, 0], "rot": [0, 0, 0]})
    assert ok(client.post("/api/cam/setup", json={"cam": offm}))["stock_bbox"][0] == pytest.approx(15, abs=1e-4)
    doc2 = dict(doc, operations=[{"id": "o1", "name": "Face", "type": "face", "tc": "TC1", "pattern": "zigzag", "stepover_pct": 60, "step_down": 2}])
    j = ok(client.post("/api/cam/run", json={"cam": doc2, "meshes": False}))
    assert j["operations"][0]["ok"] and j["operations"][0]["removed_mm3"] > 1000
    bad = client.post("/api/cam/setup", json={"cam": dict(doc, stock={"kind": "step", "path": str(tmp_path / "none.step")})})
    assert bad.status_code == 400 and "not found" in bad.get_json()["error"]
    # the part state key equals the key of the loaded geometry until the part file changes
    g = ok(client.post("/api/cam/geometry", json={"cam": dict(doc, stock={})}))
    st = ok(client.post("/api/cam/part_state", json={"cam": doc}))
    assert st["key"] and st["key"] == g["part_key"] and g["part_sketches"] == [] or isinstance(g["part_sketches"], list)
    rec = job_part("stp")
    rec["features"][2]["depth"] = 3
    ok(client.put("/api/part/file/stp", json=rec))
    assert ok(client.post("/api/cam/part_state", json={"cam": doc}))["key"] != g["part_key"]
    # the machine
    m = ok(client.get("/api/cam/machine"))
    assert m["travel_x"] > 0 and "tip_top" in m
    m2 = ok(client.put("/api/cam/machine", json=dict(m, travel_x=800)))
    assert m2["travel_x"] == 800 and ok(client.get("/api/cam/machine"))["travel_x"] == 800
    assert client.put("/api/cam/machine", json=dict(m, travel_y=0)).status_code == 400
    assert client.put("/api/cam/machine", json=dict(m, travel_y="x")).status_code == 400


def test_thread_cycles_posts_hop_probe_axismap():
    """Thread milling of the hole (helix of the pitch, the hand and the direction, passes, the ring cut from the
    stock as cut from the part), drilling canned cycles in the LinuxCNC and Mach3 posts (moves in the others), the
    GRBL post (tool change as M0), Hop and Probe items in the posts, the axis map dressup (A words, arcs as lines)."""
    from drawgen import cam
    sh = job_shape()
    k = keys_of(sh)
    bits = BITS + [THREADMILL]
    tcs = controllers() + [cam.controller_defaults(THREADMILL, 7)]
    th = {"id": "t", "name": "Thread", "type": "thread", "tc": "TC7", "faces": [k["hole"]], "pitch": 1.0, "diameter": 7.0, "passes": 2}
    doc = job_doc(sh, ops=[th], tools=tcs)
    o = cam.run(doc, sh, bits)["operations"][0]
    assert o["ok"], o["errors"]
    arcs = [m for m in o["moves"] if m["k"] == "arc"]
    zs = [m["p"][2] for m in arcs]
    assert max(zs) - min(zs) >= 10 - 1e-6 and "cut from the part" in " ".join(o["messages"]) and o["gouge_mm3"] == 0
    hel = [m for m in arcs if abs(math.hypot(m["p"][0] - 30, m["p"][1] - 45) - (3.5 - 2.35)) < 1e-6]
    assert hel and all(not m["cw"] for m in hel)                # right hand, internal, climb: counter-clockwise up
    assert hel[1]["p"][2] > hel[0]["p"][2]
    o2 = cam.run(job_doc(sh, ops=[dict(th, hand="left")], tools=tcs), sh, bits)["operations"][0]
    hel2 = [m for m in o2["moves"] if m["k"] == "arc" and abs(math.hypot(m["p"][0] - 30, m["p"][1] - 45) - 1.15) < 1e-6]
    assert all(not m["cw"] for m in hel2) and hel2[1]["p"][2] < hel2[0]["p"][2]  # left hand, internal, climb: counter-clockwise down
    bad = cam.run(job_doc(sh, ops=[dict(th, diameter=4.0)], tools=tcs), sh, bits)["operations"][0]
    assert not bad["ok"] and "does not fit" in bad["errors"][0]
    # canned cycles
    dr = {"id": "d", "name": "Drill", "type": "drilling", "tc": "TC3", "faces": [k["hole"]], "peck": 3, "dwell": 0, "cycles": True}
    for post, cyc in (("linuxcnc", True), ("mach3", True), ("generic", False), ("estlcam", False), ("grbl", False)):
        d = job_doc(sh, ops=[dr], post=post)
        res = cam.run(d, sh, BITS)
        txt = cam.gcode(d, res, BITS)
        assert ("G83 " in txt and "G80" in txt and "G98" in txt) == cyc, post
        if cyc:
            assert txt.count("G1 ") == 0 and "G43 H3" in txt
    txt = cam.gcode(job_doc(sh, ops=[dict(dr, cycles=False)], post="linuxcnc"), cam.run(job_doc(sh, ops=[dict(dr, cycles=False)], post="linuxcnc"), sh, BITS), BITS)
    assert "G83" not in txt and "G1 " in txt and txt.rstrip().endswith("M2")
    g = cam.gcode(job_doc(sh, ops=[dr], post="grbl"), cam.run(job_doc(sh, ops=[dr], post="grbl"), sh, BITS), BITS)
    assert "M6" not in g and "(tool change: T3" in g and "M0" in g and g.rstrip().endswith("M30")
    # hop and probe
    sup = [{"id": "h", "name": "Hop", "type": "hop", "height": 30}, {"id": "p", "name": "Probe", "type": "probe", "nx": 2, "ny": 2, "depth": 5, "feed": 40, "output": "probe.txt"}]
    for post in ("linuxcnc", "estlcam", "mach3"):
        d = job_doc(sh, ops=sup, post=post)
        res = cam.run(d, sh, BITS)
        assert all(o["ok"] for o in res["operations"])
        t = cam.gcode(d, res, BITS)
        if post == "linuxcnc":
            assert "(PROBEOPEN probe.txt)" in t and t.count("G38.2 Z") == 4 and "F40" in t and "(PROBECLOSE)" in t
        elif post == "mach3":
            assert t.count("G38.2") == 4 and "PROBEOPEN" not in t
        else:
            assert "G38.2" not in t and t.count("not supported") == 4
    assert any("probe" in x["text"].lower() for x in cam.sanity(job_doc(sh, ops=sup), sh, BITS))
    # the axis map: Y written as A at radius 10 mm
    pr = {"id": "pf", "name": "Profile", "type": "profile", "tc": "TC1", "step_down": 5, "extra": 0.2, "dressups": [{"type": "axismap", "axis": "y", "radius": 10}]}
    d = job_doc(sh, ops=[pr], post="generic")
    res = cam.run(d, sh, BITS)
    o = res["operations"][0]
    assert o["ok"], o["errors"]
    assert all(m["k"] != "arc" for m in o["moves"]) and all("a" in m for m in o["moves"] if "p" in m)
    m = next(m for m in o["moves"] if "p" in m)
    assert m["a"] == pytest.approx(m["p"][1] / (2 * math.pi * 10) * 360, abs=1e-3)
    t = cam.gcode(d, res, BITS)
    assert " A" in t and "G2 " not in t and "G3 " not in t


def test_part_sketch_engraving_and_placement_edges(client, web):
    """A sketch of the part on the XZ plane engraved after the part is turned so that the plane faces up (the sketch
    mapped by the placement); refused while the plane is vertical. Placement constraints of an edge and a vertex,
    the drag through the route."""
    from drawgen.cam import placement as PL
    rec = job_part("skp")
    rec["features"].append({"id": "s9", "name": "Mark", "type": "sketch", "plane": "XZ", "offset": 0,
                            "sketch": {"entities": rect(20, 4, 10, 2, 1), "layers": [{"name": "0", "on": True}]}})
    ok(client.put("/api/part/file/skp", json=rec))
    doc = {"name": "e", "source": {"type": "part", "name": "skp"}, "stock": {"kind": "offsets", "zpos": 1}, "tools": controllers(), "operations": [],
           "placement": {"pos": [0, 0, 0], "rot": [0, 0, 0]}}
    g = ok(client.post("/api/cam/geometry", json={"cam": doc}))
    assert "s9" in [s["id"] for s in g["part_sketches"]]
    eng = {"id": "en", "name": "Engrave", "type": "engrave", "tc": "TC5", "sketch": {"part": "skp", "feature": "s9"}, "depth": 0.3}
    j = ok(client.post("/api/cam/run", json={"cam": dict(doc, operations=[eng]), "meshes": False}))
    assert not j["operations"][0]["ok"] and "not horizontal" in j["operations"][0]["errors"][0]
    # turned 90 deg about X: the XZ plane (normal -Y) becomes horizontal
    turned = dict(doc, placement={"pos": [0, 0, 0], "rot": [90, 0, 0]}, operations=[eng])
    j = ok(client.post("/api/cam/run", json={"cam": turned, "meshes": False}))
    o = j["operations"][0]
    assert o["ok"], o["errors"]
    xs = [m["p"][0] for m in o["moves"] if m["k"] == "feed"]
    assert min(xs) == pytest.approx(10, abs=1e-6) and max(xs) == pytest.approx(30, abs=1e-6)
    # an edge parallel to the Y axis and a vertex on XY from the route; the drag
    sg = ok(client.post("/api/cam/placement", json={"cam": doc, "suggest": {"type": "parallel", "edge": [50, 0, 0]}}))
    assert sg["datum"] == "X" and sg["edge"] is not None and sg["ec"] == pytest.approx([50, 0, 0])
    pl = {"pos": [0, 0, 0], "rot": [0, 0, 20], "constraints": [dict(sg, id="e", type="parallel", datum="Y")]}
    r = ok(client.post("/api/cam/placement", json={"cam": dict(doc, placement=pl)}))
    assert not r["unsatisfied"] and abs(abs(r["rot"][2]) - 90) < 1e-3
    sv = ok(client.post("/api/cam/placement", json={"cam": dict(doc, placement={"pos": [0, 0, 5]}), "suggest": {"type": "coincident", "vertex": [0, 0, 5]}}))
    assert sv["datum"] in ("YZ", "XZ") and sv["vc"] == pytest.approx([0, 0, 0])
    pl2 = {"pos": [0, 0, 5], "constraints": [dict(sv, id="v", type="coincident", datum="XY")]}
    r2 = ok(client.post("/api/cam/placement", json={"cam": dict(doc, placement=pl2)}))
    assert r2["pos"][2] == pytest.approx(0, abs=1e-3) and max(abs(v) for v in r2["rot"]) < 0.01
    r3 = ok(client.post("/api/cam/placement", json={"cam": dict(doc, placement=pl2), "drag": {"delta": [5, 0, 7]}}))
    assert r3["pos"][0] == pytest.approx(5, abs=0.05) and r3["pos"][2] == pytest.approx(0, abs=1e-3)
    r4 = ok(client.post("/api/cam/placement", json={"cam": dict(doc, placement={"pos": [1, 2, 3]}), "drag": {"delta": [1, 1, 1]}}))
    assert r4["pos"] == [2, 3, 4]
    assert PL.to_part({"pos": [1, 2, 3], "rot": [0, 0, 90]}, [1, 3, 3]) == pytest.approx([1, 0, 0], abs=1e-9)


def test_finishing_modes():
    """Finishing: a separate finish (own record "<id>:finish" with the finish tool, feed and step down; the stock left
    by the roughing removed by it; a tool change in the G-code; Inspect writes both records), the finish in each level
    with its feed and a spring pass, Off (the stock to leave stays), migration of the older Pocket "finish" and Adaptive
    "finish_profile", the finish controller in the sanity check."""
    from drawgen import cam
    sh = job_shape()
    k = keys_of(sh)
    base = job_doc(sh)
    pre = [base["operations"][0], base["operations"][1]]
    pk = {"id": "pk", "name": "Pocket", "type": "pocket", "tc": "TC1", "faces": [k["floor"]], "pattern": "offset", "stepover_pct": 40, "extra_offset": 0.3,
          "finish_mode": "separate", "finish_tc": "TC6", "finish_feed": 450, "finish_step": 4, "finish_spring": True}
    doc = job_doc(sh, ops=pre + [pk])
    res = cam.run(doc, sh, BITS)
    r1, r2 = res["operations"][2:]
    assert (r1["id"], r1["phase"], r2["id"], r2["phase"], r2["finish_of"]) == ("pk", "rough", "pk:finish", "finish", "pk")
    assert r1["ok"] and r2["ok"], (r1["errors"], r2["errors"])
    assert r1["tool"] == "TC1" and r2["tool"] == "TC6" and r2["feed"] == 450 and r2["name"] == "Pocket (finish)"
    assert r1["remaining_mm3"] > 50 and r2["remaining_mm3"] < 0.2 * r1["remaining_mm3"]
    assert [l["z"] for l in r2["levels"]] == [6.0]                 # finish step down 4 mm: one level from Z 8 to the floor
    feeds = [m for m in r2["moves"] if m["k"] == "feed"]
    assert feeds and all(m["f"] == 450 for m in feeds)
    t = cam.gcode(doc, res, BITS)
    assert "M06 T6" in t and t.index("(pocket: Pocket (finish), tool TC6") > t.index("(pocket: Pocket, tool TC1")
    ins = cam.gcode(doc, res, BITS, only=2)
    assert "Pocket (finish)" in ins and "(pocket: Clear" not in ins
    # the same without the finish: the stock left stays
    off = cam.run(job_doc(sh, ops=pre + [dict(pk, finish_mode="off")]), sh, BITS)["operations"]
    assert len(off) == 3 and off[2]["remaining_mm3"] == pytest.approx(r1["remaining_mm3"], rel=0.05)
    # in each level: the finish loops at the finish feed, a spring pass on the last level
    lv = cam.run(job_doc(sh, ops=pre + [dict(pk, finish_mode="level", finish_spring=False)]), sh, BITS)["operations"][2]
    lv2 = cam.run(job_doc(sh, ops=pre + [dict(pk, finish_mode="level", finish_spring=True)]), sh, BITS)["operations"][2]
    assert lv["ok"] and lv2["ok"] and lv["remaining_mm3"] < 0.2 * r1["remaining_mm3"]
    n1 = sum(1 for m in lv["moves"] if m["k"] == "feed" and m["f"] == 450)
    n2 = sum(1 for m in lv2["moves"] if m["k"] == "feed" and m["f"] == 450)
    assert n1 > 0 and n2 > n1
    # profile: extra offset left by the roughing, the finish pass at the contour
    pr = {"id": "pf", "name": "Profile", "type": "profile", "tc": "TC1", "step_down": 3, "extra": 0.2, "extra_offset": 0.5}
    rr = cam.run(job_doc(sh, ops=[dict(pr, finish_mode="separate", finish_feed=300)]), sh, BITS)["operations"]
    assert [x["id"] for x in rr] == ["pf", "pf:finish"] and all(x["ok"] for x in rr) and rr[1]["gouge_mm3"] < 0.05
    one = cam.run(job_doc(sh, ops=[dict(pr, finish_mode="off")]), sh, BITS)["operations"][0]
    assert rr[1]["removed_mm3"] > 50 and one["removed_mm3"] == pytest.approx(rr[0]["removed_mm3"], rel=1e-3)
    # undercut: the roughing passes, then the pass at 0 with the finish record
    uc = dict(base["operations"][4], finish_mode="separate")
    ru = cam.run(job_doc(sh, ops=pre + [uc]), sh, BITS)["operations"][2:]
    assert [x["ok"] for x in ru] == [True, True] and ru[0]["remaining_mm3"] > 10 and ru[1]["remaining_mm3"] < 1.0
    # migration and the sanity check
    m = cam.migrate({"operations": [{"id": "a", "type": "pocket", "finish": False}, {"id": "b", "type": "adaptive", "finish_profile": True},
                                    {"id": "c", "type": "undercut"}, {"id": "d", "type": "profile"}]})
    assert [o["finish_mode"] for o in m["operations"]] == ["off", "level", "level", "off"]
    txt = [x["text"] for x in cam.sanity(job_doc(sh, ops=[dict(pk, finish_tc="TC9")]), sh, BITS)]
    assert any("finish tool controller TC9" in x for x in txt)
