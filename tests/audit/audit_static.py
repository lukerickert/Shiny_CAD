# -*- coding: utf-8 -*-
"""SHINYCAD audit, static part. Standard library only; runs with any Python 3.10+ (no venv, no OpenCascade).

    py tests\\audit\\audit_static.py            writes _export\\audit\\static.md and static.json
    py tests\\audit\\audit_static.py --out DIR  other output folder

Checks
  routes      every @app.route of drawgen/web.py and drawgen/explicit/routes.py; each API URL used in the JS
              (api(), postJSON(), fetch()) matched against them: URLs without a route, routes without a caller
  controls    every **bold** name in docs/*.md that looks like a control, field, tab, menu or button name,
              searched as text in index.html and the JS: names not found in the interface
  links       every [..](NN-x.md#anchor) link of the docs resolves to a heading
  files       every `drawgen/...py` and `drawgen/static/...js` named in README.md and docs/ exists, and every
              module and script of the program is named in README.md or docs/02-files.md
  markers     TODO, FIXME, XXX, NotImplementedError, "not implemented", "not supported" in the program (not
              the third-party files)
  stubs       Python functions whose body is only pass / ... / raise NotImplementedError
  routes_doc  API paths mentioned in docs/ that do not exist
"""
import ast
import glob
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DRAWGEN = os.path.join(ROOT, "drawgen")
STATIC = os.path.join(DRAWGEN, "static")
DOCS = os.path.join(ROOT, "docs")
THIRD_PARTY = ("inp2rad.py", "inertia_calc.py", "inp_to_linear.py")

PY = sorted(glob.glob(os.path.join(DRAWGEN, "*.py"))) + sorted(glob.glob(os.path.join(DRAWGEN, "explicit", "*.py"))) + \
    sorted(glob.glob(os.path.join(DRAWGEN, "cam", "*.py"))) + [os.path.join(ROOT, "run.py")]
PY_OWN = [p for p in PY if os.path.basename(p) not in THIRD_PARTY]
JS = sorted(glob.glob(os.path.join(STATIC, "*.js")))
HTML = os.path.join(STATIC, "index.html")
MD = sorted(glob.glob(os.path.join(DOCS, "*.md"))) + [os.path.join(ROOT, "README.md")]


def read(p):
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


# --------------------------------------------------------------------------- routes

ROUTE_RE = re.compile(r'@app\.route\(\s*"([^"]+)"(?:\s*,\s*methods\s*=\s*\[([^\]]*)\])?')


def routes():
    """[(path, methods, file, line)]"""
    out = []
    for p in (os.path.join(DRAWGEN, "web.py"), os.path.join(DRAWGEN, "explicit", "routes.py")):
        for i, ln in enumerate(read(p).splitlines(), 1):
            m = ROUTE_RE.search(ln)
            if m:
                meth = sorted(re.findall(r'"([A-Z]+)"', m.group(2) or "")) or ["GET"]
                out.append((m.group(1), meth, rel(p), i))
    return out


def route_regex(path):
    """Flask rule -> regex: <name> one segment, <path:p> the rest."""
    r = re.escape(path)
    r = re.sub(r"<path:[A-Za-z_]+>", "[^?]+", r.replace("\\<", "<").replace("\\>", ">"))
    r = re.sub(r"<[A-Za-z_:]+>", "[^/?]+", r)
    return re.compile("^" + r + "(\\?.*)?$")


JS_URL_RE = re.compile(r'(?:\bapi|\bpostJSON|\bfetch|\bputJSON|\bgetJSON|\bdelJSON)\(\s*(?:"([^"]*)"|`([^`]*)`|\'([^\']*)\')')
JS_URL_ANY = re.compile(r'(?:"|`)(/api/[A-Za-z0-9_/.\-${}]*)(?:"|`)')


