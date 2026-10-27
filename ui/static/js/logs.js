// ── Logs ─────────────────────────────────────────────────────────
function addLog(ts, msg) {
  const body = document.getElementById('log-body');
  const line = document.createElement('div');
  line.className = 'log-line';
  const cls = msg.startsWith('✓') || msg.startsWith('✅') ? 'ok'
            : msg.startsWith('⚠') ? 'warn'
            : msg.startsWith('❌') ? 'err' : '';
  // escapado: aquí llegan títulos de ofertas y mensajes de Telegram escritos por terceros
  line.innerHTML = `<span class="log-ts">${esc(ts)}</span><span class="log-msg ${cls}">${esc(msg)}</span>`;
  body.appendChild(line);
  const ultimo = document.getElementById('log-ultimo');
  ultimo.textContent = msg;
  ultimo.className = 'log-ultimo ' + cls;
  if ((cls === 'warn' || cls === 'err') && document.getElementById('log-panel').classList.contains('plegada')) {
    _logAvisos++;
    const av = document.getElementById('log-avisos');
    av.textContent = '⚠ ' + _logAvisos;
    av.style.display = '';
  }
  body.scrollTop = body.scrollHeight;
  // Limitar a 200 líneas
  while (body.children.length > 200) body.removeChild(body.firstChild);
}

let _logAvisos = 0;
function toggleLogPanel(forzar) {
  const panel = document.getElementById('log-panel');
  const plegada = forzar !== undefined ? forzar : !panel.classList.contains('plegada');
  panel.classList.toggle('plegada', plegada);
  document.getElementById('log-flecha').textContent = plegada ? '▲' : '▼';
  if (!plegada) {
    _logAvisos = 0;
    document.getElementById('log-avisos').style.display = 'none';
    const body = document.getElementById('log-body');
    body.scrollTop = body.scrollHeight;
  }
  safeStorage.setItem('logPlegada', plegada ? '1' : '0');
}
toggleLogPanel(safeStorage.getItem('logPlegada') !== '0');

function clearLogs() {
  document.getElementById('log-body').innerHTML = '';
  addLog(new Date().toTimeString().slice(0,8), '✓ Logs limpiados');
}

// ── Minimizar ────────────────────────────────────────────────────
async function minimizarPanel() {
  addLog(new Date().toTimeString().slice(0,8), '— Panel minimizado a bandeja');
  try { window.pywebview?.api?.hide_window(); } catch(_) {}
}

// ── Salir ─────────────────────────────────────────────────────────
async function salirSistema() {
  if (!confirm("¿Apagar todos los servicios y cerrar el sistema?")) return;
  addLog(new Date().toTimeString().slice(0,8), '🛑 Apagando sistema...');
  await fetch('/api/quit', { method: 'POST' });
}

