// ── Modo foco (pomodoro) ─────────────────────────────────────────
let focoData = null, focoMin = 25, focoTick = null;

async function loadFoco() {
  try { focoData = await (await fetch('/api/foco')).json(); renderFocoTop(); if (document.getElementById('foco-modal').classList.contains('show')) renderFoco(); } catch (e) {}
}
socket.on('foco', () => loadFoco());

const mmss = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

function renderFocoTop() {
  const el = document.getElementById('foco-top');
  clearInterval(focoTick);
  const a = focoData?.actual;
  if (!a) { el.classList.remove('activo'); el.textContent = '⏱ Foco'; return; }
  const fin = Date.now() + a.restante * 1000;
  const pinta = () => {
    const r = Math.max(0, Math.round((fin - Date.now()) / 1000));
    el.textContent = `⏱ ${mmss(r)} · ${a.materia}`;
    if (r === 0) { clearInterval(focoTick); setTimeout(loadFoco, 6000); }
  };
  el.classList.add('activo');
  pinta();
  focoTick = setInterval(pinta, 1000);
}

function abrirFoco() { renderFoco(); document.getElementById('foco-modal').classList.add('show'); }
function cerrarFoco() { document.getElementById('foco-modal').classList.remove('show'); }

function renderFoco() {
  const d = focoData;
  if (!d) return;
  const h = m => m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
  const a = d.actual;
  document.getElementById('foco-body').innerHTML = (a ? `
      <div class="foco-actual">Estás con <b>${esc(a.materia)}</b> · quedan <b id="foco-quedan">${mmss(a.restante)}</b></div>
      <div class="ent-botones"><button class="icon-btn update" onclick="terminarFoco(true)">✓ Terminado</button>
        <button class="icon-btn" onclick="terminarFoco(false)">■ Cortar (cuenta lo hecho si pasa de 5 min)</button></div>`
    : `<label class="ent-label">¿En qué vas a trabajar?</label>
      <select class="carrera-input" id="foco-materia">${d.materias.map(m => `<option>${esc(m)}</option>`).join('')}</select>
      <div class="ent-opciones">
        <button class="beca-filtro ${focoMin === 25 ? 'active' : ''}" onclick="focoMin=25; renderFoco()">25 min + 5 de descanso</button>
        <button class="beca-filtro ${focoMin === 50 ? 'active' : ''}" onclick="focoMin=50; renderFoco()">50 min + 10 de descanso</button>
      </div>
      <button class="icon-btn update ent-empezar" onclick="empezarFoco()">▶ Empezar</button>
      <div class="ent-nota">Móvil lejos, una sola pestaña. Al terminar te aviso para descansar.</div>`) + `
    <div class="red-stats"><span>Hoy: <b>${h(d.hoy_min)}</b></span><span>Esta semana: <b>${h(d.semana_min)}</b></span><span>Racha: <b>${d.racha}</b> día${d.racha === 1 ? '' : 's'}</span></div>
    ${Object.keys(d.semana).length ? `<div class="prep-bloque"><b>Esta semana por materia</b>${Object.entries(d.semana).map(([m, min]) => `
      <div class="foco-barra"><span>${esc(m)}</span><div class="stat-bar"><div class="stat-fill" style="width:${Math.round(100 * min / Math.max(...Object.values(d.semana)))}%"></div></div><span>${h(min)}</span></div>`).join('')}</div>` : ''}`;
  if (a) {
    const fin = Date.now() + a.restante * 1000;
    const t = setInterval(() => { const q = document.getElementById('foco-quedan'); if (!q) return clearInterval(t); q.textContent = mmss(Math.max(0, Math.round((fin - Date.now()) / 1000))); }, 1000);
  }
}

async function empezarFoco() {
  const materia = document.getElementById('foco-materia').value;
  await fetch('/api/foco/empezar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ materia, minutos: focoMin }) });
  await loadFoco(); cerrarFoco();
}
async function terminarFoco(completa) {
  await fetch('/api/foco/terminar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ completa }) });
  await loadFoco(); renderFoco();
}

loadFoco();
