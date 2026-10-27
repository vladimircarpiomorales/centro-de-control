importScripts("sensibles.js");

// Detecta recursos de video/audio que pide la página y los guarda por pestaña.
//
// El service worker de MV3 se suspende a los ~30 s de inactividad y pierde la
// memoria, así que el estado real vive en chrome.storage.session (se limpia al
// cerrar el navegador). El Map local es solo una caché para evitar una lectura
// asíncrona en cada request — en una página con HLS son cientos.

const MEDIA_RE   = /\.(m3u8|mpd|mp4|webm|m4v|mov|flv|mp3|m4a|aac|opus|ogg|wav)(\?|#|$)/i;
// Los segmentos son ruido: llegan por miles y no sirven sueltos. El manifiesto
// (.m3u8/.mpd) es el que lista todo, y es lo único que yt-dlp necesita.
const SEGMENT_RE = /\.(ts|m4s)(\?|#|$)/i;
const MAX_POR_TAB = 40;

const clave = (tabId) => `media_${tabId}`;
const cache = new Map();
// URL actual de cada pestaña, tomada del main_frame. La necesita el badge para
// saber qué dominio evaluar, y así evitamos el permiso "tabs".
const urlDe = new Map();

// ── Señal pasiva mientras navegas ─────────────────────────────────────────────
// El badge se pinta comparando el dominio contra sitios.json (los extractores de
// yt-dlp, generado por generar_sitios.py). Es local e instantáneo: NO se consulta
// al panel en cada página. Sondear cada URL que visitas mandaría tu navegación
// entera al panel y lanzaría un yt-dlp por página — un coste desproporcionado
// para una pista que se puede dar gratis.
//
// Por eso el badge dice "este SITIO suele funcionar", no "este VIDEO se descarga":
// login, DRM y geobloqueo solo los sabe la sonda del popup.

let sitios = null;

async function cargarSitios() {
  if (sitios) return sitios;

  // Prioridad: la lista que bajamos del panel (refleja el yt-dlp instalado hoy).
  // El sitios.json incluido es solo el respaldo del día que se empaquetó, para
  // que la extensión funcione aunque el panel nunca se abra.
  try {
    const { sitios_panel } = await chrome.storage.local.get("sitios_panel");
    if (sitios_panel?.dominios?.length) {
      sitios = new Set(sitios_panel.dominios);
      return sitios;
    }
  } catch {
    // storage inaccesible: caemos al archivo incluido.
  }

  try {
    const r = await fetch(chrome.runtime.getURL("sitios.json"));
    sitios = new Set(await r.json());
  } catch {
    sitios = new Set();
  }
  return sitios;
}

// Baja la lista del panel. Silenciosa a propósito: si el panel está apagado no
// pasa nada, seguimos con la lista que ya teníamos.
async function actualizarSitios() {
  const { panel } = await chrome.storage.local.get("panel");
  const url = (panel || "http://127.0.0.1:7788").replace(/\/+$/, "");
  try {
    const r = await fetch(`${url}/api/descargas/sitios`);
    if (!r.ok) return false;
    const d = await r.json();
    if (!Array.isArray(d.dominios) || d.dominios.length < 100) return false;  // respuesta sospechosa
    await chrome.storage.local.set({
      sitios_panel: { dominios: d.dominios, version: d.version, n: d.dominios.length, ts: Date.now() },
    });
    sitios = new Set(d.dominios);   // aplicar sin esperar al siguiente arranque
    return true;
  } catch {
    return false;
  }
}

// Al instalar/actualizar y una vez al día. Reintento a la hora: es normal que el
// panel esté cerrado justo cuando toca.
// Intenta actualizar y, si falla, programa un reintento. Lo normal es abrir el
// navegador ANTES que el panel, así que el primer intento de cada arranque falla
// casi siempre: sin reintento la lista se quedaría 24 h sin refrescar.
const MAX_REINTENTOS = 6;   // ~30 min; luego se espera a la alarma diaria

async function intentarActualizarSitios(esReintento = false) {
  if (await actualizarSitios()) {
    await chrome.storage.session.remove("sitios_intentos");
    return true;
  }
  // El contador vive en storage.session, no en una variable: el service worker se
  // suspende a los ~30 s y perdería la cuenta entre reintentos.
  const { sitios_intentos = 0 } = await chrome.storage.session.get("sitios_intentos");
  const n = esReintento ? sitios_intentos + 1 : 1;
  await chrome.storage.session.set({ sitios_intentos: n });
  if (n < MAX_REINTENTOS) {
    chrome.alarms.create("actualizar-sitios-retry", { delayInMinutes: 5 });
  }
  return false;
}

function programarActualizaciones() {
  // delayInMinutes explícito: con solo periodInMinutes la primera ejecución sería
  // a las 24 h, no ahora.
  chrome.alarms.create("actualizar-sitios", { delayInMinutes: 1, periodInMinutes: 1440 });
}

chrome.runtime.onInstalled.addListener(() => {
  programarActualizaciones();
  intentarActualizarSitios();
});

chrome.runtime.onStartup.addListener(() => {
  programarActualizaciones();
  intentarActualizarSitios();
});

async function soportado(url) {
  const lista = await cargarSitios();
  let host;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return false;
  }
  if (host.startsWith("www.")) host = host.slice(4);
  // Sufijo: "clases.udemy.com" cuenta como "udemy.com".
  if (lista.has(host)) return true;
  const p = host.split(".");
  for (let i = 1; i < p.length - 1; i++) {
    if (lista.has(p.slice(i).join("."))) return true;
  }
  return false;
}

async function pintarBadge(tabId, items, url) {
  let texto = "", color = "#c2410c";
  if (url && !esSensible(url) && await soportado(url)) {
    texto = "✓";
    color = "#15803d";               // verde: yt-dlp conoce este sitio
  } else if (items.length) {
    texto = String(items.length);    // naranja: solo hay streams crudos
  }
  try {
    await chrome.action.setBadgeText({ tabId, text: texto });
    await chrome.action.setBadgeBackgroundColor({ tabId, color });
  } catch {
    // La pestaña pudo cerrarse entre la detección y el badge.
  }
}

// Copia local del interruptor de pausa: onBeforeRequest es síncrono y no puede
// esperar una lectura de storage en cada petición.
let pausado = false;
chrome.storage.local.get("pausado").then((r) => { pausado = !!r.pausado; });
chrome.storage.onChanged.addListener((cambios, area) => {
  if (area === "local" && "pausado" in cambios) pausado = !!cambios.pausado.newValue;
});

async function leer(tabId) {
  if (cache.has(tabId)) return cache.get(tabId);
  const r = await chrome.storage.session.get(clave(tabId));
  const items = r[clave(tabId)] || [];
  cache.set(tabId, items);
  return items;
}

async function guardar(tabId, items) {
  cache.set(tabId, items);
  await chrome.storage.session.set({ [clave(tabId)]: items });
  await pintarBadge(tabId, items, urlDe.get(tabId));
}

chrome.webRequest.onBeforeRequest.addListener(
  (d) => {
    if (d.tabId < 0) return;

    // Navegar a otra página limpia lo detectado; si no, el popup mostraría los
    // videos de la anterior. Detectarlo por main_frame en vez de tabs.onUpdated
    // nos ahorra el permiso "tabs", que da acceso a TODAS las pestañas.
    if (d.type === "main_frame") {
      urlDe.set(d.tabId, d.url);
      guardar(d.tabId, []);
      return;
    }

    if (pausado || SEGMENT_RE.test(d.url)) return;

    // En sitios sensibles no guardamos nada: esas URLs llevan firmas de sesión.
    if (esSensible(d.url) || (d.initiator && esSensible(d.initiator))) return;

    const m = d.url.match(MEDIA_RE);
    if (d.type !== "media" && !m) return;

    // Sin await: onBeforeRequest en modo observación no espera la respuesta.
    leer(d.tabId).then((items) => {
      if (items.length >= MAX_POR_TAB || items.some((i) => i.url === d.url)) return;
      const tipo = m ? m[1].toLowerCase() : "media";
      // Los manifiestos van primero: son la opción buena cuando hay que elegir.
      const item = { url: d.url, tipo, manifiesto: tipo === "m3u8" || tipo === "mpd" };
      guardar(d.tabId, item.manifiesto ? [item, ...items] : [...items, item]);
    });
  },
  { urls: ["<all_urls>"], types: ["main_frame", "media", "xmlhttprequest", "other"] }
);

chrome.tabs.onRemoved.addListener((tabId) => {
  cache.delete(tabId);
  urlDe.delete(tabId);
  chrome.storage.session.remove(clave(tabId));
});

// ── Caducidad de las cookies ──────────────────────────────────────────────────
// Las cookies subidas son credenciales vivas. En vez de confiar en que el usuario
// se acuerde de pulsar "Borrar", las retiramos solas pasado el plazo.

chrome.alarms.onAlarm.addListener(async (alarma) => {
  if (alarma.name === "actualizar-sitios") {
    await intentarActualizarSitios();
    return;
  }

  if (alarma.name === "actualizar-sitios-retry") {
    await intentarActualizarSitios(true);
    return;
  }

  if (alarma.name !== "caducar-cookies") return;
  const { base } = await chrome.storage.local.get("base");
  const url = (base || "http://127.0.0.1:8086").replace(/\/+$/, "");
  try {
    await fetch(`${url}/delete-cookies`, { method: "POST" });
  } catch {
    // MeTube apagado: al encenderlo el popup mostrará que siguen ahí y avisará.
  }
  await chrome.storage.local.remove("ck_meta");
});
