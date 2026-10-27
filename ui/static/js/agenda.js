// ── Agenda ───────────────────────────────────────────────────────
let agendaData = null;
let agTipo = 'entrevista';

async function loadAgenda() {
  try { agendaData = await (await fetch('/api/agenda')).json(); renderAgenda(); } catch (e) {}
}

function renderAgendaTipos() {
  const nombres = { entrevista: 'Entrevista', examen: 'Examen', beca: 'Beca/curso', tramite: 'Trámite', estudio: 'Estudio', otro: 'Otro' };
  const orden = ['entrevista', 'examen', 'tramite', 'beca', 'estudio', 'otro'];
  document.getElementById('ag-tipos').innerHTML = orden.filter(k => agendaData.tipos[k]).map(k => [k, agendaData.tipos[k]]).map(([k, ic]) =>
    `<button class="beca-filtro ${k === agTipo ? 'active' : ''}" onclick="agTipo='${k}'; renderAgendaTipos()">${ic} ${nombres[k]}</button>`).join('');
}

const cuandoDias = d => d === 0 ? 'hoy' : d === 1 ? 'mañana' : d === -1 ? 'ayer' : d > 0 ? `en ${d} días` : `hace ${-d} días`;
function fechaLarga(f) { return new Date(f + 'T00:00:00').toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' }); }

function renderAgenda() {
  if (typeof queueHoy === 'function') queueHoy();
  if (!agendaData) return;
  renderAgendaTipos();
  const fut = agendaData.eventos.filter(e => e.dias >= 0 && !e.hecho);
  const pas = agendaData.eventos.filter(e => e.dias < 0 || e.hecho).reverse();
  const fila = e => `
    <div class="ag-evento ${e.dias <= 1 && e.dias >= 0 && !e.hecho ? 'pronto' : ''} ${e.hecho ? 'hecho' : ''}">
      <div class="ag-fecha"><b>${new Date(e.fecha + 'T00:00:00').getDate()}</b><small>${new Date(e.fecha + 'T00:00:00').toLocaleDateString('es-ES', { month: 'short' })}</small></div>
      <div class="ag-cuerpo">
        <div class="ag-titulo">${e.icono} ${esc(e.titulo)}</div>
        <div class="ent-nota">${esc(fechaLarga(e.fecha))}${e.hora ? ' · ' + esc(e.hora) : ''} · <b>${cuandoDias(e.dias)}</b>${e.lugar ? ' · 📍 ' + esc(e.lugar) : ''}</div>
        ${e.nota ? `<div class="ent-nota">${esc(e.nota)}</div>` : ''}
      </div>
      ${e.solo_lectura ? '<span class="ent-nota">desde Tu estudio</span>' : `<div class="ent-botones">
        <button class="icon-btn" onclick='editarEvento(${JSON.stringify(e.id)})' title="Editar">✎</button>
        <button class="icon-btn" onclick='marcarEvento(${JSON.stringify(e.id)}, ${!e.hecho})' title="${e.hecho ? 'Reabrir' : 'Hecho'}">${e.hecho ? '↺' : '✓'}</button>
        <button class="icon-btn" onclick='borrarEvento(${JSON.stringify(e.id)})' title="Borrar">🗑</button></div>`}
    </div>`;
  document.getElementById('agenda-lista').innerHTML = `
    <div class="ent-bloque-titulo">Próximamente</div>
    ${fut.length ? fut.map(fila).join('') : '<span class="hoy-vacio">Nada apuntado. Añade tu próxima entrevista, el examen o una cita.</span>'}
    ${pas.length ? `<details class="ingles-lista"><summary>Pasado y hecho (${pas.length})</summary>${pas.map(fila).join('')}</details>` : ''}`;
}

async function guardarEvento() {
  const v = id => document.getElementById(id).value;
  if (!v('ag-fecha')) { alert('Pon la fecha'); return; }
  const r = await (await fetch('/api/agenda/guardar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: v('ag-id'), titulo: v('ag-titulo'), tipo: agTipo, fecha: v('ag-fecha'), hora: v('ag-hora'),
                           lugar: v('ag-lugar'), nota: v('ag-nota'), oferta_id: document.getElementById('ag-id').dataset.oferta || null }) })).json();
  if (r.error) { alert(r.error); return; }
  limpiarEvento();
  loadAgenda();
}
function limpiarEvento() {
  ['ag-id', 'ag-titulo', 'ag-fecha', 'ag-hora', 'ag-lugar', 'ag-nota'].forEach(id => document.getElementById(id).value = '');
  delete document.getElementById('ag-id').dataset.oferta;
  document.getElementById('agenda-form-titulo').textContent = '🗓 Nuevo evento';
}
function editarEvento(id) {
  const e = agendaData.eventos.find(x => x.id === id);
  if (!e) return;
  [['ag-id', e.id], ['ag-titulo', e.titulo], ['ag-fecha', e.fecha], ['ag-hora', e.hora || ''], ['ag-lugar', e.lugar || ''], ['ag-nota', e.nota || '']]
    .forEach(([k, val]) => document.getElementById(k).value = val);
  agTipo = e.tipo; renderAgendaTipos();
  document.getElementById('agenda-form-titulo').textContent = '✎ Editar evento';
}
async function marcarEvento(id, hecho) {
  await fetch('/api/agenda/hecho', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, hecho }) });
  loadAgenda();
}
async function borrarEvento(id) {
  if (!confirm('¿Borrar este evento?')) return;
  await fetch('/api/agenda/borrar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
  loadAgenda();
}
// desde una oferta: «🗓 Apuntar entrevista»
function apuntarEntrevista(ofertaId) {
  const it = (ofertasData.items || []).find(i => i.id === ofertaId);
  irA('agenda');
  limpiarEvento();
  agTipo = 'entrevista'; renderAgendaTipos();
  document.getElementById('ag-titulo').value = it ? `Entrevista: ${it.titulo}${it.empresa ? ' (' + it.empresa + ')' : ''}`.slice(0, 120) : 'Entrevista';
  document.getElementById('ag-id').dataset.oferta = ofertaId;
  document.getElementById('ag-fecha').focus();
}

loadAgenda();
setInterval(loadAgenda, 10 * 60000);
