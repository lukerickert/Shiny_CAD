# -*- coding: utf-8 -*-
"""Part rebuild tests: each feature type is built on a small part and the volume and topology compared with the
values computed by hand."""
import math

import pytest

from conftest import circle, part_rec, plate, rect

BOX = 100.0 * 50.0 * 20.0


def build(p):
    from drawgen import part
    shape, st = part.build(p)
    errs = [s for s in st if s.get("error")]
    assert not errs, errs
    assert shape is not None
    return shape, st


def box_part(extra=(), name="box"):
    return part_rec(name, [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                            "sketch": {"entities": rect(100, 50)}, "depth": 20}] + list(extra))


def vertical_edges(shape):
    from drawgen import part
    return [part.edge_key(e) for e in shape.edges() if abs(e.length - 20) < 1e-6 and abs(part.edge_key(e)["mid"][2] - 10) < 1e-6]


def test_extrude_with_hole():
    shape, _ = build(plate())
    assert shape.volume == pytest.approx(BOX - math.pi * 100 * 20, rel=1e-6)
    assert len(shape.faces()) == 7


def test_cut_through():
    shape, _ = build(box_part([{"id": "f2", "name": "Cut 1", "type": "cut", "plane": "XY", "offset": 0, "through": True,
                                "sketch": {"entities": [circle(50, 25, 10, 1)]}}]))
    assert shape.volume == pytest.approx(BOX - math.pi * 100 * 20, rel=1e-6)


def test_revolve_annulus():
    p = part_rec("ring", [{"id": "f1", "name": "Revolve 1", "type": "revolve", "plane": "XY", "offset": 0, "axis": "v",
                           "angle": 360, "mode": "add", "sketch": {"entities": rect(10, 30, 10, 0)}}])
    shape, _ = build(p)
    assert shape.volume == pytest.approx(math.pi * (20 ** 2 - 10 ** 2) * 30, rel=1e-6)


def test_fillet_vertical_edges():
    base, _ = build(box_part())
    edges = vertical_edges(base)
    assert len(edges) == 4
    shape, _ = build(box_part([{"id": "f2", "name": "Fillet 1", "type": "fillet", "value": 5, "edges": edges}]))
    assert shape.volume == pytest.approx(BOX - 4 * (25 - math.pi * 25 / 4) * 20, rel=1e-6)


def test_chamfer_vertical_edges():
    base, _ = build(box_part())
    shape, _ = build(box_part([{"id": "f2", "name": "Chamfer 1", "type": "chamfer", "value": 2, "edges": vertical_edges(base)}]))
    assert shape.volume == pytest.approx(BOX - 4 * 2 * 20, rel=1e-6)


def hole_feature(fid="f2", x=50.0, y=25.0, **kw):
    f = {"id": fid, "name": "Hole 1", "type": "hole", "plane": "XY", "offset": 20, "dia": 10, "depth": None,
         "sketch": {"entities": [{"id": 1, "t": "point", "x": x, "y": y, "layer": "0"}]}}
    f.update(kw)
    return f


def test_hole_through():
    shape, _ = build(box_part([hole_feature()]))
    assert shape.volume == pytest.approx(BOX - math.pi * 25 * 20, rel=1e-6)


def test_hole_blind():
    shape, _ = build(box_part([hole_feature(depth=8)]))
    assert shape.volume == pytest.approx(BOX - math.pi * 25 * 8, rel=1e-3)     # drill point not modelled: flat bottom


def test_linear_pattern_of_hole():
    shape, _ = build(box_part([hole_feature(x=20), {"id": "f3", "name": "Pattern 1", "type": "pattern", "kind": "linear",
                                                    "features": ["f2"], "count": 3, "step": [20, 0, 0], "count2": 1,
                                                    "step2": [0, 20, 0], "row_offset": 0}]))
    assert shape.volume == pytest.approx(BOX - 3 * math.pi * 25 * 20, rel=1e-6)


def test_shell_open_top():
    shape, _ = build(box_part([{"id": "f2", "name": "Shell 1", "type": "shell", "thickness": 2,
                                "faces": [{"c": [50, 25, 20], "n": [0, 0, 1], "area": 5000}]}]))
    assert shape.volume == pytest.approx(BOX - 96 * 46 * 18, rel=1e-6)


def test_remove_faces_closes_hole():
    """Remove faces (defeature) on the hole face gives the plain box (regression: the feature was not defined)."""
    from drawgen import part
    base, _ = build(plate())
    cyl = [part.face_key(f) for f in base.faces() if f.geom_type.name == "CYLINDER"]
    assert len(cyl) == 1
    p = plate()
    p["features"].append({"id": "f9", "name": "Remove faces 1", "type": "defeature", "faces": cyl, "min_area": 0})
    shape, _ = build(p)
    assert shape.volume == pytest.approx(BOX, rel=1e-6)
    assert len(shape.faces()) == 6


def _faces_of(pred):
    from drawgen import part
    base, _ = build(plate())
    return [part.face_key(f) for f in base.faces() if pred(f)]


PLATE_VOL = BOX - math.pi * 100 * 20


def test_offset_faces_top_and_hole():
    top = _faces_of(lambda f: f.geom_type.name == "PLANE" and abs(f.center().Z - 20) < 1e-6)
    p = plate()
    p["features"].append({"id": "f9", "name": "Offset faces 1", "type": "offset_faces", "faces": top, "distance": 5})
    shape, _ = build(p)
    assert shape.volume == pytest.approx(PLATE_VOL + 5 * (5000 - math.pi * 100), rel=1e-6)
    cyl = _faces_of(lambda f: f.geom_type.name == "CYLINDER")
    p = plate()
    p["features"].append({"id": "f9", "name": "Offset faces 1", "type": "offset_faces", "faces": cyl, "distance": -2})
    shape, _ = build(p)
    assert shape.volume == pytest.approx(BOX - math.pi * 144 * 20, rel=1e-6)


def test_move_faces_planar_and_feature():
    top = _faces_of(lambda f: f.geom_type.name == "PLANE" and abs(f.center().Z - 20) < 1e-6)
    p = plate()
    p["features"].append({"id": "f9", "name": "Move faces 1", "type": "move_faces", "faces": top, "vector": [0, 0, -4]})
    shape, _ = build(p)
    assert shape.volume == pytest.approx(PLATE_VOL - 4 * (5000 - math.pi * 100), rel=1e-6)
    cyl = _faces_of(lambda f: f.geom_type.name == "CYLINDER")
    p = plate()
    p["features"].append({"id": "f9", "name": "Move faces 1", "type": "move_faces", "faces": cyl, "vector": [-30, 5, 0]})
    shape, _ = build(p)
    assert shape.volume == pytest.approx(PLATE_VOL, rel=1e-6)
    c = [f for f in shape.faces() if f.geom_type.name == "CYLINDER"][0].center()
    assert abs(c.Y - 30) < 1e-6 and abs(c.X - 20) < 10 + 1e-6


def test_partition_keeps_volume():
    p = box_part([{"id": "f2", "name": "Partition 1", "type": "split", "method": "principal", "plane": "YZ", "offset": 50}])
    shape, _ = build(p)
    assert len(shape.solids()) == 2
    assert shape.volume == pytest.approx(BOX, rel=1e-6)


def test_suppressed_feature_is_skipped():
    p = box_part([hole_feature()])
    p["features"][-1]["suppressed"] = True
    shape, _ = build(p)
    assert shape.volume == pytest.approx(BOX, rel=1e-6)


def test_failed_feature_reports_error_and_part_still_builds():
    from drawgen import part
    p = box_part([{"id": "f2", "name": "Cut 1", "type": "cut", "plane": "XY", "offset": 0, "depth": 5,
                   "sketch": {"entities": [circle(500, 500, 10, 1)]}}])
    shape, st = part.build(p)
    assert shape is not None and shape.volume == pytest.approx(BOX, rel=1e-6)
    assert any(s.get("error") for s in st)


def test_mesh_round_info():
    """Circular edges and cylindrical faces carry radius and span for the hover text."""
    from build123d import Cylinder, Box, Axis, fillet
    from drawgen import part
    m = part.mesh(Cylinder(10, 50) - Cylinder(3, 50))
    assert sorted({k["round"]["r"] for k in m["edge_keys"] if "round" in k}) == [3.0, 10.0]
    assert all(k["round"]["span"] == 360.0 for k in m["face_keys"] if k and "round" in k)
    b = Box(20, 20, 10)
    m = part.mesh(fillet(b.edges().filter_by(Axis.Z), 3))
    assert {(k["round"]["r"], k["round"]["span"]) for k in m["face_keys"] if k and "round" in k} == {(3.0, 90.0)}
    assert sum(1 for k in m["edge_keys"] if "round" in k) == 8


def _round_top_slot():
    """Block 60 x 20 x 30 with a slot 10 wide through Y, open at the bottom, top at z = 5 with R3 round corners."""
    from build123d import Box, Pos, Axis, fillet
    body = Box(60, 20, 30) - Pos(0, 0, -5) * Box(10, 40, 20)
    edges = [e for e in body.edges().filter_by(Axis.Y) if abs(e.center().Z - 5) < 1e-6 and abs(abs(e.center().X) - 5) < 1e-6]
    return fillet(edges, 3)


def test_move_faces_tangent_slot_top():
    """The flat top of a slot with tangent round corners moved up 2 mm: with the tangent faces the whole top moves
    (slot 10 mm wide x 20 mm deep), without them a notch the width of the flat (4 mm)."""
    from drawgen import part
    s = _round_top_slot()
    top = [f for f in s.faces() if f.geom_type.name == "PLANE" and abs(f.center().Z - 5) < 1e-6]
    assert len(top) == 1
    key = [part.face_key(top[0])]
    r = part._move_faces(s, {"faces": key, "vector": [0, 0, 2]})
    assert r.is_valid and r.volume == pytest.approx(s.volume - 10 * 20 * 2, rel=1e-6)
    assert len(r.faces()) == len(s.faces())
    r = part._move_faces(s, {"faces": key, "vector": [0, 0, 2], "tangent": False})
    assert r.volume == pytest.approx(s.volume - 4 * 20 * 2, rel=1e-6)
    r = part._move_faces(s, {"faces": key, "vector": [0, 0, -2]})
    assert r.volume == pytest.approx(s.volume + 10 * 20 * 2, rel=1e-6)


def test_offset_faces_slot_with_round_top():
    """All faces of the slot (sides, round corners, flat top) offset by -1 mm: the slot grows by about its
    perimeter x depth x 1 mm, and the result is one valid solid."""
    from drawgen import part
    s = _round_top_slot()
    top = [f for f in s.faces() if f.geom_type.name == "PLANE" and abs(f.center().Z - 5) < 1e-6]
    slot = part._tangent_chain(s, top)
    area = sum(f.area for f in slot)
    assert len(slot) == 5
    for d in (-1.0, 1.0):
        r = part._offset_faces(s, {"faces": [part.face_key(top[0])], "distance": d})
        assert r.is_valid and len(r.solids()) == 1
        assert (r.volume - s.volume) == pytest.approx(area * d, rel=0.1)


