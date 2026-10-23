# -*- coding: utf-8 -*-
"""Starts SHINYCAD at http://localhost:<port> and opens the browser: the system default, or the command in
config.local.json "browser" (Options dialog, or --browser): an executable path, optionally with {url} where the address goes,
for example "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --app={url}."""
import argparse
import atexit
import json
import multiprocessing
import os
import threading
import webbrowser


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
    a = ap.parse_args()

    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", a.port))
    except OSError:
        print("Port %d is already in use, probably by an earlier SHINYCAD window." % a.port)
        print("Close that window (or end python.exe in Task Manager) and start again.")
        return 1
    finally:
        probe.close()

    from drawgen import web, pool
    atexit.register(web.cleanup)
    atexit.register(pool.shutdown)
    threading.Thread(target=pool.warm, daemon=True).start()   # start the worker processes in the background
    url = "http://localhost:%d" % a.port
    print("SHINYCAD running at %s (Ctrl+C to stop)" % url)
    if not a.no_browser:
        threading.Timer(1.0, lambda: open_browser(a.browser, url)).start()
    web.app.run(host="127.0.0.1", port=a.port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
