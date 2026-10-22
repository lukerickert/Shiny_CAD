# -*- coding: utf-8 -*-
"""Analysis mesh (gmsh) of the solid bodies and plates of an analysis.

run(job) meshes in a subprocess (python -m drawgen.femesh <job.json> <out.json>) and returns the mesh:

job:
  {"size": mm, "bonded": bool,
   "mesh": {"size_min": mm, "curvature": elements per 360 deg (0: off), "algorithm": "delaunay" | "frontal" | "hxt",
            "optimize": bool, "strategy": "tet" | "hex" | "hexsub" (default of the solid bodies),
            "tet_type": "C3D10" | "C3D4", "hex_type": "C3D8I" | "C3D8" | "C3D8R" | "C3D20" | "C3D20R"},
   "bodies": [{"id", "brep": path, "mode": "solid" | "plate", "size": mm or null, "layers": n (plate),
               "strategy": null (job default) | "tet" | "hex" | "hexsub"}]}

out:
  {"nodes": {"ids": [...], "xyz": [x0, y0, z0, x1, ...]},
   "bodies": {id: {"blocks": [{"type": Abaqus element type, "elements": [[e, n1, n2, ...], ...]}],
                   "surfaces": [{"nodes": [...], "facets": [[n...], ...], "sample": [[x, y, z], ...]}],
                   "group": "tet" | "hex" | "hexsub" | "plate:<id>"}},
   "warnings": [...]}

Mesh strategies of the solid bodies:
  tet     free tetrahedra (C3D10 second order, C3D4 first order)
  hex     structured hexahedra (transfinite): every cell of the body must be a block (6 faces with 4 edges each) or a
          prism (wedge elements); bodies are partitioned into such cells in the Part tab (Partition)
  hexsub  all hexahedra by subdivision of a tetrahedral mesh (each tetrahedron gives four hexahedra)
Hexahedra: C3D8I (incompatible modes), C3D8, C3D8R, or with C3D20 / C3D20R second order (wedges C3D6 / C3D15).
The bodies of one strategy share their nodes at touching faces ("bonded": the solids are fragmented); bodies of
different strategies and plates are tied (analysis.Model._ties).
Plates: the largest planar face is meshed with quadrangles and the mesh is extruded through the thickness
(C3D8I, C3D6 for the triangles left), "layers" elements through the thickness; the plate must be a prism of that face.
Facets of the surfaces carry the corner nodes first, then the mid-side nodes.
"""
import json
import math
import os
import subprocess
import sys


def run(job, timeout=1800):
    import tempfile
    d = tempfile.mkdtemp(prefix="drawgen_femesh_")
    jp, op = os.path.join(d, "job.json"), os.path.join(d, "out.json")
    with open(jp, "w") as f:
        json.dump(job, f)
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        r = subprocess.run([sys.executable, "-m", "drawgen.femesh", jp, op], capture_output=True, text=True,
                           timeout=timeout, cwd=root, env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError("meshing stopped after %d s" % timeout)
    if r.returncode != 0 or not os.path.isfile(op):
        msg = (r.stderr or r.stdout or "").strip().splitlines()
        raise RuntimeError("meshing failed: %s" % (msg[-1] if msg else "no output"))
    with open(op) as f:
        out = json.load(f)
    try:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass
    return out


# gmsh 10-node tetrahedron -> Abaqus C3D10: the last two mid-side nodes are swapped
def _tet10(n):
    return n[:8] + [n[9], n[8]]


# gmsh element type -> (node count, node order gmsh -> Abaqus)
GMSH_ELEMS = {
    4: (4, lambda n: n),                                                                  # tetrahedron 4
    11: (10, _tet10),                                                                      # tetrahedron 10
    5: (8, lambda n: n),                                                                  # hexahedron 8
    17: (20, lambda n: n[:8] + [n[8], n[11], n[13], n[9], n[16], n[18], n[19], n[17], n[10], n[12], n[14], n[15]]),
    6: (6, lambda n: n),                                                                  # wedge 6
    18: (15, lambda n: n[:6] + [n[6], n[9], n[7], n[12], n[14], n[13], n[8], n[10], n[11]]),
}
ALGO3D = {"delaunay": 1, "frontal": 4, "hxt": 10}
HEX_TYPES = ("C3D8I", "C3D8", "C3D8R", "C3D20", "C3D20R")
TET_TYPES = ("C3D10", "C3D4")


def _abaqus_type(gtype, opts):
    """Abaqus element type of a gmsh volume element type with the chosen element types."""
    hx = opts.get("hex_type") if opts.get("hex_type") in HEX_TYPES else "C3D8I"
    return {4: "C3D4", 11: "C3D10", 5: hx if hx in ("C3D8I", "C3D8", "C3D8R") else "C3D8I", 17: hx,
            6: "C3D6", 18: "C3D15"}.get(gtype)


def _common_options(gmsh, opts, h):
    """Size, curvature, algorithm and optimisation options of a solid mesh."""
    gmsh.option.setNumber("Mesh.MeshSizeMax", h)
    gmsh.option.setNumber("Mesh.MeshSizeMin", float(opts.get("size_min") or 0) or h / 5.0)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
    curv = opts.get("curvature")
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12 if curv is None else float(curv))
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.Algorithm3D", ALGO3D.get(str(opts.get("algorithm") or "delaunay"), 1))
    gmsh.option.setNumber("Mesh.Optimize", 1 if opts.get("optimize", True) else 0)
    gmsh.option.setNumber("Mesh.HighOrderOptimize", 0)


