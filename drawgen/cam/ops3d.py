# -*- coding: utf-8 -*-
"""3D operations on the height map of the part (geom.HeightMap): 3D Surface (the tool follows the surface
along a pattern), Waterline (contours of the surface at Z levels) and 3D Pocket (the volume above picked faces
cleared in levels, each level bounded by where the tool can go). The height of the tool centre at every grid
point comes from the surface dilated by the tool's own profile, so ball, bull nose and flat end mills are
exact (no undercuts: a height map holds one Z per point). The stock cut by these operations is simulated on a
height map of the stock with the tool profile (removed, gouge and remaining from the heights), and the
flat-footprint level cut of job.simulate keeps the solid stock in step.

Fields: "faces" (boundary faces; none: the stock area), "boundary": "faces" | "stock" | "boundbox",
  "pattern": "line" | "zigzag" | "circular" | "circular_zigzag" | "offset" | "spiral" (surface), "angle" deg,
  "stepover_pct", "sample" mm (sample interval and grid step), "depth_offset" mm (left on the surface),
  "layer": "single" | "multi" (surface: one pass on the surface, or levels clipped at the surface), "boundary_adjust"
  mm (the boundary offset: positive outward), "cut_mode": "CW" | "CCW" (waterline, pocket3d loops), "optimize"
  (collinear points removed), "clear_last" (waterline: the last level as a pocket)
"""
import math

from . import geom as G
from . import tools as TB
from .job import levels as _levels_of
from .ops2d import check_shape, base_faces, stepover_mm, oriented, nearest_start, offset_rings, zigzag_lines

_f = G._f


def _boundary(ctx):
    """(polygon of the area, z of the lowest picked face or None)."""
    from shapely.geometry import box as sbox
    from shapely.ops import unary_union
    op = ctx.op
    sb = ctx.stock_bb
    faces = base_faces(ctx)
    adj = _f(op.get("boundary_adjust"), 0.0)
    mode = op.get("boundary") or ("faces" if faces else "stock")
    if mode == "faces" and faces:
        reg = unary_union([G.face_outline(fc) for fc in faces])
        zf = min(G.bbox(fc)[2] for fc in faces)
        if op.get("boundary_shape") == "boundbox":
            reg = sbox(*reg.bounds)
    else:
        reg = sbox(sb[0], sb[1], sb[3], sb[4])
        zf = None
    if adj:
        reg = reg.buffer(adj, G.PATH_SEGS)
    return reg, zf


def _maps(ctx, step):
    """Height map of the part over the stock area and the tool-centre map."""
    sb = ctx.stock_bb
    R = TB.radius(ctx.tool)
    hm = G.HeightMap.of_shape(ctx.shape, step, margin=R + step, zfloor=sb[2] - 1.0, bounds=(sb[0], sb[1], sb[3], sb[4]))
    return hm, hm.tool_map(ctx.tool)


def _steps(pts, drop):
    """A change of Z larger than drop between consecutive sample points taken as a vertical step: the tool moves
    at the higher Z over the lower point before descending, and rises over the lower point before moving on."""
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        if a[2] - b[2] > drop:
            out.append((b[0], b[1], a[2]))
        elif b[2] - a[2] > drop:
            out.append((a[0], a[1], b[2]))
        out.append(b)
    return out


def _optimize(pts, tol):
    """Collinear points of a polyline [(x, y, z)] dropped (within tol)."""
    if tol <= 0 or len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        L = math.sqrt(ac[0] ** 2 + ac[1] ** 2 + ac[2] ** 2)
        if L < 1e-12:
            continue
        cross = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
        d = math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) / L
        if d > tol:
            out.append(b)
    out.append(pts[-1])
    return out


