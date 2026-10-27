// ── Redes: subnetting, calculadora, diagnóstico y vigilante ──────
let redesData = null;

function redSeccion(id, btn) {
  document.querySelectorAll('#tab-redes .red-sec').forEach(s => s.style.display = 'none');
  document.getElementById('red-' + id).style.display = '';
  btn.parentElement.querySelectorAll('.beca-filtro').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (id === 'diag') cargarPuertos();
  if (id === 'red') loadRedes();
}

async function loadRedes() {
  try { redesData = await (await fetch('/api/redes')).json(); renderRedes(); } catch (e) {}
}

// ── Entrenador de subnetting (todo en el navegador) ──
const ip2n = ip => ip.split('.').reduce((a, o) => (a * 256) + (+o), 0) >>> 0;
const n2ip = n => [24, 16, 8, 0].map(s => (n >>> s) & 255).join('.');
const mascara = p => p === 0 ? 0 : (0xFFFFFFFF << (32 - p)) >>> 0;
const rnd = (a, b) => a + Math.floor(Math.random() * (b - a + 1));
const ipAleatoria = () => [[10, rnd(0, 255)], [172, rnd(16, 31)], [192, 168]][rnd(0, 2)].concat([rnd(0, 255), rnd(1, 254)]).slice(0, 4).join('.');
const binOcteto = o => (o >>> 0).toString(2).padStart(8, '0');

function expandir6(a) {
  let [iz, de] = a.toLowerCase().split('::');
  const p1 = iz ? iz.split(':') : [], p2 = de !== undefined && de ? de.split(':') : [];
  const medio = de !== undefined ? Array(8 - p1.length - p2.length).fill('0') : [];
  return [...p1, ...medio, ...p2].map(g => g.padStart(4, '0')).join(':');
}
function abreviar6(full) {
  const g = full.split(':').map(x => x.replace(/^0+(?=.)/, ''));
  let mejor = [-1, 0], i = 0;
  while (i < 8) { if (g[i] === '0') { let j = i; while (j < 8 && g[j] === '0') j++; if (j - i > mejor[1]) mejor = [i, j - i]; i = j; } else i++; }
  if (mejor[1] < 2) return g.join(':');
  return (g.slice(0, mejor[0]).join(':') + '::' + g.slice(mejor[0] + mejor[1]).join(':'));
}

