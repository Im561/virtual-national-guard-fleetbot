if (!globalThis.L) {
  const mapHost = document.getElementById('map');
  if (mapHost) mapHost.innerHTML = '<div class="map-library-error"><strong>MAP ENGINE UNAVAILABLE</strong><span>Leaflet could not be loaded. Refresh the page or check network access to the map library.</span></div>';
  const systemHealth = document.getElementById('system-health');
  if (systemHealth) {
    systemHealth.textContent = 'MAP ENGINE FAILED TO LOAD';
    systemHealth.classList.add('error-text');
  }
  const link = document.getElementById('connection-status');
  if (link) link.textContent = 'MAP LIBRARY OFFLINE';
} else {
const CLIENT_BUILD = document.documentElement.dataset.build || 'unknown';

const state = {
  data: null,
  rawData: null,
  revision: -1,
  selectedCallsign: null,
  selectedOperationId: null,
  bases: [],
  filter: 'all',
  operationalRegionFilter: 'all',
  basemap: 'dark-satellite',
  atcCoverageData: [],
  centerBoundaryData: [],
  suaData: [],
  showAtcCoverage: true,
  showSua: true,
  showDcaHeliRoutes: false,
  iconMode: 'scope',
  compactScope: true,
  iconDensity: 'micro',
  atcRevision: null,
  centerBoundaryRevision: null,
  centerBoundaryLoading: false,
  atcLoading: false,
  suaVersion: null,
  localAcknowledged: new Set(),
  activeScrambleId: null,
  audioContext: null,
  alarmTimer: null,
  alarmMaster: null,
  alarmAudio: null,
  audioArmed: false,
  soundEnabled: true,
  popupEnabled: true,
  alertVolume: 0.70,
  mapControlsExpanded: true,
  ws: null,
  wsOpen: false,
  wsRetryMs: 1500,
  wsHeartbeat: null,
  lastMessageAt: 0,
  renderFrame: null,
  consoleId: null,
  consoleLabel: null,
  alertsRenderKey: null,
  interceptRenderKey: null,
  interceptWorkspaceRenderKey: null,
  previewRenderKey: null,
  railWidth: 390,
  httpFallbackSeconds: 15,
  staleWarningSeconds: 45,
  staleCriticalSeconds: 90,
  httpFallbackTimer: null,
  staleWatchdogTimer: null,
  dataStale: false,
  legendExpanded: true,
  liveLoading: false,
  suaLoading: false,
  suaRefreshTimer: null,
  consolePresenceHeartbeatSeconds: 30,
  consolePresenceHeartbeatTimer: null,
  viewerCount: null,
  interceptConsoleOpen: false,
  interceptPreviousFocus: null,
  scrambleModalOpen: false,
  scramblePreviousFocus: null,
  preScrambleBusy: new Set(),
  preScrambleTimer: null,
  workspaceTab: 'map',
  activeInterceptKey: null,
  atcSelectedCallsign: null,
  operatorAircraftCallsign: null,
  atcRenderKey: null,
  interceptTargetCallsign: null,
  multiInterceptorSelection: new Set(),
  interceptorCandidateFilter: '',
  interceptNoteDrafts: new Map(),
  interceptRecalcBusy: false,
  atcMapRenderKey: null,
  atcMapFitKey: null,
  interceptMapAutoFit: true,
  interceptMapRenderKey: null,
  interceptMapLastBoundsKey: null,
  artccFocusId: '',
  trackDetailCache: new Map(),
  trackDetailRequests: new Map(),
};

const DETAIL_ONLY_PILOT_FIELDS = [
  'context', 'observations', 'reasons', 'controller_candidates',
  'active_artcc_frequencies', 'center_frequencies', 'advisory_frequency_matches',
  'online_center_handoff_detail', 'early_unicom_handoff_detail',
  'assigned_squawk', 'reported_frequencies', 'atc_capable_reported_frequencies',
  'route', 'remarks', 'departure', 'arrival', 'flight_rules', 'controller_facility',
];

const aircraftLayers = new Map();
const aircraftTrackHistory = new Map();
const serverTrackHistory = new Map();
const trackHistoryRequests = new Map();
let flightPlanPreviewLayerGroup = null;
let centerBoundaryLayerGroup = null;
let atcLayerGroup = null;
let atcLabelMarkers = [];
let atcLabelLayoutFrame = null;
let suaLayerGroup = null;
let dcaHeliRouteLayerGroup = null;
let zoneLayerGroup = null;
let interceptLayerGroup = null;
let atcOpsMap = null;
let atcOpsLayerGroup = null;
let interceptMap = null;
let interceptMapLayerGroup = null;
let interceptMapBasemap = null;
let scopeGridLayerGroup = null;
const baseLayers = [];

const el = id => document.getElementById(id);
const MODAL_FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function modalFocusableElements(modal) {
  if (!modal) return [];
  return [...modal.querySelectorAll(MODAL_FOCUSABLE)].filter(item => {
    const style = globalThis.getComputedStyle ? getComputedStyle(item) : null;
    return !item.hidden && style?.visibility !== 'hidden' && style?.display !== 'none';
  });
}

function trapModalFocus(event, modal) {
  if (event.key !== 'Tab' || !modal || modal.hidden) return;
  const focusable = modalFocusableElements(modal);
  if (!focusable.length) {
    event.preventDefault();
    modal.focus?.();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && (document.activeElement === first || !modal.contains(document.activeElement))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || !modal.contains(document.activeElement))) {
    event.preventDefault();
    first.focus();
  }
}

function restoreStoredFocus(stateKey) {
  const target = state[stateKey];
  state[stateKey] = null;
  if (target?.isConnected && !target.disabled) setTimeout(() => target.focus(), 0);
}
const severityColor = {
  green: '#71f6ff',
  yellow: '#ffe36d',
  orange: '#ffab52',
  red: '#ff5252',
};
const severityLabel = {
  green: 'NORMAL',
  yellow: 'MONITOR',
  orange: 'INVESTIGATE',
  red: 'SCRAMBLE RECOMMENDED',
};

// DCA/NCR visual reference overlay. The current FAA chart and ATC instructions
// remain controlling; these public-landmark lines are intentionally not used
// for navigation, separation, authorization, or automatic detection.
const DCA_HELI_CHART_URL = 'https://aeronav.faa.gov/visual/07-09-2026/PDFs/Balt-Wash_Heli.pdf';
const BLACKJACK_KDCA = [38.8512, -77.0402];
const DCA_HELI_ROUTES = [
  {
    id: 'route-1', name: 'WASHINGTON ROUTE 1', status: 'PRIORITY AIRCRAFT / ATC AUTHORIZATION NEAR DCA', color: '#71f6ff',
    points: [[38.9450,-77.1195],[38.9295,-77.1145],[38.9027,-77.0708],[38.8874,-77.0554],[38.8768,-77.0412],[38.8590,-77.0230],[38.8705,-76.9950],[38.9010,-76.9740]],
  },
  {
    id: 'route-5', name: 'WASHINGTON ROUTE 5', status: 'PRIORITY AIRCRAFT / ATC AUTHORIZATION', color: '#c79cff',
    points: [[38.7935,-77.1770],[38.8115,-77.1480],[38.8290,-77.1160],[38.8460,-77.0935],[38.8615,-77.0730],[38.8719,-77.0563]],
  },
  {
    id: 'broad-creek', name: 'BROAD CREEK TRANSITION', status: 'CURRENT SOUTH-OF-DCA TRANSITION · VERIFY FAA CHART', color: '#6ee7a0',
    points: [[38.7500,-76.9480],[38.7660,-76.9790],[38.7820,-77.0060],[38.7938,-77.0384],[38.8250,-77.0250],[38.8480,-77.0180]],
  },
  {
    id: 'route-4-closed', name: 'ROUTE 4 · CLOSED SEGMENT', status: 'PERMANENTLY CLOSED · HAINS POINT TO WILSON BRIDGE', color: '#ff5252', closed: true,
    points: [[38.8590,-77.0230],[38.8420,-77.0310],[38.8230,-77.0380],[38.7938,-77.0384]],
  },
];


const ARTCC_DISPLAY_ALIASES = {
  PAZA: 'ZAN', PHZH: 'ZHN', PGZU: 'ZUA', TJZS: 'ZSU',
  CZYZ: 'CZYZ', CZUL: 'CZUL', CZVR: 'CZVR', CZEG: 'CZEG',
  CZWG: 'CZWG', CZQM: 'CZQM', CZQX: 'CZQX', CZQO: 'CZQO', CZZV: 'CZZV',
};

function artccDisplayCode(value) {
  const id = String(value?.id || value || '').toUpperCase();
  if (!id) return 'ARTCC';
  if (ARTCC_DISPLAY_ALIASES[id]) return ARTCC_DISPLAY_ALIASES[id];
  return id.startsWith('KZ') ? id.slice(1) : id;
}

function focusedArtccBoundary() {
  if (!state.artccFocusId) return null;
  return (state.centerBoundaryData || []).find(item => String(item.id || '').toUpperCase() === state.artccFocusId) || null;
}

function pointOnGeoSegment(x, y, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSquared = dx ** 2 + dy ** 2;
  // GeoJSON rings normally repeat their first coordinate at the end. Treat
  // that zero-length closing segment as a point, not as a segment containing
  // every coordinate in the world.
  if (lengthSquared <= Number.EPSILON) {
    return Math.abs(x - x1) <= 1e-9 && Math.abs(y - y1) <= 1e-9;
  }
  const cross = (y - y1) * dx - (x - x1) * dy;
  if (Math.abs(cross) > 1e-9) return false;
  const dot = (x - x1) * dx + (y - y1) * dy;
  if (dot < 0) return false;
  return dot <= lengthSquared;
}

function pointInGeoRing(lat, lon, ring) {
  if (!Array.isArray(ring) || ring.length < 3) return false;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i] || [];
    const b = ring[j] || [];
    const xi = Number(a[0]);
    const yi = Number(a[1]);
    const xj = Number(b[0]);
    const yj = Number(b[1]);
    if (![xi, yi, xj, yj].every(Number.isFinite)) continue;
    if (pointOnGeoSegment(lon, lat, xi, yi, xj, yj)) return true;
    const intersects = ((yi > lat) !== (yj > lat))
      && (lon < (xj - xi) * (lat - yi) / ((yj - yi) || Number.EPSILON) + xi);
    if (intersects) inside = !inside;
  }
  return inside;
}

function pointInGeoPolygon(lat, lon, polygon) {
  if (!Array.isArray(polygon) || !polygon.length || !pointInGeoRing(lat, lon, polygon[0])) return false;
  return !polygon.slice(1).some(hole => pointInGeoRing(lat, lon, hole));
}

function pointInGeoJsonGeometry(latValue, lonValue, geometry) {
  const lat = Number(latValue);
  const lon = Number(lonValue);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || !geometry) return false;
  if (geometry.type === 'Polygon') return pointInGeoPolygon(lat, lon, geometry.coordinates);
  if (geometry.type === 'MultiPolygon') return (geometry.coordinates || []).some(polygon => pointInGeoPolygon(lat, lon, polygon));
  if (geometry.type === 'GeometryCollection') return (geometry.geometries || []).some(item => pointInGeoJsonGeometry(lat, lon, item));
  return false;
}

function pilotArtccMembership(pilot, boundary = focusedArtccBoundary()) {
  if (!boundary?.geometry || !pilot) return { inside: false, inbound: false, relevant: false };
  if (globalThis.VngArtccCache) {
    return globalThis.VngArtccCache.membership(pilot, boundary, `${state.revision}|${state.centerBoundaryRevision || ''}`, pointInGeoJsonGeometry);
  }
  const inside = pointInGeoJsonGeometry(pilot.lat, pilot.lon, boundary.geometry);
  const inbound = !inside && !pilot.on_ground && pointInGeoJsonGeometry(pilot.arrival_lat, pilot.arrival_lon, boundary.geometry);
  return { inside, inbound, relevant: inside || inbound };
}

function pilotBaseRelevantToArtcc(pilot, boundary = focusedArtccBoundary()) {
  return pilotArtccMembership(pilot, boundary).relevant;
}

function collectFocusedArtccCallsigns(raw, boundary = focusedArtccBoundary()) {
  const relevant = new Set((raw?.pilots || []).filter(pilot => pilotBaseRelevantToArtcc(pilot, boundary)).map(pilot => pilot.callsign));
  const links = [];
  for (const assignment of raw?.manual_intercepts || []) {
    links.push([assignment.interceptor_callsign, assignment.target_callsign]);
  }
  for (const pilot of raw?.pilots || []) {
    if (pilot.intercept_assignment?.target_callsign) links.push([pilot.callsign, pilot.intercept_assignment.target_callsign]);
    for (const interceptor of pilot.active_interceptors || []) links.push([interceptor.callsign, pilot.callsign]);
  }
  let changed = true;
  while (changed) {
    changed = false;
    for (const [one, two] of links) {
      if (!one || !two) continue;
      if (relevant.has(one) && !relevant.has(two)) { relevant.add(two); changed = true; }
      if (relevant.has(two) && !relevant.has(one)) { relevant.add(one); changed = true; }
    }
  }
  return relevant;
}

function atcCoverageRelevantToArtcc(item, boundary = focusedArtccBoundary()) {
  if (!state.artccFocusId || !boundary) return true;
  const ids = [item?.parent_boundary_id, item?.boundary_id].filter(Boolean).map(value => String(value).toUpperCase());
  if (ids.some(value => value === state.artccFocusId || value.startsWith(`${state.artccFocusId}-`))) return true;
  return pointInGeoJsonGeometry(item?.lat, item?.lon, boundary.geometry);
}

function buildFocusedDashboardData(raw) {
  const boundary = focusedArtccBoundary();
  if (!raw || !state.artccFocusId || !boundary?.geometry) return raw;
  const callsigns = collectFocusedArtccCallsigns(raw, boundary);
  const pilots = (raw.pilots || []).filter(item => callsigns.has(item.callsign));
  const alerts = (raw.alerts || []).filter(item => callsigns.has(item.callsign));
  const operations = (raw.operations || []).filter(item => callsigns.has(item.callsign));
  const manualIntercepts = (raw.manual_intercepts || []).filter(item => callsigns.has(item.interceptor_callsign) || callsigns.has(item.target_callsign));
  const interceptControls = (raw.intercept_controls || []).filter(item => callsigns.has(item.target_callsign));
  const relevantCoverage = (state.atcCoverageData || []).filter(item => atcCoverageRelevantToArtcc(item, boundary));
  const controllerCallsigns = new Set(relevantCoverage.map(item => item.callsign));
  const controllers = (raw.controllers || []).filter(item => controllerCallsigns.has(item.callsign) || pointInGeoJsonGeometry(item.lat, item.lon, boundary.geometry));
  const memberships = pilots.map(item => pilotArtccMembership(item, boundary));
  const inside = memberships.filter(item => item.inside).length;
  const inbound = memberships.filter(item => item.inbound).length;
  const stats = {
    ...(raw.stats || {}),
    monitored_aircraft: pilots.length,
    us_aircraft: pilots.filter(item => item.region === 'UNITED STATES').length,
    canada_aircraft: pilots.filter(item => item.region === 'CANADA').length,
    france_aircraft: pilots.filter(item => item.region === 'FRANCE').length,
    centers_online: controllers.filter(item => item.facility === 'CTR').length,
    terminal_online: controllers.filter(item => ['APP','DEP','TWR','GND','DEL'].includes(item.facility)).length,
    alerts: alerts.length,
    red_alerts: alerts.filter(item => item.severity === 'red').length,
    mandatory_ack: alerts.filter(item => item.requires_ack).length,
    nordo_watches: pilots.filter(item => item.nordo_watch).length,
    frequency_mismatches: pilots.filter(item => item.frequency_mismatch_active).length,
    vsoa_tracks: pilots.filter(item => item.vsoa).length,
    active_intercepts: pilots.filter(item => item.active_intercept).length,
    manual_intercepts: manualIntercepts.length,
    intercept_targets: new Set(manualIntercepts.map(item => item.target_callsign).filter(Boolean)).size,
    operations: operations.length,
  };
  return {
    ...raw,
    pilots,
    alerts,
    operations,
    manual_intercepts: manualIntercepts,
    intercept_controls: interceptControls,
    controllers,
    stats,
    center_boundary_count: 1,
    _artcc_focus: {
      id: boundary.id,
      code: artccDisplayCode(boundary),
      name: boundary.name || boundary.id,
      country: boundary.country || '',
      inside,
      inbound,
      related: Math.max(0, pilots.length - inside - inbound),
      total: pilots.length,
    },
  };
}

function loadArtccFocusPreference() {
  try { state.artccFocusId = String(localStorage.getItem('vng-adoc.artcc-focus') || '').toUpperCase(); }
  catch (_) { state.artccFocusId = ''; }
}

function updateArtccFocusControls() {
  const selector = el('artcc-focus-select');
  if (selector && selector.value !== state.artccFocusId) selector.value = state.artccFocusId;
  const clear = el('clear-artcc-focus');
  if (clear) { clear.disabled = !state.artccFocusId; clear.hidden = !state.artccFocusId; }
  const status = el('artcc-focus-status');
  const focus = state.data?._artcc_focus;
  if (status) {
    status.classList.toggle('active', Boolean(state.artccFocusId));
    status.textContent = focus
      ? `${focus.code} · ${focus.inside} INSIDE · ${focus.inbound} INBOUND${focus.related ? ` · ${focus.related} RELATED` : ''}`
      : state.artccFocusId
        ? `${artccDisplayCode(state.artccFocusId)} · LOADING OUTLINE`
        : 'NATIONAL VIEW';
  }
  document.querySelector('.map-panel')?.classList.toggle('artcc-focused', Boolean(state.artccFocusId));
}

function populateArtccFocusSelector() {
  const selector = el('artcc-focus-select');
  if (!selector) return;
  const boundaries = [...(state.centerBoundaryData || [])].sort((a, b) => {
    const country = String(a.country || '').localeCompare(String(b.country || ''));
    return country || String(a.name || a.id).localeCompare(String(b.name || b.id));
  });
  selector.replaceChildren(new Option('ALL ARTCCS / FIRS', ''));
  for (const country of ['UNITED STATES', 'CANADA']) {
    const groupItems = boundaries.filter(item => item.country === country);
    if (!groupItems.length) continue;
    const group = document.createElement('optgroup');
    group.label = country;
    for (const boundary of groupItems) {
      group.append(new Option(`${artccDisplayCode(boundary)} · ${boundary.name || boundary.id}`, String(boundary.id || '').toUpperCase()));
    }
    selector.append(group);
  }
  const valid = !state.artccFocusId || boundaries.some(item => String(item.id || '').toUpperCase() === state.artccFocusId);
  if (!valid) {
    state.artccFocusId = '';
    try { localStorage.removeItem('vng-adoc.artcc-focus'); } catch (_) { /* unavailable */ }
  }
  selector.value = state.artccFocusId;
  updateArtccFocusControls();
}

function fitMapToFocusedArtcc() {
  const boundary = focusedArtccBoundary();
  if (!boundary?.geometry) return;
  const layer = L.geoJSON({ type: 'Feature', properties: {}, geometry: boundary.geometry });
  const bounds = layer.getBounds();
  if (bounds?.isValid()) map.fitBounds(bounds, { padding: [24, 24], animate: false, maxZoom: 7 });
}

function setArtccFocus(value, fit = true) {
  state.artccFocusId = String(value || '').toUpperCase();
  try {
    if (state.artccFocusId) localStorage.setItem('vng-adoc.artcc-focus', state.artccFocusId);
    else localStorage.removeItem('vng-adoc.artcc-focus');
  } catch (_) { /* unavailable */ }
  if (state.rawData) applyData(state.rawData);
  renderCenterBoundaries(state.centerBoundaryData, state.centerBoundaryRevision, true);
  renderAtcCoverage(state.atcCoverageData, state.atcRevision, true);
  updateArtccFocusControls();
  if (fit && state.artccFocusId) fitMapToFocusedArtcc();
}

function interceptTrackLabel(pilot) {
  if (!pilot?.active_intercept) return '';
  return pilot.manual_intercept ? 'MANUAL INTERCEPT' : 'INTERCEPT · SQ 7777';
}

function formatInterceptEta(assignment) {
  const minutes = Number(assignment?.estimated_intercept_minutes);
  if (!Number.isFinite(minutes)) return assignment?.live === false ? 'TRACK LOST' : 'NO SOLUTION';
  if (minutes < 1) return '<1 MIN';
  return `${minutes.toFixed(minutes < 10 ? 1 : 0)} MIN`;
}

function formatClosure(assignment) {
  const rate = Number(assignment?.signed_closure_rate_kt);
  if (!Number.isFinite(rate)) return '—';
  if (Math.abs(rate) < 10) return 'STEADY';
  return `${Math.abs(Math.round(rate))} KT ${rate > 0 ? 'CLOSING' : 'OPENING'}`;
}

function formatZuluTimestamp(value) {
  const parsed = Date.parse(value || '');
  return Number.isFinite(parsed) ? new Date(parsed).toISOString().slice(11, 19) + 'Z' : '—';
}

function latestInterceptCalculationTime(assignments = activeInterceptAssignments()) {
  const values = assignments
    .map(item => Date.parse(item.calculated_at || item.updated_at || state.data?.updated_at || ''))
    .filter(Number.isFinite);
  return values.length ? Math.max(...values) : NaN;
}

function updateInterceptRecalcStatus() {
  const stateLabel = el('intercept-recalc-state');
  const detail = el('intercept-recalc-detail');
  const button = el('intercepts-recalculate-now');
  if (!stateLabel || !detail) return;
  const assignments = activeInterceptAssignments();
  const latest = latestInterceptCalculationTime(assignments);
  const ageSeconds = Number.isFinite(latest) ? Math.max(0, Math.floor((Date.now() - latest) / 1000)) : null;
  const stale = Boolean(state.dataStale || (ageSeconds !== null && ageSeconds >= state.staleCriticalSeconds));
  stateLabel.textContent = state.interceptRecalcBusy
    ? 'RECALCULATING…'
    : !assignments.length
      ? 'STANDBY'
      : stale
        ? 'CALCULATIONS STALE'
        : 'LIVE RECALC ACTIVE';
  stateLabel.classList.toggle('stale', stale);
  detail.textContent = !assignments.length
    ? `FEED #${state.data?.feed_sequence ?? 0} · NO ACTIVE INTERCEPT SOLUTIONS`
    : `${formatZuluTimestamp(Number.isFinite(latest) ? new Date(latest).toISOString() : null)} · ${ageSeconds ?? '—'}s AGO · FEED #${state.data?.feed_sequence ?? 0} · ${assignments.length} SOLUTION${assignments.length === 1 ? '' : 'S'}`;
  if (button) {
    button.disabled = state.interceptRecalcBusy || !state.data;
    button.textContent = state.interceptRecalcBusy ? 'RECALCULATING…' : 'RECALCULATE NOW';
  }
}

function distanceNmBetween(a, b) {
  if (!a || !b) return Infinity;
  const toRad = value => Number(value) * Math.PI / 180;
  const lat1 = toRad(a.lat), lat2 = toRad(b.lat);
  const dLat = lat2 - lat1;
  const dLon = toRad(b.lon) - toRad(a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 3440.065 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)));
}



// Compatibility aliases for the unified single-ARTCC focus implementation.
function normaliseArtccId(value) {
  return String(value || '').trim().toUpperCase();
}

function selectedArtccBoundary() {
  return focusedArtccBoundary();
}

function pilotArtccRole(pilot, boundary = focusedArtccBoundary()) {
  if (!state.artccFocusId || !boundary?.geometry || !pilot) return state.artccFocusId ? null : 'national';
  const membership = pilotArtccMembership(pilot, boundary);
  if (membership.inside) return 'inside';
  if (membership.inbound) return 'inbound';
  return null;
}

function focusedPilotCallsigns(pilots = state.rawData?.pilots || state.data?.pilots || []) {
  if (!state.artccFocusId) return null;
  const boundary = focusedArtccBoundary();
  return boundary?.geometry ? collectFocusedArtccCallsigns({ ...(state.rawData || state.data || {}), pilots }, boundary) : null;
}

function focusedPilots(pilots = state.data?.pilots || []) {
  const callsigns = focusedPilotCallsigns(pilots);
  return callsigns ? pilots.filter(pilot => callsigns.has(pilot.callsign)) : pilots;
}

function focusedAlerts(alerts = state.data?.alerts || []) {
  const callsigns = focusedPilotCallsigns();
  return callsigns ? alerts.filter(alert => callsigns.has(alert.callsign)) : alerts;
}

function artccCoverageMatches(item) {
  return atcCoverageRelevantToArtcc(item);
}

function artccDisplayId(boundary = focusedArtccBoundary()) {
  return artccDisplayCode(boundary || state.artccFocusId);
}

function populateArtccFocusOptions() {
  populateArtccFocusSelector();
}

function updateArtccFocusUi() {
  updateArtccFocusControls();
}

function fitSelectedArtcc() {
  fitMapToFocusedArtcc();
}

function applyArtccFocus(value, fit = true) {
  setArtccFocus(value, fit);
}

