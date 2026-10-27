// ── Mi Carrera ───────────────────────────────────────────────────
let carreraData = null;
let fasesAbiertas = null;   // se inicializa con la primera fase incompleta

async function loadCarrera() {
  try {
    const res = await fetch('/api/carrera');
    carreraData = await res.json();
    renderCarrera();
  } catch (e) {}
}

function faseProgreso(fase) {
  let total = 0, hechas = 0;
  fase.objetivos.forEach(o => o.tareas.forEach(t => { total++; if (t.done) hechas++; }));
  return { total, hechas, pct: total ? Math.round(hechas * 100 / total) : 0 };
}

function renderCarrera() {
  if (!carreraData) return;
  if (typeof queueHoy === 'function') queueHoy();
  const st = carreraData.stats;

  document.getElementById('carrera-meta').textContent = carreraData.meta;
  document.getElementById('carrera-pct-big').textContent = st.pct + '%';
  document.getElementById('carrera-bar').style.width = st.pct + '%';
  document.getElementById('carrera-pct-detalle').textContent = st.hechas + ' de ' + st.total + ' tareas';

  const badge = document.getElementById('count-carrera-pct');
  badge.style.display = '';
  badge.textContent = st.pct + '%';

  let ritmo;
  if (st.semana > 0)                    ritmo = '🔥 <b style="color:var(--green)">' + st.semana + ' avance' + (st.semana > 1 ? 's' : '') + '</b> en los últimos 7 días — sigue así';
  else if (st.dias_sin_avance == null)  ritmo = '✨ Todo listo para empezar — marca tu primera tarea';
  else if (st.dias_sin_avance <= 3)     ritmo = '🌱 Último avance hace ' + st.dias_sin_avance + ' día' + (st.dias_sin_avance === 1 ? '' : 's');
  else                                  ritmo = '💤 ' + st.dias_sin_avance + ' días sin avances — un paso pequeño hoy cuenta';
  document.getElementById('carrera-hero-stats').innerHTML =
    ritmo + '<br>🏆 ' + carreraData.logros.length + ' logros registrados';

  // Coach: última respuesta guardada
  const hist = carreraData.coach_history || [];
  if (hist.length) mostrarCoach(hist[hist.length - 1]);

  // Logros
  document.getElementById('logros-list').innerHTML = carreraData.logros.map(l => `
    <div class="logro-item">
      <span class="logro-fecha">${esc(l.fecha)}</span>
      <span class="logro-texto">${esc(l.texto)}</span>
      <span class="logro-del" style="margin-left:auto" title="Proponer para el CV" data-txt="${esc(l.texto)}" onclick="proponerCV(this.dataset.txt)">📄</span>
      <span class="logro-del" style="margin-left:0" title="Borrar" onclick="delLogro('${esc(l.id)}')">✕</span>
    </div>`).join('');

  // Fases (por defecto se abre la primera incompleta)
  if (fasesAbiertas === null) {
    fasesAbiertas = new Set();
    const primera = carreraData.fases.find(f => faseProgreso(f).pct < 100) || carreraData.fases[0];
    if (primera) fasesAbiertas.add(primera.id);
  }
  document.getElementById('carrera-fases').innerHTML = carreraData.fases.map(f => {
    const p = faseProgreso(f);
    return `
    <div class="fase-card ${fasesAbiertas.has(f.id) ? 'abierta' : ''}" style="margin-bottom:8px">
      <div class="fase-head" onclick="toggleFase('${esc(f.id)}')">
        <div>
          <span class="fase-periodo">${esc(f.periodo)}</span>
          <div class="fase-titulo">${esc(f.titulo)}</div>
          <div class="fase-resumen">${esc(f.resumen)}</div>
        </div>
        <div class="fase-prog">
          <div class="fase-prog-num">${p.hechas}/${p.total} · ${p.pct}%</div>
          <div class="stat-bar"><div class="stat-fill" style="width:${p.pct}%;background:${p.pct === 100 ? 'var(--green)' : 'var(--cyan)'}"></div></div>
        </div>
      </div>
      <div class="fase-body">
        ${f.objetivos.map(o => {
          const oh = o.tareas.filter(t => t.done).length;
          return `
          <div class="objetivo-block ${oh === o.tareas.length && o.tareas.length ? 'completo' : ''}">
            <div class="objetivo-head">
              <span>${o.icono}</span>
              <span class="objetivo-titulo">${esc(o.titulo)}</span>
              <span class="objetivo-prog">${oh}/${o.tareas.length}${oh === o.tareas.length && o.tareas.length ? ' ✓' : ''}</span>
            </div>
            ${o.tareas.map(t => `
              <div class="tarea-item ${t.done ? 'hecha' : ''} ${t.hito ? 'hito' : ''}" onclick="toggleTarea('${esc(t.id)}')">
                <div class="tarea-check">${t.done ? '✓' : ''}</div>
                <span class="tarea-texto">${esc(t.texto)}</span>
                ${t.done_date ? `<span class="tarea-fecha">${esc(t.done_date)}</span>` : ''}
                ${t.hito && t.done ? `<span class="logro-del" title="Proponer para el CV" data-txt="${esc(t.texto)}" onclick="event.stopPropagation();proponerCV(this.dataset.txt)">📄</span>` : ''}
                ${t.custom ? `<span class="logro-del" onclick="event.stopPropagation();delTarea('${esc(t.id)}')">✕</span>` : ''}
              </div>`).join('')}
            <div class="tarea-add">
              <input class="carrera-input" id="nueva-${esc(o.id)}" placeholder="＋ añadir tarea propia…"
                     onclick="event.stopPropagation()" onkeydown="if(event.key==='Enter')addTarea('${esc(o.id)}')">
            </div>
          </div>`;
        }).join('')}
      </div>
    </div>`;
  }).join('');
}

