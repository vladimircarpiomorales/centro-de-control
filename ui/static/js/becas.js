// ── Becas & Cursos ───────────────────────────────────────────────
let becasData = { items: [], last_update: null };
let becaFiltroActivo = 'todos';
let becasLimite = 30;
let becasVerBasura = false;

const BECA_IA = { sirve: '✅ te sirve', dudosa: '❓ dudosa', basura: '🗑 descartada' };
const becaIA = it => (it.ia || {}).v || '';

const BECA_KIND_LABEL = { curado: 'catálogo', rss: 'anuncio', busqueda: 'búsqueda web', reddit: 'reddit', telegram: 'telegram' };

async function loadBecas() {
  try {
    const res = await fetch('/api/becas');
    becasData = await res.json();
    renderBecas();
  } catch (e) {}
}

function renderBecas() {
  if (typeof queueHoy === 'function') queueHoy();
  const list = document.getElementById('becas-list');
  const basura = becasData.items.filter(i => becaIA(i) === 'basura').length;
  const items = becasData.items.filter(it => {
    if (becaIA(it) === 'basura' && !becasVerBasura) return false;
    if (becaFiltroActivo === 'todos') return true;
    if (becaFiltroActivo === 'nuevo') return it.new;
    if (becaFiltroActivo === 'sirve') return becaIA(it) === 'sirve';
    return (it.tags || []).includes(becaFiltroActivo);
  });

  const nuevos = becasData.items.filter(i => i.new && becaIA(i) !== 'basura').length;
  const badge = document.getElementById('count-becas-new');
  badge.style.display = nuevos > 0 ? '' : 'none';
  badge.textContent = nuevos > 0 ? nuevos + ' ✦' : '';

  document.getElementById('becas-update-info').textContent =
    becasData.last_update ? 'actualizado ' + becasData.last_update : 'aún sin actualizar — pulsa ⟳';
  const btnBasura = document.getElementById('becas-ver-basura');
  btnBasura.style.display = basura ? '' : 'none';
  btnBasura.textContent = becasVerBasura ? `Ocultar descartadas (${basura})` : `🗑 Ver descartadas por la IA (${basura})`;

  if (!items.length) {
    list.innerHTML = '<span style="font-size:11px;color:var(--muted2)">Sin resultados para este filtro</span>';
    return;
  }
  const total = items.length;
  list.innerHTML = items.slice(0, becasLimite).map(it => `
    <div class="beca-card${becaIA(it) === 'basura' ? ' beca-basura' : ''}">
      <div class="beca-head">
        ${it.new ? '<span class="beca-new">NUEVO</span>' : ''}
        <div>
          <div class="beca-title">${esc(it.title)}</div>
          <div class="beca-provider">${esc(it.provider)} · <span class="beca-kind">${esc(BECA_KIND_LABEL[it.kind] || it.kind)}</span></div>
        </div>
        <div class="beca-abrir" style="display:flex;gap:6px">
          ${['telegram','reddit','busqueda'].includes(it.kind)
            ? `<button class="icon-btn update" data-url="${esc(it.url)}" onclick="becaDirecto(this.dataset.url)" title="Extrae el enlace de Udemy saltando redirecciones y publicidad">🎯 Directo</button>`
            : ''}
          <button class="icon-btn web" data-url="${esc(it.url)}" onclick="abrirBeca(this.dataset.url)">↗ Abrir</button>
        </div>
      </div>
      ${it.desc ? `<div class="beca-desc">${esc(it.desc)}</div>` : ''}
      <div class="beca-tags">
        ${becaIA(it) ? `<span class="beca-tag ia-${esc(becaIA(it))}" title="Lo decidió la IA local">${BECA_IA[becaIA(it)]} · ${esc(it.ia.motivo || '')}</span>` : ''}
        ${(it.tags || []).map(t => `<span class="beca-tag ${esc(t)}">${esc(t)}</span>`).join('')}
        ${it.deadline ? `<span class="beca-tag voucher">⏰ ${esc(it.deadline)}</span>` : ''}
        ${it.first_seen ? `<span class="beca-tag">visto ${esc(it.first_seen)}</span>` : ''}
      </div>
    </div>`).join('') + (total > becasLimite
    ? `<button class="icon-btn web" style="display:block;margin:10px auto" onclick="becasLimite += 30; renderBecas()">Ver 30 más (quedan ${total - becasLimite})</button>`
    : '');
}

async function refreshBecas(deep) {
  document.getElementById('becas-update-info').textContent =
    deep ? '🔎 búsqueda profunda en curso…' : '⟳ actualizando…';
  await fetch('/api/becas/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ deep: !!deep })
  });
}

async function marcarVistos() {
  await fetch('/api/becas/vistos', { method: 'POST' });
  loadBecas();
}

async function abrirBeca(url) {
  await fetch('/api/becas/open', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url })
  });
}

async function becaDirecto(url) {
  await fetch('/api/becas/directo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url })
  });
}

function filtrarBecas(tag, el) {
  becaFiltroActivo = tag;
  becasLimite = 30;
  document.querySelectorAll('#tab-becas .beca-filtro').forEach(b => b.classList.remove('active'));
  if (el) el.classList.add('active');
  renderBecas();
}

socket.on('becas_updated', () => loadBecas());
loadBecas();

