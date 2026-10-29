# -*- coding: utf-8 -*-
"""Feeds and speeds: spindle speed, feed and plunge feed of a tool bit in a workpiece material, from a table of
cutting speeds and chip loads, with radial chip thinning, the effective diameter of ball end mills and V bits at
the depth of cut, the spindle limits of the machine and a cutting power check.

Material record: {"id", "name", "group", "vc": [carbide, HSS] m/min, "fz10": chip load mm/tooth of a 10 mm carbide
end mill, "kc11": specific cutting force N/mm^2 at 1 mm chip thickness, "mc": its exponent, "plunge": plunge feed
as a fraction of the feed, "fdrill": drill feed per revolution mm per mm of drill diameter}.
The chip load of diameter D: fz10 * (D / 10)^0.8, with factors for the tool shape and HSS.

Machine (setup sheet fields): "rpm_min", "rpm_max", "rpm_rated" (the spindle gives its rated power from this speed
up and constant torque below it), "power_kw", "feed_max" mm/min, "rigidity" % (the chip load scaled by it: a light
router frame or a long tool stick-out below 100), "ramp_angle" deg (the angle of ramp and helix entries the ramp feed
is given for).
Tool bit fields used: "shape", "d", "flutes", "tool_material" (carbide | hss), "coating" (COATINGS: the cutting
speed scaled by COATING_VC for the material group), "angle", "tip", "corner".

The table values are starting values for rigid set-ups; a router spindle and frame usually need them reduced."""
import math

MATERIALS = [
    # id, name, group, vc carbide, vc HSS, fz10, kc11, mc, plunge, fdrill
    ("al_wrought", "Aluminium wrought (6061, 6082)", "Aluminium", 300, 100, 0.080, 700, 0.25, 0.5, 0.025),
    ("al_7075", "Aluminium 7075", "Aluminium", 250, 80, 0.070, 800, 0.25, 0.5, 0.022),
    ("al_cast", "Aluminium cast (AlSi)", "Aluminium", 250, 80, 0.070, 750, 0.25, 0.5, 0.020),
    ("st_free", "Free-cutting steel (11SMnPb30)", "Steel", 150, 35, 0.050, 1500, 0.25, 0.3, 0.015),
    ("st_struct", "Structural steel (S235, S355)", "Steel", 120, 28, 0.045, 1700, 0.25, 0.3, 0.014),
    ("st_alloy", "Alloy steel annealed (42CrMo4)", "Steel", 100, 22, 0.040, 1900, 0.25, 0.25, 0.012),
    ("st_tool", "Tool steel annealed (1.2842, 1.2379)", "Steel", 80, 18, 0.035, 2000, 0.26, 0.25, 0.010),
    ("st_stainless", "Stainless steel (304, 316)", "Steel", 70, 15, 0.035, 2200, 0.21, 0.25, 0.010),
    ("cu_brass", "Brass (CuZn39Pb3)", "Brass and bronze", 250, 60, 0.060, 780, 0.18, 0.5, 0.020),
    ("cu_bronze", "Bronze (CuSn8, CuSn12)", "Brass and bronze", 150, 40, 0.050, 1100, 0.20, 0.4, 0.016),
    ("pl_pom", "POM (acetal)", "Plastics", 300, 150, 0.100, 150, 0.20, 0.6, 0.040),
    ("pl_pa", "PA (nylon)", "Plastics", 250, 120, 0.090, 150, 0.20, 0.6, 0.035),
    ("pl_pe", "PE, UHMW-PE", "Plastics", 300, 150, 0.120, 100, 0.20, 0.6, 0.040),
    ("pl_pmma", "PMMA (acrylic)", "Plastics", 250, 120, 0.080, 170, 0.20, 0.5, 0.030),
    ("pl_pvc", "PVC", "Plastics", 200, 100, 0.080, 150, 0.20, 0.5, 0.030),
    ("wd_hard", "Hardwood (oak, beech)", "Wood and boards", 500, 300, 0.150, 60, 0.20, 0.6, 0.050),
    ("wd_soft", "Softwood (pine, spruce)", "Wood and boards", 600, 350, 0.180, 40, 0.20, 0.6, 0.060),
    ("wd_mdf", "MDF", "Wood and boards", 500, 300, 0.180, 50, 0.20, 0.6, 0.060),
    ("wd_ply", "Plywood (birch)", "Wood and boards", 500, 300, 0.150, 55, 0.20, 0.6, 0.050),
]
_KEYS = ("id", "name", "group", "vc_carbide", "vc_hss", "fz10", "kc11", "mc", "plunge", "fdrill")
MATERIAL = {m[0]: dict(zip(_KEYS, m)) for m in MATERIALS}

DEFAULT_MACHINE = {"rpm_min": 6000.0, "rpm_max": 24000.0, "rpm_rated": 24000.0, "power_kw": 2.2, "feed_max": 5000.0,
                   "rigidity": 100.0, "ramp_angle": 3.0}
