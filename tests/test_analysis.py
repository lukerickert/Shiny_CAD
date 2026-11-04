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
    job = {"size": size, "bonded": doc.get("bonded", True), "bodies": [], "mesh": dict(doc.get("mesh") or {}),
           "apart": sorted(set(x for p in analysis.contact_body_pairs(doc, bodies) for x in p))}
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
    frd, dat = analysis.read_frd(os.path.join(wd, "job.frd")), analysis.read_dat(os.path.join(wd, "job.dat"))
    if M.nonlinear():
        return M, analysis.Results(M, frd, dat, analysis.read_frd_incs(os.path.join(wd, "job.frd")),
                                   analysis.read_dat_incs(os.path.join(wd, "job.dat")))
    return M, analysis.Results(M, frd, dat)


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


def test_mesh_without_supports(client, web, tmp_path):
    """Mesh (mesh_only) without supports, with a support and a load not yet picked, and with a support on an edge of
    a shell that is off: the mesh is made, the incomplete items are left out (a warning for the support whose target
    is not found); the solve still needs a support."""
    c, e0, e1 = _cantilever(client, "sh_mesh")
    doc = _shell_doc("sh_mesh", {"1:s1": {"t": 2}},
                     [{"id": "s1", "name": "unpicked", "target": None, "type": "fixed"}],
                     [{"id": "l1", "name": "unpicked", "type": "force", "target": None, "value": [0, 0, -1]}],
                     source={"type": "part", "name": "sh_mesh"}, analysis_type="buckling")
    asm = web._fea_asm(doc)
    r = analysis.run(doc, asm, web._asm_sources(), str(tmp_path / "a"), None, mesh_only=True, meta={"name": "sh_mesh"})
    assert r["summary"]["nodes"] > 50 and r["payload"]["count"] > 50 and not r["summary"]["warnings"]
    assert os.path.isfile(r["files"]["inp"])
    # a support on an edge of a component that is not in the analysis: left out with a warning
    doc2 = dict(doc, supports=[{"id": "s2", "name": "stale", "target": {"comp": "9", "edge": 0}, "type": "fixed"}])
    r = analysis.run(doc2, asm, web._asm_sources(), str(tmp_path / "b"), None, mesh_only=True, meta={"name": "sh_mesh"})
    assert any("support stale left out" in w for w in r["summary"]["warnings"])
    with pytest.raises(analysis.AnalysisError, match="no supports"):
        analysis.run(dict(doc, analysis_type="static", supports=[], loads=[]), asm, web._asm_sources(), str(tmp_path / "c"), "ccx", meta={"name": "sh_mesh"})
    # the API: Mesh of the analysis without supports
    ok(client.put("/api/analysis/file/sh_mesh", json=doc))
    s = _wait(client, ok(client.post("/api/analysis/run", json={"name": "sh_mesh", "analysis": doc, "mesh_only": True}))["job"])
    assert s["state"] == "done" and s["result"]["mesh_only"], s


# --------------------------------------------------------------------------- sections, node sets, structured mesh

