const watchStatusButtons = document.querySelectorAll(".movie-watch-status-btn");

watchStatusButtons.forEach((btn) => {
  btn.addEventListener("click", async () => {
    const container = btn.closest(".movie-watch-status");
    const movieStatusURL = container ? container.dataset.url : null;
    const movieStatusCsrf = container ? container.dataset.csrf : null;
    const movieId = container ? container.dataset.movieId : null;

    container.querySelectorAll(".movie-watch-status-btn").forEach((button) => {
      button.classList.remove("is-active");
    });

    try {
      const response = await fetch(movieStatusURL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": movieStatusCsrf,
        },
        body: JSON.stringify({
          movie_id: movieId,
          status: btn.dataset.value,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.error || "Не удалось передать данные о статусе фильма");
      }
    } catch (error) {
      throw new Error(error.message || "Не удалось передать данные о статусе фильма");
    }

    void btn.offsetWidth;
    btn.classList.add("is-active");
  });
});
