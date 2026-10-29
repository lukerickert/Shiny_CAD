# -*- coding: utf-8 -*-
"""Local web server of SHINYCAD."""
import hashlib
import io
import json
import sys
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
import zipfile

import numpy as np

from flask import Flask, jsonify, request, send_file, send_from_directory

from . import analysis, assembly, cam, dialogs, drawing, fcstd, fea, fits, measure, model, part, render, sketch, sketchimage, units
from . import titleblock as tbk

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.environ.get("DRAWGEN_CONFIG") or os.path.join(APP_DIR, "config.json")   # DRAWGEN_CONFIG: tests
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
WORK_DIR = tempfile.mkdtemp(prefix="drawgen_")
STEP_EXT = (".step", ".stp")
DXF_EXT = (".dxf",)


class _Dir(object):
    """Path of a document folder of the open project (projects.py), evaluated when used."""
    def __init__(self, attr):
        self.attr = attr

    def __fspath__(self):
        return getattr(PROJECTS.dirs(), self.attr)

    def __str__(self):
        return self.__fspath__()


ANN_DIR = _Dir("annotations")
SKETCH_DIR = _Dir("sketches")
PART_DIR = _Dir("parts")
ASM_DIR = _Dir("assemblies")
FEA_DIR = _Dir("analysis")

app = Flask(__name__, static_folder=None)
app.json.sort_keys = False
FILES = {}          # file id -> {"name", "path", "source", "parts": [Part]}
CACHE = {}          # projection cache
LOCK = threading.Lock()


# --------------------------------------------------------------------------- helpers

# settings of this PC: config.local.json next to config.json (not in the repository); the other settings (sheet, views,
# title block, options) stay in config.json
LOCAL_PATH = os.path.splitext(CONFIG_PATH)[0] + ".local.json"
LOCAL_KEYS = ("projects_root", "current_project", "explicit", "browser", "ccx_path", "recent_roots", "known_projects",
              "part_last")


def load_config():
    """config.json with the settings of this PC from config.local.json."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    try:
        with open(LOCAL_PATH, "r", encoding="utf-8") as f:
            loc = json.load(f)
    except (OSError, ValueError):
        loc = {}
    cfg.update({k: v for k, v in loc.items() if k in LOCAL_KEYS})
    return cfg


def _tmp_ext():
    """Suffix of a temporary file, unique per process and thread (requests run in parallel threads)."""
    return ".%d.%d.tmp" % (os.getpid(), threading.get_ident())


def _replace(tmp, path):
    """os.replace with retries: on Windows a replace fails while another request replaces the same file."""
    for i in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 19:
                raise
            time.sleep(0.05)


def save_config(cfg):
    """Writes the settings of this PC (LOCAL_KEYS) to config.local.json and the others to config.json."""
    for path, part in ((CONFIG_PATH, {k: v for k, v in cfg.items() if k not in LOCAL_KEYS}),
                       (LOCAL_PATH, {k: cfg[k] for k in LOCAL_KEYS if k in cfg})):
        tmp = path + _tmp_ext()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(part, f, indent=2)
        _replace(tmp, path)


def _split_config():
    """Moves settings of this PC that an older version wrote to config.json into config.local.json."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return
    if any(k in raw for k in LOCAL_KEYS):
        save_config(load_config() if os.path.isfile(LOCAL_PATH) else raw)


_split_config()


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_\-.]+", "_", s).strip("_") or "drawing"


from . import projects as _projects
PROJECTS = _projects.Projects(APP_DIR, load_config, save_config)


def error(msg, code=400):
    return jsonify({"error": msg}), code


def _register(path, source=None):
    parts = model.load_step(path)
    fid = uuid.uuid4().hex[:10]
    name = os.path.basename(source or path)
    with LOCK:
        FILES[fid] = {"name": name, "path": path, "source": source, "parts": parts}
    return _file_info(fid)


def effective_config(req):
    """Saved configuration with the request's sheet, scale, view and field settings applied."""
    cfg = load_config()
    st = req.get("settings") or {}
    for k in ("sheet", "scale", "mode"):
        if st.get(k):
            cfg[k] = st[k]
    for k, v in (st.get("views") or {}).items():
        cfg["views"][k] = v
    if "density_kg_per_m3" in st:
        cfg["density_kg_per_m3"] = float(st["density_kg_per_m3"] or 0)
    return cfg


def build_drawings(req):
    """Compose drawings for the request. Returns list of drawing dicts and the config used."""
    cfg = effective_config(req)
    fields = req.get("fields") or {}
    mode = cfg.get("mode", "per_part")
    out = []
    for sel in req.get("selection") or []:
        f = FILES.get(sel.get("file_id"))
        if f is None:
            continue
        ids = set(sel.get("part_ids") or [p.id for p in f["parts"]])
        parts = [p for p in f["parts"] if p.id in ids]
        if not parts:
            continue
        stem = os.path.splitext(f["name"])[0]
        if mode == "per_part":
            groups = [(("%s_%s" % (stem, p.name)) if len(f["parts"]) > 1 else stem, p.name, [p]) for p in parts]
        else:
            groups = [(stem, stem, parts)]
        for fname, title, group in groups:
            shape = model.compound([p.shape for p in group])
            vol = sum(p.volume for p in group)
            key = (sel["file_id"], tuple(p.id for p in group))
            fname = safe_name(fname)
            # annotations and layout are stored by file name; a part or assembly made in the program by its uid
            akey = f.get("ann_key") or fname
            # parts list of an assembly drawing: shown unless the drawing layout says otherwise ("parts_list": false;
            # default: the Parts list check box of the Assembly tab at Make drawing)
            pl_show = bool(load_layout(akey).get("parts_list", f.get("parts_list_default", True)))
            d = drawing.compose(title, shape, vol, cfg, cfg.get("sheet", "A3"),
                                drawing.parse_scale(cfg.get("scale", "auto")), fields,
                                cache=CACHE, key=key, base_dir=APP_DIR,
                                annotations=load_annotations(akey),
                                view_offsets=load_layout(akey).get("offsets"),
                                hidden_views=load_layout(akey).get("hidden"),
                                details=load_layout(akey).get("details"),
                                parts_list=f.get("parts_list") if mode != "per_part" and pl_show else None,
                                trails=f.get("trails") if mode != "per_part" else None,
                                holes=f.get("holes"), sketches=load_dsketches(akey),
                                skip_sketch=req.get("skip_sketch"))
            d["balloon_anchors"] = f.get("balloon_anchors") if mode != "per_part" else None
            d["has_parts_list"] = bool(f.get("parts_list")) and mode != "per_part"
            d["parts_list_shown"] = d["has_parts_list"] and pl_show
            d["holes"] = f.get("holes")
            d["selection"] = {"file_id": sel["file_id"], "part_ids": [p.id for p in group]}
            d["file_name"] = fname
            d["ann_name"] = akey
            d["shape"] = shape
            d["part_label"] = title
            d["source"] = f.get("source")
            out.append(d)
    return out, cfg


def _ann_path(name):
    return os.path.join(ANN_DIR, safe_name(name) + ".json")


def _layout_path(name):
    return os.path.join(ANN_DIR, safe_name(name) + ".layout.json")


