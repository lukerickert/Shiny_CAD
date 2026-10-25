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
    assert "not sewn" in t.get("note", "")


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
