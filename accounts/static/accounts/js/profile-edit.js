(() => {
  const dialog = document.querySelector('[data-profile-editor]');
  const trigger = document.querySelector('[data-profile-edit-open]');
  if (!dialog || !trigger) return;

  const form = dialog.querySelector('[data-profile-edit-form]');
  const fieldset = dialog.querySelector('[data-profile-edit-fields]');
  const save = dialog.querySelector('[data-profile-edit-save]');
  const cancel = dialog.querySelector('[data-profile-edit-cancel]');
  const retry = dialog.querySelector('[data-profile-edit-retry]');
  const status = dialog.querySelector('[data-profile-edit-status]');
  const result = document.querySelector('[data-profile-edit-result]');
  const about = document.querySelector('[data-profile-about]');
  const fields = ['about', 'sex', 'bd_date'];
  const controls = Object.fromEntries(fields.map((name) => [name, form.elements.namedItem(name)]));
  const errors = Object.fromEntries(fields.map((name) => [name,
    dialog.querySelector(`[data-profile-edit-error="${name}"]`),
  ]));
  let original = null;
  let loading = false;
  let saving = false;
  let loadVersion = 0;
  let controller = null;

  const clearErrors = () => {
    fields.forEach((name) => {
      errors[name].textContent = '';
      controls[name].removeAttribute('aria-invalid');
    });
    status.textContent = '';
  };

  const setBusy = () => {
    dialog.setAttribute('aria-busy', String(loading || saving));
    fieldset.disabled = loading || saving || !original;
    save.disabled = fieldset.disabled;
    cancel.disabled = saving;
    trigger.disabled = saving;
    retry.disabled = loading || saving;
  };

  const close = () => {
    if (saving) return;
    // A dismissed GET must never fill a later editing session.
    loadVersion += 1;
    controller?.abort();
    loading = false;
    original = null;
    form.reset();
    clearErrors();
    setBusy();
    dialog.close();
    trigger.focus({ preventScroll: true });
  };

  const fill = (data) => {
    original = { about: data.about, sex: data.sex, bd_date: data.bd_date };
    fields.forEach((name) => { controls[name].value = original[name] ?? ''; });
  };

  const load = async () => {
    if (loading || saving) return;
    const version = ++loadVersion;
    controller = new AbortController();
    loading = true;
    original = null;
    clearErrors();
    status.textContent = dialog.dataset.loading;
    retry.hidden = true;
    setBusy();
    try {
      const response = await fetch(dialog.dataset.apiUrl, {
        credentials: 'same-origin', headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      if (version !== loadVersion) return;
      if (!response.ok) {
        status.textContent = [401, 403].includes(response.status)
          ? dialog.dataset.accessError : dialog.dataset.loadError;
        retry.hidden = false;
        return;
      }
      const data = await response.json();
      if (version !== loadVersion) return;
      fill(data);
      status.textContent = '';
    } catch (error) {
      if (version !== loadVersion) return;
      status.textContent = dialog.dataset.loadError;
      retry.hidden = false;
    } finally {
      if (version === loadVersion) {
        loading = false;
        setBusy();
        if (original) controls.about.focus();
        else retry.focus();
      }
    }
  };

  trigger.addEventListener('click', () => {
    if (saving || dialog.open) return;
    result.textContent = '';
    dialog.showModal();
    cancel.focus();
    load();
  });
  retry.addEventListener('click', load);
  cancel.addEventListener('click', close);
  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    close();
  });
  dialog.addEventListener('click', (event) => {
    // Only the backdrop, not padding or controls inside the dialog, dismisses it.
    const box = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right
        || event.clientY < box.top || event.clientY > box.bottom)) close();
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (loading || saving || !original || !form.reportValidity()) return;
    const values = {
      about: controls.about.value,
      sex: controls.sex.value,
      // Keep the date-only ISO string: JS Date would introduce timezone conversion.
      bd_date: controls.bd_date.value || null,
    };
    const changes = Object.fromEntries(fields
      .filter((name) => values[name] !== original[name])
      .map((name) => [name, values[name]]));
    if (!Object.keys(changes).length) {
      close();
      return;
    }
    saving = true;
    clearErrors();
    status.textContent = dialog.dataset.saving;
    setBusy();
    let succeeded = false;
    let invalidField = null;
    try {
      const response = await fetch(dialog.dataset.apiUrl, {
        method: 'PATCH', credentials: 'same-origin',
        headers: {
          Accept: 'application/json', 'Content-Type': 'application/json',
          'X-CSRFToken': form.elements.namedItem('csrfmiddlewaretoken').value,
        },
        body: JSON.stringify(changes),
      });
      if ([401, 403].includes(response.status)) {
        status.textContent = dialog.dataset.accessError;
        return;
      }
      if (!response.ok && response.status !== 400) throw new Error('Profile request failed');
      const data = await response.json();
      if (response.ok) {
        fill(data);
        about.textContent = data.about;
        about.hidden = !data.about;
        result.textContent = dialog.dataset.saved;
        succeeded = true;
      } else {
        status.textContent = dialog.dataset.saveError;
        fields.forEach((name) => {
          const message = data[name];
          if (!message) return;
          errors[name].textContent = Array.isArray(message) ? message.join(' ') : String(message);
          controls[name].setAttribute('aria-invalid', 'true');
          invalidField ||= controls[name];
        });
      }
    } catch (error) {
      status.textContent = dialog.dataset.saveError;
    } finally {
      saving = false;
      setBusy();
      if (succeeded) close();
      else invalidField?.focus();
    }
  });
})();