def test_vertex_point_references():
    """Vertices of the part picked as point references are stored as coordinates: point offset from a vertex,
    midpoint of two vertices, axis through two vertices, plane through a vertex with an axis normal."""
    p = box_part([
        {"id": "p1", "name": "Point 1", "type": "point", "method": "offset", "point_ref": [100.0, 50.0, 20.0], "offset_vec": [0, 0, 5]},
        {"id": "p2", "name": "Point 2", "type": "point", "method": "midpoint", "points_ref": [[0.0, 0.0, 0.0], [100.0, 50.0, 20.0]]},
        {"id": "a1", "name": "Axis 1", "type": "axis", "method": "two_points", "points_ref": [[0.0, 0.0, 0.0], [0.0, 0.0, 20.0]]},
        {"id": "pl1", "name": "Plane 1", "type": "plane", "method": "point_normal", "point_ref": [100.0, 0.0, 0.0], "axis_ref": "a1"}])
    from drawgen import part
    datums = {}
    shape, st = part.build(p, datums=datums)
    errs = [s for s in st if s.get("error")]
    assert not errs, errs
    by = {s["id"]: s for s in st}
    assert by["p1"]["point"] == pytest.approx([100, 50, 25])
    assert by["p2"]["point"] == pytest.approx([50, 25, 10])
    assert by["a1"]["axis"]["o"] == pytest.approx([0, 0, 0]) and by["a1"]["axis"]["d"][2] == pytest.approx(1.0)


def test_place_faces_on_principal_planes():
    """Place: a plate turned and moved (Import-like position) is laid with its top face on XY (part above), a side
    face on XZ and the end face that ends up facing -X on YZ: the bounding box starts at (0, 0, 0)."""
    from drawgen import part as P
    p = plate("pl_place")
    shape, st = P.build(p)
    m = P.mesh(shape)
    keys, fs = m["face_keys"], shape.faces()
    def face(nx, ny, nz):
        for k, fc in zip(keys, fs):
            if P._is_planar(fc):
                n = fc.normal_at(fc.center())
                if abs(n.X - nx) < 1e-6 and abs(n.Y - ny) < 1e-6 and abs(n.Z - nz) < 1e-6:
                    return k
    # moved plate first: offset (37, -12, 5) via a Place with only an offset
    feats = p["features"]
    feats.append({"id": "pz", "type": "place", "offset": [37, -12, 5]})
    shape2, st2 = P.build(p)
    assert not [s for s in st2 if s.get("error")]
    bb = shape2.bounding_box()
    assert [bb.min.X, bb.min.Y, bb.min.Z] == pytest.approx([37, -12, 5], abs=1e-6)
    m2 = P.mesh(shape2)
    k2 = {}
    for k, fc in zip(m2["face_keys"], shape2.faces()):
        if P._is_planar(fc):
            n = fc.normal_at(fc.center())
            k2[(round(n.X), round(n.Y), round(n.Z))] = k
    feats.append({"id": "pl", "type": "place", "face1": k2[(0, 0, 1)], "plane1": "XY", "face2": k2[(0, 1, 0)], "plane2": "XZ",
                  "face3": k2[(-1, 0, 0)], "plane3": "YZ"})
    shape3, st3 = P.build(p)
    assert not [s for s in st3 if s.get("error")], st3
    bb = shape3.bounding_box()
    assert [bb.min.X, bb.min.Y, bb.min.Z] == pytest.approx([0, 0, 0], abs=1e-6)
    assert sorted([bb.size.X, bb.size.Y, bb.size.Z]) == pytest.approx([20, 50, 100], abs=1e-6)
    # rest "centre": only the top face on XY, the other directions centred
    feats[-1] = {"id": "pl", "type": "place", "face1": k2[(0, 0, 1)], "plane1": "XY", "rest": "centre"}
    shape4, st4 = P.build(p)
    bb = shape4.bounding_box()
    assert [bb.min.Z, (bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2] == pytest.approx([0, 0, 0], abs=1e-6)


def test_place_cylinder_axis():
    """Place with a cylindrical face: the hole of the plate (100 x 50 x 20 mm, axis Z through (50, 25)) on the X
    axis, then the end face (normal +X) on XZ: the part turns about X, the hole axis stays on X (Y already set by the
    axis: the face gives the turn only, with a note); a plane given for a cylinder (XY) means the Z axis."""
    from drawgen import part as P
    p = plate("pl_cyl")
    shape, st = P.build(p)
    m = P.mesh(shape)
    keys = m["face_keys"]
    cyl = next(k for k, fc in zip(keys, shape.faces()) if not P._is_planar(fc))
    end = next(k for k, fc in zip(keys, shape.faces()) if P._is_planar(fc) and fc.normal_at(fc.center()).X > 0.9)
    p["features"].append({"id": "pl", "type": "place", "face1": cyl, "plane1": "X", "face2": end, "plane2": "XZ"})
    s2, st2 = P.build(p)
    assert not [x for x in st2 if x.get("error")], st2
    assert "used for the turn" in st2[-1]["note"]
    hole = next(fc for fc in s2.faces() if not P._is_planar(fc))
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    ax = BRepAdaptor_Surface(hole.wrapped).Cylinder().Axis()
    L, D = ax.Location(), ax.Direction()
    assert abs(abs(D.X()) - 1) < 1e-9 and abs(L.Y()) < 1e-6 and abs(L.Z()) < 1e-6
    bb = s2.bounding_box()
    assert [bb.size.X, bb.size.Y, bb.size.Z] == pytest.approx([20, 100, 50], abs=1e-6)
    assert [bb.min.Y, bb.max.Y, bb.min.Z, bb.max.Z] == pytest.approx([-50, 50, -25, 25], abs=1e-6)
    # the end face points -Y (the part on the +Y side of the face plane)
    assert any(P._is_planar(fc) and fc.normal_at(fc.center()).Y < -0.999 and abs(fc.center().Y + 50) < 1e-6 for fc in s2.faces())
    # cylinder on "XY": axis on Z through the origin, the rest centred
    p["features"][-1] = {"id": "pl", "type": "place", "face1": cyl, "plane1": "XY", "rest": "centre"}
    s3, st3 = P.build(p)
    hole = next(fc for fc in s3.faces() if not P._is_planar(fc))
    ax = BRepAdaptor_Surface(hole.wrapped).Cylinder().Axis()
    assert abs(ax.Location().X()) < 1e-6 and abs(ax.Location().Y()) < 1e-6 and abs(abs(ax.Direction().Z()) - 1) < 1e-9
    bb = s3.bounding_box()
    assert (bb.min.Z + bb.max.Z) / 2 == pytest.approx(0, abs=1e-6)


def test_plane_normal_to_sketch_curve_end():
    """Plane normal to a sketched curve: the chain of connected sketch curves nearest the pick point; without t the
    plane is at the chain end nearer the pick point. A point feature on the same curve uses the same rule."""
    from drawgen import part as P
    ents = [{"id": 1, "t": "line", "x1": 0, "y1": 0, "x2": 50, "y2": 0, "layer": "0"},
            {"id": 2, "t": "line", "x1": 50, "y1": 0, "x2": 50, "y2": 30, "layer": "0"},
            {"id": 3, "t": "line", "x1": 100, "y1": 0, "x2": 120, "y2": 0, "layer": "0"}]      # a separate curve
    p = {"name": "skc", "version": 2, "features": [
        {"id": "s1", "name": "Path", "type": "sketch", "plane": "XZ", "offset": 0, "sketch": {"entities": ents, "layers": [{"name": "0", "on": True}]}},
        {"id": "pa", "name": "Plane end", "type": "plane", "method": "edge", "sketch_curve": {"sketch": "s1", "pick": [50, 0, 28]}, "t": None},
        {"id": "pb", "name": "Plane start", "type": "plane", "method": "edge", "sketch_curve": {"sketch": "s1", "pick": [1, 0, 0]}, "t": None},
        {"id": "pc", "name": "Plane other", "type": "plane", "method": "edge", "sketch_curve": {"sketch": "s1", "pick": [119, 0, 0]}, "t": 0.5},
        {"id": "pt", "name": "Point end", "type": "point", "method": "edge", "sketch_curve": {"sketch": "s1", "pick": [50, 0, 29]}}]}
    dz = {}
    shape, st = P.build(p, datums=dz)
    assert not [x for x in st if x.get("error")], st
    # sketch on XZ: sketch x = global X, sketch y = global Z
    assert dz["pa"]["o"] == pytest.approx([50, 0, 30], abs=1e-6)
    assert [abs(v) for v in dz["pa"]["z"]] == pytest.approx([0, 0, 1], abs=1e-6)
    assert dz["pb"]["o"] == pytest.approx([0, 0, 0], abs=1e-6)
    assert [abs(v) for v in dz["pb"]["z"]] == pytest.approx([1, 0, 0], abs=1e-6)
    assert dz["pc"]["o"] == pytest.approx([110, 0, 0], abs=1e-6)
    assert dz["pt"]["o"] == pytest.approx([50, 0, 30], abs=1e-6)
    # a sketch placed on the plane at the curve end builds
    p["features"].append({"id": "s2", "name": "Profile", "type": "sketch", "plane": "datum", "plane_ref": "pa", "offset": 0,
                          "sketch": {"entities": [{"id": 1, "t": "circle", "cx": 0, "cy": 0, "r": 4, "layer": "0"}], "layers": [{"name": "0", "on": True}]}})
    shape, st = P.build(p, datums=dz)
    assert not [x for x in st if x.get("error")], st


def test_fillet_failure_names_edges_and_largest_radius():
    """A failed fillet names the edges that fail alone with their largest radius, or, when each edge works alone,
    the pairs of edges whose fillets overlap and the largest radius for all edges; the status lists them as
    bad_edges (drawn red)."""
    from drawgen import part as P
    pts = [(0, 0), (180, 0), (200, 40), (70, 90), (40, 270), (0, 270)]
    ents = [{"id": i + 1, "t": "line", "x1": pts[i][0], "y1": pts[i][1], "x2": pts[(i + 1) % 6][0], "y2": pts[(i + 1) % 6][1], "layer": "0"} for i in range(6)]
    p = part_rec("fil", [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": ents}, "depth": 25}])
    shape, st = P.build(p)
    refs = []
    for x, y in pts[:3]:
        e = next(e for e in shape.edges() if abs(e.length - 25) < 1e-6 and abs(e.position_at(0.5).X - x) < 1e-6 and abs(e.position_at(0.5).Y - y) < 1e-6)
        m = e.position_at(0.5)
        refs.append({"mid": [m.X, m.Y, m.Z], "len": e.length})
    p["features"].append({"id": "fl", "type": "fillet", "value": 20, "edges": refs})
    s, st = P.build(p)
    assert st[-1]["error"] is None
    p["features"][-1]["value"] = 30
    s, st = P.build(p)
    assert "edges 2 and 3" in st[-1]["error"] and "largest radius for all edges" in st[-1]["error"]
    assert st[-1]["bad_edges"] == refs[1:]
    p["features"][-1]["value"] = 60
    s, st = P.build(p)
    assert "edge 3: largest radius 40.5" in st[-1]["error"] and st[-1]["bad_edges"] == refs[2:]


def test_loft_smooth_sections():
    """Loft surface through polyline approximations of a circle (120 and 150 segments): with Smooth sections one
    smooth face, without it one face per segment; a rectangle keeps its four corners (four faces)."""
    from drawgen import part as P
    def poly(r, n, sx=1.0):
        return {"id": 1, "t": "poly", "closed": True, "layer": "0",
                "pts": [[r * sx * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)] for k in range(n)]}
    def loft(e1, e2, smooth):
        p = {"name": "l", "version": 2, "features": [{"id": "L", "name": "Loft", "type": "surf_loft", "smooth": smooth, "sections": [
            {"plane": "XY", "offset": 0, "sketch": {"entities": e1}}, {"plane": "XY", "offset": 30, "sketch": {"entities": e2}}]}]}
        bodies = {}
        s, st = P.build(p, surfaces=bodies)
        assert not st[-1].get("error"), st
        return bodies["L"]
    b = loft([poly(50, 120)], [poly(70, 150, 1.3)], True)
    assert len(b.faces()) == 1
    # the smooth section lies on the polygon vertices: the bottom edge stays within the polygon sagitta of r = 50
    e = min(b.edges(), key=lambda x: abs(x.center().Z))
    assert all(49.95 < math.hypot(e.position_at(k / 40).X, e.position_at(k / 40).Y) < 50.01 for k in range(41))
    assert len(loft([poly(50, 120)], [poly(70, 120)], False).faces()) == 120
    rect = lambda w: [{"id": i + 1, "t": "line", "layer": "0", "x1": a[0], "y1": a[1], "x2": c[0], "y2": c[1]}
                      for i, (a, c) in enumerate(zip([(0, 0), (w, 0), (w, w), (0, w)], [(w, 0), (w, w), (0, w), (0, 0)]))]
    assert len(loft(rect(40), rect(60), True).faces()) == 4


def test_bridge_surface_between_edges():
    """Bridge surface: ruled surface between an edge of one surface body and an edge of another, ends joined
    corner to corner (the 30 mm gap between two 100 mm wide plates: 3000 mm^2); Flip joins the other ends (the
    lines cross: a different surface)."""
    from drawgen import part as P
    def plate_s(fid, y0, y1):
        return {"id": fid, "name": fid, "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0,
                "sketch": {"entities": rect(100, y1 - y0, 0, y0)}}
    p = part_rec("br", [plate_s("s1", 0, 50), plate_s("s2", 80, 130)])
    bodies = {}
    P.build(p, surfaces=bodies)
    def eref(body, y):
        e = next(e for e in body.edges() if abs(e.center().Y - y) < 1e-6 and abs(e.length - 100) < 1e-6)
        m = e.position_at(0.5)
        return {"mid": [m.X, m.Y, m.Z], "len": e.length}
    sid = [f["id"] for f in p["features"] if f["type"] == "surf_sketch"]
    p["features"].append({"id": "b", "name": "Bridge", "type": "surf_bridge", "edges_a": [eref(bodies[sid[0]], 50)], "edges_b": [eref(bodies[sid[1]], 80)]})
    bodies = {}
    s, st = P.build(p, surfaces=bodies)
    assert not st[-1].get("error"), st[-1]
    assert abs(bodies["b"].area - 3000) < 1e-6
    p["features"][-1]["flip"] = True
    bodies = {}
    s, st = P.build(p, surfaces=bodies)
    assert abs(bodies["b"].area - 3000) > 100                    # crossed lines: a different surface


def test_thicken_sewn_shell_face_by_face():
    """Thicken of a sewn shell that does not offset as a whole (a fin standing on the seam of two plates: three
    faces at one edge): each face is thickened and the pieces fused; the note says so."""
    from drawgen import part as P
    line = [{"id": 1, "t": "line", "x1": 50, "y1": 0, "x2": 50, "y2": 50, "layer": "0"}]
    feats = [{"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(50, 50)}},
             {"id": "b", "name": "B", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(50, 50, 50, 0)}},
             {"id": "c", "name": "Fin", "type": "surf_sketch", "kind": "extrude", "depth": 30, "plane": "XY", "offset": 0, "sketch": {"entities": line}}]
    p = part_rec("thk", feats)
    p["features"].append({"id": "s", "name": "Sew", "type": "surf_sew", "sources": ["a", "b", "c"], "tolerance": 0.01})
    p["features"].append({"id": "t", "name": "Thicken", "type": "thicken", "source": "s", "thickness": 2, "side": "+", "mode": "new"})
    shape, st = P.build(p)
    t = st[-1]
    assert not t.get("error"), st
    assert shape is not None and len(shape.solids()) == 1 and abs(shape.volume - 12800) < 1      # 2 x 5000 + 3000 - 200 overlap
    # (a prismatic shell: the band of the profile; otherwise the pieces fused, with a note)


def test_polygon_profile_extrudes_smooth():
    """A polygon profile (P3G trochoid) and a closed polyline sampling a smooth curve extrude as one periodic
    spline (two side faces plus the caps); a rectangle polyline keeps one face per segment."""
    from drawgen import part as P
    n, k, d1, e = 3, 3, 14, 0.44
    R = d1 / 2
    pts = []
    for i in range(60 * n):
        a = 2 * math.pi * i / (60 * n)
        pts.append([R * math.cos(a) - e * math.cos(a) * math.cos(n * a) - k * e * math.sin(n * a) * math.sin(a),
                    R * math.sin(a) - e * math.sin(a) * math.cos(n * a) + k * e * math.sin(n * a) * math.cos(a)])

    def ext(ent):
        p = P.migrate({"name": "t", "features": [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY",
                                                   "offset": 0, "sketch": {"entities": [ent]}, "depth": 10}]})
        s, st = P.build(p)
        assert st[-1]["error"] is None, st[-1]
        return s

    s = ext({"id": 1, "t": "poly", "closed": True, "layer": "0", "pts": pts, "pprof": {"n": 3}})
    assert len(s.faces()) == 4
    area = abs(sum((pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1]) for i in range(len(pts)))) / 2
    assert s.volume == pytest.approx(area * 10, rel=2e-3)
    assert len(ext({"id": 1, "t": "poly", "closed": True, "layer": "0", "pts": pts}).faces()) == 4
    sq = [[0, 0], [20, 0], [20, 10], [0, 10]]
    s = ext({"id": 1, "t": "poly", "closed": True, "layer": "0", "pts": sq})
    assert len(s.faces()) == 6 and s.volume == pytest.approx(2000, rel=1e-6)


