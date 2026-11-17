(() => {
    const root = document.querySelector('div[data-add-to-playlist]')
    const addToPlaylistBtn = root.querySelector('button[data-action="toggle-menu"]')
    const addToPlaylistMenu = root.querySelector('div[data-menu]')
    const playlistList = root.querySelector('ul[data-menu-list]')
    const newMovieTitle = root.querySelector('form[data-menu-create]')
    const errorEl = root.querySelector('p[data-menu-error]')
})()