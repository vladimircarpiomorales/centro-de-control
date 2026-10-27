const BASE_DEFECTO  = "http://127.0.0.1:8086";   // MeTube
const PANEL_DEFECTO = "http://127.0.0.1:7788";   // Centro de Control (la sonda)

const $ = (id) => document.getElementById(id);
const estado = $("estado");

let tab = null;

function decir(msg, clase = "") {
  estado.textContent = msg;
  estado.className = clase;
}

async function base() {
  const { base } = await chrome.storage.local.get("base");
  return (base || BASE_DEFECTO).replace(/\/+$/, "");
}

async function panelBase() {
  const { panel } = await chrome.storage.local.get("panel");
  return (panel || PANEL_DEFECTO).replace(/\/+$/, "");
}

// ── Sonda: ¿se puede descargar de aquí? ───────────────────────────────────────
// Pregunta al panel, que corre yt-dlp en modo --simulate. Es la única respuesta
// fiable: saber que existe el extractor no basta, porque el video concreto puede
// pedir login, estar bloqueado por país o haber desaparecido.

// Cada veredicto se cachea por URL EXACTA, no por dominio: en el mismo sitio un
// video puede ser público y el siguiente de pago.
const VEREDICTOS = {
  ok:             { icono: "✅", clase: "ok" },
  necesita_login: { icono: "🔑", clase: "login" },
  edad:           { icono: "🔑", clase: "login" },
  sin_soporte:    { icono: "❌", clase: "no" },
  drm:            { icono: "🔒", clase: "no" },
  geo:            { icono: "🌍", clase: "no" },
  no_disponible:  { icono: "🚫", clase: "no" },
  en_vivo:        { icono: "🔴", clase: "login" },
  sin_conexion:   { icono: "📡", clase: "no" },
  lento:          { icono: "🐌", clase: "login" },
  error:          { icono: "⚠️", clase: "no" },
  sin_metube:     { icono: "⚠️", clase: "no" },
};

function pintarSonda(r) {
  const caja = $("sonda"), icono = $("s-icono"), txt = $("s-txt");
  $("s-otra").hidden = false;
  const v = VEREDICTOS[r.estado] || VEREDICTOS.error;
  caja.className = v.clase;
  icono.textContent = v.icono;

  let t = r.mensaje || r.estado;
  if (r.estado === "ok" && r.titulo) {
    t = r.duracion ? `${r.titulo} · ${r.duracion}` : r.titulo;
    if (r.con_cookies) t += " (con tus cookies)";
  } else if (r.detalle) {
    t += ` — ${r.detalle}`;
  }
  txt.textContent = t;
  txt.title = r.detalle || "";

  // Sin extractor, la única vía es el stream crudo: abre esa sección sola.
  if (r.estado === "sin_soporte") $("det").open = true;
}

// Misma lista que usa el badge (sitios.json, generado por generar_sitios.py).
let _sitios = null;

async function conocido(url) {
  if (!_sitios) {
    try {
      _sitios = new Set(await (await fetch(chrome.runtime.getURL("sitios.json"))).json());
    } catch {
      _sitios = new Set();
    }
  }
  let host;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return false;
  }
  if (host.startsWith("www.")) host = host.slice(4);
  if (_sitios.has(host)) return true;
  const p = host.split(".");
  for (let i = 1; i < p.length - 1; i++) {
    if (_sitios.has(p.slice(i).join("."))) return true;
  }
  return false;
}

// ── Estado de la lista de sitios ──────────────────────────────────────────────
// La mantiene al día el service worker (una vez al día). Esto solo lo muestra y
// permite forzarlo, para que no sea maquinaria invisible.

async function estadoLista() {
  const { sitios_panel } = await chrome.storage.local.get("sitios_panel");
  if (sitios_panel) {
    $("li-txt").textContent =
      `${sitios_panel.n} sitios · yt-dlp ${sitios_panel.version} · ${hace(sitios_panel.ts)}`;
  } else {
    const n = (await cargarListaLocal()).size;
    $("li-txt").textContent = `${n} sitios (lista incluida, sin actualizar aún)`;
  }
}

async function cargarListaLocal() {
  await conocido("https://x.invalid/");   // fuerza la carga de _sitios
  return _sitios || new Set();
}

