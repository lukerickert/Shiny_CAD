"""Deck generator source of the Explicit tab (DECK_GENERATOR: deck_stepgen.py, deck_mesh.py).

Stiffened deck panel (deck plate on the midplane z = 0, beams below it) -> structured shell mesh (deck_mesh) -> model
.inp for the deck build; STEP of the deck structure (deck_stepgen, build123d) and a ShinyCAD part with one surface
body per component.

Explicit document, deck part:
  "deck": {"L": mm (X distance), "B": mm (Y distance), "snipe": mm, "deck_t": mm, "deck_name": "DECK",
           "beams": [{"name", "axis": "x" | "y", "pos", "h", "bf_top", "bf_bot", "t_web", "t_flange"} (mm)],
           "size": mm (max element size), "min_div": divisions per interval, "tri": bool (S3 instead of S4),
           "shell": "S4" | "S4R", "material": material of the document ("": the default material),
           "edges": {"x0" | "xL" | "y0" | "yB": "free" | "pinned" | "clamped"}}

The .inp holds *NODE, one *ELEMENT block per element set (DECK, <BEAM>_WEB, <BEAM>_FLANGE, <BEAM>_LOWER_FLANGE),
*MATERIAL, one *SHELL SECTION per element set (thickness from the beam table), *NSET EDGE_X0 / EDGE_XL / EDGE_Y0 /
EDGE_YB (nodes on the panel edge planes, webs included) and *BOUNDARY (pinned: 1-3, clamped: 1-6). The PrePoMax
parameter table of the thicknesses is written beside it (<name>_Parameters.pmp).
Meshing runs in a subprocess (gmsh): python -m drawgen.explicit.deck <job.json> <out.json>.
"""
import json
import os
import subprocess
import sys
import tempfile

COINCIDENT_TOL = 0.5      # mm, same axis: the same place
NEAR_TOL = 10.0           # mm, same axis: meshes as slivers
EDGE_KEYS = ("x0", "xL", "y0", "yB")
EDGE_DOFS = {"pinned": (1, 3), "clamped": (1, 6)}
DEFAULT = {"L": 6000.0, "B": 4000.0, "snipe": 30.0, "deck_t": 8.0, "deck_name": "DECK", "size": 100.0, "min_div": 1,
           "tri": False, "shell": "S4", "material": "", "edges": {k: "free" for k in EDGE_KEYS},
           "beams": [{"name": "GIRDER", "axis": "y", "pos": 2000.0, "h": 500.0, "bf_top": 250.0, "bf_bot": 250.0, "t_web": 10.0, "t_flange": 14.0},
                     {"name": "GIRDER", "axis": "y", "pos": 4000.0, "h": 500.0, "bf_top": 250.0, "bf_bot": 250.0, "t_web": 10.0, "t_flange": 14.0},
                     {"name": "BEAM", "axis": "x", "pos": 1000.0, "h": 250.0, "bf_top": 120.0, "bf_bot": 120.0, "t_web": 8.0, "t_flange": 12.0},
                     {"name": "BEAM", "axis": "x", "pos": 2000.0, "h": 250.0, "bf_top": 120.0, "bf_bot": 120.0, "t_web": 8.0, "t_flange": 12.0},
                     {"name": "BEAM", "axis": "x", "pos": 3000.0, "h": 250.0, "bf_top": 120.0, "bf_bot": 120.0, "t_web": 8.0, "t_flange": 12.0},
                     {"name": "STIFF", "axis": "x", "pos": 500.0, "h": 150.0, "bf_top": 0.0, "bf_bot": 0.0, "t_web": 6.0, "t_flange": 0.0},
                     {"name": "STIFF", "axis": "x", "pos": 1500.0, "h": 150.0, "bf_top": 0.0, "bf_bot": 0.0, "t_web": 6.0, "t_flange": 0.0},
                     {"name": "STIFF", "axis": "x", "pos": 2500.0, "h": 150.0, "bf_top": 0.0, "bf_bot": 0.0, "t_web": 6.0, "t_flange": 0.0},
                     {"name": "STIFF", "axis": "x", "pos": 3500.0, "h": 150.0, "bf_top": 0.0, "bf_bot": 0.0, "t_web": 6.0, "t_flange": 0.0}]}


class DeckError(ValueError):
    pass


def _num(v, what):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise DeckError("%s: %r is not a number" % (what, v))
    if x != x or x in (float("inf"), float("-inf")):
        raise DeckError("%s: not a finite number" % what)
    return x


