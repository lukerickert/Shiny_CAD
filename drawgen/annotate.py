# -*- coding: utf-8 -*-
"""Dimensions and notes (ISO 129-1 style) as sheet primitives.

Annotation records (JSON). Coordinates are view coordinates (model mm) of the
named view, or sheet mm when "view" is null (notes only):

  linear    {"type": "linear", "view", "p1": [x, y], "p2": [x, y], "orient": "h" | "v" | "a",
             "pos": [x, y], "text", "prefix", "tol"}
  diameter  {"type": "diameter", "view", "c": [x, y], "r", "pos": [x, y], "text", "prefix", "tol"}
  radius    {"type": "radius", "view", "c": [x, y], "r", "pos": [x, y], "text", "prefix", "tol"}
  angle     {"type": "angle", "view", "c": [x, y] (vertex), "p1": [x, y], "p2": [x, y] (points on the
             two lines), "pos": [x, y] (arc position), "text", "prefix", "tol"}
  balloon   {"type": "balloon", "view", "anchor": [x, y], "pos": [x, y], "text": "1"}  item balloon (ISO 7573)
  note      {"type": "note", "view" | null, "anchor": [x, y] | null, "pos": [x, y], "text"}

  every annotation may carry "height": text height in mm (default dim_text_height_mm)
tol: {"mode": "none" | "fit" | "sym" | "dev", "fit": "H7", "show_dev": true,
      "plus": 0.1, "minus": -0.05}   (deviations in mm)

The text follows the drawing units option (units.py): mm with deviations in µm, or inch.
"""
import math

from . import fits, units as _units

ARROW_L = 3.0      # arrowhead length (mm)
ARROW_W = 0.5      # arrowhead half width (mm)
EXT_GAP = 1.0      # gap between object and extension line (mm)
EXT_OVER = 2.0     # extension line beyond the dimension line (mm)
TEXT_GAP = 1.0     # text above the dimension line (mm)
CHAR_W = 0.78      # character width / text height (Helvetica digits)


def _unit(dx, dy):
    m = math.hypot(dx, dy)
    return (dx / m, dy / m) if m > 1e-12 else (1.0, 0.0)


def _arrow(tip, d):
    """Filled arrowhead with the tip at tip, pointing in direction d."""
    bx, by = tip[0] - d[0] * ARROW_L, tip[1] - d[1] * ARROW_L
    px, py = -d[1] * ARROW_W, d[0] * ARROW_W
    return ("solid", [tip, (bx + px, by + py), (bx - px, by - py)], "dim")


def fmt(v, decimals=3):
    s = ("%.*f" % (decimals, v)).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def text_width(t, h):
    """Text width (mm) for capital height h, Helvetica metrics."""
    try:
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from .render import _pdf_font
        return stringWidth(t, _pdf_font(), h / 0.72)
    except Exception:
        return len(t) * CHAR_W * h


def value_of(a):
    """Measured value (model mm) of a dimension."""
    t = a["type"]
    if t == "linear":
        (x1, y1), (x2, y2) = a["p1"], a["p2"]
        o = a.get("orient", "a")
        if o == "h":
            return abs(x2 - x1)
        if o == "v":
            return abs(y2 - y1)
        return math.hypot(x2 - x1, y2 - y1)
    if t == "diameter":
        return 2.0 * a["r"]
    if t == "radius":
        return a["r"]
    if t == "angle":
        return math.degrees(angle_sector(a["c"], a["p1"], a["p2"], a["pos"])[1])
    return None


def angle_sector(c, p1, p2, q):
    """(start angle, span) in radians of the sector between the lines c-p1 and c-p2 that contains q."""
    t1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    t2 = math.atan2(p2[1] - c[1], p2[0] - c[0])
    tq = math.atan2(q[1] - c[1], q[0] - c[0])
    tw = 2.0 * math.pi
    best = None
    for a in (t1, t1 + math.pi):
        for b in (t2, t2 + math.pi):
            for s0, s1 in ((a, b), (b, a)):
                span = (s1 - s0) % tw
                if span < 1e-9 or span > math.pi + 1e-9:
                    continue
                inside = (tq - s0) % tw <= span + 1e-9
                if inside and (best is None or span < best[1]):
                    best = (s0 % tw, span)
    return best or (t1 % tw, (t2 - t1) % tw)


