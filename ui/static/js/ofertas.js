// ── Ofertas de empleo ────────────────────────────────────────────
let ofertasData = { items: [], stats: {}, estados: [] };
let ofertaFiltro = 'todas';
const OFERTA_FUENTE = { infojobs: 'InfoJobs', tecnoempleo: 'Tecnoempleo', linkedin: 'LinkedIn', manual: 'a mano' };
const OFERTA_ESTADO = { '': '— sin estado —', guardada: '📌 Guardada', postulada: '📨 Postulada',
                        entrevista: '🗣 Entrevista', oferta: '🎉 Oferta', rechazada: '✗ Rechazada',
                        descartada: '🚫 Descartada' };

async function loadOfertas() {
  try {
    ofertasData = await (await fetch('/api/ofertas')).json();
    renderOfertas();
  } catch (e) {}
}

function claseScore(n) { return n >= 65 ? 'alto' : n >= 45 ? 'medio' : 'bajo'; }

function renderOfertas() {
  if (typeof queueHoy === 'function') queueHoy();
  const st = ofertasData.stats || {};
  const pe = st.por_estado || {};
  document.getElementById('ofertas-semana').textContent = (st.semana || 0) + '/' + (st.meta_semana || 10);
  document.getElementById('ofertas-semana-bar').style.width =
    Math.min(100, 100 * (st.semana || 0) / (st.meta_semana || 10)) + '%';
  document.getElementById('ofertas-hero-stats').innerHTML =
    `✦ ${st.nuevas || 0} nuevas · 📨 ${pe.postulada || 0} postuladas · 🗣 ${pe.entrevista || 0} entrevistas` +
    (st.seguimiento ? `<br><span style="color:var(--amber)">⏰ ${st.seguimiento} sin respuesta hace 10+ días — toca escribir para preguntar</span>` : '');

  const badge = document.getElementById('count-ofertas-new');
  const aviso = (st.nuevas || 0) + (st.seguimiento || 0);
  badge.style.display = aviso ? '' : 'none';
  badge.textContent = st.seguimiento ? '⏰ ' + st.seguimiento : (st.nuevas + ' ✦');

  document.getElementById('ofertas-update-info').textContent = ofertasData.refrescando
    ? '⟳ buscando… (tarda ~3 min, va con pausas)'
    : ofertasData.last_update ? 'actualizado ' + ofertasData.last_update
      + ((ofertasData.errores || []).length ? ` · ⚠ ${ofertasData.errores.length} fallos (ver log)` : '')
      + ((ofertasData.fuentes_rotas || []).length ? ` · ⚠ sin resultados hace varias búsquedas: ${ofertasData.fuentes_rotas.join(', ')}` : '')
    : 'aún sin buscar — pulsa ⟳';

  const brechas = st.brechas || [];
  document.getElementById('ofertas-brechas-box').style.display = brechas.length ? '' : 'none';
  document.getElementById('ofertas-brechas').innerHTML = brechas.map(([c, n]) =>
    `<div class="brecha-item"><span class="brecha-n">${n}×</span><span>${esc(c)}</span></div>`).join('');

  const items = ofertasData.items.filter(it => {
    const e = it.estado || '';
    if (ofertaFiltro === 'descartada') return e === 'descartada';
    if (e === 'descartada') return false;
    if (ofertaFiltro === 'todas') return true;
    if (ofertaFiltro === 'nueva') return it.new && !e;
    if (ofertaFiltro === 'encajan') return it.eval ? it.eval.encaje >= 60 : it.relevancia >= 60;
    if (ofertaFiltro === 'seguimiento') return it.seguimiento;
    if (ofertaFiltro === 'cerradas') return e === 'oferta' || e === 'rechazada';
    return e === ofertaFiltro;
  });

  const list = document.getElementById('ofertas-list');
  if (!items.length) {
    list.innerHTML = '<span style="font-size:11px;color:var(--muted2)">Nada en este filtro</span>';
    return;
  }
  list.innerHTML = items.slice(0, 80).map(it => {
    const ev = it.eval;
    const score = ev
      ? `<span class="oferta-score ${claseScore(ev.encaje)}" title="Encaje según la IA">${ev.encaje}/100</span>`
      : `<span class="oferta-score" title="Relevancia por palabras del título (sin IA)">~${it.relevancia}</span>`;
    const lugar = [it.ubicacion, it.modalidad, it.publicada].filter(Boolean).map(esc).join(' · ');
    const otras = (it.tambien_en || []).map(f => OFERTA_FUENTE[f.fuente] || f.fuente).join(', ');
    const sel = ['', ...ofertasData.estados].map(e =>
      `<option value="${e}" ${(it.estado || '') === e ? 'selected' : ''}>${OFERTA_ESTADO[e] || e}</option>`).join('');
    const evalHtml = ev ? `
      <div class="oferta-eval">
        <div>${esc(ev.resumen)}</div>
        ${ev.fuertes.length ? `<div><b>A tu favor:</b> ${ev.fuertes.map(esc).join(' · ')}</div>` : ''}
        ${ev.carencias.length ? `<div><b>Te falta:</b> ${ev.carencias.map(esc).join(' · ')}</div>` : ''}
        <div><b>Técnico</b> ${ev.tecnico ?? '–'} · <b>Experiencia</b> ${ev.experiencia ?? '–'} · <b>Carrera</b> ${ev.carrera ?? '–'}
          · <b>Idioma</b> ${esc(ev.idioma)} · <b>Recomendación:</b> ${esc(ev.recomendacion)}
          ${ev.sin_descripcion ? ' · <span style="color:var(--amber)">evaluada solo por el título</span>' : ''}</div>
        ${ev.idioma === 'FLAG' && ev.idioma_nota ? `<div style="color:var(--amber)">🗣 ${esc(ev.idioma_nota)}</div>` : ''}
      </div>` : '';
    return `
    <div class="beca-card oferta-card ${it.estado === 'descartada' ? 'descartada' : ''} ${it.seguimiento ? 'seguimiento' : ''}">
      <div class="beca-head">
        ${it.new && !it.estado ? '<span class="beca-new">NUEVA</span>' : ''}
        <div style="flex:1;min-width:0">
          <div class="beca-title">${esc(it.titulo)}</div>
          <div class="beca-provider">${esc(it.empresa || 'empresa sin publicar')} ·
            <span class="beca-kind">${esc(OFERTA_FUENTE[it.fuente] || it.fuente)}${otras ? ' (también en ' + esc(otras) + ')' : ''}</span></div>
          ${lugar ? `<div class="beca-desc">${lugar}</div>` : ''}
        </div>
        ${score}
      </div>
      ${evalHtml}
      <div class="beca-tags">
        ${it.idioma_titulo ? '<span class="beca-tag voucher">🗣 pide idioma</span>' : ''}
        ${it.seguimiento ? '<span class="beca-tag voucher">⏰ 10+ días sin respuesta</span>' : ''}
        ${it.descripcion ? '<span class="beca-tag">texto guardado</span>' : ''}
        <span class="beca-tag">vista ${esc(it.first_seen)}</span>
      </div>
      <div class="oferta-acciones">
        ${it.url ? `<button class="icon-btn web" data-url="${esc(it.url)}" onclick="abrirBeca(this.dataset.url)">↗ Abrir</button>` : ''}
        <button class="icon-btn web" onclick="evaluarOferta('${it.id}', this)">🧠 ${ev ? 'Reevaluar' : 'Evaluar'}</button>
        ${it.preparacion ? `<button class="icon-btn update" onclick="verPreparacion('${it.id}')" title="Perfil, carta y preguntas de entrevista para esta oferta">📝 Candidatura</button>` : ''}
        <select class="carrera-input" onchange="setEstadoOferta('${it.id}', this.value)">${sel}</select>
        ${it.seguimiento ? `<button class="icon-btn update" onclick="seguimientoHecho('${it.id}')" title="Ya escribí para preguntar: vuelve a contar 10 días">✓ Ya escribí</button>` : ''}
        ${it.nota ? `<span class="beca-desc" title="${esc(it.nota)}">📝 ${esc(it.nota.slice(0, 40))}${it.nota.length > 40 ? '…' : ''}</span>` : ''}
        <details class="oferta-menu" style="margin-left:auto">
          <summary class="icon-btn" title="Más acciones">⋯</summary>
          <div class="svc-menu-pop">
            <button class="icon-btn" onclick="cerrarMenus(); prepararOferta('${it.id}', this)" title="Perfil del CV ajustado, carta y preguntas de entrevista con tu experiencia real (Claude vía OmniRoute, ~1 min; si no, IA local)">📝 ${it.preparacion ? 'Rehacer' : 'Preparar'} candidatura</button>
            <button class="icon-btn" onclick="cerrarMenus(); apuntarEntrevista('${it.id}')" title="Apuntar la fecha de la entrevista en la Agenda">🗓 Apuntar entrevista</button>
            <button class="icon-btn" onclick="cerrarMenus(); ensayarOferta('${it.id}')" title="Simulador de entrevista por voz para este puesto">🎤 Ensayar la entrevista</button>
            <button class="icon-btn" onclick="cerrarMenus(); toggleTextoOferta('${it.id}')" title="InfoJobs no deja leer la oferta automáticamente">📋 Pegar texto de la oferta</button>
            <input class="carrera-input" placeholder="📝 nota (Enter para guardar)…" value="${esc(it.nota || '')}"
                   onkeydown="if(event.key==='Enter'){ setNotaOferta('${it.id}', this.value).then(loadOfertas); cerrarMenus(); }"
                   onchange="setNotaOferta('${it.id}', this.value)">
          </div>
        </details>
      </div>
      <div id="texto-${it.id}" style="display:none;gap:6px;flex-direction:column">
        <textarea class="carrera-input" rows="6" id="textarea-${it.id}"
          placeholder="Pega el texto completo de la oferta y pulsa Guardar; luego Evaluar">${esc(it.descripcion || '')}</textarea>
        <button class="icon-btn update" style="align-self:flex-start" onclick="guardarTextoOferta('${it.id}')">💾 Guardar texto</button>
      </div>
    </div>`;
  }).join('') + (items.length > 80 ? `<span style="font-size: 11.5px;color:var(--muted2)">… y ${items.length - 80} más (usa los filtros)</span>` : '');
}

