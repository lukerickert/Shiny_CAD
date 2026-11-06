"""Text of a mesh file (.inp or .rad) for the Input file page: lines by number and a find.

lines(path, start, count) -> {"start", "lines": [str], "total"}   lines start .. start + count - 1 (1-based)
find(path, q) -> {"line": n or None}   q {"text", "from" (line), "back" (bool), "kind": "text" | "node" | "element"}:
    text: the next (or previous) line containing the text (case-insensitive); node / element: the data line of the
    node or element number "text" under *NODE / *ELEMENT (.rad: /NODE, /SHELL, /SH3N, /BRICK, /TETRA4, /TETRA10,
    /BEAM, /TRUSS, /SPRING).
The line offsets of a file are kept until it changes.
"""
import os
import re
import threading

_LOCK = threading.Lock()
_IDX = {}
RAD_ELEM = ("/SHELL", "/SH3N", "/BRICK", "/TETRA4", "/TETRA10", "/BEAM", "/TRUSS", "/SPRING")


def _offsets(path):
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime, st.st_size)
    with _LOCK:
        if key in _IDX:
            return _IDX[key]
    offs = [0]
    with open(path, "rb") as f:
        pos = 0
        for ln in f:
            pos += len(ln)
            offs.append(pos)
    with _LOCK:
        if len(_IDX) > 4:
            _IDX.clear()
        _IDX[key] = offs
    return offs


def _total(offs):
    return len(offs) - 1


def lines(path, start, count):
    offs = _offsets(path)
    n = _total(offs)
    start = max(1, min(int(start), max(n, 1)))
    end = min(n, start + max(0, int(count)) - 1)
    out = []
    if end >= start:
        with open(path, "rb") as f:
            f.seek(offs[start - 1])
            data = f.read(offs[end] - offs[start - 1])
        out = [ln.decode("utf-8", "replace").rstrip("\r\n") for ln in data.splitlines(True)]
    return {"start": start, "lines": out, "total": n}


def find(path, q):
    text = str(q.get("text") or "").strip()
    if not text:
        return {"line": None}
    kind = q.get("kind") or "text"
    back = bool(q.get("back"))
    frm = int(q.get("from") or (0 if not back else 10 ** 12))
    rad = path.lower().endswith(".rad")
    with open(path, "r", errors="replace") as f:
        L = f.read().splitlines()
    if kind in ("node", "element"):
        pat = re.compile(r"^\s*%d\s*(,|\s|$)" % int(float(text)))
        cur = None
        for i, ln in enumerate(L):
            s = ln.lstrip()
            if s.startswith("**") or s.startswith("#"):
                continue
            if (not rad and s.startswith("*")) or (rad and s.startswith("/")):
                u = s.upper()
                if rad:
                    cur = "node" if u.startswith("/NODE") else "element" if u.startswith(RAD_ELEM) else None
                else:
                    k = u.split(",")[0].strip()
                    cur = "node" if k == "*NODE" else "element" if k == "*ELEMENT" else None
                continue
            if cur == kind and pat.match(ln):
                return {"line": i + 1}
        return {"line": None}
    t = text.lower()
    rng = range(min(frm, len(L)) - 2, -1, -1) if back else range(max(frm, 0), len(L))
    for i in rng:
        if t in L[i].lower():
            return {"line": i + 1}
    return {"line": None}
