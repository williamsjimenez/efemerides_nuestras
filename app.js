const CALENDAR_YEAR = new Date().getFullYear();
const state = {
  data: null,
  current: new Date(CALENDAR_YEAR, new Date().getMonth(), 1),
  filters: { search: "", sede: "", kind: "", status: "" }
};
const $ = (id) => document.getElementById(id);
const fmtMonth = new Intl.DateTimeFormat("es-CO", { month: "long" });
function unique(values) { return [...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b, "es")); }
function filteredEvents() {
  const f = state.filters;
  return state.data.events.filter(e => {
    const haystack = [e.entity_name, e.sede, e.facultad, e.nivel, e.acto_administrativo, e.event_label].filter(Boolean).join(" ").toLowerCase();
    return (!f.search || haystack.includes(f.search.toLowerCase())) && (!f.sede || e.sede === f.sede) && (!f.kind || e.entity_kind === f.kind) && (!f.status || e.status === f.status);
  });
}
function entityById(id) { return state.data.entities.find(e => e.id === id); }
function expandCompact(raw) {
  if (!raw || !Array.isArray(raw.r)) return raw;
  const entities = [];
  const events = [];

  const parsedDate = (value) => {
    const exact = typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
    if (exact) {
      const [year, month, day] = value.split("-").map(Number);
      return { value, exact: true, year, month, day };
    }
    let year = null;
    if (typeof value === "string") {
      const match = value.match(/(19|20)\d{2}/);
      if (match) year = Number(match[0]);
    }
    return { value, exact: false, year, month: null, day: null };
  };

  raw.r.forEach((r) => {
    const [id, name, kind, sede, facultad, nivel, acto, actoPor, documents, status, dates] = r;
    const sourceDates = Array.isArray(dates) ? dates : [];

    let creationYear = null;
    let creationDate = null;

    sourceDates.forEach((item) => {
      const label = String(item?.[0] || "").toLowerCase();
      if (label === "creación" || label.includes("creación y celebración")) {
        const p = parsedDate(item?.[1] || null);
        if (creationYear === null && p.year !== null) creationYear = p.year;
        if (creationDate === null && p.exact) creationDate = p.value;
      }
    });

    const entity = {
      id, name, kind, sede, facultad, nivel,
      programa: kind === "Programa" ? name : null,
      creation_year: creationYear,
      creation_date: creationDate,
      acto_administrativo: acto,
      acto_por: actoPor,
      documents: documents || [],
      status: status || "pendiente"
    };
    entities.push(entity);

    const candidates = [];
    sourceDates.forEach((item) => {
      const labelRaw = item?.[0] || "Fecha de celebración";
      const label = String(labelRaw).toLowerCase();
      const value = item?.[1] || null;

      const isSameCreationCelebration = label.includes("creación y celebración");
      const isCelebration = label.includes("celebración");
      const isComplementary = label.includes("fecha histórica complementaria");

      if (!isSameCreationCelebration && !isCelebration && !isComplementary) return;

      const p = parsedDate(value);
      candidates.push({
        label: isComplementary ? "Fecha de celebración complementaria" : "Fecha de celebración",
        source_label: labelRaw,
        ...p
      });
    });

    const seen = new Set();
    const uniqueCandidates = candidates.filter((c) => {
      const key = c.exact ? `d:${c.month}-${c.day}` : `t:${String(c.value || "").trim().toLowerCase()}`;
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    if (uniqueCandidates.length) {
      uniqueCandidates.forEach((c, i) => {
        events.push({
          id: `${id}-celebracion-${i + 1}`,
          entity_id: id,
          entity_name: name,
          entity_kind: kind,
          sede, facultad, nivel,
          event_type: i === 0 ? "celebracion" : "celebracion-complementaria",
          event_label: c.label,
          original_date: c.exact ? c.value : null,
          date_text: c.exact ? null : c.value,
          precision: c.exact ? "day" : "text",
          creation_year: creationYear,
          creation_date: creationDate,
          celebration_source_year: c.year,
          month: c.month,
          day: c.day,
          acto_administrativo: acto,
          acto_por: actoPor,
          documents: documents || [],
          status: status || "pendiente",
          synthetic_pending: false
        });
      });
    } else {
      events.push({
        id: `${id}-pending-celebration`,
        entity_id: id,
        entity_name: name,
        entity_kind: kind,
        sede, facultad, nivel,
        event_type: "celebracion-pendiente",
        event_label: "Fecha de celebración pendiente",
        original_date: null,
        date_text: "Sin día y mes de celebración registrados",
        precision: "pending",
        creation_year: creationYear,
        creation_date: creationDate,
        celebration_source_year: null,
        month: null,
        day: null,
        acto_administrativo: acto,
        acto_por: actoPor,
        documents: documents || [],
        status: status || "pendiente",
        synthetic_pending: true
      });
    }
  });

  return {
    meta: { record_count: raw.m?.records || entities.length, event_count: events.length },
    entities,
    events
  };
}
function sedeLabel(value) {
  if (!value) return null;
  return /^sede\s/i.test(value) ? value : `Sede ${value}`;
}
function eventContext(e, year) {
  const entity = entityById(e.entity_id) || {};
  const kind = entity.kind || e.entity_kind || "";
  const name = entity.name || e.entity_name || "";
  const sede = entity.sede || e.sede;
  const facultad = entity.facultad || e.facultad;
  const parts = [];

  if (kind !== "Sede" && sede) parts.push(sedeLabel(sede));
  if (kind !== "Sede" && kind !== "Facultad" && facultad && facultad !== name) parts.push(facultad);

  const creationYear = entity.creation_year ?? e.creation_year ?? null;
  const ann = creationYear ? CALENDAR_YEAR - creationYear : null;
  if (ann !== null && ann >= 0) parts.push(`${ann} años`);

  return parts.join(" · ");
}
function fillFilters() {
  unique(state.data.entities.map(e => e.sede)).forEach(v => $("sedeFilter").insertAdjacentHTML("beforeend", `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`));
  unique(state.data.entities.map(e => e.kind)).forEach(v => $("kindFilter").insertAdjacentHTML("beforeend", `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`));
}
function renderSummary() {
  const ev = filteredEvents();
  const entityIds = new Set(ev.map(e => e.entity_id));
  const sourced = new Set(ev.filter(e => (e.documents || []).length).map(e => e.entity_id)).size;
  const dated = ev.filter(e => e.month && e.day && !e.synthetic_pending).length;
  const noDate = new Set(ev.filter(e => e.synthetic_pending || !e.month || !e.day).map(e => e.entity_id)).size;
  $("summary").innerHTML = `
    <div class="metric"><strong>${entityIds.size}</strong><span>registros visibles</span></div>
    <div class="metric"><strong>${dated}</strong><span>fechas con día exacto</span></div>
    <div class="metric"><strong>${noDate}</strong><span>sin fecha de celebración</span></div>
    <div class="metric"><strong>${sourced}</strong><span>entidades con fuente localizada</span></div>`;
}
function renderCalendar() {
  const y = CALENDAR_YEAR, m = state.current.getMonth();
  $("monthTitle").textContent = fmtMonth.format(state.current);
  const ev = filteredEvents().filter(e => e.month === m + 1 && e.day);
  $("monthSubtitle").textContent = `${ev.length} celebración${ev.length === 1 ? "" : "es"} registrada${ev.length === 1 ? "" : "s"} en este mes`;
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
      const context = eventContext(e, y);
      html += `<button class="event-chip ${e.status === "con-acto-sin-documento" ? "pending" : ""}" data-event="${e.id}">
        <span class="event-chip-title">${escapeHtml(e.entity_name)}</span>
        ${context ? `<span class="event-chip-meta">${escapeHtml(context)}</span>` : ""}
      </button>`;
    });
    if (dayEvents.length > 3) html += `<div class="more">+${dayEvents.length - 3} más</div>`;
    html += `</div>`;
  }
  $("calendar").innerHTML = html;
  document.querySelectorAll("[data-event]").forEach(btn => btn.addEventListener("click", () => openEvent(btn.dataset.event)));
}
const MONTHS = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
function renderMonthList() {
  const m = state.current.getMonth() + 1, y = CALENDAR_YEAR;
  const ev = filteredEvents().filter(e => e.month === m && e.day).sort((a,b) => a.day - b.day || a.entity_name.localeCompare(b.entity_name, "es"));
  $("monthList").innerHTML = ev.length ? ev.map(e => {
    const context = eventContext(e, y);
    return `<article class="event-row"><div class="event-date">${String(e.day).padStart(2,"0")} ${MONTHS[e.month-1]}</div><div><h3>${escapeHtml(e.entity_name)}</h3><p>${context ? escapeHtml(context) : escapeHtml(e.event_label)}</p></div><button data-event="${e.id}">Ver ficha</button></article>`;
  }).join("") : `<p class="empty">No hay efemérides para los filtros seleccionados en este mes.</p>`;
  document.querySelectorAll("#monthList [data-event]").forEach(btn => btn.addEventListener("click", () => openEvent(btn.dataset.event)));
}
function renderUndated() {
  const ev = filteredEvents().filter(e => !e.month || !e.day).sort((a,b) => (a.sede || "").localeCompare(b.sede || "", "es") || (a.facultad || "").localeCompare(b.facultad || "", "es") || a.entity_name.localeCompare(b.entity_name, "es"));
  $("undatedList").innerHTML = ev.length ? ev.map(e => `<article class="event-row"><div class="event-date">—</div><div><h3>${escapeHtml(e.entity_name)}</h3><p>${escapeHtml(e.event_label)} · ${escapeHtml(e.date_text || "Fecha pendiente")}</p></div><button data-event="${e.id}">Ver ficha</button></article>`).join("") : `<p class="empty">No hay fechas incompletas con los filtros actuales.</p>`;
  document.querySelectorAll("#undatedList [data-event]").forEach(btn => btn.addEventListener("click", () => openEvent(btn.dataset.event)));
}
function openEvent(eventId) {
  const e = state.data.events.find(x => x.id === eventId);
  if (!e) return;
  const entity = entityById(e.entity_id);
  const celebrationLabel = e.month && e.day
    ? new Intl.DateTimeFormat("es-CO", { day:"numeric", month:"long", timeZone:"UTC" }).format(new Date(Date.UTC(2000, e.month - 1, e.day)))
    : (e.date_text || "Pendiente");

  const docs = (entity.documents || []).length ? entity.documents.map(d => {
    const href = d.pdf_url || d.source_url, text = d.pdf_url ? "Ver PDF" : "Abrir fuente";
    return `<a class="doc-link" href="${escapeAttr(href)}" target="_blank" rel="noopener"><span>${escapeHtml(d.label)} <small>${escapeHtml(d.status)}</small></span><strong>${text} ↗</strong></a>`;
  }).join("") : `<div class="empty">El acto está registrado, pero el PDF todavía no ha sido incorporado al repositorio.</div>`;

  const age = entity.creation_year ? CALENDAR_YEAR - entity.creation_year : null;
  $("dialogContent").innerHTML = `<p class="eyebrow">${escapeHtml(entity.kind)} · ${escapeHtml(entity.sede || "Sede pendiente")}</p>
    <h2>${escapeHtml(entity.name)}</h2>
    <p>Fecha de celebración: <strong>${escapeHtml(celebrationLabel)}</strong></p>
    <div class="detail-meta">
      <div><small>Año de creación</small>${escapeHtml(entity.creation_year ?? "Pendiente")}</div>
      <div><small>Años cumplidos en ${CALENDAR_YEAR}</small>${escapeHtml(age ?? "Pendiente")}</div>
      <div><small>Facultad</small>${escapeHtml(entity.facultad || "No aplica / pendiente")}</div>
      <div><small>Nivel</small>${escapeHtml(entity.nivel || entity.kind)}</div>
      <div><small>Acto administrativo</small>${escapeHtml(entity.acto_administrativo || "Pendiente")}</div>
      <div><small>Autoridad</small>${escapeHtml(entity.acto_por || "Pendiente")}</div>
    </div>
    <span class="badge ${entity.status === "con-acto-sin-documento" ? "pending" : ""}">${escapeHtml(entity.status)}</span>
    <h3>Soporte documental</h3><div class="docs">${docs}</div>`;
  $("detailDialog").showModal();
}
function downloadICS() {
  const ev = filteredEvents().filter(e => e.month && e.day), now = new Date(), stamp = now.toISOString().replace(/[-:]/g,"").replace(/\.\d{3}Z$/,"Z");
  const lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Efemerides UNAL//ES","CALSCALE:GREGORIAN"];
  ev.forEach(e => {
    const mm = String(e.month).padStart(2,"0"), dd = String(e.day).padStart(2,"0");
    const start = `${CALENDAR_YEAR}${mm}${dd}`;
    const entity = entityById(e.entity_id) || {};
    const desc = [
      "Fecha anual de celebración",
      entity.creation_year ? `Creación: ${entity.creation_year}` : null,
      e.acto_administrativo,
      e.sede
    ].filter(Boolean).join(" | ").replace(/\n/g," ");
    lines.push("BEGIN:VEVENT",`UID:${e.id}@efemerides-unal`,`DTSTAMP:${stamp}`,`DTSTART;VALUE=DATE:${start}`,"RRULE:FREQ=YEARLY",`SUMMARY:${icsEscape(e.entity_name)}`,`DESCRIPTION:${icsEscape(desc)}`,"END:VEVENT");
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
  state.data = expandCompact(JSON.parse(chunks.join("")));
  fillFilters();
  $("searchInput").addEventListener("input", e => { state.filters.search = e.target.value.trim(); renderAll(); });
  $("sedeFilter").addEventListener("change", e => { state.filters.sede = e.target.value; renderAll(); });
  $("kindFilter").addEventListener("change", e => { state.filters.kind = e.target.value; renderAll(); });
  $("statusFilter").addEventListener("change", e => { state.filters.status = e.target.value; renderAll(); });
  $("prevMonth").addEventListener("click", () => { state.current = new Date(CALENDAR_YEAR, (state.current.getMonth() + 11) % 12, 1); renderAll(); });
  $("nextMonth").addEventListener("click", () => { state.current = new Date(CALENDAR_YEAR, (state.current.getMonth() + 1) % 12, 1); renderAll(); });
  $("downloadIcs").addEventListener("click", downloadICS);
  $("closeDialog").addEventListener("click", () => $("detailDialog").close());
  $("detailDialog").addEventListener("click", e => { if (e.target === $("detailDialog")) $("detailDialog").close(); });
  renderAll();
}
init();