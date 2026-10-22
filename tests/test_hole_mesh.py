# -*- coding: utf-8 -*-
"""Hole mesh (O-grid partition and seeds): the cells become blocks or prisms, the volume is kept, and the structured
mesh (gmsh) has only hexahedra (and wedges below a blind hole), shared nodes across the cells and the seeded edge
counts."""
import math
import os

import pytest

from conftest import circle, part_rec, plate, rect


def hole_part(name, extra_features, w=100.0, h=50.0, t=20.0, ents=None):
    return part_rec(name, [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "depth": t,
                            "sketch": {"entities": ents or rect(w, h)}}] + list(extra_features))


def drill(fid, x, y, **kw):
    f = {"id": fid, "name": "Hole", "type": "hole", "plane": "XY", "offset": 20, "dia": 12, "depth": None,
         "sketch": {"entities": [{"id": 1, "t": "point", "x": x, "y": y, "layer": "0"}]}}
    f.update(kw)
    return f


def with_hole_mesh(p, **kw):
    from drawgen import part
    base, _ = part.build(p)
    cyl = [part.face_key(f) for f in base.faces() if f.geom_type.name == "CYLINDER"]
    hm = {"id": "hm", "name": "Hole mesh 1", "type": "hole_mesh", "faces": cyl, "factor": 2, "n_circ": 3, "n_rad": 4,
          "bias": 2, "n_thick": 4}
    hm.update(kw)
    q = dict(p)
    q["features"] = p["features"] + [hm]
    shape, st = part.build(q)
    s = [x for x in st if x["id"] == "hm"][0]
    assert not s.get("error"), s.get("error")
    return base, shape, st, s


CASES = {
    "through": (lambda: plate("through", 100, 50, 20, 10), 20, 0),
    "two holes": (lambda: hole_part("two", [], 150, 50, 20, rect(150, 50) + [circle(40, 25, 6, 9), circle(110, 25, 6, 10)]), 36, 0),
    "blind": (lambda: hole_part("blind", [drill("f2", 50, 25, depth=12)]), 40, 8),
    "counterbore": (lambda: hole_part("cbore", [drill("f2", 50, 25, dia=9, cbore_dia=15, cbore_depth=9)]), 48, 0),
    "near edge": (lambda: hole_part("edge", [], 100, 50, 20, rect(100, 50) + [circle(10, 25, 6, 9)]), 16, 0),
}


@pytest.mark.parametrize("name", list(CASES))
def test_cells_are_blocks_or_prisms(name):
    make, blocks, prisms = CASES[name]
    base, shape, st, s = with_hole_mesh(make())
    assert shape.volume == pytest.approx(base.volume, rel=1e-9)
    assert (s["blocks"], s["prisms"], s["other"]) == (blocks, prisms, 0)


def test_holes_too_close_are_refused():
    from drawgen import part
    p = hole_part("close", [], 100, 50, 20, rect(100, 50) + [circle(40, 25, 6, 9), circle(50, 30, 6, 10)])
    base, _ = part.build(p)
    cyl = [part.face_key(f) for f in base.faces() if f.geom_type.name == "CYLINDER"]
    p["features"].append({"id": "hm", "name": "Hole mesh 1", "type": "hole_mesh", "faces": cyl, "factor": 2})
    shape, st = part.build(p)
    assert "too close" in ([x for x in st if x["id"] == "hm"][0].get("error") or "")


def read_inp(path):
    """Nodes {id: (x, y, z)} and element counts by type of an Abaqus file."""
    nodes, types, cur = {}, {}, None
    with open(path) as f:
        for line in f:
            s = line.strip()
            if s.startswith("*"):
                up = s.upper()
                cur = "node" if up.startswith("*NODE") else None
                if up.startswith("*ELEMENT"):
                    t = [x.split("=")[1].strip() for x in s.split(",") if x.strip().upper().startswith("TYPE=")][0]
                    cur = ("el", t)
                continue
            if cur == "node" and s:
                v = s.split(",")
                nodes[int(v[0])] = tuple(round(float(x), 6) for x in v[1:4])
            elif isinstance(cur, tuple) and s:
                types[cur[1]] = types.get(cur[1], 0) + 1
    return nodes, types


@pytest.mark.parametrize("name", ["through", "blind"])
def test_structured_mesh_with_seeds(name, tmp_path):
    from drawgen import fea, part, project as pj
    if fea.import_error():
        pytest.skip("gmsh not installed")
    make, blocks, prisms = CASES[name]
    base, shape, st, s = with_hole_mesh(make(), n_circ=3, n_thick=4)
    geo, out = str(tmp_path / "m.brep"), str(tmp_path / "m.inp")
    pj.write_brep(shape.wrapped, geo)
    res = fea.run(geo, out, {"kind": "hex", "size": 5, "seeds": part.mesh_seeds(st)})
    nodes, types = read_inp(out)
    assert set(types) <= {"C3D8", "C3D6"} and types.get("C3D8")
    assert bool(types.get("C3D6")) == bool(prisms)
    assert len(set(nodes.values())) == len(nodes)                  # no duplicate nodes: the cells share their nodes
    assert res["quality"]["inverted"] == 0 and res["quality"]["sicn_min"] > 0.2
    if name == "through":
        assert len({round(z, 3) for x, y, z in nodes.values()}) == 5      # 4 elements through the 20 mm thickness
    # 3 elements per 45 deg: 8 x 3 = 24 nodes on each hole circle
    ring = [p for p in nodes.values() if abs(math.hypot(p[0] - 50, p[1] - 25) - (10 if name == "through" else 6)) < 1e-4
            and abs(p[2] - 20) < 1e-6]
    assert len(ring) == 24
