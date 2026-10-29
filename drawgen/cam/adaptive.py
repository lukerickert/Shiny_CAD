# -*- coding: utf-8 -*-
"""Adaptive clearing and profiling: continuous spiral paths of the tool centre whose radial engagement stays
at the step over (the offset loops of the region joined into one spiral), with a helix entry and lifts
between separate regions. The spiral of a region: the loops of the region offset inward by multiples of the
step over, from the innermost outward, each loop morphed into the next so that the path never stops and the
engagement never exceeds the step over; a region that splits into parts at an offset is spiralled part by
part.

Fields: "faces" (floor faces; none: the stock area over the part), "mode": "clearing" | "profiling", "side":
  "outside" | "inside" (profiling), "stepover_pct" (% of the tool diameter), "tolerance" mm (path
  simplification), "helix_angle" deg, "helix_diameter" mm (0: 0.5 x the tool diameter), "lift" mm (lift between
  separate regions, above the level), "keep_down_ratio" (a link at the level when its length is at most this
  times the straight distance), "stock_to_leave" mm, "finish_profile" (a final pass along the wall),
  "force_inside_out", "use_outline", "passes": n (profiling: number of step overs around the contour)
"""
import math

from . import geom as G
from . import tools as TB
from .job import levels as _levels_of
from .ops2d import check_shape, base_faces, pocket_region, stepover_mm, oriented, nearest_start, stock_top_over, walls_over, reach_of

_f = G._f


def _resample(loop, n):
    """n points evenly spaced along the closed loop, from its first vertex."""
    L = loop + [loop[0]]
    total = sum(math.dist(a, b) for a, b in zip(L, L[1:]))
    if total < 1e-9:
        return [loop[0]] * n
    out = []
    k = 0
    acc = 0.0
    for i in range(n):
        s = total * i / n
        while k + 1 < len(L) - 1 and acc + math.dist(L[k], L[k + 1]) < s:
            acc += math.dist(L[k], L[k + 1])
            k += 1
        seg = math.dist(L[k], L[k + 1])
        t = (s - acc) / seg if seg > 1e-12 else 0.0
        out.append((L[k][0] + (L[k + 1][0] - L[k][0]) * t, L[k][1] + (L[k + 1][1] - L[k][1]) * t))
    return out


def spiral_paths(region, stepover, cw=False, tolerance=0.02):
    """Spiral polylines of the tool centre clearing the region from the inside out: one per part of the region
    (parts that are separate at the innermost offsets are spiralled separately up to the offset where they
    join, then the joined loop continues)."""
    out = []
    for part in G.polys(region):
        out += _spiral_part(part, stepover, cw, tolerance)
    return out


