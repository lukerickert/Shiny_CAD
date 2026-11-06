#!/usr/bin/env python3
"""
==============================================================================
RAD PREVIEW  -  one-cycle geometry preview of an OpenCourant deck   (v1.0)
==============================================================================
Displays a starter deck (<job>_0000.rad) in ParaView before the real solve.

Each selected deck is copied into its own preview folder together with the
files it includes. A one-cycle engine deck is written there, the starter and
engine are run, the first animation file is converted to legacy ASCII VTK with
anim_to_vtk_win64, and ParaView is launched on the result. The original run
folder is not written to.

    python rad_preview.py            # window with an Add decks... dialog

Windows. starter_win64, engine_win64 and anim_to_vtk_win64 must be on PATH
(the OpenCourant exec folder). The paraview.exe path is kept in rad_preview.json in
%APPDATA%\\drawgen.
==============================================================================
"""

import os
import re
import sys
import json
import glob
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, ttk

# Windows CREATE_NO_WINDOW: keeps a console from flashing for each child.
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

STARTER = "starter_win64"
ENGINE = "engine_win64"
ANIM2VTK = "anim_to_vtk_win64"

PREVIEW_DIRNAME = "_preview"

# Tstop values tried in order. 0.0 stops the engine after the animation file
# written at T=0; the second value covers builds that need one cycle first.
TSTOP_TRIES = ("0.0", "1E-9")

UI = {
    "bg": "#ffffff", "fg": "#111111",
    "btn": "#111111", "btn_fg": "#ffffff",
    "console_bg": "#000000", "console_fg": "#00ff66",
}


# ==============================================================================
# CONFIG
# ==============================================================================
def _state_dir():
    base = os.environ.get("APPDATA")
    if not base:
        return os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, "drawgen")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        return os.path.dirname(os.path.abspath(__file__))
    return d


CONFIG_FILE = os.path.join(_state_dir(), "rad_preview.json")


def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def config_set(key, value):
    """Update one key, leaving every other setting in the file intact."""
    c = load_config()
    c[key] = value
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(c, f, indent=4)
    except Exception:
        pass


def find_paraview():
    """paraview.exe from the saved path, then the usual install locations."""
    p = (load_config().get("paraview_path") or "").strip()
    if p and os.path.isfile(p):
        return p
    cands = []
    cands += glob.glob(r"C:\Program Files\ParaView*\bin\paraview.exe")
    cands += glob.glob(os.path.expanduser(r"~\Documents\ParaView*\bin\paraview.exe"))
    cands += glob.glob(r"C:\ParaView*\bin\paraview.exe")
    for c in cands:
        if os.path.isfile(c):
            config_set("paraview_path", c)
            return c
    return None


# ==============================================================================
# DECK HANDLING
# ==============================================================================
# Radioss block format include card: '#include file.inc' or '/INCLUDE file.inc'.
_INCLUDE_RE = re.compile(r"^\s*(?:#include|/INCLUDE)\s+(.+?)\s*$", re.IGNORECASE)


def included_files(deck_path):
    """Paths named by include cards in a deck, relative to the deck folder."""
    out = []
    try:
        with open(deck_path, "r", errors="ignore") as f:
            for line in f:
                m = _INCLUDE_RE.match(line)
                if m:
                    out.append(m.group(1).strip().strip('"'))
    except Exception:
        pass
    return out


def stage_deck(starter_deck, log):
    """Copy the starter deck, its include files and any .inc in the run folder
    into <run folder>/_preview/<job>/. Returns the preview folder."""
    run_folder = os.path.dirname(os.path.abspath(starter_deck))
    jobname = os.path.basename(starter_deck)[:-len("_0000.rad")]
    work = os.path.join(run_folder, PREVIEW_DIRNAME, jobname)
    if os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    shutil.copy2(starter_deck, os.path.join(work, f"{jobname}_0000.rad"))

    staged = 0
    for rel in included_files(starter_deck):
        src = rel if os.path.isabs(rel) else os.path.join(run_folder, rel)
        if not os.path.isfile(src):
            log(f"  include not found, skipped: {rel}")
            continue
        dst = os.path.join(work, rel) if not os.path.isabs(rel) \
            else os.path.join(work, os.path.basename(rel))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        staged += 1
    for pat in ("*.inc", "*.INC"):
        for src in glob.glob(os.path.join(run_folder, pat)):
            dst = os.path.join(work, os.path.basename(src))
            if not os.path.isfile(dst):
                shutil.copy2(src, dst)
                staged += 1
    log(f"  staged {jobname}_0000.rad + {staged} include file(s) in {work}")
    return work, jobname


