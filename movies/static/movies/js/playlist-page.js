(() => {
  const root = document.querySelector("[data-playlist]");
  if (!root) {
    return;
  }

  const list = root.querySelector("[data-playlist-items]");
  const countEl = root.querySelector("[data-playlist-count]");
  const emptyEl = root.querySelector("[data-playlist-empty]");
  const errorEl = root.querySelector("[data-playlist-error]");
  const nameEl = root.querySelector("[data-playlist-name]");
  const publicToggle = root.querySelector("[data-playlist-public]");

  function showError(text) {
    errorEl.textContent = text;
    errorEl.hidden = false;
  }

  function clearError() {
    errorEl.hidden = true;
  }

  function updateCount() {
    const qtyInsideElements = list.querySelectorAll("[data-item]").length;
    emptyEl.hidden = qtyInsideElements > 0;
    countEl.textContent = qtyInsideElements;
  }

  async function removeItem(button) {
    const playlistItem = button.closest("[data-item]");
    if (!playlistItem) {
      return;
    }
    const url = playlistItem.dataset.itemUrl;
    button.disabled = true;
    try {
      await apiRequest(url, { method: "DELETE" });
      playlistItem.remove();
      updateCount();
    } catch (error) {
      showError(root.dataset.msgRemoveError);
    } finally {
      button.disabled = false;
    }
  }

  list.addEventListener("click", (event) => {
    const buttonRemove = event.target.closest('[data-action="remove"]');
    if (!buttonRemove) {
      return;
    }
    removeItem(buttonRemove);
  });

  publicToggle?.addEventListener("change", async () => {
    const isPublic = publicToggle.checked;
    publicToggle.disabled = true;
    clearError();

    try {
      const url = root.dataset.playlistUrl;
      const response = await apiRequest(url, {
        method: "PUT",
        body: { is_public: isPublic, name: nameEl.textContent.trim() },
      });

      publicToggle.checked = response.data.is_public;
    } catch (error) {
      publicToggle.checked = !isPublic;
      showError(root.dataset.msgToggleError);
    } finally {
      publicToggle.disabled = false;
    }
  });
})();
