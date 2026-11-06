# -*- coding: utf-8 -*-
"""Time history requests of an OpenCourant job (analysis "history", model_inp._history): the curves of the /TH/NODE,
/TH/PART, /TH/INTER and /TH/SECTIO groups of the starter deck with the titles SC_H<k>/<request id>/<kind>/<name>, read from the results CSV
of th_to_csv (<job>_Results.csv or <job>T01.csv).

Columns: a node column is the one whose header holds the variable (DX, VX, AX, REACX, ...) and the node name
H<k>N<node>; a part, interface or section column the one whose header holds the variable and the title or the number of
the object. Columns without these names ("var <n>"): the columns after the 23 global variables in the order of the
groups (/TH/NODE, /TH/PART, /TH/INTER, /TH/SECTIO; groups in the order of the deck, per object its variables).

series(folder, job) -> {"time_history": [{"id", "name", "kind", "series": [{"name", "unit", "t", "v"}]}], "note"}.
"""
import os
import re

import numpy as np

N_GLOBAL = 23                   # global variables of th_to_csv after the time column


def groups(rad_text):
    """The SC_H groups of a deck: [{"k", "id", "kind", "name", "type": "NODE" | "PART", "vars", "objs"}] (objs: node
    numbers or part numbers), with the part titles {number: title} for the /TH/PART groups."""
    L = rad_text.splitlines()
    titles = {"PART": {}, "INTER": {}, "SECTIO": {}}
    for i, ln in enumerate(L):
        m = re.match(r"/(PART|INTER/[A-Z0-9]+|SECT)/(\d+)\s*$", ln.strip())
        if m and i + 1 < len(L):
            typ = "PART" if m.group(1) == "PART" else "SECTIO" if m.group(1) == "SECT" else "INTER"
            titles[typ][int(m.group(2))] = L[i + 1].strip().upper()
    out = []
    i = 0
    while i < len(L):
        m = re.match(r"/TH/(NODE|PART|INTER|SECTIO)/(\d+)\s*$", L[i].strip())
        if not m or i + 1 >= len(L) or not L[i + 1].startswith("SC_H"):
            i += 1
            continue
        typ, title = m.group(1), L[i + 1].strip()
        parts = title.split("/", 3)
        try:
            k = int(parts[0][4:])
        except ValueError:
            i += 1
            continue
        g = {"k": k, "id": parts[1] if len(parts) > 1 else str(k), "kind": parts[2] if len(parts) > 2 else "node",
             "name": parts[3] if len(parts) > 3 else title, "type": typ, "vars": [], "objs": []}
        j = i + 2
        while j < len(L) and not L[j].startswith("/"):
            s = L[j]
            j += 1
            if s.startswith("#") or not s.strip():
                continue
            f = s.split()
            if not f[0].lstrip("-").isdigit():
                g["vars"] += [x.upper() for x in f]
            elif typ == "NODE":
                g["objs"].append(int(f[0]))
            else:
                g["objs"] += [int(x) for x in f if x.lstrip("-").isdigit()]
        g["titles"] = {p: titles[typ].get(p, "") for p in g["objs"]} if typ != "NODE" else {}
        out.append(g)
        i = j
    return out


def read_csv(path):
    """(header, rows) of a th_to_csv CSV: header strings, rows of floats."""
    with open(path, "r", errors="replace") as f:
        raw = [ln.rstrip("\n") for ln in f if ln.strip()]

    def toks(line):
        s = line.strip().lstrip("#").strip()
        if "," in s:
            return [p.strip().strip('"').strip() for p in s.split(",")]
        return [p.strip('"') for p in s.split()]

    def num(p):
        try:
            return [float(x) for x in p if x != ""]
        except ValueError:
            return None
    head, rows = [], []
    for ln in raw:
        p = toks(ln)
        v = num(p)
        if v and len(v) >= 2:
            rows.append(v)
        elif not rows:
            head = [x for x in p if x != ""]
    return head, rows


def _word(h, w):
    return re.search(r"(^|[^A-Z0-9_])%s($|[^A-Z0-9_])" % re.escape(w), h) is not None


def columns(head, gs):
    """{(k, var, obj): column} of the groups gs; note (str) when the columns are taken by position."""
    H = [h.upper() for h in head]
    col, missing = {}, 0
    for g in gs:
        for o in g["objs"]:
            for v in g["vars"]:
                hit = None
                if g["type"] == "NODE":
                    tag = "H%dN%d" % (g["k"], o)
                    hit = next((i for i, h in enumerate(H) if tag in h and _word(h, v)), None)
                else:
                    t = g["titles"].get(o) or ""
                    hit = next((i for i, h in enumerate(H) if _word(h, v) and "|%s|" % v not in h and ((t and t in h) or _word(h, str(o)))), None)
                if hit is None:
                    missing += 1
                else:
                    col[(g["k"], v, o)] = hit
    if not missing:
        return col, ""
    # by position: after the time column and the global variables
    order = [g for typ in ("NODE", "PART", "INTER", "SECTIO") for g in gs if g["type"] == typ]
    pos, c = {}, 1 + N_GLOBAL
    for g in order:
        for o in g["objs"]:
            for v in g["vars"]:
                pos[(g["k"], v, o)] = c
                c += 1
    if len(head) and c > len(head) + 1:
        return col, ("time history: %d of the requested columns not found by name in the CSV header and the CSV has "
                     "fewer columns than the requests" % missing)
    return pos, "time history: columns taken by position (no node or part names in the CSV header)"


