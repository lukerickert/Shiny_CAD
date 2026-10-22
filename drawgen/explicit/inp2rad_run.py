"""Runs inp2rad.py unchanged as a script: python inp2rad_run.py <inp2rad.py> <input.inp> [inp2rad arguments].

inp2rad.py imports tkinter at the top. When tkinter is not installed, a stub module is put in its place (the
batch mode with a file argument opens no dialog)."""
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
    runpy.run_path(script, run_name="__main__")
