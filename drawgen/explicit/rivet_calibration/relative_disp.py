#!/usr/bin/env python3
"""
relative_disp.py - build a force vs relative-displacement curve from a T01 CSV.

Reads the CSV that th_to_csv produces, averages each gauge ring, subtracts one
ring from the other to get the relative motion across the rivet, pairs it with
the driving force, and reports peak force and displacement at failure.

Used two ways:
  * as a command-line tool (see Usage below)
  * as a library - the GUI's Rivet tab calls compute() directly, so both paths
    run exactly the same code

Usage
-----
    # find the CSV and manifest from workspace_config.json automatically
    python relative_disp.py --force-col "RBODY 12 FX"

    # or point at them explicitly
    python relative_disp.py run_T01.csv gauge_rings.json \
        --force-col "RBODY 12 FX" --out A1_curve.csv

    # let it show you what columns exist first
    python relative_disp.py --list-columns

Options
-------
  --config PATH       workspace_config.json. Default: found automatically.
  --force-col NAME    Column holding the driving force. Required unless
                      --list-columns. Accepts a partial, case-insensitive match.
  --force-scale S     Multiply force by S. Use 2.0 for a symmetry half-model.
                      Default 1.0.
  --component {x,y,z,mag,axis}
                      Which component of relative displacement to report.
                      'axis' projects onto the load direction given by --angle.
                      Default mag.
  --angle DEG         Load angle from the faying plane, matching the run sheet
                      convention: 0 = pure shear, 90 = pure tension. Used only
                      when --component axis.
  --shear-dir {x,y,z} In-plane shear direction. Default x.
  --axis-dir {x,y,z}  Rivet shank axis direction. Default z.
  --filter-hz F       Optional low-pass (zero-phase moving average) corner, for
                      the impact-rate runs. Apply the SAME value to every case
                      or you will manufacture a rate effect that is not real.
  --out FILE          Output CSV. Default <input stem>_fd.csv

Notes
-----
th_to_csv column naming depends on whether /TH/TITLE was in the engine deck.
Without it you get 'var 32' style names and this script cannot find anything
useful - use --list-columns to see what you actually have.
"""

import argparse
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wsconfig

DIRS = {"x": "X", "y": "Y", "z": "Z"}
FAIL_FRACTION = 0.05          # "failed" = force below this fraction of peak


class RivetError(Exception):
    """Anything the caller should show the user rather than traceback on."""


# --------------------------------------------------------------- csv loading
def load_csv(path):
    with open(path, "r", errors="replace") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise RivetError(f"empty file: {path}")
    header = [h.strip().strip('"') for h in rows[0]]
    data = []
    for r in rows[1:]:
        if not r or all(not c.strip() for c in r):
            continue
        vals = []
        for c in r:
            try:
                vals.append(float(c))
            except ValueError:
                vals.append(float("nan"))
        data.append(vals)
    if not data:
        raise RivetError(f"no numeric rows in {os.path.basename(path)} - this is "
                         "usually a banner-only stdout capture. Re-run th_to_csv.")
    return header, data