def _strategy(b, opts):
    st = b.get("strategy") or opts.get("strategy") or "tet"
    return st if st in ("tet", "hex", "hexsub") else "tet"


def _mesh(job):
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.Verbosity", 2)
        gmsh.option.setNumber("Geometry.OCCImportLabels", 0)
        gmsh.model.add("analysis")
        occ = gmsh.model.occ
        size = float(job.get("size") or 0)
        opts = job.get("mesh") or {}
        warnings = []
        solids, plates, hexes = [], [], {}
        for b in job["bodies"]:
            if b.get("mode") == "plate":
                plates.append(b)
            elif _strategy(b, opts) == "tet":
                solids.append(b)
            else:
                hexes.setdefault(_strategy(b, opts), []).append(b)
        out_nodes = {}
        bodies = {}
        diag = _diag(job)
        if solids:
            vol_of = _import(gmsh, solids, job.get("bonded"))
            h = size or diag / 20.0
            _common_options(gmsh, opts, h)
            order = 1 if opts.get("tet_type") == "C3D4" else 2
            gmsh.option.setNumber("Mesh.ElementOrder", order)
            gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1 if order == 2 else 0)
            for b in solids:
                if b.get("size"):
                    pts = gmsh.model.getBoundary([(3, t) for t in vol_of[b["id"]]], combined=False, recursive=True)
                    gmsh.model.mesh.setSize([p for p in pts if p[0] == 0], float(b["size"]))
            gmsh.model.mesh.generate(3)
            ntags, coords, _ = gmsh.model.mesh.getNodes()
            for i, t in enumerate(ntags):
                out_nodes[int(t)] = (coords[3 * i], coords[3 * i + 1], coords[3 * i + 2])
            for b in solids:
                bodies[b["id"]] = _body_elements(gmsh, b, vol_of[b["id"]], opts, out_nodes, lambda n: n, warnings)
                bodies[b["id"]]["group"] = "tet"
        nid = max(out_nodes) if out_nodes else 0
        eid = 0
        for b in bodies.values():
            for bl in b["blocks"]:
                for e in bl["elements"]:
                    eid = max(eid, e[0])
        for st, group in sorted(hexes.items()):
            nid, eid = _hex_group(gmsh, st, group, job, opts, size or diag / 20.0, nid, eid, out_nodes, bodies, warnings)
        for b in plates:
            nid, eid, res = _plate(gmsh, b, size, nid, eid, out_nodes)
            res["group"] = "plate:%s" % b["id"]
            bodies[b["id"]] = res
        ids = sorted(out_nodes)
        xyz = []
        for i in ids:
            xyz.extend(out_nodes[i])
        return {"nodes": {"ids": ids, "xyz": xyz}, "bodies": bodies, "warnings": warnings}
    finally:
        gmsh.finalize()


def _diag(job):
    """Bounding box diagonal of all bodies of the job (default element size: diagonal / 20)."""
    import gmsh
    gmsh.model.add("bbox")
    try:
        for b in job["bodies"]:
            gmsh.model.occ.importShapes(b["brep"])
        gmsh.model.occ.synchronize()
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
        return math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) or 1.0
    finally:
        gmsh.model.remove()
        gmsh.model.setCurrent("analysis")


