# -*- coding: utf-8 -*-
"""Sheet composition: views, layout, sheet and scale selection, title block values."""
import datetime
import math
import re

from . import project as pj
from . import titleblock as tbk
from .units import units_of

SHEET_ORDER = ["A4", "A3", "A2", "A1", "A0"]
# section plane normal axis -> (direction toward the viewer, paper x direction, base view), viewing in +axis;
# flipped: viewing in -axis
SECTIONS = {
    "X": (((-1, 0, 0), (0, -1, 0)), ((1, 0, 0), (0, 1, 0)), "front"),
    "Y": (((0, -1, 0), (1, 0, 0)), ((0, 1, 0), (-1, 0, 0)), "top"),
    "Z": (((0, 0, -1), (1, 0, 0)), ((0, 0, 1), (1, 0, 0)), "front"),
}
AXIS_VEC = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}


def section_setup(vcfg):
    """(axis, offset, flip, direction, xdir, base view) from the view settings."""
    axis = str(vcfg.get("section_axis", "X")).upper()
    if axis not in SECTIONS:
        axis = "X"
    flip = bool(vcfg.get("section_flip", False))
    d, x = SECTIONS[axis][1] if flip else SECTIONS[axis][0]
    return axis, float(vcfg.get("section_offset_mm", 0.0) or 0.0), flip, d, x, SECTIONS[axis][2]
CUTLINE_EXT = 5.0                        # cutting plane line extension beyond the front view (paper mm)
LABEL_SPACE = 12.0                       # space above/below the front view for the cutting plane letters
CAPTION_SPACE = 10.0                     # space below the section view for its caption


def scale_text(s):
    if s >= 1:
        return "%g:1" % round(s, 6)
    return "1:%g" % round(1.0 / s, 6)


def parse_scale(text):
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).strip().lower()
    if t in ("", "auto"):
        return None
    if ":" in t:
        a, b = t.split(":")
        return float(a) / float(b)
    return float(t)


# --------------------------------------------------------------------------- views

def _on_segment(px, py, l, tol):
    x1, y1, x2, y2 = l[1:5]
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return False
    t = ((px - x1) * dx + (py - y1) * dy) / L2
    if t < -1e-9 or t > 1 + 1e-9:
        return False
    cx, cy = x1 + t * dx, y1 + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2 <= tol * tol


def _drop_covered(hidden, visible, tol):
    """Remove hidden lines lying on visible lines."""
    vis_lines = [v for v in visible if v[0] == "L"]
    out = []
    for h in hidden:
        if h[0] == "L":
            if any(_on_segment(h[1], h[2], v, tol) and _on_segment(h[3], h[4], v, tol) for v in vis_lines):
                continue
        out.append(h)
    return out


class View(object):
    def __init__(self, name, visible, hidden=(), section_segments=(), factor=1.0, section_groups=None):
        self.name = name
        self.section_groups = [list(g) for g in (section_groups or [])]
        self.visible = visible
        if hidden:
            bb = pj.prims_bbox(visible)
            tol = max(bb[2] - bb[0], bb[3] - bb[1], 1.0) * 1e-5
            hidden = _drop_covered(list(hidden), visible, tol)
        self.hidden = list(hidden)
        self.section_segments = list(section_segments)
        self.factor = factor           # view scale relative to the drawing scale
        bb = pj.prims_bbox(list(visible) + list(hidden))
        self.bbox = bb
        self.w = (bb[2] - bb[0]) * factor
        self.h = (bb[3] - bb[1]) * factor


def _pool():
    """Process pool for projecting views in parallel (None if unavailable)."""
    from . import pool
    return pool.get()          # shared with the assembly builds (pool.py)


