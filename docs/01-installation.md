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
Close the command window to stop the server.

| Message or behaviour of `start.bat` | Cause and action |
|---|---|
| Windows protected your PC (SmartScreen) | The zip came from the internet. **More info** > **Run anyway**, or before extracting: right-click the zip > **Properties** > **Unblock** |
| run.py, requirements.txt or drawgen\web.py is missing | Started from inside the zip. Extract the zip (**Extract All...**) and start `start.bat` in the extracted folder |
| Python 3.10 to 3.14 was not found | Install Python 3.14 (64-bit) from python.org with **py launcher** and **Add python.exe to PATH** |
| Package installation failed | No connection to pypi.org (internet, proxy, firewall) on the first start |
| SHINYCAD stopped with an error | The lines above the message give the cause, for example Port 8765 is already in use |

Manual installation:

```
py -3.14 -m venv %LOCALAPPDATA%\drawgen\venv
%LOCALAPPDATA%\drawgen\venv\Scripts\python.exe -m pip install -r requirements.txt
%LOCALAPPDATA%\drawgen\venv\Scripts\python.exe run.py
```

The **Analysis** tab needs the CalculiX solver `ccx` and the **Explicit** tab needs OpenCourant ([section 1.1](#11-solvers)). ParaView is used for the strain extraction and the renders of the Explicit tab ([section 13.1](13-explicit.md#131-executables-and-settings-of-this-pc)).

`run.py --port 9000` sets a different port and `run.py --no-browser` does not open the browser.
`run.py --browser "<command>"` opens the program in that browser for this start ([section 3.1](03-use.md#31-options) **Browser**).
The server listens on 127.0.0.1 only.

## 1.1 Solvers

The solvers are not installed by `start.bat`.
Packages unpacked in the folder `solvers\` of the program are found without settings.

| Solver | Source | Installation |
|---|---|---|
| CalculiX `ccx` (Analysis tab) | PrePoMax, https://prepomax.fs.um.si/downloads/ (portable zip `PrePoMax v<version>.zip`, GPL-3.0, source https://gitlab.com/MatejB/PrePoMax); its `Solver` folder holds the Windows build of CalculiX | Unpack the zip to `solvers\` of the program (`solvers\PrePoMax v<version>\Solver\`), or to the user folder, Desktop, Downloads, Documents, `Program Files` or the root of the system drive. With **Solver (ccx)** empty, the program uses the first `ccx*.exe` in `solvers\` (up to 4 folder levels; `ccx.exe`, then the shortest name, so `ccx_static.exe` before `ccx_dynamic.exe`), then `ccx` on PATH, then the `Solver` folder of a `PrePoMax*` folder in those places ([section 12.1](12-analysis.md#121-solver)). The PrePoMax program itself needs the .NET Framework 4.8. Other CalculiX builds: https://github.com/calculix |
| OpenRadioss, Windows (Explicit tab, local runs; use this until OpenCourant publishes a Windows package) | Last official OpenRadioss Windows release `latest-20260728`, archived by OpenCourant: https://github.com/OpenCourant/extlib/releases/tag/upstream-latest-20260728-win64, asset `OpenRadioss_win64.zip`. SHA-256 given on the page: `04dfecb0bf26ce071132cda86dc6861417c6a4127a389befe82b8c97341b3268` | Download `OpenRadioss_win64.zip`. Check the hash in PowerShell: `Get-FileHash .\OpenRadioss_win64.zip -Algorithm SHA256`. Unpack it to `solvers\OpenRadioss\`, so that `starter_win64.exe` is in `solvers\OpenRadioss\exec\` or one folder deeper (`solvers\OpenRadioss\OpenRadioss\exec\`). Check that `exec\` also holds `anim_to_vtk_win64.exe` and `th_to_csv_win64.exe` (results view and energy curves). With **OpenCourant exec folder** empty, the program uses that folder and sets the environment of the package ([section 13.1](13-explicit.md#131-executables-and-settings-of-this-pc)) |
| OpenCourant, Windows (Explicit tab, local runs) | https://github.com/OpenCourant/OpenCourant/releases (no Windows package on 2026-10-22) | When a Windows package is published: unpack it to `solvers\OpenCourant\` the same way and delete `solvers\OpenRadioss\`, so that one exec folder remains in `solvers\` |
| OpenCourant, Linux (Explicit tab, remote runs) | `OpenCourant_linux64.zip` of the same releases page | Unpack on the server and set **Exec dir** to its `exec` folder ([section 13.6](13-explicit.md#136-solve)). The `_ompi` engine needs OpenMPI 4.1.2 in `/opt/openmpi`; the SMP engine runs without it |

OpenCourant (https://github.com/OpenCourant) is the community continuation of OpenRadioss.
The executable names (`starter_win64.exe`, `engine_win64.exe`, `anim_to_vtk_win64.exe`, `th_to_csv_win64.exe`; `starter_linux64_gf`, ...) and the package layout (`exec`, `extlib`, `hm_cfg_files`) are those of OpenRadioss.
Siemens discontinued OpenRadioss on 2026-10-01 and deleted its GitHub repository and releases; the OpenRadioss download links of other documentation no longer work.
The OpenCourant release of 2026-10-05 (`latest-20261005`) has Linux x86_64 packages only (release notes: "Windows and Linux arm64 packages are not available yet").
Until OpenCourant publishes a Windows package, local runs on Windows use the archived OpenRadioss Windows package above, or a Windows build of the OpenCourant source (`build_windows.bat`, `INSTALL.md` of the repository).
The archive is a community-held copy of the official package; the page states that its SHA-256 matches an independently recorded official hash.

Other locations: **Solver (ccx)** (Analysis tab, Settings) or `ccx` on PATH ([section 12.1](12-analysis.md#121-solver)); **OpenCourant exec folder** (Explicit tab, Solve panel) or PATH ([section 13.1](13-explicit.md#131-executables-and-settings-of-this-pc)).

[Contents](../README.md) · [2. Files →](02-files.md)
