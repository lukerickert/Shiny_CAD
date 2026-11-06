# -*- coding: utf-8 -*-
"""Audit of the interface (Playwright, headless Chromium): every tab is opened with a part loaded, every visible button
and menu item is clicked once and every select is set to each of its options. JavaScript errors, console errors,
server answers with status 500 and error texts that are Python exception messages are recorded with the control that
caused them. The test fails on JavaScript errors and status 500.

    run_tests.bat audit              (with tests\\test_audit_routes.py)
    run_tests.bat tests\\test_audit_ui.py
    AUDIT_TABS=part,cam              only these tabs (project, annotate, sketch, part, asm, fea, xp, cam)
    AUDIT_SHOTS=folder               a screenshot after each control with a finding

Report: _export\\audit\\ui.md and ui.json.
Controls that open dialogs or folders on this PC, delete documents, start solvers or write files of the program
folder are left out; their requests are answered by the test with status 400 "audit stub".
"""
import json
import os
import re
import time

import pytest

from conftest import plate

pw = pytest.importorskip("playwright.sync_api")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_export", "audit")
TABS = ("project", "annotate", "sketch", "part", "asm", "fea", "xp", "cam")

STUB_URLS = ("**/api/dialog", "**/open_folder", "**/api/open_path", "**/api/logo", "**/api/projects/root", "**/api/projects/forget",
             "**/api/file/unlink", "**/api/file/open", "**/api/file/saveas", "**/api/analysis/run", "**/api/explicit/solve",
             "**/api/explicit/kill", "**/api/explicit/server", "**/api/explicit/queue", "**/api/explicit/env_switch",
             "**/api/explicit/post", "**/api/explicit/build", "**/api/explicit/run/*", "**/api/explicit/probe",
             "**/api/explicit/save_png", "**/api/explicit/tools", "**/api/explicit/folders")
SKIP_TEXT = re.compile(r"^(Delete|Remove|Rename|Forget|Take over|Publish|Clear all|Reset all|Close project)", re.I)
SKIP_ID = re.compile(r"^(ann-delete|sk-delete|pj-adopt|pj-scan|pj-openfile)$")
PY_EXC = re.compile(r"Traceback|Error\b|'NoneType'|object has no attribute|object is not|^'[A-Za-z_0-9]+'$|list index out of range|"
                    r"indices must be|invalid literal|unsupported operand|takes \d+ positional|unexpected keyword|division by zero")
MAX_OPTIONS = 8
SETTLE_MS = 300


@pytest.fixture(scope="module")
def audit_browser():
    with pw.sync_playwright() as p:
        exe = os.environ.get("DRAWGEN_CHROMIUM") or None
        try:
            b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as e:
            pytest.skip("Chromium for Playwright not installed: %s" % str(e).splitlines()[0])
        yield b
        b.close()


class Log:
    def __init__(self):
        self.items = []
        self.control = "(page load)"
        self.tab = ""

    def add(self, kind, text):
        self.items.append({"tab": self.tab, "control": self.control, "kind": kind, "text": str(text)[:400]})


def _page(browser, server_url, client):
    pg = browser.new_page(viewport={"width": 1600, "height": 950})
    log = Log()
    pg.on("pageerror", lambda e: log.add("js_error", e))
    pg.on("console", lambda m: log.add("console_error", "%s (%s)" % (m.text, m.location.get("url", "")))
          if m.type == "error" and "favicon" not in m.location.get("url", "") and "Failed to load resource" not in m.text else None)
    pg.on("dialog", lambda d: d.accept("1") if d.type == "prompt" else d.dismiss() if d.type == "confirm" else d.accept())

    def on_response(r):
        try:
            u = r.url
            if "/api/" not in u:
                return
            if r.status >= 500:
                log.add("http_500", "%s %s %d" % (r.request.method, u, r.status))
            elif r.status >= 400:
                try:
                    msg = (r.json() or {}).get("error", "")
                except Exception:
                    msg = ""
                if msg == "audit stub":
                    return
                if PY_EXC.search(str(msg)):
                    log.add("python_message", "%s %s: %s" % (r.request.method, u, msg))
                else:
                    log.add("api_error", "%s %s: %s" % (r.request.method, u, msg or r.status))
        except Exception:
            pass
    pg.on("response", on_response)
    for u in STUB_URLS:
        pg.route(u, lambda route: route.fulfill(status=400, content_type="application/json", body='{"error": "audit stub"}'))
    client.put("/api/part/last", json={"clear": True})
    pg.goto(server_url + "/")
    pg.wait_for_load_state("networkidle")
    pg.wait_for_function("window.__part && window.__asm && window.projectInfo && window.projectInfo()")
    return pg, log


