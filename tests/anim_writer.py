"""Writer of synthetic OpenCourant animation files (FASTMAGI10, big-endian) for the tests of explicit/anim.py."""
import numpy as np


def _t(s, n):
    b = s.encode("latin-1")[:n - 1]
    return b + b"\0" * (n - len(b))


def write_anim(path, time, xyz, quads=(), parts2=(), nodal=(), efun2=(), vect=(), tens2=(), hexes=(), parts3=(),
               efun3=(), tens3=(), lines=(), parts1=(), efun1=(), tors1=(), mass=True, numbering=True, hierarchy=False,
               del2=None, del3=None, del1=None, node_ids=None):
    """parts*: [(end index, text)]; nodal / efun*: [(name, values)]; vect: [(name, (n, 3))]; tens2: [(name, (n, 3))];
    tens3: [(name, (n, 6))]; tors1: [(name, (n, 9))]."""
    xyz = np.asarray(xyz, float).reshape(-1, 3)
    nn = len(xyz)
    q = np.asarray(quads, np.int64).reshape(-1, 4)
    h = np.asarray(hexes, np.int64).reshape(-1, 8)
    ln = np.asarray(lines, np.int64).reshape(-1, 2)
    n2, n3, n1 = len(q), len(h), len(ln)
    i4 = lambda *v: np.asarray(v, ">i4").tobytes()
    f4 = lambda a: np.asarray(a, ">f4").tobytes()
    out = [i4(0x542c), f4([time]), _t("TIME", 81), _t("anim", 81), _t("OpenCourant", 81)]
    flags = [1 if mass else 0, 1 if numbering else 0, 1 if n3 else 0, 1 if n1 else 0, 1 if hierarchy else 0, 0, 0, 0, 0, 0]
    out.append(i4(*flags))
    out.append(i4(nn, n2, len(parts2), len(nodal), len(efun2), len(vect), len(tens2), 0))
    out.append(f4(xyz.reshape(-1)))
    if n2:
        out.append(i4(*q.reshape(-1)))
        out.append(np.asarray(del2 if del2 is not None else np.ones(n2), "i1").tobytes())
    if parts2:
        out.append(i4(*[e for e, _ in parts2]))
        out += [_t(t, 50) for _, t in parts2]
    out.append(np.full(3 * nn, 3000, ">u2").tobytes())
    if nodal or efun2:
        out += [_t(n, 81) for n, _ in list(nodal) + list(efun2)]
        for _, a in nodal:
            out.append(f4(a))
        for _, a in efun2:
            out.append(f4(a))
    out += [_t(n, 81) for n, _ in vect]
    for _, a in vect:
        out.append(f4(np.asarray(a).reshape(-1)))
    if tens2:
        out += [_t(n, 81) for n, _ in tens2]
        for _, a in tens2:
            out.append(f4(np.asarray(a).reshape(-1)))
    if mass:
        out.append(f4(np.ones(n2))); out.append(f4(np.ones(nn)))
    if numbering:
        out.append(i4(*(node_ids if node_ids is not None else range(101, 101 + nn))))
        out.append(i4(*range(1001, 1001 + n2)) if n2 else b"")
    if hierarchy:
        out.append(i4(*([0] * 3 * len(parts2))) if parts2 else b"")
    if n3:
        out.append(i4(n3, len(parts3), len(efun3), len(tens3)))
        out.append(i4(*h.reshape(-1)))
        out.append(np.asarray(del3 if del3 is not None else np.ones(n3), "u1").tobytes())
        out.append(i4(*[e for e, _ in parts3]) if parts3 else b"")
        out += [_t(t, 50) for _, t in parts3]
        if efun3:
            out += [_t(n, 81) for n, _ in efun3]
            for _, a in efun3:
                out.append(f4(a))
        if tens3:
            out += [_t(n, 81) for n, _ in tens3]
            for _, a in tens3:
                out.append(f4(np.asarray(a).reshape(-1)))
        if mass:
            out.append(f4(np.ones(n3)))
        if numbering:
            out.append(i4(*range(3001, 3001 + n3)))
        if hierarchy:
            out.append(i4(*([0] * 3 * len(parts3))) if parts3 else b"")
    if n1:
        out.append(i4(n1, len(parts1), len(efun1), len(tors1), 0))
        out.append(i4(*ln.reshape(-1)))
        out.append(np.asarray(del1 if del1 is not None else np.ones(n1), "u1").tobytes())
        out.append(i4(*[e for e, _ in parts1]) if parts1 else b"")
        out += [_t(t, 50) for _, t in parts1]
        if efun1:
            out += [_t(n, 81) for n, _ in efun1]
            for _, a in efun1:
                out.append(f4(a))
        if tors1:
            out += [_t(n, 81) for n, _ in tors1]
            for _, a in tors1:
                out.append(f4(np.asarray(a).reshape(-1)))
        if mass:
            out.append(f4(np.ones(n1)))
        if numbering:
            out.append(i4(*range(5001, 5001 + n1)))
        if hierarchy:
            out.append(i4(*([0] * 3 * len(parts1))) if parts1 else b"")
    if hierarchy:
        out.append(i4(0)); out.append(i4(0, 0))      # subsets, materials, properties
    with open(path, "wb") as f:
        f.write(b"".join(out))


def sample(path, time=0.0, d=0.0, erode=False):
    """A model with a quad, a triangle, a hex, a tet and a beam; nodal displacement d along x of nodes 4.."""
    xyz = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],                     # shell nodes 0-3
           [2, 0, 0], [3, 0, 0], [3, 1, 0], [2, 1, 0], [2, 0, 1], [3, 0, 1], [3, 1, 1], [2, 1, 1],   # hex 4-11
           [4, 0, 0], [5, 0, 0], [4, 1, 0], [4, 0, 1],                     # tet 12-15
           [6, 0, 0], [7, 0, 0]]                                         # beam 16-17
    xyz = np.array(xyz, float)
    disp = np.zeros_like(xyz)
    disp[4:, 0] = d
    xyz = xyz + disp
    nn = len(xyz)
    quads = [[0, 1, 2, 3], [0, 2, 3, 3]]
    hexes = [[4, 5, 6, 7, 8, 9, 10, 11], [12, 13, 14, 14, 15, 15, 15, 15]]
    write_anim(path, time, xyz, quads=quads, parts2=[(2, "1  shell part")],
               nodal=[("Velocity Norm", np.arange(nn) * 0.5)], efun2=[("Von Mises", [10.0, 20.0])],
               vect=[("Displacement", disp), ("Velocity", disp * 2)],
               tens2=[("Strain (upper)", [[0.01, 0.02, 0.003], [0.04, -0.01, 0.0]])],
               hexes=hexes, parts3=[(1, "2 solid"), (2, "3 tet")], efun3=[("Von Mises", [30.0, 40.0])],
               tens3=[("Stress", [[1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, 1]])],
               lines=[[16, 17]], parts1=[(1, "4 beam")], efun1=[("Force", [7.0])],
               tors1=[("Torsor", [np.arange(9) + 1.0])],
               del2=[1, 0 if erode else 1], del3=[1, 1], del1=[1])
    return xyz, disp
