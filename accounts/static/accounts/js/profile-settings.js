(() => {
  const root = document.querySelector('[data-profile-settings]');
  if (!root) return;

  const forms = [...root.querySelectorAll('[data-settings-api-form]')];
  const avatar = root.querySelector('[data-settings-avatar]');
  let busy = false;
  const setBusy = (value) => {
    busy = value;
    // Serialise the separate saves: two full user.save() calls must not race.
    root.querySelectorAll('fieldset').forEach(fieldset => { fieldset.disabled = value; });
  };
  const errorText = value => Array.isArray(value) ? value.join(' ') : String(value);

  forms.forEach(form => {
    const fields = form.dataset.fields.split(',');
    const controls = Object.fromEntries(fields.map(name => [name, form.elements.namedItem(name)]));
    const errors = Object.fromEntries(fields.map(name => [name, form.querySelector(`[data-field-error="${name}"]`)]));
    const status = form.querySelector('[data-settings-status]');
    let original = Object.fromEntries(fields.map(name => [name, controls[name].value]));

    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy || !form.reportValidity()) return;
      fields.forEach(name => {
        errors[name].textContent = '';
        controls[name].removeAttribute('aria-invalid');
      });
      const changes = Object.fromEntries(fields.filter(name => controls[name].value !== original[name])
        .map(name => [name, controls[name].value]));
      if (!Object.keys(changes).length) {
        status.textContent = root.dataset.unchanged;
        return;
      }
      setBusy(true);
      const submitter = event.submitter;
      form.setAttribute('aria-busy', 'true');
      status.textContent = root.dataset.saving;
      let invalid = null;
      try {
        const response = await fetch(form.action, {
          method: 'PATCH', credentials: 'same-origin',
          headers: {
            Accept: 'application/json', 'Content-Type': 'application/json',
            'X-CSRFToken': form.elements.namedItem('csrfmiddlewaretoken').value,
          },
          body: JSON.stringify(changes),
        });
        if ([401, 403].includes(response.status)) {
          status.textContent = root.dataset.accessError;
          return;
        }
        if (!response.ok && response.status !== 400) throw new Error('Settings request failed');
        const data = await response.json();
        if (!response.ok) {
          status.textContent = data.non_field_errors ? errorText(data.non_field_errors) : root.dataset.error;
          fields.forEach(name => {
            if (!data[name]) return;
            errors[name].textContent = errorText(data[name]);
            controls[name].setAttribute('aria-invalid', 'true');
            invalid ||= controls[name];
          });
          return;
        }
        original = Object.fromEntries(fields.map(name => [name, data[name] ?? '']));
        fields.forEach(name => { controls[name].value = original[name]; });
        if (fields.includes('username')) {
          document.querySelectorAll('[data-current-username]').forEach(el => { el.textContent = data.username; });
          document.querySelectorAll('[data-own-profile-link]').forEach(link => { link.href = data.profile_url; });
          status.textContent = root.dataset.usernameSaved;
        } else {
          status.textContent = root.dataset.saved;
        }
        // This is display text, never HTML; unsaved fields in the other form stay intact.
        const nameForm = forms.find(item => item.elements.namedItem('name'));
        const currentName = fields.includes('name') ? data.name : nameForm.elements.namedItem('name').defaultValue;
        root.querySelector('[data-settings-display-name]').textContent = currentName
          || root.querySelector('[data-current-username]').textContent;
        if (fields.includes('name')) nameForm.elements.namedItem('name').defaultValue = data.name;
      } catch {
        status.textContent = root.dataset.error;
      } finally {
        setBusy(false);
        form.removeAttribute('aria-busy');
        if (invalid) invalid.focus();
        else submitter?.focus({ preventScroll: true });
      }
    });
  });

  if (!avatar) return;
  const file = avatar.querySelector('input[type="file"]');
  const filename = avatar.querySelector('[data-settings-filename]');
  avatar.querySelector('[data-settings-choose-file]').addEventListener('click', () => file.click());
  file.addEventListener('change', () => {
    filename.textContent = file.files[0]?.name || filename.dataset.empty;
  });
  avatar.addEventListener('submit', event => {
    if (busy) {
      event.preventDefault();
      return;
    }
    busy = true;
    avatar.setAttribute('aria-busy', 'true');
    // Keep the submitter enabled so its avatar_action enters the native POST.
    root.querySelectorAll('button').forEach(button => { button.setAttribute('aria-disabled', 'true'); });
  });
})();
