import { h, clear, fmt, modal, toast, field, select, table, num, confirmBox, badge, empty, debounce } from '../ui.js';
import { api, state, p, loadRows } from '../api.js';
import { pickNode } from '../scope.js';
import { go, render } from '../app.js';

// after the schedule moves a line's activity window: typed (MANUAL) months that now sit outside it. They are kept, never cleared.
function warnWindows(list) {
  if (!list || !list.length) return;
  modal({ title: `Typed forecast months outside the new activity window (${list.length} lines)`, size: 'wide', body: h('div', {},
    h('div', { class: 'note warn', style: { marginBottom: '10px' } }, 'The schedule moved the activity window of these lines. Their typed (MANUAL) months were kept as they were. The months outside the window are outlined on Cost control: move them, clear them, or set the window by hand on that line.'),
    table([{ label: 'CBS', f: (x) => x.code, cls: 'mono' }, { label: 'Line', f: (x) => x.name }, { label: 'New window', f: (x) => `${fmt.month(x.start)} to ${fmt.month(x.end)}` }, { label: 'Typed months outside it', f: (x) => x.months.map((m) => fmt.month(m)).join(', ') }], list)),
    actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }, { label: 'Open Cost control', onClick: () => go('costcontrol') }] });
}


// The drop zone for a project schedule file (MS Project .mpp or XML, Excel, CSV or PDF). Used here and on Project setup > Project schedule.
export function scheduleDrop(onDone, layer = 'internal') {
  const file = h('input', { type: 'file', accept: '.xml,.xlsx,.xlsm,.csv,.pdf,.mpp', class: 'hide' });
  const dz = h('div', { class: 'dz' }, h('b', {}, layer === 'upstream' ? 'Drop the upstream schedule here, or click to choose' : 'Drop the internal project schedule here, or click to choose'), h('div', { class: 'small' }, 'An MS Project file (.mpp, needs Java on this PC) or MS Project XML, an Excel or CSV task list, or a PDF print of the project schedule. PDFs are read on a best-effort basis, so check the task list below.'));
  dz.onclick = () => file.click();
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add('over'); }; dz.ondragleave = () => dz.classList.remove('over');
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove('over'); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); };
  file.onchange = () => file.files[0] && upload(file.files[0]);
  async function upload(f) {
    toast('Reading ' + f.name + (/\.mpp$/i.test(f.name) ? '... the first MS Project file can take a minute while PMT prepares its reader' : '...'));
    try { const r = await api.upload(p('/programme/upload?layer=' + layer), f); toast(`${r.tasks} tasks read from ${r.source.toUpperCase()}; ${r.relinked || 0} links kept, ${r.auto_linked} linked by name; ${r.windows || 0} activity windows updated${r.windows_kept ? `, ${r.windows_kept} kept (set by hand)` : ''}`); if (onDone) await onDone(r); else await render(); warnWindows(r.warnings); } catch (e) { toast(e.message, 'bad'); }
  }
  return h('div', {}, dz, file);
}

