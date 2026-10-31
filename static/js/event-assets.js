/* Appearance only. The single switch is data-event on <html> in base.html.
 * No dates, storage keys, messages or award signals are used here. */
(() => {
  const root = document.documentElement;
  const icons = Array.from(document.querySelectorAll("link[data-event-icon]"), (icon) => ({
    icon,
    ordinary: icon.getAttribute("href"),
  }));
  const updateIcons = () => {
    const enabled = root.dataset.event === "halloween-2026";
    icons.forEach(({ icon, ordinary }) => {
      icon.setAttribute("href", enabled ? icon.dataset.eventIcon : ordinary);
      if (icon.hasAttribute("data-event-only")) {
        if (enabled) icon.setAttribute("rel", "icon");
        else icon.removeAttribute("rel");
      }
    });
  };
  updateIcons();
  new MutationObserver(updateIcons).observe(root, { attributes: true, attributeFilter: ["data-event"] });
})();
