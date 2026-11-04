# -*- coding: utf-8 -*-
"""Rivet section of the Explicit tab (ORC**3 workspace_rivet.py): /TH/NODE gauge rings around a rivet hole and the
force vs relative-displacement curve (rivet_calibration/make_gauge_rings.build_rings, relative_disp.compute).

Deck: the Target .rad. Gauge ring files: th_gauge_rings.inc and gauge_rings.json next to the deck. Results CSV: the
_find_th_csv search of the KE plot in the deck folder and in Output Dir, then rivet_calibration/wsconfig.py
find_results_csv (one folder level below Output Dir).
"""
import json
import os
import sys

_RIVET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rivet_calibration")
if _RIVET_DIR not in sys.path:
    sys.path.insert(0, _RIVET_DIR)

IMPORT_ERROR = None
try:
    import wsconfig as _wscfg
    import relative_disp as _rdisp
    import make_gauge_rings as _mgr
    from relative_disp import RivetError
except Exception as _e:                      # pragma: no cover
    IMPORT_ERROR = "%s: %s" % (type(_e).__name__, _e)
    _wscfg = _rdisp = _mgr = None

    class RivetError(Exception):
        pass

COMPONENTS = ["mag", "x", "y", "z", "axis"]
AXIS_CHOICES = ["x", "y", "z"]
KEYS = {"rv_centre_x": "0.0", "rv_centre_y": "0.0", "rv_centre_z": "0.0", "rv_radius": "6.0", "rv_axis": "z",
        "rv_plate1": "1.0", "rv_plate2": "-1.0", "rv_rtol": "0.5", "rv_atol": "0.4", "rv_maxnodes": "8",
        "rv_thgroup": "900", "rv_force_col": "", "rv_force_scale": "1.0", "rv_component": "mag", "rv_angle": "0",
        "rv_shear_dir": "x", "rv_axis_dir": "z", "rv_filter_hz": "", "rv_case_id": ""}


def _check():
    if IMPORT_ERROR:
        raise RivetError("the rivet_calibration package could not be imported (%s); expected at %s" % (IMPORT_ERROR, _RIVET_DIR))


def _float(ws, key, name, default=None):
    raw = (getattr(ws, key).get() or "").strip()
    if not raw:
        if default is not None:
            return default
        raise RivetError("%s is empty" % name)
    try:
        return float(raw)
    except ValueError:
        raise RivetError("%s is not a number: %r" % (name, raw))


def _deck(ws):
    deck = (ws.rad_target.get() or "").strip()
    if not deck:
        raise RivetError("no Target .rad (Solve)")
    return deck


def _results_csv(ws):
    deck = _deck(ws)
    job = os.path.basename(deck)
    for suffix in ("_0000.rad", "_0001.rad", ".rad"):
        if job.endswith(suffix):
            job = job[:-len(suffix)]
            break
    run_folder = (ws.out_dir.get() or "").strip()
    for folder in (os.path.dirname(os.path.abspath(deck)), run_folder):
        if folder and os.path.isdir(folder):
            found, _ = ws._find_th_csv(folder, job)
            if found:
                return found
    try:
        found = _wscfg.find_results_csv({"rad_target": deck, "out_dir": run_folder or os.path.dirname(deck)})
    except Exception:
        found = None
    if not found:
        raise RivetError("No results CSV found. Run the job and let Plot KE build it (th_to_csv), or use Load F-d CSV.")
    return found


def rings(ws):
    """Writes th_gauge_rings.inc and gauge_rings.json next to the Target .rad; logs the diagnostics."""
    _check()
    deck = _deck(ws)
    res = _mgr.build_rings(
        deck,
        [_float(ws, "rv_centre_x", "Hole centre X"), _float(ws, "rv_centre_y", "Hole centre Y"),
         _float(ws, "rv_centre_z", "Hole centre Z")],
        _float(ws, "rv_radius", "Ring radius"),
        [_float(ws, "rv_plate1", "Plate 1 mid-surface"), _float(ws, "rv_plate2", "Plate 2 mid-surface")],
        axis=ws.rv_axis.get(),
        rtol=_float(ws, "rv_rtol", "Radial tolerance", 0.5),
        atol=_float(ws, "rv_atol", "Axial tolerance", 0.4),
        max_nodes=int(_float(ws, "rv_maxnodes", "Max nodes", 8)),
        thgroup_id=int(_float(ws, "rv_thgroup", "First TH group", 900)))
    ws.log_msg("Rivet: read %d nodes from %s" % (res["node_count"], os.path.basename(deck)))
    for label, msgs in res["diagnostics"]:
        for m in msgs:
            ws.log_msg("Rivet:   %s - %s" % (label, m))
    ws.log_msg("Rivet: wrote %s" % res["inc_path"])
    ws.log_msg("Rivet: wrote %s" % res["json_path"])
    for line in _mgr.NEXT_STEPS:
        if line:
            ws.log_msg("Rivet: %s" % line)
    return {"inc": res["inc_path"], "json": res["json_path"], "nodes": res["node_count"],
            "rings": [{"tag": r["tag"], "name": r["name"], "plate_coord": r["plate_coord"],
                       "nodes": [h["id"] for h in r["nodes"]]} for r in res["rings"]],
            "diagnostics": [[lbl, list(m)] for lbl, m in res["diagnostics"]]}


