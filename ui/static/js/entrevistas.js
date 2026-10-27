// ── Entrevistas (simulador por voz) ──────────────────────────────
let entLista = { sesiones: [], ofertas: [] };
let entActual = null;          // sesión abierta
let entOpc = { idioma: 'es', preguntas: 6 };
let entGrab = null;            // {inicio, timer} mientras se graba
let entBorrador = null;        // {texto, segundos, audio} tras grabar
let entOyendo = -1;            // último turno del entrevistador ya reproducido
let entAudio = null;

async function loadEntrevistas() {
  try {
    entLista = await (await fetch('/api/entrevistas')).json();
    renderEntLado();
  } catch (e) {}
}

function entIdioma(i, btn) { entOpc.idioma = i; marcarOpcion(btn); }
function entPreguntas(n, btn) { entOpc.preguntas = n; marcarOpcion(btn); }
function marcarOpcion(btn) {
  btn.parentElement.querySelectorAll('.beca-filtro').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

function renderEntLado(preseleccion) {
  const sel = document.getElementById('ent-oferta');
  const actual = preseleccion ?? sel.value;
  sel.innerHTML = '<option value="">Administrador de sistemas (general)</option>' + entLista.ofertas.map(o =>
    `<option value="${esc(o.id)}">${o.estado ? '★ ' : ''}${esc(o.titulo.slice(0, 60))}${o.empresa ? ' · ' + esc(o.empresa) : ''}</option>`).join('');
  sel.value = actual || '';
  document.getElementById('ent-historial').innerHTML = entLista.sesiones.length ? entLista.sesiones.map(s => `
    <div class="ent-hist ${entActual?.id === s.id ? 'activa' : ''}" onclick="abrirEntrevista('${s.id}')">
      <span class="ent-hist-nota ${s.nota == null ? '' : s.nota >= 7 ? 'buena' : s.nota >= 5 ? 'media' : 'baja'}">${s.nota ?? (s.estado === 'terminada' ? '–' : '…')}</span>
      <span class="hoy-fila-txt">${s.idioma === 'en' ? '🇬🇧 ' : ''}${esc(s.titulo)}<small>${esc(s.creada.replace('T', ' '))}</small></span>
    </div>`).join('') : '<span class="hoy-vacio">Todavía ninguna.</span>';
}

function ensayarOferta(id) {
  irA('entrevistas');
  loadEntrevistas().then(() => renderEntLado(id));
}

async function nuevaEntrevista() {
  const oferta_id = document.getElementById('ent-oferta').value;
  const r = await (await fetch('/api/entrevistas/nueva', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ oferta_id, idioma: entOpc.idioma, preguntas: entOpc.preguntas }),
  })).json();
  entActual = { id: r.id, turnos: [], estado: 'en_curso', titulo: '…', idioma: entOpc.idioma };
  entOyendo = -1;
  entBorrador = null;
  renderEntMain(true);
  loadEntrevistas();
}

async function abrirEntrevista(id, nueva) {
  entActual = await (await fetch('/api/entrevistas/' + id)).json();
  if (!nueva) entOyendo = entActual.turnos.length - 1;   // al reabrir no se repite el audio
  renderEntMain();
  renderEntLado();
}

socket.on('entrevista_turno', ({ id }) => {
  if (entActual?.id === id) abrirEntrevista(id, true);
  loadEntrevistas();
});

function oir(n) {
  if (entAudio) entAudio.pause();
  entAudio = new Audio(`/api/entrevistas/audio?id=${entActual.id}&n=${n}`);
  entAudio.play().catch(() => {});
}

function renderEntMain(esperando) {
  const el = document.getElementById('ent-main');
  const s = entActual;
  if (!s) return;
  const turnos = s.turnos.map((t, n) => `
    <div class="ent-turno ${t.rol}">
      <div class="ent-burbuja">${t.tipo === 'repregunta' ? '<small>repregunta</small>' : ''}${esc(t.texto)}</div>
      ${t.rol === 'entrevistador' || t.audio ? `<button class="icon-btn ent-oir" onclick="oir(${n})" title="${t.rol === 'candidato' ? 'Escúchate' : 'Escuchar'}">🔊</button>` : ''}
    </div>`).join('');
  const ultimo = s.turnos[s.turnos.length - 1];
  const toca = s.estado === 'en_curso' && ultimo?.rol === 'entrevistador';
  let accion = '';
  if (s.estado === 'evaluando') accion = '<div class="ent-espera">⏳ Preparando tu informe…</div>';
  else if (s.estado === 'terminada') accion = '';
  else if (!toca || esperando) accion = '<div class="ent-espera">⏳ El entrevistador está pensando…</div>';
  else if (entGrab) accion = `
    <div class="ent-grabando"><span class="ent-punto"></span> Grabando <b id="ent-crono">0:00</b>
      <button class="icon-btn ingles-no" onclick="pararGrabacion()">■ He terminado</button></div>`;
  else if (entBorrador) accion = `
    <textarea class="carrera-input ent-texto" id="ent-texto" rows="4">${esc(entBorrador.texto || '')}</textarea>
    ${entBorrador.error ? `<div class="ent-nota" style="color:var(--amber)">${esc(entBorrador.error)}</div>` : '<div class="ent-nota">Revisa la transcripción (puedes corregirla) y envíala.</div>'}
    <div class="ent-botones">
      <button class="icon-btn" onclick="entBorrador = null; empezarGrabacion()">🎙 Repetir</button>
      <button class="icon-btn update" onclick="enviarRespuesta()">➤ Enviar respuesta</button>
    </div>`;
  else accion = `
    <div class="ent-botones">
      <button class="icon-btn update ent-grabar" onclick="empezarGrabacion()">🎙 Responder hablando</button>
      <button class="icon-btn" onclick="entBorrador = { texto: '' }; renderEntMain(); document.getElementById('ent-texto').focus()">⌨ Escribir</button>
    </div>`;
  const terminar = s.estado === 'en_curso' && s.turnos.some(t => t.rol === 'candidato')
    ? `<button class="icon-btn" onclick="terminarEntrevista()" title="Cortar aquí y ver el informe">⏹ Terminar y evaluar</button>` : '';
  el.innerHTML = `
    <div class="ent-cab">
      <div><div class="ent-titulo">${s.idioma === 'en' ? '🇬🇧 ' : ''}${esc(s.titulo)}</div><div class="ent-nota">${esc(s.empresa || '')}</div></div>
      <div class="ent-botones">${terminar}${s.estado === 'terminada' ? `<button class="icon-btn" onclick="borrarEntrevista('${s.id}')">🗑</button>` : ''}</div>
    </div>
    <div class="ent-chat" id="ent-chat">${turnos}</div>
    <div class="ent-accion">${accion}</div>
    ${s.informe ? renderInforme(s.informe, s.idioma) : ''}`;
  const chat = document.getElementById('ent-chat');
  chat.scrollTop = chat.scrollHeight;
  // la pregunta nueva se oye sola
  if (toca && s.turnos.length - 1 > entOyendo) { entOyendo = s.turnos.length - 1; oir(entOyendo); }
}

