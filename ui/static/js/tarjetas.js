// ── Tarjetas de estudio (captura → tarjetas, repaso espaciado) ───
let tjData = null, tjVolteada = false, tjProp = null;

async function loadTarjetas() {
  try { tjData = await (await fetch('/api/tarjetas')).json(); tjVolteada = false; renderTarjetas(); } catch (e) {}
}

function tjLeer(file) {
  return new Promise(res => { const r = new FileReader(); r.onload = () => res(r.result.split(',')[1]); r.readAsDataURL(file); });
}
async function tjArchivo(file) {
  if (!file || !file.type.startsWith('image/')) return;
  tjProponer(await tjLeer(file), file.type);
}
// pegar con Ctrl+V en la pestaña Mi estudio
document.addEventListener('paste', async e => {
  if (!document.getElementById('tab-estudio')?.classList.contains('active')) return;
  const item = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith('image/'));
  if (!item) return;
  e.preventDefault();
  tjArchivo(item.getAsFile());
});
document.addEventListener('DOMContentLoaded', () => {
  const z = document.getElementById('tj-zona');
  if (!z) return;
  z.addEventListener('dragover', e => { e.preventDefault(); z.classList.add('encima'); });
  z.addEventListener('dragleave', () => z.classList.remove('encima'));
  z.addEventListener('drop', e => { e.preventDefault(); z.classList.remove('encima'); tjArchivo(e.dataTransfer.files[0]); });
});

async function tjProponer(imagen, mime, texto) {
  const el = document.getElementById('tj-propuesta');
  el.innerHTML = '<div class="ent-espera">⏳ Leyendo el material y preparando tarjetas… (unos 10 s)</div>';
  tjProp = await (await fetch('/api/tarjetas/proponer', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ imagen, mime, texto }) })).json();
  if (tjProp.error) { el.innerHTML = `<div class="prep-aviso">${esc(tjProp.error)}</div>`; return; }
  el.innerHTML = `<div class="prep-bloque">
    <div class="prep-cab"><b>${tjProp.tarjetas.length} tarjetas propuestas · ${esc(tjProp.materia)}</b><span class="ent-nota">${esc(tjProp.modelo)}</span></div>
    <div class="tj-prop-grid">${tjProp.imagen ? `<img class="tj-mini" src="/api/tarjetas/imagen/${esc(tjProp.imagen)}">` : ''}
    <div>${tjProp.tarjetas.map((t, i) => `<label class="tj-prop"><input type="checkbox" checked data-i="${i}">
      <span><b contenteditable="true" data-campo="pregunta">${esc(t.pregunta)}</b><br><span contenteditable="true" data-campo="respuesta">${esc(t.respuesta)}</span></span></label>`).join('')}</div></div>
    <div class="ent-botones"><button class="icon-btn update" onclick="tjGuardar()">💾 Guardar las marcadas</button>
      <button class="icon-btn" onclick="document.getElementById('tj-propuesta').innerHTML=''">Descartar</button></div>
    <div class="ent-nota">Puedes corregir el texto antes de guardar (pincha encima).</div></div>`;
}

async function tjGuardar() {
  const filas = [...document.querySelectorAll('#tj-propuesta .tj-prop')];
  const elegidas = filas.filter(f => f.querySelector('input').checked).map(f => {
    const i = +f.querySelector('input').dataset.i;
    return { ...tjProp.tarjetas[i], pregunta: f.querySelector('[data-campo=pregunta]').innerText.trim(),
             respuesta: f.querySelector('[data-campo=respuesta]').innerText.trim() };
  });
  await fetch('/api/tarjetas/guardar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tarjetas: elegidas, materia: tjProp.materia, imagen: tjProp.imagen }) });
  document.getElementById('tj-propuesta').innerHTML = `<div class="ent-nota">✓ ${elegidas.length} tarjetas guardadas.</div>`;
  loadTarjetas();
}

function renderTarjetas() {
  if (!tjData) return;
  if (typeof queueHoy === 'function') queueHoy();
  document.getElementById('tj-stats').textContent = tjData.total
    ? `${tjData.total} tarjetas · ${tjData.aprendidas} aprendidas · ${tjData.hechas_hoy} repasos hoy` : '';
  const el = document.getElementById('tj-repaso');
  const t = tjData.cola[0];
  if (!t) {
    el.innerHTML = `<div class="ingles-card fin"><div class="ingles-sub">${tjData.total ? '✅ Repaso de hoy hecho' : 'Aún no tienes tarjetas: pega una captura a la izquierda.'}</div></div>`;
    return;
  }
  el.innerHTML = `<div class="ingles-card">
    <div class="ingles-meta"><span>${esc(t.materia)} · ${t.caja === 0 ? '🆕 nueva' : 'caja ' + t.caja}</span><span>quedan ${tjData.cola.length}</span></div>
    <div class="tj-pregunta">${esc(t.pregunta)}</div>
    ${tjVolteada ? `<div class="ingles-es">${esc(t.respuesta)}</div>
      ${t.explicacion ? `<div class="ingles-nota">💡 ${esc(t.explicacion)}</div>` : ''}
      ${t.imagen ? `<details class="ent-nota"><summary>Ver la captura</summary><img class="tj-mini" src="/api/tarjetas/imagen/${esc(t.imagen)}"></details>` : ''}
      <div class="ingles-botones"><button class="icon-btn ingles-no" onclick="tjResponder('${t.id}', false)">✗ No la sabía</button>
        <button class="icon-btn update" onclick="tjResponder('${t.id}', true)">✓ La sabía</button></div>`
    : `<div class="ingles-botones"><button class="icon-btn web" onclick="tjVolteada = true; renderTarjetas()">👁 Ver respuesta</button></div>`}
  </div>`;
}

async function tjResponder(id, acierto) {
  await fetch('/api/tarjetas/repaso', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, acierto }) });
  loadTarjetas();
}

loadTarjetas();