def find_col(header, pattern, required=True):
    """Case-insensitive substring match, with an exact match winning."""
    pl = pattern.lower().strip()
    for i, h in enumerate(header):
        if h.lower().strip() == pl:
            return i
    hits = [i for i, h in enumerate(header) if pl in h.lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        names = ", ".join(repr(header[i]) for i in hits[:8])
        raise RivetError(f"'{pattern}' matches {len(hits)} columns ({names}...). "
                         "Be more specific.")
    if required:
        raise RivetError(f"no column matching '{pattern}'. Use --list-columns "
                         "(or the Columns button) to see what exists.")
    return None


def node_disp_cols(header, node_id, tag=None):
    """Find the DX/DY/DZ columns belonging to one node.

    th_to_csv names TH node columns from the node_name written in the /TH/NODE
    card, which make_gauge_rings.py sets to e.g. 'P1_th045.0'. Falls back to
    matching on the bare node ID.
    """
    out = {}
    for comp in ("X", "Y", "Z"):
        cand = []
        for i, h in enumerate(header):
            hl = h.lower()
            if f"d{comp.lower()}" not in hl:
                continue
            if tag and tag.lower() in hl:
                cand.append(i)
            elif str(node_id) in hl:
                cand.append(i)
        if len(cand) >= 1:
            out[comp] = cand[0]
    return out if len(out) == 3 else None


# --------------------------------------------------------------- maths
def moving_average(series, window):
    if window <= 1:
        return series[:]
    half = window // 2
    n = len(series)
    out = []
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        chunk = [v for v in series[a:b] if not math.isnan(v)]
        out.append(sum(chunk) / len(chunk) if chunk else float("nan"))
    return out


def window_from_hz(times, corner_hz):
    if not corner_hz or len(times) < 3:
        return 1
    dts = [times[i + 1] - times[i] for i in range(len(times) - 1)]
    dts = [d for d in dts if d > 0]
    if not dts:
        return 1
    dt = sum(dts) / len(dts)
    w = int(round(1.0 / (corner_hz * dt)))
    return max(1, w if w % 2 else w + 1)


# --------------------------------------------------------------- library API
def resolve_inputs(csv_file=None, manifest_path=None, config=None):
    """Fill in whichever of (csv, manifest) is missing, from the GUI config.

    Returns (csv_file, manifest_path, notes[]).
    """
    notes = []
    if csv_file and manifest_path:
        return csv_file, manifest_path, notes

    cfg = wsconfig.load(config)
    notes.append(f"config: {cfg['__path__']}")
    if not csv_file:
        csv_file = wsconfig.find_results_csv(cfg)
        if not csv_file:
            raise RivetError(
                "No results CSV found in the run folder. Run th_to_csv first "
                "(the Plot KE button does this), or pass the path explicitly.")
        notes.append(f"results: {csv_file}")
    if not manifest_path:
        cand = os.path.join(wsconfig.deck_folder(cfg), "gauge_rings.json")
        if not os.path.isfile(cand):
            raise RivetError(f"No gauge_rings.json beside the deck ({cand}). "
                             "Build the gauge rings first.")
        manifest_path = cand
        notes.append(f"manifest: {manifest_path}")
    return csv_file, manifest_path, notes


def list_columns(csv_file=None, config=None):
    csv_file, _, notes = resolve_inputs(csv_file, "unused", config)
    header, _ = load_csv(csv_file)
    return header, notes


def compute(csv_file, manifest_path, force_col, force_scale=1.0,
            component="mag", angle=0.0, shear_dir="x", axis_dir="z",
            filter_hz=None, out_path=None, write_csv=True):
    """Force vs relative displacement across the rivet.

    Returns a dict with: times, disp, force, label, peak_force, peak_index,
    fail_disp, fail_index, out_path, notes (list of strings worth logging).
    fail_disp is None when the run never separated.
    """
    notes = []
    header, data = load_csv(csv_file)

    with open(manifest_path) as fh:
        man = json.load(fh)
    rings = man.get("rings", [])
    if len(rings) != 2:
        raise RivetError(f"expected 2 rings in the manifest, found {len(rings)}")

    time_idx = 0
    for i, h in enumerate(header):
        if h.strip().lower() in ("time", "t"):
            time_idx = i
            break
    times = [row[time_idx] for row in data]

    force_idx = find_col(header, force_col)
    notes.append(f"force column: {header[force_idx]!r}")
    force = [row[force_idx] * force_scale for row in data]

    # ---- average each ring
    ring_mean = []
    for ring in rings:
        cols_per_node, missing = [], []
        for nid in ring["node_ids"]:
            cols = node_disp_cols(header, nid, ring.get("tag"))
            (cols_per_node if cols else missing).append(cols if cols else nid)
        if not cols_per_node:
            raise RivetError(
                f"ring {ring.get('tag')}: no displacement columns found for any "
                "node. Check /TH/TITLE was in the engine deck and that the run "
                "actually wrote these nodes.")
        if missing:
            notes.append(f"ring {ring.get('tag')}: {len(missing)} of "
                         f"{len(ring['node_ids'])} nodes not in the CSV")
        means = {"X": [], "Y": [], "Z": []}
        for row in data:
            for comp in ("X", "Y", "Z"):
                vals = [row[c[comp]] for c in cols_per_node]
                vals = [v for v in vals if not math.isnan(v)]
                means[comp].append(sum(vals) / len(vals) if vals else float("nan"))
        ring_mean.append(means)
        notes.append(f"ring {ring.get('tag')}: averaged {len(cols_per_node)} nodes")

    rel = {c: [ring_mean[0][c][i] - ring_mean[1][c][i] for i in range(len(data))]
           for c in ("X", "Y", "Z")}

    if component in ("x", "y", "z"):
        disp = rel[DIRS[component]]
        label = f"rel_d{component}"
    elif component == "mag":
        disp = [math.sqrt(rel["X"][i] ** 2 + rel["Y"][i] ** 2 + rel["Z"][i] ** 2)
                for i in range(len(data))]
        label = "rel_disp_mag"
    elif component == "axis":
        th = math.radians(angle)
        s, a = DIRS[shear_dir], DIRS[axis_dir]
        disp = [rel[s][i] * math.cos(th) + rel[a][i] * math.sin(th)
                for i in range(len(data))]
        label = f"rel_disp_at_{angle:g}deg"
    else:
        raise RivetError(f"unknown component: {component}")

    if filter_hz:
        w = window_from_hz(times, filter_hz)
        force = moving_average(force, w)
        disp = moving_average(disp, w)
        notes.append(f"filtered at {filter_hz:g} Hz (moving average, window {w})")

    if write_csv:
        out_path = out_path or (os.path.splitext(csv_file)[0] + "_fd.csv")
        with open(out_path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["time", label, "force"])
            for i in range(len(data)):
                w.writerow([times[i], disp[i], force[i]])
    else:
        out_path = None

    valid = [(i, force[i]) for i in range(len(force)) if not math.isnan(force[i])]
    if not valid:
        raise RivetError("no valid force data in the selected column")
    pk_i, pk_f = max(valid, key=lambda t: abs(t[1]))
    thresh = FAIL_FRACTION * abs(pk_f)
    fail_i = None
    for i in range(pk_i, len(force)):
        if not math.isnan(force[i]) and abs(force[i]) < thresh:
            fail_i = i
            break

    return {
        "times": times, "disp": disp, "force": force, "label": label,
        "peak_force": pk_f, "peak_index": pk_i,
        "peak_disp": disp[pk_i], "peak_time": times[pk_i],
        "fail_disp": (disp[fail_i] if fail_i is not None else None),
        "fail_index": fail_i,
        "fail_time": (times[fail_i] if fail_i is not None else None),
        "force_scale": force_scale, "out_path": out_path, "notes": notes,
        "csv_file": csv_file, "manifest": manifest_path,
    }


def summarise(res):
    """The lines worth printing or logging after a compute()."""
    out = [f"Peak force        {res['peak_force']:.4g}   "
           f"(t = {res['peak_time']:.4g}, {res['label']} = {res['peak_disp']:.4g})"]
    if res["fail_disp"] is not None:
        out.append(f"Disp at failure   {res['fail_disp']:.4g}   "
                   f"(force below {FAIL_FRACTION:.0%} of peak, t = {res['fail_time']:.4g})")
    else:
        out.append(f"Disp at failure   NOT REACHED - force never fell below "
                   f"{FAIL_FRACTION:.0%} of peak. The run stopped before full "
                   "separation; extend the prescribed displacement.")
    if res["force_scale"] != 1.0:
        out.append(f"(force scaled by {res['force_scale']:g} - symmetry factor applied)")
    return out


# --------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Force vs relative displacement from a T01 CSV.")
    ap.add_argument("csv_file", nargs="?", default=None,
                    help="th_to_csv output. Omit to locate it from workspace_config.json.")
    ap.add_argument("manifest", nargs="?", default=None,
                    help="gauge_rings.json. Omit to look beside the deck.")
    ap.add_argument("--config", default=None, help="Path to workspace_config.json.")
    ap.add_argument("--list-columns", action="store_true")
    ap.add_argument("--force-col")
    ap.add_argument("--force-scale", type=float, default=1.0)
    ap.add_argument("--component", choices=["x", "y", "z", "mag", "axis"], default="mag")
    ap.add_argument("--angle", type=float, default=0.0)
    ap.add_argument("--shear-dir", choices=list(DIRS), default="x")
    ap.add_argument("--axis-dir", choices=list(DIRS), default="z")
    ap.add_argument("--filter-hz", type=float, default=None)
    ap.add_argument("--out")
    args = ap.parse_args()

    try:
        if args.list_columns:
            header, notes = list_columns(args.csv_file, args.config)
            for n in notes:
                print(n)
            print(f"\n{len(header)} columns:\n")
            for i, h in enumerate(header):
                print(f"  [{i:3d}] {h}")
            print("\nIf these read 'var 32', 'var 33' etc, add /TH/TITLE to the engine")
            print("deck and re-run th_to_csv - the names live in a _TITLES file, not the T01.")
            return 0

        if not args.force_col:
            raise RivetError("--force-col is required (or use --list-columns first)")

        csv_file, manifest_path, notes = resolve_inputs(
            args.csv_file, args.manifest, args.config)
        for n in notes:
            print(n)

        res = compute(csv_file, manifest_path, args.force_col,
                      force_scale=args.force_scale, component=args.component,
                      angle=args.angle, shear_dir=args.shear_dir,
                      axis_dir=args.axis_dir, filter_hz=args.filter_hz,
                      out_path=args.out)
        for n in res["notes"]:
            print(f"  {n}")
        print(f"\nWrote {res['out_path']}")
        print("\nFor the run sheet:")
        for line in summarise(res):
            print(f"  {line}")
        return 0

    except (RivetError, wsconfig.ConfigError) as e:
        sys.stderr.write(f"{e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
