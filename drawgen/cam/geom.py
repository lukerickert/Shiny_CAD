# -*- coding: utf-8 -*-
"""Geometry of the CAM operations: shapely polygons of part sections and faces, floor regions, prisms and
Boolean helpers (OpenCascade), the height map of the part for the 3D operations, text outlines."""
import math

EPS = 0.01           # mm above a floor or a bottom where the part section is taken
ARC_SEGS = 24        # polyline segments per full circle of arcs in the view data and the removed solids
PATH_SEGS = 12       # segments per quarter circle of the offset paths
TOL_VOL = 1e-3       # mm^3: volumes below this count as zero


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def sag(R):
    """Largest distance between the chords of an offset path and the circle they replace (quarter circles of
    PATH_SEGS segments); added to the offsets so that the chords stay clear of the wall."""
    return R * (1.0 - math.cos(math.pi / 4.0 / PATH_SEGS))


# --------------------------------------------------------------------------- shapely

def polys(geom):
    """Polygons of a shapely geometry (empty parts dropped)."""
    from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom] if geom.area > 1e-9 else []
    if isinstance(geom, (MultiPolygon, GeometryCollection)):
        out = []
        for g in geom.geoms:
            out += polys(g)
        return out
    return []


def lines(geom):
    """LineStrings of a shapely geometry."""
    from shapely.geometry import LineString, MultiLineString, GeometryCollection
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom] if geom.length > 1e-9 else []
    if isinstance(geom, (MultiLineString, GeometryCollection)):
        out = []
        for g in geom.geoms:
            out += lines(g)
        return out
    return []


def ring_pts(ring):
    pts = list(ring.coords)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return [(float(x), float(y)) for x, y in pts]


def loops_of(geom):
    """Closed loops [(x, y), ...] of the boundary of a polygon geometry: exteriors and holes."""
    out = []
    for p in polys(geom):
        out.append(ring_pts(p.exterior))
        for h in p.interiors:
            out.append(ring_pts(h))
    return [l for l in out if len(l) > 2]


def poly_face(p, z):
    """build123d Face at height z of a shapely polygon with holes."""
    from build123d import Face, Wire, Vector
    def ring(r):
        return Wire.make_polygon([Vector(x, y, z) for x, y in ring_pts(r)], close=True)
    outer = ring(p.exterior)
    inner = [ring(h) for h in p.interiors if len(h.coords) > 3]
    return Face(outer, inner) if inner else Face(outer)


def prism(geom, z0, z1, simplify=0.005):
    """Solid between z0 and z1 over a polygon geometry (None when empty)."""
    from build123d import Solid, Vector
    from . import tools
    sols = []
    for p in polys(geom):
        q = p.simplify(simplify, preserve_topology=True) if simplify else p
        for pp in polys(q):
            sols.append(Solid.extrude(poly_face(pp, z0), Vector(0, 0, z1 - z0)))
    if not sols:
        return None
    return tools.fuse(sols) if len(sols) > 1 else sols[0]


LAP = 0.002      # mm added to the tool radius of a level region: adjacent regions overlap instead of touching


