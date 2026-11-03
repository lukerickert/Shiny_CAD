# -*- coding: utf-8 -*-
"""Analysis (CalculiX) tests: section properties, beams, rods, fasteners with preload, plates, loads and reactions
against hand calculations, the analysis API and the Analysis tab. Skipped when CalculiX (ccx) or gmsh is missing."""
import math
import os
import subprocess
import time

import numpy as np
import pytest

from conftest import plate

from drawgen import analysis

CCX = analysis.find_ccx(os.environ.get("DRAWGEN_CCX", ""))
needs_ccx = pytest.mark.skipif(CCX is None, reason="CalculiX (ccx) not found")
STEEL = {"Steel": {"E": 210000.0, "nu": 0.3, "rho": 7850.0}}


def ok(r):
    assert r.status_code == 200, r.get_data(as_text=True)[:500]
    return r.get_json()


# --------------------------------------------------------------------------- helpers

def bodies_of(shapes, modes=None):
    """Analysis bodies of build123d shapes in place (no assembly)."""
    from drawgen import assembly
    out = []
    for bid, s in shapes.items():
        m = assembly.fast_mesh(s)
        V = np.asarray(m["vertices"], float)
        T = np.asarray(m["triangles"])
        fot = np.asarray(m["face_of_tri"])
        faces = {int(fi): (V[T[fot == fi][:, 0]], V[T[fot == fi][:, 1]], V[T[fot == fi][:, 2]]) for fi in np.unique(fot)}
        bb = m["bbox"]
        diag = math.sqrt(sum((bb[i + 3] - bb[i]) ** 2 for i in range(3)))
        out.append({"id": bid, "name": bid, "shape": s, "mode": (modes or {}).get(bid, "solid"), "material": None,
                    "size": None, "layers": 1, "faces": faces, "refs": assembly.face_refs(s),
                    "tol": max(diag / 2000.0, 0.005), "M": np.hstack([np.eye(3), np.zeros((3, 1))])})
    return out


def face_index(body, pred):
    return next(i for i, r in enumerate(body["refs"]) if r and pred(r))


def solve(doc, bodies, wd, size=5.0):
    from build123d import export_brep
    from drawgen import femesh
    os.makedirs(wd, exist_ok=True)
    job = {"size": size, "bonded": doc.get("bonded", True), "bodies": [], "mesh": dict(doc.get("mesh") or {})}
    for b in bodies:
        p = os.path.join(wd, b["id"] + ".brep")
        export_brep(b["shape"], p)
        job["bodies"].append({"id": b["id"], "brep": p, "mode": b["mode"], "size": None, "layers": 1, "strategy": b.get("strategy")})
    mesh = femesh.run(job) if bodies else {"nodes": {"ids": [], "xyz": []}, "bodies": {}, "warnings": []}
    M = analysis.Model(doc, bodies, mesh)
    M.build()
    M.write(os.path.join(wd, "job.inp"), "test")
    r = subprocess.run([CCX, "-i", "job"], cwd=wd, capture_output=True, text=True)
    assert "Job finished" in r.stdout, r.stdout[-1500:]
    if M.atype != "static":
        return M, analysis.ModeResults(M, analysis.read_frd_modes(os.path.join(wd, "job.frd")),
                                       analysis.read_eigen(os.path.join(wd, "job.dat")))
    return M, analysis.Results(M, analysis.read_frd(os.path.join(wd, "job.frd")), analysis.read_dat(os.path.join(wd, "job.dat")))


def beam_doc(members, supports, loads):
    return {"materials": STEEL, "default_material": "Steel", "mesh": {"size": 100}, "members": members,
            "supports": supports, "loads": loads}


def reaction_sum(R, st="total"):
    return sum(np.asarray(r["states"][st]["F"]) for r in R.reactions)


# --------------------------------------------------------------------------- sections

def test_section_properties():
    p = analysis.section_props({"shape": "RECT", "b": 20, "h": 40})
    assert p["A"] == 800 and abs(p["Ib"] - 20 * 40 ** 3 / 12) < 1e-9 and abs(p["Ia"] - 40 * 20 ** 3 / 12) < 1e-9
    p = analysis.section_props({"shape": "PIPE", "d": 20, "t": 2})
    assert abs(p["A"] - math.pi * (100 - 64)) < 1e-9 and abs(p["J"] - 2 * p["Ia"]) < 1e-9
    p = analysis.section_props({"shape": "I", "b": 100, "h": 200, "tf": 10, "tw": 6})
    assert abs(p["A"] - (2 * 100 * 10 + 180 * 6)) < 1e-9
    assert abs(p["Ib"] - (100 * 200 ** 3 - 94 * 180 ** 3) / 12) < 1e-6
    with pytest.raises(analysis.AnalysisError):
        analysis.section_props({"shape": "BOX", "b": 10, "h": 10, "t": 6})


def test_member_axes():
    t, e1, e2 = analysis.member_axes([0, 0, 0], [1000, 0, 0], [0, 0, 1])
    assert np.allclose(t, [1, 0, 0]) and np.allclose(e2, [0, 0, 1]) and np.allclose(e1, [0, 1, 0])
    t, e1, e2 = analysis.member_axes([0, 0, 0], [0, 0, 500], [0, 0, 1])      # vertical: up replaced
    assert abs(np.dot(t, e2)) < 1e-12 and abs(np.linalg.norm(e1) - 1) < 1e-12


# --------------------------------------------------------------------------- beams and rods

@needs_ccx
def test_cantilever_tip_load(tmp_path):
    EI = 210000.0 * 20 * 40 ** 3 / 12
    doc = beam_doc([{"id": "m1", "name": "C", "kind": "beam", "a": {"xyz": [0, 0, 0]}, "b": {"xyz": [1000, 0, 0]},
                     "section": {"shape": "RECT", "b": 20, "h": 40}, "up": [0, 0, 1]}],
                   [{"id": "s1", "name": "root", "target": {"member": "m1", "end": "a"}, "type": "fixed"}],
                   [{"id": "l1", "name": "P", "type": "force", "target": {"member": "m1", "end": "b"}, "value": [0, 0, -1000]}])
    M, R = solve(doc, [], str(tmp_path))
    tip = M.members[0]["nodes"][-1]
    assert abs(R.U["total"][tip][2] - (-1000 * 1000 ** 3 / (3 * EI))) < 1e-4
    mx = R.members[0]["states"]["total"]["max"]
    assert abs(abs(mx[4]) - 1e6) < 1 and abs(abs(mx[2]) - 1000) < 1e-3
    assert abs(R.members[0]["states"]["total"]["stress"] - 1e6 * 20 / (20 * 40 ** 3 / 12)) < 1e-3
    r = R.reactions[0]["states"]["total"]
    assert np.allclose(r["F"], [0, 0, 1000], atol=1e-2) and abs(abs(r["M"][1]) - 1e6) < 1
    # the same member in a group: the section of the group is used (member section ignored)
    doc["groups"] = [{"id": "g1", "name": "G", "kind": "beam", "section": {"shape": "RECT", "b": 20, "h": 40}}]
    doc["members"][0].update(group="g1", section={"shape": "ROUND", "d": 5})
    M, R = solve(doc, [], str(tmp_path / "g"))
    assert abs(R.U["total"][M.members[0]["nodes"][-1]][2] - (-1000 * 1000 ** 3 / (3 * EI))) < 1e-4
    # payload: the member stress at both ends of every segment (von Mises colours of the members)
    import base64
    st = R.payload()["states"]["total"]
    lvm = np.frombuffer(base64.b64decode(st["lvm"]), dtype=np.float32)
    assert len(lvm) == 2 * len(M.members[0]["elems"]) and abs(lvm.max() - 1e6 * 20 / (20 * 40 ** 3 / 12)) < 1e-2 * lvm.max()
    assert abs(st["vmmax"] - lvm.max()) < 1e-6 * lvm.max()