def js_urls():
    """{url_pattern: [(file, line, literal)]}: URLs of api()/postJSON()/fetch() calls plus every "/api/..." literal."""
    out = {}
    for p in JS:
        for i, ln in enumerate(read(p).splitlines(), 1):
            lits = []
            for m in JS_URL_RE.finditer(ln):
                lits.append(m.group(1) or m.group(2) or m.group(3) or "")
            lits += JS_URL_ANY.findall(ln)
            for lit in lits:
                if not lit.startswith("/api/"):
                    continue
                pat = re.sub(r"\$\{[^}]*\}", "<x>", lit)
                pat = re.sub(r"<x>(<x>)+", "<x>", pat)
                out.setdefault(pat, []).append((rel(p), i, lit))
    return out


def check_routes():
    rts = routes()
    urls = js_urls()
    findings = {"js_without_route": [], "route_without_js": [], "routes": len(rts), "js_urls": len(urls)}
    rx = [(route_regex(r[0]), r) for r in rts]
    called = set()
    for pat, uses in sorted(urls.items()):
        # a trailing "<x>" or "/" in the JS literal means a parameter follows (string concatenation)
        cand = [pat]
        if pat.endswith("/"):
            cand += [pat + "<x>", pat + "<x>/<x>"]
        if pat.endswith("<x>"):
            cand += [pat[:-3].rstrip("/"), pat + "/<x>"]
        probe = []
        for c in cand:
            probe.append(c.replace("<x>", "param"))
        hit = False
        for c in probe:
            for r, rt in rx:
                if r.match(c):
                    called.add(rt[0])
                    hit = True
        if not hit:
            # concatenation: "/api/x/" + name   (literal ends with "/")
            findings["js_without_route"].append({"url": pat, "uses": sorted(set("%s:%d" % u[:2] for u in uses))[:5]})
    for rt in rts:
        if rt[0] not in called and rt[0].startswith("/api/"):
            findings["route_without_js"].append({"route": rt[0], "methods": rt[1], "at": "%s:%d" % (rt[2], rt[3])})
    return findings


# --------------------------------------------------------------------------- controls named in the docs

BOLD_RE = re.compile(r"\*\*([^*\n]{1,60})\*\*")
SKIP_WORDS = {"and", "or", "the", "a", "to", "of", "in", "on", "with", "by", "not", "no", "only", "both", "all"}


def control_names():
    """{name: [doc:line]} for the bold names in the docs that look like control names."""
    names = {}
    for p in MD:
        for i, ln in enumerate(read(p).splitlines(), 1):
            if ln.startswith("|") and "---" in ln:
                continue
            for m in BOLD_RE.finditer(ln):
                n = m.group(1).strip()
                n = n.strip("`")
                if not n or n.lower() in SKIP_WORDS:
                    continue
                if re.search(r"[.`/\\]", n) and not n.endswith("…") and not n.endswith("..."):
                    continue                                        # file names, card names, paths
                if n.endswith((":", ",", ";")) or n.startswith(("(", "+", ")", ",")):
                    continue
                if len(n.split()) > 5 or ": " in n:
                    continue                                        # sentences, example values ("Mode 1: f Hz")
                if re.fullmatch(r"[0-9.\- ]+", n):
                    continue
                names.setdefault(n, []).append("%s:%d" % (rel(p), i))
    return names


def ui_text():
    t = read(HTML)
    for p in JS:
        t += "\n" + read(p)
    return t


def norm(s):
    s = s.replace("…", "...").replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def check_controls():
    names = control_names()
    ui = norm(ui_text())
    ui_nounit = ui
    missing = []
    for n, where in sorted(names.items()):
        v = [norm(n)]
        base = re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()                 # "Allowance (mm)" -> "Allowance"
        if base and base != n:
            v.append(norm(base))
        if n.endswith(("…", "...")):
            v.append(norm(n.rstrip("….")))
        if n.endswith("s") and len(n) > 4:
            v.append(norm(n[:-1]))
        if any(x and x in ui_nounit for x in v):
            continue
        missing.append({"name": n, "in_docs": where[:4], "count": len(where)})
    return {"checked": len(names), "not_in_interface": missing}


# --------------------------------------------------------------------------- docs links and files

