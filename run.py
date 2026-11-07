# -*- coding: utf-8 -*-
"""Starts SHINYCAD at http://localhost:<port> and opens the browser: the system default, or the command in
config.local.json "browser" (Options dialog, or --browser): an executable path, optionally with {url} where the address goes,
for example "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --app={url}.

Batch mode (no server, no browser; drawgen/batch.py):
    run.py --batch analysis <name> [--project <project>] [--mesh-only]
    run.py --batch explicit <name> [--project <project>] [--rad] [--radv 2025 | 2023]"""
import argparse
import atexit
import json
import multiprocessing
import os
import sys
import threading
import time
import webbrowser

# Windows: started with pythonw.exe (the SHINYCAD shortcut, start.bat) there is no console window; the output goes to
# %LOCALAPPDATA%\drawgen\shinycad.log and errors at the start are shown in a message box.
WINDOWLESS = sys.platform.startswith("win") and os.path.basename(sys.executable).lower() == "pythonw.exe"
LOG = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "drawgen", "shinycad.log")
NO_WINDOW, NEW_CONSOLE, DETACHED = 0x08000000, 0x00000010, 0x00000008


def log_to_file():
    """stdout and stderr to the log file (the previous run kept as shinycad.log.1)."""
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    try:
        if os.path.isfile(LOG):
            os.replace(LOG, LOG + ".1")
    except OSError:
        pass
    f = open(LOG, "a", encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = sys.stderr = f


def message(text, error=True):
    """A message box (windowless start), else the console."""
    print(text, flush=True)
    if WINDOWLESS:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, "SHINYCAD", 0x10 if error else 0x40)
        except Exception:  # noqa: BLE001
            pass


def hide_child_consoles():
    """Console programs started by the server (CalculiX, OpenCourant, ssh, taskkill, ...) open no console window
    of their own when the server has none (CREATE_NO_WINDOW unless a new console is asked for)."""
    import subprocess
    orig = subprocess.Popen.__init__

    def init(self, *a, **kw):
        cf = kw.get("creationflags") or 0
        if not cf & (NEW_CONSOLE | DETACHED):
            kw["creationflags"] = cf | NO_WINDOW
        orig(self, *a, **kw)
    subprocess.Popen.__init__ = init


def code_mtime(here):
    """Newest modification time of run.py and the Python files of drawgen (s)."""
    t = os.path.getmtime(os.path.join(here, "run.py"))
    for d, dirs, files in os.walk(os.path.join(here, "drawgen")):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for fn in files:
            if fn.endswith(".py"):
                try:
                    t = max(t, os.path.getmtime(os.path.join(d, fn)))
                except OSError:
                    pass
    return t


def running_instance(port):
    """{"app", "started", "pid", "root", "jobs"} of the SHINYCAD server on the port, or None."""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/app/info" % port, timeout=3) as r:
            info = json.loads(r.read().decode("utf-8"))
        return info if info.get("app") == "SHINYCAD" else None
    except Exception:  # noqa: BLE001
        return None


def stop_instance(port, wait=20.0):
    """Asks the server on the port to stop; True when the port is free within wait seconds."""
    import socket
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/api/app/quit" % port, data=b"{}", method="POST",
                                                      headers={"Content-Type": "application/json"}), timeout=5).read()
    except Exception:  # noqa: BLE001
        pass
    t0 = time.time()
    while time.time() - t0 < wait:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            time.sleep(0.3)
        finally:
            s.close()
    return False


