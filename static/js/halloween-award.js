(() => {
  function present(toast, done) {
    const tags = new Set((toast.dataset.toastTags || '').split(/\s+/));
    const template = toast.querySelector('template[data-halloween-award]');
    if (!tags.has('halloween-award-earned') || !tags.has('review-or-treat-2026')
        || document.documentElement.dataset.event !== 'halloween-2026'
        || !template || typeof HTMLDialogElement === 'undefined') return false;

    const dialog = template.content.firstElementChild.cloneNode(true);
    const scare = dialog.querySelector('[data-award-scare]');
    const content = dialog.querySelector('[data-award-content]');
    const image = dialog.querySelector('[data-scare-image]');
    const close = dialog.querySelector('[data-award-close]');
    const skip = dialog.querySelector('[data-scare-skip]');
    const previousFocus = document.activeElement;
    const previousOverflow = document.documentElement.style.overflow;
    const scroll = { left: window.scrollX, top: window.scrollY };
    let finished = false;

    const showAward = () => {
      scare.hidden = true;
      content.hidden = false;
      const badge = content.querySelector('[data-award-badge]');
      if (badge && !badge.hasAttribute('src')) {
        badge.addEventListener('error', () => { badge.hidden = true; }, { once: true });
        badge.src = badge.dataset.src;
      }
      close.focus({ preventScroll: true });
    };
    const finish = () => {
      if (finished) return;
      finished = true;
      dialog.remove();
      document.documentElement.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
      window.scrollTo({ ...scroll, behavior: 'instant' });
      done();
    };

    skip.addEventListener('click', showAward);
    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('cancel', event => {
      event.preventDefault();
      if (!scare.hidden) showAward();
      else dialog.close();
    });
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const controls = [...dialog.querySelectorAll('button, a[href]')]
        .filter(element => !element.disabled && element.getClientRects().length);
      const first = controls[0];
      const last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    dialog.addEventListener('close', finish, { once: true });
    image.addEventListener('error', showAward, { once: true });
    document.body.append(dialog);
    try {
      dialog.showModal();
    } catch {
      // Unsupported/broken dialog implementation: keep the ordinary toast.
      dialog.remove();
      return false;
    }
    document.documentElement.style.overflow = 'hidden';
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      showAward();
    } else {
      scare.hidden = false;
      image.src = image.dataset.src;
      skip.focus({ preventScroll: true });
    }
    return true;
  }

  window.RafsHalloweenAward = { present };
})();
