// ── Hoy (portada) ────────────────────────────────────────────────
// No pide datos propios: reutiliza lo que ya cargan los demás módulos
// (carreraData, ofertasData, becasData y las tarjetas de servicios) y se
// vuelve a pintar cuando cualquiera de ellos se actualiza.

function irA(tab) {
  const nav = [...document.querySelectorAll('.nav-item')]
    .find(n => (n.getAttribute('onclick') || '').includes(`'${tab}'`));
  switchTab(tab, nav);
  document.getElementById('main').scrollTop = 0;
}

let _hoyPendiente = false;
function queueHoy() {
  if (_hoyPendiente) return;
  _hoyPendiente = true;
  setTimeout(() => { _hoyPendiente = false; renderHoy(); }, 0);
}

function diasDesde(iso) {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso + 'T00:00:00')) / 86400000);
}

function renderHoy() {
  renderHoyCabecera();
  renderHoyCarrera();
  renderHoyOfertas();
  renderHoyIngles();
  renderHoyEstudio();
  renderHoyAgenda();
  renderHoyServicios();
  renderHoyBecas();
}

function renderHoyCabecera() {
  const h = new Date().getHours();
  const saludo = h < 6 ? 'Buenas noches' : h < 14 ? 'Buenos días' : h < 21 ? 'Buenas tardes' : 'Buenas noches';
  const nombre = carreraData?.perfil ? carreraData.perfil.split(' ')[0] : '';
  document.getElementById('hoy-titulo').textContent = saludo + (nombre ? ', ' + nombre : '');
  document.getElementById('hoy-fecha').textContent =
    new Date().toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' });

  const alertas = [];
  const st = ofertasData?.stats || {};
  if (st.seguimiento) alertas.push(`<span class="hoy-alerta warn" onclick="irA('ofertas'); filtrarOfertas('seguimiento', document.querySelector('#ofertas-filtros [onclick*=seguimiento]'))">⏰ ${st.seguimiento} candidatura${st.seguimiento > 1 ? 's' : ''} sin respuesta</span>`);
  const malos = [...document.querySelectorAll('.service-card.on.unhealthy .service-name')].map(n => n.textContent);
  if (malos.length) alertas.push(`<span class="hoy-alerta err" onclick="irA('sistema')">⚠ ${malos.map(esc).join(', ')} no responde${malos.length > 1 ? 'n' : ''}</span>`);
  const tocaContactar = (contactosData?.contactos || []).filter(c => c.toca);
  if (tocaContactar.length) alertas.push(`<span class="hoy-alerta warn" onclick="irA('contactos'); loadContactos()">🤝 Toca escribir a ${tocaContactar.slice(0, 2).map(c => esc(c.nombre)).join(', ')}${tocaContactar.length > 2 ? ` y ${tocaContactar.length - 2} más` : ''}</span>`);
  const olvidados = (labsData?.contenedores || []).filter(c => (c.horas || 0) >= 6);
  if (olvidados.length) alertas.push(`<span class="hoy-alerta warn" onclick="irA('laboratorios')">🧪 ${olvidados.length} contenedor${olvidados.length > 1 ? 'es' : ''} de laboratorio encendido${olvidados.length > 1 ? 's' : ''} desde hace ${Math.floor(Math.max(...olvidados.map(c => c.horas)))} h</span>`);
  const mant = (mantData?.checks || []).filter(c => c.estado === 'warn' || c.estado === 'err');
  if (mant.length) alertas.push(`<span class="hoy-alerta ${mant.some(c => c.estado === 'err') ? 'err' : 'warn'}" onclick="irA('mantenimiento')">🩺 ${mant.length === 1 ? esc(mant[0].titulo) : mant.length + ' avisos de mantenimiento'}</span>`);
  const disco = parseInt(document.getElementById('stat-disk')?.textContent);
  if (disco >= 85) alertas.push(`<span class="hoy-alerta err">💾 Disco al ${disco}%</span>`);
  document.getElementById('hoy-alertas').innerHTML = alertas.join('');
}

