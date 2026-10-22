"""View data of meshes for the Explicit tab: exterior faces of solid elements and the shell elements as triangles,
from an Abaqus .inp, from the mesh of the ShinyCAD model, or from a legacy VTK file written by anim_to_vtk.

payload(xyz, cells) -> {"count", "pos", "tri", "tri_cell", "tri_kind", "lines", "part", "ncell", "ntri", "bbox"}; base64:
pos (float32), tri (uint32, node indices into pos), tri_cell (uint32, cell of each triangle), tri_kind (uint8: 0 triangle,
1 and 2 the two halves of a quadrangle), lines (uint32 pairs, line elements), part (int32, part index of each cell).
Cells: [(kind, conn array (n, k) of indices into xyz, part ids or None)], kind "tet", "hex", "wedge", "pyr", "tri",
"quad", "line".

read_vtk(path) -> {"xyz", "cells", "point": {name: array}, "cell": {name: array}, "time", "cycle"} (ASCII or BINARY
legacy VTK, UNSTRUCTURED_GRID or POLYDATA).
read_inp(path) -> {"xyz", "cells", "node_ids", "elem_ids", "parts": [(elset, type)]} (*NODE, *ELEMENT).
"""
import base64
import re

import numpy as np

# faces of the solid kinds (corner indices)
FACES = {
    "tet": [(0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2)],
    "hex": [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    "wedge": [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)],
    "pyr": [(0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)],
}
NCORNER = {"tet": 4, "hex": 8, "wedge": 6, "pyr": 5, "tri": 3, "quad": 4, "line": 2}

# VTK cell type -> (kind, corner count)
VTK_KIND = {3: ("line", 2), 5: ("tri", 3), 9: ("quad", 4), 10: ("tet", 4), 12: ("hex", 8), 13: ("wedge", 6),
            14: ("pyr", 5), 21: ("line", 2), 22: ("tri", 3), 23: ("quad", 4), 24: ("tet", 4), 25: ("hex", 8),
            26: ("wedge", 6), 28: ("quad", 4)}

# Abaqus element type (prefix match, longest first) -> kind
INP_KIND = [("C3D10", "tet"), ("C3D4", "tet"), ("C3D20", "hex"), ("C3D8", "hex"), ("C3D15", "wedge"), ("C3D6", "wedge"),
            ("C3D5", "pyr"), ("SC8", "hex"), ("SC6", "wedge"), ("COH3D8", "hex"), ("COH3D6", "wedge"),
            ("S8", "quad"), ("S9", "quad"), ("S4", "quad"), ("S6", "tri"), ("S3", "tri"), ("M3D4", "quad"), ("M3D3", "tri"),
            ("R3D4", "quad"), ("R3D3", "tri"), ("CPS4", "quad"), ("CPS3", "tri"), ("B3", "line"), ("T3D", "line")]


def inp_kind(etype):
    u = etype.upper()
    for p, k in INP_KIND:
        if u.startswith(p):
            return k
    return None


def _b64(a, t):
    return base64.b64encode(np.ascontiguousarray(a, dtype=t).tobytes()).decode("ascii")


def boundary(cells):
    """Exterior faces of the solid cells and all shell cells: (faces [(cell index, corner index tuple)], lines)."""
    keys, owners, polys = [], [], []
    base = 0
    lines = []
    shell = []
    for kind, conn, _p in cells:
        conn = np.asarray(conn, np.int64)
        n = len(conn)
        if kind in FACES:
            for f in FACES[kind]:
                fa = conn[:, f]
                keys.append(np.sort(fa, axis=1) if len(f) == 4 else np.hstack([np.sort(fa, axis=1), np.full((n, 1), -1)]))
                owners.append(np.arange(base, base + n))
                polys.append(fa if len(f) == 4 else np.hstack([fa, np.full((n, 1), -1)]))
        elif kind in ("tri", "quad"):
            fa = conn[:, :NCORNER[kind]]
            if kind == "tri":
                fa = np.hstack([fa, np.full((n, 1), -1)])
            shell.append((np.arange(base, base + n), fa))
        elif kind == "line":
            lines.append((np.arange(base, base + n), conn[:, :2]))
        base += n
    faces = []
    if keys:
        K = np.vstack(keys)
        O = np.concatenate(owners)
        P = np.vstack(polys)
        _, inv, cnt = np.unique(K, axis=0, return_inverse=True, return_counts=True)
        inv = np.asarray(inv).reshape(-1)
        ext = cnt[inv] == 1
        faces.append((O[ext], P[ext]))
    faces += shell
    return faces, lines


