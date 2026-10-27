// ── Laboratorios (VMware, KVM, CML, contenedores sueltos) ────────
let labsData = null;

async function loadLabs(manual) {
  if (manual) document.getElementById('labs-ram').textContent = '⟳ consultando…';
  try {
    const res = await fetch('/api/labs');
    labsData = await res.json();
    renderLabs();
  } catch (e) {}
}

const gb = mb => (mb / 1024).toFixed(mb >= 10240 ? 0 : 1) + ' GB';

function renderLabs() {
  if (typeof queueHoy === 'function') queueHoy();
  if (!labsData) return;
  const d = labsData;
  const encendidas = d.vmware.filter(v => v.encendida).length + d.kvm.filter(v => v.encendida).length;
  const badge = document.getElementById('count-labs-on');
  const total = encendidas + d.contenedores.length;
  badge.style.display = total ? '' : 'none';
  badge.textContent = total ? total + '↑' : '';
  document.getElementById('labs-ram').textContent =
    `RAM libre: ${gb(d.ram_disponible_mb)} · ${encendidas} máquina${encendidas === 1 ? '' : 's'} encendida${encendidas === 1 ? '' : 's'}`;

  // contenedores sueltos
  const sec = document.getElementById('labs-sueltos-sec');
  sec.style.display = d.contenedores.length ? '' : 'none';
  document.getElementById('labs-sueltos').innerHTML = d.contenedores.map(c => `
    <div class="hoy-fila">
      <span class="hoy-orb ${(c.horas || 0) >= 6 ? 'warn' : ''}"></span>
      <span class="hoy-fila-txt">${esc(c.nombre)}<small>${esc(c.imagen)} · ${c.horas != null ? 'encendido hace ' + c.horas + ' h' : ''}${c.se_borra ? ' · se borra' : ''}</small></span>
      <button class="icon-btn" ${c.ocupada ? 'disabled' : ''} onclick="pararSueltos(['${esc(c.id)}'])">■ Parar</button>
    </div>`).join('');

  // CML
  const cml = d.cml;
  const cmlVm = d.vmware.find(v => v.es_cml);
  document.getElementById('labs-cml').innerHTML = !cml.disponible
    ? '<span class="hoy-vacio">No encuentro el comando cml (~/.local/bin/cml).</span>'
    : `<div class="lab-card ${cml.encendida ? 'on' : ''}">
        <div class="lab-top">
          <span class="hoy-orb ${cml.encendida && !cml.lista ? 'warn' : ''} ${cml.encendida ? '' : 'off'}"></span>
          <span class="lab-nombre">CML 2.10</span>
          <span class="lab-estado">${cml.ocupada ? '⏳ trabajando…' : cml.lista ? '✓ listo' : cml.encendida ? 'arrancando…' : 'apagado'}</span>
        </div>
        <div class="lab-sub">${cmlVm ? `${gb(cmlVm.ram_mb)} RAM · ${cmlVm.cpus} vCPU · ` : ''}al apagar, para antes todos los labs</div>
        <div class="lab-botones">
          ${cml.encendida
            ? `<button class="icon-btn web" onclick="abrirBeca('${esc(cml.url)}')">↗ Abrir CML</button>
               <button class="icon-btn" ${cml.ocupada ? 'disabled' : ''} onclick="labAccion('cml', null, 'off')">■ Apagar</button>`
            : `<button class="icon-btn update" ${cml.ocupada ? 'disabled' : ''} onclick="labAccion('cml', null, 'on', ${cmlVm ? cmlVm.ram_mb : 0})">▶ Encender</button>`}
        </div>
      </div>`;

  document.getElementById('labs-kvm').innerHTML = d.kvm.length
    ? d.kvm.map(v => labCard(v, 'kvm')).join('')
    : '<span class="hoy-vacio">No hay máquinas en libvirt.</span>';
  document.getElementById('labs-vmware').innerHTML = d.vmware.filter(v => !v.es_cml).map(v => labCard(v, 'vmware')).join('')
    || '<span class="hoy-vacio">No encuentro el inventario de VMware.</span>';
}

function labCard(v, tipo) {
  const detalle = [v.carpeta, v.ram_mb ? gb(v.ram_mb) + ' RAM' : '', v.cpus ? v.cpus + ' vCPU' : ''].filter(Boolean).map(esc).join(' · ');
  const id = esc(v.id);
  const botones = v.encendida
    ? `<button class="icon-btn" ${v.ocupada ? 'disabled' : ''} onclick="labAccion('${tipo}', '${id}', 'stop')">■ Apagar</button>`
    : `<button class="icon-btn update" ${v.ocupada ? 'disabled' : ''} onclick="labAccion('${tipo}', '${id}', 'start', ${v.ram_mb || 0})">▶ Encender</button>
       ${tipo === 'vmware' ? `<button class="icon-btn web" ${v.ocupada ? 'disabled' : ''} onclick="labAccion('vmware', '${id}', 'gui', ${v.ram_mb || 0})" title="Encender con la ventana de VMware">▶ Con ventana</button>` : ''}`;
  return `<div class="lab-card ${v.encendida ? 'on' : ''}">
    <div class="lab-top">
      <span class="hoy-orb ${v.encendida ? '' : 'off'}"></span>
      <span class="lab-nombre" title="${esc(v.nombre)}">${v.favorita ? '★ ' : ''}${esc(v.nombre)}</span>
      ${v.ocupada ? '<span class="lab-estado">⏳</span>' : ''}
    </div>
    <div class="lab-sub">${detalle}</div>
    <div class="lab-botones">${botones}</div>
  </div>`;
}

async function labAccion(tipo, id, accion, ramMb) {
  // aviso si encender dejaría el equipo sin memoria (deja 4 GB de margen)
  if (ramMb && labsData && ramMb > labsData.ram_disponible_mb - 4096) {
    if (!confirm(`Esta máquina pide ${gb(ramMb)} y quedan ${gb(labsData.ram_disponible_mb)} libres. ` +
                 'Puede dejar el equipo muy lento. ¿Encender igualmente?')) return;
  }
  await fetch('/api/labs/' + tipo, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(tipo === 'cml' ? { accion } : { id, accion }),
  });
  setTimeout(loadLabs, 1500);
  setTimeout(loadLabs, 8000);
}

async function pararSueltos(ids) {
  const lista = ids || (labsData?.contenedores || []).map(c => c.id);
  if (!lista.length) return;
  if (!ids && !confirm(`¿Parar ${lista.length} contenedores de laboratorio? Si tienes una práctica abierta, se cerrará.`)) return;
  await fetch('/api/labs/contenedores/parar', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: lista }),
  });
  setTimeout(loadLabs, 3000);
  setTimeout(loadLabs, 10000);
}

loadLabs();
setInterval(loadLabs, 60000);
