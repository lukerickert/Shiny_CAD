# -*- coding: utf-8 -*-
"""Measurement between two items of a part or an assembly (world coordinates, mm).

Item: {"kind": "plane" | "cylinder" | "axis" | "other", "name", "c" (centre), "n" (plane normal or axis direction),
"p" (point on the axis), "r" (cylinder radius), "area", "shape" (OCC shape of the face, or None for a reference plane
or axis: they are infinite)}.

measure(a, b) -> {"rows": [[label, value text]], "points": [[x, y, z], [x, y, z]] (closest points) or None}
"""
import math

TOL_PAR = 1e-6          # |sin| below this: parallel


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _norm(a):
    L = math.sqrt(_dot(a, a)) or 1.0
    return [a[0] / L, a[1] / L, a[2] / L]


def _len(a):
    return math.sqrt(_dot(a, a))


def mm(v):
    return "%.4f mm" % v


def deg(v):
    return "%.4f deg" % v


def vec(v):
    return "(%s)" % ", ".join("%.4f" % x for x in v)


def item_from_face(face, name=""):
    """Item of a placed face (build123d Face or OCC TopoDS_Face)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from build123d import Face
    f = face if hasattr(face, "wrapped") else Face(face)
    c = f.center()
    it = {"kind": "other", "name": name, "c": [c.X, c.Y, c.Z], "area": f.area, "shape": f.wrapped}
    ad = BRepAdaptor_Surface(f.wrapped)
    t = ad.GetType()
    if t == GeomAbs_Plane:
        n = f.normal_at(c)
        it.update(kind="plane", n=[n.X, n.Y, n.Z])
    elif t == GeomAbs_Cylinder:
        cy = ad.Cylinder()
        ax = cy.Axis()
        L, D = ax.Location(), ax.Direction()
        d = [D.X(), D.Y(), D.Z()]
        p0 = [L.X(), L.Y(), L.Z()]
        # the axis point nearest the face centre; the length of the face along the axis
        t0 = _dot(_sub(it["c"], p0), d)
        p = [p0[i] + d[i] * t0 for i in range(3)]
        try:
            u0, u1, v0, v1 = ad.FirstUParameter(), ad.LastUParameter(), ad.FirstVParameter(), ad.LastVParameter()
            length = abs(v1 - v0)
        except Exception:
            length = None
        it.update(kind="cylinder", p=p, n=d, r=cy.Radius(), length=length)
    return it


def item_from_edge(edge, name=""):
    """Item of a placed edge: kind line (straight: p start, q end, n direction, length), circle (c centre, n axis, r,
    length) or other (c midpoint, length); "shape" the edge for the minimum distance."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
    from OCP.GCPnts import GCPnts_AbscissaPoint
    from build123d import Edge
    e = edge if hasattr(edge, "wrapped") else Edge(edge)
    ad = BRepAdaptor_Curve(e.wrapped)
    u0, u1 = ad.FirstParameter(), ad.LastParameter()
    P = lambda u: [ad.Value(u).X(), ad.Value(u).Y(), ad.Value(u).Z()]
    length = GCPnts_AbscissaPoint.Length_s(ad)
    it = {"kind": "other", "name": name, "c": P((u0 + u1) / 2), "length": length, "shape": e.wrapped, "edge": True}
    t = ad.GetType()
    if t == GeomAbs_Line:
        a, b = P(u0), P(u1)
        it.update(kind="line", p=a, q=b, n=_norm(_sub(b, a)))
    elif t == GeomAbs_Circle:
        ci = ad.Circle()
        L, D = ci.Location(), ci.Axis().Direction()
        it.update(kind="circle", c=[L.X(), L.Y(), L.Z()], p=[L.X(), L.Y(), L.Z()], n=[D.X(), D.Y(), D.Z()], r=ci.Radius(),
                  sweep=math.degrees(abs(u1 - u0)))
    return it


