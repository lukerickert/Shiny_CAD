# -*- coding: utf-8 -*-
"""Tool bits of the CAM tab: the tool table (config.json "cam_tools"), the profile of each shape, the tool solid
and the solid swept by a tool along a straight move (OpenCascade).

Tool bit:
  {"id", "name", "shape": "endmill" | "ballend" | "bullnose" | "vbit" | "chamfer" | "drill" | "dovetail" | "tapered" |
   "threadmill" (single form: a tooth of the thread "angle" between the neck radius and D/2) | "tslot" (a disc of
   diameter D and thickness "height" on a neck smaller than D) | "custom" ("profile": [[r, z], ...] mm, the cutting
   edge from the tip up: z from 0 and never down, r >= 0; D and the cutting height are set from it by normalize),
   "d": diameter mm (dovetail: the large diameter; vbit: the diameter at the top of the cutting part; tapered: the
   diameter at the top of the flutes, set from the tip radius, the taper and the cutting height by normalize),
   "corner": corner radius mm (bullnose; tapered: the radius of the ball tip), "angle": deg (vbit: the included tip
   angle; chamfer: the included angle; drill: the point angle; dovetail: the angle between the flank and the base
   plane; tapered: the taper angle per side), "tip": mm (vbit, chamfer:
   diameter of the flat tip), "height": cutting height mm (the flank height of a dovetail cutter),
   "neck": neck diameter mm, "neck_length": mm, "shank": shank diameter mm, "shank_length": mm, "flutes": n,
   "length": overall length mm (information), "material": text (information), "tool_material": "carbide" | "hss"
   (feeds.py),
   "feed": mm/min, "plunge": mm/min, "rpm": 1/min (the defaults of a tool controller made from the bit)}
The key "type" of older tables is read as "shape".
"""
import math

SHAPES = ("endmill", "ballend", "bullnose", "vbit", "chamfer", "drill", "dovetail", "tapered", "threadmill", "tslot", "custom")
SHAPE_NAMES = {"endmill": "End mill", "ballend": "Ball end mill", "bullnose": "Bull nose", "vbit": "V bit",
               "chamfer": "Chamfer", "drill": "Drill", "dovetail": "Dovetail", "tapered": "Tapered ball nose", "threadmill": "Thread mill",
               "tslot": "T-slot cutter", "custom": "Custom profile"}
DEFAULT_TOOLS = [
    {"id": "T1", "name": "End mill 6 mm", "shape": "endmill", "d": 6.0, "height": 18.0, "neck": 6.0, "neck_length": 0.0,
     "shank": 6.0, "shank_length": 30.0, "flutes": 2, "feed": 800.0, "plunge": 200.0, "rpm": 12000},
    {"id": "T2", "name": "Dovetail 10 mm 60 deg 4T", "shape": "dovetail", "d": 10.0, "angle": 60.0, "height": 4.0,
     "neck": 5.0, "neck_length": 6.0, "shank": 10.0, "shank_length": 30.0, "flutes": 4, "feed": 300.0, "plunge": 100.0,
     "rpm": 8000},
    {"id": "T3", "name": "Drill 6 mm", "shape": "drill", "d": 6.0, "angle": 118.0, "height": 30.0, "neck": 6.0,
     "neck_length": 0.0, "shank": 6.0, "shank_length": 20.0, "flutes": 2, "feed": 150.0, "plunge": 150.0, "rpm": 3000},
    {"id": "T4", "name": "Ball end mill 6 mm", "shape": "ballend", "d": 6.0, "height": 12.0, "neck": 6.0, "neck_length": 0.0,
     "shank": 6.0, "shank_length": 30.0, "flutes": 2, "feed": 600.0, "plunge": 200.0, "rpm": 12000},
    {"id": "T5", "name": "V bit 90 deg 6 mm", "shape": "vbit", "d": 6.0, "angle": 90.0, "tip": 0.2, "height": 3.0,
     "neck": 6.0, "neck_length": 0.0, "shank": 6.0, "shank_length": 30.0, "flutes": 2, "feed": 400.0, "plunge": 150.0,
     "rpm": 12000},
]

SERIES = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0)


def _shank(d):
    """Metric shank of a standard end mill of diameter d mm."""
    return 3.0 if d <= 3.0 else 6.0 if d <= 6.0 else d


