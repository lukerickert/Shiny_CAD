# -*- coding: utf-8 -*-
"""Static analysis with CalculiX (linear, or nonlinear with contact, plastic and hyperelastic materials and large
deformation): solid bodies, shells, plates, beams, rods and fasteners.

Analysis record (JSON, <name>.fea.json):
  {"name", "source": {"type": "assembly" | "part", "name"} or {"type": "inp", "path"} (inpmodel.py),
   "materials": {name: {"E": MPa, "nu", "rho": kg/m^3, "law": "elastic" | "plastic" | "hyper",
                        "hardening": "isotropic" | "kinematic", "plastic": [[yield stress MPa, plastic strain], ...],
                        "library": name in the material library (E, nu, rho and the hardening curve),
                        "hyper": "neohooke" | "mooney", "C10", "C01" (MPa), "D1" (1/MPa)}},
   "contacts": [{"id", "name", "type": "surface" | "node" | "tied", "master": [face refs], "slave": [face refs],
                 "slave_nset": node set id (node-to-surface and tied: the slave nodes), "friction": mu,
                 "stiffness": N/mm^3 (penalty slope; empty: 10 x the largest E per mm), "adjust": mm (slave nodes
                 within this distance moved onto the master), "tol": mm (tied: position tolerance)}],
   "nonlinear": {"nlgeom": bool, "inc0": first increment (fraction of the step), "incmin", "incmax", "maxinc":
                 number of increments, "every": output every n increments},
   "steps": [{"id", "name", "kind": "static" | "dynamic" (*DYNAMIC, implicit) | "explicit" (*DYNAMIC, EXPLICIT),
              "time": s (step time; static default 1), "inc0", "incmin", "incmax" (fractions of the step time),
              "maxinc", "every", "alpha" (dynamic: Hilber-Hughes-Taylor alpha, -1/3 .. 0, default -0.05)}]
              static analyses in sequence (default: one static step with the "nonlinear" settings); a support or
              load takes "steps": {step id: factor} (no map: factor 1 in every step; with a map: 0 in the steps not
              in it): a load is scaled by its factor (0: removed), a support with factor 0 is released and its
              prescribed values are scaled. Static steps ramp the loads from the values of the step before, dynamic
              steps apply them at once; a load with "amplitude" (id of "amplitudes") follows the amplitude over the
              step time (*AMPLITUDE),
   "amplitudes": [{"id", "name", "points": [[t (s, step time), factor], ...]}],
   "history": [{"id", "name", "kind": "node" | "element" | "contact" | "section", "target": {"nset": id} |
                {"point": id} | {"surface": id} | {"contact": id} (contact) | multi-item target (node: the nodes of it;
                element: "bodies" and "elements"; section: "faces" of solid bodies), "quantities": node: "U", "V", "RF";
                element: "S", "E", "PEEQ", "ENER" (internal energy), "EKIN" (kinetic energy); contact: "CF"; section:
                "SOF", "every": n}]
                time history output (*NODE PRINT, *EL PRINT): curves against time in the result ("time_history"),
   "initial_velocities": [{"id", "name", "target": {"nset": id} | multi-item target | {"bodies": [ids]},
                           "v": [vx, vy, vz] mm/s}]   *INITIAL CONDITIONS, TYPE=VELOCITY (dynamic steps),
   "default_material": name,
   "mesh": {"size": mm, "size_min": mm, "curvature": elements per 360 deg, "algorithm": "delaunay" | "frontal" | "hxt",
            "optimize": bool, "strategy": "tet" | "hex" | "hexsub", "tet_type": "C3D10" | "C3D4",
            "hex_type": "C3D8I" | "C3D8" | "C3D8R" | "C3D20" | "C3D20R",
            "shell_type": "S4" | "S8R" | "S3", "shell_algorithm": "quasi" | "frontal" | "delaunay" | "tri"}  (femesh.py)
   "bonded": true,                          touching solid bodies share nodes; plates are tied to touching bodies
   "bodies": {component id: {"mode": "solid" | "plate" | "off", "material", "size": mm, "layers": n,
                             "strategy": null (mesh default) | "tet" | "hex" | "hexsub"}},
   "shells": {"<component id>:<surface id>": {"mode": "shell" | "off", "t": mm, "offset": "mid" | "positive" |
              "negative", "material", "size": mm, "layers": n}},   surface bodies of the components (default: shell,
              10 mm); "layers" (also in "sections"): S8R written as *SHELL SECTION, COMPOSITE with n layers of t / n of
              the material (each layer with its own integration points through the thickness); other shells: 1 layer
   "members": [member], "plates": [plate], "fasteners": [fastener], "supports": [support], "loads": [load]}

Units: N, mm, MPa, t/mm^3 inside the solver; densities are entered in kg/m^3 and accelerations in mm/s^2.

Face reference: {"comp": component id, "face": index into the faces of the component shape (the solid and the surface
bodies, assembly.Sources)}. Edge reference: {"comp", "edge": index into the edges of the component shape}.
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
point:    {"id", "name", "xyz": [x, y, z], "coupling", "dofs", "faces", "edges", "nsets"}   reference point ("points"):
          coupled to the nodes of its faces, edges and node sets (constraints.py: rigid, kinematic, distributing or
          none); a node for the translations and a node whose translations are the rotations; member ends at the
          point follow it. Targets {"point": id} for supports (six components) and loads (force, moment).
          Springs, joints and equations: constraints.py.
          A member end connected to a face takes "coupling": "rigid" (face nodes rigid with the end) instead of RBE3.
support:  {"id", "name", "target": face reference | edge reference | {"member", "end": "a" | "b"} | {"point": id} |
          {"faces": [face refs], "edges": [edge refs], "bodies": [body ids]} (several items: the nodes of all) |
          {"surface": id} (the faces of a surface of doc["surfaces"], resolve_surfaces),
           "type": "fixed" | "pinned" | "normal" | "dofs" | "displacement" | "xsymm" | "ysymm" | "zsymm",
           "dofs": [ux, uy, uz, rx, ry, rz] (1 = held),
           "value": [ux, uy, uz, rx, ry, rz] (displacement: mm, rad) | mm (normal: along the outward normal)}
          face: fixed = ux, uy, uz; normal = displacement normal to a planar face (0, or "value"); dofs = the global
          components held at 0; displacement = the chosen global components prescribed to "value".
          member end and reference point: fixed = all six; pinned = ux, uy, uz; dofs; displacement.
          edge and face of a shell: fixed = all six, pinned, symmetry (x: ux ry rz, y: uy rx rz, z: uz rx ry), dofs,
          displacement; translations on all nodes, rotations on the shell nodes.
          Rotations (rx, ry, rz) on a face: the face is rigidly coupled to a node at its weighted centre (kinematic
          coupling) that carries the support.
          Prescribed displacements act in the load step (with a fastener preload step they are 0 in the preload step).
load:     {"id", "name", "type": "force" | "moment" | "pressure" | "gravity" | "line",
           "target": face reference | {"member", "end"} | {"member"} | edge reference (line) | {"faces": [face refs]}
           (force and moment over all faces by area, pressure on each) | {"edges": [edge refs]} (line), "value": [x, y, z] | p}
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

from . import constraints

KAPPA = 1.0e7       # U1 shear factor: Euler-Bernoulli beam (1e7: equilibrium to 1e-5 and section forces to 6 digits); the U1 torsion output is scaled by it
SPRING_K = 1.0e-6       # stiffness (N/mm) of the preload node to ground (the node needs one element)


CONTACT_TYPES = ("surface", "node", "tied")
MAX_INC_STATES = 40         # increments sent to the view (evenly spaced, the last always)


def library_material(name):
    """E, nu, rho (kg/m^3) and the hardening table [[stress, plastic strain]] of a library material (static
    curve; Johnson-Cook a + b eps^n sampled), or None."""
    from .explicit.constants import MATERIAL_LIBRARY
    e = MATERIAL_LIBRARY.get(name or "")
    if not e:
        return None
    out = {"E": float(e["E"]), "nu": float(e["nu"]), "rho": float(e.get("rho") or 0) * 1e12, "plastic": []}
    if e.get("curve"):
        pts = sorted((float(a), float(b)) for a, b in e["curve"])
        out["plastic"] = [[sg, ep] for ep, sg in pts]
    elif e.get("a") is not None:
        a, b, n = float(e["a"]), float(e.get("b") or 0), float(e.get("n") or 1)
        out["plastic"] = [[a + b * ep ** n if ep > 0 else a, ep] for ep in (0, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05, 0.075,
                                                                         0.1, 0.15, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0)]
    return out


def _shell_layers(cfg, what):
    """Number of layers of a shell or section (1 to 20)."""
    v = (cfg or {}).get("layers")
    if v in (None, ""):
        return 1
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        raise AnalysisError("%s: layers must be a whole number" % what)
    if not 1 <= n <= 20:
        raise AnalysisError("%s: layers must be 1 to 20" % what)
    return n


def library_list():
    from .explicit.constants import MATERIAL_LIBRARY
    out = []
    for k, e in MATERIAL_LIBRARY.items():
        if not e:
            continue
        m = library_material(k)
        from . import matcurve
        out.append({"name": k, "E": m["E"], "nu": m["nu"], "rho": m["rho"], "plastic": m["plastic"], "curves": matcurve.library(k)})
    return out


def material_values(m):
    """Material record with the library values applied: {"E", "nu", "rho", "law", "hardening", "plastic", ...}."""
    m = dict(m or {})
    lib = library_material(m.get("library")) if m.get("library") else None
    if lib:
        m.update(E=lib["E"], nu=lib["nu"], rho=lib["rho"])
        if (m.get("law") or "elastic") == "plastic" and lib["plastic"]:
            m["plastic"] = lib["plastic"]
    return m


def material_cards(m):
    """CalculiX material cards (after *MATERIAL) of a material record."""
    m = material_values(m)
    law = m.get("law") or "elastic"
    E = float(m.get("E") or 210000)
    nu = float(m.get("nu") if m.get("nu") is not None else 0.3)
    L = []
    if law == "hyper":
        c10, c01, d1 = float(m.get("C10") or 0), float(m.get("C01") or 0), float(m.get("D1") or 0)
        if c10 <= 0:
            raise AnalysisError("material: hyperelastic C10 must be positive")
        if (m.get("hyper") or "neohooke") == "mooney":
            L += ["*HYPERELASTIC, MOONEY-RIVLIN", "%.9g, %.9g, %.9g" % (c10, c01, d1)]
        else:
            L += ["*HYPERELASTIC, NEO HOOKE", "%.9g, %.9g" % (c10, d1)]
    else:
        L += ["*ELASTIC", "%.12g, %.6g" % (E, nu)]
        if law == "plastic":
            rows = [(float(a), float(b)) for a, b in (m.get("plastic") or []) if a is not None and b is not None]
            rows.sort(key=lambda r: r[1])
            if not rows or rows[0][1] != 0:
                raise AnalysisError("material: the plastic table must start at plastic strain 0 (the yield stress)")
            hard = "KINEMATIC" if m.get("hardening") == "kinematic" else "ISOTROPIC"
            L += ["*PLASTIC, HARDENING=%s" % hard] + ["%.9g, %.9g" % r for r in rows]
    rho = float(m.get("rho") or 0) * 1e-12
    if rho > 0:
        L += ["*DENSITY", "%.6g" % rho]
    return L


def face_bodies(bodies):
    """(component id, face index) -> body id of the bodies of geometry() (the first body listing the face)."""
    out = {}
    for b in bodies:
        keys = b.get("faces_by") or {(str(b.get("comp", b["id"])), int(fi)): 1 for fi in (b.get("faces") or {})}
        for k in keys:
            out.setdefault((str(k[0]), int(k[1])), b["id"])
    return out


def contact_body_pairs(doc, bodies):
    """Pairs of bodies (ids) with a contact pair between their faces: meshed apart (no shared nodes, femesh "apart")
    and not tied by the bonded ties."""
    fb = face_bodies(bodies)
    pairs = set()
    for c in doc.get("contacts") or []:
        A = set(fb.get((str(r.get("comp")), int(r.get("face", -1)))) for r in c.get("master") or [] if r)
        B = set(fb.get((str(r.get("comp")), int(r.get("face", -1)))) for r in c.get("slave") or [] if r)
        ns_ = next((x for x in doc.get("nsets") or [] if c.get("slave_nset") and str(x.get("id")) == str(c["slave_nset"])), None)
        if ns_ is not None and ns_.get("kind") == "faces":
            B |= set(fb.get((str(r.get("comp")), int(r.get("face", -1)))) for r in ns_.get("faces") or [] if r)
        elif ns_ is not None and ns_.get("kind") == "body":
            B |= set(str(x) for x in ns_.get("bodies") or [])
        for a in A:
            for b in B:
                if a and b and a != b:
                    pairs.add(tuple(sorted((a, b))))
    return sorted(pairs)


def contact_search(bodies, gap):
    """Faces of different bodies within gap (mm) of each other: [{"bodies": [a, b], "master": [refs], "slave": [refs]}]
    per pair of bodies; master: the side with the larger area of the faces found."""
    fb = {}
    for b in bodies:
        keys = b.get("faces_by") or {(str(b.get("comp", b["id"])), int(fi)): v for fi, v in (b.get("faces") or {}).items()}
        for k, tri in keys.items():
            A, B, C = (np.asarray(x, float) for x in tri)
            if not len(A):
                continue
            fb[(str(k[0]), int(k[1]))] = (b["id"], A, B, C, np.minimum(np.minimum(A, B), C).min(0), np.maximum(np.maximum(A, B), C).max(0),
                                          float(0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1).sum()))
    keys = sorted(fb)
    found = {}
    for i, ka in enumerate(keys):
        ba, A1, B1, C1, lo1, hi1, ar1 = fb[ka]
        P1 = (A1 + B1 + C1) / 3.0                  # triangle centres: faces that only meet along an edge are not pairs
        N1 = np.cross(B1 - A1, C1 - A1)
        for kb in keys[i + 1:]:
            bb, A2, B2, C2, lo2, hi2, ar2 = fb[kb]
            if ba == bb or (lo1 > hi2 + gap).any() or (lo2 > hi1 + gap).any():
                continue
            P2 = (A2 + B2 + C2) / 3.0
            N2 = np.cross(B2 - A2, C2 - A2)
            i1 = np.where(((P1 >= lo2 - gap) & (P1 <= hi2 + gap)).all(1))[0]
            i2 = np.where(((P2 >= lo1 - gap) & (P2 <= hi1 + gap)).all(1))[0]
            n1 = i1[_point_tri_dist(P1[i1], A2, B2, C2) <= gap] if len(i1) else i1
            n2 = i2[_point_tri_dist(P2[i2], A1, B1, C1) <= gap] if len(i2) else i2
            if not len(n1) and not len(n2):
                continue
            m1 = N1[n1].sum(0) if len(n1) else N1.sum(0)
            m2 = N2[n2].sum(0) if len(n2) else N2.sum(0)
            l1, l2 = np.linalg.norm(m1), np.linalg.norm(m2)
            if l1 > 0 and l2 > 0 and abs(np.dot(m1, m2)) / (l1 * l2) < 0.5:     # faces crossing at an angle
                continue
            pair = tuple(sorted((ba, bb)))
            e = found.setdefault(pair, {pair[0]: {}, pair[1]: {}})
            e[ba][ka] = ar1
            e[bb][kb] = ar2
    out = []
    for (a, b), sides in sorted(found.items()):
        aa, ab = sum(sides[a].values()), sum(sides[b].values())
        m, s_ = (a, b) if aa >= ab else (b, a)
        out.append({"bodies": [m, s_], "master": [{"comp": k[0], "face": k[1]} for k in sorted(sides[m])],
                    "slave": [{"comp": k[0], "face": k[1]} for k in sorted(sides[s_])]})
    return out


ATYPES = ("static", "modal", "buckling")
STEP_KINDS = ("static", "dynamic", "explicit")
B31_SECTIONS = ("RECT", "ROUND", "PIPE", "BOX")      # beam sections written as B31 in nonlinear and dynamic steps


def resolve_steps(doc):
    """Steps of an analysis: doc["steps"] with the defaults, or one static step from doc["nonlinear"]."""
    nl = doc.get("nonlinear") or {}

    def num(d, k, dflt):
        try:
            v = float(d.get(k))
            return v if v > 0 else dflt
        except (TypeError, ValueError):
            return dflt
    raw = doc.get("steps") or [{"id": "1", "name": "Step 1", "kind": "static"}]
    out = []
    for i, st in enumerate(raw):
        kind = st.get("kind") or "static"
        if kind not in STEP_KINDS:
            raise AnalysisError("step %s: unknown kind %s" % (st.get("name") or i + 1, kind))
        src = st if doc.get("steps") else nl
        try:
            alpha = float(st.get("alpha")) if st.get("alpha") not in (None, "") else -0.05
        except (TypeError, ValueError):
            alpha = -0.05
        out.append({"id": str(st.get("id") or i + 1), "name": st.get("name") or "Step %d" % (i + 1), "kind": kind,
                    "time": num(st, "time", 1.0 if kind == "static" else 0.01),
                    "inc0": num(src, "inc0", 0.1 if kind == "static" else 0.01), "incmin": num(src, "incmin", 1e-5),
                    "incmax": num(src, "incmax", 0.25 if kind == "static" else 0.05), "maxinc": int(num(src, "maxinc", 100 if kind == "static" else 10000)),
                    "every": int(num(src, "every", 1)), "alpha": max(-1.0 / 3, min(0.0, alpha))})
    return out


def support_dofs(s):
    """Held components [ux, uy, uz, rx, ry, rz] (1: held) of a support: from its type (fixed, pinned, xsymm, ysymm,
    zsymm), else its "dofs" (dofs, displacement, explicit supports; default ux uy uz). Raises AnalysisError for a
    normal support (a support of the CalculiX branch only)."""
    typ = s.get("type")
    if typ == "fixed":
        return [1, 1, 1, 1, 1, 1]
    if typ == "pinned":
        return [1, 1, 1, 0, 0, 0]
    if typ in SYMMETRY:
        return [1 if d in SYMMETRY[typ] else 0 for d in range(1, 7)]
    if typ == "normal":
        raise AnalysisError("support %s: a normal support is not available in the explicit model" % (s.get("name") or s.get("id")))
    return (list(s.get("dofs") or [1, 1, 1]) + [0, 0, 0, 0, 0, 0])[:6]


def step_factor(item, step_id):
    """Factor of a support or load in a step: 1 without a step map, else the map value (0 when not in it)."""
    m = item.get("steps")
    if not isinstance(m, dict):
        return 1.0
    try:
        return float(m.get(str(step_id), 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def amplitude_value(points, t):
    """Value of a tabular amplitude at time t (linear between the points, constant outside)."""
    P = sorted((float(a), float(b)) for a, b in points or [])
    if not P:
        return 1.0
    if t <= P[0][0]:
        return P[0][1]
    for (t0, v0), (t1, v1) in zip(P, P[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0) if t1 > t0 else v1
    return P[-1][1]
ATYPE_NAMES = {"static": "Linear static", "modal": "Modal (natural frequencies)", "buckling": "Linear buckling"}
MAX_MODES = 100


class AnalysisError(Exception):
    pass


MULTI_KEYS = ("faces", "edges", "bodies", "vertices", "nodes", "elements")


def is_multi(tgt):
    """A target of several items: {"faces": [face refs], "edges": [edge refs], "bodies": [body ids], "vertices":
    [{"comp", "vertex", "xyz"}] (the mesh node at each geometry vertex), "nodes": [mesh node ids], "elements": [mesh
    element ids]} (any of the keys)."""
    return isinstance(tgt, dict) and any(k in tgt for k in MULTI_KEYS)


def refine_boxes(doc, bodies):
    """Mesh refinement regions of the document (doc["refine"]: [{"id", "name", "faces": [face refs], "size": mm}]) as
    femesh boxes: one box per face (bounding box of its triangles, global), [{"box", "size"}]."""
    tri = {}
    for b in bodies:
        for fi, t in (b.get("faces") or {}).items():
            tri[(str(b.get("comp")), int(fi))] = t
        for key, t in (b.get("faces_by") or {}).items():
            tri[(str(key[0]), int(key[1]))] = t
    out = []
    for r in doc.get("refine") or []:
        try:
            sz = float(r.get("size") or 0)
        except (TypeError, ValueError):
            sz = 0.0
        if sz <= 0:
            continue
        for f in r.get("faces") or []:
            t = tri.get((str(f.get("comp")), int(f.get("face", -1))))
            if t is None:
                continue
            P = np.vstack([np.asarray(a, float).reshape(-1, 3) for a in t])
            out.append({"box": P.min(0).tolist() + P.max(0).tolist(), "size": sz})
    return out


def resolve_surfaces(doc):
    """The document with the surface references resolved (doc["surfaces"]: [{"id", "name", "faces"}]): a target
    {"surface": id} of a support, load or mass becomes {"faces": [...]}; "master_surface" / "slave_surface" of a contact
    pair give its master / slave faces. Raises AnalysisError for a surface that is not found or has no faces."""
    surfs = {str(f.get("id")): f for f in doc.get("surfaces") or []}
    if not surfs and not any(isinstance(x.get("target"), dict) and "surface" in x["target"]
                             for k in ("supports", "loads", "masses", "history") for x in doc.get(k) or []):
        return doc

    def faces(sid, what):
        f = surfs.get(str(sid))
        if f is None:
            raise AnalysisError("%s: surface %s not found" % (what, sid))
        if not f.get("faces"):
            raise AnalysisError("%s: surface %s has no faces" % (what, f.get("name") or sid))
        return [dict(r) for r in f["faces"]]
    out = dict(doc)
    for k in ("supports", "loads", "masses", "history"):
        lst = []
        for x in doc.get(k) or []:
            t = x.get("target")
            if isinstance(t, dict) and "surface" in t:
                x = dict(x, target={"faces": faces(t["surface"], "%s %s" % (k[:-1], x.get("name") or x.get("id")))})
            lst.append(x)
        if k in doc:
            out[k] = lst
    if doc.get("contacts"):
        cl = []
        for c in doc["contacts"]:
            c = dict(c)
            for side in ("master", "slave"):
                if c.get(side + "_surface"):
                    c[side] = faces(c[side + "_surface"], "contact %s %s" % (c.get("name") or c.get("id"), side))
            cl.append(c)
        out["contacts"] = cl
    return out


def single_target(tgt):
    """A multi-item target of one face or one edge as the plain face or edge reference; other targets unchanged."""
    if not is_multi(tgt):
        return tgt
    f, e, b, v, n, el = (list(tgt.get(k) or []) for k in MULTI_KEYS)
    if v or n or el:
        return tgt
    if len(f) == 1 and not e and not b:
        return dict(f[0])
    if len(e) == 1 and not f and not b:
        return dict(e[0])
    return tgt


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

DEFAULT_SHELL_T = 10.0      # mm, thickness of a shell without one


def geometry(doc, asm, sources):
    """Bodies of the analysis: [{"id", "name", "shape" (placed), "mode", "material", "size", "layers",
    "faces": {index: (A, B, C) triangle corner arrays, global}, "refs": face refs (local), "comp": component id,
    "full": placed component shape (solid and surface bodies; face and edge indices of references)}].
    The solid of a component is the body with the component id (mode solid | plate); each surface body of the
    component that is not off is a shell body "<component id>:<surface id>" with "t" (mm) and "offset"."""
    from . import assembly
    out = []
    bcfg = doc.get("bodies") or {}
    scfg = doc.get("shells") or {}
    placed = {}
    surf_faces = {}                 # (component id, face index) -> (triangles, placed face, common, component name)
    surf_of = {}                    # (component id, face index) -> surface body "<component id>:<surface id>"
    # faces of a section (an off section: its faces are left out, not meshed with their surface body)
    in_section = set((str(r.get("comp")), int(r.get("face", -1))) for sec in doc.get("sections") or []
                     for r in sec.get("faces") or [])
    for c in asm.get("components") or []:
        cid = str(c.get("id"))
        cfg = bcfg.get(cid) or {}
        mode = cfg.get("mode") or "solid"
        if c.get("visible") is False and not cfg.get("mode") and not any(k.split(":")[0] == cid for k in scfg):
            continue
        src = c.get("source") or {}
        full, err = sources.load(src)
        if full is None and src.get("type") == "part" and (err or "").endswith("has no solid"):
            continue                                   # a part with sketches only: geometry for members and plates
        if full is None:
            raise AnalysisError("component %s: %s" % (c.get("name") or cid, err or "no solid"))
        solid, surfs = sources.parts(src)
        info = sources.info(src)
        t = assembly.trsf_of(c)
        M = np.array([[t.Value(i, j) for j in (1, 2, 3, 4)] for i in (1, 2, 3)])
        mesh = info["mesh"]
        V = np.asarray(mesh["vertices"], float).reshape(-1, 3) @ M[:, :3].T + M[:, 3]
        T = np.asarray(mesh["triangles"], int).reshape(-1, 3)
        fot = np.asarray(mesh["face_of_tri"], int)
        fb = mesh.get("face_body") or []
        faces = {}
        for fi in np.unique(fot):
            tt = T[fot == fi]
            faces[int(fi)] = (V[tt[:, 0]], V[tt[:, 1]], V[tt[:, 2]])
        bb = mesh.get("bbox") or [0, 0, 0, 1, 1, 1]
        diag = math.sqrt(sum((bb[i + 3] - bb[i]) ** 2 for i in range(3))) or 1.0
        pf = assembly.place(full, c)
        placed[cid] = pf
        common = {"comp": cid, "full": pf, "refs": info.get("refs") or [], "tol": max(diag / 2000.0, 0.005), "M": M}
        cname = c.get("name") or cid
        if solid is not None and mode != "off":
            out.append(dict(common, id=cid, name=cname, shape=assembly.place(solid, c), mode=mode,
                            material=cfg.get("material") or doc.get("default_material"), size=cfg.get("size"),
                            layers=cfg.get("layers") or 1, strategy=cfg.get("strategy"),
                            faces={fi: v for fi, v in faces.items() if fi >= len(fb) or fb[fi] is None}))
        pfaces = pf.faces() if surfs else []
        for fi, v in faces.items():
            if fi < len(fb) and fb[fi] is not None:
                surf_faces[(cid, fi)] = (v, pfaces[fi] if fi < len(pfaces) else None, common, cname)
                if fb[fi] < len(surfs):
                    surf_of[(cid, fi)] = "%s:%s" % (cid, surfs[fb[fi]][0])
        for k, (sid, sname, _col, sh) in enumerate(surfs):
            key = "%s:%s" % (cid, sid)
            sc = scfg.get(key) or {}
            if (sc.get("mode") or "shell") == "off":
                continue
            th = float(sc.get("t") or doc.get("shell_t") or DEFAULT_SHELL_T)
            if th <= 0:
                raise AnalysisError("shell %s / %s: thickness must be positive" % (cname, sname))
            own = {fi: v for fi, v in faces.items() if fi < len(fb) and fb[fi] == k and (cid, fi) not in in_section}
            if not own:
                continue                               # all faces in sections
            whole = len(own) == sum(1 for fi in range(len(fb)) if fb[fi] == k)
            shape = assembly.place(sh, c) if whole else _faces_shape([pfaces[fi] for fi in own])
            out.append(dict(common, id=key, name="%s / %s" % (cname, sname), shape=shape, mode="shell",
                            material=sc.get("material") or doc.get("default_material"), size=sc.get("size"), layers=1,
                            strategy=None, t=th, offset=sc.get("offset") or "mid", faces=own,
                            shell_layers=_shell_layers(sc, "shell %s / %s" % (cname, sname))))

    # sections: faces of the surface bodies of any components with one thickness, material, offset and size
    used = set()
    for sec in doc.get("sections") or []:
        if (sec.get("mode") or "shell") == "off":
            continue
        name = sec.get("name") or sec.get("id")
        fby, shapes, comps, fulls = {}, [], [], {}
        for r in sec.get("faces") or []:
            key = (str(r.get("comp")), int(r.get("face", -1)))
            if key not in surf_faces or key in used:
                continue
            tri, pfc, common, _cn = surf_faces[key]
            used.add(key)
            fby[key] = tri
            shapes.append(pfc)
            if key[0] not in comps:
                comps.append(key[0])
            fulls[key[0]] = common
        if not fby:
            continue
        th = float(sec.get("t") or doc.get("shell_t") or DEFAULT_SHELL_T)
        if th <= 0:
            raise AnalysisError("section %s: thickness must be positive" % name)
        c0 = fulls[comps[0]]
        out.append({"id": "sec:%s" % sec.get("id"), "name": name, "shape": _faces_shape(shapes), "mode": "shell",
                    "material": sec.get("material") or doc.get("default_material"), "size": sec.get("size"),
                    "layers": 1, "strategy": None, "t": th, "offset": sec.get("offset") or "mid",
                    "shell_layers": _shell_layers(sec, "section %s" % name),
                    "comp": comps[0], "comps": comps, "fulls": {k: v["full"] for k, v in fulls.items()},
                    "full": c0["full"], "refs": [], "tol": max(v["tol"] for v in fulls.values()), "M": c0["M"],
                    "faces_by": fby, "faces": {}, "surf_of": {k: surf_of.get(k) for k in fby}})

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
    for p in resolve_plate_groups(doc):
        out.append(plate_body(p, placed_shape, doc))
    if not out and not (doc.get("members") or []):
        raise AnalysisError("no bodies, plates or members")
    return out


def _fmt_coord(x):
    if abs(x) < 1e-6:
        x = 0.0
    t = ("%.1f" % x).rstrip("0").rstrip(".")
    return t.replace("-", "M").replace(".", "P") or "0"


def shell_groups(asm, sources, angle_deg=1.0):
    """Groups of the faces of the surface bodies of an assembly (step2shell "By geometry"): connected faces (touching
    within the tolerance) on the same plane, within angle_deg, or on the same cylinder form one group. Names:
    PLATE_Z0 (plane normal to z at z = 0), WEB_X1500 (plane normal to x or y), PLANE, CYL_R800 (cylinder of radius
    800 mm), SURF; a second group with the same name gets _2. Returns [{"name", "faces": [face references],
    "area"}], the largest area first."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from . import assembly
    items = []
    for c in asm.get("components") or []:
        if c.get("visible") is False:
            continue
        src = c.get("source") or {}
        full, _err = sources.load(src)
        if full is None:
            continue
        fb = (sources.info(src).get("mesh") or {}).get("face_body") or []
        if not any(v is not None for v in fb):
            continue
        pf = assembly.place(full, c)
        for fi, fc in enumerate(pf.faces()):
            if fi >= len(fb) or fb[fi] is None:
                continue
            ad = BRepAdaptor_Surface(fc.wrapped)
            t = ad.GetType()
            rec = {"ref": {"comp": str(c.get("id")), "face": fi}, "face": fc, "area": fc.area, "kind": "other"}
            if t == GeomAbs_Plane:
                ax = ad.Plane().Axis()
                n = _unit([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
                L = ax.Location()
                rec.update(kind="plane", n=n, d=float(np.dot(n, [L.X(), L.Y(), L.Z()])))
            elif t == GeomAbs_Cylinder:
                cy = ad.Cylinder()
                ax = cy.Axis()
                rec.update(kind="cylinder", p=np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()]),
                           a=_unit([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()]), r=cy.Radius())
            bb = fc.bounding_box()
            rec["bb"] = (np.array([bb.min.X, bb.min.Y, bb.min.Z]), np.array([bb.max.X, bb.max.Y, bb.max.Z]))
            items.append(rec)
    if not items:
        return []
    lo = np.min([r["bb"][0] for r in items], axis=0)
    hi = np.max([r["bb"][1] for r in items], axis=0)
    tol = max(float(np.linalg.norm(hi - lo)) * 1e-5, 1e-6)
    cos_lim = math.cos(math.radians(angle_deg))

    def same(a, b):
        if a["kind"] != b["kind"]:
            return False
        if a["kind"] == "plane":
            dot = float(np.dot(a["n"], b["n"]))
            return abs(dot) > cos_lim and abs(a["d"] - (b["d"] if dot > 0 else -b["d"])) < tol * 10
        if a["kind"] == "cylinder":
            if abs(a["r"] - b["r"]) > tol * 10 or abs(float(np.dot(a["a"], b["a"]))) < cos_lim:
                return False
            w = b["p"] - a["p"]
            return float(np.linalg.norm(w - np.dot(w, a["a"]) * a["a"])) < tol * 10
        return False
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if find(i) == find(j) or not same(a, b):
                continue
            if (a["bb"][1] < b["bb"][0] - tol * 10).any() or (b["bb"][1] < a["bb"][0] - tol * 10).any():
                continue
            ex = BRepExtrema_DistShapeShape(a["face"].wrapped, b["face"].wrapped)
            if ex.IsDone() and ex.Value() <= tol * 10:
                parent[max(find(i), find(j))] = min(find(i), find(j))
    groups = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    out, used = [], {}
    for g in sorted(groups.values(), key=lambda g: -sum(items[i]["area"] for i in g)):
        f = items[g[0]]
        base = "SURF"
        if f["kind"] == "plane":
            n = f["n"]
            ax = int(np.argmax(np.abs(n)))
            if abs(n[ax]) > 0.999:
                base = ("PLATE" if ax == 2 else "WEB") + "_" + "XYZ"[ax] + _fmt_coord(f["d"] / n[ax])
            else:
                base = "PLANE"
        elif f["kind"] == "cylinder":
            base = "CYL_R" + _fmt_coord(f["r"])
        k = used.get(base, 0) + 1
        used[base] = k
        out.append({"name": base if k == 1 else "%s_%d" % (base, k), "faces": [items[i]["ref"] for i in g],
                    "area": sum(items[i]["area"] for i in g)})
    return out


