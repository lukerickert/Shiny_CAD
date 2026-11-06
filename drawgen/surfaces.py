# -*- coding: utf-8 -*-
"""Surface bodies for the Part tab (build123d / OpenCascade).

A surface feature creates a surface body (a face or a shell) kept beside the solid during the build and shown
translucent in the 3D view. Consumer features use a surface body as a tool on the solid.

Surface features (part.py build dispatches here):
  {"type": "surf_extract", "faces": [face keys], "offset": mm}             copy of faces of the solid, offset along
                                                                           the normals (0: coincident)
  {"type": "surf_fit", "faces": [face keys], "method": "analytic" | "smooth" | "original", "tolerance": mm,
   "extend": fraction, "offset": mm}                                       one clean surface fitted to the picked faces
  {"type": "surf_sketch", "plane", "offset", "sketch", "kind": "planar" | "extrude" | "revolve", "depth": mm,
   "symmetric", "angle": deg, "axis"}                                      planar face of a closed sketch; open or
                                                                           closed curves extruded or revolved
  {"type": "surf_bridge", "edges_a", "curves_a", "edges_b", "curves_b", "flip", "continuity": "ruled" | "tangent",
   "factor"}                                                               ruled surface between two chains of
                                                                           edges, ends joined corner to corner; tangent:
                                                                           G1 to the faces owning the edges
  {"type": "surf_connect", "source_a", "edges_a", "source_b", "edges_b", "tolerance"}   two surface bodies extended
                                                                           up to each other across the picked edges and sewn
  {"type": "curve_blend", "ends": [{"kind": "edge" | "curve" | "point", "ref", "body", "point", "at", "cont":
   "position" | "tangent" | "curvature", "factor"} x 2]}                  curve body between two ends
  {"type": "curve_points", "points": [point feature ids or [x, y, z]], "method": "polyline" | "spline" | "line" |
   "arc", "closed"}                                                        curve body through points
  {"type": "surf_loft", "sections": [{"plane", "offset", "sketch"}, ...], "ruled": bool, "smooth": bool (default true),
   "smooth_angle": deg (default 15)}   loft through sketch curves; with smooth the edges of a section that meet at
   less than smooth_angle are joined into one B-spline (one smooth face instead of one face per segment)
  {"type": "surf_fill", "edges": [edge keys], "curves": [curve body ids], "sketch_refs", "tangent": bool, "gap": mm
   (default 0.5: gaps between the edges up to this bridged by straight lines)}   N-sided patch over a closed loop
  {"type": "surf_fillet", "mode": "bodies" | "edges", "radius": mm, bodies: "source_a", "source_b", "flip_a",
   "flip_b", "trim": bool (default true); edges: "source", "edges": [edge keys]}   rolling-ball fillet between two
   surface bodies (trimmed and sewn into one body), or rounded edges of one surface body
  {"type": "surf_offset", "source": feature id, "distance": mm}            offset of a surface body
  {"type": "surf_sew", "sources": [feature ids], "tolerance": mm}          sewn shell of several bodies
  {"type": "curve_section", "source" | "faces", "other": surface body id | null (the solid), "with": "plane",
   "plane": XY / XZ / YZ | plane feature id, "gap": mm (chains with ends up to gap apart joined, default 0.5)}
                                                                           intersection curve of two shapes
  {"type": "surf_separate", "source": feature id, "faces": [face keys], "keep": "picked" | "rest"}   the picked faces
                                                                           of a body (or the other faces) as a body
  {"type": "surf_gaps", "source": feature id, "max_gap": mm}               splits between faces of a body closed
  {"type": "surf_clean", "source": feature id | "faces": [face keys], "clean": "analytic" | "smooth", "tolerance": mm,
   "angle": deg, "min_edge": mm, "min_face": mm^2}                         the boundary edges of each face joined
                                                                           into one edge per smooth chain; short runs
                                                                           removed (corners extended), small faces dropped
  {"type": "curve_project", "source": curve body or sketch id, "target": surface body id | null (the solid),
   "method": "normal" | "direction", "direction": [x, y, z], "keep": "nearest" | "all"}   projected curve body
  {"type": "surf_sweep", "profile": curve body or sketch id, "path": curve body or sketch id, "orient":
   "corrected" | "frenet"}                                                 profile swept along a path
  {"type": "surf_import", "path": STEP file, "label": component name | ""}  faces of a STEP file (of the component
                                                                           with that label; empty: all) as one body
Consumer features:
  {"type": "thicken", "source": id, "thickness": mm, "side": "+" | "-" | "both", "mode": "add" | "cut" | "new"}
  {"type": "surf_cut", "source": id | "with": "plane", "plane": XY / XZ / YZ | plane feature id, "keep": "+" | "-"}
                                                                           cut the solid with the surface, keep the
                                                                           side along (+) or against (-) its normal
  Partition method "surface" (source id) and Replace faces with "surface" (source id) are in part.py.
"""
import math


def _shape_list():
    try:
        from OCP.TopTools import TopTools_ListOfShape as L
    except ImportError:
        from OCP.collections import List_TopoDS_Shape as L
    return L()


def _sew(shapes, tol=1e-4):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
    from build123d import Shape
    sew = BRepBuilderAPI_Sewing(tol)
    for s in shapes:
        sew.Add(s.wrapped if hasattr(s, "wrapped") else s)
    sew.Perform()
    return Shape.cast(sew.SewedShape())


def _c1_divided(body):
    """The body with its C0 B-spline surfaces split into C1 pieces (the joined offset refuses C0 surfaces, common
    in imported STEP files)."""
    from OCP.GeomAbs import GeomAbs_C1
    from OCP.ShapeUpgrade import ShapeUpgrade_ShapeDivideContinuity
    from build123d import Shape
    dv = ShapeUpgrade_ShapeDivideContinuity(body.wrapped)
    dv.SetBoundaryCriterion(GeomAbs_C1)
    dv.SetPCurveCriterion(GeomAbs_C1)
    dv.SetSurfaceCriterion(GeomAbs_C1)
    dv.Perform()
    return Shape.cast(dv.Result())


def _offset_body(body, d, join="auto"):
    """Offset of a face or shell along its normals. join "auto": adjacent faces are extended or trimmed to meet
    at the offset (intersection join), on the body as it is, then with its C0 surfaces split into C1 pieces; then
    with arcs at the convex edges; then (up to 12 faces) face by face joined at the sharp edges; else each face is
    offset on its own (simple offset). join "intersection" | "arcs" | "faces" | "simple": that join only."""
    from OCP.BRepOffset import BRepOffset_MakeSimpleOffset, BRepOffset_Skin
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
    from OCP.GeomAbs import GeomAbs_Intersection, GeomAbs_Arc
    from build123d import Shape
    if abs(d) < 1e-12:
        return body
    if join and join != "auto":
        return _offset_body_join(body, d, join)
    nf, ns = len(body.faces()), max(1, len(body.shells()))
    reach = body.bounding_box().diagonal + 4 * abs(d) + 1.0

    def joined(sh, join):
        try:
            op = BRepOffsetAPI_MakeOffsetShape()
            op.PerformByJoin(sh.wrapped, float(d), 1e-6, BRepOffset_Skin, False, False, join)
            res = Shape.cast(op.Shape())
        except Exception:  # noqa: BLE001
            return None
        valid = res.is_valid() if callable(res.is_valid) else res.is_valid
        if not res.faces() or not valid or abs(res.area) < 1e-9 or len(res.faces()) < nf or \
                len(res.shells()) > ns or res.bounding_box().diagonal > reach:
            return None
        return res
    res = joined(body, GeomAbs_Intersection)
    if res is not None:
        res._offset_kind = "joined"
        return res
    try:
        div = _c1_divided(body)
    except Exception:  # noqa: BLE001
        div = body
    for join, kind in ((GeomAbs_Intersection, "joined"), (GeomAbs_Arc, "arcs")):
        res = joined(div, join)
        if res is not None:
            res._offset_kind = kind
            return res
    if 1 < nf <= 12:
        try:
            res = offset_joined(body, d)
            if res is not None:
                res._offset_kind = "face_joined"
                return res
        except Exception:  # noqa: BLE001
            pass
    op = BRepOffset_MakeSimpleOffset(body.wrapped, d)
    op.SetBuildSolidFlag(False)
    op.Perform()
    if not op.IsDone():
        raise ValueError("the offset failed: %s" % op.GetErrorMessage())
    res = Shape.cast(op.GetResultShape())
    res._offset_kind = "simple"
    return res


def _offset_body_join(body, d, join):
    """Offset with one join only (see _offset_body)."""
    from OCP.BRepOffset import BRepOffset_MakeSimpleOffset, BRepOffset_Skin
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
    from OCP.GeomAbs import GeomAbs_Intersection, GeomAbs_Arc
    from build123d import Shape
    if join == "simple":
        op = BRepOffset_MakeSimpleOffset(body.wrapped, d)
        op.SetBuildSolidFlag(False)
        op.Perform()
        if not op.IsDone():
            raise ValueError("the offset failed: %s" % op.GetErrorMessage())
        res = Shape.cast(op.GetResultShape())
        res._offset_kind = "simple"
        return res
    if join == "faces":
        res = offset_joined(body, d)
        if res is None:
            raise ValueError("the face by face offset failed (try Arcs or Automatic)")
        res._offset_kind = "face_joined"
        return res
    jt = GeomAbs_Arc if join == "arcs" else GeomAbs_Intersection
    last = None
    for sh in (body, _c1_divided(body)):
        try:
            op = BRepOffsetAPI_MakeOffsetShape()
            op.PerformByJoin(sh.wrapped, float(d), 1e-6, BRepOffset_Skin, False, False, jt)
            res = Shape.cast(op.Shape())
            valid = res.is_valid() if callable(res.is_valid) else res.is_valid
            if res.faces() and valid:
                res._offset_kind = "arcs" if join == "arcs" else "joined"
                return res
            last = "the result is not a valid body"
        except Exception as e:  # noqa: BLE001
            last = str(e).strip() or "failed"
    raise ValueError("the %s offset failed: %s (try another join)" % (join, last))


def source_body(shape, bodies, f, find_faces):
    """The surface a feature works on: the picked faces of the solid ("faces", sewn into one body) when any,
    else the surface body "source"."""
    if f.get("faces"):
        faces = find_faces(shape, f.get("faces") or [])
        if not faces:
            raise ValueError("the picked faces were not found")
        return _sew(faces) if len(faces) > 1 else faces[0]
    src = bodies.get(f.get("source"))
    if src is None:
        raise ValueError("source surface not found: click a surface body or faces of the solid")
    return src


def extract(shape, f, find_faces):
    faces = find_faces(shape, f.get("faces") or [])
    if not faces:
        raise ValueError("no faces picked")
    body = _sew(faces) if len(faces) > 1 else faces[0]
    return _offset_body(body, float(f.get("offset") or 0))


def fit(shape, f, find_faces, clean_surface, extended_fit):
    """One face on a clean surface fitted to the largest picked face, extended beyond it."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Precision import Precision
    from OCP.gp import gp_Vec
    from build123d import Shape
    faces = find_faces(shape, f.get("faces") or [])
    if not faces:
        raise ValueError("no faces picked")
    main = max(faces, key=lambda fc: fc.area)
    tol = float(f.get("tolerance") or 0.05)
    method = f.get("method") or "analytic"
    surf, kind = clean_surface(main, method, tol)
    ext = float(f.get("extend") if f.get("extend") is not None else 0.3)
    u1, u2, v1, v2 = surf.Bounds()
    inf = Precision.Infinite_s() / 2
    if any(abs(b) > inf for b in (u1, u2, v1, v2)):
        # analytic, unbounded: a patch around the face, 1 + 2 * ext times its extent
        bb = main.bounding_box()
        size = bb.diagonal * (1.0 + 2.0 * ext)
        from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
        from OCP.gp import gp_Pnt
        c = main.center()
        pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(c.X, c.Y, c.Z), surf)
        u0, v0 = pr.LowerDistanceParameters()
        # cylinders, cones, tori: u is the angle
        name = surf.DynamicType().Name()
        if name in ("Geom_CylindricalSurface", "Geom_ConicalSurface"):
            u1, u2, v1, v2 = 0.0, 2 * math.pi, v0 - size / 2, v0 + size / 2
        elif name in ("Geom_SphericalSurface", "Geom_ToroidalSurface"):
            u1, u2, v1, v2 = 0.0, 2 * math.pi, 0.0, 2 * math.pi
        else:
            u1, u2, v1, v2 = u0 - size / 2, u0 + size / 2, v0 - size / 2, v0 + size / 2
    elif method != "original" and ext != 0.3:
        surf = extended_fit(__import__("OCP.BRep", fromlist=["BRep_Tool"]).BRep_Tool.Surface_s(main.wrapped), tol, ext_frac=ext)
        u1, u2, v1, v2 = surf.Bounds()
    off = float(f.get("offset") or 0)
    if abs(off) > 1e-12:
        if surf.DynamicType().Name() == "Geom_Plane":
            c = main.center()
            n = main.normal_at(c)
            surf = surf.Translated(gp_Vec(n.X * off, n.Y * off, n.Z * off))
        else:
            from OCP.Geom import Geom_OffsetSurface
            surf = Geom_OffsetSurface(surf, off)
    face = Shape.cast(BRepBuilderAPI_MakeFace(surf, u1, u2, v1, v2, 1e-6).Face())
    face._kind = kind
    return face


def from_sketch(f, plane_of, segments, profile_faces):
    """Planar face, or the sketch curves extruded / revolved as a surface."""
    from .part import seg_edge
    from build123d import Edge, Wire, Vector, Shape, Plane, Compound
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
    from OCP.gp import gp_Vec, gp_Ax1, gp_Pnt, gp_Dir
    plane = plane_of(f)
    kind = f.get("kind") or "planar"
    sk = f.get("sketch") or {}
    if kind == "planar":
        faces = profile_faces(sk, plane)
        return faces[0] if len(faces) == 1 else Compound(children=faces)
    segs, circles = segments(sk)
    W = lambda q: plane.from_local_coords(Vector(q[0], q[1], 0))
    edges = [seg_edge(k, a, b, mm, W) for k, a, b, mm in segs]
    for cx, cy, r in circles:
        edges.append(Edge.make_circle(r, Plane(origin=W((cx, cy)), x_dir=plane.x_dir, z_dir=plane.z_dir)))
    if not edges:
        raise ValueError("the sketch has no lines, arcs or circles")
    try:
        wires = Wire.combine(edges)
    except Exception:
        wires = [Wire([e]) for e in edges]
    out = []
    n = Vector(plane.z_dir)
    if kind == "extrude":
        d = float(f.get("depth") or 10)
        start = -n * (d / 2.0) if f.get("symmetric") else Vector(0, 0, 0)
        vec = gp_Vec(n.X * d, n.Y * d, n.Z * d)
        for w in wires:
            from build123d import Location
            base = w.moved(Location(start)) if f.get("symmetric") else w
            out.append(Shape.cast(BRepPrimAPI_MakePrism(base.wrapped, vec).Shape()))
    elif kind == "revolve":
        ang = math.radians(float(f.get("angle") or 360))
        ax = f.get("axis") or "v"
        if ax == "u":
            o, d = plane.origin, plane.x_dir
        elif ax == "v":
            o, d = plane.origin, plane.y_dir
        else:
            line = next((e for e in sk.get("entities") or [] if e.get("id") == ax), None)
            if line is None:
                raise ValueError("axis line %s not found" % ax)
            p1, p2 = W((line["x1"], line["y1"])), W((line["x2"], line["y2"]))
            o, d = p1, (p2 - p1).normalized()
        axis = gp_Ax1(gp_Pnt(o.X, o.Y, o.Z), gp_Dir(d.X, d.Y, d.Z))
        for w in wires:
            out.append(Shape.cast(BRepPrimAPI_MakeRevol(w.wrapped, axis, ang).Shape()))
    else:
        raise ValueError("unknown surface kind %s" % kind)
    return out[0] if len(out) == 1 else _sew(out)


def loft(f, plane_of, segments):
    """Loft through the curves of several sketches (one open or closed chain per sketch)."""
    from .part import seg_edge
    from build123d import Edge, Wire, Vector, Shape, Plane
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    secs = f.get("sections") or []
    if len(secs) < 2:
        raise ValueError("a loft needs at least two sections")
    op = BRepOffsetAPI_ThruSections(False, bool(f.get("ruled")), 1e-6)
    for sec in secs:
        plane = plane_of(sec)
        segs, circles = segments(sec.get("sketch") or {}, smooth=bool(f.get("smooth", True)))
        W = lambda q: plane.from_local_coords(Vector(q[0], q[1], 0))
        edges = [seg_edge(k, a, b, mm, W) for k, a, b, mm in segs]
        for cx, cy, r in circles:
            edges.append(Edge.make_circle(r, Plane(origin=W((cx, cy)), x_dir=plane.x_dir, z_dir=plane.z_dir)))
        if not edges:
            raise ValueError("a section sketch has no curves")
        try:
            wires = Wire.combine(edges)
        except Exception:
            wires = [Wire(edges)]
        if len(wires) != 1:
            raise ValueError("each section must be one chain of curves")
        w = smooth_wire(wires[0], float(f.get("smooth_angle", 15) or 15)) if f.get("smooth", True) else wires[0]
        op.AddWire(w.wrapped)
    op.Build()
    if not op.IsDone():
        raise ValueError("the loft failed (sections with different curve counts or orientation)")
    return Shape.cast(op.Shape())


def sketch_edges(f, plane_of, segments):
    """Edges (3D) of the lines, arcs, ellipses and circles of a sketch feature."""
    from .part import seg_edge
    from build123d import Edge, Vector, Plane
    plane = plane_of(f)
    segs, circles = segments(f.get("sketch") or {})
    W = lambda q: plane.from_local_coords(Vector(q[0], q[1], 0))
    edges = [seg_edge(k, a, b, mm, W) for k, a, b, mm in segs]
    for cx, cy, r in circles:
        edges.append(Edge.make_circle(r, Plane(origin=W((cx, cy)), x_dir=plane.x_dir, z_dir=plane.z_dir)))
    return edges


def _ref_edges(shape, refs, find_edges, bodies):
    """Edges of the solid matching the references, then of the surface and curve bodies for the rest."""
    edges = []
    if shape is not None and refs:
        edges += find_edges(shape, refs)
    if len(edges) < len(refs):
        for body in (bodies or {}).values():
            if body is None or not body.edges():
                continue
            for e in find_edges(body, refs):
                if not any(e.wrapped.IsSame(x.wrapped) for x in edges):
                    edges.append(e)
    return edges


def bridge(shape, f, find_edges, bodies=None):
    """Ruled surface between two chains of edges (side A: "edges_a" edge references and "curves_a" curve bodies;
    side B likewise): straight lines join the ends of A to the nearer ends of B (corner to corner) and the
    corresponding points between ("flip" joins the other ends). "continuity": "tangent": the surface leaves each
    side tangent to the face owning that side's edges (bridge_tangent), "factor" the tangent length."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from build123d import Shape

    def side(k):
        edges = _ref_edges(shape, f.get("edges_" + k) or [], find_edges, bodies)
        for cid in f.get("curves_" + k) or []:
            body = (bodies or {}).get(cid)
            if body is not None:
                edges += list(body.edges())
        if not edges:
            raise ValueError("pick the edges of side %s" % k.upper())
        wires = _chain_wires(edges)
        if len(wires) != 1:
            raise ValueError("the edges of side %s are not one connected chain (%d chains)" % (k.upper(), len(wires)))
        return wires[0]
    wa, wb = side("a"), side("b")
    a0, a1 = wa.position_at(0), wa.position_at(1)
    b0, b1 = wb.position_at(0), wb.position_at(1)
    rev = ((a0 - b0).length + (a1 - b1).length) > ((a0 - b1).length + (a1 - b0).length)
    if f.get("flip"):
        rev = not rev
    if (f.get("continuity") or "ruled") == "tangent":
        return bridge_tangent(shape, bodies, wa, wb, rev, float(f.get("factor") or 1.0))
    op = BRepOffsetAPI_ThruSections(False, True, 1e-6)
    op.CheckCompatibility(False)                    # the orientation set here (corner to corner, or Flip) is kept
    op.AddWire(wa.wrapped)
    if rev:
        from OCP.TopoDS import TopoDS
        rw = wb.wrapped.Reversed()
        cast = getattr(TopoDS, "Wire_s", None) or getattr(TopoDS, "Wire")        # name differs between OCP builds
        op.AddWire(cast(rw))
    else:
        op.AddWire(wb.wrapped)
    op.Build()
    if not op.IsDone():
        raise ValueError("the bridge surface failed (sides of different edge counts can need Flip, or curve bodies)")
    return Shape.cast(op.Shape())


def fill(shape, f, find_edges, bodies=None, sketches=None):
    """N-sided patch over a closed loop: edges of the solid, edges of surface bodies, curve bodies and the curves
    of sketches (sketch_refs), tangent to the adjacent faces of the solid when requested."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeFilling
    from OCP.GeomAbs import GeomAbs_C0, GeomAbs_G1
    from build123d import Shape
    refs = f.get("edges") or []
    edges = []
    if shape is not None and refs:
        edges += find_edges(shape, refs)
    # references not found on the solid: edges of the surface bodies
    if len(edges) < len(refs):
        found = set(id(e.wrapped) for e in edges)
        for body in (bodies or {}).values():
            if body is None or not body.edges():
                continue
            for e in find_edges(body, refs):
                if id(e.wrapped) not in found and not any(e.wrapped.IsSame(x.wrapped) for x in edges):
                    edges.append(e)
    for cid in f.get("curves") or []:
        body = (bodies or {}).get(cid)
        if body is not None:
            edges += list(body.edges())
    for sk in sketches or []:
        edges += sk
    if not edges:
        raise ValueError("pick the boundary: edges of the solid or of surface bodies, curve bodies or sketch curves forming a closed loop")
    # the same edge found on several bodies (a body and the one made from it) counted once
    uniq = []
    for e in edges:
        m, ln = e.position_at(0.5), e.length
        if not any((m - x.position_at(0.5)).length < 1e-4 and abs(ln - x.length) < 1e-4 for x in uniq):
            uniq.append(e)
    edges = uniq
    # the loop: the edges chained, gaps up to "gap" (mm, default 0.5) bridged by straight lines
    gap = float(f.get("gap") if f.get("gap") is not None else 0.5)
    wires = _chain_wires(edges)
    bridged = 0
    if (len(wires) != 1 or not wires[0].is_closed) and gap > 0:
        wires, bridged = _join_gaps(wires, gap, close_factor=0.0)
    if len(wires) == 1 and not wires[0].is_closed:
        wires = [_closed_wire(wires[0], max(gap, 1e-3))]
    # a chain whose ends meet within 1e-3 mm is a loop for the filling even when its end vertices are separate
    closed = len(wires) == 1 and (wires[0].is_closed or (wires[0].position_at(0) - wires[0].position_at(1)).length <= max(gap, 1e-3))
    if not closed:
        if len(wires) == 1:
            w = wires[0]
            d = (w.position_at(0) - w.position_at(1)).length
            raise ValueError("the fill failed: the loop is open by %.3f mm (raise the gap to close it)" % d)
        ends = [q for w in wires if not w.is_closed for q in (w.position_at(0), w.position_at(1))]
        dmin = min(((a - b).length for i, a in enumerate(ends) for b in ends[i + 1:]), default=0.0)
        raise ValueError("the fill failed: the edges form %d separate chain(s) (nearest ends %.3f mm apart)" % (len(wires), dmin))
    if bridged:
        f["_note"] = "%d gap(s) bridged by straight lines" % bridged
    loop = list(wires[0].edges())
    op = BRepOffsetAPI_MakeFilling()
    tangent = bool(f.get("tangent", True))
    for e in loop:
        owner = None
        if tangent and shape is not None:
            owner = next((fc for fc in shape.faces() if any(e.wrapped.IsSame(x.wrapped) for x in fc.edges())), None)
        try:
            if owner is not None:
                op.Add(e.wrapped, owner.wrapped, GeomAbs_G1, True)
            else:
                op.Add(e.wrapped, GeomAbs_C0, True)
        except Exception:
            op.Add(e.wrapped, GeomAbs_C0, True)
    try:
        op.Build()
        ok = op.IsDone()
    except Exception:
        ok = False
    if ok:
        res = Shape.cast(op.Shape())
        if res.faces() and res.area > 1e-9:
            return res
    # planar loops (a sketch circle, a planar wire): a plain face
    try:
        from build123d import Face
        fc = Face(wires[0])
        if fc.area > 1e-9:
            return fc
    except Exception:
        pass
    raise ValueError("the fill failed (the loop is closed but no surface could be built over it)")


def offset(shape, bodies, f, find_faces):
    """Offset surface: "join" (default "auto") chooses how the offset faces meet at the edges, see _offset_body."""
    src = source_body(shape, bodies, f, find_faces)
    res = _offset_body(src, float(f.get("distance") or 0), f.get("join") or "auto")
    kind = getattr(res, "_offset_kind", "")
    if kind == "simple":
        res._kind = "faces offset one by one (the joins could not be computed)"
    elif kind == "arcs":
        res._kind = "joined with arcs at the convex edges"
    elif kind == "face_joined":
        res._kind = "faces offset one by one, extended and cut at the sharp edges"
    return res


_STEP_CACHE = {}    # (path, mtime, size) -> imported compound


def import_step(f):
    """Surface body of a STEP file: the faces of the component labelled f["label"] (all faces when empty). A
    component that is one shell is returned as that shell; otherwise its faces are sewn."""
    import os
    from build123d import import_step as _imp
    path = (f.get("path") or "").strip().strip('"')
    if not path or not os.path.isfile(path):
        raise ValueError("STEP file not found: %s" % (path or "(no path)"))
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime, st.st_size)
    comp = _STEP_CACHE.get(key)
    if comp is None:
        comp = _imp(path)
        _STEP_CACHE.clear()
        _STEP_CACHE[key] = comp
    label = (f.get("label") or "").strip()
    picked = []

    def walk(o):
        if getattr(o, "label", "") == label:
            picked.append(o)
            return
        for ch in list(getattr(o, "children", None) or []):
            walk(ch)
    if label:
        walk(comp)
        if not picked:
            raise ValueError("no component %s in %s" % (label, os.path.basename(path)))
    else:
        picked = [comp]
    faces = [fc for o in picked for fc in o.faces()]
    if not faces:
        raise ValueError("no faces in %s" % (label or os.path.basename(path)))
    shells = [sh for o in picked for sh in o.shells()]
    if len(shells) == 1 and len(shells[0].faces()) == len(faces):
        return shells[0]
    return _sew(faces) if len(faces) > 1 else faces[0]


def sew(bodies, f):
    srcs = [bodies.get(i) for i in (f.get("sources") or [])]
    srcs = [s for s in srcs if s is not None]
    if not srcs:
        raise ValueError("no source surfaces")
    return _sew(srcs, float(f.get("tolerance") or 1e-3))


def thicken(shape, bodies, f, fuse, find_faces):
    """Solid from a surface body: thickness along the normal (+), against it (-) or both (half each side)."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
    from OCP.BRepOffset import BRepOffset_MakeSimpleOffset
    from build123d import Shape
    src = source_body(shape, bodies, f, find_faces)
    t = float(f.get("thickness") or 1)
    side = f.get("side") or "+"
    body = src
    if side == "both":
        body = _offset_body(src, -t / 2.0)
    d = t if side != "-" else -t
    if side == "-":
        d = -t
    # a prismatic surface (faces parallel to one direction between two planes, an extruded profile): the profile
    # offset in its plane, with the corners intersected and the rounds smaller than the thickness dropped
    solid = _prism_thick(src, t, side)
    # offset with the joins of the offset faces intersected (clean inside corners); the simple offset, which keeps
    # the offset faces untrimmed, when it fails
    if solid is None:
        solid = _join_thick(body, d)
    if solid is None:
        try:
            op = BRepOffset_MakeSimpleOffset(body.wrapped, d)
            op.SetBuildSolidFlag(True)
            op.Perform()
            if op.IsDone():
                solid = Shape.cast(op.GetResultShape())
        except Exception:
            solid = None
        if solid is not None and solid.solids():
            f["_note"] = "simple offset (the offset faces are not trimmed where they meet: inside corners can show folded faces)"
    if solid is None or not solid.solids():
        try:
            mk = BRepOffsetAPI_MakeThickSolid()
            mk.MakeThickSolidBySimple(body.wrapped, d)
            solid = Shape.cast(mk.Shape())
        except Exception:
            solid = None
    if solid is None or not solid.solids():
        # the shell as a whole does not offset (a degenerate or self-intersecting face): each shell, then each face
        # thickened alone and the pieces fused (at the seams the result is the union of the face solids)
        solid, note = _thicken_pieces(body, d)
        f["_note"] = note
    if solid.volume < 0:
        solid = Shape.cast(solid.wrapped.Reversed())
    mode = f.get("mode") or "add"
    if mode == "new" or shape is None:
        return solid if shape is None else __import__("build123d").Compound(children=list(shape.solids()) + list(solid.solids()))
    if mode == "cut":
        return shape.cut(solid).clean()
    return fuse(shape, solid)


