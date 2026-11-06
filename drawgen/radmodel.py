# -*- coding: utf-8 -*-
"""Radioss starter decks (block format, ..._0000.rad) as a mesh source: read(path) gives the form of inpmodel.read.

Read: /NODE, /SHELL, /SH3N, /BRICK, /TETRA4 (elements per part), /PART (title, property, material), /PROP/SHELL and
/PROP/TYPE1 (thickness), /PROP/SOLID and /PROP/TYPE14, /MAT/<law> (density, E, nu of the first two lines), /GRNOD/NODE
(node groups), /BEGIN (input units), #include files (relative to the deck). Other keywords (loads, boundary
conditions, interfaces, other element types) are not read.

Element types: /SHELL S4 (S3 when node 4 is 0 or repeats node 3), /SH3N S3, /BRICK C3D8 (degenerate bricks C3D6 or
C3D4), /TETRA4 C3D4. Element sets: one per part, the part title (upper case, A-Z 0-9 _), else PART_<id>. Node sets:
the /GRNOD/NODE titles, else GRNOD_<id>. Materials: the material title, else MAT_<id>; density in t/mm^3 converted to
kg/m^3 (inpmodel rule). Lengths are read as mm.
"""
import os
import re

TYPES = {"SHELL": "shell", "SH3N": "sh3n", "BRICK": "brick", "TETRA4": "tetra4"}
SKIPPED = ("SPRING", "BEAM", "TRUSS", "TETRA10", "BRIC20", "SHEL16", "PENTA6", "SPHCEL", "QUAD", "TRIA")


def _err(msg):
    from .inpmodel import InpError
    return InpError(msg)


def _lines(path, seen=None):
    """Lines of the deck with the #include files in place (comment lines left out)."""
    seen = seen if seen is not None else set()
    ap = os.path.abspath(path)
    if ap in seen:
        return []
    seen.add(ap)
    try:
        with open(path, "r", errors="replace") as f:
            raw = f.read().splitlines()
    except OSError as e:
        raise _err("cannot read %s: %s" % (path, e))
    out = []
    for ln in raw:
        s = ln.rstrip()
        if s.lower().startswith("#include"):
            inc = s[8:].strip().strip('"')
            p = inc if os.path.isabs(inc) else os.path.join(os.path.dirname(path), inc)
            out += _lines(p, seen)
            continue
        if s.lstrip().startswith("#") or s.lstrip().startswith("$"):
            continue                    # comments (a blank line is a data line: a title or default values)
        out.append(s)
    return out


def _fields(line, widths):
    """Fixed-width fields of a line (strings); a line with commas or tabs: fields split on them / white space."""
    if "," in line or "\t" in line:
        return [t.strip() for t in re.split(r"[,\t]", line)] + [""] * len(widths)
    out, k = [], 0
    for w in widths:
        out.append(line[k:k + w].strip())
        k += w
    return out


def _f(s, d=None):
    try:
        return float(s.replace("D", "E").replace("d", "e"))
    except (ValueError, AttributeError):
        return d


def _i(s, d=None):
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return d


