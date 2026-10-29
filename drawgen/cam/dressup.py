# -*- coding: utf-8 -*-
"""Dressups: modifications of the moves of an operation (FreeCAD Path Dressup): Tag (holding tags), RampEntry,
LeadInOut, Dogbone and Boundary; the derived operations Copy and Array.

Dressup records ("dressups" of an operation):
  {"type": "tag", "count": n, "width" mm, "height" mm, "angle" deg (of the flanks; 90: vertical), "positions":
      [[x, y], ...] (empty: spread along the lowest closed loop)}
  {"type": "ramp", "angle" deg (from the horizontal), "method": "ramp1" (down at the angle along the following
      path, then on) | "ramp2" (along, then down at the angle: the zigzag is the same as ramp1 here) | "zigzag"
      (back and forth over the first segment) | "helix" (a helix about the plunge point), "feed": "vertical" (the
      ramp feed of the tool controller, else the plunge feed) | "horizontal" | mm/min, "use_start_depth": the ramp starts at most at the start depth}
  {"type": "axismap", "axis": "x" | "y", "radius" mm, "invert": false}  the axis written as A (rotary)
  {"type": "leadinout", "lead_in": true, "lead_out": true, "style": "arc" | "tangent" | "perpendicular",
      "length" mm (arc radius or line length), "extend" mm (along the path before the lead)}
  {"type": "dogbone", "style": "dogbone" | "tbone_h" | "tbone_v" | "tbone_long" | "tbone_short", "side": "left" |
      "right", "incision": "adaptive" | "fixed" | "custom", "length" mm (custom)}
  {"type": "boundary", "xmin", "ymin", "xmax", "ymax" (mm, part coordinates; null: the stock), "inside": true
      (the moves kept inside, else outside)}
Copy: {"type": "copy", "of": operation id}. Array: {"type": "array", "of": id, "kind": "linear" | "polar",
      "count": n, "dx", "dy" mm (linear), "cx", "cy" mm, "angle" deg (polar: total angle of count copies; 360
      spreads evenly), "centre_on_part": bool}
"""
import math

from . import geom as G
from . import tools as TB

_f = G._f


ORDER = {"dogbone": 0, "tag": 1, "leadinout": 2, "ramp": 3, "boundary": 4, "axismap": 5}


def apply_dressups(ctx, moves):
    """The dressups of the operation applied in the order dogbone, tag, lead in/out, ramp entry, boundary, axis map."""
    for d in sorted(ctx.op.get("dressups") or [], key=lambda x: ORDER.get(x.get("type"), 9)):
        t = d.get("type")
        fn = DRESSUPS.get(t)
        if fn is None:
            ctx.error("unknown dressup %s" % t)
            return moves
        try:
            moves = fn(ctx, d, moves)
        except Exception as e:  # noqa: BLE001
            ctx.error("%s dressup: %s" % (t, e))
            return moves
    return moves


# --------------------------------------------------------------------------- helpers

def _segments(moves):
    """Runs of cutting moves: [(start index, end index)] over the moves list (feed and arc moves between
    rapids or plunges)."""
    out = []
    i = 0
    n = len(moves)
    while i < n:
        if moves[i].get("k") in ("feed", "arc"):
            j = i
            while j + 1 < n and moves[j + 1].get("k") in ("feed", "arc"):
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def _prev_point(moves, i):
    for k in range(i - 1, -1, -1):
        if "p" in moves[k]:
            return moves[k]["p"]
    return None


def _flat_closed_loop(moves, a, b):
    """The run a..b as a closed loop at one Z: [(x, y)] or None."""
    p0 = _prev_point(moves, a)
    if p0 is None:
        return None
    pts = [tuple(p0)]
    for m in moves[a:b + 1]:
        if m["k"] == "arc":
            pts += [tuple(q) for q in G.arc_pts(pts[-1], tuple(m["p"]), m["c"], m.get("cw"))]
        else:
            pts.append(tuple(m["p"]))
    if any(abs(p[2] - pts[0][2]) > 1e-6 for p in pts):
        return None
    if math.dist(pts[0][:2], pts[-1][:2]) > 1e-6 or len(pts) < 4:
        return None
    return [p[:2] for p in pts[:-1]], pts[0][2]


# --------------------------------------------------------------------------- tag

