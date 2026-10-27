// ── Mi estudio (mapa de plataformas de ~/Proyectos) ──────────────
let plataformasData = [];

async function loadPlataformas() {
  try {
    plataformasData = (await (await fetch('/api/estudio/plataformas')).json()).plataformas;
    renderPlataformas();
  } catch (e) {}
}

function abrirPlataforma(plataforma, codigo) {
  fetch('/api/estudio/abrir', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ plataforma, codigo: codigo || '' }) });
  setTimeout(loadPlataformas, 4000);
}

const cuando = d => d == null ? '' : d === 0 ? 'hoy' : d === 1 ? 'ayer' : `hace ${d} días`;
const pct = (a, b) => b ? Math.round(100 * a / b) : 0;

function barra(hechas, total) {
  return total ? `<div class="stat-bar"><div class="stat-fill" style="width:${pct(hechas, total)}%"></div></div>` : '';
}

function renderPlataformas() {
  const el = document.getElementById('plat-grid');
  el.innerHTML = plataformasData.map(p => {
    let cuerpo = '';
    if (p.id === 'certificaciones') {
      cuerpo = p.cursos.map(c => `
        <div class="plat-curso">
          <span class="plat-curso-nombre">${esc(c.nombre)}<small>${c.unidades ? `${c.hechas}/${c.unidades} unidades` : ''}${c.aciertos + c.fallos ? ` · test ${pct(c.aciertos, c.aciertos + c.fallos)} %` : ''} · ${cuando(c.dias)}</small></span>
          <button class="icon-btn" onclick="abrirPlataforma('certificaciones', '${esc(c.codigo)}')" title="Abrir este curso">▶</button>
        </div>`).join('');
    } else if (p.id === 'az104' && p.resumen) {
      const r = p.resumen;
      cuerpo = `<div class="plat-dato"><b>${r.hechas}</b> de ${r.unidades} unidades (${pct(r.hechas, r.unidades)} %)</div>${barra(r.hechas, r.unidades)}
        <div class="plat-dato">Test: <b>${pct(r.aciertos, r.aciertos + r.fallos)} %</b> de aciertos en ${r.aciertos + r.fallos} preguntas</div>`;
    } else if (p.id === 'uk' && p.resumen?.perfil) {
      const r = p.resumen;
      cuerpo = `<div class="plat-dato">Perfil <b>${esc(r.perfil)}</b> · ${r.xp} XP${r.racha ? ` · 🔥 ${r.racha}` : ''}</div>
        ${r.srs ? `<div class="plat-dato">${r.srs_hoy} de ${r.srs} tarjetas para repasar hoy</div>` : ''}
        <div class="plat-dato">💡 El vocabulario de tus ofertas está en la pestaña <a href="#" onclick="irA('ingles'); return false">Inglés</a></div>`;
    }
    const estado = p.encendida === true ? '<span class="plat-on">● encendida</span>'
                 : p.encendida === false ? '<span class="plat-off">○ apagada</span>' : '';
    const dormida = p.dias != null && p.dias > 14 ? `<span class="plat-aviso">💤 ${cuando(p.dias)}</span>`
                  : p.dias != null ? `<span class="plat-cuando">${cuando(p.dias)}</span>` : '';
    return `<section class="plat-card">
      <div class="plat-cab"><span class="plat-titulo">${p.icono} ${esc(p.nombre)}</span>${estado}</div>
      <div class="plat-que">${esc(p.que)}</div>
      ${cuerpo}
      <div class="plat-pie">${dormida}<button class="icon-btn update" onclick="abrirPlataforma('${esc(p.id)}')">▶ ${p.id === 'ccna-labs' ? 'Abrir la guía' : 'Abrir'}</button>
        ${p.id === 'ccna-labs' ? `<button class="icon-btn" onclick="irA('laboratorios')">🧪 CML y VMs</button>` : ''}</div>
    </section>`;
  }).join('');
}

loadPlataformas();
