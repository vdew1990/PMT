"""Argus: browser flow for the F4 front end (Finn, commit 6c433aa): schedule link suggestions on upload.

Expected results are Finn's brief as relayed by Atlas. Chromium stand-in; Edge itself is not tested. Synthetic data only."""
import re

import httpx
from playwright.sync_api import expect

CSV_A = "WBS,Name,Start,Finish\n1.1,Earthworks,01/11/2026,31/01/2027\n1.2,Fencing,01/12/2026,28/02/2027\n1.3,Old drainage,01/12/2026,28/02/2027\n"
CSV_B = "WBS,Name,Start,Finish\n1.1,Earthworks,01/11/2026,31/01/2027\n1.2,Fencing,01/12/2026,28/02/2027\n"
SHOTS = None


def _seed(base, name):
    c = httpx.Client(base_url=base, timeout=30)
    pid = c.post("/api/projects", json=dict(name=name, project_start="01/01/2026", project_end="30/06/2027", status_date="30/09/2026")).json()["id"]
    rows = c.get(f"/api/p/{pid}/cost-control").json()["rows"]
    ps = next(r["id"] for r in rows if r.get("code") == "PS" and r.get("kind") == "group")
    g = c.post(f"/api/p/{pid}/nodes", json=dict(parent_id=ps, kind="group", code="PS94", name="Synthetic group")).json()["id"]
    for code, nm in (("PS94.001", "Earthworks"), ("PS94.002", "Fencing"), ("PS94.003", "Old drainage")):
        r = c.post(f"/api/p/{pid}/nodes", json=dict(parent_id=g, kind="line", code=code, name=nm, method="AT-BUDGET"))
        assert r.status_code == 200, r.text
    return c, pid


def _open(page, base, pid, view=None):
    page.add_init_script(f"localStorage.setItem('pmt', JSON.stringify({{pid: {pid}, scope: {{node: null, from: null, to: null}}}}))")
    page.goto(base + "/#/programme" + ("?view=" + view if view else ""))
    page.wait_for_load_state("networkidle")


def _upload(page, tmp_path, name, text):
    f = tmp_path / name
    f.write_text(text)
    zone = page.locator("div:has(> .dz:has-text('internal project schedule')) > input[type=file]").first
    zone.set_input_files(str(f))


def _toast(page, text):
    expect(page.locator("#toasts .toast").filter(has_text=text).first).to_be_visible(timeout=10000)


def _dialog(page, title):
    return page.locator(".md").filter(has=page.locator("h2", has_text=title))


def _rows(dlg):
    return dlg.locator(".mb tbody tr")


def _kpi_linked(page):
    k = page.locator(".kpi").filter(has_text="Tasks linked").first
    return k


