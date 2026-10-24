# -*- coding: utf-8 -*-
"""Parametric parts: sketch-based extrude, cut and revolve features (build123d / OpenCascade).

Part record (JSON):
  {"name", "features": [feature, ...]}

Feature:
  {"id", "name", "type": "extrude" | "cut" | "revolve", "suppressed": false,
   "plane": "XY" | "XZ" | "YZ" | "normal", "offset": mm,
   plane "normal": normal to an edge of the solid ("plane_edge": edge key) or to a curve body ("plane_curve":
   feature id) at the fraction "plane_t" (0..1) of its length; "plane_flip" reverses the normal. Sketch x is
   the projection of global Z (global X when the tangent is within 10 deg of Z) crossed with the tangent, sketch y
   the projection itself. Applies to extrude, cut, revolve, hole, sweep (profile), split (sketch) and surf_sketch.
   "sketch": {sketch record of the Sketch tab},
   extrude / cut: "depth", "symmetric", "reverse", "through" (cut only)
   revolve:       "angle" (deg), "axis": "u" | "v" | <construction line id>, "mode": "add" | "cut"}
  {"id", "name", "type": "fillet" | "chamfer", "suppressed", "value": mm,
   "edges": [{"mid": [x, y, z], "len": mm}, ...]}      edges of the part before this feature,
                                                        identified by mid point and length
  {"type": "shell", "thickness": mm, "faces": [{"c": [x, y, z], "n": [nx, ny, nz], "area"}]}   faces removed (openings)
  {"type": "pattern", "kind": "linear" | "circular", "features": [feature ids], "count": n,
   "step": [dx, dy, dz] (linear, mm) | "axis": "X" | "Y" | "Z", "centre": [x, y, z], "angle": deg (circular, total
   angle of count instances; 360 spreads evenly)}
  {"type": "hole", "plane", "offset", "sketch" (point entities give the positions; circles their centres),
   "dia": mm, "depth": mm | null (through), "cbore_dia", "cbore_depth", "csink_dia", "csink_angle" (deg),
   "thread": text (hole callout and cosmetic thread on the drawing), "tol": tolerance class for the callout
   (H7 for a plain hole, 6H for a thread), "reverse": drill toward +normal}
  {"type": "sweep", "plane", "offset", "sketch" (profile), "path_plane", "path_offset", "path_sketch" (open chain
   of lines and arcs), "mode": "add" | "cut"}

  {"type": "plane", "method": "principal" (plane, offset) | "datum" (plane_ref: plane feature id) | "point_normal"
   (point, normal) | "three_points" (points) | "face" (face: planar face key) | "edge" (edge key, curve: curve body
   id, or sketch_curve: {"sketch": sketch id, "pick": [x, y, z]}; t, for a sketch curve null: the chain end nearer
   the pick point) | "angle" (face, edge or curve, angle deg: through the edge, rotated from the face) | "midplane" (faces: two
   parallel planar faces), "offset": mm along the normal, "flip"}      datum plane; a sketch plane "datum" with
   "plane_ref" = its id places a sketch on it; Partition method "datum" cuts with it

  {"type": "import", "path": STEP file, "part": solid index | null}      base geometry from a file
  {"type": "split", "method": "principal" (plane, offset, relative) | "point_normal" (point, normal) | "three_points"
   (points) | "face" (face key; its surface, planar or curved, extended through the cells; face_offset: mm along the face normal) |
   "sketch" (plane, offset, sketch: lines, arcs and circles extruded through the part) | "edge" (edge: edge key, or curve: curve body id; t: fraction 0..1 of the length) | "datum" (plane_ref, offset) | "ogrid" (face: cylindrical face key;
   four planes through the hole axis applied to the cells around the hole), "cells": [face keys {"c", "n", "area"} or
   points {"p": [x, y, z]} of the cells to partition; empty: all]}                                              partition of cells by a plane
  {"type": "unify", "faces": true, "edges": true, "angle": deg}         merge coplanar faces / collinear edges
  {"type": "heal", "tolerance": mm (small edges dropped), "small_faces": mm (spot and strip faces below this
   width removed)}; the result is rejected when invalid or when the volume changes by more than 1 %
  {"type": "combine", "faces": [face keys], "min_area": mm^2}         virtual topology: the faces are meshed as one
   (gmsh compound surface); faces below min_area are combined with their largest neighbour. Geometry unchanged.
  {"type": "smooth", "tolerance": mm, "segments": n, "continuity": "C2" | "C1"}   re-approximate B-spline surfaces
  {"type": "replace", "faces": [face keys], "min_area": mm^2, "method": "analytic" | "smooth" | "original",
   "tolerance": mm, "offset": mm (+ outward), "pad": mm}             rebuild the picked faces on one clean surface
  {"type": "hole_mesh", "faces": [cylindrical face keys, one per hole], "factor": square side / hole diameter,
   "n_circ": elements per 45 deg of the hole, "n_rad": elements from the hole to the square, "bias": largest /
   smallest radial element, "n_thick": elements through the thickness}   O-grid partition around the holes; the
   seeds are used by the structured hexahedral mesh (fea.py)
  {"type": "offset_faces", "faces": [face keys], "distance": mm, "tangent": bool}  faces moved along their normals
      (+ adds material); tangent (default true): faces connected through tangent edges included
  {"type": "move_faces", "faces": [face keys], "vector": [dx, dy, dz], "tangent": bool}  faces swept along the
      vector (push/pull), or a feature (hole, boss) moved across: removed and placed again at the moved position
  {"type": "defeature", "faces": [face keys], "min_area": mm^2 (small faces next to the picked ones are included),
   "all_small": true (every face below min_area, no pick needed)}       remove faces (fillets, holes) and close the gap

Sketch coordinates (u, v) are the plane's local x and y:
  XY: u = X, v = Y, normal +Z
  XZ: u = X, v = Z, normal -Y
  YZ: u = Y, v = Z, normal +X
The offset moves the plane along its normal.
"""
import math

TOL = 1e-6


def adjust_frame(fr, f):
    """Frame with the sketch origin moved to "plane_origin" (a 3D point, projected onto the plane) or to the point
    feature "plane_origin_ref", and the sketch x axis along "plane_xdir" (a 3D direction, projected into the plane)
    or along the axis feature "plane_xdir_ref", when the feature gives them."""
    o, x, z = fr["o"], fr["x"], fr["z"]
    p = f.get("plane_origin")
    if f.get("plane_origin_ref"):
        p = ref_point(f.get("_datums"), f["plane_origin_ref"])
    dx = f.get("plane_xdir")
    if f.get("plane_xdir_ref"):
        dx = ref_axis(f.get("_datums"), f["plane_xdir_ref"])["d"]
    if p:
        d = sum((p[k] - o[k]) * z[k] for k in range(3))
        o = [round(p[k] - d * z[k], 9) for k in range(3)]
    if dx:
        dn = sum(dx[k] * z[k] for k in range(3))
        xv = [dx[k] - dn * z[k] for k in range(3)]
        ln = math.sqrt(sum(v * v for v in xv))
        if ln > 1e-9:
            x = [round(v / ln, 9) for v in xv]
    if o is fr["o"] and x is fr["x"]:
        return fr
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    return {"o": o, "x": x, "y": [round(v, 9) for v in y], "z": z}


def plane_of(f):
    from build123d import Plane, Vector
    if f.get("plane") in ("normal", "datum", "face"):
        fr = f.get("_frame")
        if not fr:
            raise ValueError("the sketch plane is not resolved")
    else:
        n, x = PRINCIPAL_FRAMES[f.get("plane", "XY")]
        fr = _frame_of([0, 0, 0], n, x)
    fr = adjust_frame(fr, f)
    base = Plane(origin=Vector(*fr["o"]), x_dir=Vector(*fr["x"]), z_dir=Vector(*fr["z"]))
    off = float(f.get("offset", 0) or 0)
    return base.offset(off) if off else base


def reference_curve(shape, bodies, edge_ref, curve_id, f=None):
    """The edge of the solid (edge key), the curve body (feature id) or, with f["sketch_curve"] {"sketch": sketch
    id, "pick": [x, y, z]}, the curve of a sketch (the connected chain of sketch curves nearest the pick point) a
    plane, point, axis or partition is defined on."""
    from build123d import Wire
    sc = (f or {}).get("sketch_curve")
    if sc and sc.get("sketch"):
        fn = (f or {}).get("_sketch_curves")
        if fn is None:
            raise ValueError("the sketch curves are not available")
        return sketch_chain(fn(sc["sketch"]), sc.get("pick"))
    if curve_id:
        body = (bodies or {}).get(curve_id)
        if body is None:
            raise ValueError("the reference curve body was not found")
        edges = list(body.edges())
        if not edges:
            raise ValueError("the reference curve body has no edges")
        if len(edges) == 1:
            return edges[0]
        try:
            return Wire(edges)
        except Exception:
            return max(edges, key=lambda e: e.length)
    if edge_ref:
        if shape is None:
            raise ValueError("no solid for the reference edge")
        edges = find_edges(shape, [edge_ref])
        if not edges:
            raise ValueError("the reference edge was not found")
        return edges[0]
    raise ValueError("pick an edge or choose a curve body for the plane")


def sketch_chain(edges, pick=None):
    """The connected chain (Wire) of 3D sketch edges that lies nearest the pick point (no pick point: the longest
    chain). Construction curves are not part of the edges."""
    from build123d import Wire, Vertex
    edges = list(edges or [])
    if not edges:
        raise ValueError("the sketch has no curves")
    try:
        chains = list(Wire.combine(edges, tol=1e-4))
    except Exception:
        chains = []
    if not chains:
        chains = [Wire([e]) for e in edges]
    if pick:
        v = Vertex(*[float(x) for x in pick])
        return min(chains, key=lambda w: v.distance_to(w))
    return max(chains, key=lambda w: w.length)


def curve_t(curve, f, default=0.5):
    """Fraction of the length of a reference curve: f["t"]; for a sketch curve without t, the end of the chain
    nearer the pick point (0 or 1)."""
    t = f.get("t")
    if t is None:
        sc = f.get("sketch_curve") or {}
        if sc.get("pick") and not curve.is_closed:
            from build123d import Vector
            q = Vector(*[float(x) for x in sc["pick"]])
            t = 0.0 if (curve.position_at(0.0) - q).length <= (curve.position_at(1.0) - q).length else 1.0
        else:
            t = default
    return min(max(float(t), 0.0), 1.0)


def normal_frame(curve, t, flip=False):
    """Frame of the plane normal to the curve at the fraction t of its length: origin on the curve, z along the
    tangent, axes as in _frame_of."""
    from build123d import Vector
    t = min(max(float(t if t is not None else 0.5), 0.0), 1.0)
    o, d = curve.position_at(t), curve.tangent_at(t)
    n = Vector(d.X, d.Y, d.Z).normalized()
    if flip:
        n = -n
    return _frame_of([o.X, o.Y, o.Z], [n.X, n.Y, n.Z])


def _frame_of(o, n, x=None):
    """Frame dict from an origin and a normal. Without x: y is the projection of global Z; for a normal within
    10 deg of Z, x is the projection of global X."""
    from build123d import Vector
    n = Vector(*n).normalized()
    if x is None and abs(n.Z) < 0.985:
        ref = Vector(0, 0, 1)
        y = (ref - n * ref.dot(n)).normalized()
        x = y.cross(n)
    elif x is None:
        ref = Vector(1, 0, 0)
        x = (ref - n * ref.dot(n)).normalized()
        y = n.cross(x)
    else:
        x = Vector(*x)
        x = (x - n * x.dot(n)).normalized()
        y = n.cross(x)
    r = lambda v: [round(v.X, 9), round(v.Y, 9), round(v.Z, 9)]
    return {"o": r(Vector(*o)), "x": r(x), "y": r(y), "z": r(n)}


PRINCIPAL_FRAMES = {"XY": ([0, 0, 1], [1, 0, 0]), "XZ": ([0, -1, 0], [1, 0, 0]), "YZ": ([1, 0, 0], [0, 1, 0])}


def _planar_face(shape, ref, what="face"):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    if shape is None:
        raise ValueError("no solid for the %s" % what)
    faces = find_faces(shape, [ref or {}])
    if not faces:
        raise ValueError("the %s was not found" % what)
    fc = faces[0]
    if BRepAdaptor_Surface(fc.wrapped).GetType() != GeomAbs_Plane:
        raise ValueError("the %s is not planar" % what)
    c = fc.center()
    n = fc.normal_at(c)
    return fc, [c.X, c.Y, c.Z], [n.X, n.Y, n.Z]


def datum_get(datums, did):
    """Entry of a plane, point or axis feature; the reference planes XY, XZ, YZ are frames through the origin."""
    d = (datums or {}).get(did)
    if d is None and did in PRINCIPAL_FRAMES:
        n, x = PRINCIPAL_FRAMES[did]
        d = _frame_of([0, 0, 0], n, x)
        d["kind"] = "plane"
    return d


def ref_point(datums, pid):
    """Coordinates of a point feature (or the origin of a plane or axis feature). A vertex of the part picked in
    the view is stored as its coordinates [x, y, z] (mm) and returned as they are."""
    if isinstance(pid, (list, tuple)) and len(pid) == 3:
        return [float(v) for v in pid]
    d = datum_get(datums, pid)
    if not d:
        raise ValueError("the reference point was not found (choose a point feature above this one)")
    return list(d["o"])


def ref_axis(datums, aid):
    """{"o", "d"} of an axis feature (or the normal of a plane feature)."""
    d = datum_get(datums, aid)
    if not d:
        raise ValueError("the reference axis was not found (choose an axis feature above this one)")
    if d.get("kind") == "axis":
        return {"o": list(d["o"]), "d": list(d["d"])}
    if "z" in d:
        return {"o": list(d["o"]), "d": list(d["z"])}
    raise ValueError("%s is not an axis" % aid)


def _vec3(v, what="vector"):
    v = [float(x or 0) for x in (v or [0, 0, 0])]
    if len(v) != 3:
        raise ValueError("%s needs three values" % what)
    return v


def _unit(v, what="direction"):
    ln = math.sqrt(sum(x * x for x in v))
    if ln < 1e-12:
        raise ValueError("%s has zero length" % what)
    return [round(x / ln, 9) for x in v]


def datum_point(shape, bodies, datums, f):
    """[x, y, z] of a point feature. method: coords (point) | edge (edge key or curve body id, t) | face (face
    key: centre) | offset (point_ref, offset vector) | axis (axis_ref, distance from the axis origin) |
    axis_plane (axis_ref, plane_ref: intersection) | midpoint (two point refs). offset (vector) is added to every
    result."""
    m = f.get("method") or "coords"
    if m == "coords":
        p = _vec3(f.get("point"), "point")
    elif m == "edge":
        curve = reference_curve(shape, bodies, f.get("edge"), f.get("curve"), f)
        q = curve.position_at(curve_t(curve, f))
        p = [q.X, q.Y, q.Z]
    elif m == "face":
        if shape is None:
            raise ValueError("no solid for the face")
        if not f.get("face"):
            raise ValueError("pick the face")
        faces = find_faces(shape, [f["face"]])
        if not faces:
            raise ValueError("the face was not found")
        c = faces[0].center()
        p = [c.X, c.Y, c.Z]
    elif m == "offset":
        p = ref_point(datums, f.get("point_ref"))
    elif m == "axis":
        ax = ref_axis(datums, f.get("axis_ref"))
        dist = float(f.get("distance", 0) or 0)
        p = [ax["o"][k] + ax["d"][k] * dist for k in range(3)]
    elif m == "axis_plane":
        ax = ref_axis(datums, f.get("axis_ref"))
        pl = datum_get(datums, f.get("plane_ref"))
        if not pl or "z" not in pl:
            raise ValueError("the reference plane was not found")
        den = sum(ax["d"][k] * pl["z"][k] for k in range(3))
        if abs(den) < 1e-12:
            raise ValueError("the axis is parallel to the plane")
        t = sum((pl["o"][k] - ax["o"][k]) * pl["z"][k] for k in range(3)) / den
        p = [ax["o"][k] + ax["d"][k] * t for k in range(3)]
    elif m == "midpoint":
        refs = f.get("points_ref") or []
        if len(refs) != 2:
            raise ValueError("two point features are needed")
        a, b = ref_point(datums, refs[0]), ref_point(datums, refs[1])
        p = [(a[k] + b[k]) / 2 for k in range(3)]
    else:
        raise ValueError("unknown point method %s" % m)
    off = f.get("offset_vec")
    if off:
        ov = _vec3(off, "offset")
        p = [p[k] + ov[k] for k in range(3)]
    return [round(v, 9) for v in p]


