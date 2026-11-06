# -*- coding: utf-8 -*-
"""Search of the nodes and elements of a .inp or .rad mesh file (the parsed file of inpinfo): query(path, q).

q: {"what": "nodes" | "elements",
    "by": "number"  "numbers": "12, 40-50, 7"                         node or element numbers
          "box"     "box": [xmin, ymin, zmin, xmax, ymax, zmax]       (None: open) nodes, element centroids
          "near"    "point": [x, y, z], "radius": mm, "nearest": n    within the radius and / or the n nearest
          "set"     "set": name                                       *NSET / *ELSET (part)
          "type"    "type": element type                              elements of the type; nodes of its elements
          "attached" "numbers"                                        nodes: of the elements; elements: on the nodes
          "quality" "criterion": "inverted" | "aspect" | "warp" | "angle" | "edge" | "volume" | "coincident",
                    "value"                                           elements beyond the value; coincident nodes
          "at"      "point": [x, y, z], "within": {"set": name} | {"type": element type} | None
                                                                      a point picked in the view: the nearest node, or
                                                                      the element at the point (in the set or of the type)
    "limit": rows (default 500)}
-> {"what", "count", "rows", "truncated", "marks": {"points": [[x, y, z]], "lines": [[x, y, z, x, y, z]]}, "note"}.
Node rows: {"id", "xyz", "dist", "sets", "elements" (count), "elem_ids" (first 12)}. Element rows: {"id", "type",
"nodes", "sets", "section", "material", "centroid", "dist", "measure" (volume mm^3 or area mm^2), "edge_min",
"edge_max", "aspect", "inverted", "angle_min", "angle_max", "warp", "edges" (lines of the element in marks), "tris"
(faces of the element as triangles, x y z per corner)}.
"""
import re
import threading

import numpy as np

from . import inpinfo

_LOCK = threading.Lock()
_IDX = {}


# faces of the element shapes (corner indices) as triangles, for the highlight of an element in the view
TRIS = {"tet": [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)],
        "hex": [(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)],
        "wedge": [(0, 1, 2), (3, 4, 5), (0, 1, 4), (0, 4, 3), (1, 2, 5), (1, 5, 4), (2, 0, 3), (2, 3, 5)],
        "pyr": [(0, 1, 2), (0, 2, 3), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)],
        "tri": [(0, 1, 2)], "quad": [(0, 1, 2), (0, 2, 3)]}


class QueryError(ValueError):
    pass


def _index(path):
    """Arrays of the parsed file: node ids and coordinates, element types with corner connectivity (cached)."""
    raw = inpinfo.raw(path)
    key = id(raw)
    with _LOCK:
        if key in _IDX and _IDX[key]["raw"] is raw:
            return _IDX[key]
    nodes = raw["nodes"]
    ids = np.array(sorted(nodes), np.int64)
    X = np.array([nodes[i] for i in ids], float) if len(ids) else np.zeros((0, 3))
    pos = {int(n): k for k, n in enumerate(ids)}
    types = {}
    for et, eids in raw["etypes"].items():
        ti = inpinfo.element_type(et)
        nc = inpinfo.CORNERS.get(ti["shape"])
        good = [e for e in eids if nc and len(raw["elements"][e][1]) >= nc and all(n in pos for n in raw["elements"][e][1][:nc])]
        conn = np.array([[pos[n] for n in raw["elements"][e][1][:nc]] for e in good], np.int64).reshape(-1, nc or 1) if good else np.zeros((0, nc or 1), np.int64)
        cen = X[conn].mean(axis=1) if len(good) else np.zeros((0, 3))
        types[et] = {"shape": ti["shape"], "eids": np.array(good, np.int64), "conn": conn, "cen": cen}
    out = {"raw": raw, "ids": ids, "X": X, "pos": pos, "types": types, "n2e": None, "setsN": None, "setsE": None}
    with _LOCK:
        _IDX.clear()
        _IDX[key] = out
    return out


