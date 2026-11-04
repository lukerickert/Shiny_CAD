"""Abaqus .inp of the ShinyCAD model of an explicit document, for the deck build (inp2rad).

Explicit document (<name>.exp.json), model part:
  {"source": {"kind": "shinycad", "type": "assembly" | "part", "name"} | {"kind": "inp", "inp": path},
   "materials": {name: {"library": MATERIAL_LIBRARY key or "", "E": MPa, "nu", "rho": kg/m^3}},
   "default_material": name,
   "mesh": {"size": mm, "size_min": mm, "curvature", "algorithm", "optimize", "strategy": "tet" | "hex" | "hexsub",
            "tet_type": "C3D4" | "C3D10", "hex_type": "C3D8R" | "C3D8", "shell_type": "S4R" | "S4" | "S3",
            "shell_algorithm": "quasi" | "frontal" | "delaunay" | "tri"},
   "bonded": bool                     touching deformable bodies and shells share nodes,
   "bodies": {component id: {"role": "deformable" | "rigid" | "off", "material", "size", "strategy"}},
   "shells": {"<component id>:<surface id>": {"mode": "shell" | "rigid" | "off", "t": mm, "offset": "mid" |
              "positive" | "negative", "material", "size"}},
   "sections": [{"id", "name", "faces": [face references], "mode": "shell" | "rigid" | "off", "t", "offset",
                 "material", "size", "color"}]   faces of surface bodies of any components with one shell section,
   "nsets": [node set (analysis.Model.node_set)]   written as *NSET, NSET=<NAME>,
   "supports": [{"id", "name", "target": face reference | {"comp", "edge"} | {"nset": id} | {"point": id} |
                 {"faces": [face refs], "edges": [edge refs], "bodies": [body ids]},
                 "dofs": [ux, uy, uz, rx, ry, rz] (1 = held)}],
   "points", "springs", "joints", "equations": reference points and constraints (drawgen/constraints.py),
   "velocities": [{"id", "name", "target": {"body": body id} | {"point": id} | {"nset": id},
                   "kind": "initial" | "imposed", "v": [vx, vy, vz] mm/s, "w": [wx, wy, wz] rad/s (imposed),
                   "dofs": [6 flags] (imposed), "ramp": s (imposed: 0 to the value in ramp s, then constant)}],
   "masses": [{"id", "name", "kind": "point", "target": {"point": id}, "m": kg} |
              {"id", "name", "kind": "distributed", "target": {"faces": [face references]} | {"body": body id} |
               {"nset": id}, "mode": "total" | "area", "m": kg (total) | kg/m^2 (area, faces only)}]}

The .inp holds *NODE, one *ELEMENT block per body (ELSET B_<body>), *SOLID SECTION per solid body and *SHELL SECTION
per shell (surface body of a part or a STEP file), *MATERIAL with *ELASTIC and *DENSITY (t/mm^3), *RIGID BODY (NSET
RB_<body>, REF NODE at the centre of mass of the body) for the rigid bodies, and *BOUNDARY for the supports
(translations on all nodes of the face or edge, rotations on its shell nodes and reference points). Reference points
are nodes; a rigid coupling is a *RIGID BODY (NSET RP_<point>, REF NODE the point; inp2rad /RBODY). Kinematic and
distributing couplings, springs (spring to ground: a node held in all six components, NSET SPRING_GROUND), joints and
equations are Radioss cards in **RAD comment lines (radcards.py: /RBE2, /RBE3, /PROP/TYPE13 with /SPRING, /MPC). A
reference point coupled to the nodes of one rigid body is a node of that rigid body (its NSET RB_<body>): velocities
and supports of the point act on the REF NODE of the body, exact when the point is at the REF NODE or the rotations are
held (imposed angular velocity 0). Masses are /ADMAS type 5 cards (**RAD lines): a point mass on the node of a
reference point; a distributed mass on the nodes of faces (consistent area weights; total kg or kg/m^2), of a body
(element volume, shell element area, equal shares of the element corners) or of a node set (equal shares). The REF
NODE of a rigid body is at the centre of mass of the body with the masses on its nodes. A material with a library entry is
written with the E, nu and density of the entry; the build replaces it with the library card (library slot: the
material name). Rigid bodies are meshed apart from the deformable bodies (no shared nodes).
"""
import os
import re

import numpy as np

from .constants import MATERIAL_LIBRARY


class ModelError(Exception):
    pass


def safe(s, n=40):
    return (re.sub(r"[^A-Za-z0-9_]+", "_", str(s or "")).strip("_") or "X")[:n]


def material_values(doc, name):
    """(E MPa, nu, rho t/mm^3, library key) of a material of the document."""
    m = (doc.get("materials") or {}).get(name)
    if m is None:
        raise ModelError("material %s is not defined" % name)
    lib = m.get("library") or ""
    if lib and MATERIAL_LIBRARY.get(lib):
        e = MATERIAL_LIBRARY[lib]
        return float(e["E"]), float(e["nu"]), float(e["rho"]), lib
    try:
        return float(m["E"]), float(m["nu"]), float(m["rho"]) * 1e-12, ""
    except (KeyError, TypeError, ValueError):
        raise ModelError("material %s: E, nu and rho are required" % name)


