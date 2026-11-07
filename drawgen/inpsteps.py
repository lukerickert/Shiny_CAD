# -*- coding: utf-8 -*-
"""Supports, loads, amplitudes and steps of a CalculiX / Abaqus .inp used as the geometry of the Analysis tab, as
items of the document (the import makes the model ready to solve).

items(path) -> {"supports": [{"name", "target", "dofs": [6 flags], "value": [6] | None, "steps": [step index]}],
                "loads": [{"name", "type": "force" | "gravity", "target" | None, "value": [3], "factors": {step index:
                           factor}, "amplitude": name | None}],
                "amplitudes": [{"name", "points": [[t, factor], ...]}],
                "steps": [{"name", "kind": "static" | "dynamic" | "explicit", "time", "inc0", "incmin", "incmax"
                           (fractions of the step time), "maxinc", "nlgeom", "controls": text of its *CONTROLS cards}],
                "analysis_type": "static" | "modal" | "buckling", "modes", "nlgeom", "notes": [str],
                "nset_centre": {NSET name: [x, y, z]} (the centre of the nodes of each node set)}
target: {"set": NSET name} | {"nodes": [node ids]}.

Read: *BOUNDARY (degrees of freedom 1 to 6 with a value, or ENCASTRE, PINNED, XSYMM, YSYMM, ZSYMM, XASYMM, YASYMM,
ZASYMM; OP=NEW; before the first step: in every step), *CLOAD (degrees of freedom 1 to 3, a value per node; OP=NEW;
AMPLITUDE), *DLOAD GRAV, *AMPLITUDE (tabular), *STEP (NLGEOM, INC), *STATIC, *DYNAMIC (EXPLICIT), *CONTROLS (the cards
as text), *FREQUENCY and
*BUCKLE (the number of modes). The rest is listed in "notes". The value of a *CLOAD acts on every node of its target:
the load of the document is the total (value x number of nodes), shared equally by the nodes.
"""
from . import inpmodel

DOF_TYPES = {"ENCASTRE": (1, 2, 3, 4, 5, 6), "PINNED": (1, 2, 3), "XSYMM": (1, 5, 6), "YSYMM": (2, 4, 6), "ZSYMM": (3, 4, 5),
             "XASYMM": (2, 3, 4), "YASYMM": (1, 3, 5), "ZASYMM": (1, 2, 6)}
PROCS = {"*STATIC": "static", "*DYNAMIC": "dynamic", "*FREQUENCY": "modal", "*BUCKLE": "buckling"}
IGNORED = ("*NODE FILE", "*EL FILE", "*NODE OUTPUT", "*ELEMENT OUTPUT", "*OUTPUT", "*CONTACT FILE",
           "*CONTACT OUTPUT", "*SECTION PRINT")


def _num(s, default=None):
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return default


