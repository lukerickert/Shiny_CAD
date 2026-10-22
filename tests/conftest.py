# -*- coding: utf-8 -*-
"""Test setup. The program runs against a copy of config.json, a projects folder and a view cache in a temporary
folder, so the tests leave config.json, the projects and %LOCALAPPDATA%\\drawgen of this PC unchanged."""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP = tempfile.mkdtemp(prefix="drawgen_tests_")
with open(os.path.join(ROOT, "config.json"), "r", encoding="utf-8") as _f:
    _cfg = json.load(_f)
_cfg["projects_root"] = os.path.join(TMP, "projects")
_cfg["current_project"] = ""
os.makedirs(_cfg["projects_root"])
with open(os.path.join(TMP, "config.json"), "w", encoding="utf-8") as _f:
    json.dump(_cfg, _f, indent=2)
os.environ["DRAWGEN_CONFIG"] = os.path.join(TMP, "config.json")
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "local")
os.environ.setdefault("DRAWGEN_WORKERS", "1")          # no worker pool unless a test asks for one


def pytest_sessionfinish(session, exitstatus):
    try:
        from drawgen import pool
        pool.shutdown()
    except Exception:
        pass
    shutil.rmtree(TMP, ignore_errors=True)


# --------------------------------------------------------------------------- model helpers

def rect(w, h, x=0.0, y=0.0, start=1):
    """Four sketch lines of a rectangle."""
    p = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    return [{"id": start + i, "t": "line", "x1": p[i][0], "y1": p[i][1], "x2": p[(i + 1) % 4][0],
             "y2": p[(i + 1) % 4][1], "layer": "0"} for i in range(4)]


def circle(cx, cy, r, eid):
    return {"id": eid, "t": "circle", "cx": cx, "cy": cy, "r": r, "layer": "0"}


def part_rec(name, features):
    """Part record (version 1 form: sketches inside the features; migrate() converts it)."""
    from drawgen import part
    return part.migrate({"name": name, "features": features})


def plate(name="plate", w=100.0, h=50.0, t=20.0, hole_r=10.0):
    """Plate w x h x t with a through hole of radius hole_r in the centre."""
    ents = rect(w, h) + ([circle(w / 2, h / 2, hole_r, 9)] if hole_r else [])
    return part_rec(name, [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                            "sketch": {"entities": ents}, "depth": t}])


def sketch_part(name="sketch", w=200.0, h=80.0):
    """Part with one sketch (a w x h rectangle on XY) and no solid."""
    return {"name": name, "version": 2, "features": [{"id": "f1", "name": "Sketch 1", "type": "sketch", "plane": "XY", "offset": 0,
                                                      "sketch": {"entities": rect(w, h), "layers": [{"name": "0", "on": True}]}}]}


@pytest.fixture(scope="session")
def web():
    from drawgen import web as w
    return w


@pytest.fixture(scope="session")
def client(web):
    """Flask test client with an open project "tests"."""
    c = web.app.test_client()
    r = c.post("/api/projects", json={"name": "tests", "description": "automatic tests", "open": True})
    assert r.status_code == 200, r.get_data(as_text=True)
    return c


@pytest.fixture(scope="session")
def server_url(client, web):
    """The server on a free local port (for the browser tests)."""
    from werkzeug.serving import make_server
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = make_server("127.0.0.1", port, web.app, threaded=True)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield "http://127.0.0.1:%d" % port
    srv.shutdown()
