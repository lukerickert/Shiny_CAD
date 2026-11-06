# -*- coding: utf-8 -*-
"""Contents of a CalculiX / Abaqus .inp file or a Radioss starter deck (.rad) in detail: inspect(path) -> dict,
report(info) -> 96-column text.

.inp: file (size, lines, *HEADING, *INCLUDE files), keyword list (count, read by the program or not), nodes (count,
numbers, extent, coincident nodes, nodes in no element), element types (family, order, integration, nodes per element,
count, numbers, read or not), mesh quality per type (solids: volume, inverted elements, edge lengths, aspect ratio;
shells: area, edge lengths, aspect ratio, smallest and largest corner angle, warping of quadrangles), element sets
(elements, types, section, material, volume or area, mass, extent), node sets, surfaces, materials (the keywords and
their values), sections, constraints and interactions (*TIE, *COUPLING, *MPC, *EQUATION, *RIGID BODY, *CONTACT PAIR,
*SURFACE INTERACTION, *SPRING, *MASS, *ORIENTATION, *TRANSFORM, *AMPLITUDE, *INITIAL CONDITIONS), steps (procedure,
time and increments, boundary conditions, concentrated and distributed loads with their totals, output requests),
mass and centre of mass, and checks (elements with missing nodes, element sets without a section, sections without
elements or material, unused materials).
.rad: file, keyword list, nodes, element types, quality, parts (property, thickness, material) and materials.
Units as in the file; lengths are taken as mm and densities in t/mm^3 (below 1e-3) or kg/m^3.
"""
import math
import os
import re
import threading

import numpy as np

_LOCK = threading.Lock()
_CACHE = {}

READ_INP = {"*NODE", "*ELEMENT", "*ELSET", "*NSET", "*MATERIAL", "*ELASTIC", "*DENSITY", "*PLASTIC", "*SOLID SECTION",
            "*SHELL SECTION"}
CORNERS = {"tet": 4, "hex": 8, "wedge": 6, "pyr": 5, "tri": 3, "quad": 4, "line": 2}
EDGES = {"tet": [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)],
         "hex": [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)],
         "wedge": [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)],
         "pyr": [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4)],
         "tri": [(0, 1), (1, 2), (2, 0)], "quad": [(0, 1), (1, 2), (2, 3), (3, 0)], "line": [(0, 1)]}
TETS = {"tet": [(0, 1, 2, 3)],
        "hex": [(0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6)],
        "wedge": [(0, 1, 2, 3), (1, 4, 2, 3), (2, 4, 5, 3)],
        "pyr": [(0, 1, 2, 4), (0, 2, 3, 4)]}


def element_type(et):
    """{"family", "shape", "order", "nodes", "integration", "description"} of an Abaqus / CalculiX element type."""
    t = et.upper()
    info = {"family": "other", "shape": None, "order": "", "nodes": None, "integration": "", "description": t}
    m = re.match(r"^(C3D|DC3D|CPS|CPE|CAX|CPEG|DC2D|DCAX)(\d+)([A-Z]*)$", t)
    if m:
        pre, n, suf = m.group(1), int(m.group(2)), m.group(3)
        solid = pre in ("C3D", "DC3D")
        shape = {4: "tet", 10: "tet", 8: "hex", 20: "hex", 27: "hex", 6: "wedge", 15: "wedge", 5: "pyr", 13: "pyr"}.get(n) if solid \
            else {3: "tri", 6: "tri", 4: "quad", 8: "quad"}.get(n)
        quad = n in (10, 20, 27, 15, 13) if solid else n in (6, 8)
        integ = []
        if "R" in suf:
            integ.append("reduced integration")
        if "I" in suf:
            integ.append("incompatible modes")
        if "H" in suf:
            integ.append("hybrid")
        if "M" in suf:
            integ.append("modified")
        if "T" in suf:
            integ.append("coupled temperature")
        if not integ and solid:
            integ.append("full integration")
        fam = {"C3D": "solid", "DC3D": "heat transfer solid", "CPS": "plane stress", "CPE": "plane strain", "CAX": "axisymmetric",
               "CPEG": "generalized plane strain", "DC2D": "heat transfer plane", "DCAX": "heat transfer axisymmetric"}[pre]
        info.update(family=fam, shape=shape, order="quadratic" if quad else "linear", nodes=n, integration=", ".join(integ),
                    description="%s %s %s, %d nodes" % ("quadratic" if quad else "linear", {"tet": "tetrahedron", "hex": "hexahedron", "wedge": "wedge",
                                                                                         "pyr": "pyramid", "tri": "triangle", "quad": "quadrilateral"}.get(shape, "element"), fam, n))
        return info
    m = re.match(r"^(S|STRI|SC|M3D)(\d+)([A-Z0-9]*)$", t)
    if m:
        pre, n, suf = m.group(1), int(m.group(2)), m.group(3)
        if pre == "SC":                                   # continuum shell
            shape = {6: "wedge", 8: "hex"}.get(n)
            fam = "continuum shell"
        else:
            shape = {3: "tri", 6: "tri", 4: "quad", 8: "quad", 9: "quad"}.get(n)
            fam = "membrane" if pre == "M3D" else "shell"
        quad = n in (6, 8, 9) and pre != "SC"
        integ = ("reduced integration" if "R" in suf else "full integration") + (", 5 degrees of freedom per node" if "5" in suf else "")
        info.update(family=fam, shape=shape, order="quadratic" if quad else "linear", nodes=n, integration=integ,
                    description="%s %s %s, %d nodes" % ("quadratic" if quad else "linear", {"tri": "triangular", "quad": "quadrilateral",
                                                                                        "wedge": "wedge", "hex": "hexahedral"}.get(shape, ""), fam, n))
        return info
    m = re.match(r"^(B|PIPE)(\d)(\d)([A-Z]*)$", t)
    if m:
        n = int(m.group(3)) if m.group(1) == "B" else int(m.group(3))
        nn = {1: 2, 2: 3, 3: 2}.get(n, 2)
        info.update(family="beam" if m.group(1) == "B" else "pipe", shape="line", order="quadratic" if n == 2 else "cubic" if n == 3 else "linear",
                    nodes=nn, integration="reduced integration" if "R" in m.group(4) else "",
                    description="%s %s, %d nodes" % ("quadratic" if n == 2 else "cubic" if n == 3 else "linear", "beam" if m.group(1) == "B" else "pipe", nn))
        return info
    m = re.match(r"^T([23])D([23])$", t)
    if m:
        nn = int(m.group(2))
        info.update(family="truss", shape="line", order="quadratic" if nn == 3 else "linear", nodes=nn,
                    description="%s truss (%sD), %d nodes" % ("quadratic" if nn == 3 else "linear", m.group(1), nn))
        return info
    other = {"SPRING1": ("spring", 1, "spring to ground"), "SPRING2": ("spring", 2, "spring between two nodes, fixed direction"),
             "SPRINGA": ("spring", 2, "axial spring"), "DASHPOT1": ("dashpot", 1, "dashpot to ground"), "DASHPOT2": ("dashpot", 2, "dashpot"),
             "DASHPOTA": ("dashpot", 2, "axial dashpot"), "MASS": ("mass", 1, "point mass"), "ROTARYI": ("rotary inertia", 1, "rotary inertia"),
             "R3D3": ("rigid", 3, "rigid triangle"), "R3D4": ("rigid", 4, "rigid quadrilateral"), "RB3D2": ("rigid", 2, "rigid beam"),
             "GAPUNI": ("gap", 2, "unidirectional gap"), "CONN3D2": ("connector", 2, "connector"), "U1": ("user", 2, "user element (CalculiX U1 beam)"),
             "D": ("fluid", 3, "fluid network element")}
    if t in other:
        f, n, d = other[t]
        info.update(family=f, nodes=n, description=d, shape="line" if n == 2 else None)
    return info


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
            out.append(float(t.replace("D", "E").replace("d", "e")))
        except ValueError:
            out.append(None)
    return out


