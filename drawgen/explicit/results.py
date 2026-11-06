"""Results of an explicit run for the 3D view of the Explicit tab: the animation frames (the animation files
<job>A001, <job>A002, ... read directly, else .vtk.series / <job>_<n>.vtk written by anim_to_vtk), the fields of the
frames and the KE/IE curves.

frames(folder, job) -> [{"time", "file"}]
geometry(folder, job) -> view data of the first frame (meshview.payload) and the fields
frame(folder, job, k, field) -> deformed positions, displacement, field values and active (not eroded) cells
"""
import base64
import glob
import json
import os
import re
import threading
from collections import OrderedDict

import numpy as np

from . import anim, meshview

SKIP = ("NODE_ID", "ELEMENT_ID", "NODE_IDS", "ELEMENT_IDS")
TENSOR_COMP = {"xx": 0, "yy": 4, "zz": 8, "xy": 1, "yz": 5, "xz": 2}
_LOCK = threading.Lock()
_GEO = OrderedDict()          # (folder, job, file, mtime) -> geometry record
_FRM = OrderedDict()          # (file, mtime) -> read_vtk result


def _b64(a, t):
    return base64.b64encode(np.ascontiguousarray(a, dtype=t).tobytes()).decode("ascii")


def anim_files(folder, job):
    """Animation files <job>A<n> of a job: [(n, path)] in number order."""
    out = []
    pat = re.compile(r"^%sA(\d{3,})$" % re.escape(job))
    for p in glob.glob(os.path.join(glob.escape(folder), glob.escape(job) + "A[0-9]*")):
        m = pat.match(os.path.basename(p))
        if m and os.path.isfile(p) and os.path.getsize(p) > 0:
            out.append((int(m.group(1)), p))
    return sorted(out)


def frames(folder, job):
    """Frames of a job: the animation files <job>A<n> (time of the file header), else the .vtk.series entries, else
    the <job>_<n>.vtk files in number order."""
    out = []
    for _n, p in anim_files(folder, job):
        t = anim.anim_time(p)
        if t is not None:
            out.append({"time": t, "file": p})
    if out:
        return out
    sp = os.path.join(folder, "%s.vtk.series" % job)
    if os.path.isfile(sp):
        try:
            with open(sp, "r") as f:
                d = json.load(f)
            for e in d.get("files") or []:
                p = os.path.join(folder, e.get("name") or "")
                if os.path.isfile(p):
                    out.append({"time": float(e.get("time", 0.0)), "file": p})
        except (OSError, ValueError):
            out = []
    if not out:
        fr = []
        for p in glob.glob(os.path.join(folder, "%s_*.vtk" % job)):
            m = re.search(r"_(\d+)\.vtk$", os.path.basename(p))
            if m and os.path.getsize(p) > 0:
                fr.append((int(m.group(1)), p))
        out = [{"time": None, "file": p} for _n, p in sorted(fr)]
    out.sort(key=lambda e: (e["time"] if e["time"] is not None else 0.0))
    return out


def jobs(folder):
    """Jobs with frames, results CSV or decks in a folder (names)."""
    names = set()
    for p in glob.glob(os.path.join(folder, "*.vtk.series")):
        names.add(os.path.basename(p)[:-len(".vtk.series")])
    for p in glob.glob(os.path.join(folder, "*_0000.rad")):
        names.add(os.path.basename(p)[:-len("_0000.rad")])
    for p in glob.glob(os.path.join(folder, "*_Results.csv")):
        names.add(os.path.basename(p)[:-len("_Results.csv")])
    for p in glob.glob(os.path.join(glob.escape(folder), "*A[0-9][0-9][0-9]*")):
        m = re.match(r"^(.+)A\d{3,}$", os.path.basename(p))
        if m:
            names.add(m.group(1))
    return sorted(names)


