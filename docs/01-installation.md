[Contents](../README.md) · [2. Files →](02-files.md)

# 1. Installation (Windows)

1. Install Python 3.10 to 3.14 from python.org (64-bit). `py -0` lists the versions known to the py launcher.
2. Extract the zip file (right-click > **Extract All...**) to a folder with a short path, for example `C:\SHINYCAD`, with all files in the same folder.
3. Double-click `start.bat`.

`start.bat` uses the py launcher and selects the newest installed version from 3.14 to 3.10; without the py launcher it uses `python.exe` on PATH (not the Microsoft Store alias in `WindowsApps`) when it is version 3.10 to 3.14.
`start.bat` runs only from the extracted folder: started from inside the zip file, it reports the missing files and stops.
An environment whose Python no longer starts (Python removed or reinstalled) is created again.
The first start creates the environment in `%LOCALAPPDATA%\drawgen\venv` and installs `build123d`, `flask`, `ezdxf`, `reportlab`, `gmsh`, `shapely` and `fonttools` (approximately 500 MB, internet connection required).
Later starts use the existing environment. When `requirements.txt` differs from the installed copy, the packages are installed again before the start.
The server runs at `http://localhost:8765` and the browser opens automatically.
`start.bat` starts the program with `pythonw.exe` of the environment and its command window closes; `start.bat --console` runs it in the command window instead (Ctrl+C or closing the window stops it).
The start creates the shortcut **SHINYCAD** (SHINYCAD icon, `shinycad.ico` made from `logo.png`) on the Desktop and in the Start menu (Programs): `pythonw.exe run.py` in the program folder, without a console window. The shortcuts are made once per program folder and Python environment (`%LOCALAPPDATA%\drawgen\shortcuts.json`); a deleted shortcut is not made again until **Create shortcuts** (Options) or `run.py --shortcuts`.

| Start (shortcut, `start.bat`, a document file) | Behaviour |
|---|---|
| SHINYCAD not running | It starts and the browser opens |
| SHINYCAD running, program files (`run.py`, `drawgen\*.py`) unchanged since its start | A new browser tab of the running program (a document file: opened in it) |
| SHINYCAD running, program files changed since its start | The running program is stopped (`/api/app/quit`) and the new version starts; with CalculiX or OpenCourant jobs running it is kept and a message says so |
| `run.py --restart` | The running program is stopped and started again |
| The port in use by another program | Message: set another `port` in `config.json` or end that program |

