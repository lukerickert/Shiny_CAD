# -*- coding: utf-8 -*-
"""Achievable surface roughness Ra by manufacturing process (guide for the Surface finish field of the drawings).

Each process has three ranges of Ra (µm): fine (careful production), usual (normal production) and rough. The usual
range is the average range of the chart "Surface roughness produced by common production methods" (ASME B46.1,
appendix); the fine and rough ranges are the less frequent ends of that chart. Processes not in that chart
(sintering, wire EDM, waterjet and laser cutting, countersinking, plunge grinding) are from manufacturer data.
These are typical values; the actual roughness depends on the material, the tool, the feed and the machine.
"""

# Ra values of ISO 1302 with the roughness grade numbers N1 .. N12
RA_SERIES = [(0.025, "N1"), (0.05, "N2"), (0.1, "N3"), (0.2, "N4"), (0.4, "N5"), (0.8, "N6"), (1.6, "N7"),
             (3.2, "N8"), (6.3, "N9"), (12.5, "N10"), (25, "N11"), (50, "N12")]
RA_FINE_END = 0.0125          # first column of the chart (below N1)

# (group, process, fine (lo, hi), usual (lo, hi), rough (lo, hi)); None: no range; values in µm Ra
PROCESSES = [
    ("Primary forming", "Sand casting", (6.3, 12.5), (12.5, 25), (25, 50)),
    ("Primary forming", "Permanent mould casting", (0.8, 1.6), (1.6, 3.2), (3.2, 6.3)),
    ("Primary forming", "Die casting", (0.4, 0.8), (0.8, 1.6), (1.6, 3.2)),
    ("Primary forming", "Investment casting", (0.4, 1.6), (1.6, 3.2), None),
    ("Primary forming", "Sintering (as sintered)", (0.4, 0.8), (0.8, 3.2), (3.2, 6.3)),
    ("Forming", "Extrusion", (0.4, 0.8), (0.8, 3.2), (3.2, 6.3)),
    ("Forming", "Forging (closed die)", (1.6, 3.2), (3.2, 12.5), (12.5, 25)),
    ("Forming", "Cold rolling, drawing", (0.2, 0.8), (0.8, 3.2), (3.2, 6.3)),
    ("Forming", "Hot rolling", (6.3, 12.5), (12.5, 25), (25, 50)),
    ("Forming", "Roller burnishing", (0.1, 0.2), (0.2, 0.4), (0.4, 0.8)),
    ("Cutting", "Flame cutting", (6.3, 12.5), (12.5, 25), (25, 50)),
    ("Cutting", "Laser cutting", (0.8, 1.6), (1.6, 6.3), (6.3, 12.5)),
    ("Cutting", "Waterjet cutting", (1.6, 3.2), (3.2, 12.5), (12.5, 25)),
    ("Cutting", "Sawing", (0.8, 1.6), (1.6, 25), (25, 50)),
    ("Cutting", "EDM sinking", (0.4, 1.6), (1.6, 6.3), (6.3, 12.5)),
    ("Cutting", "Wire EDM", (0.2, 0.8), (0.8, 3.2), (3.2, 6.3)),
    ("Machining", "Drilling", (0.8, 1.6), (1.6, 6.3), (6.3, 12.5)),
    ("Machining", "Boring", (0.4, 0.8), (0.8, 6.3), (6.3, 12.5)),
    ("Machining", "Countersinking", (0.8, 1.6), (1.6, 6.3), (6.3, 12.5)),
    ("Machining", "Reaming", (0.4, 0.8), (0.8, 3.2), (3.2, 6.3)),
    ("Machining", "Broaching", (0.4, 0.8), (0.8, 3.2), (3.2, 6.3)),
    ("Machining", "Turning", (0.1, 0.4), (0.4, 6.3), (6.3, 25)),
    ("Machining", "Facing", (0.2, 0.8), (0.8, 6.3), (6.3, 12.5)),
    ("Machining", "Milling", (0.2, 0.8), (0.8, 6.3), (6.3, 25)),
    ("Machining", "Planing, shaping", (0.4, 1.6), (1.6, 12.5), (12.5, 25)),
    ("Abrasive", "Cylindrical grinding", (0.05, 0.2), (0.2, 1.6), (1.6, 3.2)),
    ("Abrasive", "Plunge grinding", (0.1, 0.4), (0.4, 1.6), (1.6, 3.2)),
    ("Abrasive", "Surface grinding", (0.1, 0.4), (0.4, 1.6), (1.6, 6.3)),
    ("Abrasive", "Honing", (0.025, 0.1), (0.1, 0.8), (0.8, 1.6)),
    ("Abrasive", "Lapping", (0.0125, 0.05), (0.05, 0.4), (0.4, 0.8)),
    ("Abrasive", "Superfinishing", (0.0125, 0.025), (0.025, 0.2), (0.2, 0.8)),
    ("Abrasive", "Polishing", (0.0125, 0.1), (0.1, 0.4), (0.4, 0.8)),
    ("Abrasive", "Electropolishing", (0.0125, 0.1), (0.1, 0.8), (0.8, 1.6)),
]


def table():
    """Reference data for the client: {"series": [[Ra, N], ...], "processes": [{"group", "name", "fine", "usual",
    "rough"}], "note"}."""
    return {"series": [[RA_FINE_END, ""]] + [[v, n] for v, n in RA_SERIES],
            "processes": [{"group": g, "name": n, "fine": f, "usual": u, "rough": r} for g, n, f, u, r in PROCESSES],
            "note": __doc__.split("\n\n", 1)[1].strip().replace("\n", " ")}


def processes_for(ra):
    """Processes whose fine, usual or rough range includes Ra (µm): [(process, band)]."""
    out = []
    for g, n, f, u, r in PROCESSES:
        for band, rg in (("usual", u), ("fine", f), ("rough", r)):
            if rg and rg[0] - 1e-9 <= ra <= rg[1] + 1e-9:
                out.append((n, band))
                break
    return out
