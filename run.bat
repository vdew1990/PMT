@echo off
rem Project Management Tool: double-click to install (first run only) and start.
rem If no suitable Python is found it offers to download one from python.org (current user only, no admin rights).
setlocal
cd /d "%~dp0"
title Project Management Tool
rem PMT.exe runs this file hidden and shows its own window: it sets PMT_GUI=1 and reads the "##PMT ..." lines
rem (step / ask-python / ready / already). Without PMT_GUI (double-clicking run.bat) it works in this console as before.
set "PAUSE=pause"
set "STEP=rem"
if defined PMT_GUI (
  set "PAUSE=rem"
  set "STEP=echo ##PMT step"
  chcp 65001 >nul
)
if "%PORT%"=="" set "PORT=8000"
rem Version offered when Python is missing. Change this one line to offer a newer release.
set "PYVER=3.13.3"
set "TRIED_INSTALL="
rem The Python environment and compiled files stay on this PC, never in the (possibly SharePoint-synced) program folder.
set "PMT_HOME=%LOCALAPPDATA%\PMT"
set "VENV=%PMT_HOME%\venv"
set "PYTHONPYCACHEPREFIX=%PMT_HOME%\pycache"
if not exist "%PMT_HOME%" mkdir "%PMT_HOME%"

:findpython
%STEP% Checking for Python...
set "PY=py -3"
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto pythonok
set "PY=python"
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto pythonok
set PY="%LOCALAPPDATA%\Programs\PMT-Python\python.exe"
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto pythonok
set "PY="
goto offerinstall

:pythonok
if not exist "%VENV%\Scripts\python.exe" goto makeenv
"%VENV%\Scripts\python.exe" -c "import sys" >nul 2>&1
if not errorlevel 1 goto haveenv
echo The Python environment in %VENV% is broken. Rebuilding it...
rmdir /s /q "%VENV%"
if exist "%VENV%" goto lockedenv

:makeenv
%STEP% Preparing Python for PMT (first run only, about a minute)...
echo Creating the private Python environment in %VENV%, first run only...
%PY% -m venv "%VENV%"
if errorlevel 1 goto fail

:haveenv
fc /b requirements.txt "%VENV%\requirements.installed.txt" >nul 2>&1
if not errorlevel 1 goto launch
%STEP% Installing packages (first run or after an update, a minute or two)...
echo Installing the required packages. This needs internet and takes a minute or two...
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
copy /y requirements.txt "%VENV%\requirements.installed.txt" >nul

:launch
rem Java is needed only to read native MS Project (.mpp) files. If this PC has none, a private copy is fetched once from
rem adoptium.net (no installer, no administrator rights, current user only). A failure here never stops PMT starting.
%STEP% Checking Java for MS Project files...
"%VENV%\Scripts\python.exe" -m app.javaenv --ensure

%STEP% Starting PMT...
echo.
if not defined PMT_GUI echo Starting the Project Management Tool. Keep this window open while you work. Press Ctrl+C to stop.
echo.
"%VENV%\Scripts\python.exe" -m app.launch
set "RC=%errorlevel%"
echo.
echo The app has stopped. If an error appeared above, copy the red text and send it on.
%PAUSE%
exit /b %RC%

:offerinstall
if defined TRIED_INSTALL goto installfailed
rem PMT.exe asks in its own window and runs this file again with PMT_INSTALL_PYTHON=1 when the user says yes
if defined PMT_INSTALL_PYTHON goto doinstall
if defined PMT_GUI (
  echo Python 3.10 or later was not found on this PC.
  echo ##PMT ask-python
  exit /b 10
)
echo.
echo Python 3.10 or later was not found on this PC.
echo (Windows has a Microsoft Store shortcut called python, but it is not Python.)
echo.
echo This program can download Python %PYVER% from python.org and install it for your user only.
echo No administrator rights are needed. The download is about 28 MB and needs internet.
echo The installer's digital signature is checked before it is run.
echo Some companies do not allow installing software. If you are unsure, answer N and ask IT.
echo.
choice /c YN /n /m "Download and install Python now? [Y/N] "
if errorlevel 2 goto manual
:doinstall
set "TRIED_INSTALL=1"
set "ARCH=amd64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=arm64"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "ARCH=arm64"
set "PMT_PY_URL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-%ARCH%.exe"
set "PMT_PY_FILE=%TEMP%\pmt-python-%PYVER%-%ARCH%.exe"
echo.
%STEP% Downloading Python (about 28 MB)...
echo Downloading %PMT_PY_URL%
if exist "%PMT_PY_FILE%" del /q "%PMT_PY_FILE%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri $env:PMT_PY_URL -OutFile $env:PMT_PY_FILE"
if errorlevel 1 goto dlfail
if not exist "%PMT_PY_FILE%" goto dlfail
echo Checking the installer's digital signature...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = Get-AuthenticodeSignature -LiteralPath $env:PMT_PY_FILE; if ($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -like '*Python Software Foundation*') { exit 0 } else { exit 1 }"
if errorlevel 1 goto sigfail
%STEP% Installing Python for your user (a minute or two)...
echo Installing Python for your user. This takes a minute or two...
start /wait "" "%PMT_PY_FILE%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0 Include_doc=0 Include_tcltk=0 Shortcuts=0 AssociateFiles=0 "TargetDir=%LOCALAPPDATA%\Programs\PMT-Python"
del /q "%PMT_PY_FILE%" >nul 2>&1
if not exist "%LOCALAPPDATA%\Programs\PMT-Python\python.exe" goto installfailed
echo Python installed.
goto findpython

:manual
echo.
echo Install Python 3.10 or later yourself from https://www.python.org/downloads/windows/
echo and tick "Add python.exe to PATH" on the first installer screen. Then run this file again.
echo If installs are blocked on your PC, ask IT.
%PAUSE%
exit /b 1

:dlfail
echo.
echo The download failed. Check your internet connection. A company network may block python.org.
echo Install Python yourself from https://www.python.org/downloads/windows/ or ask IT, then run this file again.
if exist "%PMT_PY_FILE%" del /q "%PMT_PY_FILE%" >nul 2>&1
%PAUSE%
exit /b 1

:sigfail
echo.
echo The downloaded file did not have a valid Python Software Foundation signature, so it was not run and was deleted.
del /q "%PMT_PY_FILE%" >nul 2>&1
echo Install Python yourself from https://www.python.org/downloads/windows/ or ask IT.
%PAUSE%
exit /b 1

:installfailed
echo.
echo Python could not be installed automatically. Company policy may block it.
echo Install Python 3.10 or later from https://www.python.org/downloads/windows/ or ask IT, then run this file again.
%PAUSE%
exit /b 1

:lockedenv
echo The folder %VENV% could not be deleted. Close anything using it, delete it by hand,
echo then run this file again.
%PAUSE%
exit /b 1

:fail
echo.
echo Setup failed. Copy the error text above and send it on.
echo If pip could not download packages, your network may block pypi.org. Ask IT.
%PAUSE%
exit /b 1
