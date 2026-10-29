# -*- coding: utf-8 -*-
"""STL import: a closed triangle mesh to a solid.

The mesh is welded, oriented and split into regions: flat regions (adjacent triangles in one plane within the
tolerance) and, with "fit", smooth curved regions fitted with a cylinder, cone or sphere within the tolerance.
Curved regions that do not fit stay as their flat facets. Each region becomes one face; the edges between two
regions are the intersection curves of their surfaces (lines between planes, circles and ellipses on cylinders,
cones and spheres), trimmed at the corners where three or more regions meet.

stl_solid(path, opts) -> (solid, report); opts: "fit" (bool), "tolerance" (mm, 0: automatic, 1e-3 of the size),
"angle" (deg, flat regions: largest angle between triangle normals, default 0.5), "smooth" (deg, curved regions:
largest angle between neighbouring triangles, default 30).
"""
import math
import os
import time
import re
import struct
from collections import defaultdict, deque

import numpy as np

_CACHE = {}
MAX_FACES = 150000                   # faces of one converted solid
FIT_BUDGET_S = 60.0                  # time for fitted surfaces; after it the solid is made of flat facets


# --------------------------------------------------------------------------- reading and welding

def read_stl(path):
    """Triangles (n, 3, 3) of a binary or ASCII STL file."""
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if 84 + 50 * n == len(data):
            dt = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])
            return np.frombuffer(data, dtype=dt, count=n, offset=84)["v"].astype(float)
    txt = data.decode("ascii", errors="ignore")
    nums = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", txt)
    if not nums:
        raise ValueError("the file is not an STL file or has no triangles")
    return np.array(nums, float).reshape(-1, 3, 3)


def weld(tris, tol):
    """Vertices (k, 3) and triangles (m, 3) of vertex indices; vertices closer than tol are merged, degenerate
    triangles removed."""
    P = tris.reshape(-1, 3)
    q = np.round(P / tol).astype(np.int64)
    _, idx, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    V = P[idx]
    T = inv.reshape(-1, 3)
    T = T[(T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])]
    a = 0.5 * np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1)
    T = T[a > 1e-12 * max(1.0, float(np.ptp(V, axis=0).max())) ** 2]
    used = np.unique(T)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    return V[used], remap[T]


def _edges(T):
    """Undirected edge -> list of (triangle, k) with the directed edge T[t, k] -> T[t, (k + 1) % 3]."""
    em = defaultdict(list)
    for t, (a, b, c) in enumerate(T.tolist()):
        for k, (u, v) in enumerate(((a, b), (b, c), (c, a))):
            em[(u, v) if u < v else (v, u)].append((t, k))
    return em


def orient(V, T):
    """Triangles turned consistently, outward (positive volume). Raises for an open or non-manifold mesh."""
    em = _edges(T)
    bad = [e for e, l in em.items() if len(l) != 2]
    if bad:
        n1 = sum(1 for e in bad if len(em[e]) == 1)
        raise ValueError("the mesh is not closed: %d open edge(s), %d edge(s) shared by more than two triangles"
                         % (n1, len(bad) - n1))
    T = T.copy()
    nb = [[] for _ in range(len(T))]
    for e, ((t1, k1), (t2, k2)) in em.items():
        nb[t1].append((t2, e))
        nb[t2].append((t1, e))
    seen = np.zeros(len(T), bool)
    for s in range(len(T)):
        if seen[s]:
            continue
        seen[s] = True
        dq = deque([s])
        while dq:
            t = dq.popleft()
            for o, (u, v) in nb[t]:
                if seen[o]:
                    continue
                # same direction of the shared edge in both triangles: turn the other one
                d1 = _dir(T[t], u, v)
                d2 = _dir(T[o], u, v)
                if d1 == d2:
                    T[o] = T[o][::-1]
                seen[o] = True
                dq.append(o)
    vol = np.einsum("ij,ij->i", V[T[:, 0]], np.cross(V[T[:, 1]], V[T[:, 2]])).sum() / 6.0
    if vol < 0:
        T = T[:, ::-1].copy()
        vol = -vol
    return T, vol


def _dir(tri, u, v):
    a, b, c = tri
    return (a, b) == (u, v) or (b, c) == (u, v) or (c, a) == (u, v)


# --------------------------------------------------------------------------- fitting

def fit_plane(P):
    c = P.mean(0)
    _, s, vt = np.linalg.svd(P - c, full_matrices=False)
    n = vt[-1]
    return {"kind": "plane", "p": c, "n": n}, float(np.abs((P - c) @ n).max())


def _circle2(Q):
    A = np.c_[2 * Q, np.ones(len(Q))]
    b = (Q ** 2).sum(1)
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    c = x[:2]
    return c, math.sqrt(max(x[2] + c @ c, 0.0))


