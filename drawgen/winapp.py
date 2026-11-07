# -*- coding: utf-8 -*-
"""Windows shortcuts of SHINYCAD: "SHINYCAD" on the Desktop and in the Start menu (Programs). The shortcut starts
run.py with pythonw.exe of the Python environment (no console window), with the SHINYCAD icon (shinycad.ico made from
logo.png, as for the document file types).

The shortcuts are made once per program folder and Python: %LOCALAPPDATA%\\drawgen\\shortcuts.json records the target,
so a shortcut the user deleted is not made again until the program folder or the Python environment changes, or
run.py --shortcuts (Options > Create shortcuts) asks for it."""
import json
import os
import subprocess
import sys

NAME = "SHINYCAD"
NO_WINDOW = 0x08000000


def pythonw():
    """pythonw.exe next to the running Python (python.exe when there is none)."""
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.isfile(cand) else exe


def _record_path():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "drawgen", "shortcuts.json")


def _ps(s):
    return "'" + str(s).replace("'", "''") + "'"


def make_shortcuts(app_dir):
    """Writes SHINYCAD.lnk on the Desktop and in the Start menu. Returns the paths written."""
    from .fileassoc import _icon
    target, run = pythonw(), os.path.join(app_dir, "run.py")
    icon = _icon(app_dir) or target
    script = (
        "$W = New-Object -ComObject WScript.Shell; $out = @(); "
        "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) { "
        "if (-not $d) { continue }; $p = Join-Path $d %s; $s = $W.CreateShortcut($p); "
        "$s.TargetPath = %s; $s.Arguments = %s; $s.WorkingDirectory = %s; $s.IconLocation = %s; "
        "$s.Description = 'SHINYCAD: drawings, parts, assemblies and analysis'; $s.Save(); $out += $p }; "
        "$out -join [char]10") % (_ps(NAME + ".lnk"), _ps(target), _ps('"%s"' % run), _ps(app_dir), _ps(icon + ",0"))
    import base64
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")       # no quoting of the command line
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
                       capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "powershell failed").strip()[:300])
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def ensure_shortcuts(app_dir, force=False):
    """Makes the shortcuts when they were not made for this program folder and Python (or force). Returns the paths
    written ([] when nothing was done)."""
    if not sys.platform.startswith("win"):
        return []
    want = {"target": pythonw(), "app_dir": os.path.abspath(app_dir)}
    rec = _record_path()
    try:
        with open(rec, "r", encoding="utf-8") as f:
            have = json.load(f)
    except (OSError, ValueError):
        have = None
    if have == want and not force:
        return []
    made = make_shortcuts(app_dir)
    os.makedirs(os.path.dirname(rec), exist_ok=True)
    with open(rec, "w", encoding="utf-8") as f:
        json.dump(want, f, indent=2)
    return made
