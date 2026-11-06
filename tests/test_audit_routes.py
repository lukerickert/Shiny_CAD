# -*- coding: utf-8 -*-
"""Audit of the server routes: every route of the program is called with an empty body, a body of the wrong type, a
body with a name only and a text body. A request that raises an exception (status 500) is a finding and fails the
test. A 4xx answer whose error text is a Python exception message is listed (not a failure).

    run_tests.bat audit              (with tests\\test_audit_ui.py)
    run_tests.bat tests\\test_audit_routes.py

Report: _export\\audit\\routes.md and routes.json.
Routes that open dialogs or folders on this PC, start solvers, change the projects root or write files of the program
folder are left out (SKIP).
"""
import json
import os
import re
import time
import traceback

import pytest

from conftest import plate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_export", "audit")

SKIP = ("/api/dialog", "open_folder", "/api/open_path", "/api/logo", "/api/upload", "/api/projects/root",
        "/api/projects/forget", "/api/file/unlink", "/api/file/open", "/api/file/saveas",
        "/api/analysis/run", "/api/analysis/cancel", "/api/cam/run", "/api/cam/cancel",
        "/api/explicit/solve", "/api/explicit/kill", "/api/explicit/server", "/api/explicit/queue", "/api/explicit/env_switch",
        "/api/explicit/post", "/api/explicit/build", "/api/explicit/run/", "/api/explicit/probe", "/api/explicit/save_png",
        "/api/explicit/tools", "/api/explicit/folders", "/api/explicit/console/clear", "/api/part/cancel", "/static/")

PARAMS = {"name": "audit_plate", "target": "front", "fid": "zz", "jid": "zz", "p": "app.js", "fname": "zz.png"}

BODIES = [("empty", {}), ("name", {"name": "audit_plate"}), ("list", [1, 2]), ("text", "not json")]

PY_EXC = re.compile(r"Traceback|Error\b|'NoneType'|object has no attribute|object is not|^'[A-Za-z_0-9]+'$|list index out of range|"
                    r"indices must be|invalid literal|unsupported operand|takes \d+ positional|unexpected keyword|division by zero")


def _rules(web):
    out = []
    for r in web.app.url_map.iter_rules():
        if r.rule.startswith("/static") or r.rule == "/":
            continue
        for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
            out.append((r.rule, m))
    return sorted(out)


def _url(rule):
    def sub(m):
        name = m.group(1).split(":")[-1]
        return PARAMS.get(name, "zz")
    return re.sub(r"<([^>]+)>", sub, rule)


def _call(client, method, url, kind, body):
    kw = {}
    if method in ("POST", "PUT", "PATCH"):
        if kind == "text":
            kw = {"data": body, "content_type": "text/plain"}
        else:
            kw = {"json": body}
    t0 = time.time()
    try:
        r = client.open(url, method=method, **kw)
        status = r.status_code
        try:
            data = r.get_json(silent=True)
        except Exception:
            data = None
        text = r.get_data(as_text=True)[:300] if data is None else ""
        return {"status": status, "json": data if isinstance(data, dict) and "error" in data else None, "text": text,
                "secs": round(time.time() - t0, 2), "exc": None}
    except Exception:
        return {"status": 500, "json": None, "text": "", "secs": round(time.time() - t0, 2),
                "exc": [ln for ln in traceback.format_exc().strip().splitlines() if "flask" not in ln and "werkzeug" not in ln
                        and "ensure_sync" not in ln and ln.strip() and not ln.strip().startswith(("~", "^"))][-6:]}


def test_audit_routes(client, web):
    os.makedirs(OUT, exist_ok=True)
    client.put("/api/part/file/audit_plate", json=plate("audit_plate"))
    prop = web.app.config.get("PROPAGATE_EXCEPTIONS")
    web.app.config["PROPAGATE_EXCEPTIONS"] = True          # exceptions reach the test instead of a 500 page
    rows = []
    try:
        for rule, method in _rules(web):
            if any(s in rule for s in SKIP):
                rows.append({"rule": rule, "method": method, "skip": True})
                continue
            url = _url(rule)
            variants = BODIES if method in ("POST", "PUT", "PATCH") else [("none", None)]
            for kind, body in variants:
                res = _call(client, method, url, kind, body)
                res.update({"rule": rule, "method": method, "url": url, "body": kind})
                rows.append(res)
    finally:
        web.app.config["PROPAGATE_EXCEPTIONS"] = prop
    crashes = [r for r in rows if not r.get("skip") and (r["exc"] or r["status"] >= 500)]
    leaks = [r for r in rows if not r.get("skip") and not r["exc"] and 400 <= r["status"] < 500 and r["json"] and
             PY_EXC.search(str(r["json"].get("error", "")))]
    noerr = [r for r in rows if not r.get("skip") and not r["exc"] and 400 <= r["status"] < 500 and r["json"] is None and
             "json" not in (r["text"] or "").lower()]
    slow = sorted([r for r in rows if not r.get("skip") and r["secs"] > 5], key=lambda r: -r["secs"])
    with open(os.path.join(OUT, "routes.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    lines = ["# SHINYCAD route audit", "", "Generated %s. %d routes, %d requests, %d skipped." %
             (time.strftime("%Y-%m-%d %H:%M"), len(set((r["rule"], r["method"]) for r in rows)),
              len([r for r in rows if not r.get("skip")]), len([r for r in rows if r.get("skip")])), ""]
    lines += ["## Requests that raised an exception (status 500)", ""]
    for r in crashes:
        lines.append("- `%s %s` body %s" % (r["method"], r["url"], r["body"]))
        for ln in (r["exc"] or [r["text"]]):
            lines.append("    " + ln)
    lines += ["- none"] if not crashes else []
    lines += ["", "## 4xx answers whose error text is a Python exception message", ""]
    lines += ["- `%s %s` body %s: `%s`" % (r["method"], r["url"], r["body"], str(r["json"]["error"])[:160]) for r in leaks] or ["- none"]
    lines += ["", "## 4xx answers without a JSON error (HTML or text page)", ""]
    lines += ["- `%s %s` body %s: status %d `%s`" % (r["method"], r["url"], r["body"], r["status"], (r["text"] or "").strip()[:80]) for r in noerr] or ["- none"]
    lines += ["", "## Requests slower than 5 s", ""]
    lines += ["- `%s %s` body %s: %.1f s" % (r["method"], r["url"], r["body"], r["secs"]) for r in slow] or ["- none"]
    lines += ["", "## Skipped", ""]
    lines += ["- `%s %s`" % (r["method"], r["rule"]) for r in rows if r.get("skip")]
    lines += ["", "## All requests", "", "| Method | URL | Body | Status | s |", "|---|---|---|---|---|"]
    lines += ["| %s | `%s` | %s | %d | %.1f |" % (r["method"], r["url"], r["body"], r["status"], r["secs"]) for r in rows if not r.get("skip")]
    with open(os.path.join(OUT, "routes.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    assert not crashes, "\n".join("%s %s body %s: %s" % (r["method"], r["url"], r["body"], (r["exc"] or [r["text"]])[-1]) for r in crashes)
