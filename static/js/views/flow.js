import { h } from '../ui.js';
import { go } from '../app.js';

// PMO > Workflow: a short, stage by stage summary from start to close-out, each stage ending in its next step.
// The full app guide is in the chat button and the Project library.
const STAGES = [
  ['1. Set up the project', [
    ['Project', 'setup?step=project', 'Identity, dates, client, contract law and review period.'],
    ['Contract value', 'setup?step=contract', 'Payment milestones: the contract money side.'],
    ['CBS and allowances', 'setup?step=cbs', 'Build the cost structure and load proposal allowances per group and line (see "Aligning allowances" below).'],
    ['Project schedule', 'setup?step=programme', 'Upload the internal and upstream schedules; dates then drive the forecast.'],
    ['Pronto data', 'setup?step=pronto', 'For a project already running: load the Pronto exports once.'],
    ['Allowance', 'setup?step=allowance', 'Link resources with cost to allowance buckets so the baseline is by line.'],
    ['Initialise', 'setup?step=initialise', 'Checks first, then locks the original estimate. From here, allowance only moves by transfer.']],
    'Next: initialise, then load the first Pronto exports.'],
  ['2. Each month', [
    ['Pronto data', 'pronto', 'Upload the new exports. Every cost row lands on a CBS line; new resources are offered as new lines.'],
    ['Cost control', 'costcontrol', 'Allowance, commitments, actuals, accruals, CTC and EAC per line. Load a CMT here for a gap analysis.'],
    ['Accruals', 'accruals', 'Raise and review accruals; they reverse when the invoice lands.'],
    ['Forecast lines', 'forecast', 'Choose a method per line and adjust the monthly forecast.'],
    ['Project schedule', 'programme', 'Keep the timeline current.'],
    ['Month-end', 'monthend', 'The routine in order with where each step stands: Pronto, accruals, review, close, reports.'],
    ['Month-end review', 'review', 'Review the month, log complexity and client behaviour, then issue the reports.']],
    'Next: month-end review, then the EOM report, PMR and PSR. Repeat each month.'],
  ['3. Revenue and subcontractors', [
    ['Contract and claims', 'revenue', 'Claim schedule and progress claims; client approved amounts drive revenue.'],
    ['Variations', 'variations', 'Raise and track variations; approved ones add to the allowance.'],
    ['Subcontracts', 'subcontracts', 'Subcontractor claims; a payment certificate is issued when you approve.']],
    'Next: submit the claim, record the client certificate, then match it to Pronto.'],
  ['4. Governance', [
    ['Project gate and phase', 'gates', 'Gate papers and phase tracking.'],
    ['Month-end review', 'review', 'Complexity, client behaviour and the month-end checks.'],
    ['Reports', 'eom', 'EOM report, PMR and PSR.'],
    ['Communication', 'commatrix', 'Stakeholders, communication matrix and the project org chart.']],
    'Next: complete the paper for the next gate and obtain its approval.'],
  ['5. Close-out', [
    ['Close-out', 'closeout', 'Final reconciliation, lessons and handover.'],
    ['Archive', 'library', 'Closed projects move here.']],
    'Next: close out, pass the final gate, then archive the project.'],
];


const NS = 'http://www.w3.org/2000/svg';
const el = (tag, attrs, ...kids) => { const n = document.createElementNS(NS, tag); Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, v)); kids.forEach((k) => n.append(k)); return n; };

// A row of boxes joined by arrows; `loop` draws a return arrow from the last box to the first.
function chart(boxes, { loop, link } = {}) {
  const W = 150, G = 36, H = 54, x0 = 8, y0 = loop ? 12 : 8;
  const width = x0 * 2 + boxes.length * W + (boxes.length - 1) * G, height = H + y0 + (loop ? 40 : 14);
  const svg = el('svg', { viewBox: `0 0 ${width} ${height}`, width: '100%', role: 'img', style: 'max-width:' + width + 'px' });
  const defs = el('defs', {}, el('marker', { id: 'ah', viewBox: '0 0 8 8', refX: 7, refY: 4, markerWidth: 7, markerHeight: 7, orient: 'auto' }, el('path', { d: 'M0,0 L8,4 L0,8 z', fill: '#335062' })));
  svg.append(defs);
  boxes.forEach((b, i) => {
    const x = x0 + i * (W + G), [title, sub, to] = Array.isArray(b) ? b : [b];
    const g = el('g', { style: to ? 'cursor:pointer' : '' });
    if (to) g.addEventListener('click', () => (to.includes('?') ? go('setup', { step: to.split('=')[1] }) : go(to)));
    g.append(el('rect', { x, y: y0, width: W, height: H, rx: 6, fill: i === 0 ? '#102361' : '#e0e6e8' }));
    const t = el('text', { x: x + W / 2, y: y0 + (sub ? 23 : 32), 'text-anchor': 'middle', 'font-size': 13, 'font-weight': 700, fill: i === 0 ? '#ffffff' : '#102361', 'font-family': 'Mulish, Calibri, sans-serif' }); t.textContent = title; g.append(t);
    if (sub) { const u = el('text', { x: x + W / 2, y: y0 + 41, 'text-anchor': 'middle', 'font-size': 10.5, fill: i === 0 ? '#ffffff' : '#335062', 'font-family': 'Mulish, Calibri, sans-serif' }); u.textContent = sub; g.append(u); }
    svg.append(g);
    if (i) svg.append(el('line', { x1: x - G + 2, y1: y0 + H / 2, x2: x - 3, y2: y0 + H / 2, stroke: '#335062', 'stroke-width': 1.6, 'marker-end': 'url(#ah)' }));
  });
  if (loop) {
    const xa = x0 + (boxes.length - 1) * (W + G) + W / 2, xb = x0 + W / 2, yb = y0 + H + 22;
    svg.append(el('path', { d: `M${xa},${y0 + H} L${xa},${yb} L${xb},${yb} L${xb},${y0 + H + 3}`, fill: 'none', stroke: '#e56210', 'stroke-width': 1.6, 'marker-end': 'url(#ah)' }));
    const t = el('text', { x: (xa + xb) / 2, y: yb - 5, 'text-anchor': 'middle', 'font-size': 11, fill: '#335062', 'font-family': 'Mulish, Calibri, sans-serif' }); t.textContent = loop; svg.append(t);
  }
  return svg;
}

