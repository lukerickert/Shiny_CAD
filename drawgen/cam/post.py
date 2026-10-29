# -*- coding: utf-8 -*-
"""G-code of a job: the moves of the operations in machine coordinates (job coordinates less the machine zero)
in the dialect of the post-processor.

estlcam: the Estlcam controller (https://www.estlcam.de/steuerung_cnc_programme.php): G00, G01, G02, G03 with
  the G-code on every move line, one G-code and one M-code per line, I and J from the start of the arc, no unit,
  plane, coordinate system or program end commands; M06 (manual tool change, the controller stops), S, M03, M05,
  M00 / M01 (stop), G04 is not known (a dwell is a comment). A fixture (G54..G59) is applied as a shift of the
  coordinates, since the controller has no coordinate systems. No canned cycles; probing is a comment and M00.
generic: G21 G90 G17 G40 G49 G54, G94, T<n> M6, S<rpm> M3, G0 / G1 / G2 / G3, G4 P<s>, M0 / M1, G54..G59, M5,
  M30 and the % marks.
grbl: GRBL 1.1: G21 G90 G17 G94, no tool changer (a tool change is M0 with a comment), no canned cycles, G38.2
  probing, M8 / M7 / M9 coolant, M30.
linuxcnc: LinuxCNC: G21 G90 G17 G40 G49 G54 G64 P0.01, T<n> M6 G43 H<n>, canned cycles G81 / G82 / G83 with
  G98 and G80, G38.2 probing with (PROBEOPEN file) / (PROBECLOSE), coolant, M2.
mach3: Mach3 / Mach4: G21 G90 G17 G40 G49 G80 G54, T<n> M6 G43 H<n>, canned cycles, G38.2 probing, coolant, M30
  and the % marks.
Moves with "a" (axis map dressup) write A<deg> in place of the mapped axis (X or Y).
"""
from .job import migrate, controller_of, _f

POSTS = {"estlcam": "Estlcam controller", "generic": "Generic (G21 G90 G54, M30)", "grbl": "GRBL 1.1",
         "linuxcnc": "LinuxCNC", "mach3": "Mach3 / Mach4"}
DIALECT = {
    "generic": {"head": ["%", "G21 G90 G17 G40 G49 G54", "G94"], "tool": "T{n} M6", "tlo": False, "cycles": False,
                "probe": True, "probe_file": False, "coolant": True, "end": ["M30", "%"]},
    "grbl": {"head": ["G21 G90 G17 G94"], "tool": None, "tlo": False, "cycles": False, "probe": True, "probe_file": False,
             "coolant": True, "end": ["M30"]},
    "linuxcnc": {"head": ["G21 G90 G17 G40 G49 G54 G64 P0.01", "G94"], "tool": "T{n} M6", "tlo": True, "cycles": True,
                 "probe": True, "probe_file": True, "coolant": True, "end": ["M2"]},
    "mach3": {"head": ["%", "G21 G90 G17 G40 G49 G80 G54", "G94"], "tool": "T{n} M6", "tlo": True, "cycles": True,
              "probe": True, "probe_file": False, "coolant": True, "end": ["M30", "%"]},
}


def _n3(v):
    return "%.3f" % (round(float(v), 3) + 0.0)


