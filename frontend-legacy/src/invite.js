(() => {
  history.replaceState(null, '', `${location.pathname}${location.search}`);

  const config = window.FLEET_CONFIG;
  const form = document.getElementById('inviteForm');
  const tokenInput = document.getElementById('tokenInput');
  const passwordInput = document.getElementById('passwordInput');
  const passwordConfirmInput = document.getElementById('passwordConfirmInput');
  const message = document.getElementById('inviteMessage');
  const acceptButton = document.getElementById('acceptButton');
  const successView = document.getElementById('successView');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    message.classList.remove('success');
    message.textContent = '';
    const password = passwordInput.value;
    if (password.length < 12 || password.length > 128) {
      message.textContent = 'Password must be between 12 and 128 characters.';
      return;
    }
    if (password !== passwordConfirmInput.value) {
      message.textContent = 'Passwords do not match.';
      return;
    }
    if (!config || typeof config.apiBaseUrl !== 'string') {
      message.textContent = 'The API base URL is not configured.';
      return;
    }

    let token = tokenInput.value;
    let requestBody = JSON.stringify({ token, password });
    tokenInput.value = '';
    passwordInput.value = '';
    passwordConfirmInput.value = '';
    acceptButton.disabled = true;
    try {
      const responsePromise = fetch(
        `${config.apiBaseUrl.replace(/\/$/, '')}/invitations/accept`,
        {
          method: 'POST',
          credentials: 'omit',
          headers: { 'Content-Type': 'application/json' },
          body: requestBody,
        },
      );
      token = '';
      requestBody = '';
      const response = await responsePromise;
      if (response.status === 201) {
        form.hidden = true;
        successView.hidden = false;
        return;
      }
      message.textContent = response.status === 400
        ? 'Invalid or expired invitation'
        : 'Could not accept the invitation. Check the token and try again.';
    } catch {
      message.textContent = 'Could not connect to the invitation service. Try again.';
    } finally {
      acceptButton.disabled = false;
      token = '';
      requestBody = '';
    }
  });
})();
