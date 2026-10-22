# -*- coding: utf-8 -*-
"""2D sketches: DXF import, DXF and PDF export.

Sketch record (JSON), coordinates in drawing units (normally mm):

  {"name", "source", "units": "mm", "insunits": 4, "scale": 1.0,
   "layers": [{"name", "aci", "color": "#rrggbb", "linetype", "lineweight", "on"}],
   "linetypes": [{"name", "pattern": [dash, gap, ...], "description"}],
   "current_layer": "0",
   "entities": [...], "constraints": [...], "dims": [...], "next_id": n}

Entities (all with "id", "t", "layer", optional "aci", "color", "linetype", "constr"):
  line   x1 y1 x2 y2
  circle cx cy r
  arc    cx cy r a0 a1        degrees, counter-clockwise from a0 to a1
  point  x y
  poly   pts [[x, y], ...] closed
  text   x y h text rot anchor   (baseline of the first line; lines separated by "\n")

Dimensions and notes for export are sent resolved, in the annotate.py schema,
with "view": "sketch" and model coordinates.
"""
import io
import math

from . import annotate, render
from . import titleblock as tbk

LINE_SPACING = 1.6

UNIT_NAMES = {0: "unitless", 1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}


# --------------------------------------------------------------------------- linetypes

def linetype_class(name, pattern=None):
    """continuous | hidden | chain | dot from a linetype name or pattern."""
    n = (name or "").upper()
    if n in ("", "CONTINUOUS", "BYLAYER", "BYBLOCK"):
        return "continuous"
    if any(k in n for k in ("CENTER", "CHAIN", "DASHDOT", "PHANTOM", "DIVIDE", "BORDER")):
        return "chain"
    if "DOT" in n:
        return "dot"
    if any(k in n for k in ("HIDDEN", "DASH")):
        return "hidden"
    if pattern:
        n_dash = sum(1 for i, v in enumerate(pattern) if i % 2 == 0 and v > 1e-9)
        if len(pattern) >= 4:
            return "chain"
        if n_dash:
            return "hidden"
    return "continuous"


# --------------------------------------------------------------------------- import

def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(v) for v in rgb)


def _aci_hex(aci):
    from ezdxf.colors import aci2rgb
    try:
        if aci in (7, 0, 256) or aci is None:
            return "#000000"
        return _hex(aci2rgb(abs(int(aci))))
    except Exception:
        return "#000000"