def dress_tag(ctx, d, moves):
    """Holding tags on the lowest closed loops: the tool rises over a tag of the width (between the tool
    edges) and the height with flanks at the angle."""
    R = TB.radius(ctx.tool)
    n = max(0, int(_f(d.get("count"), 4)))
    w = max(0.0, _f(d.get("width"), 6.0)) + 2 * R
    h = max(0.0, _f(d.get("height"), 2.0))
    ang = min(90.0, max(5.0, _f(d.get("angle"), 45.0)))
    flank = h / math.tan(math.radians(ang)) if ang < 90 else 0.0
    positions = [(_f(p[0]), _f(p[1])) for p in (d.get("positions") or [])]
    if n == 0 and not positions or h <= 0:
        return moves
    runs = [(a, b, _flat_closed_loop(moves, a, b)) for a, b in _segments(moves)]
    runs = [(a, b, r) for a, b, r in runs if r is not None]
    if not runs:
        ctx.message("tag: no closed loop at one level")
        return moves
    zmin = min(r[1] for _, _, r in runs)
    out = []
    last = 0
    count = 0
    for a, b, (loop, z) in runs:
        if z > zmin + 1e-6:
            continue
        out += moves[last:a]
        feed = moves[a].get("f")
        L = loop + [loop[0]]
        total = sum(math.dist(p, q) for p, q in zip(L, L[1:]))
        if positions:
            cents = []
            for px, py in positions:
                s, best = 0.0, (1e30, 0.0)
                for p, q in zip(L, L[1:]):
                    seg = math.dist(p, q)
                    if seg > 1e-9:
                        t = max(0.0, min(1.0, ((px - p[0]) * (q[0] - p[0]) + (py - p[1]) * (q[1] - p[1])) / seg ** 2))
                        dd = math.hypot(p[0] + (q[0] - p[0]) * t - px, p[1] + (q[1] - p[1]) * t - py)
                        if dd < best[0]:
                            best = (dd, s + seg * t)
                    s += seg
                cents.append(best[1])
        else:
            cents = [(k + 0.5) * total / n for k in range(n)]
        tabs = sorted((c - w / 2 - flank, c - w / 2, c + w / 2, c + w / 2 + flank) for c in cents)
        tabs = [t for t in tabs if t[0] > 1e-9 and t[3] < total - 1e-9]
        count += len(tabs)
        stations = sorted({s for t in tabs for s in t})
        # the loop with vertices at the stations, each with its Z
        pts = []
        acc = 0.0
        st_i = 0
        for p, q in zip(L, L[1:]):
            seg = math.dist(p, q)
            pts.append((p[0], p[1], acc))
            while st_i < len(stations) and stations[st_i] <= acc + seg + 1e-12:
                t = (stations[st_i] - acc) / seg if seg > 1e-12 else 0.0
                if 1e-9 < t < 1 - 1e-9:
                    pts.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, stations[st_i]))
                st_i += 1
            acc += seg
        pts.append((L[-1][0], L[-1][1], total))

        def ztag(s):
            for s0, s1, s2, s3 in tabs:
                if s0 <= s <= s3:
                    if s <= s1:
                        return z + h * (s - s0) / (s1 - s0) if s1 > s0 else z + h
                    if s >= s2:
                        return z + h * (s3 - s) / (s3 - s2) if s3 > s2 else z + h
                    return z + h
            return z
        for x, y, s in pts[1:]:
            zz = ztag(s)
            out.append({"k": "feed", "p": [x, y, zz], "f": feed})
        last = b + 1
    out += moves[last:]
    ctx.message("tag: %d tag(s) %g x %g mm" % (count, w - 2 * R, h))
    return out


# --------------------------------------------------------------------------- ramp entry