def _girder(client, name="gd", web_z=0.0):
    """Two decks (surface XY 200 x 100, side by side, x 0 to 400) and a web (surface XZ 400 x 40, turned 180 deg
    about X, hanging below the decks at y = 50, raised by web_z). Returns the assembly."""
    ok(client.put("/api/part/file/%s_deck" % name, json={"name": name + "_deck", "version": 2, "next": 2, "features": [_surf("s1", "Deck", "XY", 200, 100)]}))
    ok(client.put("/api/part/file/%s_web" % name, json={"name": name + "_web", "version": 2, "next": 2, "features": [_surf("w", "Web", "XZ", 400, 40)]}))
    asm = {"name": name, "next": 4, "components": [
        {"id": "1", "name": "deck", "source": {"type": "part", "name": name + "_deck"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "3", "name": "deck2", "source": {"type": "part", "name": name + "_deck"}, "pos": [200, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "web", "source": {"type": "part", "name": name + "_web"}, "pos": [0, 50, web_z], "rot": [180, 0, 0]}]}
    ok(client.put("/api/assembly/file/" + name, json=asm))
    return asm


def test_structured_grid_fuzzy_and_quality_report(client, web, tmp_path):
    """Girder shells, mesh size 10 mm, web size 5 mm. Section sizes Grid: every face is a structured quadrangle
    mesh (gamma 1.0, edges 5 mm to 10 mm). Section sizes Local: the deck faces next to the finer web are free. A
    web raised by 0.05 mm (through the decks): the fragment splits the web into two faces (an element edge of
    0.05 mm); with Fuzzy 0.1 mm the web joins the decks (five faces, no edge below 1 mm)."""
    asm = _girder(client, "gq")
    src = web._asm_sources()

    def mesh(asm, **m):
        doc = _shell_doc("gq", {"2:w": {"size": 5}}, [], [], mesh=dict({"size": 10}, **m))
        r = analysis.run(doc, asm, src, str(tmp_path / str(len(os.listdir(str(tmp_path))))), None, mesh_only=True, meta={"name": "gq"})
        return r["summary"]["shell"]
    g = mesh(asm, shell_size_mode="grid")
    assert g["structured"] == g["faces"] == 5 and g["free"] == 0
    assert g["min_quality"] == pytest.approx(1.0, abs=1e-6) and g["below_03"] == 0
    assert g["min_edge"] == pytest.approx(5.0, abs=1e-6) and g["max_edge"] == pytest.approx(10.0, abs=1e-6)
    assert [(b["id"], b["structured"], b["faces"]) for b in g["bodies"]] == [("1:s1", 2, 2), ("3:s1", 2, 2), ("2:w", 1, 1)]
    loc = mesh(asm)
    assert loc["free"] > 0 and loc["structured"] < loc["faces"]
    off = dict(asm, components=[dict(c, pos=[0, 50, 0.05]) if c["id"] == "2" else c for c in asm["components"]])
    s = mesh(off)
    assert s["faces"] == 6 and s["min_edge"] == pytest.approx(0.05, abs=1e-3)
    s = mesh(off, fuzzy=0.1)
    assert s["faces"] == 5 and s["min_edge"] > 1.0
    noq = mesh(asm, shell_structured=False)
    assert noq["structured"] == 0


def test_shell_groups_by_geometry(client, web):
    """By geometry: the two deck faces (one plane z = 0, touching) form PLATE_Z0, the web WEB_Y50; the largest area
    first; the API returns the same groups."""
    asm = _girder(client, "gg")
    g = analysis.shell_groups(asm, web._asm_sources())
    assert [(x["name"], sorted((f["comp"], f["face"]) for f in x["faces"]), round(x["area"])) for x in g] == [
        ("PLATE_Z0", [("1", 0), ("3", 0)], 40000), ("WEB_Y50", [("2", 0)], 16000)]
    j = ok(client.post("/api/analysis/shell_groups", json={"source": {"type": "assembly", "name": "gg"}, "angle": 1}))
    assert [x["name"] for x in j["groups"]] == ["PLATE_Z0", "WEB_Y50"]
    # a deck apart from the other: two groups on the same plane
    apart = dict(asm, components=[dict(c, pos=[300, 0, 0]) if c["id"] == "3" else c for c in asm["components"]])
    names = [x["name"] for x in analysis.shell_groups(apart, web._asm_sources())]
    assert sorted(names) == ["PLATE_Z0", "PLATE_Z0_2", "WEB_Y50"]


@needs_ccx
def test_sections_and_node_set_supports(client, web, tmp_path):
    """Sections PLATE_Z0 (t 8 mm) and WEB_Y50 (t 6 mm) from By geometry, Section sizes Grid, supports on node sets
    by plane (fixed at x = 0, pinned at x = 400), gravity: one shell per section, every face structured, the
    weight from the section thicknesses, the sum of the reactions equal to the weight."""
    asm = _girder(client, "gs")
    src = web._asm_sources()
    g = analysis.shell_groups(asm, src)
    secs = [dict(id=str(i + 1), name=x["name"], faces=x["faces"], t=8 if x["name"].startswith("PLATE") else 6) for i, x in enumerate(g)]
    nsets = [{"id": "n1", "name": "X0", "kind": "plane", "axis": "x", "value": 0, "tol": 0.01},
             {"id": "n2", "name": "X400", "kind": "plane", "axis": "x", "value": 400, "tol": 0.01}]
    doc = _shell_doc("gs", {}, [{"id": "s1", "name": "x0", "target": {"nset": "n1"}, "type": "fixed"},
                                {"id": "s2", "name": "x400", "target": {"nset": "n2"}, "type": "pinned"}],
                     [{"id": "g", "name": "g", "type": "gravity", "value": [0, 0, -9810]}],
                     sections=secs, nsets=nsets, mesh={"size": 10, "shell_size_mode": "grid"})
    bodies = analysis.geometry(doc, asm, src)
    assert [(b["id"], b["name"], b["t"]) for b in bodies] == [("sec:1", "PLATE_Z0", 8.0), ("sec:2", "WEB_Y50", 6.0)]
    r = analysis.run(doc, asm, src, str(tmp_path), CCX, meta={"name": "gs"})
    assert [(b["name"], b["elements"]) for b in r["summary"]["bodies"]] == [("PLATE_Z0", 400), ("WEB_Y50", 160)]
    assert r["summary"]["shell"]["free"] == 0
    t = r["tables"]["total"]
    W = 7850e-12 * 9810 * (400 * 100 * 8 + 400 * 40 * 6)
    assert -t["applied"][2] == pytest.approx(W, rel=1e-3)
    F = np.sum([x["F"] for x in t["reactions"]], axis=0)
    assert np.allclose(F + np.asarray(t["applied"]), 0, atol=1e-3 * W)
    # an unknown node set kind
    with pytest.raises(analysis.AnalysisError, match="unknown kind"):
        analysis.run(dict(doc, nsets=[dict(nsets[0], kind="bogus"), nsets[1]]), asm, src, str(tmp_path / "e"), CCX, meta={"name": "gs"})
    # batch mode (run.py --batch analysis gs): mesh only and solve
    from drawgen import batch
    doc = dict(doc, source={"type": "assembly", "name": "gs"})
    ok(client.put("/api/analysis/file/gs", json=doc))
    out = []
    assert batch.run("analysis", "gs", mesh_only=True, log=out.append) == 0, out
    assert out[0] == "analysis gs: %d nodes, %d elements" % (r["summary"]["nodes"], r["summary"]["elements"])
    assert "shells: 5 of 5 face(s) structured, 0 free" in out
    out = []
    assert batch.run("analysis", "gs", log=out.append) == 0, out
    assert any(x.startswith("frd: ") for x in out) or any(x.startswith("inp: ") for x in out), out
    assert batch.run("analysis", "no_such_doc", log=out.append) == 2


def test_load_values_and_node_set_without_body(client, web, tmp_path):
    """A pressure with three components, a force with one value and a node set of section edges without its section
    or shell: an error that names the load or node set (mesh only: the support or load is left out with a
    warning)."""
    c, e0, e1 = _cantilever(client, "sh_vals")
    sup = [{"id": "s1", "name": "root", "target": {"comp": "1", "edge": e0}, "type": "fixed"}]
    base = dict(source={"type": "part", "name": "sh_vals"})
    src = web._asm_sources()
    for loads, msg in (([{"id": "p", "name": "P1", "type": "pressure", "target": {"comp": "1", "face": 0}, "value": [0, 0, -1000]}], "load P1: a pressure is one value"),
                       ([{"id": "f", "name": "F1", "type": "force", "target": {"comp": "1", "face": 0}, "value": 5}], "load F1: the value of a force load is three components")):
        doc = _shell_doc("sh_vals", {"1:s1": {"t": 2}}, sup, loads, **base)
        asm = web._fea_asm(doc)
        with pytest.raises(analysis.AnalysisError, match=msg):
            analysis.run(doc, asm, src, str(tmp_path / "a"), "ccx", meta={"name": "sh_vals"})
        r = analysis.run(doc, asm, src, str(tmp_path / "m"), None, mesh_only=True, meta={"name": "sh_vals"})
        assert any(msg in w for w in r["summary"]["warnings"])
    doc = _shell_doc("sh_vals", {"1:s1": {"t": 2}}, [{"id": "s1", "name": "edges", "target": {"nset": "n1"}, "type": "fixed"}], [],
                     nsets=[{"id": "n1", "name": "FREE_1", "kind": "section_edges", "body": "", "which": "free"}], **base)
    with pytest.raises(analysis.AnalysisError, match="node set FREE_1: choose the section or shell"):
        analysis.run(doc, web._fea_asm(doc), src, str(tmp_path / "n"), "ccx", meta={"name": "sh_vals"})


def test_mesh_view_data_of_supports_and_loads(client, web, tmp_path):
    """View data of the mesh: the nodes and held components of each support (edge: translations and the rotations of
    the shell nodes; node set by plane), the nodal forces of each load (sum equal to the applied force), gravity as
    its value only. A solve that stops at a load error sends the mesh with the job poll."""
    import base64
    c, e0, e1 = _cantilever(client, "sh_view")
    doc = _shell_doc("sh_view", {"1:s1": {"t": 2}},
                     [{"id": "s1", "name": "root", "target": {"comp": "1", "edge": e0}, "type": "fixed"},
                      {"id": "s2", "name": "y0", "target": {"nset": "n1"}, "type": "dofs", "dofs": [0, 1, 0, 0, 0, 0]}],
                     [{"id": "l1", "name": "tip", "type": "line", "target": {"comp": "1", "edge": e1}, "value": [0, 0, -0.5]},
                      {"id": "l2", "name": "p", "type": "pressure", "target": {"comp": "1", "face": 0}, "value": 0.01},
                      {"id": "l3", "name": "g", "type": "gravity", "value": [0, 0, -9810]}],
                     source={"type": "part", "name": "sh_view"}, mesh={"size": 5, "shell_size_mode": "grid"},
                     nsets=[{"id": "n1", "name": "Y0", "kind": "plane", "axis": "y", "value": 0, "tol": 0.01}])
    r = analysis.run(doc, web._fea_asm(doc), web._asm_sources(), str(tmp_path / "m"), None, mesh_only=True, meta={"name": "sh_view"})
    p = r["payload"]
    pos = np.frombuffer(base64.b64decode(p["pos"]), np.float32).reshape(-1, 3)
    b = {x["id"]: x for x in p["bcs"]}
    assert b["s1"]["dofs"] == [1, 2, 3] and b["s1"]["rdofs"] == [1, 2, 3] and len(b["s1"]["nodes"]) == 20 / 5 + 1
    assert np.allclose(pos[b["s1"]["nodes"]][:, 0], 0) and sorted(b["s1"]["rnodes"]) == sorted(b["s1"]["nodes"])
    assert b["s2"]["dofs"] == [2] and b["s2"]["rdofs"] == [] and len(b["s2"]["nodes"]) == 100 / 5 + 1
    assert np.allclose(pos[b["s2"]["nodes"]][:, 1], 0)
    ld = {x["id"]: x for x in p["loads"]}
    tip = np.asarray(ld["l1"]["f"])
    assert np.allclose(pos[tip[:, 0].astype(int)][:, 0], 100) and np.allclose(tip[:, 1:].sum(axis=0), [0, 0, -10.0])
    assert np.allclose(np.asarray(ld["l2"]["f"])[:, 1:].sum(axis=0), [0, 0, -0.01 * 100 * 20])
    assert ld["l3"]["f"] == [] and ld["l3"]["value"] == [0, 0, -9810]
    # a solve stopped by a load error: the mesh comes with the job poll
    bad = dict(doc, loads=doc["loads"] + [{"id": "l4", "name": "bad", "type": "pressure", "target": {"comp": "1", "face": 0}, "value": [0, 0, -1]}])
    jid = ok(client.post("/api/analysis/run", json={"name": "sh_view", "analysis": bad}))["job"]
    t0, mesh = time.time(), None
    while time.time() - t0 < 300:
        s = ok(client.get("/api/analysis/job/" + jid))
        mesh = mesh or s.get("mesh")
        if s["state"] != "running":
            break
        time.sleep(0.3)
    assert s["state"] == "error" and "load bad: a pressure is one value" in s["error"]
    assert mesh and mesh["payload"]["count"] == p["count"] and any("load bad left out" in w for w in mesh["summary"]["warnings"])


# --------------------------------------------------------------------------- reference points and constraints

@needs_ccx
@pytest.mark.parametrize("coupling", ["rigid", "kinematic", "distributing"])
def test_reference_point_couplings_on_an_edge(client, web, tmp_path, coupling):
    """Shell cantilever 100 x 20 mm, t 2 mm, clamped at x = 0; a reference point at the centre of the free edge
    coupled to the edge (rigid, kinematic ux uy uz, distributing ux uy uz), force 10 N downwards on the point: tip
    deflection within 10 % of F L^3 / (3 E I) (1 - nu^2); reaction equal to the load."""
    c, e0, e1 = _cantilever(client, "rp_c_" + coupling)
    p = {"id": "p1", "name": "TIP", "xyz": [100, 10, 0], "coupling": coupling, "edges": [{"comp": "1", "edge": e1}]}
    if coupling != "rigid":
        p["dofs"] = [1, 1, 1, 0, 0, 0]
    doc = _shell_doc("rp_c", {"1:s1": {"t": 2}},
                     [{"id": "s1", "name": "root", "target": {"comp": "1", "edge": e0}, "type": "fixed"}],
                     [{"id": "l1", "name": "F", "type": "force", "target": {"point": "p1"}, "value": [0, 0, -10]}],
                     source={"type": "part", "name": "rp_c_" + coupling}, mesh={"size": 5}, points=[p])
    r = analysis.run(doc, web._fea_asm(doc), web._asm_sources(), str(tmp_path), CCX, meta={"name": "rp_c"})
    w = 10.0 * 100 ** 3 / (3 * 210000.0 * 20 * 2 ** 3 / 12) * (1 - 0.3 ** 2)
    t = r["tables"]["total"]
    assert t["points"][0]["u"][2] == pytest.approx(-w, rel=0.1)
    assert np.allclose(t["reactions"][0]["F"], [0, 0, 10.0], atol=1e-3)
    assert r["payload"]["rps"][0]["id"] == "p1" and len(r["payload"]["rps"][0]["nodes"]) == 5


@needs_ccx
def test_springs_joints_and_equations(client, web, tmp_path):
    """Shell cantilever (tip deflection w under 10 N at the tip reference point P1, rigid on the free edge):
    a spring kz = 10 / w from P1 to the fixed point P2 halves the deflection; the 10 N act on P3, tied to P1 by the
    equation uz(P3) - uz(P1) = 0. A hinge (axis y) joins P5 to P1; a spring to ground on ry of P5 (1e5 N mm/rad)
    takes the moment 1000 N mm about y on P5 (ry 0.01 rad), the other components of P5 follow P1."""
    c, e0, e1 = _cantilever(client, "rp_sj")
    w = 10.0 * 100 ** 3 / (3 * 210000.0 * 20 * 2 ** 3 / 12) * (1 - 0.3 ** 2)
    pts = [{"id": "p1", "name": "P1", "xyz": [100, 10, 0], "coupling": "rigid", "edges": [{"comp": "1", "edge": e1}]},
           {"id": "p2", "name": "P2", "xyz": [100, 10, -50], "coupling": "none"},
           {"id": "p3", "name": "P3", "xyz": [120, 10, 0], "coupling": "none"},
           {"id": "p5", "name": "P5", "xyz": [100, 10, 0], "coupling": "none"}]
    doc = _shell_doc("rp_sj", {"1:s1": {"t": 2}},
                     [{"id": "s1", "name": "root", "target": {"comp": "1", "edge": e0}, "type": "fixed"},
                      {"id": "s2", "name": "P2", "target": {"point": "p2"}, "type": "fixed"},
                      {"id": "s3", "name": "P3", "target": {"point": "p3"}, "type": "dofs", "dofs": [1, 1, 0, 0, 0, 0]}],
                     [{"id": "l1", "name": "F", "type": "force", "target": {"point": "p3"}, "value": [0, 0, -10]},
                      {"id": "l2", "name": "M", "type": "moment", "target": {"point": "p5"}, "value": [0, 1000, 0]}],
                     source={"type": "part", "name": "rp_sj"}, mesh={"size": 5}, points=pts,
                     springs=[{"id": "k1", "name": "K1", "a": {"point": "p1"}, "b": {"point": "p2"}, "k": [0, 0, 10 / w, 0, 0, 0]},
                              {"id": "k2", "name": "K2", "a": {"point": "p5"}, "b": None, "k": [0, 0, 0, 0, 1e5, 0]}],
                     joints=[{"id": "j1", "name": "H", "type": "hinge", "a": {"point": "p5"}, "b": {"point": "p1"}, "axis": [0, 1, 0]}],
                     equations=[{"id": "q1", "name": "E1", "terms": [{"end": {"point": "p3"}, "dof": 3, "coef": 1},
                                                                    {"end": {"point": "p1"}, "dof": 3, "coef": -1}]}])
    r = analysis.run(doc, web._fea_asm(doc), web._asm_sources(), str(tmp_path), CCX, meta={"name": "rp_sj"})
    P = {x["name"]: x for x in r["tables"]["total"]["points"]}
    assert P["P1"]["u"][2] == pytest.approx(-w / 2, rel=0.1) and P["P3"]["u"][2] == pytest.approx(P["P1"]["u"][2], rel=1e-6)
    assert P["P5"]["rot"][1] == pytest.approx(0.01, rel=1e-3)
    assert P["P5"]["u"] == pytest.approx(P["P1"]["u"], abs=1e-9) and P["P5"]["rot"][0] == pytest.approx(P["P1"]["rot"][0], abs=1e-9)
    text = open(r["files"]["inp"]).read()
    assert "*ELEMENT, TYPE=SPRING2, ELSET=SPR1_3" in text and "*ELEMENT, TYPE=SPRING1, ELSET=SPR2_5" in text
    assert [x["kind"] for x in r["payload"]["links"]] == ["spring", "spring", "joint"]
    # a reference point connected to nothing
    lone = dict(doc, points=pts + [{"id": "p9", "name": "P9", "xyz": [0, 0, 50], "coupling": "none"}])
    with pytest.raises(analysis.AnalysisError, match="reference point P9 is not connected"):
        analysis.run(lone, web._fea_asm(doc), web._asm_sources(), str(tmp_path / "b"), CCX, meta={"name": "rp_sj"})
    # the hinge needs rotations at both ends
    bad = dict(doc, joints=[{"id": "j1", "name": "H", "type": "hinge", "a": {"at": [100, 0, 0]}, "b": {"point": "p1"}, "axis": [0, 1, 0]}])
    with pytest.raises(analysis.AnalysisError, match="joint H: rx needs rotations at end A"):
        analysis.run(bad, web._fea_asm(doc), web._asm_sources(), str(tmp_path / "c"), CCX, meta={"name": "rp_sj"})


def test_node_sets_of_bodies_and_solid_faces(client, web, tmp_path):
    """Node sets of a body (all its nodes) and of a solid face (nodes of the face) as support targets: the supports
    hold those nodes; a node set of a body that is not meshed is refused."""
    ok(client.put("/api/part/file/ns_blk", json=plate("ns_blk", 40, 20, 10, 0)))
    asm = {"components": [{"id": "1", "name": "blk", "source": {"type": "part", "name": "ns_blk"}, "pos": [0, 0, 0], "rot": [0, 0, 0]}]}
    c = ok(client.post("/api/assembly/build", json={"assembly": asm}))["components"][0]
    bot = next(i for i, r in enumerate(c["refs"]) if r["kind"] == "plane" and abs(r["c"][2]) < 1e-6)
    doc = {"name": "nsb", "materials": STEEL, "default_material": "Steel", "mesh": {"size": 5}, "bonded": True, "bodies": {},
           "members": [], "plates": [], "fasteners": [], "loads": [],
           "nsets": [{"id": "n1", "name": "ALL", "kind": "body", "bodies": ["1"]},
                     {"id": "n2", "name": "BOT", "kind": "faces", "faces": [{"comp": "1", "face": bot}]}],
           "supports": [{"id": "s1", "name": "all", "target": {"nset": "n1"}, "type": "pinned"},
                        {"id": "s2", "name": "bot", "target": {"nset": "n2"}, "type": "pinned"}]}
    src = web._asm_sources()
    r = analysis.run(doc, asm, src, str(tmp_path / "a"), None, mesh_only=True, meta={"name": "nsb"})
    import base64
    pos = np.frombuffer(base64.b64decode(r["payload"]["pos"]), np.float32).reshape(-1, 3)
    b = {x["id"]: x for x in r["payload"]["bcs"]}
    assert len(b["s1"]["nodes"]) > len(b["s2"]["nodes"]) > 0 and np.allclose(pos[b["s2"]["nodes"]][:, 2], 0)
    bad = dict(doc, nsets=[{"id": "n1", "name": "ALL", "kind": "body", "bodies": ["9"]}], supports=[doc["supports"][0]])
    r = analysis.run(bad, asm, src, str(tmp_path / "b"), None, mesh_only=True, meta={"name": "nsb"})
    assert any("node set ALL: body 9 is not meshed" in w for w in r["summary"]["warnings"])


@needs_ccx
def test_multi_item_supports_and_loads(tmp_path):
    """Supports and loads on several items (selection targets {"faces", "edges", "bodies"}): a fixed support on two
    faces holds the nodes of both; a force on two faces is distributed over both by area (total as given); a pressure
    on two faces acts on each; a normal support on several faces and a load on bodies are refused; one face in a list
    is the plain face reference."""
    from build123d import Box, Pos
    blk = Pos(50, 10, 5) * Box(100, 20, 10)
    B = bodies_of({"b": blk})
    fi = lambda ax, v: face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][ax] - v) < 1e-6 and abs(r["n"][ax]) > 0.99)
    root, bot, tip, top = fi(0, 0), fi(2, 0), fi(0, 100), fi(2, 10)
    F = lambda i: {"comp": "b", "face": i}
    assert analysis.single_target({"faces": [F(root)]}) == F(root) and analysis.is_multi({"edges": []})
    doc = {"materials": STEEL, "default_material": "Steel", "mesh": {"size": 5.0},
           "supports": [{"id": "s1", "name": "root", "target": {"faces": [F(root), F(bot)]}, "type": "fixed"}],
           "loads": [{"id": "l1", "name": "tipz", "type": "force", "target": {"faces": [F(tip), F(top)]}, "value": [0, 0, -100]},
                     {"id": "l2", "name": "p", "type": "pressure", "target": {"faces": [F(tip), F(top)]}, "value": 0.1}]}
    M, R = solve(doc, B, str(tmp_path / "a"), size=5.0)
    held = set(M.supports[0]["nodes"])
    assert held == set(M.face(F(root))["nodes"]) | set(M.face(F(bot))["nodes"])
    assert np.allclose(R.applied("total"), [-0.1 * 200, 0, -100 - 0.1 * 2000], atol=1e-6)
    assert np.allclose(reaction_sum(R) + R.applied("total"), 0, atol=1e-3)
    bad = dict(doc, supports=[dict(doc["supports"][0], type="normal")], loads=[])
    with pytest.raises(analysis.AnalysisError, match="normal support takes one planar face"):
        solve(bad, B, str(tmp_path / "b"), size=5.0)
    bad = dict(doc, loads=[{"id": "l3", "name": "lb", "type": "force", "target": {"bodies": ["b"]}, "value": [0, 0, 1]}])
    with pytest.raises(analysis.AnalysisError, match="not bodies"):
        solve(bad, B, str(tmp_path / "c"), size=5.0)


