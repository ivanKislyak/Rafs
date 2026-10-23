(() => {
  const urlParams = new URLSearchParams(window.location.search);
  const query = urlParams.get('query') || '';
  const searchResultsList = document.querySelector(".search-results-list")
  const renderSearchResults = async () => {
    try {
      const params = new URLSearchParams();
      params.append("query", `${query}`);
      const response = await fetch(
        `/movies/api/v1/search/?${params.toString()}`, 
        {method: "GET"})
      if (!response.ok) throw new Error(`Response status: ${response.status}`);
      const jsonResponse = await response.json()
      const nextUrl = jsonResponse.next
      const results = jsonResponse.results
      const HTMLTemplates = []

      for (const result of results) {
        if (result.type) {
          if (result.type === "movie") {
            HTMLTemplates.push(
              `<article class="search-result-card search-result-card--movie">
                <a class="search-result-movie-link"
                    href="/movies/${result.id}/">
                    <span class="search-result-cover-wrap">
                      <!-- if-else block -->
                    </span>
                </a>
              </article>`
                    
            )
          }
        }
      }
      searchResultsList.insertAdjacentHTML('beforeend', HTMLTemplates.join(''))
       
    } catch (error) {
      console.error('Failed to load search results:', error.message);
    }
  }
  renderSearchResults();
})();