"""Projects: a folder per project that holds the working documents (parts, sketches, assemblies,
drawing annotations), the exported drawings, the exported STEP and mesh files, local copies of imported STEP files,
document versions (snapshots) and saved project states.

<projects root>/<project>/
    project.json          name, description, created, document metadata (version, note), links
    work/                 *.part.json, *.sketch.json, *.asm.json, *.fea.json, *.exp.json
    work/annotations/     drawing annotations and view layouts (by part uid or file name)
    drawings/             exported PDF, DXF, SVG, FCStd
    step/                 exported STEP and mesh files
    step_import/          local copies of imported STEP files
    analysis/<name>/      analysis runs: CalculiX input and result files, report, results for the view
    explicit/<name>/      explicit analyses (OpenRadioss): model .inp, run folders with decks and results
    versions/             <name>.<type>.v<N>.json snapshots with <name>.<type>.v<N>.meta.json
    states/               saved project states (*.state.json)
    trash/                deleted documents
"""
import json
import os
import re
import shutil
import threading
import time

TYPES = {"part": ".part.json", "sketch": ".sketch.json", "assembly": ".asm.json", "analysis": ".fea.json",
         "explicit": ".exp.json"}
SUBDIRS = ("work", os.path.join("work", "annotations"), "drawings", "step", "step_import", "versions", "states", "trash",
           "analysis", "explicit")


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_\-. ]+", "_", str(s or "")).strip(" _.") or "untitled"


class Dirs(object):
    """Directories of the documents of the open project (or of the program folder when no project is open)."""
    def __init__(self, parts, sketches, assemblies, stacks, annotations, drawings=None, step=None, step_import=None,
                 analysis=None):
        self.parts, self.sketches, self.assemblies, self.stacks = parts, sketches, assemblies, stacks
        self.annotations, self.drawings, self.step, self.step_import = annotations, drawings, step, step_import
        self.analysis = analysis


