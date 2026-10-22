# -*- coding: utf-8 -*-
"""FEA mesh export with gmsh.

run(step_path, out_path, opts) meshes the solids of a STEP file and writes the mesh. It runs gmsh in a
subprocess (python -m drawgen.fea <step> <out> <json opts>) so that a gmsh failure does not stop the server.

opts:
  "size": target element size (mm)            default: bounding box diagonal / 20
  "size_min": minimum element size (mm)       default: size / 5
  "order": 1 | 2                              element order
  "kind": "solid" | "hex" | "hexdom" | "allhex" | "surface"   see _mesh
  "corner_angle": deg                         faces with a corner angle above this are not 4-sided (hex kinds)
  "recombine": true                           surface: quadrangles
  "preview": true                             return the boundary mesh edges for the 3D view
  "compounds": [[{"c", "area"}, ...], ...]    virtual topology: face groups meshed as one surface
  "compound_min_area": mm^2                  faces below this area combined with their largest neighbour
  "fix_tolerance": mm                         gmsh healing at import (degenerated/small edges and faces, sewing)
  "algorithm": "default" | "hxt" | "delaunay" | "frontal"   3D algorithm
  "optimize": true                            Netgen optimisation of the tetrahedra
  "curvature": n                              elements per 2*pi of curvature (0: off)
  "groups": true                              one element set per face (F1..Fn) and per solid (S1..Sn)
  "seeds": [{"p", "w", "u", "v", "half", "radii", "T", "n_circ", "n_rad", "bias", "n_thick"}]   hole mesh seeds
                                              (part.mesh_seeds): edge counts of the structured mesh around the holes

Formats by file extension: .inp (Abaqus / CalculiX), .msh (gmsh), .bdf (Nastran), .unv (I-DEAS), .vtk, .med, .cgns.
"""
import json
import math
import os
import subprocess
import sys

FORMATS = {".inp": "Abaqus / CalculiX (.inp)", ".msh": "gmsh (.msh)", ".bdf": "Nastran (.bdf)",
           ".unv": "I-DEAS universal (.unv)", ".vtk": "VTK (.vtk)", ".med": "MED / Salome (.med)",
           ".cgns": "CGNS (.cgns)"}

ALGO3D = {"default": 1, "delaunay": 1, "frontal": 4, "hxt": 10}


def import_error():
    """None when gmsh imports, else the error text."""
    try:
        import gmsh  # noqa: F401
        return None
    except Exception as e:
        return str(e).strip() or e.__class__.__name__


def run(geo_path, out_path, opts, timeout=900):
    """Mesh in a subprocess (geo_path: STEP or BREP). Returns the mesh summary dict (or raises RuntimeError)."""
    cmd = [sys.executable, "-m", "drawgen.fea", geo_path, out_path or "", json.dumps(opts or {})]
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=root, env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError("meshing stopped after %d s" % timeout)
    lines = [l for l in (r.stdout or "").splitlines() if l.startswith("RESULT ")]
    if r.returncode != 0 or not lines:
        msg = (r.stderr or r.stdout or "").strip().splitlines()
        raise RuntimeError("meshing failed: %s" % (msg[-1] if msg else "no output"))
    return json.loads(lines[-1][len("RESULT "):])


ELEMENT_NAMES = {1: "2-node line", 2: "3-node triangle", 3: "4-node quadrangle", 4: "4-node tetrahedron",
                 5: "8-node hexahedron", 6: "6-node wedge", 7: "5-node pyramid", 8: "3-node line", 9: "6-node triangle",
                 10: "9-node quadrangle", 11: "10-node tetrahedron", 12: "27-node hexahedron", 13: "18-node wedge",
                 14: "14-node pyramid", 16: "8-node quadrangle", 17: "20-node hexahedron", 18: "15-node wedge",
                 19: "13-node pyramid"}
ABAQUS_NAMES = {4: "C3D4", 5: "C3D8", 6: "C3D6", 7: "C3D5", 11: "C3D10", 17: "C3D20", 18: "C3D15", 19: "C3D13",
                2: "S3", 3: "S4", 9: "STRI65", 16: "S8R"}