@needs_ccx
def test_simply_supported_line_load(tmp_path):
    EI = 210000.0 * 20 * 40 ** 3 / 12
    doc = beam_doc([{"id": "m1", "name": "B", "kind": "beam", "a": {"xyz": [0, 0, 0]}, "b": {"xyz": [1000, 0, 0]},
                     "section": {"shape": "RECT", "b": 20, "h": 40}, "up": [0, 0, 1], "n": 10}],
                   [{"id": "s1", "name": "A", "target": {"member": "m1", "end": "a"}, "type": "dofs", "dofs": [1, 1, 1, 1, 0, 0]},
                    {"id": "s2", "name": "B", "target": {"member": "m1", "end": "b"}, "type": "dofs", "dofs": [0, 1, 1, 0, 0, 0]}],
                   [{"id": "l1", "name": "q", "type": "line", "target": {"member": "m1"}, "value": [0, 0, -1]}])
    M, R = solve(doc, [], str(tmp_path))
    mid = M.members[0]["nodes"][5]
    assert abs(R.U["total"][mid][2] - (-5 * 1000.0 ** 4 / (384 * EI))) < 1e-5
    assert abs(abs(R.members[0]["states"]["total"]["max"][4]) - 1000.0 ** 2 / 8) < 1
    for r in R.reactions:
        assert abs(r["states"]["total"]["F"][2] - 500) < 1e-2


@needs_ccx
def test_two_rod_truss(tmp_path):
    rods = [{"id": "r1", "name": "R1", "kind": "rod", "a": {"xyz": [0, 0, 0]}, "b": {"xyz": [100, 0, 100]}, "section": {"shape": "ROUND", "d": 10}},
            {"id": "r2", "name": "R2", "kind": "rod", "a": {"xyz": [200, 0, 0]}, "b": {"xyz": [100, 0, 100]}, "section": {"shape": "ROUND", "d": 10}}]
    doc = beam_doc(rods, [{"id": "s1", "name": "A", "target": {"member": "r1", "end": "a"}, "type": "pinned"},
                          {"id": "s2", "name": "B", "target": {"member": "r2", "end": "a"}, "type": "pinned"},
                          {"id": "s3", "name": "Y", "target": {"member": "r1", "end": "b"}, "type": "dofs", "dofs": [0, 1, 0, 0, 0, 0]}],
                   [{"id": "l1", "name": "P", "type": "force", "target": {"member": "r1", "end": "b"}, "value": [0, 0, -1000]}])
    M, R = solve(doc, [], str(tmp_path))
    for m in R.members:
        assert abs(m["states"]["total"]["max"][0] + 1000 / math.sqrt(2)) < 1e-3
    assert np.allclose(reaction_sum(R), [0, 0, 1000], atol=1e-3)


@needs_ccx
def test_portal_frame_hinge_and_equilibrium(tmp_path):
    sec = {"shape": "I", "b": 100, "h": 200, "tf": 8.5, "tw": 5.6}
    mem = [{"id": "c1", "name": "C1", "kind": "beam", "a": {"xyz": [0, 0, 0]}, "b": {"xyz": [0, 0, 3000]}, "section": sec, "up": [1, 0, 0]},
           {"id": "c2", "name": "C2", "kind": "beam", "a": {"xyz": [4000, 0, 0]}, "b": {"xyz": [4000, 0, 3000]}, "section": sec, "up": [1, 0, 0]},
           {"id": "b1", "name": "B1", "kind": "beam", "a": {"xyz": [0, 0, 3000]}, "b": {"xyz": [4000, 0, 3000]}, "section": sec, "up": [0, 0, 1],
            "release": "ab"}]
    sup = [{"id": "s1", "name": "S1", "target": {"member": "c1", "end": "a"}, "type": "fixed"},
           {"id": "s2", "name": "S2", "target": {"member": "c2", "end": "a"}, "type": "fixed"}]
    loads = [{"id": "q", "name": "q", "type": "line", "target": {"member": "b1"}, "value": [0, 0, -2]},
             {"id": "h", "name": "H", "type": "force", "target": {"member": "c1", "end": "b"}, "value": [1000, 0, 0]}]
    M, R = solve(beam_doc(mem, sup, loads), [], str(tmp_path))
    assert np.allclose(reaction_sum(R) + R.applied("total"), 0, atol=1e-2)          # U1 equilibrium: 1e-5 relative
    # simply supported beam between the hinges: mid-span moment q L^2 / 8, end moments zero
    b = R.members[2]["states"]["total"]
    assert abs(abs(b["max"][4]) - 2 * 4000.0 ** 2 / 8) < 10
    ends = [r["f"][k][4] for r in b["rows"] for k in (0, 4)]
    assert abs(ends[0]) < 1 and abs(ends[-1]) < 1


# --------------------------------------------------------------------------- bodies, fasteners, plates

@needs_ccx
def test_bolted_bonded_blocks_preload(tmp_path):
    from build123d import Box, Cylinder, Pos
    a = Pos(0, 0, 5) * Box(50, 50, 10) - Pos(0, 0, 5) * Cylinder(5, 10)
    b = Pos(0, 0, 15) * Box(50, 50, 10) - Pos(0, 0, 15) * Cylinder(5, 10)
    B = bodies_of({"a": a, "b": b})
    fa = face_index(B[0], lambda r: r["kind"] == "cylinder")
    fb = face_index(B[1], lambda r: r["kind"] == "cylinder")
    bot = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][2]) < 1e-6)
    top = face_index(B[1], lambda r: r["kind"] == "plane" and abs(r["c"][2] - 20) < 1e-6)
    doc = {"materials": STEEL, "default_material": "Steel", "bonded": True,
           "fasteners": [{"id": "f1", "name": "M8", "faces": [{"comp": "a", "face": fa}, {"comp": "b", "face": fb}], "d": 8, "preload": 10000}],
           "supports": [{"id": "s1", "name": "base", "target": {"comp": "a", "face": bot}, "type": "fixed"}],
           "loads": [{"id": "l1", "name": "pull", "type": "force", "target": {"comp": "b", "face": top}, "value": [1000, 0, 5000]},
                     {"id": "g", "name": "g", "type": "gravity", "value": [0, 0, -9810]}]}
    M, R = solve(doc, B, str(tmp_path))
    f = R.fasteners[0]["states"]
    assert abs(f["preload"]["N"] - 10000) < 1e-3
    assert abs(f["total"]["N"] - (10000 + f["loads"]["N"])) < 1e-3
    assert np.allclose(reaction_sum(R, "preload"), 0, atol=1e-3)
    ap = R.applied("total")
    assert abs(ap[2] - (5000 - (a.volume + b.volume) * 7850e-12 * 9810)) < 0.01      # weight from the mesh volume
    assert np.allclose(reaction_sum(R) + ap, 0, atol=1e-3)


@needs_ccx
def test_unbonded_preload_is_refused(tmp_path):
    from build123d import Box, Cylinder, Pos
    a = Pos(0, 0, 5) * Box(50, 50, 10) - Pos(0, 0, 5) * Cylinder(5, 10)
    b = Pos(0, 0, 15) * Box(50, 50, 10) - Pos(0, 0, 15) * Cylinder(5, 10)
    B = bodies_of({"a": a, "b": b})
    fa = face_index(B[0], lambda r: r["kind"] == "cylinder")
    fb = face_index(B[1], lambda r: r["kind"] == "cylinder")
    bot = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][2]) < 1e-6)
    doc = {"materials": STEEL, "default_material": "Steel", "bonded": False,
           "fasteners": [{"id": "f1", "name": "M8", "faces": [{"comp": "a", "face": fa}, {"comp": "b", "face": fb}], "d": 8, "preload": 10000}],
           "supports": [{"id": "s1", "name": "base", "target": {"comp": "a", "face": bot}, "type": "fixed"}], "loads": []}
    with pytest.raises(analysis.AnalysisError, match="no reaction path"):
        solve(doc, B, str(tmp_path))


