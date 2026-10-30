"""Exported workbooks open on the deliverable: helper sheets (lists behind the dropdowns, instructions, read me) go
after it. Call deliverable_first(wb) just before wb.close() on an xlsxwriter workbook."""

HELPERS = ("lists", "instructions", "read me")


def deliverable_first(wb, helpers=HELPERS):
    sheets = list(wb.worksheets_objs)
    main = [s for s in sheets if s.name.lower() not in helpers]
    if not main:
        return
    wb.worksheets_objs[:] = main + [s for s in sheets if s.name.lower() in helpers]
    for i, s in enumerate(wb.worksheets_objs):
        s.index = i
        s.selected = 0
        s.active = 0
    wb.worksheet_meta.activesheet = 0
    wb.worksheet_meta.firstsheet = 0
    main[0].activate()