def test_node_set_of_a_surface_body_in_a_section(client, web, tmp_path):
    """Node set of a surface body whose face is in a section: the nodes of the face, meshed in the section."""
    c, e0, e1 = _cantilever(client, "sh_nsec")
    doc = _shell_doc("sh_nsec", {"1:s1": {"t": 10}}, [{"id": "s1", "name": "all", "target": {"nset": "n1"}, "type": "pinned"}], [],
                     source={"type": "part", "name": "sh_nsec"}, mesh={"size": 5},
                     sections=[{"id": "1", "name": "SEC", "faces": [{"comp": "1", "face": 0}], "t": 2}],
                     nsets=[{"id": "n1", "name": "BODY_1", "kind": "body", "bodies": ["1:s1"]}])
    asm, src = web._fea_asm(doc), web._asm_sources()
    assert [(b["id"], b["t"]) for b in analysis.geometry(doc, asm, src)] == [("sec:1", 2.0)]
    r = analysis.run(doc, asm, src, str(tmp_path / "m"), None, mesh_only=True, meta={"name": "sh_nsec"})
    assert not r["summary"]["warnings"]
    b = r["payload"]["bcs"][0]
    assert len(b["nodes"]) == r["summary"]["nodes"]
    bad = dict(doc, nsets=[{"id": "n1", "name": "BODY_1", "kind": "body", "bodies": ["1:s9"]}])
    r = analysis.run(bad, asm, src, str(tmp_path / "b"), None, mesh_only=True, meta={"name": "sh_nsec"})
    assert any("node set BODY_1: body 1:s9 is not meshed (off)" in w for w in r["summary"]["warnings"])