const RETOS = [
  { tipo: 'red', gen() {
      const ip = ipAleatoria(), p = rnd(17, 29), r = (ip2n(ip) & mascara(p)) >>> 0;
      return { q: `¿Cuál es la <b>dirección de red</b> de <code>${ip}/${p}</code>?`, r: n2ip(r),
               exp: `Máscara /${p} = ${n2ip(mascara(p))}. AND bit a bit: el octeto que cambia ${binOcteto((ip2n(ip) >>> (8 * Math.floor((32 - p) / 8))) & 255)} → red ${n2ip(r)}.` }; } },
  { tipo: 'broadcast', gen() {
      const ip = ipAleatoria(), p = rnd(17, 29), r = ((ip2n(ip) & mascara(p)) | (~mascara(p) >>> 0)) >>> 0;
      return { q: `¿Cuál es la <b>dirección de broadcast</b> de <code>${ip}/${p}</code>?`, r: n2ip(r),
               exp: `Red ${n2ip((ip2n(ip) & mascara(p)) >>> 0)} + todos los bits de host a 1 (${32 - p} bits) = ${n2ip(r)}.` }; } },
  { tipo: 'hosts', gen() {
      const p = rnd(18, 30), h = 2 ** (32 - p) - 2;
      return { q: `¿Cuántos <b>hosts útiles</b> tiene una subred <code>/${p}</code>?`, r: String(h),
               exp: `2^${32 - p} − 2 (red y broadcast) = ${h}.` }; } },
  { tipo: 'mascara', gen() {
      const p = rnd(8, 30);
      return { q: `¿Qué <b>máscara decimal</b> corresponde a <code>/${p}</code>?`, r: n2ip(mascara(p)),
               exp: `${p} unos seguidos: ${n2ip(mascara(p)).split('.').map(o => binOcteto(+o)).join('.')}.` }; } },
  { tipo: 'prefijo', gen() {
      const p = rnd(8, 30);
      return { q: `La máscara <code>${n2ip(mascara(p))}</code> es un <b>prefijo /?</b> (solo el número)`, r: String(p),
               exp: `Cuenta los unos: ${n2ip(mascara(p)).split('.').map(o => binOcteto(+o)).join('.')} → /${p}.` }; } },
  { tipo: 'primera', gen() {
      const ip = ipAleatoria(), p = rnd(18, 29), r = ((ip2n(ip) & mascara(p)) + 1) >>> 0;
      return { q: `¿Cuál es la <b>primera IP utilizable</b> de la subred de <code>${ip}/${p}</code>?`, r: n2ip(r),
               exp: `Red ${n2ip((ip2n(ip) & mascara(p)) >>> 0)} + 1.` }; } },
  { tipo: 'misma', gen() {
      const p = rnd(24, 29), base = ip2n(ipAleatoria()) & mascara(p), salto = 2 ** (32 - p);
      const a = (base + rnd(1, salto - 2)) >>> 0;
      const otra = Math.random() < 0.5 ? (base + rnd(1, salto - 2)) >>> 0 : (base + salto + rnd(1, salto - 2)) >>> 0;
      const misma = ((a & mascara(p)) >>> 0) === ((otra & mascara(p)) >>> 0);
      return { q: `¿<code>${n2ip(a)}</code> y <code>${n2ip(otra)}</code> están en la <b>misma subred /${p}</b>? (sí / no)`, r: misma ? 'sí' : 'no',
               exp: `Saltos de ${salto}: ${n2ip(a)} está en ${n2ip((a & mascara(p)) >>> 0)} y ${n2ip(otra)} en ${n2ip((otra & mascara(p)) >>> 0)}.` }; } },
  { tipo: 'ipv6-abrev', gen() {
      const g = Array.from({ length: 8 }, (_, i) => (i > 1 && i < 6 && Math.random() < 0.55) ? '0000' : rnd(0, 0xffff).toString(16).padStart(4, '0'));
      g[0] = '2001'; g[1] = '0db8';
      const full = g.join(':');
      return { q: `<b>Abrevia</b> al máximo: <code>${full}</code>`, r: abreviar6(full),
               exp: `Quita los ceros a la izquierda de cada grupo y cambia la racha de grupos 0000 más larga por «::» (solo una vez).` }; } },
  { tipo: 'ipv6-exp', gen() {
      const cortas = ['2001:db8::1', 'fe80::a1:2b', '2001:db8:acad:1::10', 'ff02::1:2', '2001:db8:0:5::200:1', 'fd00:12::34'];
      const c = cortas[rnd(0, cortas.length - 1)];
      return { q: `<b>Expande</b> por completo: <code>${c}</code>`, r: expandir6(c),
               exp: `«::» se rellena con los grupos 0000 que falten hasta 8, y cada grupo con ceros a la izquierda hasta 4 dígitos.` }; } },
];

let reto = null, retoRespondido = false;
function nuevoReto() {
  const t = RETOS[rnd(0, RETOS.length - 1)];
  reto = { tipo: t.tipo, ...t.gen() };
  retoRespondido = false;
  renderReto();
}
function normaliza(s) { return s.trim().toLowerCase().replace(/^\//, '').replace(/^si$/, 'sí').replace(/\s+/g, ''); }
function renderReto(res) {
  document.getElementById('subnet-reto').innerHTML = `
    <div class="ingles-meta"><span>${reto.tipo.startsWith('ipv6') ? 'IPv6' : 'IPv4'} · ${reto.tipo}</span><span></span></div>
    <div class="red-pregunta">${reto.q}</div>
    <input class="carrera-input red-input red-resp" id="subnet-resp" autocomplete="off" ${retoRespondido ? 'disabled' : ''}
           onkeydown="if(event.key==='Enter'){ event.preventDefault(); ${retoRespondido ? 'nuevoReto()' : 'comprobarReto()'} }">
    ${res ? `<div class="red-resultado ${res.ok ? 'ok' : 'mal'}">${res.ok ? '✓ ¡Correcto!' : `✗ Era <code>${esc(reto.r)}</code>`}</div>
             <div class="ent-nota">${reto.exp}</div>` : ''}
    <div class="ingles-botones">${retoRespondido ? '<button class="icon-btn update" onclick="nuevoReto()">Siguiente ▶</button>'
      : '<button class="icon-btn update" onclick="comprobarReto()">Comprobar</button><button class="icon-btn" onclick="nuevoReto()">Saltar</button>'}</div>`;
  const inp = document.getElementById('subnet-resp');
  if (!retoRespondido) setTimeout(() => inp.focus(), 50);
}
async function comprobarReto() {
  const v = document.getElementById('subnet-resp').value;
  if (!v.trim()) return;
  const ok = normaliza(v) === normaliza(reto.r) || (reto.tipo === 'ipv6-abrev' && normaliza(v) === normaliza(reto.r).replace(/^0:/, '0:'));
  retoRespondido = true;
  renderReto({ ok });
  await fetch('/api/redes/subnetting', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tipo: reto.tipo, acierto: ok }) });
  loadRedes();
}
document.addEventListener('keydown', e => {
  if (!document.getElementById('tab-redes')?.classList.contains('active')) return;
  if ((e.key === 'n' || e.key === 'N') && retoRespondido && document.activeElement?.tagName !== 'INPUT') nuevoReto();
});

