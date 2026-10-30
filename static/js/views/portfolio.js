import { h, clear, fmt, chart, PALETTE, select, empty, tone, chartJump } from '../ui.js';
import { api, state, saveLocal } from '../api.js';
import { go, boot, openIn, isDirector } from '../app.js';
import { projectMap, typeColour, TYPES, fmtMWh, canonType } from '../map.js';
import { bandBadge, gateBadge } from './_assess.js';
const avg = (xs) => { const v = xs.filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
import { clientsTab } from './_clients.js';
import { teamTab } from './_team.js';
import { fitTab } from './teamfit.js';
import { rollupTree, projectChart, chartFromPortfolio } from '../rollup.js';

// OVERVIEW > Portfolio: the running projects side by side. A project manager sees the projects they manage, a project
// director the program they direct (from Project setup: EPEC project manager / EPEC project director); anyone can look
// at anyone's, or at every running project. Figures, then the analytics, then the projects one per row.
const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
const BAD = '#c62828', GOOD = '#3c8d40';
const norm = (s) => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();

export default async function portfolio(root) { return portfolioPage(root, {}); }
// Program and Team (OVERVIEW, for project directors) are this page with the director's program fixed: opts.mode 'direct', opts.tab, a title
export async function portfolioPage(root, opts = {}) {
  const d = await api.get('/api/portfolio');
  const page = opts.page || 'portfolio';
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, opts.title || 'Portfolio'),
    h('div', { class: 'sub' }, opts.sub || 'The running projects side by side: the ones you manage, the program you direct, or all of them. Each project as at its own status date. Click a project to open it.'))));
  if (!d.projects.length) { root.append(empty('No running projects', 'Create a project, or restore one from the Archive.')); return; }

  const me = state.me?.name || '';
  const director = isDirector();
  const key = 'pfui' + (page === 'portfolio' ? '' : '_' + page);
  const ui = JSON.parse(sessionStorage.getItem(key) || 'null') || { mode: opts.mode || 'manage', who: me };
  if (opts.mode) ui.mode = opts.mode;
  ui.tab = (opts.tab === 'team' && ui.tab === 'fit') ? 'fit' : (opts.tab || ui.tab || 'overview');
  if (opts.directorOnly && !director) { root.append(empty('For project directors', 'Program and Team show the projects and PMs a project director leads. Change your role to Project Director in your profile (top right) to see them.')); return; }
  const save = () => { try { sessionStorage.setItem(key, JSON.stringify(ui)); } catch (e) { /* ignore */ } };
  const bar = h('div', { class: 'card', style: { padding: '10px 14px', marginBottom: '12px' } });
  const body = h('div');
  root.append(bar, body);

  function pick() {
    const who = norm(ui.who);
    if (ui.mode === 'all') return d.projects;
    return d.projects.filter((p) => norm(ui.mode === 'direct' ? p.director : p.pm) === who);
  }
  const open = async (p) => { state.pid = p.id; state.scope = { node: null, from: null, to: null }; saveLocal(); await boot(); go('dashboard'); };

  function drawBar() {
    const chip = (k, label, title) => h('span', { class: 'chip' + (ui.mode === k ? ' on' : ''), title, onclick: () => { ui.mode = k; save(); drawBar(); draw(); } }, label);
    const people = [...new Set([me, ...d.people].filter(Boolean))];
    const forced = !!opts.mode;
    const tabs = page === 'team' ? [['team', 'PM workload'], ['fit', 'Team fit']] : [['overview', 'Overview'], ['chart', 'Project chart'], ['cbs', 'Combined CBS'], ['clients', 'Clients'], ...(forced ? [] : [['team', 'Team workload']])];
    clear(bar).append(h('div', { class: 'row' },
      ...(forced ? [h('span', { class: 'small muted' }, 'Director')] : [chip('manage', 'Portfolio (projects managed)', 'A PM\'s portfolio: projects where this person is the EPEC project manager'), chip('direct', 'Program (directed)', 'A project director\'s program: projects they direct for their clients (a child project takes its parent\'s director), and the team of PMs running them'),
      chip('all', 'All running projects')]),
      ui.mode !== 'all' ? h('span', { class: 'row', style: { gap: '6px', marginLeft: forced ? '0' : '10px' } }, forced ? null : h('span', { class: 'small muted' }, 'by'),
        select(people.map((x) => [x, x === me ? `${x} (you)` : x]), ui.who || me, { onchange: (e) => { ui.who = e.target.value; save(); draw(); } })) : null,
      h('span', { class: 'sp', style: { flex: 1 } }),
      ...tabs.map(([k, l]) => h('button', { class: 'btn sm ' + (ui.tab === k ? '' : 'ghost'), onclick: () => { ui.tab = k; save(); drawBar(); draw(); } }, l)),
      h('span', { style: { width: '10px' } }),
      h('span', { class: 'small muted' }, `${d.projects.length} running project${d.projects.length === 1 ? '' : 's'} · ${d.pms.length} PM${d.pms.length === 1 ? '' : 's'} · ${d.directors.length} director${d.directors.length === 1 ? '' : 's'}`)));
  }

  function draw() {
    const list = pick();
    clear(body);
    const ctx = { ui, save, list, all: d.projects, open, redraw: () => { drawBar(); draw(); }, me };
    if (ui.tab === 'fit') return fitTab(body, ctx);
    if (ui.tab === 'team') return teamTab(body, ctx);
    if (ui.tab === 'cbs' && list.length) return combined(body, list, ui);
    if (ui.tab === 'chart' && list.length) {
      const box = h('div');
      body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Project chart'), h('span', { class: 'sp' }),
        h('span', { class: 'small muted' }, 'Program or portfolio > parent project > child project. Click a project for its cost control.')), box));
      projectChart(box, chartFromPortfolio(list, d.parents || [], { mode: ui.mode, who: ui.who }), { current: state.pid });
      return;
    }
    if (ui.tab === 'clients' && list.length) return clientsTab(body, ctx);
    if (!list.length) {
      body.append(empty(ui.mode === 'direct' ? `No project names ${ui.who || 'you'} as project director` : `No project names ${ui.who || 'you'} as project manager`,
        'Each project says who manages and directs it on Project setup (EPEC project manager, EPEC project director), spelt the same way as the name at the top right. Or look at all running projects.',
        h('button', { class: 'btn', onclick: () => { ui.mode = 'all'; save(); drawBar(); draw(); } }, 'All running projects')));
      return;
    }
    const S = (k) => list.reduce((a, p) => a + (p[k] || 0), 0);
    const cv = S('contract_value'), eac = S('eac'), co = S('contract_original'), mo = S('margin_original');
    const tile = (l, v, s, c = '', vc = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v ' + vc }, v), h('div', { class: 's' }, s));
    body.append(h('div', { class: 'grid g6', style: { marginBottom: '14px' } },
      tile('Projects', String(list.length), `${S('lines_over')} CBS lines forecast over budget`),
      tile('Contract value', fmt.m(cv), `original ${fmt.m(co)}`, 't2'),
      tile('Final cost (EAC)', fmt.m(eac), `${fmt.m(S('ctd') + S('acc'))} spent so far`, 't3'),
      tile('Forecast margin', cv ? fmt.pct((cv - eac) / cv) : '–', `${fmt.m(cv - eac)}; at tender ${co ? fmt.pct(mo / co) : '–'}`, 't4', tone(cv - eac)),
      tile(S('erosion') >= 0 ? 'Margin uplift' : 'Margin erosion', fmt.m(S('erosion')), 'forecast less tender margin', 't5', tone(S('erosion'))),
      tile('Claimed to date', fmt.m(S('claimed')), `${fmt.m(cv - S('claimed'))} still to claim`, 't6')));

    // ---- where the projects are, and what they are ------------------------------------------------------------
    const mapBox = h('div', { style: { height: '420px' } });
    body.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Where the projects are'), h('span', { class: 'sp' }),
      h('span', { class: 'small muted' }, 'Hover a dot for its figures, click to open the project. Layers (top right): outline offline, street map online.')), mapBox));
    projectMap(mapBox, list, { onOpen: open }).catch((e) => mapBox.replaceChildren(h('div', { class: 'note warn' }, 'The map could not load: ' + e.message)));
    mixRow(body, list);

    // ---- analytics ---------------------------------------------------------------------------------------------
    const names = list.map((p) => p.code || p.name);
    const tip = { title: (it) => list[it[0].dataIndex].name };
    const toProject = chartJump(({ index }) => open(list[index]));
    const card = (title, sub, box) => h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, title), h('span', { class: 'sp' }), sub ? h('span', { class: 'small muted' }, sub) : null), box);
    const b1 = h('div', { class: 'chartbox' }), b2 = h('div', { class: 'chartbox' }), b3 = h('div', { class: 'chartbox' }), b4 = h('div', { class: 'chartbox' }), b5 = h('div', { class: 'chartbox' }), b6 = h('div', { class: 'chartbox' });
    body.append(h('div', { class: 'grid g2', style: { marginBottom: '14px' } },
      card('Margin by project', 'At tender and forecast now · click a project', b1), card('Contract value and final cost', 'Click a project to open it', b2)));
    body.append(h('div', { class: 'grid g2', style: { marginBottom: '14px' } },
      card('Cost and revenue by month', 'All projects in view · lighter bars are forecast', b3), card('Cumulative cost and revenue', 'All projects in view', b4)));
    body.append(h('div', { class: 'grid g2', style: { marginBottom: '14px' } },
      card('Time elapsed against cost spent', 'Above the line: spending ahead of time', b5), card('Contingency by project', 'Allowance less EAC: below zero is a forecast overrun', b6)));

    const pctAxis = { ticks: { callback: (v) => `${Math.round(v * 100)}%` } };
    chart(b1, { type: 'bar', data: { labels: names, datasets: [
      { label: 'At tender', data: list.map((p) => p.margin_original_pct ?? 0), backgroundColor: rgba(PALETTE[0], 0.35), borderRadius: 4 },
      { label: 'Forecast', data: list.map((p) => p.margin_pct ?? 0), backgroundColor: list.map((p) => ((p.margin_pct ?? 0) < (p.margin_original_pct ?? 0) - 0.005 ? PALETTE[1] : PALETTE[0])), borderRadius: 4 }] },
    options: { scales: { y: pctAxis }, plugins: { tooltip: { callbacks: { ...tip, label: (c) => `${c.dataset.label}: ${fmt.pct(c.parsed.y)}` } } }, ...toProject } });
    chart(b2, { type: 'bar', data: { labels: names, datasets: [
      { label: 'Contract value', data: list.map((p) => p.contract_value), backgroundColor: PALETTE[0], borderRadius: 4 },
      { label: 'Final cost (EAC)', data: list.map((p) => p.eac), backgroundColor: PALETTE[1], borderRadius: 4 }] },
    options: { plugins: { tooltip: { callbacks: tip } }, ...toProject } });

    // monthly: summed over the projects in view, by calendar month
    const months = [...new Set(list.flatMap((p) => Object.keys(p.months)))].sort();
    const sumM = (i) => months.map((m) => list.reduce((a, p) => a + ((p.months[m] || [])[i] || 0), 0));
    const landed = sumM(0), fcast = sumM(1), rev = sumM(2);
    const nowM = list.map((p) => p.status_month).sort().pop();
    chart(b3, { type: 'bar', data: { labels: months.map(fmt.month), datasets: [
      { label: 'Cost landed', data: landed, backgroundColor: PALETTE[1], stack: 'c', borderRadius: 2 },
      { label: 'Cost forecast', data: fcast, backgroundColor: rgba(PALETTE[1], 0.4), stack: 'c', borderRadius: 2 },
      { label: 'Revenue (claimed, then planned)', data: rev, backgroundColor: (c) => (months[c.dataIndex] > nowM ? rgba(PALETTE[0], 0.4) : PALETTE[0]), stack: 'r', borderRadius: 2 }] },
    options: { scales: { x: { stacked: true }, y: { stacked: true } } } });
    const cum = (a) => { let s = 0; return a.map((v) => (s += v)); };
    chart(b4, { type: 'line', data: { labels: months.map(fmt.month), datasets: [
      { label: 'Cost (landed + forecast)', data: cum(months.map((_, i) => landed[i] + fcast[i])), borderColor: PALETTE[1], backgroundColor: PALETTE[1], borderWidth: 2, pointRadius: 0, tension: 0.15 },
      { label: 'Revenue', data: cum(rev), borderColor: PALETTE[0], backgroundColor: PALETTE[0], borderWidth: 2, pointRadius: 0, tension: 0.15 }] },
    options: { interaction: { mode: 'index', intersect: false } } });

    // time vs cost: each project a dot; the diagonal is "spending in step with time"
    const pts = list.map((p, i) => ({ x: p.elapsed_pct, y: p.spent_pct, i })).filter((q) => q.x != null && q.y != null);
    chart(b5, { type: 'scatter', data: { datasets: [
      { label: 'In step', type: 'line', data: [{ x: 0, y: 0 }, { x: 1, y: 1 }], borderColor: '#9aa5b8', borderDash: [4, 4], borderWidth: 1, pointRadius: 0 },
      { label: 'Projects', data: pts, backgroundColor: pts.map((q) => (q.y > q.x + 0.1 ? PALETTE[1] : PALETTE[0])), pointRadius: 7, pointHoverRadius: 9, borderColor: '#fff', borderWidth: 2 }] },
    options: { scales: { x: { min: 0, max: 1, ...pctAxis, title: { display: true, text: 'Time elapsed (start to end)' } }, y: { min: 0, max: 1.2, ...pctAxis, title: { display: true, text: 'Cost spent (of EAC)' } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { title: (it) => (it[0].datasetIndex ? list[pts[it[0].dataIndex].i].name : ''), label: (c) => (c.datasetIndex ? `Time ${fmt.pct(c.parsed.x, 0)}, cost ${fmt.pct(c.parsed.y, 0)}` : 'Spending in step with time') } } },
      ...chartJump(({ index, datasetIndex }) => { if (datasetIndex === 1) open(list[pts[index].i]); }) } });
    chart(b6, { type: 'bar', data: { labels: names, datasets: [{ label: 'Contingency', data: list.map((p) => p.contingency), backgroundColor: list.map((p) => (p.contingency < 0 ? BAD : GOOD)), borderRadius: 4 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: tip } }, ...toProject } });

    // ---- by project manager (a director's program, or everyone) --------------------------------------------------
    if (ui.mode !== 'manage') {
      const by = new Map();
      list.forEach((p) => { const k = p.pm || '(no PM named)'; if (!by.has(k)) by.set(k, []); by.get(k).push(p); });
      const rows = [...by.entries()].map(([pm, ps]) => { const s = (k) => ps.reduce((a, p) => a + (p[k] || 0), 0); const c = s('contract_value'), e = s('eac');
        return { pm, n: ps.length, cv: c, eac: e, m: c ? s('margin') / c : null, ero: s('erosion'), over: s('lines_over'), cont: s('contingency') }; }).sort((a, b) => b.cv - a.cv);
      body.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, ui.mode === 'direct' ? 'The team: project managers in this program' : 'By project manager'),
        h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Project manager', 'Projects', 'Contract value', 'Final cost (EAC)', 'Forecast margin', 'Margin erosion', 'Contingency', 'Lines over budget'].map((x, i) => h('th', { class: i ? 'r' : '' }, x)))),
          h('tbody', {}, rows.map((r) => h('tr', { style: { cursor: 'pointer' }, title: `Show ${r.pm}'s projects`, onclick: () => { if (r.pm.startsWith('(')) return; ui.mode = 'manage'; ui.who = r.pm; save(); drawBar(); draw(); } },
            h('td', {}, h('b', {}, r.pm)), h('td', { class: 'r num' }, String(r.n)), h('td', { class: 'r num' }, fmt.money(r.cv)), h('td', { class: 'r num' }, fmt.money(r.eac)),
            h('td', { class: 'r num ' + (r.m != null && r.m < 0 ? 'bad' : '') }, fmt.pct(r.m)), h('td', { class: 'r num ' + tone(r.ero) }, fmt.money(r.ero)), h('td', { class: 'r num ' + tone(r.cont) }, fmt.money(r.cont)), h('td', { class: 'r num' }, String(r.over)))))))));
    }

    // ---- the projects: a program by client, then parent project, then child; a portfolio by parent then child ----
    const projRow = (p, depth = 0) => h('tr', { style: { cursor: 'pointer' }, title: 'Open this project', onclick: () => open(p) },
          h('td', { style: { paddingLeft: `${8 + depth * 16}px` } }, depth ? '↳ ' : '', h('b', {}, p.name), p.code || p.number ? h('div', { class: 'small muted' }, [p.code, p.number, p.location].filter(Boolean).join(' · ')) : null),
          h('td', {}, gateBadge(p), p.gate_stage && p.gate_stage !== 'Whole project' ? h('div', { class: 'small muted' }, p.gate_stage) : null, p.delivery_phase ? h('div', { class: 'small muted' }, p.delivery_phase) : null), h('td', {}, p.client || '', h('div', {}, bandBadge(p.client_challenge, p.client_band))), h('td', { class: 'small' }, p.pm || h('span', { class: 'muted' }, 'no PM'), p.director ? h('div', { class: 'muted' }, p.director) : null),
          h('td', { class: 'nowrap' }, fmt.date(p.status_date)), h('td', { class: 'r num' }, fmt.money(p.contract_value)), h('td', { class: 'r num' }, fmt.money(p.claimed)),
          h('td', { class: 'r num' }, fmt.money(p.ctd + p.acc)), h('td', { class: 'r num' }, fmt.money(p.eac)), h('td', { class: 'r num ' + tone(p.contingency) }, fmt.money(p.contingency)),
          h('td', { class: 'r num' }, fmt.pct(p.margin_original_pct)), h('td', { class: 'r num ' + ((p.margin_pct ?? 0) < 0 ? 'bad' : '') }, fmt.pct(p.margin_pct)), h('td', { class: 'r num ' + tone(p.erosion) }, fmt.money(p.erosion)),
          h('td', { class: 'small nowrap' }, p.elapsed_pct != null ? `${fmt.pct(p.elapsed_pct, 0)} / ${fmt.pct(p.spent_pct, 0)}` : fmt.pct(p.spent_pct, 0)),
          h('td', { class: 'small', title: p.assessed_month ? `Last assessed ${fmt.month(p.assessed_month)}` : 'No assessment yet: record it from the client card or Project setup' }, p.client_pm_name || '', h('div', { class: 'muted' }, p.client_pm_difficulty || p.assessed_complexity ? `PM ${p.client_pm_difficulty ?? '-'} · complexity ${p.assessed_complexity ?? p.complexity ?? '-'}${p.assessment_trend ? (p.assessment_trend > 0 ? ' ↑' : ' ↓') : ''}` : 'not assessed')),
          h('td', { class: 'r num' }, `${p.lines_over} of ${p.lines}`));
    // how challenging the clients in this view are, with what the PMs recorded about the client PMs and the projects' complexity
    {
      const byClient = new Map();
      list.forEach((p) => { const k = p.client || '(no client)'; if (!byClient.has(k)) byClient.set(k, []); byClient.get(k).push(p); });
      const cl = [...byClient.entries()].map(([name, ps]) => ({ name, ps, score: ps[0].client_challenge, band: ps[0].client_band, quad: ps[0].client_quadrant, value: ps.reduce((a, x) => a + (x.contract_value || 0), 0),
        pmd: avg(ps.map((x) => x.client_pm_difficulty)), cx: avg(ps.map((x) => x.assessed_complexity ?? x.complexity)) })).sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
      if (cl.length) body.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Client challenge'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Where the client sits on knowledge and difficulty, plus the PMs\' monthly read on the client PM and complexity. Open a client under Stakeholders to change it.')),
        h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Client', 'Challenge', 'Type of client', 'Projects', 'Contract value', 'Client PM difficulty (latest)', 'Project complexity'].map((x, i) => h('th', { class: i === 4 ? 'r' : '' }, x)))),
          h('tbody', {}, cl.map((c) => h('tr', {}, h('td', {}, h('b', {}, c.name)), h('td', {}, bandBadge(c.score, c.band)), h('td', { class: 'small' }, c.quad || h('span', { class: 'muted' }, 'position not set')),
            h('td', {}, c.ps.map((x) => x.name).join(', ')), h('td', { class: 'r num' }, fmt.m(c.value)), h('td', {}, c.pmd != null ? c.pmd.toFixed(1) : h('span', { class: 'muted' }, 'not assessed')), h('td', {}, c.cx != null ? c.cx.toFixed(1) : '')))))))); 
    }
    body.append(h('div', { class: 'card' }, h('h2', {}, 'Projects'),
      h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Project', 'Gate', 'Client', 'PM / director', 'Status date', 'Contract value', 'Claimed', 'Spent', 'Final cost (EAC)', 'Contingency', 'Margin: tender', 'Margin: forecast', 'Erosion', 'Time / cost', 'Client PM and complexity', 'Lines over'].map((x, i) => h('th', { class: i >= 5 && i !== 14 && i !== 12 ? 'r' : '' }, x)))),
        h('tbody', {}, nested(list, projRow, ui.mode)))),
      d.errors.length ? h('div', { class: 'note warn', style: { marginTop: '8px' } }, `Not shown (could not be computed): ${d.errors.map((e) => e.name).join(', ')}`) : null));
  }
  drawBar(); draw();
}