function siguienteTarea() {
  for (const f of carreraData?.fases || []) {
    for (const o of f.objetivos) {
      const t = o.tareas.find(t => !t.done);
      if (t) return { tarea: t, objetivo: o, fase: f };
    }
  }
  return null;
}

function renderHoyCarrera() {
  const el = document.getElementById('hoy-carrera');
  if (!carreraData) return;
  const st = carreraData.stats;
  const sig = siguienteTarea();
  const ritmo = st.semana > 0 ? `🔥 ${st.semana} avance${st.semana > 1 ? 's' : ''} esta semana`
              : st.dias_sin_avance == null ? '✨ Marca tu primera tarea'
              : `💤 ${st.dias_sin_avance} días sin avances — un paso pequeño hoy cuenta`;
  el.innerHTML = (sig ? `
      <div class="hoy-tarea ${sig.tarea.hito ? 'hito' : ''}">${esc(sig.tarea.texto)}</div>
      <div class="hoy-sub">${esc(sig.objetivo.icono || '')} ${esc(sig.objetivo.titulo)} · ${esc(sig.fase.titulo)}</div>
      <div class="hoy-acciones">
        <button class="icon-btn update" onclick="toggleTarea('${esc(sig.tarea.id)}')">✓ Hecha</button>
        <button class="icon-btn" onclick="irA('carrera')">Ver el plan</button>
      </div>` : '<div class="hoy-tarea">🎉 Plan completado</div>') + `
    <div class="hoy-pie">${ritmo} · ${st.pct}% del plan</div>`;
}

function renderHoyOfertas() {
  const el = document.getElementById('hoy-ofertas');
  const st = ofertasData?.stats;
  if (!st) return;
  const items = ofertasData.items || [];
  const seg = items.filter(i => i.seguimiento).slice(0, 3);
  const encajan = items.filter(i => !i.estado && (i.eval ? i.eval.encaje >= 60 : i.relevancia >= 60)).slice(0, 3);
  const pct = Math.min(100, 100 * (st.semana || 0) / (st.meta_semana || 10));
  const fila = (i, extra) => `
    <div class="hoy-fila">
      <span class="oferta-score ${i.eval ? claseScore(i.eval.encaje) : ''}">${i.eval ? i.eval.encaje : '~' + i.relevancia}</span>
      <span class="hoy-fila-txt" title="${esc(i.titulo)}">${esc(i.titulo)}<small>${esc(i.empresa || '')}</small></span>
      ${extra}
    </div>`;
  el.innerHTML = `
    <div class="hoy-meta">
      <span><b>${st.semana || 0}</b> de ${st.meta_semana || 10} postulaciones esta semana</span>
      <div class="stat-bar"><div class="stat-fill" style="width:${pct}%"></div></div>
    </div>
    ${seg.length ? '<div class="hoy-subtitulo warn">⏰ Toca preguntar</div>' + seg.map(i => fila(i,
        `<button class="icon-btn update" onclick="seguimientoHecho('${i.id}')" title="Ya escribí: vuelve a contar 10 días">✓ Ya escribí</button>`)).join('') : ''}
    ${encajan.length ? '<div class="hoy-subtitulo">⭐ Encajan contigo</div>' + encajan.map(i => fila(i,
        i.url ? `<button class="icon-btn web" data-url="${esc(i.url)}" onclick="abrirBeca(this.dataset.url)">↗</button>` : '')).join('')
      : '<span class="hoy-vacio">Sin ofertas nuevas que encajen. Pulsa «Buscar ofertas» en Ofertas.</span>'}`;
}

