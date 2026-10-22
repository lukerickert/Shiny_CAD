"""Fastener and thread reference data: metric ISO threads (ISO 68-1, ISO 261, ISO 262), thread tolerances
(ISO 965-1, tolerance classes), metric trapezoidal threads (ISO 2904 / DIN 103), clearance holes (ISO 273),
counterbores for socket head cap screws (DIN 974-1) and countersinks (DIN 74, ISO 15065).
Dimensions in mm. Tolerance values in mm (tables in micrometres converted)."""
import math

# --------------------------------------------------------------------------- metric ISO threads

# ISO 261 coarse pitches (series 1 and the common series 2 sizes)
COARSE = [(1, 0.25), (1.2, 0.25), (1.4, 0.3), (1.6, 0.35), (2, 0.4), (2.5, 0.45), (3, 0.5), (3.5, 0.6), (4, 0.7),
          (5, 0.8), (6, 1), (7, 1), (8, 1.25), (10, 1.5), (12, 1.75), (14, 2), (16, 2), (18, 2.5), (20, 2.5),
          (22, 2.5), (24, 3), (27, 3), (30, 3.5), (33, 3.5), (36, 4), (39, 4), (42, 4.5), (45, 4.5), (48, 5),
          (52, 5), (56, 5.5), (60, 5.5), (64, 6)]

# ISO 262 fine pitches (selected sizes for screws and machine parts)
FINE = [(3, 0.35), (4, 0.5), (5, 0.5), (6, 0.75), (8, 1), (8, 0.75), (10, 1.25), (10, 1), (10, 0.75), (12, 1.5),
        (12, 1.25), (12, 1), (14, 1.5), (14, 1.25), (16, 1.5), (16, 1), (18, 2), (18, 1.5), (20, 2), (20, 1.5),
        (20, 1), (22, 2), (22, 1.5), (24, 2), (24, 1.5), (27, 2), (27, 1.5), (30, 3), (30, 2), (30, 1.5),
        (33, 2), (36, 3), (36, 2), (39, 3), (42, 3), (42, 2), (45, 3), (48, 3), (48, 2), (52, 4), (56, 4),
        (60, 4), (64, 4)]


# tap drills for coarse threads (DIN 336); fine threads: d - P rounded to 0.1 mm
TAP_DRILL = {(1, 0.25): 0.75, (1.2, 0.25): 0.95, (1.4, 0.3): 1.1, (1.6, 0.35): 1.25, (2, 0.4): 1.6, (2.5, 0.45): 2.05,
             (3, 0.5): 2.5, (3.5, 0.6): 2.9, (4, 0.7): 3.3, (5, 0.8): 4.2, (6, 1): 5.0, (7, 1): 6.0, (8, 1.25): 6.8,
             (10, 1.5): 8.5, (12, 1.75): 10.2, (14, 2): 12.0, (16, 2): 14.0, (18, 2.5): 15.5, (20, 2.5): 17.5,
             (22, 2.5): 19.5, (24, 3): 21.0, (27, 3): 24.0, (30, 3.5): 26.5, (33, 3.5): 29.5, (36, 4): 32.0,
             (39, 4): 35.0, (42, 4.5): 37.5, (45, 4.5): 40.5, (48, 5): 43.0, (52, 5): 47.0, (56, 5.5): 50.5,
             (60, 5.5): 54.5, (64, 6): 58.0}

