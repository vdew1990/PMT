// Every tile (.kpi) in PMT opens the data behind it: another page, or the table on the same page that holds the figures.
// One map per page, matched on the tile's label, so the links live in one place. Tiles that are live totals of an
// editor (claim entry, variation pricing, a day's detail) have nowhere else to go and are left as they are.
import { jumpTo, toCard } from './ui.js';
import { route, render } from './app.js';

// the contract value tiles: open the payment milestones in a window of their own, showing only that part, to add,
// change or delete; this page refreshes when that window is closed
const openContract = (only) => () => {
  if (document.body.classList.contains('popout')) { location.hash = `#/revenue?tab=contract${only ? '&only=' + only : ''}`; return; }
  const w = window.open(`${location.pathname}?popout=1#/revenue?tab=contract${only ? '&only=' + only : ''}`, '_blank', 'popup=yes,width=1400,height=900');
  if (!w) { location.hash = `#/revenue?tab=contract${only ? '&only=' + only : ''}`; return; }
  const t = setInterval(() => { if (w.closed) { clearInterval(t); render(); } }, 800);
};
const CONTRACT_TILES = {
  'Original contract': [openContract('original'), 'Open what is in the original contract value, in its own window'],
  'Optional prices': [openContract('optional'), 'Open the optional prices, in their own window'],
  Variations: [openContract('variation'), 'Open the variations, in their own window'],
  'Recognised revenue': [openContract(null), 'Open all payment milestones, in their own window'],
  'Official value': [openContract(null), 'Open all payment milestones, in their own window'],
  Stages: [openContract(null), 'Open all payment milestones, in their own window'],
};

