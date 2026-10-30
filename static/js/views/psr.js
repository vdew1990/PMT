import { h } from '../ui.js';
import { reportPlan } from './_reportplan.js';

// REPORTING > PSR: the Progress Summary Report to the client. Placeholder: the layout is to be agreed with the client
// (often set by the contract). It never shows EPEC's internal cost, margin or contingency.
export default async function psr(root) {
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'PSR: Progress Summary Report'),
    h('div', { class: 'sub' }, 'Progress report to the client. It shows progress, claims and variations, never internal cost or margin. The sections below are the proposed layout and are not built yet.'))));
  root.append(reportPlan({
    title: 'Progress Summary Report (client)', audience: 'The client (project manager / superintendent)', when: 'As the contract requires, usually monthly',
    purpose: 'Progress against the project schedule, what was achieved and is coming, claims and variations, issues needing the client',
    sections: [
      ['Summary', 'Overall progress and status for the period', '', ''],
      ['Safety (HSE)', 'Incidents and statistics for the client', '', ''],
      ['Progress', 'Physical progress by area or milestone, photos', 'Project schedule', '#/programme'],
      ['Project schedule', 'Milestones, baseline against forecast, look-ahead', 'Project schedule', '#/programme'],
      ['Payment claims', 'Claimed, certified and paid to date; next claim', 'Contract and claims', '#/revenue?tab=claims'],
      ['Variations', 'Submitted, approved and pending with the client', 'Variations', '#/variations'],
      ['Issues and RFIs', 'Open items needing the client\'s decision or information', '', ''],
      ['Look-ahead', 'Work planned for the next period', '3-week look-ahead (Forecast)', '#/forecast'],
    ],
    note: 'Share the client\'s required format (from the contract or a previous PSR) and this becomes the report, with an Excel / PDF download.',
  }));
}