def dress_ramp(ctx, d, moves):
    """Every plunge into material replaced by a ramp: along the following path down at the angle (ramp1 and
    ramp2), back and forth over the first segment (zigzag), or a helix about the plunge point."""
    ang = min(89.0, max(0.5, _f(d.get("angle"), 3.0)))
    method = d.get("method") or "ramp1"
    fv = d.get("feed") or "vertical"
    R = TB.radius(ctx.tool)
    use_start = d.get("use_start_depth", True)
    sz = ctx.h["start"] if ctx.h else None
    out = []
    i = 0
    n = len(moves)
    count = 0
    while i < n:
        m = moves[i]
        nxt = moves[i + 1] if i + 1 < n else None
        if m.get("k") == "plunge" and nxt is not None and nxt.get("k") in ("feed", "arc"):
            p0 = _prev_point(moves, i)
            z_from, z_to = p0[2], m["p"][2]
            if use_start and sz is not None and z_from > sz and z_to < sz:
                # a rapid down to the start depth; the ramp begins there
                out.append({"k": "rapid", "p": [p0[0], p0[1], sz]})
                z_from = sz
            drop = z_from - z_to
            if drop <= 1e-6:
                out.append(m)
                i += 1
                continue
            feed = (getattr(ctx, "rfeed", None) or _f(m.get("f"))) if fv == "vertical" else (_f(nxt.get("f")) if fv == "horizontal" else _f(fv, _f(m.get("f"))))
            ramp_len = drop / math.tan(math.radians(ang))
            # the path that follows the plunge at the level z_to
            j = i + 1
            path = [tuple(p0[:2])]
            while j < n and moves[j].get("k") in ("feed", "arc") and abs(moves[j]["p"][2] - z_to) < 1e-6:
                if moves[j]["k"] == "arc":
                    path += [q[:2] for q in G.arc_pts(path[-1] + (z_to,), tuple(moves[j]["p"]), moves[j]["c"], moves[j].get("cw"))]
                else:
                    path.append(tuple(moves[j]["p"][:2]))
                j += 1
            L = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
            if method == "helix":
                rh = 0.5 * R
                cx, cy = p0[0], p0[1]
                pitch = ramp_len and (2 * math.pi * rh) * math.tan(math.radians(ang))
                pitch = max(pitch, 0.05)
                out.append({"k": "rapid", "p": [cx + rh, cy, z_from]})
                zc = z_from
                while zc > z_to + 1e-9:
                    dz = min(pitch, zc - z_to)
                    for q in range(4):
                        a = (q + 1) * math.pi / 2
                        pt = [cx + rh * math.cos(a), cy + rh * math.sin(a), zc - dz * (q + 1) / 4]
                        out.append({"k": "arc", "p": pt, "c": [cx, cy], "cw": False, "f": feed})
                    zc -= dz
                for q in range(4):
                    a = (q + 1) * math.pi / 2
                    out.append({"k": "arc", "p": [cx + rh * math.cos(a), cy + rh * math.sin(a), z_to], "c": [cx, cy], "cw": False, "f": feed})
                out.append({"k": "feed", "p": [p0[0], p0[1], z_to], "f": feed})
                count += 1
                i += 1
                continue
            if L < 1e-6:
                out.append(m)
                i += 1
                continue
            if method == "zigzag" or ramp_len > L:
                # back and forth over the path until the level is reached
                seg = path
                z = z_from
                forward = True
                while z > z_to + 1e-9:
                    dz = min(drop, L * math.tan(math.radians(ang)), z - z_to)
                    pts = seg if forward else seg[::-1]
                    acc = 0.0
                    for a, b in zip(pts, pts[1:]):
                        acc += math.dist(a, b)
                        out.append({"k": "feed", "p": [b[0], b[1], z - dz * acc / L], "f": feed})
                    z -= dz
                    forward = not forward
                if not forward:
                    # back to the start of the path at the level
                    for b in seg[::-1][1:]:
                        out.append({"k": "feed", "p": [b[0], b[1], z_to], "f": feed})
                count += 1
                i += 1
                continue
            # ramp1: down along the path over ramp_len, the rest of the moves follow (the ramp length is cut
            # again at the level by the loop itself when it is closed; else the path is run back to its start)
            acc = 0.0
            for a, b in zip(path, path[1:]):
                seg = math.dist(a, b)
                if acc + seg >= ramp_len - 1e-9:
                    t = (ramp_len - acc) / seg if seg > 1e-12 else 1.0
                    end = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                    out.append({"k": "feed", "p": [end[0], end[1], z_to], "f": feed})
                    # back to the plunge point along the ramp at the level
                    back = path[:path.index(a) + 1][::-1]
                    for q in back:
                        out.append({"k": "feed", "p": [q[0], q[1], z_to], "f": feed})
                    break
                acc += seg
                out.append({"k": "feed", "p": [b[0], b[1], z_from - drop * acc / ramp_len], "f": feed})
            count += 1
            i += 1
            continue
        out.append(m)
        i += 1
    ctx.message("ramp entry: %d plunge(s) replaced, %g deg" % (count, ang))
    return out


# --------------------------------------------------------------------------- lead in / out

