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
  {"type": "surf_bridge", "edges_a", "curves_a", "edges_b", "curves_b", "flip"}   ruled surface between two chains
   of edges, ends joined corner to corner
  {"type": "surf_loft", "sections": [{"plane", "offset", "sketch"}, ...], "ruled": bool, "smooth": bool (default true),
   "smooth_angle": deg (default 15)}   loft through sketch curves; with smooth the edges of a section that meet at
   less than smooth_angle are joined into one B-spline (one smooth face instead of one face per segment)
  {"type": "surf_fill", "edges": [edge keys], "tangent": bool}             N-sided patch over a closed loop of edges
  {"type": "surf_fillet", "mode": "bodies" | "edges", "radius": mm, bodies: "source_a", "source_b", "flip_a",
   "flip_b", "trim": bool (default true); edges: "source", "edges": [edge keys]}   rolling-ball fillet between two
   surface bodies (trimmed and sewn into one body), or rounded edges of one surface body
  {"type": "surf_offset", "source": feature id, "distance": mm}            offset of a surface body
  {"type": "surf_sew", "sources": [feature ids], "tolerance": mm}          sewn shell of several bodies
  {"type": "surf_import", "path": STEP file, "label": component name | ""}  faces of a STEP file (of the component
                                                                           with that label; empty: all) as one body
Consumer features:
  {"type": "thicken", "source": id, "thickness": mm, "side": "+" | "-" | "both", "mode": "add" | "cut" | "new"}
  {"type": "surf_cut", "source": id, "keep": "+" | "-"}                     cut the solid with the surface, keep the
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


def _offset_body(body, d):
    """Offset of a face or shell along its normals. Adjacent faces are extended or trimmed to meet at the
    offset (intersection join); when that fails each face is offset on its own (simple offset)."""
    from OCP.BRepOffset import BRepOffset_MakeSimpleOffset, BRepOffset_Skin
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
    from OCP.GeomAbs import GeomAbs_Intersection
    from build123d import Shape
    if abs(d) < 1e-12:
        return body
    try:
        op = BRepOffsetAPI_MakeOffsetShape()
        op.PerformByJoin(body.wrapped, float(d), 1e-6, BRepOffset_Skin, False, False, GeomAbs_Intersection)
        res = Shape.cast(op.Shape())
        valid = res.is_valid() if callable(res.is_valid) else res.is_valid
        if res.faces() and valid and abs(res.area) > 1e-9:
            res._offset_kind = "joined"
            return res
    except Exception:
        pass
    op = BRepOffset_MakeSimpleOffset(body.wrapped, d)
    op.SetBuildSolidFlag(False)
    op.Perform()
    if not op.IsDone():
        raise ValueError("the offset failed: %s" % op.GetErrorMessage())
    res = Shape.cast(op.GetResultShape())
    res._offset_kind = "simple"
    return res


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
    corresponding points between ("flip" joins the other ends)."""
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
    # a closed loop of one edge (circle, ellipse) or two edges needs no check; longer loops are checked below by the fill
    op = BRepOffsetAPI_MakeFilling()
    tangent = bool(f.get("tangent", True))
    for e in edges:
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
        from build123d import Wire, Face
        w = Wire(edges) if len(edges) > 1 else Wire([edges[0]])
        if w.is_closed:
            fc = Face(w)
            if fc.area > 1e-9:
                return fc
    except Exception:
        pass
    raise ValueError("the fill failed (the edges do not form one closed loop)")


def offset(shape, bodies, f, find_faces):
    src = source_body(shape, bodies, f, find_faces)
    res = _offset_body(src, float(f.get("distance") or 0))
    if getattr(res, "_offset_kind", "") == "simple":
        res._kind = "faces offset one by one (the joins could not be computed)"
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
    src = bodies.get(f.get("source"))
    if src is None:
        raise ValueError("source surface not found")
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
    op.Build()
    if not op.IsDone():
        raise ValueError("the split failed")
    pieces = list(Shape.cast(op.Shape()).solids())
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


def _chain_wires(edges):
    from build123d import Wire
    try:
        return list(Wire.combine(edges))
    except Exception:
        return [Wire([e]) for e in edges]


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
    clean = f.get("clean") or "none"
    tol = float(f.get("tolerance") or 0.05)
    out = []
    kinds = []
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
    body._kind = ", ".join(sorted(set(k for k in kinds if k))) or None
    return body


def curve_section(shape, bodies, f, find_faces):
    """Intersection curves of two surface bodies, or of a surface body (or faces of the solid) with the solid."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from build123d import Shape, Compound
    a = source_body(shape, bodies, f, find_faces)
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
    return wires[0] if len(wires) == 1 else Compound(children=wires)


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
        return Shape.cast(BRepPrimAPI_MakePrism(base.wrapped, gp_Vec(*d)).Shape())
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