async function postOfertas(ruta, body) {
  await fetch('/api/ofertas/' + ruta, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {})
  });
}

async function refreshOfertas() {
  document.getElementById('ofertas-update-info').textContent = '⟳ buscando… (tarda ~3 min, va con pausas)';
  await postOfertas('refresh');
}
async function marcarOfertasVistas() { await postOfertas('vistas'); loadOfertas(); }
async function setEstadoOferta(id, estado) { await postOfertas('estado', { id, estado }); loadOfertas(); }
async function setNotaOferta(id, nota) { await postOfertas('nota', { id, nota }); }
async function seguimientoHecho(id) { await postOfertas('seguimiento', { id }); loadOfertas(); }

function toggleTextoOferta(id) {
  const el = document.getElementById('texto-' + id);
  el.style.display = el.style.display === 'none' ? 'flex' : 'none';
}
async function guardarTextoOferta(id) {
  const texto = document.getElementById('textarea-' + id).value;
  await postOfertas('descripcion', { id, texto });
  loadOfertas();
}

async function evaluarOferta(id, btn) {
  if (btn) { btn.disabled = true; btn.textContent = '🧠 Pensando…'; }
  const modelo = document.getElementById('ofertas-modelo').value;
  await postOfertas('evaluar', id ? { id, modelo } : { modelo });
}

