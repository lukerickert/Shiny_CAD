# -*- coding: utf-8 -*-
"""Static checks: Python and JS syntax, undefined names, interface ids, names used across modules."""
import ast
import glob
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THIRD_PARTY = ("inp2rad.py", "inertia_calc.py", "inp_to_linear.py")         # drawgen/explicit: kept unchanged
PY = sorted(glob.glob(os.path.join(ROOT, "drawgen", "*.py"))) + [os.path.join(ROOT, "run.py")] + \
    sorted(p for p in glob.glob(os.path.join(ROOT, "drawgen", "explicit", "*.py")) if os.path.basename(p) not in THIRD_PARTY)
JS = sorted(glob.glob(os.path.join(ROOT, "drawgen", "static", "*.js")))
HTML = os.path.join(ROOT, "drawgen", "static", "index.html")


@pytest.mark.parametrize("path", PY, ids=os.path.basename)
def test_python_compiles(path):
    with open(path, "r", encoding="utf-8") as f:
        compile(f.read(), path, "exec")


def test_pyflakes_no_undefined_names():
    pytest.importorskip("pyflakes")
    r = subprocess.run([sys.executable, "-m", "pyflakes"] + PY, capture_output=True, text=True)
    bad = [ln for ln in r.stdout.splitlines() if "undefined name" in ln or "syntax" in ln.lower()]
    assert not bad, "\n".join(bad)


@pytest.mark.parametrize("path", JS, ids=os.path.basename)
def test_js_syntax(path, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    mod = tmp_path / (os.path.basename(path) + ".mjs")      # the files are ES modules or plain scripts
    mod.write_text(open(path, encoding="utf-8").read(), encoding="utf-8")
    r = subprocess.run([node, "--check", str(mod)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_js_ids_exist_in_html():
    """Every #id used in the JS exists in index.html or is created by the JS (prefix-built ids excepted)."""
    html = open(HTML, encoding="utf-8").read()
    js = {p: open(p, encoding="utf-8").read() for p in JS}
    ids = set(re.findall(r'id="([A-Za-z0-9_-]+)"', html))
    made = set()
    for t in js.values():
        made |= set(re.findall(r'id="([A-Za-z0-9_-]+)"', t)) | set(re.findall(r'setAttribute\("id", "([A-Za-z0-9_-]+)"', t))
        made |= set(re.findall(r'\.id = "([A-Za-z0-9_-]+)"', t))
    prefixes = set()                                          # ids built in templates: id="am-p${side}"
    for t in list(js.values()) + [html]:
        prefixes |= set(re.findall(r'id="([A-Za-z0-9_-]+)\$\{', t))
        prefixes |= set(re.findall(r'\b(?:v3|memberEndSelect)\("([A-Za-z0-9_-]+)"', t))     # analysis.js id helpers
    missing = []
    for p, t in js.items():
        for i in set(re.findall(r'\$\("#([A-Za-z0-9_-]+)"\)', t)) | set(re.findall(r'getElementById\("([A-Za-z0-9_-]+)"\)', t)):
            if i not in ids and i not in made and not any(i.startswith(pf) for pf in prefixes):
                missing.append("%s: #%s" % (os.path.basename(p), i))
    assert not missing, "\n".join(sorted(missing))


def test_cross_module_names():
    """module.name used in one drawgen module exists in the other module."""
    mods = {os.path.basename(f)[:-3]: f for f in PY if "drawgen" in f}
    top = {}
    for m, f in mods.items():
        t = ast.parse(open(f, encoding="utf-8").read())
        names = set()
        for n in ast.walk(t):
            if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                names.add(n.name)
            elif isinstance(n, ast.Assign) and n in t.body:
                names |= {x.id for tg in n.targets for x in ast.walk(tg) if isinstance(x, ast.Name)}
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                names |= {a.asname or a.name.split(".")[0] for a in n.names}
        names |= {x.id for n in t.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                  for tg in (n.targets if isinstance(n, ast.Assign) else [n.target]) for x in ast.walk(tg) if isinstance(x, ast.Name)}
        top[m] = names
    bad = []
    for m, f in mods.items():
        t = ast.parse(open(f, encoding="utf-8").read())
        alias = {}
        for n in ast.walk(t):
            if isinstance(n, ast.ImportFrom) and n.level >= 1:
                for a in n.names:
                    if a.name in mods:
                        alias[a.asname or a.name] = a.name
        locals_ = {x.id for x in ast.walk(t) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}
        for n in ast.walk(t):
            if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in alias
                    and n.value.id not in locals_ and n.attr not in top[alias[n.value.id]]):
                bad.append("%s: %s.%s" % (m, n.value.id, n.attr))
    assert not bad, "\n".join(sorted(set(bad)))


def test_window_exports_do_not_shadow_globals():
    """Names that sketch.js assigns to window must not be top-level functions of the other plain scripts: the
    assignment replaces them (annotate.js showProps was replaced this way)."""
    static = os.path.join(ROOT, "drawgen", "static")
    s = open(os.path.join(static, "sketch.js"), encoding="utf-8").read()
    exp = re.search(r"Object\.assign\(window, \{(.*?)\}\);", s, re.S).group(1)
    names = [n.strip() for n in exp.replace("\n", " ").split(",") if n.strip()]
    names = [n for n in names if re.search(r"^\s*(?:async\s+)?function\s+%s\s*\(|^\s*(?:const|let|var)\s+%s\b" % (n, n), s, re.M)]
    bad = []
    for f in ("app.js", "annotate.js", "refdiagrams.js", "icons.js"):
        t = open(os.path.join(static, f), encoding="utf-8").read()
        for n in names:
            if re.search(r"^(?:async\s+)?function\s+%s\s*\(|^(?:const|let|var)\s+%s\b" % (re.escape(n), re.escape(n)), t, re.M):
                bad.append("%s: %s" % (f, n))
    assert not bad, "\n".join(bad)
