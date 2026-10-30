import { h } from '../ui.js';
import { eomTab } from './reports.js';

// REPORTING > EOM report: the end-of-month cost and revenue report to finance (app/eom_report.py), as Excel or PDF.
export default async function eom(root, params) {
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'EOM report'),
    h('div', { class: 'sub' }, 'End of month cost and revenue report to finance: cost to date, accruals, forecast and EAC by category, revenue and cash flow. Download it as Excel or PDF.'))));
  const body = h('div'); root.append(body);
  await eomTab(body, params);
}
