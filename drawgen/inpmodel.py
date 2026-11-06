# -*- coding: utf-8 -*-
"""CalculiX / Abaqus .inp files (and Radioss starter decks, radmodel.py) as the geometry of the Analysis and Explicit
tabs (source {"type": "inp", "path"}).

read(path) parses *NODE, *ELEMENT (TYPE, ELSET), *ELSET and *NSET (GENERATE), *MATERIAL with *ELASTIC, *DENSITY and
*PLASTIC, *SOLID SECTION and *SHELL SECTION (ELSET, MATERIAL, OFFSET, thickness). Steps, boundary conditions and
loads of the file are not read (supports and loads are set in the tab).

Bodies: one per element set with a section (elements in no section: one body per element type, "<TYPE>_ELEMENTS").
The exterior element faces of a body are grouped into faces (connected, normals within FEATURE_ANGLE); the face
boundaries form the edges. A component of the view per body (id: the body name): face references {"comp", "face"},
edge references {"comp", "edge"}. Shell bodies are a surface body of their component (the sections of the tab).

view(path) -> {"components": [...], "materials", "bodies", "shells", "nsets", "warnings"}: view data of the
components (mesh with "wire": the element edges of the exterior faces as vertex index pairs, refs, erefs, surfaces,
matrix) and the inputs of the file for the document.
analysis_input(doc) -> (bodies, mesh) for analysis.run and the explicit model: the bodies (solids: doc["bodies"][id];
shells: the sections of the document, else doc["shells"]["<id>:shell"]; "shape" None, with "volume" (mm^3), "area"
(mm^2) and "centre") and the mesh in the femesh output form, with "edges" (node chains
of the edges) and "nsets" (node sets of the file) for analysis.Model.
"""
import math
import os
import re
import threading

import numpy as np

FEATURE_ANGLE = 30.0     # deg between the normals of neighbouring element faces of one face
SHELL_ID = "shell"       # surface body id of a shell component

SOLID = {"C3D4": "tet", "C3D10": "tet", "C3D8": "hex", "C3D8R": "hex", "C3D8I": "hex", "C3D20": "hex", "C3D20R": "hex",
         "C3D6": "wedge", "C3D15": "wedge"}
SHELL = {"S3": "tri", "S3R": "tri", "S6": "tri", "S4": "quad", "S4R": "quad", "S8": "quad", "S8R": "quad"}
TYPE_MAP = {"S3R": "S3", "S8": "S8R"}           # element types written by the analysis
NCORNER = {"tet": 4, "hex": 8, "wedge": 6, "tri": 3, "quad": 4}
FACES = {"tet": [(0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)],
         "hex": [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)],
         "wedge": [(0, 1, 2), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]}
# mid-side nodes of the quadratic elements: (corner a, corner b) -> node index
MIDS = {"C3D10": {(0, 1): 4, (1, 2): 5, (2, 0): 6, (0, 3): 7, (1, 3): 8, (2, 3): 9},
        "C3D20": {(0, 1): 8, (1, 2): 9, (2, 3): 10, (3, 0): 11, (4, 5): 12, (5, 6): 13, (6, 7): 14, (7, 4): 15,
                  (0, 4): 16, (1, 5): 17, (2, 6): 18, (3, 7): 19},
        "C3D15": {(0, 1): 6, (1, 2): 7, (2, 0): 8, (3, 4): 9, (4, 5): 10, (5, 3): 11, (0, 3): 12, (1, 4): 13, (2, 5): 14},
        "S6": {(0, 1): 3, (1, 2): 4, (2, 0): 5}, "S8R": {(0, 1): 4, (1, 2): 5, (2, 3): 6, (3, 0): 7}}
MIDS["C3D20R"] = MIDS["C3D20"]
MIDS["S8"] = MIDS["S8R"]


class InpError(ValueError):
    pass


def _params(line):
    out = {}
    for p in line.split(",")[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip().upper()] = v.strip()
        elif p.strip():
            out[p.strip().upper()] = True
    return out


def _nums(s):
    out = []
    for t in s.replace(",", " ").split():
        try:
            out.append(float(t))
        except ValueError:
            pass
    return out