def item_from_point(p, name=""):
    """Item of a point (a vertex): kind point with a vertex shape."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.gp import gp_Pnt
    q = [float(v) for v in p][:3]
    return {"kind": "point", "name": name, "c": q, "shape": BRepBuilderAPI_MakeVertex(gp_Pnt(*q)).Vertex()}


def _shape_of(it, size):
    """OCC shape of an item for the minimum distance: the face, or a large plane face / long edge for a reference
    plane or axis."""
    if it.get("shape") is not None:
        return it["shape"]
    from build123d import Face, Plane, Vector, Edge
    if it["kind"] == "plane":
        return Face.make_rect(size, size, Plane(origin=Vector(*it["c"]), z_dir=Vector(*it["n"]))).wrapped
    if it["kind"] == "axis":
        p, d = it.get("p") or it["c"], _norm(it["n"])
        a = [p[i] - d[i] * size / 2 for i in range(3)]
        b = [p[i] + d[i] * size / 2 for i in range(3)]
        return Edge.make_line(Vector(*a), Vector(*b)).wrapped
    return None


def describe(it):
    """Rows of one item."""
    rows = []
    k = it["kind"]
    if k == "cylinder":
        rows.append(["Cylinder", "Ø " + mm(2 * it["r"]) + " (R " + mm(it["r"]) + ")"])
        rows.append(["Axis direction", vec(it["n"])])
        rows.append(["Axis point", vec(it["p"])])
        if it.get("length"):
            rows.append(["Length along the axis", mm(it["length"])])
    elif k == "plane":
        rows.append(["Plane" if it.get("shape") is None else "Planar face", "normal " + vec(it["n"])])
        rows.append(["Point" if it.get("shape") is None else "Centre", vec(it["c"])])
    elif k == "point":
        rows.append(["Point", vec(it["c"])])
        return rows
    elif k == "line":
        rows.append(["Straight edge", "length " + mm(it["length"])])
        rows.append(["Direction", vec(it["n"])])
        rows.append(["Start", vec(it["p"])])
        rows.append(["End", vec(it["q"])])
        return rows
    elif k == "circle":
        rows.append(["Circular edge", "Ø " + mm(2 * it["r"]) + " (R " + mm(it["r"]) + ")"])
        rows.append(["Centre", vec(it["c"])])
        rows.append(["Axis direction", vec(it["n"])])
        rows.append(["Arc", deg(it.get("sweep", 360.0)) + ", length " + mm(it["length"])])
        return rows
    elif k == "other" and it.get("edge"):
        rows.append(["Edge", "length " + mm(it["length"])])
        rows.append(["Midpoint", vec(it["c"])])
        return rows
    elif k == "axis":
        rows.append(["Axis", "direction " + vec(it["n"])])
        rows.append(["Point", vec(it.get("p") or it["c"])])
    else:
        rows.append(["Face", "centre " + vec(it["c"])])
    if it.get("area") is not None and it.get("shape") is not None:
        rows.append(["Area", "%.4f mm^2" % it["area"]])
    return rows


def _line_line(p1, d1, p2, d2):
    """Shortest distance between two lines and the closest points."""
    w = _sub(p1, p2)
    a, b, c = _dot(d1, d1), _dot(d1, d2), _dot(d2, d2)
    d, e = _dot(d1, w), _dot(d2, w)
    den = a * c - b * b
    if abs(den) < 1e-12:
        t, s = 0.0, e / c
    else:
        t, s = (b * e - c * d) / den, (a * e - b * d) / den
    q1 = [p1[i] + d1[i] * t for i in range(3)]
    q2 = [p2[i] + d2[i] * s for i in range(3)]
    return _len(_sub(q1, q2)), q1, q2


def measure(a, b=None):
    """Measurement of one item (b None) or between two items."""
    if b is None:
        return {"rows": describe(a), "points": None}
    rows, points = [], None
    size = 1e4
    sa, sb = _shape_of(a, size), _shape_of(b, size)
    if sa is not None and sb is not None:
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        ex = BRepExtrema_DistShapeShape(sa, sb)
        ex.Perform()
        if ex.IsDone() and ex.NbSolution():
            pa, pb = ex.PointOnShape1(1), ex.PointOnShape2(1)
            points = [[pa.X(), pa.Y(), pa.Z()], [pb.X(), pb.Y(), pb.Z()]]
            rows.append(["Minimum distance", mm(ex.Value())])
    ka, kb = a["kind"], b["kind"]
    line = lambda k: k in ("cylinder", "axis", "line", "circle")
    if ka == "plane" and kb == "plane":
        na, nb = _norm(a["n"]), _norm(b["n"])
        cosv = max(-1.0, min(1.0, _dot(na, nb)))
        ang = math.degrees(math.acos(abs(cosv)))
        rows.append(["Angle between the planes", deg(ang)])
        if _len(_cross(na, nb)) < TOL_PAR:
            rows.append(["Distance between the planes", mm(abs(_dot(_sub(b["c"], a["c"]), na)))])
    elif line(ka) and line(kb):
        da, db = _norm(a["n"]), _norm(b["n"])
        pa, pb = a.get("p") or a["c"], b.get("p") or b["c"]
        ang = math.degrees(math.acos(min(1.0, abs(_dot(da, db)))))
        w = "lines" if ka == kb == "line" else "line and the axis" if "line" in (ka, kb) else "axes"
        rows.append(["Angle between the " + w, deg(ang)])
        dist, q1, q2 = _line_line(pa, da, pb, db)
        rows.append(["Distance between the " + w if _len(_cross(da, db)) < TOL_PAR else "Shortest distance between the " + w, mm(dist)])
        if ka in ("cylinder", "circle") and kb in ("cylinder", "circle"):
            rows.append(["Diameters", "Ø %.4f mm, Ø %.4f mm" % (2 * a["r"], 2 * b["r"])])
            if _len(_cross(da, db)) < TOL_PAR:
                rows.append(["Axis distance minus both radii", mm(dist - a["r"] - b["r"])])
    elif (ka == "plane" and line(kb)) or (kb == "plane" and line(ka)):
        pl, ln = (a, b) if ka == "plane" else (b, a)
        n, d = _norm(pl["n"]), _norm(ln["n"])
        s = abs(_dot(n, d))
        w = "edge" if ln["kind"] == "line" else "axis"
        rows.append(["Angle between the %s and the plane" % w, deg(math.degrees(math.asin(min(1.0, s))))])
        if s < TOL_PAR:
            dist = abs(_dot(_sub(ln.get("p") or ln["c"], pl["c"]), n))
            rows.append(["Distance from the %s to the plane" % w, mm(dist)])
            if ln["kind"] in ("cylinder", "circle"):
                rows.append(["Axis distance minus radius", mm(dist - ln["r"])])
    elif "point" in (ka, kb) and (ka in ("plane",) or kb in ("plane",) or line(ka) or line(kb)):
        pt, o = (a, b) if ka == "point" else (b, a)
        if o["kind"] == "plane":
            rows.append(["Distance from the point to the plane", mm(abs(_dot(_sub(pt["c"], o["c"]), _norm(o["n"]))))])
        else:
            dl = _norm(o["n"])
            v = _sub(pt["c"], o.get("p") or o["c"])
            rows.append(["Distance from the point to the " + ("line" if o["kind"] == "line" else "axis"), mm(_len(_sub(v, [_dot(v, dl) * x for x in dl])))])
    d = _sub(b["c"], a["c"])
    rows.append(["Distance between the centres", mm(_len(d)) + "  dx %.4f, dy %.4f, dz %.4f" % tuple(d)])
    return {"rows": rows, "points": points}


def label(it):
    """Name of an item with its kind: "PART : cylinder Ø 20.0000 mm"."""
    k = it["kind"]
    if it.get("shape") is None:
        return it.get("name") or k
    if k == "point":
        return (it.get("name") or "point") + " " + vec(it["c"])
    kind = {"plane": "planar face", "cylinder": "cylinder Ø %.4f mm" % (2 * it.get("r", 0)),
            "line": "straight edge %.4f mm" % it.get("length", 0), "circle": "circular edge Ø %.4f mm" % (2 * it.get("r", 0)),
            "other": "edge %.4f mm" % it.get("length", 0) if it.get("edge") else "face"}.get(k, k)
    return (it.get("name") + " : " if it.get("name") else "") + kind
