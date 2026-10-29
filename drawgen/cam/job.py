# -*- coding: utf-8 -*-
"""CAM job: the document, the tool controllers, the setup sheet, the heights and depths of the operations, the
stock and the machine zero, the run of the operations with the stock cut by the tool, the sanity check and the
job template.

Job document (<name>.cam.json):
  {"name", "source": {"type": "part", "name"},
   "stock": {"kind": "offsets" (the part bounding box with the margins "xneg", "xpos", "yneg", "ypos", "zneg",
       "zpos" mm) | "box" (explicit: "xmin", "ymin", "zmin", "xmax", "ymax", "zmax" mm) | "part_filled" (the part
       with the undercuts filled) | "step" ("path": a STEP file in the coordinates of the part, relative paths in
       the STEP folder of the project; "dx", "dy", "dz" mm and "rx", "ry", "rz" deg: the solid turned about the
       part origin (about X, then Y, then Z) and moved by the offset in part coordinates; then moved with the model
       placement); "material": workpiece material id of
       feeds.py},
   "placement": {"pos", "rot", "constraints"} (the part moved in the job coordinate system before everything else;
       placement.py),
   "origin": {"xy": "stock_min" | "stock_centre" | "part" | "point", "z": "stock_top" | "stock_bottom" | "part" | "point",
       "point": [x, y, z] (a picked vertex of the part, job coordinates)},
   "setup": {"clearance_offset" mm above the start depth, "safe_offset" mm above the start depth, "step_down" mm,
       "finish_depth" mm, "hrapid" mm/min, "vrapid" mm/min, "coolant": "none" | "flood" | "mist", machine:
       "rpm_min", "rpm_max", "rpm_rated", "power_kw", "feed_max" mm/min, "rigidity" %, "ramp_angle" deg} (setup sheet: the defaults of the
       operations and the spindle limits of the feeds and speeds calculator, feeds.py),
   "tools": [{"id", "name", "bit": tool bit id (tools.py), "number": tool number of the G-code, "hfeed" mm/min,
       "vfeed" mm/min, "rfeed" mm/min (ramp and helix entries; empty: the feed of the helix arcs, the plunge feed of
       a ramp), "rpm", "dir": "CW" | "CCW"}] (tool controllers),
   "post": "estlcam" | "generic", "output": {"folder", "name"},
   "operations": [operation, ...], "next"}

Operation (all types): {"id", "name", "type", "active": true, "tc": tool controller id, "comment",
   finishing (Pocket, Profile, Adaptive, Undercut; ops2d.finish_mode): "finish_mode": "off" | "level" | "separate",
   "finish_tc", "finish_feed", "finish_plunge", "finish_rpm", "finish_step" (mm), "finish_spring" (the last finish
   pass once more),
   "clearance_height", "safe_height", "start_depth", "final_depth", "step_down", "finish_depth" (mm, part
   coordinates; null: the default of the type), "dressups": [{"type", ...}], fields of the type}
Types: face, pocket, profile, drilling, helix, slot, engrave, deburr, vcarve, adaptive, thread (ops2d.py, adaptive.py,
   vcarve.py), pocket3d, surface, waterline (ops3d.py), undercut (ops2d.py), fixture, comment, stop, custom, hop
   ("height"), probe ("xmin".."ymax", "nx", "ny", "start_z", "depth", "feed", "output") (supplemental: no cut),
   copy, array (of another operation).
Dressups: tag, ramp, leadinout, dogbone, boundary, axismap (dressup.py).

Moves: [{"k": "rapid" | "plunge" | "feed" | "arc", "p": [x, y, z], "f" mm/min, arc: "c": [cx, cy], "cw"}] and the
   items {"k": "comment", "text"}, {"k": "stop", "optional"}, {"k": "custom", "text"}, {"k": "fixture", "g"},
   {"k": "dwell", "s"}, {"k": "hop", "z"}, {"k": "probe", "x", "y", "z0", "z1", "f"}, {"k": "probe_open", "name"},
   {"k": "probe_close"}; job coordinates. Drilling moves of a hole carry "cyc" (index into the record's "cycles":
   {"x", "y", "z", "r", "q", "p", "f"}); axis-mapped moves carry "a" (deg) and "amap" ("x" | "y").
"""
import hashlib
import json
import math
import threading

from . import tools as TB
from . import geom as G

DEFAULT_SETUP = {"clearance_offset": 5.0, "safe_offset": 3.0, "step_down": 2.0, "finish_depth": 0.0,
                 "hrapid": 3000.0, "vrapid": 1000.0, "coolant": "none",
                 "rpm_min": 6000.0, "rpm_max": 24000.0, "rpm_rated": 24000.0, "power_kw": 2.2, "feed_max": 5000.0,
                 "rigidity": 100.0, "ramp_angle": 3.0}
SUPPLEMENTAL = ("fixture", "comment", "stop", "custom", "hop", "probe")
DERIVED = ("copy", "array")
OP_NAMES = {"face": "Face", "pocket": "Pocket Shape", "profile": "Profile", "drilling": "Drilling", "helix": "Helix",
            "slot": "Slot", "engrave": "Engrave", "deburr": "Deburr", "vcarve": "Vcarve", "adaptive": "Adaptive",
            "pocket3d": "3D Pocket", "surface": "3D Surface", "waterline": "Waterline", "undercut": "Undercut",
            "fixture": "Fixture", "comment": "Comment", "stop": "Stop", "custom": "Custom", "copy": "Copy", "array": "Array",
            "thread": "Thread milling", "hop": "Hop", "probe": "Probe"}


def _f(v, default=0.0):
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


# --------------------------------------------------------------------------- document

