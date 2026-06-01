// Leyte DEWS dashboard — vanilla JS SPA talking to the Django REST API.
'use strict';

const HAZARD_TYPES = ['flood', 'rainfall', 'river_level', 'landslide', 'storm_surge', 'seismic'];
const HAZARD_STATUS = ['normal', 'advisory', 'watch', 'warning', 'critical'];
const INCIDENT_TYPES = ['flooding', 'landslide', 'road_blockage', 'structural_damage', 'casualty', 'evacuation', 'power_outage', 'other'];
const INCIDENT_STATUS = ['reported', 'in_progress', 'resolved', 'closed'];
const MUNICIPALITIES = ['Tacloban City', 'Palo', 'Tanauan', 'Tolosa', 'Dulag', 'Abuyog', 'Baybay City', 'Ormoc City', 'Carigara', 'Barugo', 'Jaro', 'Pastrana', 'Alangalang', 'Santa Fe', 'Tabontabon', 'MacArthur'];

const state = { token: null, user: null, sensors: [], selected: new Set() };

// ---- DOM helpers ----------------------------------------------------------
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) node.append(c?.nodeType ? c : document.createTextNode(c ?? ''));
  return node;
}
const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString('en-PH', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—');
const titleCase = (s) => String(s).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

let toastTimer;
function toast(msg, kind = '') {
  const t = $('#toast');
  t.textContent = msg; t.className = `toast ${kind}`; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 3500);
}

// Flatten a DRF error object into a readable string.
function extractError(data, fallback) {
  if (!data || typeof data !== 'object') return fallback;
  if (data.error) return data.error;
  if (data.detail) return data.detail;
  const parts = [];
  for (const [k, v] of Object.entries(data)) {
    const msg = Array.isArray(v) ? v.join(' ') : typeof v === 'object' ? JSON.stringify(v) : v;
    parts.push(k === 'non_field_errors' ? msg : `${k}: ${msg}`);
  }
  return parts.join(' · ') || fallback;
}

// ---- API client -----------------------------------------------------------
async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(`/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (res.status === 401 && state.token) { logout(); throw new Error('Session expired. Please sign in again.'); }
  if (!res.ok) throw new Error(extractError(data, `Request failed (${res.status}).`));
  return data;
}
// DRF list endpoints are paginated; normalize to an array.
const listOf = (data) => (Array.isArray(data) ? data : data.results || []);

// ---- Auth -----------------------------------------------------------------
function saveSession() {
  localStorage.setItem('dews_token', state.token);
  localStorage.setItem('dews_user', JSON.stringify(state.user));
}
function logout() {
  state.token = null; state.user = null;
  localStorage.removeItem('dews_token'); localStorage.removeItem('dews_user');
  $('#app-view').hidden = true; $('#login-view').hidden = false;
}

$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('#login-btn'); const errEl = $('#login-error');
  errEl.hidden = true; btn.disabled = true; btn.textContent = 'Signing in…';
  try {
    const data = await api('/auth/login', { method: 'POST', body: {
      username: $('#login-username').value, password: $('#login-password').value } });
    state.token = data.token; state.user = data.user; saveSession();
    enterApp();
  } catch (err) { errEl.textContent = err.message; errEl.hidden = false; }
  finally { btn.disabled = false; btn.textContent = 'Sign in'; }
});
$('#logout-btn').addEventListener('click', logout);

// ---- Bootstrap ------------------------------------------------------------
function enterApp() {
  $('#login-view').hidden = true; $('#app-view').hidden = false;
  const u = state.user;
  $('#user-badge').innerHTML = `${u.name} <span class="role">${u.role}</span>`;
  $$('[data-role-gate]').forEach((n) => n.classList.toggle('role-hidden', !u.can_edit));
  populateSelects();
  refreshAll();
}

function populateSelects() {
  const opt = (v, label) => `<option value="${v}">${label || titleCase(v)}</option>`;
  $('#sensor-filter-muni').innerHTML = `<option value="">All municipalities</option>` + MUNICIPALITIES.map((m) => opt(m, m)).join('');
  $('#sensor-filter-hazard').innerHTML = `<option value="">All hazards</option>` + HAZARD_TYPES.map((h) => opt(h)).join('');
  $('#bulk-status').innerHTML = `<option value="">Set status to…</option>` + HAZARD_STATUS.map((s) => opt(s)).join('');
  $('#inc-type').innerHTML = INCIDENT_TYPES.map((t) => opt(t)).join('');
  $('#inc-muni').innerHTML = MUNICIPALITIES.map((m) => opt(m, m)).join('');
  $('#wn-hazard').innerHTML = HAZARD_TYPES.map((h) => opt(h)).join('');
  $('#wn-munis').innerHTML = MUNICIPALITIES.map((m) => opt(m, m)).join('');
}

// ---- Tabs -----------------------------------------------------------------
$$('.tab').forEach((tab) => tab.addEventListener('click', () => {
  $$('.tab').forEach((t) => t.classList.remove('active'));
  $$('.tab-panel').forEach((p) => p.classList.remove('active'));
  tab.classList.add('active');
  $(`#tab-${tab.dataset.tab}`).classList.add('active');
}));

