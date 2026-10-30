import { h, clear, fmt, modal, tone, statusPill, empty } from './ui.js';
import { openIn } from './app.js';

// Projects lumped together: a parent project's children, a PM's portfolio or a director's program. The CBS is merged
// code by code (app/linking.py); every row carries by_project, what each project puts in, so any row drills down to the
// project's own line (its drawer: forecast, actuals, accruals, POs) however high up you start.

const COLS = [['allowance', 'Allowance'], ['ctd', 'CTD'], ['acc', 'Accruals'], ['ctc', 'CTC'], ['eac', 'EAC'], ['contingency', 'Contingency']];

// one row's split by project; each project opens on its own line in cost control
export function splitDialog(r, note) {
  const parts = r.by_project || [];
  const tot = (k) => parts.reduce((a, x) => a + (x[k] || 0), 0);
  const body = h('div', {},
    h('p', { class: 'small muted', style: { marginTop: 0 } }, note || 'What each project puts into this line. Open a project to see the line there with its forecast, actuals, accruals and POs.'),
    parts.length ? h('div', { class: 'tw' }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Project'), ...COLS.map(([, l]) => h('th', { class: 'r' }, l)), h('th', {}, 'Status'), h('th', {}, ''))),
      h('tbody', {}, parts.map((x) => h('tr', { class: 'click', title: `Open ${r.code} in ${x.project}`, onclick: () => go(x) },
        h('td', {}, h('b', {}, x.project), x.method ? h('div', { class: 'small muted' }, x.method) : null),
        ...COLS.map(([k]) => h('td', { class: 'r num ' + (k === 'contingency' ? tone(x[k]) : '') }, fmt.money(x[k]))),
        h('td', {}, x.budget_status ? statusPill(x.budget_status) : ''),
        h('td', {}, h('button', { class: 'btn sm', onclick: (e) => { e.stopPropagation(); go(x); } }, 'Open in project'))))),
      parts.length > 1 ? h('tfoot', {}, h('tr', {}, h('td', {}, h('b', {}, 'Together')), ...COLS.map(([k]) => h('td', { class: 'r num' }, h('b', {}, fmt.money(tot(k))))), h('td'), h('td'))) : null))
      : empty('No project has this line', ''));
  const md = modal({ title: `${r.code}  ${r.name}: by project`, size: 'wide', body, actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }] });
  function go(x) {
    md.close();
    // a line or pot opens its drawer; a group opens cost control scoped to it
    openIn(x.project_id, 'costcontrol', x.kind === 'group' ? { node: x.id } : { open: x.id });
  }
}