async function addOfertaManual() {
  const titulo = document.getElementById('manual-titulo').value;
  const empresa = document.getElementById('manual-empresa').value;
  const url = document.getElementById('manual-url').value;
  if (!titulo.trim()) return;
  await postOfertas('manual', { titulo, empresa, url });
  ['manual-titulo', 'manual-empresa', 'manual-url'].forEach(i => document.getElementById(i).value = '');
  loadOfertas();
}

function filtrarOfertas(f, el) {
  ofertaFiltro = f;
  document.querySelectorAll('#ofertas-filtros .beca-filtro').forEach(b => b.classList.remove('active'));
  if (el) el.classList.add('active');
  renderOfertas();
}

socket.on('ofertas_updated', () => loadOfertas());
socket.on('ofertas_eval', () => loadOfertas());

// ── Preparar candidatura (candidatura.py) ──────────────────────
const _preparando = new Set();
async function prepararOferta(id) {
  _preparando.add(id);
  await postOfertas('preparar', { id });
}

socket.on('ofertas_preparacion', async ({ id, error }) => {
  _preparando.delete(id);
  await loadOfertas();
  if (!error) verPreparacion(id);
});

function copiarTexto(btn) {
  const texto = btn.closest('.prep-bloque').querySelector('.prep-texto').innerText;
  const ok = () => { btn.textContent = '✓ Copiado'; setTimeout(() => btn.textContent = '⧉ Copiar', 1500); };
  if (navigator.clipboard) navigator.clipboard.writeText(texto).then(ok).catch(() => {});
  else {
    const ta = document.createElement('textarea');
    ta.value = texto; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); ta.remove(); ok();
  }
}