// Optional schedule upload. The schedule is a starting point for dates; every date can still be typed by hand.
async function updatePage(root) {
  const data = await loadRows();
  const allTasks = await api.get(p('/programme/tasks'));
  const tasks = allTasks.filter((t) => t.layer !== 'upstream'); const upTasks = allTasks.filter((t) => t.layer === 'upstream');
  const upInfo = state.project.settings?.programme_file_upstream;
  const contract = await api.get(p('/contract'));
  const leaves = contract.items.filter((i) => i.is_leaf && i.kind !== 'variation');
  const lines = data.rows.filter((r) => r.kind === 'line');
  const info = state.project.settings?.programme_file;
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Update project schedule'), h('div', { class: 'sub' }, 'Upload a new version of the internal or the client schedule, link its tasks and apply their dates to the claim schedule and the cost forecast. Every date can still be edited by hand.')), h('div', { class: 'sp' }), h('button', { class: 'btn ghost', onclick: () => go('programme') }, '\u2190 Back to the schedule')));

  // ---- where dates stand in the claim schedule and the cost forecast (not the project schedule itself) ----
  root.append(h('h3', { style: { margin: '4px 0 8px' } }, 'What the schedule feeds: claim schedule and cost forecast dates'));
  const sovDated = leaves.filter((i) => i.start_date).length;
  const linesDated = lines.filter((r) => r.start_own || r.end_own || r.start).length;
  const ownDated = lines.filter((r) => r.start_own).length;
  root.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } },
    kpi('Claim items with dates', `${sovDated} of ${leaves.length}`, leaves.length - sovDated ? `${leaves.length - sovDated} will not be scheduled` : 'All scheduled'), kpi('CBS lines with their own dates', `${ownDated} of ${lines.length}`, 'Others inherit from their group, else the project dates', 't2'),
    kpi('Project schedule tasks loaded', String(tasks.length), info ? `${info.name} (${info.source.toUpperCase()})` : 'No project schedule uploaded', 't3'), kpi('Tasks linked', String(tasks.filter((t) => t.link_item_id || t.link_node_id).length), 'To a claim item or a CBS line', 't4')));

  // how much of the cost forecast follows the schedule, and which lines do not
  const lk = await api.get(p('/programme/links')).catch(() => ({ span: [], anchors: [] }));
  const driven = new Set([...lk.span.map((x) => x.node_id), ...lk.anchors.filter((x) => !x.suspended).map((x) => x.node_id)]);
  const real = lines.filter((r) => !['ctc', 'wip'].includes(r.origin) && !String(r.name || '').includes('(Unallocated)'));
  const loose = real.filter((r) => !driven.has(r.node_id ?? r.id));
  root.append(h('details', { style: { margin: '-4px 0 14px' } }, h('summary', { style: { cursor: 'pointer', fontWeight: 700, color: 'var(--navy)' } }, `${real.length - loose.length} of ${real.length} cost lines follow the schedule`, loose.length ? h('span', { class: 'muted small', style: { fontWeight: 400, marginLeft: '8px' } }, `${loose.length} are set by hand: open to see them`) : null),
    loose.length ? h('div', { class: 'tw', style: { maxHeight: '260px', marginTop: '8px' } }, table([{ label: 'CBS', f: (r) => h('span', { class: 'mono' }, r.code) }, { label: 'Line', f: (r) => r.name }, { label: 'Start', f: (r) => r.start ? fmt.date(r.start) : '' }, { label: 'End', f: (r) => r.end ? fmt.date(r.end) : '' },
      { label: '', f: (r) => h('button', { class: 'btn ghost sm', onclick: () => go('costcontrol', { node: r.node_id ?? r.id }) }, 'Open on Cost control') }], loose)) : h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'Every cost line is driven by the schedule.')));

  // ---- two ways in -------------------------------------------------------------------------------
  root.append(h('div', { class: 'grid g2', style: { marginBottom: '14px' } },
    h('div', { class: 'card' }, h('h2', {}, '1. Internal project schedule (optional)'), h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'EPEC\'s own schedule. This one drives the claim schedule and cost forecast dates.'), scheduleDrop(),
      h('h2', { style: { marginTop: '14px' } }, 'Upstream project schedule (optional)'), h('div', { class: 'small muted', style: { marginBottom: '6px' } }, 'The client or head contract schedule, kept for reference and comparison. It does not change any dates.'), scheduleDrop(null, 'upstream')),
    h('div', { class: 'card' }, h('h2', {}, '2. No internal project schedule? Set dates by hand'),
      h('p', { class: 'muted' }, 'Give each CBS line its start and end. A group\'s dates apply to every line below it that has none of its own, so one entry can cover a whole discipline. The same works for the claim schedule items.'),
      h('div', { class: 'row' }, h('button', { class: 'btn', onclick: () => go('cbs') }, 'Dates on CBS lines'), h('button', { class: 'btn ghost', onclick: () => go('revenue', { tab: 'contract' }) }, 'Dates on claim items')),
      h('div', { class: 'note', style: { marginTop: '12px' } }, 'Items with no dates use the project start and end for costs, and are left out of the claim schedule until they are given dates.'))));

  if (upTasks.length) root.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, `Upstream schedule (${upTasks.length} tasks${upInfo ? ', ' + upInfo.name : ''})`), h('span', { class: 'sp' }),
      h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox('Remove the upstream schedule?', 'Remove', true)) { await api.del(p('/programme?layer=upstream')); render(); } } }, 'Remove upstream schedule')),
      h('div', { class: 'tw', style: { maxHeight: '36vh' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['WBS', 'Task', 'Start', 'Finish'].map((c) => h('th', {}, c)))),
        h('tbody', {}, upTasks.map((t) => h('tr', { class: t.summary ? 'par' : '' }, h('td', { class: 'mono muted' }, t.wbs || ''), h('td', { style: { paddingLeft: 9 + (t.outline - 1) * 14 + 'px' } }, t.name, t.milestone ? badge('milestone', 'warn') : null), h('td', {}, fmt.date(t.start_date)), h('td', {}, fmt.date(t.finish_date)))))))));
  if (!tasks.length) return;

  // ---- task list ---------------------------------------------------------------------------------
  let q = ''; let showSummary = true;
  const wrap = h('div');
  const itemOpts = [['', '(not linked)'], ...leaves.map((i) => [i.id, `${i.ref || ''} ${i.description}`.trim()])];
  const search = h('input', { type: 'search', placeholder: 'Search tasks...', style: { width: '240px' }, oninput: debounce(() => { q = search.value.toLowerCase(); draw(); }, 150) });
  const only = h('input', { type: 'checkbox', checked: false });
  root.append(h('div', { class: 'card' }, h('div', { class: 'ch' }, h('h2', {}, 'Project schedule tasks'), h('span', { class: 'sp' }),
    h('button', { class: 'btn ghost sm', onclick: async () => { const r = await api.post(p('/programme/auto-link')); toast(`${r.linked} tasks linked by name`); render(); } }, 'Link by name'),
    h('button', { class: 'btn ghost sm', onclick: async () => { const r = await api.post(p('/programme/to-milestones'), {}); toast(`${r.created} milestones and phases copied to the project programme`); } }, 'Copy milestones to project'),
    h('button', { class: 'btn danger sm', onclick: async () => { if (await confirmBox('Remove the uploaded project schedule? Dates already applied stay as they are.', 'Remove', true)) { await api.del(p('/programme')); render(); } } }, 'Remove programme')),
    h('div', { class: 'note', style: { marginBottom: '10px' } }, 'Link each task to the claim item it drives and/or the CBS line or group it drives. Several tasks on one target widen it to the earliest start and the latest finish. Apply copies the dates across; nothing changes until you press an Apply button.'),
    h('div', { class: 'row', style: { marginBottom: '10px' } }, search, h('label', { class: 'row small' }, h('input', { type: 'checkbox', checked: true, onchange: (e) => { showSummary = e.target.checked; draw(); } }), 'Show summary tasks'),
      h('span', { class: 'sp', style: { flex: 1 } }),
      h('label', { class: 'row small' }, only, 'Only where no date is set yet'),
      h('button', { class: 'btn', onclick: () => apply(['claims']) }, 'Apply to claim schedule'), h('button', { class: 'btn', onclick: () => apply(['costs']) }, 'Apply to cost forecast'), h('button', { class: 'btn', onclick: () => apply(['claims', 'costs']) }, 'Apply to both')), wrap));
  async function apply(targets) {
    const r = await api.post(p('/programme/apply'), { targets, only_empty: only.checked });
    toast(`${r.items} claim items and ${r.nodes} CBS items now carry project schedule dates${r.kept ? `; ${r.kept} CBS items kept their own window (set by hand)` : ''}`); render(); warnWindows(r.warnings);
  }
  function draw() {
    const l = tasks.filter((t) => (showSummary || !t.summary) && (!q || `${t.wbs} ${t.name}`.toLowerCase().includes(q)));
    clear(wrap).append(h('div', { class: 'tw', style: { maxHeight: '62vh' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['WBS', 'Task', 'Start', 'Finish', 'Drives claim item', 'Drives CBS line or group'].map((x) => h('th', {}, x)))),
      h('tbody', {}, l.map((t) => h('tr', { class: t.summary ? 'par' : '' },
        h('td', { class: 'mono muted' }, t.wbs || ''), h('td', { style: { paddingLeft: 9 + (t.outline - 1) * 14 + 'px' } }, t.name, t.milestone ? badge('milestone', 'warn') : null),
        h('td', { class: 'in' }, h('input', { type: 'date', value: t.start_date || '', onchange: (e) => saveTask(t, { start_date: e.target.value }) })), h('td', { class: 'in' }, h('input', { type: 'date', value: t.finish_date || '', onchange: (e) => saveTask(t, { finish_date: e.target.value }) })),
        h('td', {}, select(itemOpts, t.link_item_id || '', { onchange: (e) => saveTask(t, { link_item_id: e.target.value ? +e.target.value : null }), style: { maxWidth: '260px' } })),
        h('td', {}, h('button', { class: 'btn ghost sm', onclick: () => pickNode({ title: `Link "${t.name}" to a CBS item`, kinds: ['line', 'group'], onPick: (r) => saveTask(t, { link_node_id: r.node_id }, true) }) }, t.node_code ? `${t.node_code} ${t.node_name}` : 'Choose...'), t.link_node_id ? h('button', { class: 'btn danger sm', style: { marginLeft: '4px' }, onclick: () => saveTask(t, { link_node_id: null }, true) }, '×') : null)))))));
  }
  async function saveTask(t, patch, reload) { const r = await api.put(p(`/programme/tasks/${t.id}`), patch); Object.assign(t, patch); if (reload) render(); warnWindows(r.warnings); }
  draw();
  function kpi(l, v, s, c = '') { return h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s)); }
}



