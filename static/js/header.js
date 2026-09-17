(() => {
  const profileMenu = document.querySelector(".header-profile");

  if (!profileMenu) return;

  const trigger = profileMenu.querySelector(".header-profile-trigger");

  document.addEventListener("click", (event) => {
    if (profileMenu.open && !profileMenu.contains(event.target)) {
      profileMenu.open = false;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !profileMenu.open) return;

    profileMenu.open = false;
    trigger?.focus();
  });
})();

(() => {
  const search = document.querySelector("[data-header-search]");

  if (!search) return;

  const form = search.querySelector("[data-header-search-form]");
  const input = search.querySelector("[data-header-search-input]");
  const suggestions = search.querySelector("[data-header-search-suggestions]");
  const clearButton = search.querySelector("[data-header-search-clear]");
  const suggestionCards = search.querySelectorAll("[data-search-value]");

  const openSuggestions = () => {
    suggestions.hidden = false;
    input.setAttribute("aria-expanded", "true");
  };

  const closeSuggestions = () => {
    suggestions.hidden = true;
    input.setAttribute("aria-expanded", "false");
  };

  const updateClearButton = () => {
    clearButton.hidden = input.value.length === 0;
  };

  input.addEventListener("focus", openSuggestions);
  input.addEventListener("click", openSuggestions);
  input.addEventListener("input", updateClearButton);

  clearButton.addEventListener("click", () => {
    input.value = "";
    updateClearButton();
    openSuggestions();
    input.focus();
  });

  suggestionCards.forEach((card) => {
    card.addEventListener("click", () => {
      input.value = card.dataset.searchValue;
      updateClearButton();
      form.requestSubmit();
    });
  });

  form.addEventListener("submit", (event) => {
    input.value = input.value.trim();

    if (!input.value) {
      event.preventDefault();
      openSuggestions();
      input.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (!search.contains(event.target)) closeSuggestions();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || suggestions.hidden) return;

    closeSuggestions();
    input.focus();
  });

  updateClearButton();
})();