def _fmt(v):
    return ("%g" % v)


def library():
    """The standard tool library (metric): flat end mills 2 and 3 flute and ball end mills 2 flute of the series
    1 to 12 mm, single flute end mills 3, 4, 6 mm, chamfer mills 90 and 60 deg 6 and 12 mm, tapered ball nose
    mills (tip radius 0.25 to 1 mm, taper 1.5, 3 and 5 deg per side, 6 mm shank) and a spoilboard surfacing tool
    (D set by hand). Each entry has "group"; feed, plunge and rpm from feeds.calc in wrought aluminium."""
    from . import feeds as FS
    out = []

    def add(group, t):
        t = normalize(dict(t, group=group, tool_material="carbide"))
        try:
            r = FS.calc(t, "al_wrought" if group != "Spoilboard" else "wd_mdf", None, None, min(t["d"] / 2.0, 3.0))
            t.update(feed=float(r["feed"]), plunge=float(r["plunge"]), rpm=float(r["rpm"]))
        except ValueError:
            pass
        out.append(t)

    for d in SERIES:
        sh = _shank(d)
        neck = round(d - 0.1, 2) if sh > d else d
        nl = round(3 * d, 2) if sh > d else 0.0
        h = min(26.0, max(3.0, 3 * d))
        for z in (2, 3):
            if z == 3 and d < 2:
                continue
            add("Flat end mills", {"id": "EM%d-%s" % (z, _fmt(d)), "name": "End mill %s mm %dF" % (_fmt(d), z), "shape": "endmill", "d": d, "height": h,
                                   "neck": neck, "neck_length": nl, "shank": sh, "shank_length": 30.0, "flutes": z})
        add("Ball end mills", {"id": "BE2-%s" % _fmt(d), "name": "Ball end mill %s mm 2F" % _fmt(d), "shape": "ballend", "d": d, "height": h,
                               "neck": neck, "neck_length": nl, "shank": sh, "shank_length": 30.0, "flutes": 2})
    for d in (3.0, 4.0, 6.0):
        add("Single flute end mills", {"id": "EM1-%s" % _fmt(d), "name": "Single flute %s mm" % _fmt(d), "shape": "endmill", "d": d, "height": 3 * d,
                                       "neck": d, "neck_length": 0.0, "shank": d, "shank_length": 30.0, "flutes": 1})
    for ang in (90.0, 60.0):
        for d in (6.0, 12.0):
            add("Chamfer mills", {"id": "CH%d-%s" % (ang, _fmt(d)), "name": "Chamfer %d deg %s mm" % (ang, _fmt(d)), "shape": "chamfer", "d": d, "angle": ang,
                                  "tip": 0.0, "height": d / 2.0 / math.tan(math.radians(ang / 2.0)) + 1.0, "neck": d, "neck_length": 0.0, "shank": d,
                                  "shank_length": 30.0, "flutes": 3 if d > 6 else 2})
    for rb in (0.25, 0.5, 0.75, 1.0):
        for a in (1.5, 3.0, 5.0):
            add("Tapered ball nose", {"id": "TB-R%s-%s" % (_fmt(rb), _fmt(a)), "name": "Tapered ball R%s %s deg" % (_fmt(rb), _fmt(a)), "shape": "tapered",
                                      "corner": rb, "angle": a, "height": 20.0, "neck": 6.0, "neck_length": 0.0, "shank": 6.0, "shank_length": 30.0, "flutes": 2})
    for d, nk in ((4.7, 3.0), (6.0, 4.0), (8.0, 6.0)):
        add("Thread mills", {"id": "TM60-%s" % _fmt(d), "name": "Thread mill 60 deg D%s" % _fmt(d), "shape": "threadmill", "d": d, "angle": 60.0,
                             "height": 2.0, "neck": nk, "neck_length": 15.0, "shank": 6.0 if d <= 6 else 8.0, "shank_length": 30.0, "flutes": 3})
    add("Spoilboard", {"id": "SB-25", "name": "Spoilboard surfacing (set D)", "shape": "endmill", "d": 25.0, "height": 6.0, "neck": 12.0,
                       "neck_length": 10.0, "shank": 12.0, "shank_length": 30.0, "flutes": 2})
    return out


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


