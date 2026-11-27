(() => {
  const root = document.querySelector("[data-feedback]");
  if (!root) {
    return;
  }

  const form = root.querySelector("[data-feedback-form]");
  const thanks = root.querySelector("[data-feedback-thanks]");
  const thanksTitle = root.querySelector("[data-feedback-thanks-title]");
  const message = form.elements.message;
  const kind = form.elements.kind;
  const email = form.elements.email; // Guests only.
  const pageUrl = form.elements.page_url;
  const submitButton = form.querySelector("[data-feedback-submit]");
  const counter = form.querySelector("[data-feedback-count]");
  const formError = form.querySelector("[data-form-error]");
  const minLength = Number(root.dataset.minLength);
  const maxLength = Number(root.dataset.maxLength);
  const fields = { email, kind, message }; // Form order, so the first invalid field gets focus.
  let sending = false;

  // The server trims the message and counts code points, so emoji count as one here too.
  function messageLength() {
    return [...message.value.trim()].length;
  }

  function fieldError(name) {
    return form.querySelector(`[data-field-error="${name}"]`);
  }

  function setFieldError(name, text) {
    const errorEl = fieldError(name);
    if (!errorEl) {
      return false;
    }
    errorEl.textContent = text;
    errorEl.hidden = !text;
    fields[name]?.setAttribute("aria-invalid", text ? "true" : "false");
    return true;
  }

  function showFormError(text) {
    formError.textContent = text;
    formError.hidden = !text;
  }

  function clearErrors() {
    for (const name of Object.keys(fields)) {
      setFieldError(name, "");
    }
    showFormError("");
  }

  // Counter and button only: never touches an error the server returned.
  function refreshControls() {
    const length = messageLength();
    counter.textContent = length;
    counter.parentElement.classList.toggle("is-over", length > maxLength);
    submitButton.disabled = sending || length < minLength;
  }

  // While typing: over the limit say so at once and never cut the text; editing clears an old error.
  function onMessageInput() {
    refreshControls();
    setFieldError("message", messageLength() > maxLength ? root.dataset.msgTooLong : "");
  }

  // DRF answers {"field": ["text", ...]} or {"detail": "text"}; unknown keys go above the button.
  function showValidationErrors(data) {
    const general = [];
    for (const [key, value] of Object.entries(data || {})) {
      const text = Array.isArray(value) ? value.join(" ") : String(value);
      if (key === "non_field_errors" || key === "detail" || !setFieldError(key, text)) {
        general.push(text);
      }
    }
    showFormError(general.join(" "));
    const firstInvalid = Object.keys(fields).find((name) => fields[name]?.getAttribute("aria-invalid") === "true");
    fields[firstInvalid]?.focus();
  }

  async function send(event) {
    event.preventDefault();
    if (sending) {
      return;
    }
    clearErrors();
    const length = messageLength();
    if (length > maxLength) {
      onMessageInput();
      message.focus();
      return;
    }
    if (length < minLength) {
      return;
    }

    const body = { kind: kind.value, message: message.value, page_url: pageUrl.value };
    if (email) {
      body.email = email.value.trim();
    }

    sending = true;
    submitButton.disabled = true;
    form.setAttribute("aria-busy", "true");
    try {
      await apiRequest(root.dataset.apiUrl, { method: "POST", body });
      form.hidden = true;
      thanks.hidden = false;
      thanksTitle.focus();
    } catch (error) {
      if (error.status === 400) {
        showValidationErrors(error.data);
      } else if (error.status === 429) {
        showFormError(root.dataset.msgThrottled);
      } else {
        // Network failure or 5xx: the typed text stays in the form.
        showFormError(root.dataset.msgError);
      }
    } finally {
      sending = false;
      form.removeAttribute("aria-busy");
      refreshControls();
    }
  }

  function writeAgain() {
    message.value = "";
    clearErrors();
    refreshControls();
    thanks.hidden = true;
    form.hidden = false;
    message.focus();
  }

  message.addEventListener("input", onMessageInput);
  form.addEventListener("submit", send);
  for (const name of ["kind", "email"]) {
    fields[name]?.addEventListener("input", () => setFieldError(name, ""));
  }
  root.addEventListener("click", (event) => {
    if (event.target.closest('[data-action="write-again"]')) {
      writeAgain();
    }
  });

  refreshControls();
})();