def _read(path):
    key = (path, os.path.getmtime(path), os.path.getsize(path))
    with _LOCK:
        if key in _FRM:
            _FRM.move_to_end(key)
            return _FRM[key]
    v = anim.read_anim(path) if not path.lower().endswith(".vtk") and anim.is_anim(path) else meshview.read_vtk(path)
    with _LOCK:
        _FRM[key] = v
        while len(_FRM) > 6:
            _FRM.popitem(last=False)
    return v


def field_list(v):
    """Fields of a frame: [{"key", "label", "loc"}]."""
    out = []
    for loc in ("point", "cell"):
        for name, a in sorted((v.get(loc) or {}).items()):
            if name.upper() in SKIP:
                continue
            a = np.asarray(a)
            nc = 1 if a.ndim == 1 else a.shape[1]
            if nc == 1:
                out.append({"key": "%s|%s|s" % (loc, name), "label": name, "loc": loc})
            elif nc == 3:
                out.append({"key": "%s|%s|mag" % (loc, name), "label": name + " |v|", "loc": loc})
                for i, c in enumerate("xyz"):
                    out.append({"key": "%s|%s|%d" % (loc, name, i), "label": "%s %s" % (name, c), "loc": loc})
            elif nc == 9:
                out.append({"key": "%s|%s|eps1" % (loc, name), "label": name + " max principal", "loc": loc})
                out.append({"key": "%s|%s|min" % (loc, name), "label": name + " min principal", "loc": loc})
                for c in TENSOR_COMP:
                    out.append({"key": "%s|%s|%s" % (loc, name, c), "label": "%s %s" % (name, c), "loc": loc})
    return out


DISP_FIELDS = [{"key": "point|@disp|mag", "label": "Displacement |v|", "loc": "point"}] + \
    [{"key": "point|@disp|%d" % i, "label": "Displacement %s" % c, "loc": "point"} for i, c in enumerate("xyz")]


def _values(v, key, order, disp=None):
    loc, name, op = key.split("|")
    a = disp if name == "@disp" else (v.get(loc) or {}).get(name)
    if a is None:
        return None, loc
    a = np.asarray(a, float)
    if op == "s":
        val = a.reshape(-1)
    elif op == "mag":
        val = np.linalg.norm(a.reshape(-1, 3), axis=1)
    elif op in ("0", "1", "2"):
        val = a.reshape(-1, 3)[:, int(op)]
    elif op in ("eps1", "min"):
        a = a.reshape(-1, 9)
        val = np.full(len(a), np.nan)
        ok = np.isfinite(a).all(axis=1)
        if ok.any():
            val[ok] = meshview.eps1(a[ok]) if op == "eps1" else meshview.eig_min(a[ok])
    elif op in TENSOR_COMP:
        val = a.reshape(-1, 9)[:, TENSOR_COMP[op]]
    else:
        return None, loc
    if loc == "cell":
        val = val[order] if len(val) > (order.max() if len(order) else -1) else np.zeros(len(order))
    return val, loc


def _disp(v):
    for n in ("Displacement", "DISP", "2DNODE_Displacement", "3DNODE_Displacement"):
        a = (v.get("point") or {}).get(n)
        if a is not None and np.asarray(a).size == v["xyz"].size:
            return np.asarray(a, float).reshape(-1, 3)
    return None