_OLD_SHAPES = {"tapered_ball": "tapered", "taperedball": "tapered", "ball": "ballend", "ballnose": "ballend", "end_mill": "endmill", "flat": "endmill", "v": "vbit", "v_bit": "vbit", "engraver": "vbit"}


def shape_of(tool):
    """Shape of a tool bit ("shape", or "type" of older tables, with the older names mapped)."""
    s = str(tool.get("shape") or tool.get("type") or "endmill")
    s = _OLD_SHAPES.get(s, s)
    return s if s in SHAPES else "endmill"


def radius(tool):
    return _f(tool.get("d")) / 2.0


def tip_length(tool):
    """Height of the point of a drill (0 for the other shapes)."""
    if shape_of(tool) != "drill":
        return 0.0
    R = radius(tool)
    return R / math.tan(math.radians(_f(tool.get("angle"), 118.0) / 2.0))


def tool_profile(tool):
    """Half profile of the tool as (r, z) points from the axis at the tip up the cutting part, and the neck and
    shank parts: (cutting: [(r, z)...], body: [(r, z)...]). z = 0 at the lowest point of the tool."""
    s = shape_of(tool)
    R = radius(tool)
    H = _f(tool.get("height"), 10.0)
    rn = _f(tool.get("neck"), 2 * R) / 2.0
    Ln = _f(tool.get("neck_length"), 0.0)
    rs = _f(tool.get("shank"), max(2 * rn, 2 * R)) / 2.0
    Ls = _f(tool.get("shank_length"), 30.0)
    if s == "custom":
        pts = custom_points(tool)
        H = pts[-1][1]
        R = max(r for r, z in pts)
        cut = ([(0.0, 0.0)] if pts[0][0] > 1e-9 else []) + pts
        rn = min(rn, R) if rn > 0 else pts[-1][0]
        if abs(cut[-1][0] - rn) > 1e-9:
            cut.append((rn, H))
        z0 = H
        body = [(rn, z0), (rn, z0 + Ln), (rs, z0 + Ln), (rs, z0 + Ln + Ls)]
        if Ln <= 0:
            body = [(rn, z0), (rs, z0), (rs, z0 + Ls)]
        return cut, body
    if R <= 0:
        raise ValueError("tool %s: the diameter is 0" % tool.get("id"))
    if s == "tslot" and rn >= R - 1e-9:
        raise ValueError("tool %s: the neck diameter %.3f mm must be smaller than the disc diameter %.3f mm" % (tool.get("id"), 2 * rn, 2 * R))
    if s == "dovetail":
        ang = _f(tool.get("angle"), 60.0)
        if not 10.0 <= ang <= 89.0:
            raise ValueError("tool %s: the dovetail angle must be between 10 and 89 deg" % tool.get("id"))
        r_top = R - H / math.tan(math.radians(ang))
        if r_top <= 0.05:
            raise ValueError("tool %s: the cutting height %.2f mm is more than the flank allows (%.2f mm)"
                             % (tool.get("id"), H, (R - 0.05) * math.tan(math.radians(ang))))
        if rn > r_top + 1e-9:
            rn = r_top
        cut = [(0.0, 0.0), (R, 0.0), (r_top, H), (rn, H)]
        z0 = H
    elif s == "ballend":
        n = 8
        cut = [(0.0, 0.0)] + [(R * math.sin(math.pi / 2 * i / n), R - R * math.cos(math.pi / 2 * i / n)) for i in range(1, n + 1)]
        cut += [(R, max(H, R)), (rn, max(H, R))]
        z0 = max(H, R)
    elif s == "bullnose":
        rc = min(max(_f(tool.get("corner"), 1.0), 0.0), R)
        n = 6
        cut = [(0.0, 0.0), (R - rc, 0.0)] + [(R - rc + rc * math.sin(math.pi / 2 * i / n), rc - rc * math.cos(math.pi / 2 * i / n)) for i in range(1, n + 1)]
        cut += [(R, max(H, rc)), (rn, max(H, rc))]
        z0 = max(H, rc)
    elif s in ("vbit", "chamfer"):
        ang = _f(tool.get("angle"), 90.0)
        rt = max(0.0, _f(tool.get("tip"), 0.0) / 2.0)
        hcone = (R - rt) / math.tan(math.radians(ang / 2.0))
        cut = [(0.0, 0.0), (rt, 0.0), (R, hcone), (R, max(H, hcone)), (rn, max(H, hcone))]
        z0 = max(H, hcone)
    elif s == "tapered":
        rb, a, zt = _taper(tool)
        rt = rb * math.cos(a)
        n = 8
        cut = [(0.0, 0.0)] + [(rb * math.sin((math.pi / 2 - a) * i / n), rb - rb * math.cos((math.pi / 2 - a) * i / n)) for i in range(1, n + 1)]
        Ht = max(H, zt + 1e-3)
        R = rt + (Ht - zt) * math.tan(a)
        cut += [(R, Ht), (min(rn, R) if rn > 0 else R, Ht)]
        z0 = Ht
    elif s == "threadmill":
        # a single-form thread mill: a tooth of the thread angle at the bottom of the neck
        ang = _f(tool.get("angle"), 60.0)
        if not 20.0 <= ang <= 120.0:
            raise ValueError("tool %s: the thread angle must be between 20 and 120 deg" % tool.get("id"))
        r0 = min(rn, R * 0.9) if rn > 0 else R * 0.6
        h = 2.0 * (R - r0) * math.tan(math.radians(ang / 2.0))
        cut = [(0.0, 0.0), (r0, 0.0), (R, h / 2.0), (r0, h), (r0, max(H, h)), (rn, max(H, h))]
        z0 = max(H, h)
    elif s == "drill":
        tip = tip_length(tool)
        cut = [(0.0, 0.0), (R, tip), (R, H + tip), (rn, H + tip)]
        z0 = H + tip
    else:
        cut = [(0.0, 0.0), (R, 0.0), (R, H), (rn, H)]
        z0 = H
    body = [(rn, z0), (rn, z0 + Ln), (rs, z0 + Ln), (rs, z0 + Ln + Ls)]
    if Ln <= 0:
        body = [(rn, z0), (rs, z0), (rs, z0 + Ls)]
    return cut, body


