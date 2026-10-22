# -*- coding: utf-8 -*-
"""Assemblies: placed components from saved parts or STEP files.

Assembly record (JSON):
  {"name", "components": [component, ...], "next": n}

Component:
  {"id", "name", "source": {"type": "part", "name": <saved part>} | {"type": "step", "path": <file>, "part": <solid name or null>},
   "pos": [x, y, z] (mm), "rot": [rx, ry, rz] (deg, rotations about the fixed X, then Y, then Z axis, about the origin of
   the component, applied before the translation), "color": "#rrggbb", "visible": true, "density": kg/m^3 or null,
   "explode": [dx, dy, dz] (mm, exploded view offset)}
"""
import json
import math
import os
import threading

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

from . import part as partmod


def trsf_of(c, explode=False):
    """gp_Trsf of a component: rotation X, Y, Z about the origin, then translation (plus explode offset)."""
    t = gp_Trsf()
    rot = c.get("rot") or [0, 0, 0]
    for axis, ang in zip(((1, 0, 0), (0, 1, 0), (0, 0, 1)), rot):
        if abs(float(ang or 0)) > 1e-12:
            r = gp_Trsf()
            r.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(*axis)), math.radians(float(ang)))
            t = r.Multiplied(t)
    pos = [float(v or 0) for v in (c.get("pos") or [0, 0, 0])]
    if explode:
        ex = c.get("explode") or [0, 0, 0]
        pos = [p + float(e or 0) for p, e in zip(pos, ex)]
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(*pos))
    return tr.Multiplied(t)


def place(shape, c, explode=False):
    """Component shape (build123d) moved by the component transform."""
    from build123d import Shape
    bt = BRepBuilderAPI_Transform(shape.wrapped, trsf_of(c, explode), True)
    return Shape.cast(bt.Shape())


def _step_solids(path):
    from . import model
    return model.step_solids(path)


