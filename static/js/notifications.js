(() => {
  const region = document.querySelector("#site-toast-region");

  if (!region) {
    return;
  }

  const toasts = Array.from(region.querySelectorAll("[data-site-toast]"));
  if (!toasts.length) {
    return;
  }

  // Present the badge first, then preserve every other message (including Frames).
  const hasAwardTags = toast => {
    const tags = new Set((toast.dataset.toastTags || '').split(/\s+/));
    return tags.has('halloween-award-earned') && tags.has('review-or-treat-2026');
  };
  toasts.sort((a, b) => Number(hasAwardTags(b)) - Number(hasAwardTags(a)));
  toasts.forEach(toast => { toast.hidden = true; });
  document.documentElement.classList.add('has-toast-js');

  function nextToast() {
    const toast = toasts.shift();
    if (!toast) {
      region.remove();
      return;
    }
    if (window.RafsHalloweenAward?.present(toast, () => {
      toast.remove();
      nextToast();
    })) return;
    showToast(toast);
  }

  function showToast(toast) {

    let closeTimer;
    let rewardTimer;
    let isClosed = false;

    const closeToast = () => {
      if (isClosed) {
        return;
      }

      isClosed = true;
      window.clearTimeout(closeTimer);
      window.clearTimeout(rewardTimer);
      toast.classList.remove("is-visible");
      toast.classList.add("is-leaving");
      window.setTimeout(() => {
        toast.remove();
        nextToast();
      }, 230);
    };

    const animateFramesToBalance = () => {
      const balance = document.querySelector("[data-frames-balance]");
      const profileTrigger = document.querySelector("[data-profile-reward-target]");
      const origin = toast.querySelector("[data-toast-particle-origin]");

      if ((!balance && !profileTrigger) || !origin) {
        return;
      }

      const balanceRect = balance?.getBoundingClientRect();
      const target = balanceRect?.width && balanceRect?.height ? balance : profileTrigger;

      if (!target) {
        return;
      }

      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        target.classList.add("is-frames-rewarded");
        return;
      }

      const originRect = origin.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const targetX = targetRect.left + targetRect.width / 2;
      const targetY = targetRect.top + targetRect.height / 2;

      for (let index = 0; index < 7; index += 1) {
        const square = document.createElement("span");
        const startX = originRect.left + originRect.width / 2 + (index - 3) * 3;
        const startY = originRect.top + originRect.height / 2 + (index % 2) * 5;
        const endX = targetX - startX + (index - 3) * 2;
        const endY = targetY - startY;

        square.className = "frames-flight-square";
        square.style.left = `${startX}px`;
        square.style.top = `${startY}px`;
        square.style.setProperty("--square-size", `${4 + (index % 3)}px`);
        square.style.setProperty("--flight-delay", `${index * 45}ms`);
        square.style.setProperty("--flight-mid-x", `${endX * 0.44 - 24}px`);
        square.style.setProperty("--flight-mid-y", `${endY * 0.46 - 42}px`);
        square.style.setProperty("--flight-end-x", `${endX}px`);
        square.style.setProperty("--flight-end-y", `${endY}px`);
        square.addEventListener("animationend", () => square.remove(), { once: true });
        document.body.append(square);
      }

      window.setTimeout(() => {
        target.classList.add("is-frames-rewarded");
        window.setTimeout(() => target.classList.remove("is-frames-rewarded"), 700);
      }, 900);
    };

    toast.hidden = false;
    toast.querySelector("[data-toast-close]")?.addEventListener("click", closeToast);

    window.requestAnimationFrame(() => {
      toast.classList.add("is-visible");

      if (toast.dataset.toastTags.split(/\s+/).includes("frames-reward")) {
        rewardTimer = window.setTimeout(animateFramesToBalance, 240);
      }
    });

    closeTimer = window.setTimeout(closeToast, 4800);
  }

  nextToast();
})();
