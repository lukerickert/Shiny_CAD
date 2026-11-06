"""Material curves for the plots of the Analysis tab: true stress (MPa) against true plastic strain.

library(name) -> [{"name", "ep": [], "s": []}]   the curves of a library material as the deck has them: the static
    curve, and per strain rate the curve scaled by the Cowper-Symonds factor 1 + (rate / D)^(1 / q) (LAW36 entries
    with rates) or by 1 + c ln(rate / eps0) (Johnson-Cook entries with c > 0: the curve at eps0 and at 10, 100 and 1000 1/s).
inp(raw_material) -> curves of the *PLASTIC table of a material of an .inp (one curve per temperature).
rad(lines) -> {"materials": {name: curves}, "functions": [{"id", "name", "x", "y"}]}   /MAT/PLAS_TAB (its /FUNCT
    curves times Fscale) and /MAT/PLAS_JOHNS (Iflag 0) of a Radioss deck, and its /FUNCT curves.
"""
import math
import re

EP = (0.0, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0)
JC_RATES = (10.0, 100.0, 1000.0)


def _jc(a, b, n, f=1.0, name="static"):
    return {"name": name, "ep": list(EP), "s": [(a + (b * ep ** n if ep > 0 else 0.0)) * f for ep in EP]}


def _rate(r):
    return "%g 1/s" % r


def library(name):
    from .explicit.constants import MATERIAL_LIBRARY
    e = MATERIAL_LIBRARY.get(name or "")
    if not e:
        return []
    if e.get("curve"):
        pts = sorted((float(a), float(b)) for a, b in e["curve"])
        ep, s = [p[0] for p in pts], [p[1] for p in pts]
        out = [{"name": "static", "ep": ep, "s": s}]
        D, q, rates = float(e.get("cs_D") or 0), float(e.get("cs_q") or 0), e.get("rates") or []
        if D > 0 and q > 0:
            for r in sorted(rates)[:4]:
                f = 1.0 + (float(r) / D) ** (1.0 / q)
                out.append({"name": _rate(r), "ep": ep, "s": [v * f for v in s]})
        return out
    if e.get("a") is not None:
        a, b, n = float(e["a"]), float(e.get("b") or 0), float(e.get("n") or 1)
        c, eps0 = float(e.get("c") or 0), float(e.get("eps0") or 1)
        out = [_jc(a, b, n, 1.0, _rate(eps0) if c > 0 else "static")]
        if c > 0:
            for r in JC_RATES:
                if r > eps0:
                    out.append(_jc(a, b, n, 1.0 + c * math.log(r / eps0), _rate(r)))
        return out
    return []


def inp(m):
    """Curves of the *PLASTIC rows of a material ({"_rows": {"*PLASTIC": [[stress, strain, temperature], ...]}})."""
    rows = (m.get("_rows") or {}).get("*PLASTIC") or []
    by_t = {}
    for r in rows:
        if len(r) >= 2 and r[0] is not None and r[1] is not None:
            t = r[2] if len(r) >= 3 and r[2] is not None else None
            by_t.setdefault(t, []).append((float(r[1]), float(r[0])))
    out = []
    for t, pts in by_t.items():
        pts.sort()
        out.append({"name": "true stress" if t is None or len(by_t) == 1 else "T %g" % t, "ep": [p[0] for p in pts], "s": [p[1] for p in pts]})
    return out


def _nums(line):
    out = []
    for t in line.replace(",", " ").split():
        try:
            out.append(float(t))
        except ValueError:
            return None
    return out


def rad(lines):
    """Material curves and functions of the lines of a Radioss deck."""
    blocks, cur = [], None
    for ln in lines:
        if ln.startswith("/"):
            cur = {"head": ln.strip(), "title": None, "data": []}
            blocks.append(cur)
        elif cur is not None and not ln.startswith("#") and ln.strip():
            if cur["title"] is None:
                cur["title"] = ln.strip()
            else:
                cur["data"].append(ln)
    funcs = {}
    for b in blocks:
        m = re.match(r"/FUNCT/(\d+)", b["head"], re.I)
        if m:
            x, y = [], []
            for ln in b["data"]:
                v = _nums(ln)
                if v and len(v) >= 2:
                    x.append(v[0]); y.append(v[1])
            funcs[int(m.group(1))] = {"id": int(m.group(1)), "name": b["title"] or "", "x": x, "y": y}
    mats = {}
    for b in blocks:
        m = re.match(r"/MAT/(PLAS_TAB|LAW36|PLAS_JOHNS|LAW2)/(\d+)", b["head"], re.I)
        if not m:
            continue
        rows = [_nums(ln) for ln in b["data"]]
        rows = [r for r in rows if r is not None]
        name = (b["title"] or "MAT %s" % m.group(2)).upper()
        try:
            if m.group(1).upper() in ("PLAS_TAB", "LAW36"):
                n = int(rows[2][0])
                ids = [int(v) for v in rows[4][:n]]
                fs = (rows[5] if len(rows) > 5 else []) + [0.0] * n
                rate = (rows[6] if len(rows) > 6 else []) + [0.0] * n
                cs = []
                for k, i in enumerate(ids):
                    f = funcs.get(i)
                    if not f:
                        continue
                    sc = fs[k] or 1.0
                    cs.append({"name": "static" if n == 1 or rate[k] == 0 else _rate(rate[k]), "ep": f["x"], "s": [v * sc for v in f["y"]]})
                if cs:
                    mats[name] = cs
            else:
                if len(rows[1]) > 2 and int(rows[1][2]) != 0:
                    continue
                a, bb, nn = rows[2][0], rows[2][1], rows[2][2]
                mats[name] = [_jc(a, bb, nn)]
        except (IndexError, ValueError):
            continue
    return {"materials": mats, "functions": [funcs[k] for k in sorted(funcs)]}