def fit_cyl_cone(P, C, N, W):
    """Cylinder or cone from the points P, the triangle centroids C and normals N (weights W = areas): the normals
    of a cylinder are at a right angle to the axis, those of a cone at a constant angle; the axis is the normal of
    the plane through the normal vectors. The apex of a cone lies on every triangle plane."""
    m = (N * W[:, None]).sum(0) / W.sum()
    Cv = ((N - m) * W[:, None]).T @ (N - m)
    w, vec = np.linalg.eigh(Cv)
    a = vec[:, 0]
    sa = float(m @ a)                        # sin of the half angle of a cone (0: cylinder)
    e1 = np.cross(a, [1.0, 0, 0] if abs(a[0]) < 0.9 else [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    if abs(sa) < 0.02:
        c2, r = _circle2(np.c_[P @ e1, P @ e2])
        o = c2[0] * e1 + c2[1] * e2
        dist = lambda X: np.linalg.norm(X - o - np.outer(X @ a - o @ a, a), axis=1) - r
        return {"kind": "cylinder", "o": o, "a": a, "r": r}, dist
    A = (N * W[:, None]).T @ N
    b = (N * W[:, None]).T @ np.einsum("ij,ij->i", N, C)
    apex = np.linalg.lstsq(A, b, rcond=None)[0]
    half = math.asin(min(1.0, abs(sa)))
    if ((P - apex) @ a).mean() < 0:
        a = -a

    def dist(X):
        t = (X - apex) @ a
        rr = np.linalg.norm(X - apex - np.outer(t, a), axis=1)
        return rr * math.cos(half) - t * math.sin(half)
    return {"kind": "cone", "apex": apex, "a": a, "half": half}, dist


def fit_torus(P, C, N, W):
    """Torus (a fillet along a circular edge) from the triangle centroids C and normals N: the points C - r N lie on
    the spine circle (centre o, axis a, radius R) for the minor radius r (signed: the normals point away from the
    spine or towards it). r is found by a search for the most circular and planar point set."""
    size = float(np.ptp(C, axis=0).max())
    if size <= 0 or len(C) < 6:
        raise ValueError("too few points")

    def spine(r):
        Q = C - r * N
        c = Q.mean(0)
        _, _, vt = np.linalg.svd(Q - c, full_matrices=False)
        a = vt[-1]
        e1 = np.cross(a, [1.0, 0, 0] if abs(a[0]) < 0.9 else [0, 1.0, 0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(a, e1)
        c2, R = _circle2(np.c_[(Q - c) @ e1, (Q - c) @ e2])
        o = c + c2[0] * e1 + c2[1] * e2
        h = (Q - o) @ a
        rho = np.linalg.norm(Q - o - np.outer(h, a), axis=1) - R
        return float(np.sqrt(((h ** 2 + rho ** 2) * W).sum() / W.sum())), o, a, R

    rs = np.r_[-np.geomspace(size, size * 1e-3, 40), np.geomspace(size * 1e-3, size, 40)]
    errs = [spine(r)[0] for r in rs]
    k = int(np.argmin(errs))
    lo, hi = rs[max(k - 1, 0)], rs[min(k + 1, len(rs) - 1)]
    g = (math.sqrt(5) - 1) / 2
    for _ in range(40):                       # golden section between the neighbours of the best sample
        x1, x2 = hi - g * (hi - lo), lo + g * (hi - lo)
        if spine(x1)[0] < spine(x2)[0]:
            hi = x2
        else:
            lo = x1
    r = (lo + hi) / 2
    _, o, a, R = spine(r)
    r = abs(r)
    if R <= r:
        raise ValueError("not a ring torus")

    def dist(X):
        v = X - o
        h = v @ a
        rho = np.linalg.norm(v - np.outer(h, a), axis=1)
        return np.sqrt((rho - R) ** 2 + h ** 2) - r
    return {"kind": "torus", "o": o, "a": a, "R": R, "r": r}, dist


def fit_sphere(P):
    A = np.c_[2 * P, np.ones(len(P))]
    b = (P ** 2).sum(1)
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    c = x[:3]
    r = math.sqrt(max(x[3] + c @ c, 0.0))
    return {"kind": "sphere", "c": c, "r": r}, lambda X: np.linalg.norm(X - c, axis=1) - r


def surface_normal(sf, X):
    """Unit normals of the fitted surface at the points X (direction away from the axis or centre)."""
    k = sf["kind"]
    if k == "sphere":
        d = X - sf["c"]
    elif k == "torus":
        o, a = sf["o"], sf["a"]
        v = X - o
        rad = v - np.outer(v @ a, a)
        rad /= np.linalg.norm(rad, axis=1)[:, None]
        d = X - (o + sf["R"] * rad)
    elif k == "cylinder":
        a = sf["a"]
        d = X - sf["o"] - np.outer((X - sf["o"]) @ a, a)
    else:
        a, h = sf["a"], sf["half"]
        v = X - sf["apex"]
        rad = v - np.outer(v @ a, a)
        rad /= np.linalg.norm(rad, axis=1)[:, None]
        d = rad * math.cos(h) - a * math.sin(h)
    return d / np.linalg.norm(d, axis=1)[:, None]


def best_fit(P, C, N, W, tol, max_angle, torus=True):
    """The simplest of cylinder, cone and sphere that fits: vertices within tol, triangle centroids within 4 tol
    and triangle normals within max_angle (deg) of the surface normals (either side). (surface, deviation) or None."""
    cands = []
    for fn in (lambda: fit_cyl_cone(P, C, N, W), lambda: fit_sphere(P)) + ((lambda: fit_torus(P, C, N, W),) if torus else ()):
        try:
            cands.append(fn())
        except Exception:
            pass
    size = float(np.ptp(P, axis=0).max())
    cmin = math.cos(math.radians(max_angle))
    # a curved surface: the normals must turn by more than a few degrees
    spread = float(np.degrees(np.arccos(np.clip((N @ N.T).min(), -1, 1)))) if len(N) <= 400 else \
        float(np.degrees(np.arccos(np.clip((N @ N[np.random.default_rng(0).choice(len(N), 400)].T).min(), -1, 1))))
    if spread < 3.0:
        return None
    ok = []
    for sf, dist in cands:
        if max(sf.get("r", 0), sf.get("R", 0)) > 50 * max(size, 1e-9) or not np.isfinite(dist(P)).all():
            continue
        if sf["kind"] == "cone" and sf["half"] > math.radians(80):
            continue
        dv = float(np.abs(dist(P)).max())
        if dv > tol or float(np.abs(dist(C)).max()) > 4 * tol:
            continue
        if (np.abs(np.einsum("ij,ij->i", surface_normal(sf, C), N)) < cmin).any():
            continue
        ok.append((sf, dv))
    if not ok:
        return None
    # the simplest surface (cylinder or cone, sphere, torus) unless a later one is much closer (a narrow band of a
    # torus also lies within the tolerance of a sphere)
    best = min(dv for _, dv in ok)
    return next((sf, dv) for sf, dv in ok if dv <= 3 * best + 1e-12)


# --------------------------------------------------------------------------- regions

CURVED_COS = math.cos(math.radians(0.1))   # normals of one region turning by more: a curved surface


def regions(V, T, tol, ang_flat, ang_smooth, fit):
    """Region index of each triangle and the surface of each region."""
    m = len(T)
    P0, P1, P2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    cr = np.cross(P1 - P0, P2 - P0)
    area = 0.5 * np.linalg.norm(cr, axis=1)
    N = cr / (2 * area[:, None])
    em = _edges(T)
    nb = [[] for _ in range(m)]
    for e, ((t1, _), (t2, _)) in em.items():
        nb[t1].append(t2)
        nb[t2].append(t1)
    cos_flat, cos_smooth = math.cos(math.radians(ang_flat)), math.cos(math.radians(ang_smooth))
    reg = -np.ones(m, int)
    surf = []
    total = area.sum()
    for s in np.argsort(-area):
        if reg[s] >= 0:
            continue
        rid = len(surf)
        n0, p0 = N[s], P0[s]
        reg[s] = rid
        members, dq = [s], deque([s])
        while dq:
            t = dq.popleft()
            for o in nb[t]:
                if reg[o] >= 0 or N[o] @ n0 < cos_flat:
                    continue
                if max(abs((V[T[o]] - p0) @ n0)) > tol:
                    continue
                reg[o] = rid
                members.append(o)
                dq.append(o)
        idx = np.unique(T[members])
        pl, pdev = fit_plane(V[idx])
        if pl["n"] @ n0 < 0:
            pl["n"] = -pl["n"]
        surf.append(dict(pl, tris=members, dev=pdev))
    if not fit:
        return reg, surf, area, N
    # curved candidates: flat regions joined smoothly (angle below "smooth") to two or more neighbours that are
    # small or not exactly flat (a fine mesh of a curved surface gives flat regions of many triangles within tol)
    cand = np.zeros(m, bool)
    for rid, s in enumerate(surf):
        tr = s["tris"]
        small = len(tr) <= 8 and area[tr].sum() <= 0.02 * total
        if not small and s["dev"] <= 0.02 * tol:
            # a fine mesh of a curved surface: flat within the tolerance, but the triangle normals turn (a planar
            # face has one normal; the larger triangles are used, small slivers have imprecise normals)
            at = area[tr]
            big = np.asarray(tr)[at >= 0.1 * at.max()]
            if len(big) < 2 or float((N[big] @ N[big[0]]).min()) >= CURVED_COS:
                continue
        nsm = set()
        for t in tr:
            for o in nb[t]:
                if reg[o] != rid and N[t] @ N[o] >= cos_smooth:
                    nsm.add(int(reg[o]))
        if len(nsm) >= 2:
            cand[tr] = True
    newreg = reg.copy()
    newsurf = []
    seen = np.zeros(m, bool)
    groups = []
    for s in range(m):
        if not cand[s] or seen[s]:
            continue
        seen[s] = True
        g, dq = [s], deque([s])
        while dq:
            t = dq.popleft()
            for o in nb[t]:
                if cand[o] and not seen[o] and N[t] @ N[o] >= cos_smooth:
                    seen[o] = True
                    g.append(o)
                    dq.append(o)
        groups.append(g)
    for g in groups:
        if len(g) < 6:
            continue
        P = V[np.unique(T[g])]
        Cg = (V[T[g, 0]] + V[T[g, 1]] + V[T[g, 2]]) / 3.0
        # normals of the fitted surface within a few mesh steps of the triangle normals (the median angle between
        # neighbouring triangles of the group): a surface that only passes within the tolerance of a group made of
        # two tangent surfaces (a cylinder running into a fillet) is refused and the group is split
        gs = set(g)
        steps = [float(N[t] @ N[o]) for t in g[:2000] for o in nb[t] if o in gs]
        step = math.degrees(math.acos(min(1.0, float(np.median(steps))))) if steps else ang_smooth
        ang_fit = min(ang_smooth, max(3.0, 2.5 * step))
        best = best_fit(P, Cg, N[g], area[g], tol, ang_fit)
        found = [(best[0], g)] if best is not None else _split_group(g, V, T, N, area, reg, nb, tol, ang_smooth)
        for sf, gg in found:
            gg = list(gg)
            Cgg = (V[T[gg, 0]] + V[T[gg, 1]] + V[T[gg, 2]]) / 3.0
            sid = len(newsurf)
            for part in _halves(sf, gg, Cgg, reg):
                for t in part:
                    newreg[t] = -2 - len(newsurf)
                newsurf.append(dict(sf, tris=part, sid=sid))
    # renumber: flat regions not dissolved keep their surface
    out_reg = -np.ones(m, int)
    out_surf = []
    keymap = {}
    for t in range(m):
        k = int(newreg[t])
        if k not in keymap:
            keymap[k] = len(out_surf)
            out_surf.append(newsurf[-2 - k] if k <= -2 else surf[k])
        out_reg[t] = keymap[k]
    for i, s in enumerate(out_surf):
        s = dict(s)
        s["tris"] = [t for t in s["tris"] if out_reg[t] == i]
        out_surf[i] = s
    return out_reg, out_surf, area, N


def _fits_unit(sf, dist, V, T, N, tris, tol, cmin):
    """True when the triangles lie on the fitted surface (vertices within tol, centroids within 4 tol, normals
    within the angle)."""
    P = V[np.unique(T[tris])]
    C = (V[T[tris, 0]] + V[T[tris, 1]] + V[T[tris, 2]]) / 3.0
    if float(np.abs(dist(P)).max()) > tol or float(np.abs(dist(C)).max()) > 4 * tol:
        return False
    return not (np.abs(np.einsum("ij,ij->i", surface_normal(sf, C), N[tris])) < cmin).any()


def _split_group(g, V, T, N, area, reg, nb, tol, ang_smooth, min_tris=16):
    """A smooth group that no single surface fits (for example a cone at a rounded corner joined tangentially to
    straight chamfers): grown again from its smallest flat facets. Up to 24 triangles, a facet is added when the
    surface fitted to all facets still fits; then neighbouring facets that lie on the fitted surface are added, and
    the surface is fitted again each time the region has grown by a quarter. Returns [(surface, triangles)] with at least min_tris triangles each; facets left
    over stay flat."""
    units = defaultdict(list)
    for t in g:
        units[int(reg[t])].append(t)
    uadj = defaultdict(set)
    gs = set(g)
    for u, tr in units.items():
        for t in tr:
            for o in nb[t]:
                if o in gs and int(reg[o]) != u:
                    uadj[u].add(int(reg[o]))
    uarea = {u: float(area[tr].sum()) for u, tr in units.items()}
    cmin = math.cos(math.radians(ang_smooth))
    used, tried, out = set(), set(), []
    for seed in sorted(units, key=lambda u: uarea[u]):
        if seed in used or seed in tried:
            continue
        tried.add(seed)
        # start: facets added one by one while the surface fitted to all of them still fits, until the normals
        # turn by 10 deg (a patch of a finely meshed surface is too flat to fit) or 400 triangles; before the
        # normals turn by 3 deg no fit is possible and facets are added without one
        cur, cur_t, inset, fit = [seed], list(units[seed]), {seed}, None
        dq = deque(sorted(uadj[seed] - used, key=lambda u: uarea[u]))
        n0 = N[cur_t[0]]
        while dq and len(cur_t) < 400:
            u = dq.popleft()
            if u in inset or u in used:
                continue
            cand = cur_t + units[u]
            turn = float(np.degrees(np.arccos(np.clip((N[cand] @ n0).min(), -1, 1))))
            if turn >= 3.0:
                P = V[np.unique(T[cand])]
                C = (V[T[cand, 0]] + V[T[cand, 1]] + V[T[cand, 2]]) / 3.0
                f2 = best_fit(P, C, N[cand], area[cand], tol, ang_smooth, torus=False)
                if f2 is None:
                    continue
                fit = f2
            inset.add(u)
            cur.append(u)
            cur_t = cand
            dq.extend(sorted(uadj[u] - inset - used, key=lambda x: uarea[x]))
            if fit is not None and turn >= 10.0:
                break
        if fit is None or len(cur_t) < 6:
            continue
        sf = fit[0]
        dist = _dist_fn(sf)
        last = len(cur_t)
        frontier = deque(sorted(set().union(*[uadj[u] for u in cur]) - inset - used, key=lambda u: uarea[u]))
        rejected = set()
        while frontier or rejected:
            if not frontier:
                # facets rejected by the fit of a smaller region: tried again with a fit of the whole region
                P = V[np.unique(T[cur_t])]
                C = (V[T[cur_t, 0]] + V[T[cur_t, 1]] + V[T[cur_t, 2]]) / 3.0
                refit = best_fit(P, C, N[cur_t], area[cur_t], tol, ang_smooth, torus=False)
                if refit is None or len(cur_t) == last:
                    break
                sf, dist, last = refit[0], _dist_fn(refit[0]), len(cur_t)
                frontier.extend(rejected)
                rejected = set()
                continue
            u = frontier.popleft()
            if u in inset or u in used:
                continue
            if not _fits_unit(sf, dist, V, T, N, units[u], tol, cmin):
                rejected.add(u)
                continue
            inset.add(u)
            cur.append(u)
            cur_t += units[u]
            frontier.extend(uadj[u] - inset - used)
            if len(cur_t) > 1.25 * last:
                P = V[np.unique(T[cur_t])]
                C = (V[T[cur_t, 0]] + V[T[cur_t, 1]] + V[T[cur_t, 2]]) / 3.0
                refit = best_fit(P, C, N[cur_t], area[cur_t], tol, ang_smooth, torus=False)
                if refit is None:
                    for x in units[u]:
                        cur_t.remove(x)
                    cur.pop()
                    inset.discard(u)
                    break
                sf, dist, last = refit[0], _dist_fn(refit[0]), len(cur_t)
        if len(cur_t) >= min_tris:
            used |= set(cur)
            out.append((sf, cur_t))
    return out


def _dist_fn(sf):
    """Signed distance function of a fitted surface."""
    k = sf["kind"]
    if k == "sphere":
        return lambda X: np.linalg.norm(X - sf["c"], axis=1) - sf["r"]
    if k == "torus":
        o, a, R, r = sf["o"], sf["a"], sf["R"], sf["r"]

        def dt(X):
            v = X - o
            h = v @ a
            return np.sqrt((np.linalg.norm(v - np.outer(h, a), axis=1) - R) ** 2 + h ** 2) - r
        return dt
    if k == "cylinder":
        o, a, r = sf["o"], sf["a"], sf["r"]
        return lambda X: np.linalg.norm(X - o - np.outer((X - o) @ a, a), axis=1) - r
    apex, a, h = sf["apex"], sf["a"], sf["half"]

    def d(X):
        t = (X - apex) @ a
        return np.linalg.norm(X - apex - np.outer(t, a), axis=1) * math.cos(h) - t * math.sin(h)
    return d


def _halves(sf, g, Cg, reg):
    """The triangles g of a cylinder or cone that goes all the way round its axis, in two halves (a face closed
    round the axis would need a seam edge): whole flat facets (regions reg) go to the half of their mean angle, so
    the boundary between the halves runs along facet edges (generator lines)."""
    if sf["kind"] not in ("cylinder", "cone", "torus"):
        return [g]
    a = sf["a"]
    e1 = np.cross(a, [1.0, 0, 0] if abs(a[0]) < 0.9 else [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    base = sf["apex"] if sf["kind"] == "cone" else sf["o"]
    th = np.arctan2((Cg - base) @ e2, (Cg - base) @ e1)
    srt = np.sort(th)
    gaps = np.diff(np.r_[srt, srt[0] + 2 * math.pi])
    if gaps.max() > math.radians(90):
        return [g]                                   # not closed round the axis
    units = defaultdict(list)
    for t, ang in zip(g, th):
        units[int(reg[t])].append((t, ang))
    A, B = [], []
    for u, lst in units.items():
        m = math.atan2(sum(math.sin(x) for _, x in lst), sum(math.cos(x) for _, x in lst))
        (A if 0 <= m < math.pi else B).extend(t for t, _ in lst)
    return [A, B] if A and B else [g]


# --------------------------------------------------------------------------- B-rep

def _geom_surface(s):
    from OCP.Geom import Geom_Plane, Geom_CylindricalSurface, Geom_ConicalSurface, Geom_SphericalSurface, Geom_ToroidalSurface
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3
    P = lambda v: gp_Pnt(*[float(x) for x in v])
    D = lambda v: gp_Dir(*[float(x) for x in v])
    k = s["kind"]
    if k == "plane":
        return Geom_Plane(P(s["p"]), D(s["n"]))
    if k == "cylinder":
        return Geom_CylindricalSurface(gp_Ax3(P(s["o"]), D(s["a"])), float(s["r"]))
    if k == "cone":
        return Geom_ConicalSurface(gp_Ax3(P(s["apex"]), D(s["a"])), float(s["half"]), 0.0)
    if k == "torus":
        return Geom_ToroidalSurface(gp_Ax3(P(s["o"]), D(s["a"])), float(s["R"]), float(s["r"]))
    return Geom_SphericalSurface(gp_Ax3(P(s["c"]), D([0, 0, 1])), float(s["r"]))


def _loops(T, reg):
    """Directed boundary edges of each region (in the turning of its triangles) chained into loops:
    {region: [[(u, v, other region), ...], ...]}."""
    em = _edges(T)
    out = defaultdict(dict)                       # region -> {u: [(v, other)]}
    for e, ((t1, k1), (t2, k2)) in em.items():
        r1, r2 = reg[t1], reg[t2]
        if r1 == r2:
            continue
        for t, k, r, o in ((t1, k1, r1, r2), (t2, k2, r2, r1)):
            u, v = T[t][k], T[t][(k + 1) % 3]
            out[r].setdefault(int(u), []).append((int(v), int(o)))
    loops = {}
    for r, nxt in out.items():
        ls = []
        used = set()
        for u0 in list(nxt):
            for v0, o0 in nxt[u0]:
                if (u0, v0) in used:
                    continue
                lp = []
                u, v, o = u0, v0, o0
                while (u, v) not in used:
                    used.add((u, v))
                    lp.append((u, v, o))
                    cands = [(w, oo) for w, oo in nxt.get(v, []) if (v, w) not in used]
                    if not cands:
                        break
                    u, (v, o) = v, cands[0]
                ls.append(lp)
        loops[r] = ls
    return loops


def build(V, T, reg, surf, tol):
    """Solid from the regions."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeSegment
    from OCP.GeomAPI import GeomAPI_IntSS, GeomAPI_ProjectPointOnCurve
    from OCP.ShapeFix import ShapeFix_Shell, ShapeFix_Solid, ShapeFix_Shape
    from OCP.TopoDS import TopoDS_Shell, TopoDS_Vertex, TopoDS
    from OCP.TopAbs import TopAbs_FACE
    from OCP.gp import gp_Pnt
    from build123d import Shape
    loops = _loops(T, reg)
    geo = [_geom_surface(s) for s in surf]
    for i, s in enumerate(surf):
        if s["kind"] == "torus":
            # a torus is periodic around the tube too, with its seam on the outer equator, where a fillet usually
            # starts: the face is made on the torus trimmed to the tube angles of its triangles (no seam)
            geo[i] = _torus_trimmed(geo[i], s, V[np.unique(T[s["tris"]])])
    B = BRep_Builder()
    # corners: vertices with three or more regions, or more than two region boundary edges
    vreg = defaultdict(set)
    for t, (a, b, c) in enumerate(T.tolist()):
        for v in (a, b, c):
            vreg[v].add(int(reg[t]))
    bdeg = defaultdict(int)
    for r, ls in loops.items():
        for lp in ls:
            for u, v, o in lp:
                bdeg[u] += 1
    corner = {v for v, rs in vreg.items() if len(rs) >= 3} | {v for v, d in bdeg.items() if d > 2}
    verts = {}

    vtol = max(1e-6 * float(np.ptp(V, axis=0).max()), 1e-7)    # raised where a fitted curve ends further away

    def vert(i):
        if i not in verts:
            vx = TopoDS_Vertex()
            B.MakeVertex(vx, gp_Pnt(*[float(x) for x in V[i]]), vtol)
            verts[i] = vx
        return verts[i]

    edges = {}                                    # chain key (vertex tuple) -> list of TopoDS edges
    nfit = {"line": 0, "curve": 0, "segments": 0}

    def chain_edges(ch, ra, rb):
        key = tuple(ch)
        if key in edges:
            return edges[key], False
        rk = tuple(reversed(ch))
        if rk in edges:
            return edges[rk], True
        pts = V[list(ch)]
        closed = ch[0] == ch[-1]
        made = None
        sa, sb = surf[ra], surf[rb]
        same = sa.get("sid") is not None and sa.get("sid") == sb.get("sid")
        if (same or (sa["kind"] == "plane" and sb["kind"] == "plane")) and not closed:
            d = pts[-1] - pts[0]
            L = np.linalg.norm(d)
            if L > 0 and np.linalg.norm(np.cross(pts - pts[0], d / L), axis=1).max() <= tol:
                seg = GC_MakeSegment(gp_Pnt(*pts[0]), gp_Pnt(*pts[-1])).Value()
                made = [_mk_edge(seg, vert(ch[0]), vert(ch[-1]))]
                nfit["line"] += 1
            elif same and len(ch) >= 3:
                # boundary between the two halves of one surface: the straight line between its ends when that
                # lies on the surface within tol (a generator line), else a curve on the surface through the points
                q = pts[0] + np.outer(np.linspace(0, 1, 9), pts[-1] - pts[0])
                if _surf_dev(geo[ra], q) <= tol:
                    seg = GC_MakeSegment(gp_Pnt(*pts[0]), gp_Pnt(*pts[-1])).Value()
                    made = [_mk_edge(seg, vert(ch[0]), vert(ch[-1]))]
                else:
                    made = _curve_on_surface(geo[ra], pts, vert(ch[0]), vert(ch[-1]))
                if made is not None:
                    nfit["curve"] += 1
        elif not same and (sa["kind"] != "plane" or sb["kind"] != "plane"):
            try:
                inter = GeomAPI_IntSS(geo[ra], geo[rb], 1e-7)
                if inter.IsDone():
                    for i in range(1, inter.NbLines() + 1):
                        cu = inter.Line(i)
                        # a trimmed circle or ellipse: its whole periodic curve (the chain can run past the trim)
                        if cu.DynamicType().Name() == "Geom_TrimmedCurve" and cu.BasisCurve().IsPeriodic():
                            cu = cu.BasisCurve()
                        dev, par = 0.0, []
                        for p in pts:
                            pr = GeomAPI_ProjectPointOnCurve(gp_Pnt(*p), cu)
                            if not pr.NbPoints():
                                dev = 1e30
                                break
                            dev = max(dev, pr.LowerDistance())
                            par.append(pr.LowerDistanceParameter())
                        if dev > tol:
                            continue
                        made = _trimmed_edge(cu, par, closed, vert(ch[0]), vert(ch[-1]))
                        if made is not None:
                            nfit["curve"] += 1
                            break
            except Exception:
                made = None
        if made is None and (sa["kind"] != "plane" or sb["kind"] != "plane"):
            made = _fallback_chain(pts, closed, geo[ra], geo[rb], tol, vert(ch[0]), vert(ch[-1]))
            if made is not None:
                nfit["curve"] += 1
        if made is None:
            if surf[ra]["kind"] != "plane" or surf[rb]["kind"] != "plane":
                raise _Demote({ra, rb} - {i for i in (ra, rb) if surf[i]["kind"] == "plane"})
            made = []
            for i in range(len(ch) - 1):
                seg = GC_MakeSegment(gp_Pnt(*V[ch[i]]), gp_Pnt(*V[ch[i + 1]])).Value()
                made.append(_mk_edge(seg, vert(ch[i]), vert(ch[i + 1])))
            nfit["segments"] += 1
        edges[key] = made
        return made, False

    # pass 1: the edges of every chain; the fitted regions whose edges cannot be made are collected
    demote = set()
    region_wires = {}
    for r, ls in loops.items():
        wl = []
        for lp in ls:
            # split the loop into chains at corners and where the neighbouring region changes
            n = len(lp)
            cut = [i for i in range(n) if lp[i][0] in corner or lp[i][2] != lp[i - 1][2]]
            if not cut:
                # a closed loop along one neighbour: one closed chain from its smallest vertex
                k = min(range(n), key=lambda i: lp[i][0])
                lp = lp[k:] + lp[:k]
                cut = [0]
                corner.add(lp[0][0])
            wl_e = []
            for j, i0 in enumerate(cut):
                i1 = cut[(j + 1) % len(cut)]
                seq = [lp[(i0 + q) % n] for q in range(((i1 - i0) % n) or n)]
                ch = [seq[0][0]] + [s[1] for s in seq]
                try:
                    es, rev = chain_edges(ch, r, seq[0][2])
                except _Demote as d:
                    demote |= d.regs
                    continue
                wl_e.extend(TopoDS.Edge(e.Reversed()) if rev else e for e in (reversed(es) if rev else es))
            wl.append(wl_e)
        region_wires[r] = wl
    if demote:
        raise _Demote(demote)
    # pass 2: faces
    shell = TopoDS_Shell()
    B.MakeShell(shell)
    for r, wl in region_wires.items():
        wires = []
        for es in wl:
            mw = BRepBuilderAPI_MakeWire()
            for e in es:
                mw.Add(e)
            if not mw.IsDone():
                raise ValueError("a boundary loop of region %d could not be closed" % r)
            wires.append(mw.Wire())
        g = geo[r]
        face = _make_face(g, wires, True)
        if surf[r]["kind"] != "plane":
            # a face on a closed surface bounded by its loops can be either side: it must hold the triangles and
            # have their area (on a torus both sides can hold a point when the parameters wrap)
            tr = surf[r]["tris"]
            ta = area_of(V, T, tr)
            t0 = tr[int(np.argmax(ta))]
            tarea = float(ta.sum())
            cands = [f for f in (face, _make_face(g, [TopoDS.Wire(w.Reversed()) for w in wires], False))
                     if _face_holds(f, g, V[T[t0]].mean(0))]
            cands = [(abs(_face_area(f) - tarea), f) for f in cands]
            cands = [c for c in cands if c[0] <= 0.25 * tarea]
            if not cands:
                demote.add(r)
                continue
            face = min(cands, key=lambda c: c[0])[1]
        B.Add(shell, face)
    if demote:
        raise _Demote(demote)
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SHELL
    fs = ShapeFix_Shell(shell)
    fs.Perform()
    sh = fs.Shell()
    if fs.NbShells() != 1 and any(x["kind"] != "plane" for x in surf):
        # fitted faces that do not form one shell: made of flat facets instead (sewing curved faces can take long)
        raise ValueError("the fitted faces do not close one shell (%d shells)" % fs.NbShells())
    if fs.NbShells() != 1:
        # faces whose shared edges were copied by the face fixes: sewn again (the edges coincide)
        sew = BRepBuilderAPI_Sewing(max(tol, 1e-6))
        ex = TopExp_Explorer(shell, TopAbs_FACE)
        while ex.More():
            sew.Add(ex.Current())
            ex.Next()
        sew.Perform()
        ex = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
        shells = []
        while ex.More():
            shells.append(ex.Current())
            ex.Next()
        if len(shells) != 1:
            raise ValueError("the faces from the STL do not close one shell (%d shells)" % len(shells))
        fs = ShapeFix_Shell(TopoDS.Shell(shells[0]))
        fs.Perform()
        sh = fs.Shell()
    so = ShapeFix_Solid(BRepBuilderAPI_MakeSolid(TopoDS.Shell(sh)).Solid())
    so.Perform()
    fx = ShapeFix_Shape(so.Solid())
    fx.SetPrecision(max(tol * 0.1, 1e-7))
    fx.SetMaxTolerance(max(tol, 1e-7))
    fx.Perform()
    out = fx.Shape()
    # edge and vertex tolerances to the real deviation of the fitted curves from their faces
    from OCP.BRepLib import BRepLib
    BRepLib.SameParameter_s(out, max(tol, 1e-7), True)
    BRepLib.UpdateTolerances_s(out, False)
    return Shape.cast(out), nfit


class _Demote(Exception):
    def __init__(self, regs):
        super().__init__("demote")
        self.regs = regs


def _torus_trimmed(g, s, X):
    from OCP.Geom import Geom_RectangularTrimmedSurface
    o, a, R = s["o"], s["a"], s["R"]
    w = X - o
    h = w @ a
    rho = np.linalg.norm(w - np.outer(h, a), axis=1)
    v = np.sort(np.mod(np.arctan2(h, rho - R), 2 * math.pi))
    gaps = np.diff(np.r_[v, v[0] + 2 * math.pi])
    k = int(np.argmax(gaps))
    v0 = v[(k + 1) % len(v)]
    v1 = v[k] if k + 1 < len(v) else v[k]
    if v1 <= v0:
        v1 += 2 * math.pi
    span = v1 - v0
    m = min(0.2, max(0.0, (2 * math.pi - span) / 3))
    if span + 2 * m >= 2 * math.pi - 1e-6:
        return g                                  # all round the tube
    return Geom_RectangularTrimmedSurface(g, float(v0 - m), float(v1 + m), False)


def _surf_dev(g, pts):
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt
    d = 0.0
    for p in pts:
        pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*[float(x) for x in p]), g)
        if not pr.NbPoints():
            return 1e30
        d = max(d, pr.LowerDistance())
    return d


def _fallback_chain(pts, closed, ga, gb, tol, v0, v1):
    """Edge of a chain between two surfaces where their intersection was not found (tangent surfaces, a fitted
    surface slightly off): a straight line, a circle through the chain points, or a curve on one surface through
    them; each must lie within tol of both surfaces. None when nothing fits."""
    from OCP.GC import GC_MakeSegment
    from OCP.Geom import Geom_Circle
    from OCP.GeomAPI import GeomAPI_ProjectPointOnCurve
    from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir
    if _surf_dev(ga, pts) > tol or _surf_dev(gb, pts) > tol:
        return None
    if not closed:
        d = pts[-1] - pts[0]
        L = np.linalg.norm(d)
        if L > 0 and np.linalg.norm(np.cross(pts - pts[0], d / L), axis=1).max() <= tol:
            seg = GC_MakeSegment(gp_Pnt(*pts[0]), gp_Pnt(*pts[-1])).Value()
            return [_mk_edge(seg, v0, v1)]
    if len(pts) >= 4:
        pl, dev = fit_plane(pts)
        if dev <= tol:
            n = pl["n"]
            e1 = np.cross(n, [1.0, 0, 0] if abs(n[0]) < 0.9 else [0, 1.0, 0])
            e1 /= np.linalg.norm(e1)
            e2 = np.cross(n, e1)
            c2, r = _circle2(np.c_[(pts - pl["p"]) @ e1, (pts - pl["p"]) @ e2])
            c = pl["p"] + c2[0] * e1 + c2[1] * e2
            if r > 0 and np.abs(np.linalg.norm(pts - c, axis=1) - r).max() <= tol:
                circ = Geom_Circle(gp_Ax2(gp_Pnt(*c), gp_Dir(*n), gp_Dir(*e1)), r)
                par = [GeomAPI_ProjectPointOnCurve(gp_Pnt(*p), circ).LowerDistanceParameter() for p in pts]
                made = _trimmed_edge(circ, par, closed, v0, v1)
                if made is not None:
                    return made
    if not closed:
        for g in (ga, gb):
            made = _curve_on_surface(g, pts, v0, v1)
            if made is not None:
                return made
    return None


def area_of(V, T, tris):
    t = T[tris]
    return 0.5 * np.linalg.norm(np.cross(V[t[:, 1]] - V[t[:, 0]], V[t[:, 2]] - V[t[:, 0]]), axis=1)


def _make_face(g, wires, fix_orientation):
    """Face on the surface g bounded by the wires (pcurves, seam and, optionally, wire orientation fixed)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.ShapeFix import ShapeFix_Face
    mf = BRepBuilderAPI_MakeFace(g, wires[0], True)
    for w in wires[1:]:
        mf.Add(w)
    sf = ShapeFix_Face(mf.Face())
    sf.FixOrientationMode = 1 if fix_orientation else 0
    sf.FixMissingSeamMode = 1
    sf.Perform()
    return sf.Face()


def _face_area(face):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    gp = GProp_GProps()
    try:
        BRepGProp.SurfaceProperties_s(face, gp)
        return abs(gp.Mass())
    except Exception:  # noqa: BLE001
        return float("inf")


def _face_holds(face, g, p):
    """True when the point p projected onto the surface g lies inside the face."""
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    from OCP.gp import gp_Pnt, gp_Pnt2d
    pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*[float(x) for x in p]), g)
    if not pr.NbPoints():
        return True
    u, v = pr.LowerDistanceParameters()
    us = [u + k * g.UPeriod() for k in (-1, 0, 1)] if g.IsUPeriodic() else [u]
    vs = [v + k * g.VPeriod() for k in (-1, 0, 1)] if g.IsVPeriodic() else [v]
    return any(BRepClass_FaceClassifier(face, gp_Pnt2d(a, b), 1e-7).State() in (TopAbs_IN, TopAbs_ON)
               for a in us for b in vs)


def _curve_on_surface(g, pts, v0, v1):
    """Edge through the points projected onto the surface g (cubic interpolation), or None."""
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf, GeomAPI_Interpolate
    from OCP.gp import gp_Pnt
    try:
        from OCP.TColgp import TColgp_HArray1OfPnt as HArr
    except ImportError:
        from OCP.collections import HArray1_gp_Pnt as HArr
    q = []
    for p in pts:
        pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*[float(x) for x in p]), g)
        if not pr.NbPoints():
            return None
        q.append(pr.NearestPoint())
    arr = HArr(1, len(q))
    for i, x in enumerate(q):
        arr.SetValue(i + 1, x)
    try:
        it = GeomAPI_Interpolate(arr, False, 1e-7)
        it.Perform()
        if not it.IsDone():
            return None
        e = _mk_edge(it.Curve(), v0, v1)
        return [e] if e is not None else None
    except Exception:
        return None


def _mk_edge(cu, v0, v1, t0=None, t1=None):
    """Edge on the curve between the vertices; a vertex tolerance is raised to the distance of the curve end."""
    from OCP.BRep import BRep_Tool, BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    if t0 is None:
        t0, t1 = cu.FirstParameter(), cu.LastParameter()
    B = BRep_Builder()
    for v, t in ((v0, t0), (v1, t1)):
        d = BRep_Tool.Pnt_s(v).Distance(cu.Value(t))
        if d > BRep_Tool.Tolerance_s(v):
            B.UpdateVertex(v, d * 1.05 + 1e-9)
    mk = BRepBuilderAPI_MakeEdge(cu, v0, v1, t0, t1)
    return mk.Edge() if mk.IsDone() else None


def _trimmed_edge(cu, par, closed, v0, v1):
    """Edge on the curve from the first to the last chain point, in the direction of the chain (the parameters of
    the chain points par)."""
    t0, t1 = par[0], par[-1]
    per = cu.IsPeriodic()
    P = cu.Period() if per else 0.0
    if per:
        # unwrap the parameters along the chain
        u = [par[0]]
        for t in par[1:]:
            d = (t - u[-1] + P / 2) % P - P / 2
            u.append(u[-1] + d)
        if closed:
            u[-1] = u[0] + (P if u[-1] - u[0] > 0 else -P) if abs(u[-1] - u[0]) < 1e-9 else u[-1]
        t0, t1 = u[0], u[-1]
    if t1 < t0:
        cu = cu.Reversed()
        tr = lambda t: cu.ReversedParameter(t)
        t0, t1 = tr(t0), tr(t1)
    if abs(t1 - t0) < 1e-12:
        return None
    e = _mk_edge(cu, v0, v1, t0, t1)
    return [e] if e is not None else None


# --------------------------------------------------------------------------- import

def stl_solid(path, opts=None):
    """(solid, report) of an STL file; cached per path, modification time, size and options."""
    opts = dict(opts or {})
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime, st.st_size, tuple(sorted(opts.items())))
    if key in _CACHE:
        return _CACHE[key]
    tris = read_stl(path)
    size = float(np.ptp(tris.reshape(-1, 3), axis=0).max())
    V, T = weld(tris, max(size * 1e-7, 1e-9))
    T, vol = orient(V, T)
    tol = float(opts.get("tolerance") or 0) or max(1e-3 * size, 1e-4)
    ang = float(opts.get("angle") or 0.5)
    smooth = float(opts.get("smooth") or 30)
    fit = bool(opts.get("fit", True))
    rep = {"triangles": int(len(T)), "mesh_volume": round(vol, 6), "tolerance": tol, "fit": fit}
    # flat faces made without fitted surfaces: coplanar triangles merged within a tight tolerance, so that the
    # faces stay planar and the solid valid
    ftol = min(tol, max(1e-5 * size, 1e-7))
    t_fit = time.time()
    reg, surf, area, N = regions(V, T, tol if fit else ftol, ang, smooth, fit)
    if len(surf) > MAX_FACES:
        raise ValueError("the mesh gives %d faces (limit %d): curved areas stay as flat facets; reduce the number of "
                         "triangles of the STL, or raise the tolerance or the flat face angle" % (len(surf), MAX_FACES))
    shape = None
    err = None
    for attempt in range(8):
        try:
            shape, nfit = build(V, T, reg, surf, tol)
            if len(shape.solids()) == 1 and abs(abs(shape.solids()[0].volume) - vol) <= 0.02 * vol:
                break
            raise ValueError("the faces from the STL give no closed solid of the mesh volume")
        except _Demote as d:
            # fitted regions whose edges cannot be made: back to their flat facets
            regs = d.regs
            if time.time() - t_fit > FIT_BUDGET_S:
                rep["fallback"] = True
                reg, surf, area, N = regions(V, T, ftol, ang, smooth, False)
            else:
                reg, surf = _demote(V, T, reg, surf, regs, tol, ang)
        except ValueError as e:
            # the fitted faces do not join: spheres and tori first, then every fitted surface back to flat facets
            # (at once after the time for fitting)
            err, shape = e, None
            sph = {i for i, sf in enumerate(surf) if sf["kind"] in ("sphere", "torus")}
            allfit = {i for i, sf in enumerate(surf) if sf["kind"] != "plane"}
            fitted = allfit if time.time() - t_fit > FIT_BUDGET_S else (sph or allfit)
            if not fitted:
                break
            if fitted == allfit:
                # every fitted surface back to flat: the flat faces of the mesh (coplanar triangles merged)
                rep["fallback"] = True
                reg, surf, area, N = regions(V, T, ftol, ang, smooth, False)
            else:
                reg, surf = _demote(V, T, reg, surf, fitted, tol, ang)
            if len(surf) > MAX_FACES:
                raise ValueError("the fitted faces do not join, and without fitting the mesh gives %d faces "
                                 "(limit %d)" % (len(surf), MAX_FACES))
    if shape is None:
        raise err or ValueError("the STL could not be converted to a solid")
    kinds = defaultdict(int)
    for s in surf:
        kinds[s["kind"]] += 1
    sols = shape.solids()
    if len(sols) != 1:
        raise ValueError("the STL gave %d solids" % len(sols))
    so = sols[0]
    rep.update(faces=len(so.faces()), kinds=dict(kinds), volume=round(abs(so.volume), 6), valid=bool(so.is_valid))
    if abs(abs(so.volume) - vol) > 0.02 * vol:
        raise ValueError("the solid from the STL has volume %.6g mm^3, the mesh %.6g mm^3" % (abs(so.volume), vol))
    _CACHE[key] = (so, rep)
    return so, rep


def _demote(V, T, reg, surf, regs, tol, ang):
    """The regions regs (with the other halves of their surfaces) split back into flat triangles."""
    sids = {surf[i].get("sid") for i in regs} - {None}
    regs = set(regs) | {i for i, s in enumerate(surf) if s.get("sid") in sids}
    newsurf, newreg = [], -np.ones(len(T), int)
    for i, s in enumerate(surf):
        if i in regs:
            continue
        for t in s["tris"]:
            newreg[t] = len(newsurf)
        newsurf.append(s)
    for i in regs:
        for t in surf[i]["tris"]:
            pl, _ = fit_plane(V[T[t]])
            n = np.cross(V[T[t][1]] - V[T[t][0]], V[T[t][2]] - V[T[t][0]])
            if pl["n"] @ n < 0:
                pl["n"] = -pl["n"]
            newreg[t] = len(newsurf)
            newsurf.append(dict(pl, tris=[t]))
    return newreg, newsurf


def report_note(rep):
    k = rep.get("kinds", {})
    names = [("plane", "planar"), ("cylinder", "cylindrical"), ("cone", "conical"), ("sphere", "spherical"), ("torus", "toroidal")]
    parts = ", ".join("%d %s" % (k[a], b) for a, b in names if k.get(a))
    return ("STL: %d triangles -> %d faces (%s); volume %.6g mm^3 (mesh %.6g mm^3); tolerance %.4g mm"
            % (rep["triangles"], rep["faces"], parts, rep["volume"], rep["mesh_volume"], rep["tolerance"])
            + ("; the fitted faces did not join: flat facets" if rep.get("fallback") else ""))


# --------------------------------------------------------------------------- rough mesh (surface body)

_ROUGH = {}


def cluster(V, T, max_tris):
    """Vertex clustering: the vertices in each cell of a grid are merged into their mean, triangles that collapse
    are dropped; the cell size is the smallest of a series that gives at most max_tris triangles."""
    size = float(np.ptp(V, axis=0).max())
    lo = V.min(0)
    best = (V, T)
    for k in range(40):
        h = size / 400.0 / (0.8 ** k)          # cells from 1/400 of the size, 25 % larger each step
        cell = np.floor((V - lo) / h).astype(np.int64)
        keys, inv = np.unique(cell, axis=0, return_inverse=True)
        inv = inv.reshape(-1)
        cnt = np.bincount(inv, minlength=len(keys)).astype(float)
        NV = np.stack([np.bincount(inv, weights=V[:, d], minlength=len(keys)) for d in range(3)], axis=1) / cnt[:, None]
        NT = inv[T]
        ok = (NT[:, 0] != NT[:, 1]) & (NT[:, 1] != NT[:, 2]) & (NT[:, 0] != NT[:, 2])
        NT = NT[ok]
        srt = np.sort(NT, axis=1)
        _, first = np.unique(srt, axis=0, return_index=True)
        NT = NT[np.sort(first)]
        best = (NV, NT)
        if len(NT) <= max_tris:
            break
    NV, NT = best
    used = np.unique(NT)
    remap = -np.ones(len(NV), np.int64)
    remap[used] = np.arange(len(used))
    return NV[used], remap[NT]


def mesh_shape(V, T):
    """Faces of the triangles with shared vertices and edges (a shell when the mesh is connected), as a build123d
    Shape. Triangles of zero area are left out."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.Geom import Geom_Plane
    from OCP.TopoDS import TopoDS_Vertex, TopoDS_Wire, TopoDS_Face, TopoDS_Compound, TopoDS
    from OCP.gp import gp_Pnt, gp_Dir
    from build123d import Shape
    B = BRep_Builder()
    tolv = max(1e-7, 1e-6 * float(np.ptp(V, axis=0).max()))
    verts = []
    for p in V:
        vx = TopoDS_Vertex()
        B.MakeVertex(vx, gp_Pnt(float(p[0]), float(p[1]), float(p[2])), tolv)
        verts.append(vx)
    edges = {}

    def edge(a, b):
        k = (a, b) if a < b else (b, a)
        e = edges.get(k)
        if e is None:
            e = BRepBuilderAPI_MakeEdge(verts[k[0]], verts[k[1]]).Edge()
            edges[k] = e
        return e if a < b else TopoDS.Edge(e.Reversed())

    comp = TopoDS_Compound()
    B.MakeCompound(comp)
    P0, P1, P2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    cr = np.cross(P1 - P0, P2 - P0)
    nrm = np.linalg.norm(cr, axis=1)
    n = 0
    for t in range(len(T)):
        if nrm[t] <= 1e-12:
            continue
        a, b, c = (int(x) for x in T[t])
        w = TopoDS_Wire()
        B.MakeWire(w)
        for u, v in ((a, b), (b, c), (c, a)):
            B.Add(w, edge(u, v))
        nd = cr[t] / nrm[t]
        pl = Geom_Plane(gp_Pnt(*[float(x) for x in V[a]]), gp_Dir(*[float(x) for x in nd]))
        fc = TopoDS_Face()
        B.MakeFace(fc, pl, tolv)
        B.Add(fc, w)
        B.Add(comp, fc)
        n += 1
    return Shape.cast(comp), n


def rough_mesh(path, max_tris=20000):
    """(shape, report) of an STL file as a rough mesh body: the triangles (reduced by vertex clustering to at most
    max_tris) as planar faces, without fitted surfaces. Cached per path, modification time, size and max_tris."""
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime, st.st_size, int(max_tris))
    if key in _ROUGH:
        return _ROUGH[key]
    t0 = time.time()
    tris = read_stl(path)
    size = float(np.ptp(tris.reshape(-1, 3), axis=0).max())
    V, T = weld(tris, max(size * 1e-7, 1e-9))
    n0 = len(T)
    if max_tris and len(T) > max_tris:
        V, T = cluster(V, T, int(max_tris))
    shape, n = mesh_shape(V, T)
    shape._mesh = True
    bb = np.ptp(V, axis=0)
    rep = {"triangles": int(n0), "faces": int(n), "size": [round(float(x), 3) for x in bb], "seconds": round(time.time() - t0, 1)}
    _ROUGH[key] = (shape, rep)
    while len(_ROUGH) > 4:
        _ROUGH.pop(next(iter(_ROUGH)))
    return shape, rep