def write_engine_deck(work, jobname, tstop):
    """Write <job>_0001.rad: one animation frame at T=0, then stop."""
    path = os.path.join(work, f"{jobname}_0001.rad")
    with open(path, "w") as f:
        f.write(
            "#RADIOSS ENGINE\n"
            f"/RUN/{jobname}/1\n"
            f"{tstop}\n"
            "/ANIM/DT\n"
            "0.0 1.0\n"
            "/ANIM/ELEM/VONM\n"
            "/ANIM/VECT/DISP\n"
            "/END\n"
        )
    return path


def run_tool(cmd, cwd, log):
    """Run a solver binary, tee its output, return the exit code."""
    log(f"> {' '.join(cmd)}")
    try:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1,
                             creationflags=NO_WINDOW)
    except FileNotFoundError:
        log(f"  {cmd[0]} not found on PATH - add the OpenCourant exec folder to PATH.")
        return 127
    for line in iter(p.stdout.readline, ""):
        if line.strip():
            log("  " + line.rstrip())
    p.wait()
    return p.returncode


def convert_first_anim(work, jobname, log):
    """Convert the lowest-numbered animation file to <job>_preview.vtk.
    Returns the .vtk path, or None."""
    anims = sorted(glob.glob(os.path.join(work, f"{jobname}A[0-9]*")))
    anims = [a for a in anims if not a.lower().endswith(".vtk")]
    if not anims:
        log("  no animation file was written - see the _0001.out listing.")
        return None
    anim = os.path.basename(anims[0])
    out_path = os.path.join(work, f"{jobname}_preview.vtk")
    log(f"> {ANIM2VTK} {anim}")
    try:
        with open(out_path, "wb") as out:
            subprocess.run([ANIM2VTK, anim], cwd=work, stdout=out,
                           creationflags=NO_WINDOW)
    except FileNotFoundError:
        log(f"  {ANIM2VTK} not found on PATH - no VTK written.")
        if os.path.isfile(out_path):
            os.remove(out_path)
        return None
    # Legacy ASCII VTK starts with '# vtk'. Anything else is rejected by
    # ParaView with 'no reader found'.
    with open(out_path, "rb") as fh:
        if fh.read(5) != b"# vtk":
            log(f"  {os.path.basename(out_path)} has a bad header - removed.")
            os.remove(out_path)
            return None
    return out_path


