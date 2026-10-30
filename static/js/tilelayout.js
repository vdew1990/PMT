// Tiles (.kpi) sit on a grid; the user can move them around within it. Drag a tile by the four-dot grip that shows at its
// top-left when the mouse is over it. The order is kept per page in the person's profile (follows them between PCs).
// A tile is known by its label, so the order survives the figures changing. Settings > Menu and tile layout puts them back.
import { api, state } from './api.js';
import { route } from './app.js';

const sig = (grid) => [...grid.children].map((t) => t.querySelector('.l')?.textContent.trim() || '').sort().join('|');

function eligible(grid) {
  const tiles = [...grid.children].filter((c) => c.classList.contains('kpi'));
  if (tiles.length < 2 || tiles.length !== grid.children.length) return null;
  const labels = tiles.map((t) => t.querySelector('.l')?.textContent.trim());
  return labels.every(Boolean) && new Set(labels).size === labels.length ? tiles : null;
}

function save(key, order) {
  state.tiles = { ...(state.tiles || {}) };
  if (order) state.tiles[key] = order; else delete state.tiles[key];
  api.put('/api/me/tiles', { key, order }).catch(() => { /* the layout stays for this session */ });
}

function setup(grid) {
  const tiles = eligible(grid); if (!tiles) return;
  const key = `${route().name}::${sig(grid)}`;
  grid.dataset.tl = key;
  // saved order first
  const saved = state.tiles?.[key];
  if (saved) {
    const byLabel = new Map(tiles.map((t) => [t.querySelector('.l').textContent.trim(), t]));
    saved.forEach((l) => { const t = byLabel.get(l); if (t) { grid.appendChild(t); byLabel.delete(l); } });
    byLabel.forEach((t) => grid.appendChild(t));
  }
  let dragged = null;
  [...grid.children].forEach((tile) => {
    if (tile.querySelector(':scope > .tl-grip')) return;
    tile.classList.add('tl-tile');
    const g = document.createElement('span');
    g.className = 'tl-grip grip4'; g.draggable = true; g.title = 'Drag to move this tile';
    g.addEventListener('dragstart', (e) => { dragged = tile; e.dataTransfer.setData('text/plain', 'tile'); e.dataTransfer.effectAllowed = 'move'; try { e.dataTransfer.setDragImage(tile, 16, 16); } catch (err) { /* optional */ } tile.classList.add('tl-dragging'); });
    g.addEventListener('dragend', () => { tile.classList.remove('tl-dragging'); grid.querySelectorAll('.tl-before, .tl-after').forEach((x) => x.classList.remove('tl-before', 'tl-after')); dragged = null; });
    g.addEventListener('click', (e) => e.stopPropagation());
    tile.insertBefore(g, tile.firstChild);
    tile.addEventListener('dragover', (e) => {
      if (!dragged || dragged === tile || dragged.parentElement !== grid) return;
      e.preventDefault();
      const r = tile.getBoundingClientRect(); const before = e.clientX < r.left + r.width / 2;
      grid.querySelectorAll('.tl-before, .tl-after').forEach((x) => x.classList.remove('tl-before', 'tl-after'));
      tile.classList.add(before ? 'tl-before' : 'tl-after');
    });
    tile.addEventListener('drop', (e) => {
      if (!dragged || dragged === tile || dragged.parentElement !== grid) return;
      e.preventDefault();
      const r = tile.getBoundingClientRect(); const before = e.clientX < r.left + r.width / 2;
      grid.insertBefore(dragged, before ? tile : tile.nextSibling);
      grid.querySelectorAll('.tl-before, .tl-after').forEach((x) => x.classList.remove('tl-before', 'tl-after'));
      save(key, [...grid.children].map((c) => c.querySelector('.l').textContent.trim()));
    });
  });
}

export function watchTileLayout(root = document.body) {
  let t = null;
  const run = () => { t = null; root.querySelectorAll('#view .grid:not([data-tl])').forEach((g) => { try { setup(g); } catch (e) { console.error(e); } }); };
  new MutationObserver(() => { if (!t) t = setTimeout(run, 80); }).observe(root, { childList: true, subtree: true });
  run();
  return run;
}
