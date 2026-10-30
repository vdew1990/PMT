/* Project Management Tool launcher (PMT.exe).
 *
 * Shows a small window with the PMT tile, a progress bar and what is happening ("Installing packages..."), and runs
 * run.bat from the folder this program sits in, hidden. "More info" shows run.bat's output live, as the old console
 * window did. The window stays while PMT runs: closing it (or "Stop PMT") stops PMT. Everything run.bat starts sits in
 * a Windows job object, so nothing is left running after the window closes.
 *
 * run.bat talks to this window with lines that start "##PMT " (set PMT_GUI=1 to get them):
 *   ##PMT step <text>    what is happening now
 *   ##PMT ask-python     Python is missing: run.bat exits with code 10 and this window asks before installing it
 *   ##PMT ready <url>    the app answers at <url>: open the browser
 *   ##PMT already <url>  PMT was already running for this user: open the browser and close this window
 *   ##PMT fail <text>    why it could not start, shown as the status when run.bat ends
 * Keep PMT.exe next to run.bat, app and static. A copy on its own (downloaded by clicking it in SharePoint in the browser)
 * finds the PMT folder synced by OneDrive and starts that one (see find_synced). Source is included (README.txt). */
#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <shellapi.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define WM_APP_LINE (WM_APP + 1) /* lParam: heap wchar_t* line, freed by the window */
#define WM_APP_EXIT (WM_APP + 2) /* wParam: run.bat exit code */
#define ID_MORE 101
#define ID_OPEN 102
#define ID_STOP 103
#define ID_COPY 104
#define TIMER_TICK 1
#define TIMER_CLOSE 2

#define NAVY RGB(0x10, 0x23, 0x61)
#define ORANGE RGB(0xe5, 0x62, 0x10)
#define GREEN RGB(0x2e, 0x7d, 0x32)
#define RED RGB(0xc6, 0x28, 0x28)
#define GREY RGB(0x5f, 0x6b, 0x73)

enum { WORKING, READY, FAILED, STOPPED };

static HINSTANCE g_inst;
static HWND g_wnd, g_title, g_status, g_bar, g_hint, g_more, g_copy, g_open, g_stop, g_log;
static HANDLE g_job;
static HICON g_tile;
static HFONT g_font, g_bold, g_mono;
static HBRUSH g_bg;
static int g_dpi = 96, g_expanded = 0, g_state = WORKING, g_install_python = 0, g_asked = 0, g_already = 0;
static wchar_t g_dir[MAX_PATH], g_url[512] = L"", g_step[512] = L"Starting...", g_fail[512] = L"";
static DWORD g_t0;

static int S(int x) { return MulDiv(x, g_dpi, 96); }

/* ---- a copy downloaded from SharePoint: find the synced PMT folder and run that one ---------------------------
 * Clicking PMT.exe in SharePoint in the browser only downloads the program, without the app it runs. Every normal
 * run records its folder in %LOCALAPPDATA%\PMT\home.txt; a copy with no run.bat next to it looks there first, then in
 * the folders OneDrive syncs (the libraries listed under HKCU\Software\Microsoft\OneDrive\Accounts\*\Tenants, the
 * OneDrive folders, and the organisation folders under the user's profile), and starts the PMT.exe it finds. */
static int exists(const wchar_t *dir, const wchar_t *name) {
    wchar_t p[MAX_PATH * 2];
    _snwprintf(p, MAX_PATH * 2 - 1, L"%s\\%s", dir, name);
    p[MAX_PATH * 2 - 1] = 0;
    return GetFileAttributesW(p) != INVALID_FILE_ATTRIBUTES;
}

static int is_pmt_dir(const wchar_t *d) {
    return exists(d, L"PMT.exe") && exists(d, L"run.bat") && exists(d, L"app\\launch.py");
}

