import { h, clear, fmt, toast, field, select, badge, chart, PALETTE, tabs, empty, confirmBox } from '../ui.js';
import { api, state, p, statusMonth } from '../api.js';
import { go, render } from '../app.js';
import { DIFFICULTY } from './_assess.js';

// SETUP > Project complexity (EPEC Project Complexity Matrix): ten dimensions scored 0 to 5, added up to a band C1 to C4.
//  - the project director sets the baseline (every revision is kept) and follows the PM's monthly assessments against it
//  - the PM scores the ten dimensions and the client's difficulty each month, and sees only their own assessments
const bandTone = (code) => ({ C1: 'good', C2: '', C3: 'warn', C4: 'bad' }[code] || '');
const bandCode = (name) => (name || '').slice(0, 2);
const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
const wrap = (s) => { const out = []; let line = ''; s.split(' ').forEach((w) => { if ((line + ' ' + w).trim().length > 17 && line) { out.push(line); line = w; } else line = (line + ' ' + w).trim(); }); out.push(line); return out; };

// The Complexity Profile of the EPEC framework: a radar of the ten dimensions on a 0 to 5 scale, one outline per reading.
// series: [{ label, scores: { dimension: { score } }, colour, dashed }]
export function radar(box, dims, series) {
  chart(box, { type: 'radar', data: { labels: dims.map((x) => wrap(x.label)), datasets: series.map((s) => ({ label: s.label, data: dims.map((x) => s.scores?.[x.key]?.score ?? null),
    borderColor: s.colour, backgroundColor: rgba(s.colour, s.dashed ? 0.04 : 0.18), borderWidth: 2, borderDash: s.dashed ? [6, 4] : [], pointRadius: s.dashed ? 0 : 3, pointBackgroundColor: s.colour })) },
  options: { scales: { r: { min: 0, max: 5, ticks: { stepSize: 1, backdropColor: 'transparent', callback: (v) => v }, pointLabels: { font: { size: 11 } }, grid: { color: '#d7dde0' }, angleLines: { color: '#d7dde0' } } },
    plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.r}` } } } } });
}

export default async function complexity(root, params) {
  const d = await api.get(p('/complexity'));
  const tab = params.tab || (d.director ? 'baseline' : 'monthly');
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Project complexity'),
    h('div', { class: 'sub' }, d.director ? 'Score the project on ten dimensions (0 to 5). The total gives the band and the PM level the project needs. The PM reports the same ten dimensions each month; you see how it moves against your baseline.'
      : 'Each month, score the ten dimensions (0 to 5) and the client\'s difficulty. Your assessments over time go into the monthly PMR.'))));
  if (d.director) root.append(tabs([['baseline', 'Baseline'], ['pm', 'PM\'s monthly assessments'], ['monthly', 'Add a monthly assessment']], tab, (k) => go('complexity', { tab: k })));
  const body = h('div'); root.append(body);
  if (tab === 'baseline' && d.director) baselineTab(body, d);
  else if (tab === 'pm' && d.director) pmTab(body, d);
  else monthlyTab(body, d, params);
}

// the ten rows: label and definition, 0 to 5 buttons, a note; the total and band under them. `hint` is last month's own score.
function scorer(d, start, { hint = {}, onChange, ghost = null, label = 'Score' } = {}) {
  const st = {}; d.dimensions.forEach((x) => { st[x.key] = { score: start?.[x.key]?.score ?? null, note: start?.[x.key]?.note || '' }; });
  const sum = h('div', { class: 'card', style: { margin: '10px 0', background: 'var(--grey, #e0e6e8)' } });
  const total = () => d.dimensions.reduce((a, x) => a + (st[x.key].score ?? 0), 0);
  const done = () => d.dimensions.every((x) => st[x.key].score !== null);
  const band = (t) => d.bands.find((b) => t <= b.upto) || d.bands[d.bands.length - 1];
  const drawSum = () => {
    const t = total(); const b = band(t);
    clear(sum).append(h('div', { class: 'row', style: { gap: '14px', flexWrap: 'wrap' } }, h('b', {}, `Total ${t} of 50`), badge(b.name, bandTone(b.code)), h('span', {}, `Typical ${b.typical}`),
      h('span', { class: 'muted small' }, done() ? '' : `${d.dimensions.filter((x) => st[x.key].score === null).length} dimensions not scored yet`)));
    onChange?.(t, done());
  };
  const rbox = h('div', { style: { height: '440px' } });
  const drawRadar = () => radar(rbox, d.dimensions, [...(ghost ? [ghost] : []), { label, scores: Object.fromEntries(d.dimensions.filter((x) => st[x.key].score !== null).map((x) => [x.key, { score: st[x.key].score }])), colour: PALETTE[0] }]);
  const rows = d.dimensions.map((x) => {
    const btns = [0, 1, 2, 3, 4, 5].map((n) => h('button', { type: 'button', class: 'btn sm ' + (st[x.key].score === n ? '' : 'ghost'), style: { minWidth: '34px' }, onclick: () => { st[x.key].score = n; btns.forEach((b, i) => { b.className = 'btn sm ' + (i === n ? '' : 'ghost'); }); drawSum(); drawRadar(); } }, String(n)));
    const note = h('input', { type: 'text', value: st[x.key].note, placeholder: 'Why this score (optional)', style: { width: '100%' }, oninput: () => { st[x.key].note = note.value; } });
    return h('tr', {}, h('td', { style: { width: '30%' } }, h('b', {}, x.label), h('div', { class: 'small muted' }, x.definition)),
      h('td', { class: 'nowrap' }, h('span', { class: 'row', style: { gap: '3px' } }, btns), hint[x.key] != null ? h('span', { class: 'small muted', style: { marginLeft: '8px' } }, `last ${hint[x.key]}`) : null), h('td', {}, note));
  });
  const el = h('div', { style: { display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 420px', gap: '16px', alignItems: 'start' } }, h('div', {}, h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, h('th', {}, 'Dimension'), h('th', {}, 'Score 0 to 5'), h('th', {}, 'Note'))), h('tbody', {}, rows))), sum), h('div', { style: { position: 'sticky', top: '70px', alignSelf: 'start' } }, h('div', { class: 'small muted', style: { textAlign: 'center' } }, 'Complexity profile'), rbox));
  drawSum(); setTimeout(drawRadar, 30);
  return { el, scores: () => st, complete: done, total };
}

function bandTable(d) {
  return h('details', { style: { marginTop: '12px' } }, h('summary', { class: 'small' }, 'The bands and what they ask of the PM'),
    h('div', { class: 'tw', style: { marginTop: '6px' } }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Band', 'Total', 'Typical PM level', 'Lowest PM level that should run it'].map((x) => h('th', {}, x)))),
      h('tbody', {}, d.bands.map((b, i) => h('tr', {}, h('td', {}, b.name), h('td', {}, `${i ? d.bands[i - 1].upto + 1 : 0} to ${b.upto}`), h('td', {}, b.typical), h('td', {}, `Level ${b.min_level}`)))))),
    h('div', { class: 'small muted', style: { marginTop: '4px' } }, 'From the EPEC Project Complexity Matrix (Scoring Tool and Complexity Matrix sheets). PM levels follow EPEC-PM-FW-0002; Level 5 is the project director.'));
}

function baselineTab(body, d) {
  const cur = d.baseline;
  const sc = scorer(d, cur?.scores, { label: 'Baseline' });
  const summary = h('textarea', { rows: 3, placeholder: 'Overall rationale for this score (shown with the revision)', style: { width: '100%' } }); summary.value = '';
  body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, cur ? 'Baseline' : 'Set the baseline'), h('span', { class: 'sp' }),
    cur ? h('span', { class: 'small muted' }, `Current: ${cur.total} points, ${cur.band}, set ${fmt.date(cur.created_at)}${cur.by ? ' by ' + cur.by : ''}`) : null),
    sc.el, field('Rationale', summary),
    h('div', { class: 'row', style: { marginTop: '10px' } }, h('button', { class: 'btn', onclick: async () => {
      if (!sc.complete()) { toast('Score every dimension from 0 to 5 first', 'bad'); return; }
      try { await api.put(p('/complexity/baseline'), { scores: sc.scores(), summary: summary.value }); toast('Baseline saved'); await render(); } catch (e) { toast(e.message, 'bad'); }
    } }, cur ? 'Save as a new revision' : 'Save the baseline'), h('span', { class: 'small muted' }, 'Earlier revisions are kept. The PM does not see the baseline.')), bandTable(d)));
  if (d.revisions?.length > 1) body.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('h2', {}, 'Revisions'),
    h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Date', 'By', 'Total', 'Band', 'Rationale'].map((x) => h('th', {}, x)))),
      h('tbody', {}, d.revisions.map((r) => h('tr', {}, h('td', {}, fmt.date(r.created_at)), h('td', {}, r.by || ''), h('td', { class: 'r' }, String(r.total)), h('td', {}, badge(r.band, bandTone(bandCode(r.band)))), h('td', { class: 'small wrap' }, r.summary || ''))))))));
}

function history(d, rows, withBaseline) {
  const box = h('div', { class: 'chartbox short', style: { marginTop: '8px' } });
  const b = withBaseline ? d.baseline : null;
  if (rows.length > 1 || (rows.length && b)) setTimeout(() => chart(box, { type: 'line', data: { labels: rows.map((r) => fmt.month(r.month)), datasets: [
    { label: 'Complexity total (0 to 50)', data: rows.map((r) => r.total), borderColor: PALETTE[0], backgroundColor: PALETTE[0], spanGaps: true, tension: .2, yAxisID: 'y' },
    ...(b ? [{ label: `Baseline (${b.total})`, data: rows.map(() => b.total), borderColor: PALETTE[1], borderDash: [6, 4], pointRadius: 0, yAxisID: 'y' }] : []),
    { label: 'Client difficulty (1 to 5)', data: rows.map((r) => r.pm_difficulty), borderColor: PALETTE[2], backgroundColor: PALETTE[2], spanGaps: true, tension: .2, yAxisID: 'y2' }] },
  options: { scales: { y: { min: 0, max: 50, ticks: { callback: (v) => v }, title: { display: true, text: 'Points' } }, y2: { position: 'right', min: 1, max: 5, ticks: { stepSize: 1, callback: (v) => v }, grid: { drawOnChartArea: false }, title: { display: true, text: 'Client difficulty' } } } } }), 30);
  return box;
}

function pmTab(body, d) {
  const rows = d.assessments; const b = d.baseline;
  if (!rows.length) { body.append(empty('No assessments yet', 'The PM scores the ten dimensions at each month-end. They appear here against your baseline.')); return; }
  const cmp = d.compare;
  if (!b) body.append(h('div', { class: 'note warn', style: { marginBottom: '12px' } }, 'You have not set a baseline yet, so there is nothing to compare the PM\'s assessments with.'));
  if (cmp) {
    const dims = d.dimensions.filter((x) => cmp.by_dimension[x.key] !== undefined);
    body.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, `Latest assessment ${fmt.month(cmp.month)} against your baseline`), h('span', { class: 'sp' }),
      h('span', {}, badge(`${cmp.total} points, ${cmp.band}`, bandTone(bandCode(cmp.band))), h('span', { class: cmp.delta > 0 ? 'bad' : cmp.delta < 0 ? 'good' : 'muted', style: { marginLeft: '8px' } }, cmp.delta === 0 ? 'same as baseline' : `${cmp.delta > 0 ? '+' : ''}${cmp.delta} vs baseline ${b.total}`))),
      h('div', { class: 'tw' }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, h('th', {}, 'Dimension'), h('th', { class: 'r' }, 'Baseline'), h('th', { class: 'r' }, 'PM'), h('th', { class: 'r' }, 'Difference'), h('th', {}, 'PM\'s note'))),
        h('tbody', {}, dims.map((x) => { const last = rows.filter((r) => r.scores?.[x.key]).pop(); const dv = cmp.by_dimension[x.key];
          return h('tr', {}, h('td', {}, x.label), h('td', { class: 'r' }, String(b.scores[x.key].score)), h('td', { class: 'r' }, String(last.scores[x.key].score)),
            h('td', { class: 'r ' + (dv > 0 ? 'bad' : dv < 0 ? 'good' : 'muted') }, dv ? (dv > 0 ? '+' : '') + dv : '0'), h('td', { class: 'small wrap' }, last.scores[x.key].note || '')); }))))));
  }
  const lastRow = [...rows].reverse().find((r) => r.scores && Object.keys(r.scores).length);
  if (b && lastRow) { const rb = h('div', { style: { height: '420px', maxWidth: '680px', margin: '0 auto' } }); body.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('h2', {}, 'Complexity profile: your baseline and the PM\'s latest'), rb)); setTimeout(() => radar(rb, d.dimensions, [{ label: `Your baseline (${b.total})`, scores: b.scores, colour: PALETTE[0] }, { label: `PM, ${fmt.month(lastRow.month)} (${lastRow.total})`, scores: lastRow.scores, colour: PALETTE[1] }]), 30); }
  body.append(h('div', { class: 'card' }, h('h2', {}, 'The PM\'s assessments over time'), history(d, rows, true),
    h('div', { class: 'tw', style: { marginTop: '8px' } }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Month', 'Total', 'Band', 'Against baseline', 'Client PM', 'Client difficulty', 'Note', 'By'].map((x) => h('th', {}, x)))),
      h('tbody', {}, [...rows].reverse().map((r) => h('tr', {}, h('td', {}, fmt.month(r.month)), h('td', { class: 'r' }, r.total != null ? String(r.total) : `${r.complexity} (1 to 5)`), h('td', {}, r.band ? badge(r.band, bandTone(bandCode(r.band))) : ''),
        h('td', { class: 'r' }, b && r.total != null ? `${r.total - b.total > 0 ? '+' : ''}${r.total - b.total}` : ''), h('td', {}, r.client_pm || ''), h('td', {}, r.pm_difficulty ? `${r.pm_difficulty} · ${DIFFICULTY[r.pm_difficulty]}` : ''), h('td', { class: 'small wrap' }, r.note || ''), h('td', { class: 'small muted' }, r.by || ''))))))));
}

function monthlyTab(body, d, params) {
  const rows = d.assessments;
  const month = h('input', { type: 'month', value: params.month || statusMonth() });
  const last = [...rows].reverse().find((r) => r.scores && Object.keys(r.scores).length);
  const hint = {}; if (last) Object.entries(last.scores).forEach(([k, v]) => { hint[k] = v.score; });
  const own = rows.find((r) => r.month === month.value);
  // a new month starts from last month's scores, without last month's notes
  const carry = last ? Object.fromEntries(Object.entries(last.scores).map(([k, v]) => [k, { score: v.score, note: '' }])) : undefined;
  const sc = scorer(d, own?.scores && Object.keys(own.scores).length ? own.scores : carry, { hint, label: `${fmt.month(month.value)} (this assessment)`, ghost: last ? { label: `${fmt.month(last.month)} (last)`, scores: last.scores, colour: PALETTE[3], dashed: true } : null });
  const pm = h('input', { type: 'text', value: (own || last)?.client_pm || state.project.client_pm || '', placeholder: 'Client project manager' });
  const diff = select([['', '(not rated)'], ...Object.entries(DIFFICULTY).map(([k, v]) => [k, `${k} · ${v}`])], (own || last)?.pm_difficulty ?? '');
  const note = h('input', { type: 'text', value: own?.note || '', placeholder: 'What changed this month (optional)' });
  month.onchange = () => go('complexity', { tab: 'monthly', month: month.value });
  body.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, `Assessment for ${fmt.month(month.value)}`), h('span', { class: 'sp' }), own ? badge('Saved: saving again replaces it', 'good') : null),
    h('div', { class: 'small muted', style: { marginBottom: '8px' } }, last ? 'Scores start from your last assessment: change only what moved.' : 'Score each dimension as you see the project today.'),
    h('div', { class: 'grid g4', style: { marginBottom: '10px' } }, field('Month', month), field('Client PM', pm), field('Client difficulty', diff, 'How hard the client is to work with'), h('span')),
    sc.el, field('Note', note),
    h('div', { style: { marginTop: '10px' } }, h('button', { class: 'btn', onclick: async () => {
      if (!sc.complete()) { toast('Score every dimension from 0 to 5 first', 'bad'); return; }
      try { await api.put(p('/complexity/assessment'), { month: month.value, scores: sc.scores(), client_pm: pm.value, pm_difficulty: diff.value, note: note.value }); toast('Assessment saved'); await render(); } catch (e) { toast(e.message, 'bad'); }
    } }, 'Save assessment'))));
  if (rows.length) body.append(h('div', { class: 'card', style: { marginTop: '14px' } }, h('h2', {}, 'Your assessments over time'), history(d, rows, false),
    h('div', { class: 'tw', style: { marginTop: '8px' } }, h('table', { class: 't nogroup notools' }, h('thead', {}, h('tr', {}, ['Month', 'Total', 'Band', 'Client difficulty', 'Note'].map((x) => h('th', {}, x)))),
      h('tbody', {}, [...rows].reverse().map((r) => h('tr', { class: 'click', onclick: () => go('complexity', { tab: 'monthly', month: r.month }) }, h('td', {}, fmt.month(r.month)), h('td', { class: 'r' }, r.total != null ? String(r.total) : `${r.complexity} (1 to 5)`),
        h('td', {}, r.band ? badge(r.band, bandTone(bandCode(r.band))) : ''), h('td', {}, r.pm_difficulty ? `${r.pm_difficulty} · ${DIFFICULTY[r.pm_difficulty]}` : ''), h('td', { class: 'small wrap' }, r.note || ''))))))));
}