def load_layout(name):
    try:
        with open(_layout_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _dsketch_path(name):
    return os.path.join(ANN_DIR, safe_name(name) + ".sketch.json")


def load_dsketches(name):
    """Sketches made on a drawing: {target: {"doc", "anns"}}, target "sheet" or a view name."""
    try:
        with open(_dsketch_path(name), "r", encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def load_annotations(name):
    try:
        with open(_ann_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


# --------------------------------------------------------------------------- routes

@app.route("/api/annotations/<name>", methods=["GET"])
def get_annotations(name):
    return jsonify(load_annotations(name))


@app.route("/api/annotations/<name>", methods=["PUT"])
def put_annotations(name):
    anns = request.get_json(force=True)
    if not isinstance(anns, list):
        return error("annotation list expected")
    os.makedirs(ANN_DIR, exist_ok=True)
    tmp = _ann_path(name) + _tmp_ext()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(anns, f, indent=1)
    _replace(tmp, _ann_path(name))
    return jsonify({"ok": True, "count": len(anns)})


@app.route("/api/drawing/sketch/<name>/<target>", methods=["PUT"])
def put_dsketch(name, target):
    """Stores the sketch made on a drawing for one target ("sheet" or a view name): {"doc", "anns"}; a sketch
    without entities, dimensions and notes is removed."""
    req = request.get_json(force=True) or {}
    doc = req.get("doc") or {}
    if not re.match(r"^(sheet|front|top|right|section|iso|detail_[A-Z])$", target):
        return error("invalid sketch target: %s" % target)
    sks = load_dsketches(name)
    if [e for e in doc.get("entities") or [] if not e.get("axis")] or doc.get("dims"):
        sks[target] = {"doc": doc, "anns": req.get("anns") or []}
    else:
        sks.pop(target, None)
    os.makedirs(ANN_DIR, exist_ok=True)
    path = _dsketch_path(name)
    if sks:
        tmp = path + _tmp_ext()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sks, f, indent=1)
        _replace(tmp, path)
    elif os.path.exists(path):
        os.remove(path)
    return jsonify({"ok": True, "targets": sorted(sks)})


@app.route("/api/drawing/sketch_base", methods=["POST"])
def dsketch_base():
    """Background and reference geometry for editing the sketch of a drawing: the drawing without that sketch
    (svg, size), the view map (null for the sheet), the reference edges and the stored sketch.
    Request: the preview request of the drawing plus "name" (drawing name) and "target"."""
    req = request.get_json(force=True) or {}
    target = req.get("target") or "sheet"
    req["skip_sketch"] = target
    try:
        ds, cfg = build_drawings(req)
    except Exception as e:
        traceback.print_exc()
        return error("drawing failed: %s" % e, 500)
    d = next((x for x in ds if x["file_name"] == req.get("name")), ds[0] if ds else None)
    if d is None:
        return error("drawing not found")
    maps = d["meta"]["maps"]
    if target != "sheet" and target not in maps:
        return error("the view %s is not on the drawing" % target)
    entry = load_dsketches(d["ann_name"]).get(target) or {}
    return jsonify({"svg": render.to_svg(d, cfg), "size": d["size"], "map": maps.get(target) if target != "sheet" else None,
                    "refs": drawing.sketch_refs(d, target), "doc": entry.get("doc"), "ann_name": d["ann_name"]})


@app.route("/api/layout/<name>", methods=["GET"])
def get_layout(name):
    return jsonify(load_layout(name))


@app.route("/api/layout/<name>", methods=["PUT"])
def put_layout(name):
    lay = request.get_json(force=True)
    if not isinstance(lay, dict):
        return error("layout object expected")
    os.makedirs(ANN_DIR, exist_ok=True)
    tmp = _layout_path(name) + _tmp_ext()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lay, f, indent=1)
    _replace(tmp, _layout_path(name))
    return jsonify({"ok": True})


@app.route("/api/balloons/<name>", methods=["POST"])
def auto_balloons(name):
    """Balloon annotations for an assembly drawing: one per component, anchored at the component centre
    projected onto the chosen view, placed outside the view."""
    req = request.get_json(force=True)
    anchors = req.get("anchors") or []
    view = req.get("view", "front")
    maps = req.get("maps") or {}
    if view not in maps or not anchors:
        return jsonify([])
    from . import project as pj
    d, xd = pj.VIEWS[view]
    cx, cy, f, bx, by, x0, y0, x1, y1 = maps[view]
    out = []
    cxv, cyv = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    margin = 18.0
    for i, a in enumerate(sorted(anchors, key=lambda q: q["item"])):
        vx, vy = pj.project_point(a["p"], d, xd)
        sx, sy = cx + f * (vx - bx), cy + f * (vy - by)
        # position: radially outward from the view centre to a rectangle around the view
        ux, uy = sx - cxv, sy - cyv
        if abs(ux) < 1e-9 and abs(uy) < 1e-9:
            ux, uy = 0.0, 1.0
        hw, hh = (x1 - x0) / 2.0 + margin, (y1 - y0) / 2.0 + margin
        k = min(hw / abs(ux) if abs(ux) > 1e-9 else 1e9, hh / abs(uy) if abs(uy) > 1e-9 else 1e9)
        px, py = cxv + ux * k, cyv + uy * k
        # back to view coordinates
        anchor = [bx + (sx - cx) / f, by + (sy - cy) / f]
        pos = [bx + (px - cx) / f, by + (py - cy) / f]
        out.append({"id": "b%d" % (i + 1), "type": "balloon", "view": view, "anchor": anchor, "pos": pos, "text": str(a["item"])})
    return jsonify(out)


@app.route("/api/hole_callouts/<name>", methods=["POST"])
def hole_callouts(name):
    """Note annotations for the holes of a part drawing: one per hole feature, anchored at the first hole of the
    feature in a view along the hole axis, placed outside the view."""
    req = request.get_json(force=True)
    holes = req.get("holes") or []
    maps = req.get("maps") or {}
    hidden = bool(((req.get("settings") or {}).get("views") or {}).get("hidden_lines", False))
    U = units.units_of(load_config())
    from . import project as pj
    out = []
    seen = set()
    for i, h in enumerate(holes):
        if h.get("feature") in seen:
            continue
        view = None
        external = h.get("kind") == "external"
        for n in ("front", "top", "right"):
            if n not in maps:
                continue
            d, _ = pj.VIEWS[n]
            dot = sum(h["d"][k] * d[k] for k in range(3))
            if external:
                if abs(dot) < 0.01:          # a view across the thread axis
                    view = n
                    break
            elif dot < -0.99 or (abs(dot) > 0.99 and (h.get("through") or hidden)):
                view = n
                break
        across = False
        if view is None and not external:
            # no view along the hole axis in the drawing: the note points at the hole opening in a view across the axis
            for n in ("front", "top", "right"):
                if n in maps and abs(sum(h["d"][k] * pj.VIEWS[n][0][k] for k in range(3))) < 0.01:
                    view, across = n, True
                    break
        if view is None:
            continue
        seen.add(h.get("feature"))
        d, xd = pj.VIEWS[view]
        cx, cy, f, bx, by, x0, y0, x1, y1 = maps[view]
        if external:
            # anchor on the outline at the middle of the thread length, on the side towards the top of the view
            L = float(h.get("depth") or 0)
            mid = [h["p"][k] + h["d"][k] * L / 2.0 for k in range(3)]
            vx, vy = pj.project_point(mid, d, xd)
            side = pj.project_point(h["d"], d, xd)
            ln = math.hypot(side[0], side[1]) or 1.0
            perp = (-side[1] / ln, side[0] / ln)
            if perp[1] < 0:
                perp = (-perp[0], -perp[1])
            R = float(h.get("dia") or 0) / 2.0
            sx, sy = cx + f * (vx + perp[0] * R - bx), cy + f * (vy + perp[1] * R - by)
            out.append([sy, i, view, (sx, sy, 0.0), part.callout_text(h, U), maps[view]])
            continue
        vx, vy = pj.project_point(h["p"], d, xd)
        sx, sy = cx + f * (vx - bx), cy + f * (vy - by)
        r = 0.0 if across else f * max(float(h.get("major") or 0), float(h.get("cbore_dia") or 0), float(h.get("dia") or 0)) / 2.0
        out.append([sy, i, view, (sx, sy, r), part.callout_text(h, U), maps[view]])
    # the notes are placed above the view in rows, the text ending above its hole, the leader rising from the
    # top of the hole circle; holes further right get higher rows so that the leaders do not cross the texts
    out.sort(key=lambda q: q[3][0])
    notes = []
    th = float(load_config().get("dim_text_height_mm", 3.5))
    row_y = 0.0
    for k, (sy, i, view, (sx, sy, r), text, mp) in enumerate(out):
        cx, cy, f, bx, by, x0, y0, x1, y1 = mp
        lines = text.split("\n")
        px, py = sx - 2.0 - 0.78 * th * max(len(t) for t in lines), y1 + 6.0 + row_y + (len(lines) - 1) * th * 1.6
        row_y += 6.0 + (len(lines) - 1) * th * 1.6
        ax, ay = sx, sy + r
        notes.append({"id": "h%d" % (i + 1), "type": "note", "view": view, "anchor": [bx + (ax - cx) / f, by + (ay - cy) / f],
                      "pos": [bx + (px - cx) / f, by + (py - cy) / f], "text": text})
    return jsonify(notes)


# --------------------------------------------------------------------------- projects

def _pj_error(fn):
    try:
        return fn()
    except (ValueError, OSError) as e:
        return error(str(e))


@app.route("/api/projects", methods=["GET"])
def projects_list():
    d = PROJECTS.dirs()
    return jsonify({"root": PROJECTS.root(), "current": PROJECTS.current_name(), "projects": PROJECTS.list_projects(),
                    "recent_roots": PROJECTS.recent_roots(), "known": PROJECTS.known(), "dirs": {"work": str(d.parts), "step": d.step, "drawings": d.drawings, "cam": d.cam}})


@app.route("/api/projects/root", methods=["PUT"])
def projects_root():
    req = request.get_json(force=True)
    path = (req.get("path") or "").strip().strip('"')
    if not path:
        return error("path required")
    try:
        if os.path.isfile(os.path.join(path, "project.json")):
            # a project folder: its parent becomes the projects folder and the project is opened
            PROJECTS.open_path(path)
            _clear_models()
        else:
            PROJECTS.set_root(path)
    except (OSError, ValueError) as e:
        return error("cannot use %s: %s" % (path, e))
    return projects_list()


@app.route("/api/projects", methods=["POST"])
def projects_create():
    req = request.get_json(force=True)
    def go():
        name = PROJECTS.create(req.get("name") or "", req.get("description") or "")
        if req.get("open", True):
            PROJECTS.open(name)
            _clear_models()
        return projects_list()
    return _pj_error(go)


@app.route("/api/projects/adopt", methods=["POST"])
def projects_adopt():
    """Creates a project from the parts, sketches, assemblies and stacks of the program folder (moved)."""
    req = request.get_json(force=True)
    def go():
        name, n = PROJECTS.adopt_legacy(req.get("name") or "legacy", move=req.get("move", True))
        PROJECTS.open(name)
        _clear_models()
        r = projects_list().get_json()
        r["moved"] = n
        return jsonify(r)
    return _pj_error(go)


@app.route("/api/projects/open", methods=["POST"])
def projects_open():
    req = request.get_json(force=True)
    def go():
        if req.get("path"):
            PROJECTS.open_path(req["path"])
        elif req.get("name"):
            PROJECTS.open(req["name"])
        else:
            PROJECTS.close()
        _clear_models()
        return projects_list()
    return _pj_error(go)


@app.route("/api/projects/scan", methods=["POST"])
def projects_scan():
    """Finds the projects in a folder and its subfolders and adds them to the list of known projects."""
    req = request.get_json(force=True)
    def go():
        found = PROJECTS.scan(req.get("folder") or "", int(req.get("depth") or 6))
        r = projects_list().get_json()
        r["found"] = found
        return jsonify(r)
    return _pj_error(go)


@app.route("/api/projects/forget", methods=["POST"])
def projects_forget():
    """Removes a project folder from the list of known projects (the folder is not changed)."""
    req = request.get_json(force=True)
    def go():
        PROJECTS.forget(req.get("path") or "")
        return projects_list()
    return _pj_error(go)


@app.route("/api/projects/<name>", methods=["PATCH"])
def projects_update(name):
    req = request.get_json(force=True)
    def go():
        if req.get("rename"):
            PROJECTS.rename_project(name, req["rename"])
            return projects_list()
        PROJECTS.update(name, description=req.get("description"))
        return projects_list()
    return _pj_error(go)


def _clear_models():
    with LOCK:
        FILES.clear()
        CACHE.clear()


@app.route("/api/project/docs", methods=["GET"])
def project_docs():
    if not PROJECTS.current_name():
        return jsonify({"project": {}, "docs": [], "exports": {"drawings": [], "step": [], "step_import": []}})
    def go():
        PROJECTS.sync(pack=False)
        return jsonify(PROJECTS.documents())
    return _pj_error(go)


# ------------------------------------------------------------------ document files (packages.py)
def sync_loop(interval=2.0):
    """Background thread of run.py: writes the document files of changed documents of the open project and reads
    document files changed outside the program."""
    while True:
        time.sleep(interval)
        try:
            if PROJECTS.current_name():
                r = PROJECTS.sync()
                if r["unpacked"] or r["deleted"]:
                    print("Document files read: %s" % ", ".join(r["unpacked"] + ["deleted " + k for k in r["deleted"]]))
        except Exception as e:  # noqa: BLE001 (the thread keeps running)
            print("Document files: %s" % e)


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def file_open(path):
    """Opens a document file (.scpart, .scasm, .scsketch, .scfea, .scexp). In a project folder: that project is
    opened. Elsewhere: the document is added to the open project and linked to the file (saves write it too).
    Returns {"type", "name", "project", "linked"}."""
    from . import packages
    path = os.path.abspath((path or "").strip().strip('"'))
    t = packages.pkg_type(path)
    if not t:
        raise ValueError("not a ShinyCAD document file: %s" % path)
    if not os.path.isfile(path):
        raise ValueError("file not found: %s" % path)
    packages.header(path)
    d = os.path.dirname(path)
    stem = safe_name(os.path.splitext(os.path.basename(path))[0])
    cur = PROJECTS.current_name()
    if os.path.isfile(os.path.join(d, "project.json")):
        if not cur or not _same(d, PROJECTS.project_dir(cur)):
            PROJECTS.open_path(d)
            _clear_models()
        PROJECTS.sync(force=True, pack=False)
        if not os.path.isfile(PROJECTS.doc_path(t, stem)):
            raise ValueError("%s could not be read" % path)
        return {"type": t, "name": stem, "project": PROJECTS.current_name(), "linked": ""}
    if not cur:
        raise ValueError("Open or create a project first: the document of %s is added to the open project and "
                         "stays linked to the file" % path)
    pdir = PROJECTS.project_dir(cur)
    for key, f in packages.linked(pdir).items():
        kt, kn = key.split(":", 1)
        if kt == t and _same(f, path) and os.path.isfile(PROJECTS.doc_path(t, kn)):
            PROJECTS.sync(force=True, pack=False)
            return {"type": t, "name": kn, "project": cur, "linked": path}
    name, k = stem, 1
    while os.path.exists(PROJECTS.doc_path(t, name)):
        k += 1
        name = "%s_%d" % (stem, k)
    with PROJECTS._sync_lock:
        packages.extract(PROJECTS, pdir, path, name)
        packages.link(pdir, t, name, path)
    PROJECTS.sync(force=True, only={t + ":" + name})
    return {"type": t, "name": name, "project": cur, "linked": path}


def file_save_as(dtype, dname, path):
    """Writes the document file of a document of the open project to path. In the open project folder: a copy of the
    document under the file name. In another project folder: the file only (read when that project is opened).
    Elsewhere: the document is linked to the file (saves write it too). Returns {"path", "name", "linked"}."""
    from . import packages
    if dtype not in packages.PKG_EXT:
        raise ValueError("unknown document type %s" % dtype)
    path = os.path.abspath((path or "").strip().strip('"'))
    if packages.pkg_type(path) != dtype:
        path = (os.path.splitext(path)[0] if packages.pkg_type(path) else path) + packages.PKG_EXT[dtype]
    cur = PROJECTS.current_name()
    if not cur:
        raise ValueError("no project is open")
    if not os.path.isfile(PROJECTS.doc_path(dtype, dname)):
        raise ValueError("%s %s is not saved in the project" % (dtype, dname))
    pdir = PROJECTS.project_dir(cur)
    d = os.path.dirname(path)
    stem = safe_name(os.path.splitext(os.path.basename(path))[0])
    if _same(d, pdir):
        if stem != safe_name(dname):
            PROJECTS.copy_doc(dtype, dname, stem)
        PROJECTS.sync(force=True, only={dtype + ":" + stem})
        return {"path": os.path.join(pdir, packages.pkg_name(stem, dtype)), "name": stem, "linked": ""}
    with PROJECTS._sync_lock:
        packages.write(PROJECTS, os.path.join(pdir, "work"), dtype, safe_name(dname), path)
        if os.path.isfile(os.path.join(d, "project.json")):
            return {"path": path, "name": dname, "linked": ""}
        packages.link(pdir, dtype, safe_name(dname), path)
    return {"path": path, "name": dname, "linked": path}


@app.route("/api/file/open", methods=["POST"])
def api_file_open():
    req = request.get_json(force=True)
    return _pj_error(lambda: jsonify(file_open(req.get("path") or "")))


@app.route("/api/file/saveas", methods=["POST"])
def api_file_save_as():
    req = request.get_json(force=True)
    return _pj_error(lambda: jsonify(file_save_as(req.get("type"), req.get("name") or "", req.get("path") or "")))


@app.route("/api/file/unlink", methods=["POST"])
def api_file_unlink():
    """Ends the link of a document to a file outside the project (the file is not changed)."""
    from . import packages
    req = request.get_json(force=True)
    def go():
        name, _ = PROJECTS._work()
        w = os.path.join(PROJECTS.project_dir(name), "work")
        with PROJECTS._sync_lock:
            st = packages.load_state(w)
            rec = st.get("%s:%s" % (req.get("type"), req.get("name")))
            if rec:
                rec.pop("file", None)
                rec.pop("link", None)
                packages.save_state(w, st)
        return jsonify({"ok": True})
    return _pj_error(go)


@app.route("/api/project/doc", methods=["POST"])
def project_doc_op():
    """{"op": rename | copy | delete | snapshot | restore | versions | move | copy_to, "type", "name", "new", "note",
    "version", "as_copy", "project" (move, copy_to: the target project), "with_uses" (move, copy_to: with the documents
    it uses)}"""
    req = request.get_json(force=True)
    op, t, n = req.get("op"), req.get("type"), req.get("name")
    # document names follow the file names of the tabs (_part_path, _asm_path, ...): letters, digits, _ - .
    for k in ("new", "as_copy"):
        if req.get(k):
            req[k] = safe_name(req[k])
    def go():
        if op == "rename":
            return jsonify({"name": PROJECTS.rename_doc(t, n, req.get("new") or "")})
        if op == "copy":
            return jsonify({"name": PROJECTS.copy_doc(t, n, req.get("new") or (n + " copy"))})
        if op == "delete":
            PROJECTS.delete_doc(t, n)
            return jsonify({"ok": True})
        if op == "snapshot":
            return jsonify({"version": PROJECTS.snapshot(t, n, req.get("note") or "")})
        if op == "restore":
            return jsonify({"file": PROJECTS.restore(t, n, req.get("version"), req.get("as_copy"))})
        if op == "versions":
            return jsonify(PROJECTS.versions(t, n))
        if op in ("move", "copy_to"):
            return jsonify({"done": PROJECTS.transfer_doc(t, n, req.get("project") or "", "move" if op == "move" else "copy",
                                                          bool(req.get("with_uses")))})
        raise ValueError("unknown operation %s" % op)
    return _pj_error(go)


@app.route("/api/project/states", methods=["GET"])
def project_states():
    if not PROJECTS.current_name():
        return jsonify([])             # no project open (for example while the projects folder changes)
    return _pj_error(lambda: jsonify(PROJECTS.states()))


@app.route("/api/project/state/<name>", methods=["GET", "PUT", "DELETE"])
def project_state(name):
    def go():
        if request.method == "GET":
            return jsonify(PROJECTS.load_state(name))
        if request.method == "DELETE":
            PROJECTS.delete_state(name)
            return jsonify({"ok": True})
        PROJECTS.save_state(name, request.get_json(force=True))
        return jsonify({"ok": True})
    try:
        return go()
    except (ValueError, OSError) as e:
        return error(str(e))


@app.route("/api/project/open_folder", methods=["POST"])
def project_open_folder():
    """Opens a project folder (work, drawings, step, step_import, versions or the project root) in the file manager of this PC."""
    req = request.get_json(force=True)
    name = PROJECTS.current_name()
    if not name:
        return error("no project is open")
    sub = req.get("sub") or ""
    path = os.path.join(PROJECTS.project_dir(name), sub) if sub else PROJECTS.project_dir(name)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        return error("cannot open %s: %s" % (path, e))
    return jsonify({"ok": True, "path": path})


@app.route("/api/dialog", methods=["POST"])
def dialog():
    """Native dialog on this PC: {"kind": "open" | "folder" | "save", "title", "initial", "filter": "step" | "dxf" | "inp" | ...}."""
    req = request.get_json(force=True) or {}
    filt = (req.get("filter") or "").lower()
    pats = {"step": [("STEP files", "*.step *.stp"), ("All files", "*.*")],
            "model": [("STEP and STL files", "*.step *.stp *.stl"), ("STEP files", "*.step *.stp"), ("STL files", "*.stl"), ("All files", "*.*")],
            "dxf": [("DXF files", "*.dxf"), ("All files", "*.*")],
            "inp": [("Abaqus input", "*.inp"), ("All files", "*.*")],
            "image": [("Images", "*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tif *.tiff"), ("All files", "*.*")],
            "shinycad": [("ShinyCAD documents", "*.scpart *.scasm *.scsketch *.scfea *.scexp *.sccam"), ("All files", "*.*")],
            "scpart": [("ShinyCAD part", "*.scpart")], "scasm": [("ShinyCAD assembly", "*.scasm")],
            "scsketch": [("ShinyCAD sketch", "*.scsketch")], "scfea": [("ShinyCAD analysis", "*.scfea")],
            "scexp": [("ShinyCAD explicit analysis", "*.scexp")], "sccam": [("ShinyCAD CAM", "*.sccam")],
            "nc": [("G-code", "*.nc *.ngc *.gcode *.tap"), ("All files", "*.*")]}.get(filt, [("All files", "*.*")])
    try:
        path = dialogs.ask(req.get("kind") or "open", req.get("title") or "", req.get("initial") or "", pats, req.get("save_name") or "")
    except Exception as e:
        return error("the file dialog is not available on this PC: %s" % e, 500)
    return jsonify({"path": path})


@app.route("/api/fits", methods=["GET"])
def fit_classes():
    return jsonify(fits.tables())


@app.route("/api/fits/calc", methods=["POST"])
def fit_calc():
    """{"size", "hole", "shaft"} -> fit (fits.fit)."""
    req = request.get_json(force=True)
    try:
        return jsonify(fits.fit(float(req["size"]), req["hole"], req["shaft"]))
    except (KeyError, TypeError, ValueError) as e:
        return error(str(e))


@app.route("/api/fit", methods=["POST"])
def fit_limits():
    req = request.get_json(force=True)
    try:
        up, lo = fits.limits(float(req["size"]), req["cls"])
    except (KeyError, ValueError) as e:
        return error(str(e))
    return jsonify({"upper": up, "lower": lo, "upper_text": fits.fmt_dev(up), "lower_text": fits.fmt_dev(lo)})


@app.route("/")
def index():
    r = send_from_directory(STATIC_DIR, "index.html", max_age=0)
    r.headers["Cache-Control"] = "no-store"
    return r


@app.route("/static/<path:p>")
def static_files(p):
    r = send_from_directory(STATIC_DIR, p, max_age=0)
    r.headers["Cache-Control"] = "no-store"
    return r


@app.route("/api/build")
def api_build():
    """Build stamp of the server files: the newest modification time of the static files."""
    newest = 0.0
    for root, _dirs, files in os.walk(STATIC_DIR):
        for fn in files:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, fn)))
            except OSError:
                pass
    import datetime
    return jsonify({"build": datetime.datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M")})


@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
def post_config():
    cfg = request.get_json(force=True)
    try:
        for key in ("sheet_sizes_mm", "title_block", "fields", "views", "border"):
            if key not in cfg:
                return error("missing key: %s" % key)
        save_config(cfg)
    except Exception as e:
        return error(str(e))
    return jsonify({"ok": True})


@app.route("/api/options", methods=["GET"])
def get_options():
    cfg = load_config()
    return jsonify(dict(units.options(cfg), browser=cfg.get("browser") or ""))


@app.route("/api/options", methods=["PUT"])
def put_options():
    """Program options (units.py): {"units": "mm" | "inch", "keys": "default" | "left"}; "browser": the browser
    command of run.py (config.json "browser", empty: the system default)."""
    req = request.get_json(force=True) or {}
    browser = req.pop("browser", None)
    for k, v in req.items():
        if k not in units.CHOICES or v not in units.CHOICES[k]:
            return error("invalid option %s: %s" % (k, v))
    cfg = load_config()
    o = units.options(cfg)
    o.update(req)
    cfg["options"] = o
    if browser is not None:            # browser command for run.py (used at the next start)
        cfg["browser"] = str(browser).strip()
    save_config(cfg)
    return jsonify(dict(o, browser=cfg.get("browser") or ""))


@app.route("/api/upload", methods=["POST"])
def upload():
    res, errs = [], []
    for fs in request.files.getlist("files"):
        name = os.path.basename(fs.filename or "upload.step")
        if not name.lower().endswith(STEP_EXT):
            errs.append("%s: not a STEP file" % name)
            continue
        d = os.path.join(WORK_DIR, uuid.uuid4().hex[:8])
        os.makedirs(d)
        path = os.path.join(d, name)
        fs.save(path)
        try:
            res.append(_register(path))
        except Exception as e:
            errs.append("%s: %s" % (name, e))
    return jsonify({"files": res, "errors": errs})


@app.route("/api/open_path", methods=["POST"])
def open_path():
    p = (request.get_json(force=True).get("path") or "").strip().strip('"')
    if not p or not os.path.exists(p):
        return error("path not found: %s" % p)
    paths = []
    if os.path.isdir(p):
        paths = [os.path.join(p, n) for n in sorted(os.listdir(p)) if n.lower().endswith(STEP_EXT)]
    elif p.lower().endswith(STEP_EXT):
        paths = [p]
    if not paths:
        return error("no STEP files in %s" % p)
    res, errs = [], []
    for path in paths:
        try:
            path = PROJECTS.import_copy(path)
            res.append(_register(path, source=path))
        except Exception as e:
            errs.append("%s: %s" % (os.path.basename(path), e))
    return jsonify({"files": res, "errors": errs})


@app.route("/api/files/<fid>", methods=["DELETE"])
def remove_file(fid):
    with LOCK:
        FILES.pop(fid, None)
        for k in [k for k in CACHE if k[0] and k[0][0] == fid]:
            CACHE.pop(k, None)
    return jsonify({"ok": True})


@app.route("/api/preview", methods=["POST"])
def preview():
    req = request.get_json(force=True)
    try:
        ds, cfg = build_drawings(req)
    except Exception as e:
        traceback.print_exc()
        return error("preview failed: %s" % e, 500)
    return jsonify({"drawings": [{"name": d["file_name"], "sheet": d["sheet"],
                                  "scale": drawing.scale_text(d["scale"]),
                                  "size": d["size"], "selection": d["selection"],
                                  "maps": d["meta"]["maps"], "snaps": drawing.snaps(d["views"], d["meta"].get("details"), load_dsketches(d["ann_name"]), d["meta"]["maps"]),
                                  "details": d["meta"].get("details") or [],
                                  "all_views": d["meta"]["all_views"], "hidden_views": d["meta"]["hidden_views"],
                                  "balloon_anchors": d.get("balloon_anchors"), "holes": d.get("holes"),
                                  "has_parts_list": d.get("has_parts_list", False), "parts_list_shown": d.get("parts_list_shown", False),
                                  "origin": list(d["meta"]["origin"]) if d["meta"].get("origin") is not None else None,
                                  "ann_name": d["ann_name"],
                                  "annotations": load_annotations(d["ann_name"]),
                                  "layout": load_layout(d["ann_name"]),
                                  "sketches": sorted(load_dsketches(d["ann_name"])),
                                  "svg": render.to_svg(d, cfg)} for d in ds]})


@app.route("/api/export", methods=["POST"])
def export():
    req = request.get_json(force=True)
    formats = [f for f in (req.get("formats") or ["pdf", "dxf"]) if f in ("pdf", "dxf", "svg", "fcstd")]
    out_dir = (req.get("out_dir") or "").strip().strip('"') or (PROJECTS.dirs().drawings or "")
    try:
        ds, cfg = build_drawings(req)
    except Exception as e:
        traceback.print_exc()
        return error("export failed: %s" % e, 500)
    if not ds:
        return error("nothing selected")
    files = []
    for d in ds:
        if "pdf" in formats:
            files.append((d, d["file_name"] + ".pdf", render.to_pdf([d], cfg)))
        if "dxf" in formats:
            files.append((d, d["file_name"] + ".dxf", render.to_dxf(d, cfg)))
        if "svg" in formats:
            files.append((d, d["file_name"] + ".svg", render.to_svg(d, cfg).encode("utf-8")))
        if "fcstd" in formats:
            files.append((d, d["file_name"] + ".FCStd", fcstd.build(d, cfg, d["shape"], d["part_label"])))
    if out_dir or req.get("next_to_source"):
        written = []
        for d, name, data in files:
            target = out_dir
            if not target and d.get("source"):
                target = os.path.join(os.path.dirname(d["source"]), "drawings")
            if not target:
                return error("no output folder for uploaded files")
            os.makedirs(target, exist_ok=True)
            path = os.path.join(target, name)
            with open(path, "wb") as f:
                f.write(data)
            written.append(path)
        return jsonify({"written": written})
    if len(files) == 1:
        _, name, data = files[0]
        return send_file(io.BytesIO(data), as_attachment=True, download_name=name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for _, name, data in files:
            z.writestr(name, data)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="drawings.zip", mimetype="application/zip")


@app.route("/api/titleblock_preview", methods=["POST"])
def titleblock_preview():
    cfg = request.get_json(force=True)
    sheet = cfg.get("_preview_sheet") or cfg.get("sheet", "A3")
    if str(sheet).lower() == "auto":
        sheet = "A3"
    try:
        vals = dict(cfg["fields"])
        for k in ("Title", "DrawingNumber", "Date", "Scale"):
            vals[k] = vals.get(k) or {"Title": "Part name", "DrawingNumber": "PART_NAME",
                                      "Date": "2026-01-01", "Scale": "1:1"}[k]
        W, H = tbk.sheet_size(cfg, sheet)
        d = {"size": (W, H), "prims": tbk.sheet_primitives(cfg, sheet, vals, True, APP_DIR)}
        return jsonify({"svg": render.to_svg(d, cfg)})
    except Exception as e:
        return error(str(e))


@app.route("/api/logo", methods=["POST"])
def logo():
    fs = request.files.get("file")
    if fs is None:
        return error("no file")
    ext = os.path.splitext(fs.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        return error("logo must be PNG or JPG")
    name = "logo" + ext
    fs.save(os.path.join(APP_DIR, name))
    return jsonify({"logo_file": name})


# --------------------------------------------------------------------------- sketches

def _sketch_path(name):
    return os.path.join(SKETCH_DIR, safe_name(name) + ".sketch.json")


@app.route("/api/sketch/import", methods=["POST"])
def sketch_import():
    try:
        if request.files:
            fs = request.files.get("file")
            name = os.path.basename(fs.filename or "upload.dxf")
            if not name.lower().endswith(DXF_EXT):
                return error("%s: not a DXF file" % name)
            d = os.path.join(WORK_DIR, uuid.uuid4().hex[:8])
            os.makedirs(d)
            path = os.path.join(d, name)
            fs.save(path)
            source = ""
        else:
            path = (request.get_json(force=True).get("path") or "").strip().strip('"')
            if not os.path.isfile(path):
                return error("file not found: %s" % path)
            if not path.lower().endswith(DXF_EXT):
                return error("not a DXF file: %s" % path)
            name, source = os.path.basename(path), path
        sk = sketch.import_dxf(path, os.path.splitext(name)[0])
        sk["source"] = source
        return jsonify(sk)
    except Exception as e:
        traceback.print_exc()
        return error("DXF import failed: %s" % e, 500)


@app.route("/api/sketch/list", methods=["GET"])
def sketch_list():
    names = []
    if os.path.isdir(SKETCH_DIR):
        names = sorted(n[:-len(".sketch.json")] for n in os.listdir(SKETCH_DIR) if n.endswith(".sketch.json"))
    return jsonify(names)


@app.route("/api/sketch/file/<name>", methods=["GET"])
def sketch_get(name):
    try:
        with open(_sketch_path(name), "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except (OSError, ValueError) as e:
        return error("cannot read sketch %s: %s" % (name, e), 404)


@app.route("/api/sketch/file/<name>", methods=["PUT"])
def sketch_put(name):
    sk = request.get_json(force=True)
    if not isinstance(sk, dict) or "entities" not in sk:
        return error("sketch object expected")
    os.makedirs(SKETCH_DIR, exist_ok=True)
    tmp = _sketch_path(name) + _tmp_ext()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sk, f)
    _replace(tmp, _sketch_path(name))
    return jsonify({"ok": True, "path": _sketch_path(name)})


# --------------------------------------------------------------------------- reference images of sketches

def _img_dir():
    return sketchimage.images_dir(os.fspath(SKETCH_DIR))


def _img_path(fname):
    path = sketchimage.find(_img_dir(), fname)
    if not path:
        raise FileNotFoundError("image not found: %s (folder %s)" % (fname, _img_dir()))
    return path


@app.route("/api/sketch/image", methods=["POST"])
def sketch_image_import():
    """Copies an image file (upload or path on this PC) to the images folder of the sketches."""
    try:
        if request.files:
            fs = request.files.get("file")
            name = os.path.basename(fs.filename or "image.png")
            d = os.path.join(WORK_DIR, uuid.uuid4().hex[:8])
            os.makedirs(d)
            src = os.path.join(d, safe_name(name))
            fs.save(src)
        else:
            src = (request.get_json(force=True).get("path") or "").strip().strip('"')
            if not os.path.isfile(src):
                return error("file not found: %s" % src)
            name = os.path.basename(src)
        fname, w, h = sketchimage.store(src, name, _img_dir())
        return jsonify({"file": fname, "name": os.path.splitext(name)[0], "w": w, "h": h,
                        "path": os.path.join(_img_dir(), fname)})
    except ValueError as e:
        return error(str(e))
    except Exception as e:
        traceback.print_exc()
        return error("image import failed: %s" % e, 500)


@app.route("/api/sketch/image/file/<path:fname>", methods=["GET"])
def sketch_image_file(fname):
    try:
        return send_file(_img_path(fname), max_age=3600)
    except FileNotFoundError as e:
        return error(str(e), 404)


@app.route("/api/sketch/image/lens", methods=["POST"])
def sketch_image_lens():
    """Radial lens coefficient k1 from lines of image pixels that are straight on the object."""
    req = request.get_json(force=True) or {}
    try:
        w, h = sketchimage.image_size(_img_path(req.get("file")))
        r = sketchimage.fit_k1(req.get("lines") or [], w, h)
        r["bounds"] = sketchimage.lens_bounds(r["k1"], w, h)
        return jsonify(r)
    except FileNotFoundError as e:
        return error(str(e), 404)
    except (ValueError, np.linalg.LinAlgError) as e:
        return error("lens correction: %s" % e)


@app.route("/api/sketch/image/perspective", methods=["POST"])
def sketch_image_perspective():
    """Homography from the 4 picked corners (lens-corrected pixels) of a rectangle of known size."""
    req = request.get_json(force=True) or {}
    try:
        w, h = sketchimage.image_size(_img_path(req.get("file")))
        k1 = float(req.get("k1") or 0)
        return jsonify(sketchimage.perspective(req.get("pts") or [], float(req.get("width") or 0),
                                               float(req.get("height") or 0), sketchimage.lens_bounds(k1, w, h)))
    except FileNotFoundError as e:
        return error(str(e), 404)
    except (ValueError, TypeError, np.linalg.LinAlgError) as e:
        return error("perspective correction: %s" % e)


@app.route("/api/sketch/loops", methods=["POST"])
def sketch_loops_route():
    """Closed profiles and open ends of the posted sketch (for the indication in the sketch editor)."""
    req = request.get_json(force=True) or {}
    try:
        return jsonify(part.sketch_loops(req.get("sketch") or {}))
    except Exception as e:
        return error("sketch loops: %s" % e)


@app.route("/api/sketch/image/round", methods=["POST"])
def sketch_image_round():
    """Correction from points (lens-corrected pixels) on 1 or 2 concentric circles, the diameter of the first and
    the picked centre (optional)."""
    req = request.get_json(force=True) or {}
    try:
        w, h = sketchimage.image_size(_img_path(req.get("file")))
        k1 = float(req.get("k1") or 0)
        return jsonify(sketchimage.round_part(req.get("rims") or [], float(req.get("diameter") or 0),
                                              sketchimage.lens_bounds(k1, w, h), req.get("centre")))
    except FileNotFoundError as e:
        return error(str(e), 404)
    except (ValueError, TypeError, np.linalg.LinAlgError) as e:
        return error("round part: %s" % e)


@app.route("/api/sketch/image/fit", methods=["POST"])
def sketch_image_fit():
    """Homography from control points: lens-corrected pixels and their sketch points (at least 4 pairs)."""
    req = request.get_json(force=True) or {}
    try:
        w, h = sketchimage.image_size(_img_path(req.get("file")))
        k1 = float(req.get("k1") or 0)
        return jsonify(sketchimage.fit_points(req.get("src") or [], req.get("dst") or [], sketchimage.lens_bounds(k1, w, h)))
    except FileNotFoundError as e:
        return error(str(e), 404)
    except (ValueError, TypeError, np.linalg.LinAlgError) as e:
        return error("control points: %s" % e)


@app.route("/api/sketch/image/render", methods=["POST"])
def sketch_image_render():
    """Corrected image file of {file, k1, H, out}; an existing file of the same parameters is used again."""
    req = request.get_json(force=True) or {}
    try:
        src = _img_path(req.get("file"))
        k1, H, out = float(req.get("k1") or 0), req.get("H"), req.get("out")
        if not H or not out:
            return error("H and out are required")
        name = sketchimage.corrected_name(os.path.basename(src), k1, H, out)
        dst = os.path.join(_img_dir(), name)
        if not os.path.isfile(dst):
            sketchimage.render(src, k1, H, out, dst)
        return jsonify({"file": name})
    except FileNotFoundError as e:
        return error(str(e), 404)
    except (ValueError, TypeError, np.linalg.LinAlgError) as e:
        return error("corrected image: %s" % e)


@app.route("/api/sketch/sheet", methods=["POST"])
def sketch_sheet():
    req = request.get_json(force=True)
    cfg = load_config()
    sheet = req.get("sheet", "A3")
    if sheet not in cfg["sheet_sizes_mm"]:
        return error("unknown sheet %s" % sheet)
    try:
        return jsonify(sketch.sheet_svg(req.get("sketch") or {}, cfg, sheet, bool(req.get("title_block", True)),
                                        req.get("fields") or {}, APP_DIR))
    except Exception as e:
        traceback.print_exc()
        return error("sheet failed: %s" % e, 500)


@app.route("/api/sketch/export", methods=["POST"])
def sketch_export():
    req = request.get_json(force=True)
    sk, anns = req.get("sketch") or {}, req.get("annotations") or []
    fmt = req.get("format", "dxf")
    cfg = load_config()
    try:
        if fmt == "pdf":
            opts = dict(req.get("pdf") or {})
            opts["base_dir"] = APP_DIR
            data = sketch.to_pdf(sk, anns, cfg, opts, req.get("fields") or {})
        elif fmt == "dxf":
            opts = dict(req.get("pdf") or {})
            opts["base_dir"] = APP_DIR
            data = sketch.to_dxf(sk, anns, cfg, opts, req.get("fields") or {})
        else:
            return error("unknown format %s" % fmt)
    except Exception as e:
        traceback.print_exc()
        return error("export failed: %s" % e, 500)
    name = safe_name(req.get("file_name") or sk.get("name") or "sketch") + "." + fmt
    folder = (req.get("folder") or "").strip().strip('"') or (PROJECTS.dirs().drawings or "")
    if folder:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        if os.path.exists(path) and not req.get("overwrite"):
            return jsonify({"exists": path}), 409
        with open(path, "wb") as f:
            f.write(data)
        return jsonify({"written": [path]})
    return send_file(io.BytesIO(data), as_attachment=True, download_name=name)


@app.route("/api/fea/formats", methods=["GET"])
def fea_formats():
    why = fea.import_error()
    return jsonify({"available": why is None, "error": why, "python": sys.executable, "formats": fea.FORMATS})


def _fea_geometry(req, tmpd):
    """(geometry file for gmsh, base name) of the request's part or assembly. Parts are written as BREP so that
    the faces shared by partition cells stay shared."""
    from . import project as pj
    if req.get("assembly"):
        asm = req["assembly"]
        items = assembly.build(asm, _asm_sources(), explode=False)
        if not any(sh is not None for _, sh, _ in items):
            raise ValueError("the assembly has no solids")
        base = safe_name(asm.get("name") or "assembly")
        path = os.path.join(tmpd, base + ".step")
        assembly.export_step(asm, items, path)
        return path, base
    p = req.get("part") or {}
    shape, st = part.build(p)
    if shape is None:
        raise ValueError("the part has no solid")
    base = safe_name(p.get("name") or "part")
    path = os.path.join(tmpd, base + ".brep")
    pj.write_brep(shape.wrapped, path)
    groups, min_area = part.mesh_compounds(p, shape)
    if not isinstance(req.get("opts"), dict):
        req["opts"] = {}
    opts = req["opts"]
    seeds = part.mesh_seeds(st)
    if seeds:
        opts["seeds"] = seeds
    if groups:
        opts["compounds"] = groups
    if min_area > 0:
        opts["compound_min_area"] = min_area
    return path, base


def _gmsh_missing():
    why = fea.import_error()
    if why:
        return error("gmsh cannot be imported by %s: %s. Install it with  \"%s\" -m pip install gmsh  and restart the server"
                     % (sys.executable, why, sys.executable), 500)
    return None


@app.route("/api/fea/preview", methods=["POST"])
def fea_preview():
    """Mesh without a file: the summary, the per-cell report and the boundary mesh edges for the 3D view."""
    req = request.get_json(force=True)
    miss = _gmsh_missing()
    if miss:
        return miss
    tmpd = tempfile.mkdtemp(dir=WORK_DIR)
    try:
        geo, base = _fea_geometry(req, tmpd)
        opts = dict(req.get("opts") or {})
        opts["preview"] = True
        res = fea.run(geo, "", opts)
    except Exception as e:
        return error(str(e), 500)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    res.pop("path", None)
    return jsonify(res)


@app.route("/api/fea/export", methods=["POST"])
def fea_export():
    """FEA mesh of a part or an assembly (gmsh). Body: {"part": record} or {"assembly": record}, "format": ".inp" ...,
    "opts": {size, size_min, order, kind, algorithm, optimize, curvature, groups}, "folder", "overwrite"."""
    req = request.get_json(force=True)
    miss = _gmsh_missing()
    if miss:
        return miss
    fmt = (req.get("format") or ".inp").lower()
    if fmt not in fea.FORMATS:
        return error("unknown mesh format %s" % fmt)
    tmpd = tempfile.mkdtemp(dir=WORK_DIR)
    try:
        geo, base = _fea_geometry(req, tmpd)
    except Exception as e:
        return error(str(e))
    name = base + fmt
    tmp = os.path.join(tmpd, name)
    try:
        res = fea.run(geo, tmp, req.get("opts") or {})
    except Exception as e:
        return error(str(e), 500)
    with open(tmp, "rb") as f:
        data = f.read()
    folder = (req.get("folder") or "").strip().strip('"') or (PROJECTS.dirs().step or "")
    res["bytes"] = len(data)
    res.pop("path", None)
    if folder:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        if os.path.exists(path) and not req.get("overwrite"):
            return jsonify({"exists": path}), 409
        with open(path, "wb") as f:
            f.write(data)
        res["written"] = [path]
        return jsonify(res)
    r = send_file(io.BytesIO(data), as_attachment=True, download_name=name)
    r.headers["X-Mesh-Info"] = json.dumps({k: v for k, v in res.items() if k != "path"})
    return r


def _file_info(fid):
    f = FILES[fid]
    return {"file_id": fid, "name": f["name"], "source": f.get("source") or "", "parts": [x.info() for x in f["parts"]],
            "refresh": bool(f.get("part_name") or f.get("asm_request") or f.get("path"))}


def _part_to_drawings(p):
    shape, st = part.build(p)
    if shape is None:
        return error("the part has no solid")
    pname = p.get("name") or "part"
    fid = "part_" + safe_name(pname)
    if p.get("uid") and p.get("legacy_ann"):
        # a part saved before the uid existed: its annotations stored by name are taken over once
        akey, old = "part_" + safe_name(str(p["uid"])), safe_name(pname)
        for pf in (_ann_path, _layout_path):
            if not os.path.isfile(pf(akey)) and os.path.isfile(pf(old)):
                shutil.copyfile(pf(old), pf(akey))
    with LOCK:
        FILES[fid] = {"name": pname + ".part", "path": "", "source": None, "part_name": pname, "part": p,
                      "ann_key": ("part_" + safe_name(str(p["uid"]))) if p.get("uid") else None,
                      "parts": [model.Part(0, pname, shape.wrapped)], "holes": part.holes_of(st)}
        for k in [k for k in CACHE if k[0] and k[0][0] == fid]:
            CACHE.pop(k, None)
    return jsonify({"files": [_file_info(fid)], "errors": []})


@app.route("/api/reference", methods=["GET"])
def reference_tables():
    """Thread and fastener reference tables (drawgen/fasteners.py)."""
    from . import fasteners, roughness
    d = fasteners.reference()
    d["roughness"] = roughness.table()
    return jsonify(d)


@app.route("/api/reference/tolerance", methods=["GET"])
def reference_tolerance():
    from . import fasteners
    try:
        d = float(request.args.get("d")); P = float(request.args.get("P"))
    except (TypeError, ValueError):
        return error("d and P are required")
    t = fasteners.tolerance(d, P, request.args.get("cls", "6H"))
    if t is None:
        return error("no table values for this size and class")
    return jsonify(t)


@app.route("/api/part/to_drawings", methods=["POST"])
def part_to_drawings():
    req = request.get_json(force=True)
    return _part_to_drawings(req.get("part") or {})


@app.route("/api/files/<fid>/refresh", methods=["POST"])
def refresh_file(fid):
    """Rebuilds the model of a loaded file: a part from the part given in the request ("part") or else from
    its saved part file, an assembly from its saved assembly file, a STEP file from its path. The drawing
    annotations are kept (they are stored by file name)."""
    req = request.get_json(force=True, silent=True) or {}
    f = FILES.get(fid)
    if f is None:
        return error("the model is not loaded any more: make the drawing again")
    if f.get("part_name"):
        p = req.get("part")
        if not p:
            path = _part_path(f["part_name"])
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as fh:
                    p = json.load(fh)
            else:
                p = f.get("part") or {}
        p["name"] = f["part_name"]
        return _part_to_drawings(p)
    if f.get("asm_request"):
        r = dict(f["asm_request"])
        if req.get("assembly"):
            r["assembly"] = req["assembly"]
        else:
            path = _asm_path((r.get("assembly") or {}).get("name") or "assembly")
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as fh:
                    r["assembly"] = json.load(fh)
        return _asm_to_drawings(r)
    if f.get("path"):
        parts = model.load_step(f["path"])
        with LOCK:
            f["parts"] = parts
            for k in [k for k in CACHE if k[0] and k[0][0] == fid]:
                CACHE.pop(k, None)
        return jsonify({"files": [_file_info(fid)], "errors": []})
    return error("this model cannot be rebuilt")


# --------------------------------------------------------------------------- parts (3D)

def _part_path(name):
    return os.path.join(PART_DIR, safe_name(name) + ".part.json")


@app.route("/api/part/last", methods=["GET"])
def get_part_last():
    """Last used settings of the Part tab commands (config.local.json "part_last": {type: {key: value}})."""
    return jsonify(load_config().get("part_last") or {})


@app.route("/api/part/last", methods=["PUT"])
def put_part_last():
    """{"type": command type, "values": {key: value}} merged into the last used settings of that command;
    {"clear": true} removes all of them."""
    req = request.get_json(force=True) or {}
    cfg = load_config()
    last = cfg.get("part_last") or {}
    if req.get("clear"):
        last = {}
    else:
        t = str(req.get("type") or "")
        vals = req.get("values")
        if not t or not isinstance(vals, dict):
            return error("type and values required")
        last[t] = dict(last.get(t) or {}, **vals)
    cfg["part_last"] = last
    save_config(cfg)
    return jsonify(last)


@app.route("/api/part/build", methods=["POST"])
def part_build():
    req = request.get_json(force=True)
    try:
        upto = req.get("upto")
        bodies, owners = {}, {}
        shape, st = part.build(part.migrate(req.get("part") or {}), upto=int(upto) if upto is not None else None, surfaces=bodies, owners=owners)
        m = part.mesh(shape)
        m["face_owner"] = part.face_owners(m, owners)
        vol = shape.volume if shape is not None else 0.0
        smesh = {}
        for k, b in bodies.items():
            try:
                mm = part.mesh(b)
                rough = getattr(b, "_mesh", False)        # a rough STL mesh: its triangle edges are not drawn
                smesh[k] = {"vertices": mm["vertices"], "triangles": mm["triangles"], "edges": [] if rough else mm["edges"],
                            "edge_keys": [] if rough else mm["edge_keys"], "face_keys": mm["face_keys"], "face_of_tri": mm["face_of_tri"]}
            except Exception:
                pass
        solids = []
        if shape is not None:
            for i, so in enumerate(part._topo(shape).solids):
                solids.append({"index": i, "volume_mm3": round(so.volume, 3), "bbox": part.exact_bbox(so)})
    except Exception as e:
        traceback.print_exc()
        return error("build failed: %s" % e, 500)
    return jsonify({"mesh": m, "status": st, "volume_mm3": vol, "surfaces": smesh, "solids": solids,
                    "cells": len(shape.solids()) if shape is not None else 0})


@app.route("/api/part/regions", methods=["POST"])
def part_regions():
    """Pieces of a surface trim for graphical region selection: {"part", "index"} -> [{"point", "area", "mesh"}]."""
    req = request.get_json(force=True)
    p = part.migrate(req.get("part") or {})
    i = int(req.get("index", 0))
    feats = part.normalize(p)
    if not 0 <= i < len(feats):
        return jsonify([])
    try:
        from . import surfaces as sfm
        bodies, datums = {}, {}
        shape, st = part.build(p, upto=i, surfaces=bodies, datums=datums)
        f = dict(feats[i])
        f["_datums"] = datums
        if f.get("with") == "sketch":
            frames = {x.get("id"): x["frame"] for x in st if x.get("frame")}
            f["_tool_edges"] = part.sketch_tool_edges(feats, frames, datums, f.get("tool"))
        pieces, _tool = sfm.trim_pieces(shape, bodies, f)
        out = []
        for pc in pieces:
            q = sfm._point_on(pc)
            mm = part.mesh(pc)
            out.append({"point": [q.X, q.Y, q.Z], "area": round(pc.area, 3),
                        "mesh": {"vertices": mm["vertices"], "triangles": mm["triangles"], "edges": mm["edges"]}})
        return jsonify(out)
    except Exception as e:
        return error("regions failed: %s" % e, 400)


@app.route("/api/part/inspect", methods=["POST"])
def part_inspect():
    """Topology report of a body: {"part", "body": feature id of a surface body or null for the solid, "gap_tol",
    "min_area", "min_edge"} -> {"summary", "issues"}."""
    req = request.get_json(force=True)
    p = part.migrate(req.get("part") or {})
    try:
        from . import surfaces as sfm
        bodies = {}
        shape, st = part.build(p, surfaces=bodies)
        bid = req.get("body")
        body = bodies.get(bid) if bid else shape
        if body is None:
            return error("the body was not found", 400)
        rep = sfm.inspect(body, float(req.get("gap_tol", 0.1) or 0.1), float(req.get("min_area", 0.01) or 0.01), float(req.get("min_edge", 0.01) or 0.01))
        return jsonify(rep)
    except Exception as e:
        traceback.print_exc()
        return error("inspect failed: %s" % e, 500)


@app.route("/api/part/section", methods=["POST"])
def part_section():
    """Cap faces of the solid on a plane: {"part", "origin": [x, y, z], "normal": [x, y, z]} -> mesh of the
    section faces ({"vertices", "triangles", "edges"}) for the section view."""
    req = request.get_json(force=True)
    p = part.migrate(req.get("part") or {})
    try:
        from build123d import Plane, Face, Vector, Compound
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
        shape, st = part.build(p)
        if shape is None:
            return jsonify({"vertices": [], "triangles": [], "edges": []})
        o = [float(v) for v in req.get("origin") or [0, 0, 0]]
        n = Vector(*[float(v) for v in req.get("normal") or [0, 0, 1]])
        bb = shape.bounding_box()
        size = bb.diagonal * 2.0 + 1.0
        face = Face.make_rect(size, size, Plane(origin=Vector(*o), z_dir=n))
        com = BRepAlgoAPI_Common(shape.wrapped, face.wrapped)
        com.Build()
        cap = Compound(com.Shape())
        m = part.mesh(cap) if cap.faces() else {"vertices": [], "triangles": [], "edges": []}
        return jsonify({"vertices": m["vertices"], "triangles": m["triangles"], "edges": m["edges"]})
    except Exception as e:
        traceback.print_exc()
        return error("section failed: %s" % e, 500)


@app.route("/api/part/profile_regions", methods=["POST"])
def part_profile_regions():
    """Regions of the sketch of a sketch feature for picking: {"part", "index"} -> [{"point", "uv", "area", "mesh"}]."""
    req = request.get_json(force=True)
    p = part.migrate(req.get("part") or {})
    i = int(req.get("index", 0))
    feats = part.normalize(p)
    if not 0 <= i < len(feats):
        return jsonify([])
    try:
        from . import surfaces as sfm
        bodies, datums = {}, {}
        shape, st = part.build(p, upto=i, surfaces=bodies, datums=datums)
        f = dict(feats[i])
        f["_datums"] = datums
        frames = {x.get("id"): x["frame"] for x in st if x.get("frame")}
        if f.get("sketch_ref") and frames.get(f["sketch_ref"]):
            f["_frame"] = frames[f["sketch_ref"]]
        plane = part.plane_of(f)
        out = []
        for fc, uv in part.profile_regions(f.get("sketch") or {}, plane):
            q = sfm._point_on(fc)
            mm = part.mesh(fc)
            out.append({"point": [q.X, q.Y, q.Z], "uv": list(uv), "area": round(fc.area, 3),
                        "mesh": {"vertices": mm["vertices"], "triangles": mm["triangles"], "edges": mm["edges"]}})
        return jsonify(out)
    except Exception as e:
        return error("regions failed: %s" % e, 400)


@app.route("/api/part/refs", methods=["POST"])
def part_refs():
    req = request.get_json(force=True)
    p = req.get("part") or {}
    i = int(req.get("index", 0))
    feats = p.get("features") or []
    if not 0 <= i < len(feats):
        return jsonify([])
    try:
        bodies, datums = {}, {}
        p = part.migrate(p)
        feats = part.normalize(p)
        shape, st = part.build(p, upto=i, surfaces=bodies, datums=datums)
        f = dict(feats[i])
        f["_datums"] = datums
        if not req.get("path") and req.get("section") is None:
            part.resolve_plane(f, shape, bodies, datums)
        if req.get("path"):
            f = {"plane": f.get("path_plane", "XY"), "offset": f.get("path_offset", 0)}
        if req.get("section") is not None:
            sec = (f.get("sections") or [])[int(req["section"])]
            f = {"plane": sec.get("plane", "XY"), "offset": sec.get("offset", 0)}
        out = part.section_refs(shape, f, datums, bodies)
        if f.get("_project", True):
            out += part.earlier_sketch_refs(p, feats, i, part.plane_of(f), st, datums)
        return jsonify(out)
    except Exception as e:
        traceback.print_exc()
        return error("reference geometry failed: %s" % e, 500)


@app.route("/api/part/expand", methods=["POST"])
def part_expand():
    """Edge references extended from picked edges or faces: {"part", "index", "mode": tangent | face | faces,
    "refs": [edge keys] or [face keys]} -> [edge keys]."""
    req = request.get_json(force=True)
    p = req.get("part") or {}
    i = int(req.get("index", 0))
    try:
        shape, _ = part.build(p, upto=i)
        if shape is None:
            return jsonify(req.get("refs") or [])
        return jsonify(part.expand_edges(shape, req.get("refs") or [], req.get("mode") or "tangent"))
    except Exception as e:
        traceback.print_exc()
        return error("edge selection failed: %s" % e, 500)


@app.route("/api/part/expand_faces", methods=["POST"])
def part_expand_faces():
    """Face references grown from a picked face: {"part", "index", "mode": tangent | connected, "ref": face key,
    "surface": surface body id (none: the solid)} -> [face keys]."""
    req = request.get_json(force=True)
    try:
        bodies = {}
        shape, _ = part.build(req.get("part") or {}, upto=int(req.get("index", 0)), surfaces=bodies)
        body = bodies.get(req.get("surface")) if req.get("surface") else shape
        if body is None:
            return jsonify([req.get("ref")])
        return jsonify(part.expand_faces(body, req.get("ref") or {}, req.get("mode") or "tangent"))
    except Exception as e:
        traceback.print_exc()
        return error("face selection failed: %s" % e, 500)


@app.route("/api/part/list", methods=["GET"])
def part_list():
    names = []
    if os.path.isdir(PART_DIR):
        names = sorted(n[:-len(".part.json")] for n in os.listdir(PART_DIR) if n.endswith(".part.json"))
    return jsonify(names)


@app.route("/api/part/file/<name>", methods=["GET"])
def part_get(name):
    try:
        with open(_part_path(name), "r", encoding="utf-8") as f:
            return jsonify(part.migrate(json.load(f)))
    except (OSError, ValueError) as e:
        return error("cannot read part %s: %s" % (name, e), 404)


@app.route("/api/part/file/<name>", methods=["PUT"])
def part_put(name):
    p = request.get_json(force=True)
    if not isinstance(p, dict) or "features" not in p:
        return error("part object expected")
    # imported STEP files: a local copy in the project (step_import/) and the feature path pointed at it
    for f in p.get("features") or []:
        if f.get("type") in ("import", "surf_import") and f.get("path"):
            try:
                f["path"] = PROJECTS.import_copy(f["path"].strip().strip('"'))
            except OSError:
                pass
    os.makedirs(PART_DIR, exist_ok=True)
    tmp = _part_path(name) + _tmp_ext()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f)
    _replace(tmp, _part_path(name))
    return jsonify({"ok": True, "path": _part_path(name), "part": p})


@app.route("/api/part/export", methods=["POST"])
def part_export():
    req = request.get_json(force=True)
    p = req.get("part") or {}
    bodies = {}
    shape, st = part.build(p, surfaces=bodies)
    hidden = set(p.get("hidden") or [])
    names = {f.get("id"): f.get("name") for f in p.get("features") or []}
    surfs = [(fid, b) for fid, b in bodies.items() if b is not None and fid not in hidden]
    if shape is None and not surfs:
        return error("the part has no solid and no surface body")
    name = safe_name(p.get("name") or "part") + ".step"
    tmpd = tempfile.mkdtemp(dir=WORK_DIR)
    tmp = os.path.join(tmpd, name)
    part.export_step(shape, tmp, surfaces=surfs, names=names, label=p.get("name") or "part")
    with open(tmp, "rb") as f:
        data = f.read()
    folder = (req.get("folder") or "").strip().strip('"') or (PROJECTS.dirs().step or "")
    if folder:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        if os.path.exists(path) and not req.get("overwrite"):
            return jsonify({"exists": path}), 409
        with open(path, "wb") as f:
            f.write(data)
        return jsonify({"written": [path]})
    return send_file(io.BytesIO(data), as_attachment=True, download_name=name)


# --------------------------------------------------------------------------- assemblies

def _asm_path(name):
    return os.path.join(ASM_DIR, safe_name(name) + ".asm.json")


def _asm_sources():
    with LOCK:
        files = {k: {"path": v["path"]} for k, v in FILES.items() if v.get("path")}
    return assembly.Sources(PART_DIR, files)


@app.route("/api/assembly/build", methods=["POST"])
def asm_build():
    req = request.get_json(force=True)
    asm = req.get("assembly") or {}
    try:
        src = _asm_sources()
        assembly.prefetch_views(asm, src)            # sources not cached: computed in the worker processes
        comps, rows, tot = assembly.view_data(asm, src, explode=bool(req.get("explode")), have=req.get("have") or (),
                                              default_density=float(req.get("density") or 0))
        res = {"components": comps, "mass": {"rows": rows, "total": tot}}
        if req.get("interference"):
            res["interference"] = assembly.interference_parallel(asm, src, explode=bool(req.get("explode")))
            if res["interference"] is None:
                res["interference"] = assembly.interference(assembly.build(asm, src, explode=bool(req.get("explode"))))
        return jsonify(res)
    except Exception as e:
        traceback.print_exc()
        return error("assembly build failed: %s" % e, 500)


_SKW_CACHE = {}         # sha1 of the part file -> sketch_wires


@app.route("/api/assembly/sketches", methods=["POST"])
def asm_sketches():
    """Sketch curves of the part components that no feature of the part uses, placed (world coordinates):
    {"components": [{"id", "sketches": [{"id", "name", "lines", "points"}]}]}."""
    import hashlib
    asm = (request.get_json(force=True) or {}).get("assembly") or {}
    out = []
    for c in asm.get("components") or []:
        src = c.get("source") or {}
        if src.get("type") != "part":
            continue
        try:
            with open(_part_path(src.get("name", "")), "rb") as f:
                data = f.read()
        except OSError:
            continue
        k = hashlib.sha1(data).hexdigest()
        if k not in _SKW_CACHE:
            try:
                _SKW_CACHE[k] = part.sketch_wires(json.loads(data.decode("utf-8")))
            except Exception:
                traceback.print_exc()
                _SKW_CACHE[k] = []
            while len(_SKW_CACHE) > 100:
                _SKW_CACHE.pop(next(iter(_SKW_CACHE)))
        sks = _SKW_CACHE[k]
        if not sks:
            continue
        t = assembly.trsf_of(c)
        from OCP.gp import gp_Pnt
        W = lambda q: (lambda p: [round(p.X(), 6), round(p.Y(), 6), round(p.Z(), 6)])(gp_Pnt(*q).Transformed(t))
        out.append({"id": c.get("id"), "sketches": [{"id": s["id"], "name": s["name"], "lines": [[W(q) for q in ln] for ln in s["lines"]],
                                                     "points": [W(q) for q in s["points"]]} for s in sks]})
    return jsonify({"components": out})


@app.route("/api/assembly/measure", methods=["POST"])
def asm_measure():
    """Measurement of one or two items of the posted assembly: {"assembly", "items": [{"comp", "face"} |
    {"comp", "datum"}]} -> measure.measure (rows, closest points)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    req = request.get_json(force=True)
    asm = req.get("assembly") or {}
    comps = {c["id"]: c for c in asm.get("components") or []}
    src = _asm_sources()
    items = []
    try:
        for it in (req.get("items") or [])[:2]:
            c = comps.get(it.get("comp"))
            if c is None:
                return error("component not found", 400)
            name = c.get("name") or c["id"]
            if it.get("datum"):
                d = (src.info(c.get("source") or {}).get("datums") or {}).get(it["datum"])
                if not d:
                    return error("reference %s not found" % it["datum"], 400)
                w = assembly._placed_ref(d, ([float(v or 0) for v in c.get("pos") or [0, 0, 0]], [float(v or 0) for v in c.get("rot") or [0, 0, 0]]))
                items.append(dict(w, name=name + " : " + (d.get("name") or it["datum"]), shape=None))
                continue
            shape, err = src.load(c.get("source") or {})
            if shape is None:
                return error(err or "no solid", 400)
            fs = shape.faces()
            fi = int(it.get("face", -1))
            if not 0 <= fi < len(fs):
                return error("face not found", 400)
            from build123d import Shape
            face = Shape.cast(BRepBuilderAPI_Transform(fs[fi].wrapped, assembly.trsf_of(c), True).Shape())
            items.append(measure.item_from_face(face, name))
        if not items:
            return error("nothing picked", 400)
        res = measure.measure(items[0], items[1] if len(items) > 1 else None)
        res["items"] = [measure.label(x) for x in items]
        return jsonify(res)
    except Exception as e:
        traceback.print_exc()
        return error("measure failed: %s" % e, 500)


_PART_SHAPES = {}       # sha1 of the part json -> (shape, datums), the last few parts measured


@app.route("/api/part/measure", methods=["POST"])
def part_measure():
    """Measurement of one or two items of the posted part: {"part", "items": [{"face": index} | {"plane": feature
    id} | {"axis": feature id} | {"base": "XY" | "XZ" | "YZ"}]} -> measure.measure (rows, closest points)."""
    import hashlib
    req = request.get_json(force=True)
    p = part.migrate(req.get("part") or {})
    key = hashlib.sha1(json.dumps(p, sort_keys=True).encode("utf-8")).hexdigest()
    try:
        if key not in _PART_SHAPES:
            dz = {}
            shape, st = part.build(p, datums=dz)
            _PART_SHAPES[key] = (shape, dz)
            while len(_PART_SHAPES) > 4:
                _PART_SHAPES.pop(next(iter(_PART_SHAPES)))
        shape, dz = _PART_SHAPES[key]
        names = {f.get("id"): f.get("name") or f.get("id") for f in p.get("features") or []}
        base = {"XY": [0, 0, 1], "XZ": [0, -1, 0], "YZ": [1, 0, 0]}
        items = []
        for it in (req.get("items") or [])[:2]:
            if it.get("face") is not None:
                fs = shape.faces() if shape is not None else []
                fi = int(it["face"])
                if not 0 <= fi < len(fs):
                    return error("face not found", 400)
                items.append(measure.item_from_face(fs[fi], "face %d" % fi))
            elif it.get("point") is not None:
                # a point clicked on a surface body (a rough STL mesh)
                from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
                from OCP.gp import gp_Pnt
                q = [float(v) for v in it["point"]][:3]
                items.append({"kind": "point", "name": "Point on " + names.get(it.get("surface"), "surface"), "c": q,
                              "shape": BRepBuilderAPI_MakeVertex(gp_Pnt(*q)).Vertex()})
            elif it.get("base") in base:
                items.append({"kind": "plane", "name": "Plane " + it["base"], "c": [0, 0, 0], "n": base[it["base"]], "shape": None})
            else:
                fid = it.get("plane") or it.get("axis")
                d = dz.get(fid)
                if not d:
                    return error("reference not found", 400)
                if d.get("kind") == "axis":
                    items.append({"kind": "axis", "name": names.get(fid, fid), "c": d["o"], "p": d["o"], "n": d["d"], "shape": None})
                else:
                    items.append({"kind": "plane", "name": names.get(fid, fid), "c": d["o"], "n": d["z"], "shape": None})
        if not items:
            return error("nothing picked", 400)
        res = measure.measure(items[0], items[1] if len(items) > 1 else None)
        res["items"] = [measure.label(x) for x in items]
        return jsonify(res)
    except Exception as e:
        traceback.print_exc()
        return error("measure failed: %s" % e, 500)


@app.route("/api/assembly/check", methods=["POST"])
def asm_check():
    """Mate check (assembly.mate_report) of the posted assembly."""
    req = request.get_json(force=True)
    asm = req.get("assembly") or {}
    src = _asm_sources()
    refs, datums = {}, {}
    assembly.prefetch_views(asm, src)
    for c in asm.get("components") or []:
        e = src.info(c.get("source") or {})
        refs[c["id"]] = e.get("refs")
        datums[c["id"]] = dict(e.get("datums") or {}, **assembly.geo_refs(e))
    try:
        return jsonify(assembly.mate_report(asm, lambda cid: refs.get(cid), lambda cid: datums.get(cid)))
    except Exception as e:
        traceback.print_exc()
        return error("mate check failed: %s" % e, 500)


@app.route("/api/assembly/solve", methods=["POST"])
def asm_solve():
    req = request.get_json(force=True)
    asm = req.get("assembly") or {}
    src = _asm_sources()
    refs, datums = {}, {}
    assembly.prefetch_views(asm, src)
    for c in asm.get("components") or []:
        e = src.info(c.get("source") or {})
        refs[c["id"]] = e.get("refs")
        datums[c["id"]] = dict(e.get("datums") or {}, **assembly.geo_refs(e))
    try:
        detail = {}
        out, nr, msgs = assembly.solve_mates(asm, lambda cid: refs.get(cid), lambda cid: datums.get(cid), detail,
                                             drag=req.get("drag"))
    except Exception as e:
        traceback.print_exc()
        return error("solve failed: %s" % e, 500)
    return jsonify({"placements": {k: {"pos": v[0], "rot": v[1]} for k, v in out.items()}, "residual": nr, "messages": msgs,
                    "unsatisfied": detail.get("unsatisfied", {}), "conflicts": detail.get("conflicts", {}),
                    "flipped": detail.get("flipped", [])})


@app.route("/api/assembly/list", methods=["GET"])
def asm_list():
    names = []
    if os.path.isdir(ASM_DIR):
        names = sorted(n[:-len(".asm.json")] for n in os.listdir(ASM_DIR) if n.endswith(".asm.json"))
    return jsonify(names)


@app.route("/api/assembly/file/<name>", methods=["GET"])
def asm_get(name):
    try:
        with open(_asm_path(name), "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except (OSError, ValueError) as e:
        return error("cannot read assembly %s: %s" % (name, e), 404)


@app.route("/api/assembly/file/<name>", methods=["PUT"])
def asm_put(name):
    a = request.get_json(force=True)
    if not isinstance(a, dict) or "components" not in a:
        return error("assembly object expected")
    os.makedirs(ASM_DIR, exist_ok=True)
    tmp = _asm_path(name) + _tmp_ext()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(a, f)
    _replace(tmp, _asm_path(name))
    return jsonify({"ok": True, "path": _asm_path(name)})


@app.route("/api/assembly/step_solids", methods=["POST"])
def asm_step_solids():
    """Solid names of a STEP file (for a component source)."""
    p = (request.get_json(force=True).get("path") or "").strip().strip('"')
    if not os.path.isfile(p):
        return error("file not found: %s" % p)
    try:
        parts = model.load_step(p)
        return jsonify([{"index": i, "name": x.name} for i, x in enumerate(parts)])
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/assembly/export", methods=["POST"])
def asm_export():
    req = request.get_json(force=True)
    asm = req.get("assembly") or {}
    items = assembly.build(asm, _asm_sources(), explode=bool(req.get("explode")))
    if not any(s is not None for _, s, _ in items):
        return error("the assembly has no solids")
    name = safe_name(asm.get("name") or "assembly") + ".step"
    tmpd = tempfile.mkdtemp(dir=WORK_DIR)
    tmp = os.path.join(tmpd, name)
    try:
        assembly.export_step(asm, items, tmp)
    except Exception as e:
        traceback.print_exc()
        return error("STEP export failed: %s" % e, 500)
    with open(tmp, "rb") as f:
        data = f.read()
    folder = (req.get("folder") or "").strip().strip('"') or (PROJECTS.dirs().step or "")
    if folder:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        if os.path.exists(path) and not req.get("overwrite"):
            return jsonify({"exists": path}), 409
        with open(path, "wb") as f:
            f.write(data)
        return jsonify({"written": [path]})
    return send_file(io.BytesIO(data), as_attachment=True, download_name=name)


@app.route("/api/assembly/to_drawings", methods=["POST"])
def asm_to_drawings():
    return _asm_to_drawings(request.get_json(force=True))


def _asm_to_drawings(req):
    asm = req.get("assembly") or {}
    items = assembly.build(asm, _asm_sources(), explode=bool(req.get("explode")))
    aname = asm.get("name") or "assembly"
    fid = "asm_" + safe_name(aname)
    parts = []
    rows, tot = assembly.mass_props(items, float(req.get("density") or 0))
    mass_of = {r["id"]: r for r in rows}
    groups = {}          # source key -> item row
    item_of = {}
    anchors = []         # balloon anchors: [item, centre of mass xyz]
    for c, s, err in items:
        if s is None or c.get("visible") is False:
            continue
        parts.append(model.Part(len(parts), c.get("name") or c.get("id"), s.wrapped))
        gk = json.dumps(c.get("source") or {}, sort_keys=True) + "|" + (c.get("material") or "")
        if gk not in groups:
            groups[gk] = {"item": len(groups) + 1, "qty": 0, "name": re.sub(r" \d+$", "", c.get("name") or c.get("id")),
                          "material": c.get("material") or "", "mass_kg": 0.0}
        g = groups[gk]
        g["qty"] += 1
        m = mass_of.get(c.get("id"))
        if m:
            g["mass_kg"] += m["mass_kg"]
            anchors.append({"item": g["item"], "p": m["cog"], "name": c.get("name")})
        item_of[c.get("id")] = g["item"]
    pl = []
    for g in groups.values():
        pl.append({"item": g["item"], "qty": g["qty"], "name": g["name"], "material": g["material"],
                   "mass": ("%.3f kg" % g["mass_kg"]) if g["mass_kg"] > 0 else ""})
    trails = None
    if req.get("explode"):
        base_items = assembly.build(asm, _asm_sources(), explode=False)
        trails = []
        for (c, s, err), (c0, s0, err0) in zip(items, base_items):
            if s is None or s0 is None or c.get("visible") is False:
                continue
            a, b = s0.center(), s.center()
            trails.append([[a.X, a.Y, a.Z], [b.X, b.Y, b.Z]])
    if not parts:
        return error("the assembly has no solids")
    with LOCK:
        FILES[fid] = {"name": aname + ".asm", "path": "", "source": None, "parts": parts, "asm_request": req,
                      "ann_key": ("asm_" + safe_name(str(asm["uid"]))) if asm.get("uid") else None,
                      "parts_list": pl, "parts_list_default": bool(req.get("parts_list", True)), "trails": trails,
                      "balloon_anchors": anchors}
        for k in [k for k in CACHE if k[0] and k[0][0] == fid]:
            CACHE.pop(k, None)
    return jsonify({"files": [_file_info(fid)], "errors": []})


def cleanup():
    shutil.rmtree(WORK_DIR, ignore_errors=True)


# --------------------------------------------------------------------------- analysis (CalculiX)

ANALYSIS_JOBS = {}      # job id -> {"state", "stage", "message", "error", "result", "name", "proc"}


def _fea_doc_path(name):
    return os.path.join(ASM_DIR, safe_name(name) + ".fea.json")


def _fea_workdir(name):
    return os.path.join(FEA_DIR, safe_name(name))


def _fea_asm(doc):
    """Assembly of the analysis geometry: the saved assembly, or one component for a part."""
    src = doc.get("source") or {}
    if not src.get("name"):
        return {"components": []}
    if src.get("type") == "part":
        return {"components": [{"id": "1", "name": src.get("name"), "source": {"type": "part", "name": src.get("name")},
                                "pos": [0, 0, 0], "rot": [0, 0, 0]}]}
    with open(_asm_path(src.get("name") or ""), "r", encoding="utf-8") as f:
        return json.load(f)


def _ccx_path():
    try:
        cfg = load_config()
    except (OSError, ValueError):
        cfg = {}
    return analysis.find_ccx((cfg.get("ccx_path") or "").strip())


@app.route("/api/analysis/list", methods=["GET"])
def fea_list():
    names = []
    if os.path.isdir(ASM_DIR):
        names = sorted(n[:-len(".fea.json")] for n in os.listdir(ASM_DIR) if n.endswith(".fea.json"))
    return jsonify(names)


@app.route("/api/analysis/file/<name>", methods=["GET"])
def fea_get(name):
    try:
        with open(_fea_doc_path(name), "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except (OSError, ValueError) as e:
        return error("cannot read analysis %s: %s" % (name, e), 404)


@app.route("/api/analysis/file/<name>", methods=["PUT"])
def fea_put(name):
    a = request.get_json(force=True)
    if not isinstance(a, dict) or "source" not in a:
        return error("analysis object expected")
    os.makedirs(ASM_DIR, exist_ok=True)
    tmp = _fea_doc_path(name) + _tmp_ext()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(a, f)
    _replace(tmp, _fea_doc_path(name))
    return jsonify({"ok": True, "path": _fea_doc_path(name)})


@app.route("/api/analysis/plates", methods=["POST"])
def fea_plates():
    """View data of the plate items of an analysis (as assembly components, global coordinates)."""
    doc = (request.get_json(force=True) or {}).get("analysis") or {}
    try:
        asm = _fea_asm(doc)
    except (OSError, ValueError) as e:
        return error("geometry: %s" % e)
    return jsonify({"plates": analysis.plate_views(doc, asm, _asm_sources())})


@app.route("/api/analysis/solver", methods=["GET"])
def fea_solver():
    try:
        cfg = load_config()
    except (OSError, ValueError):
        cfg = {}
    return jsonify({"configured": cfg.get("ccx_path") or "", "path": _ccx_path()})


@app.route("/api/analysis/solver", methods=["PUT"])
def fea_solver_set():
    req = request.get_json(force=True)
    cfg = load_config()
    cfg["ccx_path"] = (req.get("path") or "").strip().strip('"')
    save_config(cfg)
    return fea_solver()


@app.route("/api/analysis/sections", methods=["POST"])
def fea_sections():
    """Section properties {A, Ia, Ib, J, c1, c2} of a section, or the error."""
    req = request.get_json(force=True)
    try:
        p = analysis.section_props(req.get("section") or {})
        return jsonify({"props": p, "label": analysis.section_label(req.get("section") or {})})
    except analysis.AnalysisError as e:
        return jsonify({"error": str(e)})


class _Progress(object):
    def __init__(self, job):
        self.job = job
        self.proc = None

    def __call__(self, stage, message=""):
        self.job["stage"], self.job["message"] = stage, message

    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
        if k == "proc" and v is not None:
            self.job["proc"] = v


@app.route("/api/analysis/run", methods=["POST"])
def fea_run():
    """{"name", "analysis", "mesh_only"} -> {"job"}; the job runs in a thread (GET /api/analysis/job/<id>)."""
    req = request.get_json(force=True)
    doc = req.get("analysis") or {}
    name = safe_name(req.get("name") or doc.get("name") or "analysis")
    mesh_only = bool(req.get("mesh_only"))
    for j in ANALYSIS_JOBS.values():
        if j["name"] == name and j["state"] == "running":
            return error("analysis %s is already running" % name)
    jid = uuid.uuid4().hex[:10]
    job = {"state": "running", "stage": "start", "message": "", "error": None, "result": None, "name": name,
           "proc": None, "started": time_now(), "mesh_only": mesh_only}
    ANALYSIS_JOBS[jid] = job
    src = _asm_sources()
    ccx = _ccx_path()
    workdir = _fea_workdir(name) + ("_mesh" if mesh_only else "")
    meta = {"name": name, "project": PROJECTS.current_name() or "-",
            "source": "%s %s" % ((doc.get("source") or {}).get("type") or "assembly", (doc.get("source") or {}).get("name") or ""),
            "date": time_now()}

    def work():
        try:
            asm = _fea_asm(doc)
            prog = _Progress(job)
            res = analysis.run(doc, asm, src, workdir, ccx, progress=prog, mesh_only=mesh_only, meta=meta)
            res["name"], res["time"], res["mesh_only"] = name, time_now(), mesh_only
            if not mesh_only:
                import gzip
                with gzip.open(os.path.join(workdir, "results.json.gz"), "wt", encoding="utf-8") as f:
                    json.dump(res, f)
            job["result"] = res
            job["state"] = "done"
        except analysis.AnalysisError as e:
            job["error"], job["state"] = str(e), "error"
        except Exception as e:
            traceback.print_exc()
            job["error"], job["state"] = "%s: %s" % (e.__class__.__name__, e), "error"
        finally:
            job["proc"] = None
            if job.get("cancelled"):
                job["state"], job["error"] = "error", "cancelled"
    threading.Thread(target=work, daemon=True).start()
    return jsonify({"job": jid})


def time_now():
    import time as _t
    return _t.strftime("%Y-%m-%d %H:%M:%S")


@app.route("/api/analysis/job/<jid>", methods=["GET"])
def fea_job(jid):
    j = ANALYSIS_JOBS.get(jid)
    if j is None:
        return error("unknown job", 404)
    out = {k: j[k] for k in ("state", "stage", "message", "error", "name", "started")}
    if j["state"] == "done":
        out["result"] = j["result"]
        ANALYSIS_JOBS.pop(jid, None)
    elif j["state"] == "error":
        ANALYSIS_JOBS.pop(jid, None)
    return jsonify(out)


@app.route("/api/analysis/cancel/<jid>", methods=["POST"])
def fea_cancel(jid):
    j = ANALYSIS_JOBS.get(jid)
    if j is None:
        return error("unknown job", 404)
    j["cancelled"] = True
    p = j.get("proc")
    if p is not None:
        try:
            p.kill()
        except Exception:
            pass
    return jsonify({"ok": True})


@app.route("/api/analysis/results/<name>", methods=["GET"])
def fea_results(name):
    import gzip
    p = os.path.join(_fea_workdir(name), "results.json.gz")
    if not os.path.isfile(p):
        return jsonify({})
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/analysis/report/<name>", methods=["GET"])
def fea_report(name):
    d = _fea_workdir(name)
    fn = safe_name(name) + "_report.txt"
    p = os.path.join(d, fn)
    if not os.path.isfile(p):
        return error("no report for %s" % name, 404)
    return send_file(p, mimetype="text/plain", as_attachment=bool(request.args.get("download")), download_name=fn)


@app.route("/api/analysis/open_folder", methods=["POST"])
def fea_open_folder():
    req = request.get_json(force=True)
    path = _fea_workdir(req.get("name") or "analysis")
    os.makedirs(path, exist_ok=True)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        return error("cannot open %s: %s" % (path, e))
    return jsonify({"ok": True, "path": path})



# --------------------------------------------------------------------------- CAM

CAM_DIR = _Dir("cam")        # G-code files of the open project


def _cam_doc_path(name):
    return os.path.join(ASM_DIR, safe_name(name) + ".cam.json")


def _cam_tools():
    """Tool bit library (config.json "cam_tools"; the default tools when none is saved)."""
    t = load_config().get("cam_tools")
    bits = t if isinstance(t, list) and t else [dict(x) for x in cam.DEFAULT_TOOLS]
    return [cam.normalize_tool(b) for b in bits]


def _cam_shape(doc, placed=True):
    """(solid of the source part of a CAM document moved by the model placement (placed False: as in the part),
    cache key of the part file and the placement)."""
    src = doc.get("source") or {}
    if not src.get("name"):
        raise ValueError("no part is chosen")
    path = _part_path(src["name"])
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    p = part.migrate(json.loads(raw))
    shape, st = part.build(p)
    if shape is None:
        raise ValueError("the part %s has no solid" % src["name"])
    key = "%s:%s" % (src["name"], hashlib.sha1(raw.encode("utf-8")).hexdigest())
    st = doc.get("stock") or {}
    if st.get("kind") == "step":
        try:
            sp = cam.job.step_path(st)
            fs = os.stat(sp)
            key += ":stock:%s:%s:%s" % (sp, fs.st_mtime, fs.st_size)
        except (OSError, ValueError):
            pass
    if placed:
        pk = cam.placement.key(doc.get("placement"))
        if pk:
            shape = cam.placement.apply(shape, doc.get("placement"))
            key += ":" + pk
    return shape, key


def _cam_step_path(p):
    """A stock STEP path: absolute as it is, relative in the STEP folder of the open project."""
    if os.path.isabs(p):
        return p
    try:
        return os.path.join(PROJECTS.dirs().step, p)
    except Exception:
        return p


cam.job.RESOLVE_PATH = _cam_step_path


def _cam_part_sketch(name, fid):
    """A sketch of a part (its sketch feature fid) as a sketch record with "plane": {"o", "u", "v"} (the sketch plane
    in part coordinates; principal planes with their offset, plane features, faces and normal planes resolved by a
    build of the part)."""
    with open(_part_path(name), "r", encoding="utf-8") as f:
        p = part.migrate(json.loads(f.read()))
    feats = part.normalize(p)
    f = next((x for x in feats if x.get("id") == fid), None)
    if f is None or not f.get("sketch"):
        raise ValueError("the sketch %s of the part %s is not found" % (fid, name))
    if f.get("plane") in ("normal", "datum", "face"):
        dts, bodies = {}, {}
        shape, _ = part.build(p, datums=dts, surfaces=bodies)
        part.resolve_plane(f, shape, bodies, dts)
    pl = part.plane_of(f)
    rec = dict(f["sketch"])
    rec["name"] = "%s: %s" % (name, f.get("name") or fid)
    rec["plane"] = {"o": [pl.origin.X, pl.origin.Y, pl.origin.Z], "u": [pl.x_dir.X, pl.x_dir.Y, pl.x_dir.Z],
                    "v": [pl.y_dir.X, pl.y_dir.Y, pl.y_dir.Z]}
    return rec


def _cam_prepare(doc):
    """The document in the current form with the sketch records of the Engrave and Vcarve operations loaded
    from the project ({"sketch": {"name"}} -> the saved sketch; {"sketch": {"part", "feature"}} -> the sketch of a
    part feature with its plane)."""
    d = cam.migrate(doc)
    for op in d.get("operations") or []:
        sk = op.get("sketch")
        if isinstance(sk, dict) and sk.get("part") and sk.get("feature") and "entities" not in sk:
            try:
                op["sketch"] = _cam_part_sketch(sk["part"], sk["feature"])
            except (OSError, ValueError) as e:
                op["sketch"] = {"name": sk.get("feature"), "error": "the part sketch cannot be read: %s" % e}
            continue
        if isinstance(sk, dict) and sk.get("name") and "entities" not in sk:
            try:
                with open(_sketch_path(sk["name"]), "r", encoding="utf-8") as f:
                    rec = json.load(f)
                rec["name"] = sk["name"]
                op["sketch"] = rec
            except (OSError, ValueError) as e:
                op["sketch"] = {"name": sk["name"], "error": "the sketch %s cannot be read: %s" % (sk["name"], e)}
    return d


def _view_mesh(shape, keys=False):
    if shape is None:
        return None
    m = part.mesh(shape)
    out = {"vertices": m["vertices"], "triangles": m["triangles"], "edges": m["edges"], "bbox": m["bbox"]}
    if keys:
        out["face_keys"] = m["face_keys"]
        out["face_of_tri"] = m["face_of_tri"]
        out["edge_keys"] = m["edge_keys"]
    return out


@app.route("/api/cam/list", methods=["GET"])
def cam_list():
    names = []
    if os.path.isdir(ASM_DIR):
        names = sorted(n[:-len(".cam.json")] for n in os.listdir(ASM_DIR) if n.endswith(".cam.json"))
    return jsonify(names)


@app.route("/api/cam/file/<name>", methods=["GET"])
def cam_get(name):
    """The saved document in the current form (cam.migrate)."""
    try:
        with open(_cam_doc_path(name), "r", encoding="utf-8") as f:
            return jsonify(cam.migrate(json.load(f)))
    except (OSError, ValueError) as e:
        return error("cannot read CAM document %s: %s" % (name, e), 404)


@app.route("/api/cam/file/<name>", methods=["PUT"])
def cam_put(name):
    a = request.get_json(force=True)
    if not isinstance(a, dict) or "operations" not in a:
        return error("CAM document expected")
    os.makedirs(ASM_DIR, exist_ok=True)
    tmp = _cam_doc_path(name) + _tmp_ext()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(a, f)
    _replace(tmp, _cam_doc_path(name))
    return jsonify({"ok": True, "path": _cam_doc_path(name)})


@app.route("/api/cam/meta", methods=["GET"])
def cam_meta():
    """Names of the operation types, the tool shapes, the setup sheet defaults, the workpiece and tool materials
    and the post-processors."""
    return jsonify({"op_names": cam.OP_NAMES, "shapes": cam.SHAPE_NAMES, "setup": cam.DEFAULT_SETUP,
                    "materials": cam.feeds.materials(), "tool_materials": cam.feeds.TOOL_MATERIALS,
                    "posts": [{"id": k, "name": v} for k, v in cam.POSTS.items()], "supplemental": list(cam.SUPPLEMENTAL),
                    "derived": list(cam.DERIVED)})


@app.route("/api/cam/tools", methods=["GET"])
def cam_tools_get():
    return jsonify(_cam_tools())


@app.route("/api/cam/tool_profile", methods=["POST"])
def cam_tool_profile():
    """Half profile of a tool bit for the bit editor: {"bit": tool bit} -> {"cut": [[r, z]...], "body": [[r, z]...],
    "d", "height" (cutting), "length" (mm)} or {"error": text}."""
    b = (request.get_json(force=True) or {}).get("bit") or {}
    try:
        t = cam.tools.normalize(b)
        cut, body = cam.tools.tool_profile(t)
        return jsonify({"cut": [[round(r, 4), round(z, 4)] for r, z in cut], "body": [[round(r, 4), round(z, 4)] for r, z in body],
                        "d": round(2 * max(r for r, z in cut), 4), "height": round(cut[-1][1], 4), "length": round(body[-1][1], 4)})
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)})


@app.route("/api/cam/library", methods=["GET"])
def cam_library():
    """The standard tool library (tools.library): [tool bit with "group"]."""
    return jsonify(cam.tools.library())


CAM_MACHINE = {"travel_x": 600.0, "travel_y": 400.0, "travel_z": 100.0, "table_x": 700.0, "table_y": 500.0, "table_t": 20.0,
               "home_x": 50.0, "home_y": 50.0, "tip_top": 110.0, "gantry_clear": 130.0, "spindle_d": 80.0, "spindle_len": 200.0}


@app.route("/api/cam/machine", methods=["GET"])
def cam_machine_get():
    """The machine model of the CAM tab (config.json "cam_machine"): travels, table, the table position of X 0 Y 0
    of the travel, the tool tip height at the top of the Z travel, gantry clearance, spindle size (mm)."""
    m = dict(CAM_MACHINE)
    m.update({k: v for k, v in (load_config().get("cam_machine") or {}).items() if k in CAM_MACHINE})
    return jsonify(m)


@app.route("/api/cam/machine", methods=["PUT"])
def cam_machine_put():
    m = request.get_json(force=True)
    if not isinstance(m, dict):
        return error("machine record expected")
    out = {}
    for k, d in CAM_MACHINE.items():
        try:
            out[k] = float(m.get(k, d))
        except (TypeError, ValueError):
            return error("%s is not a number" % k)
    if min(out["travel_x"], out["travel_y"], out["travel_z"], out["table_x"], out["table_y"]) <= 0:
        return error("travels and table size must be above 0")
    cfg = load_config()
    cfg["cam_machine"] = out
    save_config(cfg)
    return jsonify(out)


@app.route("/api/cam/posts", methods=["GET"])
def cam_posts():
    """G-code post-processors: [{"id", "name"}]."""
    return jsonify([{"id": k, "name": v} for k, v in cam.POSTS.items()])


@app.route("/api/cam/tools", methods=["PUT"])
def cam_tools_put():
    """[tool bit, ...] saved to config.json "cam_tools"; each bit is checked (tool_profile)."""
    tools = request.get_json(force=True)
    if not isinstance(tools, list):
        return error("tool list expected")
    ids = set()
    out = []
    for t in tools:
        if not isinstance(t, dict) or not str(t.get("id") or "").strip():
            return error("every tool needs an id")
        t["id"] = str(t["id"]).strip()
        if t["id"] in ids:
            return error("tool id %s is used twice" % t["id"])
        ids.add(t["id"])
        try:
            t = cam.normalize_tool(t)
            cam.check_tool(t)
        except ValueError as e:
            return error(str(e))
        out.append(t)
    cfg = load_config()
    cfg["cam_tools"] = out
    save_config(cfg)
    return jsonify(out)


@app.route("/api/cam/geometry", methods=["POST"])
def cam_geometry():
    """View mesh of the source part of a CAM document with the face and edge keys, the kind of every face and the
    undercut faces: {"cam": doc}."""
    doc = (request.get_json(force=True) or {}).get("cam") or {}
    try:
        shape, skey = _cam_shape(doc)
        m = _view_mesh(shape, keys=True)
        try:
            with open(_part_path((doc.get("source") or {}).get("name", "")), "rb") as f:
                m["part_key"] = hashlib.sha1(f.read()).hexdigest()
        except OSError:
            m["part_key"] = ""
        under = []
        keys = [part.face_key(fc) for fc, _ in cam.undercut_faces(shape)]
        for i, k in enumerate(m["face_keys"]):
            if k and any(math.dist(k["c"], u["c"]) < 1e-3 for u in keys):
                under.append(i)
        m["undercuts"] = under
        m["face_kind"] = cam.face_kinds(shape, under)
        m["volume_mm3"] = round(shape.volume, 3)
        try:
            with open(_part_path((doc.get("source") or {}).get("name", "")), "r", encoding="utf-8") as f:
                prec = part.migrate(json.loads(f.read()))
            m["part_sketches"] = [{"id": x.get("id"), "name": x.get("name") or x.get("id"), "plane": x.get("plane", "XY"),
                                   "offset": x.get("offset", 0)} for x in prec.get("features") or [] if x.get("type") == "sketch"]
        except (OSError, ValueError):
            m["part_sketches"] = []
        m["bbox"] = cam._bbox(shape)
        return jsonify(m)
    except Exception as e:
        traceback.print_exc()
        return error("geometry failed: %s" % e, 400)


@app.route("/api/cam/setup", methods=["POST"])
def cam_setup():
    """Stock and machine zero of a CAM document: {"cam": doc} -> {"stock_bbox", "part_bbox", "origin", "clearance_z",
    "stock_mesh" (STEP stock: the view mesh of the stock before the first operation)}."""
    doc = (request.get_json(force=True) or {}).get("cam") or {}
    try:
        doc = cam.migrate(doc)
        shape, _ = _cam_shape(doc)
        stock0 = cam.stock_solid(doc, shape)
        bb = cam._bbox(stock0)
        out = {"stock_bbox": bb, "part_bbox": cam._bbox(shape), "origin": cam.origin_of(doc, bb),
               "clearance_z": bb[5] + cam._f((doc.get("setup") or {}).get("clearance_offset"), 5.0)}
        if (doc.get("stock") or {}).get("kind") == "step":
            out["stock_mesh"] = _view_mesh(stock0)
        return jsonify(out)
    except Exception as e:
        traceback.print_exc()
        return error("setup failed: %s" % e, 400)


_CAM_PREVIEW = {}                  # client id -> number of its latest preview run
_CAM_PREVIEW_LOCK = threading.Lock()


def _cam_run(doc, upto=None, cancel=None):
    """(document, shape, bits, result) of a run; the operations before upto come from the cache of the job module."""
    d = _cam_prepare(doc)
    shape, key = _cam_shape(d)
    bits = _cam_tools()
    res = cam.run(d, shape, bits, upto=upto, shape_key=key, cancel=cancel)
    return d, shape, bits, res


@app.route("/api/cam/part_state", methods=["POST"])
def cam_part_state():
    """State of the source part file of a CAM document without a build: {"cam": doc} -> {"key": sha1 of the part
    file, "mtime"}; the client compares the key with the key of the loaded geometry."""
    doc = (request.get_json(force=True) or {}).get("cam") or {}
    src = doc.get("source") or {}
    if not src.get("name"):
        return jsonify({"key": "", "mtime": 0})
    try:
        path = _part_path(src["name"])
        with open(path, "rb") as f:
            raw = f.read()
        return jsonify({"key": hashlib.sha1(raw).hexdigest(), "mtime": os.path.getmtime(path)})
    except OSError as e:
        return error("cannot read the part %s: %s" % (src["name"], e), 404)


@app.route("/api/cam/placement", methods=["POST"])
def cam_placement():
    """Model placement: {"cam": doc, "drag": {"delta"} (optional)} -> the solve of the placement constraints {"pos",
    "rot", "constraints", "messages", "unsatisfied", "flipped"}; {"cam": doc, "suggest": {"face": index | "edge":
    point | "vertex": point (job coordinates), "type"}} -> {"datum", "flip", "value", "kind", ...} of a new
    constraint."""
    req = request.get_json(force=True) or {}
    doc = cam.migrate(req.get("cam") or {})
    try:
        shape, _ = _cam_shape(doc, placed=False)
        if req.get("suggest") is not None:
            sg = req["suggest"] or {}
            return jsonify(cam.placement.suggest(doc.get("placement"), shape, sg.get("face"), sg.get("type") or "coincident",
                                                 edge=sg.get("edge"), vertex=sg.get("vertex")))
        return jsonify(cam.placement.solve(doc.get("placement"), shape, drag=req.get("drag")))
    except Exception as e:
        traceback.print_exc()
        return error("placement failed: %s" % e, 400)


@app.route("/api/cam/measure", methods=["POST"])
def cam_measure():
    """Measurement in a CAM job (the placed part, job coordinates): {"cam": doc, "items": [{"face": index} | {"edge":
    index} (shape.faces() / shape.edges() order of the placed part) | {"vertex": [x, y, z]} | {"ref": "zero" |
    "stock_top" | "stock_bottom"}]} -> measure.measure (rows, closest points) with "items" (labels) and "origin" (the
    machine zero); one item: its point or centre in machine coordinates as well."""
    req = request.get_json(force=True) or {}
    doc = cam.migrate(req.get("cam") or {})
    try:
        shape, _ = _cam_shape(doc)
        stock0 = cam.stock_solid(doc, shape)
        sb = cam._bbox(stock0)
        origin = cam.origin_of(doc, sb)
        items = []
        for it in (req.get("items") or [])[:2]:
            if it.get("face") is not None:
                fs = shape.faces()
                fi = int(it["face"])
                if not 0 <= fi < len(fs):
                    return error("face not found", 400)
                items.append(measure.item_from_face(fs[fi], "face %d" % (fi + 1)))
            elif it.get("edge") is not None:
                es = shape.edges()
                ei = int(it["edge"])
                if not 0 <= ei < len(es):
                    return error("edge not found", 400)
                items.append(measure.item_from_edge(es[ei], "edge %d" % (ei + 1)))
            elif it.get("vertex") is not None:
                items.append(measure.item_from_point(it["vertex"], "vertex"))
            elif it.get("ref") == "zero":
                x = measure.item_from_point(origin, "machine zero")
                items.append(x)
            elif it.get("ref") in ("stock_top", "stock_bottom"):
                top = it["ref"] == "stock_top"
                c = [(sb[0] + sb[3]) / 2, (sb[1] + sb[4]) / 2, sb[5] if top else sb[2]]
                items.append({"kind": "plane", "name": "Stock top" if top else "Stock bottom", "c": c, "n": [0, 0, 1 if top else -1], "shape": None})
            else:
                return error("unknown measure item", 400)
        if not items:
            return error("nothing picked", 400)
        res = measure.measure(items[0], items[1] if len(items) > 1 else None)
        if len(items) == 1 and items[0].get("shape") is not None:
            c = items[0]["c"]
            what = "Point" if items[0]["kind"] == "point" else "Midpoint" if items[0]["kind"] in ("line", "other") and items[0].get("edge") else "Centre"
            res["rows"].append([what + ", machine coordinates", measure.vec([c[i] - origin[i] for i in range(3)])])
        res["items"] = [measure.label(x) for x in items]
        res["origin"] = origin
        return jsonify(res)
    except Exception as e:
        traceback.print_exc()
        return error("measure failed: %s" % e, 400)


@app.route("/api/cam/feeds", methods=["POST"])
def cam_feeds():
    """Feeds and speeds: {"cam": doc, "tc": tool controller id | "bit": tool bit id, "ae", "ap" (mm), "material"
    (default: the stock material of the job)} -> feeds.calc."""
    req = request.get_json(force=True) or {}
    doc = cam.migrate(req.get("cam") or {})
    try:
        bid = req.get("bit")
        if req.get("tc"):
            tc = next((t for t in doc.get("tools") or [] if t.get("id") == req["tc"]), None)
            if tc is None:
                return error("no tool controller %s" % req["tc"])
            bid = tc.get("bit")
        bit = next((b for b in _cam_tools() if b.get("id") == bid), None)
        if bit is None:
            return error("the tool %s is not in the tool table" % bid)
        mat = req.get("material") or (doc.get("stock") or {}).get("material")
        if not mat:
            return error("no workpiece material: set the material of the stock")
        return jsonify(cam.feeds.calc(bit, mat, doc.get("setup"), req.get("ae"), req.get("ap")))
    except ValueError as e:
        return error(str(e))


@app.route("/api/cam/run", methods=["POST"])
def cam_run():
    """Toolpaths and the stock after the operations: {"cam": doc, "upto": index or null, "meshes": true} ->
    {"operations", "stock_mesh", "stock0_bbox", "clearance_z", "origin", "left_mm3", "gone_mm3", "left_mesh",
    "sanity"}. "preview": client id: a later preview of the same client stops this run before its next operation
    ({"cancelled": true})."""
    req = request.get_json(force=True) or {}
    doc = req.get("cam") or {}
    upto = req.get("upto")
    cancel = None
    cid = req.get("preview")
    if cid:
        with _CAM_PREVIEW_LOCK:
            gen = _CAM_PREVIEW[cid] = _CAM_PREVIEW.get(cid, 0) + 1
        cancel = lambda: _CAM_PREVIEW.get(cid) != gen
    try:
        d, shape, bits, res = _cam_run(doc, int(upto) if upto is not None else None, cancel=cancel)
        out = {"operations": res["operations"], "stock0_bbox": cam._bbox(res["stock0"]), "clearance_z": res["clearance_z"],
               "origin": res["origin"], "sanity": cam.sanity(d, shape, bits, res)}
        if req.get("meshes", True):
            left_v, gone_v, left = cam.remaining(res["stock"], shape)
            out.update({"stock_mesh": _view_mesh(res["stock"]), "left_mm3": round(left_v, 3), "gone_mm3": round(gone_v, 3),
                        "left_mesh": _view_mesh(left) if left is not None else None})
        return jsonify(out)
    except cam.job.Cancelled:
        return jsonify({"cancelled": True})
    except Exception as e:
        traceback.print_exc()
        return error("CAM run failed: %s" % e, 400)


@app.route("/api/cam/cancel", methods=["POST"])
def cam_cancel():
    """Stop the running preview of a client before its next operation: {"preview": client id}."""
    cid = (request.get_json(force=True) or {}).get("preview")
    if cid:
        with _CAM_PREVIEW_LOCK:
            _CAM_PREVIEW[cid] = _CAM_PREVIEW.get(cid, 0) + 1
    return jsonify({"ok": True})


@app.route("/api/cam/sanity", methods=["POST"])
def cam_sanity():
    """Sanity check of the job without a run: {"cam": doc} -> [{"level", "text"}]."""
    doc = (request.get_json(force=True) or {}).get("cam") or {}
    try:
        d = _cam_prepare(doc)
        shape = None
        try:
            shape, _ = _cam_shape(d)
        except Exception:
            shape = None
        return jsonify(cam.sanity(d, shape, _cam_tools(), None))
    except Exception as e:
        traceback.print_exc()
        return error("sanity check failed: %s" % e, 400)


@app.route("/api/cam/template", methods=["POST"])
def cam_template():
    """Job template of the document: {"cam": doc} -> the template; {"cam": doc, "apply": template} -> the document
    with the template applied."""
    req = request.get_json(force=True) or {}
    doc = req.get("cam") or {}
    try:
        if req.get("apply") is not None:
            tpl = req["apply"]
            if not isinstance(tpl, dict) or tpl.get("format") != "shinycad-cam-template":
                return error("not a ShinyCAD CAM template")
            return jsonify(cam.apply_template(doc, tpl))
        return jsonify(cam.template(doc))
    except Exception as e:
        traceback.print_exc()
        return error("template failed: %s" % e, 400)


@app.route("/api/cam/gcode", methods=["POST"])
def cam_gcode():
    """G-code of the operations: {"cam": doc, "folder": output folder (empty: the project cam folder; "-": download),
    "overwrite", "inspect": index (the text of one operation returned as {"text"}), "post"} -> {"written": [path]}
    or the file."""
    req = request.get_json(force=True) or {}
    doc = req.get("cam") or {}
    inspect = req.get("inspect")
    try:
        d, shape, bits, res = _cam_run(doc, int(inspect) if inspect is not None else None)
        bad = [o for o in res["operations"] if not o.get("ok")]
        if bad and inspect is None:
            return error("operation %s: %s" % (bad[0].get("name") or bad[0].get("id"), "; ".join(bad[0].get("errors") or ["failed"])))
        text = cam.gcode(d, res, bits, post=req.get("post") or None, only=int(inspect) if inspect is not None else None)
    except Exception as e:
        traceback.print_exc()
        return error("G-code failed: %s" % e, 400)
    if inspect is not None:
        return jsonify({"text": text, "lines": len(text.splitlines())})
    out = d.get("output") or {}
    name = safe_name(out.get("name") or d.get("name") or "cam")
    if not name.lower().endswith((".nc", ".gcode", ".tap", ".ngc")):
        name += ".nc"
    folder = (req.get("folder") or out.get("folder") or "").strip().strip('"')
    if folder == "-":
        return send_file(io.BytesIO(text.encode("utf-8")), as_attachment=True, download_name=name)
    folder = folder or (str(CAM_DIR) if PROJECTS.current_name() else "")
    if not folder:
        return send_file(io.BytesIO(text.encode("utf-8")), as_attachment=True, download_name=name)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    if os.path.exists(path) and not req.get("overwrite"):
        return jsonify({"exists": path}), 409
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return jsonify({"written": [path], "lines": len(text.splitlines())})


@app.route("/api/cam/open_folder", methods=["POST"])
def cam_open_folder():
    """Opens the G-code folder of the open project in Explorer."""
    folder = str(CAM_DIR) if PROJECTS.current_name() else ""
    if not folder:
        return error("no project is open")
    os.makedirs(folder, exist_ok=True)
    try:
        if sys.platform.startswith("win"):
            os.startfile(folder)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception as e:
        return error("cannot open %s: %s" % (folder, e))
    return jsonify({"ok": True, "path": folder})


from .explicit import routes as _explicit_routes      # noqa: E402
EXPLICIT = _explicit_routes.register(sys.modules[__name__])