static int home_file(wchar_t *out, int mkdir) {
    wchar_t la[MAX_PATH];
    DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", la, MAX_PATH);
    if (!n || n >= MAX_PATH) return 0;
    _snwprintf(out, MAX_PATH - 1, L"%s\\PMT", la);
    out[MAX_PATH - 1] = 0;
    if (mkdir) CreateDirectoryW(out, NULL);
    wcsncat(out, L"\\home.txt", MAX_PATH - wcslen(out) - 1);
    return 1;
}

static void remember_home(void) {
    wchar_t f[MAX_PATH];
    if (!home_file(f, 1)) return;
    HANDLE h = CreateFileW(f, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    DWORD w;
    WriteFile(h, g_dir, (DWORD)(wcslen(g_dir) * sizeof(wchar_t)), &w, NULL);
    CloseHandle(h);
}

static int read_home(wchar_t *out) {
    wchar_t f[MAX_PATH];
    if (!home_file(f, 0)) return 0;
    HANDLE h = CreateFileW(f, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;
    DWORD r = 0;
    BOOL ok = ReadFile(h, out, (MAX_PATH - 1) * sizeof(wchar_t), &r, NULL);
    CloseHandle(h);
    if (!ok) return 0;
    out[r / sizeof(wchar_t)] = 0;
    return is_pmt_dir(out);
}

static int skip_dir(const wchar_t *n) {
    static const wchar_t *skip[] = {L"AppData", L"node_modules", L"__pycache__", L".venv", L"venv", L"site-packages", L"Windows",
                                    L"Program Files", L"Program Files (x86)", L"$Recycle.Bin", L"Downloads", NULL};
    if (n[0] == L'.') return 1;
    for (int i = 0; skip[i]; i++)
        if (!_wcsicmp(n, skip[i])) return 1;
    return 0;
}

/* depth-first, up to five levels: a synced library is <Organisation>\<Site - Library>\<folders...>\PMT */
static int search(const wchar_t *root, int depth, wchar_t *out) {
    if (is_pmt_dir(root)) {
        wcsncpy(out, root, MAX_PATH - 1);
        out[MAX_PATH - 1] = 0;
        return 1;
    }
    if (depth <= 0) return 0;
    wchar_t pat[MAX_PATH * 2];
    _snwprintf(pat, MAX_PATH * 2 - 1, L"%s\\*", root);
    pat[MAX_PATH * 2 - 1] = 0;
    WIN32_FIND_DATAW fd;
    HANDLE f = FindFirstFileExW(pat, FindExInfoBasic, &fd, FindExSearchLimitToDirectories, NULL, 0);
    if (f == INVALID_HANDLE_VALUE) return 0;
    int found = 0;
    do {
        if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || skip_dir(fd.cFileName)) continue;
        if ((fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) &&
            (fd.dwReserved0 == IO_REPARSE_TAG_MOUNT_POINT || fd.dwReserved0 == IO_REPARSE_TAG_SYMLINK))
            continue; /* junctions and links (loops); OneDrive's own cloud folders are reparse points too and are searched */
        wchar_t sub[MAX_PATH];
        if (_snwprintf(sub, MAX_PATH - 1, L"%s\\%s", root, fd.cFileName) < 0) continue;
        sub[MAX_PATH - 1] = 0;
        if (search(sub, depth - 1, out)) { found = 1; break; }
    } while (FindNextFileW(f, &fd));
    FindClose(f);
    return found;
}

/* the folders OneDrive syncs for this user, from OneDrive's own settings */
static int search_onedrive_settings(wchar_t *out) {
    HKEY acc;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\Microsoft\\OneDrive\\Accounts", 0, KEY_READ, &acc) != ERROR_SUCCESS) return 0;
    int found = 0;
    wchar_t name[256];
    for (DWORD i = 0; !found; i++) {
        DWORD nl = 256;
        if (RegEnumKeyExW(acc, i, name, &nl, NULL, NULL, NULL, NULL) != ERROR_SUCCESS) break;
        wchar_t tk[400];
        _snwprintf(tk, 399, L"%s\\Tenants", name);
        tk[399] = 0;
        HKEY tenants;
        if (RegOpenKeyExW(acc, tk, 0, KEY_READ, &tenants) == ERROR_SUCCESS) {
            wchar_t tn[256];
            for (DWORD j = 0; !found; j++) {
                DWORD tl = 256;
                if (RegEnumKeyExW(tenants, j, tn, &tl, NULL, NULL, NULL, NULL) != ERROR_SUCCESS) break;
                HKEY t;
                if (RegOpenKeyExW(tenants, tn, 0, KEY_READ, &t) != ERROR_SUCCESS) continue;
                wchar_t path[MAX_PATH];
                for (DWORD k = 0; !found; k++) {
                    DWORD pl = MAX_PATH;
                    if (RegEnumValueW(t, k, path, &pl, NULL, NULL, NULL, NULL) != ERROR_SUCCESS) break;
                    if (path[0] && GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES) found = search(path, 5, out);
                }
                RegCloseKey(t);
            }
            RegCloseKey(tenants);
        }
        HKEY a;
        if (!found && RegOpenKeyExW(acc, name, 0, KEY_READ, &a) == ERROR_SUCCESS) {
            wchar_t uf[MAX_PATH];
            DWORD ul = sizeof uf, type = 0;
            if (RegQueryValueExW(a, L"UserFolder", NULL, &type, (LPBYTE)uf, &ul) == ERROR_SUCCESS && type == REG_SZ) {
                uf[MAX_PATH - 1] = 0;
                found = search(uf, 5, out);
            }
            RegCloseKey(a);
        }
    }
    RegCloseKey(acc);
    return found;
}

static int find_synced(wchar_t *out) {
    if (read_home(out)) return 1;
    if (search_onedrive_settings(out)) return 1;
    static const wchar_t *vars[] = {L"OneDriveCommercial", L"OneDrive", L"USERPROFILE", NULL};
    for (int i = 0; vars[i]; i++) {
        wchar_t root[MAX_PATH];
        DWORD n = GetEnvironmentVariableW(vars[i], root, MAX_PATH);
        if (n && n < MAX_PATH && search(root, 5, out)) return 1;
    }
    return 0;
}

/* ---- output of run.bat ------------------------------------------------------------------------------------- */
static void post_line(const char *s, int n) {
    /* run.bat switches the console to UTF-8 and Python writes UTF-8; anything else is read in the OEM code page */
    UINT cp = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s, n, NULL, 0) ? CP_UTF8 : CP_OEMCP;
    int w = MultiByteToWideChar(cp, 0, s, n, NULL, 0);
    wchar_t *line = (wchar_t *)malloc((size_t)(w + 1) * sizeof(wchar_t));
    if (!line) return;
    MultiByteToWideChar(cp, 0, s, n, line, w);
    line[w] = 0;
    if (!PostMessageW(g_wnd, WM_APP_LINE, 0, (LPARAM)line)) free(line);
}

