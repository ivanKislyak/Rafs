(() => {
  const editor = document.querySelector('[data-avatar-editor]');
  if (!editor) return;

  const trigger = editor.querySelector('summary');
  const fileInput = editor.querySelector('input[type="file"]');
  const chooseButton = editor.querySelector('[data-avatar-choose]');
  const filename = editor.querySelector('[data-avatar-filename]');
  const cancelButton = editor.querySelector('[data-avatar-cancel]');

  function closeEditor() {
    editor.open = false;
    trigger.setAttribute('aria-expanded', 'false');
    trigger.focus({ preventScroll: true });
  }

  editor.addEventListener('toggle', () => {
    trigger.setAttribute('aria-expanded', String(editor.open));
    if (editor.open) chooseButton.focus({ preventScroll: true });
  });

  // Only this explicit button activates the hidden native file input.
  chooseButton.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    filename.textContent = fileInput.files[0]?.name || filename.dataset.empty;
  });
  cancelButton.addEventListener('click', closeEditor);

  document.addEventListener('click', (event) => {
    if (editor.open && !editor.contains(event.target)) closeEditor();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && editor.open) {
      event.preventDefault();
      closeEditor();
    }
  });
})();
