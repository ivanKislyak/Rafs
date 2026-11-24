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

  // Owner-only controls: they are missing for guests. Liked Titles (the Favourite playlist) keeps the
  // cover control but has no rename, delete or privacy toggle: it is always private.
  const renameButton = root.querySelector('[data-action="rename"]');
  const renameInput = root.querySelector("[data-rename-input]");
  const coverButton = root.querySelector('[data-action="change-cover"]');
  const coverInput = root.querySelector("[data-cover-input]");
  const coverReset = root.querySelector('[data-action="reset-cover"]');
  const deleteButton = root.querySelector('[data-action="delete-playlist"]');
  const deleteDialog = root.querySelector("[data-delete-dialog]");
  const deleteDialogName = deleteDialog?.querySelector("[data-delete-dialog-name]");
  const deleteErrorEl = deleteDialog?.querySelector("[data-delete-error]");
  const cancelDeleteButton = deleteDialog?.querySelector('[data-action="close-dialog"]');
  const confirmDeleteButton = deleteDialog?.querySelector('[data-action="confirm-delete"]');
  // Someone else's public playlist, signed-in visitor only (guests get a sign-in link instead).
  const saveButton = root.querySelector('[data-action="toggle-save"]');

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

  // Rename: the title is swapped for an input. Enter or leaving the input saves, Esc cancels.
  function startRename() {
    clearError();
    renameInput.value = nameEl.textContent.trim();
    nameEl.hidden = true;
    renameButton.hidden = true;
    renameInput.hidden = false;
    renameInput.focus();
    renameInput.select();
  }

  function finishRename() {
    renameInput.hidden = true;
    renameInput.disabled = false;
    nameEl.hidden = false;
    renameButton.hidden = false;
  }

  function cancelRename() {
    finishRename();
    renameButton.focus();
  }

  async function saveRename() {
    // Already closed (Esc) or the request is running (Enter and then blur).
    if (renameInput.hidden || renameInput.disabled) {
      return;
    }
    const newName = renameInput.value.trim();
    if (!newName) {
      finishRename();
      showError(root.dataset.msgEmptyName);
      return;
    }
    if (newName === nameEl.textContent.trim()) {
      finishRename();
      return;
    }

    renameInput.disabled = true;
    clearError();
    try {
      const response = await apiRequest(root.dataset.playlistUrl, {
        method: "PATCH",
        body: { name: newName },
      });
      nameEl.textContent = response.data.name;
      deleteDialogName.textContent = response.data.name;
      finishRename();
    } catch (error) {
      renameInput.disabled = false;
      renameInput.focus();
      showError(error.data?.name?.[0] ?? error.data?.detail ?? root.dataset.msgRenameError);
    }
  }

  // Cover: the <img> lives inside the cover button and exists only when the playlist already had a cover,
  // so create it on the first upload (before the overlay, which must stay on top).
  function showCover(url) {
    let coverImg = coverButton.querySelector("[data-playlist-cover]");
    if (!coverImg) {
      coverImg = document.createElement("img");
      coverImg.className = "playlist-cover";
      coverImg.dataset.playlistCover = "";
      coverImg.width = 160;
      coverImg.height = 160;
      coverImg.alt = "";
      coverButton.querySelector(".playlist-cover-overlay").before(coverImg);
      coverButton.setAttribute("aria-label", coverButton.dataset.labelChange);
    }
    coverImg.src = url;
  }

  async function uploadCover() {
    const file = coverInput.files[0];
    if (!file) {
      return;
    }
    const formData = new FormData();
    formData.append("cover", file);

    coverButton.disabled = true;
    clearError();
    try {
      const response = await apiRequest(root.dataset.playlistUrl, {
        method: "PATCH",
        body: formData,
      });
      showCover(response.data.cover);
      coverReset.hidden = false;
    } catch (error) {
      showError(error.data?.cover?.[0] ?? error.data?.detail ?? root.dataset.msgCoverError);
    } finally {
      coverButton.disabled = false;
      // Reset the input so choosing the same file again still fires "change".
      coverInput.value = "";
    }
  }

  // Trash on an uploaded cover: Liked Titles goes back to its default image (data-default-cover),
  // other playlists back to the "Add cover" placeholder.
  async function resetCover() {
    coverReset.disabled = true;
    coverButton.disabled = true;
    clearError();
    try {
      await apiRequest(root.dataset.playlistUrl, { method: "PATCH", body: { cover: null } });
      const defaultCover = coverButton.dataset.defaultCover;
      if (defaultCover) {
        showCover(defaultCover);
      } else {
        coverButton.querySelector("[data-playlist-cover]")?.remove();
        coverButton.setAttribute("aria-label", coverButton.dataset.labelAdd);
      }
      coverReset.hidden = true;
      // The trash disappears, so keep keyboard focus on the cover itself.
      coverButton.focus();
    } catch (error) {
      showError(error.data?.cover?.[0] ?? error.data?.detail ?? root.dataset.msgCoverError);
    } finally {
      coverReset.disabled = false;
      coverButton.disabled = false;
    }
  }

  // Save / unsave: flip aria-pressed at once (CSS swaps the label), PUT or DELETE, and flip back on failure.
  // PUT answers 201 (saved now) or 200 (already saved): both are success.
  async function toggleSave() {
    const wasSaved = saveButton.getAttribute("aria-pressed") === "true";
    const hadFocus = document.activeElement === saveButton;
    saveButton.setAttribute("aria-pressed", String(!wasSaved));
    saveButton.disabled = true;
    clearError();
    try {
      await apiRequest(saveButton.dataset.saveUrl, { method: wasSaved ? "DELETE" : "PUT" });
    } catch (error) {
      saveButton.setAttribute("aria-pressed", String(wasSaved));
      showError(wasSaved ? root.dataset.msgUnsaveError : root.dataset.msgSaveError);
    } finally {
      saveButton.disabled = false;
      // A disabled button drops the focus; give it back so Enter/Space can toggle again.
      if (hadFocus) {
        saveButton.focus();
      }
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

  // Reorder (owner only: Sortable.min.js is loaded just for the owner). The numbers 1, 2, 3 are a CSS
  // counter, so they follow the DOM by themselves.
  let sortable = null;
  let isSavingOrder = false;
  let orderBefore = [];

  // Send the order the DOM shows now; on failure put the cards back as they were in orderBefore.
  async function saveOrder(previousOrder) {
    isSavingOrder = true;
    sortable.option("disabled", true);
    list.setAttribute("aria-busy", "true");
    clearError();
    try {
      await apiRequest(root.dataset.orderUrl, {
        method: "PUT",
        body: { movie_ids: sortable.toArray().map(Number) },
      });
    } catch (error) {
      sortable.sort(previousOrder, true);
      showError(root.dataset.msgOrderError);
    } finally {
      sortable.option("disabled", false);
      list.removeAttribute("aria-busy");
      isSavingOrder = false;
    }
  }

  // Keyboard: ArrowUp / ArrowDown on a focused handle moves its card by one place.
  async function moveItemByKey(handle, key) {
    const playlistItem = handle.closest("[data-item]");
    const neighbour = key === "ArrowUp" ? playlistItem.previousElementSibling : playlistItem.nextElementSibling;
    if (!neighbour) {
      return;
    }
    const previousOrder = sortable.toArray();
    if (key === "ArrowUp") {
      neighbour.before(playlistItem);
    } else {
      neighbour.after(playlistItem);
    }
    // Moving a node drops the focus; keep it on the handle so the next arrow press works.
    handle.focus();
    await saveOrder(previousOrder);
    if (document.activeElement === document.body) {
      handle.focus();
    }
  }

  if (typeof Sortable === "function" && root.dataset.orderUrl) {
    sortable = Sortable.create(list, {
      handle: "[data-drag-handle]",
      dataIdAttr: "data-movie-id",
      animation: 150,
      ghostClass: "playlist-item--ghost",
      dragClass: "playlist-item--drag",
      onStart() {
        orderBefore = sortable.toArray();
      },
      onEnd(event) {
        if (event.oldIndex === event.newIndex) {
          return;
        }
        saveOrder(orderBefore);
      },
    });

    list.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") {
        return;
      }
      const handle = event.target.closest("[data-drag-handle]");
      if (!handle) {
        return;
      }
      event.preventDefault();
      if (isSavingOrder) {
        return;
      }
      moveItemByKey(handle, event.key);
    });
  }

  list.addEventListener("click", (event) => {
    const buttonRemove = event.target.closest('[data-action="remove"]');
    if (!buttonRemove) {
      return;
    }
    removeItem(buttonRemove);
  });

  publicToggle?.addEventListener("change", togglePublic);
  saveButton?.addEventListener("click", toggleSave);

  renameButton?.addEventListener("click", startRename);
  renameInput?.addEventListener("blur", saveRename);
  renameInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveRename();
    } else if (event.key === "Escape") {
      cancelRename();
    }
  });

  coverButton?.addEventListener("click", () => coverInput.click());
  coverInput?.addEventListener("change", uploadCover);
  coverReset?.addEventListener("click", resetCover);

  deleteButton?.addEventListener("click", openDeleteDialog);
  cancelDeleteButton?.addEventListener("click", () => deleteDialog.close());
  confirmDeleteButton?.addEventListener("click", deletePlaylist);
  deleteDialog?.addEventListener("click", (event) => {
    if (event.target === deleteDialog) {
      deleteDialog.close();
    }
  });
})();