**Options** ([section 3.1](03-use.md#31-options)): **Restart SHINYCAD** (the server is stopped and started again; the browser tab reloads when the new server answers), **Quit SHINYCAD** (the server stops), **Create shortcuts**. With jobs running, both ask first; a solver run started by the server goes on, but the new server does not follow it.
Without a console window, the output of the program is written to `%LOCALAPPDATA%\drawgen\shinycad.log` (the run before: `shinycad.log.1`), and an error at the start is shown in a message box. The console programs started by the server (CalculiX, OpenCourant, ssh) open no console window. The document file types open with `pythonw.exe` as well.

| Message or behaviour of `start.bat` | Cause and action |
|---|---|
| Windows protected your PC (SmartScreen) | The zip came from the internet. **More info** > **Run anyway**, or before extracting: right-click the zip > **Properties** > **Unblock** |
| run.py, requirements.txt or drawgen\web.py is missing | Started from inside the zip. Extract the zip (**Extract All...**) and start `start.bat` in the extracted folder |
| Python 3.10 to 3.14 was not found | Install Python 3.14 (64-bit) from python.org with **py launcher** and **Add python.exe to PATH** |
| Package installation failed | No connection to pypi.org (internet, proxy, firewall) on the first start |
| SHINYCAD stopped with an error | The message box and `shinycad.log` give the cause |
| Port 8765 is in use by another program | Set another `port` in `config.json`, or end that program |

Manual installation:

```
py -3.14 -m venv %LOCALAPPDATA%\drawgen\venv
%LOCALAPPDATA%\drawgen\venv\Scripts\python.exe -m pip install -r requirements.txt
%LOCALAPPDATA%\drawgen\venv\Scripts\python.exe run.py
```

The **Analysis** tab needs the CalculiX solver `ccx` and the **Explicit** tab needs OpenCourant ([section 1.1](#11-solvers)). ParaView is used for the strain extraction and the renders of the Explicit tab ([section 13.1](13-explicit.md#131-executables-and-settings-of-this-pc)).

`run.py --port 9000` sets a different port and `run.py --no-browser` does not open the browser.
`run.py --restart` stops the running program and starts again; `run.py --shortcuts` creates the shortcuts again.
`run.py --browser "<command>"` opens the program in that browser for this start ([section 3.1](03-use.md#31-options) **Browser**).
The server listens on 127.0.0.1 only.

## 1.1 Solvers

The solvers are not installed by `start.bat`.
Packages unpacked in the folder `solvers\` of the program are found without settings.

| Solver | Source | Installation |
|---|---|---|
| CalculiX `ccx` (Analysis tab) | PrePoMax, https://prepomax.fs.um.si/downloads/ (portable zip `PrePoMax v<version>.zip`, GPL-3.0, source https://gitlab.com/MatejB/PrePoMax); its `Solver` folder holds the Windows build of CalculiX | Unpack the zip to `solvers\` of the program (`solvers\PrePoMax v<version>\Solver\`), or to the user folder, Desktop, Downloads, Documents, `Program Files` or the root of the system drive. With **Solver (ccx)** empty, the program uses the first `ccx*.exe` in `solvers\` (up to 4 folder levels; `ccx.exe`, then the shortest name, so `ccx_static.exe` before `ccx_dynamic.exe`), then `ccx` on PATH, then the `Solver` folder of a `PrePoMax*` folder in those places ([section 12.1](12-analysis.md#121-solver)). The PrePoMax program itself needs the .NET Framework 4.8. Other CalculiX builds: https://github.com/calculix |
| OpenCourant, Windows (Explicit tab, local runs) | https://opencourant.org/downloads/, package `OpenCourant_win64.zip` (release `latest-20261011` on 2026-11-06; the page gives the SHA-256 of each package) | Check the hash: `certutil -hashfile OpenCourant_win64.zip SHA256`. Unpack it to `solvers\OpenCourant\`, so that `starter_win64.exe` is in `solvers\OpenCourant\exec\` or one folder deeper. `exec\` also holds `engine_win64.exe`, `anim_to_vtk_win64.exe` and `th_to_csv_win64.exe` (results view and energy curves). With **OpenCourant exec folder** empty, the program uses that folder and sets the environment of the package ([section 13.1](13-explicit.md#131-executables-and-settings-of-this-pc)) |
| OpenCourant, Linux (Explicit tab, remote runs) | `OpenCourant_linux64.zip` (x86-64) or `OpenCourant_linuxa64.zip` (arm64) of https://opencourant.org/downloads/ | Unpack on the server and set **Exec dir** to its `exec` folder ([section 13.6](13-explicit.md#136-solve)). The `_ompi` engine needs OpenMPI 4.1.2 in `/opt/openmpi`; the SMP engine runs without it |

OpenCourant: https://opencourant.org/ (source https://github.com/OpenCourant/OpenCourant, GNU AGPL v3).
The executable names (`starter_win64.exe`, `engine_win64.exe`, `anim_to_vtk_win64.exe`, `th_to_csv_win64.exe`; `starter_linux64_gf`, ...) and the package layout (`exec`, `extlib`, `hm_cfg_files`) are those of the OpenCourant packages.

Other locations: **Solver (ccx)** (Analysis tab, Settings) or `ccx` on PATH ([section 12.1](12-analysis.md#121-solver)); **OpenCourant exec folder** (Explicit tab, Solve panel) or PATH ([section 13.1](13-explicit.md#131-executables-and-settings-of-this-pc)).

[Contents](../README.md) · [2. Files →](02-files.md)