static DWORD WINAPI reader(LPVOID p) {
    HANDLE rd = (HANDLE)p;
    static char buf[8192];
    char line[4096];
    int len = 0;
    DWORD got;
    while (ReadFile(rd, buf, sizeof buf, &got, NULL) && got) {
        for (DWORD i = 0; i < got; i++) {
            char c = buf[i];
            if (c == '\n' || len == (int)sizeof line - 1) {
                if (len && line[len - 1] == '\r') len--;
                post_line(line, len);
                len = 0;
                if (c == '\n') continue;
            }
            line[len++] = c;
        }
    }
    if (len) post_line(line, len);
    CloseHandle(rd);
    return 0;
}

static DWORD WINAPI waiter(LPVOID p) {
    HANDLE proc = (HANDLE)p;
    DWORD code = 1;
    WaitForSingleObject(proc, INFINITE);
    GetExitCodeProcess(proc, &code);
    CloseHandle(proc);
    PostMessageW(g_wnd, WM_APP_EXIT, code, 0);
    return 0;
}

static BOOL start_run(void) {
    SECURITY_ATTRIBUTES sa = {sizeof sa, NULL, TRUE};
    HANDLE rd, wr;
    if (!CreatePipe(&rd, &wr, &sa, 0)) return FALSE;
    SetHandleInformation(rd, HANDLE_FLAG_INHERIT, 0);
    HANDLE nul = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, NULL);
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = nul;
    si.hStdOutput = wr;
    si.hStdError = wr;
    ZeroMemory(&pi, sizeof pi);
    wchar_t cmd[2 * MAX_PATH + 64];
    _snwprintf(cmd, 2 * MAX_PATH + 63, L"cmd.exe /d /c \"\"%s\\run.bat\"\"", g_dir);
    cmd[2 * MAX_PATH + 63] = 0;
    SetEnvironmentVariableW(L"PMT_GUI", L"1");
    SetEnvironmentVariableW(L"PMT_NO_BROWSER", L"1"); /* this window opens the browser, outside the job */
    SetEnvironmentVariableW(L"PYTHONUNBUFFERED", L"1");
    SetEnvironmentVariableW(L"PYTHONIOENCODING", L"utf-8");
    SetEnvironmentVariableW(L"PMT_INSTALL_PYTHON", g_install_python ? L"1" : NULL);
    BOOL ok = CreateProcessW(NULL, cmd, NULL, NULL, TRUE, CREATE_NO_WINDOW | CREATE_SUSPENDED, NULL, g_dir, &si, &pi);
    CloseHandle(wr);
    if (nul != INVALID_HANDLE_VALUE) CloseHandle(nul);
    if (!ok) {
        CloseHandle(rd);
        return FALSE;
    }
    AssignProcessToJobObject(g_job, pi.hProcess);
    ResumeThread(pi.hThread);
    CloseHandle(pi.hThread);
    CloseHandle(CreateThread(NULL, 0, reader, rd, 0, NULL));
    CloseHandle(CreateThread(NULL, 0, waiter, pi.hProcess, 0, NULL));
    return TRUE;
}

