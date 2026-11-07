# -*- coding: utf-8 -*-
"""Deck tools: open .inp / .rad decks by alias and query them through drawgen.inpinfo, inpquery and inptext.

Every function returns a JSON-serialisable dict. Lists are limited (limit argument) and the totals are given.
"""
import fnmatch
import os
import re

from drawgen import inpinfo, inpquery, inptext

DECKS = {}                      # alias -> absolute path
MAX_LINES = 200


class ToolError(ValueError):
    pass


def _r(v, d=6):
    """Value rounded to d significant digits (lists and dicts recursively)."""
    if isinstance(v, float):
        return float("%.*g" % (d, v))
    if isinstance(v, (list, tuple)):
        return [_r(x, d) for x in v]
    if isinstance(v, dict):
        return {k: _r(x, d) for k, x in v.items()}
    return v


def open_deck(path, alias=None):
    """Registers the deck under an alias (default: file stem, made unique). Returns the alias."""
    path = os.path.abspath(os.path.expanduser(str(path).strip().strip('"')))
    if not os.path.isfile(path):
        raise ToolError("file not found: %s" % path)
    if not alias:
        stem = os.path.splitext(os.path.basename(path))[0]
        alias, k = stem, 2
        while alias in DECKS and DECKS[alias] != path:
            alias = "%s_%d" % (stem, k)
            k += 1
    DECKS[alias] = path
    return alias


def close_deck(alias):
    DECKS.pop(alias, None)


def _path(deck):
    if deck in DECKS:
        return DECKS[deck]
    for k, v in DECKS.items():
        if k.lower() == str(deck).lower():
            return v
    raise ToolError("unknown deck %r; open decks: %s" % (deck, ", ".join(DECKS) or "none"))


def _info(deck):
    return inpinfo.inspect(_path(deck))


def list_decks():
    return {"decks": [{"deck": a, "file": os.path.basename(p), "size_mb": round(os.path.getsize(p) / 1e6, 1)}
                      for a, p in DECKS.items()]}


def deck_summary(deck):
    """File, heading, node and element counts, element types, sections, materials, constraint counts, steps, checks."""
    i = _info(deck)
    cons = {}
    for kind, _name, _txt in i["constraints"]:
        cons[kind] = cons.get(kind, 0) + 1
    return _r({
        "deck": deck,
        "file": i["file"]["name"], "size_mb": i["file"]["size_kb"] / 1024.0, "lines": i["file"]["lines"],
        "heading": i["file"]["heading"][:200] if isinstance(i["file"]["heading"], str) else i["file"]["heading"],
        "includes": i["file"]["includes"],
        "nodes": {"count": i["nodes"]["count"], "bbox": i["nodes"]["bbox"], "coincident": i["nodes"]["coincident"],
                  "unused": i["nodes"]["unused"]},
        "elements": i["elements"]["count"],
        "element_types": [{"type": t["type"], "count": t["count"]} for t in i["element_types"]],
        "counts": {"elsets": len(i["elsets"]), "nsets": len(i["nsets"]), "surfaces": len(i["surfaces"]),
                   "sections": len(i["sections"]), "materials": len(i["materials"])},
        "sections": [{"kind": s["kind"], "elset": s["elset"], "material": s["material"], "elements": s["elements"],
                      "t": s.get("t")} for s in i["sections"][:20]],
        "materials": [{"name": m["name"], "E": m.get("E"), "nu": m.get("nu"), "rho_file": m.get("rho_file"),
                       "plastic": bool(m.get("plastic"))} for m in i["materials"][:20]],
        "constraints": cons,
        "steps": [{"index": k + 1, "name": s["name"], "procedure": s["procedure"], "proc_params": s["proc_params"],
                   "proc_data": s["proc_data"], "cload_total": s["cload_total"][:3]} for k, s in enumerate(i["steps"])],
        "mass_kg": i["mass"]["kg"],
        "checks": [c for c in i["checks"] if not c.startswith("keywords not used by the program")][:15],
    })


_KINDS = ("elset", "nset", "surface", "constraint", "section", "material", "keyword")


def list_items(deck, kind, pattern="*", limit=40):
    """Rows of one kind whose name matches the pattern (case-insensitive wildcards * and ?)."""
    if kind not in _KINDS:
        raise ToolError("kind must be one of %s" % ", ".join(_KINDS))
    i = _info(deck)
    pat = str(pattern or "*").upper()
    limit = max(1, min(int(limit or 40), 200))
    if kind == "elset":
        rows = [{"name": s["name"], "elements": s["elements"], "types": s["types"], "section": s["section"],
                 "material": s["material"], "volume": s.get("volume"), "area": s.get("area"), "bbox": s["bbox"]}
                for s in i["elsets"]]
    elif kind == "nset":
        rows = [{"name": s["name"], "nodes": s["nodes"], "missing": s["missing"], "bbox": s["bbox"]} for s in i["nsets"]]
    elif kind == "surface":
        rows = [dict(s) for s in i["surfaces"]]
    elif kind == "constraint":
        rows = [{"keyword": k, "name": n, "definition": t} for k, n, t in i["constraints"]]
    elif kind == "section":
        rows = [dict(s) for s in i["sections"]]
    elif kind == "material":
        rows = [dict(m) for m in i["materials"]]
    else:
        rows = [dict(k) for k in i["keywords"]]
    keys = {"section": ("elset",), "keyword": ("keyword",), "constraint": ("name", "keyword")}.get(kind, ("name",))
    hit = [r for r in rows if any(fnmatch.fnmatchcase(str(r.get(k) or "").upper(), pat) for k in keys)]
    return _r({"deck": deck, "kind": kind, "pattern": pattern, "total": len(rows), "matches": len(hit),
               "rows": hit[:limit], "truncated": len(hit) > limit})


