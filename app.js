const state = {
  data: null,
  current: new Date(),
  filters: { search: "", sede: "", kind: "", status: "" }
};
const $ = (id) => document.getElementById(id);
const fmtMonth = new Intl.DateTimeFormat("es-CO", { month: "long", year: "numeric" });
function unique(values) { return [...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b, "es")); }
function filteredEvents() {
  const f = state.filters;
  return state.data.events.filter(e => {
    const haystack = [e.entity_name, e.sede, e.facultad, e.nivel, e.acto_administrativo, e.event_label].filter(Boolean).join(" ").toLowerCase();
    return (!f.search || haystack.includes(f.search.toLowerCase())) && (!f.sede || e.sede === f.sede) && (!f.kind || e.entity_kind === f.kind) && (!f.status || e.status === f.status);
  });
}
function entityById(id) { return state.data.entities.find(e => e.id === id); }
function fillFilters() {
  unique(state.data.entities.map(e => e.sede)).forEach(v => $("sedeFilter").insertAdjacentHTML("beforeend", `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`));
  unique(state.data.entities.map(e => e.kind)).forEach(v => $("kindFilter").insertAdjacentHTML("beforeend", `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`));
}
function renderSummary() {
  const ev = filteredEvents();
  const entityIds = new Set(ev.map(e => e.entity_id));
  const sourced = new Set(ev.filter(e => (e.documents || []).length).map(e => e.entity_id)).size;
  const undated = ev.filter(e => !e.month || !e.day).length;
  $("summary").innerHTML = `
    <div class="metric"><strong>${entityIds.size}</strong><span>entidades visibles</span></div>
    <div class="metric"><strong>${ev.length}</strong><span>hitos históricos</span></div>
    <div class="metric"><strong>${sourced}</strong><span>entidades con fuente localizada</span></div>
    <div class="metric"><strong>${undated}</strong><span>hitos sin día exacto</span></div>`;
}
function renderCalendar() {
  const y = state.current.getFullYear(), m = state.current.getMonth();
  $("monthTitle").textContent = fmtMonth.format(state.current);
  const ev = filteredEvents().filter(e => e.month === m + 1 && e.day);
  $("monthSubtitle").textContent = `${ev.length} hito${ev.length === 1 ? "" : "s"} registrado${ev.length === 1 ? "" : "s"} en este mes`;
  const first = new Date(y, m, 1), last = new Date(y, m + 1, 0);
  const firstMondayIndex = (first.getDay() + 6) % 7;
  const cells = Math.ceil((firstMondayIndex + last.getDate()) / 7) * 7;
  const start = new Date(y, m, 1 - firstMondayIndex);
  let html = "";
  for (let i = 0; i < cells; i++) {
    const d = new Date(start); d.setDate(start.getDate() + i);
    const outside = d.getMonth() !== m;
    const dayEvents = outside ? [] : ev.filter(e => e.day === d.getDate());
    html += `<div class="day ${outside ? "outside" : ""}"><div class="day-number">${d.getDate()}</div>`;
    dayEvents.slice(0,3).forEach(e => {
      const ann = e.original_year ? y - e.original_year : null;
      const annText = ann >= 0 ? ` · ${ann} años` : "";
      html += `<button class="event-chip ${e.status === "con-acto-sin-documento" ? "pending" : ""}" data-event="${e.id}">${escapeHtml(e.entity_name)}${annText}</button>`;
    });
    if (dayEvents.length > 3) html += `<div class="more">+${dayEvents.length - 3} más</div>`;
    html += `</div>`;
  }
  $("calendar").innerHTML = html;
  document.querySelectorAll("[data-event]").forEach(btn => btn.addEventListener("click", () => openEvent(btn.dataset.event)));
}
const MONTHS = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
function renderMonthList() {
  const m = state.current.getMonth() + 1, y = state.current.getFullYear();
  const ev = filteredEvents().filter(e => e.month === m && e.day).sort((a,b) => a.day - b.day || a.entity_name.localeCompare(b.entity_name, "es"));
  $("monthList").innerHTML = ev.length ? ev.map(e => {
    const ann = e.original_year ? y - e.original_year : null;
    return `<article class="event-row"><div class="event-date">${String(e.day).padStart(2,"0")} ${MONTHS[e.month-1]}</div><div><h3>${escapeHtml(e.entity_name)}</h3><p>${escapeHtml(e.event_label)}${ann >= 0 ? ` · ${ann} años en ${y}` : ""} · ${escapeHtml(e.sede || "Sede pendiente")}</p></div><button data-event="${e.id}">Ver ficha</button></article>`;
  }).join("") : `<p class="empty">No hay efemérides para los filtros seleccionados en este mes.</p>`;
  document.querySelectorAll("#monthList [data-event]").forEach(btn => btn.addEventListener("click", () => openEvent(btn.dataset.event)));
}
function renderUndated() {
  const ev = filteredEvents().filter(e => !e.month || !e.day).slice(0,50);
  $("undatedList").innerHTML = ev.length ? ev.map(e => `<article class="event-row"><div class="event-date">—</div><div><h3>${escapeHtml(e.entity_name)}</h3><p>${escapeHtml(e.event_label)} · ${escapeHtml(e.date_text || "Fecha pendiente")}</p></div><button data-event="${e.id}">Ver ficha</button></article>`).join("") : `<p class="empty">No hay fechas incompletas con los filtros actuales.</p>`;
  document.querySelectorAll("#undatedList [data-event]").forEach(btn => btn.addEventListener("click", () => openEvent(btn.dataset.event)));
}
function openEvent(eventId) {
  const e = state.data.events.find(x => x.id === eventId);
  if (!e) return;
  const entity = entityById(e.entity_id);
  const dateLabel = e.original_date ? new Intl.DateTimeFormat("es-CO", { day:"numeric", month:"long", year:"numeric", timeZone:"UTC" }).format(new Date(e.original_date + "T00:00:00Z")) : (e.date_text || "Pendiente");
  const docs = (entity.documents || []).length ? entity.documents.map(d => {
    const href = d.pdf_url || d.source_url, text = d.pdf_url ? "Ver PDF" : "Abrir fuente";
    return `<a class="doc-link" href="${escapeAttr(href)}" target="_blank" rel="noopener"><span>${escapeHtml(d.label)} <small>${escapeHtml(d.status)}</small></span><strong>${text} ↗</strong></a>`;
  }).join("") : `<div class="empty">El acto está registrado, pero el PDF todavía no ha sido incorporado al repositorio.</div>`;
  $("dialogContent").innerHTML = `<p class="eyebrow">${escapeHtml(entity.kind)} · ${escapeHtml(entity.sede || "Sede pendiente")}</p><h2>${escapeHtml(entity.name)}</h2><p>${escapeHtml(e.event_label)}: <strong>${escapeHtml(dateLabel)}</strong></p><div class="detail-meta"><div><small>Facultad</small>${escapeHtml(entity.facultad || "No aplica / pendiente")}</div><div><small>Nivel</small>${escapeHtml(entity.nivel || entity.kind)}</div><div><small>Acto administrativo</small>${escapeHtml(entity.acto_administrativo || "Pendiente")}</div><div><small>Autoridad</small>${escapeHtml(entity.acto_por || "Pendiente")}</div></div><span class="badge ${entity.status === "con-acto-sin-documento" ? "pending" : ""}">${escapeHtml(entity.status)}</span><h3>Soporte documental</h3><div class="docs">${docs}</div>`;
  $("detailDialog").showModal();
}
function downloadICS() {
  const ev = filteredEvents().filter(e => e.month && e.day), now = new Date(), stamp = now.toISOString().replace(/[-:]/g,"").replace(/\.\d{3}Z$/,"Z");
  const lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Efemerides UNAL//ES","CALSCALE:GREGORIAN"];
  ev.forEach(e => {
    const yr = e.original_year || now.getFullYear(), mm = String(e.month).padStart(2,"0"), dd = String(e.day).padStart(2,"0");
    const desc = [e.event_label, e.acto_administrativo, e.sede].filter(Boolean).join(" | ").replace(/\n/g," ");
    lines.push("BEGIN:VEVENT",`UID:${e.id}@efemerides-unal`,`DTSTAMP:${stamp}`,`DTSTART;VALUE=DATE:${yr}${mm}${dd}`,"RRULE:FREQ=YEARLY",`SUMMARY:${icsEscape(e.entity_name)}`,`DESCRIPTION:${icsEscape(desc)}`,"END:VEVENT");
  });
  lines.push("END:VCALENDAR");
  const blob = new Blob([lines.join("\r\n")], {type:"text/calendar;charset=utf-8"}), url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url; a.download = "efemerides-unal.ics"; a.click(); URL.revokeObjectURL(url);
}
function renderAll() { renderSummary(); renderCalendar(); renderMonthList(); renderUndated(); }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch])); }
function escapeAttr(value) { return escapeHtml(value); }
function icsEscape(value) { return String(value ?? "").replace(/\\/g,"\\\\").replace(/,/g,"\\,").replace(/;/g,"\\;").replace(/\n/g,"\\n"); }
async function init() {
  const manifest = await fetch("data/manifest.json").then(r => r.json());
  const chunks = await Promise.all(manifest.parts.map(p => fetch(p).then(r => r.text())));
  state.data = JSON.parse(chunks.join(""));
  fillFilters();
  $("searchInput").addEventListener("input", e => { state.filters.search = e.target.value.trim(); renderAll(); });
  $("sedeFilter").addEventListener("change", e => { state.filters.sede = e.target.value; renderAll(); });
  $("kindFilter").addEventListener("change", e => { state.filters.kind = e.target.value; renderAll(); });
  $("statusFilter").addEventListener("change", e => { state.filters.status = e.target.value; renderAll(); });
  $("prevMonth").addEventListener("click", () => { state.current = new Date(state.current.getFullYear(), state.current.getMonth()-1, 1); renderAll(); });
  $("nextMonth").addEventListener("click", () => { state.current = new Date(state.current.getFullYear(), state.current.getMonth()+1, 1); renderAll(); });
  $("downloadIcs").addEventListener("click", downloadICS);
  $("closeDialog").addEventListener("click", () => $("detailDialog").close());
  $("detailDialog").addEventListener("click", e => { if (e.target === $("detailDialog")) $("detailDialog").close(); });
  renderAll();
}
init();