// the merged CBS as a tree: groups fold, each project's EAC in its own column, click a row for its split
export function rollupTree(container, res, opts = {}) {
  const rows = res.rows || [];
  const projects = (res.children || []).filter((c) => !c.error);
  const byParent = new Map();
  rows.forEach((r) => { const k = r.parent_id ?? 'root'; if (!byParent.has(k)) byParent.set(k, []); byParent.get(k).push(r); });
  let level = opts.level || 2;
  const open = new Set(rows.filter((r) => r.kind === 'group' && r.level < level).map((r) => String(r.id)));
  let q = '';
  const bar = h('div', { class: 'row', style: { marginBottom: '8px' } },
    h('input', { type: 'search', placeholder: 'Search code or name...', style: { width: '240px' }, oninput: (e) => { q = e.target.value.trim().toLowerCase(); draw(); } }),
    h('span', { class: 'small muted' }, 'Expand to'),
    ...[1, 2, 3, 4, 5].map((n) => h('span', { class: 'chip lv' + (n === level ? ' on' : ''), onclick: (e) => {
      level = n; open.clear(); rows.forEach((r) => r.kind === 'group' && r.level < n && open.add(String(r.id)));
      bar.querySelectorAll('.chip.lv').forEach((c, i) => c.classList.toggle('on', i + 1 === n)); draw(); } }, 'L' + n)),
    h('span', { class: 'sp', style: { flex: 1 } }),
    h('span', { class: 'small muted' }, 'Click a line for each project\'s share and to open it in that project'));
  const wrap = h('div');
  clear(container).append(bar, wrap);
  const share = (r, pid) => (r.by_project || []).filter((x) => x.project_id === pid).reduce((a, x) => a + (x.eac || 0), 0);
  const cls = (r) => (r.kind !== 'group' ? '' : r.level === 1 ? 'gp' : r.level === 2 ? 'par' : 'par2');
  function visible() {
    if (q) return rows.filter((r) => `${r.code} ${r.name}`.toLowerCase().includes(q));
    const out = [];
    const walk = (pid) => (byParent.get(pid) || []).forEach((r) => { out.push(r); if (r.kind === 'group' && open.has(String(r.id))) walk(r.node_id); });
    walk('root');
    return out;
  }
  function draw() {
    const list = visible();
    const t = res.total || {};
    clear(wrap).append(list.length ? h('div', { class: 'tw', style: { maxHeight: opts.maxHeight || '70vh' } }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Code'), h('th', {}, 'Name'), ...COLS.map(([, l]) => h('th', { class: 'r' }, l)), h('th', {}, 'Status'),
        ...projects.map((p) => h('th', { class: 'r', title: `${p.name}: EAC` }, p.name.length > 22 ? p.name.slice(0, 21) + '…' : p.name)))),
      h('tbody', {}, list.map((r) => {
        const isOpen = open.has(String(r.id));
        const tog = r.kind === 'group' ? h('span', { class: 'tog', onclick: (e) => { e.stopPropagation(); isOpen ? open.delete(String(r.id)) : open.add(String(r.id)); draw(); } }, isOpen ? '▾' : '▸') : h('span', { class: 'tog' });
        return h('tr', { class: cls(r) + ' click', onclick: () => splitDialog(r) },
          h('td', { class: 'nowrap', style: { paddingLeft: `${8 + (r.level - 1) * 14}px` } }, tog, ' ', h('span', { class: 'mono' }, r.code)),
          h('td', {}, r.name),
          ...COLS.map(([k]) => h('td', { class: 'r num ' + (k === 'contingency' ? tone(r[k]) : '') }, fmt.money(r[k]))),
          h('td', {}, r.budget_status ? statusPill(r.budget_status) : ''),
          ...projects.map((p) => { const v = share(r, p.id); return h('td', { class: 'r num' + (v ? '' : ' muted') }, v ? fmt.money(v) : '–'); }));
      })),
      h('tfoot', {}, h('tr', {}, h('td', {}, h('b', {}, 'Total')), h('td'), ...COLS.map(([k]) => h('td', { class: 'r num' }, h('b', {}, fmt.money(t[k])))), h('td'),
        ...projects.map((p) => h('td', { class: 'r num' }, h('b', {}, fmt.money(p.eac)))))))) : empty('Nothing to show', 'No CBS lines match.'));
  }
  draw();
}

// ---- project chart: who sits under whom, click a box to go to that level's cost control ----------------------------
// nodes: {id?, name, kind: 'root'|'person'|'parent'|'child'|'project', sub, eac, contingency, children: [...]}
export function projectChart(container, root, opts = {}) {
  const here = opts.current;
  const box = (n) => {
    const can = n.id && n.kind !== 'root' && n.kind !== 'person';
    const el = h('div', { class: `pc-node pc-${n.kind}` + (n.id && n.id === here ? ' pc-here' : '') + (can ? ' pc-click' : ''),
      title: can ? `Open ${n.name}: cost control${n.kind === 'parent' ? ' of its children together' : ''}` : '',
      onclick: can ? () => openIn(n.id, 'costcontrol') : null },
    h('div', { class: 'pc-kind' }, { root: opts.rootLabel || 'Overview', person: n.role || 'Person', parent: 'Parent project', child: 'Child project', project: 'Project' }[n.kind]),
    h('div', { class: 'pc-name' }, n.name),
    n.sub ? h('div', { class: 'pc-sub' }, n.sub) : null,
    n.eac != null ? h('div', { class: 'pc-fig' }, `EAC ${fmt.m(n.eac)}`, n.contingency != null ? h('span', { class: tone(n.contingency) }, ` · ${fmt.m(n.contingency)}`) : null) : null);
    return el;
  };
  // n.stack: the children in a column (a PM's projects), not side by side
  const tree = (n) => h('li', {}, box(n), n.children?.length ? h('ul', { class: n.stack ? 'pc-stack' : '' }, n.children.map(tree)) : null);
  clear(container).append(h('div', { class: 'pchart' }, h('ul', {}, tree(root))),
    h('div', { class: 'small muted', style: { marginTop: '8px' } }, 'Click a parent or child project to open its cost control. A parent shows its children together; every line there drills down to the child.'));
}

