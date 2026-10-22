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
    solid = None
    try:
        op = BRepOffset_MakeSimpleOffset(body.wrapped, d)
        op.SetBuildSolidFlag(True)
        op.Perform()
        if op.IsDone():
            solid = Shape.cast(op.GetResultShape())
    except Exception:
        solid = None
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
        return [proj(p + (q - p) * (i / m)) for i in range(m + 1)]

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

    outer = BRepBuilderAPI_MakeEdge(bspl(Q)).Edge()
    s1 = BRepBuilderAPI_MakeEdge(bspl(side(P[-1], Q[-1]))).Edge()
    s2 = BRepBuilderAPI_MakeEdge(bspl(side(Q[0], P[0]))).Edge()
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
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
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
    order = {"gap": 0, "pointgap": 1, "nonmanifold": 2, "free": 3, "smallface": 4, "smalledge": 5}
    issues.sort(key=lambda x: (order.get(x["kind"], 9), -x.get("value", 0)))
    summary = {"faces": len(faces), "edges": len(all_edges), "vertices": len(body.vertices()), "free_edges": len(free),
               "free_length": round(total_free, 3), "area": round(body.area, 3), "valid": valid, "shells": len(closed), "closed_shells": sum(1 for c in closed if c),
               "gaps": sum(1 for x in issues if x["kind"] in ("gap", "pointgap")), "nonmanifold": len(nonman)}
    return {"summary": summary, "issues": issues}