def get_steps(deck):
    """Steps: procedure, its parameters and data line, boundary targets, load totals, distributed loads, outputs."""
    i = _info(deck)
    return _r({"deck": deck, "steps": [dict(s, index=k + 1) for k, s in enumerate(i["steps"])]})


def query_mesh(deck, what, by, numbers=None, box=None, point=None, radius=None, nearest=None, set=None, type=None,
               criterion=None, value=None, limit=20):
    """Nodes or elements by number, box, distance, set, element type, attachment or quality (drawgen.inpquery)."""
    q = {"what": what, "by": by, "limit": max(1, min(int(limit or 20), 50))}
    for k, v in (("numbers", numbers), ("box", box), ("point", point), ("radius", radius), ("nearest", nearest),
                 ("set", set), ("type", type), ("criterion", criterion), ("value", value)):
        if v is not None:
            q[k] = v
    try:
        res = inpquery.query(_path(deck), q)
    except inpquery.QueryError as e:
        raise ToolError(str(e))
    rows = []
    for r in res.get("rows", []):
        rows.append({k: v for k, v in r.items() if k not in ("edges", "tris")})
    return _r({"deck": deck, "what": res.get("what"), "count": res.get("count"), "rows": rows,
               "truncated": res.get("truncated"), "note": res.get("note")})


def read_lines(deck, start, count=50):
    """Lines start .. start + count - 1 of the deck (1-based, at most 200), each with its line number."""
    count = max(1, min(int(count or 50), MAX_LINES))
    res = inptext.lines(_path(deck), int(start), count)
    return {"deck": deck, "total_lines": res["total"],
            "lines": ["%d: %s" % (res["start"] + k, ln) for k, ln in enumerate(res["lines"])]}


def find_lines(deck, text, kind="text", limit=20, from_line=1):
    """Lines containing the text (case-insensitive), from from_line on. kind "keyword": lines starting with the
    keyword (for example *TIE, *STEP, *CONTACT PAIR); kind "node" / "element": the data line of that number."""
    path = _path(deck)
    limit = max(1, min(int(limit or 20), 100))
    text = str(text or "").strip()
    if not text:
        raise ToolError("text is empty")
    if kind in ("node", "element"):
        n = inptext.find(path, {"text": text, "kind": kind}).get("line")
        hits = [] if n is None else ["%d: %s" % (n, inptext.lines(path, n, 1)["lines"][0])]
        return {"deck": deck, "matches": len(hits), "lines": hits, "truncated": False}
    if kind == "keyword":
        kw = text.upper() if text.startswith(("*", "/")) else "*" + text.upper()
        rx = re.compile(r"^\s*%s\s*(,|$)" % re.escape(kw), re.I)
        test = rx.match
    else:
        t = text.lower()
        test = lambda s: t in s.lower()
    hits, more = [], False
    with open(path, "r", errors="replace") as f:
        for k, ln in enumerate(f, 1):
            if k < int(from_line or 1):
                continue
            if test(ln):
                if len(hits) >= limit:
                    more = True
                    break
                hits.append("%d: %s" % (k, ln.rstrip("\r\n")[:200]))
    return {"deck": deck, "matches": len(hits), "lines": hits, "truncated": more}


def compare_decks(a, b):
    """Differences of two decks: counts, element types, sections, materials, constraints and steps."""
    sa, sb = deck_summary(a), deck_summary(b)
    out = {"a": a, "b": b, "differences": {}}
    d = out["differences"]
    for k in ("lines", "elements", "mass_kg"):
        if sa[k] != sb[k]:
            d[k] = [sa[k], sb[k]]
    if sa["nodes"]["count"] != sb["nodes"]["count"]:
        d["nodes"] = [sa["nodes"]["count"], sb["nodes"]["count"]]
    for k in ("element_types", "sections", "materials", "steps"):
        if sa[k] != sb[k]:
            d[k] = {"a": sa[k], "b": sb[k]}
    if sa["constraints"] != sb["constraints"]:
        d["constraints"] = {"a": sa["constraints"], "b": sb["constraints"]}
    if sa["counts"] != sb["counts"]:
        d["counts"] = {"a": sa["counts"], "b": sb["counts"]}
    return out
