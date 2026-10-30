import { h, empty } from '../ui.js';

// COMMUNICATION > Communication matrix: who is told what, how often and by whom (content to be defined).
export default async function commatrix(root) {
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Communication matrix'), h('div', { class: 'sub' }, 'Who is told what, how often, by whom and how.'))));
  root.append(empty('Communication matrix: not built yet', 'This page will list who gets which information, how often, from whom and by what method, drawing on the Stakeholders and the Project org chart. Until then, the Stakeholders page holds each person\'s contact details and interest.'));
}