def read(path):
    """{"nodes": {id: (x, y, z)}, "elements": {id: (type, [nodes])}, "elsets": {name: [ids]}, "nsets": {name: [ids]},
    "materials": {name: {"E", "nu", "rho" (kg/m^3), "plastic"}}, "sections": [{"elset", "kind", "material", "t",
    "offset"}], "warnings"}. Names upper case."""
    if not os.path.isfile(path):
        raise InpError("file not found: %s" % path)
    if path.lower().endswith(".rad"):          # Radioss starter deck (radmodel.py)
        from . import radmodel
        return radmodel.read(path)
    nodes, elements, elsets, nsets, materials, sections, warnings = {}, {}, {}, {}, {}, [], []
    kw, prm, mat, pend = None, {}, None, []
    skipped = {}

    def flush_elem(vals):
        if not vals:
            return
        eid, ns = int(vals[0]), [int(v) for v in vals[1:]]
        et = prm.get("TYPE", "").upper()
        elements[eid] = (et, ns)
        es = prm.get("ELSET")
        if es:
            elsets.setdefault(es.upper(), []).append(eid)
    with open(path, "r", errors="replace") as f:
        lines = f.read().splitlines()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            if kw == "*ELEMENT" and pend:
                flush_elem(pend)
                pend = []
            kw = line.split(",")[0].strip().upper()
            prm = _params(line)
            if kw == "*MATERIAL":
                mat = str(prm.get("NAME", "MATERIAL")).upper()
                materials[mat] = {}
            elif kw in ("*SOLID SECTION", "*SHELL SECTION"):
                sections.append({"elset": str(prm.get("ELSET", "")).upper(), "kind": "solid" if kw == "*SOLID SECTION" else "shell",
                                 "material": str(prm.get("MATERIAL", "")).upper(), "t": None,
                                 "offset": {"0.5": "positive", "-0.5": "negative", "SPOS": "positive", "SNEG": "negative"}.get(str(prm.get("OFFSET", "0")).upper(), "mid")})
            elif kw == "*ELEMENT":
                et = prm.get("TYPE", "").upper()
                if et not in SOLID and et not in SHELL:
                    skipped[et] = skipped.get(et, 0)
            elif kw in ("*STEP", "*END STEP"):
                pass
            continue
        if kw == "*NODE":
            v = _nums(line)
            if len(v) >= 4:
                nodes[int(v[0])] = (v[1], v[2], v[3])
                if prm.get("NSET"):
                    nsets.setdefault(str(prm["NSET"]).upper(), []).append(int(v[0]))
        elif kw == "*ELEMENT":
            vals = [t for t in line.replace(",", " ").split()]
            cont = line.rstrip().endswith(",")
            pend += vals
            if not cont:
                et = prm.get("TYPE", "").upper()
                if et in SOLID or et in SHELL:
                    flush_elem(pend)
                else:
                    skipped[et] = skipped.get(et, 0) + 1
                pend = []
        elif kw in ("*ELSET", "*NSET"):
            name = str(prm.get("ELSET" if kw == "*ELSET" else "NSET", "")).upper()
            dst = (elsets if kw == "*ELSET" else nsets).setdefault(name, [])
            if prm.get("GENERATE"):
                v = [int(x) for x in _nums(line)]
                if len(v) >= 2:
                    dst += list(range(v[0], v[1] + 1, v[2] if len(v) > 2 and v[2] else 1))
            else:
                for t in line.replace(",", " ").split():
                    try:
                        dst.append(int(float(t)))
                    except ValueError:
                        ref = (elsets if kw == "*ELSET" else nsets).get(t.upper())
                        if ref:
                            dst += ref
        elif kw == "*ELASTIC" and mat:
            v = _nums(line)
            if len(v) >= 2 and "E" not in materials[mat]:
                materials[mat].update(E=v[0], nu=v[1])
        elif kw == "*DENSITY" and mat:
            v = _nums(line)
            if v and "rho" not in materials[mat]:
                r = v[0]
                materials[mat]["rho"] = r * 1e12 if r < 1e-3 else r          # t/mm^3 -> kg/m^3
        elif kw == "*PLASTIC" and mat:
            v = _nums(line)
            if len(v) >= 2:
                materials[mat].setdefault("plastic", []).append([v[0], v[1]])
        elif kw == "*SHELL SECTION" and sections and sections[-1]["t"] is None:
            v = _nums(line)
            if v:
                sections[-1]["t"] = v[0]
    if kw == "*ELEMENT" and pend:
        flush_elem(pend)
    for et, n in skipped.items():
        warnings.append("%s elements left out (%d): only solid and shell elements are read" % (et, n))
    if not nodes or not elements:
        raise InpError("%s: no nodes or no solid and shell elements" % os.path.basename(path))
    return {"nodes": nodes, "elements": elements, "elsets": elsets, "nsets": nsets, "materials": materials,
            "sections": sections, "warnings": warnings}


