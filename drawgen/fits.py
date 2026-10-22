# -*- coding: utf-8 -*-
"""ISO 286-1/-2 limits for holes and shafts.

Standard tolerance grades IT1 to IT18 for nominal sizes up to 3150 mm. Fundamental deviations for nominal sizes up to
500 mm: shafts a, b, c, d, e, f, g, h, js, k, m, n, p, r, s, u and holes A to U (the same letters); H, h, JS and js
up to 3150 mm (they need the grade only).
"""
import re

# upper limits of the nominal size ranges (mm); a size belongs to the range (previous, limit]
RANGES_ALL = [3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150]
RANGES = RANGES_ALL[:13]

# standard tolerance grades IT1 .. IT18 (um), per range of RANGES_ALL
IT_ALL = {
    1: [0.8, 1, 1, 1.2, 1.5, 1.5, 2, 2.5, 3.5, 4.5, 6, 7, 8, 9, 10, 11, 13, 15, 18, 22, 26],
    2: [1.2, 1.5, 1.5, 2, 2.5, 2.5, 3, 4, 5, 7, 8, 9, 10, 11, 13, 15, 18, 21, 25, 30, 36],
    3: [2, 2.5, 2.5, 3, 4, 4, 5, 6, 8, 10, 12, 13, 15, 16, 18, 21, 24, 29, 35, 41, 50],
    4: [3, 4, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 33, 39, 46, 55, 68],
    5: [4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27, 32, 36, 40, 47, 55, 65, 78, 96],
    6: [6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40, 44, 50, 56, 66, 78, 92, 110, 135],
    7: [10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63, 70, 80, 90, 105, 125, 150, 175, 210],
    8: [14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97, 110, 125, 140, 165, 195, 230, 280, 330],
    9: [25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155, 175, 200, 230, 260, 310, 370, 440, 540],
    10: [40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250, 280, 320, 360, 420, 500, 600, 700, 860],
    11: [60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400, 440, 500, 560, 660, 780, 920, 1100, 1350],
    12: [100, 120, 150, 180, 210, 250, 300, 350, 400, 460, 520, 570, 630, 700, 800, 900, 1050, 1250, 1500, 1750, 2100],
    13: [140, 180, 220, 270, 330, 390, 460, 540, 630, 720, 810, 890, 970, 1100, 1250, 1400, 1650, 1950, 2300, 2800, 3300],
    14: [250, 300, 360, 430, 520, 620, 740, 870, 1000, 1150, 1300, 1400, 1550, 1750, 2000, 2300, 2600, 3100, 3700, 4400, 5400],
    15: [400, 480, 580, 700, 840, 1000, 1200, 1400, 1600, 1850, 2100, 2300, 2500, 2800, 3200, 3600, 4200, 5000, 6000, 7000, 8600],
    16: [600, 750, 900, 1100, 1300, 1600, 1900, 2200, 2500, 2900, 3200, 3600, 4000, 4400, 5000, 5600, 6600, 7800, 9200, 11000, 13500],
    17: [1000, 1200, 1500, 1800, 2100, 2500, 3000, 3500, 4000, 4600, 5200, 5700, 6300, 7000, 8000, 9000, 10500, 12500, 15000, 17500, 21000],
    18: [1400, 1800, 2200, 2700, 3300, 3900, 4600, 5400, 6300, 7200, 8100, 8900, 9700, 11000, 12500, 14000, 16500, 19500, 23000, 28000, 33000],
}
IT = {g: v[:13] for g, v in IT_ALL.items()}       # up to 500 mm (fundamental deviations)