def _lines(path, seen=None, includes=None):
    """(line, file) of the file with the *INCLUDE files in place."""
    seen = seen if seen is not None else set()
    ap = os.path.abspath(path)
    if ap in seen:
        return []
    seen.add(ap)
    with open(path, "r", errors="replace") as f:
        raw = f.read().splitlines()
    out = []
    for ln in raw:
        s = ln.strip()
        if s[:8].upper() == "*INCLUDE":
            inc = _params(s).get("INPUT", "")
            inc = inc.strip('"') if isinstance(inc, str) else ""
            p = inc if os.path.isabs(inc) else os.path.join(os.path.dirname(path), inc)
            if includes is not None:
                includes.append({"file": inc, "found": os.path.isfile(p), "lines": 0})
            if os.path.isfile(p):
                sub = _lines(p, seen, includes)
                if includes is not None:
                    includes[-1]["lines"] = len(sub)
                out += sub
            continue
        out.append(s)
    return out


def _bbox(P):
    if not len(P):
        return None
    lo, hi = P.min(axis=0), P.max(axis=0)
    return {"min": lo.tolist(), "max": hi.tolist(), "size": (hi - lo).tolist()}


def _stats(a):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    if not len(a):
        return None
    return {"min": float(a.min()), "mean": float(a.mean()), "max": float(a.max())}


def _quality(X, idx, conn, shape):
    """Quality of the elements of one type: conn (n, corners) indices into X."""
    q = {"count": int(len(conn))}
    if not len(conn) or shape not in EDGES:
        return q
    P = X[conn]                                            # (n, corners, 3)
    L = np.stack([np.linalg.norm(P[:, b] - P[:, a], axis=1) for a, b in EDGES[shape]], axis=1)
    q["edge"] = _stats(L.ravel())
    with np.errstate(divide="ignore", invalid="ignore"):
        ar = L.max(axis=1) / L.min(axis=1)
    q["aspect"] = _stats(ar)
    q["aspect_above_10"] = int(np.sum(ar > 10))
    q["zero_edge"] = int(np.sum(L.min(axis=1) <= 0))
    if shape in TETS:
        vol = np.zeros(len(conn))
        neg = np.zeros(len(conn), bool)
        for a, b, c, d in TETS[shape]:
            v = np.einsum("ij,ij->i", np.cross(P[:, b] - P[:, a], P[:, c] - P[:, a]), P[:, d] - P[:, a]) / 6.0
            vol += v
            neg |= v <= 0
        q["volume"] = _stats(vol)
        q["volume_total"] = float(vol.sum())
        q["inverted"] = int(np.sum(vol <= 0))
        q["distorted"] = int(np.sum(neg & (vol > 0)))      # a sub-tetrahedron with zero or negative volume
        q["_vol"] = vol
    if shape in ("tri", "quad"):
        n = CORNERS[shape]
        ang = []
        for i in range(n):
            u = P[:, (i + 1) % n] - P[:, i]
            w = P[:, (i - 1) % n] - P[:, i]
            with np.errstate(divide="ignore", invalid="ignore"):
                c = np.einsum("ij,ij->i", u, w) / (np.linalg.norm(u, axis=1) * np.linalg.norm(w, axis=1))
            ang.append(np.degrees(np.arccos(np.clip(c, -1, 1))))
        A = np.stack(ang, axis=1)
        q["angle_min"] = _stats(A.min(axis=1))
        q["angle_max"] = _stats(A.max(axis=1))
        q["angle_below_30"] = int(np.sum(A.min(axis=1) < 30))
        if shape == "tri":
            area = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
        else:
            n1 = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
            n2 = np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 0])
            area = 0.5 * (np.linalg.norm(n1, axis=1) + np.linalg.norm(n2, axis=1))
            m1 = np.cross(P[:, 1] - P[:, 0], P[:, 3] - P[:, 0])   # warping: angle between the triangles of both diagonals
            m2 = np.cross(P[:, 2] - P[:, 1], P[:, 3] - P[:, 1])
            with np.errstate(divide="ignore", invalid="ignore"):
                w1 = np.einsum("ij,ij->i", n1, n2) / (np.linalg.norm(n1, axis=1) * np.linalg.norm(n2, axis=1))
                w2 = np.einsum("ij,ij->i", m1, m2) / (np.linalg.norm(m1, axis=1) * np.linalg.norm(m2, axis=1))
            warp = np.degrees(np.maximum(np.arccos(np.clip(w1, -1, 1)), np.arccos(np.clip(w2, -1, 1))))
            q["warp"] = _stats(warp)
            q["warp_above_10"] = int(np.sum(warp > 10))
        q["area"] = _stats(area)
        q["area_total"] = float(area.sum())
        q["_area"] = area
    return q


def _density_kg_m3(r):
    return r * 1e12 if r is not None and r < 1e-3 else r


# --------------------------------------------------------------------------- .inp