def migrate(doc):
    """The document in the current form: stock margins, setup sheet, tool controllers from the tool ids of older
    documents, operation types and fields of older documents."""
    d = dict(doc or {})
    d.setdefault("name", "cam")
    d.setdefault("source", {"type": "part", "name": ""})
    st = dict(d.get("stock") or {})
    if st.get("kind") in (None, "box") and "xmin" not in st:
        m = _f(st.get("sides"), 1.0)
        st = {"kind": "offsets", "xneg": _f(st.get("xneg"), m), "xpos": _f(st.get("xpos"), m), "yneg": _f(st.get("yneg"), m),
              "ypos": _f(st.get("ypos"), m), "zneg": _f(st.get("zneg"), _f(st.get("bottom"), 0.0)), "zpos": _f(st.get("zpos"), _f(st.get("top"), 1.0))}
    d["stock"] = st
    d.setdefault("origin", {"xy": "stock_min", "z": "stock_top"})
    from . import placement as PL
    d["placement"] = PL.normalize(d.get("placement"))
    setup = dict(DEFAULT_SETUP)
    setup.update({k: v for k, v in (d.get("setup") or {}).items() if k in DEFAULT_SETUP})
    if "clearance" in d and "setup" not in d:
        setup["clearance_offset"] = _f(d["clearance"], 5.0)
    d["setup"] = setup
    d.setdefault("post", "estlcam")
    d.setdefault("output", {"folder": "", "name": ""})
    d.setdefault("next", 1)
    tcs = list(d.get("tools") or [])
    ops = []
    for op in d.get("operations") or []:
        op = dict(op)
        if op.get("type") == "drill":
            op["type"] = "drilling"
        if "active" not in op:
            op["active"] = not op.get("suppressed", False)
        op.pop("suppressed", None)
        if "tc" not in op and op.get("tool"):
            # a tool bit id of an older document: a tool controller for that bit
            tid = op.pop("tool")
            tc = next((t for t in tcs if t.get("bit") == tid), None)
            if tc is None:
                tc = {"id": "TC" + str(len(tcs) + 1), "name": tid, "bit": tid, "number": len(tcs) + 1,
                      "hfeed": op.get("feed"), "vfeed": op.get("plunge"), "rpm": op.get("rpm"), "dir": "CW"}
                tcs.append(tc)
            op["tc"] = tc["id"]
        op.setdefault("dressups", [])
        for k in ("clearance_height", "safe_height", "start_depth", "final_depth", "step_down", "finish_depth"):
            op.setdefault(k, None)
        if op.get("type") == "profile" and "tabs" in op and op.get("tabs"):
            # tabs of an older profile: a Tag dressup
            if not any(x.get("type") == "tag" for x in op["dressups"]):
                op["dressups"].append({"type": "tag", "count": int(_f(op.get("tabs"), 3)), "width": _f(op.get("tab_width"), 6.0),
                                       "height": _f(op.get("tab_height"), 2.0), "angle": 45.0})
            op.pop("tabs", None)
        if op.get("type") == "profile" and "ramp_angle" in op and _f(op.get("ramp_angle"), 0) > 0 and not any(x.get("type") == "ramp" for x in op["dressups"]):
            op["dressups"].append({"type": "ramp", "angle": _f(op.get("ramp_angle"), 3.0), "method": "ramp1"})
        if op.get("type") in ("pocket", "profile", "adaptive", "undercut") and op.get("finish_mode") not in ("off", "level", "separate"):
            from .ops2d import finish_mode
            op["finish_mode"] = finish_mode(op)
        if op.get("type") == "pocket":
            op.setdefault("pattern", "offset")
            if "stepover" in op and "stepover_pct" not in op:
                op["stepover_pct"] = None
        ops.append(op)
    d["tools"] = tcs
    d["operations"] = ops
    return d


def controller_of(doc, tcid):
    for t in doc.get("tools") or []:
        if t.get("id") == tcid:
            return t
    raise ValueError("tool controller %s is not in the job" % (tcid or "(none)"))


def bit_of(bits, bid):
    for t in bits or []:
        if t.get("id") == bid:
            return TB.normalize(t)
    raise ValueError("tool %s is not in the tool table" % (bid or "(none)"))


def controller_defaults(bit, n=1):
    """A tool controller for a tool bit."""
    return {"id": "TC%d" % n, "name": bit.get("name") or bit.get("id"), "bit": bit.get("id"), "number": n,
            "hfeed": _f(bit.get("feed"), 500.0), "vfeed": _f(bit.get("plunge"), 150.0), "rpm": _f(bit.get("rpm"), 10000.0), "dir": "CW"}


def feeds(op, tc):
    """(feed, plunge feed, rpm) of an operation: the operation's values when set, else the controller's."""
    feed = _f(op.get("feed"), 0) or _f(tc.get("hfeed"), 500.0)
    plunge = _f(op.get("plunge"), 0) or _f(tc.get("vfeed"), feed / 3.0)
    rpm = _f(op.get("rpm"), 0) or _f(tc.get("rpm"), 0.0)
    return feed, plunge, rpm


# --------------------------------------------------------------------------- stock and origin

def undercut_faces(shape):
    from .ops2d import undercut_faces as uf
    return uf(shape)


RESOLVE_PATH = None      # set by the server: a stock STEP path (relative: in the STEP folder of the project) -> file path


def step_path(st):
    """File path of a STEP stock record."""
    p = str((st or {}).get("path") or "").strip().strip('"')
    if not p:
        raise ValueError("no STEP file is chosen for the stock")
    if RESOLVE_PATH is not None:
        p = RESOLVE_PATH(p)
    import os
    if not os.path.isfile(p):
        raise ValueError("the stock STEP file %s is not found" % p)
    return p