def run_surface(ctx):
    """3D Surface: the tool follows the surface (the tool-centre map plus the depth offset) along the pattern
    inside the boundary, between the start depth and the final depth; multi-layer: one pass per level with the
    surface clipped at the level."""
    check_shape(ctx, "endmill", "ballend", "bullnose", "vbit", "tapered", "custom")
    op = ctx.op
    R = TB.radius(ctx.tool)
    step = max(0.05, _f(op.get("sample"), 0.5))
    stepover = stepover_mm(ctx, 25.0)
    pattern = op.get("pattern") or "zigzag"
    angle = _f(op.get("angle"), 0.0)
    doff = max(0.0, _f(op.get("depth_offset"), 0.0))
    region, zf = _boundary(ctx)
    hm, tm = _maps(ctx, step)
    h = ctx.heights(final=zf if zf is not None else ctx.part_bb[2])
    single = (op.get("layer") or "single") == "single"
    lv = [h["final"]] if single else (_levels_of(h) or [h["final"]])
    reg = region.buffer(-G.sag(R), G.PATH_SEGS) if op.get("boundary_enforce", True) else region
    if reg.is_empty:
        raise ValueError("the boundary is smaller than the tool")
    mv = ctx.moves()
    tol = 0.01 if op.get("optimize", True) else 0.0
    nlines = 0

    def zc(x, y, zlev):
        return max(zlev, min(h["start"], tm.at(x, y) + doff))

    def run_line(pl, zlev, link):
        nonlocal nlines
        pts = []
        for a, b in zip(pl, pl[1:]):
            L = math.dist(a, b)
            n = max(1, int(math.ceil(L / step)))
            for i in range(0 if not pts else 1, n + 1):
                x, y = a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n
                pts.append((x, y, zc(x, y, zlev)))
        pts = _steps(pts, 2.0 * step)
        pts = _optimize(pts, tol)
        if not pts:
            return
        if link and mv.cur is not None:
            mv.feed_to(pts[0][0], pts[0][1], max(pts[0][2], zc(mv.cur[0], mv.cur[1], zlev)))
        else:
            mv.rapid_to(pts[0][0], pts[0][1])
            mv.to_safe()
            mv.plunge_to(pts[0][2])
        for x, y, z in pts[1:]:
            mv.feed_to(x, y, z)
        nlines += 1
    for zlev in lv:
        if pattern in ("line", "zigzag"):
            lines_ = zigzag_lines(reg, stepover, angle, zig=pattern == "zigzag")
            for k, pl in enumerate(lines_):
                run_line(pl, zlev, link=pattern == "zigzag" and k > 0)
        elif pattern in ("circular", "circular_zigzag"):
            cx, cy = reg.centroid.x, reg.centroid.y
            x0, y0, x1, y1 = reg.bounds
            rmax = math.hypot(max(x1 - cx, cx - x0), max(y1 - cy, cy - y0))
            r = stepover
            k = 0
            from shapely.geometry import Point
            while r <= rmax:
                ring = Point(cx, cy).buffer(r, 32).exterior
                for l in G.lines(reg.intersection(ring)):
                    pl = [(float(x), float(y)) for x, y in l.coords]
                    if pattern == "circular_zigzag" and k % 2:
                        pl = pl[::-1]
                    run_line(pl, zlev, link=pattern == "circular_zigzag" and k > 0)
                r += stepover
                k += 1
        elif pattern == "spiral":
            from .adaptive import spiral_paths
            for pl in spiral_paths(reg, stepover, False, 0.0):
                run_line(pl, zlev, link=False)
        else:
            for loops in offset_rings(reg, stepover, outward=True):
                for loop in loops:
                    lp = nearest_start(oriented(loop, False), mv.cur and mv.cur[:2])
                    run_line(lp + [lp[0]], zlev, link=False)
        mv.retract()
    _hm_simulate(ctx, hm, mv.moves, step, envelope=(region, h["final"], h["start"], True))
    ctx.message("%s pattern, step over %.2f mm, sample %.2f mm, %d line(s), %d level(s)" % (pattern, stepover, step, nlines, len(lv)))
    return mv


def run_waterline(ctx):
    """Waterline: at every level from the start depth to the final depth the contours where the tool touches the
    surface (the boundary of the region where the tool centre may be at that level), inside the boundary."""
    check_shape(ctx, "endmill", "ballend", "bullnose", "tapered", "custom")
    op = ctx.op
    R = TB.radius(ctx.tool)
    step = max(0.05, _f(op.get("sample"), 0.5))
    doff = max(0.0, _f(op.get("depth_offset"), 0.0))
    cw = (op.get("cut_mode") or "CW") == "CW"
    region, zf = _boundary(ctx)
    hm, tm = _maps(ctx, step)
    h = ctx.heights(final=zf if zf is not None else ctx.part_bb[2])
    lv = _levels_of(h)
    if not lv:
        raise ValueError("the final depth %.3f mm is not below the start depth %.3f mm" % (h["final"], h["start"]))
    reg = region.buffer(-G.sag(R), G.PATH_SEGS)
    mv = ctx.moves()
    nloops = 0
    tol = 0.01 if op.get("optimize", True) else 0.0
    for z in lv:
        free = tm.region(z - doff)          # where the tool centre may be at z
        area = free.intersection(reg)
        loops = []
        for p in G.polys(area):
            for ring in [p.exterior] + list(p.interiors):
                # only the contours that touch the surface (not the boundary of the stock area)
                pts = G.ring_pts(ring)
                if len(pts) < 3:
                    continue
                on_surface = [q for q in pts if abs(tm.at(q[0], q[1]) + doff - z) < step * 2]
                if len(on_surface) < len(pts) * 0.2:
                    continue
                loops.append(pts)
        for lp in loops:
            lp = nearest_start(oriented(lp, cw), mv.cur and mv.cur[:2])
            pts = _optimize([(x, y, z) for x, y in lp + [lp[0]]], tol)
            mv.rapid_to(pts[0][0], pts[0][1])
            mv.to_safe()
            mv.plunge_to(z)
            for x, y, _ in pts[1:]:
                mv.feed_to(x, y, z)
            nloops += 1
        if op.get("clear_last") and z == lv[-1]:
            stepover = stepover_mm(ctx, 50.0)
            for loops2 in offset_rings(area, stepover):
                for loop in loops2:
                    lp = nearest_start(oriented(loop, cw), mv.cur and mv.cur[:2])
                    mv.enter(lp[0][0], lp[0][1], z)
                    mv.polyline(lp[1:] + [lp[0]], z)
        mv.retract()
    _hm_simulate(ctx, hm, mv.moves, step, region=region)
    ctx.message("%d level(s), %d waterline(s), sample %.2f mm" % (len(lv), nloops, step))
    return mv


