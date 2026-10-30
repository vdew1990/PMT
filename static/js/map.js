// A world map that works offline: country outlines bundled with PMT (Natural Earth via world-atlas), drawn with
// Leaflet. "Street map" swaps in OpenStreetMap tiles when the PC is online. Projects are dots coloured by type and
// sized by contract value; click one to open it. pickMap() lets the user click the site location for a project.
import { fmt } from './ui.js';

export const TYPES = ['Solar farm', 'Wind farm', 'BESS', 'Hybrid (solar + BESS)', 'Mining', 'Transmission', 'Substation', 'Other'];
// projects saved before the split keep working: "Substation / transmission" reads as Substation
export const canonType = (t) => (t === 'Substation / transmission' ? 'Substation' : t);
// fixed order, never cycled: a type keeps its colour whatever else is on the map
export const TYPE_COLOUR = { 'Solar farm': '#ffb500', BESS: '#4195f2', 'Hybrid (solar + BESS)': '#e56210', 'Wind farm': '#2938c2', Substation: '#102361', Transmission: '#335062', Mining: '#8c6a3f', Other: '#6b7a90' };
export const typeColour = (t) => TYPE_COLOUR[canonType(t)] || TYPE_COLOUR.Other;
// one white symbol per project type, drawn in a 24 x 24 box on the coloured dot
const SUN = '<circle cx="12" cy="12" r="4.2" fill="#fff"/><g stroke="#fff" stroke-width="2" stroke-linecap="round"><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/></g>';
const SUN_ONLY = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.6" fill="#fff"/><g stroke="#fff" stroke-width="2.2" stroke-linecap="round"><path d="M12 1.8v3M12 19.2v3M1.8 12h3M19.2 12h3M4.8 4.8l2.1 2.1M17.1 17.1l2.1 2.1M4.8 19.2l2.1-2.1M17.1 6.9l2.1-2.1"/></g></svg>';
const SYMBOL = {
  'Solar farm': '<svg viewBox="0 0 24 24"><g fill="none" stroke="#fff" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"><g transform="translate(-0.6 0.4) rotate(26 11 14)"><path d="M3.5 17.2 6.2 10.2h12.4l2.7 7z"/><path d="M5.2 13.7h14.5M10.4 10.2l-.8 7M15.4 10.2l.6 7"/></g><path d="M10.6 18.6v2.2M7.4 20.8h6.4"/><path d="M19.8 1.2v1.2M19.8 8v1.2M15.8 4.8H17M22.6 4.8h1.2M17 2l.8.8M21.8 6.8l.8.8M22.6 2l-.8.8M17.8 6.8l-.8.8" stroke-width="1.3"/></g><circle cx="19.8" cy="4.8" r="2" fill="#fff"/></svg>',
  BESS: '<svg viewBox="0 0 24 24"><rect x="6.5" y="5" width="11" height="16.5" rx="1.9" fill="none" stroke="#fff" stroke-width="2"/><rect x="9.5" y="2.2" width="5" height="2.4" rx=".7" fill="#fff"/><path d="M13 8.4 9.4 14h2.7l-1 4.6 3.6-5.9h-2.7z" fill="#fff"/></svg>',
  'Hybrid (solar + BESS)': '<svg viewBox="0 0 24 24"><g fill="none" stroke="#fff" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"><g transform="translate(-0.7 1.6) scale(.9) rotate(24 8 11)"><path d="M1.8 14.6 4 8.4h9l2.2 6.2z"/><path d="M3.2 11.5h11.6M7.4 8.4l-.6 6.2M11.4 8.4l.5 6.2"/></g><path d="M6.4 16.6v2.4M3.6 19h5.6"/><rect x="15.6" y="7.2" width="6.6" height="12.8" rx="1.5" stroke-width="1.7"/></g><rect x="17.5" y="5" width="2.8" height="1.7" rx=".5" fill="#fff"/><path d="M19.4 9.8 16.9 14h2l-.9 4 2.8-4.7h-2.1z" fill="#fff"/></svg>',
  'Wind farm': '<svg viewBox="0 0 24 24"><g stroke="#fff" stroke-width="2" stroke-linecap="round" fill="#fff"><path d="M12 12.5V22"/><path d="M12 11.5 12 3.2M12 11.5 4.6 15.6M12 11.5l7.4 4.1"/><circle cx="12" cy="11.5" r="1.7"/></g></svg>',
  Substation: '<svg viewBox="0 0 24 24"><g fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="9" width="14" height="10" rx="1.5"/><path d="M8 9V4.5M12 9V4.5M16 9V4.5"/><path d="M5 12.5H3M5 16H3M19 12.5h2M19 16h2"/></g><path d="M9 11.5v5M12 11.5v5M15 11.5v5" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/></svg>',
  Mining: '<svg viewBox="0 0 24 24"><g fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2.6 13.4 4 7.2 22 3.6 22.4 6.2 15 7.6V13.4z" fill="#fff" fill-opacity=".3"/><path d="M15.4 8.6h4.6v4.4h-4.6z" fill="#fff" fill-opacity=".3"/><circle cx="7.2" cy="17.4" r="4.2" fill="#fff" fill-opacity=".3"/><circle cx="16.8" cy="17.4" r="4.2" fill="#fff" fill-opacity=".3"/><circle cx="7.2" cy="17.4" r="1.4" fill="#fff" stroke="none"/><circle cx="16.8" cy="17.4" r="1.4" fill="#fff" stroke="none"/></g></svg>',
  Transmission: '<svg viewBox="0 0 24 24"><g stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" fill="none"><path d="M12 2.5 7 21.5M12 2.5l5 19M8.8 14h6.4M7.6 18h8.8"/><path d="M4.5 8h15M7 5h10"/></g></svg>',
  Other: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4" fill="#fff"/></svg>',
};
// small dots (legend, small map markers): a solar farm shows just the sun, the panel is too fine to read
const SMALL_PX = 32;
export const typeSymbol = (t, px = 99) => (canonType(t) === 'Solar farm' && px < SMALL_PX ? SUN_ONLY : SYMBOL[canonType(t)] || SYMBOL.Other);
export const typeIcon = (t, px = 24) => `<span class="tsym" style="width:${px}px;height:${px}px;padding:${Math.max(2, Math.round(px * 0.17))}px;background:${typeColour(t)}">${typeSymbol(t, px)}</span>`;

