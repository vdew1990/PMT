import { h, fmt, modal, toast, field, select, table, num, empty, debounce } from '../ui.js';
import { api, p } from '../api.js';
import { render } from '../app.js';

// Allowance: link each resource to an allowance bucket (a CBS group). The link is the starting point of the ledger;
// later movements are ordinary transfers on Cost control and CBS and allowances.
const OPTS = [
  [1, 'Option 1: no cost yet', 'You set the initial budget the resource draws from the bucket. It cannot draw more than the bucket has left.'],
  [2, 'Option 2: cover the cost so far', 'The cost already posted is covered automatically. If the bucket cannot cover it all, the line gets what is left.'],
  [3, 'Option 3: cover the cost, plus more', 'The cost already posted is covered as a floor, and you add an amount for future costs. The total cannot exceed the bucket.'],
];
const STATE = { cost_no_line: 'Has cost, no line yet', unfunded_line: 'Line without enough allowance' };

export default async function allowance(root) {
  const ov = await api.get(p('/allowance/overview'));
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Allowance'),
    h('div', { class: 'sub' }, 'Link resources to allowance buckets. Each link is posted to the ledger as the starting point; later movements are transfers.')),
    h('span', { class: 'sp' }), h('button', { class: 'btn', onclick: () => linkDialog(ov, {}) }, 'Link a resource...')));
  allowanceBody(root, ov);
}

// the buckets and the resources to link: the Allowance page, and the Allowance step of Project setup
const sel = new Set(); const ui = { empty: false };
export function allowanceBody(root, ov) {
  const bname = (id) => { const b = ov.buckets.find((x) => x.id === id); return b ? `${b.code} ${b.name}` : ''; };
  const live = ov.buckets.filter((b) => Math.abs(b.budget) > 0.5 || Math.abs(b.parked) > 0.5);
  const shown = ui.empty ? ov.buckets : live;
  const bucketCard = (h('div', { class: 'card', style: { marginTop: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, `Allowance buckets (${shown.length}${shown.length < ov.buckets.length ? ' of ' + ov.buckets.length : ''})`), h('span', { class: 'sp' }),
    ov.buckets.length > live.length || ui.empty ? h('label', { class: 'small' }, h('input', { type: 'checkbox', checked: ui.empty, style: { width: 'auto', marginRight: '4px' }, onchange: (e) => { ui.empty = e.target.checked; render(); } }), `Show the ${ov.buckets.length - live.length} empty buckets`) : null),
    h('div', { class: 'small muted', style: { marginBottom: '8px' } }, 'A bucket is the allowance a CBS group holds itself, not yet moved to a named line. Cost already posted to the group counts against it. Buckets with nothing held and nothing parked are hidden.'),
    shown.length ? table([
      { label: 'CBS', f: (b) => b.code, cls: 'mono' }, { label: 'Name', f: (b) => b.name },
      { label: 'Held', f: (b) => fmt.money(b.budget), r: true, sort: (b) => b.budget },
      { label: 'Cost parked on it', f: (b) => fmt.money(b.parked), r: true, sort: (b) => b.parked },
      { label: 'Left to draw', f: (b) => fmt.money(b.available), r: true, sort: (b) => b.available },
      { label: '', f: (b) => h('button', { class: 'btn ghost sm', onclick: () => linkDialog(ov, { bucket_id: b.id }) }, 'Link...') }], shown)
      : empty('No buckets with allowance', ov.buckets.length ? 'Every bucket is empty. Tick "Show the empty buckets" to see them.' : 'Enter proposal allowances on CBS and allowances first.')));

  const rows = ov.resources; const key = (r) => `${r.kind}:${r.code || ''}:${r.line_id || ''}:${r.bucket_id || ''}`;   // the same company can have cost in two categories
  for (const k of [...sel]) if (!rows.some((r) => key(r) === k)) sel.delete(k);
  const bar = h('div', { class: 'note', style: { marginBottom: '8px', display: 'none', alignItems: 'center', gap: '8px' } });
  const pick = select([['', 'Each into its suggested bucket'], ...ov.buckets.map((b) => [b.id, `${b.code} ${b.name} (left ${fmt.money(b.available)})`])], '');
  const drawBar = () => {
    const chosen = rows.filter((r) => sel.has(key(r)));
    bar.style.display = chosen.length ? 'flex' : 'none'; bar.replaceChildren();
    if (!chosen.length) return;
    const noSug = chosen.filter((r) => !r.bucket_id).length;
    bar.append(...[h('b', {}, `${chosen.length} selected`), pick,
      h('button', { class: 'btn sm', title: 'The cost already posted is covered, and the line gets that much from the bucket (option 2)', onclick: async () => {
        const o = await api.post(p('/allowance/link-many'), { option: 2, bucket_id: pick.value ? +pick.value : null, rows: chosen.map((r) => ({ kind: r.kind, code: r.code, name: r.name, function: r.function, line_id: r.line_id, bucket_id: pick.value ? +pick.value : r.bucket_id })) });
        sel.clear(); toast((o.draw < 1 && o.linked ? `${o.linked} linked, but their buckets had nothing left to draw: move allowance into the bucket first` : `${o.linked} linked, ${fmt.money(o.draw)} drawn from the buckets`) + (o.skipped.length ? `; ${o.skipped.length} left (${o.skipped[0].why})` : ''), o.skipped.length || o.draw < 1 ? 'bad' : undefined); render();
      } }, 'Cover cost so far'),
      h('a', { onclick: () => { sel.clear(); drawBar(); redrawBoxes(); } }, 'Clear'),
      noSug && !pick.value ? h('span', { class: 'small muted' }, `${noSug} have no suggested bucket: choose one.`) : null].filter(Boolean));
  };
  const boxes = [];
  const redrawBoxes = () => boxes.forEach((b) => { b.checked = sel.has(b.dataset.k); });
  const tick = (r) => { const b = h('input', { type: 'checkbox', 'data-k': key(r), checked: sel.has(key(r)), style: { width: 'auto' }, onclick: (e) => e.stopPropagation(), onchange: (e) => { e.target.checked ? sel.add(key(r)) : sel.delete(key(r)); drawBar(); } }); boxes.push(b); return b; };
  const all = h('input', { type: 'checkbox', style: { width: 'auto' }, title: 'Select every resource', onchange: (e) => { rows.forEach((r) => (e.target.checked ? sel.add(key(r)) : sel.delete(key(r)))); redrawBoxes(); drawBar(); } });
  root.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, `Resources to link (${rows.length})`), h('span', { class: 'sp' }), rows.length ? h('label', { class: 'small' }, all, ' Select all') : null), bar,
    rows.length ? table([
      { label: '', f: tick },
      { label: 'Status', f: (r) => STATE[r.state] || r.state }, { label: 'Code', f: (r) => r.code || '', cls: 'mono' }, { label: 'Name', f: (r) => r.name || '' },
      { label: 'Cost so far', f: (r) => fmt.money(r.cost), r: true, sort: (r) => r.cost },
      { label: 'Allowance now', f: (r) => (r.allowance == null ? '' : fmt.money(r.allowance)), r: true },
      { label: 'Bucket (suggested from its function)', f: (r) => bname(r.bucket_id) || h('span', { class: 'muted' }, 'none suggested') },
      { label: '', f: (r) => h('button', { class: 'btn sm', onclick: () => linkDialog(ov, r) }, 'Link...') }], rows)
      : h('div', { class: 'good' }, 'Every resource with cost has a line with allowance. Use "Link a resource" for a new one.')));
  root.append(bucketCard);   // the resources to link come first: they are the job; the buckets are what they draw from
  drawBar();
}