def _inspect_inp(path):
    includes = []
    lines = _lines(path, includes=includes)
    kws = {}                       # keyword -> count
    order = []
    nodes, elements, etypes = {}, {}, {}
    elsets, nsets, nset_gen = {}, {}, set()
    surfaces, materials, sections = [], {}, []
    cons = {k: [] for k in ("tie", "coupling", "mpc", "equation", "rigid_body", "contact_pair", "interaction", "spring",
                            "mass", "orientation", "transform", "amplitude", "initial", "distributing", "kinematic")}
    steps, cur_step = [], None
    heading = []
    kw, prm, mat, pend, block = None, {}, None, [], None
    elem_bad = 0

    def flush(vals):
        nonlocal elem_bad
        if not vals:
            return
        try:
            eid, ns = int(vals[0]), [int(v) for v in vals[1:]]
        except ValueError:
            elem_bad += 1
            return
        et = str(prm.get("TYPE", "")).upper()
        elements[eid] = (et, ns)
        etypes.setdefault(et, []).append(eid)
        es = prm.get("ELSET")
        if isinstance(es, str):
            elsets.setdefault(es.upper(), []).append(eid)

    for line in lines:
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            if kw == "*ELEMENT" and pend:
                flush(pend)
                pend = []
            kw = line.split(",")[0].strip().upper()
            prm = _params(line)
            kws[kw] = kws.get(kw, 0) + 1
            if kw not in order:
                order.append(kw)
            block = None
            if kw == "*MATERIAL":
                mat = str(prm.get("NAME", "MATERIAL")).upper()
                materials[mat] = {"keywords": [], "used": False}
            elif kw in ("*ELASTIC", "*DENSITY", "*PLASTIC", "*EXPANSION", "*CONDUCTIVITY", "*SPECIFIC HEAT", "*HYPERELASTIC",
                        "*DAMPING", "*CREEP", "*DEFORMATION PLASTICITY", "*USER MATERIAL", "*CYCLIC HARDENING", "*HYPERFOAM",
                        "*ANISO HYPERELASTIC", "*DEPVAR") and mat:
                materials[mat]["keywords"].append(kw[1:] + "".join(", %s=%s" % (k, v) if v is not True else ", %s" % k for k, v in prm.items()))
                block = {"kw": kw, "rows": []}
                materials[mat].setdefault("_rows", {})[kw] = block["rows"]
            elif kw.endswith(" SECTION"):
                mat = None
                sec = {"kind": kw[1:-8].lower(), "elset": str(prm.get("ELSET", "")).upper(), "material": str(prm.get("MATERIAL", "")).upper(),
                       "params": {k: v for k, v in prm.items() if k not in ("ELSET", "MATERIAL")}, "data": []}
                sections.append(sec)
                block = {"kw": kw, "rows": sec["data"]}
            elif kw == "*SURFACE":
                surfaces.append({"name": str(prm.get("NAME", "")).upper(), "type": str(prm.get("TYPE", "ELEMENT")).upper(), "entries": 0})
            elif kw == "*HEADING":
                block = {"kw": kw, "rows": heading}
            elif kw == "*STEP":
                cur_step = {"name": str(prm.get("NAME", "Step %d" % (len(steps) + 1))), "params": {k: v for k, v in prm.items() if k != "NAME"},
                            "procedure": None, "proc_params": {}, "proc_data": [], "boundary": [], "cload": [], "dload": [], "dsload": [],
                            "outputs": [], "other": [], "amplitude_refs": set()}
                steps.append(cur_step)
            elif kw == "*END STEP":
                cur_step = None
            elif cur_step is not None:
                if kw in ("*STATIC", "*DYNAMIC", "*FREQUENCY", "*BUCKLE", "*HEAT TRANSFER", "*COUPLED TEMPERATURE-DISPLACEMENT",
                          "*MODAL DYNAMIC", "*STEADY STATE DYNAMICS", "*VISCO", "*UNCOUPLED TEMPERATURE-DISPLACEMENT", "*COMPLEX FREQUENCY",
                          "*GREEN", "*SENSITIVITY", "*ELECTROMAGNETICS"):
                    cur_step["procedure"] = kw[1:]
                    cur_step["proc_params"] = {k: v for k, v in prm.items()}
                    block = {"kw": kw, "rows": cur_step["proc_data"]}
                elif kw in ("*BOUNDARY", "*CLOAD", "*DLOAD", "*DSLOAD"):
                    block = {"kw": kw, "rows": cur_step[kw[1:].lower()], "params": prm}
                    if prm.get("AMPLITUDE"):
                        cur_step["amplitude_refs"].add(str(prm["AMPLITUDE"]).upper())
                elif kw in ("*NODE FILE", "*EL FILE", "*NODE PRINT", "*EL PRINT", "*CONTACT FILE", "*CONTACT PRINT", "*SECTION PRINT",
                            "*NODE OUTPUT", "*ELEMENT OUTPUT", "*CONTACT OUTPUT", "*OUTPUT"):
                    out = {"kw": kw[1:], "params": {k: v for k, v in prm.items()}, "vars": []}
                    cur_step["outputs"].append(out)
                    block = {"kw": kw, "rows": out["vars"]}
                else:
                    cur_step["other"].append(kw[1:])
            if kw == "*TIE":
                cons["tie"].append({"name": str(prm.get("NAME", "")), "params": {k: v for k, v in prm.items() if k != "NAME"}, "pairs": []})
                block = {"kw": kw, "rows": cons["tie"][-1]["pairs"]}
            elif kw == "*COUPLING":
                cons["coupling"].append({"name": str(prm.get("CONSTRAINT NAME", "")), "ref": str(prm.get("REF NODE", "")),
                                         "surface": str(prm.get("SURFACE", "")), "type": None})
            elif kw in ("*KINEMATIC", "*DISTRIBUTING") and cons["coupling"]:
                cons["coupling"][-1]["type"] = kw[1:].lower()
            elif kw == "*MPC":
                block = {"kw": kw, "rows": cons["mpc"]}
            elif kw == "*EQUATION":
                cons["equation"].append(0)
                block = {"kw": kw, "rows": []}
            elif kw == "*RIGID BODY":
                cons["rigid_body"].append({k: v for k, v in prm.items()})
            elif kw == "*CONTACT PAIR":
                cons["contact_pair"].append({"params": {k: v for k, v in prm.items()}, "pairs": []})
                block = {"kw": kw, "rows": cons["contact_pair"][-1]["pairs"]}
            elif kw == "*SURFACE INTERACTION":
                cons["interaction"].append({"name": str(prm.get("NAME", "")), "behaviour": [], "friction": None})
            elif kw == "*SURFACE BEHAVIOR" and cons["interaction"]:
                cons["interaction"][-1]["behaviour"].append(", ".join("%s=%s" % (k, v) for k, v in prm.items() if v is not True))
            elif kw == "*FRICTION" and cons["interaction"]:
                block = {"kw": kw, "rows": []}
                cons["interaction"][-1]["_fric"] = block["rows"]
            elif kw == "*SPRING":
                cons["spring"].append({"elset": str(prm.get("ELSET", "")), "data": []})
                block = {"kw": kw, "rows": cons["spring"][-1]["data"]}
            elif kw == "*MASS":
                cons["mass"].append({"elset": str(prm.get("ELSET", "")), "data": []})
                block = {"kw": kw, "rows": cons["mass"][-1]["data"]}
            elif kw == "*ORIENTATION":
                cons["orientation"].append({"name": str(prm.get("NAME", "")), "system": str(prm.get("SYSTEM", "RECTANGULAR"))})
            elif kw == "*TRANSFORM":
                cons["transform"].append({"nset": str(prm.get("NSET", "")), "type": str(prm.get("TYPE", "R"))})
            elif kw == "*AMPLITUDE":
                cons["amplitude"].append({"name": str(prm.get("NAME", "")).upper(), "points": [], "time": str(prm.get("TIME", "STEP TIME"))})
                block = {"kw": kw, "rows": cons["amplitude"][-1]["points"]}
            elif kw == "*INITIAL CONDITIONS":
                cons["initial"].append({"type": str(prm.get("TYPE", "")), "rows": 0})
                block = {"kw": kw, "rows": []}
            continue
        # data lines
        if kw == "*NODE":
            v = _nums(line)
            if len(v) >= 4 and v[0] is not None:
                nodes[int(v[0])] = (v[1] or 0.0, v[2] or 0.0, v[3] or 0.0)
                if isinstance(prm.get("NSET"), str):
                    nsets.setdefault(prm["NSET"].upper(), []).append(int(v[0]))
            elif len(v) >= 3 and v[0] is not None:
                nodes[int(v[0])] = (v[1] or 0.0, v[2] or 0.0, 0.0)
        elif kw == "*ELEMENT":
            pend += line.replace(",", " ").split()
            if not line.rstrip().endswith(","):
                flush(pend)
                pend = []
        elif kw in ("*ELSET", "*NSET"):
            name = str(prm.get("ELSET" if kw == "*ELSET" else "NSET", "")).upper()
            dst = (elsets if kw == "*ELSET" else nsets).setdefault(name, [])
            if prm.get("GENERATE"):
                v = [int(x) for x in _nums(line) if x is not None]
                if len(v) >= 2:
                    dst += list(range(v[0], v[1] + 1, v[2] if len(v) > 2 and v[2] else 1))
                if kw == "*NSET":
                    nset_gen.add(name)
            else:
                for t in line.replace(",", " ").split():
                    try:
                        dst.append(int(float(t)))
                    except ValueError:
                        dst += (elsets if kw == "*ELSET" else nsets).get(t.upper(), [])
        elif kw == "*SURFACE" and surfaces:
            surfaces[-1]["entries"] += 1
        elif kw == "*EQUATION" and cons["equation"]:
            block["rows"].append(line)
            cons["equation"][-1] += 1
        elif kw == "*INITIAL CONDITIONS" and cons["initial"]:
            cons["initial"][-1]["rows"] += 1
        elif block is not None:
            if kw == "*HEADING":
                block["rows"].append(line)
            elif kw in ("*TIE", "*CONTACT PAIR", "*MPC") or (kw in ("*NODE FILE", "*EL FILE", "*NODE PRINT", "*EL PRINT", "*CONTACT FILE",
                                                                   "*CONTACT PRINT", "*SECTION PRINT", "*NODE OUTPUT", "*ELEMENT OUTPUT",
                                                                   "*CONTACT OUTPUT")):
                block["rows"].append([t.strip() for t in line.split(",") if t.strip()])
            elif kw in ("*BOUNDARY", "*CLOAD", "*DLOAD", "*DSLOAD"):
                block["rows"].append([t.strip() for t in line.split(",")])
            else:
                block["rows"].append(_nums(line))
    if kw == "*ELEMENT" and pend:
        flush(pend)
    from .inpmodel import SOLID, SHELL
    return {"path": path, "includes": includes, "nlines": len(lines), "heading": " ".join(heading)[:200], "keywords": kws,
            "order": order, "nodes": nodes, "elements": elements, "etypes": etypes, "elsets": elsets, "nsets": nsets,
            "nset_gen": nset_gen, "surfaces": surfaces, "materials": materials, "sections": sections, "cons": cons, "steps": steps,
            "elem_bad": elem_bad, "read_types": set(SOLID) | set(SHELL)}