# --------------------------------------------------------------------------- bodies and faces

def _bodies(m):
    """[(name, kind "solid" | "shell", section or None, [element ids])]: element sets with a section (an element in
    several: the first section), the other elements by element type."""
    seen, out = set(), []
    for s in m["sections"]:
        ids = [e for e in m["elsets"].get(s["elset"], []) if e in m["elements"] and e not in seen]
        ids = [e for e in ids if (m["elements"][e][0] in SHELL) == (s["kind"] == "shell")]
        if ids:
            seen.update(ids)
            out.append((s["elset"] or "SECTION_%d" % (len(out) + 1), s["kind"], s, ids))
    rest = {}
    for e, (et, _ns) in m["elements"].items():
        if e not in seen:
            rest.setdefault(et, []).append(e)
    for et, ids in sorted(rest.items()):
        out.append(("%s_ELEMENTS" % et, "shell" if et in SHELL else "solid", None, ids))
    names = set()
    res = []
    for name, kind, s, ids in out:
        n, k = re.sub(r"[^A-Za-z0-9_]+", "_", name).upper() or "BODY", 2
        base = n
        while n in names:
            n = "%s_%d" % (base, k)
            k += 1
        names.add(n)
        res.append((n, kind, s, sorted(ids)))
    return res


def _facets(m, kind, ids):
    """Exterior element faces of a body: [(element id, corner nodes, all nodes of the facet)]."""
    out = []
    if kind == "shell":
        for e in ids:
            et, ns = m["elements"][e]
            nc = NCORNER[SHELL[et]]
            mids = MIDS.get(et)
            corners = ns[:nc]
            full = corners + ([ns[mids[(i, (i + 1) % nc)]] for i in range(nc)] if mids and len(ns) > nc else [])
            out.append((e, corners, full))
        return out
    count = {}
    cand = []
    for e in ids:
        et, ns = m["elements"][e]
        sk = SOLID[et]
        mids = MIDS.get(et)
        for f in FACES[sk]:
            corners = [ns[i] for i in f]
            full = corners + ([ns[mids.get((f[i], f[(i + 1) % len(f)])) if (f[i], f[(i + 1) % len(f)]) in mids
                                  else mids[(f[(i + 1) % len(f)], f[i])]] for i in range(len(f))] if mids and len(ns) > NCORNER[sk] else [])
            key = tuple(sorted(corners))
            count[key] = count.get(key, 0) + 1
            cand.append((key, e, corners, full))
    for key, e, corners, full in cand:
        if count[key] == 1:
            out.append((e, corners, full))
    return out


def _normal(X, corners):
    P = [np.asarray(X[n], float) for n in corners]
    v = np.cross(P[1] - P[0], P[2] - P[0]) if len(P) == 3 else np.cross(P[2] - P[0], P[3] - P[1])
    a = float(np.linalg.norm(v))
    return (v / a if a > 0 else v), 0.5 * a


def _group(X, facets, shell):
    """Face index of each facet: connected facets with normals within FEATURE_ANGLE (shells: either side)."""
    cosmin = math.cos(math.radians(FEATURE_ANGLE))
    N = [_normal(X, f[1])[0] for f in facets]
    edge_of = {}
    for i, f in enumerate(facets):
        c = f[1]
        for k in range(len(c)):
            a, b = c[k], c[(k + 1) % len(c)]
            edge_of.setdefault((min(a, b), max(a, b)), []).append(i)
    grp = [-1] * len(facets)
    g = 0
    for s in range(len(facets)):
        if grp[s] >= 0:
            continue
        grp[s] = g
        stack = [s]
        while stack:
            i = stack.pop()
            c = facets[i][1]
            for k in range(len(c)):
                a, b = c[k], c[(k + 1) % len(c)]
                for j in edge_of[(min(a, b), max(a, b))]:
                    if grp[j] < 0:
                        d = float(np.dot(N[i], N[j]))
                        if (abs(d) if shell else d) >= cosmin:
                            grp[j] = g
                            stack.append(j)
        g += 1
    return grp, edge_of


