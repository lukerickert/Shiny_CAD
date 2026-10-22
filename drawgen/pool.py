# -*- coding: utf-8 -*-
"""Process pool shared by the drawing views (drawing.py) and the assembly builds (assembly.py).

Python runs one thread of Python code at a time, and the OpenCascade calls keep that lock while they run, so
geometry work in threads of the server uses one core. The pool runs the work in separate processes, one per core
(less one for the server, at most 5; DRAWGEN_WORKERS sets the number). The workers keep their caches (STEP files
read, sources loaded) between tasks. The processes are started with "spawn" on every platform (as on Windows)."""
import os
import threading

_POOL = None
_LOCK = threading.Lock()


def size():
    try:
        n = int(os.environ.get("DRAWGEN_WORKERS", 0))
    except ValueError:
        n = 0
    return n or max(1, min(5, (os.cpu_count() or 2) - 1))


def get():
    """The pool, or None with one worker or when processes cannot be started."""
    global _POOL
    with _LOCK:
        if _POOL is None:
            try:
                import concurrent.futures
                import multiprocessing
                n = size()
                _POOL = (concurrent.futures.ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context("spawn"))
                         if n > 1 else False)
            except Exception:
                _POOL = False
        return _POOL or None


def reset():
    """Drops a broken pool; the next get() starts a new one."""
    global _POOL
    with _LOCK:
        p, _POOL = _POOL, None
    if p:
        try:
            p.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


def shutdown():
    global _POOL
    with _LOCK:
        p, _POOL = _POOL, False
    if p:
        try:
            p.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


def _warm():
    from . import assembly  # noqa: F401  (imports build123d and OpenCascade in the worker)
    return os.getpid()


def warm():
    """Starts the workers and loads the geometry libraries in them (in the background, at server start)."""
    p = get()
    if p:
        for _ in range(size()):
            try:
                p.submit(_warm)
            except Exception:
                break
