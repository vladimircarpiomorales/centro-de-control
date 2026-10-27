// ── Mantenimiento (chequeos del equipo, copia de datos) ──────────
let mantData = null;
const MANT_ICONO = { ok: '✅', info: 'ℹ️', warn: '⚠️', err: '⛔' };
const MANT_ORDEN = { err: 0, warn: 1, info: 2, ok: 3 };

async function loadMant() {
  try {
    const res = await fetch('/api/mantenimiento');
    mantData = await res.json();
    renderMant();
  } catch (e) {}
}

function renderMant() {
  if (typeof queueHoy === 'function') queueHoy();
  if (!mantData) return;
  const badge = document.getElementById('count-mant');
  badge.style.display = mantData.avisos ? '' : 'none';
  badge.textContent = mantData.avisos ? mantData.avisos + ' ⚠' : '';
  document.getElementById('mant-info').textContent = mantData.corriendo ? '⟳ revisando…'
    : mantData.fecha ? `revisado ${mantData.fecha.replace('T', ' ')} · se repite cada 6 h` : '';
  if (!mantData.checks.length) return;
  const checks = [...mantData.checks].sort((a, b) => MANT_ORDEN[a.estado] - MANT_ORDEN[b.estado]);
  document.getElementById('mant-lista').innerHTML = checks.map(c => {
    const a = c.arreglo || {};
    return `<div class="mant-item ${c.estado}">
      <span class="mant-icono">${MANT_ICONO[c.estado] || ''}</span>
      <div class="mant-cuerpo">
        <div class="mant-titulo">${esc(c.titulo)}</div>
        <div class="mant-detalle">${esc(c.detalle)}</div>
        ${a.texto ? `<div class="mant-detalle">💡 ${esc(a.texto)}</div>` : ''}
        ${a.comando ? `<div class="mant-cmd"><code>${esc(a.comando)}</code>
          <button class="icon-btn" onclick="copiarCmd(this)" title="Copiar el comando para pegarlo en una terminal">⧉</button></div>` : ''}
      </div>
      ${a.accion ? `<button class="icon-btn update" onclick="accionMant('${esc(a.accion)}', this)">${esc(a.boton || 'Arreglar')}</button>` : ''}
    </div>`;
  }).join('');
}

function copiarCmd(btn) {
  const texto = btn.parentElement.querySelector('code').textContent.split('   #')[0].trim();
  const ok = () => { btn.textContent = '✓'; setTimeout(() => btn.textContent = '⧉', 1500); };
  if (navigator.clipboard) navigator.clipboard.writeText(texto).then(ok).catch(() => {});
}

async function revisarMant() {
  document.getElementById('mant-info').textContent = '⟳ revisando…';
  await fetch('/api/mantenimiento/revisar', { method: 'POST' });
  setTimeout(loadMant, 4000);
  setTimeout(loadMant, 15000);
}

async function accionMant(accion, btn) {
  btn.disabled = true;
  btn.textContent = '⏳';
  await fetch('/api/mantenimiento/accion', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ accion }),
  });
  setTimeout(loadMant, 5000);
  setTimeout(loadMant, 20000);
}

loadMant();
setInterval(loadMant, 5 * 60000);