def run_pocket3d(ctx):
    """3D Pocket: the volume above the picked faces (or inside the boundary) cleared in levels; at every level the
    region is where the tool centre may be over the surface, cleared with offset loops."""
    check_shape(ctx, "endmill", "bullnose", "ballend", "tapered")
    op = ctx.op
    R = TB.radius(ctx.tool)
    step = max(0.05, _f(op.get("sample"), 0.5))
    stepover = stepover_mm(ctx, 40.0)
    doff = max(0.0, _f(op.get("depth_offset"), 0.0))
    cw = (op.get("cut_mode") or "CW") == "CW"
    pattern = op.get("pattern") or "offset"
    angle = _f(op.get("angle"), 0.0)
    faces = base_faces(ctx)
    if not faces:
        raise ValueError("no face is picked")
    region, zf = _boundary(ctx)
    hm, tm = _maps(ctx, step)
    h = ctx.heights(final=zf)
    lv = _levels_of(h)
    if not lv:
        raise ValueError("the final depth %.3f mm is not below the start depth %.3f mm" % (h["final"], h["start"]))
    # the tool centre must stay over the faces: the boundary offset inward by the radius, extended over open sides
    reg0 = region.buffer(-R - G.sag(R), G.PATH_SEGS)
    mv = ctx.moves()
    nlev = 0
    from .ops2d import clear_region
    for i, z in enumerate(lv):
        zt = h["start"] if i == 0 else lv[i - 1]
        free = tm.region(z - doff)
        area = free.intersection(region.buffer(R, G.PATH_SEGS)).buffer(-R - G.sag(R), G.PATH_SEGS) if op.get("boundary") == "stock" else free.intersection(reg0)
        if area.is_empty:
            continue
        nlev += 1
        clear_region(ctx, mv, area, z, zt, stepover, pattern, angle, cw, "centre", True, op.get("entry") or "helix", max(_f(op.get("helix_pitch"), 1.0), 0.05))
        mv.retract()
    _hm_simulate(ctx, hm, mv.moves, step, region=region)
    ctx.message("%d level(s), step over %.2f mm, sample %.2f mm" % (nlev, stepover, step))
    return mv