@needs_ccx
def test_plate_tie_beam_on_face_pressure_moment(tmp_path):
    from build123d import Box, Cylinder, Pos
    a = Pos(0, 0, 10) * Box(80, 50, 20) - Pos(20, 0, 10) * Cylinder(5, 20)
    p = Pos(0, 0, 22) * Box(60, 40, 4) - Pos(20, 0, 22) * Cylinder(5, 4)
    B = bodies_of({"a": a, "p": p}, {"p": "plate"})
    bot = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][2]) < 1e-6)
    side = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][0] + 40) < 1e-6)
    ptop = face_index(B[1], lambda r: r["kind"] == "plane" and abs(r["c"][2] - 24) < 1e-6)
    doc = {"materials": STEEL, "default_material": "Steel", "bonded": True,
           "members": [{"id": "m1", "name": "post", "kind": "beam", "a": {"xyz": [-15, 0, 24], "face": {"comp": "p", "face": ptop}},
                        "b": {"xyz": [-15, 0, 224]}, "section": {"shape": "PIPE", "d": 20, "t": 2}, "up": [1, 0, 0]}],
           "supports": [{"id": "s1", "name": "base", "target": {"comp": "a", "face": bot}, "type": "fixed"}],
           "loads": [{"id": "l1", "name": "tip", "type": "force", "target": {"member": "m1", "end": "b"}, "value": [100, 50, -200]},
                     {"id": "l2", "name": "pr", "type": "pressure", "target": {"comp": "a", "face": side}, "value": 0.5},
                     {"id": "l3", "name": "mom", "type": "moment", "target": {"comp": "p", "face": ptop}, "value": [0, 0, 1000]}]}
    M, R = solve(doc, B, str(tmp_path))
    assert len(M.ties) == 1
    assert {bl["type"] for bl in M.mesh["bodies"]["p"]["blocks"]} <= {"C3D8I", "C3D6"}
    assert np.allclose(M.loads[1]["total"], [0.5 * 50 * 20, 0, 0], atol=1e-6)
    assert np.allclose(reaction_sum(R), [-600, -50, 200], atol=1e-3)
    mz = sum(r["states"]["total"]["M"][2] for r in R.reactions)
    c = R.reactions[0]["states"]["total"]["point"]
    # moment about the support centre: tip load at (-15, 0) plus the 1000 N mm couple
    assert abs(mz + (-15 - c[0]) * 50 - 0 * 100 + 1000) < 2
    mx = R.members[0]["states"]["total"]["max"]
    assert abs(math.hypot(mx[4], mx[5]) - math.hypot(100, 50) * 200) < 1e-2


def test_report_and_payload_without_solver():
    """The input file of a beam model is written without the solver; the mesh payload has the member lines."""
    doc = beam_doc([{"id": "m1", "name": "C", "kind": "beam", "a": {"xyz": [0, 0, 0]}, "b": {"xyz": [100, 0, 0]},
                     "section": {"shape": "ROUND", "d": 10}}],
                   [{"id": "s1", "name": "root", "target": {"member": "m1", "end": "a"}, "type": "fixed"}], [])
    M = analysis.Model(doc, [], {"nodes": {"ids": [], "xyz": []}, "bodies": {}, "warnings": []})
    M.build()
    p = analysis.mesh_payload(M)
    assert p["count"] == 5 and len(p["lines"][0]["segs"]) == 4
    with pytest.raises(analysis.AnalysisError, match="no supports"):
        analysis.Model(dict(doc, supports=[]), [], {"nodes": {"ids": [], "xyz": []}, "bodies": {}, "warnings": []}).build()


# --------------------------------------------------------------------------- API

def _faces(client, asm):
    j = ok(client.post("/api/assembly/build", json={"assembly": asm}))
    return {c["id"]: c["refs"] for c in j["components"]}


