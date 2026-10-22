# -*- coding: utf-8 -*-
"""Hidden-line projection, section cut and hatching with OpenCascade (OCP).

View geometry is returned in view coordinates (model mm, x to the right,
y up) as primitives:
    ("L", x1, y1, x2, y2)          line
    ("C", cx, cy, r)               full circle
    ("A", cx, cy, r, a0, a1)       arc, counter-clockwise from a0 to a1 (deg)
    ("P", [(x, y), ...])           polyline
"""
import math

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepLib import BRepLib
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line, GeomAbs_Plane
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.BRep import BRep_Builder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

def _static(cls, name):
    """OCP static methods carry a '_s' suffix in older releases."""
    return getattr(cls, name + "_s", None) or getattr(cls, name)


_to_edge = _static(TopoDS, "Edge")
_to_face = _static(TopoDS, "Face")
_bnd_add = _static(BRepBndLib, "Add")
_build_curves3d = _static(BRepLib, "BuildCurves3d")


# view name -> (direction toward the viewer, x direction on paper)
VIEWS = {
    "front": ((0, -1, 0), (1, 0, 0)),
    "right": ((1, 0, 0), (0, 1, 0)),      # seen from +X, placed left of front (first angle)
    "top": ((0, 0, 1), (1, 0, 0)),        # seen from +Z, placed below front (first angle)
    "left": ((-1, 0, 0), (0, -1, 0)),     # seen from -X
    "bottom": ((0, 0, -1), (1, 0, 0)),
    "rear": ((0, 1, 0), (-1, 0, 0)),
    "iso": ((1, -1, 1), (1, 1, 0)),
}


def _norm(v):
    m = math.sqrt(sum(c * c for c in v))
    return tuple(c / m for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def frame(direction, xdir):
    d = _norm(direction)
    x = _norm(xdir)
    y = _cross(d, x)
    return d, x, y


def bounding_box(shape):
    b = Bnd_Box()
    _bnd_add(shape, b)
    mn, mx = b.CornerMin(), b.CornerMax()
    return mn.X(), mn.Y(), mn.Z(), mx.X(), mx.Y(), mx.Z()


# --------------------------------------------------------------------------- edges -> primitives

def _edge_prims(edge, deflection):
    """Primitives for one projected edge (z = 0 plane of the projector)."""
    try:
        c = BRepAdaptor_Curve(edge)
    except Exception:
        return []
    t = c.GetType()
    u0, u1 = c.FirstParameter(), c.LastParameter()
    if t == GeomAbs_Line:
        p0, p1 = c.Value(u0), c.Value(u1)
        return [("L", p0.X(), p0.Y(), p1.X(), p1.Y())]
    if t == GeomAbs_Circle:
        circ = c.Circle()
        ctr = circ.Location()
        r = circ.Radius()
        if abs(u1 - u0) >= 2 * math.pi - 1e-6:
            return [("C", ctr.X(), ctr.Y(), r)]
        p0, p1 = c.Value(u0), c.Value(u1)
        a0 = math.degrees(math.atan2(p0.Y() - ctr.Y(), p0.X() - ctr.X()))
        a1 = math.degrees(math.atan2(p1.Y() - ctr.Y(), p1.X() - ctr.X()))
        if circ.Axis().Direction().Z() < 0:
            a0, a1 = a1, a0
        return [("A", ctr.X(), ctr.Y(), r, a0, a1)]
    try:
        disc = GCPnts_QuasiUniformDeflection(c, deflection, u0, u1)
        pts = [disc.Value(i) for i in range(1, disc.NbPoints() + 1)]
    except Exception:
        pts = [c.Value(u0 + (u1 - u0) * k / 32.0) for k in range(33)]
    return [("P", [(p.X(), p.Y()) for p in pts])]


def _compound_prims(comp, deflection):
    out = []
    if comp is None or comp.IsNull():
        return out
    _build_curves3d(comp)
    ex = TopExp_Explorer(comp, TopAbs_EDGE)
    while ex.More():
        out += _edge_prims(_to_edge(ex.Current()), deflection)
        ex.Next()
    return out


def hlr(shape, direction, xdir, hidden=False, smooth=False, deflection=None):
    """Hidden-line removal. Returns dict with 'visible' and 'hidden' primitive lists."""
    d, x, _ = frame(direction, xdir)
    if deflection is None:
        x0, y0, z0, x1, y1, z1 = bounding_box(shape)
        deflection = max(x1 - x0, y1 - y0, z1 - z0) * 2e-4
    algo = HLRBRep_Algo()
    algo.Add(shape)
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*d), gp_Dir(*x))
    algo.Projector(HLRAlgo_Projector(ax))
    algo.Update()
    algo.Hide()
    h = HLRBRep_HLRToShape(algo)
    vis = _compound_prims(h.VCompound(), deflection)
    vis += _compound_prims(h.OutLineVCompound(), deflection)
    if smooth:
        vis += _compound_prims(h.Rg1LineVCompound(), deflection)
    hid = []
    if hidden:
        hid = _compound_prims(h.HCompound(), deflection)
        hid += _compound_prims(h.OutLineHCompound(), deflection)
    return {"visible": vis, "hidden": hid}