async function actualizarLista() {
  const btn = $("li-act");
  btn.disabled = true;
  $("li-txt").textContent = "Pidiendo la lista al panel…";
  try {
    const r = await fetch(`${await panelBase()}/api/descargas/sitios?forzar=1`);
    const d = await r.json();
    if (!r.ok || !Array.isArray(d.dominios) || d.dominios.length < 100) {
      // El panel contestó, solo que con algo inservible. Decir "¿está abierto?"
      // aquí mandaría a mirar donde no está el problema.
      $("li-txt").textContent = "El panel respondió una lista inválida — se mantiene la anterior";
      decir(d.error || `Lista inválida (${r.status})`, "error");
      return;
    }
    await chrome.storage.local.set({
      sitios_panel: { dominios: d.dominios, version: d.version, n: d.dominios.length, ts: Date.now() },
    });
    _sitios = new Set(d.dominios);
    await estadoLista();
    decir(`✓ Lista actualizada — ${d.dominios.length} sitios`, "ok");
  } catch (e) {
    $("li-txt").textContent = "No pude actualizar — ¿está abierto el panel?";
    decir(String(e.message || e).slice(0, 80), "error");
  } finally {
    btn.disabled = false;
  }
}

function falloSonda(icono, texto) {
  $("sonda").className = "";
  $("s-icono").textContent = icono;
  $("s-txt").textContent = texto;
  $("s-otra").hidden = false;
}

async function sondar({ forzar = false } = {}) {
  const cacheKey = `sonda_${tab.url}`;
  if (!forzar) {
    const c = await chrome.storage.session.get(cacheKey);
    if (c[cacheKey]) return pintarSonda(c[cacheKey]);
  }

  // Pista instantánea desde sitios.json mientras llega el veredicto real: el
  // sondeo tarda ~2 s y dejar "Comprobando…" a secas parece que no hace nada.
  $("sonda").className = "";
  $("s-icono").textContent = "⏳";
  $("s-txt").textContent = (await conocido(tab.url))
    ? "Sitio conocido por yt-dlp — comprobando este video…"
    : "Comprobando el sitio…";
  $("s-otra").hidden = true;

  try {
    const r = await fetch(`${await panelBase()}/api/descargas/sonda`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: tab.url }),
    });
    // Un 404 NO es "el panel está cerrado": es un panel vivo corriendo código
    // viejo, sin la ruta de la sonda. Confundir ambos manda a buscar el problema
    // al sitio equivocado, así que se distinguen.
    if (r.status === 404) {
      return falloSonda("♻️", "El panel está abierto pero con código viejo — reinícialo");
    }
    const d = await r.json();
    if (!r.ok) return falloSonda("⚠️", d.error || `El panel respondió ${r.status}`);

    // Pintar ANTES de cachear, y que el cacheo no pueda tirar el veredicto: si
    // storage falla, perder la caché es irrelevante, pero perder la respuesta
    // mostraría "no hay respuesta" cuando el panel contestó perfectamente.
    pintarSonda(d);
    // try/catch propio, no un .catch() encadenado: si storage.session.set no
    // existiera, la llamada lanzaría de forma SINCRÓNICA y no habría promesa que
    // capturar — el error subiría al catch de abajo y borraría el veredicto ya
    // pintado, mostrando "no hay respuesta" cuando el panel sí contestó.
    try {
      await chrome.storage.session.set({ [cacheKey]: d });
    } catch {
      // Perder la caché no importa; perder el veredicto sí.
    }
    return;
  } catch {
    falloSonda("❔", `No hay respuesta en ${await panelBase()} — ¿está abierto el panel?`);
  }
}