def custom_points(tool):
    """The points (r, z) of a custom profile, checked: at least two, z starting at 0 and never going down, r >= 0, a
    largest radius above 0 (ValueError otherwise)."""
    raw = tool.get("profile") or []
    pts = []
    for p in raw:
        try:
            r, z = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            raise ValueError("tool %s: a profile point is not two numbers" % tool.get("id"))
        pts.append((r, z))
    if len(pts) < 2:
        raise ValueError("tool %s: the custom profile needs at least two points (r, z)" % tool.get("id"))
    if abs(pts[0][1]) > 1e-9:
        raise ValueError("tool %s: the custom profile starts at z 0 (the tip)" % tool.get("id"))
    for (r0, z0), (r1, z1) in zip(pts, pts[1:]):
        if z1 < z0 - 1e-9:
            raise ValueError("tool %s: the custom profile goes down from z %g to z %g mm" % (tool.get("id"), z0, z1))
    if any(r < 0 for r, z in pts) or max(r for r, z in pts) <= 0:
        raise ValueError("tool %s: the radii of the custom profile must be 0 or more, the largest above 0" % tool.get("id"))
    return pts


def cutting_height(tool):
    cut, _ = tool_profile(tool)
    return cut[-1][1]


def tool_length(tool):
    cut, body = tool_profile(tool)
    return body[-1][1]


def bottom_offset(tool, d):
    """Height of the cutting edge above the lowest point of the tool at the distance d from the axis (the tool
    resting on a point at that distance stands this much lower than on a point under its axis). None beyond
    the radius."""
    s = shape_of(tool)
    R = radius(tool)
    if d > R + 1e-9:
        return None
    if s == "ballend":
        return R - math.sqrt(max(0.0, R * R - d * d))
    if s == "bullnose":
        rc = min(max(_f(tool.get("corner"), 1.0), 0.0), R)
        if d <= R - rc:
            return 0.0
        e = d - (R - rc)
        return rc - math.sqrt(max(0.0, rc * rc - e * e))
    if s in ("vbit", "chamfer"):
        rt = max(0.0, _f(tool.get("tip"), 0.0) / 2.0)
        ang = _f(tool.get("angle"), 90.0)
        return 0.0 if d <= rt else (d - rt) / math.tan(math.radians(ang / 2.0))
    if s == "drill":
        return d / math.tan(math.radians(_f(tool.get("angle"), 118.0) / 2.0))
    if s in ("dovetail", "threadmill", "tslot"):
        return 0.0
    if s == "custom":
        cut, _ = tool_profile(tool)
        best = None
        for (r0, z0), (r1, z1) in zip(cut, cut[1:]):
            lo, hi = min(r0, r1), max(r0, r1)
            if lo - 1e-9 <= d <= hi + 1e-9:
                z = z0 if hi - lo < 1e-12 else z0 + (z1 - z0) * (d - r0) / (r1 - r0)
                best = z if best is None else min(best, z)
        return best
    if s == "tapered":
        rb, a, zt = _taper(tool)
        if d <= rb * math.cos(a):
            return rb - math.sqrt(max(0.0, rb * rb - d * d))
        return zt + (d - rb * math.cos(a)) / math.tan(a)
    return 0.0


