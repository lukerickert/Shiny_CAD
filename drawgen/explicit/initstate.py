"""Initial state of an explicit run from a static solve (CalculiX) on the mesh of the Explicit model.

The static solve (solve) uses the mesh of the last Mesh of the Explicit model (model/<name>_mesh.json.gz, the node
and element numbers of model/<name>.inp), the bodies, shells, sections and materials of the Explicit document
(rigid bodies left out) and the supports, loads, fasteners, reference points, springs, joints, equations, contacts,
node sets and nonlinear step settings of an Analysis document. Element types of the static solve: S4R -> S4,
C3D8R -> C3D8I (same nodes); the others as in the Explicit model. Materials: "elastic" (E, nu, rho of the material or
of its library entry) or "explicit" (the library hardening curve: nonlinear step, plastic strain).

The result (model/<name>_initial.json.gz) holds the node displacements, per solid element the mean stress of its
integration points and the plastic strain, per shell element the stress at 5 points through the thickness (linear
through the two integration point layers of the expanded element) and the plastic strain. The build (apply) moves the
/NODE coordinates by the displacements and writes /INIBRI/STRS_FGLO (solids, 1 integration point: 8-node bricks
Isolid 1, 4-node tetrahedra Isolid 0) and /INISHE/STRS_F/GLOB, /INISH3/STRS_F/GLOB (shells: 5 points through the
thickness at T = -1, -0.5, 0, 0.5, 1, 1 surface point) into the starter deck (formats of the OpenRadioss hm_cfg_files
radioss2021 TABLE inibri_strs_fglo_sub.cfg and inishe_strs_f_glob_sub.cfg). Units: mm, t, s (stress MPa, density
t/mm^3, energy mJ).
"""
import gzip
import json
import os
import time

import numpy as np

from .constants import MATERIAL_LIBRARY
from . import model_inp

STATIC_TYPE = {"S4R": "S4", "C3D8R": "C3D8I"}
SOLID_NODES = {"C3D8R": 8, "C3D8": 8, "C3D8I": 8, "C3D4": 4}
SHELL_TYPES = ("S4R", "S4", "S3")
T_POINTS = (-1.0, -0.5, 0.0, 0.5, 1.0)
GAUSS = 1.0 / np.sqrt(3.0)
ANALYSIS_KEYS = ("supports", "loads", "fasteners", "points", "springs", "joints", "equations", "contacts", "nsets",
                 "nonlinear", "nlgeom")


class InitError(ValueError):
    pass


def result_path(inp_path):
    return os.path.splitext(inp_path)[0] + "_initial.json.gz"


def _material(m, mode):
    """Analysis material of an Explicit material (rho kg/m^3)."""
    lib = (m or {}).get("library") or ""
    e = MATERIAL_LIBRARY.get(lib) if lib else None
    if e:
        out = {"E": float(e["E"]), "nu": float(e["nu"]), "rho": float(e["rho"]) * 1e12}
        if mode == "explicit":
            out["library"] = lib
        return out
    return {"E": float(m["E"]), "nu": float(m["nu"]), "rho": float(m["rho"])}


def static_doc(xdoc, adoc, mode="elastic"):
    """Analysis document of the static solve: the bodies and materials of the Explicit document, the loading of the
    Analysis document. Returns (doc, warnings)."""
    warn = []
    bodies = {}
    for cid, b in (xdoc.get("bodies") or {}).items():
        role = b.get("role") or "deformable"
        bodies[cid] = {"mode": "solid" if role == "deformable" else "off", "material": b.get("material"),
                       "strategy": b.get("strategy"), "size": b.get("size")}
    shells = {}
    for k, b in (xdoc.get("shells") or {}).items():
        shells[k] = dict(b, mode="off" if b.get("mode") in ("rigid", "off") else "shell")
    sections = [dict(x, mode="off" if x.get("mode") in ("rigid", "off") else "shell") for x in xdoc.get("sections") or []]
    mats = {}
    for n, m in (xdoc.get("materials") or {}).items():
        try:
            mats[n] = _material(m, mode)
        except (KeyError, TypeError, ValueError):
            raise InitError("material %s: E, nu and rho are required" % n)
    d = {"name": (adoc.get("name") or "static") + "_initial", "source": xdoc.get("source"), "materials": mats,
         "default_material": xdoc.get("default_material"), "bodies": bodies, "shells": shells, "sections": sections,
         "bonded": xdoc.get("bonded", True), "analysis_type": "static", "ip_output": True,
         "members": [], "plates": [], "mesh": dict(xdoc.get("mesh") or {})}
    for k in ANALYSIS_KEYS:
        if adoc.get(k) is not None:
            d[k] = adoc[k]
    for k, what in (("members", "members"), ("plates", "plates")):
        if adoc.get(k):
            warn.append("%d %s of the analysis left out (not in the Explicit model)" % (len(adoc[k]), what))
    if adoc.get("fasteners"):
        warn.append("%d fastener(s) of the analysis are in the static solve only (the Explicit model has no fasteners)"
                    % len(adoc["fasteners"]))
    if (adoc.get("analysis_type") or "static") != "static":
        warn.append("analysis type %s of the analysis: the static solve is static" % adoc.get("analysis_type"))
    return d, warn


