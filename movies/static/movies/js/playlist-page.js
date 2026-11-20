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

  // Owner-only controls: they are missing for guests and for the Favourite playlist.
  const deleteButton = root.querySelector('[data-action="delete-playlist"]');
  const deleteDialog = root.querySelector("[data-delete-dialog]");
  const deleteErrorEl = deleteDialog?.querySelector("[data-delete-error]");
  const cancelDeleteButton = deleteDialog?.querySelector('[data-action="close-dialog"]');
  const confirmDeleteButton = deleteDialog?.querySelector('[data-action="confirm-delete"]');

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

  async function togglePublic() {
    const isPublic = publicToggle.checked;
    publicToggle.disabled = true;
    clearError();

    try {
      // PATCH sends only is_public, so it never overwrites the name.
      const response = await apiRequest(root.dataset.playlistUrl, {
        method: "PATCH",
        body: { is_public: isPublic },
      });

      publicToggle.checked = response.data.is_public;
    } catch (error) {
      publicToggle.checked = !isPublic;
      showError(root.dataset.msgToggleError);
    } finally {
      publicToggle.disabled = false;
    }
  }

  function openDeleteDialog() {
    deleteErrorEl.hidden = true;
    deleteDialog.showModal();
  }

  async function deletePlaylist() {
    confirmDeleteButton.disabled = true;
    deleteErrorEl.hidden = true;
    try {
      await apiRequest(root.dataset.playlistUrl, { method: "DELETE" });
      location.href = root.dataset.profileUrl;
    } catch (error) {
      deleteErrorEl.textContent = root.dataset.msgDeleteError;
      deleteErrorEl.hidden = false;
      confirmDeleteButton.disabled = false;
    }
  }

  list.addEventListener("click", (event) => {
    const buttonRemove = event.target.closest('[data-action="remove"]');
    if (!buttonRemove) {
      return;
    }
    removeItem(buttonRemove);
  });

  publicToggle?.addEventListener("change", togglePublic);

  deleteButton?.addEventListener("click", openDeleteDialog);
  cancelDeleteButton?.addEventListener("click", () => deleteDialog.close());
  confirmDeleteButton?.addEventListener("click", deletePlaylist);
  deleteDialog?.addEventListener("click", (event) => {
    if (event.target === deleteDialog) {
      deleteDialog.close();
    }
  });
})();
