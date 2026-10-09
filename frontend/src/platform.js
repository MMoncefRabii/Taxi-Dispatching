(() => {
  const config = window.FLEET_CONFIG;
  const loginView = document.getElementById('loginView');
  const consoleView = document.getElementById('consoleView');
  const loginForm = document.getElementById('loginForm');
  const loginMessage = document.getElementById('loginMessage');
  const consoleMessage = document.getElementById('consoleMessage');
  const centerForm = document.getElementById('centerForm');
  const centerMessage = document.getElementById('centerMessage');
  const centersTableBody = document.getElementById('centersTableBody');
  const centersEmpty = document.getElementById('centersEmpty');
  const auditTableBody = document.getElementById('auditTableBody');
  const auditEmpty = document.getElementById('auditEmpty');
  const ownerEmail = document.getElementById('ownerEmail');
  const sections = {
    centers: document.getElementById('centersSection'),
    audit: document.getElementById('auditSection'),
  };

  class ApiError extends Error {
    constructor(status, message) {
      super(message);
      this.status = status;
    }
  }

  function endpoint(path) {
    if (!config || typeof config.apiBaseUrl !== 'string') {
      throw new Error('The API base URL is not configured.');
    }
    return `${config.apiBaseUrl.replace(/\/$/, '')}/platform/${path}`;
  }

  async function request(path, options = {}) {
    const response = await fetch(endpoint(path), {
      ...options,
      credentials: 'include',
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    });
    if (response.status === 204) return null;
    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error('The platform API returned an invalid response.');
    }
    if (!response.ok) {
      throw new ApiError(response.status, payload.detail || 'The request failed.');
    }
    return payload;
  }

  function setMessage(element, message) {
    element.textContent = message;
  }

  function showLogin(message = '') {
    consoleView.hidden = true;
    loginView.hidden = false;
    setMessage(loginMessage, message);
  }

  function showConsole(email) {
    loginView.hidden = true;
    consoleView.hidden = false;
    ownerEmail.textContent = email;
  }

  function handleUnauthorized(error) {
    if (error instanceof ApiError && error.status === 401) {
      showLogin('Your session has expired. Please sign in again.');
      return true;
    }
    return false;
  }

  function makeCell(value, className = '') {
    const cell = document.createElement('td');
    cell.textContent = value == null ? '' : String(value);
    if (className) cell.className = className;
    return cell;
  }

  async function loadCenters() {
    setMessage(consoleMessage, '');
    const centers = await request('centers?limit=50&offset=0');
    centersTableBody.replaceChildren();
    for (const center of centers) {
      const row = document.createElement('tr');
      row.append(
        makeCell(center.name),
        makeCell(center.city),
        makeCell(center.timezone),
        makeCell(center.active ? 'Active' : 'Inactive', `status ${center.active ? 'active' : 'inactive'}`),
        makeCell(center.driver_count),
        makeCell(center.admin_count),
      );
      centersTableBody.append(row);
    }
    centersEmpty.hidden = centers.length !== 0;
  }

  async function loadAudit() {
    setMessage(consoleMessage, '');
    const events = await request('audit?limit=50&offset=0');
    auditTableBody.replaceChildren();
    for (const event of events) {
      const row = document.createElement('tr');
      const timestamp = event.created_at
        ? new Date(event.created_at).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, 'Z')
        : '';
      const target = [event.target_type, event.target_id].filter(Boolean).join(' · ');
      row.append(
        makeCell(timestamp),
        makeCell(event.action),
        makeCell(target),
        makeCell(event.success ? 'Success' : 'Failed', `result ${event.success ? 'success' : 'failure'}`),
        makeCell(event.ip),
        makeCell(event.user_agent),
      );
      auditTableBody.append(row);
    }
    auditEmpty.hidden = events.length !== 0;
  }

  async function loadConsole(email) {
    showConsole(email);
    try {
      await Promise.all([loadCenters(), loadAudit()]);
    } catch (error) {
      if (!handleUnauthorized(error)) {
        setMessage(consoleMessage, error.message || 'Could not load console data.');
      }
    }
  }

  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(loginMessage, '');
    const formData = new FormData(loginForm);
    try {
      await request('login', {
        method: 'POST',
        body: JSON.stringify({
          email: formData.get('email'),
          password: formData.get('password'),
        }),
      });
      loginForm.reset();
      const me = await request('me');
      await loadConsole(me.email);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setMessage(loginMessage, 'Invalid email or password.');
      } else if (!handleUnauthorized(error)) {
        setMessage(loginMessage, error.message || 'Could not sign in.');
      }
    }
  });

  centerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(centerMessage, '');
    const formData = new FormData(centerForm);
    try {
      await request('centers', {
        method: 'POST',
        body: JSON.stringify({
          name: formData.get('name'),
          city: formData.get('city'),
          timezone: formData.get('timezone'),
        }),
      });
      centerForm.reset();
      await loadCenters();
      setMessage(centerMessage, 'Center created.');
      centerMessage.classList.add('success');
    } catch (error) {
      centerMessage.classList.remove('success');
      if (!handleUnauthorized(error)) {
        setMessage(centerMessage, error.message || 'Could not create the center.');
      }
    }
  });

  document.getElementById('logoutButton').addEventListener('click', async () => {
    try {
      await request('logout', { method: 'POST' });
      ownerEmail.textContent = '';
      showLogin();
    } catch (error) {
      if (!handleUnauthorized(error)) {
        setMessage(consoleMessage, error.message || 'Could not log out.');
      }
    }
  });

  document.querySelectorAll('[data-section]').forEach((button) => {
    button.addEventListener('click', async () => {
      const selected = button.dataset.section;
      for (const [name, section] of Object.entries(sections)) {
        section.hidden = name !== selected;
      }
      document.querySelectorAll('[data-section]').forEach((link) => {
        link.classList.toggle('selected', link === button);
      });
      if (selected === 'audit') {
        try {
          await loadAudit();
        } catch (error) {
          if (!handleUnauthorized(error)) {
            setMessage(consoleMessage, error.message || 'Could not load the audit log.');
          }
        }
      }
    });
  });

  (async () => {
    try {
      const me = await request('me');
      await loadConsole(me.email);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        showLogin();
      } else {
        showLogin(error.message || 'Could not connect to the platform API.');
      }
    }
  })();
})();
