// ── Contactos ────────────────────────────────────────────────────
let contactosData = null;
const CT_ESTADO = { por_contactar: '⚪ por contactar', contactado: '📨 contactado', respondio: '💬 respondió',
                    conversacion: '🤝 en conversación', frio: '🧊 frío' };
const CT_MSG = { conectar: '🔗 Conectar (LinkedIn)', seguimiento: '📨 Seguimiento', gracias: '🙏 Gracias tras entrevista',
                 charla: '☕ Charla informativa', referencia: '⭐ Pedir referencia' };

async function loadContactos() {
  try { contactosData = await (await fetch('/api/contactos')).json(); renderContactos(); } catch (e) {}
}

function renderContactos() {
  if (typeof queueHoy === 'function') queueHoy();
  if (!contactosData) return;
  const badge = document.getElementById('count-contactos');
  if (badge) { badge.style.display = contactosData.pendientes ? '' : 'none'; badge.textContent = contactosData.pendientes ? contactosData.pendientes + ' ⏰' : ''; }
  const el = document.getElementById('ct-lista');
  if (!contactosData.contactos.length) {
    el.innerHTML = `<div class="ent-vacio"><div class="ent-vacio-icono">🤝</div><div>Apunta a la gente con la que hablas: reclutadores, personas de las empresas que te interesan, compañeros del curso…</div>
      <div class="ent-nota">La mayoría de los trabajos llegan por contactos. Con 2-3 mensajes por semana se nota.</div></div>`;
    return;
  }
  el.innerHTML = contactosData.contactos.map(c => `
    <div class="ct-card ${c.toca ? 'toca' : ''}">
      <div class="ct-cab">
        <div><div class="ag-titulo"><b>${esc(c.nombre)}</b>${c.rol ? ' · ' + esc(c.rol) : ''}</div>
          <div class="ent-nota">${esc(c.empresa || '')}${c.enlace ? ` · <a href="#" data-url="${esc(c.enlace)}" onclick="abrirBeca(this.dataset.url); return false">${esc(c.enlace.replace(/^https?:\/\/(www\.)?/, '').slice(0, 40))}</a>` : ''}</div></div>
        <select class="carrera-input ct-estado" onchange="anotarContacto('${c.id}', 'Cambio de estado', this.value, 0)">
          ${contactosData.estados.map(e => `<option value="${e}" ${e === c.estado ? 'selected' : ''}>${CT_ESTADO[e]}</option>`).join('')}</select>
      </div>
      ${c.toca ? `<div class="ct-toca">⏰ Toca: ${esc(c.proximo_que || 'escribirle')} (${esc(c.proximo)})</div>` : c.proximo ? `<div class="ent-nota">Próximo: ${esc(c.proximo_que || '')} · ${esc(c.proximo)}</div>` : ''}
      ${c.notas ? `<div class="ent-nota">📝 ${esc(c.notas)}</div>` : ''}
      ${c.historial.length ? `<details class="ent-nota"><summary>Historial (${c.historial.length}) · último ${esc(c.ultimo_contacto || '')}</summary>
        ${c.historial.map(h => `<div>${esc(h.fecha)} — ${esc(h.texto)}</div>`).join('')}</details>` : ''}
      <div class="ent-botones">
        <details class="oferta-menu"><summary class="icon-btn">✍ Borrador</summary><div class="svc-menu-pop">
          ${Object.entries(CT_MSG).map(([k, v]) => `<button class="icon-btn" onclick="cerrarMenus(); borradorContacto('${c.id}', '${k}', 'es')">${v}</button>`).join('')}
          <button class="icon-btn" onclick="cerrarMenus(); borradorContacto('${c.id}', 'conectar', 'en')">🇬🇧 Connect (English)</button>
        </div></details>
        <button class="icon-btn update" onclick="anotarContacto('${c.id}', prompt('¿Qué le has dicho / qué ha pasado?') || 'Contacto', '', 7)" title="Anota el contacto de hoy y programa el siguiente en 7 días">✓ Le escribí hoy</button>
        <button class="icon-btn" onclick="editarContacto('${c.id}')">✎</button>
        <button class="icon-btn" onclick="borrarContacto('${c.id}')">🗑</button>
      </div>
      <div class="ct-borrador" id="ct-borrador-${c.id}"></div>
    </div>`).join('');
}

async function guardarContacto() {
  const v = id => document.getElementById(id).value;
  if (!v('ct-nombre').trim()) { alert('Pon al menos el nombre'); return; }
  const r = await (await fetch('/api/contactos/guardar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: v('ct-id'), nombre: v('ct-nombre'), empresa: v('ct-empresa'), rol: v('ct-rol'), enlace: v('ct-enlace'),
                           notas: v('ct-notas'), proximo: v('ct-proximo'), proximo_que: v('ct-proximo-que') }) })).json();
  if (r.error) { alert(r.error); return; }
  limpiarContacto(); loadContactos();
}
function limpiarContacto() {
  ['ct-id', 'ct-nombre', 'ct-empresa', 'ct-rol', 'ct-enlace', 'ct-notas', 'ct-proximo', 'ct-proximo-que'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('ct-form-titulo').textContent = '🤝 Nuevo contacto';
}
function editarContacto(id) {
  const c = contactosData.contactos.find(x => x.id === id);
  [['ct-id', c.id], ['ct-nombre', c.nombre], ['ct-empresa', c.empresa], ['ct-rol', c.rol], ['ct-enlace', c.enlace],
   ['ct-notas', c.notas], ['ct-proximo', c.proximo], ['ct-proximo-que', c.proximo_que]].forEach(([k, v]) => document.getElementById(k).value = v || '');
  document.getElementById('ct-form-titulo').textContent = '✎ Editar contacto';
}
async function anotarContacto(id, texto, estado, dias) {
  await fetch('/api/contactos/anotar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, texto, estado, dias }) });
  loadContactos();
}
async function borrarContacto(id) {
  if (!confirm('¿Borrar este contacto?')) return;
  await fetch('/api/contactos/borrar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
  loadContactos();
}
async function borradorContacto(id, tipo, idioma) {
  const el = document.getElementById('ct-borrador-' + id);
  el.innerHTML = '<div class="ent-espera">⏳ Escribiendo el borrador…</div>';
  const r = await (await fetch('/api/contactos/borrador', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, tipo, idioma }) })).json();
  el.innerHTML = r.error ? `<div class="prep-aviso">${esc(r.error)}</div>` : `
    <div class="prep-bloque"><div class="prep-cab"><b>${esc(CT_MSG[tipo] || tipo)}</b><button class="icon-btn" onclick="copiarTexto(this)">⧉ Copiar</button></div>
      ${r.avisos?.length ? `<div class="prep-aviso">⚠ ${r.avisos.map(esc).join('<br>')}</div>` : ''}
      ${r.asunto ? `<div class="ent-nota">Asunto: ${esc(r.asunto)}</div>` : ''}
      <div class="prep-texto" contenteditable="true">${esc(r.mensaje)}</div>
      <div class="ent-nota">${r.caracteres} caracteres${tipo === 'conectar' ? ' (LinkedIn admite 300)' : ''} · revísalo y retócalo antes de enviarlo.</div></div>`;
}

loadContactos();
