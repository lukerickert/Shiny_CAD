# -*- coding: utf-8 -*-
"""Model placement of a CAM job: the part moved and turned in the job coordinate system before the stock, the
machine zero and the operations are worked out (the job coordinate system is the coordinate system of the
toolpaths; its XY plane is the machine table plane, +Z the spindle axis).

Placement record (doc["placement"]):
  {"pos": [x, y, z] mm, "rot": [rx, ry, rz] deg (rotations about the fixed X, then Y, then Z axis about the part
   origin, then the translation: the convention of assembly components),
   "constraints": [{"id", "type": "coincident" | "distance" | "parallel" | "angle" | "concentric",
       "face": index of the face of the part (shape.faces() order), "fc": centre of that face in part coordinates
       (filled by solve; used to find the face again when the part changes), or "edge" (index of
       assembly.edge_refs) with "ec" (its midpoint, part coordinates), or "vertex" with "vc" (its point),
       "datum": "XY" | "XZ" | "YZ" | "X" |
       "Y" | "Z", "value": mm (distance) or deg (angle), "flip": false, "suppressed": false}],
   "next": n}

The constraints are assembly mates (assembly.py) between a face, edge or vertex of the part and a datum plane or
axis of the job coordinate system: the datums form a fixed component, the part the free one."""
import hashlib
import json
import math

DATUMS = {
    "XY": {"kind": "plane", "c": [0.0, 0.0, 0.0], "n": [0.0, 0.0, 1.0]},
    "XZ": {"kind": "plane", "c": [0.0, 0.0, 0.0], "n": [0.0, 1.0, 0.0]},
    "YZ": {"kind": "plane", "c": [0.0, 0.0, 0.0], "n": [1.0, 0.0, 0.0]},
    "X": {"kind": "axis", "c": [0.0, 0.0, 0.0], "p": [0.0, 0.0, 0.0], "n": [1.0, 0.0, 0.0]},
    "Y": {"kind": "axis", "c": [0.0, 0.0, 0.0], "p": [0.0, 0.0, 0.0], "n": [0.0, 1.0, 0.0]},
    "Z": {"kind": "axis", "c": [0.0, 0.0, 0.0], "p": [0.0, 0.0, 0.0], "n": [0.0, 0.0, 1.0]},
}
TYPES = ("coincident", "distance", "parallel", "angle", "concentric")
TYPE_NAMES = {"coincident": "Coincident", "distance": "Distance", "parallel": "Parallel", "angle": "Angle",
              "concentric": "Concentric"}


def _f(v, default=0.0):
    try:
        return float(default) if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return float(default)


def normalize(pl):
    """The placement record with every field present."""
    pl = dict(pl or {})
    pl["pos"] = [_f(v) for v in (list(pl.get("pos") or []) + [0, 0, 0])[:3]]
    pl["rot"] = [_f(v) for v in (list(pl.get("rot") or []) + [0, 0, 0])[:3]]
    pl["constraints"] = [dict(c) for c in pl.get("constraints") or [] if isinstance(c, dict)]
    pl.setdefault("next", len(pl["constraints"]) + 1)
    return pl


def is_identity(pl):
    pl = normalize(pl)
    return all(abs(v) < 1e-12 for v in pl["pos"] + pl["rot"])


def key(pl):
    """Text of the transform for the cache key of the placed shape ("" without a transform)."""
    pl = normalize(pl)
    if is_identity(pl):
        return ""
    return hashlib.sha1(json.dumps([round(v, 9) for v in pl["pos"] + pl["rot"]]).encode("utf-8")).hexdigest()[:16]


def apply(shape, pl):
    """The shape moved by the placement (the same shape without a transform)."""
    pl = normalize(pl)
    if is_identity(pl):
        return shape
    from .. import assembly
    return assembly.place(shape, {"pos": pl["pos"], "rot": pl["rot"]})


def face_refs(shape):
    """Face references of the unplaced part (assembly.face_refs: kind plane | cylinder | other, c, n, p, r)."""
    from .. import assembly
    return assembly.face_refs(shape)


def _face_of(c, refs):
    """Index of the face of a constraint: the face whose centre is at "fc" (within 0.05 mm), else "face"."""
    fc = c.get("fc")
    if fc and len(fc) == 3:
        best, bd = None, 0.05
        for i, r in enumerate(refs):
            if r:
                d = math.dist(r["c"], fc)
                if d < bd:
                    best, bd = i, d
        if best is not None:
            return best
    i = c.get("face")
    try:
        i = int(i)
    except (TypeError, ValueError):
        return None
    return i if 0 <= i < len(refs) and refs[i] else None


