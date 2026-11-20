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
  const {
    movieId,
    playlistsUrl,
    itemUrlTemplate,
    msgLoadError,
    msgToggleError,
    msgEmpty,
  } = root.dataset;

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

  list.addEventListener("change", async (event) => {
    const box = event.target;
    if (!box.matches('input[type="checkbox"]')) return;
    box.disabled = true;
    const inputStatus = box.checked;
    clearError();
    try {
      await apiRequest(
        itemUrlTemplate
          .replace("__PL__", box.dataset.playlistId)
          .replace("__MOVIE__", movieId),
        { method: inputStatus ? "PUT" : "DELETE" },
      );
    } catch (error) {
      console.error(error);
      showError(msgToggleError);
      box.checked = !inputStatus;
    } finally {
      box.disabled = false;
    }
  });

  createForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = nameInput.value.trim();
    if (!name) {
      nameInput.value = '';
      nameInput.focus();
      return;
    }

    const button = createForm.querySelector('[type="submit"]');
    button.disabled = true;
    clearError();

    let playlist = null;
    try {
      const response1 = await apiRequest(playlistsUrl, {
        method: "POST",
        body: { name: name },
      });
      
      playlist = response1.data;
      const response2 = await apiRequest(
        itemUrlTemplate
          .replace("__PL__", playlist.id)
          .replace("__MOVIE__", movieId),
        { method: "PUT" },
      );
      playlist.contains_movie = true;
    } catch (error) {
      const errorResponse =
        (error.data?.name?.[0] ?? error.data?.detail) || msgToggleError;
      showError(errorResponse);
      console.error(errorResponse);
    } finally {
      button.disabled = false;
    }

    if (playlist) {
      list.querySelector('p') ? list.replaceChildren() : list.prepend(renderRow(playlist));
      createForm.reset();
    }
  });
})();
