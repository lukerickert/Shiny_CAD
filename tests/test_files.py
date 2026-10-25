# -*- coding: utf-8 -*-
"""Document files (.scpart, .scasm, ...): written next to project.json, read back after a change outside the program,
copied in, deleted, renamed; opened from and saved to a folder outside the project (linked file)."""
import json
import os
import shutil
import time
import zipfile

import pytest

from conftest import plate


def ok(r):
    assert r.status_code == 200, r.get_data(as_text=True)[:500]
    return r.get_json()


@pytest.fixture()
def fpj(client, web):
    """An open project "files_pj" (removed afterwards); the project "tests" is opened again at the end."""
    root0, cur0 = web.PROJECTS.root(), web.PROJECTS.current_name()
    ok(client.post("/api/projects", json={"name": "files_pj", "description": "", "open": True}))
    pdir = web.PROJECTS.project_dir("files_pj")
    try:
        yield pdir
    finally:
        web.PROJECTS.set_root(root0)
        web.PROJECTS.open(cur0)
        web.PROJECTS.forget(pdir)
        shutil.rmtree(pdir, ignore_errors=True)


def ext(d):
    """The extrude feature of a plate."""
    return next(f for f in d["features"] if f.get("type") == "extrude")


def names(zpath):
    with zipfile.ZipFile(zpath) as z:
        return z.namelist()


def doc(zpath):
    with zipfile.ZipFile(zpath) as z:
        return json.loads(z.read("document.json").decode("utf-8"))


def test_package_written_with_annotations(client, web, fpj):
    p = plate("pk_a")
    p["uid"] = "pkuid0000a1"
    ok(client.put("/api/part/file/pk_a", json=p))
    ok(client.put("/api/annotations/pkuid0000a1", json=[{"id": "n", "type": "note", "text": "PK NOTE"}]))
    r = web.PROJECTS.sync(force=True)
    assert "part:pk_a" in r["packed"]
    f = os.path.join(fpj, "pk_a.scpart")
    assert os.path.isfile(f)
    n = names(f)
    assert "shinycad.json" in n and "document.json" in n and "annotations/pkuid0000a1.json" in n
    with zipfile.ZipFile(f) as z:
        h = json.loads(z.read("shinycad.json"))
    assert h["format"] == "shinycad-package" and h["type"] == "part" and h["name"] == "pk_a"
    # unchanged: not written again
    assert web.PROJECTS.sync(force=True)["packed"] == []
    # a change of the drawing only: written again
    time.sleep(0.05)
    ok(client.put("/api/annotations/pkuid0000a1", json=[{"id": "n", "type": "note", "text": "PK NOTE 2"}]))
    assert "part:pk_a" in web.PROJECTS.sync(force=True)["packed"]
    # the Documents list shows the file
    d = next(x for x in ok(client.get("/api/project/docs"))["docs"] if x["name"] == "pk_a")
    assert d["package"] == "pk_a.scpart" and d["linked"] == ""


