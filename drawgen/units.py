# -*- coding: utf-8 -*-
"""Program options (config.json "options") and the number formats of the drawing units.

units: "mm" (default) or "inch". The model is always in mm; only the text on the drawings changes.
  mm:   dimensions 0.001 mm with trailing zeros removed, deviations in µm (+27, -40, 0)
  inch: dimensions with 3 decimals, deviations with 4 decimals and a sign also on zero (+.0011, -.0000),
        leading zero omitted below 1 in (ASME Y14.5)
keys: "default" or "left" (left-handed keyboard shortcuts, keys on the right side of the keyboard).
"""
DEFAULTS = {"units": "mm", "keys": "default"}
CHOICES = {"units": ("mm", "inch"), "keys": ("default", "left")}
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


def dev_text(v_mm, units, lower=False):
    """Deviation text on the drawing: µm for mm, inch with 4 decimals and a sign (zero: +.0000 upper, -.0000
    lower) for inch."""
    if units == "inch":
        if abs(v_mm) < 0.5e-4 * MM_PER_IN:
            return ("-" if lower else "+") + "." + "0" * 4
        return inch_text(v_mm, 4, sign=True)
    from .fits import fmt_dev_um
    return fmt_dev_um(v_mm)


def sym_text(v_mm, units):
    """Value after ± of a symmetric tolerance."""
    if units == "inch":
        return inch_text(abs(v_mm), 4)
    from .fits import fmt_dev_um
    return fmt_dev_um(abs(v_mm)).lstrip("+")


def length_text(v_mm, units, decimals=3):
    """Length on the drawing: mm with trailing zeros removed, or inch."""
    if units == "inch":
        return inch_text(v_mm, decimals)
    s = ("%.*f" % (decimals, v_mm)).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s
