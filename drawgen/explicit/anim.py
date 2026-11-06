"""OpenCourant animation files (<job>A001, <job>A002, ...) read directly, without the anim_to_vtk conversion.

Format FASTMAGI10 (big-endian), as read by anim_to_vtk (OpenCourant tools, output_converters/anim_to_vtk, MIT):
header (magic, time, 3 x 81 character texts, 10 flags), 2D block (nodes, 4-node elements, parts, nodal normals,
nodal and element scalars, nodal vectors, element tensors xx yy xy, masses, numbering, hierarchy), 3D block (flag 2:
8-node elements, scalars, tensors xx yy zz xy xz yz), 1D block (flag 3: 2-node elements, scalars, 9-component
torsors). The blocks after the 1D block (hierarchy, time history lists, SPH) are not read.

read_anim(path) returns the structure of meshview.read_vtk with the names anim_to_vtk writes:
{"xyz", "cells": [(kind, conn, None, idx)], "point": {"NODE_ID", <nodal scalars>, <vectors>},
 "cell": {"ELEMENT_ID", "PART_ID", "EROSION_STATUS", "1DELEM_*", "2DELEM_*", "3DELEM_*"}, "time", "cycle",
 "part_names": {part id: text of the part after its id}}.
Cell index order: 1D, 2D, 3D elements. Element values of the other element dimensions are NaN.
"""
import re
import struct

import numpy as np

MAGIC = 0x542c          # FASTMAGI10
SHORT2FLOAT = 3000.0
TEXT = 81
PTEXT = 50


class AnimError(ValueError):
    pass


class _Buf:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def arr(self, dtype, n):
        dt = np.dtype(dtype)
        size = dt.itemsize * int(n)
        if n < 0 or self.p + size > len(self.d):
            raise AnimError("animation file ends early (offset %d, %d bytes wanted)" % (self.p, size))
        a = np.frombuffer(self.d, dt, int(n), self.p)
        self.p += size
        return a

    def i4(self):
        return int(self.arr(">i4", 1)[0])

    def text(self, n):
        raw = bytes(self.arr("u1", n))
        return raw.split(b"\0", 1)[0].decode("latin-1").strip()


def is_anim(path):
    """True when the file starts with the FASTMAGI10 magic number."""
    try:
        with open(path, "rb") as f:
            h = f.read(4)
        return len(h) == 4 and struct.unpack(">i", h)[0] == MAGIC
    except OSError:
        return False


def anim_time(path):
    """Time of an animation file (header), None when the file is not an animation file."""
    try:
        with open(path, "rb") as f:
            h = f.read(8)
        if len(h) < 8 or struct.unpack(">i", h[:4])[0] != MAGIC:
            return None
        return _f7(struct.unpack(">f", h[4:8])[0])
    except OSError:
        return None


def _f7(x):
    """float32 value as the nearest decimal of 7 significant digits."""
    return float("%.7g" % float(x))


def _name(s):
    return s.replace(" ", "_")


def _pid(text):
    m = re.match(r"\s*([+-]?\d+)", text)
    return int(m.group(1)) if m else 0


def _part_ids(defpart, ptext, n):
    """Part ID of each element from the cumulative end indices of the parts."""
    out = np.zeros(n, np.int32)
    start = 0
    for end, t in zip(defpart, ptext):
        end = int(min(max(end, start), n))
        out[start:end] = _pid(t)
        start = end
    return out


def _first(con):
    """Mask of the first occurrence of each node in the rows of con and the number of different nodes per row."""
    first = np.ones(con.shape, bool)
    for j in range(1, con.shape[1]):
        first[:, j] = ~(con[:, :j] == con[:, j:j + 1]).any(axis=1)
    return first, first.sum(axis=1)


def _collapse(con, rows, k):
    """Rows of con with k different nodes, as the k nodes in order of first occurrence."""
    c = con[rows]
    f, _n = _first(c)
    return c[f].reshape(-1, k)


