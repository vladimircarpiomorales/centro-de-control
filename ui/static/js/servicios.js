// ── Toggle servicio ──────────────────────────────────────────────
async function toggleService(id) {
  const card = document.getElementById('card-' + id);
  const isOn = card.classList.contains('on');
  const newState = !isOn;
  card.classList.toggle('on', newState);
  updateTabCounts();
  await fetch('/api/toggle/' + id, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ on: newState })
  });
}

// ── Update ───────────────────────────────────────────────────────
async function updateService(id) {
  const bar = document.getElementById('progress-' + id);
  if (bar) bar.classList.add('active');
  await fetch('/api/update/' + id, { method: 'POST' });
}

// ── Restart ──────────────────────────────────────────────────────
async function restartService(id) {
  const bar = document.getElementById('progress-' + id);
  if (bar) bar.classList.add('active');
  await fetch('/api/restart/' + id, { method: 'POST' });
}

// ── Uptime ───────────────────────────────────────────────────────
function formatUptime(seconds) {
  if (!seconds || seconds < 0) return '';
  if (seconds < 60)   return seconds + 's';
  if (seconds < 3600) return Math.floor(seconds / 60) + 'm';
  if (seconds < 86400) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return h + 'h ' + (m > 0 ? m + 'm' : '');
  }
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  return d + 'd ' + (h > 0 ? h + 'h' : '');
}

// ── Scan (radar) ─────────────────────────────────────────────────
async function scanAll() {
  const res = await fetch('/api/status');
  const data = await res.json();
  for (const [id, on] of Object.entries(data.services)) {
    const card = document.getElementById('card-' + id);
    if (card) {
      card.classList.toggle('on', on);
      if (data.health && data.health[id] !== undefined) {
        card.classList.toggle('healthy', data.health[id] === 'healthy');
        card.classList.toggle('unhealthy', data.health[id] === 'unhealthy');
      }
    }
  }
  updateTabCounts();
}

// ── Stats polling ─────────────────────────────────────────────────
async function pollStats() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    const { cpu, ram, disk, gpu } = data.system;
    updateStat('cpu', cpu);
    updateStat('ram', ram);
    updateStat('disk', disk);
    updateGpuStat(gpu);

    let metubeOn = false;
    for (const [id, on] of Object.entries(data.services)) {
      const card = document.getElementById('card-' + id);
      if (card) {
        card.classList.toggle('on', on);
        if (data.health && data.health[id] !== undefined) {
          card.classList.toggle('healthy', data.health[id] === 'healthy');
          card.classList.toggle('unhealthy', data.health[id] === 'unhealthy');
        }
        // Uptime
        const uptimeEl = document.getElementById('uptime-' + id);
        if (uptimeEl && data.uptimes) {
          const secs = data.uptimes[id];
          uptimeEl.textContent = on && secs ? '↑ ' + formatUptime(secs) : '';
        }
      }
      if (id === 'metube' && on) metubeOn = true;
    }
    updateTabCounts();

    // MeTube monitor
    const monitor = document.getElementById('metube-monitor');
    if (monitor) {
      monitor.classList.toggle('visible', metubeOn);
      if (metubeOn) pollMetube();
    }
  } catch (e) {}
}

// ── MeTube monitor ────────────────────────────────────────────────
async function pollMetube() {
  try {
    const res  = await fetch('/api/metube/queue');
    const data = await res.json();

    const queueEl = document.getElementById('metube-queue-list');
    if (data.queue.length === 0) {
      queueEl.innerHTML = '<span style="font-size:11px;color:var(--muted2)">Sin descargas activas</span>';
    } else {
      queueEl.innerHTML = data.queue.map(item => {
        const info  = item.info || item;
        const title = info.title || info.url || '—';
        const pct   = info.percent ? Math.round(info.percent) + '%' : '…';
        return `<div class="metube-item">
          <span class="metube-item-status downloading">▼ ${pct}</span>
          <span class="metube-item-title" title="${title}">${title}</span>
        </div>`;
      }).join('');
    }

    const compEl = document.getElementById('metube-completed-list');
    if (data.completed.length === 0) {
      compEl.innerHTML = '<span style="font-size:11px;color:var(--muted2)">Sin historial</span>';
    } else {
      compEl.innerHTML = data.completed.map(item => {
        const info  = item.info || item;
        const title = info.title || '—';
        const size  = info.size ? (info.size / 1e6).toFixed(0) + ' MB' : '';
        return `<div class="metube-item">
          <span class="metube-item-status finished">✓</span>
          <span class="metube-item-title" title="${title}">${title}</span>
          <span class="metube-item-size">${size}</span>
        </div>`;
      }).join('');
    }
  } catch (e) {}
}

