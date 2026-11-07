# LLM queries of decks and reference documents

Chat with a local model about CalculiX / Abaqus .inp and Radioss .rad decks, the solver messages and files of an analysis, and reference documents.
The chat runs in the **Chat** card of the **Analysis** tab or in a console (`chat.bat`).
The model reads the decks through tool calls to the parsers of SHINYCAD (`drawgen/inpinfo.py`, `drawgen/inpquery.py`, `drawgen/inptext.py`) and searches the documents in `llm/refdocs/` through a keyword index.
The model is served by Ollama or llama.cpp `llama-server` on the same PC through the OpenAI-compatible API.

## Files

| File | Content |
|---|---|
| `chat.bat` | Starts the console chat in the Python environment of SHINYCAD; first run installs `requirements.txt` |
| `chat.py` | Console chat and the tool-call loop |
| `web.py` | Routes of the **Chat** card (Flask blueprint, registered by `drawgen/web.py`) |
| `static/llm.js` | **Chat** card of the **Analysis** tab (loaded by `drawgen/static/index.html`) |
| `tools.py` | Tool definitions (OpenAI function format) and dispatch |
| `decks.py` | Deck tools |
| `runs.py` | Run folder tools: files and solver messages of the analysis |
| `docindex.py` | Keyword index of `refdocs/` (SQLite FTS5, BM25 ranking) |
| `refdocs/` | Reference documents (not in git) |
| `refdocs.db` | Index of `refdocs/`, created at the first start (not in git) |
| `settings.json` | Optional: `{"model", "url", "temperature"}` in place of the defaults (not in git) |
| `tests/test_llm.py` | Tests |

## Model server

1. Install Ollama for Windows.
2. Set the context length as a user environment variable: `OLLAMA_CONTEXT_LENGTH` = `32768`.
3. Download the model: `ollama pull qwen3-coder:30b`.
4. Check that the model runs on the GPU: `ollama ps` after the first question.

The default model is `qwen3-coder:30b` (Q4_K_M, approx. 19 GB) at `http://localhost:11434/v1`.
On a Ryzen 7 5800U with Vega 8 graphics and 64 GB DDR4-3200, Ollama with Vulkan generates approx. 12 tokens/s with this model.
`--model` and `--url` select another model or server, for example `--model gemma4:26b-a4b-it-qat`, or `--url http://localhost:8080/v1` for `llama-server --jinja`.
Gemma 4 requires thinking switched off in the server (`{"enable_thinking":false}`) for tool calls.

## Chat card (Analysis tab)

**Chat** in the tool bar of the **Analysis** tab scrolls the side panel to the **Chat** card.
The card shows the model and the model server, or that the server is not reachable.
Ctrl+Enter or **Ask** sends the question.
**Stop** ends the answer after the current model request.
**Clear** clears the conversation.
**Tool calls** under a question lists the tool calls of its answer.

Each question passes the open analysis to the model:

| Item | Source |
|---|---|
| Run folder | `<project>/analysis/<analysis name>/`: `job.inp`, `solver.log`, `job.sta`, `job.cvg`, `job.dat`, report, `*.nam` |
| Deck `job` | `job.inp` of the run folder (written by **Mesh** or **Solve**) |
| Deck `source` | The .inp or .rad mesh file of **Geometry**, if the analysis uses one |
| Solver messages | Number of `*ERROR` and `*WARNING` messages of `solver.log` |

The conversation is kept until **Clear** or until the program is closed.
The reference documents are indexed at the first question after the program start.

## Console

```
llm\chat.bat [deck ...] [--run folder] [--model M] [--url U] [--temperature T] [--max-steps N] [--ask "question"]
```

A deck is given as a path (alias: the file name without extension) or as `alias=path`.
`--run` sets the run folder of an analysis for the run folder tools.
`--ask` answers one question and exits.
The start updates the index of `refdocs/` (new, changed and removed files).

| Command | Function |
|---|---|
| `/open [alias=]path` | Opens a deck |
| `/close alias` | Closes a deck |
| `/run folder` | Sets the run folder |
| `/decks` | Open decks |
| `/docs` | Indexed documents |
| `/reindex` | Updates the index of `refdocs/` |
| `/clear` | Clears the conversation |
| `/tools` | Tool names |
| `/quit` | Ends the chat |

Each tool call is printed as `[tool] name arguments`.
Each answer ends with the time and the prompt and completion token counts.

The first query of a deck parses the file and caches it until the file changes (approx. 13 s for a 115 MB deck of 1.1 million nodes).

## Tools

| Tool | Returns |
|---|---|
| `list_decks` | Open decks: alias, file name, size |
| `deck_summary` | Heading, node and element counts, node extent, element types, sections, materials (E, nu, density), constraint counts by keyword, steps with procedure and total concentrated load, mass, checks |
| `list_items` | Element sets, node sets, surfaces, constraints, sections, materials or keywords whose name matches a wildcard pattern |
| `get_steps` | Steps: procedure with parameters and data line, boundary condition targets, concentrated load totals, distributed loads, output requests |
| `query_mesh` | Nodes or elements by number, box, distance from a point, set, element type, attachment or quality criterion |
| `find_lines` | Line numbers and text of lines containing a text, starting with a keyword, or the data line of a node or element number |
| `read_lines` | Up to 200 deck lines with line numbers |
| `compare_decks` | Differences of two decks in counts, element types, sections, materials, constraints and steps |
| `search_docs` | Document, page, heading and snippet of the best matches of a keyword query |
| `read_doc` | Text of one page or section of a document (up to 6000 characters) |
| `list_docs` | Indexed documents |
| `run_files` | Files of the run folder with size and time |
| `solver_messages` | `*ERROR` and `*WARNING` messages of `solver.log` grouped by text (numbers replaced) with count, first line number and the first message in full; last lines of `solver.log` and `job.sta`; `*.nam` files |
| `read_run_file` | Up to 200 lines of a run folder file |
| `find_in_run_file` | Line numbers and text of the lines of a run folder file containing a text |

Tool results are limited to 6000 characters.
Arguments that a tool does not take are dropped and listed in `ignored_arguments` of the result.
Lists are limited by a `limit` argument and give the total count.

## Reference documents

Files in `refdocs/` and its subfolders are indexed as follows:

| Type | Unit of the index (`page`) |
|---|---|
| .pdf | Page (text layer; scanned pages without text are not found) |
| .md | Section, split at `#` headings |
| .txt, .f, .c, .h | Block of 60 lines |

`search_docs` first returns the chunks containing all words of the query and, if there are none, the chunks containing any of them.
The search matches words, not meaning: `bonded` does not find a page with only `tied`.
The CalculiX source (`ccx_2.22/src`, .f and .c files) in `refdocs/` makes the text of a solver message searchable, with the routine that writes it.

## Tests

```
python -m pytest llm/tests
```

The tests use a two-element deck, a run folder with a `solver.log` and a fake model server; no model is required.
The test of the **Chat** card routes requires Flask.