function toggleFase(id) {
  if (fasesAbiertas.has(id)) fasesAbiertas.delete(id); else fasesAbiertas.add(id);
  renderCarrera();
}

async function toggleTarea(id) {
  await fetch('/api/carrera/tarea', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  });
  loadCarrera();
}

async function addTarea(objetivoId) {
  const input = document.getElementById('nueva-' + objetivoId);
  const texto = (input.value || '').trim();
  if (!texto) return;
  await fetch('/api/carrera/tarea/nueva', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ objetivo_id: objetivoId, texto })
  });
  loadCarrera();
}

async function delTarea(id) {
  await fetch('/api/carrera/tarea/borrar', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  });
  loadCarrera();
}

async function addLogro() {
  const input = document.getElementById('logro-input');
  const texto = (input.value || '').trim();
  if (!texto) return;
  input.value = '';
  await fetch('/api/carrera/logro', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto })
  });
  loadCarrera();
}

async function delLogro(id) {
  await fetch('/api/carrera/logro/borrar', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  });
  loadCarrera();
}

function mostrarCoach(entry) {
  const box = document.getElementById('coach-respuesta');
  box.classList.toggle('vacia', !!entry.error);
  box.textContent = entry.texto;
  document.getElementById('coach-fecha').textContent = entry.fecha ? 'evaluado el ' + entry.fecha : '';
}

async function pedirCoach() {
  const btn = document.getElementById('coach-btn');
  btn.disabled = true;
  btn.textContent = '🧠 Pensando…';
  const modelo = document.getElementById('coach-modelo').value;
  await fetch('/api/carrera/coach', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ modelo })
  });
}

socket.on('carrera_coach', entry => {
  const btn = document.getElementById('coach-btn');
  btn.disabled = false;
  btn.textContent = '🧠 Evaluar mi progreso';
  mostrarCoach(entry);
  if (!entry.error) loadCarrera();
});

loadCarrera();

// ── Logro → CV (Reactive Resume) ─────────────────────────────────
let cvPropuesta = null;
const CV_SECCION_LABEL = { certifications: 'Certificaciones', projects: 'Proyectos', awards: 'Premios',
                           education: 'Formación', volunteer: 'Voluntariado', skills: 'Competencias',
                           experience: 'Experiencia' };

function abrirCvModal(html, aplicable) {
  document.getElementById('cv-modal-body').innerHTML = html;
  document.getElementById('cv-aplicar-btn').style.display = aplicable ? '' : 'none';
  document.getElementById('cv-modal').classList.add('show');
}
function cerrarCvModal() { document.getElementById('cv-modal').classList.remove('show'); }

