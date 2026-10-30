PMT.exe is the launcher. It shows a small window with the PMT tile, a progress bar and the current step
("Installing packages...", "Starting PMT..."), and runs run.bat from the folder it sits in, hidden.
"More info" shows run.bat's output live; "Copy details" copies it to send on when something fails.
When the app answers it opens your browser. Keep the window open (minimised is fine): closing it, or
"Stop PMT", stops PMT. Everything run.bat started is stopped with it (Windows job object).
If Python is missing it asks in its own window before downloading it (run.bat does the work).
It makes no network connections itself and changes nothing on the PC; run.bat does the installing.
Java (only needed to read MS Project .mpp files) is checked at every start: if the PC has none, run.bat has PMT fetch a
private copy once (about 45 MB from adoptium.net, no installer, no administrator rights, kept in %LOCALAPPDATA%\PMT\jre).
If that fails the app still starts and the first .mpp upload tries again.
Double-clicking run.bat instead still works, in a console window, as before.

Clicked in SharePoint in the browser
  The browser only downloads PMT.exe (a browser never runs a program from SharePoint). A copy with no run.bat next
  to it looks for the PMT folder synced to this PC and starts that PMT.exe, then closes. It looks, in order:
    1. where PMT last ran from (every normal run writes its folder to %LOCALAPPDATA%\PMT\home.txt);
    2. the libraries OneDrive syncs (HKCU\Software\Microsoft\OneDrive\Accounts\*\Tenants, and each account's folder);
    3. %OneDriveCommercial%, %OneDrive% and the user's profile (where synced libraries sit, under the organisation).
  It searches up to five folders deep for a folder with PMT.exe, run.bat and app\launch.py, skipping AppData,
  Downloads and folder links. If none is found it explains how to sync the library and run PMT from File Explorer once.

Files
  launcher.c     the complete source
  pmt.rc         the icon, version details and manifest compiled into the program
  pmt.manifest   modern Windows controls (moving progress bar) and sharp text on high-DPI screens
  PMT_icon.ico   the icon: the PMT logo on a white rounded tile, 16 to 256 px; also usable for a shortcut

To rebuild (any machine with Zig; `pip install ziglang` gives one):
  zig cc -target x86_64-windows-gnu -O2 -s -Wl,--subsystem,windows launcher.c pmt.rc -o ../PMT.exe -luser32 -lgdi32 -lcomctl32 -lshell32 -ladvapi32

The program is not code-signed, so Windows SmartScreen may show "Unknown publisher" the first time.
Choose "More info", then "Run anyway", or ask IT to allow it or sign it.
Windows caches icons: if the old icon still shows after an update, it refreshes after a sign-out or restart.