def _show_tab(pg, name):
    if name == "xp":
        pg.evaluate("showTab('xp')")
    elif name == "sketch":
        pg.click(".tab[data-tab=annotate]")
        pg.click("#tab-annotate .dmode button[data-dmode=sketch]")
    else:
        pg.click(".tab[data-tab=%s]" % name)
    pg.wait_for_timeout(SETTLE_MS)


def _pane(name):
    return "#tab-annotate" if name == "sketch" else "#tab-" + name


def _label(el):
    try:
        return el.evaluate("e => (e.id ? '#' + e.id : '') + ' ' + ((e.textContent || e.title || e.value || '').trim().slice(0, 40)) + "
                           "(e.dataset ? Object.entries(e.dataset).map(([k, v]) => ' [' + k + '=' + v + ']').join('') : '')").strip()
    except Exception:
        return "?"


def _close_popups(pg):
    pg.keyboard.press("Escape")
    for sel in ("#value-dialog-cancel", "#text-dialog-cancel", "#pt-cancel", "#fea-cancel", "#fa-cancel"):
        try:
            if pg.is_visible(sel):
                pg.click(sel, timeout=1000)
        except Exception:
            pass
    for sel in ("#opt-dialog", "#tb-dialog", "#ref-dialog", "#pj-mdialog", "#pj-vdialog"):
        try:
            if pg.is_visible(sel):
                pg.evaluate("s => { const d = document.querySelector(s); if (d) d.hidden = true; }", sel)
        except Exception:
            pass


def _load_part(pg, client):
    client.put("/api/part/file/audit_plate", json=plate("audit_plate"))
    _show_tab(pg, "part")
    try:
        if not pg.is_visible("#tab-part .dd > .dd-menu.file-menu"):
            pg.click("#tab-part .dd > .dd-btn", timeout=5000)
        pg.select_option("#pt-list", "audit_plate", timeout=5000)
        pg.wait_for_function("document.querySelector('#pt-info') && document.querySelector('#pt-info').textContent.includes('Volume')", timeout=60000)
        pg.keyboard.press("Escape")
    except Exception as e:
        return "part not loaded: %s" % str(e).splitlines()[0]
    return "audit_plate loaded"


