import { h } from '../ui.js';

// A report still being designed: its purpose, audience and planned sections, each with what PMT already holds for it
// (a link to the page with that data) or what is still to be built.
export function reportPlan({ title, audience, when, purpose, sections, note }) {
  return h('div', { class: 'card', style: { marginBottom: '14px' } },
    h('div', { class: 'row', style: { gap: '8px', marginBottom: '6px' } }, h('span', { class: 'badge warn' }, 'Placeholder'), h('b', {}, title)),
    h('div', { class: 'grid g3', style: { margin: '8px 0 12px' } },
      h('div', {}, h('div', { class: 'small muted' }, 'For'), h('div', {}, audience)),
      h('div', {}, h('div', { class: 'small muted' }, 'When'), h('div', {}, when)),
      h('div', {}, h('div', { class: 'small muted' }, 'Purpose'), h('div', {}, purpose))),
    h('div', { class: 'tw' }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'Section'), h('th', {}, 'Content'), h('th', {}, 'Source in PMT'))),
      h('tbody', {}, sections.map(([s, c, src, link], i) => h('tr', {},
        h('td', {}, String(i + 1)), h('td', {}, h('b', {}, s)), h('td', { class: 'small' }, c),
        h('td', { class: 'small' }, link ? h('a', { href: link }, src) : h('span', { class: src ? '' : 'muted' }, src || 'to be built'))))))),
    note ? h('div', { class: 'note', style: { marginTop: '10px' } }, note) : null);
}
