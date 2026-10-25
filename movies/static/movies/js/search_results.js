(() => {
  const urlParams = new URLSearchParams(window.location.search);
  const query = urlParams.get('query') || '';
  const searchResultsList = document.querySelector(".search-results-list")
  const params = new URLSearchParams();
  params.append("query", `${query}`);
  let requestUrl = `/movies/api/v1/search/?${params.toString()}`
  const renderSearchResults = async () => {
    try {
      if (!requestUrl) return;
      const response = await fetch(requestUrl, {method: "GET"})
      if (!response.ok) throw new Error(`Response status: ${response.status}`);
      const jsonResponse = await response.json()
      const results = jsonResponse.results
      const HTMLTemplates = []

      for (const result of results) {
        if (result.type) {
          if (result.type === "movie") {
            const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
              '&': '&amp;',
              '<': '&lt;',
              '>': '&gt;',
              '"': '&quot;',
              "'": '&#39;',
            })[character]);
            const fallbackImage = searchResultsList.dataset.fallbackSrc || '/static/movies/images/nocover.png';
            const title = escapeHTML(result.title || result.wikidata_id || '');
            const descriptionWords = String(result.description ?? '').trim().split(/\s+/);
            const description = escapeHTML(
              descriptionWords.slice(0, 34).join(' ') + (descriptionWords.length > 34 ? ' …' : '')
            );
            const rank = result.rank != null && Number.isFinite(Number(result.rank))
              ? Number(result.rank).toLocaleString(document.documentElement.lang || 'en', {
                  minimumFractionDigits: 3,
                  maximumFractionDigits: 3,
                })
              : null;

            HTMLTemplates.push(
              `<article class="search-result-card search-result-card--movie">
                <a class="search-result-movie-link"
                   href="/movies/${encodeURIComponent(result.id)}/">
                  <span class="search-result-cover-wrap">
                    <img class="search-result-cover"
                         src="${escapeHTML(result.image || fallbackImage)}"
                         data-fallback-src="${escapeHTML(fallbackImage)}"
                         onerror="this.onerror=null; this.src=this.dataset.fallbackSrc;"
                         alt="${title}"
                         loading="lazy">
                  </span>
                  <span class="search-result-content">
                    <span class="search-result-topline">
                      <span class="search-result-kind">${escapeHTML(searchResultsList.dataset.movieLabel || 'Movie')}</span>
                      ${rank !== null ? `<span class="search-result-rank">${escapeHTML(searchResultsList.dataset.relevanceLabel || 'Relevance:')} ${escapeHTML(rank)}</span>` : ''}
                    </span>
                    <strong class="search-result-title">${title}</strong>
                    <span class="search-result-meta">
                      ${result.year ? `<span>${escapeHTML(result.year)}</span>` : ''}
                      ${result.wikidata_id ? `<span>${escapeHTML(result.wikidata_id)}</span>` : ''}
                    </span>
                    ${description ? `<span class="search-result-description">${description}</span>` : ''}
                  </span>
                </a>
              </article>`
            )
          }
        }
      }
      searchResultsList.insertAdjacentHTML('beforeend', HTMLTemplates.join(''))
      requestUrl = jsonResponse.next
      const oldButton = document.querySelector('.load-more-button')
      if (oldButton) oldButton.remove();
      if (jsonResponse.next) {
        const loadMoreButtonHTML = `<button type="button" class="load-more-button">Load More</button>`
        searchResultsList.insertAdjacentHTML('beforeend', loadMoreButtonHTML)

        const newButton = document.querySelector('.load-more-button')
        newButton.addEventListener('click', renderSearchResults)
      } 
    } catch (error) {
      console.error('Failed to load search results:', error.message);
    }
  }
  renderSearchResults();
})();