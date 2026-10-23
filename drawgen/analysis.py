# -*- coding: utf-8 -*-
"""Linear static analysis with CalculiX: solid bodies, plates, beams, rods and fasteners.

Analysis record (JSON, <name>.fea.json):
  {"name", "source": {"type": "assembly" | "part", "name"},
   "materials": {name: {"E": MPa, "nu", "rho": kg/m^3}},
   "default_material": name,
   "mesh": {"size": mm, "size_min": mm, "curvature": elements per 360 deg, "algorithm": "delaunay" | "frontal" | "hxt",
            "optimize": bool, "strategy": "tet" | "hex" | "hexsub", "tet_type": "C3D10" | "C3D4",
            "hex_type": "C3D8I" | "C3D8" | "C3D8R" | "C3D20" | "C3D20R"}      (femesh.py)
   "bonded": true,                          touching solid bodies share nodes; plates are tied to touching bodies
   "bodies": {component id: {"mode": "solid" | "plate" | "off", "material", "size": mm, "layers": n,
                             "strategy": null (mesh default) | "tet" | "hex" | "hexsub"}},
   "members": [member], "plates": [plate], "fasteners": [fastener], "supports": [support], "loads": [load]}

Units: N, mm, MPa, t/mm^3 inside the solver; densities are entered in kg/m^3 and accelerations in mm/s^2.

Face reference: {"comp": component id, "face": index into the faces of the component shape}.
Point: {"xyz": [x, y, z]} (global, mm), optionally {"face": face reference} (member end connected to the face) and
{"r": mm} (only the face nodes within r of the point are connected).

plate:    {"id", "name", "t", "position", "material", "size", "face" | "points", "group"} (plate_solid): a plate layer
          (C3D8I) built from a planar face of a body or from an outline polygon; body id "plate_<id>" in face references.
member:   {"id", "name", "kind": "beam" | "rod", "a": point, "b": point, "section": section, "up": [x, y, z],
           "material", "n": elements, "release": "" | "a" | "b" | "ab", "group": group id}
          A member with a group takes kind, section and material from the group: "groups": [{"id", "name", "kind",
          "section", "material"}]. A member lying on a plate (edge or mid-surface) is tied to the plate.
          beam: U1 elements (CalculiX linear beam, Euler-Bernoulli, shear factor KAPPA); rod: T3D2 elements.
          Local axes: x from a to b; 2 = "up" projected normal to x (section depth h); 1 = 2 x x (section width b).
          release: bending moments released at that end (hinge about the local 1 and 2 axes; torsion connected).
section:  {"shape": "RECT", "b", "h"} | {"shape": "ROUND", "d"} | {"shape": "PIPE", "d", "t"} |
          {"shape": "BOX", "b", "h", "t"} | {"shape": "I", "b", "h", "tf", "tw"} |
          {"shape": "GENERAL", "A", "I11", "I22", "J", "c1", "c2"}
fastener: {"id", "name", "faces": [face A, face B], "d": mm, "material", "preload": N}
          U1 beam (ROUND d) between the centres of the two faces on the axis of the first cylindrical face; both ends
          are connected to their face by RBE3 equations (weighted mean of the face nodes). With a preload the
          fastener is cut at mid-length: step 1 applies the preload force across the cut, step 2 the loads with
          the cut length fixed; the results are the sum of both steps.
point:    {"id", "name", "xyz": [x, y, z], "faces": [face reference]}   reference point ("points"): rigidly connected to
          the faces (*RIGID BODY, REF NODE translations, ROT NODE translations = rotations); member ends at the point
          follow it. Targets {"point": id} for supports (six components) and loads (force, moment).
          A member end connected to a face takes "coupling": "rigid" (face nodes rigid with the end) instead of RBE3.
support:  {"id", "name", "target": face reference | {"member", "end": "a" | "b"} | {"point": id},
           "type": "fixed" | "pinned" | "normal" | "dofs" | "displacement", "dofs": [ux, uy, uz, rx, ry, rz] (1 = held),
           "value": [ux, uy, uz, rx, ry, rz] (displacement: mm, rad) | mm (normal: along the outward normal)}
          face: fixed = ux, uy, uz; normal = displacement normal to a planar face (0, or "value"); dofs = the global
          components held at 0; displacement = the chosen global components prescribed to "value".
          member end and reference point: fixed = all six; pinned = ux, uy, uz; dofs; displacement.
          Rotations (rx, ry, rz) on a face: the face is rigidly coupled to a node at its weighted centre (kinematic
          coupling) that carries the support.
          Prescribed displacements act in the load step (with a fastener preload step they are 0 in the preload step).
load:     {"id", "name", "type": "force" | "moment" | "pressure" | "gravity" | "line",
           "target": face reference | {"member", "end"} | {"member"} , "value": [x, y, z] | p}
          force on a face: total force distributed by area; moment on a face: about the face centre, distributed
          by area (RBE3 distribution); pressure: MPa, positive into the face; line: N/mm on a member (global);
          gravity: acceleration vector (mm/s^2) on all bodies and members.
"""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import time

import numpy as np

KAPPA = 1.0e7       # U1 shear factor: Euler-Bernoulli beam (1e7: equilibrium to 1e-5 and section forces to 6 digits); the U1 torsion output is scaled by it
SPRING_K = 1.0e-6       # stiffness (N/mm) of the preload node to ground (the node needs one element)


ATYPES = ("static", "modal", "buckling")
ATYPE_NAMES = {"static": "Linear static", "modal": "Modal (natural frequencies)", "buckling": "Linear buckling"}
MAX_MODES = 100


class AnalysisError(Exception):
    pass


# --------------------------------------------------------------------------- sections

def section_props(sec):
    """A, Ia (= integral of x1^2 dA, ccx I11), Ib (= integral of x2^2 dA, ccx I22), J (torsion constant), c1, c2
    (extreme fibre distances along the local 1 and 2 axes), round (bending stress from the resultant moment)."""
    s = (sec or {}).get("shape", "ROUND").upper()
    g = lambda k: float(sec.get(k) or 0)
    if s == "RECT":
        b, h = g("b"), g("h")
        if b <= 0 or h <= 0:
            raise AnalysisError("RECT section: b and h must be positive")
        a, c = max(b, h), min(b, h)
        J = a * c ** 3 * (1.0 / 3 - 0.21 * c / a * (1 - c ** 4 / (12 * a ** 4)))
        return dict(A=b * h, Ia=h * b ** 3 / 12, Ib=b * h ** 3 / 12, J=J, c1=b / 2, c2=h / 2, round=False)
    if s == "ROUND":
        d = g("d")
        if d <= 0:
            raise AnalysisError("ROUND section: d must be positive")
        I = math.pi * d ** 4 / 64
        return dict(A=math.pi * d * d / 4, Ia=I, Ib=I, J=2 * I, c1=d / 2, c2=d / 2, round=True)
    if s == "PIPE":
        d, t = g("d"), g("t")
        if d <= 0 or t <= 0 or 2 * t > d:
            raise AnalysisError("PIPE section: d > 2 t > 0 required")
        ro, ri = d / 2, d / 2 - t
        I = math.pi * (ro ** 4 - ri ** 4) / 4
        return dict(A=math.pi * (ro * ro - ri * ri), Ia=I, Ib=I, J=2 * I, c1=ro, c2=ro, round=True)
    if s == "BOX":
        b, h, t = g("b"), g("h"), g("t")
        if b <= 0 or h <= 0 or t <= 0 or 2 * t >= min(b, h):
            raise AnalysisError("BOX section: b, h > 2 t > 0 required")
        bi, hi = b - 2 * t, h - 2 * t
        J = 2 * t * (b - t) ** 2 * (h - t) ** 2 / ((b - t) + (h - t))
        return dict(A=b * h - bi * hi, Ia=(h * b ** 3 - hi * bi ** 3) / 12, Ib=(b * h ** 3 - bi * hi ** 3) / 12, J=J,
                    c1=b / 2, c2=h / 2, round=False)
    if s == "I":
        b, h, tf, tw = g("b"), g("h"), g("tf"), g("tw")
        if min(b, h, tf, tw) <= 0 or 2 * tf >= h or tw >= b:
            raise AnalysisError("I section: h > 2 tf, b > tw, all positive")
        hw = h - 2 * tf
        return dict(A=2 * b * tf + hw * tw, Ia=(2 * tf * b ** 3 + hw * tw ** 3) / 12,
                    Ib=(b * h ** 3 - (b - tw) * hw ** 3) / 12, J=(2 * b * tf ** 3 + (h - tf) * tw ** 3) / 3,
                    c1=b / 2, c2=h / 2, round=False)
    if s == "GENERAL":
        A, Ia, Ib = g("A"), g("I11"), g("I22")
        if min(A, Ia, Ib) <= 0:
            raise AnalysisError("GENERAL section: A, I11 and I22 must be positive")
        return dict(A=A, Ia=Ia, Ib=Ib, J=g("J") or (Ia + Ib), c1=g("c1"), c2=g("c2"), round=False)
    raise AnalysisError("unknown section shape %s" % s)


def section_label(sec):
    s = (sec or {}).get("shape", "ROUND").upper()
    f = lambda k: ("%g" % float(sec.get(k) or 0))
    if s == "RECT":
        return "RECT %s x %s" % (f("b"), f("h"))
    if s == "ROUND":
        return "ROUND d %s" % f("d")
    if s == "PIPE":
        return "PIPE %s x %s" % (f("d"), f("t"))
    if s == "BOX":
        return "BOX %s x %s x %s" % (f("b"), f("h"), f("t"))
    if s == "I":
        return "I %s x %s x %s / %s" % (f("h"), f("b"), f("tw"), f("tf"))
    return "GENERAL A %s" % f("A")


# --------------------------------------------------------------------------- vector helpers

def _unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def member_axes(a, b, up):
    """Local axes of a member: t (a -> b), e1 (section width, ccx 1-direction), e2 (section depth)."""
    t = _unit(np.asarray(b, float) - np.asarray(a, float))
    u = np.asarray(up if up is not None and np.linalg.norm(up) > 0 else [0, 0, 1], float)
    u = _unit(u)
    if abs(float(np.dot(u, t))) > 0.999:
        u = np.array([1.0, 0, 0]) if abs(t[0]) < 0.9 else np.array([0, 1.0, 0])
    e2 = _unit(u - np.dot(u, t) * t)
    e1 = np.cross(e2, t)
    return t, e1, e2


def _point_tri_dist(P, A, B, C):
    """Distances from points P (n, 3) to the nearest of the triangles (A, B, C) (m, 3 each): (n,)."""
    P = np.asarray(P, float)
    best = np.full(len(P), np.inf)
    m = len(A)
    if m == 0 or len(P) == 0:
        return best
    chunk = max(1, 300000 // max(1, len(P)))

    def seg(p, x, y):
        xy = y - x
        tt = np.clip(((p - x) * xy).sum(-1) / np.maximum((xy * xy).sum(-1), 1e-300), 0.0, 1.0)
        return np.linalg.norm(p - (x + xy * tt[..., None]), axis=-1)

    for s in range(0, m, chunk):
        a, b, c = A[s:s + chunk][None], B[s:s + chunk][None], C[s:s + chunk][None]
        p = P[:, None, :]
        e0, e1, e2 = b - a, c - a, p - a
        d00, d01, d11 = (e0 * e0).sum(-1), (e0 * e1).sum(-1), (e1 * e1).sum(-1)
        d20, d21 = (e2 * e0).sum(-1), (e2 * e1).sum(-1)
        den = d00 * d11 - d01 * d01
        den = np.where(np.abs(den) < 1e-300, 1e-300, den)
        v = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
        u = 1 - v - w
        q = a + e0 * v[..., None] + e1 * w[..., None]
        dplane = np.linalg.norm(p - q, axis=-1)
        dedge = np.minimum(np.minimum(seg(p, a, b), seg(p, b, c)), seg(p, c, a))
        d = np.where((u >= 0) & (v >= 0) & (w >= 0), dplane, dedge)
        best = np.minimum(best, d.min(1))
    return best


# --------------------------------------------------------------------------- solver

SOLVERS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "solvers")


def _solvers_ccx():
    """ccx executables in <program>/solvers/ (an unpacked CalculiX package), up to 4 folder levels deep; ccx.exe
    and the shortest names first."""
    found = []
    if not os.path.isdir(SOLVERS_DIR):
        return found
    base = SOLVERS_DIR.rstrip(os.sep).count(os.sep)
    for dp, dn, fn in os.walk(SOLVERS_DIR):
        for f in fn:
            fl = f.lower()
            if fl.startswith("ccx") and (fl.endswith(".exe") if os.name == "nt" else "." not in fl):
                found.append(os.path.join(dp, f))
        if dp.count(os.sep) - base >= 4:
            dn[:] = []
    return sorted(found, key=lambda p: (os.path.basename(p).lower() not in ("ccx.exe", "ccx"), len(os.path.basename(p)), p))


def find_ccx(cfg_path=""):
    """Path of the CalculiX executable: configured path, a CalculiX package in <program>/solvers/, ccx on PATH, or
    the solver of a PrePoMax installation."""
    cands = []
    if cfg_path:
        cands.append(cfg_path)
    cands += _solvers_ccx()
    for n in ("ccx", "ccx.exe", "ccx_static", "ccx_static.exe", "ccx_dynamic", "ccx_dynamic.exe", "ccx_2.21", "ccx_2.22"):
        p = shutil.which(n)
        if p:
            cands.append(p)
    # PrePoMax folders (the zip unpacks to "PrePoMax v<version>"): program folders, user folder, Desktop, Downloads,
    # Documents, root of the system drive; names in reverse order (v3 before v2)
    roots = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "USERPROFILE")]
    if os.environ.get("SystemDrive"):
        roots.append(os.environ["SystemDrive"] + os.sep)
    bases = []
    for r in roots:
        if not r:
            continue
        for par in [r] + [os.path.join(r, sub) for sub in ("Desktop", "Downloads", "Documents")]:
            bases += sorted((b for b in glob.glob(os.path.join(par, "PrePoMax*")) if os.path.isdir(b)), reverse=True)
    for base in bases:
        for dp, dn, fn in os.walk(base):
            for f in fn:
                if f.lower() in ("ccx_static.exe", "ccx_dynamic.exe", "ccx.exe"):
                    cands.append(os.path.join(dp, f))
            if dp.count(os.sep) - base.count(os.sep) > 3:
                dn[:] = []
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


# --------------------------------------------------------------------------- geometry