# bearing lock nut threads (KM nuts, DIN 981 / ISO 2982-2): (d, P, KM number)
BEARING = [(10, 0.75, "KM 0"), (12, 1, "KM 1"), (15, 1, "KM 2"), (17, 1, "KM 3"), (20, 1, "KM 4"), (25, 1.5, "KM 5"),
           (30, 1.5, "KM 6"), (35, 1.5, "KM 7"), (40, 1.5, "KM 8"), (45, 1.5, "KM 9"), (50, 1.5, "KM 10"),
           (55, 2, "KM 11"), (60, 2, "KM 12"), (65, 2, "KM 13"), (70, 2, "KM 14"), (75, 2, "KM 15"), (80, 2, "KM 16"),
           (85, 2, "KM 17"), (90, 2, "KM 18"), (95, 2, "KM 19"), (100, 2, "KM 20"), (105, 2, "KM 21"), (110, 2, "KM 22"),
           (115, 2, "KM 23"), (120, 2, "KM 24"), (125, 2, "KM 25"), (130, 2, "KM 26"), (140, 2, "KM 28"),
           (150, 2, "KM 30"), (160, 3, "KM 32"), (170, 3, "KM 34"), (180, 3, "KM 36"), (190, 3, "KM 38"),
           (200, 3, "KM 40")]


def metric_profile(d, P):
    """Nominal dimensions of a metric ISO thread (ISO 68-1): pitch diameter, minor diameters, thread depths,
    root radius, tap drill (D1 rounded to 0.05 mm as in DIN 336), tensile stress area."""
    H = 0.866025 * P
    d2 = d - 0.649519 * P
    d3 = d - 1.226869 * P
    D1 = d - 1.082532 * P
    h3 = 0.613435 * P
    H1 = 0.541266 * P
    ds = (d2 + d3) / 2.0
    return {"d": d, "P": P, "H": round(H, 4), "d2": round(d2, 3), "d3": round(d3, 3), "D1": round(D1, 3),
            "h3": round(h3, 3), "H1": round(H1, 3), "R": round(H / 6.0, 3), "Rmin": round(0.125 * P, 3),
            "drill": TAP_DRILL.get((d, P), round(d - P + 1e-9, 1)), "As": round(math.pi / 4.0 * ds * ds, 1),
            "name": "M%s" % _n(d) + ("" if (d, P) in COARSE else "x%s" % _n(P))}


def _n(v):
    return ("%g" % v)


# ISO 965-1 tolerances, grade 6, in micrometres. Td: major diameter of the external thread, by pitch.
TD_6 = {0.2: 56, 0.25: 67, 0.3: 75, 0.35: 85, 0.4: 95, 0.45: 100, 0.5: 106, 0.6: 125, 0.7: 140, 0.75: 140,
        0.8: 150, 1: 180, 1.25: 212, 1.5: 236, 1.75: 265, 2: 280, 2.5: 335, 3: 375, 3.5: 425, 4: 475, 4.5: 500,
        5: 530, 5.5: 560, 6: 600}
# TD1: minor diameter of the internal thread, by pitch
TD1_6 = {0.5: 140, 0.6: 160, 0.7: 180, 0.75: 190, 0.8: 200, 1: 236, 1.25: 265, 1.5: 300, 1.75: 335, 2: 375,
         2.5: 450, 3: 500, 3.5: 560, 4: 600, 4.5: 670, 5: 710, 5.5: 750, 6: 800}