function setWorkspaceTab(tab) {
  const next = ['map', 'intercept', 'atc'].includes(tab) ? tab : 'map';
  state.workspaceTab = next;
  const situation = el('situation-workspace');
  const intercept = el('intercept-workspace');
  const atc = el('atc-workspace');
  if (situation) situation.hidden = next !== 'map';
  if (intercept) intercept.hidden = next !== 'intercept';
  if (atc) atc.hidden = next !== 'atc';
  document.querySelectorAll('[data-workspace-tab]').forEach(button => {
    const active = button.dataset.workspaceTab === next;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
  const force = globalThis.VngRenderScheduler?.consume(next) ?? true;
  if (next === 'map') {
    if (state.data) {
      renderAircraft(state.data.pilots || [], force);
      renderAlerts(state.data.alerts || [], force);
      renderInterceptOverlay(force);
      if (state.selectedCallsign) renderFlightPlanPreview(state.selectedCallsign);
    }
    setTimeout(() => map.invalidateSize(false), 0);
  }
  else if (next === 'intercept') {
    renderInterceptConsole();
    renderActiveInterceptWorkspace(force);
    setTimeout(() => {
      ensureInterceptMap();
      interceptMap?.invalidateSize(false);
      renderInterceptTacticalMap(force);
    }, 0);
  }
  else {
    renderAtcWorkspace(force);
    setTimeout(() => {
      const atcMap = ensureAtcOpsMap();
      if (atcMap) {
        atcMap.invalidateSize(false);
        renderAtcOpsMap(force);
      }
    }, 0);
  }
}

function activeInterceptAssignments() {
  const assignments = (state.data?.manual_intercepts || []).map(item => ({ ...item, key: `manual:${item.interceptor_callsign}`, manual: true }));
  const manualInterceptors = new Set(assignments.map(item => item.interceptor_callsign));
  for (const pilot of state.data?.pilots || []) {
    if (!pilot.active_intercept || !pilot.intercept_assignment || manualInterceptors.has(pilot.callsign)) continue;
    assignments.push({
      ...pilot.intercept_assignment,
      key: `auto:${pilot.callsign}`,
      manual: false,
      live: true,
      calculated_at: pilot.intercept_assignment.calculated_at || state.data?.updated_at,
      interceptor_callsign: pilot.callsign,
      target_callsign: pilot.intercept_assignment.target_callsign,
      interceptor: pilot,
      target: pilotForCallsign(pilot.intercept_assignment.target_callsign),
      target_response_status: operationForCallsign(pilot.intercept_assignment.target_callsign)?.target_response_status || 'UNKNOWN',
    });
  }
  return assignments;
}

function operationForCallsign(callsign) {
  return (state.data?.operations || []).find(item => item.callsign === callsign && item.active)
    || (state.data?.operations || []).find(item => item.callsign === callsign)
    || null;
}

function contactStatusLabel(status) {
  const labels = {
    UNKNOWN: 'STATUS UNKNOWN',
    RESPONDING: 'RESPONDING',
    NOT_RESPONDING: 'NOT RESPONDING',
    COMMS_RESTORED: 'COMMS RESTORED',
  };
  return labels[String(status || 'UNKNOWN').toUpperCase()] || 'STATUS UNKNOWN';
}

function interceptResponseControlsHtml(assignment) {
  const current = String(assignment?.target_response_status || 'UNKNOWN').toUpperCase();
  const operation = operationForCallsign(assignment?.target_callsign);
  const attribute = assignment?.manual
    ? `data-intercept-response="${escapeHtml(assignment.interceptor_callsign)}"`
    : operation
      ? `data-operation-target-response="${escapeHtml(operation.id)}"`
      : '';
  if (!attribute) return '<div class="intercept-contact-note">Response status requires a manual assignment or active alert operation.</div>';
  return `<div class="intercept-contact-controls" role="group" aria-label="Target response status">
    ${['UNKNOWN','RESPONDING','NOT_RESPONDING','COMMS_RESTORED'].map(status => `<button type="button" ${attribute} data-response-status="${status}" class="${current === status ? 'active ' : ''}${status === 'NOT_RESPONDING' ? 'danger' : status === 'RESPONDING' || status === 'COMMS_RESTORED' ? 'positive' : ''}">${contactStatusLabel(status)}</button>`).join('')}
  </div>`;
}

function interceptControlForTarget(callsign) {
  const target = normaliseCallsign(callsign);
  const control = (state.data?.intercept_controls || []).find(item => item.target_callsign === target) || {};
  const operation = operationForCallsign(target) || {};
  const assignment = activeInterceptAssignments().find(item => item.target_callsign === target) || {};
  return {
    target_callsign: target,
    target_response_status: control.target_response_status || assignment.target_response_status || operation.target_response_status || 'UNKNOWN',
    atc_coordination_status: control.atc_coordination_status || assignment.atc_coordination_status || operation.atc_coordination_status || 'UNCOORDINATED',
    command_status: control.command_status || assignment.command_status || operation.command_status || 'MONITOR',
    coordination_note: control.coordination_note || assignment.coordination_note || operation.coordination_note || '',
    updated_at: control.updated_at || operation.updated_at || assignment.updated_at || null,
    updated_by: control.updated_by || operation.target_response_updated_by || assignment.assigned_by || 'SYSTEM',
  };
}

function atcCoordinationLabel(status) {
  const labels = {
    UNCOORDINATED: 'NOT COORDINATED',
    ATC_NOTIFIED: 'ATC NOTIFIED',
    COORDINATING: 'COORDINATING',
    INTERCEPT_APPROVED: 'INTERCEPT APPROVED',
    HANDOFF_COMPLETE: 'HANDOFF COMPLETE',
  };
  return labels[String(status || 'UNCOORDINATED').toUpperCase()] || 'NOT COORDINATED';
}

function interceptCommandLabel(status) {
  const labels = {
    MONITOR: 'MONITOR',
    ATTEMPT_CONTACT: 'ATTEMPT CONTACT',
    IDENTIFY: 'IDENTIFY',
    ESCORT_SHADOW: 'ESCORT / SHADOW',
    BREAK_OFF: 'BREAK OFF',
    RETURN_TO_BASE: 'RETURN TO BASE',
  };
  return labels[String(status || 'MONITOR').toUpperCase()] || 'MONITOR';
}

function groupedInterceptAssignments() {
  const groups = new Map();
  for (const assignment of activeInterceptAssignments()) {
    const target = normaliseCallsign(assignment.target_callsign);
    if (!target) continue;
    if (!groups.has(target)) groups.set(target, []);
    groups.get(target).push(assignment);
  }
  return [...groups.entries()].map(([targetCallsign, assignments]) => ({
    targetCallsign,
    assignments: assignments.sort((a, b) => {
      const aEta = Number.isFinite(Number(a.estimated_intercept_minutes)) ? Number(a.estimated_intercept_minutes) : Infinity;
      const bEta = Number.isFinite(Number(b.estimated_intercept_minutes)) ? Number(b.estimated_intercept_minutes) : Infinity;
      return aEta - bEta || String(a.interceptor_callsign).localeCompare(String(b.interceptor_callsign));
    }),
  })).sort((a, b) => {
    const aManual = a.assignments.some(item => item.manual) ? 0 : 1;
    const bManual = b.assignments.some(item => item.manual) ? 0 : 1;
    return aManual - bManual || a.targetCallsign.localeCompare(b.targetCallsign);
  });
}

function setInterceptBatchFeedback(message, status = '') {
  const host = el('intercept-batch-feedback');
  if (!host) return;
  host.textContent = message;
  host.classList.toggle('error-text', status === 'error');
  host.classList.toggle('success-text', status === 'success');
}

async function runInterceptButtonAction(button, pendingLabel, action) {
  if (!button || button.disabled) return;
  const original = button.textContent;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  if (pendingLabel) button.textContent = pendingLabel;
  try {
    await action();
  } finally {
    if (button.isConnected) {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.textContent = original;
    }
  }
}

function activeTargetForBuilder() {
  return pilotForCallsign(state.interceptTargetCallsign)
    || pilotForCallsign(el('intercepts-target-input')?.value)
    || pilotForCallsign(state.selectedCallsign)
    || null;
}

function updateInterceptorSelectionUi() {
  const callsigns = [...state.multiInterceptorSelection].sort();
  const button = el('assign-selected-interceptors');
  const list = el('intercept-selected-list');
  const target = activeTargetForBuilder();
  if (el('intercept-selection-count')) el('intercept-selection-count').textContent = String(callsigns.length);
  if (button) {
    button.disabled = !target || callsigns.length === 0;
    button.textContent = callsigns.length
      ? `ASSIGN ${callsigns.length} SELECTED TO ${target?.callsign || 'TARGET'}`
      : 'ASSIGN 0 SELECTED';
  }
  if (list) {
    list.innerHTML = callsigns.length
      ? `<span>SELECTED</span>${callsigns.map(callsign => `<b>${escapeHtml(callsign)}</b>`).join('')}`
      : 'NO INTERCEPTORS SELECTED';
  }
}

function rankedInterceptorCandidates(target) {
  const filter = String(state.interceptorCandidateFilter || '').trim().toUpperCase();
  const assigned = new Map((state.data?.manual_intercepts || []).map(item => [item.interceptor_callsign, item.target_callsign]));
  return (state.data?.pilots || [])
    .filter(pilot => !pilot.on_ground && pilot.callsign !== target?.callsign)
    .filter(pilot => !filter || `${pilot.callsign} ${pilot.aircraft || ''} ${pilot.aircraft_type || ''} ${pilot.vsoa_label || ''}`.toUpperCase().includes(filter))
    .map(pilot => ({
      pilot,
      distance: target ? distanceNmBetween(pilot, target) : Infinity,
      assignedTarget: assigned.get(pilot.callsign) || '',
      rank: pilot.vsoa ? 0 : pilot.active_intercept ? 1 : pilot.aircraft_category === 'fighter' ? 2 : 3,
    }))
    .sort((a, b) => a.rank - b.rank || a.distance - b.distance || String(a.pilot.callsign).localeCompare(String(b.pilot.callsign)));
}

function renderMultiInterceptorCandidates() {
  const host = el('intercept-multi-candidates');
  const targetPreview = el('intercepts-target-preview');
  const target = activeTargetForBuilder();
  if (!host || !targetPreview) return;
  if (!target) {
    state.multiInterceptorSelection.clear();
    targetPreview.innerHTML = 'SELECT A LIVE TARGET AIRCRAFT';
    targetPreview.classList.remove('valid');
    host.innerHTML = '<div class="empty">SELECT A TARGET TO LOAD LIVE INTERCEPTOR OPTIONS</div>';
    updateInterceptorSelectionUi();
    return;
  }
  state.interceptTargetCallsign = target.callsign;
  const input = el('intercepts-target-input');
  if (input && document.activeElement !== input) input.value = target.callsign;
  targetPreview.innerHTML = `<strong>${escapeHtml(target.callsign)}</strong><span>${escapeHtml(target.aircraft || target.aircraft_type || 'UNKNOWN')} · ${Number(target.altitude || 0).toLocaleString()} FT · ${target.groundspeed || 0} KT · HDG ${String(normaliseHeading(target.heading)).padStart(3,'0')}°</span>`;
  targetPreview.classList.add('valid');
  const candidates = rankedInterceptorCandidates(target);
  const liveCallsigns = new Set(candidates.map(item => item.pilot.callsign));
  for (const callsign of [...state.multiInterceptorSelection]) {
    if (!liveCallsigns.has(callsign) || callsign === target.callsign) state.multiInterceptorSelection.delete(callsign);
  }
  host.innerHTML = candidates.length ? candidates.map(({ pilot, distance, assignedTarget }) => {
    const selected = state.multiInterceptorSelection.has(pilot.callsign);
    const assignedHere = assignedTarget === target.callsign;
    const className = `intercept-candidate${pilot.vsoa ? ' vsoa' : ''}${assignedTarget ? ' assigned' : ''}${selected ? ' selected' : ''}`;
    const assignmentNote = assignedHere ? `ASSIGNED TO THIS TARGET` : assignedTarget ? `ASSIGNED TO ${escapeHtml(assignedTarget)} · SELECT TO REASSIGN` : '';
    return `<label class="${className}">
      <input type="checkbox" data-multi-interceptor="${escapeHtml(pilot.callsign)}" ${selected ? 'checked' : ''} ${assignedHere ? 'disabled' : ''}>
      <span class="candidate-main"><strong>${escapeHtml(pilot.callsign)}</strong>${pilot.vsoa ? `<em>${escapeHtml(pilot.vsoa_label || 'VSOA')}</em>` : ''}<small>${escapeHtml(pilot.aircraft || pilot.aircraft_type || 'UNKNOWN')} · ${Number(pilot.altitude || 0).toLocaleString()} FT</small></span>
      <span class="candidate-geometry"><strong>${Number.isFinite(distance) ? distance.toFixed(distance < 100 ? 1 : 0) : '—'} NM</strong><small>${pilot.groundspeed || 0} KT · HDG ${String(normaliseHeading(pilot.heading)).padStart(3,'0')}°</small></span>
      ${assignmentNote ? `<span class="candidate-assignment">${assignmentNote}</span>` : ''}
    </label>`;
  }).join('') : '<div class="empty">NO MATCHING AIRBORNE AIRCRAFT</div>';
  updateInterceptorSelectionUi();
}

function targetControlButtonsHtml(targetCallsign, control) {
  const normalizedTarget = normaliseCallsign(targetCallsign);
  const response = String(control.target_response_status || 'UNKNOWN').toUpperCase();
  const atc = String(control.atc_coordination_status || 'UNCOORDINATED').toUpperCase();
  const command = String(control.command_status || 'MONITOR').toUpperCase();
  const hasDraft = state.interceptNoteDrafts.has(normalizedTarget);
  const noteValue = hasDraft ? state.interceptNoteDrafts.get(normalizedTarget) : (control.coordination_note || '');
  const responseButtons = ['UNKNOWN','RESPONDING','NOT_RESPONDING','COMMS_RESTORED'].map(value => `<button type="button" data-target-control="response_status" data-target-callsign="${escapeHtml(targetCallsign)}" data-control-value="${value}" class="${response === value ? 'active ' : ''}${value === 'NOT_RESPONDING' ? 'danger' : value === 'RESPONDING' || value === 'COMMS_RESTORED' ? 'positive' : ''}">${contactStatusLabel(value)}</button>`).join('');
  const atcButtons = ['UNCOORDINATED','ATC_NOTIFIED','COORDINATING','INTERCEPT_APPROVED','HANDOFF_COMPLETE'].map(value => `<button type="button" data-target-control="atc_status" data-target-callsign="${escapeHtml(targetCallsign)}" data-control-value="${value}" class="${atc === value ? 'active' : ''}">${atcCoordinationLabel(value)}</button>`).join('');
  const commandButtons = ['MONITOR','ATTEMPT_CONTACT','IDENTIFY','ESCORT_SHADOW','BREAK_OFF','RETURN_TO_BASE'].map(value => `<button type="button" data-target-control="command_status" data-target-callsign="${escapeHtml(targetCallsign)}" data-control-value="${value}" class="${command === value ? 'active' : ''}">${interceptCommandLabel(value)}</button>`).join('');
  return `<div class="intercept-target-controls">
    <section><div><span>TARGET RESPONSE</span><small>Observed response status shared across consoles.</small></div><div class="intercept-control-buttons response">${responseButtons}</div></section>
    <section><div><span>ATC COORDINATION</span><small>Workflow state only; it does not verify controller approval.</small></div><div class="intercept-control-buttons atc">${atcButtons}</div></section>
    <section><div><span>MISSION COMMAND</span><small>Shared simulation command/status for assigned interceptors.</small></div><div class="intercept-control-buttons command">${commandButtons}</div></section>
    <section class="intercept-note-control"><label><span>ATC / COMMAND NOTE</span><input data-intercept-note="${escapeHtml(normalizedTarget)}" class="${hasDraft ? 'dirty' : ''}" maxlength="500" value="${escapeHtml(noteValue)}" placeholder="Frequency, handoff, instructions, or coordination note"></label><button type="button" data-save-intercept-note="${escapeHtml(normalizedTarget)}">${hasDraft ? 'SAVE DRAFT' : 'SAVE NOTE'}</button></section>
  </div>`;
}

function interceptorCalculationCardHtml(assignment) {
  const interceptor = assignment.interceptor || pilotForCallsign(assignment.interceptor_callsign) || {};
  const target = assignment.target || pilotForCallsign(assignment.target_callsign) || {};
  const live = assignment.live !== false;
  const status = !live ? 'TRACK LOST' : String(assignment.closure_status || assignment.status || 'LIVE').toUpperCase();
  const vsoa = interceptor.vsoa ? `<em>${escapeHtml(interceptor.vsoa_label || 'VSOA')}</em>` : '<em class="unverified">NON-VSOA</em>';
  const calculatedAt = assignment.calculated_at || assignment.updated_at || state.data?.updated_at;
  return `<article class="interceptor-calculation-card${live ? '' : ' track-lost'}">
    <header><div><span>INTERCEPTOR</span><strong>${escapeHtml(assignment.interceptor_callsign)}</strong>${vsoa}</div><div class="interceptor-live-state"><span class="viewer-live-dot"></span><strong>${escapeHtml(status)}</strong><small>${assignment.manual ? 'MANUAL' : 'SQ 7777 AUTO'}</small></div></header>
    <div class="interceptor-primary-calcs"><div><span>ETA</span><strong>${escapeHtml(formatInterceptEta(assignment))}</strong></div><div><span>SEPARATION</span><strong>${assignment.separation_nm ?? '—'} NM</strong></div><div><span>CLOSURE</span><strong>${escapeHtml(formatClosure(assignment))}</strong></div><div><span>COURSE</span><strong>${assignment.recommended_course_deg == null ? '—' : String(assignment.recommended_course_deg).padStart(3,'0') + '°'}</strong></div></div>
    <div class="interceptor-secondary-calcs"><div><span>BEARING</span><strong>${assignment.bearing_to_target_deg == null ? '—' : String(assignment.bearing_to_target_deg).padStart(3,'0') + '°'}</strong></div><div><span>TURN</span><strong>${assignment.turn_required_deg ?? '—'}°</strong></div><div><span>ALT Δ</span><strong>${assignment.altitude_delta_ft == null ? '—' : `${assignment.altitude_delta_ft >= 0 ? '+' : ''}${Number(assignment.altitude_delta_ft).toLocaleString()} FT`}</strong></div><div><span>INT H/S/A</span><strong>${String(interceptor.heading ?? assignment.interceptor_heading_deg ?? 0).padStart(3,'0')}° · ${interceptor.groundspeed ?? assignment.interceptor_speed_kt ?? '—'} KT · ${Number(interceptor.altitude ?? assignment.interceptor_altitude_ft ?? 0).toLocaleString()} FT</strong></div></div>
    <div class="interceptor-live-calcs"><div><span>TARGET H/S/A</span><strong>${String(target.heading ?? assignment.target_heading_deg ?? 0).padStart(3,'0')}° · ${target.groundspeed ?? assignment.target_speed_kt ?? '—'} KT · ${Number(target.altitude ?? assignment.target_altitude_ft ?? 0).toLocaleString()} FT</strong></div><div><span>ANTICIPATED INTERCEPT POINT</span><strong>${Number.isFinite(Number(assignment.intercept_point_lat)) && Number.isFinite(Number(assignment.intercept_point_lon)) ? `${Number(assignment.intercept_point_lat).toFixed(4)}, ${Number(assignment.intercept_point_lon).toFixed(4)}` : 'NO CURRENT SOLUTION'}</strong><small>Recomputed from current target motion</small></div><div><span>LAST RECALC</span><strong>${formatZuluTimestamp(calculatedAt)}</strong><small>FEED #${state.data?.feed_sequence ?? 0}</small></div></div>
    <footer><button type="button" data-focus-pair="${escapeHtml(assignment.interceptor_callsign)}" data-focus-target="${escapeHtml(assignment.target_callsign)}">SHOW ON MAP</button>${assignment.manual ? `<button type="button" class="danger" data-intercept-cancel="${escapeHtml(assignment.interceptor_callsign)}">RELEASE ${escapeHtml(assignment.interceptor_callsign)}</button>` : ''}</footer>
  </article>`;
}

function renderActiveInterceptWorkspace(force = false) {
  const assignments = activeInterceptAssignments();
  const groups = groupedInterceptAssignments();
  updateInterceptRecalcStatus();
  const tabCount = el('active-intercept-tab-count');
  if (tabCount) tabCount.textContent = String(assignments.length);
  if (el('intercept-target-count')) el('intercept-target-count').textContent = String(groups.length);
  if (el('intercept-assigned-count')) el('intercept-assigned-count').textContent = String(assignments.length);
  if (el('intercept-vsoa-available')) el('intercept-vsoa-available').textContent = String((state.data?.pilots || []).filter(item => item.vsoa && !item.on_ground).length);
  if (el('intercept-selection-count')) el('intercept-selection-count').textContent = String(state.multiInterceptorSelection.size);
  const select = el('intercept-focus-select');
  const container = el('intercept-focus-content');
  if (!container) return;
  if (!state.activeInterceptKey || !assignments.some(item => item.key === state.activeInterceptKey)) state.activeInterceptKey = assignments[0]?.key || null;
  if (!state.interceptTargetCallsign || !pilotForCallsign(state.interceptTargetCallsign)) {
    state.interceptTargetCallsign = pilotForCallsign(state.selectedCallsign)?.callsign || groups[0]?.targetCallsign || null;
  }
  if (select) select.innerHTML = assignments.length
    ? assignments.map(item => `<option value="${escapeHtml(item.key)}" ${item.key === state.activeInterceptKey ? 'selected' : ''}>${escapeHtml(item.interceptor_callsign)} → ${escapeHtml(item.target_callsign)}</option>`).join('')
    : '<option value="">NO ACTIVE ASSIGNMENT</option>';
  const renderKey = compactJson({
    assignments: assignments.map(item => [item.key, item.calculated_at, item.updated_at, item.separation_nm, item.estimated_intercept_minutes, item.signed_closure_rate_kt, item.recommended_course_deg, item.live]),
    controls: (state.data?.intercept_controls || []).map(item => [item.target_callsign, item.updated_at, item.target_response_status, item.atc_coordination_status, item.command_status, item.coordination_note]),
    target: state.interceptTargetCallsign,
    selected: [...state.multiInterceptorSelection].sort(),
    filter: state.interceptorCandidateFilter,
  });
  if (!force && state.interceptWorkspaceRenderKey === renderKey) return;
  state.interceptWorkspaceRenderKey = renderKey;
  renderMultiInterceptorCandidates();
  if (!groups.length) {
    container.innerHTML = '<div class="intercept-focus-empty"><strong>NO ACTIVE INTERCEPTS</strong><span>Select a target and one or more live interceptors from the assignment panel.</span></div>';
    renderInterceptTacticalMap(force);
    updateInterceptRecalcStatus();
    return;
  }
  container.innerHTML = groups.map(({ targetCallsign, assignments: groupAssignments }) => {
    const target = pilotForCallsign(targetCallsign) || groupAssignments[0]?.target || {};
    const control = interceptControlForTarget(targetCallsign);
    const earliest = groupAssignments.map(item => Number(item.estimated_intercept_minutes)).filter(Number.isFinite).sort((a,b) => a-b)[0];
    const manualCount = groupAssignments.filter(item => item.manual).length;
    return `<article class="intercept-target-group" data-target-group="${escapeHtml(targetCallsign)}">
      <header class="intercept-target-group-header"><div><span>INTERCEPT TARGET</span><strong>${escapeHtml(targetCallsign)}</strong><small>${escapeHtml(target.aircraft || target.aircraft_type || 'UNKNOWN')} · ${Number(target.altitude || 0).toLocaleString()} FT · ${target.groundspeed || 0} KT · HDG ${String(normaliseHeading(target.heading)).padStart(3,'0')}°</small></div><div class="target-group-status"><span>${groupAssignments.length} INTERCEPTOR${groupAssignments.length === 1 ? '' : 'S'}</span><strong>${Number.isFinite(earliest) ? `${earliest < 1 ? '<1' : earliest.toFixed(earliest < 10 ? 1 : 0)} MIN EARLIEST` : 'NO ETA'}</strong><small>${contactStatusLabel(control.target_response_status)} · ${atcCoordinationLabel(control.atc_coordination_status)} · ${interceptCommandLabel(control.command_status)}</small></div></header>
      ${targetControlButtonsHtml(targetCallsign, control)}
      <div class="interceptor-calculation-list">${groupAssignments.map(interceptorCalculationCardHtml).join('')}</div>
      <div class="intercept-target-group-actions"><button type="button" data-add-interceptor-target="${escapeHtml(targetCallsign)}">ADD MORE INTERCEPTORS</button><button type="button" data-focus-target-only="${escapeHtml(targetCallsign)}">FOCUS TARGET ON MAP</button>${manualCount ? `<button type="button" class="danger" data-release-target-interceptors="${escapeHtml(targetCallsign)}">RELEASE ALL MANUAL INTERCEPTORS</button>` : ''}</div>
    </article>`;
  }).join('');
  renderInterceptTacticalMap(force);
  updateInterceptRecalcStatus();
}

async function assignSelectedInterceptors() {
  const target = activeTargetForBuilder();
  const callsigns = [...state.multiInterceptorSelection].sort();
  if (!target) return setInterceptBatchFeedback('Select a live target aircraft first.', 'error');
  if (!callsigns.length) return setInterceptBatchFeedback('Select at least one interceptor.', 'error');
  const existingAssignments = new Map((state.data?.manual_intercepts || []).map(item => [item.interceptor_callsign, item.target_callsign]));
  const reassignments = callsigns.filter(callsign => existingAssignments.has(callsign) && existingAssignments.get(callsign) !== target.callsign);
  if (reassignments.length && !window.confirm(`${reassignments.join(', ')} ${reassignments.length === 1 ? 'is' : 'are'} assigned to another target. Reassign to ${target.callsign}?`)) return;
  setInterceptBatchFeedback(`Assigning ${callsigns.length} interceptor${callsigns.length === 1 ? '' : 's'} to ${target.callsign}…`);
  const response = await fetchWithTimeout('/api/intercepts/manual/batch', {
    method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ interceptor_callsigns: callsigns, target_callsign: target.callsign, console_id: state.consoleId, console_label: state.consoleLabel }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) throw new Error(payload.error || `batch_${response.status}`);
  const assigned = new Set((payload.assignments || []).map(item => item.interceptor_callsign));
  const errors = payload.errors || {};
  state.multiInterceptorSelection = new Set(callsigns.filter(callsign => !assigned.has(callsign)));
  state.interceptTargetCallsign = target.callsign;
  await loadLive(true);
  const errorCalls = Object.keys(errors);
  setInterceptBatchFeedback(
    errorCalls.length
      ? `${assigned.size} assigned to ${target.callsign}; ${errorCalls.join(', ')} could not be assigned and remain selected.`
      : `${assigned.size || callsigns.length} interceptor${callsigns.length === 1 ? '' : 's'} assigned to ${target.callsign}. Live recalculation is active.`,
    errorCalls.length ? 'error' : 'success',
  );
  renderActiveInterceptWorkspace(true);
}

async function recalculateInterceptsNow() {
  if (state.interceptRecalcBusy) return;
  state.interceptRecalcBusy = true;
  updateInterceptRecalcStatus();
  try {
    const response = await fetchWithTimeout('/api/intercepts/recalculate', {
      method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ console_id: state.consoleId, console_label: state.consoleLabel }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.error || `recalculate_${response.status}`);
    await loadLive(true);
    const refreshed = Number(payload.active_count ?? payload.count ?? 0);
    setInterceptBatchFeedback(`${refreshed} active intercept solution${refreshed === 1 ? '' : 's'} recalculated from the latest live tracks.`, 'success');
  } finally {
    state.interceptRecalcBusy = false;
    updateInterceptRecalcStatus();
  }
}

async function updateInterceptTargetControl(targetCallsign, field, value, note) {
  const body = { console_id: state.consoleId, console_label: state.consoleLabel };
  if (field) body[field] = value;
  if (note !== undefined) body.note = note;
  const response = await fetchWithTimeout(`/api/intercepts/targets/${encodeURIComponent(targetCallsign)}/control`, {
    method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) throw new Error(payload.error || `control_${response.status}`);
  if (note !== undefined) state.interceptNoteDrafts.delete(normaliseCallsign(targetCallsign));
  await loadLive(true);
  renderActiveInterceptWorkspace(true);
}

async function releaseTargetInterceptors(targetCallsign) {
  const response = await fetchWithTimeout(`/api/intercepts/targets/${encodeURIComponent(targetCallsign)}`, {
    method: 'DELETE', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ console_id: state.consoleId, console_label: state.consoleLabel }),
  });
  if (!response.ok) throw new Error(`release_target_${response.status}`);
  await loadLive(true);
  renderActiveInterceptWorkspace(true);
}

async function setInterceptResponse(interceptorCallsign, status) {
  const response = await fetchWithTimeout(`/api/intercepts/manual/${encodeURIComponent(interceptorCallsign)}/response`, {
    method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ status, console_id: state.consoleId, console_label: state.consoleLabel }),
  });
  if (!response.ok) throw new Error(`response_${response.status}`);
  await loadLive(true);
  renderActiveInterceptWorkspace(true);
}

async function setOperationTargetResponse(operationId, status) {
  const response = await fetchWithTimeout(`/api/operations/${encodeURIComponent(operationId)}/target-response`, {
    method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ status, console_id: state.consoleId, console_label: state.consoleLabel }),
  });
  if (!response.ok) throw new Error(`response_${response.status}`);
  await loadLive(true);
  renderActiveInterceptWorkspace(true);
}

function liveVsoaAircraft() {
  return (state.data?.pilots || [])
    .filter(pilot => pilot?.vsoa && !pilot?.on_ground)
    .sort((a, b) => {
      const selectedA = normaliseCallsign(a.callsign) === normaliseCallsign(state.operatorAircraftCallsign) ? -1 : 0;
      const selectedB = normaliseCallsign(b.callsign) === normaliseCallsign(state.operatorAircraftCallsign) ? -1 : 0;
      const blackjackA = a.blackjack ? -1 : 0;
      const blackjackB = b.blackjack ? -1 : 0;
      return selectedA - selectedB || blackjackA - blackjackB || String(a.callsign).localeCompare(String(b.callsign));
    });
}

function operatorAircraftPilot() {
  const pilot = pilotForCallsign(state.operatorAircraftCallsign);
  return pilot?.vsoa && !pilot?.on_ground ? pilot : null;
}

function saveOperatorAircraftSelection(callsign, announce = true) {
  const normalized = normaliseCallsign(callsign);
  const pilot = pilotForCallsign(normalized);
  if (!pilot || !pilot.vsoa || pilot.on_ground) {
    if (announce) el('system-health').textContent = normalized
      ? `${normalized} IS NOT AN AIRBORNE VSOA-TAGGED TRACK`
      : 'SELECT A LIVE VSOA AIRCRAFT';
    return false;
  }
  state.operatorAircraftCallsign = normalized;
  try { localStorage.setItem('vng-adoc.operator-aircraft', normalized); } catch (_) {}
  const input = el('atc-operator-aircraft-input');
  if (input && document.activeElement !== input) input.value = normalized;
  if (announce) el('system-health').textContent = `MY VSOA AIRCRAFT SET · ${normalized}`;
  state.atcRenderKey = null;
  state.atcMapRenderKey = null;
  renderAtcWorkspace(true);
  return true;
}

function renderAtcVsoaOptions() {
  const options = el('atc-vsoa-aircraft-options');
  if (!options) return;
  const aircraft = liveVsoaAircraft();
  options.innerHTML = aircraft.map(pilot => `<option value="${escapeHtml(pilot.callsign)}" label="${escapeHtml(`${pilot.vsoa_label || 'VSOA'} · ${pilot.aircraft || pilot.aircraft_type || 'UNKNOWN'} · ${Number(pilot.altitude || 0).toLocaleString()} FT · ${pilot.center || 'NO ARTCC'}`)}"></option>`).join('');
}

function renderAtcAircraftSelectors() {
  renderAtcVsoaOptions();
  const operatorSelect = el('atc-operator-aircraft-select');
  const targetSelect = el('atc-track-select');
  const pilots = [...(state.data?.pilots || [])].sort((a, b) => String(a.callsign).localeCompare(String(b.callsign)));
  if (operatorSelect) {
    const selected = normaliseCallsign(state.operatorAircraftCallsign);
    operatorSelect.innerHTML = '<option value="">SELECT VSOA CALLSIGN</option>' + liveVsoaAircraft().map(pilot => `<option value="${escapeHtml(pilot.callsign)}"${pilot.callsign === selected ? ' selected' : ''}>${escapeHtml(pilot.callsign)} · ${escapeHtml(pilot.aircraft || pilot.aircraft_type || 'UNKNOWN')} · ${Number(pilot.altitude || 0).toLocaleString()} FT · ${escapeHtml(pilot.center || 'NO ARTCC')}</option>`).join('');
  }
  if (targetSelect) {
    const selected = normaliseCallsign(state.atcSelectedCallsign);
    const activeCaseCalls = new Set((state.data?.operations || []).filter(item => item.active && !item.completed).map(item => normaliseCallsign(item.callsign)));
    const cases = pilots.filter(pilot => activeCaseCalls.has(pilot.callsign));
    const others = pilots.filter(pilot => !activeCaseCalls.has(pilot.callsign));
    const option = pilot => `<option value="${escapeHtml(pilot.callsign)}"${pilot.callsign === selected ? ' selected' : ''}>${escapeHtml(pilot.callsign)} · ${escapeHtml(pilot.aircraft || pilot.aircraft_type || 'UNKNOWN')} · ${Number(pilot.altitude || 0).toLocaleString()} FT · ${escapeHtml(pilot.center || 'NO ARTCC')}</option>`;
    targetSelect.innerHTML = '<option value="">SELECT AIRCRAFT</option>' + (cases.length ? `<optgroup label="ACTIVE CASES">${cases.map(option).join('')}</optgroup>` : '') + `<optgroup label="ALL LIVE AIRCRAFT">${others.map(option).join('')}</optgroup>`;
  }
}

function atcVsoaRosterHtml(activeCases, assignments) {
  const aircraft = liveVsoaAircraft();
  const selected = operatorAircraftPilot();
  const cards = aircraft.map(pilot => {
    const assignment = assignments.find(item => item.interceptor_callsign === pilot.callsign);
    const active = selected?.callsign === pilot.callsign;
    return `<article class="atc-vsoa-aircraft-card${active ? ' active' : ''}${pilot.blackjack ? ' blackjack' : ''}">
      <header><div><span>${active ? 'MY AIRCRAFT' : escapeHtml(pilot.vsoa_label || 'VSOA REMARKS')}</span><strong>${escapeHtml(pilot.callsign)}</strong><small>${escapeHtml(pilot.aircraft || pilot.aircraft_type || 'UNKNOWN')} · ${Number(pilot.altitude || 0).toLocaleString()} FT · ${pilot.groundspeed || 0} KT · ${escapeHtml(pilot.center || 'NO ARTCC')}</small></div>${assignment ? `<em>ASSIGNED → ${escapeHtml(assignment.target_callsign)}</em>` : '<em>AVAILABLE</em>'}</header>
      <div class="atc-vsoa-aircraft-actions"><button type="button" data-atc-set-operator="${escapeHtml(pilot.callsign)}">${active ? 'MY AIRCRAFT SELECTED' : 'SET AS MY AIRCRAFT'}</button><button type="button" class="secondary" data-atc-select-call="${escapeHtml(pilot.callsign)}">VIEW LIVE TRACK</button></div>
    </article>`;
  }).join('');
  const targets = activeCases.slice(0, 8).map(operation => `<button type="button" data-atc-select-call="${escapeHtml(operation.callsign)}"><strong>${escapeHtml(operation.callsign)}</strong><span>${escapeHtml(operation.status || 'ACTIVE CASE')}</span></button>`).join('');
  return `<section class="atc-vsoa-dispatch-home">
    <div class="atc-panel-heading"><span>LIVE VSOA AIRCRAFT</span><small>VSOA-tagged flights are detected from explicit flight-plan remarks. Select your own callsign before accepting an intercept assignment.</small></div>
    <div class="atc-vsoa-aircraft-list">${cards || '<div class="empty">NO AIRBORNE VSOA-TAGGED AIRCRAFT ARE CURRENTLY VISIBLE IN THIS DASHBOARD VIEW</div>'}</div>
    <div class="atc-vsoa-target-home"><div><span>AVAILABLE ALERT TARGETS</span><small>Select a case, or enter any live target callsign in TARGET / CASE AIRCRAFT above.</small></div><div class="atc-vsoa-target-buttons">${targets || '<span>NO ACTIVE ALERT CASES · YOU MAY STILL ENTER A LIVE AIRCRAFT CALLSIGN MANUALLY</span>'}</div></div>
  </section>`;
}

function atcOperatorDispatchHtml(targetPilot, assignments) {
  const operator = operatorAircraftPilot();
  if (!operator) {
    return `<section class="atc-operator-dispatch unavailable"><div><span>VSOA INTERCEPTOR ASSIGNMENT</span><strong>SELECT YOUR LIVE VSOA AIRCRAFT</strong><small>Use MY VSOA AIRCRAFT above or choose one from the live VSOA list. The console cannot determine which VSOA flight is yours when several are online.</small></div></section>`;
  }
  if (!targetPilot || operator.callsign === targetPilot.callsign) {
    return `<section class="atc-operator-dispatch self"><div><span>MY LIVE VSOA AIRCRAFT</span><strong>${escapeHtml(operator.callsign)}</strong><small>${escapeHtml(operator.aircraft || operator.aircraft_type || 'UNKNOWN')} · ${Number(operator.altitude || 0).toLocaleString()} FT · ${operator.groundspeed || 0} KT · ${escapeHtml(operator.center || 'NO ARTCC')}</small></div><div class="atc-operator-dispatch-note">Select a different TARGET / CASE AIRCRAFT to create an intercept assignment.</div></section>`;
  }
  const assignment = assignments.find(item => item.interceptor_callsign === operator.callsign) || null;
  const sameTarget = assignment?.target_callsign === targetPilot.callsign;
  const distance = distanceNmBetween(operator, targetPilot);
  const buttonLabel = sameTarget
    ? `OPEN ${operator.callsign} → ${targetPilot.callsign} INTERCEPT`
    : assignment
      ? `REASSIGN ${operator.callsign} TO ${targetPilot.callsign}`
      : `ASSIGN ${operator.callsign} TO INTERCEPT ${targetPilot.callsign}`;
  return `<section class="atc-operator-dispatch${sameTarget ? ' assigned' : ''}">
    <div class="atc-operator-dispatch-route"><div><span>MY VSOA AIRCRAFT</span><strong>${escapeHtml(operator.callsign)}</strong><small>${escapeHtml(operator.vsoa_label || 'VSOA')} · ${Number(operator.altitude || 0).toLocaleString()} FT · ${operator.groundspeed || 0} KT</small></div><i>→</i><div><span>SELECTED TARGET</span><strong>${escapeHtml(targetPilot.callsign)}</strong><small>${escapeHtml(targetPilot.aircraft || targetPilot.aircraft_type || 'UNKNOWN')} · ${Number(targetPilot.altitude || 0).toLocaleString()} FT · ${targetPilot.groundspeed || 0} KT</small></div></div>
    <div class="atc-operator-dispatch-meta"><span>${Number.isFinite(distance) ? distance.toFixed(1) : '—'} NM CURRENT SEPARATION</span>${assignment && !sameTarget ? `<span class="warning">CURRENTLY ASSIGNED TO ${escapeHtml(assignment.target_callsign)}</span>` : ''}${sameTarget ? '<span class="positive">LIVE INTERCEPT ASSIGNMENT ACTIVE</span>' : ''}</div>
    <button type="button" class="${sameTarget ? 'secondary' : ''}" data-atc-dispatch-operator="${escapeHtml(operator.callsign)}" data-target-callsign="${escapeHtml(targetPilot.callsign)}" data-assignment-active="${sameTarget ? 'true' : 'false'}">${escapeHtml(buttonLabel)}</button>
    <small class="atc-operator-dispatch-warning">Shared VATSIM workflow only. This does not command the aircraft or verify ATC/VSOA authorization.</small>
  </section>`;
}

function atcSelectedPilot() {
  return pilotForCallsign(state.atcSelectedCallsign)
    || pilotForCallsign(state.selectedCallsign)
    || pilotForCallsign(state.data?.alerts?.[0]?.callsign)
    || null;
}

function atcCommunicationsStatus(pilot) {
  if (!pilot) return 'NO TRACK';
  if (pilot.manual_nordo) return 'MANUAL NORDO CONFIRMED';
  if (pilot.automatic_flag_dismissed) return 'AUTOMATIC FLAG DISMISSED — CONTINUE MONITORING';
  if (pilot.mass_alert_verification_pending) {
    const verify = pilot.mass_alert_verification || {};
    return `MULTI-TRACK BURST — VERIFYING ${verify.stable_snapshots || 0}/${verify.required_snapshots || 0}`;
  }
  if (pilot.temporary_exemption_active) return 'TEMPORARY OPERATOR EXEMPTION ACTIVE';
  if (pilot.frequency_change_grace_active) return 'FREQUENCY CHANGE STABILITY GRACE';
  if (pilot.communications_cooldown_active) return 'POST-HANDOFF COOLDOWN ACTIVE';
  if (pilot.active_artcc_frequency_match) return 'ACTIVE ARTCC FREQUENCY MATCHED';
  if (pilot.advisory_frequency_whitelisted) return 'CTAF / UNICOM WHITELIST ACTIVE';
  if (pilot.online_center_handoff) return `EARLY HANDOFF TO ${pilot.online_center_handoff_detail?.downstream_controller || 'DOWNSTREAM CENTER'} VERIFIED`;
  if (pilot.early_unicom_handoff) return 'EARLY 122.800 HANDOFF SUPPRESSED';
  if (pilot.nordo_gate_ready) return pilot.frequency_mismatch_active ? 'HIGH-CONFIDENCE MISMATCH TIMER ACTIVE' : 'HIGH-CONFIDENCE NORDO GATE READY';
  return 'AUTOMATIC ALERT GATE INHIBITED';
}


function currentAlertForCallsign(callsign) {
  const normalized = normaliseCallsign(callsign);
  return (state.data?.alerts || []).find(item => normaliseCallsign(item.callsign) === normalized) || null;
}

function evidenceCheck(label, passed, detail, tone = '') {
  const status = passed ? 'PASS' : 'BLOCK';
  return `<div class="atc-evidence-row ${passed ? 'pass' : 'block'} ${tone}"><i>${passed ? '✓' : '×'}</i><span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(detail || '')}</small></span><em>${status}</em></div>`;
}

function atcEvidencePanelHtml(pilot, operation) {
  const alert = currentAlertForCallsign(pilot?.callsign);
  const reasonCodes = (alert?.reasons || []).map(item => item.code).filter(Boolean);
  const expected = formatFreqs(pilot?.active_artcc_frequencies || pilot?.center_frequencies);
  const radios = formatPilotRadios(pilot);
  const mismatchSeconds = Number(pilot?.frequency_mismatch_seconds || 0);
  const controllerStable = Boolean(pilot?.communications_watch_controller_stable || pilot?.frequency_mismatch_controller_stable);
  const suppression = pilot?.temporary_exemption_active
    ? `Temporary exemption: ${pilot.temporary_exemption_detail?.reason || 'operator-approved'}`
    : pilot?.online_center_handoff
      ? `Verified handoff to ${pilot.online_center_handoff_detail?.downstream_controller || 'downstream Center'}`
      : pilot?.communications_cooldown_active
        ? `Post-handoff cooldown: ${pilot.communications_cooldown_remaining_seconds || 0}s remaining`
        : pilot?.frequency_change_grace_active
          ? `Frequency-change grace: ${pilot.frequency_change_grace_remaining_seconds || 0}s remaining`
          : pilot?.advisory_frequency_whitelisted
            ? 'Published advisory frequency verified'
            : pilot?.early_unicom_handoff
              ? 'Early UNICOM handoff verified'
              : 'No automatic suppression active';
  const rows = [
    evidenceCheck('Airborne operating profile', !pilot?.on_ground && Number(pilot?.groundspeed || 0) >= 80, `${Number(pilot?.altitude || 0).toLocaleString()} FT · ${pilot?.groundspeed || 0} KT`),
    evidenceCheck('Live controlling coverage', Boolean(pilot?.center && pilot.center !== 'NONE'), pilot?.center || 'No qualifying controller'),
    evidenceCheck('Controller stability gate', controllerStable, controllerStable ? 'Online-duration requirement satisfied' : `${pilot?.communications_watch_stabilization_remaining_seconds ?? pilot?.frequency_mismatch_stabilization_remaining_seconds ?? '—'}s remaining`),
    evidenceCheck('Reported radio differs from active ARTCC', Boolean(pilot?.frequency_mismatch_current), `Reported ${radios} · Expected ${expected}`),
    evidenceCheck('Observed mismatch stability', Boolean(pilot?.frequency_mismatch_active), `${mismatchSeconds}s observed · ${pilot?.frequency_mismatch_case_status || 'INACTIVE'}`),
    evidenceCheck('High-confidence NORDO gate', Boolean(pilot?.nordo_gate_ready), pilot?.nordo_gate_ready ? 'Automatic gate ready for operator review' : suppression),
    ...(pilot?.mass_alert_verification_pending ? [evidenceCheck(
      'Independent burst verification',
      false,
      `${pilot.mass_alert_verification?.stable_snapshots || 0}/${pilot.mass_alert_verification?.required_snapshots || 0} fresh stable snapshots · ${pilot.mass_alert_verification?.remaining_seconds || 0}s minimum hold remaining`,
      'verify',
    )] : []),
    ...(pilot?.automatic_flag_dismissed ? [evidenceCheck(
      'Automatic flag disposition',
      true,
      `Dismissed by ${pilot.automatic_flag_dismissal?.dismissed_by || 'ATC console'} · ${pilot.automatic_flag_dismissal?.reason || 'operator review'}`,
      'dismissed',
    )] : []),
  ].join('');
  const reasons = reasonCodes.length ? reasonCodes.join(' · ') : 'No active alert reason codes';
  return `<section class="atc-evidence-panel"><div class="atc-panel-heading"><span>ALERT EVIDENCE</span><small>Why the track is alerting—or why escalation is blocked.</small></div>${rows}<div class="atc-evidence-codes"><span>DETECTOR CODES</span><strong>${escapeHtml(reasons)}</strong></div></section>`;
}

function atcDetectorDiagnosticsHtml(pilot) {
  const candidates = (pilot?.controller_candidates || []).length
    ? pilot.controller_candidates.map(item => `<div class="diagnostic-candidate"><strong>${escapeHtml(item.callsign || 'ATC')}</strong><span>${escapeHtml(item.facility || '—')} · ${escapeHtml(formatFreqs(item.frequencies))} · ${Number(item.distance_nm || 0).toFixed(1)} / ${Number(item.coverage_radius_nm || 0).toFixed(1)} NM · ${escapeHtml(item.coverage_confidence || item.match_quality || '—')}</span></div>`).join('')
    : '<div class="diagnostic-candidate"><strong>NO QUALIFYING LIVE ATC COVERAGE</strong><span>The wrong-frequency timer cannot advance without a valid coverage candidate.</span></div>';
  return `<details class="detector-diagnostics atc-detector-diagnostics"><summary>DETECTOR DIAGNOSTICS</summary><div class="diagnostic-grid">
    <div><span>WRONG-FREQ TIMER</span><strong>${pilot?.frequency_mismatch_active ? formatDuration(pilot.frequency_mismatch_seconds || 0) : 'INACTIVE'}</strong></div>
    <div><span>WATCH ACTIVATION</span><strong>${pilot?.communications_watch_stabilization_remaining_seconds ? `${formatDuration(pilot.communications_watch_stabilization_remaining_seconds)} REMAINING` : 'READY / NOT REQUIRED'}</strong></div>
    <div><span>AUTO-FLAG STABILIZATION</span><strong>${pilot?.frequency_mismatch_stabilization_remaining_seconds ? `${formatDuration(pilot.frequency_mismatch_stabilization_remaining_seconds)} REMAINING` : 'READY / NOT REQUIRED'}</strong></div>
    <div><span>AUTO-FLAG ELIGIBLE TIMER</span><strong>${pilot?.frequency_mismatch_active ? `${formatDuration(pilot.auto_scramble_mismatch_seconds || 0)} / ${formatDuration(pilot.frequency_mismatch_threshold_seconds || 0)} · ${pilot.auto_scramble_eligible ? 'COUNTING' : 'PAUSED'}` : 'INACTIVE'}</strong></div>
    <div><span>NORDO GATE</span><strong>${pilot?.nordo_gate_ready ? 'READY · EXACT ACTIVE ARTCC' : 'INHIBITED / NOT QUALIFIED'}</strong></div>
    <div><span>PILOT RADIO</span><strong>${escapeHtml(formatPilotRadios(pilot))}</strong></div>
    <div><span>VALID ATC FREQ(S)</span><strong>${escapeHtml(formatFreqs(pilot?.active_artcc_frequencies || pilot?.center_frequencies))}</strong></div>
    <div><span>LAST CASE RESET</span><strong>${escapeHtml(String(pilot?.frequency_mismatch_last_reset_reason || 'NONE').replaceAll('_',' '))}</strong></div>
    <div><span>SUPPRESSIONS</span><strong>${pilot?.online_center_handoff ? 'VERIFIED CENTER HANDOFF' : pilot?.advisory_frequency_whitelisted ? 'PUBLISHED CTAF / UNICOM' : pilot?.early_unicom_handoff ? 'EARLY UNICOM HANDOFF' : pilot?.temporary_exemption_active ? 'TEMPORARY EXEMPTION' : 'NONE'}</strong></div>
  </div><div class="diagnostic-candidates"><div class="section-label">ATC COVERAGE CANDIDATES</div>${candidates}</div><div class="atc-diagnostic-note">121.500 Guard and 122.800 advisory/UNICOM never count as ATC contact. 122.800 suppression requires a verified nearby advisory frequency or likely early handoff.</div></details>`;
}

