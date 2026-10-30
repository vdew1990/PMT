"""The outline for month and day grids (static/js/outlinecore.js): which columns show, and what the 1 2 (3) levels do.
Run with node; skipped when node is not installed."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")

SCRIPT = r"""
import * as o from './outlinecore.mjs';
const months = ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06','2026-07','2026-08','2026-09','2026-10','2026-11','2026-12'].map((id) => ({ id }));
const cur = months.findIndex((c) => c.id === '2026-09');
const out = {};
out.q = o.fyQuarter('2026-07').key + '|' + o.fyQuarter('2026-06').key + '|' + o.fyQuarter('2026-01').label;
// default: quarters before the current one are folded; the current column always shows
let st = { folded: null, hidden: [] };
let v = o.visible(months, cur, st, o.MONTH_LEVELS);
out.defaultShown = months.filter((c, i) => v[i]).map((c) => c.id);
// the current month stays when its own quarter is folded, the rest of the quarter goes
st = { folded: ['0:2027-Q1'], hidden: [] };
v = o.visible(months, cur, st, o.MONTH_LEVELS);
out.curQuarterFolded = months.filter((c, i) => v[i]).map((c) => c.id).filter((m) => m >= '2026-07' && m <= '2026-09');
// hidden single months
st = { folded: [], hidden: ['2026-02', '2026-11'] };
v = o.visible(months, cur, st, o.MONTH_LEVELS);
out.hiddenGone = months.filter((c, i) => !v[i]).map((c) => c.id);
// levels, months: 1 = this quarter only, 2 = every month
out.l1 = o.levelFolds(months, cur, o.MONTH_LEVELS, 1).sort();
out.l2 = o.levelFolds(months, cur, o.MONTH_LEVELS, 2);
out.curLevel1 = o.currentLevel(months, cur, { folded: out.l1, hidden: [] }, o.MONTH_LEVELS);
out.curLevel2 = o.currentLevel(months, cur, { folded: [], hidden: [] }, o.MONTH_LEVELS);
out.curLevelNone = o.currentLevel(months, cur, { folded: [], hidden: ['2026-02'] }, o.MONTH_LEVELS);
// days: month then week
const days = []; for (let d = new Date(Date.UTC(2026, 8, 14)); d <= new Date(Date.UTC(2026, 9, 11)); d.setUTCDate(d.getUTCDate() + 1)) days.push({ id: d.toISOString().slice(0, 10) });
const dcur = days.findIndex((c) => c.id === '2026-09-30');
const shownAt = (L) => { const st2 = { folded: L === 3 ? [] : o.levelFolds(days, dcur, o.DAY_LEVELS, L), hidden: [] }; const vv = o.visible(days, -1, st2, o.DAY_LEVELS); return days.filter((c, i) => vv[i]).map((c) => c.id); };
out.d1 = shownAt(1); out.d2n = shownAt(2).length; out.d3n = shownAt(3).length; out.dall = days.length;
out.wk = o.DAY_LEVELS[1].label({ id: '2026-09-30' }) + '|' + o.DAY_LEVELS[1].key({ id: '2026-09-30' });
console.log(JSON.stringify(out));
"""


def _run():
    d = Path(tempfile.mkdtemp(prefix="pmt-outline-"))
    (d / "outlinecore.mjs").write_text((ROOT / "static" / "js" / "outlinecore.js").read_text())
    (d / "t.mjs").write_text(SCRIPT)
    r = subprocess.run(["node", str(d / "t.mjs")], capture_output=True, text=True, cwd=d, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_outline_logic():
    o = _run()
    assert o["q"] == "2027-Q1|2026-Q4|Q3 FY26"                                   # July starts the financial year
    assert o["defaultShown"] == ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"]   # earlier quarters folded
    assert "2026-09" in o["curQuarterFolded"] and "2026-07" not in o["curQuarterFolded"]   # the current month always shows
    assert o["hiddenGone"] == ["2026-02", "2026-11"]
    assert "0:2027-Q1" not in o["l1"] and len(o["l1"]) == 3 and o["l2"] == []   # level 1 folds every quarter but this one
    assert o["curLevel1"] == 1 and o["curLevel2"] == 2 and o["curLevelNone"] == 0
    assert o["d1"] == ["2026-09-28", "2026-09-29", "2026-09-30"]                  # level 1 on a day grid: this week (its days in this month; October is folded)
    assert o["d2n"] > 7 and o["d3n"] == o["dall"]                                # 2: this month's days, 3: every day
    assert o["wk"] == "Wk 28 Sep|2026-09-28"
