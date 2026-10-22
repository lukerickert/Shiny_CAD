# -*- coding: utf-8 -*-
"""Native file and folder dialogs on the PC running the server (tkinter, in a subprocess so that the Tk main loop
never runs inside the Flask thread). Returns "" when the dialog is cancelled."""
import json
import subprocess
import sys


def ask(kind, title="", initial="", patterns=None, save_name=""):
    """kind: "open" (one file), "folder", "save". patterns: [("STEP files", "*.step *.stp"), ...]."""
    arg = json.dumps({"kind": kind, "title": title, "initial": initial, "patterns": patterns or [], "save_name": save_name})
    try:
        r = subprocess.run([sys.executable, "-m", "drawgen.dialogs", arg], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return ""
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip().splitlines()[-1] if (r.stderr or "").strip() else "dialog failed")
    return (r.stdout or "").strip()


def _run(opts):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    kind = opts.get("kind")
    kw = {"title": opts.get("title") or ""}
    init = opts.get("initial") or ""
    if init:
        kw["initialdir"] = init
    if kind == "folder":
        path = filedialog.askdirectory(**kw)
    elif kind == "save":
        pats = [tuple(p) for p in opts.get("patterns") or []] or [("All files", "*.*")]
        path = filedialog.asksaveasfilename(filetypes=pats, initialfile=opts.get("save_name") or "", **kw)
    else:
        pats = [tuple(p) for p in opts.get("patterns") or []] or [("All files", "*.*")]
        path = filedialog.askopenfilename(filetypes=pats, **kw)
    root.destroy()
    return path or ""


if __name__ == "__main__":
    o = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    try:
        p = _run(o)
    except Exception as e:
        sys.stderr.write("%s\n" % e)
        sys.exit(1)
    sys.stdout.write(p.replace("/", "\\") if sys.platform.startswith("win") else p)