def _stack(client, web, name):
    """Block 40 x 20 x 10 (component 1) with a block 20 x 20 x 10 (component 2) standing on it: faces bottom of 1,
    top of 1, bottom of 2, top of 2."""
    ok(client.put("/api/part/file/%s_lo" % name, json=plate("%s_lo" % name, 40, 20, 10, 0)))
    ok(client.put("/api/part/file/%s_hi" % name, json=plate("%s_hi" % name, 20, 20, 10, 0)))
    asm = {"components": [{"id": "1", "name": "lo", "source": {"type": "part", "name": "%s_lo" % name}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
                          {"id": "2", "name": "hi", "source": {"type": "part", "name": "%s_hi" % name}, "pos": [10, 0, 10], "rot": [0, 0, 0]}]}
    comps = ok(client.post("/api/assembly/build", json={"assembly": asm}))["components"]
    def zface(c, z):
        return next(i for i, r in enumerate(c["refs"]) if r["kind"] == "plane" and abs(r["n"][2]) > 0.99 and abs(r["c"][2] - z) < 1e-6)
    return asm, {"lo_bot": {"comp": "1", "face": zface(comps[0], 0)}, "lo_top": {"comp": "1", "face": zface(comps[0], 10)},
                 "hi_bot": {"comp": "2", "face": zface(comps[1], 0)}, "hi_top": {"comp": "2", "face": zface(comps[1], 10)}}


@pytest.mark.skipif(not CCX, reason="CalculiX not installed")
def test_contact_plastic_nonlinear(client, web, tmp_path):
    """Block pressed onto a block (surface-to-surface penalty contact with friction, the bodies meshed apart although
    Bonded is on), plastic material with isotropic hardening: nonlinear step with increments, PEEQ, the reactions of
    the two supports equal and opposite, a history row per increment; the input file cards."""
    asm, F = _stack(client, web, "ct")
    mats = {"Soft": {"E": 210000.0, "nu": 0.3, "rho": 7850.0, "law": "plastic", "plastic": [[100.0, 0.0], [200.0, 0.1]]}}
    doc = {"name": "ct", "materials": mats, "default_material": "Soft", "mesh": {"size": 4}, "bonded": True, "bodies": {},
           "members": [], "plates": [], "fasteners": [], "loads": [],
           "supports": [{"id": "s1", "name": "base", "target": F["lo_bot"], "type": "fixed"},
                        {"id": "s2", "name": "press", "target": F["hi_top"], "type": "displacement", "dofs": [1, 1, 1, 0, 0, 0], "value": [0, 0, -0.05, 0, 0, 0]}],
           "contacts": [{"id": "c1", "name": "seat", "type": "surface", "master": [F["lo_top"]], "slave": [F["hi_bot"]], "friction": 0.2}],
           "nonlinear": {"inc0": 0.25, "incmax": 0.25}}
    src = web._asm_sources()
    r = analysis.run(doc, asm, src, str(tmp_path / "a"), CCX, meta={"name": "ct"})
    inp = open(r["files"]["inp"]).read()
    assert "*CONTACT PAIR, INTERACTION=C1I, TYPE=SURFACE TO SURFACE" in inp and "*FRICTION" in inp
    assert "*PLASTIC, HARDENING=ISOTROPIC" in inp and "*STEP, INC=100" in inp and "S, PEEQ" in inp
    assert "*TIE" not in inp
    assert r["summary"]["nonlinear"] and r["summary"]["contacts"][0]["name"] == "seat"
    h = r["history"]["rows"]
    assert len(h) >= 4 and abs(h[-1]["time"] - 1.0) < 1e-9 and h[0]["time"] < h[-1]["time"]
    assert [x["state"] for x in r["increments"]] == ["i%d" % (k + 1) for k in range(len(h))]
    t = r["tables"]["total"]
    Fb, Fp = (np.asarray(x["F"]) for x in t["reactions"])
    assert Fp[2] < -100.0 and abs(Fb[2] + Fp[2]) < 1e-3 * abs(Fp[2])
    assert max(b["pemax"] or 0 for b in t["bodies"]) > 0
    assert h[-1]["reactions"][1][2] == pytest.approx(Fp[2], rel=1e-6) and abs(h[0]["reactions"][1][2]) < abs(h[-1]["reactions"][1][2])
    assert "pe" in r["payload"]["states"]["total"] and "pe" in r["payload"]["states"]["i1"]


def test_nonlinear_refuses_beams_and_fasteners(tmp_path):
    """A nonlinear solve (here: contact) with a fastener: refused (U1 elements are linear only); mesh only: a warning."""
    from build123d import Box, Cylinder, Pos
    a = Pos(0, 0, 5) * Box(50, 50, 10) - Pos(0, 0, 5) * Cylinder(5, 10)
    b = Pos(0, 0, 15) * Box(50, 50, 10) - Pos(0, 0, 15) * Cylinder(5, 10)
    B = bodies_of({"a": a, "b": b})
    fa = face_index(B[0], lambda r: r["kind"] == "cylinder")
    fb = face_index(B[1], lambda r: r["kind"] == "cylinder")
    bot = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][2]) < 1e-6)
    atop = face_index(B[0], lambda r: r["kind"] == "plane" and abs(r["c"][2] - 10) < 1e-6)
    bbot = face_index(B[1], lambda r: r["kind"] == "plane" and abs(r["c"][2] - 10) < 1e-6)
    doc = {"materials": STEEL, "default_material": "Steel", "bonded": True,
           "fasteners": [{"id": "f1", "name": "M8", "faces": [{"comp": "a", "face": fa}, {"comp": "b", "face": fb}], "d": 8, "preload": 10000}],
           "supports": [{"id": "s1", "name": "base", "target": {"comp": "a", "face": bot}, "type": "fixed"}],
           "contacts": [{"id": "c1", "name": "joint", "type": "surface", "master": [{"comp": "a", "face": atop}],
                         "slave": [{"comp": "b", "face": bbot}], "friction": 0.3}], "loads": []}
    from drawgen import femesh
    from build123d import export_brep
    job = {"size": 8.0, "bonded": True, "bodies": [], "apart": ["a", "b"], "mesh": {}}
    for x in B:
        p = os.path.join(str(tmp_path), x["id"] + ".brep")
        export_brep(x["shape"], p)
        job["bodies"].append({"id": x["id"], "brep": p, "mode": "solid", "size": None, "layers": 1})
    mesh = femesh.run(job)
    with pytest.raises(analysis.AnalysisError, match="U1 elements, linear only"):
        analysis.Model(doc, B, mesh).build()
    M = analysis.Model(doc, B, mesh)
    M.build(mesh_only=True)
    assert any("U1 elements" in w for w in M.warnings) and M.contact_defs