def _fuzzy_fuse(shapes, fuzzy=1e-5):
    """Fusion of the shapes (faces in one plane, or solids) with a fuzzy tolerance (mm): regions that meet along
    nearly the same segment are joined."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from build123d import Shape
    if len(shapes) == 1:
        return shapes[0]
    args, tools = _shape_list(), _shape_list()
    args.Append(shapes[0].wrapped)
    for x in shapes[1:]:
        tools.Append(x.wrapped)
    op = BRepAlgoAPI_Fuse()
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetFuzzyValue(fuzzy)
    op.SetRunParallel(True)
    op.SetUseOBB(True)
    op.Build()
    if not op.IsDone():
        out = shapes[0]
        for x in shapes[1:]:
            out = out.fuse(x)
        return out
    return Shape.cast(op.Shape())


def _band_slabs(w, faces, D, sg, dist, tol, corners=True, raw=False, info=None):
    """Faces of the band between the planar wire w and its offset by dist to the side of the face normals (sg = +1)
    or against them (-1): for each edge the region between the edge and the edge moved along its normal (an arc
    with its centre on that side and a radius up to dist: the sector to its centre), at each corner where the
    offsets part the mitre to the intersection of the offset tangents (a round when the mitre is longer than
    4 x dist); the regions are fused. None when a region cannot be made."""
    from OCP.GeomAPI import GeomAPI_PointsToBSpline
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Pnt
    from build123d import Vector, Edge, Wire, Face
    try:
        from OCP.TColgp import TColgp_Array1OfPnt as Arr1
    except ImportError:
        from OCP.collections import Array1_gp_Pnt as Arr1
    try:
        ordered = list(w.order_edges()) if len(w.edges()) > 1 else list(w.edges())
        n_e = len(ordered)
        # direction of each edge along the wire (position_at follows the curve, not the wire)
        rev = [False] * n_e
        if n_e > 1:
            a0, a1 = ordered[0].position_at(0), ordered[0].position_at(1)
            b0, b1 = ordered[1].position_at(0), ordered[1].position_at(1)
            rev[0] = min((a0 - b0).length, (a0 - b1).length) < min((a1 - b0).length, (a1 - b1).length)
            for k in range(1, n_e):
                prev_end = ordered[k - 1].position_at(0 if rev[k - 1] else 1)
                c0, c1 = ordered[k].position_at(0), ordered[k].position_at(1)
                rev[k] = (c1 - prev_end).length < (c0 - prev_end).length
        pos = lambda k, u: ordered[k].position_at(1 - u if rev[k] else u)
        tan = lambda k, u: ordered[k].tangent_at(1 - u if rev[k] else u) * (-1.0 if rev[k] else 1.0)
        owner = []
        for e in ordered:
            m = e.position_at(0.5)
            fc = next((f for f in faces if any(e.wrapped.IsSame(x.wrapped) for x in f.edges())), None)
            if fc is None:
                fc = min(faces, key=lambda f: min((x.position_at(0.5) - m).length for x in f.edges()))
            owner.append(fc)
        # the normal of each edge from the wire direction (D x tangent, consistent along the wire); its side from the
        # face normals of the edges, weighted by length (a face of the shell with a reversed normal does not count)
        vote = 0.0
        for k, e in enumerate(ordered):
            try:
                vote += e.length * D.cross(tan(k, 0.5)).dot(owner[k].normal_at(pos(k, 0.5)))
            except Exception:
                pass
        side_k = sg * (1.0 if vote >= 0 else -1.0)
        nrm0 = lambda k, u: (D.cross(tan(k, u)) * side_k).normalized()
        # at a joint where the two edges meet nearly tangent (within 2 deg) both regions end on the mean normal, so
        # that they share the end segment and fuse into one region
        over = {}
        jp = [(k, k + 1) for k in range(n_e - 1)] + ([(n_e - 1, 0)] if w.is_closed and n_e > 1 else [])
        for a_k, b_k in jp:
            if (pos(a_k, 1.0) - pos(b_k, 0.0)).length > 1e-4:
                continue
            na_, nb_ = nrm0(a_k, 1.0), nrm0(b_k, 0.0)
            if na_.dot(nb_) > math.cos(math.radians(2.0)):
                m_ = (na_ + nb_).normalized()
                over[(a_k, 1.0)] = m_
                over[(b_k, 0.0)] = m_

        def nrm(k, u):
            if u in (0.0, 1.0) and (k, u) in over:
                return over[(k, u)]
            return nrm0(k, u)

        def bspl(pts):
            a = Arr1(1, len(pts))
            for j, q in enumerate(pts):
                a.SetValue(j + 1, gp_Pnt(q.X, q.Y, q.Z))
            return Edge(BRepBuilderAPI_MakeEdge(GeomAPI_PointsToBSpline(a, 3, 8, GeomAbs_C2, 1e-6).Curve()).Edge())

        def face_of(first, pts):
            """Face bounded by the edge first (or None) and the polygon pts (closing back to the start of first);
            segments shorter than 1e-9 mm are left out. None when no face can be made."""
            try:
                es = [first] if first is not None else []
                q = pts
                for x, y in zip(q[:-1], q[1:]):
                    if (y - x).length > 1e-7:
                        es.append(Edge.make_line(x, y))
                return Face(Wire(es))
            except Exception:
                return None

        def add(fc):
            # every region with its normal along D, so that the fusion merges them
            if fc is not None:
                try:
                    # degenerate regions (a crossing exactly at the offset) are left out: they break the fusion
                    if fc.area < 1e-9:
                        return
                    if fc.normal_at(fc.center()).dot(D) < 0:
                        fc = Face(fc.wrapped.Reversed())
                except Exception:
                    pass
                regions.append(fc)
                if cur[0] is not None and edge_reg[cur[0]] is None:
                    edge_reg[cur[0]] = fc

        regions = []
        ends = []
        edge_reg = [None] * n_e
        cur = [None]
        for k, e in enumerate(ordered):
            cur[0] = k
            p0, p1 = pos(k, 0.0), pos(k, 1.0)
            n0, n1 = nrm(k, 0.0), nrm(k, 1.0)
            ends.append((p0, p1, n0, n1, tan(k, 0.0), tan(k, 1.0)))
            g = e.geom_type.name
            if g == "LINE":
                q0, q1 = p0 + n0 * dist, p1 + n1 * dist
                add(face_of(e, [p1, q1, q0, p0]))
                continue
            if g == "CIRCLE":
                c = e.arc_center
                if (c - pos(k, 0.5)).dot(nrm(k, 0.5)) > 0 and e.radius <= dist + 1e-9:
                    # concave arc smaller than the offset: the sector to its centre
                    add(face_of(e, [p1, c, p0]))
                    continue
            if g == "CIRCLE":
                # concentric arc
                qs = [pos(k, u) + nrm(k, u) * dist for u in (0.0, 0.5, 1.0)]
                off = Edge.make_three_point_arc(qs[0], qs[1], qs[2])
                add(Face(Wire([e, Edge.make_line(p1, qs[-1]), off, Edge.make_line(qs[0], p0)])))
                continue
            n_s = max(12, min(96, int(e.length / max(dist, 1e-6) * 6) + 12))
            us = [j / n_s for j in range(n_s + 1)]
            P_ = [pos(k, u) for u in us]
            N_ = [nrm(k, u) for u in us]

            def cross_at(j):
                # parameter along the normals where the normals at samples j and j + 1 meet (None: they part)
                a_, b_ = P_[j], P_[j + 1]
                den = N_[j].cross(N_[j + 1]).dot(D)
                if abs(den) < 1e-14:
                    return None
                s_ = (b_ - a_).cross(N_[j + 1]).dot(D) / den
                t_ = (b_ - a_).cross(N_[j]).dot(D) / den
                return s_ if s_ > 0 and t_ > 0 else None
            folds = [cross_at(j) for j in range(n_s)]
            if not any(x is not None and x < dist * 1.02 for x in folds):
                qs = [p + n * dist for p, n in zip(P_, N_)]
                off = bspl(qs)
                add(Face(Wire([e, Edge.make_line(p1, qs[-1]), off, Edge.make_line(qs[0], p0)])))
                continue
            # the curve turns tighter than the offset on that side (a small round of a B-spline): one region bounded
            # by the curve and the points along its normals at the offset, or nearer where neighbouring normals meet
            # (the swept region beyond the meeting points is covered by the neighbouring edges)
            rr = [dist] * (n_s + 1)
            for j in range(n_s):
                fj = folds[j]
                if fj is not None and fj < dist:
                    rr[j] = min(rr[j], fj)
                    rr[j + 1] = min(rr[j + 1], fj)
            gs = [P_[j] + N_[j] * rr[j] for j in range(n_s + 1)]
            pts = [p1]
            for q in gs[::-1] + [p0]:
                if (q - pts[-1]).length > 1e-5 or q is p0:
                    pts.append(q)
            # the offset side as smooth curves through the points, split where the points turn sharply (where the
            # region narrows to the meeting point of the normals); single segments as lines
            inner = pts[1:-1]
            runs, cur_run = [], [inner[0]] if inner else []
            for j in range(1, len(inner)):
                cur_run.append(inner[j])
                if 0 < j < len(inner) - 1:
                    d1 = (inner[j] - inner[j - 1]).normalized()
                    d2 = (inner[j + 1] - inner[j]).normalized()
                    if d1.dot(d2) < math.cos(math.radians(30)):
                        runs.append(cur_run)
                        cur_run = [inner[j]]
            if cur_run:
                runs.append(cur_run)
            es = [e, Edge.make_line(p1, inner[0])] if inner and (inner[0] - p1).length > 1e-7 else [e]
            try:
                for r_ in runs:
                    if len(r_) >= 3:
                        es.append(bspl(r_))
                    elif len(r_) == 2 and (r_[1] - r_[0]).length > 1e-7:
                        es.append(Edge.make_line(r_[0], r_[1]))
                if inner and (p0 - inner[-1]).length > 1e-7:
                    es.append(Edge.make_line(inner[-1], p0))
                add(Face(Wire(es)))
            except Exception:
                add(face_of(e, pts))
        cur[0] = None
        if info is not None:
            info["edges"] = edge_reg
            info["convex"] = []
        if raw:
            if info is not None:
                for a, b in [(k, k + 1) for k in range(n_e - 1)] + ([(n_e - 1, 0)] if w.is_closed and n_e > 1 else []):
                    v, na, ta = ends[a][1], ends[a][3], ends[a][5]
                    v2, nb = ends[b][0], ends[b][2]
                    if (v - v2).length <= 1e-4 and na.dot(nb) <= 1 - 1e-9 and nb.dot(ta) > 1e-9:
                        info["convex"].append((a, b))
            return regions
        # corners
        pairs = [(k, k + 1) for k in range(n_e - 1)] + ([(n_e - 1, 0)] if w.is_closed and n_e > 1 else []) if corners else []
        for a, b in pairs:
            _, v, _, na, ta, _ = ends[a][0], ends[a][1], ends[a][2], ends[a][3], ends[a][5], None
            v2, nb, tb = ends[b][0], ends[b][2], ends[b][4]
            if (v - v2).length > 1e-4 or na.dot(nb) > 1 - 1e-9:
                continue
            if nb.dot(ta) <= 1e-9:
                continue                        # the offsets overlap (corner towards the offset side)
            A, B = v + na * dist, v + nb * dist
            den = ta.cross(tb).dot(D)
            M = None
            if abs(den) > 1e-12:
                s_ = (B - A).cross(tb).dot(D) / den
                M = A + ta * s_
            if M is None or (M - v).length > 4 * dist:
                mid = (na + nb).normalized()
                add(Face(Wire([Edge.make_line(v, A), Edge.make_three_point_arc(A, v + mid * dist, B), Edge.make_line(B, v)])))
            else:
                add(face_of(None, [v, A, M, B, v]))
        if not regions:
            return None
        fused = _fuzzy_fuse(regions)
        try:
            fused = fused.clean()
        except Exception:
            pass
        out = list(fused.faces())
        if not out or abs(sum(f.area for f in out)) < 1e-12:
            return None
        return out
    except Exception:
        return None


def _prism_thick(body, t, side):
    """Solid of a prismatic shell or face thickened by t (side "+" along the face normals, "-" against them, "both"
    half each side): every face is parallel to one direction D and spans the same height between two planes normal
    to D. The boundary of the faces in the lower plane is offset in that plane (BRepOffsetAPI_MakeOffset,
    intersection join: arcs whose radius is smaller than the offset vanish into a sharp corner), the band between
    the boundary and its offset is extruded along D. None when the body is not prismatic or the offset fails."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
    from OCP.GeomAbs import GeomAbs_Intersection, GeomAbs_Arc
    from build123d import Shape, Vector, Wire, Face, Solid, Kind, Side
    try:
        faces = list(body.faces())
        if not faces:
            return None
        normals = []
        for fc in faces:
            for a in (0.1, 0.5, 0.9):
                for b in (0.1, 0.5, 0.9):
                    normals.append(fc.normal_at(fc.position_at(a, b)))
        D = None
        for n in normals[1:]:
            c = normals[0].cross(n)
            if c.length > 1e-3:
                D = c.normalized()
                break
        if D is None or any(abs(n.dot(D)) > 1e-5 for n in normals):
            return None
        hs = [Vector(v).dot(D) for v in body.vertices()]
        h0, h1 = min(hs), max(hs)
        tol = 1e-6 * max(1.0, body.bounding_box().diagonal)
        if h1 - h0 < 10 * tol or any(min(abs(h - h0), abs(h - h1)) > tol for h in hs):
            return None
        low = lambda p: abs(Vector(p).dot(D) - h0) < tol
        bottom = [e for e in body.edges() if low(e.position_at(0)) and low(e.position_at(0.5)) and low(e.position_at(1))]
        if not bottom:
            return None
        signs = {"+": [1.0], "-": [-1.0], "both": [1.0, -1.0]}[side]
        cutters = []
        dist = t if side != "both" else t / 2.0
        pieces = []
        for w in Wire.combine(bottom):
            # a point on the thickened side of the first edge of the wire, for each sign
            e0 = w.edges()[0]
            m = e0.position_at(0.5)
            fc0 = next(fc for fc in faces if any(e0.wrapped.IsSame(x.wrapped) for x in fc.edges()) or
                       any(abs((x.position_at(0.5) - m).length) < tol for x in fc.edges()))
            n0 = fc0.normal_at(m)
            for sg in signs:
                tp = m + n0 * (sg * dist / 2.0)
                # the union of the regions swept by the normals of each edge (and the mitre at convex corners)
                band = _band_slabs(w, faces, D, sg, dist, tol)
                if band and not any(x.is_inside(tp) for x in band):
                    band = None
                if band:
                    pass
                elif w.is_closed:
                    fw = Face(w)
                    for jt in (GeomAbs_Intersection, GeomAbs_Arc):
                        for k in (1.0, -1.0):
                            mo = BRepOffsetAPI_MakeOffset(fw.wrapped, jt)
                            mo.Perform(k * dist)
                            if not mo.IsDone():
                                continue
                            ws = [x for x in Shape.cast(mo.Shape()).wires() if x.is_closed]
                            if not ws:
                                continue
                            fo = Face(max(ws, key=lambda x: x.length))
                            b = (fo - fw) if fo.area > fw.area else (fw - fo)
                            bf = [x for x in b.faces()] if hasattr(b, "faces") else [b]
                            if any(x.is_inside(tp) for x in bf):
                                band = bf
                                break
                        if band:
                            break
                if not band:
                    return None
                hgt = D * (h1 - h0)
                if w.is_closed:
                    # a closed loop: the band is clipped by the face of the loop (kept inside or outside of it, the
                    # side of the thickening), which removes the regions that reach across the surface exactly
                    try:
                        lf = Face(w)
                        L = Solid.extrude(lf, hgt)
                        B = _fuzzy_fuse([Solid.extrude(x, hgt) for x in band])
                        inside = lf.is_inside(tp)
                        clipped = B.intersect(L) if inside else B.cut(L)
                        cs = list(clipped.solids()) if hasattr(clipped, "solids") else []
                        if cs and sum(x.volume for x in cs) > 0.5 * B.volume:
                            pieces += cs
                            continue
                    except Exception:
                        pass
                pieces += [Solid.extrude(x, hgt) for x in band]
                # the regions swept by the edge normals to the other side are cut away afterwards: at a corner the
                # region of one edge can reach across the next edge, to the other side of the surface
                # at a corner where the offsets part on the thickened side, the region of an edge on the other side
                # reaches across the next edge instead: there the next edge's region is taken out of the cutter
                ib, ia = {}, {}
                _band_slabs(w, faces, D, sg, dist, tol, raw=True, info=ib)
                _band_slabs(w, faces, D, -sg, dist, tol, raw=True, info=ia)
                eb, ea = ib.get("edges") or [], ia.get("edges") or []
                nbr = {}
                for a_, b_ in ib.get("convex") or []:
                    nbr.setdefault(a_, []).append(b_)
                    nbr.setdefault(b_, []).append(a_)
                hgt = D * (h1 - h0)
                for k_, fa in enumerate(ea):
                    if fa is None:
                        continue
                    ck = Solid.extrude(fa, hgt)
                    for j_ in nbr.get(k_, []):
                        if j_ < len(eb) and eb[j_] is not None:
                            try:
                                ck2 = ck.cut(Solid.extrude(eb[j_], hgt))
                                ck = ck2.solids()[0] if len(ck2.solids()) == 1 else (ck2 if ck2.solids() else ck)
                            except Exception:
                                pass
                    for x in (ck.solids() if hasattr(ck, "solids") else [ck]):
                        cutters.append(x)
        solid = _fuzzy_fuse(pieces)
        if cutters and side != "both":
            try:
                cut = solid.cut(cutters[0].fuse(*cutters[1:]) if len(cutters) > 1 else cutters[0])
                if cut.solids() and cut.volume > 0.5 * solid.volume:
                    solid = cut
            except Exception:
                pass
        try:
            solid = solid.clean()
        except Exception:
            pass
        sols = list(solid.solids()) if hasattr(solid, "solids") else [solid]
        if len(sols) != 1 or not sols[0].is_valid:
            return None
        solid = sols[0]
        if solid.volume < 0:
            solid = Shape.cast(solid.wrapped.Reversed())
        expect = body.area * t
        if not 0.5 * expect <= solid.volume <= 1.5 * expect:
            return None
        return solid
    except Exception:
        return None


def _join_thick(body, d):
    """Solid of a shell or face thickened by d with BRepOffset_MakeOffset (thickening, intersection join): the
    offset faces are trimmed where they meet, so inside corners have no folded faces. None when the offset fails,
    is not one valid solid, or its volume is not near area x thickness (a self-intersecting result)."""
    from OCP.BRepOffset import BRepOffset_MakeOffset, BRepOffset_Skin
    from OCP.GeomAbs import GeomAbs_Intersection
    from OCP.BRepCheck import BRepCheck_Analyzer
    from build123d import Shape
    try:
        mo = BRepOffset_MakeOffset()
        mo.Initialize(body.wrapped, d, 1e-4, BRepOffset_Skin, False, False, GeomAbs_Intersection, True, False)
        mo.MakeOffsetShape()
        if not mo.IsDone():
            return None
        r = Shape.cast(mo.Shape())
        if len(r.solids()) != 1 or not BRepCheck_Analyzer(r.wrapped).IsValid():
            return None
        r = r.solids()[0]
        if r.volume < 0:
            r = Shape.cast(r.wrapped.Reversed())
        expect = body.area * abs(d)
        if expect > 0 and not 0.5 * expect <= r.volume <= 1.5 * expect:
            return None
        return r
    except Exception:
        return None


def _simple_thick(shape, d):
    """Solid of one shell or face thickened by d (simple offset), or None."""
    from OCP.BRepOffset import BRepOffset_MakeSimpleOffset
    from build123d import Shape
    try:
        op = BRepOffset_MakeSimpleOffset(shape.wrapped, d)
        op.SetBuildSolidFlag(True)
        op.Perform()
        if op.IsDone():
            r = Shape.cast(op.GetResultShape())
            if r.solids():
                return Shape.cast(r.wrapped.Reversed()) if r.volume < 0 else r
    except Exception:
        pass
    return None


def _thicken_pieces(body, d):
    """Thicken shell by shell (and the loose faces), a shell that does not offset face by face, and fuse.
    Returns (solid, note); raises with the faces that do not offset."""
    shells = list(body.shells())
    in_shell = [fc for sh in shells for fc in sh.faces()]
    loose = [fc for fc in body.faces() if not any(fc.wrapped.IsSame(x.wrapped) for x in in_shell)]
    parts, bad, by_face = [], [], 0
    for sh in shells:
        r = _simple_thick(sh, d)
        if r is not None:
            parts.append(r)
            continue
        for fc in sh.faces():
            by_face += 1
            rf = _simple_thick(fc, d)
            if rf is None:
                c = fc.center()
                bad.append("face at (%.1f, %.1f, %.1f) mm, area %.1f mm^2" % (c.X, c.Y, c.Z, fc.area))
            else:
                parts.append(rf)
    for fc in loose:
        rf = _simple_thick(fc, d)
        if rf is None:
            c = fc.center()
            bad.append("face at (%.1f, %.1f, %.1f) mm, area %.1f mm^2" % (c.X, c.Y, c.Z, fc.area))
        else:
            parts.append(rf)
    if bad:
        raise ValueError("the thicken failed on %d face(s): %s (a degenerate face, or a curvature radius smaller than "
                         "the thickness)" % (len(bad), "; ".join(bad[:4])))
    if not parts:
        raise ValueError("the thicken failed")
    solid = parts[0]
    for q in parts[1:]:
        solid = solid.fuse(q)
    try:
        solid = solid.clean()
    except Exception:
        pass
    if not solid.solids():
        raise ValueError("the thicken failed (the pieces do not fuse)")
    bits = []
    if loose:
        bits.append("%d face(s) not sewn to the shell thickened alone" % len(loose))
    if by_face:
        bits.append("%d face(s) of a shell that does not offset as a whole thickened face by face" % by_face)
    if len(shells) > 1:
        bits.append("%d shells thickened separately" % len(shells))
    return solid, "; ".join(bits) + "; the pieces are fused (at the seams the result is the union of the pieces)"


