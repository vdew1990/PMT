"""Read an OpenDocument spreadsheet (.ods, as saved by LibreOffice or Excel) without extra packages.

sheets(path) -> [(sheet_name, [row tuple, ...])], values typed the way openpyxl gives them for an .xlsx: numbers as int
or float, dates as datetime, booleans, text as str, empty cells as None. Repeated cells and rows (LibreOffice pads a
sheet to a million rows that way) are expanded only up to the last cell that holds something.
"""
import zipfile
from datetime import datetime
from xml.etree.ElementTree import iterparse

NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
T = lambda ns, tag: f"{{{NS[ns]}}}{tag}"  # noqa: E731
TABLE, ROW, CELL, COVERED = T("table", "table"), T("table", "table-row"), T("table", "table-cell"), T("table", "covered-table-cell")
P, SPACE, TAB, BREAK = T("text", "p"), T("text", "s"), T("text", "tab"), T("text", "line-break")
A_NAME, A_COLS, A_ROWS = T("table", "name"), T("table", "number-columns-repeated"), T("table", "number-rows-repeated")
A_TYPE, A_VALUE, A_DATE, A_BOOL = T("office", "value-type"), T("office", "value"), T("office", "date-value"), T("office", "boolean-value")


def _text(el):
    """A text:p as the user sees it: text:s is that many spaces, text:tab a tab, text:line-break a new line."""
    out = [el.text or ""]
    for ch in el:
        if ch.tag == SPACE:
            out.append(" " * int(ch.get(T("text", "c"), "1")))
        elif ch.tag == TAB:
            out.append("\t")
        elif ch.tag == BREAK:
            out.append("\n")
        else:
            out.append(_text(ch))
        out.append(ch.tail or "")
    return "".join(out)


def _value(cell):
    kind = cell.get(A_TYPE)
    if kind in ("float", "percentage", "currency"):
        v = float(cell.get(A_VALUE))
        return int(v) if v.is_integer() and abs(v) < 1e15 else v
    if kind == "date":
        s = cell.get(A_DATE)
        try:
            return datetime.fromisoformat(s[:19])
        except ValueError:
            return s
    if kind == "boolean":
        return cell.get(A_BOOL) == "true"
    paras = [_text(p) for p in cell.findall(P)]
    if kind in ("string", "time") or paras:
        s = "\n".join(paras)
        return s if s != "" else None
    return None


def sheets(path):
    out = []
    with zipfile.ZipFile(path) as z, z.open("content.xml") as f:
        name, rows, pending_rows = None, [], 0
        row, pending_cells = None, 0
        for ev, el in iterparse(f, events=("start", "end")):
            if ev == "start":
                if el.tag == TABLE:
                    name, rows, pending_rows = el.get(A_NAME), [], 0
                elif el.tag == ROW:
                    row, pending_cells = [], 0
                continue
            if el.tag in (CELL, COVERED) and row is not None:
                v = _value(el) if el.tag == CELL else None
                n = int(el.get(A_COLS, "1"))
                if v is None:
                    pending_cells += n          # empty cells count only if something follows them on the row
                else:
                    row.extend([None] * pending_cells)
                    pending_cells = 0
                    row.extend([v] * n)
                el.clear()
            elif el.tag == ROW and row is not None:
                n = int(el.get(A_ROWS, "1"))
                if row:
                    rows.extend([()] * pending_rows)
                    pending_rows = 0
                    rows.extend([tuple(row)] * n)
                else:
                    pending_rows += n           # empty rows count only if a row with values follows
                row = None
                el.clear()
            elif el.tag == TABLE:
                out.append((name, rows))
                el.clear()
    return out