class _Importer:
    def __init__(self):
        self.entities = []
        self.skipped = {}
        self.n = 0

    def nid(self):
        self.n += 1
        return "e%d" % self.n

    def base(self, e, t, inherit=None):
        d = {"id": self.nid(), "t": t, "layer": e.dxf.get("layer", "0")}
        if inherit is not None and d["layer"] == "0":
            d["layer"] = inherit.get("layer", "0")
        aci = e.dxf.get("color", 256)
        if aci == 0 and inherit is not None:
            aci = inherit.get("aci", 256)
        if aci not in (256, 0):
            d["aci"] = int(aci)
            d["color"] = _aci_hex(aci)
        if e.dxf.hasattr("true_color"):
            try:
                d["color"] = _hex(e.rgb)
                d.setdefault("aci", 7)
            except Exception:
                pass
        lt = e.dxf.get("linetype", "BYLAYER")
        if lt.upper() == "BYBLOCK" and inherit is not None:
            lt = inherit.get("linetype", "BYLAYER")
        if lt.upper() not in ("BYLAYER", "BYBLOCK"):
            d["linetype"] = lt
        return d

    def skip(self, t):
        self.skipped[t] = self.skipped.get(t, 0) + 1

    def add(self, e, inherit=None, depth=0):
        t = e.dxftype()
        try:
            if t == "LINE":
                s, f = e.dxf.start, e.dxf.end
                d = self.base(e, "line", inherit)
                d.update(x1=s.x, y1=s.y, x2=f.x, y2=f.y)
                self.entities.append(d)
            elif t == "CIRCLE":
                c = e.ocs().to_wcs(e.dxf.center)
                d = self.base(e, "circle", inherit)
                d.update(cx=c.x, cy=c.y, r=float(e.dxf.radius))
                self.entities.append(d)
            elif t == "ARC":
                ocs = e.ocs()
                c0, r = e.dxf.center, float(e.dxf.radius)
                a0, a1 = math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle)
                c = ocs.to_wcs(c0)
                s = ocs.to_wcs((c0.x + r * math.cos(a0), c0.y + r * math.sin(a0), c0.z))
                f = ocs.to_wcs((c0.x + r * math.cos(a1), c0.y + r * math.sin(a1), c0.z))
                if e.dxf.extrusion.z < 0:
                    s, f = f, s
                d = self.base(e, "arc", inherit)
                d.update(cx=c.x, cy=c.y, r=r,
                         a0=math.degrees(math.atan2(s.y - c.y, s.x - c.x)) % 360.0,
                         a1=math.degrees(math.atan2(f.y - c.y, f.x - c.x)) % 360.0)
                self.entities.append(d)
            elif t == "POINT":
                p = e.dxf.location
                d = self.base(e, "point", inherit)
                d.update(x=p.x, y=p.y)
                self.entities.append(d)
            elif t in ("LWPOLYLINE", "POLYLINE"):
                if t == "POLYLINE" and not e.is_2d_polyline:
                    pts = [(v.x, v.y) for v in e.points()]
                    self._poly(e, pts, e.is_closed, inherit)
                elif t == "LWPOLYLINE" and len(e) > 50 and not any(b for b in e.get_points("b")):
                    self._poly(e, [(p[0], p[1]) for p in e.get_points("xy")], e.closed, inherit)
                else:
                    attrs = self._inherit(e, inherit)
                    for v in e.virtual_entities():
                        self.add(v, attrs, depth)
            elif t in ("SPLINE", "ELLIPSE"):
                pts = [(p.x, p.y) for p in e.flattening(0.01)]
                closed = len(pts) > 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-9
                self._poly(e, pts[:-1] if closed else pts, closed, inherit)
            elif t in ("SOLID", "TRACE"):
                v = [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx3, e.dxf.vtx2]
                if v[2].isclose(v[3]):
                    v = v[:3]
                d = self.base(e, "poly", inherit)
                d.update(pts=[[p.x, p.y] for p in v], closed=True, fill=True)
                self.entities.append(d)
            elif t == "TEXT":
                self._text(e, inherit)
            elif t == "MTEXT":
                self._mtext(e, inherit)
            elif t in ("INSERT", "DIMENSION", "LEADER", "MULTILEADER", "MLEADER") and depth < 8:
                attrs = self._inherit(e, inherit)
                for v in e.virtual_entities():
                    self.add(v, attrs, depth + 1)
                if t == "INSERT":
                    for a in e.attribs:
                        self._text(a, attrs)
            elif t == "ATTRIB":
                self._text(e, inherit)
            else:
                self.skip(t)
        except Exception:
            self.skip(t)

    def _inherit(self, e, inherit):
        layer = e.dxf.get("layer", "0")
        if layer == "0" and inherit is not None:
            layer = inherit.get("layer", "0")
        aci = e.dxf.get("color", 256)
        if aci == 0 and inherit is not None:
            aci = inherit.get("aci", 256)
        lt = e.dxf.get("linetype", "BYLAYER")
        return {"layer": layer, "aci": aci, "linetype": lt}

    def _poly(self, e, pts, closed, inherit):
        if len(pts) < 2:
            return
        d = self.base(e, "poly", inherit)
        d.update(pts=[[float(x), float(y)] for x, y in pts], closed=bool(closed))
        self.entities.append(d)

    def _text(self, e, inherit):
        txt = e.plain_text() if hasattr(e, "plain_text") else e.dxf.text
        if not txt:
            return
        h = float(e.dxf.get("height", 2.5))
        rot = float(e.dxf.get("rotation", 0.0))
        halign, valign = e.dxf.get("halign", 0), e.dxf.get("valign", 0)
        p = e.dxf.insert
        if (halign or valign) and e.dxf.hasattr("align_point"):
            p = e.dxf.align_point
        anchor = {1: "middle", 2: "end", 4: "middle"}.get(halign, "start")
        shift = {2: -h / 2.0, 3: -h}.get(valign, 0.0)
        r = math.radians(rot)
        x, y = p.x - math.sin(r) * shift, p.y + math.cos(r) * shift
        d = self.base(e, "text", inherit)
        d.update(x=x, y=y, h=h, text=txt, rot=rot, anchor=anchor)
        self.entities.append(d)

    def _mtext(self, e, inherit):
        txt = e.plain_text()
        if not txt:
            return
        h = float(e.dxf.get("char_height", 2.5))
        try:
            rot = float(e.get_rotation())
        except Exception:
            rot = float(e.dxf.get("rotation", 0.0))
        ap = e.dxf.get("attachment_point", 1)
        lines = txt.split("\n")
        n = len(lines)
        block = h + (n - 1) * LINE_SPACING * h
        shift = {0: -h, 1: block / 2.0 - h, 2: block - h}[(ap - 1) // 3]
        anchor = {0: "start", 1: "middle", 2: "end"}[(ap - 1) % 3]
        p = e.dxf.insert
        r = math.radians(rot)
        x, y = p.x - math.sin(r) * shift, p.y + math.cos(r) * shift
        d = self.base(e, "text", inherit)
        d.update(x=x, y=y, h=h, text=txt, rot=rot, anchor=anchor)
        self.entities.append(d)


def import_dxf(path, name):
    import ezdxf
    from ezdxf import recover
    try:
        doc = ezdxf.readfile(path)
    except ezdxf.DXFStructureError:
        doc, _ = recover.readfile(path)
    layers = []
    for lay in doc.layers:
        aci = lay.dxf.get("color", 7)
        try:
            lw = int(lay.dxf.get("lineweight", -3))
        except (TypeError, ValueError):
            lw = -3
        layers.append({"name": lay.dxf.name, "aci": abs(aci), "color": _aci_hex(abs(aci)),
                       "linetype": lay.dxf.get("linetype", "Continuous"),
                       "lineweight": lw / 100.0 if lw > 0 else -1,
                       "on": aci >= 0 and not lay.is_frozen()})
    linetypes = []
    for lt in doc.linetypes:
        nm = lt.dxf.name
        if nm.upper() in ("BYLAYER", "BYBLOCK", "CONTINUOUS"):
            continue
        try:
            pat = [float(v) for v in lt.simplified_line_pattern()]
        except Exception:
            pat = []
        linetypes.append({"name": nm, "pattern": pat, "description": lt.dxf.get("description", ""),
                          "cls": linetype_class(nm, pat)})
    imp = _Importer()
    for e in doc.modelspace():
        imp.add(e)
    names = {l["name"] for l in layers}
    for e in imp.entities:
        if e["layer"] not in names:
            layers.append({"name": e["layer"], "aci": 7, "color": "#000000", "linetype": "Continuous",
                           "lineweight": -1, "on": True})
            names.add(e["layer"])
    ins = int(doc.header.get("$INSUNITS", 0) or 0)
    return {"name": name, "source": "", "units": UNIT_NAMES.get(ins, "unit %d" % ins), "insunits": ins,
            "scale": 1.0, "layers": layers, "linetypes": linetypes,
            "current_layer": "0" if "0" in names else layers[0]["name"],
            "entities": imp.entities, "constraints": [], "dims": [], "next_id": imp.n + 1,
            "skipped": imp.skipped}


# --------------------------------------------------------------------------- common

def _layer_map(sk):
    return {l["name"]: l for l in sk.get("layers") or []}


def visible_entities(sk):
    lays = _layer_map(sk)
    for e in sk.get("entities") or []:
        if e.get("constr"):
            continue
        lay = lays.get(e.get("layer", "0"))
        if lay is not None and not lay.get("on", True):
            continue
        yield e, lay


def entity_linetype(sk, e, lay):
    lt = e.get("linetype") or (lay or {}).get("linetype") or "Continuous"
    if lt.upper() == "BYLAYER":
        lt = (lay or {}).get("linetype") or "Continuous"
    pats = {l["name"].upper(): l.get("pattern") for l in sk.get("linetypes") or []}
    return lt, linetype_class(lt, pats.get(lt.upper()))


def _arc_pts(cx, cy, r, a0, a1, n=None):
    span = (a1 - a0) % 360.0 or 360.0
    n = n or max(8, int(span / 5))
    return [(cx + r * math.cos(math.radians(a0 + span * i / n)),
             cy + r * math.sin(math.radians(a0 + span * i / n))) for i in range(n + 1)]


def _ellipse_pts(e, n=64):
    """Sampled points of an ellipse entity (cx, cy, rx, ry, rot deg, a0, a1 parameter angles)."""
    a0 = float(e.get("a0", 0) or 0)
    a1 = float(e.get("a1", 0) or 0)
    span = (a1 - a0) % 360.0
    if span < 1e-9:
        span = 360.0
    r = math.radians(float(e.get("rot", 0) or 0))
    out = []
    for i in range(n + 1):
        t = math.radians(a0 + span * i / n)
        x, y = e["rx"] * math.cos(t), e["ry"] * math.sin(t)
        out.append((e["cx"] + x * math.cos(r) - y * math.sin(r), e["cy"] + x * math.sin(r) + y * math.cos(r)))
    return out


_SPLINE_CACHE = {}


def _spline_solve(pts, closed):
    """Cached _spline_solve_now (the same fit points are solved for every span of a profile)."""
    key = (tuple((float(p[0]), float(p[1])) for p in pts), bool(closed))
    S = _SPLINE_CACHE.get(key)
    if S is None:
        if len(_SPLINE_CACHE) > 256:
            _SPLINE_CACHE.clear()
        S = _SPLINE_CACHE[key] = _spline_solve_now(pts, closed)
    return S


def _spline_solve_now(pts, closed):
    """Second derivatives of the cubic spline through pts (chord-length parameters, natural ends, periodic when
    closed). Returns (P, h, m, Mx, My). The same curve as splineSolve in sketch.js."""
    pts = [tuple(p) for p in pts]
    P = pts + [pts[0]] if closed else pts
    m = len(P) - 1
    h = [max(1e-9, math.hypot(P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1])) for i in range(m)]
    npts = m if closed else m + 1

    def solve(c):
        if m < 1 or (m == 1 and not closed):
            return [0.0, 0.0]
        y = [q[c] for q in P]
        N = m if closed else m + 1
        A = [[0.0] * N for _ in range(N)]
        b = [0.0] * N
        if not closed:
            A[0][0] = 1.0
            A[N - 1][N - 1] = 1.0
        for i in range(0 if closed else 1, m):
            hp, hc = h[(i - 1 + m) % m], h[i % m]
            r = i % N
            A[r][(i - 1 + N) % N] += hp
            A[r][r] += 2 * (hp + hc)
            A[r][(i + 1) % N] += hc
            b[r] = 6 * ((y[(i + 1) % npts] - y[i]) / hc - (y[i] - y[(i - 1 + npts) % npts]) / hp)
        if N > 24:
            # many fit points (a sampled curve): numpy solve of the (cyclic) tridiagonal system
            try:
                import numpy as np
                M = [float(v) for v in np.linalg.solve(np.asarray(A), np.asarray(b))]
                return M + [M[0]] if closed else M
            except Exception:
                pass
        for c0 in range(N):
            piv = max(range(c0, N), key=lambda r: abs(A[r][c0]))
            A[c0], A[piv] = A[piv], A[c0]
            b[c0], b[piv] = b[piv], b[c0]
            if abs(A[c0][c0]) < 1e-14:
                continue
            for r in range(c0 + 1, N):
                f = A[r][c0] / A[c0][c0]
                if f:
                    for j in range(c0, N):
                        A[r][j] -= f * A[c0][j]
                    b[r] -= f * b[c0]
        M = [0.0] * N
        for r in range(N - 1, -1, -1):
            sm = b[r] - sum(A[r][j] * M[j] for j in range(r + 1, N))
            M[r] = 0.0 if abs(A[r][r]) < 1e-14 else sm / A[r][r]
        return M + [M[0]] if closed else M

    return P, h, m, closed, solve(0), solve(1)


