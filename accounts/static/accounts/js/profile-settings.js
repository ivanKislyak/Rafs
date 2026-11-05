(() => {
  const root = document.querySelector('[data-profile-settings]');
  if (!root) return;
  const form = root.querySelector('[data-settings-form]');
  const fields = ['name', 'username', 'about', 'sex', 'bd_date'];
  const controls = Object.fromEntries(fields.map(name => [name, form.elements.namedItem(name)]));
  const status = root.querySelector('[data-settings-status]');
  const save = root.querySelector('[data-settings-save]');
  const hint = root.querySelector('[data-unsaved-hint]');
  const emailForm = root.querySelector('[data-email-form]');
  let original = Object.fromEntries(fields.map(name => [name, controls[name].value]));
  let busy = false;
  let avatar;
  const text = value => Array.isArray(value) ? value.join(' ') : String(value);
  function dirty() { return fields.some(name => controls[name].value !== original[name]) || avatar?.action !== 'keep'; }
  function updateDirty() { hint.hidden = !dirty(); save.disabled = busy || !dirty(); }
  function setBusy(value) {
    busy = value;
    root.querySelectorAll('fieldset').forEach(el => { el.disabled = value; });
    if (!value) avatar.refresh();
    updateDirty();
  }
  function clearErrors(container) {
    container.querySelectorAll('[data-field-error]').forEach(el => { el.textContent = ''; });
    container.querySelectorAll('[aria-invalid]').forEach(el => el.removeAttribute('aria-invalid'));
  }
  function showErrors(container, data) {
    let first;
    container.querySelectorAll('[data-field-error]').forEach(el => {
      const name = el.dataset.fieldError;
      if (!data[name]) return;
      el.textContent = text(data[name]);
      const control = container.elements.namedItem(name);
      control?.setAttribute('aria-invalid', 'true');
      if (control && control.type !== 'file') first ||= control;
    });
    return first;
  }
  avatar = window.RafsAvatarCrop(root, () => { status.textContent = ''; updateDirty(); });
  form.addEventListener('input', () => { status.textContent = ''; updateDirty(); });
  form.addEventListener('change', updateDirty);
  updateDirty();

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !dirty() || !form.reportValidity()) return;
    clearErrors(form);
    const body = new FormData();
    fields.filter(name => controls[name].value !== original[name]).forEach(name => body.append(name, controls[name].value));
    if (avatar.action !== 'keep') body.append('avatar_action', avatar.action);
    if (avatar.blob) body.append('avatar_image', avatar.blob, 'avatar.png');
    setBusy(true);
    form.setAttribute('aria-busy', 'true');
    status.textContent = root.dataset.saving;
    let invalid;
    try {
      const response = await fetch(form.action, {
        method: 'PATCH', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'X-CSRFToken': form.elements.namedItem('csrfmiddlewaretoken').value },
        body,
      });
      if ([401, 403].includes(response.status)) { status.textContent = root.dataset.accessError; return; }
      if (!response.ok && response.status !== 400) throw new Error('Settings request failed');
      const data = await response.json();
      if (!response.ok) {
        invalid = showErrors(form, data);
        status.textContent = data.non_field_errors ? text(data.non_field_errors) : root.dataset.error;
        return;
      }
      fields.forEach(name => { controls[name].value = data[name] ?? ''; });
      // Textareas normalise multipart CRLF to LF; compare the displayed values.
      original = Object.fromEntries(fields.map(name => [name, controls[name].value]));
      avatar.saved(data);
      document.querySelectorAll('[data-current-username]').forEach(el => { el.textContent = data.username; });
      document.querySelectorAll('[data-own-profile-link]').forEach(el => { el.href = data.profile_url; });
      document.querySelectorAll('.header-user-avatar').forEach(el => { el.src = data.avatar_url; });
      status.textContent = root.dataset.saved;
    } catch {
      status.textContent = root.dataset.error;
    } finally {
      setBusy(false);
      form.removeAttribute('aria-busy');
      if (invalid) invalid.focus();
      else save.focus({ preventScroll: true });
    }
  });

  emailForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !emailForm.reportValidity()) return;
    clearErrors(emailForm);
    const emailStatus = emailForm.querySelector('[data-email-status]');
    const payload = { email: emailForm.elements.email.value, current_password: emailForm.elements.current_password.value };
    setBusy(true);
    emailStatus.textContent = root.dataset.saving;
    let invalid;
    try {
      const response = await fetch(emailForm.action, {
        method: 'PATCH', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': emailForm.elements.csrfmiddlewaretoken.value },
        body: JSON.stringify(payload),
      });
      if ([401, 403].includes(response.status)) { emailStatus.textContent = root.dataset.accessError; return; }
      if (!response.ok && response.status !== 400) throw new Error('Email request failed');
      const data = await response.json();
      if (!response.ok) { invalid = showErrors(emailForm, data); emailStatus.textContent = root.dataset.error; return; }
      root.querySelector('[data-current-email]').textContent = data.email;
      emailForm.elements.email.value = data.email;
      emailForm.elements.current_password.value = '';
      emailStatus.textContent = emailForm.dataset.saved;
    } catch {
      emailStatus.textContent = root.dataset.error;
    } finally {
      setBusy(false);
      invalid?.focus();
    }
  });
})();