def columns(ws):
    """Columns of the results CSV (logged)."""
    _check()
    csv_path = _results_csv(ws)
    header, _ = _rdisp.load_csv(csv_path)
    ws.log_msg("Rivet: %d columns in %s" % (len(header), os.path.basename(csv_path)))
    for i, h in enumerate(header):
        ws.log_msg("Rivet:   [%3d] %s" % (i, h))
    unnamed = any(h.lower().startswith("var ") for h in header)
    if unnamed:
        ws.log_msg("Rivet: columns are unnamed ('var NN') - add /TH/TITLE to the engine deck and re-run th_to_csv.")
    return {"csv": csv_path, "columns": header, "unnamed": unnamed}


def _curve(label, res, summary):
    return {"label": label, "disp": res["disp"], "force": res["force"], "times": res["times"], "xlabel": res.get("label"),
            "peak_index": res.get("peak_index"), "peak_disp": res.get("peak_disp"), "peak_force": res.get("peak_force"),
            "fail_disp": res.get("fail_disp"), "out_path": res.get("out_path"), "summary": summary}


def extract(ws):
    """Force vs relative displacement of the results CSV and the gauge ring manifest; writes <csv>_fd.csv."""
    _check()
    if not (ws.rv_force_col.get() or "").strip():
        raise RivetError("Force column is empty - use Columns to see what the run wrote.")
    deck = _deck(ws)
    manifest = os.path.join(os.path.dirname(os.path.abspath(deck)), _mgr.JSON_NAME)
    if not os.path.isfile(manifest):
        raise RivetError("No %s beside the deck - press Build Gauge Rings first." % _mgr.JSON_NAME)
    csv_path = _results_csv(ws)
    filt = (ws.rv_filter_hz.get() or "").strip()
    res = _rdisp.compute(csv_path, manifest, ws.rv_force_col.get().strip(),
                         force_scale=_float(ws, "rv_force_scale", "Force scale", 1.0),
                         component=ws.rv_component.get(), angle=_float(ws, "rv_angle", "Load angle", 0.0),
                         shear_dir=ws.rv_shear_dir.get(), axis_dir=ws.rv_axis_dir.get(),
                         filter_hz=(float(filt) if filt else None))
    label = (ws.rv_case_id.get() or "").strip() or os.path.splitext(os.path.basename(csv_path))[0]
    ws.log_msg("Rivet: extracted from %s" % os.path.basename(csv_path))
    for n in res["notes"]:
        ws.log_msg("Rivet:   %s" % n)
    ws.log_msg("Rivet: wrote %s" % res["out_path"])
    lines = _rdisp.summarise(res)
    for line in lines:
        ws.log_msg("Rivet: %s" % line)
    return _curve(label, res, "   |   ".join(lines[:2]))


def load_fd(path):
    """F-d CSV written by Extract (time, displacement, force)."""
    _check()
    header, data = _rdisp.load_csv(path)
    if len(header) < 3:
        raise RivetError("expected columns: time, displacement, force")
    res = {"times": [r[0] for r in data], "disp": [r[1] for r in data], "force": [r[2] for r in data], "label": header[1]}
    pk_i, pk_f = max(enumerate(res["force"]), key=lambda t: abs(t[1]))
    res.update({"peak_index": pk_i, "peak_force": pk_f, "peak_disp": res["disp"][pk_i], "out_path": path})
    label = os.path.splitext(os.path.basename(path))[0]
    return _curve(label, res, "Loaded %s   |   Peak force %.4g at %.4g" % (os.path.basename(path), pk_f, res["peak_disp"]))


def write_ws_config(ws, path):
    """workspace_config.json with the current settings for the rivet_calibration scripts (RIVET_CAL_CONFIG)."""
    snap = ws._settings_snapshot()
    snap["env_dirs"] = {}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2)
    return path
