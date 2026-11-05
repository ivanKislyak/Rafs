(() => {
  window.RafsAvatarCrop = (root, changed) => {
    const preview = root.querySelector('[data-avatar-preview]');
    const file = root.querySelector('input[type=file]');
    const choose = root.querySelector('[data-avatar-choose]');
    const remove = root.querySelector('[data-avatar-remove]');
    const undo = root.querySelector('[data-avatar-undo]');
    const error = root.querySelector('[data-field-error=avatar_image]');
    const crop = root.querySelector('[data-avatar-crop]');
    const removal = root.querySelector('[data-avatar-remove-dialog]');
    const canvas = crop.querySelector('canvas');
    const stage = crop.querySelector('.profile-crop-stage');
    const zoom = crop.querySelector('input[type=range]');
    const confirm = crop.querySelector('[data-crop-confirm]');
    const status = crop.querySelector('[data-crop-status]');
    const context = canvas.getContext('2d');
    const size = canvas.width;
    let savedUrl = preview.getAttribute('src');
    let hasAvatar = root.dataset.hasAvatar === 'true';
    let action = 'keep';
    let blob = null;
    let previewUrl = null;
    let sourceUrl = null;
    let image = null;
    let generation = 0;
    let x = 0, y = 0, drag = null;

    function update() {
      preview.src = action === 'upload' ? previewUrl : action === 'remove' ? root.dataset.defaultAvatar : savedUrl;
      remove.disabled = action === 'remove' || (action === 'keep' && !hasAvatar);
      undo.hidden = action === 'keep';
    }
    function clearDraft() {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = null;
      blob = null;
      action = 'keep';
    }
    function draw() {
      if (!image) return;
      const scale = Math.max(size / image.naturalWidth, size / image.naturalHeight) * Number(zoom.value);
      const width = image.naturalWidth * scale, height = image.naturalHeight * scale;
      x = Math.max(-(width - size) / 2, Math.min((width - size) / 2, x));
      y = Math.max(-(height - size) / 2, Math.min((height - size) / 2, y));
      context.clearRect(0, 0, size, size);
      context.drawImage(image, (size - width) / 2 + x, (size - height) / 2 + y, width, height);
    }
    function cleanSource() {
      generation += 1;
      if (sourceUrl) URL.revokeObjectURL(sourceUrl);
      sourceUrl = null;
      image = null;
      drag = null;
      file.value = '';
    }
    // Native dialogs provide inert background; keep Tab inside the active panel.
    [crop, removal].forEach(dialog => {
      dialog.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const controls = [...dialog.querySelectorAll('button, input, [tabindex="0"]')]
          .filter(el => !el.disabled && el.getClientRects().length);
        const first = controls[0], last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      });
      dialog.addEventListener('click', event => {
        const box = dialog.getBoundingClientRect();
        if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right
            || event.clientY < box.top || event.clientY > box.bottom)) dialog.close();
      });
    });
    crop.addEventListener('close', () => { cleanSource(); choose.focus({ preventScroll: true }); });
    removal.addEventListener('close', () => { (remove.disabled ? choose : remove).focus({ preventScroll: true }); });
    choose.addEventListener('click', () => file.click());
    file.addEventListener('change', () => {
      const selected = file.files[0];
      if (!selected) return;
      error.textContent = '';
      if (selected.size > 12 * 1024 * 1024) {
        error.textContent = root.dataset.imageSizeError;
        file.value = '';
        return;
      }
      cleanSource();
      const version = generation;
      confirm.disabled = true;
      zoom.disabled = true;
      status.textContent = root.dataset.loading;
      context.clearRect(0, 0, size, size);
      crop.showModal();
      sourceUrl = URL.createObjectURL(selected);
      const candidate = new Image();
      candidate.onload = () => {
        if (version !== generation || !crop.open) return;
        image = candidate;
        zoom.value = '1';
        x = 0; y = 0;
        draw();
        status.textContent = '';
        confirm.disabled = false;
        zoom.disabled = false;
        stage.focus({ preventScroll: true });
      };
      candidate.onerror = () => {
        if (version !== generation) return;
        crop.close();
        error.textContent = root.dataset.imageError;
      };
      candidate.src = sourceUrl;
    });
    zoom.addEventListener('input', draw);
    canvas.addEventListener('pointerdown', event => {
      if (!image || drag || event.button !== 0) return;
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', event => {
      if (!drag || drag.id !== event.pointerId) return;
      const scale = size / canvas.getBoundingClientRect().width;
      x += (event.clientX - drag.x) * scale;
      y += (event.clientY - drag.y) * scale;
      drag.x = event.clientX; drag.y = event.clientY;
      draw();
    });
    ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(type => canvas.addEventListener(type, () => { drag = null; }));
    stage.addEventListener('keydown', event => {
      const delta = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10] }[event.key];
      if (!delta || !image) return;
      event.preventDefault();
      x += delta[0]; y += delta[1]; draw();
    });
    crop.querySelector('[data-crop-cancel]').addEventListener('click', () => crop.close());
    confirm.addEventListener('click', () => {
      if (!image || confirm.disabled) return;
      const version = generation;
      confirm.disabled = true;
      try {
        canvas.toBlob(result => {
          if (version !== generation || !crop.open) return;
          if (!result) { status.textContent = root.dataset.imageError; confirm.disabled = false; return; }
          clearDraft();
          action = 'upload'; blob = result; previewUrl = URL.createObjectURL(result);
          update(); changed(); crop.close();
        }, 'image/png');
      } catch {
        status.textContent = root.dataset.imageError;
        confirm.disabled = false;
      }
    });
    remove.addEventListener('click', () => removal.showModal());
    removal.querySelector('[data-remove-cancel]').addEventListener('click', () => removal.close());
    removal.querySelector('[data-remove-confirm]').addEventListener('click', () => {
      clearDraft(); action = hasAvatar ? 'remove' : 'keep';
      update(); changed(); removal.close();
    });
    undo.addEventListener('click', () => { clearDraft(); update(); changed(); });
    update();
    return {
      get action() { return action; },
      get blob() { return blob; },
      saved(data) {
        clearDraft(); savedUrl = data.avatar_url; hasAvatar = data.has_avatar;
        update();
      },
      refresh: update,
    };
  };
})();