TOOL_MATERIALS = {"carbide": "Carbide", "hss": "HSS"}
COATINGS = {"none": "Uncoated", "tin": "TiN", "ticn": "TiCN", "tialn": "TiAlN", "altin": "AlTiN", "dlc": "DLC", "zrn": "ZrN"}
# cutting speed factor of a coating per material group (default for the groups not listed)
COATING_VC = {"none": {}, "tin": {"default": 1.1}, "ticn": {"default": 1.15, "Aluminium": 1.05},
              "tialn": {"default": 1.15, "Steel": 1.3, "Aluminium": 0.9, "Plastics": 1.0, "Wood and boards": 1.0},
              "altin": {"default": 1.15, "Steel": 1.4, "Aluminium": 0.8, "Plastics": 1.0, "Wood and boards": 1.0},
              "dlc": {"default": 1.0, "Aluminium": 1.25, "Plastics": 1.15, "Brass and bronze": 1.15, "Steel": 0.9},
              "zrn": {"default": 1.0, "Aluminium": 1.15, "Plastics": 1.05, "Brass and bronze": 1.1}}
# chip load and cutting speed factors of the tool shapes
SHAPE_FZ = {"endmill": 1.0, "bullnose": 1.0, "ballend": 0.8, "vbit": 0.6, "chamfer": 0.6, "dovetail": 0.5, "drill": 1.0, "tapered": 0.6, "threadmill": 0.4,
            "tslot": 0.5, "custom": 0.5}
SHAPE_VC = {"dovetail": 0.8, "drill": 0.7, "tslot": 0.8, "custom": 0.8}
EFFICIENCY = 0.8           # spindle power to cutting power
RCTF_MAX = 3.0             # largest radial chip thinning factor applied
HM_MIN = 0.008             # mm: below this mean chip thickness the edge rubs (metals)


def _f(v, default=0.0):
    try:
        return float(default) if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return float(default)


def materials():
    """[{"id", "name", "group"}] in the order of the table."""
    return [{"id": m[0], "name": m[1], "group": m[2]} for m in MATERIALS]


def machine_of(setup):
    s = setup or {}
    return {k: _f(s.get(k), v) for k, v in DEFAULT_MACHINE.items()}


def effective_diameter(bit, ap):
    """Cutting diameter at the depth of cut ap (mm): ball end mill 2 sqrt(ap (D - ap)) below D/2, V bit and chamfer
    tip + 2 ap tan(angle / 2), tapered ball nose the profile diameter at ap, else D."""
    D = _f(bit.get("d"), 6.0)
    sh = bit.get("shape") or "endmill"
    ap = max(0.0, _f(ap))
    if sh == "ballend" and 0 < ap < D / 2.0:
        return max(0.05 * D, 2.0 * math.sqrt(ap * (D - ap)))
    if sh == "tapered" and ap > 0:
        from . import tools as TB
        cut, _ = TB.tool_profile(bit)
        return min(D, max(0.05 * D, 2.0 * TB._radius_at(cut, min(ap, cut[-1][1]))))
    if sh in ("vbit", "chamfer") and ap > 0:
        a = math.radians(_f(bit.get("angle"), 90.0)) / 2.0
        return min(D, max(0.05 * D, _f(bit.get("tip"), 0.0) + 2.0 * ap * math.tan(a)))
    return D


def chip_thinning(ae, D):
    """Radial chip thinning factor 1 / sqrt(1 - (1 - 2 ae / D)^2) for ae below D / 2 (at most RCTF_MAX), else 1."""
    if D <= 0 or ae <= 0 or ae >= D / 2.0:
        return 1.0
    x = 1.0 - 2.0 * ae / D
    return min(RCTF_MAX, 1.0 / math.sqrt(max(1e-12, 1.0 - x * x)))