def test_polygon_profile_shell():
    """Shell of an extruded polygon profile (P3G d1 50 mm, e 1.56 mm, 10 mm deep, 1 mm wall, top open): the side
    spline is C2 (knots of multiplicity 1), so the offset succeeds."""
    from drawgen import part as P
    n, k, d1, e = 3, 3, 50, 1.56
    R = d1 / 2
    pts = []
    for i in range(60 * n):
        a = 2 * math.pi * i / (60 * n)
        pts.append([R * math.cos(a) - e * math.cos(a) * math.cos(n * a) - k * e * math.sin(n * a) * math.sin(a),
                    R * math.sin(a) - e * math.sin(a) * math.cos(n * a) + k * e * math.sin(n * a) * math.cos(a)])
    ent = {"id": 1, "t": "poly", "closed": True, "layer": "0", "pts": pts, "pprof": {"n": 3}}
    p = P.migrate({"name": "t", "features": [
        {"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": [ent]}, "depth": 10},
        {"id": "f2", "name": "Shell 1", "type": "shell", "thickness": 1, "faces": [{"c": [0, 0, 10], "n": [0, 0, 1]}]}]})
    s, st = P.build(p)
    assert st[-1]["error"] is None, st[-1]
    area = abs(sum((pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1]) for i in range(len(pts)))) / 2
    per = sum(math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]) for i in range(len(pts)))
    assert s.volume == pytest.approx(area * 1 + (per - math.pi) * 9, rel=5e-3)


def _two_cells():
    """Box 20 x 10 x 10 mm (x -10 to 10) split at x = 0 into two cells that share the face at x = 0."""
    from build123d import Box, Face, Plane, Shape
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from drawgen import surfaces as sfm
    box = Box(20, 10, 10)
    cut = Face.make_rect(30, 30, Plane.YZ)
    a, t = sfm._shape_list(), sfm._shape_list()
    a.Append(box.wrapped)
    t.Append(cut.wrapped)
    op = BRepAlgoAPI_Splitter()
    op.SetArguments(a)
    op.SetTools(t)
    op.Build()
    shape = Shape.cast(op.Shape())
    assert len(shape.solids()) == 2
    return shape


def test_offset_faces_shared_by_two_cells():
    """A face between two cells is offset in the cell it was picked on ("cell"), the other cell is unchanged."""
    from drawgen import part
    shape = _two_cells()
    shared = [f for f in shape.faces() if abs(f.center().X) < 1e-9]
    assert len(shared) == 1
    sols = shape.solids()
    right = next(i for i, s in enumerate(sols) if s.center().X > 0)
    key = dict(part.face_key(shared[0]), cell=right)
    r = part._offset_faces(shape, {"faces": [key], "distance": 2})
    vols = sorted(round(s.volume, 6) for s in r.solids())
    assert vols == [1000.0, 1200.0]
    grown = next(s for s in r.solids() if abs(s.volume - 1200) < 1e-6)
    bb = grown.bounding_box()
    assert bb.min.X == pytest.approx(-2) and bb.max.X == pytest.approx(10)


def test_periodic_span_face_rebuilt_on_short_range():
    """A torus face between the tube circles at v = 0 and v = 270 deg that covers the 270 deg way round is rebuilt on
    the 90 deg range, as two halves (no seam edge)."""
    from build123d import Face
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepTools import BRepTools
    from OCP.Geom import Geom_ToroidalSurface
    from OCP.gp import gp_Ax3
    from drawgen import part
    R, r = 22.0, 0.5
    surf = Geom_ToroidalSurface(gp_Ax3(), R, r)
    long = Face(BRepBuilderAPI_MakeFace(surf, 0, 2 * math.pi, 0, 1.5 * math.pi, 1e-7).Face())
    assert long.area == pytest.approx(2 * math.pi * r * (1.5 * math.pi * R - r), rel=1e-6)    # dA = r (R + r cos v) du dv
    out = part._periodic_span_face(long)
    assert out and len(out) == 2
    assert sum(f.area for f in out) == pytest.approx(2 * math.pi * r * (0.5 * math.pi * R + r), rel=1e-6)
    for f in out:
        v0, v1 = BRepTools.UVBounds_s(f.wrapped)[2:]
        assert v1 - v0 == pytest.approx(0.5 * math.pi)
    short = Face(BRepBuilderAPI_MakeFace(surf, 0, 2 * math.pi, 1.5 * math.pi, 2 * math.pi, 1e-7).Face())
    assert part._periodic_span_face(short) is None


def test_import_clean_up(tmp_path):
    """Import clean-up of a STEP file with a box and a small cube: the cube below the minimum volume is removed, fix
    and merge keep the box valid, the status gives the counts."""
    from build123d import Box, Compound, Location, export_step
    path = str(tmp_path / "two.step")
    export_step(Compound(children=[Box(20, 10, 5), Box(1, 1, 1).moved(Location((30, 0, 0)))]), path)
    p = part_rec("imp", [{"id": "f1", "name": "Import STEP 1", "type": "import", "path": path, "part": None,
                          "clean": {"rebuild": True, "fix": True, "unify": True, "min_volume": 10}}])
    shape, st = build(p)
    assert len(shape.solids()) == 1 and shape.volume == pytest.approx(1000)
    assert st[0]["clean"]["removed"] == 1 and st[0]["clean"]["invalid_after"] == 0
    assert "1 solid(s) below the minimum volume removed" in st[0]["note"]
    p["features"][0]["clean"] = {}
    shape, st = build(p)
    assert len(shape.solids()) == 2 and "clean" not in st[0]