def open_browser(cmd, url):
    """Opens url with the browser command (empty: the system default browser)."""
    cmd = (cmd or "").strip()
    if not cmd:
        webbrowser.open(url)
        return
    import shlex
    import subprocess
    line = cmd.replace("{url}", url) if "{url}" in cmd else '%s "%s"' % (cmd if cmd.startswith('"') or " " not in cmd else '"%s"' % cmd, url)
    try:
        subprocess.Popen(line if os.name == "nt" else shlex.split(line))
    except OSError as e:
        print("Browser command failed (%s): %s; opening the system default browser" % (line, e))
        webbrowser.open(url)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "config.json"), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    try:                                   # settings of this PC (browser command)
        with open(os.path.join(here, "config.local.json"), "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    port = int(cfg.get("port", 8765))
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=port)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--browser", default=cfg.get("browser") or "", help="browser command; {url} is replaced by the address")
    ap.add_argument("--open", default="", help="document file (.scpart, .scasm, ...) opened in the program")
    ap.add_argument("--batch", nargs=2, metavar=("KIND", "NAME"), help="analysis | explicit and the document name: mesh or "
                    "solve the analysis, or write the model .inp of the explicit document, without the server")
    ap.add_argument("--project", default="", help="batch: the project of the document (default: the open project)")
    ap.add_argument("--mesh-only", action="store_true", help="batch analysis: mesh and write job.inp without solving")
    ap.add_argument("--rad", action="store_true", help="batch explicit: also the OpenCourant decks (inp2rad)")
    ap.add_argument("--radv", type=int, default=2025, choices=[2023, 2025], help="batch explicit: deck format")
    ap.add_argument("--restart", action="store_true", help="stop a running SHINYCAD server on the port and start again")
    ap.add_argument("--shortcuts", action="store_true", help="create the SHINYCAD shortcuts (Desktop, Start menu) again")
    a = ap.parse_args()
    if a.batch:
        os.environ.setdefault("DRAWGEN_PART_WORKER", "0")
        from drawgen import batch
        return batch.run(a.batch[0], a.batch[1], project=a.project or None, mesh_only=a.mesh_only, rad=a.rad, radv=a.radv)
    url = "http://localhost:%d" % a.port
    if a.open:
        from urllib.parse import quote
        url += "/?open=" + quote(os.path.abspath(a.open))

    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", a.port))
        busy = False
    except OSError:
        busy = True
    finally:
        probe.close()
    if busy:
        info = running_instance(a.port)
        if info is None:
            message("Port %d is in use by another program. Set another \"port\" in config.json, or end that program, "
                    "and start again." % a.port)
            return 1
        newer = code_mtime(here) > float(info.get("started") or 0) + 1 or os.path.normcase(info.get("root") or "") != os.path.normcase(here)
        if a.open or not (newer or a.restart):
            # the program is running and up to date: a new browser tab of it (with the file to open)
            if not a.no_browser:
                open_browser(a.browser, url)
            return 0
        if info.get("jobs") and not a.restart:
            message("SHINYCAD was updated, but %d job(s) are running in the running SHINYCAD. It is kept; Options > "
                    "Restart SHINYCAD loads the new version when the jobs are finished." % info["jobs"], error=False)
            if not a.no_browser:
                open_browser(a.browser, url)
            return 0
        print("Stopping the running SHINYCAD (%s)" % ("restart" if a.restart else "newer program files"), flush=True)
        if not stop_instance(a.port):
            message("The running SHINYCAD (process %s) did not stop. End it in Task Manager and start again." % info.get("pid"))
            return 1

    # the geometry requests of the Part tab run in a separate process (drawgen/partworker.py): Cancel in the Part
    # tab ends a build that does not return. DRAWGEN_PART_WORKER=0 in the environment keeps them in this process.
    os.environ.setdefault("DRAWGEN_PART_WORKER", "1")
    import time
    t0 = time.time()
    print("Starting SHINYCAD: loading the modules (the first start after an update or a restart of the PC can take "
          "about a minute)", flush=True)
    from drawgen import web, pool, partworker
    print("Modules loaded in %.0f s" % (time.time() - t0), flush=True)
    atexit.register(web.cleanup)
    atexit.register(pool.shutdown)
    threading.Thread(target=pool.warm, daemon=True).start()   # start the worker processes in the background
    if partworker.enabled():
        threading.Thread(target=partworker.WORKER.warm, daemon=True).start()
    threading.Thread(target=web.sync_loop, daemon=True).start()   # document files of the open project
    if sys.platform.startswith("win"):
        def shortcuts():
            try:
                from drawgen import winapp
                made = winapp.ensure_shortcuts(here, force=a.shortcuts)
                if made:
                    print("Shortcuts created: %s" % ", ".join(made), flush=True)
            except Exception as e:  # noqa: BLE001
                print("Shortcuts not created: %s" % e, flush=True)
        threading.Thread(target=shortcuts, daemon=True).start()
    try:
        from drawgen import fileassoc
        if fileassoc.register(here):
            print("File types .scpart .scasm .scsketch .scfea .scexp .sccam registered (double-click opens them in SHINYCAD)")
    except Exception as e:  # noqa: BLE001
        print("File types not registered: %s" % e)
    print("SHINYCAD running at %s (%s)" % (url, "Options > Quit SHINYCAD stops it" if WINDOWLESS else "Ctrl+C to stop"), flush=True)
    if not a.no_browser:
        threading.Timer(1.0, lambda: open_browser(a.browser, url)).start()
    web.app.run(host="127.0.0.1", port=a.port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if WINDOWLESS and multiprocessing.parent_process() is None:
        log_to_file()
        hide_child_consoles()
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        import traceback
        traceback.print_exc()
        message("SHINYCAD stopped with an error:\n\n%s\nThe output is in %s" % (traceback.format_exc(limit=3), LOG))
        raise SystemExit(1)