# TD2: pitch diameter of the internal thread, by diameter range (over, up to) and pitch
TD2_6 = [
    ((1.4, 2.8), {0.25: 56, 0.35: 67, 0.4: 71, 0.45: 75}),
    ((2.8, 5.6), {0.35: 85, 0.5: 100, 0.6: 112, 0.7: 118, 0.75: 125, 0.8: 125}),
    ((5.6, 11.2), {0.75: 118, 1: 150, 1.25: 160, 1.5: 180}),
    ((11.2, 22.4), {1: 160, 1.25: 180, 1.5: 190, 1.75: 200, 2: 212, 2.5: 224}),
    ((22.4, 45), {1: 170, 1.5: 200, 2: 224, 3: 265, 3.5: 280, 4: 300, 4.5: 315}),
    ((45, 90), {1.5: 212, 2: 236, 3: 280, 4: 315, 5: 335, 5.5: 355, 6: 375}),
    ((90, 180), {2: 250, 3: 300, 4: 335, 6: 400}),
    ((180, 355), {3: 335, 4: 355, 6: 425}),
]
# Td2: pitch diameter of the external thread
Td2_6 = [
    ((1.4, 2.8), {0.25: 42, 0.35: 50, 0.4: 53, 0.45: 56}),
    ((2.8, 5.6), {0.35: 64, 0.5: 75, 0.6: 85, 0.7: 90, 0.75: 95, 0.8: 95}),
    ((5.6, 11.2), {0.75: 90, 1: 112, 1.25: 118, 1.5: 132}),
    ((11.2, 22.4), {1: 118, 1.25: 132, 1.5: 140, 1.75: 150, 2: 160, 2.5: 170}),
    ((22.4, 45), {1: 125, 1.5: 150, 2: 170, 3: 200, 3.5: 212, 4: 224, 4.5: 236}),
    ((45, 90), {1.5: 160, 2: 180, 3: 212, 4: 236, 5: 250, 5.5: 265, 6: 280}),
    ((90, 180), {2: 190, 3: 224, 4: 250, 6: 300}),
    ((180, 355), {3: 250, 4: 265, 6: 315}),
]
GRADE_FACTOR = {4: 0.63, 5: 0.8, 6: 1.0, 7: 1.25, 8: 1.6}


def _range_value(table, d, P):
    for (lo, hi), vals in table:
        if lo < d <= hi:
            return vals.get(P)
    return None


# fundamental deviation of the positions G (+) and g (-) in micrometres by pitch (ISO 965-1, table 3)
DEV_G = {0.5: 20, 0.6: 21, 0.7: 22, 0.75: 22, 0.8: 24, 1: 26, 1.25: 28, 1.5: 32, 1.75: 34, 2: 38, 2.5: 42, 3: 48,
         3.5: 53, 4: 60, 4.5: 63, 5: 71, 5.5: 75, 6: 80}


def _dev(pos, P):
    """Fundamental deviation (micrometres) of a tolerance position. G and g from the table of ISO 965-1; e and f
    from the formulas es = -(50 + 11 P) and es = -(30 + 11 P)."""
    if pos in ("H", "h"):
        return 0.0
    if pos == "e":
        return -(50 + 11 * P)
    if pos == "f":
        return -(30 + 11 * P)
    g = DEV_G.get(P, 15 + 11 * P)
    return g if pos == "G" else -g


def tolerance(d, P, cls):
    """Limits of a metric thread for a tolerance class, e.g. "6H" (internal) or "6g" (external): dict with
    the limits of D2/D1 (internal) or d/d2/d3 (external) in mm, or None when the tables do not cover the size."""
    cls = cls.strip()
    if len(cls) < 2 or not cls[0].isdigit():
        return None
    grade = int(cls[0])
    pos = cls[1:]
    fac = GRADE_FACTOR.get(grade)
    if fac is None or P < 0.5:
        return None
    pr = metric_profile(d, P)
    internal = pos.isupper()
    out = {"class": cls, "name": pr["name"], "internal": internal}
    if internal:
        if pos not in ("H", "G"):
            return None
        EI = _dev(pos, P) / 1000.0
        TD2 = _range_value(TD2_6, d, P)
        TD1 = TD1_6.get(P)
        if TD2 is None or TD1 is None:
            return None
        TD2 = TD2 * fac / 1000.0
        TD1 = TD1 * fac / 1000.0
        out.update({"D2_min": round(pr["d2"] + EI, 3), "D2_max": round(pr["d2"] + EI + TD2, 3),
                    "D1_min": round(pr["D1"] + EI, 3), "D1_max": round(pr["D1"] + EI + TD1, 3),
                    "D_min": round(d + EI, 3)})
    else:
        if pos not in ("h", "g", "e", "f"):
            return None
        es = _dev(pos, P) / 1000.0
        Td = TD_6.get(P)
        Td2 = _range_value(Td2_6, d, P)
        if Td is None or Td2 is None:
            return None
        Td = Td * fac / 1000.0
        Td2 = Td2 * fac / 1000.0
        d2max = pr["d2"] + es
        d2min = d2max - Td2
        out.update({"d_max": round(d + es, 3), "d_min": round(d + es - Td, 3),
                    "d2_max": round(d2max, 3), "d2_min": round(d2min, 3),
                    "d3_max": round(pr["d3"] + es, 3), "d3_min": round(d2min - 0.616 * P, 3)})
    out["derived"] = grade != 6
    return out