function linkDialog(ov, r) {
  const bucket = select(ov.buckets.map((b) => [b.id, `${b.code} ${b.name} (left ${fmt.money(b.available)})`]), r.bucket_id || (ov.buckets.find((b) => b.available > 0) || ov.buckets[0])?.id);
  const kind = select([['supplier', 'Company (subcontractor, supplier)'], ['employee', 'Employee']], r.kind || 'supplier');
  const code = h('input', { type: 'text', value: r.code || '', placeholder: 'Pronto code' });
  const name = h('input', { type: 'text', value: r.name || '' });
  const amount = h('input', { type: 'text', inputmode: 'decimal', placeholder: '0' });
  const known = !!(r.code || r.line_id);
  if (known) [kind, code, name].forEach((x) => (x.disabled = true));
  if (r.line_id) bucket.disabled = true;
  let option = r.cost > 1 ? 2 : 1;
  const radios = OPTS.map(([n, t, d]) => h('label', { style: { display: 'flex', flexDirection: 'row', alignItems: 'flex-start', gap: '8px', marginBottom: '8px', cursor: 'pointer' } },
    h('input', { type: 'radio', name: 'alw-opt', value: n, checked: n === option, style: { width: 'auto', marginTop: '3px' }, onchange: () => { option = n; sync(); } }),
    h('span', {}, h('b', {}, t), h('div', { class: 'small muted' }, d))));
  const box = h('div', { class: 'note' });
  const args = () => ({ bucket_id: +bucket.value, kind: kind.value, code: code.value.trim(), name: name.value.trim() || undefined, option, amount: num(amount.value), line_id: r.line_id || undefined });
  const q = (a) => new URLSearchParams(Object.fromEntries(Object.entries(a).filter(([, v]) => v !== undefined && v !== ''))).toString();
  const show = debounce(async () => {
    const a = args();
    if (!a.code && !a.line_id) { box.textContent = 'Choose or type the resource to see what the link does.'; return; }
    try {
      const o = await api.get(p('/allowance/preview?' + q(a)));
      box.textContent = '';
      box.append(h('div', {}, `Cost so far: ${fmt.money(o.cost)}. Bucket has ${fmt.money(o.bucket_left)} left.`),
        h('div', {}, h('b', {}, `The resource draws ${fmt.money(o.draw)}`), ` (${fmt.money(o.line_allowance_after)} on its line); the bucket keeps ${fmt.money(o.bucket_after)}.`),
        o.uncovered > 0 ? h('div', { class: 'bad' }, `${fmt.money(o.uncovered)} of its cost is not covered because the bucket has run out.`) : '');
    } catch (e) { box.textContent = e.message || String(e); }
  }, 250);
  const sync = () => { amountField.style.display = option === 2 ? 'none' : ''; show(); };
  [bucket, kind, code, name, amount].forEach((x) => x.addEventListener('input', show));
  bucket.addEventListener('change', show);
  const amountField = field(option === 3 ? 'Extra for future costs' : 'Initial budget', amount, 'Dollars drawn from the bucket');
  modal({ title: 'Link a resource to an allowance bucket', wide: true,
    body: h('div', { class: 'grid' }, field('Allowance bucket', bucket),
      h('div', { class: 'grid g3' }, field('Resource type', kind), field('Pronto code', code), field('Name', name)),
      h('div', {}, radios), amountField, box),
    actions: [{ label: 'Cancel', kind: 'ghost', onClick: () => {} }, { label: 'Link', onClick: async () => {
      const o = await api.post(p('/allowance/link'), args());
      toast(`Linked: ${fmt.money(o.draw)} moved from the bucket to the resource`); render();
    } }] });
  setTimeout(sync, 0);
}
