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
const isAuthenticated = form.dataset.isAuthenticated?.toLowerCase() === "true";

const escapeHtml = (str) => {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
};

const ICONS = {
    history: `
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <circle cx="12" cy="12" r="8.5"></circle>
            <path d="M12 7.5V12l3 2"></path>
        </svg>
    `,
    popular: `
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M5 16.5 10 11l3 3 6-7"></path>
            <path d="M14.5 7H19v4.5"></path>
        </svg>
    `
};

const renderSuggestions = async () => {
    let searchHistory = [];

    if (isAuthenticated) {
        try {
            const response = await fetch('/accounts/api/v1/search-history/', {
                method: 'GET'
            });

            if (response.ok) {
                const data = await response.json();
                const items = Array.isArray(data) ? data : (data.results || []);
                // API returns newest first; Set keeps the first occurrence.
                searchHistory = [...new Set(items.map(item => item))].slice(0, 11);
            }
        } catch (error) {
            console.error('Failed to load search history:', error);
        }
    }

    const popularSearches = JSON.parse(suggestions.dataset.popularSearches || '[]');
    
    const textHistory = suggestions.dataset.textHistory || 'Search history';
    const textPopular = suggestions.dataset.textPopular || 'Popular searches';
    const textEmpty = suggestions.dataset.textEmpty || 'No search suggestions yet';

    let html = '';

    if (searchHistory.length > 0) {
      html += `<p class="search-suggestions-title">${escapeHtml(textHistory)}</p>`;
      html += `<div class="search-suggestions-list">`;
      searchHistory.forEach(item => {
          html += `
              <div class="search-suggestions-item">
                  <button class="search-suggestion-card" type="submit" data-search-value="${escapeHtml(item.query)}">
                      ${ICONS.history || ''}
                      <span>${escapeHtml(item.query)}</span>
                  </button>
                  <button class="delete-search-result" type="button" data-delete-id="${escapeHtml(item.id)}" aria-label="Delete">
                    <svg xmlns="http://w3.org" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18"></line>
                      <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                  </button>
              </div>
          `;
      });
      html += `</div>`;
    }
    else if (popularSearches.length > 0) {
        html += `<p class="search-suggestions-title">${escapeHtml(textPopular)}</p>`;
        html += `<div class="search-suggestions-list">`;
        popularSearches.forEach(item => {
            html += `
                <button class="search-suggestion-card" type="button" role="option" data-search-value="${escapeHtml(item.query)}">
                    ${ICONS.popular}
                    <span>${escapeHtml(item.query)}</span>
                </button>
            `;
        });
        html += `</div>`;
    } 
    else {
        html += `<p class="search-suggestions-empty">${escapeHtml(textEmpty)}</p>`;
    }

    suggestions.innerHTML = html;
};

const openSuggestions = async () => {
  if (!suggestions.hidden) return;
  closeOthers(panels.find((item) => item.panel === search));
  
  suggestions.hidden = false;
  input.setAttribute('aria-expanded', 'true');
  
  await renderSuggestions(); 
};

const updateClearButton = () => { 
    clearButton.hidden = input.value.length === 0; 
};

input.addEventListener('focus', openSuggestions);
input.addEventListener('click', openSuggestions);
input.addEventListener('input', updateClearButton);

clearButton.addEventListener('click', () => {
    input.value = '';
    updateClearButton();
    input.focus();
    openSuggestions();
});

suggestions.addEventListener('click', (event) => {
    const card = event.target.closest('[data-search-value]');
    if (!card) return;

    input.value = card.dataset.searchValue;
    updateClearButton();
    suggestions.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    
    if (form) {
        form.requestSubmit();
    }
});
function sendSearchHistory(searchQuery) {
  fetch(`/accounts/api/v1/search-history/`, {
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
  .then(response => {
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.json();
  })
  .then(data => {
      console.log('Successfully saved on the backend:', data);
  })
  .catch(error => {
      console.error('Something went wrong:', error);
  });
}
function deleteSearchResult(pk) {
  fetch(`/accounts/api/v1/search-history/${pk}/`, {
      method: 'DELETE',
      headers: {
          "X-CSRFToken": form.dataset.csrf,
      },
      keepalive: true
  })
  .then(response => {
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.status === 204 ? null: response.json();
  })
  .then(data => {
      console.log('Successfully deleted on the backend:', data);
  })
  .catch(error => {
      console.error('Something went wrong:', error);
  });
}

form.addEventListener('submit', (event) => {
  input.value = input.value.trim();
  if (!input.value) { 
    event.preventDefault(); 
    openSuggestions(); 
    input.focus(); 
  } else if (isAuthenticated) {
    sendSearchHistory(input.value);
  }
});

suggestions.addEventListener('click', (event) => {
  const deleteButton = event.target.closest('.delete-search-result');
  
  if (deleteButton) {
    event.preventDefault();
    event.stopPropagation();

    const pkQuery = deleteButton.dataset.deleteId

    if (isAuthenticated) {
      deleteSearchResult(pkQuery);
      
      const listItem = deleteButton.closest('.search-suggestions-item');
      if (listItem) listItem.remove();
    }
  }
});

updateClearButton();
})();