def _numbers(text):
    out = []
    for part in re.split(r"[,\s;]+", str(text or "").strip()):
        if not part:
            continue
        m = re.match(r"^(-?\d+)\s*(?:-|\.\.|:)\s*(-?\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if abs(b - a) > 2000000:
                raise QueryError("range %s too large" % part)
            out += list(range(min(a, b), max(a, b) + 1))
        else:
            try:
                out.append(int(float(part)))
            except ValueError:
                raise QueryError("not a number: %s" % part)
    return out


def _n2e(I):
    """{node index: [element numbers]} over all nodes of the elements (mid-side nodes included)."""
    if I["n2e"] is None:
        n2e, pos = {}, I["pos"]
        for e, (_t, ns) in I["raw"]["elements"].items():
            for n in ns:
                k = pos.get(n)
                if k is not None:
                    n2e.setdefault(k, []).append(e)
        I["n2e"] = n2e
    return I["n2e"]


def _sets_of(I, kind, ids):
    """{id: [set names]} for the ids (node numbers or element numbers)."""
    raw = I["raw"]
    key = "setsN" if kind == "nodes" else "setsE"
    if I[key] is None:
        I[key] = {name: set(v) for name, v in (raw["nsets"] if kind == "nodes" else raw["elsets"]).items()}
    want = set(ids)
    out = {i: [] for i in ids}
    for name, s in I[key].items():
        for i in want & s if len(s) > len(want) else (x for x in s if x in want):
            out[i].append(name)
    return out


def _elem_info(I, rows):
    """Measures of elements [(type, index in the type)]: dict per element id."""
    out = {}
    by = {}
    for et, k in rows:
        by.setdefault(et, []).append(k)
    for et, ks in by.items():
        t = I["types"][et]
        ks = np.array(ks, np.int64)
        q = inpinfo._quality(I["X"], None, t["conn"][ks], t["shape"]) if t["shape"] in inpinfo.EDGES else {}
        P = I["X"][t["conn"][ks]]
        L = np.stack([np.linalg.norm(P[:, b] - P[:, a], axis=1) for a, b in inpinfo.EDGES[t["shape"]]], axis=1) if t["shape"] in inpinfo.EDGES else None
        vol = q.get("_vol")
        area = q.get("_area")
        ang = _angles(P, t["shape"]) if t["shape"] in ("tri", "quad") else None
        warp = _warp(P) if t["shape"] == "quad" else None
        for j, k in enumerate(ks.tolist()):
            e = int(t["eids"][k])
            d = {"type": et, "centroid": t["cen"][k].tolist()}
            if L is not None:
                d.update(edge_min=float(L[j].min()), edge_max=float(L[j].max()), aspect=float(L[j].max() / L[j].min()) if L[j].min() > 0 else None)
            if vol is not None:
                d.update(measure=float(vol[j]), inverted=bool(vol[j] <= 0))
            if area is not None:
                d.update(measure=float(area[j]))
            if ang is not None:
                d["angle_min"], d["angle_max"] = float(ang[j].min()), float(ang[j].max())
            if warp is not None:
                d["warp"] = float(warp[j])
            out[e] = d
    return out


def _angles(P, shape):
    n = inpinfo.CORNERS[shape]
    ang = []
    for i in range(n):
        u = P[:, (i + 1) % n] - P[:, i]
        w = P[:, (i - 1) % n] - P[:, i]
        with np.errstate(divide="ignore", invalid="ignore"):
            c = np.einsum("ij,ij->i", u, w) / (np.linalg.norm(u, axis=1) * np.linalg.norm(w, axis=1))
        ang.append(np.degrees(np.arccos(np.clip(c, -1, 1))))
    return np.stack(ang, axis=1)


def _warp(P):
    n1 = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    n2 = np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 0])
    m1 = np.cross(P[:, 1] - P[:, 0], P[:, 3] - P[:, 0])
    m2 = np.cross(P[:, 2] - P[:, 1], P[:, 3] - P[:, 1])
    with np.errstate(divide="ignore", invalid="ignore"):
        w1 = np.einsum("ij,ij->i", n1, n2) / (np.linalg.norm(n1, axis=1) * np.linalg.norm(n2, axis=1))
        w2 = np.einsum("ij,ij->i", m1, m2) / (np.linalg.norm(m1, axis=1) * np.linalg.norm(m2, axis=1))
    return np.degrees(np.maximum(np.arccos(np.clip(w1, -1, 1)), np.arccos(np.clip(w2, -1, 1))))


def _all_elements(I):
    """[(type, index)] of all elements and their centroids (n, 3)."""
    refs, C = [], []
    for et, t in I["types"].items():
        refs += [(et, k) for k in range(len(t["eids"]))]
        C.append(t["cen"])
    return refs, (np.concatenate(C) if C else np.zeros((0, 3)))


def _where(I, numbers):
    """[(type, index)] of element numbers."""
    look = {}
    for et, t in I["types"].items():
        for k, e in enumerate(t["eids"].tolist()):
            look[e] = (et, k)
    return [look[e] for e in numbers if e in look], [e for e in numbers if e not in look]