def datum_axis(shape, bodies, datums, f):
    """{"o", "d"} of an axis feature. method: two_points (points_ref: two point features, or p1, p2 coordinates) |
    point_dir (point_ref or point, direction "X" | "Y" | "Z" | vector) | edge (straight edge key or curve body id)
    | cylinder (face key: axis of a cylindrical, conical or toroidal face) | planes (planes_ref: two plane
    features) | normal (plane_ref, point_ref optional: normal to the plane through the point) | parallel
    (axis_ref, point_ref: parallel axis through the point). flip reverses the direction."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Torus, GeomAbs_Line, GeomAbs_SurfaceOfRevolution
    m = f.get("method") or "two_points"
    if m == "two_points":
        refs = f.get("points_ref") or []
        if len(refs) == 2:
            a, b = ref_point(datums, refs[0]), ref_point(datums, refs[1])
        else:
            a, b = _vec3(f.get("p1"), "point 1"), _vec3(f.get("p2") or [0, 0, 1], "point 2")
        o, d = a, [b[k] - a[k] for k in range(3)]
    elif m == "point_dir":
        o = ref_point(datums, f["point_ref"]) if f.get("point_ref") else _vec3(f.get("point"), "point")
        dr = f.get("direction") or "Z"
        d = {"X": [1, 0, 0], "Y": [0, 1, 0], "Z": [0, 0, 1]}[dr] if isinstance(dr, str) else _vec3(dr, "direction")
    elif m == "edge":
        curve = reference_curve(shape, bodies, f.get("edge"), f.get("curve"), f)
        ad = BRepAdaptor_Curve(curve.wrapped) if hasattr(curve, "wrapped") and curve.wrapped.ShapeType() == 6 else None
        a, b = curve.position_at(0.0), curve.position_at(1.0)
        if ad is not None and ad.GetType() != GeomAbs_Line and (b - a).length < 1e-9:
            raise ValueError("the edge is not straight")
        o, d = [a.X, a.Y, a.Z], [b.X - a.X, b.Y - a.Y, b.Z - a.Z]
    elif m == "cylinder":
        if shape is None:
            raise ValueError("no solid for the face")
        if not f.get("face"):
            raise ValueError("pick the face")
        faces = find_faces(shape, [f["face"]])
        if not faces:
            raise ValueError("the face was not found")
        ad = BRepAdaptor_Surface(faces[0].wrapped)
        t = ad.GetType()
        if t == GeomAbs_Cylinder:
            ax = ad.Cylinder().Axis()
        elif t == GeomAbs_Cone:
            ax = ad.Cone().Axis()
        elif t == GeomAbs_Torus:
            ax = ad.Torus().Axis()
        elif t == GeomAbs_SurfaceOfRevolution:
            ax = ad.AxeOfRevolution()
        else:
            raise ValueError("the face is not cylindrical, conical or toroidal")
        L, D = ax.Location(), ax.Direction()
        c = faces[0].center()
        o0 = [L.X(), L.Y(), L.Z()]
        d = [D.X(), D.Y(), D.Z()]
        # axis point at the height of the face centre
        h = sum((getattr(c, a) - o0[k]) * d[k] for k, a in enumerate("XYZ"))
        o = [o0[k] + d[k] * h for k in range(3)]
    elif m == "planes":
        refs = f.get("planes_ref") or []
        if len(refs) != 2:
            raise ValueError("two plane features are needed")
        p1, p2 = datum_get(datums, refs[0]), datum_get(datums, refs[1])
        if not p1 or not p2 or "z" not in p1 or "z" not in p2:
            raise ValueError("the reference planes were not found")
        n1, n2 = p1["z"], p2["z"]
        d = [n1[1] * n2[2] - n1[2] * n2[1], n1[2] * n2[0] - n1[0] * n2[2], n1[0] * n2[1] - n1[1] * n2[0]]
        if math.sqrt(sum(v * v for v in d)) < 1e-9:
            raise ValueError("the planes are parallel")
        # a point on both planes: solve from the plane origins
        import numpy as np
        A = np.array([n1, n2, d], dtype=float)
        b = np.array([sum(n1[k] * p1["o"][k] for k in range(3)), sum(n2[k] * p2["o"][k] for k in range(3)), sum(d[k] * p1["o"][k] for k in range(3))])
        o = list(np.linalg.solve(A, b))
    elif m == "normal":
        pl = datum_get(datums, f.get("plane_ref"))
        if not pl or "z" not in pl:
            raise ValueError("the reference plane was not found")
        o = ref_point(datums, f["point_ref"]) if f.get("point_ref") else list(pl["o"])
        d = list(pl["z"])
    elif m == "parallel":
        ax = ref_axis(datums, f.get("axis_ref"))
        o = ref_point(datums, f["point_ref"]) if f.get("point_ref") else ax["o"]
        d = ax["d"]
    else:
        raise ValueError("unknown axis method %s" % m)
    d = _unit(d, "axis direction")
    if f.get("flip"):
        d = [-v for v in d]
    return {"o": [round(float(v), 9) for v in o], "d": d}


def datum_frame(shape, bodies, datums, f):
    """Frame of a plane feature. method: principal (plane, offset) | datum (plane_ref: plane feature id) |
    point_normal (point, normal) | three_points (points) | face (face: planar face key) | edge (edge key or curve
    body id, t, flip) | angle (face, edge, angle deg: through the edge, rotated from the face) | midplane (faces:
    two parallel planar faces). offset (mm) moves every result along its normal; flip reverses the normal."""
    from build123d import Vector
    m = f.get("method") or "principal"
    if m == "principal":
        n, x = PRINCIPAL_FRAMES[f.get("plane", "XY")]
        fr = _frame_of([0, 0, 0], n, x)
    elif m == "datum":
        base = datum_get(datums, f.get("plane_ref"))
        if not base or "z" not in base:
            raise ValueError("the reference plane was not found")
        fr = dict(base)
    elif m == "point_normal":
        p = ref_point(datums, f["point_ref"]) if f.get("point_ref") else (f.get("point") or [0, 0, 0])
        n = ref_axis(datums, f["axis_ref"])["d"] if f.get("axis_ref") else (f.get("normal") or [0, 0, 1])
        fr = _frame_of(p, n)
    elif m == "axis_point":
        ax = ref_axis(datums, f.get("axis_ref"))
        p = ref_point(datums, f.get("point_ref"))
        v = [p[k] - ax["o"][k] for k in range(3)]
        d = ax["d"]
        n = [d[1] * v[2] - d[2] * v[1], d[2] * v[0] - d[0] * v[2], d[0] * v[1] - d[1] * v[0]]
        if math.sqrt(sum(x * x for x in n)) < 1e-9:
            raise ValueError("the point lies on the axis")
        fr = _frame_of(ax["o"], n, d)
    elif m == "normal_axis":
        ax = ref_axis(datums, f.get("axis_ref"))
        p = ref_point(datums, f["point_ref"]) if f.get("point_ref") else ax["o"]
        fr = _frame_of(p, ax["d"])
    elif m == "three_points":
        pts = [Vector(*q) for q in (f.get("points") or [])]
        if len(pts) != 3:
            raise ValueError("three points are needed")
        n = (pts[1] - pts[0]).cross(pts[2] - pts[0])
        if n.length < 1e-9:
            raise ValueError("the three points are on one line")
        fr = _frame_of(pts[0], n, pts[1] - pts[0])
    elif m == "face":
        _, c, n = _planar_face(shape, f.get("face"))
        fr = _frame_of(c, n)
    elif m == "edge":
        curve = reference_curve(shape, bodies, f.get("edge"), f.get("curve"), f)
        fr = normal_frame(curve, curve_t(curve, f))
    elif m == "angle":
        _, c, n = _planar_face(shape, f.get("face"))
        curve = reference_curve(shape, bodies, f.get("edge"), f.get("curve"), f)
        d = curve.tangent_at(0.5)
        d = Vector(d.X, d.Y, d.Z).normalized()
        o = curve.position_at(0.5)
        nv = Vector(*n)
        nv = (nv - d * nv.dot(d)).normalized()
        a = math.radians(float(f.get("angle", 0) or 0))
        n2 = nv * math.cos(a) + d.cross(nv) * math.sin(a)
        fr = _frame_of([o.X, o.Y, o.Z], n2, d)
    elif m == "midplane":
        refs = f.get("faces") or []
        if len(refs) != 2:
            raise ValueError("two faces are needed")
        _, c1, n1 = _planar_face(shape, refs[0], "first face")
        _, c2, n2 = _planar_face(shape, refs[1], "second face")
        v1, v2 = Vector(*n1), Vector(*n2)
        if abs(abs(v1.dot(v2)) - 1) > 1e-3:
            raise ValueError("the two faces are not parallel")
        d = (Vector(*c2) - Vector(*c1)).dot(v1)
        o = Vector(*c1) + v1 * (d / 2)
        fr = _frame_of(o, v1)
    else:
        raise ValueError("unknown plane method %s" % m)
    if f.get("flip"):
        fr = _frame_of(fr["o"], [-v for v in fr["z"]], fr["x"])
    off = float(f.get("offset", 0) or 0)
    if off:
        fr["o"] = [round(fr["o"][k] + fr["z"][k] * off, 9) for k in range(3)]
    return fr


def resolve_plane(f, shape, bodies=None, datums=None):
    """Sets f["_frame"] for a feature whose sketch plane is "normal" (normal to an edge of the solid, plane_edge,
    or to a curve body, plane_curve, at the fraction plane_t of the length; plane_flip reverses the normal) or
    "datum" (a plane feature, plane_ref)."""
    pl = f.get("plane")
    if pl == "normal" and f.get("plane_axis"):
        ax = ref_axis(datums, f["plane_axis"])
        o = ref_point(datums, f["plane_point"]) if f.get("plane_point") else ax["o"]
        d = [-v for v in ax["d"]] if f.get("plane_flip") else ax["d"]
        f["_frame"] = _frame_of(o, d)
        return f["_frame"]
    if pl == "normal":
        curve = reference_curve(shape, bodies, f.get("plane_edge"), f.get("plane_curve"))
        f["_frame"] = normal_frame(curve, f.get("plane_t", 0.5), bool(f.get("plane_flip")))
        return f["_frame"]
    if pl == "datum":
        base = datum_get(datums, f.get("plane_ref"))
        if not base or "z" not in base:
            raise ValueError("the reference plane was not found (choose a plane feature above this one)")
        f["_frame"] = dict(base)
        return f["_frame"]
    if pl == "face":
        _, c, n = _planar_face(shape, f.get("plane_face"), "sketch face")
        f["_frame"] = _frame_of(c, n)
        return f["_frame"]
    f.pop("_frame", None)
    return None


# --------------------------------------------------------------------------- profiles

def _arc_pts(cx, cy, r, a0, a1):
    span = (a1 - a0) % 360.0 or 360.0
    am = a0 + span / 2.0
    p = lambda a: (cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
    return p(a0), p(am), p(a0 + span)


def ellipse_pt(d, t):
    """Point of an ellipse (cx, cy, rx, ry, rot deg, ...) at the parameter angle t (deg)."""
    cx, cy, rx, ry, rot = d[0], d[1], d[2], d[3], math.radians(d[4])
    tt = math.radians(t)
    x, y = rx * math.cos(tt), ry * math.sin(tt)
    return (cx + x * math.cos(rot) - y * math.sin(rot), cy + x * math.sin(rot) + y * math.cos(rot))


def conic_pt(d, t):
    """Point of a conic (x0, y0, x1, y1, xt, yt, rho) at the parameter t (0..1): rational quadratic Bezier."""
    x0, y0, x1, y1, xt, yt, rho = d[:7]
    rho = min(0.999, max(0.001, float(rho)))
    w = rho / (1.0 - rho)
    a, b, c = (1 - t) ** 2, 2 * w * t * (1 - t), t * t
    den = a + b + c
    return ((a * x0 + b * xt + c * x1) / den, (a * y0 + b * yt + c * y1) / den)


def spline_curve(S, W, start_span=0):
    """The sketch spline (solution S of sketch._spline_solve) as a 3D cubic B-spline curve, spans counted from
    start_span (a closed spline wraps), parameter the chord length (span_par maps span index plus fraction to it).
    Each span is the exact cubic of the sketch."""
    from .sketch import spline_span_hermite
    from OCP.Geom import Geom_BezierCurve
    from OCP.GeomConvert import GeomConvert_CompCurveToBSplineCurve
    from OCP.gp import gp_Pnt
    from OCP.collections import Array1_gp_Pnt
    nsp = S[2]
    comp = None
    for j in range(nsp):
        i = (start_span + j) % nsp
        p0, p1, d0, d1 = spline_span_hermite(S, i)
        c0 = W(p0)
        c3 = W(p1)
        c1 = W((p0[0] + d0[0] / 3.0, p0[1] + d0[1] / 3.0))
        c2 = W((p1[0] - d1[0] / 3.0, p1[1] - d1[1] / 3.0))
        arr = Array1_gp_Pnt(1, 4)
        for n, v in enumerate((c0, c1, c2, c3)):
            arr.SetValue(n + 1, gp_Pnt(v.X, v.Y, v.Z))
        bz = Geom_BezierCurve(arr)
        if comp is None:
            comp = GeomConvert_CompCurveToBSplineCurve(bz)
        elif not comp.Add(bz, 1e-7, True, False, 1):
            raise ValueError("the spline spans do not join")
    bs = comp.BSplineCurve()
    # the spans are Bezier pieces (interior knots of multiplicity 3: C0 in OCCT terms). The sketch spline is C2 in
    # the chord-length parameter: the knots are set to the cumulative chord lengths and reduced to multiplicity 1
    # (exact), so offset, shell and thicken see a C2 surface. Parameter: span_par.
    from OCP.collections import Array1_double
    h = S[1]
    if bs.NbKnots() == nsp + 1:
        ks = Array1_double(1, nsp + 1)
        u = 0.0
        ks.SetValue(1, 0.0)
        for j in range(nsp):
            u += h[(start_span + j) % nsp]
            ks.SetValue(j + 2, u)
        bs.SetKnots(ks)
        for i in range(2, bs.NbKnots()):
            bs.RemoveKnot(i, 1, 1e-7)
    return bs


def span_par(S, start_span, t):
    """Parameter of spline_curve(S, W, start_span) at t (span index plus fraction, counted from start_span)."""
    h, nsp = S[1], S[2]
    j = int(math.floor(t))
    j = min(max(j, 0), nsp - 1) if nsp else 0
    return sum(h[(start_span + i) % nsp] for i in range(j)) + (t - j) * h[(start_span + j) % nsp]


def seg_edge(k, a, b, m, W, plane=None):
    """3D edge of a profile segment: line, three-point arc, or elliptical arc (data cx, cy, rx, ry, rot, a0, a1)."""
    from build123d import Edge
    if k == "line":
        return Edge.make_line(W(a), W(b))
    if k == "arc":
        return Edge.make_three_point_arc(W(a), W(m), W(b))
    if k == "spl":
        # fit points of the whole spline, closed flag, part (None: whole / trimmed; 0/1: half of a closed spline),
        # t0, t1 (parameter range of a trimmed spline: span index plus fraction)
        pts, closed, part, t0, t1 = m
        from .sketch import _spline_solve
        from OCP.Geom import Geom_TrimmedCurve
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        S = _spline_solve(pts, bool(closed))
        nsp = S[2]
        if part is not None:
            mid = len(pts) // 2
            crv = spline_curve(S, W, 0)
            um, ue = span_par(S, 0, float(mid)), span_par(S, 0, float(nsp))
            seg = Geom_TrimmedCurve(crv, 0.0, um) if part == 0 else Geom_TrimmedCurve(crv, um, ue)
            return Edge(BRepBuilderAPI_MakeEdge(seg).Edge())
        if t0 is None and t1 is None:
            return Edge(BRepBuilderAPI_MakeEdge(spline_curve(S, W, 0)).Edge())
        t0 = 0.0 if t0 is None else float(t0)
        t1 = float(nsp) if t1 is None else float(t1)
        if closed:
            s0 = int(math.floor(t0)) % nsp
            crv = spline_curve(S, W, s0)
            a0, a1 = t0 - math.floor(t0), t1 - math.floor(t0)
            while a1 <= a0 + 1e-9:
                a1 += nsp
            if a1 > nsp + 1e-9:
                a1 = min(a1, float(nsp))
            return Edge(BRepBuilderAPI_MakeEdge(Geom_TrimmedCurve(crv, span_par(S, s0, a0), span_par(S, s0, a1))).Edge())
        crv = spline_curve(S, W, 0)
        if t1 < t0:
            t0, t1 = t1, t0
        return Edge(BRepBuilderAPI_MakeEdge(Geom_TrimmedCurve(crv, span_par(S, 0, max(0.0, t0)), span_par(S, 0, min(float(nsp), t1)))).Edge())
    if k == "con":
        from OCP.Geom import Geom_BezierCurve, Geom_TrimmedCurve
        from OCP.gp import gp_Pnt
        from OCP.collections import Array1_gp_Pnt, Array1_double
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        x0, y0, x1, y1, xt, yt, rho, t0, t1 = m
        rho = min(0.999, max(0.001, float(rho)))
        arr = Array1_gp_Pnt(1, 3)
        for n, q in enumerate((W((x0, y0)), W((xt, yt)), W((x1, y1)))):
            arr.SetValue(n + 1, gp_Pnt(q.X, q.Y, q.Z))
        wts = Array1_double(1, 3)
        wts.SetValue(1, 1.0)
        wts.SetValue(2, rho / (1.0 - rho))
        wts.SetValue(3, 1.0)
        crv = Geom_BezierCurve(arr, wts)
        t0 = 0.0 if t0 is None else float(t0)
        t1 = 1.0 if t1 is None else float(t1)
        if t1 < t0:
            t0, t1 = t1, t0
        if t0 > 1e-9 or t1 < 1 - 1e-9:
            crv = Geom_TrimmedCurve(crv, max(0.0, t0), min(1.0, t1))
        return Edge(BRepBuilderAPI_MakeEdge(crv).Edge())
    if k == "ell":
        from OCP.Geom import Geom_Ellipse
        from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        cx, cy, rx, ry, rot, a0, a1 = m
        c = W((cx, cy))
        rr = math.radians(rot)
        ux = W((cx + math.cos(rr), cy + math.sin(rr))) - c
        n = W((cx, cy)) - W((cx, cy))
        # plane normal from two in-plane directions
        uy = W((cx - math.sin(rr), cy + math.cos(rr))) - c
        nz = ux.cross(uy)
        if rx >= ry:
            ax2 = gp_Ax2(gp_Pnt(c.X, c.Y, c.Z), gp_Dir(nz.X, nz.Y, nz.Z), gp_Dir(ux.X, ux.Y, ux.Z))
            ell = Geom_Ellipse(ax2, rx, ry)
            t0, t1 = math.radians(a0), math.radians(a1)
        else:
            # Geom_Ellipse needs major >= minor: major along the local y direction, parameter shifted by -90 deg
            ax2 = gp_Ax2(gp_Pnt(c.X, c.Y, c.Z), gp_Dir(nz.X, nz.Y, nz.Z), gp_Dir(uy.X, uy.Y, uy.Z))
            ell = Geom_Ellipse(ax2, ry, rx)
            t0, t1 = math.radians(a0 - 90), math.radians(a1 - 90)
        return Edge(BRepBuilderAPI_MakeEdge(ell, t0, t1).Edge())
    raise ValueError("unknown segment kind %s" % k)


def sketch_tool_edges(feats, frames, planes, sid):
    """3D edges of the curves of the sketch feature sid (frames: resolved sketch frames by id, planes: datums)."""
    from . import surfaces as sfm
    skf = next((x for x in feats if x.get("id") == sid), None)
    if skf is None:
        raise ValueError("sketch %s was not found" % sid)
    g = dict(skf)
    g["_frame"] = frames.get(sid) or g.get("_frame")
    g["_datums"] = planes
    return sfm.sketch_edges(g, plane_of, _segments)


def sketch_wires(part):
    """3D curves of the sketches of a part that no other feature uses (not suppressed, not hidden): one entry per
    sketch {"id", "name", "lines": [[x, y, z], ...] polylines, "points": [x, y, z] curve ends, circle centres and
    sketch points}. Construction entities and entities on layers that are off are left out."""
    import json as _json
    feats = normalize(part)
    dz = {}
    _shape, st = build(part, datums=dz)
    frames = {x.get("id"): x["frame"] for x in st if x.get("frame")}
    hidden = set(part.get("hidden") or [])
    raw = [f for f in part.get("features") or [] if not f.get("suppressed")]
    out = []
    for f in feats:
        sid = f.get("id")
        if f.get("type") != "sketch" or f.get("suppressed") or sid in hidden:
            continue
        tag = _json.dumps(sid)
        if any(g.get("id") != sid and tag in _json.dumps(g) for g in raw):
            continue                                   # a profile, path or tool of another feature
        try:
            edges = sketch_tool_edges(feats, frames, dz, sid)
            g = dict(f)
            g["_frame"] = frames.get(sid) or g.get("_frame")
            g["_datums"] = dz
            plane = plane_of(g)
        except Exception:
            continue
        lines, pts = [], []
        P = lambda v: [round(v.X, 6), round(v.Y, 6), round(v.Z, 6)]
        for e in edges:
            gt = getattr(e.geom_type, "name", e.geom_type)
            if str(gt).upper() == "LINE":
                lines.append([P(e.position_at(0)), P(e.position_at(1))])
            else:
                n = max(8, min(96, int(e.length / 2.0)))
                lines.append([P(e.position_at(i / n)) for i in range(n + 1)])
            if e.is_closed:
                pts.append(P(e.arc_center) if str(gt).upper() == "CIRCLE" else P(e.position_at(0)))
            else:
                pts += [P(e.position_at(0)), P(e.position_at(1))]
        lays = {l["name"]: l for l in (f.get("sketch") or {}).get("layers") or []}
        for en in (f.get("sketch") or {}).get("entities") or []:
            lay = lays.get(en.get("layer", "0"))
            if en.get("t") == "point" and not en.get("constr") and not en.get("axis") and (lay is None or lay.get("on", True)):
                from build123d import Vector
                pts.append(P(plane.from_local_coords(Vector(en["x"], en["y"], 0))))
        seen, upts = set(), []
        for q in pts:
            k = tuple(round(v, 4) for v in q)
            if k not in seen:
                seen.add(k)
                upts.append(q)
        out.append({"id": sid, "name": f.get("name") or sid, "lines": lines, "points": upts})
    return out


def _segments(sketch, smooth=True):
    """Profile segments (local coordinates) from the visible, non-construction sketch entities.
    Returns (segments, circles); segment = (kind, start, end, data). smooth: a polygon profile and a closed
    polyline sampling a smooth curve (smooth_polygon) become one periodic spline; False keeps the segments."""
    lays = {l["name"]: l for l in sketch.get("layers") or []}
    segs, circles = [], []
    for e in sketch.get("entities") or []:
        if e.get("constr"):
            continue
        lay = lays.get(e.get("layer", "0"))
        if lay is not None and not lay.get("on", True):
            continue
        t = e["t"]
        if t == "line":
            a, b = (e["x1"], e["y1"]), (e["x2"], e["y2"])
            if math.hypot(b[0] - a[0], b[1] - a[1]) > TOL:
                segs.append(("line", a, b, None))
        elif t == "arc":
            s, m, f = _arc_pts(e["cx"], e["cy"], e["r"], e["a0"], e["a1"])
            segs.append(("arc", s, f, m))
        elif t == "circle":
            circles.append((e["cx"], e["cy"], e["r"]))
        elif t == "ellipse":
            a0, a1 = float(e.get("a0", 0) or 0), float(e.get("a1", 0) or 0)
            full = abs(((a1 - a0) % 360.0)) < 1e-9
            data = (e["cx"], e["cy"], e["rx"], e["ry"], float(e.get("rot", 0) or 0), a0, a1 if not full else a0 + 360.0)
            if full:
                # a closed ellipse: two half arcs so the loop finder sees a loop
                m = a0 + 180.0
                segs.append(("ell", ellipse_pt(data, a0), ellipse_pt(data, m), data[:5] + (a0, m)))
                segs.append(("ell", ellipse_pt(data, m), ellipse_pt(data, a0 + 360.0), data[:5] + (m, a0 + 360.0)))
            else:
                segs.append(("ell", ellipse_pt(data, a0), ellipse_pt(data, a1 if a1 > a0 else a1 + 360.0), data[:5] + (a0, a1 if a1 > a0 else a1 + 360.0)))
        elif t == "conic":
            data = (e["x0"], e["y0"], e["x1"], e["y1"], e["xt"], e["yt"], float(e.get("rho", 0.5) or 0.5))
            t0 = e.get("t0")
            t1 = e.get("t1")
            t0 = 0.0 if t0 is None else float(t0)
            t1 = 1.0 if t1 is None else float(t1)
            a, b = conic_pt(data, t0), conic_pt(data, t1)
            if math.hypot(b[0] - a[0], b[1] - a[1]) > TOL:
                segs.append(("con", a, b, data + (t0, t1)))
        elif t == "spline":
            from .sketch import spline_range, _spline_solve, spline_at
            pts = [tuple(p) for p in e["pts"]]
            if len(pts) < 2:
                continue
            trimmed = e.get("t0") is not None or e.get("t1") is not None
            if e.get("closed") and len(pts) >= 3 and not trimmed:
                mid = len(pts) // 2
                segs.append(("spl", pts[0], pts[mid], (pts, True, 0, None, None)))
                segs.append(("spl", pts[mid], pts[0], (pts, True, 1, None, None)))
            elif trimmed:
                t0, t1 = spline_range(e)
                S = _spline_solve(pts, bool(e.get("closed")))
                a, b = spline_at(S, t0), spline_at(S, t1)
                if math.hypot(b[0] - a[0], b[1] - a[1]) > TOL:
                    segs.append(("spl", a, b, (pts, bool(e.get("closed")), None, t0, t1)))
            else:
                segs.append(("spl", pts[0], pts[-1], (pts, False, None, None, None)))
        elif t == "poly" and not e.get("fill"):
            pts = [tuple(p) for p in e["pts"]]
            if e.get("closed") and len(pts) > 1 and math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) <= TOL:
                pts = pts[:-1]
            if smooth and e.get("closed") and smooth_polygon(pts, bool(e.get("pprof"))):
                # a closed polyline that samples a smooth curve (polygon profile, or every corner below 15 deg):
                # one periodic spline through the vertices, so faces built from it are smooth
                mid = len(pts) // 2
                segs.append(("spl", pts[0], pts[mid], (pts, True, 0, None, None)))
                segs.append(("spl", pts[mid], pts[0], (pts, True, 1, None, None)))
                continue
            if e.get("closed") and pts:
                pts.append(pts[0])
            for a, b in zip(pts, pts[1:]):
                if math.hypot(b[0] - a[0], b[1] - a[1]) > TOL:
                    segs.append(("line", a, b, None))
    return segs, circles


def smooth_polygon(pts, force=False, angle=15.0, min_pts=12):
    """True when a closed polyline is the sampling of a smooth curve: force (a polygon profile), or at least
    min_pts vertices with every turning angle below angle (deg)."""
    n = len(pts)
    if n < 4:
        return False
    if force:
        return True
    if n < min_pts:
        return False
    c = math.cos(math.radians(angle))
    for i in range(n):
        a, b, d = pts[i - 1], pts[i], pts[(i + 1) % n]
        u, v = (b[0] - a[0], b[1] - a[1]), (d[0] - b[0], d[1] - b[1])
        lu, lv = math.hypot(*u), math.hypot(*v)
        if lu <= TOL or lv <= TOL:
            continue
        if (u[0] * v[0] + u[1] * v[1]) / (lu * lv) < c:
            return False
    return True


def _loops(segs, scale):
    """Closed loops of segments. Returns (loops, open_points); loop = [(seg, reversed), ...]."""
    tol = max(1e-6, 1e-7 * scale)
    nodes = []

    def node(p):
        for i, q in enumerate(nodes):
            if abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol:
                return i
        nodes.append(p)
        return len(nodes) - 1

    ends = [(node(s[1]), node(s[2])) for s in segs]
    adj = {}
    for i, (a, b) in enumerate(ends):
        adj.setdefault(a, []).append(i)
        adj.setdefault(b, []).append(i)
    open_pts = [nodes[n] for n, l in adj.items() if len(l) != 2]
    used = [False] * len(segs)
    loops = []
    for i in range(len(segs)):
        if used[i]:
            continue
        a, b = ends[i]
        if len(adj.get(a, [])) != 2 or len(adj.get(b, [])) != 2:
            continue
        loop = [(i, False)]
        used[i] = True
        cur, start = b, a
        ok = True
        while cur != start:
            nxt = [j for j in adj[cur] if not used[j]]
            if not nxt:
                ok = False
                break
            j = nxt[0]
            used[j] = True
            rev = ends[j][1] == cur
            loop.append((j, rev))
            cur = ends[j][0] if rev else ends[j][1]
        if ok:
            loops.append(loop)
    return loops, open_pts


def _poly_of_loop(loop, segs):
    pts = []
    for i, rev in loop:
        k, a, b, m = segs[i]
        if k == "line":
            seq = [a, b]
        elif k == "ell":
            n = 32
            seq = [ellipse_pt(m, m[5] + (m[6] - m[5]) * j / n) for j in range(n + 1)]
        elif k == "con":
            n = 32
            seq = [conic_pt(m, m[7] + (m[8] - m[7]) * j / n) for j in range(n + 1)]
        elif k == "spl":
            from .sketch import spline_pts
            pts, closed, part, t0, t1 = m
            if part is None:
                seq = spline_pts(pts, closed, 12, t0, t1)
            else:
                mid = len(pts) // 2
                full = spline_pts(pts, True, 12)
                seq = full[:mid * 12 + 1] if part == 0 else full[mid * 12:]
        else:
            seq = _sample_arc3(a, m, b, 24)
        if rev:
            seq = seq[::-1]
        pts += seq[:-1]
    return pts


def _sample_arc3(a, m, b, n):
    # circle through three points
    ax, ay = a
    bx, by = m
    cx, cy = b
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return [a, b]
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    t0 = math.atan2(ay - uy, ax - ux)
    tm = math.atan2(by - uy, bx - ux)
    t1 = math.atan2(cy - uy, cx - ux)
    ccw = (tm - t0) % (2 * math.pi) < (t1 - t0) % (2 * math.pi)
    span = (t1 - t0) % (2 * math.pi) if ccw else -((t0 - t1) % (2 * math.pi))
    return [(ux + r * math.cos(t0 + span * k / n), uy + r * math.sin(t0 + span * k / n)) for k in range(n + 1)]


def _area(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                     for i in range(len(pts)))


def _inside(p, pts):
    x, y = p
    ins = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            ins = not ins
    return ins


def profile_faces(sketch, plane, notes=None):
    """Faces (build123d) on the plane from the closed loops of the sketch; nested loops are holes. Open chains
    are ignored when at least one closed profile exists (a note is appended to notes); with no closed profile
    the open ends are reported in the error."""
    from build123d import Edge, Wire, Face, Vector
    segs, circles = _segments(sketch)
    allp = [p for s in segs for p in (s[1], s[2])] + [(c[0], c[1]) for c in circles]
    scale = max([abs(v) for p in allp for v in p] + [1.0])
    loops, open_pts = _loops(segs, scale)
    if open_pts:
        text = "open sketch chain ignored, ends at %s" % ", ".join("(%.3f, %.3f)" % p for p in open_pts[:4]) + (" ..." if len(open_pts) > 4 else "")
        if not loops and not circles:
            raise ValueError("sketch profile is not closed at %s" %
                             ", ".join("(%.3f, %.3f)" % p for p in open_pts[:4]) + (" ..." if len(open_pts) > 4 else ""))
        if notes is not None:
            notes.append(text)
    W = lambda p: plane.from_local_coords(Vector(p[0], p[1], 0))
    items = []                      # (abs area, polygon, wire)
    for loop in loops:
        edges = []
        for i, rev in loop:
            k, a, b, m = segs[i]
            edges.append(seg_edge(k, a, b, m, W))
        poly = _poly_of_loop(loop, segs)
        items.append((abs(_area(poly)), poly, Wire(edges)))
    for cx, cy, r in circles:
        from build123d import Plane
        cp = Plane(origin=W((cx, cy)), x_dir=plane.x_dir, z_dir=plane.z_dir)
        poly = [(cx + r * math.cos(2 * math.pi * k / 48), cy + r * math.sin(2 * math.pi * k / 48)) for k in range(48)]
        items.append((math.pi * r * r, poly, Wire([Edge.make_circle(r, cp)])))
    if not items:
        raise ValueError("sketch has no closed profile")
    items.sort(key=lambda t: -t[0])
    parent = [-1] * len(items)
    depth = [0] * len(items)
    for i in range(len(items)):
        probe = items[i][1][0]
        for j in range(i - 1, -1, -1):
            if items[j][0] > items[i][0] and _inside(probe, items[j][1]):
                parent[i] = j
                depth[i] = depth[j] + 1
                break
    faces = []
    for i, it in enumerate(items):
        if depth[i] % 2:
            continue
        holes = [items[j][2] for j in range(len(items)) if parent[j] == i]
        faces.append(Face(it[2], holes) if holes else Face(it[2]))
    return faces


def profile_regions(sketch, plane):
    """All bounded regions of the sketch: the profile faces split by every sketch curve (crossing lines partition
    a loop). Returns [(face, uv)] with uv the local coordinates of a point inside each region."""
    from build123d import Vector, Shape, Edge, Plane
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from . import surfaces as sfm
    faces = profile_faces(sketch, plane, [])
    segs, circles = _segments(sketch)
    W = lambda q: plane.from_local_coords(Vector(q[0], q[1], 0))
    tools = [seg_edge(k, a, b, m, W) for k, a, b, m in segs]
    for cx, cy, r in circles:
        tools.append(Edge.make_circle(r, Plane(origin=W((cx, cy)), x_dir=plane.x_dir, z_dir=plane.z_dir)))
    args, tl = sfm._shape_list(), sfm._shape_list()
    for fc in faces:
        args.Append(fc.wrapped)
    for e in tools:
        tl.Append(e.wrapped)
    pieces = list(faces)
    try:
        op = BRepAlgoAPI_Splitter()
        op.SetArguments(args)
        op.SetTools(tl)
        op.SetRunParallel(True)
        op.Build()
        if op.IsDone():
            got = list(Shape.cast(op.Shape()).faces())
            if got:
                pieces = got
    except Exception:
        pass
    out = []
    for fc in pieces:
        if fc.area < 1e-9:
            continue
        q = sfm._point_on(fc)
        loc = plane.to_local_coords(q)
        out.append((fc, (round(loc.X, 6), round(loc.Y, 6))))
    return out


def select_regions(sketch, plane, regions):
    """The profile regions containing the local points in regions ([[u, v], ...])."""
    from build123d import Vector
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    pieces = profile_regions(sketch, plane)
    out = []
    for fc, _uv in pieces:
        for uv in regions:
            v = plane.from_local_coords(Vector(uv[0], uv[1], 0))
            st = BRepClass_FaceClassifier(fc.wrapped, gp_Pnt(v.X, v.Y, v.Z), 1e-6).State()
            if st in (TopAbs_IN, TopAbs_ON):
                out.append(fc)
                break
    if not out:
        raise ValueError("none of the picked regions exists in the sketch any more: pick the regions again")
    return out


# --------------------------------------------------------------------------- features

def _axis(f, plane, sketch):
    from build123d import Axis, Vector
    ax = f.get("axis", "v")
    W = lambda p: plane.from_local_coords(Vector(p[0], p[1], 0))
    if f.get("axis_ref"):
        a = ref_axis(f.get("_datums"), f["axis_ref"])
        return Axis(Vector(*a["o"]), Vector(*a["d"]))
    if ax == "u":
        a, b = (0.0, 0.0), (1.0, 0.0)
    elif ax == "v":
        a, b = (0.0, 0.0), (0.0, 1.0)
    else:
        e = next((x for x in sketch.get("entities") or [] if x.get("id") == ax and x["t"] == "line"), None)
        if e is None:
            raise ValueError("revolve axis line %s not found in the sketch" % ax)
        a, b = (e["x1"], e["y1"]), (e["x2"], e["y2"])
    pa, pb = W(a), W(b)
    return Axis(pa, pb - pa)


def _solid_of(f, faces, size):
    from build123d import Solid, Vector
    plane = plane_of(f)
    n = Vector(plane.z_dir)
    out = []
    if f["type"] in ("extrude", "cut"):
        through = f["type"] == "cut" and f.get("through")
        d = 2.0 * size + 10.0 if through else float(f.get("depth", 10) or 0)
        if d <= 0:
            raise ValueError("depth must be > 0")
        sym = f.get("symmetric") or through
        sgn = -1.0 if f.get("reverse") else 1.0
        for face in faces:
            if sym:
                face = face.translate(n * (-d / 2.0))
                out.append(Solid.extrude(face, n * d))
            else:
                out.append(Solid.extrude(face, n * (sgn * d)))
    elif f["type"] == "revolve":
        ang = float(f.get("angle", 360) or 360)
        axis = _axis(f, plane, f.get("sketch") or {})
        for face in faces:
            out.append(Solid.revolve(face, ang, axis))
    else:
        raise ValueError("unknown feature type %s" % f["type"])
    return out


def _fuse(a, b):
    return b if a is None else a.fuse(b).clean()


# --------------------------------------------------------------------------- import, partition, clean-up

def _import(f):
    """Import feature: the solids of a STEP file (one solid, or a compound of solids). The file is read once per
    path, modification time and size (model.step_solids)."""
    import os
    path = (f.get("path") or "").strip().strip('"')
    if not os.path.isfile(path):
        raise ValueError("file not found: %s" % path)
    from . import model
    comp, named = model.step_solids(path)       # solid indices as in the Add STEP list of the Assembly tab
    solids = [s for _, s in named]
    if not solids:
        raise ValueError("the STEP file has no solids")
    want = f.get("part")
    if want not in (None, ""):
        try:
            return solids[int(want)]
        except (ValueError, IndexError, TypeError):
            raise ValueError("solid %s not in the file (%d solids)" % (want, len(solids)))
    return solids[0] if len(solids) == 1 else comp


def _plane_of_split(shape, f):
    """gp_Pln of a split feature: method principal (plane + offset), point_normal, three_points, face (extend a
    planar face), edge (normal to an edge at parameter t)."""
    from OCP.gp import gp_Pln, gp_Pnt, gp_Dir, gp_Vec
    m = f.get("method") or "principal"
    if m == "principal":
        base = {"XY": ((0, 0, 1), 2), "XZ": ((0, 1, 0), 1), "YZ": ((1, 0, 0), 0)}[f.get("plane", "XY")]
        n, k = base
        off = float(f.get("offset", 0) or 0)
        p = [0.0, 0.0, 0.0]
        if f.get("relative"):          # offset measured from the minimum of the bounding box
            bb = shape.bounding_box()
            p[k] = [bb.min.X, bb.min.Y, bb.min.Z][k]
        p[k] += off
        return gp_Pln(gp_Pnt(*p), gp_Dir(*n))
    if m == "point_normal":
        p, n = f.get("point") or [0, 0, 0], f.get("normal") or [0, 0, 1]
        return gp_Pln(gp_Pnt(*[float(v) for v in p]), gp_Dir(*[float(v) for v in n]))
    if m == "three_points":
        pts = [gp_Pnt(*[float(v) for v in q]) for q in (f.get("points") or [])]
        if len(pts) != 3:
            raise ValueError("three points are needed")
        v1, v2 = gp_Vec(pts[0], pts[1]), gp_Vec(pts[0], pts[2])
        n = v1.Crossed(v2)
        if n.Magnitude() < 1e-9:
            raise ValueError("the three points are on one line")
        return gp_Pln(pts[0], gp_Dir(n))
    if m == "edge":
        curve = reference_curve(shape, f.get("_bodies"), f.get("edge"), f.get("curve"), f)
        fr = normal_frame(curve, curve_t(curve, f))
        return gp_Pln(gp_Pnt(*fr["o"]), gp_Dir(*fr["z"]))
    if m == "datum":
        fr = datum_get(f.get("_datums"), f.get("plane_ref"))
        if not fr or "z" not in fr:
            raise ValueError("the reference plane was not found (choose a plane feature above this one)")
        off = float(f.get("offset", 0) or 0)
        o = [fr["o"][k] + fr["z"][k] * off for k in range(3)]
        return gp_Pln(gp_Pnt(*o), gp_Dir(*fr["z"]))
    raise ValueError("unknown partition method %s" % m)


# --------------------------------------------------------------------------- hole mesh (O-grid)

def _og_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _og_cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _og_unit(a):
    L = math.sqrt(_og_dot(a, a)) or 1.0
    return [a[0] / L, a[1] / L, a[2] / L]


def _og_dist_line(p, w, q):
    c = _og_cross([q[i] - p[i] for i in range(3)], w)
    return math.sqrt(_og_dot(c, c))


def _og_kind(s):
    """"block" (6 faces of 4 edges), "prism" (5 faces: 2 of 3 edges, 3 of 4 edges) or ""."""
    fs = s.faces()
    n = sorted(len(f.edges()) for f in fs)
    if n == [4] * 6:
        return "block"
    if n == [3, 3, 4, 4, 4]:
        return "prism"
    return ""


def _split_cells(cells, tools, chosen=None):
    """Splits the chosen cells (indices; all when None) with the tool faces. Returns the new list of cells."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from build123d import Shape
    try:
        from OCP.TopTools import TopTools_ListOfShape as ShapeList
    except ImportError:
        from OCP.collections import List_TopoDS_Shape as ShapeList
    idx = list(range(len(cells))) if chosen is None else list(chosen)
    if not idx or not tools:
        return cells
    args, tl = ShapeList(), ShapeList()
    for i in idx:
        args.Append(cells[i].wrapped)
    for t in tools:
        tl.Append(t)
    op = BRepAlgoAPI_Splitter()
    op.SetArguments(args)
    op.SetTools(tl)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise ValueError("the partition failed")
    new = list(Shape.cast(op.Shape()).solids())
    sel = set(idx)
    return [c for i, c in enumerate(cells) if i not in sel] + new


