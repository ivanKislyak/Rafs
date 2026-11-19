(() => {
  const root = document.querySelector("[data-add-to-playlist]");
  if (!root) {
    return;
  }

  // 1st Stage - elements and data
  const toggle = root.querySelector('button[data-action="toggle-menu"]');
  const menu = root.querySelector("div[data-menu]");
  const list = root.querySelector("ul[data-menu-list]");
  const errorEl = root.querySelector("p[data-menu-error]");
  const createForm = root.querySelector("form[data-menu-create]");
  const nameInput = createForm.querySelector('input[name="name"]');

  const { movieId, playlistsUrl, itemUrlTemplate, msgLoadError, msgToggleError, msgEmpty } = root.dataset;

  console.log({ toggle, menu, list, errorEl, createForm, nameInput });
  console.log({ movieId, playlistsUrl, itemUrlTemplate });

  // 2nd Stage - functions
  function openMenu() {
    clearError();
    loadPlaylists();
    menu.hidden = false;
    menu.setAttribute("aria-expanded", "true");
  }

  function closeMenu() {
    menu.hidden = true;
    menu.setAttribute("aria-expanded", "false");
  }

  // 3rd Stage - handlers and response
  toggle.addEventListener("click", () => {
    menu.hidden ? openMenu() : closeMenu();
  });

  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!menu.hidden) {
      closeMenu();
      toggle.focus();
    }
  });

  let loaded = false;

  function showError(text) {
    errorEl.textContent = text;
    errorEl.hidden = false;
  }
  function clearError() {
    errorEl.hidden = true;
  }

  async function loadPlaylists() {
    if (loaded) {
      return;
    }
    try {
      const response = await apiRequest(`${playlistsUrl}?movie_id=${movieId}`);
      console.log(response.data);
      loaded = true;
    } catch (error) {
      console.error(error);
      showError(msgLoadError);
    }
  }
})();