def cut_with_surface(shape, bodies, f):
    """Splits the solid with the surface body and keeps the pieces on one side of it."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.BRep import BRep_Tool
    from OCP.gp import gp_Pnt
    from build123d import Shape, Compound
    if (f.get("with") or "") == "plane":
        # a plane: a square on it larger than the solid ("plane": XY / XZ / YZ or a plane feature id)
        src = _plane_tool_face(_plane_frame(f, f.get("plane") or "XY"), shape)
    else:
        src = bodies.get(f.get("source"))
    if src is None:
        raise ValueError("source surface not found (a surface body above this feature, or a plane)")
    keep = f.get("keep") or "-"
    args, tools = _shape_list(), _shape_list()
    for so in shape.solids():
        args.Append(so.wrapped)
    for fc in src.faces():
        tools.Append(fc.wrapped)
    op = BRepAlgoAPI_Splitter()
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetRunParallel(True)
    op.SetUseOBB(True)
    op.Build()
    if not op.IsDone():
        raise ValueError("the split failed")
    pieces = list(Shape.cast(op.Shape()).solids())
    v_all = sum(so.volume for so in shape.solids())

    def plausible(pcs):
        return len(pcs) >= len(list(shape.solids())) + 1 and abs(sum(x.volume for x in pcs) - v_all) <= 1e-3 * v_all
    if not plausible(pieces) and (f.get("with") or "") == "plane":
        # a plane through edges, seams or degenerate faces of the solid (the symmetry plane of an imported part)
        # does not split it: the plane is moved towards the removed side, by 0.001 mm, then 0.3 mm, then 1 mm
        fr = _plane_frame(f, f.get("plane") or "XY")
        n = [float(v) for v in fr["z"]]
        sgn = -1.0 if keep == "+" else 1.0           # towards the removed side: against the normal when + is kept
        for d in (1e-3, 0.3, 1.0):
            fr2 = dict(fr, o=[fr["o"][k] + sgn * d * n[k] for k in range(3)])
            src2 = _plane_tool_face(fr2, shape)
            tools2 = _shape_list()
            for fc in src2.faces():
                tools2.Append(fc.wrapped)
            op2 = BRepAlgoAPI_Splitter()
            op2.SetArguments(args)
            op2.SetTools(tools2)
            op2.SetRunParallel(True)
            op2.SetUseOBB(True)
            op2.Build()
            if not op2.IsDone():
                continue
            pcs = list(Shape.cast(op2.Shape()).solids())
            if plausible(pcs):
                pieces, src = pcs, src2
                f["_note"] = "the plane lies on edges or faces of the solid: moved %g mm towards the removed side for the cut" % d
                break
        else:
            raise ValueError("the plane does not cut the solid (it lies outside the solid, or edges, seams or degenerate "
                             "faces of the part lie in it); move the plane")
    faces = list(src.faces())
    out = []
    for p in pieces:
        c = p.center()
        # signed side: projection on the nearest surface face, dot with its normal
        best = None
        for fc in faces:
            pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(c.X, c.Y, c.Z), BRep_Tool.Surface_s(fc.wrapped))
            if pr.NbPoints() == 0:
                continue
            dist = pr.LowerDistance()
            if best is None or dist < best[0]:
                q = pr.NearestPoint()
                u, v = pr.LowerDistanceParameters()
                n = fc.normal_at(__import__("build123d").Vector(q.X(), q.Y(), q.Z()))
                side = (c.X - q.X()) * n.X + (c.Y - q.Y()) * n.Y + (c.Z - q.Z()) * n.Z
                best = (dist, side)
        if best is None:
            out.append(p)
        elif (best[1] >= 0) == (keep == "+"):
            out.append(p)
    if not out:
        raise ValueError("nothing left on the kept side; change Keep")
    return out[0] if len(out) == 1 else Compound(children=out)


# --------------------------------------------------------------------------- curve bodies

def smooth_wire(wire, angle=15.0):
    """The wire with its runs of edges that meet at less than angle (deg) replaced by one B-spline each (an
    interpolation through the edge ends and points along curved edges; periodic for a closed wire without a sharp
    corner). Corners at or above angle are kept, so a polyline approximation of a curve becomes one smooth edge and
    a rectangle stays four edges."""
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.GeomAPI import GeomAPI_Interpolate
    try:
        from OCP.TColgp import TColgp_HArray1OfPnt
    except ImportError:                                   # OCP builds with the collections module
        from OCP.collections import HArray1_gp_Pnt as TColgp_HArray1OfPnt
    from OCP.gp import gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from build123d import Edge, Wire
    ex = BRepTools_WireExplorer(wire.wrapped)
    edges = []
    while ex.More():
        edges.append(Edge(ex.Current()))
        ex.Next()
    if len(edges) < 2:
        return wire
    closed = wire.is_closed
    cos_t = math.cos(math.radians(angle))
    # oriented ends and tangents along the wire direction
    info = []
    for i, e in enumerate(edges):
        a, b = e.position_at(0), e.position_at(1)
        nxt = edges[(i + 1) % len(edges)]
        rev = False
        if i > 0:
            # follow the oriented end of the previous edge (a two-edge loop touches the next edge at both ends)
            pa = info[-1]["end"]
            rev = (b - pa).length < (a - pa).length
        elif len(edges) > 1:
            na, nb = nxt.position_at(0), nxt.position_at(1)
            if min((b - na).length, (b - nb).length) > min((a - na).length, (a - nb).length) + 1e-9:
                rev = True
        ts = [e.tangent_at(u) for u in (0.0, 1.0)]
        if rev:
            a, b = b, a
            ts = [-ts[1], -ts[0]]
        geo = str(getattr(e.geom_type, "name", e.geom_type)).upper()
        n = 1 if geo == "LINE" else max(4, min(24, int(e.length / max(1e-9, wire.length) * 200)))
        pts = [e.position_at(1.0 - k / n if rev else k / n) for k in range(n)]
        info.append({"start": a, "end": b, "t0": ts[0], "t1": ts[1], "pts": pts, "edge": e})
    smooth = [info[i]["t1"].normalized().dot(info[(i + 1) % len(info)]["t0"].normalized()) >= cos_t
              for i in range(len(info))]
    if not closed:
        smooth[-1] = False
    if not any(smooth):
        return wire
    if all(smooth):
        runs, periodic = [list(range(len(info)))], True
    else:
        # runs between sharp joints; a closed wire starts after a sharp joint
        start = (smooth.index(False) + 1) % len(info) if closed else 0
        order = [(start + k) % len(info) for k in range(len(info))]
        runs, cur = [], []
        for i in order:
            cur.append(i)
            if not smooth[i]:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        periodic = False
    out = []
    for run in runs:
        if len(run) == 1:
            out.append(info[run[0]]["edge"])
            continue
        pts = [q for i in run for q in info[i]["pts"]]
        if not periodic:
            pts.append(info[run[-1]]["end"])
        clean = [pts[0]]
        for q in pts[1:]:
            if (q - clean[-1]).length > 1e-7:
                clean.append(q)
        if periodic and (clean[-1] - clean[0]).length <= 1e-7:
            clean.pop()
        arr = TColgp_HArray1OfPnt(1, len(clean))
        for k, q in enumerate(clean):
            arr.SetValue(k + 1, gp_Pnt(q.X, q.Y, q.Z))
        it = GeomAPI_Interpolate(arr, periodic, 1e-7)
        it.Perform()
        if not it.IsDone():
            return wire
        out.append(Edge(BRepBuilderAPI_MakeEdge(it.Curve()).Edge()))
    try:
        return Wire(out)
    except Exception:
        return wire


def _closed_wire(wire, tol):
    """The wire with its two end vertices merged when they lie within tol (mm) of each other (edges from different
    bodies meet at the same point with separate vertices, so the chain is not closed topologically); the wire
    itself otherwise."""
    from OCP.ShapeFix import ShapeFix_Wire
    from OCP.ShapeAnalysis import ShapeAnalysis_Wire
    from build123d import Wire
    try:
        d = (wire.position_at(0) - wire.position_at(1)).length
        if d > tol:
            return wire
        sw = ShapeFix_Wire()
        sw.Load(wire.wrapped)
        sw.SetPrecision(max(tol, 1e-6))
        sw.ClosedWireMode = True
        sw.FixReorder()
        sw.FixConnected()
        sw.FixClosed()
        w = Wire(sw.Wire())
        return w if w.is_closed else wire
    except Exception:
        return wire


def _chain_wires(edges):
    from build123d import Wire
    try:
        return list(Wire.combine(edges))
    except Exception:
        return [Wire([e]) for e in edges]


def _join_gaps(wires, gap, close_factor=10.0):
    """Wires whose ends are at most gap (mm) apart joined into one wire each, every gap bridged by a straight line;
    a chain whose two ends are at most gap apart (and longer than close_factor x gap) closed the same way.
    Returns (wires, number of bridges)."""
    from build123d import Wire, Edge
    rest = list(wires)
    out, n = [], 0
    while rest:
        chain = [rest.pop(0)]
        a, b = chain[0].position_at(0), chain[0].position_at(1)
        while True:
            best = None
            for k, w in enumerate(rest):
                s, e = w.position_at(0), w.position_at(1)
                for side, p in (("b", b), ("a", a)):
                    for q, other in ((s, e), (e, s)):
                        d = (q - p).length
                        if d <= gap and (best is None or d < best[0]):
                            best = (d, k, side, p, q, other)
            if best is None:
                break
            d, k, side, p, q, other = best
            w = rest.pop(k)
            bridge = [Edge.make_line(p, q)] if d > 1e-6 else []
            n += len(bridge)
            if side == "b":
                chain += bridge + [w]
                b = other
            else:
                chain = [w] + bridge + chain
                a = other
        d = (b - a).length
        if 1e-6 < d <= gap and sum(x.length for x in chain) > close_factor * gap:
            chain.append(Edge.make_line(b, a))
            n += 1
        edges = [e for x in chain for e in x.edges()]
        joined = list(Wire.combine(edges, tol=1e-4))
        out += joined
    return out, n


def _approx_wire(wire, tol, analytic):
    """One smooth edge through a wire: a line or a circular arc within tol when analytic is set and the shape
    allows it, else a degree-3 C2 B-spline fitted to the wire (joins the pieces, removes small kinks)."""
    from OCP.BRepAdaptor import BRepAdaptor_CompCurve
    from OCP.Approx import Approx_Curve3d
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from build123d import Edge
    n = 33
    pts = [wire.position_at(k / (n - 1.0)) for k in range(n)]
    if analytic:
        a, b = pts[0], pts[-1]
        d = b - a
        if d.length > 1e-9:
            u = d.normalized()
            if max(((q - a) - u * (q - a).dot(u)).length for q in pts) <= tol:
                e = Edge.make_line(a, b)
                e._kind = "line"
                return e
        try:
            m = pts[n // 2]
            arc = Edge.make_three_point_arc(a, m, b)
            # deviation of the sampled points from the arc's circle
            c = arc.arc_center
            r = (a - c).length
            nrm = (m - a).cross(b - a)
            if nrm.length > 1e-9:
                nrm = nrm.normalized()
                dev = max(max(abs((q - c).length - r), abs((q - c).dot(nrm))) for q in pts)
                if dev <= tol:
                    arc._kind = "circular arc"
                    return arc
        except Exception:
            pass
    ad = BRepAdaptor_CompCurve(wire.wrapped, True)
    ap = Approx_Curve3d(ad, tol, GeomAbs_C2, 64, 3)
    if not (ap.IsDone() or ap.HasResult()):
        raise ValueError("the curve cannot be approximated within %g mm" % tol)
    e = Edge(BRepBuilderAPI_MakeEdge(ap.Curve()).Edge())
    e._kind = "smooth spline"
    return e


def curve_extract(shape, bodies, f, find_edges, expand_edges):
    """Curve body from picked edges of the solid: chains joined; "clean": none | smooth | analytic within
    tolerance; "project": surface body id to project the curve onto."""
    from build123d import Compound, Wire
    refs = f.get("edges") or []
    if f.get("tangent_chain") and shape is not None:
        refs = expand_edges(shape, refs, "tangent")
    edges = find_edges(shape, refs)
    if not edges:
        raise ValueError("no edges picked")
    wires = _chain_wires(edges)
    gap = float(f.get("gap") or 0)
    bridged = 0
    if gap > 0 and wires:
        wires, bridged = _join_gaps(wires, gap)
    clean = f.get("clean") or "none"
    tol = float(f.get("tolerance") or 0.05)
    out = []
    kinds = ["%d gap(s) bridged" % bridged] if bridged else []
    for w in wires:
        if clean == "none":
            out.append(w)
        else:
            e = _approx_wire(w, tol, clean == "analytic")
            kinds.append(getattr(e, "_kind", ""))
            out.append(Wire([e]))
    proj = f.get("project")
    if proj:
        surf = bodies.get(proj)
        if surf is None:
            raise ValueError("projection surface not found")
        from OCP.BRepProj import BRepProj_Projection
        from OCP.gp import gp_Dir
        from build123d import Shape
        projected = []
        for w in out:
            # projection along the surface normal at the curve middle
            fc = max(surf.faces(), key=lambda x: x.area)
            c = w.position_at(0.5)
            n = fc.normal_at(c)
            pr = BRepProj_Projection(w.wrapped, surf.wrapped, gp_Dir(n.X, n.Y, n.Z))
            best = None
            while pr.More():
                cand = Shape.cast(pr.Current())
                d = (cand.center() - c).length
                if best is None or d < best[0]:
                    best = (d, cand)
                pr.Next()
            if best is None:
                raise ValueError("the projection misses the surface")
            projected.append(best[1])
        out = projected
    body = out[0] if len(out) == 1 else Compound(children=out)
    body._kind = ", ".join(dict.fromkeys(k for k in kinds if k)) or None
    return body


def _wire_edges_ordered(wire):
    """The edges of a wire in order, each as (edge, start point, end point, start tangent, end tangent) with the
    points and tangents following the direction of travel along the wire."""
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.gp import gp_Pnt, gp_Vec
    from build123d import Edge, Vector
    out = []
    ex = BRepTools_WireExplorer(wire.wrapped)
    while ex.More():
        e = ex.Current()
        ad = BRepAdaptor_Curve(e)
        p0, p1, v0, v1 = gp_Pnt(), gp_Pnt(), gp_Vec(), gp_Vec()
        ad.D1(ad.FirstParameter(), p0, v0)
        ad.D1(ad.LastParameter(), p1, v1)
        a, b = Vector(p0.X(), p0.Y(), p0.Z()), Vector(p1.X(), p1.Y(), p1.Z())
        ta, tb = Vector(v0.X(), v0.Y(), v0.Z()), Vector(v1.X(), v1.Y(), v1.Z())
        if e.Orientation() == TopAbs_REVERSED:
            a, b, ta, tb = b, a, -tb, -ta
        if ta.length > 1e-12:
            ta = ta.normalized()
        if tb.length > 1e-12:
            tb = tb.normalized()
        out.append((Edge(e), a, b, ta, tb))
        ex.Next()
    return out


def _smooth_chains(items, angle):
    """Runs of consecutive edges of a wire whose junctions turn by at most angle (deg); the last and the first edge
    of a closed wire join across the closing point. Each run is a list of items (edge, start, end, start tangent,
    end tangent) as _wire_edges_ordered gives them."""
    n = len(items)
    if n == 0:
        return []
    cos_min = math.cos(math.radians(angle))

    def smooth(i, j):
        tb, ta = items[i][4], items[j][3]
        return (items[i][2] - items[j][1]).length < 1e-3 and tb.dot(ta) >= cos_min

    breaks = [k for k in range(n) if not smooth(k - 1, k)]
    if not breaks:
        return [list(items)]
    chains = []
    for s, k in enumerate(breaks):
        end = breaks[s + 1] if s + 1 < len(breaks) else breaks[0] + n
        chains.append([items[m % n] for m in range(k, end)])
    return chains


def _corner_point(pe, pt, ns, nt, reach):
    """Where the line from pe along pt meets the line through ns along nt (the closest points of the two lines,
    their middle), or None when the lines are nearly parallel or the meeting point is more than reach away."""
    d = pt.cross(nt)
    if d.length < 1e-6:
        return None
    w = ns - pe
    # pe + s pt and ns + u nt closest: solve for s and u
    a, b, c = pt.dot(pt), pt.dot(nt), nt.dot(nt)
    dd, ee = pt.dot(w), nt.dot(w)
    den = a * c - b * b
    if abs(den) < 1e-12:
        return None
    s = (dd * c - b * ee) / den
    u = (b * dd - a * ee) / den
    if s < -1e-6 or u > 1e-6 or s > reach or -u > reach:
        return None
    p1 = pe + pt * s
    p2 = ns + nt * u
    if (p1 - p2).length > 0.1 * max(reach, 1e-3):
        return None
    return (p1 + p2) * 0.5


def _item_of(edge, start, end):
    """An item (edge, start, end, tangents) for a straight edge."""
    t = (end - start)
    t = t.normalized() if t.length > 1e-12 else t
    return (edge, start, end, t, t)


def _drop_short_chains(chains, min_edge):
    """Chains shorter than min_edge (mm) that sit in a corner removed: the chains on both sides are extended to the
    corner where their end tangents meet, when that corner lies within 1.5 x min_edge of the removed chain. A
    straight last or first edge gets the corner as its new end, any other edge a straight piece up to the corner.
    Short chains between nearly parallel neighbours (the end of a narrow strip) stay. Nothing happens when fewer
    than two chains would stay. Returns (chains, number of edges removed)."""
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from build123d import Edge
    if min_edge > 0:
        # a short edge at the start or end of a longer chain (a tiny chamfer meeting a long edge at a shallow
        # angle) is split off as a chain of its own
        split = []
        for ch in chains:
            if len(ch) > 1 and ch[0][0].length < min_edge and sum(it[0].length for it in ch) >= min_edge:
                split.append([ch[0]])
                ch = ch[1:]
            if len(ch) > 1 and ch[-1][0].length < min_edge and sum(it[0].length for it in ch) >= min_edge:
                split.append(ch[:-1])
                split.append([ch[-1]])
            else:
                split.append(ch)
        chains = split
    n = len(chains)
    if min_edge <= 0 or n < 3:
        return chains, 0
    short = [sum(it[0].length for it in ch) < min_edge for ch in chains]
    if n - sum(short) < 2:
        return chains, 0
    kept = [k for k in range(n) if not short[k]]
    # the gaps (runs of short chains between two kept chains) that have a corner
    corners = {}
    for idx, k in enumerate(kept):
        nk = kept[(idx + 1) % len(kept)]
        gap = [m % n for m in range(k + 1, k + 1 + ((nk - k - 1) % n))]
        if not gap:
            continue
        pe, pt = chains[k][-1][2], chains[k][-1][4]
        ns, nt = chains[nk][0][1], chains[nk][0][3]
        c = _corner_point(pe, pt, ns, nt, 3.0 * min_edge)
        if c is None or (c - pe).length > 1.5 * min_edge or (c - ns).length > 1.5 * min_edge:
            continue
        corners[k] = (nk, gap, c)
    if not corners:
        return chains, 0
    out = [list(ch) for ch in chains]
    drop = set()
    removed = 0

    def straight(it):
        return BRepAdaptor_Curve(it[0].wrapped).GetType() == GeomAbs_Line
    for k, (nk, gap, c) in corners.items():
        drop.update(gap)
        removed += sum(len(chains[m]) for m in gap)
        prev, nxt = out[k], out[nk]
        pe, ns = prev[-1][2], nxt[0][1]
        if (c - pe).length > 1e-6:
            if straight(prev[-1]):
                it = prev[-1]
                prev[-1] = _item_of(Edge.make_line(it[1], c), it[1], c)
            else:
                prev.append(_item_of(Edge.make_line(pe, c), pe, c))
        if (ns - c).length > 1e-6:
            if straight(nxt[0]):
                it = nxt[0]
                nxt[0] = _item_of(Edge.make_line(c, it[2]), c, it[2])
            else:
                nxt.insert(0, _item_of(Edge.make_line(c, ns), c, ns))
    return [out[k] for k in range(n) if k not in drop], removed


def _clean_wire(wire, clean, tol, angle, min_edge=0.0):
    """The wire with each smooth chain of its edges replaced by one edge (a line or circular arc within tol when
    analytic, else a C2 spline); with min_edge, chains shorter than it removed and their neighbours extended to the
    corner. Returns (wire, edges before, edges after, edges removed at corners)."""
    from build123d import Wire, Edge
    from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    items = _wire_edges_ordered(wire)
    chains = _smooth_chains(items, angle)
    removed = 0
    if wire.is_closed:
        chains, removed = _drop_short_chains(chains, min_edge)
    if len(chains) == 1 and len(chains[0]) > 1 and wire.is_closed:
        # a closed smooth loop: two halves, each one edge
        es = chains[0]
        h = max(1, len(es) // 2)
        chains = [es[:h], es[h:]]
    out = []
    for ch in chains:
        es = [it[0] for it in ch]
        if len(es) == 1:
            t = BRepAdaptor_Curve(es[0].wrapped).GetType()
            if t in (GeomAbs_Line, GeomAbs_Circle):
                out.append(es[0])
                continue
        w = Wire(es) if len(es) > 1 else Wire([es[0]])
        try:
            e = _approx_wire(w, tol, clean == "analytic")
        except Exception:
            out.extend(es)
            continue
        if abs(e.length - w.length) > max(tol, 0.01 * w.length) + 1e-6:
            out.extend(es)
            continue
        out.append(e)
    try:
        new = Wire(out) if len(out) > 1 else Wire([out[0]])
    except Exception:
        joined = list(Wire.combine(out, tol=max(tol, 1e-4)))
        if len(joined) != 1:
            return wire, len(items), len(items), 0
        new = joined[0]
    return new, len(items), len(out), removed


def _rebuild_face(face, wires, tol, allow=0.0):
    """The face rebuilt on its own surface with the given wires (the first is the outer wire); the new edges are
    projected onto the surface within tol. Raises ValueError when the result is not valid or its area changed by
    more than the tolerance allows plus allow (mm^2)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.ShapeFix import ShapeFix_Face, ShapeFix_Wire
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_REVERSED
    from build123d import Face
    surf = BRep_Tool.Surface_s(face.wrapped)
    base = BRepBuilderAPI_MakeFace(surf, 1e-6).Face()

    def on_surface(w):
        # the wire with pcurves on the surface (the new edges projected within tol)
        sw = ShapeFix_Wire(w.wrapped, base, max(tol, 1e-4))
        sw.FixReorder()
        sw.FixConnected()
        sw.FixEdgeCurves()
        sw.Perform()
        return sw.Wire()
    mk = BRepBuilderAPI_MakeFace(surf, on_surface(wires[0]), True)
    for w in wires[1:]:
        mk.Add(on_surface(w))
    if not mk.IsDone():
        raise ValueError("the face could not be rebuilt")
    fx = ShapeFix_Face(mk.Face())
    fx.SetPrecision(max(tol, 1e-4))
    fx.SetMaxTolerance(max(10 * tol, 1e-3))
    fx.FixOrientationMode = 1
    fx.FixWireMode = 1
    fx.Perform()
    res = fx.Face()
    if face.wrapped.Orientation() == TopAbs_REVERSED and res.Orientation() != TopAbs_REVERSED:
        res.Reverse()
    from OCP.BRepLib import BRepLib
    try:
        BRepLib.SameParameter_s(res, max(tol, 1e-4), True)
    except Exception:
        pass
    out = Face(res)
    if not BRepCheck_Analyzer(out.wrapped).IsValid():
        raise ValueError("the rebuilt face is not valid")
    a0, a1 = face.area, out.area
    per = sum(w.length for w in face.wires())
    if abs(a1 - a0) > max(0.02 * a0, 2.0 * tol * per) + allow:
        raise ValueError("the rebuilt face area differs (%.3f -> %.3f mm^2)" % (a0, a1))
    # the face must triangulate over its whole area (a boundary the mesher cannot follow leaves holes in the view)
    am = _mesh_area(out)
    if am is not None and abs(am - a1) > max(0.03 * a1, 0.5):
        raise ValueError("the rebuilt face does not triangulate (%.3f of %.3f mm^2)" % (am, a1))
    return out