NODE_Q = (("D", "u", "mm"), ("V", "v", "mm/s"), ("A", "a", "mm/s^2"))


def build_series(gs, head, rows):
    col, note = columns(head, gs)
    if not rows:
        return [], note or "time history: no rows in the CSV"
    A = np.array([r for r in rows if len(r) >= len(rows[0])], float) if rows else np.zeros((0, 1))
    t = A[:, 0].tolist()
    out = {}
    for g in gs:
        req = out.setdefault(g["k"], {"id": g["id"], "name": g["name"], "kind": g["kind"], "series": []})
        ser = req["series"]

        def vals(v):
            cs = [col.get((g["k"], v, o)) for o in g["objs"]]
            cs = [c for c in cs if c is not None and c < A.shape[1]]
            return A[:, cs] if cs else None
        if g["type"] == "NODE":
            for pre, lab, unit in NODE_Q:
                comp = [vals(pre + c) if pre + c in g["vars"] else None for c in "XYZ"]
                if all(x is None for x in comp):
                    continue
                for c, x in zip("xyz", comp):
                    if x is not None:
                        ser.append({"name": "%s%s mean" % (lab, c), "unit": unit, "t": t, "v": x.mean(axis=1).tolist()})
                if all(x is not None for x in comp):
                    mag = np.sqrt(comp[0] ** 2 + comp[1] ** 2 + comp[2] ** 2)
                    ser.append({"name": "|%s| max" % lab, "unit": unit, "t": t, "v": mag.max(axis=1).tolist()})
            for c in "XYZ":
                x = vals("REAC" + c) if "REAC" + c in g["vars"] else None
                if x is not None:
                    ser.append({"name": "RF%s total" % c.lower(), "unit": "N", "t": t, "v": x.sum(axis=1).tolist()})
        elif g["type"] in ("INTER", "SECTIO"):
            fn = [vals("FN" + c) for c in "XYZ"]
            ft = [vals("FT" + c) for c in "XYZ"]
            for c, a, b in zip("xyz", fn, ft):
                if a is not None and b is not None:
                    ser.append({"name": "F%s total" % c, "unit": "N", "t": t, "v": (a + b).sum(axis=1).tolist()})
            if all(a is not None for a in fn):
                ser.append({"name": "normal force", "unit": "N", "t": t, "v": np.sqrt(sum(a.sum(axis=1) ** 2 for a in fn)).tolist()})
            if all(b is not None for b in ft):
                ser.append({"name": "tangential force", "unit": "N", "t": t, "v": np.sqrt(sum(b.sum(axis=1) ** 2 for b in ft)).tolist()})
            for c in "XYZ":
                x = vals("M" + c) if "M" + c in g["vars"] else None
                if x is not None:
                    ser.append({"name": "M%s" % c.lower(), "unit": "N mm", "t": t, "v": x.sum(axis=1).tolist()})
        else:
            for v, lab in (("IE", "internal energy"), ("KE", "kinetic energy")):
                x = vals(v) if v in g["vars"] else None
                if x is not None:
                    ser.append({"name": lab, "unit": "mJ", "t": t, "v": x.sum(axis=1).tolist()})
    return [out[k] for k in sorted(out)], note


def series(folder, job, csv_path=None):
    """Curves of the history requests of a job of a run folder (None without SC_H groups in the deck)."""
    rad = os.path.join(folder, "%s_0000.rad" % job)
    if not os.path.isfile(rad):
        return None
    with open(rad, "r", errors="replace") as f:
        gs = groups(f.read())
    if not gs:
        return None
    if csv_path is None:
        import glob
        c = [os.path.join(folder, "%s_Results.csv" % job)] + sorted(glob.glob(os.path.join(folder, "%sT[0-9][0-9]*.csv" % job)))
        csv_path = next((p for p in c if os.path.isfile(p)), None)
    if not csv_path:
        return {"time_history": [{"id": g["id"], "name": g["name"], "kind": g["kind"], "series": []} for g in gs],
                "note": "time history: no results CSV"}
    head, rows = read_csv(csv_path)
    th, note = build_series(gs, head, rows)
    return {"time_history": th, "note": note}