// ---- Refresh --------------------------------------------------------------
async function refreshAll() {
  await Promise.all([loadSensors(), loadIncidents(), loadWarnings()]);
}

async function loadOverview() {
  try {
    const health = await api('/health');
    const grid = $('#stat-grid'); grid.innerHTML = '';
    const atWarning = state.sensors.filter((s) => ['warning', 'critical'].includes(s.status)).length;
    const stats = [
      { num: health.counts.sensors, lbl: 'Sensors monitored' },
      { num: health.counts.active_warnings, lbl: 'Active warnings', alert: health.counts.active_warnings > 0 },
      { num: health.counts.incidents, lbl: 'Incident reports' },
      { num: atWarning, lbl: 'Sensors at warning+', alert: atWarning > 0 },
    ];
    for (const s of stats) {
      grid.append(el('div', { class: `stat ${s.alert ? 'alert' : ''}` }, [
        el('div', { class: 'num' }, String(s.num)), el('div', { class: 'lbl' }, s.lbl)]));
    }
    const byMuni = {};
    for (const s of state.sensors) {
      const cur = byMuni[s.municipality] || 'normal';
      byMuni[s.municipality] = HAZARD_STATUS.indexOf(s.status) > HAZARD_STATUS.indexOf(cur) ? s.status : cur;
    }
    const wrap = $('#muni-status'); wrap.innerHTML = '';
    Object.entries(byMuni).sort((a, b) => HAZARD_STATUS.indexOf(b[1]) - HAZARD_STATUS.indexOf(a[1]))
      .forEach(([m, st]) => wrap.append(el('div', { class: 'muni-chip' }, [
        el('span', {}, m), el('span', { class: `badge ${st}` }, titleCase(st))])));
  } catch (err) { toast(err.message, 'err'); }
}

// ---- Sensors --------------------------------------------------------------
async function loadSensors() {
  try {
    const params = new URLSearchParams();
    const m = $('#sensor-filter-muni').value; const h = $('#sensor-filter-hazard').value;
    if (m) params.set('municipality', m);
    if (h) params.set('hazard_type', h);
    const data = await api(`/sensors/?${params}`);
    state.sensors = listOf(data).sort((a, b) => HAZARD_STATUS.indexOf(b.status) - HAZARD_STATUS.indexOf(a.status));
    renderSensors();
    loadOverview();
  } catch (err) { toast(err.message, 'err'); }
}

