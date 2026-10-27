// ── Inglés (vocabulario de las ofertas, repaso espaciado) ────────
let inglesData = null;
let inglesVolteada = false;

async function loadIngles() {
  try {
    const res = await fetch('/api/ingles');
    inglesData = await res.json();
    inglesVolteada = false;
    renderIngles();
  } catch (e) {}
}

function renderIngles() {
  if (typeof queueHoy === 'function') queueHoy();
  if (!inglesData) return;
  const st = inglesData.stats;
  const badge = document.getElementById('count-ingles');
  badge.style.display = st.pendientes_hoy ? '' : 'none';
  badge.textContent = st.pendientes_hoy || '';

  document.getElementById('ingles-stats').innerHTML = `
    <span>🔥 <b>${st.racha}</b> día${st.racha === 1 ? '' : 's'} seguidos</span>
    <span>✅ <b>${st.aprendidas}</b> aprendidas</span>
    <span>📈 <b>${st.en_curso}</b> en curso</span>
    <span>🆕 <b>${st.sin_empezar}</b> sin empezar</span>
    <span>💼 <b>${st.de_ofertas}</b> de tus ofertas</span>`;

  renderInglesTarjeta();
  renderInglesTodas();
}

// el término resaltado dentro de su frase de ejemplo
function resaltar(frase, termino) {
  const i = frase.toLowerCase().indexOf(termino.toLowerCase());
  if (i < 0) return esc(frase);
  return esc(frase.slice(0, i)) + '<mark>' + esc(frase.slice(i, i + termino.length)) + '</mark>' + esc(frase.slice(i + termino.length));
}

function renderInglesTarjeta() {
  const el = document.getElementById('ingles-repaso');
  const t = inglesData.cola[0];
  if (!t) {
    el.innerHTML = `<div class="ingles-card fin">
      <div class="ingles-en">✅ Repaso de hoy hecho</div>
      <div class="ingles-sub">${inglesData.stats.hechas_hoy} repasos hoy. Mañana habrá más; lo que aciertas se espacia solo.</div>
      ${inglesData.stats.de_ofertas ? '' : '<div class="ingles-sub">Pulsa «🧠 Sacar de mis ofertas» para añadir el vocabulario de las ofertas que te interesan.</div>'}
    </div>`;
    return;
  }
  const quedan = inglesData.cola.length;
  const origen = t.origen === 'oferta' && t.oferta
    ? `💼 de «${esc(t.oferta.titulo)}»${t.oferta.empresa ? ' · ' + esc(t.oferta.empresa) : ''}`
    : '📋 vocabulario habitual de anuncios IT';
  const voz = `<button class="icon-btn" onclick="pronunciar('${t.id}', 'en')" title="Escuchar (tecla P)">🔊</button>`;
  const vozFrase = t.modo !== 'es' && t.ejemplo ? ` <button class="icon-btn ingles-voz-frase" onclick="pronunciar('${t.id}', 'ejemplo')" title="Escuchar la frase">🔊 frase</button>` : '';
  const botones = `
      <div class="ingles-botones">
        <button class="icon-btn ingles-no" onclick="responderIngles('${t.id}', false)">✗ No la sabía</button>
        <button class="icon-btn update" onclick="responderIngles('${t.id}', true)">✓ La sabía</button>
      </div>
      <div class="ingles-atajos">teclado: P escuchar · ← no la sabía · → la sabía</div>`;
  const meta = `<div class="ingles-meta"><span>${t.caja === 0 ? '🆕 nueva' : 'caja ' + t.caja + ' de 5'}</span><span>quedan ${quedan}</span></div>`;

  // modo «es»: la frase sale de una oferta en español → ¿cómo lo dirías en inglés?
  if (t.modo === 'es') {
    el.innerHTML = `<div class="ingles-card">
      ${meta}
      <div class="ingles-pregunta">¿Cómo lo dirías en inglés en una entrevista?</div>
      <div class="ingles-en ingles-es-frente">${esc(t.es)}</div>
      ${t.ejemplo ? `<div class="ingles-ejemplo">“${resaltar(t.ejemplo, t.es)}”</div>` : ''}
      <div class="ingles-sub">${origen}</div>
      ${inglesVolteada ? `<div class="ingles-respuesta">${esc(t.en)} ${voz}</div>${botones}` : `
        <div class="ingles-botones">
          <button class="icon-btn web" onclick="voltearIngles()">👁 Ver en inglés <small>(espacio)</small></button>
        </div>`}
    </div>`;
    return;
  }

  el.innerHTML = `<div class="ingles-card">
    ${meta}
    <div class="ingles-en">${esc(t.en)} ${voz}</div>
    ${t.ejemplo ? `<div class="ingles-ejemplo">“${resaltar(t.ejemplo, t.en)}”${vozFrase}</div>` : ''}
    <div class="ingles-sub">${origen}</div>
    ${inglesVolteada ? `
      <div class="ingles-es">${esc(t.es)}</div>
      ${t.nota ? `<div class="ingles-nota">💡 ${esc(t.nota)}</div>` : ''}${botones}` : `
      <div class="ingles-botones">
        <button class="icon-btn web" onclick="voltearIngles()">👁 Ver traducción <small>(espacio)</small></button>
      </div>`}
  </div>`;
}

function voltearIngles() {
  inglesVolteada = true;
  renderInglesTarjeta();
}

async function responderIngles(id, acierto) {
  await fetch('/api/ingles/repaso', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, acierto }),
  });
  loadIngles();
}

let _audioIngles = null;
function pronunciar(id, que) {
  // voz neuronal (Piper) generada en el panel; la del navegador sonaba robótica
  try {
    if (_audioIngles) _audioIngles.pause();
    _audioIngles = new Audio(`/api/ingles/audio?id=${encodeURIComponent(id)}&que=${que}`);
    _audioIngles.play().catch(() => {});
  } catch (e) {}
}

async function extraerIngles() {
  await fetch('/api/ingles/extraer', { method: 'POST' });
}

async function borrarIngles(id) {
  await fetch('/api/ingles/borrar', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  });
  loadIngles();
}

function renderInglesTodas() {
  const el = document.getElementById('ingles-todas');
  const caja = c => c >= 4 ? '✅' : c > 0 ? '📈' : '🆕';
  el.innerHTML = inglesData.todas.map(t => `
    <div class="ingles-fila">
      <span title="caja ${t.caja}">${caja(t.caja)}</span>
      <b>${esc(t.en)}</b>
      <span class="ingles-fila-es">${esc(t.es)}</span>
      <span class="ingles-fila-origen">${t.origen === 'oferta' ? '💼' : ''}</span>
      <button class="icon-btn" onclick="borrarIngles('${t.id}')" title="Quitar esta expresión">✕</button>
    </div>`).join('');
}

// espacio voltea, ← / → responden (solo con la pestaña Inglés abierta)
document.addEventListener('keydown', (e) => {
  if (!document.getElementById('tab-ingles')?.classList.contains('active')) return;
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
  const t = inglesData?.cola?.[0];
  if (!t) return;
  if (e.key === 'p' || e.key === 'P') { e.preventDefault(); pronunciar(t.id, 'en'); }
  else if (e.key === ' ' && !inglesVolteada) { e.preventDefault(); voltearIngles(); }
  else if (inglesVolteada && e.key === 'ArrowRight') { e.preventDefault(); responderIngles(t.id, true); }
  else if (inglesVolteada && e.key === 'ArrowLeft') { e.preventDefault(); responderIngles(t.id, false); }
});

socket.on('ingles_updated', loadIngles);
loadIngles();
