# -*- coding: utf-8 -*-
"""Program options (config.json "options") and the number formats of the drawing units.

units: "mm" (default) or "inch". The model is always in mm; only the text on the drawings changes.
  mm:   dimensions 0.001 mm with trailing zeros removed, deviations in µm (+27, -40, 0)
  inch: dimensions with 3 decimals, deviations with 4 decimals and a sign also on zero (+.0011, -.0000),
        leading zero omitted below 1 in (ASME Y14.5)
keys: "default" or "left" (left-handed keyboard shortcuts, keys on the right side of the keyboard).
decimals: "auto" (mm: up to 3 decimals, trailing zeros removed; inch: 3 decimals) or a fixed number of decimals
  "0".."4" of the dimension values. A dimension can carry its own number of decimals ("decimals" of the annotation).
tol_unit: text of the deviations and symmetric tolerances of mm drawings:
  "um"      µm without a unit (+27, -40, 0)
  "um_unit" µm with the unit (+27 µm, -40 µm, 0 µm)
  "mm"      mm with 3 decimals (+0.027, -0.040, 0)
  Inch drawings are not affected (deviations in inch with 4 decimals).
"""
DEFAULTS = {"units": "mm", "keys": "default", "decimals": "auto", "tol_unit": "um"}
CHOICES = {"units": ("mm", "inch"), "keys": ("default", "left"), "decimals": ("auto", "0", "1", "2", "3", "4"),
           "tol_unit": ("um", "um_unit", "mm")}
UM = "\u00b5m"
MM_PER_IN = 25.4


def options(cfg):
    """Options of a configuration with the defaults filled in."""
    o = dict(DEFAULTS)
    for k, v in ((cfg or {}).get("options") or {}).items():
        if k in CHOICES and v in CHOICES[k]:
            o[k] = v
    return o


def units_of(cfg):
    return options(cfg)["units"]


def inch_text(v_mm, decimals=3, sign=False):
    """Inch value of a length in mm, leading zero omitted: 1.575, .591, -.0007; sign: + also on positive and zero."""
    v = v_mm / MM_PER_IN
    s = "%.*f" % (decimals, abs(v))
    if s.startswith("0."):
        s = s[1:]
    neg = v < 0 and float(s) != 0.0
    return ("-" if neg else ("+" if sign else "")) + s


def mm_dev_text(v_mm, sign=True):
    """Deviation in mm with 3 decimals (4 when the value has a fourth): +0.027, -0.040, +0.0005; zero: 0."""
    if abs(v_mm) < 0.5e-4:
        return "0"
    d = 3 if abs(round(v_mm, 4) - round(v_mm, 3)) < 0.5e-4 else 4
    s = "%.*f" % (d, abs(v_mm))
    return ("-" if v_mm < 0 else ("+" if sign else "")) + s


def dev_text(v_mm, units, lower=False, tol_unit="um"):
    """Deviation text on the drawing: µm for mm (tol_unit: "um", "um_unit" with the unit, "mm" in mm), inch with 4
    decimals and a sign (zero: +.0000 upper, -.0000 lower) for inch."""
    if units == "inch":
        if abs(v_mm) < 0.5e-4 * MM_PER_IN:
            return ("-" if lower else "+") + "." + "0" * 4
        return inch_text(v_mm, 4, sign=True)
    if tol_unit == "mm":
        return mm_dev_text(v_mm)
    from .fits import fmt_dev_um
    return fmt_dev_um(v_mm) + (" " + UM if tol_unit == "um_unit" else "")


def sym_text(v_mm, units, tol_unit="um"):
    """Value after ± of a symmetric tolerance."""
    if units == "inch":
        return inch_text(abs(v_mm), 4)
    if tol_unit == "mm":
        return mm_dev_text(abs(v_mm), sign=False)
    from .fits import fmt_dev_um
    return fmt_dev_um(abs(v_mm)).lstrip("+") + (" " + UM if tol_unit == "um_unit" else "")


def length_text(v_mm, units, decimals=3, fixed=False):
    """Length on the drawing: mm with trailing zeros removed (fixed: decimals kept), or inch."""
    if units == "inch":
        return inch_text(v_mm, decimals)
    s = "%.*f" % (decimals, v_mm)
    if not fixed:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        return "0"
    if s.startswith("-") and float(s) == 0.0:
        return s[1:]
    return s


def fixed_decimals(opts, a=None):
    """Number of decimals of a dimension value, or None for the automatic format: the annotation's "decimals"
    when set, otherwise the decimals option."""
    d = (a or {}).get("decimals")
    if d not in (None, ""):
        try:
            return max(0, min(6, int(d)))
        except (TypeError, ValueError):
            pass
    o = (opts or {}).get("decimals", "auto")
    return None if o in (None, "auto") else int(o)
