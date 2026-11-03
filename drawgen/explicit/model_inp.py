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
   "supports": [{"id", "name", "target": face reference | {"comp", "edge"}, "dofs": [ux, uy, uz, rx, ry, rz] (1 = held)}]}

The .inp holds *NODE, one *ELEMENT block per body (ELSET B_<body>), *SOLID SECTION per solid body and *SHELL SECTION
per shell (surface body of a part or a STEP file), *MATERIAL with *ELASTIC and *DENSITY (t/mm^3), *RIGID BODY (NSET
RB_<body>, REF NODE at the centre of mass of the body) for the rigid bodies, and *BOUNDARY for the supports
(translations on all nodes of the face or edge, rotations on its shell nodes). A material with a library entry is
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
    return {"bodies": bodies, "shells": shells, "plates": [], "members": [], "materials": {}, "default_material": None}


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
    deform = [b for b in bodies if role.get(b["id"], "deformable") == "deformable"]
    rigid = [b for b in bodies if role.get(b["id"]) == "rigid"]
    mopt = doc.get("mesh") or {}
    opts = {k: mopt.get(k) for k in ("size_min", "curvature", "algorithm", "optimize", "strategy", "tet_type", "hex_type",
                                     "shell_type", "shell_algorithm")
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
    ref_nodes = {}
    next_node = (max(X) if X else 0) + 1
    for b in rigid:
        c = b["shape"].center()
        ref_nodes[b["id"]] = next_node
        X[next_node] = np.array([c.X, c.Y, c.Z])
        next_node += 1
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
        cfg = ((doc.get("shells") if b.get("mode") == "shell" else doc.get("bodies")) or {}).get(b["id"]) or {}
        mname = cfg.get("material") or doc.get("default_material") or next(iter(doc.get("materials") or {}), None)
        if not mname:
            raise ModelError("body %s: no material" % b["name"])
        mat_of[b["id"]] = mname
    def ids_lines(ids):
        ids = sorted(ids)
        return [", ".join(str(v) for v in ids[k:k + 16]) for k in range(0, len(ids), 16)]
    for b in rigid:
        L.append("*NSET, NSET=RB_%s" % bname[b["id"]])
        L += ids_lines(body_nodes.get(b["id"], ()))
    sup_rows = []
    rigid_nodes = set(n for b in rigid for n in body_nodes.get(b["id"], ()))
    for k, s in enumerate(doc.get("supports") or []):
        t = s.get("target")
        if not t or t.get("comp") is None:
            continue
        sname = s.get("name") or k + 1
        try:
            if t.get("edge") is not None:
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
        rn = [n for n in nodes if n in M.shell_nodes]
        if any(dofs[3:]) and rn:
            L.append("*NSET, NSET=%s_R" % ns)
            L += ids_lines(rn)
            sup_rows += ["%s_R, %d, %d" % (ns, d + 1, d + 1) for d in range(3, 6) if dofs[d]]
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
    if sup_rows:
        L.append("*BOUNDARY")
        L += sup_rows
    with open(inp_path, "w") as f:
        f.write("\n".join(L) + "\n")

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
    summary = {"nodes": len(X), "elements": nel, "bodies": [
        {"id": b["id"], "name": names[b["id"]], "role": role.get(b["id"], "deformable"), "elset": "B_" + bname[b["id"]],
         "material": safe(mat_of.get(b["id"], ""), 60).upper(),
         "elements": sum(len(bl["elements"]) for bl in (mesh["bodies"].get(b["id"]) or {}).get("blocks", [])),
         "types": [bl["type"] for bl in (mesh["bodies"].get(b["id"]) or {}).get("blocks", [])],
         "ref_node": ref_nodes.get(b["id"])} for b in bodies],
        "supports": len(sup_rows), "warnings": mesh.get("warnings") or []}
    return {"inp": inp_path, "payload": pl, "summary": summary}