def metric_table(series):
    rows = []
    items = COARSE if series == "coarse" else FINE if series == "fine" else [(d, P) for d, P, _ in BEARING]
    for i, (d, P) in enumerate(items):
        r = metric_profile(d, P)
        if series == "bearing":
            r["name"] = "M%sx%s" % (_n(d), _n(P))
            r["nut"] = BEARING[i][2]
        r["t6H"] = tolerance(d, P, "6H")
        r["t6g"] = tolerance(d, P, "6g")
        rows.append(r)
    return rows


# --------------------------------------------------------------------------- unified and pipe threads

# Unified threads ASME B1.1: (designation, major diameter mm, threads per inch)
UNC = [("#1-64 UNC", 1.854, 64), ("#2-56 UNC", 2.184, 56), ("#3-48 UNC", 2.515, 48), ("#4-40 UNC", 2.845, 40),
       ("#5-40 UNC", 3.175, 40), ("#6-32 UNC", 3.505, 32), ("#8-32 UNC", 4.166, 32), ("#10-24 UNC", 4.826, 24),
       ("#12-24 UNC", 5.486, 24), ("1/4-20 UNC", 6.35, 20), ("5/16-18 UNC", 7.938, 18), ("3/8-16 UNC", 9.525, 16),
       ("7/16-14 UNC", 11.112, 14), ("1/2-13 UNC", 12.7, 13), ("9/16-12 UNC", 14.288, 12), ("5/8-11 UNC", 15.875, 11),
       ("3/4-10 UNC", 19.05, 10), ("7/8-9 UNC", 22.225, 9), ("1-8 UNC", 25.4, 8), ("1 1/8-7 UNC", 28.575, 7),
       ("1 1/4-7 UNC", 31.75, 7), ("1 3/8-6 UNC", 34.925, 6), ("1 1/2-6 UNC", 38.1, 6), ("1 3/4-5 UNC", 44.45, 5),
       ("2-4.5 UNC", 50.8, 4.5)]
UNF = [("#0-80 UNF", 1.524, 80), ("#1-72 UNF", 1.854, 72), ("#2-64 UNF", 2.184, 64), ("#3-56 UNF", 2.515, 56),
       ("#4-48 UNF", 2.845, 48), ("#5-44 UNF", 3.175, 44), ("#6-40 UNF", 3.505, 40), ("#8-36 UNF", 4.166, 36),
       ("#10-32 UNF", 4.826, 32), ("#12-28 UNF", 5.486, 28), ("1/4-28 UNF", 6.35, 28), ("5/16-24 UNF", 7.938, 24),
       ("3/8-24 UNF", 9.525, 24), ("7/16-20 UNF", 11.112, 20), ("1/2-20 UNF", 12.7, 20), ("9/16-18 UNF", 14.288, 18),
       ("5/8-18 UNF", 15.875, 18), ("3/4-16 UNF", 19.05, 16), ("7/8-14 UNF", 22.225, 14), ("1-12 UNF", 25.4, 12),
       ("1 1/8-12 UNF", 28.575, 12), ("1 1/4-12 UNF", 31.75, 12), ("1 1/2-12 UNF", 38.1, 12)]