def label(a, units="mm"):
    """(main text, upper deviation, lower deviation); deviations are None when not stacked. units: "mm" or
    "inch" (drawing units option)."""
    v = value_of(a)
    t = a["type"]
    sym = {"diameter": "Ø", "radius": "R"}.get(t, "")
    if t == "linear" and a.get("dia"):
        sym = "\u00d8"
    if t == "angle":
        main = a.get("text") or (a.get("prefix", "") + fmt(v, 2) + "°")
    else:
        main = a.get("text") or (a.get("prefix", "") + sym + (_units.length_text(v, "inch") if units == "inch" else fmt(v)))
    tol = a.get("tol") or {}
    mode = tol.get("mode", "none")
    up = lo = None
    if mode == "fit" and tol.get("fit"):
        main += " " + tol["fit"]
        if tol.get("show_dev", True):
            try:
                u, l = fits.limits(v, tol["fit"])
                up, lo = _units.dev_text(u, units), _units.dev_text(l, units, lower=True)
            except ValueError:
                pass
    elif mode == "sym":
        main += " ±" + _units.sym_text(float(tol.get("plus", 0) or 0), units)
    elif mode == "dev":
        up = _units.dev_text(float(tol.get("plus", 0) or 0), units)
        lo = _units.dev_text(float(tol.get("minus", 0) or 0), units, lower=True)
    return main, up, lo


def _text_block(base, ang_deg, h, main, up, lo, anchor="middle"):
    """Main text with optional stacked deviations. base: baseline point of the main text."""
    out = []
    a = math.radians(ang_deg)
    u = (math.cos(a), math.sin(a))
    n = (-u[1], u[0])
    wm = text_width(main, h)
    if up is None:
        out.append(("rtext", base[0], base[1], h, main, anchor, ang_deg))
        return out
    hd = h * 0.7
    wd = max(text_width(up, hd), text_width(lo, hd))
    total = wm + 0.8 + wd
    if anchor == "middle":
        s0 = -total / 2.0
    elif anchor == "end":
        s0 = -total
    else:
        s0 = 0.0
    p = (base[0] + u[0] * s0, base[1] + u[1] * s0)
    out.append(("rtext", p[0], p[1], h, main, "start", ang_deg))
    q = (p[0] + u[0] * (wm + 0.8), p[1] + u[1] * (wm + 0.8))
    # ISO 129-1: the lower deviation on the baseline of the nominal value, the upper deviation above it
    out.append(("rtext", q[0] + n[0] * hd * 1.4, q[1] + n[1] * hd * 1.4, hd, up, "start", ang_deg))
    out.append(("rtext", q[0], q[1], hd, lo, "start", ang_deg))
    return out


def _reading_angle(u):
    """Text angle for a dimension line direction u: readable from the bottom or the right."""
    ang = math.degrees(math.atan2(u[1], u[0]))
    while ang <= -90.0 + 1e-9:
        ang += 180.0
    while ang > 90.0 + 1e-9:
        ang -= 180.0
    return ang


def _linear(a, M, h, U="mm"):
    P1, P2, Q = M(a["p1"]), M(a["p2"]), M(a["pos"])
    o = a.get("orient", "a")
    if o == "h":
        u = (1.0, 0.0)
    elif o == "v":
        u = (0.0, 1.0)
    else:
        u = _unit(P2[0] - P1[0], P2[1] - P1[1])
    n = (-u[1], u[0])

    def foot(P):
        d = (Q[0] - P[0]) * n[0] + (Q[1] - P[1]) * n[1]
        return (P[0] + n[0] * d, P[1] + n[1] * d), d

    A, dA = foot(P1)
    B, dB = foot(P2)
    out = []
    for P, F, d in ((P1, A, dA), (P2, B, dB)):
        if abs(d) > EXT_GAP:
            sg = 1.0 if d > 0 else -1.0
            out.append(("line", P[0] + n[0] * sg * EXT_GAP, P[1] + n[1] * sg * EXT_GAP,
                        F[0] + n[0] * sg * EXT_OVER, F[1] + n[1] * sg * EXT_OVER, "dim"))
    L = math.hypot(B[0] - A[0], B[1] - A[1])
    dab = _unit(B[0] - A[0], B[1] - A[1])
    main, up, lo = label(a, U)
    tw = text_width(main, h) + (0.8 + max(text_width(up, h * 0.7), text_width(lo, h * 0.7)) if up else 0.0)
    # text position along the dimension line: projection of pos (dragging the dimension moves the text)
    t = (Q[0] - A[0]) * dab[0] + (Q[1] - A[1]) * dab[1]
    if not a.get("text_free"):
        t = L / 2.0          # centred until the dimension is dragged
    inside = L >= 2 * ARROW_L + 1.0
    if inside:
        out.append(("line", A[0], A[1], B[0], B[1], "dim"))
        out.append(_arrow(A, (-dab[0], -dab[1])))
        out.append(_arrow(B, dab))
    else:
        e = ARROW_L + 3.0
        out.append(("line", A[0] - dab[0] * e, A[1] - dab[1] * e, B[0] + dab[0] * e, B[1] + dab[1] * e, "dim"))
        out.append(_arrow(A, dab))
        out.append(_arrow(B, (-dab[0], -dab[1])))
    # text outside the extension lines: extend the dimension line under the text
    if t > L:
        end = t + tw / 2.0 + 1.0
        out.append(("line", B[0], B[1], A[0] + dab[0] * end, A[1] + dab[1] * end, "dim"))
    elif t < 0:
        end = t - tw / 2.0 - 1.0
        out.append(("line", A[0], A[1], A[0] + dab[0] * end, A[1] + dab[1] * end, "dim"))
    ang = _reading_angle(u)
    ar = math.radians(ang)
    up_dir = (-math.sin(ar), math.cos(ar))
    mid = (A[0] + dab[0] * t, A[1] + dab[1] * t)
    base = (mid[0] + up_dir[0] * TEXT_GAP, mid[1] + up_dir[1] * TEXT_GAP)
    out += _text_block(base, ang, h, main, up, lo, "middle")
    return out


