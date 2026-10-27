// ── Resumen semanal ──────────────────────────────────────────────
let resumenData = null;

async function loadResumen() {
  try { resumenData = await (await fetch('/api/resumen')).json(); renderHoySemana(); } catch (e) {}
}
async function generarResumen(a) {
  a.textContent = '⏳ escribiendo…';
  await fetch('/api/resumen/generar', { method: 'POST' });
  a.textContent = '✍ Resumen';
  loadResumen();
}

function renderHoySemana() {
  const el = document.getElementById('hoy-semana');
  if (!el || !resumenData) return;
  const filas = resumenData.filas.filter(f => f.esta || f.anterior);
  const flecha = f => f.esta > f.anterior ? '<span class="sem-sube">▲</span>' : f.esta < f.anterior ? '<span class="sem-baja">▼</span>' : '';
  const m = resumenData.mensaje;
  el.innerHTML = (filas.length ? `<div class="sem-grid">${filas.map(f => `
      <div class="sem-fila" title="semana pasada: ${f.anterior}"><span>${f.icono}</span><b>${f.esta}</b><span class="sem-txt">${esc(f.texto)}</span>${flecha(f)}</div>`).join('')}</div>`
    : '<span class="hoy-vacio">Aún nada esta semana: cualquier cosa que hagas en el panel aparecerá aquí.</span>')
    + (resumenData.nota_simulacros != null ? `<div class="hoy-sub">🎙 Nota media en los simulacros: ${resumenData.nota_simulacros}/10</div>` : '')
    + (m ? `<details class="hoy-sub sem-msg"><summary>💬 Mensaje del coach (${esc(m.fecha.slice(0, 10))})</summary><div>${esc(m.mensaje)}</div></details>` : '')
    + `<div class="hoy-pie">Semana del ${esc(resumenData.esta.inicio)} · el domingo por la tarde te llega el resumen</div>`;
}

loadResumen();
setInterval(loadResumen, 15 * 60000);