/* ---- window ------------------------------------------------------------------------------------------------ */
static void log_append(const wchar_t *s) {
    int n = GetWindowTextLengthW(g_log);
    if (n > 600000) { /* keep the newest output */
        SendMessageW(g_log, EM_SETSEL, 0, 200000);
        SendMessageW(g_log, EM_REPLACESEL, FALSE, (LPARAM)L"");
        n = GetWindowTextLengthW(g_log);
    }
    SendMessageW(g_log, EM_SETSEL, n, n);
    SendMessageW(g_log, EM_REPLACESEL, FALSE, (LPARAM)s);
    SendMessageW(g_log, EM_REPLACESEL, FALSE, (LPARAM)L"\r\n");
}

static void show_status(void) {
    wchar_t s[640];
    if (g_state == WORKING) {
        DWORD t = (GetTickCount() - g_t0) / 1000;
        _snwprintf(s, 639, L"%s   (%lu:%02lu)", g_step, (unsigned long)(t / 60), (unsigned long)(t % 60));
        s[639] = 0;
        SetWindowTextW(g_status, s);
    } else {
        SetWindowTextW(g_status, g_step);
    }
    InvalidateRect(g_status, NULL, TRUE);
}

static void set_state(int st, const wchar_t *title, const wchar_t *step, const wchar_t *hint) {
    g_state = st;
    if (title) SetWindowTextW(g_title, title);
    if (step) lstrcpynW(g_step, step, 512);
    if (hint) SetWindowTextW(g_hint, hint);
    if (st != WORKING) {
        SendMessageW(g_bar, PBM_SETMARQUEE, FALSE, 0);
        LONG_PTR style = GetWindowLongPtrW(g_bar, GWL_STYLE);
        SetWindowLongPtrW(g_bar, GWL_STYLE, style & ~PBS_MARQUEE);
        SendMessageW(g_bar, PBM_SETRANGE32, 0, 100);
        SendMessageW(g_bar, PBM_SETPOS, 100, 0);
        SendMessageW(g_bar, PBM_SETSTATE, st == FAILED ? PBST_ERROR : (st == STOPPED ? PBST_PAUSED : PBST_NORMAL), 0);
    }
    EnableWindow(g_open, st == READY);
    SetWindowTextW(g_stop, (st == READY || st == WORKING) ? L"Stop PMT" : L"Close");
    show_status();
    InvalidateRect(g_title, NULL, TRUE);
    InvalidateRect(g_hint, NULL, TRUE);
    POINT pt;
    GetCursorPos(&pt);
    SetCursorPos(pt.x, pt.y); /* refresh the pointer (hourglass while working) */
}

