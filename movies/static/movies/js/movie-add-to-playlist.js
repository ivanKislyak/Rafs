(() => {
  const root = document.querySelector("[data-add-to-playlist]");
  if (!root) {
    return;
  }

  const toggle = root.querySelector('button[data-action="toggle-menu"]');
  const menu = root.querySelector("div[data-menu]");
  const list = root.querySelector("ul[data-menu-list]");
  const errorEl = root.querySelector("p[data-menu-error]");
  const createForm = root.querySelector("form[data-menu-create]");
  const nameInput = createForm.querySelector('input[name="name"]');
  const { movieId, playlistsUrl, itemUrlTemplate, msgLoadError, msgToggleError, msgEmpty } = root.dataset;

  function openMenu() {
    clearError();
    loadPlaylists();
    menu.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
  }

  function closeMenu() {
    menu.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }

  toggle.addEventListener("click", () => {
    menu.hidden ? openMenu() : closeMenu();
  });

  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!menu.hidden && event.key === "Escape") {
      closeMenu();
      toggle.focus();
    }
  });

  function showError(text) {
    errorEl.textContent = text;
    errorEl.hidden = false;
  }
  function clearError() {
    errorEl.hidden = true;
  }

  function renderRow(playlist) {
    const listItem = document.createElement("li");
    const labelPlaylist = document.createElement("label");
    const inputCheckbox = document.createElement("input");
    const spanName = document.createElement("span");
    listItem.append(labelPlaylist);
    labelPlaylist.append(inputCheckbox);
    labelPlaylist.append(spanName);
    inputCheckbox.type = "checkbox";
    inputCheckbox.checked = playlist.contains_movie;
    inputCheckbox.dataset.playlistId = playlist.id;
    spanName.textContent = playlist.name;
    return listItem;
  }

  function showMessage(text) {
    const liEl = document.createElement("li");
    const pEl = document.createElement("p");
    liEl.append(pEl);
    pEl.textContent = text;
    list.replaceChildren(liEl);
  }

  let loaded = false;
  async function loadPlaylists() {
    if (loaded) {
      return;
    }
    try {
      showMessage("Загрузка...");
      const response = await apiRequest(`${playlistsUrl}?movie_id=${movieId}`);
      if (response.data.length === 0) {
        showMessage(msgEmpty);
        return;
      }
      list.replaceChildren(...response.data.map(renderRow));
      loaded = true;
    } catch (error) {
      console.error(error);
      showError(msgLoadError);
    }
  }
})();