def _import(gmsh, group, bonded):
    """Imports the bodies of a group into the current model; with bonded the solids are fragmented (shared faces).
    Returns {body id: [volume tags]}."""
    occ = gmsh.model.occ
    vol_of = {}
    for b in group:
        ents = occ.importShapes(b["brep"])
        vol_of[b["id"]] = [t for d, t in ents if d == 3]
        if not vol_of[b["id"]]:
            raise RuntimeError("body %s has no solid" % b["id"])
    occ.synchronize()
    if bonded and len(group) > 1:
        inp = [(3, t) for b in group for t in vol_of[b["id"]]]
        _, omap = occ.fragment(inp, [])
        k = 0
        for b in group:
            new = []
            for _ in vol_of[b["id"]]:
                new += [t for d, t in omap[k] if d == 3]
                k += 1
            vol_of[b["id"]] = sorted(set(new))
        occ.synchronize()
    return vol_of


def _body_elements(gmsh, b, vols, opts, out_nodes, nmap, warnings, emap=lambda e: e):
    """Element blocks (one per Abaqus type) and boundary surfaces of a body; nmap / emap renumber gmsh node and
    element tags."""
    blocks = {}
    for vt in vols:
        et, eg, en = gmsh.model.mesh.getElements(3, vt)
        for typ, tags, nds in zip(et, eg, en):
            typ = int(typ)
            if typ not in GMSH_ELEMS:
                warnings.append("body %s: %d elements of gmsh type %d (pyramids) left out" % (b["id"], len(tags), typ))
                continue
            nn, order = GMSH_ELEMS[typ]
            at = _abaqus_type(typ, opts)
            lst = blocks.setdefault(at, [])
            for i, tg in enumerate(tags):
                lst.append([emap(int(tg))] + [nmap(v) for v in order([int(v) for v in nds[nn * i:nn * i + nn]])])
    surfs = []
    seen = set()
    for vt in vols:
        for d, st in gmsh.model.getBoundary([(3, vt)], combined=False, oriented=False):
            if st in seen:
                continue
            seen.add(st)
            surfs.append(_surface(gmsh, st, out_nodes, nmap=nmap))
    return {"blocks": [{"type": t, "elements": els} for t, els in blocks.items()], "surfaces": surfs}


def _hex_group(gmsh, st, group, job, opts, h, nid, eid, out_nodes, bodies, warnings):
    """Hexahedral mesh of the bodies of one strategy ("hex": structured, "hexsub": subdivision) in a model of its
    own; nodes and elements renumbered after nid / eid."""
    from . import fea
    gmsh.model.add("hex_%s" % st)
    try:
        vol_of = _import(gmsh, group, job.get("bonded"))
        order = 2 if opts.get("hex_type") in ("C3D20", "C3D20R") else 1
        hh = h * (2.0 if st == "hexsub" else 1.0)          # subdivision halves the edge length
        _common_options(gmsh, opts, hh)
        if st == "hexsub":
            gmsh.option.setNumber("Mesh.SubdivisionAlgorithm", 2)
        else:
            gmsh.option.setNumber("Mesh.SubdivisionAlgorithm", 0)
            vols = [(3, t) for b in group for t in vol_of[b["id"]]]
            blocks = fea._block_cells(gmsh, vols)
            bad = [b["id"] for b in group if any((3, t) not in blocks for t in vol_of[b["id"]])]
            if bad:
                raise RuntimeError("body %s: structured hexahedra need cells that are blocks (6 faces with 4 edges "
                                   "each) or prisms; partition the part (Part tab, Partition) or use the subdivision "
                                   "hexahedra" % ", ".join(bad))
            fea._structured(gmsh, blocks, hh, None)
        for b in group:
            if b.get("size"):
                pts = gmsh.model.getBoundary([(3, t) for t in vol_of[b["id"]]], combined=False, recursive=True)
                gmsh.model.mesh.setSize([p for p in pts if p[0] == 0], float(b["size"]) * (2.0 if st == "hexsub" else 1.0))
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
        gmsh.model.mesh.generate(3)
        if order == 2:
            gmsh.model.mesh.setOrder(2)
        ntags, coords, _ = gmsh.model.mesh.getNodes()
        nmap = {}
        for i, t in enumerate(ntags):
            nid += 1
            nmap[int(t)] = nid
            out_nodes[nid] = (coords[3 * i], coords[3 * i + 1], coords[3 * i + 2])
        emap = {}

        def em(t):
            if t not in emap:
                emap[t] = eid + len(emap) + 1
            return emap[t]
        for b in group:
            res = _body_elements(gmsh, b, vol_of[b["id"]], opts, out_nodes, lambda n: nmap[n], warnings, em)
            res["group"] = st
            bodies[b["id"]] = res
        return nid, eid + len(emap)
    finally:
        gmsh.model.remove()
        gmsh.option.setNumber("Mesh.SubdivisionAlgorithm", 0)


