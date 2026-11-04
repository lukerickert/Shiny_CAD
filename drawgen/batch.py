# -*- coding: utf-8 -*-
"""Batch mode (run.py --batch): meshes or solves a saved analysis, or writes the model .inp (and the OpenCourant
decks) of a saved explicit document, without the browser.

    run.py --batch analysis <name> [--project <project>] [--mesh-only]
    run.py --batch explicit <name> [--project <project>] [--rad] [--radv 2025 | 2023]

The documents are those of the project (the open project of config.json, or --project). The requests are the ones
of the Analysis and Explicit tabs (Flask test client), so the results are the same files: analysis/<name>/ (job.inp,
results, report) and explicit/<name>/model/<name>.inp. --rad: inp2rad writes <name>_0000.rad and <name>_0001.rad next
to the .inp. Returns the exit code (0: done)."""
import os
import subprocess
import sys
import time


def _wait(client, url, timeout=3600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(url).get_json()
        if j.get("state") != "running":
            return j
        time.sleep(0.5)
    raise RuntimeError("the job did not finish in %d s" % timeout)


def _shell_lines(r):
    if not r:
        return []
    return ["shells: %d of %d face(s) structured, %d free" % (r["structured"], r["faces"], r["free"]),
            "element quality (gamma): min %.3f, mean %.3f, below 0.3: %d" % (r["min_quality"] or 0, r["mean_quality"] or 0, r["below_03"]),
            "element edges: %.3f mm to %.3f mm" % (r["min_edge"] or 0, r["max_edge"] or 0)]


def run(kind, name, project=None, mesh_only=False, rad=False, radv=2025, log=print):
    from . import web
    c = web.app.test_client()
    if project:
        r = c.post("/api/projects/open", json={"name": project})
        if r.status_code != 200:
            log("project %s: %s" % (project, (r.get_json() or {}).get("error")))
            return 2
    if kind == "analysis":
        r = c.get("/api/analysis/file/" + name)
        if r.status_code != 200:
            log((r.get_json() or {}).get("error") or "analysis %s not found" % name)
            return 2
        doc = r.get_json()
        jid = c.post("/api/analysis/run", json={"name": name, "analysis": doc, "mesh_only": mesh_only}).get_json()["job"]
        j = _wait(c, "/api/analysis/job/" + jid)
        if j["state"] != "done":
            log("analysis %s: %s" % (name, j.get("error")))
            return 1
        res = j["result"]
        s = res["summary"]
        log("analysis %s: %d nodes, %d elements" % (name, s["nodes"], s["elements"]))
        for b in s["bodies"]:
            log("  %s: %d elements %s" % (b["name"], b["elements"], " ".join(b["types"])))
        for line in _shell_lines(s.get("shell")):
            log(line)
        for w in s.get("warnings") or []:
            log("warning: " + w)
        for k, p in (res.get("files") or {}).items():
            log("%s: %s" % (k, p))
        return 0
    if kind == "explicit":
        r = c.get("/api/explicit/file/" + name)
        if r.status_code != 200:
            log((r.get_json() or {}).get("error") or "explicit document %s not found" % name)
            return 2
        doc = r.get_json()
        jid = c.post("/api/explicit/model", json={"name": name, "doc": doc}).get_json()["job"]
        j = _wait(c, "/api/explicit/job/" + jid)
        if j["state"] != "done":
            log("explicit %s: %s" % (name, j.get("error")))
            return 1
        s = j["result"]["summary"]
        inp = j["result"]["inp"]
        log("explicit %s: %d nodes, %d elements" % (name, s["nodes"], s["elements"]))
        for b in s.get("bodies") or []:
            log("  %s (%s): %d elements %s" % (b["name"], b["role"], b["elements"], " ".join(b["types"])))
        for line in _shell_lines(s.get("shell")):
            log(line)
        for ns in s.get("nsets") or []:
            log("  node set %s: %d nodes" % (ns["name"], ns["nodes"]))
        log("inp: " + inp)
        if rad:
            here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "explicit")
            args = [sys.executable, os.path.join(here, "inp2rad_run.py"), os.path.join(here, "inp2rad.py"), inp]
            if int(radv) != 2025:
                args += ["--radv", str(radv)]
            p = subprocess.run(args, cwd=os.path.dirname(inp), input="y\n" * 5000, text=True, capture_output=True)
            stem = os.path.splitext(inp)[0]
            decks = [stem + "_0000.rad", stem + "_0001.rad"]
            if not os.path.isfile(decks[0]):
                log("inp2rad failed: %s" % ((p.stdout or "") + (p.stderr or "")).strip()[-2000:])
                return 1
            for d in decks:
                if os.path.isfile(d):
                    log("deck: " + d)
        return 0
    log("unknown kind %s (analysis or explicit)" % kind)
    return 2
