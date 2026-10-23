@echo off
rem Publishes the program folder to GitHub: commits all changes (the files listed by git status, without the
rem files of .gitignore) with a description, then pull --rebase and push to the repository of the folder
rem (git remote "origin": https://github.com/lukerickert/Shiny_CAD).
rem   publish.bat           asks for the description
rem   publish.bat "text"    description given
setlocal
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 goto nogit
if not exist ".git" goto norepo
git config user.email >nul 2>nul
if errorlevel 1 call :identity
for /f "delims=" %%r in ('git remote get-url origin') do echo Repository: %%r
git add -A
if errorlevel 1 goto fail
git diff --cached --quiet
if not errorlevel 1 (
  echo No changes to commit.
  goto push
)
echo Changes:
git status --short
set "MSG=%~1"
if not "%MSG%"=="" goto commit
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
set /p "MSG=Description of the changes (Enter: Update %TODAY%): "
if "%MSG%"=="" set "MSG=Update %TODAY%"
:commit
git commit -q -m "%MSG%"
if errorlevel 1 goto fail
:push
git pull --rebase -q
if errorlevel 1 goto fail
git push -q
if errorlevel 1 goto fail
echo.
echo Published to GitHub:
git log -1 --format="%%h %%s (%%ad)" --date=format:"%%Y-%%m-%%d %%H:%%M"
pause
exit /b 0

:identity
echo Git needs a name and an e-mail address for the commits (stored for this folder only).
set /p "GNAME=Name: "
set /p "GEMAIL=E-mail (for example the GitHub noreply address): "
git config user.name "%GNAME%"
git config user.email "%GEMAIL%"
exit /b 0

:nogit
echo Git for Windows was not found. Install it from https://git-scm.com/download/win
echo (default options; Git Credential Manager signs in to GitHub in the browser at the first push).
pause
exit /b 1

:norepo
echo This folder is not a git repository (.git is missing).
pause
exit /b 1

:fail
echo.
echo Publishing stopped: see the messages above.
pause
exit /b 1