def hole_axes(shape, faces):
    """Holes of the picked cylindrical faces: [{"p": point on the axis, "w": axis direction, "radii": [...]}]. All
    cylindrical faces of the part on the same axis belong to the hole (bore, counterbore)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    cyls = []
    for fc in shape.faces():
        ad = BRepAdaptor_Surface(fc.wrapped)
        if ad.GetType() == GeomAbs_Cylinder:
            cy = ad.Cylinder()
            L, D = cy.Axis().Location(), cy.Axis().Direction()
            cyls.append((fc, [L.X(), L.Y(), L.Z()], [D.X(), D.Y(), D.Z()], cy.Radius()))
    holes = []
    for f in faces:
        mine = [c for c in cyls if c[0].wrapped.IsSame(f.wrapped)]
        if not mine:
            raise ValueError("a picked face is not cylindrical")
        _, p, w, r = mine[0]
        if any(abs(abs(_og_dot(w, h["w"])) - 1) < 1e-9 and _og_dist_line(h["p"], h["w"], p) < 1e-6 for h in holes):
            continue                                                       # another face of the same hole
        radii = sorted({round(c[3], 9) for c in cyls
                        if abs(abs(_og_dot(c[2], w)) - 1) < 1e-9 and _og_dist_line(p, w, c[1]) < 1e-6})
        holes.append({"p": p, "w": _og_unit(w), "radii": radii})
    return holes


def _hole_mesh(shape, f):
    """Hole mesh (O-grid partition) of holes through a planar part. For each hole: planes through the axis along the
    in-plane directions u and v, the sides of a square around the hole (side = factor x largest hole diameter) and
    planes normal to the axis at the steps of the hole (counterbore, blind bottom), all through the whole part; the
    hole cylinders extended through the cells of the square that they pass through; the two diagonals through the
    axis inside the square. The cells become blocks (6 faces of 4 edges) or, below a blind hole, prisms. Returns the
    shape with the attribute _ogrid (cell counts and the mesh seeds of the holes)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Pln, gp_Pnt, gp_Dir, gp_Ax3
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from build123d import Compound, Shape
    picked = find_faces(shape, f.get("faces") or [])
    if not picked:
        raise ValueError("pick a cylindrical face of each hole")
    holes = hole_axes(shape, picked)
    w = holes[0]["w"]
    if any(abs(abs(_og_dot(h["w"], w)) - 1) > 1e-6 for h in holes):
        raise ValueError("the holes are not parallel")
    # in-plane frame along the global axis most perpendicular to the hole axis (the part edges are normally
    # parallel to the global axes)
    k = min(range(3), key=lambda i: abs(w[i]))
    a = [0.0, 0.0, 0.0]
    a[k] = 1.0
    u = _og_unit([a[i] - w[i] * _og_dot(a, w) for i in range(3)])
    v = _og_cross(w, u)
    bb = shape.bounding_box()
    big = bb.diagonal * 2 + 10
    tol = 1e-6 * max(bb.diagonal, 1.0)
    corners = [[x, y, z] for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y) for z in (bb.min.Z, bb.max.Z)]
    ext = {key: (min(_og_dot(c, e) for c in corners), max(_og_dot(c, e) for c in corners))
           for key, e in (("u", u), ("v", v), ("w", w))}
    factor = float(f.get("factor") or 2.0)
    for h in holes:
        h["u"], h["v"], h["R"] = _og_dot(h["p"], u), _og_dot(h["p"], v), max(h["radii"])
    # half side of the squares: factor x largest radius, limited so that the square lines of one hole do not cross
    # the square of another
    half = min(factor * h["R"] for h in holes)
    for i, ha in enumerate(holes):
        for hb in holes[i + 1:]:
            for key in ("u", "v"):
                d = abs(ha[key] - hb[key])
                if d > tol:
                    half = min(half, d / 2.0)
    for h in holes:                                     # the square stays inside the part (its bounding box)
        for key in ("u", "v"):
            half = min(half, h[key] - ext[key][0], ext[key][1] - h[key])
    rmax = max(h["R"] for h in holes)
    if half < 1.1 * rmax:
        raise ValueError("the holes are too close to each other or to the edge of the part for O-grid squares (square "
                         "half side %.3f mm, hole radius %.3f mm)" % (half, rmax))
    # levels normal to the axis: steps and bottoms of the holes (planar faces normal to the axis within the radius)
    levels = set()
    for fc in shape.faces():
        ad = BRepAdaptor_Surface(fc.wrapped)
        if ad.GetType() != GeomAbs_Plane:
            continue
        n = ad.Plane().Axis().Direction()
        if abs(abs(n.X() * w[0] + n.Y() * w[1] + n.Z() * w[2]) - 1) > 1e-6:
            continue
        vs = [[q.X, q.Y, q.Z] for q in fc.vertices()]
        for h in holes:
            if vs and all(_og_dist_line(h["p"], w, q) <= h["R"] + tol for q in vs):
                lw = _og_dot(vs[0], w)
                if ext["w"][0] + tol < lw < ext["w"][1] - tol:
                    levels.add(round(lw, 9))

    def plane(dist, normal, xdir):
        o = [normal[i] * dist for i in range(3)]
        return BRepBuilderAPI_MakeFace(gp_Pln(gp_Ax3(gp_Pnt(*o), gp_Dir(*normal), gp_Dir(*xdir))), -big, big, -big, big).Face()
    tools, seen = [], set()

    def add(key, val, normal, xdir):
        lo, hi = ext[key]
        if (key, round(val, 6)) in seen or not (lo + tol < val < hi - tol):
            return
        seen.add((key, round(val, 6)))
        tools.append(plane(val, normal, xdir))
    for h in holes:
        for d in (0.0, -half, half):
            add("u", h["u"] + d, u, v)
            add("v", h["v"] + d, v, u)
    for lw in sorted(levels):
        add("w", lw, w, u)
    cells = _split_cells(list(shape.solids()), tools)

    def inside(c, h):
        m = c.center()
        q = [m.X, m.Y, m.Z]
        return abs(_og_dot(q, u) - h["u"]) < half - tol and abs(_og_dot(q, v) - h["v"]) < half - tol
    # the hole cylinders extended through the cells of the square that they pass through
    for h in holes:
        ae = BRepBuilderAPI_MakeEdge(gp_Pnt(*[h["p"][i] - w[i] * big for i in range(3)]),
                                     gp_Pnt(*[h["p"][i] + w[i] * big for i in range(3)])).Edge()
        for r in h["radii"]:
            surf = Geom_CylindricalSurface(gp_Ax3(gp_Pnt(*h["p"]), gp_Dir(*w), gp_Dir(*u)), r)
            tool = BRepBuilderAPI_MakeFace(surf, 0.0, 2 * math.pi, -big, big, 1e-7).Face()
            chosen = []
            for i, c in enumerate(cells):
                if inside(c, h):
                    dd = BRepExtrema_DistShapeShape(c.wrapped, ae)
                    if dd.IsDone() and dd.Value() < r - tol:
                        chosen.append(i)
            cells = _split_cells(cells, [tool], chosen)
    # diagonals through the axis inside the square
    for h in holes:
        nn = [_og_unit([u[i] + v[i] for i in range(3)]), _og_unit([u[i] - v[i] for i in range(3)])]
        cells = _split_cells(cells, [plane(_og_dot(h["p"], n), n, w) for n in nn],
                             [i for i, c in enumerate(cells) if inside(c, h)])
    # a hole cylinder whose seam lies on no cut leaves a face split at the seam: merged again in that cell
    out = []
    for c in cells:
        if not _og_kind(c):
            uu = ShapeUpgrade_UnifySameDomain(c.wrapped, True, True, True)
            uu.Build()
            cc = Shape.cast(uu.Shape()).solids()
            if len(cc) == 1 and abs(cc[0].volume - c.volume) < 1e-6 * max(abs(c.volume), 1.0):
                c = cc[0]
        out.append(c)
    kinds = [_og_kind(c) for c in out]
    res = out[0] if len(out) == 1 else Compound(children=out)
    thick = ext["w"][1] - ext["w"][0]
    res._ogrid = {"blocks": kinds.count("block"), "prisms": kinds.count("prism"), "other": kinds.count(""),
                  "half": half, "holes": len(holes), "levels": sorted(levels),
                  "seeds": [{"p": h["p"], "w": w, "u": u, "v": v, "half": half, "radii": h["radii"], "T": thick,
                             "n_circ": int(f.get("n_circ") or 3), "n_rad": int(f.get("n_rad") or 4),
                             "bias": float(f.get("bias") or 1.0), "n_thick": int(f.get("n_thick") or 4)} for h in holes]}
    return res


def mesh_seeds(status):
    """Mesh seeds of the hole mesh features of a build status (for the structured hexahedral mesh)."""
    out = []
    for st in status or []:
        out += st.get("seeds") or []
    return out


