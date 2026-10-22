(() => {
  const urlParams = new URLSearchParams(window.location.search);
  const query = urlParams.get('query') || '';

  const renderSearchResults = async () => {
    try {
      const params = new URLSearchParams();
      params.append("query", `${query}`);
      const response = await fetch(
        `/movies/api/v1/search/?${params.toString()}`, 
        {method: "GET"})
      if (!response.ok) throw new Error(`Response status: ${response.status}`);
      const jsonResponse = await response.json()
      return jsonResponse
    } catch (error) {
      console.error('Failed to load search results:', error.message);
    }
  }
  renderSearchResults();
})();