def _spiral_part(part, stepover, cw, tolerance):
    """Spiral of one polygon: the inward offsets as a tree (children: the parts at the next offset); the path
    spirals the deepest child outward and joins at the parent loop."""
    # offsets: level k polygon parts
    levels = [[part]]
    k = 1
    while True:
        g = part.buffer(-k * stepover, G.PATH_SEGS)
        ps = G.polys(g)
        if not ps:
            break
        levels.append(ps)
        k += 1
        if k > 5000:
            break
    paths = []

    def spiral(poly, level, entry=None):
        """Spiral of the polygon at the level from its children outward; returns the path."""
        children = [c for c in (levels[level + 1] if level + 1 < len(levels) else []) if poly.contains(c.representative_point())]
        outer = oriented(G.ring_pts(poly.exterior), cw)
        if entry is not None:
            outer = nearest_start(outer, entry)
        if not children:
            # the innermost loop: the loop itself (a small region: its centre)
            if poly.area < stepover * stepover:
                c = poly.representative_point()
                return [(c.x, c.y)] + outer + [outer[0]]
            return outer + [outer[0]]
        path = []
        if len(children) == 1:
            inner_path = spiral(children[0], level + 1, entry)
            path += inner_path
            # morph from the child's loop to this loop
            inner = oriented(G.ring_pts(children[0].exterior), cw)
            inner = nearest_start(inner, path[-1])
            outer2 = nearest_start(outer, path[-1])
            n = max(32, min(2000, int((_perimeter(outer2) / max(stepover * 0.5, 0.2)))))
            A = _resample(inner, n)
            B = _resample(outer2, n)
            for i in range(n + 1):
                t = i / n
                a, b = A[i % n], B[i % n]
                path.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            # the holes of this level's polygon: their loops after the exterior
            for h in poly.interiors:
                hl = nearest_start(oriented(G.ring_pts(h), not cw), path[-1])
                path += hl + [hl[0]]
            return path
        # several children: each spiralled on its own, joined by the parent loop
        for c in children:
            p = spiral(c, level + 1, path[-1] if path else entry)
            path += p
        outer2 = nearest_start(outer, path[-1])
        path += outer2 + [outer2[0]]
        for h in poly.interiors:
            hl = nearest_start(oriented(G.ring_pts(h), not cw), path[-1])
            path += hl + [hl[0]]
        return path

    p = spiral(part, 0)
    # the links of separate children cross uncut or cut material at the level: split the path where a link
    # leaves the region by more than the tolerance
    from shapely.geometry import LineString
    reg = part.buffer(1e-6)
    cur = [p[0]]
    for a, b in zip(p, p[1:]):
        if math.dist(a, b) < 1e-9:
            continue
        if reg.contains(LineString([a, b])):
            cur.append(b)
        else:
            if len(cur) > 1:
                paths.append(cur)
            cur = [b]
    if len(cur) > 1:
        paths.append(cur)
    if tolerance > 0:
        paths = [[(float(x), float(y)) for x, y in LineString(pl).simplify(tolerance, preserve_topology=False).coords] if len(pl) > 2 else pl for pl in paths]
    return paths


def _perimeter(loop):
    return sum(math.dist(a, b) for a, b in zip(loop, loop[1:] + loop[:1]))