def library_slots(doc):
    """Library slots of the build for the materials with a library entry: [[library key, model material name]]."""
    out = []
    for name, m in (doc.get("materials") or {}).items():
        lib = (m or {}).get("library") or ""
        if lib and MATERIAL_LIBRARY.get(lib):
            out.append([lib, safe(name, 60).upper()])
    return out


SHELL_OFFSET = {"positive": "SPOS", "negative": "SNEG"}


def _geometry_doc(doc):
    bodies = {}
    for cid, b in (doc.get("bodies") or {}).items():
        bodies[cid] = {"mode": "off" if b.get("role") == "off" else "solid", "size": b.get("size"),
                       "strategy": b.get("strategy"), "material": b.get("material")}
    shells = {}
    for k, b in (doc.get("shells") or {}).items():
        shells[k] = dict(b, mode="off" if b.get("mode") == "off" else "shell")
    sections = [dict(x, mode="off" if x.get("mode") == "off" else "shell") for x in doc.get("sections") or []]
    return {"bodies": bodies, "shells": shells, "sections": sections, "nsets": doc.get("nsets") or [], "plates": [],
            "members": [], "materials": {}, "default_material": None}


def _mesh_group(group, doc, opts, size, bonded, workdir, tag):
    from build123d import export_brep
    from .. import femesh
    job = {"size": size, "bonded": bonded, "bodies": [], "mesh": opts}
    for b in group:
        p = os.path.join(workdir, "%s_%s.brep" % (tag, safe(b["id"])))
        export_brep(b["shape"], p)
        job["bodies"].append({"id": b["id"], "brep": p, "mode": "shell" if b.get("mode") == "shell" else "solid",
                              "size": b.get("size"), "strategy": b.get("strategy"), "t": b.get("t")})
    return femesh.run(job)


def _merge(meshes):
    """Merges femesh outputs, renumbering nodes and elements of the later meshes."""
    out = {"nodes": {"ids": [], "xyz": []}, "bodies": {}, "warnings": []}
    noff = eoff = 0
    for m in meshes:
        ids = m["nodes"]["ids"]
        out["nodes"]["ids"] += [i + noff for i in ids]
        out["nodes"]["xyz"] += m["nodes"]["xyz"]
        emax = 0
        for bid, mb in m["bodies"].items():
            blocks = []
            for bl in mb["blocks"]:
                els = [[e[0] + eoff] + [n + noff for n in e[1:]] for e in bl["elements"]]
                emax = max([emax] + [e[0] for e in bl["elements"]])
                blocks.append({"type": bl["type"], "elements": els})
            surfs = [{"nodes": [n + noff for n in s["nodes"]], "facets": [[n + noff for n in f] for f in s["facets"]],
                      "sample": s["sample"]} for s in mb["surfaces"]]
            out["bodies"][bid] = {"blocks": blocks, "surfaces": surfs, "group": mb.get("group"), "thickness": mb.get("thickness")}
        out["warnings"] += m.get("warnings") or []
        noff += (max(ids) if ids else 0)
        eoff += emax
    return out


def _body_material(doc, b):
    if b.get("mode") == "shell":
        cfg = (doc.get("shells") or {}).get(b["id"]) or next((x for x in doc.get("sections") or [] if "sec:%s" % x.get("id") == b["id"]), {})
    else:
        cfg = (doc.get("bodies") or {}).get(b["id"]) or {}
    return cfg.get("material") or doc.get("default_material") or next(iter(doc.get("materials") or {}), None)


def _body_mass(doc, b):
    """Mass of a body (t): volume x density, shells area x t x density."""
    name = _body_material(doc, b)
    if not name:
        return 0.0
    rho = material_values(doc, name)[2]
    try:
        if b.get("mode") == "shell":
            return float(b["shape"].area) * float(b.get("t") or 0) * rho
        return float(b["shape"].volume) * rho
    except Exception:
        return 0.0


def _tet_vol(a, b, c, d):
    return abs(float(np.dot(b - a, np.cross(c - a, d - a)))) / 6.0


_HEX_TETS = ((0, 1, 3, 4), (1, 2, 3, 6), (1, 4, 5, 6), (3, 4, 6, 7), (1, 3, 4, 6))
_WEDGE_TETS = ((0, 1, 2, 3), (1, 2, 3, 4), (2, 3, 4, 5))


def _element_shares(X, blocks):
    """{node: share} of the element measures (volume of solids, area of shells) split equally over the corners."""
    from . import meshview
    out = {}
    for bl in blocks:
        kind = meshview.inp_kind(bl["type"])
        nc = meshview.NCORNER.get(kind, 0)
        for e in bl["elements"]:
            c = e[1:1 + nc]
            P = [X[n] for n in c]
            if kind == "tet":
                v = _tet_vol(*P)
            elif kind == "hex":
                v = sum(_tet_vol(*[P[i] for i in t]) for t in _HEX_TETS)
            elif kind == "wedge":
                v = sum(_tet_vol(*[P[i] for i in t]) for t in _WEDGE_TETS)
            elif kind == "tri":
                v = 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
            elif kind == "quad":
                v = 0.5 * float(np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[1])))
            else:
                continue
            for n in c:
                out[n] = out.get(n, 0.0) + v / len(c)
    return out


def _in_sections(bodies, bid):
    """[(section body id, (component id, face index))] of the faces of the surface body bid meshed in sections."""
    return [(b["id"], key) for b in bodies for key, sb in (b.get("surf_of") or {}).items() if sb == bid]


