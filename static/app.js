'use strict';
const $ = (selector) => document.querySelector(selector);
const state = { incidents: [], selected: null, current: null, detailRequest: 0, searching: 0, dirty: false, lastQuery: '' };
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const caseId = (id) => `INC-${String(id).padStart(4, '0')}`;
const badgeClass = (status) => status === 'Resuelta' ? 'closed' : status === 'En investigación' ? 'investigating' : '';
const dateLabel = (date) => new Date(date).toLocaleDateString('es-MX', {day:'2-digit', month:'short'});
const closureFields = [
  ['conclusion', 'Conclusión', '¿Qué ocurrió y qué explicación está respaldada?'],
  ['evidence', 'Evidencia y referencias', 'Documento, sección o página y mediciones que sostienen la conclusión.'],
  ['action_taken', 'Acción registrada', 'Qué se corrigió en la simulación, o por qué no se intervino.'],
  ['verification', 'Verificación del resultado', 'Compara los resultados con el criterio de aceptación. Incluye unidades, duración y límites.'],
  ['reviewed_by', 'Responsable de revisión', 'Tu nombre + revisión de ejercicio, si es una práctica.']
];
const statusHelp = {
  'Abierta': 'Reporte recibido. Todavía falta analizar el expediente.',
  'En investigación': 'Hipótesis y evidencia en revisión. Los datos o la comprobación pueden estar pendientes.',
  'Resuelta': 'Conclusión, evidencia, acción y verificación documentadas, con responsable de revisión.'
};

function closureForm(i) {
  return `<details class="closure-panel" id="closure-panel" ${i.status === 'Resuelta' ? 'open' : ''}><summary>Ficha de cierre <span>Conclusión y comprobación</span></summary><p class="muted">Completa esta ficha antes de marcar Resuelta. Puedes guardar un borrador mientras investigas. Faro comprueba que los campos tengan contenido; la validez de la conclusión requiere revisión humana.</p>${closureFields.map(([key, label, hint]) => `<label for="closure-${key}">${label}</label>${key === 'reviewed_by' ? `<input id="closure-${key}" maxlength="160" value="${escapeHtml(i[key] || '')}" placeholder="${escapeHtml(hint)}">` : `<textarea id="closure-${key}" rows="3" maxlength="5000" placeholder="${escapeHtml(hint)}">${escapeHtml(i[key] || '')}</textarea>`}`).join('')}<p class="muted" id="closed-at">${i.closed_at ? `Cierre guardado en Faro: ${escapeHtml(new Date(i.closed_at).toLocaleString('es-MX'))}` : 'Aún no hay un cierre guardado.'}</p></details>`;
}

function syncClosureFields() {
  const status = $('#case-status').value;
  $('#status-help').textContent = statusHelp[status];
  closureFields.forEach(([key]) => { $(`#closure-${key}`).required = status === 'Resuelta'; });
  if (status === 'Resuelta') $('#closure-panel').open = true;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'No se pudo completar la operación.');
  return result;
}
function notify(message, error = false) {
  const target = $('#notice');
  target.textContent = message;
  target.className = `notice${error ? ' error' : ''}`;
  target.hidden = false;
}
function renderList() {
  const term = $('#filter').value.toLocaleLowerCase();
  const status = $('#status-filter').value;
  const rows = state.incidents.filter((i) => `${i.title} ${i.equipment} ${caseId(i.id)}`.toLocaleLowerCase().includes(term) && (!status || i.status === status));
  $('#list-count').textContent = rows.length;
  $('#case-list').innerHTML = rows.length ? rows.map((i) => `<button class="case-card ${i.id === state.selected ? 'selected' : ''}" data-id="${i.id}" aria-pressed="${i.id === state.selected}"><span class="case-meta"><span class="case-id">${caseId(i.id)}</span><span class="badge ${i.priority === 'Alta' ? 'high' : ''}">${escapeHtml(i.priority)}</span></span><h3>${escapeHtml(i.title)}</h3><p>${escapeHtml(i.equipment)}</p><span class="case-bottom"><span class="badge ${badgeClass(i.status)}">${escapeHtml(i.status)}</span><small>${dateLabel(i.created_at)}</small></span></button>`).join('') : '<p class="empty">No hay incidencias que coincidan.<br>Crea un caso o cambia los filtros.</p>';
  $('#count-total').textContent = state.incidents.length;
  $('#count-active').textContent = state.incidents.filter((i) => i.status === 'En investigación').length;
  $('#count-closed').textContent = state.incidents.filter((i) => i.status === 'Resuelta').length;
  $('#count-docs').textContent = state.incidents.reduce((sum, i) => sum + i.document_count, 0);
}
async function refreshList() { state.incidents = await api('/api/incidents'); renderList(); }