def _edges(facets, grp, edge_of):
    """Node chains of the face boundaries: [[nodes]] (element edges between two faces or on a free boundary,
    chained per pair of faces)."""
    segs = {}
    for (a, b), fs in edge_of.items():
        gs = sorted(set(grp[i] for i in fs))
        if len(fs) == 1 or len(gs) > 1:
            segs.setdefault(tuple(gs), []).append((a, b))
    chains = []
    for _key, ss in sorted(segs.items()):
        adj = {}
        for a, b in ss:
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
        used = set()
        ends = [n for n, v in adj.items() if len(v) != 2] + list(adj)
        for s in ends:
            for nb in adj[s]:
                if (min(s, nb), max(s, nb)) in used:
                    continue
                ch = [s, nb]
                used.add((min(s, nb), max(s, nb)))
                while True:
                    cur, prev = ch[-1], ch[-2]
                    nxt = [x for x in adj[cur] if x != prev and (min(cur, x), max(cur, x)) not in used]
                    if len(adj[cur]) != 2 or not nxt:
                        break
                    used.add((min(cur, nxt[0]), max(cur, nxt[0])))
                    ch.append(nxt[0])
                chains.append(ch)
    return chains


def _split_corners(X, chains):
    """Chains split at the nodes where the direction turns by more than FEATURE_ANGLE (a closed chain starts at its
    first corner)."""
    cosmin = math.cos(math.radians(FEATURE_ANGLE))

    def turn(a, b, c):
        u = np.asarray(X[b], float) - np.asarray(X[a], float)
        v = np.asarray(X[c], float) - np.asarray(X[b], float)
        nu, nv = np.linalg.norm(u), np.linalg.norm(v)
        return nu > 0 and nv > 0 and float(np.dot(u, v)) / (nu * nv) < cosmin
    out = []
    for ch in chains:
        closed = len(ch) > 3 and ch[0] == ch[-1]
        if closed:
            ring = ch[:-1]
            k = len(ring)
            corners = [i for i in range(k) if turn(ring[i - 1], ring[i], ring[(i + 1) % k])]
            if not corners:
                out.append(ch)
                continue
            ring = ring[corners[0]:] + ring[:corners[0]]
            ch = ring + [ring[0]]
        cut = [0] + [i for i in range(1, len(ch) - 1) if turn(ch[i - 1], ch[i], ch[i + 1])] + [len(ch) - 1]
        for a, b in zip(cut[:-1], cut[1:]):
            out.append(ch[a:b + 1])
    return out


_CACHE = {}
_LOCK = threading.Lock()


def model(path):
    """Parsed file with the bodies, faces and edges (cached by path, modification time and size):
    {"m": read(), "bodies": [{"id", "kind", "section", "elements", "facets", "group", "nfaces", "edges"}]}."""
    if not os.path.isfile(path):
        raise InpError("file not found: %s" % path)
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime, st.st_size)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    m = read(path)
    X = m["nodes"]
    bodies = []
    for name, kind, sec, ids in _bodies(m):
        fac = _facets(m, kind, ids)
        grp, edge_of = _group(X, fac, kind == "shell")
        bodies.append({"id": name, "kind": kind, "section": sec, "elements": ids, "facets": fac, "group": grp,
                       "nfaces": (max(grp) + 1) if grp else 0, "edges": _split_corners(X, _edges(fac, grp, edge_of))})
    out = {"m": m, "bodies": bodies}
    with _LOCK:
        _CACHE.clear()
        _CACHE[key] = out
    return out


# --------------------------------------------------------------------------- view