def _box_mask(P, box):
    m = np.ones(len(P), bool)
    for d in range(3):
        lo, hi = (box[d] if box else None), (box[d + 3] if box else None)
        if lo is not None and lo != "":
            m &= P[:, d] >= float(lo)
        if hi is not None and hi != "":
            m &= P[:, d] <= float(hi)
    return m


def _near(P, q):
    pt = q.get("point")
    if not pt or len(pt) != 3:
        raise QueryError("give the point x, y, z")
    p = np.asarray([float(v) for v in pt])
    d = np.linalg.norm(P - p, axis=1)
    sel = np.arange(len(P))
    r = q.get("radius")
    if r not in (None, ""):
        sel = sel[d[sel] <= float(r)]
    n = q.get("nearest")
    if n not in (None, ""):
        sel = sel[np.argsort(d[sel])[:int(n)]]
    elif r in (None, ""):
        sel = sel[np.argsort(d[sel])[:1]]
    return sel[np.argsort(d[sel])], d


def _score(P, shape, p):
    """How far the point p is inside an element (corners P): solids the smallest barycentric coordinate of the best
    tetrahedron of the element (>= 0 inside), shells and lines minus the distance (mm) over the element size."""
    if shape in inpinfo.TETS:
        best = -1e30
        for t in inpinfo.TETS[shape]:
            A = np.stack([P[t[1]] - P[t[0]], P[t[2]] - P[t[0]], P[t[3]] - P[t[0]]], axis=1)
            try:
                lam = np.linalg.solve(A, p - P[t[0]])
            except np.linalg.LinAlgError:
                continue
            best = max(best, float(min(1.0 - lam.sum(), lam.min())))
        return best
    size = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0))) or 1.0
    if shape == "line":
        u = P[1] - P[0]
        s_ = float(np.clip(np.dot(p - P[0], u) / max(np.dot(u, u), 1e-30), 0, 1))
        return -float(np.linalg.norm(p - (P[0] + s_ * u))) / size
    tris = [(0, 1, 2)] if shape == "tri" else [(0, 1, 2), (0, 2, 3)]
    best = 1e30
    for a, b, c in tris:
        A, B, C = P[a], P[b], P[c]
        n = np.cross(B - A, C - A)
        nn = float(np.linalg.norm(n))
        if nn == 0:
            continue
        n = n / nn
        h = float(np.dot(p - A, n))
        q_ = p - h * n
        inside = all(np.dot(np.cross(Y - X_, q_ - X_), n) >= -1e-9 * size * size for X_, Y in ((A, B), (B, C), (C, A)))
        d = abs(h) if inside else min(float(np.linalg.norm(p - X_)) for X_ in (A, B, C))
        best = min(best, d)
    return -best / size


def _within_nodes(I, w):
    """Node indices of a restriction {"set"} or {"type"} (None: all)."""
    raw, pos = I["raw"], I["pos"]
    if not w:
        return None
    if w.get("set"):
        name = str(w["set"]).upper()
        if name not in raw["nsets"]:
            raise QueryError("node set %s not found" % name)
        return np.array(sorted(pos[n] for n in raw["nsets"][name] if n in pos), np.int64)
    if w.get("type"):
        et = str(w["type"]).upper()
        if et not in raw["etypes"]:
            raise QueryError("element type %s not found" % w["type"])
        return np.array(sorted(set(pos[n] for e in raw["etypes"][et] for n in raw["elements"][e][1] if n in pos)), np.int64)
    return None


def _within_elements(I, w):
    """[(type, index)] and centroids of a restriction {"set"} or {"type"} (None: all)."""
    raw = I["raw"]
    if w and w.get("set"):
        name = str(w["set"]).upper()
        if name not in raw["elsets"]:
            raise QueryError("element set %s not found" % name)
        refs, _m = _where(I, raw["elsets"][name])
    elif w and w.get("type"):
        et = str(w["type"]).upper()
        if et not in I["types"]:
            raise QueryError("element type %s not found" % et)
        refs = [(et, k) for k in range(len(I["types"][et]["eids"]))]
    else:
        return _all_elements(I)
    C = np.array([I["types"][et]["cen"][k] for et, k in refs]) if refs else np.zeros((0, 3))
    return refs, C


def _point(q):
    pt = q.get("point")
    if not pt or len(pt) != 3:
        raise QueryError("give the point x, y, z")
    return np.asarray([float(v) for v in pt])