def spline_at(S, t):
    P, h, m, closed, Mx, My = S
    if m < 1:
        return P[0]
    if closed:
        t = t % m
    i = min(m - 1, max(0, int(math.floor(t))))
    u = t - i
    hi = h[i]
    a = 1 - u
    f = lambda y0, y1, M0, M1: a * y0 + u * y1 + ((a ** 3 - a) * M0 + (u ** 3 - u) * M1) * hi * hi / 6.0
    return (f(P[i][0], P[i + 1][0], Mx[i], Mx[i + 1]), f(P[i][1], P[i + 1][1], My[i], My[i + 1]))


def spline_span_hermite(S, i):
    """Span i of the spline as Hermite data in its own parameter u in [0, 1]: (p0, p1, d0, d1) with d = dP/du."""
    P, h, m, closed, Mx, My = S
    hi = h[i]

    def d(y0, y1, M0, M1, u):
        a = 1 - u
        return (y1 - y0) + ((-(3 * a * a - 1)) * M0 + (3 * u * u - 1) * M1) * hi * hi / 6.0

    d0 = (d(P[i][0], P[i + 1][0], Mx[i], Mx[i + 1], 0.0), d(P[i][1], P[i + 1][1], My[i], My[i + 1], 0.0))
    d1 = (d(P[i][0], P[i + 1][0], Mx[i], Mx[i + 1], 1.0), d(P[i][1], P[i + 1][1], My[i], My[i + 1], 1.0))
    return P[i], P[i + 1], d0, d1