def _name(s):
    import re
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(s or "").strip()).strip("_").upper()


def model(deck):
    """deck_mesh model dict {L, B, snipe, deck_name, deck_t, beams} of the deck part. Raises DeckError."""
    d = dict(DEFAULT, **(deck or {}))
    L, B = _num(d["L"], "X distance"), _num(d["B"], "Y distance")
    if L <= 0 or B <= 0:
        raise DeckError("X and Y distance must be more than 0 mm")
    snipe = _num(d.get("snipe", 30.0), "Flange snipe")
    if snipe < 0:
        raise DeckError("Flange snipe must be 0 mm or more")
    beams = []
    for i, b in enumerate(d.get("beams") or []):
        name = _name(b.get("name")) or "BEAM"
        where = "beam %d (%s)" % (i + 1, name)
        axis = str(b.get("axis") or "x").strip().lower()
        if axis not in ("x", "y"):
            raise DeckError("%s: axis must be x or y" % where)
        r = {"name": name, "axis": axis}
        for k in ("pos", "h", "bf_top", "bf_bot", "t_web", "t_flange"):
            v = b.get(k)
            if v in (None, "") and k not in ("pos", "h"):
                v = 0.0
            r[k] = _num(v, "%s %s" % (where, k))
        if r["h"] <= 0:
            raise DeckError("%s: h must be more than 0 mm" % where)
        if min(r["bf_top"], r["bf_bot"], r["t_web"], r["t_flange"]) < 0:
            raise DeckError("%s: widths and thicknesses must be 0 mm or more" % where)
        lim = B if axis == "x" else L
        if r["pos"] < -1e-9 or r["pos"] > lim + 1e-9:
            raise DeckError("%s: pos %g mm is outside %s 0 to %g mm" % (where, r["pos"], "y" if axis == "x" else "x", lim))
        beams.append(r)
    return {"L": L, "B": B, "snipe": snipe, "deck_name": _name(d.get("deck_name")) or "DECK",
            "deck_t": _num(d.get("deck_t", 0), "Deck thickness"), "beams": beams}


def clashes(m):
    """(coincident, near): same-axis beam pairs closer than COINCIDENT_TOL / NEAR_TOL mm, as texts."""
    co, near = [], []
    bs = m["beams"]
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            a, b = bs[i], bs[j]
            if a["axis"] != b["axis"]:
                continue
            d = abs(a["pos"] - b["pos"])
            if d <= COINCIDENT_TOL:
                co.append("%s and %s: both at %g mm (axis %s)" % (a["name"], b["name"], a["pos"], a["axis"]))
            elif d <= NEAR_TOL:
                near.append("%s at %g and %s at %g: %g mm apart (axis %s)" % (a["name"], a["pos"], b["name"], b["pos"], d, a["axis"]))
    return co, near


def parts(m):
    """[(part name, [polygons])] of deck_stepgen.deck_model."""
    from . import deck_mesh
    return deck_mesh.model_parts(m)


def check(deck):
    """Geometry and sections of the deck part, without meshing:
    {"parts": [{"name", "polys"}], "sections": [{"set", "param", "t"}], "errors", "warnings", "inp_errors"}."""
    from . import deck_mesh
    try:
        m = model(deck)
    except DeckError as e:
        return {"parts": [], "sections": [], "errors": [str(e)], "warnings": [], "inp_errors": []}
    co, near = clashes(m)
    errors = ["two beams on one line: " + t for t in co]
    warnings = ["closer than %g mm: %s" % (NEAR_TOL, t) for t in near]
    ps = parts(m)
    names = [n for n, _p in ps]
    thick, conflicts = deck_mesh.section_thicknesses(m, names)
    warnings += ["one section per name: " + c for c in conflicts]
    inp_errors = ["%s: thickness %s is 0 mm" % (s, p) for s, (p, t) in thick.items() if t <= 0]
    return {"parts": [{"name": n, "polys": [[list(map(float, q)) for q in poly] for poly in pl]} for n, pl in ps],
            "sections": [{"set": s, "param": p, "t": t} for s, (p, t) in thick.items()],
            "errors": errors, "warnings": warnings, "inp_errors": inp_errors}


# --------------------------------------------------------------------------- .inp