def geometry(doc, asm, sources):
    """Bodies of the analysis: [{"id", "name", "shape" (placed), "mode", "material", "size", "layers",
    "faces": {index: (A, B, C) triangle corner arrays, global}, "refs": face refs (local)}]."""
    from . import assembly
    out = []
    bcfg = doc.get("bodies") or {}
    for c in asm.get("components") or []:
        cid = str(c.get("id"))
        cfg = bcfg.get(cid) or {}
        mode = cfg.get("mode") or "solid"
        if mode == "off" or c.get("visible") is False and not cfg.get("mode"):
            continue
        src = c.get("source") or {}
        shape, err = sources.load(src)
        if shape is None and src.get("type") == "part" and (err or "").endswith("has no solid"):
            continue                                   # a part with sketches only: geometry for members and plates
        if shape is None:
            raise AnalysisError("component %s: %s" % (c.get("name") or cid, err or "no solid"))
        info = sources.info(src)
        t = assembly.trsf_of(c)
        M = np.array([[t.Value(i, j) for j in (1, 2, 3, 4)] for i in (1, 2, 3)])
        mesh = info["mesh"]
        V = np.asarray(mesh["vertices"], float) @ M[:, :3].T + M[:, 3]
        T = np.asarray(mesh["triangles"], int).reshape(-1, 3)
        fot = np.asarray(mesh["face_of_tri"], int)
        faces = {}
        for fi in np.unique(fot):
            tt = T[fot == fi]
            faces[int(fi)] = (V[tt[:, 0]], V[tt[:, 1]], V[tt[:, 2]])
        bb = mesh.get("bbox") or [0, 0, 0, 1, 1, 1]
        diag = math.sqrt(sum((bb[i + 3] - bb[i]) ** 2 for i in range(3))) or 1.0
        out.append({"id": cid, "name": c.get("name") or cid, "shape": assembly.place(shape, c), "mode": mode,
                    "material": cfg.get("material") or doc.get("default_material"), "size": cfg.get("size"),
                    "layers": cfg.get("layers") or 1, "strategy": cfg.get("strategy"), "faces": faces, "refs": info.get("refs") or [],
                    "tol": max(diag / 2000.0, 0.005), "M": M})
    placed = {}

    def placed_shape(cid):
        if cid not in placed:
            c = next((x for x in asm.get("components") or [] if str(x.get("id")) == cid), None)
            if c is None:
                raise AnalysisError("component %s not found" % cid)
            shape, err = sources.load(c.get("source") or {})
            if shape is None:
                raise AnalysisError("component %s: %s" % (c.get("name") or cid, err or "no solid"))
            placed[cid] = assembly.place(shape, c)
        return placed[cid]
    for b in out:
        placed[b["id"]] = b["shape"]
    for p in resolve_plate_groups(doc):
        out.append(plate_body(p, placed_shape, doc))
    if not out and not (doc.get("members") or []):
        raise AnalysisError("no bodies, plates or members")
    return out


def _mesh_faces(shape):
    """View mesh, face triangles {index: (A, B, C)} and face refs of a shape in global coordinates."""
    from . import assembly
    mesh = assembly.fast_mesh(shape)
    V = np.asarray(mesh["vertices"], float)
    T = np.asarray(mesh["triangles"], int).reshape(-1, 3)
    fot = np.asarray(mesh["face_of_tri"], int)
    faces = {}
    for fi in np.unique(fot):
        tt = T[fot == fi]
        faces[int(fi)] = (V[tt[:, 0]], V[tt[:, 1]], V[tt[:, 2]])
    return mesh, faces, assembly.face_refs(shape)


def plate_solid(p, placed_shape):
    """Solid of a plate item and its unit normal (from the outline towards the positive side).

    plate: {"id", "name", "t" (mm), "position": "mid" | "positive" | "negative", "material", "size",
            "face": face reference (a planar face of a body; positive: the outward side) |
            "points": [[x, y, z], ...] (outline polygon in one plane; positive: right-hand rule of the order)}"""
    from build123d import Face, Pos, Solid, Vector, Wire
    name = p.get("name") or p.get("id")
    t = float(p.get("t") or 0)
    if t <= 0:
        raise AnalysisError("plate %s: thickness must be positive" % name)
    if p.get("face"):
        ref = p["face"]
        shape = placed_shape(str(ref.get("comp")))
        faces = shape.faces()
        fi = int(ref.get("face", -1))
        if not 0 <= fi < len(faces):
            raise AnalysisError("plate %s: face not found" % name)
        base = faces[fi]
        if not str(getattr(base.geom_type, "name", base.geom_type)).upper().endswith("PLANE"):
            raise AnalysisError("plate %s: the face is not planar" % name)
        nv = base.normal_at(base.center())
        n = _unit([nv.X, nv.Y, nv.Z])
    else:
        pts = np.asarray(p.get("points") or [], float)
        if len(pts) < 3:
            raise AnalysisError("plate %s: at least 3 outline points" % name)
        c = pts.mean(0)
        _, sv, vt = np.linalg.svd(pts - c)
        n = vt[2]
        size = float(np.ptp(pts, axis=0).max()) or 1.0
        if np.abs((pts - c) @ n).max() > 1e-6 * size + 1e-6:
            raise AnalysisError("plate %s: the outline points are not in one plane" % name)
        av = sum(np.cross(pts[i] - c, pts[(i + 1) % len(pts)] - c) for i in range(len(pts)))
        if np.linalg.norm(av) < 1e-9 * size * size:
            raise AnalysisError("plate %s: the outline has no area" % name)
        if np.dot(av, n) < 0:
            n = -n
        base = Face(Wire.make_polygon([Vector(*q) for q in pts], close=True))
    off = {"mid": -t / 2, "positive": 0.0, "negative": -t}.get(p.get("position") or ("positive" if p.get("face") else "mid"), -t / 2)
    if off:
        base = Pos(*(n * off)) * base
    sol = Solid.extrude(base, Vector(*(n * t)))
    return sol, n


def plate_body(p, placed_shape, doc):
    sol, n = plate_solid(p, placed_shape)
    mesh, faces, refs = _mesh_faces(sol)
    bb = mesh["bbox"]
    diag = math.sqrt(sum((bb[i + 3] - bb[i]) ** 2 for i in range(3))) or 1.0
    return {"id": "plate_" + str(p.get("id")), "name": p.get("name") or str(p.get("id")), "shape": sol, "mode": "plate",
            "material": p.get("material") or doc.get("default_material"), "size": p.get("size"), "layers": 1,
            "faces": faces, "refs": refs, "tol": max(diag / 2000.0, 0.005),
            "M": np.hstack([np.eye(3), np.zeros((3, 1))]), "normal": [float(v) for v in n]}


def plate_views(doc, asm, sources):
    """View data of the plate items: [{"id" ("plate_<id>"), "name", "mesh", "refs", "matrix", "mkey"} or with "error"]."""
    import hashlib
    from . import assembly
    placed = {}

    def placed_shape(cid):
        if cid not in placed:
            c = next((x for x in asm.get("components") or [] if str(x.get("id")) == cid), None)
            if c is None:
                raise AnalysisError("component %s not found" % cid)
            shape, err = sources.load(c.get("source") or {})
            if shape is None:
                raise AnalysisError(err or "no solid")
            placed[cid] = assembly.place(shape, c)
        return placed[cid]
    out = []
    ident = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0]
    for p in resolve_plate_groups(doc):
        pid = "plate_" + str(p.get("id"))
        key = json.dumps(p, sort_keys=True)
        if p.get("face"):
            c = next((x for x in asm.get("components") or [] if str(x.get("id")) == str(p["face"].get("comp"))), {})
            key += json.dumps([c.get("pos"), c.get("rot"), c.get("source")], sort_keys=True)
        mkey = "pl_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        try:
            sol, n = plate_solid(p, placed_shape)
            mesh, faces, refs = _mesh_faces(sol)
            out.append({"id": pid, "name": p.get("name"), "mesh": mesh, "refs": refs, "matrix": ident, "mkey": mkey,
                        "plate": True})
        except Exception as e:
            out.append({"id": pid, "name": p.get("name"), "error": str(e), "plate": True})
    return out


# --------------------------------------------------------------------------- model

_TET_FACES = [(1, 2, 3), (1, 4, 2), (2, 4, 3), (3, 4, 1)]
_HEX_FACES = [(1, 2, 3, 4), (5, 8, 7, 6), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 8, 4), (4, 8, 5, 1)]
_WEDGE_FACES = [(1, 2, 3), (4, 5, 6), (1, 2, 5, 4), (2, 3, 6, 5), (3, 1, 4, 6)]
FACE_NODES = {   # Abaqus element faces (1-based corner indices)
    "C3D4": _TET_FACES, "C3D10": _TET_FACES,
    "C3D8I": _HEX_FACES, "C3D8": _HEX_FACES, "C3D8R": _HEX_FACES, "C3D20": _HEX_FACES, "C3D20R": _HEX_FACES,
    "C3D6": _WEDGE_FACES, "C3D15": _WEDGE_FACES,
}
NCORNER = {"C3D4": 4, "C3D10": 4, "C3D8I": 8, "C3D8": 8, "C3D8R": 8, "C3D20": 8, "C3D20R": 8, "C3D6": 6, "C3D15": 6}
# consistent nodal fractions of a uniform body force (exact for straight-sided elements of constant Jacobian)
_W_HEX20 = [-1.0 / 8] * 8 + [1.0 / 6] * 12
_W_WEDGE15 = [-1.0 / 9] * 6 + [1.0 / 6] * 6 + [2.0 / 9] * 3
BODY_FRACTIONS = {"C3D4": [0.25] * 4, "C3D10": [-1.0 / 20] * 4 + [1.0 / 5] * 6, "C3D8I": [0.125] * 8,
                  "C3D8": [0.125] * 8, "C3D8R": [0.125] * 8, "C3D20": _W_HEX20, "C3D20R": _W_HEX20,
                  "C3D6": [1.0 / 6] * 6, "C3D15": _W_WEDGE15}


def resolve_plate_groups(doc):
    """Plates with the thickness, material and element size of their group (doc["plate_groups"]: [{"id", "name",
    "t", "material", "size"}], plate "group": group id)."""
    groups = {g.get("id"): g for g in doc.get("plate_groups") or []}
    out = []
    for p in doc.get("plates") or []:
        g = groups.get(p.get("group"))
        if g:
            p = dict(p)
            for k in ("t", "material", "size"):
                if g.get(k) is not None:
                    p[k] = g[k]
                elif k != "t":
                    p.pop(k, None)
        out.append(p)
    return out


def resolve_groups(doc):
    """Members with the kind, section and material of their group (doc["groups"]: [{"id", "name", "kind",
    "section", "material"}], member "group": group id)."""
    groups = {g.get("id"): g for g in doc.get("groups") or []}
    out = []
    for m in doc.get("members") or []:
        g = groups.get(m.get("group"))
        if g:
            m = dict(m)
            for k in ("kind", "section", "material"):
                if g.get(k) is not None:
                    m[k] = g[k]
        out.append(m)
    return out