def _hm_simulate(ctx, part_hm, moves, step, envelope=None, region=None):
    """Simulation of the moves on a height map of the stock with the tool profile: removed and gouge volumes and
    the remaining material over the part; stored in ctx.res["hm"]. Without envelope the solid stock is cut by
    job.simulate (operations with flat levels); region: the area (polygon) the volumes are counted in (the whole
    map when None). envelope = (region, z_lo, z_hi, keep_part): operations whose moves vary in Z continuously;
    job.simulate is skipped (ctx.res["hm_sim"]) and the solid stock is cut by the solid between the cut surface of
    the height map and the top of the stock (geom.cut_by_heights; when that fails: by the prism of the region between
    z_lo and z_hi for keep_part False, unchanged for keep_part True); keep_part True also gives the cut surface as
    the height map mesh ctx.res["hm"]["mesh"] for the view."""
    import numpy as np
    from .job import move_points
    tool = ctx.tool
    R = TB.radius(tool)
    if envelope is not None:
        ctx.res["hm_sim"] = {"stock": ctx.stock, "levels": [], "removed_mm3": 0.0, "gouge_mm3": 0.0, "errors": []}
    stock_hm = G.HeightMap.of_shape(ctx.stock, step, margin=R + step, zfloor=ctx.stock_bb[2] - 1.0,
                                    bounds=(ctx.stock_bb[0], ctx.stock_bb[1], ctx.stock_bb[3], ctx.stock_bb[4]))
    # the same grid as the part map
    z = stock_hm.z
    if z.shape != part_hm.z.shape:
        return
    n = int(math.ceil(R / step))
    offs = np.full((2 * n + 1, 2 * n + 1), np.inf)
    for dj in range(-n, n + 1):
        for di in range(-n, n + 1):
            o = TB.bottom_offset(tool, math.hypot(di * step, dj * step))
            if o is not None:
                offs[dj + n, di + n] = o
    before = z.copy()
    ny, nx = z.shape
    for pl in move_points(moves):
        pts = []
        for a, b in zip(pl, pl[1:]):
            L = math.dist(a, b)
            k = max(1, int(math.ceil(L / (step * 0.5))))
            for t in range(k + 1):
                pts.append((a[0] + (b[0] - a[0]) * t / k, a[1] + (b[1] - a[1]) * t / k, a[2] + (b[2] - a[2]) * t / k))
        if len(pl) == 1:
            pts = [pl[0]]
        for x, y, zz in pts:
            i = int(round((x - stock_hm.x0) / step))
            j = int(round((y - stock_hm.y0) / step))
            i0, i1 = max(0, i - n), min(nx, i + n + 1)
            j0, j1 = max(0, j - n), min(ny, j + n + 1)
            if i1 <= i0 or j1 <= j0:
                continue
            win = offs[j0 - j + n:j1 - j + n, i0 - i + n:i1 - i + n] + zz
            sub = z[j0:j1, i0:i1]
            np.minimum(sub, win, out=sub)
    cell = step * step
    part = part_hm.z
    # the cells counted: the region grown by the tool radius (all when no region)
    mask = part > ctx.part_bb[2] - 0.5
    if region is not None and not region.is_empty:
        from shapely import contains_xy
        X, Y = np.meshgrid(stock_hm.x0 + step * np.arange(nx), stock_hm.y0 + step * np.arange(ny))
        mask &= contains_xy(region.buffer(R + step, G.PATH_SEGS), X, Y)
    removed = float(np.sum(np.maximum(before - z, 0.0)) * cell)
    gouge = float(np.sum(np.maximum(np.minimum(before, part) - z, 0.0)[mask]) * cell)
    left = float(np.sum(np.maximum(z - part, 0.0)[mask]) * cell)
    ctx.res["hm"] = {"removed_mm3": round(removed, 3), "gouge_mm3": round(gouge, 4), "remaining_mm3": round(left, 3), "step": step}
    ctx.res["messages"].append("height map simulation (%.2f mm grid): removed %.1f mm^3, gouge %.3f mm^3, %.1f mm^3 left over the part"
                               % (step, removed, gouge, left))
    if ctx.res.get("hm_sim") is not None:
        ctx.res["hm_sim"].update(removed_mm3=removed, gouge_mm3=gouge)
        ctx.res["_remaining"] = lambda st, v=left: v
        if envelope[3]:
            b = envelope[0].buffer(R + step).bounds
            ctx.res["hm"]["mesh"] = stock_hm.mesh(bounds=b)
        # the solid stock cut by the solid between the cut surface of the height map and the top of the stock
        try:
            cur, ncell = G.cut_by_heights(ctx.stock, stock_hm.x0, stock_hm.y0, step, before, z, max_cells=_f(ctx.op.get("sim_cells"), 100))
            ctx.res["hm_sim"]["stock"] = cur
            if ncell:
                ctx.res["messages"].append("the solid stock is cut by the height map surface (%d grid points)" % ncell)
        except ValueError as e:
            region_, z_lo, z_hi, keep_part = envelope
            cur = ctx.stock
            if not keep_part and not region_.is_empty:
                env = G.prism(region_, min(z_lo, z_hi), max(z_lo, z_hi) + 1e-3)
                if env is not None and G.volume(env) > G.TOL_VOL:
                    cur = G.cut(cur, [env])
            ctx.res["hm_sim"]["stock"] = cur
            ctx.res["messages"].append("the height map surface could not cut the solid stock (%s): %s" % (
                e, "the stock is cut by the envelope of the operation" if not keep_part else "the solid stock is not changed"))


OPS = {"surface": run_surface, "waterline": run_waterline, "pocket3d": run_pocket3d}
