"""Standard EPEC CBS taxonomy and the fixed lists used across the tool.

The grandparent and parent codes are the EPEC company standard (shared with Finance and Pronto).
Child levels below a parent are project specific and are built in the app.
"""

GRANDPARENTS = {
    "PL": "Project Labour",
    "PS": "Project Subcontractors",
    "PM": "Materials & Equipment",
    "PE": "Expenses & Indirects",
}

GP_GROUP = {"PL": "Labour", "PS": "Subcontractors", "PM": "Materials", "PE": "Expenses"}

PARENTS = [
    ("PL01", "Project Mgmt/Admin Labour"), ("PL02", "Design Labour"), ("PL03", "Engineering Labour"),
    ("PL04", "Construction Labour"), ("PL05", "Testing/Compliance Labour"), ("PL06", "Transmission Lines"),
    ("PL07", "SCADA Labour"), ("PL08", "LAHA"),
    ("PS01", "Project Mgmt/Admin Subcontractors"), ("PS02", "Design Subcontractors"),
    ("PS03", "Engineering Subcontractors"), ("PS04", "Construction Subcontractors"),
    ("PS05", "Testing/Compliance Subcontractors"), ("PS06", "Transmission Lines"),
    ("PS07", "SCADA Subcontractors"),
    ("PM01", "Comms/SCADA Equipment"), ("PM02", "Transformers"), ("PM03", "Primary Equipment"),
    ("PM04", "Secondary Equipment"), ("PM05", "Cables and Accessories"), ("PM06", "Misc Materials"),
    ("PM07", "Civil Materials"), ("PM08", "Spares"),
    ("PE01", "Travel And Accomm"), ("PE02", "Equipment/Plant Hire"), ("PE03", "Site Indirects"),
    ("PE04", "Vehicle Costs (incl Hire)"), ("PE05", "Freight"), ("PE06", "BG Fees"), ("PE07", "Insurance"),
    ("PE08", "Misc Overheads"), ("PE09", "Contingency"),
]

# Forecast methods (see the workbook ReadMe, FORECAST METHOD COLOURS) plus MANUAL for typed months.
METHODS = {
    "GROUND-UP": "Built line by line from forecast items (quantity x rate over time).",
    "CLAIM": "Net monthly amounts from a subcontract claim schedule.",
    "BURN-RATE": "Average monthly spend to date x remaining months (current month excluded).",
    "AT-BUDGET": "Remaining allowance: spend what is left, no more, no less.",
    "AT-COMMIT": "Outstanding PO commitments plus an estimate of what is still uncommitted.",
    "TOP-DOWN": "EAC typed directly; cost to complete is EAC less cost to date and accruals.",
    "MANUAL": "Monthly amounts typed directly on the line.",
    "NONE": "No forecast: only what has landed (cost to date and accruals).",
}

DEFAULT_METHOD_BY_GP = {"PL": "BURN-RATE", "PS": "AT-BUDGET", "PM": "AT-COMMIT", "PE": "BURN-RATE"}

SPREAD_MODES = ["Lump", "Linear", "Recurring", "Manual", "Calendar", "Milestones", "Roster"]
SPREAD_NOTES = {
    "Calendar": "Day grid for one resource on this line: type hours (x rate), units (x rate) or dollars per day.",
    "Milestones": "Payment milestones: each with its % of the item value and the month the supplier is expected to reach it.",
    "Roster": "A pattern such as 10:4 from a start date for a number of swings, x headcount x hours a shift, priced from the supplier rates.",
    "Lump": "All in the start month.", "Linear": "Even from start to end.", "Recurring": "Quantity x rate every period.",
    "Manual": "Typed amounts per month.",
}
FORECAST_BASIS = {"hours": "Hours x rate", "people": "People a day x hours a shift (crews, lookaheads)", "units": "Units x rate (days, nights, ea)", "dollars": "Dollars typed directly"}
ROSTER_PATTERNS = ["10:4", "14:7", "8:6", "7:7", "21:7", "5:2", "WEEKDAYS", "DAILY"]
MILESTONE_PRESETS = {
    "Long-lead equipment": [("On order", 0.10), ("Drawing submission", 0.15), ("Drawing approval", 0.10), ("FAT", 0.20), ("Delivery to site", 0.35), ("SAT / commissioning", 0.10)],
    "Standard procurement": [("On order", 0.10), ("Delivery", 0.80), ("Documentation / close-out", 0.10)],
    "Design package": [("30% design", 0.30), ("70% design", 0.40), ("IFC", 0.30)],
}
FREQUENCIES = ["Daily", "Weekly", "Fortnightly", "Monthly"]

CLIENT_STATUS = ["Pending", "Under Review", "In Discussion", "Approved", "Denied", "Withdrawn"]
EPEC_STATUS = ["Drafting", "Submitted", "Pursuing", "In Dispute", "Agreed", "Dropped"]
CONTRACT_STATUS = ["n/a", "Not started", "In progress", "Executed"]
PRICING_MODELS = {"LS": "Lump Sum", "PS": "Provisional Sum", "T&M": "Time & Materials",
                  "C+": "Cost-Plus", "SOR": "Schedule of Rates", "GMP": "Guaranteed Maximum Price",
                  "TCA": "Target Cost Agreement"}

CLAIM_STATUS = ["draft", "submitted", "certified", "paid"]
ACCRUAL_REASONS = [
    "Timesheets not yet posted", "Invoice received, held for approval", "Work done, invoice not yet received",
    "Card / expense claim not yet reconciled", "Cost to be journalled in from another project",
    "Correction to earlier accrual", "Other",
]

COST_CATEGORY_RE = r"^(PL|PS|PM|PE)\d{2}$"