def _two_plate_doc(client, name="fea_api"):
    client.put("/api/part/file/fea_plate", json=plate("fea_plate", 100.0, 50.0, 10.0, 5.0))
    asm = {"name": "fea_asm", "components": [
        {"id": "c1", "name": "lower", "source": {"type": "part", "name": "fea_plate"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "c2", "name": "upper", "source": {"type": "part", "name": "fea_plate"}, "pos": [0, 0, 10], "rot": [0, 0, 0]}], "next": 3}
    ok(client.put("/api/assembly/file/fea_asm", json=asm))
    refs = _faces(client, asm)
    cyl = next(i for i, r in enumerate(refs["c1"]) if r and r["kind"] == "cylinder")
    bot = next(i for i, r in enumerate(refs["c1"]) if r and r["kind"] == "plane" and abs(r["c"][2]) < 1e-6)
    top = next(i for i, r in enumerate(refs["c2"]) if r and r["kind"] == "plane" and abs(r["c"][2] - 10) < 1e-6)
    return {"name": name, "source": {"type": "assembly", "name": "fea_asm"}, "materials": STEEL, "default_material": "Steel",
            "mesh": {"size": 8}, "bonded": True, "bodies": {},
            "fasteners": [{"id": "f1", "name": "M10", "faces": [{"comp": "c2", "face": cyl}, {"comp": "c1", "face": cyl}], "d": 10, "preload": 5000}],
            "supports": [{"id": "s1", "name": "base", "target": {"comp": "c1", "face": bot}, "type": "fixed"}],
            "loads": [{"id": "l1", "name": "shear", "type": "force", "target": {"comp": "c2", "face": top}, "value": [500, 0, 0]}],
            "members": []}


def _wait(client, jid, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = ok(client.get("/api/analysis/job/" + jid))
        if s["state"] != "running":
            return s
        time.sleep(0.3)
    raise AssertionError("job did not finish")


@needs_ccx
def test_api_save_run_results_report(client, web):
    doc = _two_plate_doc(client)
    ok(client.put("/api/analysis/file/fea_api", json=doc))
    assert "fea_api" in ok(client.get("/api/analysis/list"))
    s = _wait(client, ok(client.post("/api/analysis/run", json={"name": "fea_api", "analysis": doc, "mesh_only": True}))["job"])
    assert s["state"] == "done", s
    assert s["result"]["summary"]["nodes"] > 100 and s["result"]["mesh_only"]
    s = _wait(client, ok(client.post("/api/analysis/run", json={"name": "fea_api", "analysis": doc}))["job"])
    assert s["state"] == "done", s
    r = s["result"]
    assert set(r["states"]) == {"total", "preload", "loads"}
    t = r["tables"]
    assert abs(t["preload"]["fasteners"][0]["N"] - 5000) < 1e-3
    F = np.sum([x["F"] for x in t["total"]["reactions"]], axis=0)
    assert np.allclose(F + np.asarray(t["total"]["applied"]), 0, atol=1e-3)
    saved = ok(client.get("/api/analysis/results/fea_api"))
    assert saved["tables"]["total"]["fasteners"][0]["name"] == "M10"
    rep = client.get("/api/analysis/report/fea_api")
    assert rep.status_code == 200 and b"ANALYSIS REPORT" in rep.data and b"Fasteners" in rep.data
    docs = ok(client.get("/api/project/docs"))["docs"]
    d = next(x for x in docs if x["type"] == "analysis" and x["name"] == "fea_api")
    assert d["links"] == [{"type": "assembly", "name": "fea_asm"}]


def test_api_errors(client):
    doc = {"name": "fea_bad", "source": {"type": "assembly", "name": "fea_asm_missing"}, "materials": STEEL,
           "default_material": "Steel", "members": [], "fasteners": [], "supports": [], "loads": []}
    s = _wait(client, ok(client.post("/api/analysis/run", json={"name": "fea_bad", "analysis": doc}))["job"])
    assert s["state"] == "error" and s["error"]
    j = ok(client.post("/api/analysis/sections", json={"section": {"shape": "PIPE", "d": 10, "t": 6}}))
    assert "error" in j
    assert "path" in ok(client.get("/api/analysis/solver"))


# --------------------------------------------------------------------------- plate items

def _plate_body(p):
    return analysis.plate_body(p, None, {"default_material": "Steel"})


def _ref(body, pred):
    return {"comp": body["id"], "face": face_index(body, pred)}


def test_plate_solid_from_points_and_errors():
    sol, n = analysis.plate_solid({"id": "p", "t": 10, "points": [[0, 0, 0], [100, 0, 0], [100, 50, 0], [0, 50, 0]]}, None)
    bb = sol.bounding_box()
    assert abs(sol.volume - 100 * 50 * 10) < 1e-6 and abs(bb.min.Z + 5) < 1e-9 and np.allclose(n, [0, 0, 1])
    sol, n = analysis.plate_solid({"id": "p", "t": 10, "position": "positive",
                                   "points": [[0, 0, 0], [0, 50, 0], [100, 50, 0], [100, 0, 0]]}, None)
    assert np.allclose(n, [0, 0, -1]) and abs(sol.bounding_box().min.Z + 10) < 1e-9
    with pytest.raises(analysis.AnalysisError, match="not in one plane"):
        analysis.plate_solid({"id": "p", "t": 10, "points": [[0, 0, 0], [100, 0, 0], [100, 50, 1], [0, 50, 0]]}, None)
    with pytest.raises(analysis.AnalysisError, match="thickness"):
        analysis.plate_solid({"id": "p", "t": 0, "points": [[0, 0, 0], [100, 0, 0], [0, 50, 0]]}, None)


@needs_ccx
def test_plate_cantilever_by_points(tmp_path):
    P = _plate_body({"id": "p1", "name": "P1", "t": 10, "points": [[0, 0, 0], [500, 0, 0], [500, 100, 0], [0, 100, 0]], "size": 20})
    doc = {"materials": STEEL, "default_material": "Steel", "bonded": True,
           "supports": [{"id": "s", "name": "root", "target": _ref(P, lambda r: r["kind"] == "plane" and abs(r["c"][0]) < 1e-6), "type": "fixed"}],
           "loads": [{"id": "l", "name": "tip", "type": "force", "value": [0, 0, -100],
                      "target": _ref(P, lambda r: r["kind"] == "plane" and abs(r["c"][0] - 500) < 1e-6)}]}
    M, R = solve(doc, [P], str(tmp_path), size=20)
    assert {bl["type"] for bl in M.mesh["bodies"][P["id"]]["blocks"]} <= {"C3D8I", "C3D6"}
    EI = 210000.0 * 100 * 10 ** 3 / 12
    uz = min(u[2] for u in R.U["total"].values())
    beam = -100 * 500.0 ** 3 / (3 * EI)
    assert beam <= uz <= beam * (1 - 0.3 ** 2)          # between beam theory and plate theory (D = E t^3 / 12 (1 - nu^2))
    assert np.allclose(reaction_sum(R), [0, 0, 100], atol=1e-6)


@needs_ccx
def test_plate_t_joint_and_beam_on_plate(tmp_path):
    A = _plate_body({"id": "a", "name": "A", "t": 10, "points": [[0, 0, 0], [300, 0, 0], [300, 200, 0], [0, 200, 0]]})
    B = _plate_body({"id": "b", "name": "B", "t": 8, "points": [[100, 50, 0], [100, 150, 0], [100, 150, 100], [100, 50, 100]]})
    doc = {"materials": STEEL, "default_material": "Steel", "bonded": True,
           "supports": [{"id": "s", "name": "bottom", "target": _ref(A, lambda r: r["kind"] == "plane" and abs(r["c"][2] + 5) < 1e-6), "type": "fixed"}],
           "loads": [{"id": "l", "name": "top", "type": "force", "value": [1000, 0, -500],
                      "target": _ref(B, lambda r: r["kind"] == "plane" and abs(r["c"][2] - 100) < 1e-6)},
                     {"id": "l2", "name": "post", "type": "force", "target": {"member": "m", "end": "b"}, "value": [0, 100, 0]}],
           "members": [{"id": "m", "name": "post", "kind": "beam", "section": {"shape": "ROUND", "d": 20},
                        "a": {"xyz": [250, 100, 5], "r": 15, "face": _ref(A, lambda r: r["kind"] == "plane" and abs(r["c"][2] - 5) < 1e-6)},
                        "b": {"xyz": [250, 100, 200]}}]}
    M, R = solve(doc, [A, B], str(tmp_path), size=10)
    assert len(M.ties) == 1 and M.ties[0]["bodies"] == (B["id"], A["id"])
    assert np.allclose(reaction_sum(R) + R.applied("total"), 0, atol=1e-2)
    # the post is connected to the nodes within 15 mm only: its root moment equals 100 N x 195 mm
    assert abs(math.hypot(*R.members[0]["states"]["total"]["max"][4:]) - 100 * 195) < 1e-2


@needs_ccx
def test_api_plates_without_geometry(client):
    doc = {"name": "fea_deck", "source": {"type": "assembly", "name": ""}, "materials": STEEL, "default_material": "Steel",
           "mesh": {"size": 25}, "bonded": True, "bodies": {}, "fasteners": [],
           "plates": [{"id": "p1", "name": "Deck", "t": 8, "position": "mid",
                       "points": [[0, 0, 1000], [1000, 0, 1000], [1000, 600, 1000], [0, 600, 1000]]}]}
    pv = ok(client.post("/api/analysis/plates", json={"analysis": doc}))["plates"]
    assert pv[0]["id"] == "plate_p1" and pv[0]["refs"] and pv[0]["mkey"]
    bot = next(i for i, r in enumerate(pv[0]["refs"]) if r["kind"] == "plane" and abs(r["c"][2] - 996) < 1e-6)
    doc["members"] = [{"id": "c%d" % i, "name": "Col %d" % i, "kind": "beam", "section": {"shape": "BOX", "b": 80, "h": 80, "t": 5},
                       "up": [1, 0, 0], "a": {"xyz": [x, y, 0]}, "b": {"xyz": [x, y, 996], "face": {"comp": "plate_p1", "face": bot}, "r": 60}}
                      for i, (x, y) in enumerate([(50, 50), (950, 50), (950, 550), (50, 550)])]
    doc["supports"] = [{"id": "s%d" % i, "name": "S%d" % i, "target": {"member": "c%d" % i, "end": "a"}, "type": "fixed"} for i in range(4)]
    doc["loads"] = [{"id": "g", "name": "g", "type": "gravity", "value": [0, 0, -9810]}]
    s = _wait(client, ok(client.post("/api/analysis/run", json={"name": "fea_deck", "analysis": doc}))["job"])
    assert s["state"] == "done", s
    t = s["result"]["tables"]["total"]
    F = np.sum([x["F"] for x in t["reactions"]], axis=0)
    weight = 7850e-12 * 9810 * (1000 * 600 * 8 + 4 * (80 ** 2 - 70 ** 2) * 996)
    assert abs(F[2] - weight) < 1e-3 * weight and np.allclose(F + np.asarray(t["applied"]), 0, atol=1e-2)



@needs_ccx
@pytest.mark.parametrize("mesh", [{"strategy": "tet"}, {"strategy": "tet", "tet_type": "C3D4"},
                                  {"strategy": "hex", "hex_type": "C3D8I"}, {"strategy": "hex", "hex_type": "C3D20R"},
                                  {"strategy": "hexsub", "hex_type": "C3D8I"}, {"strategy": "hex", "hex_type": "C3D8"}])
def test_mesh_strategies_cantilever_block(tmp_path, mesh):
    """Block 100 x 20 x 10 mm fixed at x = 0, 100 N along -z at x = 100: tip deflection F L^3 / (3 E I) = 0.0952 mm
    within 6 % for tetrahedra (C3D10), structured hexahedra (C3D8I, C3D20R) and subdivision hexahedra (C3D8I);
    first order C3D4 and C3D8 are stiffer (shear locking) and only checked for the element type and equilibrium."""
    from build123d import Box, Pos
    blk = Pos(50, 10, 5) * Box(100, 20, 10)
    B = bodies_of({"b": blk})
    root = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][0]) < 1e-6)
    tip = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][0] - 100) < 1e-6)
    doc = {"materials": STEEL, "default_material": "Steel", "mesh": dict(mesh, size=5.0),
           "supports": [{"id": "s1", "name": "root", "target": {"comp": "b", "face": root}, "type": "fixed"}],
           "loads": [{"id": "l1", "name": "tip", "type": "force", "target": {"comp": "b", "face": tip}, "value": [0, 0, -100]}]}
    M, R = solve(doc, B, str(tmp_path), size=5.0)
    types = {bl["type"] for bl in M.mesh["bodies"]["b"]["blocks"]}
    want = mesh.get("hex_type") if mesh["strategy"] != "tet" else mesh.get("tet_type", "C3D10")
    assert types == {want}, types
    assert np.allclose(reaction_sum(R) + R.applied("total"), 0, atol=1e-3)
    tipn = [n for n in M.face({"comp": "b", "face": tip})["nodes"]]
    uz = np.mean([R.U["total"][n][2] for n in tipn])
    ref = 100 * 100.0 ** 3 / (3 * 210000 * 20 * 10.0 ** 3 / 12)
    if mesh["strategy"] == "hex":
        # view data: element edges of the quadrangle faces without diagonals (each edge along one axis)
        import base64
        pl = R.payload()
        pos = np.frombuffer(base64.b64decode(pl["pos"]), dtype=np.float32).reshape(-1, 3)
        ed = np.frombuffer(base64.b64decode(pl["edges"]), dtype=np.uint32).reshape(-1, 2)
        dv = np.abs(pos[ed[:, 0]] - pos[ed[:, 1]]) > 1e-4
        assert len(ed) and (dv.sum(1) == 1).all()
    if want not in ("C3D4", "C3D8"):
        assert abs(-uz / ref - 1) < 0.06, (uz, ref)
    else:
        assert 0 < -uz < ref