# Pipe threads ISO 228-1 (G, BSPP, Whitworth 55 deg): (designation, major d, threads per inch, pitch diameter d2,
# minor diameter d1)
BSPP = [("G1/16", 7.723, 28, 7.142, 6.561), ("G1/8", 9.728, 28, 9.147, 8.566), ("G1/4", 13.157, 19, 12.301, 11.445),
        ("G3/8", 16.662, 19, 15.806, 14.950), ("G1/2", 20.955, 14, 19.793, 18.631), ("G5/8", 22.911, 14, 21.749, 20.587),
        ("G3/4", 26.441, 14, 25.279, 24.117), ("G7/8", 30.201, 14, 29.039, 27.877), ("G1", 33.249, 11, 31.770, 30.291),
        ("G1 1/8", 37.897, 11, 36.418, 34.939), ("G1 1/4", 41.910, 11, 40.431, 38.952), ("G1 1/2", 47.803, 11, 46.324, 44.845),
        ("G1 3/4", 53.746, 11, 52.267, 50.788), ("G2", 59.614, 11, 58.135, 56.656), ("G2 1/2", 75.184, 11, 73.705, 72.226),
        ("G3", 87.884, 11, 86.405, 84.926)]


def unified_profile(name, d, tpi):
    """Unified thread (60 deg, the same basic profile as ISO 68-1): pitch in mm, pitch and minor diameters, depths."""
    P = 25.4 / tpi
    pr = metric_profile(d, P)
    pr["name"] = name
    pr["tpi"] = tpi
    pr["P"] = round(P, 4)
    pr["drill"] = round(d - P + 1e-9, 1)
    return pr


def unified_table(series):
    return [unified_profile(n, d, tpi) for n, d, tpi in (UNC if series == "unc" else UNF)]


def bspp_profile(name, d, tpi, d2, d1):
    """Pipe thread G (ISO 228-1, Whitworth form, 55 deg): h = 0.6403 P, r = 0.1373 P."""
    P = 25.4 / tpi
    return {"name": name, "d": d, "tpi": tpi, "P": round(P, 4), "d2": d2, "d1": d1, "h": round(0.640327 * P, 3),
            "r": round(0.137329 * P, 3), "drill": round(d1 + 1e-9, 1)}


def bspp_table():
    return [bspp_profile(*row) for row in BSPP]


def find_unified(name):
    key = name.upper().replace(" ", "")
    for n, d, tpi in UNC + UNF:
        if n.upper().replace(" ", "") == key:
            return unified_profile(n, d, tpi)
    return None


def find_bspp(name):
    key = name.upper().replace(" ", "")
    for row in BSPP:
        if row[0].upper().replace(" ", "") == key:
            return bspp_profile(*row)
    return None


# --------------------------------------------------------------------------- trapezoidal threads

# ISO 2904 preferred combinations d x P (series 1 and 2)
TRAPEZOIDAL = [(8, 1.5), (10, 2), (12, 3), (14, 3), (16, 4), (18, 4), (20, 4), (22, 5), (24, 5), (26, 5), (28, 5),
               (30, 6), (32, 6), (34, 6), (36, 6), (38, 7), (40, 7), (42, 7), (44, 7), (46, 8), (48, 8), (50, 8),
               (52, 8), (55, 9), (60, 9), (65, 10), (70, 10), (75, 10), (80, 10), (85, 12), (90, 12), (95, 12),
               (100, 12), (110, 12), (120, 14), (130, 14), (140, 14), (150, 16), (160, 16), (170, 16), (180, 18),
               (190, 18), (200, 18)]


def trapezoidal_profile(d, P):
    """Nominal dimensions of a metric trapezoidal thread (ISO 2904 / DIN 103-1)."""
    ac = 0.15 if P <= 1.5 else 0.25 if P <= 5 else 0.5 if P <= 12 else 1.0
    h3 = 0.5 * P + ac
    return {"name": "Tr%sx%s" % (_n(d), _n(P)), "d": d, "P": P, "ac": ac, "d2": round(d - 0.5 * P, 3),
            "d3": round(d - 2 * h3, 3), "D1": round(d - P, 3), "D4": round(d + 2 * ac, 3), "h3": round(h3, 3),
            "H1": round(0.5 * P, 3), "b": round(0.366 * P - 0.54 * ac, 3), "R1max": round(0.5 * ac, 3),
            "R2max": round(ac, 3)}