def _ints(line):
    """Integers of a line of 10-character fields (fields that touch: read by position)."""
    toks = line.replace(",", " ").split()
    if all(len(t) < 10 for t in toks):
        return [v for v in (_i(t) for t in toks) if v is not None]
    return [v for v in (_i(x) for x in _fields(line, [10] * (len(line) // 10 + 1))) if v is not None]


def _name(title, prefix, key):
    n = re.sub(r"[^A-Za-z0-9_]+", "_", (title or "").strip()).strip("_").upper()
    return n or "%s_%s" % (prefix, key)


def read(path):
    if not os.path.isfile(path):
        raise _err("file not found: %s" % path)
    lines = _lines(path)
    nodes, elements, part_elems, warnings = {}, {}, {}, []
    parts, props, mats, grnod = {}, {}, {}, {}
    skipped = {}
    i, n = 0, len(lines)
    units = None
    while i < n:
        ln = lines[i]
        if not ln.startswith("/"):
            i += 1
            continue
        kw = [t for t in ln.strip().split("/") if t != ""]
        head = kw[0].upper() if kw else ""
        i += 1
        body = []
        while i < n and not lines[i].startswith("/"):
            body.append(lines[i])
            i += 1
        if head == "BEGIN" and len(body) >= 3:
            units = [x for x in _fields(body[2], [20, 20, 20]) if x]
        elif head == "NODE":
            for b in body:
                f = b.split()
                if len(f) == 4 and all(_f(x) is not None for x in f):
                    nid, xyz = _i(f[0]), [_f(x) for x in f[1:]]
                else:
                    g = _fields(b, [10, 20, 20, 20])
                    nid, xyz = _i(g[0]), [_f(x, 0.0) for x in g[1:4]]
                if nid is not None:
                    nodes[nid] = tuple(xyz)
        elif head in TYPES and len(kw) >= 2:
            pid = _i(kw[1])
            kind = TYPES[head]
            for b in body:
                v = _ints(b)
                if kind == "shell" and len(v) >= 4:
                    eid, ns = v[0], v[1:5] if len(v) >= 5 else v[1:4]
                    if len(ns) == 4 and (ns[3] == 0 or ns[3] == ns[2]):
                        ns = ns[:3]
                    et = "S4" if len(ns) == 4 else "S3"
                elif kind == "sh3n" and len(v) >= 4:
                    eid, ns, et = v[0], v[1:4], "S3"
                elif kind == "tetra4" and len(v) >= 5:
                    eid, ns, et = v[0], v[1:5], "C3D4"
                elif kind == "brick" and len(v) >= 9:
                    eid, ns = v[0], v[1:9]
                    u = list(dict.fromkeys(ns))
                    if len(u) == 8:
                        et = "C3D8"
                    elif len(u) == 4:
                        et, ns = "C3D4", u
                    elif len(u) == 6 and ns[2] == ns[3] and ns[6] == ns[7]:
                        et, ns = "C3D6", [ns[0], ns[1], ns[2], ns[4], ns[5], ns[6]]
                    else:
                        skipped["degenerate BRICK"] = skipped.get("degenerate BRICK", 0) + 1
                        continue
                else:
                    continue
                elements[eid] = (et, ns)
                part_elems.setdefault(pid, []).append(eid)
        elif head == "PART" and len(kw) >= 2:
            g = _fields(body[1], [10, 10, 10]) if len(body) > 1 else ["", "", ""]
            parts[_i(kw[1])] = {"title": body[0].strip() if body else "", "prop": _i(g[0]), "mat": _i(g[1])}
        elif head == "PROP" and len(kw) >= 3:
            ptype, pid = kw[1].upper(), _i(kw[2])
            if ptype in ("SHELL", "TYPE1"):
                t = _f(_fields(body[3], [10, 10, 20, 20, 10, 10])[2]) if len(body) > 3 else None
                props[pid] = {"kind": "shell", "t": t}
            elif ptype in ("SOLID", "TYPE14", "TSHELL", "TYPE20"):
                props[pid] = {"kind": "solid"}
            else:
                props[pid] = {"kind": "other", "type": ptype}
        elif head == "MAT" and len(kw) >= 3:
            mid = _i(kw[-1])
            m = {"title": body[0].strip() if body else "", "law": kw[1].upper()}
            if len(body) > 1:
                m["rho"] = _f(_fields(body[1], [20])[0])
            if len(body) > 2:
                g = _fields(body[2], [20, 20])
                m["E"], m["nu"] = _f(g[0]), _f(g[1])
            mats[mid] = m
        elif head == "GRNOD" and len(kw) >= 3 and kw[1].upper() == "NODE":
            gid = _i(kw[2])
            ids = []
            for b in body[1:]:
                ids += [x for x in _ints(b) if x > 0]
            grnod[gid] = (body[0].strip() if body else "", ids)
        elif head in SKIPPED:
            skipped[head] = skipped.get(head, 0) + len(body)
    if units and len(units) >= 2 and units[1].lower() != "mm":
        warnings.append("input units %s: lengths are read as mm" % " ".join(units))
    for k, v in skipped.items():
        warnings.append("/%s left out (%d lines): only shells, bricks and 4-node tetrahedra are read" % (k, v) if not k.startswith("degenerate")
                        else "%d degenerate bricks left out" % v)
    if not nodes or not elements:
        raise _err("%s: no nodes or no shell, brick or tetrahedron elements" % os.path.basename(path))
    materials, mat_names = {}, {}
    for mid, m in mats.items():
        nm = _name(m["title"], "MAT", mid)
        while nm in materials:
            nm += "_%s" % mid
        mat_names[mid] = nm
        e = {}
        if m.get("E"):
            e.update(E=m["E"], nu=m.get("nu") if m.get("nu") is not None else 0.3)
        if m.get("rho"):
            e["rho"] = m["rho"] * 1e12 if m["rho"] < 1e-3 else m["rho"]
        materials[nm] = e
    elsets, sections, used = {}, [], set()
    for pid, ids in sorted(part_elems.items(), key=lambda x: (x[0] is None, x[0])):
        p = parts.get(pid) or {}
        nm = _name(p.get("title"), "PART", pid)
        while nm in used:
            nm += "_%s" % pid
        used.add(nm)
        elsets[nm] = ids
        pr = props.get(p.get("prop")) or {}
        shell = elements[ids[0]][0] in ("S3", "S4")
        if pr.get("kind") == "other":
            warnings.append("part %s: /PROP/%s is read as a %s section without its data" % (nm, pr.get("type"), "shell" if shell else "solid"))
        sections.append({"elset": nm, "kind": "shell" if shell else "solid", "material": mat_names.get(p.get("mat"), ""),
                         "t": pr.get("t") if shell else None, "offset": "mid"})
    nsets = {}
    for gid, (title, ids) in grnod.items():
        nm = _name(title, "GRNOD", gid)
        while nm in nsets:
            nm += "_%s" % gid
        nsets[nm] = ids
    return {"nodes": nodes, "elements": elements, "elsets": elsets, "nsets": nsets, "materials": materials,
            "sections": sections, "warnings": warnings}