def spline_range(e):
    m = len(e["pts"]) if e.get("closed") else len(e["pts"]) - 1
    t0 = e.get("t0")
    t1 = e.get("t1")
    return (0.0 if t0 is None else float(t0)), (float(m) if t1 is None else float(t1))


def spline_pts(pts, closed, k=12, t0=None, t1=None):
    """Points of the cubic spline through the fit points between the parameters t0 and t1 (span index plus
    fraction; default the whole curve), k samples per span."""
    pts = [tuple(p) for p in pts]
    if len(pts) < 2:
        return pts
    S = _spline_solve(pts, closed)
    m = S[2]
    if t0 is None:
        t0 = 0.0
    if t1 is None:
        t1 = float(m)
    out = [spline_at(S, t0)]
    if m >= 1 and (len(pts) > 2 or closed):
        i = int(math.floor(t0 * k)) + 1
        while i < t1 * k - 1e-9:
            t = i / float(k)
            if t > t0 + 1e-9:
                out.append(spline_at(S, t))
            i += 1
    out.append(spline_at(S, t1))
    return out


def spline_pts_e(e, k=12):
    t0, t1 = spline_range(e)
    return spline_pts(e["pts"], e.get("closed"), k, t0, t1)


def conic_pts(e, n=32):
    """Sampled points of a conic entity (x0, y0, x1, y1, xt, yt, rho; t0, t1 kept range)."""
    from .part import conic_pt
    d = (e["x0"], e["y0"], e["x1"], e["y1"], e["xt"], e["yt"], float(e.get("rho", 0.5) or 0.5))
    t0 = 0.0 if e.get("t0") is None else float(e["t0"])
    t1 = 1.0 if e.get("t1") is None else float(e["t1"])
    return [conic_pt(d, t0 + (t1 - t0) * i / n) for i in range(n + 1)]


