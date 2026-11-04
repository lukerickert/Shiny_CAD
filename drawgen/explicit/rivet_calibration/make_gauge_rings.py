#!/usr/bin/env python3
"""
make_gauge_rings.py - build /TH/NODE gauge rings around a rivet hole.

Picks a ring of nodes at a given radius from the hole axis, on each of the two
plates, and writes the /TH/NODE cards to paste into your Radioss starter deck.
Also writes a JSON manifest so the post-processor knows which node IDs belong to
which ring.

The point of the ring is to measure RELATIVE displacement across the joint
without perturbing the model: no rigid bodies, no extra constraints, nothing
that adds stiffness where the plate is yielding. You simply record several
nodes and average them afterwards.

Used two ways:
  * as a command-line tool (see Usage below)
  * as a library - the GUI's Rivet tab calls build_rings() directly, so both
    paths run exactly the same code

Usage
-----
  Using the GUI's current model (reads workspace_config.json):
      python make_gauge_rings.py

  Explicit deck, interactive prompts for the gauge:
      python make_gauge_rings.py --deck coupon_0000.rad

  Fully non-interactive:
      python make_gauge_rings.py --centre 0 0 0 --radius 6.0 --plates 1.0 -1.0 \
          --axis z --rtol 0.5 --atol 0.4 --thgroup-id 900

With no --deck, the deck comes from 'rad_target' in workspace_config.json and
the outputs are written next to it, so the .inc lands where the starter deck
can include it.

Arguments
---------
  --centre X Y Z   Hole centre, in model units. Only the two coordinates
                   perpendicular to --axis are used for the radius; the
                   along-axis value is ignored (use --plates for that).
  --radius R       Gauge ring radius from the hole axis.
  --plates A B     Along-axis coordinate of each plate's mid-surface. Two
                   values: plate 1 and plate 2.
  --axis {x,y,z}   Rivet shank axis. Default z.
  --rtol           Radial tolerance for accepting a node. Default 0.5.
  --atol           Along-axis tolerance for accepting a node. Default 0.4.
  --max-nodes N    Cap nodes per ring, spread evenly by angle. Default 8.
  --thgroup-id N   First TH group ID. Second ring uses N+1. Default 900.

Outputs
-------
  th_gauge_rings.inc    /TH/NODE cards - paste into the starter deck
  gauge_rings.json      manifest for relative_disp.py
"""

import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wsconfig
from relative_disp import RivetError

AXES = {"x": 0, "y": 1, "z": 2}
INC_NAME = "th_gauge_rings.inc"
JSON_NAME = "gauge_rings.json"