// click a schedule item: the CBS lines it drives (the whole window, or just Start or Stop), with links to add and remove
async function drivesDialog(t, onChange) {
  const L = await api.get(p('/programme/links'));
  const mine = [...L.span.filter((x) => x.task_id === t.id).map((x) => ({ ...x, role: 'span' })), ...L.anchors.filter((x) => x.task_id === t.id)];
  const what = (x) => (x.role === 'span' ? 'Whole window: start to finish' : `${x.role === 'start' ? 'Start' : 'Stop'} follows its ${x.edge === 'start' ? (t.milestone ? 'date' : 'start') : 'finish'}`);
  const role = select([['span', 'Whole window (start to finish)'], ['start', 'Start only'], ['stop', 'Stop only'], ['both', 'Start and Stop (same item)']], 'span');
  const edge = select([['start', 'its start date'], ['finish', 'its finish date']], t.milestone ? 'start' : 'start');
  const box = h('div');
  const md = modal({ title: `${t.name}: what it drives`, size: 'wide', body: h('div', {},
    h('div', { class: 'small muted', style: { marginBottom: '8px' } }, `${fmt.date(t.start_date)}${t.milestone ? '' : ' to ' + fmt.date(t.finish_date)}. A CBS line follows this item through its activity window. Lines can also be left unlinked and set by hand on Cost control.`), box,
    h('div', { class: 'card', style: { marginTop: '12px' } }, h('h3', { style: { margin: '0 0 6px' } }, 'Link a CBS line'), h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap' } }, role, edge,
      h('button', { class: 'btn', onclick: () => pickNode({ title: `Link "${t.name}" to a CBS item`, kinds: ['line', 'group'], onPick: async (r) => { const o = await api.post(p('/programme/links'), { task_id: t.id, node_id: r.node_id, role: role.value, edge: edge.value }); md.close(); toast('Linked'); if (onChange) await onChange(o); } }) }, 'Choose CBS line...')))),
    actions: [{ label: 'Close', kind: 'ghost', onClick: () => {} }] });
  const draw = () => clear(box).append(mine.length ? table([
    { label: 'CBS', f: (x) => `${x.code} ${x.name}` }, { label: 'Drives', f: (x) => what(x) },
    { label: '', f: (x) => (x.suspended ? badge('Typed over on Cost control', 'navy') : '') },
    { label: '', f: (x) => h('button', { class: 'btn danger sm', onclick: async () => { await api.del(p(`/programme/links?task_id=${t.id}&node_id=${x.node_id}&role=${x.role}`)); mine.splice(mine.indexOf(x), 1); draw(); if (onChange) onChange(); } }, 'Unlink') }], mine) : h('div', { class: 'muted' }, 'Drives no CBS line yet.'));
  draw();
}