function verPreparacion(id) {
  const it = (ofertasData.items || []).find(i => i.id === id);
  const p = it?.preparacion;
  if (!p) return;
  const lista = xs => xs.map(x => `<li>${esc(x)}</li>`).join('');
  const copiar = '<button class="icon-btn" onclick="copiarTexto(this)">⧉ Copiar</button>';
  document.getElementById('prep-modal-titulo').textContent = '📝 ' + it.titulo;
  document.getElementById('prep-modal-body').innerHTML = `
    <div class="prep-sub">${esc(it.empresa || '')} · preparada el ${esc(p.fecha)} con ${esc(p.modelo)}${p.revision === 'IA' ? ' · revisada frase a frase contra tu CV' : ''} · revísalo siempre antes de enviarlo</div>
    ${p.avisos?.length ? `<div class="prep-aviso"><b>⚠ Revisa esto antes de usarlo — la IA a veces mezcla o se inventa cosas:</b>
      <ul>${p.avisos.map(a => `<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}
    ${p.revisar?.length ? `<div class="prep-aviso">⚠ Estas cifras no están en tu CV ni en la oferta, compruébalas: <b>${p.revisar.map(esc).join(', ')}</b></div>` : ''}
    <div class="prep-bloque"><div class="prep-cab"><b>Perfil para el CV</b>${copiar}</div><div class="prep-texto">${esc(p.perfil)}</div>
      ${p.palabras_clave.length ? `<div class="prep-sub">Palabras de la oferta que conviene usar: ${p.palabras_clave.map(esc).join(' · ')}</div>` : ''}</div>
    <div class="prep-bloque"><div class="prep-cab"><b>Carta de presentación</b>${copiar}</div><div class="prep-texto">${esc(p.carta).replace(/\n/g, '<br>')}</div></div>
    <div class="prep-dos">
      <div class="prep-bloque"><b>✅ Por qué encajas</b><ul>${lista(p.encaje)}</ul></div>
      <div class="prep-bloque"><b>🧩 Lo que no cubres (prepáralo)</b><ul>${lista(p.huecos)}</ul></div>
    </div>
    <div class="prep-bloque"><b>🎤 Preguntas probables de la entrevista</b>
      ${p.preguntas.map((q, i) => `<details class="prep-q" ${i === 0 ? 'open' : ''}>
        <summary>${esc(q.pregunta)}</summary>
        ${q.por_que ? `<div class="prep-sub">Qué quieren comprobar: ${esc(q.por_que)}</div>` : ''}
        <div class="prep-texto">${esc(q.respuesta)}</div></details>`).join('')}
    </div>
    ${p.preguntas_en.length ? `<div class="prep-bloque"><b>🇬🇧 Preguntas en inglés</b>
      ${p.preguntas_en.map(q => `<details class="prep-q">
        <summary>${esc(q.pregunta)}</summary>
        <div class="prep-texto">${esc(q.respuesta)}</div>
        ${q.traduccion ? `<div class="prep-sub">${esc(q.traduccion)}</div>` : ''}</details>`).join('')}
    </div>` : ''}`;
  document.getElementById('prep-modal').classList.add('show');
}
function cerrarPreparacion() { document.getElementById('prep-modal').classList.remove('show'); }
loadOfertas();


// ── Sueldo neto y comparador (sueldo.py) ─────────────────────────
const SUELDO_CAMPOS = [
  ['nombre', 'Oferta', 'text', 'Oferta A'], ['bruto', 'Bruto anual (€)', 'number', ''],
  ['pagas', 'Pagas', 'select', '14'], ['extras', 'Extras exentos €/año (ticket, seguro…)', 'number', '0'],
  ['dias_oficina', 'Días de oficina por semana', 'number', '5'], ['coste_desplazamiento', 'Coste por día de oficina (€)', 'number', '0'],
];
let sueldoCols = null;
function abrirSueldo() {
  if (!sueldoCols) sueldoCols = ['Oferta A', 'Oferta B'].map(n => ({ nombre: n, pagas: '14', extras: '0', dias_oficina: '5', coste_desplazamiento: '0' }));
  renderSueldoCols();
  document.getElementById('sueldo-modal').classList.add('show');
}
function cerrarSueldo() { document.getElementById('sueldo-modal').classList.remove('show'); }
function renderSueldoCols() {
  document.getElementById('sueldo-cols').innerHTML = sueldoCols.map((c, i) => `
    <div class="prep-bloque sueldo-col">
      ${SUELDO_CAMPOS.map(([k, lbl, tipo]) => `<label class="ent-label">${lbl}</label>${tipo === 'select'
        ? `<select class="carrera-input" onchange="sueldoCols[${i}].${k}=this.value; calcularSueldo()"><option ${c[k] === '14' ? 'selected' : ''}>14</option><option ${c[k] === '12' ? 'selected' : ''}>12</option></select>`
        : `<input class="carrera-input" type="${tipo}" value="${esc(c[k] ?? '')}" oninput="sueldoCols[${i}].${k}=this.value; calcularSueldo()">`}`).join('')}
      ${sueldoCols.length > 1 ? `<button class="icon-btn" onclick="sueldoCols.splice(${i},1); renderSueldoCols(); calcularSueldo()">🗑 Quitar</button>` : ''}
    </div>`).join('') + (sueldoCols.length < 3 ? `<button class="icon-btn update sueldo-mas" onclick="sueldoCols.push({ nombre: 'Oferta ' + 'ABC'[sueldoCols.length], pagas: '14', extras: '0', dias_oficina: '5', coste_desplazamiento: '0' }); renderSueldoCols()">＋ Añadir oferta</button>` : '');
  calcularSueldo();
}
let _sueldoT = null;
function calcularSueldo() {
  clearTimeout(_sueldoT);
  _sueldoT = setTimeout(async () => {
    const validas = sueldoCols.filter(c => +c.bruto > 0);
    if (!validas.length) { document.getElementById('sueldo-res').innerHTML = ''; return; }
    const { resultados } = await (await fetch('/api/sueldo', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ofertas: validas }) })).json();
    const e = n => Math.round(n).toLocaleString('es-ES') + ' €';
    document.getElementById('sueldo-res').innerHTML = `<table class="red-tabla sueldo-tabla">
      <tr><td></td>${resultados.map(r => `<td><b>${esc(r.nombre)}</b></td>`).join('')}</tr>
      <tr><td>Neto al mes</td>${resultados.map(r => `<td class="sueldo-grande">${e(r.neto_mes)}<small> × ${r.pagas}</small></td>`).join('')}</tr>
      <tr><td>Neto al mes (prorrateado en 12)</td>${resultados.map(r => `<td>${e(r.neto_mes_12)}</td>`).join('')}</tr>
      <tr><td>Neto al año</td>${resultados.map(r => `<td>${e(r.neto_anual)}</td>`).join('')}</tr>
      <tr><td>IRPF estimado</td>${resultados.map(r => `<td>${e(r.irpf)} <small>(${r.tipo_irpf} %)</small></td>`).join('')}</tr>
      <tr><td>Seguridad Social</td>${resultados.map(r => `<td>${e(r.ss)}</td>`).join('')}</tr>
      <tr><td>+ Extras exentos</td>${resultados.map(r => `<td>${e(r.extras)}</td>`).join('')}</tr>
      <tr><td>− Ir a la oficina</td>${resultados.map(r => `<td>${e(r.coste_oficina)}</td>`).join('')}</tr>
      <tr class="sueldo-total"><td>Lo que de verdad te queda al año</td>${resultados.map(r => `<td>${e(r.valor_real)}${resultados.length > 1 ? `<br><small>${r.diferencia === 0 ? '🏆 la mejor' : e(r.diferencia)}</small>` : ''}</td>`).join('')}</tr>
    </table>`;
  }, 250);
}
