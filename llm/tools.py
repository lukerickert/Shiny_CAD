# -*- coding: utf-8 -*-
"""Tool definitions (OpenAI function format) and dispatch: call(name, arguments) -> JSON text for the model."""
import inspect
import json

from . import decks, docindex, runs

MAX_CHARS = 6000

_DECK = {"type": "string", "description": "Alias of an open deck (see list_decks)."}


def _fn(name, description, props=None, required=()):
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": props or {},
                                                            "required": list(required)}}}


TOOLS = [
    _fn("list_decks", "Open decks: alias, file name, size."),
    _fn("deck_summary", "Overview of a deck: heading, node and element counts, element types, sections, materials "
        "(E, nu, density), constraint counts by keyword, steps with procedure and total concentrated load, mass, checks.",
        {"deck": _DECK}, ["deck"]),
    _fn("list_items", "Rows of one kind whose name matches a wildcard pattern (* and ?, case-insensitive). "
        "elset: elements, types, section, material, volume, bbox. nset: nodes, bbox. surface: type, entries. "
        "constraint: keyword (*TIE, *CONTACT PAIR, *EQUATION, ...), name, definition. section, material, keyword: counts.",
        {"deck": _DECK,
         "kind": {"type": "string", "enum": list(decks._KINDS)},
         "pattern": {"type": "string", "description": "Wildcard pattern, default *."},
         "limit": {"type": "integer", "description": "Maximum rows, default 40."}}, ["deck", "kind"]),
    _fn("get_steps", "All steps of a deck: procedure (STATIC, FREQUENCY, DYNAMIC, ...), its parameters and data line, "
        "boundary condition targets, concentrated load totals (Fx, Fy, Fz, Mx, My, Mz), distributed loads, output requests.",
        {"deck": _DECK}, ["deck"]),
    _fn("query_mesh", "Nodes or elements of a deck. by: number (numbers '12, 40-50'), box ([xmin,ymin,zmin,xmax,ymax,zmax]), "
        "near (point [x,y,z] with radius and/or nearest), set (set name), type (element type), attached (numbers), "
        "quality (criterion inverted|aspect|warp|angle|edge|volume|coincident, value).",
        {"deck": _DECK,
         "what": {"type": "string", "enum": ["nodes", "elements"]},
         "by": {"type": "string", "enum": ["number", "box", "near", "set", "type", "attached", "quality"]},
         "numbers": {"type": "string"}, "box": {"type": "array", "items": {"type": "number"}},
         "point": {"type": "array", "items": {"type": "number"}}, "radius": {"type": "number"},
         "nearest": {"type": "integer"}, "set": {"type": "string"}, "type": {"type": "string"},
         "criterion": {"type": "string"}, "value": {"type": "number"},
         "limit": {"type": "integer", "description": "Maximum rows, default 20."}}, ["deck", "what", "by"]),
    _fn("find_lines", "Line numbers and text of deck lines. kind text: lines containing the text. kind keyword: lines "
        "starting with the keyword (e.g. *TIE, *STEP, *CONTACT PAIR, *CLOAD). kind node / element: the data line of that number.",
        {"deck": _DECK, "text": {"type": "string"},
         "kind": {"type": "string", "enum": ["text", "keyword", "node", "element"]},
         "limit": {"type": "integer", "description": "Maximum lines, default 20."},
         "from_line": {"type": "integer", "description": "First line searched, default 1."}}, ["deck", "text"]),
    _fn("read_lines", "Deck lines start .. start+count-1 with line numbers (count at most 200).",
        {"deck": _DECK, "start": {"type": "integer"}, "count": {"type": "integer"}}, ["deck", "start"]),
    _fn("compare_decks", "Differences between two decks: node and element counts, element types, sections, materials, "
        "constraint counts, steps.",
        {"a": _DECK, "b": _DECK}, ["a", "b"]),
    _fn("search_docs", "Keyword search of the reference documents (manuals, standards, briefs, notes). Returns document, "
        "page, heading and a snippet. Use exact terms as written in the documents (e.g. TIE, POSITION TOLERANCE, C3D10).",
        {"query": {"type": "string"}, "k": {"type": "integer", "description": "Number of results, default 5."}}, ["query"]),
    _fn("read_doc", "Full text of one page or section of a reference document (doc and page from search_docs).",
        {"doc": {"type": "string"}, "page": {"type": "integer"}}, ["doc", "page"]),
    _fn("list_docs", "Indexed reference documents."),
    _fn("run_files", "Files of the run folder of the current analysis (job.inp, solver.log, job.sta, job.cvg, job.dat, "
        "report, *.nam) with size and time."),
    _fn("solver_messages", "*ERROR and *WARNING messages of the CalculiX output (solver.log) of the current analysis, "
        "grouped by text with count, first line number and the full first message; the last lines of solver.log and "
        "job.sta; the *.nam node set files CalculiX wrote for warnings.",
        {"limit": {"type": "integer", "description": "Maximum message groups, default 20."}}),
    _fn("read_run_file", "Lines of a text file of the run folder with line numbers (count at most 200).",
        {"file": {"type": "string", "description": "File name from run_files, e.g. solver.log, job.sta, job.dat."},
         "start": {"type": "integer"}, "count": {"type": "integer"}}, ["file"]),
    _fn("find_in_run_file", "Line numbers and text of the lines of a run folder file containing a text.",
        {"file": {"type": "string"}, "text": {"type": "string"},
         "limit": {"type": "integer", "description": "Maximum lines, default 20."}}, ["file", "text"]),
]

DISPATCH = {
    "list_decks": decks.list_decks,
    "deck_summary": decks.deck_summary,
    "list_items": decks.list_items,
    "get_steps": decks.get_steps,
    "query_mesh": decks.query_mesh,
    "find_lines": decks.find_lines,
    "read_lines": decks.read_lines,
    "compare_decks": decks.compare_decks,
    "search_docs": docindex.search,
    "read_doc": docindex.read,
    "list_docs": docindex.list_docs,
    "run_files": runs.run_files,
    "solver_messages": runs.solver_messages,
    "read_run_file": runs.read_run_file,
    "find_in_run_file": runs.find_in_run_file,
}


def call(name, arguments):
    """Runs a tool. arguments: dict or JSON text. Returns JSON text, cut at MAX_CHARS."""
    if name not in DISPATCH:
        return json.dumps({"error": "unknown tool %r" % name})
    try:
        args = json.loads(arguments) if isinstance(arguments, str) and arguments.strip() else (arguments or {})
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
        fn = DISPATCH[name]
        known = set(inspect.signature(fn).parameters)
        extra = sorted(set(args) - known)
        res = fn(**{k: v for k, v in args.items() if k in known})
        if extra and isinstance(res, dict):
            res = dict(res, ignored_arguments=extra)
    except TypeError as e:
        res = {"error": "bad arguments for %s: %s" % (name, e)}
    except Exception as e:                                  # reported to the model, which can correct the call
        res = {"error": "%s: %s" % (type(e).__name__, e)}
    text = json.dumps(res, default=str, ensure_ascii=False)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + ' ... [cut at %d of %d characters; use a smaller limit or a narrower pattern]' % (MAX_CHARS, len(text))
    return text