def static_mesh(mesh, roles):
    """The Explicit mesh for the static solve: deformable bodies only, static element types."""
    out = {"nodes": mesh["nodes"], "bodies": {}, "warnings": []}
    for bid, mb in mesh["bodies"].items():
        if roles.get(bid, "deformable") != "deformable":
            continue
        blocks = [dict(bl, type=STATIC_TYPE.get(bl["type"], bl["type"])) for bl in mb["blocks"]]
        out["bodies"][bid] = dict(mb, blocks=blocks)
    return out


def _compliance(E, nu):
    G = E / (2 * (1 + nu))
    C = np.zeros((6, 6))
    C[:3, :3] = -nu / E
    np.fill_diagonal(C[:3, :3], 1.0 / E)
    C[3, 3] = C[4, 4] = C[5, 5] = 1.0 / G
    return C


def _energy(s6, C):
    """Elastic strain energy density 0.5 s : C : s (s in the order xx yy zz xy yz zx)."""
    s = np.asarray(s6, float)
    return 0.5 * float(s @ C @ s)


def _area(P):
    if len(P) == 3:
        return 0.5 * float(np.linalg.norm(np.cross(P[1] - P[0], P[2] - P[0])))
    return 0.5 * float(np.linalg.norm(np.cross(P[2] - P[0], P[3] - P[1])))


def _rows_by_elem(dat_step, kind):
    out = {}
    for (k, _set), rows in dat_step.items():
        if k != kind:
            continue
        for e, ip, v in rows:
            out.setdefault(e, {})[ip] = v
    return out