def items(path):
    m = inpmodel.read(path)
    nsets = {k.upper(): v for k, v in m["nsets"].items()}
    nodes = m["nodes"]
    lines = inpmodel.expand_lines(path)
    notes, seen_notes = [], set()

    def note(t):
        if t not in seen_notes:
            seen_notes.add(t)
            notes.append(t)
    base_bc, base_cl = {}, {}          # model data before the first step
    steps = []                         # {"name", "proc", "params", "data", "bc", "cl", "grav", "nlgeom", "inc"}
    amps = {}
    cur = None                         # the step being read
    kw, prm, block, kwline = None, {}, [], ""
    last_name = None                   # "** Name: <name>" comment before a keyword (PrePoMax)
    bname = None                       # the name of the keyword block being read

    def state():
        return (cur["bc"], cur["cl"]) if cur is not None else (base_bc, base_cl)

    def target(t):
        t = t.strip()
        if t.lstrip("-").isdigit():
            n = int(t)
            if n not in nodes:
                note("node %d of a boundary condition or load is not in the mesh" % n)
                return None
            return ("nodes", n)
        if t.upper() in nsets:
            return ("set", t.upper())
        note("node set %s of a boundary condition or load is not in the file" % t)
        return None

    def flush():
        nonlocal block
        if kw is None:
            return
        rows = [[x.strip() for x in ln.split(",")] for ln in block]
        if kw == "*BOUNDARY":
            bc, _cl = state()
            if prm.get("AMPLITUDE"):
                note("*BOUNDARY, AMPLITUDE=%s: read without the amplitude (constant)" % prm["AMPLITUDE"])
            if str(prm.get("TYPE", "")).upper() in ("VELOCITY", "ACCELERATION"):
                note("*BOUNDARY, TYPE=%s not read" % prm["TYPE"])
                return
            for r in rows:
                if not r or not r[0]:
                    continue
                tg = target(r[0])
                if tg is None:
                    continue
                if len(r) > 1 and r[1].upper() in DOF_TYPES:
                    for d in DOF_TYPES[r[1].upper()]:
                        bc[(tg, d)] = (0.0, bname)
                    continue
                d1 = int(_num(r[1], 0)) if len(r) > 1 else 0
                d2 = int(_num(r[2], d1)) if len(r) > 2 and r[2] else d1
                v = _num(r[3], 0.0) if len(r) > 3 and r[3] else 0.0
                for d in range(d1, d2 + 1):
                    if 1 <= d <= 6:
                        bc[(tg, d)] = (v, bname)
                    elif d:
                        note("*BOUNDARY degree of freedom %d not read" % d)
        elif kw == "*CLOAD":
            _bc, cl = state()
            for r in rows:
                if len(r) < 3 or not r[0]:
                    continue
                tg = target(r[0])
                d, v = int(_num(r[1], 0)), _num(r[2], 0.0)
                if tg is None:
                    continue
                if d in (4, 5, 6):
                    note("*CLOAD moment (degree of freedom %d) not read" % d)
                    continue
                if 1 <= d <= 3:
                    key = (tg, prm.get("AMPLITUDE"))
                    vec = cl.setdefault(key, [[0.0, 0.0, 0.0], bname])
                    vec[0][d - 1] += v
        elif kw == "*DLOAD":
            for r in rows:
                if len(r) >= 6 and r[1].upper() == "GRAV" and cur is not None:
                    g = _num(r[2], 0.0)
                    vec = [g * (_num(r[k], 0.0) or 0.0) for k in (3, 4, 5)]
                    cur["grav"].append((vec, bname))
                elif len(r) >= 2:
                    note("*DLOAD %s on %s not read (set a pressure on the faces in the tab)" % (r[1], r[0]))
        elif kw == "*AMPLITUDE":
            vals = [_num(x) for r in rows for x in r if x != ""]
            vals = [x for x in vals if x is not None]
            name = str(prm.get("NAME", "")).upper()
            if name:
                amps[name] = [[vals[k], vals[k + 1]] for k in range(0, len(vals) - 1, 2)]
        elif kw == "*CONTROLS" and cur is not None:
            cur["controls"] += [kwline] + block
        elif kw in PROCS and cur is not None:
            cur["proc"] = PROCS[kw] if not (kw == "*DYNAMIC" and "EXPLICIT" in prm) else "explicit"
            cur["data"] = [_num(x) for x in (rows[0] if rows else [])]
            if kw == "*STATIC" and "RIKS" in prm:
                note("*STATIC, RIKS (arc length) read as a static step")
        block = []

    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("**"):
            t = s[2:].strip()
            if t.lower().startswith("name:"):
                last_name = t[5:].strip() or None
            continue
        if s.startswith("*"):
            flush()
            kw = s.split(",")[0].strip().upper()
            kwline = s
            prm = inpmodel._params(s)
            prm = {k: v for k, v in prm.items()}
            if kw == "*STEP":
                prev = steps[-1] if steps else None
                cur = {"name": "Step %d" % (len(steps) + 1), "proc": None, "data": [],
                       "bc": dict(prev["bc"]) if prev else dict(base_bc),
                       "cl": {k: [list(v[0]), v[1]] for k, v in (prev["cl"] if prev else base_cl).items()},
                       "grav": list(prev["grav"]) if prev else [],
                       "nlgeom": "NLGEOM" in prm and str(prm.get("NLGEOM", "YES")).upper() != "NO",
                       "inc": int(_num(prm.get("INC"), 0) or 0) or None, "controls": []}
                steps.append(cur)
            elif kw == "*BOUNDARY" and "FIXED" in prm and len(steps) > 1:
                note("*BOUNDARY, FIXED in step %d read as held at 0 (CalculiX: held at the displacement of the step before)" % len(steps))
            elif kw == "*END STEP":
                cur = None
            elif kw in ("*BOUNDARY", "*CLOAD", "*DLOAD") and str(prm.get("OP", "")).upper() == "NEW" and cur is not None:
                if kw == "*BOUNDARY":
                    cur["bc"] = {}
                elif kw == "*CLOAD":
                    cur["cl"] = {}
                else:
                    cur["grav"] = []
            elif kw in IGNORED:
                note("%s not read (the tab writes its own result output)" % kw)
            elif kw in ("*DSLOAD", "*TEMPERATURE", "*FILM", "*RADIATE", "*DFLUX", "*CFLUX"):
                note("%s not read" % kw)
            elif kw in ("*NODE PRINT", "*EL PRINT", "*CONTACT PRINT"):
                note("%s not read (History output of the tab)" % kw)
            block = []
            bname, last_name = last_name, None
            continue
        block.append(s)
    flush()
    if not steps:
        steps = [{"name": "Step 1", "proc": "static", "data": [], "bc": base_bc, "cl": base_cl, "grav": [], "nlgeom": False, "inc": None, "controls": []}]
    # analysis type: a frequency or buckling step (the steps before it are not read)
    procs = [s["proc"] or "static" for s in steps]
    out = {"supports": [], "loads": [], "amplitudes": [], "steps": [], "analysis_type": "static", "modes": None,
           "nlgeom": any(s["nlgeom"] for s in steps), "notes": notes}
    for kind in ("modal", "buckling"):
        if kind in procs:
            k = procs.index(kind)
            if len(steps) > 1:
                note("%d step(s) besides the %s step not read" % (len(steps) - 1, "frequency" if kind == "modal" else "buckling"))
            out["analysis_type"] = kind
            d = steps[k]["data"]
            out["modes"] = int(d[0]) if d and d[0] else (6 if kind == "modal" else 1)
            steps = [steps[k]]
            break
    for s in steps:
        d = s["data"] + [None] * 4
        T = d[1] if d[1] and d[1] > 0 else 1.0
        rec = {"name": s["name"], "kind": s["proc"] if s["proc"] in ("static", "dynamic", "explicit") else "static", "time": T,
               "nlgeom": s["nlgeom"], "maxinc": s["inc"], "controls": "\n".join(s["controls"])}
        if d[0]:
            rec["inc0"] = min(d[0] / T, 1.0)
        if d[2]:
            rec["incmin"] = min(d[2] / T, 1.0)
        if d[3]:
            rec["incmax"] = min(d[3] / T, 1.0)
        out["steps"].append(rec)
    # supports: one per target, held degrees of freedom and values (the steps they act in)
    sup = {}
    for k, s in enumerate(steps):
        per = {}
        for (tg, dof), (v, nm) in s["bc"].items():
            p = per.setdefault(tg, {"dofs": [0] * 6, "value": [0.0] * 6, "name": nm})
            p["dofs"][dof - 1] = 1
            p["value"][dof - 1] = v
            p["name"] = p["name"] or nm
        for tg, p in per.items():
            key = (tg, tuple(p["dofs"]), tuple(p["value"]))
            e = sup.setdefault(key, {"tg": tg, "dofs": p["dofs"], "value": p["value"], "name": p["name"], "steps": []})
            e["steps"].append(k)
    group = {}                          # node targets with the same degrees of freedom and values: one support
    for key, e in sup.items():
        tg = e["tg"]
        if tg[0] == "nodes":
            g = group.setdefault((tuple(e["dofs"]), tuple(e["value"]), tuple(e["steps"]), e["name"]), dict(e, nodes=[]))
            g["nodes"].append(tg[1])
        else:
            out["supports"].append({"name": e["name"] or "BC %s" % tg[1], "target": {"set": tg[1]}, "dofs": e["dofs"],
                                    "value": e["value"] if any(e["value"]) else None, "steps": e["steps"]})
    for g in group.values():
        out["supports"].append({"name": g["name"] or "BC nodes %s" % ",".join(map(str, g["nodes"][:3])), "target": {"nodes": sorted(g["nodes"])},
                                "dofs": g["dofs"], "value": g["value"] if any(g["value"]) else None, "steps": g["steps"]})
    # loads: the total per target and amplitude; the same direction in every step: one load with a factor per step
    def count(tg):
        return len([n for n in nsets.get(tg[1], []) if n in nodes]) if tg[0] == "set" else 1
    per_t = {}
    for k, s in enumerate(steps):
        for (tg, amp), (vec, nm) in s["cl"].items():
            tot = [c * count(tg) for c in vec]
            per_t.setdefault((tg, amp), {"name": nm, "by": {}})["by"][k] = tot
    nodegroups = {}
    for (tg, amp), e in per_t.items():
        ref = next((v for v in e["by"].values() if any(v)), None)
        if ref is None:
            continue
        i = max(range(3), key=lambda j: abs(ref[j]))
        same = all(all(abs(v[j] * ref[i] - ref[j] * v[i]) <= 1e-9 * max(1.0, abs(ref[i]) * max(map(abs, v))) for j in range(3))
                   for v in e["by"].values())
        groups = [(ref, {k: v[i] / ref[i] for k, v in e["by"].items()})] if same else \
            [(v, {k: 1.0}) for k, v in e["by"].items() if any(v)]
        for vec, fac in groups:
            rec = {"name": e["name"] or "Load %s" % tg[1], "type": "force", "value": vec, "factors": fac,
                   "amplitude": str(amp).upper() if amp else None}
            if tg[0] == "set":
                rec["target"] = {"set": tg[1]}
                out["loads"].append(rec)
            else:
                key = (tuple(vec), tuple(sorted(fac.items())), rec["amplitude"], e["name"])
                g = nodegroups.setdefault(key, dict(rec, nodes=[]))
                g["nodes"].append(tg[1])
    for g in nodegroups.values():
        n = len(g["nodes"])
        rec = {k: v for k, v in g.items() if k != "nodes"}
        if rec["name"].startswith("Load ") and n > 1:
            rec["name"] = "Load nodes %s" % ", ".join(map(str, sorted(g["nodes"])[:3])) + (" ..." if n > 3 else "")
        rec["target"] = {"nodes": sorted(g["nodes"])}
        rec["value"] = [c * n for c in g["value"]]
        out["loads"].append(rec)
    grav = {}
    for k, s in enumerate(steps):
        tot = [sum(v[0][j] for v in s["grav"]) for j in range(3)]
        if any(tot):
            grav.setdefault(tuple(tot), []).append(k)
    for vec, ks in grav.items():
        out["loads"].append({"name": "Gravity", "type": "gravity", "target": None, "value": list(vec), "factors": {k: 1.0 for k in ks}, "amplitude": None})
    # centres of the node sets (the view draws the support and load glyphs there)
    out["nset_centre"] = {}
    for nm in nsets:
        P = [nodes[n] for n in nsets.get(nm, []) if n in nodes]
        if P:
            out["nset_centre"][nm] = [sum(p[k] for p in P) / len(P) for k in range(3)]
    used = set(l["amplitude"] for l in out["loads"] if l.get("amplitude"))
    for a in sorted(used):
        if a in amps:
            out["amplitudes"].append({"name": a, "points": amps[a]})
        else:
            note("*AMPLITUDE %s not in the file: the load is constant" % a)
            for l in out["loads"]:
                if l.get("amplitude") == a:
                    l["amplitude"] = None
    return out
