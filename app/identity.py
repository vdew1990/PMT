"""Who is using the app.

PMT runs on each user's own PC, so the user is the Windows account that started it. No IT set-up is needed: the
Microsoft 365 identity is read from the OneDrive for Business sign-in (the same account that syncs the SharePoint
folder), then from Windows itself. PMT_USER_UPN / PMT_USER_NAME override everything (tests, or a shared kiosk).

This is attribution among colleagues, not authentication: someone with access to the PC could change it. Verified
sign-in through Microsoft Entra (MSAL) needs an app registration from IT and is a later phase.
"""
import getpass
import os
import re
import socket
import subprocess
import sys
from contextvars import ContextVar

_cached = None
# EPEC's companies. OneDrive for Business reports the organisation (one of these) as its "DisplayName"; it is the
# person's entity, never their name.
ENTITIES = ["EPEC Projects Pty Ltd", "EPEC Group Pty Ltd", "EPEC Engineering Pty Ltd"]
_ORG = re.compile(r"\b(pty|ltd|limited|inc|llc|plc|group|corporation|company|holdings)\b|\bepec\b", re.I)


def looks_like_org(name):
    """True for a company name ("EPEC Group Pty Ltd"), which must not be shown as a person's name."""
    return bool(name and _ORG.search(name))
# per-request override, for a future hosted mode where the user comes from a sign-in header
request_user: ContextVar = ContextVar("pmt_request_user", default=None)


def _onedrive_business():
    """UPN and display name of the OneDrive for Business account(s) signed in on this PC."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\OneDrive\Accounts")
    except OSError:
        return None
    found = []
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        if not sub.lower().startswith("business"):
            continue
        try:
            k = winreg.OpenKey(root, sub)
            email = winreg.QueryValueEx(k, "UserEmail")[0]
            try:
                name = winreg.QueryValueEx(k, "DisplayName")[0]
            except OSError:
                name = None
            if email:
                found.append((sub, email, name))
        except OSError:
            continue
    if not found:
        return None
    found.sort()
    _, email, org = found[0]  # Business1 is the primary work account; its DisplayName is the organisation
    return dict(upn=email.lower(), name=None, org=org, source="OneDrive for Business")


def _office_name():
    """The user name Office shows on this PC (File > Account), usually the person's full name."""
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Office\Common\UserInfo")
        return winreg.QueryValueEx(k, "UserName")[0] or None
    except Exception:
        return None


def _windows_api():
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    def get(fmt):
        fn = ctypes.windll.secur32.GetUserNameExW
        fn.argtypes = [ctypes.c_int, wintypes.LPWSTR, ctypes.POINTER(wintypes.ULONG)]
        size = wintypes.ULONG(0)
        fn(fmt, None, ctypes.byref(size))
        if not size.value:
            return None
        buf = ctypes.create_unicode_buffer(size.value)
        return buf.value if fn(fmt, buf, ctypes.byref(size)) else None
    try:
        upn, name = get(8), get(3)  # NameUserPrincipal, NameDisplay
    except Exception:
        return None
    if not upn:
        try:
            out = subprocess.run(["whoami", "/upn"], capture_output=True, text=True, timeout=5, creationflags=0x08000000)
            upn = out.stdout.strip() if out.returncode == 0 and "@" in out.stdout else None
        except Exception:
            upn = None
    if not upn:
        return None
    return dict(upn=upn.lower(), name=name, source="Windows sign-in")


def _fallback():
    user = os.environ.get("USERNAME") or getpass.getuser() or "user"
    dom = os.environ.get("USERDOMAIN") or socket.gethostname()
    return dict(upn=f"{user}@{dom}".lower(), name=None, source="Local account")


def _pretty(upn):
    """jane.citizen@epec.com.au -> Jane Citizen"""
    local = upn.split("@")[0]
    return " ".join(w.capitalize() for w in re.split(r"[._\-]+", local) if w) or upn


def current():
    """The person using this copy of PMT: {upn, name, source}."""
    ru = request_user.get()
    if ru:
        return ru
    global _cached
    if _cached:
        return _cached
    if os.environ.get("PMT_USER_UPN"):
        u = dict(upn=os.environ["PMT_USER_UPN"].lower(), name=os.environ.get("PMT_USER_NAME"), source="Configured")
    else:
        u = None
        for f in (_onedrive_business, _windows_api):
            try:
                u = f()
            except Exception:
                u = None
            if u:
                break
        u = u or _fallback()
    # the person's name: Office's user name, then Windows' display name, then the email address; never a company name
    names = [u.get("name")]
    if u.get("source") != "Configured":
        names.append(_safe(_office_name))
        names.append(_safe(lambda: (_windows_api() or {}).get("name")))
    u["name"] = next((n for n in names if n and not looks_like_org(n) and "@" not in n), None) or _pretty(u["upn"])
    u["org"] = u.get("org") if looks_like_org(u.get("org")) else None
    _cached = u
    return u


def _safe(f):
    try:
        return f()
    except Exception:
        return None


def apply_profile(name=None, entity=None):
    """The name and entity the person set in their profile (shared through sync_state) win over what was detected."""
    u = current()
    if name and name.strip():
        u["name"] = name.strip()
    if entity:
        u["org"] = entity
    return u


def device():
    return re.sub(r"[^A-Za-z0-9\-]", "", socket.gethostname())[:40] or "pc"


def slug(upn):
    return re.sub(r"[^a-z0-9.\-]", "_", upn.lower())


def reset():
    """Forget the cached identity (tests)."""
    global _cached
    _cached = None
# EPEC's companies. OneDrive for Business reports the organisation (one of these) as its "DisplayName"; it is the
# person's entity, never their name.
ENTITIES = ["EPEC Projects Pty Ltd", "EPEC Group Pty Ltd", "EPEC Engineering Pty Ltd"]
_ORG = re.compile(r"\b(pty|ltd|limited|inc|llc|plc|group|corporation|company|holdings)\b|\bepec\b", re.I)


def looks_like_org(name):
    """True for a company name ("EPEC Group Pty Ltd"), which must not be shown as a person's name."""
    return bool(name and _ORG.search(name))
