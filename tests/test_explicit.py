# -*- coding: utf-8 -*-
"""Explicit tab (drawgen/explicit): mesh view data and readers, the model .inp of the ShinyCAD geometry,
the deck build (inp2rad and the cards of the settings), run folders, the local solve with a stand-in for the
OpenCourant executables (fake_opencourant.py), results, post-processing, the Explicit document in the project."""
import base64
import glob
import json
import os
import time

import numpy as np
import pytest

from conftest import part_rec, rect

import anim_writer
import fake_opencourant
from drawgen.explicit import anim
from drawgen.explicit import constants as C
from drawgen.explicit import host, meshview, results

SHELL_SETTINGS = {"mat_slots": [["Steel S355 (DNVGL 19-Point Standard)", "S355"]],
                  "rigid_vel_mode": C.RBV_EXPL, "rigid_vel": "0 0 -8000", "fail_model": C.FAIL_TENS, "ts_et1": "0.12",
                  "ts_soften": "0.08", "tie_mode": C.TIE_AUTO, "tstop": "0.01", "anim_frames": "4"}


def ok(r):
    assert r.status_code == 200, r.get_data(as_text=True)[:800]
    return r.get_json()


def b64(s, t):
    return np.frombuffer(base64.b64decode(s), t)


def shell_inp(path):
    """Deck plate (S4R) with a stiffener tied to it (*TIE, every second element reversed), a rigid impactor
    (*RIGID BODY on a node set) and clamped edges."""
    L = ["** shell test model", "*Heading", "shell test", "*Node"]
    nid = [0]

    def node(x, y, z):
        nid[0] += 1
        L.append("%d, %g, %g, %g" % (nid[0], x, y, z))
        return nid[0]
    n, h = 10, 20.0
    grid = [[node(i * h, j * h, 0.0) for i in range(n + 1)] for j in range(n + 1)]
    st = [[node(i * h, 100.0, -0.5 - k * 20.0) for i in range(n + 1)] for k in range(4)]
    imp = [[node(80 + i * 10.0, 80 + j * 10.0, 50.0) for i in range(5)] for j in range(5)]
    rp = node(100.0, 100.0, 50.0)
    eid = 0
    L.append("*Element, Type=S4R, Elset=DECK")
    for j in range(n):
        for i in range(n):
            eid += 1
            L.append("%d, %d, %d, %d, %d" % (eid, grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
    deck = list(range(1, eid + 1))
    L.append("*Element, Type=S4R, Elset=STIFF")
    s0 = eid + 1
    for k in range(3):
        for i in range(n):
            eid += 1
            a, b, c, d = st[k][i], st[k][i + 1], st[k + 1][i + 1], st[k + 1][i]
            L.append("%d, %d, %d, %d, %d" % ((eid, a, b, c, d) if i % 2 == 0 else (eid, a, d, c, b)))
    stiff = list(range(s0, eid + 1))
    L.append("*Element, Type=S4R, Elset=IMPACTOR")
    for j in range(4):
        for i in range(4):
            eid += 1
            L.append("%d, %d, %d, %d, %d" % (eid, imp[j][i], imp[j][i + 1], imp[j + 1][i + 1], imp[j + 1][i]))

    def ids(xs):
        return [", ".join(str(v) for v in xs[k:k + 16]) for k in range(0, len(xs), 16)]
    L += ["*Nset, Nset=EDGE"] + ids([grid[j][0] for j in range(n + 1)] + [grid[j][n] for j in range(n + 1)])
    L += ["*Nset, Nset=IMPN"] + ids(sorted({v for row in imp for v in row}))
    L += ["*Elset, Elset=TIE_S"] + ids(stiff[:n]) + ["*Elset, Elset=TIE_M"] + ids(deck)
    L += ["*Surface, Name=TIE_SLAVE, Type=Element", "TIE_S, SPOS", "*Surface, Name=TIE_MASTER, Type=Element", "TIE_M, SNEG"]
    L += ["*Material, Name=S355", "*Density", "7.85E-09", "*Elastic", "210000, 0.3", "*Plastic", "355, 0", "500, 0.2",
          "*Material, Name=MAT2", "*Density", "7.85E-09", "*Elastic", "210000, 0.3",
          "*Shell section, Elset=DECK, Material=S355", "10", "*Shell section, Elset=STIFF, Material=S355", "8",
          "*Shell section, Elset=IMPACTOR, Material=MAT2", "5", "*Rigid body, Ref node=%d, Nset=IMPN" % rp,
          "*Tie, Name=Tie-1, Position tolerance=1.0", "TIE_SLAVE, TIE_MASTER", "*Boundary", "EDGE, 1, 6, 0",
          "*Step", "*Dynamic, Explicit", ", 0.01", "*End step"]
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    return rp


def cards(path):
    with open(path) as f:
        return f.read().splitlines()


def block_after(lines, head, n=4):
    i = next(k for k, l in enumerate(lines) if l.startswith(head))
    return [l for l in lines[i + 1:i + 1 + 3 * n] if l.strip() and not l.startswith("#")][:n]


def wait_status(c, cond, timeout=int(os.environ.get("XP_WAIT", "120"))):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = ok(c.get("/api/explicit/status?since=0"))
        if cond(s):
            return s
        time.sleep(0.2)
    raise AssertionError("timeout: %s" % [l for _q, l in s["log"]][-20:])


def wait_job(c, jid, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = ok(c.get("/api/explicit/job/" + jid))
        if j["state"] != "running":
            return j
        time.sleep(0.2)
    raise AssertionError("job timeout")


# --------------------------------------------------------------------------- mesh view data and readers

def test_boundary_of_two_hexahedra_and_shells():
    xyz = [(x, y, z) for z in (0, 1) for y in (0, 1) for x in (0, 1, 2)]
    hexes = np.array([[0, 1, 4, 3, 6, 7, 10, 9], [1, 2, 5, 4, 7, 8, 11, 10]])
    pl = meshview.payload(xyz, [("hex", hexes, None), ("quad", np.array([[0, 1, 7, 6]]), None)])
    tc, tk = b64(pl["tri_cell"], np.uint32), b64(pl["tri_kind"], np.uint8)
    assert pl["ntri"] == 2 * (10 + 1)                 # 10 exterior faces of the two cells, one shell
    assert np.bincount(tc).tolist() == [10, 10, 2]
    assert sorted(set(tk.tolist())) == [1, 2]
    assert pl["bbox"] == [0, 0, 0, 2, 1, 1]


def test_read_inp_and_vtk_ascii_binary(tmp_path):
    p = tmp_path / "m.inp"
    shell_inp(str(p))
    m = meshview.read_inp(str(p))
    assert [x[0] for x in m["parts"]] == ["DECK", "STIFF", "IMPACTOR"]
    assert sum(len(c[1]) for c in m["cells"]) == 100 + 30 + 16
    # legacy VTK written by the stand-in anim_to_vtk, and the same data as BINARY
    a = tmp_path / "jA003"
    anim_writer.write_anim(str(a), 0.005, [[0, 0, 0]])
    import subprocess
    import sys
    out = subprocess.run([sys.executable, fake_opencourant.__file__, "anim_to_vtk", str(a)], capture_output=True, text=True).stdout
    (tmp_path / "j_003.vtk").write_text(out)
    v = meshview.read_vtk(str(tmp_path / "j_003.vtk"))
    assert v["xyz"].shape == (50, 3) and v["time"] == pytest.approx(0.005)
    assert v["cell"]["3DELEM_Strain"].shape == (16, 9) and v["point"]["Displacement"].shape == (50, 3)
    e1 = meshview.eps1(v["cell"]["3DELEM_Strain"])
    assert e1[0] == pytest.approx(0.003) and e1[1] == pytest.approx(0.006)
    cells, order = meshview.vtk_cells(v)
    assert cells[0][0] == "hex" and len(order) == 16
    # binary copy
    lines = out.splitlines()
    bl = lines[:2] + ["BINARY"] + lines[3:4]
    buf = b"\n".join(x.encode() for x in bl) + b"\n"
    buf += b"POINTS 50 float\n" + v["xyz"].astype(">f4").tobytes() + b"\n"
    conn = np.hstack([np.full((16, 1), 8), cells[0][1]]).astype(">i4")
    buf += b"CELLS 16 144\n" + conn.tobytes() + b"\nCELL_TYPES 16\n" + np.full(16, 12, ">i4").tobytes() + b"\n"
    buf += b"CELL_DATA 16\nSCALARS EROSION_STATUS float 1\nLOOKUP_TABLE default\n" + np.ones(16, ">f4").tobytes() + b"\n"
    (tmp_path / "b.vtk").write_bytes(buf)
    vb = meshview.read_vtk(str(tmp_path / "b.vtk"))
    assert np.allclose(vb["xyz"], v["xyz"]) and vb["cell"]["EROSION_STATUS"].sum() == 16


# --------------------------------------------------------------------------- settings, executables

def test_workspace_settings_and_executables(tmp_path):
    w = host.Workspace()
    snap = w.snapshot()
    assert snap["tie_mode"] == C.TIE_AUTO and snap["mat1"] == "None (Use PrePoMax Data)" and snap["mat_slots"][0][1] == "MAT1"
    # older run.json snapshot with three slots
    w.apply({"mat1": "Steel S355 (DNVGL 19-Point Standard)", "mat1_name": "S355", "mat2": "None (Use PrePoMax Data)",
             "mat2_name": "MAT2", "gravity": "false", "tstop": 0.02, "unknown": 1})
    assert w.mat_slots[0] == ["Steel S355 (DNVGL 19-Point Standard)", "S355"] and w.gravity.get() is False and w.tstop.get() == "0.02"
    assert [(a.get(), b.get()) for a, b in w._mat_slots()][0] == ("Steel S355 (DNVGL 19-Point Standard)", "S355")
    suffix = "_win64" if os.name == "nt" else "_linux64_gf"
    assert w._or_exe("starter") == "starter" + suffix and w._or_env() is None
    d = fake_opencourant.install(str(tmp_path / "exec"))
    (tmp_path / "hm_cfg_files").mkdir()
    w.or_exec.set(d)
    assert os.path.isfile(w._or_exe("engine"))
    env = w._or_env()
    assert env["PATH"].startswith(d) and env["RAD_CFG_PATH"] == str(tmp_path / "hm_cfg_files") and env["KMP_STACKSIZE"]
    # remote helpers
    w.apply({"share_map": "Z:/ => /home/u/RUN; Y:/x => /data", "remote_exec": "/opt/or/exec", "remote_scratch": "/scratch"})
    assert w._map_to_linux("Z:\\a\\b") == "/home/u/RUN/a/b" and w._map_to_linux("C:/a") is None
    p = w._remote_pipeline("job_b01", 8)
    assert "/opt/or/exec/starter_linux64_gf -i job_b01_0000.rad" in p and "-nt 8" in p and "th_to_csv_linux64_gf job_b01T01" in p
    assert w._remote_workdir("C:/r/run 1", "j") == "/scratch/run_1"


# --------------------------------------------------------------------------- deck build

def test_build_shell_deck_cards(tmp_path):
    inp = tmp_path / "shell.inp"
    rp = shell_inp(str(inp))
    w = host.Workspace()
    w.apply(dict(SHELL_SETTINGS, inp_path=str(inp), out_dir=str(tmp_path)))
    w._build_thread()
    log = "\n".join(t for _s, t in w.logs)
    rad = tmp_path / "shell_b01" / "shell_b01_0000.rad"
    assert rad.is_file(), log[-3000:]
    L = cards(str(rad))
    heads = [l for l in L if l.startswith("/")]
    assert any(h.startswith("/MAT/PLAS_TAB/") for h in heads) and any(h.startswith("/FAIL/TENSSTRAIN") for h in heads)
    et = block_after(L, "/FAIL/TENSSTRAIN", 1)[0].split()
    assert float(et[0]) == pytest.approx(0.12) and float(et[1]) == pytest.approx(0.12 * 1.08) and et[5] == "23"
    assert "Auto-tie 'Tie-1'" in log and any(h.startswith("/INTER/TYPE2/") for h in heads)
    assert "Heal Normals: flipped" in log and "Istrain=1" in log
    t7 = block_after(L, "/INTER/TYPE7/9999999", 2)
    assert t7[1].split()[6] == "1"                      # Idel=1: the failure model erodes elements
    iv = block_after(L, "/INIVEL/TRA/9990005", 2)[1].split()
    assert [float(x) for x in iv[:3]] == [0.0, 0.0, -8000.0]
    gr = block_after(L, "/GRNOD/NODE/9990004", 2)[1].split()
    assert int(gr[0]) == rp                           # the /RBODY main node is the *RIGID BODY reference node
    eng = cards(str(tmp_path / "shell_b01" / "shell_b01_0001.rad"))
    assert eng[1] == "/RUN/shell_b01/1" and float(eng[2]) == 0.01 and "/DT/INTER/DEL" in eng and "/ANIM/BRICK/TENS/STRAIN" in eng
    assert (tmp_path / "shell_b01" / "shell_b01_settings.txt").read_text().count("TENSSTRAIN as WRITTEN") == 1
    # second build: b02
    w._build_thread()
    assert (tmp_path / "shell_b02" / "shell_b02_0000.rad").is_file()


def test_build_halts_on_geometry_file(tmp_path):
    w = host.Workspace()
    (tmp_path / "x.step").write_text("ISO-10303-21;")
    w.apply({"inp_path": str(tmp_path / "x.step")})
    w._build_thread()
    assert any("BUILD HALTED" in t for _s, t in w.logs)


# --------------------------------------------------------------------------- the ShinyCAD model, API workflow

def _block(name, w, h, t, x=0.0, y=0.0):
    return part_rec(name, [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                            "sketch": {"entities": rect(w, h, x, y)}, "depth": t}])


@pytest.fixture(scope="module")
def xp_doc(client):
    ok(client.put("/api/part/file/xp_target", json=_block("xp_target", 200, 200, 10, -100, -100)))
    ok(client.put("/api/part/file/xp_impactor", json=_block("xp_impactor", 40, 40, 40, -20, -20)))
    ok(client.put("/api/assembly/file/xp_drop", json={"name": "xp_drop", "next": 3, "components": [
        {"id": "1", "name": "target", "source": {"type": "part", "name": "xp_target"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "impactor", "source": {"type": "part", "name": "xp_impactor"}, "pos": [0, 0, 15], "rot": [0, 0, 0]}]}))
    from drawgen import web
    info = web._asm_sources().info({"type": "part", "name": "xp_target"})
    fx = [i for i, r in enumerate(info["refs"]) if r and r.get("kind") == "plane" and abs(abs(r["n"][0]) - 1) < 1e-6]
    return {"name": "xp_drop1", "source": {"kind": "shinycad", "type": "assembly", "name": "xp_drop"},
            "materials": {"S355": {"library": "Steel S355 (DNVGL 19-Point Standard)"}, "Rigid": {"library": "", "E": 210000, "nu": 0.3, "rho": 7850}},
            "default_material": "S355", "mesh": {"size": 20, "strategy": "tet", "tet_type": "C3D4"}, "bonded": True,
            "bodies": {"1": {"role": "deformable", "material": "S355"}, "2": {"role": "rigid", "material": "Rigid"}},
            "supports": [{"id": "s1", "name": "x edges", "target": {"comp": "1", "face": fx[0]}, "dofs": [1, 1, 1]},
                         {"id": "s2", "name": "x edge 2", "target": {"comp": "1", "face": fx[1]}, "dofs": [0, 0, 1]}],
            "settings": {"rigid_vel_mode": C.RBV_EXPL, "rigid_vel": "0 0 -5000", "tstop": "0.01", "anim_frames": "4",
                         "pv_images": False, "extract_strains": False, "fail_model": C.FAIL_TENS, "ts_et1": "0.2"},
            "next": 3}


def test_model_inp_of_the_shinycad_geometry(client, xp_doc):
    ok(client.put("/api/explicit/file/xp_drop1", json=xp_doc))
    assert "xp_drop1" in ok(client.get("/api/explicit/list"))
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xp_drop1", "doc": xp_doc}))["job"])
    assert j["state"] == "done", j
    s = j["result"]["summary"]
    assert [b["role"] for b in s["bodies"]] == ["deformable", "rigid"] and s["bodies"][1]["ref_node"] == s["nodes"]
    assert s["supports"] == 4                      # 3 + 1 held components
    pl = j["result"]["payload"]
    assert pl["ncell"] == s["elements"] and set(b64(pl["part"], np.int32).tolist()) == {0, 1}
    text = open(j["result"]["inp"]).read()
    for k in ("*ELEMENT, TYPE=C3D4, ELSET=B_TARGET", "*MATERIAL, NAME=S355", "** library material: Steel S355",
              "*SOLID SECTION, ELSET=B_IMPACTOR, MATERIAL=RIGID", "*RIGID BODY, NSET=RB_IMPACTOR, REF NODE=%d" % s["nodes"],
              "*BOUNDARY", "SUP_2_X_EDGE_2, 3, 3"):
        assert k in text, k
    assert "SUP_2_X_EDGE_2, 1, 1" not in text
    # the reference node is at the centre of the impactor block
    m = meshview.read_inp(j["result"]["inp"])
    assert np.allclose(m["xyz"][list(m["node_ids"]).index(s["nodes"])], [0, 0, 35], atol=1e-6)
    # the external .inp view of the same file
    j2 = wait_job(client, ok(client.post("/api/explicit/inp_view", json={"path": j["result"]["inp"]}))["job"])
    assert j2["state"] == "done" and j2["result"]["summary"]["elements"] == s["elements"]


def test_run_build_solve_results(client, xp_doc, tmp_path, monkeypatch):
    exe = fake_opencourant.install(str(tmp_path / "exec"))
    ok(client.put("/api/explicit/env", json={"or_exec": exe, "ssh_threads": "2", "run_target": host.LOCAL}))
    env = ok(client.get("/api/explicit/env"))
    assert all(v["found"] for v in env["executables"].values())
    base = {"name": "xp_drop1", "doc": xp_doc, "settings": dict(xp_doc["settings"])}
    wait_job(client, ok(client.post("/api/explicit/model", json=base))["job"])
    r = ok(client.post("/api/explicit/run/new", json=dict(base, description="Drop 1, 5 m/s", notes="test")))
    run = r["run"]
    assert os.path.basename(run).endswith("_r001_drop-1-5-m-s") and os.path.isfile(os.path.join(run, "model", "xp_drop1.inp"))
    base["settings"]["out_dir"] = run
    ok(client.post("/api/explicit/build", json=base))
    s = wait_status(client, lambda s: not s["building"] and s["last_build"] and s["last_build"]["dir"].startswith(run))
    rad = s["last_build"]["rad"]
    assert rad.endswith("xp_drop1_b01/xp_drop1_b01_0000.rad")
    runs = ok(client.post("/api/explicit/runs", json=base))["runs"]
    assert runs[0]["builds"] == 1 and runs[0]["decks"] == [rad]
    meta = json.load(open(os.path.join(run, "run.json")))
    assert meta["builds"][0]["settings"]["rigid_vel"] == "0 0 -5000"
    assert "S355" in [x[1] for x in meta["builds"][0]["settings"]["mat_slots"]]
    L = cards(rad)
    assert any(l.startswith("/BCS/") for l in L) and any(l.startswith("/RBODY/") for l in L) and any(l.startswith("/MAT/PLAS_TAB/") for l in L)
    # starter only: Min dt offer from the added-mass table
    base["settings"]["rad_target"] = rad
    base["settings"]["dt_target_dmm"] = "2"
    ok(client.post("/api/explicit/solve", json=dict(base, mode="starter")))
    s = wait_status(client, lambda s: not s["busy"] and s["min_dt_offer"] and s["min_dt_offer"].get("job") == "xp_drop1_b01")
    assert s["min_dt_offer"]["dt"] == pytest.approx(6e-7) and s["rows"][0]["status"] == "Starter done"
    # full run
    ok(client.post("/api/explicit/solve", json=dict(base, mode="run")))
    s = wait_status(client, lambda s: not s["busy"] and any(r["job"] == "xp_drop1_b01" and r["status"] in ("Done", "Failed") for r in s["rows"]))
    row = next(r for r in s["rows"] if r["job"] == "xp_drop1_b01")
    assert row["status"] == "Done" and row["nc"] == 500 and row["progress"] == 100.0 and row["dmm"] == pytest.approx(5e-4)
    assert s["history"][0]["job"] == "xp_drop1_b01" and s["history"][0]["status"] == "Done"
    folder = os.path.dirname(rad)
    res = ok(client.post("/api/explicit/results", json={"folder": folder, "job": "xp_drop1_b01"}))
    assert len(res["frames"]) == 5 and res["energy"]["ke"][0] == 100.0 and res["outs"]["0000"] > 0
    assert "xp_drop1_b01_pv.json" in res["files"] and os.path.isfile(os.path.join(folder, "console.log")) is False
    g = ok(client.post("/api/explicit/geometry", json={"folder": folder, "job": "xp_drop1_b01"}))
    keys = [f["key"] for f in g["fields"]]
    assert "cell|3DELEM_Strain|eps1" in keys and "point|Displacement|mag" in keys and g["has_erosion"]
    f = ok(client.post("/api/explicit/frame", json={"folder": folder, "job": "xp_drop1_b01", "index": 4, "field": "cell|3DELEM_Strain|eps1"}))
    assert f["eroded"] == 1 and f["max"] == pytest.approx(0.015) and f["loc"] == "cell"
    assert b64(f["pos"], np.float32).reshape(-1, 3)[:, 2].min() == pytest.approx(-2.0)
    f0 = ok(client.post("/api/explicit/frame", json={"folder": folder, "job": "xp_drop1_b01", "index": 0, "field": "point|Displacement|mag"}))
    assert f0["loc"] == "point" and f0["max"] == 0.0 and f0["eroded"] == 0
    # post-processing: salvage rebuilds the frames, the series and the CSV from the A-files
    for p in glob.glob(os.path.join(folder, "*.vtk")) + glob.glob(os.path.join(folder, "*.vtk.series")):
        os.remove(p)
    ok(client.post("/api/explicit/post", json=dict(base, op="salvage", job="xp_drop1_b01", folder=folder)))
    wait_status(client, lambda s: "Salvage" not in s["tasks"] and os.path.isfile(os.path.join(folder, "xp_drop1_b01.vtk.series")))
    assert len(results.frames(folder, "xp_drop1_b01")) == 5
    # clean: listing, then delete
    c = ok(client.post("/api/explicit/run/clean", json={"path": run}))
    assert c["files"] >= 11
    ok(client.post("/api/explicit/run/clean", json={"path": run, "confirm": True}))
    assert not glob.glob(os.path.join(folder, "*.vtk")) and os.path.isfile(rad)
    st = ok(client.post("/api/explicit/run/settings", json={"path": run}))["settings"]
    assert st["fail_model"] == C.FAIL_TENS
    # a killed engine: Failed with the solver message
    monkeypatch.setenv("FAKE_OR_FAIL", "engine")
    ok(client.post("/api/explicit/solve", json=dict(base, mode="run")))
    s = wait_status(client, lambda s: not s["busy"] and next(r for r in s["rows"] if r["job"] == "xp_drop1_b01")["status"] in ("Done", "Failed"))
    row = next(r for r in s["rows"] if r["job"] == "xp_drop1_b01")
    assert row["status"] == "Failed" and "RUN KILLED: TOTAL MASS ERROR" in row["note"]
    # queue
    q = ok(client.post("/api/explicit/queue", json=dict(base, op="add")))
    assert q["queue"] == [rad]
    q = ok(client.post("/api/explicit/queue", json=dict(base, op="clear")))
    assert q["queue"] == []


def test_explicit_document_in_project(client, xp_doc):
    ok(client.put("/api/explicit/file/xp_drop1", json=xp_doc))
    docs = ok(client.get("/api/project/docs"))["docs"]
    d = next(x for x in docs if x["type"] == "explicit" and x["name"] == "xp_drop1")
    assert d["links"] == [{"type": "assembly", "name": "xp_drop"}]
    a = next(x for x in docs if x["type"] == "assembly" and x["name"] == "xp_drop")
    assert {"type": "explicit", "name": "xp_drop1"} in a["used_by"]
    # renaming the assembly updates the explicit document; renaming the document moves its folder
    ok(client.post("/api/project/doc", json={"op": "rename", "type": "assembly", "name": "xp_drop", "new": "xp_drop_r"}))
    assert ok(client.get("/api/explicit/file/xp_drop1"))["source"]["name"] == "xp_drop_r"
    ok(client.post("/api/project/doc", json={"op": "rename", "type": "assembly", "name": "xp_drop_r", "new": "xp_drop"}))
    f = ok(client.post("/api/explicit/folders", json={"name": "xp_drop1"}))
    os.makedirs(os.path.dirname(f["model_inp"]), exist_ok=True)
    open(f["model_inp"], "w").write("*NODE\n")
    ok(client.post("/api/project/doc", json={"op": "rename", "type": "explicit", "name": "xp_drop1", "new": "xp_drop2"}))
    f2 = ok(client.post("/api/explicit/folders", json={"name": "xp_drop2"}))
    assert f2["model_exists"] and not os.path.isdir(f["project_dir"])
    ok(client.post("/api/project/doc", json={"op": "rename", "type": "explicit", "name": "xp_drop2", "new": "xp_drop1"}))


def test_meta_and_errors(client):
    m = ok(client.get("/api/explicit/meta"))
    assert C.MATERIAL_LIBRARY and set(m["library"]) == {k for k, v in C.MATERIAL_LIBRARY.items() if v}
    assert m["analysis_modes"][0] == "Impact / drop test" and "floor" in m["mode_spec"]["Quasi-static (load-hold-unload)"]["hide_sections"]
    r = client.post("/api/explicit/build", json={"name": "none", "doc": {"source": {"kind": "inp", "inp": "/no/such.inp"}}, "settings": {}})
    assert r.status_code == 400 and "does not exist" in r.get_json()["error"]
    r = client.post("/api/explicit/model", json={"name": "x", "doc": {"source": {"kind": "shinycad", "name": ""}}})
    assert r.status_code == 400


# --------------------------------------------------------------------------- deck generator source

def _deck_doc(**kw):
    from drawgen.explicit import deck
    d = json.loads(json.dumps(deck.DEFAULT))
    d.update(kw)
    return {"source": {"kind": "deck"}, "deck": d, "default_material": "S355",
            "materials": {"S355": {"library": "Steel S355 (DNVGL 19-Point Standard)"}, "Mild": {"library": "", "E": 200000, "nu": 0.3, "rho": 7850}}}


def _inp_parts(path):
    """nodes {id: xyz}, elements {id: (elset, type, nodes)}, *ELSET sets, *SHELL SECTION rows, *BOUNDARY rows."""
    nodes, els, sets, secs, bnd = {}, {}, {}, {}, []
    mode = cur = None
    for raw in open(path):
        s = raw.strip()
        if not s or s.startswith("**"):
            continue
        if s.startswith("*"):
            kw = s.split(",")[0].upper()
            prm = {p.split("=")[0].strip().upper(): p.split("=")[1].strip() for p in s.split(",")[1:] if "=" in p}
            mode = {"*NODE": "n", "*ELEMENT": "e", "*ELSET": "s", "*SHELL SECTION": "t", "*BOUNDARY": "b"}.get(kw)
            cur = (prm.get("ELSET"), prm.get("TYPE"))
            if mode == "s":
                sets[cur[0]] = []
            continue
        v = [x.strip() for x in s.split(",") if x.strip()]
        if mode == "n":
            nodes[int(v[0])] = tuple(round(float(x), 6) for x in v[1:])
        elif mode == "e":
            els[int(v[0])] = (cur[0], cur[1], tuple(int(x) for x in v[1:]))
        elif mode == "s":
            sets[cur[0]] += [int(x) for x in v]
        elif mode == "t":
            secs[cur[0]] = float(v[0])
        elif mode == "b":
            bnd.append(v)
    return nodes, els, sets, secs, bnd


def test_deck_mesh_inp_matches_deck_mesh_script(tmp_path):
    """The model .inp of the deck source has the nodes, elements, element sets and sections that deck_mesh.py
    writes for the same model; one *ELEMENT block per set; the z = 0 elements tile the panel exactly once."""
    import subprocess
    import sys
    from drawgen.explicit import deck
    doc = _deck_doc(edges={"x0": "clamped", "xL": "pinned", "y0": "free", "yB": "free"}, shell="S4R")
    m = deck.model(doc["deck"])
    mj = tmp_path / "m_model.json"
    mj.write_text(json.dumps(m))
    ref = tmp_path / "ref.inp"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-m", "drawgen.explicit.deck_mesh", str(mj), "--size", "100", "-o", str(ref)],
                       cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    out = tmp_path / "model" / "deck.inp"
    res = deck.build(doc, str(out), "test")
    n1, e1, s1, t1, _b1 = _inp_parts(str(ref))
    n2, e2, _s2, t2, b2 = _inp_parts(str(out))
    assert n1 == n2 and {k: v[2] for k, v in e1.items()} == {k: v[2] for k, v in e2.items()}
    of = {e: k for k, ids in s1.items() for e in ids}
    assert all(of[e] == v[0] for e, v in e2.items()) and {v[1] for v in e2.values()} == {"S4R"}
    assert t1 == t2 == {"DECK": 8, "GIRDER_WEB": 10, "GIRDER_LOWER_FLANGE": 14, "BEAM_WEB": 8, "BEAM_LOWER_FLANGE": 12,
                        "STIFF_WEB": 6, "BEAM_FLANGE": 12, "GIRDER_FLANGE": 14}
    assert b2 == [["EDGE_X0", "1", "6"], ["EDGE_XL", "1", "3"]]
    assert (tmp_path / "model" / "deck_Parameters.pmp").read_text().splitlines()[1] == "DECK_t;8;8"
    # area of the elements at z = 0 (deck and top flanges): X distance x Y distance
    area = 0.0
    for _e, (_s, _t, c) in e2.items():
        p = [np.array(n2[i]) for i in c]
        if all(abs(q[2]) < 1e-9 for q in p):
            area += 0.5 * np.linalg.norm(np.cross(p[2] - p[0], p[3] - p[1]))
    assert area == pytest.approx(6000.0 * 4000.0)
    s = res["summary"]
    assert s["elements"] == len(e2) and s["supports"] == 2 and s["longest_edge"] <= 100.0 + 1e-6 and s["material"] == "S355"
    assert [x["set"] for x in s["sets"]][0] == "DECK" and s["sets"][0]["section"] == "Section-1"
    assert res["payload"]["ncell"] == len(e2)


def test_deck_section_properties_and_report():
    """Section designation, area, centroid and second moment of a beam (midsurface, deck plate excluded); the report
    lists the beams, sections, element sets with thicknesses and the plates, 96 columns wide."""
    from drawgen.explicit import deck
    sp = deck.section_props({"h": 500, "t_web": 10, "bf_top": 0, "bf_bot": 250, "t_flange": 14})
    assert sp["designation"] == "T 500x10/250x14" and sp["A"] == pytest.approx(8500.0)
    zc = (5000 * -250 + 3500 * -500) / 8500.0
    I = 10 * 500 ** 3 / 12 + 5000 * (-250 - zc) ** 2 + 250 * 14 ** 3 / 12 + 3500 * (-500 - zc) ** 2
    assert sp["zc"] == pytest.approx(zc) and sp["I"] == pytest.approx(I)
    assert deck.section_props({"h": 150, "t_web": 6, "bf_top": 0, "bf_bot": 0, "t_flange": 0})["designation"] == "FB 150x6"
    doc = _deck_doc()
    rep = deck.report(doc, step_path="x_deck.step")
    L = rep.splitlines()
    assert max(len(l) for l in L) <= 96
    assert any(l.startswith("1   GIRDER       y    x = 2000, y 0 to 4000") for l in L)
    sets = {l.split()[0]: l.split() for l in L if l.startswith(("DECK ", "GIRDER_FLANGE ", "STIFF_WEB "))
            and len(l.split()) == 6}
    assert sets["DECK"][1:3] == ["DECK_t", "8"] and sets["STIFF_WEB"][2] == "6"
    # deck plate and top flanges together cover L x B
    assert int(sets["DECK"][4]) + int(sets["GIRDER_FLANGE"][4]) + 1980000 == 6000 * 4000


def test_deck_check_and_errors(client):
    from drawgen.explicit import deck
    c = ok(client.post("/api/explicit/deck/check", json={"deck": deck.DEFAULT}))
    assert [p["name"] for p in c["parts"]][:3] == ["DECK", "GIRDER_WEB", "GIRDER_LOWER_FLANGE"] and not c["errors"]
    assert {s["set"]: s["param"] for s in c["sections"]}["GIRDER_LOWER_FLANGE"] == "GIRDER_FLANGE_t"
    d = json.loads(json.dumps(deck.DEFAULT))
    d["beams"].append(dict(d["beams"][2], pos=1000.3))           # coincident with BEAM at 1000
    d["beams"].append(dict(d["beams"][2], pos=1505.0))           # 5 mm from STIFF at 1500
    d["beams"].append(dict(d["beams"][5], name="FB", t_web=0))
    c = ok(client.post("/api/explicit/deck/check", json={"deck": d}))
    assert "two beams on one line" in c["errors"][0] and any("5 mm apart" in w for w in c["warnings"])
    assert any(e.startswith("FB_WEB") for e in c["inp_errors"])
    d = json.loads(json.dumps(deck.DEFAULT))
    d["beams"][0]["pos"] = 7000
    c = ok(client.post("/api/explicit/deck/check", json={"deck": d}))
    assert "outside x 0 to 6000 mm" in c["errors"][0]
    r = client.post("/api/explicit/model", json={"name": "xp_deck_bad", "doc": _deck_doc(deck_t=0)})
    j = wait_job(client, ok(r)["job"])
    assert j["state"] == "error" and "DECK" in j["error"]


def test_deck_model_build_and_step_part(client, tmp_path):
    """Write .inp of the deck source, deck build (one /PROP/SHELL per section, /BCS on the edges), STEP of the deck
    structure and the part <name>_deck with one Import surface body per component."""
    from drawgen import part
    doc = _deck_doc(size=200, edges={"y0": "clamped", "yB": "clamped"})
    base = {"name": "xp_deck1", "doc": doc, "settings": {"tstop": "0.01", "anim_frames": "4"}}
    ok(client.put("/api/explicit/file/xp_deck1", json=doc))
    j = wait_job(client, ok(client.post("/api/explicit/model", json=base))["job"])
    assert j["state"] == "done", j
    inp = j["result"]["inp"]
    assert inp.replace("\\", "/").endswith("explicit/xp_deck1/model/xp_deck1.inp")
    ok(client.post("/api/explicit/build", json=base))
    s = wait_status(client, lambda s: not s["building"] and s["last_build"] and "xp_deck1_b" in s["last_build"]["rad"])
    L = cards(s["last_build"]["rad"])
    heads = [l for l in L if l.startswith("/")]
    assert sum(h.startswith("/PROP/SHELL/") for h in heads) == 8 and sum(h.startswith("/BCS/") for h in heads) == 2
    assert block_after(L, "/PROP/SHELL/1", 4)[3].split()[2] == "8"
    assert any(h.startswith("/MAT/PLAS_TAB/") for h in heads)
    # STEP and part
    j = wait_job(client, ok(client.post("/api/explicit/deck/step", json=base))["job"])
    assert j["state"] == "done", j
    r = j["result"]
    assert r["part"] == "xp_deck1_deck" and os.path.isfile(r["step"]) and os.path.isfile(r["step"][:-5] + "_model.json")
    assert r["components"] == ["DECK", "GIRDER_WEB", "GIRDER_LOWER_FLANGE", "BEAM_WEB", "BEAM_LOWER_FLANGE", "STIFF_WEB", "BEAM_FLANGE", "GIRDER_FLANGE"]
    assert r["report"] == r["step"][:-5] + "_properties.txt" and os.path.isfile(r["report"])
    rep = open(r["report"], encoding="utf-8").read()
    assert "I 500x10/250x14/250x14" in rep and "FB 150x6" in rep and "EDGE_Y0    clamped    1-6" in rep
    p = ok(client.get("/api/part/file/xp_deck1_deck"))
    assert [f["type"] for f in p["features"]] == ["surf_import"] * 8 and p["features"][0]["label"] == "DECK"
    # the Import feature (solids) on the surface STEP names the Import surface feature
    with pytest.raises(ValueError, match="no solids, only surfaces .8 components: DECK.*Import surface"):
        part._import({"path": r["step"]})
    b = ok(client.post("/api/part/build", json={"part": p}))
    assert all(st["error"] is None and st["surface"] for st in b["status"]) and len(b["surfaces"]) == 8
    bodies = {}
    part.build(p, surfaces=bodies)
    z0 = [f["id"] for f in p["features"] if f["label"] in ("DECK", "BEAM_FLANGE", "GIRDER_FLANGE")]
    assert sum(bodies[i].area for i in z0) == pytest.approx(6000.0 * 4000.0)
    # a second STEP keeps the other features of the part and replaces the Import surface features
    p["features"].append({"id": "f99", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0, "depth": 5,
                          "sketch": {"entities": rect(10, 10)}})
    ok(client.put("/api/part/file/xp_deck1_deck", json=part.migrate(p)))
    wait_job(client, ok(client.post("/api/explicit/deck/step", json=base))["job"])
    p2 = ok(client.get("/api/part/file/xp_deck1_deck"))
    assert [f["type"] for f in p2["features"]].count("surf_import") == 8 and any(f["type"] == "extrude" for f in p2["features"])


def test_solver_packages_in_the_solvers_folder(tmp_path, monkeypatch):
    """OpenCourant: the exec folder of a package in <program>/solvers/ when OpenCourant exec folder is empty;
    CalculiX: ccx of a PrePoMax folder in <program>/solvers/."""
    from drawgen import analysis
    monkeypatch.setattr(host, "SOLVERS_DIR", str(tmp_path))
    w = host.Workspace()
    w.apply({"or_exec": ""})
    assert w._or_dir() == "" and w._or_env() is None
    ex = tmp_path / "OpenCourant" / "OpenCourant_win64" / "exec"
    ex.mkdir(parents=True)
    (tmp_path / "OpenCourant" / "OpenCourant_win64" / "hm_cfg_files").mkdir()
    name = "starter_win64.exe" if os.name == "nt" else "starter_linux64_gf"
    (ex / name).write_text("x")
    assert w._or_dir() == str(ex) and w._or_exe("starter") == str(ex / name)
    assert w._or_env()["RAD_CFG_PATH"].endswith("hm_cfg_files") or os.environ.get("RAD_CFG_PATH")
    w.apply({"or_exec": "/opt/x/exec"})
    assert w._or_dir() == "/opt/x/exec"
    monkeypatch.setattr(analysis, "SOLVERS_DIR", str(tmp_path))
    sv = tmp_path / "PrePoMax v3.0.0 RC2" / "Solver"
    sv.mkdir(parents=True)
    ext = ".exe" if os.name == "nt" else ""
    for n in ("ccx_dynamic", "ccx_static"):
        (sv / (n + ext)).write_text("x")
    assert analysis.find_ccx("") == str(sv / ("ccx_static" + ext))


def test_model_inp_of_shells_with_edge_supports(client, tmp_path):
    """Two surface parts (a plate and a stiffener) as shells, one rigid shell impactor and one solid block: the .inp
    holds *SHELL SECTION with the thickness and OFFSET, the edge support with the translations on all its nodes and
    the rotations on its shell nodes (NSET ..._R), and inp2rad converts it (/PROP/SHELL, /BCS)."""
    def surf(fid, name, plane, w, h, x=0.0, y=0.0):
        return {"id": fid, "name": name, "type": "surf_sketch", "kind": "planar", "plane": plane, "offset": 0,
                "sketch": {"entities": rect(w, h, x, y)}}
    ok(client.put("/api/part/file/xs_plate", json={"name": "xs_plate", "version": 2, "next": 2, "features": [surf("s1", "Plate", "XY", 200, 100)]}))
    ok(client.put("/api/part/file/xs_stiff", json={"name": "xs_stiff", "version": 2, "next": 2, "features": [surf("s1", "Stiffener", "XZ", 200, 30)]}))
    ok(client.put("/api/part/file/xs_imp", json={"name": "xs_imp", "version": 2, "next": 2, "features": [surf("s1", "Tup", "XY", 20, 20, -10, -10)]}))
    ok(client.put("/api/assembly/file/xs_asm", json={"name": "xs_asm", "next": 4, "components": [
        {"id": "1", "name": "plate", "source": {"type": "part", "name": "xs_plate"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "stiff", "source": {"type": "part", "name": "xs_stiff"}, "pos": [0, 50, 0], "rot": [180, 0, 0]},
        {"id": "3", "name": "tup", "source": {"type": "part", "name": "xs_imp"}, "pos": [100, 25, 20], "rot": [0, 0, 0]}]}))
    asm = ok(client.get("/api/assembly/file/xs_asm"))
    c = ok(client.post("/api/assembly/build", json={"assembly": asm}))["components"][0]
    x0 = next(i for i, r in enumerate(c["erefs"]) if r and r["kind"] == "line" and abs(r["c"][0]) < 1e-6)
    doc = {"name": "xs1", "source": {"kind": "shinycad", "type": "assembly", "name": "xs_asm"},
           "materials": {"S355": {"library": "", "E": 210000, "nu": 0.3, "rho": 7850}}, "default_material": "S355",
           "mesh": {"size": 10, "shell_type": "S4R"}, "bonded": True, "bodies": {},
           "shells": {"1:s1": {"t": 8}, "2:s1": {"t": 6, "offset": "positive"}, "3:s1": {"t": 5, "mode": "rigid"}},
           "supports": [{"id": "s1", "name": "clamp", "target": {"comp": "1", "edge": x0}, "dofs": [1, 1, 1, 1, 1, 1]}],
           "settings": {}, "next": 2}
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xs1", "doc": doc}))["job"])
    assert j["state"] == "done", j
    s = j["result"]["summary"]
    assert [(b["name"], b["role"], b["types"][0]) for b in s["bodies"]] == [
        ("plate / Plate", "deformable", "S4R"), ("stiff / Stiffener", "deformable", "S4R"), ("tup / Tup", "rigid", "S4R")]
    text = open(j["result"]["inp"]).read()
    for k in ("*SHELL SECTION, ELSET=B_PLATE_PLATE, MATERIAL=S355\n8", "*SHELL SECTION, ELSET=B_STIFF_STIFFENER, MATERIAL=S355, OFFSET=SPOS\n6",
              "*RIGID BODY, NSET=RB_TUP_TUP", "SUP_1_CLAMP, 1, 1", "SUP_1_CLAMP_R, 6, 6"):
        assert k in text, k
    m = meshview.read_inp(j["result"]["inp"])
    sup = text.split("*NSET, NSET=SUP_1_CLAMP\n")[1].split("*")[0]
    ids = [int(v) for v in sup.replace("\n", ",").split(",") if v.strip()]
    xyz = np.asarray([m["xyz"][list(m["node_ids"]).index(n)] for n in ids])
    assert len(ids) >= 100 / 10 and np.allclose(xyz[:, 0], 0) and np.allclose(xyz[:, 2], 0)
    # inp2rad
    import shutil
    import subprocess
    import sys
    from drawgen.explicit import build as xb
    work = tmp_path / "rad"
    work.mkdir()
    inp = str(work / "xs1.inp")
    shutil.copy(j["result"]["inp"], inp)
    r = subprocess.run([sys.executable, os.path.join(xb.SCRIPT_DIR, "inp2rad_run.py"), os.path.join(xb.SCRIPT_DIR, "inp2rad.py"), inp],
                       cwd=str(work), input="y\n" * 500, text=True, capture_output=True, timeout=300)
    rad = glob.glob(str(work / "*_0000.rad"))
    assert rad, r.stdout[-2000:] + r.stderr[-2000:]
    deck = open(rad[0], errors="replace").read()
    assert "/PROP/SHELL" in deck and "/BCS" in deck and "/RBODY" in deck


def test_model_inp_of_sections_and_node_sets_and_batch(client, tmp_path):
    """Decks (two surface parts XY 200 x 100, x 0 to 400) and a web (XZ 400 x 40 at y = 50, below the decks) as
    sections PLATE_Z0 and WEB_Y50, Section sizes Grid at 10 mm, node sets by plane (x = 0), free edges and outline
    of the plate section and of the web section: the .inp holds one *SHELL SECTION per section and one *NSET per
    node set with the node counts of the grid; the support on the node set X0 holds the translations and the
    rotations. Batch mode (run.py --batch explicit) writes the same .inp and, with --rad, the decks."""
    def surf(fid, name, plane, w, h):
        return {"id": fid, "name": name, "type": "surf_sketch", "kind": "planar", "plane": plane, "offset": 0,
                "sketch": {"entities": rect(w, h)}}
    ok(client.put("/api/part/file/xn_deck", json={"name": "xn_deck", "version": 2, "next": 2, "features": [surf("s1", "Deck", "XY", 200, 100)]}))
    ok(client.put("/api/part/file/xn_web", json={"name": "xn_web", "version": 2, "next": 2, "features": [surf("w", "Web", "XZ", 400, 40)]}))
    ok(client.put("/api/assembly/file/xn_asm", json={"name": "xn_asm", "next": 4, "components": [
        {"id": "1", "name": "deck", "source": {"type": "part", "name": "xn_deck"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "3", "name": "deck2", "source": {"type": "part", "name": "xn_deck"}, "pos": [200, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "web", "source": {"type": "part", "name": "xn_web"}, "pos": [0, 50, 0], "rot": [180, 0, 0]}]}))
    g = ok(client.post("/api/analysis/shell_groups", json={"source": {"type": "assembly", "name": "xn_asm"}}))["groups"]
    secs = [{"id": str(i + 1), "name": x["name"], "faces": x["faces"], "t": 8 if i == 0 else 6} for i, x in enumerate(g)]
    nsets = [{"id": "n1", "name": "X0", "kind": "plane", "axis": "x", "value": 0, "tol": 0.01},
             {"id": "n2", "name": "plate free", "kind": "section_edges", "body": "sec:1", "which": "free"},
             {"id": "n3", "name": "plate outline", "kind": "section_edges", "body": "sec:1", "which": "outline"},
             {"id": "n4", "name": "web free", "kind": "section_edges", "body": "sec:2", "which": "free"},
             {"id": "n5", "name": "web outline", "kind": "section_edges", "body": "sec:2", "which": "outline"}]
    doc = {"name": "xn1", "source": {"kind": "shinycad", "type": "assembly", "name": "xn_asm"},
           "materials": {"S355": {"library": "", "E": 210000, "nu": 0.3, "rho": 7850}}, "default_material": "S355",
           "mesh": {"size": 10, "shell_type": "S4R", "shell_size_mode": "grid"}, "bonded": True, "bodies": {}, "shells": {},
           "sections": secs, "nsets": nsets,
           "supports": [{"id": "s1", "name": "clamp", "target": {"nset": "n1"}, "dofs": [1, 1, 1, 1, 1, 1]}],
           "settings": {}, "next": 2}
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xn1", "doc": doc}))["job"])
    assert j["state"] == "done", j
    s = j["result"]["summary"]
    assert [(b["name"], b["role"], b["elements"]) for b in s["bodies"]] == [("PLATE_Z0", "deformable", 400), ("WEB_Y50", "deformable", 160)]
    assert s["shell"]["structured"] == s["shell"]["faces"] and s["shell"]["min_quality"] == pytest.approx(1.0, abs=1e-6)
    # x = 0: 11 deck nodes and 4 web nodes below the junction; plate free = outline (the junction is inside the
    # plate); web free: bottom and sides; web outline: plus the junction
    assert {n["name"]: n["nodes"] for n in s["nsets"]} == {"X0": 15, "PLATE_FREE": 100, "PLATE_OUTLINE": 100, "WEB_FREE": 49, "WEB_OUTLINE": 88}
    text = open(j["result"]["inp"]).read()
    for k in ("*SHELL SECTION, ELSET=B_PLATE_Z0, MATERIAL=S355\n8", "*SHELL SECTION, ELSET=B_WEB_Y50, MATERIAL=S355\n6",
              "*NSET, NSET=X0\n", "*NSET, NSET=WEB_OUTLINE\n", "SUP_1_CLAMP, 1, 1", "SUP_1_CLAMP_R, 6, 6"):
        assert k in text, k
    # batch mode
    ok(client.put("/api/explicit/file/xn1", json=doc))
    from drawgen import batch
    out = []
    assert batch.run("explicit", "xn1", rad=True, log=out.append) == 0, out
    assert any(x.startswith("explicit xn1: ") for x in out) and any("node set WEB_FREE: 49 nodes" in x for x in out)
    deck = next(x[6:] for x in out if x.startswith("deck: ") and x.endswith("_0000.rad"))
    assert "/PROP/SHELL" in open(deck, errors="replace").read()
    assert batch.run("explicit", "no_such_doc", log=out.append) == 2
    assert batch.run("other", "xn1", log=out.append) == 2


def test_reference_points_and_constraints_in_the_inp_and_deck(client, tmp_path):
    """Plate (surface 200 x 100) with reference points: rigid on the edge x = 0 (*RIGID BODY, inp2rad /RBODY),
    kinematic ux uy uz on the edge x = 200 (/RBE2), distributing on the plate face (/RBE3) and a free point; a
    spring from the free point to ground, a ball joint and an equation (/MPC), a support on a point (*BOUNDARY).
    After inp2rad the deck holds the cards with numbers above all numbers of the deck."""
    def surf(fid, name, plane, w, h):
        return {"id": fid, "name": name, "type": "surf_sketch", "kind": "planar", "plane": plane, "offset": 0,
                "sketch": {"entities": rect(w, h)}}
    ok(client.put("/api/part/file/xr_plate", json={"name": "xr_plate", "version": 2, "next": 2, "features": [surf("s1", "Plate", "XY", 200, 100)]}))
    ok(client.put("/api/assembly/file/xr_asm", json={"name": "xr_asm", "next": 2, "components": [
        {"id": "1", "name": "plate", "source": {"type": "part", "name": "xr_plate"}, "pos": [0, 0, 0], "rot": [0, 0, 0]}]}))
    asm = ok(client.get("/api/assembly/file/xr_asm"))
    c = ok(client.post("/api/assembly/build", json={"assembly": asm}))["components"][0]
    ex = lambda v: next(i for i, r in enumerate(c["erefs"]) if r and r["kind"] == "line" and abs(r["c"][0] - v) < 1e-6)
    pts = [{"id": "p1", "name": "Root", "xyz": [0, 50, 0], "coupling": "rigid", "edges": [{"comp": "1", "edge": ex(0)}]},
           {"id": "p2", "name": "Tip", "xyz": [200, 50, 0], "coupling": "kinematic", "dofs": [1, 1, 1, 0, 0, 0], "edges": [{"comp": "1", "edge": ex(200)}]},
           {"id": "p3", "name": "Mid", "xyz": [100, 50, 10], "coupling": "distributing", "dofs": [1, 1, 1, 1, 1, 1], "faces": [{"comp": "1", "face": 0}]},
           {"id": "p4", "name": "Free", "xyz": [250, 50, 0], "coupling": "none"}]
    doc = {"name": "xr1", "source": {"kind": "shinycad", "type": "assembly", "name": "xr_asm"},
           "materials": {"S355": {"library": "", "E": 210000, "nu": 0.3, "rho": 7850}}, "default_material": "S355",
           "mesh": {"size": 20, "shell_type": "S4R", "shell_size_mode": "grid"}, "bonded": True, "bodies": {},
           "shells": {"1:s1": {"t": 5}}, "points": pts,
           "supports": [{"id": "s1", "name": "root", "target": {"point": "p1"}, "dofs": [1, 1, 1, 1, 1, 1]}],
           "springs": [{"id": "k1", "name": "K1", "a": {"point": "p4"}, "b": None, "k": [100, 100, 100, 0, 0, 0]}],
           "joints": [{"id": "j1", "name": "J1", "type": "ball", "a": {"point": "p4"}, "b": {"point": "p2"}}],
           "equations": [{"id": "q1", "name": "Q1", "terms": [{"end": {"point": "p3"}, "dof": 3, "coef": 1},
                                                             {"end": {"at": [100, 50, 0]}, "dof": 3, "coef": -1}]}],
           "settings": {}, "next": 5}
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xr1", "doc": doc}))["job"])
    assert j["state"] == "done", j
    s = j["result"]["summary"]
    assert [(p["name"], p["coupling"]) for p in s["points"]] == [("Root", "rigid"), ("Tip", "kinematic"), ("Mid", "distributing"), ("Free", "none")]
    assert s["points"][0]["nodes"] == 100 / 20 + 1 and s["springs"] == 1 and s["equations"] == 4
    text = open(j["result"]["inp"]).read()
    root = s["points"][0]["node"]
    for k in ("*RIGID BODY, NSET=RP_ROOT, REF NODE=%d" % root, "**RAD /RBE2/<X", "**RAD /RBE3/<X", "**RAD /MPC/<X",
              "**RAD /PROP/TYPE13/<X", "**RAD /SPRING/<X", "*NSET, NSET=SPRING_GROUND", "SPRING_GROUND, 6, 6"):
        assert k in text, k
    # inp2rad and the cards
    import shutil
    import subprocess
    import sys
    from drawgen.explicit import build as xb
    work = tmp_path / "rad"
    work.mkdir()
    inp = str(work / "xr1.inp")
    shutil.copy(j["result"]["inp"], inp)
    r = subprocess.run([sys.executable, os.path.join(xb.SCRIPT_DIR, "inp2rad_run.py"), os.path.join(xb.SCRIPT_DIR, "inp2rad.py"), inp],
                       cwd=str(work), input="y\n" * 500, text=True, capture_output=True, timeout=300)
    rad = glob.glob(str(work / "*_0000.rad"))
    assert rad and "SHINYCAD constraints" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]
    deck = open(rad[0], errors="replace").read()
    assert "<X" not in deck and deck.index("# SHINYCAD constraints") < deck.rindex("\n/END") and "/RBODY" in deck
    head, tail = deck.split("# SHINYCAD constraints")
    import re as _re
    ids = [int(v) for v in _re.findall(r"^/(?:RBE2|RBE3|MPC|SPRING|PART|PROP/TYPE13|GRNOD/NODE)/(\d+)", tail, _re.M)]
    first = [int(ln[:10]) for ln in head.splitlines() if ln[:10].strip().isdigit()]
    assert len(ids) >= 8 and min(ids) > max(first)
    assert _re.search(r"^ +%d   111 000 +0 +\d+ +0$" % s["points"][1]["node"], tail, _re.M)       # RBE2 main node, Trarot
    mpc = tail.split("/MPC/")[1].splitlines()
    assert _re.match(r"^ +%d +1 +0 +-?1$" % s["points"][3]["node"], mpc[3]) or _re.match(r"^ +\d+ +1 +0 +-?1$", mpc[3])
    # a second apply does not add the cards twice
    from drawgen.explicit import radcards
    assert radcards.apply(inp, rad[0]) == 0


def test_velocities_and_node_sets_of_bodies_and_faces(client, tmp_path):
    """A solid block (deformable) and a rigid impactor plate above it: an initial velocity -5000 mm/s on the rigid
    impactor (*INITIAL CONDITIONS on all its nodes and its reference node, inp2rad /INIVEL/TRA), an imposed velocity
    on a reference point with a ramp of 1 ms (*AMPLITUDE and *BOUNDARY TYPE=VELOCITY, inp2rad /IMPVEL with its
    /FUNCT), node sets of the block body and of the bottom face of the solid (nodes at z = 0); an imposed velocity on
    supported nodes is refused; an imposed velocity with an amplitude of the document."""
    def surf(fid, name, plane, w, h):
        return {"id": fid, "name": name, "type": "surf_sketch", "kind": "planar", "plane": plane, "offset": 0,
                "sketch": {"entities": rect(w, h)}}
    ok(client.put("/api/part/file/xv_blk", json=part_rec("xv_blk", [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                                                                   "sketch": {"entities": rect(40, 40)}, "depth": 20}])))
    ok(client.put("/api/part/file/xv_tup", json={"name": "xv_tup", "version": 2, "next": 2, "features": [surf("s1", "Tup", "XY", 20, 20)]}))
    ok(client.put("/api/assembly/file/xv_asm", json={"name": "xv_asm", "next": 3, "components": [
        {"id": "1", "name": "block", "source": {"type": "part", "name": "xv_blk"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "tup", "source": {"type": "part", "name": "xv_tup"}, "pos": [10, 10, 30], "rot": [0, 0, 0]}]}))
    asm = ok(client.get("/api/assembly/file/xv_asm"))
    c = ok(client.post("/api/assembly/build", json={"assembly": asm}))["components"][0]
    bot = next(i for i, r in enumerate(c["refs"]) if r and r["kind"] == "plane" and abs(r["c"][2]) < 1e-6)
    doc = {"name": "xv1", "source": {"kind": "shinycad", "type": "assembly", "name": "xv_asm"},
           "materials": {"S355": {"library": "", "E": 210000, "nu": 0.3, "rho": 7850}}, "default_material": "S355",
           "mesh": {"size": 10}, "bonded": True, "bodies": {}, "shells": {"2:s1": {"t": 2, "mode": "rigid"}},
           "nsets": [{"id": "n1", "name": "BLOCK", "kind": "body", "bodies": ["1"]},
                     {"id": "n2", "name": "BOTTOM", "kind": "faces", "faces": [{"comp": "1", "face": bot}]}],
           "points": [{"id": "p1", "name": "Drive", "xyz": [20, 20, 20], "coupling": "none"}],
           "supports": [{"id": "s1", "name": "base", "target": {"nset": "n2"}, "dofs": [1, 1, 1, 0, 0, 0]}],
           "velocities": [{"id": "v1", "name": "drop", "target": {"body": "2:s1"}, "kind": "initial", "v": [0, 0, -5000]},
                          {"id": "v2", "name": "push", "target": {"point": "p1"}, "kind": "imposed", "v": [0, 0, -1000],
                           "dofs": [1, 1, 1, 0, 0, 0], "ramp": 0.001}],
           "settings": {}, "next": 3}
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xv1", "doc": doc}))["job"])
    assert j["state"] == "done", j
    s = j["result"]["summary"]
    ns = {n["name"]: n["nodes"] for n in s["nsets"]}
    assert ns["BOTTOM"] >= 25 and ns["BLOCK"] > ns["BOTTOM"]
    text = open(j["result"]["inp"]).read()
    m = meshview.read_inp(j["result"]["inp"])
    ids = [int(v) for v in text.split("*NSET, NSET=BOTTOM\n")[1].split("*")[0].replace("\n", ",").split(",") if v.strip()]
    xyz = np.asarray([m["xyz"][list(m["node_ids"]).index(n)] for n in ids])
    assert np.allclose(xyz[:, 2], 0)
    tup = next(b for b in s["bodies"] if b["role"] == "rigid")
    for k in ("*INITIAL CONDITIONS, TYPE=VELOCITY\nVEL_1_DROP, 1, 0\nVEL_1_DROP, 2, 0\nVEL_1_DROP, 3, -5000",
              "*AMPLITUDE, NAME=VA_2\n0, 0, 0.001, 1, 1000.001, 1", "*BOUNDARY, AMPLITUDE=VA_2 , TYPE=VELOCITY\nVEL_2_PUSH, 1, 1, 0\nVEL_2_PUSH, 2, 2, 0\nVEL_2_PUSH, 3, 3, -1000"):
        assert k in text, k
    vel1 = text.split("*NSET, NSET=VEL_1_DROP\n")[1].split("*")[0]
    assert str(tup["ref_node"]) in vel1.replace(",", " ").split()
    import shutil
    import subprocess
    import sys
    from drawgen.explicit import build as xb
    work = tmp_path / "rad"
    work.mkdir()
    inp = str(work / "xv1.inp")
    shutil.copy(j["result"]["inp"], inp)
    r = subprocess.run([sys.executable, os.path.join(xb.SCRIPT_DIR, "inp2rad_run.py"), os.path.join(xb.SCRIPT_DIR, "inp2rad.py"), inp],
                       cwd=str(work), input="y\n" * 500, text=True, capture_output=True, timeout=300)
    rad = glob.glob(str(work / "*_0000.rad"))
    assert rad, r.stdout[-2000:] + r.stderr[-2000:]
    deck = open(rad[0], errors="replace").read()
    import re as _re
    iv = deck.split("/INIVEL/TRA/")[1].splitlines()
    assert _re.match(r"^ +0 +0 +-5000 +\d+", iv[3]), iv[:5]
    imp = deck.split("/IMPVEL/")[1].splitlines()
    fid = int(imp[4][:10])
    assert imp[1] == "VEL_2_PUSH" and imp[4][10:20].strip() == "Z" and float(imp[6][20:40]) == -1000
    fn = deck.split("/FUNCT/%d\n" % fid)[1].split("/")[0]
    assert [float(v) for v in fn.replace("\n", " ").split() if _re.match(r"^-?[\d.]+(e[-+]?\d+)?$", v)][:4] == [0, 0, 0.001, 1]
    # imposed velocity on held nodes
    bad = dict(doc, velocities=[{"id": "v3", "name": "bad", "target": {"nset": "n2"}, "kind": "imposed", "v": [0, 0, 1], "dofs": [0, 0, 1, 0, 0, 0]}])
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xv2", "doc": bad}))["job"])
    assert j["state"] == "error" and "held by support base" in j["error"]
    # imposed velocity with an amplitude: its points from t = 0 (the first factor before the first point), constant
    # after the last point; an amplitude not in the document refused
    va = dict(doc["velocities"][1], amplitude="a1")
    amp = dict(doc, amplitudes=[{"id": "a1", "name": "pulse", "points": [[0.002, 0.5], [0.0005, 0], [0.001, 1]]}], velocities=[va])
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xv3", "doc": amp}))["job"])
    assert j["state"] == "done", j
    assert "*AMPLITUDE, NAME=VA_1\n0, 0, 0.0005, 0, 0.001, 1, 0.002, 0.5\n1000.002, 0.5\n*BOUNDARY, AMPLITUDE=VA_1 , TYPE=VELOCITY" in open(j["result"]["inp"]).read()
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xv4", "doc": dict(amp, amplitudes=[])}))["job"])
    assert j["state"] == "error" and "amplitude a1 not found" in j["error"]


# --------------------------------------------------------------------------- explicit functions

def _wait(cond, timeout=60.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.2)
    return False


def _console(client):
    return "\n".join(t for _s, t in ok(client.get("/api/explicit/status?since=0"))["log"])


def test_tools_list_add_launch_hide_restore(client, tmp_path):
    from drawgen import web
    T = ok(client.get("/api/explicit/tools"))
    keys = [t["key"] for t in T["tools"]]
    for k in ("inertia_builder", "inertia_calc", "inp2rad", "inp_to_linear", "job_audit", "rad_preview",
              "make_gauge_rings", "relative_disp", "deck_builder", "deck_gui", "deck_mesh", "deck_elsets",
              "stiffened_panel", "stiffened_panel_conformal", "deck_strip", "inp2unv"):
        assert k in keys
    by = {t["key"]: t for t in T["tools"]}
    for k in ("inertia_builder", "inertia_calc", "inp2rad", "inp_to_linear", "job_audit", "rad_preview", "make_gauge_rings", "relative_disp"):
        assert by[k]["exists"] and by[k]["builtin"] and by[k]["doc"]
    assert by["deck_mesh"]["group"] == "Model generation (repo scripts)" and by["deck_mesh"]["path"].endswith("DECK_GENERATOR/deck_mesh.py")
    assert T["file"] == os.path.join(os.path.dirname(web.CONFIG_PATH), "tools.json").replace("\\", "/")
    # user script: added, launched with arguments (output captured into the console off Windows), removed
    sc = tmp_path / "echo_args.py"
    sc.write_text("import sys, pathlib\npathlib.Path(sys.argv[0]).with_suffix('.out').write_text(' '.join(sys.argv[1:]))\nprint('ARGS', *sys.argv[1:])\n")
    T = ok(client.post("/api/explicit/tools", json={"op": "add", "path": str(sc), "title": "Echo", "kind": "cli"}))
    u = [t for t in T["tools"] if not t["builtin"]]
    assert len(u) == 1 and u[0]["key"] == "user:echo_args" and u[0]["title"] == "Echo  (CLI)" and u[0]["group"] == "My scripts"
    assert client.post("/api/explicit/tools", json={"op": "add", "path": str(sc)}).status_code == 400      # not twice
    saved = json.load(open(T["file"]))
    assert saved["tools"][0]["script"] == str(sc) and saved["_readme"]
    ok(client.post("/api/explicit/tools", json={"op": "launch", "key": "user:echo_args", "args": '-x "a b"', "name": "tl",
                                                 "doc": {"source": {"kind": "inp", "inp": ""}}, "settings": {}}))
    assert _wait(lambda: (tmp_path / "echo_args.out").exists())
    assert (tmp_path / "echo_args.out").read_text() == "-x a b"
    assert _wait(lambda: "[Echo  (CLI)] ARGS -x a b" in _console(client))
    assert ok(client.get("/api/explicit/tools"))["tools"][-1]["args"] == '-x "a b"'          # box text remembered
    # auto_arg "dir": job_audit on Output Dir
    od = tmp_path / "runs"
    od.mkdir()
    ok(client.post("/api/explicit/tools", json={"op": "args", "key": "job_audit", "args": ""}))
    cwd = os.getcwd()
    ok(client.post("/api/explicit/tools", json={"op": "launch", "key": "job_audit", "args": "", "name": "tl",
                                                 "doc": {"source": {"kind": "inp", "inp": ""}}, "settings": {"out_dir": str(od)}}))
    assert _wait(lambda: "Tools: Job audit  (CLI) finished" in _console(client))
    assert "[Output Dir]" in _console(client)
    for ext in (".txt", ".csv"):                      # job_audit writes job_audit.txt / .csv into its working folder
        f = os.path.join(os.path.dirname(host.__file__), "job_audit" + ext)
        if os.path.isfile(f):
            os.remove(f)
    assert os.getcwd() == cwd
    r = client.post("/api/explicit/tools", json={"op": "launch", "key": "inp2rad", "args": "", "name": "tl",
                                                  "doc": {"source": {"kind": "inp", "inp": ""}}, "settings": {}})
    assert r.status_code == 400 and "needs a file" in r.get_json()["error"]
    T = ok(client.post("/api/explicit/tools", json={"op": "remove", "key": "user:echo_args"}))
    assert not [t for t in T["tools"] if not t["builtin"]] and sc.exists()
    # built-in: hidden, restored
    T = ok(client.post("/api/explicit/tools", json={"op": "remove", "key": "inp2unv"}))
    assert "inp2unv" in T["hidden"] and [t for t in T["tools"] if t["key"] == "inp2unv"][0]["hidden"]
    T = ok(client.post("/api/explicit/tools", json={"op": "restore", "key": "inp2unv"}))
    assert "inp2unv" not in T["hidden"]
    # hand-edited tools.json with a bad entry
    json.dump({"tools": [{"script": str(sc), "title": "Hand", "kind": "gui"}, {"title": "no script"}], "hidden": ["deck_gui"]}, open(T["file"], "w"))
    T = ok(client.post("/api/explicit/tools", json={"op": "reload"}))
    assert "#2" in T["file_error"] and [t["title"] for t in T["tools"] if not t["builtin"]] == ["Hand"] and T["hidden"] == ["deck_gui"]
    json.dump({"tools": [], "hidden": []}, open(T["file"], "w"))


def test_inertia_payload_summary(client, tmp_path):
    p = tmp_path / "imp.json"
    p.write_text(json.dumps({"mass": 0.5, "cx": 1, "cy": 2, "cz": 3, "Jxx": 10, "Jyy": 20, "Jzz": 30, "Jxy": 5, "Jyz": 0, "Jxz": 0}))
    j = ok(client.post("/api/explicit/inertia", json={"path": str(p)}))
    assert j["state"] == "ready" and "mass   : 0.5" in j["text"] and "full tensor written" in j["text"] and "READY" in j["text"]
    p.write_text(json.dumps({"mass": 0.5, "cx": 0, "cy": 0, "cz": 0, "Jxx": 0, "Jyy": 1, "Jzz": 1, "Jxy": 0, "Jyz": 0, "Jxz": 0}))
    assert ok(client.post("/api/explicit/inertia", json={"path": str(p)}))["state"] == "invalid"
    assert ok(client.post("/api/explicit/inertia", json={"path": ""}))["state"] == "off"
    assert ok(client.post("/api/explicit/inertia", json={"path": str(tmp_path / "none.json")}))["state"] == "missing"
    # primitives file of the inertia builder
    p.write_text(json.dumps({"units": "mm_t", "primitives": [{"name": "a", "mass": 1.0, "center": [0, 0, 0], "dims": [10, 20, 30]}]}))
    j = ok(client.post("/api/explicit/inertia", json={"path": str(p)}))
    assert j["state"] == "ready" and abs(j["payload"]["Jxx"] - (20 ** 2 + 30 ** 2) / 12.0) < 1e-9


def _rivet_deck(folder):
    """Starter deck with the /NODE block of two plates (z = +1, z = -1) with nodes on rings r = 4, 6, 8 mm."""
    import math
    L = ["#RADIOSS STARTER", "/BEGIN", "rivet", "/NODE"]
    nid = 0
    for z in (1.0, -1.0):
        for r in (4.0, 6.0, 8.0):
            for k in range(12):
                nid += 1
                a = math.radians(30 * k)
                L.append("%10d%20.6f%20.6f%20.6f" % (nid, r * math.cos(a), r * math.sin(a), z))
    L += ["/END"]
    p = os.path.join(folder, "cp_0000.rad")
    open(p, "w").write("\n".join(L) + "\n")
    return p


def test_rivet_gauge_rings_columns_extract_and_load(client, tmp_path):
    deck = _rivet_deck(str(tmp_path))
    req = {"name": "rv", "doc": {"source": {"kind": "inp", "inp": ""}},
           "settings": {"rad_target": deck, "out_dir": str(tmp_path), "rv_radius": "6.0", "rv_maxnodes": "4"}}
    j = ok(client.post("/api/explicit/rivet", json=dict(req, op="rings")))
    assert j["nodes"] == 72 and [r["tag"] for r in j["rings"]] == ["P1", "P2"] and all(len(r["nodes"]) == 4 for r in j["rings"])
    assert os.path.isfile(os.path.join(str(tmp_path), "th_gauge_rings.inc")) and os.path.isfile(os.path.join(str(tmp_path), "gauge_rings.json"))
    assert "/TH/NODE" in open(os.path.join(str(tmp_path), "th_gauge_rings.inc")).read()
    r = client.post("/api/explicit/rivet", json=dict(req, op="columns"))
    assert r.status_code == 400 and "No results CSV" in r.get_json()["error"]
    rows = ['"time","P1 DX","P1 DY","P1 DZ","P2 DX","P2 DY","P2 DZ","RBODY 12 FX"']
    for k in range(11):
        f = 100.0 * k if k <= 6 else 600.0 - 290.0 * (k - 6)
        rows.append("%g,%g,0,0,0,0,0,%g" % (k * 1e-4, 0.1 * k, max(f, 0.0)))
    open(os.path.join(str(tmp_path), "cp_Results.csv"), "w").write("\n".join(rows) + "\n")
    j = ok(client.post("/api/explicit/rivet", json=dict(req, op="columns")))
    assert j["columns"][-1] == "RBODY 12 FX" and not j["unnamed"]
    r = client.post("/api/explicit/rivet", json=dict(req, op="extract"))
    assert r.status_code == 400 and "Force column is empty" in r.get_json()["error"]
    req["settings"].update({"rv_force_col": "RBODY 12 FX", "rv_component": "x", "rv_case_id": "A1"})
    c = ok(client.post("/api/explicit/rivet", json=dict(req, op="extract")))["curve"]
    assert c["label"] == "A1" and c["peak_force"] == 600.0 and abs(c["peak_disp"] - 0.6) < 1e-12 and abs(c["fail_disp"] - 0.8) < 1e-12
    assert "Peak force" in c["summary"] and os.path.isfile(c["out_path"])
    c2 = ok(client.post("/api/explicit/rivet", json=dict(req, op="load_fd", path=c["out_path"])))["curve"]
    assert c2["label"] == "cp_Results_fd" and c2["peak_force"] == 600.0 and len(c2["disp"]) == 11
    assert "Rivet: wrote" in _console(client)


def test_history_env_dirs_results_csv_png_and_queue(client, tmp_path):
    from drawgen import web
    WS = web.EXPLICIT
    run = tmp_path / "run1"
    run.mkdir()
    (run / "jb_0000.rad").write_text("/BEGIN\n/END\n")
    ok(client.post("/api/explicit/history", json={"op": "clear"}))
    WS._history_add("jb", "Done", str(run), "Local (Windows)")
    WS._history_add("jx", "Failed", str(tmp_path / "gone"), "Local (Windows)")
    h = ok(client.get("/api/explicit/status?since=0"))["history"]
    assert [(e["job"], e["index"]) for e in h] == [("jx", 1), ("jb", 0)]
    j = ok(client.post("/api/explicit/history", json={"op": "load", "index": 0, "job": "jb", "folder": str(run)}))
    assert j["rad_target"].endswith("run1/jb_0000.rad") and j["out_dir"] == str(run).replace("\\", "/")
    assert client.post("/api/explicit/history", json={"op": "load", "index": 1, "job": "jx", "folder": str(tmp_path / "gone")}).status_code == 400
    j = ok(client.post("/api/explicit/history", json={"op": "remove", "index": 1}))
    assert [e["job"] for e in j["history"]] == ["jb"]
    # Env switch: dirs remembered per Env
    j = ok(client.post("/api/explicit/env_switch", json={"old": "Local (Windows)", "new": "Remote (Linux)", "rad_target": "C:/a/x_0000.rad", "out_dir": "C:/a"}))
    assert j == {"rad_target": None, "out_dir": None}
    assert "Remote resolution" in _console(client)
    j = ok(client.post("/api/explicit/env_switch", json={"old": "Remote (Linux)", "new": "Local (Windows)", "rad_target": "Z:/r/y_0000.rad", "out_dir": "Z:/r"}))
    assert j == {"rad_target": "C:/a/x_0000.rad", "out_dir": "C:/a"}
    assert web.load_config()["explicit"]["env_dirs"]["Remote (Linux)"]["out_dir"] == "Z:/r"
    # results CSV of any folder
    p = tmp_path / "jq_Results.csv"
    p.write_text('"time","INTERNAL ENERGY","KINETIC ENERGY"\n0,0,100\n0.001,10,90\n0.002,20,80\n')
    j = ok(client.post("/api/explicit/results_csv", json={"path": str(p)}))
    assert j["job"] == "jq" and j["ke"] == [100, 90, 80] and j["ie"] == [0, 10, 20]
    p2 = tmp_path / "jzT01.csv"
    p2.write_text(p.read_text())
    assert ok(client.post("/api/explicit/results_csv", json={"path": str(p2)}))["job"] == "jz"
    # PNG of a plot
    png = base64.b64encode(b"\x89PNG\r\n\x1a\nxx").decode()
    j = ok(client.post("/api/explicit/save_png", json={"path": str(tmp_path / "plot"), "data": "data:image/png;base64," + png}))
    assert j["path"].endswith("plot.png") and open(j["path"], "rb").read().startswith(b"\x89PNG")
    # queue: kept in config.json > explicit > job_queue
    deck = str(run / "jb_0000.rad")
    ok(client.post("/api/explicit/queue", json={"op": "add", "name": "q", "doc": {"source": {"kind": "inp", "inp": ""}}, "settings": {"rad_target": deck}}))
    ok(client.get("/api/explicit/status?since=0"))
    assert web.load_config()["explicit"]["job_queue"] == [deck]
    ok(client.post("/api/explicit/queue", json={"op": "clear", "name": "q", "doc": {"source": {"kind": "inp", "inp": ""}}, "settings": {}}))
    ok(client.get("/api/explicit/status?since=0"))
    assert web.load_config()["explicit"]["job_queue"] == []


def test_plot_ke_rebuilds_csv_from_t_file(client, tmp_path):
    exe = fake_opencourant.install(str(tmp_path / "exec"))
    ok(client.put("/api/explicit/env", json={"or_exec": exe}))
    d = tmp_path / "res"
    d.mkdir()
    (d / "kjT01").write_text("0 0.001 0.002 0.003\n")
    ok(client.post("/api/explicit/post", json={"op": "plot_ke", "job": "kj", "folder": str(d), "name": "k",
                                                "doc": {"source": {"kind": "inp", "inp": ""}}, "settings": {}}))
    assert _wait(lambda: (d / "kj_Results.csv").exists() and "KE plot" in _console(client) and
                 not [t for t in ok(client.get("/api/explicit/status?since=0"))["tasks"] if t == "Plot KE"])
    assert "rebuilt kj_Results.csv" in _console(client)
    assert host.Workspace()._parse_th_csv(str(d / "kj_Results.csv"))[1] == [100, 90, 80, 70]
    # folder only (no job): the newest *_Results.csv of the folder
    ok(client.post("/api/explicit/post", json={"op": "plot_ke", "job": "", "folder": str(d), "name": "k",
                                                "doc": {"source": {"kind": "inp", "inp": ""}}, "settings": {}}))
    ok(client.put("/api/explicit/env", json={"or_exec": ""}))


def test_legacy_settings_migration_and_rivet_mode(client, tmp_path):
    from drawgen.explicit import modes
    s, notes = host.migrate({"auto_tie": False, "tie_pairs": "A > B : 1", "self_contact": False, "rigid_vel": "0 0 -1",
                             "mat1": "Aluminium 6061-T6 (Johnson-Cook, Lesuer)"}, legacy=True)
    assert s["tie_mode"] == C.TIE_SCOPED and s["contact_mode"] == C.CONTACT_NONE and s["rigid_vel_mode"] == C.RBV_EXPL
    assert s["mat1"] == "Aluminium 6061-T6 (Johnson-Cook)" and len(notes) == 3
    s, notes = host.migrate({"rigid_vel": "0 0 -1"})                 # a ShinyCAD document: no migration
    assert "rigid_vel_mode" not in s and not notes
    assert host.migrate({"auto_tie": True})[0]["tie_mode"] == C.TIE_AUTO
    assert host.migrate({"tie_dist": "2", "auto_tie": False})[0]["tie_mode"] == C.TIE_GLOBAL
    w = host.Workspace()
    w.apply({"self_contact": True, "contact_mode": "old"})
    assert w.contact_mode.get() == C.CONTACT_T7
    run = tmp_path / "r"
    run.mkdir()
    json.dump({"builds": [{"settings": {"auto_tie": False, "tie_dist": "0", "rigid_mode": "Rigidify part", "tstop": "0.2"}}]}, open(run / "run.json", "w"))
    j = ok(client.post("/api/explicit/run/settings", json={"path": str(run)}))
    assert j["settings"]["tie_mode"] == C.TIE_NONE and j["settings"]["rigid_vel_mode"] == C.RBV_NONE and any("Rigidify" in n for n in j["notes"])
    m = ok(client.get("/api/explicit/meta"))
    assert m["defaults"]["analysis_mode"] == modes.MODE_ALL and modes.MODE_RIVET in m["analysis_modes"]
    assert "rivet" in m["mode_spec"][modes.MODE_IMPACT]["hide_sections"] and "rivet" not in m["mode_spec"][modes.MODE_RIVET]["hide_sections"]
    assert "point_mass" in m["mode_spec"][modes.MODE_RIVET]["hide_sections"]
    for k in ("tie_doc", "contact_doc", "rbv_doc", "fail_doc", "travel_doc", "inertia_doc"):
        assert m[k]
    assert m["travel_mm"] == [100.0, 500.0, 1000.0] and m["rivet"]["import_error"] is None
    assert m["defaults"]["rv_thgroup"] == "900"


def test_read_inp_shell_section_thickness(tmp_path):
    """read_inp: thickness and offset of the *SHELL SECTION of each shell *ELEMENT ELSET (Shell thickness view)."""
    p = tmp_path / "th.inp"
    p.write_text("*NODE\n1,0,0,0\n2,1,0,0\n3,1,1,0\n4,0,1,0\n5,0,0,1\n6,1,0,1\n7,1,1,1\n8,0,1,1\n"
                 "*ELEMENT, TYPE=S4R, ELSET=PL\n1,1,2,3,4\n*ELEMENT, TYPE=S3, ELSET=TR\n2,1,2,3\n"
                 "*ELEMENT, TYPE=C3D8, ELSET=BLK\n3,1,2,3,4,5,6,7,8\n"
                 "*SHELL SECTION, ELSET=pl, MATERIAL=S, OFFSET=SPOS\n3.0\n*SHELL SECTION, ELSET=TR, MATERIAL=S, OFFSET=-0.25\n2, 5\n"
                 "*SOLID SECTION, ELSET=BLK, MATERIAL=S\n")
    m = meshview.read_inp(str(p))
    assert [x[0] for x in m["parts"]] == ["PL", "TR", "BLK"]
    assert m["part_thick"] == [[3.0, 0.5], [2.0, -0.25], None]


def test_anim_file_reader(tmp_path):
    """Animation files read directly: element kinds, part IDs, erosion, fields, tensors, frames and the 3D view data."""
    p = str(tmp_path / "jobA001")
    xyz, disp = anim_writer.sample(p, time=0.0)
    anim_writer.sample(str(tmp_path / "jobA002"), time=0.002, d=0.25, erode=True)
    anim_writer.sample(str(tmp_path / "jobA010"), time=0.02, d=1.0, erode=True)
    assert anim.is_anim(p) and anim.anim_time(str(tmp_path / "jobA002")) == 0.002
    v = anim.read_anim(str(tmp_path / "jobA002"))
    kinds = {k: (c.tolist(), i.tolist()) for k, c, _p, i in v["cells"]}
    assert kinds["line"] == ([[16, 17]], [0]) and kinds["quad"] == ([[0, 1, 2, 3]], [1])
    assert kinds["tri"] == ([[0, 2, 3]], [2]) and kinds["hex"][1] == [3] and kinds["tet"] == ([[12, 13, 14, 15]], [4])
    c = v["cell"]
    assert c["PART_ID"].tolist() == [4, 1, 1, 2, 3] and c["EROSION_STATUS"].tolist() == [1, 1, 0, 1, 1]
    assert c["ELEMENT_ID"].tolist() == [5001, 1001, 1002, 3001, 3002] and v["point"]["NODE_ID"][0] == 101
    vm2, vm3 = c["2DELEM_Von_Mises"], c["3DELEM_Von_Mises"]
    assert np.isnan(vm2[[0, 3, 4]]).all() and vm2[1:3].tolist() == [10.0, 20.0] and vm3[3:].tolist() == [30.0, 40.0]
    assert c["1DELEM_Force"][0] == 7.0 and c["1DELEM_TorsorM6"][0] == 9.0
    T2 = c["2DELEM_Strain_(upper)"][1].reshape(3, 3)
    assert np.allclose(T2, [[0.01, 0.003, 0], [0.003, 0.02, 0], [0, 0, 0]])
    T3 = c["3DELEM_Stress"][3].reshape(3, 3)
    assert np.allclose(T3, [[1, 4, 5], [4, 2, 6], [5, 6, 3]])
    assert np.allclose(v["point"]["Displacement"][4], [0.25, 0, 0]) and v["point"]["Velocity_Norm"][2] == 1.0
    # frames: number order, time of the header; jobs lists the A-files
    fr = results.frames(str(tmp_path), "job")
    assert [os.path.basename(e["file"]) for e in fr] == ["jobA001", "jobA002", "jobA010"]
    assert [e["time"] for e in fr] == [0.0, 0.002, 0.02] and results.jobs(str(tmp_path)) == ["job"]
    g = results.geometry(str(tmp_path), "job")
    keys = [f["key"] for f in g["fields"]]
    assert "cell|3DELEM_Stress|xz" in keys and "cell|2DELEM_Strain_(upper)|eps1" in keys and "point|@disp|mag" not in keys
    assert g["payload"]["pos"] and g["has_erosion"]
    f = results.frame(str(tmp_path), "job", 2, "cell|3DELEM_Stress|xz")
    vals = b64(f["values"], np.float32)
    assert f["eroded"] == 1 and np.nanmax(vals) == 5.0 and np.isnan(vals).sum() == 3
    f = results.frame(str(tmp_path), "job", 1, "cell|2DELEM_Strain_(upper)|eps1")
    assert f["max"] == pytest.approx(0.04)
    f = results.frame(str(tmp_path), "job", 2, "point|Displacement|mag")
    assert f["max"] == pytest.approx(1.0) and b64(f["pos"], np.float32).reshape(-1, 3)[4, 0] == pytest.approx(3.0)
    # parts: names of the animation file, per part max |d|, signed components and range of the field
    assert [(q["id"], q["name"], q["cells"], q["nodes"]) for q in g["parts"]] == [(1, "shell part", 2, 4), (2, "solid", 1, 8), (3, "tet", 1, 4), (4, "beam", 1, 2)]
    assert b64(g["payload"]["part"], np.int32).tolist() == [3, 0, 0, 2, 1]
    P = f["parts"]
    assert P[0]["umax"] == 0 and P[1]["umax"] == pytest.approx(1.0) and P[1]["ucomp"] == pytest.approx([1.0, 0, 0])
    assert P[0]["max"] == 0 and P[1]["min"] == pytest.approx(1.0)
    P = results.frame(str(tmp_path), "job", 2, "cell|3DELEM_Stress|xz")["parts"]
    assert P[1]["max"] == pytest.approx(5.0) and P[2]["max"] == pytest.approx(2.0) and "max" not in P[0]
    # an animation file that ends early
    data = open(p, "rb").read()
    open(str(tmp_path / "cutA001"), "wb").write(data[:len(data) // 2])
    with pytest.raises(anim.AnimError):
        anim.read_anim(str(tmp_path / "cutA001"))


def test_anim_without_displacement_vector(tmp_path):
    """No Displacement vector in the animation files: displacement from the coordinates of the first frame."""
    base = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    for k, d in ((1, 0.0), (2, 0.5)):
        anim_writer.write_anim(str(tmp_path / ("plateA%03d" % k)), 0.001 * (k - 1), base + [0, 0, d],
                               quads=[[0, 1, 2, 3]], parts2=[(1, "7 plate")], numbering=False, mass=False)
    g = results.geometry(str(tmp_path), "plate")
    assert [f["key"] for f in g["fields"]][:4] == ["point|@disp|mag", "point|@disp|0", "point|@disp|1", "point|@disp|2"]
    f = results.frame(str(tmp_path), "plate", 1, "point|@disp|2")
    assert f["max"] == pytest.approx(0.5) and np.allclose(b64(f["disp"], np.float32).reshape(-1, 3)[:, 2], 0.5)
    v = anim.read_anim(str(tmp_path / "plateA001"))
    assert v["point"]["NODE_ID"].tolist() == [1, 2, 3, 4] and v["cell"]["PART_ID"].tolist() == [7]


def test_solve_without_vtk_conversion(client, xp_doc, tmp_path):
    """Convert to VTK off: no .vtk frames; the Results read the animation files."""
    exe = fake_opencourant.install(str(tmp_path / "exec"))
    ok(client.put("/api/explicit/env", json={"or_exec": exe, "run_target": host.LOCAL}))
    base = {"name": "xp_drop1", "doc": xp_doc, "settings": dict(xp_doc["settings"], vtk_convert=False)}
    wait_job(client, ok(client.post("/api/explicit/model", json=base))["job"])
    t0 = time.time() - 1
    ok(client.post("/api/explicit/build", json=base))
    s = wait_status(client, lambda s: not s["building"] and s["last_build"] and os.path.getmtime(s["last_build"]["rad"]) >= t0)
    rad = s["last_build"]["rad"]
    base["settings"]["rad_target"] = rad
    ok(client.post("/api/explicit/solve", json=dict(base, mode="run")))
    job = os.path.basename(rad)[:-len("_0000.rad")]
    s = wait_status(client, lambda s: not s["busy"] and any(r["job"] == job and r["status"] in ("Done", "Failed") for r in s["rows"]))
    folder = os.path.dirname(rad)
    assert not glob.glob(os.path.join(folder, "*.vtk")) and len(glob.glob(os.path.join(folder, job + "A0*"))) == 5
    res = ok(client.post("/api/explicit/results", json={"folder": folder, "job": job}))
    assert [f["name"] for f in res["frames"]][-1] == job + "A005" and res["frames"][-1]["time"] == pytest.approx(0.01)
    f = ok(client.post("/api/explicit/frame", json={"folder": folder, "job": job, "index": 4, "field": "cell|3DELEM_Strain|eps1"}))
    assert f["eroded"] == 1 and f["max"] == pytest.approx(0.015)


def test_masses_and_reference_point_on_rigid_body(client):
    """A reference point coupled to a rigid impactor (rigid shell) is a node of the rigid body: no RP_ rigid body, the
    point in the NSET RB_, velocities and supports of the point on the REF NODE (rotations held), refused with free
    rotations at an offset. Masses (/ADMAS type 5 in **RAD lines): point mass on the point (REF NODE at the centre of
    mass with it), mass per area on a face, total mass on a body and on a node set."""
    def surf(fid, name, plane, w, h):
        return {"id": fid, "name": name, "type": "surf_sketch", "kind": "planar", "plane": plane, "offset": 0,
                "sketch": {"entities": rect(w, h)}}
    ok(client.put("/api/part/file/xm_blk", json=part_rec("xm_blk", [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                                                                   "sketch": {"entities": rect(40, 40)}, "depth": 20}])))
    ok(client.put("/api/part/file/xm_tup", json={"name": "xm_tup", "version": 2, "next": 2, "features": [surf("s1", "Tup", "XY", 20, 20)]}))
    ok(client.put("/api/assembly/file/xm_asm", json={"name": "xm_asm", "next": 3, "components": [
        {"id": "1", "name": "block", "source": {"type": "part", "name": "xm_blk"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "tup", "source": {"type": "part", "name": "xm_tup"}, "pos": [10, 10, 30], "rot": [0, 0, 0]}]}))
    asm = ok(client.get("/api/assembly/file/xm_asm"))
    c = ok(client.post("/api/assembly/build", json={"assembly": asm}))["components"][0]
    bot = next(i for i, r in enumerate(c["refs"]) if r and r["kind"] == "plane" and abs(r["c"][2]) < 1e-6)
    doc = {"name": "xm1", "source": {"kind": "shinycad", "type": "assembly", "name": "xm_asm"},
           "materials": {"S355": {"library": "", "E": 210000, "nu": 0.3, "rho": 7850}}, "default_material": "S355",
           "mesh": {"size": 10}, "bonded": True, "bodies": {}, "shells": {"2:s1": {"t": 2, "mode": "rigid"}},
           "nsets": [{"id": "n2", "name": "BOTTOM", "kind": "faces", "faces": [{"comp": "1", "face": bot}]}],
           "points": [{"id": "p1", "name": "Drive", "xyz": [20, 20, 40], "coupling": "rigid", "faces": [{"comp": "2", "face": 0}]}],
           "velocities": [{"id": "v1", "name": "push", "target": {"point": "p1"}, "kind": "imposed", "v": [0, 0, -1000],
                           "w": [0, 0, 0], "dofs": [1, 1, 1, 1, 1, 1], "ramp": 0.001},
                          {"id": "v2", "name": "drop", "target": {"point": "p1"}, "kind": "initial", "v": [0, 0, -2000]}],
           "masses": [{"id": "m1", "name": "ballast", "kind": "point", "target": {"point": "p1"}, "m": 1.0},
                      {"id": "m2", "name": "coating", "kind": "distributed", "target": {"faces": [{"comp": "1", "face": bot}]}, "mode": "area", "m": 10.0},
                      {"id": "m3", "name": "contents", "kind": "distributed", "target": {"body": "1"}, "mode": "total", "m": 2.0},
                      {"id": "m4", "name": "base", "kind": "distributed", "target": {"nset": "n2"}, "mode": "total", "m": 0.5}],
           "settings": {}, "next": 5}
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xm1", "doc": doc}))["job"])
    assert j["state"] == "done", j
    s = j["result"]["summary"]
    text = open(j["result"]["inp"]).read()
    m = meshview.read_inp(j["result"]["inp"])
    pos = {int(n): m["xyz"][i] for i, n in enumerate(m["node_ids"])}
    tup = next(b for b in s["bodies"] if b["role"] == "rigid")
    rp = s["points"][0]
    assert rp["coupling"].startswith("rigid body") and "NSET=RP_" not in text
    rb = text.split("*NSET, NSET=RB_")[1].split("*")[0].split("\n", 1)[1]
    assert str(rp["node"]) in rb.replace(",", " ").split()
    m_tup = 400 * 2 * 7.85e-9
    assert pos[tup["ref_node"]][2] == pytest.approx((m_tup * 30 + 1e-3 * 40) / (m_tup + 1e-3), abs=1e-6)
    vel1 = text.split("*NSET, NSET=VEL_1_PUSH\n")[1].split("*")[0].replace(",", " ").split()
    assert vel1 == [str(tup["ref_node"])]
    vel2 = text.split("*NSET, NSET=VEL_2_DROP\n")[1].split("*")[0].replace(",", " ").split()
    assert str(tup["ref_node"]) in vel2 and str(rp["node"]) in vel2
    # /ADMAS cards
    cards = text.split("**RAD /ADMAS/5/")[1:]
    assert len(cards) == 4
    tot = [sum(float(l[6:26]) for l in cd.splitlines()[3:] if l.startswith("**RAD ") and not l.startswith("**RAD #") and len(l) > 30) for cd in cards]
    assert tot[0] == pytest.approx(1e-3) and cards[0].splitlines()[3][26:36].strip() == str(rp["node"])
    assert tot[1] == pytest.approx(1600 * 10e-9, rel=1e-6) and tot[2] == pytest.approx(2e-3, rel=1e-6) and tot[3] == pytest.approx(0.5e-3, rel=1e-6)
    assert [round(x["kg"], 6) for x in s["masses"]] == [1.0, 0.016, 2.0, 0.5]
    assert s["rigid_mass"][0]["kg"] == pytest.approx(m_tup * 1e3 + 1.0, rel=1e-6) and s["rigid_mass"][0]["added_kg"] == pytest.approx(1.0)
    assert s["rigid_mass"][0]["shell"] and s["total_kg"] == pytest.approx(40 * 40 * 20 * 7.85e-6 + m_tup * 1e3 + 3.516, rel=1e-6)
    # inp2rad and the **RAD cards: the point in the /RBODY node group, /ADMAS in the starter deck
    import shutil
    import subprocess
    import sys
    from drawgen.explicit import build as xb
    from drawgen.explicit import radcards
    work = os.path.join(os.path.dirname(j["result"]["inp"]), "rad_xm1")
    os.makedirs(work, exist_ok=True)
    inp = os.path.join(work, "xm1.inp")
    shutil.copy(j["result"]["inp"], inp)
    r = subprocess.run([sys.executable, os.path.join(xb.SCRIPT_DIR, "inp2rad_run.py"), os.path.join(xb.SCRIPT_DIR, "inp2rad.py"), inp],
                       cwd=work, input="y\n" * 500, text=True, capture_output=True, timeout=300)
    rad = glob.glob(os.path.join(work, "*_0000.rad"))
    assert rad, r.stdout[-2000:] + r.stderr[-2000:]
    deck = open(rad[0], errors="replace").read()
    if "/ADMAS/5/" not in deck:
        radcards.apply(inp, rad[0])
        deck = open(rad[0], errors="replace").read()
    assert deck.count("/ADMAS/5/") == 4 and "<X" not in deck
    rb = deck.split("/RBODY/")[1].splitlines()
    assert int(rb[3][:10]) == tup["ref_node"]
    gid = int(rb[3][60:70])
    import re as _re
    grp = _re.split(r"\n/GRNOD/NODE/%d *\n" % gid, deck)[1].split("\n#---")[0].split("\n/")[0]
    assert str(rp["node"]) in grp.split()
    # free rotations at an offset from the REF NODE: refused; support on the point with the rotations held: the REF NODE
    bad = dict(doc, velocities=[dict(doc["velocities"][0], dofs=[1, 1, 1, 0, 0, 0])])
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xm2", "doc": bad}))["job"])
    assert j["state"] == "error" and "hold rx, ry, rz" in j["error"]
    sup = dict(doc, velocities=[], supports=[{"id": "s1", "name": "hold", "target": {"point": "p1"}, "dofs": [1, 1, 1, 1, 1, 1]}])
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xm3", "doc": sup}))["job"])
    assert j["state"] == "done", j
    text = open(j["result"]["inp"]).read()
    ref = next(b for b in j["result"]["summary"]["bodies"] if b["role"] == "rigid")["ref_node"]
    assert text.split("*NSET, NSET=SUP_1_HOLD\n")[1].split("*")[0].strip() == str(ref)
    assert "SUP_1_HOLD_R, 4, 4" in text
    # a support on several items (selection target): the nodes of the bottom face and of the block body
    multi = dict(doc, velocities=[], supports=[{"id": "s2", "name": "both", "target": {"faces": [{"comp": "1", "face": bot}], "bodies": ["1"]},
                                                "dofs": [1, 1, 1, 0, 0, 0]},
                                               {"id": "s3", "name": "surf", "target": {"surface": "sf1"}, "dofs": [0, 0, 1, 0, 0, 0]}],
                 surfaces=[{"id": "sf1", "name": "BASE", "faces": [{"comp": "1", "face": bot}]}])
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xm3b", "doc": multi}))["job"])
    assert j["state"] == "done", j
    text = open(j["result"]["inp"]).read()
    held = set(int(x) for x in text.split("*NSET, NSET=SUP_1_BOTH\n")[1].split("*")[0].replace(",", " ").split())
    blk = set()
    for part in text.split("*ELEMENT, TYPE=")[1:]:
        head, body = part.split("\n", 1)
        if "ELSET=B_BLOCK" in head:
            for line in body.split("*")[0].splitlines():
                blk.update(int(x) for x in line.replace(",", " ").split()[1:])
    assert held == blk and len(blk) > 0
    # a support on a surface: the nodes of its faces (the bottom face: as the node set BOTTOM)
    nodes = lambda name: set(int(x) for x in text.split("*NSET, NSET=%s\n" % name)[1].split("*")[0].replace(",", " ").split())
    assert nodes("SUP_2_SURF") == nodes("BOTTOM")
    bad = dict(multi, surfaces=[])
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xm3c", "doc": bad}))["job"])
    assert j["state"] == "error" and "surface sf1 not found" in j["error"]
    # no mass: a rigid body of density 0 without masses; a velocity on a free reference point without a point mass
    norho = dict(doc, materials={"S355": {"library": "", "E": 210000, "nu": 0.3, "rho": 0}}, masses=[], velocities=[])
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xm5", "doc": norho}))["job"])
    assert j["state"] == "error" and "rigid body" in j["error"] and "has no mass" in j["error"]
    free = dict(doc, points=[{"id": "p2", "name": "Free", "xyz": [0, 0, 60], "coupling": "none"}], masses=[],
                velocities=[{"id": "v9", "name": "go", "target": {"point": "p2"}, "kind": "initial", "v": [0, 0, -1]}])
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xm6", "doc": free}))["job"])
    assert j["state"] == "error" and "reference point Free, which has no mass and no coupling" in j["error"]
    free["masses"] = [{"id": "m8", "name": "pm", "kind": "point", "target": {"point": "p2"}, "m": 5}]
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xm7", "doc": free}))["job"])
    assert j["state"] == "done", j
    # the tup surface body meshed in a rigid section: a mass and a velocity on the surface body act on the section
    insec = dict(doc, shells={}, points=[], sections=[{"id": "q1", "name": "IMPACTOR", "mode": "rigid", "t": 2,
                                                         "faces": [{"comp": "2", "face": 0}]}],
                 masses=[{"id": "m9", "name": "tupmass", "kind": "distributed", "target": {"body": "2:s1"}, "mode": "total", "m": 3.0}],
                 velocities=[{"id": "v8", "name": "drop", "target": {"body": "2:s1"}, "kind": "imposed", "v": [0, 0, -1000],
                              "w": [0, 0, 0], "dofs": [1, 1, 1, 1, 1, 1], "ramp": 0.001}])
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xm8", "doc": insec}))["job"])
    assert j["state"] == "done", j
    s = j["result"]["summary"]
    text = open(j["result"]["inp"]).read()
    ref = next(b for b in s["bodies"] if b["role"] == "rigid")["ref_node"]
    assert text.split("*NSET, NSET=VEL_1_DROP\n")[1].split("*")[0].strip() == str(ref)
    assert s["rigid_mass"][0]["added_kg"] == pytest.approx(3.0) and [round(x["kg"], 6) for x in s["masses"]] == [3.0]
    nomass = dict(doc, masses=[{"id": "m9", "name": "zero", "kind": "point", "target": {"point": "p1"}, "m": 0}])
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xm4", "doc": nomass}))["job"])
    assert j["state"] == "error" and "greater than 0" in j["error"]


@pytest.mark.skipif(os.name == "nt", reason="shell script stand-in for pvbatch")
def test_post_steps_status_notes_and_strain_timeout(tmp_path):
    """Post-processing steps in the status note; a pvbatch that does not return is stopped after STRAIN_TIMEOUT."""
    pvb = tmp_path / "pvbatch"
    pvb.write_text("#!/bin/sh\nsleep 30\n")
    pvb.chmod(0o755)
    w = host.Workspace()
    w.pvbatch_path.set(str(pvb))
    w.extract_strains.set(True)
    w.pv_images.set(False)
    w.plot_ke.set(False)
    notes = []
    orig = w._status_touch
    w._status_touch = lambda job, **kw: (notes.append(kw.get("note")), orig(job, **kw))
    w.STRAIN_TIMEOUT = 1
    t0 = time.time()
    w._post_steps(str(tmp_path), "jt")
    assert time.time() - t0 < 20
    assert notes == ["KE plot", "ParaView files", "Extract Strains, pvbatch", "PV Images, pvbatch", ""]
    assert any("did not finish in 1 s" in l for _n, l in w.logs)


# --------------------------------------------------------------------------- initial state from a static solve

def _ccx():
    from drawgen import analysis
    return analysis.find_ccx(os.environ.get("DRAWGEN_CCX", ""))


def _plane_face(refs, axis, value):
    return next(i for i, r in enumerate(refs) if r and r["kind"] == "plane" and abs(r["c"][axis] - value) < 1e-6
                and abs(abs(r["n"][axis]) - 1) < 1e-6)


@pytest.mark.skipif(_ccx() is None, reason="CalculiX (ccx) not found")
def test_initial_state_static_solve_and_deck(client, tmp_path):
    """A block 40 x 40 x 20 mm (C3D4) under 10 MPa on the top face with symmetry supports, and a shell cantilever
    100 x 20 mm, t 2 mm (S4R, static S4) with 10 N at the tip, solved on the mesh of the Explicit model: uniaxial
    stress -10 MPa and the top displacement -10 * 20 / E of the block; shell stress at T = -1 and 1 opposite, about
    6 M / (b t^2) at the root, 0 at T = 0; the deck: /NODE moved by the displacements, /INIBRI/STRS_FGLO and
    /INISHE/STRS_F/GLOB before /END in the fixed field widths; the state refused for a newer .inp."""
    from drawgen import web
    from drawgen.explicit import initstate
    ok(client.put("/api/part/file/is_blk", json=part_rec("is_blk", [{"id": "f1", "name": "Extrude 1", "type": "extrude", "plane": "XY", "offset": 0,
                                                                   "sketch": {"entities": rect(40, 40)}, "depth": 20}])))
    ok(client.put("/api/part/file/is_sh", json={"name": "is_sh", "version": 2, "next": 2, "features": [
        {"id": "s1", "name": "Plate", "type": "surf_sketch", "kind": "planar", "plane": "XY", "offset": 0, "sketch": {"entities": rect(100, 20)}}]}))
    ok(client.put("/api/assembly/file/is_asm", json={"name": "is_asm", "next": 3, "components": [
        {"id": "1", "name": "block", "source": {"type": "part", "name": "is_blk"}, "pos": [0, 0, 0], "rot": [0, 0, 0]},
        {"id": "2", "name": "plate", "source": {"type": "part", "name": "is_sh"}, "pos": [0, 100, 0], "rot": [0, 0, 0]}]}))
    asm = ok(client.get("/api/assembly/file/is_asm"))
    cs = ok(client.post("/api/assembly/build", json={"assembly": asm}))["components"]
    blk, sh = cs[0], cs[1]
    top, bot = _plane_face(blk["refs"], 2, 20.0), _plane_face(blk["refs"], 2, 0.0)
    x0, y0 = _plane_face(blk["refs"], 0, 0.0), _plane_face(blk["refs"], 1, 0.0)
    e0 = next(i for i, r in enumerate(sh["erefs"]) if r and r["kind"] == "line" and abs(r["c"][0]) < 1e-6)
    e1 = next(i for i, r in enumerate(sh["erefs"]) if r and r["kind"] == "line" and abs(r["c"][0] - 100) < 1e-6)
    xdoc = {"name": "is1", "source": {"kind": "shinycad", "type": "assembly", "name": "is_asm"},
            "materials": {"S": {"library": "", "E": 210000, "nu": 0.3, "rho": 7850}}, "default_material": "S",
            "mesh": {"size": 5, "tet_type": "C3D4", "shell_type": "S4R"}, "bonded": False, "bodies": {},
            "shells": {"2:s1": {"t": 2}}, "settings": {}, "next": 1}
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "is1", "doc": xdoc}))["job"])
    assert j["state"] == "done", j
    inp = j["result"]["inp"]
    adoc = {"name": "pre", "supports": [{"id": "a", "name": "zs", "target": {"comp": "1", "face": bot}, "type": "dofs", "dofs": [0, 0, 1]},
                                        {"id": "b", "name": "xs", "target": {"comp": "1", "face": x0}, "type": "dofs", "dofs": [1, 0, 0]},
                                        {"id": "c", "name": "ys", "target": {"comp": "1", "face": y0}, "type": "dofs", "dofs": [0, 1, 0]},
                                        {"id": "d", "name": "root", "target": {"comp": "2", "edge": e0}, "type": "fixed"}],
            "loads": [{"id": "p", "name": "p", "type": "pressure", "target": {"comp": "1", "face": top}, "value": 10.0},
                      {"id": "l", "name": "tip", "type": "line", "target": {"comp": "2", "edge": e1}, "value": [0, 0, -0.5]}],
            "members": [{"id": "m"}]}
    sx = initstate.solve(xdoc, adoc, web._fea_asm(xdoc), web._asm_sources(), inp, str(tmp_path / "st"), _ccx())
    assert sx["solids"] > 100 and sx["shells"] == 80 and any("members" in w for w in sx["warnings"])
    st = initstate.load(inp)
    s = np.array([v["s"] for v in st["solids"].values()])
    assert np.allclose(s[:, 2], -10.0, atol=0.2) and np.abs(s[:, [0, 1, 3, 4, 5]]).max() < 0.2
    m = meshview.read_inp(inp)
    ids = list(m["node_ids"])
    topn = [n for i, n in enumerate(ids) if abs(m["xyz"][i][2] - 20) < 1e-6 and abs(m["xyz"][i][1]) < 40.001]
    assert topn and all(st["disp"][str(n)][2] == pytest.approx(-10 * 20 / 210000.0, rel=0.02) for n in topn)
    root = [v for v in st["shells"].values()]
    lo = max(abs(v["s"][0][0]) for v in root)
    assert lo == pytest.approx(6 * 10.0 * 97.5 / (20 * 4), rel=0.15)
    k = max(st["shells"], key=lambda e: abs(st["shells"][e]["s"][0][0]))
    v = st["shells"][k]["s"]
    assert v[0][0] * v[4][0] < 0 and abs(v[2][0]) < 0.02 * abs(v[0][0]) and v[1][0] == pytest.approx(0.5 * v[0][0], rel=0.01)
    # deck
    deck = ["/BEGIN\n", "/NODE\n"] + ["%10d%20.12g%20.12g%20.12g\n" % (n, *m["xyz"][i]) for i, n in enumerate(ids)] + ["/END\n"]
    out, cnt = initstate.apply(deck, st)
    assert cnt["nodes"] == len(st["disp"]) and out[-1] == "/END\n"
    n0 = topn[0]
    line = next(l for l in out[2:2 + len(ids)] if int(l[:10]) == n0)
    assert float(line[50:70]) == pytest.approx(20 - 10 * 20 / 210000.0, rel=1e-6)
    text = "".join(out)
    assert text.index("/INIBRI/STRS_FGLO") < text.index("/INISHE/STRS_F/GLOB") < text.index("/END")
    blk_lines = text.split("/INIBRI/STRS_FGLO\n")[1].split("/INISHE")[0].splitlines()
    data = [l for l in blk_lines if not l.startswith("#")]
    assert len(data) % 5 == 0 and len(data[0]) == 90 and int(data[0][10:20]) == 1 and int(data[0][20:30]) == 4
    assert len(data[1]) == 40 and len(data[2]) == 60 and float(data[2][40:60]) == pytest.approx(-10, abs=0.2) and len(data[4]) == 20
    sh_lines = [l for l in text.split("/INISHE/STRS_F/GLOB\n")[1].split("/END")[0].splitlines() if not l.startswith("#")]
    assert len(sh_lines) % 12 == 0 and len(sh_lines[0]) == 50 and int(sh_lines[0][10:20]) == 5 and float(sh_lines[0][30:50]) == 2
    assert len(sh_lines[2]) == 60 and len(sh_lines[3]) == 100 and float(sh_lines[3][80:100]) == -1 and float(sh_lines[11][80:100]) == 1
    # build step: Use in Build on
    w = host.Workspace()
    w.init_state.set(True)
    w.init_peeq.set(False)
    lines = w._gen_initial_state(deck, inp)
    assert lines is not None and "".join(lines) == text
    w.init_geometry.set(False)
    g = w._gen_initial_state(deck, inp)
    assert g[2:2 + len(ids)] == deck[2:2 + len(ids)] and "/INIBRI/STRS_FGLO" in "".join(g)
    # routes: the Analysis document saved, the solve as a job, the status
    ok(client.put("/api/analysis/file/pre", json=dict(adoc, source={"type": "assembly", "name": "is_asm"})))
    xdoc["initial_state"] = {"analysis": "pre", "materials": "elastic"}
    j = wait_job(client, ok(client.post("/api/explicit/initial_state", json={"name": "is1", "doc": xdoc}))["job"])
    assert j["state"] == "done" and j["result"]["shells"] == 80, j
    stt = ok(client.get("/api/explicit/initial_state?name=is1"))["state"]
    assert stt["summary"]["analysis"] == "pre" and stt["summary"]["umax"] > 0
    # a newer .inp
    with open(inp, "a") as f:
        f.write("** changed\n")
    with pytest.raises(initstate.InitError, match="older model .inp"):
        initstate.load(inp)
    assert ok(client.get("/api/explicit/initial_state?name=is1"))["state"] == {"stale": True}
    assert w._gen_initial_state(deck, inp) is None and any("BUILD HALTED: initial state" in l for _n, l in w.logs)


def test_tool_substitute_module_without_cadquery(tmp_path):
    """A repo script that imports deck_stepgen (cadquery) starts with the build123d deck_stepgen of ShinyCAD when the
    needed module is not installed; the arguments reach the script; with the module present the plain command."""
    import subprocess
    import sys
    from drawgen.explicit import launcher
    d = tmp_path / "DECK_GENERATOR"
    d.mkdir()
    (d / "deck_stepgen.py").write_text("raise ImportError('No module named cadquery')\n")
    (d / "gui.py").write_text("import sys\nfrom deck_stepgen import Beam, deck_model, build\nimport deck_stepgen\n"
                              "print(deck_stepgen.__file__.replace(chr(92), '/'), sys.argv[1:], __file__ == sys.argv[0])\n"
                              "print(len(deck_model(1000, 500, [Beam('S', 'x', 250, 100)])))\n")
    tool = {"key": "t", "title": "T", "substitute": {"needs": "no_such_module_xyz", "modules": launcher.SUBSTITUTE_STEPGEN["modules"]}}
    cmd = launcher.command(tool, str(d / "gui.py"), ["a b"])
    assert cmd[1] == "-c"
    r = subprocess.run(cmd, cwd=str(d), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    first, second = r.stdout.strip().splitlines()
    assert first.split()[0].endswith("drawgen/explicit/deck_stepgen.py") and "['a b']" in first and first.endswith("True")
    assert int(second) == 2
    tool["substitute"]["needs"] = "json"
    assert launcher.command(tool, "x.py", ["1"]) == [sys.executable, "x.py", "1"]
    gui = next(t for t in launcher.TOOLS if t["key"] == "deck_gui")
    assert gui["substitute"]["needs"] == "cadquery"


def test_deck_view_flanges_claim_the_deck():
    """Model view of the deck generator: a top flange cuts the deck plate (the region belongs to the later part, as in
    the STEP fuse and the mesh); the z = 0 area of the view equals the panel area, other parts keep their area."""
    from drawgen.explicit import deck
    c = deck.check({})

    def area(polys):
        return sum(0.5 * np.linalg.norm(np.cross(np.subtract(P[2], P[0]), np.subtract(P[3], P[1]))) for P in polys)
    view = {v["name"]: v["polys"] for v in c["view"]}
    raw = {p["name"]: p["polys"] for p in c["parts"]}
    z0 = sum(area([P for P in pl if all(abs(q[2]) < 1e-9 for q in P)]) for pl in view.values())
    assert z0 == pytest.approx(6000 * 4000)
    cross = 2 * 3 * 250 * 120                       # beam flange under the deeper girder flanges: 2 girders x 3 beams
    assert area(view["BEAM_FLANGE"]) == pytest.approx(area(raw["BEAM_FLANGE"]) - cross)
    assert area(view["DECK"]) == pytest.approx(6000 * 4000 - area(raw["GIRDER_FLANGE"]) - area(raw["BEAM_FLANGE"]) + cross)


def test_inp_source_model(client, tmp_path):
    """Explicit model of a CalculiX .inp source (editable model): the elements of the file in B_ element sets, the
    *NSET FIX of the file as a support node set, the strip (shell section of the tab, t 2 mm) as a rigid body with a
    reference node at its centre of mass, an initial velocity on the bar; total mass from the volume and area."""
    from test_analysis import write_test_inp
    from drawgen import inpmodel
    p = write_test_inp(str(tmp_path / "t.inp"))
    v = inpmodel.view(p)
    doc = {"name": "xinp", "source": {"kind": "shinycad", "type": "inp", "path": p, "name": "t.inp"},
           "materials": {"STEEL": {"library": "", "E": 210000, "nu": 0.3, "rho": 7850}}, "default_material": "STEEL",
           "mesh": {}, "bonded": True, "bodies": {"BEAM": {"role": "deformable", "material": "STEEL"}},
           "shells": v["shells"],
           "sections": [{"id": "s1", "name": "PLATE", "faces": [{"comp": "PLATE", "face": 0}], "t": 2.0, "material": "STEEL", "mode": "rigid"}],
           "nsets": [{"id": "n1", "name": "FIX", "kind": "inp", "set": "FIX"}],
           "supports": [{"id": "s1", "name": "fix", "target": {"nset": "n1"}, "dofs": [1, 1, 1, 1, 1, 1]}],
           "velocities": [{"id": "v1", "name": "hit", "target": {"body": "BEAM"}, "kind": "initial", "v": [0, 0, -1000]}],
           "settings": {}, "next": 3}
    j = wait_job(client, ok(client.post("/api/explicit/model", json={"name": "xinp", "doc": doc}))["job"])
    assert j["state"] == "done", j
    s = j["result"]["summary"]
    text = open(j["result"]["inp"]).read()
    m = meshview.read_inp(j["result"]["inp"])
    assert len(m["node_ids"]) >= 132
    fix = text.split("*NSET, NSET=FIX\n")[1].split("*")[0].replace(",", " ").split()
    assert sorted(int(x) for x in fix) == sorted(int(x) for x in "1 12 23 34 45 56 67 78 89".split())
    rb = next(b for b in s["bodies"] if b["role"] == "rigid")
    pos = {int(n): m["xyz"][i] for i, n in enumerate(m["node_ids"])}
    assert np.allclose(pos[rb["ref_node"]], [50, 5, 20], atol=1e-6)
    assert s["total_kg"] == pytest.approx((100 * 10 * 10 + 100 * 10 * 2) * 7.85e-6, rel=1e-6)


def test_time_history_requests(client, xp_doc, tmp_path):
    """History output of the document in the explicit model: a node request on a supported face (displacement,
    velocity, reaction force) and a part request on both bodies (internal and kinetic energy) as /TH/NODE and /TH/PART
    cards (**RAD lines; node names H1N<node>, the parts by their titles); after the build the cards in the starter deck
    with the part numbers; after the run (fake th_to_csv: DZ -k, VZ -1000, REACZ 10 k per node, IE 5 k, KE 100 - 5 k
    per part at row k) the curves of the requests in the results: uz mean, RFz total (10 k x the node count), the
    energies of the two parts; the columns by position for a CSV without names; the run monitor of the job (the cycle
    lines of the engine output); probes of a point field and a cell field over the frames."""
    exe = fake_opencourant.install(str(tmp_path / "exec"))
    ok(client.put("/api/explicit/env", json={"or_exec": exe, "ssh_threads": "2", "run_target": host.LOCAL}))
    doc = dict(xp_doc, history=[
        {"id": "h1", "name": "edge", "kind": "node", "target": xp_doc["supports"][0]["target"], "quantities": ["U", "V", "RF"]},
        {"id": "h2", "name": "bodies", "kind": "element", "target": {"bodies": ["1", "2"]}, "quantities": ["ENER", "EKIN", "S"]},
        {"id": "h3", "name": "contact", "kind": "contact", "target": None, "quantities": ["CF"]},
        {"id": "h4", "name": "cut", "kind": "section", "target": {"faces": [xp_doc["supports"][0]["target"]]}, "quantities": ["SOF"]}])
    base = {"name": "xp_th1", "doc": doc, "settings": dict(xp_doc["settings"])}
    j = wait_job(client, ok(client.post("/api/explicit/model", json=base))["job"])
    assert j["state"] == "done", j
    h = j["result"]["summary"]["history"]
    assert [x["vars"] for x in h][:2] == [["DX", "DY", "DZ", "VX", "VY", "VZ", "REACX", "REACY", "REACZ"], ["IE", "KE"]]
    assert h[2]["vars"] == ["FNX", "FNY", "FNZ", "FTX", "FTY", "FTZ"] and h[3]["n"] > 0
    assert h[1]["left_out"] == ["S"] and h[1]["n"] == 2
    n_nodes = h[0]["n"]
    text = open(j["result"]["inp"]).read()
    assert "**RAD /TH/NODE/<X" in text and "**RAD SC_H1/h1/node/edge" in text and "<P:B_TARGET>" in text
    assert "**RAD /TH/INTER/<X" in text and "**RAD /SECT/<X" in text and "**RAD /GRBRIC/BRIC/<X" in text and "**RAD /TH/SECTIO/<X" in text
    r = ok(client.post("/api/explicit/run/new", json=dict(base, description="th")))
    base["settings"]["out_dir"] = r["run"]
    ok(client.post("/api/explicit/build", json=base))
    s = wait_status(client, lambda s: not s["building"] and s["last_build"] and s["last_build"]["dir"].startswith(r["run"]))
    rad = s["last_build"]["rad"]
    deck = open(rad).read()
    tail = deck.split("# SHINYCAD constraints")[1]
    assert "<P:" not in tail and "/TH/PART/" in tail and "H1N" in tail
    from drawgen.explicit import radcards, thist
    pids = radcards.part_ids(deck)
    gs = thist.groups(deck)
    assert [g["type"] for g in gs] == ["NODE", "PART", "INTER", "SECTIO"] and gs[1]["objs"] == [pids["B_TARGET"], pids["B_IMPACTOR"]]
    assert gs[2]["objs"] == [9999999] and gs[2]["titles"][9999999] == "GENERAL_SELF_CONTACT" and len(gs[3]["objs"]) == 1
    sect = tail.split("/SECT/")[1].splitlines()
    assert sect[0].strip() == str(gs[3]["objs"][0]) and sect[3][:10].strip().isdigit() and sect[6].rstrip().endswith("11")
    assert len(gs[0]["objs"]) == n_nodes
    base["settings"]["rad_target"] = rad
    ok(client.post("/api/explicit/solve", json=dict(base, mode="run")))
    job = os.path.basename(rad)[:-len("_0000.rad")]
    wait_status(client, lambda s: not s["busy"] and any(r["job"] == job and r["status"] in ("Done", "Failed") for r in s["rows"]))
    folder = os.path.dirname(rad)
    mon = ok(client.get("/api/explicit/monitor?job=" + job))          # run monitor: the 5 cycle lines of the fake engine
    assert mon["nc"] == [100, 200, 300, 400, 500] and mon["err"][2] == pytest.approx(-0.3) and mon["dmm"][4] == pytest.approx(5e-4)
    res = ok(client.post("/api/explicit/results", json={"folder": folder, "job": job}))
    th = {q["id"]: {x["name"]: x for x in q["series"]} for q in res["time_history"]}
    assert "th_note" not in res, res.get("th_note")
    assert th["h1"]["uz mean"]["v"] == pytest.approx([0, -1, -2, -3, -4]) and th["h1"]["|v| max"]["v"][2] == pytest.approx(1000)
    assert th["h1"]["RFz total"]["v"][3] == pytest.approx(30 * n_nodes)
    assert th["h2"]["internal energy"]["v"][2] == pytest.approx(20) and th["h2"]["kinetic energy"]["v"][0] == pytest.approx(200)
    assert th["h3"]["Fz total"]["v"] == pytest.approx([0, 7, 14, 21, 28]) and th["h3"]["Fx total"]["v"][1] == pytest.approx(2)
    assert th["h4"]["Fz total"]["v"][4] == pytest.approx(28) and th["h4"]["My"]["v"][2] == pytest.approx(6)
    # probe: the z displacement of the centre point of the fake grid (-0.5 (k - 1) at frame k) and the von Mises
    # stress of cell 3 (10 k + 3) over the frames
    g = ok(client.post("/api/explicit/geometry", json={"folder": folder, "job": job}))
    keys = [f["key"] for f in g["fields"]]
    vmk = next(k for k in keys if "Von_Mises" in k)
    pr = ok(client.post("/api/explicit/probe", json={"folder": folder, "job": job, "field": "point|Displacement|2", "probes": [{"point": 12, "cell": 0}]}))
    assert pr["loc"] == "point" and pr["values"][0] == pytest.approx([0, -0.5, -1, -1.5, -2]) and len(pr["time"]) == 5
    pr = ok(client.post("/api/explicit/probe", json={"folder": folder, "job": job, "field": vmk, "probes": [{"point": 0, "cell": 3}]}))
    assert pr["loc"] == "cell" and pr["values"][0] == pytest.approx([13, 23, 33, 43, 53])
    assert "node_ids" in g["payload"]
    # a CSV without names: by position
    csv = os.path.join(folder, job + "_Results.csv")
    L = open(csv).read().splitlines()
    n = len(L[1].split(","))
    open(csv, "w").write(",".join(['"time"'] + ['"var %d"' % i for i in range(1, n)]) + "\n" + "\n".join(L[1:]) + "\n")
    t2 = thist.series(folder, job)
    assert "by position" in t2["note"]
    th2 = {q["id"]: {x["name"]: x for x in q["series"]} for q in t2["time_history"]}
    assert th2["h1"]["RFz total"]["v"] == th["h1"]["RFz total"]["v"] and th2["h2"]["kinetic energy"]["v"] == th["h2"]["kinetic energy"]["v"]
    assert th2["h4"]["My"]["v"] == th["h4"]["My"]["v"]
