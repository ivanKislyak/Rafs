/* Progressive enhancement: native scroll/snap, links and touch work without JS. */
(() => {
  document.querySelectorAll("[data-collection]").forEach((section) => {
    const track = section.querySelector("[data-collection-track]");
    const controls = section.querySelector("[data-collection-controls]");
    const previous = section.querySelector("[data-collection-prev]");
    const next = section.querySelector("[data-collection-next]");
    if (!track || !controls || !previous || !next) return;

    const isRTL = getComputedStyle(track).direction === "rtl";
    const position = () => Math.abs(track.scrollLeft);
    const update = () => {
      const end = track.scrollWidth - track.clientWidth;
      controls.hidden = end <= 2;
      previous.disabled = position() <= 2;
      next.disabled = position() >= end - 2;
    };
    const move = (direction) => {
      const card = track.firstElementChild;
      if (!card) return;
      const gap = parseFloat(getComputedStyle(track).columnGap) || 0;
      const stride = card.getBoundingClientRect().width + gap;
      const count = Math.max(1, Math.floor((track.clientWidth + gap + 1) / stride));
      track.scrollBy({
        left: direction * (isRTL ? -1 : 1) * stride * count,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
      });
    };
    previous.addEventListener("click", () => move(-1));
    next.addEventListener("click", () => move(1));
    track.addEventListener("scroll", update, { passive: true });
    // Native Arrow keys still scroll the focused region. Home/End add a shortcut.
    track.addEventListener("keydown", (event) => {
      if (event.target !== track || !["Home", "End"].includes(event.key)) return;
      event.preventDefault();
      track.scrollTo({ left: event.key === "Home" ? 0 : (isRTL ? -1 : 1) * track.scrollWidth, behavior: "instant" });
    });
    if ("ResizeObserver" in window) new ResizeObserver(update).observe(track);
    window.addEventListener("resize", update, { passive: true });
    update();
  });
})();