def run_adaptive(ctx):
    """Adaptive: clearing of the picked floors (or of the stock over the part) or profiling around the contour,
    with spiral paths of constant engagement, helix entry, levels from the start depth to the final depth."""
    from shapely.geometry import Polygon, box as sbox
    check_shape(ctx, "endmill", "bullnose")
    op = ctx.op
    R = TB.radius(ctx.tool)
    mode = op.get("mode") or "clearing"
    leave = max(0.0, _f(op.get("stock_to_leave"), 0.0))
    stepover = stepover_mm(ctx, 20.0)
    tol = max(0.0, _f(op.get("tolerance"), 0.02))
    hang = min(60.0, max(0.5, _f(op.get("helix_angle"), 3.0)))
    hdia = _f(op.get("helix_diameter"), 0.0)
    rh_max = (hdia / 2.0) if hdia > 0 else 0.5 * R
    lift = max(0.0, _f(op.get("lift"), 1.0))
    from .ops2d import finish_mode, finish_in_level, phase_of, finish_feed, finish_loops
    phase = phase_of(op)
    finish = finish_in_level(op) or phase == "finish"
    spring = bool(op.get("finish_spring")) and finish
    faces = base_faces(ctx)
    mv = None
    infos = []
    if faces:
        for fc in faces:
            infos.append(G.floor_info(ctx.shape, fc))
        z_floor = min(i["z"] for i in infos)
        h = ctx.heights(final=z_floor)
    else:
        sb = ctx.stock_bb
        h = ctx.heights(final=ctx.part_bb[2])
        infos.append({"z": h["final"], "poly": sbox(sb[0], sb[1], sb[3], sb[4]), "open": [], "all": True})
    mv = ctx.moves()
    nlev = 0
    for info in infos:
        poly = Polygon(info["poly"].exterior) if op.get("use_outline") else info["poly"]
        z_top = stock_top_over(ctx.stock, poly, info["z"], h["start"]) if not info.get("all") else h["start"]
        hh = dict(h, start=z_top, final=max(info["z"], h["final"]) if op.get("final_depth") is None else h["final"])
        lv = _levels_of(hh)
        if not lv:
            ctx.message("floor Z %.3f mm: nothing to cut" % info["z"])
            continue
        nlev += len(lv)
        for i, z in enumerate(lv):
            zt = z_top if i == 0 else lv[i - 1]
            walls = walls_over(ctx.shape, z, zt, reach_of(ctx, z))
            if info.get("all"):
                region = poly.buffer(R + 1.0).difference(walls.buffer(leave + G.sag(R), G.PATH_SEGS)).buffer(-R, G.PATH_SEGS)
            else:
                region = pocket_region(ctx.shape, info, R, leave, z, zt, True, op.get("use_outline"), reach_of(ctx, z))
            if mode == "profiling":
                # the band around the walls: passes x step over wide
                npass = max(1, int(_f(op.get("passes"), 2)))
                band = walls.buffer(R + leave + G.sag(R) + npass * stepover, G.PATH_SEGS).difference(walls.buffer(R + leave + G.sag(R), G.PATH_SEGS))
                region = region.intersection(band) if not info.get("all") else band.intersection(poly.buffer(R + 1.0).buffer(-R))
            if phase == "finish":
                if info.get("all"):
                    ctx.message("no walls to finish: pick floor faces")
                    continue
                fin = pocket_region(ctx.shape, info, R, 0.0, z, zt, True, op.get("use_outline"), reach_of(ctx, z))
                finish_loops(ctx, mv, fin, z, False, True)
                if spring and i == len(lv) - 1:
                    finish_loops(ctx, mv, fin, z, False, True)
                mv.retract()
                continue
            if region.is_empty:
                ctx.message("Z %.3f mm: no room for the tool" % z)
                continue
            paths = spiral_paths(region, stepover, cw=False, tolerance=tol)
            first = True
            for pl in paths:
                if first:
                    first = False
                    from .ops2d import helix_entry, link_or_lift
                    end = None
                    rh = min(rh_max, 0.5 * R)
                    pitch = 2 * math.pi * rh * math.tan(math.radians(hang))
                    inner = region.buffer(-rh, G.ARC_SEGS // 4)
                    if not inner.is_empty:
                        end = helix_entry(mv, region, R, zt, z, max(pitch, 0.05), False)
                    if end is None:
                        ctx.message("Z %.3f mm: no room for the helix: plunge entry" % z)
                        mv.enter(pl[0][0], pl[0][1], z)
                    else:
                        link_or_lift(mv, region, pl[0], z, True)
                else:
                    # a lift between separate parts of the region
                    from shapely.geometry import LineString
                    if region.buffer(1e-6).contains(LineString([tuple(mv.cur[:2]), pl[0]])):
                        mv.feed_to(pl[0][0], pl[0][1], z)
                    else:
                        mv._add("rapid", (mv.cur[0], mv.cur[1], z + lift))
                        mv._add("rapid", (pl[0][0], pl[0][1], z + lift))
                        mv.plunge_to(z)
                mv.polyline(pl[1:], z)
            if finish and not info.get("all"):
                fin = pocket_region(ctx.shape, info, R, 0.0, z, zt, True, op.get("use_outline"), reach_of(ctx, z))
                for rep in range(2 if spring and i == len(lv) - 1 else 1):
                    for loop in G.loops_of(fin):
                        lp = nearest_start(oriented(loop, False), mv.cur and mv.cur[:2])
                        mv.enter(lp[0][0], lp[0][1], z)
                        mv.polyline(lp[1:] + [lp[0]], z, finish_feed(ctx))
            mv.retract()
    ctx.message("%s, %d level(s), step over %.2f mm, stock to leave %.2f mm" % (mode, nlev, stepover, leave))
    return mv


OPS = {"adaptive": run_adaptive}