@pytest.mark.skipif(not CCX, reason="CalculiX not installed")
def test_contact_types_and_material_laws(client, web, tmp_path):
    """Node-to-surface with a node set as slave, tied faces (linear), kinematic hardening, a library material,
    Neo-Hooke and Mooney-Rivlin (large deformation): solved, equal and opposite reactions; contact search route;
    the library route; a plastic table not starting at 0 refused."""
    asm, F = _stack(client, web, "cv")
    src = web._asm_sources()
    base = {"name": "cv", "materials": {"S": {"E": 210000.0, "nu": 0.3, "rho": 7850.0}}, "default_material": "S", "mesh": {"size": 5},
            "bonded": True, "bodies": {}, "members": [], "plates": [], "fasteners": [], "loads": [],
            "supports": [{"id": "s1", "name": "base", "target": F["lo_bot"], "type": "fixed"},
                         {"id": "s2", "name": "press", "target": F["hi_top"], "type": "displacement", "dofs": [1, 1, 1, 0, 0, 0], "value": [0, 0, -0.02, 0, 0, 0]}],
            "contacts": [{"id": "c1", "name": "seat", "type": "surface", "master": [F["lo_top"]], "slave": [F["hi_bot"]]}]}

    def run(tag, **kw):
        import copy
        d = copy.deepcopy(base)
        d.update(kw)
        r = analysis.run(d, asm, src, str(tmp_path / tag), CCX, meta={"name": tag})
        Fz = [x["F"][2] for x in r["tables"]["total"]["reactions"]]
        assert Fz[0] > 0 and abs(Fz[0] + Fz[1]) < 1e-3 * Fz[0], (tag, Fz)
        return r, open(r["files"]["inp"]).read()
    r, inp = run("nset", nsets=[{"id": "n1", "name": "HIB", "kind": "faces", "faces": [F["hi_bot"]]}],
                 contacts=[dict(base["contacts"][0], type="node", slave=[], slave_nset="n1")])
    assert "TYPE=NODE TO SURFACE" in inp and "*SURFACE, NAME=C1S, TYPE=NODE" in inp
    r, inp = run("tied", contacts=[dict(base["contacts"][0], type="tied")])
    assert "*TIE, NAME=C1T" in inp and not r["summary"]["nonlinear"] and r["history"] is None
    r, inp = run("kin", materials={"S": {"E": 210000.0, "nu": 0.3, "rho": 7850, "law": "plastic", "hardening": "kinematic", "plastic": [[100, 0], [150, 0.1]]}})
    assert "*PLASTIC, HARDENING=KINEMATIC" in inp and max(b["pemax"] for b in r["tables"]["total"]["bodies"]) > 0
    r, inp = run("lib", materials={"S": {"E": 1, "nu": 0.3, "rho": 1, "law": "plastic", "library": "Steel S355 (DNVGL 19-Point Standard)"}})
    assert "210000, 0.3" in inp and "355, 0" in inp and "853.86, 1" in inp and "*DENSITY\n7.85e-09" in inp
    r, inp = run("neo", materials={"S": {"E": 10, "nu": 0.45, "rho": 1000, "law": "hyper", "hyper": "neohooke", "C10": 0.5, "D1": 0.1}})
    assert "*HYPERELASTIC, NEO HOOKE\n0.5, 0.1" in inp and "*STEP, NLGEOM, INC=100" in inp
    r, inp = run("mooney", materials={"S": {"E": 10, "nu": 0.45, "rho": 1000, "law": "hyper", "hyper": "mooney", "C10": 0.4, "C01": 0.1, "D1": 0.1}})
    assert "*HYPERELASTIC, MOONEY-RIVLIN\n0.4, 0.1, 0.1" in inp
    with pytest.raises(analysis.AnalysisError, match="plastic strain 0"):
        run("bad", materials={"S": {"E": 210000.0, "nu": 0.3, "law": "plastic", "plastic": [[100, 0.01]]}})
    doc = dict(base, source={"type": "assembly", "name": "cv_asm"})
    ok(client.put("/api/assembly/file/cv_asm", json=dict(asm, name="cv_asm", next=3)))
    j = ok(client.post("/api/analysis/contact_search", json={"analysis": doc, "gap": 0.2}))
    assert len(j["pairs"]) == 1 and j["pairs"][0]["master"] == [F["lo_top"]] and j["pairs"][0]["slave"] == [F["hi_bot"]]
    assert j["pairs"][0]["names"] == ["lo", "hi"]
    lib = ok(client.get("/api/analysis/material_library"))
    s355 = next(x for x in lib if x["name"] == "Steel S355 (DNVGL 19-Point Standard)")
    assert s355["E"] == 210000 and s355["rho"] == pytest.approx(7850) and s355["plastic"][0] == [355.0, 0.0]
    jc = next(x for x in lib if x["name"].startswith("Aluminium 6061"))
    assert jc["plastic"][0][0] == pytest.approx(324.1) and jc["plastic"][-1][0] == pytest.approx(324.1 + 113.8)


