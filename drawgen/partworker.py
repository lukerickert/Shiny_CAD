# -*- coding: utf-8 -*-
"""The part worker: the geometry requests of the Part tab run in a separate process, so that a build that does not
return (a Boolean on bad geometry) can be stopped. Cancel in the Part tab ends that process; the next request
starts a new one. The worker keeps the build cache (part._BUILD_CACHE) between requests; after a Cancel the cache
is empty and the next build starts from the file again.

The server (web.py) forwards a request as (path, method, JSON body) over a pipe; the worker runs the same Flask
view through a test client of the same app and sends back (status code, body, mimetype, headers). The forwarding
is on when the environment variable DRAWGEN_PART_WORKER is "1" (run.py sets it); the tests run the views in
process."""
import multiprocessing
import os
import threading

# set in the worker process: the forwarding wrappers run the real view there
IN_WORKER = False


def enabled():
    return not IN_WORKER and os.environ.get("DRAWGEN_PART_WORKER", "0") == "1"


class Cancelled(Exception):
    pass


def _serve(conn):
    """Worker loop: runs the forwarded requests through a test client of the app."""
    global IN_WORKER
    IN_WORKER = True
    import atexit
    from . import web
    atexit.register(web.cleanup)          # the worker's own temporary folder
    client = web.app.test_client()
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            return
        if msg is None:
            return
        path, method, payload = msg
        try:
            r = client.open(path, method=method, json=payload)
            headers = [(k, v) for k, v in r.headers.items() if k.lower() in ("content-disposition", "content-type")]
            conn.send((r.status_code, r.get_data(), r.mimetype, headers))
        except Exception as e:  # noqa: BLE001
            import json
            conn.send((500, json.dumps({"error": "worker: %s" % e}).encode("utf-8"), "application/json", []))


class PartWorker:
    """One worker process, requests one at a time; cancel() ends the process (and the running request)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.conn = None
        self.generation = 0
        self.busy = False

    def _start(self):
        ctx = multiprocessing.get_context("spawn")
        parent, child = ctx.Pipe()
        self.proc = ctx.Process(target=_serve, args=(child,), daemon=True, name="shinycad-part-worker")
        self.proc.start()
        child.close()
        self.conn = parent
        self.generation += 1

    def _alive(self):
        return self.proc is not None and self.proc.is_alive()

    def warm(self):
        """Starts the worker (at server start, so that the first request does not wait for the imports)."""
        with self.lock:
            if not self._alive():
                self._start()

    def call(self, path, method, payload):
        """(status, body, mimetype, headers) of the request run in the worker. Raises Cancelled when the worker
        was ended by cancel() while the request ran."""
        with self.lock:
            if not self._alive():
                self._start()
            proc, conn, gen = self.proc, self.conn, self.generation
            self.busy = True
            try:
                conn.send((path, method, payload))
                while True:
                    if conn.poll(0.2):
                        try:
                            return conn.recv()
                        except (EOFError, OSError):
                            raise Cancelled()
                    if not proc.is_alive() or gen != self.generation:
                        raise Cancelled()
            finally:
                self.busy = False

    def cancel(self):
        """Ends the worker process; a request running in it is lost. Returns True when a process was ended."""
        proc = self.proc
        if proc is None:
            return False
        was = proc.is_alive()
        try:
            proc.terminate()
            proc.join(5)
            if proc.is_alive():
                proc.kill()
                proc.join(5)
        except Exception:
            pass
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception:
            pass
        self.proc, self.conn = None, None
        self.generation += 1
        return was

    def shutdown(self):
        self.cancel()


WORKER = PartWorker()