function documentRows(docs) {
  return docs.map((d) => `<div class="document-row"><span class="doc-icon">${d.media_type === 'application/pdf' ? 'PDF' : 'TXT'}</span><div class="document-info"><a href="/api/documents/${d.id}/file" target="_blank" rel="noopener">${escapeHtml(d.name)} ↗</a><small>${d.page_count} ${d.media_type === 'application/pdf' ? 'página(s)' : 'sección(es)'}${d.synthetic ? ' · Ejemplo sintético' : ''}${d.empty_pages ? ` · ${d.empty_pages} sin texto extraíble` : ''}</small></div><button type="button" class="delete-document" data-delete-document="${d.id}" aria-label="Eliminar ${escapeHtml(d.name)}">Eliminar</button></div>`).join('');
}

function renderExcerpt(result) {
  if (!Array.isArray(result.excerpt_parts)) return escapeHtml(result.excerpt);
  return result.excerpt_parts.map((part) => part.highlight
    ? `<mark class="search-highlight">${escapeHtml(part.text)}</mark>`
    : escapeHtml(part.text)).join('');
}

async function deleteDocument(event) {
  const button = event.target.closest('[data-delete-document]');
  if (!button) return;
  const id = state.selected, documentId = Number(button.dataset.deleteDocument);
  const doc = state.current.documents.find((item) => item.id === documentId);
  if (!doc || !confirm(`¿Eliminar «${doc.name}» de esta incidencia? Se quitará el adjunto y su contenido de las búsquedas. El archivo original de tu computadora no se modifica.`)) return;
  button.disabled = true;
  try {
    await api(`/api/incidents/${id}/documents/${documentId}`, {method:'DELETE'});
    if (state.selected === id) {
      // Update just the document area; never replace unsaved review inputs.
      state.current.documents = state.current.documents.filter((item) => item.id !== documentId);
      $('#documents').innerHTML = documentRows(state.current.documents);
      $('#document-count').textContent = `${state.current.documents.length} adjunto(s)`;
      state.searching++;
      $('#search-results').textContent = '';
      if (state.lastQuery) await runSearch(state.lastQuery);
    }
    await refreshList();
    notify(`«${doc.name}» eliminado de ${caseId(id)}.`);
  } catch (error) { notify(error.message, true); }
  finally { button.disabled = false; }
}