@needs_ccx
def test_prescribed_displacement_and_tie_between_mesh_groups(tmp_path):
    """Two blocks stacked: the lower one structured hexahedra, the upper one tetrahedra, tied at the common face.
    Lower base fixed, upper top face given uz = 0.01 mm (displacement support) and the normal support with a value:
    the reaction of the prescribed face equals the base reaction with the opposite sign; the face moves by the
    prescribed value."""
    from build123d import Box, Pos
    lo = Pos(0, 0, 5) * Box(40, 40, 10)
    up = Pos(0, 0, 15) * Box(40, 40, 10)
    B = bodies_of({"lo": lo, "up": up})
    B[0]["strategy"] = "hex"
    bot = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][2]) < 1e-6)
    top = face_index(B[1], lambda r: r["kind"] == "plane" and abs(r["c"][2] - 20) < 1e-6)
    doc = {"materials": STEEL, "default_material": "Steel", "bonded": True, "mesh": {"size": 5.0},
           "supports": [{"id": "s1", "name": "base", "target": {"comp": "lo", "face": bot}, "type": "fixed"},
                        {"id": "s2", "name": "lift", "target": {"comp": "up", "face": top}, "type": "displacement",
                         "dofs": [0, 0, 1], "value": [0, 0, 0.01]}],
           "loads": []}
    M, R = solve(doc, B, str(tmp_path), size=5.0)
    assert len(M.ties) == 1 and M.mesh["bodies"]["lo"]["group"] == "hex"
    tn = M.face({"comp": "up", "face": top})["nodes"]
    assert np.allclose([R.U["total"][n][2] for n in tn], 0.01, atol=1e-9)
    rb = next(r for r in R.reactions if r["name"] == "base")["states"]["total"]["F"]
    rt = next(r for r in R.reactions if r["name"] == "lift")["states"]["total"]["F"]
    assert rt[2] > 1.0e5 and abs(rb[2] + rt[2]) < 1e-3 * abs(rt[2])      # E A u / L = 168 kN without the lateral restraint
    # the same lift as a normal support with a value along the outward normal (+z)
    doc["supports"][1] = {"id": "s2", "name": "lift", "target": {"comp": "up", "face": top}, "type": "normal", "value": 0.01}
    M2, R2 = solve(doc, B, str(tmp_path / "n"), size=5.0)
    rt2 = next(r for r in R2.reactions if r["name"] == "lift")["states"]["total"]["F"]
    assert abs(rt2[2] / rt[2] - 1) < 0.05


@needs_ccx
def test_plate_on_beams_is_tied(tmp_path):
    """A triangular plate (1 mm, outline points) whose two edges are beams: the beam nodes along the edges are
    tied to the plate; the plate carries load (stress above 0) and the model is in equilibrium."""
    P = _plate_body({"id": "p", "name": "P", "t": 1, "points": [[0, 0, 0], [250, 0, 0], [200, 0, 100]]})
    sec = {"shape": "PIPE", "d": 10, "t": 1}
    doc = {"materials": STEEL, "default_material": "Steel", "bonded": True,
           "members": [{"id": "m1", "name": "B1", "kind": "beam", "section": sec, "a": {"xyz": [0, 0, 0]}, "b": {"xyz": [200, 0, 100]}, "up": [0, 1, 0]},
                       {"id": "m2", "name": "B2", "kind": "beam", "section": sec, "a": {"xyz": [200, 0, 100]}, "b": {"xyz": [250, 0, 0]}, "up": [0, 1, 0]}],
           "supports": [{"id": "s1", "name": "A", "target": {"member": "m1", "end": "a"}, "type": "fixed"},
                        {"id": "s2", "name": "B", "target": {"member": "m2", "end": "b"}, "type": "fixed"}],
           "loads": [{"id": "l1", "name": "top", "type": "force", "target": {"member": "m1", "end": "b"}, "value": [0, 0, -1000]}]}
    M, R = solve(doc, [P], str(tmp_path), size=10)
    t = [x for x in M.ties if x["bodies"][0] == "members"]
    assert len(t) == 1 and len(t[0]["nodes"]) > 10
    assert np.allclose(reaction_sum(R) + R.applied("total"), 0, atol=1e-2)
    smax = max(analysis.von_mises(R.S["total"][n]) for bl in M.mesh["bodies"]["plate_p"]["blocks"] for e in bl["elements"] for n in e[1:] if n in R.S["total"])
    assert smax > 1.0


