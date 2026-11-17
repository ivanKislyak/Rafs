(() => {
    const root = document.querySelector('[data-playlists]')
    if (!root) return
    const createFormPlaylist = root.querySelector('form[data-create-form]')
    const errorEl = root.querySelector('[data-form-error]')
    const dialog = root.querySelector('dialog[data-create-dialog]');
    if (!dialog) return;
    const closeDialog = root.querySelector('button[data-action="close-dialog"]')
    root.addEventListener("click", (event) => {
        const addPlaylistButton = event.target.closest('[data-action="open-create"]')
        if (!addPlaylistButton) return;
        errorEl.hidden = true;
        createFormPlaylist.reset()
        dialog.showModal()
    });
    closeDialog.addEventListener("click", () => {
        dialog.close()
    })

})()