def trapezoidal_table():
    return [trapezoidal_profile(d, P) for d, P in TRAPEZOIDAL]


# --------------------------------------------------------------------------- holes for screws

# ISO 273 clearance holes: d -> (fine H12, medium H13, coarse H14)
CLEARANCE = {1: (1.1, 1.2, 1.3), 1.2: (1.3, 1.4, 1.5), 1.4: (1.5, 1.6, 1.8), 1.6: (1.7, 1.8, 2), 2: (2.2, 2.4, 2.6),
             2.5: (2.7, 2.9, 3.1), 3: (3.2, 3.4, 3.6), 3.5: (3.7, 3.9, 4.2), 4: (4.3, 4.5, 4.8), 5: (5.3, 5.5, 5.8),
             6: (6.4, 6.6, 7), 7: (7.4, 7.6, 8), 8: (8.4, 9, 10), 10: (10.5, 11, 12), 12: (13, 13.5, 14.5),
             14: (15, 15.5, 16.5), 16: (17, 17.5, 18.5), 18: (19, 20, 21), 20: (21, 22, 24), 22: (23, 24, 26),
             24: (25, 26, 28), 27: (28, 30, 33), 30: (31, 33, 35), 33: (34, 36, 38), 36: (37, 39, 42),
             39: (40, 42, 45), 42: (43, 45, 48), 45: (46, 48, 52), 48: (50, 52, 56), 52: (54, 56, 62),
             56: (58, 62, 66), 60: (62, 66, 70), 64: (66, 70, 74)}

# DIN 974-1 counterbores for socket head cap screws, row 1 (no washer): d -> (counterbore dia d1 H13,
# depth t for ISO 4762, depth t for DIN 7984 low head). Through hole: ISO 273 medium.
COUNTERBORE = {3: (6.5, 3.4, 2.4), 4: (8, 4.4, 3.2), 5: (10, 5.4, 3.9), 6: (11, 6.4, 4.4), 8: (15, 8.6, 5.6),
               10: (18, 10.6, 6.6), 12: (20, 12.6, 7.6), 16: (26, 16.6, 9.6), 20: (33, 20.6, 11.6),
               24: (40, 24.8, 13.8), 30: (50, 31.0, None), 36: (58, 37.0, None)}

# DIN 74 form F countersinks (90 deg) for countersunk socket head screws ISO 10642: d -> (through hole d1 H13,
# countersink dia d2 H13, depth t1)
COUNTERSINK_F = {3: (3.4, 6.9, 1.8), 4: (4.5, 9.2, 2.3), 5: (5.5, 11.5, 3.0), 6: (6.6, 13.7, 3.6),
                 8: (9, 18.3, 4.6), 10: (11, 22.7, 5.9), 12: (13.5, 27.2, 6.9), 14: (15.5, 31.2, 7.8),
                 16: (17.5, 34.0, 8.2), 20: (22, 40.7, 9.4)}

# ISO 15065 countersinks (90 deg) for countersunk screws with ISO 7721 head (slotted, cross recess):
# d -> (through hole d1, countersink dia d2 min, depth t1)
COUNTERSINK_ISO15065 = {1.6: (1.8, 3.6, 1.0), 2: (2.4, 4.4, 1.1), 2.5: (2.9, 5.5, 1.4), 3: (3.4, 6.3, 1.6),
                        3.5: (3.9, 8.2, 2.3), 4: (4.5, 9.4, 2.6), 5: (5.5, 10.4, 2.6), 6: (6.6, 12.6, 3.1),
                        8: (9, 17.3, 4.3), 10: (11, 20, 4.7)}