def payload(xyz, cells):
    """View data (see the module text)."""
    xyz = np.asarray(xyz, float).reshape(-1, 3)
    faces, lines = boundary(cells)
    tri, tcell, tkind = [], [], []
    for owner, P in faces:
        if not len(P):
            continue
        q = P[:, 3] >= 0
        t = P[~q]
        qq = P[q]
        tri += [t[:, :3], qq[:, [0, 1, 2]], qq[:, [0, 2, 3]]]
        tcell += [owner[~q], owner[q], owner[q]]
        tkind += [np.zeros(len(t), np.uint8), np.ones(len(qq), np.uint8), np.full(len(qq), 2, np.uint8)]
    T = np.vstack(tri) if tri else np.zeros((0, 3), np.int64)
    C = np.concatenate(tcell) if tcell else np.zeros(0, np.int64)
    K = np.concatenate(tkind) if tkind else np.zeros(0, np.uint8)
    L = np.vstack([c for _o, c in lines]) if lines else np.zeros((0, 2), np.int64)
    used = xyz if len(xyz) else np.zeros((1, 3))
    lo, hi = used.min(0), used.max(0)
    ncell = sum(len(c[1]) for c in cells)
    parts = []
    for kind, conn, p in cells:
        parts.append(np.asarray(p, np.int64) if p is not None else np.zeros(len(conn), np.int64))
    pid = np.concatenate(parts) if parts else np.zeros(0, np.int64)
    return {"count": int(len(xyz)), "pos": _b64(xyz, np.float32), "tri": _b64(T, np.uint32), "tri_cell": _b64(C, np.uint32),
            "tri_kind": _b64(K, np.uint8), "lines": _b64(L, np.uint32), "ncell": int(ncell), "ntri": int(len(T)),
            "part": _b64(pid, np.int32), "bbox": [float(v) for v in list(lo) + list(hi)]}


# --------------------------------------------------------------------------- legacy VTK

_TYPES = {"float": np.float32, "double": np.float64, "int": np.int32, "unsigned_int": np.uint32, "long": np.int64,
          "unsigned_long": np.uint64, "short": np.int16, "unsigned_short": np.uint16, "char": np.int8,
          "unsigned_char": np.uint8, "vtkidtype": np.int64, "bit": np.uint8}


class _Reader(object):
    def __init__(self, data, binary):
        self.d = data
        self.p = 0
        self.binary = binary

    def line(self):
        n = len(self.d)
        while self.p < n:
            e = self.d.find(b"\n", self.p)
            if e < 0:
                e = n
            s = self.d[self.p:e].strip()
            self.p = e + 1
            if s:
                return s.decode("latin-1")
        return None

    def numbers(self, count, dtype):
        dt = np.dtype(_TYPES.get(dtype.lower(), np.float32))
        if self.binary:
            be = dt.newbyteorder(">")
            nb = count * be.itemsize
            a = np.frombuffer(self.d, dtype=be, count=count, offset=self.p).astype(dt.newbyteorder("="))
            self.p += nb
            if self.p < len(self.d) and self.d[self.p:self.p + 1] == b"\n":
                self.p += 1
            return a
        out = []
        got = 0
        while got < count:
            e = self.d.find(b"\n", self.p)
            if e < 0:
                e = len(self.d)
            chunk = self.d[self.p:e]
            self.p = e + 1
            if not chunk.strip():
                if e >= len(self.d):
                    break
                continue
            v = np.array(chunk.split(), dtype=np.float64)
            out.append(v)
            got += len(v)
        a = np.concatenate(out) if out else np.zeros(0)
        return a[:count].astype(dt) if dt.kind in "iu" else a[:count]