def _mesh(geo_path, out_path, opts):
    """Meshes the solids of a STEP or BREP file.

    kind: "solid"  tetrahedra (free)
          "hex"    structured hexahedra (transfinite); every cell must be a block: 6 faces with 4 edges each
                   (CAE: Structured), or a prism (5 faces; wedge elements). Other cells are reported and the mesh is
                   refused.
          "hexmix" structured hexahedra in the block cells, tetrahedra in the other cells; the interfaces between
                   a block and a free cell are not conforming (a tie constraint is needed there)
          "allhex" all hexahedra by subdivision of a tetrahedral mesh (every tetrahedron gives four hexahedra;
                   element size is the size of the tetrahedra before subdivision)
          "surface" triangles (or quadrangles with recombine) of the boundary
    """
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.Verbosity", 2)
        gmsh.model.add("part")
        gmsh.option.setNumber("Geometry.OCCImportLabels", 0)
        fix_tol = float(opts.get("fix_tolerance") or 0)
        if fix_tol > 0:
            # gmsh's own healing at import: degenerated and small edges, small faces, sewing (dirty CAD)
            for k in ("Geometry.OCCFixDegenerated", "Geometry.OCCFixSmallEdges", "Geometry.OCCFixSmallFaces",
                      "Geometry.OCCSewFaces", "Geometry.OCCMakeSolids"):
                gmsh.option.setNumber(k, 1)
            gmsh.option.setNumber("Geometry.Tolerance", fix_tol)
        gmsh.model.occ.importShapes(geo_path)
        gmsh.model.occ.removeAllDuplicates()
        gmsh.model.occ.synchronize()
        vols = gmsh.model.getEntities(3)
        surfs = gmsh.model.getEntities(2)
        if fix_tol > 0 and surfs and not vols:
            # the healed faces no longer form a solid for OCC; one volume from the closed surface loop
            sl = gmsh.model.occ.addSurfaceLoop([t for d, t in surfs])
            gmsh.model.occ.addVolume([sl])
            gmsh.model.occ.synchronize()
            vols = gmsh.model.getEntities(3)
        if not surfs:
            raise RuntimeError("the geometry has no faces")
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
        diag = math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2) or 1.0
        size = float(opts.get("size") or 0) or diag / 20.0
        size_min = float(opts.get("size_min") or 0) or size / 5.0
        kind = str(opts.get("kind") or "solid")
        if kind in ("solid", "hex", "hexmix", "allhex") and not vols:
            raise RuntimeError("the geometry has no solids; use the surface mesh")
        if kind == "allhex":
            size *= 2.0                                  # subdivision halves the edge length
            size_min *= 2.0
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", size_min)
        curv = float(opts.get("curvature") or 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", curv)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
        gmsh.option.setNumber("Mesh.Algorithm", 6)                    # 2D: frontal-Delaunay
        gmsh.option.setNumber("Mesh.Algorithm3D", ALGO3D.get(str(opts.get("algorithm") or "default"), 1))
        order = int(opts.get("order") or 1)
        gmsh.option.setNumber("Mesh.ElementOrder", 2 if order == 2 else 1)
        gmsh.option.setNumber("Mesh.SecondOrderIncomplete", 1 if order == 2 else 0)   # C3D10, C3D20, S8
        if opts.get("optimize", True):
            gmsh.option.setNumber("Mesh.Optimize", 1)
            gmsh.option.setNumber("Mesh.OptimizeNetgen", 1 if kind == "solid" else 0)
        if kind in ("hex", "hexmix"):
            # transfinite (structured) constraints on the block cells: 6 faces, 4 edges per face
            angle = math.radians(float(opts.get("corner_angle") or 135.0))
            blocks = _block_cells(gmsh, vols)
            if kind == "hex" and len(blocks) != len(vols):
                bad = [i + 1 for i, (d, t) in enumerate(vols) if (d, t) not in blocks]
                raise RuntimeError("cell(s) %s are not blocks (6 faces with 4 edges each) or prisms; partition them further "
                                   "or use the mixed or subdivision mesh" % ", ".join(str(b) for b in bad))
            seeds = opts.get("seeds") or []
            prisms = len(blocks) > len([b for b in blocks if len(gmsh.model.getBoundary([b], combined=False, oriented=False)) == 6])
            if blocks and (seeds or prisms):
                # edge counts from the hole mesh seeds (elements per 45 deg arc, radial with bias, through the
                # thickness) and from the element size elsewhere; prisms (wedges at a blind hole axis) included
                _structured(gmsh, blocks, size, seeds)
            elif blocks:
                gmsh.model.mesh.setTransfiniteAutomatic(blocks, angle, True)
        if kind == "allhex":
            gmsh.option.setNumber("Mesh.SubdivisionAlgorithm", 2)         # all hexahedra
        if kind == "surface" and opts.get("recombine"):
            gmsh.option.setNumber("Mesh.RecombineAll", 1)
            gmsh.option.setNumber("Mesh.RecombinationAlgorithm", 1)
        comp_info = _compounds(gmsh, surfs, opts.get("compounds") or [], float(opts.get("compound_min_area") or 0)) or {}
        gmsh.option.setNumber("Mesh.SaveGroupsOfNodes", 1)
        gmsh.option.setNumber("Mesh.SaveGroupsOfElements", 1)
        gmsh.option.setNumber("Mesh.SaveAll", 0 if opts.get("groups", True) else 1)
        ext = os.path.splitext(out_path)[1].lower()
        solid_kind = kind != "surface"
        groups = bool(opts.get("groups", True))
        inp_solid = groups and solid_kind and ext == ".inp"      # faces as node sets, no surface elements
        if groups:
            if solid_kind:
                for i, (d, t) in enumerate(vols):
                    g = gmsh.model.addPhysicalGroup(3, [t])
                    gmsh.model.setPhysicalName(3, g, "S%d" % (i + 1))
            if not inp_solid:
                for i, (d, t) in enumerate(surfs):
                    g = gmsh.model.addPhysicalGroup(2, [t])
                    gmsh.model.setPhysicalName(2, g, "F%d" % (i + 1))
        else:
            gmsh.option.setNumber("Mesh.SaveAll", 1)
        gmsh.model.mesh.generate(3 if solid_kind else 2)
        if kind in ("hex", "hexmix") and order == 2:
            gmsh.model.mesh.setOrder(2)
        if ext == ".msh":
            gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        if ext == ".bdf":
            gmsh.option.setNumber("Mesh.BdfFieldFormat", 2)
        if out_path:
            gmsh.write(out_path)
            if inp_solid:
                with open(out_path, "a") as fh:
                    for i, (d, t) in enumerate(surfs):
                        tags, _, _ = gmsh.model.mesh.getNodes(2, t, includeBoundary=True)
                        tags = sorted(set(int(v) for v in tags))
                        fh.write("*NSET, NSET=F%d\n" % (i + 1))
                        for k in range(0, len(tags), 10):
                            fh.write(", ".join(str(v) for v in tags[k:k + 10]) + "\n")
        ntags, _, _ = gmsh.model.mesh.getNodes()
        etypes, etags, _ = gmsh.model.mesh.getElements(3 if solid_kind else 2)
        counts = {}
        for t, tags in zip(etypes, etags):
            counts[int(t)] = counts.get(int(t), 0) + len(tags)
        nel = sum(counts.values())
        # per cell: element types (structured cells are all hexahedra)
        cells = []
        if solid_kind:
            for i, (d, t) in enumerate(vols):
                et, eg, _ = gmsh.model.mesh.getElements(3, t)
                c = {int(a): len(b) for a, b in zip(et, eg)}
                hexes = sum(v for k, v in c.items() if k in (5, 12, 17))
                n = sum(c.values())
                tech = "free (tetrahedra)"
                if hexes and hexes == n:
                    tech = "subdivision (hexahedra)" if kind == "allhex" else "structured (hexahedra)"
                elif hexes:
                    tech = "mixed"
                cells.append({"cell": i + 1, "elements": n, "hex": hexes, "technique": tech})
        # quality (minSICN: 1 ideal, <= 0 inverted; gamma: inscribed/circumscribed ratio)
        quality = {}
        try:
            all_tags = [int(v) for tags in etags for v in tags]
            if all_tags:
                q = list(gmsh.model.mesh.getElementQualities(all_tags, "minSICN"))
                q.sort()
                quality = {"sicn_min": round(q[0], 4), "sicn_mean": round(sum(q) / len(q), 4),
                           "sicn_below_0_2": sum(1 for v in q if v < 0.2), "inverted": sum(1 for v in q if v <= 0)}
                if all(int(t) in (2, 4, 9, 11) for t in etypes):          # gamma is defined for simplices
                    g = list(gmsh.model.mesh.getElementQualities(all_tags, "gamma"))
                    quality.update(gamma_min=round(min(g), 4), gamma_mean=round(sum(g) / len(g), 4))
        except Exception:
            pass
        res = {"nodes": len(ntags), "elements": nel, "size": size, "size_min": size_min, "kind": kind,
               "types": ["%d %s (%s)" % (n, ELEMENT_NAMES.get(t, "type %d" % t), ABAQUS_NAMES.get(t, "-")) for t, n in sorted(counts.items())],
               "counts": {ELEMENT_NAMES.get(t, str(t)): n for t, n in counts.items()},
               "faces": len(surfs), "solids": len(vols), "cells": cells, "quality": quality, "path": out_path,
               "blocks": len(_block_cells(gmsh, vols)) if solid_kind else 0,
               "compounds": comp_info.get("compounds", 0), "compounds_skipped": comp_info.get("skipped", 0)}
        if opts.get("preview"):
            res["preview"] = _preview(gmsh, int(opts.get("preview_limit") or 400000))
        return res
    finally:
        gmsh.finalize()


def _compounds(gmsh, surfs, groups, min_area):
    """Virtual topology: groups of faces (by centre of mass) meshed as one compound surface; faces below min_area
    combined with their largest neighbour."""
    if not groups and min_area <= 0:
        return
    info = {}
    for d, t in surfs:
        c = gmsh.model.occ.getCenterOfMass(2, t)
        info[t] = (c, gmsh.model.occ.getMass(2, t))
    curves_of = {t: set(abs(ct) for cd, ct in gmsh.model.getBoundary([(2, t)], combined=False, oriented=False)) for d, t in surfs}

    def valid(tags):
        # the curves inside the group must not bound a surface outside it (they disappear from the mesh)
        inner = set()
        for i, a in enumerate(tags):
            for b in tags[i + 1:]:
                inner |= curves_of[a] & curves_of[b]
        return not any(inner & curves_of[o] for o in curves_of if o not in tags)

    used = set()
    out, skipped = [], 0
    for g in groups:
        tags = []
        for ref in g:
            best, bd = None, None
            for t, (c, a) in info.items():
                dd = sum((c[i] - ref["c"][i]) ** 2 for i in range(3))
                if bd is None or dd < bd:
                    best, bd = t, dd
            if best is not None and best not in used and best not in tags:
                tags.append(best)
        if len(tags) > 1:
            if valid(tags):
                out.append(tags)
                used.update(tags)
            else:
                skipped += 1
    if min_area > 0:
        for d, t in surfs:
            if t in used or info[t][1] >= min_area:
                continue
            nb = [(info[o][1], o) for o in curves_of if o != t and curves_of[o] & curves_of[t]]
            nb.sort(reverse=True)
            for a, o in nb:
                grp = next((gg for gg in out if o in gg), None)
                cand = (grp + [t]) if grp is not None else [o, t]
                if valid(cand):
                    if grp is not None:
                        grp.append(t)
                    else:
                        out.append([o, t])
                        used.add(o)
                    used.add(t)
                    break
    for tags in out:
        gmsh.model.mesh.setCompound(2, tags)
    return {"compounds": len(out), "skipped": skipped}


def _block_cells(gmsh, vols):
    """Cells for a structured mesh: blocks (6 faces of 4 edges, one loop each) and prisms (5 faces: 2 of 3 edges, 3 of
    4 edges; the prisms below a blind hole of a hole mesh give wedge elements along the axis)."""
    out = []
    for d, t in vols:
        faces = gmsh.model.getBoundary([(3, t)], combined=False, oriented=False, recursive=False)
        n = sorted(len(gmsh.model.getBoundary([(2, abs(ft))], combined=False, oriented=False)) for fd, ft in faces)
        if n == [4] * 6 or n == [3, 3, 4, 4, 4]:
            out.append((3, t))
    return out


class _UF(object):
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def _structured(gmsh, vols, size, seeds=None):
    """Transfinite (structured) constraints on the block cells (6 faces of 4 edges) and the prism cells (5 faces:
    2 triangles, 3 quadrangles). Edge counts are equal on opposite edges of every quadrangle and on the two edges at
    the apex of every triangle; a set of such edges gets the count of the hole seeds (elements per 45 deg arc,
    radial elements with bias, elements through the thickness) or length / size."""
    seeds = seeds or []
    cells = []
    for d, t in vols:
        faces = [abs(ft) for fd, ft in gmsh.model.getBoundary([(3, t)], combined=False, oriented=False, recursive=False)]
        loops = {f: [c for cd, c in gmsh.model.getBoundary([(2, f)], combined=False, oriented=True)] for f in faces}
        n = sorted(len(l) for l in loops.values())
        if n == [4] * 6 or n == [3, 3, 4, 4, 4]:
            cells.append((t, faces, loops))
    if not cells:
        return []
    pos = {}

    def vpos(v):
        if v not in pos:
            pos[v] = gmsh.model.getValue(0, v, [])
        return pos[v]

    def cv(c):
        b = gmsh.model.getBoundary([(1, abs(c))], combined=False, oriented=True)
        a, e = abs(b[0][1]), abs(b[-1][1])
        return (a, e) if c > 0 else (e, a)

    def axis_dist(p):
        best = None
        for s in seeds:
            q = [p[i] - s["p"][i] for i in range(3)]
            w = s["w"]
            t = sum(q[i] * w[i] for i in range(3))
            d = math.sqrt(max(sum(x * x for x in q) - t * t, 0.0))
            if best is None or d < best[0]:
                best = (d, s)
        return best

    uf = _UF()
    apex = {}
    for t, faces, loops in cells:
        for f, cs in loops.items():
            for c in cs:
                uf.find(abs(c))
            if len(cs) == 4:
                uf.union(abs(cs[0]), abs(cs[2]))
                uf.union(abs(cs[1]), abs(cs[3]))
            else:
                # apex: the corner nearest a hole axis (else the smallest angle)
                verts = [cv(c)[0] for c in cs]
                if seeds:
                    k = min(range(3), key=lambda i: axis_dist(vpos(verts[i]))[0])
                else:
                    def ang(i):
                        p0, p1, p2 = vpos(verts[i]), vpos(verts[i - 1]), vpos(verts[(i + 1) % 3])
                        a = [p1[j] - p0[j] for j in range(3)]
                        b = [p2[j] - p0[j] for j in range(3)]
                        ab = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b)) or 1.0
                        return math.acos(max(-1.0, min(1.0, sum(a[j] * b[j] for j in range(3)) / ab)))
                    k = min(range(3), key=ang)
                apex[f] = verts[k]
                ins = [abs(c) for c in cs if verts[k] in cv(c)]
                uf.union(ins[0], ins[1])
    classes = {}
    for c in list(uf.p):
        classes.setdefault(uf.find(c), []).append(c)

    def kind(c):
        """"arc" | "radial" | "axial" | ""  and the seed of the hole."""
        typ = gmsh.model.getType(1, c)
        a, b = cv(c)
        pa, pb = vpos(a), vpos(b)
        if not seeds:
            return "", None, pa, pb
        da, sa = axis_dist(pa)
        db, sb = axis_dist(pb)
        s = sa if da <= db else sb
        w = s["w"]
        dv = [pb[i] - pa[i] for i in range(3)]
        L = math.sqrt(sum(x * x for x in dv)) or 1.0
        along = abs(sum(dv[i] * w[i] for i in range(3))) / L
        reach = s["half"] * math.sqrt(2) * 1.001

        def in_square(p):
            q = [p[i] - s["p"][i] for i in range(3)]
            return all(abs(sum(q[i] * e[i] for i in range(3))) <= s["half"] * 1.000001 for e in (s["u"], s["v"]))
        if typ != "Line" and abs(da - db) < 1e-6 * reach and da < reach:
            lo, hi = gmsh.model.getParametrizationBounds(1, c)
            pm = gmsh.model.getValue(1, c, [(lo[0] + hi[0]) / 2.0])
            if abs(axis_dist(pm)[0] - da) < 1e-6 * reach:
                return "arc", s, pa, pb
        if along > 1 - 1e-6:
            return "axial", s, pa, pb
        # radial: a straight edge normal to the axis on a line through the axis, inside the square
        through_axis = False
        if typ == "Line" and L > 0:
            e = [x / L for x in dv]
            q = [pa[i] - s["p"][i] for i in range(3)]
            cr = [q[1] * e[2] - q[2] * e[1], q[2] * e[0] - q[0] * e[2], q[0] * e[1] - q[1] * e[0]]
            through_axis = abs(sum(cr[i] * w[i] for i in range(3))) < 1e-6 * reach
        if along < 1e-6 and through_axis and in_square(pa) and in_square(pb) and abs(da - db) > 1e-6 * reach:
            return ("core" if min(da, db) < 1e-6 * reach else "radial"), s, pa, pb
        return "", s, pa, pb

    counts = {}
    progression = {}
    for root, cs in classes.items():
        kinds = [kind(c) for c in cs]
        ks = {k[0] for k in kinds}
        n = None
        if "arc" in ks:
            s = next(k[1] for k in kinds if k[0] == "arc")
            n = int(s["n_circ"])
        elif "radial" in ks:
            # n_rad elements from the hole wall to the square; a ring between two radii gets its share by length
            s = next(k[1] for k in kinds if k[0] == "radial")
            span = s["half"] - min(s["radii"])
            L = min(math.dist(k[2], k[3]) for k in kinds if k[0] == "radial")      # along u or v (the shortest)
            n_all = int(s["n_rad"])
            n = max(1, int(round(n_all * L / span))) if span > 0 else n_all
            B = float(s.get("bias") or 1.0)
            if n > 1 and n_all > 1 and abs(B - 1) > 1e-9:
                coef = B ** (1.0 / (n_all - 1))
                for c, (k, ss, pa, pb) in zip(cs, kinds):
                    da, db = axis_dist(pa)[0], axis_dist(pb)[0]
                    progression[c] = coef if da < db else 1.0 / coef
        elif "core" in ks:
            s = next(k[1] for k in kinds if k[0] == "core")
            n = max(1, int(round(int(s["n_circ"]) * 4 / math.pi * 0.5)))
        elif "axial" in ks:
            s = next(k[1] for k in kinds if k[0] == "axial")
            L = max(math.dist(k[2], k[3]) for k in kinds)
            n = max(1, int(round(int(s["n_thick"]) * L / s["T"])))
        if n is None:
            L = max(gmsh.model.occ.getMass(1, c) for c in cs)
            n = max(1, int(math.ceil(L / size - 1e-9)))
        for c in cs:
            counts[c] = n
    for c, n in counts.items():
        if c in progression:
            gmsh.model.mesh.setTransfiniteCurve(c, n + 1, "Progression", progression[c])
        else:
            gmsh.model.mesh.setTransfiniteCurve(c, n + 1)
    done = set()
    for t, faces, loops in cells:
        for f in faces:
            if f in done:
                continue
            done.add(f)
            if f in apex:
                cs = loops[f]
                verts = [cv(c)[0] for c in cs]
                k = verts.index(apex[f])
                gmsh.model.mesh.setTransfiniteSurface(f, "Left", [verts[k], verts[(k + 1) % 3], verts[(k + 2) % 3]])
            else:
                gmsh.model.mesh.setTransfiniteSurface(f)
            gmsh.model.mesh.setRecombine(2, f)
        gmsh.model.mesh.setTransfiniteVolume(t)
    return [(3, t) for t, faces, loops in cells]