def _taper(tool):
    """(ball tip radius, taper angle per side rad, height of the tangent point of the ball and the cone) of a tapered
    ball nose."""
    rb = max(0.01, _f(tool.get("corner"), 0.25))
    a = math.radians(min(30.0, max(0.1, _f(tool.get("angle"), 3.0))))
    return rb, a, rb - rb * math.sin(a)


def taper_diameter(tool):
    """Diameter at the top of the flutes of a tapered ball nose."""
    rb, a, zt = _taper(tool)
    Ht = max(_f(tool.get("height"), 10.0), zt + 1e-3)
    return 2.0 * (rb * math.cos(a) + (Ht - zt) * math.tan(a))


def check(tool):
    """Raises ValueError for a tool that cannot be built."""
    tool_profile(tool)
    return True


def normalize(tool):
    """Tool record with "shape" (from "type" of older tables) and numbers as floats."""
    t = dict(tool)
    t["shape"] = shape_of(t)
    t.pop("type", None)
    for k in ("d", "corner", "angle", "tip", "height", "neck", "neck_length", "shank", "shank_length", "feed", "plunge", "rpm", "length"):
        if k in t and t[k] not in (None, ""):
            t[k] = _f(t[k])
    if t["shape"] == "tapered":
        t["d"] = round(taper_diameter(t), 4)
    if t["shape"] == "custom" and t.get("profile"):
        try:
            pts = [[_f(p[0]), _f(p[1])] for p in t["profile"]]
        except (TypeError, IndexError):
            pts = []
        t["profile"] = pts
        if pts:
            t["d"] = round(2 * max(p[0] for p in pts), 4)
            t["height"] = round(pts[-1][1], 4)
    return t


# --------------------------------------------------------------------------- solids

def _profile_face(pts, at, u):
    """Planar face of a half profile [(r, z)] closed along the axis, in the plane through at spanned by the
    horizontal unit vector u and Z; r along u."""
    from build123d import Face, Wire, Vector
    P = [Vector(at) + Vector(0, 0, pts[0][1])] + [Vector(at) + Vector(u) * r + Vector(0, 0, z) for r, z in pts]
    P.append(Vector(at) + Vector(0, 0, pts[-1][1]))
    Q = []
    for q in P:
        if not Q or (q - Q[-1]).length > 1e-9:
            Q.append(q)
    if len(Q) > 1 and (Q[0] - Q[-1]).length < 1e-9:
        Q.pop()
    return Face(Wire.make_polygon(Q, close=True))


def _section_face(pts, at, u):
    """Full axial section (both sides of the axis) of a profile [(r, z)] as a planar face."""
    from build123d import Face, Wire, Vector
    right = [Vector(at) + Vector(u) * r + Vector(0, 0, z) for r, z in pts]
    left = [Vector(at) - Vector(u) * r + Vector(0, 0, z) for r, z in reversed(pts)]
    P = []
    for q in right + left:
        if not P or (q - P[-1]).length > 1e-9:
            P.append(q)
    if (P[0] - P[-1]).length < 1e-9:
        P.pop()
    return Face(Wire.make_polygon(P, close=True))


def tool_solid(tool, at, which="cut"):
    """Solid of the tool with its lowest point at the point at (axis +Z): "cut" the cutting part, "body" the neck
    and shank, "all" both."""
    from build123d import Solid, Axis, Vector
    cut, body = tool_profile(tool)
    at = Vector(at)
    ax = Axis(at, (0, 0, 1))
    u = (1, 0, 0)
    if which == "cut":
        return Solid.revolve(_profile_face(cut, at, u), 360, ax)
    if which == "body":
        return Solid.revolve(_profile_face(body, at, u), 360, ax)
    return Solid.revolve(_profile_face(cut + body[1:], at, u), 360, ax)