// A target is a page ('#/accruals'), or a function called on click with (tile, line) that either returns a page or
// does the jump itself (scroll to a card or table on the same page).
// scroll to the first table below the tiles, in the same page or drawer (lists whose tiles summarise the table itself)
const toTable = () => (el) => {
  const scope = el?.closest('.drawer, .ov') || document.getElementById('view');
  const t = scope.querySelector('.tw, table.t');
  if (!t) return;
  t.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const c = t.closest('.card') || t; c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash');
};
// click a chip / tab on this page by its text (e.g. a filter), then scroll to the table
const chip = (text) => () => { const c = [...document.querySelectorAll('#view .chip, #view .tab')].find((e) => e.textContent.trim() === text); if (c && !c.classList.contains('on')) c.click(); setTimeout(toTable(), 150); };
// in the cost control drawer and on a forecast line: the CBS line the tiles belong to
const ctx = (el) => el.closest('[data-node]')?.dataset || {};
// scroll to the card whose heading contains `text`
const toCardHas = (text) => () => {
  const c = [...document.querySelectorAll('#view .card')].find((e) => (e.querySelector('h2')?.textContent || '').includes(text));
  if (c) { c.scrollIntoView({ behavior: 'smooth', block: 'start' }); c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash'); }
};
// the forecast / actuals / accruals history pages: their tile labels carry the month or close they are about
const HISTORY = {
  '^EAC': ['#/costcontrol', 'Open cost control'], '^Closes$': [toCardHas('at each close'), 'Show each close'],
  '^Method changes$': [toCardHas('Per line'), 'Show the lines'], ' in [A-Z][a-z]{2}-\\d{2}$': [toCardHas('at each close'), 'Show each close'],
  '*': [toCardHas('Per line'), 'Show the lines'],
};

const T = {
  costcontrolDrawer: {
    Allowance: ['#/cbs?tab=ledger', 'Open the allowance movements'],
    CTD: [(el, d) => `#/actuals?node=${d.node}`, 'Open the actuals for this line'],
    Accruals: ['#/accruals', 'Open the accruals'],
    CTC: [(el, d) => `#/forecast?node=${d.row}`, 'Open the forecast for this line'],
    EAC: [(el, d) => `#/forecast?node=${d.row}`, 'Open the forecast for this line'],
    Contingency: [(el) => drawerCard(el, 'Budget build-up'), 'Show the budget build-up'],
  },
  forecastLine: {
    Allowance: [(el, d) => `#/costcontrol?open=${d.row}`, 'Open the line in cost control (budget build-up)'],
    'Cost to date': [(el, d) => `#/actuals?node=${d.node}`, 'Open the actuals for this line'],
    Accruals: ['#/accruals', 'Open the accruals'],
    'Cost to complete': [toCard('Forecast items', 'Typed months', 'Monthly forecast', 'Forecast method'), 'Show how the cost to complete is forecast'],
    EAC: [toCard('Monthly profile'), 'Show the monthly profile'],
    Contingency: [(el, d) => `#/costcontrol?open=${d.row}`, 'Open the line in cost control'],
  },
  forecast: {
    'Cost to complete': ['#/costcontrol', 'Open cost control'], EAC: ['#/costcontrol', 'Open cost control'], Contingency: ['#/costcontrol', 'Open cost control'],
    'Built ground-up': ['#/forecast?method=GROUND-UP', 'Show the lines built ground-up'], 'Held at budget': ['#/forecast?method=AT-BUDGET', 'Show the lines held at budget'],
    'Forecast hours': ['#/calendar', 'Open the labour calendar'],
  },
  accruals: {
    'Your open accruals': [toCard('Your accruals'), 'Show your accruals'], 'Invoice differs: review': [toCard('Your accruals'), 'Show the accruals to review'],
    'Accrued by finance in Pronto': [toCard('Accrued by finance'), 'Show finance\'s accruals in Pronto'],
    'Unposted timesheets': [toCard('Unposted timesheets'), 'Show the unposted timesheets'], 'Subcontract claims': [toCard('Subcontract claims'), 'Show the subcontract claims'],
    '*': [toCard('Month by month'), 'Show month by month'],
  },
  cbs: {
    'Original budget': [chip('Structure and estimate'), 'Show the structure and estimate'], 'Original risk': ['#/risk?tab=buckets', 'Open the risk buckets by CBS'],
    'Contingency held': ['#/risk?tab=buckets', 'Open the risk buckets by CBS'], 'Approved variations': ['#/variations', 'Open the variation register'],
    'Current budget': ['#/cbs?tab=ledger', 'Open the allowance movements'], 'Current allowance': ['#/cbs?tab=ledger', 'Open the allowance movements'],
  },
  commitments: { '*': [toTable(), 'Show the purchase orders'] },
  subcontracts: { '*': [toTable(), 'Show the subcontracts'] },
  subDetail: { '*': [toTable(), 'Show the claims'] },
  variations: { Recognised: ['#/revenue?tab=contract', 'Open the contract value'], '*': [toTable(), 'Show the register'] },
  risk: {
    'Contingency held': ['#/risk?tab=buckets', 'Open the buckets by CBS'], 'Company risk bucket': ['#/risk?tab=buckets', 'Open the buckets by CBS'],
    'Risk cost occurred': ['#/risk?tab=tagging', 'Open the tagged costs'], 'Risk cover set aside': ['#/risk?tab=release', 'Open the funding entries'],
    'Still uncovered': ['#/risk?tab=release', 'Open funding risk costs'], 'Landed + accrued': ['#/risk?tab=tagging', 'Open the tagged costs'],
    Uncovered: ['#/risk?tab=release', 'Open funding risk costs'], 'Already covered': ['#/risk?tab=release', 'Open the funding entries'],
    '*': [toTable(), 'Show the detail'],
  },
  revenue: {
    ...CONTRACT_TILES,
    'Claims in this tool': [toCard('Progress claims'), 'Show the progress claims'], 'Pronto claims': [toCard('Pronto claims'), 'Show the Pronto claims'],
    'Pronto paid': [toCard('Pronto claims'), 'Show the Pronto claims'], Difference: ['#/diagnostics', 'Open Diagnostics'],
    'Claim items': [toTable(), 'Show the claim schedule'], 'With dates': ['#/programme', 'Open the project schedule'], 'With monthly amounts': [toTable(), 'Show the claim schedule'], 'Value by section': [toTable(), 'Show the claim schedule'],
  },
  review: {
    'Planned this month': [toTable(), 'Show the lines'], Actual: ['#/actuals', 'Open the actuals'], Accrued: ['#/accruals', 'Open the accruals'],
    'Landed vs plan': [chip('Plan and landed differ'), 'Show the lines that differ'], Planned: ['#/fhistory', 'Open the forecast history (the plan as it was)'], Difference: [chip('Plan and landed differ'), 'Show the lines that differ'], 'Still forecast this month': ['#/forecast', 'Open the forecast lines'], Reviewed: [chip('Not reviewed yet'), 'Show the lines not reviewed yet'],
  },
  programme: {
    'Claim items with dates': ['#/revenue?tab=schedule', 'Open the claim schedule'], 'CBS lines with their own dates': [toCard('2.'), 'Show the dates set by hand'],
    'Project schedule tasks loaded': [toCard('Project schedule tasks', '1. Upload'), 'Show the project schedule tasks'], 'Tasks linked': [toCard('Project schedule tasks', '1. Upload'), 'Show the project schedule tasks'],
  },
  setup: {
    ...CONTRACT_TILES,
    'Budget entered': ['#/cbs', 'Open the CBS and allowances'], Risk: ['#/risk?tab=buckets', 'Open the risk buckets'], Allowance: ['#/cbs', 'Open the CBS and allowances'],
    'CBS lines': ['#/cbs', 'Open the CBS'], Lines: ['#/cbs', 'Open the CBS'], 'Contract value': ['#/revenue?tab=contract', 'Open the contract value'],
    'Total allowance (budget + risk)': ['#/cbs', 'Open the CBS and allowances'], 'Planned margin': ['#/pmr', 'Open the PMR (board report)'],
  },
  reports: {
    'Cost to date': ['#/actuals', 'Open the actuals'], 'Cost to complete': ['#/forecast', 'Open the forecast lines'], EAC: ['#/costcontrol', 'Open cost control'],
    Allowance: ['#/cbs?tab=ledger', 'Open the allowance movements'], 'Forecast margin': ['#/pmr', 'Open the PMR (board report)'], 'Forecast profit': ['#/pmr', 'Open the PMR (board report)'],
  },
  actuals: HISTORY, fhistory: HISTORY,
  invoices: { Suppliers: [toCard('Suppliers'), 'Show the suppliers'], Invoices: [toCard('All invoices', 'Suppliers'), 'Show the invoices'], Invoiced: [toCard('All invoices', 'Suppliers'), 'Show the invoices'], '*': [toCard('Suppliers'), 'Show the suppliers'] },
  portfolio: { '*': [toCard('Projects', 'Clients', 'Workload by project manager'), 'Show the detail'] }, library: { '*': [toTable(), 'Show the projects'] },
  diagnostics: {
    'Do not tie': [() => firstCheck('#c62828'), 'Show the first check that does not tie'], 'To review or match': [() => firstCheck('#ffb500'), 'Show the first check to review'],
    'Checked and fine': [() => firstCheck('#3c8d40'), 'Show the checks that pass'],
  },
};

function drawerCard(el, title) {
  const c = [...el.closest('.drawer').querySelectorAll('.card')].find((e) => (e.querySelector('h2')?.textContent || '').startsWith(title));
  if (c) { c.scrollIntoView({ behavior: 'smooth', block: 'start' }); c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash'); }
}
function firstCheck(color) {
  const c = [...document.querySelectorAll('#view .card')].find((e) => e.style.borderLeft.includes(color) || getComputedStyle(e).borderLeftColor === hexRgb(color));
  if (c) { c.scrollIntoView({ behavior: 'smooth', block: 'start' }); c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash'); }
}
const hexRgb = (x) => { const n = parseInt(x.slice(1), 16); return `rgb(${n >> 16}, ${(n >> 8) & 255}, ${n & 255})`; };

function mapFor(el) {
  if (el.closest('.ov')) return null;                                 // dialogs: the tiles are the detail itself
  const { name, params } = route();
  if (el.closest('.drawer')) return el.closest('[data-node]') ? T.costcontrolDrawer : (name === 'subcontracts' ? T.subDetail : null);
  if (name === 'forecast' && params.node) return T.forecastLine;
  if (name === 'accruals' && params.tab === 'history') return HISTORY;
  if (name === 'actuals' && params.tab !== 'history' && !params.node) return T.invoices;
  return T[name] || null;
}

export function linkTile(el) {
  if (el.classList.contains('jump') || el.dataset.tl) return;
  el.dataset.tl = '1';
  const m = mapFor(el);
  if (!m) return;
  const label = (el.querySelector('.l')?.textContent || '').replace(/\s*→$/, '').trim();
  const hit = m[label] || Object.entries(m).find(([k]) => (k.startsWith('^') || k.startsWith(' ')) && new RegExp(k).test(label))?.[1] || m['*'];
  if (!hit) return;
  const [to, title] = hit;
  jumpTo(el, typeof to === 'string' ? to : () => { const r = to(el, ctx(el)); if (typeof r === 'string' && !r.includes('undefined')) location.hash = r; }, title);
}

export function watchTiles(root = document.body) {
  let t = null;
  const run = () => { t = null; root.querySelectorAll('.kpi:not([data-tl]):not(.jump)').forEach((k) => { try { linkTile(k); } catch (e) { console.error(e); } }); };
  new MutationObserver(() => { if (!t) t = setTimeout(run, 80); }).observe(root, { childList: true, subtree: true });
  run();
  return run;
}
