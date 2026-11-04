# -*- coding: utf-8 -*-
"""Reference point couplings, springs, joints and equations of the Analysis (CalculiX) and Explicit (Radioss) models.

Document entries (analysis and explicit documents):
  "points":    [{"id", "name", "xyz": [x, y, z] mm, "place": {...} (placement of the panel, not used here),
                 "coupling": "rigid" | "kinematic" | "distributing" | "none" (default rigid),
                 "dofs": [ux, uy, uz, rx, ry, rz] (1 = coupled; kinematic and distributing),
                 "faces": [face references], "edges": [edge references], "nsets": [node set ids]}]
  "springs":   [{"id", "name", "a": end, "b": end | null (to ground), "k": [kx, ky, kz] N/mm + [krx, kry, krz] N mm/rad}]
  "joints":    [{"id", "name", "type": "ball" | "hinge" | "weld" | "dofs", "a": end, "b": end,
                 "axis": [x, y, z] (hinge), "dofs": [6 flags] (dofs)}]
  "equations": [{"id", "name", "terms": [{"end": end, "dof": 1..6, "coef"}]}]   sum coef * u = 0
  end: {"point": reference point id} | {"at": [x, y, z]} (the mesh node nearest to the point)

Kinematic coupling (RBE2): for each coupled node and each coupled translation d, u_d = u_d(RP) + (theta(RP) x r)_d;
coupled rotations of nodes with rotations (beam nodes) equal the RP rotations. Rigid: CalculiX *RIGID BODY (Radioss
/RBODY). Distributing (RBE3): the coupled RP components are the weighted mean motion of the nodes (face nodes weighted
by their tributary area, edge and node set nodes 1). Joints: ball (ux uy uz equal), weld (all six equal), hinge (ux uy
uz equal, rotations about the two axes normal to the hinge axis equal), dofs (the chosen components equal), all as
linear equations. The RP rotations are the translations of its rotation node (CalculiX ROT NODE).
"""
import numpy as np

DOF_NAMES = ["ux", "uy", "uz", "rx", "ry", "rz"]


class ConstraintError(Exception):
    pass


def _flags(v, default=(1, 1, 1, 1, 1, 1)):
    f = list(v) if isinstance(v, (list, tuple)) else list(default)
    return [1 if x else 0 for x in (f + [0] * 6)[:6]]


def coupling_of(p):
    c = p.get("coupling") or "rigid"
    if c == "kinematic" and all(_flags(p.get("dofs"))):
        return "rigid"
    return c


def target_nodes(M, p):
    """Nodes and weights of the faces, edges and node sets of a reference point: ({node: weight}, faces)."""
    w = {}
    name = p.get("name") or p.get("id")
    for fr in p.get("faces") or []:
        f = M.face(fr)
        for n in f["nodes"]:
            w[n] = w.get(n, 0.0) + float(f["w"].get(n, 0.0) or 0.0)
    for er in p.get("edges") or []:
        for n in M.edge(er)["nodes"]:
            w[n] = w.get(n, 0.0) + 1.0
    for nid in p.get("nsets") or []:
        ns = next((x for x in M.doc.get("nsets") or [] if str(x.get("id")) == str(nid)), None)
        if ns is None:
            raise ConstraintError("reference point %s: node set %s not found" % (name, nid))
        for n in M.node_set(ns):
            w[n] = w.get(n, 0.0) + 1.0
    for n in list(w):
        if w[n] <= 0:
            w[n] = 1.0
    return w


def nearest_node(M, xyz, exclude=()):
    p = np.asarray(xyz, float)
    best, bd = None, None
    for n, x in M.X.items():
        if n in exclude:
            continue
        d = float(np.linalg.norm(x - p))
        if bd is None or d < bd:
            best, bd = n, d
    if best is None:
        raise ConstraintError("no mesh node")
    return best, bd


def rp_nodes(M):
    return set(n for rp in M.rps.values() for n in (rp["ref"], rp["rot"]))


def resolve_end(M, end, what):
    """{"point"} -> ("rp", ref, rot); {"at"} -> ("node", node, None)."""
    end = end or {}
    if end.get("point") is not None:
        rp = M.rps.get(str(end["point"]))
        if rp is None:
            raise ConstraintError("%s: reference point %s not found" % (what, end["point"]))
        return ("rp", rp["ref"], rp["rot"])
    if end.get("at") is not None:
        n, d = nearest_node(M, end["at"], rp_nodes(M))
        if d > max(1e-3 * M.diag, 1e-6):
            M.warnings.append("%s: the nearest mesh node is %.4g mm from the point" % (what, d))
        return ("node", n, None)
    raise ConstraintError("%s: pick the point" % what)