def read_anim(path):
    with open(path, "rb") as f:
        data = f.read()
    b = _Buf(data)
    magic = b.i4()
    if magic != MAGIC:
        raise AnimError("%s: not an OpenCourant animation file (magic 0x%x)" % (path, magic & 0xffffffff))
    t = _f7(b.arr(">f4", 1)[0])
    b.text(TEXT); b.text(TEXT); b.text(TEXT)
    flag = [int(x) for x in b.arr(">i4", 10)]

    # ---------------------------------------------------------------- 2D
    nn, n2, np2, nfun, nefun, nvect, ntens, nskew = (int(x) for x in b.arr(">i4", 8))
    if nskew:
        b.arr(">u2", 6 * nskew)
    xyz = b.arr(">f4", 3 * nn).astype(float).reshape(-1, 3)
    con2 = del2 = None
    if n2:
        con2 = b.arr(">i4", 4 * n2).reshape(-1, 4).astype(np.int64)
        del2 = b.arr("i1", n2)
    def2, ptx2 = [], []
    if np2:
        def2 = [int(x) for x in b.arr(">i4", np2)]
        ptx2 = [b.text(PTEXT) for _ in range(np2)]
    b.arr(">u2", 3 * nn)                                      # nodal normals
    ftext, nodal, efun2 = [], [], []
    if nfun + nefun:
        ftext = [b.text(TEXT) for _ in range(nfun + nefun)]
        if nfun:
            a = b.arr(">f4", nn * nfun).reshape(nfun, nn)
            nodal = [(_name(ftext[i]), a[i]) for i in range(nfun)]
        if nefun:
            a = b.arr(">f4", n2 * nefun).reshape(nefun, n2)
            efun2 = [(_name(ftext[nfun + i]), a[i]) for i in range(nefun)]
    vtext = [b.text(TEXT) for _ in range(nvect)]
    vect = b.arr(">f4", 3 * nn * nvect).reshape(max(nvect, 0), nn, 3) if nvect else np.zeros((0, nn, 3), np.float32)
    tens2 = []
    if ntens:
        ttext = [b.text(TEXT) for _ in range(ntens)]
        a = b.arr(">f4", ntens * n2 * 3).reshape(ntens, n2, 3)
        tens2 = [(_name(ttext[i]), a[i]) for i in range(ntens)]
    if flag[0] == 1:
        b.arr(">f4", n2); b.arr(">f4", nn)
    nodnum = elnum2 = None
    if flag[1]:
        nodnum = b.arr(">i4", nn)
        elnum2 = b.arr(">i4", n2)
    if flag[4]:
        b.arr(">i4", 3 * np2)

    # ---------------------------------------------------------------- 3D
    n3 = 0
    con3 = del3 = elnum3 = None
    def3, ptx3, efun3, tens3 = [], [], [], []
    if flag[2]:
        n3, np3, nefun3, ntens3 = (int(x) for x in b.arr(">i4", 4))
        con3 = b.arr(">i4", 8 * n3).reshape(-1, 8).astype(np.int64)
        del3 = b.arr("u1", n3)
        def3 = [int(x) for x in b.arr(">i4", np3)]
        ptx3 = [b.text(PTEXT) for _ in range(np3)]
        if nefun3:
            tx = [b.text(TEXT) for _ in range(nefun3)]
            a = b.arr(">f4", nefun3 * n3).reshape(nefun3, n3)
            efun3 = [(_name(tx[i]), a[i]) for i in range(nefun3)]
        if ntens3:
            tx = [b.text(TEXT) for _ in range(ntens3)]
            a = b.arr(">f4", n3 * 6 * ntens3).reshape(ntens3, n3, 6)
            tens3 = [(_name(tx[i]), a[i]) for i in range(ntens3)]
        if flag[0] == 1:
            b.arr(">f4", n3)
        if flag[1] == 1:
            elnum3 = b.arr(">i4", n3)
        if flag[4]:
            b.arr(">i4", 3 * np3)

    # ---------------------------------------------------------------- 1D
    n1 = 0
    con1 = del1 = elnum1 = None
    def1, ptx1, efun1, tors1 = [], [], [], []
    if flag[3]:
        n1, np1, nefun1, ntors1, skew1 = (int(x) for x in b.arr(">i4", 5))
        con1 = b.arr(">i4", 2 * n1).reshape(-1, 2).astype(np.int64)
        del1 = b.arr("u1", n1)
        def1 = [int(x) for x in b.arr(">i4", np1)]
        ptx1 = [b.text(PTEXT) for _ in range(np1)]
        if nefun1:
            tx = [b.text(TEXT) for _ in range(nefun1)]
            a = b.arr(">f4", n1 * nefun1).reshape(nefun1, n1)
            efun1 = [(_name(tx[i]), a[i]) for i in range(nefun1)]
        if ntors1:
            tx = [b.text(TEXT) for _ in range(ntors1)]
            a = b.arr(">f4", n1 * 9 * ntors1).reshape(ntors1, n1, 9)
            tors1 = [(_name(tx[i]), a[i]) for i in range(ntors1)]
        if skew1:
            b.arr(">i4", n1)
        if flag[0] == 1:
            b.arr(">f4", n1)
        if flag[1] == 1:
            elnum1 = b.arr(">i4", n1)

    # ---------------------------------------------------------------- result
    nc = n1 + n2 + n3
    o2, o3 = n1, n1 + n2
    cells = []
    if n1:
        cells.append(("line", con1, None, np.arange(n1, dtype=np.int64)))
    if n2:
        tri = _first(con2)[1] == 3
        if tri.any():
            ti = np.nonzero(tri)[0]
            cells.append(("tri", _collapse(con2, ti, 3), None, ti + o2))
        qi = np.nonzero(~tri)[0]
        if len(qi):
            cells.append(("quad", con2[qi], None, qi + o2))
    if n3:
        tet = _first(con3)[1] == 4
        if tet.any():
            ti = np.nonzero(tet)[0]
            cells.append(("tet", _collapse(con3, ti, 4), None, ti + o3))
        hi = np.nonzero(~tet)[0]
        if len(hi):
            cells.append(("hex", con3[hi], None, hi + o3))

    point = {"NODE_ID": (nodnum.astype(np.int64) if nodnum is not None else np.arange(1, nn + 1, dtype=np.int64))}
    for name, a in nodal:
        point[name] = a
    for i, name in enumerate(vtext):
        point[_name(name)] = vect[i]

    def full(dim, a, ncomp=1):
        shape = (nc,) if ncomp == 1 else (nc, ncomp)
        out = np.full(shape, np.nan, np.float32)
        lo = {1: 0, 2: o2, 3: o3}[dim]
        out[lo:lo + len(a)] = a
        return out

    cell = {}
    eid = np.zeros(nc, np.int64)
    for lo, a in ((0, elnum1), (o2, elnum2), (o3, elnum3)):
        if a is not None:
            eid[lo:lo + len(a)] = a
    cell["ELEMENT_ID"] = eid
    cell["PART_ID"] = np.concatenate([_part_ids(def1, ptx1, n1), _part_ids(def2, ptx2, n2), _part_ids(def3, ptx3, n3)])
    er = np.zeros(nc, np.int32)
    for lo, a in ((0, del1), (o2, del2), (o3, del3)):
        if a is not None:
            er[lo:lo + len(a)] = (a.astype(np.int32) == 1)
    cell["EROSION_STATUS"] = er
    for name, a in efun1:
        cell["1DELEM_" + name] = full(1, a)
    for name, a in tors1:
        for j, c in enumerate(("F1", "F2", "F3", "M1", "M2", "M3", "M4", "M5", "M6")):
            cell["1DELEM_" + name + c] = full(1, a[:, j])
    for name, a in efun2:
        cell["2DELEM_" + name] = full(2, a)
    for name, a in tens2:
        T = np.zeros((len(a), 9), np.float32)            # [xx xy 0; xy yy 0; 0 0 0]
        T[:, 0] = a[:, 0]; T[:, 1] = a[:, 2]; T[:, 3] = a[:, 2]; T[:, 4] = a[:, 1]
        cell["2DELEM_" + name] = full(2, T, 9)
    for name, a in efun3:
        cell["3DELEM_" + name] = full(3, a)
    for name, a in tens3:
        T = a[:, [0, 3, 4, 3, 1, 5, 4, 5, 2]]            # [xx xy xz; xy yy yz; xz yz zz]
        cell["3DELEM_" + name] = full(3, T, 9)
    pnames = {}
    for t_ in list(ptx1) + list(ptx2) + list(ptx3):
        m = re.match(r"\s*([+-]?\d+)\s*(.*)", t_)
        if m:
            pnames[int(m.group(1))] = m.group(2).strip()
    return {"xyz": xyz, "cells": cells, "point": point, "cell": cell, "time": t, "cycle": None, "format": "anim",
            "flags": flag, "part_names": pnames}