function renderSubnetStats() {
  const s = redesData?.subnetting || {};
  const tipos = Object.values(s.tipos || {});
  const v = tipos.reduce((a, t) => a + t.v, 0), f = tipos.reduce((a, t) => a + t.f, 0);
  document.getElementById('subnet-stats').innerHTML = `
    <span>Hoy: <b>${(s.dias || {})[redesData.hoy] || 0}</b></span>
    <span>Aciertos: <b>${v + f ? Math.round(100 * v / (v + f)) : 0} %</b> de ${v + f}</span>
    <span>Racha: <b>${s.racha_aciertos || 0}</b> (mejor ${s.mejor_racha || 0})</span>
    ${Object.entries(s.tipos || {}).filter(([, t]) => t.v + t.f >= 3).sort((a, b) => a[1].v / (a[1].v + a[1].f) - b[1].v / (b[1].v + b[1].f))
      .slice(0, 1).map(([k, t]) => `<span>Lo que más fallas: <b>${esc(k)}</b> (${Math.round(100 * t.v / (t.v + t.f))} %)</span>`).join('')}`;
}

// ── Calculadora ──
async function calcularRed() {
  const cidr = document.getElementById('calc-cidr').value;
  const r = await (await fetch('/api/redes/calcular?cidr=' + encodeURIComponent(cidr))).json();
  const el = document.getElementById('calc-res');
  if (r.error) { el.innerHTML = `<div class="prep-aviso">${esc(r.error)}</div>`; return; }
  const fila = (k, v) => `<tr><td>${k}</td><td><code>${esc(String(v))}</code></td></tr>`;
  el.innerHTML = `<table class="red-tabla">${r.version === 4 ? [
      fila('IP', `${r.ip}/${r.prefijo}`), fila('Red', r.red), fila('Broadcast', r.broadcast),
      fila('Rango útil', `${r.primera} – ${r.ultima}`), fila('Hosts útiles', r.hosts.toLocaleString('es')),
      fila('Máscara', r.mascara), fila('Wildcard (ACL/OSPF)', r.wildcard), fila('Tipo', r.clase),
      fila('IP en binario', r.bin_ip), fila('Máscara en binario', r.bin_mascara), fila('Red en binario', r.bin_red)].join('')
    : [fila('IP', `${r.ip}/${r.prefijo}`), fila('Completa', r.ip_completa), fila('Red', `${r.red}/${r.prefijo}`),
       fila('Red completa', r.red_completa), fila('Rango', r.rango), fila('Direcciones', r.direcciones), fila('Tipo', r.tipo)].join('')}</table>`;
}

// ── Diagnóstico ──
async function diagnosticar(tipo) {
  const destino = document.getElementById('diag-destino').value;
  const out = document.getElementById('diag-salida');
  out.textContent = `⏳ ${tipo} ${destino}…${tipo === 'mtr' || tipo === 'traceroute' ? ' (puede tardar 10-30 s)' : ''}`;
  const r = await (await fetch('/api/redes/diagnostico', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tipo, destino }) })).json();
  out.textContent = r.error || r.salida;
}
async function cargarPuertos() {
  const r = await (await fetch('/api/redes/puertos')).json();
  const icono = { 'toda la red': '⚠️', 'una interfaz': '🔸', 'local': '🔒' };
  document.getElementById('puertos').innerHTML = `<table class="red-tabla">${r.puertos.map(p => `
    <tr class="${p.alcance === 'toda la red' ? 'expuesto' : ''}"><td>${icono[p.alcance]} ${esc(p.alcance)}</td>
    <td><code>:${esc(String(p.puerto))}</code></td><td>${esc(p.proceso)}</td><td class="ent-nota">${esc(p.direcciones.join(', '))}</td></tr>`).join('')}</table>
    <div class="ent-nota">⚠️ = escucha en 0.0.0.0: lo puede usar cualquiera en tu red local · 🔒 = solo este equipo.</div>`;
}

