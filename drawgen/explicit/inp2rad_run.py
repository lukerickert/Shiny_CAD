"""Runs inp2rad.py unchanged as a script: python inp2rad_run.py <inp2rad.py> <input.inp> [inp2rad arguments].

inp2rad.py imports tkinter at the top. When tkinter is not installed, a stub module is put in its place (the
batch mode with a file argument opens no dialog). After inp2rad, the Radioss cards of the SHINYCAD constraints
(**RAD lines of the .inp: couplings, springs, joints, equations; radcards.py) go into the _0000.rad."""
import os
import runpy
import sys
import types


def _stub_tkinter():
    tk = types.ModuleType("tkinter")
    tk.filedialog = types.ModuleType("tkinter.filedialog")
    tk.messagebox = types.ModuleType("tkinter.messagebox")
    sys.modules["tkinter"] = tk
    sys.modules["tkinter.filedialog"] = tk.filedialog
    sys.modules["tkinter.messagebox"] = tk.messagebox


if __name__ == "__main__":
    try:
        import tkinter  # noqa: F401
        import tkinter.filedialog  # noqa: F401
        import tkinter.messagebox  # noqa: F401
    except ImportError:
        _stub_tkinter()
    script = sys.argv[1]
    sys.argv = [script] + sys.argv[2:]
    code = 0
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit as e:
        code = e.code
    inp = next((a for a in sys.argv[1:] if a.lower().endswith(".inp")), None)
    if inp and not code:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import radcards
        try:
            n = radcards.apply(inp)
            if n:
                print("SHINYCAD constraints: %d card lines written into the _0000.rad" % n)
        except FileNotFoundError as e:
            print("SHINYCAD constraints not written: %s" % e)
    sys.exit(code)
