// ── Almacenamiento seguro (localStorage puede no existir en el webview embebido) ──
const _memStore = {};
const safeStorage = {
  getItem(k) { try { return localStorage.getItem(k); } catch (e) { return _memStore[k] ?? null; } },
  setItem(k, v) { try { localStorage.setItem(k, v); } catch (e) { _memStore[k] = v; } }
};

// ── Tamaño de letra ──────────────────────────────────────────────
// zoom en <body> escala todo (los tamaños están en px). La rejilla mide 100vh y,
// según el motor, vh se escala con el zoom o no: se mide y se corrige en px.
const ZOOM_PASOS = [0.8, 0.9, 1, 1.1, 1.2, 1.3, 1.4, 1.5, 1.65, 1.8];
function aplicarZoom(z) {
  document.body.style.zoom = z;
  const shell = document.querySelector('.shell');
  if (shell) {
    shell.style.height = '';
    const alto = shell.getBoundingClientRect().height;
    if (Math.abs(alto - window.innerHeight) > 2) shell.style.height = (window.innerHeight / z) + 'px';
  }
  const val = document.getElementById('zoom-val');
  if (val) val.textContent = Math.round(z * 100) + '%';
}
function cambiarZoom(dir) {
  const actual = parseFloat(safeStorage.getItem('zoomPanel')) || 1;
  let i = ZOOM_PASOS.indexOf(actual);
  if (i < 0) i = ZOOM_PASOS.indexOf(1);
  const z = dir === 0 ? 1 : ZOOM_PASOS[Math.max(0, Math.min(ZOOM_PASOS.length - 1, i + dir))];
  safeStorage.setItem('zoomPanel', String(z));
  aplicarZoom(z);
}
document.addEventListener('DOMContentLoaded', () => aplicarZoom(parseFloat(safeStorage.getItem('zoomPanel')) || 1));
window.addEventListener('resize', () => aplicarZoom(parseFloat(safeStorage.getItem('zoomPanel')) || 1));
document.addEventListener('keydown', (e) => {
  if (!e.ctrlKey) return;
  if (e.key === '+' || e.key === '=') { e.preventDefault(); cambiarZoom(1); }
  else if (e.key === '-') { e.preventDefault(); cambiarZoom(-1); }
  else if (e.key === '0') { e.preventDefault(); cambiarZoom(0); }
});

// ── WebSocket ────────────────────────────────────────────────────
const socket = io();

socket.on('connect', () => {
  loadPastLogs();
});

socket.on('log', ({ ts, msg }) => {
  addLog(ts, msg);
});

socket.on('progress', ({ id, active }) => {
  const bar = document.getElementById('progress-' + id);
  if (bar) bar.classList.toggle('active', active);
});

let manualesConvHideTimer = null;
socket.on('pdf_progress', ({ file, percent }) => {
  clearTimeout(manualesConvHideTimer);
  const box = document.getElementById('manuales-conv-progress');
  box.style.display = 'block';
  document.getElementById('manuales-conv-file').textContent = file;
  document.getElementById('manuales-conv-pct').textContent = percent + '%';
  document.getElementById('manuales-conv-fill').style.width = percent + '%';
  if (percent >= 100) {
    manualesConvHideTimer = setTimeout(() => { box.style.display = 'none'; }, 1500);
  }
});

// ── Past logs ────────────────────────────────────────────────────
async function loadPastLogs() {
  try {
    const res = await fetch('/api/logs');
    const lines = await res.json();
    lines.forEach(line => {
      const match = line.match(/^\[(\d{2}:\d{2}:\d{2})\]\s(.*)/);
      if (match) addLog(match[1], match[2]);
    });
  } catch (e) {}
}

// ── Clock ────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent = now.toTimeString().slice(0, 8);
}
updateClock();
setInterval(updateClock, 1000);

// ── Tabs ─────────────────────────────────────────────────────────
function switchTab(tabId, el) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const tab = document.getElementById('tab-' + tabId);
  if (tab) { tab.classList.add('active'); }
  if (el) { el.classList.add('active'); }
}

// ── Helpers ──────────────────────────────────────────────────────
async function apiCall(path, method) {
  await fetch(path, { method });
}
// ── Escapado HTML (lo usan todos los módulos) ───────────────────
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