function renderSensors() {
  const tbody = $('#sensor-rows'); tbody.innerHTML = '';
  const canEdit = state.user.can_edit;
  for (const s of state.sensors) {
    const reading = s.last_reading ? `${s.last_reading.value} ${s.last_reading.unit}` : '—';
    const checkbox = el('input', { type: 'checkbox' });
    checkbox.checked = state.selected.has(s.id); checkbox.disabled = !canEdit;
    checkbox.addEventListener('change', () => {
      checkbox.checked ? state.selected.add(s.id) : state.selected.delete(s.id);
      updateBulkBar();
    });
    const checkCell = el('td', { class: 'check-col' }); checkCell.append(checkbox);
    tbody.append(el('tr', {}, [
      checkCell,
      el('td', {}, [el('strong', {}, s.name), el('div', { class: 'muted', html: `<small>${s.barangay || ''}</small>` })]),
      el('td', {}, titleCase(s.hazard_type)),
      el('td', {}, s.municipality),
      el('td', {}, reading),
      el('td', {}, el('span', { class: `badge ${s.status}` }, titleCase(s.status))),
      el('td', { class: 'muted' }, fmtTime(s.updated_at)),
    ]));
  }
  updateBulkBar();
}

$('#sensor-check-all').addEventListener('change', (e) => {
  if (!state.user.can_edit) return;
  state.selected.clear();
  if (e.target.checked) state.sensors.forEach((s) => state.selected.add(s.id));
  renderSensors();
});
function updateBulkBar() {
  $('#bulk-selected').textContent = String(state.selected.size);
  $('#bulk-apply').disabled = state.selected.size === 0 || !$('#bulk-status').value;
}
$('#bulk-status').addEventListener('change', updateBulkBar);
$('#sensor-refresh').addEventListener('click', loadSensors);
$('#sensor-filter-muni').addEventListener('change', () => { state.selected.clear(); loadSensors(); });
$('#sensor-filter-hazard').addEventListener('change', () => { state.selected.clear(); loadSensors(); });

$('#bulk-apply').addEventListener('click', async () => {
  const status = $('#bulk-status').value;
  if (!status || state.selected.size === 0) return;
  try {
    const r = await api('/sensors/bulk-status/', { method: 'PATCH', body: { status, sensor_ids: [...state.selected] } });
    toast(`Updated ${r.updated} of ${r.matched} sensor(s) to "${status}".`, 'ok');
    state.selected.clear(); loadSensors();
  } catch (err) { toast(err.message, 'err'); }
});

$('#bulk-apply-filter').addEventListener('click', async () => {
  const status = $('#bulk-status').value;
  if (!status) return toast('Choose a status first.', 'err');
  const municipality = $('#sensor-filter-muni').value || undefined;
  const hazard_type = $('#sensor-filter-hazard').value || undefined;
  if (!municipality && !hazard_type) return toast('Set a municipality or hazard filter to bulk-apply.', 'err');
  if (!confirm(`Set ALL sensors matching the current filter to "${status}"?`)) return;
  try {
    const r = await api('/sensors/bulk-status/', { method: 'PATCH', body: { status, municipality, hazard_type } });
    toast(`Updated ${r.updated} of ${r.matched} sensor(s) to "${status}".`, 'ok');
    loadSensors();
  } catch (err) { toast(err.message, 'err'); }
});

// ---- Incidents ------------------------------------------------------------
async function loadIncidents() {
  try {
    const data = await api('/incidents/');
    const incidents = listOf(data);
    const tbody = $('#incident-rows'); tbody.innerHTML = '';
    for (const i of incidents) {
      tbody.append(el('tr', {}, [
        el('td', {}, titleCase(i.type)),
        el('td', {}, [el('div', {}, i.municipality), el('small', { class: 'muted' }, i.barangay || '')]),
        el('td', {}, el('span', { class: `sev-${i.severity}` }, titleCase(i.severity))),
        el('td', {}, renderIncidentStatus(i)),
        el('td', { class: 'muted' }, fmtTime(i.reported_at)),
      ]));
    }
    if (!incidents.length) tbody.append(el('tr', {}, el('td', { colspan: '5', class: 'muted' }, 'No incidents logged.')));
  } catch (err) { toast(err.message, 'err'); }
}