def _mesh_area(face):
    """Area of the triangulation of a face (meshed alone), or None when it cannot be meshed."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    try:
        f = BRepBuilderAPI_Copy(face.wrapped, True, False).Shape()
        bb = face.bounding_box()
        BRepMesh_IncrementalMesh(f, max(bb.diagonal / 500.0, 0.01), False, 0.5, True)
        loc = TopLoc_Location()
        from OCP.TopoDS import TopoDS
        tri = BRep_Tool.Triangulation_s(TopoDS.Face_s(f), loc)
        if tri is None or tri.NbTriangles() == 0:
            return 0.0
        area = 0.0
        for i in range(1, tri.NbTriangles() + 1):
            n1, n2, n3 = tri.Triangle(i).Get()
            p1, p2, p3 = tri.Node(n1), tri.Node(n2), tri.Node(n3)
            ax, ay, az = p2.X() - p1.X(), p2.Y() - p1.Y(), p2.Z() - p1.Z()
            bx, by, bz = p3.X() - p1.X(), p3.Y() - p1.Y(), p3.Z() - p1.Z()
            cx, cy, cz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
            area += 0.5 * (cx * cx + cy * cy + cz * cz) ** 0.5
        return area
    except Exception:
        return None


def clean_edges(shape, bodies, f, find_faces):
    """Surface body with the boundary edges of each face joined: every run of edges meeting within "angle" (deg)
    becomes one edge, a line or circular arc within "tolerance" when "clean" is "analytic" (else a C2 spline).
    "min_edge" (mm): runs shorter than it (a notch, a chamfered corner) are removed and the neighbouring edges
    extended to their corner. "min_face" (mm^2): faces smaller than it are dropped. Faces that cannot be rebuilt
    are kept as they are."""
    from OCP.BRepTools import BRepTools
    from build123d import Wire, Compound
    src = source_body(shape, bodies, f, find_faces)
    clean = f.get("clean") or "analytic"
    tol = float(f.get("tolerance") or 0.05)
    angle = float(f.get("angle") if f.get("angle") is not None else 15.0)
    min_edge = float(f.get("min_edge") or 0)
    min_face = float(f.get("min_face") or 0)
    faces = list(src.faces())
    dropped = 0
    if min_face > 0 and len(faces) > 1:
        small = [fc for fc in faces if fc.area < min_face]
        if len(small) < len(faces):
            faces = [fc for fc in faces if fc.area >= min_face]
            dropped = len(small)
    if not faces:
        raise ValueError("the source has no faces")
    out, before, after, kept, corners = [], 0, 0, 0, 0
    for fc in faces:
        outer = Wire(BRepTools.OuterWire_s(fc.wrapped))
        inner = [w for w in fc.wires() if not w.wrapped.IsSame(outer.wrapped)]
        new_wires, nb, na, nr = [], 0, 0, 0
        for w in [outer] + inner:
            nw, b, a, r = _clean_wire(w, clean, tol, angle, min_edge)
            new_wires.append(nw)
            nb += b
            na += a
            nr += r
        if na == nb and nr == 0:
            out.append(fc)
            before += nb
            after += na
            continue
        try:
            out.append(_rebuild_face(fc, new_wires, tol, allow=min(1.5 * min_edge * min_edge * nr, 0.5 * fc.area)))
            before += nb
            after += na
            corners += nr
        except ValueError:
            out.append(fc)
            before += nb
            after += nb
            kept += 1
    body = _sew(out, max(tol, 1e-4)) if len(out) > 1 else out[0]
    if len(out) > 1 and len(list(body.faces())) != len(out):
        body = Compound(children=out)
    note = "%d edge(s) joined into %d" % (before, after) if after < before else "no edges to join"
    if corners:
        note += "; %d short edge(s) removed at corners" % corners
    if dropped:
        note += "; %d small face(s) dropped" % dropped
    if kept:
        note += "; %d face(s) kept as they were" % kept
    body._kind = note
    return body


def _plane_tool_face(fr, about):
    """A square face on the frame fr (dict o, z, x), centred at the projection of the centre of the shape about
    and larger than it."""
    from build123d import Shape
    bb = about.bounding_box()
    c, o, z = bb.center(), fr["o"], fr["z"]
    h = (c.X - o[0]) * z[0] + (c.Y - o[1]) * z[1] + (c.Z - o[2]) * z[2]
    fr = dict(fr, o=[c.X - h * z[0], c.Y - h * z[1], c.Z - h * z[2]])
    return Shape.cast(plane_face(fr, max(bb.diagonal, 10.0) * 2))


def _plane_frame(f, ref):
    """The frame of a plane reference: XY / XZ / YZ or a plane feature id (from f["_datums"])."""
    from .part import PRINCIPAL_FRAMES, _frame_of
    if ref in PRINCIPAL_FRAMES:
        n, x = PRINCIPAL_FRAMES[ref]
        return _frame_of([0, 0, 0], n, x)
    fr = (f.get("_datums") or {}).get(ref)
    if not fr:
        raise ValueError("the plane was not found")
    return fr


def separate(shape, bodies, f, find_faces):
    """Separate faces: the picked "faces" of surface body "source" as one body ("keep": "picked"), or the other
    faces of that body ("keep": "rest")."""
    src = bodies.get(f.get("source"))
    if src is None:
        raise ValueError("source surface not found (a surface body above this feature in the tree)")
    refs = f.get("faces") or []
    if not refs:
        raise ValueError("pick the faces to separate")
    picked = find_faces(src, refs)
    if not picked:
        raise ValueError("the picked faces were not found on the source body (pick them again)")
    allf = list(src.faces())
    if (f.get("keep") or "picked") == "rest":
        out = [fc for fc in allf if not any(fc.wrapped.IsSame(x.wrapped) for x in picked)]
        if not out:
            raise ValueError("every face of the body is picked: nothing remains")
    else:
        out = picked
    body = _sew(out) if len(out) > 1 else out[0]
    body._kind = "%d of %d face(s) of %s, %d shell(s)" % (len(out), len(allf), "the rest" if (f.get("keep") or "picked") == "rest" else "the picked faces", len(body.shells()) if len(out) > 1 else 1)
    return body


def curve_section(shape, bodies, f, find_faces):
    """Intersection curves of two surface bodies, of a surface body (or faces of the solid) with the solid, or
    ("with": "plane", "plane": XY / XZ / YZ or a plane feature id) with a plane."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from build123d import Shape, Compound
    a = source_body(shape, bodies, f, find_faces)
    if (f.get("with") or "") == "plane":
        b = _plane_tool_face(_plane_frame(f, f.get("plane") or "XY"), a)
    else:
        b = bodies.get(f.get("other")) if f.get("other") else shape
    if b is None:
        raise ValueError("second shape not found")
    sec = BRepAlgoAPI_Section(a.wrapped, b.wrapped, False)
    sec.ComputePCurveOn1(False)
    sec.Approximation(True)
    sec.Build()
    if not sec.IsDone():
        raise ValueError("the intersection failed")
    res = Shape.cast(sec.Shape())
    edges = list(res.edges())
    if not edges:
        raise ValueError("the shapes do not intersect")
    wires = _chain_wires(edges)
    gap = float(f.get("gap") if f.get("gap") is not None else 0.5)
    bridged = 0
    if gap > 0 and len(wires) > 1:
        wires, bridged = _join_gaps(wires, gap)
    out = wires[0] if len(wires) == 1 else Compound(children=wires)
    out._kind = "%d curve(s), %.1f mm%s" % (len(wires), sum(w.length for w in wires), ", %d gap(s) bridged" % bridged if bridged else "")
    return out


def surf_from_curve(bodies, f):
    """Surface from a curve body: extruded along a direction (x, y, z, length) or revolved about an axis."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
    from OCP.gp import gp_Vec, gp_Ax1, gp_Pnt, gp_Dir
    from build123d import Shape, Location, Vector
    src = bodies.get(f.get("source"))
    if src is None:
        raise ValueError("source curve not found")
    kind = f.get("kind") or "extrude"
    if kind == "extrude":
        d = [float(v) for v in (f.get("direction") or [0, 0, 1])]
        L = math.sqrt(sum(v * v for v in d)) or 1.0
        depth = float(f.get("depth") or 10)
        d = [v / L * depth for v in d]
        base = src
        if f.get("symmetric"):
            base = src.moved(Location(Vector(-d[0] / 2, -d[1] / 2, -d[2] / 2)))
        res = Shape.cast(BRepPrimAPI_MakePrism(base.wrapped, gp_Vec(*d)).Shape())
        # an edge along the direction gives a face of zero area: left out
        faces = list(res.faces())
        good = [fc for fc in faces if fc.area > 1e-9]
        if good and len(good) < len(faces):
            res = good[0] if len(good) == 1 else _sew(good, 1e-6)
            res._kind = "%d face(s) of zero area left out (curve edges along the direction)" % (len(faces) - len(good))
        return res
    p = [float(v) for v in (f.get("axis_point") or [0, 0, 0])]
    d = [float(v) for v in (f.get("axis_dir") or [0, 0, 1])]
    ang = math.radians(float(f.get("angle") or 360))
    return Shape.cast(BRepPrimAPI_MakeRevol(src.wrapped, gp_Ax1(gp_Pnt(*p), gp_Dir(*d)), ang).Shape())


def loft_sources(bodies, f):
    """Loft through curve bodies (one chain each)."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from build123d import Shape
    srcs = [bodies.get(i) for i in (f.get("curves") or [])]
    srcs = [s for s in srcs if s is not None]
    if len(srcs) < 2:
        raise ValueError("a loft needs at least two curve bodies")
    op = BRepOffsetAPI_ThruSections(False, bool(f.get("ruled")), 1e-6)
    for s in srcs:
        wires = _chain_wires(list(s.edges()))
        if len(wires) != 1:
            raise ValueError("each curve body must be one chain")
        w = smooth_wire(wires[0], float(f.get("smooth_angle", 15) or 15)) if f.get("smooth", True) else wires[0]
        op.AddWire(w.wrapped)
    op.Build()
    if not op.IsDone():
        raise ValueError("the loft failed")
    return Shape.cast(op.Shape())


def _point_on(face):
    """A point on the face (its centre of mass can lie in a hole)."""
    from OCP.BRepTools import BRepTools
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.gp import gp_Pnt2d
    from OCP.TopAbs import TopAbs_IN
    from OCP.BRep import BRep_Tool
    from build123d import Vector
    from OCP.TopAbs import TopAbs_FACE
    if face.wrapped.ShapeType() != TopAbs_FACE:
        # a region of several faces: a point on its largest face
        face = max(face.faces(), key=lambda x: x.area)
    u1, u2, v1, v2 = BRepTools.UVBounds_s(face.wrapped)
    surf = BRep_Tool.Surface_s(face.wrapped)
    for fu, fv in ((0.5, 0.5), (0.25, 0.5), (0.75, 0.5), (0.5, 0.25), (0.5, 0.75), (0.25, 0.25), (0.75, 0.75), (0.1, 0.5), (0.9, 0.5), (0.5, 0.1), (0.5, 0.9)):
        u, v = u1 + (u2 - u1) * fu, v1 + (v2 - v1) * fv
        if BRepClass_FaceClassifier(face.wrapped, gp_Pnt2d(u, v), 1e-7).State() == TopAbs_IN:
            p = surf.Value(u, v)
            return Vector(p.X(), p.Y(), p.Z())
    return face.center()


def plane_face(frame, size):
    """A square face of side 2*size (mm) on a frame {"o", "x", "y", "z"}."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Pln, gp_Pnt, gp_Dir, gp_Ax3
    ax = gp_Ax3(gp_Pnt(*frame["o"]), gp_Dir(*frame["z"]), gp_Dir(*frame["x"]))
    return BRepBuilderAPI_MakeFace(gp_Pln(ax), -size, size, -size, size).Face()


def trim_pieces_all(shape, bodies, f):
    """The pieces a trim chooses from: those of the source split by the tool and, with "mutual" (the tool a
    surface body), those of the tool split by the source as well. Returns (pieces, tool_body)."""
    pieces, tool_body = trim_pieces(shape, bodies, f)
    if f.get("mutual") and (f.get("with") or "surface") == "surface" and tool_body is not None and tool_body.faces():
        g = dict(f, source=f.get("tool"), tool=f.get("source"), faces=f.get("tool_faces") or [], tool_faces=f.get("faces") or [])
        g.pop("_note", None)
        more, _ = trim_pieces(shape, bodies, g)
        if g.get("_note"):
            f["_note"] = ((f.get("_note") + "; ") if f.get("_note") else "") + "tool: " + g["_note"]
        pieces = pieces + more
    return pieces, tool_body


def trim_pieces(shape, bodies, f):
    """The pieces of the source surface body split by the trimming tool: (pieces, tool_body). "faces": only these
    faces of the source body (or of the solid when "source" is null). "with": "surface" (tool: surface or curve body
    id; "tool_faces": only these faces of it), "solid", "plane" (tool: plane feature id, or XY / XZ / YZ; needs
    f["_datums"]) or "sketch" (tool: sketch feature id; its curves in f["_tool_edges"], projected onto the surface)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from OCP.BRepProj import BRepProj_Projection
    from OCP.gp import gp_Dir
    from build123d import Shape
    from .part import find_faces

    def part_of(body, refs, what):
        # the picked faces of a body (refs: face keys) as one body, the whole body without refs
        if not refs:
            return body
        fs = find_faces(body, refs)
        if not fs:
            raise ValueError("the picked faces of the %s were not found (pick them again)" % what)
        return _sew(fs) if len(fs) > 1 else fs[0]
    src = bodies.get(f.get("source"))
    if src is None and f.get("faces") and shape is not None:
        src = shape          # faces of the solid as the target
    if src is None:
        raise ValueError("source surface not found (a surface body above this feature in the tree)")
    src = part_of(src, f.get("faces"), "target")
    with_kind = f.get("with") or "surface"
    tool_shapes = []
    tool_body = None
    if with_kind == "solid":
        if shape is None:
            raise ValueError("no solid")
        tool_shapes = [fc.wrapped for fc in shape.faces()]
    elif with_kind == "plane":
        from .part import PRINCIPAL_FRAMES, _frame_of
        ref = f.get("tool") or "XY"
        if ref in PRINCIPAL_FRAMES:
            n, x = PRINCIPAL_FRAMES[ref]
            fr = _frame_of([0, 0, 0], n, x)
        else:
            fr = (f.get("_datums") or {}).get(ref)
            if not fr:
                raise ValueError("the trimming plane was not found")
        # a square on the plane centred at the projection of the middle of the surface, larger than the surface
        bb = src.bounding_box()
        c, o, z = bb.center(), fr["o"], fr["z"]
        h = (c.X - o[0]) * z[0] + (c.Y - o[1]) * z[1] + (c.Z - o[2]) * z[2]
        fr = dict(fr, o=[c.X - h * z[0], c.Y - h * z[1], c.Z - h * z[2]])
        tool_shapes = [plane_face(fr, max(bb.diagonal, 10.0) * 2)]
    else:
        curves = None
        if with_kind == "sketch":
            curves = f.get("_tool_edges") or []
            if not curves:
                raise ValueError("the tool sketch has no curves")
        else:
            if not f.get("tool"):
                raise ValueError("pick the trimming tool: a surface or curve body, a sketch, the solid or a plane")
            tool_body = bodies.get(f.get("tool"))
            if tool_body is None:
                raise ValueError("trimming tool not found (a surface or curve body above this feature in the tree)")
            if tool_body.faces():
                tool_body = part_of(tool_body, f.get("tool_faces"), "tool")
                tool_shapes = [fc.wrapped for fc in tool_body.faces()]
            else:
                curves = tool_body.wires() or tool_body.edges()
        if curves is not None:
            # curve: projected onto the surface along the surface normal at the curve middle
            main = max(src.faces(), key=lambda x: x.area)
            for w in curves:
                c = w.position_at(0.5) if hasattr(w, "position_at") else w.center()
                n = main.normal_at(c)
                pr = BRepProj_Projection(w.wrapped, src.wrapped, gp_Dir(n.X, n.Y, n.Z))
                while pr.More():
                    tool_shapes.append(pr.Current())
                    pr.Next()
            if not tool_shapes:
                raise ValueError("the curve projection misses the surface")
    def run(faces, tool_list, fuzzy):
        args, tools = _shape_list(), _shape_list()
        for fc in faces:
            args.Append(fc.wrapped)
        for t in tool_list:
            tools.Append(t)
        op = BRepAlgoAPI_Splitter()
        op.SetArguments(args)
        op.SetTools(tools)
        op.SetRunParallel(True)
        if fuzzy:
            op.SetFuzzyValue(fuzzy)
        op.SetUseOBB(True)
        op.Build()
        if not op.IsDone():
            return None
        try:
            return list(Shape.cast(op.Shape()).faces())
        except Exception:  # noqa: BLE001
            return None

    def split(tool_list):
        # faces of zero area (they make the split fail) left out
        faces = [fc for fc in src.faces() if fc.area > 1e-9]
        for fuzzy in (0.0, 1e-4):
            res = run(faces, tool_list, fuzzy)
            if res:
                return res
        # the faces split one at a time (faces of the body that overlap or touch each other make the split of the
        # whole body fail), the pieces sewn again; a face that does not split stays whole
        out, bad = [], 0
        for fc in faces:
            res = None
            for fuzzy in (0.0, 1e-4, 1e-3):
                res = run([fc], tool_list, fuzzy)
                if res:
                    break
            if not res:
                bad += 1
                res = [fc]
            out += res
        if bad == len(faces):
            raise ValueError("the split failed")
        f["_note"] = "split face by face" + (" (%d face(s) not split)" % bad if bad else "")
        if len(out) < 2:
            return out
        return list(_sew(out, 1e-4).faces())
    tfs = list(tool_body.faces()) if (with_kind == "surface" and tool_body is not None and tool_body.faces()) else None
    by_face = (f.get("grouping") or "connected") == "faces"

    def regions(faces, tools_, tool_faces):
        # "grouping": "faces": every piece of the split on its own (no grouping through shared edges)
        return [fc for fc in faces if fc.area > 1e-9] if by_face else _regions(faces, tools_, tool_faces)
    pieces = regions(split(tool_shapes), tool_shapes, tfs)
    # slivers (a tool that only touches the target along an edge) do not count as a cut
    small = max(1e-6, 1e-4 * src.area)
    cut = len([pc for pc in pieces if pc.area > small]) >= 2
    if not cut and with_kind == "surface" and tool_body is not None and tool_body.faces():
        # a tool surface that does not quite reach across the target: its faces extended beyond their edges by
        # "extend" (mm, default 3; 0: off), then as a last resort across the whole target
        ext_mm = float(f.get("extend") if f.get("extend") is not None else 3.0)
        bb = src.bounding_box()
        reach = max(bb.diagonal, 1.0)
        dists = ([ext_mm] if ext_mm > 0 else []) + ([reach] if f.get("extend_far", True) else [])
        tfaces = list(tool_body.faces())
        # all the tool faces together; a tool of many faces also face by face (the extended faces of a whole
        # body intersect each other and make the split very slow)
        groups = [tfaces] + ([[fc] for fc in tfaces if fc.area > small] if len(tfaces) > 4 else [])
        for d in dists:
            for grp in (groups if d != reach or len(tfaces) <= 4 else groups[1:]):
                try:
                    ext_faces = [untrimmed_extended(fc, d) for fc in grp]
                    ext = [fc.wrapped for fc in ext_faces]
                    more = regions(split(ext), ext, ext_faces)
                except ValueError:
                    continue
                if len([pc for pc in more if pc.area > small]) >= 2:
                    pieces = more
                    cut = True
                    f["_note"] = "the tool surface was extended by %g mm beyond its edges to cut across the target" % d + (
                        "" if len(grp) == len(tfaces) else " (one face of the tool)")
                    break
            if cut:
                break
    if not cut:
        raise ValueError("the tool does not cut the surface" + (" (it only touches it)" if len(pieces) >= 2 else ""))
    return pieces, tool_body


def _side_of(point, tool_faces):
    """Signed distance of a point from the nearest of the tool faces (along that face's normal), or None."""
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.BRep import BRep_Tool
    from OCP.gp import gp_Pnt
    from build123d import Vector
    best = None
    for fc in tool_faces:
        try:
            pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(point.X, point.Y, point.Z), BRep_Tool.Surface_s(fc.wrapped))
            if pr.NbPoints() == 0:
                continue
            q = pr.NearestPoint()
            n = fc.normal_at(Vector(q.X(), q.Y(), q.Z()))
            side = (point.X - q.X()) * n.X + (point.Y - q.Y()) * n.Y + (point.Z - q.Z()) * n.Z
            if best is None or pr.LowerDistance() < best[0]:
                best = (pr.LowerDistance(), side)
        except Exception:
            continue
    return None if best is None else best[1]


