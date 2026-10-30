import { h, fmt } from '../ui.js';
import { api, p } from '../api.js';
import { go } from '../app.js';
import { radar } from './complexity.js';
import { pmrTab } from './reports.js';
import { reportPlan } from './_reportplan.js';

// REPORTING > PMR: the Project Management Report to EPEC's internal board, every month. Placeholder: the layout is to
// be agreed; the commercial block (the PMR output PMT already calculates) is below it.
export default async function pmr(root) {
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'PMR: Project Management Report'),
    h('div', { class: 'sub' }, 'Monthly report to the internal board. The commercial figures are live; the other sections are the proposed layout and are not built yet.'))));
  // the PM's own complexity and client assessments, month by month (the director's baseline is not shown here)
  const cx = await api.get(p('/complexity')).catch(() => null);
  if (cx) {
    const rows = cx.assessments.filter((x) => x.total != null);
    root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Project complexity and client difficulty'), h('span', { class: 'sp' }), h('a', { onclick: () => go('complexity', { tab: 'monthly' }) }, rows.length ? 'Update this month' : 'Add the first assessment')),
      rows.length ? h('div', { style: { height: '360px', maxWidth: '620px', margin: '0 auto 10px' } }) : null,
      rows.length ? h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Month', 'Complexity (0 to 50)', 'Band', 'Client difficulty (1 to 5)', 'Note'].map((x) => h('th', {}, x)))),
        h('tbody', {}, rows.slice(-6).reverse().map((x) => h('tr', {}, h('td', {}, fmt.month(x.month)), h('td', { class: 'r' }, String(x.total)), h('td', {}, x.band || ''), h('td', { class: 'r' }, x.pm_difficulty ? String(x.pm_difficulty) : ''), h('td', { class: 'small wrap' }, x.note || '')))))) : h('div', { class: 'muted' }, 'No assessment yet. Score the ten dimensions on Project complexity.')));
  }
  const rbox = root.querySelector('.card div[style*="360px"]'); const lastRow = cx && [...cx.assessments].reverse().find((x) => x.scores && Object.keys(x.scores).length);
  if (rbox && lastRow) setTimeout(() => radar(rbox, cx.dimensions, [{ label: `${fmt.month(lastRow.month)} (${lastRow.total})`, scores: lastRow.scores, colour: '#102361' }]), 30);
  root.append(reportPlan({
    title: 'Project Management Report (internal board)', audience: 'EPEC internal board, general manager', when: 'Monthly, after the month-end close',
    purpose: 'Where the project stands commercially and on delivery, what is at risk, what the board needs to decide',
    sections: [
      ['Executive summary', 'Status in a few lines, traffic lights for cost, time, safety, quality, client', '', ''],
      ['Safety (HSE)', 'Incidents, lead and lag indicators, observations', '', ''],
      ['Project schedule', 'Key milestones, baseline against forecast, critical path, delays', 'Project schedule', '#/programme'],
      ['Commercial', 'Contract value, cost to date, EAC, margin at tender and forecast, erosion', 'PMR output (below)', ''],
      ['Cash flow', 'Claimed, certified and paid against cost landed, by month', 'EOM report', '#/eom'],
      ['Variations', 'Approved, pending and in discussion, with value and exposure', 'Variations', '#/variations'],
      ['Risks and opportunities', 'Top risks, contingency held and drawn, opportunities', 'Allowances', '#/risk'],
      ['Subcontractors and procurement', 'Subcontract claims, open POs, key procurement status', 'Subcontracts / Commitments', '#/subcontracts'],
      ['Resourcing', 'Labour forecast, PM workload', 'Labour calendar', '#/calendar'],
      ['Decisions and look-ahead', 'What the board is asked to decide; next month', '', ''],
    ],
    note: 'Tell Claude which sections, order and charts the board wants (or share an existing PMR) and this becomes the report, with an Excel / PDF download like the EOM report.',
  }));
  root.append(h('h2', { style: { margin: '18px 0 10px' } }, 'Commercial block (live)'));
  const body = h('div'); root.append(body);
  await pmrTab(body);
}
