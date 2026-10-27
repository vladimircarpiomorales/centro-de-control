// ── Reto de laboratorio del día ──────────────────────────────────
let retoData = null;
const RETO_AREA = { ccna: '🔀 CCNA', linux: '🐧 Linux', azure: '☁️ Azure' };

async function loadReto(ruta = '/api/retos', metodo = 'GET') {
  try { retoData = await (await fetch(ruta, { method: metodo })).json(); renderHoyReto(); } catch (e) {}
}
function otroReto() { loadReto('/api/retos/otro', 'POST'); }

async function abrirReto() {
  const r = retoData.reto;
  if (r.area === 'azure') {
    let { md } = await (await fetch('/api/retos/lab?id=' + encodeURIComponent(r.id))).json();
    md = md.replace(/^---\n[\s\S]*?\n---\n/, '');   // cabecera YAML de Microsoft Learn
    document.getElementById('lab-modal-titulo').textContent = '☁️ ' + r.titulo;
    // el lab es texto de Microsoft Learn: se escapa el HTML que traiga y se pinta el markdown
    document.getElementById('lab-modal-body').innerHTML = marked.parse(esc(md).replace(/&gt;/g, '>'));
    document.getElementById('lab-modal').classList.add('show');
    return;
  }
  await fetch('/api/retos/abrir', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: r.id }) });
}
async function retoHecho() {
  await fetch('/api/retos/hecho', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: retoData.reto.id }) });
  loadReto();
}

function renderHoyReto() {
  const el = document.getElementById('hoy-reto');
  if (!el || !retoData) return;
  const r = retoData.reto, s = retoData.resumen;
  if (!r || !r.id) { el.innerHTML = '<span class="hoy-vacio">No encuentro labs en ~/Proyectos.</span>'; return; }
  const total = Object.values(s.hechos).reduce((a, b) => a + b, 0);
  el.innerHTML = `
    <div class="hoy-sub">${RETO_AREA[r.area]} · ${esc(r.donde)}</div>
    <div class="hoy-tarea ${r.hecho ? 'reto-hecho' : ''}">${r.hecho ? '✅ ' : ''}${esc(r.titulo)}</div>
    ${r.motivo ? `<div class="hoy-sub">🎯 Porque ${esc(r.motivo)}</div>` : ''}
    ${r.enunciado ? `<details class="hoy-sub"><summary>Ver el enunciado</summary><div class="reto-enunciado">${esc(r.enunciado)}</div>
      ${r.pista ? `<div>💡 ${esc(r.pista)}</div>` : ''}</details>` : ''}
    <div class="hoy-acciones">
      ${r.hecho ? '' : `<button class="icon-btn update" onclick="abrirReto()">▶ ${r.area === 'azure' ? 'Leer el lab' : r.area === 'ccna' ? 'Abrir la ficha' : 'Ir al curso'}</button>
      <button class="icon-btn" onclick="retoHecho()">✓ Hecho</button>`}
      ${r.area === 'ccna' ? `<button class="icon-btn" onclick="irA('laboratorios')" title="Encender CML">🧪 CML</button>` : ''}
    </div>
    <div class="hoy-pie">${total} labs hechos (${s.hechos.ccna}/${s.total.ccna} CCNA · ${s.hechos.linux}/${s.total.linux} Linux · ${s.hechos.azure}/${s.total.azure} Azure)</div>`;
}

loadReto();
