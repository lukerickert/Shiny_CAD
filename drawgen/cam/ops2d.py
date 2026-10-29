# -*- coding: utf-8 -*-
"""2.5D operations: Face, Pocket Shape, Profile, Drilling, Helix, Slot, Engrave, Deburr and Undercut. Every
generator takes a Ctx (job.py) and returns the Moves of the operation; it reports with ctx.message and
ctx.error. The regions and offsets are shapely polygons (geom.py), the paths polylines at Z levels.

Fields of the types (in addition to the common fields of job.py):
  face:     "boundary": "stock" | "boundbox" | "faces" (the picked faces), "faces", "pattern": "zigzag" | "line" |
            "offset", "stepover_pct" (% of the tool diameter), "angle" deg (of the zigzag lines), "cut_mode",
            "overhang" mm (beyond the boundary at the pass ends)
  pocket:   "faces" (floor faces, or wall faces of a pocket), "pattern": "offset" | "zigzag" | "line" | "spiral" |
            "zigzag_offset", "stepover_pct", "angle", "cut_mode": "CW" | "CCW", "start_at": "centre" | "boundary",
            "extra_offset" mm (material left on the walls), "use_outline" (holes of the floor ignored),
            "keep_down" (links at the level), "finish" (a wall pass at extra offset 0), "entry": "helix" | "plunge",
            "helix_pitch" mm
  profile:  "faces" | "edges" | nothing (the whole model), "side": "outside" | "inside", "direction": "CW" | "CCW",
            "compensation" (offset by the tool radius), "extra_offset" mm, "process_holes", "process_perimeter",
            "process_circles", "passes": n (extra passes stepping out by "stepover_pct")
  drilling: "faces" (hole faces), "peck" mm, "dwell" s, "retract": mm above the start depth where the feed
            begins, "tip" (the drill tip added to the depth), "through", "breakthrough" mm
  helix:    "faces" (hole faces), "direction": "CW" | "CCW", "start_side": "outside" | "inside", "stepover_pct",
            "extra_offset"
  slot:     "points": [[x, y(, z)], [x, y(, z)]] (z: the clicked point, kept for the placement) or "edges" (one straight or circular edge) or "faces" (a slot floor),
            "extend_start", "extend_end" mm, "layer": "single" | "multi", "reverse", "radius_offset" mm (arc slot)
  engrave:  "edges" (edges of the part), "sketch" (a saved sketch of the project), "text": {"text", "size", "font",
            "x", "y", "angle", "align"}, "start_vertex"
  deburr:   "edges" or "faces" (their outer edges), "width" mm (W), "extra_depth" mm (h), "direction", "entry":
            index of the start corner
  undercut: "faces" (undercut faces), "stepover" mm, "allowance" mm, "runout" mm, "reverse"
"""
import math

from . import geom as G
from . import tools as TB
from .job import levels as _levels_of

_f = G._f


# --------------------------------------------------------------------------- base geometry

def base_faces(ctx, key="faces"):
    from .. import part as P
    return P.find_faces(ctx.shape, ctx.op.get(key) or [])


def base_edges(ctx, key="edges"):
    from .. import part as P
    return P.find_edges(ctx.shape, ctx.op.get(key) or [])


def check_shape(ctx, *shapes):
    s = TB.shape_of(ctx.tool)
    if s not in shapes:
        raise ValueError("the tool %s is a %s; %s needs %s" % (ctx.tool.get("id"), TB.SHAPE_NAMES.get(s, s),
                                                                 ctx.op.get("type"), " or ".join(TB.SHAPE_NAMES.get(x, x).lower() for x in shapes)))


def stepover_mm(ctx, default_pct=50.0):
    """Step over (mm) from "stepover_pct" (% of the tool diameter) or "stepover" (mm)."""
    D = 2 * TB.radius(ctx.tool)
    pct = ctx.op.get("stepover_pct")
    if pct not in (None, ""):
        return max(0.05, min(100.0, _f(pct, default_pct)) / 100.0 * D)
    if ctx.op.get("stepover") not in (None, ""):
        return max(0.05, _f(ctx.op.get("stepover")))
    return max(0.05, default_pct / 100.0 * D)


FINISHABLE = ("pocket", "profile", "adaptive", "undercut")


def finish_mode(op):
    """Finishing of an operation: "off" (the stock to leave stays), "level" (a finish pass with the same tool in each
    level, after the roughing of the level) or "separate" (the roughing first, then the finish passes as their own
    record with the finish tool, feeds and step down; job.run). Older documents: Pocket "finish", Adaptive
    "finish_profile"; an Undercut finishes in its pass sequence by default."""
    m = op.get("finish_mode")
    if m in ("off", "level", "separate"):
        return m
    t = op.get("type")
    if t == "pocket":
        return "level" if op.get("finish", True) else "off"
    if t == "adaptive":
        return "level" if op.get("finish_profile") else "off"
    if t == "undercut":
        return "level"
    return "off"


def phase_of(op):
    """None (one record), "rough" or "finish" (the two records of a separate finish)."""
    return op.get("_phase")


def finish_in_level(op):
    return phase_of(op) is None and finish_mode(op) == "level"


def finish_feed(ctx):
    """Feed of the finish passes: "finish_feed" of the operation, else the feed of the operation."""
    return _f(ctx.op.get("finish_feed"), 0.0) or ctx.feed


def finish_loops(ctx, mv, fin, z, cw, keep_down=True, feed=None):
    """The loops of a finish region at the level z (the tool enters the first loop, links or lifts to the others)."""
    n = 0
    for loop in G.loops_of(fin):
        lp = nearest_start(oriented(loop, cw), mv.cur and mv.cur[:2])
        if mv.cur is None or mv.cur[2] > z + 1e-6:
            mv.enter(lp[0][0], lp[0][1], z)
        else:
            link_or_lift(mv, fin, lp[0], z, keep_down)
        mv.polyline(lp[1:] + [lp[0]], z, feed)
        n += 1
    return n


def oriented(loop, cw):
    """The loop in clockwise order when cw, else counterclockwise (signed area)."""
    a = 0.0
    for (x0, y0), (x1, y1) in zip(loop, loop[1:] + loop[:1]):
        a += x0 * y1 - x1 * y0
    if (a < 0) != cw:
        return loop[::-1]
    return loop


def nearest_start(loop, p):
    if p is None:
        return loop
    k = min(range(len(loop)), key=lambda i: (loop[i][0] - p[0]) ** 2 + (loop[i][1] - p[1]) ** 2)
    return loop[k:] + loop[:k]


# --------------------------------------------------------------------------- regions

def region_of_faces(ctx, faces, allowance, z_lo, z_hi, extend_open=True):
    """Region of the tool centre for floor faces at a level between z_lo and z_hi (see pocket_region), joined."""
    from shapely.ops import unary_union
    regs = []
    for fc in faces:
        info = G.floor_info(ctx.shape, fc)
        regs.append(pocket_region(ctx.shape, info, TB.radius(ctx.tool), allowance, z_lo, z_hi, extend_open, ctx.op.get("use_outline"), reach_of(ctx, z_lo)))
    return unary_union(regs) if regs else None


def walls_over(shape, z_lo, z_hi, z_reach=None):
    """Union of the part sections the tool meets between z_lo and z_hi (the slab of a level) and up to z_reach
    (the top of the cutting part of the tool): the walls, islands and overhangs to keep away from."""
    from shapely.ops import unary_union
    zs = [z_lo + G.EPS, z_hi - G.EPS]
    if z_reach is not None and z_reach > z_hi + G.EPS:
        zs += [z_reach - G.EPS, (z_hi + z_reach) / 2.0]
    bb = G.bbox(shape)
    zs = [z for z in zs if bb[2] < z < bb[5]]
    return unary_union([G.section_polys(shape, z) for z in zs]) if zs else G.section_polys(shape, z_lo + G.EPS)


