# -*- coding: utf-8 -*-
"""Document files: one zip file per document (.scpart, .scasm, .scsketch, .scfea, .scexp).

A package holds the document (document.json), its drawing annotations and layouts (annotations/), the sketch images
it uses (images/), the CAD files it references (step_import/) and, for an assembly or an analysis, packages of the
documents it uses (uses/). shinycad.json gives the format, type, name and save time.

In a project the packages are kept in the project folder next to project.json. work/ holds the unpacked documents the
program works on. sync() writes a package after a document changed in work/ and unpacks a package that was changed,
copied in or deleted outside the program. work/.packages.json records the state of each package at the last sync.
A document can also be linked to a package outside the project (opened from or saved to another folder); that file
is written along with the project package."""
import io
import json
import os
import shutil
import time
import uuid
import zipfile

PKG_EXT = {"part": ".scpart", "sketch": ".scsketch", "assembly": ".scasm", "analysis": ".scfea", "explicit": ".scexp"}
EXT_TYPE = {v: k for k, v in PKG_EXT.items()}
CAD_EXT = (".step", ".stp", ".stl", ".iges", ".igs", ".brep")
FORMAT = "shinycad-package"
VERSION = 1
ANN_SUFFIX = (".json", ".layout.json", ".sketch.json")
STATE_FILE = ".packages.json"
SETTLE_S = 1.0          # a document is packed when its files are unchanged for this time


def doc_name(s):
    """Document name of a file name (as the tabs name their files: letters, digits, _ - .)."""
    import re
    return re.sub(r"[^A-Za-z0-9_\-.]+", "_", str(s or "")).strip("_") or "untitled"


def pkg_type(path):
    """Document type of a package path (by extension), or None."""
    return EXT_TYPE.get(os.path.splitext(str(path or ""))[1].lower())


def pkg_name(dname, dtype):
    from .projects import safe_name
    return safe_name(dname) + PKG_EXT[dtype]


# ---------------------------------------------------------------------------------------------- file sets
def _walk_strings(v, fn):
    """Calls fn(s) for every string in v; a non-None return value replaces the string. Returns the new value."""
    if isinstance(v, dict):
        return {k: _walk_strings(x, fn) for k, x in v.items()}
    if isinstance(v, list):
        return [_walk_strings(x, fn) for x in v]
    if isinstance(v, str):
        r = fn(v)
        return v if r is None else r
    return v


def _cad_files(data):
    """Existing CAD files (STEP, STL, IGES, BREP) referenced by path anywhere in a document."""
    out = []

    def f(s):
        if s.lower().endswith(CAD_EXT) and ("/" in s or "\\" in s) and os.path.isfile(s) and s not in out:
            out.append(s)
    _walk_strings(data, f)
    return out


def _stems(dname, data):
    from .projects import safe_name
    st = {safe_name(dname)}
    if data.get("uid"):
        st.add(safe_name(data["uid"]))
    return st


def _ann_files(w, dname, data):
    ad = os.path.join(w, "annotations")
    if not os.path.isdir(ad):
        return []
    st = _stems(dname, data)
    return [os.path.join(ad, fn) for fn in sorted(os.listdir(ad)) if any(fn == s + suf for s in st for suf in ANN_SUFFIX)]


def _image_files(w, data):
    from .projects import Projects
    out = []
    for im in sorted(Projects._image_files(data)):
        p = os.path.join(w, "images", im)
        if os.path.isfile(p):
            out.append(p)
    return out


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_REFS = {}       # document path -> (mtime, size, (stems, images, CAD files)) of the last read


def doc_files(w, dtype, dname):
    """The files of a document in work/: [document, annotations..., images..., CAD files...]. The references of the
    document are read again only when the document file changed."""
    from .projects import TYPES, safe_name
    dp = os.path.join(w, safe_name(dname) + TYPES[dtype])
    st = os.stat(dp)
    c = _REFS.get(dp)
    if c is None or c[0] != st.st_mtime or c[1] != st.st_size:
        data = _load(dp)
        c = (st.st_mtime, st.st_size, (_stems(dname, data), sorted(Projects_image_names(data)), _cad_files(data)))
        _REFS[dp] = c
    stems, images, cad = c[2]
    ad = os.path.join(w, "annotations")
    anns = [os.path.join(ad, fn) for fn in sorted(os.listdir(ad)) if any(fn == s + suf for s in stems for suf in ANN_SUFFIX)] if os.path.isdir(ad) else []
    imgs = [p for p in (os.path.join(w, "images", im) for im in images) if os.path.isfile(p)]
    return [dp] + anns + imgs + [p for p in cad if os.path.isfile(p)]