def _ogrid(shape, f):
    """Partition around a hole: four planes through the axis of the picked cylindrical face (two along the
    principal directions of the plane normal to the axis, two diagonals) applied to the cells around the hole."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    faces = find_faces(shape, [f.get("face") or {}])
    if not faces:
        raise ValueError("the hole face was not found")
    ad = BRepAdaptor_Surface(faces[0].wrapped)
    if ad.GetType() != GeomAbs_Cylinder:
        raise ValueError("the picked face is not cylindrical")
    cy = ad.Cylinder()
    L, D = cy.Axis().Location(), cy.Axis().Direction()
    r = cy.Radius()
    n = [D.X(), D.Y(), D.Z()]
    c = faces[0].center()
    # point on the axis at the height of the face centre
    t = (c.X - L.X()) * n[0] + (c.Y - L.Y()) * n[1] + (c.Z - L.Z()) * n[2]
    p = [L.X() + n[0] * t, L.Y() + n[1] * t, L.Z() + n[2] * t]
    # in-plane basis aligned with the global axis that is most perpendicular to the hole axis
    axes = sorted(((abs(n[i]), i) for i in range(3)))
    a = [0.0, 0.0, 0.0]
    a[axes[0][1]] = 1.0
    u = [a[1] * n[2] - a[2] * n[1], a[2] * n[0] - a[0] * n[2], a[0] * n[1] - a[1] * n[0]]
    lu = math.sqrt(sum(x * x for x in u)) or 1.0
    u = [x / lu for x in u]
    v = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]
    rr = r * 1.15
    pts = [{"p": [p[i] + rr * (math.cos(th) * u[i] + math.sin(th) * v[i]) for i in range(3)]}
           for th in (math.radians(22.5 + 45 * k) for k in range(8))]
    normals = [u, v, [u[i] + v[i] for i in range(3)], [u[i] - v[i] for i in range(3)]]
    out = shape
    for nn in normals:
        out = _split(out, {"method": "point_normal", "point": p, "normal": nn, "cells": pts})
    return out


def _split_tools(shape, f, big):
    """Tool faces of a partition: one extended plane, the extended surface of a picked face, or the curves of a
    sketch extruded through the part (CAE: Partition Cell by sketch / extrude edges)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.BRep import BRep_Tool
    from OCP.gp import gp_Vec
    from OCP.Precision import Precision
    m = f.get("method") or "principal"
    if m == "surface":
        body = (f.get("_bodies") or {}).get(f.get("source"))
        if body is None:
            raise ValueError("source surface not found (it must be above this feature)")
        return [fc.wrapped for fc in body.faces()]
    if m == "face":
        faces = find_faces(shape, [f.get("face") or {}])
        if not faces:
            raise ValueError("the face was not found")
        surf = BRep_Tool.Surface_s(faces[0].wrapped)
        off = float(f.get("face_offset", 0) or 0)
        if abs(off) > 1e-9:
            # offset along the face normal (outward normal of the picked face: positive moves away from the material)
            from OCP.Geom import Geom_OffsetSurface
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.GeomAbs import GeomAbs_Plane
            sign = 1.0 if faces[0].wrapped.Orientation() == 0 else -1.0     # FORWARD: surface normal = face normal
            ad = BRepAdaptor_Surface(faces[0].wrapped)
            if ad.GetType() == GeomAbs_Plane:
                n = ad.Plane().Axis().Direction()
                surf = surf.Translated(gp_Vec(n.X() * off * sign, n.Y() * off * sign, n.Z() * off * sign))
            else:
                surf = Geom_OffsetSurface(surf, off * sign)
        u1, u2, v1, v2 = surf.Bounds()
        inf = Precision.Infinite_s() / 2
        u1, u2 = (-big if u1 < -inf else u1), (big if u2 > inf else u2)
        v1, v2 = (-big if v1 < -inf else v1), (big if v2 > inf else v2)
        return [BRepBuilderAPI_MakeFace(surf, u1, u2, v1, v2, 1e-6).Face()]
    if m == "sketch":
        from build123d import Edge, Vector, Location, Plane
        plane = plane_of(f)
        segs, circles = _segments(f.get("sketch") or {})
        W = lambda q: plane.from_local_coords(Vector(q[0], q[1], 0))
        edges = [seg_edge(k, a, b, mm, W) for k, a, b, mm in segs]
        for cx, cy, r in circles:
            edges.append(Edge.make_circle(r, Plane(origin=W((cx, cy)), x_dir=plane.x_dir, z_dir=plane.z_dir)))
        if not edges:
            raise ValueError("the partition sketch has no lines, arcs or circles")
        n = Vector(plane.z_dir)
        out = []
        for e in edges:
            # extruded both ways through the part
            moved = e.moved(Location(-n * big))
            out.append(BRepPrimAPI_MakePrism(moved.wrapped, gp_Vec(n.X * 2 * big, n.Y * 2 * big, n.Z * 2 * big)).Shape())
        return out
    pln = _plane_of_split(shape, f)
    return [BRepBuilderAPI_MakeFace(pln, -big, big, -big, big).Face()]


def _split(shape, f):
    """Partition: cuts cells of the shape with a plane, an extended surface or an extruded sketch
    (Abaqus/CAE: Partition Cell)."""
    if (f.get("method") or "") == "ogrid":
        return _ogrid(shape, f)
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from build123d import Shape
    try:
        from OCP.TopTools import TopTools_ListOfShape as ShapeList
    except ImportError:
        from OCP.collections import List_TopoDS_Shape as ShapeList
    from build123d import Compound
    bb = shape.bounding_box()
    big = bb.diagonal * 2 + 10
    tool_faces = _split_tools(shape, f, big)
    solids = list(shape.solids())
    # cells to partition: the solids owning the picked faces (none picked: all cells)
    refs = f.get("cells") or []
    sel = find_faces(shape, [r for r in refs if "c" in r])
    pts = [r["p"] for r in refs if "p" in r]
    if sel or pts:
        chosen = [so for so in solids if any(any(fc.wrapped.IsSame(x.wrapped) for x in so.faces()) for fc in sel)]
        if pts:
            from OCP.BRepClass3d import BRepClass3d_SolidClassifier
            from OCP.gp import gp_Pnt
            from OCP.TopAbs import TopAbs_IN, TopAbs_ON
            for so in solids:
                if so in chosen:
                    continue
                for q in pts:
                    c = BRepClass3d_SolidClassifier(so.wrapped, gp_Pnt(*[float(v) for v in q]), 1e-6)
                    if c.State() in (TopAbs_IN, TopAbs_ON):
                        chosen.append(so)
                        break
        if not chosen:
            raise ValueError("the picked faces or points belong to no cell")
    else:
        chosen = solids
    args, tools = ShapeList(), ShapeList()
    for so in chosen:
        args.Append(so.wrapped)
    for tool in tool_faces:
        tools.Append(tool)
    op = BRepAlgoAPI_Splitter()
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise ValueError("the partition failed")
    cut = Shape.cast(op.Shape())
    new = list(cut.solids())
    if not new:
        raise ValueError("the partition removed the solid")
    rest = [so for so in solids if so not in chosen]
    if not rest:
        return cut if len(new) > 1 else new[0]
    return Compound(children=rest + new)


def _boolean(shape, f):
    """Boolean between solids of the part: "op": "union" | "subtract" | "intersect"; "targets" and "tools": solid
    indices (order of shape.solids()); "keep_tools" keeps the tool solids as separate solids."""
    from build123d import Compound
    solids = list(shape.solids())
    n = len(solids)
    op = f.get("op") or "union"
    ti = [int(i) for i in f.get("targets") or [] if 0 <= int(i) < n]
    ui = [int(i) for i in f.get("tools") or [] if 0 <= int(i) < n and int(i) not in (f.get("targets") or [])]
    T = [solids[i] for i in ti]
    U = [solids[i] for i in ui]
    if op == "union":
        sel = T + U
        if len(sel) < 2:
            raise ValueError("a union needs at least two solids (targets and tools)")
        res = sel[0].fuse(*sel[1:]).clean()
        new = list(res.solids())
        used = set(ti) | set(ui)
    else:
        if not T or not U:
            raise ValueError("pick the target solid(s) and the tool solid(s)")
        new = []
        for t in T:
            if op == "subtract":
                r = t.cut(*U).clean()
            else:
                r = t
                for u in U:
                    r = r.intersect(u)
                    if isinstance(r, (list, tuple)):
                        r = Compound(children=list(r))
                r = r.clean()
            new += list(r.solids())
        used = set(ti) | (set() if f.get("keep_tools") else set(ui))
        if not new:
            raise ValueError("the %s left nothing of the target" % op)
    rest = [so for i, so in enumerate(solids) if i not in used]
    out = rest + new
    if not out:
        raise ValueError("the boolean left no solid")
    return out[0] if len(out) == 1 else Compound(children=out)


def _unify(shape, f):
    """Merges coplanar faces and collinear/cocircular edges (CAE: Virtual topology / Remove redundant entities)."""
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from build123d import Shape
    u = ShapeUpgrade_UnifySameDomain(shape.wrapped, bool(f.get("edges", True)), bool(f.get("faces", True)), True)
    ang = float(f.get("angle", 0) or 0)
    if ang > 0:
        u.SetAngularTolerance(math.radians(ang))
    u.Build()
    return Shape.cast(u.Shape())


def _heal(shape, f):
    """Shape healing (CAE: Geometry Repair): fixes the topology and removes small edges below the tolerance."""
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Wireframe
    from build123d import Shape
    from OCP.ShapeFix import ShapeFix_FixSmallFace
    tol = float(f.get("tolerance", 0) or 0)
    small = float(f.get("small_faces", 0) or 0)
    v0 = shape.volume
    sh = shape.wrapped
    if small > 0:
        # spot and strip faces narrower than the tolerance (CAE: remove small faces / sliver faces)
        sf = ShapeFix_FixSmallFace()
        sf.Init(sh)
        sf.SetPrecision(small)
        sf.Perform()
        sh = sf.FixShape()
    if tol > 0:
        wf = ShapeFix_Wireframe(sh)
        wf.SetPrecision(tol)
        wf.ModeDropSmallEdges = True
        wf.FixSmallEdges()
        wf.FixWireGaps()
        sh = wf.Shape()
    fx = ShapeFix_Shape(sh)
    if tol > 0:
        fx.SetPrecision(tol)
    fx.Perform()
    out = Shape.cast(fx.Shape())
    try:
        v1 = out.volume
        ok = out.is_valid() if callable(out.is_valid) else out.is_valid
    except Exception:
        v1, ok = 0.0, False
    if not ok or not (0.99 * abs(v0) <= abs(v1) <= 1.01 * abs(v0)):
        raise ValueError("healing with tolerance %g / small faces %g gives an invalid solid (volume %.4g -> %.4g mm^3); "
                         "use a smaller tolerance" % (tol, small, v0, v1))
    return out


def _smooth(shape, f):
    """Re-approximates the B-spline surfaces and curves with smooth splines (degree 3, C2) within a tolerance
    (CAE: convert to analytical / re-approximate). Analytic surfaces are kept. The result is rejected when invalid
    or when the volume changes by more than 1 %."""
    from OCP.ShapeCustom import ShapeCustom, ShapeCustom_RestrictionParameters
    from OCP.GeomAbs import GeomAbs_C1, GeomAbs_C2
    from OCP.ShapeFix import ShapeFix_Shape
    from build123d import Shape
    tol = float(f.get("tolerance") or 0.05)
    seg = int(f.get("segments") or 6)
    cont = GeomAbs_C1 if f.get("continuity") == "C1" else GeomAbs_C2
    prm = ShapeCustom_RestrictionParameters()
    r = ShapeCustom.BSplineRestriction_s(shape.wrapped, tol, tol * 0.1, 3, seg, cont, cont, True, True, prm)
    sf = ShapeFix_Shape(r)
    sf.Perform()
    out = Shape.cast(sf.Shape())
    v0, v1 = shape.volume, out.volume
    ok = out.is_valid() if callable(out.is_valid) else out.is_valid
    if not ok or not (0.99 * abs(v0) <= abs(v1) <= 1.01 * abs(v0)):
        raise ValueError("smoothing with tolerance %g gives an invalid solid (volume %.4g -> %.4g mm^3); use a smaller tolerance" % (tol, v0, v1))
    return out


def _point_on_face(face):
    """A point on the face itself (the centre of mass can lie outside a ring or L-shaped face)."""
    from OCP.BRepTools import BRepTools
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.gp import gp_Pnt2d
    from OCP.TopAbs import TopAbs_IN
    from OCP.BRep import BRep_Tool
    c = face.center()
    u1, u2, v1, v2 = BRepTools.UVBounds_s(face.wrapped)
    surf = BRep_Tool.Surface_s(face.wrapped)
    cands = [(0.5, 0.5), (0.25, 0.5), (0.75, 0.5), (0.5, 0.25), (0.5, 0.75), (0.25, 0.25), (0.75, 0.75), (0.25, 0.75), (0.75, 0.25)]
    for fu, fv in cands:
        u, v = u1 + (u2 - u1) * fu, v1 + (v2 - v1) * fv
        cl = BRepClass_FaceClassifier(face.wrapped, gp_Pnt2d(u, v), 1e-7)
        if cl.State() == TopAbs_IN:
            p = surf.Value(u, v)
            from build123d import Vector
            return Vector(p.X(), p.Y(), p.Z())
    return c


def _clean_surface(face, method, tol):
    """A clean surface for a face: "analytic" (plane / cylinder / cone / sphere / torus within tol, else a smooth
    re-approximation), "smooth" (degree-3 C2 spline within tol), "original" (the face's own surface)."""
    from OCP.BRep import BRep_Tool
    from OCP.GeomConvert import GeomConvert_SurfToAnaSurf
    surf = BRep_Tool.Surface_s(face.wrapped)
    if method == "original":
        try:
            return _extended_fit(surf, 1e-4), "original (re-fitted)"
        except Exception:
            return surf, "original"
    if method == "analytic":
        try:
            ana = GeomConvert_SurfToAnaSurf(surf).ConvertToAnalytical(tol)
        except Exception:
            ana = None
        if ana is not None:
            return ana, ana.DynamicType().Name().replace("Geom_", "")
    try:
        return _extended_fit(surf, tol), "smooth spline"
    except Exception:
        pass
    return surf, "original"


def _extended_fit(surf, tol, ext_frac=0.3, n=25):
    """Smooth degree-3 C2 B-spline fitted to a surface within tol, extended beyond the surface bounds by
    ext_frac of the parameter range (linear extrapolation along the boundary tangents)."""
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    try:
        from OCP.TColgp import TColgp_Array2OfPnt as Arr
    except ImportError:
        from OCP.collections import Array2_gp_Pnt as Arr
    from OCP.Precision import Precision
    u1, u2, v1, v2 = surf.Bounds()
    inf = Precision.Infinite_s() / 2
    if any(abs(b) > inf for b in (u1, u2, v1, v2)):
        return surf                     # unbounded (analytic) surface: nothing to extend
    du, dv = u2 - u1, v2 - v1
    ua, ub, va, vb = u1 - ext_frac * du, u2 + ext_frac * du, v1 - ext_frac * dv, v2 + ext_frac * dv
    pts = Arr(1, n, 1, n)
    for i in range(n):
        u = ua + (ub - ua) * i / (n - 1)
        for j in range(n):
            v = va + (vb - va) * j / (n - 1)
            uc, vc = min(max(u, u1), u2), min(max(v, v1), v2)
            p, d1u, d1v = gp_Pnt(), gp_Vec(), gp_Vec()
            surf.D1(uc, vc, p, d1u, d1v)
            pts.SetValue(i + 1, j + 1, gp_Pnt(p.X() + d1u.X() * (u - uc) + d1v.X() * (v - vc),
                                              p.Y() + d1u.Y() * (u - uc) + d1v.Y() * (v - vc),
                                              p.Z() + d1u.Z() * (u - uc) + d1v.Z() * (v - vc)))
    return GeomAPI_PointsToBSplineSurface(pts, 3, 3, GeomAbs_C2, tol).Surface()


def _replace_faces(shape, f):
    """Replace faces: the picked faces (and the small faces touching them) are rebuilt on one clean surface.
    The clean surface is offset by "offset" (mm, + outward); a thick pad of the old faces ("pad", mm, outward)
    is fused to the part and everything outside the clean surface is cut away, so that material is both removed
    (bumps outside) and added (hollows inside). Works cell by cell."""
    from build123d import Compound, Shape
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Sewing
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Fuse
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.Precision import Precision
    faces = find_faces(shape, f.get("faces") or [])
    if not faces:
        raise ValueError("no faces picked")
    min_area = float(f.get("min_area") or 0)
    if min_area > 0:
        small = [fc for fc in shape.faces() if fc.area < min_area]
        extra, frontier = [], list(faces)
        while frontier:
            nxt = []
            for sm in small:
                if any(sm.wrapped.IsSame(x.wrapped) for x in faces + extra):
                    continue
                if any(any(e.wrapped.IsSame(x.wrapped) for x in sm.edges()) for fr in frontier for e in fr.edges()):
                    extra.append(sm)
                    nxt.append(sm)
            frontier = nxt
        faces = faces + extra
    main = max(faces, key=lambda fc: fc.area)
    tol = float(f.get("tolerance") or 0.05)
    pad_t = float(f.get("pad") or 1.0)
    off = float(f.get("offset") or 0.0)
    if (f.get("method") or "") == "surface":
        body = (f.get("_bodies") or {}).get(f.get("source"))
        if body is None:
            raise ValueError("source surface not found (it must be above this feature)")
        bf = list(body.faces())
        if len(bf) != 1:
            raise ValueError("the source surface must be one face")
        from OCP.BRep import BRep_Tool
        surf, kind = BRep_Tool.Surface_s(bf[0].wrapped), "surface body"
    else:
        surf, kind = _clean_surface(main, f.get("method") or "analytic", tol)
    c = _point_on_face(main)
    n = main.normal_at(c)
    # outward normal: the point a little inside along -n must be in the material
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_IN
    owner = next((so for so in shape.solids() if any(main.wrapped.IsSame(x.wrapped) for x in so.faces())), None)
    if owner is not None:
        for eps in (0.05, 0.3, 1.0):
            cl = BRepClass3d_SolidClassifier(owner.wrapped, gp_Pnt(c.X - n.X * eps, c.Y - n.Y * eps, c.Z - n.Z * eps), 1e-7)
            cl2 = BRepClass3d_SolidClassifier(owner.wrapped, gp_Pnt(c.X + n.X * eps, c.Y + n.Y * eps, c.Z + n.Z * eps), 1e-7)
            if cl.State() == TopAbs_IN and cl2.State() != TopAbs_IN:
                break
            if cl2.State() == TopAbs_IN and cl.State() != TopAbs_IN:
                n = -n
                break
    if abs(off) > 1e-9:
        surf = surf.Translated(gp_Vec(n.X * off, n.Y * off, n.Z * off))
    bb = shape.bounding_box()
    big = bb.diagonal * 2 + 10
    u1, u2, v1, v2 = surf.Bounds()
    inf = Precision.Infinite_s() / 2
    u1, u2 = (-big if u1 < -inf else u1), (big if u2 > inf else u2)
    v1, v2 = (-big if v1 < -inf else v1), (big if v2 > inf else v2)
    T = BRepBuilderAPI_MakeFace(surf, u1, u2, v1, v2, 1e-6).Face()
    d = abs(off) + pad_t + 1.0
    half = BRepPrimAPI_MakeHalfSpace(T, gp_Pnt(c.X - n.X * d, c.Y - n.Y * d, c.Z - n.Z * d)).Solid()

    def pad_of(fcs, outward):
        # the old faces sewn to one shell and thickened outward (True) or inward (False)
        sew = BRepBuilderAPI_Sewing(1e-4)
        for fc in fcs:
            sew.Add(fc.wrapped)
        sew.Perform()
        sh = sew.SewedShape()
        for sgn in (1.0, -1.0):
            try:
                mk = BRepOffsetAPI_MakeThickSolid()
                mk.MakeThickSolidBySimple(sh, sgn * pad_t)
                p = Shape.cast(mk.Shape())
                if p.volume < 0:
                    p = Shape.cast(mk.Shape().Reversed())
                if p.volume <= 1e-9:
                    continue
                # the pad on the wanted side contains the point half a pad thickness from the face
                from OCP.BRepClass3d import BRepClass3d_SolidClassifier
                from OCP.TopAbs import TopAbs_IN
                k = 0.5 * pad_t * (1.0 if outward else -1.0)
                cl = BRepClass3d_SolidClassifier(p.wrapped, gp_Pnt(c.X + n.X * k, c.Y + n.Y * k, c.Z + n.Z * k), 1e-7)
                if cl.State() == TopAbs_IN:
                    return p
            except Exception:
                continue
        return None

    solids = list(shape.solids())
    out, done = [], 0
    for so in solids:
        mine = [fc for fc in faces if any(fc.wrapped.IsSame(x.wrapped) for x in so.faces())]
        if not mine:
            out.append(so)
            continue
        v0 = so.volume
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        body = so.wrapped
        pad_out = pad_of(mine, True)
        if pad_out is None:
            raise ValueError("the pad over the picked faces could not be built")
        if off < 0:
            # material inside the old faces is cut away down to the offset surface: the pad reaches inward too
            pad_in = pad_of(mine, False)
            if pad_in is not None:
                fu = BRepAlgoAPI_Fuse(pad_out.wrapped, pad_in.wrapped)
                fu.Build()
                if fu.IsDone():
                    pad_out = Shape.cast(fu.Shape())
        # local operation: within the pad footprint, material outside the clean surface is removed and material
        # up to the clean surface is added; the rest of the cell is untouched
        cut = BRepAlgoAPI_Cut(body, pad_out.wrapped)
        cut.Build()
        if not cut.IsDone():
            raise ValueError("the cut of the pad region failed")
        body = cut.Shape()
        fill = BRepAlgoAPI_Common(pad_out.wrapped, half)
        fill.Build()
        if fill.IsDone() and Shape.cast(fill.Shape()).solids():
            fu = BRepAlgoAPI_Fuse(body, fill.Shape())
            fu.Build()
            if not fu.IsDone():
                raise ValueError("adding material up to the clean surface failed")
            body = fu.Shape()
        r = Shape.cast(body)
        rs = list(r.solids())
        if not rs:
            raise ValueError("the clean surface removed the whole cell; check the offset sign")
        r = rs[0] if len(rs) == 1 else max(rs, key=lambda x: x.volume)
        try:
            u = _unify(r, {})
            if u.solids() and abs(u.volume - r.volume) < 1e-6 * max(abs(r.volume), 1.0):
                r = u
        except Exception:
            pass
        valid = r.is_valid() if callable(r.is_valid) else r.is_valid
        if not valid:
            raise ValueError("the rebuilt cell is not a valid solid; pick a larger group of faces (the face and "
                             "its neighbours) or use a smaller pad")
        if abs(r.volume - v0) > 0.2 * abs(v0):
            raise ValueError("the volume changed by %.0f %%; the pad or offset is too large, or the surface is not "
                             "close to the picked faces" % (100 * abs(r.volume - v0) / abs(v0)))
        out.append(r)
        done += 1
    res = out[0] if len(out) == 1 else Compound(children=out)
    res._replace_kind = kind
    return res