def read_vtk(path):
    with open(path, "rb") as f:
        data = f.read()
    head = data[:2000].split(b"\n")
    binary = len(head) > 2 and head[2].strip().upper().startswith(b"BINARY")
    r = _Reader(data, binary)
    r.line(); r.line(); r.line()             # version, title, ASCII / BINARY
    out = {"xyz": np.zeros((0, 3)), "cells": [], "point": {}, "cell": {}, "time": None, "cycle": None}
    conn = types = None
    polys = []
    section = None
    npts = ncells = 0
    while True:
        s = r.line()
        if s is None:
            break
        tok = s.split()
        kw = tok[0].upper()
        if kw == "DATASET":
            continue
        if kw == "POINTS":
            npts = int(tok[1])
            out["xyz"] = r.numbers(3 * npts, tok[2]).astype(float).reshape(-1, 3)
        elif kw == "CELLS":
            if len(tok) >= 3 and r.binary is False and _peek_offsets(r):
                conn = _read_new_cells(r, int(tok[1]), int(tok[2]))
            else:
                n, size = int(tok[1]), int(tok[2])
                a = r.numbers(size, "int").astype(np.int64)
                conn = _split_legacy(a, n)
        elif kw in ("POLYGONS", "TRIANGLE_STRIPS", "LINES", "VERTICES"):
            n, size = int(tok[1]), int(tok[2])
            a = r.numbers(size, "int").astype(np.int64)
            polys.append((kw, _split_legacy(a, n)))
        elif kw == "CELL_TYPES":
            types = r.numbers(int(tok[1]), "int").astype(np.int64)
        elif kw == "POINT_DATA":
            section = "point"
        elif kw == "CELL_DATA":
            section, ncells = "cell", int(tok[1])
        elif kw == "FIELD":
            nf = int(tok[2])
            for _ in range(nf):
                h = r.line()
                if h is None:
                    break
                ht = h.split()
                if len(ht) < 4:
                    continue
                name, ncomp, ntup, dtype = ht[0], int(ht[1]), int(ht[2]), ht[3]
                a = r.numbers(ncomp * ntup, dtype)
                if ht[0].upper() == "TIME" and section is None:
                    out["time"] = float(a[0]) if len(a) else None
                elif ht[0].upper() == "CYCLE" and section is None:
                    out["cycle"] = int(a[0]) if len(a) else None
                elif section:
                    out[section][name] = a.reshape(ntup, ncomp) if ncomp > 1 else a
                else:
                    out.setdefault("field", {})[name] = a
        elif kw in ("SCALARS", "VECTORS", "NORMALS", "TENSORS", "COLOR_SCALARS", "TEXTURE_COORDINATES") and section:
            name = tok[1]
            dtype = tok[2] if len(tok) > 2 else "float"
            nt = npts if section == "point" else ncells
            if kw == "SCALARS":
                ncomp = int(tok[3]) if len(tok) > 3 else 1
                save = r.p
                lt = r.line()
                if not (lt and lt.upper().startswith("LOOKUP_TABLE")):
                    r.p = save
                a = r.numbers(ncomp * nt, dtype)
                out[section][name] = a.reshape(nt, ncomp) if ncomp > 1 else a
            elif kw in ("VECTORS", "NORMALS"):
                out[section][name] = r.numbers(3 * nt, dtype).reshape(nt, 3)
            elif kw == "TENSORS":
                out[section][name] = r.numbers(9 * nt, dtype).reshape(nt, 9)
            elif kw == "COLOR_SCALARS":
                ncomp = int(tok[2])
                out[section][name] = r.numbers(ncomp * nt, "float").reshape(nt, ncomp)
            else:
                dim = int(tok[2])
                out[section][name] = r.numbers(dim * nt, tok[3] if len(tok) > 3 else "float").reshape(nt, dim)
        elif kw == "LOOKUP_TABLE":
            n = int(tok[2])
            r.numbers(4 * n, "float")
        elif kw == "METADATA":
            continue                                  # INFORMATION / NAME / DATA lines are skipped as unknown lines
    cells = []
    if conn is not None and types is not None:
        groups = {}
        for i, (t, c) in enumerate(zip(types, conn)):
            k = VTK_KIND.get(int(t))
            if k is None:
                continue
            groups.setdefault(k, []).append(i)
        for (kind, nc), idx in sorted(groups.items()):
            arr = np.array([conn[i][:nc] for i in idx], np.int64)
            cells.append((kind, arr, None, np.array(idx, np.int64)))
    for kw, cl in polys:
        for nc, kind in ((3, "tri"), (4, "quad"), (2, "line")):
            idx = [i for i, c in enumerate(cl) if len(c) == nc and (kw != "LINES" or nc == 2)]
            if idx:
                cells.append((kind, np.array([cl[i] for i in idx], np.int64), None, np.array(idx, np.int64)))
    out["cells"] = cells
    return out


def _peek_offsets(r):
    save = r.p
    s = r.line()
    r.p = save
    return bool(s and s.upper().startswith("OFFSETS"))


