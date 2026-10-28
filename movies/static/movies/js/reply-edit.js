(() => {
  const sessions = new WeakMap();

  const close = (reply, form) => {
    if (sessions.get(form)?.pending) return;
    sessions.delete(form);
    form.reset();
    form.hidden = true;
    reply.querySelector('[data-reply-text]').hidden = false;
    const trigger = reply.querySelector('[data-reply-edit-open]');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.focus({ preventScroll: true });
  };

  document.addEventListener('click', event => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest('button');
    if (!button?.matches('[data-reply-edit-open], [data-reply-edit-cancel]')) return;
    const reply = button.closest('[data-review-reply]');
    const form = reply?.querySelector('[data-reply-edit-form]');
    if (!form || sessions.get(form)?.pending) return;
    if (button.matches('[data-reply-edit-cancel]')) {
      reply.querySelector('[data-reply-edit-status]').textContent = '';
      close(reply, form);
      return;
    }
    if (!form.hidden) return;
    const original = reply.querySelector('[data-reply-text]').textContent;
    sessions.set(form, { original, pending: false });
    const text = form.elements.namedItem('text');
    text.value = original;
    text.removeAttribute('aria-invalid');
    const feedback = form.querySelector('[data-reply-edit-error]');
    feedback.textContent = '';
    feedback.hidden = true;
    reply.querySelector('[data-reply-edit-status]').textContent = '';
    reply.querySelector('[data-reply-text]').hidden = true;
    form.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    text.focus();
  });

  // Capture also blocks a conflicting deletion submitted while this reply is saving.
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const reply = form.closest('[data-review-reply]');
    if (!reply) return;
    const editor = reply.querySelector('[data-reply-edit-form]');
    if (form !== editor) {
      if (editor && sessions.get(editor)?.pending) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      return;
    }
    event.preventDefault();
    const session = sessions.get(form);
    if (!session || session.pending) return;
    const text = form.elements.namedItem('text');
    if (text.value === session.original) {
      close(reply, form);
      return;
    }
    if (!form.reportValidity()) return;

    const feedback = form.querySelector('[data-reply-edit-error]');
    const status = reply.querySelector('[data-reply-edit-status]');
    feedback.textContent = '';
    feedback.hidden = true;
    text.removeAttribute('aria-invalid');
    session.pending = true;
    form.setAttribute('aria-busy', 'true');
    const controls = [...reply.querySelectorAll('button')].map(button => [button, button.disabled]);
    controls.forEach(([button]) => { button.disabled = true; });
    text.readOnly = true;
    status.textContent = form.dataset.saving;
    let succeeded = false;
    let receivedResponse = false;
    try {
      const endpoint = new URL(form.dataset.editUrl, location.href);
      if (endpoint.origin !== location.origin) throw new Error();
      const response = await fetch(endpoint.href, {
        method: 'PATCH', credentials: 'same-origin',
        headers: {
          Accept: 'application/json', 'Content-Type': 'application/json',
          'X-CSRFToken': form.elements.namedItem('csrfmiddlewaretoken').value,
        },
        body: JSON.stringify({ text: text.value }),
      });
      receivedResponse = true;
      if (response.status === 200 && !response.redirected) {
        const data = await response.json();
        if (typeof data.text !== 'string') throw new Error();
        reply.querySelector('[data-reply-text]').textContent = data.text;
        succeeded = true;
        status.textContent = form.dataset.saved;
      } else {
        let message = form.dataset.error;
        if ([401, 403].includes(response.status) || response.redirected) {
          message = form.dataset.authError;
        } else if (response.status === 404) {
          message = form.dataset.missingError;
        } else if (response.status === 400) {
          const errors = await response.json().catch(() => null);
          if (Array.isArray(errors?.text) && errors.text.every(item => typeof item === 'string')) {
            message = errors.text.join(' ') || message;
            text.setAttribute('aria-invalid', 'true');
          }
        }
        feedback.textContent = message;
        feedback.hidden = false;
      }
    } catch {
      feedback.textContent = receivedResponse ? form.dataset.error : form.dataset.networkError;
      feedback.hidden = false;
    } finally {
      session.pending = false;
      form.removeAttribute('aria-busy');
      controls.forEach(([button, disabled]) => { button.disabled = disabled; });
      text.readOnly = false;
      if (succeeded) close(reply, form);
      else {
        status.textContent = '';
        text.focus({ preventScroll: true });
      }
    }
  }, true);
})();
