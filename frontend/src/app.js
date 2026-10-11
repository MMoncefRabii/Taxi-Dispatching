const TUNIS_CENTER = [36.8065, 10.1815];
const API_BASE_URL = new URL(window.FLEET_CONFIG.apiBaseUrl);
if (!['http:', 'https:'].includes(API_BASE_URL.protocol)) {
  throw new Error('The API base URL must use HTTP or HTTPS.');
}

function apiUrl(path) {
  return new URL(path, API_BASE_URL);
}

const STATUS = {
  ONLINE: 'online',
  STALE: 'stale',
  OFFLINE: 'offline'
};

const state = {
  drivers: new Map(),
  selectedDriverId: null,
  ws: null,
  reconnectTimer: null,
  liveStatus: 'reconnecting',
  search: '',
  driverFilter: 'all',
  editingDriverId: null,
  lastRefreshAt: 0,
  admins: [],
  adminsOffset: 0,
  adminsHasMore: false,

  authenticated: false
};

const map = L.map('map', { zoomControl: true }).setView(TUNIS_CENTER, 11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

const markerLayer = L.layerGroup().addTo(map);
const driverMap = new Map();

const elements = {
  loginOverlay: document.getElementById('loginOverlay'),
  loginForm: document.getElementById('loginForm'),
  adminEmailInput: document.getElementById('adminEmailInput'),
  adminPasswordInput: document.getElementById('adminPasswordInput'),
  loginError: document.getElementById('loginError'),
  loginBtn: document.getElementById('loginBtn'),
  logoutBtn: document.getElementById('logoutBtn'),
  driversViewBtn: document.getElementById('driversViewBtn'),
  adminsViewBtn: document.getElementById('adminsViewBtn'),
  driversView: document.getElementById('driversView'),
  adminsView: document.getElementById('adminsView'),
  adminsError: document.getElementById('adminsError'),
  adminList: document.getElementById('adminList'),
  loadMoreAdminsBtn: document.getElementById('loadMoreAdminsBtn'),
  driverList: document.getElementById('driverList'),
  fitBtn: document.getElementById('fitBtn'),
  searchInput: document.getElementById('searchInput'),
  driverFilter: document.getElementById('driverFilter'),
  counterOnline: document.getElementById('counter-online'),
  counterStale: document.getElementById('counter-stale'),
  counterOffline: document.getElementById('counter-offline'),
  liveText: document.getElementById('live-text'),
  liveDot: document.getElementById('live-dot'),
  sidebar: document.getElementById('sidebar'),
  collapseBtn: document.getElementById('collapseBtn'),
  newDriverBtn: document.getElementById('newDriverBtn'),
  newDriverOverlay: document.getElementById('newDriverOverlay'),
  newDriverForm: document.getElementById('newDriverForm'),
  newDriverTitle: document.getElementById('newDriverTitle'),
  newDriverName: document.getElementById('newDriverName'),
  newDriverPhone: document.getElementById('newDriverPhone'),
  newDriverTaxiNumber: document.getElementById('newDriverTaxiNumber'),
  newDriverPlate: document.getElementById('newDriverPlate'),
  newDriverModel: document.getElementById('newDriverModel'),
  newDriverError: document.getElementById('newDriverError'),
  cancelNewDriverBtn: document.getElementById('cancelNewDriverBtn'),
  submitNewDriverBtn: document.getElementById('submitNewDriverBtn'),
  driverTokenOverlay: document.getElementById('driverTokenOverlay'),
  createdDriverName: document.getElementById('createdDriverName'),
  createdDriverToken: document.getElementById('createdDriverToken'),
  copyTokenBtn: document.getElementById('copyTokenBtn'),
  closeTokenDialogBtn: document.getElementById('closeTokenDialogBtn'),
  copyTokenStatus: document.getElementById('copyTokenStatus'),
  listRefreshError: document.getElementById('listRefreshError')
};

let oneTimeToken = '';

function getDriverStatus(driver) {
  if (!driver || driver.active === false || driver.lat == null || driver.lng == null) {
    return STATUS.OFFLINE;
  }
  if (driver.online === 1) {
    const now = Date.now() / 1000;
    if (now - Number(driver.recorded_at || 0) <= 60) {
      return STATUS.ONLINE;
    }
    return STATUS.STALE;
  }
  return STATUS.OFFLINE;
}

function getStatusColor(driver) {
  const status = getDriverStatus(driver);
  if (status === STATUS.ONLINE) return '#1bbf5c';
  if (status === STATUS.STALE) return '#f2a93b';
  return '#7f8a9b';
}

function getStatusLabel(driver) {
  const status = getDriverStatus(driver);
  if (status === STATUS.ONLINE) return 'online';
  if (status === STATUS.STALE) return 'stale';
  return 'offline';
}

function formatSpeedKmh(speedMps) {
  if (speedMps == null || Number.isNaN(Number(speedMps))) return '—';
  const value = Number(speedMps) * 3.6;
  return `${value.toFixed(1)} km/h`;
}

function formatLastSeen(driver) {
  if (driver == null || driver.recorded_at == null) {
    return 'never';
  }
  const secs = Math.max(0, Math.floor((Date.now() / 1000) - Number(driver.recorded_at)));
  if (secs < 60) return `${secs} s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  return `${hours} h ago`;
}

function makeDriverIcon(driver) {
  const color = getStatusColor(driver);
  const arrow = document.createElement('div');
  arrow.className = 'driver-marker';
  arrow.style.width = '18px';
  arrow.style.height = '18px';
  arrow.style.borderRadius = '50%';
  arrow.style.background = color;
  arrow.style.border = '2px solid rgba(255,255,255,0.9)';
  arrow.style.boxShadow = '0 2px 6px rgba(0,0,0,0.28)';
  arrow.style.position = 'relative';
  arrow.style.transition = 'transform 0.3s ease';
  arrow.style.transform = 'rotate(0deg)';
  arrow.style.display = 'flex';
  arrow.style.alignItems = 'center';
  arrow.style.justifyContent = 'center';
  arrow.style.fontSize = '12px';
  arrow.style.color = '#fff';
  arrow.style.fontWeight = '700';

  const needle = document.createElement('span');
  needle.textContent = '→';
  needle.style.display = 'block';
  const heading = Number(driver.heading);
  needle.style.transform = `rotate(${Number.isFinite(heading) ? heading : 0}deg)`;
  needle.style.transition = 'transform 0.25s ease';
  needle.style.pointerEvents = 'none';
  arrow.appendChild(needle);

  return L.divIcon({
    className: 'custom-driver-icon',
    html: arrow,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -14]
  });
}

function updateMarker(driver) {
  const id = String(driver.id);
  const marker = driverMap.get(id);
  if (!driver || driver.lat == null || driver.lng == null) {
    if (marker) {
      markerLayer.removeLayer(marker);
      driverMap.delete(id);
    }
    return;
  }

  if (!marker) {
    const newMarker = L.marker([driver.lat, driver.lng], {
      icon: makeDriverIcon(driver),
      keyboard: false
    }).addTo(markerLayer);

    newMarker.on('click', () => {
      state.selectedDriverId = id;
      renderList();
      openDriverCard(driver);
    });

    driverMap.set(id, newMarker);
  } else {
    marker.setLatLng([driver.lat, driver.lng]);
    marker.setIcon(makeDriverIcon(driver));
  }
}

function openDriverCard(driver) {
  const status = getDriverStatus(driver);
  const statusClass = status === STATUS.ONLINE ? 'online' : status === STATUS.STALE ? 'stale' : 'offline';
  const content = document.createElement('div');
  content.className = 'driver-card';
  const name = document.createElement('h3');
  name.textContent = String(driver.name || 'Unknown driver');
  content.appendChild(name);

  const statusChip = document.createElement('div');
  statusChip.className = `status-chip ${statusClass}`;
  statusChip.textContent = status;
  content.appendChild(statusChip);

  const phoneRow = document.createElement('div');
  phoneRow.className = 'row';
  const phoneLabel = document.createElement('span');
  phoneLabel.textContent = 'Phone';
  const phoneLink = document.createElement('a');
  const phone = String(driver.phone || '');
  phoneLink.href = `tel:${encodeURIComponent(phone)}`;
  phoneLink.textContent = phone || '—';
  phoneRow.append(phoneLabel, phoneLink);
  content.appendChild(phoneRow);

  const speedRow = document.createElement('div');
  speedRow.className = 'row';
  const speedLabel = document.createElement('span');
  speedLabel.textContent = 'Speed';
  const speedValue = document.createElement('span');
  speedValue.textContent = formatSpeedKmh(driver.speed);
  speedRow.append(speedLabel, speedValue);
  content.appendChild(speedRow);

  const lastSeenRow = document.createElement('div');
  lastSeenRow.className = 'row';
  const lastSeenLabel = document.createElement('span');
  lastSeenLabel.textContent = 'Last seen';
  const lastSeenValue = document.createElement('span');
  lastSeenValue.textContent = formatLastSeen(driver);
  lastSeenRow.append(lastSeenLabel, lastSeenValue);
  content.appendChild(lastSeenRow);

  const marker = driverMap.get(String(driver.id));
  if (marker) {
    marker.bindPopup(content).openPopup();
  }
}

function renderCounters() {
  const drivers = Array.from(state.drivers.values());
  const online = drivers.filter((d) => getDriverStatus(d) === STATUS.ONLINE).length;
  const stale = drivers.filter((d) => getDriverStatus(d) === STATUS.STALE).length;
  const offline = drivers.filter((d) => getDriverStatus(d) === STATUS.OFFLINE).length;

  elements.counterOnline.textContent = String(online);
  elements.counterStale.textContent = String(stale);
  elements.counterOffline.textContent = String(offline);
}

function renderList() {
  const query = elements.searchInput.value.trim().toLowerCase();
  let rows = Array.from(state.drivers.values());
  rows = rows.filter((driver) => {
    if (state.driverFilter === 'active' && driver.active === false) return false;
    if (state.driverFilter === 'inactive' && driver.active !== false) return false;
    if (!query) return true;
    const vehicle = driver.vehicle || {};
    return `${driver.name || ''} ${driver.phone || ''} ${vehicle.plate_number || ''} ${vehicle.taxi_number || ''} ${vehicle.type || ''}`
      .toLowerCase()
      .includes(query);
  });

  rows.sort((a, b) => {
    const statusOrder = { [STATUS.ONLINE]: 0, [STATUS.STALE]: 1, [STATUS.OFFLINE]: 2 };
    const byStatus = statusOrder[getDriverStatus(a)] - statusOrder[getDriverStatus(b)];
    if (byStatus !== 0) return byStatus;
    return String(a.name || '').localeCompare(String(b.name || ''));
  });

  if (!rows.length) {
    const emptyMessage = document.createElement('div');
    emptyMessage.style.padding = '12px';
    emptyMessage.style.color = 'var(--muted)';
    emptyMessage.textContent = 'No drivers found.';
    elements.driverList.replaceChildren(emptyMessage);
    return;
  }

  const items = rows.map((driver) => {
    const status = getDriverStatus(driver);
    const statusColor = getStatusColor(driver);
    const isActive = String(state.selectedDriverId) === String(driver.id);
    const row = document.createElement('article');
    row.className = `driver-item${isActive ? ' active' : ''}${driver.active === false ? ' inactive' : ''}`;

    const dot = document.createElement('span');
    dot.className = 'driver-dot';
    dot.style.background = statusColor;
    const selectButton = document.createElement('button');
    selectButton.className = 'driver-select';
    selectButton.type = 'button';
    const main = document.createElement('span');
    main.className = 'driver-main';
    const name = document.createElement('span');
    name.className = 'driver-name';
    name.textContent = String(driver.name || 'Unknown driver');
    const meta = document.createElement('span');
    meta.className = 'driver-meta';
    const phone = document.createElement('span');
    phone.textContent = String(driver.phone || '—');
    const statusText = document.createElement('span');
    statusText.textContent = status;
    meta.append(phone, statusText);
    if (driver.active === false) {
      const inactiveBadge = document.createElement('span');
      inactiveBadge.className = 'inactive-badge';
      inactiveBadge.textContent = 'Inactive';
      meta.appendChild(inactiveBadge);
    }
    main.append(name, meta);

    const vehicleLabel = document.createElement('span');
    vehicleLabel.className = 'driver-vehicle';
    const vehicle = driver.vehicle || {};
    vehicleLabel.textContent = [vehicle.plate_number, vehicle.type]
      .filter(Boolean)
      .join(' · ') || 'No vehicle';
    main.appendChild(vehicleLabel);
    const speed = document.createElement('span');
    speed.className = 'driver-speed';
    speed.append(document.createTextNode(formatSpeedKmh(driver.speed)));
    speed.append(document.createElement('br'));
    speed.append(document.createTextNode(formatLastSeen(driver)));
    selectButton.append(dot, main, speed);
    selectButton.addEventListener('click', () => {
      state.selectedDriverId = String(driver.id);
      renderList();
      openDriverCard(driver);
    });
    const actions = document.createElement('div');
    actions.className = 'driver-actions';
    const editButton = document.createElement('button');
    editButton.className = 'btn secondary';
    editButton.type = 'button';
    editButton.textContent = 'Edit';
    editButton.addEventListener('click', () => showNewDriverDialog(driver));
    actions.appendChild(editButton);

    if (driver.active === false) {
      const reactivateButton = document.createElement('button');
      reactivateButton.className = 'btn secondary';
      reactivateButton.type = 'button';
      reactivateButton.textContent = 'Reactivate';
      reactivateButton.addEventListener('click', () => reactivateDriver(driver));
      actions.appendChild(reactivateButton);
    } else {
      const deactivateButton = document.createElement('button');
      deactivateButton.className = 'btn secondary danger-button';
      deactivateButton.type = 'button';
      deactivateButton.textContent = 'Deactivate';
      deactivateButton.addEventListener('click', () => deactivateDriver(driver));
      actions.appendChild(deactivateButton);

      const tokenButton = document.createElement('button');
      tokenButton.className = 'btn secondary';
      tokenButton.type = 'button';
      tokenButton.textContent = 'New token';
      tokenButton.addEventListener('click', () => regenerateDriverToken(driver));
      actions.appendChild(tokenButton);
    }
    row.append(selectButton, actions);
    return row;
  });
  elements.driverList.replaceChildren(...items);
}

function updateDriverListState() {
  for (const driver of state.drivers.values()) {
    updateMarker(driver);
  }
  renderCounters();
  renderList();
  maybeFitMap();
}

function maybeFitMap() {
  const drivers = Array.from(state.drivers.values()).filter((d) => d.lat != null && d.lng != null);
  if (!drivers.length) {
    map.setView(TUNIS_CENTER, 11);
    return;
  }
  const bounds = L.latLngBounds(drivers.map((d) => [d.lat, d.lng]));
  map.fitBounds(bounds.pad(0.22), { animate: true });
}

function setLiveStatus(label, isLive) {
  state.liveStatus = label;
  elements.liveText.textContent = label === 'Live' ? 'Live' : 'Reconnecting';
  elements.liveDot.classList.toggle('live', isLive);
  elements.liveDot.classList.toggle('reconnect', !isLive);
}

function setDriver(driver) {
  state.drivers.set(String(driver.id), driver);
  updateDriverListState();
}

function handleLocationEvent(event) {
  const driverId = String(event.driver_id);
  const driver = state.drivers.get(driverId);
  const next = driver ? { ...driver } : { id: driverId, name: event.name || '', phone: '', online: 0, lat: null, lng: null, speed: null, heading: null, accuracy: null, recorded_at: null };
  next.name = event.name || next.name || 'Unknown driver';
  next.lat = Number(event.lat);
  next.lng = Number(event.lng);
  next.speed = event.speed ?? next.speed ?? null;
  next.heading = event.heading ?? next.heading ?? 0;
  next.recorded_at = Number(event.recorded_at);
  next.online = next.active === false ? 0 : 1;
  state.drivers.set(driverId, next);
  updateDriverListState();
}

function handleStatusEvent(event) {
  const driverId = String(event.driver_id);
  const driver = state.drivers.get(driverId);
  const next = driver ? { ...driver } : { id: driverId, name: 'Unknown driver', phone: '', online: 0, lat: null, lng: null, speed: null, heading: null, accuracy: null, recorded_at: null };
  next.online = next.active === false ? 0 : event.online ? 1 : 0;
  state.drivers.set(driverId, next);
  updateDriverListState();
}

function handleDriverStatusEvent(event) {
  const driverId = String(event.driver_id);
  const driver = state.drivers.get(driverId);
  const next = driver ? { ...driver } : {
    id: driverId,
    name: 'Unknown driver',
    phone: '',
    online: 0,
    active: false,
    vehicle: null,
    lat: null,
    lng: null,
    speed: null,
    heading: null,
    accuracy: null,
    recorded_at: null
  };
  next.active = Boolean(event.active);
  next.online = next.active && event.online ? 1 : 0;
  state.drivers.set(driverId, next);
  updateDriverListState();
}

function updateDriverFromListRow(row) {
  if (!row) return;
  const id = String(row.id);
  const existing = state.drivers.get(id) || { id, name: '', phone: '', online: 0, active: true, vehicle: null, lat: null, lng: null, speed: null, heading: null, accuracy: null, recorded_at: null };
  existing.name = row.name;
  existing.phone = row.phone;
  existing.active = row.active !== false;
  existing.deactivated_at = row.deactivated_at;
  existing.vehicle = row.vehicle;
  existing.online = row.online;
  existing.lat = row.lat;
  existing.lng = row.lng;
  existing.speed = row.speed;
  existing.heading = row.heading;
  existing.accuracy = row.accuracy;
  existing.recorded_at = row.recorded_at;
  state.drivers.set(id, existing);
  updateDriverListState();
}

async function fetchLatestDrivers() {
  const response = await fetch(apiUrl('/admin/drivers/latest'), {
    credentials: 'include'
  });

  if (response.status === 401) {
    await logout();
    return;
  }

  if (!response.ok) {
    throw new Error(`Failed to load drivers: ${response.status}`);
  }

  const rows = await response.json();
  state.drivers.clear();
  for (const row of rows) {
    updateDriverFromListRow(row);
  }
  updateDriverListState();
  state.lastRefreshAt = Date.now();
}

function setSidebarView(view) {
  const showAdmins = view === 'admins';
  elements.driversView.hidden = showAdmins;
  elements.adminsView.hidden = !showAdmins;
  elements.driversViewBtn.classList.toggle('selected', !showAdmins);
  elements.adminsViewBtn.classList.toggle('selected', showAdmins);
  elements.driversViewBtn.setAttribute('aria-selected', String(!showAdmins));
  elements.adminsViewBtn.setAttribute('aria-selected', String(showAdmins));
  if (showAdmins) fetchAdmins(false);
}

async function fetchAdmins(append) {
  if (!state.authenticated) return;
  if (!append) {
    state.admins = [];
    state.adminsOffset = 0;
    state.adminsHasMore = false;
  }
  elements.adminsError.textContent = '';
  elements.loadMoreAdminsBtn.disabled = true;
  try {
    const url = apiUrl('/admin/admins');
    url.searchParams.set('limit', '200');
    url.searchParams.set('offset', String(state.adminsOffset));
    const response = await fetch(url, { credentials: 'include' });
    if (response.status === 401) {
      await logout();
      return;
    }
    if (!response.ok) throw new Error(`Unable to load admins: ${response.status}`);
    const rows = await response.json();
    if (!Array.isArray(rows)) throw new Error('Invalid admin list response.');
    state.admins = append ? state.admins.concat(rows) : rows;
    state.adminsOffset += rows.length;
    state.adminsHasMore = rows.length === 200;
    renderAdmins();
  } catch (error) {
    console.error(error);
    elements.adminsError.textContent = 'Unable to load admins. Please try again.';
  } finally {
    elements.loadMoreAdminsBtn.disabled = false;
  }
}

function renderAdmins() {
  const rows = state.admins.map((admin) => {
    const row = document.createElement('article');
    row.className = 'admin-item';
    const details = document.createElement('div');
    details.className = 'admin-details';
    const email = document.createElement('strong');
    email.className = 'admin-email';
    email.textContent = String(admin.email || 'Unknown admin');

    const badges = document.createElement('div');
    badges.className = 'admin-badges';
    const status = document.createElement('span');
    status.className = admin.active ? 'admin-badge active' : 'admin-badge inactive';
    status.textContent = admin.active ? 'Active' : 'Inactive';
    badges.appendChild(status);
    if (admin.is_self) {
      const self = document.createElement('span');
      self.className = 'admin-badge self';
      self.textContent = 'You';
      badges.appendChild(self);
    }
    const metadata = document.createElement('span');
    metadata.className = 'admin-meta';
    const createdAt = admin.created_at ? new Date(admin.created_at) : null;
    metadata.textContent = createdAt && !Number.isNaN(createdAt.getTime())
      ? `Created ${createdAt.toLocaleDateString()}`
      : '';
    details.append(email, badges, metadata);
    row.appendChild(details);

    if (admin.active && !admin.is_self) {
      const button = document.createElement('button');
      button.className = 'btn secondary danger-button';
      button.type = 'button';
      button.textContent = 'Deactivate';
      button.addEventListener('click', () => deactivateAdmin(admin));
      row.appendChild(button);
    }
    return row;
  });
  if (rows.length === 0) {
    const emptyMessage = document.createElement('p');
    emptyMessage.className = 'admin-empty';
    emptyMessage.textContent = 'No admins found.';
    rows.push(emptyMessage);
  }
  elements.adminList.replaceChildren(...rows);
  elements.loadMoreAdminsBtn.hidden = !state.adminsHasMore;
}

async function deactivateAdmin(admin) {
  if (!window.confirm(`Deactivate ${String(admin.email || 'this admin')}?`)) return;
  elements.adminsError.textContent = '';
  try {
    const response = await fetch(
      apiUrl(`/admin/admins/${encodeURIComponent(admin.id)}/deactivate`),
      { method: 'POST', credentials: 'include' }
    );
    if (response.status === 401) {
      await logout();
      return;
    }
    if (response.status === 409) {
      elements.adminsError.textContent =
        'This admin cannot be deactivated. The last active admin in a center must remain active.';
      return;
    }
    if (response.status === 404) {
      elements.adminsError.textContent = 'Admin not found in your center.';
      return;
    }
    if (!response.ok) throw new Error(`Unable to deactivate admin: ${response.status}`);
    await fetchAdmins(false);
  } catch (error) {
    console.error(error);
    elements.adminsError.textContent = 'Unable to deactivate this admin. Please try again.';
  }
}

function tryConnectWebSocket() {
  if (!state.authenticated) return;

  const socketUrl = apiUrl('/ws');
  socketUrl.protocol = socketUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(socketUrl);
  state.ws = socket;

  socket.addEventListener('open', () => {
    setLiveStatus('Live', true);
    fetchLatestDrivers().catch(() => setLiveStatus('Reconnecting', false));
  });

  socket.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'location') {
        handleLocationEvent(data);
      } else if (data.type === 'status') {
        handleStatusEvent(data);
      } else if (data.type === 'driver_status') {
        handleDriverStatusEvent(data);
      }
    } catch (err) {
      console.error('WS message parse error', err);
    }
  });

  socket.addEventListener('close', () => {
    setLiveStatus('Reconnecting', false);
    if (state.ws === socket) {
      state.ws = null;
    }
    if (!state.authenticated) return;
    if (state.reconnectTimer) clearTimeout(state.reconnectTimer);
    state.reconnectTimer = setTimeout(() => {
      tryConnectWebSocket();
      fetchLatestDrivers().catch((err) => {
        console.error(err);
        setLiveStatus('Reconnecting', false);
      });
    }, 3000);
  });

  socket.addEventListener('error', () => {
    socket.close();
  });
}

function showLogin() {
  elements.loginOverlay.style.display = 'flex';
  elements.adminPasswordInput.value = '';
  elements.loginError.textContent = '';
  elements.adminEmailInput.focus();
}

function hideLogin() {
  elements.loginOverlay.style.display = 'none';
}

function showNewDriverDialog(driver = null) {
  state.editingDriverId = driver ? String(driver.id) : null;
  elements.newDriverTitle.textContent = driver ? 'Edit driver' : 'New driver';
  elements.submitNewDriverBtn.textContent = driver ? 'Save changes' : 'Create driver';
  elements.newDriverError.textContent = '';
  elements.newDriverPlate.setCustomValidity('');
  elements.newDriverForm.reset();
  if (driver) {
    const vehicle = driver.vehicle || {};
    elements.newDriverName.value = String(driver.name || '');
    elements.newDriverPhone.value = String(driver.phone || '');
    elements.newDriverTaxiNumber.value = String(vehicle.taxi_number || '');
    elements.newDriverPlate.value = String(vehicle.plate_number || '');
    elements.newDriverModel.value = String(vehicle.type || '');
  }
  elements.newDriverOverlay.hidden = false;
  elements.newDriverName.focus();
}

function closeNewDriverDialog() {
  elements.newDriverOverlay.hidden = true;
  elements.newDriverForm.reset();
  elements.newDriverPlate.setCustomValidity('');
  state.editingDriverId = null;
  elements.newDriverTitle.textContent = 'New driver';
  elements.submitNewDriverBtn.textContent = 'Create driver';
  elements.newDriverError.textContent = '';
  elements.newDriverBtn.focus();
}

function closeTokenDialog() {
  oneTimeToken = '';
  elements.createdDriverToken.textContent = '';
  elements.createdDriverName.textContent = '';
  elements.copyTokenStatus.textContent = '';
  elements.listRefreshError.textContent = '';
  elements.driverTokenOverlay.hidden = true;
  elements.newDriverBtn.focus();
}

function showOneTimeTokenDialog(name, token) {
  oneTimeToken = token;
  elements.createdDriverName.textContent = name;
  elements.createdDriverToken.textContent = oneTimeToken;
  elements.copyTokenStatus.textContent = '';
  elements.listRefreshError.textContent = '';
  elements.driverTokenOverlay.hidden = false;
}

async function createDriver(event) {
  event.preventDefault();
  elements.newDriverPlate.setCustomValidity('');
  if (!elements.newDriverForm.reportValidity()) return;

  const plate = elements.newDriverPlate.value.trim().toUpperCase();
  if (!/^[A-Z0-9](?:[A-Z0-9 -]{0,48}[A-Z0-9])?$/.test(plate)) {
    elements.newDriverPlate.setCustomValidity(
      'Use letters, numbers, spaces, and hyphens; the plate must start and end with a letter or number.'
    );
    elements.newDriverForm.reportValidity();
    return;
  }
  elements.newDriverError.textContent = '';
  elements.submitNewDriverBtn.disabled = true;
  const name = elements.newDriverName.value.trim();
  const phone = elements.newDriverPhone.value.trim();
  const driverId = state.editingDriverId;
  const body = {
    name,
    phone,
    vehicle: {
      taxi_number: elements.newDriverTaxiNumber.value.trim(),
      plate_number: plate,
      type: elements.newDriverModel.value.trim() || null
    }
  };

  try {
    const response = await fetch(
      apiUrl(driverId ? `/admin/drivers/${encodeURIComponent(driverId)}` : '/admin/drivers'),
      {
        method: driverId ? 'PATCH' : 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      }
    );

    if (!response.ok) {
      if (response.status === 401) {
        await logout();
        elements.newDriverError.textContent = 'Your admin session is no longer valid. Log in again.';
      } else if (response.status === 422) {
        elements.newDriverError.textContent =
          'Check the driver and vehicle fields and try again.';
      } else if (response.status === 409) {
        elements.newDriverError.textContent =
          'That taxi number is already assigned. Check the vehicle details and try again.';
      } else {
        elements.newDriverError.textContent = 'Unable to save the driver. Please try again.';
      }
      return;
    }

    const result = await response.json();
    closeNewDriverDialog();

    if (!driverId) {
      if (!result || typeof result.token !== 'string' || !result.token) {
        window.alert('The driver was created, but no token was returned. Contact support.');
        return;
      }
      const token = result.token;
      result.token = '';
      showOneTimeTokenDialog(String(result.name || name), token);
    }

    try {
      await fetchLatestDrivers();
    } catch {
      if (!elements.driverTokenOverlay.hidden) {
        elements.listRefreshError.textContent =
          'The driver was saved, but the list could not be refreshed. Refresh the page to see the changes.';
      } else {
        window.alert('The driver was saved, but the list could not be refreshed. Refresh the page.');
      }
    }
  } catch {
    elements.newDriverError.textContent =
      'Unable to save the driver. Check your connection and try again.';
  } finally {
    elements.submitNewDriverBtn.disabled = false;
  }
}

async function sendDriverAction(path) {
  const response = await fetch(apiUrl(path), {
    method: 'POST',
    credentials: 'include'
  });
  if (response.status === 401) {
    await logout();
    throw new Error('unauthorized');
  }
  if (!response.ok) {
    throw new Error(String(response.status));
  }
  return response.json();
}

async function deactivateDriver(driver) {
  if (!window.confirm(`Deactivate ${driver.name}? The driver will be signed out immediately.`)) {
    return;
  }
  try {
    await sendDriverAction(`/admin/drivers/${encodeURIComponent(driver.id)}/deactivate`);
  } catch (error) {
    if (error.message !== 'unauthorized') {
      window.alert('Unable to deactivate the driver. Please try again.');
    }
    return;
  }
  try {
    await fetchLatestDrivers();
  } catch {
    window.alert('The driver was deactivated, but the list could not be refreshed.');
  }
}

async function reactivateDriver(driver) {
  let tokenShown = false;
  try {
    const result = await sendDriverAction(
      `/admin/drivers/${encodeURIComponent(driver.id)}/reactivate`
    );
    if (!result || typeof result.token !== 'string' || !result.token) {
      window.alert('The driver was reactivated, but no token was returned. Contact support.');
      return;
    }
    const token = result.token;
    result.token = '';
    showOneTimeTokenDialog(String(driver.name || 'Driver token'), token);
    tokenShown = true;
  } catch (error) {
    if (error.message !== 'unauthorized') {
      window.alert('Unable to reactivate the driver. Please try again.');
    }
    return;
  }
  try {
    await fetchLatestDrivers();
  } catch {
    if (tokenShown) {
      elements.listRefreshError.textContent =
        'The driver was reactivated, but the list could not be refreshed. Refresh the page.';
    }
  }
}

async function regenerateDriverToken(driver) {
  if (!window.confirm(
    `Generate a new token for ${driver.name}? The old token will stop working immediately.`
  )) {
    return;
  }
  let tokenShown = false;
  try {
    const result = await sendDriverAction(
      `/admin/drivers/${encodeURIComponent(driver.id)}/token`
    );
    if (!result || typeof result.token !== 'string' || !result.token) {
      window.alert('No new token was returned. Contact support.');
      return;
    }
    const token = result.token;
    result.token = '';
    showOneTimeTokenDialog(String(driver.name || 'Driver token'), token);
    tokenShown = true;
  } catch (error) {
    if (error.message !== 'unauthorized') {
      window.alert('Unable to generate a new token. Please try again.');
    }
    return;
  }
  try {
    await fetchLatestDrivers();
  } catch {
    if (tokenShown) {
      elements.listRefreshError.textContent =
        'The token was changed, but the list could not be refreshed. Refresh the page.';
    }
  }
}

async function login(event) {
  event.preventDefault();
  if (!elements.loginForm.reportValidity()) return;
  elements.loginBtn.disabled = true;
  elements.loginError.textContent = '';
  try {
    const response = await fetch(apiUrl('/admin/login'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: elements.adminEmailInput.value,
        password: elements.adminPasswordInput.value
      })
    });

    if (response.status === 401) {
      elements.loginError.textContent = 'Invalid email or password.';
      return;
    }

    if (!response.ok) {
      throw new Error(`Unable to log in: ${response.status}`);
    }

    state.authenticated = true;
    elements.adminPasswordInput.value = '';
    hideLogin();
    await fetchLatestDrivers();
    if (!elements.adminsView.hidden) await fetchAdmins(false);
    tryConnectWebSocket();
  } catch (err) {
    console.error(err);
    elements.loginError.textContent = 'Unable to connect to the server.';
  } finally {
    elements.loginBtn.disabled = false;
  }
}

async function logout() {
  let logoutFailed = false;
  try {
    const response = await fetch(apiUrl('/admin/logout'), {
      method: 'POST',
      credentials: 'include'
    });
    if (!response.ok) {
      throw new Error(`Unable to log out: ${response.status}`);
    }
  } catch (err) {
    console.error(err);
    logoutFailed = true;
  }

  state.authenticated = false;
  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }
  state.drivers.clear();
  state.admins = [];
  state.adminsOffset = 0;
  state.adminsHasMore = false;
  elements.adminList.replaceChildren();
  updateDriverListState();
  showLogin();
  if (logoutFailed) {
    elements.loginError.textContent =
      'Unable to confirm logout with the server. Please try again.';
  }
}

function startStatusTimer() {
  setInterval(() => {
    renderCounters();
    renderList();
  }, 5000);
}

async function initialize() {
  try {
    const response = await fetch(apiUrl('/admin/me'), {
      credentials: 'include'
    });
    if (response.status === 401) {
      state.authenticated = false;
      showLogin();
      return;
    }
    if (!response.ok) {
      throw new Error(`Unable to check admin session: ${response.status}`);
    }

    const admin = await response.json();
    state.authenticated = true;
    hideLogin();
    await fetchLatestDrivers();
    if (!elements.adminsView.hidden) await fetchAdmins(false);
    tryConnectWebSocket();
  } catch (err) {
    console.error(err);
    state.authenticated = false;
    showLogin();
    elements.loginError.textContent = 'Unable to check your admin session.';
  }
}

function init() {
  elements.loginForm.addEventListener('submit', login);
  elements.logoutBtn.addEventListener('click', logout);
  elements.driversViewBtn.addEventListener('click', () => setSidebarView('drivers'));
  elements.adminsViewBtn.addEventListener('click', () => setSidebarView('admins'));
  elements.loadMoreAdminsBtn.addEventListener('click', () => fetchAdmins(true));
  elements.newDriverBtn.addEventListener('click', () => showNewDriverDialog());
  elements.cancelNewDriverBtn.addEventListener('click', closeNewDriverDialog);
  elements.newDriverForm.addEventListener('submit', createDriver);
  elements.newDriverOverlay.addEventListener('click', (event) => {
    if (event.target === elements.newDriverOverlay) closeNewDriverDialog();
  });
  elements.driverTokenOverlay.addEventListener('click', (event) => {
    if (event.target === elements.driverTokenOverlay) closeTokenDialog();
  });
  elements.closeTokenDialogBtn.addEventListener('click', closeTokenDialog);
  elements.copyTokenBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(oneTimeToken);
      elements.copyTokenStatus.textContent = 'Token copied.';
    } catch {
      elements.copyTokenStatus.textContent = 'Could not copy. Select the token and copy it manually.';
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!elements.driverTokenOverlay.hidden) {
      closeTokenDialog();
    } else if (!elements.newDriverOverlay.hidden) {
      closeNewDriverDialog();
    }
  });
  elements.collapseBtn.addEventListener('click', () => {
    elements.sidebar.classList.toggle('collapsed');
  });
  elements.searchInput.addEventListener('input', (event) => {
    state.search = event.target.value.trim();
    renderList();
  });
  elements.driverFilter.addEventListener('change', (event) => {
    state.driverFilter = event.target.value;
    renderList();
  });
  elements.fitBtn.addEventListener('click', () => {
    maybeFitMap();
  });
  document.getElementById('sidebar').addEventListener('click', (event) => {
    if (event.target.closest('button')) return;
  });

  startStatusTimer();
  initialize();
}

init();