def _surface(gmsh, st, nodes, nsample=25, nmap=lambda n: n):
    """Nodes, facets (corners first, then the mid-side nodes) and sample points of a gmsh surface."""
    tg, _, _ = gmsh.model.mesh.getNodes(2, st, includeBoundary=True)
    ns = sorted(set(nmap(int(v)) for v in tg))
    facets = []
    et, eg, en = gmsh.model.mesh.getElements(2, st)
    for typ, tags, nds in zip(et, eg, en):
        nn = gmsh.model.mesh.getElementProperties(int(typ))[3]
        for i in range(len(tags)):
            facets.append([nmap(int(v)) for v in nds[nn * i:nn * i + nn]][:8])
    step = max(1, len(ns) // nsample)
    sample = [list(nodes[n]) for n in ns[::step] if n in nodes][:nsample]
    return {"nodes": ns, "facets": facets, "sample": sample}


def _plate(gmsh, b, size, nid, eid, out_nodes):
    """Swept mesh of a prismatic plate: quadrangles on the largest planar face, extruded through the thickness."""
    gmsh.model.add("plate_%s" % b["id"])
    occ = gmsh.model.occ
    ents = occ.importShapes(b["brep"])
    occ.synchronize()
    vols = [t for d, t in ents if d == 3]
    if len(vols) != 1:
        raise RuntimeError("plate %s: one solid expected" % b["id"])
    vol = occ.getMass(3, vols[0])
    best = None
    hint = b.get("normal")
    for d, s in gmsh.model.getBoundary([(3, vols[0])], combined=False, oriented=False):
        if gmsh.model.getType(2, s) != "Plane":
            continue
        if hint:
            cs = occ.getCenterOfMass(2, s)
            ns = gmsh.model.getNormal(s, list(gmsh.model.getParametrization(2, s, list(cs))))
            if abs(sum(ns[i] * hint[i] for i in range(3))) < 0.999:
                continue
        a = occ.getMass(2, s)
        if best is None or a > best[1]:
            best = (s, a)
    if best is None:
        raise RuntimeError("plate %s has no planar face" % b["id"])
    base, area = best
    t = vol / area
    c = occ.getCenterOfMass(2, base)
    uv = gmsh.model.getParametrization(2, base, list(c))
    n = gmsh.model.getNormal(base, list(uv))
    # n points from the base face into the plate
    probe = [c[i] + n[i] * t * 0.5 for i in range(3)]
    if not gmsh.model.isInside(3, vols[0], probe):
        n = [-v for v in n]
    # the plate must be a prism: the opposite face has the same area at distance t
    xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(3, vols[0])
    diag = math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) or 1.0
    top = None
    for d, s in gmsh.model.getBoundary([(3, vols[0])], combined=False, oriented=False):
        if s == base or gmsh.model.getType(2, s) != "Plane":
            continue
        cs = occ.getCenterOfMass(2, s)
        dist = sum((cs[i] - c[i]) * n[i] for i in range(3))
        if abs(occ.getMass(2, s) - area) < 1e-3 * area and abs(dist - t) < 1e-4 * diag:
            top = s
    if top is None:
        raise RuntimeError("plate %s is not a prism of its largest face (no opposite face of equal area at the thickness)" % b["id"])
    h = float(b.get("size") or size or 0) or diag / 20.0
    gmsh.option.setNumber("Mesh.MeshSizeMax", h)
    gmsh.option.setNumber("Mesh.MeshSizeMin", h / 5.0)
    gmsh.option.setNumber("Mesh.ElementOrder", 1)
    gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 0)
    gmsh.option.setNumber("Mesh.Algorithm", 8)
    gmsh.option.setNumber("Mesh.RecombineAll", 1)
    gmsh.option.setNumber("Mesh.RecombinationAlgorithm", 1)
    gmsh.model.mesh.generate(2)
    tags, coords, _ = gmsh.model.mesh.getNodes(2, base, includeBoundary=True)
    base_nodes = [int(v) for v in tags]
    pos = {int(v): (coords[3 * i], coords[3 * i + 1], coords[3 * i + 2]) for i, v in enumerate(tags)}
    layers = max(1, int(b.get("layers") or 1))
    newid = {}
    for k in range(layers + 1):
        for g in base_nodes:
            nid += 1
            newid[(g, k)] = nid
            p = pos[g]
            out_nodes[nid] = (p[0] + n[0] * t * k / layers, p[1] + n[1] * t * k / layers, p[2] + n[2] * t * k / layers)
    hexes, wedges = [], []
    et, eg, en = gmsh.model.mesh.getElements(2, base)
    for typ, tgs, nds in zip(et, eg, en):
        nn = gmsh.model.mesh.getElementProperties(int(typ))[3]
        for i in range(len(tgs)):
            q = [int(v) for v in nds[nn * i:nn * i + nn]]
            # corner order counter-clockwise about n (extrusion direction) for a positive volume
            a, bq, cq = pos[q[0]], pos[q[1]], pos[q[2]]
            cr = [(bq[1] - a[1]) * (cq[2] - a[2]) - (bq[2] - a[2]) * (cq[1] - a[1]),
                  (bq[2] - a[2]) * (cq[0] - a[0]) - (bq[0] - a[0]) * (cq[2] - a[2]),
                  (bq[0] - a[0]) * (cq[1] - a[1]) - (bq[1] - a[1]) * (cq[0] - a[0])]
            if sum(cr[j] * n[j] for j in range(3)) < 0:
                q = q[::-1]
            for k in range(layers):
                eid += 1
                lo = [newid[(g, k)] for g in q]
                hi = [newid[(g, k + 1)] for g in q]
                (hexes if len(q) == 4 else wedges).append([eid] + lo + hi)
    # surfaces: base, top, and one per boundary curve of the base face (side faces)
    surfs = []
    bottom_f, top_f = [], []
    for e in hexes + wedges:
        m = (len(e) - 1) // 2
        bottom_f.append(e[1:1 + m][::-1])
        top_f.append(e[1 + m:])
    allb = sorted(newid[(g, 0)] for g in base_nodes)
    allt = sorted(newid[(g, layers)] for g in base_nodes)
    surfs.append({"nodes": allb, "facets": bottom_f, "sample": _sample(allb, out_nodes)})
    surfs.append({"nodes": allt, "facets": top_f, "sample": _sample(allt, out_nodes)})
    for d, cv in gmsh.model.getBoundary([(2, base)], combined=False, oriented=False):
        ctags, _, _ = gmsh.model.mesh.getNodes(1, abs(cv), includeBoundary=True)
        cn = [int(v) for v in ctags]
        segs = []
        et1, eg1, en1 = gmsh.model.mesh.getElements(1, abs(cv))
        for typ, tgs, nds in zip(et1, eg1, en1):
            for i in range(len(tgs)):
                segs.append((int(nds[2 * i]), int(nds[2 * i + 1])))
        ns = sorted(newid[(g, k)] for g in cn for k in range(layers + 1))
        facets = [[newid[(a, k)], newid[(bb, k)], newid[(bb, k + 1)], newid[(a, k + 1)]] for a, bb in segs for k in range(layers)]
        surfs.append({"nodes": ns, "facets": facets, "sample": _sample(ns, out_nodes)})
    blocks = []
    if hexes:
        blocks.append({"type": "C3D8I", "elements": hexes})
    if wedges:
        blocks.append({"type": "C3D6", "elements": wedges})
    gmsh.model.remove()
    return nid, eid, {"blocks": blocks, "surfaces": surfs, "thickness": t, "normal": n}


def _sample(ns, nodes, k=25):
    step = max(1, len(ns) // k)
    return [list(nodes[n]) for n in ns[::step]][:k]


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        job = json.load(f)
    try:
        res = _mesh(job)
    except Exception as e:
        sys.stderr.write("%s\n" % e)
        sys.exit(1)
    with open(sys.argv[2], "w") as f:
        json.dump(res, f)