async function proponerCV(texto) {
  cvPropuesta = null;
  abrirCvModal('<div class="coach-respuesta vacia">Comprobando conexión con Reactive Resume…</div>', false);
  let st;
  try { st = await (await fetch('/api/carrera/cv/estado')).json(); }
  catch (e) { st = { ok: false, motivo: 'error', detalle: 'el panel no responde' }; }
  if (!st.ok) {
    if (st.motivo === 'sin_api_key') {
      abrirCvModal(`<div class="coach-respuesta" style="border-left-color:var(--amber);white-space:normal">
        Para conectar el panel con Reactive Resume (solo se hace una vez):<br><br>
        1. Abre Reactive Resume → ajustes → <b>API Keys</b> → crea una clave y cópiala.<br>
        2. Pégala en <b>~/MiPanelControl/.env</b>: <code>RESUME_API_KEY=tu_clave</code><br>
        3. Reinicia el panel y vuelve a pulsar 📄.</div>`, false);
    } else {
      abrirCvModal(`<div class="coach-respuesta" style="border-left-color:var(--red)">⚠ ${esc(st.detalle || 'Error de conexión')}</div>`, false);
    }
    return;
  }
  abrirCvModal(`<div class="coach-respuesta vacia">🧠 El modelo está evaluando el logro y decidiendo dónde encaja en «${esc(st.resume.name)}»… (puede tardar un minuto)</div>`, false);
  await fetch('/api/carrera/cv/proponer', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto })
  });
}

socket.on('carrera_cv', d => {
  if (d.tipo === 'error') {
    abrirCvModal(`<div class="coach-respuesta" style="border-left-color:var(--red);white-space:normal">⚠ ${esc(d.texto)}</div>`, false);
    return;
  }
  cvPropuesta = d;
  if (!d.va_al_cv) {
    abrirCvModal(`<div class="coach-respuesta" style="white-space:normal"><b>El modelo recomienda NO añadirlo al CV.</b><br><br>${esc(d.razon)}</div>`, false);
    return;
  }
  let campos = '';
  if (d.item) {
    campos = Object.entries(d.item)
      .filter(([k, v]) => typeof v === 'string' && v && k !== 'id')
      .map(([k, v]) => `<div style="font-size:11px"><span style="color:var(--muted2)">${esc(k)}:</span> <span style="color:var(--text)">${esc(v.replace(/<[^>]*>/g, ' '))}</span></div>`)
      .join('');
    if (Array.isArray(d.item.keywords) && d.item.keywords.length)
      campos += `<div style="font-size:11px"><span style="color:var(--muted2)">keywords:</span> <span style="color:var(--text)">${d.item.keywords.map(esc).join(', ')}</span></div>`;
  } else if (d.sugerencia) {
    campos = `<div style="font-size:11px;color:var(--text)">${esc(JSON.stringify(d.sugerencia))}</div>`;
  }
  abrirCvModal(`
    <div style="font-size: 12px;color:var(--muted)">Logro: «${esc(d.logro)}»</div>
    <div class="coach-respuesta" style="white-space:normal">
      <b>Destino:</b> ${esc(CV_SECCION_LABEL[d.seccion] || d.seccion)} · CV «${esc(d.resume.name)}»<br>
      <b>Motivo:</b> ${esc(d.razon)}
    </div>
    <div style="border:1px solid var(--border-dim);border-radius:8px;padding:10px 12px;display:flex;flex-direction:column;gap:4px">${campos}</div>
    ${d.aplicable ? '' : `<div style="font-size: 11.5px;color:var(--amber)">Esta propuesta no puede insertarse automáticamente (p. ej. un bullet dentro de una experiencia) — cópiala a mano en el editor de Reactive Resume.</div>`}
  `, d.aplicable);
});

async function aplicarCV() {
  if (!cvPropuesta || !cvPropuesta.aplicable) return;
  const btn = document.getElementById('cv-aplicar-btn');
  btn.disabled = true;
  btn.textContent = 'Aplicando…';
  try {
    const res = await fetch('/api/carrera/cv/aplicar', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seccion: cvPropuesta.seccion, item: cvPropuesta.item })
    });
    const out = await res.json();
    if (out.ok) {
      abrirCvModal(`<div class="coach-respuesta" style="border-left-color:var(--green);white-space:normal">✅ Añadido a <b>${esc(CV_SECCION_LABEL[out.seccion] || out.seccion)}</b> del CV «${esc(out.resume.name)}».<br>Ábrelo en Reactive Resume para verlo (recarga la pestaña si ya lo tenías abierto).</div>`, false);
    } else {
      abrirCvModal(`<div class="coach-respuesta" style="border-left-color:var(--red);white-space:normal">⚠ ${esc(out.error || 'Error al aplicar')}</div>`, false);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = '✅ Aplicar al CV';
  }
}

