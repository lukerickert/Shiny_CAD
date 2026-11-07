# -*- coding: utf-8 -*-
"""Flask blueprint of the Chat card of the Analysis tab (registered by drawgen/web.py when the llm package is present).

GET  /api/llm/status            {"model", "url", "server": bool, "models": [names], "docs": n}
POST /api/llm/ask               {"conv", "question", "analysis": {"name", "solver", "source": {"type", "path"}}} -> {"job"}
GET  /api/llm/job/<id>          {"state": "running" | "done" | "error", "events": [text], "answer", "error", "seconds"}
POST /api/llm/stop/<id>         stops the job after the current model request
POST /api/llm/clear             {"conv"}: clears the conversation
GET  /llm/static/<file>         llm.js
The current analysis sets the run folder (runs.RUN) and opens its input file as deck "job" and an imported .inp or
.rad mesh as deck "source".
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid

from flask import Blueprint, jsonify, request

from . import chat, decks, docindex, runs

HERE = os.path.dirname(os.path.abspath(__file__))
bp = Blueprint("llm", __name__, static_folder=os.path.join(HERE, "static"), static_url_path="/llm/static")
CONVS = {}          # conversation id -> chat.Chat
JOBS = {}           # job id -> {"state", "events", "answer", "error", "started", "chat"}
LOCK = threading.Lock()
_INDEXED = {"done": False}


def _err(msg, code=400):
    return jsonify({"error": msg}), code


def _workdir(name):
    from drawgen import web
    return web._fea_workdir(name)


def _set_context(a):
    """Run folder and decks of the analysis of the Analysis tab."""
    name = (a or {}).get("name") or None
    folder = _workdir(name) if name else None
    runs.set_run(name, folder)
    job = os.path.join(folder, "job.inp") if folder else None
    if job and os.path.isfile(job):
        decks.open_deck(job, "job")
    else:
        decks.close_deck("job")
    src = (a or {}).get("source") or {}
    if src.get("type") == "inp" and src.get("path") and os.path.isfile(src["path"]):
        decks.open_deck(src["path"], "source")
    else:
        decks.close_deck("source")
    L = [runs.context_text()]
    if (a or {}).get("solver"):
        L.append("Solver of the analysis: %s" % a["solver"])
    if src.get("type"):
        L.append("Geometry of the analysis: %s %s" % (src.get("type"), src.get("path") or src.get("name") or ""))
    L.append("Deck aliases: job = the input file written for the solver (run folder job.inp); source = the imported mesh file.")
    return "\n".join(L)


@bp.route("/api/llm/status", methods=["GET"])
def status():
    s = chat.settings()
    out = {"model": s["model"], "url": s["url"], "server": False, "models": [], "docs": 0}
    try:
        with urllib.request.urlopen(s["url"].rstrip("/") + "/models", timeout=2) as r:
            out["models"] = [m.get("id") for m in json.loads(r.read().decode("utf-8")).get("data", [])]
        out["server"] = True
    except (urllib.error.URLError, OSError, ValueError):
        pass
    try:
        out["docs"] = len(docindex.list_docs()["docs"])
    except Exception:
        pass
    return jsonify(out)


@bp.route("/api/llm/ask", methods=["POST"])
def ask():
    req = request.get_json(force=True)
    q = str(req.get("question") or "").strip()
    if not q:
        return _err("empty question")
    conv = str(req.get("conv") or "default")
    with LOCK:
        if any(j["state"] == "running" and j["conv"] == conv for j in JOBS.values()):
            return _err("a question of this chat is still being answered")
        s = chat.settings()
        c = CONVS.get(conv)
        if c is None:
            c = CONVS[conv] = chat.Chat(s["model"], s["url"], s["temperature"])
        c.model, c.url, c.temperature = s["model"], s["url"], s["temperature"]
        jid = uuid.uuid4().hex[:10]
        job = JOBS[jid] = {"state": "running", "events": [], "answer": None, "error": None, "started": time.time(),
                           "conv": conv, "chat": c}
    analysis = req.get("analysis") or {}

    def work():
        try:
            if not _INDEXED["done"]:
                r = docindex.build()
                _INDEXED["done"] = True
                if r["added"] or r["updated"] or r["removed"]:
                    job["events"].append("[index] reference documents: %d added, %d updated, %d removed" % (r["added"], r["updated"], r["removed"]))
            ctx = _set_context(analysis)
            c.out = job["events"].append
            c.context = lambda: ctx
            job["answer"] = c.ask(q)
            job["state"] = "done"
        except chat.Stopped:
            job["error"], job["state"] = "stopped", "error"
        except urllib.error.URLError as e:
            job["error"], job["state"] = "no answer from the model server %s: %s" % (c.url, e), "error"
        except Exception as e:                      # shown in the card
            job["error"], job["state"] = "%s: %s" % (type(e).__name__, e), "error"
    threading.Thread(target=work, daemon=True).start()
    return jsonify({"job": jid})


@bp.route("/api/llm/job/<jid>", methods=["GET"])
def job(jid):
    j = JOBS.get(jid)
    if j is None:
        return _err("unknown job", 404)
    out = {"state": j["state"], "events": list(j["events"]), "answer": j["answer"], "error": j["error"],
           "seconds": round(time.time() - j["started"], 1)}
    if j["state"] != "running":
        JOBS.pop(jid, None)
    return jsonify(out)


@bp.route("/api/llm/stop/<jid>", methods=["POST"])
def stop(jid):
    j = JOBS.get(jid)
    if j is None:
        return _err("unknown job", 404)
    j["chat"].stop = True
    return jsonify({"ok": True})


@bp.route("/api/llm/clear", methods=["POST"])
def clear():
    req = request.get_json(force=True, silent=True) or {}
    c = CONVS.get(str(req.get("conv") or "default"))
    if c is not None:
        c.clear()
    return jsonify({"ok": True})
