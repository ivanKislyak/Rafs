(() => {
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      location.reload();
    }
  });
  const root = document.querySelector("[data-playlists]");
  if (!root) {
    return;
  }
  const url = root.dataset.apiUrl;
  const createFormPlaylist = root.querySelector("form[data-create-form]");
  const errorEl = root.querySelector("[data-form-error]");
  const emptyErrReason = errorEl.dataset.emptyFieldError;
  const dialog = root.querySelector("dialog[data-create-dialog]");
  if (!dialog) {
    return;
  }
  const closeDialog = dialog.querySelector('button[data-action="close-dialog"]');
  const inputName = document.getElementById("profile-playlist-name");
  const privateInput = createFormPlaylist.querySelector('input[name="is_private"]');
  const submitButton = createFormPlaylist.querySelector('[type="submit"]');

  // Optional cover: kept in a variable (not only in the file input) so a dropped file works the same way.
  const coverField = dialog.querySelector("[data-cover-field]");
  const coverInput = coverField.querySelector("[data-cover-input]");
  const coverPicker = coverField.querySelector('[data-action="pick-cover"]');
  const coverRemove = coverField.querySelector('[data-action="remove-cover"]');
  const coverPreview = coverField.querySelector("[data-cover-preview]");
  let coverFile = null;
  let coverUrl = null;

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function setCover(file) {
    if (coverUrl) {
      URL.revokeObjectURL(coverUrl);
      coverUrl = null;
    }
    coverFile = file;
    if (file) {
      coverUrl = URL.createObjectURL(file);
      coverPreview.src = coverUrl;
      coverField.dataset.hasCover = "";
    } else {
      coverPreview.removeAttribute("src");
      delete coverField.dataset.hasCover;
    }
    // Reset the input so choosing the same file again still fires "change".
    coverInput.value = "";
  }

  function pickCover(file) {
    if (!file) {
      return;
    }
    if (!file.type.startsWith("image/")) {
      showError(root.dataset.msgCoverType);
      return;
    }
    errorEl.hidden = true;
    setCover(file);
  }

  root.addEventListener("click", (event) => {
    const addPlaylistButton = event.target.closest('[data-action="open-create"]');
    if (!addPlaylistButton) {
      return;
    }
    errorEl.hidden = true;
    createFormPlaylist.reset();
    setCover(null);
    dialog.showModal();
    inputName.focus();
  });
  closeDialog.addEventListener("click", () => {
    dialog.close();
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      dialog.close();
    }
  });

  coverPicker.addEventListener("click", () => coverInput.click());
  coverInput.addEventListener("change", () => pickCover(coverInput.files[0]));
  coverRemove.addEventListener("click", () => {
    setCover(null);
    coverPicker.focus();
  });

  coverPicker.addEventListener("dragover", (event) => {
    event.preventDefault();
    coverField.dataset.dragover = "";
  });
  coverPicker.addEventListener("dragleave", () => {
    delete coverField.dataset.dragover;
  });
  coverPicker.addEventListener("drop", (event) => {
    event.preventDefault();
    delete coverField.dataset.dragover;
    pickCover(event.dataTransfer.files[0]);
  });

  createFormPlaylist.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = inputName.value.trim();
    if (!name) {
      showError(emptyErrReason);
      inputName.focus();
      return;
    }
    const isPublic = !privateInput.checked;
    // One request either way: with a cover it goes as multipart, so a rejected image creates nothing.
    let body = { name: name, is_public: isPublic };
    if (coverFile) {
      body = new FormData();
      body.append("name", name);
      body.append("is_public", String(isPublic));
      body.append("cover", coverFile);
    }

    submitButton.disabled = true;
    createFormPlaylist.setAttribute("aria-busy", "true");
    errorEl.hidden = true;
    try {
      const response = await apiRequest(url, { method: "POST", body: body });
      const pageTemplate = root.dataset.playlistPageTemplate;
      dialog.close();
      location.href = pageTemplate.replace("__ID__", response.data.id);
    } catch (error) {
      const data = error.data;
      showError(data?.cover?.[0] ?? data?.name?.[0] ?? data?.detail ?? root.dataset.msgCreateError);
      console.error(error);
    } finally {
      submitButton.disabled = false;
      createFormPlaylist.removeAttribute("aria-busy");
    }
  });
})();
