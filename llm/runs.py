# -*- coding: utf-8 -*-
"""Run folder tools: the solver files of the current analysis (job.inp, solver.log, job.sta, job.cvg, job.dat, the
report, *.nam files of CalculiX).

set_run(name, folder)      current analysis and its run folder (Analysis tab: <project>/analysis/<name>)
run_files()                files of the run folder
solver_messages(limit)     *ERROR and *WARNING messages of solver.log grouped by text, last lines of the log and of job.sta
read_run_file(file, start, count), find_in_run_file(file, text, limit)
"""
import os
import re
import time

from drawgen import inptext

RUN = {"name": None, "dir": None}
LOG = "solver.log"
MAX_LINES = 200


class RunError(ValueError):
    pass


def set_run(name, folder):
    RUN["name"] = name or None
    RUN["dir"] = os.path.abspath(folder) if folder else None


def _dir():
    if not RUN["dir"]:
        raise RunError("no analysis run folder (open an analysis in the Analysis tab, or start the chat with --run)")
    if not os.path.isdir(RUN["dir"]):
        raise RunError("run folder %s does not exist (the analysis has not been solved)" % RUN["dir"])
    return RUN["dir"]


def _file(name):
    d = _dir()
    p = os.path.abspath(os.path.join(d, str(name)))
    if os.path.dirname(p) != d:
        raise RunError("file must be in the run folder, without a path: %s" % name)
    if not os.path.isfile(p):
        raise RunError("no file %s in the run folder; files: %s" % (name, ", ".join(f["file"] for f in run_files()["files"])))
    return p


def run_files():
    d = _dir()
    rows = []
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n)
        if os.path.isfile(p):
            st = os.stat(p)
            rows.append({"file": n, "size_kb": round(st.st_size / 1024.0, 1),
                         "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))})
    return {"analysis": RUN["name"], "folder": d, "files": rows}


_MSG = re.compile(r"^\s*\*(ERROR|WARNING)\b", re.I)
_NUM = re.compile(r"[-+]?\d+(\.\d*)?([eEdD][-+]?\d+)?")


def _blocks(lines):
    """[(line number, kind, [text lines])] of the *ERROR / *WARNING messages: the message line and the indented lines
    that follow it (at most 8)."""
    out = []
    i, n = 0, len(lines)
    while i < n:
        m = _MSG.match(lines[i])
        if not m:
            i += 1
            continue
        blk = [lines[i].strip()]
        j = i + 1
        while j < n and len(blk) < 8 and lines[j].strip() and lines[j].startswith("   ") and not _MSG.match(lines[j]):
            blk.append(lines[j].strip())
            j += 1
        out.append((i + 1, m.group(1).upper(), blk))
        i = j
    return out


def message_counts(path):
    with open(path, "r", errors="replace") as f:
        b = _blocks(f.read().splitlines())
    return {"errors": sum(1 for x in b if x[1] == "ERROR"), "warnings": sum(1 for x in b if x[1] == "WARNING")}


def solver_messages(limit=20):
    """*ERROR and *WARNING messages of solver.log, grouped by their text with the numbers replaced by #: count, first
    line number and the first message of the group in full. Also the last 15 lines of solver.log and the last 5 lines
    of job.sta, and the *.nam files of the run folder (node sets written by CalculiX for warnings)."""
    limit = max(1, min(int(limit or 20), 60))
    p = _file(LOG)
    with open(p, "r", errors="replace") as f:
        lines = f.read().splitlines()
    groups = {}
    for ln, kind, blk in _blocks(lines):
        key = kind + ": " + _NUM.sub("#", " ".join(blk[:2]))
        g = groups.get(key)
        if g is None:
            groups[key] = {"kind": kind, "count": 1, "first_line": ln, "message": blk}
        else:
            g["count"] += 1
    rows = sorted(groups.values(), key=lambda g: (g["kind"] != "ERROR", g["first_line"]))
    out = {"analysis": RUN["name"], "file": LOG, "lines": len(lines),
           "errors": sum(g["count"] for g in rows if g["kind"] == "ERROR"),
           "warnings": sum(g["count"] for g in rows if g["kind"] == "WARNING"),
           "groups": rows[:limit], "groups_total": len(rows), "log_tail": lines[-15:]}
    d = _dir()
    sta = os.path.join(d, "job.sta")
    if os.path.isfile(sta):
        with open(sta, "r", errors="replace") as f:
            out["sta_tail"] = f.read().splitlines()[-5:]
    out["nam_files"] = sorted(n for n in os.listdir(d) if n.lower().endswith(".nam"))
    return out


def read_run_file(file, start=1, count=100):
    """Lines start .. start + count - 1 of a text file of the run folder (at most 200), with line numbers."""
    p = _file(file)
    count = max(1, min(int(count or 100), MAX_LINES))
    res = inptext.lines(p, int(start or 1), count)
    return {"file": file, "total_lines": res["total"], "lines": ["%d: %s" % (res["start"] + k, ln) for k, ln in enumerate(res["lines"])]}


def find_in_run_file(file, text, limit=20):
    """Line numbers and text of the lines of a run folder file containing the text (case-insensitive)."""
    p = _file(file)
    t = str(text or "").lower()
    if not t:
        raise RunError("text is empty")
    limit = max(1, min(int(limit or 20), 100))
    hits, more = [], False
    with open(p, "r", errors="replace") as f:
        for k, ln in enumerate(f, 1):
            if t in ln.lower():
                if len(hits) >= limit:
                    more = True
                    break
                hits.append("%d: %s" % (k, ln.rstrip("\r\n")[:200]))
    return {"file": file, "matches": len(hits), "lines": hits, "truncated": more}


def context_text():
    """Lines for the system prompt: the analysis, its run folder and the message counts of solver.log."""
    if not RUN["name"] and not RUN["dir"]:
        return "No analysis is open."
    L = ["Current analysis: %s" % (RUN["name"] or "-")]
    d = RUN["dir"]
    if not d or not os.path.isdir(d):
        L.append("Run folder: none yet (the analysis has not been solved or meshed).")
        return "\n".join(L)
    files = [n for n in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, n))]
    L.append("Run folder files: " + (", ".join(files[:30]) or "none"))
    if LOG in files:
        c = message_counts(os.path.join(d, LOG))
        L.append("solver.log: %d *ERROR and %d *WARNING message(s) (solver_messages lists them)." % (c["errors"], c["warnings"]))
    return "\n".join(L)