def gcode(doc, result, bits, post=None, only=None):
    """G-code text. only: the index of the one operation of the document to write (Inspect; with its finish record)."""
    doc = migrate(doc)
    post = post or doc.get("post") or "estlcam"
    if post not in POSTS:
        raise ValueError("unknown post-processor %s" % post)
    est = post == "estlcam"
    D = DIALECT.get(post, {})
    G0, G1, G2, G3 = ("G00", "G01", "G02", "G03") if est else ("G0", "G1", "G2", "G3")
    name = doc.get("name") or "cam"
    lines = ["(ShinyCAD CAM: %s, post %s, mm)" % (name, POSTS[post])] if est else \
        [D["head"][0]] if D["head"][0] == "%" else []
    if not est:
        lines.append("(ShinyCAD CAM: %s, post %s)" % (name, POSTS[post]))
        lines += [h for h in D["head"] if h != "%"]
    ops = {o.get("id"): o for o in doc.get("operations") or []}
    ox, oy, oz = result.get("origin") or [0.0, 0.0, 0.0]
    cz = result.get("clearance_z", 0.0) - oz
    lines.append("(machine zero at job X%s Y%s Z%s)" % (_n3(ox), _n3(oy), _n3(oz)))
    coolant = (doc.get("setup") or {}).get("coolant") or "none"
    fixture = [0.0, 0.0, 0.0]        # estlcam: a fixture as a shift
    cur_tool = None
    spindle = False
    cool_on = False

    def mc(p):
        return p[0] - ox + fixture[0], p[1] - oy + fixture[1], p[2] - oz + fixture[2]

    def xyz(m, x, y, z):
        """Coordinate words of a move; an axis-mapped move writes A for the mapped axis."""
        if "a" in m:
            if m.get("amap") == "x":
                return "A%s Y%s Z%s" % (_n3(m["a"]), _n3(y), _n3(z))
            return "X%s A%s Z%s" % (_n3(x), _n3(m["a"]), _n3(z))
        return "X%s Y%s Z%s" % (_n3(x), _n3(y), _n3(z))

    only_id = None
    if only is not None:
        dops = doc.get("operations") or []
        only_id = dops[only].get("id") if 0 <= only < len(dops) else None
    for idx, rec in enumerate(result.get("operations") or []):
        if only is not None and rec.get("id") != only_id and rec.get("finish_of") != only_id:
            continue
        if not rec.get("ok") or not rec.get("moves"):
            continue
        op = ops.get(rec.get("id")) or ops.get(rec.get("finish_of")) or {}
        moves = rec["moves"]
        cutting = any("p" in m for m in moves)
        if cutting:
            tc = controller_of(doc, rec.get("tool") or op.get("tc"))
            tn = int(_f(tc.get("number"), 1))
            lines.append("(%s: %s, tool %s %s)" % (rec.get("type"), rec.get("name") or op.get("name") or rec.get("id"), tc.get("id"), tc.get("name") or ""))
            if tn != cur_tool:
                if spindle:
                    lines.append("M05" if est else "M5")
                    spindle = False
                if cool_on:
                    lines.append("M9")
                    cool_on = False
                if est:
                    lines.append("M06 T%d" % tn)
                elif D["tool"]:
                    lines.append(D["tool"].format(n=tn))
                    if D["tlo"]:
                        lines.append("G43 H%d" % tn)
                else:
                    lines.append("(tool change: T%d %s)" % (tn, tc.get("name") or ""))
                    lines.append("M0")
                cur_tool = tn
            rpm = int(_f(rec.get("rpm"), _f(tc.get("rpm"), 0)))
            if not spindle:
                if rpm:
                    lines.append("S%d" % rpm if est else "S%d M%s" % (rpm, "4" if (tc.get("dir") or "CW") == "CCW" else "3"))
                if est:
                    lines.append("M03")
                elif not rpm:
                    lines.append("M3")
                spindle = True
            if not est and D.get("coolant") and coolant != "none" and not cool_on:
                lines.append("M8" if coolant == "flood" else "M7")
                cool_on = True
            lines.append("%s Z%s" % (G0, _n3(cz)))
        feed = None
        prev = None
        cycles = rec.get("cycles") if (not est and D.get("cycles") and op.get("cycles")) else None
        cyc_done = set()
        in_cycle = False
        for m in moves:
            k = m.get("k")
            if cycles is not None and m.get("cyc") is not None and m["cyc"] < len(cycles):
                # the hole as one canned cycle line (the expanded moves are skipped)
                ci = m["cyc"]
                if ci not in cyc_done:
                    c = cycles[ci]
                    cyc_done.add(ci)
                    x, y, z = mc([c["x"], c["y"], c["z"]])
                    r = c["r"] - oz + fixture[2]
                    if c.get("q"):
                        g = "G83 X%s Y%s Z%s R%s Q%s" % (_n3(x), _n3(y), _n3(z), _n3(r), _n3(c["q"]))
                    elif c.get("p"):
                        g = "G82 X%s Y%s Z%s R%s P%.1f" % (_n3(x), _n3(y), _n3(z), _n3(r), _f(c["p"]))
                    else:
                        g = "G81 X%s Y%s Z%s R%s" % (_n3(x), _n3(y), _n3(z), _n3(r))
                    lines.append(("G98 " if not in_cycle else "") + g + " F%.0f" % _f(c.get("f"), 100))
                    in_cycle = True
                    feed = None
                continue
            if in_cycle and "p" in m:
                lines.append("G80")
                in_cycle = False
            if k == "comment":
                lines.append("(%s)" % str(m.get("text", "")).replace("(", "[").replace(")", "]"))
                continue
            if k == "stop":
                if spindle and not m.get("optional"):
                    lines.append("M05" if est else "M5")
                    spindle = False
                lines.append(("M01" if m.get("optional") else "M00") if est else ("M1" if m.get("optional") else "M0"))
                continue
            if k == "custom":
                for ln in str(m.get("text", "")).splitlines():
                    if ln.strip():
                        lines.append(ln.rstrip())
                continue
            if k == "fixture":
                g = str(m.get("g") or "G54")
                if est:
                    sh = (op.get("shift") or [0, 0, 0])
                    fixture = [_f(sh[0]), _f(sh[1]), _f(sh[2])]
                    lines.append("(fixture %s: shift X%s Y%s Z%s)" % (g, _n3(fixture[0]), _n3(fixture[1]), _n3(fixture[2])))
                else:
                    lines.append(g)
                continue
            if k == "dwell":
                lines.append("(dwell %.1f s)" % _f(m.get("s")) if est else "G4 P%.1f" % _f(m.get("s")))
                continue
            if k == "hop":
                lines.append("%s Z%s" % (G0, _n3(_f(m.get("z")) - oz + fixture[2])))
                continue
            if k in ("probe_open", "probe_close"):
                if D.get("probe_file"):
                    lines.append("(PROBEOPEN %s)" % m.get("name") if k == "probe_open" else "(PROBECLOSE)")
                continue
            if k == "probe":
                x, y, z0 = mc([m["x"], m["y"], m["z0"]])
                z1 = _f(m["z1"]) - oz + fixture[2]
                if est or not D.get("probe"):
                    lines.append("(probe X%s Y%s down to Z%s: not supported by %s)" % (_n3(x), _n3(y), _n3(z1), POSTS[post]))
                    lines.append("M00" if est else "M0")
                else:
                    lines.append("%s X%s Y%s Z%s" % (G0, _n3(x), _n3(y), _n3(z0)))
                    lines.append("G38.2 Z%s F%.0f" % (_n3(z1), _f(m.get("f"), 50)))
                    lines.append("%s Z%s" % (G0, _n3(z0)))
                continue
            if "p" not in m:
                continue
            x, y, z = mc(m["p"])
            if k == "rapid":
                lines.append("%s %s" % (G0, xyz(m, x, y, z)))
            elif k == "arc":
                f = m.get("f") or 100
                fw = "" if f == feed else " F%.0f" % f
                feed = f
                cx, cy = m["c"][0] - ox + fixture[0], m["c"][1] - oy + fixture[1]
                px, py = prev if prev else (x, y)
                g = G2 if m.get("cw") else G3
                lines.append("%s X%s Y%s Z%s I%s J%s%s" % (g, _n3(x), _n3(y), _n3(z), _n3(cx - px), _n3(cy - py), fw))
            else:
                f = m.get("f") or 100
                fw = "" if f == feed else " F%.0f" % f
                feed = f
                lines.append("%s %s%s" % (G1, xyz(m, x, y, z), fw))
            prev = (x, y)
        if in_cycle:
            lines.append("G80")
    if spindle:
        lines.append("M05" if est else "M5")
    if cool_on:
        lines.append("M9")
    if est:
        lines.append("G00 Z%s" % _n3(cz))
        lines.append("(end)")
    else:
        lines += ["G0 Z%s" % _n3(cz)] + D["end"]
    return "\n".join(lines) + "\n"