def _ellipse_closed(e):
    return ((float(e.get("a1", 0) or 0) - float(e.get("a0", 0) or 0)) % 360.0) < 1e-9


def entity_points(e):
    t = e["t"]
    if t == "ellipse":
        return _ellipse_pts(e, 36)
    if t == "line":
        return [(e["x1"], e["y1"]), (e["x2"], e["y2"])]
    if t == "circle":
        return [(e["cx"] - e["r"], e["cy"] - e["r"]), (e["cx"] + e["r"], e["cy"] + e["r"])]
    if t == "arc":
        return _arc_pts(e["cx"], e["cy"], e["r"], e["a0"], e["a1"], 36)
    if t == "point":
        return [(e["x"], e["y"])]
    if t == "poly":
        return [tuple(p) for p in e["pts"]]
    if t == "spline":
        return spline_pts_e(e, 8)
    if t == "conic":
        return conic_pts(e, 16)
    if t == "text":
        n = len(str(e.get("text", "")).split("\n"))
        w = max(annotate.text_width(s, e["h"]) for s in str(e["text"]).split("\n"))
        r = math.radians(e.get("rot", 0.0))
        u, v = (math.cos(r), math.sin(r)), (-math.sin(r), math.cos(r))
        off = {"middle": -w / 2.0, "end": -w}.get(e.get("anchor"), 0.0)
        pts = []
        for s in (off, off + w):
            for tt in (e["h"], -(n - 1) * LINE_SPACING * e["h"]):
                pts.append((e["x"] + u[0] * s + v[0] * tt, e["y"] + u[1] * s + v[1] * tt))
        return pts
    return []


def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if not xs:
        return 0.0, 0.0, 100.0, 100.0
    return min(xs), min(ys), max(xs), max(ys)


def _xform_prim(p, f):
    """Apply f(x, y) -> (x', y') with uniform scale k = f's scale to a primitive (k passed as f.k)."""
    k = f.k
    t = p[0]
    if t == "line":
        a, b = f(p[1], p[2]), f(p[3], p[4])
        return ("line", a[0], a[1], b[0], b[1], p[5])
    if t == "circle":
        a = f(p[1], p[2])
        return ("circle", a[0], a[1], p[3] * k, p[4])
    if t == "arc":
        a = f(p[1], p[2])
        return ("arc", a[0], a[1], p[3] * k, p[4], p[5], p[6])
    if t in ("poly", "solid"):
        return (t, [f(x, y) for x, y in p[1]]) + tuple(p[2:])
    if t == "rtext":
        a = f(p[1], p[2])
        return ("rtext", a[0], a[1], p[3] * k, p[4], p[5], p[6])
    if t == "text":
        a = f(p[1], p[2])
        return ("text", a[0], a[1], p[3] * k) + tuple(p[4:])
    if t == "group":
        return ("group", p[1], [_xform_prim(q, f) for q in p[2]])
    return p


class _Xf:
    def __init__(self, k, ox, oy):
        self.k, self.ox, self.oy = k, ox, oy

    def __call__(self, x, y):
        return (self.ox + self.k * x, self.oy + self.k * y)


def _style(cfg, cls, lw):
    if lw is None or lw <= 0:
        w = cfg["line_widths_mm"]["visible"] if cls == "continuous" else cfg["line_widths_mm"]["hidden"]
    else:
        w = lw
    return "lw:%.3f:%s" % (w, cls)


def model_prims(sk, cfg):
    """Entity primitives in model coordinates (PDF styles)."""
    out = []
    for e, lay in visible_entities(sk):
        _, cls = entity_linetype(sk, e, lay)
        st = _style(cfg, cls, (lay or {}).get("lineweight", -1))
        t = e["t"]
        if t == "line":
            out.append(("line", e["x1"], e["y1"], e["x2"], e["y2"], st))
        elif t == "circle":
            out.append(("circle", e["cx"], e["cy"], e["r"], st))
        elif t == "arc":
            out.append(("arc", e["cx"], e["cy"], e["r"], e["a0"], e["a1"], st))
        elif t == "poly" and e.get("fill"):
            out.append(("solid", [tuple(p) for p in e["pts"]], st))
        elif t == "poly":
            out.append(("poly", [tuple(p) for p in e["pts"]], st, bool(e.get("closed"))))
        elif t == "ellipse":
            pts = _ellipse_pts(e, 96)
            closed = _ellipse_closed(e)
            out.append(("poly", pts[:-1] if closed else pts, st, closed))
        elif t == "spline":
            pts = spline_pts_e(e, 16)
            closed = bool(e.get("closed")) and e.get("t0") is None and e.get("t1") is None
            out.append(("poly", pts[:-1] if closed else pts, st, closed))
        elif t == "conic":
            out.append(("poly", conic_pts(e, 64), st, False))
        elif t == "text":
            r = math.radians(e.get("rot", 0.0))
            for i, s in enumerate(str(e["text"]).split("\n")):
                d = i * LINE_SPACING * e["h"]
                out.append(("rtext", e["x"] + math.sin(r) * d, e["y"] - math.cos(r) * d, e["h"], s,
                            e.get("anchor", "start"), e.get("rot", 0.0)))
    return out