def _radial(a, M, h, f, U="mm"):
    C = M(a["c"])
    r = a["r"] * f
    Q = M(a["pos"])
    d = _unit(Q[0] - C[0], Q[1] - C[1])
    N = (C[0] + d[0] * r, C[1] + d[1] * r)
    F = (C[0] - d[0] * r, C[1] - d[1] * r)
    dist = math.hypot(Q[0] - C[0], Q[1] - C[1])
    out = []
    main, up, lo = label(a, U)
    outside = dist > r + 0.5
    if a["type"] == "diameter":
        if 2 * r >= 2 * ARROW_L + 2.0:
            end = Q if outside else N
            out.append(("line", F[0], F[1], end[0], end[1], "dim"))
            out.append(_arrow(F, (-d[0], -d[1])))
            out.append(_arrow(N, d))
        else:
            out.append(("line", N[0], N[1], Q[0], Q[1], "dim"))
            out.append(_arrow(N, (-d[0], -d[1])))
            out.append(("line", F[0], F[1], F[0] - d[0] * (ARROW_L + 3), F[1] - d[1] * (ARROW_L + 3), "dim"))
            out.append(_arrow(F, d))
            outside = True
    else:
        end = Q if outside else N
        out.append(("line", C[0], C[1], end[0], end[1], "dim"))
        out.append(_arrow(N, d))
    if outside:
        sgn = 1.0 if d[0] >= 0 else -1.0
        w = text_width(main, h) + (0.8 + text_width(up or "", h * 0.7) if up else 0.0) + 1.0
        S = (Q[0] + sgn * w, Q[1])
        out.append(("line", Q[0], Q[1], S[0], S[1], "dim"))
        x0 = min(Q[0], S[0]) + 0.5
        out += _text_block((x0, Q[1] + TEXT_GAP), 0.0, h, main, up, lo, "start")
    else:
        out += _text_block((Q[0], Q[1] + TEXT_GAP), 0.0, h, main, up, lo, "middle")
    return out


