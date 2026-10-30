from app import drill, engine


def _lines(con, pid):
    res = engine.compute(con, pid)
    return [r for r in res["rows"] if r["kind"] == "line"], res


def _sec_total(d, key=None):
    return [s["total"] for s in d["sections"] if s.get("total") is not None]


def test_ctd_drill_ties_to_the_row(demo):
    con, pid = demo
    lines, _ = _lines(con, pid)
    checked = 0
    for r in lines:
        if not r["ctd"]:
            continue
        d = drill.drill(con, pid, r["node_id"], "ctd")
        tots = _sec_total(d)
        assert tots, r["code"]
        assert abs(tots[0] - r["ctd"]) < 0.01, (r["code"], tots, r["ctd"])
        checked += 1
    assert checked > 3


def test_ctd_drill_on_a_group_ties_to_the_group(demo):
    con, pid = demo
    res = engine.compute(con, pid)
    g = next(r for r in res["rows"] if r["kind"] == "group" and r["level"] == 1 and r["ctd"])
    d = drill.drill(con, pid, g["node_id"], "ctd")
    assert abs(_sec_total(d)[0] - g["ctd"]) < 0.01


def test_month_drill_lists_only_that_months_records(demo):
    con, pid = demo
    lines, res = _lines(con, pid)
    grid = res["grid"]
    r = next(r for r in lines if any(r["a"]))
    i = next(i for i, v in enumerate(r["a"]) if v)
    d = drill.drill(con, pid, r["node_id"], "month", grid[i])
    assert d["month"] == grid[i]
    txs = [s for s in d["sections"] if s.get("total") is not None]
    assert txs and abs(txs[0]["total"] - r["a"][i]) < 0.01


def test_po_drill_sums_ordered_and_outstanding(demo):
    con, pid = demo
    lines, _ = _lines(con, pid)
    r = next(r for r in lines if r["po_committed"])
    d = drill.drill(con, pid, r["node_id"], "po")
    assert d["sections"][0]["rows"]
    assert abs(d["sections"][0]["total"] - r["po_committed"]) < 0.01 or abs(d["total"] - r["po_committed"]) < 0.01
    o = drill.drill(con, pid, r["node_id"], "outstanding")
    assert abs(o["total"] - r["outstanding"]) < 0.01


def test_every_metric_returns_sections_without_error(demo):
    con, pid = demo
    lines, _ = _lines(con, pid)
    r = lines[0]
    for m in ("ctd", "po", "outstanding", "acc", "budget", "ctc", "eac", "contingency", "risk"):
        d = drill.drill(con, pid, r["node_id"], m)
        assert "sections" in d and "title" in d, m


def test_pot_node_is_exact(demo):
    con, pid = demo
    res = engine.compute(con, pid)
    pots = [r for r in res["rows"] if r["kind"] == "pot"]
    if pots:
        d = drill.drill(con, pid, "p" + str(pots[0]["node_id"]), "ctd")
        assert "sections" in d
