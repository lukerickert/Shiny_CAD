@echo off
rem SHINYCAD: creates the Python environment on first start, then starts the server.
rem The environment is placed in %LOCALAPPDATA%\drawgen\venv to keep file paths below the
rem Windows 260 character limit. When requirements.txt changes, the packages are installed again.
rem Python: the py launcher (newest of 3.14 to 3.10), else python.exe on PATH.
cd /d "%~dp0"
if not exist "%~dp0run.py" goto notextracted
if not exist "%~dp0requirements.txt" goto notextracted
if not exist "%~dp0drawgen\web.py" goto notextracted
set "VENV=%LOCALAPPDATA%\drawgen\venv"
if not exist "%VENV%\Scripts\python.exe" goto create
"%VENV%\Scripts\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 goto create
if not exist "%VENV%\installed.txt" goto install
fc /b requirements.txt "%VENV%\installed.txt" >nul 2>&1
if errorlevel 1 goto install
goto run

:notextracted
echo run.py, requirements.txt or drawgen\web.py is missing in %~dp0
echo Extract the whole zip file first: right-click the zip, Extract All..., then
echo double-click start.bat in the extracted SHINYCAD folder.
echo start.bat does not run from inside the zip file.
pause
exit /b 1

:create
echo Creating Python environment in %VENV%
set PY=
for %%v in (3.14 3.13 3.12 3.11 3.10) do (
  if not defined PY (
    py -%%v -c "import sys" >nul 2>&1 && set PY=py -%%v
  )
)
if defined PY goto havepy
rem no py launcher: python.exe on PATH (the Microsoft Store alias in WindowsApps is not Python)
for /f "delims=" %%p in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PY set PY="%%p"
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>&1
if errorlevel 1 goto badpython

:havepy
echo Using %PY%
if exist "%VENV%" rmdir /s /q "%VENV%"
%PY% -m venv "%VENV%"
if errorlevel 1 goto venvfail
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip

:install
echo Installing packages from requirements.txt (first start: approximately 500 MB)
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pipfail
copy /y requirements.txt "%VENV%\installed.txt" >nul

:run
"%VENV%\Scripts\python.exe" run.py %*
if errorlevel 1 goto runfail
exit /b 0

:nopython
echo Python 3.10 to 3.14 was not found: no py launcher and no python.exe on PATH.
echo Install Python 3.14 (64-bit) from https://www.python.org/downloads/windows/
echo with the options "py launcher" and "Add python.exe to PATH", then start again.
pause
exit /b 1

:badpython
echo %PY% is not Python 3.10 to 3.14:
%PY% --version
echo Install Python 3.14 (64-bit) from https://www.python.org/downloads/windows/ and start again.
pause
exit /b 1

:venvfail
echo Creating the environment in %VENV% failed.
pause
exit /b 1

:pipfail
echo Package installation failed. An internet connection is required on the first start;
echo a proxy or firewall that blocks pypi.org stops the installation.
pause
exit /b 1

:runfail
echo.
echo SHINYCAD stopped with an error. The lines above give the cause.
pause
exit /b 1