def geometry(folder, job, rigid=None):
    """View data of the first frame of a job: payload, fields, frame times. rigid: {"pids", "nodes"} of the deck."""
    fr = frames(folder, job)
    if not fr:
        raise ValueError("no frames of %s in %s" % (job, folder))
    first = fr[0]["file"]
    key = (folder, job, first, os.path.getmtime(first))
    with _LOCK:
        if key in _GEO:
            g = _GEO[key]
            return g["out"]
    v = _read(first)
    cells, order = meshview.vtk_cells(v)
    d = _disp(v)
    xyz0 = v["xyz"] - d if d is not None else v["xyz"]
    pl = meshview.payload(xyz0, cells)
    nid0 = (v.get("point") or {}).get("NODE_ID")
    if nid0 is not None and len(np.asarray(nid0).reshape(-1)) == len(xyz0):
        pl["node_ids"] = _b64(np.asarray(nid0).reshape(-1), np.uint32)        # node numbers (probe labels)
    # rigid cells (kept when eroded elements are hidden): PART_ID in the rigid parts or all nodes rigid
    rigid_mask = np.zeros(len(order), bool)
    rigid = rigid or {}
    pid = (v.get("cell") or {}).get("PART_ID")
    if rigid.get("pids") and pid is not None:
        rigid_mask |= np.isin(np.asarray(pid).reshape(-1)[order], rigid["pids"])
    nid = (v.get("point") or {}).get("NODE_ID")
    if rigid.get("nodes") and nid is not None:
        rn = np.isin(np.asarray(nid).reshape(-1), rigid["nodes"])
        k = 0
        for kind, conn, _p in cells:
            m = rn[conn].all(axis=1)
            rigid_mask[k:k + len(conn)] |= m
            k += len(conn)
    fields = field_list(v)
    if d is None:
        fields = DISP_FIELDS + fields
    # parts (PART_ID of the cells): index of each payload cell into the part list, nodes of each part
    pc = np.asarray(pid).reshape(-1)[order] if pid is not None else np.zeros(len(order), np.int64)
    ids = sorted(int(x) for x in np.unique(pc)) if len(pc) else []
    names = dict(v.get("part_names") or {})
    if not all(names.get(i) for i in ids):
        for i, t in _rad_part_names(folder, job).items():
            names.setdefault(i, t)
    pidx = np.searchsorted(np.asarray(ids, np.int64), pc).astype(np.int32) if ids else np.zeros(len(pc), np.int32)
    pl["part"] = _b64(pidx, np.int32)
    pnodes = [[] for _ in ids]
    k = 0
    for _kind, conn, _p in cells:
        conn = np.asarray(conn)
        for j in range(len(ids)):
            m = pidx[k:k + len(conn)] == j
            if m.any():
                pnodes[j].append(conn[m].reshape(-1))
        k += len(conn)
    pnodes = [np.unique(np.concatenate(a)) if a else np.zeros(0, np.int64) for a in pnodes]
    out = {"payload": pl, "fields": fields, "frames": [{"time": e["time"], "name": os.path.basename(e["file"])} for e in fr],
           "rigid_cells": int(rigid_mask.sum()), "has_disp": d is not None,
           "has_erosion": "EROSION_STATUS" in (v.get("cell") or {}),
           "parts": [{"id": i, "name": names.get(i) or "PART %d" % i, "cells": int((pidx == j).sum()), "nodes": int(len(pnodes[j]))}
                     for j, i in enumerate(ids)]}
    with _LOCK:
        _GEO[key] = {"out": out, "order": order, "rigid": rigid_mask, "cells": cells, "xyz0": xyz0, "pidx": pidx, "pnodes": pnodes}
        while len(_GEO) > 4:
            _GEO.popitem(last=False)
    return out


