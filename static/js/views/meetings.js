import { h, empty } from '../ui.js';

// COMMUNICATION > Meetings: the home for PMO meetings (content to be defined).
export default async function meetings(root) {
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Meetings'), h('div', { class: 'sub' }, 'PMO meetings.'))));
  root.append(empty('Meeting register: not built yet', 'This page will hold the project\'s meetings: agendas, minutes and actions. Until then, minutes and action lists are kept in the project folder.'));
}