def _preview(gmsh, limit):
    """Unique edges of the boundary elements as line segments [[x, y, z], [x, y, z]] for the 3D view."""
    ntags, coords, _ = gmsh.model.mesh.getNodes()
    pos = {}
    for k, t in enumerate(ntags):
        pos[int(t)] = (round(coords[3 * k], 4), round(coords[3 * k + 1], 4), round(coords[3 * k + 2], 4))
    etypes, etags, enodes = gmsh.model.mesh.getElements(2)
    edges = set()
    corners = {2: 3, 3: 4, 9: 3, 10: 4, 16: 4}            # corner nodes come first in gmsh ordering
    for t, tags, nodes in zip(etypes, etags, enodes):
        nc = corners.get(int(t))
        if not nc:
            continue
        props = gmsh.model.mesh.getElementProperties(int(t))
        nn = props[3]
        for i in range(len(tags)):
            ns = [int(v) for v in nodes[i * nn:i * nn + nc]]
            for a, b in zip(ns, ns[1:] + ns[:1]):
                edges.add((a, b) if a < b else (b, a))
            if len(edges) > limit:
                break
    return [[pos[a], pos[b]] for a, b in edges if a in pos and b in pos]


if __name__ == "__main__":
    step, out = sys.argv[1], sys.argv[2]
    o = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    try:
        res = _mesh(step, out, o)
    except Exception as e:
        sys.stderr.write("%s\n" % e)
        sys.exit(1)
    print("RESULT " + json.dumps(res))