// MeTube exige url + download_type + quality + format. Para video "any" deja que
// yt-dlp elija el mejor contenedor; forzar mp4 a veces obliga a recodificar.
async function enviar(url, tipo) {
  const cuerpo = tipo === "audio"
    ? { url, download_type: "audio", quality: "best", format: "mp3" }
    : { url, download_type: "video", quality: "best", format: "any" };

  decir("Enviando…");
  try {
    const r = await fetch(`${await base()}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...cuerpo, auto_start: true }),
    });
    const txt = await r.text();
    if (!r.ok) return decir(`Error ${r.status}: ${txt.slice(0, 90)}`, "error");
    const data = JSON.parse(txt);
    if (data.status === "ok") decir("✓ En la cola de MeTube", "ok");
    else decir(data.msg || "MeTube lo rechazó", "error");
  } catch (e) {
    decir(`No hay conexión con MeTube — ¿está encendido en el panel?`, "error");
  }
}

// ── Cookies ───────────────────────────────────────────────────────────────────
// MeTube guarda UN solo cookies.txt global, así que subir las de un sitio pisa
// las del anterior. No es un bug nuestro: es cómo funciona su /upload-cookies.

// Formato Netscape, 7 campos separados por TAB. yt-dlp rechaza el archivo si le
// falta esta cabecera exacta ("does not look like a Netscape format cookies file").
function aNetscape(cookies) {
  const lineas = ["# Netscape HTTP Cookie File", "# Generado por la extensión Enviar a MeTube", ""];
  for (const c of cookies) {
    lineas.push([
      c.domain,
      c.hostOnly ? "FALSE" : "TRUE",
      c.path,
      c.secure ? "TRUE" : "FALSE",
      Math.floor(c.expirationDate || 0),   // 0 = cookie de sesión
      c.name,
      c.value,
    ].join("\t"));
  }
  return lineas.join("\n") + "\n";
}

function hace(ts) {
  const min = Math.floor((Date.now() - ts) / 60000);
  if (min < 1) return "ahora mismo";
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  return h < 24 ? `hace ${h} h` : `hace ${Math.floor(h / 24)} d`;
}

async function estadoCookies() {
  const punto = $("ck-punto");
  const txt = $("ck-txt");
  try {
    const r = await fetch(`${await base()}/cookie-status`);
    const d = await r.json();
    if (!d.has_cookies) {
      punto.className = "punto no";
      txt.textContent = "Sin cookies en MeTube";
      return;
    }
    // Decir de QUÉ sitio son es la diferencia entre saber lo que tienes cargado y
    // subir credenciales a ciegas — MeTube solo guarda un cookies.txt global.
    const { ck_meta } = await chrome.storage.local.get("ck_meta");
    if (ck_meta) {
      const viejo = Date.now() - ck_meta.ts > 3600_000;
      punto.className = "punto " + (viejo ? "viejo" : "si");
      txt.textContent = `${ck_meta.n} cookies de ${ck_meta.host} · ${hace(ck_meta.ts)}`;
    } else {
      punto.className = "punto viejo";
      txt.textContent = "Cookies cargadas — origen desconocido";
    }
  } catch {
    punto.className = "punto";
    txt.textContent = "Cookies: MeTube no responde";
  }
}

// Subir cookies = entregar credenciales vivas. Pide confirmación explícita en dos
// pasos, con el número y el sitio delante, en vez de hacerlo al primer clic.
let confirmando = null;

async function subirCookies() {
  if (esSensible(tab.url)) return decir("Sitio sensible: no subo cookies de aquí.", "error");

  // getAll({url}) devuelve las cookies que el navegador ENVIARÍA a esa URL, que es
  // justo lo que necesita yt-dlp. Filtrar por {domain} fallaría: las cookies de
  // login viven en ".sitio.com", que no es subdominio de "www.sitio.com".
  const cookies = await chrome.cookies.getAll({ url: tab.url });
  if (!cookies.length) return decir("Este sitio no tiene cookies. ¿Iniciaste sesión?", "error");

  const host = new URL(tab.url).hostname;
  const btn = $("ck-subir");

  if (!confirmando) {
    btn.textContent = `¿Subir ${cookies.length} de ${host}?`;
    btn.classList.add("peligro");
    decir("Son credenciales de sesión. Pulsa otra vez para confirmar.", "error");
    confirmando = setTimeout(() => {
      confirmando = null;
      btn.textContent = "Subir cookies del sitio";
      btn.classList.remove("peligro");
      decir("");
    }, 6000);
    return;
  }

  clearTimeout(confirmando);
  confirmando = null;
  btn.textContent = "Subir cookies del sitio";
  btn.classList.remove("peligro");

  const texto = aNetscape(cookies);
  const bytes = new Blob([texto]).size;
  if (bytes > 1_000_000) return decir(`Demasiadas cookies (${(bytes / 1024).toFixed(0)} KB, máx 1 MB)`, "error");

  const fd = new FormData();
  // El campo TIENE que llamarse "cookies" — MeTube rechaza cualquier otro nombre.
  fd.append("cookies", new Blob([texto], { type: "text/plain" }), "cookies.txt");

  decir("Subiendo cookies…");
  try {
    const r = await fetch(`${await base()}/upload-cookies`, { method: "POST", body: fd });
    const d = await r.json();
    if (!r.ok || d.status !== "ok") return decir(d.msg || `Error ${r.status}`, "error");

    await chrome.storage.local.set({ ck_meta: { host, n: cookies.length, ts: Date.now() } });

    const min = Number($("plazo").value);
    await chrome.alarms.clear("caducar-cookies");
    if (min > 0) await chrome.alarms.create("caducar-cookies", { delayInMinutes: min });

    decir(`✓ ${cookies.length} cookies de ${host}` + (min ? ` · se borran en ${min} min` : ""), "ok");
    estadoCookies();
  } catch {
    decir("No hay conexión con MeTube", "error");
  }
}

async function borrarCookies() {
  try {
    const r = await fetch(`${await base()}/delete-cookies`, { method: "POST" });
    const d = await r.json();
    const ok = r.ok && d.status === "ok";
    if (ok) {
      await chrome.storage.local.remove("ck_meta");
      await chrome.alarms.clear("caducar-cookies");
    }
    decir(ok ? "✓ Cookies borradas" : (d.msg || `Error ${r.status}`), ok ? "ok" : "error");
    estadoCookies();
  } catch {
    decir("No hay conexión con MeTube", "error");
  }
}

function pintarStreams(items) {
  $("n").textContent = items.length;
  $("vacio").hidden = items.length > 0;
  const lista = $("lista");
  lista.textContent = "";

  for (const it of items) {
    const fila = document.createElement("div");
    fila.className = "stream";

    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = it.tipo;

    const code = document.createElement("code");
    // Solo el nombre del archivo: las URLs de CDN traen firmas larguísimas.
    code.textContent = decodeURIComponent(it.url.split("?")[0].split("/").pop() || it.url);
    code.title = it.url;

    const btn = document.createElement("button");
    btn.textContent = "Enviar";
    btn.addEventListener("click", () => enviar(it.url, "video"));

    fila.append(tag, code, btn);
    lista.append(fila);
  }
}

(async () => {
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  $("titulo").textContent = tab?.title || tab?.url || "—";
  $("base").value  = await base();
  $("panel").value = await panelBase();

  const esWeb = /^https?:/.test(tab?.url || "");
  const sensible = esWeb && esSensible(tab.url);

  if (sensible) {
    // En un sitio sensible no ofrecemos nada: ni descarga ni cookies. Es más
    // barato equivocarse por exceso aquí que subir el token del banco.
    const aviso = $("aviso");
    aviso.hidden = false;
    aviso.textContent =
      `Sitio sensible (${new URL(tab.url).hostname}). La extensión está desactivada aquí: ` +
      `no detecta media ni sube cookies. Si es un falso positivo, quita el patrón de sensibles.js.`;
  }

  const puedeDescargar = esWeb && !sensible;
  $("video").disabled = $("audio").disabled = !puedeDescargar;
  if (!esWeb) decir("Esta pestaña no es una página web.", "error");

  // La URL de la página, no la del stream: yt-dlp tiene extractores por sitio que
  // resuelven título, calidad y audio separado mucho mejor que una URL cruda.
  $("video").addEventListener("click", () => enviar(tab.url, "video"));
  $("audio").addEventListener("click", () => enviar(tab.url, "audio"));

  $("guardar").addEventListener("click", async () => {
    await chrome.storage.local.set({
      base:  $("base").value.trim()  || BASE_DEFECTO,
      panel: $("panel").value.trim() || PANEL_DEFECTO,
    });
    decir("Guardado", "ok");
    estadoCookies();
    if (puedeDescargar) sondar({ forzar: true });
  });

  $("ck-subir").disabled = !puedeDescargar;
  $("ck-subir").addEventListener("click", subirCookies);
  $("ck-borrar").addEventListener("click", borrarCookies);
  estadoCookies();

  $("li-act").addEventListener("click", actualizarLista);
  estadoLista();

  $("s-otra").addEventListener("click", () => sondar({ forzar: true }));
  if (puedeDescargar) {
    sondar();
  } else {
    // En un sitio sensible ni preguntamos: enviar la URL al panel sería justo lo
    // que prometimos no hacer aquí.
    $("sonda").hidden = true;
  }

  const { pausado } = await chrome.storage.local.get("pausado");
  $("pausa").checked = !!pausado;
  $("pausa").addEventListener("change", async (e) => {
    await chrome.storage.local.set({ pausado: e.target.checked });
    decir(e.target.checked ? "Detección pausada" : "Detección activa", "ok");
  });

  const r = await chrome.storage.session.get(`media_${tab.id}`);
  pintarStreams(sensible ? [] : (r[`media_${tab.id}`] || []));
})();