@needs_ccx
def test_reference_point_rigid_and_face_rotation_support(tmp_path):
    """Block 100 x 20 x 20 mm fixed at x = 0. A reference point at (150, 10, 10) rigidly connected to the end face
    x = 100 carries 100 N along -z: the root reaction moment is 100 N x 150 mm; the reference point moves by
    the tip motion plus the end rotation times 50 mm. A torque on the reference point gives the reaction torque. A
    face support with rotation components (kinematic coupling) holds the end face rotation at 0. A beam end at
    the reference point follows it (rotations included)."""
    from build123d import Box, Pos
    blk = Pos(50, 10, 10) * Box(100, 20, 20)
    B = bodies_of({"b": blk})
    root = {"comp": "b", "face": face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][0]) < 1e-6)}
    tip = {"comp": "b", "face": face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][0] - 100) < 1e-6)}
    doc = {"materials": STEEL, "default_material": "Steel", "mesh": {"size": 5.0},
           "points": [{"id": "rp", "name": "RP", "xyz": [150, 10, 10], "faces": [tip]}],
           "supports": [{"id": "s1", "name": "root", "target": root, "type": "fixed"}],
           "loads": [{"id": "l1", "name": "P", "type": "force", "target": {"point": "rp"}, "value": [0, 0, -100]},
                     {"id": "l2", "name": "T", "type": "moment", "target": {"point": "rp"}, "value": [5000, 0, 0]}]}
    M, R = solve(doc, B, str(tmp_path), size=5.0)
    r = R.reactions[0]["states"]["total"]
    assert np.allclose(r["F"], [0, 0, 100], atol=1e-2)
    c = r["point"]
    m_exp = -np.cross(np.array([150, 10, 10]) - c, [0, 0, -100]) - np.array([5000, 0, 0])
    assert np.allclose(r["M"], m_exp, atol=1.0), (r["M"], m_exp)
    pt = R.tables()["total"]["points"][0]
    assert pt["u"][2] < 0 and abs(pt["rot"][0]) > 0
    rep = analysis.report(R, {"name": "rp"})
    assert "Reference points" in rep and "ref. point" not in rep
    # face support with rotations: end face rotation about y held (kinematic coupling), translations free
    doc2 = dict(doc, points=[], loads=[{"id": "l1", "name": "P", "type": "force", "target": tip, "value": [0, 0, -100]}],
                supports=[doc["supports"][0], {"id": "s2", "name": "guide", "target": tip, "type": "dofs", "dofs": [0, 0, 0, 1, 1, 1]}])
    M2, R2 = solve(doc2, B, str(tmp_path / "f"), size=5.0)
    g = next(x for x in R2.reactions if x["name"] == "guide")["states"]["total"]
    assert abs(g["M"][1]) > 100 and np.allclose(g["F"], 0, atol=1e-3)
    assert np.allclose(reaction_sum(R2) + R2.applied("total"), 0, atol=1e-2)
    # beam end at the reference point: a moment at the beam tip reaches the block
    doc3 = dict(doc, loads=[{"id": "l1", "name": "Mb", "type": "moment", "target": {"member": "m", "end": "b"}, "value": [0, 1000, 0]}],
                members=[{"id": "m", "name": "arm", "kind": "beam", "section": {"shape": "ROUND", "d": 10}, "a": {"xyz": [150, 10, 10]},
                          "b": {"xyz": [250, 10, 10]}, "up": [0, 0, 1]}])
    M3, R3 = solve(doc3, B, str(tmp_path / "b"), size=5.0)
    assert abs(R3.reactions[0]["states"]["total"]["M"][1] + 1000) < 1.0
    # beam end connected to the end face with a rigid coupling (instead of RBE3)
    doc4 = dict(doc3, points=[], members=[dict(doc3["members"][0], a={"xyz": [100, 10, 10], "face": tip, "coupling": "rigid"})])
    M4, R4 = solve(doc4, B, str(tmp_path / "c"), size=5.0)
    assert abs(R4.reactions[0]["states"]["total"]["M"][1] + 1000) < 1.0
    tn = M4.face(tip)["nodes"]
    ux = np.array([R4.U["total"][n][0] for n in tn])
    zz = np.array([M4.X[n][2] - 10 for n in tn])
    assert np.allclose(ux, np.polyval(np.polyfit(zz, ux, 1), zz), atol=1e-8)          # the face stays plane


def test_plate_groups_resolve():
    """A plate in a plate group takes thickness, material and element size from the group."""
    doc = {"plate_groups": [{"id": "g", "name": "skin", "t": 4, "material": "Aluminium"}],
           "plates": [{"id": "p1", "name": "P1", "t": 1, "size": 7, "group": "g", "points": []}, {"id": "p2", "name": "P2", "t": 2}]}
    a, b = analysis.resolve_plate_groups(doc)
    assert (a["t"], a["material"], a.get("size")) == (4, "Aluminium", None) and b["t"] == 2


# --------------------------------------------------------------------------- modal and buckling

def _bar(L=200.0, b=20.0, h=10.0):
    from build123d import Box, Pos
    B = bodies_of({"bar": Pos(L / 2, b / 2, h / 2) * Box(L, b, h)})
    root = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][0]) < 1e-6)
    tip = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][0] - L) < 1e-6)
    return B, root, tip


@needs_ccx
def test_modal_cantilever_bar(tmp_path):
    """Bar 200 x 20 x 10 mm clamped at x = 0: f = 1.875^2 / (2 pi) sqrt(E I / (rho A L^4)), 1st mode bending about the
    thin direction (I = 20 x 10^3 / 12), 2nd about the wide direction (twice the frequency). Effective mass of the
    1st mode in z about 61 % (Euler-Bernoulli cantilever: 0.613)."""
    B, root, tip = _bar()
    doc = {"materials": STEEL, "default_material": "Steel", "mesh": {"size": 5.0}, "analysis_type": "modal", "modes": 4,
           "supports": [{"id": "s1", "name": "root", "target": {"comp": "bar", "face": root}, "type": "fixed"}],
           "loads": [{"id": "l1", "name": "tip", "type": "force", "target": {"comp": "bar", "face": tip}, "value": [0, 0, -100]}]}
    M, R = solve(doc, B, str(tmp_path), size=5.0)
    assert "*FREQUENCY" in open(os.path.join(str(tmp_path), "job.inp")).read()
    E, rho, A, L = 210000.0, 7.85e-9, 200.0, 200.0
    f = lambda I: 1.875 ** 2 / (2 * math.pi) * math.sqrt(E * I / (rho * A * L ** 4))
    md = R.modes()
    assert len(md) == 4 and list(R.state_steps) == ["m1", "m2", "m3", "m4"]
    assert abs(md[0]["value"] / f(20 * 10 ** 3 / 12) - 1) < 0.03, md
    assert abs(md[1]["value"] / f(10 * 20 ** 3 / 12) - 1) < 0.03, md
    assert abs(md[0]["frac"][2] - 0.613) < 0.03 and md[0]["frac"][1] < 0.01
    # mode shape: normalised, largest at the tip, along z
    U = R.U["m1"]
    assert abs(max(float(np.linalg.norm(u)) for u in U.values()) - 1) < 1e-9
    tn = M.face({"comp": "bar", "face": tip})["nodes"]
    assert np.mean([abs(U[n][2]) for n in tn]) > 0.95
    rep = analysis.report(R, {"name": "modal"})
    assert "Natural frequencies" in rep and "Modal (natural frequencies)" in rep and "Eff. mass z (%)" in rep
    tb = R.tables()
    assert tb["m1"]["mode"]["mode"] == 1 and tb["m2"]["bodies"][0]["umax"] == pytest.approx(1.0, abs=1e-6)
    pl = R.payload()
    assert set(pl["states"]) == {"m1", "m2", "m3", "m4"}