def Projects_image_names(data):
    from .projects import Projects
    return Projects._image_files(data)


def fingerprint(w, dtype, dname):
    """[newest mtime, total size, number of files] of the files of a document in work/ (None: not readable)."""
    try:
        files = doc_files(w, dtype, dname)
        sts = [os.stat(p) for p in files]
    except (OSError, ValueError):
        return None
    return [round(max(s.st_mtime for s in sts), 3), sum(s.st_size for s in sts), len(sts)]


def _stat(path):
    try:
        s = os.stat(path)
        return [round(s.st_mtime, 3), s.st_size]
    except OSError:
        return None


# ---------------------------------------------------------------------------------------------- write
def _write_zip(z, w, dtype, dname, uses_of=None):
    from .projects import TYPES, safe_name
    dp = os.path.join(w, safe_name(dname) + TYPES[dtype])
    data = _load(dp)
    head = {"format": FORMAT, "version": VERSION, "type": dtype, "name": dname, "uid": data.get("uid", ""),
            "saved": time.strftime("%Y-%m-%d %H:%M:%S")}
    z.writestr("shinycad.json", json.dumps(head, indent=1))
    z.write(dp, "document.json")
    for p in _ann_files(w, dname, data):
        z.write(p, "annotations/" + os.path.basename(p))
    for p in _image_files(w, data):
        z.write(p, "images/" + os.path.basename(p), compress_type=zipfile.ZIP_STORED)
    for p in _cad_files(data):
        z.write(p, "step_import/" + os.path.basename(p), compresslevel=1)
    for t, n in (uses_of or []):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zu:
            _write_zip(zu, w, t, n)
        z.writestr("uses/" + pkg_name(n, t), buf.getvalue(), compress_type=zipfile.ZIP_STORED)


def write(projects, w, dtype, dname, dest):
    """Writes the package of the document dname in work folder w to dest (through a temporary file)."""
    uses = projects._uses(w, dtype, dname) if dtype in ("assembly", "analysis", "explicit") else []
    d = os.path.dirname(os.path.abspath(dest))
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "." + os.path.basename(dest) + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            _write_zip(z, w, dtype, dname, uses)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return dest