def solve(xdoc, adoc, asm, sources, inp_path, workdir, ccx, mode="elastic", progress=None):
    """Static solve on the mesh of the last Mesh of the Explicit model; writes <stem>_initial.json.gz. Returns the
    summary."""
    from .. import analysis
    say = progress or (lambda *a: None)
    if mode not in ("elastic", "explicit"):
        raise InitError("materials: elastic or explicit")
    try:
        saved = model_inp.load_mesh(inp_path)
    except model_inp.ModelError as e:
        raise InitError(str(e))
    sdoc, warn = static_doc(xdoc, adoc, mode)
    smesh = static_mesh(saved["mesh"], saved.get("roles") or {})
    if not smesh["bodies"]:
        raise InitError("the Explicit model has no deformable bodies")
    say("static", "Static solve on the Explicit mesh")
    try:
        r = analysis.run(sdoc, asm, sources, workdir, ccx, progress=progress, meta={"name": sdoc["name"]}, mesh=smesh,
                         keep=True)
    except analysis.AnalysisError as e:
        raise InitError("static solve: %s" % e)
    M = r["model"]
    frd = r["frd"] or {}
    last = frd[max(frd)] if frd else {}
    U = last.get("DISP") or {}
    dat = analysis.read_dat(r["files"]["dat"])
    dstep = dat[max(dat)] if dat else {}
    S = _rows_by_elem(dstep, "stresses")
    PE = _rows_by_elem(dstep, "peeq")
    X = M.X
    out_solid, out_shell = {}, {}
    mats = sdoc["materials"]
    xmats = xdoc.get("materials") or {}
    for bid, mb in saved["mesh"]["bodies"].items():
        if bid not in smesh["bodies"]:
            continue
        b = M.bodies[bid]
        mname = b.get("material") or sdoc.get("default_material")
        if mname not in mats:
            raise InitError("body %s: material %s is not defined" % (b["name"], mname))
        mv = mats[mname]
        C = _compliance(float(mv["E"]), float(mv["nu"]))
        rho = model_inp.material_values(xdoc, mname)[2] if mname in xmats else float(mv["rho"]) * 1e-12
        for bl in mb["blocks"]:
            typ = bl["type"]
            for e in bl["elements"]:
                eid = e[0]
                ips = S.get(eid)
                if not ips:
                    continue
                keys = sorted(ips)
                vals = np.asarray([ips[k] for k in keys], float)          # xx yy zz xy xz yz (CalculiX)
                vals = vals[:, [0, 1, 2, 3, 5, 4]]                         # -> xx yy zz xy yz zx
                pe = np.asarray([PE.get(eid, {}).get(k, [0.0])[0] for k in keys], float)
                if typ in SOLID_NODES:
                    s6 = vals.mean(axis=0)
                    out_solid[eid] = {"nn": SOLID_NODES[typ], "s": [round(float(v), 9) for v in s6],
                                      "pe": float(pe.mean()), "rho": rho, "e": _energy(s6, C)}
                elif typ in SHELL_TYPES:
                    n = len(keys)
                    lo, hi = vals[:n // 2].mean(axis=0), vals[n // 2:].mean(axis=0)
                    plo, phi = pe[:n // 2].mean(), pe[n // 2:].mean()
                    m_, g = 0.5 * (lo + hi), (hi - lo) / (2 * GAUSS)
                    mp, gp = 0.5 * (plo + phi), (phi - plo) / (2 * GAUSS)
                    pts = [m_ + t * g for t in T_POINTS]
                    t = float(b.get("t") or 10.0)
                    A = _area([np.asarray(X[nid], float) for nid in e[1:1 + (3 if typ == "S3" else 4)]])
                    u = [_energy(p, C) for p in pts]
                    w = [0.125, 0.25, 0.25, 0.25, 0.125]                   # trapezoid over T in [-1, 1], times 1/2
                    etot = A * t * sum(wi * ui for wi, ui in zip(w, u))
                    em = A * t * _energy(m_, C)
                    out_shell[eid] = {"t": t, "tri": typ == "S3", "s": [[round(float(v), 9) for v in p] for p in pts],
                                      "pe": [max(0.0, float(mp + tt * gp)) for tt in T_POINTS], "em": em, "eb": max(0.0, etot - em)}
    disp = {}
    for nid in saved["mesh"]["nodes"]["ids"]:
        v = U.get(nid)
        if v is not None:
            disp[int(nid)] = [float(x) for x in v[:3]]
    umax = max([float(np.linalg.norm(v)) for v in disp.values()] or [0.0])
    vm = [analysis.von_mises(x["s"]) for x in out_solid.values()] + \
         [analysis.von_mises(p) for x in out_shell.values() for p in x["s"]]
    summary = {"analysis": adoc.get("name"), "materials": mode, "time": time.strftime("%Y-%m-%d %H:%M"),
               "nodes": len(disp), "solids": len(out_solid), "shells": len(out_shell), "umax": umax,
               "smax": max(vm or [0.0]), "pemax": max([x["pe"] for x in out_solid.values()] +
                                                       [max(x["pe"]) for x in out_shell.values()] or [0.0]),
               "nonlinear": bool(r["summary"].get("nonlinear")),
               "warnings": warn + list(r["summary"].get("warnings") or []), "report": r["files"].get("report")}
    with gzip.open(result_path(inp_path), "wt", encoding="utf-8") as f:
        json.dump({"inp_md5": saved["inp_md5"], "summary": summary, "disp": disp, "solids": out_solid,
                   "shells": out_shell}, f)
    return summary


def load(inp_path):
    """The initial state of the .inp, or None. Raises InitError when it belongs to an older .inp."""
    p = result_path(inp_path)
    if not os.path.isfile(p):
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        d = json.load(f)
    if not os.path.isfile(inp_path) or d.get("inp_md5") != model_inp.file_md5(inp_path):
        raise InitError("the initial state belongs to an older model .inp: Solve static again")
    return d


def status(inp_path):
    """{"summary"} of the saved initial state, {"stale": true} when it belongs to an older .inp, or None."""
    try:
        d = load(inp_path)
    except InitError:
        return {"stale": True}
    except (OSError, ValueError):
        return None
    return {"summary": d["summary"]} if d else None


# --------------------------------------------------------------------------- deck

def _f(v):
    return "%20.10g" % float(v)


def cards(state, stress=True, peeq=True):
    """Lines of /INIBRI/STRS_FGLO, /INISHE/STRS_F/GLOB and /INISH3/STRS_F/GLOB (without line ends)."""
    L = []
    if not stress:
        return L
    sol = state.get("solids") or {}
    if sol:
        L.append("/INIBRI/STRS_FGLO")
        for eid in sorted(sol, key=int):
            x = sol[eid]
            s = x["s"]
            pe = x["pe"] if peeq else 0.0
            L += ["# brick_ID Nb_integr   Isolnod    Isolid      nptr      npts      nptt      nlay grbric_ID",
                  "%10d%10d%10d%10d%10d%10d%10d%10d%10d" % (int(eid), 1, x["nn"], 1 if x["nn"] == 8 else 0, 0, 0, 0, 0, 0),
                  "#               Eint                 RHO", _f(x["e"]) + _f(x["rho"]),
                  "#             SIGMA1              SIGMA2              SIGMA3", _f(s[0]) + _f(s[1]) + _f(s[2]),
                  "#            SIGMA12             SIGMA23             SIGMA31", _f(s[3]) + _f(s[4]) + _f(s[5]),
                  "#          Epsilon_p", _f(pe)]
    for tri, head in ((False, "/INISHE/STRS_F/GLOB"), (True, "/INISH3/STRS_F/GLOB")):
        sh = {k: v for k, v in (state.get("shells") or {}).items() if bool(v.get("tri")) == tri}
        if not sh:
            continue
        L.append(head)
        for eid in sorted(sh, key=int):
            x = sh[eid]
            L += ["# shell_ID nb_integr       npg               Thick",
                  "%10d%10d%10d%s" % (int(eid), len(T_POINTS), 1, _f(x["t"])),
                  "#                 Em                  Eb                  H1                  H2                  H3",
                  _f(x["em"]) + _f(x["eb"]) + _f(0) + _f(0) + _f(0)]
            for k, s in enumerate(x["s"]):
                pe = x["pe"][k] if peeq else 0.0
                L += ["#            sigma_X             sigma_Y             sigma_Z", _f(s[0]) + _f(s[1]) + _f(s[2]),
                      "#           sigma_XY            sigma_YZ            sigma_ZX               eps_p             pos_nip",
                      _f(s[3]) + _f(s[4]) + _f(s[5]) + _f(pe) + _f(T_POINTS[k])]
    return L


def apply(lines, state, geometry=True, stress=True, peeq=True):
    """Starter deck lines (with line ends) with the /NODE coordinates moved by the displacements of the initial state
    and the initial stress cards before /END. Returns (lines, counts)."""
    out = list(lines)
    disp = {int(k): v for k, v in (state.get("disp") or {}).items()} if geometry else {}
    moved = 0
    in_node = False
    for i, ln in enumerate(out):
        s = ln.strip()
        if s.startswith("/"):
            in_node = s.upper().split("/")[1:2] == ["NODE"]
            continue
        if not in_node or not disp or s.startswith("#") or not s:
            continue
        try:
            nid = int(ln[:10])
            x = [float(ln[10:30]), float(ln[30:50]), float(ln[50:70])]
        except ValueError:
            parts = s.split()
            try:
                nid, x = int(parts[0]), [float(v) for v in parts[1:4]]
            except (ValueError, IndexError):
                continue
        d = disp.get(nid)
        if d is None:
            continue
        nl = "\r\n" if ln.endswith("\r\n") else "\n"
        out[i] = "%10d%20.12g%20.12g%20.12g" % (nid, x[0] + d[0], x[1] + d[1], x[2] + d[2]) + nl
        moved += 1
    add = cards(state, stress, peeq)
    if add:
        nl = "\r\n" if out and out[-1].endswith("\r\n") else "\n"
        block = ["#---1----|----2----|----3----|----4----|----5----|----6----|----7----|----8----|----9----|---10----|" + nl,
                 "# initial state from the static solve of %s (SHINYCAD initstate.py)%s" % ((state.get("summary") or {}).get("analysis"), nl)]
        block += [l + nl for l in add]
        k = next((j for j in range(len(out) - 1, -1, -1) if out[j].strip().upper() == "/END"), len(out))
        out[k:k] = block
    return out, {"nodes": moved, "solids": len(state.get("solids") or {}) if stress else 0,
                 "shells": len(state.get("shells") or {}) if stress else 0}