def _two_plates(extra=()):
    """Surface bodies: A on XY (x -20..20, y 0..20), B on XZ (x -20..20, z 0..20): a right angle along the x axis."""
    return part_rec("sf", [{"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0,
                            "sketch": {"entities": rect(40, 20, -20, 0)}},
                           {"id": "b", "name": "B", "type": "surf_sketch", "kind": "planar", "plane": "XZ", "offset": 0,
                            "sketch": {"entities": rect(40, 20, -20, 0)}}] + list(extra))


def test_surface_fillet_between_bodies():
    """R3 rolling-ball fillet between two plates at a right angle: a quarter cylinder of 3 x pi / 2 x 40 mm^2;
    trimmed and sewn: the plates lose 3 mm each."""
    from drawgen import part
    for trim, area, nf in ((False, math.pi / 2 * 3 * 40, 1), (True, 2 * 40 * 17 + math.pi / 2 * 3 * 40, 3)):
        p = _two_plates([{"id": "f", "name": "Surface fillet 1", "type": "surf_fillet", "mode": "bodies", "source_a": "a",
                          "source_b": "b", "radius": 3, "trim": trim}])
        bodies = {}
        shape, st = part.build(p, surfaces=bodies)
        assert st[-1]["error"] is None, st[-1]
        assert len(bodies["f"].faces()) == nf and bodies["f"].area == pytest.approx(area, rel=1e-5)


def test_surface_fillet_between_faces_of_one_body():
    """Surface A and surface B as separate faces of one surface body (two plates sewn into one body with a gap):
    the R3 fillet between the picked faces; without picked faces for both sides the feature asks for them."""
    from drawgen import part
    plates = part_rec("sf1", [
        {"id": "a", "name": "A", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 1)}},
        {"id": "b", "name": "B", "type": "surf_sketch", "kind": "planar", "plane": "XZ", "offset": 0, "sketch": {"entities": rect(40, 20, -20, 1)}},
        {"id": "s", "name": "Sew", "type": "surf_sew", "sources": ["a", "b"], "tolerance": 0.001}])
    fa = {"c": [0.0, 11.0, 0.0], "area": 800.0}
    fb = {"c": [0.0, 0.0, 11.0], "area": 800.0}
    p = dict(plates, features=plates["features"] + [{"id": "f", "name": "Surface fillet 1", "type": "surf_fillet", "mode": "bodies",
                                                    "source_a": "s", "faces_a": [fa], "source_b": "s", "faces_b": [fb], "radius": 3, "trim": False}])
    bodies = {}
    shape, st = part.build(p, surfaces=bodies)
    assert st[-1]["error"] is None, st[-1]
    assert bodies["f"].area == pytest.approx(math.pi / 2 * 3 * 40, rel=1e-5)
    p["features"][-1]["trim"] = True
    bodies = {}
    shape, st = part.build(p, surfaces=bodies)
    assert st[-1]["error"] is None, st[-1]
    # the plates start 1 mm from the corner and are cut 3 mm from it
    assert len(bodies["f"].faces()) == 3 and bodies["f"].area == pytest.approx(2 * 40 * 18 + math.pi / 2 * 3 * 40, rel=1e-5)
    p["features"][-1]["faces_b"] = []
    shape, st = part.build(p, surfaces={})
    assert "one body" in st[-1]["error"]


def test_surface_fillet_plane_and_cylinder():
    """R2 fillet between a floor and a cylinder face (r 10) standing on it, inside (default sides) and outside
    (Flip on the cylinder): fillet areas of the torus quarters."""
    from build123d import Cylinder, Face, Plane, Pos
    from drawgen import surfaces as sfm
    cyl = [f for f in Cylinder(10, 20).moved(Pos(0, 0, 10)).faces() if f.geom_type.name == "CYLINDER"][0]
    bodies = {"a": Face.make_rect(60, 60, Plane.XY), "b": cyl}
    inside = sfm.fillet(None, bodies, {"source_a": "a", "source_b": "b", "radius": 2, "trim": False}, None)
    outside = sfm.fillet(None, bodies, {"source_a": "a", "source_b": "b", "radius": 2, "trim": False, "flip_b": True}, None)
    # torus quarter: area = 2 pi r (R pi / 2 -/+ r) with R the radius of the ball centre circle
    assert inside.area == pytest.approx(2 * math.pi * 2 * (8 * math.pi / 2 + 2), rel=1e-4)
    assert outside.area == pytest.approx(2 * math.pi * 2 * (12 * math.pi / 2 - 2), rel=1e-4)
    trimmed = sfm.fillet(None, bodies, {"source_a": "a", "source_b": "b", "radius": 2, "flip_b": True}, None)
    assert trimmed.area == pytest.approx(3600 - math.pi * 144 + 2 * math.pi * 10 * 18 + outside.area, rel=1e-4)


def test_surface_fillet_edges_of_a_body():
    """Edges mode: the four vertical edges of an open box (shell of 5 faces) rounded with R3."""
    from build123d import Box
    from drawgen import part, surfaces as sfm
    sh = sfm._sew([f for f in Box(30, 20, 10).faces() if f.center().Z < 4.9])
    vert = [part.edge_key(e) for e in sh.edges() if abs(e.length - 10) < 1e-6]
    res = sfm.fillet(None, {"s": sh}, {"mode": "edges", "source": "s", "edges": vert, "radius": 3}, part.find_edges)
    assert len(res.faces()) == 9
    # each corner: two 3 x 10 strips and the 3 x 3 floor squares less the quarter discs replaced by quarter cylinders
    expect = 1600 - 4 * (2 * 3 * 10 - math.pi * 3 / 2 * 10) - 4 * (9 - math.pi * 9 / 4)
    assert res.area == pytest.approx(expect, rel=1e-4)


def test_spline_end_conditions_profile():
    """Profile with a spline whose ends are tangent and curvature continuous (d0, k0 = 0, d1, k1 = 0) to two lines:
    the spline edge starts along +x with zero curvature, and the extruded volume matches the sampled profile."""
    from drawgen import part as P
    from drawgen.sketch import spline_pts_e, _spline_solve, spline_ends, spline_at
    sp = {"id": 2, "t": "spline", "layer": "0", "closed": False, "pts": [[20, 0], [30, 10], [20, 20]],
          "d0": [1, 0], "k0": 0.0, "d1": [-1, 0], "k1": 0.0}
    ents = [{"id": 1, "t": "line", "layer": "0", "x1": 0, "y1": 0, "x2": 20, "y2": 0}, sp,
            {"id": 3, "t": "line", "layer": "0", "x1": 20, "y1": 20, "x2": 0, "y2": 20},
            {"id": 4, "t": "line", "layer": "0", "x1": 0, "y1": 20, "x2": 0, "y2": 0}]
    S = _spline_solve(sp["pts"], False, spline_ends(sp))
    assert len(S[0]) == 5 and S[6] == [2, 2]
    for t, q in ((0, (20, 0)), (1, (30, 10)), (2, (20, 20))):
        assert spline_at(S, t) == pytest.approx(q, abs=1e-9)
    p = P.migrate({"name": "t", "features": [
        {"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": ents}, "depth": 10}]})
    s, st = P.build(p)
    assert st[-1]["error"] is None, st[-1]
    poly = [(0, 0)] + spline_pts_e(sp, 400) + [(0, 20)]
    area = abs(sum(poly[i - 1][0] * poly[i][1] - poly[i][0] * poly[i - 1][1] for i in range(len(poly)))) / 2
    assert s.volume == pytest.approx(area * 10, rel=1e-4)
    # the spline edge on the bottom face: tangent +x and curvature 0 at (20, 0)
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepLProp import BRepLProp_CLProps
    from OCP.gp import gp_Dir
    edge = next(e for e in s.edges() if e.geom_type.name != "LINE" and abs(e.center().Z) < 1e-6)
    ad = BRepAdaptor_Curve(edge.wrapped)
    for u in (ad.FirstParameter(), ad.LastParameter()):
        pr = BRepLProp_CLProps(ad, u, 2, 1e-7)
        pt = pr.Value()
        if abs(pt.X() - 20) < 1e-6 and abs(pt.Y()) < 1e-6:
            d = gp_Dir()
            pr.Tangent(d)
            assert abs(abs(d.X()) - 1) < 1e-6 and pr.Curvature() < 1e-6
            break
    else:
        raise AssertionError("spline edge end at (20, 0) not found")


def test_pattern_bodies():
    """Pattern of a body: a 20 x 10 x 5 mm block copied twice 30 mm along x as new solids (3 solids, 3000 mm^3)."""
    from drawgen import part as P
    sq = [{"id": i, "t": "line", "layer": "0", "x1": a, "y1": b, "x2": c, "y2": d}
          for i, (a, b, c, d) in enumerate([(0, 0, 20, 0), (20, 0, 20, 10), (20, 10, 0, 10), (0, 10, 0, 0)])]
    p = P.migrate({"name": "t", "features": [
        {"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": sq}, "depth": 5},
        {"id": "f2", "name": "Pattern 1", "type": "pattern", "kind": "linear", "features": [], "bodies": [{"solid": 0}], "count": 3, "step": [30, 0, 0]}]})
    s, st = P.build(p)
    assert st[-1]["error"] is None and st[-1]["solids_before"] == 1, st[-1]
    assert len(s.solids()) == 3 and s.volume == pytest.approx(3000, rel=1e-9)
    xs = sorted(round(so.center().X, 6) for so in s.solids())
    assert xs == [10, 40, 70]


