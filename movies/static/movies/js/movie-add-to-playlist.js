(() => {
    const root = document.querySelector('div[data-add-to-playlist]')
    if (!root) return;
    const playlistList = root.querySelector('ul[data-menu-list]')
    const newMovieTitle = root.querySelector('form[data-menu-create]')
    const errorEl = root.querySelector('p[data-menu-error]')
    
    root.addEventListener("click", (event) => {
        const addToPlaylistBtn = event.target.closest('button[data-action="toggle-menu"]')
        if (!addToPlaylistBtn) return;
        errorEl.hidden = true;
        const addToPlaylistMenu = root.querySelector('div[data-menu]')
        addToPlaylistMenu.hidden = false
    });
})()