def _material_summary(m):
    rows = m.get("_rows", {})
    out = {"keywords": m["keywords"]}
    e = rows.get("*ELASTIC")
    if e and e[0] and len(e[0]) >= 2:
        out["E"], out["nu"] = e[0][0], e[0][1]
        if len(e) > 1:
            out["elastic_rows"] = len(e)
    d = rows.get("*DENSITY")
    if d and d[0]:
        out["rho_file"] = d[0][0]
        out["rho"] = _density_kg_m3(d[0][0])
    p = rows.get("*PLASTIC")
    if p:
        pts = [r[:2] for r in p if len(r) >= 2 and r[0] is not None and r[1] is not None]
        if pts:
            out["plastic"] = {"points": len(pts), "yield": pts[0][0], "last_stress": pts[-1][0], "last_strain": pts[-1][1]}
    x = rows.get("*EXPANSION")
    if x and x[0]:
        out["alpha"] = x[0][0]
    h = rows.get("*HYPERELASTIC")
    if h:
        out["hyperelastic_constants"] = [v for r in h for v in r if v is not None][:8]
    dm = rows.get("*DAMPING")
    if dm:
        out["damping"] = True
    return out


def _finish(raw, rad=False):
    nodes = raw["nodes"]
    ids = np.array(sorted(nodes), np.int64) if nodes else np.zeros(0, np.int64)
    X = np.array([nodes[i] for i in ids], float) if len(ids) else np.zeros((0, 3))
    pos = {int(n): k for k, n in enumerate(ids)}
    info = {"file": {"name": os.path.basename(raw["path"]), "path": raw["path"], "kind": "rad" if rad else "inp",
                     "size_kb": os.path.getsize(raw["path"]) / 1024.0, "lines": raw["nlines"], "heading": raw.get("heading", ""),
                     "includes": raw.get("includes", []), "modified": os.path.getmtime(raw["path"])}}
    read = raw.get("read_keywords") or READ_INP
    info["keywords"] = [{"keyword": k, "count": raw["keywords"][k], "read": k in read} for k in raw["order"]]
    # nodes
    used = set()
    missing = 0
    for _e, (_t, ns) in raw["elements"].items():
        for n in ns:
            if n in pos:
                used.add(n)
            elif n:
                missing += 1
    diag = float(np.linalg.norm(X.max(axis=0) - X.min(axis=0))) if len(X) else 0.0
    coinc = 0
    if len(X) > 1:
        tol = max(diag * 1e-6, 1e-9)
        key = np.round(X / tol).astype(np.int64)
        _u, cnt = np.unique(key, axis=0, return_counts=True)
        coinc = int((cnt[cnt > 1] - 1).sum())
    info["nodes"] = {"count": int(len(ids)), "first": int(ids[0]) if len(ids) else None, "last": int(ids[-1]) if len(ids) else None,
                     "bbox": _bbox(X), "diagonal": diag, "coincident": coinc, "unused": int(len(ids) - len(used)),
                     "elements_with_missing_nodes": 0}
    # element types and quality
    types = []
    by_elem_measure = {}
    bad_elems = set()
    for et, eids in sorted(raw["etypes"].items(), key=lambda x: -len(x[1])):
        ti = element_type(et)
        nc = CORNERS.get(ti["shape"])
        row = dict(ti, type=et, count=len(eids), first=min(eids), last=max(eids),
                   read=et in raw.get("read_types", ()), nodes_given=None)
        lens = sorted(set(len(raw["elements"][e][1]) for e in eids))
        row["nodes_given"] = lens
        if nc:
            good = [e for e in eids if len(raw["elements"][e][1]) >= nc and all(n in pos for n in raw["elements"][e][1][:nc])]
            bad_elems.update(set(eids) - set(good))
            if good:
                conn = np.array([[pos[n] for n in raw["elements"][e][1][:nc]] for e in good], np.int64)
                q = _quality(X, None, conn, ti["shape"])
                for k, arr in (("_vol", q.pop("_vol", None)), ("_area", q.pop("_area", None))):
                    if arr is not None:
                        for e, v in zip(good, arr):
                            by_elem_measure[e] = (k, float(v))
                row["quality"] = q
        types.append(row)
    info["nodes"]["elements_with_missing_nodes"] = len(bad_elems)
    info["element_types"] = types
    info["elements"] = {"count": len(raw["elements"]), "first": min(raw["elements"]) if raw["elements"] else None,
                        "last": max(raw["elements"]) if raw["elements"] else None}
    # materials
    mats = {name: _material_summary(m) for name, m in raw["materials"].items()}
    # sections and element sets
    sec_of = {}
    secs = []
    for s in raw["sections"]:
        data = [v for r in s["data"] for v in r if v is not None]
        row = {"kind": s["kind"], "elset": s["elset"], "material": s["material"],
               "params": {k: (v if v is not True else "") for k, v in s["params"].items()}, "data": data[:6],
               "elements": len(raw["elsets"].get(s["elset"], [])), "elset_found": s["elset"] in raw["elsets"],
               "material_found": (not s["material"]) or s["material"] in mats}
        if s["kind"] == "shell" and data:
            row["t"] = data[0]
        if s["kind"] == "beam":
            row["section"] = str(s["params"].get("SECTION", ""))
        secs.append(row)
        sec_of.setdefault(s["elset"], row)
        if s["material"] in raw["materials"]:
            raw["materials"][s["material"]]["used"] = True
    info["sections"] = secs
    esets = []
    tot_mass, mom = 0.0, np.zeros(3)
    for name, eids in sorted(raw["elsets"].items()):
        es = [e for e in eids if e in raw["elements"]]
        typ = {}
        for e in es:
            typ[raw["elements"][e][0]] = typ.get(raw["elements"][e][0], 0) + 1
        s = sec_of.get(name)
        vol = sum(v for e in es for k, v in [by_elem_measure.get(e, ("", 0.0))] if k == "_vol")
        area = sum(v for e in es for k, v in [by_elem_measure.get(e, ("", 0.0))] if k == "_area")
        row = {"name": name, "elements": len(es), "missing": len(eids) - len(es), "types": typ,
               "section": s["kind"] if s else None, "material": s["material"] if s else None}
        if vol:
            row["volume"] = vol
        if area:
            row["area"] = area
        if s and s.get("t") and area:
            row["volume"] = area * s["t"]
        rho = (mats.get(s["material"]) or {}).get("rho") if s else None
        if rho and row.get("volume"):
            row["mass_kg"] = row["volume"] * 1e-9 * rho
            nn = sorted(set(n for e in es for n in raw["elements"][e][1] if n in pos))
            if nn:
                c = X[[pos[n] for n in nn]].mean(axis=0)
                tot_mass += row["mass_kg"]
                mom += row["mass_kg"] * c
        nn = [pos[n] for e in es for n in raw["elements"][e][1] if n in pos]
        row["bbox"] = _bbox(X[sorted(set(nn))]) if nn else None
        esets.append(row)
    info["elsets"] = esets
    info["nsets"] = [{"name": n, "nodes": len(v), "missing": sum(1 for x in v if x not in pos), "generated": n in raw.get("nset_gen", set()),
                      "bbox": _bbox(X[[pos[x] for x in v if x in pos]]) if any(x in pos for x in v) else None}
                     for n, v in sorted(raw["nsets"].items())]
    info["surfaces"] = raw.get("surfaces", [])
    for name, m in raw["materials"].items():
        mats[name]["used"] = m.get("used", False)
    info["materials"] = [dict(v, name=k) for k, v in mats.items()]
    from . import matcurve
    info["curves"] = {"materials": {k: matcurve.inp(m) for k, m in raw["materials"].items() if matcurve.inp(m)}, "amplitudes": [], "functions": []}
    info["mass"] = {"kg": tot_mass, "centre": (mom / tot_mass).tolist() if tot_mass > 0 else None}
    # constraints, steps
    c = raw.get("cons") or {}
    cons = []
    for t in c.get("tie", []):
        cons.append(["*TIE", t["name"], "; ".join(" / ".join(p) for p in t["pairs"]) + "".join(" %s=%s" % kv for kv in t["params"].items() if kv[1] is not True)])
    for t in c.get("coupling", []):
        cons.append(["*COUPLING", t["name"], "ref node %s, surface %s, %s" % (t["ref"], t["surface"], t["type"] or "?")])
    if c.get("mpc"):
        cons.append(["*MPC", "", "%d line(s): %s" % (len(c["mpc"]), ", ".join(sorted(set(r[0].upper() for r in c["mpc"] if r))))])
    if c.get("equation"):
        cons.append(["*EQUATION", "", "%d equation block(s), %d data line(s)" % (len(c["equation"]), sum(c["equation"]))])
    for r in c.get("rigid_body", []):
        cons.append(["*RIGID BODY", "", ", ".join("%s=%s" % kv for kv in r.items() if kv[1] is not True)])
    for p in c.get("contact_pair", []):
        cons.append(["*CONTACT PAIR", str(p["params"].get("INTERACTION", "")), "%s; %s" % (p["params"].get("TYPE", ""), "; ".join(" / ".join(x) for x in p["pairs"]))])
    for s in c.get("interaction", []):
        fr = [v for r in s.get("_fric", []) for v in r if v is not None]
        cons.append(["*SURFACE INTERACTION", s["name"], "; ".join(s["behaviour"]) + ("; friction mu %g" % fr[0] if fr else "")])
    for s in c.get("spring", []):
        cons.append(["*SPRING", s["elset"], ", ".join("%g" % v for r in s["data"] for v in r if v is not None)[:80]])
    for s in c.get("mass", []):
        cons.append(["*MASS", s["elset"], ", ".join("%g" % v for r in s["data"] for v in r if v is not None)[:80]])
    for s in c.get("orientation", []):
        cons.append(["*ORIENTATION", s["name"], s["system"]])
    for s in c.get("transform", []):
        cons.append(["*TRANSFORM", s["nset"], "type %s" % s["type"]])
    for s in c.get("amplitude", []):
        pts = [v for r in s["points"] for v in r if v is not None]
        cons.append(["*AMPLITUDE", s["name"], "%d point(s), %s, t %g to %g" % (len(pts) // 2, s["time"], pts[0], pts[-2]) if len(pts) >= 2 else "no points"])
    for s in c.get("initial", []):
        cons.append(["*INITIAL CONDITIONS", s["type"], "%d line(s)" % s["rows"]])
    info["constraints"] = cons
    for s_ in c.get("amplitude", []):
        pts = [v for r in s_["points"] for v in r if v is not None]
        if len(pts) >= 2:
            info["curves"]["amplitudes"].append({"name": s_["name"], "time": s_["time"], "t": pts[0:len(pts) // 2 * 2:2], "v": pts[1:len(pts) // 2 * 2:2]})
    st = []
    for s in raw.get("steps", []):
        pd = [v for r in s["proc_data"] for v in r if v is not None]
        bnd = s["boundary"]
        targets = sorted(set(r[0].upper() for r in bnd if r and r[0]))
        fsum = np.zeros(6)
        for r in s["cload"]:
            try:
                d, v = int(float(r[1])), float(r[2])
            except (IndexError, ValueError):
                continue
            tgt = r[0].upper()
            n = 1
            if not tgt.lstrip("-").isdigit():
                n = len(raw["nsets"].get(tgt, []))
            if 1 <= d <= 6:
                fsum[d - 1] += v * n
        dl = {}
        for r in s["dload"]:
            if len(r) >= 2:
                dl[r[1].upper()] = dl.get(r[1].upper(), 0) + 1
        st.append({"name": s["name"], "params": {k: (v if v is not True else "") for k, v in s["params"].items()}, "procedure": s["procedure"],
                   "proc_params": {k: (v if v is not True else "") for k, v in s["proc_params"].items()}, "proc_data": pd[:6],
                   "boundary": len(bnd), "boundary_targets": targets[:12], "cload": len(s["cload"]), "cload_total": fsum.tolist(),
                   "dload": dl, "dsload": len(s["dsload"]), "amplitudes": sorted(s["amplitude_refs"]),
                   "outputs": [{"kw": o["kw"], "params": {k: (v if v is not True else "") for k, v in o["params"].items()},
                                "vars": sorted(set(x for r in o["vars"] for x in r))} for o in s["outputs"]],
                   "other": sorted(set(s["other"]))})
    info["steps"] = st
    # checks
    chk = []
    if info["nodes"]["elements_with_missing_nodes"]:
        chk.append("%d element(s) refer to nodes that are not in the file" % info["nodes"]["elements_with_missing_nodes"])
    if raw.get("elem_bad"):
        chk.append("%d element line(s) not readable" % raw["elem_bad"])
    if info["nodes"]["coincident"]:
        chk.append("%d coincident node(s) (distance below 1e-6 x the model diagonal)" % info["nodes"]["coincident"])
    if info["nodes"]["unused"]:
        chk.append("%d node(s) in no element" % info["nodes"]["unused"])
    for t in types:
        q = t.get("quality") or {}
        if q.get("inverted"):
            chk.append("%s: %d inverted element(s) (zero or negative volume)" % (t["type"], q["inverted"]))
        if q.get("zero_edge"):
            chk.append("%s: %d element(s) with a zero-length edge" % (t["type"], q["zero_edge"]))
        if not t["read"]:
            chk.append("%s: %d element(s) not used as geometry by the program" % (t["type"], t["count"]))
    for s in secs:
        if not s["elset_found"]:
            chk.append("%s section: element set %s not found" % (s["kind"], s["elset"]))
        if not s["material_found"]:
            chk.append("%s section %s: material %s not found" % (s["kind"], s["elset"], s["material"]))
    insec = set()
    for s in raw["sections"]:
        insec.update(raw["elsets"].get(s["elset"], []))
    nosec = sum(1 for e, (t, _n) in raw["elements"].items() if e not in insec and element_type(t)["family"] in ("solid", "shell", "membrane", "beam", "truss", "continuum shell"))
    if nosec and raw["sections"]:
        chk.append("%d element(s) in no section" % nosec)
    for m in info["materials"]:
        if not m["used"] and raw["sections"]:
            chk.append("material %s is not used by a section" % m["name"])
    for s in info["nsets"]:
        if s["missing"]:
            chk.append("node set %s: %d node(s) not in the file" % (s["name"], s["missing"]))
    for s in esets:
        if s["missing"]:
            chk.append("element set %s: %d element(s) not in the file" % (s["name"], s["missing"]))
    unread = [k["keyword"] for k in info["keywords"] if not k["read"]]
    if unread:
        chk.append("keywords not used by the program (supports, loads and steps are set in the tab): " + ", ".join(unread[:30]))
    info["checks"] = chk
    return info


# --------------------------------------------------------------------------- .rad

RAD_READ = {"/BEGIN", "/NODE", "/SHELL", "/SH3N", "/BRICK", "/TETRA4", "/PART", "/PROP/SHELL", "/PROP/TYPE1", "/PROP/SOLID",
            "/PROP/TYPE14", "/MAT", "/GRNOD/NODE"}
RAD_TYPE = {"SHELL": "S4", "SH3N": "S3", "BRICK": "C3D8", "TETRA4": "C3D4", "TETRA10": "C3D10", "BRIC20": "C3D20", "PENTA6": "C3D6",
            "BEAM": "B31", "TRUSS": "T3D2", "SPRING": "SPRINGA"}


def _inspect_rad(path):
    from . import radmodel
    lines = radmodel._lines(path)
    kws, order = {}, []
    for ln in lines:
        if ln.startswith("/"):
            parts = [t for t in ln.strip().split("/") if t]
            k = "/" + "/".join(p for p in parts[:2] if not p.lstrip("-").isdigit()) if parts else ln
            if parts and parts[0].upper() in ("NODE", "SHELL", "SH3N", "BRICK", "TETRA4", "PART", "MAT", "BEAM", "TRUSS", "SPRING", "TETRA10"):
                k = "/" + parts[0].upper() + ("/" + parts[1].upper() if parts[0].upper() == "MAT" and len(parts) > 1 else "")
            kws[k] = kws.get(k, 0) + 1
            if k not in order:
                order.append(k)
    m = radmodel.read(path)
    etypes = {}
    for e, (et, _ns) in m["elements"].items():
        etypes.setdefault(et, []).append(e)
    mats = {}
    for name, v in m["materials"].items():
        mats[name] = {"keywords": [], "used": True, "_rows": {}}
        if v.get("E"):
            mats[name]["_rows"]["*ELASTIC"] = [[v["E"], v.get("nu", 0.3)]]
        if v.get("rho"):
            mats[name]["_rows"]["*DENSITY"] = [[v["rho"]]]
    secs = [{"kind": s["kind"], "elset": s["elset"], "material": s["material"], "params": {}, "data": [[s["t"]]] if s.get("t") else []}
            for s in m["sections"]]
    raw = {"path": path, "nlines": len(lines), "keywords": kws, "order": order, "nodes": m["nodes"], "elements": m["elements"],
           "etypes": etypes, "elsets": m["elsets"], "nsets": m["nsets"], "materials": mats, "sections": secs,
           "read_types": set(etypes), "read_keywords": {k for k in kws if any(k.upper().startswith(r) for r in RAD_READ)}}
    info = _finish(raw, rad=True)
    from . import matcurve
    rc = matcurve.rad(lines)
    info["curves"] = {"materials": rc["materials"], "amplitudes": [], "functions": rc["functions"]}
    info["checks"] = list(m.get("warnings") or []) + info["checks"]
    return info, raw


def _load(path):
    """(info, raw) of the file, cached by path, modification time and size."""
    if not os.path.isfile(path):
        from .inpmodel import InpError
        raise InpError("file not found: %s" % path)
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime, st.st_size)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    if path.lower().endswith(".rad"):
        info, raw = _inspect_rad(path)
    else:
        raw = _inspect_inp(path)
        info = _finish(raw)
    with _LOCK:
        if len(_CACHE) > 2:
            _CACHE.clear()
        _CACHE[key] = (info, raw)
    return info, raw


def inspect(path):
    """Contents of the file (cached by path, modification time and size)."""
    return _load(path)[0]


def raw(path):
    """Parsed file (nodes, elements, sets, sections, materials; cached with inspect)."""
    return _load(path)[1]


# --------------------------------------------------------------------------- report

W = 96


def _g(v, d=5):
    if v is None:
        return "-"
    if isinstance(v, str):
        return v
    if v == 0:
        return "0"
    a = abs(v)
    return ("%.*e" % (d - 1, v)) if (a < 1e-3 or a >= 1e7) else ("%.*g" % (d, v))


def _table(head, rows, widths):
    out = ["".join(("%-*s" if i == 0 else "%*s") % (w, h) for i, (h, w) in enumerate(zip(head, widths))), "-" * sum(widths)]
    for r in rows:
        out.append("".join(("%-*s" if i == 0 else "%*s") % (w, str(c)[:w - 1] if i else str(c)[:w - 1]) for i, (c, w) in enumerate(zip(r, widths))))
    return out


def report(info):
    """Text report (96 columns)."""
    import time
    L = ["=" * W, "INPUT FILE: %s" % info["file"]["name"], "=" * W]
    f = info["file"]
    L += ["Path      : %s" % f["path"], "Size      : %.1f kB, %d lines (with the include files)" % (f["size_kb"], f["lines"]),
          "Modified  : %s" % time.strftime("%Y-%m-%d %H:%M", time.localtime(f["modified"]))]
    if f.get("heading"):
        L.append("Heading   : %s" % f["heading"])
    for i in f.get("includes") or []:
        L.append("Include   : %s (%s)" % (i["file"], "%d lines" % i["lines"] if i["found"] else "not found"))
    n = info["nodes"]
    L += ["", "NODES", "-" * W, "Count %d, numbers %s to %s" % (n["count"], n["first"], n["last"])]
    if n["bbox"]:
        b = n["bbox"]
        L.append("Extent (mm): x %s to %s, y %s to %s, z %s to %s; size %s x %s x %s; diagonal %s" % (
            _g(b["min"][0]), _g(b["max"][0]), _g(b["min"][1]), _g(b["max"][1]), _g(b["min"][2]), _g(b["max"][2]),
            _g(b["size"][0]), _g(b["size"][1]), _g(b["size"][2]), _g(n["diagonal"])))
    L.append("Coincident nodes %d; nodes in no element %d; elements with missing nodes %d" % (n["coincident"], n["unused"], n["elements_with_missing_nodes"]))
    L += ["", "ELEMENT TYPES (%d elements)" % info["elements"]["count"], "-" * W]
    L += _table(["Type", "Count", "Numbers", "Family", "Order", "Nodes", "Read"],
                [[t["type"], t["count"], "%d-%d" % (t["first"], t["last"]), t["family"], t["order"], "/".join(map(str, t["nodes_given"])),
                  "yes" if t["read"] else "no"] for t in info["element_types"]], [10, 10, 18, 22, 12, 12, 12])
    for t in info["element_types"]:
        L.append("%s: %s%s" % (t["type"], t["description"], ("; " + t["integration"]) if t.get("integration") else ""))
    L += ["", "MESH QUALITY (corner nodes; aspect ratio: longest / shortest edge)", "-" * W]
    for t in info["element_types"]:
        q = t.get("quality")
        if not q:
            continue
        s = []
        if q.get("edge"):
            s.append("edge %s to %s mm (mean %s)" % (_g(q["edge"]["min"]), _g(q["edge"]["max"]), _g(q["edge"]["mean"])))
        if q.get("aspect"):
            s.append("aspect ratio max %s, mean %s, above 10: %d" % (_g(q["aspect"]["max"], 4), _g(q["aspect"]["mean"], 4), q["aspect_above_10"]))
        if q.get("volume"):
            s.append("volume %s to %s mm^3, total %s mm^3, inverted %d" % (_g(q["volume"]["min"]), _g(q["volume"]["max"]), _g(q["volume_total"]), q["inverted"]))
        if q.get("area"):
            s.append("area %s to %s mm^2, total %s mm^2" % (_g(q["area"]["min"]), _g(q["area"]["max"]), _g(q["area_total"])))
        if q.get("angle_min"):
            s.append("corner angle %s to %s deg, below 30 deg: %d" % (_g(q["angle_min"]["min"], 4), _g(q["angle_max"]["max"], 4), q["angle_below_30"]))
        if q.get("warp"):
            s.append("warping max %s deg, above 10 deg: %d" % (_g(q["warp"]["max"], 4), q["warp_above_10"]))
        L.append("%s (%d): %s" % (t["type"], q["count"], "; ".join(s)))
    L += ["", "ELEMENT SETS", "-" * W]
    L += _table(["Name", "Elements", "Types", "Section", "Material", "Vol mm^3", "Mass kg"],
                [[e["name"], e["elements"], " ".join("%s:%d" % kv for kv in e["types"].items()), e["section"] or "-", e["material"] or "-",
                  _g(e.get("volume"), 4), _g(e.get("mass_kg"), 4)] for e in info["elsets"]], [32, 9, 14, 8, 11, 11, 11])
    if info["mass"]["kg"]:
        L.append("Total mass of the element sets with a section and a density: %s kg, centre of mass (%s) mm" % (
            _g(info["mass"]["kg"]), ", ".join(_g(v) for v in info["mass"]["centre"])))
    L += ["", "NODE SETS", "-" * W]
    L += _table(["Name", "Nodes", "Generated", "Extent x / y / z (mm)"],
                [[s["name"], s["nodes"], "yes" if s["generated"] else "", " / ".join("%s..%s" % (_g(a, 4), _g(b, 4)) for a, b in zip(s["bbox"]["min"], s["bbox"]["max"])) if s["bbox"] else "-"]
                 for s in info["nsets"]], [32, 8, 10, 46])
    if info["surfaces"]:
        L += ["", "SURFACES", "-" * W]
        L += _table(["Name", "Type", "Lines"], [[s["name"], s["type"], s["entries"]] for s in info["surfaces"]], [40, 20, 10])
    L += ["", "MATERIALS", "-" * W]
    for m in info["materials"]:
        s = []
        if m.get("E") is not None:
            s.append("E %s MPa, nu %s" % (_g(m["E"]), _g(m["nu"])))
        if m.get("rho") is not None:
            s.append("density %s kg/m^3" % _g(m["rho"]) + (" (%s in the file)" % _g(m["rho_file"]) if m["rho_file"] != m["rho"] else ""))
        if m.get("plastic"):
            p = m["plastic"]
            s.append("plastic %d points, yield %s MPa, last %s MPa at %s" % (p["points"], _g(p["yield"]), _g(p["last_stress"]), _g(p["last_strain"])))
        if m.get("alpha") is not None:
            s.append("expansion %s 1/K" % _g(m["alpha"]))
        if m.get("hyperelastic_constants"):
            s.append("hyperelastic " + ", ".join(_g(v) for v in m["hyperelastic_constants"]))
        L.append("%s%s: %s" % (m["name"], "" if m.get("used") else " (not used)", "; ".join(s)))
        if m.get("keywords"):
            L.append("    " + "; ".join(m["keywords"])[:W - 4])
    L += ["", "SECTIONS", "-" * W]
    L += _table(["Element set", "Kind", "Material", "Elements", "Thickness", "Parameters"],
                [[s["elset"], s["kind"], s["material"] or "-", s["elements"], _g(s.get("t")), " ".join("%s=%s" % kv for kv in s["params"].items())]
                 for s in info["sections"]], [32, 8, 14, 10, 10, 22])
    if info["constraints"]:
        L += ["", "CONSTRAINTS, INTERACTIONS, AMPLITUDES, INITIAL CONDITIONS", "-" * W]
        L += _table(["Keyword", "Name", "Content"], info["constraints"], [22, 20, 54])
    if info["steps"]:
        L += ["", "STEPS", "-" * W]
        for k, s in enumerate(info["steps"]):
            L.append("%d. %s: %s %s%s" % (k + 1, s["name"], s["procedure"] or "(no procedure)", " ".join("%s=%s" % kv for kv in s["proc_params"].items()),
                                         (" [" + " ".join("%s=%s" % kv for kv in s["params"].items()) + "]") if s["params"] else ""))
            if s["proc_data"]:
                L.append("   data: " + ", ".join(_g(v) for v in s["proc_data"]))
            L.append("   *BOUNDARY %d line(s) on %s; *CLOAD %d line(s), total F (%s) N, M (%s) N mm; *DLOAD %s; *DSLOAD %d" % (
                s["boundary"], ", ".join(s["boundary_targets"]) or "-", s["cload"], ", ".join(_g(v) for v in s["cload_total"][:3]),
                ", ".join(_g(v) for v in s["cload_total"][3:]), ", ".join("%s %d" % kv for kv in s["dload"].items()) or "0", s["dsload"]))
            for o in s["outputs"]:
                L.append("   *%s %s: %s" % (o["kw"], " ".join("%s=%s" % kv for kv in o["params"].items()), ", ".join(o["vars"])))
            if s["amplitudes"]:
                L.append("   amplitudes: " + ", ".join(s["amplitudes"]))
            if s["other"]:
                L.append("   other keywords: " + ", ".join(s["other"]))
    L += ["", "KEYWORDS", "-" * W]
    L += _table(["Keyword", "Count", "Read by the program"], [[k["keyword"], k["count"], "yes" if k["read"] else "no"] for k in info["keywords"]], [40, 10, 22])
    L += ["", "CHECKS", "-" * W] + (["- " + c for c in info["checks"]] or ["none"])
    return "\n".join(L) + "\n"