def calc(bit, material, setup=None, ae=None, ap=None):
    """Feeds and speeds of a tool bit in a material id (MATERIAL) for a width of cut ae and a depth of cut ap (mm;
    None: ae = D, ap = D / 2; drills: ap is the hole depth and ae is not used). Returns {"rpm", "feed", "plunge"
    (mm/min), "vc" (m/min at the effective diameter), "deff" mm, "fz" (table) and "fz_adj" (with chip thinning)
    mm/tooth, "rctf", "hm" mm (mean chip thickness), "mrr" cm^3/min, "power_kw", "power_avail_kw", "torque_nm",
    "limited": [reasons], "warnings": [texts], "ae", "ap"}."""
    m = MATERIAL.get(material)
    if m is None:
        raise ValueError("unknown material %s" % material)
    mc = machine_of(setup)
    sh = bit.get("shape") or "endmill"
    D = _f(bit.get("d"), 6.0)
    if D <= 0:
        raise ValueError("the tool diameter is 0")
    z = max(1, int(_f(bit.get("flutes"), 2) or 2))
    hss = str(bit.get("tool_material") or "carbide").lower() == "hss"
    ae = D if ae is None or _f(ae) <= 0 else min(_f(ae), D)
    ap = D / 2.0 if ap is None or _f(ap) <= 0 else _f(ap)
    warnings, limited = [], []
    coat = str(bit.get("coating") or "none").lower()
    cf = COATING_VC.get(coat, {})
    vc0 = (m["vc_hss"] if hss else m["vc_carbide"]) * SHAPE_VC.get(sh, 1.0) * cf.get(m["group"], cf.get("default", 1.0))
    rig = min(1.5, max(0.1, mc["rigidity"] / 100.0))
    deff = D if sh == "drill" else effective_diameter(bit, ap)
    n = vc0 * 1000.0 / (math.pi * deff)
    if n > mc["rpm_max"]:
        n = mc["rpm_max"]
        limited.append("rpm_max")
    if n < mc["rpm_min"]:
        n = mc["rpm_min"]
        warnings.append("the cutting speed needs %.0f rpm, below the spindle minimum %.0f rpm: the speed is raised to the minimum"
                        % (vc0 * 1000.0 / (math.pi * deff), mc["rpm_min"]))
    vc = math.pi * deff * n / 1000.0
    p_avail = mc["power_kw"] * min(1.0, n / mc["rpm_rated"]) if mc["rpm_rated"] > 0 else mc["power_kw"]
    if sh == "drill":
        fr = m["fdrill"] * D * (0.8 if hss else 1.0) * rig         # mm/rev
        feed = fr * n
        fz = fz_adj = fr / 2.0
        rctf = 1.0
        kappa = math.radians(_f(bit.get("angle"), 118.0)) / 2.0
        hm = fz * math.sin(kappa)
        mrr = math.pi * D * D / 4.0 * feed / 1000.0
    else:
        fz = m["fz10"] * (D / 10.0) ** 0.8 * SHAPE_FZ.get(sh, 1.0) * (0.8 if hss else 1.0) * rig
        rctf = chip_thinning(ae, deff)
        fz_adj = fz * rctf
        feed = fz_adj * z * n
        hm = fz_adj * math.sqrt(min(1.0, ae / deff))
        mrr = ae * ap * feed / 1000.0
    if feed > mc["feed_max"]:
        f2 = mc["feed_max"]
        hm *= f2 / feed
        fz_adj *= f2 / feed
        mrr *= f2 / feed
        feed = f2
        limited.append("feed_max")
    kc = m["kc11"] * max(hm, 1e-4) ** (-m["mc"])
    pc = mrr * kc / 60e3 / EFFICIENCY                               # kW
    if pc > p_avail > 0:
        # the feed lowered until the power fits: P ~ feed^(1 - mc) with the chip thickness proportional to the feed
        s = (p_avail / pc) ** (1.0 / (1.0 - m["mc"]))
        feed *= s
        fz_adj *= s
        hm *= s
        mrr *= s
        kc = m["kc11"] * max(hm, 1e-4) ** (-m["mc"])
        pc = mrr * kc / 60e3 / EFFICIENCY
        limited.append("power")
        warnings.append("the cutting power limits the feed (%.2f kW available at %.0f rpm): a smaller depth or width of cut keeps the chip load"
                        % (p_avail, n))
    if m["group"] in ("Steel", "Aluminium", "Brass and bronze") and hm < HM_MIN:
        warnings.append("mean chip thickness %.4f mm: below %.3f mm the edge rubs instead of cutting" % (hm, HM_MIN))
    plunge = feed if sh == "drill" else feed * m["plunge"]
    # ramp and helix entries: the feed up to 2 deg, down to the plunge feed at 15 deg
    ra = max(0.0, mc["ramp_angle"])
    k = 1.0 - min(1.0, max(0.0, (ra - 2.0) / 13.0)) * (1.0 - m["plunge"])
    ramp = feed if sh == "drill" else max(plunge, feed * k)
    torque = pc * EFFICIENCY * 60e3 / (2.0 * math.pi * n) if n > 0 else 0.0
    return {"rpm": round(n), "feed": round(feed), "plunge": round(plunge), "ramp": round(ramp), "ramp_angle": ra,
            "coating": coat, "rigidity": round(rig * 100.0, 1), "vc": round(vc, 1), "deff": round(deff, 3),
            "fz": round(fz, 4), "fz_adj": round(fz_adj, 4), "rctf": round(rctf, 3), "hm": round(hm, 4), "mrr": round(mrr, 3),
            "power_kw": round(pc, 3), "power_avail_kw": round(p_avail, 3), "torque_nm": round(torque, 3),
            "limited": limited, "warnings": warnings, "ae": round(ae, 4), "ap": round(ap, 4), "material": material,
            "tool_material": "hss" if hss else "carbide"}