def _angle(a, M, h, U="mm"):
    C, P1, P2, Q = M(a["c"]), M(a["p1"]), M(a["p2"]), M(a["pos"])
    s0, span = angle_sector(C, P1, P2, Q)
    R = math.hypot(Q[0] - C[0], Q[1] - C[1])
    out = []
    ends = (s0, s0 + span)
    # extension lines from the line ends to the arc where the arc is beyond the lines
    for P in (P1, P2):
        tp = math.atan2(P[1] - C[1], P[0] - C[0])
        dp = math.hypot(P[0] - C[0], P[1] - C[1])
        for e in ends:
            if abs(math.remainder(tp - e, 2 * math.pi)) < 1e-6 and R > dp + EXT_GAP:
                u = (math.cos(e), math.sin(e))
                out.append(("line", C[0] + u[0] * (dp + EXT_GAP), C[1] + u[1] * (dp + EXT_GAP),
                            C[0] + u[0] * (R + EXT_OVER), C[1] + u[1] * (R + EXT_OVER), "dim"))
    out.append(("arc", C[0], C[1], R, math.degrees(s0), math.degrees(s0 + span), "dim"))
    for e, sg in ((ends[0], -1.0), (ends[1], 1.0)):
        tip = (C[0] + R * math.cos(e), C[1] + R * math.sin(e))
        tang = (-math.sin(e) * sg, math.cos(e) * sg)
        if R * span < 2 * ARROW_L + 1.0:
            tang = (-tang[0], -tang[1])
        out.append(_arrow(tip, tang))
    main, up, lo = label(a, U)
    mid = s0 + span / 2.0
    u = (-math.sin(mid), math.cos(mid))
    ang = _reading_angle(u)
    ar = math.radians(ang)
    up_dir = (-math.sin(ar), math.cos(ar))
    base = (C[0] + R * math.cos(mid) + up_dir[0] * TEXT_GAP, C[1] + R * math.sin(mid) + up_dir[1] * TEXT_GAP)
    if up_dir[0] * math.cos(mid) + up_dir[1] * math.sin(mid) < 0:
        base = (C[0] + R * math.cos(mid) - up_dir[0] * (TEXT_GAP + h),
                C[1] + R * math.sin(mid) - up_dir[1] * (TEXT_GAP + h))
    out += _text_block(base, ang, h, main, up, lo, "middle")
    return out


def _balloon(a, M, h):
    """Circle with the item number, leader from the circle edge to the anchor point (dot at the anchor)."""
    P = M(a["pos"])
    text = str(a.get("text", ""))
    r = max(h * 1.0, text_width(text, h) / 2.0 + h * 0.5)
    out = [("circle", P[0], P[1], r, "dim")]
    out.append(("rtext", P[0], P[1] - h * 0.5, h, text, "middle", 0.0))
    if a.get("anchor"):
        A = M(a["anchor"])
        d = _unit(A[0] - P[0], A[1] - P[1])
        S = (P[0] + d[0] * r, P[1] + d[1] * r)
        out.append(("line", S[0], S[1], A[0], A[1], "dim"))
        # dot at the anchor (the leader ends on a surface)
        n = 12
        pts = [(A[0] + 0.6 * math.cos(2 * math.pi * k / n), A[1] + 0.6 * math.sin(2 * math.pi * k / n)) for k in range(n)]
        out.append(("solid", pts, "dim"))
    return out


def _note(a, M, h):
    raw = (a.get("text") or "").replace("\r\n", "\n")
    # typed line-break markers are also accepted: \n or /n surrounded by spaces
    raw = raw.replace("\\n", "\n").replace(" /n ", "\n").replace(" /n", "\n").replace("/n ", "\n")
    lines = raw.split("\n")
    P = M(a["pos"])
    out = []
    for i, t in enumerate(lines):
        if t:
            out.append(("rtext", P[0], P[1] - i * h * 1.6, h, t, "start", 0.0))
    if a.get("anchor"):
        A = M(a["anchor"])
        w = max([text_width(t, h) for t in lines] + [h])
        left = A[0] <= P[0] + w / 2.0
        S = (P[0] - 1.0, P[1] + h * 0.4) if left else (P[0] + w + 1.0, P[1] + h * 0.4)
        out.append(("line", A[0], A[1], S[0], S[1], "dim"))
        out.append(_arrow(A, _unit(A[0] - S[0], A[1] - S[1])))
    return out


def render(anns, maps, cfg):
    """Sheet primitives for annotations; one ("group", id, prims) per annotation."""
    h = float(cfg.get("dim_text_height_mm", 3.5))
    U = _units.units_of(cfg)
    out = []
    for a in anns or []:
        view = a.get("view")
        if view:
            if view not in maps:
                continue
            cx, cy, f, bx, by = maps[view][:5]

            def M(p, cx=cx, cy=cy, f=f, bx=bx, by=by):
                return cx + f * (p[0] - bx), cy + f * (p[1] - by)
        else:
            f = 1.0

            def M(p):
                return float(p[0]), float(p[1])
        try:
            t = a["type"]
            ah = float(a.get("height") or 0) or h          # per-annotation text height (mm)
            if t == "linear":
                prims = _linear(a, M, ah, U)
            elif t in ("diameter", "radius"):
                prims = _radial(a, M, ah, f, U)
            elif t == "angle":
                prims = _angle(a, M, ah, U)
            elif t == "note":
                prims = _note(a, M, ah)
            elif t == "balloon":
                prims = _balloon(a, M, ah)
            else:
                continue
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
        out.append(("group", a.get("id", ""), prims))
    return out