def _crawl_tab(pg, log, name, shots):
    log.tab = name
    pane = _pane(name)
    _show_tab(pg, name)
    done = set()
    counts = {"buttons": 0, "menu_items": 0, "selects": 0, "skipped": 0, "not_clickable": 0}

    def after(label):
        pg.wait_for_timeout(SETTLE_MS)
        _close_popups(pg)
        if not pg.is_visible(pane):                   # the control switched the tab (Make drawing, ...)
            _show_tab(pg, name)
        if shots and any(i["control"] == label and i["tab"] == name for i in log.items):
            try:
                pg.screenshot(path=os.path.join(shots, re.sub(r"[^A-Za-z0-9_-]+", "_", name + "_" + label)[:80] + ".png"))
            except Exception:
                pass

    # buttons (the list is taken again after each click: controls appear and disappear)
    for _ in range(600):
        btns = pg.locator("%s button:visible" % pane).all()
        nxt = None
        for b in btns:
            lab = _label(b)
            if lab in done:
                continue
            nxt = (b, lab)
            break
        if nxt is None:
            break
        b, lab = nxt
        done.add(lab)
        ident = lab.split(" ")[0][1:] if lab.startswith("#") else ""
        text = lab[len("#" + ident) + 1:] if ident else lab
        if SKIP_TEXT.match(text.strip()) or SKIP_ID.match(ident) or "danger" in (b.get_attribute("class") or ""):
            counts["skipped"] += 1
            continue
        log.control = lab
        try:
            if b.get_attribute("disabled") is not None:
                counts["not_clickable"] += 1
                continue
            b.click(timeout=2000)
            counts["buttons"] += 1
        except Exception as e:
            counts["not_clickable"] += 1
            log.add("not_clickable", str(e).splitlines()[0][:160])
            continue
        after(lab)
        # a dropdown menu opened by the click: its items, each with the menu opened again
        if "dd-btn" in (b.get_attribute("class") or ""):
            items = pg.locator("%s .dd-menu:visible button, %s .dd-menu:visible a" % (pane, pane)).all()
            labels = [_label(i) for i in items]
            for il in labels:
                if il in done:
                    continue
                done.add(il)
                it_text = il[len(il.split(" ")[0]) + 1:] if il.startswith("#") else il
                if SKIP_TEXT.match(it_text.strip()):
                    counts["skipped"] += 1
                    continue
                log.control = lab + " > " + il
                try:
                    if not pg.locator("%s .dd-menu:visible" % pane).count():
                        b.click(timeout=2000)
                        pg.wait_for_timeout(100)
                    item = None
                    for i in pg.locator("%s .dd-menu:visible button, %s .dd-menu:visible a" % (pane, pane)).all():
                        if _label(i) == il:
                            item = i
                            break
                    if item is None:
                        continue
                    item.click(timeout=2000)
                    counts["menu_items"] += 1
                except Exception as e:
                    counts["not_clickable"] += 1
                    log.add("not_clickable", str(e).splitlines()[0][:160])
                    continue
                after(log.control)

    # selects: each option (at most MAX_OPTIONS), then the first value again
    for s in pg.locator("%s select:visible" % pane).all():
        lab = _label(s)
        log.control = lab
        try:
            opts = s.evaluate("e => Array.from(e.options).map(o => o.value)")
            first = s.evaluate("e => e.value")
            for v in opts[:MAX_OPTIONS]:
                s.select_option(v, timeout=2000)
                pg.wait_for_timeout(150)
                _close_popups(pg)
            if first in opts:
                s.select_option(first, timeout=2000)
            counts["selects"] += 1
        except Exception as e:
            log.add("not_clickable", str(e).splitlines()[0][:160])
        if not pg.is_visible(pane):
            _show_tab(pg, name)
    return counts


def test_audit_ui(audit_browser, server_url, client):
    os.makedirs(OUT, exist_ok=True)
    shots = os.environ.get("AUDIT_SHOTS") or ""
    if shots:
        os.makedirs(shots, exist_ok=True)
    tabs = [t for t in (os.environ.get("AUDIT_TABS") or ",".join(TABS)).split(",") if t in TABS]
    pg, log = _page(audit_browser, server_url, client)
    t0 = time.time()
    note = _load_part(pg, client)
    counts = {}
    for t in tabs:
        counts[t] = _crawl_tab(pg, log, t, shots)
    pg.close()
    with open(os.path.join(OUT, "ui.json"), "w", encoding="utf-8") as f:
        json.dump({"note": note, "counts": counts, "findings": log.items}, f, indent=1)
    order = ("js_error", "http_500", "python_message", "console_error", "api_error", "not_clickable")
    lines = ["# SHINYCAD interface audit", "", "Generated %s, %.0f s. %s." % (time.strftime("%Y-%m-%d %H:%M"), time.time() - t0, note), "",
             "| Tab | Buttons | Menu items | Selects | Skipped | Not clickable |", "|---|---|---|---|---|---|"]
    lines += ["| %s | %d | %d | %d | %d | %d |" % (t, c["buttons"], c["menu_items"], c["selects"], c["skipped"], c["not_clickable"]) for t, c in counts.items()]
    lines += ["", "Findings are attributed to the last control clicked; a request started by an earlier control can be listed under the next one.", ""]
    titles = {"js_error": "JavaScript errors", "http_500": "Server status 500", "python_message": "Error texts that are Python exception messages",
              "console_error": "Console errors", "api_error": "Error texts shown by the interface (4xx)", "not_clickable": "Controls that could not be clicked"}
    for k in order:
        its = [i for i in log.items if i["kind"] == k]
        lines += ["## %s (%d)" % (titles[k], len(its)), ""]
        lines += ["- %s: %s: %s" % (i["tab"], i["control"], i["text"]) for i in its] or ["- none"]
        lines.append("")
    with open(os.path.join(OUT, "ui.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    bad = [i for i in log.items if i["kind"] in ("js_error", "http_500")]
    assert not bad, "\n".join("%s: %s: %s" % (i["tab"], i["control"], i["text"]) for i in bad)