const AUS = [[-44, 112], [-10, 154]];
let ready = null;
function load() {
  if (ready) return ready;
  const css = (href) => new Promise((res) => { const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = href; l.onload = res; l.onerror = res; document.head.append(l); });
  const js = (src) => new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = () => rej(new Error('Could not load ' + src)); document.head.append(s); });
  ready = Promise.all([css('/static/vendor/leaflet/leaflet.css'), js('/static/vendor/leaflet/leaflet.js'), js('/static/vendor/topojson-client.min.js')])
    .then(() => fetch('/static/vendor/countries-50m.json')).then((r) => r.json())
    .then((topo) => window.topojson.feature(topo, topo.objects.countries));
  return ready;
}

function base(el, opts = {}) {
  return load().then((countries) => {
    const L = window.L;
    const map = L.map(el, { worldCopyJump: true, minZoom: 2, maxZoom: 14, zoomSnap: 0.5, attributionControl: true, ...opts });
    map.attributionControl.setPrefix('');
    map.fitBounds(AUS);   // a view first: layers need one to draw
    const outline = L.geoJSON(countries, { style: { color: '#b7c0d0', weight: 0.7, fillColor: '#f7f8fb', fillOpacity: 1 }, interactive: false });
    const streets = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors' });
    outline.addTo(map);
    el.classList.add('pmtmap');
    L.control.layers({ 'Outline (works offline)': outline, 'Street map (online)': streets }, null, { position: 'topright', collapsed: true }).addTo(map);
    map.attributionControl.addAttribution('Outlines: Natural Earth');
    return map;
  });
}