def view(path):
    M = model(path)
    m, X = M["m"], M["m"]["nodes"]
    comps = []
    for b in M["bodies"]:
        used = sorted(set(n for f in b["facets"] for n in f[1]) | set(n for ch in b["edges"] for n in ch))
        ix = {n: i for i, n in enumerate(used)}
        V = [list(map(float, X[n])) for n in used]
        T, fot = [], []
        for (e, c, _full), g in zip(b["facets"], b["group"]):
            if len(c) == 3:
                T.append([ix[c[0]], ix[c[1]], ix[c[2]]])
                fot.append(g)
            else:
                T += [[ix[c[0]], ix[c[1]], ix[c[2]]], [ix[c[0]], ix[c[2]], ix[c[3]]]]
                fot += [g, g]
        wire = set()                     # element edges of the exterior faces (vertex index pairs)
        for _e, c, _full in b["facets"]:
            for k in range(len(c)):
                a, q = ix[c[k]], ix[c[(k + 1) % len(c)]]
                wire.add((a, q) if a < q else (q, a))
        refs = []
        for g in range(b["nfaces"]):
            fs = [f for f, gg in zip(b["facets"], b["group"]) if gg == g]
            A, cs, ns = 0.0, np.zeros(3), np.zeros(3)
            for _e, c, _full in fs:
                n, a = _normal(X, c)
                A += a
                cs += a * np.mean([X[q] for q in c], axis=0)
                ns += a * n
            nn = ns / (np.linalg.norm(ns) or 1.0)
            planar = all(abs(float(np.dot(_normal(X, c)[0], nn))) > 0.9999 for _e, c, _f in fs[:200])
            refs.append({"kind": "plane" if planar else "other", "c": (cs / (A or 1.0)).tolist(), "n": nn.tolist(), "area": A})
        edges, erefs = [], []
        for ch in b["edges"]:
            P = [list(map(float, X[n])) for n in ch]
            edges.append(P)
            d = np.asarray(P[-1]) - np.asarray(P[0])
            L = float(np.linalg.norm(d))
            straight = L > 0 and all(np.linalg.norm(np.cross(np.asarray(q) - np.asarray(P[0]), d)) / L < 1e-6 * max(L, 1) for q in P)
            erefs.append({"kind": "line" if straight else "other", "c": np.mean(P, axis=0).tolist(), "n": (d / L).tolist() if L > 0 else None})
        shell = b["kind"] == "shell"
        lo, hi = np.min(V, axis=0).tolist(), np.max(V, axis=0).tolist()
        comps.append({"id": b["id"], "name": b["id"], "mkey": "inp_%s_%x" % (b["id"], abs(hash((path, os.path.getmtime(path)))) & 0xffffff),
                      "mesh": {"vertices": V, "triangles": T, "face_of_tri": fot, "face_body": [0 if shell else None] * b["nfaces"],
                               "edges": edges, "bbox": lo + hi, "wire": [i for w in sorted(wire) for i in w]},
                      "refs": refs, "erefs": erefs, "surfaces": [{"id": SHELL_ID, "name": b["id"], "color": "#5b7fb5"}] if shell else [],
                      "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0], "error": None, "elements": len(b["elements"]), "kind": b["kind"]})
    mats = {}
    for name, v in m["materials"].items():
        e = {"E": v.get("E", 210000.0), "nu": v.get("nu", 0.3), "rho": round(v.get("rho", 7850.0), 6)}
        if v.get("plastic"):
            e.update(law="plastic", hardening="isotropic", plastic=v["plastic"])
        mats[name] = e
    bodies, shells = {}, {}
    for b in M["bodies"]:
        s = b["section"] or {}
        if b["kind"] == "shell":
            shells["%s:%s" % (b["id"], SHELL_ID)] = {k: v for k, v in (("t", s.get("t")), ("material", s.get("material") or None),
                                                                     ("offset", None if s.get("offset", "mid") == "mid" else s.get("offset"))) if v}
        elif s.get("material"):
            bodies[b["id"]] = {"material": s["material"]}
    return {"components": comps, "materials": mats, "bodies": bodies, "shells": shells, "nsets": sorted(m["nsets"]),
            "warnings": m["warnings"], "nodes": len(X), "elements": len(m["elements"])}


# --------------------------------------------------------------------------- analysis input

def analysis_input(doc):
    """(bodies, mesh) of an inp source for analysis.run (see the module text)."""
    from . import analysis
    path = (doc.get("source") or {}).get("path") or ""
    M = model(path)
    m, X = M["m"], M["m"]["nodes"]
    bcfg, scfg = doc.get("bodies") or {}, doc.get("shells") or {}
    sec_of = {}                      # (comp, face) -> section of the document
    for sec in doc.get("sections") or []:
        for r in sec.get("faces") or []:
            sec_of.setdefault((str(r.get("comp")), int(r.get("face", -1))), sec)
    groups = {}                      # analysis body id -> {"cfg", "name", "kind", "elems", "faces": {(comp, fi): tris}, "surf"}
    I3 = np.hstack([np.eye(3), np.zeros((3, 1))])

    def tri_arrays(fs):
        A, B, C = [], [], []
        for _e, c, _full in fs:
            P = [np.asarray(X[n], float) for n in c]
            for t in ([(0, 1, 2)] if len(P) == 3 else [(0, 1, 2), (0, 2, 3)]):
                A.append(P[t[0]]); B.append(P[t[1]]); C.append(P[t[2]])
        return np.asarray(A), np.asarray(B), np.asarray(C)
    for b in M["bodies"]:
        cid = b["id"]
        by_face = {}
        for f, g in zip(b["facets"], b["group"]):
            by_face.setdefault(g, []).append(f)
        if b["kind"] == "solid":
            cfg = bcfg.get(cid) or {}
            if cfg.get("mode") == "off":
                continue
            groups[cid] = {"cfg": cfg, "name": cid, "kind": "solid", "elems": list(b["elements"]), "faces": by_face, "comp": cid,
                           "material": cfg.get("material") or (b["section"] or {}).get("material")}
            continue
        elem_face = {f[0]: g for f, g in zip(b["facets"], b["group"])}
        for e in b["elements"]:
            g = elem_face.get(e, 0)
            sec = sec_of.get((cid, g))
            if sec is not None:
                if (sec.get("mode") or "shell") == "off":
                    continue
                gid, cfg, name = "sec:%s" % sec.get("id"), sec, sec.get("name") or sec.get("id")
            else:
                cfg = dict((b["section"] or {}), **(scfg.get("%s:%s" % (cid, SHELL_ID)) or {}))
                if cfg.get("mode") == "off":
                    continue
                gid, name = "%s:%s" % (cid, SHELL_ID), cid
            G = groups.setdefault(gid, {"cfg": cfg, "name": name, "kind": "shell", "elems": [], "faces": {}, "comp": cid,
                                        "material": cfg.get("material") or (b["section"] or {}).get("material")})
            G["elems"].append(e)
            G["faces"].setdefault((cid, g), [])
        for gid, G in groups.items():
            if G["kind"] == "shell":
                for (c2, g), lst in G["faces"].items():
                    if c2 == cid and not lst:
                        lst += [f for f in by_face.get(g, []) if f[0] in set(G["elems"])]
    bodies, mbodies = [], {}
    for gid, G in groups.items():
        blocks = {}
        for e in G["elems"]:
            et, ns = m["elements"][e]
            blocks.setdefault(TYPE_MAP.get(et, et), []).append([e] + list(ns))
        surfs = []
        faces_by = {}
        items = G["faces"].items() if G["kind"] == "shell" else (((G["comp"], g), fs) for g, fs in G["faces"].items())
        for key, fs in items:
            if not fs:
                continue
            faces_by[(str(key[0]), int(key[1]))] = tri_arrays(fs)
            nodes = sorted(set(n for f in fs for n in f[2] or f[1]))
            surfs.append({"nodes": nodes, "facets": [list(f[2] or f[1]) for f in fs],
                          "sample": [list(map(float, X[n])) for n in nodes[:: max(1, len(nodes) // 50)]]})
        cfg = G["cfg"]
        t = float(cfg.get("t") or 0) or None
        vol = 0.0
        if G["kind"] == "solid":         # enclosed volume of the exterior facets (divergence theorem)
            for A, B, C in faces_by.values():
                vol += float(np.einsum("ij,ij->i", A, np.cross(B, C)).sum()) / 6.0
            vol = abs(vol)
        area = sum(0.5 * float(np.linalg.norm(np.cross(B - A, C - A), axis=1).sum()) for A, B, C in faces_by.values())
        en = sorted(set(n for e in G["elems"] for n in m["elements"][e][1]))
        centre = np.mean([X[n] for n in en], axis=0).tolist() if en else [0.0, 0.0, 0.0]
        bodies.append({"id": gid, "name": G["name"], "mode": G["kind"], "material": G["material"] or doc.get("default_material"),
                       "size": None, "layers": 1, "strategy": None, "t": t if G["kind"] == "shell" else None,
                       "offset": cfg.get("offset") or "mid", "comp": G["comp"], "faces": {}, "faces_by": faces_by,
                       "refs": [], "tol": 1e-6, "M": I3, "shape": None, "volume": vol, "area": area, "centre": centre,
                       "shell_layers": analysis._shell_layers(cfg, "section %s" % G["name"]) if G["kind"] == "shell" else None})
        mbodies[gid] = {"blocks": [{"type": k, "elements": v} for k, v in blocks.items()], "surfaces": surfs, "group": "inp",
                        "thickness": t or 0.0}
    used = sorted(set(n for mb in mbodies.values() for bl in mb["blocks"] for e in bl["elements"] for n in e[1:]))
    edges = {}
    for b in M["bodies"]:
        for k, ch in enumerate(b["edges"]):
            edges["%s:%d" % (b["id"], k)] = list(ch)
    mesh = {"nodes": {"ids": used, "xyz": [c for n in used for c in X[n]]}, "bodies": mbodies,
            "warnings": list(m["warnings"]), "edges": edges, "nsets": {k: v for k, v in m["nsets"].items()}}
    return bodies, mesh
