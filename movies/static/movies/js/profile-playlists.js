(() => {
    const root = document.querySelector('[data-playlists]')
    if (!root) return
    const url = root.dataset.apiUrl
    const createFormPlaylist = root.querySelector('form[data-create-form]')
    const errorEl = root.querySelector('[data-form-error]')
    const dialog = root.querySelector('dialog[data-create-dialog]');
    if (!dialog) return;
    const closeDialog = dialog.querySelector('button[data-action="close-dialog"]')
    const inputName = document.getElementById('profile-playlist-name')
    root.addEventListener("click", (event) => {
        const addPlaylistButton = event.target.closest('[data-action="open-create"]')
        if (!addPlaylistButton) return;
        errorEl.hidden = true;
        createFormPlaylist.reset()
        dialog.showModal()
    });
    closeDialog.addEventListener("click", () => {
        dialog.close()
    });
    createFormPlaylist.addEventListener('submit', async(event) => {
        event.preventDefault();
        try {
            const response = await apiRequest(url, {
                method: "POST",
                body: { name: inputName.value.trim() },
            });
            const newData = await response.json();
        } catch (error) {
        } finally {
        }
    })

})()