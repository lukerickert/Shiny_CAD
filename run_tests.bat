@echo off
rem SHINYCAD: runs the automatic tests (tests\) in the program's Python environment.
rem First run: installs pytest, pyflakes and Playwright with its Chromium browser (about 150 MB).
rem The tests use a temporary copy of config.json and a temporary projects folder.
rem   run_tests.bat            all tests
rem   run_tests.bat fast       without the browser tests
rem   run_tests.bat -k mate    tests whose name contains "mate" (any pytest options)
cd /d "%~dp0"
set VENV=%LOCALAPPDATA%\drawgen\venv
if not exist "%VENV%\Scripts\python.exe" (
  echo Start the program once with start.bat to create the Python environment.
  pause
  exit /b 1
)
set PY="%VENV%\Scripts\python.exe"
fc /b tests\requirements-test.txt "%VENV%\tests-installed.txt" >nul 2>&1
if errorlevel 1 (
  echo Installing the test packages
  %PY% -m pip install -r tests\requirements-test.txt || goto fail
  %PY% -m playwright install chromium || goto fail
  copy /y tests\requirements-test.txt "%VENV%\tests-installed.txt" >nul
)
set ARGS=%*
if /i "%1"=="fast" set ARGS=--ignore=tests\test_browser.py
%PY% -m pytest tests -p no:cacheprovider %ARGS%
echo.
pause
exit /b %errorlevel%

:fail
echo Installing the test packages failed.
pause
exit /b 1
