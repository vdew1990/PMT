PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  code TEXT, number TEXT,
  client_name TEXT, client_project_name TEXT, client_project_number TEXT, client_project_code TEXT,
  client_po TEXT, client_pm TEXT, epec_pm TEXT,
  contract_ref TEXT, early_works_ref TEXT,
  status_date TEXT, project_start TEXT, project_end TEXT, grid_start TEXT, grid_end TEXT,
  default_risk_pct REAL DEFAULT 0.07,
  tolerance REAL DEFAULT 1,
  initialised INTEGER DEFAULT 0, initialised_at TEXT,
  settings_json TEXT DEFAULT '{}',
  notes TEXT,
  version INTEGER DEFAULT 0,
  is_template INTEGER DEFAULT 0,
  archived_at TEXT, archived_by TEXT, archive_summary TEXT,
  location TEXT, project_director TEXT,
  project_type TEXT, capacity_mw REAL, storage_mwh REAL, voltage TEXT,   -- asset: Solar farm / BESS / Hybrid / Wind farm..., MW, MWh, e.g. 33/330 kV
  lat REAL, lon REAL,                  -- site location (portfolio map, travel in PM workload)
  complexity INTEGER,                  -- 1..5; blank = suggested (see workload.suggest_complexity)
  is_parent INTEGER DEFAULT 0,         -- a parent project over linked child projects (linking.py)
  parent_project_id INTEGER,           -- the parent this project is linked under
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resource (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('employee','supplier')),
  code TEXT NOT NULL,
  name TEXT,
  function TEXT,
  work_rate_code TEXT,
  cost_rate REAL, sell_rate REAL,
  status TEXT DEFAULT 'active',
  source TEXT DEFAULT 'manual',
  UNIQUE (project_id, kind, code)
);

CREATE TABLE IF NOT EXISTS rate_card (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  department TEXT, role TEXT NOT NULL, work_rate_code TEXT,
  cost_rate REAL, sell_rate REAL, fy TEXT, rev TEXT
);

CREATE TABLE IF NOT EXISTS cbs_node (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES cbs_node(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('group','line')),
  gp TEXT,
  category TEXT,               -- Pronto cost category (set on level-2 parent nodes)
  resource_id INTEGER REFERENCES resource(id) ON DELETE SET NULL,
  function TEXT, scope TEXT,
  po_no TEXT,                  -- optional PO number(s) bound to this line, comma separated
  method TEXT, start_date TEXT, end_date TEXT,
  eac_override REAL,           -- TOP-DOWN typed EAC
  uncommitted REAL DEFAULT 0,  -- AT-COMMIT estimate still to be committed
  unalloc_method TEXT,         -- method for the (Unallocated) pot of a group
  unalloc_eac REAL,
  sort_order INTEGER DEFAULT 0,
  origin TEXT DEFAULT 'manual',
  active INTEGER DEFAULT 1,
  notes TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE (project_id, code)
);
CREATE INDEX IF NOT EXISTS ix_cbs_parent ON cbs_node(project_id, parent_id);

