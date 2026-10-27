// Sitios donde la extensión se apaga por completo: no detecta media y se niega a
// subir cookies.
//
// IMPORTANTE — esto es una red de seguridad, NO una garantía. Es imposible
// enumerar todos los bancos y servicios del mundo, así que un sitio sensible que
// no esté aquí pasará el filtro. Sirve para evitar el descuido (abrir el popup en
// la pestaña del banco por inercia), no para protegerte de una decisión
// deliberada. El criterio final sigue siendo tuyo.
//
// Se compara por ETIQUETAS DNS, no por subcadenas. Buscar "ing." suelto hacía
// match dentro de "learning.platzi.com", "streaming.*" y "training.*" — bloqueaba
// sitios de cursos legítimos. Las etiquetas evitan toda esa familia de errores.

// Subcadena libre: marcas largas y distintivas, sin riesgo de colisión.
const FRAGMENTOS = [
  "bbva", "santander", "caixa", "sabadell", "bankinter", "unicaja", "openbank",
  "paypal", "stripe.com", "wise.com", "revolut", "coinbase", "binance", "kraken.com",
  "interbank", "scotiabank", "pichincha", "mastercard", "americanexpress",
  "ing.com", "ing.es", "ing.nl",            // ING, con dominio completo
  "sunat", "reniec", "agenciatributaria", "seguridadsocial", "seg-social",
  "essalud", "sanitas", "adeslas", "doctoralia", "mapfre",
  "gmail", "hotmail", "outlook", "office.com", "sharepoint", "icloud",
  "protonmail", "proton.me", "tutanota", "fastmail", "zoho",
  "1password", "bitwarden", "lastpass", "dashlane", "keepersecurity",
  "authy", "okta.com", "duosecurity", "login.microsoftonline",
];

// La etiqueta debe EMPEZAR por esto ("banking" ✓ para "bank"; "learning" ✗ para "ing").
const PREFIJOS = [
  "bank", "banco", "banca", "caja", "bcp", "yape", "plin",
  "salud", "health", "hospital", "clinic",
  "mail", "webmail", "correo", "hacienda",
];

// La etiqueta debe ser EXACTAMENTE esto.
const ETIQUETAS = ["gob", "gov", "visa", "sat", "clave", "n26", "banco"];

function esSensible(url) {
  let host;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return false;   // URL no parseable: no es http(s), no nos interesa igual
  }
  if (FRAGMENTOS.some((p) => host.includes(p))) return true;

  const etiquetas = host.split(".");
  return etiquetas.some((e) => ETIQUETAS.includes(e) || PREFIJOS.some((p) => e.startsWith(p)));
}