function atcTimelinePanelHtml(operation) {
  const events = (operation?.events || []).slice().reverse().slice(0, 16);
  const rows = events.length
    ? events.map(event => `<div class="atc-timeline-row"><time>${formatZulu(event.time)}</time><span><strong>${escapeHtml(event.label || event.code || 'EVENT')}</strong>${event.detail ? `<small>${escapeHtml(event.detail)}</small>` : ''}</span></div>`).join('')
    : '<div class="empty compact-empty">NO CASE EVENTS RECORDED</div>';
  return `<section class="atc-timeline-panel"><div class="atc-panel-heading"><span>ALERT TIMELINE</span><small>Newest event first · retained with the operational case.</small></div><div class="atc-timeline-list">${rows}</div></section>`;
}

function atcHandoffPanelHtml(pilot) {
  const detail = pilot?.online_center_handoff_detail || null;
  if (!detail) {
    const cooldown = pilot?.communications_cooldown_active
      ? `<div class="atc-handoff-cooldown"><strong>POST-HANDOFF COOLDOWN ACTIVE</strong><span>${pilot.communications_cooldown_remaining_seconds || 0} seconds remaining · ${escapeHtml(pilot.communications_cooldown_reason || 'HANDOFF')}</span></div>`
      : '<div class="atc-handoff-empty">No verified adjacent-Center handoff is active for this track.</div>';
    return `<section class="atc-handoff-panel"><div class="atc-panel-heading"><span>ARTCC HANDOFF</span><small>Boundary projection and downstream radio verification.</small></div>${cooldown}</section>`;
  }
  const speed = Math.max(1, Number(pilot?.groundspeed || 0));
  const distance = Number(detail.boundary_distance_nm ?? detail.downstream_entry_distance_nm ?? 0);
  const minutes = Math.max(0, distance / speed * 60);
  return `<section class="atc-handoff-panel active"><div class="atc-panel-heading"><span>ARTCC HANDOFF VERIFIED</span><small>Projected path enters the staffed downstream ARTCC.</small></div><div class="atc-handoff-route"><strong>${escapeHtml(detail.current_artcc || detail.current_controller || 'CURRENT')}</strong><i>→</i><strong>${escapeHtml(detail.downstream_artcc || detail.downstream_controller || 'DOWNSTREAM')}</strong></div><div class="atc-handoff-grid"><div><span>BOUNDARY DISTANCE</span><strong>${distance.toFixed(1)} NM</strong></div><div><span>EST. CROSSING</span><strong>${minutes.toFixed(1)} MIN</strong></div><div><span>DOWNSTREAM POSITION</span><strong>${escapeHtml(detail.downstream_controller || 'ONLINE CENTER')}</strong></div><div><span>MATCHED RADIO</span><strong>${escapeHtml(formatFreqs(detail.matched_frequencies))}</strong></div><div><span>PROJECTED POINT</span><strong>${Number(detail.projected_lat || 0).toFixed(3)}, ${Number(detail.projected_lon || 0).toFixed(3)}</strong></div><div><span>STATUS</span><strong>WHITELISTED</strong></div></div></section>`;
}

function activeExemptionsForCallsign(callsign) {
  const normalized = normaliseCallsign(callsign);
  return (state.data?.temporary_exemptions || []).filter(item => normaliseCallsign(item.callsign) === normalized);
}

function atcExemptionPanelHtml(pilot) {
  const exemptions = activeExemptionsForCallsign(pilot?.callsign);
  const active = exemptions.map(item => {
    const remaining = Math.max(0, Math.ceil((Number(item.expires_at_epoch || 0) * 1000 - Date.now()) / 60000));
    return `<div class="atc-exemption-active"><span><strong>${escapeHtml(item.reason || 'Operational exemption')}</strong><small>${remaining} min remaining · ${escapeHtml(item.created_by || 'CONSOLE')}</small></span><button type="button" class="danger" data-remove-exemption="${escapeHtml(item.id)}">REMOVE</button></div>`;
  }).join('');
  return `<section class="atc-exemption-panel"><div class="atc-panel-heading"><span>TEMPORARY EXEMPTION</span><small>Shared, expiring suppression for automatic communications escalation only.</small></div>${active || '<div class="atc-exemption-none">No active exemption for this aircraft.</div>'}<div class="atc-exemption-form"><label><span>REASON</span><input data-exemption-reason maxlength="240" value="Coordinated ATC handoff" autocomplete="off"></label><label><span>MINUTES</span><select data-exemption-minutes><option value="5">5</option><option value="10">10</option><option value="15" selected>15</option><option value="30">30</option><option value="60">60</option><option value="120">120</option></select></label><button type="button" data-create-exemption="${escapeHtml(pilot?.callsign || '')}">CREATE EXEMPTION</button></div><div class="atc-exemption-note">Does not suppress emergency squawks, manual NORDO, or active intercept assignments.</div></section>`;
}

function renderAtcWorkspace(force = false) {
  const host = el('atc-selected-track');
  const casesHost = el('atc-active-cases');
  if (!host || !casesHost) return;
  const pilots = state.data?.pilots || [];
  const activeCases = (state.data?.operations || []).filter(item => item.active && !item.completed);
  const assignments = activeInterceptAssignments();
  const stats = state.data?.stats || {};
  const caseCount = el('atc-case-tab-count');
  if (caseCount) caseCount.textContent = String(activeCases.length);
  const summaryValues = {
    'atc-summary-cases': activeCases.length,
    'atc-summary-nordo': pilots.filter(item => item.manual_nordo).length,
    'atc-summary-mismatch': pilots.filter(item => item.frequency_mismatch_active).length,
    'atc-summary-intercepts': assignments.length,
    'atc-summary-centers': stats.centers_online ?? (state.data?.controllers || []).filter(item => item.facility === 'CTR').length,
    'atc-summary-terminal': stats.terminal_online ?? (state.data?.controllers || []).filter(item => ['APP','DEP','TWR','GND','DEL'].includes(item.facility)).length,
  };
  for (const [id, value] of Object.entries(summaryValues)) if (el(id)) el(id).textContent = String(value ?? 0);
  const availableVsoa = liveVsoaAircraft();
  if (!operatorAircraftPilot() && availableVsoa.length === 1) saveOperatorAircraftSelection(availableVsoa[0].callsign, false);
  renderAtcVsoaOptions();
  const operatorPilot = operatorAircraftPilot();
  const operatorInput = el('atc-operator-aircraft-input');
  if (operatorInput && document.activeElement !== operatorInput) operatorInput.value = operatorPilot?.callsign || state.operatorAircraftCallsign || '';
  renderAtcAircraftSelectors();
  const pilot = atcSelectedPilot();
  if (pilot) {
    state.atcSelectedCallsign = pilot.callsign;
    if (state.rawData?.payload_mode === 'compact' && !state.trackDetailCache.has(pilot.callsign)) {
      fetchTrackDetail(pilot.callsign).then(() => renderAtcWorkspace(true)).catch(() => {});
    }
    const operatorPilot = operatorAircraftPilot();
    if (operatorPilot && state.rawData?.payload_mode === 'compact' && !state.trackDetailCache.has(operatorPilot.callsign)) {
      fetchTrackDetail(operatorPilot.callsign).then(() => renderAtcWorkspace(true)).catch(() => {});
    }
  }
  const input = el('atc-track-input');
  if (input && document.activeElement !== input) input.value = state.atcSelectedCallsign || '';
  const labelInput = el('atc-console-label');
  if (labelInput && document.activeElement !== labelInput) labelInput.value = state.consoleLabel || '';
  const key = compactJson({
    operator: operatorPilot ? [operatorPilot.callsign, operatorPilot.altitude, operatorPilot.groundspeed, operatorPilot.heading, operatorPilot.center] : state.operatorAircraftCallsign,
    selected: pilot ? [pilot.callsign, pilot.altitude, pilot.groundspeed, pilot.heading, pilot.manual_nordo, pilot.frequency_mismatch_seconds, pilot.nordo_gate_ready, pilot.mass_alert_verification_pending, pilot.mass_alert_verification, pilot.automatic_flag_dismissed, pilot.automatic_flag_dismissal, pilot.active_artcc_frequency_match, pilot.advisory_frequency_whitelisted, pilot.online_center_handoff, pilot.early_unicom_handoff, pilot.temporary_exemption_active, pilot.frequency_change_grace_active, pilot.communications_cooldown_active, pilot.communications_cooldown_remaining_seconds, pilot.center, pilot.controller_candidates] : null,
    assignments: assignments.map(item => [item.interceptor_callsign, item.target_callsign, item.updated_at, item.target_response_status, item.atc_coordination_status, item.command_status, item.coordination_note]),
    cases: activeCases.map(item => [item.id, item.callsign, item.status, item.updated_at, item.target_response_status, item.accepted_count, (item.phases || []).map(phase => [phase.id, phase.complete])]),
    exemptions: (state.data?.temporary_exemptions || []).map(item => [item.id, item.callsign, item.expires_at_epoch, item.reason]),
    summaryValues,
    label: state.consoleLabel,
  });
  if (!force && key === state.atcRenderKey && state.workspaceTab !== 'atc') return;
  state.atcRenderKey = key;

  if (!pilot) {
    host.innerHTML = atcVsoaRosterHtml(activeCases, assignments);
  } else {
    const targetAssignment = assignments.find(item => item.target_callsign === pilot.callsign) || null;
    const interceptorAssignment = assignments.find(item => item.interceptor_callsign === pilot.callsign) || null;
    const assignment = targetAssignment || interceptorAssignment;
    const operation = operationForCallsign(pilot.callsign);
    const responseControls = targetAssignment ? interceptResponseControlsHtml(targetAssignment) : operation
      ? interceptResponseControlsHtml({ target_callsign: pilot.callsign, target_response_status: operation.target_response_status || 'UNKNOWN', manual: false })
      : '<div class="intercept-contact-note">Open an intercept case to share target-response status.</div>';
    const nordoAction = pilot.manual_nordo ? 'clear' : 'mark';
    const automaticAlertId = pilot.automatic_alert_id || (pilot.auto_scramble_flag?.active ? pilot.alert_id : null);
    const canDismissAutomatic = Boolean(automaticAlertId && pilot.auto_scramble_flag?.active && !pilot.manual_nordo && !pilot.automatic_flag_dismissed);
    const recommendation = atcRecommendedAction(pilot, assignment, operation);
    const targetCallsign = targetAssignment?.target_callsign || operation?.callsign || (pilot.active_interceptors?.length ? pilot.callsign : null);
    const control = targetCallsign ? interceptControlForTarget(targetCallsign) : null;
    const assignmentSummary = assignment
      ? `<div class="atc-intercept-summary"><span>${interceptorAssignment ? 'SELECTED AIRCRAFT IS AN INTERCEPTOR' : 'ACTIVE INTERCEPT TARGET'}</span><strong>${escapeHtml(assignment.interceptor_callsign)} → ${escapeHtml(assignment.target_callsign)}</strong><small>${escapeHtml(formatInterceptEta(assignment))} · ${assignment.separation_nm ?? '—'} NM · ${escapeHtml(formatClosure(assignment))} · COURSE ${assignment.recommended_course_deg == null ? '—' : String(assignment.recommended_course_deg).padStart(3,'0') + '°'}</small></div>`
      : '';
    host.innerHTML = `<div class="atc-track-summary">
      ${atcOperatorDispatchHtml(pilot, assignments)}
      <div class="atc-next-action ${recommendation.level}"><span>NEXT ATC REVIEW ACTION</span><strong>${escapeHtml(recommendation.title)}</strong><small>${escapeHtml(recommendation.detail)}</small></div>
      <div class="atc-track-title"><span>LIVE TRACK</span><strong>${escapeHtml(pilot.callsign)}</strong><em>${escapeHtml(pilot.aircraft || pilot.aircraft_type || 'UNKNOWN')}</em></div>
      <div class="atc-track-metrics"><div><span>ALTITUDE</span><strong>${Number(pilot.altitude || 0).toLocaleString()} FT</strong></div><div><span>SPEED</span><strong>${pilot.groundspeed || 0} KT</strong></div><div><span>HEADING</span><strong>${String(normaliseHeading(pilot.heading)).padStart(3,'0')}°</strong></div><div><span>FLIGHT RULES</span><strong>${escapeHtml(pilot.flight_rules || '—')}</strong></div><div><span>VSOA MARKER</span><strong>${pilot.vsoa ? escapeHtml(vsoaMarkerLabel(pilot)) : 'NONE'}</strong><small>Visual marker only; does not verify membership or authorization.</small></div></div>
      <section class="atc-aircraft-details"><div class="atc-panel-heading"><span>AIRCRAFT COMMUNICATIONS & TRANSPONDER</span><small>Live reported values compared with the current ATC assignment.</small></div><div class="atc-aircraft-detail-grid">
        <div><span>REPORTED RADIO(S)</span><strong>${escapeHtml(formatPilotRadios(pilot))}</strong></div>
        <div><span>REPORTED ATC-CAPABLE RADIO(S)</span><strong>${escapeHtml(formatFreqs(pilot.atc_capable_reported_frequencies))}</strong></div>
        <div><span>EXPECTED CONTROLLER</span><strong>${escapeHtml(pilot.center || 'NONE')}</strong></div>
        <div><span>EXPECTED FREQUENCY</span><strong>${escapeHtml(formatFreqs(pilot.active_artcc_frequencies || pilot.center_frequencies))}</strong></div>
        <div><span>COMMUNICATIONS DECISION</span><strong>${escapeHtml(atcCommunicationsStatus(pilot))}</strong></div>
        <div><span>CURRENT SQUAWK</span><strong>${escapeHtml(pilot.squawk || '—')}</strong></div>
        <div><span>ASSIGNED SQUAWK</span><strong>${escapeHtml(pilot.assigned_squawk || '—')}</strong></div>
        <div><span>SQUAWK COMPARISON</span><strong class="${pilot.assigned_squawk && pilot.squawk !== pilot.assigned_squawk ? 'warning' : 'positive'}">${pilot.assigned_squawk ? (pilot.squawk === pilot.assigned_squawk ? 'MATCH' : 'MISMATCH') : 'NO ASSIGNMENT REPORTED'}</strong></div>
        <div><span>ROUTE</span><strong>${escapeHtml(pilot.departure || '—')} → ${escapeHtml(pilot.arrival || '—')}</strong></div>
      </div>${pilot.route ? `<div class="atc-filed-route"><span>FILED ROUTE</span><strong>${escapeHtml(routeText(pilot.route, 300))}</strong></div>` : ''}</section>
      ${atcDetectorDiagnosticsHtml(pilot)}
      ${atcEvidencePanelHtml(pilot, operation)}
      ${atcHandoffPanelHtml(pilot)}
      ${atcExemptionPanelHtml(pilot)}
      <section class="atc-controller-panel"><div class="atc-controller-heading"><span>LIVE CONTROLLER CANDIDATES</span><small>Coverage candidates used by the communications gate.</small></div><div class="atc-controller-list">${atcControllerRowsHtml(pilot)}</div></section>
      ${atcTimelinePanelHtml(operation)}
      ${assignmentSummary}
      <div class="atc-response-row"><div><span>TARGET RESPONSE</span><small>Manual operator observation shared across consoles.</small></div>${responseControls}</div>
      ${control && targetCallsign === pilot.callsign ? targetControlButtonsHtml(targetCallsign, control) : ''}
      <div class="atc-action-grid">
        <button type="button" data-atc-action="focus-map" data-callsign="${escapeHtml(pilot.callsign)}">FOCUS ON MAIN MAP</button>
        <button type="button" data-atc-action="target" data-callsign="${escapeHtml(pilot.callsign)}">SET AS INTERCEPT TARGET / UPDATE</button>
        <button type="button" data-atc-action="interceptor" data-callsign="${escapeHtml(pilot.callsign)}">USE AS INTERCEPTOR</button>
        <button type="button" class="${pilot.manual_nordo ? 'secondary' : 'danger'}" data-atc-action="${nordoAction}-nordo" data-callsign="${escapeHtml(pilot.callsign)}">${pilot.manual_nordo ? 'CLEAR MANUAL NORDO' : 'MARK AIRCRAFT NORDO · CONFIRM NOT RESPONDING / NORDO'}</button>
        <button type="button" data-atc-action="active-intercept" data-callsign="${escapeHtml(pilot.callsign)}">OPEN RELATED INTERCEPT</button>
        ${canDismissAutomatic ? `<button type="button" class="danger atc-dismiss-auto" data-dismiss-automatic-flag="${escapeHtml(automaticAlertId)}" data-callsign="${escapeHtml(pilot.callsign)}">DISMISS AUTOMATIC FLAG</button>` : ''}
      </div>
    </div>`;
  }

  casesHost.innerHTML = activeCases.length ? activeCases.map(operation => {
    const target = pilotForCallsign(operation.callsign) || {};
    const status = String(operation.target_response_status || 'UNKNOWN').toUpperCase();
    const related = assignments.filter(item => item.target_callsign === operation.callsign);
    const control = interceptControlForTarget(operation.callsign);
    return `<article class="atc-case-card">
      <header><div><span>${escapeHtml(operation.status || 'ACTIVE CASE')}</span><strong>${escapeHtml(operation.callsign)}</strong><small>${escapeHtml(target.aircraft || target.aircraft_type || 'UNKNOWN')} · ${Number(target.altitude || 0).toLocaleString()} FT · ${target.groundspeed || 0} KT</small></div><em class="contact-${status.toLowerCase().replaceAll('_','-')}">${escapeHtml(contactStatusLabel(status))}</em></header>
      <div class="atc-case-meta"><span>${related.length} INTERCEPTOR${related.length === 1 ? '' : 'S'}</span><span>${escapeHtml(atcCoordinationLabel(control.atc_coordination_status))}</span><span>${escapeHtml(interceptCommandLabel(control.command_status))}</span></div>
      <div class="atc-case-response">${interceptResponseControlsHtml({ target_callsign: operation.callsign, target_response_status: status, manual: false })}</div>
      ${operationActionsHtml(operation)}
      <div class="atc-case-buttons"><button type="button" class="atc-case-focus" data-atc-select-call="${escapeHtml(operation.callsign)}">LOAD IN ATC PANEL</button><button type="button" data-atc-open-intercept="${escapeHtml(operation.callsign)}">OPEN INTERCEPT MISSION</button></div>
    </article>`;
  }).join('') : '<div class="empty">NO ACTIVE ALERT CASES</div>';
  renderAtcOpsMap(force);
}

function atcRecommendedAction(pilot, assignment, operation) {
  if (!pilot) return { level: 'neutral', title: 'SELECT A TRACK', detail: 'Load an aircraft to review live communications and coordination data.' };
  if (pilot.manual_nordo) return { level: 'danger', title: 'NORDO MANUALLY CONFIRMED', detail: 'Coordinate on the active controller frequency, document attempts, and open or update the intercept case.' };
  if (pilot.automatic_flag_dismissed) return { level: 'neutral', title: 'AUTOMATIC FLAG DISMISSED', detail: `${pilot.automatic_flag_dismissal?.reason || 'Operator review completed'} · the possible NORDO watch remains visible until the underlying condition clears.` };
  if (pilot.mass_alert_verification_pending) return { level: 'warning', title: 'INDEPENDENT NORDO VERIFICATION IN PROGRESS', detail: `${pilot.mass_alert_verification?.stable_snapshots || 0}/${pilot.mass_alert_verification?.required_snapshots || 0} stable fresh snapshots confirmed. Automatic scramble escalation remains paused for this track only.` };
  if (pilot.temporary_exemption_active) return { level: 'positive', title: 'TEMPORARY EXEMPTION ACTIVE', detail: `${pilot.temporary_exemption_detail?.reason || 'Operator-approved suppression'} · automatic communications escalation is paused until expiry.` };
  if (pilot.frequency_change_grace_active) return { level: 'neutral', title: 'VERIFYING RECENT FREQUENCY CHANGE', detail: `${pilot.frequency_change_grace_remaining_seconds || 0} seconds remain in the stability grace period.` };
  if (pilot.communications_cooldown_active) return { level: 'positive', title: 'POST-HANDOFF COOLDOWN', detail: `${pilot.communications_cooldown_remaining_seconds || 0} seconds remain before a new mismatch case may open.` };
  if (pilot.active_artcc_frequency_match) return { level: 'positive', title: 'ACTIVE ATC FREQUENCY MATCHED', detail: 'The aircraft is reported on an active ARTCC frequency. Continue monitoring before treating the track as NORDO.' };
  if (pilot.online_center_handoff) return { level: 'positive', title: 'CENTER HANDOFF VERIFIED', detail: `The reported radio matches ${pilot.online_center_handoff_detail?.downstream_controller || 'the online downstream Center'}, and the projected track crosses into that ARTCC within the 80 NM handoff window.` };
  if (pilot.advisory_frequency_whitelisted || pilot.early_unicom_handoff) return { level: 'positive', title: 'ADVISORY FREQUENCY SUPPRESSION ACTIVE', detail: 'The current radio state is being treated as an allowed CTAF/UNICOM or early-handoff condition.' };
  if (pilot.nordo_gate_ready && pilot.frequency_mismatch_active) return { level: 'warning', title: 'COMMUNICATIONS CHECK REQUIRED', detail: 'The live coverage and frequency gates are met. Attempt contact and verify the assigned controller before confirming NORDO.' };
  if (assignment) return { level: 'warning', title: `INTERCEPT ${interceptCommandLabel(interceptControlForTarget(assignment.target_callsign).command_status)}`, detail: `Track the assigned interceptors and keep ATC coordination status current for ${assignment.target_callsign}.` };
  if (operation) return { level: 'warning', title: 'ACTIVE ALERT CASE', detail: 'Review the case phases, target response status, and whether an intercept assignment is required.' };
  return { level: 'neutral', title: 'MONITOR LIVE TRACK', detail: 'No high-confidence NORDO or active intercept state is currently attached to this aircraft.' };
}

function atcControllerRowsHtml(pilot) {
  const rows = Array.isArray(pilot?.controller_candidates) ? pilot.controller_candidates.slice(0, 6) : [];
  if (!rows.length) return '<div class="atc-controller-empty">NO QUALIFYING LIVE CONTROLLER COVERAGE</div>';
  return rows.map(item => `<div class="atc-controller-row"><strong>${escapeHtml(item.callsign || 'ATC')}</strong><span>${escapeHtml(item.facility || '—')} · ${escapeHtml(formatFreqs(item.frequencies))}</span><small>${Number(item.distance_nm || 0).toFixed(1)} NM · ${escapeHtml(item.coverage_confidence || item.match_quality || 'LIVE')}</small></div>`).join('');
}

function interceptMapCoordinate(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function interceptMapTrackPosition(track) {
  const lat = interceptMapCoordinate(track?.lat);
  const lon = interceptMapCoordinate(track?.lon);
  return lat == null || lon == null ? null : [lat, lon];
}

function ensureAtcOpsMap() {
  const host = el('atc-map');
  if (!host) return null;
  if (atcOpsMap) return atcOpsMap;
  atcOpsMap = L.map(host, {
    zoomControl: false,
    minZoom: 3,
    maxZoom: 16,
    preferCanvas: true,
    worldCopyJump: true,
    zoomAnimation: true,
    fadeAnimation: false,
    markerZoomAnimation: false,
  }).setView([38.5, -97], 4);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 16,
    className: 'basemap-atc-scope',
    attribution: 'Basemap &copy; Esri, HERE, Garmin, and contributors',
    updateWhenIdle: true,
    keepBuffer: 2,
  }).addTo(atcOpsMap);
  L.control.zoom({ position: 'bottomright' }).addTo(atcOpsMap);
  return atcOpsMap;
}

function relatedAssignmentsForAtcPilot(pilot) {
  if (!pilot) return [];
  return activeInterceptAssignments().filter(item => item.target_callsign === pilot.callsign || item.interceptor_callsign === pilot.callsign);
}

function renderAtcOpsMap(forceFit = false) {
  const atcMap = ensureAtcOpsMap();
  const statusHost = el('atc-map-status');
  if (!atcMap) return;
  const selectedPilot = atcSelectedPilot();
  const operatorPilot = operatorAircraftPilot();
  const pilot = selectedPilot || operatorPilot;
  const assignments = relatedAssignmentsForAtcPilot(pilot);
  const controllers = (state.data?.controllers || []).filter(item => Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lon)));
  const nearbyControllers = pilot
    ? controllers.map(item => ({ ...item, distance: distanceNmBetween(pilot, item) })).sort((a, b) => a.distance - b.distance).slice(0, 8)
    : [];
  const renderKey = compactJson({
    feed: state.data?.feed_sequence,
    pilot: selectedPilot ? [selectedPilot.callsign, selectedPilot.lat, selectedPilot.lon, selectedPilot.heading, selectedPilot.altitude, selectedPilot.groundspeed] : null,
    operator: operatorPilot ? [operatorPilot.callsign, operatorPilot.lat, operatorPilot.lon, operatorPilot.heading, operatorPilot.altitude, operatorPilot.groundspeed] : null,
    assignments: assignments.map(item => [item.interceptor_callsign, item.target_callsign, item.intercept_point_lat, item.intercept_point_lon, item.updated_at, item.live]),
    controllers: nearbyControllers.map(item => [item.callsign, item.lat, item.lon, item.frequency]),
    handoff: pilot?.online_center_handoff_detail || null,
  });
  if (!forceFit && renderKey === state.atcMapRenderKey) return;
  state.atcMapRenderKey = renderKey;
  if (atcOpsLayerGroup) atcMap.removeLayer(atcOpsLayerGroup);
  const layers = [];
  const bounds = [];
  const selectedPosition = interceptMapTrackPosition(selectedPilot);
  const operatorPosition = interceptMapTrackPosition(operatorPilot);
  if (selectedPosition) {
    bounds.push(selectedPosition);
    const marker = L.circleMarker(selectedPosition, { radius: 8, color: '#ffab52', weight: 3, fillColor: '#ffab52', fillOpacity: 0.2 });
    marker.bindTooltip(`${escapeHtml(selectedPilot.callsign)} · TARGET`, { permanent: true, direction: 'top', className: 'intercept-map-track-label atc-map-selected-label' });
    marker.bindPopup(`<strong>${escapeHtml(selectedPilot.callsign)}</strong><br>${Number(selectedPilot.altitude || 0).toLocaleString()} FT · ${selectedPilot.groundspeed || 0} KT · HDG ${String(normaliseHeading(selectedPilot.heading)).padStart(3,'0')}°<br>${escapeHtml(atcCommunicationsStatus(selectedPilot))}`);
    layers.push(marker);
  }
  if (operatorPosition && (!selectedPilot || operatorPilot.callsign !== selectedPilot.callsign)) {
    bounds.push(operatorPosition);
    const marker = L.circleMarker(operatorPosition, { radius: 7, color: '#c79cff', weight: 3, fillColor: '#c79cff', fillOpacity: 0.2 });
    marker.bindTooltip(`${escapeHtml(operatorPilot.callsign)} · MY VSOA AIRCRAFT`, { permanent: true, direction: 'bottom', className: 'intercept-map-track-label atc-map-operator-label' });
    marker.bindPopup(`<strong>${escapeHtml(operatorPilot.callsign)} · MY VSOA AIRCRAFT</strong><br>${Number(operatorPilot.altitude || 0).toLocaleString()} FT · ${operatorPilot.groundspeed || 0} KT · HDG ${String(normaliseHeading(operatorPilot.heading)).padStart(3,'0')}°<br>${escapeHtml(operatorPilot.vsoa_label || 'VSOA REMARKS')}`);
    layers.push(marker);
    const operatorAssignment = assignments.find(item => item.interceptor_callsign === operatorPilot.callsign && selectedPilot && item.target_callsign === selectedPilot.callsign);
    if (selectedPosition && !operatorAssignment) {
      layers.push(L.polyline([operatorPosition, selectedPosition], { color: '#c79cff', weight: 1.8, opacity: 0.78, dashArray: '6 8' })
        .bindTooltip(`PENDING ASSIGNMENT · ${distanceNmBetween(operatorPilot, selectedPilot).toFixed(1)} NM`, { direction: 'center', className: 'intercept-map-track-label atc-map-operator-label' }));
    }
  }
  const handoff = pilot?.online_center_handoff_detail || null;
  if (selectedPosition && handoff) {
    const handoffLat = interceptMapCoordinate(handoff.projected_lat);
    const handoffLon = interceptMapCoordinate(handoff.projected_lon);
    if (handoffLat != null && handoffLon != null) {
      const handoffPoint = [handoffLat, handoffLon];
      bounds.push(handoffPoint);
      layers.push(L.polyline([selectedPosition, handoffPoint], { color: '#6ee7a0', weight: 2.4, opacity: 0.95, dashArray: '9 6' }));
      layers.push(L.circleMarker(handoffPoint, { radius: 6, color: '#6ee7a0', weight: 2.5, fillColor: '#071217', fillOpacity: 0.96 })
        .bindTooltip(`${escapeHtml(handoff.current_artcc || 'CURRENT')} → ${escapeHtml(handoff.downstream_artcc || handoff.downstream_controller || 'NEXT')} · HANDOFF`, { permanent: true, direction: 'right', className: 'intercept-map-track-label atc-handoff-map-label' })
        .bindPopup(`<strong>VERIFIED CENTER HANDOFF</strong><br>${escapeHtml(handoff.current_controller || handoff.current_artcc || 'CURRENT')} → ${escapeHtml(handoff.downstream_controller || handoff.downstream_artcc || 'DOWNSTREAM')}<br>${Number(handoff.boundary_distance_nm || 0).toFixed(1)} NM TO BOUNDARY · ${escapeHtml(formatFreqs(handoff.matched_frequencies))}`));
    }
  }
  for (const controller of nearbyControllers) {
    const position = [Number(controller.lat), Number(controller.lon)];
    bounds.push(position);
    const marker = L.circleMarker(position, { radius: 4, color: '#71f6ff', weight: 1.5, fillColor: '#071217', fillOpacity: 0.85 });
    marker.bindTooltip(`${escapeHtml(controller.callsign)} · ${escapeHtml(formatFreqs(controller.frequencies || [controller.frequency]))}`, { direction: 'top', className: 'intercept-map-track-label atc-controller-map-label' });
    marker.bindPopup(`<strong>${escapeHtml(controller.callsign)}</strong><br>${escapeHtml(controller.facility || 'ATC')} · ${escapeHtml(formatFreqs(controller.frequencies || [controller.frequency]))}<br>${Number(controller.distance || 0).toFixed(1)} NM FROM SELECTED TRACK`);
    layers.push(marker);
  }
  for (const assignment of assignments) {
    const target = pilotForCallsign(assignment.target_callsign) || assignment.target || null;
    const interceptor = pilotForCallsign(assignment.interceptor_callsign) || assignment.interceptor || null;
    const targetPosition = interceptMapTrackPosition(target);
    const interceptorPosition = interceptMapTrackPosition(interceptor);
    const pointLat = interceptMapCoordinate(assignment.intercept_point_lat);
    const pointLon = interceptMapCoordinate(assignment.intercept_point_lon);
    const pointPosition = pointLat == null || pointLon == null ? null : [pointLat, pointLon];
    if (targetPosition && (!pilot || target?.callsign !== pilot.callsign)) {
      bounds.push(targetPosition);
      layers.push(L.circleMarker(targetPosition, { radius: 7, color: '#ff5252', weight: 2.5, fillColor: '#ff5252', fillOpacity: 0.16 }).bindTooltip(`${escapeHtml(assignment.target_callsign)} · TARGET`, { permanent: true, direction: 'top', className: 'intercept-map-track-label' }));
    }
    if (interceptorPosition && (!pilot || interceptor?.callsign !== pilot.callsign)) {
      bounds.push(interceptorPosition);
      layers.push(L.circleMarker(interceptorPosition, { radius: 6, color: '#ffe36d', weight: 2.5, fillColor: '#ffe36d', fillOpacity: 0.16 }).bindTooltip(`${escapeHtml(assignment.interceptor_callsign)} · ${escapeHtml(formatInterceptEta(assignment))}`, { permanent: true, direction: 'bottom', className: 'intercept-map-track-label' }));
    }
    if (pointPosition) {
      bounds.push(pointPosition);
      layers.push(L.circleMarker(pointPosition, { radius: 5, color: '#71f6ff', weight: 2.5, fillColor: '#071217', fillOpacity: 0.95 }).bindTooltip(`INTERCEPT POINT · ${escapeHtml(formatInterceptEta(assignment))}`, { permanent: true, direction: 'right', className: 'intercept-map-track-label intercept-map-point-label' }));
      if (interceptorPosition) layers.push(L.polyline([interceptorPosition, pointPosition], { color: '#ffe36d', weight: 2.4, opacity: 0.92 }));
      if (targetPosition) layers.push(L.polyline([targetPosition, pointPosition], { color: '#ff5252', weight: 1.7, opacity: 0.8, dashArray: '8 7' }));
    }
  }
  atcOpsLayerGroup = L.layerGroup(layers).addTo(atcMap);
  const fitKey = compactJson([selectedPilot?.callsign, operatorPilot?.callsign, assignments.map(item => [item.interceptor_callsign, item.target_callsign]), nearbyControllers.map(item => item.callsign)]);
  if (bounds.length && (forceFit || state.atcMapFitKey !== fitKey)) {
    state.atcMapFitKey = fitKey;
    atcMap.fitBounds(L.latLngBounds(bounds), { padding: [34, 34], maxZoom: assignments.length ? 9 : 8, animate: false });
  } else if (!bounds.length) {
    atcMap.setView([38.5, -97], 4, { animate: false });
  }
  if (statusHost) {
    statusHost.textContent = pilot
      ? `${selectedPilot?.callsign || operatorPilot?.callsign}${operatorPilot ? ` · MY AIRCRAFT ${operatorPilot.callsign}` : ''} · ${nearbyControllers.length} NEARBY ATC POSITION${nearbyControllers.length === 1 ? '' : 'S'} · ${assignments.length} RELATED INTERCEPT${assignments.length === 1 ? '' : 'S'}${pilot.online_center_handoff ? ' · HANDOFF VERIFIED' : ''} · UPDATED ${formatZulu(state.data?.feed_updated_at || state.data?.updated_at)}`
      : 'Select an aircraft to show its track, controllers, interceptors, and predicted intercept points.';
  }
}

function selectNearestInterceptors(limit = 3) {
  const target = activeTargetForBuilder();
  if (!target) return setInterceptBatchFeedback('Select a live target aircraft first.', 'error');
  state.multiInterceptorSelection.clear();
  const available = rankedInterceptorCandidates(target).filter(item => item.assignedTarget !== target.callsign);
  for (const item of available.slice(0, Math.max(1, limit))) state.multiInterceptorSelection.add(item.pilot.callsign);
  renderMultiInterceptorCandidates();
  setInterceptBatchFeedback(`${state.multiInterceptorSelection.size} closest available interceptor${state.multiInterceptorSelection.size === 1 ? '' : 's'} selected.`, 'success');
}