def test_extrude_cut_bodies():
    """Extrude and Cut acting on chosen solids: two 20 x 10 x 5 mm blocks (the second a new body at x 30 to 50); a
    through cut removing z 3 to 5 mm across both with bodies [1] cuts only the second block; an extrude overlapping both with
    bodies [0] is fused with the first block only (the solids stay separate)."""
    from drawgen import part as P

    def rect(x0, y0, x1, y1):
        return [{"id": i, "t": "line", "layer": "0", "x1": a, "y1": b, "x2": c, "y2": d}
                for i, (a, b, c, d) in enumerate([(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)])]
    base = [
        {"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": rect(0, 0, 20, 10)}, "depth": 5},
        {"id": "f2", "name": "Extrude 2", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": rect(30, 0, 50, 10)}, "depth": 5, "new_body": True}]
    cut = {"id": "f3", "name": "Cut 1", "type": "cut", "plane": "XZ", "offset": 0, "sketch": {"entities": rect(-10, 3, 60, 7)}, "through": True, "bodies": [1]}
    import copy
    s, st = P.build(P.migrate({"name": "t", "features": copy.deepcopy(base) + [cut]}))
    assert st[-1]["error"] is None, st[-1]
    vols = sorted(round(so.volume, 6) for so in s.solids())
    assert vols == [600, 1000], vols   # the second block loses 20 x 10 x 2 mm
    add = {"id": "f3", "name": "Extrude 3", "type": "extrude", "plane": "XY", "offset": 5, "sketch": {"entities": rect(10, 0, 40, 10)}, "depth": 2, "bodies": [0]}
    s, st = P.build(P.migrate({"name": "t", "features": copy.deepcopy(base) + [add]}))
    assert st[-1]["error"] is None, st[-1]
    vols = sorted(round(so.volume, 6) for so in s.solids())
    assert len(vols) == 2 and vols == [1000, 1000 + 30 * 10 * 2], vols


def test_copy_and_delete_body(tmp_path):
    """Copy body: a copy of the solid moved by the vector is a new solid; Delete body removes the original. A rough STL
    mesh body is copied as a surface body of the copy feature and removed by Delete body."""
    from build123d import Box, export_stl
    from drawgen import part
    stl = str(tmp_path / "b.stl")
    export_stl(Box(10, 10, 10), stl)
    p = plate("cd", 100.0, 50.0, 20.0, 10.0)
    feats = p["features"]
    feats.append({"id": "c1", "name": "Copy body 1", "type": "body_copy", "bodies": [0], "move": [0, 0, 30]})
    shape, st = part.build(part.migrate(p))
    assert len(shape.solids()) == 2 and abs(shape.volume - 2 * (100 * 50 * 20 - math.pi * 100 * 20)) < 1
    feats.append({"id": "d1", "name": "Delete body 1", "type": "body_delete", "bodies": [{"solid": 0}]})
    shape, st = part.build(part.migrate(p))
    assert len(shape.solids()) == 1 and abs(shape.bounding_box().min.Z - 30) < 1e-6
    feats.append({"id": "m1", "name": "Import geometry 2", "type": "import", "path": stl, "stl": {"mode": "rough"}})
    feats.append({"id": "c2", "name": "Copy body 2", "type": "body_copy", "surfaces": ["m1"], "move": [50, 0, 0]})
    bodies = {}
    shape, st = part.build(part.migrate(p), surfaces=bodies)
    assert set(bodies) >= {"m1", "c2"} and abs(bodies["c2"].bounding_box().min.X - bodies["m1"].bounding_box().min.X - 50) < 1e-6
    sm = next(s for s in st if s["id"] == "m1")
    assert sm["mesh"] and sm["faces"] == 12 and sm["error"] is None
    feats.append({"id": "d2", "name": "Delete body 2", "type": "body_delete", "surfaces": ["m1", "c2"], "bodies": [0]})
    bodies = {}
    shape, st = part.build(part.migrate(p), surfaces=bodies)
    assert shape is None and "m1" not in bodies and "c2" not in bodies
    bad = dict(feats[-1], id="d3", surfaces=["nope"], bodies=[])
    feats.append(bad)
    shape, st = part.build(part.migrate(p))
    assert "not found" in st[-1]["error"]


def test_scale_body():
    """Scale body: uniform factor about the origin, the centre of mass, the bounding box centre and a point feature;
    non-uniform factors; Copy keeps the original; a surface body is scaled in place; factors <= 0 are rejected."""
    from drawgen import part
    V = 100 * 50 * 20 - math.pi * 100 * 20

    def run(**kw):
        p = plate("sc", 100.0, 50.0, 20.0, 10.0)
        p["features"].append(dict({"id": "s1", "name": "Scale body 1", "type": "body_scale", "bodies": [0]}, **kw))
        return part.build(part.migrate(p))

    shape, st = run(factor=2)
    assert st[-1]["error"] is None, st[-1]
    bb0 = run(factor=1)[0].bounding_box()
    bb = shape.bounding_box()
    assert abs(shape.volume - 8 * V) < 1e-3 * V
    assert abs(bb.min.X - 2 * bb0.min.X) < 1e-6 and abs(bb.max.Z - 2 * bb0.max.Z) < 1e-6
    c0 = [(bb0.min.X + bb0.max.X) / 2, (bb0.min.Y + bb0.max.Y) / 2, (bb0.min.Z + bb0.max.Z) / 2]
    shape, st = run(factor=0.5, about="bbox")
    bb = shape.bounding_box()
    assert abs((bb.min.X + bb.max.X) / 2 - c0[0]) < 1e-6 and abs(bb.max.X - bb.min.X - 50) < 1e-6
    shape, st = run(factor=3, about="centroid")
    assert abs(shape.volume - 27 * V) < 1e-3 * 27 * V and st[-1]["error"] is None
    p = plate("sc", 100.0, 50.0, 20.0, 10.0)
    p["features"].append({"id": "pt", "name": "Point 1", "type": "point", "method": "coords", "point": [10, 0, 0]})
    p["features"].append({"id": "s1", "name": "Scale body 1", "type": "body_scale", "bodies": [0], "factor": 2,
                          "about": "point", "point_ref": "pt"})
    shape, st = part.build(part.migrate(p))
    assert st[-1]["error"] is None and st[-1]["centre"] == [10, 0, 0], st[-1]
    assert abs(shape.bounding_box().min.X - (10 + 2 * (bb0.min.X - 10))) < 1e-6
    shape, st = run(uniform=False, factors=[1, 2, 0.5])
    bb = shape.bounding_box()
    assert st[-1]["error"] is None, st[-1]
    assert abs(shape.volume - V) < 1e-3 * V and abs(bb.max.Y - bb.min.Y - 100) < 1e-6 and abs(bb.max.Z - bb.min.Z - 10) < 1e-6
    assert shape.is_valid
    shape, st = run(factor=2, copy=True)
    assert len(shape.solids()) == 2 and abs(shape.volume - 9 * V) < 1e-3 * V
    shape, st = run(factor=0)
    assert "greater than 0" in st[-1]["error"]
    p = plate("sc", 100.0, 50.0, 20.0, 10.0)
    sh, _ = part.build(part.migrate(p))
    top = [fc for fc in sh.faces() if abs(fc.center().Z - bb0.max.Z) < 1e-6]
    p["features"].append({"id": "e1", "name": "Extract 1", "type": "surf_extract", "faces": [part.face_key(fc) for fc in top], "offset": 0})
    p["features"].append({"id": "s1", "name": "Scale body 1", "type": "body_scale", "surfaces": ["e1"], "factor": 2})
    bodies = {}
    shape, st = part.build(part.migrate(p), surfaces=bodies)
    assert st[-1]["error"] is None, st[-1]
    assert abs(bodies["e1"].bounding_box().max.Z - 2 * bb0.max.Z) < 1e-6
    assert abs(bodies["e1"].area - 4 * sum(fc.area for fc in top)) < 1e-3
    assert abs(shape.volume - V) < 1e-3 * V


def test_rough_mesh_section_without_projection(tmp_path):
    """A sketch through a rough mesh body gets its section as reference geometry and no projected triangle edges."""
    from build123d import Cylinder, export_stl
    from drawgen import part
    stl = str(tmp_path / "c.stl")
    export_stl(Cylinder(10, 20), stl, tolerance=0.01, angular_tolerance=0.1)
    p = {"name": "rm", "version": 2, "features": [
        {"id": "m1", "name": "Import geometry 1", "type": "import", "path": stl, "stl": {"mode": "rough"}},
        {"id": "s1", "name": "Sketch 1", "type": "sketch", "plane": "XY", "offset": 0, "sketch": {"entities": []}}]}
    p = part.migrate(p)
    bodies, datums = {}, {}
    shape, st = part.build(p, upto=1, surfaces=bodies, datums=datums)
    f = part.normalize(p)[1]
    part.resolve_plane(f, shape, bodies, datums)
    refs = part.section_refs(shape, f, datums, bodies)
    assert any(r.get("kind") == "section" for r in refs)
    assert not any(r.get("kind") in ("proj", "hidden") for r in refs)


def test_inspect_edges_where_cells_meet():
    """Inspect of a part of 4 cells (two partitions): the edges shared by the cells are listed as edges where cells
    meet, not as non-manifold edges; Boolean union of the cells and Merge faces give one solid of 6 faces."""
    from drawgen import part, surfaces as sfm
    p = plate("cells", 100.0, 50.0, 20.0, 0)
    p["features"] += [{"id": "s1", "name": "Partition 1", "type": "split", "method": "principal", "plane": "YZ", "offset": 50},
                      {"id": "s2", "name": "Partition 2", "type": "split", "method": "principal", "plane": "XZ", "offset": 25}]
    shape, st = part.build(part.migrate(p))
    assert len(shape.solids()) == 4
    r = sfm.inspect(shape)
    assert r["summary"]["nonmanifold"] == 0 and r["summary"]["cell_edges"] > 0 and r["summary"]["cells"] == 4
    assert all(i["kind"] == "celledge" for i in r["issues"])
    p["features"] += [{"id": "b1", "name": "Boolean 1", "type": "boolean", "op": "union", "targets": [0, 1, 2, 3], "tools": []},
                      {"id": "u1", "name": "Merge faces 1", "type": "unify", "faces": True, "edges": True, "angle": 0}]
    shape, st = part.build(part.migrate(p))
    r = sfm.inspect(shape)
    assert len(shape.solids()) == 1 and len(shape.faces()) == 6 and not r["issues"]


def test_expand_faces_tangent_and_connected():
    """Faces grown from the top of a plate with filleted top edges: tangent: the top, the 4 fillets and the 4 sides
    (tangent to the fillets), not the bottom; connected: all 10 faces; a face of a surface body grows on that body."""
    import copy
    from drawgen import part
    p = plate("fx", 40.0, 20.0, 10.0, 0)
    sh, st = part.build(copy.deepcopy(p))
    top = [f for f in sh.faces() if abs(f.center().Z - 10) < 1e-6][0]
    p["features"].append({"id": "f9", "name": "Fillet 1", "type": "fillet", "edges": [part.edge_key(e) for e in top.edges()], "value": 2})
    sh, st = part.build(copy.deepcopy(p))
    top = [f for f in sh.faces() if abs(f.center().Z - 10) < 1e-6][0]
    t = part.expand_faces(sh, part.face_key(top), "tangent")
    assert len(t) == 9 and not any(abs(k["c"][2]) < 1e-6 for k in t)
    assert len(part.expand_faces(sh, part.face_key(top), "connected")) == 10
    p["features"].append({"id": "x1", "name": "Extract surface 1", "type": "surf_extract", "faces": t, "offset": 0})
    bodies = {}
    sh, st = part.build(copy.deepcopy(p), surfaces=bodies)
    body = bodies["x1"]
    side = [f for f in body.faces() if f.geom_type.name == "PLANE" and abs(f.normal_at().Z) < 1e-6][0]
    assert len(part.expand_faces(body, part.face_key(side), "connected")) == 9


def test_thicken_inside_corners_trimmed():
    """Thicken of an open surface with corners (an extruded polyline): the offset faces are trimmed where they
    meet (2D offset of the profile, intersection join): 3 + 3 side faces, two end faces, top and bottom, and the volume of the 2D offset profile x height."""
    from build123d import Wire, Polyline, Face, Kind, Side
    from drawgen import part as P
    pts = [(0, 0), (40, 0), (60, 30), (100, 30)]
    ents = [{"id": i + 1, "t": "line", "x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1], "layer": "0"} for i, (a, b) in enumerate(zip(pts, pts[1:]))]
    for side, sd in (("+", Side.LEFT), ("-", Side.RIGHT)):
        p = part_rec("thc", [{"id": "c", "name": "Wall", "type": "surf_sketch", "kind": "extrude", "depth": 20, "plane": "XY",
                              "offset": 0, "sketch": {"entities": ents}},
                             {"id": "t", "name": "Thicken", "type": "thicken", "source": "c", "thickness": 3, "side": side, "mode": "new"}])
        shape, st = P.build(p)
        assert not st[-1].get("error"), st
        assert len(shape.solids()) == 1 and len(shape.faces()) in (10, 14), (side, len(shape.faces()))
        vols = [Face(Wire(Polyline(*pts).edges()).offset_2d(3, kind=Kind.INTERSECTION, side=s)).area * 20 for s in (Side.LEFT, Side.RIGHT)]
        assert min(abs(shape.volume - v) for v in vols) < 1e-3, (shape.volume, vols)
        assert "simple offset" not in (st[-1].get("note") or "")


def test_fillet_edge_of_one_cell():
    """Fillet in a part of two solids side by side: the picked edge at the place where both solids have an edge is
    rounded only in the solid it was picked on ("cell" of the edge reference); the other solid is unchanged."""
    from drawgen import part as P
    ext = lambda i, x, nb: {"id": "e%d" % i, "name": "Extrude %d" % i, "type": "extrude", "plane": "XY", "offset": 0,
                            "depth": 10, "direction": "normal", "new_body": nb, "sketch": {"entities": rect(10, 10, x, 0)}}
    base = lambda: [ext(1, 0, False), ext(2, 10, True)]
    shape, st = P.build(part_rec("cf", base()))
    assert len(shape.solids()) == 2
    v = [so.volume for so in shape.solids()]
    cut = 1 * 1 * 10 * (1 - math.pi / 4)                     # fillet R1 of a 10 mm long edge
    for cell in (0, 1):
        x = 10.0
        f = {"id": "fl", "name": "Fillet 1", "type": "fillet", "value": 1, "edges": [{"mid": [x, 0, 5], "len": 10, "cell": cell}]}
        shape, st = P.build(part_rec("cf", base() + [f]))
        assert not st[-1].get("error"), st
        sols = list(shape.solids())
        assert len(sols) == 2
        dv = [v[i] - sols[i].volume for i in range(2)]
        assert abs(dv[cell] - cut) < 1e-3 and abs(dv[1 - cell]) < 1e-6, (cell, dv)


def test_remove_tiny_face_next_to_extruded_spline():
    """Remove faces of a 0.01 mm round between an extruded sketch spline and a planar face: the spline face is on
    an extrusion surface, which the defeaturing does not extend; the removal runs on the solid with that surface
    converted to a B-spline surface and the round is gone."""
    from drawgen import part as P
    sp = {"id": 2, "t": "spline", "layer": "0", "closed": False, "pts": [[20, 0], [30, 10], [20.01, 20]]}
    ents = [{"id": 1, "t": "line", "layer": "0", "x1": 0, "y1": 0, "x2": 20, "y2": 0}, sp,
            {"id": 3, "t": "arc", "layer": "0", "cx": 20, "cy": 20, "r": 0.01, "a0": 0, "a1": 90},
            {"id": 4, "t": "line", "layer": "0", "x1": 20, "y1": 20.01, "x2": 0, "y2": 20.01},
            {"id": 5, "t": "line", "layer": "0", "x1": 0, "y1": 20.01, "x2": 0, "y2": 0}]
    feats = [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": ents}, "depth": 10}]
    s, st = P.build(P.migrate({"name": "t", "features": [dict(f) for f in feats]}))
    assert st[-1]["error"] is None, st
    tiny = [fc for fc in s.faces() if fc.geom_type.name == "CYLINDER"]
    assert len(tiny) == 1 and tiny[0].area < 0.2
    c = tiny[0].center()
    feats2 = [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": ents}, "depth": 10},
              {"id": "rf", "name": "Remove faces 1", "type": "defeature", "faces": [{"c": [c.X, c.Y, c.Z], "n": [0, 0, 0], "area": tiny[0].area}]}]
    s2, st2 = P.build(P.migrate({"name": "t", "features": feats2}))
    assert st2[-1]["error"] is None, st2
    assert len(s2.faces()) == len(s.faces()) - 1 and not [fc for fc in s2.faces() if fc.geom_type.name == "CYLINDER"]
    assert s2.is_valid and abs(s2.volume - s.volume) < 0.01


def test_extend_extruded_spline_surface_across_edges():
    """Extend surface of an extruded sketch spline (extrusion surface): across a straight end edge and across the
    curved edge, the strip is built on the surface extended as a B-spline surface and sewn to the face."""
    from drawgen import part as P
    sp = {"id": 1, "t": "spline", "layer": "0", "closed": False, "pts": [[0, 0], [10, 4], [20, 0]]}
    base = lambda: [{"id": "s", "name": "Wall", "type": "surf_sketch", "kind": "extrude", "depth": 10, "plane": "XY", "offset": 0,
                     "sketch": {"entities": [dict(sp)]}}]
    bodies = {}
    P.build(P.migrate({"name": "t", "features": base()}), surfaces=bodies)
    face = bodies["s"].faces()[0]
    a0 = face.area
    for e in face.edges():
        m = e.position_at(0.5)
        ext = {"id": "x", "name": "Extend", "type": "surf_extend", "source": "s", "edges": [{"mid": [m.X, m.Y, m.Z], "len": e.length}],
               "mode": "edges", "distance": 5, "tolerance": 0.01}
        bodies = {}
        s, st = P.build(P.migrate({"name": "t", "features": base() + [ext]}), surfaces=bodies)
        assert not st[-1].get("error"), (e.geom_type.name, st[-1])
        b = bodies["x"]
        expect = a0 + 5 * e.length                              # strip of the edge length x 5 mm (curvature: approximately)
        assert abs(b.area - expect) < 0.02 * expect, (e.geom_type.name, b.area, expect)
        assert len(b.shells()) == 1


def test_fillet_edge_ending_on_round():
    """Fillet R0.2 of the edge where a round of R0.2 (tangent to one side) meets the other side at 20 deg: the
    fillet alone fails; the round is removed (its neighbours extended to their corner) and the corner is filleted
    with R0.2; the result line says so."""
    from drawgen import part as P
    px, py = 10 + 0.2 * math.cos(math.radians(-30)), 0.2 + 0.2 * math.sin(math.radians(-30))
    qx, qy = px + 5 * math.cos(math.radians(80)), py + 5 * math.sin(math.radians(80))
    ents = [{"id": 1, "t": "line", "layer": "0", "x1": 0, "y1": 0, "x2": 10, "y2": 0},
            {"id": 2, "t": "arc", "layer": "0", "cx": 10, "cy": 0.2, "r": 0.2, "a0": -90, "a1": -30},
            {"id": 3, "t": "line", "layer": "0", "x1": px, "y1": py, "x2": qx, "y2": qy},
            {"id": 4, "t": "line", "layer": "0", "x1": qx, "y1": qy, "x2": 0, "y2": qy},
            {"id": 5, "t": "line", "layer": "0", "x1": 0, "y1": qy, "x2": 0, "y2": 0}]
    ext = lambda: {"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": ents}, "depth": 2}
    s0, st0 = P.build(P.migrate({"name": "t", "features": [ext()]}))
    assert st0[-1]["error"] is None, st0
    fl = {"id": "fl", "name": "Fillet 1", "type": "fillet", "value": 0.2, "edges": [{"mid": [px, py, 1], "len": 2}]}
    assert P._round_edges(s0, "fillet", 0.2, P.find_edges(s0, fl["edges"])) is None
    s, st = P.build(P.migrate({"name": "t", "features": [ext(), fl]}))
    assert st[-1]["error"] is None, st[-1]
    assert "round(s) of R0.2 mm" in st[-1].get("note", "")
    cyl = [fc for fc in s.faces() if fc.geom_type.name == "CYLINDER"]
    assert len(cyl) == 1 and s.is_valid and len(s.faces()) == len(s0.faces())
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    assert abs(BRepAdaptor_Surface(cyl[0].wrapped, True).Cylinder().Radius() - 0.2) < 1e-6


def test_thicken_prismatic_surface_with_small_rounds():
    """Thicken by 0.5 mm of an extruded profile with a round of R0.2: on the side where the round is concave the
    offset faces cannot follow the round (radius smaller than the thickness); the profile is offset in its plane
    with intersected corners, so the solid has a sharp outer corner there (one cylindrical face, the round
    itself) and on the other side an outer round of R0.7."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from drawgen import part as P
    ents = [{"id": 1, "t": "line", "layer": "0", "x1": 0, "y1": 10, "x2": 0, "y2": 0.2},
            {"id": 2, "t": "arc", "layer": "0", "cx": 0.2, "cy": 0.2, "r": 0.2, "a0": 180, "a1": 270},
            {"id": 3, "t": "line", "layer": "0", "x1": 0.2, "y1": 0, "x2": 10, "y2": 0}]
    radii = {}
    for side in ("+", "-"):
        feats = [{"id": "c", "name": "Wall", "type": "surf_sketch", "kind": "extrude", "depth": 2, "plane": "XY", "offset": 0,
                  "sketch": {"entities": [dict(e) for e in ents]}},
                 {"id": "t", "name": "Thicken", "type": "thicken", "source": "c", "thickness": 0.5, "side": side, "mode": "new"}]
        shape, st = P.build(part_rec("thr", feats))
        assert not st[-1].get("error"), st
        assert "simple offset" not in (st[-1].get("note") or "")
        assert len(shape.solids()) == 1 and shape.is_valid
        radii[side] = sorted(round(BRepAdaptor_Surface(fc.wrapped, True).Cylinder().Radius(), 6)
                             for fc in shape.faces() if fc.geom_type.name == "CYLINDER")
        # band: two legs of 9.8 mm, the corner region within 2 % (volume = band area x 2 mm)
        assert abs(shape.volume - 2 * 0.5 * (9.8 + 9.8 + 0.2 * math.pi / 2)) < 0.03 * shape.volume, (side, shape.volume)
    assert sorted([radii["+"], radii["-"]]) == [[0.2], [0.2, 0.7]], radii


def test_fillet_result_fixed_by_shapefix():
    """Fillet R0.2 of the corner edge between two B-spline faces of a solid (tests/data/fillet_bspline_corner.brep.gz,
    a cell of an imported part after Remove faces): OpenCascade builds the fillet with one face it checks as
    invalid; ShapeFix repairs it and the fillet is kept (valid solid, small volume change)."""
    import gzip
    import os
    import tempfile
    from build123d import Shape, Vector
    from OCP.BRepTools import BRepTools
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Shape
    from drawgen import part as P
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fillet_bspline_corner.brep.gz")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "s.brep")
        with gzip.open(src, "rb") as fi, open(p, "wb") as fo:
            fo.write(fi.read())
        sh = TopoDS_Shape()
        BRepTools.Read_s(sh, p, BRep_Builder())
    so = Shape.cast(sh)
    c = Vector(-0.272337, 7.70701, 2.3)
    e = min(so.edges(), key=lambda q: (q.center() - c).length)
    assert (e.center() - c).length < 1e-4 and abs(e.length - 2) < 1e-6
    new = P._round_edges(so, "fillet", 0.2, [e])
    assert new is not None and new.is_valid
    assert len(new.faces()) == len(so.faces()) + 1 and 0 < new.volume - so.volume < 0.02


def test_build_cache_prefix_state():
    """A rebuild after a change of the last feature starts from the cached state before it (same result as a build
    without the cache); a change of an earlier feature builds again from there."""
    import copy
    from drawgen import part as P
    p = plate("bc", 40.0, 20.0, 10.0, 5.0)
    sh, st = P.build(copy.deepcopy(p))
    top = [f for f in sh.faces() if abs(f.center().Z - 10) < 1e-6][0]
    p["features"].append({"id": "f9", "name": "Fillet 1", "type": "fillet", "edges": [P.edge_key(e) for e in top.edges()][:4], "value": 1})
    vols = {}
    for depth in (10.0, 12.0):
        for r in (1.0, 2.0, 1.0):
            q = copy.deepcopy(p)
            next(f for f in q["features"] if f["type"] == "extrude")["depth"] = depth
            q["features"][-1]["value"] = r
            s1, st1 = P.build(copy.deepcopy(q))
            P._BUILD_CACHE.clear()
            del P._BUILD_CACHE_ORDER[:]
            s2, st2 = P.build(copy.deepcopy(q))
            assert abs(s1.volume - s2.volume) < 1e-6 and [x.get("error") for x in st1] == [x.get("error") for x in st2]
            vols[(depth, r)] = s1.volume
    assert vols[(12.0, 1.0)] > vols[(10.0, 1.0)] and vols[(10.0, 2.0)] < vols[(10.0, 1.0)]


def test_thicken_prismatic_chain_with_spline_and_rounds():
    """Thicken by 0.5 mm of extruded walls (lines, a spline, rounds of R0.2) as an open chain and as a closed loop,
    to both sides: the profile band is built from the regions swept by the edge normals and the corner mitres; one
    valid solid, no simple offset, volume within 8 % of length x thickness x height (corners)."""
    from drawgen import part as P
    sp = {"id": 2, "t": "spline", "layer": "0", "closed": False, "pts": [[10, 0], [14, 3], [15, 8]]}
    loop = [{"id": 1, "t": "line", "layer": "0", "x1": 0, "y1": 0, "x2": 10, "y2": 0}, sp,
            {"id": 3, "t": "line", "layer": "0", "x1": 15, "y1": 8, "x2": 6.2, "y2": 8},
            {"id": 4, "t": "arc", "layer": "0", "cx": 6.2, "cy": 7.8, "r": 0.2, "a0": 90, "a1": 180},
            {"id": 5, "t": "line", "layer": "0", "x1": 6, "y1": 7.8, "x2": 6, "y2": 4.2},
            {"id": 6, "t": "arc", "layer": "0", "cx": 5.8, "cy": 4.2, "r": 0.2, "a0": 270, "a1": 360},
            {"id": 7, "t": "line", "layer": "0", "x1": 5.8, "y1": 4, "x2": 0, "y2": 4},
            {"id": 8, "t": "line", "layer": "0", "x1": 0, "y1": 4, "x2": 0, "y2": 0}]
    for name, ents in (("open", loop[:-1]), ("closed", loop)):
        for side in ("+", "-"):
            feats = [{"id": "c", "name": "Wall", "type": "surf_sketch", "kind": "extrude", "depth": 2, "plane": "XY", "offset": 0,
                      "sketch": {"entities": [dict(e) for e in ents]}},
                     {"id": "t", "name": "Thicken", "type": "thicken", "source": "c", "thickness": 0.5, "side": side, "mode": "new"}]
            bodies = {}
            shape, st = P.build(part_rec("thc2", feats), surfaces=bodies)
            assert not st[-1].get("error"), (name, side, st[-1])
            assert "simple offset" not in (st[-1].get("note") or ""), (name, side, st[-1])
            assert len(shape.solids()) == 1 and shape.is_valid, (name, side)
            expect = bodies["c"].area * 0.5
            assert abs(shape.volume - expect) < 0.08 * expect, (name, side, shape.volume, expect)


def test_thicken_loop_does_not_cross_the_walls():
    """Thicken by 0.5 mm of the walls of a hole of an imported part (tests/data/thicken_loop_walls.brep.gz: lines,
    B-splines, a round of R0.076 next to a spline that sweeps across the line beside it): to both sides one valid
    solid that stays on its side of the walls (nothing inside the hole for the outward side, nothing outside for
    the inward side)."""
    import gzip
    import os
    import tempfile
    from build123d import Shape, Vector, Wire, Face, Solid
    from OCP.BRepTools import BRepTools
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Shape
    from drawgen import surfaces as sfm
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "thicken_loop_walls.brep.gz")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "s.brep")
        with gzip.open(src, "rb") as fi, open(p, "wb") as fo:
            fo.write(fi.read())
        sh = TopoDS_Shape()
        BRepTools.Read_s(sh, p, BRep_Builder())
    walls = Shape.cast(sh)
    z0 = min(v.Z for v in walls.vertices())
    z1 = max(v.Z for v in walls.vertices())
    bottom = [e for e in walls.edges() if all(abs(q.Z - z0) < 1e-6 for q in (e.position_at(0), e.position_at(0.5), e.position_at(1)))]
    hole = Solid.extrude(Face(Wire.combine(bottom)[0]), Vector(0, 0, z1 - z0))
    vols = []
    for side in ("+", "-"):
        s = sfm._prism_thick(walls, 0.5, side)
        assert s is not None and s.is_valid and len(s.solids()) == 1, side
        inside = sum(x.volume for x in s.intersect(hole).solids()) if s.intersect(hole) else 0.0
        vols.append((s.volume, inside))
    # one side lies in the hole, the other outside it
    (va, ia), (vb, ib) = vols
    assert min(abs(va - ia), ia) < 1e-4 and min(abs(vb - ib), ib) < 1e-4, vols
    assert abs(ia - ib) > 0.5 * min(va, vb), vols


def test_boolean_subtract_inside_out_tool():
    """Boolean subtract with a tool solid whose faces point inward: the tool is turned outward first, so the target
    loses only the overlap (was: the target cut down to the overlap)."""
    from build123d import Box, Cylinder, Pos, Compound, Shape
    from drawgen import part as P
    base = Box(30, 20, 2)
    tool = Pos(5, 0, 0) * Cylinder(3, 4)
    inv = Shape.cast(tool.wrapped.Reversed())
    assert inv.volume < 0
    r = P._boolean(Compound(children=[base, inv]), {"op": "subtract", "targets": [0], "tools": [1], "keep_tools": True})
    vols = sorted(round(x.volume, 3) for x in r.solids())
    assert vols == sorted([round(tool.volume, 3), round(1200 - math.pi * 9 * 2, 3)]), vols


def test_boolean_sliver_removed():
    """Boolean subtract whose tool face lies 0.001 mm inside a target face: no sliver solid is left (fuzzy value of
    the sliver thickness, or the sliver removed) and the note says so; with "keep_slivers" the 0.001 mm slab stays.
    Delete body of solids thinner than 0.01 mm."""
    from build123d import Box, Pos, Compound
    from drawgen import part as P
    tgt = Pos(5, 5, 5) * Box(10, 10, 10)
    tool = Pos((0.001 + 5) / 2, 5, 5) * Box(5 - 0.001, 12, 12)
    f = {"op": "subtract", "targets": [0], "tools": [1]}
    r = P._boolean(Compound(children=[tgt, tool]), f)
    assert len(r.solids()) == 1 and abs(r.volume - 500) < 0.2, [x.volume for x in r.solids()]
    assert "fuzzy" in f["_note"] or "sliver" in f["_note"], f
    f = {"op": "subtract", "targets": [0], "tools": [1], "keep_slivers": True}
    r = P._boolean(Compound(children=[tgt, tool]), f)
    vols = sorted(x.volume for x in r.solids())
    assert len(vols) == 2 and abs(vols[0] - 0.1) < 1e-6 and "_note" not in f, vols
    st = []
    d = {"id": "d1", "type": "body_delete", "min_thickness": 0.01}
    out = P._body_op(r, {}, d, st)
    assert len(out.solids()) == 1 and st[-1]["small"] == [0] and "Solid 1" in st[-1]["note"], st
    st = []
    out = P._body_op(r, {}, {"id": "d2", "type": "body_delete", "min_volume": 1e-3}, st)
    assert len(out.solids()) == 2 and "no small solids" in st[-1]["note"], st


def test_fillet_shallow_crease():
    """Fillet of an edge whose faces meet at 3 deg (convex) and at 4 deg (concave), which OpenCascade refuses below
    5.74 deg: made by the stretched fillet; one blend face added, volume change within 5 % of the circular fillet;
    an edge between faces meeting at 0.1 deg is left with a note; a chamfer of the 3 deg edge fails with the angle
    in the message."""
    import copy
    from conftest import part_rec
    from drawgen import part

    def prism(ang, r, kind="fillet"):
        a = math.radians(ang)
        pts = [(0, 0), (10, 0), (20, 10 * math.tan(a)), (20, 10), (0, 10)]
        ents = [{"id": i + 1, "t": "line", "x1": pts[i][0], "y1": pts[i][1], "x2": pts[(i + 1) % 5][0],
                 "y2": pts[(i + 1) % 5][1], "layer": "0"} for i in range(5)]
        p = part_rec("cr", [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                             "sketch": {"entities": ents}, "depth": 5}])
        s0, _ = part.build(copy.deepcopy(p))
        e = [e for e in s0.edges() if abs(e.position_at(0.5).X - 10) < 1e-6 and abs(e.position_at(0.5).Y) < 1e-6][0]
        p["features"].append({"id": "fl9", "name": "Fillet 1", "type": kind, "value": r, "edges": [part.edge_key(e)]})
        s1, st = part.build(copy.deepcopy(p))
        return s0, s1, st[-1]

    for ang, r in ((3, 5.0), (-4, 2.0), (3, 0.2)):
        s0, s1, st = prism(ang, r)
        assert st["error"] is None, st
        assert "stretched" in st["note"], st
        assert len(s1.faces()) == len(s0.faces()) + 1 and s1.is_valid
        phi = math.radians(abs(ang)) / 2
        exp = r * r * (math.tan(phi) - phi) * 5
        dv = abs(part._precise_volume(s1) - part._precise_volume(s0))
        assert abs(dv - exp) < 0.05 * exp, (ang, r, dv, exp)
    s0, s1, st = prism(0.1, 2.0)
    assert st["error"] is None and "tangent" in st["note"] and len(s1.faces()) == len(s0.faces())
    s0, s1, st = prism(3, 1.0, "chamfer")
    assert st["error"] and "3.00 deg" in st["error"] and "5.7 deg" in st["error"], st


def test_checked_unify_keeps_valid_solid():
    """build123d merges faces and edges after each Boolean; a merge that turns a valid solid invalid (two half-ring
    torus faces on one surface) is replaced by a valid one (occfix.CheckedUnify)."""
    import gzip, tempfile, os
    from build123d import import_brep, Box, Pos
    from drawgen import occfix
    path = os.path.join(os.path.dirname(__file__), "data", "unify_torus_ring.brep.gz")
    with gzip.open(path, "rb") as f, tempfile.NamedTemporaryFile(suffix=".brep", delete=False) as g:
        g.write(f.read())
    so = import_brep(g.name).solids()[0]
    os.unlink(g.name)
    assert so.is_valid
    n0 = occfix.FALLBACKS["count"]
    bb = so.bounding_box()
    r = so.cut(Pos(bb.max.X + 5, 0, 0) * Box(1, 1, 1))
    assert r.is_valid and len(r.faces()) == len(so.faces())
    assert occfix.FALLBACKS["count"] > n0


def _sweep_part(kind="tool", path_plane=None):
    from conftest import part_rec
    L = lambda i, a, b: {"id": i, "t": "line", "x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1], "layer": "0"}
    path = [L(1, (0, 0), (10, 0)), {"id": 2, "t": "arc", "cx": 10, "cy": 1, "r": 1, "a0": -90, "a1": 0, "layer": "0"},
            L(3, (11, 1), (11, 10))]
    prof = [L(11, (-3, 4), (3, 4)), L(12, (3, 4), (0, 0)), L(13, (0, 0), (-3, 4))]
    p = part_rec("sw", [{"id": "b1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "depth": 2,
                         "sketch": {"entities": [L(21, (-5, -5), (16, -5)), L(22, (16, -5), (16, 15)),
                                                 L(23, (16, 15), (-5, 15)), L(24, (-5, 15), (-5, -5))]}}])
    sp = {"id": "sp", "name": "Path", "type": "sketch", "plane": "XY", "offset": 2, "sketch": {"entities": path}}
    if path_plane:
        sp.update(path_plane)
    p["features"].append(sp)
    p["features"].append({"id": "sq", "name": "Profile", "type": "sketch", "plane": "XZ", "offset": 0, "sketch": {"entities": prof}})
    p["features"].append({"id": "sw", "name": "Sweep 1", "type": "sweep", "sketch_ref": "sq", "path_ref": "sp", "mode": "cut",
                          "kind": kind, "axis": "auto"})
    return p


def test_sweep_moving_tool():
    """Sweep with a moving tool: a V-bit (the triangle profile revolved about its axis, radius 0.75 x height) along a
    line, an arc of R1 (tighter than the tool) and a line on the top face of a 2 mm plate; the removed volume equals
    the volume within 0.75 z of the path computed on a grid (66.413 mm^3). A tool axis not normal to the path
    plane is refused. A construction line of the profile as the tool axis: the tool as drawn, moved with the path,
    or with its axis on the path."""
    import copy
    from drawgen import part
    p = _sweep_part()
    s, st = part.build(copy.deepcopy(p))
    assert st[-1]["error"] is None, st[-1]
    assert s.is_valid and len(s.solids()) == 1
    assert abs((21 * 20 * 2 - s.volume) - 66.413) < 0.05, 21 * 20 * 2 - s.volume
    p["features"][-1]["axis"] = "u"
    s, st = part.build(copy.deepcopy(p))
    assert "normal to the path plane" in st[-1]["error"], st[-1]
    # the profile drawn 2 mm to the side with a construction line through its centre as the tool axis: "drawn"
    # (default with a chosen axis) keeps the tool there and moves it with the path; "path" puts the axis on the path
    from build123d import Vector
    sq = [f for f in p["features"] if f["id"] == "sq"][0]
    for e in sq["sketch"]["entities"]:
        for k in ("x1", "x2"):
            e[k] += 2
    sq["sketch"]["entities"].append({"id": "ax", "t": "line", "x1": 2, "y1": 0, "x2": 2, "y2": 5, "constr": True, "layer": "0"})
    p["features"][-1]["axis"] = "ax"
    s, st = part.build(copy.deepcopy(p))
    assert st[-1]["error"] is None, st[-1]
    assert abs((21 * 20 * 2 - s.volume) - 66.413) < 0.05
    assert not s.is_inside(Vector(7, 0, 1.9)) and s.is_inside(Vector(5, -1.5, 1.9))
    p["features"][-1]["tool_at"] = "path"
    s, st = part.build(copy.deepcopy(p))
    assert st[-1]["error"] is None and not s.is_inside(Vector(5, 0, 1.9)) and s.is_inside(Vector(7, 1.5, 1.9))


def test_sweep_path_sketch_on_face():
    """The path sketch on a planar face of the solid (plane "face"): the sweep takes the plane of the path sketch
    as resolved at its place in the tree (was: the sketch plane is not resolved)."""
    import copy
    from drawgen import part
    p = _sweep_part(path_plane={"plane": "face", "offset": 0, "plane_face": {"c": [5.5, 5, 2], "n": [0, 0, 1], "area": 420},
                                "plane_origin": [0, 0, 2], "plane_xdir": [1, 0, 0]})
    s, st = part.build(copy.deepcopy(p))
    assert st[-1]["error"] is None, st[-1]
    assert abs((21 * 20 * 2 - s.volume) - 66.413) < 0.05


def test_sketch_plane_normal_to_sketch_curve_end():
    """Sketch plane normal to a curve of an earlier sketch (plane_sketch_curve): at the end of the chain nearer the
    pick point, normal along the curve there; plane_t gives another position."""
    import copy
    from drawgen import part
    p = _sweep_part()
    p["features"] = p["features"][:[f["id"] for f in p["features"]].index("sp") + 1]
    p["features"].append({"id": "sn", "name": "Sketch 3", "type": "sketch", "plane": "normal", "offset": 0,
                          "plane_sketch_curve": {"sketch": "sp", "pick": [11, 9.8, 2]}, "sketch": {"entities": []}})

    def frame(q):
        _, st = part.build(copy.deepcopy(q))
        assert st[-1]["error"] is None, st[-1]
        return st[-1]["frame"]
    fr = frame(p)
    assert max(abs(a - b) for a, b in zip(fr["o"], [11, 10, 2])) < 1e-6 and abs(abs(fr["z"][1]) - 1) < 1e-9, fr
    p["features"][-1]["plane_sketch_curve"]["pick"] = [0.2, 0, 2]
    fr = frame(p)
    assert max(abs(a - b) for a, b in zip(fr["o"], [0, 0, 2])) < 1e-6 and abs(abs(fr["z"][0]) - 1) < 1e-9, fr
    p["features"][-1]["plane_t"] = 0.5
    fr = frame(p)
    assert abs(fr["o"][2] - 2) < 1e-6 and abs(math.hypot(fr["o"][0] - 10, fr["o"][1] - 1) - 1) < 1e-6, fr   # on the arc


def test_boolean_subtract_tool_not_overlapping():
    """Subtract with a tool that only touches the target: the target is kept and the result line says the tools
    do not overlap it (was: the subtract left nothing of the target)."""
    from build123d import Box, Pos, Compound
    from drawgen import part as P
    tgt = Pos(5, 5, 5) * Box(10, 10, 10)
    tool = Pos(15, 5, 5) * Box(10, 10, 10)
    f = {"op": "subtract", "targets": [0], "tools": [1], "keep_tools": True}
    r = P._boolean(Compound(children=[tgt, tool]), f)
    vols = sorted(round(x.volume, 3) for x in r.solids())
    assert vols == [1000, 1000], vols


def test_sweep_profile_self_intersecting():
    """Profile sweep of the 6 mm wide V profile along a path with a corner of R1: the swept solid intersects itself
    and the error names the moving tool."""
    import copy
    from drawgen import part
    p = _sweep_part(kind="profile")
    s, st = part.build(copy.deepcopy(p))
    assert st[-1]["error"] and "intersects itself" in st[-1]["error"], st[-1]


def test_build_cache_final_state_and_mesh_record():
    """A rebuild of an unchanged part returns the kept shape (no geometry work) and mesh() returns the kept record of
    that shape; a changed last feature gives a new shape and record."""
    import copy
    from drawgen import part as P
    p = plate("fc", 40.0, 20.0, 10.0, 5.0)
    s1, st1 = P.build(copy.deepcopy(p))
    s2, st2 = P.build(copy.deepcopy(p))
    assert s1 is s2 and [x.get("error") for x in st1] == [x.get("error") for x in st2]
    m1, m2 = P.mesh(s1), P.mesh(s2)
    assert m1 is m2 and m1["bbox"] == pytest.approx([0, 0, 0, 40, 20, 10], abs=1e-6)
    q = copy.deepcopy(p)
    next(f for f in q["features"] if f["type"] == "extrude")["depth"] = 12.0
    s3, _ = P.build(q)
    assert s3 is not s1 and abs(s3.volume - s1.volume * 1.2) < 1e-6
    m3 = P.mesh(s3)
    assert m3 is not m1 and m3["bbox"][5] == pytest.approx(12.0, abs=1e-6)
    # the faces kept by the change (the hole cylinder is a new face: the mesh data of unchanged faces is shared)
    assert len(m3["face_keys"]) == len(m1["face_keys"]) == 7


def test_exact_bbox_matches_precise_box():
    """exact_bbox: the precise box (BRepBndLib.AddOptimal without triangulation) of a rotated filleted box, a torus
    and a sphere, not the box of their triangulation."""
    from build123d import Box, Torus, Sphere, Axis, Location
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from drawgen import part as P
    b = Box(100, 50, 20)
    shapes = [b.fillet(4, b.edges()).rotate(Axis.Z, 30).rotate(Axis.X, 20), Torus(30, 5).rotate(Axis.X, 33),
              Sphere(7).moved(Location((3, 4, 5)))]
    for s in shapes:
        BRepMesh_IncrementalMesh(s.wrapped, 0.5, False, 0.3, True)
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(s.wrapped, box, False, False)
        lo, hi = box.CornerMin(), box.CornerMax()
        ref = [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()]
        assert P.exact_bbox(s) == pytest.approx(ref, abs=1e-6)
    assert P.exact_bbox(shapes[2]) == pytest.approx([-4, -3, -2, 10, 11, 12], abs=1e-6)


def test_find_edges_and_faces_on_cells():
    """find_edges and find_faces with a cell reference: the edge or face of that solid is taken where two cells share
    a coincident one; without a cell the first match."""
    import copy
    from drawgen import part as P
    p = box_part([{"id": "sp", "name": "Partition 1", "type": "split", "method": "principal", "plane": "YZ", "offset": 50, "cells": []}])
    sh, st = P.build(copy.deepcopy(p))
    assert len(sh.solids()) == 2
    tp = P._topo(sh)
    shared = [i for i in range(len(tp.edges)) if sum(i in s for s in tp.solid_edges) == 2]
    assert len(shared) == 4
    key = P.edge_key(tp.edges[shared[0]])
    for cell in (0, 1):
        es = P.find_edges(sh, [dict(key, cell=cell)])
        assert len(es) == 1 and tp.edge_index(es[0]) in tp.solid_edges[cell]
    mid = [fc for fc in tp.faces if abs(fc.center().X - 50) < 1e-6]
    assert mid
    for cell in (0, 1):
        fs = P.find_faces(sh, [dict(P.face_key(mid[0]), cell=cell)])
        assert len(fs) == 1 and tp.face_index(fs[0]) in tp.solid_faces[cell]