async function empezarGrabacion() {
  if (entAudio) entAudio.pause();
  const r = await (await fetch('/api/entrevistas/grabar', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: entActual.id }) })).json();
  if (!r.ok) return;
  entGrab = { inicio: Date.now() };
  renderEntMain();
  entGrab.timer = setInterval(() => {
    const s = Math.floor((Date.now() - entGrab.inicio) / 1000);
    const c = document.getElementById('ent-crono');
    if (c) c.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }, 500);
}

async function pararGrabacion() {
  clearInterval(entGrab.timer);
  entGrab = null;
  entBorrador = { texto: '⏳ pasando tu voz a texto…' };
  renderEntMain();
  entBorrador = await (await fetch('/api/entrevistas/parar', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: entActual.id }) })).json();
  renderEntMain();
}

async function enviarRespuesta() {
  const texto = document.getElementById('ent-texto').value.trim();
  if (!texto) return;
  const b = entBorrador || {};
  entBorrador = null;
  entActual.turnos.push({ rol: 'candidato', texto });
  renderEntMain(true);
  await fetch('/api/entrevistas/responder', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: entActual.id, texto, segundos: b.segundos || 0, audio: b.audio || '' }),
  });
}

async function terminarEntrevista() {
  await fetch('/api/entrevistas/terminar', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: entActual.id }) });
  entActual.estado = 'evaluando';
  renderEntMain();
}

async function borrarEntrevista(id) {
  if (!confirm('¿Borrar esta entrevista?')) return;
  await fetch('/api/entrevistas/borrar', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
  entActual = null;
  document.getElementById('ent-main').innerHTML = '';
  loadEntrevistas();
}

// los modelos marcan negritas con **…**: escapar y luego convertir solo eso
const md = t => esc(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');

function renderInforme(inf, idioma) {
  const nota = n => n == null ? '–' : n;
  const clase = n => n == null ? '' : n >= 7 ? 'buena' : n >= 5 ? 'media' : 'baja';
  return `<div class="ent-informe">
    <div class="ent-informe-cab">
      <div class="ent-nota-grande ${clase(inf.nota)}">${nota(inf.nota)}<small>/10</small></div>
      <div><div>${md(inf.resumen)}</div>${inf.minutos_hablando ? `<div class="ent-nota">Hablaste ${inf.minutos_hablando} min</div>` : ''}</div>
    </div>
    ${inf.avisos?.length ? `<div class="prep-aviso"><b>⚠ Cuidado con las respuestas mejoradas: esto no está en tu CV</b><ul>${inf.avisos.map(a => `<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}
    <div class="prep-dos">
      <div class="prep-bloque"><b>✅ Lo que hiciste bien</b><ul>${inf.fuertes.map(x => `<li>${md(x)}</li>`).join('')}</ul></div>
      <div class="prep-bloque"><b>🎯 Para la próxima</b><ul>${inf.mejorar.map(x => `<li>${md(x)}</li>`).join('')}</ul></div>
    </div>
    ${inf.ingles?.length ? `<div class="prep-bloque"><b>🇬🇧 Tu inglés</b>
      ${inf.ingles.map(x => `<div class="ent-ingles"><s>${esc(x.dijiste)}</s> → <b>${esc(x.mejor)}</b><div class="ent-nota">${esc(x.por_que)}</div></div>`).join('')}</div>` : ''}
    <div class="prep-bloque"><b>🗒 Respuesta a respuesta</b>
      ${inf.respuestas.map(r => `<details class="prep-q">
        <summary><span class="ent-hist-nota ${clase(r.nota)}">${nota(r.nota)}</span> ${esc(r.pregunta)}</summary>
        <div class="ent-nota">👍 ${md(r.bien)}</div><div class="ent-nota">🎯 ${md(r.mejorar)}</div>
        <div class="prep-texto ent-mejorada">💬 ${md(r.mejorada)}</div></details>`).join('')}
    </div>
  </div>`;
}

loadEntrevistas();
