(() => {
  const list = document.querySelector('[data-search-results]');
  const status = document.querySelector('[data-search-status]');
  const sentinel = document.querySelector('[data-search-sentinel]');
  const retry = document.querySelector('[data-search-retry]');
  const empty = document.querySelector('[data-search-empty]');
  if (!list || !status || !sentinel || !retry || !empty || !list.dataset.apiUrl) return;

  const labels = list.dataset;
  const locale = document.documentElement.lang || 'en';
  const types = new Set(['movie', 'review', 'user', 'person', 'studio', 'country', 'genre', 'typeofwork']);
  const seenResults = new Set();
  const seenPages = new Set();
  const query = (labels.query || '').trim();
  const margin = 300;
  let loading = false;
  let failed = false;
  let renderedCount = 0;
  let observer = null;

  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);

  function localURL(value) {
    if (typeof value !== 'string' || !value) return null;
    try {
      const url = new URL(value, location.href);
      return url.origin === location.origin && ['http:', 'https:'].includes(url.protocol) ? url.href : null;
    } catch {
      return null;
    }
  }

  function imageURL(value) {
    if (typeof value !== 'string' || !value) return '';
    try {
      const url = new URL(value, location.href);
      return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
    } catch {
      return '';
    }
  }

  function image(value, className, alt, fallback = '') {
    const src = imageURL(value) || imageURL(fallback);
    if (!src) return '';
    return `<img class="${className}" src="${escapeHTML(src)}" alt="${escapeHTML(alt)}"
      ${fallback ? `data-fallback-src="${escapeHTML(imageURL(fallback))}"` : ''} loading="lazy">`;
  }

  list.addEventListener('error', event => {
    const img = event.target;
    if (!(img instanceof HTMLImageElement)) return;
    const fallback = img.dataset.fallbackSrc;
    img.removeAttribute('data-fallback-src');
    if (fallback && img.src !== fallback) img.src = fallback;
    else img.hidden = true;
  }, true);

  function truncate(value, limit) {
    const text = String(value ?? '').trim();
    const words = text.split(/\s+/);
    return words.length > limit ? `${words.slice(0, limit).join(' ')} …` : text;
  }

  function date(value) {
    if (!value) return '';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleDateString(locale, { dateStyle: 'medium' });
  }

  function symbol(type) {
    const paths = {
      person: '<circle cx="12" cy="8" r="4"></circle><path d="M5 20c.8-4 3.2-6 7-6s6.2 2 7 6"></path>',
      studio: '<path d="M4 20V7l8-4 8 4v13M8 20v-5h8v5M8 9h1M12 9h1M16 9h1"></path>',
      country: '<path d="M5 21V3h14l-3 5 3 5H5"></path>',
      genre: '<path d="M3 3h8l10 10-8 8L3 11Z"></path><circle cx="7" cy="7" r="1"></circle>',
      typeofwork: '<rect x="3" y="4" width="18" height="16" rx="2"></rect><path d="M8 4v16M16 4v16M3 9h5M3 15h5M16 9h5M16 15h5"></path>',
    };
    return `<span class="search-result-symbol" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false">${paths[type] || paths.person}</svg></span>`;
  }

  function renderResult(result) {
    const title = escapeHTML(result.title || result.wikidata_id || '');
    const description = escapeHTML(truncate(result.description, 34));
    const url = localURL(result.url);
    const kind = escapeHTML(result.type === 'movie' ? result.type_of_work : labels[`${result.type}Label`]);

    if (result.type === 'movie') {
      const tag = url ? 'a' : 'div';
      return `<article class="search-result-card search-result-card--movie">
        <${tag} class="search-result-movie-link" ${url ? `href="${escapeHTML(url)}"` : ''}>
          <span class="search-result-cover-wrap">${image(result.image, 'search-result-cover', result.title, labels.fallbackSrc)}</span>
          <span class="search-result-content">
            ${kind ? `<span class="search-result-topline"><span class="search-result-kind">${kind}</span></span>` : ''}
            <strong class="search-result-title">${title}</strong>
            <span class="search-result-meta">
              ${result.year ? `<span>${escapeHTML(result.year)}</span>` : ''}
              ${result.wikidata_id ? `<span>${escapeHTML(result.wikidata_id)}</span>` : ''}
            </span>
            ${description ? `<span class="search-result-description">${description}</span>` : ''}
          </span>
        </${tag}>
      </article>`;
    }

    if (result.type === 'review') {
      const author = result.author;
      const deleted = !author || author.is_deleted;
      const name = deleted ? labels.deletedUserLabel : author.name;
      const authorURL = deleted ? null : localURL(author.url);
      const authorTag = authorURL ? 'a' : 'span';
      const created = date(result.created_at);
      return `<article class="search-result-card search-result-card--review">
        <div class="search-result-review-head">
          <${authorTag} class="search-result-avatar-link" ${authorURL ? `href="${escapeHTML(authorURL)}"` : ''}>
            ${image(deleted ? labels.avatarFallbackSrc : author.image, 'search-result-avatar search-result-avatar--small', name, labels.avatarFallbackSrc)}
          </${authorTag}>
          <div class="search-result-review-heading">
            <span class="search-result-kind">${kind}</span>
            <h2 class="search-result-title">${url ? `<a href="${escapeHTML(url)}">${title}</a>` : title}</h2>
            <span class="search-result-meta">
              <${authorTag} ${authorURL ? `href="${escapeHTML(authorURL)}"` : ''}>${escapeHTML(name)}</${authorTag}>
              ${created ? `<time datetime="${escapeHTML(result.created_at)}">${escapeHTML(created)}</time>` : ''}
            </span>
          </div>
        </div>
        <p class="search-result-review-text">${escapeHTML(truncate(result.description, 42)).replace(/\r?\n/g, '<br>')}</p>
      </article>`;
    }

    const deleted = result.type === 'user' && result.is_deleted;
    const destination = deleted ? null : url;
    const tag = destination ? 'a' : 'div';
    const joined = deleted ? '' : date(result.date_joined);
    const displayedTitle = deleted ? escapeHTML(labels.deletedUserLabel) : title;
    const visual = result.type === 'user'
      ? image(deleted ? labels.avatarFallbackSrc : result.image, 'search-result-avatar', deleted ? labels.deletedUserLabel : result.title, labels.avatarFallbackSrc)
      : image(result.image, 'search-result-avatar', result.title) || symbol(result.type);
    return `<article class="search-result-card search-result-card--entity">
      <${tag} class="search-result-entity-layout" ${destination ? `href="${escapeHTML(destination)}"` : ''}>
        <span class="search-result-image">${visual}</span>
        <span class="search-result-content">
          <span class="search-result-topline"><span class="search-result-kind">${kind}</span></span>
          <strong class="search-result-title">${displayedTitle}</strong>
          ${!deleted && (joined || result.wikidata_id) ? `<span class="search-result-meta">
            ${joined ? `<span>${escapeHTML(labels.joinedLabel)} ${escapeHTML(joined)}</span>` : ''}
            ${result.wikidata_id ? `<span>${escapeHTML(result.wikidata_id)}</span>` : ''}
          </span>` : ''}
          ${!deleted && description ? `<span class="search-result-description">${description}</span>` : ''}
        </span>
      </${tag}>
    </article>`;
  }

  const firstURL = localURL(labels.apiUrl);
  if (!query || !firstURL) {
    empty.hidden = false;
    sentinel.hidden = true;
    return;
  }
  const initialURL = new URL(firstURL);
  initialURL.searchParams.set('query', query);
  let nextURL = initialURL.href;

  function isNearEnd() {
    const rect = sentinel.getBoundingClientRect();
    return rect.top <= window.innerHeight + margin && rect.bottom >= 0;
  }

  function loadIfNear() {
    if (isNearEnd()) loadMore();
  }

  function stopObserving() {
    observer?.disconnect();
    sentinel.hidden = true;
    window.removeEventListener('scroll', loadIfNear);
    window.removeEventListener('resize', loadIfNear);
  }

  async function loadMore() {
    if (loading || failed || !nextURL) return;
    loading = true;
    list.setAttribute('aria-busy', 'true');
    retry.hidden = true;
    retry.disabled = true;
    status.textContent = status.dataset.loading;
    const requestedURL = nextURL;
    try {
      const response = await fetch(requestedURL, {
        credentials: 'same-origin', headers: { Accept: 'application/json' },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!data || !Array.isArray(data.results) || !Number.isInteger(data.count) || data.count < 0) {
        throw new Error('Invalid search response');
      }
      const followingURL = data.next === null ? null : localURL(data.next);
      if (data.next !== null && (!followingURL || followingURL === requestedURL || seenPages.has(followingURL))) {
        throw new Error('Invalid next page URL');
      }
      const pageKeys = new Set();
      const html = [];
      for (const result of data.results) {
        if (!result || !types.has(result.type) || result.is_missing || !/^\d+$/.test(String(result.id))) continue;
        const key = `${result.type}:${result.id}`;
        if (seenResults.has(key) || pageKeys.has(key)) continue;
        html.push(renderResult(result));
        pageKeys.add(key);
      }
      list.insertAdjacentHTML('beforeend', html.join(''));
      pageKeys.forEach(key => seenResults.add(key));
      renderedCount += pageKeys.size;
      seenPages.add(requestedURL);
      nextURL = followingURL;
      status.textContent = '';
      if (!nextURL) {
        stopObserving();
        empty.hidden = renderedCount > 0;
      }
    } catch (error) {
      failed = true;
      status.textContent = status.dataset.error;
      retry.hidden = false;
      console.error('Search loading failed:', error);
    } finally {
      loading = false;
      retry.disabled = false;
      list.setAttribute('aria-busy', 'false');
      // Observer callbacks need a threshold crossing. Fill a short viewport ourselves.
      if (!failed && nextURL && isNearEnd()) requestAnimationFrame(loadIfNear);
    }
  }

  retry.addEventListener('click', () => {
    failed = false;
    loadMore();
  });
  if ('IntersectionObserver' in window) {
    observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) loadIfNear();
    }, { rootMargin: `${margin}px` });
    observer.observe(sentinel);
  } else {
    window.addEventListener('scroll', loadIfNear, { passive: true });
    window.addEventListener('resize', loadIfNear);
  }
  loadMore();
})();