# ==============================================================================
# GUI
# ==============================================================================
class RadPreview(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Rad preview  -  one-cycle deck check")
        self.geometry("860x600")
        self.minsize(640, 420)
        self.configure(bg=UI["bg"])

        self.decks = []
        self.threads = tk.StringVar(value="4")
        self.open_pv = tk.BooleanVar(value=True)
        self._busy = False

        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=8, pady=(8, 4))
        tk.Button(bar, text="Add decks...", command=self.cmd_add,
                  bg=UI["btn"], fg=UI["btn_fg"], width=14).pack(side=tk.LEFT)
        tk.Button(bar, text="Remove", command=self.cmd_remove,
                  bg=UI["btn"], fg=UI["btn_fg"], width=10).pack(side=tk.LEFT, padx=4)
        tk.Button(bar, text="Clear", command=self.cmd_clear,
                  bg=UI["btn"], fg=UI["btn_fg"], width=10).pack(side=tk.LEFT)
        ttk.Label(bar, text="Threads:").pack(side=tk.LEFT, padx=(14, 2))
        ttk.Entry(bar, textvariable=self.threads, width=5).pack(side=tk.LEFT)
        ttk.Checkbutton(bar, text="Open in ParaView",
                        variable=self.open_pv).pack(side=tk.LEFT, padx=10)
        self.btn_preview = tk.Button(bar, text="Preview", command=self.cmd_preview,
                                     bg=UI["btn"], fg=UI["btn_fg"], width=12)
        self.btn_preview.pack(side=tk.RIGHT)

        self.listbox = tk.Listbox(self, height=6, selectmode=tk.EXTENDED,
                                  activestyle="none")
        self.listbox.pack(fill=tk.X, padx=8, pady=4)

        self.console = tk.Text(self, bg=UI["console_bg"], fg=UI["console_fg"],
                               insertbackground=UI["console_fg"],
                               font=("Consolas", 9), wrap=tk.NONE)
        self.console.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))
        self.log("Select one or more <job>_0000.rad starter decks, then press Preview.")
        for exe in (STARTER, ENGINE, ANIM2VTK):
            if shutil.which(exe) is None:
                self.log(f"WARNING: {exe} is not on PATH.")

    # ---------------------------------------------------------------- helpers
    def log(self, msg):
        self.console.insert(tk.END, msg + "\n")
        self.console.see(tk.END)

    def log_safe(self, msg):
        """log() from a worker thread."""
        self.after(0, self.log, msg)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for d in self.decks:
            self.listbox.insert(tk.END, d)

    # ---------------------------------------------------------------- buttons
    def cmd_add(self):
        paths = filedialog.askopenfilenames(
            title="Select starter deck(s)  -  <job>_0000.rad",
            filetypes=[("Radioss starter deck", "*_0000.rad"),
                       ("Radioss deck", "*.rad"),
                       ("All files", "*.*")])
        for p in paths:
            p = os.path.abspath(p)
            if not p.endswith("_0000.rad"):
                self.log(f"Not a starter deck, skipped: {os.path.basename(p)}")
                continue
            if p not in self.decks:
                self.decks.append(p)
        self._refresh_list()

    def cmd_remove(self):
        for i in sorted(self.listbox.curselection(), reverse=True):
            del self.decks[i]
        self._refresh_list()

    def cmd_clear(self):
        self.decks = []
        self._refresh_list()

    def cmd_preview(self):
        if self._busy:
            return
        if not self.decks:
            self.log("No decks selected.")
            return
        try:
            nt = str(max(1, int(self.threads.get())))
        except ValueError:
            self.log("Threads must be a whole number.")
            return
        self._busy = True
        self.btn_preview.config(state=tk.DISABLED, text="Running")
        threading.Thread(target=self._worker, args=(list(self.decks), nt),
                         daemon=True).start()

    # ----------------------------------------------------------------- worker
    def _worker(self, decks, nt):
        log = self.log_safe
        try:
            for deck in decks:
                log(f"\n=== {os.path.basename(deck)} ===")
                if not os.path.isfile(deck):
                    log("  deck not found on disk.")
                    continue
                work, jobname = stage_deck(deck, log)

                if run_tool([STARTER, "-i", f"{jobname}_0000.rad", "-np", "1"],
                            work, log) not in (0, None):
                    log(f"  starter failed - see {jobname}_0000.out in {work}")
                    continue

                vtk = None
                for tstop in TSTOP_TRIES:
                    # Clear the previous attempt's animation files so the
                    # converter cannot pick up a stale one.
                    for old in glob.glob(os.path.join(work, f"{jobname}A[0-9]*")):
                        os.remove(old)
                    write_engine_deck(work, jobname, tstop)
                    log(f"  engine deck written with Tstop {tstop}")
                    run_tool([ENGINE, "-i", f"{jobname}_0001.rad", "-nt", nt],
                             work, log)
                    vtk = convert_first_anim(work, jobname, log)
                    if vtk:
                        break
                if not vtk:
                    log("  no VTK produced.")
                    continue

                log(f"  VTK: {vtk}")
                if self.open_pv.get():
                    self.after(0, self._launch_paraview, vtk)
        except Exception as e:
            log(f"Preview error: {e}")
        finally:
            self.after(0, self._done)

    def _done(self):
        self._busy = False
        self.btn_preview.config(state=tk.NORMAL, text="Preview")

    def _launch_paraview(self, vtk):
        """Main thread: the file dialog for a missing paraview.exe needs it."""
        pv = find_paraview()
        if not pv:
            pv = filedialog.askopenfilename(
                title="Locate paraview.exe (in ParaView's bin folder)",
                filetypes=[("paraview", "paraview.exe"), ("Executables", "*.exe")])
            if not pv:
                self.log("ParaView not set - the .vtk is on disk.")
                return
            config_set("paraview_path", pv)
        try:
            subprocess.Popen([pv, vtk], cwd=os.path.dirname(vtk),
                             creationflags=NO_WINDOW)
            self.log(f"ParaView launched on {os.path.basename(vtk)}.")
        except Exception as e:
            self.log(f"ParaView launch failed: {e}")


def main():
    if os.name != "nt":
        print("rad_preview.py targets Windows (starter_win64 / engine_win64 / "
              "anim_to_vtk_win64).")
    app = RadPreview()
    # Decks passed on the command line are pre-loaded.
    for a in sys.argv[1:]:
        p = os.path.abspath(a)
        if p.endswith("_0000.rad") and os.path.isfile(p):
            app.decks.append(p)
    app._refresh_list()
    app.mainloop()


if __name__ == "__main__":
    main()
