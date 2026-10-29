# -*- coding: utf-8 -*-
"""Vcarve: centre-line carving of closed regions (text outlines, sketch regions, faces) with a V bit: the medial
axis of the region from the Voronoi diagram of its sampled boundary, the depth at every point from the radius of
the largest circle that fits there and the bit angle; where that depth would pass the final depth the region is
cleared at the final depth with the bit's width at that depth.

Fields: "text" ({"text", "size", "font", "x", "y", "angle", "align"}), "sketch" (a sketch record: its closed
  loops), "faces" (horizontal faces), "discretize" mm (boundary sampling), "threshold" (0..1: medial edges closer
  to the boundary than threshold x discretize are dropped), "colinear" mm (path simplification)
"""
import math

from . import geom as G
from . import tools as TB
from .ops2d import check_shape, base_faces, sketch_polylines, offset_rings, oriented, nearest_start

_f = G._f


def regions_of(ctx):
    """Closed regions to carve (shapely polygons)."""
    from shapely.ops import unary_union, polygonize
    from shapely.geometry import LineString
    op = ctx.op
    regs = []
    tx = op.get("text")
    if tx and tx.get("text"):
        g, _ = G.text_polygons(str(tx["text"]), _f(tx.get("size"), 10.0), tx.get("font") or "", _f(tx.get("x")), _f(tx.get("y")),
                               _f(tx.get("angle")), tx.get("align") or "left")
        regs += G.polys(g)
    sk = op.get("sketch")
    if sk:
        ls = [LineString(pl) for pl in sketch_polylines(ctx, sk) if len(pl) > 1]
        ps = list(polygonize(unary_union(ls))) if ls else []
        # nested loops: even-odd
        ps.sort(key=lambda p: -p.area)
        g = None
        for p in ps:
            g = p if g is None else g.symmetric_difference(p)
        regs += G.polys(g) if g is not None else []
    for fc in base_faces(ctx):
        try:
            regs.append(G.face_outline(fc))
        except Exception:
            continue
    return [p for p in regs if p.area > 1e-6]


def medial_axis(poly, step, threshold):
    """Medial axis of a polygon: [(polyline [(x, y, r)])] with r the distance to the boundary at every point."""
    from shapely.geometry import MultiPoint, Point, LineString, MultiLineString
    from shapely.ops import voronoi_diagram, linemerge
    samples = []
    rings = [poly.exterior] + list(poly.interiors)
    for ring in rings:
        L = ring.length
        n = max(8, int(L / step))
        for i in range(n):
            q = ring.interpolate(L * i / n)
            samples.append((q.x, q.y))
    if len(samples) < 4:
        return []
    vd = voronoi_diagram(MultiPoint(samples), edges=True)
    bnd = poly.boundary
    inner = poly.buffer(-threshold * step)
    segs = []
    for l in G.lines(vd):
        cs = list(l.coords)
        for a, b in zip(cs, cs[1:]):
            pa, pb = Point(a), Point(b)
            if inner.contains(pa) and inner.contains(pb):
                segs.append(LineString([a, b]))
    if not segs:
        return []
    m = linemerge(MultiLineString(segs))
    out = []
    for l in (m.geoms if hasattr(m, "geoms") else [m]):
        pts = [(float(x), float(y), float(bnd.distance(Point(x, y)))) for x, y in l.coords]
        if len(pts) > 1:
            out.append(pts)
    return out


def run_vcarve(ctx):
    check_shape(ctx, "vbit")
    ctx.res["cuts_part"] = True
    op = ctx.op
    tool = ctx.tool
    phi = math.radians(_f(tool.get("angle"), 90.0) / 2.0)
    rt = max(0.0, _f(tool.get("tip"), 0.0) / 2.0)
    R = TB.radius(tool)
    regs = regions_of(ctx)
    if not regs:
        raise ValueError("no region to carve: a text, a sketch with closed loops or faces")
    step = max(0.02, _f(op.get("discretize"), 0.2))
    thr = min(0.9, max(0.0, _f(op.get("threshold"), 0.25)))
    col = max(0.0, _f(op.get("colinear"), 0.01))
    from .ops2d import surface_z
    zt = surface_z(ctx, [G.ring_pts(p.exterior) for p in regs])
    dmax = (R - rt) / math.tan(phi)                         # the full depth of the bit
    h = ctx.heights(start=zt if op.get("start_depth") is None else None, final=zt - dmax if op.get("final_depth") is None else None)
    depth_limit = h["start"] - h["final"]
    mv = ctx.moves()
    npaths = 0
    from shapely.geometry import LineString
    for poly in regs:
        axes = medial_axis(poly, step, thr)
        for pl in axes:
            if col > 0 and len(pl) > 2:
                keep = LineString([(x, y) for x, y, _ in pl]).simplify(col, preserve_topology=False)
                kept = {(round(x, 6), round(y, 6)) for x, y in keep.coords}
                pl = [p for p in pl if (round(p[0], 6), round(p[1], 6)) in kept] or pl
            pts = [(x, y, h["start"] - min(depth_limit, max(0.0, (r - rt) / math.tan(phi)))) for x, y, r in pl]
            mv.rapid_to(pts[0][0], pts[0][1])
            mv.to_safe()
            mv.plunge_to(pts[0][2])
            for x, y, z in pts[1:]:
                mv.feed_to(x, y, z)
            mv.retract()
            npaths += 1
        # the parts of the region wider than the bit at the final depth: cleared at the final depth
        r_at = rt + depth_limit * math.tan(phi)
        deep = poly.buffer(-r_at, G.PATH_SEGS)
        if not deep.is_empty:
            z = h["final"]
            for loops in offset_rings(deep, max(0.1, r_at * 0.8)):
                for loop in loops:
                    lp = nearest_start(oriented(loop, False), mv.cur and mv.cur[:2])
                    mv.enter(lp[0][0], lp[0][1], z)
                    mv.polyline(lp[1:] + [lp[0]], z)
            mv.retract()
            ctx.message("region wider than the bit at the final depth: cleared at Z %.3f mm" % z)
    ctx.message("%d region(s), %d centre-line path(s), bit %.0f deg, depth at most %.3f mm" % (len(regs), npaths, 2 * math.degrees(phi), depth_limit))
    # simulation on a height map (the moves vary in Z); the solid stock cut by the envelope of the regions
    from shapely.ops import unary_union
    from .ops3d import _hm_simulate
    zmin = min([m["p"][2] for m in mv.moves if m.get("k") in ("feed", "plunge")] or [h["final"]])
    hstep = max(0.1, min(0.5, step))
    sb = ctx.stock_bb
    hm = G.HeightMap.of_shape(ctx.shape, hstep, margin=R + hstep, zfloor=sb[2] - 1.0, bounds=(sb[0], sb[1], sb[3], sb[4]))
    _hm_simulate(ctx, hm, mv.moves, hstep, envelope=(unary_union(regs), zmin, h["start"], False))
    return mv


OPS = {"vcarve": run_vcarve}