def geo_refs(shape):
    """Edge and vertex references of the unplaced part as {"edge:<i>": ref, "vertex:<i>": ref} (assembly.edge_refs,
    vertex_refs: line p n c, circle c n r m, other edge c; vertex c)."""
    from .. import assembly
    out = {}
    for i, r in enumerate(assembly.edge_refs(shape)):
        if r:
            out["edge:%d" % i] = r
    for i, r in enumerate(assembly.vertex_refs(shape)):
        out["vertex:%d" % i] = r
    return out


def to_part(pl, p):
    """A point of the job coordinates in part coordinates (the inverse of the placement)."""
    from .. import assembly
    pl = normalize(pl)
    R = assembly._rot_matrix(pl["rot"])
    d = [p[i] - pl["pos"][i] for i in range(3)]
    return [sum(R[k][i] * d[k] for k in range(3)) for i in range(3)]


def _mid(r):
    return r.get("m") or r["c"]


def find_geo(geo, kind, c, tol=0.05):
    """Key of the edge (by its midpoint) or vertex nearest to the part point c within tol mm, or None."""
    best, bd = None, tol
    for k, r in geo.items():
        if not k.startswith(kind + ":"):
            continue
        d = math.dist(_mid(r) if kind == "edge" else r["c"], c)
        if d < bd:
            best, bd = k, d
    return best


def _side(c, refs, geo):
    """(mate side of the part, reference) of a constraint: a face, an edge or a vertex; (None, reason) when lost."""
    if c.get("edge") is not None or c.get("ec"):
        k = find_geo(geo, "edge", c.get("ec") or [0, 0, 0]) if c.get("ec") else "edge:%d" % int(c["edge"])
        if k is None or k not in geo:
            return None, "the edge is not found in the part"
        r = geo[k]
        if r["kind"] not in ("line", "circle"):
            return None, "the edge is neither straight nor circular"
        c["edge"], c["ec"] = int(k.split(":")[1]), _mid(r)
        return {"comp": "part", "datum": k}, r
    if c.get("vertex") is not None or c.get("vc"):
        k = find_geo(geo, "vertex", c.get("vc") or [0, 0, 0]) if c.get("vc") else "vertex:%d" % int(c["vertex"])
        if k is None or k not in geo:
            return None, "the vertex is not found in the part"
        c["vertex"], c["vc"] = int(k.split(":")[1]), geo[k]["c"]
        return {"comp": "part", "datum": k}, geo[k]
    i = _face_of(c, refs)
    if i is None:
        return None, "the face is not found in the part"
    r = refs[i]
    if r["kind"] not in ("plane", "cylinder"):
        return None, "the face is neither planar nor cylindrical"
    c["face"], c["fc"] = i, r["c"]
    return {"comp": "part", "face": i}, r