def step_stock(doc):
    """The solids of the stock STEP file (one solid; several fused): the file is in the coordinates of the part; the
    solid turned by "rx", "ry", "rz" deg about the part origin and moved by "dx", "dy", "dz" mm (stock offsets, part
    coordinates), then moved by the model placement."""
    from .. import model
    from . import placement as PL
    comp, named = model.step_solids(step_path(doc.get("stock")))
    sols = [s for _, s in named for s in (s.solids() if hasattr(s, "solids") else [s])]
    if not sols:
        raise ValueError("the stock STEP file has no solid")
    solid = sols[0] if len(sols) == 1 else TB.fuse(sols)
    st = doc.get("stock") or {}
    pos = [_f(st.get(k)) for k in ("dx", "dy", "dz")]
    rot = [_f(st.get(k)) for k in ("rx", "ry", "rz")]
    if any(abs(v) > 1e-12 for v in pos + rot):
        from .. import assembly
        solid = assembly.place(solid, {"pos": pos, "rot": rot})
    return PL.apply(solid, doc.get("placement"))


def stock_solid(doc, shape):
    """Stock before the first operation."""
    from build123d import Box, Location, Vector
    st = doc.get("stock") or {}
    kind = st.get("kind") or "offsets"
    if kind == "step":
        return step_stock(doc)
    bb = G.bbox(shape)
    if kind == "part_filled":
        from .ops2d import undercut_fill
        fills = [undercut_fill(info) for fc, info in undercut_faces(shape)]
        if not fills:
            return shape
        from .. import part as P
        r = P._fuzzy_op("union", [shape], fills, 1e-5)
        if r is None:
            raise ValueError("the undercuts could not be filled")
        sols = list(r.solids())
        if len(sols) > 1:
            raise ValueError("the filled stock is %d separate solids" % len(sols))
        return sols[0]
    if kind == "box":
        x0, y0, z0 = _f(st.get("xmin"), bb[0]), _f(st.get("ymin"), bb[1]), _f(st.get("zmin"), bb[2])
        x1, y1, z1 = _f(st.get("xmax"), bb[3]), _f(st.get("ymax"), bb[4]), _f(st.get("zmax"), bb[5])
    else:
        x0, y0, z0 = bb[0] - _f(st.get("xneg"), 1.0), bb[1] - _f(st.get("yneg"), 1.0), bb[2] - _f(st.get("zneg"), 0.0)
        x1, y1, z1 = bb[3] + _f(st.get("xpos"), 1.0), bb[4] + _f(st.get("ypos"), 1.0), bb[5] + _f(st.get("zpos"), 1.0)
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        raise ValueError("the stock has no size")
    b = Box(x1 - x0, y1 - y0, z1 - z0)
    return b.moved(Location(Vector((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)))


def origin_of(doc, stock_bb):
    """Machine zero [x, y, z] in job coordinates ("point": the picked vertex origin["point"])."""
    o = doc.get("origin") or {}
    sb = stock_bb
    xy = o.get("xy") or "stock_min"
    zk = o.get("z") or "stock_top"
    pt = [_f(v) for v in (list(o.get("point") or []) + [0, 0, 0])[:3]]
    if xy == "stock_centre":
        x, y = (sb[0] + sb[3]) / 2.0, (sb[1] + sb[4]) / 2.0
    elif xy == "part":
        x, y = 0.0, 0.0
    elif xy == "point":
        x, y = pt[0], pt[1]
    else:
        x, y = sb[0], sb[1]
    z = {"stock_bottom": sb[2], "part": 0.0, "point": pt[2]}.get(zk, sb[5])
    return [round(x + 0.0, 4), round(y + 0.0, 4), round(z + 0.0, 4)]


# --------------------------------------------------------------------------- heights and depths

def heights(op, doc, stock_bb, part_bb, start=None, final=None):
    """Resolved {"clearance", "safe", "start", "final", "step", "finish"} of an operation: the operation's values,
    else the defaults: start the top of the stock (or the given start), final the given final or the part
    bottom, safe and clearance from the setup sheet offsets above the start depth."""
    su = doc.get("setup") or DEFAULT_SETUP
    s0 = _f(op.get("start_depth"), start if start is not None else stock_bb[5])
    f0 = _f(op.get("final_depth"), final if final is not None else part_bb[2])
    safe = _f(op.get("safe_height"), s0 + _f(su.get("safe_offset"), 3.0))
    clear = _f(op.get("clearance_height"), s0 + _f(su.get("clearance_offset"), 5.0))
    step = _f(op.get("step_down"), _f(su.get("step_down"), 2.0))
    fin = _f(op.get("finish_depth"), _f(su.get("finish_depth"), 0.0))
    if clear < safe:
        clear = safe
    if safe < s0:
        safe = s0
    return {"clearance": round(clear, 4), "safe": round(safe, 4), "start": round(s0, 4), "final": round(f0, 4),
            "step": max(step, 0.05), "finish": max(fin, 0.0)}


def levels(h):
    """Z levels from the start depth down to the final depth: steps of step down, the last level at the final
    depth and, with a finish depth, the level before it at final + finish."""
    z_top, z_bot, s = h["start"], h["final"], h["step"]
    out = []
    if z_bot >= z_top - 1e-9:
        return out
    fin = h.get("finish", 0.0)
    zb = z_bot + fin if fin > 0 and z_bot + fin < z_top else z_bot
    n = int(math.ceil((z_top - zb) / s - 1e-6))
    for i in range(1, n + 1):
        out.append(max(zb, z_top - i * s))
    out[-1] = zb
    out = [z for i, z in enumerate(out) if i == 0 or z < out[i - 1] - 1e-6]
    if zb > z_bot + 1e-9:
        out.append(z_bot)
    return out


# --------------------------------------------------------------------------- moves

class Moves(object):
    """Collects the moves of an operation."""

    def __init__(self, h, feed, plunge, hrapid=None):
        self.moves = []
        self.h = h                       # heights
        self.cz = h["clearance"]
        self.sz = h["safe"]
        self.feed = feed
        self.plunge = plunge
        self.ramp = None                 # feed of ramp and helix entries (None: the feed)
        self.cur = None

    def _add(self, k, p, **kw):
        m = {"k": k, "p": [float(p[0]), float(p[1]), float(p[2])]}
        m.update(kw)
        self.moves.append(m)
        self.cur = tuple(m["p"])

    def rapid_to(self, x, y):
        """Rapid at the clearance height (lifted first when below it)."""
        if self.cur is not None and self.cur[2] < self.cz - 1e-9:
            self._add("rapid", (self.cur[0], self.cur[1], self.cz))
        self._add("rapid", (x, y, self.cz))

    def rapid_down(self, z):
        self._add("rapid", (self.cur[0], self.cur[1], z))

    def to_safe(self):
        """Rapid down to the safe height."""
        if self.cur is not None and self.cur[2] > self.sz + 1e-9:
            self._add("rapid", (self.cur[0], self.cur[1], self.sz))

    def plunge_to(self, z, feed=None):
        self._add("plunge", (self.cur[0], self.cur[1], z), f=feed or self.plunge)

    def feed_to(self, x, y, z, feed=None):
        self._add("feed", (x, y, z), f=feed or self.feed)

    def arc_to(self, x, y, z, cx, cy, cw, feed=None):
        self._add("arc", (x, y, z), c=[float(cx), float(cy)], cw=bool(cw), f=feed or self.feed)

    def polyline(self, pts, z, feed=None):
        for x, y in pts:
            self.feed_to(x, y, z, feed)

    def retract(self):
        if self.cur is not None and self.cur[2] < self.cz - 1e-9:
            self._add("rapid", (self.cur[0], self.cur[1], self.cz))

    def enter(self, x, y, z):
        """Rapid to above (x, y), down to the safe height, plunge to z."""
        self.rapid_to(x, y)
        self.to_safe()
        self.plunge_to(z)

    def item(self, k, **kw):
        m = {"k": k}
        m.update(kw)
        self.moves.append(m)


def move_points(moves):
    """Points (x, y, z) of the cutting moves: [(polyline [(x, y, z)...], kind)], arcs sampled; rapids split the
    polylines."""
    out = []
    cur = None
    prev = None
    for m in moves:
        if "p" not in m:
            continue
        p = tuple(m["p"])
        if m["k"] == "rapid":
            if cur:
                out.append(cur)
            cur = None
        else:
            if cur is None:
                cur = [prev] if prev is not None else []
            if m["k"] == "arc" and prev is not None:
                cur += G.arc_pts(prev, p, m["c"], m.get("cw"))
            else:
                cur.append(p)
        prev = p
    if cur:
        out.append(cur)
    return [pl for pl in out if pl]


def path_length(moves):
    """(cut length mm, rapid length mm) of the moves."""
    cut = rapid = 0.0
    prev = None
    for m in moves:
        if "p" not in m:
            continue
        p = m["p"]
        if prev is not None:
            if m["k"] == "rapid":
                rapid += math.dist(prev, p)
            elif m["k"] == "arc":
                pts = [prev] + G.arc_pts(prev, p, m["c"], m.get("cw"))
                cut += sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
            else:
                cut += math.dist(prev, p)
        prev = p
    return cut, rapid


def cycle_time(moves, hrapid=3000.0):
    """Estimated time (s) of the moves from the feeds and the rapid speed."""
    t = 0.0
    prev = None
    for m in moves:
        if m.get("k") == "dwell":
            t += _f(m.get("s"))
        if "p" not in m:
            continue
        p = m["p"]
        if prev is not None:
            if m["k"] == "rapid":
                d = math.dist(prev, p)
                t += d / max(hrapid, 1.0) * 60.0
            else:
                if m["k"] == "arc":
                    pts = [prev] + G.arc_pts(prev, p, m["c"], m.get("cw"))
                    d = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
                else:
                    d = math.dist(prev, p)
                t += d / max(_f(m.get("f"), 100.0), 1.0) * 60.0
        prev = p
    return t


# --------------------------------------------------------------------------- simulation

def simulate(stock, shape, tool, moves, flat=True):
    """Stock after the cutting moves of a tool: the moves grouped by their Z, the footprint of the tool along the
    moves of a level extruded from the level to the cutting height and subtracted, from the top level down. The
    neck and the shank over the footprint are checked against the stock of each level. Returns {"stock",
    "levels": [{"z", "removed_mm3", "length_mm"}], "removed_mm3", "gouge_mm3" (the part material cut), "errors"}."""
    R = TB.radius(tool)
    cut, body = TB.tool_profile(tool)
    hcut = cut[-1][1]
    rn = _f(tool.get("neck"), 2 * R) / 2.0
    ln = _f(tool.get("neck_length"), 0.0)
    rs = _f(tool.get("shank"), max(2 * rn, 2 * R)) / 2.0
    ls = _f(tool.get("shank_length"), 30.0)
    groups = _level_groups(moves)
    res = {"stock": stock, "levels": [], "removed_mm3": 0.0, "gouge_mm3": 0.0, "errors": []}
    cur = stock
    sb = G.bbox(stock)
    for z in sorted(groups, reverse=True):
        lines_ = groups[z]
        reg = G.level_region(lines_, R)
        if reg is None or reg.is_empty:
            continue
        ztop = min(z + hcut, sb[5] + 1.0)
        if ztop <= z + 1e-9:
            continue
        # neck and shank above the cutting part
        bodies = []
        if ln > 0:
            bodies.append(G.prism(G.level_region(lines_, rn), z + hcut, z + hcut + ln))
        bodies.append(G.prism(G.level_region(lines_, rs), z + hcut + ln, z + hcut + ln + ls))
        for b in bodies:
            if b is None:
                continue
            v = G.common_volume(b, cur)
            if v is None or v > G.TOL_VOL:
                res["errors"].append("Z %.3f mm: the neck or shank of the tool collides with the stock (%.1f mm^3): the cut is deeper than the cutting height of the tool or the stock above is not cleared" % (z, v or 0.0))
                res["stock"] = cur
                return res
        before = G.volume(cur)
        slabs = []
        for r0, h0, h1 in _slabs(cut, R):
            if z + h0 >= ztop - 1e-9:
                break
            p = G.prism(reg if abs(r0 - R) < 1e-9 else G.level_region(lines_, r0), z + h0, min(z + h1, ztop))
            if p is not None:
                slabs.append(p)
        if not slabs:
            continue
        removed = TB.fuse(slabs) if len(slabs) > 1 else slabs[0]
        try:
            cur = G.cut(cur, [removed])
        except ValueError as e:
            res["errors"].append("Z %.3f mm: %s" % (z, e))
            res["stock"] = cur
            return res
        dv = before - G.volume(cur)
        res["removed_mm3"] += dv
        res["levels"].append({"z": round(z, 4), "removed_mm3": round(dv, 3),
                              "length_mm": round(sum(_plen(pl) for pl in lines_), 1)})
    res["stock"] = cur
    # the part material cut: the part inside the stock before less the part inside the stock after
    if res["levels"]:
        v0 = G.common_volume(stock, shape)
        v1 = G.common_volume(cur, shape)
        if v0 is not None and v1 is not None:
            res["gouge_mm3"] = max(0.0, v0 - v1)
    return res


def _slabs(cut, R, dr=None):
    """The cutting profile as slabs (radius, z from, z to) from the tip up: a cylinder of the full radius for a
    flat end mill; a sloping or curved part of the profile as steps of at most dr mm of radius change, each step
    with the larger radius of its ends."""
    dr = dr or max(0.3, R / 4.0)
    out = []
    for (ra, ha), (rb, hb) in zip(cut, cut[1:]):
        if hb - ha < 1e-9:
            continue
        if abs(rb - ra) < 1e-9:
            out.append((ra, ha, hb))
            continue
        n = max(1, min(12, int(math.ceil(abs(rb - ra) / dr))))
        for j in range(n):
            za, zb = ha + (hb - ha) * j / n, ha + (hb - ha) * (j + 1) / n
            out.append((max(ra + (rb - ra) * j / n, ra + (rb - ra) * (j + 1) / n), za, zb))
    # merge consecutive slabs of one radius
    merged = []
    for r, a, b in out:
        if merged and abs(merged[-1][0] - r) < 1e-9 and abs(merged[-1][2] - a) < 1e-9:
            merged[-1] = (r, merged[-1][1], b)
        else:
            merged.append((r, a, b))
    return merged or [(R, 0.0, cut[-1][1])]


def _level_groups(moves, piece=1.0):
    """The cutting moves as polylines (x, y) grouped by Z level: a run of moves at one Z is one polyline of that
    level; a sloping move is cut in pieces of at most piece mm, each put at the nearest level at or below its
    lower end (its own lower end when no level is below)."""
    flat = {}
    slopes = []
    for pl in move_points(moves):
        if len(pl) == 1:
            flat.setdefault(round(pl[0][2], 4), []).append([pl[0][:2]])
            continue
        cur = None
        for a, b in zip(pl, pl[1:]):
            if abs(a[2] - b[2]) < 1e-6:
                z = round(a[2], 4)
                if cur is not None and cur[0] == z:
                    cur[1].append(b[:2])
                else:
                    cur = (z, [a[:2], b[:2]])
                    flat.setdefault(z, []).append(cur[1])
            else:
                cur = None
                L = math.dist(a, b)
                n = max(1, int(math.ceil(L / piece)))
                for i in range(n):
                    p = (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, a[2] + (b[2] - a[2]) * i / n)
                    q = (a[0] + (b[0] - a[0]) * (i + 1) / n, a[1] + (b[1] - a[1]) * (i + 1) / n, a[2] + (b[2] - a[2]) * (i + 1) / n)
                    slopes.append((min(p[2], q[2]), [p[:2], q[:2]]))
    levels_ = sorted(flat)
    for zmin, seg in slopes:
        below = [z for z in levels_ if z <= zmin + 1e-6]
        z = below[-1] if below else round(zmin, 4)
        flat.setdefault(z, []).append(seg)
    return flat


def _plen(pl):
    return sum(math.hypot(pl[i + 1][0] - pl[i][0], pl[i + 1][1] - pl[i][1]) for i in range(len(pl) - 1))


FILM = 0.02


def remaining(stock, shape):
    """Material of the stock outside the part (mm^3) and the part material cut away (mm^3), and the solid of
    the remaining material without films thinner than FILM."""
    from .. import part as P
    from build123d import Compound
    stock = G.solids_only(stock)
    if stock is None:
        return 0.0, G.volume(shape), None
    left = P._fuzzy_op("subtract", [stock], [shape], 1e-5)
    gone = P._fuzzy_op("subtract", [shape], [stock], 1e-5)
    vg = G.volume(gone)
    if gone is None or vg > 0.999 * G.volume(shape):
        # the Boolean failed (coincident faces): the cut part material from the common volume
        c = G.common_volume(shape, stock)
        vg = max(0.0, G.volume(shape) - c) if c is not None else vg
    pieces = []
    if left is not None:
        for so in left.solids():
            v, a = abs(so.volume), so.area
            if a > 0 and 2 * v / a >= FILM:
                pieces.append(so)
        left = Compound(children=pieces) if pieces else None
    return sum(abs(x.volume) for x in pieces), vg, left


# --------------------------------------------------------------------------- run

class Ctx(object):
    """What an operation generator gets: the part, the stock before the operation, the job, the resolved heights
    and the tool."""

    def __init__(self, doc, shape, stock, bits, op, tc, tool, res):
        self.doc, self.shape, self.stock, self.bits = doc, shape, stock, bits
        self.op, self.tc, self.tool, self.res = op, tc, tool, res
        self.part_bb = G.bbox(shape)
        self.stock_bb = G.bbox(stock)
        self.feed, self.plunge, self.rpm = feeds(op, tc)
        self.rfeed = _f(op.get("ramp_feed"), 0) or _f(tc.get("rfeed"), 0) or None
        self.h = None

    def heights(self, start=None, final=None):
        self.h = heights(self.op, self.doc, self.stock_bb, self.part_bb, start, final)
        return self.h

    def moves(self):
        mv = Moves(self.h, self.feed, self.plunge)
        mv.ramp = self.rfeed
        return mv

    def message(self, text):
        self.res["messages"].append(text)

    def error(self, text):
        self.res["errors"].append(text)


def generators():
    from . import ops2d, adaptive, vcarve, ops3d
    g = dict(ops2d.OPS)
    g.update(adaptive.OPS)
    g.update(vcarve.OPS)
    g.update(ops3d.OPS)
    return g


_CACHE = {}
_CACHE_ORDER = []
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 60


def _key(doc, shape_key, upto):
    core = {"source": doc.get("source"), "stock": doc.get("stock"), "setup": doc.get("setup"), "tools": doc.get("tools"),
            "operations": (doc.get("operations") or [])[:upto]}
    return hashlib.sha1((shape_key + json.dumps(core, sort_keys=True)).encode("utf-8")).hexdigest()


def cache_clear():
    with _CACHE_LOCK:
        _CACHE.clear()
        del _CACHE_ORDER[:]


class Cancelled(Exception):
    """A run stopped by its cancel test (a newer preview of the same client)."""


def run(doc, shape, bits, upto=None, shape_key="", only=None, cancel=None):
    """All operations of the document on the part shape. upto: index of the last operation to run; only: the
    index of the one operation whose moves are wanted (the earlier ones are taken from the cache when possible).
    cancel: a function tested before each operation (and phase); True stops the run with Cancelled (the operations
    done so far stay in the cache).
    Returns {"stock0", "stock", "operations": [record...], "origin", "clearance_z"}; a record: {"id", "type",
    "name", "ok", "errors", "messages", "moves", "levels", "removed_mm3", "gouge_mm3", "remaining_mm3", "heights",
    "feed", "plunge", "rpm", "cut_mm", "rapid_mm", "time_s", "tool"}. An operation with a separate finish
    ("finish_mode": "separate", ops2d.FINISHABLE) gives two records: the roughing ("phase": "rough", the operation id)
    and the finish ("phase": "finish", id "<id>:finish", "finish_of": the operation id)."""
    doc = migrate(doc)
    stock0 = stock_solid(doc, shape)
    sb0 = G.bbox(stock0)
    origin = origin_of(doc, sb0)
    ops = doc.get("operations") or []
    n = len(ops) if upto is None else min(len(ops), upto + 1)
    out = []
    cur = stock0
    gens = generators()
    # the cache: the stock and the records after the first k operations
    start = 0
    if shape_key:
        for k in range(n, 0, -1):
            hit = _CACHE.get(_key(doc, shape_key, k))
            if hit is not None:
                cur, out = hit[0], [dict(r) for r in hit[1]]
                start = k
                break
    from .ops2d import FINISHABLE, finish_mode

    def one(op):
        """One record: the operation (or one phase of it) run on the current stock."""
        nonlocal cur
        rec = {"id": op.get("id"), "type": op.get("type"), "name": op.get("name"), "ok": False, "errors": [], "messages": [],
               "moves": [], "levels": [], "removed_mm3": 0.0, "gouge_mm3": 0.0, "remaining_mm3": 0.0, "heights": None,
               "tool": None}
        if op.get("_phase"):
            rec["phase"] = op["_phase"]
        if op.get("finish_of"):
            rec["finish_of"] = op["finish_of"]
        out.append(rec)
        if not op.get("active", True):
            rec["ok"] = True
            rec["messages"].append("inactive")
            return rec
        t = op.get("type")
        try:
            if t in SUPPLEMENTAL:
                _supplemental(doc, op, rec, origin, sb0)
                rec["ok"] = True
                return rec
            if t in DERIVED:
                src = next((r for r in out if r["id"] == op.get("of")), None)
                if src is None or not src.get("ok") or not src.get("moves"):
                    raise ValueError("the operation %s to %s is not before this one or has no moves" % (op.get("of") or "(none)", t))
                tcid = next((o.get("tc") for o in ops if o.get("id") == op.get("of")), None)
                tc = controller_of(doc, tcid)
                tool = bit_of(bits, tc.get("bit"))
                from .dressup import derived_moves
                moves = derived_moves(op, src["moves"])
                rec["tool"] = tc.get("id")
                rec["heights"] = src.get("heights")
                rec["feed"], rec["plunge"], rec["rpm"] = src.get("feed"), src.get("plunge"), src.get("rpm")
            else:
                gen = gens.get(t)
                if gen is None:
                    raise ValueError("unknown operation type %s" % t)
                tc = controller_of(doc, op.get("tc"))
                tool = bit_of(bits, tc.get("bit"))
                ctx = Ctx(doc, shape, cur, bits, op, tc, tool, rec)
                mv = gen(ctx)
                if rec["errors"]:
                    return rec
                moves = mv.moves if hasattr(mv, "moves") else list(mv or [])
                from .dressup import apply_dressups
                moves = apply_dressups(ctx, moves)
                if rec["errors"]:
                    return rec
                rec["tool"] = tc.get("id")
                rec["heights"] = ctx.h
                rec["feed"], rec["plunge"], rec["rpm"] = ctx.feed, ctx.plunge, ctx.rpm
            if op.get("comment"):
                moves.insert(0, {"k": "comment", "text": str(op["comment"])})
            for m in moves:
                if "p" in m:
                    m["p"] = [round(v, 4) for v in m["p"]]
            rec["moves"] = moves
            try:
                cut_, body_ = TB.tool_profile(tool)
                rec["profile"] = [[round(r, 4), round(z, 4)] for r, z in cut_ + body_[1:]]
                rec["cut_height"] = round(cut_[-1][1], 4)
            except ValueError:
                pass
            if rec.get("hm_sim"):
                sim = rec.pop("hm_sim")
            else:
                sim = simulate(cur, shape, tool, moves)
            rec["levels"] = sim.get("levels", [])
            rec["removed_mm3"] = round(sim.get("removed_mm3", 0.0), 3)
            rec["gouge_mm3"] = round(sim.get("gouge_mm3", 0.0), 4)
            rec["errors"] += sim.get("errors", [])
            if rec["errors"]:
                return rec
            if rec.pop("cuts_part", False):
                # engraving operations cut into the part by design
                rec["messages"].append("%.3f mm^3 cut from the part" % rec["gouge_mm3"])
                rec["engraved_mm3"] = rec["gouge_mm3"]
                rec["gouge_mm3"] = 0.0
            elif rec["gouge_mm3"] > max(0.05, 1e-6 * G.volume(shape)):
                rec["messages"].append("gouge: %.3f mm^3 of the part cut" % rec["gouge_mm3"])
            cur = sim["stock"]
            if rec.get("_remaining") is not None:
                rec["remaining_mm3"] = round(rec.pop("_remaining")(cur), 3)
            rec["cut_mm"], rec["rapid_mm"] = [round(v, 1) for v in path_length(moves)]
            rec["time_s"] = round(cycle_time(moves, _f((doc.get("setup") or {}).get("hrapid"), 3000.0)), 1)
            rec["ok"] = True
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            rec["errors"].append(str(e))
        finally:
            rec.pop("_remaining", None)
            rec.pop("cuts_part", None)
        return rec

    def check():
        if cancel is not None and cancel():
            raise Cancelled("run cancelled")

    for i in range(start, n):
        op = ops[i]
        check()
        if op.get("type") in FINISHABLE and finish_mode(op) == "separate" and op.get("active", True):
            r1 = one(dict(op, _phase="rough"))
            check()
            r2 = one(finish_variant(op)) if r1["ok"] else None
            ok_all = r1["ok"] and (r2 is None or r2["ok"])
        else:
            ok_all = one(op)["ok"]
        if shape_key and ok_all:
            with _CACHE_LOCK:
                k = _key(doc, shape_key, i + 1)
                _CACHE[k] = (cur, [dict(r) for r in out])
                _CACHE_ORDER.append(k)
                while len(_CACHE_ORDER) > _CACHE_MAX:
                    _CACHE.pop(_CACHE_ORDER.pop(0), None)
    return {"stock0": stock0, "stock": cur, "operations": out, "origin": origin, "clearance_z": sb0[5] + _f((doc.get("setup") or {}).get("clearance_offset"), 5.0)}


def finish_variant(op):
    """The finish phase of an operation with a separate finish: its own record (id "<id>:finish"), the finish tool
    controller (empty: the operation's), the finish feeds (empty: the operation's with the same tool, else the finish
    controller's) and the finish step down (empty: the operation's)."""
    tcf = op.get("finish_tc") or op.get("tc")
    same = tcf == op.get("tc")
    pick = lambda k_fin, k_op: op.get(k_fin) if op.get(k_fin) not in (None, "") else (op.get(k_op) if same else None)
    return dict(op, _phase="finish", id=str(op.get("id")) + ":finish", name=(op.get("name") or str(op.get("id"))) + " (finish)",
                tc=tcf, finish_of=op.get("id"), feed=pick("finish_feed", "feed"), plunge=pick("finish_plunge", "plunge"),
                rpm=pick("finish_rpm", "rpm"), ramp_feed=op.get("ramp_feed") if same else None,
                step_down=op.get("finish_step") if op.get("finish_step") not in (None, "") else op.get("step_down"), comment="")


def _supplemental(doc, op, rec, origin, stock_bb=None):
    t = op.get("type")
    if t == "hop":
        # a rapid lift to a height (job coordinates; empty: the clearance height of the job)
        sb = stock_bb or [0, 0, 0, 0, 0, 0]
        z = _f(op.get("height"), sb[5] + _f((doc.get("setup") or {}).get("clearance_offset"), 5.0))
        rec["moves"] = [{"k": "hop", "z": round(z, 4)}]
        return
    if t == "probe":
        # a grid of probe moves (G38.2) over a rectangle (empty: the stock) from the start height down to the depth
        sb = stock_bb or [0, 0, 0, 0, 0, 0]
        x0, x1 = _f(op.get("xmin"), sb[0]), _f(op.get("xmax"), sb[3])
        y0, y1 = _f(op.get("ymin"), sb[1]), _f(op.get("ymax"), sb[4])
        nx, ny = max(1, int(_f(op.get("nx"), 3))), max(1, int(_f(op.get("ny"), 3)))
        zs = _f(op.get("start_z"), sb[5] + 2.0)
        zd = _f(op.get("depth"), sb[5] - 5.0)
        f = _f(op.get("feed"), 50.0)
        mv = []
        if op.get("output"):
            mv.append({"k": "probe_open", "name": str(op["output"])})
        for j in range(ny):
            xs = [x0 + (x1 - x0) * i / max(1, nx - 1) for i in range(nx)]
            if j % 2:
                xs.reverse()
            y = y0 + (y1 - y0) * j / max(1, ny - 1)
            for x in xs:
                mv.append({"k": "probe", "x": round(x, 4), "y": round(y, 4), "z0": round(zs, 4), "z1": round(zd, 4), "f": f})
        if op.get("output"):
            mv.append({"k": "probe_close"})
        rec["moves"] = mv
        rec["messages"].append("%d probe point(s)" % (nx * ny))
        return
    if t == "fixture":
        rec["moves"] = [{"k": "fixture", "g": op.get("fixture") or "G54"}]
    elif t == "comment":
        rec["moves"] = [{"k": "comment", "text": str(op.get("text") or "")}]
    elif t == "stop":
        rec["moves"] = [{"k": "stop", "optional": bool(op.get("optional"))}]
    elif t == "custom":
        rec["moves"] = [{"k": "custom", "text": str(op.get("gcode") or "")}]


# --------------------------------------------------------------------------- sanity check and template

def sanity(doc, shape, bits, result=None):
    """Checks of the job: [{"level": "error" | "warning" | "info", "text"}]."""
    doc = migrate(doc)
    out = []
    add = lambda lvl, txt: out.append({"level": lvl, "text": txt})
    if not (doc.get("source") or {}).get("name"):
        add("error", "no part is chosen")
    if not doc.get("tools"):
        add("error", "the job has no tool controller")
    bids = {b.get("id") for b in bits or []}
    for tc in doc.get("tools") or []:
        if tc.get("bit") not in bids:
            add("error", "tool controller %s: the tool %s is not in the tool table" % (tc.get("id"), tc.get("bit")))
        if _f(tc.get("hfeed")) <= 0 or _f(tc.get("vfeed")) <= 0:
            add("error", "tool controller %s: feed or plunge feed is 0" % tc.get("id"))
        if _f(tc.get("rpm")) <= 0:
            add("warning", "tool controller %s: spindle speed is 0" % tc.get("id"))
        su = doc.get("setup") or {}
        if _f(tc.get("rpm")) > 0 and not (_f(su.get("rpm_min"), 0) - 1e-6 <= _f(tc.get("rpm")) <= _f(su.get("rpm_max"), 1e9) + 1e-6):
            add("warning", "tool controller %s: spindle speed %.0f rpm outside the spindle range %.0f to %.0f rpm" % (
                tc.get("id"), _f(tc.get("rpm")), _f(su.get("rpm_min")), _f(su.get("rpm_max"))))
        if max(_f(tc.get("hfeed")), _f(tc.get("vfeed"))) > _f(su.get("feed_max"), 1e9) + 1e-6:
            add("warning", "tool controller %s: feed above the machine maximum %.0f mm/min" % (tc.get("id"), _f(su.get("feed_max"))))
    nums = [tc.get("number") for tc in doc.get("tools") or []]
    if len(nums) != len(set(nums)):
        add("warning", "two tool controllers have the same tool number")
    ops = doc.get("operations") or []
    if not ops:
        add("warning", "the job has no operation")
    tcs = {tc.get("id") for tc in doc.get("tools") or []}
    for op in ops:
        t = op.get("type")
        if t == "probe" and (doc.get("post") or "estlcam") == "estlcam":
            add("warning", "%s: the Estlcam post writes no probe moves (a comment and M00 per point)" % op.get("name"))
        if t in SUPPLEMENTAL:
            continue
        if t in DERIVED:
            if not any(o.get("id") == op.get("of") for o in ops):
                add("error", "%s: the operation it copies is not in the job" % op.get("name"))
            continue
        if op.get("tc") not in tcs:
            add("error", "%s: no tool controller" % op.get("name"))
        if op.get("finish_mode") == "separate" and op.get("finish_tc") and op.get("finish_tc") not in tcs:
            add("error", "%s: the finish tool controller %s is not in the job" % (op.get("name"), op.get("finish_tc")))
        if t in ("pocket", "drilling", "helix", "undercut", "pocket3d", "deburr", "thread") and not op.get("faces") and not op.get("edges"):
            add("error", "%s: no base geometry" % op.get("name"))
        if t in ("engrave", "vcarve") and not (op.get("edges") or op.get("sketch") or op.get("text")):
            add("error", "%s: no base geometry" % op.get("name"))
        if op.get("final_depth") is not None and op.get("start_depth") is not None and _f(op["final_depth"]) >= _f(op["start_depth"]):
            add("error", "%s: the final depth is not below the start depth" % op.get("name"))
    if shape is not None:
        try:
            st = stock_solid(doc, shape)
            sb, pb = G.bbox(st), G.bbox(shape)
            if any(sb[i] > pb[i] + 1e-6 for i in range(3)) or any(sb[i] < pb[i] - 1e-6 for i in range(3, 6)):
                add("warning", "the stock does not cover the part")
        except ValueError as e:
            add("error", str(e))
    if result:
        for r in result.get("operations") or []:
            for e in r.get("errors") or []:
                add("error", "%s: %s" % (r.get("name"), e))
            if r.get("gouge_mm3", 0) > 0.05:
                add("warning", "%s: gouge %.3f mm^3" % (r.get("name"), r["gouge_mm3"]))
    if not (doc.get("output") or {}).get("name"):
        add("info", "output file name empty: <job name>.nc")
    if not out:
        add("info", "no problem found")
    return out


def template(doc):
    """Job template: the setup sheet, the tool controllers, the post-processor and the operations without their
    geometry (faces, edges, points)."""
    doc = migrate(doc)
    ops = []
    for op in doc.get("operations") or []:
        o = {k: v for k, v in op.items() if k not in ("faces", "edges", "points", "id")}
        ops.append(o)
    return {"format": "shinycad-cam-template", "version": 1, "setup": doc.get("setup"), "tools": doc.get("tools"),
            "post": doc.get("post"), "stock": doc.get("stock"), "origin": doc.get("origin"), "operations": ops}


def apply_template(doc, tpl):
    """The template's setup sheet, tool controllers, post-processor, stock, origin and operations (without
    geometry, new ids) in the document."""
    doc = migrate(doc)
    for k in ("setup", "tools", "post", "stock", "origin"):
        if tpl.get(k) is not None:
            doc[k] = json.loads(json.dumps(tpl[k]))
    ops = []
    n = int(doc.get("next") or 1)
    for op in tpl.get("operations") or []:
        o = json.loads(json.dumps(op))
        o["id"] = "op%d" % n
        n += 1
        for k in ("faces", "edges", "points"):
            if k in op or o.get("type") in ("pocket", "drilling", "helix", "undercut", "pocket3d", "deburr", "engrave", "vcarve", "slot"):
                o.setdefault(k, [])
        ops.append(o)
    doc["operations"] = ops
    doc["next"] = n
    return doc
