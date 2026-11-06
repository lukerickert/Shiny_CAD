# tests/audit

Bug and feature-gap audit of SHINYCAD. Three parts, run from the program folder; reports go to `_export\audit\`
(not in the repository).

| Command | Report | Content |
|---|---|---|
| `py tests\audit\audit_static.py` | `static.md`, `static.json` | Standard library only. Routes of `web.py` and `explicit/routes.py` against the API URLs used in the JS; bold control names of `docs\` not found in the interface; broken docs links; files named in the docs that do not exist; modules missing from the file list; TODO and "not supported" markers; stub functions |
| `run_tests.bat audit` | `routes.md`, `ui.md` (+ `.json`) | `tests\test_audit_routes.py`: every route called with an empty body, a list, a name and a text body; requests that raise (status 500), error texts that are Python exception messages, slow requests. `tests\test_audit_ui.py`: every tab opened with a part loaded, every visible button, menu item and select option exercised in headless Chromium; JavaScript errors, status 500, Python exception messages and interface error texts per control |
| `shinycad-audit` skill (Cowork) | `AUDIT_<date>.md` | Runs the static part, reads the reports of `run_tests.bat audit`, reviews each tab against `docs\` and `checklists.md`, and writes the findings list |

`run_tests.bat audit` needs the program environment (`start.bat` once) and the test packages (installed by the first `run_tests.bat`).
`AUDIT_TABS=part,cam` limits the interface audit to those tabs; `AUDIT_SHOTS=<folder>` saves a screenshot after each control with a finding.

Routes and controls that open dialogs or folders on this PC, delete documents, start solvers, change the projects root or write files of the program folder are skipped (lists `SKIP` and `STUB_URLS` in the test files).