async function selectIncident(id, force = false) {
  if (!force && state.dirty && !confirm('Tienes notas o un estado sin guardar. ¿Quieres descartarlos?')) return;
  const request = ++state.detailRequest;
  try {
    const i = await api(`/api/incidents/${id}`);
    if (request !== state.detailRequest) return;
    state.selected = id; state.current = i; state.dirty = false; state.searching++; state.lastQuery = '';
    renderList();
    $('#detail').innerHTML = `<header class="detail-heading"><div class="detail-topline"><span class="case-id">${caseId(i.id)} / DETALLE DEL CASO</span><span class="badge ${i.synthetic ? 'demo' : badgeClass(i.status)}">${i.synthetic ? 'CASO SINTÉTICO' : escapeHtml(i.status)}</span></div><h2>${escapeHtml(i.title)}</h2><span class="equipment">◈ &nbsp; ${escapeHtml(i.equipment)}</span></header>
      <div class="detail-body"><section class="observation"><h3 class="section-label">SÍNTOMAS OBSERVADOS</h3><p>${escapeHtml(i.symptoms)}</p></section><section class="conditions"><h3 class="section-label">CONDICIONES DE OPERACIÓN</h3><p>${escapeHtml(i.conditions || 'Sin condiciones registradas.')}</p></section>
      <div class="section-title"><h3>Documentos del caso</h3><span id="document-count">${i.documents.length} adjunto(s)</span></div><div id="documents">${documentRows(i.documents)}</div>
      <div class="upload-zone"><div><p>Agrega contexto a tu investigación</p><small>PDF con texto o TXT · hasta 10 MB</small></div><button class="secondary" id="upload-button">＋ Adjuntar</button><input id="file-input" type="file" accept=".pdf,.txt" hidden aria-label="Documento adjunto"></div>
      <section class="search-box"><h3>Busca evidencia en tus documentos</h3><p>Encuentra fragmentos por palabras clave. Los resultados son coincidencias documentales y requieren revisión.</p><form id="search-form" class="search-form"><label for="search-query" class="visually-hidden">Palabras clave para buscar evidencia</label><input id="search-query" type="search" maxlength="500" required placeholder="Ej. vibración temperatura"><button class="primary" type="submit">Buscar</button></form><div id="search-results" aria-live="polite"></div></section>
      <form class="review-form" id="review-form"><label for="notes">NOTAS DE INVESTIGACIÓN</label><textarea id="notes" maxlength="10000" placeholder="Observaciones, hipótesis, fuentes y próximos pasos…">${escapeHtml(i.notes)}</textarea>${closureForm(i)}<div class="review-bottom"><label for="case-status" class="visually-hidden">Estado del caso</label><select id="case-status" aria-describedby="status-help">${['Abierta','En investigación','Resuelta'].map((s) => `<option ${s === i.status ? 'selected' : ''}>${s}</option>`).join('')}</select><button class="secondary" type="submit">Guardar revisión</button></div><p class="muted" id="status-help"></p></form><div class="detail-links"><a href="/api/incidents/${i.id}/export" download>Exportar registro JSON ↗</a></div></div>`;
    $('#upload-button').onclick = () => $('#file-input').click();
    $('#file-input').onchange = uploadDocument;
    $('#documents').onclick = deleteDocument;
    $('#search-form').onsubmit = search;
    $('#review-form').onsubmit = saveReview;
    $('#notes').oninput = () => { state.dirty = true; };
    closureFields.forEach(([key]) => {
      $(`#closure-${key}`).oninput = () => { state.dirty = true; };
      $(`#closure-${key}`).oninvalid = () => { $('#closure-panel').open = true; };
    });
    $('#case-status').onchange = () => { state.dirty = true; syncClosureFields(); };
    syncClosureFields();
  } catch (error) { notify(error.message, true); }
}

async function uploadDocument(event) {
  const file = event.target.files[0];
  if (!file) return;
  const id = state.selected;
  const button = $('#upload-button');
  if (file.size > 10 * 1024 * 1024) return notify('El archivo supera el límite de 10 MB.', true);
  button.disabled = true; button.textContent = 'Procesando…';
  try {
    await api(`/api/incidents/${id}/documents`, {method:'POST', headers:{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(file.name)}, body:file});
    const updated = await api(`/api/incidents/${id}`);
    if (state.selected === id) {
      state.current.documents = updated.documents;
      $('#documents').innerHTML = documentRows(updated.documents);
      $('#document-count').textContent = `${updated.documents.length} adjunto(s)`;
    }
    await refreshList();
    notify(`Documento adjuntado a ${caseId(id)}. Ya puedes buscar en su contenido.`);
  } catch (error) { notify(error.message, true); }
  finally { button.disabled = false; button.textContent = '＋ Adjuntar'; event.target.value = ''; }
}

async function search(event) {
  event.preventDefault();
  const query = $('#search-query').value.trim();
  if (!query) return;
  state.lastQuery = query;
  await runSearch(query);
}

