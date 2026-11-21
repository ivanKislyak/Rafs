// Hearts over movie covers (movies/_like_button.html): add or remove the movie from the
// viewer's Liked Titles playlist (kind FAVOURITE) through the ordinary playlist item API.
//
// Loaded from base.html for signed-in users. The liked state is fetched only when the page has
// hearts (two requests: the own playlists, then the Liked Titles items); hearts inserted later
// (catalog pages, search results) are painted as they appear.
//
// Other scripts stay in sync through the "liked-titles:change" document event:
// detail = { movieId: "42", liked: true, source: "heart" | "menu" }.
(() => {
  const config = document.querySelector("[data-liked-titles]");
  if (!config || typeof apiRequest !== "function") {
    return;
  }
  const { playlistsUrl, labelAdd, labelRemove } = config.dataset;
  const HEART = "[data-like-movie]";
  const liked = new Set();
  const pending = new Set();
  let playlistId = null;
  let ready = false;
  let loading = false;

  // Same routes as movies/urls.py: playlists/<pl_id>/ and playlists/<pl_id>/items/<movie_id>/.
  const playlistUrl = () => `${playlistsUrl}${playlistId}/`;
  const itemUrl = (movieId) => `${playlistsUrl}${playlistId}/items/${movieId}/`;

  function heartsFor(movieId) {
    return document.querySelectorAll(`[data-like-movie="${CSS.escape(String(movieId))}"]`);
  }

  function paint(button) {
    const isLiked = liked.has(button.dataset.likeMovie);
    button.setAttribute("aria-pressed", String(isLiked));
    button.title = isLiked ? labelRemove : labelAdd;
    button.disabled = !ready;
  }

  function replay(button, className) {
    button.classList.remove(className);
    // Force a reflow so the animation restarts on quick repeated clicks.
    void button.offsetWidth;
    button.classList.add(className);
  }

  function setLiked(movieId, isLiked, { animate = false } = {}) {
    const id = String(movieId);
    if (isLiked) {
      liked.add(id);
    } else {
      liked.delete(id);
    }
    heartsFor(id).forEach((button) => {
      paint(button);
      if (animate && isLiked) {
        replay(button, "is-popping");
      }
    });
  }

  async function load() {
    if (ready || loading) {
      return;
    }
    loading = true;
    try {
      const playlists = await apiRequest(playlistsUrl);
      const favourite = playlists.data.find((playlist) => playlist.kind === "FAVOURITE");
      if (!favourite) {
        // No Liked Titles playlist: the hearts stay hidden.
        return;
      }
      playlistId = favourite.id;
      const playlist = await apiRequest(playlistUrl());
      playlist.data.items.forEach((item) => liked.add(String(item.movie.id)));
      ready = true;
      document.querySelectorAll(HEART).forEach(paint);
    } catch (error) {
      // The hearts stay hidden rather than showing a state that may be wrong.
      console.error(error);
    } finally {
      loading = false;
    }
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest(HEART);
    if (!button) {
      return;
    }
    // Covers often sit in clickable cards: the heart must not trigger them.
    event.preventDefault();
    event.stopPropagation();
    const movieId = button.dataset.likeMovie;
    if (!ready || pending.has(movieId)) {
      return;
    }
    const wasLiked = liked.has(movieId);
    pending.add(movieId);
    // Optimistic: fill (or empty) the heart at once, roll back if the request fails.
    setLiked(movieId, !wasLiked, { animate: true });
    try {
      await apiRequest(itemUrl(movieId), { method: wasLiked ? "DELETE" : "PUT" });
      document.dispatchEvent(
        new CustomEvent("liked-titles:change", {
          detail: { movieId, liked: !wasLiked, source: "heart" },
        }),
      );
    } catch (error) {
      console.error(error);
      setLiked(movieId, wasLiked);
      heartsFor(movieId).forEach((heart) => replay(heart, "is-failed"));
    } finally {
      pending.delete(movieId);
    }
  });

  document.addEventListener("animationend", (event) => {
    const button = event.target.closest?.(HEART);
    button?.classList.remove("is-popping", "is-failed");
  });

  // The "Your playlists" menu on the movie page can tick Liked Titles too.
  document.addEventListener("liked-titles:change", (event) => {
    if (event.detail.source !== "heart" && ready) {
      setLiked(event.detail.movieId, event.detail.liked);
    }
  });

  // Hearts added after load (catalog pages, search results, library cards).
  new MutationObserver((mutations) => {
    const added = mutations.some((mutation) =>
      [...mutation.addedNodes].some(
        (node) => node.nodeType === Node.ELEMENT_NODE && (node.matches(HEART) || node.querySelector(HEART)),
      ),
    );
    if (!added) {
      return;
    }
    if (ready) {
      document.querySelectorAll(`${HEART}:disabled`).forEach(paint);
    } else {
      load();
    }
  }).observe(document.body, { childList: true, subtree: true });

  if (document.querySelector(HEART)) {
    load();
  }
})();