# --------------------------------------------------------------- deck parsing
def parse_nodes(path):
    """Return {node_id: (x, y, z)} from the /NODE blocks of a Radioss deck.

    Handles both fixed-width (I10 + 3F20.0) and free/whitespace-separated
    layouts, which is the usual source of grief when a deck has been through
    more than one pre-processor.
    """
    nodes = {}
    in_block = False
    with open(path, "r", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            stripped = line.strip()

            if stripped.startswith("/"):
                in_block = bool(re.match(r"^/NODE\b", stripped, re.I))
                continue
            if not in_block:
                continue
            if not stripped or stripped.startswith("#") or stripped.startswith("$"):
                continue

            rec = _parse_node_line(line)
            if rec:
                nid, xyz = rec
                nodes[nid] = xyz
    return nodes


def _parse_node_line(line):
    parts = line.split()
    if len(parts) == 4:
        try:
            return int(parts[0]), tuple(float(p) for p in parts[1:4])
        except ValueError:
            pass
    if len(line) >= 30:
        try:
            nid = int(line[0:10])
            x = float(line[10:30] or 0.0)
            y = float(line[30:50] or 0.0) if len(line) > 30 else 0.0
            z = float(line[50:70] or 0.0) if len(line) > 50 else 0.0
            return nid, (x, y, z)
        except ValueError:
            return None
    return None


# --------------------------------------------------------------- ring picking
def pick_ring(nodes, centre, radius, axis_idx, plate_coord, rtol, atol, max_nodes):
    """Nodes within rtol of `radius` from the hole axis and atol of the plate."""
    perp = [i for i in range(3) if i != axis_idx]
    hits = []
    for nid, xyz in nodes.items():
        if abs(xyz[axis_idx] - plate_coord) > atol:
            continue
        du = xyz[perp[0]] - centre[perp[0]]
        dv = xyz[perp[1]] - centre[perp[1]]
        r = math.hypot(du, dv)
        if abs(r - radius) > rtol:
            continue
        theta = math.degrees(math.atan2(dv, du)) % 360.0
        hits.append({"id": nid, "r": r, "theta": theta, "xyz": xyz})

    hits.sort(key=lambda h: h["theta"])
    if max_nodes and len(hits) > max_nodes:
        hits = _spread_by_angle(hits, max_nodes)
    return hits


def _spread_by_angle(hits, n):
    """Keep n nodes spread as evenly as possible around the ring."""
    chosen, used = [], set()
    for k in range(n):
        target = 360.0 * k / n
        best_i, best_d = None, None
        for i, h in enumerate(hits):
            if i in used:
                continue
            d = abs(((h["theta"] - target + 180.0) % 360.0) - 180.0)
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        if best_i is not None:
            used.add(best_i)
            chosen.append(hits[best_i])
    chosen.sort(key=lambda h: h["theta"])
    return chosen


def diagnose(hits, radius):
    """Warn about the failure modes that produce plausible-looking wrong data."""
    msgs = []
    if not hits:
        msgs.append("NO NODES FOUND - check the centre, axis, radius and tolerances.")
        return msgs
    rs = [h["r"] for h in hits]
    msgs.append(f"{len(hits)} nodes, radius {min(rs):.3f} to {max(rs):.3f} "
                f"(requested {radius:.3f})")
    if len(hits) < 4:
        msgs.append("WARNING: fewer than 4 nodes - averaging will be noisy. "
                    "Widen the radial tolerance or check mesh density at the hole.")
    thetas = sorted(h["theta"] for h in hits)
    gaps = [(thetas[(i + 1) % len(thetas)] - thetas[i]) % 360.0
            for i in range(len(thetas))]
    if len(thetas) > 1 and gaps and max(gaps) > 120.0:
        msgs.append(f"WARNING: largest angular gap is {max(gaps):.0f} deg - the ring "
                    "is one-sided, so the average will be biased toward that side.")
    return msgs


# --------------------------------------------------------------- card writing
def th_node_cards(rings, thgroup_id0, variables):
    """/TH/NODE/thgroup_ID / name / vars / then one line per node."""
    out = []
    out.append("#" + "-" * 79)
    out.append("# Gauge rings for relative displacement across the rivet")
    out.append("# Generated by make_gauge_rings.py - do not hand-edit node lists")
    out.append("#" + "-" * 79)
    for k, ring in enumerate(rings):
        gid = thgroup_id0 + k
        out.append(f"/TH/NODE/{gid}")
        out.append(ring["name"][:100])
        out.append(" ".join(variables))
        out.append("#  node_ID   skew_ID node_name")
        for h in ring["nodes"]:
            label = f"{ring['tag']}_th{h['theta']:05.1f}"
            out.append(f"{h['id']:>10d}{0:>10d} {label}")
    out.append("#" + "-" * 79)
    return "\n".join(out) + "\n"


# --------------------------------------------------------------- library API
def build_rings(deck, centre, radius, plates, axis="z", rtol=0.5, atol=0.4,
                max_nodes=8, thgroup_id=900, variables=("DX", "DY", "DZ"),
                outdir=None, write=True):
    """Pick both rings and (optionally) write the .inc and manifest.

    Returns a dict with: rings, diagnostics (list of (label, [msg])), inc_path,
    json_path, node_count, deck, outdir.
    Raises RivetError when the deck is unreadable or a ring comes back empty.
    """
    axis = (axis or "z").lower()
    if axis not in AXES:
        raise RivetError(f"bad axis: {axis!r} (expected x, y or z)")
    axis_idx = AXES[axis]

    if not deck or not os.path.isfile(deck):
        raise RivetError(f"deck not found: {deck}")
    if len(plates) != 2:
        raise RivetError("need exactly two plate mid-surface coordinates")

    nodes = parse_nodes(deck)
    if not nodes:
        raise RivetError(
            f"no nodes parsed from {os.path.basename(deck)}. Is there a /NODE "
            "block in this file? Some decks keep nodes in a separate include.")

    outdir = outdir or os.path.dirname(os.path.abspath(deck))
    variables = list(variables)

    rings, diagnostics = [], []
    for k, pc in enumerate(plates, start=1):
        hits = pick_ring(nodes, centre, radius, axis_idx, pc, rtol, atol, max_nodes)
        ring = {
            "tag": f"P{k}",
            "name": f"GAUGE_RING_PLATE{k}_R{radius:g}",
            "plate_coord": pc,
            "nodes": hits,
        }
        rings.append(ring)
        diagnostics.append((f"Plate {k} (at {axis} = {pc:g})", diagnose(hits, radius)))

    empty = [r["tag"] for r in rings if not r["nodes"]]
    if empty:
        detail = "; ".join(f"{lbl}: {' '.join(msgs)}" for lbl, msgs in diagnostics)
        raise RivetError(f"ring(s) {', '.join(empty)} came back empty - nothing "
                         f"written. {detail}")

    inc_path = os.path.join(outdir, INC_NAME)
    json_path = os.path.join(outdir, JSON_NAME)

    manifest = {
        "deck": os.path.abspath(deck),
        "axis": axis,
        "centre": list(centre),
        "radius": radius,
        "rtol": rtol,
        "atol": atol,
        "max_nodes": max_nodes,
        "thgroup_id": thgroup_id,
        "variables": variables,
        "rings": [
            {
                "tag": r["tag"],
                "name": r["name"],
                "thgroup_id": thgroup_id + i,
                "plate_coord": r["plate_coord"],
                "node_ids": [h["id"] for h in r["nodes"]],
                "node_theta": [round(h["theta"], 2) for h in r["nodes"]],
                "node_radius": [round(h["r"], 4) for h in r["nodes"]],
            }
            for i, r in enumerate(rings)
        ],
    }

    if write:
        os.makedirs(outdir, exist_ok=True)
        with open(inc_path, "w") as fh:
            fh.write(th_node_cards(rings, thgroup_id, variables))
        with open(json_path, "w") as fh:
            json.dump(manifest, fh, indent=2)

    return {
        "rings": rings, "diagnostics": diagnostics, "manifest": manifest,
        "inc_path": inc_path if write else None,
        "json_path": json_path if write else None,
        "node_count": len(nodes), "deck": deck, "outdir": outdir,
    }


NEXT_STEPS = [
    f"1. #include {INC_NAME} in the starter deck, or paste it in.",
    "2. Add /TH/TITLE to the engine deck so th_to_csv writes real variable names.",
    "3. Set /TFILE fine enough to resolve the force peak.",
    "4. After the run: th_to_csv, then extract the force-displacement curve.",
    "",
    "Check before trusting the result: none of these nodes should lose all their",
    "attached elements to erosion before separation. A free-flying node gives a",
    "displacement curve that looks entirely reasonable and is wrong.",
]


# --------------------------------------------------------------- CLI helpers
def ask(prompt, cast=str, default=None):
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            return cast(raw)
        except (ValueError, TypeError):
            print("  could not read that, try again")


def ask_triple(prompt, default=None):
    while True:
        suffix = f" [{' '.join(str(d) for d in default)}]" if default else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default:
            return list(default)
        parts = raw.replace(",", " ").split()
        if len(parts) == 3:
            try:
                return [float(p) for p in parts]
            except ValueError:
                pass
        print("  need three numbers, try again")


def main():
    ap = argparse.ArgumentParser(description="Build /TH/NODE gauge rings around a rivet hole.")
    ap.add_argument("deck", nargs="?", default=None,
                    help="Radioss starter deck. Omit to use rad_target from workspace_config.json.")
    ap.add_argument("--deck", dest="deck_opt", default=None, help="Same as the positional deck.")
    ap.add_argument("--config", default=None, help="Path to workspace_config.json.")
    ap.add_argument("--centre", nargs=3, type=float, metavar=("X", "Y", "Z"))
    ap.add_argument("--radius", type=float)
    ap.add_argument("--plates", nargs=2, type=float, metavar=("A", "B"))
    ap.add_argument("--axis", choices=list(AXES), default=None)
    ap.add_argument("--rtol", type=float, default=None)
    ap.add_argument("--atol", type=float, default=None)
    ap.add_argument("--max-nodes", type=int, default=None)
    ap.add_argument("--thgroup-id", type=int, default=None)
    ap.add_argument("--outdir", default=None,
                    help="Where to write the .inc and manifest. Default: beside the deck.")
    ap.add_argument("--variables", default="DX DY DZ",
                    help="TH variables. 'DEF' gives DX DY DZ VX VY VZ in one go.")
    args = ap.parse_args()

    try:
        deck = args.deck_opt or args.deck
        if not deck:
            cfg = wsconfig.load(args.config)
            deck = wsconfig.rad_target(cfg)
            print(wsconfig.summary(cfg))
            print()

        # Interactive only when a core input is missing. With centre, radius
        # and plates all supplied, everything else takes its default and the
        # script never blocks on stdin - which matters when it is driven from
        # a loop over the run matrix.
        interactive = args.centre is None or args.radius is None or args.plates is None
        if interactive:
            print("Enter the gauge definition. Units are model units throughout.")
            print("Press Enter to accept the value in brackets.\n")

        def opt(value, prompt, cast, default):
            if value is not None:
                return value
            return ask(prompt, cast, default) if interactive else default

        axis = (args.axis or (ask("Rivet shank axis (x/y/z)", str, "z")
                              if interactive else "z")).lower()
        centre = args.centre or ask_triple("Hole centre X Y Z")
        radius = args.radius if args.radius is not None else ask("Gauge ring radius", float)
        if args.plates:
            plates = list(args.plates)
        else:
            print(f"\nPlate mid-surface {axis.upper()} coordinates - the two points "
                  f"the connector will span in the hull model.")
            plates = [ask(f"  plate 1 mid-surface {axis}", float),
                      ask(f"  plate 2 mid-surface {axis}", float)]

        rtol = opt(args.rtol, "Radial tolerance", float, 0.5)
        atol = opt(args.atol, f"Along-{axis} tolerance", float, 0.4)
        max_nodes = opt(args.max_nodes, "Max nodes per ring", int, 8)
        gid0 = opt(args.thgroup_id, "First TH group ID", int, 900)

        print(f"\nReading nodes from {deck} ...")
        res = build_rings(deck, centre, radius, plates, axis=axis, rtol=rtol,
                          atol=atol, max_nodes=max_nodes, thgroup_id=gid0,
                          variables=args.variables.split(), outdir=args.outdir)
        print(f"  {res['node_count']} nodes\n")
        for label, msgs in res["diagnostics"]:
            print(f"{label}:")
            for m in msgs:
                print(f"  {m}")
            print()

        print(f"Wrote {res['inc_path']}")
        print(f"Wrote {res['json_path']}\n")
        print("Next steps:")
        for line in NEXT_STEPS:
            print(f"  {line}" if line else "")
        return 0

    except (RivetError, wsconfig.ConfigError) as e:
        sys.stderr.write(f"{e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
