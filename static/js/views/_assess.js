import { h, clear, fmt, modal, toast, field, select, badge, chart, PALETTE, confirmBox } from '../ui.js';
import { api, state } from '../api.js';
import { go } from '../app.js';

// Client challenge: the knowledge / difficulty grid a client card is placed on, and the monthly assessment of a project's
// client PM and complexity that EPEC's PMs keep through the project (app/challenge.py explains how they add up).
export const KNOWLEDGE = { 1: 'Clueless', 2: 'Limited', 3: 'Typical', 4: 'Informed', 5: 'Expert' };
export const DIFFICULTY = { 1: 'Easy', 2: 'Fairly easy', 3: 'Typical', 4: 'Demanding', 5: 'Difficult' };
export const BAND_KIND = { Easy: 'good', Manageable: '', Challenging: 'warn', 'Very challenging': 'bad' };
const n01 = (v) => (v - 1) / 4;

export function positionScore(k, d) {
  if (k && d) return Math.round(100 * (0.6 * n01(d) + 0.4 * (1 - n01(k))));
  if (d) return Math.round(100 * n01(d));
  if (k) return Math.round(100 * (1 - n01(k)));
  return null;
}
export function quadrant(k, d) {
  if (!k || !d) return null;
  const exp = k >= 4, clue = k <= 2, hard = d >= 4, easy = d <= 2;
  if (exp && easy) return ['Ideal client', 'Knows what they want and is easy to deal with.'];
  if (exp && hard) return ['Demanding expert', 'Knows the detail and pushes back on scope, price and process.'];
  if (clue && hard) return ['Hands-on and hard', 'Needs educating and also contests decisions: the most PM time.'];
  if (clue && easy) return ['Needs guidance', 'Pleasant, but relies on EPEC to explain and steer.'];
  if (exp) return ['Capable', 'Knows the work; the working relationship is typical.'];
  if (clue) return ['Needs education', 'Limited knowledge; allow time to explain.'];
  if (hard) return ['Demanding', 'Typical knowledge but hard to work with.'];
  if (easy) return ['Easy going', 'Typical knowledge and easy to work with.'];
  return ['Typical', 'Neither knowledge nor difficulty stands out.'];
}
export const bandOf = (s) => (s == null ? null : s < 25 ? 'Easy' : s < 45 ? 'Manageable' : s < 65 ? 'Challenging' : 'Very challenging');
export const bandBadge = (score, band) => (score == null ? h('span', { class: 'muted small' }, 'not rated') : badge(`${band || bandOf(score)} · ${score}`, BAND_KIND[band || bandOf(score)]));

// a 5 x 5 grid: knowledge across (clueless to expert), difficulty up (easy at the bottom, difficult at the top). Click a square.
export function positionPicker(init, onChange) {
  const st = { k: init.knowledge || null, d: init.difficulty || null };
  const note = h('div', { class: 'small', style: { marginTop: '6px', minHeight: '34px' } });
  const grid = h('div', { class: 'pgrid' });
  const draw = () => {
    const q = quadrant(st.k, st.d); const s = positionScore(st.k, st.d);
    clear(grid);
    for (let d = 5; d >= 1; d--) for (let k = 1; k <= 5; k++) {
      const on = st.k === k && st.d === d;
      const heat = 0.6 * n01(d) + 0.4 * (1 - n01(k));
      grid.append(h('div', { class: 'pcell' + (on ? ' on' : ''), title: `${KNOWLEDGE[k]} · ${DIFFICULTY[d]}`, style: { background: on ? '' : `rgba(229,98,16,${0.06 + heat * 0.34})` },
        onclick: () => { st.k = k; st.d = d; draw(); onChange?.(st); } }, on ? '●' : ''));
    }
    clear(note).append(...[q ? h('span', {}, h('b', {}, q[0]), ' ' + q[1], s != null ? h('span', { class: 'muted' }, ` Position score ${s}.`) : '') : h('span', { class: 'muted' }, 'Click the square that fits: across for what they know, up for how hard they are to deal with.'),
      st.k || st.d ? h('a', { style: { marginLeft: '8px' }, onclick: () => { st.k = null; st.d = null; draw(); onChange?.(st); } }, 'Clear') : null].filter(Boolean));
  };
  draw();
  const el = h('div', {}, h('div', { class: 'pwrap' },
    h('div', { class: 'pyl' }, h('span', {}, 'Difficult'), h('span', {}, 'Easy')),
    h('div', {}, grid, h('div', { class: 'pxl' }, h('span', {}, 'Clueless'), h('span', {}, 'Expert')))), note);
  return { el, knowledge: { get value() { return st.k ?? ''; } }, complexity: { get value() { return st.d ?? ''; } } };
}

