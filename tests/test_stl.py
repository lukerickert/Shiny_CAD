# -*- coding: utf-8 -*-
"""STL import (drawgen/stlimport.py): reading, welding and orientation of the mesh, flat faces, fitted cylinders
and cones, the Import feature with an STL file."""
import math

import numpy as np
import pytest

from conftest import part_rec


def _stl(tmp_path, shape, name, **kw):
    from build123d import export_stl
    p = str(tmp_path / name)
    export_stl(shape, p, **kw)
    return p


def _plate():
    from build123d import Box, Cylinder, Cone, Pos
    return Box(60, 40, 10) - Pos(-15, 0, 0) * Cylinder(5, 10) - Pos(15, 0, 3) * Cone(2, 6, 4)


def test_box_flat_faces(tmp_path):
    from build123d import Box
    from drawgen import stlimport as si
    so, rep = si.stl_solid(_stl(tmp_path, Box(20, 10, 5), "box.stl"), {})
    assert rep["triangles"] == 12 and len(so.faces()) == 6 and so.is_valid
    assert so.volume == pytest.approx(1000, rel=1e-9)


def test_plate_fitted_cylinder_and_cone(tmp_path):
    """Hole (cylinder r 5) and countersink (cone, 45 deg) fitted: 7 planes, 2 cylinder halves, 2 cone halves."""
    from drawgen import stlimport as si
    path = _stl(tmp_path, _plate(), "plate.stl", tolerance=0.01, angular_tolerance=0.2)
    so, rep = si.stl_solid(path, {"fit": True})
    assert rep["kinds"] == {"plane": 7, "cylinder": 2, "cone": 2}
    assert so.is_valid and so.volume == pytest.approx(rep["mesh_volume"], rel=1e-3)
    cyl = [f for f in so.faces() if f.geom_type.name == "CYLINDER"]
    assert sum(f.area for f in cyl) == pytest.approx(2 * math.pi * 5 * 10, rel=1e-3)
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    assert BRepAdaptor_Surface(cyl[0].wrapped).Cylinder().Radius() == pytest.approx(5, abs=1e-3)
    circles = [e for e in so.edges() if e.geom_type.name == "CIRCLE" and abs(e.radius - 5) < 1e-3]
    assert len(circles) == 4                         # two half circles at the top and two at the bottom
    flat, rep2 = si.stl_solid(path, {"fit": False})
    assert rep2["kinds"] == {"plane": len(flat.faces())} and flat.is_valid
    assert flat.volume == pytest.approx(rep2["mesh_volume"], rel=1e-5)


def test_read_ascii_and_orientation(tmp_path):
    """ASCII STL with inward triangles: read, welded and turned outward."""
    from drawgen import stlimport as si
    V = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], float)
    F = [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)]           # mixed turning
    lines = ["solid t"]
    for f in F:
        lines += ["facet normal 0 0 0", "outer loop"] + ["vertex %g %g %g" % tuple(V[i]) for i in f] + ["endloop", "endfacet"]
    lines.append("endsolid t")
    p = tmp_path / "tet.stl"
    p.write_text("\n".join(lines))
    so, rep = si.stl_solid(str(p), {})
    assert so.volume == pytest.approx(1000 / 6.0) and len(so.faces()) == 4


def test_open_mesh_refused(tmp_path):
    from drawgen import stlimport as si
    p = tmp_path / "open.stl"
    p.write_text("solid o\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid o\n")
    with pytest.raises(ValueError, match="not closed: 3 open edge"):
        si.stl_solid(str(p), {})


def test_import_feature_with_stl(tmp_path):
    from drawgen import part
    path = _stl(tmp_path, _plate(), "plate.stl", tolerance=0.01, angular_tolerance=0.2)
    p = part_rec("stl", [{"id": "f1", "name": "Import STEP 1", "type": "import", "path": path, "part": None,
                          "stl": {"fit": True}}])
    shape, st = part.build(p)
    assert st[0]["error"] is None and "2 cylindrical, 2 conical" in st[0]["note"]
    assert shape.volume == pytest.approx(_plate().volume, rel=2e-3)


def test_fine_mesh_cylinders_fitted(tmp_path):
    """A finely meshed part (about 19000 triangles, 0.46 deg between neighbouring triangles of the cylinders): the
    cylinders are fitted (a fine mesh of a curved surface is flat within the tolerance over several triangles)."""
    from build123d import Box, Cylinder, Pos, Rot, export_stl
    from drawgen import stlimport
    cap = Cylinder(30, 4) + Pos(0, 0, 4) * (Cylinder(28, 8) - Cylinder(26, 8))
    for a in (0, 90, 180, 270):
        cap += Rot(0, 0, a) * Pos(26, 0, 10) * Box(2, 10, 12)
    path = str(tmp_path / "cap.stl")
    export_stl(cap, path, tolerance=0.0008, angular_tolerance=0.008)
    so, rep = stlimport.stl_solid(path, {"fit": True})
    assert rep["triangles"] > 15000
    assert rep["kinds"].get("cylinder", 0) >= 6 and rep["faces"] < 60
    assert abs(rep["volume"] - rep["mesh_volume"]) < 0.001 * rep["mesh_volume"]


def test_flat_faces_without_fitting_valid(tmp_path):
    """Fitting off on a finely meshed curved part: coplanar triangles are merged only within 1e-5 x the size, so the
    faces stay planar and the solid is valid with the mesh volume."""
    from build123d import Cylinder, export_stl
    from drawgen import stlimport
    path = str(tmp_path / "cyl.stl")
    export_stl(Cylinder(20, 10), path, tolerance=0.001, angular_tolerance=0.02)
    so, rep = stlimport.stl_solid(path, {"fit": False})
    assert rep["kinds"] == {"plane": rep["faces"]} and rep["faces"] > 100
    assert so.is_valid and abs(rep["volume"] - rep["mesh_volume"]) < 1e-3 * rep["mesh_volume"]


def test_rough_mesh_reduced_and_exact(tmp_path):
    """Rough import: a mesh above the maximum is reduced by vertex clustering (size kept within a cell); a mesh below
    it keeps every triangle; the faces are planar triangles of one compound marked as a mesh body."""
    from build123d import Cylinder, Box, export_stl
    from drawgen import stlimport
    path = str(tmp_path / "cyl.stl")
    export_stl(Cylinder(20, 10), path, tolerance=0.001, angular_tolerance=0.02)
    sh, rep = stlimport.rough_mesh(path, 2000)
    assert rep["triangles"] > 2000 and rep["faces"] <= 2000
    assert abs(rep["size"][0] - 40) < 0.5 and abs(rep["size"][2] - 10) < 0.5
    assert getattr(sh, "_mesh", False) and len(sh.faces()) == rep["faces"]
    path2 = str(tmp_path / "box.stl")
    export_stl(Box(10, 20, 30), path2)
    sh2, rep2 = stlimport.rough_mesh(path2, 2000)
    assert rep2["faces"] == rep2["triangles"] == 12
    assert abs(sh2.area - 2 * (200 + 300 + 600)) < 1e-6
