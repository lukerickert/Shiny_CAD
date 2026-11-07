@echo off
rem SHINYCAD: console chat with a local model about .inp / .rad decks and the reference documents (llm\README.md).
rem   llm\chat.bat                                   chat, decks opened with /open
rem   llm\chat.bat C:\runs\model.inp ref=D:\x.inp    chat with two decks open (alias "model" and "ref")
rem   llm\chat.bat --model gemma4:26b-a4b-it-qat     another model
rem First run: installs pypdfium2 into the program's Python environment.
cd /d "%~dp0\.."
set VENV=%LOCALAPPDATA%\drawgen\venv
if not exist "%VENV%\Scripts\python.exe" (
  echo Start the program once with start.bat to create the Python environment.
  pause
  exit /b 1
)
set PY="%VENV%\Scripts\python.exe"
fc /b llm\requirements.txt "%VENV%\llm-installed.txt" >nul 2>&1
if errorlevel 1 (
  echo Installing the packages of llm\requirements.txt
  %PY% -m pip install -r llm\requirements.txt || goto fail
  copy /y llm\requirements.txt "%VENV%\llm-installed.txt" >nul
)
%PY% -m llm.chat %*
exit /b %errorlevel%

:fail
echo Installing the packages failed.
pause
exit /b 1