// rows of the projects table, nested: client (program / all) > parent project > child project, with subtotals
function nested(list, projRow, mode) {
  const KEYS = ['contract_value', 'claimed', 'ctd', 'acc', 'eac', 'contingency', 'lines_over', 'lines'];
  const sub = (ps, label, cls, depth, extra) => {
    const S = (k) => ps.reduce((a, p) => a + (p[k] || 0), 0);
    const cv = S('contract_value'), eac = S('eac');
    return h('tr', { class: cls, onclick: extra?.onclick, style: extra?.onclick ? { cursor: 'pointer' } : {}, title: extra?.title || '' },
      h('td', { style: { paddingLeft: `${8 + depth * 16}px` } }, h('b', {}, label), h('div', { class: 'small muted' }, `${ps.length} project${ps.length === 1 ? '' : 's'}`)),
      h('td'), h('td', { class: 'small' }, extra?.who || ''), h('td'),
      h('td', { class: 'r num' }, h('b', {}, fmt.money(cv))), h('td', { class: 'r num' }, fmt.money(S('claimed'))), h('td', { class: 'r num' }, fmt.money(S('ctd') + S('acc'))),
      h('td', { class: 'r num' }, h('b', {}, fmt.money(eac))), h('td', { class: 'r num ' + tone(S('contingency')) }, fmt.money(S('contingency'))), h('td'),
      h('td', { class: 'r num ' + (cv && cv - eac < 0 ? 'bad' : '') }, cv ? fmt.pct((cv - eac) / cv) : '–'), h('td'), h('td'), h('td', { class: 'r num' }, `${S('lines_over')} of ${S('lines')}`));
  };
  const byParent = (ps, depth) => {
    const out = [];
    const seen = new Set();
    ps.forEach((p) => {
      if (!p.parent_id) { out.push(projRow(p, depth)); return; }
      if (seen.has(p.parent_id)) return;
      seen.add(p.parent_id);
      const kids = ps.filter((x) => x.parent_id === p.parent_id);
      out.push(sub(kids, `▣ ${p.parent_name}`, depth ? 'par' : 'gp', depth, { onclick: () => openIn(p.parent_id, 'dashboard'), title: 'Open the parent project (its children together)' }));
      kids.forEach((k) => out.push(projRow(k, depth + 1)));
    });
    return out;
  };
  if (mode === 'manage') return byParent(list, 0);
  const clients = [...new Set(list.map((p) => (p.client || '').trim() || '(no client)'))].sort();
  return clients.flatMap((c) => {
    const ps = list.filter((p) => ((p.client || '').trim() || '(no client)') === c);
    return [sub(ps, c, 'gp', 0, { who: [...new Set(ps.map((p) => p.pm).filter(Boolean))].join(', ') }), ...byParent(ps, 1)];
  });
}