def _rad_part_names(folder, job):
    """{part id: title} of the /PART cards of the starter deck <job>_0000.rad of the folder."""
    out = {}
    p = os.path.join(folder, "%s_0000.rad" % job)
    if not os.path.isfile(p):
        return out
    try:
        with open(p, "r", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for i, ln in enumerate(lines[:-1]):
        m = re.match(r"/PART/(\d+)\s*$", ln.strip())
        if m:
            out[int(m.group(1))] = lines[i + 1].strip()
    return out


def frame(folder, job, k, field, rigid=None):
    """Data of frame k: {"time", "pos" (deformed), "disp", "values", "loc", "min", "max", "active"} (base64) and
    "parts": per part of geometry() {"umax", "ucomp" [dx, dy, dz of largest magnitude], "min", "max" of the field}."""
    geometry(folder, job, rigid)
    fr = frames(folder, job)
    if not fr:
        raise ValueError("no frames")
    k = max(0, min(int(k), len(fr) - 1))
    first = fr[0]["file"]
    key = (folder, job, first, os.path.getmtime(first))
    with _LOCK:
        g = _GEO[key]
    v = _read(fr[k]["file"])
    order = g["order"]
    xyz = v["xyz"]
    d = _disp(v)
    if d is not None and k > 0 and len(xyz) == len(g["xyz0"]) and np.allclose(xyz, g["xyz0"]) and np.abs(d).max() > 0:
        xyz = g["xyz0"] + d                       # POINTS undeformed: deformed = undeformed + displacement
    if d is None and len(xyz) == len(g["xyz0"]):
        d = xyz - g["xyz0"]                       # no displacement vector: deformed - first frame
    out = {"index": k, "time": fr[k]["time"] if fr[k]["time"] is not None else v.get("time"), "count": int(len(xyz)),
           "pos": _b64(xyz, np.float32)}
    if d is not None:
        out["disp"] = _b64(d, np.float32)
    val = loc = None
    if field:
        val, loc = _values(v, field, order, d)
        if val is not None:
            fin = val[np.isfinite(val)]
            out.update(values=_b64(val, np.float32), loc=loc, min=float(fin.min()) if len(fin) else 0.0,
                       max=float(fin.max()) if len(fin) else 0.0)
    # per part: max |d|, the dx, dy, dz of largest magnitude (signed), range of the field
    parts = []
    for j, nodes in enumerate(g.get("pnodes") or []):
        e = {}
        if d is not None and len(nodes) and len(d) == len(xyz):
            dn = np.asarray(d, float)[nodes]
            e["umax"] = float(np.linalg.norm(dn, axis=1).max())
            e["ucomp"] = [float(dn[np.abs(dn[:, i]).argmax(), i]) for i in range(3)]
        if val is not None:
            vv = val[g["pidx"] == j] if loc == "cell" else (val[nodes] if len(nodes) and len(val) > nodes.max() else val[:0])
            vv = vv[np.isfinite(vv)]
            if len(vv):
                e["min"], e["max"] = float(vv.min()), float(vv.max())
        parts.append(e)
    out["parts"] = parts
    er = (v.get("cell") or {}).get("EROSION_STATUS")
    if er is not None:
        act = (np.asarray(er, float).reshape(-1)[order] >= 0.5) | g["rigid"]
        out["active"] = _b64(act, np.uint8)
        out["eroded"] = int((~act).sum())
    return out



def probe(folder, job, field, probes, rigid=None):
    """Values of a field over the frames at probes [{"point": index into the view points, "cell": index into the
    view cells}] (a point field at the point, a cell field at the cell): {"time": [s], "loc", "values": [[value per
    frame] per probe]}."""
    geometry(folder, job, rigid)
    fr = frames(folder, job)
    if not fr:
        raise ValueError("no frames")
    first = fr[0]["file"]
    key = (folder, job, first, os.path.getmtime(first))
    with _LOCK:
        g = _GEO[key]
    order = g["order"]
    times, cols, loc = [], [[] for _ in probes], None
    for e in fr:
        v = _read(e["file"])
        xyz = v["xyz"]
        d = _disp(v)
        if d is None and len(xyz) == len(g["xyz0"]):
            d = xyz - g["xyz0"]
        val, loc = _values(v, field, order, d)
        times.append(e["time"] if e["time"] is not None else v.get("time"))
        for j, q in enumerate(probes):
            i = int(q.get("cell" if loc == "cell" else "point", -1))
            x = float(val[i]) if val is not None and 0 <= i < len(val) else float("nan")
            cols[j].append(x if np.isfinite(x) else None)
    return {"time": times, "loc": loc, "values": cols}