LINK_RE = re.compile(r"\]\((?:([0-9]{2}-[a-z0-9-]+\.md)|\.\./README\.md|docs/([0-9]{2}-[a-z0-9-]+\.md))?(?:#([a-z0-9.\-]+))?\)")


def anchor(h):
    """GitHub style anchor of a heading text."""
    a = h.strip().lower()
    a = re.sub(r"[^\w\- ]", "", a)
    return a.replace(" ", "-")


def check_links():
    heads = {}
    for p in MD:
        hs = set()
        for ln in read(p).splitlines():
            m = re.match(r"^(#{1,6})\s+(.*)$", ln)
            if m:
                hs.add(anchor(m.group(2)))
        heads[os.path.basename(p)] = hs
    bad = []
    n = 0
    for p in MD:
        for i, ln in enumerate(read(p).splitlines(), 1):
            for m in LINK_RE.finditer(ln):
                n += 1
                target = m.group(1) or m.group(2) or os.path.basename(p)
                anc = m.group(3)
                if target not in heads:
                    if target == os.path.basename(p):
                        continue
                    bad.append({"at": "%s:%d" % (rel(p), i), "link": m.group(0), "why": "file missing"})
                elif anc and anc not in heads[target]:
                    bad.append({"at": "%s:%d" % (rel(p), i), "link": m.group(0), "why": "anchor missing"})
    return {"checked": n, "broken": bad}


FILE_RE = re.compile(r"`((?:drawgen/|tests/|docs/|static/|explicit/|cam/|solvers/)?[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-]+)*\.(?:py|js|html|css|bat|txt|md))`")
SUBDIRS = ("drawgen", "drawgen/static", "drawgen/explicit", "drawgen/cam", "drawgen/explicit/rivet_calibration", "tests", "tests/audit", "docs", "solvers")


def check_files():
    """Program files named in the docs (.py .js .html .css .bat .txt .md; .json files are mostly created at run time and
    are left out)."""
    named = {}
    for p in MD:
        for i, ln in enumerate(read(p).splitlines(), 1):
            for m in FILE_RE.finditer(ln):
                named.setdefault(m.group(1), []).append("%s:%d" % (rel(p), i))
    missing = []
    for f, where in sorted(named.items()):
        cands = [os.path.join(ROOT, f)] + [os.path.join(ROOT, d, f) for d in SUBDIRS]
        if not any(os.path.exists(c) for c in cands):
            missing.append({"file": f, "in_docs": where[:3]})
    # modules of the program not named in README.md or docs/02-files.md
    listing = read(os.path.join(ROOT, "README.md")) + read(os.path.join(DOCS, "02-files.md"))
    undocumented = []
    for p in PY + JS:
        r = rel(p)
        b = os.path.basename(p)
        if b in ("__init__.py",):
            continue
        if ("`%s`" % r) in listing or ("`%s`" % b) in listing or ("%s`" % b) in listing:
            continue
        undocumented.append(r)
    return {"named": len(named), "missing": missing, "modules_not_in_file_list": undocumented}


# --------------------------------------------------------------------------- markers and stubs

MARK_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b|NotImplementedError")
MARK_RE_I = re.compile(r"not implemented|not yet (?:supported|implemented|available)|not supported|unsupported", re.I)


def check_markers():
    out = []
    for p in PY_OWN + JS:
        for i, ln in enumerate(read(p).splitlines(), 1):
            if MARK_RE.search(ln) or MARK_RE_I.search(ln):
                out.append({"at": "%s:%d" % (rel(p), i), "text": ln.strip()[:160]})
    return out