def fast_mesh(shape, tol=None):
    """View mesh of a component (local coordinates): vertices, triangles, face_of_tri (index into shape.faces()),
    edges (polylines), bbox. One BRepMesh pass; triangles and edge polylines are read from the triangulation."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopAbs import TopAbs_REVERSED, TopAbs_EDGE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS
    to_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge          # OCCT 8: TopoDS.Edge
    try:
        from OCP.TopTools import TopTools_IndexedMapOfShape
    except ImportError:                       # OCCT 8
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
    bb = shape.bounding_box()
    tol = tol or max(bb.diagonal / 2000.0, 0.005)
    BRepMesh_IncrementalMesh(shape.wrapped, tol, False, 0.3, True)
    emap = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape.wrapped, TopAbs_EDGE, emap)
    done = set()
    verts, tris, face_of_tri, edges = [], [], [], []
    for fi, fc in enumerate(shape.faces()):
        f = fc.wrapped
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        trsf = loc.Transformation()
        ident = loc.IsIdentity()
        base = len(verts)
        for i in range(1, tri.NbNodes() + 1):
            p = tri.Node(i)
            if not ident:
                p = p.Transformed(trsf)
            verts.append([round(p.X(), 5), round(p.Y(), 5), round(p.Z(), 5)])
        rev = f.Orientation() == TopAbs_REVERSED
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            tris.append([base + a - 1, base + c - 1, base + b - 1] if rev else [base + a - 1, base + b - 1, base + c - 1])
        face_of_tri += [fi] * tri.NbTriangles()
        ex = TopExp_Explorer(f, TopAbs_EDGE)
        while ex.More():
            e = to_edge(ex.Current())
            ex.Next()
            k = emap.FindIndex(e)
            if k in done:
                continue
            poly = BRep_Tool.PolygonOnTriangulation_s(e, tri, loc)
            if poly is None:
                continue
            done.add(k)
            nodes = poly.Nodes()
            edges.append([verts[base + nodes.Value(j) - 1] for j in range(nodes.Lower(), nodes.Upper() + 1)])
    return {"vertices": verts, "triangles": tris, "face_of_tri": face_of_tri, "edges": edges,
            "bbox": [bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z]}


# view data of the sources on disk (mesh, face references, planes and axes, volume), so the first build after a
# server start does not load or tessellate unchanged sources: <cache dir>/<mkey>.json.gz
_VIEW_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "drawgen", "viewcache")
_VIEW_KEYS = ("mesh", "refs", "datums", "vol", "cog", "err", "mkey")


def _view_read(mkey):
    import gzip
    try:
        with gzip.open(os.path.join(_VIEW_DIR, mkey + ".json.gz"), "rt", encoding="utf-8") as f:
            d = json.load(f)
        # entries written before the centre planes existed are computed again
        return d if all(k in d for k in ("mesh", "refs", "vol", "cog")) and "cplane:XY" in (d.get("datums") or {}) else None
    except (OSError, ValueError, EOFError):
        return None


def _view_write(e):
    import gzip
    try:
        os.makedirs(_VIEW_DIR, exist_ok=True)
        path = os.path.join(_VIEW_DIR, e["mkey"] + ".json.gz")
        tmp = path + ".%d.%d.tmp" % (os.getpid(), threading.get_ident())
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=1) as f:
            json.dump({k: e.get(k) for k in _VIEW_KEYS}, f)
        os.replace(tmp, path)
        files = [os.path.join(_VIEW_DIR, n) for n in os.listdir(_VIEW_DIR) if n.endswith((".json.gz", ".brep"))]
        if len(files) > 1200:                         # keep the 1000 newest
            files.sort(key=os.path.getmtime)
            for fn in files[:-1000]:
                try:
                    os.remove(fn)
                except OSError:
                    pass
    except OSError:
        pass


def _brep_read(k):
    """Shape of a source from the BRep cache (<cache dir>/<mkey>.brep), or None."""
    path = os.path.join(_VIEW_DIR, _mkey(k) + ".brep")
    if not os.path.isfile(path):
        return None
    try:
        from build123d import import_brep
        return import_brep(path)
    except Exception:
        return None


def _brep_write(k, shape):
    path = os.path.join(_VIEW_DIR, _mkey(k) + ".brep")
    if os.path.isfile(path):
        return
    try:
        from build123d import export_brep
        os.makedirs(_VIEW_DIR, exist_ok=True)
        tmp = path + ".%d.%d.tmp.brep" % (os.getpid(), threading.get_ident())
        export_brep(shape, tmp)
        os.replace(tmp, path)
    except Exception:
        pass


def _step_key(path, part):
    st = os.stat(path)
    return ("step", os.path.normcase(os.path.abspath(path)), st.st_mtime, st.st_size, str(part))


def write_step_breps(path, solids):
    """Writes each solid of a STEP file to the BRep cache (a BRep file reads much faster than the STEP file)."""
    try:
        for i, (_nm, sh) in enumerate(solids):
            _brep_write(_step_key(path, i), sh)
    except OSError:
        pass


def _worker_split_step(path):
    """Worker: reads a STEP file once and writes its solids to the BRep cache; returns the solid count."""
    comp, solids = _step_solids(path)
    write_step_breps(path, solids)
    return len(solids)


def _mkey(k):
    import hashlib
    return hashlib.sha1(repr(k).encode("utf-8")).hexdigest()[:16]


_SRC_CACHE = {}     # source key -> {"shape", "err", and once computed: "mesh", "refs", "vol", "cog", "mkey"}
_SRC_CACHE_MAX = 300


class Sources(object):
    """Loads component source shapes. Shapes, their view meshes, face references and volume properties are kept
    between builds, keyed by the source and the state of its files (part file content, imported STEP files, STEP file
    modification time and size), so a component whose source is unchanged is not rebuilt or tessellated again."""

    def __init__(self, part_dir, file_registry=None):
        self.part_dir = part_dir
        self.files = file_registry or {}
        self.cache = {}
        self.keys = {}
        self.fdatums = {}       # source json -> [(feature id, name, datum)] of the plane and axis features of a part

    def _step_path(self, src):
        path = src.get("path", "")
        fid = src.get("file_id")
        if fid and fid in self.files:
            path = self.files[fid]["path"]
        return path

    def key(self, src):
        """Cache key of a source, or None when its files cannot be read (not cached)."""
        import hashlib
        jk = json.dumps(src, sort_keys=True)
        if jk in self.keys:
            return self.keys[jk]
        k = None
        try:
            if src.get("type") == "part":
                path = os.path.join(self.part_dir, partmod_safe(src.get("name", "")) + ".part.json")
                with open(path, "rb") as f:
                    data = f.read()
                stamps = []
                for f in (json.loads(data.decode("utf-8")).get("features") or []):
                    ip = (f.get("path") or "").strip().strip('"') if f.get("type") in ("import", "surf_import") else ""
                    if ip and os.path.isfile(ip):
                        st = os.stat(ip)
                        stamps.append((ip, st.st_mtime, st.st_size))
                k = ("part", os.path.normcase(os.path.abspath(path)), hashlib.sha1(data).hexdigest(), tuple(stamps))
            elif src.get("type") == "step":
                path = self._step_path(src)
                st = os.stat(path)
                k = ("step", os.path.normcase(os.path.abspath(path)), st.st_mtime, st.st_size, str(src.get("part")))
        except (OSError, ValueError):
            k = None
        self.keys[jk] = k
        return k

    def info(self, src):
        """Cache entry of a source with the local mesh, face references, planes and axes, volume and centre of mass:
        from memory, else from the view cache on disk (the shape is then loaded only when needed), else computed."""
        k = self.key(src)
        e = _SRC_CACHE.get(k) if k is not None else None
        if e is not None and "mesh" in e:
            return e
        if k is not None and e is None:
            d = _view_read(_mkey(k))
            if d is not None:
                d["mkey"] = _mkey(k)
                _SRC_CACHE[k] = d
                return d
        shape, err = self.load(src)
        e = _SRC_CACHE.get(k) if k is not None else None
        if e is None:
            e = {"shape": shape, "err": err}
        if shape is not None and "mesh" not in e:
            # computed into a new dict and added in one update: a build in another thread that finds "mesh" also
            # finds the other entries
            try:
                mesh = fast_mesh(shape)
            except Exception:
                mesh = partmod.mesh(shape)
            g = GProp_GProps()
            BRepGProp.VolumeProperties_s(shape.wrapped, g)
            cm = g.CentreOfMass()
            e.update({"refs": face_refs(shape),
                      "datums": datum_refs(shape, self.fdatums.get(json.dumps(src, sort_keys=True)) or e.get("fdatums") or []),
                      "vol": g.Mass(), "cog": (cm.X(), cm.Y(), cm.Z()), "mkey": _mkey(k if k is not None else id(e)),
                      "mesh": mesh})
            if k is not None:
                _view_write(e)
        return e

    def load(self, src):
        jk = json.dumps(src, sort_keys=True)
        if jk in self.cache:
            return self.cache[jk]
        k = self.key(src)
        if k is not None and "shape" in _SRC_CACHE.get(k, {}):
            e = _SRC_CACHE[k]
            self.cache[jk] = (e["shape"], e["err"])
            return self.cache[jk]
        shape, err = self._load(src)
        if k is not None:
            if k not in _SRC_CACHE:
                while len(_SRC_CACHE) >= _SRC_CACHE_MAX:
                    _SRC_CACHE.pop(next(iter(_SRC_CACHE)))
                _SRC_CACHE[k] = {}
            _SRC_CACHE[k].update({"shape": shape, "err": err, "fdatums": self.fdatums.get(jk) or []})
        self.cache[jk] = (shape, err)
        return shape, err

    def _load(self, src):
        shape, err = None, None
        try:
            if src.get("type") == "part":
                path = os.path.join(self.part_dir, partmod_safe(src.get("name", "")) + ".part.json")
                with open(path, "r", encoding="utf-8") as f:
                    p = json.load(f)
                dz = {}
                shape, st = partmod.build(p, datums=dz)
                names = {f.get("id"): f.get("name") or f.get("id") for f in p.get("features") or []}
                self.fdatums[json.dumps(src, sort_keys=True)] = [(fid, names.get(fid, fid), d) for fid, d in dz.items()
                                                                if d.get("kind") in ("plane", "axis")]
                bad = [s["error"] for s in st if s.get("error")]
                if shape is None:
                    err = "part %s has no solid" % src.get("name")
                elif bad:
                    err = "part %s: %s" % (src.get("name"), bad[0])
            elif src.get("type") == "step":
                path = self._step_path(src)
                if not os.path.isfile(path):
                    err = "file not found: %s" % path
                else:
                    k = self.key(src)
                    shape = _brep_read(k) if k is not None else None
                    if shape is not None:
                        return shape, None
                    comp, solids = _step_solids(path)
                    want = src.get("part")
                    if want is not None and want != "":
                        # by index or by label
                        pick = None
                        try:
                            pick = solids[int(want)][1]
                        except (ValueError, IndexError, TypeError):
                            for nm, s in solids:
                                if nm == want:
                                    pick = s
                        shape = pick
                        if shape is None:
                            err = "solid %s not found in %s" % (want, os.path.basename(path))
                    else:
                        shape = comp if len(solids) != 1 else solids[0][1]
                    write_step_breps(path, solids)
                    if shape is not None and k is not None and (want is None or want == ""):
                        _brep_write(k, shape)
            else:
                err = "unknown source type"
        except Exception as e:
            err = str(e)
        return shape, err


def partmod_safe(s):
    import re
    return re.sub(r"[^A-Za-z0-9_\-.]+", "_", s).strip("_") or "part"


def build(asm, sources, explode=False):
    """Returns [(component, placed shape or None, error)]."""
    out = []
    for c in asm.get("components") or []:
        shape, err = sources.load(c.get("source") or {})
        placed = None
        if shape is not None:
            try:
                placed = place(shape, c, explode)
            except Exception as e:
                err = str(e)
        out.append((c, placed, err))
    return out


def datum_refs(shape, fdatums):
    """Reference planes and axes of a component in its local coordinates: the principal planes XY, XZ, YZ and the
    axes X, Y, Z through the origin, the centre planes and axes (the same directions through the centre of the
    bounding box), and the plane and axis features of a part. {key: ref}; a plane ref is {"kind": "plane", "c", "n"},
    an axis ref {"kind": "axis", "c", "p", "n"}; "name" and "size" (mm, for drawing)."""
    try:
        bb = shape.bounding_box()
        size = max(bb.size.X, bb.size.Y, bb.size.Z, 1.0)
        ctr = [float(bb.center().X), float(bb.center().Y), float(bb.center().Z)]
    except Exception:
        size = 100.0
        ctr = [0.0, 0.0, 0.0]
    out = {}
    for key, n in (("XY", [0, 0, 1]), ("XZ", [0, -1, 0]), ("YZ", [1, 0, 0])):
        out["plane:" + key] = {"kind": "plane", "name": "Plane " + key, "c": [0.0, 0.0, 0.0], "n": n, "size": size}
    for key, n in (("X", [1, 0, 0]), ("Y", [0, 1, 0]), ("Z", [0, 0, 1])):
        out["axis:" + key] = {"kind": "axis", "name": "Axis " + key, "c": [0.0, 0.0, 0.0], "p": [0.0, 0.0, 0.0], "n": n, "size": size}
    for key, n in (("XY", [0, 0, 1]), ("XZ", [0, -1, 0]), ("YZ", [1, 0, 0])):
        out["cplane:" + key] = {"kind": "plane", "name": "Centre plane " + key, "c": list(ctr), "n": n, "size": size}
    for key, n in (("X", [1, 0, 0]), ("Y", [0, 1, 0]), ("Z", [0, 0, 1])):
        out["caxis:" + key] = {"kind": "axis", "name": "Centre axis " + key, "c": list(ctr), "p": list(ctr), "n": n, "size": size}
    for fid, name, d in fdatums or []:
        try:
            if d.get("kind") == "plane":
                out["feat:" + fid] = {"kind": "plane", "name": name, "c": [float(v) for v in d["o"]],
                                      "n": _norm([float(v) for v in d["z"]]), "x": _norm([float(v) for v in d["x"]]), "size": size}
            elif d.get("kind") == "axis":
                o = [float(v) for v in d["o"]]
                out["feat:" + fid] = {"kind": "axis", "name": name, "c": o, "p": o, "n": _norm([float(v) for v in d["d"]]), "size": size}
        except (KeyError, TypeError, ValueError):
            continue
    return out


# --------------------------------------------------------------------------- worker pool (pool.py)

def _worker_view(src, part_dir, files):
    """Worker: view data of one source (computed and written to the view cache)."""
    e = Sources(part_dir, files).info(src)
    if "mesh" not in e:
        return {"err": e.get("err") or "no solid"}
    return {k: e.get(k) for k in _VIEW_KEYS}


def prefetch_views(asm, sources):
    """Computes the view data of the sources that are neither in memory nor in the view cache, in the worker
    processes in parallel. Sources that fail here are computed in the server by view_data. Returns the count."""
    from . import pool as _pool
    from concurrent.futures import as_completed
    todo = {}
    for c in asm.get("components") or []:
        src = c.get("source") or {}
        k = sources.key(src)
        if k is None or k in todo:
            continue
        e = _SRC_CACHE.get(k)
        if e is not None and "mesh" in e:
            continue
        if e is None:
            d = _view_read(_mkey(k))
            if d is not None:
                d["mkey"] = _mkey(k)
                _SRC_CACHE[k] = d
                continue
        todo[k] = src
    p = _pool.get() if len(todo) > 1 else None
    if p is None:
        return 0
    # STEP files: read once in one worker, which writes the solids to the BRep cache; the solids are then meshed
    # in all workers from their BRep files
    files = {}
    for k, src in todo.items():
        if k[0] == "step" and k[4] not in ("None", "") and not os.path.isfile(os.path.join(_VIEW_DIR, _mkey(k) + ".brep")):
            files.setdefault(sources._step_path(src), []).append(k)
    try:
        split = [p.submit(_worker_split_step, path) for path, ks in files.items() if len(ks) > 1]
        for f in split:
            f.result()
    except Exception:
        _pool.reset()
        return 0
    try:
        futs = {p.submit(_worker_view, src, os.fspath(sources.part_dir), dict(sources.files)): k for k, src in todo.items()}
    except Exception:
        _pool.reset()
        return 0
    n = 0
    for f in as_completed(futs):
        k = futs[f]
        try:
            d = f.result()
        except Exception:
            if f.exception() is not None and "Broken" in type(f.exception()).__name__:
                _pool.reset()
            continue
        if "mesh" not in d:
            continue                                  # computed again in the server, with the error text
        e = _SRC_CACHE.setdefault(k, {})
        e.update(d)
        n += 1
    return n


def _common_volume(sa, sb):
    """Volume (mm^3) of the overlap of two placed solids, 0 when their boxes are apart."""
    ba, bb = sa.bounding_box(), sb.bounding_box()
    if (ba.max.X < bb.min.X - 1e-6 or bb.max.X < ba.min.X - 1e-6 or
            ba.max.Y < bb.min.Y - 1e-6 or bb.max.Y < ba.min.Y - 1e-6 or
            ba.max.Z < bb.min.Z - 1e-6 or bb.max.Z < ba.min.Z - 1e-6):
        return 0.0
    common = sa.intersect(sb)
    if common is None:
        return 0.0
    vol = 0.0
    for s in (list(common) if isinstance(common, (list, tuple)) else [common]):
        try:
            vol += s.volume
        except Exception:
            pass
    return vol


def _worker_interference(pairs, comps, part_dir, files, explode):
    """Worker: overlap volume of each pair of components [(id a, id b)]; comps: {id: component}."""
    src = Sources(part_dir, files)
    placed = {}

    def get(cid):
        if cid not in placed:
            c = comps[cid]
            shape, err = src.load(c.get("source") or {})
            placed[cid] = place(shape, c, explode) if shape is not None else None
        return placed[cid]

    out = []
    for a, b in pairs:
        try:
            sa, sb = get(a), get(b)
            out.append((a, b, _common_volume(sa, sb) if sa is not None and sb is not None else 0.0))
        except Exception:
            out.append((a, b, 0.0))
    return out


def interference_parallel(asm, sources, explode=False, min_volume=1e-3):
    """interference() in the worker processes: the pairs whose boxes overlap (from the cached view meshes and the
    placements) are split over the workers. None when there is no pool (the caller uses interference())."""
    from . import pool as _pool
    p = _pool.get()
    if p is None:
        return None
    vis = [c for c in asm.get("components") or [] if c.get("visible") is not False]
    boxes = {}
    for c in vis:
        e = sources.info(c.get("source") or {})
        if "mesh" not in e or not e["mesh"].get("bbox"):
            continue
        x0, y0, z0, x1, y1, z1 = e["mesh"]["bbox"]
        t = trsf_of(c, explode)
        pts = [gp_Pnt(x, y, z).Transformed(t) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        boxes[c["id"]] = ([min(q.X() for q in pts), min(q.Y() for q in pts), min(q.Z() for q in pts)],
                          [max(q.X() for q in pts), max(q.Y() for q in pts), max(q.Z() for q in pts)])
    ids = [c["id"] for c in vis if c["id"] in boxes]
    pairs = []
    for i in range(len(ids)):
        lo_a, hi_a = boxes[ids[i]]
        for j in range(i + 1, len(ids)):
            lo_b, hi_b = boxes[ids[j]]
            if all(hi_a[d] >= lo_b[d] - 1e-6 and hi_b[d] >= lo_a[d] - 1e-6 for d in range(3)):
                pairs.append((ids[i], ids[j]))
    if not pairs:
        return []
    comps = {c["id"]: c for c in vis}
    nch = min(len(pairs), _pool.size() * 2)
    chunks = [pairs[i::nch] for i in range(nch)]
    try:
        futs = [p.submit(_worker_interference, ch, {cid: comps[cid] for pr in ch for cid in pr},
                         os.fspath(sources.part_dir), dict(sources.files), explode) for ch in chunks]
        res = [r for f in futs for r in f.result()]
    except Exception:
        _pool.reset()
        return None
    out = []
    order = {pr: n for n, pr in enumerate(pairs)}
    for a, b, vol in sorted(res, key=lambda r: order.get((r[0], r[1]), 0)):
        if vol > min_volume:
            out.append({"a": a, "b": b, "a_name": comps[a].get("name"), "b_name": comps[b].get("name"), "volume_mm3": vol})
    return out


def view_data(asm, sources, explode=False, have=(), default_density=0.0):
    """3D view data without placing or tessellating shapes: per component the cached local mesh (left out when the
    client already holds its mkey), face references, the placement matrix (3 x 4, row-major) and mass properties
    from the local volume and centre of mass."""
    comps, rows = [], []
    tm = tv = cx = cy = cz = 0.0
    have = set(have or ())
    for c in asm.get("components") or []:
        try:
            e = sources.info(c.get("source") or {})
        except Exception as ex:
            e = {"shape": None, "err": str(ex)}
        if "mesh" not in e:
            comps.append({"id": c.get("id"), "error": e.get("err") or "no solid", "mesh": None})
            continue
        t = trsf_of(c, explode)
        mat = [t.Value(i, j) for i in (1, 2, 3) for j in (1, 2, 3, 4)]
        out = {"id": c.get("id"), "error": e.get("err"), "mkey": e["mkey"], "matrix": mat,
               "color": c.get("color"), "visible": c.get("visible") is not False}
        if e["mkey"] not in have:
            out["mesh"], out["refs"], out["datums"] = e["mesh"], e["refs"], e.get("datums") or {}
        comps.append(out)
        if c.get("visible") is False:
            continue
        p = gp_Pnt(*e["cog"]).Transformed(t)
        v = e["vol"]
        rho = float(c.get("density") or default_density or 0)
        m = v * 1e-9 * rho
        rows.append({"id": c.get("id"), "name": c.get("name"), "volume_mm3": v, "mass_kg": m,
                     "cog": [p.X(), p.Y(), p.Z()], "density": rho})
        tv += v
        tm += m
        cx += m * p.X()
        cy += m * p.Y()
        cz += m * p.Z()
    tot = {"volume_mm3": tv, "mass_kg": tm, "cog": [cx / tm, cy / tm, cz / tm] if tm > 0 else None}
    return comps, rows, tot


def mass_props(items, default_density):
    """Per component and total: volume (mm^3), mass (kg), centre of mass (mm)."""
    rows = []
    tm, cx, cy, cz = 0.0, 0.0, 0.0, 0.0
    tv = 0.0
    for c, s, err in items:
        if s is None or c.get("visible") is False:
            continue
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(s.wrapped, g)
        v = g.Mass()
        rho = float(c.get("density") or default_density or 0)
        m = v * 1e-9 * rho
        cm = g.CentreOfMass()
        rows.append({"id": c.get("id"), "name": c.get("name"), "volume_mm3": v, "mass_kg": m,
                     "cog": [cm.X(), cm.Y(), cm.Z()], "density": rho})
        tv += v
        tm += m
        cx += m * cm.X()
        cy += m * cm.Y()
        cz += m * cm.Z()
    tot = {"volume_mm3": tv, "mass_kg": tm, "cog": [cx / tm, cy / tm, cz / tm] if tm > 0 else None}
    return rows, tot


def interference(items, min_volume=1e-3):
    """Pairs of components whose solids overlap: [{a, b, volume_mm3}]."""
    out = []
    vis = [(c, s) for c, s, err in items if s is not None and c.get("visible") is not False]
    for i in range(len(vis)):
        for j in range(i + 1, len(vis)):
            ca, sa = vis[i]
            cb, sb = vis[j]
            try:
                ba, bb = sa.bounding_box(), sb.bounding_box()
                if (ba.max.X < bb.min.X - 1e-6 or bb.max.X < ba.min.X - 1e-6 or
                        ba.max.Y < bb.min.Y - 1e-6 or bb.max.Y < ba.min.Y - 1e-6 or
                        ba.max.Z < bb.min.Z - 1e-6 or bb.max.Z < ba.min.Z - 1e-6):
                    continue
                common = sa.intersect(sb)
                if common is None:
                    continue
                shapes = list(common) if isinstance(common, (list, tuple)) else [common]
                vol = 0.0
                for s in shapes:
                    try:
                        vol += s.volume
                    except Exception:
                        pass
                if vol > min_volume:
                    out.append({"a": ca.get("id"), "b": cb.get("id"), "a_name": ca.get("name"), "b_name": cb.get("name"),
                                "volume_mm3": vol})
            except Exception:
                continue
    return out


def export_step(asm, items, path):
    """STEP with one product per component (labels from the component names)."""
    from build123d import Compound, export_step as _ex
    children = []
    for c, s, err in items:
        if s is None or c.get("visible") is False:
            continue
        sc = s
        try:
            sc.label = c.get("name") or c.get("id")
        except Exception:
            pass
        children.append(sc)
    comp = Compound(children=children)
    comp.label = asm.get("name") or "assembly"
    _ex(comp, path)


# --------------------------------------------------------------------------- mates

def face_refs(local_shape):
    """Face references of a component in its local coordinates: kind plane | cylinder | other,
    c (centre), n (plane normal or cylinder axis direction), p (point on the axis), r (radius), area."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    out = []
    for f in local_shape.faces():
        try:
            c = f.center()
            ref = {"kind": "other", "c": [round(c.X, 4), round(c.Y, 4), round(c.Z, 4)], "area": round(f.area, 4)}
            ad = BRepAdaptor_Surface(f.wrapped)
            t = ad.GetType()
            if t == GeomAbs_Plane:
                n = f.normal_at(c)
                ref.update(kind="plane", n=[round(n.X, 6), round(n.Y, 6), round(n.Z, 6)])
            elif t == GeomAbs_Cylinder:
                cy = ad.Cylinder()
                ax = cy.Axis()
                L, D = ax.Location(), ax.Direction()
                ref.update(kind="cylinder", p=[round(L.X(), 4), round(L.Y(), 4), round(L.Z(), 4)],
                           n=[round(D.X(), 6), round(D.Y(), 6), round(D.Z(), 6)], r=round(cy.Radius(), 4))
            out.append(ref)
        except Exception:
            out.append(None)
    return out