// chart from Portfolio rows: projects (child and stand-alone) and parents, under people (director or PM) or one root
export function chartFromPortfolio(list, parents, { mode, who } = {}) {
  const S = (ps, k) => ps.reduce((a, p) => a + (p[k] || 0), 0);
  const node = (p, kind) => ({ id: p.id, name: p.name, kind, sub: [p.pm && `PM ${p.pm}`, p.client].filter(Boolean).join(' · '), eac: p.eac, contingency: p.contingency });
  const under = (ps) => {
    const out = [];
    const seen = new Set();
    ps.forEach((p) => {
      if (!p.parent_id) { out.push(node(p, 'project')); return; }
      if (seen.has(p.parent_id)) return;
      seen.add(p.parent_id);
      const kids = ps.filter((x) => x.parent_id === p.parent_id);
      const par = parents.find((x) => x.id === p.parent_id) || { id: p.parent_id, name: p.parent_name };
      out.push({ ...node({ ...par, eac: S(kids, 'eac'), contingency: S(kids, 'contingency'), pm: '' }, 'parent'),
        sub: par.director ? `Director ${par.director}` : `${kids.length} child projects`, children: kids.map((k) => node(k, 'child')) });
    });
    return out;
  };
  // a director's program: the team of PMs, each with their projects in a column (a child project says which parent
  // it is in), and each parent project once, with the children it brings together
  const team = (ps) => {
    const pms = [...new Set(ps.map((p) => p.pm || '(no PM named)'))].sort();
    const kids = pms.map((pm) => {
      const mine = ps.filter((p) => (p.pm || '(no PM named)') === pm);
      return { kind: 'person', role: 'Project manager', name: pm, eac: S(mine, 'eac'), contingency: S(mine, 'contingency'), stack: true,
        children: mine.map((p) => ({ ...node(p, p.parent_id ? 'child' : 'project'), sub: [p.client, p.parent_name && `in ${p.parent_name}`].filter(Boolean).join(' · ') })) };
    });
    const pids = [...new Set(ps.filter((p) => p.parent_id).map((p) => p.parent_id))];
    pids.forEach((id) => {
      const ch = ps.filter((p) => p.parent_id === id);
      const par = parents.find((x) => x.id === id) || { id, name: ch[0].parent_name };
      kids.push({ id, kind: 'parent', name: par.name, eac: S(ch, 'eac'), contingency: S(ch, 'contingency'),
        sub: ch.map((c) => `${c.name.replace(/^Demo team: /, '')} (${c.pm || 'no PM'})`).join(' + ') });
    });
    return kids;
  };
  if (mode === 'direct') {
    return { kind: 'person', role: 'Project director · program', name: who || '', eac: S(list, 'eac'), contingency: S(list, 'contingency'), children: team(list) };
  }
  if (mode === 'manage') {
    return { kind: 'person', role: 'Project manager · portfolio', name: who || '', eac: S(list, 'eac'), contingency: S(list, 'contingency'), children: under(list) };
  }
  // a parent sits once, under its own director, with all its children (a child may name another director)
  const dirOf = (p) => (p.parent_id ? ((parents.find((x) => x.id === p.parent_id) || {}).director || p.director) : p.director) || '(no director)';
  const dirs = [...new Set(list.map(dirOf))].sort();
  return { kind: 'root', name: 'All running projects', eac: S(list, 'eac'), contingency: S(list, 'contingency'),
    children: dirs.map((d) => { const ps = list.filter((p) => dirOf(p) === d); return { kind: 'person', role: 'Project director · program', name: d, eac: S(ps, 'eac'), contingency: S(ps, 'contingency'), children: team(ps) }; }) };
}
