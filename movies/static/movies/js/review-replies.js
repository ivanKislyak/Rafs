(() => {
  const pending = new WeakSet();

  // One listener also handles forms cloned or loaded after page initialization.
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches('[data-review-reply-form]')) return;
    event.preventDefault();
    if (pending.has(form)) return;

    const text = form.elements.namedItem('text');
    const csrf = form.elements.namedItem('csrfmiddlewaretoken');
    const feedback = form.querySelector('[data-reply-feedback]');
    const showError = message => {
      feedback.textContent = message;
      feedback.hidden = false;
    };
    feedback.textContent = '';
    feedback.hidden = true;

    if (!text.value.trim()) {
      showError(form.dataset.emptyError);
      text.focus();
      return;
    }

    const controls = [...form.querySelectorAll('button')];
    pending.add(form);
    form.setAttribute('aria-busy', 'true');
    controls.forEach(button => { button.disabled = true; });
    text.readOnly = true;
    let created = false;
    let receivedResponse = false;

    try {
      const endpoint = new URL(form.action, location.href);
      const destination = new URL(form.dataset.successUrl, location.href);
      if (endpoint.origin !== location.origin || destination.origin !== location.origin) {
        throw new Error();
      }

      const response = await fetch(endpoint.href, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': csrf.value,
        },
        body: JSON.stringify({ text: text.value }),
      });
      receivedResponse = true;

      if (response.status !== 201 || response.redirected) {
        let message = form.dataset.error;
        if ([401, 403].includes(response.status) || response.redirected) {
          message = form.dataset.authError;
        } else if (response.status === 404) {
          message = form.dataset.missingError;
        } else if (response.status === 400) {
          const errors = await response.json().catch(() => null);
          const messages = errors?.text || errors?.non_field_errors;
          if (Array.isArray(messages) && messages.every(value => typeof value === 'string')) {
            message = messages.join(' ') || message;
          }
        }
        showError(message);
        return;
      }

      created = true;
      // Navigating only to a different fragment does not reload server-rendered replies.
      if (destination.pathname === location.pathname && destination.search === location.search) {
        history.replaceState(null, '', destination.href);
        location.reload();
      } else {
        location.assign(destination.href);
      }
    } catch {
      showError(receivedResponse ? form.dataset.error : form.dataset.networkError);
    } finally {
      if (!created) {
        pending.delete(form);
        form.removeAttribute('aria-busy');
        controls.forEach(button => { button.disabled = false; });
        text.readOnly = false;
      }
    }
  });
})();