def _regions(faces, tool_shapes, tool_faces=None):
    """The split faces grouped into regions: faces joined through an edge stay in one region unless that edge lies
    on the tool (the cut). With tool_faces (the surface tool), faces on opposite sides of the tool are never
    joined (a cut that is discontinuous at a face junction of imported geometry does not reconnect the sides), and
    a face on the tool itself (a sliver) joins its largest neighbour only. A region of one face is that face,
    else a shell of its faces."""
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.TopoDS import TopoDS_Compound, TopoDS_Shell
    from OCP.gp import gp_Pnt
    from build123d import Shape
    if len(faces) < 2:
        return list(faces)
    bld = BRep_Builder()
    tool = TopoDS_Compound()
    bld.MakeCompound(tool)
    for t in tool_shapes:
        bld.Add(tool, t)

    def on_tool(e):
        tol = max(1e-5, 2 * BRep_Tool.Tolerance_s(e.wrapped))
        for t in (0.0, 0.5, 1.0):
            q = e.position_at(t)
            v = BRepBuilderAPI_MakeVertex(gp_Pnt(q.X, q.Y, q.Z)).Vertex()
            if BRepExtrema_DistShapeShape(v, tool).Value() > tol:
                return False
        return True
    # side of each face: +1 / -1, 0 for a face on the tool (a sliver) or without a side
    sides = [0] * len(faces)
    if tool_faces:
        for i, fc in enumerate(faces):
            try:
                s = _side_of(_point_on(fc), tool_faces)
            except Exception:
                s = None
            sides[i] = 0 if s is None or abs(s) < 0.02 else (1 if s > 0 else -1)
    parent = list(range(len(faces)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    owners = {}
    for i, fc in enumerate(faces):
        for e in fc.edges():
            owners.setdefault(hash(e.wrapped), []).append((i, e))
    links = []                                   # (i, j) joined through an edge that is not on the tool
    for lst in owners.values():
        for a in range(len(lst)):
            for b in range(a + 1, len(lst)):
                (i, ei), (j, ej) = lst[a], lst[b]
                if i != j and ei.wrapped.IsSame(ej.wrapped) and not on_tool(ei):
                    links.append((i, j))
    # faces with a side: joined when on the same side
    for i, j in links:
        if sides[i] and sides[j] and sides[i] == sides[j] and root(i) != root(j):
            parent[root(i)] = root(j)
    # slivers (and faces without a side when no face has one): joined to their largest neighbour
    for i in range(len(faces)):
        if sides[i]:
            continue
        nb = [j for a, b in links for j in ((b,) if a == i else (a,) if b == i else ()) if j != i]
        if not nb:
            continue
        if not any(sides):
            for j in nb:
                if root(i) != root(j):
                    parent[root(i)] = root(j)
        else:
            j = max(nb, key=lambda k: faces[k].area)
            if root(i) != root(j):
                parent[root(i)] = root(j)
    groups = {}
    for i in range(len(faces)):
        groups.setdefault(root(i), []).append(faces[i])
    out = []
    for g in groups.values():
        if sum(fc.area for fc in g) <= 1e-9:
            continue
        if len(g) == 1:
            out.append(g[0])
            continue
        sh = TopoDS_Shell()
        bld.MakeShell(sh)
        for fc in g:
            bld.Add(sh, fc.wrapped)
        out.append(Shape.cast(sh))
    return out


def trim(shape, bodies, f):
    """Trim a surface body: split it with another surface body, with the solid, with a plane, or with a curve
    body projected onto it, and keep the pieces selected by "keep": "+" / "-" (side along / against the tool
    surface normal), "inside" / "outside" (of the solid), "largest", "point" (the piece nearest to "point"), or
    "pick" (every piece except those nearest to the points in "remove"). "mutual" (tool a surface body): the tool
    is split by the source too, its pieces are chosen the same way and the kept pieces of both are sewn into one
    body. "min_area" (mm^2, default 0.5): kept pieces below it are dropped. "grouping": "connected" (default: pieces
    joined through shared edges off the cut form one region) | "faces" (every piece of the split on its own)."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    from OCP.gp import gp_Pnt
    from build123d import Vector
    pieces, tool_body = trim_pieces_all(shape, bodies, f)
    keep = f.get("keep") or "largest"
    out = []
    if keep == "pick":
        removed = set()
        for q in f.get("remove") or []:
            qv = Vector(*[float(v) for v in q])
            i = min(range(len(pieces)), key=lambda k: (_point_on(pieces[k]) - qv).length)
            removed.add(i)
        out = [p for k, p in enumerate(pieces) if k not in removed]
        if not out:
            raise ValueError("every piece is removed")
    elif keep == "largest":
        out = [max(pieces, key=lambda p: p.area)]
    elif keep == "point":
        q = Vector(*[float(v) for v in (f.get("point") or [0, 0, 0])])
        out = [min(pieces, key=lambda p: (_point_on(p) - q).length)]
    elif keep in ("inside", "outside"):
        if shape is None:
            raise ValueError("no solid")
        solids = list(shape.solids())
        for p in pieces:
            c = _point_on(p)
            n = (p if len(p.faces()) == 1 else max(p.faces(), key=lambda x: x.area)).faces()[0].normal_at(c)
            # a point just off the face on both sides: inside when either is in the solid
            ins = False
            for sg in (1.0, -1.0):
                pt = gp_Pnt(c.X + n.X * 1e-3 * sg, c.Y + n.Y * 1e-3 * sg, c.Z + n.Z * 1e-3 * sg)
                if any(BRepClass3d_SolidClassifier(so.wrapped, pt, 1e-7).State() in (TopAbs_IN, TopAbs_ON) for so in solids):
                    ins = True
                    break
            if ins == (keep == "inside"):
                out.append(p)
    else:
        if tool_body is None or not tool_body.faces():
            raise ValueError("a side needs a surface tool; use largest, point, inside or outside")
        tfaces = list(tool_body.faces())
        for p in pieces:
            c = _point_on(p)
            best = None
            for fc in tfaces:
                pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(c.X, c.Y, c.Z), BRep_Tool.Surface_s(fc.wrapped))
                if pr.NbPoints() == 0:
                    continue
                q = pr.NearestPoint()
                n = fc.normal_at(Vector(q.X(), q.Y(), q.Z()))
                side = (c.X - q.X()) * n.X + (c.Y - q.Y()) * n.Y + (c.Z - q.Z()) * n.Z
                if best is None or pr.LowerDistance() < best[0]:
                    best = (pr.LowerDistance(), side)
            if best is not None and (best[1] >= 0) == (keep == "+"):
                out.append(p)
    if not out:
        raise ValueError("nothing kept; change Keep")
    # small pieces (below "min_area" mm^2, default 0.5) and slivers of the cut (faces thinner than 0.02 mm:
    # 2 x area / perimeter) dropped from the kept pieces
    min_area = float(f.get("min_area") if f.get("min_area") is not None else 0.5)
    big = [p for p in out if p.area >= min_area]
    if big and len(big) < len(out):
        f["_note"] = ((f.get("_note") + "; ") if f.get("_note") else "") + "%d piece(s) below %g mm^2 dropped" % (len(out) - len(big), min_area)
        out = big
    faces = [fc for pc in out for fc in pc.faces()]
    keep_f = [fc for fc in faces if not _is_sliver(fc)]
    if keep_f and len(keep_f) < len(faces):
        f["_note"] = ((f.get("_note") + "; ") if f.get("_note") else "") + "%d sliver face(s) dropped" % (len(faces) - len(keep_f))
        out = [_sew(keep_f) if len(keep_f) > 1 else keep_f[0]]
    res = out[0] if len(out) == 1 else _sew(out)
    return _merge_split_faces(res)


def _is_sliver(face, width=0.02):
    """A face thinner than width (mm): its mean width 2 x area / perimeter, or an area below 1e-6 mm^2."""
    try:
        a = face.area
        if a < 1e-6:
            return True
        per = sum(e.length for e in face.edges())
        return per > 0 and 2.0 * a / per < width
    except Exception:
        return False


def _merge_split_faces(body):
    """Pieces of one face of the body that lie on the same surface and share an edge merged back into one face
    (the cuts of a trim where both sides are kept disappear); the body is returned unchanged when the merge fails
    or changes the area."""
    from .occfix import CheckedUnify
    from build123d import Shape
    try:
        if len(body.faces()) < 2:
            return body
        u = CheckedUnify(body.wrapped, True, True, False)
        u.SetLinearTolerance(1e-4)
        u.SetAngularTolerance(1e-4)
        u.Build()
        out = Shape.cast(u.Shape())
        if out.faces() and abs(out.area - body.area) <= max(0.5, 1e-3 * body.area):
            return out
    except Exception:
        pass
    return body


def extend(shape, bodies, f, find_faces):
    """Extend a one-face surface body beyond its boundary by a distance (mm). "sides": "all" or a list of
    "umin", "umax", "vmin", "vmax", or "point" (the side nearest to "point"). Analytic surfaces get wider
    parameter bounds; B-spline surfaces are re-fitted with a linear (tangent) extrapolation beyond each side.
    The result is the untrimmed extended patch (inner trims are dropped)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.Precision import Precision
    from build123d import Shape, Vector
    try:
        from OCP.TColgp import TColgp_Array2OfPnt as Arr
    except ImportError:
        from OCP.collections import Array2_gp_Pnt as Arr
    src = source_body(shape, bodies, f, find_faces)
    faces = list(src.faces())
    if len(faces) != 1:
        raise ValueError("the source must be one face (sew several faces first, or extend them one by one)")
    face = faces[0]
    dist = float(f.get("distance") or 5.0)
    surf = BRep_Tool.Surface_s(face.wrapped)
    u1, u2, v1, v2 = BRepTools.UVBounds_s(face.wrapped)
    sides = f.get("sides") or "all"
    if sides == "point":
        q = Vector(*[float(v) for v in (f.get("point") or [0, 0, 0])])
        mids = {"umin": surf.Value(u1, (v1 + v2) / 2), "umax": surf.Value(u2, (v1 + v2) / 2),
                "vmin": surf.Value((u1 + u2) / 2, v1), "vmax": surf.Value((u1 + u2) / 2, v2)}
        sides = [min(mids, key=lambda k: (Vector(mids[k].X(), mids[k].Y(), mids[k].Z()) - q).length)]
    elif sides == "all":
        sides = ["umin", "umax", "vmin", "vmax"]

    def dlen(u, v, du, dv):
        # length of a parameter step at (u, v)
        p, d1u, d1v = gp_Pnt(), gp_Vec(), gp_Vec()
        surf.D1(u, v, p, d1u, d1v)
        return math.sqrt((d1u.X() * du + d1v.X() * dv) ** 2 + (d1u.Y() * du + d1v.Y() * dv) ** 2 + (d1u.Z() * du + d1v.Z() * dv) ** 2)

    um, vm = (u1 + u2) / 2, (v1 + v2) / 2
    # parameter increments giving the distance along each side (from the first derivative at the side middle)
    def inc(side):
        if side == "umin":
            s_ = dlen(u1, vm, 1.0, 0.0)
        elif side == "umax":
            s_ = dlen(u2, vm, 1.0, 0.0)
        elif side == "vmin":
            s_ = dlen(um, v1, 0.0, 1.0)
        else:
            s_ = dlen(um, v2, 0.0, 1.0)
        return dist / s_ if s_ > 1e-12 else 0.0

    du1 = inc("umin") if "umin" in sides else 0.0
    du2 = inc("umax") if "umax" in sides else 0.0
    dv1 = inc("vmin") if "vmin" in sides else 0.0
    dv2 = inc("vmax") if "vmax" in sides else 0.0
    name = surf.DynamicType().Name()
    nu1, nu2, nv1, nv2 = u1 - du1, u2 + du2, v1 - dv1, v2 + dv2
    if name in ("Geom_Plane", "Geom_CylindricalSurface", "Geom_ConicalSurface", "Geom_SphericalSurface", "Geom_ToroidalSurface"):
        if name != "Geom_Plane":
            nu1, nu2 = max(nu1, u1 - (2 * math.pi - (u2 - u1)) / 2), min(nu2, u2 + (2 * math.pi - (u2 - u1)) / 2)
            if name in ("Geom_SphericalSurface", "Geom_ToroidalSurface"):
                nv1, nv2 = max(nv1, -2 * math.pi), min(nv2, 2 * math.pi)
        out = Shape.cast(BRepBuilderAPI_MakeFace(surf, nu1, nu2, nv1, nv2, 1e-6).Face())
    else:
        # B-spline or other: sampled grid with tangent extrapolation beyond the kept bounds, re-fitted
        n = 25
        su1, su2, sv1, sv2 = surf.Bounds()
        inf = Precision.Infinite_s() / 2
        cu1, cu2 = max(u1, su1) if abs(su1) < inf else u1, min(u2, su2) if abs(su2) < inf else u2
        cv1, cv2 = max(v1, sv1) if abs(sv1) < inf else v1, min(v2, sv2) if abs(sv2) < inf else v2
        pts = Arr(1, n, 1, n)
        for i in range(n):
            u = nu1 + (nu2 - nu1) * i / (n - 1)
            for j in range(n):
                v = nv1 + (nv2 - nv1) * j / (n - 1)
                uc, vc = min(max(u, cu1), cu2), min(max(v, cv1), cv2)
                p, d1u, d1v = gp_Pnt(), gp_Vec(), gp_Vec()
                surf.D1(uc, vc, p, d1u, d1v)
                pts.SetValue(i + 1, j + 1, gp_Pnt(p.X() + d1u.X() * (u - uc) + d1v.X() * (v - vc),
                                                  p.Y() + d1u.Y() * (u - uc) + d1v.Y() * (v - vc),
                                                  p.Z() + d1u.Z() * (u - uc) + d1v.Z() * (v - vc)))
        tol = float(f.get("tolerance") or 0.01)
        fit_s = GeomAPI_PointsToBSplineSurface(pts, 3, 3, GeomAbs_C2, tol).Surface()
        a1, a2, b1, b2 = fit_s.Bounds()
        out = Shape.cast(BRepBuilderAPI_MakeFace(fit_s, a1, a2, b1, b2, 1e-6).Face())
    out._kind = "%s extended by %g mm on %s" % (name.replace("Geom_", ""), dist, ", ".join(sides))
    return out


def _inside_near(face, p, w, dist):
    """The point a small step from the edge point p along w, projected onto the face's surface, lies inside the
    face (classified in its parameter plane): w points into the face."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface
    from OCP.TopAbs import TopAbs_IN
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt
    to_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    sa = ShapeAnalysis_Surface(BRep_Tool.Surface_s(face.wrapped))
    for k in (0.01, 0.003, 0.03):
        q = p + w * (dist * k)
        uv = sa.ValueOfUV(gp_Pnt(q.X, q.Y, q.Z), 1e-7)
        st = BRepClass_FaceClassifier(to_face(face.wrapped), uv, 1e-7).State()
        if st == TopAbs_IN:
            return True
        q2 = p - w * (dist * k)
        uv2 = sa.ValueOfUV(gp_Pnt(q2.X, q2.Y, q2.Z), 1e-7)
        if BRepClass_FaceClassifier(to_face(face.wrapped), uv2, 1e-7).State() == TopAbs_IN:
            return False
    return face.is_inside(p + w * (dist * 0.01))


def _strip(face, surf, e, dist, n=24, ends=None):
    """Extension strip of face across its boundary edge e by dist (mm), as a face on the surface surf: the edge,
    the edge moved outward along the surface, and two side curves. A closed edge gives the parametric band.
    ends: [outer corner point at the start of the edge or None, at the end or None] (strip_corners): the outer
    curve ends there instead of perpendicular to the edge, so that the strips of two edges meeting at a corner
    share the mitre and a strip next to an unpicked edge continues that edge."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf, GeomAPI_PointsToBSpline
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.ShapeFix import ShapeFix_Face
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt
    from build123d import Shape, Vector
    try:
        from OCP.TColgp import TColgp_Array1OfPnt as Arr1
    except ImportError:
        from OCP.collections import Array1_gp_Pnt as Arr1

    def proj(x):
        pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(x.X, x.Y, x.Z), surf)
        if pr.NbPoints() == 0:
            raise ValueError("the extension leaves the surface")
        q = pr.NearestPoint()
        return Vector(q.X(), q.Y(), q.Z())

    # the outward side decided once, at the middle of the edge (classifying near the ends is ambiguous)
    pm, tm = e.position_at(0.5), e.tangent_at(0.5)
    sgn = -1.0 if _inside_near(face, pm, face.normal_at(pm).cross(tm).normalized(), dist) else 1.0
    P, Q = [], []
    for i in range(n + 1):
        t = i / n
        p, tg = e.position_at(t), e.tangent_at(t)
        nrm = face.normal_at(p)
        w = nrm.cross(tg).normalized() * sgn
        P.append(p)
        step = dist
        qv = p
        for _ in range(4):
            qv = proj(p + w * step)
            got = (qv - p).length
            if got < 1e-12 or abs(got - dist) < 1e-6 * max(1.0, dist):
                break
            step *= dist / got
        Q.append(qv)

    def side(p, q, m=8):
        # the end points exactly at p and q (the vertices of the strip)
        return [p] + [proj(p + (q - p) * (i / m)) for i in range(1, m)] + [q]

    # the distance measured along the surface (projected side polyline) is made equal to dist
    s0 = side(P[0], Q[0])
    sl = sum((a - b).length for a, b in zip(s0[1:], s0[:-1]))
    if sl > 1e-9 and abs(sl - dist) > 1e-6 * max(1.0, dist):
        k = dist / sl
        Q = [proj(p + (q - p) * k) for p, q in zip(P, Q)]
    # mitred corners: the outer curve is skewed along the edge so that it ends at the given corner points
    if ends and not e.is_closed and (ends[0] is not None or ends[1] is not None):
        # the picked edge runs from the end nearer P[0]
        e0, e1 = ends
        if e0 is not None and e1 is not None and (e0 - P[0]).length > (e1 - P[0]).length:
            e0, e1 = e1, e0
        c0 = (e0 - Q[0]) if e0 is not None else Vector(0, 0, 0)
        c1 = (e1 - Q[-1]) if e1 is not None else Vector(0, 0, 0)
        Q = [proj(q + c0 * (1 - i / n) + c1 * (i / n)) for i, q in enumerate(Q)]
        if e0 is not None:
            Q[0] = e0
        if e1 is not None:
            Q[-1] = e1
    if e.is_closed:
        us, vs = [], []
        for x in P + Q:
            pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(x.X, x.Y, x.Z), surf)
            u, v = pr.LowerDistanceParameters()
            us.append(u)
            vs.append(v)
        u1, u2, v1, v2 = min(us), max(us), min(vs), max(vs)
        if surf.IsUPeriodic() and (u2 - u1) > 0.5 * surf.UPeriod():
            u1, u2 = 0.0, surf.UPeriod()
        if surf.IsVPeriodic() and (v2 - v1) > 0.5 * surf.VPeriod():
            v1, v2 = 0.0, surf.VPeriod()
        return Shape.cast(BRepBuilderAPI_MakeFace(surf, u1, u2, v1, v2, 1e-6).Face())

    def bspl(pts):
        a = Arr1(1, len(pts))
        for i, p in enumerate(pts):
            a.SetValue(i + 1, gp_Pnt(p.X, p.Y, p.Z))
        return GeomAPI_PointsToBSpline(a, 3, 8, GeomAbs_C2, 1e-5).Curve()

    # the strip edges share the vertices: the ends of the picked edge and two new vertices at the outer corners
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.TopExp import TopExp
    from OCP.BRep import BRep_Tool as BT
    va, vb = TopExp.FirstVertex_s(e.wrapped), TopExp.LastVertex_s(e.wrapped)
    pt = lambda v: Vector(*[getattr(BT.Pnt_s(v), k)() for k in ("X", "Y", "Z")])
    if (pt(va) - P[0]).length > (pt(vb) - P[0]).length:
        va, vb = vb, va
    P[0], P[-1] = pt(va), pt(vb)
    vq0 = BRepBuilderAPI_MakeVertex(gp_Pnt(Q[0].X, Q[0].Y, Q[0].Z)).Vertex()
    vq1 = BRepBuilderAPI_MakeVertex(gp_Pnt(Q[-1].X, Q[-1].Y, Q[-1].Z)).Vertex()

    def edge(pts, v1, v2):
        mk = BRepBuilderAPI_MakeEdge(bspl(pts), v1, v2)
        if not mk.IsDone():
            raise ValueError("the extension strip is not closed")
        return mk.Edge()
    outer = edge(Q, vq0, vq1)
    s1 = edge(side(P[-1], Q[-1]), vb, vq1)
    s2 = edge(side(Q[0], P[0]), vq0, va)
    mw = BRepBuilderAPI_MakeWire()
    for x in (e.wrapped, s1, outer, s2):
        mw.Add(x)
    if not mw.IsDone():
        raise ValueError("the extension strip is not closed")

    def make(w):
        mf = BRepBuilderAPI_MakeFace(surf, w, True)
        fx = ShapeFix_Face(mf.Face())
        fx.Perform()
        return Shape.cast(fx.Face())

    out = make(mw.Wire())
    if out.area < 0 or not BRepCheck_Analyzer(out.wrapped).IsValid():
        out2 = make(TopoDS.Wire(mw.Wire().Reversed()))
        if out2.area > 0:
            out = out2
    if out.area <= 0:
        raise ValueError("the extension strip could not be built")
    # the strip runs along the picked edge the other way round than the face does (consistent orientation: the
    # sewn face and strip keep their normals and merge)
    if _edge_sense(out, e) == _edge_sense(face, e):
        out2 = make(TopoDS.Wire(mw.Wire().Reversed()))
        if out2.area > 0 and BRepCheck_Analyzer(out2.wrapped).IsValid() and _edge_sense(out2, e) != _edge_sense(face, e):
            out = out2
        else:
            out = Shape.cast(out.wrapped.Reversed())
    return out


def _edge_sense(face, e):
    """The direction in which a face runs along its edge e (the edge orientation in the face, with the face's own
    orientation applied): True forward."""
    from OCP.TopAbs import TopAbs_REVERSED
    for x in face.edges():
        if x.wrapped.IsSame(e.wrapped):
            fwd = x.wrapped.Orientation() != TopAbs_REVERSED
            return fwd != (face.wrapped.Orientation() == TopAbs_REVERSED)
    return None


def _face_on_surface(face, surf):
    """The face rebuilt on another surface (one that holds it, such as its surface extended): the same wires, the
    edge curves on the new surface added (ShapeFix_Face, SameParameter), the normal on the side of the old face."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepLib import BRepLib
    from OCP.BRepTools import BRepTools
    from OCP.ShapeFix import ShapeFix_Face
    from OCP.TopoDS import TopoDS
    from build123d import Shape
    to_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    to_wire = getattr(TopoDS, "Wire_s", None) or TopoDS.Wire
    F = to_face(face.wrapped)
    outer = BRepTools.OuterWire_s(F)
    inner = [w.wrapped for w in face.wires() if not w.wrapped.IsSame(outer)]
    nf = None
    # the edges get their curves on the new surface in the first pass; the second builds on them
    for attempt in range(3):
        for wire in (outer, to_wire(outer.Reversed())):
            mk = BRepBuilderAPI_MakeFace(surf, wire, True)
            if not mk.IsDone():
                continue
            for w in inner:
                mk.Add(to_wire(w))
            fx = ShapeFix_Face(mk.Face())
            fx.Perform()
            cand = fx.Face()
            BRepLib.SameParameter_s(cand, 1e-5, True)
            c = Shape.cast(cand)
            if c.area > 0 and BRepCheck_Analyzer(cand).IsValid() and abs(c.area - face.area) <= 1e-3 * max(face.area, 1e-6):
                nf = c
                break
        if nf is not None:
            break
    if nf is None:
        raise ValueError("the face cannot be rebuilt on the extended surface")
    pc = _point_on(face)
    try:
        if face.normal_at(pc).dot(nf.normal_at(pc)) < 0:
            nf = Shape.cast(nf.wrapped.Reversed())
    except Exception:  # noqa: BLE001
        pass
    return nf


_DEBUG = False


def _outward_at(face, e, t, dist):
    """Unit direction in the face's tangent plane at the point of edge e at parameter t, perpendicular to the edge
    and pointing out of the face."""
    pm, tm = e.position_at(0.5), e.tangent_at(0.5)
    sgn = -1.0 if _inside_near(face, pm, face.normal_at(pm).cross(tm).normalized(), dist) else 1.0
    p, tg = e.position_at(t), e.tangent_at(t)
    return face.normal_at(p).cross(tg).normalized() * sgn


def strip_corners(face, surf, picked, dist):
    """Outer corner points of the extension strips of the picked boundary edges of face, one per picked edge as
    [start point or None, end point or None]. Where two picked edges share a vertex the corner is the mitre: on
    the bisector of their outward directions, at the distance that keeps both strips dist wide. Where a picked
    edge meets an unpicked boundary edge within 45 deg of the perpendicular the strip's side continues that edge.
    Otherwise None (perpendicular side). Points are projected onto surf."""
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS
    from build123d import Shape, Vector
    to_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face

    def proj(x):
        pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(x.X, x.Y, x.Z), surf)
        if pr.NbPoints() == 0:
            return x
        q = pr.NearestPoint()
        return Vector(q.X(), q.Y(), q.Z())

    def along(v, d, s, m=8):
        # the point s (mm) from v along direction d measured on the surface (the projected straight segment,
        # as the sides of the strips are measured): the step is corrected until the projected length matches
        step = s
        q = proj(v + d * step)
        for _ in range(4):
            pts = [v] + [proj(v + (q - v) * (i / m)) for i in range(1, m)] + [q]
            L = sum((a - b).length for a, b in zip(pts[1:], pts[:-1]))
            if L < 1e-9 or abs(L - s) < 1e-6 * max(1.0, s):
                break
            step *= s / L
            q = proj(v + d * step)
        # a projection that lands far from the intended point (a folded or far extended surface): no corner point
        if (q - v).length > 1.5 * s + 1e-6 or (q - (v + d * step)).length > 0.5 * s + 1e-6:
            return None
        return q
    outer = Shape.cast(BRepTools.OuterWire_s(to_face(face.wrapped))).edges()
    boundary = [b for b in outer if not any(b.wrapped.IsSame(p.wrapped) for p in picked)]
    vtol = 1e-4 * max(1.0, dist) + 1e-6
    gap_tol = max(vtol, 0.5)                      # two picked edges with a short edge between them: one corner
    out = []
    cache = {}
    for e in picked:
        ends = [None, None]
        if e.is_closed:
            out.append(ends)
            continue
        for k, t in ((0, 0.0), (1, 1.0)):
            v = e.position_at(t)
            w = _outward_at(face, e, t, dist)
            # another picked edge at this vertex (or within gap_tol of it, across a short edge): the mitre
            other, best = None, None
            for o in picked:
                if o.wrapped.IsSame(e.wrapped) or o.is_closed:
                    continue
                for to in (0.0, 1.0):
                    d = (o.position_at(to) - v).length
                    if d < gap_tol and (best is None or d < best):
                        other, best = (o, to), d
            if other:
                vo = other[0].position_at(other[1])
                vm = v if best < vtol else (v + vo) * 0.5    # the corner starts between the two vertices
                key = tuple(round(c, 6) for c in (vm.X, vm.Y, vm.Z))
                if key not in cache:
                    wo = _outward_at(face, other[0], other[1], dist)
                    wb = w + wo
                    if wb.length < 1e-9:
                        cache[key] = None
                    else:
                        wb = wb.normalized()
                        cos = max(wb.dot(w), 0.5)         # the mitre length is capped at 2 x dist (sharp corners)
                        corner = along(vm, wb, dist / cos)
                        if best >= vtol and corner is not None:
                            # across a short edge: the corner is where the outer sides of the two strips meet
                            # (each side: the edge's tangent line moved outward by dist), when that lies near the mitre
                            te = e.tangent_at(t) * (1.0 if t > 0.5 else -1.0)
                            to_ = other[0].tangent_at(other[1]) * (1.0 if other[1] > 0.5 else -1.0)
                            p1, p2 = v + w * dist, vo + wo * dist
                            d = te.cross(to_)
                            if d.length > 1e-6:
                                r = p2 - p1
                                a_, b_, c_ = te.dot(te), te.dot(to_), to_.dot(to_)
                                dd, ee = te.dot(r), to_.dot(r)
                                den = a_ * c_ - b_ * b_
                                if abs(den) > 1e-12:
                                    s1 = (dd * c_ - b_ * ee) / den
                                    s2 = (b_ * dd - a_ * ee) / den
                                    q = (p1 + te * s1 + p2 + to_ * s2) * 0.5
                                    if (q - corner).length <= dist:
                                        corner = proj(q)
                        cache[key] = corner
                ends[k] = cache[key]
                continue
            # an unpicked boundary edge at this vertex: the side continues it
            for b in boundary:
                for tb, inward in ((0.0, 1.0), (1.0, -1.0)):
                    if (b.position_at(tb) - v).length < vtol:
                        tn = b.tangent_at(tb) * (-inward)      # direction away from the vertex, continuing b
                        cos = tn.dot(w)
                        # continued only within 45 deg of the perpendicular; a shallower neighbour gives the
                        # perpendicular side (continuing it would make a long spike)
                        if cos > 0.7:
                            ends[k] = along(v, tn, dist / cos)
                        break
                if ends[k] is not None:
                    break
        out.append(ends)
    return out


def _merged_face(owner, surf, strips, picked):
    """One face on surf bounded by the outer wire of owner with each picked edge replaced by the three other edges
    of its strip (the extension made part of the face); the inner wires of owner kept. Raises ValueError."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepLib import BRepLib
    from OCP.BRepTools import BRepTools
    from OCP.ShapeFix import ShapeFix_Face
    from OCP.TopoDS import TopoDS
    from build123d import Shape, Edge
    to_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    to_wire = getattr(TopoDS, "Wire_s", None) or TopoDS.Wire
    to_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    outer = BRepTools.OuterWire_s(to_face(owner.wrapped))
    pool = [e for e in Shape.cast(outer).edges() if not any(e.wrapped.IsSame(p.wrapped) for p in picked)]

    def same_span(a, b):
        # the shared side of two mitred strips: the same end points (built from the same corner point)
        a0, a1, b0, b1 = a.position_at(0), a.position_at(1), b.position_at(0), b.position_at(1)
        tol = 1e-5 * max(1.0, a.length)
        return ((a0 - b0).length < tol and (a1 - b1).length < tol) or ((a0 - b1).length < tol and (a1 - b0).length < tol)
    added = []
    for st, p in zip(strips, picked):
        for e in st.edges():
            if e.wrapped.IsSame(p.wrapped):
                continue
            # the side shared by two mitred strips lies inside the merged face: neither copy is in the boundary
            twin = next((x for x in added if abs(x.length - e.length) < 1e-5 * max(1.0, e.length) and same_span(e, x)), None)
            if twin is not None:
                added.remove(twin)
                continue
            added.append(e)
    pool += added
    mw = BRepBuilderAPI_MakeWire()
    left = list(pool)
    mw.Add(to_edge(left.pop(0).wrapped))
    guard = 0
    while left and guard < 10 * len(pool):
        guard += 1
        e = left.pop(0)
        mw.Add(to_edge(e.wrapped))
        if not mw.IsDone():
            left.append(e)                 # not connected yet
            mw = _rebuild_wire(mw, pool, left)
    if left or not mw.IsDone():
        raise ValueError("the extended boundary is not one closed wire")
    wire = mw.Wire()
    inner = [w.wrapped for w in owner.wires() if not w.wrapped.IsSame(outer)]
    for attempt in range(3):
        for wr in (wire, to_wire(wire.Reversed())):
            mk = BRepBuilderAPI_MakeFace(surf, wr, True)
            if not mk.IsDone():
                continue
            for w in inner:
                mk.Add(to_wire(w))
            fx = ShapeFix_Face(mk.Face())
            fx.Perform()
            cand = fx.Face()
            BRepLib.SameParameter_s(cand, 1e-5, True)
            c = Shape.cast(cand)
            want = owner.area + sum(st.area for st in strips)
            if _DEBUG:
                print("merged face attempt", attempt, c.area, want, BRepCheck_Analyzer(cand).IsValid())
            if c.area > 0 and BRepCheck_Analyzer(cand).IsValid() and abs(c.area - want) <= 2e-3 * max(want, 1e-6):
                pc = _point_on(owner)
                try:
                    if owner.normal_at(pc).dot(c.normal_at(pc)) < 0:
                        c = Shape.cast(c.wrapped.Reversed())
                except Exception:  # noqa: BLE001
                    pass
                return c
    raise ValueError("the extended face could not be built")


