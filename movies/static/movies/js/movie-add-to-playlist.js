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

  // 3rd Stage - response
})();