def write_inp(path, title, nodes, elems, sets, thick, material, shell="S4", edges=None, L=0.0, B=0.0):
    """Model .inp: one *ELEMENT block per element set and type, the sections of deck_mesh (*MATERIAL, *SHELL SECTION
    per set), edge node sets and *BOUNDARY. Returns the number of *BOUNDARY rows."""
    from . import deck_mesh
    typ = {"S4": "S4R" if shell == "S4R" else "S4", "S3": "S3R" if shell == "S4R" else "S3"}
    conn = {}
    for t, block in elems.items():
        for e, c in block.items():
            conn[e] = (t, c)
    out = ["*HEADING\n", (title or "SHINYCAD deck")[:80] + "\n",
           "** SHINYCAD deck generator (deck_mesh). Units: mm, t, s, N, MPa. Deck midplane z = 0.\n", "*NODE\n"]
    for nid in sorted(nodes):
        x, y, z = nodes[nid]
        out.append("%d, %.6f, %.6f, %.6f\n" % (nid, x, y, z))
    for name, ids in sets.items():
        by = {}
        for e in sorted(ids):
            if e in conn:
                by.setdefault(conn[e][0], []).append(e)
        for t, es in by.items():
            out.append("*ELEMENT, TYPE=%s, ELSET=%s\n" % (typ.get(t, t), name))
            for e in es:
                out.append("%d, %s\n" % (e, ", ".join(str(n) for n in conn[e][1])))
    rows = []
    for k in EDGE_KEYS:
        mode = (edges or {}).get(k) or "free"
        if mode not in EDGE_DOFS:
            continue
        ax, val = (0, 0.0) if k == "x0" else (0, L) if k == "xL" else (1, 0.0) if k == "y0" else (1, B)
        ns = sorted(n for n, p in nodes.items() if abs(p[ax] - val) < 1e-6)
        if not ns:
            continue
        nm = "EDGE_" + k.upper()
        out.append("*NSET, NSET=%s\n" % nm)
        for i in range(0, len(ns), 16):
            out.append(", ".join(str(n) for n in ns[i:i + 16]) + "\n")
        a, b = EDGE_DOFS[mode]
        rows.append("%s, %d, %d\n" % (nm, a, b))
    out += deck_mesh._section_lines(thick, material, only=list(sets))
    if rows:
        out.append("*BOUNDARY\n")
        out += rows
    with open(path, "w") as f:
        f.writelines(out)
    return len(rows)


def _mesh_main(job_path, out_path):
    """Subprocess: meshes the model of the job and writes the .inp. Writes {"ok", "error", summary fields}."""
    with open(job_path, "r") as f:
        job = json.load(f)
    res = {"ok": False}
    try:
        from . import deck_mesh
        m = job["model"]
        size = float(job["size"])
        gmsh, _parts, sets, stats = deck_mesh.build_and_mesh(m, size, min_div=int(job.get("min_div") or 1),
                                                             recombine=not job.get("tri"), order=1, verbose=False)
        try:
            nodes, elems = deck_mesh.mesh_data(gmsh)
            ext = deck_mesh.set_extents(gmsh, sets)
        finally:
            gmsh.finalize()
        thick, conflicts = deck_mesh.section_thicknesses(m, sets)
        nb = write_inp(job["inp"], job.get("title"), nodes, elems, sets, thick, job["material"], job.get("shell") or "S4",
                       job.get("edges"), m["L"], m["B"])
        if thick:
            deck_mesh.write_pmp(thick, os.path.splitext(job["inp"])[0] + "_Parameters.pmp")
        sec = {s: (n, p, t) for n, s, p, t in deck_mesh.section_map(thick, list(sets))}
        res = {"ok": True, "nodes": len(nodes), "elements": sum(len(v) for v in sets.values()), "supports": nb,
               "sets": [{"set": k, "elements": len(v), "z": list(ext[k]), "t": sec[k][2] if k in sec else 0.0,
                         "param": sec[k][1] if k in sec else "", "section": sec[k][0] if k in sec else ""} for k, v in sets.items()],
               "counts": stats["counts"], "longest_edge": stats["longest_edge"], "ar_median": stats["ar_median"],
               "ar_worst": stats["ar_worst"], "junctions": {str(k): v for k, v in stats["junctions"].items()},
               "conflicts": conflicts}
    except Exception as e:
        res = {"ok": False, "error": "%s: %s" % (e.__class__.__name__, e)}
    with open(out_path, "w") as f:
        json.dump(res, f)


