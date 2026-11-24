(() => {
  const root = document.querySelector("[data-library]");
  if (!root) {
    return;
  }

  const list = root.querySelector("[data-library-list]");
  const countEl = root.querySelector("[data-library-count]");
  const emptyEl = root.querySelector("[data-library-empty]");
  const errorEl = root.querySelector("[data-library-error]");
  const titleEl = root.querySelector("#library-title");

  function visibleCards() {
    return [...list.querySelectorAll("[data-library-item]:not([hidden])")];
  }

  function updateCount() {
    const count = visibleCards().length;
    countEl.textContent = count;
    emptyEl.hidden = count > 0;
  }

  function showError(text) {
    errorEl.textContent = text;
    errorEl.hidden = false;
  }

  // Remove: the card disappears at once and comes back if DELETE fails.
  async function removeCard(button) {
    const card = button.closest("[data-library-item]");
    const cards = visibleCards();
    const index = cards.indexOf(card);
    // The button is about to vanish: keep keyboard focus on the next card, or the previous one, or the heading.
    const neighbour = cards[index + 1] ?? cards[index - 1];
    const focusTarget = neighbour?.querySelector(".library-card-link") ?? titleEl;
    const hadFocus = document.activeElement === button;

    button.disabled = true;
    card.hidden = true;
    errorEl.hidden = true;
    updateCount();
    if (hadFocus) {
      focusTarget.focus();
    }
    try {
      await apiRequest(button.dataset.saveUrl, { method: "DELETE" });
      card.remove();
    } catch (error) {
      card.hidden = false;
      updateCount();
      showError(root.dataset.msgRemoveError);
      if (hadFocus && document.activeElement === focusTarget) {
        button.disabled = false;
        button.focus();
      }
    } finally {
      button.disabled = false;
    }
  }

  list.addEventListener("click", (event) => {
    const button = event.target.closest('[data-action="unsave"]');
    if (!button) {
      return;
    }
    removeCard(button);
  });
})();