def _masses(doc, M, mesh, bodies):
    """[(mass entry, {node or ("rp", point id): mass t})] of the masses of the document."""
    from .. import analysis
    out = []
    pids = set(str(p.get("id")) for p in doc.get("points") or [])
    for k, mm in enumerate(doc.get("masses") or []):
        what = "mass %s" % (mm.get("name") or k + 1)
        try:
            m = float(mm.get("m") or 0)
        except (TypeError, ValueError):
            m = 0.0
        if not m > 0:
            raise ModelError("%s: the mass must be greater than 0" % what)
        t = mm.get("target") or {}
        try:
            if (mm.get("kind") or "point") == "point":
                if t.get("point") is None or str(t["point"]) not in pids:
                    raise ModelError("%s: choose the reference point" % what)
                out.append((mm, {("rp", str(t["point"])): m * 1e-3}))
                continue
            area = mm.get("mode") == "area"
            if t.get("faces"):
                w = {}
                for fr in t["faces"]:
                    f = M.face(fr)
                    for n in f["nodes"]:
                        w[n] = w.get(n, 0.0) + float(f["w"].get(n, 0.0) or 0.0)
            elif area:
                raise ModelError("%s: a mass per area needs faces" % what)
            elif t.get("body") is not None:
                # a surface body with faces in sections: the elements of its own faces and the faces in the sections
                mb = mesh["bodies"].get(str(t["body"]))
                sec = _in_sections(bodies, str(t["body"]))
                if not mb and not sec:
                    raise ModelError("%s: body %s is not meshed (off)" % (what, t["body"]))
                w = _element_shares(M.X, mb["blocks"]) if mb else {}
                for _sid, (cid, fi) in sec:
                    f = M.face({"comp": cid, "face": fi})
                    for n in f["nodes"]:
                        w[n] = w.get(n, 0.0) + float(f["w"].get(n, 0.0) or 0.0)
            elif t.get("nset") is not None:
                ns = next((x for x in doc.get("nsets") or [] if str(x.get("id")) == str(t["nset"])), None)
                if ns is None:
                    raise ModelError("%s: node set not found" % what)
                w = {n: 1.0 for n in M.node_set(ns)}
            else:
                raise ModelError("%s: choose the faces, body or node set" % what)
        except analysis.AnalysisError as e:
            raise ModelError("%s: %s" % (what, e))
        tot = sum(w.values())
        if not tot > 0:
            raise ModelError("%s: no nodes" % what)
        if area:
            out.append((mm, {n: m * 1e-9 * x for n, x in w.items()}))        # kg/m^2 -> t/mm^2
        else:
            out.append((mm, {n: m * 1e-3 * x / tot for n, x in w.items()}))
    return out


def file_md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mesh_path(inp_path):
    return os.path.splitext(inp_path)[0] + "_mesh.json.gz"


def save_mesh(inp_path, mesh, roles):
    """The mesh of the bodies (femesh output, node and element numbers of the .inp) and the role of each body, next to
    the .inp (<stem>_mesh.json.gz) for the static solve of the initial state (initstate.py)."""
    import gzip
    import json
    with gzip.open(mesh_path(inp_path), "wt", encoding="utf-8") as f:
        json.dump({"inp_md5": file_md5(inp_path), "roles": roles,
                   "mesh": {"nodes": mesh["nodes"], "bodies": mesh["bodies"]}}, f)


def load_mesh(inp_path):
    import gzip
    import json
    p = mesh_path(inp_path)
    if not os.path.isfile(p):
        raise ModelError("no mesh of %s: Mesh first" % os.path.basename(inp_path))
    with gzip.open(p, "rt", encoding="utf-8") as f:
        d = json.load(f)
    if not os.path.isfile(inp_path) or d.get("inp_md5") != file_md5(inp_path):
        raise ModelError("the mesh file does not belong to %s: Mesh again" % os.path.basename(inp_path))
    return d