def test_shell_frontal_quad_failed_face_remeshed(tmp_path):
    """Shell tube (cylinder faces): a face that Frontal-Delaunay for quadrangles leaves as the boundary triangulation
    is meshed again with Delaunay, recombined (elements no longer than about the element size, a warning)."""
    from build123d import Compound, Cylinder, export_brep
    from drawgen import femesh
    p = os.path.join(str(tmp_path), "tube.brep")
    export_brep(Compound(Cylinder(60, 60).faces()), p)
    for algo in ("frontal", "delaunay"):
        job = {"size": 5.0, "bonded": False, "mesh": {"shell_algorithm": algo, "shell_structured": False, "shell_type": "S4"},
               "bodies": [{"id": "tube", "brep": p, "mode": "shell", "t": 2.0}]}
        mesh = femesh.run(job)
        xyz = np.array(mesh["nodes"]["xyz"]).reshape(-1, 3)
        row = {n: i for i, n in enumerate(mesh["nodes"]["ids"])}
        longest = 0.0
        for b in mesh["bodies"]["tube"]["blocks"]:
            for e in b["elements"]:
                q = [row[n] for n in e[1:]]
                longest = max(longest, max(np.linalg.norm(xyz[q[i]] - xyz[q[i - 1]]) for i in range(len(q))))
        assert longest < 12.0
        assert any("meshed with Delaunay" in w for w in mesh["warnings"]) == (algo == "frontal")