class Model(object):
    """Builds the CalculiX input of an analysis from the bodies (geometry()) and the mesh (femesh)."""

    def __init__(self, doc, bodies, mesh):
        doc = dict(doc, members=resolve_groups(doc))
        self.doc = doc
        self.bodies = {b["id"]: b for b in bodies}
        self.mesh = mesh
        ids = mesh["nodes"]["ids"]
        xyz = np.asarray(mesh["nodes"]["xyz"], float).reshape(-1, 3)
        self.X = {int(i): xyz[k] for k, i in enumerate(ids)}
        self.next_node = (max(ids) if ids else 0) + 1
        self.next_elem = 1 + max([e[0] for b in mesh["bodies"].values() for bl in b["blocks"] for e in bl["elements"]] or [0])
        self.lines = []
        self.warnings = list(mesh.get("warnings") or [])
        self.equations = []             # input lines
        self.dependent = set()          # (node, dof)
        self.spc = {}                   # node -> set of dofs (global, or local for transformed nodes)
        self.transforms = []            # (nset name, a, b)
        self.nsets, self.elsets = {}, {}
        self.cloads = [{}, {}]          # step index (0: preload, 1: loads) -> {(node, dof): value}
        self.grav = None
        self.members, self.fasteners, self.supports, self.loads = [], [], [], []
        self.mat_names = {}
        self.rot_nodes = set()          # nodes with rotational degrees of freedom (U1)
        self.beam_elems = []            # (elem, member info, n1, n2, t, e1, e2, L, q)
        self.rod_elems = []
        self.face_cache = {}
        allx = np.asarray(list(self.X.values())) if self.X else np.zeros((1, 3))
        pts = [allx]
        for m in doc.get("members") or []:
            for k in ("a", "b"):
                p = (m.get(k) or {}).get("xyz")
                if p:
                    pts.append(np.asarray([p], float))
        allp = np.vstack(pts)
        self.diag = float(np.linalg.norm(allp.max(0) - allp.min(0))) or 1.0
        self.ptol = max(self.diag * 1e-7, 1e-6)
        self.point_nodes = {}
        self.eq_loads = {}
        self.rbe_nodes = set()
        self.ties = []
        self.rps = {}                   # reference point id -> {"name", "ref", "rot", "xyz", "nodes", "joints"}
        self.rigid = []                 # (nset, ref node, rot node) of *RIGID BODY
        self.rp_rot_nodes = set()       # rotation nodes of reference points (their translations are rotations)
        self.atype = doc.get("analysis_type") or "static"      # static | modal | buckling
        if self.atype not in ATYPES:
            raise AnalysisError("unknown analysis type %s" % self.atype)
        self.nmodes = max(1, min(MAX_MODES, int(doc.get("modes") or 6)))

    # ------------------------------------------------------------------ helpers
    def new_node(self, p):
        n = self.next_node
        self.next_node += 1
        self.X[n] = np.asarray(p, float)
        return n

    def new_elem(self):
        e = self.next_elem
        self.next_elem += 1
        return e

    def material(self, name):
        mats = self.doc.get("materials") or {}
        if not name or name not in mats:
            name = self.doc.get("default_material") or (next(iter(mats)) if mats else None)
        if not name or name not in mats:
            raise AnalysisError("no material defined")
        if name not in self.mat_names:
            self.mat_names[name] = "M%d_%s" % (len(self.mat_names) + 1, re.sub(r"[^A-Za-z0-9]+", "_", name)[:60])
        return name, self.mat_names[name]

    def face(self, ref):
        """Nodes, consistent area weights {node: w} and facets [(nodes, corners)] of a referenced face."""
        key = (str(ref.get("comp")), int(ref.get("face", -1)))
        if key in self.face_cache:
            return self.face_cache[key]
        b = self.bodies.get(key[0])
        if b is None:
            raise AnalysisError("face %s of component %s: the component is not in the analysis" % (key[1], key[0]))
        tri = b["faces"].get(key[1])
        if tri is None:
            raise AnalysisError("face %s of component %s not found" % (key[1], key[0]))
        mb = self.mesh["bodies"].get(key[0])
        thr = 3 * b["tol"] + 1e-6 * self.diag
        A, B, C = tri
        lo = np.minimum(np.minimum(A.min(0), B.min(0)), C.min(0)) - thr
        hi = np.maximum(np.maximum(A.max(0), B.max(0)), C.max(0)) + thr
        nodes, facets = set(), []
        for s in mb["surfaces"]:
            sp = np.asarray(s["sample"], float)
            if not len(sp) or (sp < lo).any() or (sp > hi).any():
                continue
            if _point_tri_dist(sp, A, B, C).max() <= thr:
                nodes.update(s["nodes"])
                facets += s["facets"]
        if not nodes:
            raise AnalysisError("face %s of component %s: no mesh nodes found on the face" % (key[1], b["name"]))
        w = {}
        for f in facets:
            nc = 4 if len(f) in (4, 8) else 3
            P = [self.X[n] for n in f[:nc]]
            if nc == 3:
                area = 0.5 * np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0]))
            else:
                area = 0.5 * np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[1]))
            if len(f) == 6:              # quadratic triangle: consistent loads on the mid-side nodes
                for n in f[3:]:
                    w[n] = w.get(n, 0.0) + area / 3
            elif len(f) == 8:            # quadratic quadrangle: the loads on the mid-side nodes
                for n in f[4:]:
                    w[n] = w.get(n, 0.0) + area / 4
            else:
                for n in f[:nc]:
                    w[n] = w.get(n, 0.0) + area / nc
        res = {"nodes": sorted(nodes), "w": w, "facets": facets, "area": sum(w.values()), "body": key[0]}
        self.face_cache[key] = res
        return res

    def face_near(self, face, p, r, what):
        """The part of a face within distance r of point p (nodes and weights)."""
        ids = [n for n in face["nodes"] if np.linalg.norm(self.X[n] - p) <= r]
        w = {n: face["w"][n] for n in ids if n in face["w"]}
        if len([n for n in w if w[n] > 0]) < 3:
            raise AnalysisError("%s: fewer than 3 face nodes within the connection radius %g mm" % (what, r))
        return dict(face, nodes=ids, w=w, area=sum(w.values()))

    def face_normal_out(self, ref, f):
        """Outward unit normal of a facet (sign from the nearest triangle of the CAD face)."""
        b = self.bodies[str(ref["comp"])]
        A, B, C = b["faces"][int(ref["face"])]
        cn = np.cross(B - A, C - A)
        cc = (A + B + C) / 3
        nc = 4 if len(f) in (4, 8) else 3
        P = [self.X[n] for n in f[:nc]]
        n = np.cross(P[1] - P[0], P[2] - P[0]) if nc == 3 else np.cross(P[2] - P[0], P[3] - P[1])
        c = sum(P) / nc
        k = int(np.argmin(np.linalg.norm(cc - c, axis=1)))
        if np.dot(n, cn[k]) < 0:
            n = -n
        return _unit(n), 0.5 * np.linalg.norm(n) if nc == 3 else 0.5 * np.linalg.norm(n)

    def nset(self, name, nodes):
        self.nsets[name] = sorted(set(int(n) for n in nodes))
        return name

    def add_eq(self, terms):
        """terms [(node, dof, coef)]; the first term is the dependent DOF."""
        n, d, c = terms[0]
        if (n, d) in self.dependent:
            raise AnalysisError("node %d dof %d is constrained twice (two connections at the same point)" % (n, d))
        if d in self.spc.get(n, ()):
            raise AnalysisError("a supported point is also connected to a face (node %d)" % n)
        self.dependent.add((n, d))
        out = [str(len(terms))]
        row = []
        for t in terms:
            row.append("%d, %d, %.12g" % t)
            if len(row) == 4:
                out.append(", ".join(row))
                row = []
        if row:
            out.append(", ".join(row))
        self.equations += out

    def rbe3(self, ref_node, face, rotations=True):
        """RBE3: ref node DOFs (dependent) = weighted mean motion of the face nodes (supported nodes left out)."""
        ids = [n for n in face["nodes"] if face["w"].get(n, 0) > 0 and not self.spc.get(n)]
        if len(ids) < 3:
            raise AnalysisError("a connected face has fewer than 3 free nodes")
        xyz = np.asarray([self.X[n] for n in ids])
        w = np.asarray([face["w"][n] for n in ids], float)
        w = w / w.sum()
        c = (w[:, None] * xyz).sum(0)
        r = xyz - c
        Am = np.zeros((3, 3))
        for wi, ri in zip(w, r):
            Am += wi * (ri @ ri * np.eye(3) - np.outer(ri, ri))
        sk = lambda v: np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        Ainv = np.linalg.pinv(Am)
        T = [Ainv @ (wi * sk(ri)) for wi, ri in zip(w, r)]
        D = sk(self.X[ref_node] - c)
        tol = 1e-12
        for k in range(3):
            terms = [(ref_node, k + 1, 1.0)]
            for i, n in enumerate(ids):
                coef = w[i] * np.eye(3)[k] - (D @ T[i])[k]
                for j in range(3):
                    if abs(coef[j]) > tol:
                        terms.append((n, j + 1, -coef[j]))
            self.add_eq(terms)
        if rotations:
            for k in range(3):
                terms = [(ref_node, k + 4, 1.0)]
                for i, n in enumerate(ids):
                    for j in range(3):
                        if abs(T[i][k, j]) > tol:
                            terms.append((n, j + 1, -T[i][k, j]))
                self.add_eq(terms)
        return c

    def distribute(self, face, F=None, M=None, step=1):
        """Nodal forces of a total force F and a moment M (about the weighted face centre) on a face."""
        ids = [n for n in face["nodes"] if face["w"].get(n, 0) > 0]
        xyz = np.asarray([self.X[n] for n in ids])
        w = np.asarray([face["w"][n] for n in ids], float)
        w = w / w.sum()
        c = (w[:, None] * xyz).sum(0)
        f = np.zeros((len(ids), 3))
        if F is not None:
            f += w[:, None] * np.asarray(F, float)[None]
        if M is not None and np.linalg.norm(M) > 0:
            r = xyz - c
            Am = np.zeros((3, 3))
            for wi, ri in zip(w, r):
                Am += wi * (ri @ ri * np.eye(3) - np.outer(ri, ri))
            a = np.linalg.pinv(Am) @ np.asarray(M, float)
            f += w[:, None] * np.cross(a[None], r)
        for n, fi in zip(ids, f):
            for d in range(3):
                if abs(fi[d]) > 0:
                    self.cload(n, d + 1, fi[d], step)
        return c

    def cload(self, n, d, v, step=1):
        cl = self.cloads[step]
        cl[(n, d)] = cl.get((n, d), 0.0) + float(v)

    def point_node(self, p):
        """Member node at point p (shared by the members meeting there)."""
        p = np.asarray(p, float)
        for n, q in self.point_nodes.items():
            if np.linalg.norm(q - p) <= self.ptol * 10:
                return n
        n = self.new_node(p)
        self.point_nodes[n] = p
        return n

    # ------------------------------------------------------------------ build
    def build(self):
        doc = self.doc
        for s in doc.get("supports") or []:
            if not s.get("target"):
                raise AnalysisError("support %s has no target (pick a face or choose a member end)" % (s.get("name") or s.get("id")))
        for ld in doc.get("loads") or []:
            if (ld.get("type") or "force") != "gravity" and not ld.get("target"):
                raise AnalysisError("load %s has no target" % (ld.get("name") or ld.get("id")))
        for f in doc.get("fasteners") or []:
            if len([r for r in (f.get("faces") or []) if r]) != 2:
                raise AnalysisError("fastener %s: pick the two faces" % (f.get("name") or f.get("id")))
        for m in doc.get("members") or []:
            for k in ("a", "b"):
                if not (m.get(k) or {}).get("xyz"):
                    raise AnalysisError("member %s: end %s has no point" % (m.get("name") or m.get("id"), k.upper()))
        if not (doc.get("supports") or []):
            raise AnalysisError("no supports")
        if self.atype != "static":
            beams = [m.get("name") or m.get("id") for m in doc.get("members") or [] if (m.get("kind") or "beam") == "beam"]
            fas = [f.get("name") or f.get("id") for f in doc.get("fasteners") or []]
            if beams or fas:
                raise AnalysisError("%s analysis: beams and fasteners are not available (the CalculiX U1 beam element has "
                                    "no mass and no stress stiffness); %s. Rods, plates and solid bodies are available"
                                    % (ATYPE_NAMES[self.atype].lower(), ", ".join(
                                        (["beams " + ", ".join(beams[:5])] if beams else []) + (["fasteners " + ", ".join(fas[:5])] if fas else []))))
        # bodies
        self.body_sets = []
        for bid, mb in self.mesh["bodies"].items():
            b = self.bodies[bid]
            mname, mset = self.material(b.get("material"))
            for k, bl in enumerate(mb["blocks"]):
                es = "B%s_%d" % (re.sub(r"[^A-Za-z0-9]+", "_", bid), k + 1)
                self.elsets[es] = (bl["type"], bl["elements"])
                self.body_sets.append((es, bid, mname))
        # members: nodes at the ends and at the ends of other members lying on them
        mems = doc.get("members") or []
        ends = []
        for m in mems:
            for k in ("a", "b"):
                p = (m.get(k) or {}).get("xyz")
                if p is None:
                    raise AnalysisError("member %s: end %s has no point" % (m.get("name") or m.get("id"), k))
                ends.append(np.asarray(p, float))
        size = float((doc.get("mesh") or {}).get("size") or 0) or self.diag / 20.0
        for m in mems:
            self._member(m, ends, size)
        for f in doc.get("fasteners") or []:
            self._fastener_geometry(f)
        for p in doc.get("points") or []:
            self._ref_point_nodes(p)
        for s in doc.get("supports") or []:
            self._support(s)
        self.elem_nodes = set()
        for info in self.members + self.fasteners:
            for e, n1, n2 in info["elems"]:
                self.elem_nodes.update((n1, n2))
        for info in self.members:
            self._member_connections(info)
        for info in self.fasteners:
            self._fastener_connections(info)
        for p in doc.get("points") or []:
            self._ref_point_links(p)
        for ld in doc.get("loads") or []:
            self._load(ld)
        self._member_loads()
        if self.doc.get("bonded", True):
            self._ties()
            self._member_plate_ties()
        if self.atype == "modal":
            mats = doc.get("materials") or {}
            bad = [n for n in self.mat_names if not float((mats.get(n) or {}).get("rho") or 0) > 0]
            if bad:
                raise AnalysisError("modal analysis: material %s has no density" % ", ".join(bad))
        if self.atype == "buckling":
            loaded = any(v for v in self.cloads[1].values()) or any(v for sp in self.supports for v in sp["values"].values()) \
                or any(v for sp in self.supports for v in ((sp.get("rot") or {}).get("values") or {}).values())
            if not loaded:
                raise AnalysisError("buckling analysis: no loads (the buckling factors multiply the loads)")

    def _member(self, m, ends, size):
        name = m.get("name") or m.get("id")
        kind = m.get("kind") or "beam"
        a, b = np.asarray(m["a"]["xyz"], float), np.asarray(m["b"]["xyz"], float)
        L = float(np.linalg.norm(b - a))
        if L <= self.ptol * 100:
            raise AnalysisError("member %s has zero length" % name)
        t, e1, e2 = member_axes(a, b, m.get("up"))
        mname, mset = self.material(m.get("material"))
        sec = section_props(m.get("section") or {"shape": "ROUND", "d": 10})
        params = {0.0, 1.0}
        for p in ends:
            s = float(np.dot(p - a, t)) / L
            if 1e-6 < s < 1 - 1e-6 and np.linalg.norm(a + s * L * t - p) <= self.ptol * 10:
                params.add(s)
        params = sorted(params)
        nseg = int(m.get("n") or 0) or (max(4, int(math.ceil(L / size))) if kind == "beam" else 1)
        pts = []
        for s0, s1 in zip(params, params[1:]):
            k = 1 if kind == "rod" else max(1, int(round(nseg * (s1 - s0))))
            for j in range(k):
                pts.append(s0 + (s1 - s0) * j / k)
        pts.append(1.0)
        nodes = []
        for s in pts:
            p = a + s * L * t
            on_point = any(abs(s - q) < 1e-9 for q in params)
            nodes.append(self.point_node(p) if on_point else self.new_node(p))
        rel = m.get("release") or ""
        joint = {"a": nodes[0], "b": nodes[-1]}
        if kind == "beam":
            if "a" in rel:
                nodes[0] = self.new_node(self.X[nodes[0]])
            if "b" in rel:
                nodes[-1] = self.new_node(self.X[nodes[-1]])
        els = []
        es = "EM%d" % (len(self.members) + 1)
        for n1, n2 in zip(nodes, nodes[1:]):
            e = self.new_elem()
            els.append((e, n1, n2))
            if kind == "beam":
                self.rot_nodes.update((n1, n2))
        info = {"m": m, "name": name, "kind": kind, "elset": es, "elems": els, "nodes": nodes, "joint": joint,
                "t": t, "e1": e1, "e2": e2, "L": L, "sec": sec, "material": mname, "mset": mset, "release": rel,
                "q": np.zeros(3), "end_nodes": {"a": nodes[0], "b": nodes[-1]}}
        self.members.append(info)

    def _fastener_geometry(self, f):
        name = f.get("name") or f.get("id")
        fr = f.get("faces") or []
        if len(fr) != 2:
            raise AnalysisError("fastener %s: two faces required" % name)
        fa, fb = self.face(fr[0]), self.face(fr[1])
        def centre(face):
            ids = list(face["w"])
            w = np.asarray([face["w"][n] for n in ids], float)
            return (w[:, None] * np.asarray([self.X[n] for n in ids])).sum(0) / w.sum()
        ca, cb = centre(fa), centre(fb)
        axis = None
        for r in fr:
            b = self.bodies[str(r["comp"])]
            refs = b["refs"]
            ref = refs[int(r["face"])] if int(r["face"]) < len(refs) else None
            if ref and ref.get("kind") == "cylinder":
                M = b["M"]
                p = M[:, :3] @ np.asarray(ref["p"], float) + M[:, 3]
                n = _unit(M[:, :3] @ np.asarray(ref["n"], float))
                axis = (p, n)
                break
        if axis is not None:
            p, n = axis
            A = p + np.dot(ca - p, n) * n
            B = p + np.dot(cb - p, n) * n
        else:
            A, B = ca, cb
        L = float(np.linalg.norm(B - A))
        if L <= self.ptol * 100:
            raise AnalysisError("fastener %s: the two faces have the same centre on the axis" % name)
        t = (B - A) / L
        up = np.array([0, 0, 1.0]) if abs(t[2]) < 0.9 else np.array([1.0, 0, 0])
        t, e1, e2 = member_axes(A, B, up)
        d = float(f.get("d") or 0)
        if d <= 0:
            raise AnalysisError("fastener %s: diameter required" % name)
        mname, mset = self.material(f.get("material"))
        F = float(f.get("preload") or 0)
        nA, nB = self.new_node(A), self.new_node(B)
        if F:
            n1 = self.new_node(A + 0.25 * L * t)
            pm = self.new_node(A + 0.5 * L * t)
            pp = self.new_node(A + 0.5 * L * t)
            n2 = self.new_node(A + 0.75 * L * t)
            chain = [(nA, n1), (n1, pm), (pp, n2), (n2, nB)]
            pt = self.new_node(A + 0.5 * L * t)
        else:
            n1 = self.new_node(A + 0.25 * L * t)
            mid = self.new_node(A + 0.5 * L * t)
            n2 = self.new_node(A + 0.75 * L * t)
            chain = [(nA, n1), (n1, mid), (mid, n2), (n2, nB)]
            pm = pp = pt = None
        els = []
        for a_, b_ in chain:
            els.append((self.new_elem(), a_, b_))
            self.rot_nodes.update((a_, b_))
        info = {"f": f, "name": name, "elset": "EF%d" % (len(self.fasteners) + 1), "elems": els, "A": nA, "B": nB,
                "pm": pm, "pp": pp, "pt": pt, "t": t, "e1": e1, "e2": e2, "L": L, "d": d, "preload": F,
                "sec": section_props({"shape": "ROUND", "d": d}), "material": mname, "mset": mset,
                "faces": (fa, fb), "spring": self.new_elem() if F else None}
        self.fasteners.append(info)

    def _ref_point_nodes(self, p):
        """Reference point: a node for the translations (REF NODE) and a node whose translations are the rotations
        (ROT NODE) of a CalculiX *RIGID BODY."""
        name = p.get("name") or p.get("id")
        xyz = p.get("xyz")
        if not xyz or len(xyz) != 3:
            raise AnalysisError("reference point %s has no coordinates" % name)
        if not (p.get("faces") or []):
            raise AnalysisError("reference point %s: pick the faces it is rigidly connected to" % name)
        xyz = np.asarray(xyz, float)
        ref, rot = self.new_node(xyz), self.new_node(xyz)
        self.rp_rot_nodes.add(rot)
        self.rps[str(p.get("id"))] = {"name": name, "ref": ref, "rot": rot, "xyz": xyz, "nodes": [], "joints": []}

    def _ref_point_links(self, p):
        """Rigid connection of a reference point: the nodes of its faces (*RIGID BODY; supported nodes and nodes
        already constrained are left out) and the member ends at the point (translations and, at a beam end,
        rotations equal to those of the reference point)."""
        rp = self.rps[str(p.get("id"))]
        nodes = set()
        for fr in p.get("faces") or []:
            nodes.update(self.face(fr)["nodes"])
        left = [n for n in nodes if self.spc.get(n) or (n, 1) in self.dependent]
        nodes = sorted(n for n in nodes if not self.spc.get(n) and (n, 1) not in self.dependent)
        if left:
            self.warnings.append("reference point %s: %d supported or constrained face node(s) left out of the rigid "
                                 "connection" % (rp["name"], len(left)))
        self._rigid_set(rp, nodes)
        tol = max(self.ptol, 1e-6 * self.diag)
        joints = sorted(set(info["joint"][e] for info in self.members for e in ("a", "b")
                            if np.linalg.norm(self.X[info["joint"][e]] - rp["xyz"]) <= tol))
        for j in joints:
            for d in (1, 2, 3):
                self.add_eq([(j, d, 1.0), (rp["ref"], d, -1.0)])
            if j in self.rot_nodes:
                for d in (1, 2, 3):
                    self.add_eq([(j, d + 3, 1.0), (rp["rot"], d, -1.0)])
        rp["joints"] = joints

    def _rigid_set(self, rp, nodes):
        """*RIGID BODY of the nodes on the reference point rp."""
        if not nodes:
            raise AnalysisError("reference point %s: no free nodes on its faces" % rp["name"])
        k = len(self.rigid) + 1
        ns = self.nset("RB%d" % k, nodes)
        self.rigid.append((ns, rp["ref"], rp["rot"]))
        self.dependent.update((n, d) for n in nodes for d in (1, 2, 3))
        rp["nodes"] = list(nodes)

    def rigid_face(self, j, face, rotations):
        """Rigid coupling of the free face nodes to node j (beam end): u_i = u_j + theta_j x (x_i - x_j); without
        rotations (rod end) u_i = u_j."""
        ids = [n for n in face["nodes"] if not self.spc.get(n) and (n, 1) not in self.dependent and n != j]
        if not ids:
            raise AnalysisError("a rigidly connected face has no free nodes")
        for n in ids:
            r = self.X[n] - self.X[j]
            if rotations:
                self.add_eq([(n, 1, 1.0), (j, 1, -1.0), (j, 5, -float(r[2])), (j, 6, float(r[1]))])
                self.add_eq([(n, 2, 1.0), (j, 2, -1.0), (j, 6, -float(r[0])), (j, 4, float(r[2]))])
                self.add_eq([(n, 3, 1.0), (j, 3, -1.0), (j, 4, -float(r[1])), (j, 5, float(r[0]))])
            else:
                for d in (1, 2, 3):
                    self.add_eq([(n, d, 1.0), (j, d, -1.0)])

    def _support(self, s):
        name = s.get("name") or s.get("id")
        tgt = s.get("target") or {}
        typ = s.get("type") or "fixed"
        nodes, rot_ok = [], False
        trans = None
        values = {}                     # dof -> prescribed displacement (mm; rad for rotations)
        fl6 = list(s.get("dofs") or [1, 1, 1, 0, 0, 0]) + [0] * 6
        if "point" not in tgt and "member" not in tgt and typ in ("dofs", "displacement") and any(fl6[3:6]):
            # rotations on a face: the face is rigidly coupled (kinematic coupling) to a node at its weighted centre
            face = self.face(tgt)
            ws = face["w"]
            tw = sum(ws.values())
            c = sum(self.X[n] * w for n, w in ws.items()) / tw if tw > 0 else np.mean([self.X[n] for n in face["nodes"]], axis=0)
            pid = "_sup_%s" % (s.get("id") or len(self.supports))
            self._ref_point_nodes({"id": pid, "name": "%s (face coupling)" % name, "xyz": list(c), "faces": [tgt]})
            rp = self.rps[pid]
            self._rigid_set(rp, [n for n in face["nodes"] if not self.spc.get(n) and (n, 1) not in self.dependent])
            tgt = {"point": pid}
        if "point" in tgt:
            rp = self.rps.get(str(tgt["point"]))
            if rp is None:
                raise AnalysisError("support %s: reference point not found" % name)
            dofs = {"fixed": [1, 2, 3, 4, 5, 6], "pinned": [1, 2, 3]}.get(typ)
            if dofs is None:
                fl = s.get("dofs") or [1, 1, 1, 0, 0, 0]
                dofs = [i + 1 for i, v in enumerate(fl) if v]
                if typ == "displacement":
                    vv = (list(s.get("value") or []) + [0.0] * 6)[:6]
                    values = {d: float(vv[d - 1] or 0) for d in dofs}
            if not dofs:
                raise AnalysisError("support %s fixes no degree of freedom" % name)
            k = len(self.supports) + 1
            ns, nr = self.nset("SUP%d" % k, [rp["ref"]]), self.nset("SUP%dR" % k, [rp["rot"]])
            td, rd = [d for d in dofs if d <= 3], [d - 3 for d in dofs if d > 3]
            self.spc.setdefault(rp["ref"], set()).update(td)
            self.spc.setdefault(rp["rot"], set()).update(rd)
            self.supports.append({"s": s, "name": name, "nset": ns, "nodes": [rp["ref"]], "dofs": td, "trans": None,
                                  "values": {d: v for d, v in values.items() if d <= 3}, "member": False, "point": True,
                                  "rot": {"nset": nr, "node": rp["rot"], "dofs": rd,
                                          "values": {d - 3: v for d, v in values.items() if d > 3}},
                                  "centre": np.asarray(rp["xyz"], float)})
            return
        if "member" in tgt:
            info = next((x for x in self.members if str(x["m"].get("id")) == str(tgt["member"])), None)
            if info is None:
                raise AnalysisError("support %s: member not found" % name)
            n = info["joint"][tgt.get("end") or "a"]
            nodes = [n]
            rot_ok = n in self.rot_nodes
            dofs = {"fixed": [1, 2, 3, 4, 5, 6], "pinned": [1, 2, 3]}.get(typ)
            if dofs is None:
                fl = s.get("dofs") or [1, 1, 1, 0, 0, 0]
                dofs = [i + 1 for i, v in enumerate(fl) if v]
                if typ == "displacement":
                    vv = (list(s.get("value") or []) + [0.0] * 6)[:6]
                    values = {d: float(vv[d - 1] or 0) for d in dofs}
            if not rot_ok:
                dofs = [d for d in dofs if d <= 3]
        else:
            face = self.face(tgt)
            nodes = face["nodes"]
            if typ == "normal":
                n0, _ = self.face_normal_out(tgt, face["facets"][0])
                ns = [self.face_normal_out(tgt, fc)[0] for fc in face["facets"][:50]]
                if min(abs(float(np.dot(n0, v))) for v in ns) < 0.9999:
                    raise AnalysisError("support %s: the normal support needs a planar face" % name)
                other = np.array([1.0, 0, 0]) if abs(n0[0]) < 0.9 else np.array([0, 1.0, 0])
                bb = _unit(other - np.dot(other, n0) * n0)
                trans = (n0, bb)
                dofs = [1]
                if s.get("value"):
                    values = {1: float(s.get("value") or 0)}      # along the outward normal
            elif typ in ("dofs", "displacement"):
                fl = s.get("dofs") or [1, 1, 1]
                dofs = [i + 1 for i, v in enumerate(fl[:3]) if v]
                if typ == "displacement":
                    vv = (list(s.get("value") or []) + [0.0] * 3)[:3]
                    values = {d: float(vv[d - 1] or 0) for d in dofs}
            else:
                dofs = [1, 2, 3]
        if not dofs:
            raise AnalysisError("support %s fixes no degree of freedom" % name)
        ns = "SUP%d" % (len(self.supports) + 1)
        self.nset(ns, nodes)
        if "member" in tgt:
            centre = self.X[nodes[0]]
        else:
            ws = face["w"]
            tw = sum(ws.values())
            centre = sum(self.X[n] * w for n, w in ws.items()) / tw if tw > 0 else np.mean([self.X[n] for n in nodes], axis=0)
        if trans is not None:
            self.transforms.append((ns, trans[0], trans[1]))
        for n in nodes:
            self.spc.setdefault(n, set()).update(dofs)
        self.supports.append({"s": s, "name": name, "nset": ns, "nodes": list(nodes), "dofs": dofs, "trans": trans, "values": values,
                              "member": "member" in tgt, "centre": np.asarray(centre, float)})

    def _has_rot(self, n):
        return n in self.rot_nodes or any(d > 3 for d in self.spc.get(n, ()))

    def _member_connections(self, info):
        m = info["m"]
        for end in ("a", "b"):
            j = info["joint"][end]
            fref = (m.get(end) or {}).get("face")
            if fref and j not in self.rbe_nodes:
                face = self.face(fref)
                r = float((m.get(end) or {}).get("r") or 0)
                if r > 0:
                    face = self.face_near(face, self.X[j], r, "member %s end %s" % (info["name"], end.upper()))
                if (m.get(end) or {}).get("coupling") == "rigid":
                    self.rigid_face(j, face, rotations=self._has_rot(j) or info["kind"] == "beam")
                else:
                    self.rbe3(j, face, rotations=self._has_rot(j) or info["kind"] == "beam")
                if info["kind"] == "beam":
                    self.rot_nodes.add(j)
                self.rbe_nodes.add(j)
        # bending releases: translations of the beam end node follow the joint; torsion connected at one end
        rel = info["release"] if info["kind"] == "beam" else ""
        tied_torsion = False
        for end in ("a", "b"):
            if end not in rel:
                continue
            r, j = info["end_nodes"][end], info["joint"][end]
            anchored = (j in self.elem_nodes or j in self.rbe_nodes or self.spc.get(j) or (j, 1) in self.dependent)
            for d in (1, 2, 3):
                if anchored:
                    self.add_eq([(r, d, 1.0), (j, d, -1.0)])
                else:                       # free hinge: the joint follows the first released end
                    self.add_eq([(j, d, 1.0), (r, d, -1.0)])
            if rel == "ab" and tied_torsion:
                continue
            if rel == "ab" and not self._has_rot(j):
                continue
            if self._has_rot(j):
                t = info["t"]
                k = int(np.argmax(np.abs(t)))
                terms = [(r, 4 + k, float(t[k]))]
                for i in range(3):
                    if i != k and abs(t[i]) > 1e-12:
                        terms.append((r, 4 + i, float(t[i])))
                for i in range(3):
                    if abs(t[i]) > 1e-12:
                        terms.append((j, 4 + i, -float(t[i])))
                self.add_eq(terms)
                tied_torsion = True
        if rel == "ab" and not tied_torsion:
            raise AnalysisError("member %s: both ends released and no end has a rotational connection (torsion free)" % info["name"])

    def _fastener_connections(self, info):
        fa, fb = info["faces"]
        self.rbe3(info["A"], fa, rotations=True)
        self.rbe3(info["B"], fb, rotations=True)
        if info["preload"]:
            pp, pm, pt = info["pp"], info["pm"], info["pt"]
            R = np.vstack([info["t"], info["e1"], info["e2"]])
            import itertools
            best = max(itertools.permutations(range(3)), key=lambda p: abs(R[0, p[0]] * R[1, p[1]] * R[2, p[2]]))
            for row, dep in zip(range(3), best):
                v = R[row]
                terms = [(pp, dep + 1, float(v[dep]))]
                for i in range(3):
                    if i != dep and abs(v[i]) > 1e-12:
                        terms.append((pp, i + 1, float(v[i])))
                for i in range(3):
                    if abs(v[i]) > 1e-12:
                        terms.append((pm, i + 1, -float(v[i])))
                if row == 0:
                    terms.append((pt, 1, -1.0))
                self.add_eq(terms)
            for d in (4, 5, 6):
                self.add_eq([(pp, d, 1.0), (pm, d, -1.0)])
            self.cload(pt, 1, -info["preload"], step=0)

    def _target_node(self, tgt, what):
        info = next((x for x in self.members if str(x["m"].get("id")) == str(tgt.get("member"))), None)
        if info is None:
            raise AnalysisError("%s: member not found" % what)
        return info, info["joint"][tgt.get("end") or "a"]

    def _load(self, ld):
        name = ld.get("name") or ld.get("id")
        typ = ld.get("type") or "force"
        tgt = ld.get("target") or {}
        val = ld.get("value")
        if typ == "gravity":
            g = np.asarray(val or [0, 0, -9810.0], float)
            self.grav = g if self.grav is None else self.grav + g
            self._body_weight(g)
            for info in self.members:
                rho = float(((self.doc.get("materials") or {}).get(info["material"]) or {}).get("rho") or 0) * 1e-12
                info["q"] = info["q"] + rho * info["sec"]["A"] * g
            self.loads.append({"l": ld, "name": name, "type": typ})
            return
        if typ == "line":
            info = next((x for x in self.members if str(x["m"].get("id")) == str(tgt.get("member"))), None)
            if info is None:
                raise AnalysisError("load %s: member not found" % name)
            info["q"] = info["q"] + np.asarray(val, float)
            self.loads.append({"l": ld, "name": name, "type": typ, "total": np.asarray(val, float) * info["L"]})
            return
        if "point" in tgt:
            rp = self.rps.get(str(tgt["point"]))
            if rp is None:
                raise AnalysisError("load %s: reference point not found" % name)
            v = np.asarray(val, float)
            if typ == "moment":
                for d in range(3):
                    self.cload(rp["rot"], d + 1, v[d])
                self.loads.append({"l": ld, "name": name, "type": typ, "moment": v, "point": rp["xyz"]})
            elif typ == "force":
                for d in range(3):
                    self.cload(rp["ref"], d + 1, v[d])
                self.loads.append({"l": ld, "name": name, "type": typ, "total": v})
            else:
                raise AnalysisError("load %s: a reference point takes a force or a moment" % name)
            return
        if "member" in tgt:
            info, n = self._target_node(tgt, "load %s" % name)
            v = np.asarray(val, float)
            if typ == "moment":
                if n not in self.rot_nodes:
                    raise AnalysisError("load %s: a moment needs a beam end" % name)
                for d in range(3):
                    self.cload(n, d + 4, v[d])
                self.loads.append({"l": ld, "name": name, "type": typ, "moment": v, "point": self.X[n]})
            else:
                for d in range(3):
                    self.cload(n, d + 1, v[d])
                self.loads.append({"l": ld, "name": name, "type": typ, "total": v})
            return
        face = self.face(tgt)
        if typ == "pressure":
            p = float(val or 0)
            tot = np.zeros(3)
            for f in face["facets"]:
                n, area = self.face_normal_out(tgt, f)
                if len(f) == 6:
                    nn, w = f[3:], [area / 3] * 3
                elif len(f) == 8:              # consistent: corners -1/12, mid-side nodes 1/3
                    nn, w = f, [-area / 12] * 4 + [area / 3] * 4
                else:
                    nc = 4 if len(f) in (4, 8) else 3
                    nn, w = f[:nc], [area / nc] * nc
                for k, wi in zip(nn, w):
                    for d in range(3):
                        self.cload(k, d + 1, -p * n[d] * wi)
                tot += -p * n * area
            self.loads.append({"l": ld, "name": name, "type": typ, "total": tot})
        elif typ == "moment":
            c = self.distribute(face, M=np.asarray(val, float))
            self.loads.append({"l": ld, "name": name, "type": typ, "moment": np.asarray(val, float), "point": c})
        else:
            v = np.asarray(val, float)
            self.distribute(face, F=v)
            self.loads.append({"l": ld, "name": name, "type": typ, "total": v})

    def _body_weight(self, g):
        """Consistent nodal loads of the weight of the solid and plate elements (BODY_FRACTIONS; the volume from
        the corner nodes)."""
        mats = self.doc.get("materials") or {}
        self.body_weight = getattr(self, "body_weight", np.zeros(3))
        tets_of = {4: [(0, 1, 2, 3)], 8: [(0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (3, 4, 6, 7), (1, 4, 5, 6)],
                   6: [(0, 1, 2, 3), (1, 2, 3, 4), (2, 3, 4, 5)]}
        for es, (typ, els) in self.elsets.items():
            mname = next(mn for e2, b, mn in self.body_sets if e2 == es)
            rho = float(mats[mname].get("rho") or 0) * 1e-12
            if rho <= 0:
                continue
            fr = BODY_FRACTIONS[typ]
            tets = tets_of[NCORNER[typ]]
            for e in els:
                n = e[1:]
                P = [self.X[k] for k in n]
                V = sum(abs(np.dot(P[b] - P[a], np.cross(P[c] - P[a], P[d] - P[a]))) / 6 for a, b, c, d in tets)
                W = rho * V * g
                for k, f in zip(n, fr):
                    for d in range(3):
                        self.cload(k, d + 1, W[d] * f)
                self.body_weight = self.body_weight + W

    def _ties(self):
        """Bodies meshed apart from the others (plates, hexahedral bodies: mesh group other than "tet") tied to the
        touching surfaces of the bodies of other groups (slave: the nodes of the body of the other group). Tolerance:
        0.51 times the larger plate thickness of the pair, so that a plate edge on the mid-plane of another plate
        (T-joint of plates defined by their mid-surfaces) is tied to it."""
        self.ties = []
        group = {bid: mb.get("group") or ("tet" if all(bl["type"] in ("C3D10", "C3D4") for bl in mb["blocks"]) else "plate:" + bid)
                 for bid, mb in self.mesh["bodies"].items()}
        plates = [bid for bid in self.mesh["bodies"] if group[bid] != "tet"]
        if not plates:
            return
        node_elem = {}
        for bid, mb in self.mesh["bodies"].items():
            for bl in mb["blocks"]:
                for e in bl["elements"]:
                    for n in e[1:]:
                        node_elem.setdefault(n, []).append((e, bl["type"]))
        thick = {bid: float(mb.get("thickness") or 0) for bid, mb in self.mesh["bodies"].items()}
        tied = set()
        masters = set()
        for pid in plates:
            for si, s in enumerate(self.mesh["bodies"][pid]["surfaces"]):
                sp = np.asarray(s["sample"], float)
                for bid, mb in self.mesh["bodies"].items():
                    if bid == pid or group[bid] == group[pid]:
                        continue
                    tol = max(1e-3 * self.diag, 0.51 * max(thick[pid], thick[bid]))
                    cands = []
                    for s2i, s2 in enumerate(mb["surfaces"]):
                        if (bid, s2i, pid, si) in tied:
                            continue
                        F = s2["facets"]
                        if not F:
                            continue
                        A = np.asarray([self.X[f[0]] for f in F])
                        B = np.asarray([self.X[f[1]] for f in F])
                        C = np.asarray([self.X[f[2]] for f in F])
                        lo, hi = np.minimum(np.minimum(A, B), C).min(0), np.maximum(np.maximum(A, B), C).max(0)
                        inb = ((sp >= lo - tol) & (sp <= hi + tol)).all(1)
                        if inb.sum() < max(3, len(sp) // 2):
                            continue
                        quads = [f for f in F if len(f) in (4, 8)]
                        if quads:
                            A = np.vstack([A, np.asarray([self.X[f[0]] for f in quads])])
                            B = np.vstack([B, np.asarray([self.X[f[2]] for f in quads])])
                            C = np.vstack([C, np.asarray([self.X[f[3]] for f in quads])])
                        d = _point_tri_dist(sp[inb], A, B, C)
                        if (d <= tol).sum() < max(3, len(sp) // 2):
                            continue
                        mnodes = set(n for f in F for n in f)
                        fixed = sum(1 for n in mnodes if self.spc.get(n)) / float(len(mnodes))
                        cands.append((fixed, float(np.mean(d[d <= tol])), s2i, F, (A, B, C), mnodes))
                    # the touching surface with the fewest supported nodes, then the nearest (a supported master
                    # face would pass the load to the support outside the reaction output)
                    for fixed, dm, s2i, F, (A, B, C), mnodes in sorted(cands, key=lambda c: (c[0], c[1]))[:1]:
                        sn = np.asarray(s["nodes"])
                        ds = _point_tri_dist(np.asarray([self.X[n] for n in sn]), A, B, C)
                        slave = [int(n) for n in sn[ds <= tol] if (int(n), 1) not in self.dependent
                                 and int(n) not in masters and int(n) not in mnodes and not self.spc.get(int(n))]
                        if len(slave) < 3:
                            continue
                        master = self._facet_faces(F, node_elem)
                        if not master:
                            continue
                        k = len(self.ties) + 1
                        self.nset("TS%d" % k, slave)
                        self.ties.append({"name": "T%d" % k, "slave": "TS%d" % k, "master": master, "tol": tol * 1.5,
                                          "bodies": (pid, bid), "nodes": slave})
                        tied.add((pid, si, bid, s2i))
                        masters |= mnodes
                        for n in slave:
                            self.dependent.update((n, d_) for d_ in (1, 2, 3))

    def _member_plate_ties(self):
        """Members lying on a plate (along its edge or across its mid-surface, within 0.51 times the plate thickness
        of a plate surface) are tied to the plate: translations of the member nodes follow the plate surface
        (*TIE, slave: member nodes). Member nodes that are supported, connected to a face by RBE3 or already tied
        are left out."""
        mn = sorted(set(n for info in self.members for e, a, b in info["elems"] for n in (a, b)))
        mn = [n for n in mn if (n, 1) not in self.dependent and not self.spc.get(n) and n not in self.rbe_nodes]
        if not mn:
            return
        P = np.asarray([self.X[n] for n in mn])
        node_elem = {}
        for bid, mb in self.mesh["bodies"].items():
            for bl in mb["blocks"]:
                for e in bl["elements"]:
                    for n in e[1:]:
                        node_elem.setdefault(n, []).append((e, bl["type"]))
        used = set()
        for bid, mb in self.mesh["bodies"].items():
            if not str(mb.get("group") or "").startswith("plate:"):
                continue
            tol = max(1e-3 * self.diag, 0.51 * float(mb.get("thickness") or 0))
            F = [f for sf in mb["surfaces"] for f in sf["facets"]]
            if not F:
                continue
            A = [self.X[f[0]] for f in F] + [self.X[f[0]] for f in F if len(f) in (4, 8)]
            B = [self.X[f[1]] for f in F] + [self.X[f[2]] for f in F if len(f) in (4, 8)]
            C = [self.X[f[2]] for f in F] + [self.X[f[3]] for f in F if len(f) in (4, 8)]
            d = _point_tri_dist(P, np.asarray(A), np.asarray(B), np.asarray(C))
            slave = [mn[i] for i in np.where(d <= tol)[0] if mn[i] not in used]
            if not slave:
                continue
            master = self._facet_faces(F, node_elem)
            if not master:
                continue
            k = len(self.ties) + 1
            self.nset("TS%d" % k, slave)
            self.ties.append({"name": "T%d" % k, "slave": "TS%d" % k, "master": master, "tol": tol * 1.5,
                              "bodies": ("members", bid), "nodes": slave})
            used.update(slave)
            for n in slave:
                self.dependent.update((n, d_) for d_ in (1, 2, 3))

    def _facet_faces(self, facets, node_elem):
        out = []
        for f in facets:
            nc = 4 if len(f) in (4, 8) else 3
            cs = set(f[:nc])
            for e, typ in node_elem.get(f[0], ()):
                if not cs.issubset(set(e[1:1 + NCORNER[typ]])):
                    continue
                for k, fn in enumerate(FACE_NODES[typ]):
                    if set(e[i] for i in fn) == cs:
                        out.append((e[0], k + 1))
                        break
                break
        return out

    # ------------------------------------------------------------------ input file
    def write(self, path, title=""):
        L = ["** %s" % (title or "drawgen analysis"), "*HEADING", (title or "analysis")[:80]]
        def ids_lines(ids):
            ids = list(ids)
            return [", ".join(str(v) for v in ids[k:k + 16]) for k in range(0, len(ids), 16)]
        L.append("*NODE, NSET=NALL")
        for n in sorted(self.X):
            p = self.X[n]
            L.append("%d, %.9g, %.9g, %.9g" % (n, p[0], p[1], p[2]))
        for es, (typ, els) in self.elsets.items():
            L.append("*ELEMENT, TYPE=%s, ELSET=%s" % (typ, es))
            for e in els:
                vals = [str(v) for v in e]
                L.append(", ".join(vals[:16]) + ("," if len(vals) > 16 else ""))
                if len(vals) > 16:
                    L.append(", ".join(vals[16:]))
        beams = [i for i in self.members if i["kind"] == "beam"] + self.fasteners
        if beams:
            L.append("*USER ELEMENT, TYPE=U1, INTEGRATION POINTS=2, MAXDOF=6, NODES=2")
            for info in beams:
                L.append("*ELEMENT, TYPE=U1, ELSET=%s" % info["elset"])
                L += ["%d, %d, %d" % e for e in info["elems"]]
        for info in self.members:
            if info["kind"] == "rod":
                L.append("*ELEMENT, TYPE=T3D2, ELSET=%s" % info["elset"])
                L += ["%d, %d, %d" % e for e in info["elems"]]
        springs = [f for f in self.fasteners if f["spring"]]
        if springs:
            L.append("*ELEMENT, TYPE=SPRING1, ELSET=EPT")
            L += ["%d, %d" % (f["spring"], f["pt"]) for f in springs]
        if beams:
            L.append("*ELSET, ELSET=EU1")
            L += ids_lines(i["elset"] for i in beams)
        rods = [i for i in self.members if i["kind"] == "rod"]
        if rods:
            L.append("*ELSET, ELSET=EROD")
            L += ids_lines(i["elset"] for i in rods)
        mnodes = sorted(set(n for i in self.members + self.fasteners for e in i["elems"] for n in e[1:]) |
                        set(j for i in self.members for j in i["joint"].values()) |
                        set(f["pt"] for f in self.fasteners if f["pt"]))
        if mnodes:
            self.nsets["NMEMB"] = mnodes
        if self.rps:
            self.nsets["NRP"] = sorted(n for rp in self.rps.values() for n in (rp["ref"], rp["rot"]))
        for name, nodes in self.nsets.items():
            L.append("*NSET, NSET=%s" % name)
            L += ids_lines(nodes)
        for ns, a, b in self.transforms:
            L.append("*TRANSFORM, NSET=%s, TYPE=R" % ns)
            L.append("%.12g, %.12g, %.12g, %.12g, %.12g, %.12g" % (a[0], a[1], a[2], b[0], b[1], b[2]))
        mats = self.doc.get("materials") or {}
        for name, mset in self.mat_names.items():
            m = mats[name]
            L += ["*MATERIAL, NAME=%s" % mset, "*ELASTIC", "%.12g, %.6g" % (float(m.get("E") or 210000), float(m.get("nu") if m.get("nu") is not None else 0.3))]
            rho = float(m.get("rho") or 0) * 1e-12
            if rho > 0:
                L += ["*DENSITY", "%.6g" % rho]
        for es, bid, mname in self.body_sets:
            L.append("*SOLID SECTION, ELSET=%s, MATERIAL=%s" % (es, self.mat_names[mname]))
        for info in beams:
            s = info["sec"]
            L += ["*BEAM SECTION, ELSET=%s, MATERIAL=%s, SECTION=GENERAL" % (info["elset"], info["mset"]),
                  "%.9g, %.9g, 0., %.9g, %.6g" % (s["A"], s["Ia"], s["Ib"], KAPPA),
                  "%.12g, %.12g, %.12g" % tuple(info["e1"])]
        for info in rods:
            L += ["*SOLID SECTION, ELSET=%s, MATERIAL=%s" % (info["elset"], info["mset"]), "%.9g" % info["sec"]["A"]]
        if springs:
            L += ["*SPRING, ELSET=EPT", "1", "%.6E" % SPRING_K]
        if self.equations:
            L.append("*EQUATION")
            L += self.equations
        for ns, ref, rot in self.rigid:
            L.append("*RIGID BODY, NSET=%s, REF NODE=%d, ROT NODE=%d" % (ns, ref, rot))
        for t in self.ties:
            L.append("*SURFACE, NAME=%sS, TYPE=NODE" % t["name"])
            L.append(t["slave"])
            L.append("*SURFACE, NAME=%sM, TYPE=ELEMENT" % t["name"])
            L += ["%d, S%d" % fm for fm in t["master"]]
            L += ["*TIE, NAME=%s, POSITION TOLERANCE=%.6g, ADJUST=NO" % (t["name"], t["tol"]), "%sS, %sM" % (t["name"], t["name"])]
        if self.atype != "static":
            buck = self.atype == "buckling"
            L += ["*STEP", "*BUCKLE" if buck else "*FREQUENCY", "%d" % self.nmodes, "*BOUNDARY"]
            for sp in self.supports:
                for d in sp["dofs"]:
                    v = sp["values"].get(d, 0.0) if buck else 0.0
                    L.append("%s, %d, %d" % (sp["nset"], d, d) + (", %.12g" % v if v else ""))
                for d in (sp.get("rot") or {}).get("dofs") or []:
                    v = sp["rot"]["values"].get(d, 0.0) if buck else 0.0
                    L.append("%s, %d, %d" % (sp["rot"]["nset"], d, d) + (", %.12g" % v if v else ""))
            if buck:
                L.append("*CLOAD")
                for (n, d), v in sorted(self.cloads[1].items()):
                    if v != 0:
                        L.append("%d, %d, %.12g" % (n, d, v))
            L += ["*NODE FILE", "U", "*END STEP"]
            with open(path, "w") as f:
                f.write("\n".join(L) + "\n")
            return
        steps = [0, 1] if springs else [1]
        for st in steps:
            L += ["*STEP", "*STATIC"]
            L.append("*BOUNDARY, OP=NEW")
            for sp in self.supports:
                for d in sp["dofs"]:
                    v = sp["values"].get(d, 0.0) if st == 1 else 0.0     # prescribed displacements in the load step
                    L.append("%s, %d, %d" % (sp["nset"], d, d) + (", %.12g" % v if v else ""))
                for d in (sp.get("rot") or {}).get("dofs") or []:          # reference point rotations
                    v = sp["rot"]["values"].get(d, 0.0) if st == 1 else 0.0
                    L.append("%s, %d, %d" % (sp["rot"]["nset"], d, d) + (", %.12g" % v if v else ""))
            for f in springs:
                L.append("%d, 2, 6" % f["pt"])
                if st == 1:
                    L.append("%d, 1, 1" % f["pt"])
            cl = self.cloads[st]
            L.append("*CLOAD, OP=NEW")
            for (n, d), v in sorted(cl.items()):
                if v != 0:
                    L.append("%d, %d, %.12g" % (n, d, v))
            L += ["*NODE FILE", "U", "*EL FILE", "S"]
            if mnodes:
                L += ["*NODE PRINT, NSET=NMEMB", "U"]
            if beams:
                L += ["*EL PRINT, ELSET=EU1", "S"]
            if rods:
                L += ["*EL PRINT, ELSET=EROD", "S"]
            for sp in self.supports:
                L += ["*NODE PRINT, NSET=%s" % sp["nset"], "RF"]
                if sp.get("rot"):
                    L += ["*NODE PRINT, NSET=%s" % sp["rot"]["nset"], "RF"]
            if self.rps:
                L += ["*NODE PRINT, NSET=NRP", "U"]
            L.append("*END STEP")
        with open(path, "w") as f:
            f.write("\n".join(L) + "\n")

    def _member_loads(self):
        """Consistent nodal loads of the line loads (and the weight) of the members."""
        extra = self.cloads[1]
        self.eq_loads = eq = {}
        for info in self.members:
            q = info["q"]
            if not np.any(q):
                continue
            t = info["t"]
            for e, n1, n2 in info["elems"]:
                le = float(np.linalg.norm(self.X[n2] - self.X[n1]))
                for n in (n1, n2):
                    for d in range(3):
                        extra[(n, d + 1)] = extra.get((n, d + 1), 0.0) + q[d] * le / 2
                        eq[(n, d + 1)] = eq.get((n, d + 1), 0.0) + q[d] * le / 2
                if info["kind"] == "beam":
                    qp = q - np.dot(q, t) * t
                    m = le * le / 12 * np.cross(t, qp)
                    for d in range(3):
                        extra[(n1, d + 4)] = extra.get((n1, d + 4), 0.0) + m[d]
                        extra[(n2, d + 4)] = extra.get((n2, d + 4), 0.0) - m[d]
                        eq[(n1, d + 4)] = eq.get((n1, d + 4), 0.0) + m[d]
                        eq[(n2, d + 4)] = eq.get((n2, d + 4), 0.0) - m[d]


# --------------------------------------------------------------------------- result files

def read_frd(path, want=("DISP", "STRESS")):
    """Nodal results of a .frd file: {step: {name: {node: [values]}}} for the result blocks in want."""
    out = {}
    step = 1
    name = None
    cur = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith("    1PSTEP"):
                try:
                    step = int(line.split()[-1])
                except ValueError:
                    pass
                continue
            if line.startswith(" -4"):
                name = line[5:13].strip()
                cur = out.setdefault(step, {}).setdefault(name, {}) if name in want else None
                continue
            if cur is None:
                continue
            if line.startswith(" -1"):
                try:
                    nid = int(line[3:13])
                    s = line[13:].rstrip("\n")
                    cur[nid] = [float(s[k:k + 12]) for k in range(0, len(s), 12) if s[k:k + 12].strip()]
                except ValueError:
                    pass
            elif line.startswith(" -3"):
                cur = None
    return out


def read_frd_modes(path):
    """Displacement blocks of a .frd file in their order: [{node: [ux, uy, uz]}] (frequency and buckling steps
    write one block per mode; a buckling step writes the static block of the reference loads first)."""
    out = []
    cur = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith(" -4"):
                cur = {} if line[5:13].strip() == "DISP" else None
                if cur is not None:
                    out.append(cur)
                continue
            if cur is None:
                continue
            if line.startswith(" -1"):
                try:
                    s = line[13:].rstrip("\n")
                    cur[int(line[3:13])] = [float(s[k:k + 12]) for k in range(0, 36, 12)]
                except ValueError:
                    pass
            elif line.startswith(" -3"):
                cur = None
    return out


def read_eigen(path):
    """Eigenvalue tables of a .dat file: {"freq": [Hz], "factor": [buckling factors], "eff": [[mx, my, mz]] (t),
    "total": [mx, my, mz] (t, total effective mass)}."""
    out = {"freq": [], "factor": [], "eff": [], "total": None}
    sec = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if "E I G E N V A L U E   O U T P U T" in s:
                sec = "freq"; continue
            if "B U C K L I N G   F A C T O R" in s:
                sec = "factor"; continue
            if "T O T A L   E F F E C T I V E   M A S S" in s:
                sec = "total"; continue
            if "E F F E C T I V E   M O D A L   M A S S" in s:
                sec = "eff"; continue
            if s.startswith("P A R T I C I P") or s.startswith("S T E P") or s.startswith("MODE") or s.startswith("("):
                if s.startswith("P A R T I C I P") or s.startswith("S T E P"):
                    sec = None
                continue
            parts = s.split()
            try:
                if sec == "freq" and len(parts) >= 5:
                    out["freq"].append(float(parts[3]))
                elif sec == "factor" and len(parts) >= 2:
                    out["factor"].append(float(parts[1]))
                elif sec == "eff" and len(parts) >= 4 and parts[0] != "TOTAL":
                    out["eff"].append([float(v) for v in parts[1:4]])
                elif sec == "total" and len(parts) >= 3:
                    out["total"] = [float(v) for v in parts[:3]]
                    sec = None
            except ValueError:
                pass
    return out


def read_dat(path):
    """Blocks of a .dat file: {step: {(kind, set): rows}} with kind displacements | forces | stresses | total;
    rows: displacements/forces {node: [values]}, stresses [(elem, ip, [values])], total [values]."""
    out = {}
    step = 0
    kind = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("S T E P"):
                step = int(s.split()[-1])
                kind = None
                continue
            m = re.match(r"(displacements|forces|stresses|total force)\b.*for set (\S+)", s)
            if m:
                k = {"total force": "total"}.get(m.group(1), m.group(1))
                kind = (k, m.group(2))
                out.setdefault(step, {})[kind] = [] if k in ("stresses", "total") else {}
                continue
            if kind is None:
                continue
            parts = s.split()
            try:
                if kind[0] == "stresses":
                    out[step][kind].append((int(parts[0]), int(parts[1]), [float(v) for v in parts[2:]]))
                elif kind[0] == "total":
                    out[step][kind] = [float(v) for v in parts]
                else:
                    # "L": values in the local system of a *TRANSFORM (normal supports)
                    out[step][kind][int(parts[0])] = [float(v) for v in parts[1:] if v != "L"]
            except (ValueError, IndexError):
                kind = None
    return out


def von_mises(s):
    sxx, syy, szz, sxy, syz, szx = s[:6]
    return math.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2) + 3 * (sxy * sxy + syz * syz + szx * szx))


# --------------------------------------------------------------------------- results

def _beam_local(c):
    """U1 element output (one integration point) -> local section forces [N, V1, V2, T, M1, M2] (positive face)."""
    return np.array([c[0], -c[3], -c[4], c[5] / KAPPA, c[2], -c[1]])


class Results(object):
    """Results of a solved model: states "preload" (step 1, fasteners with preload), "loads" and "total"."""

    def __init__(self, model, frd, dat):
        self.m = model
        steps = sorted(dat)
        if not steps:
            raise AnalysisError("the solver wrote no results")
        pre = len(steps) == 2
        self.state_steps = {"total": steps}
        if pre:
            self.state_steps.update(preload=[steps[0]], loads=[steps[1]])
        self.frd, self.dat = frd, dat
        self.U = {}
        self.S = {}
        for st, ss in self.state_steps.items():
            U, S = {}, {}
            for k in ss:
                for n, v in ((frd.get(k) or {}).get("DISP") or {}).items():
                    U[n] = U.get(n, 0) + np.asarray(v[:3])
                for n, v in ((frd.get(k) or {}).get("STRESS") or {}).items():
                    S[n] = S.get(n, 0) + np.asarray(v[:6])
            Um = {}
            for k in ss:
                for n, v in ((dat.get(k) or {}).get(("displacements", "NMEMB")) or {}).items():
                    Um[n] = Um.get(n, 0) + np.asarray((list(v) + [0.0] * 6)[:6])
                for n, v in ((dat.get(k) or {}).get(("displacements", "NRP")) or {}).items():
                    Um[n] = Um.get(n, 0) + np.asarray((list(v) + [0.0] * 6)[:6])
            U.update(Um)
            self.U[st], self.S[st] = U, S
        if pre:
            for f in model.fasteners:
                us = [self.U["preload"].get(n) for n in [f["pt"]] + [n for e in f["elems"] for n in e[1:]]]
                if any(u is not None and np.linalg.norm(u[:3]) > model.diag for u in us):
                    raise AnalysisError("fastener %s: the preload has no reaction path (the clamped parts are not "
                                        "connected to each other; use bonded contact)" % f["name"])
        self.members = self._members()
        self.fasteners = self._fasteners()
        self.reactions = self._reactions()

    def _elem_forces(self, steps, elset):
        out = {}
        for k in steps:
            for e, ip, c in (self.dat.get(k) or {}).get(("stresses", elset)) or []:
                d = out.setdefault(e, [np.zeros(6), np.zeros(6)])
                d[ip - 1] = d[ip - 1] + _beam_local(c)
        return out

    def _beam_rows(self, info, steps, with_q):
        """Per element: section forces at s = 0, L/4, L/2, 3L/4, L (local: N, V1, V2, T, M1, M2)."""
        ef = self._elem_forces(steps, "EU1")
        rows = []
        q = info["q"] if with_q else np.zeros(3)
        t, e1, e2 = info["t"], info["e1"], info["e2"]
        R = np.vstack([t, e1, e2])
        for e, n1, n2 in info["elems"]:
            if e not in ef:
                continue
            le = float(np.linalg.norm(self.m.X[n2] - self.m.X[n1]))
            f0 = ef[e][0].copy()
            # consistent nodal loads of the line load at node 1 (not known to U1): force q le / 2, moment le^2/12 t x q
            qp = q - np.dot(q, t) * t
            m_eq = le * le / 12 * np.cross(t, qp)
            F0 = R.T @ f0[:3] + q * le / 2
            M0 = R.T @ f0[3:] + m_eq
            pts = []
            for s in (0.0, 0.25, 0.5, 0.75, 1.0):
                x = s * le
                F = F0 - q * x
                M = M0 - np.cross(t, F0 * x - q * x * x / 2)
                pts.append(np.concatenate([R @ F, R @ M]))
            rows.append({"e": e, "n1": n1, "n2": n2, "L": le, "f": pts})
        return rows

    def _stress(self, sec, f):
        N, V1, V2, T, M1, M2 = f
        if sec.get("round"):
            return abs(N) / sec["A"] + math.hypot(M1, M2) * sec["c1"] / sec["Ia"]
        s = abs(N) / sec["A"]
        if sec.get("c2"):
            s += abs(M1) * sec["c2"] / sec["Ib"]
        if sec.get("c1"):
            s += abs(M2) * sec["c1"] / sec["Ia"]
        return s

    def _members(self):
        out = []
        for info in self.m.members:
            res = {"name": info["name"], "kind": info["kind"], "section": section_label(info["m"].get("section") or {}),
                   "L": info["L"], "states": {}}
            for st, steps in self.state_steps.items():
                if info["kind"] == "beam":
                    rows = self._beam_rows(info, steps, with_q=(st != "preload"))
                else:
                    rows = []
                    sig = {}
                    for k in steps:
                        for e, ip, c in (self.dat.get(k) or {}).get(("stresses", "EROD")) or []:
                            if ip == 1:
                                sig[e] = sig.get(e, np.zeros(6)) + np.asarray(c[:6])
                    t = info["t"]
                    for e, n1, n2 in info["elems"]:
                        s = sig.get(e, np.zeros(6))
                        T = np.array([[s[0], s[3], s[4]], [s[3], s[1], s[5]], [s[4], s[5], s[2]]])
                        N = float(t @ T @ t) * info["sec"]["A"]
                        f = np.array([N, 0, 0, 0, 0, 0.0])
                        rows.append({"e": e, "n1": n1, "n2": n2, "L": float(np.linalg.norm(self.m.X[n2] - self.m.X[n1])),
                                     "f": [f, f, f, f, f]})
                env = np.zeros(6)
                smax = 0.0
                for r in rows:
                    for f in r["f"]:
                        env = np.where(np.abs(f) > np.abs(env), f, env)
                        smax = max(smax, self._stress(info["sec"], f))
                res["states"][st] = {"rows": rows, "max": env, "stress": smax}
            out.append(res)
        return out

    def _fasteners(self):
        out = []
        for info in self.m.fasteners:
            res = {"name": info["name"], "d": info["d"], "preload": info["preload"], "L": info["L"], "states": {}}
            for st, steps in self.state_steps.items():
                ef = self._elem_forces(steps, "EU1")
                N = V = M = T = 0.0
                for e, n1, n2 in info["elems"]:
                    for f in ef.get(e, []):
                        N = f[0] if abs(f[0]) > abs(N) else N
                        V = max(V, math.hypot(f[1], f[2]))
                        T = f[3] if abs(f[3]) > abs(T) else T
                        M = max(M, math.hypot(f[4], f[5]))
                A = info["sec"]["A"]
                res["states"][st] = {"N": N, "V": V, "M": M, "T": T,
                                     "stress": abs(N) / A + M * info["d"] / 2 / info["sec"]["Ia"]}
            out.append(res)
        return out

    def _node_elem_forces(self, steps, with_q):
        """Force and moment (global) exerted by the member elements on their nodes."""
        acc = {}
        def add(n, F, M):
            a = acc.setdefault(n, [np.zeros(3), np.zeros(3)])
            a[0] += F
            a[1] += M
        for info in self.m.members:
            R = np.vstack([info["t"], info["e1"], info["e2"]])
            if info["kind"] == "beam":
                for r in self._beam_rows(info, steps, with_q):
                    f0, fl = r["f"][0], r["f"][-1]
                    add(r["n1"], R.T @ f0[:3], R.T @ f0[3:])
                    add(r["n2"], -(R.T @ fl[:3]), -(R.T @ fl[3:]))
            # released ends: forces of the end node pass to the joint (translations and torsion)
            for end in ("a", "b"):
                r_, j = info["end_nodes"][end], info["joint"][end]
                if r_ != j and r_ in acc:
                    F, M = acc.pop(r_)
                    add(j, F, np.dot(M, info["t"]) * info["t"])
        return acc

    def _reactions(self):
        out = []
        for sp in self.m.supports:
            res = {"name": sp["name"], "states": {}}
            for st, steps in self.state_steps.items():
                F, Mo = np.zeros(3), np.zeros(3)
                nodes = sp["nodes"]
                c = sp["centre"]
                if sp.get("point"):
                    # reference point: force from the REF node, moment from the ROT node (loads at held DOFs removed)
                    for k in steps:
                        cl = self.m.cloads[self.load_index(k)]
                        dk = self.dat.get(k) or {}
                        for n, v in (dk.get(("forces", sp["nset"])) or {}).items():
                            F += np.array([v[i] - cl.get((n, i + 1), 0.0) if (i + 1) in sp["dofs"] else 0.0 for i in range(3)])
                        for n, v in (dk.get(("forces", sp["rot"]["nset"])) or {}).items():
                            Mo += np.array([v[i] - cl.get((n, i + 1), 0.0) if (i + 1) in sp["rot"]["dofs"] else 0.0 for i in range(3)])
                elif sp["member"]:
                    n = nodes[0]
                    acc = self._node_elem_forces(steps, with_q=(st != "preload"))
                    f, m = acc.get(n, [np.zeros(3), np.zeros(3)])
                    # rods at the node
                    for i, info in enumerate(self.m.members):
                        if info["kind"] != "rod":
                            continue
                        for r in self.members[i]["states"][st]["rows"]:
                            N = r["f"][0][0]
                            if r["n1"] == n:
                                f = f + N * info["t"]
                            if r["n2"] == n:
                                f = f - N * info["t"]
                    P = np.zeros(6)
                    for k in steps:
                        idx = self.load_index(k)
                        for d in range(6):
                            P[d] += self.m.cloads[idx].get((n, d + 1), 0.0)
                            if idx == 1:
                                P[d] -= self.m.eq_loads.get((n, d + 1), 0.0)
                    F = -P[:3] - f
                    Mo = -P[3:] - m
                    fixed = sp["dofs"]
                    F = np.array([F[i] if (i + 1) in fixed else 0.0 for i in range(3)])
                    Mo = np.array([Mo[i] if (i + 4) in fixed else 0.0 for i in range(3)])
                else:
                    # RF of the solver is the internal nodal force; loads applied at the fixed DOFs go to the support
                    for k in steps:
                        cl = self.m.cloads[self.load_index(k)]
                        rf = (self.dat.get(k) or {}).get(("forces", sp["nset"])) or {}
                        for n, v in rf.items():
                            v = np.asarray(v[:3], float)
                            p = np.array([cl.get((n, d), 0.0) for d in (1, 2, 3)])
                            if sp["trans"] is not None:
                                a, b = sp["trans"]
                                v = np.array([v[0] - np.dot(p, a), 0.0, 0.0])
                                v = v[0] * a
                            else:
                                fixed = self.m.spc.get(n, set())
                                v = np.array([v[i] - (p[i] if (i + 1) in fixed else 0.0) for i in range(3)])
                            F += v
                            Mo += np.cross(self.m.X[n] - c, v)
                res["states"][st] = {"F": F, "M": Mo, "point": c}
            out.append(res)
        return out

    def applied(self, st):
        """Total applied force of a state (concentrated loads, line loads, gravity on the bodies)."""
        steps = self.state_steps[st]
        tot = np.zeros(3)
        pts = set(f["pt"] for f in self.m.fasteners)
        for k in steps:
            idx = self.load_index(k)
            for (n, d), v in self.m.cloads[idx].items():
                if d <= 3 and n not in pts and n not in self.m.rp_rot_nodes:
                    tot[d - 1] += v
        return tot

    def load_index(self, k):
        """Load set of a solver step: 0 preload, 1 loads."""
        steps = self.state_steps["total"]
        return 0 if (len(steps) == 2 and k == steps[0]) else 1

    # ------------------------------------------------------------------ summaries
    def body_max(self, st):
        """Per body: max displacement magnitude and max von Mises stress with their node positions."""
        out = []
        for bid, mb in self.m.mesh["bodies"].items():
            nodes = set()
            for bl in mb["blocks"]:
                for e in bl["elements"]:
                    nodes.update(e[1:])
            U, S = self.U[st], self.S[st]
            umax, un, smax, sn = 0.0, None, 0.0, None
            for n in nodes:
                u = U.get(n)
                if u is not None:
                    v = float(np.linalg.norm(u[:3]))
                    if v > umax:
                        umax, un = v, n
                s = S.get(n)
                if s is not None:
                    v = von_mises(s)
                    if v > smax:
                        smax, sn = v, n
            out.append({"id": bid, "name": self.m.bodies[bid]["name"], "umax": umax,
                        "upos": self.m.X[un].tolist() if un else None, "smax": smax,
                        "spos": self.m.X[sn].tolist() if sn else None})
        return out

    def payload(self):
        """3D view data: exterior faces of the bodies (triangles), member lines and the nodal fields of the states,
        as base64 float32 / uint32 arrays."""
        import base64
        m = self.m
        count = {}
        for bid, mb in m.mesh["bodies"].items():
            for s in mb["surfaces"]:
                k = (len(s["nodes"]), tuple(s["nodes"][:8]), tuple(s["nodes"][-8:]))
                count[k] = count.get(k, 0) + 1
        idx, pos = {}, []
        def ix(n):
            if n not in idx:
                idx[n] = len(pos)
                pos.append(m.X[n])
            return idx[n]
        tris, bodies = [], []
        edges = set()                    # element edges of the facets (quadrangles without their diagonals)
        EDGE_LOOP = {3: (0, 1, 2), 4: (0, 1, 2, 3), 6: (0, 3, 1, 4, 2, 5), 8: (0, 4, 1, 5, 2, 6, 3, 7)}
        for bid, mb in m.mesh["bodies"].items():
            start = len(tris)
            for s in mb["surfaces"]:
                k = (len(s["nodes"]), tuple(s["nodes"][:8]), tuple(s["nodes"][-8:]))
                if count[k] > 1:
                    continue
                for f in s["facets"]:
                    loop = [ix(f[i]) for i in EDGE_LOOP.get(len(f), range(len(f)))]
                    for i in range(len(loop)):
                        a_, b_ = loop[i], loop[(i + 1) % len(loop)]
                        edges.add((a_, b_) if a_ < b_ else (b_, a_))
                    if len(f) == 6:
                        a, b, c, d, e, g = [ix(n) for n in f]
                        tris += [(a, d, g), (d, b, e), (g, e, c), (d, e, g)]
                    elif len(f) == 8:
                        a, b, c, d, e, g, h, k = [ix(n) for n in f]
                        tris += [(a, e, k), (e, b, g), (g, c, h), (k, h, d), (e, g, k), (g, h, k)]
                    elif len(f) == 4:
                        a, b, c, d = [ix(n) for n in f]
                        tris += [(a, b, c), (a, c, d)]
                    else:
                        a, b, c = [ix(n) for n in f[:3]]
                        tris.append((a, b, c))
            bodies.append({"id": bid, "name": m.bodies[bid]["name"], "start": start, "count": len(tris) - start})
        lines = []
        for info in m.members:
            lines.append({"kind": info["kind"], "name": info["name"], "segs": [[ix(a), ix(b)] for e, a, b in info["elems"]]})
        for info in m.fasteners:
            lines.append({"kind": "fastener", "name": info["name"], "segs": [[ix(a), ix(b)] for e, a, b in info["elems"]]})
        nodes = sorted(idx, key=lambda n: idx[n])
        body_nodes = set(n for mb in m.mesh["bodies"].values() for bl in mb["blocks"] for e in bl["elements"] for n in e[1:])
        b64 = lambda a, t: base64.b64encode(np.ascontiguousarray(a, dtype=t).tobytes()).decode("ascii")
        states = {}
        for st in self.state_steps:
            U = np.zeros((len(nodes), 3))
            vm = np.zeros(len(nodes))
            for i, n in enumerate(nodes):
                u = self.U[st].get(n)
                if u is not None:
                    U[i] = u[:3]
                s = self.S[st].get(n) if n in body_nodes else None
                if s is not None:
                    vm[i] = von_mises(s)
            # members: combined stress (|N| / A + bending, as the member table) at both ends of every segment, in
            # the order of the segments of "lines"; fasteners 0
            lvm = []
            for i, info in enumerate(m.members):
                se = {}
                mr = getattr(self, "members", None)
                if mr:
                    for r in mr[i]["states"][st]["rows"]:
                        se[r["e"]] = (self._stress(info["sec"], r["f"][0]), self._stress(info["sec"], r["f"][-1]))
                for e, a, b in info["elems"]:
                    lvm += list(se.get(e, (0.0, 0.0)))
            for info in m.fasteners:
                lvm += [0.0, 0.0] * len(info["elems"])
            lvm = np.asarray(lvm, float)
            states[st] = {"U": b64(U, np.float32), "vm": b64(vm, np.float32), "lvm": b64(lvm, np.float32),
                          "umax": float(np.linalg.norm(U, axis=1).max()) if len(U) else 0.0,
                          "vmmax": float(max(vm.max() if len(vm) else 0.0, lvm.max() if len(lvm) else 0.0))}
        return {"count": len(nodes), "pos": b64(np.asarray(pos) if pos else np.zeros((0, 3)), np.float32),
                "tri": b64(np.asarray(tris) if tris else np.zeros((0, 3)), np.uint32), "bodies": bodies,
                "edges": b64(np.asarray(sorted(edges)) if edges else np.zeros((0, 2)), np.uint32),
                "lines": lines, "states": states}

    def tables(self):
        """Result tables for the client (per state)."""
        out = {}
        for st in self.state_steps:
            out[st] = {
                "bodies": self.body_max(st),
                "members": [{"name": r["name"], "kind": r["kind"], "section": r["section"],
                             "max": [float(v) for v in r["states"][st]["max"]], "stress": r["states"][st]["stress"]}
                            for r in self.members],
                "fasteners": [{"name": r["name"], "d": r["d"], "preload": r["preload"],
                               **{k: float(v) for k, v in r["states"][st].items()}} for r in self.fasteners],
                "reactions": [{"name": r["name"], "F": r["states"][st]["F"].tolist(), "M": r["states"][st]["M"].tolist(),
                               "point": r["states"][st]["point"].tolist()} for r in self.reactions],
                "applied": self.applied(st).tolist(),
                "points": [{"name": rp["name"], "u": [float(x) for x in (self.U[st].get(rp["ref"]) if self.U[st].get(rp["ref"]) is not None else np.zeros(3))[:3]],
                            "rot": [float(x) for x in (self.U[st].get(rp["rot"]) if self.U[st].get(rp["rot"]) is not None else np.zeros(3))[:3]]}
                           for pid, rp in self.m.rps.items() if not pid.startswith("_sup_")],
            }
        return out


class ModeResults(object):
    """Results of a modal or buckling analysis: one state "m<k>" per mode with the mode shape normalised to a
    largest displacement of 1."""

    def __init__(self, model, blocks, eig):
        self.m = model
        self.kind = model.atype
        vals = eig["freq"] if self.kind == "modal" else eig["factor"]
        if not vals:
            raise AnalysisError("the solver wrote no %s" % ("frequencies" if self.kind == "modal" else "buckling factors"))
        blocks = blocks[-len(vals):] if len(blocks) >= len(vals) else blocks + [{}] * (len(vals) - len(blocks))
        self.values = vals
        self.eff = eig["eff"] if len(eig["eff"]) == len(vals) else None
        self.total = eig["total"]
        self.state_steps, self.U, self.S = {}, {}, {}
        for k, b in enumerate(blocks):
            st = "m%d" % (k + 1)
            U = {n: np.asarray(v[:3], float) for n, v in b.items() if n in model.X}
            mx = max([float(np.linalg.norm(u)) for u in U.values()] or [0.0])
            if mx > 0:
                U = {n: u / mx for n, u in U.items()}
            self.state_steps[st] = [k]
            self.U[st], self.S[st] = U, {}
        self.members, self.fasteners, self.reactions = [], [], []

    def modes(self):
        out = []
        for k, v in enumerate(self.values):
            r = {"mode": k + 1, "value": float(v)}
            if self.eff and self.total:
                r["eff"] = [float(x) for x in self.eff[k]]
                r["frac"] = [float(x / t) if t > 0 else 0.0 for x, t in zip(self.eff[k], self.total)]
            out.append(r)
        return out

    def body_max(self, st):
        return Results.body_max(self, st)

    def payload(self):
        return Results.payload(self)

    def tables(self):
        modes = self.modes()
        return {st: {"bodies": self.body_max(st), "mode": modes[k], "members": [], "fasteners": [], "reactions": [],
                     "applied": [0.0, 0.0, 0.0], "points": []} for k, st in enumerate(self.state_steps)}


# --------------------------------------------------------------------------- report

W = 96
STATE_TITLES = {"preload": "Step 1: fastener preload", "loads": "Step 2: loads (fastener lengths fixed)",
                "total": "Total (preload + loads)"}


def _rule(ch="-"):
    return ch * W


def _table(head, rows, widths):
    fmt = "".join("%%-%ds" % widths[0] if i == 0 else "%%%ds" % w for i, w in enumerate(widths))
    out = [fmt % tuple(head), _rule("-")[:sum(widths)]]
    for r in rows:
        out.append(fmt % tuple(r))
    return out


def _g(v, p=4):
    if v is None:
        return "-"
    return ("%." + str(p) + "g") % v


def report(res, meta):
    """Text report (96 columns) of a solved analysis."""
    m = res.m
    doc = m.doc
    L = [_rule("="), "ANALYSIS REPORT  %s" % meta.get("name", ""), _rule("=")]
    for k, v in (("Project", meta.get("project")), ("Geometry", meta.get("source")), ("Date", meta.get("date")),
                 ("Solver", meta.get("solver")), ("Input file", meta.get("inp")),
                 ("Mesh", "%d nodes, %d elements" % (meta.get("nodes", 0), meta.get("elements", 0)))):
        L.append("%-14s%s" % (k, v or "-"))
    L += ["%-14s%s" % ("Units", "N, mm, MPa, t/mm^3 (densities listed in kg/m^3)")]
    L += ["%-14s%s" % ("Analysis", ATYPE_NAMES[m.atype] + ("" if m.atype == "static" else ", %d modes requested" % m.nmodes)), ""]
    L += [_rule("="), "1  MODEL", _rule("=")]
    L += ["", "1.1  Materials"]
    L += _table(["Name", "E (MPa)", "nu", "rho (kg/m^3)"],
                [[n, _g(float(v.get("E") or 0), 6), _g(float(v.get("nu") or 0), 3), _g(float(v.get("rho") or 0), 5)]
                 for n, v in (doc.get("materials") or {}).items() if n in m.mat_names], [30, 16, 10, 16])
    L += ["", "1.2  Bodies"]
    rows = []
    for bid, mb in m.mesh["bodies"].items():
        b = m.bodies[bid]
        mname = next(mn for es, bb, mn in m.body_sets if bb == bid)
        els = " + ".join("%d %s" % (len(bl["elements"]), bl["type"]) for bl in mb["blocks"])
        rows.append([b["name"][:28], {"plate": "plate"}.get(b["mode"], "solid"), mname[:18], els[:24],
                     _g(float(b["shape"].volume), 6)])
    L += _table(["Body", "Model", "Material", "Elements", "Volume (mm^3)"], rows, [28, 8, 18, 26, 16])
    mo = doc.get("mesh") or {}
    L.append("Mesh: %s; element size %s mm; tetrahedra %s; hexahedra %s." % (
        {"tet": "free tetrahedra", "hex": "structured hexahedra", "hexsub": "hexahedra by subdivision"}.get(mo.get("strategy") or "tet"),
        _g(float(mo.get("size") or 0)) if mo.get("size") else "auto", mo.get("tet_type") or "C3D10", mo.get("hex_type") or "C3D8I"))
    if any(b["mode"] == "plate" for b in m.bodies.values()):
        L.append("Plates: swept mesh of C3D8I (and C3D6) elements through the thickness.")
    if m.ties:
        L.append("Plates and bodies of other mesh groups tied to touching bodies: %d tie constraint(s)." % len(m.ties))
    L.append("Bonded contact between touching solid bodies: %s." % ("yes (shared nodes)" if doc.get("bonded", True) else "no"))
    if m.members:
        L += ["", "1.3  Members"]
        rows = []
        for i in m.members:
            s = i["sec"]
            rows.append([i["name"][:20], i["kind"], section_label(i["m"].get("section") or {})[:22], _g(i["L"], 6),
                         _g(s["A"], 5), _g(s["Ia"], 5), _g(s["Ib"], 5), i["release"] or "-"])
        L += _table(["Member", "Kind", "Section", "L (mm)", "A (mm^2)", "I11 (mm^4)", "I22 (mm^4)", "Rel."], rows,
                    [20, 6, 24, 10, 10, 11, 11, 4])
        L.append("Beams: CalculiX U1 elements (Euler-Bernoulli); torsional stiffness G (I11 + I22).")
        L.append("I11 governs bending in the local 1-direction, I22 in the local 2-direction (section depth h).")
    if m.fasteners:
        L += ["", "1.4  Fasteners"]
        L += _table(["Fastener", "d (mm)", "Preload (N)", "L (mm)", "Elements"],
                    [[f["name"][:30], _g(f["d"], 4), _g(f["preload"], 6), _g(f["L"], 5), str(len(f["elems"]))]
                     for f in m.fasteners], [32, 12, 16, 12, 12])
        L.append("Fastener ends connected to the hole faces by RBE3 equations (weighted mean of the face nodes).")
    L += ["", "1.5  Supports"]
    dn = lambda s, d: "un" if s["trans"] is not None else ["ux", "uy", "uz", "rx", "ry", "rz"][d - 1]
    L += _table(["Support", "Target", "Held / prescribed DOF", "Nodes"],
                [[s["name"][:24], "member end" if s["member"] else "ref. point" if s.get("point") else "face",
                  " ".join([dn(s, d) + ("=%s" % _g(s["values"][d]) if s["values"].get(d) else "") for d in s["dofs"]] +
                           ["r" + "xyz"[d - 1] + ("=%s" % _g(s["rot"]["values"][d]) if s["rot"]["values"].get(d) else "")
                            for d in ((s.get("rot") or {}).get("dofs") or [])]),
                  str(len(s["nodes"]))] for s in m.supports], [26, 14, 40, 10])
    if m.rps:
        L += ["", "Reference points (*RIGID BODY: the connected face nodes move rigidly with the point; a face support "
                  "with rotations uses a point at the face centre)"]
        L += _table(["Point", "x (mm)", "y (mm)", "z (mm)", "Face nodes", "Member ends"],
                    [[rp["name"][:30]] + [_g(float(v), 6) for v in rp["xyz"]] + [str(len(rp["nodes"])), str(len(rp["joints"]))]
                     for rp in m.rps.values()], [32, 12, 12, 12, 12, 12])
    L += ["", "1.6  Loads"]
    rows = []
    for ld in m.loads:
        l = ld["l"]
        v = l.get("value")
        val = ("%s" % _g(v, 5)) if not isinstance(v, (list, tuple)) else "(" + ", ".join(_g(float(x), 5) for x in v) + ")"
        tot = ld.get("total")
        rows.append([ld["name"][:24], ld["type"], val[:30], "(" + ", ".join(_g(float(x), 5) for x in tot) + ")" if tot is not None else "-"])
    L += _table(["Load", "Type", "Value", "Total force (N)"], rows, [26, 10, 30, 30])
    if m.atype == "modal":
        L.append("The loads are not used in a modal analysis.")
    if isinstance(res, ModeResults):
        L += _mode_report(res)
        if m.warnings:
            L += ["", _rule("="), "WARNINGS", _rule("=")] + m.warnings
        L.append(_rule("="))
        return "\n".join(l[:W] if len(l) > W else l for l in L) + "\n"
    tables = res.tables()
    order = [st for st in ("preload", "loads", "total") if st in res.state_steps]
    for k, st in enumerate(order):
        tb = tables[st]
        title = STATE_TITLES[st] if len(order) > 1 else "Loads"
        L += ["", _rule("="), "2.%d  RESULTS  %s" % (k + 1, title), _rule("=")]
        L += ["", "Bodies"]
        L += _table(["Body", "max |u| (mm)", "at (x, y, z)", "max von Mises (MPa)"],
                    [[b["name"][:28], _g(b["umax"], 4), "(%s)" % ", ".join(_g(v, 5) for v in (b["upos"] or [])),
                      _g(b["smax"], 4)] for b in tb["bodies"]], [30, 14, 30, 20])
        if tb["members"]:
            L += ["", "Members: maximum section forces (local axes; N tension positive)"]
            L += _table(["Member", "N (N)", "V1 (N)", "V2 (N)", "T (N mm)", "M1 (N mm)", "M2 (N mm)", "sig (MPa)"],
                        [[r["name"][:18]] + [_g(v, 5) for v in r["max"]] + [_g(r["stress"], 4)] for r in tb["members"]],
                        [18, 11, 11, 11, 11, 12, 12, 10])
            L.append("sig = |N| / A + |M1| c2 / I22 + |M2| c1 / I11 (round sections: |N| / A + M r / I).")
        if tb["fasteners"]:
            L += ["", "Fasteners"]
            L += _table(["Fastener", "N (N)", "V (N)", "M (N mm)", "T (N mm)", "sig (MPa)"],
                        [[r["name"][:26], _g(r["N"], 6), _g(r["V"], 5), _g(r["M"], 5), _g(r["T"], 4), _g(r["stress"], 4)]
                         for r in tb["fasteners"]], [28, 13, 13, 14, 14, 12])
            L.append("sig = |N| / A + M d / (2 I) on the nominal diameter.")
        L += ["", "Reactions (moments about the support centre)"]
        rows = [[r["name"][:16]] + [_g(v, 5) for v in r["F"] + r["M"]] for r in tb["reactions"]]
        F = sum(np.asarray(r["F"]) for r in tb["reactions"]) if tb["reactions"] else np.zeros(3)
        rows.append(["Sum"] + [_g(float(v), 5) for v in F] + ["", "", ""])
        L += _table(["Support", "Fx (N)", "Fy (N)", "Fz (N)", "Mx (N mm)", "My (N mm)", "Mz (N mm)"], rows,
                    [16, 13, 13, 13, 13, 14, 14])
        ap = tb["applied"]
        L.append("Applied loads (N): (%s)" % ", ".join(_g(v, 6) for v in ap))
        L.append("Sum of reactions and applied loads (N): (%s)" % ", ".join(_g(float(F[i] + ap[i]), 3) for i in range(3)))
        if tb.get("points"):
            L += ["", "Reference points"]
            L += _table(["Point", "ux (mm)", "uy (mm)", "uz (mm)", "rx (rad)", "ry (rad)", "rz (rad)"],
                        [[r["name"][:16]] + [_g(v, 5) for v in r["u"] + r["rot"]] for r in tb["points"]],
                        [16, 13, 13, 13, 13, 14, 14])
    if m.warnings:
        L += ["", _rule("="), "WARNINGS", _rule("=")] + m.warnings
    L.append(_rule("="))
    return "\n".join(l[:W] if len(l) > W else l for l in L) + "\n"


def _mode_report(res):
    modes = res.modes()
    if res.kind == "modal":
        L = ["", _rule("="), "2  RESULTS  Natural frequencies", _rule("=")]
        if res.eff and res.total:
            rows = [[str(r["mode"]), _g(r["value"], 6)] + ["%.1f" % (100 * f) for f in r["frac"]] for r in modes]
            cum = np.sum([r["frac"] for r in modes], axis=0)
            rows.append(["Sum", ""] + ["%.1f" % (100 * f) for f in cum])
            L += _table(["Mode", "f (Hz)", "Eff. mass x (%)", "Eff. mass y (%)", "Eff. mass z (%)"], rows, [8, 16, 18, 18, 18])
            L.append("Effective modal mass as a percentage of the total effective mass (%s kg in x, y, z)." %
                     ", ".join(_g(t * 1000, 5) for t in res.total))
        else:
            L += _table(["Mode", "f (Hz)"], [[str(r["mode"]), _g(r["value"], 6)] for r in modes], [8, 16])
    else:
        L = ["", _rule("="), "2  RESULTS  Buckling factors", _rule("=")]
        L += _table(["Mode", "Buckling factor"], [[str(r["mode"]), _g(r["value"], 6)] for r in modes], [8, 18])
        L.append("Critical loads: buckling factor x the applied loads and prescribed displacements. A negative factor: "
                 "buckling under the reversed loads.")
    L += ["", "Mode shapes: displacements normalised to a largest value of 1 (CalculiX: mass-normalised for modal)."]
    rows = []
    for k, st in enumerate(res.state_steps):
        for b in res.body_max(st):
            rows.append([str(k + 1), b["name"][:30], _g(b["umax"], 4), "(%s)" % ", ".join(_g(v, 5) for v in (b["upos"] or []))])
    L += _table(["Mode", "Body", "max |u|", "at (x, y, z)"], rows, [8, 32, 12, 36])
    return L


# --------------------------------------------------------------------------- run

def _ccx_errors(text):
    out = []
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if "*ERROR" in l:
            out.append(" ".join(x.strip() for x in lines[i:i + 3]))
    return out


def run(doc, asm, sources, workdir, ccx, progress=None, mesh_only=False, meta=None, procs=None):
    """Meshes, writes the input file, runs CalculiX and reads the results. Returns {"payload", "tables", "report",
    "summary", "files"}; with mesh_only the mesh payload and the model summary."""
    from build123d import export_brep
    from . import femesh
    say = progress or (lambda *a: None)
    meta = dict(meta or {})
    os.makedirs(workdir, exist_ok=True)
    for fn in os.listdir(workdir):
        if fn.startswith("job.") or fn.endswith(".brep") or fn.startswith("solver") or fn.endswith("_report.txt"):
            try:
                os.remove(os.path.join(workdir, fn))
            except OSError:
                pass
    say("geometry", "Placing the bodies")
    bodies = geometry(doc, asm, sources)
    mopt = doc.get("mesh") or {}
    job = {"size": float(mopt.get("size") or 0), "bonded": bool(doc.get("bonded", True)), "bodies": [],
           "mesh": {k: mopt.get(k) for k in ("size_min", "curvature", "algorithm", "optimize", "strategy", "tet_type", "hex_type")
                    if mopt.get(k) is not None}}
    for b in bodies:
        p = os.path.join(workdir, "body_%s.brep" % re.sub(r"[^A-Za-z0-9]+", "_", b["id"]))
        export_brep(b["shape"], p)
        job["bodies"].append({"id": b["id"], "brep": p, "mode": b["mode"], "size": b["size"], "layers": b["layers"],
                              "normal": b.get("normal"), "strategy": b.get("strategy")})
    say("mesh", "Meshing %d bodies" % len(bodies))
    t0 = time.time()
    mesh = femesh.run(job) if bodies else {"nodes": {"ids": [], "xyz": []}, "bodies": {}, "warnings": []}
    say("model", "Building the model")
    M = Model(doc, bodies, mesh)
    M.build()
    inp = os.path.join(workdir, "job.inp")
    M.write(inp, meta.get("name") or "analysis")
    nel = sum(len(bl["elements"]) for b in mesh["bodies"].values() for bl in b["blocks"]) + \
        sum(len(i["elems"]) for i in M.members + M.fasteners)
    meta.update(nodes=len(M.X), elements=nel, inp=inp)
    summary = {"nodes": len(M.X), "elements": nel, "mesh_time": round(time.time() - t0, 2),
               "bodies": [{"id": bid, "name": M.bodies[bid]["name"],
                           "elements": sum(len(bl["elements"]) for bl in mb["blocks"]),
                           "types": [bl["type"] for bl in mb["blocks"]]} for bid, mb in mesh["bodies"].items()],
               "ties": len(M.ties), "warnings": M.warnings}
    if mesh_only:
        return {"payload": mesh_payload(M), "summary": summary, "files": {"inp": inp}}
    if not ccx:
        raise AnalysisError("CalculiX (ccx) not found: set the solver path in the analysis settings")
    say("solve", "Solving (%d nodes)" % len(M.X))
    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(procs or max(1, (os.cpu_count() or 2)))
    env["CCX_NPROC_STIFFNESS"] = env["OMP_NUM_THREADS"]
    log = os.path.join(workdir, "solver.log")
    t1 = time.time()
    with open(log, "w") as lf:
        p = subprocess.Popen([ccx, "-i", "job"], cwd=workdir, stdout=lf, stderr=subprocess.STDOUT, env=env,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if progress is not None and hasattr(progress, "proc"):
            progress.proc = p
        p.wait()
    with open(log, "r", errors="replace") as f:
        text = f.read()
    if "Job finished" not in text:
        errs = _ccx_errors(text)
        raise AnalysisError("solver failed: %s (see %s)" % ("; ".join(errs[:3]) or (text.strip().splitlines() or ["no output"])[-1], log))
    summary["solve_time"] = round(time.time() - t1, 2)
    say("results", "Reading the results")
    if M.atype == "static":
        frd = read_frd(os.path.join(workdir, "job.frd"))
        dat = read_dat(os.path.join(workdir, "job.dat"))
        res = Results(M, frd, dat)
    else:
        res = ModeResults(M, read_frd_modes(os.path.join(workdir, "job.frd")), read_eigen(os.path.join(workdir, "job.dat")))
    meta["solver"] = ccx
    rep = report(res, meta)
    rp = os.path.join(workdir, "%s_report.txt" % re.sub(r"[^A-Za-z0-9_\-.]+", "_", meta.get("name") or "analysis"))
    with open(rp, "w", encoding="utf-8") as f:
        f.write(rep)
    summary["atype"] = M.atype
    out = {"payload": res.payload(), "tables": res.tables(), "summary": summary, "states": list(res.state_steps),
           "atype": M.atype, "modes": res.modes() if M.atype != "static" else None,
           "files": {"inp": inp, "report": rp, "frd": os.path.join(workdir, "job.frd"), "dat": os.path.join(workdir, "job.dat"),
                     "log": log}}
    return out


def mesh_payload(M):
    """View data of the mesh without results."""
    class _R(object):
        pass
    r = _R()
    r.m = M
    r.state_steps = {}
    r.U, r.S = {}, {}
    return Results.payload(r)
