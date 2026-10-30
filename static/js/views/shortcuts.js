import { h, clear, toast, select, table } from '../ui.js';
import { api, state } from '../api.js';
import { DEFAULT_SHORTCUTS, comboOf, searchPages } from '../app.js';

// CONTROL > Shortcuts: the person's own keyboard shortcuts. Kept in their profile, so they follow them between PCs.
const RESERVED = ['Ctrl+T', 'Ctrl+W', 'Ctrl+N', 'Ctrl+R', 'Ctrl+L', 'Ctrl+P', 'Ctrl+S', 'Ctrl+F', 'Ctrl+Q', 'Ctrl+Tab', 'Ctrl+Shift+N', 'Ctrl+Shift+T', 'Ctrl+Shift+W', 'Ctrl+A', 'Ctrl+C', 'Ctrl+V', 'Ctrl+X', 'Ctrl+Z', 'Ctrl+Y', 'Alt+F4', 'F5', 'F11', 'F12'];

export default async function shortcuts(root) {
  const pages = searchPages();
  const actions = [['search', 'Open search'], ['back', 'Go back'], ['forward', 'Go forward'], ...pages.map(([k, label, grp]) => [`page:${k}`, `Go to: ${grp} > ${label}`])];
  let rows = (state.shortcuts || DEFAULT_SHORTCUTS).map((x) => ({ ...x }));
  const out = h('div');
  const problem = (r, i) => {
    if (!r.combo) return 'Press the keys';
    if (RESERVED.includes(r.combo)) return `${r.combo} is used by the browser`;
    if (!/^(Ctrl|Alt)\+|^F\d+$/.test(r.combo) && !['/', '?'].includes(r.combo)) return 'Use Ctrl or Alt with a key, or a function key';
    if (rows.some((x, j) => j !== i && x.combo === r.combo)) return `${r.combo} is already used above`;
    return '';
  };
  function capture(r, box) {
    document.body.dataset.capturing = '1';
    box.value = 'Press the keys...';
    const done = () => { delete document.body.dataset.capturing; box.removeEventListener('keydown', onKey, true); box.removeEventListener('blur', done); draw(); };
    const onKey = (e) => {
      e.preventDefault(); e.stopPropagation();
      if (e.key === 'Escape') return done();
      const c = comboOf(e); if (!c) return;
      r.combo = e.key === 'Backspace' ? '' : c; done();
    };
    box.addEventListener('keydown', onKey, true); box.addEventListener('blur', done);
  }
  function draw() {
    clear(out).append(table([
      { label: 'Keys', f: (r, i) => { const box = h('input', { type: 'text', readonly: true, value: r.combo, placeholder: 'Click, then press the keys', style: { width: '170px', cursor: 'pointer', fontFamily: 'monospace' } }); box.addEventListener('focus', () => capture(r, box)); return h('div', {}, box, problem(r, i) ? h('div', { class: 'small', style: { color: 'var(--bad)' } }, problem(r, i)) : null); } },
      { label: 'Does this', f: (r) => select(actions, r.action, { onchange: (e) => { r.action = e.target.value; }, style: { minWidth: '320px' } }) },
      { label: '', f: (r, i) => h('button', { class: 'btn danger sm', onclick: () => { rows.splice(i, 1); draw(); } }, 'Remove') },
    ], rows));
  }
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Shortcuts'), h('div', { class: 'sub' }, 'Your own keyboard shortcuts. They are kept in your profile and follow you between PCs. Click a Keys box and press the keys you want; Backspace clears it.'))));
  root.append(h('div', { class: 'card' }, out, h('div', { class: 'row', style: { marginTop: '12px', gap: '8px' } },
    h('button', { class: 'btn ghost', onclick: () => { rows.push({ combo: '', action: 'search' }); draw(); } }, 'Add a shortcut'),
    h('button', { class: 'btn ghost', onclick: () => { rows = DEFAULT_SHORTCUTS.map((x) => ({ ...x })); draw(); } }, 'Back to the defaults'),
    h('span', { class: 'sp', style: { flex: 1 } }),
    h('button', { class: 'btn', onclick: async () => {
      const bad = rows.map((r, i) => problem(r, i)).find(Boolean);
      if (bad) return toast(bad, 'bad');
      const r = await api.put('/api/me/shortcuts', { shortcuts: rows });
      state.shortcuts = r.shortcuts; toast('Shortcuts saved');
    } }, 'Save shortcuts')),
    h('div', { class: 'small muted', style: { marginTop: '10px' } }, 'Fixed keys: Esc closes a dialog or the search box; in the search box, the arrow keys choose and Enter opens. A plain key such as / only works when you are not typing in a box. Keys the browser keeps for itself (Ctrl+T, Ctrl+W, F5 and similar) cannot be used.')));
  draw();
}
