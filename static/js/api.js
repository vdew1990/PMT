// Thin fetch wrapper plus app-wide state. Everything project-scoped goes through p().

export const state = {
  projects: [], pid: null, project: null, tax: null,
  scope: { node: null, from: null, to: null },      // the dashboard / cost-control CBS scope
  rows: null, rowsKey: null,                          // cached cost-control rows (no month arrays)
  version: 0,
};

async function call(method, url, body) {
  if (method !== 'GET' && api.beforeWrite) await api.beforeWrite(method, url);   // the Project setup draft hook (app.js)
  const opts = { method, headers: {} };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch (e) { /* ignore */ }
    throw new Error(msg);
  }
  if (method !== 'GET' && api.afterWrite) api.afterWrite(method, url);   // the Revert button in the top bar (app.js)
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r;
}

export const api = {
  beforeWrite: null, afterWrite: null,
  get: (u) => call('GET', u), post: (u, b) => call('POST', u, b ?? {}), put: (u, b) => call('PUT', u, b ?? {}), del: (u) => call('DELETE', u),
  upload: (u, file, extra = {}) => { const fd = new FormData(); fd.append('file', file); Object.entries(extra).forEach(([k, v]) => fd.append(k, v)); return call('POST', u, fd); },
};

export const p = (path = '') => `/api/p/${state.pid}${path}`;

// Cost-control rows without the month arrays: cheap enough to fetch whenever something changed.
export async function loadRows(force = false) {
  const res = await api.get(p('/cost-control?months=0'));
  state.rows = res;
  return res;
}
export async function loadProject() {
  state.project = await api.get(`/api/projects/${state.pid}`);
  return state.project;
}
export async function loadProjects() { state.projects = await api.get('/api/projects'); return state.projects; }

export const saveLocal = () => {
  try { localStorage.setItem('pmt', JSON.stringify({ pid: state.pid, scope: state.scope })); } catch (e) { /* storage may be blocked */ }
};
export const loadLocal = () => {
  try { return JSON.parse(localStorage.getItem('pmt') || '{}'); } catch (e) { return {}; }
};

export const isCompany = () => (state.project?.settings?.allowance_view || 'pm') === 'company';

// This person's view defaults (Settings > Your defaults): how each page opens. A page keeps what you change while
// you work (for the session); a new session starts from these.
export const PREFS = [
  // [key, label, kind, default, options, page]
  ['start_page', 'Page PMT opens on', 'select', 'dashboard', [['dashboard', 'Dashboard'], ['portfolio', 'Portfolio'], ['costcontrol', 'Cost control'], ['forecast', 'Forecast lines'], ['calendar', 'Labour calendar'], ['review', 'Month-end review'], ['diagnostics', 'Diagnostics']], 'General'],
  ['table_filters', 'Show the filter row under table headings', 'bool', false, null, 'General'],
  ['cc_level', 'Expand to level', 'select', 2, [[1, 'Level 1'], [2, 'Level 2'], [3, 'Level 3'], [4, 'Level 4'], [5, 'Level 5']], 'Cost control'],
  ['cc_months', 'Show the monthly grid', 'bool', false, null, 'Cost control'],
  ['cc_hide_zero', 'Hide empty lines', 'bool', true, null, 'Cost control'],
  ['cc_only', 'Show', 'select', '', [['', 'All lines'], ['over', 'Overruns'], ['under', 'Underruns'], ['short', 'CTC below PO'], ['nomethod', 'Nothing to forecast from']], 'Cost control'],
  ['cbs_level', 'Expand to level', 'select', 0, [[0, 'As last left'], [1, 'Level 1'], [2, 'Level 2'], [3, 'Level 3'], [4, 'Level 4'], [5, 'Level 5']], 'CBS and allowances'],
  ['rev_level', 'Contract value and claim schedule: expand to level', 'select', 0, [[0, 'Everything open'], [1, 'Level 1'], [2, 'Level 2'], [3, 'Level 3'], [4, 'Level 4'], [5, 'Level 5']], 'Contract and claims'],
  ['cal_weeks', 'Weeks shown', 'select', 6, [[2, '2 weeks'], [4, '4 weeks'], [6, '6 weeks'], [9, '9 weeks'], [13, '13 weeks']], 'Labour calendar'],
  ['cal_project', 'Open on "Whole project by month"', 'bool', false, null, 'Labour calendar'],
  ['cal_kind', 'Show', 'select', '', [['', 'Everyone'], ['employee', 'Employees'], ['supplier', 'Suppliers']], 'Labour calendar'],
  ['cal_pools_shut', 'Unassigned pools collapsed', 'bool', false, null, 'Labour calendar'],
  ['review_only', 'Show', 'select', 'diff', [['diff', 'Plan and landed differ'], ['open', 'Not reviewed yet'], ['all', 'All lines']], 'Month-end review'],
  ['po_open_only', 'Open POs only', 'bool', true, null, 'Commitments'],
  ['copilot_url', 'Microsoft Copilot Chat address', 'text', 'https://m365.cloud.microsoft/chat', null, 'Help and Copilot'],
  ['copilot_embed', 'Copilot Studio agent web chat address (optional, from IT)', 'text', '', null, 'Help and Copilot'],
  ['flow_tab', 'Revenue against cost: first tab', 'select', 'work', [['work', 'Value of work'], ['invoices', 'Invoiced vs bills'], ['cash', 'Cash']], 'Dashboard'],
];
export function pref(key) {
  const v = state.me?.prefs?.[key];
  if (v !== undefined && v !== null) return v;
  const d = PREFS.find((x) => x[0] === key);
  return d ? d[3] : undefined;
}
// session keys the pages keep their current view in; cleared when the defaults change so they take effect
export const VIEW_KEYS = ['ccui', 'cbsLvl', 'cbsExp', 'revLvl', 'revExp', 'calui', 'revui', 'flowTab', 'poOpen'];

// the status month (YYYY-MM): from the loaded cost control rows, else from the project's status date (a page opened directly has no rows yet)
export const statusMonth = () => state.rows?.status_month || String(state.project?.status_date || '').slice(0, 7);