# --------------------------------------------------------------------------- sketches on drawings

# line class of a sketch entity -> drawing layer (render.py)
DRAWING_LAYER = {"continuous": "visible", "hidden": "hidden", "chain": "chain", "dot": "hidden"}
_LAYER_INDEX = {"line": 5, "circle": 4, "arc": 6, "poly": 2, "solid": 2}


def _to_drawing_layer(p):
    i = _LAYER_INDEX.get(p[0])
    if i is None or not (isinstance(p[i], str) and p[i].startswith("lw:")):
        return p
    cls = p[i].split(":")[-1]
    return p[:i] + (DRAWING_LAYER.get(cls, "visible"),) + p[i + 1:]


def drawing_prims(entry, mp, cfg):
    """Sheet primitives of a sketch made on a drawing. entry: {"doc": sketch record, "anns": resolved dimensions
    and notes (annotate.py schema, sketch coordinates)}. mp: view map [cx, cy, f, bx, by, ...] for a sketch on a
    view (view coordinates, model mm; paper = c + f * (x - b)), None for a sketch on the sheet (paper mm).
    Lines go to the drawing layers visible, hidden and chain by their line type."""
    sk = entry.get("doc") or {}
    cx, cy, f, bx, by = (mp[:5] if mp else (0.0, 0.0, 1.0, 0.0, 0.0))
    xf = _Xf(f, cx - f * bx, cy - f * by)
    out = [_to_drawing_layer(_xform_prim(p, xf)) for p in model_prims(sk, cfg)]
    anns = []
    for a in entry.get("anns") or []:
        a = dict(a)
        a["view"] = "sketch"
        anns.append(a)
    if anns:
        out += annotate.render(anns, {"sketch": [cx, cy, f, bx, by]}, cfg)
    return out


def dim_prims(anns, cfg, scale):
    """Annotation primitives in paper mm for model coordinates multiplied by scale."""
    for a in anns:
        a["view"] = "sketch"
    return annotate.render(anns, {"sketch": [0.0, 0.0, scale, 0.0, 0.0]}, cfg)


# --------------------------------------------------------------------------- sheet

def sheet_primitives(sk, cfg, sheet, fields, base_dir):
    """Frame and title block primitives (paper mm) and the title used."""
    from .drawing import field_values
    s = float(sk.get("scale", 1.0) or 1.0)
    vals = field_values(cfg, sk.get("name", "sketch"), 0.0, s, fields)
    return tbk.sheet_primitives(cfg, sheet, vals, True, base_dir), vals.get("Title", sk.get("name", "sketch"))


def sheet_svg(sk, cfg, sheet, title_block, fields, base_dir):
    """SVG of the empty sheet (frame and title block) for the editor, with the drawing area."""
    W, H = tbk.sheet_size(cfg, sheet)
    prims = []
    if title_block:
        prims, _ = sheet_primitives(sk, cfg, sheet, fields, base_dir)
        area = tbk.drawing_area(cfg, sheet)
    else:
        area = (10.0, 10.0, W - 10.0, H - 10.0)
    svg = render.to_svg({"size": (W, H), "prims": prims}, cfg)
    return {"size": [W, H], "area": list(area), "svg": svg}


# --------------------------------------------------------------------------- PDF

