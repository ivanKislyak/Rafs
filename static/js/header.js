(() => {
  const header = document.querySelector('[data-site-header]');
  if (!header) return;
  const mobile = window.matchMedia('(max-width: 900px)');
  const search = header.querySelector('[data-header-search]');
  const input = search.querySelector('[data-header-search-input]');
  const suggestions = search.querySelector('[data-header-search-suggestions]');
  const panels = [
    { trigger: header.querySelector('[data-header-navigation-toggle]'), panel: header.querySelector('#header-navigation') },
    { trigger: header.querySelector('[data-header-search-toggle]'), panel: search },
    { trigger: header.querySelector('.header-profile-trigger'), panel: header.querySelector('#header-profile-panel') },
  ].filter(({ trigger, panel }) => trigger && panel);

  function close(item, restoreFocus = false) {
    item.trigger.setAttribute('aria-expanded', 'false');
    item.panel.classList.remove('is-open');
    if (item.panel.id === 'header-profile-panel') item.panel.hidden = true;
    if (item.panel === search) {
      suggestions.hidden = true;
      input.setAttribute('aria-expanded', 'false');
    }
    if (restoreFocus) item.trigger.focus();
  }
  function closeOthers(except) {
    panels.forEach((item) => { if (item !== except) close(item); });
  }
  panels.forEach((item) => {
    item.trigger.addEventListener('click', () => {
      const willOpen = item.trigger.getAttribute('aria-expanded') !== 'true';
      closeOthers(item);
      if (!willOpen) return close(item);
      item.trigger.setAttribute('aria-expanded', 'true');
      item.panel.hidden = false;
      item.panel.classList.add('is-open');
      if (item.panel === search) input.focus();
      else {
        const focusArea = !mobile.matches && item.panel.id === 'header-navigation'
          ? item.panel.querySelector('.header-navigation-extras') : item.panel;
        focusArea.querySelector('a, button, select')?.focus();
      }
    });
    item.panel.addEventListener('click', (event) => {
      if (event.target.closest('a, [data-theme-toggle], .header-logout-button')) {
        close(item, Boolean(event.target.closest('[data-theme-toggle]')));
      }
    });
  });
  document.addEventListener('click', (event) => {
    panels.forEach((item) => {
      if (!item.panel.contains(event.target) && !item.trigger.contains(event.target)) close(item);
    });
    if (!search.contains(event.target) && !header.querySelector('[data-header-search-toggle]').contains(event.target)) {
      suggestions.hidden = true;
      input.setAttribute('aria-expanded', 'false');
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const active = panels.find((item) => item.trigger.getAttribute('aria-expanded') === 'true');
    if (active) { close(active, true); event.preventDefault(); }
    else if (!suggestions.hidden) {
      suggestions.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      input.focus();
      event.preventDefault();
    }
  });
  mobile.addEventListener('change', () => {
    // A viewport change must not leave focus inside a now hidden mobile panel.
    const owner = panels.find((item) => item.panel.contains(document.activeElement));
    panels.forEach((item) => close(item));
    if (owner && owner.panel !== search) owner.trigger.focus();
    else if (owner && mobile.matches) owner.trigger.focus();
  });

  const form = search.querySelector('[data-header-search-form]');
  const clearButton = search.querySelector('[data-header-search-clear]');
  const openSuggestions = () => {
    closeOthers(panels.find((item) => item.panel === search));
    suggestions.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  };
  const updateClearButton = () => { clearButton.hidden = input.value.length === 0; };
  input.addEventListener('focus', openSuggestions);
  input.addEventListener('click', openSuggestions);
  input.addEventListener('input', updateClearButton);
  clearButton.addEventListener('click', () => {
    input.value = '';
    updateClearButton();
    input.focus();
    openSuggestions();
  });
  search.querySelectorAll('[data-search-value]').forEach((card) => {
    card.addEventListener('click', () => {
      input.value = card.dataset.searchValue;
      updateClearButton();
      form.requestSubmit();
    });
  });
  function sendSearchHistory(searchQuery) {
    fetch('/accounts/api/v1/search-history/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            "X-CSRFToken": form.dataset.csrf,
        },
        body: JSON.stringify({
            query: searchQuery
        }),
        keepalive: true
    })
    .then(response => response.json())
    .then(data => {
        console.log('Successfully saved on the backend:', data);
    })
    .catch(error => {
        console.error('Something went wrong:', error);
    });
  }
  form.addEventListener('submit', (event) => {
    input.value = input.value.trim();
    if (!input.value) { event.preventDefault(); openSuggestions(); input.focus(); 
    } else {
      sendSearchHistory(input.value);
    }
  });
  updateClearButton();
})();
