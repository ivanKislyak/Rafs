(() => {
  const root = document.documentElement;
  const storageKey = "rafs-theme";

  const readTheme = () => {
    try {
      return localStorage.getItem(storageKey) === "light" ? "light" : "dark";
    } catch (_error) {
      return "dark";
    }
  };

  const saveTheme = (theme) => {
    try {
      localStorage.setItem(storageKey, theme);
    } catch (_error) {
      // The selected theme still applies for the current page.
    }
  };

  const applyTheme = (theme) => {
    root.dataset.theme = theme;
  };

  applyTheme(readTheme());

  const setupToggle = () => {
    const toggle = document.querySelector("[data-theme-toggle]");
    if (!toggle) return;

    const label = toggle.querySelector("[data-theme-toggle-label]");

    const updateToggle = () => {
      const isLight = root.dataset.theme === "light";
      const nextLabel = isLight ? toggle.dataset.darkLabel : toggle.dataset.lightLabel;
      toggle.setAttribute("aria-label", nextLabel);
      toggle.setAttribute("aria-pressed", String(isLight));
      if (label) label.textContent = nextLabel;
    };

    toggle.addEventListener("click", () => {
      const nextTheme = root.dataset.theme === "light" ? "dark" : "light";
      applyTheme(nextTheme);
      saveTheme(nextTheme);
      updateToggle();
    });

    updateToggle();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupToggle, { once: true });
  } else {
    setupToggle();
  }
})();