def test_package_changed_copied_in_and_deleted_outside(client, web, fpj):
    p = plate("pk_b")
    p["uid"] = "pkuid0000b1"
    ok(client.put("/api/part/file/pk_b", json=p))
    ok(client.put("/api/annotations/pkuid0000b1", json=[{"id": "n", "type": "note", "text": "B"}]))
    web.PROJECTS.sync(force=True)
    f = os.path.join(fpj, "pk_b.scpart")
    # copied in under another name (with spaces): a new document with a new uid and its own drawing
    shutil.copy(f, os.path.join(fpj, "pk b copy.scpart"))
    r = web.PROJECTS.sync(force=True)
    assert "part:pk_b_copy" in r["unpacked"] and os.path.isfile(os.path.join(fpj, "pk_b_copy.scpart"))
    cp = ok(client.get("/api/part/file/pk_b_copy"))
    assert cp["name"] == "pk_b_copy" and cp["uid"] != "pkuid0000b1"
    assert ok(client.get("/api/annotations/" + cp["uid"]))[0]["text"] == "B"
    # changed outside the program (a file from elsewhere with the same name): read, earlier state kept as a version
    other = os.path.join(os.path.dirname(fpj), "pk_b_other.scpart")
    with zipfile.ZipFile(f) as zi, zipfile.ZipFile(other, "w") as zo:
        for n in zi.namelist():
            b = zi.read(n)
            if n == "document.json":
                d = json.loads(b)
                ext(d)["depth"] = 33.0
                b = json.dumps(d).encode("utf-8")
            zo.writestr(n, b)
    time.sleep(0.05)
    shutil.copy(other, f)
    os.remove(other)
    ok(client.put("/api/part/file/pk_b", json=dict(p, note_pad="local change")))
    r = web.PROJECTS.sync(force=True)
    assert "part:pk_b" in r["unpacked"]
    assert ext(ok(client.get("/api/part/file/pk_b")))["depth"] == 33.0
    assert any(v["note"].startswith("before the change") for v in web.PROJECTS.versions("part", "pk_b"))
    # deleted outside the program: the document goes to trash
    os.remove(os.path.join(fpj, "pk_b_copy.scpart"))
    r = web.PROJECTS.sync(force=True)
    assert "part:pk_b_copy" in r["deleted"]
    assert not os.path.exists(web.PROJECTS.doc_path("part", "pk_b_copy"))
    assert any(fn.endswith("pk_b_copy.part.json") for fn in os.listdir(os.path.join(fpj, "trash")))


def test_rename_and_delete_follow_the_file(client, web, fpj):
    ok(client.put("/api/part/file/pk_c", json=plate("pk_c")))
    web.PROJECTS.sync(force=True)
    ok(client.post("/api/project/doc", json={"op": "rename", "type": "part", "name": "pk_c", "new": "pk_c2"}))
    assert not os.path.exists(os.path.join(fpj, "pk_c.scpart")) and os.path.isfile(os.path.join(fpj, "pk_c2.scpart"))
    web.PROJECTS.sync(force=True)
    assert doc(os.path.join(fpj, "pk_c2.scpart"))["name"] == "pk_c2"
    assert web.PROJECTS.doc_path("part", "pk_c2") and os.path.isfile(web.PROJECTS.doc_path("part", "pk_c2"))
    ok(client.post("/api/project/doc", json={"op": "delete", "type": "part", "name": "pk_c2"}))
    assert not os.path.exists(os.path.join(fpj, "pk_c2.scpart"))
    assert web.PROJECTS.sync(force=True)["unpacked"] == []


def test_open_loose_file_linked_and_save_as(client, web, fpj, tmp_path):
    ok(client.put("/api/part/file/pk_d", json=plate("pk_d")))
    out = tmp_path / "elsewhere"
    out.mkdir()
    # Save as file outside the project: written and linked
    r = ok(client.post("/api/file/saveas", json={"type": "part", "name": "pk_d", "path": str(out / "my part")}))
    lf = str(out / "my part.scpart")
    assert r["path"] == lf and r["linked"] == lf and os.path.isfile(lf)
    # a later save writes the linked file too
    time.sleep(0.05)
    ok(client.put("/api/part/file/pk_d", json=dict(plate("pk_d", t=12.0))))
    web.PROJECTS.sync(force=True)
    assert ext(doc(lf))["depth"] == 12.0
    d = next(x for x in ok(client.get("/api/project/docs"))["docs"] if x["name"] == "pk_d")
    assert d["linked"] == lf
    # a loose file opened: added to the open project under its file name and linked
    loose = str(out / "loose.scpart")
    shutil.copy(lf, loose)
    j = ok(client.post("/api/file/open", json={"path": loose}))
    assert j == {"type": "part", "name": "loose", "project": "files_pj", "linked": loose}
    assert ext(ok(client.get("/api/part/file/loose")))["depth"] == 12.0
    # changed outside: read at the next sync
    with zipfile.ZipFile(lf) as zi, zipfile.ZipFile(loose + ".x", "w") as zo:
        for n in zi.namelist():
            b = zi.read(n)
            if n == "document.json":
                dd = json.loads(b)
                ext(dd)["depth"] = 7.0
                b = json.dumps(dd).encode("utf-8")
            zo.writestr(n, b)
    time.sleep(0.05)
    os.replace(loose + ".x", loose)
    assert "part:loose" in web.PROJECTS.sync(force=True)["unpacked"]
    assert ext(ok(client.get("/api/part/file/loose")))["depth"] == 7.0
    # opened again: the same document
    assert ok(client.post("/api/file/open", json={"path": loose}))["name"] == "loose"
    # unlink: the file is no longer written
    ok(client.post("/api/file/unlink", json={"type": "part", "name": "loose"}))
    m0 = os.path.getmtime(loose)
    time.sleep(0.05)
    ok(client.put("/api/part/file/loose", json=plate("loose", t=5.0)))
    web.PROJECTS.sync(force=True)
    assert os.path.getmtime(loose) == m0
    # not a document file
    (out / "x.scpart").write_bytes(b"no zip")
    assert client.post("/api/file/open", json={"path": str(out / "x.scpart")}).status_code >= 400
    assert client.post("/api/file/open", json={"path": str(out / "x.txt")}).status_code >= 400


