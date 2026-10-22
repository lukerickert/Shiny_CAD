"""Results of an explicit run for the 3D view of the Explicit tab: the animation frames (.vtk.series / <job>_<n>.vtk
written by anim_to_vtk), the fields of the frames and the KE/IE curves.

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

from . import meshview

SKIP = ("NODE_ID", "ELEMENT_ID", "NODE_IDS", "ELEMENT_IDS")
_LOCK = threading.Lock()
_GEO = OrderedDict()          # (folder, job, file, mtime) -> geometry record
_FRM = OrderedDict()          # (file, mtime) -> read_vtk result


def _b64(a, t):
    return base64.b64encode(np.ascontiguousarray(a, dtype=t).tobytes()).decode("ascii")


def frames(folder, job):
    """Frames of a job: the .vtk.series entries, else the <job>_<n>.vtk files in number order."""
    sp = os.path.join(folder, "%s.vtk.series" % job)
    out = []
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
    return sorted(names)


def _read(path):
    key = (path, os.path.getmtime(path), os.path.getsize(path))
    with _LOCK:
        if key in _FRM:
            _FRM.move_to_end(key)
            return _FRM[key]
    v = meshview.read_vtk(path)
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
    return out


def _values(v, key, order):
    loc, name, op = key.split("|")
    a = (v.get(loc) or {}).get(name)
    if a is None:
        return None, loc
    a = np.asarray(a, float)
    if op == "s":
        val = a.reshape(-1)
    elif op == "mag":
        val = np.linalg.norm(a.reshape(-1, 3), axis=1)
    elif op in ("0", "1", "2"):
        val = a.reshape(-1, 3)[:, int(op)]
    elif op == "eps1":
        val = meshview.eps1(a)
    elif op == "min":
        M = a.reshape(-1, 3, 3)
        val = np.linalg.eigvalsh(0.5 * (M + np.transpose(M, (0, 2, 1))))[:, 0]
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
    out = {"payload": pl, "fields": field_list(v), "frames": [{"time": e["time"], "name": os.path.basename(e["file"])} for e in fr],
           "rigid_cells": int(rigid_mask.sum()), "has_disp": d is not None,
           "has_erosion": "EROSION_STATUS" in (v.get("cell") or {})}
    with _LOCK:
        _GEO[key] = {"out": out, "order": order, "rigid": rigid_mask, "cells": cells, "xyz0": xyz0}
        while len(_GEO) > 4:
            _GEO.popitem(last=False)
    return out


def frame(folder, job, k, field, rigid=None):
    """Data of frame k: {"time", "pos" (deformed), "disp", "values", "loc", "min", "max", "active"} (base64)."""
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
    out = {"index": k, "time": fr[k]["time"] if fr[k]["time"] is not None else v.get("time"), "count": int(len(xyz)),
           "pos": _b64(xyz, np.float32)}
    if d is not None:
        out["disp"] = _b64(d, np.float32)
    if field:
        val, loc = _values(v, field, order)
        if val is not None:
            fin = val[np.isfinite(val)]
            out.update(values=_b64(val, np.float32), loc=loc, min=float(fin.min()) if len(fin) else 0.0,
                       max=float(fin.max()) if len(fin) else 0.0)
    er = (v.get("cell") or {}).get("EROSION_STATUS")
    if er is not None:
        act = (np.asarray(er, float).reshape(-1)[order] >= 0.5) | g["rigid"]
        out["active"] = _b64(act, np.uint8)
        out["eroded"] = int((~act).sum())
    return out