def to_pdf(sk, anns, cfg, opts, fields):
    s = float(sk.get("scale", 1.0) or 1.0)
    geo = [_xform_prim(p, _Xf(s, 0.0, 0.0)) for p in model_prims(sk, cfg)]
    dims = dim_prims(anns, cfg, s)
    pts = []
    for e, _ in visible_entities(sk):
        pts += [(x * s, y * s) for x, y in entity_points(e)]
    for p in render.flatten(dims):
        if p[0] == "line":
            pts += [(p[1], p[2]), (p[3], p[4])]
        elif p[0] == "rtext":
            pts += [(p[1] - annotate.text_width(p[4], p[3]), p[2]), (p[1] + annotate.text_width(p[4], p[3]), p[2] + p[3])]
    x0, y0, x1, y1 = _bbox(pts)
    mode = opts.get("mode", "extents")
    margin = 10.0
    sheet_prims = []
    title = sk.get("name", "sketch")
    if mode == "sheet":
        sheet = opts.get("sheet", "A3")
        W, H = tbk.sheet_size(cfg, sheet)
        if opts.get("title_block", True):
            sheet_prims, title = sheet_primitives(sk, cfg, sheet, fields, opts.get("base_dir", ""))
        origin = opts.get("origin")
        if origin is not None:
            # paper = (model - origin) * scale
            ox, oy = -float(origin[0]) * s, -float(origin[1]) * s
        else:
            if opts.get("title_block", True):
                ax0, ay0, ax1, ay1 = tbk.drawing_area(cfg, sheet)
            else:
                ax0, ay0, ax1, ay1 = margin, margin, W - margin, H - margin
            ox = (ax0 + ax1) / 2.0 - (x0 + x1) / 2.0
            oy = (ay0 + ay1) / 2.0 - (y0 + y1) / 2.0
    else:
        W, H = (x1 - x0) + 2 * margin, (y1 - y0) + 2 * margin
        ox, oy = margin - x0, margin - y0
    sh = _Xf(1.0, ox, oy)
    prims = sheet_prims + [_xform_prim(p, sh) for p in geo] + [_xform_prim(p, sh) for p in dims]
    d = {"name": sk.get("name", "sketch"), "size": (W, H), "prims": prims, "values": {"Title": title}}
    return render.to_pdf([d], cfg)


# --------------------------------------------------------------------------- DXF