def test_assembly_file_with_parts_opened_in_another_project(client, web, fpj, tmp_path):
    ok(client.put("/api/part/file/pk_p1", json=plate("pk_p1")))
    comp = lambda cid, part: {"id": cid, "name": cid, "source": {"type": "part", "name": part}, "pos": [0, 0, 0], "rot": [0, 0, 0]}
    ok(client.put("/api/assembly/file/pk_asm", json={"name": "pk_asm", "components": [comp("c1", "pk_p1")], "next": 2}))
    f = str(tmp_path / "pk_asm.scasm")
    ok(client.post("/api/file/saveas", json={"type": "assembly", "name": "pk_asm", "path": f}))
    assert "uses/pk_p1.scpart" in names(f)
    # in a project folder: the file is read when that project is opened
    ok(client.post("/api/projects", json={"name": "files_pj2", "description": "", "open": False}))
    p2 = web.PROJECTS.project_dir("files_pj2")
    try:
        shutil.copy(f, os.path.join(p2, "pk_asm.scasm"))
        j = ok(client.post("/api/file/open", json={"path": os.path.join(p2, "pk_asm.scasm")}))
        assert j["project"] == "files_pj2" and j["name"] == "pk_asm" and j["linked"] == ""
        assert os.path.isfile(web.PROJECTS.doc_path("part", "pk_p1"))
        web.PROJECTS.sync(force=True)              # the background thread of run.py
        assert os.path.isfile(os.path.join(p2, "pk_p1.scpart"))
    finally:
        web.PROJECTS.open("files_pj")
        shutil.rmtree(p2, ignore_errors=True)


def test_step_import_carried_in_the_file(client, web, fpj, tmp_path):
    """A part with an imported STEP file: the STEP file goes into the document file and is placed in step_import/ of
    the project the file is opened in."""
    from drawgen import packages
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "partition_test.step")
    stp = tmp_path / "base geo.step"
    shutil.copy(src, stp)
    w = os.path.join(fpj, "work")
    with open(os.path.join(w, "pk_s.part.json"), "w") as fh:
        json.dump({"name": "pk_s", "version": 2, "features": [{"id": "f1", "type": "import", "path": str(stp)}]}, fh)
    f = str(tmp_path / "pk_s.scpart")
    packages.write(web.PROJECTS, w, "part", "pk_s", f)
    assert "step_import/base geo.step" in names(f)
    os.remove(stp)
    t, n = packages.extract(web.PROJECTS, fpj, f, "pk_s2")
    path = json.load(open(os.path.join(w, "pk_s2.part.json")))["features"][0]["path"]
    assert os.path.isfile(path) and os.path.dirname(path) == os.path.join(fpj, "step_import")


def test_file_type_command():
    from drawgen import fileassoc
    c = fileassoc.command(r"C:\app", r"C:\venv\python.exe")
    assert c.startswith('"C:\\venv\\python.exe" "') and c.endswith('run.py" --open "%1"')