@needs_ccx
def test_buckling_column(tmp_path):
    """Bar 200 x 20 x 10 mm clamped at x = 0, 1000 N compression at x = 200: Euler P = pi^2 E I / (4 L^2) with
    I = 20 x 10^3 / 12, buckling factor P / 1000."""
    B, root, tip = _bar()
    doc = {"materials": STEEL, "default_material": "Steel", "mesh": {"size": 5.0}, "analysis_type": "buckling", "modes": 2,
           "supports": [{"id": "s1", "name": "root", "target": {"comp": "bar", "face": root}, "type": "fixed"}],
           "loads": [{"id": "l1", "name": "tip", "type": "force", "target": {"comp": "bar", "face": tip}, "value": [-1000, 0, 0]}]}
    M, R = solve(doc, B, str(tmp_path), size=5.0)
    P = math.pi ** 2 * 210000.0 * (20 * 10 ** 3 / 12) / (4 * 200.0 ** 2)
    md = R.modes()
    assert abs(md[0]["value"] / (P / 1000) - 1) < 0.04, (md, P)
    assert "Buckling factors" in analysis.report(R, {"name": "buckle"})


def test_modal_and_buckling_refusals():
    B, root, tip = _bar()
    mesh = {"nodes": {"ids": [], "xyz": []}, "bodies": {}, "warnings": []}
    sup = [{"id": "s1", "name": "root", "target": {"member": "m1", "end": "a"}, "type": "fixed"}]
    mem = [{"id": "m1", "name": "beam1", "kind": "beam", "a": {"xyz": [0, 0, 0]}, "b": {"xyz": [100, 0, 0]},
            "section": {"shape": "ROUND", "d": 10}}]
    doc = {"materials": STEEL, "default_material": "Steel", "analysis_type": "modal", "members": mem, "supports": sup, "loads": []}
    with pytest.raises(analysis.AnalysisError, match="beams and fasteners"):
        analysis.Model(doc, [], mesh).build()
    rod = [dict(mem[0], kind="rod")]
    nod = {"materials": {"Steel": {"E": 210000.0, "nu": 0.3, "rho": 0}}, "default_material": "Steel",
           "analysis_type": "modal", "members": rod, "supports": sup, "loads": []}
    with pytest.raises(analysis.AnalysisError, match="no density"):
        analysis.Model(nod, [], mesh).build()
    with pytest.raises(analysis.AnalysisError, match="no loads"):
        analysis.Model(dict(nod, analysis_type="buckling"), [], mesh).build()
    with pytest.raises(analysis.AnalysisError, match="unknown analysis type"):
        analysis.Model(dict(nod, analysis_type="dynamic"), [], mesh)


# --------------------------------------------------------------------------- shells (surface bodies)

def _surf(fid, name, plane, w, h, x=0.0, y=0.0):
    from conftest import rect
    return {"id": fid, "name": name, "type": "surf_sketch", "kind": "planar", "plane": plane, "offset": 0,
            "sketch": {"entities": rect(w, h, x, y)}}


def _edge_at(erefs, axis, value, M=None):
    """Index of the straight edge whose midpoint has coordinate axis = value (local coordinates)."""
    return next(i for i, r in enumerate(erefs) if r and r["kind"] == "line" and abs(r["c"][axis] - value) < 1e-6)


def _shell_doc(name, shells, supports, loads, **kw):
    d = {"name": name, "materials": STEEL, "default_material": "Steel", "mesh": {"size": 5}, "bonded": True,
         "bodies": {}, "shells": shells, "members": [], "plates": [], "fasteners": [], "supports": supports, "loads": loads}
    d.update(kw)
    return d


def _cantilever(client, name="sh_cant"):
    ok(client.put("/api/part/file/" + name, json={"name": name, "version": 2, "next": 2, "features": [_surf("s1", "Plate", "XY", 100, 20)]}))
    asm = {"components": [{"id": "1", "name": name, "source": {"type": "part", "name": name}, "pos": [0, 0, 0], "rot": [0, 0, 0]}]}
    c = ok(client.post("/api/assembly/build", json={"assembly": asm}))["components"][0]
    return c, _edge_at(c["erefs"], 0, 0.0), _edge_at(c["erefs"], 0, 100.0)


@needs_ccx
@pytest.mark.parametrize("stype", ["S4", "S8R"])
def test_shell_cantilever_edge_support_and_line_load(client, web, tmp_path, stype):
    """Surface body 100 x 20 mm, t 2 mm, clamped edge (fixed: all six), line load on the free edge (total 10 N):
    tip deflection within 10 % of the plate solution (beam: F L^3 / (3 E I) times 1 - nu^2), root bending stress
    within 10 % of 6 F L / (b t^2), reaction equal to the load."""
    c, e0, e1 = _cantilever(client)
    doc = _shell_doc("sh_cant", {"1:s1": {"t": 2}},
                     [{"id": "s1", "name": "root", "target": {"comp": "1", "edge": e0}, "type": "fixed"}],
                     [{"id": "l1", "name": "tip", "type": "line", "target": {"comp": "1", "edge": e1}, "value": [0, 0, -0.5]}],
                     source={"type": "part", "name": "sh_cant"}, mesh={"size": 5, "shell_type": stype})
    asm = web._fea_asm(doc)
    r = analysis.run(doc, asm, web._asm_sources(), str(tmp_path), CCX, meta={"name": "sh_cant"})
    t = r["tables"]["total"]
    assert r["summary"]["bodies"][0]["types"][0] == stype
    w = 10.0 * 100 ** 3 / (3 * 210000.0 * 20 * 2 ** 3 / 12) * (1 - 0.3 ** 2)
    assert t["bodies"][0]["umax"] == pytest.approx(w, rel=0.1)
    assert t["bodies"][0]["smax"] == pytest.approx(6 * 10.0 * 100 / (20 * 2 ** 2), rel=0.1)
    assert np.allclose(t["reactions"][0]["F"], [0, 0, 10.0], atol=1e-3) and np.allclose(t["applied"], [0, 0, -10.0], atol=1e-6)
    text = open(r["files"]["inp"]).read()
    assert "*SHELL SECTION, ELSET=B1_s1_1, MATERIAL=M1_Steel, OFFSET=0" in text and "SUP1R, 4, 4" in text


@needs_ccx
def test_shell_symmetry_pinned_and_modal(client, web, tmp_path):
    """Half of a simply supported strip with a symmetry edge: pinned edge (ux uy uz) at x = 0, symmetry X (ux, ry,
    rz) at x = 50, pressure 0.01 MPa: mid-span deflection 5 q L^4 / (384 D) of the full span 100 mm within 10 %.
    Modal: first natural frequency of the clamped strip (1.875^2 / (2 pi L^2) sqrt(D / (rho t))) within 5 %."""
    ok(client.put("/api/part/file/sh_half", json={"name": "sh_half", "version": 2, "next": 2, "features": [_surf("s1", "Strip", "XY", 50, 20)]}))
    asm = {"components": [{"id": "1", "name": "half", "source": {"type": "part", "name": "sh_half"}, "pos": [0, 0, 0], "rot": [0, 0, 0]}]}
    c = ok(client.post("/api/assembly/build", json={"assembly": asm}))["components"][0]
    e0, e1 = _edge_at(c["erefs"], 0, 0.0), _edge_at(c["erefs"], 0, 50.0)
    y0, y1 = _edge_at(c["erefs"], 1, 0.0), _edge_at(c["erefs"], 1, 20.0)
    sups = [{"id": "a", "name": "pin", "target": {"comp": "1", "edge": e0}, "type": "pinned"},
            {"id": "b", "name": "sym", "target": {"comp": "1", "edge": e1}, "type": "xsymm"},
            {"id": "c", "name": "cyl1", "target": {"comp": "1", "edge": y0}, "type": "dofs", "dofs": [0, 1, 0, 1, 0, 0]},
            {"id": "d", "name": "cyl2", "target": {"comp": "1", "edge": y1}, "type": "dofs", "dofs": [0, 1, 0, 1, 0, 0]}]
    doc = _shell_doc("sh_half", {"1:s1": {"t": 2}}, sups,
                     [{"id": "p", "name": "p", "type": "pressure", "target": {"comp": "1", "face": 0}, "value": 0.01}],
                     mesh={"size": 2.5})
    r = analysis.run(doc, asm, web._asm_sources(), str(tmp_path / "s"), CCX, meta={"name": "sh_half"})
    D = 210000.0 * 2 ** 3 / (12 * (1 - 0.09))
    w = 5 * 0.01 * 100 ** 4 / (384 * D)
    assert r["tables"]["total"]["bodies"][0]["umax"] == pytest.approx(w, rel=0.1)
    text = open(r["files"]["inp"]).read()
    assert "SUP2, 1, 1" in text and "SUP2R, 5, 5" in text and "SUP2R, 6, 6" in text and "SUP1R" not in text
    # modal: the strip clamped at x = 0 (the full 50 mm as cantilever)
    m = _shell_doc("sh_modal", {"1:s1": {"t": 2}}, [{"id": "a", "name": "clamp", "target": {"comp": "1", "edge": e0}, "type": "fixed"}], [],
                   mesh={"size": 2.5}, analysis_type="modal", modes=2)
    r = analysis.run(m, asm, web._asm_sources(), str(tmp_path / "m"), CCX, meta={"name": "sh_modal"})
    f1 = 1.875 ** 2 / (2 * math.pi * 50.0 ** 2) * math.sqrt(D / (7850e-12 * 2))
    assert r["modes"][0]["value"] == pytest.approx(f1, rel=0.05)