# shaft fundamental deviations (um): upper deviation es for d..h, lower deviation ei for k..p
SHAFT_ES = {
    "d": [-20, -30, -40, -50, -65, -80, -100, -120, -145, -170, -190, -210, -230],
    "e": [-14, -20, -25, -32, -40, -50, -60, -72, -85, -100, -110, -125, -135],
    "f": [-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68],
    "g": [-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20],
    "h": [0] * 13,
}
SHAFT_EI = {
    "k": [0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5],          # IT4 to IT7; 0 for other grades
    "m": [2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23],
    "n": [4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40],
    "p": [6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68],
}
# a, b, c: upper deviation es with sub-ranges above 30 mm: (upper limit of sub-range, es)
SHAFT_ES_SUB = {
    "a": [(3, -270), (6, -270), (10, -280), (18, -290), (30, -300), (40, -310), (50, -320), (65, -340), (80, -360),
          (100, -380), (120, -410), (140, -460), (160, -520), (180, -580), (200, -660), (225, -740), (250, -820),
          (280, -920), (315, -1050), (355, -1200), (400, -1350), (450, -1500), (500, -1650)],
    "b": [(3, -140), (6, -140), (10, -150), (18, -150), (30, -160), (40, -170), (50, -180), (65, -190), (80, -200),
          (100, -220), (120, -240), (140, -260), (160, -280), (180, -310), (200, -340), (225, -380), (250, -420),
          (280, -480), (315, -540), (355, -600), (400, -680), (450, -760), (500, -840)],
    "c": [(3, -60), (6, -70), (10, -80), (18, -95), (30, -110), (40, -120), (50, -130), (65, -140), (80, -150),
          (100, -170), (120, -180), (140, -200), (160, -210), (180, -230), (200, -240), (225, -260), (250, -280),
          (280, -300), (315, -330), (355, -360), (400, -400), (450, -440), (500, -480)],
}
# r, s and u use finer subdivisions: (upper limit of sub-range, ei)
SHAFT_EI_SUB = {
    "u": [(3, 18), (6, 23), (10, 28), (14, 33), (18, 33), (24, 41), (30, 48), (40, 60), (50, 70), (65, 87),
          (80, 102), (100, 124), (120, 144), (140, 170), (160, 190), (180, 210), (200, 236), (225, 258), (250, 284),
          (280, 315), (315, 350), (355, 390), (400, 435), (450, 490), (500, 540)],
    "r": [(3, 10), (6, 15), (10, 19), (18, 23), (30, 28), (50, 34), (65, 41), (80, 43), (100, 51), (120, 54),
          (140, 63), (160, 65), (180, 68), (200, 77), (225, 80), (250, 84), (280, 94), (315, 98), (355, 108),
          (400, 114), (450, 126), (500, 132)],
    "s": [(3, 14), (6, 19), (10, 23), (18, 28), (30, 35), (50, 43), (65, 53), (80, 59), (100, 71), (120, 79),
          (140, 92), (160, 100), (180, 108), (200, 122), (225, 130), (250, 140), (280, 158), (315, 170),
          (355, 190), (400, 208), (450, 232), (500, 252)],
}

HOLE_CLASSES = ["C11", "D9", "D10", "E9", "F7", "F8", "G7", "H6", "H7", "H8", "H9", "H11", "JS7", "K7", "M7", "N7",
                "P7", "R7", "S7", "U7"]
SHAFT_CLASSES = ["c11", "d9", "e8", "f7", "g6", "h6", "h7", "h9", "h11", "js6", "k6", "m6", "n6", "p6", "r6", "s6",
                 "u6"]
SHAFT_LETTERS = ["a", "b", "c", "d", "e", "f", "g", "h", "js", "k", "m", "n", "p", "r", "s", "u"]

# preferred fits (ISO 286-2 / ISO 1829 selection), hole basis and shaft basis: (hole, shaft, description)
PREFERRED = [
    ("H11", "c11", "loose running"), ("H9", "d9", "free running"), ("H8", "f7", "close running"),
    ("H7", "g6", "sliding"), ("H7", "h6", "locational clearance"), ("H7", "k6", "locational transition"),
    ("H7", "n6", "locational transition"), ("H7", "p6", "locational interference"), ("H7", "s6", "medium drive"),
    ("H7", "u6", "force"),
    ("C11", "h11", "loose running"), ("D9", "h9", "free running"), ("F8", "h7", "close running"),
    ("G7", "h6", "sliding"), ("H7", "h6", "locational clearance"), ("K7", "h6", "locational transition"),
    ("N7", "h6", "locational transition"), ("P7", "h6", "locational interference"), ("S7", "h6", "medium drive"),
    ("U7", "h6", "force"),
]


def _index(size, limit=500):
    if size <= 0 or size > limit:
        raise ValueError("ISO 286 range is 0 to %g mm%s" % (limit, " for this letter" if limit == 500 else ""))
    for i, lim in enumerate(RANGES_ALL):
        if size <= lim:
            return i
    raise ValueError("size out of range")


def it_um(grade, size):
    """Standard tolerance IT<grade> (um) for a nominal size up to 3150 mm."""
    if grade not in IT_ALL:
        raise ValueError("grades IT1 to IT18")
    return IT_ALL[grade][_index(size, 3150)]


def _sub(table, size):
    for lim, v in table:
        if size <= lim:
            return v
    raise ValueError("size out of range")