def dress_leadinout(ctx, d, moves):
    """A lead-in before and a lead-out after every closed loop at one Z: an arc (quarter circle tangent to the
    path), a tangent line or a perpendicular line of the length; the plunge moves to the lead start."""
    style = d.get("style") or "arc"
    L = max(0.1, _f(d.get("length"), TB.radius(ctx.tool)))
    ext = max(0.0, _f(d.get("extend"), 0.0))
    lead_in = d.get("lead_in", True)
    lead_out = d.get("lead_out", True)
    runs = [(a, b, _flat_closed_loop(moves, a, b)) for a, b in _segments(moves)]
    out = []
    last = 0
    count = 0
    for a, b, r in runs:
        if r is None:
            continue
        loop, z = r
        feed = moves[a].get("f")
        p0, p1 = loop[0], loop[1]
        t = (p1[0] - p0[0], p1[1] - p0[1])
        tl = math.hypot(*t) or 1.0
        t = (t[0] / tl, t[1] / tl)
        # the side away from the material: the loop's interior is on the left of a CCW loop
        area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(loop, loop[1:] + loop[:1]))
        nrm = (-t[1], t[0]) if area < 0 else (t[1], -t[0])        # outward normal at the start
        # the moves before the run up to the plunge: the plunge point moved to the lead start
        pre = moves[last:a]
        if style == "arc":
            cen = (p0[0] + nrm[0] * L, p0[1] + nrm[1] * L)
            start = (cen[0] - t[0] * L, cen[1] - t[1] * L)
            cw = area < 0
        elif style == "perpendicular":
            start = (p0[0] + nrm[0] * L, p0[1] + nrm[1] * L)
        else:
            start = (p0[0] - t[0] * L, p0[1] - t[1] * L)
        if lead_in:
            for m in pre:
                if "p" in m and math.dist(m["p"][:2], p0) < 1e-6:
                    m = dict(m, p=[start[0], start[1], m["p"][2]])
                out.append(m)
            if style == "arc":
                out.append({"k": "arc", "p": [p0[0], p0[1], z], "c": [cen[0], cen[1]], "cw": not cw, "f": feed})
            else:
                out.append({"k": "feed", "p": [p0[0], p0[1], z], "f": feed})
        else:
            out += pre
        out += moves[a:b + 1]
        if ext > 0:
            # along the path beyond the start
            acc, k = 0.0, 0
            Lp = loop + [loop[0]]
            while acc < ext and k + 1 < len(Lp):
                seg = math.dist(Lp[k], Lp[k + 1])
                if acc + seg >= ext:
                    tt = (ext - acc) / seg if seg > 1e-12 else 1.0
                    out.append({"k": "feed", "p": [Lp[k][0] + (Lp[k + 1][0] - Lp[k][0]) * tt, Lp[k][1] + (Lp[k + 1][1] - Lp[k][1]) * tt, z], "f": feed})
                    break
                acc += seg
                k += 1
                out.append({"k": "feed", "p": [Lp[k][0], Lp[k][1], z], "f": feed})
        if lead_out:
            q = tuple(out[-1]["p"][:2])
            if style == "arc":
                cen2 = (q[0] + nrm[0] * L, q[1] + nrm[1] * L)
                end = (cen2[0] + t[0] * L, cen2[1] + t[1] * L)
                out.append({"k": "arc", "p": [end[0], end[1], z], "c": [cen2[0], cen2[1]], "cw": not cw, "f": feed})
            elif style == "perpendicular":
                out.append({"k": "feed", "p": [q[0] + nrm[0] * L, q[1] + nrm[1] * L, z], "f": feed})
            else:
                out.append({"k": "feed", "p": [q[0] + t[0] * L, q[1] + t[1] * L, z], "f": feed})
        last = b + 1
        count += 1
    out += moves[last:]
    ctx.message("lead in/out: %d loop(s), %s %g mm" % (count, style, L))
    return out


# --------------------------------------------------------------------------- dogbone