def _rot_matrix(rot):
    """3x3 rotation matrix: Rz * Ry * Rx (same convention as trsf_of)."""
    rx, ry, rz = [math.radians(float(a or 0)) for a in rot]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    Rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    Rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    def mm(A, B):
        return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mm(Rz, mm(Ry, Rx))


def _euler_of(R):
    """Euler angles (deg, about X then Y then Z) of a rotation matrix built by _rot_matrix."""
    sy = -R[2][0]
    sy = max(-1.0, min(1.0, sy))
    ry = math.asin(sy)
    if abs(sy) < 0.999999:
        rx = math.atan2(R[2][1], R[2][2])
        rz = math.atan2(R[1][0], R[0][0])
    else:
        rx = math.atan2(-R[1][2], R[1][1])
        rz = 0.0
    return [math.degrees(rx), math.degrees(ry), math.degrees(rz)]


def _axis_rot(axis, ang):
    """Rotation matrix about a unit axis by ang (rad)."""
    x, y, z = axis
    c, s = math.cos(ang), math.sin(ang)
    C = 1 - c
    return [[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C]]


def _mm(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _apply(R, pos, v, point=True):
    out = [sum(R[i][k] * v[k] for k in range(3)) for i in range(3)]
    if point:
        out = [out[i] + pos[i] for i in range(3)]
    return out


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _norm(a):
    L = math.sqrt(_dot(a, a)) or 1.0
    return [a[0] / L, a[1] / L, a[2] / L]


def _perp_basis(n):
    a = [1, 0, 0] if abs(n[0]) < 0.9 else [0, 1, 0]
    u = _norm(_cross(n, a))
    v = _cross(n, u)
    return u, v


def _placed_ref(ref, params):
    """Reference in world coordinates for component params (pos, rot)."""
    pos, rot = params
    R = _rot_matrix(rot)
    out = dict(ref)
    out["c"] = _apply(R, pos, ref["c"])
    if "n" in ref:
        out["n"] = _apply(R, pos, ref["n"], point=False)
    if "p" in ref:
        out["p"] = _apply(R, pos, ref["p"])
    return out


TOL_MM = 0.01          # a mate is reported as not satisfied above these errors
TOL_DEG = 0.1


def _residuals(mate, A, B):
    """Residuals of a mate between the placed references A and B."""
    return _residuals_split(mate, A, B)[0]


def mate_error(mate, A, B):
    """(position error mm, direction error deg) of a mate between the placed references A and B."""
    res, nd = _residuals_split(mate, A, B)
    ang = max([abs(v) for v in res[:nd]] or [0.0])
    return max([abs(v) for v in res[nd:]] or [0.0]), math.degrees(math.asin(min(1.0, ang)))


def _residuals_split(mate, A, B):
    """(residuals, number of direction residuals at the start of the list) of a mate."""
    t = mate.get("type")
    sgn = -1.0 if mate.get("flip") else 1.0
    val = float(mate.get("value") or 0)
    res = []
    na, nb = A.get("n"), B.get("n")
    ka, kb = A.get("kind"), B.get("kind")
    line = ("axis", "cylinder")
    if "axis" in (ka, kb) and t in ("coincident", "distance", "parallel") and na is not None and nb is not None:
        # a reference axis with a plane (planar face or reference plane) or with another axis or cylinder
        if ka in line and kb in line:
            target = [-sgn * x for x in nb]          # axis directions opposite, Flip: the same
            res += [na[i] - target[i] for i in range(3)]
            nd = 3
            if t != "parallel":                      # coincident: collinear; distance: parallel at the distance
                d = _sub(B.get("p") or B["c"], A.get("p") or A["c"])
                off = _sub(d, [_dot(d, nb) * x for x in nb])
                if t == "coincident":
                    res += off
                else:
                    res.append(math.sqrt(_dot(off, off) + 1e-18) - val)
            return res, nd
        pl, ax = (A, B) if ka == "plane" else (B, A)
        if pl.get("kind") != "plane":
            raise ValueError("an axis mates with a plane, an axis or a cylinder")
        res.append(_dot(pl["n"], ax["n"]))           # the axis parallel to the plane
        nd = 1
        if t != "parallel":                          # coincident: the axis in the plane; distance: at the distance
            res.append(_dot(_sub(ax.get("p") or ax["c"], pl["c"]), pl["n"]) - (val if t == "distance" else 0.0))
        return res, nd
    if t in ("coincident", "distance", "parallel", "angle"):
        if na is None or nb is None:
            raise ValueError("mate needs planar or cylindrical faces")
        if t == "angle":
            ang = math.radians(val)
            res.append(_dot(na, nb) - sgn * math.cos(ang))
        else:
            # normals anti-parallel (coincident/distance: facing) or parallel (flip): na = target
            target = [-sgn * x for x in nb]
            res += [na[i] - target[i] for i in range(3)]
        nd = len(res)
        if t in ("coincident", "distance"):
            pa = A.get("p") or A["c"]
            pb = B.get("p") or B["c"]
            res.append(_dot(_sub(pb, pa), na) - val)
    elif t == "concentric":
        if A.get("kind") not in line or B.get("kind") not in line:
            raise ValueError("concentric needs two cylindrical faces or axes")
        # axes opposite (default, as the facing of the planar mates) or the same direction (Flip): the direction
        # is part of the mate, so Flip turns the component end for end
        target = [-sgn * x for x in nb]
        u, v = _perp_basis(target)
        res += [na[i] - target[i] for i in range(3)]
        nd = 3
        d = _sub(B["p"], A["p"])
        res.append(_dot(d, u))
        res.append(_dot(d, v))
    elif t == "point":
        res += _sub(B["c"], A["c"])
        nd = 0
    else:
        raise ValueError("unknown mate type %s" % t)
    return res, nd


def _solve_core(asm, refs_of, datums_of=None, detail=None, drag=None, summary=True):
    """Gauss-Newton solve of the mates. refs_of(comp id) -> list of face refs (local). Fixed components and
    components without mates keep their placement; in a group of mated components without a fixed one, the first
    component of the group in the component list keeps its placement. Returns ({comp id: (pos, rot)}, max residual, messages).
    detail (dict): gets "unsatisfied" {mate id: error text} of the mates above TOL_MM or TOL_DEG.
    drag {"comp", "delta": [dx, dy, dz], "grab": [x, y, z], "skip": [mate ids left out by the last solve]} or
    {"comp", "pos", "rot", "skip"} (a target placement): the
    grabbed point (world; default: the reference centre) is pulled by delta (mm), or the component towards the
    placement, as far as the mates allow ("limit": time limit of the pull, s, default 1.5); the
    other components that are not fixed follow (the group of the dragged component holds no component in place
    unless one is fixed). Then the mates are solved without the pull."""
    comps = {c["id"]: c for c in asm.get("components") or []}
    msgs = []
    mates = []
    for m in asm.get("mates") or []:
        if m.get("suppressed"):
            continue
        a, b = m.get("a") or {}, m.get("b") or {}
        name = m.get("name") or m.get("type") or m.get("id")
        if not a.get("comp") or not b.get("comp"):
            msgs.append("mate %s skipped: a face is not picked" % name)
        elif a["comp"] not in comps or b["comp"] not in comps:
            msgs.append("mate %s skipped: its component was deleted" % name)
        elif (a.get("face") is None and not a.get("datum")) or (b.get("face") is None and not b.get("datum")):
            msgs.append("mate %s skipped: a face is not picked" % name)
        else:
            mates.append(m)
    # each group of components connected by mates keeps one component in place: a fixed one, else the first of
    # the group in the component list (the solve does not move the whole group in space)
    order = [c["id"] for c in asm.get("components") or []]
    link = {}
    for m in mates:
        a, b = m["a"]["comp"], m["b"]["comp"]
        link.setdefault(a, set()).add(b)
        link.setdefault(b, set()).add(a)
    held, seen = set(), set()
    for cid in order:
        if cid not in link or cid in seen:
            continue
        group, todo = [], [cid]
        while todo:
            k = todo.pop()
            if k in seen:
                continue
            seen.add(k)
            group.append(k)
            todo += list(link.get(k, ()))
        if not any(comps[k].get("fixed") for k in group) and not (drag and drag.get("comp") in group):
            held.add(min(group, key=order.index))
    involved = []
    for m in mates:
        for side in ("a", "b"):
            cid = (m.get(side) or {}).get("comp")
            if cid in comps and not comps[cid].get("fixed") and cid not in held and cid not in involved:
                involved.append(cid)
    if not mates or not involved:
        return {}, 0.0, msgs
    # parameter vector: 6 per free component. The rotation pivots about the component's reference centre
    # (mean of its face centres) so that a rotation step does not move the component as a whole.
    def centre_local(cid):
        lst = [r for r in (refs_of(cid) or []) if r]
        if not lst:
            return [0.0, 0.0, 0.0]
        return [sum(r["c"][i] for r in lst) / len(lst) for i in range(3)]

    cl = {cid: centre_local(cid) for cid in involved}
    x = []
    for cid in involved:
        c = comps[cid]
        pos0 = [float(v or 0) for v in (c.get("pos") or [0, 0, 0])]
        rot0 = [float(v or 0) for v in (c.get("rot") or [0, 0, 0])]
        x += _apply(_rot_matrix(rot0), pos0, cl[cid]) + rot0
    idx = {cid: 6 * i for i, cid in enumerate(involved)}

    def params(cid, xv):
        if cid in idx:
            b = idx[cid]
            cw, rot = xv[b:b + 3], xv[b + 3:b + 6]
            rc = _apply(_rot_matrix(rot), [0, 0, 0], cl[cid], point=False)
            return (_sub(cw, rc), rot)
        c = comps[cid]
        return ([float(v or 0) for v in (c.get("pos") or [0, 0, 0])], [float(v or 0) for v in (c.get("rot") or [0, 0, 0])])

    def ref(side, xv):
        cid, fi = side.get("comp"), side.get("face")
        if side.get("datum"):
            d = (datums_of(cid) if datums_of else None) or {}
            if side["datum"] not in d:
                raise ValueError("reference %s lost" % side["datum"])
            return _placed_ref(d[side["datum"]], params(cid, xv))
        lst = refs_of(cid)
        if lst is None or fi is None or fi >= len(lst) or lst[fi] is None:
            raise ValueError("face reference lost")
        return _placed_ref(lst[fi], params(cid, xv))

    # Jacobian by central differences, column by column; a parameter of a component changes only the residuals of
    # the mates of that component, so only those are evaluated (sparse). Linear algebra with numpy.
    mates_of = {cid: [k for k, m in enumerate(mates) if cid in ((m.get("a") or {}).get("comp"), (m.get("b") or {}).get("comp"))]
                for cid in involved}

    def block(k, xv):
        m = mates[k]
        try:
            return _residuals(m, ref(m["a"], xv), ref(m["b"], xv))
        except ValueError as e:
            m["_error"] = str(e)
            return []

    def solve(pull=None):
        """Gauss-Newton with minimum-norm steps. pull (b, target, w): extra residuals w (x[b:b+3] - target) that
        draw the centre of a component towards target; the step is then accepted on the sum of squares."""
        import numpy as np
        nonlocal x
        blocks = [block(k, x) for k in range(len(mates))]
        off, m = [], 0
        for b in blocks:
            off.append(m)
            m += len(b)
        if not m:
            return 0.0
        Rt = pull[3] if pull else None
        mm = m + (3 if pull else 0) + (9 if Rt is not None else 0)

        def pull_rows(xv):
            pb, tg, w, _r, gl, pcid = pull
            if gl is not None:                         # the grabbed point of the component
                pos, rot = params(pcid, xv)
                q = _apply(_rot_matrix(rot), pos, gl)
                v = [w * (q[i] - tg[i]) for i in range(3)]
            else:
                v = [w * (xv[pb + i] - tg[i]) for i in range(3)]
            if Rt is not None:                         # orientation: rotation matrix entries, 1 like 100 mm
                R = _rot_matrix(xv[pb + 3:pb + 6])
                v += [w * 100.0 * (R[i][j] - Rt[i][j]) for i in range(3) for j in range(3)]
            return v

        def rvec(bl, xv):
            v = [q for b in bl for q in b]
            if pull:
                v += pull_rows(xv)
            return np.array(v, dtype=float)

        measure = (lambda rr: float(rr @ rr)) if pull else (lambda rr: float(np.max(np.abs(rr))))
        r = rvec(blocks, x)
        nr = measure(r)
        n = len(x)
        mu = 1e-6
        import time as _time
        t_end = _time.time() + max(0.05, min(5.0, float((drag or {}).get("limit") or 1.5)))   # time limit of a pull
        stall = 0
        for it in range(80):
            if nr < (1e-18 if pull else 1e-7) or (pull and _time.time() > t_end):
                break
            # imported models are rarely exact (a bore 0.001 rad off its slide): the residual stops at a small
            # floor; the solve ends when it no longer improves (2 % in 4 iterations) instead of running on
            if stall >= 4 and (pull or nr < 1e-4) or stall >= 8:
                break                                  # (8: a solve that cannot satisfy its mates)
            nr_prev = nr
            J = np.zeros((mm, n))
            if pull:
                for j in range(pull[0], pull[0] + 6):
                    xp, xq = list(x), list(x)
                    xp[j] += 1e-5
                    xq[j] -= 1e-5
                    J[m:mm, j] = (np.array(pull_rows(xp)) - np.array(pull_rows(xq))) / 2e-5
            for cid in involved:
                b0 = idx[cid]
                for j in range(b0, b0 + 6):
                    h = 1e-6 * max(1.0, abs(x[j]))
                    xp, xm = list(x), list(x)
                    xp[j] += h
                    xm[j] -= h
                    for k in mates_of[cid]:
                        L = len(blocks[k])
                        if not L:
                            continue
                        rp, rm = block(k, xp), block(k, xm)
                        if len(rp) == L and len(rm) == L:
                            J[off[k]:off[k] + L, j] = (np.array(rp) - np.array(rm)) / (2 * h)
            JJ = J @ J.T
            improved = False
            if pull:                                  # least squares, minimum norm, step halved until it improves
                # rotations cost more than translations in the minimum norm (1 deg like 100 mm): a pulled chain
                # translates and turns only where its mates need it
                S = np.array([1.0 if j % 6 < 3 else 0.01 for j in range(n)])
                d0 = S * np.linalg.lstsq(J * S, -r, rcond=1e-10)[0]
                for tries in range(8):
                    xn = [a + float(b) for a, b in zip(x, d0 * 0.5 ** tries)]
                    bn = [block(k, xn) for k in range(len(mates))]
                    if max([abs(q) for b in bn for q in b] or [0.0]) > 1e-9:
                        saved, x = x, xn             # the mates solved again from the step (curved motions)
                        solve()
                        xn, x = x, saved
                        bn = [block(k, xn) for k in range(len(mates))]
                    if [len(b) for b in bn] != [len(b) for b in blocks]:
                        continue
                    rn = rvec(bn, xn)
                    nn = measure(rn)
                    if nn < nr * (1 - 1e-12):
                        x, r, nr, blocks = xn, rn, nn, bn
                        improved = True
                        break
                if not improved:
                    break
                stall = stall + 1 if nr > 0.98 * nr_prev else 0
                continue
            for tries in range(8):
                # minimum-norm step: dx = J^T (J J^T + mu (1 + diag)) ^-1 (-r)
                A = JJ + np.diag(mu * (1.0 + np.diag(JJ)))
                try:
                    y = np.linalg.solve(A, -r)
                except np.linalg.LinAlgError:
                    mu *= 10
                    continue
                xn = [a + float(b) for a, b in zip(x, J.T @ y)]
                bn = [block(k, xn) for k in range(len(mates))]
                if [len(b) for b in bn] != [len(b) for b in blocks]:
                    mu *= 10
                    continue
                rn = rvec(bn, xn)
                nn = measure(rn)
                if nn < nr * (1 - 1e-12):
                    x, r, nr, blocks = xn, rn, nn, bn
                    mu = max(mu / 10, 1e-12)
                    improved = True
                    break
                mu *= 10
            stall = stall + 1 if improved and nr > 0.98 * nr_prev else 0
            if not improved:
                break
        return float(np.max(np.abs(np.array([v for b in blocks for v in b], dtype=float)))) if pull else nr

    # a facing mate whose normals point the same way (or the reverse for Flip) is a stationary point of the
    # least-squares problem: turn the free component by 180 deg about its reference centre first
    for m in mates:
        if m.get("type") not in ("coincident", "distance", "parallel", "concentric"):
            continue
        try:
            A_, B_ = ref(m["a"], x), ref(m["b"], x)
        except ValueError:
            continue
        if "plane" in (A_.get("kind"), B_.get("kind")) and "axis" in (A_.get("kind"), B_.get("kind")):
            continue                                 # a plane with an axis has no direction
        sgn = -1.0 if m.get("flip") else 1.0
        if _dot(A_["n"], B_["n"]) * sgn < 0.3:
            continue
        cid = m["a"]["comp"] if m["a"]["comp"] in idx else (m["b"]["comp"] if m["b"]["comp"] in idx else None)
        if cid is None:
            continue
        n = A_["n"] if cid == m["a"]["comp"] else B_["n"]
        u, _v = _perp_basis(n)
        b = idx[cid]
        R = _mm(_axis_rot(u, math.pi), _rot_matrix(x[b + 3:b + 6]))
        x[b + 3:b + 6] = _euler_of(R)

    if drag and drag.get("comp") in idx:
        dc = drag["comp"]
        b = idx[dc]
        if drag.get("rot") is not None:              # a target placement (rotation drag)
            Rt = _rot_matrix([float(v or 0) for v in drag["rot"]])
            ctr = _apply(Rt, [float(v or 0) for v in drag.get("pos") or [0, 0, 0]], cl[dc])
            solve((b, ctr, 1e-5, Rt, None, dc))
        else:
            dl = [float(v or 0) for v in (drag.get("delta") or [0, 0, 0])][:3]
            g = drag.get("grab")
            if g is not None:                        # the grabbed point (world) follows the cursor: a part that can
                pos0, rot0 = params(dc, x)           # only turn turns like a lever
                R0 = _rot_matrix(rot0)
                d0 = [float(g[i]) - pos0[i] for i in range(3)]
                gl = [sum(R0[k][i] * d0[k] for k in range(3)) for i in range(3)]
                solve((b, [float(g[i]) + dl[i] for i in range(3)], 1e-5, None, gl, dc))
            else:
                solve((b, [x[b + i] + dl[i] for i in range(3)], 1e-5, None, None, dc))
    nr = solve()
    out = {}
    for cid in involved:
        pos, rot = params(cid, x)
        out[cid] = ([round(v, 6) for v in pos], [round(((v + 180) % 360) - 180, 6) for v in rot])
    bad = {}
    for m in mates:
        if m.get("_error"):
            msgs.append("%s: %s" % (m.get("name") or m.get("id"), m.pop("_error")))
            continue
        try:
            dmm, ddeg = mate_error(m, ref(m["a"], x), ref(m["b"], x))
        except ValueError:
            continue
        err = (["%.3g mm" % dmm] if dmm > TOL_MM else []) + (["%.2g deg" % ddeg] if ddeg > TOL_DEG else [])
        if err:
            bad[m.get("id")] = (dmm / TOL_MM + ddeg / TOL_DEG, "%s / %s %s %s" % (
                comps[m["a"]["comp"]].get("name") or m["a"]["comp"], comps[m["b"]["comp"]].get("name") or m["b"]["comp"],
                m.get("name") or m.get("type"), ", ".join(err)))
    if bad and summary:
        msgs.append(_bad_text(bad))
    if detail is not None:
        detail["unsatisfied"] = {k: v[1] for k, v in bad.items()}
        detail["_bad"] = bad
    return out, nr, msgs


def _bad_text(bad):
    worst = sorted(bad.values(), key=lambda v: -v[0])
    return "%d mate%s not satisfied: %s%s" % (len(bad), "" if len(bad) == 1 else "s", "; ".join(v[1] for v in worst[:3]),
                                              "; %d more marked in the mates list" % (len(bad) - 3) if len(bad) > 3 else "")


def _valid_mates(asm, msgs):
    """Active mates with both sides picked on existing components; the others are named in msgs."""
    comps = {c["id"] for c in asm.get("components") or []}
    out = []
    for m in asm.get("mates") or []:
        if m.get("suppressed"):
            continue
        a, b = m.get("a") or {}, m.get("b") or {}
        name = m.get("name") or m.get("type") or m.get("id")
        if not a.get("comp") or not b.get("comp"):
            msgs.append("mate %s skipped: a face is not picked" % name)
        elif a["comp"] not in comps or b["comp"] not in comps:
            msgs.append("mate %s skipped: its component was deleted" % name)
        elif (a.get("face") is None and not a.get("datum")) or (b.get("face") is None and not b.get("datum")):
            msgs.append("mate %s skipped: a face is not picked" % name)
        else:
            out.append(m)
    return out


def _mate_groups(comp_ids, mates):
    """Groups of components connected by mates: [(component ids, mates)], in the order of the component list."""
    link = {}
    for m in mates:
        a, b = m["a"]["comp"], m["b"]["comp"]
        link.setdefault(a, set()).add(b)
        link.setdefault(b, set()).add(a)
    seen, groups = set(), []
    for cid in comp_ids:
        if cid not in link or cid in seen:
            continue
        g, todo = set(), [cid]
        while todo:
            k = todo.pop()
            if k in seen:
                continue
            seen.add(k)
            g.add(k)
            todo += list(link.get(k, ()))
        groups.append(([c for c in comp_ids if c in g], [m for m in mates if m["a"]["comp"] in g]))
    return groups


def _mate_order(cids, mates, comps):
    """Mates in the order a chain is built: from the fixed components (else the first component) outwards, in the
    order of the mate list among the mates that reach the components placed so far."""
    placed = {c for c in cids if comps[c].get("fixed")} or {cids[0]}
    left, out = list(mates), []
    while left:
        nxt = next((m for m in left if m["a"]["comp"] in placed or m["b"]["comp"] in placed), left[0])
        left.remove(nxt)
        out.append(nxt)
        placed.update((nxt["a"]["comp"], nxt["b"]["comp"]))
    return out


def solve_mates(asm, refs_of, datums_of=None, detail=None, drag=None):
    """Solves the mates group by group (components connected by mates); a group is independent of the others.
    When the mates of a group cannot all be satisfied, the group is solved again from its starting placement adding
    one mate at a time (from the fixed components outwards): a mate that cannot be satisfied together with the mates
    before it is tried with Flip changed (kept flipped when that works: detail "flipped"), else left out (a conflict)
    and the other mates are satisfied, so one bad mate does not scatter the group.
    Returns ({comp id: (pos, rot)}, max residual, messages). detail gets "unsatisfied" {mate id: text} and "conflicts"
    {mate id: text}; drag as in _solve_core (with conflicts: applied with the mates that are kept)."""
    msgs = []
    mates = _valid_mates(asm, msgs)
    comps = {c["id"]: c for c in asm.get("components") or []}
    order = [c["id"] for c in asm.get("components") or []]
    out, nr, bad, conflicts, flipped = {}, 0.0, {}, {}, []
    skip = set((drag or {}).get("skip") or [])           # a drag: the mates the last solve left out
    if skip:
        conflicts.update({m.get("id"): "left out by the last solve" for m in mates if m.get("id") in skip})
        mates = [m for m in mates if m.get("id") not in skip]
    for cids, gm in _mate_groups(order, mates):
        sub = {"components": [comps[c] for c in cids], "mates": gm}
        det = {}
        g_drag = drag if drag and drag.get("comp") in cids else None
        o, r, ms = _solve_core(sub, refs_of, datums_of, det, drag=g_drag, summary=False)
        gb = det.get("_bad") or {}
        if gb:
            # first: the newest mate and the mates with the largest errors, each tried flipped and then left out in
            # a solve of the whole group (a few solves instead of one per mate)
            cand = [gm[-1].get("id")] + [k for k, _v in sorted(gb.items(), key=lambda kv: -kv[1][0])]
            byid = {m.get("id"): m for m in gm}
            seen = []
            for mid in cand:
                if mid not in seen and mid in byid and len(seen) < 3:
                    seen.append(mid)
            for mid in seen:
                m0 = byid[mid]
                trials = ([("flip", [dict(m, flip=not m.get("flip")) if m.get("id") == mid else m for m in gm])] if m0.get("type") in FLIPPABLE else []) + \
                    [("out", [m for m in gm if m.get("id") != mid])]
                done = False
                for how, gm2 in trials:
                    det2 = {}
                    o2, r2, ms2 = _solve_core({"components": sub["components"], "mates": gm2}, refs_of, datums_of, det2, drag=g_drag, summary=False)
                    if not det2.get("_bad"):
                        o, r, ms, gb = o2, r2, ms2, {}
                        if how == "flip":
                            flipped.append(mid)
                        else:
                            conflicts[mid] = "%s / %s %s" % (comps[m0["a"]["comp"]].get("name") or m0["a"]["comp"], comps[m0["b"]["comp"]].get("name") or m0["b"]["comp"],
                                                             m0.get("name") or m0.get("type"))
                        done = True
                        break
                if done:
                    break
        if gb:
            kept = []
            o, r, ms, gb, cf = _solve_incremental(cids, gm, comps, refs_of, datums_of, flipped, kept)
            conflicts.update(cf)
            if g_drag and kept:                        # the drag with the mates that are kept
                cur = [dict(comps[c], pos=o[c][0], rot=o[c][1]) if c in o else comps[c] for c in cids]
                o3, r3, ms3 = _solve_core({"components": cur, "mates": kept}, refs_of, datums_of, {}, drag=g_drag, summary=False)
                o = dict(o, **o3)
                r = r3
        out.update(o)
        nr = max(nr, r)
        msgs += ms
        bad.update(gb)
    if conflicts:
        names = list(conflicts.values())
        msgs.append("%d mate%s left out (conflict with the mates solved before %s): %s%s" % (
            len(conflicts), "" if len(conflicts) == 1 else "s", "it" if len(conflicts) == 1 else "them", "; ".join(names[:3]),
            "; %d more marked in the mates list" % (len(names) - 3) if len(names) > 3 else ""))
    if bad:
        msgs.append(_bad_text(bad))
    if flipped:
        nm = {m.get("id"): "%s / %s %s" % (comps[m["a"]["comp"]].get("name") or m["a"]["comp"], comps[m["b"]["comp"]].get("name") or m["b"]["comp"],
                                           m.get("name") or m.get("type")) for m in mates}
        msgs.append("%d mate%s flipped (could not be satisfied the other way): %s" % (
            len(flipped), "" if len(flipped) == 1 else "s", "; ".join(nm.get(i, i) for i in flipped[:3])))
    if detail is not None:
        detail["flipped"] = flipped
        detail["unsatisfied"] = {k: v[1] for k, v in bad.items()}
        detail["unsatisfied"].update({k: "conflict, left out: " + v for k, v in conflicts.items()})
        detail["conflicts"] = conflicts
    return out, nr, msgs


FLIPPABLE = ("coincident", "distance", "parallel", "concentric")


def _solve_incremental(cids, gm, comps, refs_of, datums_of, flipped=None, kept_out=None):
    """Group solve one mate at a time from the starting placement; returns (placements, residual, messages,
    unsatisfied of the kept mates, {mate id: text} of the mates left out). A mate that cannot be satisfied with the
    mates before it is tried once more with Flip changed; when that works it is kept flipped and its id is added to
    flipped (list)."""
    cur = {c: dict(comps[c]) for c in cids}
    kept, conflicts, out, nr, msgs = [], {}, {}, 0.0, []
    name = lambda c: comps[c].get("name") or c
    for m in _mate_order(cids, gm, comps):
        tries = [m] + ([dict(m, flip=not m.get("flip"))] if m.get("type") in FLIPPABLE else [])
        for k, mm in enumerate(tries):
            det = {}
            o, r, ms = _solve_core({"components": [cur[c] for c in cids], "mates": kept + [mm]}, refs_of, datums_of, det, summary=False)
            if not (det.get("_bad") or ms):
                break
        else:
            msgs += [x for x in ms if x not in msgs]
            if ms and not det.get("_bad"):
                continue                               # a lost reference: skipped (named in msgs), not a conflict
            conflicts[m.get("id")] = "%s / %s %s" % (name(m["a"]["comp"]), name(m["b"]["comp"]), m.get("name") or m.get("type"))
            continue
        if k == 1 and flipped is not None:
            flipped.append(m.get("id"))
        kept = kept + [mm]
        for cid, (pos, rot) in o.items():
            cur[cid] = dict(cur[cid], pos=pos, rot=rot)
            out[cid] = (pos, rot)
        nr = r
    if kept_out is not None:
        kept_out.extend(kept)
    return out, nr, msgs, {}, conflicts


def mate_report(asm, refs_of, datums_of=None):
    """Mate check of an assembly: solves the mates (conflicting mates left out), then per mate its state and the
    number of conditions it adds, and per component the motions its mates leave free with the other components
    held. Returns {"placements": {id: {"pos", "rot"}}, "mates": {id: {"status", "text", "adds"}},
    "components": {id: {"status", "free_t", "free_r", "text"}}, "summary", "messages"}.
    Mate status: "ok", "redundant" (adds no condition to the mates before it), "not satisfied", "conflict" (left out),
    "skipped" (a side not picked or lost). Conditions are counted from the rank of the Jacobian of the residuals
    (central differences: 1e-4 mm, 1e-4 deg)."""
    import numpy as np
    det = {}
    out, nr, msgs = solve_mates(asm, refs_of, datums_of, det)
    comps = {c["id"]: dict(c) for c in asm.get("components") or []}
    for cid, (pos, rot) in out.items():
        comps[cid]["pos"], comps[cid]["rot"] = pos, rot
    fl = set(det.get("flipped") or [])
    valid = [dict(m, flip=not m.get("flip")) if m.get("id") in fl else m for m in _valid_mates(asm, [])]
    vids = {m.get("id") for m in valid}
    conflicts = det.get("conflicts") or {}
    unsat = det.get("unsatisfied") or {}
    kept = [m for m in valid if m.get("id") not in conflicts]

    def P(cid):
        c = comps[cid]
        return ([float(v or 0) for v in (c.get("pos") or [0, 0, 0])], [float(v or 0) for v in (c.get("rot") or [0, 0, 0])])

    def ref(side, params):
        cid = side["comp"]
        if side.get("datum"):
            d = (datums_of(cid) if datums_of else None) or {}
            return _placed_ref(d[side["datum"]], params)
        return _placed_ref(refs_of(cid)[side["face"]], params)

    def resid(m, override=None):
        pa = override[1] if override and override[0] == m["a"]["comp"] else P(m["a"]["comp"])
        pb = override[1] if override and override[0] == m["b"]["comp"] else P(m["b"]["comp"])
        return _residuals(m, ref(m["a"], pa), ref(m["b"], pb))

    free = [cid for cid in comps if not comps[cid].get("fixed") and any(cid in (m["a"]["comp"], m["b"]["comp"]) for m in kept)]
    col = {cid: 6 * i for i, cid in enumerate(free)}
    rows, owner = [], []
    for m in kept:
        try:
            r0 = resid(m)
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        blk = np.zeros((len(r0), 6 * len(free)))
        for cid in {m["a"]["comp"], m["b"]["comp"]}:
            if cid not in col:
                continue
            pos, rot = P(cid)
            for j in range(6):
                h = 1e-4
                pp = (list(pos), list(rot))
                pm = (list(pos), list(rot))
                if j < 3:
                    pp[0][j] += h
                    pm[0][j] -= h
                    scale = 1.0
                else:
                    pp[1][j - 3] += h
                    pm[1][j - 3] -= h
                    scale = 180.0 / math.pi        # per radian
                d = (np.array(resid(m, (cid, pp))) - np.array(resid(m, (cid, pm)))) / (2 * h) * scale
                blk[:, col[cid] + j] = d
        rows.append(blk)
        owner.append(m.get("id"))
    rank = lambda A: int(np.linalg.matrix_rank(A, tol=1e-6)) if A.size else 0
    rep_m = {}
    # conditions added by each mate over the mates before it (in the list order)
    acc = np.zeros((0, 6 * len(free)))
    for mid, blk in zip(owner, rows):
        r_before = rank(acc)
        acc = np.vstack([acc, blk])
        rep_m[mid] = rank(acc) - r_before
    for m in asm.get("mates") or []:
        mid = m.get("id")
        name = m.get("name") or m.get("type")
        if m.get("suppressed"):
            rep_m[mid] = {"status": "suppressed", "text": "suppressed", "adds": 0}
        elif mid not in vids:
            rep_m[mid] = {"status": "skipped", "text": "a side is not picked or its component was deleted", "adds": 0}
        elif mid in conflicts:
            rep_m[mid] = {"status": "conflict", "text": "conflicts with the mates solved before it; left out of the solve", "adds": 0}
        elif mid in unsat:
            rep_m[mid] = {"status": "not satisfied", "text": unsat[mid], "adds": rep_m.get(mid, 0) if isinstance(rep_m.get(mid), int) else 0}
        elif isinstance(rep_m.get(mid), int):
            k = rep_m[mid]
            rep_m[mid] = {"status": "ok" if k else "redundant",
                          "text": ("adds %d condition%s" % (k, "" if k == 1 else "s")) if k else "adds no condition to the mates before it (redundant)",
                          "adds": k}
        else:
            rep_m[mid] = {"status": "skipped", "text": "reference lost", "adds": 0}
        rep_m[mid]["name"] = name
    J = np.vstack(rows) if rows else np.zeros((0, 6 * len(free)))
    rep_c = {}
    for cid, c in comps.items():
        if c.get("fixed"):
            rep_c[cid] = {"status": "fixed", "free_t": 0, "free_r": 0, "text": "fixed"}
            continue
        if cid not in col:
            rep_c[cid] = {"status": "no mates", "free_t": 3, "free_r": 3, "text": "no mates"}
            continue
        Jc = J[:, col[cid]:col[cid] + 6]
        rt = rank(Jc[:, :3])
        ra = rank(Jc)
        ft, fr = 3 - rt, max(0, 6 - ra - (3 - rt))
        txt = "held" if ft == 0 and fr == 0 else "free: %s" % ", ".join(
            x for x in (("%d translation%s" % (ft, "" if ft == 1 else "s")) if ft else "",
                        ("%d rotation%s" % (fr, "" if fr == 1 else "s")) if fr else "") if x)
        rep_c[cid] = {"status": "held" if txt == "held" else "free", "free_t": ft, "free_r": fr, "text": txt + " (other components held)"}
    nc = sum(1 for v in rep_m.values() if v["status"] == "conflict")
    nb = sum(1 for v in rep_m.values() if v["status"] == "not satisfied")
    nrd = sum(1 for v in rep_m.values() if v["status"] == "redundant")
    nsk = sum(1 for v in rep_m.values() if v["status"] == "skipped")
    nsup = sum(1 for v in rep_m.values() if v["status"] == "suppressed")
    nfree = sum(1 for v in rep_c.values() if v["status"] == "free")
    dof = 6 * len(free) - rank(J)
    summary = "%d mates: %d conflict%s, %d not satisfied, %d redundant, %d skipped, %d suppressed. %d component%s with free motion; %d degree%s of freedom in all" % (
        len(asm.get("mates") or []), nc, "" if nc == 1 else "s", nb, nrd, nsk, nsup, nfree, "" if nfree == 1 else "s", dof, "" if dof == 1 else "s")
    return {"placements": {k: {"pos": v[0], "rot": v[1]} for k, v in out.items()}, "mates": rep_m, "components": rep_c,
            "summary": summary, "messages": msgs, "unsatisfied": unsat, "dof": dof, "flipped": sorted(fl)}