def _defeature(shape, f):
    """Removes faces and fills the gap (CAE: Remove faces / Repair): fillets, holes, bosses."""
    from build123d import Compound
    faces = find_faces(shape, f.get("faces") or [])
    min_area = float(f.get("min_area") or 0)
    if min_area > 0:
        allf = list(shape.faces())
        small = [fc for fc in allf if fc.area < min_area]
        if f.get("all_small"):
            extra = small
        else:
            # small faces touching a picked face (shared edge), repeated so that chains of slivers are included
            extra, frontier = [], list(faces)
            while frontier:
                nxt = []
                for sm in small:
                    if any(sm.wrapped.IsSame(x.wrapped) for x in faces + extra):
                        continue
                    if any(any(e.wrapped.IsSame(x.wrapped) for x in sm.edges()) for fr in frontier for e in fr.edges()):
                        extra.append(sm)
                        nxt.append(sm)
                frontier = nxt
        faces = faces + [fc for fc in extra if not any(fc.wrapped.IsSame(x.wrapped) for x in faces)]
    if not faces:
        raise ValueError("no faces selected" if min_area <= 0 else "no faces below %g mm^2" % min_area)
    # one operation per cell (the algorithm works on a solid, not on a compound of solids)
    solids = list(shape.solids())
    out, removed, failed = [], 0, []
    for so in solids:
        mine = [fc for fc in faces if any(fc.wrapped.IsSame(x.wrapped) for x in so.faces())]
        if not mine:
            out.append(so)
            continue
        n0 = len(so.faces())
        res = _defeature_solid(so, mine)
        if res is None or len(res.faces()) >= n0:
            res = _patch_faces(so, mine)
            if res is None:
                failed.append(len(mine))
                out.append(so)
                continue
        removed += n0 - len(res.faces())
        out += list(res.solids()) or [res]
    if failed:
        raise ValueError("%d face(s) could not be removed: the neighbouring faces cannot be extended and the opening "
                         "cannot be patched. Use Combine faces (meshing only) for these faces." % sum(failed))
    return out[0] if len(out) == 1 else Compound(children=out)


def _occt_offset(so, offsets):
    """Faces moved along their normals with BRepOffset_MakeOffset; None when the result is not valid or its volume
    change is far from the sum of face area x distance (the algorithm can move other faces)."""
    from OCP.BRepOffset import BRepOffset_MakeOffset, BRepOffset_Skin
    from OCP.GeomAbs import GeomAbs_Intersection
    from build123d import Shape
    try:
        m = BRepOffset_MakeOffset()
        m.Initialize(so.wrapped, 0.0, 1e-5, BRepOffset_Skin, False, False, GeomAbs_Intersection, False)
        for fc, d in offsets:
            m.SetOffsetOnFace(fc.wrapped, float(d))
        m.MakeOffsetShape()
        if not m.IsDone():
            return None
        r = Shape.cast(m.Shape())
        sols = r.solids()
        if len(sols) != 1 or not sols[0].is_valid:
            return None
        r = sols[0]
    except Exception:
        return None
    expect = sum(fc.area * d for fc, d in offsets)
    scale = sum(abs(fc.area * d) for fc, d in offsets)
    if abs((r.volume - so.volume) - expect) > 0.3 * scale + 1e-9 * so.volume:
        return None
    return r


def _prism(fc, vec):
    """Solid swept by a face along a vector."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec
    from build123d import Shape
    return Shape.cast(BRepPrimAPI_MakePrism(fc.wrapped, gp_Vec(*vec)).Shape())


def _slab(fc, d):
    """Solid between a face and its offset by d along the outward normal (d < 0: inside the part)."""
    if _is_planar(fc):
        n = fc.normal_at(0.5, 0.5)
        return _prism(fc, (n.X * d, n.Y * d, n.Z * d))
    from OCP.BRepOffset import BRepOffset_MakeOffset, BRepOffset_Skin
    from OCP.GeomAbs import GeomAbs_Intersection
    from build123d import Shape
    m = BRepOffset_MakeOffset()
    m.Initialize(fc.wrapped, float(d), 1e-5, BRepOffset_Skin, False, False, GeomAbs_Intersection, True)
    m.MakeOffsetShape()
    if not m.IsDone():
        raise ValueError("the face cannot be offset (%s)" % str(m.Error()).split(".")[-1])
    return Shape.cast(m.Shape())


def _is_planar(fc):
    return str(getattr(fc.geom_type, "name", fc.geom_type)).upper().endswith("PLANE")


def _add_remove(so, adds, cuts):
    """Part with the solids in adds fused and those in cuts removed; one valid solid (or several) required."""
    r = so
    if adds:
        r = r.fuse(*adds)
    if cuts:
        r = r.cut(*cuts)
    r = r.clean()
    sols = r.solids()
    if not sols:
        raise ValueError("the result has no solid")
    if not all(x.is_valid for x in sols):
        raise ValueError("the result is not a valid solid")
    return sols[0] if len(sols) == 1 else r


def _offset_solid_faces(so, offsets):
    """Faces of one solid moved along their normals: offsets [(face, distance)], positive outward (adds material).
    BRepOffset_MakeOffset extends or trims the neighbouring faces; when it fails, the solid between each face and
    its offset is added (distance > 0) or removed (distance < 0): neighbouring faces at a right angle to the face
    are extended or trimmed, other neighbouring faces keep their position."""
    r = _occt_offset(so, offsets)
    if r is not None:
        return r
    adds = [_slab(fc, d) for fc, d in offsets if d > 0]
    cuts = [_slab(fc, d) for fc, d in offsets if d < 0]
    return _add_remove(so, adds, cuts)


def _tangent_chain(so, faces, cos_tol=0.9998):
    """The faces and all faces of the solid connected to them through tangent (G1) edges."""
    try:
        from OCP.TopTools import TopTools_IndexedMapOfShape as ShapeMap
    except ImportError:                       # OCCT 8
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
    emap = ShapeMap()
    owners = {}                               # edge index -> faces of the solid with that edge
    all_faces = list(so.faces())
    for fc in all_faces:
        for e in fc.edges():
            emap.Add(e.wrapped)
            owners.setdefault(emap.FindIndex(e.wrapped), []).append(fc)
    out = [g for g in all_faces if any(g.wrapped.IsSame(fc.wrapped) for fc in faces)]
    k = 0
    while k < len(out):
        fc = out[k]
        k += 1
        for e in fc.edges():
            p = e.position_at(0.5)
            for g in owners.get(emap.FindIndex(e.wrapped), []):
                if any(g.wrapped.IsSame(o.wrapped) for o in out):
                    continue
                try:
                    if fc.normal_at(p).dot(g.normal_at(p)) > cos_tol:
                        out.append(g)
                except Exception:
                    pass
    return out


def _per_solid(shape, faces, fn):
    """Applies fn(solid, faces of that solid) to each cell that holds picked faces."""
    from build123d import Compound
    out = []
    for so in shape.solids():
        mine = [fc for fc in faces if any(fc.wrapped.IsSame(x.wrapped) for x in so.faces())]
        out += list((fn(so, mine) if mine else so).solids())
    return out[0] if len(out) == 1 else Compound(children=out)


def _offset_faces(shape, f):
    """Offset faces: the picked faces move along their normals by "distance" (mm, positive adds material); the
    neighbouring faces are extended or trimmed (CAD: offset face, push/pull). "tangent" (default true): faces
    connected through tangent edges are included."""
    faces = find_faces(shape, f.get("faces") or [])
    if not faces:
        raise ValueError("no faces selected")
    d = float(f.get("distance") or 0)
    if d == 0:
        raise ValueError("distance is 0")
    tangent = f.get("tangent", True)

    def off(so, mine):
        if tangent:
            mine = _tangent_chain(so, mine)
        return _offset_solid_faces(so, [(fc, d) for fc in mine])
    return _per_solid(shape, faces, off)


def _side_of(fc, v, n=5):
    """+1 when the outward normal of the face points along v everywhere, -1 against, 0 at a right angle, None for
    both (a curved face moved across, for example a cylinder moved sideways)."""
    L = math.sqrt(sum(x * x for x in v))
    ds = []
    for a in range(n):
        for b in range(n):
            try:
                q = fc.normal_at((a + 0.5) / n, (b + 0.5) / n)
            except Exception:
                continue
            ds.append((q.X * v[0] + q.Y * v[1] + q.Z * v[2]) / L)
    if not ds:
        return None
    if all(abs(x) < 1e-6 for x in ds):
        return 0
    if all(x > -1e-6 for x in ds):
        return 1
    if all(x < 1e-6 for x in ds):
        return -1
    return None


PLANE_NORMALS = {"XY": (0.0, 0.0, 1.0), "XZ": (0.0, 1.0, 0.0), "YZ": (1.0, 0.0, 0.0)}


def _rot_between(a, b):
    """3x3 rotation turning unit vector a onto unit vector b (the smallest rotation)."""
    ax = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    s = math.sqrt(sum(x * x for x in ax))
    c = sum(a[i] * b[i] for i in range(3))
    if s < 1e-12:
        if c > 0:
            return [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
        # opposite: a half turn about any axis normal to a
        t = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)
        ax = [a[1] * t[2] - a[2] * t[1], a[2] * t[0] - a[0] * t[2], a[0] * t[1] - a[1] * t[0]]
        s = math.sqrt(sum(x * x for x in ax))
        return _axis_angle([x / s for x in ax], math.pi)
    return _axis_angle([x / s for x in ax], math.atan2(s, c))


def _axis_angle(k, t):
    c, s, C = math.cos(t), math.sin(t), 1 - math.cos(t)
    x, y, z = k
    return [[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C]]


def _mat_mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _mat_vec(A, v):
    return [sum(A[i][k] * v[k] for k in range(3)) for i in range(3)]


AXIS_DIRS = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
PLANE_AXIS = {"XY": "Z", "XZ": "Y", "YZ": "X"}           # a cylinder given a plane goes on the axis normal to it


def _place_item(shape, f, i):
    """Item i of a Place feature: {"kind": "plane" | "axis", "target", "c" (face centre or axis point), "v" (outward
    normal or axis direction), "T" (target normal or direction), "sign" (wanted direction of v: -1 against T for a
    plane, +1 along T for an axis; Flip changes it), "set" (principal directions the item fixes)}."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    ref = f.get("face%d" % i)
    fs = find_faces(shape, [ref])
    if not fs:
        raise ValueError("face %d not found" % i)
    fc = fs[0]
    tg = f.get("plane%d" % i) or ("XY", "XZ", "YZ")[i - 1]
    flip = bool(f.get("flip%d" % i))
    if _is_planar(fc):
        if tg not in PLANE_NORMALS:
            raise ValueError("face %d is planar: it goes on a plane (XY, XZ or YZ), not on axis %s" % (i, tg))
        c = fc.center()
        n = fc.normal_at(c)
        N = PLANE_NORMALS[tg]
        return {"kind": "plane", "target": tg, "c": [c.X, c.Y, c.Z], "v": [n.X, n.Y, n.Z], "T": list(N),
                "sign": 1.0 if flip else -1.0, "set": [j for j in range(3) if abs(N[j]) > 0.5]}
    ad = BRepAdaptor_Surface(fc.wrapped)
    if ad.GetType() != GeomAbs_Cylinder:
        raise ValueError("face %d is neither planar nor cylindrical" % i)
    if tg in PLANE_AXIS:
        tg = PLANE_AXIS[tg]
    if tg not in AXIS_DIRS:
        raise ValueError("axis %s unknown" % tg)
    ax = ad.Cylinder().Axis()
    L, D0 = ax.Location(), ax.Direction()
    D = AXIS_DIRS[tg]
    return {"kind": "axis", "target": tg, "c": [L.X(), L.Y(), L.Z()], "v": [D0.X(), D0.Y(), D0.Z()], "T": list(D),
            "sign": -1.0 if flip else 1.0, "set": [j for j in range(3) if abs(D[j]) < 0.5]}


def place_transform(shape, f):
    """(R, t) of a Place feature. Up to three faces of the solid ("face1".."face3") with a target each
    ("plane1".."plane3"): a planar face goes on a principal plane ("XY" | "XZ" | "YZ"), its outward normal against
    the plane normal (the part on the positive side; "flipN": along it); a cylindrical face goes with its axis on a
    principal axis ("X" | "Y" | "Z"; a plane given for a cylinder means the axis normal to it), the axis direction
    along the target ("flipN": against it). The first item is turned onto its target, the second turned about the
    first target direction, the third only moved. A direction already set by an earlier item is not moved again
    (a note says so; the second item still gives the turn). Directions not set by an item: "rest" "keep" (default), "centre"
    (bounding box centre to 0) or "min" (bounding box minimum to 0). "offset" [dx, dy, dz] (mm) is added last.
    Returns a 3x3 rotation and a translation."""
    R = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
    items = []
    taken = set()
    notes = []
    for i in (1, 2, 3):
        if not f.get("face%d" % i):
            continue
        it = _place_item(shape, f, i)
        it["i"] = i
        it["move"] = [j for j in it["set"] if j not in taken]
        clash = [j for j in it["set"] if j in taken]
        if clash:
            notes.append("face %d: %s already set by an earlier face, %s" % (
                i, "/".join("XYZ"[j] for j in clash),
                "used for the turn" + (" and %s" % "/".join("XYZ"[j] for j in it["move"]) if it["move"] else " only")
                if len(items) == 1 else ("used for %s only" % "/".join("XYZ"[j] for j in it["move"]) if it["move"] else "not used")))
        taken.update(it["set"])
        tgt = [it["sign"] * x for x in it["T"]]
        cur = _mat_vec(R, it["v"])
        if not items:
            R = _mat_mul(_rot_between(_norm_v(cur), tgt), R)
        elif len(items) == 1:
            k = items[0]["T"]                           # turn about the first target direction (keeps item 1)
            pc = [cur[j] - sum(cur[m] * k[m] for m in range(3)) * k[j] for j in range(3)]
            pt = [tgt[j] - sum(tgt[m] * k[m] for m in range(3)) * k[j] for j in range(3)]
            lc, lt = math.sqrt(sum(x * x for x in pc)), math.sqrt(sum(x * x for x in pt))
            if lc < 1e-6 and lt < 1e-6:
                # both along the first direction (an end face of a shaft on the axis): only a sign to check
                if sum(cur[j] * tgt[j] for j in range(3)) < 0:
                    raise ValueError("face %d points the other way: use Flip on face %d or face 1" % (i, i))
            elif lc < 1e-6 or lt < 1e-6:
                raise ValueError("face %d cannot be turned onto %s about the first direction" % (i, it["target"]))
            else:
                pc, pt = _norm_v(pc), _norm_v(pt)
                ang = math.atan2(sum(k[j] * (pc[(j + 1) % 3] * pt[(j + 2) % 3] - pc[(j + 2) % 3] * pt[(j + 1) % 3]) for j in range(3)),
                                 sum(pc[j] * pt[j] for j in range(3)))
                R = _mat_mul(_axis_angle(k, ang), R)
        items.append(it)
    if len(items) == 3:                                # the third item is only moved: its direction follows the turn
        it = items[2]
        nn = _mat_vec(R, it["v"])
        if sum(nn[j] * it["T"][j] for j in range(3)) * it["sign"] < -0.5:
            notes.append("face 3 points the other way (%s): the part is on the %s side" % (it["target"], "negative" if it["kind"] == "plane" else "other"))
        elif abs(sum(_norm_v(nn)[j] * it["T"][j] for j in range(3))) < 0.999 and it["kind"] == "axis":
            notes.append("face 3: the axis is not parallel to %s after the turn; its point is put on the axis" % it["target"])
    f["_notes"] = notes
    t = [0.0, 0.0, 0.0]
    for it in items:
        c = _mat_vec(R, it["c"])
        for j in it["move"]:
            t[j] = -c[j]
    rest = f.get("rest") or "keep"
    if rest in ("centre", "min"):
        bb = shape.bounding_box()
        corners = [[x, y, z] for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y) for z in (bb.min.Z, bb.max.Z)]
        rc = [_mat_vec(R, q) for q in corners]
        for j in range(3):
            if j in taken:
                continue
            lo, hi = min(q[j] for q in rc), max(q[j] for q in rc)
            t[j] = -((lo + hi) / 2.0 if rest == "centre" else lo)
    off = [float(x or 0) for x in (f.get("offset") or [0, 0, 0])][:3]
    t = [t[j] + off[j] for j in range(3)]
    return R, t


def _norm_v(v):
    L = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / L for x in v]


def _apply_rt(shape, R, t):
    """Shape moved by the rotation R (3x3) and translation t."""
    from OCP.gp import gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from build123d import Shape
    tr = gp_Trsf()
    tr.SetValues(R[0][0], R[0][1], R[0][2], t[0], R[1][0], R[1][1], R[1][2], t[1], R[2][0], R[2][1], R[2][2], t[2])
    return Shape.cast(BRepBuilderAPI_Transform(shape.wrapped, tr, True).Shape())


def _move_faces(shape, f):
    """Move faces by a vector (mm). "tangent" (default true): faces connected through tangent edges move with the
    picked faces. Faces whose outward normal points along the vector sweep added material, faces pointing against
    it sweep removed material, faces at a right angle to the vector are extended (push/pull; a planar face moved
    along its normal is offset). Otherwise (a curved face moved across, for example a hole moved sideways) the
    picked faces are taken as a feature: the feature is removed (Remove faces) and its volume is added or cut again
    at the moved position."""
    from build123d import Location, Vector
    faces = find_faces(shape, f.get("faces") or [])
    if not faces:
        raise ValueError("no faces selected")
    v = [float(x or 0) for x in (f.get("vector") or [0, 0, 0])]
    L = math.sqrt(sum(x * x for x in v))
    if L == 0:
        raise ValueError("move vector is 0")
    tangent = f.get("tangent", True)

    def move(so, mine):
        if tangent:
            mine = _tangent_chain(so, mine)
        sides = [_side_of(fc, v) for fc in mine]
        if None not in sides:
            moving = [(fc, s) for fc, s in zip(mine, sides) if s]
            if not moving:
                raise ValueError("the faces are parallel to the move vector")
            if all(_is_planar(fc) and abs(abs(fc.normal_at(0.5, 0.5).dot(Vector(*v))) - L) < 1e-6 * L for fc, _ in moving):
                r = _occt_offset(so, [(fc, s * L) for fc, s in moving])
                if r is not None:
                    return r
            try:
                return _add_remove(so, [_prism(fc, v) for fc, s in moving if s > 0],
                                   [_prism(fc, v) for fc, s in moving if s < 0])
            except ValueError:
                pass
        base = _defeature_solid(so, mine)
        if base is None or len(base.faces()) >= len(so.faces()):
            raise ValueError("the faces cannot be moved: they do not form a feature that Remove faces can take away "
                             "(pick all faces of the hole, boss or slot)")
        loc = Location(Vector(*v))
        hole = base.cut(so)                     # material of the feature removed from the part (hole, slot)
        boss = so.cut(base)                     # material added by the feature (boss, rib)
        res = base
        if hole.solids():
            res = res.cut(hole.moved(loc))
        if boss.solids():
            res = res.fuse(boss.moved(loc))
        res = res.clean()
        if not res.solids():
            raise ValueError("move gave no solid")
        return res
    return _per_solid(shape, faces, move)


def _defeature_solid(so, faces):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Defeaturing
    from build123d import Shape
    try:
        op = BRepAlgoAPI_Defeaturing()
        op.SetShape(so.wrapped)
        for fc in faces:
            op.AddFaceToRemove(fc.wrapped)
        op.SetRunParallel(True)
        op.Build()
        if not op.IsDone():
            return None
        r = Shape.cast(op.Shape())
        return r if r.solids() else None
    except Exception:
        return None


