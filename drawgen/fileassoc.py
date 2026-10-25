# -*- coding: utf-8 -*-
"""Windows file types of the document files (.scpart, .scasm, .scsketch, .scfea, .scexp) for the current user
(HKEY_CURRENT_USER\\Software\\Classes, no administrator rights): a double-click in Explorer runs
run.py --open <file> with the Python of the running program."""
import os
import sys

from .packages import PKG_EXT

LABEL = {"part": "ShinyCAD part", "sketch": "ShinyCAD sketch", "assembly": "ShinyCAD assembly",
         "analysis": "ShinyCAD analysis", "explicit": "ShinyCAD explicit analysis"}


def _icon(app_dir):
    """shinycad.ico made from logo.png (Pillow), or "" when Pillow or logo.png is missing."""
    ico = os.path.join(os.environ.get("LOCALAPPDATA") or app_dir, "drawgen", "shinycad.ico")
    if os.path.isfile(ico):
        return ico
    png = os.path.join(app_dir, "logo.png")
    try:
        from PIL import Image
        os.makedirs(os.path.dirname(ico), exist_ok=True)
        Image.open(png).convert("RGBA").save(ico, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
        return ico
    except Exception:  # noqa: BLE001
        return ""


def command(app_dir, python=None):
    py = python or sys.executable
    return '"%s" "%s" --open "%%1"' % (py, os.path.join(app_dir, "run.py"))


def register(app_dir, python=None):
    """Registers the file types. Returns True when an entry was changed."""
    if not sys.platform.startswith("win"):
        return False
    import winreg
    cmd = command(app_dir, python)
    icon = _icon(app_dir)
    changed = False

    def setv(path, value, name=""):
        nonlocal changed
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\" + path) as k:
            try:
                cur = winreg.QueryValueEx(k, name)[0]
            except OSError:
                cur = None
            if cur != value:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
                changed = True

    for t, ext in PKG_EXT.items():
        prog = "ShinyCAD." + t
        setv(ext, prog)
        setv(prog, LABEL[t])
        setv(prog + "\\shell\\open\\command", cmd)
        if icon:
            setv(prog + "\\DefaultIcon", icon)
    if changed:
        try:
            import ctypes
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)    # SHCNE_ASSOCCHANGED
        except Exception:  # noqa: BLE001
            pass
    return changed