# --------------------------------------------------------------------------- section

def cut_half(shape, origin, normal):
    """Part of shape on the side of the plane opposite to normal (normal points toward the viewer)."""
    x0, y0, z0, x1, y1, z1 = bounding_box(shape)
    big = 2.0 * max(x1 - x0, y1 - y0, z1 - z0) + 10.0
    n = _norm(normal)
    # box with one face on the plane, extending away from the viewer (direction -n)
    _, u, v = frame(n, _any_perp(n))
    corner = [origin[i] - n[i] * big - u[i] * big - v[i] * big for i in range(3)]
    ax = gp_Ax2(gp_Pnt(*corner), gp_Dir(*n), gp_Dir(*u))
    box = BRepPrimAPI_MakeBox(ax, 2 * big, 2 * big, big).Shape()
    # one boolean per solid: a compound of touching or overlapping solids (assembly) fails as one argument
    solids = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        solids.append(ex.Current())
        ex.Next()
    if len(solids) <= 1:
        com = BRepAlgoAPI_Common(shape, box)
        com.Build()
        return com.Shape()
    out = TopoDS_Compound()
    bld = BRep_Builder()
    bld.MakeCompound(out)
    for so in solids:
        com = BRepAlgoAPI_Common(so, box)
        com.Build()
        if com.IsDone():
            r = com.Shape()
            if not Bnd_Box_is_void(r):
                bld.Add(out, r)
    return out


def Bnd_Box_is_void(shape):
    b = Bnd_Box()
    _bnd_add(shape, b)
    return b.IsVoid()


def _any_perp(n):
    a = (1, 0, 0) if abs(n[0]) < 0.9 else (0, 1, 0)
    return _norm(_cross(n, a))


def section_faces(cut, origin, normal, tol=1e-4):
    """Faces of the cut lying in the section plane."""
    n = _norm(normal)
    if Bnd_Box_is_void(cut):
        return []
    x0, y0, z0, x1, y1, z1 = bounding_box(cut)
    size = max(x1 - x0, y1 - y0, z1 - z0, 1.0)
    faces = []
    ex = TopExp_Explorer(cut, TopAbs_FACE)
    while ex.More():
        f = _to_face(ex.Current())
        s = BRepAdaptor_Surface(f)
        if s.GetType() == GeomAbs_Plane:
            pl = s.Plane()
            dd = pl.Axis().Direction()
            if abs(abs(dd.X() * n[0] + dd.Y() * n[1] + dd.Z() * n[2]) - 1.0) < 1e-6:
                p = pl.Location()
                dist = (p.X() - origin[0]) * n[0] + (p.Y() - origin[1]) * n[1] + (p.Z() - origin[2]) * n[2]
                if abs(dist) < tol * size:
                    faces.append(f)
        ex.Next()
    return faces


def face_segments(face, direction, xdir, deflection):
    """Boundary of a face as 2D segments in view coordinates."""
    _, x, y = frame(direction, xdir)
    segs = []
    ex = TopExp_Explorer(face, TopAbs_EDGE)
    while ex.More():
        e = _to_edge(ex.Current())
        c = BRepAdaptor_Curve(e)
        u0, u1 = c.FirstParameter(), c.LastParameter()
        if c.GetType() == GeomAbs_Line:
            pts = [c.Value(u0), c.Value(u1)]
        else:
            try:
                disc = GCPnts_QuasiUniformDeflection(c, deflection, u0, u1)
                pts = [disc.Value(i) for i in range(1, disc.NbPoints() + 1)]
            except Exception:
                pts = [c.Value(u0 + (u1 - u0) * k / 64.0) for k in range(65)]
        p2 = [(p.X() * x[0] + p.Y() * x[1] + p.Z() * x[2], p.X() * y[0] + p.Y() * y[1] + p.Z() * y[2]) for p in pts]
        segs += list(zip(p2[:-1], p2[1:]))
        ex.Next()
    return segs