@needs_ccx
def test_shell_layers_s8r_composite(client, web, tmp_path):
    """S8R cantilever (100 x 20 mm, t 2 mm) with 4 layers: *SHELL SECTION, COMPOSITE with 4 layers of 0.5 mm, tip
    deflection and root stress within 10 % of the plate solution as with one layer; S4 with layers: one layer and a
    warning; layers 0 refused."""
    c, e0, e1 = _cantilever(client, "sh_lay")
    sup = [{"id": "s1", "name": "root", "target": {"comp": "1", "edge": e0}, "type": "fixed"}]
    load = [{"id": "l1", "name": "tip", "type": "line", "target": {"comp": "1", "edge": e1}, "value": [0, 0, -0.5]}]
    doc = _shell_doc("sh_lay", {"1:s1": {"t": 2, "layers": 4}}, sup, load, source={"type": "part", "name": "sh_lay"},
                     mesh={"size": 5, "shell_type": "S8R"})
    asm = web._fea_asm(doc)
    r = analysis.run(doc, asm, web._asm_sources(), str(tmp_path / "a"), CCX, meta={"name": "sh_lay"})
    text = open(r["files"]["inp"]).read()
    assert "*SHELL SECTION, ELSET=B1_s1_1, COMPOSITE, OFFSET=0\n0.5, , M1_Steel\n0.5, , M1_Steel\n0.5, , M1_Steel\n0.5, , M1_Steel\n" in text
    t = r["tables"]["total"]
    w = 10.0 * 100 ** 3 / (3 * 210000.0 * 20 * 2 ** 3 / 12) * (1 - 0.3 ** 2)
    assert t["bodies"][0]["umax"] == pytest.approx(w, rel=0.1)
    assert t["bodies"][0]["smax"] == pytest.approx(6 * 10.0 * 100 / (20 * 2 ** 2), rel=0.1)
    doc4 = dict(doc, mesh={"size": 5, "shell_type": "S4"})
    r = analysis.run(doc4, asm, web._asm_sources(), str(tmp_path / "b"), CCX, meta={"name": "sh_lay"})
    assert "COMPOSITE" not in open(r["files"]["inp"]).read()
    assert any("4 layers need S8R" in w for w in r["summary"]["warnings"])
    sec = dict(doc, shells={}, sections=[{"id": "q", "name": "SEC", "faces": [{"comp": "1", "face": 0}], "t": 2, "layers": 2}])
    r = analysis.run(sec, asm, web._asm_sources(), str(tmp_path / "d"), CCX, meta={"name": "sh_lay"})
    assert "COMPOSITE, OFFSET=0\n1, , M1_Steel\n1, , M1_Steel\n*" in open(r["files"]["inp"]).read()
    assert r["tables"]["total"]["bodies"][0]["umax"] == pytest.approx(w, rel=0.1)
    bad = dict(doc, shells={"1:s1": {"t": 2, "layers": 0}})
    with pytest.raises(analysis.AnalysisError, match="layers must be 1 to 20"):
        analysis.run(bad, asm, web._asm_sources(), str(tmp_path / "c"), CCX, meta={"name": "sh_lay"})