static void layout(void) {
    RECT rc;
    GetClientRect(g_wnd, &rc);
    int w = rc.right, x0 = S(100);
    MoveWindow(g_title, x0, S(16), w - x0 - S(16), S(26), TRUE);
    MoveWindow(g_status, x0, S(46), w - x0 - S(16), S(20), TRUE);
    MoveWindow(g_bar, x0, S(70), w - x0 - S(16), S(16), TRUE);
    MoveWindow(g_hint, x0, S(92), w - x0 - S(16), S(36), TRUE);
    int by = S(136), bh = S(28);
    MoveWindow(g_more, S(16), by, S(110), bh, TRUE);
    MoveWindow(g_copy, S(132), by, S(110), bh, TRUE);
    MoveWindow(g_stop, w - S(16) - S(100), by, S(100), bh, TRUE);
    MoveWindow(g_open, w - S(16) - S(100) - S(8) - S(130), by, S(130), bh, TRUE);
    MoveWindow(g_log, S(16), S(176), w - S(32), rc.bottom - S(176) - S(16), TRUE);
}

static void set_expanded(int on) {
    g_expanded = on;
    RECT r = {0, 0, S(600), on ? S(520) : S(178)};
    AdjustWindowRectEx(&r, (DWORD)GetWindowLongPtrW(g_wnd, GWL_STYLE), FALSE, 0);
    RECT cur;
    GetWindowRect(g_wnd, &cur);
    SetWindowPos(g_wnd, NULL, cur.left, cur.top, r.right - r.left, r.bottom - r.top, SWP_NOZORDER);
    ShowWindow(g_log, on ? SW_SHOW : SW_HIDE);
    ShowWindow(g_copy, on ? SW_SHOW : SW_HIDE);
    SetWindowTextW(g_more, on ? L"Less info \x25B4" : L"More info \x25BE");
    layout();
    if (on) SendMessageW(g_log, EM_SCROLLCARET, 0, 0);
}

static void copy_log(void) {
    int n = GetWindowTextLengthW(g_log);
    HGLOBAL mem = GlobalAlloc(GMEM_MOVEABLE, (size_t)(n + 1) * sizeof(wchar_t));
    if (!mem) return;
    GetWindowTextW(g_log, (wchar_t *)GlobalLock(mem), n + 1);
    GlobalUnlock(mem);
    if (OpenClipboard(g_wnd)) {
        EmptyClipboard();
        if (!SetClipboardData(CF_UNICODETEXT, mem)) GlobalFree(mem);
        CloseClipboard();
    } else {
        GlobalFree(mem);
    }
}

static void open_browser(void) {
    if (g_url[0]) ShellExecuteW(g_wnd, L"open", g_url, NULL, NULL, SW_SHOWNORMAL);
}

static void on_line(wchar_t *line) {
    if (wcsncmp(line, L"##PMT ", 6) == 0) {
        wchar_t *cmd = line + 6;
        if (wcsncmp(cmd, L"step ", 5) == 0) {
            lstrcpynW(g_step, cmd + 5, 512);
            show_status();
            wchar_t s[600];
            _snwprintf(s, 599, L"\x00BB %s", cmd + 5);
            s[599] = 0;
            log_append(s);
        } else if (wcsncmp(cmd, L"ready ", 6) == 0) {
            lstrcpynW(g_url, cmd + 6, 512);
            set_state(READY, L"Project Management Tool is running", L"PMT is open in your browser.",
                      L"Keep this window open while you work (you can minimise it). Closing it stops PMT; your work is saved as you go.");
            open_browser();
        } else if (wcsncmp(cmd, L"already ", 8) == 0) {
            lstrcpynW(g_url, cmd + 8, 512);
            g_already = 1;
            set_state(READY, L"Project Management Tool is already running", L"Opening it in your browser.", L"This window closes by itself.");
            open_browser();
            SetTimer(g_wnd, TIMER_CLOSE, 2500, NULL);
        } else if (wcsncmp(cmd, L"fail ", 5) == 0) {
            lstrcpynW(g_fail, cmd + 5, 512);
            log_append(cmd + 5);
        } else if (wcscmp(cmd, L"ask-python") == 0) {
            g_asked = 1;
        }
        return;
    }
    log_append(line);
}

