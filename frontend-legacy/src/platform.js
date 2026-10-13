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
  const inviteAdminDialog = document.getElementById('inviteAdminDialog');
  const inviteAdminForm = document.getElementById('inviteAdminForm');
  const inviteAdminTitle = document.getElementById('inviteAdminTitle');
  const inviteAdminMessage = document.getElementById('inviteAdminMessage');
  const inviteResult = document.getElementById('inviteResult');
  const inviteLink = document.getElementById('inviteLink');
  const inviteToken = document.getElementById('inviteToken');
  const inviteResultMessage = document.getElementById('inviteResultMessage');
  const centerInvitationsDialog = document.getElementById('centerInvitationsDialog');
  const centerInvitationsTitle = document.getElementById('centerInvitationsTitle');
  const centerInvitationsBody = document.getElementById('centerInvitationsBody');
  const centerInvitationsEmpty = document.getElementById('centerInvitationsEmpty');
  const centerInvitationsMessage = document.getElementById('centerInvitationsMessage');
  const auditTableBody = document.getElementById('auditTableBody');
  const auditEmpty = document.getElementById('auditEmpty');
  const ownerEmail = document.getElementById('ownerEmail');
  const devTasksNavButton = document.getElementById('devTasksNavButton');
  const devTaskCards = document.getElementById('devTaskCards');
  const sections = {
    centers: document.getElementById('centersSection'),
    audit: document.getElementById('auditSection'),
    devTasks: document.getElementById('devTasksSection'),
  };
  const devTasks = new Map();
  const devTaskDefinitions = new Map();
  const devRuns = new Map();
  let devTaskPoller = null;
  let pollingDevRuns = false;
  let selectedCenterId = null;
  let selectedCenterName = '';
  let invitationLink = null;
  let invitationToken = null;
  let invitationListCenterId = null;

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
    if (inviteAdminDialog.open) inviteAdminDialog.close();
    clearInvitationDialog();
    if (centerInvitationsDialog.open) centerInvitationsDialog.close();
    invitationListCenterId = null;
    if (devTaskPoller !== null) {
      clearInterval(devTaskPoller);
      devTaskPoller = null;
    }
    devRuns.clear();
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

  function makeButton(label, className, onClick) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.textContent = label;
    button.addEventListener('click', onClick);
    return button;
  }

  function openInvitationForm(center) {
    selectedCenterId = center.id;
    selectedCenterName = center.name;
    inviteAdminForm.reset();
    setMessage(inviteAdminMessage, '');
    inviteAdminTitle.textContent = `Invite an admin to ${center.name}`;
    inviteAdminForm.hidden = false;
    inviteResult.hidden = true;
    inviteAdminDialog.showModal();
  }

  function clearInvitationDialog() {
    invitationLink = null;
    invitationToken = null;
    inviteLink.value = '';
    inviteToken.value = '';
    setMessage(inviteResultMessage, '');
    inviteResultMessage.classList.remove('success');
    inviteAdminForm.reset();
    setMessage(inviteAdminMessage, '');
    inviteAdminForm.hidden = false;
    inviteResult.hidden = true;
    selectedCenterId = null;
    selectedCenterName = '';
  }

  function formatTimestamp(value) {
    return value
      ? new Date(value).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, 'Z')
      : '';
  }

  async function loadCenterInvitations(centerId, centerName) {
    invitationListCenterId = centerId;
    centerInvitationsTitle.textContent = `Invitations · ${centerName}`;
    centerInvitationsBody.replaceChildren();
    centerInvitationsEmpty.hidden = true;
    setMessage(centerInvitationsMessage, '');
    try {
      const invitations = await request(
        `centers/${encodeURIComponent(centerId)}/invitations?limit=50&offset=0`,
      );
      centerInvitationsBody.replaceChildren();
      for (const invitation of invitations) {
        const row = document.createElement('tr');
        row.append(
          makeCell(invitation.email),
          makeCell(formatTimestamp(invitation.created_at)),
          makeCell(formatTimestamp(invitation.expires_at)),
          makeCell(invitation.status, `status ${invitation.status}`),
        );
        const actionCell = makeCell('');
        if (invitation.status === 'pending') {
          const revokeButton = makeButton('Revoke', 'button secondary', async () => {
            revokeButton.disabled = true;
            try {
              await request(
                `invitations/${encodeURIComponent(invitation.id)}/revoke`,
                { method: 'POST' },
              );
              await loadCenterInvitations(invitationListCenterId, centerName);
            } catch (error) {
              revokeButton.disabled = false;
              if (!handleUnauthorized(error)) {
                setMessage(centerInvitationsMessage, error.message || 'Could not revoke the invitation.');
              }
            }
          });
          actionCell.append(revokeButton);
        }
        row.append(actionCell);
        centerInvitationsBody.append(row);
      }
      centerInvitationsEmpty.hidden = invitations.length !== 0;
    } catch (error) {
      if (!handleUnauthorized(error)) {
        setMessage(centerInvitationsMessage, error.message || 'Could not load invitations.');
      }
    }
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
      const actions = makeCell('');
      actions.append(
        makeButton('Invite admin', 'button secondary', () => openInvitationForm(center)),
        makeButton('Invitations', 'button secondary', async () => {
          invitationListCenterId = center.id;
          selectedCenterName = center.name;
          centerInvitationsDialog.showModal();
          await loadCenterInvitations(center.id, center.name);
        }),
      );
      row.append(actions);
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

  function latestRunForTask(taskId) {
    return [...devRuns.values()].reverse().find((run) => run.task_id === taskId);
  }

  function activeRunForTask(taskId) {
    return [...devRuns.values()].reverse().find(
      (run) => run.task_id === taskId && run.status === 'running',
    );
  }

  function formatDuration(seconds) {
    return typeof seconds === 'number' && Number.isFinite(seconds)
      ? `${seconds.toFixed(1)} s`
      : '—';
  }

  function refreshDevTaskCard(task) {
    const cardElements = devTasks.get(task.id);
    if (!cardElements) return;
    try {
      const run = latestRunForTask(task.id);
      const activeRun = activeRunForTask(task.id);
      if (task.kind === 'service') {
        cardElements.badge.textContent = activeRun ? 'Running' : 'Stopped';
        cardElements.badge.className = `dev-task-status ${activeRun ? 'running' : ''}`;
        cardElements.resultStatus.textContent = run ? run.status : 'Ready';
        cardElements.resultStatus.className = `dev-task-status ${run ? run.status : ''}`;
        cardElements.button.textContent = activeRun ? 'Stop' : 'Start';
        cardElements.button.disabled = false;
      } else {
        cardElements.badge.textContent = run ? run.status : 'Ready';
        cardElements.badge.className = `dev-task-status ${run ? run.status : ''}`;
        cardElements.resultStatus.textContent = '';
        cardElements.button.textContent = activeRun ? 'Running' : 'Run';
        cardElements.button.disabled = Boolean(activeRun);
      }
      cardElements.duration.textContent = run
        ? `Duration: ${formatDuration(run.duration_seconds)}`
        : 'Duration: —';
      cardElements.error.hidden = true;
      cardElements.error.textContent = '';
    } catch {
      cardElements.error.textContent = 'This task card could not be updated. Reload the console and try again.';
      cardElements.error.hidden = false;
    }
  }

  function createDevTaskCardError(task) {
    const errorCard = document.createElement('article');
    errorCard.className = 'dev-task-card';
    const title = document.createElement('h2');
    title.textContent = task.label || 'Development task';
    const message = document.createElement('p');
    message.className = 'message';
    message.textContent = 'This task card could not be displayed. Reload the console and try again.';
    errorCard.append(title, message);
    return errorCard;
  }

  function makeDevTaskCard(task) {
    const card = document.createElement('article');
    card.className = 'dev-task-card';
    const heading = document.createElement('div');
    heading.className = 'dev-task-heading';
    const title = document.createElement('h2');
    title.textContent = task.label;
    const badge = document.createElement('span');
    badge.className = 'dev-task-status';
    const resultStatus = document.createElement('span');
    resultStatus.className = 'dev-task-status';
    heading.append(title, badge, resultStatus);

    const description = document.createElement('p');
    description.className = 'dev-task-description';
    description.textContent = task.description;

    const controls = document.createElement('div');
    controls.className = 'dev-task-controls';
    const parameterInputs = new Map();
    for (const parameter of task.parameters || []) {
      const input = document.createElement('input');
      input.type = 'text';
      input.name = parameter.name;
      input.placeholder = parameter.description;
      input.setAttribute('aria-label', parameter.description);
      input.pattern = parameter.pattern;
      controls.append(input);
      parameterInputs.set(parameter.name, input);
    }
    const button = document.createElement('button');
    button.className = 'button primary';
    button.type = 'button';
    controls.append(button);
    const duration = document.createElement('span');
    duration.className = 'dev-task-meta';
    const log = document.createElement('pre');
    log.className = 'dev-task-log';
    log.setAttribute('aria-label', `${task.label} output`);
    log.textContent = '';
    const error = document.createElement('p');
    error.className = 'message';
    error.hidden = true;
    card.append(heading, description, controls, duration, error, log);
    const elements = {
      badge,
      button,
      duration,
      error,
      log,
      parameterInputs,
      resultStatus,
    };
    devTasks.set(task.id, elements);

    button.addEventListener('click', async () => {
      button.disabled = true;
      setMessage(consoleMessage, '');
      try {
        const activeRun = activeRunForTask(task.id);
        let response;
        if (task.kind === 'service' && activeRun) {
          response = await request(`dev/runs/${encodeURIComponent(activeRun.id)}/stop`, {
            method: 'POST',
          });
        } else {
          const parameters = {};
          for (const [name, input] of parameterInputs) {
            if (input.value) parameters[name] = input.value;
          }
          response = await request(`dev/tasks/${encodeURIComponent(task.id)}/run`, {
            method: 'POST',
            body: JSON.stringify(parameters),
          });
          response.outputLines = [];
          response.outputOffset = 0;
          response.output_line_count = 0;
          devRuns.set(response.id, response);
          elements.log.textContent = '';
        }
        if (task.kind === 'service' && activeRun) {
          Object.assign(activeRun, response);
        }
        if (response && response.id) devRuns.set(response.id, response);
        refreshDevTaskCard(task);
        ensureDevTaskPolling();
        await pollDevTaskRuns();
      } catch (error) {
        button.disabled = false;
        if (!handleUnauthorized(error)) {
          setMessage(
            consoleMessage,
            error instanceof ApiError
              ? error.message
              : 'Could not update this task card. Reload the console and try again.',
          );
        }
      }
    });

    refreshDevTaskCard(task);
    return card;
  }

  function ensureDevTaskPolling() {
    const needsPolling = [...devRuns.values()].some(
      (run) => run.status === 'running' || (run.outputOffset || 0) < (run.output_line_count || 0),
    );
    if (needsPolling && devTaskPoller === null) {
      devTaskPoller = setInterval(pollDevTaskRuns, 1000);
    } else if (!needsPolling && devTaskPoller !== null) {
      clearInterval(devTaskPoller);
      devTaskPoller = null;
    }
  }

  async function pollDevTaskRuns() {
    if (pollingDevRuns) return;
    pollingDevRuns = true;
    try {
      for (const run of devRuns.values()) {
        if (
          run.status !== 'running'
          && (run.outputOffset || 0) >= (run.output_line_count || 0)
        ) continue;
        const output = await request(
          `dev/runs/${encodeURIComponent(run.id)}?offset=${run.outputOffset || 0}`,
        );
        run.outputOffset = output.offset;
        run.output_line_count = output.offset;
        run.outputLines = [...(run.outputLines || []), ...output.lines].slice(-500);
        run.status = output.status;
        run.service_state = output.service_state;
        run.duration_seconds = output.duration_seconds;
        const task = devTaskDefinitions.get(run.task_id);
        if (task) {
          const cardElements = devTasks.get(task.id);
          if (cardElements) {
            try {
              cardElements.log.textContent = run.outputLines.join('\n');
            } catch {
              cardElements.error.textContent = 'This task output could not be displayed. Reload the console and try again.';
              cardElements.error.hidden = false;
            }
          }
          refreshDevTaskCard(task);
        }
      }
    } catch (error) {
      if (!handleUnauthorized(error)) {
        setMessage(consoleMessage, error.message || 'Could not refresh task output.');
      }
    } finally {
      pollingDevRuns = false;
      ensureDevTaskPolling();
    }
  }

  async function loadDevTasks() {
    let tasks;
    try {
      tasks = await request('dev/tasks');
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        devTasksNavButton.hidden = true;
        sections.devTasks.hidden = true;
        return;
      }
      throw error;
    }
    devTasksNavButton.hidden = false;
    devTaskCards.replaceChildren();
    devTasks.clear();
    devTaskDefinitions.clear();
    devRuns.clear();
    for (const task of tasks) {
      devTaskDefinitions.set(task.id, task);
      try {
        devTaskCards.append(makeDevTaskCard(task));
      } catch {
        devTaskCards.append(createDevTaskCardError(task));
      }
    }
    const result = await request('dev/runs?limit=50');
    for (const run of [...result.runs].reverse()) {
      run.outputLines = [];
      run.outputOffset = 0;
      devRuns.set(run.id, run);
    }
    for (const task of tasks) refreshDevTaskCard(task);
    ensureDevTaskPolling();
  }

  async function loadConsole(email) {
    showConsole(email);
    try {
      await Promise.all([loadCenters(), loadAudit(), loadDevTasks()]);
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

  inviteAdminForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    setMessage(inviteAdminMessage, '');
    if (!selectedCenterId) return;
    const formData = new FormData(inviteAdminForm);
    const submitButton = inviteAdminForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
      const result = await request(
        `centers/${encodeURIComponent(selectedCenterId)}/invitations`,
        {
          method: 'POST',
          body: JSON.stringify({ email: formData.get('email') }),
        },
      );
      invitationLink = result.link;
      invitationToken = result.token;
      inviteLink.value = invitationLink;
      inviteToken.value = invitationToken;
      setMessage(inviteResultMessage, '');
      result.token = '';
      inviteAdminForm.hidden = true;
      inviteResult.hidden = false;
    } catch (error) {
      if (!handleUnauthorized(error)) {
        setMessage(inviteAdminMessage, error.message || 'Could not create the invitation.');
      }
    } finally {
      submitButton.disabled = false;
    }
  });

  document.querySelectorAll('[data-close-invite]').forEach((button) => {
    button.addEventListener('click', () => inviteAdminDialog.close());
  });
  document.getElementById('closeInviteResult').addEventListener('click', () => {
    inviteAdminDialog.close();
  });
  inviteAdminDialog.addEventListener('close', clearInvitationDialog);

  document.getElementById('copyInviteLink').addEventListener('click', async () => {
    if (!invitationLink) return;
    try {
      await navigator.clipboard.writeText(invitationLink);
      setMessage(inviteResultMessage, 'Invitation link copied.');
      inviteResultMessage.classList.add('success');
    } catch {
      inviteResultMessage.classList.remove('success');
      setMessage(inviteResultMessage, 'Could not copy the invitation link.');
    }
  });
  document.getElementById('copyInviteToken').addEventListener('click', async () => {
    if (!invitationToken) return;
    try {
      await navigator.clipboard.writeText(invitationToken);
      setMessage(inviteResultMessage, 'One-time token copied.');
      inviteResultMessage.classList.add('success');
    } catch {
      inviteResultMessage.classList.remove('success');
      setMessage(inviteResultMessage, 'Could not copy the one-time token.');
    }
  });

  document.getElementById('closeCenterInvitations').addEventListener('click', () => {
    centerInvitationsDialog.close();
    invitationListCenterId = null;
    selectedCenterName = '';
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
      } else if (selected === 'devTasks') {
        await pollDevTaskRuns();
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
