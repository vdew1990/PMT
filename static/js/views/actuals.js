import { h, clear, fmt, tabs, chart, PALETTE, empty, debounce, badge, select } from '../ui.js';
import { api, p } from '../api.js';
import { go } from '../app.js';
import { historyPage } from './_history.js';

// COST > Actuals. Two views:
//   Invoices by supplier: every supplier invoice in the Pronto GL export (PO receipts, direct invoices, journals),
//     per supplier, with their purchase orders and, for subcontractors, the claims approved in PMT.
//   By CBS line and month: cost in Pronto per line and month as it stood at each month-end close.
export default async function actuals(root, params) {
  const tab = params.tab || (params.node ? 'history' : 'invoices');
  if (tab === 'history') {
    await historyPage(root, params, 'a', {
      title: 'Actuals',
      sub: 'Cost in Pronto by CBS line and month, as it stood at each month-end close (journals and re-coded transactions show as movement).',
      actions: [h('button', { class: 'btn ghost', onclick: () => go('actuals', { tab: 'invoices' }) }, 'Invoices by supplier'), h('button', { class: 'btn ghost', onclick: () => go('costcontrol') }, 'Cost control')],
    });
    root.querySelector('.pagehead')?.after(tabs(TABS, 'history', (k) => go('actuals', { tab: k })));
    return;
  }
  root.append(h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Actuals'),
    h('div', { class: 'sub' }, 'Every supplier invoice Pronto has posted to the project (purchase-order receipts, direct invoices and supplier journals), per supplier. Labour timesheets are on the labour calendar.')),
  h('div', { class: 'sp' }), h('button', { class: 'btn ghost', onclick: () => window.open(p('/invoices.xlsx')) }, 'Export to Excel'), h('button', { class: 'btn ghost', onclick: () => go('pronto') }, 'Pronto data')));
  root.append(tabs(TABS, 'invoices', (k) => go('actuals', { tab: k })));
  const d = await api.get(p('/invoices'));
  if (!d.suppliers.length) {
    root.append(empty('No supplier invoices yet', 'Upload the Pronto GL transactions export on Pronto data: every purchase-order receipt and supplier invoice in it shows here, per supplier.',
      h('button', { class: 'btn', onclick: () => go('pronto') }, 'Open Pronto data')));
    return;
  }
  const ui = JSON.parse(sessionStorage.getItem('invui') || '{}');
  if (params.supplier) ui.sel = params.supplier;
  ui.group = ui.group ?? ''; ui.q = ui.q || ''; ui.from = ui.from || ''; ui.to = ui.to || '';
  const save = () => { try { sessionStorage.setItem('invui', JSON.stringify(ui)); } catch (e) { /* ignore */ } };
  const months = [...new Set(d.invoices.map((i) => i.month))].sort();
  const names = Object.fromEntries(d.suppliers.map((s) => [s.code, s.name]));

  const q = h('input', { type: 'search', value: ui.q, placeholder: 'Search supplier, invoice, PO, description, CBS...', style: { width: '300px' }, oninput: debounce(() => { ui.q = q.value.trim(); save(); draw(); }, 150) });
  const chip = (k, l) => h('span', { class: 'chip' + (ui.group === k ? ' on' : ''), onclick: () => { ui.group = k; save(); bar(); draw(); } }, l);
  const mSel = (k, label) => select([['', label], ...months.map((m) => [m, fmt.month(m)])], ui[k], { onchange: (e) => { ui[k] = e.target.value; save(); draw(); } });
  const barBox = h('div', { class: 'card', style: { padding: '10px 14px', marginBottom: '12px' } });
  const bar = () => clear(barBox).append(h('div', { class: 'row' }, q, chip('', 'All'), chip('PS', 'Subcontractors'), chip('PM', 'Materials'), chip('PE', 'Expenses'),
    h('span', { style: { width: '10px' } }), h('span', { class: 'small muted' }, 'Invoice dates'), mSel('from', 'from the start'), h('span', { class: 'small muted' }, 'to'), mSel('to', 'now')));
  bar();
  const out = h('div');
  root.append(barBox, out);

  const inRange = (i) => (!ui.from || i.month >= ui.from) && (!ui.to || i.month <= ui.to);
  const hay = (i) => `${i.supplier} ${names[i.supplier] || ''} ${i.ref} ${i.po || ''} ${i.description} ${i.cbs.join(' ')} ${i.categories.join(' ')}`.toLowerCase();
  const tile = (l, v, s, c = '') => h('div', { class: 'kpi ' + c }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v), h('div', { class: 's' }, s));

  function draw() {
    const words = ui.q.toLowerCase().split(/\s+/).filter(Boolean);
    const sups = d.suppliers.filter((s) => !ui.group || s.group === ui.group);
    const codes = new Set(sups.map((s) => s.code));
    const inv = d.invoices.filter((i) => codes.has(i.supplier) && inRange(i) && words.every((w) => hay(i).includes(w)));
    const per = {};
    inv.forEach((i) => { (per[i.supplier] = per[i.supplier] || []).push(i); });
    const shown = sups.filter((s) => per[s.code]);
    const total = inv.reduce((a, i) => a + i.amount, 0);
    const thisM = inv.filter((i) => i.month === d.status_month).reduce((a, i) => a + i.amount, 0);
    clear(out).append(h('div', { class: 'grid g4', style: { marginBottom: '14px' } },
      tile('Suppliers', String(shown.length), `of ${d.suppliers.length} with invoices`),
      tile('Invoices', String(inv.length), ui.from || ui.to ? `${ui.from ? fmt.month(ui.from) : 'start'} to ${ui.to ? fmt.month(ui.to) : 'now'}` : 'all dates', 't2'),
      tile('Invoiced', fmt.money(total), 'in view', 't3'),
      tile(`Invoiced in ${fmt.month(d.status_month)}`, fmt.money(thisM), 'the status month', 't4')));

    // suppliers: click one for its invoices
    const sel = shown.find((s) => s.code === ui.sel) || null;
    out.append(h('div', { class: 'card', style: { marginBottom: '14px' } }, h('div', { class: 'ch' }, h('h2', {}, 'Suppliers'), h('span', { class: 'sp' }), h('span', { class: 'small muted' }, 'Click a supplier for its invoices')),
      h('div', { class: 'tw', style: { maxHeight: '46vh' } }, h('table', { class: 't' },
        h('thead', {}, h('tr', {}, ['Supplier', 'Type', 'Invoices', 'Invoiced', fmt.month(d.status_month), 'Last invoice', 'PO committed', 'PO left', 'Subcontract', 'Approved less invoiced'].map((x, i) => h('th', { class: [2, 3, 4, 6, 7, 9].includes(i) ? 'r' : '' }, x)))),
        h('tbody', {}, shown.map((s) => {
          const mine = per[s.code]; const tot = mine.reduce((a, i) => a + i.amount, 0);
          return h('tr', { class: s.code === ui.sel ? 'sel' : '', style: { cursor: 'pointer' }, onclick: () => { ui.sel = s.code === ui.sel ? '' : s.code; save(); draw(); } },
            h('td', {}, h('b', {}, s.name), h('div', { class: 'small muted mono' }, s.code)),
            h('td', { class: 'small' }, s.group_name), h('td', { class: 'r num' }, String(mine.length)), h('td', { class: 'r num' }, fmt.money(tot)),
            h('td', { class: 'r num' }, fmt.money(mine.filter((i) => i.month === d.status_month).reduce((a, i) => a + i.amount, 0)) || ''),
            h('td', { class: 'nowrap small' }, fmt.date(mine[0].date)),
            h('td', { class: 'r num' }, s.po_committed ? fmt.money(s.po_committed) : ''), h('td', { class: 'r num' }, s.po_committed ? fmt.money(s.po_committed - s.po_received) : ''),
            h('td', { class: 'small' }, s.subcontracts.map((x) => h('a', { onclick: (e) => { e.stopPropagation(); go('subcontracts', { open: x.id }); } }, x.name))),
            h('td', { class: 'r num ' + (s.approved_not_invoiced > 0.5 ? 'warn' : '') }, s.approved_not_invoiced == null ? '' : fmt.money(s.approved_not_invoiced)));
        })))),
      h('div', { class: 'small muted', style: { marginTop: '6px' } }, 'PO left: committed less received on the supplier\'s purchase orders. Approved less invoiced: subcontract claims approved in PMT less what has been invoiced in Pronto (above zero is approved work still to be invoiced, and accrued).')));

    // the invoices: of the selected supplier, or all of them
    const list = sel ? per[sel.code] : inv;
    const card = h('div', { class: 'card' });
    card.append(h('div', { class: 'ch' }, h('h2', {}, sel ? `${sel.name}: ${list.length} invoice${list.length === 1 ? '' : 's'}, ${fmt.money(list.reduce((a, i) => a + i.amount, 0))}` : `All invoices (${list.length})`),
      h('span', { class: 'sp' }), sel ? h('button', { class: 'btn ghost sm', onclick: () => { ui.sel = ''; save(); draw(); } }, 'Show every supplier\'s invoices') : null));
    if (sel) {
      // invoiced per month, and the supplier's purchase orders
      const ms = [...new Set(list.map((i) => i.month))].sort();
      const box = h('div', { class: 'chartbox', style: { height: '200px' } });
      card.append(h('div', { class: 'grid g2', style: { marginBottom: '10px' } }, box,
        h('div', {}, sel.pos.length ? h('div', {}, h('b', { class: 'small' }, 'Purchase orders'), h('div', { class: 'tw' }, h('table', { class: 't' },
          h('thead', {}, h('tr', {}, ['PO', 'Status', 'Committed', 'Received', 'Left', 'CBS'].map((x, i) => h('th', { class: i >= 2 && i <= 4 ? 'r' : '' }, x)))),
          h('tbody', {}, sel.pos.map((po) => h('tr', {}, h('td', { class: 'mono' }, po.order_no), h('td', {}, badge(po.open ? 'open' : 'closed', po.open ? 'good' : '')),
            h('td', { class: 'r num' }, fmt.money(po.committed)), h('td', { class: 'r num' }, fmt.money(po.received)), h('td', { class: 'r num' }, fmt.money(po.committed - po.received)), h('td', { class: 'small' }, po.cbs.join(', ')))))))) : h('div', { class: 'muted small' }, 'No purchase order: direct invoices only.'),
        sel.subcontracts.map((x) => h('div', { class: 'note', style: { marginTop: '8px' } }, 'Subcontract ', h('a', { onclick: () => go('subcontracts', { open: x.id }) }, x.name), `: contract ${fmt.money(x.contract_value)}, claims approved ${fmt.money(x.approved)}, invoiced ${fmt.money(sel.total)}.`)))));
      chart(box, { type: 'bar', data: { labels: ms.map(fmt.month), datasets: [{ label: 'Invoiced', data: ms.map((m) => list.filter((i) => i.month === m).reduce((a, i) => a + i.amount, 0)), backgroundColor: PALETTE[0], borderRadius: 4 }] },
        options: { plugins: { legend: { display: false } } } });
    }
    card.append(list.length ? h('div', { class: 'tw', style: { maxHeight: '60vh' } }, h('table', { class: 't' },
      h('thead', {}, h('tr', {}, ['Date', ...(sel ? [] : ['Supplier']), 'Invoice / reference', 'Type', 'PO', 'Description', 'CBS', 'Amount', 'Claim'].map((x) => h('th', { class: x === 'Amount' ? 'r' : '' }, x)))),
      h('tbody', {}, list.map((i) => h('tr', {},
        h('td', { class: 'nowrap' }, fmt.date(i.date)), ...(sel ? [] : [h('td', { class: 'small' }, names[i.supplier] || i.supplier)]),
        h('td', { class: 'mono' }, i.ref), h('td', { class: 'small' }, i.kind), h('td', { class: 'mono small' }, i.po || ''), h('td', { class: 'small' }, i.description),
        h('td', { class: 'small mono' }, i.cbs.join(', ') || h('span', { class: 'muted' }, i.categories.join(', '))),
        h('td', { class: 'r num ' + (i.amount < 0 ? 'bad' : '') }, fmt.money(i.amount, 2)),
        h('td', { class: 'small' }, i.claim ? h('a', { onclick: () => go('subcontracts', { open: i.claim.sub_id }) }, `Claim ${i.claim.claim_no || ''} ${fmt.month(i.claim.month)}`) : '')))))) : empty('No invoices match', 'Change the search, the type or the dates.'));
    out.append(card);
  }
  draw();
}

const TABS = [['invoices', 'Invoices by supplier'], ['history', 'By CBS line and month (at each close)']];
