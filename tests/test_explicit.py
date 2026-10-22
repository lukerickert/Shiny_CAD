# -*- coding: utf-8 -*-
"""Explicit tab (drawgen/explicit, ORC**3 core): mesh view data and readers, the model .inp of the ShinyCAD geometry,
the deck build (inp2rad and the cards of the settings), run folders, the local solve with a stand-in for the
OpenCourant executables (fake_openradioss.py), results, post-processing, the Explicit document in the project."""
import base64
import glob
import json
import os
import time

import numpy as np
import pytest

from conftest import part_rec, rect

import fake_openradioss
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


def wait_status(c, cond, timeout=120):
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
    a.write_text("fake animation 3 0.005\n")
    import subprocess
    import sys
    out = subprocess.run([sys.executable, fake_openradioss.__file__, "anim_to_vtk", str(a)], capture_output=True, text=True).stdout
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
    # ORC**3 run.json snapshot with three slots
    w.apply({"mat1": "Steel S355 (DNVGL 19-Point Standard)", "mat1_name": "S355", "mat2": "None (Use PrePoMax Data)",
             "mat2_name": "MAT2", "gravity": "false", "tstop": 0.02, "unknown": 1})
    assert w.mat_slots[0] == ["Steel S355 (DNVGL 19-Point Standard)", "S355"] and w.gravity.get() is False and w.tstop.get() == "0.02"
    assert [(a.get(), b.get()) for a, b in w._mat_slots()][0] == ("Steel S355 (DNVGL 19-Point Standard)", "S355")
    suffix = "_win64" if os.name == "nt" else "_linux64_gf"
    assert w._or_exe("starter") == "starter" + suffix and w._or_env() is None
    d = fake_openradioss.install(str(tmp_path / "exec"))
    (tmp_path / "hm_cfg_files").mkdir()
    w.or_exec.set(d)
    assert os.path.isfile(w._or_exe("engine"))
    env = w._or_env()
    assert env["PATH"].startswith(d) and env["RAD_CFG_PATH"] == str(tmp_path / "hm_cfg_files") and env["KMP_STACKSIZE"]
    # remote helpers (ORC**3)
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
    exe = fake_openradioss.install(str(tmp_path / "exec"))
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
    p = ok(client.get("/api/part/file/xp_deck1_deck"))
    assert [f["type"] for f in p["features"]] == ["surf_import"] * 8 and p["features"][0]["label"] == "DECK"
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