def to_dxf(sk, anns, cfg, opts=None, fields=None):
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    doc = ezdxf.new("R2010", setup=True)
    ins = int(sk.get("insunits", 4) or 0)
    doc.header["$INSUNITS"] = ins
    doc.header["$MEASUREMENT"] = 0 if ins in (1, 2) else 1
    for lt in sk.get("linetypes") or []:
        nm = lt["name"]
        if nm in doc.linetypes:
            continue
        pat = [float(v) for v in lt.get("pattern") or []]
        if not pat:
            continue
        elems = [v if i % 2 == 0 else -v for i, v in enumerate(pat)]
        try:
            doc.linetypes.add(nm, pattern=[sum(abs(v) for v in elems)] + elems,
                              description=lt.get("description", ""))
        except Exception:
            pass
    for lay in sk.get("layers") or []:
        nm = lay["name"]
        lt = lay.get("linetype") or "Continuous"
        if lt not in doc.linetypes:
            lt = "Continuous"
        attrs = {"color": int(lay.get("aci", 7) or 7), "linetype": lt}
        if (lay.get("lineweight") or -1) > 0:
            attrs["lineweight"] = int(round(lay["lineweight"] * 100))
        if nm in doc.layers:
            L = doc.layers.get(nm)
            for k, v in attrs.items():
                L.dxf.set(k, v)
        else:
            L = doc.layers.add(nm, **attrs)
        if not lay.get("on", True):
            L.off()
    if "DIM" not in doc.layers:
        doc.layers.add("DIM", color=7, lineweight=25)
    msp = doc.modelspace()
    align = {"start": TextEntityAlignment.LEFT, "middle": TextEntityAlignment.CENTER,
             "end": TextEntityAlignment.RIGHT}
    for e in sk.get("entities") or []:
        if e.get("constr"):
            continue
        at = {"layer": e.get("layer", "0")}
        if e.get("aci") is not None:
            at["color"] = int(e["aci"])
        lt = e.get("linetype")
        if lt and lt in doc.linetypes:
            at["linetype"] = lt
        t = e["t"]
        if t == "line":
            msp.add_line((e["x1"], e["y1"]), (e["x2"], e["y2"]), dxfattribs=at)
        elif t == "circle":
            msp.add_circle((e["cx"], e["cy"]), e["r"], dxfattribs=at)
        elif t == "arc":
            msp.add_arc((e["cx"], e["cy"]), e["r"], e["a0"], e["a1"], dxfattribs=at)
        elif t == "point":
            msp.add_point((e["x"], e["y"]), dxfattribs=at)
        elif t == "ellipse":
            r = math.radians(float(e.get("rot", 0) or 0))
            rx, ry = float(e["rx"]), float(e["ry"])
            a0, a1 = math.radians(float(e.get("a0", 0) or 0)), math.radians(float(e.get("a1", 0) or 0))
            if _ellipse_closed(e):
                a0, a1 = 0.0, 2 * math.pi
            if rx >= ry:
                major = (rx * math.cos(r), rx * math.sin(r))
                ratio = ry / rx if rx else 1.0
            else:
                # DXF major axis must be the longer one: along the local y direction, parameters shifted
                major = (-ry * math.sin(r), ry * math.cos(r))
                ratio = rx / ry
                a0, a1 = a0 - math.pi / 2, a1 - math.pi / 2
            if _ellipse_closed(e):
                a0, a1 = 0.0, 2 * math.pi
            else:
                span = (a1 - a0) % (2 * math.pi)
                a0 = a0 % (2 * math.pi)
                a1 = a0 + span
            msp.add_ellipse((e["cx"], e["cy"]), major_axis=major, ratio=ratio, start_param=a0, end_param=a1, dxfattribs=at)
        elif t == "poly" and e.get("fill") and len(e["pts"]) in (3, 4):
            q = [tuple(p) for p in e["pts"]]
            q = q if len(q) == 4 else q + [q[2]]
            msp.add_solid([q[0], q[1], q[3], q[2]], dxfattribs=at)
        elif t == "poly":
            msp.add_lwpolyline([tuple(p) for p in e["pts"]], close=bool(e.get("closed")), dxfattribs=at)
        elif t == "spline" and e.get("t0") is None and e.get("t1") is None:
            fit = [tuple(p) for p in e["pts"]]
            if e.get("closed"):
                fit = fit + [fit[0]]
            sp = msp.add_spline(fit_points=fit, degree=3, dxfattribs=at)
            if e.get("closed"):
                sp.closed = True
        elif t == "spline":
            # a trimmed spline: fitted through sampled points of the kept range
            msp.add_spline(fit_points=spline_pts_e(e, 6), degree=3, dxfattribs=at)
        elif t == "conic" and e.get("t0") is None and e.get("t1") is None:
            rho = min(0.999, max(0.001, float(e.get("rho", 0.5) or 0.5)))
            msp.add_rational_spline([(e["x0"], e["y0"]), (e["xt"], e["yt"]), (e["x1"], e["y1"])], [1.0, rho / (1.0 - rho), 1.0], degree=2, dxfattribs=at)
        elif t == "conic":
            msp.add_spline(fit_points=conic_pts(e, 24), degree=3, dxfattribs=at)
        elif t == "text":
            r = math.radians(e.get("rot", 0.0))
            for i, s in enumerate(str(e["text"]).split("\n")):
                if not s:
                    continue
                d = i * LINE_SPACING * e["h"]
                txt = msp.add_text(s, height=e["h"], rotation=e.get("rot", 0.0), dxfattribs=dict(at))
                txt.set_placement((e["x"] + math.sin(r) * d, e["y"] - math.cos(r) * d),
                                  align=align.get(e.get("anchor", "start"), TextEntityAlignment.LEFT))
    # dimensions: rendered at paper size for the sketch scale, written in model units
    s = float(sk.get("scale", 1.0) or 1.0)
    back = _Xf(1.0 / s, 0.0, 0.0)
    for g in dim_prims(anns, cfg, s):
        for q in render.flatten([_xform_prim(g, back)]):
            at = {"layer": "DIM"}
            k = q[0]
            if k == "line":
                msp.add_line((q[1], q[2]), (q[3], q[4]), dxfattribs=at)
            elif k == "arc":
                msp.add_arc((q[1], q[2]), q[3], q[4], q[5], dxfattribs=at)
            elif k == "solid":
                pts = q[1]
                r4 = pts if len(pts) == 4 else [pts[0], pts[1], pts[2], pts[2]]
                msp.add_solid([r4[0], r4[1], r4[3], r4[2]], dxfattribs=at)
            elif k == "rtext" and q[4]:
                txt = msp.add_text(q[4], height=q[3], rotation=q[6], dxfattribs=at)
                txt.set_placement((q[1], q[2]), align=align.get(q[5], TextEntityAlignment.LEFT))
    opts = opts or {}
    if opts.get("mode") == "sheet" and opts.get("title_block") and opts.get("origin") is not None:
        # frame and title block at drawing scale: model = origin + paper / scale
        sheet_prims, _ = sheet_primitives(sk, cfg, opts.get("sheet", "A3"), fields or {}, opts.get("base_dir", ""))
        o = opts["origin"]
        to_model = _Xf(1.0 / s, float(o[0]), float(o[1]))
        for name in ("FRAME", "TITLE", "TEXT"):
            if name not in doc.layers:
                doc.layers.add(name, color=7)
        for q in sheet_prims:
            if q[0] == "image":
                continue
            q = _xform_prim(q, to_model)
            k = q[0]
            lay = {"frame": "FRAME", "title": "TITLE", "chain": "TITLE"}.get(q[-1] if k != "text" else "text", "TITLE")
            if k == "line":
                msp.add_line((q[1], q[2]), (q[3], q[4]), dxfattribs={"layer": lay})
            elif k == "circle":
                msp.add_circle((q[1], q[2]), q[3], dxfattribs={"layer": lay})
            elif k == "poly":
                msp.add_lwpolyline(q[1], close=bool(q[3]), dxfattribs={"layer": {"frame": "FRAME"}.get(q[2], "TITLE")})
            elif k == "text" and q[4]:
                txt = msp.add_text(str(q[4]), height=q[3], dxfattribs={"layer": "TEXT"})
                txt.set_placement((q[1], q[2]), align=align.get(q[6], TextEntityAlignment.LEFT))
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")