def hole_table():
    rows = []
    for d in sorted(set(CLEARANCE) | set(COUNTERBORE) | set(COUNTERSINK_F)):
        cl = CLEARANCE.get(d)
        cb = COUNTERBORE.get(d)
        cs = COUNTERSINK_F.get(d)
        ci = COUNTERSINK_ISO15065.get(d)
        P = dict(COARSE).get(d)
        rows.append({"d": d, "name": "M%s" % _n(d), "P": P,
                     "drill": metric_profile(d, P)["drill"] if P else None,
                     "fine": cl[0] if cl else None, "medium": cl[1] if cl else None, "coarse": cl[2] if cl else None,
                     "cb_dia": cb[0] if cb else None, "cb_depth": cb[1] if cb else None,
                     "cb_depth_low": cb[2] if cb else None,
                     "cs_dia": cs[1] if cs else None, "cs_depth": cs[2] if cs else None,
                     "cs15065_dia": ci[1] if ci else None, "cs15065_depth": ci[2] if ci else None})
    return rows


def hole_presets():
    """Presets for the Hole feature: [{id, label, d, dia, cbore_dia, cbore_depth, csink_dia, csink_angle,
    thread, tol}]."""
    out = []
    for d, P in COARSE:
        if d < 1.6 or d > 64:
            continue
        name = "M%s" % _n(d)
        cl = CLEARANCE.get(d)
        pr = metric_profile(d, P)
        out.append({"id": "tap_%s" % _n(d), "group": "Tapped hole (coarse, 6H)", "label": "%s tapped, drill %s" % (name, pr["drill"]),
                    "d": d, "dia": pr["drill"], "thread": name, "tol": "6H"})
        if cl:
            for i, ser in enumerate(("fine", "medium", "coarse")):
                out.append({"id": "cl_%s_%s" % (ser, _n(d)), "group": "Clearance hole ISO 273 %s" % ser,
                            "label": "%s clearance %s: %s" % (name, ser, _n(cl[i])), "d": d, "dia": cl[i]})
        cb = COUNTERBORE.get(d)
        if cb and cl:
            out.append({"id": "cb_%s" % _n(d), "group": "Counterbore for ISO 4762 socket head cap screw (DIN 974-1)",
                        "label": "%s: hole %s, counterbore %s x %s deep" % (name, _n(cl[1]), _n(cb[0]), _n(cb[1])),
                        "d": d, "dia": cl[1], "cbore_dia": cb[0], "cbore_depth": cb[1]})
            if cb[2]:
                out.append({"id": "cbl_%s" % _n(d), "group": "Counterbore for DIN 7984 low head screw (DIN 974-1)",
                            "label": "%s: hole %s, counterbore %s x %s deep" % (name, _n(cl[1]), _n(cb[0]), _n(cb[2])),
                            "d": d, "dia": cl[1], "cbore_dia": cb[0], "cbore_depth": cb[2]})
        cs = COUNTERSINK_F.get(d)
        if cs:
            out.append({"id": "cs_%s" % _n(d), "group": "Countersink 90 deg for ISO 10642 countersunk socket screw (DIN 74 F)",
                        "label": "%s: hole %s, countersink %s x 90 deg" % (name, _n(cs[0]), _n(cs[1])),
                        "d": d, "dia": cs[0], "csink_dia": cs[1], "csink_angle": 90})
        ci = COUNTERSINK_ISO15065.get(d)
        if ci:
            out.append({"id": "csi_%s" % _n(d), "group": "Countersink 90 deg for ISO 7721 head screws (ISO 15065)",
                        "label": "%s: hole %s, countersink %s x 90 deg" % (name, _n(ci[0]), _n(ci[1])),
                        "d": d, "dia": ci[0], "csink_dia": ci[1], "csink_angle": 90})
    return out


def reference():
    return {"coarse": metric_table("coarse"), "fine": metric_table("fine"), "bearing": metric_table("bearing"),
            "trapezoidal": trapezoidal_table(), "unc": unified_table("unc"), "unf": unified_table("unf"), "bspp": bspp_table(),
            "holes": hole_table(), "presets": hole_presets(),
            "classes": {"internal": ["4H", "5H", "6H", "7H", "6G"], "external": ["4h", "6h", "6g", "6e", "8g"]}}