# ---------------------------------------------------------------------------------------------- read
def header(src):
    """shinycad.json of a package (path or file object)."""
    try:
        with zipfile.ZipFile(src) as z:
            h = json.loads(z.read("shinycad.json").decode("utf-8"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as e:
        raise ValueError("not a ShinyCAD document file: %s" % e)
    if h.get("format") != FORMAT or h.get("type") not in PKG_EXT:
        raise ValueError("not a ShinyCAD document file")
    return h


def _put_file(dst_dir, base, blob):
    """Writes blob as dst_dir/base; an existing different file keeps its name and blob goes to base_<n>. Returns the
    path written (or the existing equal file)."""
    os.makedirs(dst_dir, exist_ok=True)
    stem, ext = os.path.splitext(base)
    k = 0
    while True:
        p = os.path.join(dst_dir, base if k == 0 else "%s_%d%s" % (stem, k, ext))
        if not os.path.exists(p):
            with open(p, "wb") as f:
                f.write(blob)
            return p
        if os.path.getsize(p) == len(blob):
            with open(p, "rb") as f:
                if f.read() == blob:
                    return p
        k += 1


def extract(projects, pdir, src, dname=None, with_uses=True, overwrite=True):
    """Unpacks a package (path or file object) into the project folder pdir as document dname (default: the name in
    the package). Used documents in uses/ are unpacked only when the project has no document of that name.
    overwrite False: an existing document of that name is kept. Returns (type, name)."""
    from .projects import TYPES, safe_name
    h = header(src)
    dtype = h["type"]
    w = os.path.join(pdir, "work")
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        data = json.loads(z.read("document.json").decode("utf-8"))
        old = h.get("name") or data.get("name") or "untitled"
        dname = doc_name(dname or old)
        dp = os.path.join(w, dname + TYPES[dtype])
        if os.path.exists(dp) and not overwrite:
            return dtype, dname
        os.makedirs(w, exist_ok=True)
        data["name"] = dname
        old_uid = data.get("uid")
        if dtype == "part" and old_uid:
            # a part of another name with the same uid (a copy of the file): new uid, its drawing goes along
            for fn in os.listdir(w):
                if fn.endswith(TYPES["part"]) and fn != dname + TYPES["part"]:
                    try:
                        if _load(os.path.join(w, fn)).get("uid") == old_uid:
                            data["uid"] = uuid.uuid4().hex[:12]
                            break
                    except (OSError, ValueError):
                        pass
        repl = {}
        # sketch images
        for n in names:
            if n.startswith("images/") and not n.endswith("/"):
                base = n[len("images/"):]
                p = _put_file(os.path.join(w, "images"), base, z.read(n))
                if os.path.basename(p) != base:
                    repl[base] = os.path.basename(p)
        if repl:
            data = _walk_strings(data, lambda s: repl.get(s) or (os.path.join(os.path.dirname(s), repl[os.path.basename(s)])
                                                                 if ("/" in s or "\\" in s) and os.path.basename(s) in repl else None))
        # CAD files: to step_import/, references to the local copies
        cad = {}
        for n in names:
            if n.startswith("step_import/") and not n.endswith("/"):
                base = n[len("step_import/"):]
                cad[base.lower()] = _put_file(os.path.join(pdir, "step_import"), base, z.read(n))
        if cad:
            def fix(s):
                if s.lower().endswith(CAD_EXT) and ("/" in s or "\\" in s):
                    b = os.path.basename(s.replace("\\", "/")).lower()
                    if b in cad:
                        return cad[b]
                return None
            data = _walk_strings(data, fix)
        # annotations (by name or uid)
        stems_old = {safe_name(old): dname}
        if old_uid:
            stems_old[safe_name(old_uid)] = safe_name(data.get("uid") or old_uid)
        ad = os.path.join(w, "annotations")
        for n in names:
            if n.startswith("annotations/") and not n.endswith("/"):
                base = n[len("annotations/"):]
                for so, sn in stems_old.items():
                    suf = next((x for x in ANN_SUFFIX[::-1] if base == so + x), None)
                    if suf:
                        os.makedirs(ad, exist_ok=True)
                        with open(os.path.join(ad, sn + suf), "wb") as f:
                            f.write(z.read(n))
                        break
        # used documents
        if with_uses:
            for n in names:
                if n.startswith("uses/") and pkg_type(n):
                    extract(projects, pdir, io.BytesIO(z.read(n)), None, with_uses=False, overwrite=False)
    tmp = dp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, dp)
    return dtype, dname


# ---------------------------------------------------------------------------------------------- sync
def load_state(w):
    try:
        return _load(os.path.join(w, STATE_FILE))
    except (OSError, ValueError):
        return {}


def save_state(w, st):
    p = os.path.join(w, STATE_FILE)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, p)