def _faces_shape(faces):
    """One shape of the faces (a compound)."""
    from build123d import Shape
    from . import model
    return Shape.cast(model.compound([f.wrapped for f in faces if f is not None], always=True))


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
        _, sv, vt = np.linalg.svd(pts - c, full_matrices=False)
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
    return {"id": "plate_" + str(p.get("id")), "comp": "plate_" + str(p.get("id")), "full": sol,
            "name": p.get("name") or str(p.get("id")), "shape": sol, "mode": "plate",
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
NCORNER = {"C3D4": 4, "C3D10": 4, "C3D8I": 8, "C3D8": 8, "C3D8R": 8, "C3D20": 8, "C3D20R": 8, "C3D6": 6, "C3D15": 6,
           "S4": 4, "S4R": 4, "S8R": 4, "S3": 3, "S6": 3}
SHELL_ELEMS = ("S4", "S4R", "S8R", "S3", "S6")
# consistent nodal fractions of a uniform surface load on a shell element (corners, then mid-side nodes)
SHELL_FRACTIONS = {"S4": [0.25] * 4, "S4R": [0.25] * 4, "S3": [1.0 / 3] * 3, "S8R": [-1.0 / 12] * 4 + [1.0 / 3] * 4,
                   "S6": [0.0] * 3 + [1.0 / 3] * 3}
# expanded 3D element of CalculiX: node positions of the bottom / top layers for the shell nodes (corners, mid-sides)
SHELL_EXPANSION = {"S4": [(0, 4), (1, 5), (2, 6), (3, 7)], "S4R": [(0, 4), (1, 5), (2, 6), (3, 7)],
                   "S3": [(0, 3), (1, 4), (2, 5)],
                   "S8R": [(0, 4), (1, 5), (2, 6), (3, 7), (8, 12), (9, 13), (10, 14), (11, 15)],
                   "S6": [(0, 3), (1, 4), (2, 5), (6, 9), (7, 10), (8, 11)]}
SHELL_OFFSET = {"mid": 0.0, "positive": 0.5, "negative": -0.5}
SYMMETRY = {"xsymm": [1, 5, 6], "ysymm": [2, 4, 6], "zsymm": [3, 4, 5]}
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
        self._layer_warned = set()
        self.equations = []             # input lines
        self.dependent = set()          # (node, dof)
        self.spc = {}                   # node -> set of dofs (global, or local for transformed nodes)
        self.transforms = []            # (nset name, a, b)
        self.nsets, self.elsets = {}, {}
        self.cloads = [{}, {}]          # step index (0: preload, 1: loads) -> {(node, dof): value}
        self._vis = None                # {(node, dof): value} of the load being applied (view data)
        self.load_vis = []              # [{"id", "name", "type", "nodal": {(node, dof): value}, "value"}]
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
        self.rot_used = set()           # rotation nodes of reference points used by a coupling, spring, joint or equation
        self.user_springs = []          # [{"elset", "type": SPRING1 | SPRING2, "elem", "dofs", "k"}]
        self.spring_vis, self.joint_vis = [], []
        self.extra_fix = []             # (node, first dof, last dof) held in every step
        self.face_body = {}             # (component id, face index) -> body id
        for bid, b in self.bodies.items():
            if not b.get("faces_by"):
                b["faces_by"] = {(str(b.get("comp", bid)), int(fi)): v for fi, v in (b.get("faces") or {}).items()}
            for key in b["faces_by"]:
                self.face_body.setdefault(key, bid)
        self.shell_nodes = set(n for bid, mb in mesh["bodies"].items() for bl in mb["blocks"] if bl["type"] in SHELL_ELEMS
                               for e in bl["elements"] for n in e[1:])
        self.edge_cache = {}
        self.atype = doc.get("analysis_type") or "static"      # static | modal | buckling
        if self.atype not in ATYPES:
            raise AnalysisError("unknown analysis type %s" % self.atype)
        self.nmodes = max(1, min(MAX_MODES, int(doc.get("modes") or 6)))
        self.b31 = False                # beams written as B31 (nonlinear or dynamic steps)
        self.user_steps = resolve_steps(doc) if self.atype == "static" else []
        self.load_parts = []            # per load: {"id", "nodal": {(node, dof): v}, "dq": {member index: q}, "amp", "f": [factor per step]}
        self.amplitudes = {str(a.get("id")): a for a in doc.get("amplitudes") or []}
        self.step_cloads = None         # several steps, factors or amplitudes: [{amplitude id or None: {(node, dof): v}}] per step
        self.step_q = None              # member line loads per step: [[q per member]]
        self.ivel = []                  # initial velocities: (nset, [vx, vy, vz])
        self.contact_defs = []          # [{"name", "type", "master": [(elem, label)], "slave": ..., ...}] (_contacts)
        self.contact_bodies = set(frozenset(p) for p in contact_body_pairs(doc, bodies))

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
        bid = self.face_body.get(key)
        if bid is None:
            if not any(str(b.get("comp", i)) == key[0] for i, b in self.bodies.items()):
                raise AnalysisError("face %s of component %s: the component is not in the analysis" % (key[1], key[0]))
            raise AnalysisError("face %s of component %s: its body is off or the face is not found" % (key[1], key[0]))
        b = self.bodies[bid]
        tri = b["faces_by"][key]
        mb = self.mesh["bodies"].get(bid)
        if mb is None:
            raise AnalysisError("face %s of %s: the body has no mesh" % (key[1], b["name"]))
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
        res = {"nodes": sorted(nodes), "w": w, "facets": facets, "area": sum(w.values()), "body": bid,
               "shell": b.get("mode") == "shell"}
        self.face_cache[key] = res
        return res

    def faces_merged(self, refs):
        """Nodes, area weights and facets of several faces as one face (weights of shared nodes added)."""
        nodes, w, facets = set(), {}, []
        for r in refs:
            f = self.face(r)
            nodes.update(f["nodes"])
            for n, v in f["w"].items():
                w[n] = w.get(n, 0.0) + v
            facets += f["facets"]
        return {"nodes": sorted(nodes), "w": w, "facets": facets, "area": sum(w.values())}

    def face_near(self, face, p, r, what):
        """The part of a face within distance r of point p (nodes and weights)."""
        ids = [n for n in face["nodes"] if np.linalg.norm(self.X[n] - p) <= r]
        w = {n: face["w"][n] for n in ids if n in face["w"]}
        if len([n for n in w if w[n] > 0]) < 3:
            raise AnalysisError("%s: fewer than 3 face nodes within the connection radius %g mm" % (what, r))
        return dict(face, nodes=ids, w=w, area=sum(w.values()))

    def face_normal_out(self, ref, f):
        """Outward unit normal of a facet (sign from the nearest triangle of the CAD face)."""
        key = (str(ref["comp"]), int(ref["face"]))
        A, B, C = self.bodies[self.face_body[key]]["faces_by"][key]
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

    def edge(self, ref):
        """Mesh nodes on a referenced edge of a component, in their order along the edge: {"nodes", "w" (tributary
        length per node, mm), "length" (mm), "centre"}. The nodes are those of the meshed bodies of the component
        within half the view tolerance of the edge curve."""
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GCPnts import GCPnts_QuasiUniformDeflection
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp
        from OCP.TopoDS import TopoDS
        try:
            from OCP.TopTools import TopTools_IndexedMapOfShape
        except ImportError:
            from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
        key = (str(ref.get("comp")), int(ref.get("edge", -1)))
        if key in self.edge_cache:
            return self.edge_cache[key]
        chains = self.mesh.get("edges")
        if chains is not None:       # mesh of an .inp: the node chains of the edges (inpmodel)
            ch = chains.get("%s:%d" % key)
            if ch is None:
                raise AnalysisError("edge %s of component %s not found" % (key[1], key[0]))
            ids = [int(n) for n in ch if int(n) in self.X]
            closed = len(ids) > 2 and ids[0] == ids[-1]
            if closed:
                ids = ids[:-1]
            if len(ids) < 2:
                raise AnalysisError("edge %s of component %s: no mesh nodes found on the edge" % (key[1], key[0]))
            Y = np.asarray([self.X[n] for n in ids])
            segl = np.linalg.norm(Y[1:] - Y[:-1], axis=1)
            if closed:
                segl = np.append(segl, np.linalg.norm(Y[0] - Y[-1]))
            w = np.zeros(len(ids))
            w[:-1] += segl[:len(ids) - 1] / 2
            w[1:] += segl[:len(ids) - 1] / 2
            if closed:
                w[-1] += segl[-1] / 2
                w[0] += segl[-1] / 2
            res = {"nodes": ids, "w": {n: float(x) for n, x in zip(ids, w)}, "length": float(segl.sum()),
                   "centre": (w[:, None] * Y).sum(0) / max(w.sum(), 1e-30)}
            self.edge_cache[key] = res
            return res
        bs = [b for b in self.bodies.values() if str(b.get("comp")) == key[0] or key[0] in (b.get("comps") or ())]
        if not bs:
            raise AnalysisError("edge %s of component %s: the component is not in the analysis" % (key[1], key[0]))
        full = next((b["full"] for b in bs if str(b.get("comp")) == key[0]), None) or bs[0]["fulls"][key[0]]
        emap = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(full.wrapped, TopAbs_EDGE, emap)
        if not 0 <= key[1] < emap.Extent():
            raise AnalysisError("edge %s of component %s not found" % (key[1], key[0]))
        to_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
        ad = BRepAdaptor_Curve(to_edge(emap.FindKey(key[1] + 1)))
        tol = bs[0]["tol"]
        disc = GCPnts_QuasiUniformDeflection(ad, tol / 4.0)
        if disc.IsDone() and disc.NbPoints() >= 2:
            P = np.array([[disc.Value(i).X(), disc.Value(i).Y(), disc.Value(i).Z()] for i in range(1, disc.NbPoints() + 1)])
        else:
            u0, u1 = ad.FirstParameter(), ad.LastParameter()
            P = np.array([[q.X(), q.Y(), q.Z()] for q in (ad.Value(u0 + (u1 - u0) * i / 64.0) for i in range(65))])
        closed = float(np.linalg.norm(P[0] - P[-1])) <= max(tol, 1e-9)
        nodes = sorted(set(n for b in bs for bl in (self.mesh["bodies"].get(b["id"]) or {}).get("blocks", [])
                           for e in bl["elements"] for n in e[1:]))
        if not nodes:
            raise AnalysisError("edge %s of component %s: the bodies of the component have no mesh" % (key[1], key[0]))
        thr = 0.5 * tol + 1e-7 * self.diag
        X = np.asarray([self.X[n] for n in nodes])
        lo, hi = P.min(0) - thr, P.max(0) + thr
        inb = np.where(((X >= lo) & (X <= hi)).all(1))[0]
        A, B = P[:-1], P[1:]
        seg = B - A
        L2 = np.maximum((seg * seg).sum(1), 1e-30)
        cum = np.concatenate([[0.0], np.cumsum(np.sqrt(L2))])
        found = []
        for i0 in range(0, len(inb), 2000):
            idx = inb[i0:i0 + 2000]
            Q = X[idx]
            t = np.clip(((Q[:, None, :] - A[None]) * seg[None]).sum(2) / L2[None], 0.0, 1.0)
            D = np.linalg.norm(Q[:, None, :] - (A[None] + t[:, :, None] * seg[None]), axis=2)
            k = D.argmin(1)
            for j, i in enumerate(idx):
                if D[j, k[j]] <= thr:
                    found.append((cum[k[j]] + t[j, k[j]] * math.sqrt(L2[k[j]]), nodes[i]))
        if len(found) < 2:
            raise AnalysisError("edge %s of component %s: no mesh nodes found on the edge" % (key[1], key[0]))
        found.sort()
        ids = [n for _s, n in found]
        Y = np.asarray([self.X[n] for n in ids])
        segl = np.linalg.norm(Y[1:] - Y[:-1], axis=1)
        if closed:
            segl = np.append(segl, np.linalg.norm(Y[0] - Y[-1]))
        w = np.zeros(len(ids))
        w[:-1] += segl[:len(ids) - 1] / 2
        w[1:] += segl[:len(ids) - 1] / 2
        if closed:
            w[-1] += segl[-1] / 2
            w[0] += segl[-1] / 2
        length = float(segl.sum())
        res = {"nodes": ids, "w": {n: float(x) for n, x in zip(ids, w)}, "length": length,
               "centre": (w[:, None] * Y).sum(0) / max(w.sum(), 1e-30)}
        self.edge_cache[key] = res
        return res

    def vertex_node(self, ref):
        """Mesh node at a geometry vertex {"comp", "vertex", "xyz"}: the node of the bodies of the component (all
        bodies when none is found there) nearest to xyz, within 1e-4 of the model size + 0.01 mm."""
        p = np.asarray(ref.get("xyz") or [], float)
        if p.shape != (3,):
            raise AnalysisError("vertex %s of component %s has no coordinates" % (ref.get("vertex"), ref.get("comp")))
        key = ("v", round(float(p[0]), 6), round(float(p[1]), 6), round(float(p[2]), 6))
        if key in self.edge_cache:
            return self.edge_cache[key]
        cid = str(ref.get("comp"))
        own = set()
        for bid, b in self.bodies.items():
            if str(b.get("comp", bid)) == cid or cid in (b.get("comps") or ()):
                own |= self.body_nodes(bid)
        thr = 1e-4 * self.diag + 0.01
        best = None
        for cand in ([n for n in own if n in self.X], list(self.X)):
            if not cand:
                continue
            Y = np.asarray([self.X[n] for n in cand])
            d = np.linalg.norm(Y - p, axis=1)
            k = int(d.argmin())
            if d[k] <= thr:
                best = cand[k]
                break
        if best is None:
            raise AnalysisError("no mesh node at the vertex (%.4g, %.4g, %.4g) of component %s" % (p[0], p[1], p[2], cid))
        self.edge_cache[key] = best
        return best

    def mesh_nodes(self, nodes, elements, what):
        """Mesh nodes of a selection of mesh nodes and elements (ids of the mesh; ids not in the mesh: an error)."""
        ids = set()
        missing = [n for n in nodes if int(n) not in self.X]
        if missing:
            raise AnalysisError("%s: %d mesh node(s) not in the mesh (the mesh changed since the selection), e.g. %s" % (what, len(missing), missing[0]))
        ids.update(int(n) for n in nodes)
        if elements:
            want = set(int(e) for e in elements)
            found = set()
            for mb in self.mesh["bodies"].values():
                for bl in mb["blocks"]:
                    for e in bl["elements"]:
                        if e[0] in want:
                            found.add(e[0])
                            ids.update(e[1:])
            if len(found) < len(want):
                raise AnalysisError("%s: %d element(s) not in the mesh (the mesh changed since the selection)" % (what, len(want) - len(found)))
        return ids

    def body_nodes(self, bid):
        mb = self.mesh["bodies"].get(bid) or {}
        return set(n for bl in mb.get("blocks", []) for e in bl["elements"] for n in e[1:])

    def shell_edges(self, bids):
        """Element edges of the shell elements of the bodies: {(corner a, corner b): [nodes of the edge]} with the
        number of elements using each edge: ({key: nodes}, {key: count})."""
        nodes, count = {}, {}
        for bid in bids:
            for bl in (self.mesh["bodies"].get(bid) or {}).get("blocks", []):
                if bl["type"] not in SHELL_ELEMS:
                    continue
                nc = NCORNER[bl["type"]]
                for e in bl["elements"]:
                    n = e[1:]
                    for i in range(nc):
                        a, b = n[i], n[(i + 1) % nc]
                        k = (a, b) if a < b else (b, a)
                        nodes[k] = [a, b] + ([n[nc + i]] if len(n) > nc else [])
                        count[k] = count.get(k, 0) + 1
        return nodes, count

    def node_set(self, ns):
        """Nodes of a node set (doc["nsets"]):
            {"kind": "plane", "axis": "x" | "y" | "z", "value": mm, "tol": mm}   all mesh nodes within tol of the plane
            {"kind": "edges", "edges": [edge references]}                       the nodes on the edges
            {"kind": "faces", "faces": [face references]}                       the nodes of the faces
            {"kind": "selection", "faces", "edges", "bodies", "vertices", "nodes", "elements"}
                                                                                the nodes of the faces, edges, bodies,
                                                                                vertices, mesh nodes and elements
            {"kind": "inp", "set": name}                                        the nodes of a *NSET (.inp) or /GRNOD (.rad) of the mesh file source
            {"kind": "body", "bodies": [body ids]}                              all nodes of the bodies (component id,
                                                                                "<component>:<surface>", "sec:<id>")
            {"kind": "section_edges", "body": body id ("sec:<id>" or "<component>:<surface>"), "which": "free" |
             "outline"}   free: the element edges of the body that bound one shell element of the whole model;
                          outline: the element edges of the body used by one element of the body."""
        kind = ns.get("kind")
        name = ns.get("name") or ns.get("id")
        ids = set()
        if kind == "plane":
            ax = "xyz".index(str(ns.get("axis") or "z").lower()[:1])
            c, tol = float(ns.get("value") or 0), float(ns.get("tol") if ns.get("tol") not in (None, "") else 0.01)
            for bid in self.mesh["bodies"]:
                ids.update(n for n in self.body_nodes(bid) if abs(self.X[n][ax] - c) <= tol)
        elif kind == "edges":
            for r in ns.get("edges") or []:
                ids.update(self.edge(r)["nodes"])
        elif kind == "faces":
            for r in ns.get("faces") or []:
                ids.update(self.face(r)["nodes"])
        elif kind == "selection":
            for r in ns.get("faces") or []:
                ids.update(self.face(r)["nodes"])
            for r in ns.get("edges") or []:
                ids.update(self.edge(r)["nodes"])
            for r in ns.get("vertices") or []:
                ids.add(self.vertex_node(r))
            ids.update(self.mesh_nodes(ns.get("nodes") or [], ns.get("elements") or [], "node set %s" % name))
            if ns.get("bodies"):
                ids.update(self.node_set({"kind": "body", "name": name, "bodies": ns["bodies"]}))
        elif kind == "inp":
            src = (self.mesh.get("nsets") or {}).get(str(ns.get("set") or "").upper())
            if src is None:
                raise AnalysisError("node set %s: %s is not in the mesh file" % (name, ns.get("set")))
            ids.update(int(n) for n in src if int(n) in self.X)
        elif kind == "body":
            for bid in ns.get("bodies") or []:
                bid = str(bid)
                # faces of a surface body meshed in sections: the nodes of those faces
                sec = [key for b in self.bodies.values() for key, sb in (b.get("surf_of") or {}).items() if sb == bid]
                if bid not in self.mesh["bodies"] and not sec:
                    raise AnalysisError("node set %s: body %s is not meshed (off)" % (name, bid))
                if bid in self.mesh["bodies"]:
                    ids.update(self.body_nodes(bid))
                for cid, fi in sec:
                    ids.update(self.face({"comp": cid, "face": fi})["nodes"])
        elif kind == "section_edges":
            bid = str(ns.get("body") or "")
            if not bid:
                raise AnalysisError("node set %s: choose the section or shell of its edges" % name)
            if bid not in self.mesh["bodies"]:
                raise AnalysisError("node set %s: shell or section %s is not meshed" % (name, bid))
            own, ocount = self.shell_edges([bid])
            if ns.get("which") == "outline":
                keys = [k for k, n in ocount.items() if n == 1]
            else:
                _all, acount = self.shell_edges(list(self.mesh["bodies"]))
                keys = [k for k in own if acount.get(k) == 1]
            for k in keys:
                ids.update(own[k])
        else:
            raise AnalysisError("node set %s: unknown kind %s" % (name, kind))
        if not ids:
            raise AnalysisError("node set %s has no nodes" % name)
        return sorted(ids)

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
        if self._vis is not None:
            self._vis[(n, d)] = self._vis.get((n, d), 0.0) + float(v)

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
    def build(self, mesh_only=False):
        """Builds the model. mesh_only: the mesh with the items that are complete; supports, loads, fasteners and
        members without their targets or points are left out, supports and loads whose targets are not found give
        a warning, and the checks of the solve (no supports, analysis type) are not made."""
        doc = self.doc
        if mesh_only:
            doc = self.doc = dict(doc,
                                  supports=[x for x in doc.get("supports") or [] if x.get("target")],
                                  loads=[x for x in doc.get("loads") or [] if (x.get("type") or "force") == "gravity" or x.get("target")],
                                  fasteners=[x for x in doc.get("fasteners") or [] if len([r for r in (x.get("faces") or []) if r]) == 2],
                                  members=[x for x in doc.get("members") or [] if all((x.get(k) or {}).get("xyz") for k in ("a", "b"))])
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
        if not (doc.get("supports") or []) and not mesh_only:
            raise AnalysisError("no supports")
        if self.atype != "static" and not mesh_only:
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
            if mesh_only:
                try:
                    self._support(s)
                except AnalysisError as err:
                    self.warnings.append("support %s left out: %s" % (s.get("name") or s.get("id"), err))
            else:
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
        for fn, key in ((constraints.springs, "springs"), (constraints.joints, "joints"), (constraints.equations, "equations")):
            try:
                fn(self, doc)
            except (constraints.ConstraintError, AnalysisError) as err:
                if not mesh_only:
                    raise AnalysisError(str(err))
                self.warnings.append("%s left out: %s" % (key, err))
        for ld in doc.get("loads") or []:
            self._vis = {}
            q0 = [np.array(info["q"], float) for info in self.members]
            try:
                self._load(ld)
                self.load_parts.append({"id": ld.get("id"), "nodal": dict(self._vis), "amp": str(ld["amplitude"]) if ld.get("amplitude") else None,
                                        "dq": {i: np.asarray(info["q"], float) - q0[i] for i, info in enumerate(self.members)
                                               if np.any(np.asarray(info["q"], float) - q0[i])},
                                        "f": [step_factor(ld, st["id"]) for st in self.user_steps], "name": ld.get("name") or ld.get("id")})
            except AnalysisError as err:
                if not mesh_only:
                    raise
                self.warnings.append("load %s left out: %s" % (ld.get("name") or ld.get("id"), err))
                continue
            finally:
                vis, self._vis = self._vis, None
            self.load_vis.append({"id": ld.get("id"), "name": ld.get("name") or ld.get("id"), "type": ld.get("type") or "force",
                                  "nodal": vis, "value": ld.get("value")})
        self._rp_check(mesh_only)
        self._member_loads()
        self._step_loads()
        self._initial_velocities()
        if self.doc.get("bonded", True):
            self._ties()
            self._member_plate_ties()
        self._contacts(mesh_only)
        self._history(mesh_only)
        if self.atype == "static" and self.incremental():
            # nonlinear and dynamic steps: beams as B31 (expanded to 3D elements by CalculiX); fasteners stay linear
            bad = [i["name"] for i in self.members if i["kind"] == "beam" and (i["m"].get("section") or {}).get("shape", "ROUND").upper() not in B31_SECTIONS]
            msg = None
            if self.fasteners:
                msg = ("nonlinear or dynamic solve: fasteners (U1 elements with preload, linear only) are not supported: %s"
                       % ", ".join(f["name"] for f in self.fasteners[:4]))
            elif bad:
                msg = ("nonlinear or dynamic solve: beams are B31 elements with a RECT, ROUND, PIPE or BOX section; not available for %s"
                       % ", ".join(bad[:4]))
            if msg:
                if not mesh_only:
                    raise AnalysisError(msg)
                self.warnings.append(msg)
            self.b31 = any(i["kind"] == "beam" for i in self.members)
        if mesh_only:
            return
        if self.atype == "modal":
            mats = doc.get("materials") or {}
            bad = [n for n in self.mat_names if not float(material_values(mats.get(n)).get("rho") or 0) > 0]
            if bad:
                raise AnalysisError("modal analysis: material %s has no density" % ", ".join(bad))
        if self.atype == "buckling":
            loaded = any(v for v in self.cloads[1].values()) or any(v for sp in self.supports for v in sp["values"].values()) \
                or any(v for sp in self.supports for v in ((sp.get("rot") or {}).get("values") or {}).values()) \
                or any(v for sp in self.supports for v in (sp.get("rvalues") or {}).values())
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
        (ROT NODE of a CalculiX *RIGID BODY)."""
        name = p.get("name") or p.get("id")
        xyz = p.get("xyz")
        if not xyz or len(xyz) != 3:
            raise AnalysisError("reference point %s has no coordinates" % name)
        if constraints.coupling_of(p) != "none" and not (p.get("faces") or p.get("edges") or p.get("nsets")):
            raise AnalysisError("reference point %s: pick the faces, edges or node sets it is coupled to (or Coupling none)" % name)
        xyz = np.asarray(xyz, float)
        ref, rot = self.new_node(xyz), self.new_node(xyz)
        self.rp_rot_nodes.add(rot)
        self.rps[str(p.get("id"))] = {"name": name, "ref": ref, "rot": rot, "xyz": xyz, "nodes": [], "joints": [],
                                      "coupling": constraints.coupling_of(p)}

    def _ref_point_links(self, p):
        """Coupling of a reference point (constraints.py): rigid (equations of the rigid motion of the nodes of its
        faces, edges and node sets; supported nodes and nodes already constrained are left out), kinematic (the
        chosen components), distributing (RBE3 equations) or none; and the member ends at the point (translations
        and, at a beam end, rotations equal to those of the reference point)."""
        rp = self.rps[str(p.get("id"))]
        mode = constraints.coupling_of(p)
        what = "reference point %s" % rp["name"]
        if mode != "none":
            try:
                w = constraints.target_nodes(self, p)
                if mode == "distributing":
                    rp["nodes"] = constraints.distributing(self, rp, w, constraints._flags(p.get("dofs")), what)
                else:                   # rigid: all six components (linear equations of the rigid motion)
                    dofs = [1] * 6 if mode == "rigid" else constraints._flags(p.get("dofs"))
                    rp["nodes"] = constraints.kinematic(self, rp, w, dofs, what)
            except constraints.ConstraintError as e:
                raise AnalysisError(str(e))
        tol = max(self.ptol, 1e-6 * self.diag)
        joints = sorted(set(info["joint"][e] for info in self.members for e in ("a", "b")
                            if np.linalg.norm(self.X[info["joint"][e]] - rp["xyz"]) <= tol))
        for j in joints:
            for d in (1, 2, 3):
                self.add_eq([(j, d, 1.0), (rp["ref"], d, -1.0)])
            if j in self.rot_nodes:
                self.rot_used.add(rp["rot"])
                for d in (1, 2, 3):
                    self.add_eq([(j, d + 3, 1.0), (rp["rot"], d, -1.0)])
        rp["joints"] = joints

    def _rp_check(self, mesh_only):
        """Rotation nodes of reference points that nothing uses are held (no stiffness); a reference point that
        nothing connects to the model stops the solve."""
        if not self.rps:
            return
        used = set()
        for ln in self.equations:
            v = [x.strip() for x in ln.split(",")]
            if len(v) >= 3:
                used.update(int(float(v[k])) for k in range(0, len(v) - 2, 3))
        for sp in self.user_springs:
            used.update(sp["elem"][1:])
        for ns, ref, rot in self.rigid:
            used.update((ref, rot))
        for cl in self.cloads:
            used.update(n for n, d in cl)
        used.update(n for n, ds in self.spc.items() if ds)
        for rp in self.rps.values():
            if rp["rot"] not in used and rp["rot"] not in self.rot_used:
                self.extra_fix.append((rp["rot"], 1, 3))
            if rp["ref"] not in used:
                msg = "reference point %s is not connected to the model (coupling, member end, spring, joint, equation or support)" % rp["name"]
                if mesh_only:
                    self.warnings.append(msg)
                else:
                    raise AnalysisError(msg)

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
        typ = s.get("type") or ("dofs" if s.get("dofs") else "fixed")      # a support of the explicit branch: its dofs
        nodes, rot_ok = [], False
        trans = None
        values = {}                     # dof -> prescribed displacement (mm; rad for rotations)
        fl6 = list(s.get("dofs") or [1, 1, 1, 0, 0, 0]) + [0] * 6
        tgt = single_target(tgt)
        if is_multi(tgt):
            if typ == "normal":
                raise AnalysisError("support %s: the normal support takes one planar face" % name)
            return self._support_nodes(s, name, tgt, typ)
        if "edge" in tgt or "nset" in tgt or ("point" not in tgt and "member" not in tgt and typ != "normal" and self.face(tgt)["shell"]):
            return self._support_nodes(s, name, tgt, typ)
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

    def _support_nodes(self, s, name, tgt, typ):
        """Support on an edge or on a face of a shell: the translations of all its nodes and the rotations of its
        shell nodes (solid nodes have no rotations). Types fixed (all six), pinned (translations), xsymm / ysymm /
        zsymm (symmetry about the plane normal to x / y / z), dofs, displacement."""
        if is_multi(tgt):
            nodes = self.node_set(dict({k: tgt.get(k) or [] for k in MULTI_KEYS}, kind="selection", name="of support %s" % name))
            centre = np.mean([self.X[n] for n in nodes], axis=0)
        elif "edge" in tgt:
            ed = self.edge(tgt)
            nodes, centre = ed["nodes"], ed["centre"]
        elif "nset" in tgt:
            ns = next((x for x in self.doc.get("nsets") or [] if str(x.get("id")) == str(tgt["nset"])), None)
            if ns is None:
                raise AnalysisError("support %s: node set not found" % name)
            nodes = self.node_set(ns)
            centre = np.mean([self.X[n] for n in nodes], axis=0)
        else:
            face = self.face(tgt)
            nodes = face["nodes"]
            ws = face["w"]
            tw = sum(ws.values())
            centre = sum(self.X[n] * w for n, w in ws.items()) / tw if tw > 0 else np.mean([self.X[n] for n in nodes], axis=0)
        fl6 = (list(s.get("dofs") or [1, 1, 1, 0, 0, 0]) + [0] * 6)[:6]
        values = {}
        if typ == "fixed":
            dofs = [1, 2, 3, 4, 5, 6]
        elif typ == "pinned":
            dofs = [1, 2, 3]
        elif typ in SYMMETRY:
            dofs = list(SYMMETRY[typ])
        elif typ in ("dofs", "displacement"):
            dofs = [i + 1 for i, v in enumerate(fl6) if v]
            if typ == "displacement":
                vv = (list(s.get("value") or []) + [0.0] * 6)[:6]
                values = {d: float(vv[d - 1] or 0) for d in dofs}
        else:
            raise AnalysisError("support %s: type %s is not available on an edge or a node set" % (name, typ))
        if not dofs:
            raise AnalysisError("support %s fixes no degree of freedom" % name)
        rn = [n for n in nodes if n in self.shell_nodes]
        td = [d for d in dofs if d <= 3]
        rd = [d for d in dofs if d > 3] if rn else []
        if not rn and any(d > 3 for d in dofs) and typ != "fixed":
            self.warnings.append("support %s: rotations left out (the nodes are nodes of solid elements)" % name)
        if not td and not rd:
            raise AnalysisError("support %s fixes no degree of freedom of its nodes" % name)
        k = len(self.supports) + 1
        ns = self.nset("SUP%d" % k, nodes)
        rns = self.nset("SUP%dR" % k, rn) if rd else None
        for n in nodes:
            self.spc.setdefault(n, set()).update(td)
        for n in rn:
            self.spc.setdefault(n, set()).update(rd)
        self.supports.append({"s": s, "name": name, "nset": ns, "nodes": list(nodes), "dofs": td, "trans": None,
                              "values": {d: v for d, v in values.items() if d <= 3}, "member": False,
                              "rdofs": rd, "rnset": rns, "rvalues": {d: v for d, v in values.items() if d > 3},
                              "centre": np.asarray(centre, float)})

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
        if typ == "pressure":
            if isinstance(val, (list, tuple)) or not isinstance(val, (int, float, str, type(None))):
                raise AnalysisError("load %s: a pressure is one value (MPa), not %s" % (name, val))
            try:
                val = float(val or 0)
            except ValueError:
                raise AnalysisError("load %s: pressure %r is not a number" % (name, val))
        elif typ != "gravity" or val is not None:
            if not isinstance(val, (list, tuple)) or len(val) != 3:
                raise AnalysisError("load %s: the value of a %s load is three components (x, y, z), not %s" % (name, typ, val))
            try:
                val = [float(x) for x in val]
            except (TypeError, ValueError):
                raise AnalysisError("load %s: the components %s are not numbers" % (name, val))
        if typ == "gravity":
            g = np.asarray(val or [0, 0, -9810.0], float)
            self.grav = g if self.grav is None else self.grav + g
            self._body_weight(g)
            for info in self.members:
                rho = float(material_values((self.doc.get("materials") or {}).get(info["material"])).get("rho") or 0) * 1e-12
                info["q"] = info["q"] + rho * info["sec"]["A"] * g
            self.loads.append({"l": ld, "name": name, "type": typ})
            return
        tgt = single_target(tgt)
        if is_multi(tgt):
            fr, er, br, vr, nr, elr = (list(tgt.get(k) or []) for k in MULTI_KEYS)
            if vr or nr or elr:
                if fr or er or br:
                    raise AnalysisError("load %s: vertices, mesh nodes and elements take a load of their own (not with faces, edges or bodies)" % name)
                if typ != "force":
                    raise AnalysisError("load %s: vertices, mesh nodes and elements take a force (N), shared equally by their nodes" % name)
                ids = set(self.vertex_node(r) for r in vr) | self.mesh_nodes(nr, elr, "load %s" % name)
                F = np.asarray(val, float)
                for n in sorted(ids):
                    for d in range(3):
                        if F[d]:
                            self.cload(n, d + 1, F[d] / len(ids))
                self.loads.append({"l": ld, "name": name, "type": typ, "total": F})
                return
            if br:
                raise AnalysisError("load %s: a load takes faces or edges, not bodies" % name)
            if fr and er:
                raise AnalysisError("load %s: faces and edges together; a load takes faces or edges" % name)
            if er:
                if typ != "line":
                    raise AnalysisError("load %s: edges take a line load (N/mm)" % name)
                q = np.asarray(val, float)
                length = 0.0
                for r in er:
                    ed = self.edge(r)
                    length += ed["length"]
                    for n in ed["nodes"]:
                        for d in range(3):
                            if q[d]:
                                self.cload(n, d + 1, q[d] * ed["w"][n])
                self.loads.append({"l": ld, "name": name, "type": typ, "total": q * length})
                return
            if typ == "pressure":
                tot = np.zeros(3)
                for r in fr:
                    tot += self._pressure(r, float(val or 0))
                self.loads.append({"l": ld, "name": name, "type": typ, "total": tot})
                return
            face = self.faces_merged(fr)
            if typ == "moment":
                c = self.distribute(face, M=np.asarray(val, float))
                self.loads.append({"l": ld, "name": name, "type": typ, "moment": np.asarray(val, float), "point": c})
            elif typ == "force":
                self.distribute(face, F=np.asarray(val, float))
                self.loads.append({"l": ld, "name": name, "type": typ, "total": np.asarray(val, float)})
            else:
                raise AnalysisError("load %s: faces take a force, a moment or a pressure" % name)
            return
        if typ == "line" and "edge" in tgt:
            ed = self.edge(tgt)
            q = np.asarray(val, float)
            for n in ed["nodes"]:
                for d in range(3):
                    if q[d]:
                        self.cload(n, d + 1, q[d] * ed["w"][n])
            self.loads.append({"l": ld, "name": name, "type": typ, "total": q * ed["length"]})
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
            tot = self._pressure(tgt, float(val or 0))
            self.loads.append({"l": ld, "name": name, "type": typ, "total": tot})
        elif typ == "moment":
            c = self.distribute(face, M=np.asarray(val, float))
            self.loads.append({"l": ld, "name": name, "type": typ, "moment": np.asarray(val, float), "point": c})
        else:
            v = np.asarray(val, float)
            self.distribute(face, F=v)
            self.loads.append({"l": ld, "name": name, "type": typ, "total": v})

    def _pressure(self, tgt, p):
        """Nodal loads of a pressure p (MPa, positive into the face) on a face; returns the total force."""
        face = self.face(tgt)
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
        return tot

    def _body_weight(self, g):
        """Consistent nodal loads of the weight of the solid and plate elements (BODY_FRACTIONS; the volume from
        the corner nodes)."""
        mats = self.doc.get("materials") or {}
        self.body_weight = getattr(self, "body_weight", np.zeros(3))
        tets_of = {4: [(0, 1, 2, 3)], 8: [(0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (3, 4, 6, 7), (1, 4, 5, 6)],
                   6: [(0, 1, 2, 3), (1, 2, 3, 4), (2, 3, 4, 5)]}
        for es, (typ, els) in self.elsets.items():
            mname = next(mn for e2, b, mn in self.body_sets if e2 == es)
            rho = float(material_values(mats[mname]).get("rho") or 0) * 1e-12
            if rho <= 0:
                continue
            if typ in SHELL_ELEMS:
                th = float(self.bodies[next(b for e2, b, mn in self.body_sets if e2 == es)]["t"])
                fr = SHELL_FRACTIONS[typ]
                for e in els:
                    n = e[1:]
                    P = [self.X[k] for k in n[:NCORNER[typ]]]
                    A = 0.5 * np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])) if len(P) == 3 else \
                        0.5 * np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[1]))
                    W = rho * A * th * g
                    for k, f in zip(n, fr):
                        for d in range(3):
                            self.cload(k, d + 1, W[d] * f)
                    self.body_weight = self.body_weight + W
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
                    if bid == pid or group[bid] == group[pid] or group[bid] == "shell" or frozenset((bid, pid)) in self.contact_bodies:
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
                        # a shell face may lie on a solid face in part only: one sample point near it is enough
                        need = 1 if group[pid] == "shell" else max(3, len(sp) // 2)
                        if group[pid] == "shell":
                            snx = np.asarray([self.X[n] for n in s["nodes"]])
                            inb_n = ((snx >= lo - tol) & (snx <= hi + tol)).all(1)
                            if not inb_n.any():
                                continue
                            sp_t, inb = snx[inb_n], np.ones(int(inb_n.sum()), bool)
                        else:
                            sp_t = sp
                        if inb.sum() < need:
                            continue
                        quads = [f for f in F if len(f) in (4, 8)]
                        if quads:
                            A = np.vstack([A, np.asarray([self.X[f[0]] for f in quads])])
                            B = np.vstack([B, np.asarray([self.X[f[2]] for f in quads])])
                            C = np.vstack([C, np.asarray([self.X[f[3]] for f in quads])])
                        d = _point_tri_dist(sp_t[inb], A, B, C)
                        if (d <= tol).sum() < (3 if group[pid] == "shell" else need):
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

    # ------------------------------------------------------------------ contact
    def _node_elems(self):
        ne = {}
        for mb in self.mesh["bodies"].values():
            for bl in mb["blocks"]:
                for e in bl["elements"]:
                    for n in e[1:]:
                        ne.setdefault(n, []).append((e, bl["type"]))
        return ne

    def _surface_faces(self, facets, node_elem, toward):
        """Element faces of mesh facets: [(elem, "S<k>" | "SPOS" | "SNEG")]. A shell facet is the shell element; its
        side is the one whose normal points to toward (the centre of the other surface)."""
        out = []
        for f in facets:
            nc = 4 if len(f) in (4, 8) else 3
            cs = set(f[:nc])
            for e, typ in node_elem.get(f[0], ()):
                if not cs.issubset(set(e[1:1 + NCORNER[typ]])):
                    continue
                if typ in SHELL_ELEMS:
                    if set(e[1:1 + NCORNER[typ]]) != cs:
                        continue
                    P = [self.X[n] for n in e[1:4]]
                    nrm = np.cross(P[1] - P[0], P[2] - P[0])
                    ctr = np.mean([self.X[n] for n in e[1:1 + NCORNER[typ]]], axis=0)
                    out.append((e[0], "SPOS" if np.dot(nrm, toward - ctr) >= 0 else "SNEG"))
                    break
                for k, fn in enumerate(FACE_NODES[typ]):
                    if set(e[i] for i in fn) == cs:
                        out.append((e[0], "S%d" % (k + 1)))
                        break
                break
        return out

    def _contacts(self, mesh_only):
        """Contact pairs (doc["contacts"]): penalty surface-to-surface or node-to-surface contact with friction, or
        tied surfaces. Master: element faces of the master faces; slave: element faces (surface-to-surface) or the
        nodes of the slave faces or of the slave node set."""
        self.contact_defs = []
        cs = self.doc.get("contacts") or []
        if not cs:
            return
        node_elem = self._node_elems()
        mats = self.doc.get("materials") or {}
        emax = max([float(material_values(mats.get(n)).get("E") or 0) for n in self.mat_names] or [210000.0]) or 210000.0
        for k, c in enumerate(cs):
            name = c.get("name") or c.get("id") or str(k + 1)
            try:
                typ = c.get("type") or "surface"
                if typ not in CONTACT_TYPES:
                    raise AnalysisError("unknown type %s" % typ)
                mref = [r for r in c.get("master") or [] if r]
                sref = [r for r in c.get("slave") or [] if r]
                if not mref:
                    raise AnalysisError("no master faces")
                mf = [self.face(r) for r in mref]
                mfac = [f for x in mf for f in x["facets"]]
                mnodes = set(n for x in mf for n in x["nodes"])
                if c.get("slave_nset") and typ != "surface":
                    ns_ = next((x for x in self.doc.get("nsets") or [] if str(x.get("id")) == str(c["slave_nset"])), None)
                    if ns_ is None:
                        raise AnalysisError("slave node set not found")
                    snodes, sfac = set(self.node_set(ns_)), []
                elif sref:
                    sf = [self.face(r) for r in sref]
                    sfac = [f for x in sf for f in x["facets"]]
                    snodes = set(n for x in sf for n in x["nodes"])
                else:
                    raise AnalysisError("no slave faces" + (" (surface-to-surface takes slave faces; a node set slave: node-to-surface)" if c.get("slave_nset") else ""))
                shared = mnodes & snodes
                if shared:
                    raise AnalysisError("the master and slave faces share %d node(s): the bodies are meshed together (Bonded contact between "
                                        "touching bodies) or a face is on both sides" % len(shared))
                mc = np.mean([self.X[n] for n in mnodes], axis=0)
                sc = np.mean([self.X[n] for n in snodes], axis=0)
                master = self._surface_faces(mfac, node_elem, sc)
                if not master:
                    raise AnalysisError("no element faces found on the master faces")
                d = {"name": "C%d" % (k + 1), "label": str(name), "type": typ, "master": master,
                     "friction": float(c.get("friction") or 0), "adjust": c.get("adjust"),
                     "K": float(c.get("stiffness") or 0) or 10.0 * emax, "slave_nodes": sorted(snodes)}
                if typ == "surface":
                    d["slave"] = self._surface_faces(sfac, node_elem, mc)
                    if not d["slave"]:
                        raise AnalysisError("no element faces found on the slave faces")
                else:
                    self.nset("C%dSN" % (k + 1), sorted(snodes))
                    d["tol"] = float(c.get("tol") or 0) or max(0.01 * self.diag, 1e-3)
                if typ == "tied":
                    for n in snodes:
                        self.dependent.update((n, dd) for dd in (1, 2, 3))
                self.contact_defs.append(d)
            except AnalysisError as e:
                if not mesh_only:
                    raise AnalysisError("contact %s: %s" % (name, e))
                self.warnings.append("contact %s left out: %s" % (name, e))

    def nonlinear(self):
        """Nonlinear static step: large deformation, contact (not tied), or a plastic or hyperelastic material used."""
        mats = self.doc.get("materials") or {}
        return bool(self.nlgeom() or any(d["type"] != "tied" for d in self.contact_defs) or
                    any((material_values(mats.get(n)).get("law") or "elastic") != "elastic" for n in self.mat_names))

    def incremental(self):
        """Steps with increments: a nonlinear material, contact or large deformation, or a dynamic step."""
        return self.nonlinear() or any(st["kind"] != "static" for st in self.user_steps)

    def multistep(self):
        """Loads written per step (several steps, step factors or amplitudes)."""
        return self.step_cloads is not None

    def step_periods(self):
        """Period (s) of each step of the input file in order: the preload step of the fastener springs when there
        is one, then the steps."""
        if self.atype != "static" or not self.user_steps:
            return []
        pre = any(f.get("spring") for f in self.fasteners)
        return ([self.user_steps[0]["time"]] if pre else []) + [u["time"] for u in self.user_steps]

    def _step_loads(self):
        """Loads of each step from the load parts (factors, amplitudes) and the member line loads of each step."""
        N = len(self.user_steps)
        if not N:
            return
        need = N > 1 or any(p["amp"] for p in self.load_parts) or any(abs(f - 1.0) > 0 for p in self.load_parts for f in p["f"])
        if not need:
            return
        for p in self.load_parts:
            if p["amp"] and p["amp"] not in self.amplitudes:
                raise AnalysisError("load %s: amplitude %s not found" % (p["name"], p["amp"]))
        # member line loads of the parts as nodal loads; loads outside the parts (constant) stay in every step
        full = []
        for p in self.load_parts:
            nd = dict(p["nodal"])
            for i, q in p["dq"].items():
                for k, v in self._q_nodal(self.members[i], q).items():
                    nd[k] = nd.get(k, 0.0) + v
            full.append(nd)
            p["full"] = nd
        base = dict(self.cloads[1])
        for nd in full:
            for k, v in nd.items():
                base[k] = base.get(k, 0.0) - v
        base = {k: v for k, v in base.items() if abs(v) > 1e-12 * (1 + abs(self.cloads[1].get(k, 0.0)))}
        self.base_loads = base
        self.step_cloads = []
        self.step_q = []
        cl_tot = []
        for k in range(N):
            amp_sets = {None: dict(base)}
            for p in self.load_parts:
                f = p["f"][k]
                if not f:
                    continue
                dst = amp_sets.setdefault(p["amp"], {})
                for kk, v in p["full"].items():
                    dst[kk] = dst.get(kk, 0.0) + f * v
            seen = {}
            for a, dct in amp_sets.items():
                for kk, v in dct.items():
                    if v and kk in seen and seen[kk] != a:
                        names = [p["name"] for p in self.load_parts if p["f"][k] and p["amp"] in (a, seen[kk]) and kk in p["full"]]
                        raise AnalysisError("step %s: loads with different amplitudes act on the same nodes (CalculiX takes one "
                                            "amplitude per node and direction): %s" % (self.user_steps[k]["name"], ", ".join(names)))
                    if v:
                        seen[kk] = a
            self.step_cloads.append(amp_sets)
            tot = {}
            for dct in amp_sets.values():
                for kk, v in dct.items():
                    tot[kk] = tot.get(kk, 0.0) + v
            cl_tot.append(tot)
            self.step_q.append([sum((p["f"][k] * p["dq"][i] for p in self.load_parts if i in p["dq"]), np.zeros(3)) for i in range(len(self.members))])
        self.cloads = [self.cloads[0]] + cl_tot

    def part_weight(self, part, k, tau):
        """Factor of a load part in step k (1-based) at the fraction tau of the step (amplitude, ramp or step)."""
        st = self.user_steps[k - 1]
        f = part["f"][k - 1]
        if part["amp"]:
            return f * amplitude_value(self.amplitudes[part["amp"]].get("points"), tau * st["time"])
        if st["kind"] != "static":
            return f
        fp = part["f"][k - 2] if k >= 2 and not part["amp"] else 0.0
        return fp + (f - fp) * tau

    def _history(self, mesh_only=False):
        """Time history requests: node set H<k> or element set HE<k> per request (self.hist)."""
        self.hist = []
        for k, h in enumerate(self.doc.get("history") or []):
            name = h.get("name") or h.get("id")
            kind = h.get("kind") or "node"
            q = [x for x in (h.get("quantities") or []) if x]
            t = h.get("target") or {}
            try:
                if not q:
                    raise AnalysisError("no quantities")
                if kind == "node":
                    if "nset" in t:
                        ns = next((x for x in self.doc.get("nsets") or [] if str(x.get("id")) == str(t["nset"])), None)
                        if ns is None:
                            raise AnalysisError("node set not found")
                        nodes = self.node_set(ns)
                    elif "point" in t:
                        rp = self.rps.get(str(t["point"]))
                        if rp is None:
                            raise AnalysisError("reference point not found")
                        nodes = [rp["ref"]]
                    elif is_multi(t):
                        nodes = self.node_set(dict({x: t.get(x) or [] for x in MULTI_KEYS}, kind="selection", name="of history %s" % name))
                    elif "comp" in t:
                        nodes = self.edge(t)["nodes"] if "edge" in t else self.face(t)["nodes"]
                    else:
                        raise AnalysisError("no target")
                    self.hist.append({"h": h, "name": name, "kind": kind, "q": q, "set": self.nset("H%d" % (k + 1), nodes), "n": len(nodes)})
                elif kind == "contact":
                    cid = str(t.get("contact") or "")
                    cs = self.doc.get("contacts") or []
                    ci = next((i for i, c in enumerate(cs) if str(c.get("id")) == cid), None)
                    if ci is None:
                        raise AnalysisError("contact not found (choose a contact pair)")
                    cd = next((c for c in self.contact_defs if c["name"] == "C%d" % (ci + 1)), None)
                    if cd is None:
                        raise AnalysisError("contact %s is not in the model" % (cs[ci].get("name") or cid))
                    if cd["type"] == "tied":
                        raise AnalysisError("contact %s is tied (no contact forces)" % cd["label"])
                    self.hist.append({"h": h, "name": name, "kind": kind, "q": q, "slave": cd["name"] + "S", "master": cd["name"] + "M"})
                elif kind == "section":
                    refs = [r for r in (t.get("faces") or ([t] if "face" in t else [])) if r]
                    if not refs:
                        raise AnalysisError("no faces (pick faces of solid bodies)")
                    faces = []
                    for r in refs:
                        f = self.face(r)
                        bid = self.face_body.get((str(r.get("comp")), int(r.get("face", -1))))
                        ne = {}
                        for bl in self.mesh["bodies"][bid]["blocks"]:
                            if bl["type"] in SHELL_ELEMS:
                                raise AnalysisError("face %s: a shell (section forces of solid bodies)" % r.get("face"))
                            for e in bl["elements"]:
                                for n in e[1:]:
                                    ne.setdefault(n, []).append((e, bl["type"]))
                        faces += self._surface_faces(f["facets"], ne, None)
                    if not faces:
                        raise AnalysisError("no element faces on the faces")
                    self.hist.append({"h": h, "name": name, "kind": kind, "q": q, "surf": "HS%d" % (k + 1), "faces": faces})
                else:
                    want = set(int(e) for e in t.get("elements") or [])
                    els = set()
                    for bid in t.get("bodies") or []:
                        mb = self.mesh["bodies"].get(str(bid))
                        if mb is None:
                            raise AnalysisError("body %s is not meshed" % bid)
                        els.update(e[0] for bl in mb["blocks"] for e in bl["elements"])
                    for mb in self.mesh["bodies"].values():
                        els.update(e[0] for bl in mb["blocks"] for e in bl["elements"] if e[0] in want)
                    if not els:
                        raise AnalysisError("no elements (choose bodies or mesh elements)")
                    es = "HE%d" % (k + 1)
                    self.hist.append({"h": h, "name": name, "kind": kind, "q": q, "elset": es, "elements": sorted(els)})
            except AnalysisError as e:
                if not mesh_only:
                    raise AnalysisError("history %s: %s" % (name, e))
                self.warnings.append("history %s left out: %s" % (name, e))

    def _history_cards(self, incr, step_every, dynamic=False):
        """Print requests of the history requests in a step (velocities and kinetic energy in dynamic steps only)."""
        L = self._history_cards0(incr, step_every, dynamic)
        for h in getattr(self, "hist", []):
            try:
                ev = int(h["h"].get("every") or step_every or 1)
            except (TypeError, ValueError):
                ev = 1
            freq = ", FREQUENCY=%d" % ev if incr and ev > 1 else ""
            if h["kind"] == "contact":
                L += ["*CONTACT PRINT, SLAVE=%s, MASTER=%s%s" % (h["slave"], h["master"], freq), "CF"]
            elif h["kind"] == "section":
                L += ["*SECTION PRINT, SURFACE=%s, NAME=SP%s%s" % (h["surf"], h["surf"][2:], freq), "SOF, SOM"]
        return L

    def _history_cards0(self, incr, step_every, dynamic=False):
        """Print requests of the history requests in a step (velocities and kinetic energy in dynamic steps only)."""
        L = []
        for h in getattr(self, "hist", []):
            try:
                ev = int(h["h"].get("every") or step_every or 1)
            except (TypeError, ValueError):
                ev = 1
            freq = ", FREQUENCY=%d" % ev if incr and ev > 1 else ""
            if h["kind"] in ("contact", "section"):
                continue
            if h["kind"] == "node":
                per = [x for x in h["q"] if x == "U" or (x == "V" and dynamic)]
                if per:
                    L += ["*NODE PRINT, NSET=%s%s" % (h["set"], freq), ", ".join(per)]
                if "RF" in h["q"]:
                    L += ["*NODE PRINT, NSET=%s, TOTALS=ONLY%s" % (h["set"], freq), "RF"]
            else:
                per = [x for x in h["q"] if x in ("S", "E")] + (["PEEQ"] if "PEEQ" in h["q"] and self.plastic() else [])
                if per:
                    L += ["*EL PRINT, ELSET=%s%s" % (h["elset"], freq), ", ".join(per)]
                tot = (["ELSE"] if "ENER" in h["q"] else []) + (["ELKE"] if "EKIN" in h["q"] and dynamic else [])
                if tot:
                    L += ["*EL PRINT, ELSET=%s, TOTALS=ONLY%s" % (h["elset"], freq), ", ".join(tot)]
        return L

    def _initial_velocities(self):
        for i, iv in enumerate(self.doc.get("initial_velocities") or []):
            name = iv.get("name") or iv.get("id")
            t = iv.get("target") or {}
            if "nset" in t:
                ns = next((x for x in self.doc.get("nsets") or [] if str(x.get("id")) == str(t["nset"])), None)
                if ns is None:
                    raise AnalysisError("initial velocity %s: node set not found" % name)
                nodes = self.node_set(ns)
            elif is_multi(t):
                nodes = self.node_set(dict({k: t.get(k) or [] for k in MULTI_KEYS}, kind="selection", name="of initial velocity %s" % name))
            else:
                raise AnalysisError("initial velocity %s has no target" % name)
            v = [float(x or 0) for x in (list(iv.get("v") or []) + [0, 0, 0])[:3]]
            self.ivel.append((self.nset("IVEL%d" % (i + 1), nodes), v))

    def nlgeom(self):
        mats = self.doc.get("materials") or {}
        return bool((self.doc.get("nonlinear") or {}).get("nlgeom") or
                    any((material_values(mats.get(n)).get("law") or "elastic") == "hyper" for n in self.mat_names))

    def plastic(self):
        mats = self.doc.get("materials") or {}
        return any((material_values(mats.get(n)).get("law") or "elastic") == "plastic" for n in self.mat_names)

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
        if beams and self.b31:
            for info in beams:
                L.append("*ELEMENT, TYPE=B31, ELSET=%s" % info["elset"])
                L += ["%d, %d, %d" % e for e in info["elems"]]
        elif beams:
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
        for sp in self.user_springs:
            L.append("*ELEMENT, TYPE=%s, ELSET=%s" % (sp["type"], sp["elset"]))
            L.append(", ".join(str(v) for v in sp["elem"]))
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
        for h in getattr(self, "hist", []):
            if h.get("elset"):
                L.append("*ELSET, ELSET=%s" % h["elset"])
                L += ids_lines(h["elements"])
            if h.get("surf"):
                L.append("*SURFACE, NAME=%s, TYPE=ELEMENT" % h["surf"])
                L += ["%d, %s" % fe for fe in h["faces"]]
        for ns, a, b in self.transforms:
            L.append("*TRANSFORM, NSET=%s, TYPE=R" % ns)
            L.append("%.12g, %.12g, %.12g, %.12g, %.12g, %.12g" % (a[0], a[1], a[2], b[0], b[1], b[2]))
        mats = self.doc.get("materials") or {}
        for name, mset in self.mat_names.items():
            try:
                L += ["*MATERIAL, NAME=%s" % mset] + material_cards(mats[name])
            except AnalysisError as e:
                raise AnalysisError("%s %s" % (name, str(e)[len("material: "):] if str(e).startswith("material: ") else e))
        for es, bid, mname in self.body_sets:
            b = self.bodies[bid]
            if self.elsets[es][0] in SHELL_ELEMS:
                nl = int(b.get("shell_layers") or 1)
                if nl > 1 and self.elsets[es][0] == "S8R":
                    L.append("*SHELL SECTION, ELSET=%s, COMPOSITE, OFFSET=%g" % (es, SHELL_OFFSET.get(b.get("offset"), 0.0)))
                    L += ["%.9g, , %s" % (float(b["t"]) / nl, self.mat_names[mname])] * nl
                else:
                    if nl > 1 and es not in self._layer_warned:
                        self._layer_warned.add(es)
                        self.warnings.append("%s: %d layers need S8R shell elements (Mesh: Shell elements); %s written with one layer"
                                             % (b["name"], nl, self.elsets[es][0]))
                    L += ["*SHELL SECTION, ELSET=%s, MATERIAL=%s, OFFSET=%g" % (es, self.mat_names[mname], SHELL_OFFSET.get(b.get("offset"), 0.0)),
                          "%.9g" % float(b["t"])]
            else:
                L.append("*SOLID SECTION, ELSET=%s, MATERIAL=%s" % (es, self.mat_names[mname]))
        for info in beams:
            s = info["sec"]
            if self.b31:
                L += self._b31_section(info)
                continue
            L += ["*BEAM SECTION, ELSET=%s, MATERIAL=%s, SECTION=GENERAL" % (info["elset"], info["mset"]),
                  "%.9g, %.9g, 0., %.9g, %.6g" % (s["A"], s["Ia"], s["Ib"], KAPPA),
                  "%.12g, %.12g, %.12g" % tuple(info["e1"])]
        for info in rods:
            L += ["*SOLID SECTION, ELSET=%s, MATERIAL=%s" % (info["elset"], info["mset"]), "%.9g" % info["sec"]["A"]]
        if springs:
            L += ["*SPRING, ELSET=EPT", "1", "%.6E" % SPRING_K]
        for sp in self.user_springs:
            L += ["*SPRING, ELSET=%s" % sp["elset"], ", ".join(str(d) for d in sp["dofs"]), "%.9E" % sp["k"]]   # a stiffness without a decimal point is not read
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
        for c in self.contact_defs:
            nm = c["name"]
            L.append("*SURFACE, NAME=%sM, TYPE=ELEMENT" % nm)
            L += ["%d, %s" % fm for fm in c["master"]]
            if c["type"] == "surface":
                L.append("*SURFACE, NAME=%sS, TYPE=ELEMENT" % nm)
                L += ["%d, %s" % fs for fs in c["slave"]]
            else:
                L += ["*SURFACE, NAME=%sS, TYPE=NODE" % nm, "%sSN" % nm]
            if c["type"] == "tied":
                L += ["*TIE, NAME=%sT, POSITION TOLERANCE=%.6g, ADJUST=YES" % (nm, c["tol"]), "%sS, %sM" % (nm, nm)]
                continue
            L += ["*SURFACE INTERACTION, NAME=%sI" % nm, "*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR",
                  "%.6g" % c["K"] if c["type"] == "surface" else "%.6g, %.6g" % (c["K"], 1e-5 * c["K"])]
            if c["friction"] > 0:
                L += ["*FRICTION", "%.6g, %.6g" % (c["friction"], 0.1 * c["K"])]
            adj = ""
            try:
                if c.get("adjust") not in (None, "") and float(c["adjust"]) > 0:
                    adj = ", ADJUST=%.6g" % float(c["adjust"])
            except (TypeError, ValueError):
                adj = ""
            L += ["*CONTACT PAIR, INTERACTION=%sI, TYPE=%s%s" % (nm, "SURFACE TO SURFACE" if c["type"] == "surface" else "NODE TO SURFACE", adj),
                  "%sS, %sM" % (nm, nm)]
        if self.contact_defs and self.atype != "static":
            raise AnalysisError("contact: modal and buckling analyses take no contact pairs")
        if self.atype != "static":
            buck = self.atype == "buckling"
            L += ["*STEP", "*BUCKLE" if buck else "*FREQUENCY", "%d" % self.nmodes, "*BOUNDARY"]
            L += ["%d, %d, %d" % f for f in self.extra_fix]
            for sp in self.supports:
                for d in sp["dofs"]:
                    v = sp["values"].get(d, 0.0) if buck else 0.0
                    L.append("%s, %d, %d" % (sp["nset"], d, d) + (", %.12g" % v if v else ""))
                for d in (sp.get("rot") or {}).get("dofs") or []:
                    v = sp["rot"]["values"].get(d, 0.0) if buck else 0.0
                    L.append("%s, %d, %d" % (sp["rot"]["nset"], d, d) + (", %.12g" % v if v else ""))
                for d in sp.get("rdofs") or []:
                    v = sp["rvalues"].get(d, 0.0) if buck else 0.0
                    L.append("%s, %d, %d" % (sp["rnset"], d, d) + (", %.12g" % v if v else ""))
            if buck:
                L.append("*CLOAD")
                for (n, d), v in sorted(self.cloads[1].items()):
                    if v != 0:
                        L.append("%d, %d, %.12g" % (n, d, v))
            L += ["*NODE FILE", "U", "*END STEP"]
            with open(path, "w") as f:
                f.write("\n".join(L) + "\n")
            return
        N = len(self.user_steps)
        steps = ([0] if springs else []) + list(range(1, N + 1))
        incr = self.incremental()
        dyn = any(st["kind"] != "static" for st in self.user_steps)
        # amplitudes and initial velocities (before the first step)
        used_amps = sorted(set(a for sc in (self.step_cloads or []) for a in sc if a))
        for a in used_amps:
            pts = sorted((float(t), float(v)) for t, v in self.amplitudes[a].get("points") or [])
            L.append("*AMPLITUDE, NAME=AMP_%s" % re.sub(r"[^A-Za-z0-9]+", "_", a))
            flat = ["%.9g" % x for tv in pts for x in tv]
            L += [", ".join(flat[k:k + 8]) for k in range(0, len(flat), 8)]
        if self.ivel:
            L.append("*INITIAL CONDITIONS, TYPE=VELOCITY")
            for ns, v in self.ivel:
                L += ["%s, %d, %.12g" % (ns, d + 1, v[d]) for d in range(3) if v[d]]
        first = True
        prev_active = None
        for st in steps:
            u = self.user_steps[st - 1] if st >= 1 else self.user_steps[0]
            T = u["time"]
            every = u["every"] if st >= 1 else 1
            freq = ", FREQUENCY=%d" % every if incr and every > 1 else ""
            nlg = ", NLGEOM" if self.nlgeom() else ""
            if st == 0 or u["kind"] == "static":
                if incr:
                    L += ["*STEP%s, INC=%d" % (nlg, u["maxinc"]), "*STATIC",
                          "%.6g, %.6g, %.6g, %.6g" % (min(u["inc0"], 1.0) * T, T, u["incmin"] * T, min(u["incmax"], 1.0) * T)]
                else:
                    L += ["*STEP", "*STATIC"]
            elif u["kind"] == "dynamic":
                L += ["*STEP%s, INC=%d" % (nlg, u["maxinc"]), "*DYNAMIC, ALPHA=%.6g" % u["alpha"],
                      "%.6g, %.6g, %.6g, %.6g" % (min(u["inc0"], 1.0) * T, T, u["incmin"] * T, min(u["incmax"], 1.0) * T)]
            else:
                L += ["*STEP%s, INC=%d" % (nlg, u["maxinc"]), "*DYNAMIC, EXPLICIT", "%.6g, %.6g" % (min(u["inc0"], 1.0) * T, T)]
            # OP=NEW in the first step and where a support is released; else the boundary conditions are modified
            # (OP=NEW in a later step loses the rotation conditions of expanded shell nodes in CalculiX)
            active = set(i for i, sp in enumerate(self.supports) if st == 0 or step_factor(sp.get("s") or {}, u["id"]) != 0)
            L.append("*BOUNDARY, OP=NEW" if prev_active is None or not active >= prev_active else "*BOUNDARY")
            prev_active = active
            L += ["%d, %d, %d" % f for f in self.extra_fix]
            for sp in self.supports:
                fs = step_factor(sp.get("s") or {}, u["id"]) if st >= 1 else 1.0
                if st >= 1 and fs == 0:
                    continue                                           # released in this step
                sv = fs if st >= 1 else 0.0                            # prescribed displacements in the load steps
                for d in sp["dofs"]:
                    v = sp["values"].get(d, 0.0) * sv
                    L.append("%s, %d, %d" % (sp["nset"], d, d) + (", %.12g" % v if v else ""))
                for d in (sp.get("rot") or {}).get("dofs") or []:          # reference point rotations
                    v = sp["rot"]["values"].get(d, 0.0) * sv
                    L.append("%s, %d, %d" % (sp["rot"]["nset"], d, d) + (", %.12g" % v if v else ""))
                for d in sp.get("rdofs") or []:                             # shell node rotations
                    v = sp["rvalues"].get(d, 0.0) * sv
                    L.append("%s, %d, %d" % (sp["rnset"], d, d) + (", %.12g" % v if v else ""))
            for f in springs:
                L.append("%d, 2, 6" % f["pt"])
                if st >= 1:
                    L.append("%d, 1, 1" % f["pt"])
            if st >= 1 and self.step_cloads is not None:
                sets = self.step_cloads[st - 1]
                L.append("*CLOAD, OP=NEW")
                for (n, d), v in sorted((sets.get(None) or {}).items()):
                    if v != 0:
                        L.append("%d, %d, %.12g" % (n, d, v))
                for a in sorted(k for k in sets if k):
                    L.append("*CLOAD, AMPLITUDE=AMP_%s" % re.sub(r"[^A-Za-z0-9]+", "_", a))
                    for (n, d), v in sorted(sets[a].items()):
                        if v != 0:
                            L.append("%d, %d, %.12g" % (n, d, v))
            else:
                cl = self.cloads[st if st == 0 else 1]
                L.append("*CLOAD, OP=NEW")
                for (n, d), v in sorted(cl.items()):
                    if v != 0:
                        L.append("%d, %d, %.12g" % (n, d, v))
            out_s = "S, PEEQ" if self.plastic() else "S"
            if first and dyn:
                out_s += ", ENER"                                      # dynamic steps: energy output requested in the first step
            L += ["*NODE FILE%s" % freq, "U", "*EL FILE%s" % freq, out_s]
            first = False
            if mnodes:
                L += ["*NODE PRINT, NSET=NMEMB%s" % freq, "U"]
            if beams and not self.b31:
                L += ["*EL PRINT, ELSET=EU1%s" % freq, "S"]
            if rods:
                L += ["*EL PRINT, ELSET=EROD%s" % freq, "S"]
            for sp in self.supports:
                L += ["*NODE PRINT, NSET=%s%s" % (sp["nset"], freq), "RF"]
                if sp.get("rot"):
                    L += ["*NODE PRINT, NSET=%s%s" % (sp["rot"]["nset"], freq), "RF"]
            if self.rps:
                L += ["*NODE PRINT, NSET=NRP%s" % freq, "U"]
            L += self._history_cards(incr, every, st >= 1 and u["kind"] != "static")
            if self.doc.get("ip_output"):                  # integration point stresses (initial state of the Explicit tab)
                for es, _bid, _m in self.body_sets:
                    L += ["*EL PRINT, ELSET=%s%s" % (es, freq), "S, PEEQ" if self.plastic() else "S"]
            L.append("*END STEP")
        with open(path, "w") as f:
            f.write("\n".join(L) + "\n")

    def _b31_section(self, info):
        """*BEAM SECTION of a beam as B31 (RECT b h, ROUND as CIRC, PIPE, BOX), the 1-direction e1."""
        sec = info["m"].get("section") or {"shape": "ROUND", "d": 10}
        sh = sec.get("shape", "ROUND").upper()
        g = lambda k: float(sec.get(k) or 0)
        if sh == "RECT":
            kind, data = "RECT", "%.9g, %.9g" % (g("b"), g("h"))
        elif sh == "ROUND":
            kind, data = "CIRC", "%.9g, %.9g" % (g("d") / 2, g("d") / 2)
        elif sh == "PIPE":
            kind, data = "PIPE", "%.9g, %.9g" % (g("d") / 2, g("t"))
        elif sh == "BOX":
            kind, data = "BOX", "%.9g, %.9g, %.9g, %.9g, %.9g, %.9g" % (g("b"), g("h"), g("t"), g("t"), g("t"), g("t"))
        else:
            raise AnalysisError("member %s: section %s is not available as a B31 beam" % (info["name"], sh))
        return ["*BEAM SECTION, ELSET=%s, MATERIAL=%s, SECTION=%s" % (info["elset"], info["mset"], kind), data,
                "%.12g, %.12g, %.12g" % tuple(info["e1"])]

    def _q_nodal(self, info, q):
        """Consistent nodal loads {(node, dof): v} of a line load q (N/mm, global) on a member."""
        out = {}
        q = np.asarray(q, float)
        if not np.any(q):
            return out
        t = info["t"]
        for e, n1, n2 in info["elems"]:
            le = float(np.linalg.norm(self.X[n2] - self.X[n1]))
            for n in (n1, n2):
                for d in range(3):
                    out[(n, d + 1)] = out.get((n, d + 1), 0.0) + q[d] * le / 2
            if info["kind"] == "beam":
                qp = q - np.dot(q, t) * t
                m = le * le / 12 * np.cross(t, qp)
                for d in range(3):
                    out[(n1, d + 4)] = out.get((n1, d + 4), 0.0) + m[d]
                    out[(n2, d + 4)] = out.get((n2, d + 4), 0.0) - m[d]
        return out

    def _member_loads(self):
        """Consistent nodal loads of the line loads (and the weight) of the members."""
        extra = self.cloads[1]
        self.eq_loads = eq = {}
        for info in self.members:
            for k, v in self._q_nodal(info, info["q"]).items():
                extra[k] = extra.get(k, 0.0) + v
                eq[k] = eq.get(k, 0.0) + v


# --------------------------------------------------------------------------- result files

def read_frd_incs(path, want=("DISP", "STRESS", "PE")):
    """Result blocks of every increment of a .frd file: [(step, increment, time, {name: {node: [values]}})] in their
    order (nonlinear steps write one set of blocks per output increment)."""
    out = []
    cur = None
    key = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith("    1PSTEP"):
                p = line.split()
                try:
                    key = (int(p[3]), int(p[2]))
                except (ValueError, IndexError):
                    key = None
                continue
            if line.startswith("  100C"):
                try:
                    t = float(line[12:24])
                except ValueError:
                    t = 0.0
                if key is not None and (not out or out[-1][:2] != key):
                    out.append((key[0], key[1], t, {}))
                continue
            if line.startswith(" -4"):
                name = line[5:13].strip()
                cur = out[-1][3].setdefault(name, {}) if out and name in want else None
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


_HIST_RE = re.compile(r"(displacements|velocities|forces|total force|stresses|strains|equivalent plastic strain|total internal energy|"
                      r"total kinetic energy)\b.*for set (\S+) and time\s+(\S+)")


_STAT_RE = re.compile(r"statistics for (surface|slave) set (\S+?),?(?: master set (\S+))? and time\s+(\S+)")


def read_history(path):
    """Time history blocks of a .dat file: {(kind, set): [(time, rows)]} in their order; rows as read_dat (nodal
    {node: [values]}, element [(elem, ip, [values])], totals [values])."""
    out = {}
    cur = None
    try:
        f = open(path, "r", errors="replace")
    except OSError:
        return out
    with f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            m = _STAT_RE.match(s)
            if m:                       # *SECTION PRINT (surface set) and *CONTACT PRINT CF (slave set) statistics
                try:
                    t = float(m.group(4))
                except ValueError:
                    t = 0.0
                rows = {}
                cur = ("stat", rows, None)
                out.setdefault(("section" if m.group(1) == "surface" else "contact", m.group(2)), []).append((t, rows))
                continue
            if cur is not None and cur[0] == "stat":
                p = s.split()
                try:
                    cur[1][cur[2]] = [float(v) for v in p]
                except ValueError:
                    lab = ("force" if s.startswith("total surface force") else "cg" if s.startswith("center of gravity")
                           else "mcg" if s.startswith("moment about the center") else "anf" if s.startswith("area") else None)
                    if lab is None:
                        cur = None
                    else:
                        cur = ("stat", cur[1], lab)
                continue
            m = _HIST_RE.match(s)
            if m:
                k = m.group(1)
                try:
                    t = float(m.group(3))
                except ValueError:
                    t = 0.0
                rows = [] if k in ("stresses", "strains", "equivalent plastic strain") else ({} if not k.startswith("total") else [])
                cur = (k, rows)
                out.setdefault((k, m.group(2)), []).append((t, rows))
                continue
            if cur is None:
                continue
            p = s.split()
            try:
                if isinstance(cur[1], dict):
                    cur[1][int(p[0])] = [float(v) for v in p[1:] if v != "L"]
                elif cur[0].startswith("total"):
                    cur[1].extend(float(v) for v in p)
                else:
                    vals = []
                    for v in p[2:]:
                        try:
                            vals.append(float(v))
                        except ValueError:
                            break
                    cur[1].append((int(p[0]), int(p[1]), vals))
            except (ValueError, IndexError):
                cur = None
    return out


LIVE_EVERY = 1.5


def read_sta(path):
    """Increments of a CalculiX .sta file: [{"step", "inc", "att", "cut" (attempt with cutback), "itrs", "tot",
    "time", "dt"}] (times in s)."""
    out = []
    try:
        f = open(path, "r", errors="replace")
    except OSError:
        return out
    with f:
        for line in f:
            p = line.split()
            if len(p) != 7:
                continue
            try:
                out.append({"step": int(p[0]), "inc": int(p[1]), "att": int(p[2].rstrip("U")), "cut": p[2].endswith("U"),
                            "itrs": int(p[3]), "tot": float(p[4]), "time": float(p[5]), "dt": float(p[6])})
            except ValueError:
                continue
    return out


def sta_series(rows):
    """Request of the increments of the .sta file: increment size and iterations against the total time."""
    if len(rows) < 2:
        return None
    t = [r["tot"] for r in rows]
    return {"id": "_sta", "name": "Increments (job.sta)", "kind": "solver", "series": [
        {"name": "increment size", "unit": "s", "t": t, "v": [r["dt"] for r in rows]},
        {"name": "iterations", "unit": "-", "t": t, "v": [r["itrs"] for r in rows]},
        {"name": "attempt", "unit": "-", "t": t, "v": [r["att"] for r in rows]},
        {"name": "step", "unit": "-", "t": t, "v": [r["step"] for r in rows]}]}


def read_cvg(path, limit=4000):
    """Iterations of a CalculiX .cvg file: [{"step", "inc", "att", "iter", "cont" (contact elements), "force"
    (residual force, %), "disp" (displacement correction, %)}]; the last limit rows."""
    out = []
    try:
        f = open(path, "r", errors="replace")
    except OSError:
        return out
    with f:
        for line in f:
            p = line.split()
            if len(p) < 7:
                continue
            try:
                out.append({"step": int(p[0]), "inc": int(p[1]), "att": int(p[2]), "iter": int(p[3]), "cont": int(p[4]),
                            "force": float(p[5]), "disp": float(p[6])})
            except ValueError:
                continue
    return out[-limit:]


def cvg_series(rows):
    """Request of the iterations of the .cvg file: residual force and displacement correction (%, logarithmic
    axis), contact elements and attempt against the iteration count of the run; "incs": the first iteration of each
    increment ([iteration, step, increment, attempt])."""
    if not rows:
        return None
    t = list(range(1, len(rows) + 1))
    incs, last = [], None
    for k, r in enumerate(rows):
        key = (r["step"], r["inc"], r["att"])
        if key != last:
            incs.append([k + 1, r["step"], r["inc"], r["att"]])
            last = key
    return {"id": "_cvg", "name": "Convergence (job.cvg)", "kind": "solver", "x": "iteration", "ylog": True, "incs": incs,
            "series": [{"name": "residual force", "unit": "%", "t": t, "v": [r["force"] for r in rows]},
                       {"name": "displacement correction", "unit": "%", "t": t, "v": [r["disp"] for r in rows]},
                       {"name": "contact elements", "unit": "-", "t": t, "v": [r["cont"] for r in rows]},
                       {"name": "attempt", "unit": "-", "t": t, "v": [r["att"] for r in rows]}]}


LOG_TAIL = 24000


def log_tail(path, limit=LOG_TAIL):
    """The last limit bytes of the solver log, from a line start (the whole file when it is shorter); "" when
    the file does not exist."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            n = f.tell()
            f.seek(max(0, n - limit))
            b = f.read()
    except OSError:
        return ""
    t = b.decode("utf-8", errors="replace")
    if n > limit:
        t = t[t.find("\n") + 1:]
    return t


# stage of the CalculiX run from the last matching line of the log (the C output of ccx is written as it runs; the
# messages of the input reading are written when the solver exits)
_STAGES = [("Job finished", "Finished"),
           ("for the stress calculation", "Computing the stresses and writing the results"),
           ("Factoring the system", "Factorising the system of equations"),
           ("for spooles", "Factorising the system of equations"),
           ("PARDISO", "Factorising the system of equations"),
           ("stiffness/mass contributions", "Assembling the stiffness matrix"),
           ("structure of the matrix", "Setting up the matrix structure"),
           ("Decascading", "Reading the input file")]


def log_stage(text):
    """(stage, increment text) of the solver from the log text: stage is the computation step of the last matching
    line ("Reading the input file" when none matches); increment text is "increment i attempt a, iteration k" of a
    step with increments (None in a linear step, or when the text starts after the increment line)."""
    stage, inc = "Reading the input file", None
    best = -1
    for key, name in _STAGES:
        i = text.rfind(key)
        if i > best:
            best, stage = i, name
    if stage == "Computing the stresses and writing the results" and text.rfind("Factoring the system") < 0 and text.rfind("for spooles") < 0 \
            and text.rfind("PARDISO") < 0:
        stage = "Assembling the stiffness matrix"   # the first stress calculation comes before the stiffness matrix
    ms = list(re.finditer(r"increment (\d+) attempt (\d+)", text))
    if ms:
        m = ms[-1]
        inc = "increment %s attempt %s" % (m.group(1), m.group(2))
        its = list(re.finditer(r"\siteration (\d+)", text[m.end():]))
        if its:
            inc += ", iteration %s" % its[-1].group(1)
    return stage, inc


def _proc_stats(p):
    """(CPU time in s, resident memory in MB) of a running process, or None."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            h = wintypes.HANDLE(int(p._handle))
            ft = (ctypes.c_ulonglong * 4)()
            if not ctypes.windll.kernel32.GetProcessTimes(h, ctypes.byref(ft, 0), ctypes.byref(ft, 8), ctypes.byref(ft, 16), ctypes.byref(ft, 24)):
                return None
            cpu = (ft[2] + ft[3]) * 1e-7

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            mem = None
            if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
                mem = pmc.WorkingSetSize / 1048576.0
            return cpu, mem
        with open("/proc/%d/stat" % p.pid, "r") as f:
            parts = f.read().rsplit(")", 1)[1].split()
        tck = os.sysconf("SC_CLK_TCK")
        cpu = (int(parts[11]) + int(parts[12])) / float(tck)
        mem = int(parts[21]) * os.sysconf("SC_PAGE_SIZE") / 1048576.0
        return cpu, mem
    except Exception:
        return None


class RunMonitor(object):
    """Run monitor of a CalculiX run: the increments of job.sta, the iterations of job.cvg, the history requests of
    job.dat, the tail of solver.log with the stage of the solver, the CPU use and memory of the ccx process and an
    estimate of the remaining time from the increments so far. snapshot() is the data sent with the job polls."""

    def __init__(self, M, workdir, proc=None, threads=None):
        self.M, self.workdir, self.proc, self.threads = M, workdir, proc, threads
        self.t0 = time.time()
        self.periods = M.step_periods()
        self.samples = []               # (elapsed s, total time s) at each change of the total time
        self.stages = []                # [{"name", "t0" (elapsed s)}]: the stages before the increments, Increments, Finished
        self.cpu = None                 # (elapsed s, CPU s) of the last sample
        self.cpu_pct = None

    def snapshot(self, final=False):
        wd = self.workdir
        el = time.time() - self.t0
        rows = read_sta(os.path.join(wd, "job.sta"))
        cvg = read_cvg(os.path.join(wd, "job.cvg"))
        th = history_series(self.M, os.path.join(wd, "job.dat")) if getattr(self.M, "hist", None) and self.M.atype == "static" else []
        st = sta_series(rows)
        text = log_tail(os.path.join(wd, "solver.log"))
        stage, inc = log_stage(text)
        if cvg:                         # the iteration from job.cvg (the log tail can start after the increment line)
            r = cvg[-1]
            inc = "step %d, increment %d, attempt %d, iteration %d" % (r["step"], r["inc"], r["att"], r["iter"])
        if final and stage != "Finished":
            stage = "Stopped"
        name = stage if inc is None or stage in ("Finished", "Stopped") else "Increments"
        if not self.stages or self.stages[-1]["name"] != name:          # the stages outside the increments
            self.stages.append({"name": name, "t0": round(el, 1)})
        tot = rows[-1]["tot"] if rows else None
        if tot is not None and (not self.samples or self.samples[-1][1] != tot):
            self.samples.append((el, tot))
        stats = _proc_stats(self.proc) if self.proc is not None and self.proc.poll() is None else None
        mem = None
        if stats is not None:
            cpu_s, mem = stats
            if self.cpu is not None and el - self.cpu[0] >= 1.0:
                self.cpu_pct = 100.0 * (cpu_s - self.cpu[1]) / (el - self.cpu[0])
                self.cpu = (el, cpu_s)
            elif self.cpu is None:
                self.cpu = (el, cpu_s)
        return {"sta": rows[-1] if rows else None, "n": len(rows), "time_history": th + ([st] if st else []),
                "cvg": cvg_series(cvg), "log": text, "stage": stage, "increment": inc, "stages": self.stages,
                "elapsed": round(el, 1), "threads": self.threads, "cpu_pct": None if self.cpu_pct is None else round(self.cpu_pct),
                "mem_mb": None if mem is None else round(mem), "estimate": self.estimate(tot), "final": final}

    def estimate(self, tot):
        """{"total" (s of analysis time), "done" (fraction), "remaining" (s)} from the rate of the last increments;
        None without two increments."""
        T = sum(self.periods)
        if tot is None or T <= 0 or len(self.samples) < 2:
            return None
        recent = self.samples[-6:]
        (e0, t0), (e1, t1) = recent[0], recent[-1]
        if t1 <= t0 or e1 <= e0:
            return None
        rate = (t1 - t0) / (e1 - e0)
        return {"total": T, "done": min(1.0, tot / T), "remaining": round(max(0.0, T - tot) / rate)}


def live_state(M, workdir):
    """Run monitor data of a work folder (one snapshot without a process)."""
    return RunMonitor(M, workdir).snapshot()


def _final_history(M, workdir):
    """Time history of the result: the history requests and the increments of the .sta file (None: neither)."""
    if M.atype != "static":
        return None
    th = history_series(M, os.path.join(workdir, "job.dat")) if getattr(M, "hist", None) else []
    st = sta_series(read_sta(os.path.join(workdir, "job.sta")))
    return (th + ([st] if st else [])) or None


def history_series(M, dat_path):
    """Curves of the time history requests of a solved model: [{"id", "name", "kind", "series": [{"name", "unit",
    "t", "v"}]}]; time is the total time (s; static steps: step time 1 per step)."""
    blocks = read_history(dat_path)
    out = []

    def vm(c):
        sx, sy, sz, txy, txz, tyz = (list(c) + [0] * 6)[:6]
        return math.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (txy ** 2 + txz ** 2 + tyz ** 2))

    def eqs(c):                     # equivalent strain (von Mises), engineering shear strains
        ex, ey, ez, gxy, gxz, gyz = (list(c) + [0] * 6)[:6]
        return math.sqrt(2.0 / 9 * ((ex - ey) ** 2 + (ey - ez) ** 2 + (ez - ex) ** 2) + 1.0 / 3 * (gxy ** 2 + gxz ** 2 + gyz ** 2))
    for h in getattr(M, "hist", []):
        ser = []

        def add(name, unit, pts):
            if pts:
                ser.append({"name": name, "unit": unit, "t": [p[0] for p in pts], "v": [p[1] for p in pts]})
        if h["kind"] == "node":
            for key, lab, unit in (("displacements", "u", "mm"), ("velocities", "v", "mm/s")):
                bl = blocks.get((key, h["set"])) or []
                if not bl or (lab == "u" and "U" not in h["q"]) or (lab == "v" and "V" not in h["q"]):
                    continue
                for i, c in enumerate("xyz"):
                    add("%s%s mean" % (lab, c), unit, [(t, float(np.mean([r[i] for r in rows.values()]))) for t, rows in bl if rows])
                add("|%s| max" % lab, unit, [(t, float(max(np.linalg.norm(r[:3]) for r in rows.values()))) for t, rows in bl if rows])
            bl = blocks.get(("total force", h["set"])) or []
            if "RF" in h["q"]:
                for i, c in enumerate("xyz"):
                    add("RF%s total" % c, "N", [(t, rows[i]) for t, rows in bl if len(rows) > i])
        elif h["kind"] == "element":
            es = h["elset"]
            if "S" in h["q"]:
                bl = blocks.get(("stresses", es)) or []
                add("von Mises max", "MPa", [(t, max(vm(c) for _e, _i, c in rows)) for t, rows in bl if rows])
                add("von Mises mean", "MPa", [(t, float(np.mean([vm(c) for _e, _i, c in rows]))) for t, rows in bl if rows])
            if "E" in h["q"]:
                bl = blocks.get(("strains", es)) or []
                add("equivalent strain max", "-", [(t, max(eqs(c) for _e, _i, c in rows)) for t, rows in bl if rows])
            if "PEEQ" in h["q"]:
                bl = blocks.get(("equivalent plastic strain", es)) or []
                add("PEEQ max", "-", [(t, max(c[0] for _e, _i, c in rows if c)) for t, rows in bl if rows])
            if "ENER" in h["q"]:
                add("internal energy", "mJ", [(t, rows[0]) for t, rows in blocks.get(("total internal energy", es)) or [] if rows])
            if "EKIN" in h["q"]:
                add("kinetic energy", "mJ", [(t, rows[0]) for t, rows in blocks.get(("total kinetic energy", es)) or [] if rows])
        else:                       # contact (CF) and section (SOF, SOM): statistics blocks
            key = ("contact", h["slave"]) if h["kind"] == "contact" else ("section", h["surf"])
            bl = [(t, r) for t, r in blocks.get(key) or [] if len(r.get("force") or []) >= 3]
            for i, c in enumerate("xyz"):
                add("F%s total" % c, "N", [(t, r["force"][i]) for t, r in bl])
            add("normal force (+ = tension)", "N", [(t, r["anf"][1]) for t, r in bl if len(r.get("anf") or []) > 1])
            add("shear force", "N", [(t, r["anf"][2]) for t, r in bl if len(r.get("anf") or []) > 2])
            if h["kind"] == "section":
                add("torque", "N mm", [(t, r["anf"][3]) for t, r in bl if len(r.get("anf") or []) > 3])
                add("bending moment", "N mm", [(t, r["anf"][4]) for t, r in bl if len(r.get("anf") or []) > 4])
                for i, c in enumerate("xyz"):
                    add("M%s about the centre" % c, "N mm", [(t, r["mcg"][i]) for t, r in bl if len(r.get("mcg") or []) > i])
            add("area", "mm^2", [(t, r["anf"][0]) for t, r in bl if r.get("anf")])
        out.append({"id": h["h"].get("id"), "name": h["name"], "kind": h["kind"], "series": ser})
    return out


def read_dat_incs(path):
    """Blocks of every increment of a .dat file: {(step, increment): {(kind, set): rows}} (rows as read_dat)."""
    out = {}
    step, inc = 0, 1
    kind = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("S T E P"):
                step, inc, kind = int(s.split()[-1]), 1, None
                continue
            if s.startswith("INCREMENT"):
                try:
                    inc = int(s.split()[-1])
                except ValueError:
                    pass
                kind = None
                continue
            m = re.match(r"(displacements|forces|stresses|total force)\b.*for set (\S+)", s)
            if m:
                k = {"total force": "total"}.get(m.group(1), m.group(1))
                kind = (k, m.group(2))
                out.setdefault((step, inc), {})[kind] = [] if k in ("stresses", "total") else {}
                continue
            if kind is None:
                continue
            parts = s.split()
            blk = out[(step, inc)]
            try:
                if kind[0] == "stresses":
                    blk[kind].append((int(parts[0]), int(parts[1]), [float(v) for v in parts[2:]]))
                elif kind[0] == "total":
                    blk[kind] = [float(v) for v in parts]
                else:
                    blk[kind][int(parts[0])] = [float(v) for v in parts[1:] if v != "L"]
            except (ValueError, IndexError):
                kind = None
    return out


def read_frd(path, want=("DISP", "STRESS", "PE")):
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


def read_frd_shell_map(path, model):
    """Expanded nodes of the shell nodes: {shell node: [expanded nodes]}. CalculiX writes a shell element to the .frd
    as its expanded 3D element (same element number; composite shells: one element per layer, numbered after all
    elements of the input); the bottom and top nodes of each element follow the order of the shell nodes
    (SHELL_EXPANSION)."""
    shells = {e[0]: (bl["type"], e[1:]) for mb in model.mesh["bodies"].values() for bl in mb["blocks"]
              if bl["type"] in SHELL_ELEMS for e in bl["elements"]}
    if not shells or not os.path.isfile(path):
        return {}
    top = int(getattr(model, "next_elem", 0) or 0) or (max(shells) + 1)
    els, cur, inblock = {}, None, False
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith("    3C"):
                inblock = True
                continue
            if not inblock:
                continue
            if line.startswith(" -3"):
                break
            if line.startswith(" -1"):
                cur = int(line[3:13])
                els[cur] = [] if cur in shells or cur >= top else None
            elif line.startswith(" -2") and els.get(cur) is not None:
                s = line.rstrip("\n")
                els[cur] += [int(s[k:k + 10]) for k in range(3, len(s) - 9, 10) if s[k:k + 10].strip()]
    # composite shells (*SHELL SECTION, COMPOSITE): CalculiX writes one expanded element per layer, numbered after
    # all elements of the input, in the order of the shell elements and of the layers
    layers = {}
    for es, bid, _m in getattr(model, "body_sets", []):
        nl = int(model.bodies[bid].get("shell_layers") or 1)
        typ, elems = model.elsets.get(es, (None, []))
        if typ == "S8R" and nl > 1:
            for e in elems:
                layers[e[0]] = nl
    missing = sorted(e for e in shells if not els.get(e))
    extra = iter(sorted(e for e in els if e >= top and els[e]))
    stack = {e: [els[e]] for e in shells if els.get(e)}
    for e in missing:
        stack[e] = [els.get(next(extra, None)) or [] for _ in range(layers.get(e, 1))]
    out = {}
    for eid, (typ, nn) in shells.items():
        for x in stack.get(eid) or []:
            for i, (a, b) in enumerate(SHELL_EXPANSION[typ]):
                if i < len(nn) and b < len(x):
                    out.setdefault(nn[i], set()).update((x[a], x[b]))
    return {n: sorted(v) for n, v in out.items()}


def shell_results(blocks, smap):
    """Shell node results from the expanded nodes: displacement the mean of the bottom and top layers, stress the
    tensor of the layer with the larger von Mises stress. blocks: {name: {node: values}} (in place)."""
    if not smap:
        return
    U, S, PE = blocks.get("DISP"), blocks.get("STRESS"), blocks.get("PE")
    for n, xs in smap.items():
        if PE is not None:
            v = [PE[x][0] for x in xs if x in PE]
            if v:
                PE[n] = [max(v)]
        if U is not None:
            v = [U[x] for x in xs if x in U]
            if v:
                U[n] = list(np.mean(np.asarray([w[:3] for w in v], float), axis=0))
        if S is not None:
            v = [S[x] for x in xs if x in S]
            if v:
                S[n] = max(v, key=von_mises)


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
            m = re.match(r"(displacements|forces|stresses|total force|equivalent plastic strain)\b.*for set (\S+)", s)
            if m:
                k = {"total force": "total", "equivalent plastic strain": "peeq"}.get(m.group(1), m.group(1))
                kind = (k, m.group(2))
                out.setdefault(step, {})[kind] = [] if k in ("stresses", "total", "peeq") else {}
                continue
            if kind is None:
                continue
            parts = s.split()
            try:
                if kind[0] in ("stresses", "peeq"):
                    vals = []
                    for v in parts[2:]:                     # shell rows end with the name of the expanded element
                        try:
                            vals.append(float(v))
                        except ValueError:
                            break
                    out[step][kind].append((int(parts[0]), int(parts[1]), vals))
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
    """Results of a solved model: states "preload" (step 1, fasteners with preload), "loads" and "total". A nonlinear
    solve: "total" (end of the last step), "preload", and one state "i<k>" per output increment (incs: read_frd_incs,
    dat_incs: read_dat_incs), the loads of an increment scaled by its step time."""

    def __init__(self, model, frd, dat, incs=None, dat_incs=None):
        self.m = model
        steps = sorted(dat)
        if not steps:
            raise AnalysisError("the solver wrote no results")
        self.nonlinear = bool(incs)
        self.kidx = {}
        self.kscale = {}
        self.increments = []
        self._lcache = {}
        N = len(model.user_steps or [1])
        if N > 1 or model.multistep():
            self._init_steps(model, frd, dat, incs, dat_incs, steps)
            return
        pre = len(steps) == 2
        if pre:
            self.kidx = {steps[0]: 0, steps[1]: 1}
        if self.nonlinear:
            self.state_steps = {"total": [steps[-1]]}
            if pre:
                self.state_steps["preload"] = [steps[0]]
            frd, dat = dict(frd), dict(dat)
            sel = list(range(len(incs)))
            if len(sel) > MAX_INC_STATES:
                sel = sorted(set([int(round(i * (len(incs) - 1) / float(MAX_INC_STATES - 1))) for i in range(MAX_INC_STATES)]))
            for j, i in enumerate(sel):
                stp, inc, t, blocks = incs[i]
                lab = "i%d" % (j + 1)
                frd[lab] = blocks
                dat[lab] = (dat_incs or {}).get((stp, inc)) or {}
                self.state_steps[lab] = [lab]
                self.kidx[lab] = 0 if (pre and stp == steps[0]) else 1
                self.kscale[lab] = float(t)
                self.increments.append({"state": lab, "step": stp, "inc": inc, "time": float(t), "preload": bool(pre and stp == steps[0])})
        else:
            self.state_steps = {"total": steps}
            if pre:
                self.state_steps.update(preload=[steps[0]], loads=[steps[1]])
        self._finish(model, frd, dat, pre)

    def _init_steps(self, model, frd, dat, incs, dat_incs, steps):
        """States of several steps (or step factors and amplitudes): "s<k>" at the end of step k, "total" at the end
        of the last step, "i<j>" per output increment (incremental steps), the loads of a state from the load parts
        (Model.part_weight)."""
        pre = any(f.get("spring") for f in model.fasteners)
        off = 1 if pre else 0
        N = len(model.user_steps)
        ccx = {k: k + off for k in range(1, N + 1)}               # user step -> solver step
        if len(steps) < N + off:
            raise AnalysisError("the solver wrote results for %d of %d steps (see the solver log)" % (len(steps) - off, N))
        times = ([model.user_steps[0]["time"]] if pre else []) + [st["time"] for st in model.user_steps]
        start = {}
        acc = 0.0
        for i, T in enumerate(times):
            start[i + 1] = acc
            acc += T
        frd, dat = dict(frd), dict(dat)
        self.state_steps = {}
        if pre:
            self.state_steps["preload"] = [steps[0]]
            self.kidx[steps[0]] = 0
        for k in range(1, N + 1):
            lab = "s%d" % k
            frd[lab], dat[lab] = frd.get(ccx[k]) or {}, dat.get(ccx[k]) or {}
            self.state_steps[lab] = ([steps[0]] if pre and not self.nonlinear else []) + [lab]   # linear steps: the preload added
            self.kidx[lab] = k
            self.kscale[lab] = 1.0
        self.state_steps["total"] = ["s%d" % N]
        if self.nonlinear:
            sel = list(range(len(incs)))
            if len(sel) > MAX_INC_STATES:
                sel = sorted(set([int(round(i * (len(incs) - 1) / float(MAX_INC_STATES - 1))) for i in range(MAX_INC_STATES)]))
            for j, i in enumerate(sel):
                stp, inc, t, blocks = incs[i]
                lab = "i%d" % (j + 1)
                frd[lab] = blocks
                dat[lab] = (dat_incs or {}).get((stp, inc)) or {}
                self.state_steps[lab] = [lab]
                k = stp - off
                T = times[stp - 1] if 0 < stp <= len(times) else 1.0
                tau = max(0.0, min(1.0, (float(t) - start.get(stp, 0.0)) / T)) if T > 0 else 1.0
                self.kidx[lab] = max(k, 0)
                self.kscale[lab] = tau
                self.increments.append({"state": lab, "step": stp, "inc": inc, "time": float(t), "preload": bool(pre and stp == 1),
                                        "user_step": k if k >= 1 else None, "tau": tau})
        self._finish(model, frd, dat, pre)

    def _loads(self, k):
        """Nodal loads of a solver step or state and their factor: (dict, factor)."""
        idx = self.kidx.get(k, 1)
        if not self.m.multistep() or idx == 0:
            return self.m.cloads[idx], self.kscale.get(k, 1.0)
        if k not in self._lcache:
            tau = self.kscale.get(k, 1.0)
            st = self.m.user_steps[idx - 1]
            fb = tau if (idx == 1 and st["kind"] == "static") else 1.0
            out = {kk: fb * v for kk, v in (getattr(self.m, "base_loads", None) or {}).items()}
            for p in self.m.load_parts:
                w = self.m.part_weight(p, idx, tau)
                if w:
                    for kk, v in p["full"].items():
                        out[kk] = out.get(kk, 0.0) + w * v
            self._lcache[k] = out
        return self._lcache[k], 1.0

    def _qvec(self, info, k):
        """Line load (N/mm) of a member in a state."""
        idx = self.kidx.get(k, 1)
        if not self.m.multistep():
            return info["q"] * self.kscale.get(k, 1.0)
        if idx == 0:
            return np.zeros(3)
        mi = self.m.members.index(info)
        tau = self.kscale.get(k, 1.0)
        q = np.zeros(3)
        rest = np.asarray(info["q"], float)
        for p in self.m.load_parts:
            if mi in p["dq"]:
                rest = rest - p["dq"][mi]
                q = q + self.m.part_weight(p, idx, tau) * p["dq"][mi]
        st = self.m.user_steps[idx - 1]
        return q + rest * (tau if (idx == 1 and st["kind"] == "static") else 1.0)

    def _finish(self, model, frd, dat, pre):
        self.frd, self.dat = frd, dat
        self.U = {}
        self.S = {}
        self.PE = {}
        for st, ss in self.state_steps.items():
            U, S, PE = {}, {}, {}
            for k in ss:
                for n, v in ((frd.get(k) or {}).get("DISP") or {}).items():
                    U[n] = U.get(n, 0) + np.asarray(v[:3])
                for n, v in ((frd.get(k) or {}).get("STRESS") or {}).items():
                    S[n] = S.get(n, 0) + np.asarray(v[:6])
                for n, v in ((frd.get(k) or {}).get("PE") or {}).items():
                    PE[n] = float(v[0]) if v else 0.0
            self.PE[st] = PE
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
        q = self._qvec(info, steps[0]) if (with_q and steps) else np.zeros(3)
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
                    rows = self._beam_rows(info, steps, with_q=self._qf(st, steps))
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
                        cl, f_ = self._loads(k)
                        dk = self.dat.get(k) or {}
                        for n, v in (dk.get(("forces", sp["nset"])) or {}).items():
                            F += np.array([v[i] - f_ * cl.get((n, i + 1), 0.0) if (i + 1) in sp["dofs"] else 0.0 for i in range(3)])
                        for n, v in (dk.get(("forces", sp["rot"]["nset"])) or {}).items():
                            Mo += np.array([v[i] - f_ * cl.get((n, i + 1), 0.0) if (i + 1) in sp["rot"]["dofs"] else 0.0 for i in range(3)])
                elif sp["member"] and not self.m.b31:
                    n = nodes[0]
                    acc = self._node_elem_forces(steps, with_q=self._qf(st, steps))
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
                        cl, f_ = self._loads(k)
                        if self.m.multistep() and idx >= 1:
                            eqd = {}
                            for info in self.m.members:
                                for kk, v in self.m._q_nodal(info, self._qvec(info, k)).items():
                                    eqd[kk] = eqd.get(kk, 0.0) + v
                            ef = 1.0
                        else:
                            eqd, ef = (self.m.eq_loads, f_) if idx == 1 else ({}, 0.0)
                        for d in range(6):
                            P[d] += f_ * cl.get((n, d + 1), 0.0) - ef * eqd.get((n, d + 1), 0.0)
                    F = -P[:3] - f
                    Mo = -P[3:] - m
                    fixed = sp["dofs"]
                    F = np.array([F[i] if (i + 1) in fixed else 0.0 for i in range(3)])
                    Mo = np.array([Mo[i] if (i + 4) in fixed else 0.0 for i in range(3)])
                else:
                    # RF of the solver is the internal nodal force; loads applied at the fixed DOFs go to the support
                    for k in steps:
                        cl, f_ = self._loads(k)
                        rf = (self.dat.get(k) or {}).get(("forces", sp["nset"])) or {}
                        for n, v in rf.items():
                            v = np.asarray(v[:3], float)
                            p = f_ * np.array([cl.get((n, d), 0.0) for d in (1, 2, 3)])
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
            cl, f_ = self._loads(k)
            for (n, d), v in cl.items():
                if d <= 3 and n not in pts and n not in self.m.rp_rot_nodes:
                    tot[d - 1] += f_ * v
        return tot

    def load_index(self, k):
        """Load set of a solver step or increment state: 0 preload, 1 loads."""
        return self.kidx.get(k, 1)

    def sc(self, k):
        """Load factor of a solver step (1) or of an increment state (its step time)."""
        return self.kscale.get(k, 1.0)

    def _qf(self, st, steps):
        """Factor of the member line loads of a state: 0 in the preload step."""
        if st == "preload" or not steps or self.load_index(steps[0]) == 0:
            return 0.0
        return self.sc(steps[0])

    # ------------------------------------------------------------------ summaries
    def body_max(self, st):
        """Per body: max displacement magnitude, the ux, uy, uz of largest magnitude (signed), max von Mises stress
        with their node positions."""
        out = []
        for bid, mb in self.m.mesh["bodies"].items():
            nodes = set()
            for bl in mb["blocks"]:
                for e in bl["elements"]:
                    nodes.update(e[1:])
            U, S = self.U[st], self.S[st]
            umax, un, smax, sn = 0.0, None, 0.0, None
            ucomp = [0.0, 0.0, 0.0]                  # component of largest magnitude (signed)
            for n in nodes:
                u = U.get(n)
                if u is not None:
                    v = float(np.linalg.norm(u[:3]))
                    if v > umax:
                        umax, un = v, n
                    for i in range(3):
                        if abs(float(u[i])) > abs(ucomp[i]):
                            ucomp[i] = float(u[i])
                s = S.get(n)
                if s is not None:
                    v = von_mises(s)
                    if v > smax:
                        smax, sn = v, n
            PEs = (getattr(self, "PE", {}) or {}).get(st) or {}
            out.append({"id": bid, "name": self.m.bodies[bid]["name"], "umax": umax, "ucomp": ucomp,
                        "upos": self.m.X[un].tolist() if un else None, "smax": smax,
                        "spos": self.m.X[sn].tolist() if sn else None,
                        "pemax": max([PEs.get(n, 0.0) for n in nodes] or [0.0]) if PEs else None})
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
        tri_elem = []                    # element of each triangle (mesh selection of elements)
        elems_of = {}                    # node -> elements (corner nodes of the facets only)
        for mb in m.mesh["bodies"].values():
            for bl in mb["blocks"]:
                for e in bl["elements"]:
                    for n in e[1:]:
                        elems_of.setdefault(n, []).append(e[0])

        def facet_elem(f):
            c = set(elems_of.get(f[0], ()))
            for n in f[1:3]:
                c &= set(elems_of.get(n, ()))
            return min(c) if c else 0
        edges = set()                    # element edges of the facets (quadrangles without their diagonals)
        EDGE_LOOP = {3: (0, 1, 2), 4: (0, 1, 2, 3), 6: (0, 3, 1, 4, 2, 5), 8: (0, 4, 1, 5, 2, 6, 3, 7)}
        for bid, mb in m.mesh["bodies"].items():
            start = len(tris)
            for s in mb["surfaces"]:
                k = (len(s["nodes"]), tuple(s["nodes"][:8]), tuple(s["nodes"][-8:]))
                if count[k] > 1:
                    continue
                for f in s["facets"]:
                    t0 = len(tris)
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
                    tri_elem += [facet_elem(f)] * (len(tris) - t0)
            mbd = m.bodies[bid]
            shell = bool(mb["blocks"]) and all(bl["type"] in SHELL_ELEMS for bl in mb["blocks"])
            bodies.append({"id": bid, "name": mbd["name"], "start": start, "count": len(tris) - start,
                           "t": float(mbd.get("t") or 0) if shell else None,          # shell thickness (mm), offset in t
                           "offset": SHELL_OFFSET.get(mbd.get("offset"), 0.0) if shell else None})
        lines = []
        for info in m.members:
            lines.append({"kind": info["kind"], "name": info["name"], "segs": [[ix(a), ix(b)] for e, a, b in info["elems"]]})
        for info in m.fasteners:
            lines.append({"kind": "fastener", "name": info["name"], "segs": [[ix(a), ix(b)] for e, a, b in info["elems"]]})
        bcs = []
        for sp in m.supports:
            s0 = sp.get("s") or {}
            rot = sp.get("rot") or {}
            rnodes = set(sp.get("rnset") and m.nsets.get(sp["rnset"]) or ([rot["node"]] if rot.get("node") is not None else []))
            bcs.append({"id": s0.get("id"), "name": sp["name"], "nodes": [ix(n) for n in sp["nodes"]], "dofs": sorted(sp["dofs"]),
                        "rnodes": [ix(n) for n in sorted(rnodes)], "rdofs": sorted(d - 3 if d > 3 else d for d in (sp.get("rdofs") or rot.get("dofs") or [])),
                        "prescribed": any(abs(v) > 0 for v in list((sp.get("values") or {}).values()) + list((sp.get("rvalues") or {}).values())
                                          + list((rot.get("values") or {}).values())),
                        "normal": sp.get("trans") is not None})
        loadv = []
        for lv in getattr(m, "load_vis", []):
            per = {}
            for (n, d), v in ({} if lv["type"] == "gravity" else lv["nodal"]).items():
                per.setdefault(n, [0.0] * 6)[d - 1] += v
            f = [(ix(n), q[:3]) for n, q in per.items() if any(abs(x) > 0 for x in q[:3])]
            mo = [(ix(n), q[3:]) for n, q in per.items() if any(abs(x) > 0 for x in q[3:])]
            loadv.append({"id": lv["id"], "name": lv["name"], "type": lv["type"],
                          "value": lv["value"] if lv["type"] == "gravity" else None,
                          "f": [[i] + [float(x) for x in q] for i, q in f], "m": [[i] + [float(x) for x in q] for i, q in mo]})
        rpv = []
        for pid, rp in getattr(m, "rps", {}).items():
            if pid.startswith("_sup_"):
                continue
            ns = list(rp.get("nodes") or [])
            k = max(1, len(ns) // 400 + 1)
            rpv.append({"id": pid, "name": rp["name"], "node": ix(rp["ref"]), "nodes": [ix(n) for n in ns[::k]]})
        links = [{"id": v["id"], "kind": "spring", "a": ix(v["a"]), "b": ix(v["b"]) if v["b"] is not None else None}
                 for v in getattr(m, "spring_vis", [])]
        links += [{"id": v["id"], "kind": "joint", "a": ix(v["a"]), "b": ix(v["b"])} for v in getattr(m, "joint_vis", [])]
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
            PEs = getattr(self, "PE", {}).get(st) or {}
            if PEs:
                pe = np.asarray([PEs.get(n, 0.0) if n in body_nodes else 0.0 for n in nodes], float)
                states[st]["pe"] = b64(pe, np.float32)
                states[st]["pemax"] = float(pe.max()) if len(pe) else 0.0
        return {"count": len(nodes), "pos": b64(np.asarray(pos) if pos else np.zeros((0, 3)), np.float32),
                "tri": b64(np.asarray(tris) if tris else np.zeros((0, 3)), np.uint32), "bodies": bodies,
                "edges": b64(np.asarray(sorted(edges)) if edges else np.zeros((0, 2)), np.uint32),
                "lines": lines, "states": states, "bcs": bcs, "loads": loadv, "rps": rpv, "links": links,
                "node_ids": b64(np.asarray(nodes, np.int64), np.uint32), "tri_elem": b64(np.asarray(tri_elem, np.int64), np.uint32)}

    def history(self):
        """Nonlinear solve: per output increment the step time, max |u|, max von Mises, max equivalent plastic strain,
        the reaction of each support and the displacement of each reference point."""
        rows = []
        bnodes = set(n for mb in self.m.mesh["bodies"].values() for bl in mb["blocks"] for e in bl["elements"] for n in e[1:])
        for inc in getattr(self, "increments", []):
            st = inc["state"]
            U, S, PE = self.U[st], self.S[st], self.PE.get(st) or {}
            rows.append({"state": st, "step": inc["step"], "inc": inc["inc"], "time": inc["time"], "preload": inc["preload"],
                         "umax": max([float(np.linalg.norm(u[:3])) for u in U.values()] or [0.0]),
                         "vmmax": max([von_mises(v) for n, v in S.items() if n in bnodes] or [0.0]),
                         "pemax": max(list(PE.values()) or [0.0]),
                         "reactions": [[float(x) for x in r["states"][st]["F"]] for r in self.reactions],
                         "points": [[float(x) for x in (U.get(rp["ref"]) if U.get(rp["ref"]) is not None else np.zeros(3))[:3]]
                                    for pid, rp in self.m.rps.items() if not pid.startswith("_sup_")]})
        return {"rows": rows, "supports": [r["name"] for r in self.reactions],
                "points": [rp["name"] for pid, rp in self.m.rps.items() if not pid.startswith("_sup_")]}

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
    LAWN = {"elastic": "elastic", "plastic": "plastic", "hyper": "hyperelastic"}
    mrows = []
    for n, v0 in (doc.get("materials") or {}).items():
        if n not in m.mat_names:
            continue
        v = material_values(v0)
        law = LAWN.get(v.get("law") or "elastic", "elastic")
        if law == "plastic":
            law += " (%s)" % ("kinematic" if v.get("hardening") == "kinematic" else "isotropic")
        mrows.append([n, _g(float(v.get("E") or 0), 6), _g(float(v.get("nu") or 0), 3), _g(float(v.get("rho") or 0), 5), law])
    L += _table(["Name", "E (MPa)", "nu", "rho (kg/m^3)", "Law"], mrows, [30, 14, 8, 14, 30])
    for n, v0 in (doc.get("materials") or {}).items():
        v = material_values(v0)
        if n in m.mat_names and (v.get("law") or "elastic") == "plastic":
            L += ["", "%s: hardening table%s" % (n, " (library %s)" % v["library"] if v.get("library") else "")]
            L += _table(["Yield stress (MPa)", "Plastic strain"], [[_g(a, 6), _g(b, 6)] for a, b in v.get("plastic") or []], [24, 20])
        if n in m.mat_names and (v.get("law") or "elastic") == "hyper":
            L += ["", "%s: %s, C10 %s MPa, C01 %s MPa, D1 %s 1/MPa" % (n, "Mooney-Rivlin" if v.get("hyper") == "mooney" else "Neo-Hooke",
                                                                      _g(float(v.get("C10") or 0)), _g(float(v.get("C01") or 0)), _g(float(v.get("D1") or 0)))]
    L += ["", "1.2  Bodies"]
    rows = []
    for bid, mb in m.mesh["bodies"].items():
        b = m.bodies[bid]
        mname = next(mn for es, bb, mn in m.body_sets if bb == bid)
        els = " + ".join("%d %s" % (len(bl["elements"]), bl["type"]) for bl in mb["blocks"])
        rows.append([b["name"][:28], {"plate": "plate"}.get(b["mode"], "solid"), mname[:18], els[:24],
                     _g(float(b["shape"].volume if b.get("shape") is not None else b.get("volume") or 0), 6)])
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
    if m.contact_defs:
        L += ["", "Contact pairs"]
        TN = {"surface": "surface-to-surface", "node": "node-to-surface", "tied": "tied"}
        L += _table(["Pair", "Type", "Master faces", "Slave", "Friction", "K (N/mm^3)"],
                    [[c["label"], TN[c["type"]], str(len(c["master"])),
                      ("%d faces" % len(c["slave"])) if c.get("slave") else "%d nodes" % len(c["slave_nodes"]),
                      _g(c["friction"]) if c["type"] != "tied" else "-", _g(c["K"]) if c["type"] != "tied" else "-"] for c in m.contact_defs],
                    [24, 22, 14, 14, 10, 12])
    if m.atype == "static" and (m.incremental() or len(m.user_steps) > 1):
        KN = {"static": "static", "dynamic": "dynamic (implicit, alpha %s)", "explicit": "dynamic (explicit)"}
        L += ["", "Steps%s%s:" % (" (nonlinear, increments)" if m.incremental() else "", ", large deformation (NLGEOM)" if m.nlgeom() else "")]
        rows = []
        for k, st in enumerate(m.user_steps):
            kind = KN[st["kind"]] % _g(st["alpha"]) if st["kind"] == "dynamic" else KN[st["kind"]]
            loads = ", ".join("%s x%s" % (p["name"], _g(p["f"][k])) + (" (amplitude)" if p["amp"] else "") for p in m.load_parts if p["f"][k]) or "-"
            rows.append([st["name"][:20], kind[:30], _g(st["time"]), "%s / %s / %s" % (_g(st["inc0"] * st["time"]), _g(st["incmin"] * st["time"]), _g(st["incmax"] * st["time"])),
                         str(st["maxinc"]), loads[:40]])
        L += _table(["Step", "Kind", "Time (s)", "Increments (s)", "Max", "Loads"], rows, [20, 24, 10, 22, 6, 14])
        rel = [sp["name"] for sp in m.supports for st in m.user_steps if step_factor(sp.get("s") or {}, st["id"]) == 0]
        if rel:
            L.append("Supports released in a step: %s." % ", ".join(sorted(set(rel))))
        if m.b31:
            L.append("Beams written as B31 elements (expanded to 3D elements by CalculiX); section forces of the beams are not given.")
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
        L += ["", "Reference points (coupling: rigid, kinematic, distributing or none)"]
        L += _table(["Point", "x (mm)", "y (mm)", "z (mm)", "Coupling", "Nodes", "Member ends"],
                    [[rp["name"][:24]] + [_g(float(v), 6) for v in rp["xyz"]] + [rp.get("coupling") or "rigid", str(len(rp["nodes"])), str(len(rp["joints"]))]
                     for rp in m.rps.values()], [24, 11, 11, 11, 14, 10, 13])
    cdoc = m.doc
    if cdoc.get("springs") or cdoc.get("joints") or cdoc.get("equations"):
        L += ["", "Springs, joints and equations"]
        rows = []
        for sp in cdoc.get("springs") or []:
            k = (list(sp.get("k") or []) + [0] * 6)[:6]
            rows.append([(sp.get("name") or "")[:24], "spring" + ("" if sp.get("b") else " to ground"),
                         " ".join("%s=%s" % (constraints.DOF_NAMES[i], _g(float(k[i]), 4)) for i in range(6) if float(k[i] or 0) > 0)])
        for j in cdoc.get("joints") or []:
            rows.append([(j.get("name") or "")[:24], "joint " + (j.get("type") or "ball"),
                         "axis (%s)" % ", ".join(_g(float(v), 4) for v in (j.get("axis") or [0, 0, 1])) if j.get("type") == "hinge" else ""])
        pname = {str(p.get("id")): p.get("name") or p.get("id") for p in cdoc.get("points") or []}
        endtxt = lambda e: pname.get(str((e or {}).get("point")), "?") if (e or {}).get("point") is not None else \
            "(%s)" % ", ".join(_g(float(v), 4) for v in ((e or {}).get("at") or []))
        for q in cdoc.get("equations") or []:
            rows.append([(q.get("name") or "")[:24], "equation", (" + ".join("%s %s %s" % (_g(float(t.get("coef") or 0), 4), endtxt(t.get("end")),
                                                                                         constraints.DOF_NAMES[int(t.get("dof") or 1) - 1])
                                                                        for t in q.get("terms") or []) + " = 0")[:52]])
        L += _table(["Name", "Kind", "Definition"], rows, [26, 18, 52])
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


def run(doc, asm, sources, workdir, ccx, progress=None, mesh_only=False, meta=None, procs=None, mesh=None, keep=False):
    """Meshes, writes the input file, runs CalculiX and reads the results. Returns {"payload", "tables", "report",
    "summary", "files"}; with mesh_only the mesh payload and the model summary. mesh: a femesh output to use instead
    of meshing (the bodies of the document must be in it; other bodies of it are left out). keep: the result also
    holds "model" (the Model) and "frd" (the result blocks of the .frd)."""
    from build123d import export_brep
    from . import femesh
    doc = resolve_surfaces(doc)
    say = progress or (lambda *a: None)
    meta = dict(meta or {})
    os.makedirs(workdir, exist_ok=True)
    for fn in os.listdir(workdir):
        if fn.startswith("job.") or fn.endswith(".brep") or fn.startswith("solver") or fn.endswith("_report.txt"):
            try:
                os.remove(os.path.join(workdir, fn))
            except OSError:
                pass
    inp_src = (doc.get("source") or {}).get("type") == "inp"
    if inp_src:                     # a meshed CalculiX .inp: its nodes and elements (inpmodel)
        from . import inpmodel
        say("geometry", "Reading the .inp")
        try:
            bodies, mesh = inpmodel.analysis_input(doc)
        except (inpmodel.InpError, OSError) as e:
            raise AnalysisError("inp: %s" % e)
        if not bodies:
            raise AnalysisError("inp: no bodies (all off)")
    else:
        say("geometry", "Placing the bodies")
        bodies = geometry(doc, asm, sources)
    mopt = doc.get("mesh") or {}
    job = {"size": float(mopt.get("size") or 0), "bonded": bool(doc.get("bonded", True)), "bodies": [],
           "apart": sorted(set(x for p in contact_body_pairs(doc, bodies) for x in p)),
           "mesh": {k: mopt.get(k) for k in ("size_min", "curvature", "algorithm", "optimize", "strategy", "tet_type", "hex_type",
                                             "shell_type", "shell_algorithm", "shell_structured", "shell_min_div", "shell_size_mode",
                                             "fuzzy")
                    if mopt.get(k) is not None},
           "refine": [] if inp_src else refine_boxes(doc, bodies)}
    for b in (bodies if mesh is None else []):
        p = os.path.join(workdir, "body_%s.brep" % re.sub(r"[^A-Za-z0-9]+", "_", b["id"]))
        export_brep(b["shape"], p)
        job["bodies"].append({"id": b["id"], "brep": p, "mode": b["mode"], "size": b["size"], "layers": b["layers"],
                              "normal": b.get("normal"), "strategy": b.get("strategy"), "t": b.get("t")})
    t0 = time.time()
    if mesh is not None:
        missing = [b["name"] for b in bodies if b["id"] not in mesh["bodies"]]
        if missing:
            raise AnalysisError("not in the given mesh: %s" % ", ".join(missing))
        ids = set(b["id"] for b in bodies)
        mesh = dict(mesh, bodies={k: v for k, v in mesh["bodies"].items() if k in ids})
    else:
        say("mesh", "Meshing %d bodies" % len(bodies))
        mesh = femesh.run(job) if bodies else {"nodes": {"ids": [], "xyz": []}, "bodies": {}, "warnings": []}
    say("model", "Building the model")

    def summ(M):
        nel = sum(len(bl["elements"]) for b in mesh["bodies"].values() for bl in b["blocks"]) + \
            sum(len(i["elems"]) for i in M.members + M.fasteners)
        return {"nodes": len(M.X), "elements": nel, "mesh_time": round(time.time() - t0, 2),
                "bodies": [{"id": bid, "name": M.bodies[bid]["name"],
                            "elements": sum(len(bl["elements"]) for bl in mb["blocks"]),
                            "types": [bl["type"] for bl in mb["blocks"]]} for bid, mb in mesh["bodies"].items()],
                "ties": len(M.ties), "warnings": M.warnings, "shell": mesh.get("shell_report"),
                "contacts": len(M.contact_defs)}
    publish = getattr(progress, "mesh_ready", None)
    M = Model(doc, bodies, mesh)
    try:
        M.build(mesh_only=mesh_only)
    except AnalysisError:
        if publish is not None and not mesh_only:        # the mesh with the items that could be applied
            try:
                Mm = Model(doc, bodies, mesh)
                Mm.build(mesh_only=True)
                publish({"payload": mesh_payload(Mm), "summary": summ(Mm)})
            except Exception:
                pass
        raise
    inp = os.path.join(workdir, "job.inp")
    M.write(inp, meta.get("name") or "analysis")
    summary = summ(M)
    meta.update(nodes=len(M.X), elements=summary["elements"], inp=inp)
    if publish is not None and not mesh_only:
        publish({"payload": mesh_payload(M), "summary": summary})
    if mesh_only:
        return {"payload": mesh_payload(M), "summary": summary, "files": {"inp": inp}}
    if not ccx:
        raise AnalysisError("CalculiX (ccx) not found: set the solver path in the analysis settings")
    say("solve", "Solving (%d nodes)" % len(M.X))
    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(procs or max(1, (os.cpu_count() or 2)))
    env["CCX_NPROC_STIFFNESS"] = env["OMP_NUM_THREADS"]
    log = os.path.join(workdir, "solver.log")
    for fn in ("spooles.out", "job.sta", "job.cvg", "job.dat"):
        try:
            os.remove(os.path.join(workdir, fn))
        except OSError:
            pass
    t1 = time.time()
    mon = None
    with open(log, "w") as lf:
        p = subprocess.Popen([ccx, "-i", "job"], cwd=workdir, stdout=lf, stderr=subprocess.STDOUT, env=env,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if progress is not None and hasattr(progress, "proc"):
            progress.proc = p
        live = getattr(progress, "live", None) if progress is not None else None
        if live is None:
            p.wait()
        else:                           # run monitor: increments, iterations, log and process every LIVE_EVERY s
            mon = RunMonitor(M, workdir, p, int(env["OMP_NUM_THREADS"]))
            t_live = 0.0
            while p.poll() is None:
                time.sleep(0.1)
                if time.time() - t_live >= LIVE_EVERY:
                    t_live = time.time()
                    try:
                        live(mon.snapshot())
                    except Exception:
                        pass
    with open(log, "r", errors="replace") as f:
        text = f.read()
    run_info = None
    if mon is not None:
        try:
            run_info = mon.snapshot(final=True)
            live(run_info)
        except Exception:
            run_info = None
    if "Job finished" not in text:
        errs = _ccx_errors(text)
        try:
            with open(os.path.join(workdir, "spooles.out"), "r", errors="replace") as f:
                if "singular" in f.read():
                    errs.insert(0, "the stiffness matrix is singular (a body, reference point or component without support or stiffness)")
        except OSError:
            pass
        raise AnalysisError("solver failed: %s (see %s)" % ("; ".join(errs[:3]) or (text.strip().splitlines() or ["no output"])[-1], log))
    summary["solve_time"] = round(time.time() - t1, 2)
    say("results", "Reading the results")
    smap = read_frd_shell_map(os.path.join(workdir, "job.frd"), M)
    if M.atype == "static":
        frd = read_frd(os.path.join(workdir, "job.frd"))
        for blocks in frd.values():
            shell_results(blocks, smap)
        dat = read_dat(os.path.join(workdir, "job.dat"))
        if M.incremental():
            incs = read_frd_incs(os.path.join(workdir, "job.frd"))
            for _s, _i, _t, blocks in incs:
                shell_results(blocks, smap)
            res = Results(M, frd, dat, incs, read_dat_incs(os.path.join(workdir, "job.dat")))
        else:
            res = Results(M, frd, dat)
    else:
        modes = read_frd_modes(os.path.join(workdir, "job.frd"))
        for b in modes:
            shell_results({"DISP": b}, smap)
        res = ModeResults(M, modes, read_eigen(os.path.join(workdir, "job.dat")))
    meta["solver"] = ccx
    rep = report(res, meta)
    rp = os.path.join(workdir, "%s_report.txt" % re.sub(r"[^A-Za-z0-9_\-.]+", "_", meta.get("name") or "analysis"))
    with open(rp, "w", encoding="utf-8") as f:
        f.write(rep)
    summary["atype"] = M.atype
    summary["nonlinear"] = bool(M.atype == "static" and M.incremental())
    summary["steps"] = [{"id": st["id"], "name": st["name"], "kind": st["kind"], "time": st["time"]} for st in M.user_steps]
    summary["contacts"] = [{"name": c["label"], "type": c["type"], "master": len(c["master"]),
                            "slave": len(c.get("slave") or c["slave_nodes"])} for c in M.contact_defs]
    out = {"payload": res.payload(), "tables": res.tables(), "summary": summary, "states": list(res.state_steps),
           "history": res.history() if M.atype == "static" and getattr(res, "nonlinear", False) else None,
           "time_history": _final_history(M, workdir),
           "increments": getattr(res, "increments", None) or None,
           "run": None if run_info is None else {k: run_info.get(k) for k in ("cvg", "log", "stages", "elapsed", "threads", "sta", "n")},
           "atype": M.atype, "modes": res.modes() if M.atype != "static" else None,
           "files": {"inp": inp, "report": rp, "frd": os.path.join(workdir, "job.frd"), "dat": os.path.join(workdir, "job.dat"),
                     "log": log}}
    if keep:
        out["model"] = M
        out["frd"] = frd if M.atype == "static" else None
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