@needs_ccx
def test_shells_of_two_parts_bonded_and_tied_to_a_solid(client, web, tmp_path):
    """Deck (surface XY 200 x 100) and web (surface XZ 200 x 40, turned 180 deg about X, hanging below the deck at
    y = 50) as two parts: the shells share the nodes of their junction line (one mesh group, fragmented); a solid
    block under the deck end is tied to the deck. Sum of the reactions equal to the applied loads (weight and
    pressure)."""
    ok(client.put("/api/part/file/sh_deck", json={"name": "sh_deck", "version": 2, "next": 2, "features": [_surf("s1", "Deck", "XY", 200, 100)]}))
    ok(client.put("/api/part/file/sh_web", json={"name": "sh_web", "version": 2, "next": 2, "features": [_surf("w", "Web", "XZ", 200, 40)]}))
    ok(client.put("/api/part/file/sh_blk", json=plate("sh_blk", 40, 100, 30, 0)))
    asm = {"components": [
        {"id": "1", "name": "deck", "source": {"type": "part", "name": "sh_deck"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "web", "source": {"type": "part", "name": "sh_web"}, "pos": [0, 50, 0], "rot": [180, 0, 0]},
        {"id": "3", "name": "block", "source": {"type": "part", "name": "sh_blk"}, "pos": [160, 0, -30], "rot": [0, 0, 0]}]}
    cs = {c["id"]: c for c in ok(client.post("/api/assembly/build", json={"assembly": asm}))["components"]}
    x0 = _edge_at(cs["1"]["erefs"], 0, 0.0)
    bot = next(i for i, r in enumerate(cs["3"]["refs"]) if r["kind"] == "plane" and abs(r["c"][2]) < 1e-6)
    doc = _shell_doc("sh_t", {"1:s1": {"t": 8}, "2:w": {"t": 6, "offset": "negative"}},
                     [{"id": "s1", "name": "root", "target": {"comp": "1", "edge": x0}, "type": "fixed"},
                      {"id": "s2", "name": "blk", "target": {"comp": "3", "face": bot}, "type": "fixed"}],
                     [{"id": "g", "name": "g", "type": "gravity", "value": [0, 0, -9810]},
                      {"id": "p", "name": "p", "type": "pressure", "target": {"comp": "1", "face": 0}, "value": 0.01}],
                     mesh={"size": 10})
    sources = web._asm_sources()
    bodies = analysis.geometry(doc, asm, sources)
    assert [(b["id"], b["mode"]) for b in bodies] == [("1:s1", "shell"), ("2:w", "shell"), ("3", "solid")]
    r = analysis.run(doc, asm, sources, str(tmp_path), CCX, meta={"name": "sh_t"})
    assert r["summary"]["ties"] >= 1
    t = r["tables"]["total"]
    F = np.sum([x["F"] for x in t["reactions"]], axis=0)
    assert np.allclose(F + np.asarray(t["applied"]), 0, atol=1e-3 * abs(t["applied"][2]))
    W = 7850e-12 * 9810 * (200 * 100 * 8 + 200 * 40 * 6 + 40 * 100 * 30)
    assert -t["applied"][2] == pytest.approx(W + 0.01 * 200 * 100, rel=1e-3)
    text = open(r["files"]["inp"]).read()
    assert "OFFSET=-0.5" in text and "*TIE" in text
    # junction line: deck and web elements share nodes on y = 50, z = 0
    import re as _re
    nodes = {int(a): (float(b), float(c), float(d)) for a, b, c, d in _re.findall(r"^(\d+), ([-\d.e+]+), ([-\d.e+]+), ([-\d.e+]+)$", text.split("*ELEMENT")[0], _re.M)}
    blocks = _re.findall(r"\*ELEMENT, TYPE=S4, ELSET=(B\S+)\n((?:\d+(?:, \d+)+\n)+)", text)
    used = {es: set(int(v) for ln in body.strip().splitlines() for v in ln.split(", ")[1:]) for es, body in blocks}
    deck = used[next(k for k in used if k.startswith("B1_s1"))]
    web_ = used[next(k for k in used if k.startswith("B2_w"))]
    shared = deck & web_
    assert len(shared) >= 200 / 10 and all(abs(nodes[n][1] - 50) < 1e-6 and abs(nodes[n][2]) < 1e-6 for n in shared)


def test_step_surface_component_shells(tmp_path, web):
    """A surface STEP file (two labelled faces, no solids) as an assembly component: one surface body per STEP
    component, named from the labels; the analysis makes one shell per surface body."""
    from build123d import Compound, Face, Pos, export_step
    from drawgen import assembly
    f1 = Face.make_rect(100, 50)
    f2 = Pos(0, 0, 30) * Face.make_rect(100, 50)
    f1.label, f2.label = "LOWER", "UPPER"
    comp = Compound(children=[f1, f2])
    comp.label = "PANELS"
    p = str(tmp_path / "panels.step")
    export_step(comp, p)
    src = assembly.Sources(str(tmp_path))
    s = {"type": "step", "path": p, "part": None}
    full, err = src.load(s)
    assert err is None and len(full.faces()) == 2
    assert [(i, n) for i, n, _c, _sh in src.surfaces(s)] == [("s1", "LOWER"), ("s2", "UPPER")]
    e = src.info(s)
    assert e["mesh"]["face_body"] == [0, 1] and e["vol"] == 0
    # read again from the BRep cache of the whole file
    assembly._SRC_CACHE.clear()
    src2 = assembly.Sources(str(tmp_path))
    solid, surfs = src2.parts(s)
    assert solid is None and [n for _i, n, _c, _s in surfs] == ["LOWER", "UPPER"]
    asm = {"components": [{"id": "7", "name": "panels", "source": s, "pos": [0, 0, 0], "rot": [0, 0, 0]}]}
    bodies = analysis.geometry({"bodies": {}, "shells": {"7:s2": {"t": 3}}}, asm, src2)
    assert [(b["id"], b["t"], b["name"]) for b in bodies] == [("7:s1", analysis.DEFAULT_SHELL_T, "panels / LOWER"), ("7:s2", 3.0, "panels / UPPER")]