// the CBS of every project in view lumped together, each line drilling down to the projects and their own lines
async function combined(body, list, ui) {
  const box = h('div');
  body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, ui.mode === 'direct' ? `${ui.who}'s program: the CBS together` : ui.mode === 'manage' ? `${ui.who}'s portfolio: the CBS together` : 'All running projects: the CBS together'),
    h('span', { class: 'sp' }), h('span', { class: 'small muted' }, `${list.length} project${list.length === 1 ? '' : 's'}, added code by code; each project's EAC in its own column`)), box));
  box.append(h('div', { class: 'muted small' }, 'Adding up...'));
  const res = await api.get('/api/rollup?ids=' + list.map((p) => p.id).join(','));
  rollupTree(box, res);
}

// the portfolio's make-up: by type (value, MW, MWh), by client, by voltage
function mixRow(body, list) {
  const S = (arr, k) => arr.reduce((a, p) => a + (p[k] || 0), 0);
  const kvs = list.map((p) => p.kv).filter(Boolean);
  const tile = (l, v, s, c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s));
  const clients = [...new Set(list.map((p) => (p.client || '').trim()).filter(Boolean))];
  body.append(h('div', { class: 'grid g5', style: { marginBottom: '14px' } },
    tile('Generation capacity', `${fmt.n(S(list, 'mw'))} MW`, `${list.filter((p) => p.mw).length} project(s) with MW set`),
    tile('Energy storage', fmtMWh(S(list, 'mwh')), `${list.filter((p) => p.mwh).length} project(s) with storage`, 't2'),
    tile('Highest voltage', kvs.length ? `${fmt.n(Math.max(...kvs))} kV` : '–', kvs.length ? `${list.filter((p) => (p.kv || 0) >= 220).length} project(s) at 220 kV or more` : 'Set voltages on Project setup', 't3'),
    tile('Clients', String(clients.length), clients.slice(0, 3).join(', ') + (clients.length > 3 ? '...' : ''), 't4'),
    tile('Average complexity', list.length ? fmt.n(S(list, 'complexity') / list.length, 1) + ' / 5' : '–', `${list.filter((p) => !p.complexity_set).length} suggested, not set`, 't5')));
  const typeOf = (p) => (TYPES.includes(canonType(p.project_type)) ? canonType(p.project_type) : 'Other');
  const types = TYPES.filter((t) => list.some((p) => typeOf(p) === t));
  const byClient = clients.map((c) => ({ c, v: S(list.filter((p) => (p.client || '').trim() === c), 'contract_value') })).sort((a, b) => b.v - a.v).slice(0, 8);
  const band = (kv) => (!kv ? 'Not set' : kv <= 33 ? 'Up to 33 kV' : kv <= 132 ? '66 to 132 kV' : kv <= 275 ? '220 to 275 kV' : '330 kV and above');
  const bands = ['Up to 33 kV', '66 to 132 kV', '220 to 275 kV', '330 kV and above', 'Not set'].filter((b) => list.some((p) => band(p.kv) === b));
  const b1 = h('div', { class: 'chartbox' }), b2 = h('div', { class: 'chartbox' }), b3 = h('div', { class: 'chartbox' });
  const card = (t, s, b) => h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, t), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, s)), b);
  body.append(h('div', { class: 'grid g3', style: { marginBottom: '14px' } }, card('Contract value by type', 'MW and MWh in the tooltip', b1), card('Contract value by client', 'Top 8', b2), card('Projects by voltage', 'Highest voltage on site', b3)));
  chart(b1, { type: 'bar', data: { labels: types, datasets: [{ label: 'Contract value', data: types.map((t) => S(list.filter((p) => typeOf(p) === t), 'contract_value')), backgroundColor: types.map(typeColour), borderRadius: 4 }] },
    options: { plugins: { legend: { display: false }, tooltip: { callbacks: { afterLabel: (c) => { const ps = list.filter((p) => typeOf(p) === types[c.dataIndex]); return `${ps.length} project(s) · ${fmt.n(S(ps, 'mw'))} MW · ${fmtMWh(S(ps, 'mwh'))}`; } } } } } });
  chart(b2, { type: 'bar', data: { labels: byClient.map((x) => x.c), datasets: [{ label: 'Contract value', data: byClient.map((x) => x.v), backgroundColor: PALETTE[0], borderRadius: 4 }] },
    options: { indexAxis: 'y', plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmt.money(c.parsed.x) } } }, scales: { x: { ticks: { callback: (v) => fmt.m(v) } }, y: { ticks: { callback: function (v) { const l = this.getLabelForValue(v); return l.length > 22 ? l.slice(0, 21) + '...' : l; } } } } } });
  chart(b3, { type: 'bar', data: { labels: bands, datasets: [{ label: 'Projects', data: bands.map((b) => list.filter((p) => band(p.kv) === b).length), backgroundColor: PALETTE[3], borderRadius: 4 }] },
    options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.parsed.y} project(s)`, afterLabel: (c) => list.filter((p) => band(p.kv) === bands[c.dataIndex]).map((p) => p.name).join(', ') } } }, scales: { y: { ticks: { precision: 0, callback: (v) => v } } } } });
}
