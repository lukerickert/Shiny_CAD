@echo off
rem SHINYCAD: creates the Python environment on first start, then starts the server.
rem The environment is placed in %LOCALAPPDATA%\drawgen\venv to keep file paths below the
rem Windows 260 character limit. When requirements.txt changes, the packages are installed again.
cd /d "%~dp0"
set VENV=%LOCALAPPDATA%\drawgen\venv
if not exist "%VENV%\Scripts\python.exe" goto create
if not exist "%VENV%\installed.txt" goto install
fc /b requirements.txt "%VENV%\installed.txt" >nul 2>&1
if errorlevel 1 goto install
goto run

:create
echo Creating Python environment in %VENV%
set PY=
for %%v in (3.14 3.13 3.12 3.11 3.10) do (
  if not defined PY (
    py -%%v -c "import sys" >nul 2>&1 && set PY=py -%%v
  )
)
if not defined PY (
  echo Python 3.10 to 3.14 not found by the py launcher. Installed versions:
  py -0
  pause
  exit /b 1
)
echo Using %PY%
if exist "%VENV%" rmdir /s /q "%VENV%"
%PY% -m venv "%VENV%"
if errorlevel 1 (
  echo Creating the environment failed.
  pause
  exit /b 1
)
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip

:install
echo Installing packages from requirements.txt
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Package installation failed.
  pause
  exit /b 1
)
copy /y requirements.txt "%VENV%\installed.txt" >nul

:run
"%VENV%\Scripts\python.exe" run.py %*