function renderHoyIngles() {
  const el = document.getElementById('hoy-ingles');
  const st = inglesData?.stats;
  if (!el || !st) return;
  const racha = st.racha ? `🔥 ${st.racha} día${st.racha > 1 ? 's' : ''} seguidos` : 'Empieza tu racha hoy';
  el.innerHTML = st.pendientes_hoy
    ? `<div class="hoy-tarea">${st.pendientes_hoy} tarjetas para hoy · unos ${Math.max(2, Math.round(st.pendientes_hoy / 3))} min</div>
       <div class="hoy-sub">${st.de_ofertas ? `${st.de_ofertas} expresiones salen de tus ofertas` : 'Vocabulario de anuncios IT'}</div>
       <div class="hoy-acciones"><button class="icon-btn update" onclick="irA('ingles')">▶ Repasar</button></div>
       <div class="hoy-pie">${racha} · ${st.aprendidas} aprendidas de ${st.total}</div>`
    : `<div class="hoy-tarea">✅ Repaso de hoy hecho</div>
       <div class="hoy-pie">${racha} · ${st.aprendidas} aprendidas de ${st.total}</div>`;
}

// ── Estudio (app Certificaciones, :7810) ─────────────────────────
let estudioData = null;
let _editandoExamen = false;

async function loadEstudio() {
  try {
    estudioData = await (await fetch('/api/estudio')).json();
    renderHoyEstudio();
  } catch (e) {}
}

function abrirEstudio(codigo) {
  fetch('/api/estudio/abrir', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ codigo }) });
}

async function guardarExamen() {
  const nombre = document.getElementById('examen-nombre').value;
  const fecha = document.getElementById('examen-fecha').value;
  await fetch('/api/estudio/examen', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                       body: JSON.stringify({ nombre, fecha }) });
  _editandoExamen = false;
  loadEstudio();
}

function renderHoyEstudio() {
  const el = document.getElementById('hoy-estudio');
  const d = estudioData;
  if (!el || !d) return;
  if (!d.disponible) { el.innerHTML = '<span class="hoy-vacio">No encuentro tus datos de Certificaciones (¿OneDrive montado?).</span>'; return; }
  const ex = d.examen;
  const examen = _editandoExamen || !ex
    ? `<div class="hoy-examen-form">
         <input class="carrera-input" id="examen-nombre" placeholder="Examen (p. ej. AZ-104)" value="${esc(ex?.nombre || '')}">
         <input class="carrera-input" id="examen-fecha" type="date" value="${esc(ex?.fecha || '')}">
         <button class="icon-btn update" onclick="guardarExamen()">📅 Guardar</button>
       </div>`
    : `<div class="hoy-examen ${ex.dias <= 14 ? 'cerca' : ''}" onclick="_editandoExamen = true; renderHoyEstudio()" title="Pulsa para cambiarlo">
         📅 <b>${esc(ex.nombre)}</b> ${ex.dias > 0 ? `en <b>${ex.dias}</b> día${ex.dias === 1 ? '' : 's'}` : ex.dias === 0 ? '<b>¡hoy!</b>' : 'ya pasó — pulsa para poner el siguiente'}
       </div>`;
  const ult = d.cursos[0];
  const seguir = ult ? `
    <div class="hoy-fila">
      <span class="hoy-fila-txt">${esc(ult.nombre)}<small>${ult.dias === 0 ? 'hoy' : ult.dias === 1 ? 'ayer' : 'hace ' + ult.dias + ' días'}${ult.unidades ? ` · ${ult.hechas} de ${ult.unidades} unidades` : ''}${ult.aciertos + ult.fallos ? ` · test ${Math.round(100 * ult.aciertos / (ult.aciertos + ult.fallos))} % aciertos` : ''}</small></span>
      <button class="icon-btn" onclick="abrirFoco()" title="Modo foco: 25 min sin distracciones">⏱</button>
      <button class="icon-btn update" onclick="abrirEstudio('${esc(ult.codigo)}')">▶ Seguir</button>
    </div>` : '';
  const racha = d.racha ? `🔥 ${d.racha} día${d.racha > 1 ? 's' : ''} seguidos` : 'La racha cuenta desde mañana';
  el.innerHTML = examen + seguir + `
    <div class="hoy-pie">${racha}${d.repasar ? ` · 🔁 ${d.repasar} unidades para repasar` : ''}${d.respuestas ? ` · ${d.respuestas} preguntas de test (${d.pct_aciertos} % bien)` : ''}${d.app_encendida ? '' : ' · la app está apagada (▶ la enciende)'}${tjData?.cola?.length ? ` · <a href="#" onclick="irA('estudio'); loadPlataformas(); return false">🃏 ${tjData.cola.length} tarjetas para hoy</a>` : ''}</div>`;
}

