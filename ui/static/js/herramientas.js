// ── Selectores nativos (GTK vía PyWebView, con fallback a Flask) ──
async function nativePickFile(fileTypes) {
  if (window.pywebview?.api?.pick_file) {
    try {
      const path = await window.pywebview.api.pick_file(fileTypes || []);
      if (path) return path;
    } catch (e) {}
  }
  const ext = (fileTypes?.[0]?.match(/\*\.(\w+)/) || [])[1] || 'epub';
  const res = await fetch('/api/pick-file', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ext })
  });
  const data = await res.json();
  return data.path || null;
}
async function nativePickFolder() {
  if (window.pywebview?.api?.pick_folder) {
    try {
      const path = await window.pywebview.api.pick_folder();
      if (path) return path;
    } catch (e) {}
  }
  const res = await fetch('/api/pick-folder', { method: 'POST' });
  const data = await res.json();
  return data.path || null;
}
let pickerTarget = null;
async function _picker(run) {
  const path = await nativePickFolder();
  if (path) run(path);
}
async function pickerOrigen() {
  pickerTarget = 'org-origenes';
  await _picker(p => {
    const ta = document.getElementById('org-origenes');
    const lines = ta.value.split('\n').map(s => s.trim()).filter(Boolean);
    if (!lines.includes(p)) lines.push(p);
    ta.value = lines.join('\n');
  });
}
async function pickerDestino() {
  await _picker(p => {
    document.getElementById('org-destino').value = p;
  });
}

// ── Modal organización ────────────────────────────────────────────
function abrirModalOrg() {
  const saved = JSON.parse(safeStorage.getItem('orgConfig') || '{}');
  document.getElementById('org-origenes').value = (saved.origenes || ['~/Descargas', '~/Desktop']).join('\n');
  document.getElementById('org-destino').value = saved.destino || '~/Organizado';
  document.getElementById('org-modal').classList.add('show');
}
function cerrarModal() {
  document.getElementById('org-modal').classList.remove('show');
}
function guardarConfigOrg() {
  const raw = document.getElementById('org-origenes').value;
  const origenes = raw.split('\n').map(s => s.trim()).filter(Boolean);
  const destino = document.getElementById('org-destino').value.trim() || '~/Organizado';
  safeStorage.setItem('orgConfig', JSON.stringify({ origenes, destino }));
  cerrarModal();
  addLog(new Date().toTimeString().slice(0,8), `✓ Config guardada: ${origenes.length} origen(es) → ${destino}`);
}

// ── Organizador ───────────────────────────────────────────────────
let organizando = false;
async function organizarArchivos(dryRun = true) {
  if (organizando) return;
  organizando = true;
  const saved = JSON.parse(safeStorage.getItem('orgConfig') || '{}');
  const origenes = saved.origenes || ['~/Descargas', '~/Desktop'];
  const destino = saved.destino || '~/Organizado';
  addLog(new Date().toTimeString().slice(0,8), dryRun ? '🔍 Vista previa de organización...' : '🚀 Organizando archivos...');
  await fetch('/api/organize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dry_run: dryRun, origenes, destino })
  });
  organizando = false;
}

// ── EPUB ─────────────────────────────────────────────────────────
function abrirModalEpub() {
  document.getElementById('epub-modal').classList.add('show');
}
function cerrarModalEpub() {
  document.getElementById('epub-modal').classList.remove('show');
}
async function pickerEpub() {
  const path = await nativePickFile(['EPUB files (*.epub)']);
  if (path) {
    document.getElementById('epub-path').value = path;
    const name = path.split('/').pop();
    const size = await fetch('/api/file-size', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    }).then(r => r.json()).then(d => d.size || '').catch(() => '');
    document.getElementById('epub-icon').textContent = '📗';
    document.getElementById('epub-drop-text').textContent = name;
    document.getElementById('epub-drop-text').style.color = 'var(--amber)';
    document.getElementById('epub-file-info').textContent = size ? (size / 1024).toFixed(0) + ' KB' : '';
  }
}
async function pickerDestinoEpub() {
  const path = await nativePickFolder();
  if (path) document.getElementById('epub-output').value = path;
}
async function convertirEpub() {
  const path = document.getElementById('epub-path').value;
  if (!path) { alert('Selecciona un archivo .epub'); return; }
  cerrarModalEpub();
  addLog(new Date().toTimeString().slice(0,8), '🎵 Iniciando conversión EPUB...');
  await fetch('/api/convert-epub', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      epub_path: path,
      voz: document.getElementById('epub-voz').value,
      velocidad: parseFloat(document.getElementById('epub-speed').value),
      output_dir: document.getElementById('epub-output').value,
    })
  });
}

// ── PDF → Markdown ───────────────────────────────────────────────
let pdfIsDir = false;
function abrirModalPdf() {
  document.getElementById('pdf-modal').classList.add('show');
}
function cerrarModalPdf() {
  document.getElementById('pdf-modal').classList.remove('show');
}
async function pickerPdf() {
  const path = await nativePickFile(['Documentos (*.pdf;*.epub)']);
  if (path) {
    pdfIsDir = false;
    document.getElementById('pdf-path').value = path;
    const name = path.split('/').pop();
    const size = await fetch('/api/file-size', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    }).then(r => r.json()).then(d => d.size || '').catch(() => '');
    document.getElementById('pdf-icon').textContent = '📕';
    document.getElementById('pdf-drop-text').textContent = name;
    document.getElementById('pdf-drop-text').style.color = 'var(--blue)';
    document.getElementById('pdf-file-info').textContent = size ? (size / 1024 / 1024).toFixed(1) + ' MB' : '';
  }
}
async function pickerPdfFolder() {
  const path = await nativePickFolder();
  if (path) {
    pdfIsDir = true;
    document.getElementById('pdf-path').value = path;
    document.getElementById('pdf-icon').textContent = '📚';
    document.getElementById('pdf-drop-text').textContent = path;
    document.getElementById('pdf-drop-text').style.color = 'var(--blue)';
    document.getElementById('pdf-file-info').textContent = 'Se convertirán todos los .pdf de esta carpeta';
  }
}
async function pickerDestinoPdf() {
  const path = await nativePickFolder();
  if (path) document.getElementById('pdf-output').value = path;
}
async function convertirPdf() {
  const path = document.getElementById('pdf-path').value;
  if (!path) { alert('Selecciona un archivo .pdf o una carpeta'); return; }
  cerrarModalPdf();
  addLog(new Date().toTimeString().slice(0,8), '📄 Iniciando conversión PDF → Markdown (Docling)...');
  await fetch('/api/convert-pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pdf_path: path,
      output_dir: document.getElementById('pdf-output').value,
    })
  });
}