def _rebuild_wire(mw, pool, left):
    """A wire maker with the connected edges of pool so far (MakeWire keeps no state after a failed Add)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
    from OCP.TopoDS import TopoDS
    to_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    used = [e for e in pool if not any(e.wrapped.IsSame(x.wrapped) for x in left)]
    m = BRepBuilderAPI_MakeWire()
    for e in used:
        m.Add(to_edge(e.wrapped))
    return m


def _natural_extension(owner, es, dist):
    """The face extended across its picked edges when it is an untrimmed patch (its boundary is the four iso-curves
    of its parameter range) and the picked edges are sides of it: one face on the surface converted to a B-spline
    and lengthened at those sides (GeomLib.ExtendSurfByLength, curvature continuous; the surface inside unchanged).
    None otherwise."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepTools import BRepTools
    from OCP.Geom import Geom_RectangularTrimmedSurface
    from OCP.GeomConvert import GeomConvert
    from OCP.GeomLib import GeomLib
    from build123d import Shape, Vector
    try:
        surf = BRep_Tool.Surface_s(owner.wrapped)
        u1, u2, v1, v2 = BRepTools.UVBounds_s(owner.wrapped)
        patch = Shape.cast(BRepBuilderAPI_MakeFace(surf, u1, u2, v1, v2, 1e-6).Face())
        if abs(patch.area - owner.area) > 1e-6 * max(owner.area, 1e-9) or len(owner.wires()) != 1:
            return None
        um, vm = (u1 + u2) / 2, (v1 + v2) / 2
        side_pts = {(True, False): surf.Value(u1, vm), (True, True): surf.Value(u2, vm),
                    (False, False): surf.Value(um, v1), (False, True): surf.Value(um, v2)}
        sides = []
        for e in es:
            m = e.position_at(0.5)
            key = min(side_pts, key=lambda k: (Vector(side_pts[k].X(), side_pts[k].Y(), side_pts[k].Z()) - m).length)
            q = side_pts[key]
            if (Vector(q.X(), q.Y(), q.Z()) - m).length > 1e-4 * max(1.0, owner.bounding_box().diagonal):
                return None                     # not a side of the patch
            sides.append(key)
        out = _extend_patch(surf, (u1, u2, v1, v2), dist, set(sides))
        if out is None:
            return None
        c = _point_on(owner)
        if owner.normal_at(c).dot(out.normal_at(c)) < 0:
            out = Shape.cast(out.wrapped.Reversed())
        return out
    except Exception as ex:  # noqa: BLE001
        if _DEBUG:
            import traceback
            traceback.print_exc()
        return None


def _same_edge(face, e):
    """The edge of face that is e (the same edge, else the one with the nearest middle)."""
    for x in face.edges():
        if x.wrapped.IsSame(e.wrapped):
            return x
    m = e.position_at(0.5)
    return min(face.edges(), key=lambda x: (x.position_at(0.5) - m).length)


def untrimmed_extended(face, dist, tol=0.01):
    """The surface of a face as an untrimmed patch extended by dist (mm) beyond all sides (a trimming tool that does
    not quite reach across the target)."""
    return extend(None, {"_f": face}, {"source": "_f", "distance": dist, "sides": "all", "tolerance": tol}, None)


def extend_face(face, es, dist, tol=0.01, single=True):
    """One face extended across its edges es by dist (mm): the extension part of the face (see extend_edges);
    a shell of the face and its strips when the face cannot be rebuilt."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
    from .occfix import CheckedUnify as ShapeUpgrade_UnifySameDomain
    from build123d import Shape
    surf = BRep_Tool.Surface_s(face.wrapped)
    name = surf.DynamicType().Name()
    analytic = name in ("Geom_Plane", "Geom_CylindricalSurface", "Geom_ConicalSurface", "Geom_SphericalSurface", "Geom_ToroidalSurface")
    if not analytic:
        surf = _extended_surface(face, dist * 1.5, tol)
        if single:
            nat = _natural_extension(face, es, dist)
            if nat is not None:
                return nat
    corners = strip_corners(face, surf, es, dist)
    strips = [_strip(face, surf, e, dist, ends=c) for e, c in zip(es, corners)]
    try:
        return _merged_face(face, surf, strips, es)
    except ValueError:
        pass
    base = face
    if not analytic:
        try:
            base = _face_on_surface(face, surf)
        except ValueError:
            base = face
    sew = BRepBuilderAPI_Sewing(1e-5)
    sew.Add(base.wrapped)
    for st in strips:
        sew.Add(st.wrapped)
    sew.Perform()
    u = ShapeUpgrade_UnifySameDomain(sew.SewedShape(), True, True, False)
    u.Build()
    return Shape.cast(u.Shape())


def _keep_side(piece_src, tools, mark):
    """The pieces of piece_src split by the tool shapes that hold the point mark (or are nearest to it)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    from build123d import Shape
    args, tl = _shape_list(), _shape_list()
    for fc in piece_src.faces():
        args.Append(fc.wrapped)
    for t in tools:
        tl.Append(t)
    op = BRepAlgoAPI_Splitter()
    op.SetArguments(args)
    op.SetTools(tl)
    op.SetUseOBB(True)
    op.Build()
    if not op.IsDone():
        return piece_src
    pieces = list(Shape.cast(op.Shape()).faces())
    if len(pieces) < 2:
        return piece_src
    v = BRepBuilderAPI_MakeVertex(gp_Pnt(mark.X, mark.Y, mark.Z)).Vertex()
    d = [BRepExtrema_DistShapeShape(v, p.wrapped).Value() for p in pieces]
    best = min(d)
    keep = [p for p, x in zip(pieces, d) if x <= best + 1e-6]
    return keep[0] if len(keep) == 1 else _sew(keep)


def offset_joined(body, d, angle=1.0):
    """Offset of a shell face by face, joined at the sharp edges: each face offset on its own (its exact offset
    surface), then at each edge where the faces meet at more than angle (deg) both offset faces are extended across
    that edge and cut where they meet (the intersection join); the faces sewn. Returns the shell or raises
    ValueError."""
    import math as _m
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_Sewing
    from OCP.BRepOffset import BRepOffset_MakeSimpleOffset
    from build123d import Shape
    faces = list(body.faces())
    offs = []
    for fc in faces:
        op = BRepOffset_MakeSimpleOffset(BRepBuilderAPI_Copy(fc.wrapped, True, False).Shape(), d)
        op.SetBuildSolidFlag(False)
        op.Perform()
        if not op.IsDone():
            raise ValueError("a face could not be offset")
        o = Shape.cast(op.GetResultShape()).faces()
        if len(o) != 1:
            raise ValueError("a face could not be offset")
        offs.append(o[0])
    # sharp edges between faces: (i, j, edge)
    sharp = []
    edges = [fc.edges() for fc in faces]
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            for e in edges[i]:
                if any(e.wrapped.IsSame(x.wrapped) for x in edges[j]):
                    p = e.position_at(0.5)
                    a, b = faces[i].normal_at(p), faces[j].normal_at(p)
                    if a.dot(b) < _m.cos(_m.radians(angle)):
                        sharp.append((i, j, e))
    if not sharp:
        return None
    L = 4.0 * abs(d) + 1.0

    def image(k, e):
        # the edge of offset face k that is the offset of the source edge e
        p = e.position_at(0.5)
        q = p + faces[k].normal_at(p) * d
        return min(offs[k].edges(), key=lambda x: (x.position_at(0.5) - q).length)
    by_face = {}
    for i, j, e in sharp:
        by_face.setdefault(i, []).append((j, e))
        by_face.setdefault(j, []).append((i, e))
    ext = {}
    for k, lst in by_face.items():
        es = [image(k, e) for _, e in lst]
        ext[k] = extend_face(offs[k], es, L, 0.01, single=False)
    tool_of = {}
    out = []
    for k in range(len(faces)):
        if k not in by_face:
            out.append(offs[k])
            continue
        cur = ext[k]
        mark = _point_on(offs[k])
        for j, e in by_face[k]:
            if j not in tool_of:
                tool_of[j] = [untrimmed_extended(fc, 2 * L).wrapped for fc in ext[j].faces()]
            cur = _keep_side(cur, tool_of[j], mark)
        out += list(cur.faces())
    sew = BRepBuilderAPI_Sewing(max(1e-4, 1e-3 * abs(d)))
    for fc in out:
        sew.Add(fc.wrapped)
    sew.Perform()
    res = Shape.cast(sew.SewedShape())
    if not res.faces():
        raise ValueError("the joined offset failed")
    return res


def extend_edges(shape, bodies, f, find_edges, find_faces):
    """Extend a surface body across selected boundary edges ("edges": edge keys) by "distance" (mm), or up to
    another surface body ("mode": "upto", "target": body id; the extension is cut where it meets that surface, the
    target extended beyond its own edges when it is too small). The trim of the surface (holes, other edges) is
    kept. The extension is part of the face it extends: an analytic surface is extended on itself; a B-spline face
    is rebuilt on its surface extended beyond its sides (GeomLib, curvature continuous) and the strip lies on that
    same surface, so the face and the strip merge into one face."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from .occfix import CheckedUnify as ShapeUpgrade_UnifySameDomain
    from build123d import Shape
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    src = source_body(shape, bodies, f, find_faces)
    # a copy: the edge curves on the extended surfaces are added to the edges in place (the body is cached)
    src = Shape.cast(BRepBuilderAPI_Copy(src.wrapped, True, False).Shape())
    edges = find_edges(src, f.get("edges") or [])
    if not edges:
        raise ValueError("no edges of the surface selected")
    tol = float(f.get("tolerance") or 0.01)
    upto = f.get("mode") == "upto"
    target = None
    if upto:
        target = bodies.get(f.get("target"))
        if target is None or not target.faces():
            raise ValueError("choose the surface to extend up to")
        far = max(BRepExtrema_DistShapeShape(e.wrapped, target.wrapped).Value() for e in edges)
        bb = src.bounding_box()
        dist = max(3.0 * far + 2.0, 0.5 * bb.diagonal)
    else:
        dist = float(f.get("distance") or 5.0)
    faces = list(src.faces())
    by_owner = {}
    for e in edges:
        k = next((i for i, fc in enumerate(faces) if any(x.wrapped.IsSame(e.wrapped) for x in fc.edges())), None)
        if k is None:
            raise ValueError("an edge does not belong to the surface")
        by_owner.setdefault(k, []).append(e)
    strips, kinds, merged = [], set(), True
    for k, es in by_owner.items():
        owner = faces[k]
        surf = BRep_Tool.Surface_s(owner.wrapped)
        name = surf.DynamicType().Name()
        kinds.add(name.replace("Geom_", ""))
        analytic = name in ("Geom_Plane", "Geom_CylindricalSurface", "Geom_ConicalSurface", "Geom_SphericalSurface", "Geom_ToroidalSurface")
        if not analytic:
            surf = _extended_surface(owner, dist * 1.5, tol)
        # the strips first (their edge curves on the extended surface), then one face on that surface bounded by the
        # face's boundary with the strips added; when that fails, the face and its strips are sewn (and merged where
        # they share a surface)
        nat = _natural_extension(owner, es, dist) if not analytic and len(faces) == 1 else None
        if nat is not None:
            faces[k] = nat
            continue
        corners = strip_corners(owner, surf, es, dist)
        mine = [_strip(owner, surf, e, dist, ends=c) for e, c in zip(es, corners)]
        try:
            faces[k] = _merged_face(owner, surf, mine, es)
        except ValueError:
            strips += mine
            if not analytic:
                try:
                    faces[k] = _face_on_surface(owner, surf)
                except ValueError:
                    merged = False
    sew = BRepBuilderAPI_Sewing(1e-5)
    for fc in faces:
        sew.Add(fc.wrapped)
    for st in strips:
        sew.Add(st.wrapped)
    sew.Perform()
    u = ShapeUpgrade_UnifySameDomain(sew.SewedShape(), True, True, False)
    u.Build()
    out = Shape.cast(u.Shape())
    if upto:
        out = _cut_at(out, target, src, dist, tol)
        out._kind = "%s extended across %d edge(s) up to the surface" % (", ".join(sorted(kinds)), len(edges))
    else:
        out._kind = "%s extended by %g mm across %d edge(s)" % (", ".join(sorted(kinds)), dist, len(edges))
    if not merged:
        out._kind += " (the extension is a separate face: the face could not be rebuilt on the extended surface)"
    return out


def _cut_at(ext, target, src, dist, tol):
    """The extended surface ext cut where it meets the target surface body: the pieces that hold the surface before
    the extension are kept. The target is extended beyond its own edges when the cut does not separate the
    extension."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from build123d import Shape
    marks = [_point_on(fc) for fc in src.faces()]

    def split(tools):
        args, tl = _shape_list(), _shape_list()
        for fc in ext.faces():
            args.Append(fc.wrapped)
        for t in tools:
            tl.Append(t)
        op = BRepAlgoAPI_Splitter()
        op.SetArguments(args)
        op.SetTools(tl)
        op.SetUseOBB(True)
        op.Build()
        if not op.IsDone():
            return None
        pieces = list(Shape.cast(op.Shape()).faces())
        keep = []
        for p in pieces:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
            from OCP.gp import gp_Pnt
            if any(BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(m.X, m.Y, m.Z)).Vertex(), p.wrapped).Value() < 1e-4 for m in marks):
                keep.append(p)
        if not keep or len(keep) == len(pieces):
            return None
        return keep
    keep = split([fc.wrapped for fc in target.faces()])
    if keep is None:
        keep = split([untrimmed_extended(fc, dist * 2, tol).wrapped for fc in target.faces()])
    if keep is None:
        raise ValueError("the extension does not reach the surface (within %.3g mm)" % dist)
    return keep[0] if len(keep) == 1 else _sew(keep)


def _extended_surface(face, dist, tol):
    """The surface of a face as a B-spline surface extended by dist (mm) beyond the four sides of the face's
    parameter range (GeomLib.ExtendSurfByLength, curvature continuous; the surface inside is unchanged); when that
    fails, the surface re-fitted with a tangent extrapolation."""
    try:
        return _extended_bspline(face, dist)
    except Exception:
        return _refit_extended_surface(face, dist, tol)


def _extend_patch(surf, bounds, dist, sides):
    """The patch of surf over bounds (u1, u2, v1, v2) as a B-spline face lengthened by dist (mm) at the sides
    {(in_u, after)} (BRepLib.ExtendFace: curvature continuous, the surface inside unchanged), or None."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepLib import BRepLib
    from OCP.Geom import Geom_RectangularTrimmedSurface
    from OCP.GeomConvert import GeomConvert
    from OCP.TopoDS import TopoDS_Face
    from build123d import Shape
    u1, u2, v1, v2 = bounds
    bs = GeomConvert.SurfaceToBSplineSurface_s(Geom_RectangularTrimmedSurface(surf, u1, u2, v1, v2))
    a1, a2, b1, b2 = bs.Bounds()
    F = BRepBuilderAPI_MakeFace(bs, a1, a2, b1, b2, 1e-6).Face()
    out = TopoDS_Face()
    BRepLib.ExtendFace_s(F, dist, (True, False) in sides, (True, True) in sides, (False, False) in sides, (False, True) in sides, out)
    if out.IsNull():
        return None
    r = Shape.cast(out)
    return r if r.area > Shape.cast(F).area else None


def _extended_bspline(face, dist):
    """The surface of a face as a B-spline surface lengthened by dist (mm) beyond the four sides of its parameter
    range (BRepLib.ExtendFace)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools
    surf = BRep_Tool.Surface_s(face.wrapped)
    r = _extend_patch(surf, BRepTools.UVBounds_s(face.wrapped), dist, {(True, False), (True, True), (False, False), (False, True)})
    if r is None:
        raise ValueError("the surface cannot be extended")
    return BRep_Tool.Surface_s(r.wrapped)


def _refit_extended_surface(face, dist, tol):
    """The B-spline surface of a face re-fitted with a tangent extrapolation by dist (mm) beyond all four sides."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.Precision import Precision
    try:
        from OCP.TColgp import TColgp_Array2OfPnt as Arr
    except ImportError:
        from OCP.collections import Array2_gp_Pnt as Arr
    surf = BRep_Tool.Surface_s(face.wrapped)
    u1, u2, v1, v2 = BRepTools.UVBounds_s(face.wrapped)

    def dlen(u, v, du, dv):
        p, d1u, d1v = gp_Pnt(), gp_Vec(), gp_Vec()
        surf.D1(u, v, p, d1u, d1v)
        return math.sqrt((d1u.X() * du + d1v.X() * dv) ** 2 + (d1u.Y() * du + d1v.Y() * dv) ** 2 + (d1u.Z() * du + d1v.Z() * dv) ** 2)
    um, vm = (u1 + u2) / 2, (v1 + v2) / 2
    inc = lambda s_: dist / s_ if s_ > 1e-12 else 0.0
    nu1, nu2 = u1 - inc(dlen(u1, vm, 1, 0)), u2 + inc(dlen(u2, vm, 1, 0))
    nv1, nv2 = v1 - inc(dlen(um, v1, 0, 1)), v2 + inc(dlen(um, v2, 0, 1))
    n = 25
    su1, su2, sv1, sv2 = surf.Bounds()
    inf = Precision.Infinite_s() / 2
    cu1, cu2 = max(u1, su1) if abs(su1) < inf else u1, min(u2, su2) if abs(su2) < inf else u2
    cv1, cv2 = max(v1, sv1) if abs(sv1) < inf else v1, min(v2, sv2) if abs(sv2) < inf else v2
    pts = Arr(1, n, 1, n)
    for i in range(n):
        u = nu1 + (nu2 - nu1) * i / (n - 1)
        for j in range(n):
            v = nv1 + (nv2 - nv1) * j / (n - 1)
            uc, vc = min(max(u, cu1), cu2), min(max(v, cv1), cv2)
            p, d1u, d1v = gp_Pnt(), gp_Vec(), gp_Vec()
            surf.D1(uc, vc, p, d1u, d1v)
            pts.SetValue(i + 1, j + 1, gp_Pnt(p.X() + d1u.X() * (u - uc) + d1v.X() * (v - vc),
                                              p.Y() + d1u.Y() * (u - uc) + d1v.Y() * (v - vc),
                                              p.Z() + d1u.Z() * (u - uc) + d1v.Z() * (v - vc)))
    return GeomAPI_PointsToBSplineSurface(pts, 3, 3, GeomAbs_C2, tol).Surface()


# --------------------------------------------------------------------------- inspection

def _edge_polyline(edge, n=16):
    pts = []
    for i in range(n + 1):
        try:
            q = edge.position_at(i / float(n))
        except Exception:
            q = edge.start_point() if i == 0 else edge.end_point()
        pts.append([round(q.X, 5), round(q.Y, 5), round(q.Z, 5)])
    return pts


def _dist_to_edge(p, edge, n=24):
    """Smallest distance from the point p (Vector) to sampled points of the edge."""
    best = float("inf")
    for i in range(n + 1):
        q = edge.position_at(i / float(n))
        best = min(best, (q - p).length)
    return best


def inspect(body, gap_tol=0.1, min_area=0.01, min_edge=0.01):
    """Topology report of a body (shell or solid): free edges, gaps between free edges, non-manifold edges, small
    faces and edges, validity. Returns {"summary": {...}, "issues": [{"kind", "text", "pts", "p", "value"}]}."""
    from OCP.TopExp import TopExp
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as AncestorMap
    from OCP.BRepCheck import BRepCheck_Analyzer
    issues = []
    if body is None:
        return {"summary": {}, "issues": issues}
    amap = AncestorMap()
    TopExp.MapShapesAndAncestors_s(body.wrapped, TopAbs_EDGE, TopAbs_FACE, amap)
    free, nonman = [], []
    all_edges = body.edges()
    faces = body.faces()
    for e in all_edges:
        try:
            idx = amap.FindIndex(e.wrapped)
            n = amap.FindFromIndex(idx).Size() if idx > 0 else 0
        except Exception:
            n = 0
        if n == 1:
            free.append(e)
        elif n > 2:
            nonman.append((e, n))
    total_free = sum(e.length for e in free)
    # a part of several cells (solids that share faces, after Partition or an import): an edge with more than two
    # faces in the whole part but at most two in each solid is where cells meet, not a non-manifold edge of a solid
    cell_edges = []
    sols = list(body.solids()) if hasattr(body, "solids") else []
    if len(sols) > 1 and nonman:
        smaps = []
        for so in sols:
            m = AncestorMap()
            TopExp.MapShapesAndAncestors_s(so.wrapped, TopAbs_EDGE, TopAbs_FACE, m)
            smaps.append(m)

        def per_solid(e):
            out = []
            for m in smaps:
                try:
                    i = m.FindIndex(e.wrapped)
                    out.append(m.FindFromIndex(i).Size() if i > 0 else 0)
                except Exception:
                    out.append(0)
            return out
        keep = []
        for e, n in nonman:
            ns = per_solid(e)
            if max(ns) <= 2:
                cell_edges.append((e, sum(1 for k in ns if k)))
            else:
                keep.append((e, n))
        nonman = keep
    for e, k in cell_edges:
        q = e.position_at(0.5)
        issues.append({"kind": "celledge", "text": "Edge where %d cells meet, length %.3f mm" % (k, e.length),
                       "pts": _edge_polyline(e), "p": [q.X, q.Y, q.Z], "value": e.length})
    for e, n in nonman:
        q = e.position_at(0.5)
        issues.append({"kind": "nonmanifold", "text": "Non-manifold edge shared by %d faces, length %.3f mm" % (n, e.length),
                       "pts": _edge_polyline(e), "p": [q.X, q.Y, q.Z], "value": e.length})
    # gaps: a free edge whose both ends lie within gap_tol of another free edge (a seam that did not sew)
    seams = set()
    for i, a in enumerate(free):
        pa, pb = a.start_point(), a.end_point()
        for j, b in enumerate(free):
            if i == j or (j, i) in seams:
                continue
            da, db = _dist_to_edge(pa, b), _dist_to_edge(pb, b)
            if da <= gap_tol and db <= gap_tol and abs(a.length - b.length) <= max(gap_tol * 4, 0.5 * max(a.length, b.length)):
                # width along the seam
                w = 0.0
                for k in range(9):
                    w = max(w, _dist_to_edge(a.position_at(k / 8.0), b))
                if w > 1e-9:
                    seams.add((i, j))
                    q = a.position_at(0.5)
                    issues.append({"kind": "gap", "text": "Gap %.4f mm between two free edges (length %.2f mm)" % (w, a.length),
                                   "pts": _edge_polyline(a) + _edge_polyline(b)[::-1], "p": [q.X, q.Y, q.Z], "value": w})
    seam_edges = set(i for i, j in seams) | set(j for i, j in seams)
    seam_ends = [q for i in seam_edges for q in (free[i].start_point(), free[i].end_point())]
    at_seam = lambda p: any((p - q).length < 1e-6 for q in seam_ends)
    # free edge vertices close to another free edge vertex but not shared (a point gap), one report per position pair
    verts = []
    for i, e in enumerate(free):
        for q in (e.start_point(), e.end_point()):
            verts.append((i, q))
    seen_pairs = set()
    for n1 in range(len(verts)):
        for n2 in range(n1 + 1, len(verts)):
            i, p = verts[n1]
            j, q = verts[n2]
            if i == j:
                continue
            d = (p - q).length
            if 1e-7 < d <= gap_tol:
                if at_seam(p) and at_seam(q):
                    continue
                key = tuple(sorted([tuple(round(v, 4) for v in (p.X, p.Y, p.Z)), tuple(round(v, 4) for v in (q.X, q.Y, q.Z))]))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                m = (p + q) * 0.5
                issues.append({"kind": "pointgap", "text": "Vertex gap %.4f mm between free edges" % d,
                               "pts": [[p.X, p.Y, p.Z], [q.X, q.Y, q.Z]], "p": [m.X, m.Y, m.Z], "value": d})
    # remaining free edges (open boundary)
    for i, e in enumerate(free):
        if i in seam_edges:
            continue
        q = e.position_at(0.5)
        issues.append({"kind": "free", "text": "Free edge, length %.3f mm" % e.length, "pts": _edge_polyline(e), "p": [q.X, q.Y, q.Z], "value": e.length})
    for f in faces:
        if f.area < min_area:
            c = f.center()
            issues.append({"kind": "smallface", "text": "Small face, area %.5f mm^2" % f.area, "pts": [[round(v.X, 5), round(v.Y, 5), round(v.Z, 5)] for v in [e.position_at(0.0) for e in f.edges()]] + [[c.X, c.Y, c.Z]], "p": [c.X, c.Y, c.Z], "value": f.area, "face": True})
    for e in all_edges:
        if e.length < min_edge:
            q = e.position_at(0.5)
            issues.append({"kind": "smalledge", "text": "Short edge, length %.5f mm" % e.length, "pts": _edge_polyline(e, 2), "p": [q.X, q.Y, q.Z], "value": e.length})
    try:
        valid = bool(BRepCheck_Analyzer(body.wrapped).IsValid())
    except Exception:
        valid = None
    try:
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_SHELL
        from OCP.TopExp import TopExp_Explorer
        closed = []
        ex = TopExp_Explorer(body.wrapped, TopAbs_SHELL)
        while ex.More():
            closed.append(bool(BRep_Tool.IsClosed_s(ex.Current())))
            ex.Next()
    except Exception:
        closed = []
    order = {"gap": 0, "pointgap": 1, "nonmanifold": 2, "free": 3, "smallface": 4, "smalledge": 5, "celledge": 6}
    issues.sort(key=lambda x: (order.get(x["kind"], 9), -x.get("value", 0)))
    summary = {"faces": len(faces), "edges": len(all_edges), "vertices": len(body.vertices()), "free_edges": len(free),
               "free_length": round(total_free, 3), "area": round(body.area, 3), "valid": valid, "shells": len(closed), "closed_shells": sum(1 for c in closed if c),
               "gaps": sum(1 for x in issues if x["kind"] in ("gap", "pointgap")), "nonmanifold": len(nonman),
               "cells": len(sols), "cell_edges": len(cell_edges)}
    return {"summary": summary, "issues": issues}


# --------------------------------------------------------------------------- surface fillet

def _oriented_surface(face):
    """Geometric surface of a face and the sign that turns its natural normal into the face normal."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_REVERSED
    return BRep_Tool.Surface_s(face.wrapped), (-1.0 if face.wrapped.Orientation() == TopAbs_REVERSED else 1.0)


