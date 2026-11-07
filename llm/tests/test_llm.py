# -*- coding: utf-8 -*-
"""Tests of the llm package: deck tools, document index, tool dispatch and the chat loop against a fake server.
Run from the program folder: python -m pytest llm/tests"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from llm import chat, decks, docindex, tools  # noqa: E402

DECK = """** test deck
*HEADING
two tets
*NODE
1, 0, 0, 0
2, 10, 0, 0
3, 0, 10, 0
4, 0, 0, 10
5, 10, 10, 10
*ELEMENT, TYPE=C3D4, ELSET=PART_A
1, 1, 2, 3, 4
*ELEMENT, TYPE=C3D4, ELSET=PART_B
2, 2, 3, 4, 5
*NSET, NSET=FIX
1, 2, 3
*NSET, NSET=LOADED
5
*SURFACE, NAME=SA, TYPE=ELEMENT
1, S3
*SURFACE, NAME=SB, TYPE=ELEMENT
2, S1
*MATERIAL, NAME=STEEL
*ELASTIC
210000, 0.3
*DENSITY
7.85e-9
*SOLID SECTION, ELSET=PART_A, MATERIAL=STEEL
*SOLID SECTION, ELSET=PART_B, MATERIAL=STEEL
*TIE, NAME=BOND_AB, POSITION TOLERANCE=0.1
SB, SA
*STEP
*STATIC
1., 1.
*BOUNDARY
FIX, 1, 3, 0.
*CLOAD
LOADED, 3, 500.
*NODE FILE
U
*END STEP
"""


@pytest.fixture()
def deck(tmp_path):
    p = tmp_path / "two_tets.inp"
    p.write_text(DECK)
    decks.DECKS.clear()
    return decks.open_deck(str(p))


def test_summary(deck):
    s = decks.deck_summary(deck)
    assert deck == "two_tets"
    assert s["nodes"]["count"] == 5 and s["elements"] == 2
    assert s["element_types"] == [{"type": "C3D4", "count": 2}]
    assert s["constraints"] == {"*TIE": 1}
    assert s["steps"][0]["procedure"] == "STATIC"
    assert s["steps"][0]["cload_total"] == [0.0, 0.0, 500.0]
    assert s["materials"][0]["E"] == 210000


def test_items_lines_mesh(deck):
    r = decks.list_items(deck, "constraint", "bond*")
    assert r["matches"] == 1 and "SB" in r["rows"][0]["definition"]
    assert decks.list_items(deck, "nset", "*")["total"] == 2
    f = decks.find_lines(deck, "*tie", kind="keyword")
    assert f["matches"] == 1 and f["lines"][0].startswith("%d: *TIE" % (DECK.splitlines().index("*TIE, NAME=BOND_AB, POSITION TOLERANCE=0.1") + 1))
    assert decks.find_lines(deck, "5", kind="node")["lines"] == ["9: 5, 10, 10, 10"]
    rl = decks.read_lines(deck, 1, 500)
    assert rl["total_lines"] == len(DECK.splitlines()) and rl["lines"][0] == "1: ** test deck"
    q = decks.query_mesh(deck, "nodes", "near", point=[0, 0, 0], radius=10.5)
    assert q["count"] == 4


def test_compare(deck, tmp_path):
    p = tmp_path / "b.inp"
    p.write_text(DECK.replace("LOADED, 3, 500.", "LOADED, 3, 250."))
    b = decks.open_deck(str(p))
    d = decks.compare_decks(deck, b)["differences"]
    assert list(d) == ["steps"]


def test_dispatch(deck):
    assert json.loads(tools.call("nope", {}))["error"].startswith("unknown tool")
    assert "bad arguments" in json.loads(tools.call("deck_summary", {"wrong": 1}))["error"]
    r = json.loads(tools.call("get_steps", {"deck": "two_tets", "procedure": "STATIC"}))
    assert r["ignored_arguments"] == ["procedure"] and r["steps"][0]["procedure"] == "STATIC"
    assert "unknown deck" in json.loads(tools.call("deck_summary", '{"deck": "x"}'))["error"]
    assert json.loads(tools.call("deck_summary", '{"deck": "two_tets"}'))["nodes"]["count"] == 5
    names = {t["function"]["name"] for t in tools.TOOLS}
    assert names == set(tools.DISPATCH)


def test_docindex(tmp_path):
    folder, db = tmp_path / "docs", str(tmp_path / "i.db")
    folder.mkdir()
    (folder / "manual.md").write_text("# Intro\ntext\n# Tie constraint\nThe POSITION TOLERANCE of a *TIE sets the distance.\n")
    (folder / "notes.txt").write_text("\n".join("line %d" % i for i in range(130)) + "\nC3D10 elements\n")
    r = docindex.build(str(folder), db)
    assert r["added"] == 2 and not r["errors"]
    s = docindex.search("position tolerance tie", db=db)
    assert s["match"] == "all words" and s["results"][0]["doc"] == "manual.md" and s["results"][0]["page"] == 2
    assert docindex.search("c3d10", db=db)["results"][0]["page"] == 3
    assert docindex.search("tolerance unknownword", db=db)["match"] == "any word"
    assert "POSITION TOLERANCE" in docindex.read("manual.md", 2, db=db)["text"]
    assert docindex.build(str(folder), db)["unchanged"] == 2
    os.remove(folder / "notes.txt")
    assert docindex.build(str(folder), db)["removed"] == 1
    assert docindex.list_docs(db=db)["docs"] == [{"doc": "manual.md", "chunks": 2}]


def test_docindex_pdf(tmp_path):
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    pytest.importorskip("pypdfium2")
    folder, db = tmp_path / "docs", str(tmp_path / "i.db")
    folder.mkdir()
    c = canvas.Canvas(str(folder / "ccx.pdf"))
    c.drawString(72, 720, "Page one")
    c.showPage()
    c.drawString(72, 720, "CONTACT PAIR hard pressure overclosure")
    c.save()
    docindex.build(str(folder), db)
    r = docindex.search("pressure overclosure", db=db)["results"]
    assert r[0]["doc"] == "ccx.pdf" and r[0]["page"] == 2


class _Fake(BaseHTTPRequestHandler):
    bodies = []
    deck = "two_tets"

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Fake.bodies.append(body)
        if body["messages"][-1]["role"] == "user":
            msg = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "deck_summary", "arguments": json.dumps({"deck": _Fake.deck})}}]}
        else:
            n = json.loads(body["messages"][-1]["content"])["nodes"]["count"]
            msg = {"role": "assistant", "content": "The deck has %d nodes." % n}
        out = json.dumps({"choices": [{"message": msg}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def test_chat_loop(deck, tmp_path, monkeypatch):
    monkeypatch.setattr(docindex, "DB", str(tmp_path / "i.db"))
    monkeypatch.setattr(docindex.list_docs, "__defaults__", (str(tmp_path / "i.db"),))
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        log = []
        c = chat.Chat("m", "http://127.0.0.1:%d/v1" % srv.server_port, out=log.append)
        assert c.ask("How many nodes?") == "The deck has 5 nodes."
        assert log[0] == '[tool] deck_summary {"deck": "two_tets"}'
        first = _Fake.bodies[0]
        assert "two_tets (two_tets.inp)" in first["messages"][0]["content"]
        assert [m["role"] for m in c.messages] == ["user", "assistant", "tool", "assistant"]
    finally:
        srv.shutdown()


SOLVER_LOG = """CalculiX Version 2.22
 Using up to 8 cpu(s) for the stress calculation.

 *WARNING in gentiedmpc: no tied MPC
          generated for node       143754
          opposite master face found but
          too far away; distance:    1.7341
          tolerance:   0.2
 *WARNING in gentiedmpc: no tied MPC
          generated for node       143760
          opposite master face found but
          too far away; distance:    3.3305
          tolerance:   0.2
 *ERROR in e_c3d: nonpositive jacobian
        determinant in element 12

 Job finished
