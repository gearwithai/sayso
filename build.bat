@echo off
REM Builds dist\Sayso\Sayso.exe and, if Inno Setup is installed, the SaysoSetup installer in dist
setlocal
cd /d "%~dp0"

if not exist .venv (
  py -3.11 -m venv .venv || python -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat || goto :fail
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller pytest || goto :fail

python -m pytest -q || goto :fail
python -m sayso.icons sayso\sayso.ico || goto :fail
pyinstaller --noconfirm --clean sayso.spec || goto :fail

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% installer\sayso.iss || goto :fail
  echo.
  echo Installer ready in the dist folder: SaysoSetup-x.y.z.exe
) else (
  echo.
  echo App built: dist\Sayso\Sayso.exe
  echo For the installer, get Inno Setup 6 from https://jrsoftware.org/isdl.php and run this again.
)
exit /b 0

:fail
echo.
echo BUILD FAILED - scroll up for the error.
exit /b 1