def level_region(lines_, R):
    """Polygon swept in the XY plane by a tool of radius R along polylines (a single point: a disc), the radius
    plus LAP so that the regions of adjacent levels overlap (a Boolean between solids with coincident faces is
    unreliable)."""
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    parts = []
    for pl in lines_:
        if len(pl) == 1:
            parts.append(Point(pl[0]).buffer(R + LAP, ARC_SEGS // 4))
        elif len(pl) > 1:
            parts.append(LineString(pl).buffer(R + LAP, ARC_SEGS // 4))
    return unary_union(parts) if parts else None


def arc_pts(a, b, c, cw, n=None):
    """Points of the arc from a to b about c (XY), Z interpolated, the start point left out."""
    ax, ay = a[0] - c[0], a[1] - c[1]
    bx, by = b[0] - c[0], b[1] - c[1]
    r = math.hypot(ax, ay)
    t0, t1 = math.atan2(ay, ax), math.atan2(by, bx)
    d = t1 - t0
    if cw:
        while d > -1e-9:
            d -= 2 * math.pi
    else:
        while d < 1e-9:
            d += 2 * math.pi
    n = n or max(2, int(math.ceil(abs(d) / (2 * math.pi) * ARC_SEGS)))
    out = []
    for i in range(1, n + 1):
        t = t0 + d * i / n
        out.append((c[0] + r * math.cos(t), c[1] + r * math.sin(t), a[2] + (b[2] - a[2]) * i / n))
    return out


# --------------------------------------------------------------------------- OpenCascade

def bbox(shape):
    from .. import part as P
    return P.exact_bbox(shape)


def volume(sh):
    try:
        return sum(abs(s.volume) for s in sh.solids()) if sh is not None else 0.0
    except Exception:
        return 0.0


def solids_only(shape, vmin=1e-6):
    """The solids of the shape with a volume above vmin (mm^3), as one solid or a compound; None when there is
    none (degenerate slivers of a Boolean dropped)."""
    from build123d import Compound
    if shape is None:
        return None
    sols = [s for s in shape.solids() if abs(s.volume) > vmin]
    if not sols:
        return None
    if len(sols) == 1:
        return sols[0]
    return Compound(children=sols)


def _solid_list(shapes):
    """The solids of the shapes (a compound tool given as its solids)."""
    out = []
    for t in shapes:
        sols = list(t.solids()) if hasattr(t, "solids") else [t]
        out += sols if sols else [t]
    return out


def cut(target, tools_, fuzzy=1e-5):
    """The target less the tool solids (ValueError when the Boolean fails)."""
    from .. import part as P
    r = P._fuzzy_op("subtract", [target], _solid_list(tools_), fuzzy)
    if r is None:
        raise ValueError("the stock could not be cut by the swept tool")
    return solids_only(r) or r


def common_volume(a, b, fuzzy=1e-5):
    """Volume (mm^3) of the common part of two shapes (None when the Boolean fails)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from build123d import Shape
    from ..surfaces import _shape_list
    if a is None or b is None:
        return 0.0
    x, y = _shape_list(), _shape_list()
    for sa in _solid_list([a]):
        x.Append(BRepBuilderAPI_Copy(sa.wrapped).Shape())
    for sb in _solid_list([b]):
        y.Append(BRepBuilderAPI_Copy(sb.wrapped).Shape())
    op = BRepAlgoAPI_Common()
    op.SetArguments(x)
    op.SetTools(y)
    op.SetFuzzyValue(fuzzy)
    op.Build()
    if not op.IsDone():
        return None
    return sum(abs(s.volume) for s in Shape.cast(op.Shape()).solids())


def common_shape(a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from build123d import Shape
    op = BRepAlgoAPI_Common(a.wrapped, b.wrapped)
    op.Build()
    if not op.IsDone():
        return None
    return Shape.cast(op.Shape())


# --------------------------------------------------------------------------- faces and sections of the part

def _edge_pts(e):
    if e.geom_type.name == "LINE":
        n = 1
    else:
        n = max(8, min(200, int(e.length / 0.5) + 8))
    return [e.position_at(i / float(n)) for i in range(n + 1)]


def edge_polyline(e):
    """Points (x, y, z) along an edge."""
    return [(p.X, p.Y, p.Z) for p in _edge_pts(e)]


def wire_ring(w):
    """Closed ring [(x, y)] of a wire (its edges joined end to end, projected on XY)."""
    from shapely.ops import linemerge
    from shapely.geometry import LineString, MultiLineString
    ls = []
    for e in w.edges():
        pts = [(round(p.X, 6), round(p.Y, 6)) for p in _edge_pts(e)]
        pts = [q for i, q in enumerate(pts) if i == 0 or q != pts[i - 1]]
        if len(pts) > 1:
            ls.append(LineString(pts))
    if not ls:
        return []
    m = linemerge(MultiLineString(ls)) if len(ls) > 1 else ls[0]
    if m.geom_type != "LineString":
        m = max(m.geoms, key=lambda g: g.length)
    return list(m.coords)


def face_poly(fc, holes=None):
    """Polygon (XY) of a horizontal planar face: its outer wire with the inner wires as holes (holes: the inner
    wires to use; None: all)."""
    from shapely.geometry import Polygon
    outer = wire_ring(fc.outer_wire())
    rings = [wire_ring(w) for w in (fc.inner_wires() if holes is None else holes)]
    p = Polygon(outer, [h for h in rings if len(h) > 2])
    if not p.is_valid:
        p = p.buffer(0)
    return p


def face_outline(fc):
    """Polygon (XY) of the projection of any face (its outer wire; inner wires as holes)."""
    return face_poly(fc)


def section_polys(shape, z):
    """Polygons (XY) of the section of the solid at the height z (union)."""
    from build123d import Face, Plane, Vector, Compound
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from shapely.ops import unary_union
    from shapely.geometry import Polygon
    bb = shape.bounding_box()
    size = bb.diagonal * 2.0 + 10.0
    c = (bb.min + bb.max) * 0.5
    face = Face.make_rect(size, size, Plane(origin=Vector(c.X, c.Y, z), z_dir=(0, 0, 1)))
    com = BRepAlgoAPI_Common(shape.wrapped, face.wrapped)
    com.Build()
    ps = []
    for fc in Compound(com.Shape()).faces():
        try:
            ps.append(face_poly(fc))
        except Exception:
            continue
    return unary_union(ps) if ps else Polygon()


def top_z_at(shape, x, y, default=None):
    """Z of the top surface of the solid under the point (x, y): the highest intersection of the vertical line
    through the point with the faces of the solid (default when the line misses the solid)."""
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.gp import gp_Lin, gp_Pnt, gp_Dir
    bb = bbox(shape)
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape.wrapped, 1e-6)
    inter.Perform(gp_Lin(gp_Pnt(x, y, bb[5] + 1.0), gp_Dir(0, 0, -1)), 0.0, bb[5] - bb[2] + 2.0)
    if not inter.IsDone() or inter.NbPnt() == 0:
        return default
    return max(inter.Pnt(i).Z() for i in range(1, inter.NbPnt() + 1))


def silhouette(shape):
    """Outline (XY) of the solid: the union of the sections at the Z of every vertex and in between."""
    from shapely.ops import unary_union
    bb = bbox(shape)
    zs = sorted({round(v.Z, 4) for v in shape.vertices()})
    levels = []
    for a, b in zip(zs, zs[1:]):
        levels.append((a + b) / 2.0)
    levels += [bb[2] + EPS, bb[5] - EPS]
    return unary_union([section_polys(shape, z) for z in levels if bb[2] < z < bb[5]])


def face_kinds(shape, undercuts=()):
    """Kind of every face of the solid, in the order of shape.faces(): "floor" (planar, normal up), "wall"
    (planar, vertical), "hole" (cylindrical, vertical axis), "undercut" (index in undercuts), "other"."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from .. import part as P
    out = []
    und = set(undercuts)
    for i, fc in enumerate(shape.faces()):
        kind = "other"
        try:
            if i in und:
                kind = "undercut"
            else:
                ad = BRepAdaptor_Surface(fc.wrapped)
                t = ad.GetType()
                if t == GeomAbs_Plane:
                    n = P._normal_at(fc, fc.center())
                    if n.Z > 0.999:
                        kind = "floor"
                    elif abs(n.Z) < 1e-3:
                        kind = "wall"
                elif t == GeomAbs_Cylinder:
                    d = ad.Cylinder().Axis().Direction()
                    if abs(abs(d.Z()) - 1) < 1e-6:
                        kind = "hole"
        except Exception:
            pass
        out.append(kind)
    return out


def floor_info(shape, fc):
    """Geometry of a floor face: z, polygon (islands kept as holes, pockets and holes going down filled in), open
    edges (polylines of the outer wire whose other face does not rise above the floor)."""
    from .. import part as P
    from build123d import Vector
    c = fc.center()
    n = P._normal_at(fc, c)
    if abs(n.Z) < 0.999:
        raise ValueError("the face is not horizontal")
    if n.Z < 0:
        raise ValueError("the face points downward")
    z = c.Z
    tp = P._topo(shape)

    def rises(e):
        for g in tp.faces_of_edge(e):
            if g.wrapped.IsSame(fc.wrapped):
                continue
            if g.bounding_box().max.Z > z + 1e-4 and g.center().Z > z + 1e-6:
                return True
        return False
    islands = [w for w in fc.inner_wires() if any(rises(e) for e in w.edges())]
    poly = face_poly(fc, islands)
    open_lines = []
    for e in fc.outer_wire().edges():
        if not rises(e):
            open_lines.append([(p.X, p.Y) for p in _edge_pts(e)])
    return {"z": z, "poly": poly, "open": open_lines, "n": Vector(n.X, n.Y, n.Z)}


def hole_info(fc):
    """Centre, radius and Z range of a cylindrical face with a vertical axis."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    ad = BRepAdaptor_Surface(fc.wrapped)
    if ad.GetType() != GeomAbs_Cylinder:
        raise ValueError("the face is not cylindrical")
    cy = ad.Cylinder()
    ax = cy.Axis()
    d = ax.Direction()
    if abs(abs(d.Z()) - 1) > 1e-6:
        raise ValueError("the hole axis is not vertical")
    L = ax.Location()
    zs = [v.Z for v in fc.vertices()]
    return {"x": L.X(), "y": L.Y(), "r": cy.Radius(), "z0": min(zs), "z1": max(zs)}


def wall_outline(shape, faces):
    """Outline (XY) of the region bounded by picked vertical wall faces: the section of the solid just below the
    top of the walls, kept where it touches the walls, with the walls' outline."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union, polygonize
    ls = []
    zs = []
    for fc in faces:
        for e in fc.edges():
            pts = [(p.X, p.Y) for p in _edge_pts(e)]
            pts = [q for i, q in enumerate(pts) if i == 0 or math.dist(q, pts[i - 1]) > 1e-6]
            if len(pts) > 1:
                ls.append(LineString(pts))
        zs += [v.Z for v in fc.vertices()]
    if not ls:
        return None, None
    merged = unary_union(ls)
    ps = list(polygonize(merged))
    return (unary_union(ps) if ps else None), (min(zs), max(zs))


# --------------------------------------------------------------------------- height map of the part

class HeightMap(object):
    """Grid of the highest Z of the part at every (x, y) (numpy), from the tessellation of the solid; the
    tool-centre height map of a tool (the lowest Z the tool axis may stand at without the tool entering the
    part) by dilation with the tool profile; contours at a height (marching squares)."""

    def __init__(self, x0, y0, nx, ny, step, z):
        self.x0, self.y0, self.nx, self.ny, self.step = x0, y0, nx, ny, step
        self.z = z                               # numpy array [ny, nx]

    @classmethod
    def of_shape(cls, shape, step, margin=0.0, zfloor=None, bounds=None):
        """Height map of a solid (or a compound): the highest Z at every grid point; zfloor where the part is not."""
        import numpy as np
        from .. import part as P
        bb = bbox(shape)
        if bounds is not None:
            bb = [bounds[0], bounds[1], bb[2], bounds[2], bounds[3], bb[5]]
        x0, y0 = bb[0] - margin, bb[1] - margin
        nx = int(math.ceil((bb[3] - bb[0] + 2 * margin) / step)) + 1
        ny = int(math.ceil((bb[4] - bb[1] + 2 * margin) / step)) + 1
        zf = bb[2] - 1.0 if zfloor is None else zfloor
        z = np.full((ny, nx), zf, dtype=float)
        m = P.mesh(shape, tol=min(step / 2.0, 0.05))
        V = np.array(m["vertices"], dtype=float)
        T = np.array(m["triangles"], dtype=int).reshape(-1, 3)
        hm = cls(x0, y0, nx, ny, step, z)
        hm._raster(V, T)
        return hm

    def _raster(self, V, T):
        """Highest Z of every triangle at the grid points it covers."""
        import numpy as np
        z = self.z
        s = self.step
        for tri in T:
            a, b, c = V[tri[0]], V[tri[1]], V[tri[2]]
            xmin, xmax = min(a[0], b[0], c[0]), max(a[0], b[0], c[0])
            ymin, ymax = min(a[1], b[1], c[1]), max(a[1], b[1], c[1])
            i0 = max(0, int(math.floor((xmin - self.x0) / s)))
            i1 = min(self.nx - 1, int(math.ceil((xmax - self.x0) / s)))
            j0 = max(0, int(math.floor((ymin - self.y0) / s)))
            j1 = min(self.ny - 1, int(math.ceil((ymax - self.y0) / s)))
            if i1 < i0 or j1 < j0:
                continue
            xs = self.x0 + s * np.arange(i0, i1 + 1)
            ys = self.y0 + s * np.arange(j0, j1 + 1)
            X, Y = np.meshgrid(xs, ys)
            d = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
            if abs(d) < 1e-12:
                # a vertical triangle: its edges on the grid
                continue
            l1 = ((b[0] - X) * (c[1] - Y) - (c[0] - X) * (b[1] - Y)) / d
            l2 = ((c[0] - X) * (a[1] - Y) - (a[0] - X) * (c[1] - Y)) / d
            l3 = 1.0 - l1 - l2
            tol = -1e-6 - 1e-9
            inside = (l1 >= tol) & (l2 >= tol) & (l3 >= tol)
            if not inside.any():
                # the triangle is smaller than a cell: its highest vertex at the nearest grid point
                for p in (a, b, c):
                    i = int(round((p[0] - self.x0) / s))
                    j = int(round((p[1] - self.y0) / s))
                    if 0 <= i < self.nx and 0 <= j < self.ny and abs(p[0] - (self.x0 + i * s)) <= s and abs(p[1] - (self.y0 + j * s)) <= s:
                        z[j, i] = max(z[j, i], p[2])
                continue
            Zt = l1 * a[2] + l2 * b[2] + l3 * c[2]
            sub = z[j0:j1 + 1, i0:i1 + 1]
            np.maximum(sub, np.where(inside, Zt, -1e30), out=sub)

    def tool_map(self, tool):
        """Height map of the tool centre: the lowest Z of the lowest point of the tool at every grid point such
        that the tool touches the part nowhere (the surface dilated by the inverted tool profile, with one grid
        cell of margin)."""
        import numpy as np
        from . import tools as TB
        R = TB.radius(tool)
        s = self.step
        # one cell of margin: the part between the grid points lifts the tool as if it were one cell nearer
        n = int(math.ceil((R + s) / s))
        out = self.z.copy()
        ny, nx = self.z.shape
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                d = math.hypot(di * s, dj * s)
                off = TB.bottom_offset(tool, max(0.0, d - s))
                if off is None:
                    continue
                # the part point at (i + di, j + dj) lifts the tool at (i, j) to z - off
                src = self.z[max(0, dj):ny + min(0, dj), max(0, di):nx + min(0, di)] - off
                dst = out[max(0, -dj):ny + min(0, -dj), max(0, -di):nx + min(0, -di)]
                np.maximum(dst, src, out=dst)
        return HeightMap(self.x0, self.y0, self.nx, self.ny, s, out)

    def at(self, x, y):
        """Value at (x, y) (bilinear; the border value outside)."""
        import numpy as np
        fx = (x - self.x0) / self.step
        fy = (y - self.y0) / self.step
        i = int(np.clip(math.floor(fx), 0, self.nx - 2))
        j = int(np.clip(math.floor(fy), 0, self.ny - 2))
        tx = min(1.0, max(0.0, fx - i))
        ty = min(1.0, max(0.0, fy - j))
        z = self.z
        return (z[j, i] * (1 - tx) + z[j, i + 1] * tx) * (1 - ty) + (z[j + 1, i] * (1 - tx) + z[j + 1, i + 1] * tx) * ty

    def contours(self, level):
        """Closed loops [(x, y), ...] of the boundary of the region z <= level (marching squares)."""
        import numpy as np
        from shapely.geometry import LineString, MultiLineString
        from shapely.ops import linemerge
        # a border of one cell above every level closes the loops of a region reaching the edge of the map
        z = np.pad(self.z, 1, constant_values=1e9)
        ny, nx = z.shape
        inside = z <= level
        segs = []
        s = self.step

        def interp(i0, j0, i1, j1):
            za, zb = z[j0, i0], z[j1, i1]
            t = 0.5 if abs(zb - za) < 1e-12 else (level - za) / (zb - za)
            t = min(1.0, max(0.0, t))
            return (self.x0 + (i0 - 1 + (i1 - i0) * t) * s, self.y0 + (j0 - 1 + (j1 - j0) * t) * s)
        # cell corners: (i, j), (i+1, j), (i+1, j+1), (i, j+1)
        for j in range(ny - 1):
            for i in range(nx - 1):
                c = (inside[j, i], inside[j, i + 1], inside[j + 1, i + 1], inside[j + 1, i])
                if all(c) or not any(c):
                    continue
                code = (c[0] << 0) | (c[1] << 1) | (c[2] << 2) | (c[3] << 3)
                e = {0: interp(i, j, i + 1, j), 1: interp(i + 1, j, i + 1, j + 1), 2: interp(i, j + 1, i + 1, j + 1), 3: interp(i, j, i, j + 1)}
                for a, b in _MS_TABLE[code]:
                    segs.append(LineString([e[a], e[b]]))
        if not segs:
            return []
        m = linemerge(MultiLineString(segs))
        out = []
        for l in (m.geoms if hasattr(m, "geoms") else [m]):
            pts = [(float(x), float(y)) for x, y in l.coords]
            if len(pts) > 2:
                if math.dist(pts[0], pts[-1]) < 1e-9:
                    pts = pts[:-1]
                out.append(pts)
        return out

    def region(self, level):
        """Polygon geometry of the region z <= level."""
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        loops = self.contours(level)
        ps = [Polygon(l) for l in loops if len(l) > 2]
        ps = [p.buffer(0) for p in ps]
        if not ps:
            return Polygon()
        # holes are loops inside loops: the even-odd union
        ps.sort(key=lambda p: -p.area)
        out = None
        for p in ps:
            out = p if out is None else out.symmetric_difference(p)
        return unary_union([out]) if out is not None else Polygon()

    def mesh(self, bounds=None, max_cells=90000):
        """Triangles of the height map for the view: {"vertices", "triangles", "edges"}; bounds (x0, y0, x1, y1)
        crops the grid; a grid of more than max_cells points is thinned by an integer factor."""
        import numpy as np
        ny, nx = self.z.shape
        i0, j0, i1, j1 = 0, 0, nx - 1, ny - 1
        if bounds is not None:
            i0 = max(0, int(math.floor((bounds[0] - self.x0) / self.step)))
            j0 = max(0, int(math.floor((bounds[1] - self.y0) / self.step)))
            i1 = min(nx - 1, int(math.ceil((bounds[2] - self.x0) / self.step)))
            j1 = min(ny - 1, int(math.ceil((bounds[3] - self.y0) / self.step)))
        if i1 <= i0 or j1 <= j0:
            return {"vertices": [], "triangles": [], "edges": []}
        k = 1
        while ((i1 - i0) // k + 1) * ((j1 - j0) // k + 1) > max_cells:
            k += 1
        ii = np.arange(i0, i1 + 1, k)
        jj = np.arange(j0, j1 + 1, k)
        X, Y = np.meshgrid(self.x0 + ii * self.step, self.y0 + jj * self.step)
        Z = self.z[np.ix_(jj, ii)]
        verts = np.round(np.stack([X, Y, Z], axis=-1).reshape(-1, 3), 4).tolist()
        w = len(ii)
        a = (np.arange(len(jj) - 1)[:, None] * w + np.arange(w - 1)[None, :]).ravel()
        tris = np.concatenate([np.stack([a, a + 1, a + w + 1], axis=1), np.stack([a, a + w + 1, a + w], axis=1)]).tolist()
        return {"vertices": verts, "triangles": tris, "edges": []}


# marching squares: for every corner code the edge pairs (edge 0 bottom, 1 right, 2 top, 3 left) of the boundary
# of the inside region (corner bits: 0 (i,j), 1 (i+1,j), 2 (i+1,j+1), 3 (i,j+1))
_MS_TABLE = {
    1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)], 5: [(3, 0), (1, 2)], 6: [(0, 2)], 7: [(3, 2)],
    8: [(2, 3)], 9: [(2, 0)], 10: [(0, 1), (2, 3)], 11: [(2, 1)], 12: [(1, 3)], 13: [(1, 0)], 14: [(0, 3)],
}


# --------------------------------------------------------------------------- text

FONT_PATHS = [r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]


def find_font(name=""):
    import os
    cands = []
    if name:
        cands.append(name)
        cands.append(os.path.join(r"C:\Windows\Fonts", name))
        cands.append(os.path.join(r"C:\Windows\Fonts", name + ".ttf"))
    cands += FONT_PATHS
    for p in cands:
        if p and os.path.isfile(p):
            return p
    return None


def text_polygons(text, size, font="", x=0.0, y=0.0, angle=0.0, align="left"):
    """Polygons (XY, mm) of the glyph outlines of a text (fontTools): size is the cap height in mm (the font's
    units per em scaled so that the em is size / 0.7), the baseline at (x, y) turned by angle deg."""
    from fontTools.ttLib import TTFont
    from fontTools.pens.recordingPen import RecordingPen
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    path = find_font(font)
    if path is None:
        raise ValueError("no font file found (%s)" % (font or "arial.ttf / DejaVuSans.ttf"))
    f = TTFont(path)
    upem = f["head"].unitsPerEm
    scale = size / 0.7 / upem
    cmap = f.getBestCmap()
    gs = f.getGlyphSet()
    hmtx = f["hmtx"]
    pen_x = 0.0
    glyph_polys = []
    for ch in text:
        gname = cmap.get(ord(ch))
        if gname is None:
            pen_x += hmtx[".notdef"][0] * scale if ".notdef" in hmtx.metrics else size * 0.6
            continue
        pen = RecordingPen()
        gs[gname].draw(pen)
        contours, cur = [], []
        last = None
        for op, args in pen.value:
            if op == "moveTo":
                if len(cur) > 2:
                    contours.append(cur)
                cur = [args[0]]
                last = args[0]
            elif op == "lineTo":
                cur.append(args[0])
                last = args[0]
            elif op == "qCurveTo":
                pts = list(args)
                # implied on-curve points between off-curve points
                if pts[-1] is None:
                    pts = pts[:-1] + [pts[0]]
                ctrl = pts[:-1]
                end = pts[-1]
                p0 = last
                for k, c in enumerate(ctrl):
                    nxt = ctrl[k + 1] if k + 1 < len(ctrl) else end
                    mid = nxt if k + 1 == len(ctrl) else ((c[0] + nxt[0]) / 2, (c[1] + nxt[1]) / 2)
                    for t in [i / 6.0 for i in range(1, 7)]:
                        cur.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * mid[0],
                                    (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * mid[1]))
                    p0 = mid
                last = end
            elif op == "curveTo":
                c1, c2, end = args
                p0 = last
                for t in [i / 8.0 for i in range(1, 9)]:
                    cur.append(((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t * t * c2[0] + t ** 3 * end[0],
                                (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t * t * c2[1] + t ** 3 * end[1]))
                last = end
            elif op in ("closePath", "endPath"):
                if len(cur) > 2:
                    contours.append(cur)
                cur = []
        if len(cur) > 2:
            contours.append(cur)
        rings = [[(pen_x + px * scale, py * scale) for px, py in c] for c in contours]
        ps = [Polygon(r).buffer(0) for r in rings if len(r) > 2]
        # outer contours and holes by the even-odd rule
        ps = [p for p in ps if not p.is_empty]
        ps.sort(key=lambda p: -p.area)
        g = None
        for p in ps:
            g = p if g is None else g.symmetric_difference(p)
        if g is not None and not g.is_empty:
            glyph_polys.append(g)
        pen_x += hmtx[gname][0] * scale
    width = pen_x
    g = unary_union(glyph_polys) if glyph_polys else Polygon()
    dx = {"centre": -width / 2.0, "center": -width / 2.0, "right": -width}.get(align, 0.0)
    from shapely import affinity
    g = affinity.translate(g, dx, 0)
    if angle:
        g = affinity.rotate(g, angle, origin=(0, 0))
    return affinity.translate(g, x, y), width


def grid_solid(x0, y0, step, ztop, zbot):
    """Closed solid between two height grids on one XY grid (arrays ny x nx; ztop above zbot everywhere): the top
    and bottom triangulated, the four sides closed; built from a mesh (BRepBuilderAPI_MakeShapeOnMesh), sewn."""
    import numpy as np
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeShapeOnMesh, BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.Poly import Poly_Triangulation, Poly_Triangle
    from OCP.gp import gp_Pnt
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from build123d import Solid
    ztop, zbot = np.asarray(ztop, float), np.asarray(zbot, float)
    ny, nx = ztop.shape
    if nx < 2 or ny < 2:
        raise ValueError("the height grid is too small")
    nv = nx * ny
    tri = []
    T = lambda i, j: j * nx + i
    B = lambda i, j: nv + j * nx + i
    for j in range(ny - 1):
        for i in range(nx - 1):
            a, b, c, d = T(i, j), T(i + 1, j), T(i + 1, j + 1), T(i, j + 1)
            tri += [(a, b, c), (a, c, d)]
            a, b, c, d = B(i, j), B(i + 1, j), B(i + 1, j + 1), B(i, j + 1)
            tri += [(a, c, b), (a, d, c)]
    ring = [(i, 0) for i in range(nx - 1)] + [(nx - 1, j) for j in range(ny - 1)] + \
        [(i, ny - 1) for i in range(nx - 1, 0, -1)] + [(0, j) for j in range(ny - 1, 0, -1)]
    for k in range(len(ring)):
        p, q = ring[k], ring[(k + 1) % len(ring)]
        tri += [(T(*p), B(*p), B(*q)), (T(*p), B(*q), T(*q))]
    pt = Poly_Triangulation(2 * nv, len(tri), False)
    k = 1
    for zz in (ztop, zbot):
        for j in range(ny):
            for i in range(nx):
                pt.SetNode(k, gp_Pnt(x0 + i * step, y0 + j * step, float(zz[j, i])))
                k += 1
    for k, (a, b, c) in enumerate(tri):
        pt.SetTriangle(k + 1, Poly_Triangle(a + 1, b + 1, c + 1))
    mk = BRepBuilderAPI_MakeShapeOnMesh(pt)
    mk.Build()
    sw = BRepBuilderAPI_Sewing(1e-6)
    sw.Add(mk.Shape())
    sw.Perform()
    ex = TopExp_Explorer(sw.SewedShape(), TopAbs_SHELL)
    if not ex.More():
        raise ValueError("the height grid could not be closed to a solid")
    shell = (getattr(TopoDS, "Shell_s", None) or TopoDS.Shell)(ex.Current())
    so = Solid(BRepBuilderAPI_MakeSolid(shell).Solid())
    if so.volume < 0:
        so = Solid(so.wrapped.Reversed())
    return so


def cut_by_heights(stock, x0, y0, step, before, after, max_cells=100):
    """The stock less the material between two height maps of its top (before and after an operation, same grid):
    the cells cut (after below before by more than 0.001 mm) with a margin of one cell, sampled to at most
    max_cells per side, as the solid from the cut surface up to above the stock. Returns (stock, cells used) or
    (stock, 0) when nothing is cut."""
    import numpy as np
    cutm = (before - after) > 1e-3
    if not cutm.any():
        return stock, 0
    js, is_ = np.nonzero(cutm)
    j0, j1 = max(0, js.min() - 1), min(cutm.shape[0], js.max() + 2)
    i0, i1 = max(0, is_.min() - 1), min(cutm.shape[1], is_.max() + 2)
    k = max(1, int(math.ceil(max(j1 - j0, i1 - i0) / float(max_cells))))
    sb = bbox(stock)
    zt = sb[5]
    sub_a = after[j0:j1:k, i0:i1:k]
    sub_c = cutm[j0:j1:k, i0:i1:k]
    if sub_a.shape[0] < 2 or sub_a.shape[1] < 2:
        return stock, 0
    bottom = np.where(sub_c, np.minimum(sub_a, zt + 0.5), zt + 1.0)
    top = np.full(bottom.shape, zt + 2.0)
    rem = grid_solid(x0 + i0 * step, y0 + j0 * step, step * k, top, bottom)
    return cut(stock, [rem]), int(sub_a.size)