def build(doc, inp_path, title="", progress=None, timeout=1800):
    """Meshes the deck part of the document and writes the .inp. Returns {"inp", "payload", "summary"}."""
    from . import meshview
    from .model_inp import ModelError, material_values, safe
    say = progress or (lambda *a: None)
    deck = dict(DEFAULT, **(doc.get("deck") or {}))
    c = check(deck)
    if c["errors"]:
        raise ModelError("; ".join(c["errors"]))
    if c["inp_errors"]:
        raise ModelError("shell sections need a thickness: " + "; ".join(c["inp_errors"]))
    m = model(deck)
    size = _num(deck.get("size") or 100.0, "Max element size")
    if size <= 0:
        raise ModelError("Max element size must be more than 0 mm")
    mname = deck.get("material") or doc.get("default_material") or next(iter(doc.get("materials") or {}), None)
    if not mname:
        raise ModelError("no material")
    E, nu, rho, _lib = material_values(doc, mname)
    job = {"model": m, "size": size, "min_div": int(deck.get("min_div") or 1), "tri": bool(deck.get("tri")),
           "shell": deck.get("shell") or "S4", "edges": deck.get("edges") or {}, "inp": inp_path,
           "title": title or "SHINYCAD deck", "material": {"name": safe(mname, 60).upper(), "E": E, "nu": nu, "rho": rho}}
    os.makedirs(os.path.dirname(os.path.abspath(inp_path)), exist_ok=True)
    say("mesh", "Meshing the deck (%d beams, max element %g mm)" % (len(m["beams"]), size))
    with tempfile.TemporaryDirectory() as td:
        jp, op = os.path.join(td, "job.json"), os.path.join(td, "out.json")
        with open(jp, "w") as f:
            json.dump(job, f)
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        try:
            r = subprocess.run([sys.executable, "-m", "drawgen.explicit.deck", jp, op], cwd=root, capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ModelError("meshing the deck took longer than %d s" % timeout)
        if not os.path.isfile(op):
            raise ModelError("deck meshing failed: %s" % ((r.stderr or r.stdout or "").strip()[-600:] or "no output"))
        with open(op, "r") as f:
            res = json.load(f)
    if not res.get("ok"):
        raise ModelError("deck meshing failed: %s" % res.get("error"))
    say("view", "Reading the mesh")
    mm = meshview.read_inp(inp_path)
    pl = meshview.payload(mm["xyz"], mm["cells"])
    pl["part_names"] = ["%s (%s)" % p for p in mm["parts"]]
    warnings = list(c["warnings"])
    if res["longest_edge"] > size * 1.001:
        warnings.append("an element edge of %.1f mm exceeds the max element size %g mm (a face meshed unstructured)"
                        % (res["longest_edge"], size))
    summary = {"nodes": res["nodes"], "elements": res["elements"], "supports": res["supports"], "deck": True,
               "material": job["material"]["name"], "sets": res["sets"], "counts": res["counts"],
               "longest_edge": res["longest_edge"], "ar_median": res["ar_median"], "ar_worst": res["ar_worst"],
               "junctions": res["junctions"], "warnings": warnings}
    return {"inp": inp_path, "payload": pl, "summary": summary}


# --------------------------------------------------------------------------- STEP and ShinyCAD part

def step(doc, out, progress=None):
    """STEP of the deck structure (deck_stepgen.build: fuse, group per part name, sewn shells, one named component per
    part) and <stem>_model.json beside it. Returns the component names."""
    import contextlib
    import io
    from . import deck_stepgen
    say = progress or (lambda *a: None)
    deck = dict(DEFAULT, **(doc.get("deck") or {}))
    c = check(deck)
    if c["errors"]:
        raise DeckError("; ".join(c["errors"]))
    m = model(deck)
    beams = [deck_stepgen.Beam(**b) for b in m["beams"]]
    ps = deck_stepgen.deck_model(m["L"], m["B"], beams, deck_name=m["deck_name"], snipe=m["snipe"])
    say("step", "Fusing %d plates" % sum(len(p) for _n, p in ps))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        names = deck_stepgen.build(ps, out, L=m["L"], B=m["B"], beams=beams, snipe=m["snipe"], deck_name=m["deck_name"],
                                   deck_t=m["deck_t"])
    return {"step": out, "components": names, "log": log.getvalue().splitlines()}


def part_record(name, step_path, components):
    """ShinyCAD part: one Import surface feature (surf_import) per component of the deck STEP."""
    feats = [{"id": "f%d" % (i + 1), "name": c, "type": "surf_import", "suppressed": False, "path": step_path, "label": c}
             for i, c in enumerate(components)]
    return {"name": name, "version": 2, "features": feats, "next": len(feats) + 1}


if __name__ == "__main__":
    _mesh_main(sys.argv[1], sys.argv[2])