loadEstudio();
setInterval(loadEstudio, 30 * 60000);

function renderHoyAgenda() {
  const el = document.getElementById('hoy-agenda');
  const prox = agendaData?.proximos || [];
  const badge = document.getElementById('count-agenda');
  if (badge) { const n = prox.filter(e => e.dias <= 1).length; badge.style.display = n ? '' : 'none'; badge.textContent = n ? n + ' ⏰' : ''; }
  if (!el) return;
  el.innerHTML = prox.length ? `<span class="hoy-agenda-tit">🗓 Próximos días</span>` + prox.slice(0, 5).map(e => `
    <span class="hoy-agenda-ev ${e.dias <= 1 ? 'pronto' : ''}" onclick="irA('agenda'); loadAgenda()">${e.icono} <b>${e.dias === 0 ? 'Hoy' : e.dias === 1 ? 'Mañana' : new Date(e.fecha + 'T00:00:00').toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric' })}${e.hora ? ' ' + esc(e.hora) : ''}</b> ${esc(e.titulo)}</span>`).join('') : '';
}

function renderHoyServicios() {
  const el = document.getElementById('hoy-servicios');
  if (!el) return;
  const cards = [...document.querySelectorAll('.servicios-grid .service-card')];
  const on = cards.filter(c => c.classList.contains('on'));
  if (!on.length) {
    el.innerHTML = '<span class="hoy-vacio">Todo apagado.</span>';
    return;
  }
  el.innerHTML = on.map(c => {
    const id = c.dataset.id;
    const nombre = c.querySelector('.service-name').textContent;
    const abrir = c.querySelector('.svc-bottom .icon-btn.web');
    const up = c.querySelector('.uptime-tag')?.textContent || '';
    return `<div class="hoy-fila">
      <span class="hoy-orb ${c.classList.contains('unhealthy') ? 'warn' : ''}"></span>
      <span class="hoy-fila-txt">${esc(nombre)}<small>${/\d/.test(up) ? esc(up) : 'encendido'}</small></span>
      ${abrir ? `<button class="icon-btn web" onclick="apiCall('/api/open/${esc(id)}','POST')">↗ Abrir</button>` : ''}
    </div>`;
  }).join('') + `<div class="hoy-pie">${on.length} de ${cards.length} servicios encendidos</div>`;
}

function renderHoyBecas() {
  const el = document.getElementById('hoy-becas');
  const items = becasData?.items || [];
  if (!becasData?.last_update && !items.length) return;
  const nuevos = items.filter(i => i.new && (i.ia || {}).v !== 'basura');
  // primero lo que la IA dice que sirve, luego lo verificado (catálogo, anuncios, reddit)
  // y al final los cupones de Telegram
  const orden = { curado: 0, rss: 1, reddit: 2, busqueda: 3, telegram: 4 };
  const ia = { sirve: 0, '': 1, dudosa: 2 };
  const top = [...nuevos].sort((a, b) => (ia[(a.ia || {}).v || ''] - ia[(b.ia || {}).v || ''])
    || (orden[a.kind] ?? 5) - (orden[b.kind] ?? 5)).slice(0, 4);
  el.innerHTML = top.length ? top.map(i => `
    <div class="hoy-fila">
      <span class="hoy-fila-txt" title="${esc(i.title)}">${esc(i.title)}<small>${esc(i.provider || '')}</small></span>
      <button class="icon-btn web" data-url="${esc(i.url)}" onclick="abrirBeca(this.dataset.url)">↗</button>
    </div>`).join('') + `<div class="hoy-pie">${nuevos.length} novedades de los últimos 7 días</div>`
    : '<span class="hoy-vacio">Nada nuevo esta semana.</span>';
}

renderHoyCabecera();
setInterval(renderHoyCabecera, 60000);