CREATE TABLE IF NOT EXISTS allowance_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  node_id INTEGER NOT NULL REFERENCES cbs_node(id) ON DELETE CASCADE,
  date TEXT,
  kind TEXT NOT NULL,          -- estimate | transfer | variation | risk_release | adjustment
  budget REAL DEFAULT 0,
  risk REAL DEFAULT 0,                 -- company-held risk bucket (not part of the PM's allowance)
  contingency REAL DEFAULT 0,          -- earmark inside the budget for market movements (the PM separates it)
  risk_cover REAL DEFAULT 0,           -- earmark inside the budget that covers materialised risk costs
  ref TEXT, note TEXT,
  pair_id TEXT,
  variation_id INTEGER,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_allow_node ON allowance_ledger(project_id, node_id);

CREATE TABLE IF NOT EXISTS forecast_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  node_id INTEGER NOT NULL REFERENCES cbs_node(id) ON DELETE CASCADE,
  scope TEXT, note TEXT,
  spread TEXT DEFAULT 'Linear',    -- Lump | Linear | Recurring | Manual
  unit TEXT, qty REAL DEFAULT 1, rate REAL DEFAULT 0, pct REAL DEFAULT 1,
  start_date TEXT, end_date TEXT,
  freq TEXT, occurrences INTEGER,
  po_no TEXT, milestone TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS forecast_manual (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  node_id INTEGER NOT NULL REFERENCES cbs_node(id) ON DELETE CASCADE,
  item_id INTEGER,               -- NULL = line level (MANUAL method); else a forecast item (Manual spread)
  month TEXT NOT NULL,
  amount REAL NOT NULL,
  UNIQUE (node_id, item_id, month)
);

CREATE TABLE IF NOT EXISTS accrual (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  node_id INTEGER NOT NULL REFERENCES cbs_node(id) ON DELETE CASCADE,
  month TEXT NOT NULL,
  amount REAL NOT NULL,
  source TEXT DEFAULT 'PM',
  po_no TEXT, inv_ref TEXT, reason TEXT, note TEXT,
  status TEXT DEFAULT 'open',     -- open | matched | investigate | cancelled
  matched_amount REAL, matched_date TEXT,
  kind TEXT,                      -- work (estimate of work done) | invoice (awaiting approval) | hours (timesheet) ; see accruals.py
  supplier_code TEXT, supplier_name TEXT, quote_ref TEXT,
  matched_via TEXT, matched_month TEXT, matched_refs TEXT,   -- how and when the invoice landed (refs: JSON list)
  resolution TEXT,                -- invoice differs: accept (true up to the invoice) | rest_open (the rest still to come)
  created_at TEXT DEFAULT (datetime('now'))
);

-- Unposted timesheet hours the PM does not agree belong to this project: asked to be journalled elsewhere
CREATE TABLE IF NOT EXISTS timesheet_request (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  resource_code TEXT NOT NULL, person TEXT,
  date_from TEXT NOT NULL, date_to TEXT NOT NULL, hours REAL,
  target TEXT,                    -- the project (code / name) the hours should go to
  note TEXT,
  status TEXT DEFAULT 'requested',  -- requested | done (the hours left this project in Pronto) | withdrawn
  requested_at TEXT DEFAULT (datetime('now')), done_at TEXT
);

-- Pronto landing tables --------------------------------------------------
CREATE TABLE IF NOT EXISTS import_batch (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,           -- transactions | labour | po | claims | variations | ctd
  filename TEXT, sheet TEXT, mode TEXT,
  rows_read INTEGER, rows_new INTEGER, rows_skipped INTEGER,
  as_of TEXT, summary_json TEXT,
  uploaded_at TEXT DEFAULT (datetime('now')),
  active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pronto_tx (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  batch_id INTEGER REFERENCES import_batch(id) ON DELETE CASCADE,
  row_hash TEXT,
  category TEXT, cat_desc TEXT, account_code TEXT, account_desc TEXT,
  type TEXT, doc_type TEXT, doc_no TEXT, doc_suffix TEXT, doc_seq TEXT,
  tx_date TEXT, reference TEXT, description TEXT,
  qty REAL, cost REAL, charge REAL, variation_no TEXT,
  fin_year INTEGER, fin_period INTEGER,
  class TEXT,                    -- actual | journal | revenue | other
  resource_code TEXT, po_no TEXT,
  node_id INTEGER REFERENCES cbs_node(id) ON DELETE SET NULL,
  month TEXT
);
CREATE INDEX IF NOT EXISTS ix_tx_proj ON pronto_tx(project_id, class, node_id, month);
CREATE INDEX IF NOT EXISTS ix_tx_hash ON pronto_tx(project_id, row_hash);

CREATE TABLE IF NOT EXISTS pronto_labour (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  batch_id INTEGER REFERENCES import_batch(id) ON DELETE CASCADE,
  row_hash TEXT,
  resource_code TEXT, name TEXT, work_rate_code TEXT, work_rate TEXT,
  date_worked TEXT, month TEXT, status TEXT, approved TEXT,
  category TEXT, notes TEXT,
  hours REAL, cost_rate REAL, total_cost REAL, charge_rate REAL, total_charge REAL,
  posted INTEGER,
  node_id INTEGER REFERENCES cbs_node(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_lab_proj ON pronto_labour(project_id, posted, node_id, month);

CREATE TABLE IF NOT EXISTS pronto_po (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  batch_id INTEGER REFERENCES import_batch(id) ON DELETE CASCADE,
  row_hash TEXT,
  order_no TEXT, status TEXT, order_type TEXT,
  supplier_name TEXT, supplier_code TEXT,
  ordered TEXT, due TEXT, received_date TEXT,
  committed REAL, received REAL, invoiced_inc_tax REAL,
  category TEXT, category_desc TEXT, notes TEXT,
  is_open INTEGER,
  node_id INTEGER REFERENCES cbs_node(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_po_proj ON pronto_po(project_id, order_no, node_id);

CREATE TABLE IF NOT EXISTS pronto_claim (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  batch_id INTEGER REFERENCES import_batch(id) ON DELETE CASCADE,
  row_hash TEXT,
  claim_no TEXT, description TEXT, status TEXT, status_desc TEXT,
  date_created TEXT, date_submitted TEXT, date_certified TEXT, date_paid TEXT,
  total REAL, certified REAL, retained REAL, paid REAL, order_no TEXT
);

CREATE TABLE IF NOT EXISTS pronto_variation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  batch_id INTEGER REFERENCES import_batch(id) ON DELETE CASCADE,
  row_hash TEXT,
  variation_no TEXT, status TEXT, description TEXT,
  expected REAL, approved REAL, total_cost REAL, total_hours REAL,
  approved_date TEXT, customer_ref TEXT, instructed_by TEXT
);

CREATE TABLE IF NOT EXISTS pronto_ctd (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  batch_id INTEGER REFERENCES import_batch(id) ON DELETE CASCADE,
  category TEXT, description TEXT, cat_type TEXT,
  actual REAL, budget REAL, hrs_actual REAL, hrs_budget REAL
);

-- Revenue -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contract_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES contract_item(id) ON DELETE CASCADE,
  ref TEXT, description TEXT NOT NULL,
  stage TEXT,                    -- e.g. Early Works / EPC
  kind TEXT DEFAULT 'base',      -- base | optional | variation
  optional_status TEXT,          -- taken | declined | pending
  value REAL DEFAULT 0,
  phase TEXT, claim_requirement TEXT,
  start_date TEXT, end_date TEXT,
  method TEXT DEFAULT 'even',    -- even | lump | manual
  variation_id INTEGER,
  sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS revenue_plan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES contract_item(id) ON DELETE CASCADE,
  month TEXT NOT NULL,
  amount REAL NOT NULL,
  UNIQUE (item_id, month)
);

CREATE TABLE IF NOT EXISTS claim (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  claim_no TEXT, period TEXT NOT NULL,
  status TEXT DEFAULT 'draft',
  submitted_date TEXT, certified_date TEXT, paid_date TEXT,
  certified_amount REAL, paid_amount REAL, retention REAL DEFAULT 0,
  pronto_claim_no TEXT, note TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS claim_line (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id INTEGER NOT NULL REFERENCES claim(id) ON DELETE CASCADE,
  item_id INTEGER NOT NULL REFERENCES contract_item(id) ON DELETE CASCADE,
  amount REAL DEFAULT 0,               -- claimed to the client this period
  certified REAL,                      -- certified by the client; NULL until certified
  note TEXT,
  UNIQUE (claim_id, item_id)
);

CREATE TABLE IF NOT EXISTS variation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  ref TEXT NOT NULL,
  stage TEXT, title TEXT,
  description TEXT,
  client_status TEXT DEFAULT 'Pending',
  client_status_date TEXT,
  epec_status TEXT DEFAULT 'Drafting',
  epec_status_date TEXT,
  contract_change TEXT DEFAULT 'No',
  contract_status TEXT DEFAULT 'n/a',
  closed INTEGER DEFAULT 0, close_date TEXT,
  prepared_by TEXT, validity TEXT,
  pricing_model TEXT DEFAULT 'LS',
  pronto_ref TEXT,
  submission_date TEXT,
  outcome TEXT,
  schedule_item_id INTEGER,   -- the contract item this entry stands for (created from an uploaded contract); its revenue stays on that item
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE (project_id, ref)
);
CREATE TABLE IF NOT EXISTS variation_rev (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  variation_id INTEGER NOT NULL REFERENCES variation(id) ON DELETE CASCADE,
  rev INTEGER DEFAULT 0,
  date TEXT, value REAL DEFAULT 0, note TEXT,
  is_current INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS variation_line (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  variation_id INTEGER NOT NULL REFERENCES variation(id) ON DELETE CASCADE,
  section TEXT,
  node_id INTEGER REFERENCES cbs_node(id) ON DELETE SET NULL,
  category TEXT,
  description TEXT,
  role TEXT, unit TEXT,
  qty REAL DEFAULT 1, rate REAL DEFAULT 0,
  item_count REAL, hrs_day REAL, days_wk REAL, wks REAL,
  risk_pct REAL DEFAULT 0, markup_pct REAL DEFAULT 0,
  price_override REAL,
  optional INTEGER DEFAULT 0,
  sort_order INTEGER DEFAULT 0
);
-- price items of a variation (the client-facing price lines), grouped in sections; cost lines build them up
CREATE TABLE IF NOT EXISTS variation_price (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  variation_id INTEGER NOT NULL REFERENCES variation(id) ON DELETE CASCADE,
  seq INTEGER DEFAULT 0,
  section TEXT,                    -- e.g. Labour, Materials, Subcontractors, Overheads
  name TEXT,                       -- the price item as the client sees it
  pricing_type TEXT DEFAULT 'LS',  -- LS, PS (provisional), T&M, ...
  optional INTEGER DEFAULT 0,      -- offered as an option
  selected TEXT DEFAULT 'Pending', -- for an option: Pending | Yes | No (Yes counts in the value)
  detail TEXT,                     -- client detail for this item; blank = the variation's
  spread TEXT DEFAULT 'none',      -- none | uniform | proportional: spread this item's price over the carriers
  spread_scope TEXT DEFAULT 'all', -- all | section: carriers in every section or only this item's section
  carries INTEGER DEFAULT 1,       -- receives other items' spread
  note TEXT
);
CREATE TABLE IF NOT EXISTS variation_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  variation_id INTEGER NOT NULL REFERENCES variation(id) ON DELETE CASCADE,
  date TEXT, kind TEXT, text TEXT, who TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

-- Subcontracts ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subcontract (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  name TEXT NOT NULL, supplier_code TEXT, po_no TEXT,
  supplier_name TEXT,               -- the supplier as named before Pronto has it (matched later on Diagnostics)
  node_id INTEGER REFERENCES cbs_node(id) ON DELETE SET NULL,
  contract_value REAL DEFAULT 0,
  retention_pct REAL DEFAULT 0,
  retention_release_month TEXT,
  status TEXT DEFAULT 'active',
  notes TEXT
);
CREATE TABLE IF NOT EXISTS sub_milestone (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subcontract_id INTEGER NOT NULL REFERENCES subcontract(id) ON DELETE CASCADE,
  seq INTEGER, name TEXT,
  type TEXT DEFAULT 'Milestone',      -- Milestone | Progress | Price | Variation (Price: a price-table item, claimed x the progress share)
  pct REAL DEFAULT 0, value REAL DEFAULT 0,
  start_month TEXT, end_month TEXT,    -- Milestone: lands in start_month; Progress: even across the window
  trigger_note TEXT
);
CREATE TABLE IF NOT EXISTS sub_claim (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subcontract_id INTEGER NOT NULL REFERENCES subcontract(id) ON DELETE CASCADE,
  claim_no TEXT, month TEXT NOT NULL,
  gross REAL DEFAULT 0, retention REAL DEFAULT 0,   -- cached effective totals (approved where available, else claimed)
  retention_release REAL DEFAULT 0,
  status TEXT DEFAULT 'received',      -- draft | received | approved | paid
  received_date TEXT, approved_date TEXT, paid_date TEXT,
  inv_ref TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS sub_claim_line (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id INTEGER NOT NULL REFERENCES sub_claim(id) ON DELETE CASCADE,
  item_id INTEGER NOT NULL REFERENCES sub_milestone(id) ON DELETE CASCADE,
  claimed REAL DEFAULT 0,              -- what the subcontractor claims this month
  approved REAL,                       -- what EPEC approves; NULL until reviewed
  note TEXT,
  UNIQUE (claim_id, item_id)
);

-- Programme ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS milestone (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  phase TEXT, name TEXT NOT NULL, type TEXT DEFAULT 'Milestone',
  baseline_start TEXT, baseline_end TEXT,
  forecast_start TEXT, forecast_end TEXT,
  actual_date TEXT, pct REAL DEFAULT 0,
  pmr_row TEXT, note TEXT, sort_order INTEGER DEFAULT 0
);

-- History / reconciliation -------------------------------------------------
CREATE TABLE IF NOT EXISTS snapshot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  period TEXT, label TEXT, kind TEXT DEFAULT 'eom',
  status_date TEXT, created_at TEXT DEFAULT (datetime('now')),
  summary_json TEXT, curve_json TEXT
);
CREATE TABLE IF NOT EXISTS snapshot_line (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id INTEGER NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
  node_ref TEXT, code TEXT, name TEXT, level INTEGER, gp TEXT,
  budget REAL, risk REAL, allowance REAL, ctd REAL, acc REAL, ctc REAL, eac REAL,
  months_json TEXT                      -- cost by month (actual + accrual + forecast) as it stood in that snapshot
);
CREATE TABLE IF NOT EXISTS cmt_entry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  as_of TEXT, revenue REAL, eac REAL, ctd REAL, note TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER, at TEXT DEFAULT (datetime('now')),
  action TEXT, detail TEXT
);

-- Optional programme (MS Project XML, Excel/CSV export or PDF) used to seed dates ------------------
CREATE TABLE IF NOT EXISTS programme_task (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  source TEXT, seq INTEGER,
  wbs TEXT, name TEXT NOT NULL,
  start_date TEXT, finish_date TEXT,
  pct REAL DEFAULT 0, outline INTEGER DEFAULT 1, summary INTEGER DEFAULT 0, milestone INTEGER DEFAULT 0,
  link_item_id INTEGER REFERENCES contract_item(id) ON DELETE SET NULL,
  link_node_id INTEGER REFERENCES cbs_node(id) ON DELETE SET NULL
);

-- What drives a CBS line's activity window: its Start and/or Stop follow a schedule task (its start or finish date, a milestone has one date).
-- suspended = the user typed over it; the link is kept so "Return to schedule" can restore it.
CREATE TABLE IF NOT EXISTS window_link (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  node_id INTEGER NOT NULL REFERENCES cbs_node(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('start','stop')),
  task_id INTEGER NOT NULL REFERENCES programme_task(id) ON DELETE CASCADE,
  edge TEXT NOT NULL DEFAULT 'start' CHECK (edge IN ('start','finish')),
  suspended INTEGER NOT NULL DEFAULT 0,
  UNIQUE (node_id, role)
);

-- Risk register, buckets, cost tagging and General Manager releases ---------------------------------
CREATE TABLE IF NOT EXISTS risk (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  ref TEXT NOT NULL, title TEXT NOT NULL, description TEXT, cause TEXT, owner TEXT,
  status TEXT DEFAULT 'open',          -- open | materialised | ceased
  kind TEXT DEFAULT 'Risk',            -- Risk | Opportunity
  category TEXT, area TEXT, consequences TEXT, basis TEXT, trigger_event TEXT, controls TEXT,
  treatment TEXT,                      -- Mitigate | Avoid | Accept | Preventative | Transfer
  estimate REAL DEFAULT 0,             -- unmitigated cost if it happens
  likelihood REAL DEFAULT 0,           -- 0 to 1
  control_cost REAL DEFAULT 0,
  effectiveness REAL DEFAULT 0,        -- 0 to 1: how much the treatment removes
  last_reviewed TEXT, retire_date TEXT, comment TEXT,
  raised_date TEXT, note TEXT,
  delay_days REAL DEFAULT 0,           -- time impact if it happens (calendar days of delay)
  delay_actual REAL DEFAULT 0,         -- delay that has actually occurred
  revenue_impact REAL DEFAULT 0,       -- revenue lost or deferred if it happens (positive = loss)
  revenue_actual REAL DEFAULT 0,       -- revenue actually lost or deferred
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE (project_id, ref)
);
CREATE TABLE IF NOT EXISTS risk_alloc (        -- how a CBS item's risk bucket is broken down by risk subject
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  risk_id INTEGER NOT NULL REFERENCES risk(id) ON DELETE CASCADE,
  node_id INTEGER NOT NULL REFERENCES cbs_node(id) ON DELETE CASCADE,
  amount REAL NOT NULL DEFAULT 0,
  UNIQUE (risk_id, node_id)
);
CREATE TABLE IF NOT EXISTS risk_tag (          -- a Pronto transaction (by stable row key) whose cost landed because of a risk
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  risk_id INTEGER NOT NULL REFERENCES risk(id) ON DELETE CASCADE,
  row_hash TEXT NOT NULL,
  amount REAL,                                  -- NULL = the whole transaction
  note TEXT, created_at TEXT DEFAULT (datetime('now')),
  UNIQUE (project_id, row_hash, risk_id)
);
CREATE TABLE IF NOT EXISTS risk_release (      -- General Manager releases risk into budget
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  source_node_id INTEGER REFERENCES cbs_node(id) ON DELETE SET NULL,
  target_node_id INTEGER NOT NULL REFERENCES cbs_node(id) ON DELETE CASCADE,
  amount REAL NOT NULL, date TEXT, approved_by TEXT, ref TEXT, note TEXT,
  kind TEXT DEFAULT 'release',         -- contingency (PM transfer) | release (from the company bucket) | infuse (new company funds)
  forced INTEGER DEFAULT 0,
  pair_id TEXT, created_at TEXT DEFAULT (datetime('now'))
);

-- Forecast detail: day grids, payment milestones, supplier rates, public holidays ---------------------------
-- No UNIQUE keys on these: two people may fill the same cell on their own copies; the newest row (highest id) wins.
CREATE TABLE IF NOT EXISTS forecast_day (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  item_id INTEGER NOT NULL REFERENCES forecast_item(id) ON DELETE CASCADE,
  day TEXT NOT NULL,                   -- ISO date
  qty REAL                             -- hours, units or dollars per the item's basis
);
CREATE INDEX IF NOT EXISTS ix_fday ON forecast_day(item_id, day);

CREATE TABLE IF NOT EXISTS forecast_ms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  item_id INTEGER NOT NULL REFERENCES forecast_item(id) ON DELETE CASCADE,
  seq INTEGER DEFAULT 0,
  name TEXT,                           -- e.g. On order, Drawing submission, FAT, Delivery
  pct REAL DEFAULT 0,                  -- share of the item value (0.10 = 10%)
  month TEXT,                          -- scheduled month the supplier reaches it (YYYY-MM)
  status TEXT DEFAULT 'forecast',      -- forecast | reached | invoiced (invoiced is in actuals, not forecast)
  note TEXT
);
CREATE INDEX IF NOT EXISTS ix_fms ON forecast_ms(item_id);

CREATE TABLE IF NOT EXISTS supplier_rate (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  resource_id INTEGER REFERENCES resource(id) ON DELETE CASCADE,
  role TEXT NOT NULL,                  -- Electrician, Foreman, Trade assistant...
  unit TEXT DEFAULT 'hr',              -- hr | day | shift | ea
  rate REAL DEFAULT 0,                 -- normal time
  ot_rate REAL,                        -- overtime rate per hour beyond nt_hours a day
  nt_hours REAL,                       -- normal hours a day before overtime
  allowance REAL,                      -- per person per day worked (LAHA, meals, travel)
  ref TEXT, valid_from TEXT, note TEXT
);

CREATE TABLE IF NOT EXISTS holiday (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  day TEXT NOT NULL, name TEXT
);

-- Lump-sum subcontracts: the PM's forecast of future claims per schedule line per month (gross, before retention) --------
CREATE TABLE IF NOT EXISTS sub_forecast (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  subcontract_id INTEGER NOT NULL REFERENCES subcontract(id) ON DELETE CASCADE,
  item_id INTEGER NOT NULL REFERENCES sub_milestone(id) ON DELETE CASCADE,
  month TEXT NOT NULL,
  amount REAL
);
CREATE INDEX IF NOT EXISTS ix_subfc ON sub_forecast(subcontract_id, item_id, month);

-- Schedule-of-rates subcontractors: their timesheets, uploaded from the template ------------------------------
-- the subcontractor's own planned claims (claimable $) per schedule line and month, from their payment schedule
CREATE TABLE IF NOT EXISTS sub_plan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  subcontract_id INTEGER NOT NULL REFERENCES subcontract(id) ON DELETE CASCADE,
  item_id INTEGER NOT NULL REFERENCES sub_milestone(id) ON DELETE CASCADE,
  month TEXT NOT NULL,
  amount REAL
);
CREATE TABLE IF NOT EXISTS sub_timesheet (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  batch TEXT,                          -- upload it came from (file name and time)
  resource_id INTEGER REFERENCES resource(id) ON DELETE CASCADE,   -- the supplier
  role TEXT, worker TEXT,
  day TEXT NOT NULL, hours REAL NOT NULL,
  node_id INTEGER REFERENCES cbs_node(id) ON DELETE SET NULL,
  docket TEXT, note TEXT,
  row_hash TEXT
);
CREATE INDEX IF NOT EXISTS ix_subts ON sub_timesheet(project_id, resource_id, day);

-- Month-end review: the decision taken per CBS line per month (who and when come from the change log) ---------
CREATE TABLE IF NOT EXISTS month_review (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  node_ref TEXT NOT NULL,              -- CBS line id, or p<group id> for an (Unallocated) pool
  month TEXT NOT NULL,
  decision TEXT,                       -- see review.DECISIONS
  note TEXT
);

-- actions already reverted (revert.py): the next Revert takes the action before them
CREATE TABLE IF NOT EXISTS revert_mark (txn TEXT PRIMARY KEY, project_id INTEGER, rev_id INTEGER);

-- Change log: who changed what and when (written by triggers, see changelog.py) -----------------------------
CREATE TABLE IF NOT EXISTS change_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT UNIQUE,                     -- global id once published (<writer>:<n>); NULL until then
  ts INTEGER NOT NULL,                 -- hybrid clock, microseconds
  at TEXT,                             -- ISO UTC
  user_upn TEXT, user_name TEXT,
  via TEXT,                            -- set when the app changed it by itself (e.g. automatic accrual reversal)
  txn TEXT,                            -- one user action (HTTP request) groups its changes
  project_id INTEGER,
  tbl TEXT NOT NULL, row_id INTEGER NOT NULL,
  op TEXT NOT NULL,                    -- I | U | D
  data TEXT,                           -- I: new row; U: {col: [old, new]}; D: old row
  remote INTEGER DEFAULT 0,            -- 1 = received from another user's journal
  writer TEXT
);
CREATE INDEX IF NOT EXISTS ix_cl_row ON change_log(tbl, row_id, ts);
CREATE INDEX IF NOT EXISTS ix_cl_proj ON change_log(project_id, id);
CREATE INDEX IF NOT EXISTS ix_cl_pending ON change_log(remote, uid);

CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sync_file (path TEXT PRIMARY KEY, offset INTEGER DEFAULT 0, size INTEGER DEFAULT 0);

-- Company-wide records (not per project): the client CRM and the people who run projects -----------------------
CREATE TABLE IF NOT EXISTS client (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,                  -- matches project.client_name (case and spaces ignored)
  sector TEXT,                         -- e.g. Developer, Utility / network, IPP, Government, Mining
  abn TEXT, website TEXT, hq TEXT,
  contacts TEXT,                       -- key people, one per line: name · role · email · phone
  risk TEXT,                           -- Low | Medium | High (commercial / payment / dispute risk)
  complexity INTEGER,                  -- difficulty: 1 easy .. 5 difficult to work with (the grid's Y axis)
  knowledge INTEGER,                   -- 1 clueless .. 5 expert (the grid's X axis)
  payment_terms TEXT,
  relationship TEXT,                   -- how the relationship stands, what matters to them
  notes TEXT
);
-- company-wide directory of the organisations EPEC buys from (directory.py): suppliers, subcontractors, consultants
CREATE TABLE IF NOT EXISTS company (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL DEFAULT 'supplier',   -- supplier | subcontractor | consultant
  name TEXT NOT NULL,                  -- matched to project resources / subcontracts by name (case and spaces ignored)
  code TEXT,                           -- Pronto supplier code
  abn TEXT, trade TEXT,                -- what they do: electrical, civil, HV testing, design...
  contacts TEXT, email TEXT, phone TEXT, address TEXT,
  notes TEXT,
  active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS person (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,                  -- matches project.epec_pm / project_director
  role TEXT,                           -- Project Manager | Project Director | ...
  pm_level INTEGER,                    -- EPEC-PM-FW-0002 PM Level 1..4 (4 = portfolio / director)
  fte REAL DEFAULT 1,                  -- time available for project management (1 = full time)
  base TEXT, lat REAL, lon REAL,       -- home office, for travel to sites
  reports_to TEXT,                     -- their project director
  email TEXT, notes TEXT,
  active INTEGER DEFAULT 1
);

-- what an Excel load is about to change, kept so it can be undone (Project setup > Undo last Excel load)
CREATE TABLE IF NOT EXISTS restore_point (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  label TEXT, data TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')), created_by TEXT,
  undone_at TEXT
);

-- EPEC PMs' monthly read on the client's PM and the project's complexity through the project's life (challenge.py)
CREATE TABLE IF NOT EXISTS assessment (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  month TEXT NOT NULL,                 -- YYYY-MM
  client_pm TEXT,                      -- the client's project manager this month
  pm_difficulty INTEGER,               -- 1 easy .. 5 difficult
  complexity INTEGER,                  -- the project's complexity this month, 1 simple .. 5 very complex
  note TEXT, by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (project_id, month)
);

-- the project director's complexity score (complexity.py): ten dimensions 0 to 5; every revision is kept and the latest is current
CREATE TABLE IF NOT EXISTS cx_baseline (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  scores_json TEXT NOT NULL,           -- { dimension: { score, note } }
  total INTEGER, band TEXT, summary TEXT,
  by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- competency levels of people by role (team.py): 1 to 4, read like the Project Resourcing Requirement table; the PM level stays on person.pm_level (1 to 5)
CREATE TABLE IF NOT EXISTS person_role (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  role_key TEXT NOT NULL,              -- pe | dm | cm | tc | ct | co
  level INTEGER NOT NULL,
  UNIQUE (person_id, role_key)
);

-- who fills which role on a project (team.py); the PM and the director are the project's own fields
CREATE TABLE IF NOT EXISTS team_slot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  role_key TEXT NOT NULL,
  person_id INTEGER REFERENCES person(id) ON DELETE SET NULL,
  status TEXT DEFAULT 'selected',      -- selected | recruitment | tbc
  start_date TEXT, end_date TEXT,      -- in post from / until (a leaver has an end date)
  note TEXT
);

-- the EPEC Classification Framework as reference data (ecf.py): seeded from the published framework, editable when HR revises it
CREATE TABLE IF NOT EXISTS ecf_role (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role_key TEXT NOT NULL UNIQUE,
  family TEXT NOT NULL, name TEXT NOT NULL,
  level_from INTEGER, level_to INTEGER,       -- a role can span two levels (Design Manager 6 to 7)
  titles_json TEXT, profile_json TEXT, sort_order INTEGER DEFAULT 0
);

-- HR's revisions to a framework role (ecf.py): kept apart from the seeded ecf_role so they are logged and shared like other changes
CREATE TABLE IF NOT EXISTS ecf_edit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role_key TEXT NOT NULL UNIQUE,
  level_from INTEGER, level_to INTEGER, titles_json TEXT
);

-- a person's level (1 to 5, PM capability) per complexity dimension (team.py); unset = their overall PM level
CREATE TABLE IF NOT EXISTS person_dimension (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  dim_key TEXT NOT NULL,
  level INTEGER NOT NULL,
  UNIQUE (person_id, dim_key)
);

-- the PM confirms the team each month (team.py): the rating at that moment is kept with the note
CREATE TABLE IF NOT EXISTS team_review (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  month TEXT NOT NULL,
  rating TEXT, note TEXT, by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (project_id, month)
);

-- where the project stands on EPEC's gates 1 to 7 (gates.py): every change kept, the latest is current; a gate can move back (Early Works, then EPC)
CREATE TABLE IF NOT EXISTS gate_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  gate INTEGER NOT NULL,
  date TEXT NOT NULL,                  -- the day the project reached this gate
  stage TEXT,                          -- Whole project | Early Works | EPC
  note TEXT, by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_gate_log ON gate_log(project_id, date);

-- the delivery stage the PM says the project is in (Design, Procure, Construct, Commission, Close Out); each change kept, the latest is current (gates.py)
CREATE TABLE IF NOT EXISTS phase_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  phase TEXT NOT NULL,
  date TEXT NOT NULL,
  note TEXT, by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_phase_log ON phase_log(project_id, date);

-- the lifecycle stage the PM says the project is in (Handover, Setup, Delivery, Close Out, Warranty), with when it started and ended; the latest start is current
CREATE TABLE IF NOT EXISTS lifecycle_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  date TEXT NOT NULL,
  end_date TEXT,
  note TEXT, by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_lifecycle_log ON lifecycle_log(project_id, date);

-- every correction or deletion of a ledger entry: who, when, what it was, what it became and the reason the user gave
CREATE TABLE IF NOT EXISTS ledger_edit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  ledger_id INTEGER NOT NULL,
  node_code TEXT, action TEXT NOT NULL,            -- edit | delete
  old_json TEXT, new_json TEXT, reason TEXT NOT NULL,
  by TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_ledger_edit ON ledger_edit(project_id, ledger_id);

-- the project's parties and the lines between them (orgchart.py): one JSON document per project
CREATE TABLE IF NOT EXISTS project_org (
  project_id INTEGER PRIMARY KEY REFERENCES project(id) ON DELETE CASCADE,
  data TEXT NOT NULL, updated_by TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Project Library (PMO): knowledge documents (checklists, procedures, forms) kept in the database so they travel with it ----
CREATE TABLE IF NOT EXISTS kb_doc (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL, doc_type TEXT, phase TEXT, gate INTEGER, project_type TEXT, description TEXT,
  filename TEXT, mime TEXT, size INTEGER, data TEXT,   -- base64: the sharing triggers cannot hold BLOBs
  uploaded_by TEXT, uploaded_at TEXT
);

-- Project stakeholders (COMMUNICATION): the people and organisations that matter to this one project ----
CREATE TABLE IF NOT EXISTS project_stakeholder (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  name TEXT NOT NULL, organisation TEXT, role TEXT, contact TEXT,
  interest TEXT, influence TEXT,        -- High / Medium / Low
  notes TEXT, source TEXT               -- source: manual | org chart | project team
);

-- The schedule file as uploaded (MS Project, Excel, PDF), kept so it can be downloaded again; base64 because the sharing triggers cannot hold BLOBs ----
CREATE TABLE IF NOT EXISTS programme_file (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  layer TEXT NOT NULL DEFAULT 'internal',
  filename TEXT, mime TEXT, size INTEGER, data TEXT, uploaded_by TEXT, uploaded_at TEXT
);

-- A person's own settings that follow them between PCs (menu order and open groups), keyed by their sign-in name ----
CREATE TABLE IF NOT EXISTS user_setting (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  upn TEXT NOT NULL, key TEXT NOT NULL, value TEXT,
  UNIQUE (upn, key)
);
