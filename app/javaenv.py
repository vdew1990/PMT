"""Java for reading native MS Project (.mpp) files (MPXJ needs a Java runtime).

PMT looks for Java in this order: JAVA_HOME, java on the PATH, then a private copy in <PMT home>/jre. If there is none it
downloads Eclipse Temurin's runtime from Adoptium (a zip of about 45 MB, no installer and no administrator rights) into that
private folder, once. Nothing else on the PC is changed. Run as `python -m app.javaenv --ensure` (PMT.exe's run.bat does this
at start-up, so the first .mpp upload is instant); the first upload does it too if the start-up step was skipped or failed.
Set PMT_NO_JAVA_DOWNLOAD=1 to stop it downloading.
"""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

FEATURE = 17          # Temurin 17 (long-term support); MPXJ needs Java 11 or later
MIN_MB = 20           # anything smaller than this is not a runtime


class JavaUnavailable(Exception):
    pass


def pmt_home():
    if os.environ.get("PMT_HOME"):
        return Path(os.environ["PMT_HOME"])
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "PMT"
    return Path.home() / ".local" / "share" / "PMT"


def _exe(home):
    return Path(home) / "bin" / ("java.exe" if os.name == "nt" else "java")


def _works(exe):
    try:
        r = subprocess.run([str(exe), "-version"], capture_output=True, timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find():
    """JAVA_HOME of a Java that runs, or None."""
    jh = os.environ.get("JAVA_HOME")
    if jh and _exe(jh).exists() and _works(_exe(jh)):
        return Path(jh)
    onpath = shutil.which("java")
    if onpath and _works(onpath):
        return Path(onpath).resolve().parent.parent
    mine = pmt_home() / "jre"
    if _exe(mine).exists() and _works(_exe(mine)):
        return mine
    return None


def download_url():
    osname = {"nt": "windows", "posix": "mac" if sys.platform == "darwin" else "linux"}.get(os.name, "linux")
    arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    return f"https://api.adoptium.net/v3/binary/latest/{FEATURE}/ga/{osname}/{arch}/jre/hotspot/normal/eclipse"


def _fetch(url, dest, say):
    req = urllib.request.Request(url, headers={"User-Agent": "PMT"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, last = 0, -1
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total and say and got * 100 // total // 10 != last:
                last = got * 100 // total // 10
                say(f"Downloading Java ({got * 100 // total}%)...")


def _unpack(archive, target):
    """Unpack a Temurin zip or tar.gz so that target/bin/java exists (the archive has one top folder)."""
    tmp = Path(tempfile.mkdtemp(prefix="pmt-jre-", dir=str(target.parent)))
    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as z:
                z.extractall(tmp)
        else:
            import tarfile
            with tarfile.open(archive) as t:
                t.extractall(tmp)
        tops = [p for p in tmp.iterdir() if p.is_dir()]
        root = tops[0] if len(tops) == 1 else tmp
        if root.name.endswith(".app") or (root / "Contents" / "Home").exists():
            root = root / "Contents" / "Home"
        if not _exe(root).exists():
            raise JavaUnavailable("The download did not contain a Java runtime")
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(root), str(target))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ensure(say=None):
    """JAVA_HOME of a working Java, downloading a private runtime if there is none. Raises JavaUnavailable with a plain message."""
    found = find()
    if found:
        return found
    if os.environ.get("PMT_NO_JAVA_DOWNLOAD") == "1":
        raise JavaUnavailable("Java is not installed and downloading it is switched off")
    target = pmt_home() / "jre"
    target.parent.mkdir(parents=True, exist_ok=True)
    if say:
        say("Downloading Java (first time only, about 45 MB)...")
    fd, arc = tempfile.mkstemp(prefix="pmt-jre-", suffix=".bin", dir=str(target.parent))
    os.close(fd)
    try:
        _fetch(download_url(), arc, say)
        if Path(arc).stat().st_size < MIN_MB * 1024 * 1024:
            raise JavaUnavailable("The download was too small to be a Java runtime")
        if say:
            say("Setting up Java...")
        _unpack(arc, target)
    except JavaUnavailable:
        raise
    except Exception as e:   # no internet, a company firewall, a full disk
        raise JavaUnavailable(f"Java could not be downloaded ({str(e)[:100]}). A company network may block adoptium.net") from e
    finally:
        Path(arc).unlink(missing_ok=True)
    if not _works(_exe(target)):
        raise JavaUnavailable("The downloaded Java does not run on this PC")
    return target


def jvm_path(home):
    """The JVM library inside a Java home (what JPype starts)."""
    for rel in ("bin/server/jvm.dll", "lib/server/libjvm.so", "lib/server/libjvm.dylib", "bin/client/jvm.dll"):
        if (Path(home) / rel).exists():
            return str(Path(home) / rel)
    return None


if __name__ == "__main__":
    if "--ensure" in sys.argv:
        def say(m):
            print("##PMT step " + m, flush=True)
        try:
            h = ensure(say)
            print(f"Java is ready: {h}")
        except JavaUnavailable as e:
            print(f"Java was not set up: {e}. PMT still works; .mpp files will try again when you upload one.")
        sys.exit(0)
    print(find() or "Java not found")