class _Projector:
    """Projection of points onto one surface: (point, u, v, distance) of the nearest point, or None. The extrema
    data of the surface (the sample grid of a B-spline surface) is built once, in the constructor, and used for
    every point."""

    def __init__(self, surf):
        from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
        self.surf = surf
        self._pr = GeomAPI_ProjectPointOnSurf()
        self._pr.Init(surf, *surf.Bounds(), 1e-7)

    def __call__(self, p):
        from OCP.gp import gp_Pnt
        pr = self._pr
        pr.Perform(gp_Pnt(*p))
        if not pr.NbPoints():
            return None
        q = pr.NearestPoint()
        u, v = pr.LowerDistanceParameters()
        return (q.X(), q.Y(), q.Z()), u, v, pr.LowerDistance()


def _project(surf, p):
    """(point, u, v, distance) of the projection of p onto the surface, or None (one point; _Projector for many)."""
    return _Projector(surf)(p)


def _inside(face, surf, uv, classifier=None):
    """True when the parameters uv lie in the face (periodic surfaces: also shifted by one period). classifier: a
    BRepClass_FaceClassifier reused between calls."""
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    from OCP.gp import gp_Pnt2d
    u, v = uv
    us = [u + k * surf.UPeriod() for k in (-1, 0, 1)] if surf.IsUPeriodic() else [u]
    vs = [v + k * surf.VPeriod() for k in (-1, 0, 1)] if surf.IsVPeriodic() else [v]
    cl = classifier or BRepClass_FaceClassifier()
    for a in us:
        for b in vs:
            cl.Perform(face.wrapped, gp_Pnt2d(a, b), 1e-6)
            if cl.State() in (TopAbs_IN, TopAbs_ON):
                return True
    return False


def _closest_faces(ba, bb):
    """The faces of the two bodies nearest to each other (the first pair in face order when several are at the
    same distance). The face pairs are taken in the order of the distance between their bounding boxes, a lower
    bound of the face distance, and the search stops at the first pair whose boxes are further apart than the
    nearest faces found."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    def boxes(body):
        out = []
        for fc in body.faces():
            b = Bnd_Box()
            BRepBndLib.Add_s(fc.wrapped, b, False)
            out.append((fc, b))
        return out
    fa_, fb_ = boxes(ba), boxes(bb)
    pairs = sorted(((ba_.Distance(bb_), i, j) for i, (_, ba_) in enumerate(fa_) for j, (_, bb_) in enumerate(fb_)),
                   key=lambda x: (x[0], x[1], x[2]))
    best = None
    for lower, i, j in pairs:
        if best is not None and lower > best[0]:
            break
        d = fa_[i][0].distance_to(fb_[j][0])
        if best is None or (d, i, j) < best[:3]:
            best = (d, i, j, fa_[i][0], fb_[j][0])
    return best[3], best[4]


def _default_side(face, other):
    """+1 when the other body lies mostly along the face normal, else -1."""
    c = other.center()
    p = face.center()
    n = face.normal_at(p)
    return 1.0 if (c - p).dot(n) >= 0 else -1.0


def _interp_closed(pts):
    """Periodic cubic B-spline through the points (the first point not repeated)."""
    from OCP.GeomAPI import GeomAPI_Interpolate
    from OCP.gp import gp_Pnt
    try:
        from OCP.TColgp import TColgp_HArray1OfPnt as HArr
    except ImportError:
        from OCP.collections import HArray1_gp_Pnt as HArr
    a = HArr(1, len(pts))
    for i, p in enumerate(pts):
        a.SetValue(i + 1, gp_Pnt(*p))
    it = GeomAPI_Interpolate(a, True, 1e-7)
    it.Perform()
    if not it.IsDone():
        raise ValueError("closed fillet curve failed")
    return it.Curve()


def _interp(pts):
    from OCP.GeomAPI import GeomAPI_PointsToBSpline
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.gp import gp_Pnt
    try:
        from OCP.TColgp import TColgp_Array1OfPnt as Arr
    except ImportError:
        from OCP.collections import Array1_gp_Pnt as Arr
    a = Arr(1, len(pts))
    for i, p in enumerate(pts):
        a.SetValue(i + 1, gp_Pnt(*p))
    return GeomAPI_PointsToBSpline(a, 3, 8, GeomAbs_C2, 1e-6).Curve()


def fillet_faces(fa, fb, r, sa, sb, n=48):
    """Rolling-ball fillet of radius r between the faces fa and fb, the ball on side sa of fa and sb of fb
    (+1 along the face normal). Returns (fillet face, contact curve on fa, contact curve on fb) as build123d
    shapes; the spine is the intersection of the two offset surfaces, the fillet a pipe of radius r along it
    between the contact curves."""
    from OCP.Geom import Geom_OffsetSurface
    from OCP.GeomAPI import GeomAPI_IntSS
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from build123d import Edge
    from OCP.BRepClass import BRepClass_FaceClassifier
    ga, ka = _oriented_surface(fa)
    gb, kb = _oriented_surface(fb)
    oa = Geom_OffsetSurface(ga, sa * ka * r)
    ob = Geom_OffsetSurface(gb, sb * kb * r)
    inter = GeomAPI_IntSS(oa, ob, 1e-7)
    if not inter.IsDone() or inter.NbLines() == 0:
        raise ValueError("the faces have no fillet of radius %g on these sides (the offset surfaces do not meet; "
                         "try Flip or a smaller radius)" % r)
    proj_a, proj_b = _Projector(ga), _Projector(gb)
    cls_a, cls_b = BRepClass_FaceClassifier(), BRepClass_FaceClassifier()
    best = None
    for i in range(1, inter.NbLines() + 1):
        cu = inter.Line(i)
        t0, t1 = cu.FirstParameter(), cu.LastParameter()
        if abs(t0) > 1e50 or abs(t1) > 1e50:
            # an infinite line (two planes): bounded to the size of the faces
            big = 2 * (fa.bounding_box().diagonal + fb.bounding_box().diagonal) + 10
            t0, t1 = max(t0, -big), min(t1, big)
        # the part of the spine whose contact points lie on both faces
        def good(t):
            p = cu.Value(t)
            pa = proj_a((p.X(), p.Y(), p.Z()))
            pb = proj_b((p.X(), p.Y(), p.Z()))
            return (pa is not None and pb is not None and abs(pa[3] - r) < 1e-3 * max(r, 1) + 1e-6 and
                    abs(pb[3] - r) < 1e-3 * max(r, 1) + 1e-6 and _inside(fa, ga, pa[1:3], cls_a) and
                    _inside(fb, gb, pb[1:3], cls_b))
        rows = [(good(t), t, None, None) for t in (t0 + (t1 - t0) * k / n for k in range(n + 1))]
        runs, cur = [], []
        for row in rows:
            if row[0]:
                cur.append(row)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        for run in runs:
            if len(run) >= 2 and (best is None or len(run) > len(best[1])):
                # the ends of the run moved to the face boundaries (bisection to the neighbouring samples)
                i0 = rows.index(run[0])
                i1 = rows.index(run[-1])
                lo, hi = run[0][1], run[-1][1]
                if i0 > 0:
                    a, b = rows[i0 - 1][1], lo
                    for _ in range(40):
                        mid = 0.5 * (a + b)
                        a, b = (a, mid) if good(mid) else (mid, b)
                    lo = b
                if i1 < len(rows) - 1:
                    a, b = hi, rows[i1 + 1][1]
                    for _ in range(40):
                        mid = 0.5 * (a + b)
                        a, b = (mid, b) if good(mid) else (a, mid)
                    hi = a
                best = (cu, run, lo, hi)
    if best is None:
        raise ValueError("the fillet does not touch both faces (radius %g; try Flip or a smaller radius)" % r)
    cu, run, ta, tb = best
    closed = len(run) == n + 1 and cu.IsClosed() and cu.Value(cu.FirstParameter()).Distance(cu.Value(cu.LastParameter())) < 1e-7
    m = max(24, len(run) * 2)
    if closed:
        # a fillet all the way round (a plane and a cylinder, a cone): two halves (no seam edge)
        t0, t1 = cu.FirstParameter(), cu.LastParameter()
        tm = 0.5 * (t0 + t1)
        f1, a1, b1 = _arc_patch(cu, t0, tm, proj_a, proj_b, r, m // 2)
        f2, a2, b2 = _arc_patch(cu, tm, t1, proj_a, proj_b, r, m // 2)
        return [f1, f2], [a1, a2], [b1, b2]
    face, _, _ = _arc_patch(cu, ta, tb, proj_a, proj_b, r, m)
    # trimming curves: the contact curves extended a little beyond the face boundaries
    ext = 0.02 * (tb - ta)
    pts_a, pts_b = [], []
    for k in range(m + 1):
        p = cu.Value(ta - ext + (tb - ta + 2 * ext) * k / m)
        p = (p.X(), p.Y(), p.Z())
        qa, qb = proj_a(p), proj_b(p)
        if qa is None or qb is None:
            continue
        pts_a.append(qa[0])
        pts_b.append(qb[0])
    ea = Edge(BRepBuilderAPI_MakeEdge(_interp(pts_a)).Edge())
    eb = Edge(BRepBuilderAPI_MakeEdge(_interp(pts_b)).Edge())
    return [face], [ea], [eb]


def _arc_patch(cu, ta, tb, proj_a, proj_b, r, m, nu=9):
    """Fillet patch along the spine cu from ta to tb: at each spine point the circular arc of radius r from the
    contact point on surface A to the one on surface B (the shorter arc), fitted with a B-spline surface. proj_a,
    proj_b: _Projector of surface A and of surface B. Returns (face, contact edge A, contact edge B); the contact
    edges are the boundary curves of the face."""
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeEdge
    import numpy as np
    from OCP.gp import gp_Pnt
    from build123d import Face, Edge
    try:
        from OCP.TColgp import TColgp_Array2OfPnt as Arr2
    except ImportError:
        from OCP.collections import Array2_gp_Pnt as Arr2
    pts = Arr2(1, nu, 1, m + 1)
    for k in range(m + 1):
        q = cu.Value(ta + (tb - ta) * k / m)
        P = np.array([q.X(), q.Y(), q.Z()])
        A = np.array(proj_a(tuple(P))[0]) - P
        B = np.array(proj_b(tuple(P))[0]) - P
        th = math.acos(max(-1.0, min(1.0, float(A @ B) / (np.linalg.norm(A) * np.linalg.norm(B)))))
        for j in range(nu):
            s = j / (nu - 1)
            if th < 1e-9:
                X = P + A
            else:
                X = P + (math.sin((1 - s) * th) * A + math.sin(s * th) * B) / math.sin(th)
            pts.SetValue(j + 1, k + 1, gp_Pnt(*X))
    sf = GeomAPI_PointsToBSplineSurface(pts, 3, 8, GeomAbs_C2, 1e-6).Surface()
    u0, u1, v0, v1 = sf.Bounds()
    face = Face(BRepBuilderAPI_MakeFace(sf, u0, u1, v0, v1, 1e-6).Face())
    ea = Edge(BRepBuilderAPI_MakeEdge(sf.UIso(u0)).Edge())
    eb = Edge(BRepBuilderAPI_MakeEdge(sf.UIso(u1)).Edge())
    return face, ea, eb


def _trim_at(face, edges, centre_side):
    """The face split by the contact edges; the pieces on the far side of the corner kept. centre_side(p) > 0 for
    points between the contact curve and the corner."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from build123d import Shape
    args, tools = _shape_list(), _shape_list()
    args.Append(face.wrapped)
    for e in edges:
        tools.Append(e.wrapped)
    op = BRepAlgoAPI_Splitter()
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetUseOBB(True)
    op.Build()
    if not op.IsDone():
        raise ValueError("the face could not be trimmed at the fillet")
    pieces = list(Shape.cast(op.Shape()).faces())
    keep = [pc for pc in pieces if centre_side(_point_on(pc)) <= 0]
    if not keep or len(keep) == len(pieces):
        raise ValueError("the fillet does not cut the face across (extend the face or use a smaller radius)")
    return keep


def fillet(shape, bodies, f, find_edges, find_faces=None):
    """Surface fillet. "mode": "bodies": rolling-ball fillet of "radius" between the surface bodies "source_a" and
    "source_b" (their nearest faces; "faces_a" / "faces_b": only these faces of the body, so that both sides can be
    faces of one body), the ball on the side of each face facing the other ("flip_a", "flip_b" turn it); "trim":
    the bodies trimmed at the contact curves and sewn with the fillet into one body (else the fillet alone).
    "edges": the edges "edges" of the surface body "source" rounded with "radius"."""
    from build123d import Shape, Vector
    r = float(f.get("radius") or 0)
    if r <= 0:
        raise ValueError("radius must be > 0")
    if f.get("mode") == "edges":
        from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
        body = (bodies or {}).get(f.get("source"))
        if body is None:
            raise ValueError("choose the surface body")
        edges = find_edges(body, f.get("edges") or [])
        if not edges:
            raise ValueError("pick the edges to round")
        mk = BRepFilletAPI_MakeFillet(body.wrapped)
        for e in edges:
            mk.Add(r, e.wrapped)
        try:
            mk.Build()
        except Exception:
            pass
        if not mk.IsDone():
            raise ValueError("the fillet of radius %g failed on these edges (the edges must join two faces of the "
                             "body; a smaller radius can work)" % r)
        res = Shape.cast(mk.Shape())
        res._kind = "%d edge(s) rounded" % len(edges)
        return res
    from build123d import Compound
    ba, bb = (bodies or {}).get(f.get("source_a")), (bodies or {}).get(f.get("source_b"))
    if ba is None or bb is None:
        raise ValueError("choose surface A and surface B")

    def side(body, refs, name):
        if not refs:
            return body.faces()
        fs = find_faces(body, refs) if find_faces else []
        if not fs:
            raise ValueError("the faces of surface %s were not found (pick them again)" % name)
        return fs
    fsa, fsb = side(ba, f.get("faces_a"), "A"), side(bb, f.get("faces_b"), "B")
    same = f.get("source_a") == f.get("source_b")
    if same and (not f.get("faces_a") or not f.get("faces_b") or
                 any(x.wrapped.IsSame(y.wrapped) for x in fsa for y in fsb)):
        raise ValueError("surface A and surface B are one body: pick separate faces of it for each side "
                         "(Pick single faces)")
    ca = fsa[0] if len(fsa) == 1 else Compound(children=fsa)
    cb = fsb[0] if len(fsb) == 1 else Compound(children=fsb)
    fa, fb = _closest_faces(ca, cb)
    sa = _default_side(fa, cb) * (-1 if f.get("flip_a") else 1)
    sb = _default_side(fb, ca) * (-1 if f.get("flip_b") else 1)
    try:
        faces, eas, ebs = fillet_faces(fa, fb, r, sa, sb)
    except ValueError as e:
        if f.get("flip_a") or f.get("flip_b"):
            raise
        # the sides facing each other give no fillet (for example a face that curves away): the other sides
        for ta, tb in ((sa, -sb), (-sa, sb), (-sa, -sb)):
            try:
                faces, eas, ebs = fillet_faces(fa, fb, r, ta, tb)
                break
            except ValueError:
                continue
        else:
            raise e
    if not f.get("trim", True):
        res = faces[0] if len(faces) == 1 else _sew(faces, max(1e-4, r * 1e-3))
        res._kind = "fillet face"
        return res

    def side_fn(fc, es, other_face):
        # positive towards the corner: along the face, from the contact curve towards the other face
        def g(p):
            p = Vector(*p) if not hasattr(p, "X") else p
            e, t = min(((e, k / 32) for e in es for k in range(33)), key=lambda x: (x[0].position_at(x[1]) - p).length)
            c = e.position_at(t)
            n = fc.normal_at(c)
            tan = e.tangent_at(t)
            d = n.cross(tan)
            towards = (other_face.distance_to(c + d * (r * 0.1)) < other_face.distance_to(c - d * (r * 0.1)))
            return (p - c).dot(d) * (1 if towards else -1)
        return g
    ka = _trim_at(fa, eas, side_fn(fa, eas, fb))
    kb = _trim_at(fb, ebs, side_fn(fb, ebs, fa))
    if same:
        others = [x for x in ba.faces() if not x.wrapped.IsSame(fa.wrapped) and not x.wrapped.IsSame(fb.wrapped)]
    else:
        others = [x for x in ba.faces() if not x.wrapped.IsSame(fa.wrapped)] + \
                 [x for x in bb.faces() if not x.wrapped.IsSame(fb.wrapped)]
    res = _sew(ka + kb + faces + others, max(1e-4, r * 1e-3))
    res._kind = "fillet between the surfaces, trimmed and sewn (%d faces)" % len(res.faces())
    return res


def close_gaps(bodies, f):
    """Close gaps: slits between faces of the surface body "source" closed. A slit is a free edge of one face with
    free edges of another face running beside it, at most "max_gap" (mm) apart over its whole length (a V-shaped
    split between two faces, or a narrow gap along a seam). One of the two faces is rebuilt on its surface (extended
    beyond the face when it is not analytic) with its edge replaced by the edges of the other face, with short
    lines where the ends do not meet; the faces then share those edges and are sewn into one shell."""
    from OCP.BRep import BRep_Tool, BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_MakeVertex, BRepBuilderAPI_Sewing
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.TopoDS import TopoDS, TopoDS_Compound
    from OCP.gp import gp_Pnt
    from build123d import Shape
    to_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    src = bodies.get(f.get("source"))
    if src is None:
        raise ValueError("choose the surface body")
    max_gap = float(f.get("max_gap") or 0.5)
    if max_gap <= 0:
        raise ValueError("the maximum gap must be > 0")
    # a copy: the edges get curves on the rebuilt faces (the source body is cached)
    body = Shape.cast(BRepBuilderAPI_Copy(src.wrapped, True, False).Shape())
    faces = list(body.faces())
    if len(faces) < 2:
        raise ValueError("the surface body has one face")
    seen = {}
    for i, fc in enumerate(faces):
        for e in fc.edges():
            if BRep_Tool.Degenerated_s(to_edge(e.wrapped)):
                continue
            lst = seen.setdefault(hash(e.wrapped), [])
            for item in lst:
                if item[0].wrapped.IsSame(e.wrapped):
                    item[1].add(i)
                    break
            else:
                lst.append((e, {i}))
    free = [(e, next(iter(s))) for lst in seen.values() for e, s in lst if len(s) == 1]
    by_face = {}
    for e, i in free:
        by_face.setdefault(i, []).append(e)
    boxes = {}

    def box(e):
        k = id(e)
        if k not in boxes:
            bb = e.bounding_box()
            boxes[k] = (bb.min.X - max_gap, bb.min.Y - max_gap, bb.min.Z - max_gap, bb.max.X + max_gap, bb.max.Y + max_gap, bb.max.Z + max_gap)
        return boxes[k]

    def overlap(a, b):
        p, q = box(a), box(b)
        return all(p[k] <= q[k + 3] and q[k] <= p[k + 3] for k in range(3))

    def pts(e, n=9):
        return [e.position_at(k / (n - 1)) for k in range(n)]

    def dist(p, shp):
        v = BRepBuilderAPI_MakeVertex(gp_Pnt(p.X, p.Y, p.Z)).Vertex()
        return BRepExtrema_DistShapeShape(v, shp).Value()

    def comp(edges):
        c = TopoDS_Compound()
        b = BRep_Builder()
        b.MakeCompound(c)
        for e in edges:
            b.Add(c, e.wrapped)
        return c
    cands = []
    for ea, i in free:
        for j, ebs in by_face.items():
            if j == i:
                continue
            near = [eb for eb in ebs if overlap(ea, eb) and all(dist(q, ea.wrapped) <= max_gap for q in pts(eb))]
            if not near:
                continue
            gap = max(dist(q, comp(near)) for q in pts(ea))
            if gap > max_gap or gap < 1e-7:
                continue
            cands.append((not _is_analytic(faces[i]), -faces[i].area, i, ea, j, near))
    # the analytic face (extended on its own surface), else the larger face, takes the slit
    cands.sort(key=lambda c: (c[0], c[1]))
    used, slits = [], []
    isused = lambda e: any(e.wrapped.IsSame(u.wrapped) for u in used)
    for _, _, i, ea, j, near in cands:
        if isused(ea) or any(isused(x) for x in near):
            continue
        used += [ea] + near
        slits.append((i, [ea], j, near))
    if not slits:
        raise ValueError("no gaps up to %g mm between faces of the body" % max_gap)
    out = list(faces)
    plan = {}
    for i, old, j, new in slits:
        plan.setdefault(i, []).append((old, new, j))
    closed, failed = 0, 0
    tried = set()
    while plan:
        i = next(iter(plan))
        reps = plan.pop(i)
        tried.add(i)
        try:
            out[i] = _replaced_edges_face(out[i], [(o, n) for o, n, _ in reps], max_gap)
            closed += len(reps)
            continue
        except ValueError:
            pass
        # the other face of each slit takes it
        for o, n, j in reps:
            if j in tried:
                failed += 1
            else:
                plan.setdefault(j, []).append((n, o, i))
    sew = BRepBuilderAPI_Sewing(max(1e-5, min(1e-3, max_gap * 0.05)))
    for fc in out:
        sew.Add(fc.wrapped)
    sew.Perform()
    res = Shape.cast(sew.SewedShape())
    res._kind = "%d gap(s) closed" % closed + (", %d could not be closed" % failed if failed else "")
    return res


def _is_analytic(fc):
    from OCP.BRep import BRep_Tool
    return BRep_Tool.Surface_s(fc.wrapped).DynamicType().Name() in (
        "Geom_Plane", "Geom_CylindricalSurface", "Geom_ConicalSurface", "Geom_SphericalSurface", "Geom_ToroidalSurface")