function updateStat(key, val) {
  const pct = val + '%';
  document.getElementById('stat-' + key).textContent = pct;
  document.getElementById('big-' + key).textContent = pct;
  const bar = document.getElementById('bar-' + key);
  bar.style.width = val + '%';
  bar.className = 'stat-fill' + (val > 85 ? ' danger' : val > 65 ? ' warn' : '');
}
function updateGpuStat(gpu) {
  const card = document.getElementById('card-gpu');
  const wrap = document.getElementById('stat-gpu-wrap');
  const divider = document.getElementById('divider-gpu');
  if (!gpu) {
    card.style.display = 'none';
    wrap.style.display = 'none';
    divider.style.display = 'none';
    return;
  }
  card.style.display = 'flex';
  wrap.style.display = 'flex';
  divider.style.display = 'block';
  const pct = gpu.util + '%';
  document.getElementById('stat-gpu').textContent = pct;
  document.getElementById('big-gpu').textContent = pct;
  const bar = document.getElementById('bar-gpu');
  bar.style.width = gpu.util + '%';
  document.getElementById('gpu-extra').textContent = `${gpu.mem_used}/${gpu.mem_total} MB · ${gpu.temp}°C`;
  wrap.title = `VRAM ${gpu.mem_used}/${gpu.mem_total} MB · ${gpu.temp}°C`;
}

setInterval(pollStats, 8000);
pollStats();

// ── Tab counts ───────────────────────────────────────────────────
function updateTabCounts() {
  ['podman', 'locales', 'media', 'sistema'].forEach(tab => {
    const cards = document.querySelectorAll('#tab-' + tab + ' .service-card');
    let on = 0, off = 0;
    cards.forEach(c => c.classList.contains('on') ? on++ : off++);
    document.getElementById('count-' + tab + '-on').textContent = on + '↑';
    document.getElementById('count-' + tab + '-off').textContent = off + '↓';
    document.getElementById('tab-' + tab).classList.toggle('sin-encendidos',
      document.body.classList.contains('solo-on') && on === 0);
  });
  if (typeof renderHoyServicios === 'function') renderHoyServicios();
}

// ── Filtro «solo encendidos» y menús ⋯ ───────────────────────────
function filtrarServicios(modo) {
  document.body.classList.toggle('solo-on', modo === 'on');
  document.querySelectorAll('.svc-filtro').forEach(b => b.classList.toggle('active', b.dataset.filtro === modo));
  safeStorage.setItem('filtroServicios', modo);
  updateTabCounts();
}
function cerrarMenus(excepto) {
  document.querySelectorAll('details.svc-menu[open], details.oferta-menu[open]').forEach(d => {
    if (d !== excepto) d.removeAttribute('open');
  });
}
// un clic fuera cierra cualquier menú ⋯ abierto
document.addEventListener('click', e => cerrarMenus(e.target.closest('details.svc-menu, details.oferta-menu')));
document.addEventListener('toggle', e => {
  if (!e.target.matches?.('details.svc-menu, details.oferta-menu')) return;
  e.target.closest('.service-card, .beca-card')?.classList.toggle('menu-abierto', e.target.open);
}, true);
filtrarServicios(safeStorage.getItem('filtroServicios') || 'todos');