def test_f4_suggestions_flow(pmt_server, browser_page, tmp_path):
    base, page = pmt_server, browser_page
    c, pid = _seed(base, "F4 UI synthetic")
    _open(page, base, pid, "update")
    page.screenshot(path=str(tmp_path / "0-start.png"))

    # a. upload CSV A
    _upload(page, tmp_path, "a.csv", CSV_A)
    _toast(page, "3 tasks read from CSV; 0 links kept; 3 suggested links waiting for your review; 0 lines lost their schedule link; 0 activity windows updated")
    dlg = _dialog(page, "Suggested schedule links")
    expect(dlg).to_be_visible()
    expect(_rows(dlg)).to_have_count(3)
    expect(dlg.get_by_role("button", name="Accept all (3)")).to_be_visible()
    focused = page.evaluate("() => [document.activeElement.textContent, document.activeElement.closest('tr') ? document.activeElement.closest('tr').textContent : '']")
    assert focused[0].strip() == "Accept" and "Earthworks" in focused[1], focused
    expect(_kpi_linked(page)).to_contain_text(re.compile(r"Tasks linked\s*0"))
    page.screenshot(path=str(tmp_path / "a.png"))

    # b. Enter accepts Earthworks
    page.keyboard.press("Enter")
    expect(dlg.locator("[role=status]")).to_have_text("Linked: Earthworks to CBS line PS94.001 Earthworks.")
    expect(_rows(dlg)).to_have_count(2)
    focused = page.evaluate("() => [document.activeElement.textContent, document.activeElement.closest('tr') ? document.activeElement.closest('tr').textContent : '']")
    assert focused[0].strip() == "Accept" and "Fencing" in focused[1], focused

    # c. Tab, Enter rejects Fencing
    page.keyboard.press("Tab")
    focused = page.evaluate("() => document.activeElement.textContent")
    assert focused.strip() == "Reject", focused
    page.keyboard.press("Enter")
    expect(dlg.locator("[role=status]")).to_have_text(re.compile(r"^Rejected: Fencing"))
    expect(_rows(dlg)).to_have_count(1)
    expect(dlg.get_by_role("button", name="Accept all (1)")).to_be_visible()
    page.screenshot(path=str(tmp_path / "c.png"))

    # d. Accept all (1)
    dlg.get_by_role("button", name="Accept all (1)").click()
    _toast(page, "1 link accepted.")
    expect(dlg).to_have_count(0)
    expect(_kpi_linked(page)).to_contain_text(re.compile(r"Tasks linked\s*2"))
    # API cross-check: Earthworks and Old drainage linked, Fencing not
    linked = {t["name"] for t in c.get(f"/api/p/{pid}/programme/tasks").json() if t["link_node_id"]}
    assert linked == {"Earthworks", "Old drainage"}, linked
    # Fencing is not offered again on a re-upload of CSV A
    _upload(page, tmp_path, "a2.csv", CSV_A)
    _toast(page, "0 suggested links waiting for your review")
    expect(_dialog(page, "Suggested schedule links")).to_have_count(0)
    assert c.get(f"/api/p/{pid}/programme/suggestions").json() == []

    # e. CSV B drops Old drainage
    _upload(page, tmp_path, "b.csv", CSV_B)
    _toast(page, "1 line lost its schedule link")
    lost = _dialog(page, "Lines that lost their schedule link (1 line)")
    expect(lost).to_be_visible()
    expect(_rows(lost)).to_have_count(1)
    cells = [x.strip() for x in _rows(lost).first.locator("td").all_inner_texts()]
    assert cells == ["PS94.003", "Old drainage", "Start and Stop", "1.3 Old drainage", "01/12/2026", "28/02/2027"], cells
    page.screenshot(path=str(tmp_path / "e.png"))
    assert page.js_errors == [], page.js_errors


def test_f4_pending_suggestions_buttons(pmt_server, browser_page, tmp_path):
    base, page = pmt_server, browser_page
    c, pid = _seed(base, "F4 UI fresh synthetic")
    _open(page, base, pid, "update")
    _upload(page, tmp_path, "a.csv", CSV_A)
    dlg = _dialog(page, "Suggested schedule links")
    expect(dlg).to_be_visible()
    dlg.locator(".mf button", has_text="Close").click()
    expect(dlg).to_have_count(0)
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("button", name="Review suggested links (3)")).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("Link by name"))).to_have_count(0)

    page.goto(base + "/#/programme")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text(re.compile(r"3 suggested links are waiting for your review"))).to_be_visible()
    expect(page.get_by_role("button", name=re.compile(r"^Review"))).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("Link by name"))).to_have_count(0)
    page.screenshot(path=str(tmp_path / "f-schedule.png"))

    # clear the suggestions (reject all over the API), then neither button is shown
    assert c.post(f"/api/p/{pid}/programme/suggestions/reject", json={"all": True}).status_code == 200
    page.reload()
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text(re.compile("suggested links? (are|is) waiting"))).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile(r"^Review suggested"))).to_have_count(0)
    page.goto(base + "/#/programme?view=update")
    page.wait_for_load_state("networkidle")
    expect(page.locator(".kpi").filter(has_text="Tasks linked").first).to_be_visible()
    expect(page.get_by_role("button", name=re.compile(r"Review suggested links"))).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile("Link by name"))).to_have_count(0)
    assert page.js_errors == [], page.js_errors