const CHARTS = [
  ['Project life cycle', [['Set up', 'Project, contract, CBS', 'setup?step=project'], ['Initialise', 'Lock the estimate', 'setup?step=initialise'], ['Run', 'Monthly cycle', 'costcontrol'], ['Gates', 'Papers and approvals', 'gates'], ['Close-out', 'Final reconciliation', 'closeout'], ['Archive', 'Project is archived', 'library']]],
  ['Month-end cycle', [['Load Pronto', 'New exports', 'pronto'], ['Cost control', 'Check allowance, CTC', 'costcontrol'], ['Accruals', 'Raise and reverse', 'accruals'], ['Forecast', 'Method and months', 'forecast'], ['Claims', 'Claim and certify', 'revenue'], ['Review', 'Month-end review', 'review'], ['Reports', 'EOM, PMR, PSR', 'eom']], { loop: 'Next month' }],
  ['Allowances and CBS', [['CBS group', 'Role or trade pot'], ['Link resource', 'Pick option 1, 2 or 3', 'allowance'], ['Ledger', 'Link is the starting point', 'cbs'], ['Pronto cost', 'Matched by resource code', 'pronto'], ['Cost control', 'Overspend shows a transfer', 'costcontrol']]],
  ['Gate system', [['Phase work', 'Deliver the phase', 'phases'], ['Gate paper', 'Complete the form', 'gates'], ['Review', 'Approver by value', 'gates'], ['Approved', 'Gate passed', 'phases']], { loop: 'Next phase' }],
];

export default async function flow(root) {
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Workflow'),
    h('div', { class: 'sub' }, 'The project from start to close-out, stage by stage, and the next step in each. The full guide is in the chat button and the Project library.'))));
  for (const [title, boxes, opt] of CHARTS) root.append(h('div', { class: 'card', style: { marginBottom: '14px', overflowX: 'auto' } }, h('h2', {}, title), chart(boxes, opt)));
  for (const [title, items, next] of STAGES) {
    root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, title),
      h('table', { class: 't' }, h('tbody', {}, items.map(([name, to, text]) => h('tr', {},
        h('td', { style: { width: '220px' } }, h('a', { href: '#', onclick: (e) => { e.preventDefault(); to.includes('?') ? go('setup', { step: to.split('=')[1] }) : go(to); } }, name)),
        h('td', {}, text))))),
      h('div', { class: 'note', style: { marginTop: '8px' } }, next)));
  }
  root.append(h('div', { class: 'card' }, h('h2', {}, 'Aligning allowances with CBS resources'),
    h('ol', {},
      h('li', {}, 'On the Allowance page (Setup), link each resource to a bucket with option 1, 2 or 3; the link is posted to the ledger. In CBS and allowances, each group (role or trade pot) holds its proposal allowance; an "(Unallocated)" row is allowance not yet given to a named line.'),
      h('li', {}, 'Add a line under the group: pick the resource (employee or company) or type its Pronto code. The resource code is what ties Pronto cost to the line.'),
      h('li', {}, 'Before Initialise, type the budget on the line. After Initialise, use Transfer to move allowance from the group or pot to the line; the ledger keeps every movement.'),
      h('li', {}, 'On Pronto data, "New employees and subcontractors" lists every resource posting cost without a line; tick them to create lines. Their cost is parked on the pot until funded.'),
      h('li', {}, 'On Cost control, any line with cost but no allowance, and any pot that is overspent, shows where a transfer is needed.'))));
}