def pocket_region(shape, info, R, allowance, z_lo, z_hi, extend_open=True, use_outline=False, z_reach=None):
    """Region the tool centre may cover at a level between z_lo and z_hi: the floor polygon, extended beyond the
    open edges by 2R + allowance + 1 mm, less the part sections through the slab and up to the reach of the
    tool's cutting part (walls, islands, overhangs), then offset inward by R + allowance."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    poly = info["poly"]
    if use_outline:
        poly = Polygon(poly.exterior)
    ext = [poly]
    E = 2 * R + allowance + 1.0
    if extend_open:
        for pl in info["open"]:
            if len(pl) > 1:
                ext.append(LineString(pl).buffer(E, G.ARC_SEGS // 4, cap_style="flat"))
    region = unary_union(ext)
    walls = walls_over(shape, z_lo, z_hi, z_reach)
    region = region.difference(walls.buffer(allowance + G.sag(R), G.PATH_SEGS))
    return region.buffer(-R, G.PATH_SEGS)


def reach_of(ctx, z):
    """Top of the cutting part of the tool at the level z, limited to the top of the stock."""
    return min(z + TB.cutting_height(ctx.tool), ctx.stock_bb[5])


def offset_rings(region, stepover, outward=False):
    """Loops of the region boundary offset inward by multiples of the stepover, innermost first (outward: the
    boundary first)."""
    rings = []
    k = 0
    while True:
        g = region.buffer(-k * stepover, G.PATH_SEGS) if k else region
        if g.is_empty:
            break
        rings.append(G.loops_of(g))
        k += 1
        if k > 10000:
            break
    if not outward:
        rings.reverse()
    return rings


def zigzag_lines(region, stepover, angle_deg, zig=True):
    """Parallel lines across the region at the angle, spaced by the stepover, as polylines of the tool centre,
    ordered as a zigzag (alternating direction) or all in one direction."""
    from shapely.geometry import LineString
    from shapely import affinity
    if region.is_empty:
        return []
    rot = affinity.rotate(region, -angle_deg, origin=(0, 0), use_radians=False)
    x0, y0, x1, y1 = rot.bounds
    out = []
    y = y0 + 1e-6
    k = 0
    ys = []
    while y <= y1 - 1e-6:
        ys.append(y)
        y += stepover
    if not ys or ys[-1] < y1 - stepover * 0.5:
        ys.append(y1 - 1e-6)
    for y in ys:
        ln = LineString([(x0 - 1, y), (x1 + 1, y)])
        segs = G.lines(rot.intersection(ln))
        segs.sort(key=lambda s: s.coords[0][0])
        if zig and k % 2 == 1:
            segs = [LineString(list(s.coords)[::-1]) for s in reversed(segs)]
        for s in segs:
            back = affinity.rotate(s, angle_deg, origin=(0, 0), use_radians=False)
            out.append([(float(x), float(yy)) for x, yy in back.coords])
        k += 1
    return out


def link_or_lift(mv, region, pt, z, keep_down=True):
    """Move to the point pt at the level z: a feed when the straight line lies in the region (and keep_down),
    else up to the clearance height, over and a plunge."""
    from shapely.geometry import LineString
    if mv.cur is not None and keep_down and region is not None and region.buffer(1e-6).contains(LineString([tuple(mv.cur[:2]), pt])):
        mv.feed_to(pt[0], pt[1], z)
        return False
    mv.enter(pt[0], pt[1], z)
    return True


def helix_entry(mv, region, R, z_from, z_to, pitch, cw=False):
    """Helix down about a point with the tool inside the region: quarter arcs down, then a flat turn. Returns the
    end point, or None when no helix fits (the caller plunges)."""
    cen = None
    for rh in (0.5 * R, 0.35 * R, 0.25 * R):
        inner = region.buffer(-rh, G.ARC_SEGS // 4)
        if not inner.is_empty:
            q = inner.representative_point()
            cen = (q.x, q.y, rh)
            break
    if cen is None:
        return None
    cx, cy, rh = cen
    mv.rapid_to(cx + rh, cy)
    mv.to_safe()
    mv.plunge_to(z_from)
    zc = z_from
    sgn = -1.0 if cw else 1.0
    while zc > z_to + 1e-9:
        dz = min(pitch, zc - z_to)
        for q in range(4):
            ang = sgn * (q + 1) * math.pi / 2
            mv.arc_to(cx + rh * math.cos(ang), cy + rh * math.sin(ang), zc - dz * (q + 1) / 4, cx, cy, cw, feed=getattr(mv, "ramp", None))
        zc -= dz
    for q in range(4):
        ang = sgn * (q + 1) * math.pi / 2
        mv.arc_to(cx + rh * math.cos(ang), cy + rh * math.sin(ang), z_to, cx, cy, cw)
    return (cx + rh, cy)


def air_entry(ctx, region, z, z_above, R, near):
    """A point of the region where the tool goes down to the level z beside the stock (no stock in the slab from z
    to z_above within R + 0.5 mm), nearest to near; None when the stock covers the whole region."""
    from shapely.geometry import Point
    from shapely.ops import nearest_points
    st = getattr(ctx, "stock", None)
    if st is None:
        return None
    try:
        mat = walls_over(st, z, z_above)
    except Exception:  # noqa: BLE001
        return None
    free = region.difference(mat.buffer(R + 0.5, G.PATH_SEGS)) if not mat.is_empty else region
    if free.is_empty or free.area < 1e-6:
        return None
    q = nearest_points(free, Point(near[0], near[1]))[0]
    return (q.x, q.y)


def clear_region(ctx, mv, region, z, z_above, stepover, pattern="offset", angle=0.0, cw=False, start_at="centre",
                 keep_down=True, entry="plunge", pitch=1.0, finish_region=None):
    """Cuts a region at the level z with the pattern. Returns the number of plunges. The first entry of the level
    goes down beside the stock when the region reaches past it (an open side), else by the entry (helix or
    plunge)."""
    plunges = 0
    R = TB.radius(ctx.tool)
    if region is None or region.is_empty:
        return 0
    first = True

    def start(pt):
        nonlocal first, plunges
        if first:
            first = False
            ae = air_entry(ctx, region, z, z_above, R, pt)
            if ae is not None:
                mv.enter(ae[0], ae[1], z)
                if math.dist(ae, pt[:2]) > 1e-6 and link_or_lift(mv, region, pt, z, True):
                    plunges += 1
                return
            if entry == "helix":
                end = helix_entry(mv, region, R, z_above, z, pitch, cw)
                if end is not None:
                    if link_or_lift(mv, region, pt, z, True):
                        plunges += 1
                    return
                ctx.message("Z %.3f mm: no room for a helix of 0.25 x R: plunge entry" % z)
            mv.enter(pt[0], pt[1], z)
            plunges += 1
        elif link_or_lift(mv, region, pt, z, keep_down):
            plunges += 1
    if pattern in ("zigzag", "line", "zigzag_offset"):
        for pl in zigzag_lines(region, stepover, angle, zig=pattern != "line"):
            if pattern == "line":
                if mv.cur is not None:
                    mv.retract()
                mv.enter(pl[0][0], pl[0][1], z)
                plunges += 1
            else:
                start(pl[0])
            mv.polyline(pl[1:], z)
        if pattern == "zigzag_offset":
            for loop in G.loops_of(region):
                lp = nearest_start(oriented(loop, cw), mv.cur and mv.cur[:2])
                start(lp[0])
                mv.polyline(lp[1:] + [lp[0]], z)
    elif pattern == "spiral":
        from .adaptive import spiral_paths
        for pl in spiral_paths(region, stepover, cw):
            start(pl[0])
            mv.polyline(pl[1:], z)
    else:
        rings = offset_rings(region, stepover, outward=start_at == "boundary")
        prev = None
        for loops in rings:
            for loop in loops:
                lp = nearest_start(oriented(loop, cw), prev or (mv.cur and mv.cur[:2]))
                start(lp[0])
                mv.polyline(lp[1:] + [lp[0]], z)
                prev = lp[0]
    if finish_region is not None and not finish_region.is_empty:
        for loop in G.loops_of(finish_region):
            lp = nearest_start(oriented(loop, cw), mv.cur and mv.cur[:2])
            if link_or_lift(mv, finish_region, lp[0], z, keep_down):
                plunges += 1
            mv.polyline(lp[1:] + [lp[0]], z, finish_feed(ctx))
    return plunges


# --------------------------------------------------------------------------- face

def run_face(ctx):
    """Face: the top of the stock (or a bound box, or the picked faces) cleared down to the part top in levels."""
    from shapely.geometry import box as sbox
    from shapely.ops import unary_union
    check_shape(ctx, "endmill", "bullnose")
    op = ctx.op
    R = TB.radius(ctx.tool)
    sb, pb = ctx.stock_bb, ctx.part_bb
    boundary = op.get("boundary") or "stock"
    faces = base_faces(ctx) if boundary == "faces" else []
    if boundary == "faces" and not faces:
        raise ValueError("no face is picked")
    if faces:
        reg = unary_union([G.face_outline(fc) for fc in faces])
        zf = min(fc.center().Z for fc in faces)
        x0, y0, x1, y1 = reg.bounds
        region0 = sbox(x0, y0, x1, y1) if boundary == "boundbox" else reg
        h = ctx.heights(final=zf)
    else:
        region0 = sbox(sb[0], sb[1], sb[3], sb[4])
        h = ctx.heights(final=pb[5])
    over = R + _f(op.get("overhang"), 1.0)
    region = region0.buffer(over, 1)
    stepover = stepover_mm(ctx, 60.0)
    pattern = op.get("pattern") or "zigzag"
    angle = _f(op.get("angle"), 0.0)
    cw = (op.get("cut_mode") or "CW") == "CW"
    lv = _levels_of(h)
    if not lv:
        ctx.message("the start depth %.3f mm is not above the final depth %.3f mm: nothing to cut" % (h["start"], h["final"]))
        return ctx.moves()
    mv = ctx.moves()
    for i, z in enumerate(lv):
        z_above = h["start"] if i == 0 else lv[i - 1]
        if pattern == "offset":
            clear_region(ctx, mv, region, z, z_above, stepover, "offset", angle, cw, "boundary", True, "plunge")
        else:
            clear_region(ctx, mv, region, z, z_above, stepover, pattern, angle, cw, "boundary", True, "plunge")
        mv.retract()
    ctx.message("Z %.3f mm to %.3f mm in %d level(s), %s pattern, step over %.2f mm" % (h["start"], h["final"], len(lv), pattern, stepover))
    return mv


# --------------------------------------------------------------------------- pocket

def run_pocket(ctx):
    """Pocket Shape: the material above the picked floor faces (or inside the picked walls) removed in levels
    with the pattern."""
    check_shape(ctx, "endmill", "bullnose")
    op = ctx.op
    faces = base_faces(ctx)
    if not faces:
        raise ValueError("no floor face is picked")
    R = TB.radius(ctx.tool)
    allowance = max(0.0, _f(op.get("extra_offset"), _f(op.get("allowance"), 0.0)))
    stepover = stepover_mm(ctx, 40.0)
    pattern = op.get("pattern") or "offset"
    angle = _f(op.get("angle"), 0.0)
    cw = (op.get("cut_mode") or "CW") == "CW"
    start_at = op.get("start_at") or "centre"
    keep_down = op.get("keep_down", True)
    phase = phase_of(op)
    finish = (finish_in_level(op) and allowance > 0) or phase == "finish"
    spring = bool(op.get("finish_spring")) and (finish_in_level(op) or phase == "finish")
    entry = op.get("entry") or "helix"
    pitch = max(_f(op.get("helix_pitch"), 1.0), 0.05)
    infos, walls = [], []
    for fc in faces:
        try:
            infos.append(G.floor_info(ctx.shape, fc))
        except ValueError:
            walls.append(fc)
    if walls and not infos:
        outline, zr = G.wall_outline(ctx.shape, walls)
        if outline is None or outline.is_empty:
            raise ValueError("the picked walls do not enclose a region")
        infos.append({"z": zr[0], "poly": outline, "open": [], "wall": True})
    elif walls:
        ctx.message("%d wall face(s) left out: pick floors or walls" % len(walls))
    z_floor = min(i["z"] for i in infos)
    h = ctx.heights(final=z_floor)
    mv = ctx.moves()
    total_levels = 0
    plunges = 0
    tops = []
    for info in infos:
        from shapely.geometry import Polygon
        # the levels start at the top of the stock over the floor
        poly = Polygon(info["poly"].exterior) if op.get("use_outline") else info["poly"]
        z_top = stock_top_over(ctx.stock, poly, info["z"], h["start"])
        hh = dict(h, start=z_top, final=max(info["z"], h["final"]) if op.get("final_depth") is None else h["final"])
        lv = _levels_of(hh)
        if not lv:
            ctx.message("floor Z %.3f mm: no stock above the floor, nothing to cut" % info["z"])
            continue
        tops.append(z_top)
        total_levels += len(lv)
        for i, z in enumerate(lv):
            zt = z_top if i == 0 else lv[i - 1]
            if info.get("wall"):
                walls = walls_over(ctx.shape, z, zt, reach_of(ctx, z))
                region = poly.difference(walls.buffer(allowance + G.sag(R), G.PATH_SEGS)).buffer(-R, G.PATH_SEGS)
                fin = poly.difference(walls.buffer(G.sag(R), G.PATH_SEGS)).buffer(-R, G.PATH_SEGS) if finish else None
            else:
                region = pocket_region(ctx.shape, info, R, allowance, z, zt, True, op.get("use_outline"), reach_of(ctx, z))
                fin = pocket_region(ctx.shape, info, R, 0.0, z, zt, True, op.get("use_outline"), reach_of(ctx, z)) if finish else None
            if phase == "finish":
                if fin is None or fin.is_empty:
                    ctx.message("Z %.3f mm: no room for the finish tool" % z)
                    continue
                finish_loops(ctx, mv, fin, z, cw, keep_down)
                if spring and i == len(lv) - 1:
                    finish_loops(ctx, mv, fin, z, cw, keep_down)
                mv.retract()
                continue
            if region.is_empty:
                ctx.message("Z %.3f mm: no room for the tool" % z)
                continue
            plunges += clear_region(ctx, mv, region, z, zt, stepover, pattern, angle, cw, start_at, keep_down, entry, pitch, fin)
            if spring and fin is not None and i == len(lv) - 1:
                finish_loops(ctx, mv, fin, z, cw, keep_down, finish_feed(ctx))
            mv.retract()
        fill = G.prism(poly, info["z"], z_top)
        if fill is not None:
            pin = G.common_volume(ctx.shape, fill) or 0.0
            ctx.res["_remaining"] = (lambda st, fill=fill, pin=pin, prev=ctx.res.get("_remaining"): max(0.0, (G.common_volume(st, fill) or 0.0) - pin) + (prev(st) if prev else 0.0))
    if tops and op.get("start_depth") is None:
        ctx.h["start"] = round(max(tops), 4)              # the start depth shown: the stock over the floors
    ctx.message("%d floor(s), %d level(s), %s pattern, step over %.2f mm%s" % (len(infos), total_levels, pattern, stepover,
                                                                         ", %d plunge(s) between separate loops" % plunges if plunges > len(infos) else ""))
    return mv


def stock_top_over(stock, geom, z0, z1):
    """Highest Z of the stock over a polygon geometry between z0 and z1 (z0 when the stock has no material
    there)."""
    pr = G.prism(geom, z0, z1 + 1.0)
    if pr is None:
        return z0
    sh = G.common_shape(stock, pr)
    if sh is None:
        return z1
    if not sh.solids():
        return z0
    return min(z1, round(G.bbox(sh)[5], 4))


# --------------------------------------------------------------------------- profile

def profile_loops(ctx):
    """[(loop [(x, y)], closed, kind)] of the contours a profile cuts, before the tool offset: the model
    outline (no base geometry), the outlines of the picked faces, or the picked edges (chains)."""
    from shapely.ops import unary_union, linemerge
    from shapely.geometry import LineString, MultiLineString
    op = ctx.op
    faces = base_faces(ctx)
    edges = base_edges(ctx)
    out = []
    if edges:
        ls = []
        for e in edges:
            pts = [(p[0], p[1]) for p in G.edge_polyline(e)]
            pts = [q for i, q in enumerate(pts) if i == 0 or math.dist(q, pts[i - 1]) > 1e-6]
            if len(pts) > 1:
                ls.append(LineString(pts))
        m = linemerge(MultiLineString(ls)) if len(ls) > 1 else ls[0]
        for l in (m.geoms if hasattr(m, "geoms") else [m]):
            pts = [(float(x), float(y)) for x, y in l.coords]
            closed = math.dist(pts[0], pts[-1]) < 1e-6 and len(pts) > 3
            out.append((pts[:-1] if closed else pts, closed, "edges"))
        return out
    if faces:
        regs = []
        for fc in faces:
            try:
                regs.append(G.face_outline(fc))
            except Exception:
                continue
        region = unary_union(regs)
    else:
        region = G.silhouette(ctx.shape)
    holes_ok = op.get("process_holes", False)
    perim = op.get("process_perimeter", True)
    circles = op.get("process_circles", False)
    for p in G.polys(region):
        if perim:
            out.append((G.ring_pts(p.exterior), True, "perimeter"))
        for hring in p.interiors:
            pts = G.ring_pts(hring)
            if _is_circle(pts):
                if circles:
                    out.append((pts, True, "circle"))
            elif holes_ok:
                out.append((pts, True, "hole"))
    return out


def _is_circle(pts, tol=0.02):
    if len(pts) < 8:
        return False
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    rs = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    r = sum(rs) / len(rs)
    return r > 0 and max(abs(x - r) for x in rs) < tol * r + 1e-3


def run_profile(ctx):
    """Profile: contours of the model, of faces or of edges, offset by the tool radius to the chosen side, cut in
    levels from the start depth to the final depth."""
    from shapely.geometry import Polygon, LineString
    check_shape(ctx, "endmill", "bullnose", "ballend")
    op = ctx.op
    R = TB.radius(ctx.tool)
    extra = max(0.0, _f(op.get("extra_offset"), _f(op.get("allowance"), 0.0)))
    comp = op.get("compensation", True)
    cw = (op.get("direction") or "CW") == "CW"
    outside = (op.get("side") or "outside") == "outside"
    faces = base_faces(ctx)
    edges = base_edges(ctx)
    loops = profile_loops(ctx)
    if not loops:
        raise ValueError("no contour to cut")
    # depths: the model bottom, or the bottom of the faces or edges
    if faces:
        zf = min(G.bbox(fc)[2] for fc in faces)
    elif edges:
        zf = min(G.bbox(e)[2] for e in edges)
    else:
        zf = ctx.part_bb[2]
    h = ctx.heights(final=zf - max(0.0, _f(op.get("extra"), 0.0)))
    lv = _levels_of(h)
    if not lv:
        raise ValueError("the final depth %.3f mm is not below the start depth %.3f mm" % (h["final"], h["start"]))
    off = (R + extra + G.sag(R)) if comp else extra
    off0 = (R + G.sag(R)) if comp else 0.0                    # the finish pass: no stock left
    phase = phase_of(op)
    npass = max(1, int(_f(op.get("passes"), 1)))
    stepover = stepover_mm(ctx, 50.0)
    spring = bool(op.get("finish_spring")) and (finish_in_level(op) or phase == "finish")
    paths = []            # [(loop pts, closed, finish)]
    for pts, closed, kind in loops:
        inward = (kind in ("hole", "circle")) == outside      # a hole is cut from inside when the side is outside
        ds = [(off + k * stepover, False) for k in range(npass - 1, -1, -1)]
        if phase == "finish":
            ds = [(off0, True)]
        elif finish_in_level(op) and extra > 0:
            ds.append((off0, True))
        for d, fp in ds:
            if closed:
                p = Polygon(pts).buffer(0)
                g = p.buffer(d if not inward else -d, G.PATH_SEGS)
                for lp in G.loops_of(g):
                    paths.append((oriented(lp, cw), True, fp))
            else:
                ln = LineString(pts)
                side = -1.0 if (op.get("side") or "outside") == "inside" else 1.0
                g = ln.offset_curve(side * d, G.PATH_SEGS) if d > 0 else ln
                for l in G.lines(g):
                    paths.append(([(float(x), float(y)) for x, y in l.coords], False, fp))
    if not paths:
        raise ValueError("the offset contour is empty")
    mv = ctx.moves()
    for lp, closed, fp in paths:
        fd = finish_feed(ctx) if fp and phase is None else None
        for i, z in enumerate(lv):
            if i == 0 or not closed:
                mv.enter(lp[0][0], lp[0][1], z)
            else:
                mv.plunge_to(z)
            mv.polyline(lp[1:] + ([lp[0]] if closed else []), z, fd)
            if fp and spring and i == len(lv) - 1:
                if not closed:
                    lp = lp[::-1]
                mv.polyline(lp[1:] + ([lp[0]] if closed else []), z, fd)
            if not closed:
                lp = lp[::-1] if i + 1 < len(lv) else lp
        mv.retract()
    ctx.message("%d contour(s), Z %.3f mm to %.3f mm in %d level(s), %s, %s%s" % (len(paths), h["start"], h["final"], len(lv),
                "outside" if outside else "inside", "CW" if cw else "CCW", "" if comp else ", no tool compensation"))
    return mv


# --------------------------------------------------------------------------- drilling

def hole_list(ctx):
    """Holes of the picked faces: [{"x", "y", "r", "z0", "z1"}], one per axis position."""
    faces = base_faces(ctx)
    if not faces:
        raise ValueError("no hole face is picked")
    out, seen = [], set()
    for fc in faces:
        hi = G.hole_info(fc)
        key = (round(hi["x"], 3), round(hi["y"], 3))
        if key in seen:
            continue
        seen.add(key)
        out.append(hi)
    return out


def run_drilling(ctx):
    """Drilling: the picked holes from the start depth to the final depth with straight moves; pecks with a
    retract to the retract height, a dwell at the bottom."""
    check_shape(ctx, "drill", "endmill")
    op = ctx.op
    D = 2 * TB.radius(ctx.tool)
    tip = TB.tip_length(ctx.tool) if op.get("tip", True) else 0.0
    peck = max(0.0, _f(op.get("peck"), 0.0))
    dwell = max(0.0, _f(op.get("dwell"), 0.0))
    brk = max(0.0, _f(op.get("breakthrough"), 1.0))
    holes = hole_list(ctx)
    pb = ctx.part_bb
    zs = []
    for hi in holes:
        through = op.get("through")
        if through is None:
            through = hi["z0"] <= pb[2] + 1e-6
        zs.append((pb[2] - brk if through else hi["z0"]) - tip)
    h = ctx.heights(start=max(hi["z1"] for hi in holes) if op.get("start_depth") is None and all(hi["z1"] < ctx.stock_bb[5] for hi in holes) else None, final=min(zs))
    retract = h["start"] + max(0.0, _f(op.get("retract"), 1.0))
    mv = ctx.moves()
    n = 0
    for hi, zb in zip(holes, zs):
        if abs(2 * hi["r"] - D) > 0.05:
            ctx.message("hole at X %.2f Y %.2f: diameter %.2f mm, tool %.2f mm" % (hi["x"], hi["y"], 2 * hi["r"], D))
        z_bot = zb if op.get("final_depth") is None else h["final"]
        if z_bot >= h["start"] - 1e-9:
            ctx.message("hole at X %.2f Y %.2f: nothing to drill" % (hi["x"], hi["y"]))
            continue
        n0 = len(mv.moves)
        mv.rapid_to(hi["x"], hi["y"])
        mv.rapid_down(retract)
        z = h["start"]
        while z > z_bot + 1e-9:
            zn = max(z_bot, z - peck) if peck > 0 else z_bot
            mv.plunge_to(zn)
            z = zn
            if z > z_bot + 1e-9:
                mv.rapid_down(retract)
                mv.rapid_down(z + 0.5)
        if dwell > 0:
            mv.item("dwell", s=dwell)
        mv.rapid_down(retract)
        mv.retract()
        # a canned cycle (G81 / G82 / G83) for the posts that have them: the moves of the hole are tagged
        cyc = {"x": hi["x"], "y": hi["y"], "z": z_bot, "r": retract, "q": peck, "p": dwell, "f": ctx.plunge}
        ctx.res.setdefault("cycles", []).append(cyc)
        for m in mv.moves[n0 + 1:]:
            m["cyc"] = len(ctx.res["cycles"]) - 1
        n += 1
    ctx.message("%d hole(s)%s%s" % (n, ", peck %.2f mm" % peck if peck > 0 else "", ", tip %.2f mm added" % tip if tip > 0 else ""))
    return mv


# --------------------------------------------------------------------------- helix

def run_helix(ctx):
    """Helix: the picked holes cleared with helical passes of an end mill, from the outside (or the inside)
    stepping over, the pitch the step down."""
    check_shape(ctx, "endmill", "bullnose")
    op = ctx.op
    R = TB.radius(ctx.tool)
    extra = max(0.0, _f(op.get("extra_offset"), 0.0))
    cw = (op.get("direction") or "CW") == "CW"
    inside_first = (op.get("start_side") or "outside") == "inside"
    stepover = stepover_mm(ctx, 50.0)
    holes = hole_list(ctx)
    brk = max(0.0, _f(op.get("breakthrough"), 0.0))
    pb = ctx.part_bb
    zs = []
    for hi in holes:
        through = hi["z0"] <= pb[2] + 1e-6
        zs.append(pb[2] - brk if through else hi["z0"])
    h = ctx.heights(final=min(zs))
    pitch = h["step"]
    mv = ctx.moves()
    n = 0
    for hi, zb in zip(holes, zs):
        rmax = hi["r"] - R - extra - G.sag(R)
        if rmax < 0:
            ctx.message("hole at X %.2f Y %.2f: the tool is larger than the hole (%.2f mm)" % (hi["x"], hi["y"], 2 * hi["r"]))
            continue
        z_bot = zb if op.get("final_depth") is None else h["final"]
        radii = []
        r = rmax
        while r > 1e-6:
            radii.append(r)
            r -= stepover
        if not radii or radii[-1] > 1e-6:
            radii.append(0.0) if rmax > 0 and radii and radii[-1] > stepover * 0.5 else None
        radii = [x for x in radii if x > 1e-6] or [0.0]
        if inside_first:
            radii = radii[::-1]
        sgn = -1.0 if cw else 1.0
        for r in radii:
            mv.rapid_to(hi["x"] + r, hi["y"])
            mv.to_safe()
            mv.plunge_to(h["start"])
            zc = h["start"]
            if r < 1e-6:
                mv.plunge_to(z_bot)
            else:
                while zc > z_bot + 1e-9:
                    dz = min(pitch, zc - z_bot)
                    for q in range(4):
                        ang = sgn * (q + 1) * math.pi / 2
                        mv.arc_to(hi["x"] + r * math.cos(ang), hi["y"] + r * math.sin(ang), zc - dz * (q + 1) / 4, hi["x"], hi["y"], cw)
                    zc -= dz
                for q in range(4):
                    ang = sgn * (q + 1) * math.pi / 2
                    mv.arc_to(hi["x"] + r * math.cos(ang), hi["y"] + r * math.sin(ang), z_bot, hi["x"], hi["y"], cw)
            mv.retract()
        n += 1
    ctx.message("%d hole(s), pitch %.2f mm, step over %.2f mm" % (n, pitch, stepover))
    return mv


# --------------------------------------------------------------------------- slot

def run_slot(ctx):
    """Slot: a straight or circular slot from two points, an edge or a slot floor, cut along its centre line in
    one pass at the final depth or in levels."""
    check_shape(ctx, "endmill", "bullnose", "ballend", "tapered")
    op = ctx.op
    R = TB.radius(ctx.tool)
    pts = op.get("points") or []
    edges = base_edges(ctx)
    faces = base_faces(ctx)
    path = None          # [(x, y)] or ("arc", centre, r, a0, a1)
    z_ref = None
    if len(pts) >= 2:
        path = [(_f(pts[0][0]), _f(pts[0][1])), (_f(pts[1][0]), _f(pts[1][1]))]
    elif edges:
        e = edges[0]
        if e.geom_type.name == "CIRCLE":
            c = e.arc_center
            r = (e.position_at(0) - c).length + _f(op.get("radius_offset"), 0.0)
            a0 = math.atan2(e.position_at(0).Y - c.Y, e.position_at(0).X - c.X)
            a1 = math.atan2(e.position_at(1).Y - c.Y, e.position_at(1).X - c.X)
            if e.length > 2 * math.pi * r * 0.999:
                a1 = a0 + 2 * math.pi
            elif a1 <= a0:
                a1 += 2 * math.pi
            path = ("arc", (c.X, c.Y), r, a0, a1)
        else:
            a, b = e.position_at(0), e.position_at(1)
            path = [(a.X, a.Y), (b.X, b.Y)]
        z_ref = G.bbox(e)[2]
    elif faces:
        fc = faces[0]
        poly = G.face_outline(fc)
        rect = poly.minimum_rotated_rectangle
        rp = list(rect.exterior.coords)[:4]
        d1 = math.dist(rp[0], rp[1])
        d2 = math.dist(rp[1], rp[2])
        if d1 >= d2:
            a = ((rp[0][0] + rp[3][0]) / 2, (rp[0][1] + rp[3][1]) / 2)
            b = ((rp[1][0] + rp[2][0]) / 2, (rp[1][1] + rp[2][1]) / 2)
            w = d2
        else:
            a = ((rp[0][0] + rp[1][0]) / 2, (rp[0][1] + rp[1][1]) / 2)
            b = ((rp[2][0] + rp[3][0]) / 2, (rp[2][1] + rp[3][1]) / 2)
            w = d1
        # the centre line between the ends of a rounded slot
        u = ((b[0] - a[0]), (b[1] - a[1]))
        L = math.hypot(*u) or 1.0
        u = (u[0] / L, u[1] / L)
        path = [(a[0] + u[0] * w / 2, a[1] + u[1] * w / 2), (b[0] - u[0] * w / 2, b[1] - u[1] * w / 2)]
        z_ref = fc.center().Z
        if w > 2 * R + 0.05:
            ctx.message("slot width %.2f mm, tool %.2f mm: the slot is not cleared to its width" % (w, 2 * R))
    else:
        raise ValueError("no slot geometry: two points, an edge or a slot floor")
    # a slot from points or an edge starts at the part surface under its path (an edge: its top)
    z_start = None
    if op.get("start_depth") is None:
        if len(pts) >= 2:
            z_start = surface_z(ctx, [path] if isinstance(path, list) else [])
        elif edges:
            z_start = max(G.bbox(edges[0])[5], z_ref if z_ref is not None else -1e30)
    h = ctx.heights(start=z_start, final=z_ref if z_ref is not None else None)
    lv = _levels_of(h) if (op.get("layer") or "multi") == "multi" else [h["final"]]
    if not lv:
        raise ValueError("the final depth %.3f mm is not below the start depth %.3f mm" % (h["final"], h["start"]))
    es, ee = _f(op.get("extend_start"), 0.0), _f(op.get("extend_end"), 0.0)
    mv = ctx.moves()
    if isinstance(path, tuple):
        _, c, r, a0, a1 = path
        if op.get("reverse"):
            a0, a1 = a1, a0
        da = (es / r) if r > 0 else 0.0
        de = (ee / r) if r > 0 else 0.0
        a0 = a0 - da if a1 > a0 else a0 + da
        a1 = a1 + de if a1 > a0 else a1 - de
        cw = a1 < a0
        n = max(2, int(math.ceil(abs(a1 - a0) / (math.pi / 2) - 1e-9)))
        for i, z in enumerate(lv):
            p0 = (c[0] + r * math.cos(a0), c[1] + r * math.sin(a0))
            if i == 0:
                mv.enter(p0[0], p0[1], z)
            else:
                mv.plunge_to(z)
            for k in range(1, n + 1):
                a = a0 + (a1 - a0) * k / n
                mv.arc_to(c[0] + r * math.cos(a), c[1] + r * math.sin(a), z, c[0], c[1], cw)
            a0, a1 = a1, a0
            cw = not cw
        mv.retract()
    else:
        a, b = path
        if op.get("reverse"):
            a, b = b, a
        u = (b[0] - a[0], b[1] - a[1])
        L = math.hypot(*u) or 1.0
        u = (u[0] / L, u[1] / L)
        a = (a[0] - u[0] * es, a[1] - u[1] * es)
        b = (b[0] + u[0] * ee, b[1] + u[1] * ee)
        for i, z in enumerate(lv):
            if i == 0:
                mv.enter(a[0], a[1], z)
            else:
                mv.plunge_to(z)
            mv.feed_to(b[0], b[1], z)
            a, b = b, a
        mv.retract()
    ctx.message("slot Z %.3f mm to %.3f mm in %d pass(es)" % (h["start"], h["final"], len(lv)))
    return mv


# --------------------------------------------------------------------------- engrave

def engrave_paths(ctx):
    """Polylines [(x, y)] to engrave: picked edges of the part, the curves of a saved sketch, the outlines of a
    text."""
    op = ctx.op
    out = []
    for e in base_edges(ctx):
        pts = [(p[0], p[1]) for p in G.edge_polyline(e)]
        if len(pts) > 1:
            out.append(pts)
    sk = op.get("sketch")
    if sk:
        out += sketch_polylines(ctx, sk)
    tx = op.get("text")
    if tx and tx.get("text"):
        g, _ = G.text_polygons(str(tx["text"]), _f(tx.get("size"), 10.0), tx.get("font") or "", _f(tx.get("x")), _f(tx.get("y")),
                               _f(tx.get("angle")), tx.get("align") or "left")
        for lp in G.loops_of(g):
            out.append(lp + [lp[0]])
    return out


def sketch_polylines(ctx, sketch):
    """Polylines of the entities of a sketch record (the Sketch tab: lines, arcs, circles, polylines, splines) in
    job coordinates (the sketch on the XY plane, or on the record's "plane" {"o", "u", "v"} moved by the placement)."""
    from .. import part as P
    s = sketch if isinstance(sketch, dict) else {}
    if s.get("error"):
        raise ValueError(s["error"])
    try:
        segs, circles = P._segments(s)
    except Exception as e:
        raise ValueError("the sketch cannot be read: %s" % e)
    out = []
    to_xy = _sketch_mapper(ctx, s.get("plane"))
    from shapely.geometry import LineString, MultiLineString
    from shapely.ops import linemerge
    ls = []
    for k, a, b, m in segs:
        pts = []
        if k == "line":
            pts = [tuple(a), tuple(b)]
        elif k == "arc":
            pts = P._sample_arc3(a, m, b, 16)
        else:
            pts = [tuple(a), tuple(b)]
        pts = [(float(p[0]), float(p[1])) for p in pts]
        if len(pts) > 1:
            ls.append(LineString(pts))
    if ls:
        mg = linemerge(MultiLineString(ls)) if len(ls) > 1 else ls[0]
        for l in (mg.geoms if hasattr(mg, "geoms") else [mg]):
            out.append([(float(x), float(y)) for x, y in l.coords])
    for cx, cy, r in circles:
        out.append([(cx + r * math.cos(2 * math.pi * i / 32), cy + r * math.sin(2 * math.pi * i / 32)) for i in range(33)])
    if to_xy is not None:
        out = [[to_xy(p) for p in pl] for pl in out]
    return out


def _sketch_mapper(ctx, plane):
    """For a sketch on a plane {"o", "u", "v"} (part coordinates): the function (u, v) -> (x, y) of the job (the plane
    moved by the model placement); the plane must be horizontal in the job (within 0.5 deg). None for a sketch
    without a plane (the XY plane of the job)."""
    if not plane:
        return None
    from .. import assembly
    from . import placement as PL
    pl = PL.normalize((ctx.doc or {}).get("placement"))
    R = assembly._rot_matrix(pl["rot"])
    o = assembly._apply(R, pl["pos"], plane["o"])
    u = assembly._apply(R, [0, 0, 0], plane["u"], point=False)
    v = assembly._apply(R, [0, 0, 0], plane["v"], point=False)
    n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    if abs(n[2]) < math.cos(math.radians(0.5)):
        raise ValueError("the sketch plane is not horizontal in the job (normal %.3f, %.3f, %.3f): turn the part with Placement" % tuple(n))
    return lambda p: (o[0] + p[0] * u[0] + p[1] * v[0], o[1] + p[0] * u[1] + p[1] * v[1])


def surface_z(ctx, paths):
    """Z of the part surface under the paths (XY polylines): the Z of the picked floor faces when there are any,
    else the highest Z of the part under the first points of the paths, else the part top."""
    faces = base_faces(ctx)
    if faces:
        return max(G.bbox(fc)[5] for fc in faces)
    zs = []
    for pts in paths:
        for p in pts[:: max(1, len(pts) // 4)]:
            z = G.top_z_at(ctx.shape, p[0], p[1])
            if z is not None:
                zs.append(z)
    return max(zs) if zs else ctx.part_bb[5]


def run_engrave(ctx):
    """Engrave: the edges, sketch curves or text outlines followed at the levels from the start depth to the
    final depth."""
    op = ctx.op
    paths = engrave_paths(ctx)
    if not paths:
        raise ValueError("no edges, sketch or text to engrave")
    ctx.res["cuts_part"] = True
    edges = base_edges(ctx)
    if edges:
        zt = max(G.bbox(e)[5] for e in edges)
    else:
        zt = surface_z(ctx, paths)
    h = ctx.heights(start=zt if op.get("start_depth") is None else None, final=zt - max(0.1, _f(op.get("depth"), 0.5)) if op.get("final_depth") is None else None)
    lv = _levels_of(h) or [h["final"]]
    sv = int(_f(op.get("start_vertex"), 0))
    mv = ctx.moves()
    for pts in paths:
        closed = math.dist(pts[0], pts[-1]) < 1e-6 and len(pts) > 3
        if closed and sv:
            k = sv % (len(pts) - 1)
            pts = pts[k:-1] + pts[:k] + [pts[k]]
        for i, z in enumerate(lv):
            if i == 0:
                mv.enter(pts[0][0], pts[0][1], z)
            else:
                mv.plunge_to(z)
            mv.polyline(pts[1:], z)
            if not closed and i + 1 < len(lv):
                pts = pts[::-1]
        mv.retract()
    ctx.message("%d path(s), Z %.3f mm to %.3f mm in %d level(s)" % (len(paths), h["start"], h["final"], len(lv)))
    return mv


# --------------------------------------------------------------------------- deburr

def run_deburr(ctx):
    """Deburr: a chamfer of the width W along the picked edges (or the outer edges of the picked faces) with a
    V bit or a chamfer bit, the tip h below the chamfer."""
    from shapely.geometry import Polygon, LineString
    from shapely.ops import linemerge
    from shapely.geometry import MultiLineString
    check_shape(ctx, "vbit", "chamfer")
    ctx.res["cuts_part"] = True
    op = ctx.op
    tool = ctx.tool
    W = max(0.05, _f(op.get("width"), 1.0))
    hx = max(0.0, _f(op.get("extra_depth"), 0.5))
    phi = math.radians(_f(tool.get("angle"), 90.0) / 2.0)
    rt = max(0.0, _f(tool.get("tip"), 0.0) / 2.0)
    cw = (op.get("direction") or "CW") == "CW"
    depth = W / math.tan(phi) + hx                   # tip below the top of the edge
    o = rt + hx * math.tan(phi)                      # axis outside the edge
    edges = base_edges(ctx)
    faces = base_faces(ctx)
    if not edges and faces:
        edges = [e for fc in faces for e in fc.outer_wire().edges()]
    if not edges:
        raise ValueError("no edge is picked")
    ls = []
    zs = []
    for e in edges:
        pts = [(p[0], p[1]) for p in G.edge_polyline(e)]
        pts = [q for i, q in enumerate(pts) if i == 0 or math.dist(q, pts[i - 1]) > 1e-6]
        if len(pts) > 1:
            ls.append(LineString(pts))
        zs.append(G.bbox(e)[5])
    z_edge = max(zs)
    m = linemerge(MultiLineString(ls)) if len(ls) > 1 else ls[0]
    chains = [l for l in (m.geoms if hasattr(m, "geoms") else [m])]
    sec = G.section_polys(ctx.shape, z_edge - G.EPS)
    paths = []
    for l in chains:
        pts = [(float(x), float(y)) for x, y in l.coords]
        closed = math.dist(pts[0], pts[-1]) < 1e-6 and len(pts) > 3
        if closed:
            p = Polygon(pts[:-1]).buffer(0)
            rp = p.representative_point()
            inside = any(Polygon(hole).buffer(1e-6).contains(rp) for q in G.polys(sec) for hole in q.interiors)
            g = p.buffer(-o, G.PATH_SEGS) if inside else p.buffer(o, G.PATH_SEGS)
            for lp in G.loops_of(g):
                paths.append((oriented(lp, cw), True))
        else:
            # the side away from the material: the section is on one side of the chain
            left = l.offset_curve(o, G.PATH_SEGS)
            right = l.offset_curve(-o, G.PATH_SEGS)
            pick = left
            for cand in (left, right):
                if not cand.is_empty and not sec.buffer(1e-3).intersects(cand):
                    pick = cand
                    break
            for ll in G.lines(pick):
                paths.append(([(float(x), float(y)) for x, y in ll.coords], False))
    if not paths:
        raise ValueError("no chamfer path")
    z = z_edge - depth
    ctx.heights(start=z_edge, final=z)
    entry = int(_f(op.get("entry"), 0))
    mv = ctx.moves()
    for lp, closed in paths:
        if closed and entry:
            k = entry % len(lp)
            lp = lp[k:] + lp[:k]
        mv.enter(lp[0][0], lp[0][1], z)
        mv.polyline(lp[1:] + ([lp[0]] if closed else []), z)
        mv.retract()
    ctx.message("%d edge chain(s), chamfer %.2f mm at %.1f deg, tip %.3f mm below the edge, axis %.3f mm outside" % (len(paths), W, math.degrees(phi), depth, o))
    return mv


# --------------------------------------------------------------------------- undercut

def undercut_faces(shape):
    """Planar faces of the solid whose outward normal points downward and sideways: [(face, info)]."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    out = []
    for fc in shape.faces():
        try:
            if BRepAdaptor_Surface(fc.wrapped).GetType() != GeomAbs_Plane:
                continue
            info = undercut_info(fc)
        except ValueError:
            continue
        out.append((fc, info))
    return out


def undercut_info(fc):
    """Geometry of an undercut face: angle (deg, between the face and the base plane), height, depth (horizontal
    extent), z0 (base Z), z1, e0 (start of the bottom edge), d (unit direction of the bottom edge), length,
    out (horizontal unit vector away from the material), n (face normal)."""
    from build123d import Vector
    from .. import part as P
    c = fc.center()
    n = P._normal_at(fc, c)
    if n.Z > -0.01:
        raise ValueError("the face is not an undercut: its normal points up or sideways")
    nh = Vector(n.X, n.Y, 0)
    if nh.length < 0.01:
        raise ValueError("the face is horizontal: not an undercut")
    out = nh.normalized()
    ang = math.degrees(math.acos(min(1.0, abs(n.Z))))
    vs = [(v.X, v.Y, v.Z) for v in fc.vertices()]
    zs = [v[2] for v in vs]
    z0, z1 = min(zs), max(zs)
    h = z1 - z0
    if h < 1e-6:
        raise ValueError("the face has no height")
    bottom = None
    for e in fc.edges():
        a, b = e.position_at(0), e.position_at(1)
        if abs(a.Z - z0) < 1e-5 and abs(b.Z - z0) < 1e-5 and e.geom_type.name == "LINE" and e.length > 1e-6:
            if bottom is None or e.length > bottom.length:
                bottom = e
    if bottom is None:
        raise ValueError("the face has no straight bottom edge")
    a, b = bottom.position_at(0), bottom.position_at(1)
    d = Vector(b.X - a.X, b.Y - a.Y, 0).normalized()
    if out.cross(d).Z < 0:
        d = -d
    ts = [(Vector(v) - a).dot(d) for v in vs]
    t0, t1 = min(ts), max(ts)
    e0 = a + d * t0
    return {"angle": ang, "height": h, "depth": h / math.tan(math.radians(ang)), "z0": z0, "z1": z1,
            "e0": e0, "d": d, "t0": 0.0, "t1": t1 - t0, "out": out, "n": n, "length": t1 - t0}


def undercut_fill(info, extra=0.0):
    """Solid that fills the undercut of a face: the triangle between the face, the base plane and the vertical
    plane through the top edge, extruded along the face."""
    from build123d import Solid, Face, Wire, Vector
    e0, d, out = info["e0"], info["d"], info["out"]
    A = e0 - d * extra
    B = A + out * info["depth"]
    C = B + Vector(0, 0, info["height"])
    tri = Face(Wire.make_polygon([A, B, C], close=True))
    return Solid.extrude(tri, d * (info["length"] + 2 * extra))


def undercut_passes(info, tool, stepover, allowance):
    """Pass offsets (mm, outward from the finish position): the roughing passes stepping in from the outside,
    the pass at the allowance, and the finish pass at 0."""
    u = info["depth"]
    s = max(stepover, 1e-3)
    a_off = allowance / math.sin(math.radians(info["angle"])) if allowance > 0 else 0.0
    offs = []
    o = u - s
    while o > a_off + 1e-9:
        offs.append(o)
        o -= s
    if a_off > 0:
        offs.append(a_off)
    offs.append(0.0)
    return offs


def undercut_checks(info, tool):
    if TB.shape_of(tool) != "dovetail":
        raise ValueError("the tool %s is not a dovetail cutter" % tool.get("id"))
    ang = _f(tool.get("angle"), 60.0)
    if abs(ang - info["angle"]) > 0.5:
        raise ValueError("the cutter angle %.1f deg differs from the face angle %.1f deg" % (ang, info["angle"]))
    H = _f(tool.get("height"), 0.0)
    if H + 1e-6 < info["height"]:
        raise ValueError("the cutting height %.2f mm is less than the undercut height %.2f mm" % (H, info["height"]))
    R = TB.radius(tool)
    if R <= info["depth"]:
        raise ValueError("the cutter radius %.2f mm is not more than the undercut depth %.2f mm" % (R, info["depth"]))
    return "face angle %.1f deg, undercut depth %.2f mm, height %.2f mm, length %.1f mm" % (info["angle"], info["depth"], info["height"], info["length"])


def run_undercut(ctx):
    """Undercut: the material under the picked inclined faces removed with a dovetail cutter in passes along
    the face at the base Z, stepping in from the outside."""
    from build123d import Vector
    op = ctx.op
    tool = ctx.tool
    faces = base_faces(ctx)
    if not faces:
        raise ValueError("no undercut face is picked")
    stepover = _f(op.get("stepover"), 1.0)
    allowance = max(0.0, _f(op.get("allowance"), 0.0))
    runout = _f(op.get("runout"), 2.0)
    R = TB.radius(tool)
    infos = []
    for fc in faces:
        info = undercut_info(fc)
        ctx.message(undercut_checks(info, tool))
        infos.append(info)
    z0 = min(i["z0"] for i in infos)
    h = ctx.heights(final=z0)
    mv = ctx.moves()
    cur = ctx.stock
    gouge = 0.0
    for info in infos:
        e0, d, out, zf = info["e0"], info["d"], info["out"], info["z0"]
        if op.get("reverse"):
            d = -d
            e0 = info["e0"] + info["d"] * info["length"]
        ta, tb = -(R + runout), info["length"] + R + runout
        offs = undercut_passes(info, tool, stepover, allowance)
        phase = phase_of(op)
        mode = finish_mode(op)
        if phase == "finish":
            offs = [0.0, 0.0] if op.get("finish_spring") else [0.0]
        elif (phase == "rough" or mode == "off") and allowance > 0:
            offs = [o for o in offs if o > 1e-9]
        elif mode == "level" and op.get("finish_spring"):
            offs = offs + [0.0]
        for off in offs:
            base = e0 + out * (R + off)
            p0 = Vector(base.X + d.X * ta, base.Y + d.Y * ta, zf)
            p1 = Vector(base.X + d.X * tb, base.Y + d.Y * tb, zf)
            for q, what in ((p0, "start"), (p1, "end")):
                col = TB.sweep_line(tool, q, Vector(q.X, q.Y, h["clearance"]), "all")
                v = G.common_volume(col, cur)
                if v is None or v > G.TOL_VOL:
                    raise ValueError("the tool at the %s of the pass at offset %.2f mm is inside the stock (%.1f mm^3): the end of the undercut is not open or the stock is not cleared"
                                     % (what, off, v or 0.0))
            body = TB.sweep_line(tool, p0, p1, "body")
            vb = G.common_volume(body, cur)
            if vb is None or vb > G.TOL_VOL:
                raise ValueError("the neck or shank collides with the stock on the pass at offset %.2f mm (%.1f mm^3): the stock above the undercut is not cleared" % (off, vb or 0.0))
            swept = TB.sweep_line(tool, p0, p1, "cut")
            gouge += G.common_volume(swept, ctx.shape) or 0.0
            cur = G.cut(cur, [swept])
            mv.rapid_to(p0.X, p0.Y)
            mv.to_safe()
            mv.plunge_to(zf)
            mv.feed_to(p1.X, p1.Y, zf, finish_feed(ctx) if off <= 1e-9 and phase is None and mode == "level" else None)
            mv.retract()
        fill = undercut_fill(info)
        pin = G.common_volume(ctx.shape, fill) or 0.0
        ctx.res["_remaining"] = (lambda st, fill=fill, pin=pin, prev=ctx.res.get("_remaining"): max(0.0, (G.common_volume(st, fill) or 0.0) - pin) + (prev(st) if prev else 0.0))
    # the exact swept solids replace the level simulation
    ctx.res["hm_sim"] = {"stock": cur, "levels": [{"z": round(z0, 4), "removed_mm3": round(G.volume(ctx.stock) - G.volume(cur), 3), "gouge_mm3": round(gouge, 4),
                                                   "length_mm": round(sum(i["length"] + 2 * (R + runout) for i in infos) * len(undercut_passes(infos[0], tool, stepover, allowance)), 1)}],
                         "removed_mm3": G.volume(ctx.stock) - G.volume(cur), "gouge_mm3": gouge, "errors": []}
    return mv


# --------------------------------------------------------------------------- thread milling

def run_thread(ctx):
    """Thread milling: picked hole faces (internal) or cylindrical bosses (external) cut along a helix of the pitch,
    from a lead-in to the thread diameter. Climb milling: counter-clockwise inside, clockwise outside (conventional:
    the reverse); a right-hand thread: counter-clockwise moves up, clockwise moves down (left-hand: the reverse). Radial
    passes step the thread depth (0.6134 x pitch external, 0.5413 x pitch internal, or "depth") to the full
    diameter. The stock is cut by the ring between the hole and the thread diameter (the part has no thread form)."""
    from shapely.geometry import Point
    check_shape(ctx, "threadmill", "endmill")
    op = ctx.op
    R = TB.radius(ctx.tool)
    pitch = _f(op.get("pitch"), 1.0)
    if pitch <= 0:
        raise ValueError("the pitch must be above 0")
    internal = (op.get("side") or "internal") == "internal"
    rh = (op.get("hand") or "right") == "right"
    climb = (op.get("direction") or "climb") == "climb"
    passes = max(1, int(_f(op.get("passes"), 1)))
    holes = hole_list(ctx)
    mv = None
    rings = []
    n = 0
    for hi in holes:
        dmaj = _f(op.get("diameter"), 0.0) or (2 * hi["r"] + pitch if internal else 2 * hi["r"])
        depth = _f(op.get("depth"), 0.0) or (0.5413 if internal else 0.6134) * pitch
        rc_end = dmaj / 2.0 - R if internal else dmaj / 2.0 + R
        if internal and rc_end <= 0.05:
            raise ValueError("hole at X %.2f Y %.2f: the tool (D %.2f mm) does not fit the thread diameter %.2f mm" % (hi["x"], hi["y"], 2 * R, dmaj))
        top = hi["z1"] if op.get("start_depth") is None else _f(op["start_depth"])
        bot = hi["z0"] if op.get("final_depth") is None else _f(op["final_depth"])
        h = ctx.heights(start=top, final=bot)
        if mv is None:
            mv = ctx.moves()
        ccw = (internal == climb)                        # climb: counter-clockwise inside, clockwise outside (spindle M3)
        up = (ccw == rh)                                 # a right-hand helix: counter-clockwise up, clockwise down
        turns = max(1, int(math.ceil((h["start"] - h["final"]) / pitch)))
        z_lo, z_hi = h["final"], h["final"] + turns * pitch
        cx, cy = hi["x"], hi["y"]
        sgn = 1.0 if ccw else -1.0
        for k in range(passes):
            f = (k + 1) / float(passes)
            rc = rc_end - (1 - f) * depth if internal else rc_end + (1 - f) * depth
            z0 = z_lo if up else z_hi
            dz = pitch if up else -pitch
            if internal:
                mv.rapid_to(cx, cy)
                mv.to_safe()
                mv.plunge_to(z0)
                mv.arc_to(cx + rc, cy, z0, cx + rc / 2.0, cy, not ccw)
            else:
                mv.rapid_to(cx + rc + 2 * R, cy)
                mv.to_safe()
                mv.plunge_to(z0)
                mv.feed_to(cx + rc, cy, z0)
            for t in range(turns):
                for q in range(4):
                    a = sgn * (q + 1) * math.pi / 2
                    mv.arc_to(cx + rc * math.cos(a), cy + rc * math.sin(a), z0 + dz * (t + (q + 1) / 4.0), cx, cy, not ccw)
            ze = z0 + dz * turns
            if internal:
                mv.arc_to(cx, cy, ze, cx + rc / 2.0, cy, not ccw)
            else:
                mv.feed_to(cx + rc + 2 * R, cy, ze)
            mv.retract()
        r_in, r_out = (hi["r"], dmaj / 2.0) if internal else (dmaj / 2.0 - depth, hi["r"])
        if r_out > r_in:
            ring = Point(cx, cy).buffer(r_out, G.ARC_SEGS).difference(Point(cx, cy).buffer(r_in, G.ARC_SEGS))
            rings.append(G.prism(ring, h["final"], h["start"]))
        n += 1
    cur = ctx.stock
    rings = [r for r in rings if r is not None]
    if rings:
        cur = G.cut(cur, rings)
    gone = sum(G.common_volume(r, ctx.shape) or 0.0 for r in rings)
    ctx.res["hm_sim"] = {"stock": cur, "levels": [], "removed_mm3": G.volume(ctx.stock) - G.volume(cur), "gouge_mm3": gone, "errors": []}
    ctx.res["cuts_part"] = True
    ctx.message("%d thread(s), pitch %.3f mm, %s-hand, %s, %d pass(es)" % (n, pitch, "right" if rh else "left", "internal" if internal else "external", passes))
    return mv


OPS = {"face": run_face, "pocket": run_pocket, "profile": run_profile, "drilling": run_drilling, "helix": run_helix,
       "slot": run_slot, "engrave": run_engrave, "deburr": run_deburr, "undercut": run_undercut, "thread": run_thread}