def dress_dogbone(ctx, d, moves):
    """Overcuts at the inside corners of the loops (the corners where the material is on the inside of the turn):
    dogbone (along the bisector) or T-bone (along one of the edges), of the length that clears the corner."""
    R = TB.radius(ctx.tool)
    style = d.get("style") or "dogbone"
    side = d.get("side") or "left"
    inc = d.get("incision") or "adaptive"
    custom = max(0.0, _f(d.get("length"), R))
    out = []
    last = 0
    count = 0
    for a, b in _segments(moves):
        r = _flat_closed_loop(moves, a, b)
        if r is None:
            continue
        loop, z = r
        feed = moves[a].get("f")
        # material on the left of a CCW inside path: a left turn is an inside corner for side left
        out += moves[last:a]
        n = len(loop)
        pts = []
        for i in range(n):
            p = loop[i]
            q = loop[(i + 1) % n]
            o = loop[i - 1]
            v1 = (p[0] - o[0], p[1] - o[1])
            v2 = (q[0] - p[0], q[1] - p[1])
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            if l1 < 1e-9 or l2 < 1e-9:
                pts.append((p, None))
                continue
            u1, u2 = (v1[0] / l1, v1[1] / l1), (v2[0] / l2, v2[1] / l2)
            cross = u1[0] * u2[1] - u1[1] * u2[0]
            turn_left = cross > 1e-6
            inside = (turn_left and side == "left") or (not turn_left and side == "right")
            if not inside or abs(cross) < 0.2:
                pts.append((p, None))
                continue
            # the corner: the bisector into the material, the overcut length
            bis = (-u1[0] + u2[0], -u1[1] + u2[1])
            bl = math.hypot(*bis) or 1.0
            bis = (bis[0] / bl, bis[1] / bl)
            half = math.acos(max(-1.0, min(1.0, -(u1[0] * u2[0] + u1[1] * u2[1])))) / 2.0
            if inc == "custom":
                length = custom
            elif inc == "fixed":
                length = R
            else:
                length = R / math.sin(half) - R if half > 1e-6 else R
            if style == "dogbone":
                dirv = bis
            elif style in ("tbone_h", "tbone_v"):
                dirv = (1.0, 0.0) if style == "tbone_h" else (0.0, 1.0)
                if dirv[0] * bis[0] + dirv[1] * bis[1] < 0:
                    dirv = (-dirv[0], -dirv[1])
                length = length * max(1e-6, abs(dirv[0] * bis[0] + dirv[1] * bis[1])) if inc == "adaptive" else length
            else:
                along_prev = (-u1[0], -u1[1])
                along_next = (u2[0], u2[1])
                dirv = along_prev if (style == "tbone_long") == (l1 >= l2) else along_next
            pts.append((p, (p[0] + dirv[0] * length, p[1] + dirv[1] * length)))
            count += 1
        for p, bone in pts[1:] + pts[:1]:
            out.append({"k": "feed", "p": [p[0], p[1], z], "f": feed})
            if bone is not None:
                out.append({"k": "feed", "p": [bone[0], bone[1], z], "f": feed})
                out.append({"k": "feed", "p": [p[0], p[1], z], "f": feed})
        last = b + 1
    out += moves[last:]
    ctx.message("dogbone: %d corner(s), %s" % (count, style))
    return out


# --------------------------------------------------------------------------- boundary

def dress_boundary(ctx, d, moves):
    """The cutting moves clipped to a rectangle (the stock by default): the parts outside are left out, with a
    retract and a plunge where the path leaves and enters the rectangle."""
    from shapely.geometry import box as sbox, LineString
    sb = ctx.stock_bb
    x0, y0 = _f(d.get("xmin"), sb[0]), _f(d.get("ymin"), sb[1])
    x1, y1 = _f(d.get("xmax"), sb[3]), _f(d.get("ymax"), sb[4])
    inside = d.get("inside", True)
    rect = sbox(x0, y0, x1, y1)
    out = []
    prev = None
    cz = ctx.h["clearance"] if ctx.h else sb[5] + 5
    cut_n = 0
    for m in moves:
        if "p" not in m or m["k"] not in ("feed", "arc", "plunge") or prev is None:
            out.append(m)
            if "p" in m:
                prev = m["p"]
            continue
        p = m["p"]
        if m["k"] == "arc":
            pts = [tuple(prev)] + G.arc_pts(tuple(prev), tuple(p), m["c"], m.get("cw"))
        else:
            pts = [tuple(prev), tuple(p)]
        for a, b in zip(pts, pts[1:]):
            seg = LineString([a[:2], b[:2]])
            keep = seg.intersection(rect) if inside else seg.difference(rect)
            parts = G.lines(keep)
            if not parts:
                cut_n += 1
                continue
            for l in parts:
                cs = list(l.coords)
                s0 = cs[0]
                if out and "p" in out[-1] and math.dist(out[-1]["p"][:2], s0) > 1e-6:
                    # the path enters the kept region: up, over and down
                    za = a[2] + (b[2] - a[2]) * (math.dist(a[:2], s0) / max(math.dist(a[:2], b[:2]), 1e-9))
                    out.append({"k": "rapid", "p": [out[-1]["p"][0], out[-1]["p"][1], cz]})
                    out.append({"k": "rapid", "p": [s0[0], s0[1], cz]})
                    out.append({"k": "plunge", "p": [s0[0], s0[1], za], "f": ctx.plunge})
                for q in cs[1:]:
                    t = math.dist(a[:2], q) / max(math.dist(a[:2], b[:2]), 1e-9)
                    out.append({"k": "feed", "p": [q[0], q[1], a[2] + (b[2] - a[2]) * t], "f": m.get("f")})
        prev = p
    ctx.message("boundary: moves outside X %g..%g Y %g..%g left out (%d segment(s))" % (x0, x1, y0, y1, cut_n))
    return out