// projects: [{ id, name, lat, lon, project_type, contract_value, client, mw, mwh, voltage, pm }]
export async function projectMap(el, projects, { onOpen, extra = [] } = {}) {
  const map = await base(el);
  const L = window.L;
  const placed = projects.filter((p) => p.lat != null && p.lon != null);
  const maxV = Math.max(1, ...placed.map((p) => p.contract_value || 0));
  const pts = [];
  // biggest first, so smaller dots on the same site stay on top and clickable
  [...placed].sort((a, b) => (b.contract_value || 0) - (a.contract_value || 0)).forEach((p) => {
    const r = 6 + 14 * Math.sqrt((p.contract_value || 0) / maxV);
    const px = Math.round(r * 2 + 16);   // the symbol sits on a dot sized by contract value
    const m = L.marker([p.lat, p.lon], { icon: L.divIcon({ className: 'tsym-wrap', html: typeIcon(p.project_type, px), iconSize: [px, px], iconAnchor: [px / 2, px / 2] }), zIndexOffset: Math.round(1000 - px * 10) }).addTo(map);
    m.bindTooltip(`<b>${esc(p.name)}</b><br>${esc(p.project_type || 'Type not set')}${p.client ? ' · ' + esc(p.client) : ''}<br>`
      + `${fmt.m(p.contract_value || 0)}${p.mw ? ` · ${fmt.n(p.mw)} MW` : ''}${p.mwh ? ` · ${fmtMWh(p.mwh)}` : ''}${p.voltage ? ` · ${esc(p.voltage)} kV` : ''}`
      + `${p.pm ? `<br>PM ${esc(p.pm)}` : ''}${p.location ? ` · ${esc(p.location)}` : ''}`, { direction: 'top', offset: [0, -px / 2] });
    if (onOpen) m.on('click', () => onOpen(p));
    pts.push([p.lat, p.lon]);
  });
  // extra points (e.g. PM home offices): small navy squares
  extra.filter((x) => x.lat != null).forEach((x) => {
    L.marker([x.lat, x.lon], { icon: L.divIcon({ className: 'pm-base', html: `<span title="${esc(x.label)}"></span>`, iconSize: [12, 12] }) }).addTo(map).bindTooltip(esc(x.label), { direction: 'top' });
    pts.push([x.lat, x.lon]);
  });
  if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.6), { maxZoom: 5 });
  else map.fitBounds(AUS);
  // legend: the types on the map, plus a note for projects without a location
  const legend = L.control({ position: 'bottomleft' });
  legend.onAdd = () => {
    const used = TYPES.filter((t) => placed.some((p) => (TYPE_COLOUR[canonType(p.project_type)] ? canonType(p.project_type) : 'Other') === t));
    const d = L.DomUtil.create('div', 'map-legend');
    d.innerHTML = used.map((t) => `<span class="lg">${typeIcon(t, 20)}${t}</span>`).join('') + (extra.length ? '<span><i class="sq"></i>PM base</span>' : '')
      + (projects.length > placed.length ? `<div class="muted">${projects.length - placed.length} project(s) without a site location (set it on Project setup)</div>` : '')
      + '<div class="muted">Dot size: contract value</div>';
    return d;
  };
  legend.addTo(map);
  setTimeout(() => map.invalidateSize(), 50);
  return map;
}

// click to set a site location; returns a function that reads it
export async function pickMap(el, start, onPick) {
  const map = await base(el);
  const L = window.L;
  let marker = null;
  const set = (lat, lon, fly) => {
    if (marker) marker.setLatLng([lat, lon]); else marker = L.circleMarker([lat, lon], { radius: 9, color: '#fff', weight: 2, fillColor: '#e56210', fillOpacity: 0.95, interactive: false }).addTo(map);
    if (fly) map.setView([lat, lon], Math.max(map.getZoom(), 7));
  };
  if (start && start.lat != null) { set(start.lat, start.lon); map.setView([start.lat, start.lon], 7); } else map.fitBounds(AUS);
  map.on('click', (e) => { set(e.latlng.lat, e.latlng.lng); onPick(round(e.latlng.lat), round(e.latlng.lng)); });
  setTimeout(() => map.invalidateSize(), 50);
  return { set: (lat, lon) => set(lat, lon, true), map };
}

// find a place by name (OpenStreetMap Nominatim; needs internet)
export async function geocode(q) {
  const r = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=5&countrycodes=au,nz&q=${encodeURIComponent(q)}`, { headers: { 'Accept-Language': 'en-AU' } });
  if (!r.ok) throw new Error('Place search is not available (offline?)');
  return (await r.json()).map((x) => ({ label: x.display_name, lat: round(+x.lat), lon: round(+x.lon) }));
}

const round = (v) => Math.round(v * 10000) / 10000;
export const fmtMWh = (v) => (v >= 1000 ? `${fmt.n(v / 1000, 2)} GWh` : `${fmt.n(v)} MWh`);
function esc(s) { return String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