async function runSearch(query) {
  const id = state.selected, request = ++state.searching;
  const button = $('#search-form button');
  button.disabled = true;
  $('#search-results').textContent = 'Buscando…';
  try {
    const rows = await api(`/api/incidents/${id}/search?q=${encodeURIComponent(query)}`);
    if (state.selected !== id || request !== state.searching) return;
    $('#search-results').innerHTML = rows.length ? `<div class="search-meta">${rows.length} fragmento(s) · ordenados por relevancia textual</div>` + rows.map((r) => `<article class="search-result"><a href="/api/documents/${r.document_id}/file${r.media_type === 'application/pdf' ? `#page=${r.page}` : ''}" target="_blank" rel="noopener">${escapeHtml(r.name)} · ${r.media_type === 'application/pdf' ? 'página' : 'sección'} ${r.page} ↗</a><p>${renderExcerpt(r)}</p></article>`).join('') : '<p class="search-meta">No se encontraron coincidencias. Prueba otras palabras o adjunta una fuente relevante. La ausencia de resultados no descarta una falla.</p>';
  } catch (error) { if (state.selected === id && request === state.searching) $('#search-results').textContent = error.message; }
  finally { if (state.selected === id && request === state.searching) button.disabled = false; }
}

async function saveReview(event) {
  event.preventDefault();
  const id = state.selected, button = event.target.querySelector('button');
  const notes = $('#notes').value, status = $('#case-status').value;
  const closure = Object.fromEntries(closureFields.map(([key]) => [key, $(`#closure-${key}`).value]));
  button.disabled = true;
  try {
    const saved = await api(`/api/incidents/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({notes,status,...closure})});
    if (state.selected === id && !saved.synthetic) {
      const badge = $('.detail-topline .badge');
      badge.textContent = saved.status;
      badge.className = `badge ${badgeClass(saved.status)}`;
    }
    if (state.selected === id) {
      $('#closed-at').textContent = saved.closed_at ? `Cierre guardado en Faro: ${new Date(saved.closed_at).toLocaleString('es-MX')}` : 'Aún no hay un cierre guardado.';
      if ($('#notes').value === notes && $('#case-status').value === status && closureFields.every(([key]) => $(`#closure-${key}`).value === closure[key])) state.dirty = false;
    }
    await refreshList(); notify(`Revisión de ${caseId(id)} guardada.`);
  } catch (error) { notify(error.message, true); }
  finally { button.disabled = false; }
}

$('#case-list').onclick = (event) => { const card = event.target.closest('[data-id]'); if (card) selectIncident(Number(card.dataset.id)); };
$('#filter').oninput = $('#status-filter').onchange = renderList;
$('#new-incident').onclick = () => { $('#form-error').textContent = ''; $('#incident-dialog').showModal(); };
$('#close-dialog').onclick = $('#cancel-dialog').onclick = () => $('#incident-dialog').close();
$('#incident-form').onsubmit = async (event) => {
  event.preventDefault();
  if (state.dirty && !confirm('Al abrir el nuevo caso se descartarán los cambios sin guardar del caso actual. ¿Continuar?')) return;
  const button = event.target.querySelector('[type=submit]'); button.disabled = true;
  try {
    const result = await api('/api/incidents', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});
    $('#incident-dialog').close(); event.target.reset(); $('#filter').value = ''; $('#status-filter').value = '';
    await refreshList(); await selectIncident(result.id, true); notify(`${caseId(result.id)} creada. Puedes adjuntar documentos y comenzar la investigación.`);
  } catch (error) { $('#form-error').textContent = error.message; }
  finally { button.disabled = false; }
};
window.addEventListener('beforeunload', (event) => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
(async () => { try { await refreshList(); if (state.incidents.length) await selectIncident(state.incidents[0].id); } catch (error) { $('#case-list').innerHTML = '<p class="empty">No se pudo conectar con el servidor.</p>'; notify(error.message, true); } })();
