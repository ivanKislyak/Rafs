(() => {
  const library = document.querySelector("[data-profile-library]");

  if (!library) {
    return;
  }

  const formatCount = (count) => {
    const size = Number(library.dataset.numberGrouping);
    const value = String(count);
    if (!Number.isInteger(size) || size <= 0) return value;
    const groups = [];
    for (let end = value.length; end > 0; end -= size) {
      groups.unshift(value.slice(Math.max(0, end - size), end));
    }
    return groups.join(library.dataset.thousandSeparator || "");
  };
  const libraryStatus = library.querySelector("[data-library-status]");
  const announce = (message) => {
    if (libraryStatus) libraryStatus.textContent = message;
  };

  const controlledPanel = (control) => (
    document.getElementById(control.getAttribute("aria-controls"))
  );

  document.querySelectorAll("[data-profile-watch-toggle]").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const panel = controlledPanel(toggle);
      const willOpen = toggle.getAttribute("aria-expanded") !== "true";

      document.querySelectorAll("[data-profile-watch-toggle]").forEach((otherToggle) => {
        const otherPanel = controlledPanel(otherToggle);
        const isCurrent = otherToggle === toggle;

        otherToggle.setAttribute("aria-expanded", String(isCurrent && willOpen));
        otherToggle.classList.toggle("is-active", isCurrent && willOpen);
        if (otherPanel) {
          otherPanel.hidden = !(isCurrent && willOpen);
        }
      });

    });
  });

  const dialog = document.querySelector("[data-profile-watch-dialog]");
  const csrfInput = library.querySelector(
    "[data-profile-library-csrf] [name=csrfmiddlewaretoken]"
  );

  if (!dialog || !csrfInput) {
    return;
  }

  const dialogName = dialog.querySelector("[data-profile-watch-dialog-name]");
  const cancelButton = dialog.querySelector("[data-profile-watch-cancel]");
  const confirmButton = dialog.querySelector("[data-profile-watch-confirm]");
  let pendingCard = null;
  let pendingTrigger = null;
  let returnFocus = null;

  const focusControl = (control) => {
    if (!control?.isConnected) return;
    const panel = control.closest("[data-profile-watch-panel]");
    const target = panel?.hidden
      ? library.querySelector(`[data-profile-watch-toggle][aria-controls="${panel.id}"]`)
      : control;
    target?.focus({ preventScroll: true });
  };

  const finishDialog = () => {
    const target = returnFocus || pendingTrigger;
    pendingCard = null;
    pendingTrigger = null;
    returnFocus = null;
    confirmButton.disabled = false;
    cancelButton.disabled = false;
    focusControl(target);
  };

  const closeDialog = (focusTarget = pendingTrigger) => {
    if (pendingCard?.dataset.pending === "true") return;
    returnFocus = focusTarget;
    if (typeof dialog.close === "function" && dialog.open) {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
      finishDialog();
    }
  };

  const setCount = (card, difference) => {
    const panel = card.closest("[data-profile-watch-panel]");
    if (!panel) return;
    const toggle = document.querySelector(
      `[aria-controls="${panel.id}"][data-profile-watch-toggle]`
    );
    const count = toggle?.querySelector("[data-profile-watch-count]");

    if (count) {
      const nextCount = Math.max(0, Number(count.dataset.count) + difference);
      count.dataset.count = String(nextCount);
      count.textContent = formatCount(nextCount);
    }
  };

  const updateStatus = async (card, method) => {
    const response = await fetch(card.dataset.updateUrl, {
      method,
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfInput.value,
        Accept: "application/json",
      },
      body: method === "PUT" ? JSON.stringify({
        status: card.dataset.status,
      }) : undefined,
    });

    if (!response.ok) {
      throw new Error(library.dataset.updateError);
    }

    if (method === "DELETE") {
      if (response.status !== 204) {
        throw new Error(library.dataset.updateError);
      }
      return null;
    }

    return response.json();
  };

  const showError = (card) => {
    const feedback = card.querySelector("[data-library-feedback]");
    if (feedback) {
      feedback.textContent = library.dataset.updateError;
    }
  };

  // Delegation also covers cards inserted into a status panel after page load.
  library.addEventListener("click", async (event) => {
    if (!(event.target instanceof Element)) return;
    const trigger = event.target.closest("[data-library-remove]");
    if (trigger) {
      const card = trigger.closest("[data-library-movie]");
      if (!card || trigger.disabled || card.dataset.pending === "true"
          || card.classList.contains("is-removed") || dialog.hasAttribute("open")) return;
      event.preventDefault();
      pendingCard = card;
      pendingTrigger = trigger;
      returnFocus = null;
      dialogName.textContent = pendingCard.dataset.movieName;

      if (typeof dialog.showModal === "function") {
        dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }

      cancelButton.focus();
      return;
    }

    const undoButton = event.target.closest("[data-library-undo]");
    if (!undoButton) return;
    const card = undoButton.closest("[data-library-movie]");
    if (!card || undoButton.disabled || card.dataset.pending === "true"
        || !card.classList.contains("is-removed")) return;
    event.preventDefault();
    const removeButton = card.querySelector("[data-library-remove]");
    const removedMessage = card.querySelector("[data-library-removed]");
    const feedback = card.querySelector("[data-library-feedback]");
    card.dataset.pending = "true";
    card.setAttribute("aria-busy", "true");
    undoButton.disabled = true;
    feedback.textContent = "";
    announce(library.dataset.updateLoading);

    try {
      const data = await updateStatus(card, "PUT");
      if (data.status !== card.dataset.status) {
        throw new Error(library.dataset.updateError);
      }

      card.classList.remove("is-removed");
      removedMessage.hidden = true;
      undoButton.hidden = true;
      removeButton.hidden = false;
      removeButton.disabled = false;
      setCount(card, 1);
      announce(library.dataset.updateRestored);
    } catch (error) {
      announce("");
      showError(card);
    } finally {
      delete card.dataset.pending;
      card.setAttribute("aria-busy", "false");
      undoButton.disabled = false;
      if (document.activeElement === document.body || document.activeElement === undoButton) {
        focusControl(card.classList.contains("is-removed") ? undoButton : removeButton);
      }
    }
  });

  cancelButton.addEventListener("click", () => closeDialog());

  confirmButton.addEventListener("click", async () => {
    if (!pendingCard || !pendingTrigger || pendingCard.dataset.pending === "true") {
      return;
    }

    const card = pendingCard;
    const trigger = pendingTrigger;
    const feedback = card.querySelector("[data-library-feedback]");
    const removedMessage = card.querySelector("[data-library-removed]");
    const undoButton = card.querySelector("[data-library-undo]");

    card.dataset.pending = "true";
    card.setAttribute("aria-busy", "true");
    confirmButton.disabled = true;
    cancelButton.disabled = true;
    trigger.disabled = true;
    feedback.textContent = "";
    announce(library.dataset.updateLoading);

    try {
      await updateStatus(card, "DELETE");

      setCount(card, -1);
      card.classList.add("is-removed");
      trigger.hidden = true;
      removedMessage.hidden = false;
      undoButton.hidden = false;
    } catch (error) {
      showError(card);
    } finally {
      announce("");
      delete card.dataset.pending;
      card.setAttribute("aria-busy", "false");
      confirmButton.disabled = false;
      cancelButton.disabled = false;
      trigger.disabled = false;
      closeDialog(card.classList.contains("is-removed") ? undoButton : trigger);
    }
  });

  dialog.addEventListener("cancel", (event) => {
    if (pendingCard?.dataset.pending === "true") event.preventDefault();
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      closeDialog();
    }
  });
  dialog.addEventListener("close", () => {
    if (!dialog.open) finishDialog();
  });
})();