def _patch_faces(so, faces):
    """Fallback: the faces are removed from the shell and the opening is closed with a smooth patch (G1 to the
    neighbouring faces where possible), then the solid is rebuilt. The face count does not drop below the number
    of removed faces minus one patch per connected opening."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeFilling
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.GeomAbs import GeomAbs_C0, GeomAbs_G1
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from build123d import Shape, Face
    try:
        keep = [fc for fc in so.faces() if not any(fc.wrapped.IsSame(r.wrapped) for r in faces)]
        removed = Face.fuse(*faces) if len(faces) > 1 else faces[0]
        # outer boundary edges of the removed region: edges of removed faces that belong to a kept face
        patches = []
        for region in (removed.faces() if hasattr(removed, "faces") else [removed]):
            fill = BRepOffsetAPI_MakeFilling()
            n = 0
            for e in region.edges():
                owner = next((k for k in keep if any(e.wrapped.IsSame(x.wrapped) for x in k.edges())), None)
                if owner is None:
                    continue
                try:
                    fill.Add(e.wrapped, owner.wrapped, GeomAbs_G1, True)
                except Exception:
                    fill.Add(e.wrapped, GeomAbs_C0, True)
                n += 1
            if n < 3:
                return None
            fill.Build()
            if not fill.IsDone():
                return None
            patches.append(fill.Shape())
        sew = BRepBuilderAPI_Sewing(1e-4)
        for k in keep:
            sew.Add(k.wrapped)
        for pch in patches:
            sew.Add(pch)
        sew.Perform()
        sewn = sew.SewedShape()
        ex = TopExp_Explorer(sewn, TopAbs_SHELL)
        if not ex.More():
            return None
        mk = BRepBuilderAPI_MakeSolid(TopoDS.Shell_s(ex.Current()))
        if not mk.IsDone():
            return None
        r = Shape.cast(mk.Shape())
        if abs(r.volume) < 1e-9:
            return None
        if r.volume < 0:
            from OCP.BRepLib import BRepLib
            BRepLib.OrientClosedSolid_s(TopoDS.Solid_s(mk.Shape()))
            r = Shape.cast(mk.Shape())
        return r
    except Exception:
        return None


SURFACE_TYPES = ("surf_extract", "surf_fit", "surf_sketch", "surf_loft", "surf_fill", "surf_offset", "surf_sew", "surf_import",
                 "curve_extract", "curve_section", "surf_from_curve", "surf_trim", "surf_extend", "surf_bridge")


SKETCH_PLANE_KEYS = ("plane", "offset", "plane_edge", "plane_curve", "plane_t", "plane_flip", "plane_ref", "plane_face", "plane_origin", "plane_xdir", "plane_axis", "plane_point", "plane_origin_ref", "plane_xdir_ref")


def migrate(part):
    """Part record version 2: sketches are tree items ({"type": "sketch", plane fields, "sketch": doc}) and the
    features reference them ("sketch_ref", "path_ref"). A version 1 part (sketches embedded in the features) is
    converted in place: a sketch item is inserted before each feature that carries one. Idempotent."""
    feats = part.get("features") or []
    if part.get("version", 1) >= 2 and not any(f.get("sketch") and f.get("type") != "sketch" and not f.get("sketch_ref") for f in feats):
        part["version"] = 2
        return part
    nxt = int(part.get("next") or 1)
    for f in feats:
        try:
            nxt = max(nxt, int(str(f.get("id", "f0"))[1:]) + 1)
        except ValueError:
            pass
    out = []
    n_sk = sum(1 for f in feats if f.get("type") == "sketch")
    counts = {}
    for f in feats:
        counts[f.get("type")] = counts.get(f.get("type"), 0) + 1
        if not f.get("name") or f.get("name") == "undefined":
            f["name"] = "%s %d" % (str(f.get("type", "feature")).replace("_", " ").capitalize(), counts[f.get("type")])
        if f.get("type") == "sketch" or f.get("type") in ("surf_loft",):
            out.append(f)
            continue
        if f.get("path_sketch") and not f.get("path_ref"):
            n_sk += 1
            sid = "f%d" % nxt
            nxt += 1
            out.append({"id": sid, "name": "Sketch %d" % n_sk, "type": "sketch", "plane": f.get("path_plane", "XY"),
                        "offset": f.get("path_offset", 0), "sketch": f.pop("path_sketch"), "suppressed": False})
            f["path_ref"] = sid
            f.pop("path_plane", None)
            f.pop("path_offset", None)
        if f.get("sketch") and not f.get("sketch_ref"):
            n_sk += 1
            sid = "f%d" % nxt
            nxt += 1
            item = {"id": sid, "name": "Sketch %d" % n_sk, "type": "sketch", "sketch": f.pop("sketch"), "suppressed": False}
            for k in SKETCH_PLANE_KEYS:
                if k in f:
                    item[k] = f.pop(k)
            item.setdefault("plane", "XY")
            item.setdefault("offset", 0)
            out.append(item)
            f["sketch_ref"] = sid
        out.append(f)
    part["features"] = out
    part["next"] = nxt
    part["version"] = 2
    return part


def normalize(part):
    """Feature list with the sketch references resolved into embedded sketches (the form the build uses).
    Returns copies; the part is not changed. A sketch item stays in the list as type "sketch"."""
    feats = part.get("features") or []
    by_id = {f.get("id"): f for f in feats}
    out = []
    for f in feats:
        g = dict(f)
        ref = g.get("sketch_ref")
        if ref:
            sk = by_id.get(ref)
            if sk is None or sk.get("type") != "sketch":
                g["_missing_sketch"] = True
            else:
                g["sketch"] = sk.get("sketch") or {}
                for k in SKETCH_PLANE_KEYS:
                    if k in sk:
                        g[k] = sk[k]
                g["_sketch_item"] = ref
        pref = g.get("path_ref")
        if pref:
            sk = by_id.get(pref)
            if sk is None or sk.get("type") != "sketch":
                g["_missing_sketch"] = True
            else:
                g["path_sketch"] = sk.get("sketch") or {}
                g["path_plane"] = sk.get("plane", "XY")
                g["path_offset"] = sk.get("offset", 0)
                g["_path_frame_item"] = sk
        out.append(g)
    return out


def _face_sig(fc):
    """Signature of the underlying surface of a face: planes by normal and position, cylinders, cones, spheres
    and tori by axis and radii, other surfaces by type and centre. Faces split or trimmed by a later feature keep
    their signature, so they keep the feature that created them."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_Torus
    ad = BRepAdaptor_Surface(fc.wrapped)
    t = ad.GetType()
    if t == GeomAbs_Plane:
        pl = ad.Plane()
        n = pl.Axis().Direction()
        p = pl.Location()
        d = n.X() * p.X() + n.Y() * p.Y() + n.Z() * p.Z()
        nn = (round(abs(n.X()), 4), round(abs(n.Y()), 4), round(abs(n.Z()), 4))
        sgn = 1 if (n.X() + n.Y() * 1e-3 + n.Z() * 1e-6) >= 0 else -1
        return ("P", nn, round(d * sgn, 3))
    if t in (GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_Torus):
        g = ad.Cylinder() if t == GeomAbs_Cylinder else ad.Cone() if t == GeomAbs_Cone else ad.Sphere() if t == GeomAbs_Sphere else ad.Torus()
        ax = g.Axis()
        d = ax.Direction()
        p = ax.Location()
        # axis point nearest to the origin
        k = d.X() * p.X() + d.Y() * p.Y() + d.Z() * p.Z()
        q = (round(p.X() - k * d.X(), 3), round(p.Y() - k * d.Y(), 3), round(p.Z() - k * d.Z(), 3))
        nn = (round(abs(d.X()), 4), round(abs(d.Y()), 4), round(abs(d.Z()), 4))
        rad = (round(g.Radius(), 3),) if t in (GeomAbs_Cylinder, GeomAbs_Sphere) else (round(g.RefRadius(), 3), round(g.SemiAngle(), 4)) if t == GeomAbs_Cone else (round(g.MajorRadius(), 3), round(g.MinorRadius(), 3))
        return (str(t), nn, q, rad)
    c = fc.center()
    return (str(t), round(c.X, 2), round(c.Y, 2), round(c.Z, 2))


def _face_centres(shape):
    """Rounded face centres of a shape (identity of the faces between build steps) -> (index, signature)."""
    out = {}
    if shape is None:
        return out
    for i, fc in enumerate(shape.faces()):
        try:
            c = fc.center()
            try:
                sig = _face_sig(fc)
            except Exception:
                sig = None
            out[(round(c.X, 3), round(c.Y, 3), round(c.Z, 3))] = (i, sig)
        except Exception:
            continue
    return out


def build(part, upto=None, surfaces=None, datums=None, owners=None):
    """Build the part. Returns (shape or None, [{"id", "error"}]). surfaces: dict filled with the surface bodies
    (feature id -> Shape) when given; datums: dict filled with the frames of the plane features (feature id ->
    {"o", "x", "y", "z"}) when given; owners: dict filled with face centre key -> id of the feature that created
    the face (faces of the final solid)."""
    from build123d import Compound
    from . import surfaces as sfm
    shape = None
    status = []
    tools = {}                      # feature id -> (tool solids, cut flag) for patterns
    bodies = surfaces if surfaces is not None else {}
    planes = datums if datums is not None else {}
    feats = normalize(part)
    if upto is not None:
        feats = feats[:upto]
    frames = {}
    face_owner = {}                 # face centre key -> feature id
    prev_centres = {}
    sig_owner = {}                  # surface signature -> feature id (faces split later keep their owner)
    prev_id = None

    def attribute(fid):
        nonlocal prev_centres
        cur = _face_centres(shape)
        for k, (i, sig) in cur.items():
            if k not in prev_centres:
                face_owner[k] = sig_owner.get(sig, fid) if sig is not None else fid
        for k, (i, sig) in cur.items():
            if sig is not None and sig not in sig_owner and k in face_owner:
                sig_owner[sig] = face_owner[k]
        prev_centres = cur

    for f in feats:
        if prev_id is not None:
            attribute(prev_id)
        prev_id = f.get("id")
        if f.get("suppressed"):
            status.append({"id": f.get("id"), "error": None, "suppressed": True})
            continue
        if f.get("_missing_sketch"):
            status.append({"id": f.get("id"), "error": "the referenced sketch was not found"})
            continue
        f["_bodies"] = bodies
        f["_datums"] = planes
        f["_sketch_curves"] = lambda sid: sketch_tool_edges(feats, frames, planes, sid)
        if f["type"] == "sketch":
            try:
                fr = resolve_plane(f, shape, bodies, planes)
                if not fr:
                    n, x = PRINCIPAL_FRAMES[f.get("plane", "XY")]
                    fr = _frame_of([0, 0, 0], n, x)
                fr = adjust_frame(fr, f)
                info = {"id": f.get("id"), "error": None, "sketch": True,
                        "entities": len([e for e in (f.get("sketch") or {}).get("entities") or [] if not e.get("constr")])}
                frames[f.get("id")] = fr
                try:
                    g = dict(f)
                    g["_frame"] = fr
                    info["profiles"] = len(profile_faces(f.get("sketch") or {}, plane_of(g), []))
                except Exception:
                    info["profiles"] = 0
                status.append(info)
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "sketch plane not resolved", "sketch": True})
            continue
        if f["type"] == "plane":
            try:
                fr = datum_frame(shape, bodies, planes, f)
                fr["kind"] = "plane"
                planes[f.get("id")] = fr
                frames[f.get("id")] = fr
                status.append({"id": f.get("id"), "error": None, "datum": True})
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "plane failed", "datum": True})
            continue
        if f["type"] == "point":
            try:
                p = datum_point(shape, bodies, planes, f)
                planes[f.get("id")] = {"kind": "point", "o": p}
                status.append({"id": f.get("id"), "error": None, "datum": True, "point": p})
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "point failed", "datum": True})
            continue
        if f["type"] == "axis":
            try:
                ax = datum_axis(shape, bodies, planes, f)
                planes[f.get("id")] = {"kind": "axis", "o": ax["o"], "d": ax["d"]}
                status.append({"id": f.get("id"), "error": None, "datum": True, "axis": ax})
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "axis failed", "datum": True})
            continue
        try:
            sid = f.get("_sketch_item")
            if sid and frames.get(sid):
                # the plane of the referenced sketch as resolved at the sketch's own position in the tree
                f["_frame"] = dict(frames[sid])
                frames[f.get("id")] = f["_frame"]
            else:
                fr = resolve_plane(f, shape, bodies, planes)
                if fr:
                    frames[f.get("id")] = adjust_frame(fr, f)
        except Exception as e:
            status.append({"id": f.get("id"), "error": str(e).strip() or "plane not resolved"})
            continue
        if f["type"] in SURFACE_TYPES:
            try:
                t = f["type"]
                ffa = lambda s, refs: find_faces_any(s, bodies, refs)
                fea = lambda s, refs: find_edges_any(s, bodies, refs)
                if t == "surf_extract":
                    body = sfm.extract(shape, f, ffa)
                elif t == "surf_fit":
                    body = sfm.fit(shape, f, ffa, _clean_surface, _extended_fit)
                elif t == "surf_sketch":
                    body = sfm.from_sketch(f, plane_of, _segments, profile_faces)
                elif t == "surf_loft":
                    body = sfm.loft_sources(bodies, f) if f.get("curves") else sfm.loft(f, plane_of, _segments)
                elif t == "surf_bridge":
                    body = sfm.bridge(shape, f, find_edges, bodies)
                elif t == "surf_fill":
                    sk_edges = [sketch_tool_edges(feats, frames, planes, sid) for sid in f.get("sketch_refs") or []]
                    body = sfm.fill(shape, f, find_edges, bodies, sk_edges)
                elif t == "surf_offset":
                    body = sfm.offset(shape, bodies, f, ffa)
                elif t == "curve_extract":
                    body = sfm.curve_extract(shape, bodies, f, fea, expand_edges)
                elif t == "curve_section":
                    body = sfm.curve_section(shape, bodies, f, ffa)
                elif t == "surf_from_curve":
                    body = sfm.surf_from_curve(bodies, f)
                elif t == "surf_trim":
                    if f.get("with") == "sketch":
                        f["_tool_edges"] = sketch_tool_edges(feats, frames, planes, f.get("tool"))
                    try:
                        body = sfm.trim(shape, bodies, f)
                    finally:
                        f.pop("_tool_edges", None)
                elif t == "surf_extend":
                    body = sfm.extend(shape, bodies, f, ffa) if f.get("mode") == "all" else sfm.extend_edges(shape, bodies, f, fea, ffa)
                elif t == "surf_import":
                    body = sfm.import_step(f)
                else:
                    body = sfm.sew(bodies, f)
                bodies[f.get("id")] = body
                is_curve = not body.faces()
                info = {"id": f.get("id"), "error": None, "surface": True, "curve": is_curve,
                        "faces": len(body.faces()), "edges": len(body.edges()), "area": round(body.area, 3),
                        "length": round(sum(e.length for e in body.edges()), 3)}
                if getattr(body, "_kind", None):
                    info["note"] = "%s: %s" % ("clean curve" if is_curve else "clean surface", body._kind)
                status.append(info)
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "surface operation failed", "surface": True})
            continue
        if f["type"] in ("thicken", "surf_cut"):
            try:
                if f["type"] == "thicken":
                    v0 = shape.volume if shape is not None else 0.0
                    shape = sfm.thicken(shape, bodies, f, _fuse, lambda s, refs: find_faces_any(s, bodies, refs))
                else:
                    if shape is None:
                        raise ValueError("no solid to cut")
                    v0 = shape.volume
                    shape = sfm.cut_with_surface(shape, bodies, f)
                info = {"id": f.get("id"), "error": None, "cells": len(shape.solids())}
                if f.get("_note"):
                    info["note"] = f.pop("_note")
                if abs(shape.volume - v0) < 1e-9:
                    info["error"] = "the feature changed nothing"
                status.append(info)
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "operation failed"})
            continue
        if f["type"] == "import":
            try:
                shape = _fuse(shape, _import(f))
                status.append({"id": f.get("id"), "error": None, "cells": len(shape.solids())})
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "import failed"})
            continue
        if f["type"] == "place":
            try:
                if shape is None:
                    raise ValueError("no solid to place")
                R, tv = place_transform(shape, f)
                shape = _apply_rt(shape, R, tv)
                for k in list(bodies.keys()):
                    if bodies[k] is not None:
                        bodies[k] = _apply_rt(bodies[k], R, tv)
                bb = shape.bounding_box()
                status.append({"id": f.get("id"), "error": None, "cells": len(shape.solids()),
                               "note": "; ".join((f.pop("_notes", None) or []) + ["bounding box (%.3f, %.3f, %.3f) to (%.3f, %.3f, %.3f) mm" % (
                                   bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)])})
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "place failed"})
            continue
        if f["type"] == "combine":
            # virtual topology for the mesh only: the geometry is unchanged
            n = len(find_faces(shape, f.get("faces") or [])) if shape is not None else 0
            status.append({"id": f.get("id"), "error": None if (n or f.get("min_area")) else "no faces picked", "combined": n})
            continue
        if f["type"] in ("split", "unify", "heal", "defeature", "smooth", "replace", "hole_mesh", "offset_faces", "move_faces"):
            try:
                if shape is None:
                    raise ValueError("no solid for %s" % f["type"])
                n0 = len(shape.solids())
                f0, e0 = len(shape.faces()), len(shape.edges())
                if f["type"] == "split":
                    f["_bodies"] = bodies
                    f["_datums"] = planes
                    try:
                        shape = _split(shape, f)
                    finally:
                        f.pop("_bodies", None)
                        f.pop("_datums", None)
                elif f["type"] == "unify":
                    shape = _unify(shape, f)
                elif f["type"] == "heal":
                    shape = _heal(shape, f)
                elif f["type"] == "smooth":
                    shape = _smooth(shape, f)
                elif f["type"] == "hole_mesh":
                    shape = _hole_mesh(shape, f)
                elif f["type"] == "offset_faces":
                    shape = _offset_faces(shape, f)
                elif f["type"] == "move_faces":
                    shape = _move_faces(shape, f)
                elif f["type"] == "replace":
                    f["_bodies"] = bodies
                    try:
                        shape = _replace_faces(shape, f)
                    finally:
                        f.pop("_bodies", None)
                else:
                    shape = _defeature(shape, f)
                info = {"id": f.get("id"), "error": None, "cells": len(shape.solids()), "faces": len(shape.faces()),
                        "edges": len(shape.edges()), "faces_before": f0, "edges_before": e0}
                if getattr(shape, "_replace_kind", None):
                    info["note"] = "clean surface: %s" % shape._replace_kind
                og = getattr(shape, "_ogrid", None)
                if og and f["type"] == "hole_mesh":
                    info.update(blocks=og["blocks"], prisms=og["prisms"], other=og["other"], half=round(og["half"], 6),
                                holes=og["holes"], seeds=og["seeds"])
                    info["note"] = "%d hole(s), square %.3f mm: %d blocks, %d prisms%s" % (
                        og["holes"], 2 * og["half"], og["blocks"], og["prisms"],
                        ", %d other cells (not structured)" % og["other"] if og["other"] else "")
                if f["type"] == "split" and len(shape.solids()) == n0:
                    info["error"] = "the partition did not cut any cell"
                if f["type"] in ("unify", "heal") and info["faces"] == f0 and info["edges"] == e0:
                    info["note"] = "nothing to merge: no coplanar faces or collinear edges found"
                status.append(info)
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "operation failed"})
            continue
        if f["type"] == "thread":
            try:
                if shape is None:
                    raise ValueError("no solid for the thread")
                shape, rec = _thread(shape, f)
                status.append({"id": f.get("id"), "error": None, "holes": [rec]})
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "thread failed"})
            continue
        if f["type"] in ("shell", "pattern", "hole", "mirror", "boolean"):
            try:
                if shape is None:
                    raise ValueError("no solid for %s" % f["type"])
                v0 = shape.volume
                n0 = len(shape.solids())
                if f["type"] == "shell":
                    shape = _shell(shape, f)
                elif f["type"] == "boolean":
                    shape = _boolean(shape, f)
                elif f["type"] == "pattern":
                    shape = _pattern(shape, f, tools)
                elif f["type"] == "mirror":
                    f["_shape"] = shape
                    shape = _mirror(shape, f, tools)
                else:
                    shape, tool, recs = _hole(shape, f)
                    tools[f.get("id")] = (tool, True)
                info = {"id": f.get("id"), "error": None}
                if f["type"] == "hole":
                    info["holes"] = recs
                elif f["type"] in ("pattern", "mirror"):
                    info["holes"] = _copied_holes(f, status)
                if f["type"] == "boolean":
                    info["cells"] = len(shape.solids())
                    if abs(shape.volume - v0) < 1e-9 and len(shape.solids()) == n0:
                        info["error"] = "the boolean changed nothing"
                elif abs(shape.volume - v0) < 1e-9:
                    info["error"] = "the feature changed nothing"
                status.append(info)
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "operation failed"})
            continue
        if f["type"] in ("fillet", "chamfer"):
            try:
                if shape is None:
                    raise ValueError("no solid to %s" % f["type"])
                edges = find_edges(shape, f.get("edges") or [])
                if not edges:
                    raise ValueError("no edges selected")
                v = float(f.get("value", 1) or 0)
                if v <= 0:
                    raise ValueError("value must be > 0")
                new = _round_edges(shape, f["type"], v, edges)
                if new is None:
                    msg, bad = _round_diagnosis(shape, f["type"], v, edges)
                    refs = [r for r in f.get("edges") or [] if find_edges(shape, [r])]
                    status.append({"id": f.get("id"), "error": msg,
                                   "bad_edges": [refs[i] for i in bad if i < len(refs)]})
                    continue
                shape = new
                status.append({"id": f.get("id"), "error": None})
            except Exception as e:
                status.append({"id": f.get("id"), "error": str(e).strip() or "operation failed"})
            continue
        try:
            notes = []
            faces = profile_faces(f.get("sketch") or {}, plane_of(f), notes)
            if f.get("regions"):
                faces = select_regions(f.get("sketch") or {}, plane_of(f), f["regions"])
            size = 100.0
            if shape is not None:
                bb = shape.bounding_box()
                size = max(size, bb.diagonal)
            for fc in faces:
                bb = fc.bounding_box()
                size = max(size, bb.diagonal)
            if f["type"] == "sweep":
                f["_bodies"] = bodies
                try:
                    solids = _sweep_of(f, faces)
                finally:
                    f.pop("_bodies", None)
            else:
                solids = _solid_of(f, faces, size)
            cut = f["type"] == "cut" or (f["type"] in ("revolve", "sweep") and f.get("mode") == "cut")
            tools[f.get("id")] = (solids, cut)
            bb = faces[0].bounding_box()
            for fc in faces[1:]:
                bb = bb.add(fc.bounding_box())
            info = {"id": f.get("id"), "error": None, "profiles": len(faces),
                    "extent": [round(bb.min.X, 2), round(bb.min.Y, 2), round(bb.min.Z, 2),
                               round(bb.max.X, 2), round(bb.max.Y, 2), round(bb.max.Z, 2)]}
            if notes:
                info["note"] = "; ".join(notes)
            v0 = shape.volume if shape is not None else 0.0
            if cut:
                if shape is None:
                    raise ValueError("nothing to cut")
                shape0 = shape
                for s in solids:
                    shape = shape.cut(s).clean()
                if abs(shape.volume - v0) < 1e-6 * max(v0, 1.0) and f["type"] == "cut" and not (f.get("symmetric") or f.get("through")):
                    # nothing removed in this direction: the cut is tried in the opposite direction
                    g = dict(f)
                    g["reverse"] = not f.get("reverse")
                    solids2 = _solid_of(g, faces, size)
                    shape2 = shape0
                    for s in solids2:
                        shape2 = shape2.cut(s).clean()
                    if abs(shape2.volume - v0) >= 1e-6 * max(v0, 1.0):
                        shape, solids = shape2, solids2
                        tools[f.get("id")] = (solids, cut)
                        info["flipped"] = True
                if abs(shape.volume - v0) < 1e-6 * max(v0, 1.0):
                    info["error"] = "the cut removed nothing: the profile does not pass through the part"
            elif f.get("new_body"):
                # a separate solid, not fused with the part (combined later by a Boolean feature)
                for s in solids:
                    shape = s if shape is None else Compound(children=list(shape.solids()) + list(s.solids()))
                info["new_body"] = True
            else:
                for s in solids:
                    shape = _fuse(shape, s)
                if shape is not None and abs(shape.volume - v0) < 1e-9:
                    info["error"] = "the feature added nothing"
            status.append(info)
        except Exception as e:
            status.append({"id": f.get("id"), "error": str(e)})
    if prev_id is not None:
        attribute(prev_id)
    if owners is not None:
        owners.update(face_owner)
    for s in status:
        if s.get("id") in frames:
            s["frame"] = frames[s["id"]]
    return shape, status


# --------------------------------------------------------------------------- shell, pattern, hole, sweep

def face_key(fc):
    c = fc.center()
    try:
        n = fc.normal_at(c)
    except Exception:
        n = fc.normal_at()
    return {"c": [round(c.X, 4), round(c.Y, 4), round(c.Z, 4)], "n": [round(n.X, 4), round(n.Y, 4), round(n.Z, 4)],
            "area": round(fc.area, 4)}


