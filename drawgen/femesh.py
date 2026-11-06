# -*- coding: utf-8 -*-
"""Analysis mesh (gmsh) of the solid bodies and plates of an analysis.

run(job) meshes in a subprocess (python -m drawgen.femesh <job.json> <out.json>) and returns the mesh:

job:
  {"size": mm, "bonded": bool, "apart": [body ids not fragmented with the others (contact pairs)],
   "mesh": {"size_min": mm, "curvature": elements per 360 deg (0: off), "algorithm": "delaunay" | "frontal" | "hxt",
            "optimize": bool, "strategy": "tet" | "hex" | "hexsub" (default of the solid bodies),
            "tet_type": "C3D10" | "C3D4", "hex_type": "C3D8I" | "C3D8" | "C3D8R" | "C3D20" | "C3D20R"},
   "bodies": [{"id", "brep": path, "mode": "solid" | "plate" | "shell", "size": mm or null, "layers": n (plate),
               "strategy": null (job default) | "tet" | "hex" | "hexsub", "t": mm (shell)}],
   "refine": [{"box": [x0, y0, z0, x1, y1, z1] (mm, global), "size": mm}]}   mesh refinement regions (tetrahedra and
               shells: Box fields; structured shell faces inside a region: the region size)
Automatic size (job "size" 0: h = diagonal / 20): every face of the tetrahedral bodies and shells without a size of
their own gets at most its width / ACROSS (3 elements across; width = area / largest bounding box extent), at least
"size_min" (empty: h / 10); shell faces at least the shell thickness "t".
   "mesh" also: "shell_type": "S4" | "S4R" | "S8R" | "S3", "shell_algorithm": "quasi" | "frontal" | "delaunay" | "tri"

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
Shells: the faces of all shell bodies are meshed together in a model of their own; with "bonded" they are
fragmented (general fuse, "fuzzy" mm the tolerance), so shells that touch or cross share their nodes on the common
lines. "shell_structured" (default true): structured quadrangles on axis-aligned rectangles (_structured, with
"shell_min_div" and "shell_size_mode" "local" | "grid"). out["shell_report"]: element quality (gamma), edge lengths,
structured and free faces, per body the elements and structured faces. Quadrangles (S4, S4R; S8R second
order) with triangles (S3; S6 with S8R) where the quadrangle mesh leaves them, or triangles only ("tri"). The surfaces
of a shell body are its faces; their facets are the shell elements. A face shared by two shell bodies (coincident
faces) belongs to the body listed first.
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
SHELL_TYPES = ("S4", "S4R", "S8R", "S3")
SHELL_ALGOS = {"quasi": 11, "frontal": 8, "delaunay": 6, "tri": 6}
SHELL_ALGO_NAMES = {"quasi": "Quasi-structured quadrangles", "frontal": "Frontal-Delaunay for quadrangles"}
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


def _refine_fields(gmsh, job, f=1.0):
    """Mesh refinement regions (job["refine"]: [{"box": [x0, y0, z0, x1, y1, z1], "size": mm}]): a Box field per region
    (element size inside, growing over 3 x the size outside), their minimum as the background mesh; the minimum
    element size follows the smallest region size. f: size factor of the algorithm (quasi-structured: 2)."""
    R = [r for r in job.get("refine") or [] if float(r.get("size") or 0) > 0 and len(r.get("box") or []) == 6]
    if not R:
        return
    ids = []
    for r in R:
        sz = float(r["size"]) * f
        b = [float(v) for v in r["box"]]
        pad = 0.25 * float(r["size"])
        fid = gmsh.model.mesh.field.add("Box")
        gmsh.model.mesh.field.setNumber(fid, "VIn", sz)
        gmsh.model.mesh.field.setNumber(fid, "VOut", 1e22)
        for k, v in (("XMin", b[0] - pad), ("YMin", b[1] - pad), ("ZMin", b[2] - pad),
                     ("XMax", b[3] + pad), ("YMax", b[4] + pad), ("ZMax", b[5] + pad)):
            gmsh.model.mesh.field.setNumber(fid, k, v)
        gmsh.model.mesh.field.setNumber(fid, "Thickness", 3.0 * sz)
        ids.append(fid)
    mn = gmsh.model.mesh.field.add("Min")
    gmsh.model.mesh.field.setNumbers(mn, "FieldsList", ids)
    gmsh.model.mesh.field.setAsBackgroundMesh(mn)
    smin = min(float(r["size"]) for r in R) * f
    if gmsh.option.getNumber("Mesh.MeshSizeMin") > smin:
        gmsh.option.setNumber("Mesh.MeshSizeMin", smin * 0.5)


def _refined_size(gmsh, job, st, cur):
    """Element size of a surface (structured shells): the smallest size of the refinement regions holding it."""
    out = cur
    R = [r for r in job.get("refine") or [] if float(r.get("size") or 0) > 0 and len(r.get("box") or []) == 6]
    if not R:
        return out
    bb = gmsh.model.getBoundingBox(2, st)
    for r in R:
        b, pad = r["box"], 0.25 * float(r["size"]) + 1e-6
        if all(bb[i] >= b[i] - pad and bb[i + 3] <= b[i + 3] + pad for i in range(3)):
            out = min(out, float(r["size"])) if out else float(r["size"])
    return out


ACROSS = 3          # automatic element size: at least this many elements across every face


def _face_width(gmsh, st):
    """Width of a face: area / largest extent of its bounding box (a rectangle a x b: the shorter side)."""
    try:
        a = gmsh.model.occ.getMass(2, st)
    except Exception:
        return 0.0
    bb = gmsh.model.getBoundingBox(2, st)
    L = max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])
    return a / L if L > 0 else 0.0


def _across_sizes(gmsh, surfs, h, hmin):
    """Automatic element size per face: ACROSS elements across the width of the face (h at most, hmin at least).
    Returns {surface: size} of the faces narrower than ACROSS x h."""
    out = {}
    for st in surfs:
        w = _face_width(gmsh, st)
        if w > 0 and w / ACROSS < h:
            out[st] = max(w / ACROSS, hmin)
    return out


def _point_sizes(gmsh, sizes, f=1.0):
    """Mesh sizes at the points of the faces: the smallest size of the faces at each point (x f)."""
    at = {}
    for st, sz in sizes.items():
        for d, t in gmsh.model.getBoundary([(2, st)], combined=False, recursive=True):
            if d == 0:
                at[t] = min(at.get(t, sz), sz)
    for t, sz in at.items():
        gmsh.model.mesh.setSize([(0, t)], sz * f)


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
        size = float(job.get("size") or 0)
        opts = job.get("mesh") or {}
        warnings = []
        solids, plates, hexes, shells = [], [], {}, []
        shell_report = None
        for b in job["bodies"]:
            if b.get("mode") == "plate":
                plates.append(b)
            elif b.get("mode") == "shell":
                shells.append(b)
            elif _strategy(b, opts) == "tet":
                solids.append(b)
            else:
                hexes.setdefault(_strategy(b, opts), []).append(b)
        out_nodes = {}
        bodies = {}
        diag = _diag(job)
        if solids:
            vol_of = _import(gmsh, solids, job.get("bonded"), job.get("apart") or ())
            h = size or diag / 20.0
            _common_options(gmsh, opts, h)
            order = 1 if opts.get("tet_type") == "C3D4" else 2
            gmsh.option.setNumber("Mesh.ElementOrder", order)
            gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1 if order == 2 else 0)
            if not size:
                # automatic size: ACROSS elements across every face of the bodies without a size of their own
                hmin = float(opts.get("size_min") or 0) or h / 10.0
                auto = [b for b in solids if not b.get("size")]
                faces = sorted(set(t for b in auto for d, t in gmsh.model.getBoundary([(3, v) for v in vol_of[b["id"]]], combined=False, oriented=False) if d == 2))
                acr = _across_sizes(gmsh, faces, h, hmin)
                if acr:
                    _point_sizes(gmsh, acr)
                    gmsh.option.setNumber("Mesh.MeshSizeMin", min(gmsh.option.getNumber("Mesh.MeshSizeMin"), hmin))
            for b in solids:
                if b.get("size"):
                    pts = gmsh.model.getBoundary([(3, t) for t in vol_of[b["id"]]], combined=False, recursive=True)
                    gmsh.model.mesh.setSize([p for p in pts if p[0] == 0], float(b["size"]))
            _refine_fields(gmsh, job)
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
        if shells:
            nid, eid, shell_report = _shell_group(gmsh, shells, job, opts, size or diag / 20.0, nid, eid, out_nodes, bodies, warnings)
        for b in plates:
            nid, eid, res = _plate(gmsh, b, size, nid, eid, out_nodes)
            res["group"] = "plate:%s" % b["id"]
            bodies[b["id"]] = res
        ids = sorted(out_nodes)
        xyz = []
        for i in ids:
            xyz.extend(out_nodes[i])
        return {"nodes": {"ids": ids, "xyz": xyz}, "bodies": bodies, "warnings": warnings, "shell_report": shell_report}
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


def _import(gmsh, group, bonded, apart=()):
    """Imports the bodies of a group into the current model; with bonded the solids are fragmented (shared faces),
    except the bodies in apart (contact pairs: meshed with their own nodes). Returns {body id: [volume tags]}."""
    occ = gmsh.model.occ
    vol_of = {}
    for b in group:
        ents = occ.importShapes(b["brep"])
        vol_of[b["id"]] = [t for d, t in ents if d == 3]
        if not vol_of[b["id"]]:
            raise RuntimeError("body %s has no solid" % b["id"])
    occ.synchronize()
    frag = [b for b in group if b["id"] not in set(apart)]
    if bonded and len(frag) > 1:
        inp = [(3, t) for b in frag for t in vol_of[b["id"]]]
        _, omap = occ.fragment(inp, [])
        k = 0
        for b in frag:
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
        vol_of = _import(gmsh, group, job.get("bonded"), job.get("apart") or ())
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


def _shell_type(gtype, opts):
    """Abaqus shell element type of a gmsh surface element type (3: quadrangle 4, 2: triangle 3, 16: quadrangle 8,
    9: triangle 6)."""
    st = opts.get("shell_type") if opts.get("shell_type") in SHELL_TYPES else "S4"
    if gtype == 3:
        return st if st in ("S4", "S4R") else "S4"
    return {2: "S3", 16: "S8R", 9: "S6"}.get(gtype)


def _ceil_div(length, size, min_div):
    return max(min_div, int(math.ceil(length / size - 1e-9)))


class Grid(object):
    """Break coordinates per axis and the divisions of an interval between two of them (ceil(interval / size) per
    interval, at least min_div; step2shell)."""

    def __init__(self, breaks, size, min_div):
        self.breaks = [sorted(set(b)) for b in breaks]
        self.min_div = min_div
        self.sizes = [[size] * max(len(b) - 1, 0) for b in self.breaks]   # size per interval (grid mode)

    def _index(self, ax, v, tol):
        xs = self.breaks[ax]
        lo, hi = 0, len(xs) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if abs(xs[mid] - v) <= tol:
                return mid
            if xs[mid] < v:
                lo = mid + 1
            else:
                hi = mid - 1
        return None

    def set_size(self, ax, a, b, tol, value):
        """Grid mode: the intervals between a and b take the smaller of their size and value."""
        i, j = self._index(ax, min(a, b), tol), self._index(ax, max(a, b), tol)
        if i is None or j is None or j <= i:
            return
        for k in range(i, j):
            self.sizes[ax][k] = min(self.sizes[ax][k], value)

    def divisions(self, ax, a, b, tol, size, grid=False):
        i, j = self._index(ax, min(a, b), tol), self._index(ax, max(a, b), tol)
        if i is None or j is None or j <= i:
            return None
        xs = self.breaks[ax]
        return sum(_ceil_div(xs[k + 1] - xs[k], self.sizes[ax][k] if grid else size, self.min_div) for k in range(i, j))


def _merge_breaks(values, tol):
    out = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _on_segment(p, a, b, tol):
    ab = [b[k] - a[k] for k in range(3)]
    l2 = sum(c * c for c in ab)
    if l2 <= 0:
        return False
    t = sum((p[k] - a[k]) * ab[k] for k in range(3)) / l2
    if t < -1e-6 or t > 1 + 1e-6:
        return False
    return _dist([a[k] + t * ab[k] for k in range(3)], p) <= tol


def _structured(gmsh, surfs, surf_size, h, opts, tol, f):
    """Structured quadrangles on axis-aligned rectangles (step2shell): the break coordinates of all curve ends along
    x, y and z form an interval grid; every straight axis-aligned curve gets ceil(interval / size) divisions per
    interval (at least "shell_min_div"), size the smallest of the shells of its faces ("shell_size_mode" "local"), or
    every interval the smallest size of the curves spanning it ("grid"). A face with one boundary loop of straight
    axis-aligned curves and 4 corners, no curve ending inside it and equal divisions on opposite sides is meshed
    transfinite. Returns (structured surfaces, number of free surfaces)."""
    min_div = max(1, int(opts.get("shell_min_div") or 1))
    grid_mode = opts.get("shell_size_mode") == "grid"
    occ = gmsh.model.occ
    curve_faces = {}
    for st in surfs:
        for _d, c in gmsh.model.getBoundary([(2, st)], combined=False, oriented=False):
            curve_faces.setdefault(abs(c), set()).add(st)
    ends, axis = {}, {}
    for c in curve_faces:
        pts = [t for d, t in gmsh.model.getBoundary([(1, c)], combined=False, oriented=True) if d == 0]
        ends[c] = [list(gmsh.model.getValue(0, abs(t), [])) for t in pts]
        if len(ends[c]) == 2 and gmsh.model.getType(1, c) == "Line":
            d = [ends[c][1][k] - ends[c][0][k] for k in range(3)]
            L = math.sqrt(sum(x * x for x in d)) or 1.0
            for k in range(3):
                if abs(abs(d[k]) / L - 1.0) < 1e-6:
                    axis[c] = k
    breaks = [[], [], []]
    for c, e in ends.items():
        for p in e:
            for k in range(3):
                breaks[k].append(p[k])
    grid = Grid([_merge_breaks(b, tol * 10) for b in breaks], h, min_div)
    csize = {c: min(surf_size.get(st, h) for st in fs) for c, fs in curve_faces.items()}
    if grid_mode:
        for c, k in axis.items():
            grid.set_size(k, ends[c][0][k], ends[c][1][k], tol * 10, csize[c])
    div = {}
    for c, k in axis.items():
        n = grid.divisions(k, ends[c][0][k], ends[c][1][k], tol * 10, csize[c], grid_mode)
        if n:
            div[c] = n
            gmsh.model.mesh.setTransfiniteCurve(c, n + 1)
    tf, nfree = set(), 0
    for st in surfs:
        try:
            loops, loop_curves = occ.getCurveLoops(st)
        except Exception:
            loops, loop_curves = [], []
        cs = [abs(c) for c in (loop_curves[0] if len(loops) == 1 else [])]
        if len(loops) != 1 or not cs or any(c not in axis for c in cs):
            nfree += 1
            continue
        # directed segments of the loop and the corners where the direction changes
        segs, cur = [], None
        for i, c in enumerate(cs):                       # chained by their end points
            a, b = ends[c]
            if cur is None:
                nxt = ends[cs[(i + 1) % len(cs)]]
                if min(_dist(a, q) for q in nxt) < min(_dist(b, q) for q in nxt):
                    a, b = b, a
            elif _dist(a, cur) > _dist(b, cur):
                a, b = b, a
            segs.append((a, b))
            cur = b
        dirs = []
        for a, b in segs:
            d = [b[k] - a[k] for k in range(3)]
            L = math.sqrt(sum(x * x for x in d)) or 1.0
            dirs.append([x / L for x in d])
        corners = [segs[i][0] for i in range(len(segs)) if sum(dirs[i - 1][k] * dirs[i][k] for k in range(3)) < math.cos(math.radians(30))]
        if len(corners) != 4:
            nfree += 1
            continue
        allc = [abs(c) for _d, c in gmsh.model.getBoundary([(2, st)], combined=False, oriented=False)]
        sums, ok = [0, 0, 0, 0], True
        for c in allc:
            side = next((i for i in range(4) if all(_on_segment(p, corners[i], corners[(i + 1) % 4], tol * 100) for p in ends[c])), None)
            if side is None or c not in div:
                ok = False
                break
            sums[side] += div[c]
        if not ok or sums[0] != sums[2] or sums[1] != sums[3]:
            nfree += 1
            continue
        pts = [t for d, t in gmsh.model.getBoundary([(2, st)], combined=False, oriented=False, recursive=True) if d == 0]
        ctags = []
        for cp in corners:
            best = min(pts, key=lambda t: _dist(gmsh.model.getValue(0, t, []), cp))
            if _dist(gmsh.model.getValue(0, best, []), cp) > tol * 100 or best in ctags:
                ctags = None
                break
            ctags.append(best)
        if not ctags:
            nfree += 1
            continue
        try:
            gmsh.model.mesh.setTransfiniteSurface(st, "Left", ctags)
            tf.add(st)
        except Exception:
            nfree += 1
    # the quasi-structured algorithm halves the size it reads from the curve meshes: curves of free faces only get
    # their divisions at twice the size
    if f > 1.0:
        for c, k in axis.items():
            if c in div and not (curve_faces[c] & tf):
                n = grid.divisions(k, ends[c][0][k], ends[c][1][k], tol * 10, f * csize[c], grid_mode)
                if n:
                    gmsh.model.mesh.setTransfiniteCurve(c, n + 1)
    return tf, nfree


def _quality(gmsh, surfs):
    """Element quality (gmsh gamma: 1 for a square) and element edge lengths of the surface elements."""
    tags = []
    for st in surfs:
        et, eg, _en = gmsh.model.mesh.getElements(2, st)
        for tg in eg:
            tags.extend(int(t) for t in tg)
    out = {"min_quality": None, "mean_quality": None, "below_03": 0, "min_edge": None, "max_edge": None}
    if not tags:
        return out
    q = gmsh.model.mesh.getElementQualities(tags, "gamma")
    out.update(min_quality=float(min(q)), mean_quality=float(sum(q) / len(q)), below_03=int(sum(1 for v in q if v < 0.3)))
    try:
        out.update(min_edge=float(min(gmsh.model.mesh.getElementQualities(tags, "minEdge"))),
                   max_edge=float(max(gmsh.model.mesh.getElementQualities(tags, "maxEdge"))))
    except Exception:
        pass
    return out


def _shell_group(gmsh, group, job, opts, h, nid, eid, out_nodes, bodies, warnings):
    """Shell mesh of the shell bodies in a model of their own; nodes and elements renumbered after nid / eid.
    Returns (nid, eid, report)."""
    gmsh.model.add("shells")
    occ = gmsh.model.occ
    try:
        surf_of = {}
        for b in group:
            ents = occ.importShapes(b["brep"])
            surf_of[b["id"]] = [t for d, t in ents if d == 2]
            if not surf_of[b["id"]]:
                raise RuntimeError("shell %s has no faces" % b["id"])
        occ.synchronize()
        fuzzy = float(opts.get("fuzzy") or 0)
        fgroup = [b for b in group if b["id"] not in set(job.get("apart") or ())]
        if job.get("bonded") and sum(len(surf_of[b["id"]]) for b in fgroup) > 1:
            # general fuse of all shell faces: faces split where they cross, edges shared where they touch; fuzzy:
            # the tolerance of the boolean operation (mm); shells of contact pairs are left out
            if fuzzy > 0:
                gmsh.option.setNumber("Geometry.ToleranceBoolean", fuzzy)
            inp = [(2, t) for b in fgroup for t in surf_of[b["id"]]]
            _, omap = occ.fragment(inp, [])
            k = 0
            for b in fgroup:
                new = []
                for _ in surf_of[b["id"]]:
                    new += [t for d, t in omap[k] if d == 2]
                    k += 1
                surf_of[b["id"]] = sorted(set(new))
            occ.synchronize()
        seen = set()
        for b in group:                                  # a face shared by two bodies: the body listed first
            surf_of[b["id"]] = [t for t in surf_of[b["id"]] if t not in seen]
            seen.update(surf_of[b["id"]])
        algo = str(opts.get("shell_algorithm") or "quasi")
        tri = algo == "tri" or opts.get("shell_type") == "S3"
        surf_size = {}
        for b in group:
            if b.get("size"):
                for st in surf_of[b["id"]]:
                    surf_size[st] = float(b["size"])
        allsurf = sorted(seen)
        acr = {}
        if not float(job.get("size") or 0):
            # automatic size: ACROSS elements across every face of the shells without a size of their own
            hmin = float(opts.get("size_min") or 0) or h / 10.0
            acr = _across_sizes(gmsh, [st for st in allsurf if st not in surf_size], h, hmin)
            # shells: elements not smaller than the shell thickness (shell theory; explicit time step)
            t_of = {st: float(b.get("t") or 0) for b in group for st in surf_of[b["id"]]}
            acr = {st: min(max(sz, t_of.get(st, 0.0)), h) for st, sz in acr.items()}
            acr = {st: sz for st, sz in acr.items() if sz < h}
            surf_size.update(acr)
        for st in allsurf:                               # refinement regions: the size of the faces inside them
            rs = _refined_size(gmsh, job, st, surf_size.get(st))
            if rs:
                surf_size[st] = rs
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
        tol = max(math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) * 1e-6, 1e-6)
        tf, nfree = set(), len(allsurf)
        if opts.get("shell_structured", True) and not tri:
            tf, nfree = _structured(gmsh, allsurf, surf_size, h, opts, tol, 1.0)
            if tf and algo == "quasi":
                # the quasi-structured algorithm meshes all faces of the model (transfinite faces too): with
                # structured faces the free faces are meshed with Frontal-Delaunay for quadrangles
                algo = "frontal"
        # the quasi-structured quadrangle algorithm makes elements of about half the size it reads
        f = 2.0 if algo == "quasi" and not tri else 1.0
        if f > 1.0 and opts.get("shell_structured", True) and not tri:
            _structured(gmsh, allsurf, surf_size, h, opts, tol, f)       # the curve divisions at twice the size
        gmsh.option.setNumber("Mesh.MeshSizeMax", h * f)
        gmsh.option.setNumber("Mesh.MeshSizeMin", (float(opts.get("size_min") or 0) or (h / 10.0 if acr else h / 5.0)) * f)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
        curv = opts.get("curvature")
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12 if curv is None else float(curv))
        gmsh.option.setNumber("Mesh.Algorithm", SHELL_ALGOS.get("delaunay" if tri else algo, 11))
        gmsh.option.setNumber("Mesh.RecombineAll", 0 if tri else 1)
        gmsh.option.setNumber("Mesh.RecombinationAlgorithm", 1)
        gmsh.option.setNumber("Mesh.Smoothing", 2)
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1)
        for b in group:
            if b.get("size") and surf_of[b["id"]]:
                pts = gmsh.model.getBoundary([(2, t) for t in surf_of[b["id"]]], combined=False, recursive=True)
                gmsh.model.mesh.setSize([p for p in pts if p[0] == 0], float(b["size"]) * f)
        if acr:
            _point_sizes(gmsh, acr, f)
        _refine_fields(gmsh, job, f)
        gmsh.model.mesh.generate(2)
        if SHELL_ALGOS.get("delaunay" if tri else algo, 11) != 6:
            # faces where the quadrangle algorithm returned the boundary triangulation without inside nodes
            # (Frontal-Delaunay for quadrangles on some cylindrical faces): meshed again with Delaunay, recombined
            bad = _failed_faces(gmsh, allsurf, surf_size, h, f)
            if bad:
                for st in bad:
                    gmsh.model.mesh.setAlgorithm(2, st, 6)
                gmsh.model.mesh.clear()
                gmsh.model.mesh.generate(2)
                warnings.append("shell faces %s: elements longer than 3 x the element size with %s; meshed with "
                                "Delaunay, recombined" % (", ".join(str(t) for t in bad), SHELL_ALGO_NAMES.get(algo, algo)))
        if opts.get("shell_type") == "S8R" and not tri:
            gmsh.model.mesh.setOrder(2)
        ntags, coords, _ = gmsh.model.mesh.getNodes()
        nmap = {}
        for i, t in enumerate(ntags):
            nid += 1
            nmap[int(t)] = nid
            out_nodes[nid] = (coords[3 * i], coords[3 * i + 1], coords[3 * i + 2])
        report = _quality(gmsh, allsurf)
        report.update(structured=len(tf), free=nfree, faces=len(allsurf), bodies=[])
        for b in group:
            blocks = {}
            surfs = []
            for st in surf_of[b["id"]]:
                et, eg, en = gmsh.model.mesh.getElements(2, st)
                for typ, tags, nds in zip(et, eg, en):
                    typ = int(typ)
                    at = _shell_type(typ, opts)
                    if at is None:
                        warnings.append("shell %s: %d elements of gmsh type %d left out" % (b["id"], len(tags), typ))
                        continue
                    nn = gmsh.model.mesh.getElementProperties(typ)[3]
                    lst = blocks.setdefault(at, [])
                    for i in range(len(tags)):
                        eid += 1
                        lst.append([eid] + [nmap[int(v)] for v in nds[nn * i:nn * i + nn]])
                surfs.append(_surface(gmsh, st, out_nodes, nmap=lambda n: nmap[n]))
            if not blocks:
                raise RuntimeError("shell %s: no elements (the faces are covered by another shell)" % b["id"])
            bodies[b["id"]] = {"blocks": [{"type": t, "elements": els} for t, els in blocks.items()], "surfaces": surfs,
                               "group": "shell", "thickness": float(b.get("t") or 0)}
            report["bodies"].append({"id": b["id"], "elements": sum(len(v) for v in blocks.values()),
                                     "structured": len(set(surf_of[b["id"]]) & tf), "faces": len(surf_of[b["id"]])})
        return nid, eid, report
    finally:
        gmsh.model.remove()
        gmsh.option.setNumber("Geometry.ToleranceBoolean", 0)


def _failed_faces(gmsh, surfs, surf_size, h, f):
    """Faces with an element edge longer than 3 x the element size of the face (h, or the size of its shell, times
    f) or without elements."""
    bad = []
    for st in surfs:
        _et, eg, _en = gmsh.model.mesh.getElements(2, st)
        tags = [int(t) for g in eg for t in g]
        if not tags:
            bad.append(st)
            continue
        size = surf_size.get(st, h) * f
        if max(gmsh.model.mesh.getElementQualities(tags, "maxEdge")) > 3.0 * size:
            bad.append(st)
    return bad


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
