"""Start PMT on this PC and open it in the browser. run.bat / PMT.exe call `python -m app.launch`.

* If the program folder holds a `shared` folder (the SharePoint copy), the app runs in shared mode: the database
  is a private replica under %LOCALAPPDATA%\\PMT and changes travel through `shared/journal` (see sync.py).
* If PMT is already running for this user, the browser is simply pointed at it again.
* Otherwise the first free port from 8000 up is used.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _me_at(port):
    """What a PMT server on this port says about itself (user, build), or None."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/me", timeout=1.5) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _pid_on_port(port):
    """Windows: the process listening on 127.0.0.1:port (from netstat), or None."""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1] in (f"127.0.0.1:{port}", f"0.0.0.0:{port}") and parts[3].upper() == "LISTENING":
            return int(parts[4]) if parts[4].isdigit() else None
    return None


def _stop_old(port):
    """Stop an older PMT server on this port; True once it no longer answers. First ask it (/api/shutdown); a server
    from before that existed is ended through Windows (it answered as PMT for this same user, so it is ours)."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json", "X-PMT": "1"})
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        pid = _pid_on_port(port) if os.name == "nt" else None
        if not pid or pid == os.getpid():
            return False
        print(f"The older PMT does not know how to stop itself; ending process {pid}.", flush=True)
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=15)
    for _ in range(60):
        time.sleep(0.25)
        if _me_at(port) is None:
            return True
    return False


def _answers(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/me", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def _grab(port):
    """Bind the port now and keep it, so two copies starting together cannot pick the same one."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return s
    except OSError:
        s.close()
        return None


def main():
    if not os.environ.get("PMT_SHARED") and (ROOT / "shared").is_dir():
        os.environ["PMT_SHARED"] = str(ROOT / "shared")
    from app import build, identity  # after PMT_SHARED is set: db reads it on import
    me = identity.current()["upn"]
    here = build.on_disk()
    port = int(os.environ.get("PORT") or 8000)
    sock = None
    for p in range(port, port + 20):
        info = _me_at(p) or {}
        if info.get("upn") == me and info.get("build") != here:
            # started before the program files were updated: its pages would be new and its server old ("Not Found")
            print(f"An older PMT (started before the files were updated) is running on port {p}. Stopping it...", flush=True)
            if not _stop_old(p):
                print("It could not be stopped automatically. Close the old PMT window (or end Python in Task Manager), then open PMT again.")
                print("##PMT fail An older PMT is still running. Close its window (or end Python in Task Manager), then open PMT again.", flush=True)
                sys.exit(3)
            print("Stopped. Starting the updated PMT.", flush=True)
            for _ in range(12):  # the port can take a moment to come free; otherwise the next one is used
                sock = _grab(p)
                if sock:
                    break
                time.sleep(0.25)
            if sock:
                port = p
                break
            continue
        if info.get("upn") == me:
            print(f"PMT is already running on http://127.0.0.1:{p}. Opening it.")
            print(f"##PMT already http://127.0.0.1:{p}", flush=True)  # PMT.exe opens the browser and closes its window
            if os.environ.get("PMT_NO_BROWSER") != "1":
                webbrowser.open(f"http://127.0.0.1:{p}")
            return
        sock = _grab(p)
        if sock:
            port = p
            break
    else:
        print("No free port between", port, "and", port + 19)
        sys.exit(1)
    mode = f"shared through {os.environ['PMT_SHARED']}" if os.environ.get("PMT_SHARED") else "on this PC only"
    print(f"Project Management Tool for {identity.current()['name']} <{me}>, {mode}")
    print(f"Open http://127.0.0.1:{port}" + ("" if os.environ.get("PMT_GUI") else "  (keep this window open while you work; Ctrl+C stops it)"))

    def _open():
        # wait until the app answers, then tell PMT.exe ("##PMT ready") and open the browser
        for _ in range(240):
            if _answers(port):
                break
            time.sleep(0.25)
        print(f"##PMT ready http://127.0.0.1:{port}", flush=True)
        if os.environ.get("PMT_NO_BROWSER") != "1":
            webbrowser.open(f"http://127.0.0.1:{port}")
    threading.Thread(target=_open, daemon=True).start()
    import uvicorn
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    build.SERVER = server
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