def query(path, q):
    I = _index(path)
    raw, X, ids, pos = I["raw"], I["X"], I["ids"], I["pos"]
    what = q.get("what") or "nodes"
    by = q.get("by") or "number"
    limit = int(q.get("limit") or 500)
    note = ""
    dist = None
    if what == "nodes":
        if by == "number":
            nums = _numbers(q.get("numbers"))
            sel = [pos[n] for n in nums if n in pos]
            miss = [n for n in nums if n not in pos]
            if miss:
                note = "not in the file: %s" % ", ".join(map(str, miss[:20])) + (" ..." if len(miss) > 20 else "")
        elif by == "box":
            sel = np.nonzero(_box_mask(X, q.get("box")))[0].tolist()
        elif by == "near":
            s, dist = _near(X, q)
            sel = s.tolist()
        elif by == "set":
            name = str(q.get("set") or "").upper()
            if name not in raw["nsets"]:
                raise QueryError("node set %s not found" % name)
            sel = [pos[n] for n in raw["nsets"][name] if n in pos]
        elif by == "type":
            et = str(q.get("type") or "").upper()
            if et not in raw["etypes"]:
                raise QueryError("element type %s not found" % q.get("type"))
            sel = sorted(set(pos[n] for e in raw["etypes"][et] for n in raw["elements"][e][1] if n in pos))
        elif by == "attached":
            nums = _numbers(q.get("numbers"))
            miss = [e for e in nums if e not in raw["elements"]]
            sel = sorted(set(pos[n] for e in nums if e in raw["elements"] for n in raw["elements"][e][1] if n in pos))
            if miss:
                note = "elements not in the file: %s" % ", ".join(map(str, miss[:20]))
        elif by == "at":
            p = _point(q)
            cand = _within_nodes(I, q.get("within"))
            cand = np.arange(len(X)) if cand is None else cand
            if not len(cand):
                raise QueryError("no nodes to pick from")
            dist = np.full(len(X), np.inf)
            dist[cand] = np.linalg.norm(X[cand] - p, axis=1)
            sel = [int(cand[int(np.argmin(dist[cand]))])]
        elif by == "quality":
            if q.get("criterion") != "coincident":
                raise QueryError("nodes: quality criterion coincident")
            diag = float(np.linalg.norm(X.max(axis=0) - X.min(axis=0))) if len(X) else 0.0
            tol = float(q.get("value") or 0) or max(diag * 1e-6, 1e-9)
            key = np.round(X / tol).astype(np.int64)
            _u, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
            inv = inv.ravel()
            sel = sorted(np.nonzero(cnt[inv] > 1)[0].tolist(), key=lambda k: (int(inv[k]), int(ids[k])))
            note = "coincident within %g mm (groups in order)" % tol
        else:
            raise QueryError("unknown search %s" % by)
        count = len(sel)
        sel = list(sel)[:limit]
        n2e = _n2e(I) if sel else {}
        sets = _sets_of(I, "nodes", [int(ids[k]) for k in sel])
        rows = []
        for k in sel:
            n = int(ids[k])
            es = n2e.get(k, [])
            rows.append({"id": n, "xyz": X[k].tolist(), "dist": float(dist[k]) if dist is not None else None, "sets": sets[n],
                         "elements": len(es), "elem_ids": es[:12]})
        marks = {"points": [r["xyz"] for r in rows], "lines": []}
        return {"what": what, "count": count, "rows": rows, "truncated": count > len(rows), "marks": marks, "note": note}
    # elements
    if by == "number":
        refs, miss = _where(I, _numbers(q.get("numbers")))
        if miss:
            note = "not in the file or not a solid, shell, beam or truss element: %s" % ", ".join(map(str, miss[:20]))
    elif by in ("box", "near"):
        allr, C = _all_elements(I)
        if by == "box":
            refs = [allr[k] for k in np.nonzero(_box_mask(C, q.get("box")))[0].tolist()]
        else:
            s, d = _near(C, q)
            refs = [allr[k] for k in s.tolist()]
            dist = {allr[k]: float(d[k]) for k in s.tolist()}
    elif by == "at":
        p = _point(q)
        allr, C = _within_elements(I, q.get("within"))
        if not allr:
            raise QueryError("no elements to pick from")
        d = np.linalg.norm(C - p, axis=1)
        near = np.argsort(d)[:60]
        sc = {k: _score(X[I["types"][allr[k][0]]["conn"][allr[k][1]]], I["types"][allr[k][0]]["shape"], p) for k in near.tolist()}
        best = max(sc, key=lambda k: (sc[k], -d[k]))
        if sc[best] < -0.05:                    # not on or in an element: the nearest centroid
            best = int(near[0])
        refs = [allr[best]]
        dist = {allr[best]: float(d[best])}
    elif by == "set":
        name = str(q.get("set") or "").upper()
        if name not in raw["elsets"]:
            raise QueryError("element set %s not found" % name)
        refs, _m = _where(I, raw["elsets"][name])
    elif by == "type":
        et = str(q.get("type") or "").upper()
        if et not in I["types"]:
            raise QueryError("element type %s not found" % et)
        refs = [(et, k) for k in range(len(I["types"][et]["eids"]))]
    elif by == "attached":
        nums = _numbers(q.get("numbers"))
        n2e = _n2e(I)
        es = sorted(set(e for n in nums if n in pos for e in n2e.get(pos[n], [])))
        refs, _m = _where(I, es)
    elif by == "quality":
        crit = q.get("criterion") or "inverted"
        v = q.get("value")
        allr, _C = _all_elements(I)
        info = _elem_info(I, allr)
        keyf = {"inverted": lambda d: d.get("inverted"), "aspect": lambda d: (d.get("aspect") or 0) > float(v or 10),
                "warp": lambda d: (d.get("warp") or 0) > float(v or 10), "angle": lambda d: d.get("angle_min") is not None and d["angle_min"] < float(v or 30),
                "edge": lambda d: (d.get("edge_min") or 0) < float(v or 0), "volume": lambda d: d.get("measure") is not None and d["measure"] < float(v or 0)}
        if crit not in keyf:
            raise QueryError("unknown criterion %s" % crit)
        sortk = {"aspect": lambda r: -(info[int(I["types"][r[0]]["eids"][r[1]])].get("aspect") or 0),
                 "warp": lambda r: -(info[int(I["types"][r[0]]["eids"][r[1]])].get("warp") or 0),
                 "angle": lambda r: info[int(I["types"][r[0]]["eids"][r[1]])].get("angle_min") or 0,
                 "edge": lambda r: info[int(I["types"][r[0]]["eids"][r[1]])].get("edge_min") or 0,
                 "volume": lambda r: info[int(I["types"][r[0]]["eids"][r[1]])].get("measure") or 0}.get(crit)
        refs = [r for r in allr if keyf[crit](info[int(I["types"][r[0]]["eids"][r[1]])])]
        if sortk:
            refs.sort(key=sortk)
        note = {"inverted": "zero or negative volume", "aspect": "aspect ratio above %g (largest first)" % float(v or 10),
                "warp": "warping above %g deg (largest first)" % float(v or 10), "angle": "corner angle below %g deg (smallest first)" % float(v or 30),
                "edge": "shortest edge below %g mm" % float(v or 0), "volume": "volume or area below %g" % float(v or 0)}[crit]
    else:
        raise QueryError("unknown search %s" % by)
    count = len(refs)
    refs = refs[:limit]
    info = _elem_info(I, refs)
    eids = [int(I["types"][et]["eids"][k]) for et, k in refs]
    sets = _sets_of(I, "elements", eids)
    sec_of = {s["elset"]: s for s in raw["sections"]}
    rows, lines = [], []
    for (et, k), e in zip(refs, eids):
        d = info[e]
        nodes = raw["elements"][e][1]
        s = next((sec_of[n] for n in sets[e] if n in sec_of), None)
        rows.append(dict(d, id=e, nodes=nodes, sets=sets[e], section=s["kind"] if s else None, material=s["material"] if s else None,
                         dist=dist.get((et, k)) if isinstance(dist, dict) else None))
        t = I["types"][et]
        rows[-1]["edges"] = 0
        if t["shape"] in inpinfo.EDGES:
            P = X[t["conn"][k]]
            for a, b in inpinfo.EDGES[t["shape"]]:
                lines.append(P[a].tolist() + P[b].tolist())
            rows[-1]["edges"] = len(inpinfo.EDGES[t["shape"]])
            rows[-1]["tris"] = [v for tr in TRIS.get(t["shape"], []) for i in tr for v in P[i].tolist()]
    marks = {"points": [r["centroid"] for r in rows], "lines": lines}
    return {"what": "elements", "count": count, "rows": rows, "truncated": count > len(rows), "marks": marks, "note": note}