def hatch(segments, spacing, angle_deg=45.0):
    """Hatch lines clipped to the region bounded by segments (even-odd rule)."""
    if not segments or spacing <= 0:
        return []
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    # s along the hatch direction, t across
    st = [((p[0] * ca + p[1] * sa, -p[0] * sa + p[1] * ca),
           (q[0] * ca + q[1] * sa, -q[0] * sa + q[1] * ca)) for p, q in segments]
    tmin = min(min(p[1], q[1]) for p, q in st)
    tmax = max(max(p[1], q[1]) for p, q in st)
    out = []
    t = math.floor(tmin / spacing) * spacing + spacing * 0.5
    while t < tmax:
        xs = []
        for (s1, t1), (s2, t2) in st:
            if t1 == t2:
                continue
            lo, hi = (t1, t2) if t1 < t2 else (t2, t1)
            if lo <= t < hi:
                xs.append(s1 + (t - t1) * (s2 - s1) / (t2 - t1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            sA, sB = xs[i], xs[i + 1]
            out.append(("L", sA * ca - t * sa, sA * sa + t * ca, sB * ca - t * sa, sB * sa + t * ca))
        t += spacing
    return out


def solids_of(shape):
    out = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def fused(shape):
    """One shape for the hidden-line views of an assembly: the solids fused, so that faces inside other
    solids (a pin in a hole) are not drawn. Returns the input when there is one solid or the fuse fails."""
    solids = solids_of(shape)
    if len(solids) <= 1:
        return shape
    try:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
        try:
            from OCP.TopTools import TopTools_ListOfShape as ShapeList
        except ImportError:                       # OCCT 8
            from OCP.collections import List_TopoDS_Shape as ShapeList
        args, tools = ShapeList(), ShapeList()
        args.Append(solids[0])
        for so in solids[1:]:
            tools.Append(so)
        op = BRepAlgoAPI_Fuse()
        op.SetArguments(args)
        op.SetTools(tools)
        op.SetRunParallel(True)
        op.Build()
        if op.IsDone() and not Bnd_Box_is_void(op.Shape()):
            r = op.Shape()
            b0, b1 = bounding_box(shape), bounding_box(r)
            tol = 1e-3 * max(b0[3] - b0[0], b0[4] - b0[1], b0[5] - b0[2], 1.0)
            if all(abs(b0[i] - b1[i]) < tol for i in range(6)) and solids_of(r):
                return r
    except Exception:
        pass
    return shape


def section_view(shape, origin, direction, xdir, hidden=False, deflection=None):
    """Section seen along -direction through origin. Returns visible, hidden and face segments
    (section_segments: all; section_groups: one segment list per solid, for the hatching)."""
    cut = cut_half(shape, origin, direction)
    res = hlr(fused(cut), direction, xdir, hidden=hidden, deflection=deflection)
    x0, y0, z0, x1, y1, z1 = bounding_box(shape)
    defl = deflection or max(x1 - x0, y1 - y0, z1 - z0) * 2e-4
    groups = []
    parts = solids_of(cut) or [cut]
    for part in parts:
        segs = []
        for f in section_faces(part, origin, direction):
            segs += face_segments(f, direction, xdir, defl)
        if segs:
            groups.append(segs)
    res["section_segments"] = [sg for g in groups for sg in g]
    res["section_groups"] = groups
    return res


# --------------------------------------------------------------------------- helpers

def prims_bbox(prims):
    xs, ys = [], []
    for p in prims:
        k = p[0]
        if k == "L":
            xs += [p[1], p[3]]
            ys += [p[2], p[4]]
        elif k == "C":
            xs += [p[1] - p[3], p[1] + p[3]]
            ys += [p[2] - p[3], p[2] + p[3]]
        elif k == "A":
            cx, cy, r, a0, a1 = p[1:]
            pts = _arc_points(cx, cy, r, a0, a1, 16)
            xs += [q[0] for q in pts]
            ys += [q[1] for q in pts]
        elif k == "P":
            xs += [q[0] for q in p[1]]
            ys += [q[1] for q in p[1]]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return min(xs), min(ys), max(xs), max(ys)


def _arc_points(cx, cy, r, a0, a1, n):
    span = (a1 - a0) % 360.0
    if span == 0:
        span = 360.0
    # include axis extremes
    angs = [a0 + span * k / n for k in range(n + 1)]
    for q in (0, 90, 180, 270):
        if (q - a0) % 360.0 <= span:
            angs.append(q)
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in angs]


def project_point(p, direction, xdir):
    _, x, y = frame(direction, xdir)
    return _dot(p, x), _dot(p, y)


# --------------------------------------------------------------------------- parallel execution

def write_brep(shape, path):
    from OCP.BRepTools import BRepTools
    _static(BRepTools, "Write")(shape, path)
    return path


def read_brep(path):
    from OCP.BRepTools import BRepTools
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Shape
    s = TopoDS_Shape()
    _static(BRepTools, "Read")(s, path, BRep_Builder())
    return s


def run_job(job):
    """Worker entry point. job: (brep_path, kind, args). kind 'hlr' or 'section'."""
    path, kind, args = job
    shape = read_brep(path)
    if kind == "hlr":
        direction, xdir, hidden, smooth = args
        return hlr(fused(shape), direction, xdir, hidden=hidden, smooth=smooth)
    origin, direction, xdir, hidden = args
    return section_view(shape, origin, direction, xdir, hidden=hidden)