def compute_views(shape, cfg, cache=None, key=None, workdir=None):
    """Project all views of the configuration. cache: dict for reuse between preview and export."""
    import os
    import tempfile
    v = cfg["views"]
    hidden = bool(v.get("hidden_lines", False))
    smooth = bool(v.get("smooth_lines", False))
    axis, offset, flip, sd, sx, base = section_setup(v)
    sec_on = bool(v.get("section", True))
    ck = (key, hidden, smooth, v.get("orthographic", True), sec_on, v.get("isometric", True),
          (axis, offset, flip) if sec_on else None)
    if cache is not None and key is not None and ck in cache:
        return cache[ck]
    x0, y0, z0, x1, y1, z1 = pj.bounding_box(shape)
    centre = ((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0)
    av = AXIS_VEC[axis]
    origin = tuple(centre[i] + av[i] * offset for i in range(3))
    jobs = {}
    names = ["front"] + (["right", "top"] if v.get("orthographic", True) else [])
    if sec_on and base not in names:
        names.append(base)
    for n in names:
        jobs[n] = ("hlr", (pj.VIEWS[n][0], pj.VIEWS[n][1], hidden, smooth))
    if sec_on:
        jobs["section"] = ("section", (origin, sd, sx, False))
    if v.get("isometric", True):
        jobs["iso"] = ("hlr", (pj.VIEWS["iso"][0], pj.VIEWS["iso"][1], False, smooth))

    results = {}
    pool = _pool()
    if pool is not None:
        try:
            fd, path = tempfile.mkstemp(suffix=".brep", dir=workdir)
            os.close(fd)
            pj.write_brep(shape, path)
            futs = {n: pool.submit(pj.run_job, (path, kind, args)) for n, (kind, args) in jobs.items()}
            results = {n: f.result() for n, f in futs.items()}
            os.remove(path)
        except Exception:
            results = {}
    for n, (kind, args) in jobs.items():
        if n in results:
            continue
        if kind == "hlr":
            results[n] = pj.hlr(pj.fused(shape), args[0], args[1], hidden=args[2], smooth=args[3])
        else:
            results[n] = pj.section_view(shape, *args[:3], hidden=args[3])

    factor = float(v.get("isometric_scale_factor", 1.0))
    views = {}
    for n, r in results.items():
        views[n] = View(n, r["visible"], r["hidden"], r.get("section_segments", ()),
                        factor=factor if n == "iso" else 1.0, section_groups=r.get("section_groups"))
    result = (views, origin)
    if cache is not None and key is not None:
        cache[ck] = result
    return result


# --------------------------------------------------------------------------- layout

def candidate_layouts(views):
    """Grids of (col, row) cells. Column widths and row heights in model mm.

    A:  right | front | section        B:  right | front | section | iso
              | top   | iso                      | top   |         |
    """
    def wh(n):
        return (views[n].w, views[n].h) if n in views else (0.0, 0.0)

    fr, ri, to, se, iso = wh("front"), wh("right"), wh("top"), wh("section"), wh("iso")
    c1 = max(fr[0], to[0])
    lays = [{
        "cols": [ri[0], c1, max(se[0], iso[0])],
        "rows": [max(fr[1], ri[1], se[1]), max(to[1], iso[1])],
        "cells": {"right": (0, 0), "front": (1, 0), "top": (1, 1), "section": (2, 0), "iso": (2, 1)},
    }]
    if "iso" in views:
        lays.append({
            "cols": [ri[0], c1, se[0], iso[0]],
            "rows": [max(fr[1], ri[1], se[1], iso[1]), to[1]],
            "cells": {"right": (0, 0), "front": (1, 0), "top": (1, 1), "section": (2, 0), "iso": (3, 0)},
        })
    return lays


def _bands(views):
    """Paper height (mm) above row 0 and between row 0 and row 1 for cutting plane letters and caption."""
    if "section" in views:
        return LABEL_SPACE, max(LABEL_SPACE, CAPTION_SPACE)
    return 0.0, 0.0


def _extra(views, cfg):
    """Fixed paper allowances (mm): (width, height)."""
    b0, b1 = _bands(views)
    return 0.0, b0 + b1


def _fit(cfg, sheet, lay, views):
    g = cfg["views"]["view_gap_mm"]
    x0, y0, x1, y1 = tbk.drawing_area(cfg, sheet)
    ncol = sum(1 for c in lay["cols"] if c > 0)
    nrow = sum(1 for r in lay["rows"] if r > 0)
    ew, eh = _extra(views, cfg)
    aw = (x1 - x0) - g * max(ncol - 1, 0) - ew
    ah = (y1 - y0) - g * max(nrow - 1, 0) - eh
    raw = min(aw / max(sum(lay["cols"]), 1e-9), ah / max(sum(lay["rows"]), 1e-9))
    for s in sorted(cfg["standard_scales"], reverse=True):
        if s <= raw + 1e-12:
            return s, raw
    return min(cfg["standard_scales"]), raw


def choose(cfg, views, sheet, scale):
    """Returns (sheet, scale, layout)."""
    def best(sh):
        out = None
        for lay in candidate_layouts(views):
            s, raw = _fit(cfg, sh, lay, views)
            if out is None or raw > out[2] * 1.0001:
                out = (lay, s, raw)
        return out

    if str(sheet).lower() == "auto":
        last = None
        for sh in SHEET_ORDER:
            lay, s, raw = best(sh)
            if scale is not None:
                last = (sh, scale, lay)
                if raw >= scale:
                    return last
                continue
            last = (sh, s, lay)
            if s >= cfg.get("auto_sheet_min_scale", 1.0):
                return last
        return last
    lay, s, raw = best(sheet)
    return sheet, (s if scale is None else scale), lay


# --------------------------------------------------------------------------- title block values

def field_values(cfg, name, volume, scale, overrides=None):
    vals = dict(cfg["fields"])
    if overrides:
        vals.update({k: v for k, v in overrides.items() if v not in (None, "")})
    if not vals.get("Title"):
        vals["Title"] = name
    if not vals.get("DrawingNumber"):
        vals["DrawingNumber"] = re.sub(r"\s+", "_", vals["Title"]).upper()
    if not vals.get("Date"):
        vals["Date"] = datetime.date.today().isoformat()
    if not vals.get("Mass"):
        rho = float(cfg.get("density_kg_per_m3", 0) or 0)
        if rho > 0:
            vals["Mass"] = "%.3f kg" % (volume * 1e-9 * rho)
    vals["Scale"] = scale_text(scale)
    if vals.get("Units", "").strip() == "mm" and units_of(cfg) == "inch":
        vals["Units"] = "in"
    return vals


# --------------------------------------------------------------------------- composition

def _place(prims, view, cx, cy, s, layer):
    """Map view primitives (model mm) to sheet primitives centred at (cx, cy)."""
    f = s * view.factor
    bx = (view.bbox[0] + view.bbox[2]) / 2.0
    by = (view.bbox[1] + view.bbox[3]) / 2.0

    def m(x, y):
        return cx + f * (x - bx), cy + f * (y - by)

    out = []
    for p in prims:
        k = p[0]
        if k == "L":
            a, b = m(p[1], p[2]), m(p[3], p[4])
            out.append(("line", a[0], a[1], b[0], b[1], layer))
        elif k == "C":
            c = m(p[1], p[2])
            out.append(("circle", c[0], c[1], p[3] * f, layer))
        elif k == "A":
            c = m(p[1], p[2])
            out.append(("arc", c[0], c[1], p[3] * f, p[4], p[5], layer))
        elif k == "P":
            out.append(("poly", [m(x, y) for x, y in p[1]], layer, False))
    return out, m


def _arrow(x, y, dx, dy, length=7.0, head=3.0, width=1.0):
    """Arrow from (x, y) in direction (dx, dy). Returns line + filled head."""
    ex, ey = x + dx * length, y + dy * length
    px, py = -dy, dx
    bx, by = ex - dx * head, ey - dy * head
    return [("line", x, y, bx, by, "visible"),
            ("solid", [(ex, ey), (bx + px * width, by + py * width), (bx - px * width, by - py * width)], "visible")]


def thread_prims(holes, views, centres, s, hidden_lines):
    """Cosmetic threads (ISO 6410-1) for threaded holes: a thin 3/4 circle at the major diameter in views along
    the hole axis; thin lines at the major diameter in views across the axis when hidden lines are drawn."""
    prims = []
    for h in holes:
        if h.get("kind") == "external":
            prims += _external_thread_prims(h, views, centres, s, hidden_lines)
            continue
        major = float(h.get("major") or 0)
        if major <= float(h.get("dia") or 0):
            continue
        a = h["d"]
        depth = h["depth"] if h.get("depth") else h.get("reach") or 0
        for n, view in views.items():
            if n in ("section", "iso"):
                continue
            cx, cy = centres[n]
            d, xd = pj.VIEWS[n]
            dot = a[0] * d[0] + a[1] * d[1] + a[2] * d[2]
            _, m = _place([], view, cx, cy, s, "dim")
            f = s * view.factor
            if abs(dot) > 0.99:
                if dot > 0 and not h.get("through") and not hidden_lines:
                    continue        # blind hole opening on the far side
                px, py = m(*pj.project_point(h["p"], d, xd))
                prims.append(("arc", px, py, f * major / 2.0, 90.0, 360.0, "dim" if dot < 0 or h.get("through") else "hidden"))
            elif abs(dot) < 0.01 and hidden_lines:
                p0 = h["p"]
                p1 = [p0[i] + a[i] * depth for i in range(3)]
                side = pj.project_point(a, d, xd)
                L = math.hypot(side[0], side[1]) or 1.0
                perp = (-side[1] / L, side[0] / L)
                u0, u1 = pj.project_point(p0, d, xd), pj.project_point(p1, d, xd)
                r = major / 2.0
                for sg in (-1.0, 1.0):
                    q0 = m(u0[0] + sg * perp[0] * r, u0[1] + sg * perp[1] * r)
                    q1 = m(u1[0] + sg * perp[0] * r, u1[1] + sg * perp[1] * r)
                    prims.append(("line", q0[0], q0[1], q1[0], q1[1], "hidden"))
    return prims


def _external_thread_prims(h, views, centres, s, hidden_lines):
    """Cosmetic external thread (ISO 6410-1): a thin 3/4 circle at the minor diameter in the view onto the thread
    end; thin lines at the minor diameter along the thread length and a thick line across at the thread end in
    the views across the axis."""
    prims = []
    a = h["d"]
    minor = float(h.get("minor") or 0)
    major = float(h.get("dia") or h.get("major") or 0)
    length = float(h.get("depth") or 0)
    if minor <= 0 or length <= 0:
        return prims
    for n, view in views.items():
        if n in ("section", "iso"):
            continue
        cx, cy = centres[n]
        d, xd = pj.VIEWS[n]
        dot = a[0] * d[0] + a[1] * d[1] + a[2] * d[2]
        _, m = _place([], view, cx, cy, s, "dim")
        f = s * view.factor
        if abs(dot) > 0.99:
            if dot > 0 and not hidden_lines:
                continue        # thread end on the far side
            px, py = m(*pj.project_point(h["p"], d, xd))
            prims.append(("arc", px, py, f * minor / 2.0, 90.0, 360.0, "dim" if dot < 0 else "hidden"))
        elif abs(dot) < 0.01:
            p0 = h["p"]
            p1 = [p0[i] + a[i] * length for i in range(3)]
            side = pj.project_point(a, d, xd)
            L = math.hypot(side[0], side[1]) or 1.0
            perp = (-side[1] / L, side[0] / L)
            u0, u1 = pj.project_point(p0, d, xd), pj.project_point(p1, d, xd)
            r = minor / 2.0
            for sg in (-1.0, 1.0):
                q0 = m(u0[0] + sg * perp[0] * r, u0[1] + sg * perp[1] * r)
                q1 = m(u1[0] + sg * perp[0] * r, u1[1] + sg * perp[1] * r)
                prims.append(("line", q0[0], q0[1], q1[0], q1[1], "dim"))
            R = major / 2.0
            e0 = m(u1[0] - perp[0] * R, u1[1] - perp[1] * R)
            e1 = m(u1[0] + perp[0] * R, u1[1] + perp[1] * R)
            prims.append(("line", e0[0], e0[1], e1[0], e1[1], "visible"))
    return prims


def _clip_segment(a, b, c, R):
    """Part of the segment a-b inside the circle (c, R), or None."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - c[0], a[1] - c[1]
    A = dx * dx + dy * dy
    if A < 1e-18:
        return (a, b) if fx * fx + fy * fy <= R * R else None
    B = 2 * (fx * dx + fy * dy)
    C = fx * fx + fy * fy - R * R
    disc = B * B - 4 * A * C
    if disc < 0:
        return None
    sq = math.sqrt(disc)
    t0, t1 = max(0.0, (-B - sq) / (2 * A)), min(1.0, (-B + sq) / (2 * A))
    if t1 <= t0:
        return None
    return ((a[0] + dx * t0, a[1] + dy * t0), (a[0] + dx * t1, a[1] + dy * t1))


def _clip_chain(pts, c, R, layer, out):
    """Clips a polyline to the circle; the pieces inside are appended to out as polylines."""
    cur = []
    for i in range(len(pts) - 1):
        seg = _clip_segment(pts[i], pts[i + 1], c, R)
        if seg is None:
            if len(cur) > 1:
                out.append(("poly", cur, layer, False))
            cur = []
            continue
        a, b = seg
        if cur and math.hypot(cur[-1][0] - a[0], cur[-1][1] - a[1]) < 1e-6:
            cur.append(b)
        else:
            if len(cur) > 1:
                out.append(("poly", cur, layer, False))
            cur = [a, b]
    if len(cur) > 1:
        out.append(("poly", cur, layer, False))


def detail_prims(prims, C, k, pos, R):
    """Sheet primitives of a parent view magnified k times about the circle centre C and clipped to the circle of
    radius R at pos (sheet mm): the content of a detail view."""
    tr = lambda x, y: (pos[0] + k * (x - C[0]), pos[1] + k * (y - C[1]))
    out = []
    for p in prims:
        kind = p[0]
        if kind == "line":
            seg = _clip_segment(tr(p[1], p[2]), tr(p[3], p[4]), pos, R)
            if seg:
                out.append(("line", seg[0][0], seg[0][1], seg[1][0], seg[1][1], p[5]))
        elif kind in ("circle", "arc"):
            cx, cy = tr(p[1], p[2])
            r = p[3] * k
            if kind == "circle":
                a0, span, layer = 0.0, 360.0, p[4]
                if math.hypot(cx - pos[0], cy - pos[1]) + r <= R:
                    out.append(("circle", cx, cy, r, layer))
                    continue
            else:
                a0, layer = p[4], p[6]
                span = (p[5] - p[4]) % 360.0 or 360.0
            n = max(16, int(span / 360.0 * max(24, 2 * math.pi * r / 0.6)))
            pts = [(cx + r * math.cos(math.radians(a0 + span * i / n)), cy + r * math.sin(math.radians(a0 + span * i / n))) for i in range(n + 1)]
            _clip_chain(pts, pos, R, layer, out)
        elif kind == "poly":
            pts = [tr(x, y) for x, y in p[1]]
            if p[3] and pts:
                pts = pts + [pts[0]]
            _clip_chain(pts, pos, R, p[2], out)
        elif kind == "solid":
            pts = [tr(x, y) for x, y in p[1]]
            if all(math.hypot(x - pos[0], y - pos[1]) <= R for x, y in pts):
                out.append(("solid", pts, p[2]))
    return out


def compose(name, shape, volume, cfg, sheet=None, scale=None, fields=None, cache=None, key=None,
            base_dir="", annotations=None, view_offsets=None, hidden_views=None, parts_list=None, trails=None,
            holes=None, details=None, sketches=None, skip_sketch=None):
    """Build one drawing. Returns dict: name, sheet, size, scale, values, prims.
    hidden_views: view names left out of the drawing (front, top, right, section, iso).
    sketches: {target: {"doc", "anns"}} sketches made on the drawing; target "sheet" (paper mm) or a view name
    (view coordinates). skip_sketch: target left out (the sketch being edited)."""
    sheet = sheet or cfg.get("sheet", "A3")
    if scale is None:
        scale = parse_scale(cfg.get("scale", "auto"))
    views, origin = compute_views(shape, cfg, cache, key)
    pl_h = tbk.parts_list_height(parts_list or [])
    if pl_h:
        cfg = dict(cfg)
        cfg["title_block"] = dict(cfg["title_block"])
        cfg["title_block"]["height_mm"] = cfg["title_block"]["height_mm"] + pl_h      # layout area above the list
    all_views = views
    hidden_set = set(hidden_views or [])
    if hidden_set:
        views = {n: v for n, v in views.items() if n not in hidden_set}
        if not views:
            views = {"front": all_views["front"]} if "front" in all_views else dict(all_views)
    sheet, s, lay = choose(cfg, views, sheet, scale)
    vcfg = cfg["views"]
    g = vcfg["view_gap_mm"]
    first_angle = True
    vals = field_values(cfg, name, volume, s, fields)

    W, H = tbk.sheet_size(cfg, sheet)
    if pl_h:
        tb_cfg = dict(cfg)
        tb_cfg["title_block"] = dict(cfg["title_block"])
        tb_cfg["title_block"]["height_mm"] = cfg["title_block"]["height_mm"] - pl_h
        prims = tbk.sheet_primitives(tb_cfg, sheet, vals, first_angle, base_dir)
        prims += tbk.parts_list_primitives(tb_cfg, sheet, parts_list)
    else:
        prims = tbk.sheet_primitives(cfg, sheet, vals, first_angle, base_dir)
    template_prims = list(prims)

    # grid placement, centred in the drawing area
    ax0, ay0, ax1, ay1 = tbk.drawing_area(cfg, sheet)
    cols, rows = lay["cols"], lay["rows"]

    def span(sizes):
        n = sum(1 for c in sizes if c > 0)
        return s * sum(sizes) + g * max(n - 1, 0)

    ew, eh = _extra(views, cfg)
    tw, th = span(cols) + ew, span(rows) + eh
    left = ax0 + max(((ax1 - ax0) - tw) / 2.0, 0.0)
    top = ay1 - max(((ay1 - ay0) - th) / 2.0, 0.0)

    def start(sizes, i):
        pos = 0.0
        for k in range(i):
            if sizes[k] > 0:
                pos += s * sizes[k] + g
        return pos

    band0, band1 = _bands(views)
    row_top = [top - band0]
    row_top.append(row_top[0] - s * rows[0] - band1 - (g if rows[0] > 0 else 0.0))
    row_cy = [row_top[i] - s * rows[i] / 2.0 for i in range(2)]

    def col_cx(c):
        return left + start(cols, c) + s * cols[c] / 2.0

    centres = {}
    for n, view in views.items():
        c, r = lay["cells"][n]
        if n == "section":
            centres[n] = (left + start(cols, c) + s * view.w / 2.0, row_cy[0])
        else:
            centres[n] = (col_cx(c), row_cy[r])

    # user view offsets (sheet mm). Front moves Top and Right with it; Top moves only
    # vertically and Right only horizontally to keep first-angle projection alignment.
    off = {k: (float(v[0]), float(v[1])) for k, v in (view_offsets or {}).items()
           if isinstance(v, (list, tuple)) and len(v) == 2}
    fdx, fdy = off.get("front", (0.0, 0.0))
    for n in list(centres):
        cx, cy = centres[n]
        if n in ("front", "top", "right"):
            cx, cy = cx + fdx, cy + fdy
            if n == "top":
                cy += off.get("top", (0.0, 0.0))[1]
            if n == "right":
                cx += off.get("right", (0.0, 0.0))[0]
        elif n in off:
            cx, cy = cx + off[n][0], cy + off[n][1]
        centres[n] = (cx, cy)

    view_prims = {}
    for n, view in views.items():
        cx, cy = centres[n]
        p, m = _place(view.visible, view, cx, cy, s, "visible")
        view_prims[n] = list(p)
        prims += p
        if view.hidden:
            p, _ = _place(view.hidden, view, cx, cy, s, "hidden")
            view_prims[n] += p
            prims += p
        if view.section_segments:
            spacing = float(vcfg.get("hatch_spacing_mm", 2.5)) / s
            angle = float(vcfg.get("hatch_angle_deg", 45.0))
            groups = view.section_groups if len(view.section_groups) > 1 else [view.section_segments]
            hl = []
            for gi, g in enumerate(groups):
                # adjacent parts of an assembly: alternate direction, then spacing (ISO 128-50)
                a = angle + (90.0 if gi % 2 else 0.0)
                sp = spacing * (1.0 + 0.5 * ((gi // 2) % 3))
                hl += pj.hatch(g, sp, a)
            p, _ = _place(hl, view, cx, cy, s, "hatch")
            view_prims[n] += p
            prims += p

    th_txt = float(cfg.get("text_height_mm", 5.0))
    sym = vcfg.get("section_symbol", "A")
    if "section" in views and section_setup(vcfg)[5] in views:
        axis, offset, flip, sd, sx, base = section_setup(vcfg)
        bv = views[base]
        bcx, bcy = centres[base]
        _, m = _place([], bv, bcx, bcy, s, "visible")
        bdir, bxd = pj.VIEWS[base]
        _, bx_ax, by_ax = pj.frame(bdir, bxd)
        look = (-sd[0], -sd[1], -sd[2])                     # viewing direction
        arrow2 = (pj._dot(look, bx_ax), pj._dot(look, by_ax))
        px, py = m(*pj.project_point(origin, bdir, bxd))
        half_w, half_h = s * bv.w / 2.0, s * bv.h / 2.0
        if abs(arrow2[0]) > 0.5:      # plane seen edge-on as a vertical line
            e1 = (px, bcy - half_h - CUTLINE_EXT)
            e2 = (px, bcy + half_h + CUTLINE_EXT)
            tick = (0.0, 4.0)
        else:                          # horizontal line
            e1 = (bcx - half_w - CUTLINE_EXT, py)
            e2 = (bcx + half_w + CUTLINE_EXT, py)
            tick = (4.0, 0.0)
        prims.append(("line", e1[0], e1[1], e2[0], e2[1], "chain"))
        prims.append(("line", e1[0], e1[1], e1[0] + tick[0], e1[1] + tick[1], "visible"))
        prims.append(("line", e2[0] - tick[0], e2[1] - tick[1], e2[0], e2[1], "visible"))
        ad = (round(arrow2[0]), round(arrow2[1]))
        for e, out_dir in ((e1, -1.0), (e2, 1.0)):
            prims += _arrow(e[0], e[1], ad[0], ad[1])
            # letter next to the arrow, outside the line end
            if ad[0] != 0:
                lx = e[0] + ad[0] * 3.5
                ly = e[1] + 2.0 if out_dir > 0 else e[1] - 2.0 - th_txt
            else:
                lx = e[0] + out_dir * 3.0
                ly = e[1] + ad[1] * 3.5 - th_txt / 2.0
            prims.append(("text", lx, ly, th_txt, sym, "text", "middle"))
        sv = views["section"]
        scx, scy = centres["section"]
        prims.append(("text", scx, scy - s * sv.h / 2.0 - 3.0 - th_txt, th_txt, "%s-%s" % (sym, sym),
                      "text", "middle"))
    if "iso" in views and abs(views["iso"].factor - 1.0) > 1e-9:
        iv = views["iso"]
        icx, icy = centres["iso"]
        prims.append(("text", icx, icy - s * iv.h / 2.0 - 3.0 - 3.5, 3.5,
                      "(%s)" % scale_text(s * iv.factor), "text", "middle"))

    if trails:
        for n, view in views.items():
            if n == "section":
                continue
            cx, cy = centres[n]
            d, xd = pj.VIEWS[n]
            _, m = _place([], view, cx, cy, s, "chain")
            for a, b in trails:
                pa = m(*pj.project_point(a, d, xd))
                pb = m(*pj.project_point(b, d, xd))
                if math.hypot(pb[0] - pa[0], pb[1] - pa[1]) > 0.5:
                    prims.append(("line", pa[0], pa[1], pb[0], pb[1], "chain"))

    if holes:
        for n, view in views.items():
            p = thread_prims(holes, {n: view}, centres, s, bool(vcfg.get("hidden_lines", False)))
            view_prims[n] += p
            prims += p

    maps = {}
    for n, view in views.items():
        cx, cy = centres[n]
        f = s * view.factor
        bx = (view.bbox[0] + view.bbox[2]) / 2.0
        by = (view.bbox[1] + view.bbox[3]) / 2.0
        maps[n] = [cx, cy, f, bx, by, cx - f * (view.bbox[2] - view.bbox[0]) / 2.0,
                   cy - f * (view.bbox[3] - view.bbox[1]) / 2.0,
                   cx + f * (view.bbox[2] - view.bbox[0]) / 2.0, cy + f * (view.bbox[3] - view.bbox[1]) / 2.0]

    # detail views: a circle on a parent view, its content magnified in a circle elsewhere on the sheet
    det_meta = []
    for det in details or []:
        pv = det.get("view")
        if pv not in views or pv not in maps:
            continue
        mp = maps[pv]
        c = det.get("c") or [mp[3], mp[4]]
        r = float(det.get("r") or 5.0)
        k = float(det.get("factor") or 2.0)
        label = str(det.get("id") or "A")
        C = (mp[0] + mp[2] * (c[0] - mp[3]), mp[1] + mp[2] * (c[1] - mp[4]))
        R = r * mp[2]
        Rk = R * k
        pos = det.get("pos")
        if not (isinstance(pos, (list, tuple)) and len(pos) == 2):
            # default: right of all views, at the height of the parent view
            pos = [max(v[7] for v in maps.values()) + Rk + 15.0, mp[1]]
        pos = (float(pos[0]), float(pos[1]))
        prims.append(("circle", C[0], C[1], R, "dim"))
        prims.append(("text", C[0] + R * 0.75, C[1] + R * 0.75, th_txt, label, "text", "start"))
        prims += detail_prims(view_prims.get(pv, []), C, k, pos, Rk)
        prims.append(("circle", pos[0], pos[1], Rk, "dim"))
        prims.append(("text", pos[0], pos[1] + Rk + 3.0, th_txt, "%s (%s)" % (label, scale_text(s * views[pv].factor * k)), "text", "middle"))
        name_d = "detail_" + label
        f_d = mp[2] * k
        maps[name_d] = [pos[0], pos[1], f_d, c[0], c[1], pos[0] - Rk, pos[1] - Rk, pos[0] + Rk, pos[1] + Rk]
        det_meta.append({"id": label, "view": pv, "c": [c[0], c[1]], "r": r, "factor": k, "pos": [pos[0], pos[1]]})
    if annotations:
        from . import annotate
        prims += annotate.render(annotations, maps, cfg)
    if sketches:
        from . import sketch as _sketch
        for tgt, entry in sketches.items():
            if tgt == skip_sketch or not isinstance(entry, dict):
                continue
            if tgt == "sheet":
                prims += _sketch.drawing_prims(entry, None, cfg)
            elif tgt in maps:
                prims += _sketch.drawing_prims(entry, maps[tgt], cfg)

    meta = {"centres": centres, "origin": origin, "first_angle": first_angle, "maps": maps, "details": det_meta,
            "all_views": list(all_views.keys()), "hidden_views": sorted(hidden_set & set(all_views)),
            "section": section_setup(vcfg) if "section" in views else None,
            "iso_factor": views["iso"].factor if "iso" in views else 1.0,
            "hidden": bool(vcfg.get("hidden_lines", False)), "smooth": bool(vcfg.get("smooth_lines", False)),
            "section_symbol": sym, "text_height": th_txt,
            "section_caption_y": (centres["section"][1] - s * views["section"].h / 2.0 - 3.0 - th_txt)
            if "section" in views else None}
    return {"name": name, "sheet": sheet, "size": (W, H), "scale": s, "values": vals, "prims": prims,
            "meta": meta, "template_prims": template_prims, "views": views}


def sketch_refs(d, target):
    """Reference geometry for a sketch on a drawing, as sketch entities with kind "proj" (visible) or "hidden":
    target "sheet": the edges of all views in paper mm; a view name: the edges of that view in view coordinates
    (a detail view: the edges of its parent view inside the detail circle)."""
    views, maps = d["views"], d["meta"]["maps"]
    out = []

    def ent(p, kind, xf, keep=None):
        k = p[0]
        if k == "L":
            a, b = xf(p[1], p[2]), xf(p[3], p[4])
            if keep and not (keep(*a) or keep(*b)):
                return
            out.append({"t": "line", "x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1], "kind": kind})
        elif k in ("C", "A"):
            c = xf(p[1], p[2])
            if keep and not keep(*c):
                return
            r = p[3] * xf.k
            if k == "C":
                out.append({"t": "circle", "cx": c[0], "cy": c[1], "r": r, "kind": kind})
            else:
                out.append({"t": "arc", "cx": c[0], "cy": c[1], "r": r, "a0": p[4], "a1": p[5], "kind": kind})
        elif k == "P":
            pts = [list(xf(x, y)) for x, y in p[1]]
            if keep and not any(keep(x, y) for x, y in pts):
                return
            out.append({"t": "poly", "pts": pts, "closed": False, "kind": kind})

    class Xf(object):
        def __init__(self, mp=None):
            self.mp = mp
            self.k = mp[2] if mp else 1.0

        def __call__(self, x, y):
            if not self.mp:
                return (x, y)
            cx, cy, f, bx, by = self.mp[:5]
            return (cx + f * (x - bx), cy + f * (y - by))

    if target == "sheet":
        names = [(n, maps[n]) for n in views if n in maps]
    elif target.startswith("detail_"):
        det = next((q for q in d["meta"].get("details") or [] if "detail_" + str(q["id"]) == target), None)
        if not det or det["view"] not in views:
            return out
        c, r = det["c"], float(det["r"])
        keep = lambda x, y: math.hypot(x - c[0], y - c[1]) <= r * 1.05      # noqa: E731
        v = views[det["view"]]
        for p in v.visible:
            ent(p, "proj", Xf(), keep)
        if d["meta"].get("hidden"):
            for p in v.hidden:
                ent(p, "hidden", Xf(), keep)
        return out
    else:
        names = [(target, None)] if target in views else []
    for n, mp in names:
        v = views[n]
        for p in v.visible:
            ent(p, "proj", Xf(mp))
        if d["meta"].get("hidden"):
            for p in v.hidden:
                ent(p, "hidden", Xf(mp))
    return out


def snaps(views, details=None, sketches=None, maps=None):
    """Snap geometry per view in view coordinates: points [x, y, kind], circles [cx, cy, r, kind] and straight
    lines [x1, y1, x2, y2] (for angle dimensions). The curves of the sketches made on the drawing (sketches:
    {target: {"doc"}}, maps: view maps) are added to the view they are drawn on; a sketch on the sheet adds each
    point to the view whose frame contains it. A detail view gets the snaps of its parent view inside the detail
    circle."""
    out = _snaps(views)
    if sketches and maps:
        _sketch_snaps(out, sketches, maps)
    for det in details or []:
        pv = det.get("view")
        if pv not in out:
            continue
        c, r = det["c"], float(det["r"])
        inside = lambda x, y: math.hypot(x - c[0], y - c[1]) <= r
        own = out.get("detail_" + str(det["id"])) or {"points": [], "circles": [], "lines": []}   # a sketch on the detail view
        out["detail_" + str(det["id"])] = {"points": [p for p in out[pv]["points"] if inside(p[0], p[1])] + own["points"],
                                           "circles": [q for q in out[pv]["circles"] if inside(q[0], q[1])] + own["circles"],
                                           "lines": [q for q in out[pv]["lines"] if inside((q[0] + q[2]) / 2.0, (q[1] + q[3]) / 2.0)] + own["lines"]}
    return out


def _sketch_snaps(out, sketches, maps):
    """Adds the snap geometry of drawing sketches to out (see snaps)."""
    from . import sketch as _sketch
    views = [(n, m) for n, m in maps.items() if n != "iso" and not str(n).startswith("detail_") and len(m) >= 9]

    def target_of(tgt, X, Y):
        """(view, x, y) of a sketch point: view coordinates; a sheet point goes to the view containing it."""
        if tgt != "sheet":
            return tgt, X, Y
        for n, m in views:
            if m[5] - 2 <= X <= m[7] + 2 and m[6] - 2 <= Y <= m[8] + 2:
                return n, m[3] + (X - m[0]) / m[2], m[4] + (Y - m[1]) / m[2]
        return None, X, Y

    def scale_of(view, tgt):
        return 1.0 if tgt != "sheet" else 1.0 / maps[view][2]

    for tgt, entry in sketches.items():
        if not isinstance(entry, dict) or (tgt != "sheet" and tgt not in maps):
            continue
        sk = entry.get("doc") or {}

        def put(X, Y, kind):
            v, x, y = target_of(tgt, X, Y)
            if v is None:
                return None
            d = out.setdefault(v, {"points": [], "circles": [], "lines": []})
            k = (round(x, 4), round(y, 4))
            if not any((round(p[0], 4), round(p[1], 4)) == k for p in d["points"]):
                d["points"].append([round(x, 5), round(y, 5), kind])
            return v, x, y

        for e, _lay in _sketch.visible_entities(sk):
            t = e.get("t")
            if t == "line":
                a, b = put(e["x1"], e["y1"], "end"), put(e["x2"], e["y2"], "end")
                put((e["x1"] + e["x2"]) / 2.0, (e["y1"] + e["y2"]) / 2.0, "mid")
                if a and b and a[0] == b[0] and math.hypot(b[1] - a[1], b[2] - a[2]) > 1e-6:
                    out[a[0]]["lines"].append([round(a[1], 5), round(a[2], 5), round(b[1], 5), round(b[2], 5)])
            elif t in ("circle", "arc"):
                c = put(e["cx"], e["cy"], "centre")
                if t == "arc":
                    for ang in (e["a0"], e["a1"]):
                        put(e["cx"] + e["r"] * math.cos(math.radians(ang)), e["cy"] + e["r"] * math.sin(math.radians(ang)), "end")
                if c:
                    out[c[0]]["circles"].append([round(c[1], 5), round(c[2], 5), round(e["r"] * scale_of(c[0], tgt), 5), "circle" if t == "circle" else "arc"])
            elif t == "poly":
                pts = e.get("pts") or []
                for q in pts:
                    put(q[0], q[1], "end")
                segs = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if e.get("closed") and len(pts) > 2 else [])
                for q0, q1 in segs:
                    a, b = put(q0[0], q0[1], "end"), put(q1[0], q1[1], "end")
                    put((q0[0] + q1[0]) / 2.0, (q0[1] + q1[1]) / 2.0, "mid")
                    if a and b and a[0] == b[0] and math.hypot(b[1] - a[1], b[2] - a[2]) > 1e-6:
                        out[a[0]]["lines"].append([round(a[1], 5), round(a[2], 5), round(b[1], 5), round(b[2], 5)])
            elif t == "point":
                put(e["x"], e["y"], "end")


def _snaps(views):
    out = {}
    for n, v in views.items():
        if n == "iso":
            continue
        pts, circ, lines, seen = [], [], [], set()

        def add(x, y, kind):
            k = (round(x, 4), round(y, 4))
            if k in seen:
                return
            seen.add(k)
            pts.append([round(x, 5), round(y, 5), kind])

        for p in list(v.visible) + list(v.hidden):
            k = p[0]
            if k == "L":
                add(p[1], p[2], "end")
                add(p[3], p[4], "end")
                if math.hypot(p[3] - p[1], p[4] - p[2]) > 1e-6:
                    lines.append([round(p[1], 5), round(p[2], 5), round(p[3], 5), round(p[4], 5)])
                add((p[1] + p[3]) / 2.0, (p[2] + p[4]) / 2.0, "mid")
            elif k == "C":
                add(p[1], p[2], "centre")
                circ.append([round(p[1], 5), round(p[2], 5), round(p[3], 5), "circle"])
            elif k == "A":
                cx, cy, r, a0, a1 = p[1:]
                add(cx, cy, "centre")
                add(cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0)), "end")
                add(cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1)), "end")
                circ.append([round(cx, 5), round(cy, 5), round(r, 5), "arc"])
            elif k == "P":
                add(p[1][0][0], p[1][0][1], "end")
                add(p[1][-1][0], p[1][-1][1], "end")
                fc = _fit_circle(p[1])
                if fc:
                    add(fc[0], fc[1], "centre")
                    circ.append([round(fc[0], 5), round(fc[1], 5), round(fc[2], 5), "arc"])
        out[n] = {"points": pts, "circles": circ, "lines": lines}
    return out


def _fit_circle(pts):
    """Circle (cx, cy, r) through a polyline when its points lie on a circle (B-spline circles)."""
    if len(pts) < 6:
        return None
    n = float(len(pts))
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    suu = suv = svv = suuu = svvv = suvv = svuu = 0.0
    for x, y in pts:
        u, v = x - mx, y - my
        suu += u * u
        suv += u * v
        svv += v * v
        suuu += u * u * u
        svvv += v * v * v
        suvv += u * v * v
        svuu += v * u * u
    det = suu * svv - suv * suv
    if abs(det) < 1e-12:
        return None
    b1 = 0.5 * (suuu + suvv)
    b2 = 0.5 * (svvv + svuu)
    uc = (b1 * svv - b2 * suv) / det
    vc = (suu * b2 - suv * b1) / det
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    cx, cy = uc + mx, vc + my
    if r <= 0:
        return None
    dev = max(abs(math.hypot(x - cx, y - cy) - r) for x, y in pts)
    span = max(math.hypot(x - pts[0][0], y - pts[0][1]) for x, y in pts)
    if dev > max(1e-3 * r, 1e-4) or span < 0.3 * r:
        return None
    return cx, cy, r