def check_stubs():
    out = []
    for p in PY_OWN:
        try:
            tree = ast.parse(read(p))
        except SyntaxError as e:
            out.append({"at": "%s:%d" % (rel(p), e.lineno or 0), "text": "syntax error: %s" % e.msg})
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = [b for b in node.body if not (isinstance(b, ast.Expr) and isinstance(getattr(b, "value", None), ast.Constant) and isinstance(b.value.value, str))]
                if len(body) == 1:
                    b = body[0]
                    if isinstance(b, ast.Pass) or (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and b.value.value is Ellipsis):
                        out.append({"at": "%s:%d" % (rel(p), node.lineno), "text": "def %s: empty body" % node.name})
                    elif isinstance(b, ast.Raise) and "NotImplementedError" in ast.dump(b):
                        out.append({"at": "%s:%d" % (rel(p), node.lineno), "text": "def %s: raise NotImplementedError" % node.name})
    return out


def check_routes_in_docs():
    rts = [route_regex(r[0]) for r in routes()]
    bad = []
    for p in MD:
        for i, ln in enumerate(read(p).splitlines(), 1):
            for m in re.finditer(r"`(/api/[A-Za-z0-9_/<>:\-]+)`", ln):
                u = re.sub(r"<[^>]*>", "param", m.group(1))
                if not any(r.match(u) for r in rts):
                    bad.append({"at": "%s:%d" % (rel(p), i), "path": m.group(1)})
    return bad


# --------------------------------------------------------------------------- report

def md_list(items, fmt):
    return "\n".join("- " + fmt(x) for x in items) if items else "- none"


def main(argv):
    out_dir = os.path.join(ROOT, "_export", "audit")
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    res = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "routes": check_routes(),
        "controls": check_controls(),
        "links": check_links(),
        "files": check_files(),
        "markers": check_markers(),
        "stubs": check_stubs(),
        "routes_in_docs": check_routes_in_docs(),
    }
    with open(os.path.join(out_dir, "static.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    r = res["routes"]
    lines = ["# SHINYCAD static audit", "", "Generated %s, %.1f s. Program folder `%s`." % (res["generated"], time.time() - t0, ROOT), ""]
    lines += ["## Routes", "", "%d routes, %d distinct API URL patterns in the JS." % (r["routes"], r["js_urls"]), "",
              "### JS calls without a route", "", md_list(r["js_without_route"], lambda x: "`%s` (%s)" % (x["url"], ", ".join(x["uses"]))), "",
              "### Routes not called from the JS (tests, run.py or external use only)", "",
              md_list(r["route_without_js"], lambda x: "`%s` %s (%s)" % (x["route"], "/".join(x["methods"]), x["at"])), ""]
    c = res["controls"]
    lines += ["## Control names of the docs not found in the interface", "",
              "%d bold names checked in docs/ and README.md; a name counts as found when its text (or the text without a unit in "
              "parentheses, or without the trailing ellipsis) occurs in index.html or a JS file." % c["checked"], "",
              md_list(c["not_in_interface"], lambda x: "**%s** (%s%s)" % (x["name"], ", ".join(x["in_docs"]), ", ..." if x["count"] > 4 else "")), ""]
    k = res["links"]
    lines += ["## Docs links", "", "%d links checked." % k["checked"], "", md_list(k["broken"], lambda x: "%s `%s`: %s" % (x["at"], x["link"], x["why"])), ""]
    f = res["files"]
    lines += ["## Files", "", "%d file names in the docs." % f["named"], "", "### Named in the docs, missing", "",
              md_list(f["missing"], lambda x: "`%s` (%s)" % (x["file"], ", ".join(x["in_docs"]))), "",
              "### Modules and scripts not in the file list (README.md / docs/02-files.md)", "", md_list(f["modules_not_in_file_list"], lambda x: "`%s`" % x), ""]
    lines += ["## API paths in the docs that do not exist", "", md_list(res["routes_in_docs"], lambda x: "%s `%s`" % (x["at"], x["path"])), ""]
    lines += ["## Markers (TODO, FIXME, not implemented, not supported)", "", md_list(res["markers"], lambda x: "%s `%s`" % (x["at"], x["text"])), ""]
    lines += ["## Stub functions", "", md_list(res["stubs"], lambda x: "%s %s" % (x["at"], x["text"])), ""]
    with open(os.path.join(out_dir, "static.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    print("\nwritten: %s" % os.path.join(out_dir, "static.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