const DAY = 86400000;
const t0 = (d) => (d ? Date.parse(d) : NaN);

// FORECAST > Project schedule: the schedule as it stands (internal first, client version one click away), with a download of
// the file that was uploaded. Uploading a new version and linking tasks to the claim schedule is under Update.
export default async function schedule(root, params = {}) {
  if (params.view === 'update') return updatePage(root);
  const layer = params.layer === 'upstream' ? 'upstream' : 'internal';
  const [all, fi, links] = await Promise.all([api.get(p('/programme/tasks')), api.get(p(`/programme/file?layer=${layer}&info=1`)), api.get(p('/programme/links'))]);
  const drives = {}; [...links.span, ...links.anchors].forEach((x) => { (drives[x.task_id] ||= new Set()).add(x.code); });
  const tasks = all.filter((t) => (layer === 'upstream') === (t.layer === 'upstream'));
  const other = all.filter((t) => (layer === 'upstream') !== (t.layer === 'upstream')).length;
  const info = state.project.settings?.[layer === 'upstream' ? 'programme_file_upstream' : 'programme_file'];
  const name = layer === 'upstream' ? 'Client schedule' : 'Internal schedule';
  const seg = (k, label) => h('button', { class: 'btn sm' + (layer === k ? '' : ' ghost'), onclick: () => go('programme', k === 'upstream' ? { layer: 'upstream' } : {}) }, label);
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Project schedule'), h('div', { class: 'sub' }, `${state.project.name}: the ${layer === 'upstream' ? 'client (upstream)' : 'internal'} schedule as loaded.`)), h('div', { class: 'sp' }),
    h('div', { class: 'row', style: { gap: '6px' } }, seg('internal', 'Internal schedule'), seg('upstream', 'Client schedule'))));
  const dated = tasks.filter((t) => t.start_date && t.finish_date);
  const lo = Math.min(...dated.map((t) => t0(t.start_date))); const hi = Math.max(...dated.map((t) => t0(t.finish_date)));
  const tile = (l, v, sub, cls = '') => h('div', { class: 'kpi ' + cls }, h('div', { class: 'l' }, l), h('div', { class: 'v', style: { fontSize: '19px' } }, v), h('div', { class: 's' }, sub));
  root.append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } },
    tile('Tasks', String(tasks.length), tasks.length ? `${tasks.filter((t) => t.milestone).length} milestones` : 'Nothing loaded yet', 't3'),
    tile('Starts', dated.length ? fmt.date(new Date(lo).toISOString().slice(0, 10)) : 'n/a', 'first task'), tile('Finishes', dated.length ? fmt.date(new Date(hi).toISOString().slice(0, 10)) : 'n/a', 'last task'),
    tile('Source file', info ? info.name : 'None', info ? `${info.source.toUpperCase()}, ${info.tasks} tasks${fi.uploaded_at ? ', loaded ' + fmt.date(fi.uploaded_at.slice(0, 10)) : ''}` : 'Upload one under Update')));
  const upd = h('div', { class: 'kpi click', style: { cursor: 'pointer', borderTopColor: 'var(--orange)' }, title: 'Upload a new version, link tasks and apply dates', onclick: () => go('programme', { view: 'update' }) },
    h('div', { class: 'l' }, 'Update'), h('div', { class: 'v', style: { fontSize: '17px' } }, 'Upload or update the schedule'), h('div', { class: 's' }, 'New version, task links, apply to claim schedule and forecast'));
  root.append(h('div', { class: 'row', style: { gap: '10px', marginBottom: '14px', alignItems: 'stretch' } }, h('div', { style: { flex: 1 } }, upd),
    fi.has_file ? h('a', { class: 'btn', href: p(`/programme/file?layer=${layer}`), style: { alignSelf: 'center' }, title: `Download ${fi.filename} as uploaded` }, `Download ${fi.filename}`)
      : h('span', { class: 'small muted', style: { alignSelf: 'center' } }, tasks.length ? 'The original file was not kept for this version. Upload it again under Update to download it.' : '')));
  if (!tasks.length) {
    root.append(empty(`No ${name.toLowerCase()} loaded`, other ? `The ${layer === 'upstream' ? 'internal' : 'client'} schedule has ${other} tasks: use the buttons above to switch.` : 'Use Update to upload an MS Project file, Excel or PDF. If the schedule was set up in Project setup it shows here.'));
    return;
  }
  const span = Math.max(DAY, hi - lo);
  const bar = (t) => {
    if (!t.start_date || !t.finish_date) return h('div', { class: 'gx' });
    const l = ((t0(t.start_date) - lo) / span) * 100; const w = Math.max(0.6, ((t0(t.finish_date) - t0(t.start_date)) / span) * 100);
    return h('div', { class: 'gx' }, t.milestone ? h('span', { class: 'gms', style: { left: l + '%' }, title: `${t.name}: ${fmt.date(t.start_date)}` }) : h('span', { class: 'gbar' + (t.summary ? ' sum' : ''), style: { left: l + '%', width: Math.min(w, 100 - l) + '%' }, title: `${t.name}: ${fmt.date(t.start_date)} to ${fmt.date(t.finish_date)}` }));
  };
  let q = ''; let showSummary = true;
  const wrap = h('div');
  const draw = () => {
    const rows = tasks.filter((t) => (showSummary || !t.summary) && (!q || `${t.wbs} ${t.name}`.toLowerCase().includes(q)));
    clear(wrap).append(h('div', { class: 'tw', style: { maxHeight: '70vh' } }, h('table', { class: 't' }, h('thead', {}, h('tr', {}, ['WBS', 'Task', 'Start', 'Finish', 'Drives CBS', 'Timeline'].map((c) => h('th', {}, c)))),
      h('tbody', {}, rows.map((t) => h('tr', { class: (t.summary ? 'par ' : '') + 'click', onclick: () => drivesDialog(t, () => render()) }, h('td', { class: 'mono muted' }, t.wbs || ''), h('td', { style: { paddingLeft: 9 + ((t.outline || 1) - 1) * 14 + 'px' } }, t.name, t.milestone ? badge('milestone', 'warn') : null),
        h('td', {}, fmt.date(t.start_date)), h('td', {}, fmt.date(t.finish_date)), h('td', { class: 'small', title: 'Click the row to see and change what this item drives' }, [...(drives[t.id] || [])].slice(0, 3).join(', ') + ((drives[t.id] || new Set()).size > 3 ? ` +${drives[t.id].size - 3}` : '')), h('td', { style: { minWidth: '320px', width: '40%' } }, bar(t))))))));
  };
  root.append(h('div', { class: 'row', style: { gap: '12px', marginBottom: '8px' } }, h('input', { type: 'search', placeholder: 'Search tasks...', style: { width: '240px' }, oninput: (e) => { q = e.target.value.toLowerCase(); draw(); } }),
    h('label', { class: 'row small' }, h('input', { type: 'checkbox', checked: true, onchange: (e) => { showSummary = e.target.checked; draw(); } }), 'Show summary tasks')), wrap);
  draw();
}