const ym = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;

// the monthly assessments of one project: list, chart and a form to add or replace a month
export async function assessDialog(project, after) {
  // the open project is assessed on its Project complexity page (ten dimensions); this dialog stays for the other projects reached from the Portfolio
  if (project.id === state.pid) { go('complexity', { tab: 'monthly' }); return; }
  const base = `/api/p/${project.id}/assessments`;
  const body = h('div');
  async function draw() {
    const { rows, summary } = await api.get(base);
    const month = h('input', { type: 'month', value: ym() });
    const pm = h('input', { type: 'text', value: summary.client_pm || project.client_pm || '', placeholder: 'Client project manager' });
    const last = rows[rows.length - 1] || {};
    const opts = (labels) => [['', '(no change)'], ...Object.entries(labels).map(([k, v]) => [k, `${k} · ${v}`])];
    const diff = select([['', '(not rated)'], ...Object.entries(DIFFICULTY).map(([k, v]) => [k, `${k} · ${v}`])], last.pm_difficulty ?? '');
    const cx = select([['', '(not rated)'], ...[[1, '1 · Simple'], [2, '2'], [3, '3 · Typical'], [4, '4'], [5, '5 · Very complex']]], last.complexity ?? '');
    const note = h('input', { type: 'text', placeholder: 'What changed this month (optional)' });
    const box = h('div', { class: 'chartbox short', style: { marginTop: '8px' } });
    clear(body).append(...[
      h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'Record each month how hard the client\'s project manager is to work with and how complex the project is. A difficult PM on a simple project and an easy PM on a complex one both count. The mean across the project\'s life feeds the client\'s challenge rating.'),
      h('div', { class: 'grid g4' }, field('Month', month), field('Client PM', pm), field('Client PM difficulty', diff), field('Project complexity', cx)), field('Note', note),
      h('div', { style: { marginTop: '8px' } }, h('button', { class: 'btn', onclick: async () => {
        try { await api.put(base, { month: month.value, client_pm: pm.value, pm_difficulty: diff.value, complexity: cx.value, note: note.value }); toast('Assessment saved'); after?.(); await draw(); } catch (e) { toast(e.message, 'bad'); }
      } }, 'Save assessment')),
      rows.length ? h('div', { style: { marginTop: '14px' } }, h('b', {}, `${project.name}: ${rows.length} assessment${rows.length === 1 ? '' : 's'}`),
        summary.score != null ? h('span', { style: { marginLeft: '8px' } }, bandBadge(summary.score), summary.trend ? h('span', { class: 'small muted', style: { marginLeft: '8px' } }, summary.trend > 0 ? `Getting harder (+${summary.trend})` : `Easing (${summary.trend})`) : null) : null,
        box,
        h('div', { class: 'tw', style: { marginTop: '8px' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Month', 'Client PM', 'PM difficulty', 'Complexity', 'Note', 'By', ''].map((x) => h('th', {}, x)))),
          h('tbody', {}, [...rows].reverse().map((r) => h('tr', {}, h('td', {}, fmt.month(r.month)), h('td', {}, r.client_pm || ''), h('td', {}, r.pm_difficulty ? `${r.pm_difficulty} · ${DIFFICULTY[r.pm_difficulty]}` : ''),
            h('td', {}, r.complexity ? String(r.complexity) : ''), h('td', { class: 'small' }, r.note || ''), h('td', { class: 'small muted' }, r.by || ''),
            h('td', {}, h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox(`Delete the ${fmt.month(r.month)} assessment?`, 'Delete', true)) { await api.del(`${base}/${r.id}`); after?.(); draw(); } } }, '×')))))))) : null].filter(Boolean));
    if (rows.length > 1) setTimeout(() => chart(box, { type: 'line', data: { labels: rows.map((r) => fmt.month(r.month)), datasets: [
      { label: 'Client PM difficulty', data: rows.map((r) => r.pm_difficulty), borderColor: PALETTE[1], backgroundColor: PALETTE[1], spanGaps: true, tension: .2 },
      { label: 'Project complexity', data: rows.map((r) => r.complexity), borderColor: PALETTE[0], backgroundColor: PALETTE[0], spanGaps: true, tension: .2 }] },
    options: { scales: { y: { min: 1, max: 5, ticks: { stepSize: 1, callback: (v) => v } } }, plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y}` } } } } }), 30);
  }
  await draw();
  modal({ title: `Client PM and complexity: ${project.name}`, size: 'wide', body, actions: [{ label: 'Close', kind: 'ghost', onClick: () => true }] });
}

// Project gates 1 to 7 (app/gates.py): where the project stands, and every change kept. A gate can move back (Early Works, then EPC).
export const gateBadge = (p) => (p.gate ? badge(`Gate ${p.gate}`, p.gate >= 5 ? 'good' : 'warn') : h('span', { class: 'muted small' }, 'no gate set'));
export async function gateCard(project) {
  const box = h('div', { class: 'card', style: { marginTop: '14px' } });
  async function draw() {
    const g = await api.get(`/api/p/${project.id}/gates`);
    const today = new Date().toISOString().slice(0, 10);
    const sel = select(g.gates.map((x) => [x.gate, x.label]), g.current?.gate ?? 5);
    const stage = select(g.stages.map((s) => [s, s]), g.current?.stage || 'Whole project');
    const date = h('input', { type: 'date', value: today });
    const note = h('input', { type: 'text', placeholder: 'Optional: e.g. Early Works awarded, EPC proposal to follow' });
    const cur = g.current;
    const dl = h('div', { class: 'small', style: { marginTop: '6px' } });
    const showDl = () => { const x = g.gates.find((y) => y.gate === +sel.value); clear(dl).append(x.has_form ? h('a', { href: `/api/gates/${x.gate}/form`, download: '' }, `Download the Gate ${x.gate} paper (${x.form}, Word)`) : h('span', { class: 'muted' }, `No paper has been loaded for Gate ${x.gate} yet.`)); };
    sel.onchange = showDl; showDl();
    clear(box).append(...[
      h('div', { class: 'ch' }, h('h2', {}, 'Project gate'), h('span', { class: 'sp' }), cur ? h('span', {}, badge(`Gate ${cur.gate}`, cur.gate >= 5 ? 'good' : 'warn'), h('span', { class: 'small muted', style: { marginLeft: '8px' } }, `${cur.label.replace(/^Gate \d: ?/, '') || 'name to be confirmed'} · ${cur.phase}${cur.stage && cur.stage !== 'Whole project' ? ' · ' + cur.stage : ''} · since ${fmt.date(cur.date)}`)) : h('span', { class: 'muted small' }, 'No gate recorded yet')),
      h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'Record the gate the project has reached. PMs join from Gate 3 and set the project up around Gates 4 and 5. With an Early Works award followed by an EPC award a project goes round Gates 3 to 5 twice, so choose any gate, earlier ones included; every change is kept below.'),
      h('div', { class: 'grid g4' }, field('Gate reached', sel), field('Applies to', stage), field('Date', date), field('Note', note)),
      dl,
      h('div', { style: { margin: '8px 0' } }, h('button', { class: 'btn', onclick: async () => { try { await api.post(`/api/p/${project.id}/gates`, { gate: +sel.value, stage: stage.value, date: date.value, note: note.value }); toast(`Gate ${sel.value} recorded`); await draw(); } catch (e) { toast(e.message, 'bad'); } } }, 'Record gate')),
      g.rows.length ? h('div', { class: 'tw' }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Date', 'Gate', 'Applies to', 'Note', 'By', ''].map((x) => h('th', {}, x)))),
        h('tbody', {}, [...g.rows].sort((a, b) => (b.date + b.id).localeCompare(a.date + a.id)).map((r) => h('tr', {}, h('td', {}, fmt.date(r.date)), h('td', {}, `Gate ${r.gate}`), h('td', {}, r.stage || ''), h('td', { class: 'small' }, r.note || ''), h('td', { class: 'small muted' }, r.by || ''),
          h('td', {}, h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox(`Delete the Gate ${r.gate} entry of ${fmt.date(r.date)}?`, 'Delete', true)) { await api.del(`/api/p/${project.id}/gates/${r.id}`); draw(); } } }, '×'))))))) : null,
      h('details', { style: { marginTop: '10px' } }, h('summary', { class: 'small' }, 'What the gates are'),
        h('div', { class: 'small', style: { marginTop: '4px' } }, g.gates.map((x) => h('div', {}, h('b', {}, `Gate ${x.gate}`), `: ${x.name || 'name to be confirmed'}${x.form ? ' (' + x.form + ')' : ''} · ${x.phase} phase `, x.has_form ? h('a', { href: `/api/gates/${x.gate}/form`, download: '' }, 'Download paper') : null)))),
    ].filter(Boolean));
  }
  await draw();
  return box;
}

// Delivery phases (Design, Procure, Construct, Commission, Close Out): when the PM moves the project to the next one, PMT shows what to look
// for and offers the readiness review paper (app/gates.py PHASES, checklists read from EPEC's forms).
function reminderBody(ph) {
  return h('div', {}, h('div', { class: 'note', style: { marginBottom: '10px' } }, ph.remind),
    ...ph.reviews.map((r) => h('div', { class: 'card', style: { marginBottom: '10px' } },
      h('div', { class: 'row', style: { gap: '8px' } }, h('b', {}, r.name), badge(r.status, r.status === 'Mandatory' ? 'bad' : ''), h('span', { class: 'sp', style: { flex: 1 } }),
        r.has_form ? h('a', { class: 'btn sm', href: `/api/forms/${r.code}`, download: '' }, 'Download the paper (Word)') : h('span', { class: 'muted small' }, `${r.code}: paper not loaded yet`)),
      h('div', { class: 'small muted', style: { margin: '4px 0 6px' } }, `${r.code} · ${r.when} · Reviewer: ${r.reviewer}`),
      r.sections.length ? h('div', {}, r.sections.map((s) => h('details', { open: s === r.sections.find((z) => z.items.length) }, h('summary', { class: 'small' }, h('b', {}, `${s.no}. ${s.title}`), h('span', { class: 'muted' }, ` (${s.items.length})`)),
        s.items.length ? h('ul', { class: 'small', style: { margin: '4px 0 6px 18px' } }, s.items.map((x) => h('li', {}, x))) : null))) : h('div', { class: 'small muted' }, 'The checklist items are not loaded: send the paper to add them.'))),
    ph.reviews.length ? null : h('div', { class: 'small muted' }, 'No review paper for this phase.'));
}
export function phaseReminder(ph) { modal({ title: `Entering ${ph.phase}: what to look for`, size: 'wide', body: reminderBody(ph), actions: [{ label: 'Close', kind: 'ghost', onClick: () => true }] }); }

export async function phaseCard(project) {
  const box = h('div', { class: 'card', style: { marginTop: '14px' } });
  async function draw() {
    const g = await api.get(`/api/p/${project.id}/phases`);
    const sel = select(g.phases.map((x) => [x.phase, x.phase]), g.current?.phase || 'Design');
    const date = h('input', { type: 'date', value: new Date().toISOString().slice(0, 10) });
    const note = h('input', { type: 'text', placeholder: 'Optional' });
    const cur = g.current;
    clear(box).append(...[
      h('div', { class: 'ch' }, h('h2', {}, 'Delivery phase'), h('span', { class: 'sp' }), cur ? h('span', {}, badge(cur.phase, 'good'), h('span', { class: 'small muted', style: { marginLeft: '8px' } }, `since ${fmt.date(cur.date)}`), h('button', { class: 'btn ghost sm', style: { marginLeft: '8px' }, onclick: () => phaseReminder(g.phases.find((x) => x.phase === cur.phase)) }, 'Show what to look for')) : h('span', { class: 'muted small' }, 'Not set')),
      h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'Tell PMT when the project moves to its next delivery phase (Design, Procure, Construct, Commission, Close Out). It then shows what to look for in that phase and offers the readiness review paper.'),
      h('div', { class: 'grid g4' }, field('Moved to', sel), field('Date', date), field('Note', note), h('div', { style: { alignSelf: 'end' } }, h('button', { class: 'btn', onclick: async () => {
        try { await api.post(`/api/p/${project.id}/phases`, { phase: sel.value, date: date.value, note: note.value }); toast(`Moved to ${sel.value}`); phaseReminder(g.phases.find((x) => x.phase === sel.value)); await draw(); } catch (e) { toast(e.message, 'bad'); } } }, 'Move to this phase'))),
      g.rows.length ? h('div', { class: 'tw', style: { marginTop: '8px' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['Date', 'Phase', 'Note', 'By', ''].map((x) => h('th', {}, x)))),
        h('tbody', {}, [...g.rows].sort((a, b) => (b.date + b.id).localeCompare(a.date + a.id)).map((r) => h('tr', {}, h('td', {}, fmt.date(r.date)), h('td', {}, r.phase), h('td', { class: 'small' }, r.note || ''), h('td', { class: 'small muted' }, r.by || ''),
          h('td', {}, h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox(`Delete the ${r.phase} entry of ${fmt.date(r.date)}?`, 'Delete', true)) { await api.del(`/api/p/${project.id}/phases/${r.id}`); draw(); } } }, '×'))))))) : null,
    ].filter(Boolean));
  }
  await draw();
  return box;
}