"""


def _run_folder(tmp_path):
    d = tmp_path / "an1"
    d.mkdir()
    (d / "solver.log").write_text(SOLVER_LOG)
    (d / "job.sta").write_text(" STEP INC ATT\n 1 1 1\n")
    (d / "job_WarnNodeMissTiedContact.nam").write_text("*NSET\n143754,\n")
    (d / "job.inp").write_text(DECK)
    return d


def test_runs(tmp_path):
    from llm import runs
    d = _run_folder(tmp_path)
    runs.set_run("an1", str(d))
    m = runs.solver_messages()
    assert (m["errors"], m["warnings"], m["groups_total"]) == (1, 2, 2)
    assert m["groups"][0]["kind"] == "ERROR" and m["groups"][0]["first_line"] == 14
    w = m["groups"][1]
    assert w["count"] == 2 and w["first_line"] == 4 and w["message"][-1] == "tolerance:   0.2"
    assert m["nam_files"] == ["job_WarnNodeMissTiedContact.nam"] and m["sta_tail"][-1] == " 1 1 1"
    assert runs.find_in_run_file("solver.log", "jacobian")["lines"][0].startswith("14: ")
    assert runs.read_run_file("job.sta", 2, 1)["lines"] == ["2:  1 1 1"]
    assert "without a path" in json.loads(tools.call("read_run_file", {"file": "../x"}))["error"]
    assert "1 *ERROR and 2 *WARNING" in runs.context_text()
    runs.set_run(None, None)
    assert "no analysis run folder" in json.loads(tools.call("run_files", {}))["error"]


def test_web(tmp_path, monkeypatch):
    flask = pytest.importorskip("flask")
    from llm import web as lweb
    d = _run_folder(tmp_path)
    monkeypatch.setattr(lweb, "_workdir", lambda name: str(d))
    monkeypatch.setattr(docindex, "DB", str(tmp_path / "i.db"))
    monkeypatch.setattr(docindex, "REFDOCS", str(tmp_path / "refdocs"))
    monkeypatch.setattr(docindex.list_docs, "__defaults__", (str(tmp_path / "i.db"),))
    monkeypatch.setattr(docindex.build, "__defaults__", (str(tmp_path / "refdocs"), str(tmp_path / "i.db"), None))
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/v1" % srv.server_port
    monkeypatch.setattr(chat, "settings", lambda: {"model": "m", "url": url, "temperature": 0.2})
    _Fake.deck = "job"
    app = flask.Flask("t")
    app.register_blueprint(lweb.bp)
    cl = app.test_client()
    try:
        assert cl.get("/llm/static/llm.js").status_code == 200
        st = cl.get("/api/llm/status").get_json()
        assert st["model"] == "m" and st["url"] == url
        jid = cl.post("/api/llm/ask", json={"conv": "x", "question": "nodes?", "analysis": {"name": "an1"}}).get_json()["job"]
        for _ in range(100):
            j = cl.get("/api/llm/job/" + jid).get_json()
            if j["state"] != "running":
                break
            __import__("time").sleep(0.05)
        assert j["state"] == "done" and j["answer"] == "The deck has 5 nodes."
        assert j["events"][0] == '[tool] deck_summary {"deck": "job"}'
        sysmsg = _Fake.bodies[-1]["messages"][0]["content"]
        assert "Current analysis: an1" in sysmsg and "job (job.inp)" in sysmsg and "1 *ERROR" in sysmsg
        assert cl.post("/api/llm/ask", json={"question": ""}).status_code == 400
        assert cl.post("/api/llm/clear", json={"conv": "x"}).get_json() == {"ok": True}
        assert lweb.CONVS["x"].messages == []
    finally:
        srv.shutdown()
        _Fake.deck = "two_tets"