def trim_pieces(shape, bodies, f):
    """The pieces of the source surface body split by the trimming tool: (pieces, tool_body). "with": "surface"
    (tool: surface or curve body id), "solid", "plane" (tool: plane feature id, or XY / XZ / YZ; needs
    f["_datums"]) or "sketch" (tool: sketch feature id; its curves in f["_tool_edges"], projected onto the surface)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
    from OCP.BRepProj import BRepProj_Projection
    from OCP.gp import gp_Dir
    from build123d import Shape
    src = bodies.get(f.get("source"))
    if src is None:
        raise ValueError("source surface not found")
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
        bb = src.bounding_box()
        size = max(bb.diagonal, 10.0) * 2 + (abs(bb.center().X) + abs(bb.center().Y) + abs(bb.center().Z))
        tool_shapes = [plane_face(fr, size)]
    else:
        curves = None
        if with_kind == "sketch":
            curves = f.get("_tool_edges") or []
            if not curves:
                raise ValueError("the tool sketch has no curves")
        else:
            tool_body = bodies.get(f.get("tool"))
            if tool_body is None:
                raise ValueError("trimming tool not found")
            if tool_body.faces():
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
    args, tools = _shape_list(), _shape_list()
    for fc in src.faces():
        args.Append(fc.wrapped)
    for t in tool_shapes:
        tools.Append(t)
    op = BRepAlgoAPI_Splitter()
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise ValueError("the split failed")
    pieces = list(Shape.cast(op.Shape()).faces())
    if len(pieces) < 2:
        raise ValueError("the tool does not cut the surface")
    return pieces, tool_body


def trim(shape, bodies, f):
    """Trim a surface body: split it with another surface body, with the solid, with a plane, or with a curve
    body projected onto it, and keep the pieces selected by "keep": "+" / "-" (side along / against the tool
    surface normal), "inside" / "outside" (of the solid), "largest", "point" (the piece nearest to "point"), or
    "pick" (every piece except those nearest to the points in "remove")."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    from OCP.gp import gp_Pnt
    from build123d import Vector
    pieces, tool_body = trim_pieces(shape, bodies, f)
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
            n = p.normal_at(c)
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
    return out[0] if len(out) == 1 else _sew(out)


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


def _strip(face, surf, e, dist, n=24):
    """Extension strip of face across its boundary edge e by dist (mm), as a face on the surface surf: the edge,
    the edge moved outward along the surface, and two side curves. A closed edge gives the parametric band."""
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

    P, Q = [], []
    for i in range(n + 1):
        t = i / n
        p, tg = e.position_at(t), e.tangent_at(t)
        nrm = face.normal_at(p)
        w = nrm.cross(tg).normalized()
        if face.is_inside(p + w * (dist * 0.01)):
            w = -w
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
    return out