def find_faces(shape, refs):
    faces = list(shape.faces())
    out = []
    for r in refs:
        c = r.get("c")
        best, bd = None, None
        for fc in faces:
            fcc = fc.center()
            d = math.sqrt((fcc.X - c[0]) ** 2 + (fcc.Y - c[1]) ** 2 + (fcc.Z - c[2]) ** 2)
            if bd is None or d < bd:
                best, bd = fc, d
        if best is not None and bd < max(0.05, 0.01 * math.sqrt(max(float(r.get("area", 1) or 1), 1.0))) + 1e-6:
            if not any(best.wrapped.IsSame(o.wrapped) for o in out):
                out.append(best)
    return out


def find_faces_any(shape, bodies, refs):
    """Faces matching the references on the solid or on any surface body."""
    out = []
    for r in refs:
        got = find_faces(shape, [r]) if shape is not None else []
        if not got:
            for b in (bodies or {}).values():
                if b is None or not b.faces():
                    continue
                got = find_faces(b, [r])
                if got:
                    break
        for fc in got:
            if not any(fc.wrapped.IsSame(o.wrapped) for o in out):
                out.append(fc)
    return out


def _round_edges(shape, kind, v, edges):
    """Fillet (radius v) or chamfer (distance v) of the edges; None when OpenCascade fails or the result is not
    a valid solid."""
    try:
        new = shape.fillet(v, edges) if kind == "fillet" else shape.chamfer(v, None, edges)
        return new if (new.is_valid() if callable(new.is_valid) else new.is_valid) else None
    except Exception:
        return None


def _round_diagnosis(shape, kind, v, edges, budget=5.0):
    """(message, indices of the failing edges) for a failed fillet or chamfer of v mm: each edge is tried alone;
    an edge that fails alone gets its largest value (bisection, 12 steps); when every edge works alone the largest
    value for all edges together is given (the roundings of neighbouring edges overlap on a face). The search stops
    after budget seconds."""
    import time
    t0 = time.time()
    word = "radius" if kind == "fillet" else "distance"
    name = "Fillet" if kind == "fillet" else "Chamfer"

    def largest(es):
        lo, hi = 0.0, v
        for _ in range(12):
            if time.time() - t0 > budget:
                return None
            mid = (lo + hi) / 2.0
            if _round_edges(shape, kind, mid, es) is not None:
                lo = mid
            else:
                hi = mid
        return math.floor(lo * 100.0) / 100.0

    bad = []
    for i, e in enumerate(edges):
        if time.time() - t0 > budget:
            break
        if _round_edges(shape, kind, v, [e]) is None:
            bad.append(i)
    if bad:
        parts = []
        for i in bad:
            r = largest([edges[i]]) if len(bad) <= 6 else None
            parts.append("edge %d%s" % (i + 1, (": largest %s %.2f mm" % (word, r)) if r else ""))
        msg = "%s of %g mm fails on %d of %d edge(s) (red): %s" % (name, v, len(bad), len(edges), "; ".join(parts))
        return msg, bad
    pairs = []
    if len(edges) <= 10:
        for i in range(len(edges)):
            for j in range(i + 1, len(edges)):
                if time.time() - t0 > budget:
                    break
                if _round_edges(shape, kind, v, [edges[i], edges[j]]) is None:
                    pairs.append((i, j))
    r = largest(edges)
    msg = ("%s of %g mm works on each edge alone but not on all %d edges together: the %ss of neighbouring edges "
           "overlap on a face" % (name, v, len(edges), kind))
    if pairs:
        msg += " (%s, red)" % ", ".join("edges %d and %d" % (i + 1, j + 1) for i, j in pairs)
    if r:
        msg += "; largest %s for all edges %.2f mm" % (word, r)
    return msg, sorted({k for q in pairs for k in q})


def find_edges_any(shape, bodies, refs):
    """Edges matching the references on the solid or on any surface or curve body."""
    out = []
    for r in refs:
        got = find_edges(shape, [r]) if shape is not None else []
        if not got:
            for b in (bodies or {}).values():
                if b is None:
                    continue
                got = find_edges(b, [r])
                if got:
                    break
        for e in got:
            if not any(e.wrapped.IsSame(o.wrapped) for o in out):
                out.append(e)
    return out


def _shell(shape, f):
    from build123d import offset, Kind
    t = float(f.get("thickness", 1) or 0)
    if t <= 0:
        raise ValueError("thickness must be > 0")
    openings = find_faces(shape, f.get("faces") or [])
    res = offset(shape, amount=-t, openings=openings or None, kind=Kind.INTERSECTION)
    solids = res.solids()
    if not solids:
        raise ValueError("shell failed (thickness too large?)")
    return solids[0] if len(solids) == 1 else res


def _pattern_trsfs(f, n):
    """Transforms for instances 1..n-1 as build123d Locations."""
    from build123d import Vector, Axis
    out = []
    if f.get("kind", "linear") == "linear":
        st = [float(v or 0) for v in (f.get("step") or [10, 0, 0])]
        n2 = int(f.get("count2", 1) or 1)
        st2 = [float(v or 0) for v in (f.get("step2") or [0, 10, 0])]
        ro = float(f.get("row_offset", 0) or 0)          # shift of every second row along direction 1
        l1 = math.sqrt(sum(v * v for v in st)) or 1.0
        u1 = [v / l1 for v in st]
        for j in range(max(1, n2)):
            for i in range(n):
                if i == 0 and j == 0:
                    continue
                sh = ro if (j % 2 == 1) else 0.0
                out.append(("t", Vector(st[0] * i + st2[0] * j + u1[0] * sh, st[1] * i + st2[1] * j + u1[1] * sh, st[2] * i + st2[2] * j + u1[2] * sh)))
    else:
        ax = f.get("axis", "Z")
        c = [float(v or 0) for v in (f.get("centre") or [0, 0, 0])]
        total = float(f.get("angle", 360) or 360)
        step = total / n if abs(total - 360.0) < 1e-9 else (total / (n - 1) if n > 1 else 0.0)
        d = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[ax]
        if f.get("axis_ref"):
            a = ref_axis(f.get("_datums"), f["axis_ref"])
            c, d = a["o"], tuple(a["d"])
        for i in range(1, n):
            out.append(("r", Axis(c, d), step * i))
    return out


def _apply_trsf(shape, tr):
    if tr[0] == "t":
        return shape.translate(tr[1])
    return shape.rotate(tr[1], tr[2])


def _pattern(shape, f, tools):
    n = int(f.get("count", 2) or 0)
    if n < 2:
        raise ValueError("count must be at least 2")
    ids = f.get("features") or []
    if not ids:
        raise ValueError("no features selected")
    missing = [i for i in ids if i not in tools]
    if missing:
        raise ValueError("feature %s has no tool body (only sketch features and holes can be patterned)" % missing[0])
    for tr in _pattern_trsfs(f, n):
        for fid in ids:
            solids, cut = tools[fid]
            for s0 in solids:
                s1 = _apply_trsf(s0, tr)
                shape = shape.cut(s1).clean() if cut else _fuse(shape, s1)
    return shape


def _mirror_plane(shape, f):
    """gp_Pln of a mirror feature: method principal (plane + offset), datum (plane feature + offset) or face
    (a planar face of the solid)."""
    from OCP.gp import gp_Pln, gp_Pnt, gp_Dir
    m = f.get("method") or "principal"
    if m == "face":
        fc, c, n = _planar_face(shape, f.get("face"), "mirror face")
        return gp_Pln(gp_Pnt(*c), gp_Dir(*n))
    g = dict(f)
    g["method"] = m
    g.pop("relative", None)
    return _plane_of_split(shape, g)


def _mirror(shape, f, tools):
    """Mirror: the tool bodies of the selected features (sketch features and holes) are mirrored about the plane
    and applied again (cut or fuse); with body set, the whole solid is mirrored and fused."""
    from build123d import Plane, Vector
    pln = _mirror_plane(shape, f)
    L, D = pln.Location(), pln.Axis().Direction()
    mp = Plane(origin=Vector(L.X(), L.Y(), L.Z()), z_dir=Vector(D.X(), D.Y(), D.Z()))
    ids = f.get("features") or []
    if not ids and not f.get("body"):
        raise ValueError("no features selected")
    missing = [i for i in ids if i not in tools]
    if missing:
        raise ValueError("feature %s has no tool body (only sketch features and holes can be mirrored)" % missing[0])
    if f.get("body"):
        shape = _fuse(shape, shape.mirror(mp))
    for fid in ids:
        solids, cut = tools[fid]
        for s0 in solids:
            s1 = s0.mirror(mp)
            shape = shape.cut(s1).clean() if cut else _fuse(shape, s1)
    return shape


def _hole_trsfs(f, shape):
    """gp_Trsf of every copy made by a pattern or mirror feature."""
    from OCP.gp import gp_Trsf, gp_Vec, gp_Ax1, gp_Pnt, gp_Dir, gp_Ax2
    out = []
    if f["type"] == "mirror":
        pln = _mirror_plane(shape, f)
        tr = gp_Trsf()
        tr.SetMirror(gp_Ax2(pln.Location(), pln.Axis().Direction()))
        return [tr]
    for t in _pattern_trsfs(f, int(f.get("count", 2) or 0)):
        tr = gp_Trsf()
        if t[0] == "t":
            tr.SetTranslation(gp_Vec(t[1].X, t[1].Y, t[1].Z))
        else:
            ax = t[1]
            tr.SetRotation(gp_Ax1(gp_Pnt(ax.position.X, ax.position.Y, ax.position.Z), gp_Dir(ax.direction.X, ax.direction.Y, ax.direction.Z)), math.radians(t[2]))
        out.append(tr)
    return out


def _copied_holes(f, status):
    """Hole records of the holes copied by a pattern or mirror feature f (for callouts and cosmetic threads).
    The records of the source hole feature get the new total count."""
    from OCP.gp import gp_Pnt, gp_Dir
    ids = set(f.get("features") or [])
    src = [h for st in status if st.get("id") in ids for h in (st.get("holes") or [])]
    if not src:
        return []
    allrecs = [h for st in status for h in (st.get("holes") or []) if h.get("feature") in ids]
    shape = f.get("_shape")
    trs = _hole_trsfs(f, shape)
    out = []
    for h in src:
        for tr in trs:
            p = gp_Pnt(*h["p"]).Transformed(tr)
            d = gp_Dir(*h["d"]).Transformed(tr)
            g = dict(h)
            g["p"] = [round(p.X(), 4), round(p.Y(), 4), round(p.Z(), 4)]
            g["d"] = [round(d.X(), 6), round(d.Y(), 6), round(d.Z(), 6)]
            out.append(g)
    by_feat = {}
    for h in allrecs + out:
        by_feat.setdefault(h.get("feature"), []).append(h)
    for hs in by_feat.values():
        for h in hs:
            h["count"] = len(hs)
    return out


def _hole(shape, f):
    """Hole feature: cylinders (and counterbore / countersink) from the plane into -normal."""
    from build123d import Solid, Vector, Plane
    plane = plane_of(f)
    sk = f.get("sketch") or {}
    pts = []
    for e in sk.get("entities") or []:
        if e.get("constr"):
            continue
        if e["t"] == "point":
            pts.append((e["x"], e["y"]))
        elif e["t"] == "circle":
            pts.append((e["cx"], e["cy"]))
    if not pts:
        raise ValueError("the hole sketch needs points or circles for the hole positions")
    dia = float(f.get("dia", 6) or 0)
    if dia <= 0:
        raise ValueError("diameter must be > 0")
    bb = shape.bounding_box()
    big = bb.diagonal * 2 + 10
    depth = f.get("depth")
    depth = float(depth) if depth not in (None, "", 0) else None
    n = Vector(plane.z_dir)
    tools_out = []
    recs = []
    corners = [Vector(x, y, z) for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y) for z in (bb.min.Z, bb.max.Z)]
    # drilling direction: -normal of the plane; +normal when the part lies only on that side, or with "reverse"
    o0 = plane.from_local_coords(Vector(pts[0][0], pts[0][1], 0))
    below = max((c - o0).dot(-n) for c in corners)
    above = max((c - o0).dot(n) for c in corners)
    if (below <= 1e-6 < above) != bool(f.get("reverse")):
        n = -n
    tol = (f.get("tol") or "").strip()
    for u, v in pts:
        origin = plane.from_local_coords(Vector(u, v, 0))
        reach = max((c - origin).dot(-n) for c in corners)
        recs.append({"p": [round(origin.X, 4), round(origin.Y, 4), round(origin.Z, 4)],
                     "d": [round(-n.X, 6), round(-n.Y, 6), round(-n.Z, 6)],
                     "dia": dia, "depth": depth, "through": depth is None, "reach": round(max(reach, 0.0), 4),
                     "thread": (f.get("thread") or "").strip(), "major": thread_major(f.get("thread"), dia), "tol": tol,
                     "cbore_dia": float(f.get("cbore_dia") or 0), "cbore_depth": float(f.get("cbore_depth") or 0),
                     "csink_dia": float(f.get("csink_dia") or 0), "csink_angle": float(f.get("csink_angle") or 90),
                     "count": len(pts), "feature": f.get("id")})
        # local plane at the hole, normal along -n (drilling direction), extended 1 mm above the surface
        hp = Plane(origin=origin + n * 1.0, x_dir=plane.x_dir, z_dir=-n)
        L = (depth + 1.0) if depth else big
        cyl = Solid.make_cylinder(dia / 2.0, L, hp)
        tool = cyl
        cb_d, cb_h = float(f.get("cbore_dia") or 0), float(f.get("cbore_depth") or 0)
        if cb_d > dia and cb_h > 0:
            tool = tool.fuse(Solid.make_cylinder(cb_d / 2.0, cb_h + 1.0, hp))
        cs_d, cs_a = float(f.get("csink_dia") or 0), float(f.get("csink_angle") or 90)
        if cs_d > dia and 0 < cs_a < 180:
            ta = math.tan(math.radians(cs_a / 2.0))
            h = (cs_d / 2.0) / ta
            cone = Solid.make_cone(cs_d / 2.0 + ta, 0.0, h + 1.0, hp)
            tool = tool.fuse(cone)
        tool = tool.clean()
        tools_out.append(tool)
        shape = shape.cut(tool).clean()
    return shape, tools_out, recs


def parse_metric(text):
    """(d, P) of a metric designation M8, M8x1.25, M 10 x 1 (coarse pitch from ISO 261 when none is given), else None."""
    import re
    from . import fasteners
    t = (text or "").strip().upper().replace(" ", "")
    m = re.match(r"^M(\d+(?:\.\d+)?)(?:X(\d+(?:\.\d+)?))?", t)
    if not m:
        return None
    d = float(m.group(1))
    P = float(m.group(2)) if m.group(2) else dict(fasteners.COARSE).get(d)
    return (d, P) if P else None


def parse_trapezoidal(text):
    """(d, P) of a trapezoidal designation Tr20x4 (ISO 2904 pitch when none is given), else None."""
    import re
    from . import fasteners
    t = (text or "").strip().upper().replace(" ", "")
    m = re.match(r"^TR(\d+(?:\.\d+)?)(?:X(\d+(?:\.\d+)?))?", t)
    if not m:
        return None
    d = float(m.group(1))
    P = float(m.group(2)) if m.group(2) else dict(fasteners.TRAPEZOIDAL).get(d)
    return (d, P) if P else None


def parse_other_thread(text):
    """Unified (1/4-20 UNC, #10-32 UNF) or pipe (G1/2) designation -> profile dict with d, P, d3/d1, depth, else None."""
    from . import fasteners
    t = (text or "").strip()
    u = fasteners.find_unified(t)
    if u:
        return {"kind": "UN", "d": u["d"], "P": u["P"], "d3": u["d3"], "D1": u["D1"], "h3": u["h3"], "H1": u["H1"], "drill": u["drill"], "R": u["R"]}
    g = fasteners.find_bspp(t)
    if g:
        return {"kind": "G", "d": g["d"], "P": g["P"], "d3": g["d1"], "D1": g["d1"], "h3": g["h"], "H1": g["h"], "drill": g["drill"], "R": g["r"]}
    return None


def thread_machining(h, units="mm"):
    """Second callout line for a metric thread: the bore or the outside diameter before threading with its limits
    and the nominal thread depth (internal: tap drill and D1 of the class, depth H1; external: d max/min of the
    class, d3, depth h3). units "inch": lengths in inch (drawing units option)."""
    from . import fasteners
    from .units import inch_text
    if units == "inch":
        g = lambda v: inch_text(v, 3)            # noqa: E731
        f3 = lambda v: inch_text(v, 4)           # noqa: E731
    else:
        g = lambda v: "%g" % v                    # noqa: E731
        f3 = lambda v: "%.3f" % v                 # noqa: E731
    o = parse_other_thread(h.get("thread"))
    if o:
        if h.get("kind") == "external":
            return "turn \u00d8%s, minor %s, thread depth %s, root radius %s, pitch %s" % (f3(o["d"]), f3(o["d3"]), f3(o["h3"]), f3(o["R"]), f3(o["P"]))
        return "drill \u00d8%s (minor %s), thread depth %s, pitch %s" % (g(o["drill"]), f3(o["D1"]), f3(o["H1"]), f3(o["P"]))
    tr = parse_trapezoidal(h.get("thread"))
    if tr:
        d, P = tr
        pr = fasteners.trapezoidal_profile(d, P)
        if h.get("kind") == "external":
            return "turn \u00d8%s, d3 %s, thread depth %s, root radius max %s" % (g(d), f3(pr["d3"]), f3(pr["h3"]), f3(pr["R2max"]))
        return "bore \u00d8%s (D1), D4 %s, thread depth %s" % (f3(pr["D1"]), f3(pr["D4"]), f3(pr["h3"]))
    dp = parse_metric(h.get("thread"))
    if not dp:
        return ""
    d, P = dp
    pr = fasteners.metric_profile(d, P)
    cls = (h.get("tol") or "").strip() or ("6g" if h.get("kind") == "external" else "6H")
    t = fasteners.tolerance(d, P, cls)
    if h.get("kind") == "external":
        if t:
            return "turn \u00d8%s\u2013%s, d3 %s\u2013%s, thread depth %s" % (f3(t["d_max"]), f3(t["d_min"]), f3(t["d3_max"]), f3(t["d3_min"]), f3(pr["h3"]))
        return "turn \u00d8%s, d3 %s, thread depth %s" % (g(d), f3(pr["d3"]), f3(pr["h3"]))
    if t:
        return "drill \u00d8%s (D1 %s\u2013%s), thread depth %s" % (g(pr["drill"]), f3(t["D1_min"]), f3(t["D1_max"]), f3(pr["H1"]))
    return "drill \u00d8%s, thread depth %s" % (g(pr["drill"]), f3(pr["H1"]))


def _thread(shape, f):
    """External thread on a cylindrical face: a cosmetic thread record (drawing) and, with cut_od, the face turned
    down to the maximum major diameter of the tolerance class over the thread length. Returns (shape, record)."""
    from build123d import Solid, Vector, Plane
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.BRepTools import BRepTools
    from . import fasteners
    if not f.get("face"):
        raise ValueError("pick the cylindrical face")
    faces = find_faces(shape, [f["face"]])
    if not faces:
        raise ValueError("the face was not found")
    fc = faces[0]
    ad = BRepAdaptor_Surface(fc.wrapped)
    if ad.GetType() != GeomAbs_Cylinder:
        raise ValueError("the face is not cylindrical")
    cyl = ad.Cylinder()
    ax = cyl.Axis()
    L, D = ax.Location(), ax.Direction()
    o = Vector(L.X(), L.Y(), L.Z())
    n = Vector(D.X(), D.Y(), D.Z()).normalized()
    r_face = cyl.Radius()
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(fc.wrapped)
    # v is the axial parameter of a cylindrical surface (length along the axis)
    a0, a1 = o + n * vmin, o + n * vmax
    face_len = abs(vmax - vmin)
    rev = bool(f.get("reverse"))
    start, into = (a1, -n) if not rev else (a0, n)
    thread = (f.get("thread") or "").strip()
    tr = parse_trapezoidal(thread)
    other = parse_other_thread(thread)
    dp = tr or (other and (other["d"], other["P"])) or parse_metric(thread)
    if not dp:
        raise ValueError("thread designation: M8, M10x1.25, Tr20x4, 1/4-20 UNC, G1/2, ...")
    d, P = dp
    if abs(2 * r_face - d) > 0.6 * d:
        raise ValueError("the face diameter %.2f mm does not match %s" % (2 * r_face, thread))
    pr = fasteners.trapezoidal_profile(d, P) if tr else {"d3": other["d3"], "h3": other["h3"]} if other else fasteners.metric_profile(d, P)
    length = float(f.get("length") or 0) or face_len
    length = min(length, face_len)
    cls = (f.get("tol") or ("7e" if tr else "2A" if other and other["kind"] == "UN" else "A" if other else "6g")).strip()
    t = None if (tr or other) else fasteners.tolerance(d, P, cls)
    if f.get("cut_od") and t and t["d_max"] / 2.0 < r_face - 1e-6:
        pl = Plane(origin=start, z_dir=into)
        tube = Solid.make_cylinder(r_face + 1.0, length, pl).cut(Solid.make_cylinder(t["d_max"] / 2.0, length, pl))
        shape = shape.cut(tube).clean()
        r_face = t["d_max"] / 2.0
    rec = {"kind": "external", "p": [round(start.X, 4), round(start.Y, 4), round(start.Z, 4)],
           "d": [round(into.X, 6), round(into.Y, 6), round(into.Z, 6)], "dia": round(2 * r_face, 4), "major": d,
           "minor": pr["d3"], "P": P, "depth": round(length, 4), "through": False, "reach": round(length, 4),
           "thread": thread, "tol": cls, "count": 1, "feature": f.get("id"), "chamfer": bool(f.get("chamfer"))}
    return shape, rec


def thread_major(text, dia):
    """Major diameter (mm) of a thread designation: M8, M8x1.25, M 10 x 1, G1/4 (approximate), else 0."""
    import re
    o = parse_other_thread(text)
    if o:
        return o["d"]
    t = (text or "").strip().upper().replace(" ", "")
    m = re.match(r"^(?:M|TR)(\d+(?:\.\d+)?)", t)
    if m:
        return float(m.group(1))
    m = re.match(r"^G(\d+)/(\d+)", t) or re.match(r"^G(\d+)$", t)
    if m:
        inch = float(m.group(1)) / float(m.group(2)) if m.lastindex == 2 else float(m.group(1))
        return round({0.125: 9.728, 0.25: 13.157, 0.375: 16.662, 0.5: 20.955, 0.75: 26.441, 1.0: 33.249}.get(inch, inch * 25.4 + 7.0), 3)
    return 0.0