def end_dof(M, e, d):
    """(node, dof) of component d (1..6) of a resolved end, or None (no rotations at the node)."""
    kind, n, rot = e
    if d <= 3:
        return (n, d)
    if kind == "rp":
        M.rot_used.add(rot)
        return (rot, d - 3)
    if n in M.rot_nodes:
        return (n, d)
    return None


def add_eq_auto(M, terms, what):
    """Equation sum coef * u = 0; the dependent term: the largest coefficient of a DOF not yet dependent or held."""
    terms = [(int(n), int(d), float(c)) for n, d, c in terms if abs(c) > 1e-14]
    if len(terms) < 2:
        raise ConstraintError("%s: an equation needs two terms" % what)
    free = [i for i, (n, d, c) in enumerate(terms) if (n, d) not in M.dependent and d not in M.spc.get(n, ())]
    if not free:
        raise ConstraintError("%s: all its degrees of freedom are already constrained" % what)
    i = max(free, key=lambda k: abs(terms[k][2]))
    M.add_eq([terms[i]] + terms[:i] + terms[i + 1:])


def kinematic(M, rp, w, dofs, what):
    """RBE2 equations of the nodes w on the reference point rp for the coupled components dofs."""
    ref, rot = rp["ref"], rp["rot"]
    c = M.X[ref]
    M.rot_used.add(rot)
    ids = sorted(n for n in w if n not in (ref, rot))
    left = [n for n in ids if M.spc.get(n) or any((n, d) in M.dependent for d in (1, 2, 3))]
    ids = [n for n in ids if n not in left]
    if left:
        M.warnings.append("%s: %d supported or constrained node(s) left out of the coupling" % (what, len(left)))
    if not ids:
        raise ConstraintError("%s: no free nodes to couple" % what)
    for n in ids:
        r = M.X[n] - c
        for d in range(3):
            if not dofs[d]:
                continue
            # u_n = u_ref + theta x r
            th = [(rot, 2, r[2]), (rot, 3, -r[1])] if d == 0 else [(rot, 3, r[0]), (rot, 1, -r[2])] if d == 1 else [(rot, 1, r[1]), (rot, 2, -r[0])]   # (theta x r)_d
            M.add_eq([(n, d + 1, 1.0), (ref, d + 1, -1.0)] + [(a, b, -float(v)) for a, b, v in th if abs(v) > 1e-14])
        if n in M.rot_nodes:
            for d in range(3):
                if dofs[d + 3]:
                    M.add_eq([(n, d + 4, 1.0), (rot, d + 1, -1.0)])
    return ids


def distributing(M, rp, w, dofs, what):
    """RBE3 equations: the coupled components of the reference point = weighted mean motion of the nodes w."""
    ref, rot = rp["ref"], rp["rot"]
    ids = sorted(n for n in w if n not in (ref, rot) and not M.spc.get(n))
    if len(ids) < (3 if any(dofs[3:]) else 1):
        raise ConstraintError("%s: too few free nodes for a distributing coupling" % what)
    xyz = np.asarray([M.X[n] for n in ids])
    wt = np.asarray([w[n] for n in ids], float)
    wt = wt / wt.sum()
    c = (wt[:, None] * xyz).sum(0)
    r = xyz - c
    Am = np.zeros((3, 3))
    for wi, ri in zip(wt, r):
        Am += wi * (ri @ ri * np.eye(3) - np.outer(ri, ri))
    sk = lambda v: np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    Ainv = np.linalg.pinv(Am)
    T = [Ainv @ (wi * sk(ri)) for wi, ri in zip(wt, r)]
    D = sk(M.X[ref] - c)
    for k in range(3):
        if not dofs[k]:
            continue
        terms = [(ref, k + 1, 1.0)]
        for i, n in enumerate(ids):
            coef = wt[i] * np.eye(3)[k] - (D @ T[i])[k]
            terms += [(n, j + 1, -float(coef[j])) for j in range(3) if abs(coef[j]) > 1e-12]
        M.add_eq(terms)
    for k in range(3):
        if not dofs[k + 3]:
            continue
        M.rot_used.add(rot)
        terms = [(rot, k + 1, 1.0)]
        for i, n in enumerate(ids):
            terms += [(n, j + 1, -float(T[i][k, j])) for j in range(3) if abs(T[i][k, j]) > 1e-12]
        M.add_eq(terms)
    return ids