def build(doc, asm, sources, workdir, inp_path, title="", progress=None):
    """Meshes the bodies and writes the .inp. Returns {"inp", "payload", "summary"}."""
    from .. import analysis
    from . import meshview
    say = progress or (lambda *a: None)
    os.makedirs(workdir, exist_ok=True)
    gdoc = _geometry_doc(doc)
    say("geometry", "Placing the bodies")
    try:
        bodies = analysis.geometry(gdoc, asm, sources)
    except analysis.AnalysisError as e:
        raise ModelError(str(e))
    if not bodies:
        raise ModelError("no bodies")
    role = {cid: (b.get("role") or "deformable") for cid, b in (doc.get("bodies") or {}).items()}
    for k, b in (doc.get("shells") or {}).items():
        role[k] = "rigid" if b.get("mode") == "rigid" else "off" if b.get("mode") == "off" else "deformable"
    sec_cfg = {"sec:%s" % x.get("id"): x for x in doc.get("sections") or []}
    for k, b in sec_cfg.items():
        role[k] = "rigid" if b.get("mode") == "rigid" else "off" if b.get("mode") == "off" else "deformable"
    deform = [b for b in bodies if role.get(b["id"], "deformable") == "deformable"]
    rigid = [b for b in bodies if role.get(b["id"]) == "rigid"]
    mopt = doc.get("mesh") or {}
    opts = {k: mopt.get(k) for k in ("size_min", "curvature", "algorithm", "optimize", "strategy", "tet_type", "hex_type",
                                     "shell_type", "shell_algorithm", "shell_structured", "shell_min_div", "shell_size_mode",
                                     "fuzzy")
            if mopt.get(k) not in (None, "")}
    opts.setdefault("tet_type", "C3D4")
    opts.setdefault("hex_type", "C3D8R")
    opts.setdefault("shell_type", "S4R")
    size = float(mopt.get("size") or 0)
    meshes = []
    say("mesh", "Meshing %d bodies" % len(bodies))
    try:
        if deform:
            meshes.append(_mesh_group(deform, doc, opts, size, bool(doc.get("bonded", True)), workdir, "d"))
        if rigid:
            meshes.append(_mesh_group(rigid, doc, opts, size, False, workdir, "r"))
    except RuntimeError as e:
        raise ModelError(str(e))
    shell_report = next((m.get("shell_report") for m in meshes if m.get("shell_report")), None)
    mesh = _merge(meshes)
    M = analysis.Model(gdoc, bodies, mesh)
    names = {b["id"]: b["name"] for b in bodies}
    used = set()
    bname = {}
    for b in bodies:
        n = safe(b["name"]).upper()
        k = 2
        while n in used:
            n = "%s_%d" % (safe(b["name"]).upper()[:36], k)
            k += 1
        used.add(n)
        bname[b["id"]] = n

    L = ["*HEADING", (title or "SHINYCAD explicit model")[:80],
         "** SHINYCAD explicit model. Units: mm, t, s, N, MPa. Density t/mm^3."]
    X = M.X
    from .. import constraints
    for p in doc.get("points") or []:
        xyz = p.get("xyz")
        if not xyz or len(xyz) != 3:
            raise ModelError("reference point %s has no coordinates" % (p.get("name") or p.get("id")))
    # nodes of the rigid bodies; reference points coupled to a rigid body (nodes of that rigid body)
    rigid_mesh_nodes = {b["id"]: set(n for bl in (mesh["bodies"].get(b["id"]) or {}).get("blocks", []) for e in bl["elements"] for n in e[1:])
                        for b in rigid}
    rp_targets, rp_rigid = {}, {}
    for p in doc.get("points") or []:
        pid, what = str(p.get("id")), "reference point %s" % (p.get("name") or p.get("id"))
        if constraints.coupling_of(p) == "none":
            continue
        if not (p.get("faces") or p.get("edges") or p.get("nsets")):
            raise ModelError("%s: pick the faces, edges or node sets it is coupled to (or Coupling none)" % what)
        try:
            w = constraints.target_nodes(M, p)
        except (constraints.ConstraintError, analysis.AnalysisError) as e:
            raise ModelError("%s: %s" % (what, e))
        rp_targets[pid] = w
        on = [bid for bid, ns in rigid_mesh_nodes.items() if ns.intersection(w)]
        if on:
            if len(on) > 1 or not set(w) <= rigid_mesh_nodes[on[0]]:
                raise ModelError("%s: its nodes are on a rigid body and on other bodies" % what)
            rp_rigid[pid] = on[0]
    # masses: {node or ("rp", point id): mass t} per mass entry
    mass_rows = _masses(doc, M, mesh, bodies)
    ref_nodes = {}
    next_node = (max(X) if X else 0) + 1
    rp_xyz = {str(p.get("id")): np.asarray(p["xyz"], float) for p in doc.get("points") or []}
    rigid_mass = []                                 # mass of each rigid body (kg): material and added masses
    for b in rigid:
        c = b["shape"].center()
        com, mtot = np.array([c.X, c.Y, c.Z]) * 0.0, 0.0
        mb = _body_mass(doc, b)
        if mb > 0:
            com, mtot = np.array([c.X, c.Y, c.Z]) * mb, mb
        for _m, nm in mass_rows:
            for n, m in nm.items():
                if isinstance(n, tuple):
                    if rp_rigid.get(n[1]) != b["id"]:
                        continue
                    x = rp_xyz[n[1]]
                elif n in rigid_mesh_nodes[b["id"]]:
                    x = X[n]
                else:
                    continue
                com = com + m * x
                mtot += m
        if not mtot > 0:
            raise ModelError("rigid body %s has no mass: give its material a density or add a mass (Masses)" % b["name"])
        rigid_mass.append({"id": b["id"], "name": b["name"], "kg": mtot * 1e3, "added_kg": (mtot - max(mb, 0.0)) * 1e3,
                           "shell": b.get("mode") == "shell"})
        ref_nodes[b["id"]] = next_node
        X[next_node] = com / mtot if mtot > 0 else np.array([c.X, c.Y, c.Z])
        next_node += 1
    rp_node = {}                                    # reference point id -> node
    for p in doc.get("points") or []:
        rp_node[str(p.get("id"))] = next_node
        X[next_node] = rp_xyz[str(p.get("id"))]
        next_node += 1
    special = set(rp_node.values()) | set(ref_nodes.values())

    def end_node(end, what):
        end = end or {}
        if end.get("point") is not None:
            if str(end["point"]) not in rp_node:
                raise ModelError("%s: reference point %s not found" % (what, end["point"]))
            return rp_node[str(end["point"])]
        if end.get("at") is not None:
            q = np.asarray(end["at"], float)
            cand = [(float(np.linalg.norm(x - q)), n) for n, x in X.items() if n not in special]
            if not cand:
                raise ModelError("%s: no mesh node" % what)
            return min(cand)[1]
        raise ModelError("%s: pick the point" % what)
    spring_ends, ground = [], []                    # (spring, node a, node b); springs to ground: a held node at A
    for sp in doc.get("springs") or []:
        what = "spring %s" % (sp.get("name") or sp.get("id"))
        a = end_node(sp.get("a"), what)
        if sp.get("b"):
            b = end_node(sp.get("b"), what)
            if a == b:
                raise ModelError("%s: both ends are the same node" % what)
        else:
            b = next_node
            X[b] = np.array(X[a], float)
            ground.append(b)
            next_node += 1
        spring_ends.append((sp, a, b))
    L.append("*NODE")
    for n in sorted(X):
        p = X[n]
        L.append("%d, %.9g, %.9g, %.9g" % (n, p[0], p[1], p[2]))
    mat_of = {}
    nel = 0
    body_nodes = {}
    for b in bodies:
        mb = mesh["bodies"].get(b["id"])
        if not mb:
            continue
        es = "B_" + bname[b["id"]]
        nodes = set()
        for bl in mb["blocks"]:
            L.append("*ELEMENT, TYPE=%s, ELSET=%s" % (bl["type"], es))
            for e in bl["elements"]:
                vals = [str(v) for v in e]
                L.append(", ".join(vals[:16]) + ("," if len(vals) > 16 else ""))
                if len(vals) > 16:
                    L.append(", ".join(vals[16:]))
                nodes.update(e[1:])
                nel += 1
        body_nodes[b["id"]] = nodes
        cfg = sec_cfg.get(b["id"]) or ((doc.get("shells") if b.get("mode") == "shell" else doc.get("bodies")) or {}).get(b["id"]) or {}
        mname = cfg.get("material") or doc.get("default_material") or next(iter(doc.get("materials") or {}), None)
        if not mname:
            raise ModelError("body %s: no material" % b["name"])
        mat_of[b["id"]] = mname
    def ids_lines(ids):
        ids = sorted(ids)
        return [", ".join(str(v) for v in ids[k:k + 16]) for k in range(0, len(ids), 16)]
    for b in rigid:
        L.append("*NSET, NSET=RB_%s" % bname[b["id"]])
        L += ids_lines(set(body_nodes.get(b["id"], ())) | set(rp_node[k] for k, v in rp_rigid.items() if v == b["id"]))
    def on_rigid(pid, rot_held, w_zero, what):
        """REF NODE of the rigid body of a reference point on a rigid body (None for other points)."""
        if pid not in rp_rigid:
            return None
        main = ref_nodes[rp_rigid[pid]]
        off = float(np.linalg.norm(X[rp_node[pid]] - X[main]))
        if off > 1e-6 * max(M.diag, 1.0) and not (rot_held and w_zero):
            raise ModelError("%s: the reference point is on rigid body %s, %.4g mm from its REF NODE (centre of mass): "
                             "hold rx, ry, rz (angular velocity 0) or apply it to the body"
                             % (what, names[rp_rigid[pid]], off))
        return main
    sup_rows, rigid_rows = [], []
    bc_vis = []                                     # supports at the nodes (view data, bcglyphs.js)
    held = set()                                    # (node, component, support name) held by the supports
    rigid_nodes = set(n for b in rigid for n in body_nodes.get(b["id"], ()))
    for k, s in enumerate(doc.get("supports") or []):
        t = analysis.single_target(s.get("target"))
        if not t or (t.get("comp") is None and t.get("nset") is None and t.get("point") is None and not analysis.is_multi(t)):
            continue
        sname = s.get("name") or k + 1
        try:
            if analysis.is_multi(t):
                nodes = M.node_set(dict({x: t.get(x) or [] for x in analysis.MULTI_KEYS}, kind="selection",
                                        name="of support %s" % sname))
            elif t.get("point") is not None:
                if str(t["point"]) not in rp_node:
                    raise analysis.AnalysisError("reference point not found")
                dofs0 = (list(s.get("dofs") or [1, 1, 1]) + [0, 0, 0])[:6]
                main = on_rigid(str(t["point"]), all(dofs0[3:]), True, "support %s" % sname)
                nodes = [main if main is not None else rp_node[str(t["point"])]]
            elif t.get("nset") is not None:
                ns_ = next((x for x in doc.get("nsets") or [] if str(x.get("id")) == str(t["nset"])), None)
                if ns_ is None:
                    raise analysis.AnalysisError("node set not found")
                nodes = M.node_set(ns_)
            elif t.get("edge") is not None:
                nodes = M.edge({"comp": str(t["comp"]), "edge": int(t["edge"])})["nodes"]
            else:
                nodes = M.face({"comp": str(t["comp"]), "face": int(t["face"])})["nodes"]
        except analysis.AnalysisError as e:
            raise ModelError("support %s: %s" % (sname, e))
        if rigid_nodes.intersection(nodes):
            raise ModelError("support %s: the face or edge is on a rigid body" % sname)
        ns = "SUP_%d_%s" % (k + 1, safe(s.get("name") or "support", 30).upper())
        L.append("*NSET, NSET=%s" % ns)
        L += ids_lines(nodes)
        dofs = (list(s.get("dofs") or [1, 1, 1]) + [0, 0, 0])[:6]
        sup_rows += ["%s, %d, %d" % (ns, d + 1, d + 1) for d in range(3) if dofs[d]]
        held.update((n, d + 1, sname) for n in nodes for d in range(3) if dofs[d])
        rn = [n for n in nodes if n in M.shell_nodes or n in rp_node.values() or n in ref_nodes.values()]
        held.update((n, d + 1, sname) for n in rn for d in range(3, 6) if dofs[d])
        bc_vis.append({"id": s.get("id"), "name": str(sname), "nodes": list(nodes), "dofs": [d + 1 for d in range(3) if dofs[d]],
                       "rnodes": rn, "rdofs": [d - 2 for d in range(3, 6) if dofs[d]], "prescribed": False, "normal": False})
        if any(dofs[3:]) and rn:
            L.append("*NSET, NSET=%s_R" % ns)
            L += ids_lines(rn)
            sup_rows += ["%s_R, %d, %d" % (ns, d + 1, d + 1) for d in range(3, 6) if dofs[d]]
    if ground:
        L.append("*NSET, NSET=SPRING_GROUND")
        L += ids_lines(ground)
        sup_rows += ["SPRING_GROUND, %d, %d" % (d, d) for d in range(1, 7)]
    from .radcards import Cards
    cards = Cards()
    rot_ok = set(M.shell_nodes) | set(rp_node.values())
    coupled, rigid_rp_nodes = {}, {}
    for p in doc.get("points") or []:
        mode = constraints.coupling_of(p)
        name = safe(p.get("name") or p.get("id"), 30).upper()
        what = "reference point %s" % (p.get("name") or p.get("id"))
        if mode == "none":
            continue
        w = rp_targets[str(p.get("id"))]
        n = rp_node[str(p.get("id"))]
        if str(p.get("id")) in rp_rigid:
            coupled[str(p.get("id"))] = ("rigid body %s" % names[rp_rigid[str(p.get("id"))]], len(w))
            continue
        coupled[str(p.get("id"))] = (mode, len(w))
        if mode == "rigid":
            rigid_rp_nodes[str(p.get("id"))] = sorted(w)
        flags = constraints._flags(p.get("dofs"))
        if mode == "rigid":
            L.append("*NSET, NSET=RP_%s" % name)
            L += ids_lines(w)
            rigid_rows.append("*RIGID BODY, NSET=RP_%s, REF NODE=%d" % (name, n))
        elif mode == "kinematic":
            cards.rbe2("RP " + name, n, w, flags)
        else:
            cards.rbe3("RP " + name, n, w, flags)
    for sp, a, b in spring_ends:
        k = [float(x or 0) for x in (list(sp.get("k") or []) + [0] * 6)[:6]]
        if not any(v > 0 for v in k):
            raise ModelError("spring %s: no stiffness" % (sp.get("name") or sp.get("id")))
        cards.spring("SPRING " + safe(sp.get("name") or sp.get("id"), 30).upper(), a, b, k)

    def mpc_terms(rows, ends, what):
        out = []
        for row in rows:
            terms = []
            for e, d, c in row:
                n = ends[e]
                if d > 3 and n not in rot_ok:
                    raise ModelError("%s: %s needs rotations at the node (a reference point or a shell node)" % (what, constraints.DOF_NAMES[d - 1]))
                terms.append((n, d, c))
            out.append(terms)
        return out
    neq = 0
    for j in doc.get("joints") or []:
        what = "joint %s" % (j.get("name") or j.get("id"))
        ends = {"a": end_node(j.get("a"), what), "b": end_node(j.get("b"), what)}
        if ends["a"] == ends["b"]:
            raise ModelError("%s: both ends are the same node" % what)
        try:
            rows = constraints.joint_equations(None, j)
        except constraints.ConstraintError as e:
            raise ModelError(str(e))
        for k, terms in enumerate(mpc_terms(rows, ends, what)):
            cards.mpc("JOINT %s %d" % (safe(j.get("name") or j.get("id"), 30).upper(), k + 1), terms)
            neq += 1
    for q in doc.get("equations") or []:
        what = "equation %s" % (q.get("name") or q.get("id"))
        ends, row = {}, []
        for i, t in enumerate(q.get("terms") or []):
            ends[i] = end_node(t.get("end"), what)
            row.append((i, int(t.get("dof") or 1), float(t.get("coef") or 0)))
        if len(row) < 2:
            raise ModelError("%s: an equation needs two terms" % what)
        cards.mpc("EQUATION " + safe(q.get("name") or q.get("id"), 30).upper(), mpc_terms([row], ends, what)[0])
        neq += 1
    # velocities: initial (*INITIAL CONDITIONS, TYPE=VELOCITY; inp2rad /INIVEL/TRA) on all nodes of the target,
    # imposed (*BOUNDARY, TYPE=VELOCITY with an *AMPLITUDE; inp2rad /IMPVEL with /FUNCT) on the main node of a rigid
    # target, else on all its nodes
    rigid_of = {b["id"]: b for b in rigid}
    rp_mass = {}
    for _m, nm in mass_rows:
        for n, m in nm.items():
            if isinstance(n, tuple):
                rp_mass[n[1]] = rp_mass.get(n[1], 0.0) + m
    rp_spring = {}
    for _sp, a, b in spring_ends:
        rp_spring[a] = rp_spring[b] = True
    pid_name = {str(p.get("id")): p.get("name") or p.get("id") for p in doc.get("points") or []}
    vel_rows, imp_rows = [], []
    for k, v in enumerate(doc.get("velocities") or []):
        what = "velocity %s" % (v.get("name") or k + 1)
        t = v.get("target") or {}
        main = None
        try:
            if t.get("body") is not None:
                bid = str(t["body"])
                sec = _in_sections(bodies, bid)
                if bid not in body_nodes and not sec:
                    raise ModelError("%s: body %s is not meshed (off)" % (what, bid))
                nodes = set(body_nodes.get(bid, ()))
                for _sid, (cid, fi) in sec:
                    nodes.update(M.face({"comp": cid, "face": fi})["nodes"])
                # a surface body in a rigid section: the rigid body of the section
                owners = set(sid for sid, _k in sec) | ({bid} if bid in body_nodes else set())
                rig = [o for o in owners if o in rigid_of]
                if rig and len(owners) > 1:
                    raise ModelError("%s: body %s has faces in rigid section %s and in other sections or shells: choose "
                                     "the section" % (what, bid, rigid_of[rig[0]]["name"]))
                if rig:
                    main = ref_nodes[rig[0]]
                    nodes = set(body_nodes[rig[0]]) | {main}
            elif t.get("point") is not None:
                pid = str(t["point"])
                if pid not in rp_node:
                    raise ModelError("%s: reference point not found" % what)
                main = rp_node[pid]
                nodes = set(rigid_rp_nodes.get(pid, [])) | {main}
                if pid in rp_rigid:
                    f0 = (list(v.get("dofs") or [1, 1, 1, 0, 0, 0]) + [0] * 6)[:6]
                    w0 = [float(x or 0) for x in (list(v.get("w") or []) + [0, 0, 0])[:3]]
                    imp = (v.get("kind") or "initial") == "imposed"
                    main = on_rigid(pid, all(f0[3:]) if imp else True, not any(w0) if imp else True, what)
                    nodes = set(body_nodes[rp_rigid[pid]]) | {main, rp_node[pid]}
                elif pid not in rigid_rp_nodes and coupled.get(pid, ("none",))[0] != "none":
                    main = None
                    nodes = {rp_node[pid]}
                elif ((v.get("kind") or "initial") == "initial" and coupled.get(pid, ("none",))[0] == "none"
                      and not rp_mass.get(pid, 0) > 0 and not rp_spring.get(rp_node[pid])):
                    raise ModelError("%s: initial velocity on reference point %s, which has no mass and no coupling: add a point mass (Masses) or "
                                     "couple it to faces, edges or node sets" % (what, pid_name.get(pid, pid)))
            elif t.get("nset") is not None:
                ns_ = next((x for x in doc.get("nsets") or [] if str(x.get("id")) == str(t["nset"])), None)
                if ns_ is None:
                    raise ModelError("%s: node set not found" % what)
                nodes = set(M.node_set(ns_))
            else:
                raise ModelError("%s: choose the body, reference point or node set" % what)
        except analysis.AnalysisError as e:
            raise ModelError("%s: %s" % (what, e))
        ns = "VEL_%d_%s" % (k + 1, safe(v.get("name") or "velocity", 30).upper())
        vv = [float(x or 0) for x in (list(v.get("v") or []) + [0, 0, 0])[:3]]
        if (v.get("kind") or "initial") == "initial":
            L.append("*NSET, NSET=%s" % ns)
            L += ids_lines(nodes)
            vel_rows += ["%s, %d, %.9g" % (ns, d + 1, vv[d]) for d in range(3)]
            continue
        target = [main] if main is not None else sorted(nodes)
        w = [float(x or 0) for x in (list(v.get("w") or []) + [0, 0, 0])[:3]]
        f = (list(v.get("dofs") or [1, 1, 1, 0, 0, 0]) + [0] * 6)[:6]
        if not any(f):
            raise ModelError("%s: no component" % what)
        if any(f[3:]) and not all(n in M.shell_nodes or n in rp_node.values() or n in ref_nodes.values() for n in target):
            raise ModelError("%s: rotations need a rigid body, a reference point or shell nodes" % what)
        clash = sorted(set(sn for n, d, sn in held if n in set(target) and f[d - 1]))
        if clash:
            raise ModelError("%s: its nodes are held by support %s" % (what, ", ".join(map(str, clash))))
        L.append("*NSET, NSET=%s" % ns)
        L += ids_lines(target)
        tr = float(v.get("ramp") or 0)
        amp = "VA_%d" % (k + 1)
        pts = ([(0.0, 0.0), (tr, 1.0)] if tr > 0 else [(0.0, 1.0)]) + [(max(tr, 0.0) + 1e3, 1.0)]
        imp_rows.append((amp, pts, ["%s, %d, %d, %.9g" % (ns, d + 1, d + 1, (vv + w)[d]) for d in range(6) if f[d]]))
    nset_names = {}
    for ns_ in doc.get("nsets") or []:
        nm = safe(ns_.get("name") or ns_.get("id"), 40).upper()
        try:
            ids = M.node_set(ns_)
        except analysis.AnalysisError as e:
            raise ModelError(str(e))
        nset_names[nm] = len(ids)
        L.append("*NSET, NSET=%s" % nm)
        L += ids_lines(ids)
    written = set()
    for b in bodies:
        if b["id"] not in mat_of:
            continue
        mname = mat_of[b["id"]]
        if mname not in written:
            E, nu, rho, lib = material_values(doc, mname)
            L.append("*MATERIAL, NAME=%s" % safe(mname, 60).upper())
            if lib:
                L.append("** library material: %s" % lib)
            L += ["*ELASTIC", "%.9g, %.6g" % (E, nu), "*DENSITY", "%.6g" % rho]
            written.add(mname)
        if b.get("mode") == "shell":
            off = SHELL_OFFSET.get(b.get("offset"))
            L += ["*SHELL SECTION, ELSET=B_%s, MATERIAL=%s%s" % (bname[b["id"]], safe(mname, 60).upper(), ", OFFSET=%s" % off if off else ""),
                  "%.9g" % float(b["t"])]
        else:
            L.append("*SOLID SECTION, ELSET=B_%s, MATERIAL=%s" % (bname[b["id"]], safe(mname, 60).upper()))
    for b in rigid:
        L.append("*RIGID BODY, NSET=RB_%s, REF NODE=%d" % (bname[b["id"]], ref_nodes[b["id"]]))
    L += rigid_rows
    if sup_rows:
        L.append("*BOUNDARY")
        L += sup_rows
    if vel_rows:
        L.append("*INITIAL CONDITIONS, TYPE=VELOCITY")
        L += vel_rows
    for amp, pts, rows in imp_rows:
        L.append("*AMPLITUDE, NAME=%s" % amp)
        L.append(", ".join("%.9g, %.9g" % q for q in pts))
        L.append("*BOUNDARY, AMPLITUDE=%s , TYPE=VELOCITY" % amp)       # the blank ends the name for inp2rad
        L += rows
    mass_summary = []
    for mm, nm in mass_rows:
        nodes_m = {}
        for n, m in nm.items():
            node = rp_node[n[1]] if isinstance(n, tuple) else n
            nodes_m[node] = nodes_m.get(node, 0.0) + m
        cards.admas("MASS " + safe(mm.get("name") or mm.get("id"), 30).upper(), nodes_m)
        mass_summary.append({"name": mm.get("name") or mm.get("id"), "kind": mm.get("kind") or "point",
                             "kg": sum(nodes_m.values()) * 1e3, "nodes": len(nodes_m)})
    if cards.lines:
        L.append("** Radioss cards of the reference point couplings, springs, joints, equations and masses (written into the "
                 "_0000.rad after inp2rad: radcards.py)")
        L += cards.inp_lines()
    with open(inp_path, "w") as f:
        f.write("\n".join(L) + "\n")
    save_mesh(inp_path, mesh, {b["id"]: role.get(b["id"], "deformable") for b in bodies})

    # view data
    cells = []
    nodes_sorted = sorted(X)
    idx = {n: i for i, n in enumerate(nodes_sorted)}
    xyz = np.array([X[n] for n in nodes_sorted], float)
    for k, b in enumerate(bodies):
        mb = mesh["bodies"].get(b["id"])
        if not mb:
            continue
        for bl in mb["blocks"]:
            kind = meshview.inp_kind(bl["type"])
            nc = meshview.NCORNER[kind]
            conn = np.array([[idx[n] for n in e[1:1 + nc]] for e in bl["elements"]], np.int64).reshape(-1, nc)
            cells.append((kind, conn, np.full(len(conn), k, np.int64)))
    pl = meshview.payload(xyz, cells)
    pl["part_names"] = [names[b["id"]] for b in bodies]
    pl["bcs"] = [dict(v, nodes=[idx[n] for n in v["nodes"] if n in idx], rnodes=[idx[n] for n in v["rnodes"] if n in idx]) for v in bc_vis]
    pl["part_thick"] = [[float(b["t"]), {"positive": 0.5, "negative": -0.5}.get(b.get("offset"), 0.0)] if b.get("mode") == "shell" and b.get("t") else None
                        for b in bodies]
    summary = {"nodes": len(X), "elements": nel, "bodies": [
        {"id": b["id"], "name": names[b["id"]], "role": role.get(b["id"], "deformable"), "elset": "B_" + bname[b["id"]],
         "material": safe(mat_of.get(b["id"], ""), 60).upper(),
         "elements": sum(len(bl["elements"]) for bl in (mesh["bodies"].get(b["id"]) or {}).get("blocks", [])),
         "types": [bl["type"] for bl in (mesh["bodies"].get(b["id"]) or {}).get("blocks", [])],
         "ref_node": ref_nodes.get(b["id"])} for b in bodies],
        "supports": len(sup_rows), "warnings": mesh.get("warnings") or [], "shell": shell_report,
        "nsets": [{"name": k, "nodes": v} for k, v in nset_names.items()],
        "points": [{"name": p.get("name") or p.get("id"), "node": rp_node[str(p.get("id"))],
                    "coupling": coupled.get(str(p.get("id")), (constraints.coupling_of(p),))[0],
                    "nodes": coupled.get(str(p.get("id")), (None, 0))[1]}
                   for p in doc.get("points") or []],
        "springs": len(spring_ends), "equations": neq,
        "velocities": [{"name": v.get("name"), "kind": v.get("kind") or "initial"} for v in doc.get("velocities") or []],
        "masses": mass_summary, "rigid_mass": rigid_mass,
        "total_kg": sum(_body_mass(doc, b) for b in bodies if mesh["bodies"].get(b["id"])) * 1e3 + sum(x["kg"] for x in mass_summary)}
    return {"inp": inp_path, "payload": pl, "summary": summary}