def sync(projects, force=False, pack=True, only=None):
    """Synchronises the packages in the folder of the open project with work/. Returns {"packed": [...],
    "unpacked": [...], "deleted": [...]} with "type:name" keys. pack False: document files are only read, not
    written (the background thread of run.py writes them). only: the "type:name" keys written (None: all)."""
    from .projects import TYPES
    pname = projects.current_name()
    if not pname:
        return {"packed": [], "unpacked": [], "deleted": []}
    pdir = projects.project_dir(pname)
    w = os.path.join(pdir, "work")
    if not os.path.isdir(w):
        return {"packed": [], "unpacked": [], "deleted": []}
    st = load_state(w)
    out = {"packed": [], "unpacked": [], "deleted": []}
    now = time.time()
    work_docs = {}
    for fn in os.listdir(w):
        for t, ext in TYPES.items():
            if fn.endswith(ext):
                work_docs[t + ":" + fn[:-len(ext)]] = (t, fn[:-len(ext)])
    pkgs = {}
    for fn in os.listdir(pdir):
        t = pkg_type(fn)
        if t and not fn.startswith("."):
            stem = os.path.splitext(fn)[0]
            if doc_name(stem) != stem:
                # a file name the tabs cannot use (spaces, other characters): renamed
                new = doc_name(stem) + PKG_EXT[t]
                if os.path.exists(os.path.join(pdir, new)):
                    continue
                try:
                    os.rename(os.path.join(pdir, fn), os.path.join(pdir, new))
                except OSError:
                    continue
                stem = doc_name(stem)
            pkgs[t + ":" + stem] = (t, stem)
    changed = False
    # packages changed, copied in or deleted outside the program
    for key, (t, n) in list(pkgs.items()):
        path = os.path.join(pdir, pkg_name(n, t))
        rec = st.get(key) or {}
        cur = _stat(path)
        if key in work_docs and rec.get("pkg") == cur:
            continue
        if key in work_docs and rec.get("pkg") is None and not rec:
            # project from before packages, package of the same name made outside: the newer one is kept
            fp = fingerprint(w, t, n)
            if fp and cur and fp[0] >= cur[0]:
                continue
        try:
            if key in work_docs and rec.get("work") and fingerprint(w, t, n) != rec.get("work"):
                projects.snapshot(t, n, "before the change of %s outside the program" % os.path.basename(path))
            extract(projects, pdir, path, n)
        except (OSError, ValueError, zipfile.BadZipFile, KeyError):
            continue
        # with a linked file outside the project: written again (with the linked file) below
        rec.update({"pkg": cur, "work": None if rec.get("file") else fingerprint(w, t, n)})
        st[key] = rec
        work_docs[key] = (t, n)
        out["unpacked"].append(key)
        changed = True
    # linked files outside the project changed there
    for key, rec in list(st.items()):
        f = rec.get("file")
        if not f or key not in work_docs:
            continue
        cur = _stat(f)
        if cur is None:
            rec.pop("file", None)
            rec.pop("link", None)
            changed = True
            continue
        if cur != rec.get("link"):
            t, n = work_docs[key]
            try:
                extract(projects, pdir, f, n)
            except (OSError, ValueError, zipfile.BadZipFile, KeyError):
                continue
            rec["link"] = cur
            rec["work"] = None         # project package written below
            out["unpacked"].append(key)
            changed = True
    # documents whose package was deleted outside the program
    for key, (t, n) in list(work_docs.items()):
        rec = st.get(key)
        if rec and rec.get("pkg") and key not in pkgs:
            try:
                projects.delete_doc(t, n, packages=False)
            except (OSError, ValueError):
                continue
            st.pop(key, None)
            work_docs.pop(key)
            out["deleted"].append(key)
            changed = True
    # documents changed in work/ (or without a package): written
    for key, (t, n) in (work_docs.items() if pack else ()):
        if only is not None and key not in only:
            continue
        rec = st.setdefault(key, {})
        fp = fingerprint(w, t, n)
        if fp is None:
            continue
        if rec.get("pkg") and rec.get("work") == fp and key in pkgs:
            continue
        if not force and now - fp[0] < SETTLE_S:
            continue
        path = os.path.join(pdir, pkg_name(n, t))
        try:
            write(projects, w, t, n, path)
            if rec.get("file"):
                write(projects, w, t, n, rec["file"])
                rec["link"] = _stat(rec["file"])
        except (OSError, ValueError):
            continue
        rec["pkg"] = _stat(path)
        rec["work"] = fp
        out["packed"].append(key)
        changed = True
    for key in list(st):
        if key not in work_docs and pack:
            st.pop(key)
            changed = True
    if changed:
        save_state(w, st)
    return out


def forget_doc(pdir, dtype, dname, trash=True):
    """Removes the package of a document from the project folder (to trash/ when trash) and its sync record."""
    w = os.path.join(pdir, "work")
    p = os.path.join(pdir, pkg_name(dname, dtype))
    if os.path.isfile(p):
        if trash:
            td = os.path.join(pdir, "trash")
            os.makedirs(td, exist_ok=True)
            shutil.move(p, os.path.join(td, time.strftime("%Y%m%d_%H%M%S_") + os.path.basename(p)))
        else:
            os.remove(p)
    st = load_state(w)
    if st.pop(dtype + ":" + dname, None) is not None:
        save_state(w, st)


def rename_doc(pdir, dtype, old, new):
    w = os.path.join(pdir, "work")
    a, b = os.path.join(pdir, pkg_name(old, dtype)), os.path.join(pdir, pkg_name(new, dtype))
    st = load_state(w)
    rec = st.pop(dtype + ":" + old, None)
    if os.path.isfile(a) and not os.path.exists(b):
        os.rename(a, b)
    if rec is not None:
        rec["pkg"] = _stat(b)
        rec["work"] = None           # rewritten with the new name at the next sync
        st[dtype + ":" + new] = rec
    save_state(w, st)


def link(pdir, dtype, dname, path):
    """Links a document to a package file outside the project (written along with the project package)."""
    w = os.path.join(pdir, "work")
    st = load_state(w)
    rec = st.setdefault(dtype + ":" + dname, {})
    rec["file"] = os.path.abspath(path)
    rec["link"] = _stat(path)
    save_state(w, st)


def linked(pdir):
    """{"type:name": linked file path}."""
    return {k: r["file"] for k, r in load_state(os.path.join(pdir, "work")).items() if r.get("file")}