// ── Tu red ──
async function escanearRed(btn) {
  btn.disabled = true; btn.textContent = '⏳ escaneando…';
  await fetch('/api/redes/escanear', { method: 'POST' });
  btn.disabled = false; btn.textContent = '⟳ Escanear ahora';
  loadRedes();
}
async function medirVelocidad(btn) {
  btn.disabled = true; btn.textContent = '⏳ midiendo (10 MB)…';
  const r = await (await fetch('/api/redes/velocidad', { method: 'POST' })).json();
  btn.disabled = false; btn.textContent = r.mbps ? `🚀 ${r.mbps} Mbps` : '🚀 Medir velocidad';
  loadRedes();
}
async function marcarDispositivo(clave, campos) {
  await fetch('/api/redes/dispositivo', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clave, ...campos }) });
  loadRedes();
}

function sparkline(valores, unidad, alto = 60) {
  const v = valores.filter(x => x != null);
  if (v.length < 2) return '<div class="ent-nota">Aún sin datos suficientes.</div>';
  const max = Math.max(...v) * 1.15 || 1, w = 100 / (valores.length - 1);
  const pts = valores.map((x, i) => x == null ? null : `${(i * w).toFixed(2)},${(alto - (x / max) * alto).toFixed(1)}`).filter(Boolean).join(' ');
  return `<svg class="red-spark" viewBox="0 0 100 ${alto}" preserveAspectRatio="none"><polyline points="${pts}" /></svg>
    <div class="ent-nota">último ${v[v.length - 1]} ${unidad} · media ${(v.reduce((a, b) => a + b, 0) / v.length).toFixed(1)} · máx ${Math.max(...v)}</div>`;
}

function renderRedes() {
  if (!redesData) return;
  renderSubnetStats();
  const u = redesData.ultimo_escaneo;
  document.getElementById('red-info').textContent = u ? `red ${u.red} (${u.interfaz}) · último escaneo ${u.fecha.replace('T', ' ')} · se repite cada 15 min` : '';
  document.getElementById('graf-latencia').innerHTML = sparkline(redesData.latencia.map(p => p.internet), 'ms');
  document.getElementById('graf-velocidad').innerHTML = sparkline(redesData.velocidad.map(p => p.mbps), 'Mbps');
  document.getElementById('red-dispositivos').innerHTML = `<table class="red-tabla">${redesData.dispositivos.map(d => `
    <tr class="${d.conocido ? '' : 'nuevo'}">
      <td>${d.online ? '<span class="hoy-orb"></span>' : '<span class="hoy-orb off"></span>'}</td>
      <td><code>${esc(d.ip || '')}</code></td>
      <td><input class="carrera-input red-nombre" value="${esc(d.nombre || '')}" placeholder="${esc(d.propio ? 'este equipo' : d.hostname || d.fabricante || 'ponle nombre')}"
           onchange="marcarDispositivo('${esc(d.clave)}', { nombre: this.value })"></td>
      <td class="ent-nota">${esc(d.fabricante || '')}${d.hostname ? ' · ' + esc(d.hostname) : ''}</td>
      <td class="ent-nota"><code>${esc(d.mac || '')}</code></td>
      <td class="ent-nota">desde ${esc((d.primera || '').slice(0, 10))}</td>
      <td>${d.conocido ? '' : `<button class="icon-btn update" onclick="marcarDispositivo('${esc(d.clave)}', { conocido: true })" title="Es mío / lo conozco">✓ Conocido</button>`}</td>
    </tr>`).join('')}</table>
    <div class="ent-nota">Los dispositivos en ámbar son nuevos: si no sabes qué son, revisa quién está en tu WiFi.</div>`;
}

nuevoReto();
loadRedes();
setInterval(() => { if (document.getElementById('tab-redes')?.classList.contains('active')) loadRedes(); }, 5 * 60000);