def _replaced_edges_face(fc, reps, max_gap):
    """The face rebuilt with each run of its edges old of reps [(old edges, new edges)] replaced by the chain of
    new edges (with short lines at the ends where the chain does not meet the neighbouring edges), on its surface
    (extended by 4 x max_gap + 1 mm when it is not analytic). Raises ValueError."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepLib import BRepLib
    from OCP.ShapeFix import ShapeFix_Face
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt
    from build123d import Shape
    to_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    to_wire = getattr(TopoDS, "Wire_s", None) or TopoDS.Wire
    to_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    F = to_face(fc.wrapped)
    surf = BRep_Tool.Surface_s(F)
    if not _is_analytic(fc):
        surf = _extended_surface(fc, 4 * max_gap + 1.0, 0.01)
    outer = BRepTools.OuterWire_s(F)

    def rep_of(e):
        for k, (old, _new) in enumerate(reps):
            if any(e.wrapped.IsSame(o.wrapped) for o in old):
                return k
        return None

    def line(p, q):
        return Shape.cast(BRepBuilderAPI_MakeEdge(gp_Pnt(p.X, p.Y, p.Z), gp_Pnt(q.X, q.Y, q.Z)).Edge())
    done = 0
    wires = []
    for w in fc.wires():
        ex = BRepTools_WireExplorer(to_wire(w.wrapped), F)
        seq = []
        while ex.More():
            seq.append(Shape.cast(ex.Current()))
            ex.Next()
        # start at an edge that stays, so that a replaced run is not split at the start of the list
        keep = [k for k, e in enumerate(seq) if rep_of(e) is None]
        if keep:
            seq = seq[keep[0]:] + seq[:keep[0]]
        edges = []
        k = 0
        while k < len(seq):
            r = rep_of(seq[k])
            if r is None:
                edges.append(seq[k])
                k += 1
                continue
            run = [seq[k]]
            while k + len(run) < len(seq) and rep_of(seq[k + len(run)]) == r:
                run.append(seq[k + len(run)])
            k += len(run)
            done += 1
            # (position_at follows the orientation of the edge in the wire)
            s, t = run[0].position_at(0), run[-1].position_at(1)
            chain = _ordered_chain(reps[r][1], s)
            cs, ct = chain[0][1], chain[-1][2]
            if (cs - s).length > 1e-6:
                edges.append(line(s, cs))
            edges += [c[0] for c in chain]
            if (ct - t).length > 1e-6:
                edges.append(line(ct, t))
        mw = BRepBuilderAPI_MakeWire()
        for e in edges:
            mw.Add(to_edge(e.wrapped))
            if not mw.IsDone():
                raise ValueError("the boundary is not one wire")
        wires.append((w.wrapped.IsSame(outer), mw.Wire()))
    if not done:
        raise ValueError("no edge replaced")
    ow = [x for o, x in wires if o]
    if not ow:
        raise ValueError("no outer wire")
    inner = [x for o, x in wires if not o]
    grow = max_gap * sum(sum(e.length for e in old) for old, _ in reps) + 1e-6
    for wr in (ow[0], to_wire(ow[0].Reversed())):
        mk = BRepBuilderAPI_MakeFace(surf, wr, True)
        if not mk.IsDone():
            continue
        for w in inner:
            mk.Add(w)
        fx = ShapeFix_Face(mk.Face())
        fx.Perform()
        cand = fx.Face()
        BRepLib.SameParameter_s(cand, 1e-5, True)
        c = Shape.cast(cand)
        if c.area > 0 and BRepCheck_Analyzer(cand).IsValid() and abs(c.area - fc.area) <= grow:
            pc = _point_on(fc)
            try:
                if fc.normal_at(pc).dot(c.normal_at(pc)) < 0:
                    c = Shape.cast(c.wrapped.Reversed())
            except Exception:  # noqa: BLE001
                pass
            return c
    raise ValueError("the face could not be rebuilt")


def _ordered_chain(edges, start):
    """The edges as a chain from the end nearest to start: [(edge, first point, last point)] along the chain."""
    rest = list(edges)

    def ends(e):
        return e.position_at(0), e.position_at(1)
    first = min(rest, key=lambda e: min((p - start).length for p in ends(e)))
    rest.remove(first)
    a, b = ends(first)
    out = [(first, a, b) if (a - start).length <= (b - start).length else (first, b, a)]
    while rest:
        cur = out[-1][2]
        nxt = min(rest, key=lambda e: min((p - cur).length for p in ends(e)))
        rest.remove(nxt)
        a, b = ends(nxt)
        out.append((nxt, a, b) if (a - cur).length <= (b - cur).length else (nxt, b, a))
    return out


def sweep_surface(bodies, f):
    """Sweep surface: the profile ("profile": a curve body or a sketch feature; each separate chain of it swept on
    its own) swept along the path ("path": a curve body or a sketch feature; one connected chain), the profile
    turning with the path ("orient": "corrected" (corrected Frenet, default; the discrete frame when it fails) |
    "frenet" | "discrete" (discrete frame) | "fixed" (moved without turning)), joined at the path corners by
    extended and intersected sections; "smooth" (mm, default 0.02, 0: off): the path replaced by one C2 B-spline
    within that tolerance. Open profiles give open surfaces; a closed profile gives a tube."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
    from OCP.BRepBuilderAPI import BRepBuilderAPI_RightCorner
    from build123d import Shape, Wire, Compound

    def edges_of(ref, what):
        if not ref:
            raise ValueError("choose the %s (a curve body or a sketch)" % what)
        body = (bodies or {}).get(ref)
        if body is not None:
            es = list(body.edges())
        else:
            fn = f.get("_sketch_curves")
            if fn is None:
                raise ValueError("the %s was not found" % what)
            es = list(fn(ref))
        if not es:
            raise ValueError("the %s has no curves" % what)
        return es
    profiles = _chain_wires(edges_of(f.get("profile"), "profile"))
    pe = edges_of(f.get("path"), "path")
    smooth = float(f.get("smooth", 0.02) or 0)
    note = []
    if smooth > 0:
        # the path as one smooth curve (C2 B-spline through points along the chain, within the tolerance): the
        # kinks, short edges and small breaks of an extracted curve do not twist the swept profile
        path = Wire([_smooth_chain(pe, smooth)])
        note.append("path smoothed within %g mm" % smooth)
    else:
        chains = list(Wire.combine(pe, tol=1e-4))
        if len(chains) > 1:
            chains, n = _join_gaps(chains, 0.5)
            if n:
                note.append("%d path gap(s) bridged" % n)
        if len(chains) != 1:
            raise ValueError("the path has %d separate chains: one connected chain is needed (Smooth the path "
                             "joins small breaks)" % len(chains))
        path = chains[0]
    from OCP.gp import gp_Ax2
    orient = f.get("orient") or "corrected"

    def pipe(w, mode):
        ps = BRepOffsetAPI_MakePipeShell(path.wrapped)
        if mode == "frenet":
            ps.SetMode(True)
        elif mode == "discrete":
            ps.SetDiscreteMode()
        elif mode == "fixed":
            ps.SetMode(gp_Ax2())
        else:
            ps.SetMode(False)
        ps.SetTransitionMode(BRepBuilderAPI_RightCorner)
        ps.Add(w.wrapped, False, False)
        try:
            ps.Build()
        except Exception:  # noqa: BLE001
            return None
        return Shape.cast(ps.Shape()) if ps.IsDone() else None
    out = []
    for w in profiles:
        r = pipe(w, orient)
        if r is None and orient == "corrected":
            # the corrected Frenet frame fails on paths with tight bends: the discrete frame
            r = pipe(w, "discrete")
            if r is not None and "discrete frame used (corrected Frenet failed)" not in note:
                note.append("discrete frame used (corrected Frenet failed)")
        if r is None:
            raise ValueError("the sweep failed (a path corner tighter than the profile, or a profile far from the "
                             "path start); try another Profile orientation")
        out.append(r)
    if len(out) == 1:
        res = out[0]
    else:
        res = Compound(children=out)
    if not res.faces():
        raise ValueError("the sweep gave no surface")
    if len(out) > 1:
        note.append("%d profile chain(s) swept" % len(out))
    res._kind = ", ".join(note) or None
    return res


def _smooth_chain(edges, tol, step=0.1):
    """One C2 B-spline edge through the edges taken as one chain (ordered end to nearest end, gaps up to 1 mm
    allowed), points every step (mm, at least 4 per edge), within tol (mm). Raises ValueError."""
    from OCP.GeomAPI import GeomAPI_PointsToBSpline
    try:
        from OCP.TColgp import TColgp_Array1OfPnt
    except ImportError:
        from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Pnt
    from build123d import Edge
    rest = [e for e in edges if e.length > 1e-9]
    if not rest:
        raise ValueError("the path has no length")
    ends = lambda e: (e.position_at(0), e.position_at(1))
    # start at a chain end: the edge end farthest from every other edge
    def lonely(e, p):
        return min([min((p - q).length for q in ends(o)) for o in rest if o is not e] or [0.0])
    first, rev = max(((e, k) for e in rest for k in (0, 1)), key=lambda x: lonely(x[0], ends(x[0])[x[1]]))
    order = [(first, rev == 1)]
    rest.remove(first)
    cur = ends(first)[0] if rev == 1 else ends(first)[1]
    while rest:
        nxt, d, back = min(((o, min((cur - q).length for q in ends(o)), (cur - ends(o)[1]).length < (cur - ends(o)[0]).length)
                            for o in rest), key=lambda x: x[1])
        if d > 1.0:
            raise ValueError("the path has breaks over 1 mm: one connected chain is needed")
        order.append((nxt, back))
        rest.remove(nxt)
        cur = ends(nxt)[0] if back else ends(nxt)[1]
    pts = []
    for e, back in order:
        n = max(4, int(e.length / step) + 1)
        ts = [k / n for k in range(n + 1)]
        if back:
            ts = ts[::-1]
        for t in ts:
            q = e.position_at(t)
            if not pts or (q - pts[-1]).length > max(step * 0.25, 1e-4):
                pts.append(q)
    if len(pts) < 2:
        raise ValueError("the path has no length")
    arr = TColgp_Array1OfPnt(1, len(pts))
    for i, q in enumerate(pts):
        arr.SetValue(i + 1, gp_Pnt(q.X, q.Y, q.Z))
    fit = GeomAPI_PointsToBSpline(arr, 3, 8, GeomAbs_C2, tol)
    if not fit.IsDone():
        raise ValueError("the path could not be smoothed")
    return Edge(BRepBuilderAPI_MakeEdge(fit.Curve()).Edge())


def curve_project(shape, bodies, f):
    """Project curve: the curves of "source" (a curve body or a sketch feature) projected onto "target" (a surface
    body; empty: the solid). "method": "normal" (default; each point to the nearest point of the surface, along
    the surface normal) | "direction" ("direction" [x, y, z]; a sketch without a direction: its plane normal),
    "keep": "nearest" (default; of the projections along the direction, the one nearest to the curve) | "all".
    Returns a curve body."""
    from OCP.BRepProj import BRepProj_Projection
    from OCP.BRepOffsetAPI import BRepOffsetAPI_NormalProjection
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.gp import gp_Dir
    from build123d import Shape, Compound, Vector
    ref = f.get("source")
    if not ref:
        raise ValueError("choose the curve to project (a curve body or a sketch)")
    body = (bodies or {}).get(ref)
    if body is not None:
        edges = list(body.edges())
    else:
        fn = f.get("_sketch_curves")
        if fn is None:
            raise ValueError("the curve was not found")
        edges = list(fn(ref))
    if not edges:
        raise ValueError("the curve has no edges")
    target = (bodies or {}).get(f.get("target")) if f.get("target") else shape
    if target is None or not target.faces():
        raise ValueError("choose the surface to project onto")
    wires = _chain_wires(edges)
    out = []
    if (f.get("method") or "normal") == "direction":
        d = f.get("direction")
        if not d or Vector(*d).length < 1e-12:
            # the normal of the plane of the curve (a sketch)
            pts = [e.position_at(k / 8.0) for e in edges for k in range(9)]
            n = Vector(0, 0, 0)
            for i in range(1, len(pts) - 1):
                n = n + (pts[i] - pts[0]).cross(pts[i + 1] - pts[0])
            if n.length < 1e-9:
                raise ValueError("the curve is straight: give the projection direction")
            d = [n.X, n.Y, n.Z]
        dv = Vector(*d).normalized()
        keep_all = f.get("keep") == "all"
        for w in wires:
            pr = BRepProj_Projection(w.wrapped, target.wrapped, gp_Dir(dv.X, dv.Y, dv.Z))
            cands = []
            while pr.More():
                cands.append(Shape.cast(pr.Current()))
                pr.Next()
            if not cands:
                continue
            if keep_all:
                out += cands
            else:
                c = w.center()
                out.append(min(cands, key=lambda x: (x.center() - c).length))
    else:
        for w in wires:
            op = BRepOffsetAPI_NormalProjection(target.wrapped)
            op.Add(w.wrapped)
            op.SetParams(1e-4, 1e-3, GeomAbs_C2, 14, 16)
            try:
                op.Build()
            except Exception:  # noqa: BLE001
                continue
            if not op.IsDone():
                continue
            es = list(Shape.cast(op.Projection()).edges())
            if es:
                out += _chain_wires(es)
    if not out:
        raise ValueError("the projection misses the surface")
    res = out[0] if len(out) == 1 else Compound(children=out)
    res._kind = "%d chain(s)" % len(out) if len(out) > 1 else None
    return res


# --------------------------------------------------------------------------- curves with end conditions

def _end_data(shape, bodies, end, find_edges, datums=None):
    """Point, outward unit tangent and curvature vector at one end of a curve: end {"kind": "edge", "ref": edge key,
    "at": [x, y, z] (the end of the edge nearer this point)} | {"kind": "curve", "body": curve body id, "at"} |
    {"kind": "point", "point": [x, y, z] or point feature id}. The tangent points away from the curve at its end
    (None for a point). Returns (p, t, k, edge) as build123d Vectors (k: curvature vector d2r/ds2)."""
    from build123d import Vector
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepLProp import BRepLProp_CLProps
    kind = (end or {}).get("kind")
    if kind == "point":
        from . import part as prt
        return Vector(*prt.ref_point(datums, end.get("point"))), None, None, None
    at = Vector(*(end.get("at") or [0, 0, 0]))
    if kind == "curve":
        body = (bodies or {}).get(end.get("body"))
        if body is None:
            raise ValueError("the curve body of the end was not found")
        edges = list(body.edges())
    else:
        edges = _ref_edges(shape, [end.get("ref") or {}], find_edges, bodies)
    if not edges:
        raise ValueError("the edge of the end was not found")
    # the edge end nearest the click
    best = None
    for e in edges:
        for u in (0.0, 1.0):
            q = e.position_at(u)
            d = (q - at).length
            if best is None or d < best[0]:
                best = (d, e, u)
    _, e, u = best
    ad = BRepAdaptor_Curve(e.wrapped)
    u0, u1 = ad.FirstParameter(), ad.LastParameter()
    pr = BRepLProp_CLProps(ad, u0 if u < 0.5 else u1, 2, 1e-7)
    p = pr.Value()
    d1 = pr.D1()
    t = Vector(d1.X(), d1.Y(), d1.Z())
    if t.length < 1e-12:
        t = e.tangent_at(u)
    t = t.normalized()
    kv = Vector(0, 0, 0)
    try:
        from OCP.gp import gp_Dir
        if pr.IsTangentDefined():
            c = pr.Curvature()
            if c > 1e-12:
                nrm = gp_Dir()
                pr.Normal(nrm)
                kv = Vector(nrm.X(), nrm.Y(), nrm.Z()) * c
    except Exception:
        kv = Vector(0, 0, 0)
    # outward: the direction away from the edge at this end (the curve continues the edge)
    if u < 0.5:
        t = -t
    return Vector(p.X(), p.Y(), p.Z()), t, kv, e


def _hermite_edge(p0, t0, k0, p1, t1, k1):
    """Bezier edge from p0 to p1 with the end derivatives: cubic with t0, t1 (None: free end, the control point
    at the chord third), quintic when a curvature vector k is given (second derivative)."""
    from OCP.Geom import Geom_BezierCurve
    from OCP.gp import gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from build123d import Edge
    try:
        from OCP.TColgp import TColgp_Array1OfPnt as Arr
    except ImportError:
        from OCP.collections import Array1_gp_Pnt as Arr
    chord = p1 - p0
    if t0 is None:
        t0 = chord
    if t1 is None:
        t1 = chord
    quintic = k0 is not None or k1 is not None
    if quintic:
        a0 = k0 if k0 is not None else (p1 - p0) * 0
        a1 = k1 if k1 is not None else (p1 - p0) * 0
        pts = [p0, p0 + t0 / 5, p0 + t0 * (2 / 5) + a0 / 20, p1 - t1 * (2 / 5) + a1 / 20, p1 - t1 / 5, p1]
    else:
        pts = [p0, p0 + t0 / 3, p1 - t1 / 3, p1]
    a = Arr(1, len(pts))
    for i, q in enumerate(pts):
        a.SetValue(i + 1, gp_Pnt(q.X, q.Y, q.Z))
    return Edge(BRepBuilderAPI_MakeEdge(Geom_BezierCurve(a)).Edge())


def curve_blend(shape, bodies, f, find_edges, datums=None):
    """Blend curve: a curve between two ends ("ends": [end A, end B], see _end_data) with the continuity of each
    end "cont": "position" | "tangent" | "curvature" (an end on a point is position only) and the tangent length
    "factor" of each end (x the distance between the ends; 1 is a natural blend). The curve leaves each edge in
    its direction (continues it). Returns a curve body (a wire of one edge)."""
    from build123d import Wire
    ends = f.get("ends") or []
    if len(ends) < 2 or not ends[0] or not ends[1]:
        raise ValueError("pick the two ends of the curve")
    data = [_end_data(shape, bodies, e, find_edges, datums) for e in ends[:2]]
    (p0, t0, k0, _), (p1, t1, k1, _) = data
    d = (p1 - p0).length
    if d < 1e-9:
        raise ValueError("the two ends are at the same point")
    conts = [(e.get("cont") or "tangent") if dt[1] is not None else "position" for e, dt in zip(ends, data)]
    facs = [float(e.get("factor") or 1.0) for e in ends]
    # derivatives of the blend parametrised on [0, 1]: speed = factor x distance; the curvature vector is for the
    # arc length, so the second derivative is k |speed|^2 (plus nothing along the tangent)
    def deriv(t, k, cont, fac, into):
        if cont == "position" or t is None:
            return None, None
        s = fac * d
        tv = (t if not into else -t) * s
        if cont == "curvature" and k is not None:
            return tv, k * (s * s)
        return tv, None
    T0, K0 = deriv(t0, k0, conts[0], facs[0], False)
    T1, K1 = deriv(t1, k1, conts[1], facs[1], True)
    e = _hermite_edge(p0, T0, K0, p1, T1, K1)
    w = Wire([e])
    w._kind = "blend " + " / ".join(conts) + ", %.1f mm" % e.length
    return w


def curve_points(f, datums=None):
    """Curve through points ("points": point feature ids or [x, y, z] vertices) with "method": "polyline" (straight
    segments) | "spline" (C2 B-spline through the points) | "line" (best-fit straight line over the span of the
    points) | "arc" (circular arc through three points); "closed" closes a polyline or a spline. Returns a curve
    body."""
    from build123d import Wire, Edge, Vector
    from . import part as prt
    pts = [Vector(*prt.ref_point(datums, p)) for p in (f.get("points") or [])]
    # consecutive duplicates dropped
    clean = []
    for q in pts:
        if not clean or (q - clean[-1]).length > 1e-7:
            clean.append(q)
    pts = clean
    m = f.get("method") or "polyline"
    closed = bool(f.get("closed")) and m in ("polyline", "spline")
    if m == "arc":
        if len(pts) != 3:
            raise ValueError("an arc needs exactly three points (%d picked)" % len(pts))
        w = Wire([Edge.make_three_point_arc(pts[0], pts[1], pts[2])])
        w._kind = "arc, radius %.3f mm" % w.edges()[0].radius
        return w
    if len(pts) < 2:
        raise ValueError("pick at least two points (%d picked)" % len(pts))
    if m == "line":
        import numpy as np
        A = np.array([[q.X, q.Y, q.Z] for q in pts])
        c = A.mean(axis=0)
        _, _, vt = np.linalg.svd(A - c)
        dv = vt[0]
        s = (A - c) @ dv
        a, b = c + dv * s.min(), c + dv * s.max()
        if np.linalg.norm(b - a) < 1e-9:
            raise ValueError("the points are at one place")
        w = Wire([Edge.make_line(Vector(*a), Vector(*b))])
        dev = float(np.max(np.linalg.norm((A - c) - np.outer(s, dv), axis=1)))
        w._kind = "fitted line, %.3f mm, max deviation %.4f mm" % (float(np.linalg.norm(b - a)), dev)
        return w
    if m == "spline":
        from OCP.GeomAPI import GeomAPI_Interpolate
        from OCP.gp import gp_Pnt
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        try:
            from OCP.TColgp import TColgp_HArray1OfPnt as HArr
        except ImportError:
            from OCP.collections import HArray1_gp_Pnt as HArr
        src = pts[:-1] if closed and (pts[0] - pts[-1]).length < 1e-7 else pts
        if len(src) < 2 or (closed and len(src) < 3):
            raise ValueError("pick more points")
        a = HArr(1, len(src))
        for i, q in enumerate(src):
            a.SetValue(i + 1, gp_Pnt(q.X, q.Y, q.Z))
        it = GeomAPI_Interpolate(a, closed, 1e-7)
        it.Perform()
        if not it.IsDone():
            raise ValueError("the spline through the points failed")
        w = Wire([Edge(BRepBuilderAPI_MakeEdge(it.Curve()).Edge())])
        w._kind = ("closed " if closed else "") + "spline through %d points, %.3f mm" % (len(src), w.length)
        return w
    # polyline
    seq = list(pts)
    if closed and (seq[0] - seq[-1]).length > 1e-7:
        seq.append(seq[0])
    edges = [Edge.make_line(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]
    w = Wire(edges)
    w._kind = ("closed " if closed else "") + "polyline, %d segments, %.3f mm" % (len(edges), w.length)
    return w


# --------------------------------------------------------------------------- tangent bridge

def _owner_faces(shape, bodies):
    """[(face, [edges])] over the solid and the surface bodies, for the cross-boundary direction at an edge."""
    out = []
    shapes = ([shape] if shape is not None else []) + [b for b in (bodies or {}).values() if b is not None and b.faces()]
    for s in shapes:
        for fc in s.faces():
            out.append((fc, list(fc.edges())))
    return out


def _cross_dir(p, e, owners, toward):
    """Unit direction at point p of edge e across the boundary of the face that owns e (in the face's tangent
    plane, perpendicular to the edge), pointing to the side of "toward"; None when no face owns the edge."""
    for fc, edges in owners:
        if any(e.wrapped.IsSame(x.wrapped) for x in edges):
            n = fc.normal_at(p)
            t = e.tangent_at(_param_near(e, p))
            d = n.cross(t)
            if d.length < 1e-12:
                return None
            d = d.normalized()
            if d.dot(toward - p) < 0:
                d = -d
            return d
    return None


def _param_near(e, p):
    """Normalised parameter of the point of edge e nearest p (sampled)."""
    best, bu = None, 0.0
    for i in range(33):
        u = i / 32
        d = (e.position_at(u) - p).length
        if best is None or d < best:
            best, bu = d, u
    return bu


def _edge_at(wire, u):
    """The edge of the wire at the normalised parameter u (the edge nearest the point there)."""
    p = wire.position_at(u)
    best, be = None, None
    for e in wire.edges():
        d = min((e.position_at(i / 16) - p).length for i in range(17))
        if best is None or d < best:
            best, be = d, e
    return be, p


def bridge_tangent(shape, bodies, wa, wb, rev, factor=1.0, nu=32, nv=12):
    """Surface between the wires A and B that leaves each side tangent to the face owning that side's edges (G1):
    cubic Hermite blends between corresponding points of the sides (the cross-boundary direction of the owner face
    as the end tangent, the chord direction where no face owns the edge, e.g. a curve body), fitted with a C2
    B-spline surface. factor scales the tangent length (x the distance between the sides)."""
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.GeomAbs import GeomAbs_C2
    from OCP.gp import gp_Pnt
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from build123d import Face
    try:
        from OCP.TColgp import TColgp_Array2OfPnt as Arr2
    except ImportError:
        from OCP.collections import Array2_gp_Pnt as Arr2
    owners = _owner_faces(shape, bodies)
    pts = Arr2(1, nv + 1, 1, nu + 1)
    for i in range(nu + 1):
        u = i / nu
        ea, pa = _edge_at(wa, u)
        eb, pb = _edge_at(wb, (1 - u) if rev else u)
        chord = pb - pa
        d = chord.length
        if d < 1e-9:
            ta = tb = chord
        else:
            da = _cross_dir(pa, ea, owners, pb)
            db = _cross_dir(pb, eb, owners, pa)
            s = factor * d
            ta = (da * s) if da is not None else chord
            tb = (-db * s) if db is not None else chord
        for j in range(nv + 1):
            t = j / nv
            h00 = 2 * t ** 3 - 3 * t ** 2 + 1
            h10 = t ** 3 - 2 * t ** 2 + t
            h01 = -2 * t ** 3 + 3 * t ** 2
            h11 = t ** 3 - t ** 2
            q = pa * h00 + ta * h10 + pb * h01 + tb * h11
            pts.SetValue(j + 1, i + 1, gp_Pnt(q.X, q.Y, q.Z))
    sf = GeomAPI_PointsToBSplineSurface(pts, 3, 8, GeomAbs_C2, 1e-6).Surface()
    u0, u1, v0, v1 = sf.Bounds()
    return Face(BRepBuilderAPI_MakeFace(sf, u0, u1, v0, v1, 1e-6).Face())


# --------------------------------------------------------------------------- connect surfaces (close a corner)

def connect(shape, bodies, f, find_edges, find_faces):
    """Connect surfaces: surface body "source_a" is extended across its edges "edges_a" up to surface body
    "source_b", then "source_b" across "edges_b" up to the extended A; both end at their intersection and are sewn
    into one body (a corner between two surfaces that do not quite meet, or overlap, is closed). "tolerance" (mm)
    as Extend surface."""
    a, b = f.get("source_a"), f.get("source_b")
    if not a or not b or a == b:
        raise ValueError("pick edges of two different surface bodies")
    if bodies.get(a) is None or bodies.get(b) is None:
        raise ValueError("a surface body of the connection was not found (it must be above this feature)")
    if not f.get("edges_a") or not f.get("edges_b"):
        raise ValueError("pick the edges of side A and of side B that meet at the corner")
    tol = float(f.get("tolerance") or 0.01)
    fa = {"source": a, "edges": f.get("edges_a") or [], "mode": "upto", "target": b, "tolerance": tol}
    ext_a = extend_edges(shape, bodies, fa, find_edges, find_faces)
    tmp = dict(bodies)
    tmp["_connect_a"] = ext_a
    fb = {"source": b, "edges": f.get("edges_b") or [], "mode": "upto", "target": "_connect_a", "tolerance": tol}
    ext_b = extend_edges(shape, tmp, fb, find_edges, find_faces)
    out = _sew([ext_a, ext_b], 1e-3)
    out._kind = "A extended up to B and B up to A, sewn (%d faces, %d shell(s))" % (len(out.faces()), len(out.shells()))
    notes = [x for x in (fa.get("_note"), fb.get("_note")) if x]
    if notes:
        out._kind += "; " + "; ".join(notes)
    return out
