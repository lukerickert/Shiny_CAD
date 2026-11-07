# -*- coding: utf-8 -*-
"""Keyword index of the reference documents in llm/refdocs/ (SQLite FTS5, BM25 ranking).

build()               adds new and changed files, removes deleted ones; returns counts
search(query, k)      ranked chunks: doc, page, heading, snippet
read(doc, page)       text of one chunk
list_docs()           indexed documents with their chunk count

Chunks: a PDF page (pypdfium2), a Markdown section (split at # headings), 60 lines of a text or source file (.txt,
.f, .c, .h; for example the CalculiX source, where the routines that print the solver messages are found).
"page" is the PDF page number (1-based), the section number of a Markdown file or the block number of a text file.
"""
import os
import re
import sqlite3
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
REFDOCS = os.path.join(HERE, "refdocs")
DB = os.path.join(HERE, "refdocs.db")
EXT = (".pdf", ".md", ".txt", ".f", ".c", ".h")
TEXT_BLOCK = 60
MAX_READ = 6000
_LOCK = threading.Lock()


def _connect(db=DB):
    c = sqlite3.connect(db, check_same_thread=False)
    c.execute("CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime REAL, size INTEGER, chunks INTEGER)")
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(doc, page UNINDEXED, heading, body, tokenize='unicode61')")
    return c


def _pdf(path):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path)
    try:
        for k in range(len(pdf)):
            page = pdf[k]
            tp = page.get_textpage()
            text = tp.get_text_range().replace("\r\n", "\n").replace("\r", "\n")
            tp.close()
            page.close()
            head = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
            yield k + 1, head[:120], text
    finally:
        pdf.close()


def _md(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        L = f.read().splitlines()
    sec, head, buf = 0, "", []
    for ln in L:
        if re.match(r"^#{1,6}\s", ln):
            if any(x.strip() for x in buf):
                sec += 1
                yield sec, head, "\n".join(buf)
            head, buf = ln.lstrip("#").strip()[:120], [ln]
        else:
            buf.append(ln)
    if any(x.strip() for x in buf):
        yield sec + 1, head, "\n".join(buf)


def _txt(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        L = f.read().splitlines()
    for k in range(0, len(L), TEXT_BLOCK):
        block = L[k:k + TEXT_BLOCK]
        head = next((ln.strip() for ln in block if ln.strip()), "")
        yield k // TEXT_BLOCK + 1, head[:120], "\n".join(block)


def _chunks(path):
    ext = os.path.splitext(path)[1].lower()
    return _pdf(path) if ext == ".pdf" else _md(path) if ext == ".md" else _txt(path)


def _files(folder):
    out = []
    for root, _dirs, files in os.walk(folder):
        for n in files:
            if n.lower().endswith(EXT) and not n.startswith("~$"):
                out.append(os.path.join(root, n))
    return sorted(out)


def _doc(path, folder):
    return os.path.relpath(path, folder).replace("\\", "/")


def build(folder=REFDOCS, db=DB, log=None):
    """Indexes new and changed files of the folder and drops removed ones. -> {"added", "updated", "removed", "unchanged", "errors"}"""
    out = {"added": 0, "updated": 0, "removed": 0, "unchanged": 0, "errors": []}
    with _LOCK:
        c = _connect(db)
        try:
            known = {r[0]: (r[1], r[2]) for r in c.execute("SELECT path, mtime, size FROM files")}
            present = set()
            for p in _files(folder):
                doc = _doc(p, folder)
                present.add(doc)
                st = os.stat(p)
                if doc in known and known[doc] == (st.st_mtime, st.st_size):
                    out["unchanged"] += 1
                    continue
                try:
                    rows = [(doc, page, head, body) for page, head, body in _chunks(p) if body.strip()]
                except Exception as e:                     # unreadable file: reported, index unchanged for it
                    out["errors"].append("%s: %s" % (doc, e))
                    continue
                c.execute("DELETE FROM chunks WHERE doc = ?", (doc,))
                c.executemany("INSERT INTO chunks(doc, page, heading, body) VALUES (?, ?, ?, ?)", rows)
                c.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?)", (doc, st.st_mtime, st.st_size, len(rows)))
                out["updated" if doc in known else "added"] += 1
                if log:
                    log("indexed %s (%d chunks)" % (doc, len(rows)))
                c.commit()
            for doc in set(known) - present:
                c.execute("DELETE FROM chunks WHERE doc = ?", (doc,))
                c.execute("DELETE FROM files WHERE path = ?", (doc,))
                out["removed"] += 1
            c.commit()
        finally:
            c.close()
    return out


def _fts(query, op):
    words = re.findall(r"[\w.]+", str(query or ""), re.UNICODE)
    words = [w.strip(".") for w in words if w.strip(".")]
    return (" %s " % op).join('"%s"' % w.replace('"', "") for w in words)


def search(query, k=5, db=DB):
    """Chunks containing all words of the query (ranked by BM25); if none, chunks containing any of them."""
    k = max(1, min(int(k or 5), 20))
    c = _connect(db)
    try:
        for op in ("AND", "OR"):
            q = _fts(query, op)
            if not q:
                return {"query": query, "results": []}
            rows = c.execute("SELECT doc, page, heading, snippet(chunks, 3, '[', ']', ' ... ', 24) FROM chunks "
                             "WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?", (q, k)).fetchall()
            if rows:
                return {"query": query, "match": "all words" if op == "AND" else "any word",
                        "results": [{"doc": d, "page": int(p), "heading": h, "snippet": s} for d, p, h, s in rows]}
        return {"query": query, "results": []}
    finally:
        c.close()


def read(doc, page, db=DB):
    c = _connect(db)
    try:
        r = c.execute("SELECT heading, body FROM chunks WHERE doc = ? AND page = ?", (doc, int(page))).fetchone()
        if r is None:
            r = c.execute("SELECT heading, body FROM chunks WHERE lower(doc) = lower(?) AND page = ?", (doc, int(page))).fetchone()
        if r is None:
            return {"error": "no chunk %s page %s" % (doc, page)}
        body = r[1]
        return {"doc": doc, "page": int(page), "heading": r[0], "text": body[:MAX_READ], "truncated": len(body) > MAX_READ}
    finally:
        c.close()


def list_docs(db=DB):
    c = _connect(db)
    try:
        return {"docs": [{"doc": p, "chunks": n} for p, n in c.execute("SELECT path, chunks FROM files ORDER BY path")]}
    finally:
        c.close()