def _shaft(letter, grade, size):
    """(es, ei) in um for a shaft."""
    if letter in ("h", "js"):
        it = it_um(grade, size)
        return (it / 2.0, -it / 2.0) if letter == "js" else (0, -it)
    i = _index(size)
    it = IT[grade][i]
    if letter in SHAFT_ES_SUB:
        es = _sub(SHAFT_ES_SUB[letter], size)
        return es, es - it
    if letter in SHAFT_ES:
        es = SHAFT_ES[letter][i]
        return es, es - it
    if letter == "k":
        ei = SHAFT_EI["k"][i] if 4 <= grade <= 7 else 0
    elif letter in SHAFT_EI:
        ei = SHAFT_EI[letter][i]
    elif letter in SHAFT_EI_SUB:
        ei = _sub(SHAFT_EI_SUB[letter], size)
    else:
        raise ValueError("unsupported shaft letter: %s" % letter)
    return ei + it, ei


def _hole(letter, grade, size):
    """(ES, EI) in um for a hole."""
    s = letter.lower()
    if s in ("h", "js"):
        it = it_um(grade, size)
        return (it / 2.0, -it / 2.0) if s == "js" else (it, 0)
    i = _index(size)
    it = IT[grade][i]
    if s in SHAFT_ES_SUB:
        ei_h = -_sub(SHAFT_ES_SUB[s], size)
        return ei_h + it, ei_h
    if s in SHAFT_ES:
        ei_h = -SHAFT_ES[s][i]                   # EI = -es
        return ei_h + it, ei_h
    # J..ZC: ES = -ei, with the delta rule for K, M, N up to IT8 and P..ZC up to IT7
    if s == "k":
        ei = SHAFT_EI["k"][i] if grade <= 8 else 0
    elif s in SHAFT_EI:
        ei = SHAFT_EI[s][i]
    elif s in SHAFT_EI_SUB:
        ei = _sub(SHAFT_EI_SUB[s], size)
    else:
        raise ValueError("unsupported hole letter: %s" % letter)
    delta = IT[grade][i] - IT[grade - 1][i] if grade - 1 in IT else 0
    if s in ("k", "m", "n") and grade <= 8:
        es_h = -ei + delta
    elif s in ("p", "r", "s", "u") and grade <= 7:
        es_h = -ei + delta
    elif s == "n" and grade > 8:
        es_h = 0
    elif s == "k" and grade > 8:
        es_h = 0
    else:
        es_h = -ei
    return es_h, es_h - it


def limits(size, cls):
    """Deviations (upper, lower) in mm for a tolerance class such as 'H7' or 'g6'."""
    m = re.match(r"^\s*([A-Za-z]{1,2})\s*(\d{1,2})\s*$", cls or "")
    if not m:
        raise ValueError("tolerance class format is letter + grade, for example H7 or g6")
    letter, grade = m.group(1), int(m.group(2))
    if grade not in IT_ALL:
        raise ValueError("supported grades: IT1 to IT18")
    if letter.isupper() or letter == "JS":
        up, lo = _hole(letter, grade, float(size))
    else:
        up, lo = _shaft(letter.lower(), grade, float(size))
    return up / 1000.0, lo / 1000.0


def fmt_dev(v):
    """Deviation text: 0, +0.021, -0.007."""
    if abs(v) < 1e-9:
        return "0"
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return ("+" + s) if v > 0 else s


def fmt_dev_um(v):
    """Deviation text in µm from a deviation in mm: 0, +27, -40, +2.5."""
    um = round(v * 1000.0, 1)
    if abs(um) < 0.05:
        return "0"
    s = ("%.1f" % abs(um)).rstrip("0").rstrip(".")
    return ("+" if um > 0 else "-") + s


def fit(size, hole, shaft):
    """Fit of a hole class and a shaft class at a nominal size (mm): deviations, limit sizes, clearances (mm;
    negative clearance is interference) and the kind of fit."""
    size = float(size)
    hu, hl = limits(size, hole)
    su, sl = limits(size, shaft)
    cmax, cmin = hu - sl, hl - su
    kind = "clearance" if cmin >= -1e-12 else "interference" if cmax <= 1e-12 else "transition"
    return {"size": size, "hole": hole, "shaft": shaft, "hole_upper": hu, "hole_lower": hl, "shaft_upper": su,
            "shaft_lower": sl, "hole_max": size + hu, "hole_min": size + hl, "shaft_max": size + su,
            "shaft_min": size + sl, "clearance_max": cmax, "clearance_min": cmin, "kind": kind,
            "hole_it": hu - hl, "shaft_it": su - sl}


def tables():
    """Reference data: ranges, IT grades, class lists, shaft letters, preferred fits."""
    return {"ranges": RANGES_ALL, "it": {str(g): v for g, v in IT_ALL.items()}, "holes": HOLE_CLASSES,
            "shafts": SHAFT_CLASSES, "letters": SHAFT_LETTERS,
            "preferred": [{"hole": h, "shaft": sh, "text": t} for h, sh, t in PREFERRED]}