static void on_exit(DWORD code) {
    if (g_already) return;
    if (code == 10 && g_asked && !g_install_python) {
        int a = MessageBoxW(g_wnd,
            L"Python 3.10 or later was not found on this PC. PMT needs it.\n\n"
            L"PMT can download Python from python.org and install it for your user only. No administrator rights are "
            L"needed. The download is about 28 MB and its digital signature is checked before it is run.\n\n"
            L"Some companies do not allow installing software. If you are unsure, choose No and ask IT.\n\n"
            L"Download and install Python now?",
            L"Project Management Tool", MB_YESNO | MB_ICONQUESTION);
        if (a == IDYES) {
            g_install_python = 1;
            g_asked = 0;
            g_t0 = GetTickCount();
            lstrcpynW(g_step, L"Installing Python (first run only)...", 512);
            if (start_run()) return;
        }
        set_state(FAILED, L"Project Management Tool could not start", L"Python is needed.",
                  L"Install Python 3.10 or later from python.org (tick \"Add python.exe to PATH\"), or ask IT. Then open PMT again.");
        return;
    }
    if (g_state == READY) {
        set_state(STOPPED, L"Project Management Tool has stopped", L"PMT has stopped.", L"Open PMT.exe again to restart it.");
        if (code) set_expanded(1);
        return;
    }
    set_state(FAILED, L"Project Management Tool could not start", g_fail[0] ? g_fail : L"Something went wrong. The details are below.",
              L"Click \"Copy details\" and send the text on, or close this window and try again.");
    if (!g_expanded) set_expanded(1);
}

static int confirm_stop(void) {
    if (g_state != READY && g_state != WORKING) return 1;
    return MessageBoxW(g_wnd, g_state == READY ? L"Stop PMT? Your work is saved as you go; PMT stops until you open it again."
                                               : L"PMT is still starting. Stop it?",
                       L"Project Management Tool", MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2) == IDYES;
}

static HWND mk(const wchar_t *cls, const wchar_t *text, DWORD style, int id, HFONT f) {
    HWND w = CreateWindowExW(0, cls, text, WS_CHILD | WS_VISIBLE | style, 0, 0, 10, 10, g_wnd, (HMENU)(INT_PTR)id, g_inst, NULL);
    SendMessageW(w, WM_SETFONT, (WPARAM)f, TRUE);
    return w;
}