function renderIncidentStatus(i) {
  if (!state.user.can_edit) return titleCase(i.status);
  const sel = el('select');
  INCIDENT_STATUS.forEach((s) => {
    const o = el('option', { value: s }, titleCase(s));
    if (s === i.status) o.selected = true;
    sel.append(o);
  });
  sel.addEventListener('change', async () => {
    try { await api(`/incidents/${i.id}/`, { method: 'PATCH', body: { status: sel.value } }); toast('Incident updated.', 'ok'); }
    catch (err) { toast(err.message, 'err'); loadIncidents(); }
  });
  return sel;
}

$('#incident-refresh').addEventListener('click', loadIncidents);
$('#incident-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = $('#inc-msg');
  try {
    await api('/incidents/', { method: 'POST', body: {
      type: $('#inc-type').value, municipality: $('#inc-muni').value, barangay: $('#inc-brgy').value,
      severity: $('#inc-severity').value, summary: $('#inc-summary').value,
      public_summary: $('#inc-public').value, reporter_name: $('#inc-reporter').value, reporter_contact: $('#inc-contact').value,
    } });
    e.target.reset();
    msg.textContent = 'Incident logged.'; msg.className = 'form-msg ok'; msg.hidden = false;
    loadIncidents();
  } catch (err) { msg.textContent = err.message; msg.className = 'form-msg err'; msg.hidden = false; }
});

// ---- Warnings -------------------------------------------------------------
async function loadWarnings() {
  try {
    const data = await api('/warnings/');
    const warnings = listOf(data);
    const list = $('#warning-list'); list.innerHTML = '';
    for (const w of warnings) {
      const actions = [];
      if (state.user.can_edit && w.active) actions.push(el('button', { class: 'ghost', onclick: () => cancelWarning(w.id) }, 'Cancel'));
      list.append(el('div', { class: `warning-item ${w.level} ${w.active ? '' : 'inactive'}` }, [
        el('h3', {}, w.title),
        el('p', { class: 'muted', style: 'margin:0' }, w.message),
        el('div', { class: 'meta' }, [
          el('span', { class: `lvl ${w.level}` }, w.level),
          el('span', {}, titleCase(w.hazard_type)),
          el('span', {}, (w.municipalities || []).join(', ')),
          el('span', {}, `Issued ${fmtTime(w.issued_at)}`),
          el('span', {}, w.active ? 'ACTIVE' : 'CANCELLED'),
          ...actions,
        ]),
      ]));
    }
    if (!warnings.length) list.append(el('p', { class: 'muted' }, 'No warnings issued.'));
  } catch (err) { toast(err.message, 'err'); }
}

async function cancelWarning(id) {
  if (!confirm('Cancel this early warning? It will be removed from the public feed.')) return;
  try { await api(`/warnings/${id}/cancel/`, { method: 'POST' }); toast('Warning cancelled.', 'ok'); loadWarnings(); }
  catch (err) { toast(err.message, 'err'); }
}

$('#warning-refresh').addEventListener('click', loadWarnings);
$('#warning-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = $('#wn-msg');
  const munis = Array.from($('#wn-munis').selectedOptions).map((o) => o.value);
  try {
    await api('/warnings/', { method: 'POST', body: {
      title: $('#wn-title').value, level: $('#wn-level').value, hazard_type: $('#wn-hazard').value,
      message: $('#wn-message').value, municipalities: munis,
    } });
    e.target.reset();
    msg.textContent = 'Warning broadcast.'; msg.className = 'form-msg ok'; msg.hidden = false;
    loadWarnings();
  } catch (err) { msg.textContent = err.message; msg.className = 'form-msg err'; msg.hidden = false; }
});

// ---- Restore session ------------------------------------------------------
(function restore() {
  const token = localStorage.getItem('dews_token');
  const user = localStorage.getItem('dews_user');
  if (token && user) { state.token = token; state.user = JSON.parse(user); enterApp(); }
})();