def _read_new_cells(r, noff, nconn):
    h = r.line().split()
    off = r.numbers(noff, h[1] if len(h) > 1 else "vtktypeint64").astype(np.int64)
    h = r.line().split()
    con = r.numbers(nconn, h[1] if len(h) > 1 else "vtktypeint64").astype(np.int64)
    return [con[off[i]:off[i + 1]] for i in range(len(off) - 1)]


def _split_legacy(a, n):
    out, p = [], 0
    for _ in range(n):
        k = int(a[p])
        out.append(a[p + 1:p + 1 + k])
        p += k + 1
    return out


def vtk_cells(v):
    """Cells of read_vtk for payload(): [(kind, conn, None)] and the VTK cell index of each payload cell."""
    cells, order = [], []
    for kind, conn, _p, idx in v["cells"]:
        cells.append((kind, conn, None))
        order.append(idx)
    return cells, (np.concatenate(order) if order else np.zeros(0, np.int64))


# --------------------------------------------------------------------------- Abaqus .inp

def _keyword_params(line):
    out = {}
    for p in line.split(",")[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip().upper()] = v.strip()
        elif p.strip():
            out[p.strip().upper()] = True
    return out


def read_inp(path):
    """Nodes and elements of an Abaqus .inp (without *INCLUDE files and *PART instancing)."""
    nodes_id, nodes_xyz = [], []
    groups = {}                                       # (kind, elset) -> (ids, conn rows)
    mode = None
    cur = None
    pending = []
    with open(path, "r", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if not s or s.startswith("**"):
                continue
            if s.startswith("*"):
                kw = s.split(",")[0].strip().upper()
                prm = _keyword_params(s)
                pending = []
                if kw == "*NODE" and not any(x in s.upper() for x in ("OUTPUT", "PRINT", "FILE")):
                    mode = "node"
                elif kw == "*ELEMENT" and "OUTPUT" not in s.upper():
                    t = str(prm.get("TYPE", ""))
                    kind = inp_kind(t)
                    mode = "elem" if kind else None
                    cur = (kind, NCORNER.get(kind, 0), str(prm.get("ELSET", t)), t)
                    groups.setdefault(cur[:3] + (cur[3],), ([], []))
                else:
                    mode = None
                continue
            if mode == "node":
                p = s.split(",")
                try:
                    nodes_id.append(int(p[0])); nodes_xyz.append((float(p[1]), float(p[2]), float(p[3]) if len(p) > 3 and p[3].strip() else 0.0))
                except (ValueError, IndexError):
                    pass
            elif mode == "elem":
                vals = [v for v in s.split(",") if v.strip()]
                pending += vals
                if s.endswith(","):
                    continue
                try:
                    ids = [int(v) for v in pending]
                except ValueError:
                    pending = []
                    continue
                pending = []
                g = groups[cur[:3] + (cur[3],)]
                g[0].append(ids[0])
                g[1].append(ids[1:1 + cur[1]])
    nid = np.asarray(nodes_id, np.int64)
    xyz = np.asarray(nodes_xyz, float).reshape(-1, 3)
    lookup = {int(n): i for i, n in enumerate(nid)}
    cells, elem_ids, parts = [], [], []
    for k, (kind, nc, elset, etype) in enumerate(groups):
        ids, rows = groups[(kind, nc, elset, etype)]
        if not ids:
            continue
        ok = [i for i, r in enumerate(rows) if len(r) == nc and all(n in lookup for n in r)]
        conn = np.array([[lookup[n] for n in rows[i]] for i in ok], np.int64).reshape(-1, nc)
        cells.append((kind, conn, np.full(len(ok), len(parts), np.int64)))
        elem_ids.append(np.asarray([ids[i] for i in ok], np.int64))
        parts.append((elset, etype))
    return {"xyz": xyz, "cells": cells, "node_ids": nid, "elem_ids": elem_ids, "parts": parts}


def eps1(T9):
    """Largest eigenvalue of the symmetric part of 3x3 tensors (rows of 9 components)."""
    M = np.asarray(T9, float).reshape(-1, 3, 3)
    M = 0.5 * (M + np.transpose(M, (0, 2, 1)))
    return np.linalg.eigvalsh(M)[:, 2]


def safe_field_name(name):
    return re.sub(r"[^A-Za-z0-9_()\-./ ]", "_", name)
