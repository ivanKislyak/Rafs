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
  const dialog = root.querySelector("dialog[data-create-dialog]");
  if (!dialog) {
    return;
  }
  const closeDialog = dialog.querySelector('button[data-action="close-dialog"]');
  const inputName = document.getElementById("profile-playlist-name");
  root.addEventListener("click", (event) => {
    const addPlaylistButton = event.target.closest('[data-action="open-create"]');
    if (!addPlaylistButton) {
      return;
    }
    errorEl.hidden = true;
    createFormPlaylist.reset();
    dialog.showModal();
  });
  closeDialog.addEventListener("click", () => {
    dialog.close();
  });
  createFormPlaylist.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = createFormPlaylist.querySelector('[type="submit"]');
    submitButton.disabled = true;
    try {
      const response = await apiRequest(url, {
        method: "POST",
        body: { name: inputName.value.trim() },
      });
      const playlistId = response.data.id;
      const pageTemplate = root.dataset.playlistPageTemplate;
      dialog.close();
      location.href = pageTemplate.replace("__ID__", playlistId);
    } catch (error) {
      console.error(error);
    } finally {
      submitButton.disabled = false;
    }
  });
})();