async function assignBestVsoaInterceptor() {
  const target = activeTargetForBuilder();
  if (!target) return setInterceptBatchFeedback('Select a live target aircraft first.', 'error');
  const candidate = rankedInterceptorCandidates(target).find(item => item.pilot.vsoa && item.assignedTarget !== target.callsign)
    || rankedInterceptorCandidates(target).find(item => item.assignedTarget !== target.callsign);
  if (!candidate) return setInterceptBatchFeedback('No available airborne interceptor was found.', 'error');
  state.multiInterceptorSelection = new Set([candidate.pilot.callsign]);
  renderMultiInterceptorCandidates();
  await assignSelectedInterceptors();
}

function normaliseCallsign(value) {
  return String(value || '').trim().toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 32);
}

function loadConsoleIdentity() {
  try {
    let id = localStorage.getItem('vng-adoc.console-id');
    if (!id) {
      id = (globalThis.crypto?.randomUUID?.() || `console-${Date.now()}-${Math.random().toString(16).slice(2)}`);
      localStorage.setItem('vng-adoc.console-id', id);
    }
    state.consoleId = id;
    state.consoleLabel = localStorage.getItem('vng-adoc.console-label') || `CONSOLE ${id.slice(0, 6).toUpperCase()}`;
    state.operatorAircraftCallsign = normaliseCallsign(localStorage.getItem('vng-adoc.operator-aircraft') || '');
    localStorage.setItem('vng-adoc.console-label', state.consoleLabel);
  } catch (_) {
    state.consoleId = `console-${Date.now()}`;
    state.consoleLabel = `CONSOLE ${state.consoleId.slice(-6).toUpperCase()}`;
  }
}

function operationAcceptedByThisConsole(operation) {
  return Boolean(operation?.accepted_console_list?.some(item => item.console_id === state.consoleId));
}

function compactJson(value) {
  try { return JSON.stringify(value); } catch (_) { return String(value ?? ''); }
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 12000) {
  const timeoutController = new AbortController();
  const timer = setTimeout(() => timeoutController.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: timeoutController.signal });
  } finally {
    clearTimeout(timer);
  }
}

function applySavedLayout() {
  const shell = document.querySelector('.shell');
  const root = document.documentElement;
  try {
    const railWidth = Math.max(320, Math.min(720, Number(localStorage.getItem('vng-adoc.rail-width')) || 390));
    state.railWidth = railWidth;
    root.style.setProperty('--rail-width', `${railWidth}px`);
    const maxPanelHeight = Math.max(180, Math.floor(window.innerHeight * 0.72));
    for (const panel of document.querySelectorAll('[data-panel-key]')) {
      const key = panel.dataset.panelKey;
      const saved = Number(localStorage.getItem(`vng-adoc.panel-height.${key}`));
      if (saved > 80) panel.style.height = `${Math.min(maxPanelHeight, Math.max(96, saved))}px`;
    }
    const storedLegend = localStorage.getItem('vng-adoc.map-legend-expanded');
    state.legendExpanded = storedLegend === null ? true : storedLegend === 'true';
  } catch (_) { /* storage unavailable */ }
  if (shell) shell.dataset.layoutReady = 'true';
  setMapLegendExpanded(state.legendExpanded, false);
  setTimeout(() => map.invalidateSize(false), 0);
}


function clampResizablePanels() {
  const maxPanelHeight = Math.max(180, Math.floor(window.innerHeight * 0.72));
  for (const panel of document.querySelectorAll('[data-panel-key]')) {
    const current = panel.getBoundingClientRect().height;
    if (current > maxPanelHeight) panel.style.height = `${maxPanelHeight}px`;
  }
}

function setMapLegendExpanded(expanded, persist = true) {
  state.legendExpanded = Boolean(expanded);
  const legend = el('map-legend');
  const button = el('toggle-map-legend');
  if (legend) legend.hidden = !state.legendExpanded;
  if (button) {
    button.textContent = state.legendExpanded ? 'HIDE LEGEND' : 'SHOW LEGEND';
    button.setAttribute('aria-expanded', String(state.legendExpanded));
  }
  if (persist) {
    try { localStorage.setItem('vng-adoc.map-legend-expanded', String(state.legendExpanded)); } catch (_) {}
  }
}

function initializeResizableLayout() {
  const resizer = el('rail-resizer');
  if (resizer) {
    const resizeTo = clientX => {
      const width = Math.max(320, Math.min(720, window.innerWidth - clientX));
      state.railWidth = width;
      document.documentElement.style.setProperty('--rail-width', `${width}px`);
      try { localStorage.setItem('vng-adoc.rail-width', String(Math.round(width))); } catch (_) {}
      map.invalidateSize(false);
    };
    resizer.addEventListener('pointerdown', event => {
      event.preventDefault();
      resizer.setPointerCapture(event.pointerId);
      document.body.classList.add('resizing-layout');
      const move = moveEvent => resizeTo(moveEvent.clientX);
      const up = () => {
        resizer.removeEventListener('pointermove', move);
        document.body.classList.remove('resizing-layout');
      };
      resizer.addEventListener('pointermove', move);
      resizer.addEventListener('pointerup', up, { once: true });
      resizer.addEventListener('pointercancel', up, { once: true });
    });
    resizer.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      event.preventDefault();
      const delta = event.key === 'ArrowLeft' ? 20 : -20;
      const width = Math.max(320, Math.min(720, state.railWidth + delta));
      state.railWidth = width;
      document.documentElement.style.setProperty('--rail-width', `${width}px`);
      try { localStorage.setItem('vng-adoc.rail-width', String(width)); } catch (_) {}
      map.invalidateSize(false);
    });
  }

  if ('ResizeObserver' in window) {
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        const panel = entry.target;
        if (!panel.dataset.panelKey || entry.contentRect.height < 80) continue;
        try { localStorage.setItem(`vng-adoc.panel-height.${panel.dataset.panelKey}`, String(Math.round(entry.contentRect.height))); } catch (_) {}
      }
    });
    document.querySelectorAll('[data-panel-key]').forEach(panel => observer.observe(panel));
  }
}

function resetLayout() {
  try {
    localStorage.removeItem('vng-adoc.rail-width');
    ['metrics', 'alerts'].forEach(key => localStorage.removeItem(`vng-adoc.panel-height.${key}`));
  } catch (_) {}
  document.documentElement.style.setProperty('--rail-width', '390px');
  state.railWidth = 390;
  document.querySelectorAll('[data-panel-key]').forEach(panel => { panel.style.height = ''; });
  map.invalidateSize(false);
}

function pilotVisualSeverity(pilot) {
  if (pilot?.manual_nordo) return 'red';
  if (pilot?.active_intercept) return 'yellow';
  if (pilot?.nordo_watch?.level) return pilot.nordo_watch.level;
  return pilot?.track_color || pilot?.severity || 'green';
}

function pilotVisualColor(pilot) {
  const visual = pilotVisualSeverity(pilot);
  if (state.basemap === 'atc-scope' && visual === 'green') return '#55d96a';
  return severityColor[visual] || severityColor.green;
}

const pathRenderer = L.canvas({ padding: 0.45, tolerance: 8 });
const map = L.map('map', {
  zoomControl: false,
  minZoom: 3,
  preferCanvas: true,
  worldCopyJump: true,
  zoomAnimation: true,
  fadeAnimation: false,
  markerZoomAnimation: false,
}).setView([38.5, -97], 4);

map.createPane('satelliteLabels');
map.getPane('satelliteLabels').style.zIndex = 210;
map.createPane('scopeGrid');
map.getPane('scopeGrid').style.zIndex = 235;
map.createPane('centerReference');
map.getPane('centerReference').style.zIndex = 245;
map.createPane('atcCoverage');
map.getPane('atcCoverage').style.zIndex = 260;
map.createPane('atcLabels');
map.getPane('atcLabels').style.zIndex = 275;
map.getPane('atcLabels').style.pointerEvents = 'none';
map.createPane('specialUseAirspace');
map.getPane('specialUseAirspace').style.zIndex = 290;
map.createPane('monitoredZones');
map.getPane('monitoredZones').style.zIndex = 320;
map.createPane('dcaHeliRoutes');
map.getPane('dcaHeliRoutes').style.zIndex = 345;
map.createPane('flightPlanPreview');
map.getPane('flightPlanPreview').style.zIndex = 470;
map.createPane('interceptPaths');
map.getPane('interceptPaths').style.zIndex = 520;
map.createPane('aircraft');
map.getPane('aircraft').style.zIndex = 650;
map.createPane('hoverCards');
map.getPane('hoverCards').style.zIndex = 1600;
map.getPane('hoverCards').style.pointerEvents = 'none';

L.control.zoom({ position: 'bottomright' }).addTo(map);

const basemapDefinitions = {
  'dark-satellite': {
    label: 'DARK SATELLITE',
    layers: [
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        className: 'basemap-dark-satellite',
        attribution: 'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
        updateWhenIdle: true,
        keepBuffer: 3,
      }),
      L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        pane: 'satelliteLabels',
        className: 'basemap-dark-satellite-labels',
        attribution: 'Reference labels &copy; Esri',
        updateWhenIdle: true,
        keepBuffer: 3,
      }),
    ],
  },
  satellite: {
    label: 'STANDARD SATELLITE',
    layers: [
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        className: 'basemap-standard-satellite',
        attribution: 'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
        updateWhenIdle: true,
        keepBuffer: 3,
      }),
      L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        pane: 'satelliteLabels',
        className: 'basemap-standard-labels',
        attribution: 'Reference labels &copy; Esri',
        updateWhenIdle: true,
        keepBuffer: 3,
      }),
    ],
  },
  'dark-gray': {
    label: 'DARK GRAY',
    layers: [
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 16,
        className: 'basemap-dark-gray',
        attribution: 'Basemap &copy; Esri, HERE, Garmin, and contributors',
        updateWhenIdle: true,
        keepBuffer: 3,
      }),
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 16,
        pane: 'satelliteLabels',
        className: 'basemap-dark-gray-labels',
        attribution: 'Reference &copy; Esri',
        updateWhenIdle: true,
        keepBuffer: 3,
      }),
    ],
  },
  topographic: {
    label: 'TACTICAL TOPOGRAPHIC',
    layers: [
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        className: 'basemap-tactical-topographic',
        attribution: 'Basemap &copy; Esri and contributors',
        updateWhenIdle: true,
        keepBuffer: 3,
      }),
    ],
  },
  'atc-scope': {
    label: 'ATC SCOPE',
    layers: [
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 16,
        className: 'basemap-atc-scope',
        attribution: 'Faint geographic reference &copy; Esri, HERE, Garmin, and contributors',
        updateWhenIdle: true,
        keepBuffer: 3,
      }),
    ],
  },
};

let activeBasemapLayers = [];

function loadBasemapPreference() {
  try {
    const stored = localStorage.getItem('vng-adoc.basemap');
    if (stored && basemapDefinitions[stored]) return stored;
  } catch (_) { /* browser storage unavailable */ }
  return 'dark-satellite';
}

function destinationLatLng(lat, lon, bearingDeg, distanceNm) {
  const radiusNm = 3440.065;
  const angular = distanceNm / radiusNm;
  const bearing = bearingDeg * Math.PI / 180;
  const lat1 = lat * Math.PI / 180;
  const lon1 = lon * Math.PI / 180;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angular)
    + Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing)
  );
  const lon2 = lon1 + Math.atan2(
    Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1),
    Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2),
  );
  return [lat2 * 180 / Math.PI, ((lon2 * 180 / Math.PI + 540) % 360) - 180];
}

function scopeRangeNm() {
  const center = map.getCenter();
  const bounds = map.getBounds();
  const edge = L.latLng(center.lat, bounds.getEast());
  const halfWidthNm = Math.max(5, map.distance(center, edge) / 1852);
  const candidates = [5, 10, 20, 40, 80, 160, 320, 640, 1280, 2560];
  return candidates.find(value => value >= halfWidthNm * 0.92) || 2560;
}

function updateScopeGrid() {
  if (scopeGridLayerGroup) {
    map.removeLayer(scopeGridLayerGroup);
    scopeGridLayerGroup = null;
  }
  if (state.basemap !== 'atc-scope') return;

  const center = map.getCenter();
  const outerRange = scopeRangeNm();
  const ringRanges = [0.25, 0.5, 0.75, 1].map(value => outerRange * value);
  const bounds = map.getBounds();
  const layers = [];
  const ringStyle = {
    pane: 'scopeGrid',
    renderer: pathRenderer,
    color: '#405248',
    weight: 1,
    opacity: 0.74,
    fill: false,
    dashArray: '7 8',
    interactive: false,
  };

  for (const range of ringRanges) {
    layers.push(L.circle(center, { ...ringStyle, radius: range * 1852 }));
    const labelPoint = destinationLatLng(center.lat, center.lng, 52, range);
    layers.push(L.marker(labelPoint, {
      pane: 'scopeGrid',
      interactive: false,
      keyboard: false,
      icon: L.divIcon({
        className: '',
        iconSize: [54, 18],
        iconAnchor: [27, 9],
        html: `<div class="scope-range-label">${Math.round(range)}</div>`,
      }),
    }));
  }

  layers.push(L.polyline([[center.lat, bounds.getWest()], [center.lat, bounds.getEast()]], {
    pane: 'scopeGrid', renderer: pathRenderer, color: '#284032', weight: 1, opacity: 0.72, dashArray: '3 9', interactive: false,
  }));
  layers.push(L.polyline([[bounds.getSouth(), center.lng], [bounds.getNorth(), center.lng]], {
    pane: 'scopeGrid', renderer: pathRenderer, color: '#284032', weight: 1, opacity: 0.72, dashArray: '3 9', interactive: false,
  }));

  layers.push(L.marker(center, {
    pane: 'scopeGrid',
    interactive: false,
    keyboard: false,
    icon: L.divIcon({ className: '', iconSize: [28, 28], iconAnchor: [14, 14], html: '<div class="scope-center-crosshair"></div>' }),
  }));

  scopeGridLayerGroup = L.layerGroup(layers).addTo(map);
}

function setBasemap(name, persist = true) {
  const selected = basemapDefinitions[name] ? name : 'dark-satellite';
  for (const layer of activeBasemapLayers) {
    if (map.hasLayer(layer)) map.removeLayer(layer);
  }
  activeBasemapLayers = basemapDefinitions[selected].layers;
  for (const layer of activeBasemapLayers) layer.addTo(map);
  state.basemap = selected;
  const panel = document.querySelector('.map-panel');
  if (panel) panel.dataset.basemap = selected;
  const selector = el('basemap-select');
  if (selector) selector.value = selected;
  if (persist) {
    try { localStorage.setItem('vng-adoc.basemap', selected); } catch (_) { /* browser storage unavailable */ }
  }
  updateScopeGrid();
  if (state.centerBoundaryData.length) renderCenterBoundaries(state.centerBoundaryData, state.centerBoundaryRevision, true);
  if (state.atcCoverageData.length) renderAtcCoverage(state.atcCoverageData, state.atcRevision, true);
  if (state.suaData.length) renderSua(state.suaData);
  renderAircraft(state.data?.pilots || [], true);
  if (state.selectedCallsign) renderFlightPlanPreview(state.selectedCallsign);
  map.invalidateSize(false);
}

setBasemap(loadBasemapPreference(), false);

function loadMapControlsPreference() {
  try {
    const stored = localStorage.getItem('vng-adoc.map-controls-expanded');
    return stored === null ? true : stored === 'true';
  } catch (_) {
    return true;
  }
}

function setMapControlsExpanded(expanded, persist = true) {
  state.mapControlsExpanded = Boolean(expanded);
  const toolbar = el('map-toolbar');
  const button = el('toggle-map-controls');
  if (toolbar) toolbar.hidden = !state.mapControlsExpanded;
  if (button) {
    button.setAttribute('aria-expanded', String(state.mapControlsExpanded));
    button.textContent = state.mapControlsExpanded ? 'HIDE MAP OPTIONS' : 'SHOW MAP OPTIONS';
  }
  if (!state.mapControlsExpanded) setMapMenuPanel(null);
  if (persist) {
    try { localStorage.setItem('vng-adoc.map-controls-expanded', String(state.mapControlsExpanded)); } catch (_) { /* unavailable */ }
  }
  setTimeout(() => map.invalidateSize(false), 0);
}


function setMapMenuPanel(name) {
  const selected = ['layers', 'regions', 'tools'].includes(name) ? name : null;
  document.querySelectorAll('[data-map-menu-panel]').forEach(panel => {
    panel.hidden = panel.dataset.mapMenuPanel !== selected;
  });
  document.querySelectorAll('[data-map-menu]').forEach(button => {
    const active = button.dataset.mapMenu === selected;
    button.classList.toggle('active', active);
    button.setAttribute('aria-expanded', String(active));
  });
  setTimeout(() => map.invalidateSize(false), 0);
}

setMapControlsExpanded(loadMapControlsPreference(), false);

const regionViews = {
  conus: { center: [38.5, -97], zoom: 4 },
  alaska: { center: [64.2, -152.5], zoom: 4 },
  hawaii: { center: [20.8, -157.4], zoom: 6 },
  territories: { bounds: [[-15.5, -173], [22.5, 147]] },
  canada: { center: [57.0, -106.0], zoom: 3 },
  france: { bounds: [[41.0, -5.8], [51.5, 9.8]] },
  'all-us': { bounds: [[-15.5, -180], [72.5, 147]] },
  'north-america': { bounds: [[17.0, -170.0], [84.5, -45.0]] },
};

function setRegionView(name) {
  const view = regionViews[name] || regionViews.conus;
  document.querySelectorAll('.region').forEach(button => {
    button.classList.toggle('active', button.dataset.region === name);
  });
  if (view.bounds) map.fitBounds(view.bounds, { padding: [18, 18], animate: false });
  else map.setView(view.center, view.zoom, { animate: false });
}

function operationalRegionOf(item) {
  const explicit = String(item?.region || item?.country || '').toUpperCase();
  if (explicit) return explicit;
  const boundary = String(item?.boundary_id || item?.parent_boundary_id || item?.callsign || '').toUpperCase();
  if (boundary.startsWith('LF')) return 'FRANCE';
  if (boundary.startsWith('CZ')) return 'CANADA';
  return 'UNITED STATES';
}

function matchesOperationalRegion(item) {
  const region = operationalRegionOf(item);
  if (state.operationalRegionFilter === 'france') return region === 'FRANCE';
  if (state.operationalRegionFilter === 'north-america') return region !== 'FRANCE';
  return true;
}

function setOperationalRegionFilter(name) {
  state.operationalRegionFilter = ['all', 'north-america', 'france'].includes(name) ? name : 'all';
  document.querySelectorAll('.region-filter').forEach(button => {
    const active = button.dataset.regionFilter === state.operationalRegionFilter;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  renderAircraft(state.data?.pilots || [], true);
  renderBases(state.bases || [], true);
  if (state.atcCoverageData.length) renderAtcCoverage(state.atcCoverageData, state.atcRevision, true);
}

function tickClock() {
  el('zulu-clock').textContent = new Date().toISOString().slice(11, 19) + 'Z';
  updateInterceptRecalcStatus();
  if (!state.data) return;
  const stale = updateFeedStaleState(state.data);
  const feedAgeMetric = el('metric-feed-age');
  if (feedAgeMetric) {
    feedAgeMetric.textContent = Number.isFinite(stale.age) ? `${Math.floor(stale.age)}s` : '—';
    feedAgeMetric.className = stale.critical ? 'stale' : stale.warning ? 'warning' : '';
  }
}
setInterval(tickClock, 1000);
tickClock();

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function normaliseHeading(value) {
  return Math.round(Number(value || 0)) % 360;
}

function bearingBetween(lat1, lon1, lat2, lon2) {
  const p1 = Number(lat1) * Math.PI / 180;
  const p2 = Number(lat2) * Math.PI / 180;
  const deltaLon = (Number(lon2) - Number(lon1)) * Math.PI / 180;
  const y = Math.sin(deltaLon) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(deltaLon);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

function updateAircraftTrackHistory(pilot) {
  const lat = Number(pilot?.lat);
  const lon = Number(pilot?.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || !pilot?.callsign) return;
  const now = Date.now();
  const history = aircraftTrackHistory.get(pilot.callsign) || [];
  const last = history.at(-1);
  const movedNm = last ? map.distance([last.lat, last.lon], [lat, lon]) / 1852 : Infinity;
  if (!last || movedNm >= 0.08 || now - last.time >= 60000) {
    history.push({ lat, lon, altitude: Number(pilot.altitude || 0), time: now });
  }
  // Shared server history is authoritative. Keep only a short local buffer
  // so hundreds of tracks do not accumulate thousands of browser objects.
  const cutoff = now - 15 * 60 * 1000;
  while (history.length > 30 || (history[0] && history[0].time < cutoff)) history.shift();
  aircraftTrackHistory.set(pilot.callsign, history);
}

function normalizedTrackHistory(callsign) {
  const serverRecord = serverTrackHistory.get(callsign);
  const server = (serverRecord?.points || []).map(point => ({
    lat: Number(point.lat),
    lon: Number(point.lon),
    altitude: Number(point.altitude || 0),
    time: Number(point.time || 0) * 1000,
  })).filter(point => Number.isFinite(point.lat) && Number.isFinite(point.lon));
  const local = aircraftTrackHistory.get(callsign) || [];
  const merged = [...server, ...local].sort((a, b) => a.time - b.time);
  const result = [];
  for (const point of merged) {
    const last = result.at(-1);
    if (last && Math.abs(point.time - last.time) < 5000 && map.distance([last.lat, last.lon], [point.lat, point.lon]) < 100) continue;
    result.push(point);
  }
  return result.slice(-180);
}

async function fetchTrackHistory(callsign, force = false) {
  if (!callsign) return [];
  const cached = serverTrackHistory.get(callsign);
  if (!force && cached && Date.now() - cached.fetchedAt < 15000) return cached.points || [];
  if (trackHistoryRequests.has(callsign)) return trackHistoryRequests.get(callsign);
  const request = fetchWithTimeout(`/api/tracks/${encodeURIComponent(callsign)}/history?ts=${Date.now()}`, { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error(`Track history ${response.status}`);
      return response.json();
    })
    .then(payload => {
      const points = Array.isArray(payload.points) ? payload.points : [];
      serverTrackHistory.set(callsign, { points, fetchedAt: Date.now() });
      if (state.selectedCallsign === callsign) {
        renderFlightPlanPreview(callsign);
        const record = aircraftLayers.get(callsign);
        const pilot = state.data?.pilots?.find(item => item.callsign === callsign);
      }
      return points;
    })
    .catch(error => {
      console.debug('Track history unavailable', callsign, error);
      return [];
    })
    .finally(() => trackHistoryRequests.delete(callsign));
  trackHistoryRequests.set(callsign, request);
  return request;
}

function mergeTrackDetailIntoState(callsign, detail) {
  const normalized = String(callsign || '').toUpperCase();
  for (const dataset of [state.rawData, state.data]) {
    const pilot = dataset?.pilots?.find(item => String(item.callsign || '').toUpperCase() === normalized);
    if (!pilot) continue;
    for (const field of DETAIL_ONLY_PILOT_FIELDS) {
      if (Object.hasOwn(detail, field)) pilot[field] = detail[field];
    }
  }
}

async function fetchTrackDetail(callsign, force = false) {
  const normalized = String(callsign || '').toUpperCase();
  if (!normalized) return null;
  const cached = state.trackDetailCache.get(normalized);
  if (!force && cached && Date.now() - cached.fetchedAt < 15000) {
    mergeTrackDetailIntoState(normalized, cached.pilot);
    return cached.pilot;
  }
  if (state.trackDetailRequests.has(normalized)) return state.trackDetailRequests.get(normalized);
  const request = fetchWithTimeout(`/api/tracks/${encodeURIComponent(normalized)}?ts=${Date.now()}`, { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error(`Track detail ${response.status}`);
      return response.json();
    })
    .then(payload => {
      if (!payload?.pilot) return null;
      state.trackDetailCache.set(normalized, { pilot: payload.pilot, fetchedAt: Date.now(), revision: payload.revision });
      mergeTrackDetailIntoState(normalized, payload.pilot);
      if (Array.isArray(payload.history)) serverTrackHistory.set(normalized, { points: payload.history, fetchedAt: Date.now() });
      if (state.selectedCallsign === normalized || state.atcSelectedCallsign === normalized || state.operatorAircraftCallsign === normalized) {
        renderFlightPlanPreview(normalized);
        const record = aircraftLayers.get(normalized);
        const pilot = state.data?.pilots?.find(item => item.callsign === normalized);
        if (record?.marker?.getPopup() && pilot) record.marker.setPopupContent(aircraftPopup(pilot));
        if (state.workspaceTab === 'atc') renderAtcWorkspace(true);
      }
      return payload.pilot;
    })
    .catch(error => {
      console.debug('Track detail unavailable', normalized, error);
      return null;
    })
    .finally(() => state.trackDetailRequests.delete(normalized));
  state.trackDetailRequests.set(normalized, request);
  return request;
}

function trackHistorySummary(callsign) {
  const history = normalizedTrackHistory(callsign);
  if (history.length < 2) return 'CAPTURING';
  const minutes = Math.max(1, Math.round((history.at(-1).time - history[0].time) / 60000));
  return `${minutes} MIN · ${history.length} POINTS`;
}

function observedTrackHeading(pilot) {
  const history = normalizedTrackHistory(pilot?.callsign);
  if (history.length < 2) return null;
  const previous = history.at(-2);
  const current = history.at(-1);
  if (map.distance([previous.lat, previous.lon], [current.lat, current.lon]) < 185) return null;
  return Math.round(bearingBetween(previous.lat, previous.lon, current.lat, current.lon)) % 360;
}

function routeText(value, maxLength = 170) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return 'NOT FILED / NOT AVAILABLE';
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function formatFlightLevel(altitude) {
  const feet = Math.max(0, Math.round(Number(altitude || 0)));
  return feet >= 18000 ? `FL${Math.floor(feet / 100).toString().padStart(3, '0')}` : `ALT ${Math.round(feet / 100).toString().padStart(3, '0')}`;
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds || 0)));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
    : `${minutes}:${String(secs).padStart(2, '0')}`;
}

