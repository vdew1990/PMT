import { h, clear, fmt, select, num, empty, debounce } from '../ui.js';
import { api, state, saveLocal } from '../api.js';
import { go, boot, setArchived } from '../app.js';

// PMO > Archive: finished projects kept for the record, apart from the running ones. Search on any field:
// name, code, client, location, project managers, period, contract value. Open one to look through it, or restore it.
export default async function library(root) {
  const all = await api.get('/api/library');
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Archive'),
    h('div', { class: 'sub' }, 'Finished projects, kept for the record apart from the running ones. Their figures are as they stood when archived. Archive a project from its Settings page.'))));
  if (!all.length) { root.append(empty('The archive is empty', 'Archive a finished project from its Settings page: it moves here, with its figures, and leaves the project list.')); return; }

  const ui = JSON.parse(sessionStorage.getItem('libui') || '{}');
  const save = () => { try { sessionStorage.setItem('libui', JSON.stringify(ui)); } catch (e) { /* ignore */ } };
  const opts = (k, label) => [['', label], ...[...new Set(all.map((p) => (p[k] || '').trim()).filter(Boolean))].sort().map((v) => [v, v])];
  const q = h('input', { type: 'search', value: ui.q || '', placeholder: 'Search name, code, client, location, manager, contract...', style: { width: '320px' }, oninput: debounce(() => { ui.q = q.value; save(); draw(); }, 150) });
  const sel = (k, label) => select(opts(k, label), ui[k] || '', { onchange: (e) => { ui[k] = e.target.value; save(); draw(); } });
  const client = sel('client_name', 'Every client'), loc = sel('location', 'Every location'), pm = sel('epec_pm', 'Every EPEC PM'), dir = sel('project_director', 'Every project director');
  const from = h('input', { type: 'month', value: ui.from || '', title: 'Projects running in this period (from)', onchange: () => { ui.from = from.value; save(); draw(); } });
  const to = h('input', { type: 'month', value: ui.to || '', title: 'Projects running in this period (to)', onchange: () => { ui.to = to.value; save(); draw(); } });
  const vmin = h('input', { type: 'number', value: ui.vmin ?? '', placeholder: 'min $', style: { width: '120px' }, onchange: () => { ui.vmin = vmin.value; save(); draw(); } });
  const vmax = h('input', { type: 'number', value: ui.vmax ?? '', placeholder: 'max $', style: { width: '120px' }, onchange: () => { ui.vmax = vmax.value; save(); draw(); } });
  root.append(h('div', { class: 'card', style: { padding: '10px 14px', marginBottom: '12px' } },
    h('div', { class: 'row' }, q, client, loc, pm, dir),
    h('div', { class: 'row', style: { marginTop: '8px' } }, h('span', { class: 'small muted' }, 'Running between'), from, h('span', { class: 'small muted' }, 'and'), to,
      h('span', { style: { width: '14px' } }), h('span', { class: 'small muted' }, 'Contract value'), vmin, h('span', { class: 'small muted' }, 'to'), vmax,
      h('span', { class: 'sp', style: { flex: 1 } }), h('button', { class: 'btn ghost sm', onclick: () => { sessionStorage.removeItem('libui'); clear(root); library(root); } }, 'Clear the search'))));
  const tiles = h('div', { class: 'grid g4', style: { marginBottom: '12px' } });
  const out = h('div');
  root.append(tiles, out);

  const ym = (d) => (d || '').slice(0, 7);
  function match(p) {
    if (ui.q) {
      const hay = [p.name, p.code, p.number, p.client_name, p.client_project_name, p.location, p.epec_pm, p.project_director, p.client_pm, p.contract_ref].join(' ').toLowerCase();
      if (!ui.q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w))) return false;
    }
    for (const k of ['client_name', 'location', 'epec_pm', 'project_director']) if (ui[k] && (p[k] || '').trim() !== ui[k]) return false;
    // running in the period: the project's start..end overlaps it (no dates: it cannot be placed, so it is left out)
    if (ui.from || ui.to) {
      const s = ym(p.project_start) || ym(p.project_end), e = ym(p.project_end) || ym(p.status_date) || s;
      if (!s) return false;
      if (ui.from && e < ui.from) return false;
      if (ui.to && s > ui.to) return false;
    }
    const v = p.contract_value ?? 0;
    if (ui.vmin !== undefined && ui.vmin !== '' && v < num(ui.vmin)) return false;
    if (ui.vmax !== undefined && ui.vmax !== '' && v > num(ui.vmax)) return false;
    return true;
  }
  const open = async (p) => { state.pid = p.id; state.scope = { node: null, from: null, to: null }; saveLocal(); await boot(); go('dashboard'); };

  function draw() {
    const list = all.filter(match);
    const sum = (k) => list.reduce((a, p) => a + (p[k] || 0), 0);
    const cv = sum('contract_value');
    const tile = (l, v, s, c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s));
    tiles.replaceChildren(tile('Projects', `${list.length} of ${all.length}`, 'matching the search'), tile('Contract value', fmt.m(cv), 'together', 't2'),
      tile('Final cost', fmt.m(sum('final_cost')), 'EAC when archived', 't3'), tile('Margin', cv ? fmt.pct((cv - sum('final_cost')) / cv) : '–', 'weighted by contract value', 't4'));
    clear(out).append(list.length ? h('div', { class: 'tw' }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, ['Project', 'Client', 'Location', 'EPEC PM', 'Start', 'End', 'Contract value', 'Final cost', 'Margin', 'Archived', ''].map((x, i) => h('th', { class: i >= 6 && i <= 8 ? 'r' : '' }, x)))),
      h('tbody', {}, list.map((p) => h('tr', { style: { cursor: 'pointer' }, title: 'Open this project to look through it', onclick: (e) => { if (!e.target.closest('button')) open(p); } },
        h('td', {}, h('b', {}, p.name), p.code || p.number ? h('div', { class: 'small muted' }, [p.code, p.number].filter(Boolean).join(' · ')) : null),
        h('td', {}, p.client_name || '', p.client_project_name ? h('div', { class: 'small muted' }, p.client_project_name) : null),
        h('td', {}, p.location || ''), h('td', {}, p.epec_pm || '', p.project_director ? h('div', { class: 'small muted' }, 'Director: ' + p.project_director) : null),
        h('td', { class: 'nowrap' }, fmt.date(p.project_start) || ''), h('td', { class: 'nowrap' }, fmt.date(p.project_end) || ''),
        h('td', { class: 'r num' }, p.contract_value != null ? fmt.money(p.contract_value) : ''), h('td', { class: 'r num' }, p.final_cost != null ? fmt.money(p.final_cost) : ''),
        h('td', { class: 'r num ' + (p.margin_pct != null && p.margin_pct < 0 ? 'bad' : '') }, p.margin_pct != null ? fmt.pct(p.margin_pct) : ''),
        h('td', { class: 'small nowrap' }, fmt.date((p.archived_at || '').slice(0, 10)), p.archived_by ? h('div', { class: 'muted' }, p.archived_by) : null),
        h('td', { class: 'nowrap' }, h('button', { class: 'btn ghost sm', onclick: () => open(p) }, 'Open'),
          h('button', { class: 'btn ghost sm', style: { marginLeft: '4px' }, title: 'Back to the running projects', onclick: () => setArchived(p.id, false) }, 'Restore')))))))
      : empty('No project matches', 'Change or clear the search.'));
  }
  draw();
}