def dress_axismap(ctx, d, moves):
    """Axis map: a linear axis (X or Y) written as the rotary axis A for a part on a rotary axis: A = the coordinate /
    (2 pi radius) x 360 deg (minus: Invert). The arcs become lines of at most 1 mm (an arc in a mapped plane has no
    G2/G3 form). The moves keep their coordinates for the view and the simulation; the post-processor writes A in
    place of the mapped axis ("a" deg and "amap": "x" | "y" on every move)."""
    ax = (d.get("axis") or "y").lower()
    if ax not in ("x", "y"):
        raise ValueError("the mapped axis is X or Y")
    r = _f(d.get("radius"), 0.0)
    if r <= 0:
        raise ValueError("the radius of the axis map must be above 0")
    sgn = -1.0 if d.get("invert") else 1.0
    k = 0 if ax == "x" else 1
    out = []
    prev = None
    for m in moves:
        if "p" not in m:
            out.append(m)
            continue
        if m.get("k") == "arc" and prev is not None:
            pts = G.arc_pts(prev, tuple(m["p"]), m["c"], m.get("cw"))
            dense = []
            q = prev
            for p in pts:
                L = math.dist(q, p)
                nn = max(1, int(math.ceil(L / 1.0)))
                dense += [tuple(q[i] + (p[i] - q[i]) * j / nn for i in range(3)) for j in range(1, nn + 1)]
                q = p
            for p in dense:
                out.append({"k": "feed", "p": [p[0], p[1], p[2]], "f": m.get("f")})
        else:
            out.append(dict(m))
        prev = tuple(m["p"])
    for m in out:
        if "p" in m:
            m["a"] = round(sgn * m["p"][k] / (2.0 * math.pi * r) * 360.0, 4)
            m["amap"] = ax
    ctx.message("axis map: %s written as A at radius %.3f mm" % (ax.upper(), r))
    return out


DRESSUPS = {"tag": dress_tag, "ramp": dress_ramp, "leadinout": dress_leadinout, "dogbone": dress_dogbone, "boundary": dress_boundary,
            "axismap": dress_axismap}


# --------------------------------------------------------------------------- copy and array

def derived_moves(op, src_moves):
    """Moves of a Copy (the same moves) or an Array (the moves repeated with the offsets or rotations)."""
    import copy as _copy
    if op.get("type") == "copy":
        return _copy.deepcopy(src_moves)
    n = max(1, int(_f(op.get("count"), 2)))
    kind = op.get("kind") or "linear"
    out = []
    for k in range(n):
        if kind == "polar":
            total = _f(op.get("angle"), 360.0)
            ang = math.radians(total * k / n if abs(total - 360.0) < 1e-9 else total * k / max(1, n - 1))
            cx, cy = _f(op.get("cx")), _f(op.get("cy"))
            ca, sa = math.cos(ang), math.sin(ang)

            def tr(x, y):
                return (cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca)
        else:
            dx, dy = _f(op.get("dx")) * k, _f(op.get("dy")) * k

            def tr(x, y, dx=dx, dy=dy):
                return (x + dx, y + dy)
        for m in src_moves:
            m2 = _copy.deepcopy(m)
            if "p" in m2:
                x, y = tr(m2["p"][0], m2["p"][1])
                m2["p"] = [x, y, m2["p"][2]]
            if "c" in m2:
                x, y = tr(m2["c"][0], m2["c"][1])
                m2["c"] = [x, y]
            out.append(m2)
    return out