static LRESULT CALLBACK wndproc(HWND h, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        g_wnd = h;
        g_title = mk(L"STATIC", L"Project Management Tool loading...", SS_LEFT | SS_NOPREFIX, 0, g_bold);
        g_status = mk(L"STATIC", L"", SS_LEFT | SS_NOPREFIX | SS_ENDELLIPSIS, 0, g_font);
        g_bar = mk(PROGRESS_CLASSW, L"", PBS_MARQUEE | PBS_SMOOTH, 0, g_font);
        SendMessageW(g_bar, PBM_SETMARQUEE, TRUE, 30);
        g_hint = mk(L"STATIC", L"The first start on a PC installs what PMT needs and can take a few minutes.", SS_LEFT | SS_NOPREFIX, 0, g_font);
        g_more = mk(L"BUTTON", L"More info \x25BE", BS_PUSHBUTTON, ID_MORE, g_font);
        g_copy = mk(L"BUTTON", L"Copy details", BS_PUSHBUTTON, ID_COPY, g_font);
        g_open = mk(L"BUTTON", L"Open in browser", BS_PUSHBUTTON, ID_OPEN, g_font);
        g_stop = mk(L"BUTTON", L"Stop PMT", BS_PUSHBUTTON, ID_STOP, g_font);
        g_log = mk(L"EDIT", L"", WS_BORDER | WS_VSCROLL | ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL, 0, g_mono);
        SendMessageW(g_log, EM_SETLIMITTEXT, 2000000, 0);
        ShowWindow(g_copy, SW_HIDE);
        ShowWindow(g_log, SW_HIDE);
        EnableWindow(g_open, FALSE);
        SetTimer(h, TIMER_TICK, 1000, NULL);
        return 0;
    }
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(h, &ps);
        if (g_tile) DrawIconEx(dc, S(16), S(16), g_tile, S(68), S(68), 0, NULL, DI_NORMAL);
        EndPaint(h, &ps);
        return 0;
    }
    case WM_CTLCOLORSTATIC: {
        HDC dc = (HDC)wp;
        HWND c = (HWND)lp;
        if (c == g_log) return DefWindowProcW(h, msg, wp, lp);
        SetBkMode(dc, TRANSPARENT);
        if (c == g_title) SetTextColor(dc, g_state == FAILED ? RED : NAVY);
        else if (c == g_status) SetTextColor(dc, g_state == FAILED ? RED : (g_state == READY ? GREEN : NAVY));
        else SetTextColor(dc, GREY);
        return (LRESULT)g_bg;
    }
    case WM_SETCURSOR:
        if (g_state == WORKING && LOWORD(lp) == HTCLIENT) {
            SetCursor(LoadCursorW(NULL, IDC_APPSTARTING)); /* arrow with hourglass while PMT starts */
            return TRUE;
        }
        break;
    case WM_TIMER:
        if (wp == TIMER_TICK && g_state == WORKING) show_status();
        if (wp == TIMER_CLOSE) DestroyWindow(h);
        return 0;
    case WM_APP_LINE:
        on_line((wchar_t *)lp);
        free((void *)lp);
        return 0;
    case WM_APP_EXIT:
        on_exit((DWORD)wp);
        return 0;
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case ID_MORE: set_expanded(!g_expanded); return 0;
        case ID_COPY: copy_log(); return 0;
        case ID_OPEN: open_browser(); return 0;
        case ID_STOP:
            if (confirm_stop()) DestroyWindow(h);
            return 0;
        }
        break;
    case WM_CLOSE:
        if (g_already || confirm_stop()) DestroyWindow(h);
        return 0;
    case WM_DESTROY:
        if (g_job) TerminateJobObject(g_job, 0);
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(h, msg, wp, lp);
}

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPSTR args, int show) {
    (void)hPrev;
    (void)args;
    g_inst = hInst;
    SetProcessDPIAware();
    HDC sdc = GetDC(NULL);
    g_dpi = GetDeviceCaps(sdc, LOGPIXELSY);
    ReleaseDC(NULL, sdc);

    DWORD n = GetModuleFileNameW(NULL, g_dir, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return 1;
    wchar_t *slash = wcsrchr(g_dir, L'\\');
    if (slash) *slash = 0;
    wchar_t bat[MAX_PATH + 16];
    _snwprintf(bat, MAX_PATH + 15, L"%s\\run.bat", g_dir);
    bat[MAX_PATH + 15] = 0;
    if (GetFileAttributesW(bat) == INVALID_FILE_ATTRIBUTES) {
        /* a copy on its own (e.g. clicked in SharePoint in the browser, which only downloads it): run the synced PMT */
        wchar_t home[MAX_PATH], exe[MAX_PATH + 16];
        HCURSOR old = SetCursor(LoadCursorW(NULL, IDC_WAIT));
        int ok = find_synced(home);
        SetCursor(old);
        if (ok) {
            _snwprintf(exe, MAX_PATH + 15, L"%s\\PMT.exe", home);
            exe[MAX_PATH + 15] = 0;
            if ((INT_PTR)ShellExecuteW(NULL, L"open", exe, NULL, home, SW_SHOWNORMAL) > 32) return 0;
        }
        MessageBoxW(NULL,
                    L"PMT could not find its folder on this PC.\n\n"
                    L"Opening PMT.exe from SharePoint in the browser only downloads the program; PMT has to run from the "
                    L"SharePoint library synced to this PC, where its program files and the shared project data are.\n\n"
                    L"Do this once:\n"
                    L"1. In SharePoint, open the library that holds PMT and click Sync (or \"Add shortcut to My files\").\n"
                    L"2. Open File Explorer. The library is in the left pane, under your organisation's name (or under OneDrive).\n"
                    L"3. Open the PMT folder, right-click it, choose \"Always keep on this device\", then double-click PMT.exe.\n\n"
                    L"After that, clicking PMT.exe in SharePoint finds that copy and opens it. You can delete this downloaded copy.",
                    L"Project Management Tool: run PMT from File Explorer first", MB_ICONINFORMATION | MB_OK);
        return 1;
    }
    remember_home(); /* so a copy downloaded from SharePoint can find this one */

    INITCOMMONCONTROLSEX icc = {sizeof icc, ICC_PROGRESS_CLASS | ICC_STANDARD_CLASSES};
    InitCommonControlsEx(&icc);
    /* everything run.bat starts is stopped when this window closes */
    g_job = CreateJobObjectW(NULL, NULL);
    if (g_job) {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION li;
        ZeroMemory(&li, sizeof li);
        li.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(g_job, JobObjectExtendedLimitInformation, &li, sizeof li);
    }

    g_font = CreateFontW(-MulDiv(9, g_dpi, 72), 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
    g_bold = CreateFontW(-MulDiv(13, g_dpi, 72), 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
    g_mono = CreateFontW(-MulDiv(9, g_dpi, 72), 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Consolas");
    g_bg = GetSysColorBrush(COLOR_WINDOW);
    g_tile = (HICON)LoadImageW(hInst, MAKEINTRESOURCEW(1), IMAGE_ICON, S(68), S(68), LR_DEFAULTCOLOR);

    WNDCLASSEXW wc;
    ZeroMemory(&wc, sizeof wc);
    wc.cbSize = sizeof wc;
    wc.lpfnWndProc = wndproc;
    wc.hInstance = hInst;
    wc.hIcon = (HICON)LoadImageW(hInst, MAKEINTRESOURCEW(1), IMAGE_ICON, GetSystemMetrics(SM_CXICON), GetSystemMetrics(SM_CYICON), 0);
    wc.hIconSm = (HICON)LoadImageW(hInst, MAKEINTRESOURCEW(1), IMAGE_ICON, GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON), 0);
    wc.hCursor = LoadCursorW(NULL, IDC_ARROW);
    wc.hbrBackground = g_bg;
    wc.lpszClassName = L"PMTLauncher";
    RegisterClassExW(&wc);

    DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
    RECT r = {0, 0, S(600), S(178)};
    AdjustWindowRectEx(&r, style, FALSE, 0);
    int ww = r.right - r.left, wh = r.bottom - r.top;
    HWND h = CreateWindowExW(0, L"PMTLauncher", L"Project Management Tool", style,
                             (GetSystemMetrics(SM_CXSCREEN) - ww) / 2, (GetSystemMetrics(SM_CYSCREEN) - wh) / 3, ww, wh,
                             NULL, NULL, hInst, NULL);
    if (!h) return 1;
    layout();
    g_t0 = GetTickCount();
    show_status();
    ShowWindow(h, show);
    UpdateWindow(h);
    if (!start_run()) {
        set_state(FAILED, L"Project Management Tool could not start", L"run.bat could not be started.", L"Close this window and try again.");
    }

    MSG m;
    while (GetMessageW(&m, NULL, 0, 0) > 0) {
        if (!IsDialogMessageW(h, &m)) {
            TranslateMessage(&m);
            DispatchMessageW(&m);
        }
    }
    return 0;
}
