const movieStatusURL = "{% url 'movies:set_movie_status' %}";
const reviewVoteCsrf = document.querySelector("#review-vote-csrf [name=csrfmiddlewaretoken]").value;

document.querySelectorAll(".movie-watch-status").forEach((element) => {
  const movieId = element.dataset.movieId;
  const buttons = [...element.querySelectorAll(".movie-watch-status-btn")];

  buttons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const response = await fetch(movieStatusURL, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": reviewVoteCsrf,
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

      btn.classList.remove("is-active");
      void btn.offsetWidth;
      btn.classList.add("is-active");
    });
  });
});