class Projects(object):
    def __init__(self, app_dir, load_config, save_config):
        self.app_dir = app_dir
        self.load_config = load_config
        self.save_config = save_config

    # ------------------------------------------------------------------ settings
    def root(self):
        return (self.load_config().get("projects_root") or "").strip()

    def set_root(self, path):
        cfg = self.load_config()
        cfg["projects_root"] = path
        self.save_config(cfg)
        os.makedirs(path, exist_ok=True)

    def current_name(self):
        name = (self.load_config().get("current_project") or "").strip()
        return name if name and os.path.isfile(self.manifest_path(name)) else ""

    def set_current(self, name):
        cfg = self.load_config()
        cfg["current_project"] = name or ""
        self.save_config(cfg)

    # ------------------------------------------------------------------ folders
    def project_dir(self, name):
        return os.path.join(self.root(), safe_name(name))

    def manifest_path(self, name):
        return os.path.join(self.project_dir(name), "project.json")

    def dirs(self):
        """Dirs of the open project, or the legacy folders of the program when no project is open."""
        name = self.current_name()
        if not name:
            a = self.app_dir
            return Dirs(os.path.join(a, "parts"), os.path.join(a, "sketches"), os.path.join(a, "assemblies"),
                        os.path.join(a, "stacks"), os.path.join(a, "annotations"), analysis=os.path.join(a, "analysis"))
        p = self.project_dir(name)
        w = os.path.join(p, "work")
        return Dirs(w, w, w, w, os.path.join(w, "annotations"), os.path.join(p, "drawings"), os.path.join(p, "step"),
                    os.path.join(p, "step_import"), os.path.join(p, "analysis"))

    def ensure_dirs(self, name):
        for s in SUBDIRS:
            os.makedirs(os.path.join(self.project_dir(name), s), exist_ok=True)

    # ------------------------------------------------------------------ manifest
    def load_manifest(self, name):
        try:
            with open(self.manifest_path(name), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"name": name, "description": "", "created": "", "docs": {}}

    def save_manifest(self, name, m):
        path = self.manifest_path(name)
        tmp = path + ".%d.%d.tmp" % (os.getpid(), threading.get_ident())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=1)
        os.replace(tmp, path)

    # ------------------------------------------------------------------ projects
    def list_projects(self):
        root = self.root()
        out = []
        if not root or not os.path.isdir(root):
            return out
        for n in sorted(os.listdir(root)):
            mp = os.path.join(root, n, "project.json")
            if os.path.isfile(mp):
                try:
                    with open(mp, "r", encoding="utf-8") as f:
                        m = json.load(f)
                except (OSError, ValueError):
                    m = {}
                work = os.path.join(root, n, "work")
                ndocs = len([x for x in os.listdir(work) if x.endswith(".json")]) if os.path.isdir(work) else 0
                out.append({"name": n, "description": m.get("description", ""), "created": m.get("created", ""),
                            "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(mp))), "docs": ndocs})
        return out

    def create(self, name, description=""):
        if not self.root():
            raise ValueError("set the projects folder first")
        name = safe_name(name)
        if os.path.exists(self.project_dir(name)):
            raise ValueError("a project named %s exists" % name)
        self.ensure_dirs(name)
        self.save_manifest(name, {"name": name, "description": description or "", "created": time.strftime("%Y-%m-%d %H:%M"), "docs": {}})
        return name

    def open(self, name):
        if not os.path.isfile(self.manifest_path(name)):
            raise ValueError("project %s not found" % name)
        self.ensure_dirs(name)
        self.set_current(name)
        return name

    def close(self):
        self.set_current("")

    def update(self, name, description=None):
        m = self.load_manifest(name)
        if description is not None:
            m["description"] = description
        self.save_manifest(name, m)

    def rename_project(self, old, new):
        new = safe_name(new)
        if os.path.exists(self.project_dir(new)):
            raise ValueError("a project named %s exists" % new)
        os.rename(self.project_dir(old), self.project_dir(new))
        m = self.load_manifest(new)
        m["name"] = new
        self.save_manifest(new, m)
        if self.load_config().get("current_project") == old:
            self.set_current(new)
        return new

    def adopt_legacy(self, name, move=True):
        """Creates a project and moves (or copies) the parts, sketches, assemblies, stacks and annotations of the
        program folder into it. Returns the number of files taken over."""
        name = self.create(name, "Documents of the program folder")
        a = self.app_dir
        w = os.path.join(self.project_dir(name), "work")
        n = 0
        for sub, pattern in (("parts", ".part.json"), ("sketches", ".sketch.json"), ("assemblies", ".asm.json"), ("stacks", ".stack.json"), ("stacks", ".stack.txt")):
            src = os.path.join(a, sub)
            if not os.path.isdir(src):
                continue
            for fn in os.listdir(src):
                if fn.endswith(pattern):
                    (shutil.move if move else shutil.copy2)(os.path.join(src, fn), os.path.join(w, fn))
                    n += 1
        src = os.path.join(a, "annotations")
        if os.path.isdir(src):
            for fn in os.listdir(src):
                if fn.endswith(".json"):
                    (shutil.move if move else shutil.copy2)(os.path.join(src, fn), os.path.join(w, "annotations", fn))
                    n += 1
        return name, n

    # ------------------------------------------------------------------ documents
    def _work(self):
        name = self.current_name()
        if not name:
            raise ValueError("no project is open")
        return name, os.path.join(self.project_dir(name), "work")

    def doc_path(self, dtype, dname):
        _, w = self._work()
        return os.path.join(w, safe_name(dname) + TYPES[dtype])

    def documents(self):
        """All documents of the open project with metadata and links."""
        name, w = self._work()
        m = self.load_manifest(name)
        meta = m.get("docs") or {}
        docs = []
        parts, asms = {}, {}
        for fn in sorted(os.listdir(w)):
            for dtype, ext in TYPES.items():
                if fn.endswith(ext):
                    dname = fn[:-len(ext)]
                    path = os.path.join(w, fn)
                    st = os.stat(path)
                    key = dtype + ":" + dname
                    info = meta.get(key) or {}
                    doc = {"id": key, "type": dtype, "name": dname, "file": fn, "size": st.st_size,
                           "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                           "version": int(info.get("version", 0) or 0), "note": info.get("note", ""), "links": [], "used_by": []}
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except (OSError, ValueError):
                        data = {}
                    if dtype == "part":
                        doc["uid"] = data.get("uid")
                        for ft in data.get("features") or []:
                            if ft.get("type") in ("import", "surf_import") and ft.get("path"):
                                doc["links"].append({"type": "step", "name": os.path.basename(ft["path"]), "path": ft["path"]})
                        parts[dname] = doc
                    if dtype == "assembly":
                        # one link per part and per solid of a STEP file, with the number of components using it
                        for c in data.get("components") or []:
                            s = c.get("source") or {}
                            if s.get("type") == "part" and s.get("name"):
                                link = next((l for l in doc["links"] if l["type"] == "part" and l["name"] == s["name"]), None)
                                if link is None:
                                    doc["links"].append({"type": "part", "name": s["name"], "count": 1})
                                else:
                                    link["count"] += 1
                            elif s.get("path"):
                                f = os.path.basename(s["path"])
                                solid = s.get("part")
                                name = re.sub(r"\s+\d+$", "", str(c.get("name") or "")) if solid not in (None, "") else ""
                                key = "" if solid in (None, "") else str(solid)
                                link = next((l for l in doc["links"] if l["type"] == "step" and l["name"] == f and l.get("key") == key), None)
                                if link is None:
                                    doc["links"].append({"type": "step", "name": f, "path": s["path"], "solid": name or key, "key": key, "count": 1})
                                else:
                                    link["count"] += 1
                        asms[dname] = doc
                    if dtype == "analysis":
                        s = data.get("source") or {}
                        if s.get("name"):
                            doc["links"].append({"type": s.get("type") or "assembly", "name": s["name"]})
                    if dtype == "explicit":
                        s = data.get("source") or {}
                        if s.get("kind") == "shinycad" and s.get("name"):
                            doc["links"].append({"type": s.get("type") or "assembly", "name": s["name"]})
                        elif s.get("kind") == "inp" and s.get("inp"):
                            doc["links"].append({"type": "inp", "name": os.path.basename(s["inp"]), "path": s["inp"]})
                    docs.append(doc)
        for a in asms.values():
            for l in a["links"]:
                if l["type"] == "part" and l["name"] in parts:
                    parts[l["name"]]["used_by"].append({"type": "assembly", "name": a["name"]})
        for d in docs:
            if d["type"] in ("analysis", "explicit"):
                for l in d["links"]:
                    if l["type"] not in ("assembly", "part"):
                        continue
                    tgt = (asms if l["type"] == "assembly" else parts).get(l["name"])
                    if tgt is not None:
                        tgt["used_by"].append({"type": d["type"], "name": d["name"]})
        # exported drawings and STEP files, by document name prefix
        pdir = self.project_dir(name)
        exports = {"drawings": [], "step": [], "step_import": []}
        for sub in exports:
            dd = os.path.join(pdir, sub)
            if os.path.isdir(dd):
                for fn in sorted(os.listdir(dd)):
                    st = os.stat(os.path.join(dd, fn))
                    exports[sub].append({"name": fn, "size": st.st_size, "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
        for doc in docs:
            stem = doc["name"].lower()
            doc["exports"] = [e["name"] for e in exports["drawings"] + exports["step"] if e["name"].lower().startswith(stem)]
        return {"project": m, "docs": docs, "exports": exports}

    def _meta(self, name, key):
        m = self.load_manifest(name)
        m.setdefault("docs", {})
        return m, m["docs"].setdefault(key, {"version": 0, "note": ""})

    def rename_doc(self, dtype, old, new):
        name, w = self._work()
        new = safe_name(new)
        src, dst = self.doc_path(dtype, old), self.doc_path(dtype, new)
        if not os.path.isfile(src):
            raise ValueError("%s %s not found" % (dtype, old))
        if os.path.exists(dst):
            raise ValueError("%s %s exists" % (dtype, new))
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["name"] = new
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.remove(src)
        m = self.load_manifest(name)
        docs = m.setdefault("docs", {})
        if dtype + ":" + old in docs:
            docs[dtype + ":" + new] = docs.pop(dtype + ":" + old)
        self.save_manifest(name, m)
        # folder of an explicit analysis (model .inp and run folders)
        if dtype == "explicit":
            xd = os.path.join(self.project_dir(name), "explicit")
            a, b = os.path.join(xd, safe_name(old)), os.path.join(xd, new)
            if os.path.isdir(a) and not os.path.exists(b):
                os.rename(a, b)
                mi = os.path.join(b, "model", safe_name(old) + ".inp")
                if os.path.isfile(mi):
                    os.rename(mi, os.path.join(b, "model", new + ".inp"))
        # analyses and explicit analyses referencing the part or assembly
        if dtype in ("part", "assembly"):
            for fn in os.listdir(w):
                if fn.endswith(TYPES["analysis"]) or fn.endswith(TYPES["explicit"]):
                    p = os.path.join(w, fn)
                    with open(p, "r", encoding="utf-8") as f:
                        a = json.load(f)
                    s = a.get("source") or {}
                    if fn.endswith(TYPES["explicit"]) and s.get("kind") != "shinycad":
                        continue
                    if (s.get("type") or "assembly") == dtype and s.get("name") == old:
                        s["name"] = new
                        with open(p, "w", encoding="utf-8") as f:
                            json.dump(a, f, indent=1)
        # assemblies referencing the part
        if dtype == "part":
            for fn in os.listdir(w):
                if fn.endswith(TYPES["assembly"]):
                    p = os.path.join(w, fn)
                    with open(p, "r", encoding="utf-8") as f:
                        a = json.load(f)
                    changed = False
                    for c in a.get("components") or []:
                        s = c.get("source") or {}
                        if s.get("type") == "part" and s.get("name") == old:
                            s["name"] = new
                            changed = True
                    if changed:
                        with open(p, "w", encoding="utf-8") as f:
                            json.dump(a, f, indent=1)
        return new

    def copy_doc(self, dtype, old, new):
        name, w = self._work()
        new = safe_name(new)
        src, dst = self.doc_path(dtype, old), self.doc_path(dtype, new)
        if not os.path.isfile(src):
            raise ValueError("%s %s not found" % (dtype, old))
        if os.path.exists(dst):
            raise ValueError("%s %s exists" % (dtype, new))
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["name"] = new
        if dtype == "part":
            import uuid
            data["uid"] = uuid.uuid4().hex[:12]
            data.pop("legacy_ann", None)
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        return new

    def delete_doc(self, dtype, dname):
        name, w = self._work()
        src = self.doc_path(dtype, dname)
        if not os.path.isfile(src):
            raise ValueError("%s %s not found" % (dtype, dname))
        trash = os.path.join(self.project_dir(name), "trash")
        os.makedirs(trash, exist_ok=True)
        dst = os.path.join(trash, time.strftime("%Y%m%d_%H%M%S_") + os.path.basename(src))
        shutil.move(src, dst)
        m = self.load_manifest(name)
        (m.get("docs") or {}).pop(dtype + ":" + dname, None)
        self.save_manifest(name, m)

    # ------------------------------------------------------------------ versions
    def versions(self, dtype, dname):
        name, _ = self._work()
        vdir = os.path.join(self.project_dir(name), "versions")
        prefix = safe_name(dname) + TYPES[dtype].replace(".json", "") + ".v"
        out = []
        if os.path.isdir(vdir):
            for fn in sorted(os.listdir(vdir)):
                if fn.startswith(prefix) and fn.endswith(".json") and not fn.endswith(".meta.json"):
                    try:
                        n = int(fn[len(prefix):-5])
                    except ValueError:
                        continue
                    meta = {}
                    mp = os.path.join(vdir, fn[:-5] + ".meta.json")
                    if os.path.isfile(mp):
                        with open(mp, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                    out.append({"version": n, "file": fn, "note": meta.get("note", ""), "date": meta.get("date", "")})
        return sorted(out, key=lambda v: v["version"])

    def snapshot(self, dtype, dname, note=""):
        name, _ = self._work()
        src = self.doc_path(dtype, dname)
        if not os.path.isfile(src):
            raise ValueError("%s %s not found" % (dtype, dname))
        m, meta = self._meta(name, dtype + ":" + dname)
        n = int(meta.get("version", 0) or 0) + 1
        vdir = os.path.join(self.project_dir(name), "versions")
        os.makedirs(vdir, exist_ok=True)
        base = safe_name(dname) + TYPES[dtype].replace(".json", "") + ".v%d" % n
        shutil.copy2(src, os.path.join(vdir, base + ".json"))
        with open(os.path.join(vdir, base + ".meta.json"), "w", encoding="utf-8") as f:
            json.dump({"note": note or "", "date": time.strftime("%Y-%m-%d %H:%M")}, f)
        meta["version"] = n
        meta["note"] = note or ""
        self.save_manifest(name, m)
        return n

    def restore(self, dtype, dname, version, as_copy=None):
        """Restores a snapshot over the working file, or as a new document named as_copy."""
        name, _ = self._work()
        vdir = os.path.join(self.project_dir(name), "versions")
        base = safe_name(dname) + TYPES[dtype].replace(".json", "") + ".v%d.json" % int(version)
        src = os.path.join(vdir, base)
        if not os.path.isfile(src):
            raise ValueError("version %s not found" % version)
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
        if as_copy:
            new = safe_name(as_copy)
            dst = self.doc_path(dtype, new)
            if os.path.exists(dst):
                raise ValueError("%s %s exists" % (dtype, new))
            data["name"] = new
            if dtype == "part":
                import uuid
                data["uid"] = uuid.uuid4().hex[:12]
        else:
            dst = self.doc_path(dtype, dname)
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        return os.path.basename(dst)

    # ------------------------------------------------------------------ states
    def states(self):
        name, _ = self._work()
        sdir = os.path.join(self.project_dir(name), "states")
        out = []
        if os.path.isdir(sdir):
            for fn in sorted(os.listdir(sdir)):
                if fn.endswith(".state.json"):
                    st = os.stat(os.path.join(sdir, fn))
                    out.append({"name": fn[:-len(".state.json")], "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
        return out

    def save_state(self, sname, state):
        name, _ = self._work()
        sdir = os.path.join(self.project_dir(name), "states")
        os.makedirs(sdir, exist_ok=True)
        with open(os.path.join(sdir, safe_name(sname) + ".state.json"), "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)

    def load_state(self, sname):
        name, _ = self._work()
        with open(os.path.join(self.project_dir(name), "states", safe_name(sname) + ".state.json"), "r", encoding="utf-8") as f:
            return json.load(f)

    def delete_state(self, sname):
        name, _ = self._work()
        p = os.path.join(self.project_dir(name), "states", safe_name(sname) + ".state.json")
        if os.path.isfile(p):
            os.remove(p)

    # ------------------------------------------------------------------ imported STEP copies
    def import_copy(self, path):
        """Copies a STEP file into step_import/ of the open project and returns the local path (the original path
        when no project is open or the file is already inside the project)."""
        name = self.current_name()
        if not name or not path or not os.path.isfile(path):
            return path
        pdir = os.path.abspath(self.project_dir(name))
        if os.path.abspath(path).startswith(pdir):
            return path
        dst_dir = os.path.join(pdir, "step_import")
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, os.path.basename(path))
        if not os.path.isfile(dst) or os.path.getmtime(dst) < os.path.getmtime(path) or os.path.getsize(dst) != os.path.getsize(path):
            shutil.copy2(path, dst)
        return dst