def extend_edges(shape, bodies, f, find_edges, find_faces):
    """Extend a surface body across selected boundary edges ("edges": edge keys) by "distance" (mm). The trim of
    the surface (holes, other edges) is kept. Strips on the same analytic surface merge with the face; on a
    B-spline surface the strip lies on the tangent-extrapolated surface and stays a separate face of the shell."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
    from .occfix import CheckedUnify as ShapeUpgrade_UnifySameDomain
    from build123d import Shape
    src = source_body(shape, bodies, f, find_faces)
    dist = float(f.get("distance") or 5.0)
    edges = find_edges(src, f.get("edges") or [])
    if not edges:
        raise ValueError("no edges of the surface selected")
    faces = list(src.faces())
    strips = []
    kinds = set()
    for e in edges:
        owner = None
        for fc in faces:
            if any(x.wrapped.IsSame(e.wrapped) for x in fc.edges()):
                owner = fc
                break
        if owner is None:
            raise ValueError("an edge does not belong to the surface")
        surf = BRep_Tool.Surface_s(owner.wrapped)
        name = surf.DynamicType().Name()
        if name not in ("Geom_Plane", "Geom_CylindricalSurface", "Geom_ConicalSurface", "Geom_SphericalSurface", "Geom_ToroidalSurface"):
            surf = _extended_surface(owner, dist * 1.5, float(f.get("tolerance") or 0.01))
        kinds.add(name.replace("Geom_", ""))
        strips.append(_strip(owner, surf, e, dist))
    sew = BRepBuilderAPI_Sewing(1e-5)
    for fc in faces:
        sew.Add(fc.wrapped)
    for st in strips:
        sew.Add(st.wrapped)
    sew.Perform()
    u = ShapeUpgrade_UnifySameDomain(sew.SewedShape(), True, True, False)
    u.Build()
    out = Shape.cast(u.Shape())
    out._kind = "%s extended by %g mm across %d edge(s)" % (", ".join(sorted(kinds)), dist, len(edges))
    return out


def _extended_surface(face, dist, tol):
    """The surface of a face as a B-spline surface extended by dist (mm) beyond the four sides of the face's
    parameter range (GeomLib.ExtendSurfByLength, curvature continuous; the surface inside is unchanged); when that
    fails, the surface re-fitted with a tangent extrapolation."""
    try:
        return _extended_bspline(face, dist)
    except Exception:
        return _refit_extended_surface(face, dist, tol)


def _extended_bspline(face, dist):
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools
    from OCP.Geom import Geom_RectangularTrimmedSurface, Geom_BSplineSurface
    from OCP.GeomConvert import GeomConvert
    from OCP.GeomLib import GeomLib
    surf = BRep_Tool.Surface_s(face.wrapped)
    u1, u2, v1, v2 = BRepTools.UVBounds_s(face.wrapped)
    bs = GeomConvert.SurfaceToBSplineSurface_s(Geom_RectangularTrimmedSurface(surf, u1, u2, v1, v2))
    for in_u in (True, False):
        for after in (True, False):
            GeomLib.ExtendSurfByLength_s(bs, dist, 2, in_u, after)
    return bs


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


def _project(surf, p):
    """(point, u, v, distance) of the projection of p onto the surface, or None."""
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt
    pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*p), surf)
    if not pr.NbPoints():
        return None
    q = pr.NearestPoint()
    u, v = pr.LowerDistanceParameters()
    return (q.X(), q.Y(), q.Z()), u, v, pr.LowerDistance()


def _inside(face, surf, uv):
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    from OCP.gp import gp_Pnt2d
    u, v = uv
    us = [u + k * surf.UPeriod() for k in (-1, 0, 1)] if surf.IsUPeriodic() else [u]
    vs = [v + k * surf.VPeriod() for k in (-1, 0, 1)] if surf.IsVPeriodic() else [v]
    return any(BRepClass_FaceClassifier(face.wrapped, gp_Pnt2d(a, b), 1e-6).State() in (TopAbs_IN, TopAbs_ON)
               for a in us for b in vs)


def _closest_faces(ba, bb):
    """The faces of the two bodies nearest to each other."""
    best = None
    for fa in ba.faces():
        for fb in bb.faces():
            d = fa.distance_to(fb)
            if best is None or d < best[0]:
                best = (d, fa, fb)
    return best[1], best[2]


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
    ga, ka = _oriented_surface(fa)
    gb, kb = _oriented_surface(fb)
    oa = Geom_OffsetSurface(ga, sa * ka * r)
    ob = Geom_OffsetSurface(gb, sb * kb * r)
    inter = GeomAPI_IntSS(oa, ob, 1e-7)
    if not inter.IsDone() or inter.NbLines() == 0:
        raise ValueError("the faces have no fillet of radius %g on these sides (the offset surfaces do not meet; "
                         "try Flip or a smaller radius)" % r)
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
            pa = _project(ga, (p.X(), p.Y(), p.Z()))
            pb = _project(gb, (p.X(), p.Y(), p.Z()))
            return (pa is not None and pb is not None and abs(pa[3] - r) < 1e-3 * max(r, 1) + 1e-6 and
                    abs(pb[3] - r) < 1e-3 * max(r, 1) + 1e-6 and _inside(fa, ga, pa[1:3]) and _inside(fb, gb, pb[1:3]))
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
        f1, a1, b1 = _arc_patch(cu, t0, tm, ga, gb, r, m // 2)
        f2, a2, b2 = _arc_patch(cu, tm, t1, ga, gb, r, m // 2)
        return [f1, f2], [a1, a2], [b1, b2]
    face, _, _ = _arc_patch(cu, ta, tb, ga, gb, r, m)
    # trimming curves: the contact curves extended a little beyond the face boundaries
    ext = 0.02 * (tb - ta)
    pts_a, pts_b = [], []
    for k in range(m + 1):
        p = cu.Value(ta - ext + (tb - ta + 2 * ext) * k / m)
        p = (p.X(), p.Y(), p.Z())
        qa, qb = _project(ga, p), _project(gb, p)
        if qa is None or qb is None:
            continue
        pts_a.append(qa[0])
        pts_b.append(qb[0])
    ea = Edge(BRepBuilderAPI_MakeEdge(_interp(pts_a)).Edge())
    eb = Edge(BRepBuilderAPI_MakeEdge(_interp(pts_b)).Edge())
    return [face], [ea], [eb]


def _arc_patch(cu, ta, tb, ga, gb, r, m, nu=9):
    """Fillet patch along the spine cu from ta to tb: at each spine point the circular arc of radius r from the
    contact point on surface A to the one on surface B (the shorter arc), fitted with a B-spline surface. Returns
    (face, contact edge A, contact edge B); the contact edges are the boundary curves of the face."""
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
        A = np.array(_project(ga, tuple(P))[0]) - P
        B = np.array(_project(gb, tuple(P))[0]) - P
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
