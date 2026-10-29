# -*- coding: utf-8 -*-
"""Wall time of /api/part/build for a sequence of edits of one part: py tests\bench_part_build.py (NX and NY in the
environment set the number of slots, default 4 x 2; NX=10 NY=5 gives a part of 176 faces whose fillets and chamfers
fail). Each step is one request as the Part tab makes it. Not a pytest test."""
import copy
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)
import conftest  # noqa: E402,F401
from conftest import circle, rect  # noqa: E402


def main():
    from drawgen import web, part
    c = web.app.test_client()
    c.post("/api/projects", json={"name": "bench", "description": "", "open": True})

    def build(p, label, upto=None):
        t0 = time.perf_counter()
        r = c.post("/api/part/build", json={"part": p, "upto": upto})
        dt = time.perf_counter() - t0
        j = r.get_json()
        errs = [s for s in j["status"] if s.get("error")]
        m = j["mesh"]
        print("%-44s %6.2f s   faces %4d  edges %4d  tris %6d  %s" % (label, dt, len(m.get("face_keys") or []), len(m.get("edge_keys") or []),
                                                                        len(m["triangles"]), ("ERRORS: %s" % errs) if errs else ""))
        return j

    ents = rect(150, 80)
    NX, NY = int(os.environ.get("NX", 4)), int(os.environ.get("NY", 2))
    slots, k = [], 100
    for i in range(NX):
        for j in range(NY):
            slots += rect(14 * 4.0 / NX, 8 * 2.0 / NY, 15 + i * 136.0 / NX, 14 + j * 44.0 * 2 / NY, k)
            k += 4
    holes = [circle(20 + i * 110.0 / max(NX - 1, 1), 40, min(4, 40.0 / NX), 300 + i) for i in range(NX)]
    p = {"name": "bench", "version": 2, "features": [
        {"id": "e1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "sketch": {"entities": ents}, "depth": 20},
        {"id": "c1", "name": "Cut 1", "type": "cut", "plane": "XY", "offset": 0, "through": True, "sketch": {"entities": slots}},
        {"id": "c2", "name": "Cut 2", "type": "cut", "plane": "XY", "offset": 0, "through": True, "sketch": {"entities": holes}},
    ]}
    p = part.migrate(copy.deepcopy(p))
    j = build(p, "extrude + 2 cuts (cold)")
    build(p, "same part again")
    ek = j["mesh"]["edge_keys"]
    vertical = [k for k in ek if abs(k["mid"][2] - 10) < 1e-6]
    top = [k for k in ek if abs(k["mid"][2] - 20) < 1e-6]
    print("   vertical edges %d, top edges %d" % (len(vertical), len(top)))
    # picking edges one by one: the build stops before the fillet (upto)
    f = {"id": "fl1", "name": "Fillet 1", "type": "fillet", "value": 1.5, "edges": []}
    p["features"].append(f)
    for n in (1, 2, 3):
        f["edges"] = vertical[:n]
        build(p, "picking edge %d (build before the fillet)" % n, upto=len(p["features"]) - 1)
    f["edges"] = vertical
    build(p, "fillet of %d vertical edges" % len(vertical))
    f["value"] = 2.0
    build(p, "fillet value changed")
    build(p, "same part again")
    ch = {"id": "ch1", "name": "Chamfer 1", "type": "chamfer", "value": 1.0, "edges": [k for k in top if k["len"] > 20]}
    p["features"].append(ch)
    j = build(p, "chamfer of %d top edges" % len(ch["edges"]))
    ch["value"] = 1.5
    build(p, "chamfer value changed")
    f["value"] = 2.5
    build(p, "fillet value changed (chamfer rebuilt)")
    p["features"].append({"id": "sp1", "name": "Partition 1", "type": "split", "method": "principal", "plane": "YZ", "offset": 75, "cells": []})
    p["features"].append({"id": "sp2", "name": "Partition 2", "type": "split", "method": "principal", "plane": "XZ", "offset": 40, "cells": []})
    build(p, "2 partitions (4 cells)")
    build(p, "same part again")
    ch["value"] = 1.2
    build(p, "chamfer value changed (partitions rebuilt)")
    j = build(p, "same part again")
    ek = j["mesh"]["edge_keys"]
    short = [k for k in ek if abs(k["mid"][2] - 20) < 1e-6 and k["len"] <= 20][:6]
    bad = {"id": "fl2", "name": "Fillet 2", "type": "fillet", "value": 6.0, "edges": short}
    p["features"].append(bad)
    build(p, "fillet that fails (diagnosis)")


if __name__ == "__main__":
    main()