function finiteCoordinate(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function atcFrequencyStatus(pilot) {
  if (pilot?.advisory_frequency_whitelisted) return 'CTAF / UNICOM WHITELISTED';
  if (pilot?.online_center_handoff) return `HANDOFF TO ${pilot.online_center_handoff_detail?.downstream_controller || 'DOWNSTREAM CENTER'} VERIFIED`;
  if (pilot?.early_unicom_handoff) return 'EARLY 122.800 HANDOFF SUPPRESSED';
  if (pilot?.active_artcc_frequency_match && !pilot?.frequency_mismatch_active) return 'ACTIVE ARTCC FREQUENCY MATCHED';
  if (pilot?.atc_frequency_match && !pilot?.frequency_mismatch_active) return 'MATCHED';
  if (pilot?.frequency_mismatch_active && !pilot?.frequency_mismatch_current) {
    return `${String(pilot.frequency_mismatch_case_status || 'CASE PAUSED').replaceAll('_', ' ')} · ${formatDuration(pilot.frequency_mismatch_seconds)}`;
  }
  if (pilot?.frequency_mismatch_active) {
    if (pilot?.coverage_selection_reason === 'MULTI_POSITION_MISMATCH') {
      return `NO MATCH TO ANY LIVE ATC FREQ · ${formatDuration(pilot.frequency_mismatch_seconds)}`;
    }
    if (pilot?.coverage_selection_reason === 'SPLIT_POSITION_FALLBACK') {
      return `SPLIT-SECTOR WRONG FREQ · ${formatDuration(pilot.frequency_mismatch_seconds)}`;
    }
    return `WRONG FREQ · ${formatDuration(pilot.frequency_mismatch_seconds)}`;
  }
  if (pilot?.center) return 'COVERAGE IDENTIFIED · TIMER INHIBITED';
  if (pilot?.coverage_selection_reason === 'AMBIGUOUS_OVERLAP') return 'AMBIGUOUS HANDOFF';
  if (pilot?.coverage_selection_reason === 'NO_LIVE_TRANSCEIVER_COVERAGE') return 'NO LIVE COVERAGE';
  return 'NOT EVALUATED';
}

function vsoaMarkerLabel(pilot) {
  if (pilot?.blackjack) return 'BLACKJACK';
  return String(pilot?.vsoa_label || 'VSOA');
}

function vsoaBadgeLabel(pilot) {
  const marker = vsoaMarkerLabel(pilot);
  return marker.toUpperCase() === 'VSOA' ? 'VSOA' : `VSOA · ${marker}`;
}

function clearFlightPlanPreview() {
  if (flightPlanPreviewLayerGroup) map.removeLayer(flightPlanPreviewLayerGroup);
  flightPlanPreviewLayerGroup = null;
}

function previewEndpointIcon(label, kind) {
  return L.divIcon({
    className: '',
    iconSize: [64, 24],
    iconAnchor: [12, 12],
    html: `<div class="route-endpoint ${kind}"><i></i><span>${escapeHtml(label || '—')}</span></div>`,
  });
}

function renderFlightPlanPreview(callsign) {
  clearFlightPlanPreview();
  const pilot = state.data?.pilots?.find(item => item.callsign === callsign);
  if (!pilot) return;
  const lat = Number(pilot.lat);
  const lon = Number(pilot.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

  const layers = [];
  const scopeMode = state.basemap === 'atc-scope';
  const trailColor = scopeMode ? '#55d96a' : '#42d9ff';
  const plannedColor = scopeMode ? '#5abf72' : '#497dff';
  const headingColor = pilotVisualColor(pilot);
  const history = normalizedTrackHistory(callsign);

  const depLat = finiteCoordinate(pilot.departure_lat);
  const depLon = finiteCoordinate(pilot.departure_lon);
  const arrLat = finiteCoordinate(pilot.arrival_lat);
  const arrLon = finiteCoordinate(pilot.arrival_lon);
  const hasDeparture = depLat !== null && depLon !== null;
  const hasArrival = arrLat !== null && arrLon !== null;

  if (hasDeparture && hasArrival) {
    layers.push(L.polyline([[depLat, depLon], [arrLat, arrLon]], {
      pane: 'flightPlanPreview', renderer: pathRenderer, color: plannedColor, weight: 1.7,
      opacity: 0.56, dashArray: '9 7', interactive: false,
    }));
    layers.push(L.marker([depLat, depLon], { pane: 'flightPlanPreview', interactive: false, keyboard: false, icon: previewEndpointIcon(pilot.departure, 'departure') }));
    layers.push(L.marker([arrLat, arrLon], { pane: 'flightPlanPreview', interactive: false, keyboard: false, icon: previewEndpointIcon(pilot.arrival, 'arrival') }));
  } else if (hasArrival) {
    layers.push(L.polyline([[lat, lon], [arrLat, arrLon]], {
      pane: 'flightPlanPreview', renderer: pathRenderer, color: plannedColor, weight: 1.7,
      opacity: 0.56, dashArray: '9 7', interactive: false,
    }));
    layers.push(L.marker([arrLat, arrLon], { pane: 'flightPlanPreview', interactive: false, keyboard: false, icon: previewEndpointIcon(pilot.arrival, 'arrival') }));
  }

  // Draw observed history after the filed endpoint reference so the actual
  // breadcrumb remains visible even when both paths overlap.
  if (history.length >= 2) {
    const latLngs = history.map(item => [item.lat, item.lon]);
    layers.push(L.polyline(latLngs, {
      pane: 'flightPlanPreview', renderer: pathRenderer, color: '#02070a', weight: 5.2,
      opacity: 0.82, interactive: false, lineCap: 'round', lineJoin: 'round',
    }));
    layers.push(L.polyline(latLngs, {
      pane: 'flightPlanPreview', renderer: pathRenderer, color: trailColor, weight: 2.8,
      opacity: 1, interactive: false, lineCap: 'round', lineJoin: 'round',
    }));
  }

  if (!pilot.on_ground) {
    const projectionMinutes = 12;
    const projectedDistanceNm = Math.max(8, Number(pilot.groundspeed || 0) * projectionMinutes / 60);
    const projected = destinationLatLng(lat, lon, normaliseHeading(pilot.heading), projectedDistanceNm);
    layers.push(L.polyline([[lat, lon], projected], {
      pane: 'flightPlanPreview', renderer: pathRenderer, color: headingColor, weight: 1.2,
      opacity: 0.92, dashArray: '3 5', interactive: false,
    }));
  }

  flightPlanPreviewLayerGroup = L.layerGroup(layers).addTo(map);
}

function promotedIconDensity(density, pilot) {
  if (!(pilot?.severity === 'red' || pilot?.active_intercept || pilot?.nordo_watch || state.selectedCallsign === pilot?.callsign)) return density;
  if (density === 'micro') return 'compact';
  if (density === 'compact') return 'reduced';
  return density;
}

function groundTrackColor(pilot) {
  if (pilot?.active_intercept || pilot?.severity === 'red' || pilot?.nordo_watch) return pilotVisualColor(pilot);
  return state.basemap === 'atc-scope' ? '#78927e' : '#83959a';
}

function groundScopeIcon(pilot, requestedDensity) {
  const showLabel = requestedDensity === 'reduced' || requestedDensity === 'full';
  const dimensions = showLabel ? { size: [92, 24], anchor: [8, 12] } : { size: [14, 14], anchor: [7, 7] };
  const color = groundTrackColor(pilot);
  return L.divIcon({
    className: '',
    pane: 'aircraft',
    iconSize: dimensions.size,
    iconAnchor: dimensions.anchor,
    html: `<div class="ground-scope-track${state.selectedCallsign === pilot.callsign ? ' selected' : ''}" style="--marker:${color}">
      <span class="ground-scope-symbol"></span>${showLabel ? `<span class="ground-label"><strong>${escapeHtml(pilot.callsign)}</strong><i>${escapeHtml(pilot.ground_status || 'GROUND')}</i></span>` : ''}
    </div>`,
  });
}

function groundTacticalIcon(pilot, requestedDensity) {
  const showLabel = requestedDensity === 'reduced' || requestedDensity === 'full';
  const dimensions = showLabel ? { size: [96, 26], anchor: [9, 13] } : { size: [16, 16], anchor: [8, 8] };
  const color = groundTrackColor(pilot);
  return L.divIcon({
    className: '',
    pane: 'aircraft',
    iconSize: dimensions.size,
    iconAnchor: dimensions.anchor,
    html: `<div class="ground-tactical-track${state.selectedCallsign === pilot.callsign ? ' selected' : ''}" style="--marker:${color};--heading:${normaliseHeading(pilot.heading)}deg">
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"></rect><path d="M12 2v5"></path></svg>${showLabel ? `<span class="ground-label"><strong>${escapeHtml(pilot.callsign)}</strong><i>${escapeHtml(pilot.ground_status || 'GROUND')}</i></span>` : ''}
    </div>`,
  });
}

function scopeIcon(pilot, requestedDensity) {
  if (pilot?.on_ground) return groundScopeIcon(pilot, requestedDensity);
  const density = promotedIconDensity(requestedDensity, pilot);
  const visualSeverity = pilotVisualSeverity(pilot);
  const color = pilotVisualColor(pilot);
  const selected = state.selectedCallsign === pilot.callsign;
  const altitude = Math.max(0, Math.round((pilot.altitude || 0) / 100)).toString().padStart(3, '0');
  const speed = Math.max(0, Math.round((pilot.groundspeed || 0) / 10)).toString().padStart(2, '0');
  const alert = pilot.active_intercept ? 'INTERCEPT' : (pilot.nordo_watch ? 'NORDO WATCH' : (pilot.severity === 'green' ? '' : escapeHtml(pilot.squawk || severityLabel[pilot.severity])));
  const selectedClass = selected ? ' selected' : '';
  const interceptClass = pilot.active_intercept ? ' active-intercept' : '';
  const vsoaClass = pilot.vsoa ? ' vsoa-track' : '';
  const nordoClass = pilot.nordo_watch ? ` nordo-${pilot.nordo_watch.level || 'yellow'}` : '';
  const densityClass = ` ${density}`;
  const dimensions = {
    micro: { size: [18, 18], anchor: [9, 9] },
    compact: { size: [26, 26], anchor: [13, 13] },
    reduced: { size: [92, 38], anchor: [13, 19] },
    full: { size: [178, 82], anchor: [18, 41] },
  }[density] || { size: [178, 82], anchor: [18, 41] };
  const showBlock = density === 'reduced' || density === 'full';
  const showFullBlock = density === 'full';
  const typeCode = aircraftTypeCode(pilot);
  const tags = [pilot.vsoa ? `<span class="scope-tag vsoa${pilot.blackjack ? ' blackjack' : ''}">${escapeHtml(vsoaMarkerLabel(pilot))}</span>` : '', alert ? `<span class="scope-tag alert">${alert}</span>` : ''].join('');

  return L.divIcon({
    className: '',
    pane: 'aircraft',
    iconSize: dimensions.size,
    iconAnchor: dimensions.anchor,
    html: `<div class="scope-track ${visualSeverity}${selectedClass}${interceptClass}${vsoaClass}${nordoClass}${densityClass}" style="--marker:${color};--heading:${normaliseHeading(pilot.heading)}deg">
      <div class="scope-symbol"><span class="scope-primary"></span><span class="scope-beacon"></span><span class="scope-vector"></span>${pilot.vsoa ? '<span class="vsoa-orbit"></span>' : ''}</div>
      ${showBlock ? `<div class="scope-leader"></div><div class="scope-datablock"><div class="scope-call">${escapeHtml(pilot.callsign)}</div>${showFullBlock ? `<div class="scope-line">${altitude} ${speed} ${escapeHtml(typeCode)}</div><div class="scope-tags">${tags}</div>` : (pilot.vsoa ? `<div class="scope-tags"><span class="scope-tag vsoa${pilot.blackjack ? ' blackjack' : ''}">${escapeHtml(vsoaMarkerLabel(pilot))}</span></div>` : '')}</div>` : ''}
    </div>`,
  });
}


function aircraftTypeCode(pilot) {
  const backendCode = String(pilot?.aircraft_type || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (backendCode && backendCode !== 'ACFT') return backendCode.slice(0, 8);

  const raw = String(pilot?.aircraft || '').toUpperCase().trim();
  if (/F[\s\/-]*A[\s\/-]*18/.test(raw)) return 'F18';
  const tokens = raw.match(/[A-Z0-9]+/g) || [];
  const token = tokens.find((item) => !['H', 'J', 'L', 'M', 'S'].includes(item) && /^[A-Z][A-Z0-9]{1,4}$/.test(item));
  return (token || 'ACFT').slice(0, 8);
}

function aircraftCategory(pilot) {
  if (pilot?.display_class === 'fighter' || pilot?.active_intercept) return 'fighter';
  const backendCategory = String(pilot?.aircraft_category || '').toLowerCase();
  if (['fighter', 'helicopter', 'bomber', 'military', 'turboprop', 'business', 'airliner', 'general'].includes(backendCategory)) return backendCategory;

  const code = aircraftTypeCode(pilot);
  if (/^(F14|F15|F16|F18|FA18|F22|F35|F4|F5|F104|F111|F117|A10|AV8|EF2K|EUFI|M2K|MIR2|RAFA|JAS3|GR4|TOR|MIG|SU2|SU3|FA50|TA50|T38)/.test(code)) return 'fighter';
  if (/^(H\d{1,3}|UH|HH|CH|AH|MH|SH|OH|EC|AS|AW|S76|S92|B06|B47|R22|R44|R66|MD5|BK1|KA32|MI8|MI17|MI24|MI26|MI28|HUEY)/.test(code)) return 'helicopter';
  if (/^(B1|B2|B52|TU95|TU160|VULC|LANC)/.test(code)) return 'bomber';
  if (/^(C5|C17|C130|C30J|A400|AN12|AN22|AN26|AN72|AN124|AN225|IL76|KC10|KC46|K35R|KC135|E3|E8|P3|P8|C2|C27J|C295|CN35|VC25|B703)/.test(code)) return 'military';
  if (/^(AT4|AT7|DH8|DHC|SF34|E120|F50|B190|C208|PC12|TBM|BE20|B350|C90|P46T|JS31|JS32|JS41|L410|AN24)/.test(code)) return 'turboprop';
  if (/^(C25|C5[0-9X]|C6[0-9A-Z]|C7[0-9A-Z]|GLF|GLEX|G280|CL3|CL6|LJ|E50P|E55P|HDJT|SF50|PC24|F2TH|FA7X|FA8X|H25|PRM1)/.test(code)) return 'business';
  if (/^(A3|A2[2-9]|A4|B7|BCS|E1[7-9]|E2[0-9]|CRJ|MD8|MD9|DC8|DC9|DC10|L101|F70|F100|C919|SU95|IL6|IL8|TU1|TU2|Y11|ARJ)/.test(code)) return 'airliner';
  return 'general';
}

const tacticalAircraftPaths = {
  fighter: '<path d="M32 3 38 21 57 30 51 38 39 34 45 52 35 61 32 43 29 61 19 52 25 34 13 38 7 30 26 21Z"/>',
  helicopter: '<g fill="currentColor"><rect x="27" y="20" width="10" height="31" rx="5"/><path d="M32 7 35 20H29ZM28 48h8l8 9h-5l-7-4-7 4h-5Z"/><rect x="6" y="14" width="52" height="3" rx="1.5"/><rect x="30.5" y="5" width="3" height="22" rx="1.5"/><circle cx="32" cy="15.5" r="4"/></g>',
  bomber: '<path d="M32 5 40 22 59 31 55 39 39 36 43 53 32 60 21 53 25 36 9 39 5 31 24 22Z"/>',
  military: '<path d="M30 4h4l6 20 22 8v8l-22-3 4 18-12 7-12-7 4-18-22 3v-8l22-8Z"/>',
  turboprop: '<g fill="currentColor"><path d="M29 5h6l3 23 23 4v7l-23-2 3 18-9 6-9-6 3-18-23 2v-7l23-4Z"/><circle cx="11" cy="34" r="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="53" cy="34" r="5" fill="none" stroke="currentColor" stroke-width="2"/></g>',
  business: '<path d="M31 4h2l5 24 20 8v5l-20-4 3 18-9 6-9-6 3-18-20 4v-5l20-8Z"/>',
  airliner: '<path d="M30 3h4l5 24 22 9v6l-22-5 3 18-10 7-10-7 3-18-22 5v-6l22-9Z"/>',
  general: '<path d="M29 7h6l3 20 21 5v7l-21-2 2 17-8 6-8-6 2-17-21 2v-7l21-5Z"/>',
};

function tacticalAircraftSvg(pilot) {
  const category = aircraftCategory(pilot);
  return `<svg class="aircraft-shape ${category}" viewBox="0 0 64 64" aria-hidden="true">${tacticalAircraftPaths[category] || tacticalAircraftPaths.general}</svg>`;
}

function tacticalIcon(pilot, requestedDensity) {
  if (pilot?.on_ground) return groundTacticalIcon(pilot, requestedDensity);
  const density = promotedIconDensity(requestedDensity, pilot);
  const visualSeverity = pilotVisualSeverity(pilot);
  const color = pilotVisualColor(pilot);
  const selected = state.selectedCallsign === pilot.callsign;
  const dimensions = {
    micro: { size: [18, 18], anchor: [9, 9] },
    compact: { size: [28, 24], anchor: [12, 12] },
    reduced: { size: [58, 32], anchor: [16, 16] },
    full: { size: [78, 54], anchor: [24, 27] },
  }[density] || { size: [78, 54], anchor: [24, 27] };
  const showLabel = density === 'reduced' || density === 'full';
  const vsoaTag = pilot.vsoa ? `<b class="vsoa-label">${escapeHtml(vsoaMarkerLabel(pilot))}</b>` : '';
  const statusTag = pilot.active_intercept && density === 'full' ? `<b>${pilot.manual_intercept ? 'MANUAL' : 'INTERCEPT'}</b>` : (pilot.nordo_watch && density === 'full' ? '<b>NORDO WATCH</b>' : '');
  return L.divIcon({
    className: '',
    pane: 'aircraft',
    iconSize: dimensions.size,
    iconAnchor: dimensions.anchor,
    html: `<div class="tactical-track ${visualSeverity}${selected ? ' selected' : ''}${pilot.active_intercept ? ' active-intercept' : ''}${pilot.vsoa ? ' vsoa-track' : ''}${pilot.nordo_watch ? ` nordo-${pilot.nordo_watch.level || 'yellow'}` : ''} ${density}" style="--marker:${color};--heading:${normaliseHeading(pilot.heading)}deg">
      ${pilot.vsoa ? '<span class="vsoa-orbit"></span>' : ''}${tacticalAircraftSvg(pilot)}
      ${showLabel ? `<span><strong>${escapeHtml(pilot.callsign)}</strong><i class="type-tag">${escapeHtml(aircraftTypeCode(pilot))}</i>${vsoaTag}${statusTag}</span>` : ''}
    </div>`,
  });
}

function aircraftIcon(pilot) {
  return state.iconMode === 'scope' ? scopeIcon(pilot, state.iconDensity) : tacticalIcon(pilot, state.iconDensity);
}

function iconFingerprint(pilot) {
  const selected = state.selectedCallsign === pilot.callsign ? 1 : 0;
  const headingStep = state.iconDensity === 'full' ? 5 : 10;
  const headingBucket = Math.round(normaliseHeading(pilot.heading) / headingStep) * headingStep;
  // Altitude and speed are visible only in the full scope datablock. Omitting
  // them from low-zoom fingerprints prevents hundreds of unnecessary DOM icon
  // replacements every feed cycle.
  const altitudeBucket = state.iconDensity === 'full' ? Math.round((pilot.altitude || 0) / 100) : '';
  const speedBucket = state.iconDensity === 'full' ? Math.round((pilot.groundspeed || 0) / 10) : '';
  const squawk = state.iconDensity === 'full' ? pilot.squawk : '';
  return [state.iconMode, state.iconDensity, pilotVisualSeverity(pilot), selected, headingBucket, altitudeBucket, speedBucket, squawk, pilot.on_ground ? 1 : 0, pilot.ground_status || '', pilot.active_intercept ? 1 : 0, pilot.manual_intercept ? 1 : 0, pilot.manual_nordo ? 1 : 0, pilot.vsoa ? 1 : 0, pilot.blackjack ? 1 : 0, pilot.nordo_watch?.level || '', pilot.intercept_assignment?.target_callsign || '', pilot.intercept_assignment?.assignment_source || '', aircraftCategory(pilot), aircraftTypeCode(pilot)].join('|');
}


function aircraftPopup(pilot) {
  const fl = Math.max(0, Math.floor((pilot.altitude || 0) / 100)).toString().padStart(3, '0');
  const currentSquawk = String(pilot.squawk || '—');
  const assignedSquawk = String(pilot.assigned_squawk || '—');
  const squawkState = assignedSquawk === '—' ? 'NO ASSIGNMENT' : currentSquawk === assignedSquawk ? 'MATCH' : 'MISMATCH';
  const badges = [
    pilot.manual_nordo ? '<span class="popup-status danger">MANUAL NORDO</span>' : '',
    pilot.vsoa ? `<span class="popup-status vsoa">${escapeHtml(vsoaMarkerLabel(pilot))}</span>` : '',
    pilot.nordo_watch ? `<span class="popup-status warning">${escapeHtml(pilot.nordo_watch.title || 'NORDO WATCH')}</span>` : '',
  ].join('');
  return `<div class="aircraft-click-card">
    <header><div><span>LIVE AIRCRAFT</span><strong>${escapeHtml(pilot.callsign)}</strong><small>${escapeHtml(pilot.aircraft || pilot.aircraft_type || 'UNKNOWN')} · ${pilot.on_ground ? `GROUND ${escapeHtml(pilot.ground_status || '')}` : `FL${fl}`} · ${pilot.groundspeed || 0} KT · HDG ${String(normaliseHeading(pilot.heading)).padStart(3,'0')}°</small></div>${badges}</header>
    <div class="aircraft-click-grid">
      <div><span>REPORTED RADIO(S)</span><strong>${escapeHtml(formatPilotRadios(pilot))}</strong></div>
      <div><span>EXPECTED CONTROLLER</span><strong>${escapeHtml(pilot.center || 'NONE')}</strong></div>
      <div><span>EXPECTED FREQUENCY</span><strong>${escapeHtml(formatFreqs(pilot.active_artcc_frequencies || pilot.center_frequencies))}</strong></div>
      <div><span>COMMUNICATIONS</span><strong>${escapeHtml(atcCommunicationsStatus(pilot))}</strong></div>
      <div><span>CURRENT SQUAWK</span><strong>${escapeHtml(currentSquawk)}</strong></div>
      <div><span>ASSIGNED SQUAWK</span><strong>${escapeHtml(assignedSquawk)}</strong></div>
      <div><span>SQUAWK STATUS</span><strong class="${squawkState === 'MISMATCH' ? 'warning' : ''}">${escapeHtml(squawkState)}</strong></div>
      <div><span>ROUTE</span><strong>${escapeHtml(pilot.departure || '—')} → ${escapeHtml(pilot.arrival || '—')}</strong></div>
      ${pilot.blackjack ? `<div class="blackjack-detail"><span>SPECIAL UNIT</span><strong>${escapeHtml(pilot.special_unit || 'USCG NCRAD BLACKJACK')}</strong></div><div class="blackjack-detail"><span>MISSION ROLE</span><strong>${escapeHtml(pilot.special_mission || 'ROTARY-WING AIR INTERCEPT')}</strong></div>` : ''}
    </div>
    <footer>CLICK SELECTS THIS TRACK · OPEN ATC COORDINATION FOR FULL EVIDENCE AND INTERCEPT ASSIGNMENT</footer>
  </div>`;
}
function densityForZoom(zoom) {
  if (zoom <= 4) return 'micro';
  if (zoom === 5) return 'compact';
  if (zoom === 6) return 'reduced';
  return 'full';
}

function updateScopeDensity(force = false) {
  const density = densityForZoom(map.getZoom());
  if (!force && density === state.iconDensity) return;
  state.iconDensity = density;
  state.compactScope = density !== 'full';
  renderAircraft(state.data?.pilots || [], true);
}
map.on('zoomend', () => updateScopeDensity());
map.on('moveend', () => updateScopeGrid());
map.on('zoomend', () => updateScopeGrid());
map.on('move zoom resize', scheduleAtcOnlineLabelLayout);
updateScopeDensity(true);

function renderAircraft(pilots, forceIcons = false) {
  if (state.renderFrame) cancelAnimationFrame(state.renderFrame);
  state.renderFrame = requestAnimationFrame(() => {
    const viewPilots = focusedPilots(pilots);
    const active = new Set();
    for (const pilot of viewPilots) {
      active.add(pilot.callsign);
      updateAircraftTrackHistory(pilot);
      const regionVisible = matchesOperationalRegion(pilot);
      const visible = regionVisible && (state.filter === 'all' || pilot.severity !== 'green' || pilot.active_intercept || Boolean(pilot.nordo_watch));
      let record = aircraftLayers.get(pilot.callsign);
      if (!record) {
        const marker = L.marker([pilot.lat, pilot.lon], {
          icon: aircraftIcon(pilot),
          pane: 'aircraft',
          keyboard: false,
          riseOnHover: true,
          zIndexOffset: pilot.on_ground ? 80 : (pilot.active_intercept ? 950 : (pilot.severity === 'red' ? 1200 : 300)),
        });
        marker._callsign = pilot.callsign;
        marker.on('click', () => {
          const current = aircraftLayers.get(marker._callsign)?.latestPilot;
          if (current) {
            if (marker.getPopup()) marker.setPopupContent(aircraftPopup(current));
            else marker.bindPopup(aircraftPopup(current), { ...safePopupOptions, className: 'tactical-popup', closeButton: false });
          }
          selectTrack(marker._callsign);
          setTimeout(() => {
            if (map.hasLayer(marker) && marker.getPopup()) marker.openPopup();
          }, 0);
        });
        record = { marker, iconKey: null, positionKey: `${pilot.lat}|${pilot.lon}`, latestPilot: pilot };
        aircraftLayers.set(pilot.callsign, record);
      }

      const { marker } = record;
      const nextPositionKey = `${Number(pilot.lat).toFixed(5)}|${Number(pilot.lon).toFixed(5)}`;
      if (record.positionKey !== nextPositionKey) {
        marker.setLatLng([pilot.lat, pilot.lon]);
        record.positionKey = nextPositionKey;
      }
      const nextIconKey = iconFingerprint(pilot);
      if (forceIcons || nextIconKey !== record.iconKey) {
        marker.setIcon(aircraftIcon(pilot));
        marker.setZIndexOffset(pilot.on_ground ? 80 : (pilot.active_intercept ? 950 : (pilot.severity === 'red' ? 1200 : pilot.severity === 'orange' ? 900 : 300)));
        record.iconKey = nextIconKey;
      }
      record.latestPilot = pilot;
      if (marker.isPopupOpen?.() && marker.getPopup()) {
        marker.setPopupContent(aircraftPopup(pilot));
      }
      if (visible && !map.hasLayer(marker)) marker.addTo(map);
      if (!visible && map.hasLayer(marker)) map.removeLayer(marker);
    }

    for (const [callsign, record] of aircraftLayers.entries()) {
      if (!active.has(callsign)) {
        map.removeLayer(record.marker);
        aircraftLayers.delete(callsign);
        aircraftTrackHistory.delete(callsign);
        if (state.selectedCallsign === callsign) clearFlightPlanPreview();
      }
    }

    const atcCount = state.data?.stats?.centers_online || 0;
    const canadaCount = state.data?.stats?.canada_aircraft || 0;
    const franceCount = state.data?.stats?.france_aircraft || 0;
    const focus = state.data?._artcc_focus;
    el('map-summary').textContent = focus
      ? `${focus.code} · ${pilots.length} RELEVANT TRACKS · ${focus.inside} INSIDE · ${focus.inbound} INBOUND · ${atcCount} CENTER POSITION${atcCount === 1 ? '' : 'S'}`
      : `${pilots.length} AIR TRACKS · ${canadaCount} CANADA · ${franceCount} FRANCE · ${atcCount} CENTERS`;
    updateArtccFocusControls();
    state.renderFrame = null;
  });
}

function baseIcon(base) {
  const country = String(base?.country || 'UNITED STATES').toUpperCase();
  const role = String(base?.qra_role || '').toLowerCase();
  const classes = ['base-marker'];
  if (country === 'CANADA') classes.push('rcaf');
  if (country === 'FRANCE') classes.push('france-base', base.scramble_enabled ? 'france-qra' : 'france-support', `type-${String(base.base_type || 'support').toLowerCase()}`);
  if (role === 'primary') classes.push('primary-qra');
  if (role === 'fol') classes.push('norad-fol');
  return L.divIcon({
    className: '',
    iconSize: [20, 20],
    iconAnchor: [10, 10],
    html: `<div class="${classes.join(' ')}"></div>`,
  });
}

function franceBaseRole(base) {
  if (base.scramble_enabled) return base.qra_role === 'FOL' ? 'QRA FORWARD DETACHMENT' : 'QRA FIGHTER BASE';
  return `${String(base.base_type || 'SUPPORT').replaceAll('_', ' ')} SUPPORT BASE`;
}

function renderBases(bases, force = false) {
  state.bases = bases || [];
  if (force || baseLayers.length) {
    for (const record of baseLayers.splice(0)) map.removeLayer(record.marker || record);
  }
  for (const base of state.bases.filter(item => item.scramble_enabled || item.display_enabled)) {
    if (!matchesOperationalRegion(base)) continue;
    const role = String(base.country || '').toUpperCase() === 'FRANCE'
      ? franceBaseRole(base)
      : base.qra_role === 'FOL' ? 'NORAD FORWARD OPERATING LOCATION' : base.qra_role === 'PRIMARY' ? 'PRIMARY QRA BASE' : 'FIGHTER BASE';
    const nation = base.country ? `<div>${escapeHtml(base.country)} · ${escapeHtml(role)}</div>` : '';
    const status = base.scramble_enabled ? '<div>QRA LAUNCH ELIGIBLE</div>' : '<div>SUPPORT / DISPLAY ONLY</div>';
    const marker = L.marker([base.lat, base.lon], { icon: baseIcon(base), zIndexOffset: base.scramble_enabled ? 520 : 420 })
      .bindPopup(`<div class="popup-call">${escapeHtml(base.icao)}</div><div>${escapeHtml(base.name)}</div>${nation}${status}<div>AIRCRAFT: ${escapeHtml((base.aircraft || []).join(' / '))}</div><div>${escapeHtml(base.unit || '')}</div>`, { ...safePopupOptions, className: 'tactical-popup' })
      .addTo(map);
    baseLayers.push({ marker, base });
  }
}


function findBase(icao) {
  return state.bases.find(base => base.icao === icao) || null;
}

function clearInterceptOverlay() {
  if (interceptLayerGroup) map.removeLayer(interceptLayerGroup);
  interceptLayerGroup = null;
}

function renderInterceptOverlay(force = false) {
  const pilot = state.data?.pilots?.find(item => item.callsign === state.selectedCallsign);
  const operation = state.data?.operations?.find(item => item.id === state.selectedOperationId)
    || state.data?.operations?.find(item => item.callsign === state.selectedCallsign && item.active);
  const interceptKey = compactJson({
    selectedCallsign: state.selectedCallsign,
    selectedOperationId: state.selectedOperationId,
    pilot: pilot ? [pilot.lat, pilot.lon, pilot.recommended_base, pilot.intercept_assignment, pilot.active_interceptors] : null,
    operation: operation ? [operation.lat, operation.lon, operation.recommended_base, operation.active_interceptors] : null,
  });
  if (!force && interceptKey === state.interceptRenderKey) return;
  state.interceptRenderKey = interceptKey;
  clearInterceptOverlay();
  const layers = [];

  const addPoint = (lat, lon, color, label) => {
    if (!Number.isFinite(Number(lat)) || !Number.isFinite(Number(lon))) return;
    layers.push(L.circleMarker([lat, lon], {
      pane: 'interceptPaths', renderer: pathRenderer, radius: 6, color, weight: 2,
      fillColor: color, fillOpacity: 0.35,
    }).bindTooltip(label, { permanent: false, className: 'tactical-popup' }));
  };

  const base = pilot?.recommended_base || operation?.recommended_base;
  if (base?.intercept_point_lat != null && base?.intercept_point_lon != null) {
    const home = findBase(base.icao) || base;
    if (home?.lat != null && home?.lon != null) {
      layers.push(L.polyline(
        [[home.lat, home.lon], [base.intercept_point_lat, base.intercept_point_lon]],
        { pane: 'interceptPaths', renderer: pathRenderer, color: '#71f6ff', weight: 2.3, opacity: 0.95 },
      ));
    }
    if (pilot) {
      layers.push(L.polyline(
        [[pilot.lat, pilot.lon], [base.intercept_point_lat, base.intercept_point_lon]],
        { pane: 'interceptPaths', renderer: pathRenderer, color: '#ff5252', weight: 1.8, opacity: 0.9, dashArray: '8 7' },
      ));
    }
    addPoint(base.intercept_point_lat, base.intercept_point_lon, '#71f6ff', `INTERCEPT POINT · COURSE ${String(base.intercept_course_deg ?? 0).padStart(3, '0')}°`);
  }

  if (pilot?.active_intercept && pilot.intercept_assignment) {
    const solution = pilot.intercept_assignment;
    layers.push(L.polyline(
      [[pilot.lat, pilot.lon], [solution.intercept_point_lat, solution.intercept_point_lon]],
      { pane: 'interceptPaths', renderer: pathRenderer, color: '#ffe36d', weight: 2.6, opacity: 1 },
    ));
    const target = state.data?.pilots?.find(item => item.callsign === solution.target_callsign);
    if (target) {
      layers.push(L.polyline(
        [[target.lat, target.lon], [solution.intercept_point_lat, solution.intercept_point_lon]],
        { pane: 'interceptPaths', renderer: pathRenderer, color: '#ff5252', weight: 1.8, opacity: 0.9, dashArray: '8 7' },
      ));
    }
    addPoint(solution.intercept_point_lat, solution.intercept_point_lon, '#ffe36d', `${solution.manual ? 'MANUAL INTERCEPT' : 'ACTIVE INTERCEPT'} · ${solution.target_callsign}`);
  }

  for (const interceptor of pilot?.active_interceptors || operation?.active_interceptors || []) {
    const fighter = state.data?.pilots?.find(item => item.callsign === interceptor.callsign);
    if (!fighter) continue;
    layers.push(L.polyline(
      [[fighter.lat, fighter.lon], [interceptor.intercept_point_lat, interceptor.intercept_point_lon]],
      { pane: 'interceptPaths', renderer: pathRenderer, color: '#ffe36d', weight: 2.4, opacity: 1 },
    ));
    addPoint(interceptor.intercept_point_lat, interceptor.intercept_point_lon, '#ffe36d', `${interceptor.callsign} INTERCEPT POINT`);
  }

  if (layers.length) interceptLayerGroup = L.layerGroup(layers).addTo(map);
}

function ensureInterceptMap() {
  const host = el('intercept-map');
  if (interceptMap || !host) return interceptMap;
  interceptMap = L.map(host, {
    zoomControl: false,
    minZoom: 3,
    maxZoom: 16,
    preferCanvas: true,
    worldCopyJump: true,
    zoomAnimation: true,
    fadeAnimation: false,
    markerZoomAnimation: false,
  }).setView([38.5, -97], 4);
  interceptMap.createPane('interceptRoutes');
  interceptMap.getPane('interceptRoutes').style.zIndex = 430;
  interceptMap.createPane('interceptPoints');
  interceptMap.getPane('interceptPoints').style.zIndex = 520;
  interceptMap.createPane('interceptTracks');
  interceptMap.getPane('interceptTracks').style.zIndex = 620;
  interceptMapBasemap = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 16,
    className: 'intercept-map-basemap',
    attribution: 'Basemap &copy; Esri, HERE, Garmin, and contributors',
    updateWhenIdle: true,
    keepBuffer: 2,
  }).addTo(interceptMap);
  L.control.zoom({ position: 'bottomright' }).addTo(interceptMap);
  interceptMap.on('dragstart zoomstart', event => {
    if (!event.originalEvent) return;
    state.interceptMapAutoFit = false;
    updateInterceptMapAutoFitButton();
  });
  updateInterceptMapAutoFitButton();
  return interceptMap;
}

function updateInterceptMapAutoFitButton() {
  const button = el('intercept-map-auto-fit');
  if (!button) return;
  button.classList.toggle('active', state.interceptMapAutoFit);
  button.setAttribute('aria-pressed', String(state.interceptMapAutoFit));
  button.textContent = state.interceptMapAutoFit ? 'AUTO FIT ON' : 'AUTO FIT OFF';
}

function validTrackPoint(track) {
  const lat = Number(track?.lat);
  const lon = Number(track?.lon);
  return Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : null;
}

function validInterceptPoint(assignment) {
  const lat = Number(assignment?.intercept_point_lat);
  const lon = Number(assignment?.intercept_point_lon);
  return Number.isFinite(lat) && Number.isFinite(lon) ? [lat, lon] : null;
}

function interceptMapTrackIcon(track, role, status, assignment = null) {
  const heading = normaliseHeading(track?.heading ?? (role === 'interceptor' ? assignment?.interceptor_heading_deg : assignment?.target_heading_deg));
  const callsign = track?.callsign || (role === 'interceptor' ? assignment?.interceptor_callsign : assignment?.target_callsign) || 'UNKNOWN';
  const statusText = String(status || 'LIVE').replaceAll('_', ' ');
  const eta = role === 'interceptor' && assignment ? formatInterceptEta(assignment) : '';
  return L.divIcon({
    className: '',
    pane: 'interceptTracks',
    iconSize: [150, 46],
    iconAnchor: [17, 23],
    html: `<div class="intercept-map-track ${role}${assignment?.live === false ? ' lost' : ''}" style="--heading:${heading}deg"><span class="intercept-map-aircraft">▲</span><span class="intercept-map-label"><strong>${escapeHtml(callsign)}</strong><small>${escapeHtml(statusText)}${eta ? ` · ${escapeHtml(eta)}` : ''}</small></span></div>`,
  });
}

function interceptPointIcon(assignment, sequence) {
  const eta = formatInterceptEta(assignment);
  return L.divIcon({
    className: '',
    pane: 'interceptPoints',
    iconSize: [170, 46],
    iconAnchor: [16, 23],
    html: `<div class="intercept-map-point"><span class="intercept-point-crosshair"></span><span><strong>POI ${sequence}</strong><small>${escapeHtml(assignment.interceptor_callsign)} · ${escapeHtml(eta)}</small></span></div>`,
  });
}

function renderInterceptTacticalMap(force = false, fitNow = false) {
  const host = el('intercept-map');
  if (!host) return;
  const tacticalMap = ensureInterceptMap();
  if (!tacticalMap) return;
  const assignments = activeInterceptAssignments();
  const groups = groupedInterceptAssignments();
  const controls = new Map((state.data?.intercept_controls || []).map(item => [normaliseCallsign(item.target_callsign), item]));
  const renderKey = compactJson({
    feed: state.data?.feed_sequence,
    stale: state.dataStale,
    assignments: assignments.map(item => [
      item.key, item.live, item.interceptor_callsign, item.target_callsign,
      item.interceptor?.lat ?? pilotForCallsign(item.interceptor_callsign)?.lat,
      item.interceptor?.lon ?? pilotForCallsign(item.interceptor_callsign)?.lon,
      item.target?.lat ?? pilotForCallsign(item.target_callsign)?.lat,
      item.target?.lon ?? pilotForCallsign(item.target_callsign)?.lon,
      item.intercept_point_lat, item.intercept_point_lon, item.estimated_intercept_minutes,
      item.closure_status, item.recommended_course_deg, item.calculated_at, item.updated_at,
    ]),
    controls: [...controls.entries()].map(([target, item]) => [target, item.target_response_status, item.atc_coordination_status, item.command_status]),
  });
  if (!force && renderKey === state.interceptMapRenderKey) return;
  state.interceptMapRenderKey = renderKey;
  if (interceptMapLayerGroup) tacticalMap.removeLayer(interceptMapLayerGroup);
  const layers = [];
  const bounds = [];
  const plottedTargets = new Set();
  let pointCount = 0;

  for (const { targetCallsign, assignments: targetAssignments } of groups) {
    const target = pilotForCallsign(targetCallsign) || targetAssignments[0]?.target || {};
    const targetPoint = validTrackPoint(target);
    const control = controls.get(targetCallsign) || {};
    if (targetPoint && !plottedTargets.has(targetCallsign)) {
      plottedTargets.add(targetCallsign);
      bounds.push(targetPoint);
      const targetStatus = `${contactStatusLabel(control.target_response_status)} · ${interceptCommandLabel(control.command_status)}`;
      layers.push(L.marker(targetPoint, {
        pane: 'interceptTracks',
        icon: interceptMapTrackIcon(target, 'target', targetStatus, targetAssignments[0]),
        keyboard: false,
        zIndexOffset: 900,
      }).bindTooltip(`<strong>${escapeHtml(targetCallsign)}</strong><br>${escapeHtml(targetStatus)}<br>${Number(target.altitude || 0).toLocaleString()} FT · ${target.groundspeed || 0} KT · HDG ${String(normaliseHeading(target.heading)).padStart(3, '0')}°`, { className: 'tactical-popup', direction: 'top', offset: [0, -15] }));
    }

    targetAssignments.forEach((assignment, index) => {
      const interceptor = pilotForCallsign(assignment.interceptor_callsign) || assignment.interceptor || {};
      const interceptorPoint = validTrackPoint(interceptor);
      const point = validInterceptPoint(assignment);
      const liveStatus = assignment.live === false ? 'TRACK LOST' : String(assignment.closure_status || assignment.status || 'LIVE').toUpperCase();
      if (interceptorPoint) {
        bounds.push(interceptorPoint);
        layers.push(L.marker(interceptorPoint, {
          pane: 'interceptTracks',
          icon: interceptMapTrackIcon(interceptor, 'interceptor', liveStatus, assignment),
          keyboard: false,
          zIndexOffset: 1000,
        }).bindTooltip(`<strong>${escapeHtml(assignment.interceptor_callsign)}</strong><br>${escapeHtml(liveStatus)} · ${escapeHtml(formatInterceptEta(assignment))}<br>${Number(interceptor.altitude || assignment.interceptor_altitude_ft || 0).toLocaleString()} FT · ${interceptor.groundspeed ?? assignment.interceptor_speed_kt ?? '—'} KT · COURSE ${String(assignment.recommended_course_deg ?? 0).padStart(3, '0')}°`, { className: 'tactical-popup', direction: 'top', offset: [0, -15] }));
      }
      if (!point) return;
      pointCount += 1;
      bounds.push(point);
      if (interceptorPoint) {
        layers.push(L.polyline([interceptorPoint, point], {
          pane: 'interceptRoutes',
          color: assignment.live === false ? '#7d8a8e' : '#ffe36d',
          weight: 2.6,
          opacity: assignment.live === false ? 0.55 : 1,
          dashArray: assignment.live === false ? '5 7' : null,
          interactive: false,
        }));
      }
      if (targetPoint) {
        layers.push(L.polyline([targetPoint, point], {
          pane: 'interceptRoutes',
          color: '#ff765f',
          weight: 1.8,
          opacity: 0.9,
          dashArray: '8 7',
          interactive: false,
        }));
      }
      layers.push(L.marker(point, {
        pane: 'interceptPoints',
        icon: interceptPointIcon(assignment, index + 1),
        keyboard: false,
        zIndexOffset: 1100,
      }).bindTooltip(`<strong>ANTICIPATED INTERCEPT POINT</strong><br>${escapeHtml(assignment.interceptor_callsign)} → ${escapeHtml(assignment.target_callsign)}<br>ETA ${escapeHtml(formatInterceptEta(assignment))} · COURSE ${String(assignment.recommended_course_deg ?? 0).padStart(3, '0')}°<br>${Number(point[0]).toFixed(4)}, ${Number(point[1]).toFixed(4)}`, { className: 'tactical-popup intercept-point-tooltip', direction: 'top', offset: [0, -14] }));
    });
  }

  interceptMapLayerGroup = L.layerGroup(layers).addTo(tacticalMap);
  const empty = el('intercept-map-empty');
  if (empty) empty.hidden = assignments.length > 0;
  const summary = el('intercept-map-summary');
  if (summary) summary.textContent = `${groups.length} TARGET${groups.length === 1 ? '' : 'S'} · ${assignments.length} INTERCEPTOR${assignments.length === 1 ? '' : 'S'} · ${pointCount} POINT${pointCount === 1 ? '' : 'S'} · FEED #${state.data?.feed_sequence ?? 0}`;
  const mapStatus = el('intercept-map-status');
  if (mapStatus) {
    const recalculatedAt = state.data?.intercept_recalculated_at || assignments.map(item => item.calculated_at).filter(Boolean).sort().at(-1);
    mapStatus.textContent = assignments.length
      ? `LIVE FEED #${state.data?.feed_sequence ?? 0} · LAST SOLUTION ${recalculatedAt ? formatZuluTimestamp(recalculatedAt) : 'PENDING'} · ${state.dataStale ? 'FEED STALE' : 'TRACKING'}`
      : 'Assign one or more live aircraft to display routes and anticipated intercept points.';
  }

  const boundsKey = compactJson(bounds.map(point => point.map(value => Number(value).toFixed(4))));
  if (bounds.length && (fitNow || (state.interceptMapAutoFit && boundsKey !== state.interceptMapLastBoundsKey))) {
    state.interceptMapLastBoundsKey = boundsKey;
    tacticalMap.fitBounds(bounds, { padding: [54, 54], maxZoom: 8, animate: false });
  }
  if (state.workspaceTab === 'intercept') setTimeout(() => tacticalMap.invalidateSize(false), 0);
}

function focusInterceptTargetOnTacticalMap(targetCallsign) {
  setWorkspaceTab('intercept');
  const tacticalMap = ensureInterceptMap();
  const target = pilotForCallsign(targetCallsign);
  if (!tacticalMap || !target) return setInterceptBatchFeedback(`Live target ${targetCallsign || 'track'} is unavailable.`, 'error');
  state.interceptTargetCallsign = target.callsign;
  state.interceptMapAutoFit = false;
  updateInterceptMapAutoFitButton();
  renderInterceptTacticalMap(true);
  tacticalMap.setView([target.lat, target.lon], Math.max(6, tacticalMap.getZoom()), { animate: true });
  setInterceptBatchFeedback(`Intercept map focused on target ${target.callsign}.`, 'success');
}

function focusInterceptPairOnTacticalMap(interceptorCallsign, targetCallsign) {
  setWorkspaceTab('intercept');
  const tacticalMap = ensureInterceptMap();
  const interceptor = pilotForCallsign(interceptorCallsign);
  const target = pilotForCallsign(targetCallsign);
  const assignment = activeInterceptAssignments().find(item => item.interceptor_callsign === interceptorCallsign && item.target_callsign === targetCallsign);
  if (!tacticalMap || (!interceptor && !target)) return setInterceptBatchFeedback('The selected live intercept tracks are unavailable.', 'error');
  state.interceptTargetCallsign = targetCallsign;
  state.activeInterceptKey = assignment?.key || state.activeInterceptKey;
  state.interceptMapAutoFit = false;
  updateInterceptMapAutoFitButton();
  renderInterceptTacticalMap(true);
  const points = [validTrackPoint(interceptor), validTrackPoint(target), validInterceptPoint(assignment)].filter(Boolean);
  if (points.length > 1) tacticalMap.fitBounds(points, { padding: [65, 65], maxZoom: 9, animate: true });
  else if (points.length) tacticalMap.setView(points[0], 7, { animate: true });
  setInterceptBatchFeedback(`Showing ${interceptorCallsign} → ${targetCallsign} and its latest anticipated intercept point.`, 'success');
}

function renderZones(zones) {
  if (zoneLayerGroup) return;
  const layers = [];
  for (const zone of zones || []) {
    const color = zone.severity === 'red' ? '#ff5252' : '#ffab52';
    let layer = null;
    if (zone.type === 'circle') {
      layer = L.circle(zone.center, { pane: 'monitoredZones', renderer: pathRenderer, radius: zone.radius_nm * 1852, color, weight: 1.2, fillColor: color, fillOpacity: 0.09, dashArray: '6 5' });
    } else if (zone.type === 'polygon') {
      layer = L.polygon(zone.coordinates.map(([lon, lat]) => [lat, lon]), { pane: 'monitoredZones', renderer: pathRenderer, color, weight: 1.2, fillColor: color, fillOpacity: 0.10, dashArray: '6 5' });
    }
    if (layer) {
      layer.bindTooltip(`<div class="popup-call">${escapeHtml(zone.id)}</div><div>${escapeHtml(zone.name)}</div>`, { ...safeTooltipOptions, sticky: true, className: 'tactical-popup' });
      layers.push(layer);
    }
  }
  zoneLayerGroup = L.layerGroup(layers).addTo(map);
}

function atcStyle(item) {
  const exact = ['sector', 'tracon', 'airport_transceiver'].includes(item.match_quality);
  const center = item.facility === 'CTR';
  if (state.basemap === 'atc-scope') {
    return {
      pane: 'atcCoverage',
      renderer: pathRenderer,
      color: exact ? '#66ff7f' : '#48bf61',
      weight: exact ? 2.7 : 1.8,
      opacity: exact ? 1 : 0.82,
      fillColor: '#1b8f39',
      fillOpacity: exact ? 0.09 : 0.045,
      dashArray: exact ? null : '7 6',
      lineCap: 'round',
      lineJoin: 'round',
    };
  }
  const color = center ? '#7be7ff' : '#d8adff';
  return {
    pane: 'atcCoverage',
    renderer: pathRenderer,
    color,
    weight: exact ? 2.8 : 1.9,
    opacity: exact ? 1 : 0.86,
    fillColor: center ? '#28bfe8' : '#a46beb',
    fillOpacity: exact ? (center ? 0.13 : 0.14) : 0.06,
    dashArray: exact ? null : '8 7',
    lineCap: 'round',
    lineJoin: 'round',
  };
}

function atcHaloStyle(item) {
  const exact = ['sector', 'tracon', 'airport_transceiver'].includes(item.match_quality);
  const center = item.facility === 'CTR';
  const scopeMode = state.basemap === 'atc-scope';
  return {
    pane: 'atcCoverage',
    renderer: pathRenderer,
    color: scopeMode ? '#66ff7f' : (center ? '#59dfff' : '#c68cff'),
    weight: exact ? 8 : 5.5,
    opacity: exact ? 0.24 : 0.14,
    fill: false,
    interactive: false,
    dashArray: exact ? null : '8 7',
    lineCap: 'round',
    lineJoin: 'round',
  };
}

function atcOnlineLabel(item) {
  const frequencies = item.frequencies?.length
    ? item.frequencies.map(value => Number(value).toFixed(3)).join(' / ')
    : (item.frequency ? String(item.frequency) : 'NO FREQ');
  return `<div class="atc-online-label-box"><span class="atc-online-pulse"></span><strong>${escapeHtml(item.callsign || 'ATC')}</strong><em>${escapeHtml(frequencies)} · ONLINE</em></div>`;
}

function layoutAtcOnlineLabels() {
  atcLabelLayoutFrame = null;
  if (!atcLabelMarkers.length || !map?._loaded) return;
  const size = map.getSize();
  const horizontalMargin = Math.min(190, Math.max(112, size.x * 0.16));
  const verticalMargin = 62;
  for (const marker of atcLabelMarkers) {
    const root = marker.getElement?.();
    const box = root?.querySelector?.('.atc-online-label-box');
    if (!box) continue;
    const point = map.latLngToContainerPoint(marker.getLatLng());
    let shiftX = '-50%';
    let shiftY = '-50%';
    if (point.x < horizontalMargin) shiftX = '0%';
    else if (point.x > size.x - horizontalMargin) shiftX = '-100%';
    if (point.y < verticalMargin) shiftY = '0%';
    else if (point.y > size.y - verticalMargin) shiftY = '-100%';
    box.style.setProperty('--atc-label-shift-x', shiftX);
    box.style.setProperty('--atc-label-shift-y', shiftY);
  }
}

function scheduleAtcOnlineLabelLayout() {
  if (atcLabelLayoutFrame !== null) return;
  atcLabelLayoutFrame = requestAnimationFrame(layoutAtcOnlineLabels);
}

const safePopupOptions = {
  autoPan: true,
  keepInView: true,
  autoPanPaddingTopLeft: L.point(18, 78),
  autoPanPaddingBottomRight: L.point(18, 46),
  maxWidth: 330,
};

const safeTooltipOptions = {
  direction: 'auto',
  offset: L.point(10, 0),
  opacity: 1,
};

function centerBoundaryStyle(boundary) {
  const canada = boundary.country === 'CANADA';
  const focused = Boolean(state.artccFocusId && String(boundary.id || '').toUpperCase() === state.artccFocusId);
  if (focused) {
    return {
      pane: 'centerReference', renderer: pathRenderer,
      color: state.basemap === 'atc-scope' ? '#72ff8d' : '#71f6ff', weight: 2.4, opacity: 0.98,
      fillColor: state.basemap === 'atc-scope' ? '#2e8f45' : '#1d8fa0', fillOpacity: 0.065,
      dashArray: boundary.oceanic ? '5 5' : null,
    };
  }
  if (state.basemap === 'atc-scope') {
    return {
      pane: 'centerReference', renderer: pathRenderer,
      color: canada ? '#376c88' : '#28583a', weight: 0.85, opacity: 0.42,
      fillColor: canada ? '#173547' : '#14321f', fillOpacity: 0.008,
      dashArray: boundary.oceanic ? '3 9' : '5 8',
    };
  }
  return {
    pane: 'centerReference', renderer: pathRenderer,
    color: canada ? '#5c91b3' : '#467b98', weight: 0.95, opacity: 0.44,
    fillColor: canada ? '#2a78a6' : '#246f9a', fillOpacity: 0.008,
    dashArray: boundary.oceanic ? '4 8' : '6 7',
  };
}

function centerBoundaryTooltip(boundary) {
  return `<div class="popup-call">${escapeHtml(boundary.id)}</div><div>${escapeHtml(boundary.name || boundary.id)}</div><div>${escapeHtml(boundary.country || '')}${boundary.oceanic ? ' · OCEANIC' : ''}</div><div class="coverage-quality">PUBLISHED FIR / ARTCC OUTLINE</div><div class="popup-source">VATSpy Data Project</div>`;
}

function renderCenterBoundaries(boundaries, revision, force = false) {
  const focusWasResolvable = Boolean(focusedArtccBoundary());
  state.centerBoundaryData = boundaries || [];
  populateArtccFocusSelector();
  if (!force && revision && revision === state.centerBoundaryRevision) return;
  if (centerBoundaryLayerGroup) map.removeLayer(centerBoundaryLayerGroup);
  const visibleBoundaries = state.artccFocusId
    ? (boundaries || []).filter(item => String(item.id || '').toUpperCase() === state.artccFocusId)
    : (boundaries || []);
  const collection = {
    type: 'FeatureCollection',
    features: visibleBoundaries.filter(item => item.geometry).map(item => ({
      type: 'Feature', properties: item, geometry: item.geometry,
    })),
  };
  centerBoundaryLayerGroup = L.geoJSON(collection, {
    pane: 'centerReference', renderer: pathRenderer,
    style: feature => centerBoundaryStyle(feature.properties),
    onEachFeature: (feature, layer) => layer.bindTooltip(centerBoundaryTooltip(feature.properties), {
      ...safeTooltipOptions, sticky: true, className: 'tactical-popup atc-tooltip',
    }),
  });
  if (state.showAtcCoverage) centerBoundaryLayerGroup.addTo(map);
  state.centerBoundaryRevision = revision || state.centerBoundaryRevision;
  if (state.rawData && state.artccFocusId && !focusWasResolvable && focusedArtccBoundary()) applyData(state.rawData);
  updateArtccFocusControls();
}

async function refreshCenterBoundaries(expectedRevision = null) {
  if (state.centerBoundaryLoading || (expectedRevision && expectedRevision === state.centerBoundaryRevision)) return;
  state.centerBoundaryLoading = true;
  try {
    const response = await fetchWithTimeout(`/api/center-boundaries?ts=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`CENTER BOUNDARIES ${response.status}`);
    const payload = await response.json();
    renderCenterBoundaries(payload.boundaries || [], payload.revision);
    if (payload.count) el('boundary-status').textContent = `${payload.count} CENTER OUTLINES · ${payload.status || 'ONLINE'}`;
  } catch (error) {
    console.error(error);
    el('boundary-status').textContent = 'CENTER OUTLINES RETRYING';
  } finally {
    state.centerBoundaryLoading = false;
  }
}

function atcTooltip(item) {
  const frequencies = item.frequencies?.length ? item.frequencies.map(value => Number(value).toFixed(3)).join(' / ') : item.frequency || 'NO FREQUENCY';
  const quality = item.match_quality === 'sector'
    ? 'EXACT SUBSECTOR MATCH'
    : item.match_quality === 'tracon'
      ? 'EXACT TRACON MATCH'
      : item.match_quality === 'airport_transceiver'
        ? 'EXACT AIRPORT POSITION TRANSCEIVER'
        : item.geometry
        ? 'FULL-FACILITY DISPLAY FALLBACK'
        : 'TRANSCEIVER DISPLAY FALLBACK';
  return `<div class="popup-call">${escapeHtml(item.callsign)}</div><div>${escapeHtml(item.facility)} · ${escapeHtml(frequencies)}</div><div>${escapeHtml(item.name || item.boundary_id || 'BOUNDARY')}</div><div class="coverage-quality">${quality}</div><div class="popup-source">${escapeHtml(item.source)}</div><div class="coverage-note">RADIO ALERTS USE LIVE TRANSCEIVER REACH — NOT POLYGON ALONE</div>`;
}

function renderAtcCoverage(coverage, revision, force = false) {
  state.atcCoverageData = coverage || [];
  if (!force && revision && revision === state.atcRevision) return;
  if (atcLayerGroup) map.removeLayer(atcLayerGroup);
  atcLabelMarkers = [];
  const layers = [];
  const visibleCoverage = (coverage || []).filter(item => atcCoverageRelevantToArtcc(item) && matchesOperationalRegion(item));
  for (const item of visibleCoverage) {
    let layer = null;
    let halo = null;
    let labelPoint = null;
    if (item.geometry) {
      const feature = { type: 'Feature', properties: {}, geometry: item.geometry };
      halo = L.geoJSON(feature, { style: atcHaloStyle(item), pane: 'atcCoverage', renderer: pathRenderer, interactive: false });
      layer = L.geoJSON(feature, { style: atcStyle(item), pane: 'atcCoverage', renderer: pathRenderer });
      const bounds = layer.getBounds();
      if (bounds?.isValid()) labelPoint = bounds.getCenter();
    } else if (item.facility !== 'CTR' && item.lat !== null && item.lon !== null) {
      const center = [item.lat, item.lon];
      const radius = item.radius_nm * 1852;
      halo = L.circle(center, { ...atcHaloStyle(item), radius, fill: false });
      layer = L.circle(center, { ...atcStyle(item), radius, dashArray: '7 6' });
      labelPoint = L.latLng(item.lat, item.lon);
    }
    if (!layer) continue;
    if (halo) layers.push(halo);
    layer.bindTooltip(atcTooltip(item), { ...safeTooltipOptions, sticky: true, className: 'tactical-popup atc-tooltip' });
    layers.push(layer);
    if (labelPoint) {
      const labelMarker = L.marker(labelPoint, {
        pane: 'atcLabels',
        interactive: false,
        keyboard: false,
        icon: L.divIcon({
          className: 'atc-online-label',
          html: atcOnlineLabel(item),
          iconSize: null,
          iconAnchor: [0, 0],
        }),
      });
      atcLabelMarkers.push(labelMarker);
      layers.push(labelMarker);
    }
  }
  atcLayerGroup = L.layerGroup(layers);
  if (state.showAtcCoverage) atcLayerGroup.addTo(map);
  scheduleAtcOnlineLabelLayout();
  state.atcRevision = revision || state.atcRevision;
}

async function refreshAtcCoverage(expectedRevision = null) {
  if (state.atcLoading || (expectedRevision && expectedRevision === state.atcRevision)) return;
  state.atcLoading = true;
  try {
    const response = await fetchWithTimeout(`/api/atc?ts=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`ATC ${response.status}`);
    const payload = await response.json();
    renderAtcCoverage(payload.coverage || [], payload.revision);
    el('boundary-status').textContent = payload.status || `${payload.count || 0} POSITIONS`;
  } catch (error) {
    console.error(error);
    el('boundary-status').textContent = 'ATC LAYER RETRYING';
  } finally {
    state.atcLoading = false;
  }
}

function suaStyle(area) {
  const prohibited = area.category === 'PROHIBITED';
  const color = prohibited ? '#ff4040' : '#d99024';
  if (state.basemap === 'atc-scope') {
    return { pane: 'specialUseAirspace', renderer: pathRenderer, color, weight: prohibited ? 1.6 : 1.05, opacity: prohibited ? 0.90 : 0.75, fillColor: color, fillOpacity: prohibited ? 0.09 : 0.025, dashArray: prohibited ? null : '7 6' };
  }
  return { pane: 'specialUseAirspace', renderer: pathRenderer, color, weight: prohibited ? 1.7 : 1.1, opacity: 0.92, fillColor: color, fillOpacity: prohibited ? 0.15 : 0.08, dashArray: prohibited ? null : '5 5' };
}

function suaTooltip(area) {
  const agency = area.controlling_agency ? `<div>AGENCY: ${escapeHtml(area.controlling_agency)}</div>` : '';
  const schedule = area.times_of_use ? `<div>USE: ${escapeHtml(area.times_of_use)}</div>` : '';
  return `<div class="popup-call">${escapeHtml(area.designation)}</div><div>${escapeHtml(area.category)}</div><div>${escapeHtml(area.floor_label)}–${escapeHtml(area.ceiling_label)}</div>${agency}${schedule}`;
}

function renderSua(areas) {
  state.suaData = areas || [];
  if (suaLayerGroup) map.removeLayer(suaLayerGroup);
  const collection = {
    type: 'FeatureCollection',
    features: (areas || []).filter(area => area.geometry).map(area => ({ type: 'Feature', properties: area, geometry: area.geometry })),
  };
  suaLayerGroup = L.geoJSON(collection, {
    pane: 'specialUseAirspace',
    renderer: pathRenderer,
    style: feature => suaStyle(feature.properties),
    onEachFeature: (feature, layer) => layer.bindTooltip(suaTooltip(feature.properties), { ...safeTooltipOptions, sticky: true, className: `tactical-popup sua-tooltip ${feature.properties.category === 'PROHIBITED' ? 'prohibited' : ''}` }),
  });
  if (state.showSua) suaLayerGroup.addTo(map);
}

function scheduleSuaRefresh(delayMs) {
  if (state.suaRefreshTimer) clearTimeout(state.suaRefreshTimer);
  state.suaRefreshTimer = setTimeout(loadSua, delayMs);
}

async function loadSua() {
  if (state.suaLoading) return;
  state.suaLoading = true;
  let nextDelay = 300000;
  try {
    const response = await fetchWithTimeout(`/api/sua?ts=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`SUA ${response.status}`);
    const payload = await response.json();
    const version = `${payload.updated_at || 'pending'}:${payload.count || 0}`;
    if ((payload.count || 0) > 0 && version !== state.suaVersion) {
      renderSua(payload.areas || []);
      state.suaVersion = version;
    }
    el('sua-status').textContent = payload.status || `${payload.count || 0} AREAS`;
    if (!(payload.count || 0)) nextDelay = 15000;
  } catch (error) {
    console.error(error);
    el('sua-status').textContent = 'SUA LAYER RETRYING';
    nextDelay = 15000;
  } finally {
    state.suaLoading = false;
    scheduleSuaRefresh(nextDelay);
  }
}

function toggleAtcCoverage() {
  state.showAtcCoverage = !state.showAtcCoverage;
  el('toggle-atc').classList.toggle('active', state.showAtcCoverage);
  if (centerBoundaryLayerGroup) {
    if (state.showAtcCoverage && !map.hasLayer(centerBoundaryLayerGroup)) centerBoundaryLayerGroup.addTo(map);
    if (!state.showAtcCoverage && map.hasLayer(centerBoundaryLayerGroup)) map.removeLayer(centerBoundaryLayerGroup);
  }
  if (atcLayerGroup) {
    if (state.showAtcCoverage && !map.hasLayer(atcLayerGroup)) atcLayerGroup.addTo(map);
    if (!state.showAtcCoverage && map.hasLayer(atcLayerGroup)) map.removeLayer(atcLayerGroup);
  }
  if (state.showAtcCoverage) scheduleAtcOnlineLabelLayout();
}

function toggleSua() {
  state.showSua = !state.showSua;
  el('toggle-sua').classList.toggle('active', state.showSua);
  if (!suaLayerGroup) return;
  if (state.showSua && !map.hasLayer(suaLayerGroup)) suaLayerGroup.addTo(map);
  if (!state.showSua && map.hasLayer(suaLayerGroup)) map.removeLayer(suaLayerGroup);
}

function dcaHeliRoutePopup(route) {
  const restriction = route.closed ? 'CLOSED — DO NOT USE' : route.status;
  return `<div class="dca-heli-popup"><span>DCA / NCR HELICOPTER REFERENCE</span><strong>${escapeHtml(route.name)}</strong><em>${escapeHtml(restriction)}</em><p>Public-landmark reference only. Use the current FAA Baltimore–Washington Helicopter Route Chart and live ATC instructions.</p><a href="${DCA_HELI_CHART_URL}" target="_blank" rel="noopener noreferrer">OPEN CURRENT FAA CHART</a></div>`;
}

function updateDcaHeliRouteUi() {
  const button = el('toggle-dca-heli-routes');
  const chart = el('open-dca-heli-chart');
  const status = el('dca-heli-route-status');
  if (button) {
    button.classList.toggle('active', state.showDcaHeliRoutes);
    button.setAttribute('aria-pressed', String(state.showDcaHeliRoutes));
    button.textContent = state.showDcaHeliRoutes ? 'DCA HELI ROUTES ON' : 'DCA HELI ROUTES';
  }
  if (chart) chart.hidden = !state.showDcaHeliRoutes;
  if (status) status.hidden = !state.showDcaHeliRoutes;
  document.querySelectorAll('.dca-heli-legend').forEach(item => { item.hidden = !state.showDcaHeliRoutes; });
}

function renderDcaHeliRoutes(focus = false) {
  if (dcaHeliRouteLayerGroup) {
    map.removeLayer(dcaHeliRouteLayerGroup);
    dcaHeliRouteLayerGroup = null;
  }
  updateDcaHeliRouteUi();
  if (!state.showDcaHeliRoutes) return;
  const layers = [];
  for (const route of DCA_HELI_ROUTES) {
    const line = L.polyline(route.points, {
      pane: 'dcaHeliRoutes', renderer: pathRenderer, color: route.color,
      weight: route.closed ? 3.2 : 2.6, opacity: route.closed ? 0.95 : 0.9,
      dashArray: route.closed ? '8 6' : '12 6', interactive: true,
    });
    line.bindTooltip(`${route.name} · ${route.status}`, { className: `dca-heli-tooltip${route.closed ? ' closed' : ''}`, sticky: true, direction: 'top' });
    line.bindPopup(dcaHeliRoutePopup(route), { maxWidth: 330 });
    layers.push(line);
    const labelPoint = route.points[Math.floor(route.points.length / 2)];
    layers.push(L.marker(labelPoint, {
      pane: 'dcaHeliRoutes', interactive: false,
      icon: L.divIcon({ className: '', iconSize: [150, 24], iconAnchor: [75, 12], html: `<div class="dca-heli-map-label${route.closed ? ' closed' : ''}">${escapeHtml(route.name)}</div>` }),
    }));
  }
  const blackjackMarker = L.circleMarker(BLACKJACK_KDCA, {
    pane: 'dcaHeliRoutes', radius: 7, color: '#71f6ff', weight: 2,
    fillColor: '#071419', fillOpacity: 0.95,
  }).bindTooltip('KDCA · USCG BLACKJACK NCRAD REFERENCE', { className: 'dca-heli-tooltip', direction: 'top' })
    .bindPopup(`<div class="dca-heli-popup blackjack"><span>USCG NCR AIR DEFENSE</span><strong>BLACKJACK · KDCA REFERENCE</strong><em>LIVE VATSIM TRACKS REQUIRE BLACKJACK CALLSIGN OR USCG/BLACKJACK REMARKS</em><p>This marker is an airport reference point, not a depiction of a real-world facility location.</p></div>`, { maxWidth: 330 });
  layers.push(blackjackMarker);
  dcaHeliRouteLayerGroup = L.layerGroup(layers).addTo(map);
  if (focus) map.fitBounds(L.latLngBounds(DCA_HELI_ROUTES.flatMap(route => route.points)), { padding: [35,35], maxZoom: 11 });
}

function toggleDcaHeliRoutes() {
  state.showDcaHeliRoutes = !state.showDcaHeliRoutes;
  try { localStorage.setItem('vng-adoc.dca-heli-routes', state.showDcaHeliRoutes ? '1' : '0'); } catch (_) {}
  renderDcaHeliRoutes(state.showDcaHeliRoutes);
}

function setIconMode(mode) {
  if (!['scope', 'tactical'].includes(mode) || mode === state.iconMode) return;
  state.iconMode = mode;
  document.querySelectorAll('.icon-mode').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
  renderAircraft(state.data?.pilots || [], true);
}

function renderAlerts(alerts, force = false) {
  const focusCallsigns = focusedPilotCallsigns();
  const visibleAlerts = focusedAlerts(alerts);
  const operations = (state.data?.operations || []).filter(operation => !focusCallsigns || focusCallsigns.has(operation.callsign));
  const watches = focusedPilots(state.data?.pilots || [])
    .filter(pilot => pilot.nordo_watch)
    .sort((a, b) => (b.nordo_watch?.confidence || 0) - (a.nordo_watch?.confidence || 0));
  const renderKey = compactJson({
    selectedCallsign: state.selectedCallsign,
    selectedOperationId: state.selectedOperationId,
    localAck: [...state.localAcknowledged].sort(),
    alerts: visibleAlerts.map(alert => [alert.id, alert.callsign, alert.severity, alert.confidence, alert.title, alert.active_interceptors?.length || 0]),
    watches: watches.map(pilot => [pilot.callsign, pilot.nordo_watch?.title, pilot.nordo_watch?.level, pilot.nordo_watch?.duration_seconds, pilot.mass_alert_verification_pending, pilot.mass_alert_verification?.stable_snapshots, pilot.automatic_flag_dismissed]),
    operations: operations.map(operation => [operation.id, operation.status, operation.active, operation.completed, operation.accepted_count, operation.updated_at]),
  });
  if (!force && renderKey === state.alertsRenderKey) return;
  state.alertsRenderKey = renderKey;

  el('alert-count').textContent = visibleAlerts.length;
  const list = el('alert-list');
  const operationById = new Map(operations.map(operation => [operation.id, operation]));
  el('nordo-watch-count').textContent = watches.length;
  el('nordo-watch-list').innerHTML = watches.length
    ? watches.map(pilot => `<button type="button" class="nordo-watch-card ${escapeHtml(pilot.nordo_watch.level || 'yellow')} ${state.selectedCallsign === pilot.callsign ? 'selected' : ''}" data-call="${escapeHtml(pilot.callsign)}" title="Center map on ${escapeHtml(pilot.callsign)}">
        <span class="alert-top"><strong>${escapeHtml(pilot.callsign)}</strong><em>${formatDuration(pilot.nordo_watch.duration_seconds)}</em></span>
        <span class="alert-title">${escapeHtml(pilot.nordo_watch.title || 'NORDO WATCH')}</span>
        <span class="alert-meta">${escapeHtml(pilot.nordo_watch.controller || 'ATC')} · ${formatDuration(pilot.nordo_watch.duration_seconds)} · ${Number(pilot.altitude || 0).toLocaleString()} FT</span>
        ${pilot.mass_alert_verification_pending ? `<span class="case-state-badge burst-verify">INDEPENDENT VERIFY ${pilot.mass_alert_verification?.stable_snapshots || 0}/${pilot.mass_alert_verification?.required_snapshots || 0}</span>` : ''}
        ${pilot.automatic_flag_dismissed ? '<span class="case-state-badge dismissed">AUTO FLAG DISMISSED · MONITOR</span>' : ''}
        ${pilot.frequency_mismatch_case_status && pilot.frequency_mismatch_case_status !== 'MISMATCH' ? `<span class="case-state-badge">${escapeHtml(String(pilot.frequency_mismatch_case_status).replaceAll('_', ' '))}</span>` : ''}
      </button>`).join('')
    : '<div class="empty compact-empty">NO ACTIVE COMMUNICATIONS WATCHES</div>';

  const activeHtml = visibleAlerts.length
    ? visibleAlerts.map(alert => {
      const operation = operationById.get(alert.id);
      const acceptedCount = operation?.accepted_count || 0;
      return `
      <button type="button" class="alert-card ${alert.severity} ${state.selectedCallsign === alert.callsign ? 'selected' : ''}" data-call="${escapeHtml(alert.callsign)}" data-operation-id="${escapeHtml(alert.id)}" title="Center map on ${escapeHtml(alert.callsign)}">
        <span class="alert-top"><strong>${escapeHtml(alert.callsign)}</strong><em>${alert.confidence}%</em></span>
        <span class="alert-title">${escapeHtml(alert.title)}</span>
        <span class="alert-meta">${escapeHtml(alert.aircraft)} · ${Number(alert.altitude || 0).toLocaleString()} FT · ${alert.groundspeed || 0} KT</span>
        ${alert.active_interceptors?.length ? `<span class="intercept-badge">${alert.active_interceptors.map(item => escapeHtml(item.callsign)).join(' / ')} · ${alert.active_interceptors.some(item => item.manual) ? 'MANUAL ASSIGNMENT' : 'SQ 7777'}</span>` : ''}
        ${alert.alarm_group_key ? `<span class="incident-badge ${alert.alarm_suppressed ? 'grouped' : 'primary'}">${alert.alarm_suppressed ? 'GROUPED TRACK · NO ADDITIONAL ALARM' : 'PRIMARY AUDIBLE INCIDENT'} · ${escapeHtml(alert.alarm_group_key)}</span>` : ''}
        ${acceptedCount ? `<span class="response-badge">${acceptedCount} CONSOLE${acceptedCount === 1 ? '' : 'S'} INBOUND</span>` : '<span class="response-badge waiting">AWAITING QRA ACCEPTANCE</span>'}
        ${state.localAcknowledged.has(alert.id) ? '<span class="ack-badge">ACKNOWLEDGED ON THIS CONSOLE</span>' : ''}
      </button>`;
    }).join('')
    : '<div class="empty">NO ACTIVE INTERCEPT ALERTS</div>';

  const recent = operations
    .filter(operation => !operation.active || operation.completed)
    .slice(0, 8);
  const recentHtml = recent.length
    ? `<div class="case-heading">RECENT NORAD CASES</div>${recent.map(operation => `
      <button type="button" class="case-card ${state.selectedOperationId === operation.id ? 'selected' : ''}" data-operation="${escapeHtml(operation.id)}" data-call="${escapeHtml(operation.callsign)}">
        <span><strong>${escapeHtml(operation.callsign)}</strong><em>${escapeHtml(operation.status || 'CASE')}</em></span>
        <small>${operation.accepted_count || 0} INBOUND · ${formatZulu(operation.updated_at)}</small>
        <small>${escapeHtml((operation.detector_codes || []).join(' / ') || 'NO DETECTOR CODE')} · ${operation.alarm_group_key ? `${operation.alarm_suppressed ? 'GROUPED' : 'PRIMARY'} ${escapeHtml(operation.alarm_group_key)}` : 'INDIVIDUAL INCIDENT'}</small>
      </button>`).join('')}`
    : '';
  list.innerHTML = activeHtml + recentHtml;
}

function formatFreqs(values) {
  return values?.length ? values.map(value => Number(value).toFixed(3)).join(' / ') : 'NONE REPORTED';
}

function formatPilotRadios(pilot) {
  const roles = new Map((pilot?.monitor_only_frequencies || []).map(item => [
    Number(item.frequency).toFixed(3),
    String(item.role || 'MONITOR ONLY'),
  ]));
  if (!pilot?.frequencies?.length) return 'NONE REPORTED';
  return pilot.frequencies.map(value => {
    const formatted = Number(value).toFixed(3);
    const role = roles.get(formatted);
    return role ? `${formatted} (${role} · NOT ATC CONTACT)` : formatted;
  }).join(' / ');
}

function formatZulu(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? `${date.toISOString().slice(11, 19)}Z` : '—';
}

function pilotForCallsign(callsign) {
  const value = normaliseCallsign(callsign);
  return state.data?.pilots?.find(item => item.callsign === value) || null;
}

function interceptTrackPreviewHtml(callsign, role) {
  const value = normaliseCallsign(callsign);
  if (!value) return role === 'target' ? 'SELECT THE AIRCRAFT BEING INTERCEPTED' : 'SELECT THE RESPONDING AIRCRAFT';
  const pilot = pilotForCallsign(value);
  if (!pilot) return `<span class="error-text">${escapeHtml(value)} IS NOT IN THE CURRENT LIVE FEED</span>`;
  const likely = pilot.active_intercept || pilot.aircraft_category === 'fighter' || pilot.vsoa;
  return `<strong>${escapeHtml(pilot.callsign)}</strong> · ${escapeHtml(pilot.aircraft || pilot.aircraft_type || 'UNKNOWN')} · ${Number(pilot.altitude || 0).toLocaleString()} FT · ${pilot.groundspeed || 0} KT · HDG ${String(normaliseHeading(pilot.heading)).padStart(3, '0')}°${role === 'interceptor' && !likely ? '<br><em>NOT IDENTIFIED AS A FIGHTER / SQ 7777 TRACK — MANUAL ASSIGNMENT STILL ALLOWED</em>' : ''}`;
}

function renderVsoaInterceptorRecommendations() {
  const host = el('vsoa-interceptor-recommendations');
  const target = pilotForCallsign(el('intercept-target-input')?.value);
  if (!host) return;
  if (!target) {
    host.innerHTML = '<div class="empty compact-empty">SELECT A TARGET TO RANK ACTIVE VSOA AIRCRAFT</div>';
    return;
  }
  const assigned = new Map((state.data?.manual_intercepts || []).map(item => [item.interceptor_callsign, item.target_callsign]));
  const recommendations = (state.data?.pilots || [])
    .filter(pilot => pilot.vsoa && !pilot.on_ground && pilot.callsign !== target.callsign)
    .map(pilot => ({ pilot, distance: distanceNmBetween(pilot, target), assignedTarget: assigned.get(pilot.callsign) }))
    .sort((a, b) => a.distance - b.distance || String(a.pilot.callsign).localeCompare(String(b.pilot.callsign)))
    .slice(0, 6);
  host.innerHTML = recommendations.length ? recommendations.map(({ pilot, distance, assignedTarget }, index) => `<button type="button" class="vsoa-recommendation${assignedTarget ? ' assigned' : ''}" data-recommended-interceptor="${escapeHtml(pilot.callsign)}"><span><b>#${index + 1} ${escapeHtml(pilot.callsign)}</b><em>${escapeHtml(pilot.vsoa_label || 'VSOA')}</em></span><strong>${Number.isFinite(distance) ? distance.toFixed(0) : '—'} NM</strong><small>${escapeHtml(pilot.aircraft || pilot.aircraft_type || 'UNKNOWN')} · ${Number(pilot.altitude || 0).toLocaleString()} FT · ${pilot.groundspeed || 0} KT${assignedTarget ? ` · ASSIGNED TO ${escapeHtml(assignedTarget)}` : ''}</small></button>`).join('') : '<div class="empty compact-empty">NO AIRBORNE VSOA-TAGGED AIRCRAFT IN THE LIVE FEED</div>';
}

function refreshInterceptBuilderPreviews() {
  const targetInput = el('intercept-target-input');
  const interceptorInput = el('intercept-interceptor-input');
  if (!targetInput || !interceptorInput) return;
  const targetPreview = el('intercept-target-preview');
  const interceptorPreview = el('intercept-interceptor-preview');
  const targetPilot = pilotForCallsign(targetInput.value);
  const interceptorPilot = pilotForCallsign(interceptorInput.value);
  targetPreview.innerHTML = interceptTrackPreviewHtml(targetInput.value, 'target');
  interceptorPreview.innerHTML = interceptTrackPreviewHtml(interceptorInput.value, 'interceptor');
  targetPreview.classList.toggle('valid', Boolean(targetPilot));
  interceptorPreview.classList.toggle('valid', Boolean(interceptorPilot));
  renderVsoaInterceptorRecommendations();
}

function setInterceptFeedback(message, status = '') {
  const feedback = el('intercept-console-feedback');
  if (!feedback) return;
  feedback.textContent = message;
  feedback.classList.toggle('error', status === 'error');
  feedback.classList.toggle('success', status === 'success');
}

function renderInterceptConsole() {
  const assignments = state.data?.manual_intercepts || [];
  const count = assignments.length;
  if (el('intercept-console-count')) el('intercept-console-count').textContent = String(count);
  if (el('manual-intercept-count')) el('manual-intercept-count').textContent = `${count} ACTIVE`;
  const options = el('intercept-aircraft-options');
  if (options) {
    const target = pilotForCallsign(el('intercept-target-input')?.value);
    const pilots = [...(state.data?.pilots || [])].sort((a, b) => {
      const aRank = a.vsoa && !a.on_ground ? 0 : a.active_intercept ? 1 : a.aircraft_category === 'fighter' ? 2 : a.vsoa ? 3 : 4;
      const bRank = b.vsoa && !b.on_ground ? 0 : b.active_intercept ? 1 : b.aircraft_category === 'fighter' ? 2 : b.vsoa ? 3 : 4;
      const distanceOrder = target && aRank === 0 && bRank === 0 ? distanceNmBetween(a, target) - distanceNmBetween(b, target) : 0;
      return aRank - bRank || distanceOrder || String(a.callsign).localeCompare(String(b.callsign));
    });
    options.innerHTML = pilots.map(pilot => `<option value="${escapeHtml(pilot.callsign)}" label="${escapeHtml(`${pilot.aircraft || pilot.aircraft_type || 'UNKNOWN'} · ${Number(pilot.altitude || 0).toLocaleString()} FT · ${pilot.groundspeed || 0} KT${pilot.active_intercept ? ' · INTERCEPT' : pilot.vsoa ? ' · VSOA' : ''}`)}"></option>`).join('');
  }
  const list = el('manual-intercept-list');
  if (list) {
    list.innerHTML = assignments.length ? assignments.map(assignment => {
      const live = assignment.live !== false;
      const closure = String(assignment.closure_status || '').toUpperCase();
      const closureClass = !live ? 'lost' : closure === 'OPENING' ? 'opening' : '';
      const status = !live ? `TRACK LOST · ${assignment.missing_seconds || 0}s` : closure || assignment.status || 'ACTIVE';
      const interceptor = assignment.interceptor || {};
      const target = assignment.target || {};
      return `<article class="manual-intercept-card${live ? '' : ' track-lost'}">
        <div class="manual-intercept-card-header"><strong>${escapeHtml(assignment.interceptor_callsign)} → ${escapeHtml(assignment.target_callsign)}</strong><span class="${closureClass}">${escapeHtml(status)}</span></div>
        <div class="manual-intercept-primary">
          <div><span>INTERCEPT ETA</span><strong>${escapeHtml(formatInterceptEta(assignment))}</strong></div>
          <div><span>SEPARATION</span><strong>${assignment.separation_nm ?? '—'} NM</strong></div>
          <div><span>CLOSURE</span><strong>${escapeHtml(formatClosure(assignment))}</strong></div>
          <div><span>COURSE</span><strong>${assignment.recommended_course_deg == null ? '—' : String(assignment.recommended_course_deg).padStart(3, '0') + '°'}</strong></div>
        </div>
        <div class="manual-intercept-tracks">
          <div><span>INTERCEPTOR · ${escapeHtml(assignment.interceptor_callsign)}</span><strong>${Number(interceptor.altitude || assignment.interceptor_altitude_ft || 0).toLocaleString()} FT · ${interceptor.groundspeed ?? assignment.interceptor_speed_kt ?? '—'} KT · HDG ${String(interceptor.heading ?? assignment.interceptor_heading_deg ?? 0).padStart(3, '0')}°</strong></div>
          <div><span>TARGET · ${escapeHtml(assignment.target_callsign)}</span><strong>${Number(target.altitude || assignment.target_altitude_ft || 0).toLocaleString()} FT · ${target.groundspeed ?? assignment.target_speed_kt ?? '—'} KT · HDG ${String(target.heading ?? assignment.target_heading_deg ?? 0).padStart(3, '0')}°</strong></div>
        </div>
        <div class="manual-intercept-card-actions"><button type="button" data-intercept-focus="${escapeHtml(assignment.interceptor_callsign)}" data-intercept-target="${escapeHtml(assignment.target_callsign)}">FOCUS / MANAGE</button><button type="button" class="danger" data-intercept-cancel="${escapeHtml(assignment.interceptor_callsign)}">CANCEL ASSIGNMENT</button></div>
      </article>`;
    }).join('') : '<div class="empty">NO MANUAL INTERCEPT ASSIGNMENTS</div>';
  }
  if (state.interceptConsoleOpen) refreshInterceptBuilderPreviews();
}

function openInterceptConsole(preferredRole = 'target', callsign = state.selectedCallsign) {
  if (!state.interceptConsoleOpen && !el('intercept-console-modal')?.contains(document.activeElement)) {
    state.interceptPreviousFocus = document.activeElement;
  }
  state.interceptConsoleOpen = true;
  const modal = el('intercept-console-modal');
  modal.hidden = false;
  document.body.classList.add('intercept-console-open');
  const selected = pilotForCallsign(callsign);
  const targetInput = el('intercept-target-input');
  const interceptorInput = el('intercept-interceptor-input');
  const existing = (state.data?.manual_intercepts || []).find(item => item.interceptor_callsign === selected?.callsign);
  if (existing) {
    interceptorInput.value = existing.interceptor_callsign;
    targetInput.value = existing.target_callsign;
  } else if (selected) {
    if (preferredRole === 'interceptor') interceptorInput.value = selected.callsign;
    else targetInput.value = selected.callsign;
  }
  renderInterceptConsole();
  setInterceptFeedback('Assignments are shared across all connected consoles and recalculate with each VATSIM feed update.');
  setTimeout(() => (preferredRole === 'interceptor' ? targetInput : interceptorInput).focus(), 0);
}

function closeInterceptConsole() {
  const wasOpen = state.interceptConsoleOpen;
  state.interceptConsoleOpen = false;
  el('intercept-console-modal').hidden = true;
  document.body.classList.remove('intercept-console-open');
  if (wasOpen) restoreStoredFocus('interceptPreviousFocus');
}

function focusInterceptPair(interceptorCallsign, targetCallsign) {
  const interceptor = pilotForCallsign(interceptorCallsign);
  const target = pilotForCallsign(targetCallsign);
  if (interceptor) selectTrack(interceptor.callsign, false);
  if (interceptor && target) {
    map.fitBounds([[interceptor.lat, interceptor.lon], [target.lat, target.lon]], { padding: [70, 70], maxZoom: 8, animate: true, duration: 0.65 });
  } else if (interceptor) {
    focusTrackOnMap(interceptor.callsign);
  }
}

async function assignManualIntercept() {
  const targetCallsign = normaliseCallsign(el('intercept-target-input').value);
  const interceptorCallsign = normaliseCallsign(el('intercept-interceptor-input').value);
  if (!targetCallsign || !interceptorCallsign) {
    setInterceptFeedback('Select both a target and an interceptor.', 'error');
    return;
  }
  if (targetCallsign === interceptorCallsign) {
    setInterceptFeedback('The target and interceptor must be different aircraft.', 'error');
    return;
  }
  if (!pilotForCallsign(targetCallsign) || !pilotForCallsign(interceptorCallsign)) {
    setInterceptFeedback('Both callsigns must be present in the current live VATSIM feed.', 'error');
    return;
  }
  const button = el('assign-manual-intercept');
  button.disabled = true;
  button.textContent = 'ASSIGNING…';
  try {
    const response = await fetchWithTimeout('/api/intercepts/manual', {
      method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ interceptor_callsign: interceptorCallsign, target_callsign: targetCallsign, console_id: state.consoleId, console_label: state.consoleLabel }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `assignment_${response.status}`);
    await loadLive(true);
    state.selectedCallsign = interceptorCallsign;
    if (state.workspaceTab === 'atc') renderAtcWorkspace(true);
    renderInterceptOverlay(true);
    renderInterceptConsole();
    state.activeInterceptKey = `manual:${interceptorCallsign}`;
    setInterceptFeedback(`${interceptorCallsign} is now assigned to intercept ${targetCallsign}. Live geometry is updating.`, 'success');
    closeInterceptConsole();
    setWorkspaceTab('intercept');
  } catch (error) {
    console.error(error);
    setInterceptFeedback(`Assignment failed: ${String(error.message || error).replaceAll('_', ' ')}`, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'ASSIGN / UPDATE INTERCEPT';
  }
}

async function cancelManualIntercept(interceptorCallsign) {
  const callsign = normaliseCallsign(interceptorCallsign);
  if (!callsign) return;
  if (!window.confirm(`Cancel the manual intercept assignment for ${callsign}?`)) return;
  try {
    const response = await fetchWithTimeout(`/api/intercepts/manual/${encodeURIComponent(callsign)}`, {
      method: 'DELETE', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ console_id: state.consoleId, console_label: state.consoleLabel }),
    });
    if (!response.ok) throw new Error(`cancel_${response.status}`);
    await loadLive(true);
    renderInterceptConsole();
    if (state.workspaceTab === 'atc') renderAtcWorkspace(true);
    renderInterceptOverlay(true);
    setInterceptFeedback(`${callsign} manual assignment canceled.`, 'success');
  } catch (error) {
    console.error(error);
    setInterceptFeedback('Unable to cancel the assignment. Retry.', 'error');
  }
}

function operationForSelection() {
  const operations = state.data?.operations || [];
  return operations.find(item => item.id === state.selectedOperationId)
    || operations.find(item => item.callsign === state.selectedCallsign && item.active)
    || operations.find(item => item.callsign === state.selectedCallsign)
    || null;
}

function timelineHtml(operation) {
  if (!operation) return '';
  const events = [...(operation.events || [])];
  if (state.localAcknowledged.has(operation.id)) {
    events.push({ time: new Date().toISOString(), label: 'Acknowledged on this console', detail: 'Local browser acknowledgment; other operators remain unaffected', local: true });
  }
  const rows = events.length
    ? events.map(event => `<div class="timeline-event${event.local ? ' local' : ''}"><time>${formatZulu(event.time)}</time><span><strong>${escapeHtml(event.label)}</strong>${event.detail ? `<small>${escapeHtml(event.detail)}</small>` : ''}</span></div>`).join('')
    : '<div class="empty">NO TIMELINE EVENTS</div>';
  return `<div class="timeline-block"><div class="section-label">NORAD EVENT TIMELINE · ${escapeHtml(operation.status || 'ACTIVE CASE')}</div>${rows}</div>`;
}

function operationActionsHtml(operation) {
  if (!operation) return '';
  const accepted = operation.accepted_console_list || [];
  const acceptedHere = operationAcceptedByThisConsole(operation);
  const responders = accepted.length
    ? accepted.map(item => `<span class="responder-chip${item.console_id === state.consoleId ? ' local' : ''}"><b>${escapeHtml(item.label || item.console_id)}</b><small>${escapeHtml(item.status || 'INBOUND')} · ${formatZulu(item.accepted_at)}</small></span>`).join('')
    : '<span class="no-responders">NO CONSOLES HAVE ACCEPTED THIS INTERCEPT</span>';
  const responseControl = operation.active && !operation.completed
    ? `<button type="button" class="${acceptedHere ? 'secondary' : 'accept-intercept'}" data-operation-response="${acceptedHere ? 'release' : 'accept'}" data-operation-id="${escapeHtml(operation.id)}">${acceptedHere ? 'RELEASE / NO LONGER INBOUND' : 'ACCEPT INTERCEPT · MARK INBOUND'}</button>`
    : '';
  const phases = operation.phases || [];
  const completeCount = phases.filter(phase => phase.complete).length;
  const progress = phases.length ? Math.round((completeCount / phases.length) * 100) : 0;
  const nextPhase = phases.find(phase => !phase.complete && (phase.id !== 'qra_accepted' || accepted.length));
  const nextAction = nextPhase
    ? `<div class="workflow-next"><span><b>NEXT ACTION</b><small>${escapeHtml(nextPhase.label || nextPhase.id)}</small></span><button type="button" data-operation-phase="${escapeHtml(nextPhase.id)}" data-operation-phase-complete="true" data-operation-id="${escapeHtml(operation.id)}">MARK COMPLETE</button></div>`
    : !accepted.length && operation.active
      ? '<div class="workflow-next waiting"><span><b>NEXT ACTION</b><small>Accept the intercept to begin the shared workflow.</small></span></div>'
      : '<div class="workflow-next complete"><span><b>WORKFLOW COMPLETE</b><small>All shared phases are marked complete.</small></span></div>';
  const phaseRows = phases.map(phase => `<button type="button" class="phase-check ${phase.complete ? 'complete' : ''}" data-operation-phase="${escapeHtml(phase.id)}" data-operation-phase-complete="${phase.complete ? 'false' : 'true'}" data-operation-id="${escapeHtml(operation.id)}" ${operation.completed && phase.id !== 'returned_to_base' ? 'disabled' : ''}>
      <span class="phase-box">${phase.complete ? '✓' : ''}</span>
      <span><strong>${escapeHtml(phase.label || phase.id)}</strong><small>${phase.complete ? `${escapeHtml(phase.completed_by || 'CONSOLE')} · ${formatZulu(phase.completed_at)}` : 'PENDING'}</small></span>
    </button>`).join('');
  return `<div class="intercept-workflow">
    <div class="workflow-heading"><span>SHARED INTERCEPT RESPONSE · QRA CONSOLES INBOUND</span><strong>${accepted.length} CONSOLE${accepted.length === 1 ? '' : 'S'} INBOUND</strong></div>
    <div class="workflow-progress"><span><b>${completeCount} / ${phases.length} PHASES</b><small>${escapeHtml(operation.status || 'ACTIVE CASE')}</small></span><div><i style="width:${progress}%"></i></div><strong>${progress}%</strong></div>
    ${nextAction}
    <div class="responder-list">${responders}</div>
    ${responseControl}
    <details class="phase-details"><summary>INTERCEPT PHASE CHECKLIST · ${completeCount}/${phases.length} COMPLETE</summary><div class="phase-list">${phaseRows}</div></details>
  </div>`;
}

function focusTrackOnMap(callsign) {
  const pilot = state.data?.pilots?.find(item => item.callsign === callsign);
  if (!pilot) return false;
  const lat = Number(pilot.lat);
  const lon = Number(pilot.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;

  const targetZoom = Math.max(map.getZoom(), 7);
  map.flyTo([lat, lon], targetZoom, { animate: true, duration: 0.65, easeLinearity: 0.25 });
  const record = aircraftLayers.get(callsign);
  if (record?.marker) {
    map.once('moveend', () => {
      if (map.hasLayer(record.marker)) record.marker.openPopup();
    });
  }
  return true;
}

function selectTrack(callsign, focusMap = false, operationId = null) {
  const previous = state.selectedCallsign;
  state.selectedCallsign = callsign;
  if (callsign) {
    fetchTrackHistory(callsign);
    fetchTrackDetail(callsign);
  }
  state.selectedOperationId = operationId
    || state.data?.operations?.find(item => item.callsign === callsign && item.active)?.id
    || null;
  if (previous !== callsign) renderAircraft(state.data?.pilots || [], true);
  renderAlerts(state.data?.alerts || []);
  renderInterceptOverlay();
  renderFlightPlanPreview(callsign);
  if (focusMap) focusTrackOnMap(callsign);
}

function selectOperation(operationId, focusMap = true) {
  const operation = state.data?.operations?.find(item => item.id === operationId);
  if (!operation) return;
  state.selectedOperationId = operationId;
  state.selectedCallsign = operation.callsign;
  renderAircraft(state.data?.pilots || [], true);
  renderAlerts(state.data?.alerts || []);
  renderInterceptOverlay();
  renderFlightPlanPreview(operation.callsign);
  if (focusMap && !focusTrackOnMap(operation.callsign)) {
    const lat = Number(operation.lat);
    const lon = Number(operation.lon);
    if (Number.isFinite(lat) && Number.isFinite(lon)) map.flyTo([lat, lon], Math.max(map.getZoom(), 7), { animate: true, duration: 0.65 });
  }
}

async function manualNordoAction(callsign, action) {
  if (!callsign || !['mark', 'clear'].includes(action)) return;
  const message = action === 'mark'
    ? `Mark ${callsign} as NORDO? This will create a shared red intercept alert and sound the scramble alarm on unacknowledged consoles.`
    : `Clear the manual NORDO designation for ${callsign}?`;
  if (!window.confirm(message)) return;
  try {
    const response = await fetchWithTimeout(`/api/tracks/${encodeURIComponent(callsign)}/manual-nordo`, {
      method: action === 'mark' ? 'POST' : 'DELETE',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`Manual NORDO ${response.status}`);
    el('system-health').textContent = action === 'mark' ? `${callsign} MARKED NORDO — SHARED ALERT ACTIVE` : `${callsign} MANUAL NORDO CLEARED`;
    await loadLive(true);
    state.selectedCallsign = callsign;
    if (state.workspaceTab === 'atc') renderAtcWorkspace(true);
  } catch (error) {
    console.error(error);
    el('system-health').textContent = 'MANUAL NORDO UPDATE FAILED — RETRY';
    el('system-health').classList.add('error-text');
  }
}

async function operationResponseAction(id, action) {
  if (!id || !['accept', 'release'].includes(action)) return;
  try {
    const url = action === 'accept'
      ? `/api/operations/${encodeURIComponent(id)}/accept`
      : `/api/operations/${encodeURIComponent(id)}/accept/${encodeURIComponent(state.consoleId)}`;
    const response = await fetchWithTimeout(url, {
      method: action === 'accept' ? 'POST' : 'DELETE',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: action === 'accept' ? JSON.stringify({ console_id: state.consoleId, console_label: state.consoleLabel }) : undefined,
    });
    if (!response.ok) throw new Error(`Operation response ${response.status}`);
    state.alertsRenderKey = null;
    await loadLive(true);
    state.selectedOperationId = id;
    if (state.workspaceTab === 'atc') renderAtcWorkspace(true);
  } catch (error) {
    console.error(error);
    el('system-health').textContent = 'INTERCEPT ACCEPTANCE UPDATE FAILED — RETRY';
    el('system-health').classList.add('error-text');
  }
}

async function toggleOperationPhase(id, phaseId, complete) {
  if (!id || !phaseId) return;
  try {
    const response = await fetchWithTimeout(`/api/operations/${encodeURIComponent(id)}/phases/${encodeURIComponent(phaseId)}`, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ complete: Boolean(complete), console_id: state.consoleId, console_label: state.consoleLabel }),
    });
    if (!response.ok) throw new Error(`Operation phase ${response.status}`);
    state.alertsRenderKey = null;
    await loadLive(true);
    state.selectedOperationId = id;
    if (state.workspaceTab === 'atc') renderAtcWorkspace(true);
  } catch (error) {
    console.error(error);
    el('system-health').textContent = 'INTERCEPT PHASE UPDATE FAILED — RETRY';
    el('system-health').classList.add('error-text');
  }
}

async function advanceOperation(id, stage) {
  if (!id || !stage) return;
  try {
    const response = await fetchWithTimeout(`/api/operations/${encodeURIComponent(id)}/${encodeURIComponent(stage)}`, { method: 'POST', cache: 'no-store' });
    if (!response.ok) throw new Error(`Operation ${response.status}`);
    await loadLive(true);
    state.selectedOperationId = id;
    if (state.workspaceTab === 'atc') renderAtcWorkspace(true);
  } catch (error) {
    console.error(error);
    el('system-health').textContent = 'OPERATION UPDATE FAILED — RETRY';
    el('system-health').classList.add('error-text');
  }
}

function loadLocalAcknowledgments() {
  try {
    const values = JSON.parse(localStorage.getItem('vng-adoc.local-acknowledged') || '[]');
    state.localAcknowledged = new Set(Array.isArray(values) ? values : []);
  } catch (_) {
    state.localAcknowledged = new Set();
  }
}

function saveLocalAcknowledgments() {
  try { localStorage.setItem('vng-adoc.local-acknowledged', JSON.stringify([...state.localAcknowledged])); } catch (_) { /* unavailable */ }
}

function syncLocalAcknowledgments(alerts) {
  const activeIds = new Set((alerts || []).map(alert => alert.id));
  let changed = false;
  for (const id of [...state.localAcknowledged]) {
    if (!activeIds.has(id)) {
      state.localAcknowledged.delete(id);
      changed = true;
    }
  }
  if (changed) saveLocalAcknowledgments();
}

async function alertAction(id, action) {
  if (!id) return;
  if (action === 'ack') {
    state.localAcknowledged.add(id);
    saveLocalAcknowledgments();
    if (state.activeScrambleId === id) state.activeScrambleId = null;
    stopScrambleAlarm();
    setScrambleModalVisible(false);
    el('system-health').textContent = 'ALERT ACKNOWLEDGED ON THIS CONSOLE';
    renderAlerts(state.data?.alerts || []);
    if (state.workspaceTab === 'atc') renderAtcWorkspace(true);
    renderMandatoryScramble(state.data?.alerts || [], state.data?.scramble_alarm_confidence || 90);
    return;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`/api/alerts/${encodeURIComponent(id)}/${action}`, {
      method: 'POST',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Alert action failed: ${response.status}`);
    const result = await response.json();
    if (!result.ok) throw new Error('Alert action was rejected');
    if (action === 'dismiss') state.selectedCallsign = null;
    el('system-health').textContent = 'ALERT DISMISSED';
    await loadLive(true);
  } catch (error) {
    console.error(error);
    el('system-health').textContent = 'ALERT ACTION FAILED — RETRY';
    el('system-health').classList.add('error-text');
  } finally {
    clearTimeout(timeout);
  }
}

function loadAlertPreferences() {
  try {
    const storedSound = localStorage.getItem('vng-adoc.alert-sound');
    const storedPopup = localStorage.getItem('vng-adoc.alert-popup');
    const storedVolume = Number(localStorage.getItem('vng-adoc.alert-volume'));
    state.soundEnabled = storedSound === null ? true : storedSound === 'true';
    state.popupEnabled = storedPopup === null ? true : storedPopup === 'true';
    state.alertVolume = Number.isFinite(storedVolume) && storedVolume >= 0 && storedVolume <= 1 ? storedVolume : 0.70;
  } catch (_) {
    state.soundEnabled = true;
    state.popupEnabled = true;
    state.alertVolume = 0.70;
  }
  updateAlertPreferenceControls();
}

function saveAlertPreference(key, value) {
  try { localStorage.setItem(key, String(value)); } catch (_) { /* browser storage unavailable */ }
}

function updateAlertPreferenceControls() {
  const soundButton = el('toggle-alert-sound');
  const popupButton = el('toggle-alert-popup');
  soundButton.classList.toggle('active', state.soundEnabled);
  soundButton.setAttribute('aria-pressed', String(state.soundEnabled));
  soundButton.textContent = state.soundEnabled ? '🔊 ALERT SOUNDS ON' : '🔇 ALERT SOUNDS OFF';
  popupButton.classList.toggle('active', state.popupEnabled);
  popupButton.setAttribute('aria-pressed', String(state.popupEnabled));
  popupButton.textContent = state.popupEnabled ? '▣ ALERT POPUPS ON' : '□ ALERT POPUPS OFF';
  const volume = el('alert-volume');
  const output = el('alert-volume-value');
  if (volume) volume.value = String(Math.round(state.alertVolume * 100));
  if (output) output.textContent = `${Math.round(state.alertVolume * 100)}%`;
}

function prepareAlarmAudio() {
  if (!state.alarmAudio) {
    const customSource = '/static/assets/scramble-alarm-upload-20260804.mp3';
    const audio = new Audio();
    audio.preload = 'auto';
    audio.loop = true;
    audio.dataset.customSource = customSource;
    audio.src = customSource;
    audio.addEventListener('canplaythrough', () => {
      const status = el('scramble-audio-status');
      if (status && !audio.paused) return;
      if (status) status.textContent = 'CUSTOM SCRAMBLE ALARM LOADED';
    }, { once: true });
    audio.addEventListener('error', () => {
      const status = el('scramble-audio-status');
      if (status) status.textContent = 'CUSTOM ALARM FAILED TO LOAD';
    });
    audio.load();
    state.alarmAudio = audio;
  }
  state.alarmAudio.volume = state.alertVolume;
  return state.alarmAudio;
}

async function unlockAlarmAudio(force = false) {
  if (!state.soundEnabled && !force) {
    el('scramble-audio-status').textContent = 'ALERT SOUNDS DISABLED';
    return false;
  }
  const audio = prepareAlarmAudio();
  try {
    audio.muted = true;
    audio.currentTime = 0;
    await audio.play();
    audio.pause();
    audio.currentTime = 0;
    audio.muted = false;
    state.audioArmed = true;
    el('scramble-audio-status').textContent = 'CUSTOM UPLOADED ALARM ARMED';
    return true;
  } catch (_) {
    state.audioArmed = false;
    el('scramble-audio-status').textContent = 'CLICK TEST KLAXON TO ENABLE SOUND';
    return false;
  }
}

async function startScrambleAlarm(force = false, preview = false) {
  if ((!state.soundEnabled && !force)) return;
  if (preview && state.alarmAudio) {
    state.alarmAudio.pause();
    state.alarmAudio.src = state.alarmAudio.dataset.customSource;
    state.alarmAudio.load();
    state.audioArmed = false;
  }
  const unlocked = state.audioArmed || await unlockAlarmAudio(force);
  if (!unlocked) return;
  const audio = prepareAlarmAudio();
  clearTimeout(state.alarmTimer);
  state.alarmTimer = null;
  try {
    audio.pause();
    audio.currentTime = 0;
    audio.loop = !preview;
    await audio.play();
    el('scramble-audio-status').textContent = preview ? 'CUSTOM UPLOADED ALARM TEST PLAYING' : 'CUSTOM UPLOADED ALARM ACTIVE';
    if (preview) {
      state.alarmTimer = setTimeout(() => {
        stopScrambleAlarm();
        el('scramble-audio-status').textContent = 'CUSTOM UPLOADED ALARM ARMED';
      }, 10000);
    }
  } catch (_) {
    el('scramble-audio-status').textContent = 'CLICK TEST KLAXON TO ENABLE SOUND';
  }
}

function stopScrambleAlarm() {
  if (state.alarmTimer) clearTimeout(state.alarmTimer);
  state.alarmTimer = null;
  const audio = state.alarmAudio;
  if (audio) {
    audio.pause();
    try { audio.currentTime = 0; } catch (_) { /* ignore */ }
    audio.loop = true;
  }
}

function setScrambleModalVisible(visible) {
  const modal = el('scramble-modal');
  const next = Boolean(visible);
  if (next && !state.scrambleModalOpen) {
    if (!modal.contains(document.activeElement)) state.scramblePreviousFocus = document.activeElement;
    state.scrambleModalOpen = true;
    modal.hidden = false;
    document.body.classList.add('scramble-lock');
    setTimeout(() => el('acknowledge-scramble')?.focus(), 0);
    return;
  }
  if (next) {
    modal.hidden = false;
    document.body.classList.add('scramble-lock');
    return;
  }
  modal.hidden = true;
  document.body.classList.remove('scramble-lock');
  if (state.scrambleModalOpen) {
    state.scrambleModalOpen = false;
    restoreStoredFocus('scramblePreviousFocus');
  }
}

function pendingPreScrambleWarnings(data = state.rawData || state.data) {
  return (data?.pilots || [])
    .map(pilot => ({ pilot, warning: pilot.pre_scramble_warning }))
    .filter(({ pilot, warning }) => warning?.active && !warning.denied && !pilot.pre_scramble_denied)
    .sort((a, b) => {
      const aDeadline = Number(a.warning.deadline_epoch);
      const bDeadline = Number(b.warning.deadline_epoch);
      if (Number.isFinite(aDeadline) && Number.isFinite(bDeadline)) return aDeadline - bDeadline;
      return Number(a.warning.remaining_seconds || 0) - Number(b.warning.remaining_seconds || 0);
    });
}

function preScrambleCountdownSeconds(warning) {
  const deadline = Number(warning?.deadline_epoch);
  if (Number.isFinite(deadline)) return Math.max(0, Math.ceil(deadline - Date.now() / 1000));
  return Math.max(0, Math.ceil(Number(warning?.remaining_seconds) || 0));
}

function renderPreScrambleWarning(data = state.rawData || state.data) {
  const strip = el('pre-scramble-strip');
  if (!strip) return;
  const warnings = pendingPreScrambleWarnings(data);
  if (!warnings.length) {
    strip.hidden = true;
    const button = el('deny-pre-scramble');
    if (button) {
      button.dataset.callsign = '';
      button.dataset.caseId = '';
    }
    return;
  }

  const { pilot, warning } = warnings[0];
  const callsign = String(pilot.callsign || warning.callsign || 'UNKNOWN').toUpperCase();
  const caseId = String(warning.case_id || pilot.pre_scramble_case_id || '');
  const seconds = preScrambleCountdownSeconds(warning);
  const busy = state.preScrambleBusy.has(caseId);
  strip.hidden = false;
  el('pre-scramble-callsign').textContent = callsign;
  el('pre-scramble-countdown').textContent = state.dataStale ? 'PAUSED' : seconds > 0 ? `${seconds}S` : 'DUE';
  el('pre-scramble-countdown').title = state.dataStale
    ? 'Countdown paused because the live feed is stale'
    : seconds > 0
      ? `Automatic alert eligible in approximately ${seconds} seconds if the verified mismatch continues`
      : 'Threshold reached; waiting for the next fresh feed snapshot';
  el('pre-scramble-controller').textContent = String(warning.controller || pilot.center || 'ATC COVERAGE');
  const button = el('deny-pre-scramble');
  button.dataset.callsign = callsign;
  button.dataset.caseId = caseId;
  button.disabled = busy || state.dataStale;
  button.textContent = busy ? 'DENYING…' : 'DENY AUTO ALERT';
  const more = el('pre-scramble-more');
  more.hidden = warnings.length <= 1;
  more.textContent = warnings.length > 1 ? `+${warnings.length - 1} MORE` : '';
}

async function denyPreScramble(callsign, caseId) {
  if (!callsign || !caseId || state.preScrambleBusy.has(caseId) || state.dataStale) return;
  const confirmed = window.confirm(
    `Deny the automatic scramble alert for ${callsign}? Monitoring will continue, but this communications case will not auto-escalate.`
  );
  if (!confirmed) return;
  state.preScrambleBusy.add(caseId);
  renderPreScrambleWarning();
  try {
    const response = await fetchWithTimeout(`/api/pre-scramble/${encodeURIComponent(callsign)}/deny`, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        case_id: caseId,
        reason: 'Denied during the 30-second pre-scramble review',
        console_id: state.consoleId,
        console_label: state.consoleLabel,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) throw new Error(payload.error || `pre_scramble_${response.status}`);
    el('system-health').textContent = `${callsign} AUTO ALERT DENIED — WATCH REMAINS ACTIVE`;
    el('system-health').classList.remove('error-text');
    await loadLive(true);
  } catch (error) {
    console.error(error);
    el('system-health').textContent = 'PRE-SCRAMBLE DENIAL FAILED — REVIEW CURRENT ALERT STATE';
    el('system-health').classList.add('error-text');
    await loadLive(true);
  } finally {
    state.preScrambleBusy.delete(caseId);
    renderPreScrambleWarning();
  }
}

function renderMandatoryScramble(alerts, threshold) {
  syncLocalAcknowledgments(alerts);
  const pending = (alerts || [])
    .filter(alert => !alert.alarm_suppressed && !state.localAcknowledged.has(alert.id) && (alert.requires_ack || alert.confidence >= threshold))
    .sort((a, b) => b.confidence - a.confidence || b.score - a.score);
  const modal = el('scramble-modal');
  if (!pending.length) {
    setScrambleModalVisible(false);
    state.activeScrambleId = null;
    stopScrambleAlarm();
    return;
  }

  const active = pending.find(alert => alert.id === state.activeScrambleId) || pending[0];
  const changedAlert = state.activeScrambleId !== active.id;
  state.activeScrambleId = active.id;
  if (changedAlert) selectTrack(active.callsign, true, active.id);
  el('scramble-modal-callsign').textContent = active.callsign;
  el('scramble-modal-confidence').textContent = `${active.confidence}% CONFIDENCE`;
  el('scramble-modal-alert-title').textContent = active.title;
  el('scramble-modal-reasons').innerHTML = (active.reasons || []).map(reason => `<div class="reason-row"><span>${escapeHtml(reason.label)} <b>+${reason.points}</b></span><em>${escapeHtml(reason.detail)}</em></div>`).join('');
  const base = active.recommended_base;
  el('scramble-modal-base').innerHTML = base ? `<strong>${escapeHtml(base.icao)}</strong> · ${escapeHtml(base.aircraft.join(' / '))} · ${base.distance_nm} NM · EST ${base.estimated_response_minutes} MIN<br>INTERCEPT COURSE ${String(base.intercept_course_deg ?? 0).padStart(3,'0')}° · INTERCEPT ETA ${base.intercept_total_minutes ?? '—'} MIN · ${escapeHtml(base.intercept_point_label || '—')}` : 'NO ELIGIBLE RESPONSE BASE CALCULATED';
  el('acknowledge-scramble').dataset.alertId = active.id;

  setScrambleModalVisible(state.popupEnabled);

  if (state.soundEnabled) startScrambleAlarm();
  else {
    stopScrambleAlarm();
    el('scramble-audio-status').textContent = 'ALERT SOUNDS DISABLED';
  }
}

function setSoundEnabled(enabled) {
  state.soundEnabled = Boolean(enabled);
  saveAlertPreference('vng-adoc.alert-sound', state.soundEnabled);
  updateAlertPreferenceControls();
  if (!state.soundEnabled) {
    stopScrambleAlarm();
    el('scramble-audio-status').textContent = 'ALERT SOUNDS DISABLED';
  } else {
    unlockAlarmAudio().then(() => renderMandatoryScramble(state.data?.alerts || [], state.data?.scramble_alarm_confidence || 90));
  }
}

function setPopupEnabled(enabled) {
  state.popupEnabled = Boolean(enabled);
  saveAlertPreference('vng-adoc.alert-popup', state.popupEnabled);
  updateAlertPreferenceControls();
  renderMandatoryScramble(state.data?.alerts || [], state.data?.scramble_alarm_confidence || 90);
}

function setAlertVolume(value) {
  const numeric = Math.max(0, Math.min(100, Number(value) || 0));
  state.alertVolume = numeric / 100;
  saveAlertPreference('vng-adoc.alert-volume', state.alertVolume);
  if (state.alarmAudio) state.alarmAudio.volume = state.alertVolume;
  updateAlertPreferenceControls();
}

function feedAgeSeconds(data = state.data) {
  const direct = Number(data?.feed_age_seconds);
  if (Number.isFinite(direct)) {
    const sinceMessage = state.lastMessageAt ? Math.max(0, (Date.now() - state.lastMessageAt) / 1000) : 0;
    return Math.max(0, direct + sinceMessage);
  }
  const updated = data?.feed_updated_at ? Date.parse(data.feed_updated_at) : NaN;
  return Number.isFinite(updated) ? Math.max(0, (Date.now() - updated) / 1000) : Infinity;
}

function updateFeedStaleState(data = state.data) {
  const age = feedAgeSeconds(data);
  const critical = age >= state.staleCriticalSeconds || Boolean(data?.error);
  const warning = age >= state.staleWarningSeconds;
  state.dataStale = critical;
  document.body.classList.toggle('feed-warning', warning && !critical);
  document.body.classList.toggle('feed-stale', critical);
  const banner = el('feed-stale-banner');
  if (banner) banner.hidden = !critical;
  const detail = el('feed-stale-detail');
  if (detail && critical) detail.textContent = `Last confirmed feed ${Number.isFinite(age) ? Math.floor(age) + ' seconds' : 'an unknown time'} ago · tracks are last-known · new automatic alarms paused`;
  return { age, warning, critical };
}

function updateStatus(data) {
  const stats = data.stats || {};
  const viewPilots = focusedPilots(data.pilots || []);
  const viewAlerts = focusedAlerts(data.alerts || []);
  const focusedCoverage = state.artccFocusId ? state.atcCoverageData.filter(artccCoverageMatches) : state.atcCoverageData;
  el('metric-aircraft').textContent = state.artccFocusId ? viewPilots.length : (stats.monitored_aircraft ?? stats.us_aircraft ?? 0);
  el('metric-centers').textContent = state.artccFocusId ? new Set(focusedCoverage.map(item => item.callsign).filter(Boolean)).size : (stats.centers_online || 0);
  el('metric-red').textContent = state.artccFocusId ? viewAlerts.filter(alert => alert.severity === 'red').length : (stats.red_alerts || 0);
  el('metric-nordo').textContent = state.artccFocusId ? viewPilots.filter(pilot => pilot.nordo_watch).length : (stats.nordo_watches || 0);
  el('metric-mismatch').textContent = state.artccFocusId ? viewPilots.filter(pilot => pilot.frequency_mismatch_active).length : (stats.frequency_mismatches || 0);
  el('metric-manual-intercepts').textContent = stats.manual_intercepts ?? (data.manual_intercepts || []).length;
  const inbound = (data.operations || []).filter(operation => operation.active && !operation.completed).reduce((sum, operation) => sum + Number(operation.accepted_count || 0), 0);
  el('metric-inbound').textContent = inbound;
  const top = viewAlerts[0]?.severity || 'green';
  const status = top === 'red' ? 'SCRAMBLE' : top === 'orange' ? 'ELEVATED' : top === 'yellow' ? 'WATCH' : 'NORMAL';
  el('defcon').className = `status-value ${top}`;
  el('defcon').textContent = status;

  const stale = updateFeedStaleState(data);
  el('metric-feed-age').textContent = Number.isFinite(stale.age) ? `${Math.floor(stale.age)}s` : '—';
  el('metric-feed-age').className = stale.critical ? 'stale' : stale.warning ? 'warning' : '';
  const feedTime = data.feed_updated_at ? new Date(data.feed_updated_at).toISOString().slice(11, 19) + 'Z' : 'WAITING';
  const focus = data._artcc_focus;
  const liveLabel = focus ? `${focus.code} FOCUS` : (data.monitor_canada ? 'LIVE U.S. + CANADA' : 'LIVE U.S.');
  el('feed-status').textContent = stale.critical ? `DATA STALE · ${Math.floor(stale.age)}s` : data.error ? 'FEED DEGRADED' : `${liveLabel} · ${feedTime}`;
  el('operating-mode').textContent = focus ? `${focus.code} · ${focus.name} · SINGLE ARTCC MODE` : (data.monitor_canada ? 'LIVE U.S. + CANADA' : 'LIVE UNITED STATES');
  el('boundary-status').textContent = focus ? `${focus.code} OUTLINE · ${stats.centers_online || 0} CENTER POSITION${stats.centers_online === 1 ? '' : 'S'} ONLINE` : (data.center_boundary_count ? `${data.center_boundary_count} CENTER OUTLINES · ${data.boundary_status || 'ONLINE'}` : (data.boundary_status || 'OUTLINES LOADING'));
  updateArtccFocusControls();
  el('sua-status').textContent = data.sua_status || 'NOT LOADED';
  el('processing-time').textContent = `${data.processing_ms || 0} ms`;
  const breakdown = data.processing_breakdown || {};
  el('processing-time').title = `Filter ${breakdown.filter_ms || 0} ms · Coverage ${breakdown.coverage_ms || 0} ms · Detection ${breakdown.detection_ms || 0} ms · Workflow ${breakdown.workflow_ms || 0} ms`;
  el('system-health').textContent = stale.critical ? 'DATA STALE — AUTOMATIC ALARMS PAUSED' : data.error ? `DEGRADED — ${data.error}` : 'ONLINE';
  el('system-health').classList.toggle('error-text', Boolean(data.error) || stale.critical);
}

function updateViewerCount(value) {
  const count = Math.max(0, Number(value) || 0);
  state.viewerCount = count;
  const target = el('viewer-count');
  if (target) target.textContent = String(count);
}

function applySocketMessage(data) {
  if (data?.type === 'presence') {
    updateViewerCount(data.viewer_count);
    return;
  }
  if (data?.type === 'delta') {
    const merged = globalThis.VngDeltaClient?.applyDelta(state.rawData, data);
    if (!merged) {
      loadLive(true);
      return;
    }
    applyData(merged);
    return;
  }
  applyData(data);
}

function applyData(incomingData) {
  if (!incomingData || typeof incomingData.revision !== 'number') return;
  if (incomingData.revision < state.revision) return;
  state.revision = incomingData.revision;
  state.lastMessageAt = Date.now();
  state.rawData = incomingData;
  const cachedSelected = state.selectedCallsign ? state.trackDetailCache.get(state.selectedCallsign) : null;
  if (cachedSelected?.pilot) mergeTrackDetailIntoState(state.selectedCallsign, cachedSelected.pilot);
  const data = buildFocusedDashboardData(incomingData);
  state.data = data;
  if (cachedSelected?.pilot) mergeTrackDetailIntoState(state.selectedCallsign, cachedSelected.pilot);
  const liveCallsigns = new Set((data.pilots || []).map(item => item.callsign));
  if (state.selectedCallsign && !liveCallsigns.has(state.selectedCallsign)) { state.selectedCallsign = null; state.selectedOperationId = null; clearFlightPlanPreview(); }
  if (state.atcSelectedCallsign && !liveCallsigns.has(state.atcSelectedCallsign)) state.atcSelectedCallsign = null;
  if (state.operatorAircraftCallsign && !liveCallsigns.has(state.operatorAircraftCallsign)) state.atcRenderKey = null;
  if (state.interceptTargetCallsign && !liveCallsigns.has(state.interceptTargetCallsign)) state.interceptTargetCallsign = null;
  for (const callsign of [...state.multiInterceptorSelection]) if (!liveCallsigns.has(callsign)) state.multiInterceptorSelection.delete(callsign);
  if (data.center_boundary_revision && data.center_boundary_revision !== state.centerBoundaryRevision) refreshCenterBoundaries(data.center_boundary_revision);
  if (data.atc_revision && data.atc_revision !== state.atcRevision) refreshAtcCoverage(data.atc_revision);
  globalThis.VngRenderScheduler?.mark('map', 'intercept', 'atc');
  updateStatus(data);
  renderPreScrambleWarning(incomingData);
  if (state.workspaceTab === 'map') {
    const force = globalThis.VngRenderScheduler?.consume('map') ?? false;
    renderAircraft(data.pilots || [], force);
    renderAlerts(data.alerts || [], force);
    renderInterceptOverlay(force);
    if (state.selectedCallsign) renderFlightPlanPreview(state.selectedCallsign);
  } else if (state.workspaceTab === 'intercept') {
    const force = globalThis.VngRenderScheduler?.consume('intercept') ?? false;
    renderInterceptConsole();
    renderActiveInterceptWorkspace(force);
  } else if (state.workspaceTab === 'atc') {
    const force = globalThis.VngRenderScheduler?.consume('atc') ?? false;
    renderAtcWorkspace(force);
  }
  if (state.interceptConsoleOpen && state.workspaceTab !== 'intercept') renderInterceptConsole();
  if (state.selectedCallsign && incomingData.payload_mode === 'compact') fetchTrackDetail(state.selectedCallsign);
  if (!state.dataStale) renderMandatoryScramble(data.alerts || [], data.scramble_alarm_confidence || 90);
}

async function loadLive(force = false) {
  if (state.liveLoading) return;
  if (!force && state.wsOpen && Date.now() - state.lastMessageAt < 22000) return;
  state.liveLoading = true;
  try {
    const response = await fetchWithTimeout(`/api/live?ts=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Live ${response.status}`);
    applyData(await response.json());
  } catch (error) {
    console.error(error);
    el('system-health').textContent = 'CONNECTION LOST';
    el('system-health').classList.add('error-text');
  } finally {
    state.liveLoading = false;
  }
}

function updateDeploymentIdentity(serverVersion) {
  const serverBuild = String(serverVersion || 'unknown');
  const build = el('build-version');
  const warning = el('deployment-warning');
  const mismatch = serverBuild !== 'unknown' && CLIENT_BUILD !== 'unknown' && serverBuild !== CLIENT_BUILD;
  if (build) {
    build.textContent = mismatch ? `CLIENT v${CLIENT_BUILD} / SERVER v${serverBuild}` : `v${serverBuild === 'unknown' ? CLIENT_BUILD : serverBuild}`;
    build.classList.toggle('mismatch', mismatch);
  }
  if (warning) {
    warning.hidden = !mismatch;
    warning.textContent = mismatch ? 'STALE CLIENT FILES — HARD REFRESH REQUIRED' : '';
  }
  return !mismatch;
}

async function bootstrap() {
  try {
    state.artccFocusId = normaliseArtccId(localStorage.getItem('vng-adoc.artcc-focus'));
  } catch (_) {}
  try {
    const response = await fetchWithTimeout(`/api/bootstrap?ts=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Bootstrap ${response.status}`);
    const payload = await response.json();
    updateDeploymentIdentity(payload.version);
    state.httpFallbackSeconds = Math.max(5, Number(payload.http_fallback_seconds) || 15);
    state.staleWarningSeconds = Math.max(30, Number(payload.feed_stale_warning_seconds) || 45);
    state.staleCriticalSeconds = Math.max(state.staleWarningSeconds + 15, Number(payload.feed_stale_critical_seconds) || 90);
    state.consolePresenceHeartbeatSeconds = Math.max(15, Number(payload.console_presence_heartbeat_seconds) || 30);
    if (payload.viewer_count !== undefined) updateViewerCount(payload.viewer_count);
    scheduleHttpFallback();
    scheduleConsolePresenceHeartbeat();
    renderZones(payload.zones || []);
    renderBases(payload.bases || []);
    renderDcaHeliRoutes(false);
    renderAtcCoverage(payload.atc_coverage || [], payload.atc_revision);
    await refreshCenterBoundaries(payload.center_boundary_revision);
    el('boundary-status').textContent = payload.center_boundary_count ? `${payload.center_boundary_count} CENTER OUTLINES · ${payload.boundary_status || 'ONLINE'}` : (payload.boundary_status || 'LOADING');
  } catch (error) {
    console.error(error);
  }
  await Promise.allSettled([loadSua(), loadLive(true)]);
}

function scheduleHttpFallback() {
  if (state.httpFallbackTimer) clearInterval(state.httpFallbackTimer);
  state.httpFallbackTimer = setInterval(() => loadLive(false), state.httpFallbackSeconds * 1000);
}

async function heartbeatAcceptedOperations() {
  const operations = state.data?.operations || [];
  const accepted = operations.filter(operation => operation.active && !operation.completed && operationAcceptedByThisConsole(operation));
  if (!accepted.length) return;
  await Promise.allSettled(accepted.map(operation => fetchWithTimeout(`/api/operations/${encodeURIComponent(operation.id)}/accept`, {
    method: 'POST',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ console_id: state.consoleId, console_label: state.consoleLabel }),
  }, 8000)));
}

function scheduleConsolePresenceHeartbeat() {
  if (state.consolePresenceHeartbeatTimer) clearInterval(state.consolePresenceHeartbeatTimer);
  state.consolePresenceHeartbeatTimer = setInterval(heartbeatAcceptedOperations, state.consolePresenceHeartbeatSeconds * 1000);
}

function connectWs() {
  if (state.ws && [WebSocket.OPEN, WebSocket.CONNECTING].includes(state.ws.readyState)) return;
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const clientId = encodeURIComponent(state.consoleId || `anonymous-${Date.now()}`);
  const socket = new WebSocket(`${protocol}://${location.host}/ws?client_id=${clientId}`);
  state.ws = socket;
  el('connection-status').textContent = 'CONNECTING';

  socket.onopen = () => {
    state.wsOpen = true;
    state.wsRetryMs = 1500;
    state.lastMessageAt = Date.now();
    el('connection-status').textContent = 'WEBSOCKET LIVE';
    socket.send('ready');
    clearInterval(state.wsHeartbeat);
    state.wsHeartbeat = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send('ping');
    }, 20000);
  };
  socket.onmessage = event => {
    try { applySocketMessage(JSON.parse(event.data)); } catch (error) { console.error(error); }
  };
  socket.onclose = () => {
    state.wsOpen = false;
    clearInterval(state.wsHeartbeat);
    state.wsHeartbeat = null;
    el('connection-status').textContent = 'HTTP FALLBACK';
    setTimeout(connectWs, state.wsRetryMs);
    state.wsRetryMs = Math.min(15000, Math.round(state.wsRetryMs * 1.7));
  };
  socket.onerror = () => socket.close();
}

// Event wiring
for (const button of document.querySelectorAll('[data-workspace-tab]')) {
  button.addEventListener('click', () => setWorkspaceTab(button.dataset.workspaceTab));
}
el('intercept-focus-select').addEventListener('change', event => {
  state.activeInterceptKey = event.target.value || null;
  const assignment = activeInterceptAssignments().find(item => item.key === state.activeInterceptKey);
  if (assignment) state.interceptTargetCallsign = assignment.target_callsign;
  renderActiveInterceptWorkspace(true);
});
el('intercept-focus-open-control').addEventListener('click', () => openInterceptConsole('target', state.interceptTargetCallsign || state.selectedCallsign));
el('intercepts-target-input').addEventListener('input', event => {
  const next = normaliseCallsign(event.target.value);
  if (next !== state.interceptTargetCallsign) state.multiInterceptorSelection.clear();
  state.interceptTargetCallsign = next;
  renderActiveInterceptWorkspace(true);
});
el('intercepts-target-input').addEventListener('change', event => {
  state.interceptTargetCallsign = normaliseCallsign(event.target.value);
  state.multiInterceptorSelection.clear();
  renderActiveInterceptWorkspace(true);
});
el('intercepts-use-selected').addEventListener('click', () => {
  if (pilotForCallsign(state.selectedCallsign)) {
    state.interceptTargetCallsign = state.selectedCallsign;
    state.multiInterceptorSelection.clear();
  }
  renderActiveInterceptWorkspace(true);
});
el('intercepts-candidate-filter').addEventListener('input', event => {
  state.interceptorCandidateFilter = event.target.value || '';
  renderMultiInterceptorCandidates();
});
el('intercept-multi-candidates').addEventListener('change', event => {
  const checkbox = event.target.closest('[data-multi-interceptor]');
  if (!checkbox) return;
  const callsign = checkbox.dataset.multiInterceptor;
  if (checkbox.checked) state.multiInterceptorSelection.add(callsign);
  else state.multiInterceptorSelection.delete(callsign);
  renderMultiInterceptorCandidates();
});
el('intercepts-select-vsoa').addEventListener('click', () => {
  const target = activeTargetForBuilder();
  if (!target) return setInterceptBatchFeedback('Select a live target aircraft first.', 'error');
  for (const item of rankedInterceptorCandidates(target)) {
    if (item.pilot.vsoa && !item.assignedTarget) state.multiInterceptorSelection.add(item.pilot.callsign);
  }
  renderMultiInterceptorCandidates();
});
el('intercepts-select-nearest').addEventListener('click', () => selectNearestInterceptors(3));
el('intercepts-clear-selection').addEventListener('click', () => {
  state.multiInterceptorSelection.clear();
  renderMultiInterceptorCandidates();
});
el('intercepts-assign-best-vsoa').addEventListener('click', async event => {
  try {
    await runInterceptButtonAction(event.currentTarget, 'ASSIGNING…', assignBestVsoaInterceptor);
  } catch (error) {
    console.error(error);
    setInterceptBatchFeedback(`Best-VSOA assignment failed: ${error.message}`, 'error');
  }
});
el('assign-selected-interceptors').addEventListener('click', async event => {
  try {
    await runInterceptButtonAction(event.currentTarget, 'ASSIGNING…', assignSelectedInterceptors);
  } catch (error) {
    console.error(error);
    setInterceptBatchFeedback(`Assignment failed: ${error.message}`, 'error');
  }
});
el('intercepts-recalculate-now').addEventListener('click', async () => {
  try { await recalculateInterceptsNow(); }
  catch (error) { console.error(error); setInterceptBatchFeedback(`Recalculation failed: ${error.message}`, 'error'); }
});
el('intercept-focus-map').addEventListener('click', () => {
  const target = state.interceptTargetCallsign || activeInterceptAssignments().find(item => item.key === state.activeInterceptKey)?.target_callsign;
  if (target) focusInterceptTargetOnTacticalMap(target);
  else setInterceptBatchFeedback('Select a live target first.', 'error');
});
el('intercept-open-main-map').addEventListener('click', () => {
  const target = state.interceptTargetCallsign || activeInterceptAssignments().find(item => item.key === state.activeInterceptKey)?.target_callsign;
  setWorkspaceTab('map');
  if (target) focusTrackOnMap(target);
});
el('intercept-map-fit-all').addEventListener('click', () => {
  state.interceptMapAutoFit = true;
  updateInterceptMapAutoFitButton();
  renderInterceptTacticalMap(true, true);
});
el('intercept-map-auto-fit').addEventListener('click', () => {
  state.interceptMapAutoFit = !state.interceptMapAutoFit;
  updateInterceptMapAutoFitButton();
  if (state.interceptMapAutoFit) renderInterceptTacticalMap(true, true);
});
el('intercept-focus-content').addEventListener('click', async event => {
  const control = event.target.closest('[data-target-control]');
  if (control) {
    try {
      await runInterceptButtonAction(control, 'UPDATING…', async () => {
        await updateInterceptTargetControl(control.dataset.targetCallsign, control.dataset.targetControl, control.dataset.controlValue);
        setInterceptBatchFeedback(`${control.dataset.targetCallsign} ${control.dataset.targetControl.replaceAll('_', ' ')} updated.`, 'success');
      });
    } catch (error) {
      console.error(error);
      setInterceptBatchFeedback(`Control update failed: ${error.message}`, 'error');
      el('system-health').textContent = 'INTERCEPT CONTROL UPDATE FAILED';
    }
    return;
  }
  const noteButton = event.target.closest('[data-save-intercept-note]');
  if (noteButton) {
    const target = noteButton.dataset.saveInterceptNote;
    const input = el('intercept-focus-content').querySelector(`[data-intercept-note="${CSS.escape(target)}"]`);
    try {
      await runInterceptButtonAction(noteButton, 'SAVING…', async () => {
        await updateInterceptTargetControl(target, null, null, input?.value || '');
        setInterceptBatchFeedback(`Coordination note saved for ${target}.`, 'success');
      });
    } catch (error) {
      console.error(error);
      setInterceptBatchFeedback(`Note save failed: ${error.message}`, 'error');
      el('system-health').textContent = 'INTERCEPT NOTE UPDATE FAILED';
    }
    return;
  }
  const add = event.target.closest('[data-add-interceptor-target]');
  if (add) {
    state.interceptTargetCallsign = add.dataset.addInterceptorTarget;
    state.multiInterceptorSelection.clear();
    renderActiveInterceptWorkspace(true);
    el('intercept-multi-candidates')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    el('intercepts-candidate-filter')?.focus();
    setInterceptBatchFeedback(`Select one or more additional live interceptors for ${state.interceptTargetCallsign}.`);
    return;
  }
  const targetFocus = event.target.closest('[data-focus-target-only]');
  if (targetFocus) {
    focusInterceptTargetOnTacticalMap(targetFocus.dataset.focusTargetOnly);
    return;
  }
  const releaseAll = event.target.closest('[data-release-target-interceptors]');
  if (releaseAll) {
    const target = releaseAll.dataset.releaseTargetInterceptors;
    if (!window.confirm(`Release all manual interceptors assigned to ${target}?`)) return;
    try {
      await runInterceptButtonAction(releaseAll, 'RELEASING…', async () => {
        await releaseTargetInterceptors(target);
        setInterceptBatchFeedback(`All manual interceptors released from ${target}.`, 'success');
      });
    } catch (error) {
      console.error(error);
      setInterceptBatchFeedback(`Release failed: ${error.message}`, 'error');
      el('system-health').textContent = 'RELEASE ALL FAILED';
    }
    return;
  }
  const open = event.target.closest('[data-open-focus-control]');
  if (open) {
    const interceptor = open.dataset.focusInterceptor || '';
    const target = open.dataset.focusTarget || state.interceptTargetCallsign || state.selectedCallsign;
    openInterceptConsole(interceptor ? 'interceptor' : 'target', interceptor || target);
    if (interceptor) {
      el('intercept-interceptor-input').value = interceptor;
      el('intercept-target-input').value = target || '';
      refreshInterceptBuilderPreviews();
    }
    return;
  }
  const focus = event.target.closest('[data-focus-pair]');
  if (focus) {
    focusInterceptPairOnTacticalMap(focus.dataset.focusPair, focus.dataset.focusTarget);
    return;
  }
  const manualStatus = event.target.closest('[data-intercept-response]');
  if (manualStatus) {
    try { await setInterceptResponse(manualStatus.dataset.interceptResponse, manualStatus.dataset.responseStatus); }
    catch (error) { console.error(error); el('system-health').textContent = 'INTERCEPT RESPONSE UPDATE FAILED'; }
    return;
  }
  const operationStatus = event.target.closest('[data-operation-target-response]');
  if (operationStatus) {
    try { await setOperationTargetResponse(operationStatus.dataset.operationTargetResponse, operationStatus.dataset.responseStatus); }
    catch (error) { console.error(error); el('system-health').textContent = 'TARGET RESPONSE UPDATE FAILED'; }
    return;
  }
  const cancel = event.target.closest('[data-intercept-cancel]');
  if (cancel) {
    const callsign = cancel.dataset.interceptCancel;
    try {
      await runInterceptButtonAction(cancel, 'RELEASING…', async () => {
        await cancelManualIntercept(callsign);
        setInterceptBatchFeedback(`${callsign} released from the intercept assignment.`, 'success');
      });
    } catch (error) {
      console.error(error);
      setInterceptBatchFeedback(`Release failed: ${error.message}`, 'error');
    }
  }
});
el('intercept-focus-content').addEventListener('input', event => {
  const input = event.target.closest('[data-intercept-note]');
  if (!input) return;
  const target = normaliseCallsign(input.dataset.interceptNote);
  state.interceptNoteDrafts.set(target, input.value.slice(0, 500));
  input.classList.add('dirty');
  const save = el('intercept-focus-content').querySelector(`[data-save-intercept-note="${CSS.escape(target)}"]`);
  if (save) save.textContent = 'SAVE DRAFT';
});
el('atc-operator-aircraft-input').addEventListener('change', event => {
  saveOperatorAircraftSelection(event.target.value);
});
el('atc-save-operator-aircraft').addEventListener('click', () => {
  saveOperatorAircraftSelection(el('atc-operator-aircraft-input').value);
});
el('atc-track-input').addEventListener('change', event => {
  state.atcSelectedCallsign = normaliseCallsign(event.target.value);
  renderAtcWorkspace(true);
});
el('atc-track-select').addEventListener('change', event => {
  state.atcSelectedCallsign = normaliseCallsign(event.target.value);
  const input = el('atc-track-input');
  if (input) input.value = state.atcSelectedCallsign || '';
  renderAtcWorkspace(true);
});
el('atc-operator-aircraft-select').addEventListener('change', event => {
  const input = el('atc-operator-aircraft-input');
  if (input) input.value = normaliseCallsign(event.target.value);
});
el('atc-use-selected-track').addEventListener('click', () => {
  if (state.selectedCallsign) state.atcSelectedCallsign = state.selectedCallsign;
  const targetSelect = el('atc-track-select');
  if (targetSelect) targetSelect.value = state.atcSelectedCallsign || '';
  renderAtcWorkspace(true);
});
el('atc-load-first-case').addEventListener('click', () => {
  const first = (state.data?.operations || []).find(item => item.active && !item.completed);
  if (first) state.atcSelectedCallsign = first.callsign;
  renderAtcWorkspace(true);
});
el('atc-open-intercepts').addEventListener('click', () => setWorkspaceTab('intercept'));
el('atc-map-focus-selected').addEventListener('click', () => {
  const pilot = atcSelectedPilot() || operatorAircraftPilot();
  const atcMap = ensureAtcOpsMap();
  const position = interceptMapTrackPosition(pilot);
  if (atcMap && position) atcMap.setView(position, Math.max(7, atcMap.getZoom()), { animate: false });
});
el('atc-map-fit-related').addEventListener('click', () => renderAtcOpsMap(true));
el('save-atc-console-label').addEventListener('click', () => {
  const value = String(el('atc-console-label').value || '').trim().slice(0, 40);
  if (!value) return;
  state.consoleLabel = value;
  try { localStorage.setItem('vng-adoc.console-label', value); } catch (_) {}
  el('system-health').textContent = `CONSOLE LABEL SAVED · ${value.toUpperCase()}`;
  renderAtcWorkspace(true);
});

async function assignOperatorAircraftToTarget(interceptorCallsign, targetCallsign) {
  const interceptor = pilotForCallsign(interceptorCallsign);
  const target = pilotForCallsign(targetCallsign);
  if (!interceptor?.vsoa || interceptor?.on_ground) throw new Error('Selected operator aircraft is not an airborne VSOA track');
  if (!target) throw new Error('Target track is no longer live');
  if (interceptor.callsign === target.callsign) throw new Error('Operator aircraft and target must be different tracks');
  const existing = (state.data?.manual_intercepts || []).find(item => item.interceptor_callsign === interceptor.callsign);
  if (existing?.target_callsign === target.callsign) {
    const assignment = activeInterceptAssignments().find(item => item.interceptor_callsign === interceptor.callsign && item.target_callsign === target.callsign);
    if (assignment) state.activeInterceptKey = assignment.key;
    state.interceptTargetCallsign = target.callsign;
    setWorkspaceTab('intercept');
    return;
  }
  if (existing && existing.target_callsign !== target.callsign && !window.confirm(`${interceptor.callsign} is currently assigned to ${existing.target_callsign}. Reassign it to ${target.callsign}?`)) return;
  const response = await fetchWithTimeout('/api/intercepts/manual/batch', {
    method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ interceptor_callsigns: [interceptor.callsign], target_callsign: target.callsign, console_id: state.consoleId, console_label: state.consoleLabel }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) throw new Error(payload.error || `assignment_${response.status}`);
  state.atcSelectedCallsign = target.callsign;
  state.interceptTargetCallsign = target.callsign;
  await loadLive(true);
  const assignment = activeInterceptAssignments().find(item => item.interceptor_callsign === interceptor.callsign && item.target_callsign === target.callsign);
  if (assignment) state.activeInterceptKey = assignment.key;
  el('system-health').textContent = `${interceptor.callsign} ASSIGNED TO INTERCEPT ${target.callsign}`;
  renderAtcWorkspace(true);
}

async function createTemporaryExemption(callsign) {
  const workspace = el('atc-workspace');
  const reason = String(workspace?.querySelector('[data-exemption-reason]')?.value || 'Operational coordination').trim().slice(0, 240);
  const minutes = Number(workspace?.querySelector('[data-exemption-minutes]')?.value || 15);
  const response = await fetchWithTimeout('/api/exemptions', {
    method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ callsign, minutes, reason, console_id: state.consoleId, console_label: state.consoleLabel }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) throw new Error(payload.error || `exemption_${response.status}`);
  await loadLive(true);
  renderAtcWorkspace(true);
}

async function dismissAutomaticFlag(alertId, callsign) {
  const reason = window.prompt(
    `Reason for dismissing the automatic flag for ${callsign}? The possible NORDO watch will remain active until the condition clears.`,
    'Reviewed by ATC coordination — automatic escalation not warranted',
  );
  if (reason === null) return;
  const cleanReason = String(reason || '').trim();
  if (!cleanReason) throw new Error('A dismissal reason is required');
  const response = await fetchWithTimeout(`/api/alerts/${encodeURIComponent(alertId)}/dismiss`, {
    method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ reason: cleanReason, console_id: state.consoleId, console_label: state.consoleLabel }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) throw new Error(payload.error || `dismiss_${response.status}`);
  await loadLive(true);
  state.atcSelectedCallsign = callsign;
  renderAtcWorkspace(true);
  renderAlerts(state.data?.alerts || [], true);
}

async function removeTemporaryExemption(exemptionId) {
  const response = await fetchWithTimeout(`/api/exemptions/${encodeURIComponent(exemptionId)}`, {
    method: 'DELETE', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ console_id: state.consoleId, console_label: state.consoleLabel }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) throw new Error(`remove_exemption_${response.status}`);
  await loadLive(true);
  renderAtcWorkspace(true);
}

el('atc-workspace').addEventListener('click', async event => {
  const setOperator = event.target.closest('[data-atc-set-operator]');
  if (setOperator) {
    saveOperatorAircraftSelection(setOperator.dataset.atcSetOperator);
    return;
  }
  const dispatch = event.target.closest('[data-atc-dispatch-operator]');
  if (dispatch) {
    try {
      dispatch.disabled = true;
      const original = dispatch.textContent;
      dispatch.textContent = dispatch.dataset.assignmentActive === 'true' ? 'OPENING…' : 'ASSIGNING…';
      await assignOperatorAircraftToTarget(dispatch.dataset.atcDispatchOperator, dispatch.dataset.targetCallsign);
      dispatch.textContent = original;
    } catch (error) {
      console.error(error);
      dispatch.disabled = false;
      el('system-health').textContent = `VSOA ASSIGNMENT FAILED · ${error.message}`;
    }
    return;
  }
  const select = event.target.closest('[data-atc-select-call]');
  if (select) {
    state.atcSelectedCallsign = select.dataset.atcSelectCall;
    renderAtcWorkspace(true);
    return;
  }
  const dismissAuto = event.target.closest('[data-dismiss-automatic-flag]');
  if (dismissAuto) {
    try { await dismissAutomaticFlag(dismissAuto.dataset.dismissAutomaticFlag, dismissAuto.dataset.callsign); }
    catch (error) { console.error(error); el('system-health').textContent = `AUTOMATIC FLAG DISMISSAL FAILED · ${error.message}`; }
    return;
  }
  const createExemption = event.target.closest('[data-create-exemption]');
  if (createExemption) {
    try { await createTemporaryExemption(createExemption.dataset.createExemption); }
    catch (error) { console.error(error); el('system-health').textContent = `EXEMPTION FAILED · ${error.message}`; }
    return;
  }
  const removeExemption = event.target.closest('[data-remove-exemption]');
  if (removeExemption) {
    try { await removeTemporaryExemption(removeExemption.dataset.removeExemption); }
    catch (error) { console.error(error); el('system-health').textContent = `REMOVE FAILED · ${error.message}`; }
    return;
  }
  const action = event.target.closest('[data-atc-action]');
  if (action) {
    const callsign = action.dataset.callsign;
    if (action.dataset.atcAction === 'focus-map') { setWorkspaceTab('map'); focusTrackOnMap(callsign); }
    else if (action.dataset.atcAction === 'target') openInterceptConsole('target', callsign);
    else if (action.dataset.atcAction === 'interceptor') openInterceptConsole('interceptor', callsign);
    else if (action.dataset.atcAction === 'mark-nordo') await manualNordoAction(callsign, 'mark');
    else if (action.dataset.atcAction === 'clear-nordo') await manualNordoAction(callsign, 'clear');
    else if (action.dataset.atcAction === 'active-intercept') {
      const assignment = activeInterceptAssignments().find(item => item.target_callsign === callsign || item.interceptor_callsign === callsign);
      if (assignment) state.activeInterceptKey = assignment.key;
      setWorkspaceTab('intercept');
    }
    return;
  }
  const targetControl = event.target.closest('[data-target-control]');
  if (targetControl) {
    await updateInterceptTargetControl(targetControl.dataset.targetCallsign, targetControl.dataset.targetControl, targetControl.dataset.controlValue);
    renderAtcWorkspace(true);
    return;
  }
  const saveNote = event.target.closest('[data-save-intercept-note]');
  if (saveNote) {
    const callsign = saveNote.dataset.saveInterceptNote;
    const input = el('atc-workspace').querySelector(`[data-intercept-note="${CSS.escape(callsign)}"]`);
    await updateInterceptTargetControl(callsign, null, null, input?.value || '');
    renderAtcWorkspace(true);
    return;
  }
  const openMission = event.target.closest('[data-atc-open-intercept]');
  if (openMission) {
    state.interceptTargetCallsign = openMission.dataset.atcOpenIntercept;
    const assignment = activeInterceptAssignments().find(item => item.target_callsign === state.interceptTargetCallsign);
    if (assignment) state.activeInterceptKey = assignment.key;
    setWorkspaceTab('intercept');
    return;
  }
  const response = event.target.closest('[data-operation-target-response]');
  if (response) { await setOperationTargetResponse(response.dataset.operationTargetResponse, response.dataset.responseStatus); renderAtcWorkspace(true); return; }
  const manualResponse = event.target.closest('[data-intercept-response]');
  if (manualResponse) { await setInterceptResponse(manualResponse.dataset.interceptResponse, manualResponse.dataset.responseStatus); renderAtcWorkspace(true); return; }
  const operationResponse = event.target.closest('[data-operation-response]');
  if (operationResponse) { await operationResponseAction(operationResponse.dataset.operationId, operationResponse.dataset.operationResponse); renderAtcWorkspace(true); return; }
  const phase = event.target.closest('[data-operation-phase]');
  if (phase) { await toggleOperationPhase(phase.dataset.operationId, phase.dataset.operationPhase, phase.dataset.operationPhaseComplete === 'true'); renderAtcWorkspace(true); }
});
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.filter').forEach(item => item.classList.remove('active'));
  button.classList.add('active');
  state.filter = button.dataset.filter;
  renderAircraft(state.data?.pilots || [], true);
}));
document.querySelectorAll('.region').forEach(button => button.addEventListener('click', () => setRegionView(button.dataset.region)));
document.querySelectorAll('.region-filter').forEach(button => button.addEventListener('click', () => setOperationalRegionFilter(button.dataset.regionFilter)));
document.querySelectorAll('.icon-mode').forEach(button => button.addEventListener('click', () => setIconMode(button.dataset.mode)));
el('toggle-atc').addEventListener('click', toggleAtcCoverage);
el('toggle-sua').addEventListener('click', toggleSua);
el('toggle-dca-heli-routes').addEventListener('click', toggleDcaHeliRoutes);
el('toggle-map-controls').addEventListener('click', () => setMapControlsExpanded(!state.mapControlsExpanded));
document.querySelectorAll('[data-map-menu]').forEach(button => button.addEventListener('click', () => {
  const panel = document.querySelector(`[data-map-menu-panel="${button.dataset.mapMenu}"]`);
  setMapMenuPanel(panel?.hidden ? button.dataset.mapMenu : null);
}));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') setMapMenuPanel(null);
});
map.on('click', () => setMapMenuPanel(null));
el('reset-layout').addEventListener('click', resetLayout);
el('toggle-map-legend').addEventListener('click', () => setMapLegendExpanded(!state.legendExpanded));
el('basemap-select').addEventListener('change', event => setBasemap(event.target.value));
el('artcc-focus-select').addEventListener('change', event => setArtccFocus(event.target.value, true));
el('clear-artcc-focus').addEventListener('click', () => setArtccFocus('', false));
el('nordo-watch-list').addEventListener('click', event => {
  const card = event.target.closest('[data-call]');
  if (card) selectTrack(card.dataset.call, true);
});
el('alert-list').addEventListener('click', event => {
  const operationCard = event.target.closest('[data-operation]');
  if (operationCard) {
    selectOperation(operationCard.dataset.operation, true);
    return;
  }
  const card = event.target.closest('[data-call]');
  if (card) selectTrack(card.dataset.call, true, card.dataset.operationId || null);
});
el('open-intercept-console').addEventListener('click', () => openInterceptConsole('target', state.selectedCallsign));
el('close-intercept-console').addEventListener('click', closeInterceptConsole);
el('intercept-console-modal').addEventListener('click', event => {
  const recommendation = event.target.closest('[data-recommended-interceptor]');
  if (recommendation) {
    el('intercept-interceptor-input').value = recommendation.dataset.recommendedInterceptor;
    refreshInterceptBuilderPreviews();
    return;
  }
  if (event.target.closest('[data-intercept-close]')) {
    closeInterceptConsole();
    return;
  }
  const focusButton = event.target.closest('[data-intercept-focus]');
  if (focusButton) {
    el('intercept-interceptor-input').value = focusButton.dataset.interceptFocus;
    el('intercept-target-input').value = focusButton.dataset.interceptTarget || '';
    refreshInterceptBuilderPreviews();
    state.activeInterceptKey = `manual:${focusButton.dataset.interceptFocus}`;
    closeInterceptConsole();
    setWorkspaceTab('intercept');
    return;
  }
  const cancelButton = event.target.closest('[data-intercept-cancel]');
  if (cancelButton) cancelManualIntercept(cancelButton.dataset.interceptCancel);
});
el('intercept-console-modal').addEventListener('keydown', event => {
  trapModalFocus(event, el('intercept-console-modal'));
  if (event.key === 'Escape') closeInterceptConsole();
  if (event.key === 'Enter' && event.target.matches('#intercept-target-input,#intercept-interceptor-input')) assignManualIntercept();
});
el('intercept-target-input').addEventListener('input', refreshInterceptBuilderPreviews);
el('intercept-interceptor-input').addEventListener('input', refreshInterceptBuilderPreviews);
el('use-selected-target').addEventListener('click', () => { if (state.selectedCallsign) el('intercept-target-input').value = state.selectedCallsign; refreshInterceptBuilderPreviews(); });
el('use-selected-interceptor').addEventListener('click', () => { if (state.selectedCallsign) el('intercept-interceptor-input').value = state.selectedCallsign; refreshInterceptBuilderPreviews(); });
el('swap-intercept-aircraft').addEventListener('click', () => {
  const target = el('intercept-target-input').value;
  el('intercept-target-input').value = el('intercept-interceptor-input').value;
  el('intercept-interceptor-input').value = target;
  refreshInterceptBuilderPreviews();
});
el('assign-manual-intercept').addEventListener('click', assignManualIntercept);
el('enable-alarm-audio').addEventListener('click', async () => {
  if (!state.soundEnabled) setSoundEnabled(true);
  await startScrambleAlarm(true, true);
});
el('toggle-alert-sound').addEventListener('click', () => setSoundEnabled(!state.soundEnabled));
el('toggle-alert-popup').addEventListener('click', () => setPopupEnabled(!state.popupEnabled));
el('alert-volume').addEventListener('input', event => setAlertVolume(event.target.value));
el('test-alert-sound').addEventListener('click', async () => {
  if (!state.soundEnabled) setSoundEnabled(true);
  await startScrambleAlarm(true, true);
});
el('acknowledge-scramble').addEventListener('click', async event => {
  event.preventDefault();
  event.stopPropagation();
  const button = event.currentTarget;
  const id = button.dataset.alertId || state.activeScrambleId;
  if (!id || button.disabled) return;
  button.disabled = true;
  button.textContent = 'ACKNOWLEDGING…';
  try { await alertAction(id, 'ack'); }
  finally { button.disabled = false; button.textContent = 'ACKNOWLEDGE ON THIS CONSOLE'; }
});
el('deny-pre-scramble').addEventListener('click', event => {
  const button = event.currentTarget;
  denyPreScramble(button.dataset.callsign, button.dataset.caseId);
});
el('scramble-modal').addEventListener('keydown', event => {
  trapModalFocus(event, el('scramble-modal'));
});
document.addEventListener('pointerdown', () => unlockAlarmAudio(false), { once: true, capture: true });
document.addEventListener('keydown', () => unlockAlarmAudio(false), { once: true, capture: true });

loadConsoleIdentity();
loadArtccFocusPreference();
loadLocalAcknowledgments();
loadAlertPreferences();
try {
  state.showDcaHeliRoutes = localStorage.getItem('vng-adoc.dca-heli-routes') === '1';
  localStorage.removeItem('vng-adoc.hover-details');
} catch (_) {}
updateDcaHeliRouteUi();
applySavedLayout();
initializeResizableLayout();
window.addEventListener('resize', () => { clampResizablePanels(); map.invalidateSize(false); });
scheduleHttpFallback();
scheduleConsolePresenceHeartbeat();
bootstrap();
connectWs();
state.preScrambleTimer = setInterval(() => renderPreScrambleWarning(), 1000);
state.staleWatchdogTimer = setInterval(() => {
  if (state.data) {
    updateFeedStaleState(state.data);
    updateStatus(state.data);
  }
}, 5000);

}