def _angle_start(pos, rot, m, shape):
    """Start placement of an Angle constraint whose face normal (edge direction) is parallel to the datum normal
    (axis), where the solve has no gradient: the part turned by the angle about the longest straight edge of the face
    (a datum axis perpendicular to the edge) through the face centre (the edge midpoint). The sign of the value sets
    the direction of the turn. Other starts are returned unchanged."""
    from .. import assembly as A
    r = m["_ref"]
    R = A._rot_matrix(rot)
    rv = lambda v: [sum(R[i][k] * v[k] for k in range(3)) for i in range(3)]
    a = rv(r["n"])
    nb = DATUMS[m["b"]["datum"]]["n"]
    d0 = sum(a[i] * nb[i] for i in range(3))
    want = (-1.0 if m.get("flip") else 1.0) * math.cos(math.radians(m["value"]))
    if abs(d0) < 0.9999 or abs(want) > 0.9999:
        return pos, rot
    u = None
    if "face" in m["a"]:
        try:
            fc = shape.faces()[m["a"]["face"]]
            best = 0.0
            for e in fc.edges():
                if not str(getattr(e.geom_type, "name", e.geom_type)).upper().endswith("LINE"):
                    continue
                p0, p1 = e.position_at(0), e.position_at(1)
                d = [p1.X - p0.X, p1.Y - p0.Y, p1.Z - p0.Z]
                ln = math.sqrt(sum(x * x for x in d))
                if ln > best + 1e-9:
                    best, u = ln, rv([x / ln for x in d])
        except Exception:  # noqa: BLE001
            u = None
    if u is None:
        axes = ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0])
        u = min(axes, key=lambda x: abs(sum(x[i] * a[i] for i in range(3))))
    phi = math.acos(max(-1.0, min(1.0, want / d0)))
    if m.get("_angle", 0.0) < 0:
        phi = -phi
    Ru = A._axis_rot(u, phi)
    R2 = [[sum(Ru[i][k] * R[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    c = [sum(R[i][k] * r["c"][k] for k in range(3)) + pos[i] for i in range(3)]
    q = [pos[i] - c[i] for i in range(3)]
    pos2 = [sum(Ru[i][k] * q[k] for k in range(3)) + c[i] for i in range(3)]
    return pos2, A._euler_of(R2)


def solve(pl, shape, drag=None):
    """Solve of the constraints from the current placement: {"pos", "rot", "constraints" (face / edge / vertex and
    their part centres filled), "messages", "unsatisfied": {constraint id: text}, "flipped": [ids]}. A constraint
    whose face, edge or vertex is lost is reported and left out. drag {"delta": [dx, dy, dz]}: the part moved by
    delta mm, then the constraints solved from there (the part keeps the motion the constraints leave free)."""
    from .. import assembly
    pl = normalize(pl)
    if drag and drag.get("delta"):
        pl["pos"] = [pl["pos"][i] + _f(drag["delta"][i]) for i in range(3)]
    refs = face_refs(shape)
    geo = None
    msgs, mates, lost = [], [], {}
    for c in pl["constraints"]:
        name = TYPE_NAMES.get(c.get("type"), c.get("type") or "?")
        if c.get("suppressed"):
            continue
        if c.get("type") not in TYPES:
            lost[c.get("id")] = "unknown type %s" % c.get("type")
            continue
        if c.get("datum") not in DATUMS:
            lost[c.get("id")] = "no datum plane or axis"
            continue
        if geo is None and (c.get("edge") is not None or c.get("vertex") is not None or c.get("ec") or c.get("vc")):
            geo = geo_refs(shape)
        side, r = _side(c, refs, geo or {})
        if side is None:
            lost[c.get("id")] = r
            continue
        val = _f(c.get("value"))
        if c["type"] == "angle":
            if "datum" in side and side["datum"].startswith("vertex"):
                lost[c.get("id")] = "Angle takes a planar face or a straight edge"
                continue
            if "datum" in side and r.get("kind") != "line":
                lost[c.get("id")] = "Angle takes a planar face or a straight edge"
                continue
            if "face" in side and r["kind"] != "plane":
                lost[c.get("id")] = "Angle takes a planar face or a straight edge"
                continue
            if "face" in side and DATUMS[c["datum"]]["kind"] == "axis":
                lost[c.get("id")] = "Angle of a face takes a datum plane"
                continue
            if "datum" in side and DATUMS[c["datum"]]["kind"] == "plane":
                val = 90.0 - val          # the mate works with the angle to the plane normal
        mates.append({"id": c.get("id"), "name": name, "type": c["type"], "value": val,
                      "flip": bool(c.get("flip")), "a": side, "b": {"comp": "datum", "datum": c["datum"]},
                      "_ref": r, "_angle": _f(c.get("value"))})
    for cid, t in lost.items():
        msgs.append("constraint %s left out: %s" % (cid, t))
    out = {"pos": pl["pos"], "rot": pl["rot"], "constraints": pl["constraints"], "messages": msgs,
           "unsatisfied": dict(lost), "flipped": []}
    if not mates:
        out["pos"] = [round(v, 4) + 0.0 for v in pl["pos"]]
        return out
    for m in mates:
        if m["type"] == "angle":
            pl["pos"], pl["rot"] = _angle_start(pl["pos"], pl["rot"], m, shape)
    R0 = assembly._rot_matrix(pl["rot"])
    for m in mates:
        # a straight edge on (parallel to) a datum axis keeps the direction it has (the edge direction is arbitrary)
        r = m.get("_ref") or {}
        if r.get("kind") == "line" and DATUMS[m["b"]["datum"]]["kind"] == "axis" and m["type"] in ("coincident", "parallel", "distance"):
            n = [sum(R0[i][k] * r["n"][k] for k in range(3)) for i in range(3)]
            m["flip"] = sum(n[i] * DATUMS[m["b"]["datum"]]["n"][i] for i in range(3)) > 0
    for m in mates:
        m.pop("_ref", None)
        m.pop("_angle", None)
    asm = {"components": [{"id": "datum", "name": "Datum", "fixed": True, "pos": [0, 0, 0], "rot": [0, 0, 0]},
                          {"id": "part", "name": "Part", "pos": pl["pos"], "rot": pl["rot"]}],
           "mates": mates}
    detail = {}
    res, _nr, ms = assembly.solve_mates(asm, lambda cid: refs if cid == "part" else [],
                                        lambda cid: DATUMS if cid == "datum" else (geo or {}), detail, rot_scale=0.01)
    if "part" in res:
        pos, rot = res["part"]
        out["pos"] = [round(v, 4) + 0.0 for v in pos]
        out["rot"] = [round(v, 4) + 0.0 for v in rot]
    out["messages"] += [m.replace("Part / Datum ", "") for m in ms]
    out["unsatisfied"].update({k: v.replace("Part / Datum ", "") for k, v in (detail.get("unsatisfied") or {}).items()})
    out["flipped"] = list(detail.get("flipped") or [])
    for c in pl["constraints"]:
        if c.get("id") in out["flipped"]:
            c["flip"] = not c.get("flip")
    return out


def suggest(pl, shape, face=None, ctype="coincident", edge=None, vertex=None):
    """Datum, Flip and value of a new constraint that keep the part where it is as far as possible. A face: the
    datum plane (or axis for a cylinder) closest in direction to the placed face normal (axis), Flip when the normals
    point the same way. edge / vertex: a point of the job coordinates (the edge midpoint, the vertex) that picks it:
    a straight edge to the datum axis most parallel to it (Parallel) or the datum plane containing its direction that
    is nearest (Coincident, Distance); a circular edge to the datum axis most parallel to its axis; a vertex to the
    nearest datum plane. Returns {"datum", "flip", "value", "kind", and "edge" / "vertex": index, "ec" / "vc": part
    point}."""
    from .. import assembly
    pl = normalize(pl)
    R = assembly._rot_matrix(pl["rot"])
    rot = lambda v: assembly._apply(R, [0, 0, 0], v, point=False)
    put = lambda v: assembly._apply(R, pl["pos"], v)
    if edge is not None or vertex is not None:
        geo = geo_refs(shape)
        kind = "edge" if edge is not None else "vertex"
        k = find_geo(geo, kind, to_part(pl, edge if edge is not None else vertex), tol=0.5)
        if k is None:
            raise ValueError("no %s of the part at the picked point" % kind)
        r = geo[k]
        out = {kind: int(k.split(":")[1]), ("ec" if kind == "edge" else "vc"): (_mid(r) if kind == "edge" else r["c"]), "flip": False, "value": 0.0}
        c = put(r["c"])
        if kind == "vertex":
            if ctype not in ("coincident", "distance"):
                raise ValueError("a vertex takes Coincident or Distance")
            j = min(range(3), key=lambda i: abs(c[i]))
            out.update(datum=("YZ", "XZ", "XY")[j], kind="point", value=round(c[j], 6) if ctype == "distance" else 0.0)
            return out
        if r["kind"] not in ("line", "circle"):
            raise ValueError("pick a straight or a circular edge")
        n = rot(r["n"])
        k3 = max(range(3), key=lambda i: abs(n[i]))
        if r["kind"] == "circle" or ctype in ("parallel", "concentric"):
            out.update(datum=("X", "Y", "Z")[k3], flip=bool(n[k3] > 0), kind=r["kind"])
            return out
        if ctype == "angle":
            # the datum plane that contains the edge direction and is nearest; the value is the current angle (0)
            cand = [i for i in range(3) if i != k3]
            j = min(cand, key=lambda i: abs(c[i]))
            out.update(datum=("YZ", "XZ", "XY")[j], kind="line", value=0.0)
            return out
        # a straight edge in (or at a distance from) the datum plane that contains its direction and is nearest
        cand = [i for i in range(3) if i != k3]
        j = min(cand, key=lambda i: abs(c[i]))
        out.update(datum=("YZ", "XZ", "XY")[j], kind="line", value=round(c[j], 6) if ctype == "distance" else 0.0)
        return out
    refs = face_refs(shape)
    if face is None or not (0 <= int(face) < len(refs)) or not refs[int(face)]:
        raise ValueError("no such face")
    r = refs[int(face)]
    if r["kind"] not in ("plane", "cylinder"):
        raise ValueError("pick a planar or a cylindrical face")
    n = rot(r["n"])
    axis_like = r["kind"] == "cylinder" or ctype == "concentric"
    names = ("X", "Y", "Z") if axis_like else ("YZ", "XZ", "XY")
    k = max(range(3), key=lambda i: abs(n[i]))
    datum = names[k]
    flip = n[k] > 0                     # facing by default: Flip keeps a face whose normal points along the datum normal
    if ctype == "angle":
        flip = n[k] < 0                 # Angle: the normal at the value from the datum normal (Flip: from its reverse)
    value = 0.0
    if ctype == "distance" and not axis_like:
        c = put(r["c"])
        value = round(-c[k] * (1.0 if n[k] > 0 else -1.0), 6)
    return {"datum": datum, "flip": bool(flip), "value": value, "kind": r["kind"]}
