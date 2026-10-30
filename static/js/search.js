import { h, clear } from './ui.js';
import { api, state, saveLocal } from './api.js';

// Global search (Ctrl+K, or "/" outside a text box): pages, projects, CBS lines of the open project, library documents,
// clients and people. Type, use the arrow keys, press Enter. Esc closes.
const norm = (s) => String(s || '').toLowerCase();

export async function openSearch({ pages, go, switchProject }) {
  if (document.getElementById('gsearch')) return;
  const input = h('input', { type: 'search', placeholder: 'Search pages, projects, CBS lines, documents, clients, people...', autofocus: true, style: { width: '100%', fontSize: '16px', padding: '12px 14px' } });
  const list = h('div', { class: 'gs-list' });
  const ov = h('div', { class: 'ov', id: 'gsearch', style: { alignItems: 'flex-start', paddingTop: '12vh' } }, h('div', { class: 'md', style: { width: 'min(680px, 94vw)' } },
    h('div', { class: 'mb', style: { padding: '12px' } }, input, list, h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Up and down to choose, Enter to open, Esc to close. Shortcut: Ctrl+K.'))));
  document.body.append(ov);
  const close = () => { ov.remove(); document.removeEventListener('keydown', onKey, true); };
  ov.addEventListener('mousedown', (e) => { if (e.target === ov) close(); });

  const groups = [
    ['Pages', pages.map(([k, label, grp]) => ({ label, sub: grp, run: () => { location.hash = '#/' + k; } }))],
    ['Projects', state.projects.filter((x) => !x.archived_at).map((x) => ({ label: x.name, sub: [x.code, x.client_name].filter(Boolean).join(' · '), run: () => switchProject(x.id) }))],
  ];
  const later = (title, getter) => getter.then((rows) => { groups.push([title, rows]); draw(); }).catch(() => {});
  later('CBS lines', state.pid ? api.get(`/api/p/${state.pid}/cost-control?months=0`).then((r) => r.rows.filter((x) => x.kind !== 'pot').map((x) => ({ label: `${x.code} ${x.name}`, sub: 'CBS', run: () => go('forecast', { node: x.node_id }) }))) : Promise.resolve([]));
  later('Library documents', api.get('/api/kb').then((r) => r.docs.map((d) => ({ label: d.title, sub: [d.doc_type, d.phase].filter(Boolean).join(' · '), run: () => window.open(d.url) }))));
  later('Clients', api.get('/api/clients').then((r) => r.map((c) => ({ label: c.name, sub: 'Client', run: () => go('directory') }))));
  later('People', api.get('/api/people').then((r) => r.map((x) => ({ label: x.name, sub: [x.role, x.org].filter(Boolean).join(' · ') || 'Person', run: () => go('directory') }))));

  let sel = 0; let shown = [];
  function draw() {
    const q = norm(input.value).trim();
    shown = [];
    clear(list);
    groups.forEach(([title, rows]) => {
      const hits = rows.filter((r) => !q || norm(`${r.label} ${r.sub}`).includes(q)).slice(0, q ? 8 : (title === 'Pages' ? 8 : 0));
      if (!hits.length) return;
      list.append(h('div', { class: 'small muted', style: { margin: '10px 0 2px', fontWeight: 700 } }, title));
      hits.forEach((r) => {
        const i = shown.length; shown.push(r);
        list.append(h('div', { class: 'gs-row' + (i === sel ? ' on' : ''), onmouseenter: () => { sel = i; mark(); }, onclick: () => { close(); r.run(); } }, h('span', {}, r.label), r.sub ? h('span', { class: 'small muted', style: { marginLeft: '10px' } }, r.sub) : null));
      });
    });
    if (!shown.length) list.append(h('div', { class: 'muted', style: { padding: '12px 4px' } }, 'Nothing found'));
    if (sel >= shown.length) sel = 0;
  }
  const mark = () => [...list.querySelectorAll('.gs-row')].forEach((el, i) => { el.classList.toggle('on', i === sel); if (i === sel) el.scrollIntoView({ block: 'nearest' }); });
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(shown.length - 1, sel + 1); mark(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(0, sel - 1); mark(); }
    else if (e.key === 'Enter' && shown[sel]) { e.preventDefault(); const r = shown[sel]; close(); r.run(); }
  };
  document.addEventListener('keydown', onKey, true);
  input.addEventListener('input', () => { sel = 0; draw(); });
  draw();
  setTimeout(() => input.focus(), 0);
}
