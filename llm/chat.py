# -*- coding: utf-8 -*-
"""Console chat with a local model about open decks, an analysis run folder and the reference documents.

python -m llm.chat [deck ...] [--run folder] [--model M] [--url U] [--ask "question"]
    deck: path, or alias=path
Commands in the chat: /open [alias=]path, /close alias, /run folder, /decks, /docs, /reindex, /clear, /tools, /quit.
The model is served by Ollama or llama.cpp llama-server through the OpenAI-compatible API (/v1/chat/completions).
Defaults of model, URL and temperature: llm/settings.json ({"model", "url", "temperature"}) if present, else MODEL, URL.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from . import decks, docindex, runs, tools

MODEL = "qwen3-coder:30b"
URL = "http://localhost:11434/v1"
TEMPERATURE = 0.2
MAX_STEPS = 10
SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

SYSTEM = """You answer questions about finite-element analyses: input decks (CalculiX / Abaqus .inp, Radioss .rad),
CalculiX solver messages and output files, and the reference documents.
Use the tools to read decks, run files and documents; never guess their contents. Decks are too large to read whole:
start with deck_summary, then list_items, get_steps, find_lines, query_mesh and read_lines for detail.
For a solver error or warning: solver_messages, then the deck lines it refers to, then search_docs for the keyword or
the message text (the CalculiX manual and source may be indexed).
State values with units as in the deck (mm, N, MPa, t/mm^3 unless the deck says otherwise).
Give line numbers for deck and run file statements and document and page for statements from the documents.
Answer briefly, one fact per sentence.
Open decks: {decks}
Reference documents: {docs}
{context}"""


def settings():
    s = {"model": MODEL, "url": URL, "temperature": TEMPERATURE}
    try:
        with open(SETTINGS, "r", encoding="utf-8") as f:
            s.update({k: v for k, v in json.load(f).items() if k in s})
    except (OSError, ValueError):
        pass
    return s


def _post(url, body, timeout=1800):
    req = urllib.request.Request(url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def system_prompt(context=""):
    dl = ", ".join("%s (%s)" % (d["deck"], d["file"]) for d in decks.list_decks()["decks"]) or "none"
    docs = docindex.list_docs()["docs"]
    ds = ", ".join(d["doc"] for d in docs[:40]) + (" and %d more" % (len(docs) - 40) if len(docs) > 40 else "") if docs else "none"
    return SYSTEM.format(decks=dl, docs=ds, context=context or runs.context_text())


class Stopped(Exception):
    pass


class Chat:
    """Conversation with the model. out(text): receives the tool calls and the timing line. context(): text added to
    the system prompt at every request (default: the run folder of runs.RUN)."""

    def __init__(self, model=MODEL, url=URL, temperature=TEMPERATURE, max_steps=MAX_STEPS, out=print, context=None):
        self.model, self.url, self.temperature, self.max_steps, self.out = model, url, temperature, max_steps, out
        self.context = context
        self.messages = []
        self.stop = False

    def clear(self):
        self.messages = []

    def ask(self, question):
        """Sends the question, runs the tool calls of the model and returns its final answer."""
        self.stop = False
        self.messages.append({"role": "user", "content": question})
        for _ in range(self.max_steps):
            if self.stop:
                raise Stopped()
            sysmsg = system_prompt(self.context() if self.context else "")
            body = {"model": self.model, "messages": [{"role": "system", "content": sysmsg}] + self.messages,
                    "tools": tools.TOOLS, "stream": False}
            if self.temperature is not None:
                body["temperature"] = self.temperature
            t0 = time.time()
            res = _post(self.url, body)
            msg = res["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            self.messages.append({"role": "assistant", "content": msg.get("content") or "",
                                  **({"tool_calls": calls} if calls else {})})
            if not calls:
                u = res.get("usage") or {}
                self.out("[%.0f s, %s prompt + %s completion tokens]" % (time.time() - t0, u.get("prompt_tokens", "?"),
                                                                         u.get("completion_tokens", "?")))
                return msg.get("content") or ""
            for k, c in enumerate(calls):
                fn = c.get("function") or {}
                name, args = fn.get("name", ""), fn.get("arguments", "{}")
                self.out("[tool] %s %s" % (name, args if isinstance(args, str) else json.dumps(args)))
                self.messages.append({"role": "tool", "tool_call_id": c.get("id") or "call_%d" % k, "name": name,
                                      "content": tools.call(name, args)})
        return "(stopped after %d tool rounds without an answer)" % self.max_steps


def _open(spec):
    head, sep, tail = spec.partition("=")
    if sep and head.strip() and not any(ch in head for ch in "/\\:."):
        return decks.open_deck(tail, head.strip())
    return decks.open_deck(spec)


def main(argv=None):
    st = settings()
    ap = argparse.ArgumentParser(prog="python -m llm.chat", description=__doc__.splitlines()[0])
    ap.add_argument("decks", nargs="*", help="deck path, or alias=path")
    ap.add_argument("--run", help="run folder of an analysis (solver.log, job.sta, ...)")
    ap.add_argument("--model", default=st["model"])
    ap.add_argument("--url", default=st["url"], help="OpenAI-compatible base URL (default %(default)s)")
    ap.add_argument("--temperature", type=float, default=st["temperature"])
    ap.add_argument("--max-steps", type=int, default=MAX_STEPS)
    ap.add_argument("--ask", help="answer one question and exit")
    a = ap.parse_args(argv)

    r = docindex.build(log=print)
    print("reference documents: %d added, %d updated, %d removed, %d unchanged" % (r["added"], r["updated"], r["removed"], r["unchanged"]))
    for e in r["errors"]:
        print("  not indexed: " + e)
    for spec in a.decks:
        try:
            print("open: %s" % _open(spec))
        except decks.ToolError as e:
            print(e)
    if a.run:
        runs.set_run(os.path.basename(os.path.normpath(a.run)), a.run)
    chat = Chat(a.model, a.url, a.temperature, a.max_steps)

    def answer(q):
        try:
            print("\n" + chat.ask(q) + "\n")
        except urllib.error.URLError as e:
            print("no answer from %s: %s (is the model server running?)" % (a.url, e))

    if a.ask:
        answer(a.ask)
        return 0
    print("model %s at %s; /quit to end" % (a.model, a.url))
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line.startswith("/"):
            cmd, _, rest = line.partition(" ")
            rest = rest.strip()
            if cmd in ("/quit", "/exit"):
                return 0
            if cmd == "/open" and rest:
                try:
                    print("open: %s" % _open(rest))
                except decks.ToolError as e:
                    print(e)
            elif cmd == "/close" and rest:
                decks.close_deck(rest)
            elif cmd == "/run" and rest:
                runs.set_run(os.path.basename(os.path.normpath(rest)), rest)
                print(runs.context_text())
            elif cmd == "/decks":
                print(json.dumps(decks.list_decks(), indent=1))
            elif cmd == "/docs":
                print(json.dumps(docindex.list_docs(), indent=1))
            elif cmd == "/reindex":
                print(docindex.build(log=print))
            elif cmd == "/clear":
                chat.clear()
            elif cmd == "/tools":
                print(", ".join(t["function"]["name"] for t in tools.TOOLS))
            else:
                print("commands: /open [alias=]path, /close alias, /run folder, /decks, /docs, /reindex, /clear, /tools, /quit")
            continue
        try:
            answer(line)
        except KeyboardInterrupt:
            print("\n(stopped)")


if __name__ == "__main__":
    sys.exit(main())