def fuse(solids, fuzzy=1e-6):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from build123d import Shape, Compound
    from ..surfaces import _shape_list
    allp = []
    for x in solids:
        allp += list(x.solids()) if hasattr(x, "solids") else [x]
    if len(allp) == 1:
        return allp[0]
    args, tls = _shape_list(), _shape_list()
    args.Append(allp[0].wrapped)
    for x in allp[1:]:
        tls.Append(x.wrapped)
    op = BRepAlgoAPI_Fuse()
    op.SetArguments(args)
    op.SetTools(tls)
    op.SetFuzzyValue(fuzzy)
    op.Build()
    if not op.IsDone():
        raise ValueError("the solids could not be fused")
    res = Shape.cast(op.Shape()).clean()
    sols = list(res.solids())
    if not sols:
        raise ValueError("the fused solid is empty")
    return sols[0] if len(sols) == 1 else Compound(children=sols)


def sweep_line(tool, p, q, which="cut"):
    """Solid swept by the tool moved (axis +Z, no turning) from p to q: a horizontal line (the axial section
    extruded plus the tool at both ends) or a vertical line (the envelope of the profile along the travel)."""
    from build123d import Solid, Vector
    p, q = Vector(p), Vector(q)
    d = q - p
    if d.length < 1e-9:
        return tool_solid(tool, p, which)
    cut, body = tool_profile(tool)
    pts = {"cut": cut, "body": body}.get(which) or (cut + body[1:])
    dn = Vector(d.X, d.Y, 0)
    if dn.length < 1e-9:
        return _vertical_sweep(pts, p, q)
    if abs(d.Z) > 1e-9:
        raise ValueError("a sloping move cannot be swept")
    u = Vector(0, 0, 1).cross(dn).normalized()
    pieces = [Solid.extrude(_section_face(pts, p, u), d), tool_solid(tool, p, which), tool_solid(tool, q, which)]
    return fuse(pieces)


def _radius_at(pts, z):
    """Largest radius of the profile polyline [(r, z)] at the height z (0 outside its range)."""
    best = 0.0
    for (r0, z0), (r1, z1) in zip(pts, pts[1:]):
        lo, hi = min(z0, z1), max(z0, z1)
        if z < lo - 1e-9 or z > hi + 1e-9:
            continue
        r = max(r0, r1) if hi - lo < 1e-9 else r0 + (r1 - r0) * (z - z0) / (z1 - z0)
        best = max(best, r)
    return best


def _vertical_sweep(pts, p, q, step=0.1):
    """Solid swept by a profile of revolution moved along a vertical line from p to q: the envelope radius at
    every height is the largest profile radius within the travel below it (sampled every step mm)."""
    from build123d import Solid, Axis, Vector
    lo = p if p.Z <= q.Z else q
    h = abs(q.Z - p.Z)
    ztop = max(z for _, z in pts)
    n = max(2, int(math.ceil((ztop + h) / step)))
    zs = [(ztop + h) * i / n for i in range(n + 1)]
    env = []
    for z in zs:
        m = 0.0
        s = max(0.0, z - ztop)
        while s <= min(h, z) + 1e-9:
            m = max(m, _radius_at(pts, z - s))
            s += step
        m = max(m, _radius_at(pts, z - min(h, z)))
        env.append(m)
    nz = [z for z, r in zip(zs, env) if r > 1e-9]
    prof = [(0.0, nz[0] if nz else 0.0)]
    for z, r in zip(zs, env):
        if r > 1e-9:
            prof.append((r, z))
    out = [prof[0]]
    for a, b in zip(prof[1:], prof[2:]):
        pa = out[-1]
        if abs((a[0] - pa[0]) * (b[1] - pa[1]) - (a[1] - pa[1]) * (b[0] - pa[0])) > 1e-7:
            out.append(a)
    out.append(prof[-1])
    if out[-1][0] > 1e-9:
        out.append((0.0, out[-1][1]))
    return Solid.revolve(_profile_face(out, Vector(lo), (1, 0, 0)), 360, Axis(Vector(lo), (0, 0, 1)))