def mesh_compounds(part_rec, shape):
    """Compound face groups of the combine features for the mesher: ([[{"c", "area"}, ...], ...], min_area)."""
    groups, min_area = [], 0.0
    if shape is None:
        return groups, min_area
    for f in part_rec.get("features") or []:
        if f.get("type") != "combine" or f.get("suppressed"):
            continue
        faces = find_faces(shape, f.get("faces") or [])
        if len(faces) > 1:
            groups.append([{"c": [fc.center().X, fc.center().Y, fc.center().Z], "area": fc.area} for fc in faces])
        min_area = max(min_area, float(f.get("min_area") or 0))
    return groups, min_area


def holes_of(status):
    """Hole records of a build status list (for callouts and cosmetic threads)."""
    out = []
    for st in status or []:
        out += st.get("holes") or []
    return out


def callout_text(h, units="mm"):
    """Hole callout text: count, thread or diameter, counterbore / countersink, depth. An external thread:
    designation, class and length. A metric thread gets a second line with the bore or outside diameter before
    threading and the nominal thread depth. units "inch": lengths in inch (drawing units option)."""
    from .units import inch_text
    g = (lambda v: inch_text(v, 3)) if units == "inch" else (lambda v: "%g" % v)
    parts = []
    tol = (h.get("tol") or "").strip()
    if h.get("kind") == "external":
        text = h["thread"] + ("-" + tol if tol else "") + " x %s" % g(h["depth"])
        mach = thread_machining(h, units)
        return text + ("\n" + mach if mach else "")
    if h.get("thread"):
        parts.append(h["thread"] + ("-" + tol if tol else ""))
    else:
        parts.append("\u00d8%s" % g(h["dia"]) + (" " + tol if tol else ""))
    if h.get("cbore_dia", 0) > h["dia"] and h.get("cbore_depth", 0) > 0:
        parts.append("\u00d8%s counterbore %s deep" % (g(h["cbore_dia"]), g(h["cbore_depth"])))
    if h.get("csink_dia", 0) > h["dia"]:
        parts.append("\u00d8%s x %g\u00b0 countersink" % (g(h["csink_dia"]), h.get("csink_angle", 90)))
    parts.append("through" if h.get("through") else "%s deep" % g(h["depth"]))
    text = ", ".join(parts)
    if h.get("count", 1) > 1:
        text = "%dx %s" % (h["count"], text)
    mach = thread_machining(h, units) if h.get("thread") else ""
    return text + ("\n" + mach if mach else "")


def _sweep_of(f, faces):
    """Sweep the profile faces along the path sketch (open chain of lines and arcs on its own plane)."""
    from build123d import Solid, Wire, Vector
    body = (f.get("_bodies") or {}).get(f.get("path_source")) if f.get("path_source") else None
    if body is not None:
        edges = list(body.edges())
        if not edges:
            raise ValueError("the path curve body has no edges")
    else:
        pf = {"plane": f.get("path_plane", "XY"), "offset": f.get("path_offset", 0)}
        pplane = plane_of(pf)
        segs, circles = _segments(f.get("path_sketch") or {})
        if not segs:
            raise ValueError("the path sketch has no lines or arcs")
        W = lambda p: pplane.from_local_coords(Vector(p[0], p[1], 0))
        edges = []
        for k, a, b, m in segs:
            edges.append(seg_edge(k, a, b, m, W))
    try:
        path = Wire(edges)
    except Exception:
        raise ValueError("the path is not one connected chain")
    out = []
    for face in faces:
        out.append(Solid.sweep(face, path, transition=__import__("build123d").Transition.ROUND))
    return out


# --------------------------------------------------------------------------- edges

def edge_key(e):
    m = e.position_at(0.5)
    return {"mid": [round(m.X, 4), round(m.Y, 4), round(m.Z, 4)], "len": round(e.length, 4)}


def expand_edges(shape, refs, mode):
    """Edge references extended from the picked edges: mode "tangent": the chain of edges with tangent continuity
    at the shared vertices; "face": all edges of the faces adjacent to the picked edges; "faces": refs are face
    references (face_key), result is all edges of these faces."""
    from OCP.TopExp import TopExp
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    try:
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape as ShapeMap
    except ImportError:                       # OCCT 8
        from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
    from build123d import Edge, Face
    if mode == "faces":
        out = []
        for fc in find_faces(shape, refs):
            for x in fc.edges():
                if all(not x.wrapped.IsSame(o.wrapped) for o in out):
                    out.append(x)
        return [edge_key(e) for e in out]
    picked = find_edges(shape, refs)
    if not picked:
        return refs
    out = list(picked)

    def add(e):
        if all(not e.wrapped.IsSame(o.wrapped) for o in out):
            out.append(e)

    if mode == "face":
        m = ShapeMap()
        TopExp.MapShapesAndAncestors_s(shape.wrapped, TopAbs_EDGE, TopAbs_FACE, m)
        for e in picked:
            if m.Contains(e.wrapped):
                for fc in m.FindFromKey(e.wrapped):
                    for x in Face(fc).edges():
                        add(x)
    elif mode == "tangent":
        m = ShapeMap()
        TopExp.MapShapesAndAncestors_s(shape.wrapped, TopAbs_VERTEX, TopAbs_EDGE, m)
        queue = list(picked)
        while queue:
            e = queue.pop()
            for t, vtx in ((0.0, e.vertices()[0]), (1.0, e.vertices()[-1])):
                if not m.Contains(vtx.wrapped):
                    continue
                for other in m.FindFromKey(vtx.wrapped):
                    o = Edge(other)
                    if o.wrapped.IsSame(e.wrapped) or any(o.wrapped.IsSame(x.wrapped) for x in out):
                        continue
                    # tangent at the shared vertex
                    pe = e.position_at(t)
                    te = e.tangent_at(t)
                    to = o.tangent_at(0.0 if (o.position_at(0.0) - pe).length < 1e-6 else 1.0)
                    if abs(te.normalized().dot(to.normalized())) > 0.9998:
                        add(o)
                        queue.append(o)
    return [edge_key(e) for e in out]


def find_edges(shape, refs):
    """Edges of shape matching the references (nearest mid point, length within 1 %)."""
    edges = list(shape.edges())
    out = []
    for r in refs:
        mid, ln = r.get("mid"), float(r.get("len", 0) or 0)
        best, bd = None, None
        for e in edges:
            m = e.position_at(0.5)
            d = math.sqrt((m.X - mid[0]) ** 2 + (m.Y - mid[1]) ** 2 + (m.Z - mid[2]) ** 2)
            if bd is None or d < bd:
                best, bd = e, d
        if best is not None and bd < max(0.05, 0.01 * max(ln, 1.0)) and abs(best.length - ln) <= 0.01 * max(ln, 1.0) + 1e-6:
            if all(best.wrapped.IsSame(o.wrapped) is False for o in out):
                out.append(best)
    return out


# --------------------------------------------------------------------------- display and references

def round_info(sh):
    """Radius (mm) and angular span (deg) of a circular edge or a cylindrical face; None for other geometry."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cylinder
    w = sh.wrapped
    if isinstance(sh, __import__("build123d").Edge):
        a = BRepAdaptor_Curve(w)
        if a.GetType() != GeomAbs_Circle:
            return None
        r, span = a.Circle().Radius(), abs(a.LastParameter() - a.FirstParameter())
    else:
        a = BRepAdaptor_Surface(w, True)
        if a.GetType() != GeomAbs_Cylinder:
            return None
        r, span = a.Cylinder().Radius(), abs(a.LastUParameter() - a.FirstUParameter())
    return {"r": round(r, 5), "span": round(math.degrees(min(span, 2 * math.pi)), 3)}


def mesh(shape, tol=None):
    """Triangles and edge polylines for the 3D view. One BRepMesh pass over the shape; the triangles of each face and
    the polyline of each edge are read from the triangulation (edges without a face: sampled along the curve).
    face_keys, edge_keys: one per face and per edge, in the order of shape.faces() and shape.edges()."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopAbs import TopAbs_REVERSED, TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    try:
        from OCP.TopTools import TopTools_IndexedMapOfShape as ShapeMap
    except ImportError:                       # OCCT 8
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
    to_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    if shape is None:
        return {"vertices": [], "triangles": [], "edges": [], "bbox": None}
    bb = shape.bounding_box()
    tol = tol or max(bb.diagonal / 2000.0, 0.005)
    BRepMesh_IncrementalMesh(shape.wrapped, tol, False, 0.3, True)
    faces, edges_b = list(shape.faces()), list(shape.edges())
    fmap, emap = ShapeMap(), ShapeMap()
    for fc in faces:
        fmap.Add(fc.wrapped)
    for e in edges_b:
        emap.Add(e.wrapped)
    # solid index of each face and solids of each edge (by identity)
    face_solid = [-1] * len(faces)
    edge_solids = [[] for _ in edges_b]
    for si, so in enumerate(shape.solids()):
        ex = TopExp_Explorer(so.wrapped, TopAbs_FACE)
        while ex.More():
            i = fmap.FindIndex(ex.Current())
            if i:
                face_solid[i - 1] = si
            ex.Next()
        seen = set()
        ex = TopExp_Explorer(so.wrapped, TopAbs_EDGE)
        while ex.More():
            i = emap.FindIndex(ex.Current())
            if i and i not in seen:
                seen.add(i)
                edge_solids[i - 1].append(si)
            ex.Next()
    verts, tris, face_of_tri, face_keys = [], [], [], []
    poly = {}                                  # edge index -> polyline
    for fi, fc in enumerate(faces):
        try:
            fk = face_key(fc)
            ri = round_info(fc)
            if ri:
                fk["round"] = ri
            face_keys.append(fk)
        except Exception:
            face_keys.append(None)
        f = fc.wrapped
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        trsf = loc.Transformation()
        ident = loc.IsIdentity()
        base = len(verts)
        for i in range(1, tri.NbNodes() + 1):
            p = tri.Node(i)
            if not ident:
                p = p.Transformed(trsf)
            verts.append([round(p.X(), 5), round(p.Y(), 5), round(p.Z(), 5)])
        rev = f.Orientation() == TopAbs_REVERSED
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            tris.append([base + a - 1, base + c - 1, base + b - 1] if rev else [base + a - 1, base + b - 1, base + c - 1])
        face_of_tri += [fi] * tri.NbTriangles()
        ex = TopExp_Explorer(f, TopAbs_EDGE)
        while ex.More():
            e = to_edge(ex.Current())
            ex.Next()
            k = emap.FindIndex(e)
            if not k or k in poly:
                continue
            pt = BRep_Tool.PolygonOnTriangulation_s(e, tri, loc)
            if pt is None:
                continue
            nodes = pt.Nodes()
            poly[k] = [verts[base + nodes.Value(j) - 1] for j in range(nodes.Lower(), nodes.Upper() + 1)]
    edges, keys, esol = [], [], []
    for ei, e in enumerate(edges_b):
        try:
            pl = poly.get(ei + 1)
            if pl is None:                     # an edge on no meshed face (curve bodies): sampled
                L = e.length
                n = 1 if e.geom_type.name == "LINE" else max(8, min(96, int(L / (tol * 20)) + 8))
                pl = [[round(p.X, 5), round(p.Y, 5), round(p.Z, 5)] for p in (e.position_at(i / n) for i in range(n + 1))]
            k = edge_key(e)
            ri = round_info(e)
            if ri:
                k["round"] = ri
        except Exception:
            continue
        edges.append(pl)
        keys.append(k)
        esol.append(edge_solids[ei])
    return {"vertices": verts, "triangles": tris, "edges": edges, "edge_keys": keys, "edge_solids": esol,
            "face_of_tri": face_of_tri, "face_keys": face_keys, "face_solid": face_solid,
            "bbox": [bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z]}


def face_owners(m, owners):
    """Owner feature id per face of a mesh record (None when unknown)."""
    out = []
    for k in m.get("face_keys") or []:
        if not k:
            out.append(None)
            continue
        out.append(owners.get((round(k["c"][0], 3), round(k["c"][1], 3), round(k["c"][2], 3))))
    return out


def _circle_from_points(pts, tol):
    """(cx, cy, r, a0, a1, closed) when all 2D points lie on one circle within tol, else None."""
    if len(pts) < 5:
        return None
    a, m, b = pts[0], pts[len(pts) // 2], pts[-1]
    closed = math.hypot(a[0] - b[0], a[1] - b[1]) < tol
    if closed:
        m = pts[len(pts) // 3]
        b = pts[(2 * len(pts)) // 3]
    ax, ay = a; bx, by = m; cx, cy = b
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    if r < tol:
        return None
    if any(abs(math.hypot(p[0] - ux, p[1] - uy) - r) > tol for p in pts):
        return None
    a0 = math.degrees(math.atan2(pts[0][1] - uy, pts[0][0] - ux)) % 360
    a1 = math.degrees(math.atan2(pts[-1][1] - uy, pts[-1][0] - ux)) % 360
    am = math.degrees(math.atan2(pts[1][1] - uy, pts[1][0] - ux)) % 360
    if (am - a0) % 360 > (a1 - a0) % 360:
        a0, a1 = a1, a0
    return (ux, uy, r, a0, a1, closed)


def _curve_ref(pts2, kind, tol=1e-4):
    """Reference entity for a sampled curve: a circle or arc when the points lie on a circle, else a polyline."""
    c = _circle_from_points(pts2, tol)
    if c:
        cx, cy, r, a0, a1, closed = c
        if closed:
            return {"t": "circle", "cx": cx, "cy": cy, "r": r, "kind": kind}
        return {"t": "arc", "cx": cx, "cy": cy, "r": r, "a0": a0, "a1": a1, "kind": kind}
    return {"t": "poly", "pts": [[p[0], p[1]] for p in pts2], "closed": False, "kind": kind}


def _edge_refs(body, plane):
    """Edges of a surface or curve body projected along the plane normal (kind proj), as polylines."""
    L = lambda v: plane.to_local_coords(v)
    out = []
    for e in body.edges():
        try:
            n = 2 if e.geom_type.name == "LINE" else 32
            pts = [L(e.position_at(i / n)) for i in range(n + 1)]
            if n == 2:
                out.append({"t": "line", "x1": pts[0].X, "y1": pts[0].Y, "x2": pts[-1].X, "y2": pts[-1].Y, "kind": "proj"})
            else:
                out.append(_curve_ref([(p.X, p.Y) for p in pts], "proj", 1e-3 * max(1.0, e.length)))
        except Exception:
            continue
    return out


def projected_refs(shape, plane):
    """The part seen along the plane normal (hidden-line removal), in sketch coordinates: visible edges as
    kind "proj", hidden edges as kind "hidden"."""
    from . import project as prj
    o = plane.origin
    d = [plane.z_dir.X, plane.z_dir.Y, plane.z_dir.Z]
    x = [plane.x_dir.X, plane.x_dir.Y, plane.x_dir.Z]
    y = [plane.y_dir.X, plane.y_dir.Y, plane.y_dir.Z]
    ox = o.X * x[0] + o.Y * x[1] + o.Z * x[2]
    oy = o.X * y[0] + o.Y * y[1] + o.Z * y[2]
    try:
        res = prj.hlr(shape.wrapped, d, x, hidden=True)
    except Exception:
        return []
    out = []
    seen = set()
    for kind, prims in (("proj", res["visible"]), ("hidden", res["hidden"])):
        for pr in prims:
            key = (pr[0],) + tuple(round(v, 3) for v in pr[1:] if isinstance(v, float))
            if pr[0] == "L":
                key2 = (pr[0], round(pr[3], 3), round(pr[4], 3), round(pr[1], 3), round(pr[2], 3))
                if key2 in seen:
                    continue
            if key in seen:
                continue
            seen.add(key)
            t = pr[0]
            if t == "L":
                out.append({"t": "line", "x1": pr[1] - ox, "y1": pr[2] - oy, "x2": pr[3] - ox, "y2": pr[4] - oy, "kind": kind})
            elif t == "C":
                out.append({"t": "circle", "cx": pr[1] - ox, "cy": pr[2] - oy, "r": pr[3], "kind": kind})
            elif t == "A":
                out.append({"t": "arc", "cx": pr[1] - ox, "cy": pr[2] - oy, "r": pr[3], "a0": pr[4] % 360, "a1": pr[5] % 360, "kind": kind})
            elif t == "P":
                pts2 = [(q[0] - ox, q[1] - oy) for q in pr[1]]
                out.append(_curve_ref(pts2, kind, 1e-3 * max(1.0, max(abs(v) for p in pts2 for v in p))))
    return out


def datum_refs(plane, datums, exclude=None):
    """Point, axis and plane features as reference geometry in sketch coordinates: points projected onto the
    sketch plane (kind datum), axes projected (kind axis, long lines), planes as their intersection line with
    the sketch plane (kind axis)."""
    from build123d import Vector
    out = []
    L = lambda v: plane.to_local_coords(Vector(*v))
    n = Vector(plane.z_dir)
    big = 1e4
    for did, d in (datums or {}).items():
        if did == exclude:
            continue
        k = d.get("kind")
        if k == "point":
            q = L(d["o"])
            out.append({"t": "point", "x": round(q.X, 9), "y": round(q.Y, 9), "kind": "datum", "ref": did})
        elif k == "axis":
            dv = Vector(*d["d"])
            dp = dv - n * dv.dot(n)
            if dp.length < 1e-9:
                q = L(d["o"])
                out.append({"t": "point", "x": round(q.X, 9), "y": round(q.Y, 9), "kind": "datum", "ref": did})
                continue
            dp = dp.normalized()
            o = Vector(*d["o"])
            a, b = L(o - dp * big), L(o + dp * big)
            out.append({"t": "line", "x1": round(a.X, 9), "y1": round(a.Y, 9), "x2": round(b.X, 9), "y2": round(b.Y, 9), "kind": "axis", "ref": did})
        elif k == "plane" or "z" in d:
            nz = Vector(*d["z"])
            dv = n.cross(nz)
            if dv.length < 1e-9:
                continue
            dv = dv.normalized()
            # a point on both planes
            o1, o2 = Vector(*plane.origin), Vector(*d["o"])
            w = nz - n * nz.dot(n)
            if w.length < 1e-12:
                continue
            t = (o2 - o1).dot(nz) / w.dot(nz)
            p0 = o1 + w * t
            a, b = L(p0 - dv * big), L(p0 + dv * big)
            out.append({"t": "line", "x1": round(a.X, 9), "y1": round(a.Y, 9), "x2": round(b.X, 9), "y2": round(b.Y, 9), "kind": "axis", "ref": did})
    return out


def section_refs(shape, f, datums=None, bodies=None):
    """Reference geometry for sketching on the feature plane: section of the shape with the plane
    (lines and arcs in local coordinates), plus the outline projected along the normal is not included."""
    from build123d import Vector
    plane = plane_of(f)
    out = datum_refs(plane, datums)
    # the base coordinate system projected onto the sketch plane, and the two origins as snap points
    L = lambda v: plane.to_local_coords(v)
    o = L(Vector(0, 0, 0))
    ax = {}
    for k, d in (("x", Vector(1, 0, 0)), ("y", Vector(0, 1, 0)), ("z", Vector(0, 0, 1))):
        q = L(d) - L(Vector(0, 0, 0))
        ax[k] = [q.X, q.Y]
    out.append({"t": "frame", "kind": "frame", "o": [o.X, o.Y], "x": ax["x"], "y": ax["y"], "z": ax["z"]})
    out.append({"t": "point", "x": 0.0, "y": 0.0, "kind": "origin"})
    if abs(o.X) > 1e-9 or abs(o.Y) > 1e-9:
        out.append({"t": "point", "x": o.X, "y": o.Y, "kind": "origin"})
    # the solid, then the surface and curve bodies (except the body the feature itself produces)
    targets = []
    if shape is not None:
        targets.append(shape)
    for bid, body in (bodies or {}).items():
        if body is None or bid == f.get("id"):
            continue
        targets.append(body)
    for tgt in targets:
        out += _section_refs_of(tgt, plane, f.get("_project", True), tgt is shape)
    return out


def _section_refs_of(shape, plane, project, is_solid):
    """Section (kind section) and projection (kind proj / hidden) of one shape onto the sketch plane."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from build123d import Shape as B3Shape
    out = []
    if project:
        try:
            out += projected_refs(shape, plane) if is_solid else _edge_refs(shape, plane)
        except Exception:
            pass
    sec = BRepAlgoAPI_Section(shape.wrapped, plane.wrapped)
    sec.Build()
    if not sec.IsDone():
        return out
    res = B3Shape.cast(sec.Shape())
    L = lambda v: plane.to_local_coords(v)
    for e in res.edges():
        try:
            g = e.geom_type.name
            if g == "LINE":
                a, b = L(e.position_at(0)), L(e.position_at(1))
                out.append({"t": "line", "x1": a.X, "y1": a.Y, "x2": b.X, "y2": b.Y, "kind": "section"})
            elif g == "CIRCLE":
                c = L(e.arc_center)
                r = e.radius
                a, m, b = L(e.position_at(0)), L(e.position_at(0.5)), L(e.position_at(1))
                if a.sub(b).length < 1e-7:
                    out.append({"t": "circle", "cx": c.X, "cy": c.Y, "r": r, "kind": "section"})
                else:
                    a0 = math.degrees(math.atan2(a.Y - c.Y, a.X - c.X)) % 360
                    a1 = math.degrees(math.atan2(b.Y - c.Y, b.X - c.X)) % 360
                    am = math.degrees(math.atan2(m.Y - c.Y, m.X - c.X)) % 360
                    if (am - a0) % 360 > (a1 - a0) % 360:
                        a0, a1 = a1, a0
                    out.append({"t": "arc", "cx": c.X, "cy": c.Y, "r": r, "a0": a0, "a1": a1, "kind": "section"})
            else:
                pts = [L(e.position_at(i / 32)) for i in range(33)]
                out.append(_curve_ref([(p.X, p.Y) for p in pts], "section", 1e-3 * max(1.0, e.length)))
        except Exception:
            continue
    return out


def export_step(shape, path, surfaces=None, names=None, label="part"):
    """STEP of the solid and the surface bodies that are not hidden, one labelled component each."""
    from build123d import Compound, export_step as _ex
    surfaces = surfaces or []
    if not surfaces:
        _ex(shape, path)
        return
    children = []
    if shape is not None:
        shape.label = label
        children.append(shape)
    for fid, b in surfaces:
        try:
            b.label = (names or {}).get(fid) or str(fid)
        except Exception:
            pass
        children.append(b)
    comp = Compound(children=children)
    comp.label = label
    _ex(comp, path)
