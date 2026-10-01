(() => {
  const library = document.querySelector("[data-profile-library]");

  if (!library) {
    return;
  }

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const removalTimers = new WeakMap();

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

  const closeDialog = () => {
    if (typeof dialog.close === "function" && dialog.open) {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
    }
  };

  const setCount = (card, difference) => {
    const panel = card.closest("[data-profile-watch-panel]");
    const toggle = document.querySelector(
      `[aria-controls="${panel.id}"][data-profile-watch-toggle]`
    );
    const count = toggle?.querySelector("[data-profile-watch-count]");

    if (count) {
      const nextCount = Math.max(0, Number(count.dataset.count) + difference);
      count.dataset.count = String(nextCount);
      count.textContent = String(nextCount);
    }
  };

  const updateEmptyState = (panel) => {
    const emptyState = panel.querySelector("[data-profile-watch-empty]");
    const hasMovies = Boolean(panel.querySelector("[data-library-movie]"));

    if (emptyState) {
      emptyState.hidden = hasMovies;
    }
  };

  const updateStatus = async (card) => {
    const response = await fetch(library.dataset.updateUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfInput.value,
      },
      body: JSON.stringify({
        movie_id: card.dataset.movieId,
        status: card.dataset.status,
      }),
    });
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(library.dataset.updateError);
    }

    return data;
  };

  const removeCardAfterUndoWindow = (card) => {
    const previousTimer = removalTimers.get(card);
    if (previousTimer) {
      window.clearTimeout(previousTimer);
    }

    const undoTimer = window.setTimeout(() => {
      card.classList.add("is-leaving");
      const animationDelay = reducedMotion.matches ? 0 : 220;
      const removeTimer = window.setTimeout(() => {
        const panel = card.closest("[data-profile-watch-panel]");
        card.remove();
        updateEmptyState(panel);
      }, animationDelay);

      removalTimers.set(card, removeTimer);
    }, 8000);

    removalTimers.set(card, undoTimer);
  };

  const showError = (card) => {
    const feedback = card.querySelector("[data-library-feedback]");
    if (feedback) {
      feedback.textContent = library.dataset.updateError;
    }
  };

  document.querySelectorAll("[data-library-remove]").forEach((trigger) => {
    trigger.addEventListener("click", () => {
      pendingCard = trigger.closest("[data-library-movie]");
      pendingTrigger = trigger;
      dialogName.textContent = pendingCard.dataset.movieName;

      if (typeof dialog.showModal === "function") {
        dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }

      cancelButton.focus();
    });
  });

  cancelButton.addEventListener("click", closeDialog);

  confirmButton.addEventListener("click", async () => {
    if (!pendingCard || !pendingTrigger) {
      return;
    }

    const card = pendingCard;
    const trigger = pendingTrigger;
    const feedback = card.querySelector("[data-library-feedback]");
    const removedMessage = card.querySelector("[data-library-removed]");
    const undoButton = card.querySelector("[data-library-undo]");

    confirmButton.disabled = true;
    trigger.disabled = true;
    feedback.textContent = "";

    try {
      const data = await updateStatus(card);
      if (data.status !== null) {
        throw new Error(library.dataset.updateError);
      }

      setCount(card, -1);
      card.classList.add("is-removed");
      trigger.hidden = true;
      removedMessage.hidden = false;
      undoButton.hidden = false;
      removeCardAfterUndoWindow(card);
    } catch (error) {
      trigger.disabled = false;
      showError(card);
    } finally {
      confirmButton.disabled = false;
      closeDialog();
    }
  });

  document.querySelectorAll("[data-library-undo]").forEach((undoButton) => {
    undoButton.addEventListener("click", async () => {
      const card = undoButton.closest("[data-library-movie]");
      const removeButton = card.querySelector("[data-library-remove]");
      const removedMessage = card.querySelector("[data-library-removed]");
      const feedback = card.querySelector("[data-library-feedback]");
      const timer = removalTimers.get(card);

      window.clearTimeout(timer);
      undoButton.disabled = true;
      feedback.textContent = "";

      try {
        const data = await updateStatus(card);
        if (data.status !== card.dataset.status) {
          throw new Error(library.dataset.updateError);
        }

        card.classList.remove("is-removed", "is-leaving");
        removedMessage.hidden = true;
        undoButton.hidden = true;
        removeButton.hidden = false;
        removeButton.disabled = false;
        setCount(card, 1);
      } catch (error) {
        undoButton.disabled = false;
        showError(card);
        removeCardAfterUndoWindow(card);
      }
    });
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      closeDialog();
    }
  });
  dialog.addEventListener("close", () => {
    confirmButton.disabled = false;
    pendingTrigger?.focus();
    pendingCard = null;
    pendingTrigger = null;
  });
})();