def springs(M, doc):
    """Springs: one SPRING2 (two ends) or SPRING1 (to ground) element per component with a stiffness."""
    out = []
    for s in doc.get("springs") or []:
        what = "spring %s" % (s.get("name") or s.get("id"))
        k = [float(x or 0) for x in (list(s.get("k") or []) + [0] * 6)[:6]]
        if not any(v > 0 for v in k):
            raise ConstraintError("%s: no stiffness" % what)
        a = resolve_end(M, s.get("a"), what)
        b = resolve_end(M, s.get("b"), what) if s.get("b") else None
        if b and a[1] == b[1]:
            raise ConstraintError("%s: both ends are the same node" % what)
        for d in range(1, 7):
            if k[d - 1] <= 0:
                continue
            na = end_dof(M, a, d)
            nb = end_dof(M, b, d) if b else None
            if na is None or (b and nb is None):
                M.warnings.append("%s: %s left out (no rotations at the node)" % (what, DOF_NAMES[d - 1]))
                continue
            eid = M.new_elem()
            es = "SPR%d_%d" % (len(M.user_springs) + 1, d)
            if b:
                out.append({"elset": es, "type": "SPRING2", "elem": (eid, na[0], nb[0]), "dofs": (na[1], nb[1]), "k": k[d - 1]})
            else:
                out.append({"elset": es, "type": "SPRING1", "elem": (eid, na[0]), "dofs": (na[1],), "k": k[d - 1]})
            M.user_springs.append(out[-1])
        M.spring_vis.append({"id": s.get("id"), "a": a[1], "b": b[1] if b else None})
    return out


def _perp(axis):
    e = np.asarray(axis, float)
    nrm = np.linalg.norm(e)
    if nrm < 1e-12:
        raise ConstraintError("the hinge axis is zero")
    e = e / nrm
    t = np.array([1.0, 0, 0]) if abs(e[0]) < 0.9 else np.array([0, 1.0, 0])
    e1 = np.cross(e, t)
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(e, e1)


def joint_equations(M, j):
    """Linear equations of a joint: [[(end, dof, coef), ...]] with end "a" or "b"."""
    typ = j.get("type") or "ball"
    rows = []
    if typ in ("ball", "hinge", "weld"):
        for d in (1, 2, 3):
            rows.append([("a", d, 1.0), ("b", d, -1.0)])
    if typ == "weld":
        for d in (4, 5, 6):
            rows.append([("a", d, 1.0), ("b", d, -1.0)])
    if typ == "hinge":
        for e in _perp(j.get("axis") or [0, 0, 1]):
            rows.append([("a", 4 + i, float(e[i])) for i in range(3)] + [("b", 4 + i, -float(e[i])) for i in range(3)])
    if typ == "dofs":
        f = _flags(j.get("dofs"), (1, 1, 1, 0, 0, 0))
        for d in range(1, 7):
            if f[d - 1]:
                rows.append([("a", d, 1.0), ("b", d, -1.0)])
    if not rows:
        raise ConstraintError("joint %s: no component" % (j.get("name") or j.get("id")))
    return rows


def joints(M, doc):
    for j in doc.get("joints") or []:
        what = "joint %s" % (j.get("name") or j.get("id"))
        ends = {"a": resolve_end(M, j.get("a"), what), "b": resolve_end(M, j.get("b"), what)}
        if ends["a"][1] == ends["b"][1]:
            raise ConstraintError("%s: both ends are the same node" % what)
        for row in joint_equations(M, j):
            terms = []
            for e, d, c in row:
                nd = end_dof(M, ends[e], d)
                if nd is None:
                    raise ConstraintError("%s: %s needs rotations at end %s (a reference point or a beam end)" % (what, DOF_NAMES[d - 1], e.upper()))
                terms.append((nd[0], nd[1], c))
            add_eq_auto(M, terms, what)
        M.joint_vis.append({"id": j.get("id"), "a": ends["a"][1], "b": ends["b"][1]})


def equations(M, doc):
    for q in doc.get("equations") or []:
        what = "equation %s" % (q.get("name") or q.get("id"))
        terms = []
        for t in q.get("terms") or []:
            d = int(t.get("dof") or 1)
            if not 1 <= d <= 6:
                raise ConstraintError("%s: component %s is not 1 to 6" % (what, d))
            nd = end_dof(M, resolve_end(M, t.get("end"), what), d)
            if nd is None:
                raise ConstraintError("%s: %s needs rotations at the node (a reference point or a beam end)" % (what, DOF_NAMES[d - 1]))
            terms.append((nd[0], nd[1], float(t.get("coef") or 0)))
        add_eq_auto(M, terms, what)
